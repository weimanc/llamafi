#!/usr/bin/env python3
"""Interactive taskbar-layout preview for M-MULTIAPP shell geometry.

Opens a scaled pygame window showing the full 320×240 device canvas with the
taskbar strip rendered on the right edge.  Keyboard shortcuts cycle aesthetic
parameters in real time.  Pressing `e` writes gen/shell_layout.h with the
approved values.

Usage:
    python3 tools/preview_layout.py --wsz skins/base-2.91.wsz
    python3 tools/preview_layout.py --wsz skins/base-2.91.wsz --scale 3
    python3 tools/preview_layout.py --wsz skins/base-2.91.wsz --export   # headless export

Keyboard controls (interactive mode):
    b   Cycle taskbar background colour
    i   Cycle active indicator style  A=3px bar | B=full cell | C=dot
    s   Toggle separator lines on/off
    c   Cycle active indicator colour
    [   Step active slot left (preview indicator on different app slots)
    ]   Step active slot right
    +   Increase scale (1–4)
    -   Decrease scale (1–4)
    e   Export approved params to gen/shell_layout.h
    p   Print current params as bake_skin.py CLI args
    q   Quit
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

from PIL import Image, ImageDraw

# Reuse bake_skin's BI_RLE8-aware BMP loader (TEXT.BMP needs it).
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from bake_skin import load_bmp, open_skin

# ── constants ─────────────────────────────────────────────────────────────────

SCREEN_W = 320
SCREEN_H = 240

# Taskbar geometry — fixed by ADR-025 / shell-layout.md.
TASKBAR_X          = 275
TASKBAR_W          = 45
TASKBAR_SLOT_COUNT = 6
TASKBAR_SLOT_H     = 40   # 6 × 40 == 240
TASKBAR_ICON_W     = 24
TASKBAR_ICON_H     = 24

# Winamp 5×6 glyph dimensions.
GLYPH_W = 5
GLYPH_H = 6

# Icon glyphs per slot — chars from TEXT.BMP CHAR_MAP.
# UV offsets: col × GLYPH_W, row × GLYPH_H.
_SLOT_GLYPHS = [
    ('S', 90, 0),   # slot 0 — Spotify/Winamp
    ('C', 10, 0),   # slot 1 — Clock
    ('W', 110, 0),  # slot 2 — Weather
    ('$', 145, 6),  # slot 3 — Crypto
    ('M', 60, 0),   # slot 4 — Matrix rain
    ('G', 30, 0),   # slot 5 — Game of Life
]

# Aesthetic palette options cycled by keyboard.
_BG_PALETTE = [
    0x2104,  # very dark grey (default)
    0x0000,  # black
    0x39E7,  # dark slate
    0x18C3,  # dark navy
    0x4208,  # mid grey
]
_INDICATOR_COLORS = [
    0x07E0,  # green (default, Spotify)
    0xFFE0,  # yellow
    0x001F,  # blue
    0xF800,  # red
    0xFFFF,  # white
]
_SEP_COLORS = [
    0x4208,  # mid grey (default)
    0x18C3,  # dark navy
    0x0000,  # black (invisible on dark bg)
]

# ── helpers ───────────────────────────────────────────────────────────────────

def _rgb565_to_rgb(v: int) -> tuple[int, int, int]:
    r = ((v >> 11) & 0x1F) << 3
    g = ((v >> 5)  & 0x3F) << 2
    b = (v & 0x1F)          << 3
    return r, g, b


def _open_wsz_text_bmp(wsz: pathlib.Path) -> Image.Image:
    """Extract TEXT.BMP from a .wsz file using bake_skin's BI_RLE8-aware loader."""
    z, prefix = open_skin(wsz)
    return load_bmp(z, prefix, "TEXT.BMP").convert("RGB")


def _load_skin_preview(wsz: pathlib.Path) -> Image.Image | None:
    """Return gen/skin_preview.png if it exists (relative to wsz location)."""
    gen_dir = wsz.parent.parent / "gen"
    path = gen_dir / "skin_preview.png"
    if path.exists():
        return Image.open(path).convert("RGB")
    return None


