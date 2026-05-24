#!/usr/bin/env python3
"""Extract bar-height atlas from Winamp 2 screengrab videos → C array + NumPy dump.

Usage:
  python3 bake_vis.py -i ../../resource/Screencast_20260516_060344.webm \
                      -i ../../resource/Screencast_20260516_061832.webm \
                      -o ../SpotifyDiyThing/gen
  sha256sum -c ../SpotifyDiyThing/gen/vis_atlas.sha256

Outputs (relative to -o dir):
  vis_atlas.c       — C source with VIS_ATLAS[N_FRAMES][19]
  vis_atlas.h       — header with VIS_ATLAS_FRAMES, VIS_ATLAS_BARS extern
  vis_atlas.npy     — NumPy array shape [N_FRAMES, 19] uint8 (for preview_vis.py)
  vis_atlas.sha256  — SHA256 of vis_atlas.c (golden check)

Calibration: auto-detects scale + vis area bounds from the blue dotted border
in Winamp 2's MAIN.BMP. See docs/rnd/reports/M-VIS-video-analysis-method.md.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

# ── constants (skin geometry — verified by R&D) ──────────────────────────────

VIS_BARS = 19
VIS_H    = 16   # bar height in skin pixels (rows y=43..58)

# Background dot-matrix: even (x+y) → "O" colour, odd → black
# After VP9 yuv420p compression the BG_O (24,24,41) shifts to roughly (25-35, 26-36, 30-45).
# A pixel is background if it's dark: max channel < BAR_DARK_THRESH.
BAR_DARK_THRESH = 55   # pixels darker than this in all channels are background

# vis content in skin coords: x=24..99 (76 px), y=43..58 (16 px)
SKIN_VIS_X1 = 24
SKIN_VIS_Y1 = 43

# bar geometry: 3px wide + 1px gap = 4px per bar, 19 bars
BAR_STEP = 4

# Known vis rect for the committed screengrab videos (win_x=1, win_y=13, scale=2.5).
# Auto-calibration falls back to these if detection fails.
DEFAULT_SCALE  = 2.5
DEFAULT_WIN_X  = 1
DEFAULT_WIN_Y  = 13


# ── calibration ──────────────────────────────────────────────────────────────

def _vis_rect_from_origin(win_x: int, win_y: int, scale: float) -> tuple[int, int, int, int]:
    x1 = win_x + round(SKIN_VIS_X1 * scale)
    y1 = win_y + round(SKIN_VIS_Y1 * scale)
    x2 = x1 + round(VIS_BARS * BAR_STEP * scale) - 1
    y2 = y1 + round(VIS_H * scale) - 1
    return x1, y1, x2, y2


def calibrate(frame: Image.Image) -> tuple[float, tuple[int, int, int, int]]:
    """Return (scale, vis_rect) using default values (validated R&D measurements).

    Auto-detection of scale and window origin from VP9-compressed video is
    unreliable because compression washes out the blue border markers and the
    bg_O dot colour. For the committed screengrab videos the measurements are
    known (scale=2.5, win_x=1, win_y=13); override with --manual-rect if the
    source video differs.
    """
    rect = _vis_rect_from_origin(DEFAULT_WIN_X, DEFAULT_WIN_Y, DEFAULT_SCALE)
    return DEFAULT_SCALE, rect


# ── bar-height extraction ─────────────────────────────────────────────────────

def extract_bar_heights(frame: Image.Image, scale: float,
                        rect: tuple[int, int, int, int]) -> np.ndarray:
    """Return uint8 array of shape [19] — bar heights 0..VIS_H.

    Background detection: a pixel is background if max(R,G,B) < BAR_DARK_THRESH.
    This handles VP9-compressed footage where the BG_O dot colour (24,24,41)
    compresses to ~(25-35, 26-36, 30-45) — still dark, still below threshold.
    Bar pixels are significantly coloured (green/yellow/red from VISCOLOR.TXT)
    and have at least one channel well above the threshold.
    """
    x1, y1, x2, y2 = rect
    px = np.array(frame.convert("RGB"), dtype=np.uint8)
    h_frame, w_frame = px.shape[:2]
    heights = np.zeros(VIS_BARS, dtype=np.uint8)

    frame_bar_step   = scale * BAR_STEP
    # Sample the centre column of each 3px bar
    frame_bar_centre = scale * 1.5

    for i in range(VIS_BARS):
        col_x = round(x1 + i * frame_bar_step + frame_bar_centre)
        col_x = min(col_x, w_frame - 1)

        # Vectorised: extract column within vis rect and threshold
        col = px[y1:min(y2 + 1, h_frame), col_x]   # shape [N, 3]
        is_bar = col.max(axis=1) >= BAR_DARK_THRESH  # True where bar pixel
        bar_count = int(is_bar.sum())

        # Map frame-pixel count → skin pixel count → clamp to VIS_H
        h = round(bar_count / scale)
        heights[i] = min(h, VIS_H)

    return heights


# ── video processing ──────────────────────────────────────────────────────────

def frames_from_video(video_path: pathlib.Path,
                      target_fps: float = 20.0) -> list[Image.Image]:
    """Decode video and return frames at approximately target_fps."""
    print(f"  decoding {video_path.name} …", flush=True)

    # Use ffmpeg to dump frames as PNG pipe
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
        # PNG magic
        if data[pos:pos+8] != b'\x89PNG\r\n\x1a\n':
            pos += 1
            continue
        # Find next PNG or end
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
    """Return atlas array [N_FRAMES, 19] uint8."""
    all_heights: list[np.ndarray] = []
    scale: float | None = None
    rect:  tuple[int, int, int, int] | None = None

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
                print(f"    scale={scale:.2f}×  vis_rect={rect}", flush=True)

        for frame in frames:
            h = extract_bar_heights(frame, scale, rect)
            all_heights.append(h)

    if not all_heights:
        raise RuntimeError("No frames extracted from any video.")

    atlas = np.stack(all_heights, axis=0).astype(np.uint8)
    return atlas


# ── output emission ───────────────────────────────────────────────────────────

def emit_c(atlas: np.ndarray, out_dir: pathlib.Path) -> bytes:
    n_frames, n_bars = atlas.shape
    lines = []
    lines.append('#include "vis_atlas.h"\n\n')
    lines.append(f"const uint8_t VIS_ATLAS[{n_frames}][{n_bars}] = {{\n")
    for fi in range(n_frames):
        row = ", ".join(str(int(v)) for v in atlas[fi])
        lines.append(f"    {{{row}}},\n")
    lines.append("};\n")
    src = "".join(lines).encode()

    c_path = out_dir / "vis_atlas.c"
    c_path.write_bytes(src)
    print(f"  wrote {c_path} ({len(src):,} bytes)")
    return src


def emit_h(atlas: np.ndarray, out_dir: pathlib.Path) -> None:
    n_frames, n_bars = atlas.shape
    h = f"""\
