#!/usr/bin/env python3
"""Preview Winamp vis atlas animations on host — no DUT required.

Mirrors the ESP32 firmware rendering exactly:
  originX = (screenWidth - WINDOW_W) / 2  = (320 - 275) / 2 = 22
  originY = 0
  vis area: x=originX+RECT_X=46, y=43, w=76, h=16  (1:1 device pixels)

Modes:
  --mode atlas     (default) animate VIS_ATLAS frames from bake_vis.py output
  --mode synthetic animate the firmware's synthetic spectrum engine in Python

Output:
  --out FILE.gif   write animated GIF (default: gen/skin_preview_animated.gif)
  --live           open real-time pygame window (requires pygame)

Usage examples:
  # Animated GIF from atlas (shares gen/ with bake_vis.py):
  python3 tools/preview_vis.py \\
      --atlas SpotifyDiyThing/gen/vis_atlas.npy \\
      --skin  SpotifyDiyThing/gen/skin_preview.png \\
      --out   SpotifyDiyThing/gen/skin_preview_animated.gif

  # Live pygame window — atlas mode:
  python3 tools/preview_vis.py \\
      --atlas SpotifyDiyThing/gen/vis_atlas.npy \\
      --skin  SpotifyDiyThing/gen/skin_preview.png \\
      --live

  # Live pygame window — synthetic mode (no atlas needed):
  python3 tools/preview_vis.py \\
      --skin  SpotifyDiyThing/gen/skin_preview.png \\
      --mode  synthetic --live

  # Select loop sub-range to find a cleaner wrap:
  python3 tools/preview_vis.py \\
      --atlas SpotifyDiyThing/gen/vis_atlas.npy \\
      --skin  SpotifyDiyThing/gen/skin_preview.png \\
      --loop-start 20 --loop-end 380 --live
"""
from __future__ import annotations

import argparse
import math
import pathlib
import random
import re
import sys
import time

import numpy as np
from PIL import Image

# ── firmware geometry (mirrors ESP32 implementation exactly) ──────────────────

