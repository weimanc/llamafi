"""_clock_vfd.py — VFD Dot-Matrix Clock Renderer.

Dot-matrix phosphor display. Time digits: 13×24 dot matrix, 4×4 px cells,
1 px gap (5 px stride) → 64×119 px per digit. Date: Font1 5×7 glyphs rendered
as 2×2 dot cells with 1 px gap (3 px stride). No seconds bar.

Canvas layout (275 px wide):
  3 | H1(64) | H2(64) | colon(13) | M1(64) | M2(64) | 3   = 275 px
Digit top y = 10.  Date block y ≈ 145..210.

Imported by preview_clock.py as `_clock_vfd`; exposes `VFDRenderer`.
Standalone test: python3 _clock_vfd.py → /tmp/vfd_test.png
"""
from __future__ import annotations

import pathlib
import time as _time
from PIL import Image, ImageDraw, ImageFont

# ── canvas ────────────────────────────────────────────────────────────────────

CANVAS_W = 275
CANVAS_H = 240
CENTRE_X = 137

# ── time dot-matrix geometry ──────────────────────────────────────────────────

TC = 4    # time cell size (px)
TG = 1    # time gap (px)
TS = 5    # time stride  TC + TG

T_COLS = 13                                 # dot columns per digit
T_ROWS = 24                                 # dot rows per digit
DIGIT_W = T_COLS * TC + (T_COLS - 1) * TG  # 64 px
DIGIT_H = T_ROWS * TC + (T_ROWS - 1) * TG  # 119 px

DIGIT_TOP_Y = 10   # y of digit top edge

# Horizontal x origins (left edge of each digit matrix)
_X_H1    =   3
_X_H2    =  67   # _X_H1 + 64
_X_COL   = 131   # _X_H2 + 64  → 13-px colon column
_X_M1    = 144   # _X_COL + 13
_X_M2    = 208   # _X_M1 + 64
# right edge: 208+64=272, margin=3  ✓  total=3+64+64+13+64+64+3=275

# Colon dots: 8×8 px, centred in the 13-px column
_COL_DOT_X  = _X_COL + (_X_M1 - _X_COL - 8) // 2   # = 133
_COL_DOT_Y1 = DIGIT_TOP_Y + 32
_COL_DOT_Y2 = DIGIT_TOP_Y + 79

# ── date dot-matrix geometry ──────────────────────────────────────────────────

DC = 2    # date cell size (px)
DG = 1    # date gap (px)
DS = 3    # date stride  DC + DG

# ── 11×20 dot-matrix glyphs for digits 0–9 ───────────────────────────────────
#
# Inner content: 11 cols × 16 active rows, padded to 20 rows (rows 16-19 = off).
# Placed inside the 13×24 matrix with 1-dot margin left/right, 2-dot margin top/bottom:
#   glyph col c  ↔  matrix col (c + 1)
#   glyph row r  ↔  matrix row (r + 2)
#
# Each row is an 11-bit integer: bit 10 = leftmost column (col 0), bit 0 = rightmost (col 10).

def _b(s: str) -> int:
    """'X'/'.' string (11 chars) → 11-bit integer."""
    assert len(s) == 11, f"Expected 11 chars, got {len(s)!r}"
    v = 0
    for i, c in enumerate(s):
        if c == "X":
            v |= 1 << (10 - i)
    return v

def _g(rows_16: list[str]) -> list[int]:
    """16 row-strings → 20-int glyph (padded with 4 trailing off-rows)."""
    assert len(rows_16) == 16, f"need 16 rows, got {len(rows_16)}"
    return [_b(r) for r in rows_16] + [0] * 4

