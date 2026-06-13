#!/usr/bin/env python3
"""NOS Teletekst live preview — full 320×240 device canvas with taskbar.

Fetches pages directly from teletekst-data.nos.nl and renders the 25×40
teletext grid at 6×8 px per cell (40×6=240px wide) in the 275px app area,
with the standard 45px taskbar strip on the right.

Usage:
    python3 tools/preview_teletext.py          # start at page 101
    python3 tools/preview_teletext.py 601      # start at sport index

Keyboard controls:
    ←/→        previous / next page
    ↑/↓        previous / next subpage (when page has multiple)
    1 2 3 4    jump to fast-text nav targets (red/green/yellow/cyan)
    + / -      zoom in / out  (1× 2× 3×)
    Q / Esc    quit

Mouse:
    Click bottom nav bar to follow fast-text links."""
import pathlib
import re
import sys
import urllib.request

import pygame

# ── device geometry (mirrors firmware / preview_clock.py) ─────────────────────
SCREEN_W   = 320
SCREEN_H   = 240
TASKBAR_X  = 275
TASKBAR_W  = 45
APP_W      = 275
APP_H      = 240

# ── teletext cell geometry: 6×8 fits 40 cols in 240px ────────────────────────
CHAR_W = 6
CHAR_H = 8
COLS   = 40
ROWS   = 25
GRID_W = COLS * CHAR_W   # 240
GRID_H = ROWS * CHAR_H   # 200
NAV_H  = APP_H - GRID_H  # 40 — bottom touch nav bar

ZOOM_LEVELS = [1, 2, 3]

# ── taskbar (matches preview_clock.py constants) ──────────────────────────────
_SLOT_H       = 40
_SLOT_COUNT   = 6
_ICON_W       = 24
_ICON_H       = 24
_TB_BG        = (32,  32,  32 )
_TB_ACTIVE    = (0,   255, 0  )
_TB_SEP       = (64,  64,  64 )
_ICONS_DIR    = pathlib.Path(__file__).parent.parent / "icons" / "taskbar"

# App registry order from appRegistry.h; teletext is the next new slot.
_APP_NAMES = ["spotify", "clock", "weather", "crypto", "matrix", "life",
              "settings", "stock", "aquarium", "teletext"]
_TELETEXT_IDX   = _APP_NAMES.index("teletext")
# Scroll so teletext sits in the last visible slot (slot 5).
_TB_SCROLL      = _TELETEXT_IDX - (_SLOT_COUNT - 1)   # = 4

# ── teletext color palette ────────────────────────────────────────────────────
TT_COLORS = [
    (0,   0,   0  ),  # 0 black
    (255, 0,   0  ),  # 1 red
    (0,   255, 0  ),  # 2 green
    (255, 255, 0  ),  # 3 yellow
    (0,   0,   255),  # 4 blue
    (255, 0,   255),  # 5 magenta
    (0,   255, 255),  # 6 cyan
    (255, 255, 255),  # 7 white
]

# Unscii-8: 8×8 bitmap font, squeezed to 6×8 per cell.
_UNSCII_CANDIDATES = [
    '/home/weiman/proj/esp/resources/lvgl/scripts/built_in_font/unscii-8.ttf',
    '/home/weiman/proj/esp/ESP32-C6-LCD-1.47-Demo/Arduino/libraries/lvgl/scripts/built_in_font/unscii-8.ttf',
]

# ── data fetching ─────────────────────────────────────────────────────────────

def fetch(page_str):
    url = f'https://teletekst-data.nos.nl/page/{page_str}'
    r = urllib.request.urlopen(url)
    return r.read().decode('iso-8859-1')

def parse(raw):
    meta = {}
    for line in raw.split('\n'):
        if '=' in line and not line.startswith('<'):
            k, v = line.split('=', 1)
            meta.setdefault(k.strip(), []).append(v.strip())
    m = re.search(r'<pre>(.*?)</pre>', raw, re.DOTALL)
    return meta, (m.group(1) if m else '')

def _mosaic_bits(c: int) -> int:
    """Extract 6-bit mosaic pattern from teletext graphics char byte.

    Teletext encodes a 2×3 pixel grid into a printable byte:
      bit0=top-left  bit1=top-right
      bit2=mid-left  bit3=mid-right
      bit4=bot-left  bit6=bot-right  (bit5 is always 1 to stay printable)
    """
    return ((c & 0x01)      |
            ((c & 0x02) << 0) |
            ((c & 0x04) << 0) |
            ((c & 0x08) << 0) |
            ((c & 0x10) << 0) |
            ((c & 0x40) >> 1))   # bit6 → position 5