def _parse_skin_layout(path):
    d = {}
    for line in open(path):
        m = re.match(r'#define\s+(\w+)\s+([^/]+)', line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d

_skin = _parse_skin_layout(
    pathlib.Path(__file__).parent / "../SpotifyDiyThing/gen/skin_layout.h")

SCREEN_W   = 320
SCREEN_H   = 240
WINDOW_W   = int(_skin["WINDOW_W"])   # from gen/skin_layout.h
WINDOW_H   = int(_skin["WINDOW_H"])

# Matches winampDisplay.h:37-38
ORIGIN_X   = (SCREEN_W - WINDOW_W) // 2   # = 22
ORIGIN_Y   = 0

# Vis area constants — mirrors vuMeter.h namespace vu::
RECT_X     = 24   # vu::RECT_X
LEFT_Y     = 43   # vu::LEFT_Y
RECT_W     = 76   # vu::RECT_W  (19 bars × 4px)
VIS_H      = 16   # vu::VIS_H
SPEC_BARS  = 19   # vu::SPEC_BARS
SPEC_BAR_W = 3    # vu::SPEC_BAR_W
SPEC_BAR_STEP = 4 # vu::SPEC_BAR_STEP

# Vis area in skin_preview.png pixel coordinates.
# bake_skin.py pastes the 275×116 chrome at (0, 0) in the 320×240 canvas
# (render_full_preview line 983: canvas.paste(chrome, (0, 0))).
# So the skin origin within skin_preview.png is (0, 0) — RECT_X / LEFT_Y
# are skin-relative and map directly to preview pixels with no originX shift.
# (originX only applies on the actual 320×240 ESP32 display, not in the preview.)
VIS_X = RECT_X        # = 24  (skin pixel, no originX)
VIS_Y = LEFT_Y + 1   # = 44  (+1 visual alignment tweak for skin_preview.png)

# VIS_ROW_COLOR[] — RGB888 equivalents of the RGB565 palette in vuMeter.h
# Row 0 = highest amplitude (red), Row 15 = lowest (dark green)
VIS_ROW_RGB = [
    (229,  50,  24),   # row  0 — 0xE903
    (202, 104,  16),   # row  1 — 0xCD02
    (214, 106,   0),   # row  2 — 0xD6B0
    (214, 121,   0),   # row  3 — 0xD6CC
    (214, 135,   0),   # row  4 — 0xD6E0
    (198, 222,   8),   # row  5 — 0xC6F1
    (222, 212,  24),   # row  6 — 0xDEA3
    (214, 196,  32),   # row  7 — 0xD6C4
    (189, 184,  40),   # row  8 — 0xBDC5
    (148, 152,  32),   # row  9 — 0x94C4
    ( 41, 148,  16),   # row 10 — 0x2982
    ( 50, 152,  16),   # row 11 — 0x32C2
    ( 57, 172,  16),   # row 12 — 0x3962
    ( 49, 160,   8),   # row 13 — 0x3141
    ( 41,  36,   0),   # row 14 — 0x2920
    ( 24,  32,   8),   # row 15 — 0x1901
]
VIS_PEAK_RGB = (150, 150, 150)   # color 23 from VISCOLOR.TXT — spectrum peak dot

FPS = 20

# ── atlas peak tracker ────────────────────────────────────────────────────────

class AtlasPeakTracker:
    """Winamp peak-dot physics on top of atlas bar heights.

    Gravity model (matches real Winamp behaviour):
      - bar rises above peak → snap peak to bar height, reset fall velocity to 0
      - each frame: vel += GRAVITY; peak -= vel
      - "stick" illusion: initial movement is sub-pixel so appears stationary
        for several frames before becoming visible — no explicit hold counter needed

    Returns peak row indices [0..VIS_H-1] (0 = top of vis area).
    """
    GRAVITY = 0.08   # px/frame² — tuned to ~1 s hang then ~1 s fall across VIS_H

    def __init__(self) -> None:
        self._peak = np.zeros(SPEC_BARS, dtype=float)
        self._vel  = np.zeros(SPEC_BARS, dtype=float)

    def update(self, bar_h: np.ndarray) -> np.ndarray:
        for i in range(SPEC_BARS):
            h = float(bar_h[i])
            if h >= self._peak[i]:
                self._peak[i] = h
                self._vel[i]  = 0.0
            else:
                self._vel[i]  += self.GRAVITY
                self._peak[i]  = max(1.0, self._peak[i] - self._vel[i])
        # row index: top of bar at peak_h → row = VIS_H - peak_h
        rows = np.round(VIS_H - self._peak).astype(int)
        return np.clip(rows, 0, VIS_H - 1)


# ── synthetic spectrum engine (Python port of firmware tickSpectrum) ──────────

class SyntheticVis:
    def __init__(self) -> None:
        self._t     = 0.0
        self._lLvl  = 0.5
        self._rLvl  = 0.5
        self._beat  = 0.0
        self._vel   = np.zeros(SPEC_BARS, dtype=np.float32)
        self._peaks = np.zeros(SPEC_BARS, dtype=np.float32)
        self._lfo   = 0.0
        BEAT_A_MS = 500.0   # 120 BPM
        BEAT_B_MS = 392.0   # ~153 BPM
        self._beat_period_a = BEAT_A_MS / 1000.0
        self._beat_period_b = BEAT_B_MS / 1000.0
        self._beat_a = 0.0
        self._beat_b = 0.0

    def tick(self, dt: float = 1.0 / FPS) -> np.ndarray:
        self._t   += dt
        self._lfo += dt

        lfo_val   = math.sin(self._lfo * 2 * math.pi / 0.7) * 0.15
        self._lLvl = max(0.0, min(1.0, 0.55 + lfo_val))
        self._rLvl = max(0.0, min(1.0, 0.55 - lfo_val))

        self._beat_a = (self._beat_a + dt) % self._beat_period_a
        self._beat_b = (self._beat_b + dt) % self._beat_period_b
        beat_a = math.exp(-self._beat_a / (self._beat_period_a * 0.08))
        beat_b = math.exp(-self._beat_b / (self._beat_period_b * 0.08))
        self._beat = 0.6 * beat_a + 0.4 * beat_b

        tilt     = math.sin(self._t / 14.0) * 4.0
        envelope = (self._lLvl + self._rLvl) * 0.5
        heights  = np.zeros(SPEC_BARS, dtype=np.float32)

        for i in range(SPEC_BARS):
            eff_i      = max(0.0, min(18.0, i - tilt))
            shape      = 1.0 - (eff_i / 18.0) * 0.6
            beat_boost = self._beat * 0.8 if i < 4 else 0.0
            noise      = random.uniform(0.0, 0.12)
            target     = min(1.0, envelope * shape * (1.0 + beat_boost) + noise)

            self._vel[i] = 0.7 * self._vel[i] + 0.3 * (target - heights[i])
            heights[i]   = max(0.0, min(1.0, heights[i] + self._vel[i]))

            if heights[i] > self._peaks[i]:
                self._peaks[i] = heights[i]
            self._peaks[i] -= 1.0 / VIS_H

        bar_h = np.clip(np.round(heights * VIS_H), 0, VIS_H).astype(int)
        self._last_barh  = bar_h
        self._last_peaks = np.clip(np.round(self._peaks * VIS_H), 0, VIS_H - 1).astype(int)
        return bar_h

    @property
    def peaks(self) -> np.ndarray:
        return self._last_peaks


# ── vis renderer ──────────────────────────────────────────────────────────────

class VisRenderer:
    """Renders spectrum bars into a PIL RGB image at 1:1 device pixel scale.

    Mirrors firmware blitVisBackground() + drawFastHLine() pattern exactly.
    skin_preview.png is 320×240 — same coordinate space as the ESP32 display.
    """

    def __init__(self, base_img: Image.Image) -> None:
        self._base = base_img.convert("RGB")
        # Cache the vis-area background pixels from the base skin image.
        # blitVisBackground() restores these before drawing bars — do the same.
        self._vis_bg = self._base.crop(
            (VIS_X, VIS_Y, VIS_X + RECT_W, VIS_Y + VIS_H)
        )

    def render(self, bar_heights: np.ndarray,
               peaks: np.ndarray | None = None) -> Image.Image:
        """Return new RGB PIL Image with bars drawn at firmware coordinates."""
        img = self._base.copy()
        px  = img.load()

        # blitVisBackground equivalent: restore skin background in vis area
        img.paste(self._vis_bg, (VIS_X, VIS_Y))
        px = img.load()

        # Draw bars — mirrors tickAtlas() / tickSpectrum() inner loop
        for i in range(SPEC_BARS):
            bh   = int(bar_heights[i])
            barX = VIS_X + i * SPEC_BAR_STEP   # originX + RECT_X + i * SPEC_BAR_STEP

            # Rows grow from bottom: top row = (VIS_H - bh), bottom row = VIS_H-1
            for r in range(VIS_H - bh, VIS_H):
                color = VIS_ROW_RGB[r]
                py    = VIS_Y + r
                for ppx in range(barX, barX + SPEC_BAR_W):
                    if 0 <= ppx < img.width and 0 <= py < img.height:
                        px[ppx, py] = color

            # Peak dot — fixed gray (VISCOLOR.TXT color 23)
            if peaks is not None:
                pr = int(peaks[i])
                pr = max(0, min(VIS_H - 1, pr))
                py = VIS_Y + pr
                for ppx in range(barX, barX + SPEC_BAR_W):
                    if 0 <= ppx < img.width and 0 <= py < img.height:
                        px[ppx, py] = VIS_PEAK_RGB

        return img


# ── quiet-run trimmer ─────────────────────────────────────────────────────────

def trim_quiet_frames(atlas: np.ndarray, thresh: int = 4,
                      keep_n: int = 2) -> np.ndarray:
    """Collapse contiguous runs of quiet frames to at most keep_n frames.

    A frame is 'quiet' when every bar height <= thresh (raw, before boost).
    From each quiet run the keep_n frames with highest total bar energy are
    kept (spread evenly if the run is longer); active frames are kept as-is.
    """
    # Split into runs of (is_quiet, [rows])
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
            # Pick keep_n frames with highest sum of bar heights
            arr     = np.stack(rows)
            scores  = arr.sum(axis=1)
            indices = np.argsort(scores)[-keep_n:]
            indices = np.sort(indices)   # preserve temporal order
            keep.extend(arr[i] for i in indices)

    return np.stack(keep)


# ── height boost ──────────────────────────────────────────────────────────────

def boost_heights(bar_h: np.ndarray, factor: float) -> np.ndarray:
    """Scale bar heights by factor, clamp to [0, VIS_H]. factor=1.0 = no change."""
    if factor == 1.0:
        return bar_h
    return np.clip(np.round(bar_h.astype(float) * factor), 0, VIS_H).astype(int)


# ── animated GIF output ───────────────────────────────────────────────────────

def write_gif(frames: list[Image.Image], out_path: pathlib.Path,
              fps: int = FPS) -> None:
    duration_ms = round(1000 / fps)
    quantized = [f.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                 for f in frames]
    quantized[0].save(
        out_path,
        save_all=True,
        append_images=quantized[1:],
        loop=0,
        duration=duration_ms,
        optimize=False,
    )
    print(f"Wrote {out_path} ({out_path.stat().st_size // 1024} KB, "
          f"{len(frames)} frames @ {fps} fps)")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Preview Winamp vis animation on host (no DUT required). "
                    "Renders at 1:1 device pixels — matches ESP32 display exactly.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--atlas", metavar="NPY",
                    help="vis_atlas.npy from bake_vis.py (required for --mode atlas)")
    ap.add_argument("--skin", metavar="PNG", required=True,
                    help="skin_preview.png from bake_skin.py (320×240, 1:1 device pixels)")
    ap.add_argument("--mode", choices=["atlas", "synthetic"], default="atlas",
                    help="Animation source (default: atlas)")
    ap.add_argument("--out", metavar="GIF",
                    default="SpotifyDiyThing/gen/skin_preview_animated.gif",
                    help="Output animated GIF path")
    ap.add_argument("--live", action="store_true",
                    help="Open real-time pygame window instead of writing GIF")
    ap.add_argument("--loop-start", type=int, default=0, metavar="FRAME",
                    help="First atlas frame to include (default: 0)")
    ap.add_argument("--loop-end", type=int, default=None, metavar="FRAME",
                    help="Last atlas frame (exclusive) to include (default: all)")
    ap.add_argument("--n-synth-frames", type=int, default=200, metavar="N",
                    help="Synthetic frames to generate for GIF (default: 200)")
    ap.add_argument("--boost", type=float, default=1.5, metavar="X",
                    help="Multiply bar heights by X before rendering (default: 1.5). "
                         "Lifts quiet sections, pushes peaks to ceiling/red rows.")
    ap.add_argument("--trim-quiet", action="store_true", default=True,
                    help="Collapse runs of quiet frames to 1 frame (default: on)")
    ap.add_argument("--no-trim-quiet", dest="trim_quiet", action="store_false",
                    help="Disable quiet-run trimming")
    ap.add_argument("--quiet-thresh", type=int, default=4, metavar="N",
                    help="Max bar height (raw) to count as quiet (default: 4). "
                         "Raw ≤4 = boost×1.5 ≤6 = all-green palette rows.")
    ap.add_argument("--quiet-keep", type=int, default=2, metavar="N",
                    help="Frames to keep per quiet run, highest energy (default: 2)")
    ap.add_argument("--peaks", action="store_true", default=True,
                    help="Overlay peak dots on atlas frames using Winamp physics (default: on)")
    ap.add_argument("--no-peaks", dest="peaks", action="store_false",
                    help="Disable peak dot overlay")
    args = ap.parse_args()

    skin_path = pathlib.Path(args.skin)
    if not skin_path.exists():
        print(f"ERROR: skin not found: {skin_path}", file=sys.stderr)
        sys.exit(1)
    base_img = Image.open(skin_path)
    print(f"Skin: {skin_path}  ({base_img.width}×{base_img.height})")
    print(f"Firmware display: originX={ORIGIN_X}, originY={ORIGIN_Y} (centered on 320px)")
    print(f"Vis area in preview: x={VIS_X}, y={VIS_Y}, w={RECT_W}, h={VIS_H} (skin coords, no originX shift)")

    renderer = VisRenderer(base_img)

    atlas: np.ndarray | None = None
    if args.mode == "atlas":
        if not args.atlas:
            print("ERROR: --atlas required for --mode atlas", file=sys.stderr)
            sys.exit(1)
        atlas = np.load(args.atlas)
        lo    = args.loop_start
        hi    = args.loop_end if args.loop_end is not None else len(atlas)
        atlas = atlas[lo:hi]
        print(f"Atlas: {len(atlas)} frames ({lo}..{hi}), max_height={atlas.max()}")
        if args.trim_quiet:
            before = len(atlas)
            atlas = trim_quiet_frames(atlas, args.quiet_thresh, args.quiet_keep)
            print(f"Trim quiet (thresh={args.quiet_thresh}, keep={args.quiet_keep}): "
                  f"{before} → {len(atlas)} frames (dropped {before - len(atlas)})")

    print(f"Boost: {args.boost}×  Peaks: {args.peaks}")
    if args.live:
        _run_live(renderer, atlas, args.mode, args.boost, args.peaks)
    else:
        _write_gif(renderer, atlas, args.mode, args.out, args.n_synth_frames, args.boost, args.peaks)


