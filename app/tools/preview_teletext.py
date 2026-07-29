#!/usr/bin/env python3
"""Teletext live preview — full 320×240 device canvas with taskbar.

Two interchangeable sources behind one render pipeline (M-CEEFAX DS-6 option
B: one app, pluggable source backend — this tool follows the same shape):

  --source nos     (default) NOS Teletekst, synchronous HTTP GET per page.
  --source ceefax  NMS Ceefax, live WebSocket relay via ceefax_client.py.
                    Requires `pip install websocket-client`. No pn=/ftl=
                    metadata: prev/next fall back to page±1, subpage ▲/▼ stay
                    permanently dimmed. The fastext bar shows real
                    labels/colours parsed from row 24 AND real targets
                    decoded from packet 27 (Hamming 8/4 FLOF links, see
                    ceefax_client.decode_flof_packet()) — a button navigates
                    if the current page happened to carry a link for it,
                    stays inert (no page carries FLOF links, or that colour
                    slot is unset) otherwise. See EXP-005 / M-CEEFAX DS-3.

Fetches pages directly from teletekst-data.nos.nl (NOS) or the live Ceefax
relay, and renders the 25×40 teletext grid at 6×8 px per cell (40×6=240px
wide) in the 275px app area, with the standard 45px taskbar strip on the
right. Rendering code is 100% shared between sources — only fetch/nav differ.

Usage:
    python3 tools/preview_teletext.py                    # NOS, page 101
    python3 tools/preview_teletext.py 601                 # NOS, sport index
    python3 tools/preview_teletext.py --source ceefax     # Ceefax, page 100
    python3 tools/preview_teletext.py --source ceefax 141 # Ceefax, page 141

Keyboard controls:
    ←/→         previous / next page
    ↑/↓         previous / next subpage (when page has multiple)
    1 2 3 4     jump to fast-text nav targets (red/green/yellow/cyan)
    0–9         type digits into the page-number keypad (opens automatically)
    Backspace   go back (history ring, depth 10) / delete digit in keypad
    Esc         dismiss keypad (or quit if keypad not open)
    + / -       zoom in / out  (1× 2× 3×)
    Q           quit

Mouse:
    Click page number (right strip, centre zone)   open numeric keypad
    Click keypad key                               enter digit / backspace
    Click outside keypad                           dismiss keypad
    Click grid row                                 follow inline page-ref link
    Click right strip (other zones)               navigate prev/next/subpage
    Click bottom nav bar                           fast-text links"""
import re
import sys
import urllib.error
import urllib.request

import pygame
from preview_common import (
    SCREEN_W, SCREEN_H, TASKBAR_X, TASKBAR_W, APP_W, APP_H,
    TASKBAR_SLOT_H, TASKBAR_SLOT_COUNT, TASKBAR_ICON_W, TASKBAR_ICON_H,
    TASKBAR_BG, TASKBAR_ACTIVE_COL, TASKBAR_SEP_COL,
    APP_ORDER, load_icon_pygame, draw_taskbar_pygame, PreviewWindow,
)

# ── teletext cell geometry: 6×8 fits 40 cols in 240px ────────────────────────
CHAR_W = 6
CHAR_H = 8
COLS   = 40
ROWS   = 25
GRID_W = COLS * CHAR_W   # 240
GRID_H = ROWS * CHAR_H   # 200
NAV_H  = APP_H - GRID_H  # 40 — bottom fast-text bar

# ── right-strip geometry (between grid and taskbar) ───────────────────────────
# Pixel-exact zone boundaries — will become teletext_layout.h constants.
STRIP_X = GRID_W          # 240
STRIP_W = TASKBAR_X - GRID_W  # 35

STRIP_SUBUP_Y0 =   0;  STRIP_SUBUP_Y1 =  33   # subpage ▲    (34 px)
STRIP_PAGE_Y0  =  34;  STRIP_PAGE_Y1  =  66   # page number   (33 px)
STRIP_BACK_Y0  =  67;  STRIP_BACK_Y1  =  99   # ◄◄ back       (33 px)
STRIP_PREV_Y0  = 100;  STRIP_PREV_Y1  = 132   # prev page ◄   (33 px)
STRIP_NEXT_Y0  = 133;  STRIP_NEXT_Y1  = 165   # next page ►   (33 px)
STRIP_SUBDN_Y0 = 166;  STRIP_SUBDN_Y1 = 199   # subpage ▼    (34 px)

