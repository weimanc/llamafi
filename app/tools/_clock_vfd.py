"""_clock_vfd.py — VFD Dot-Matrix Clock Renderer.

Rendering model: rasterize-then-blur.
  1. Grid pass  — paint every dot as a flat C_ON / C_OFF rectangle.  No glow.
  2. Bloom pass — GaussianBlur(sharp_grid, radius) × BLOOM_SCALE.
  3. Composite  — ImageChops.add(sharp, bloom).  Additive: adjacent lit dots
                  accumulate stronger glow at their shared boundary.

Canvas: 275×240 px app canvas.
Dot geometry: 4×4 px cells, 1 px gap → 5 px stride, 13×24 matrix per digit.
Layout: 3 | H1(64) | H2(64) | colon(13) | M1(64) | M2(64) | 3 = 275 px.

Imported by preview_clock.py; exposes VFDRenderer.
Standalone test: python3 _clock_vfd.py → /tmp/vfd_test.png
"""
from __future__ import annotations

import pathlib
import time as _time
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter

# ── canvas ────────────────────────────────────────────────────────────────────

CANVAS_W = 275
CANVAS_H = 240

# ── dot-matrix geometry ───────────────────────────────────────────────────────

TC = 4    # dot cell size (px)
TG = 1    # gap between dots (px)
TS = 5    # stride = TC + TG

T_COLS = 13
T_ROWS = 24
DIGIT_W = T_COLS * TC + (T_COLS - 1) * TG  # 64 px
DIGIT_H = T_ROWS * TC + (T_ROWS - 1) * TG  # 119 px

DIGIT_TOP_Y = 10

_X_H1  =   3
_X_H2  =  67   # 3 + 64
_X_COL = 131   # 3 + 64 + 64  → 13-px colon column
_X_M1  = 144   # 131 + 13
_X_M2  = 208   # 144 + 64
# right margin: 208 + 64 = 272, +3 = 275  ✓

# Colon: two 8×8 px dots centred in the 13-px colon column
_COL_DOT_X  = _X_COL + (_X_M1 - _X_COL - 8) // 2   # = 133
_COL_DOT_Y1 = DIGIT_TOP_Y + 32
_COL_DOT_Y2 = DIGIT_TOP_Y + 79

# ── date dot-matrix geometry ──────────────────────────────────────────────────

DC = 2    # date cell size (px)
DG = 1    # date gap (px)
DS = 3    # date stride = DC + DG

# ── digit glyphs (11 cols × 20 rows, 16 active + 4 padding) ──────────────────
#
# Placed inside the 13×24 matrix with 1-dot L/R margin, 2-dot top/bottom margin.
# Each row is an 11-bit integer: bit 10 = col 0 (left), bit 0 = col 10 (right).

def _b(s: str) -> int:
    assert len(s) == 11
    v = 0
    for i, c in enumerate(s):
        if c == "X":
            v |= 1 << (10 - i)
    return v

def _g(rows_16: list[str]) -> list[int]:
    assert len(rows_16) == 16
    return [_b(r) for r in rows_16] + [0] * 4