def _render_taskbar(font_bmp: Image.Image, params: dict) -> Image.Image:
    """Render the 45×240 taskbar strip as a PIL RGB image."""
    strip = Image.new("RGB", (TASKBAR_W, SCREEN_H), _rgb565_to_rgb(params["bg"]))
    draw  = ImageDraw.Draw(strip)

    icon_pad_x = (TASKBAR_W   - TASKBAR_ICON_W) // 2
    icon_pad_y = (TASKBAR_SLOT_H - TASKBAR_ICON_H) // 2
    glyph_off_x = (TASKBAR_ICON_W - GLYPH_W) // 2   # = 9
    glyph_off_y = (TASKBAR_ICON_H - GLYPH_H) // 2   # = 9

    for slot, (char, gu, gv) in enumerate(_SLOT_GLYPHS):
        slot_y = slot * TASKBAR_SLOT_H

        # Active-slot indicator.
        if slot == params["active_slot"]:
            style = params["style"]
            col   = _rgb565_to_rgb(params["indicator_color"])
            if style == 'A':
                # 3-pixel left bar
                draw.rectangle([0, slot_y, 2, slot_y + TASKBAR_SLOT_H - 1], fill=col)
            elif style == 'B':
                # Full cell highlight
                draw.rectangle([0, slot_y, TASKBAR_W - 1, slot_y + TASKBAR_SLOT_H - 1],
                                fill=col)
            elif style == 'C':
                # Centre dot (6×6)
                cx = TASKBAR_W // 2
                cy = slot_y + TASKBAR_SLOT_H // 2
                draw.rectangle([cx - 3, cy - 3, cx + 2, cy + 2], fill=col)

        # Glyph — crop from TEXT.BMP and paste.
        glyph = font_bmp.crop((gu, gv, gu + GLYPH_W, gv + GLYPH_H)).convert("RGB")
        cell_x = icon_pad_x + glyph_off_x
        cell_y = slot_y + icon_pad_y + glyph_off_y
        strip.paste(glyph, (cell_x, cell_y))

        # Separator line below slot (except last).
        if params["sep_enabled"] and slot < TASKBAR_SLOT_COUNT - 1:
            sep_y = slot_y + TASKBAR_SLOT_H - 1
            sep_col = _rgb565_to_rgb(params["sep_color"])
            draw.line([(0, sep_y), (TASKBAR_W - 1, sep_y)], fill=sep_col)

    return strip


def _composite(skin_preview: Image.Image | None,
               taskbar_strip: Image.Image) -> Image.Image:
    """Compose full 320×240 canvas: skin on left, taskbar on right."""
    canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (20, 20, 20))
    if skin_preview is not None:
        canvas.paste(skin_preview, (0, 0))
    canvas.paste(taskbar_strip, (TASKBAR_X, 0))
    return canvas


def _export(params: dict, out_dir: pathlib.Path) -> pathlib.Path:
    """Write gen/shell_layout.h from current params. Returns path."""
    path = out_dir / "shell_layout.h"
    bg    = params["bg"]
    style = params["style"]
    ic    = params["indicator_color"]
    sep   = 1 if params["sep_enabled"] else 0
    sc    = params["sep_color"]
    path.write_text(
        "// Generated by tools/preview_layout.py — do not edit by hand.\n"
        "// Re-generate: cd Spotify-Diy-Thing/tools && "
        "python3 preview_layout.py --wsz ../skins/base-2.91.wsz\n"
        "#pragma once\n"
        "\n"
        "// Taskbar strip geometry (screen coordinates, landscape rotation 1)\n"
        f"#define TASKBAR_X          {TASKBAR_X:4d}   // left edge of taskbar strip\n"
        f"#define TASKBAR_W          {TASKBAR_W:4d}   // width of taskbar strip\n"
        f"#define TASKBAR_SLOT_COUNT {TASKBAR_SLOT_COUNT:4d}   // number of app slots (== AppId::COUNT)\n"
        f"#define TASKBAR_SLOT_H     {TASKBAR_SLOT_H:4d}   // height of each icon slot (SLOT_COUNT × SLOT_H == 240)\n"
        f"#define TASKBAR_ICON_W     {TASKBAR_ICON_W:4d}   // icon glyph width (centred in slot)\n"
        f"#define TASKBAR_ICON_H     {TASKBAR_ICON_H:4d}   // icon glyph height\n"
        "\n"
        "// Aesthetics (resolved in interactive preview pass)\n"
        f"#define TASKBAR_BG_RGB565    0x{bg:04X}   // background fill colour\n"
        f"#define TASKBAR_ACTIVE_STYLE '{style}'      // A=3px left bar, B=full cell, C=dot\n"
        f"#define TASKBAR_ACTIVE_COLOR 0x{ic:04X}   // active indicator colour (RGB565)\n"
        f"#define TASKBAR_SEP_ENABLED  {sep}        // 1=draw separator lines, 0=borderless\n"
        f"#define TASKBAR_SEP_COLOR    0x{sc:04X}   // separator line colour (RGB565)\n",
        encoding="utf-8",
    )
    return path