ZOOM_LEVELS = [1, 2, 3]

# ── taskbar ───────────────────────────────────────────────────────────────────
# Teletext not yet in appRegistry.h — append manually until it lands.
_APP_ORDER    = APP_ORDER + ["Teletext"]
_TELETEXT_IDX = _APP_ORDER.index("Teletext")
_TB_SCROLL    = _TELETEXT_IDX - (TASKBAR_SLOT_COUNT - 1)  # scroll so Teletext is last visible

# ── teletext colour palette ───────────────────────────────────────────────────
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

# Strip UI colours
_STRIP_BG      = (28,  28,  28)
_STRIP_ACTIVE  = (220, 220, 220)
_STRIP_DIM     = (70,  70,  70)
_STRIP_BACK    = (0,   200, 200)   # cyan tint when history available
_STRIP_PAGENUM = (160, 160, 160)
_STRIP_SEP     = (50,  50,  50)

# Unscii-8: 8×8 bitmap font
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
            ((c & 0x40) >> 1))

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
            if 0x01 <= c <= 0x07:
                fg = c; gfx_mode = False
                cells.append((fg, bg, None, False))
            elif c == 0x10:
                fg = 0; gfx_mode = True
                cells.append((fg, bg, None, False))
            elif 0x11 <= c <= 0x17:
                fg = c & 0x07; gfx_mode = True
                cells.append((fg, bg, None, False))
            elif c == 0x1C:
                bg = 0
                cells.append((fg, bg, None, False))
            elif c == 0x1D:
                bg = fg
                cells.append((fg, bg, None, False))
            elif c < 0x20:
                cells.append((fg, bg, None, False))
            elif gfx_mode:
                cells.append((fg, bg, _mosaic_bits(c), True))
            else:
                cells.append((fg, bg, chr(c), False))
        grid.append(cells)
    return grid

def extract_nav(meta, content):
    subpages = meta.get('pn', [])
    prev = next_ = ns = ps = None
    for sp in subpages:
        if sp.startswith('p_'):  prev  = sp[2:]
        if sp.startswith('n_'):  next_ = sp[2:]
        if sp.startswith('ns'): ns    = sp[2:]
        if sp.startswith('ps'): ps    = sp[2:]

    row24 = content[24*COLS:25*COLS]
    segments = []
    cur = ''; cur_fg = 7
    for ch in row24:
        c = ord(ch)
        if 0x01 <= c <= 0x07:
            if cur.strip(): segments.append((cur_fg, cur))
            cur_fg = c; cur = ''
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

def ceefax_extract_nav(page_int, content, flof=None):
    """Ceefax equivalent of extract_nav() — no pn=/ftl= metadata exists (see
    EXP-005 finding 6), so:
      - prev/next fall back to page±1 (no "skip missing pages" smartness).
      - subpage ▲/▼ stay unavailable (no subcode navigation surfaced yet).
      - fastext bar: row 24's colour-coded label segments parse the same way
        as NOS (same control-code scheme). Real targets come from `flof`
        (ceefax_client.decode_flof_packet()'s packet-27 decode, keyed by
        link index 0-3); a button with no entry in `flof` stays inert,
        matching real teletext where not every page carries FLOF links.
    """
    prev  = str(page_int - 1) if page_int > 100 else None
    next_ = str(page_int + 1) if page_int < 899 else None
    ns = ps = None
    flof = flof or {}

    row24 = content[24*COLS:25*COLS]
    segments = []
    cur = ''; cur_fg = 7
    for ch in row24:
        c = ord(ch)
        if 0x01 <= c <= 0x07:
            if cur.strip(): segments.append((cur_fg, cur))
            cur_fg = c; cur = ''
        elif c < 0x20: cur += ' '
        else:          cur += ch
    if cur.strip(): segments.append((cur_fg, cur))

    COLOR_ORDER = [1, 2, 3, 6]
    btns = []
    for slot_idx, color in enumerate(COLOR_ORDER):
        lbl = ''
        for seg_fg, seg_txt in segments:
            if seg_fg == color:
                lbl = seg_txt.strip(); break
        target = str(flof[slot_idx]) if slot_idx in flof else None
        btns.append((color, lbl, target))

    return prev, next_, ns, ps, btns