_GLYPHS: list[list[int]] = [
    _g([  # 0
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
    _g([  # 1
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
    _g([  # 2
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
    _g([  # 3
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
    _g([  # 4
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
    _g([  # 5
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
    _g([  # 6
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
    _g([  # 7
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
    _g([  # 8
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
    _g([  # 9
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
    ("teal",  (0,  210, 230)),
    ("amber", (230, 160,   0)),
    ("blue",  (60,  120, 255)),
    ("green", (0,  220,  80)),
]

# ── Font1 date support ────────────────────────────────────────────────────────

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
    if _HAS_F1:
        return _F1.CHAR_W * DS
    return 14

def _centre_x(text: str) -> int:
    w = len(text) * _date_char_width() - (DG if _HAS_F1 else 0)
    return max(0, (CANVAS_W - w) // 2)

# ── rasterizers (Step 1 — flat color, no glow) ────────────────────────────────

def _rasterize_digit(
    draw: ImageDraw.ImageDraw,
    digit: int,
    dx: int, dy: int,
    C_ON: tuple, C_OFF: tuple,
) -> None:
    glyph = _GLYPHS[digit % 10]
    for mat_row in range(T_ROWS):
        gr = mat_row - 2
        row_bits = glyph[gr] if 0 <= gr < 20 else 0
        for mat_col in range(T_COLS):
            gc = mat_col - 1
            active = bool(row_bits & (1 << (10 - gc))) if 0 <= gc < 11 else False
            px = dx + mat_col * TS
            py = dy + mat_row * TS
            draw.rectangle([px, py, px + TC - 1, py + TC - 1],
                           fill=C_ON if active else C_OFF)


def _rasterize_colon(
    draw: ImageDraw.ImageDraw,
    lit: bool,
    C_ON: tuple, C_OFF: tuple,
) -> None:
    colour = C_ON if lit else C_OFF
    for cy in (_COL_DOT_Y1, _COL_DOT_Y2):
        draw.rectangle([_COL_DOT_X, cy, _COL_DOT_X + 7, cy + 7], fill=colour)


def _rasterize_date_str(
    draw: ImageDraw.ImageDraw,
    text: str,
    x0: int, y0: int,
    C_FG: tuple, C_OFF: tuple,
    font_fallback: ImageFont.FreeTypeFont,
) -> None:
    if not _HAS_F1:
        draw.text((x0, y0), text, font=font_fallback, fill=C_FG)
        return
    cx = x0
    for ch in text:
        bm = _F1._glyph(ord(ch))
        for r, row in enumerate(bm):
            for c, lit in enumerate(row):
                px = cx + c * DS
                py = y0 + r * DS
                draw.rectangle([px, py, px + DC - 1, py + DC - 1],
                               fill=C_FG if lit else C_OFF)
        cx += _F1.CHAR_W * DS

# ── VFDRenderer ───────────────────────────────────────────────────────────────

class VFDRenderer:
    """VFD dot-matrix clock.

    Pipeline each frame:
      1. Rasterize all dots to a sharp grid (no glow).
      2. GaussianBlur(sharp, BLOOM_R) × BLOOM_SCALE  → bloom layer.
      3. ImageChops.add(sharp, bloom)  → additive composite.
    """

    CANVAS_W = CANVAS_W
    CANVAS_H = CANVAS_H

    def __init__(self) -> None:
        self._theme_idx  = 0
        self._bloom_r     = 4.0   # GaussianBlur radius (px)
        self._bloom_scale = 1.2   # bloom layer intensity multiplier
        self._contrast   = 0      # 0=standard 1=high 2=low
        self._bg         = (0, 5, 18)
        self._font_fb    = _fallback_font(14)

    # ── palette ───────────────────────────────────────────────────────────────

    def _palette(self):
        """Return (C_ON, C_OFF, C_DATE)."""
        _, c_on = _THEMES[self._theme_idx]
        if self._contrast == 0:
            off_f = 0.06   # dark gaps — bloom fills them; this is standard VFD look
        elif self._contrast == 1:
            off_f = 0.0    # fully black gaps, maximum bloom contrast
        else:
            off_f = 0.14   # more visible grid, less dramatic bloom
        c_off  = tuple(min(255, int(v * off_f)) for v in c_on)
        c_date = tuple(min(255, int(v * 0.68))  for v in c_on)
        return c_on, c_off, c_date

    # ── render ────────────────────────────────────────────────────────────────

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        C_ON, C_OFF, C_DATE = self._palette()

        # ── Step 1: rasterize all dots as flat rectangles ─────────────────────
        sharp = Image.new("RGB", (CANVAS_W, CANVAS_H), self._bg)
        d     = ImageDraw.Draw(sharp)

        h1, h2 = t.tm_hour // 10, t.tm_hour % 10
        m1, m2 = t.tm_min  // 10, t.tm_min  % 10
        _rasterize_digit(d, h1, _X_H1, DIGIT_TOP_Y, C_ON, C_OFF)
        _rasterize_digit(d, h2, _X_H2, DIGIT_TOP_Y, C_ON, C_OFF)
        _rasterize_digit(d, m1, _X_M1, DIGIT_TOP_Y, C_ON, C_OFF)
        _rasterize_digit(d, m2, _X_M2, DIGIT_TOP_Y, C_ON, C_OFF)
        _rasterize_colon(d, t.tm_sec % 2 == 0, C_ON, C_OFF)

        _MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN",
                   "JUL","AUG","SEP","OCT","NOV","DEC"]
        _DAYS   = ["MON","TUE","WED","THU","FRI","SAT","SUN"]
        day_str  = _DAYS[t.tm_wday]
        date_str = f"{t.tm_mday:02d} {_MONTHS[t.tm_mon - 1]} {t.tm_year}"

        CHAR_H_DOT = (_F1.GLYPH_H * DS - DG) if _HAS_F1 else 16
        block_top  = DIGIT_TOP_Y + DIGIT_H + 12   # 141 px
        line_gap   = 10
        _rasterize_date_str(d, day_str,
                            _centre_x(day_str),  block_top,
                            C_DATE, C_OFF, self._font_fb)
        _rasterize_date_str(d, date_str,
                            _centre_x(date_str), block_top + CHAR_H_DOT + line_gap,
                            C_DATE, C_OFF, self._font_fb)

        # ── Step 2: bloom (blur + scale) ──────────────────────────────────────
        bloom = sharp.filter(ImageFilter.GaussianBlur(radius=self._bloom_r))
        bloom = bloom.point(lambda x: int(x * self._bloom_scale))

        # ── Step 3: additive composite ────────────────────────────────────────
        out = ImageChops.add(sharp, bloom)
        img.paste(out, (0, 0))

    # ── key handler ───────────────────────────────────────────────────────────

    def on_key(self, key: str) -> bool:
        if key == "g":
            self._bloom_scale = min(1.2, round(self._bloom_scale + 0.05, 2))
        elif key in ("G", "shift+g"):
            self._bloom_scale = max(0.0, round(self._bloom_scale - 0.05, 2))
        elif key == "r":
            self._bloom_r = min(6.0, round(self._bloom_r + 0.2, 1))
        elif key in ("R", "shift+r"):
            self._bloom_r = max(0.2, round(self._bloom_r - 0.2, 1))
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
        return ("g/G=bloom scale  r/R=bloom radius  "
                "s=contrast  c=colour theme  b=bg blue")

    def param_dict(self) -> dict:
        C_ON, C_OFF, C_DATE = self._palette()
        return {
            "theme":        _THEMES[self._theme_idx][0],
            "contrast":     ["standard", "high", "low"][self._contrast],
            "C_BG":         self._bg,
            "C_ON":         C_ON,
            "C_OFF":        C_OFF,
            "C_DATE":       C_DATE,
            "BLOOM_R":      self._bloom_r,
            "BLOOM_SCALE":  self._bloom_scale,
            "TC": TC, "TG": TG, "T_COLS": T_COLS, "T_ROWS": T_ROWS,
            "DIGIT_W": DIGIT_W, "DIGIT_H": DIGIT_H,
            "DC": DC, "DG": DG,
        }


# ── standalone debug ──────────────────────────────────────────────────────────

def _debug_render(r: VFDRenderer, t: _time.struct_time) -> None:
    """Run render pipeline step-by-step, save all three layers, print pixel probes."""
    import numpy as np

    C_ON, C_OFF, C_DATE = r._palette()

    # ── Step 1: sharp grid ────────────────────────────────────────────────────
    sharp = Image.new("RGB", (CANVAS_W, CANVAS_H), r._bg)
    d     = ImageDraw.Draw(sharp)
    h1, h2 = t.tm_hour // 10, t.tm_hour % 10
    m1, m2 = t.tm_min  // 10, t.tm_min  % 10
    _rasterize_digit(d, h1, _X_H1, DIGIT_TOP_Y, C_ON, C_OFF)
    _rasterize_digit(d, h2, _X_H2, DIGIT_TOP_Y, C_ON, C_OFF)
    _rasterize_digit(d, m1, _X_M1, DIGIT_TOP_Y, C_ON, C_OFF)
    _rasterize_digit(d, m2, _X_M2, DIGIT_TOP_Y, C_ON, C_OFF)
    _rasterize_colon(d, t.tm_sec % 2 == 0, C_ON, C_OFF)

    # ── Step 2: bloom ─────────────────────────────────────────────────────────
    bloom_raw   = sharp.filter(ImageFilter.GaussianBlur(radius=r._bloom_r))
    bloom_scaled = bloom_raw.point(lambda x: int(x * r._bloom_scale))

    # ── Step 3: additive composite ────────────────────────────────────────────
    out = ImageChops.add(sharp, bloom_scaled)

    # ── save all three layers (3× nearest-neighbour scale) ────────────────────
    S = 3
    sz = (CANVAS_W * S, CANVAS_H * S)
    sharp.resize(sz, Image.NEAREST).save("/tmp/vfd_1_sharp.png")
    bloom_raw.resize(sz, Image.NEAREST).save("/tmp/vfd_2_bloom_raw.png")
    bloom_scaled.resize(sz, Image.NEAREST).save("/tmp/vfd_2_bloom_scaled.png")
    out.resize(sz, Image.NEAREST).save("/tmp/vfd_3_out.png")

    # ── pixel probes ──────────────────────────────────────────────────────────
    # Pick three meaningful points inside digit H2 (the "0" at x=67):
    #   A — centre of an active dot  (should be C_ON in sharp, brighter in out)
    #   B — the 1-px gap between two adjacent active dots  (C_OFF in sharp, lit up by bloom)
    #   C — background far from any digit  (C_BG in sharp, tiny bloom spill in out)

    # "0" glyph: row 4 of glyph (matrix row 6) is "X.........X"
    # col 0 of glyph → matrix col 1 → pixel x = _X_H2 + 1*TS = 67+5 = 72
    # matrix row 6  → pixel y = DIGIT_TOP_Y + 6*TS = 10+30 = 40
    # Centre of that dot: (72+1, 40+1) = (73, 41)
    px_A = (73, 41)

    # Gap pixel: one pixel to the right of that dot's right edge
    # dot right edge at x = 72 + TC - 1 = 75; gap pixel at x = 76
    px_B = (76, 41)

    # Background pixel far from all digits: bottom-left corner
    px_C = (10, 220)

    def probe(img, label, px):
        pixel = img.getpixel(px)
        g_val = max(pixel)   # max channel = "brightness"
        return f"  {label} {px}: RGB{pixel}  max={g_val}"

    print("=" * 60)
    print(f"Bloom params: radius={r._bloom_r}  scale={r._bloom_scale}")
    print(f"C_ON={C_ON}  C_OFF={C_OFF}  C_BG={r._bg}")
    print()
    print("Probe A — centre of active dot (expect C_ON in sharp, ≥C_ON in out):")
    print(probe(sharp,        "sharp      ", px_A))
    print(probe(bloom_scaled, "bloom      ", px_A))
    print(probe(out,          "out        ", px_A))
    print()
    print("Probe B — gap pixel beside active dot (expect C_OFF in sharp, lit up in out):")
    print(probe(sharp,        "sharp      ", px_B))
    print(probe(bloom_scaled, "bloom      ", px_B))
    print(probe(out,          "out        ", px_B))
    print()
    print("Probe C — background far from digits (expect C_BG in sharp, tiny spill in out):")
    print(probe(sharp,        "sharp      ", px_C))
    print(probe(bloom_scaled, "bloom      ", px_C))
    print(probe(out,          "out        ", px_C))
    print()

    # ── channel stats via numpy ───────────────────────────────────────────────
    def stats(img, name):
        a = np.array(img)
        return (f"  {name:20s}  "
                f"min={a.min():3d}  max={a.max():3d}  "
                f"mean={a.mean():.1f}  "
                f"nonzero={np.count_nonzero(a):6d} px-channels")

    print("Image stats (all channels):")
    print(stats(sharp,        "sharp"))
    print(stats(bloom_raw,    "bloom_raw"))
    print(stats(bloom_scaled, "bloom_scaled"))
    print(stats(out,          "out"))
    print()
    print("Saved:")
    print("  /tmp/vfd_1_sharp.png        ← pure rasterized grid, no glow")
    print("  /tmp/vfd_2_bloom_raw.png    ← blurred grid (before scale)")
    print("  /tmp/vfd_2_bloom_scaled.png ← blurred grid (after ×scale)")
    print("  /tmp/vfd_3_out.png          ← final additive composite")
    print("=" * 60)


if __name__ == "__main__":
    t = _time.struct_time((2026, 6, 13, 10, 34, 1, 4, 164, 1))
    r = VFDRenderer()
    _debug_render(r, t)
