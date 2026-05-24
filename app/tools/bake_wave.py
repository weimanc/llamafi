#!/usr/bin/env python3
"""Extract oscilloscope waveform atlas from Winamp 2 screengrab video → C array + NumPy dump.

Usage:
  python3 tools/bake_wave.py -i ../../resource/Screencast_20260516_061832.webm \
                              -o SpotifyDiyThing/gen
  cd SpotifyDiyThing/gen && sha256sum -c wave_atlas.sha256

Outputs (relative to -o dir):
  wave_atlas.c       — C source with WAVE_ATLAS[N_FRAMES][76]
  wave_atlas.h       — header with WAVE_ATLAS_FRAMES, WAVE_ATLAS_COLS extern
  wave_atlas.npy     — NumPy array shape [N_FRAMES, 76] uint8 (gitignored, for preview_wave.py)
  wave_atlas.sha256  — SHA256 of wave_atlas.c (golden check)

Calibration: same window origin / scale as bake_vis.py (win_x=1, win_y=13, scale=2.5).
The vis area in frame pixels is (61, 120, 250, 159) — same 76×16 region as the spectrum vis.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image

# ── geometry (mirrors bake_vis.py + vuMeter.h constants) ─────────────────────

VIS_COLS = 76    # skin pixel columns in vis area (19 bars × 4px)
VIS_H    = 16    # vis height in skin pixels (rows 0..15, 0=top)

# Background dot-matrix (same as bake_vis.py): BG_O = (24,24,41) → "dark" after VP9
BAR_DARK_THRESH = 55   # max channel for background pixel (same threshold as bake_vis.py)

# White foreground threshold: VP9 rounding on Winamp's pure-white waveform line
# Winamp VISCOLOR[18] = (255,255,255). After VP9 yuv420p, can drop to ~225-245.
WHITE_THRESH = 200   # all three channels must exceed this

# Skin-relative vis origin (same as bake_vis.py SKIN_VIS_X1 / SKIN_VIS_Y1)
SKIN_VIS_X1 = 24
SKIN_VIS_Y1 = 43

# Known calibration for the committed screengrab videos (win_x=1, win_y=13, scale=2.5).
DEFAULT_SCALE = 2.5
DEFAULT_WIN_X = 1
DEFAULT_WIN_Y = 13

# Frame-pixel vis rect (derived from defaults above — verified in R&D):
#   x1 = 1 + round(24*2.5) = 61
#   y1 = 13 + round(43*2.5) = 120
#   x2 = 61 + round(76*2.5) - 1 = 250
#   y2 = 120 + round(16*2.5) - 1 = 159
_DEFAULT_RECT = (61, 120, 250, 159)


# ── calibration ───────────────────────────────────────────────────────────────

def _vis_rect_from_origin(win_x: int, win_y: int, scale: float) -> tuple[int, int, int, int]:
    x1 = win_x + round(SKIN_VIS_X1 * scale)
    y1 = win_y + round(SKIN_VIS_Y1 * scale)
    x2 = x1 + round(VIS_COLS * scale) - 1
    y2 = y1 + round(VIS_H * scale) - 1
    return x1, y1, x2, y2


def calibrate(frame: Image.Image) -> tuple[float, tuple[int, int, int, int]]:
    """Return (scale, vis_rect) using default calibration (validated R&D measurements)."""
    rect = _vis_rect_from_origin(DEFAULT_WIN_X, DEFAULT_WIN_Y, DEFAULT_SCALE)
    return DEFAULT_SCALE, rect


# ── waveform extraction ───────────────────────────────────────────────────────

def extract_wave_row(frame: Image.Image, scale: float,
                     rect: tuple[int, int, int, int]) -> np.ndarray:
    """Return uint8 array of shape [76] — waveform y positions 0..VIS_H-1.

    0 = top of vis area, VIS_H-1 = bottom.  Fallback for no-signal columns: VIS_H//2.

    Detection: scan each skin column for frame-space pixels with R,G,B > WHITE_THRESH.
    When multiple white pixels exist in a column (Winamp fills vertically between samples),
    take the one farthest from the vis-area vertical centre — that's the peak excursion.
    """
    x1, y1, x2, y2 = rect
    px = np.array(frame.convert("RGB"), dtype=np.uint8)
    h_frame, w_frame = px.shape[:2]

    # Float array — keep fractional skin-row precision (1/scale = 0.4 rows per frame px).
    # Rounding happens only at the final quantize/dither step so the full pipeline
    # (boost, smooth, error-diffusion) operates on sub-pixel values.
    wave = np.full(VIS_COLS, VIS_H / 2.0, dtype=np.float32)

    # Centre row in frame pixels (between skin rows 7 and 8)
    centre_frame = y1 + round((VIS_H / 2) * scale)

    row_indices = np.arange(y1, min(y2 + 1, h_frame))

    for col_skin in range(VIS_COLS):
        col_frame = x1 + round(col_skin * scale)
        col_frame = min(col_frame, w_frame - 1)

        col_px = px[y1:min(y2 + 1, h_frame), col_frame]  # shape [N, 3]
        is_white = (col_px[:, 0] > WHITE_THRESH) & \
                   (col_px[:, 1] > WHITE_THRESH) & \
                   (col_px[:, 2] > WHITE_THRESH)

        if not is_white.any():
            # Propagate left neighbour rather than snapping to centre.
            if col_skin > 0:
                wave[col_skin] = wave[col_skin - 1]
            continue

        white_rows = row_indices[is_white]
        # Farthest from centre → peak excursion
        dists = np.abs(white_rows.astype(int) - centre_frame)
        peak_frame_row = int(white_rows[np.argmax(dists)])

        # Sub-pixel precision: do NOT round here
        skin_row = (peak_frame_row - y1) / scale
        wave[col_skin] = float(np.clip(skin_row, 0, VIS_H - 1))

    return wave


# ── video processing ──────────────────────────────────────────────────────────

def frames_from_video(video_path: pathlib.Path,
                      target_fps: float = 20.0) -> list[Image.Image]:
    """Decode video and return frames at approximately target_fps."""
    print(f"  decoding {video_path.name} …", flush=True)
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"fps={target_fps}",
        "-f", "image2pipe", "-vcodec", "png", "-",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[-500:]}")

    frames: list[Image.Image] = []
    data = result.stdout
    pos = 0
    while pos < len(data):
        if data[pos:pos + 8] != b'\x89PNG\r\n\x1a\n':
            pos += 1
            continue
        next_pos = data.find(b'\x89PNG\r\n\x1a\n', pos + 8)
        chunk = data[pos: next_pos if next_pos != -1 else len(data)]
        try:
            img = Image.open(io.BytesIO(chunk))
            img.load()
            frames.append(img.copy())
        except Exception:
            pass
        if next_pos == -1:
            break
        pos = next_pos

    print(f"    → {len(frames)} frames at {target_fps} Hz", flush=True)
    return frames


def process_videos(video_paths: list[pathlib.Path],
                   fps: float = 20.0,
                   manual_rect: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Return atlas array [N_FRAMES, 76] uint8."""
    all_waves: list[np.ndarray] = []
    scale: float | None = None
    rect: tuple[int, int, int, int] | None = None

    for vpath in video_paths:
        frames = frames_from_video(vpath, fps)
        if not frames:
            print(f"  WARNING: no frames from {vpath.name}", file=sys.stderr)
            continue

        if rect is None:
            if manual_rect is not None:
                rect  = manual_rect
                scale = DEFAULT_SCALE
                print(f"  using manual vis rect: {rect}  scale={scale:.2f}×", flush=True)
            else:
                print("  calibrating vis area …", flush=True)
                scale, rect = calibrate(frames[0])
                x1, y1, x2, y2 = rect
                print(f"    scale={scale:.2f}×  vis_rect=({x1},{y1},{x2},{y2})", flush=True)
                print(f"    crop size in frame: {x2-x1+1}×{y2-y1+1} px  "
                      f"({(x2-x1+1)/scale:.1f}×{(y2-y1+1)/scale:.1f} skin px)", flush=True)

        for i, frame in enumerate(frames):
            w = extract_wave_row(frame, scale, rect)
            all_waves.append(w)
            if i == 0:
                # Spot-check first frame
                print(f"  frame[0] sample: col[0..9]={w[:10].tolist()}  "
                      f"col[38]={int(w[38])} (centre={VIS_H//2})", flush=True)

    if not all_waves:
        raise RuntimeError("No frames extracted from any video.")

    atlas = np.stack(all_waves, axis=0)   # float32, sub-pixel precision
    return atlas