def ceefax_waiting_content(page_int):
    """Synthesize a 1000-char content string with a centred "waiting for
    carousel" message, rendered through the same build_cell_grid() path as
    real content — no special-casing added to the renderer. Page acquisition
    takes 3-20s+ (EXP-005 finding 4); without this the grid just goes blank
    with no on-canvas indication of what's happening, which reads as a hang.
    """
    msg = f"Waiting for page {page_int} to air..."
    row = 12
    buf = [0x20] * (ROWS * COLS)
    col = max(0, (COLS - len(msg)) // 2)
    idx = row * COLS
    buf[idx] = 0x03  # yellow FG control code, same scheme as real content
    for i, ch in enumerate(msg):
        pos = idx + col + i
        if idx <= pos < idx + COLS:
            buf[pos] = ord(ch)
    return ''.join(chr(b) for b in buf)

# ── numeric keypad widget ─────────────────────────────────────────────────────
#
# Remote-control layout, centered over the grid area:
#
#   ┌──────────────────┐
#   │  _ _ _           │  ← digit entry display (underscores = remaining)
#   │  [1] [2] [3]     │
#   │  [4] [5] [6]     │
#   │  [7] [8] [9]     │
#   │      [0] [⌫]     │
#   └──────────────────┘
#
# 3 digits → auto-navigate.  Esc / click outside → dismiss.

class Keypad:
    KEY_W  = 34
    KEY_H  = 28
    GAP    = 4
    PAD    = 8
    ENTRY_H = 22

    # Row layout: None = empty/inert cell
    ROWS = [
        ['1', '2', '3'],
        ['4', '5', '6'],
        ['7', '8', '9'],
        [None, '0', '<'],   # '<' = backspace
    ]

    def __init__(self):
        self.visible = False
        self.digits  = ''
        inner_w = 3 * self.KEY_W + 2 * self.GAP
        inner_h = self.ENTRY_H + self.GAP + 4 * self.KEY_H + 3 * self.GAP
        self.W = inner_w + 2 * self.PAD
        self.H = inner_h + 2 * self.PAD
        # Centre in the 240×200 grid area
        self.x0 = (GRID_W - self.W) // 2
        self.y0 = (GRID_H - self.H) // 2

    def show(self):
        self.visible = True
        self.digits  = ''

    def hide(self):
        self.visible = False
        self.digits  = ''

    def push(self, ch):
        """Feed one character ('0'-'9' or 'backspace'). Returns page str when 3 digits done."""
        if ch == 'backspace':
            self.digits = self.digits[:-1]
            return None
        if ch.isdigit() and len(self.digits) < 3:
            self.digits += ch
            if len(self.digits) == 3:
                pg = self.digits
                self.hide()
                return pg
        return None

    def hit(self, cx, cy):
        """Return key label for canvas coords (within keypad), or None."""
        if not self.visible:
            return None
        rx = cx - self.x0 - self.PAD
        ry = cy - self.y0 - self.PAD - self.ENTRY_H - self.GAP
        if rx < 0 or rx >= 3 * self.KEY_W + 2 * self.GAP:
            return None
        if ry < 0:
            return None
        row = ry // (self.KEY_H + self.GAP)
        col = rx // (self.KEY_W + self.GAP)
        if 0 <= row < 4 and 0 <= col < 3:
            return self.ROWS[row][col]  # may be None for inert cell
        return None

    def contains(self, cx, cy):
        return (self.visible and
                self.x0 <= cx < self.x0 + self.W and
                self.y0 <= cy < self.y0 + self.H)

    def draw(self, canvas, font):
        if not self.visible:
            return
        x0, y0 = self.x0, self.y0

        # Drop shadow
        pygame.draw.rect(canvas, (10, 10, 10), (x0 + 3, y0 + 3, self.W, self.H))
        # Panel
        pygame.draw.rect(canvas, (30, 30, 35), (x0, y0, self.W, self.H))
        pygame.draw.rect(canvas, (110, 110, 140), (x0, y0, self.W, self.H), 1)

        ix = x0 + self.PAD
        iy = y0 + self.PAD

        # Entry display bar
        entry_w = 3 * self.KEY_W + 2 * self.GAP
        pygame.draw.rect(canvas, (15, 15, 20), (ix, iy, entry_w, self.ENTRY_H))
        pygame.draw.rect(canvas, (80, 80, 100), (ix, iy, entry_w, self.ENTRY_H), 1)
        display = self.digits.ljust(3, '_')
        ex = ix + (entry_w - 3 * CHAR_W * 2) // 2  # chars at 2× width for readability
        ey = iy + (self.ENTRY_H - CHAR_H) // 2
        for i, ch in enumerate(display):
            col = (255, 220, 0) if i < len(self.digits) else (70, 70, 90)
            glyph = font.render(ch, False, col)
            glyph = pygame.transform.scale(glyph, (CHAR_W * 2, CHAR_H))
            canvas.blit(glyph, (ex + i * CHAR_W * 2, ey))

        # Keys
        ky = iy + self.ENTRY_H + self.GAP
        for row_keys in self.ROWS:
            kx = ix
            for key in row_keys:
                if key is not None:
                    is_del = (key == '<')
                    bg  = (70, 30, 30) if is_del else (55, 55, 65)
                    bdr = (130, 60, 60) if is_del else (95, 95, 115)
                    pygame.draw.rect(canvas, bg, (kx, ky, self.KEY_W, self.KEY_H))
                    pygame.draw.rect(canvas, bdr, (kx, ky, self.KEY_W, self.KEY_H), 1)
                    label = '<<' if is_del else key
                    gw = CHAR_W * len(label)
                    glyph = font.render(label, False, (210, 210, 220))
                    glyph = pygame.transform.scale(glyph, (gw, CHAR_H))
                    canvas.blit(glyph, (kx + (self.KEY_W - gw) // 2,
                                        ky + (self.KEY_H - CHAR_H) // 2))
                kx += self.KEY_W + self.GAP
            ky += self.KEY_H + self.GAP


def find_row_link(grid, row, tap_col=None):
    """Find an isolated 3-digit NOS page ref (100–899) in a grid row.

    Two NOS layout patterns exist:
      - Right-edge index (101, 601): ref at cols 33-39
      - Two-column index (600, 800): refs at cols 1 and 21

    When tap_col is given, returns the ref whose digits are within 3 cols
    of tap_col — works for any column position without special-casing.
    When tap_col is None (used by scan_links), returns the first ref found
    anywhere in the row (to mark the row as interactive).
    """
    if row >= len(grid):
        return None
    chars = ''
    for ci in range(COLS):
        _, _, payload, is_mosaic = grid[row][ci]
        chars += (payload if (not is_mosaic and payload) else ' ')
    for m in re.finditer(r'(?<!\d)(\d{3})(?!\d)', chars):
        pg = int(m.group(1))
        if not (100 <= pg <= 899):
            continue
        if tap_col is None:
            return m.group(1)                          # scan mode: first match
        ref_start, ref_end = m.start(), m.start() + 2
        if ref_start - 3 <= tap_col <= ref_end + 3:   # tap within ±3 of any digit
            return m.group(1)
    return None

def scan_links(grid):
    """Return set of row indices that contain any inline page link."""
    return {ri for ri in range(ROWS) if find_row_link(grid, ri)}

# ── rendering ─────────────────────────────────────────────────────────────────


def _triangle(canvas, color, cx, cy, size, direction):
    """Draw a filled triangle arrow. direction: 'up','down','left','right'."""
    h = size; w = int(size * 1.2)
    if direction == 'up':
        pts = [(cx - w//2, cy + h//2), (cx + w//2, cy + h//2), (cx, cy - h//2)]
    elif direction == 'down':
        pts = [(cx - w//2, cy - h//2), (cx + w//2, cy - h//2), (cx, cy + h//2)]
    elif direction == 'left':
        pts = [(cx + h//2, cy - w//2), (cx + h//2, cy + w//2), (cx - h//2, cy)]
    else:  # right
        pts = [(cx - h//2, cy - w//2), (cx - h//2, cy + w//2), (cx + h//2, cy)]
    pygame.draw.polygon(canvas, color, pts)

def draw_strip(canvas, font, current_page, prev, next_, ns, ps, history, keypad_open):
    """Render the 35×200 px right-strip navigation panel."""
    cx = STRIP_X + STRIP_W // 2

    # Background
    pygame.draw.rect(canvas, _STRIP_BG, (STRIP_X, 0, STRIP_W, GRID_H))

    # Separator line on left edge
    pygame.draw.line(canvas, _STRIP_SEP, (STRIP_X, 0), (STRIP_X, GRID_H - 1))

    # Zone separators
    for y in (STRIP_PAGE_Y0, STRIP_BACK_Y0, STRIP_PREV_Y0, STRIP_NEXT_Y0, STRIP_SUBDN_Y0):
        pygame.draw.line(canvas, _STRIP_SEP, (STRIP_X + 2, y), (STRIP_X + STRIP_W - 1, y))

    # ── Subpage UP ▲ (y=0..33) ───────────────────────────────────────────────
    mid = (STRIP_SUBUP_Y0 + STRIP_SUBUP_Y1) // 2
    col = _STRIP_ACTIVE if ps else _STRIP_DIM
    _triangle(canvas, col, cx, mid, 8, 'up')

    # ── Page number / keypad trigger (y=34..66) ───────────────────────────────
    mid = (STRIP_PAGE_Y0 + STRIP_PAGE_Y1) // 2
    if keypad_open:
        pygame.draw.rect(canvas, (0, 60, 60),
                         (STRIP_X + 1, STRIP_PAGE_Y0, STRIP_W - 2, STRIP_PAGE_Y1 - STRIP_PAGE_Y0))
    pg_str = str(current_page).zfill(3)
    pg_col = (0, 220, 220) if keypad_open else _STRIP_PAGENUM
    for i, ch in enumerate(pg_str):
        glyph = font.render(ch, False, pg_col)
        glyph = pygame.transform.scale(glyph, (CHAR_W, CHAR_H))
        x_off = STRIP_X + (STRIP_W - CHAR_W * 3) // 2 + i * CHAR_W
        canvas.blit(glyph, (x_off, mid - CHAR_H // 2))

    # ── Back ◄◄ (y=67..99) — double arrow distinguishes from prev ◄ ──────────
    mid = (STRIP_BACK_Y0 + STRIP_BACK_Y1) // 2
    if history:
        pygame.draw.rect(canvas, (0, 30, 30),
                         (STRIP_X + 1, STRIP_BACK_Y0, STRIP_W - 2, STRIP_BACK_Y1 - STRIP_BACK_Y0))
    col = _STRIP_BACK if history else _STRIP_DIM
    _triangle(canvas, col, cx - 4, mid, 6, 'left')
    _triangle(canvas, col, cx + 4, mid, 6, 'left')

    # ── Prev page ◄ (y=100..132) ─────────────────────────────────────────────
    mid = (STRIP_PREV_Y0 + STRIP_PREV_Y1) // 2
    col = _STRIP_ACTIVE if prev else _STRIP_DIM
    _triangle(canvas, col, cx, mid, 8, 'left')

    # ── Next page ► (y=133..165) ─────────────────────────────────────────────
    mid = (STRIP_NEXT_Y0 + STRIP_NEXT_Y1) // 2
    col = _STRIP_ACTIVE if next_ else _STRIP_DIM
    _triangle(canvas, col, cx, mid, 8, 'right')

    # ── Subpage DOWN ▼ (y=166..199) ──────────────────────────────────────────
    mid = (STRIP_SUBDN_Y0 + STRIP_SUBDN_Y1) // 2
    col = _STRIP_ACTIVE if ns else _STRIP_DIM
    _triangle(canvas, col, cx, mid, 8, 'down')

def draw_page(surf, font, grid, nav_btns, current_page,
              prev, next_, ns, ps, history, link_rows, keypad, zoom):
    """Render at native 320×240, nearest-neighbor scale once for zoom."""
    canvas = pygame.Surface((SCREEN_W, SCREEN_H))
    canvas.fill(TT_COLORS[0])

    # Teletext grid (left 240px)
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

        # Subtle link-row indicator: dim cyan tint over each ref's 3 chars
        if ri in link_rows:
            chars = ''
            for ci in range(COLS):
                _, _, payload, is_mosaic = grid[ri][ci]
                chars += (payload if (not is_mosaic and payload) else ' ')
            tint = pygame.Surface((CHAR_W * 3, CHAR_H), pygame.SRCALPHA)
            tint.fill((0, 200, 200, 50))
            for m in re.finditer(r'(?<!\d)(\d{3})(?!\d)', chars):
                if 100 <= int(m.group(1)) <= 899:
                    canvas.blit(tint, (m.start() * CHAR_W, ri * CHAR_H))

    # Right-strip nav panel
    draw_strip(canvas, font, current_page, prev, next_, ns, ps, history, keypad.visible)

    # Numeric keypad overlay (drawn last — on top of everything)
    keypad.draw(canvas, font)

    # Bottom fast-text bar (4 coloured buttons across APP_W)
    nav_bw = APP_W // 4
    for i, (col, lbl, _) in enumerate(nav_btns):
        nx = i * nav_bw
        pygame.draw.rect(canvas, TT_COLORS[col], (nx, GRID_H, nav_bw, NAV_H))
        if lbl:
            txt = font.render(lbl[:10], False, TT_COLORS[0], TT_COLORS[col])
            txt = pygame.transform.scale(txt, (CHAR_W * len(lbl[:10]), CHAR_H))
            tw  = txt.get_width()
            canvas.blit(txt, (nx + (nav_bw - tw) // 2, GRID_H + (NAV_H - CHAR_H) // 2))

    draw_taskbar_pygame(canvas, active_app="Teletext",
                        scroll_offset=_TB_SCROLL, app_order=_APP_ORDER)

    if zoom == 1:
        surf.blit(canvas, (0, 0))
    else:
        surf.blit(pygame.transform.scale(canvas, (SCREEN_W * zoom, SCREEN_H * zoom)), (0, 0))

# ── strip hit-test (canvas coordinates) ──────────────────────────────────────

def strip_hit(cx, cy):
    """Return action string for a canvas-coord click in the right strip, or None."""
    if not (STRIP_X <= cx < TASKBAR_X and 0 <= cy < GRID_H):
        return None
    if cy <= STRIP_SUBUP_Y1:  return 'subup'
    if cy <= STRIP_PAGE_Y1:   return 'page'
    if cy <= STRIP_BACK_Y1:   return 'back'
    if cy <= STRIP_PREV_Y1:   return 'prev'
    if cy <= STRIP_NEXT_Y1:   return 'next'
    return 'subdn'

# ── main ──────────────────────────────────────────────────────────────────────

def parse_args():
    """--source {nos,ceefax} plus an optional positional page number."""
    argv = sys.argv[1:]
    source = 'nos'
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == '--source' and i + 1 < len(argv):
            source = argv[i + 1]
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    default_page = '101' if source == 'nos' else '100'
    page = rest[0] if rest else default_page
    return source, page

def main():
    source, page = parse_args()

    win = PreviewWindow("NOS Teletekst" if source == 'nos' else "NMS Ceefax",
                        scale=ZOOM_LEVELS[1])

    font = None
    for candidate in _UNSCII_CANDIDATES:
        try:
            font = pygame.font.Font(candidate, 8)
            break
        except FileNotFoundError:
            pass
    if font is None:
        font = pygame.font.SysFont('monospace', 8)

    history  = []   # 10-entry page history ring
    keypad   = Keypad()
    fetch_err = [None]     # [str | None] — NOS HTTP errors, shown in title bar
    ceefax_status = [None] # [str | None] — Ceefax connection/acquisition status

    client = None
    if source == 'ceefax':
        from ceefax_client import CeefaxClient
        client = CeefaxClient(page=int(page))
        client.start()

    def load(pg):
        raw = fetch(pg)
        meta, content = parse(raw)
        return build_cell_grid(content), *extract_nav(meta, content)

    def navigate(pg, push=True):
        nonlocal current_page, grid, prev, next_, ns, ps, btns, link_rows
        if source == 'ceefax':
            # Non-blocking: request the page, then let the per-frame poll
            # below pick up header/row updates as the carousel airs it
            # (EXP-005 finding 4 — there is no synchronous "fetch" here).
            if push:
                history.append(current_page)
                if len(history) > 10:
                    history.pop(0)
            current_page = pg
            fetch_err[0] = None
            client.goto(int(pg))
            # Immediate on-canvas feedback — without this the grid just goes
            # blank for the 3-20s+ carousel wait, which reads as a hang, not
            # a wait (see ceefax_client.goto()'s docstring for the bug this
            # was masking: the status string used to go stale here too).
            waiting = ceefax_waiting_content(int(pg))
            grid = build_cell_grid(waiting)
            prev, next_, ns, ps, btns = ceefax_extract_nav(int(pg), waiting)
            link_rows = set()
            return
        try:
            new_grid, new_prev, new_next, new_ns, new_ps, new_btns = load(pg)
        except urllib.error.HTTPError as e:
            fetch_err[0] = f'p{pg}: HTTP {e.code}'
            return
        except Exception as e:
            fetch_err[0] = f'p{pg}: {e}'
            return
        fetch_err[0] = None
        if push:
            history.append(current_page)
            if len(history) > 10:
                history.pop(0)
        current_page = pg
        grid, prev, next_, ns, ps, btns = new_grid, new_prev, new_next, new_ns, new_ps, new_btns
        link_rows = scan_links(grid)

    def go_back():
        if history:
            pg = history.pop()
            navigate(pg, push=False)

    current_page = page
    if source == 'ceefax':
        waiting = ceefax_waiting_content(int(current_page))
        grid = build_cell_grid(waiting)
        prev, next_, ns, ps, btns = ceefax_extract_nav(int(current_page), waiting)
        link_rows = set()
    else:
        grid, prev, next_, ns, ps, btns = load(current_page)
        link_rows = scan_links(grid)
    clock = pygame.time.Clock()
    running = True

    while running:
        zoom = win.scale

        if source == 'ceefax':
            content, dirty, status, acquired, flof = client.snapshot()
            ceefax_status[0] = status
            if dirty:
                if acquired:
                    grid = build_cell_grid(content)
                    prev, next_, ns, ps, btns = ceefax_extract_nav(int(current_page), content, flof)
                    link_rows = scan_links(grid)
                else:
                    # goto() marks dirty on its own reset too (blank content)
                    # — show the waiting message instead of a blank flash.
                    waiting = ceefax_waiting_content(int(current_page))
                    grid = build_cell_grid(waiting)
                    prev, next_, ns, ps, btns = ceefax_extract_nav(int(current_page), waiting)
                    link_rows = set()

        for ev in pygame.event.get():
            if ev.type == pygame.KEYDOWN:
                # ── keypad open: digits route to keypad; +/-/q handled by PreviewWindow ──
                if keypad.visible:
                    if win.handle_event(ev):   # +/-: resize; q: quit
                        continue
                    if ev.key == pygame.K_ESCAPE:
                        keypad.hide()
                    elif ev.key == pygame.K_BACKSPACE:
                        keypad.push('backspace')
                    elif pygame.K_0 <= ev.key <= pygame.K_9:
                        pg = keypad.push(chr(ev.key))
                        if pg:
                            navigate(pg)
                    elif ev.key in (pygame.K_KP0, pygame.K_KP1, pygame.K_KP2,
                                    pygame.K_KP3, pygame.K_KP4, pygame.K_KP5,
                                    pygame.K_KP6, pygame.K_KP7, pygame.K_KP8,
                                    pygame.K_KP9):
                        pg = keypad.push(str(ev.key - pygame.K_KP0))
                        if pg:
                            navigate(pg)

                # ── keypad closed: navigation + PreviewWindow events ─────────
                else:
                    if win.handle_event(ev):   # +/-: resize; q/Q: quit
                        continue
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_RIGHT and next_:   navigate(next_)
                    elif ev.key == pygame.K_LEFT  and prev:    navigate(prev)
                    elif ev.key == pygame.K_UP    and ns:      navigate(ns)
                    elif ev.key == pygame.K_DOWN  and ps:      navigate(ps)
                    elif ev.key == pygame.K_BACKSPACE:         go_back()
                    elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                        idx = ev.key - pygame.K_1
                        if idx < len(btns) and btns[idx][2]: navigate(btns[idx][2])
                    # Any digit key opens keypad and feeds first digit
                    elif pygame.K_0 <= ev.key <= pygame.K_9:
                        keypad.show()
                        pg = keypad.push(chr(ev.key))
                        if pg: navigate(pg)

            elif win.handle_event(ev):   # handles QUIT for non-KEYDOWN events
                continue

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                cx_raw = mx // zoom
                cy_raw = my // zoom

                # ── keypad open: route clicks into keypad or dismiss ─────────
                if keypad.visible:
                    key = keypad.hit(cx_raw, cy_raw)
                    if key is not None:
                        if key == '<':
                            keypad.push('backspace')
                        elif key:
                            pg = keypad.push(key)
                            if pg: navigate(pg)
                    elif not keypad.contains(cx_raw, cy_raw):
                        keypad.hide()  # click outside → dismiss

                # ── keypad closed: strip / grid / nav bar ────────────────────
                else:
                    action = strip_hit(cx_raw, cy_raw)
                    if action == 'page':                    keypad.show()
                    elif action == 'back':                  go_back()
                    elif action == 'subup' and ps:          navigate(ps)
                    elif action == 'prev'  and prev:        navigate(prev)
                    elif action == 'next'  and next_:       navigate(next_)
                    elif action == 'subdn' and ns:          navigate(ns)
                    elif cy_raw >= GRID_H and cx_raw < APP_W:
                        nav_bw = APP_W // 4
                        btn_idx = cx_raw // nav_bw
                        if btn_idx < len(btns) and btns[btn_idx][2]:
                            navigate(btns[btn_idx][2])
                    elif cx_raw < GRID_W and cy_raw < GRID_H:
                        row = cy_raw // CHAR_H
                        tap_col = cx_raw // CHAR_W
                        pg_ref = find_row_link(grid, row, tap_col)
                        if pg_ref: navigate(pg_ref)

        draw_page(pygame.display.get_surface(), font, grid, btns, current_page,
                  prev, next_, ns, ps, history, link_rows, keypad, zoom)
        if source == 'ceefax':
            if keypad.visible:
                hint = '[keypad] 0-9 digit  Esc dismiss'
            else:
                hint = '←→ page±1  1-4 ftl(if linked)  0-9 goto  Bksp back  +/- zoom  (no subpg)'
            title = f'NMS Ceefax  p:{current_page}  hist:{len(history)}  {ceefax_status[0]}   {hint}'
        else:
            if fetch_err[0]:
                hint = f'ERROR: {fetch_err[0]}'
            elif keypad.visible:
                hint = '[keypad] 0-9 digit  Esc dismiss'
            else:
                hint = '←→ page  ↑↓ subpg  1-4 ftl  0-9 goto  Bksp back  +/- zoom'
            title = f'NOS Teletekst  p:{current_page}  hist:{len(history)}   {hint}'
        pygame.display.set_caption(title)
        win.flip()
        clock.tick(10)

    if client:
        client.stop()
    pygame.quit()

if __name__ == '__main__':
    main()