_GLYPHS: list[list[int]] = [
    _g([  # 0 — oval
        "...XXXXX...",
        "..X.....X..",
        ".X.......X.",
        ".X.......X.",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        ".X.......X.",
        ".X.......X.",
        "..X.....X..",
        "...XXXXX...",
        "...........",
    ]),
    _g([  # 1 — centred stem with base
        ".....X.....",
        "....XX.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        "....XXX....",
        "...XXXXX...",
        "...........",
    ]),
    _g([  # 2 — top-right to bottom-left sweep
        "...XXXXX...",
        "..X.....X..",
        ".X.......X.",
        "X.........X",
        "..........X",
        "..........X",
        ".........X.",
        "........X..",
        "......XX...",
        "....XX.....",
        "...X.......",
        "..X........",
        ".X.........",
        "X..........",
        "XXXXXXXXXXX",
        "...........",
    ]),
    _g([  # 3 — two-loop form
        "...XXXXX...",
        "..X.....X..",
        ".X.......X.",
        "X.........X",
        "..........X",
        "..........X",
        "...XXXXXXX.",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "X.........X",
        ".X.......X.",
        "..X.....X..",
        "...XXXXX...",
        "...........",
    ]),
    _g([  # 4 — vertical strokes + horizontal bar
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "XXXXXXXXXXX",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "...........",
    ]),
    _g([  # 5 — top horizontal, mid-bar, lower loop
        "XXXXXXXXXXX",
        "X..........",
        "X..........",
        "X..........",
        "X..........",
        "XXXXXXXXXX.",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "X.........X",
        ".X.......X.",
        "..X.....X..",
        "...XXXXX...",
        "...........",
    ]),
    _g([  # 6 — top cap, open right side, lower oval
        "...XXXXX...",
        "..X.....X..",
        ".X.........",
        "X..........",
        "X..........",
        "XXXXXXXXXX.",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        ".X.......X.",
        "..X.....X..",
        "...XXXXX...",
        "...........",
    ]),
    _g([  # 7 — top bar, diagonal drop
        "XXXXXXXXXXX",
        "..........X",
        "..........X",
        ".........X.",
        ".........X.",
        "........X..",
        "........X..",
        ".......X...",
        ".......X...",
        "......X....",
        "......X....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        ".....X.....",
        "...........",
    ]),
    _g([  # 8 — double oval
        "...XXXXX...",
        "..X.....X..",
        ".X.......X.",
        "X.........X",
        "X.........X",
        ".X.......X.",
        "..XXXXXXX..",
        ".X.......X.",
        "X.........X",
        "X.........X",
        "X.........X",
        "X.........X",
        ".X.......X.",
        "..X.....X..",
        "...XXXXX...",
        "...........",
    ]),
    _g([  # 9 — top oval, descender
        "...XXXXX...",
        "..X.....X..",
        ".X.......X.",
        "X.........X",
        "X.........X",
        "X.........X",
        ".X.......X.",
        "..XXXXXXXX.",
        "..........X",
        "..........X",
        "..........X",
        "..........X",
        "X.........X",
        ".X.......X.",
        "..XXXXXXX..",
        "...........",
    ]),
]

# ── colour themes ─────────────────────────────────────────────────────────────

_THEMES = [
    # name,  C_ON,              glow_ratio (0..1)
    ("teal",  (0,  210, 230),   0.24),
    ("amber", (230, 160,   0),  0.24),
    ("blue",  (60,  120, 255),  0.22),
    ("green", (0,  220,  80),   0.22),
]

# ── drawing helpers ───────────────────────────────────────────────────────────

def _dot_time(
    draw: ImageDraw.ImageDraw,
    px: int, py: int,
    active: bool,
    C_ON: tuple, C_GLOW: tuple, C_OFF: tuple,
) -> None:
    """Draw one 4×4 time dot at pixel top-left (px, py)."""
    if active:
        draw.rectangle([px - 1, py - 1, px + TC, py + TC], fill=C_GLOW)  # 1-px glow fringe
        draw.rectangle([px,     py,     px + TC - 1, py + TC - 1], fill=C_ON)
    else:
        draw.rectangle([px, py, px + TC - 1, py + TC - 1], fill=C_OFF)


def _draw_digit(
    draw: ImageDraw.ImageDraw,
    digit: int,
    dx: int, dy: int,
    C_ON: tuple, C_GLOW: tuple, C_OFF: tuple,
) -> None:
    """Render one digit at top-left (dx, dy) using the 13×24 dot matrix."""
    glyph = _GLYPHS[digit % 10]  # list of 20 ints
    for mat_row in range(T_ROWS):
        gr = mat_row - 2  # map matrix row → glyph row (top 2 = margin)
        row_bits = glyph[gr] if 0 <= gr < 20 else 0
        for mat_col in range(T_COLS):
            gc = mat_col - 1  # map matrix col → glyph col (left 1 = margin)
            active = bool(row_bits & (1 << (10 - gc))) if 0 <= gc < 11 else False
            _dot_time(draw,
                      dx + mat_col * TS,
                      dy + mat_row * TS,
                      active, C_ON, C_GLOW, C_OFF)


