#!/usr/bin/env python3
"""Preview Web Radio canvas — composites onto the actual Winamp skin.

ALL coordinates come from gen/skin_layout.h and app/src/winamp/vuMeter.h.
originX = originY = 0 for this device (no centering offset).

Zone map:
  TITLE    x=111 y=27 w=154 h=6    station name marquee (Winamp green LED zone)
  ICY_LINE x=111 y=36 w=154 h=6    ICY StreamTitle (gap between title y=33 and VU y=43)
  VU       x=24  y=43 w=76  h=16   spectrum bars (two horizontal bars, L top / R bottom)
  POSBAR   x=16  y=72 w=248 h=10   buffer bar replacing seek bar
  BUTTONS  y=88  PREV=16 PLAY=39 PAUSE=62 STOP=85 NEXT=108 (skin drawn; no remap needed)
  COUNTRY  x=241 y=10 w=32  h=13   badge over the bitrate-legend area top-right
  PLEDIT title bar  y=116..135 (h=20) station count / stream status
  PLEDIT rows       y=136..200 (5 rows × 13px), content x=12 w=244
  PLEDIT bottom bar y=201..238 (h=38)

States (keyboard: S / C / P / E — Q to quit):
  stopped     station list visible, bar empty, VU flat
  connecting  title "Connecting…", bar 0 %, VU flat
  playing     station name + ICY title, bar 65 %, VU active (sine)
  error       title "Error: conn lost", bar 0 %, VU flat

Headless: set DISPLAY="" or pass --headless -> writes preview_webradio_{state}.png per state.
"""
from __future__ import annotations

import argparse
import math
import os
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from preview_common import (
    APP_ORDER,
    draw_taskbar_pil,
    SCREEN_W,
    SCREEN_H,
)
from bake_skin import (
    open_skin,
    load_bmp,
    composite_text,
    composite_with_transparency,
    build_pledit_atlas,
    POSBAR_LAYOUT,
    GLYPH_W,
    PLEDIT_SIDE_LEFT_W,
    PLEDIT_SIDE_RIGHT_W,
    PLEDIT_SIDE_H_SRC,
    PLEDIT_DISPLAY_W,
    PLEDIT_THUMB_W,
    PLEDIT_THUMB_H,
    PLEDIT_THUMB_X0,
    PLEDIT_THUMB_Y0,
    PLEDIT_TRANSPARENT_KEY,
    PLEDIT_TRANSPARENT_TOL,
)

# ── zone constants (mirrors skin_layout.h / vuMeter.h) ────────────────────────
TITLE_X, TITLE_Y, TITLE_W, TITLE_H = 111, 27, 154, 6
VU_X,    VU_Y,    VU_W,    VU_H    = 24,  43, 76,  16   # RECT_X / LEFT_Y / RECT_W / VIS_H
POSBAR_X, POSBAR_Y, POSBAR_W, POSBAR_H = 16, 72, 248, 10

PLEDIT_Y        = 116
PLEDIT_H        = 124
PLEDIT_TITLE_H  = 20
PLEDIT_ROWS_Y   = 136
PLEDIT_ROW_H    = 13
PLEDIT_ROW_COUNT= 5
PLEDIT_CONTENT_X= 12
PLEDIT_CONTENT_W= 244
PLEDIT_BOTTOM_Y = 201
PLEDIT_BOTTOM_H = 38

# PLEDIT colours (from PLEDIT.TXT via skin_layout.h)
PLEDIT_FG_NORMAL   = (0x00, 0xFF, 0x00)
PLEDIT_FG_CURRENT  = (0xFF, 0xFF, 0xFF)
PLEDIT_BG_NORMAL   = (0x00, 0x00, 0x00)
PLEDIT_BG_SELECTED = (0x00, 0x00, 0xC6)

VU_GREEN_HI = (0x00, 0xFF, 0x00)
VU_GREEN_LO = (0x00, 0x66, 0x00)

STATIONS = [
    "Radio 1 NL", "Radio 2", "NPO 3FM", "NPO Radio 4",
    "Sky Radio", "Radio 538", "Q-music", "BNR Nieuws",
    "Veronica", "100% NL",
]
ICY_TITLE = "Billie Eilish - BIRDS OF A FEATHER"
BITRATE   = "128 kbps"

try:
    _FONT = ImageFont.load_default()
except Exception:
    _FONT = None