# Mosaic sub-rects within a CHAR_W×CHAR_H cell (6×8):
#   2 columns of 3px, 3 rows of heights 3/3/2 px
_MOSAIC_RECTS = [
    (0, 0, 3, 3),   # top-left
    (3, 0, 3, 3),   # top-right
    (0, 3, 3, 3),   # mid-left
    (3, 3, 3, 3),   # mid-right
    (0, 6, 3, 2),   # bot-left
    (3, 6, 3, 2),   # bot-right
]

def build_cell_grid(content):
    """Return 25×40 grid of (fg, bg, payload, is_mosaic).

    payload: str char when is_mosaic=False, int 6-bit pattern when True.
    Mode (text vs graphics) resets to text at the start of each row.
    """
    grid = []
    for ri in range(ROWS):
        row = content[ri*COLS:(ri+1)*COLS]
        fg, bg = 7, 0
        gfx_mode = False
        cells = []
        for ch in row:
            c = ord(ch)
            if 0x01 <= c <= 0x07:                  # Alpha color → text mode
                fg = c; gfx_mode = False
                cells.append((fg, bg, None, False))
            elif c == 0x10:                         # Mosaic Black → gfx mode
                fg = 0; gfx_mode = True
                cells.append((fg, bg, None, False))
            elif 0x11 <= c <= 0x17:                # Mosaic color → gfx mode
                fg = c & 0x07; gfx_mode = True
                cells.append((fg, bg, None, False))
            elif c == 0x1C:                        # Black background
                bg = 0
                cells.append((fg, bg, None, False))
            elif c == 0x1D:                        # New background
                bg = fg
                cells.append((fg, bg, None, False))
            elif c < 0x20:                         # Other control → space
                cells.append((fg, bg, None, False))
            elif gfx_mode:                         # Graphics character
                cells.append((fg, bg, _mosaic_bits(c), True))
            else:                                  # Text character
                cells.append((fg, bg, chr(c), False))
        grid.append(cells)
    return grid

def extract_nav(meta, content):
    subpages = meta.get('pn', [])
    prev = next_ = ns = ps = None
    for sp in subpages:
        if sp.startswith('p_'):  prev = sp[2:]
        if sp.startswith('n_'):  next_ = sp[2:]
        if sp.startswith('ns'): ns   = sp[2:]
        if sp.startswith('ps'): ps   = sp[2:]

    row24 = content[24*COLS:25*COLS]
    fg = 7
    segments = []
    cur = ''; cur_fg = 7
    for ch in row24:
        c = ord(ch)
        if 0x01 <= c <= 0x07:
            if cur.strip(): segments.append((cur_fg, cur))
            fg = c; cur_fg = fg; cur = ''
        elif c < 0x20: cur += ' '
        else:          cur += ch
    if cur.strip(): segments.append((cur_fg, cur))

    COLOR_ORDER = [1, 2, 3, 6]
    btns = []
    for i, f in enumerate(meta.get('ftl', [])[:4]):
        lbl = ''
        for seg_fg, seg_txt in segments:
            if seg_fg == COLOR_ORDER[i]:
                lbl = seg_txt.strip(); break
        btns.append((COLOR_ORDER[i], lbl, f.split('-')[0]))

    return prev, next_, ns, ps, btns

# ── rendering ─────────────────────────────────────────────────────────────────

_icon_cache: dict[tuple, pygame.Surface | None] = {}

def _load_icon(name: str, active: bool) -> pygame.Surface | None:
    key = (name, active)
    if key not in _icon_cache:
        suffix = "_active" if active else ""
        path = _ICONS_DIR / f"{name}{suffix}.png"
        if path.exists():
            ico = pygame.image.load(str(path)).convert_alpha()
            _icon_cache[key] = pygame.transform.scale(ico, (_ICON_W, _ICON_H))
        else:
            _icon_cache[key] = None
    return _icon_cache[key]

