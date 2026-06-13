#!/usr/bin/env python3
"""Preview Winamp oscilloscope waveform atlas animation on host — no DUT required.

Mirrors the ESP32 firmware tickWave() rendering:
  - Wave drawn as white (255,255,255) line connecting adjacent columns
  - Vertical fill between prev_y and current y (Winamp connect-the-dots)
  - Background restored from skin_preview.png vis area each frame

Output:
  gen/skin_preview_wave.gif  — full 320×240 animated GIF at 20 fps
  gen/wave_zoom.gif          — 6× zoom of vis area only (76×16 → 456×96), nearest-neighbour

Usage:
  python3 tools/preview_wave.py \\
      --atlas gen/wave_atlas.npy \\
      --skin  gen/skin_preview.png \\
      --out   gen/skin_preview_wave.gif
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
from PIL import Image
from preview_common import SCREEN_W, SCREEN_H, write_gif

# ── firmware geometry (mirrors preview_vis.py / vuMeter.h) ────────────────────

WINDOW_W = 275
ORIGIN_X = (SCREEN_W - WINDOW_W) // 2   # = 22 (device only; preview uses skin coords)

# Vis area in skin_preview.png coordinates (1:1 device pixels, no originX shift)
RECT_X   = 24    # vu::RECT_X
LEFT_Y   = 43    # vu::LEFT_Y
RECT_W   = 76    # vu::RECT_W (19 bars × 4px = 76 skin px)
VIS_H    = 16    # vu::VIS_H

VIS_X = RECT_X          # = 24
VIS_Y = LEFT_Y + 1      # = 44 (same +1 alignment tweak as preview_vis.py)

VIS_WAVE_COLOR = (255, 255, 255)   # VISCOLOR[18] = white; firmware VIS_WAVE_COLOR = 0xFFFF

FPS = 20
ZOOM = 6


# ── wave renderer ─────────────────────────────────────────────────────────────

class WaveRenderer:
    """Renders oscilloscope waveform into a PIL RGB image at 1:1 device pixel scale.

    Mirrors firmware tickWave(): white line connecting (x-1,prev_y) to (x,y) vertically.
    """

    def __init__(self, base_img: Image.Image) -> None:
        self._base = base_img.convert("RGB")
        self._vis_bg = self._base.crop(
            (VIS_X, VIS_Y, VIS_X + RECT_W, VIS_Y + VIS_H)
        )

    def render(self, wave_row: np.ndarray) -> Image.Image:
        """Return new RGB PIL Image with waveform drawn at firmware coordinates."""
        img = self._base.copy()
        img.paste(self._vis_bg, (VIS_X, VIS_Y))

        prev_y = VIS_Y + int(wave_row[0])
        for x in range(RECT_W):
            y = VIS_Y + int(wave_row[x])
            y = max(VIS_Y, min(VIS_Y + VIS_H - 1, y))

            y_top = min(y, prev_y)
            y_bot = max(y, prev_y)
            for py in range(y_top, y_bot + 1):
                if 0 <= VIS_X + x < img.width and 0 <= py < img.height:
                    img.putpixel((VIS_X + x, py), VIS_WAVE_COLOR)

            prev_y = y

        return img

    @property
    def vis_bg(self) -> Image.Image:
        return self._vis_bg


# ── zoom crop ─────────────────────────────────────────────────────────────────

def zoom_vis(img: Image.Image, factor: int = ZOOM) -> Image.Image:
    """Return nearest-neighbour upscale of the vis area only."""
    crop = img.crop((VIS_X, VIS_Y, VIS_X + RECT_W, VIS_Y + VIS_H))
    return crop.resize((RECT_W * factor, VIS_H * factor), Image.NEAREST)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Preview Winamp oscilloscope waveform atlas as animated GIF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--atlas", metavar="NPY", required=True,
                    help="wave_atlas.npy from bake_wave.py")
    ap.add_argument("--skin", metavar="PNG", required=True,
                    help="skin_preview.png from bake_skin.py (320×240, 1:1 device pixels)")
    ap.add_argument("--out", metavar="GIF",
                    default="gen/skin_preview_wave.gif",
                    help="Output animated GIF path (default: gen/skin_preview_wave.gif)")
    ap.add_argument("--zoom-out", metavar="GIF", default=None,
                    help="Zoom GIF path (default: <out-dir>/wave_zoom.gif)")
    ap.add_argument("--zoom", type=int, default=ZOOM,
                    help=f"Zoom factor for vis-area crop GIF (default: {ZOOM})")
    ap.add_argument("--fps", type=int, default=FPS,
                    help=f"Frames per second for output GIF (default: {FPS})")
    args = ap.parse_args()

    skin_path  = pathlib.Path(args.skin)
    atlas_path = pathlib.Path(args.atlas)
    out_path   = pathlib.Path(args.out)

    for p in (skin_path, atlas_path):
        if not p.exists():
            print(f"ERROR: not found: {p}", file=sys.stderr)
            sys.exit(1)

    zoom_path = pathlib.Path(args.zoom_out) if args.zoom_out \
                else out_path.parent / "wave_zoom.gif"

    base_img = Image.open(skin_path)
    print(f"Skin:  {skin_path}  ({base_img.width}×{base_img.height})")

    atlas = np.load(str(atlas_path))
    print(f"Atlas: {atlas_path}  shape={atlas.shape}  "
          f"min={int(atlas.min())} max={int(atlas.max())} mean={atlas.mean():.2f}")

    if atlas.shape[1] != RECT_W:
        print(f"ERROR: atlas has {atlas.shape[1]} cols, expected {RECT_W}", file=sys.stderr)
        sys.exit(1)

    renderer = WaveRenderer(base_img)
    print(f"Vis area: x={VIS_X} y={VIS_Y} w={RECT_W} h={VIS_H} (skin coords, no originX shift)")
    print(f"Wave colour: {VIS_WAVE_COLOR}  Centre row: {(VIS_H-1)//2} (abs y {VIS_Y+(VIS_H-1)//2})")
    print(f"Rendering {len(atlas)} frames …")

    full_frames: list[Image.Image] = []
    zoom_frames: list[Image.Image] = []

    for fi, row in enumerate(atlas):
        img = renderer.render(row)
        full_frames.append(img)
        zoom_frames.append(zoom_vis(img, args.zoom))
        if fi % 50 == 0:
            print(f"  {fi}/{len(atlas)}", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_gif(full_frames, out_path, args.fps)
    write_gif(zoom_frames, zoom_path, args.fps)
    print(f"Zoom GIF ({args.zoom}×, {RECT_W*args.zoom}×{VIS_H*args.zoom} px): see {zoom_path}")


if __name__ == "__main__":
    main()