def _print_args(params: dict) -> None:
    """Print bake_skin.py CLI args for the current configuration."""
    print(
        f"  bake_skin.py args: --taskbar-bg 0x{params['bg']:04X}"
        f" --taskbar-style {params['style']}"
        f" --taskbar-indicator 0x{params['indicator_color']:04X}"
        f" --taskbar-sep {'1' if params['sep_enabled'] else '0'}"
        f" --taskbar-sep-color 0x{params['sep_color']:04X}"
    )


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wsz", required=True, type=pathlib.Path,
                    help="Path to .wsz skin file")
    ap.add_argument("--scale", type=int, default=2, choices=[1, 2, 3, 4],
                    help="Initial display scale (default 2 = 640×480)")
    ap.add_argument("--export", action="store_true",
                    help="Non-interactive: export shell_layout.h with defaults and exit")
    args = ap.parse_args()

    wsz = args.wsz.resolve()
    if not wsz.exists():
        sys.exit(f"WSZ not found: {wsz}")

    gen_dir = wsz.parent.parent / "gen"

    font_bmp     = _open_wsz_text_bmp(wsz)
    skin_preview = _load_skin_preview(wsz)

    params = {
        "bg":             _BG_PALETTE[0],
        "style":          'A',
        "indicator_color": _INDICATOR_COLORS[0],
        "sep_enabled":    True,
        "sep_color":      _SEP_COLORS[0],
        "active_slot":    0,
        "scale":          args.scale,
        # palette indices for cycling
        "_bg_idx":        0,
        "_ic_idx":        0,
        "_sc_idx":        0,
    }

    if args.export:
        path = _export(params, gen_dir)
        print(f"Exported: {path}")
        return

    try:
        import pygame
    except ImportError:
        sys.exit("pip install pygame  (required for interactive mode)")

    pygame.init()
    pygame.display.set_caption("M-MULTIAPP Shell Layout Preview  —  e=export  q=quit")

    scale  = params["scale"]
    screen = pygame.display.set_mode((SCREEN_W * scale, SCREEN_H * scale))
    clock  = pygame.time.Clock()

    def redraw():
        strip  = _render_taskbar(font_bmp, params)
        canvas = _composite(skin_preview, strip)
        # Nearest-neighbour scale
        scaled = canvas.resize((SCREEN_W * params["scale"],
                                 SCREEN_H * params["scale"]),
                                Image.NEAREST)
        surf = pygame.image.fromstring(scaled.tobytes(), scaled.size, "RGB")
        screen.blit(surf, (0, 0))
        pygame.display.flip()

    def resize_window():
        nonlocal screen
        s = params["scale"]
        screen = pygame.display.set_mode((SCREEN_W * s, SCREEN_H * s))

    redraw()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                k = event.key
                if k == pygame.K_q:
                    running = False
                elif k == pygame.K_b:
                    params["_bg_idx"] = (params["_bg_idx"] + 1) % len(_BG_PALETTE)
                    params["bg"] = _BG_PALETTE[params["_bg_idx"]]
                    print(f"  bg → 0x{params['bg']:04X}")
                elif k == pygame.K_i:
                    styles = ('A', 'B', 'C')
                    params["style"] = styles[(styles.index(params["style"]) + 1) % 3]
                    print(f"  indicator style → {params['style']}")
                elif k == pygame.K_s:
                    params["sep_enabled"] = not params["sep_enabled"]
                    print(f"  separators → {'on' if params['sep_enabled'] else 'off'}")
                elif k == pygame.K_c:
                    params["_ic_idx"] = (params["_ic_idx"] + 1) % len(_INDICATOR_COLORS)
                    params["indicator_color"] = _INDICATOR_COLORS[params["_ic_idx"]]
                    print(f"  indicator colour → 0x{params['indicator_color']:04X}")
                elif k == pygame.K_LEFTBRACKET:
                    params["active_slot"] = (params["active_slot"] - 1) % TASKBAR_SLOT_COUNT
                    print(f"  active slot → {params['active_slot']}")
                elif k == pygame.K_RIGHTBRACKET:
                    params["active_slot"] = (params["active_slot"] + 1) % TASKBAR_SLOT_COUNT
                    print(f"  active slot → {params['active_slot']}")
                elif k == pygame.K_PLUS or k == pygame.K_EQUALS:
                    params["scale"] = min(4, params["scale"] + 1)
                    resize_window()
                    print(f"  scale → {params['scale']}")
                elif k == pygame.K_MINUS:
                    params["scale"] = max(1, params["scale"] - 1)
                    resize_window()
                    print(f"  scale → {params['scale']}")
                elif k == pygame.K_e:
                    path = _export(params, gen_dir)
                    print(f"  Exported → {path}")
                elif k == pygame.K_p:
                    _print_args(params)
                redraw()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