# ── post-processing pipeline (all operate on float32 atlas) ──────────────────

def apply_dc_offset(atlas_f: np.ndarray, offset: int) -> np.ndarray:
    return np.clip(atlas_f + offset, 0, VIS_H - 1)


def apply_boost(atlas_f: np.ndarray, factor: float) -> np.ndarray:
    """Amplify deviation from centre, hard-clip to [0, VIS_H-1]."""
    centre = VIS_H // 2
    return np.clip(centre + (atlas_f - centre) * factor, 0, VIS_H - 1)


def apply_spatial_smooth(atlas_f: np.ndarray, size: int) -> np.ndarray:
    """Low-pass filter along the column (x) axis. Rounds staircase on sloped sections."""
    from scipy.ndimage import uniform_filter1d
    return uniform_filter1d(atlas_f, size=size, axis=1, mode='nearest')


def apply_temporal_smooth(atlas_f: np.ndarray, size: int) -> np.ndarray:
    """Low-pass filter along the time axis. Damps frame-to-frame shimmer."""
    from scipy.ndimage import uniform_filter1d
    return uniform_filter1d(atlas_f, size=size, axis=0, mode='wrap')


def apply_error_diffusion(atlas_f: np.ndarray) -> np.ndarray:
    """1D Floyd-Steinberg error diffusion along the column (x) axis per frame.

    Carries quantization error forward to the next column, breaking long
    horizontal plateaus into a spatially dithered alternation between two
    adjacent rows. No temporal component — operates within each frame only.
    """
    n_frames, n_cols = atlas_f.shape
    out = np.empty_like(atlas_f, dtype=np.uint8)
    for t in range(n_frames):
        err = 0.0
        for x in range(n_cols):
            v = float(atlas_f[t, x]) + err
            q = int(np.clip(round(v), 0, VIS_H - 1))
            err = v - q
            out[t, x] = q
    return out