def _text(draw, xy, text, colour, font=None):
    draw.text(xy, text, fill=colour, font=font or _FONT)


# Skin sprite cache — populated by _load_skin_assets() before first render.
_text_bmp      = None
_posbar_bmp    = None
_pledit_atlas  = None
_left_tile     = None
_right_tile    = None
_thumb_sprite  = None


def _load_skin_assets(wsz_path: pathlib.Path) -> None:
    global _text_bmp, _posbar_bmp, _pledit_atlas, _left_tile, _right_tile, _thumb_sprite
    wsz_path = pathlib.Path(wsz_path)
    if not wsz_path.exists():
        print(f"error: wsz not found: {wsz_path}", file=sys.stderr)
        sys.exit(1)
    try:
        z, prefix      = open_skin(wsz_path)
        _text_bmp      = load_bmp(z, prefix, "TEXT.BMP")
        _posbar_bmp    = load_bmp(z, prefix, "POSBAR.BMP")
        pledit_raw     = load_bmp(z, prefix, "PLEDIT.BMP")
        _pledit_atlas  = build_pledit_atlas(pledit_raw)
        pledit_src     = pledit_raw.convert("RGB")
        _left_tile     = pledit_src.crop((0,  42, 0  + PLEDIT_SIDE_LEFT_W,  42 + PLEDIT_SIDE_H_SRC))
        _right_tile    = pledit_src.crop((32, 42, 32 + PLEDIT_SIDE_RIGHT_W, 42 + PLEDIT_SIDE_H_SRC))
        _thumb_sprite  = pledit_src.crop((PLEDIT_THUMB_X0, PLEDIT_THUMB_Y0,
                                           PLEDIT_THUMB_X0 + PLEDIT_THUMB_W,
                                           PLEDIT_THUMB_Y0 + PLEDIT_THUMB_H))
    except Exception as e:
        print(f"error: failed to load skin {wsz_path}: {e}", file=sys.stderr)
        sys.exit(1)


def _draw_vu(draw, l_level: float, r_level: float):
    """Two horizontal bars at the VU zone — mirrors vuMeter.h left/right layout."""
    half_h = VU_H // 2  # 8 px per channel
    for ch, lvl in enumerate((l_level, r_level)):
        bar_w = max(0, min(VU_W, int(lvl * VU_W)))
        row_y = VU_Y + ch * half_h
        # Clear row to black (firmware restores from MAIN_BG — preview uses black)
        draw.rectangle([VU_X, row_y, VU_X + VU_W - 1, row_y + half_h - 1],
                       fill=(0, 0, 0))
        if bar_w > 0:
            for px in range(bar_w):
                frac = px / max(1, VU_W - 1)
                g = int(VU_GREEN_LO[1] + (VU_GREEN_HI[1] - VU_GREEN_LO[1]) * frac)
                draw.line([(VU_X + px, row_y), (VU_X + px, row_y + half_h - 1)],
                          fill=(0, g, 0))


def _draw_buffer_bar(img: Image.Image, fill_pct: float):
    """Buffer-health bar (TASK-253) — a horizontal gradient stretched to the buffer
    fill width, tinted amber(low)→green(high) by fill level so the colour signals
    stream health, not just amount. Mirrors firmware _drawPosbar() exactly (same
    endpoints + lerp); groove BG painted first by repaintChrome equivalent."""
    bg_x, bg_y, bg_w, bg_h = POSBAR_LAYOUT["POSBAR_BG"]
    img.paste(_posbar_bmp.crop((bg_x, bg_y, bg_x + bg_w, bg_y + bg_h)), (POSBAR_X, POSBAR_Y))
    if fill_pct <= 0:
        return
    pct = max(0.0, min(1.0, fill_pct))
    fillw = int(pct * POSBAR_W)

    def lerp(a, b, t):
        return int(a + (b - a) * t)

    # Health tip colour: amber (low buffer) → green (healthy), by fill level.
    tr, tg, tb = lerp(0xF0, 0x30, pct), lerp(0x90, 0xE0, pct), lerp(0x10, 0x20, pct)
    px = img.load()
    for x in range(fillw):
        t = x / max(1, fillw - 1)               # within-bar: dark tip → full tip
        r = lerp(int(tr * 0.4), tr, t)
        g = lerp(int(tg * 0.4), tg, t)
        b = lerp(int(tb * 0.4), tb, t)
        for y in range(POSBAR_H):
            px[POSBAR_X + x, POSBAR_Y + y] = (r, g, b)