def draw_taskbar(canvas: pygame.Surface) -> None:
    pygame.draw.rect(canvas, _TB_BG, (TASKBAR_X, 0, TASKBAR_W, SCREEN_H))
    icon_x = TASKBAR_X + (TASKBAR_W - _ICON_W) // 2
    for i in range(_SLOT_COUNT):
        app_idx  = (_TB_SCROLL + i) % len(_APP_NAMES)
        y0       = i * _SLOT_H
        is_active = (app_idx == _TELETEXT_IDX)

        if i < _SLOT_COUNT - 1:
            pygame.draw.line(canvas, _TB_SEP,
                             (TASKBAR_X, y0 + _SLOT_H), (SCREEN_W - 1, y0 + _SLOT_H))

        ico = _load_icon(_APP_NAMES[app_idx], is_active)
        if ico:
            canvas.blit(ico, (icon_x, y0 + (_SLOT_H - _ICON_H) // 2))

        if is_active:
            pygame.draw.rect(canvas, _TB_ACTIVE, (TASKBAR_X, y0, 3, _SLOT_H))

def draw_page(surf: pygame.Surface, font: pygame.font.Font,
              grid: list, nav_btns: list, zoom: int) -> None:
    """Render at native 320×240, nearest-neighbor scale once for zoom."""
    canvas = pygame.Surface((SCREEN_W, SCREEN_H))
    canvas.fill(TT_COLORS[0])

    # Teletext grid (left 275px)
    for ri, row in enumerate(grid):
        for ci, (fg, bg, payload, is_mosaic) in enumerate(row):
            x, y = ci * CHAR_W, ri * CHAR_H
            pygame.draw.rect(canvas, TT_COLORS[bg], (x, y, CHAR_W, CHAR_H))
            if is_mosaic:
                for bit_idx, (rx, ry, rw, rh) in enumerate(_MOSAIC_RECTS):
                    if payload & (1 << bit_idx):
                        pygame.draw.rect(canvas, TT_COLORS[fg],
                                         (x + rx, y + ry, rw, rh))
            elif payload:
                glyph = font.render(payload, False, TT_COLORS[fg], TT_COLORS[bg])
                glyph = pygame.transform.scale(glyph, (CHAR_W, CHAR_H))
                canvas.blit(glyph, (x, y))

    # Bottom nav bar (4 coloured buttons across APP_W)
    nav_bw = APP_W // 4
    for i, (col, lbl, _) in enumerate(nav_btns):
        nx = i * nav_bw
        pygame.draw.rect(canvas, TT_COLORS[col], (nx, GRID_H, nav_bw, NAV_H))
        if lbl:
            txt = font.render(lbl[:10], False, TT_COLORS[0], TT_COLORS[col])
            txt = pygame.transform.scale(txt, (CHAR_W * len(lbl[:10]), CHAR_H))
            tw  = txt.get_width()
            canvas.blit(txt, (nx + (nav_bw - tw) // 2, GRID_H + (NAV_H - CHAR_H) // 2))

    draw_taskbar(canvas)

    if zoom == 1:
        surf.blit(canvas, (0, 0))
    else:
        surf.blit(pygame.transform.scale(canvas, (SCREEN_W * zoom, SCREEN_H * zoom)), (0, 0))

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    page     = sys.argv[1] if len(sys.argv) > 1 else '101'
    zoom_idx = 1  # default 2×

    pygame.init()

    font = None
    for candidate in _UNSCII_CANDIDATES:
        try:
            font = pygame.font.Font(candidate, 8)
            break
        except FileNotFoundError:
            pass
    if font is None:
        font = pygame.font.SysFont('monospace', 8)

    def make_screen(zoom):
        return pygame.display.set_mode((SCREEN_W * zoom, SCREEN_H * zoom))

    screen = make_screen(ZOOM_LEVELS[zoom_idx])

    def load(pg):
        raw = fetch(pg)
        meta, content = parse(raw)
        return build_cell_grid(content), *extract_nav(meta, content)

    current_page = page
    grid, prev, next_, ns, ps, btns = load(current_page)
    clock = pygame.time.Clock()
    running = True

    def nav_to(pg):
        nonlocal current_page, grid, prev, next_, ns, ps, btns
        current_page = pg
        grid, prev, next_, ns, ps, btns = load(current_page)

    while running:
        zoom = ZOOM_LEVELS[zoom_idx]
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif ev.key == pygame.K_RIGHT and next_:   nav_to(next_)
                elif ev.key == pygame.K_LEFT  and prev:    nav_to(prev)
                elif ev.key == pygame.K_UP    and ns:      nav_to(ns)
                elif ev.key == pygame.K_DOWN  and ps:      nav_to(ps)
                elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    zoom_idx = min(zoom_idx + 1, len(ZOOM_LEVELS) - 1)
                    screen = make_screen(ZOOM_LEVELS[zoom_idx])
                elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    zoom_idx = max(zoom_idx - 1, 0)
                    screen = make_screen(ZOOM_LEVELS[zoom_idx])
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    idx = ev.key - pygame.K_1
                    if idx < len(btns): nav_to(btns[idx][2])
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                if my >= GRID_H * zoom:
                    nav_bw = (APP_W * zoom) // 4
                    btn_idx = mx // nav_bw
                    if btn_idx < len(btns): nav_to(btns[btn_idx][2])

        draw_page(screen, font, grid, btns, zoom)
        pygame.display.set_caption(
            f'NOS Teletekst  p:{current_page}  zoom:{zoom}×'
            f'  ←→ page  ↑↓ subpg  1-4 nav  +/- zoom'
        )
        pygame.display.flip()
        clock.tick(10)

    pygame.quit()

if __name__ == '__main__':
    main()