def apply_dither(atlas_f: np.ndarray) -> np.ndarray:
    """Temporal ordered dither: use fractional wave-y to alternate between two
    adjacent rows across frames, giving perceived sub-pixel vertical resolution.

    Uses an 8-step Bayer sequence along the time axis so the pattern is
    deterministic and stable (no flicker on slow-moving sections).
    """
    bayer = np.array([0, 4, 2, 6, 1, 5, 3, 7], dtype=float) / 8.0
    n_frames = atlas_f.shape[0]
    threshold = bayer[np.arange(n_frames) % 8]          # [n_frames]
    base = np.floor(atlas_f).astype(int)
    frac = atlas_f - np.floor(atlas_f)
    round_up = frac >= threshold[:, np.newaxis]          # broadcast over cols
    return np.clip(base + round_up.astype(int), 0, VIS_H - 1).astype(np.uint8)


def quantize(atlas_f: np.ndarray) -> np.ndarray:
    return np.clip(np.round(atlas_f), 0, VIS_H - 1).astype(np.uint8)


# ── diagnostics ───────────────────────────────────────────────────────────────

def report_flat_frames(atlas: np.ndarray, flat_radius: int = 1) -> None:
    """Report how many frames are effectively flat (all cols near centre)."""
    centre = VIS_H // 2
    flat_mask = (np.abs(atlas.astype(int) - centre) <= flat_radius).all(axis=1)
    n_flat = int(flat_mask.sum())
    pct = 100 * n_flat / len(atlas)
    print(f"  Flat frames (all cols within ±{flat_radius} of centre={centre}): "
          f"{n_flat}/{len(atlas)} ({pct:.1f}%)")
    if n_flat == len(atlas):
        print("  WARNING: all frames are flat — check vis rect calibration")
    elif n_flat > len(atlas) * 0.5:
        print("  NOTE: >50% flat — video may include silent/paused segments")