# ── Font1 date rendering ──────────────────────────────────────────────────────

try:
    import sys as _sys
    _sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import dut_fonts as _dut
    _F1 = _dut.Font1()
    _HAS_F1 = True
except Exception:
    _HAS_F1 = False

_DATE_FONT_PATHS = [
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
    "/usr/share/fonts/google-noto/NotoSansMono-ExtraBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]

def _fallback_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _DATE_FONT_PATHS:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def _date_char_width() -> int:
    """Pixel advance of one date character (Font1 at 3-px stride)."""
    if _HAS_F1:
        return _F1.CHAR_W * DS   # 6 × 3 = 18 px
    return 14   # approx for fallback font


def _draw_date_str(
    draw: ImageDraw.ImageDraw,
    text: str,
    x0: int, y0: int,
    C_ON: tuple, C_GLOW: tuple, C_OFF: tuple,
    font_fallback: ImageFont.FreeTypeFont,
) -> None:
    """Render a date/day string as 2×2 dot cells (Font1) or PIL fallback."""
    if not _HAS_F1:
        draw.text((x0, y0), text, font=font_fallback, fill=C_ON)
        return

    cx = x0
    for ch in text:
        bm = _F1._glyph(ord(ch))   # 7 rows × 5 cols booleans
        for r, row in enumerate(bm):
            for c, lit in enumerate(row):
                px = cx + c * DS
                py = y0 + r * DS
                if lit:
                    draw.rectangle([px - 1, py - 1, px + DC, py + DC], fill=C_GLOW)
                    draw.rectangle([px, py, px + DC - 1, py + DC - 1], fill=C_ON)
                else:
                    draw.rectangle([px, py, px + DC - 1, py + DC - 1], fill=C_OFF)
        cx += _F1.CHAR_W * DS


def _centre_x(text: str) -> int:
    """Return left x to centre text in 275-px canvas."""
    w = len(text) * _date_char_width() - (DG if _HAS_F1 else 0)
    return max(0, (CANVAS_W - w) // 2)


# ── VFDRenderer ───────────────────────────────────────────────────────────────

class VFDRenderer:
    """VFD dot-matrix clock renderer.

    Time: 13×24 dot matrix per digit, 4×4 px cells, 1 px gap.
    Date: Font1 5×7 rendered as 2×2 dot cells, 1 px gap.
    Glow: 1 px teal fringe on active dots.
    """

    CANVAS_W = CANVAS_W
    CANVAS_H = CANVAS_H

    def __init__(self) -> None:
        self._theme_idx = 0
        self._glow_scale = 0.24   # fraction of C_ON for glow
        self._contrast   = 0      # 0=standard 1=high 2=low
        self._bg         = (0, 5, 18)
        self._font_fb    = _fallback_font(14)

    # ── palette ───────────────────────────────────────────────────────────────

    def _palette(self):
        """Return (C_ON, C_GLOW, C_OFF, C_DATE)."""
        _, c_on, _ = _THEMES[self._theme_idx]

        c_glow = tuple(min(255, int(v * self._glow_scale)) for v in c_on)

        if self._contrast == 0:     # standard
            off_f = 0.17
        elif self._contrast == 1:   # high contrast
            off_f = 0.0
        else:                        # low contrast
            off_f = 0.27
        c_off  = tuple(min(255, int(v * off_f)) for v in c_on)
        c_date = tuple(min(255, int(v * 0.68))  for v in c_on)
        return c_on, c_glow, c_off, c_date

    # ── render ────────────────────────────────────────────────────────────────

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        draw   = ImageDraw.Draw(img)
        C_ON, C_GLOW, C_OFF, C_DATE = self._palette()

        draw.rectangle([0, 0, CANVAS_W - 1, CANVAS_H - 1], fill=self._bg)

        # ── time digits ──────────────────────────────────────────────────────
        h1, h2 = t.tm_hour // 10, t.tm_hour % 10
        m1, m2 = t.tm_min  // 10, t.tm_min  % 10

        _draw_digit(draw, h1, _X_H1, DIGIT_TOP_Y, C_ON, C_GLOW, C_OFF)
        _draw_digit(draw, h2, _X_H2, DIGIT_TOP_Y, C_ON, C_GLOW, C_OFF)
        _draw_digit(draw, m1, _X_M1, DIGIT_TOP_Y, C_ON, C_GLOW, C_OFF)
        _draw_digit(draw, m2, _X_M2, DIGIT_TOP_Y, C_ON, C_GLOW, C_OFF)

        # ── colon (8×8 px dots, blinking) ────────────────────────────────────
        c_colon = C_ON if (t.tm_sec % 2 == 0) else C_OFF
        for cy in (_COL_DOT_Y1, _COL_DOT_Y2):
            draw.rectangle([_COL_DOT_X - 1, cy - 1,
                            _COL_DOT_X + 8, cy + 8], fill=C_GLOW if t.tm_sec % 2 == 0 else self._bg)
            draw.rectangle([_COL_DOT_X, cy,
                            _COL_DOT_X + 7, cy + 7], fill=c_colon)

        # ── date block (2×2 dot Font1) ────────────────────────────────────────
        _MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN",
                   "JUL","AUG","SEP","OCT","NOV","DEC"]
        _DAYS   = ["MON","TUE","WED","THU","FRI","SAT","SUN"]

        day_str  = _DAYS[t.tm_wday]
        date_str = f"{t.tm_mday:02d} {_MONTHS[t.tm_mon - 1]} {t.tm_year}"

        # Char height at 2×2 dot scale: 7 rows × DC + 6 gaps × DG = 14+6 = 20 px
        CHAR_H_DOT = _F1.GLYPH_H * DS - DG if _HAS_F1 else 16

        # Two lines centred vertically in the remaining space below digits
        block_top = DIGIT_TOP_Y + DIGIT_H + 12   # 10+119+12 = 141
        line_gap  = 10
        day_y     = block_top
        date_y    = block_top + CHAR_H_DOT + line_gap

        _draw_date_str(draw, day_str,  _centre_x(day_str),  day_y,  C_DATE, C_GLOW, C_OFF, self._font_fb)
        _draw_date_str(draw, date_str, _centre_x(date_str), date_y, C_DATE, C_GLOW, C_OFF, self._font_fb)

    # ── key handler ───────────────────────────────────────────────────────────

    def on_key(self, key: str) -> bool:
        if key == "g":
            self._glow_scale = min(0.55, round(self._glow_scale + 0.04, 2))
        elif key == "G" or key == "shift+g":
            self._glow_scale = max(0.08, round(self._glow_scale - 0.04, 2))
        elif key == "s":
            self._contrast = (self._contrast + 1) % 3
        elif key == "c":
            self._theme_idx = (self._theme_idx + 1) % len(_THEMES)
        elif key == "b":
            r, g, b = self._bg
            self._bg = (r, g, min(80, b + 5))
        else:
            return False
        return True

    def help_text(self) -> str:
        return "g/G=glow  s=contrast  c=colour theme (teal/amber/blue/green)  b=bg blue"

    def param_dict(self) -> dict:
        C_ON, C_GLOW, C_OFF, C_DATE = self._palette()
        return {
            "theme":       _THEMES[self._theme_idx][0],
            "contrast":    ["standard","high","low"][self._contrast],
            "C_BG":        self._bg,
            "C_ON":        C_ON,
            "C_GLOW":      C_GLOW,
            "C_OFF":       C_OFF,
            "C_DATE":      C_DATE,
            "glow_scale":  self._glow_scale,
            "TC":          TC,
            "TG":          TG,
            "T_COLS":      T_COLS,
            "T_ROWS":      T_ROWS,
            "DIGIT_W":     DIGIT_W,
            "DIGIT_H":     DIGIT_H,
            "DC":          DC,
            "DG":          DG,
        }


# ── standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = _time.struct_time((2026, 6, 12, 10, 34, 45, 3, 163, 1))
    r = VFDRenderer()
    img = Image.new("RGB", (CANVAS_W, CANVAS_H))
    r.render(img, t)
    out = "/tmp/vfd_test.png"
    img.save(out)
    print(f"VFDRenderer OK  →  {out}")
    print(f"Digit: {DIGIT_W}×{DIGIT_H} px  (TC={TC} TG={TG} → stride={TS}  cols={T_COLS} rows={T_ROWS})")
    print(f"Date:  DC={DC} DG={DG} → stride={DS}  font={'Font1 (exact)' if _HAS_F1 else 'PIL fallback'}")
    print(f"Params: {r.param_dict()}")