def _draw_title(img: Image.Image, text: str):
    """Single scrolling LED title row — mirrors firmware drawTitleText(titleScrollOffset=0)."""
    draw = ImageDraw.Draw(img)
    draw.rectangle([TITLE_X, TITLE_Y,
                    TITLE_X + TITLE_W - 1, TITLE_Y + TITLE_H - 1],
                   fill=(0x0A, 0x24, 0x0A))
    max_chars = TITLE_W // (GLYPH_W + 1)
    if text:
        composite_text(img, _text_bmp, text.upper()[:max_chars], TITLE_X + 1, TITLE_Y)



def _draw_station_list(img: Image.Image, active_idx: int, state: str):
    """PLEDIT chrome + rows + scroll indicator."""
    draw = ImageDraw.Draw(img)
    # Title bar from skin atlas — no text overlay (firmware draws chrome only)
    img.paste(_pledit_atlas.crop((0, 0, PLEDIT_DISPLAY_W, PLEDIT_TITLE_H)), (0, PLEDIT_Y))

    # Row area (bounded to 275 px app canvas, not SCREEN_W)
    draw.rectangle([0, PLEDIT_ROWS_Y,
                    PLEDIT_DISPLAY_W - 1, PLEDIT_ROWS_Y + PLEDIT_ROW_COUNT * PLEDIT_ROW_H - 1],
                   fill=PLEDIT_BG_NORMAL)
    for i in range(PLEDIT_ROW_COUNT):
        ry = PLEDIT_ROWS_Y + i * PLEDIT_ROW_H
        name = STATIONS[i] if i < len(STATIONS) else ""
        is_active = (i == active_idx)
        bg = PLEDIT_BG_SELECTED if is_active else PLEDIT_BG_NORMAL
        fg = PLEDIT_FG_CURRENT  if is_active else PLEDIT_FG_NORMAL
        draw.rectangle([PLEDIT_CONTENT_X, ry,
                        PLEDIT_CONTENT_X + PLEDIT_CONTENT_W - 1, ry + PLEDIT_ROW_H - 1],
                       fill=bg)
        _text(draw, (PLEDIT_CONTENT_X + 3, ry + 2), name, fg)

    # Side tiles tiled vertically over rows area (right tile includes scrollbar track)
    rows_h = PLEDIT_ROW_COUNT * PLEDIT_ROW_H
    for y_off in range(0, rows_h, PLEDIT_SIDE_H_SRC):
        clip_h = min(PLEDIT_SIDE_H_SRC, rows_h - y_off)
        ry = PLEDIT_ROWS_Y + y_off
        img.paste(_left_tile.crop((0, 0, PLEDIT_SIDE_LEFT_W, clip_h)), (0, ry))
        img.paste(_right_tile.crop((0, 0, PLEDIT_SIDE_RIGHT_W, clip_h)),
                  (PLEDIT_DISPLAY_W - PLEDIT_SIDE_RIGHT_W, ry))

    # Scrollbar thumb — mirrors firmware: SKIN_PLEDIT_THUMB at scroll position with transparent key
    scroll_frac = 0.0  # preview always at top; firmware: scrollOffset / max(1, count - ROW_COUNT)
    travel_px   = rows_h - PLEDIT_THUMB_H
    thumb_x_inset = (PLEDIT_SIDE_RIGHT_W - PLEDIT_THUMB_W) // 2
    thumb_x = PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + thumb_x_inset
    thumb_y = PLEDIT_ROWS_Y + int(scroll_frac * travel_px)
    composite_with_transparency(img, _thumb_sprite, thumb_x, thumb_y,
                                PLEDIT_TRANSPARENT_KEY, PLEDIT_TRANSPARENT_TOL)

    # Bottom bar from skin atlas
    img.paste(_pledit_atlas.crop((0, PLEDIT_TITLE_H, PLEDIT_DISPLAY_W,
                                   PLEDIT_TITLE_H + PLEDIT_BOTTOM_H)), (0, PLEDIT_BOTTOM_Y))
    if state == "playing":
        _text(draw, (PLEDIT_CONTENT_X + 2, PLEDIT_BOTTOM_Y + 6),
              BITRATE, (0x88, 0x88, 0x88))