def report_wrap(atlas: np.ndarray) -> None:
    first = atlas[0].astype(int)
    last  = atlas[-1].astype(int)
    dist  = int(np.sum(np.abs(first - last)))
    print(f"  Wrap L1 distance frame[0]↔frame[-1]: {dist}  ", end="")
    if dist > 76:
        print("⚠  visible jump possible")
    else:
        print("✓  smooth wrap")


# ── output emission ───────────────────────────────────────────────────────────

def emit_c(atlas: np.ndarray, out_dir: pathlib.Path) -> bytes:
    n_frames, n_cols = atlas.shape
    lines = []
    lines.append('#include "wave_atlas.h"\n\n')
    lines.append(f"const uint8_t WAVE_ATLAS[{n_frames}][{n_cols}] = {{\n")
    for fi in range(n_frames):
        row = ", ".join(str(int(v)) for v in atlas[fi])
        lines.append(f"    {{{row}}},\n")
    lines.append("};\n")
    src = "".join(lines).encode()
    c_path = out_dir / "wave_atlas.c"
    c_path.write_bytes(src)
    print(f"  wrote {c_path} ({len(src):,} bytes)")
    return src


def emit_h(atlas: np.ndarray, out_dir: pathlib.Path) -> None:
    n_frames, n_cols = atlas.shape
    h = f"""\
#pragma once
#include <stdint.h>

#define WAVE_ATLAS_FRAMES  {n_frames}
#define WAVE_ATLAS_COLS    {n_cols}

extern const uint8_t WAVE_ATLAS[WAVE_ATLAS_FRAMES][WAVE_ATLAS_COLS];
"""
    h_path = out_dir / "wave_atlas.h"
    h_path.write_text(h)
    print(f"  wrote {h_path}")


def emit_npy(atlas: np.ndarray, out_dir: pathlib.Path) -> None:
    npy_path = out_dir / "wave_atlas.npy"
    np.save(str(npy_path), atlas)
    print(f"  wrote {npy_path} (shape {atlas.shape})")