#pragma once
#include <stdint.h>

#define VIS_ATLAS_FRAMES  {n_frames}
#define VIS_ATLAS_BARS    {n_bars}

extern const uint8_t VIS_ATLAS[VIS_ATLAS_FRAMES][VIS_ATLAS_BARS];
"""
    h_path = out_dir / "vis_atlas.h"
    h_path.write_text(h)
    print(f"  wrote {h_path}")


def emit_npy(atlas: np.ndarray, out_dir: pathlib.Path) -> None:
    import numpy as np
    npy_path = out_dir / "vis_atlas.npy"
    np.save(str(npy_path), atlas)
    print(f"  wrote {npy_path} (shape {atlas.shape})")


def emit_golden(c_src: bytes, out_dir: pathlib.Path) -> None:
    digest = hashlib.sha256(c_src).hexdigest()
    golden_path = out_dir / "vis_atlas.sha256"
    golden_path.write_text(f"{digest}  vis_atlas.c\n")
    print(f"  wrote {golden_path}  ({digest[:16]}…)")


def boost_atlas(atlas: np.ndarray, factor: float) -> np.ndarray:
    """Scale bar heights by factor and clamp to [0, VIS_H]."""
    return np.clip(np.round(atlas.astype(float) * factor), 0, VIS_H).astype(np.uint8)


def trim_quiet_frames(atlas: np.ndarray, thresh: int, keep_n: int) -> np.ndarray:
    """Collapse runs of quiet frames (all bars <= thresh) to keep_n highest-energy frames."""
    runs: list[tuple[bool, list[np.ndarray]]] = []
    for row in atlas:
        quiet = int(row.max()) <= thresh
        if runs and runs[-1][0] == quiet:
            runs[-1][1].append(row)
        else:
            runs.append((quiet, [row]))

    keep: list[np.ndarray] = []
    for quiet, rows in runs:
        if not quiet or len(rows) <= keep_n:
            keep.extend(rows)
        else:
            arr     = np.stack(rows)
            scores  = arr.sum(axis=1)
            indices = np.sort(np.argsort(scores)[-keep_n:])
            keep.extend(arr[i] for i in indices)

    return np.stack(keep)


def report_wrap(atlas: np.ndarray) -> None:
    first = atlas[0].astype(int)
    last  = atlas[-1].astype(int)
    dist  = int(np.sum(np.abs(first - last)))
    print(f"  wrap L1 distance frame[0]↔frame[-1]: {dist}  ", end="")
    if dist > 30:
        print("⚠  visible jump possible — use --loop-end in preview_vis.py to tune")
    else:
        print("✓  smooth wrap")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Bake Winamp vis bar-height atlas from screengrab video(s).")
    ap.add_argument("-i", "--input", dest="inputs", action="append",
                    metavar="VIDEO", required=True,
                    help="Input video file (repeat for multiple, concatenated in order)")
    ap.add_argument("-o", "--output", default=".", metavar="DIR",
                    help="Output directory (default: .)")
    ap.add_argument("--fps", type=float, default=20.0,
                    help="Target atlas frame rate (default: 20)")
    ap.add_argument("--manual-rect", metavar="X1,Y1,X2,Y2", default=None,
                    help="Override vis rect in frame pixels (skip auto-calibration). "
                         "Committed videos: 61,121,248,158 (win_x=1,win_y=13,scale=2.5)")
    ap.add_argument("--boost", type=float, default=1.5, metavar="X",
                    help="Multiply bar heights by X, clamp to VIS_H (default: 1.5)")
    ap.add_argument("--trim-quiet", action="store_true", default=True,
                    help="Collapse quiet runs to keep_n highest-energy frames (default: on)")
    ap.add_argument("--no-trim-quiet", dest="trim_quiet", action="store_false",
                    help="Disable quiet-run trimming")
    ap.add_argument("--quiet-thresh", type=int, default=4, metavar="N",
                    help="Max raw bar height to count as quiet, applied before boost (default: 4)")
    ap.add_argument("--quiet-keep", type=int, default=2, metavar="N",
                    help="Frames to keep per quiet run (default: 2)")
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
            print("ERROR: --manual-rect requires exactly 4 comma-separated ints", file=sys.stderr)
            sys.exit(1)
        manual_rect = tuple(parts)

    print(f"Processing {len(video_paths)} video(s) at {args.fps} Hz …")
    atlas = process_videos(video_paths, args.fps, manual_rect)

    n_frames, n_bars = atlas.shape
    kb = n_frames * n_bars / 1024
    print(f"\nAtlas (raw): {n_frames} frames × {n_bars} bars, max_height={atlas.max()}")

    if args.trim_quiet:
        before = len(atlas)
        atlas = trim_quiet_frames(atlas, args.quiet_thresh, args.quiet_keep)
        print(f"Trim quiet (thresh={args.quiet_thresh}, keep={args.quiet_keep}): "
              f"{before} → {len(atlas)} frames (dropped {before - len(atlas)})")

    if args.boost != 1.0:
        atlas = boost_atlas(atlas, args.boost)
        print(f"Boost {args.boost}×: max_height now {atlas.max()}")

    n_frames, n_bars = atlas.shape
    kb = n_frames * n_bars / 1024
    print(f"Atlas (final): {n_frames} frames × {n_bars} bars = {n_frames * n_bars:,} bytes ({kb:.1f} KB)")
    print(f"  Duration: {n_frames / args.fps:.1f} s")

    report_wrap(atlas)

    print("\nEmitting outputs …")
    c_src = emit_c(atlas, out_dir)
    emit_h(atlas, out_dir)
    emit_npy(atlas, out_dir)
    emit_golden(c_src, out_dir)

    print("\nDone. Verify with:")
    print(f"  cd {out_dir} && sha256sum -c vis_atlas.sha256")


if __name__ == "__main__":
    main()