# ── per-state render ──────────────────────────────────────────────────────────

def render(state: str, skin_path: str, frame: int = 0) -> Image.Image:
    img = Image.open(skin_path).convert("RGB")
    if img.size != (SCREEN_W, SCREEN_H):
        raise ValueError(f"Skin must be {SCREEN_W}x{SCREEN_H}, got {img.size}")

    _app_order = list(APP_ORDER) + ["WebRadio"]
    draw_taskbar_pil(img, "WebRadio", app_order=_app_order)

    draw = ImageDraw.Draw(img)

    if state == "stopped":
        _draw_title(img, STATIONS[0])
        _draw_buffer_bar(img, 0.0)
        _draw_vu(draw, 0.0, 0.0)
        _draw_station_list(img, 0, state)

    elif state == "connecting":
        _draw_title(img, "Connecting...")
        _draw_buffer_bar(img, 0.0)
        _draw_vu(draw, 0.0, 0.0)
        _draw_station_list(img, 0, state)

    elif state == "playing":
        t = frame / 30.0
        l_lvl = max(0.0, 0.55 + 0.35 * math.sin(t * 2.7))
        r_lvl = max(0.0, 0.50 + 0.35 * math.sin(t * 1.9 + 1.1))
        # Firmware (TASK-252): LED-font title = station name (marquee). The ICY
        # StreamTitle display is unsettled (its y=36 line collides with the baked
        # kbps/kHz badge) — see TASK-254; omitted here pending that decision.
        _draw_title(img, STATIONS[0])
        _draw_buffer_bar(img, 0.65)
        _draw_vu(draw, l_lvl, r_lvl)
        _draw_station_list(img, 0, state)

    elif state == "error":
        _draw_title(img, "Error: conn lost")
        _draw_buffer_bar(img, 0.0)
        _draw_vu(draw, 0.0, 0.0)
        _draw_station_list(img, -1, state)

    return img


# ── headless export ───────────────────────────────────────────────────────────

STATES = ["stopped", "connecting", "playing", "error"]


def run_headless(skin_path: str):
    # Anchor output to this script's dir, not the CWD — running from the repo
    # root otherwise sprays orphan preview_webradio_*.png there (cleaned 2026-06-21).
    out_dir = os.path.dirname(os.path.abspath(__file__))
    for state in STATES:
        img = render(state, skin_path, frame=15)
        out = os.path.join(out_dir, f"preview_webradio_{state}.png")
        img.save(out)
        print(f"Wrote {out}")
    print(f"Headless render complete → {out_dir}")


# ── interactive pygame window ─────────────────────────────────────────────────

def run_interactive(skin_path: str):
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

    state_idx = 2  # start on "playing"
    frame = 0
    clock = pygame.time.Clock()

    key_map = {
        pygame.K_s: 0,
        pygame.K_c: 1,
        pygame.K_p: 2,
        pygame.K_e: 3,
    }

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    pygame.quit(); return
                if event.key in key_map:
                    state_idx = key_map[event.key]
                    frame = 0

        state = STATES[state_idx]
        img = render(state, skin_path, frame=frame)
        pygame.display.set_caption(
            f"WebRadio preview — {state.upper()}  [S/C/P/E=state  Q=quit]")

        data = img.tobytes()
        surf = pygame.image.fromstring(data, img.size, "RGB")
        screen.blit(surf, (0, 0))
        pygame.display.flip()

        if state == "playing":
            frame += 1
        clock.tick(30)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    here = pathlib.Path(__file__).parent
    default_skin = str(here / "../gen/skin_preview.png")
    default_wsz  = here / "../skins/base-2.91.wsz"

    parser = argparse.ArgumentParser(description="WebRadio canvas preview")
    parser.add_argument("--skin", default=default_skin)
    parser.add_argument("--wsz", type=pathlib.Path, default=default_wsz,
                        help="Winamp .wsz skin file (default: app/skins/base-2.91.wsz)")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    skin_path = pathlib.Path(args.skin)
    if not skin_path.exists():
        print(f"error: skin PNG not found: {skin_path}", file=sys.stderr)
        sys.exit(1)

    _load_skin_assets(args.wsz)

    headless = args.headless or not os.environ.get("DISPLAY", "")
    if headless:
        run_headless(args.skin)
    else:
        run_interactive(args.skin)


if __name__ == "__main__":
    main()