def _write_gif(renderer: VisRenderer, atlas: np.ndarray | None, mode: str,
               out_path: str, n_synth: int, boost: float = 1.0,
               show_peaks: bool = True) -> None:
    print("Rendering frames …")
    synth   = SyntheticVis() if mode == "synthetic" else None
    tracker = AtlasPeakTracker() if (mode == "atlas" and show_peaks) else None
    frames: list[Image.Image] = []

    if mode == "atlas" and atlas is not None:
        for fi, row in enumerate(atlas):
            bh    = boost_heights(row, boost)
            peaks = tracker.update(bh) if tracker is not None else None
            frames.append(renderer.render(bh, peaks))
            if fi % 50 == 0:
                print(f"  {fi}/{len(atlas)}", flush=True)
    else:
        for fi in range(n_synth):
            h = synth.tick()
            frames.append(renderer.render(boost_heights(h, boost), synth.peaks))
            if fi % 50 == 0:
                print(f"  {fi}/{n_synth}", flush=True)

    write_gif(frames, pathlib.Path(out_path))


def _run_live(renderer: VisRenderer, atlas: np.ndarray | None, mode: str,
              boost: float = 1.0, show_peaks: bool = True) -> None:
    try:
        import pygame
    except ImportError:
        print("ERROR: pygame not installed. Run: pip install pygame", file=sys.stderr)
        sys.exit(1)

    base = renderer._base
    w, h = base.width, base.height

    pygame.init()
    screen = pygame.display.set_mode((w, h))
    pygame.display.set_caption(f"vis preview — {mode} — originX={ORIGIN_X} visX={VIS_X},Y={VIS_Y}")
    clock = pygame.time.Clock()

    synth     = SyntheticVis() if mode == "synthetic" else None
    tracker   = AtlasPeakTracker() if (mode == "atlas" and show_peaks) else None
    frame_idx = 0
    running   = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        if mode == "atlas" and atlas is not None:
            bar_h = boost_heights(atlas[frame_idx % len(atlas)], boost)
            peaks = tracker.update(bar_h) if tracker is not None else None
            frame_idx += 1
        else:
            bar_h = boost_heights(synth.tick(1.0 / FPS), boost)
            peaks = synth.peaks

        img_pil = renderer.render(bar_h, peaks)
        surf = pygame.image.fromstring(img_pil.tobytes(), img_pil.size, "RGB")
        screen.blit(surf, (0, 0))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