def emit_golden(c_src: bytes, out_dir: pathlib.Path) -> None:
    digest = hashlib.sha256(c_src).hexdigest()
    golden_path = out_dir / "wave_atlas.sha256"
    golden_path.write_text(f"{digest}  wave_atlas.c\n")
    print(f"  wrote {golden_path}  ({digest[:16]}…)")
    print("  NOTE: SHA256 is machine/ffmpeg-version specific. "
          "Re-generate on a new machine rather than copying.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Bake Winamp oscilloscope waveform atlas from screengrab video.")
    ap.add_argument("-i", "--input", dest="inputs", action="append",
                    metavar="VIDEO", required=True,
                    help="Input video file (repeat for multiple, concatenated in order)")
    ap.add_argument("-o", "--output", default=".", metavar="DIR",
                    help="Output directory (default: .)")
    ap.add_argument("--fps", type=float, default=20.0,
                    help="Target atlas frame rate (default: 20)")
    ap.add_argument("--manual-rect", metavar="X1,Y1,X2,Y2", default=None,
                    help="Override vis rect in frame pixels (skip auto-calibration). "
                         "Committed oscilloscope video: 61,121,250,160")
    ap.add_argument("--dc-offset", type=int, default=0, metavar="N",
                    help="Add N to every wave_y value after extraction, clamp to [0,VIS_H-1]. "
                         "Positive = shift waveform DOWN in the display (larger skin row). "
                         "Use to correct systematic calibration bias (default: 0). "
                         "Committed oscilloscope video: +3")
    ap.add_argument("--boost", type=float, default=1.0, metavar="X",
                    help="Amplify waveform deviation from centre by X, then hard-clip to "
                         "[0, VIS_H-1]. 1.0 = no change. 2.0 doubles excursion. "
                         "High values rail the signal to ceiling/floor (default: 1.0)")
    ap.add_argument("--spatial-smooth", type=int, default=0, metavar="N",
                    help="Box-filter kernel width along the column (x) axis. "
                         "Smooths column-to-column jumps / staircase artefacts. "
                         "0 = off. Recommended: 3–5 (default: 0)")
    ap.add_argument("--temporal-smooth", type=int, default=0, metavar="N",
                    help="Box-filter kernel width along the time axis. "
                         "Damps frame-to-frame shimmer. 0 = off. Recommended: 3 (default: 0)")
    ap.add_argument("--dither", action="store_true", default=False,
                    help="Apply 8-step Bayer temporal dither using the fractional wave-y "
                         "position. Gives perceived sub-pixel vertical resolution. "
                         "Most effective after --spatial-smooth and --temporal-smooth.")
    ap.add_argument("--error-diffusion", action="store_true", default=False,
                    help="Apply 1D Floyd-Steinberg error diffusion along the column axis "
                         "per frame. Breaks horizontal plateau runs into a spatially "
                         "dithered alternation. No temporal component.")
    ap.add_argument("--frame-start", type=int, default=0, metavar="N",
                    help="First frame index to keep (0-based, inclusive). "
                         "Use to skip a frozen/static lead-in in the source video.")
    ap.add_argument("--frame-end", type=int, default=None, metavar="N",
                    help="Last frame index to keep (0-based, inclusive). "
                         "Default: last frame.")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    video_paths = [pathlib.Path(p) for p in args.inputs]
    for vp in video_paths:
        if not vp.exists():
            print(f"ERROR: {vp} not found", file=sys.stderr)
            sys.exit(1)

    manual_rect = None
    if args.manual_rect:
        parts = [int(x) for x in args.manual_rect.split(",")]
        if len(parts) != 4:
            print("ERROR: --manual-rect requires exactly 4 comma-separated ints",
                  file=sys.stderr)
            sys.exit(1)
        manual_rect = tuple(parts)

    print(f"Processing {len(video_paths)} video(s) at {args.fps} Hz …")
    atlas_raw = process_videos(video_paths, args.fps, manual_rect)

    # ── frame trimming ────────────────────────────────────────────────────────
    fs = args.frame_start
    fe = (args.frame_end + 1) if args.frame_end is not None else len(atlas_raw)
    if fs != 0 or fe != len(atlas_raw):
        atlas_raw = atlas_raw[fs:fe]
        print(f"Frame trim: [{fs}:{fe}] → {len(atlas_raw)} frames")

    # ── float pipeline: extraction already float32, keep precision throughout ─
    atlas_f = atlas_raw  # float32, sub-pixel skin-row values

    if args.dc_offset != 0:
        atlas_f = apply_dc_offset(atlas_f, args.dc_offset)
        print(f"DC offset +{args.dc_offset}")

    if args.boost != 1.0:
        atlas_f = apply_boost(atlas_f, args.boost)
        print(f"Boost {args.boost}×")

    if args.spatial_smooth > 1:
        atlas_f = apply_spatial_smooth(atlas_f, args.spatial_smooth)
        print(f"Spatial smooth kernel={args.spatial_smooth}")

    if args.temporal_smooth > 1:
        atlas_f = apply_temporal_smooth(atlas_f, args.temporal_smooth)
        print(f"Temporal smooth kernel={args.temporal_smooth}")

    if args.error_diffusion:
        atlas = apply_error_diffusion(atlas_f)
        print("Error diffusion: 1D Floyd-Steinberg along x")
    elif args.dither:
        atlas = apply_dither(atlas_f)
        print("Dither: 8-step Bayer temporal")
    else:
        atlas = quantize(atlas_f)

    n_frames, n_cols = atlas.shape
    print(f"\nAtlas: {n_frames} frames × {n_cols} cols  "
          f"min={int(atlas.min())} max={int(atlas.max())} "
          f"mean={atlas.mean():.2f} centre={VIS_H//2}")
    print(f"  Duration: {n_frames / args.fps:.1f} s  "
          f"Size: {n_frames * n_cols:,} bytes ({n_frames * n_cols / 1024:.1f} KB)")

    report_flat_frames(atlas)
    report_wrap(atlas)

    print("\nEmitting outputs …")
    c_src = emit_c(atlas, out_dir)
    emit_h(atlas, out_dir)
    emit_npy(atlas, out_dir)
    emit_golden(c_src, out_dir)

    print("\nDone. Verify with:")
    print(f"  cd {out_dir} && sha256sum -c wave_atlas.sha256")


if __name__ == "__main__":
    main()
