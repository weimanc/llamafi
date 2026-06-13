"""_clock_vfd.py — VFD Dot-Matrix Clock Renderer.

Rendering model: rasterize-then-blur.
  1. Grid pass  — one unified GRID_COLS×GRID_ROWS matrix covers the full time
                  area.  Every cell is painted C_ON (active) or C_OFF (inactive).
                  HH:MM glyphs are placed at specific column offsets within this
                  single grid — inter-digit gaps are ordinary off-dot columns.
  2. Bloom pass — GaussianBlur(sharp_grid, radius) × BLOOM_SCALE.
  3. Composite  — ImageChops.add(sharp, bloom).  Adjacent lit dots accumulate
                  stronger glow at their shared boundary.

Canvas: 275×240 px app canvas.
Dot geometry: TC=4 px cells, TG=1 px gap, TS=5 px stride.
Unified time grid: 54 cols × 24 rows, 3 px margin each side = 275 px.
  col layout:  2 | H1(11) | 1 | H2(11) | 4-colon | M1(11) | 1 | M2(11) | 2

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

# ── dot geometry ─────────────────────────────────────────────────────────────

TC = 4    # dot cell size (px)
TG = 1    # gap between dots (px)
TS = 5    # stride = TC + TG

# ── unified time matrix ───────────────────────────────────────────────────────
#
# One 54×24 grid covers the full time area.
# 3 px margin + 54 cols × 5 px stride − 1 px + 3 px margin = 275 px  ✓
#
# Column layout (glyph = 11 active cols, no built-in margins):
#   cols  0- 1  left margin (2 off-cols)
#   cols  2-12  H1 glyph
#   col  13     gap  ← visible separation between H1 and H2
#   cols 14-24  H2 glyph
#   cols 25-28  colon area (dots at col 26, rows 7-8 and 15-16)
#   cols 29-39  M1 glyph
#   col  40     gap  ← visible separation between M1 and M2
#   cols 41-51  M2 glyph
#   cols 52-53  right margin (2 off-cols)

GRID_COLS = 54
GRID_ROWS = 24
GRID_X0   = 3    # left margin (px); right margin = 275 − (3 + 54×5 − 1) = 3 px  ✓
GRID_Y0   = 10   # top of time matrix (px)

# Glyph inner dimensions within the unified grid
GLYPH_W          = 11   # active glyph columns
GLYPH_H          = 22   # active glyph rows  (1-row margin top + bottom = 24)
GLYPH_ROW_OFFSET =  1   # grid rows before glyph top (1-dot top margin)

# Digit glyph start columns
_H1_COL = 2
_H2_COL = 14
_M1_COL = 29
_M2_COL = 41

# Colon: 2×2-cell dots (each 2 cols × 2 rows = 9×9 px) at grid col 26
_COLON_CELLS = frozenset([
    (7, 26), (7, 27), (8, 26), (8, 27),    # upper colon dot
    (15, 26), (15, 27), (16, 26), (16, 27), # lower colon dot
])

# DIGIT_H kept for date block positioning below the matrix
DIGIT_H = GRID_ROWS * TC + (GRID_ROWS - 1) * TG  # 119 px

# ── date dot-matrix geometry ──────────────────────────────────────────────────

DC = 2    # date cell size (px)
DG = 1    # date gap (px)
DS = 3    # date stride = DC + DG

# ── digit glyphs — Dexter v2 ─────────────────────────────────────────────────
#
# Design system (all derived from W=11, H=22, S=2):
#   T  bar:  rows  0-1,  cols 2-8   (inset, 7 wide)
#   M  bar:  rows 10-11, cols 2-8
#   B  bar:  rows 20-21, cols 2-8
#   UL vert: rows  0-11, cols 0-1   (2 wide)
#   UR vert: rows  0-11, cols 9-10  (2 wide)
#   LL vert: rows 10-21, cols 0-1   (2 wide)
#   LR vert: rows 10-14, cols 9-10  (2 wide, upper section)
#            rows 15-21, cols 8-10  (3 wide, bottom 7 rows — lopsided flare)
#
#   Chamfer: single dot removed at each outer 90° corner (TL TR BL BR).
#   Row bit format: bit 10 = col 0 (left), bit 0 = col 10 (right).

_W = 11; _H = 22
_LR_SPLIT = _H - 7   # row 15 — LR widens from 2→3 dots below this row

def _blank_grid():
    return [[False] * _W for _ in range(_H)]

def _fill(g, r0, r1, c0, c1):
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            g[r][c] = True

def _grid_to_rows(g):
    out = []
    for row in g:
        v = 0
        for i, lit in enumerate(row):
            if lit:
                v |= 1 << (10 - i)
        out.append(v)
    return out

def _dex(segs: str) -> list[int]:
    s = set(segs.split())
    g = _blank_grid()
    if "T"  in s: _fill(g,  0,  1,  2,  8)
    if "M"  in s: _fill(g, 10, 11,  2,  8)
    if "B"  in s: _fill(g, 20, 21,  2,  8)
    if "UL" in s: _fill(g,  0, 11,  0,  1)
    if "UR" in s: _fill(g,  0, 11,  9, 10)
    if "LL" in s: _fill(g, 10, 21,  0,  1)
    if "LR" in s:
        _fill(g, 10, _LR_SPLIT - 1, 9, 10)   # upper LR: 2 wide
        _fill(g, _LR_SPLIT, 21,     8, 10)    # lower LR: 3 wide (flare)
    if "T" in s and "UL" in s: g[0][0]  = False   # TL chamfer
    if "T" in s and "UR" in s: g[0][10] = False   # TR chamfer
    if "B" in s and "LL" in s: g[21][0] = False   # BL chamfer
    if "B" in s and "LR" in s: g[21][10]= False   # BR chamfer
    return _grid_to_rows(g)

def _dex_one() -> list[int]:
    g = _blank_grid()
    for c in range(2, 6): g[0][c] = True          # serif
    for r in range(1, 20): g[r][4] = g[r][5] = True  # 2-wide stem
    _fill(g, 20, 21, 2, 8)                         # base
    return _grid_to_rows(g)

def _dex_seven() -> list[int]:
    g = _blank_grid()
    _fill(g, 0, 1, 2, 8)                           # T bar
    _fill(g, 0, 11, 9, 10)                          # UR 2-wide
    g[0][10] = False                                # TR chamfer
    for r in range(11, 14): _fill(g, r, r, 7, 10)  # diagonal step (4-wide)
    _fill(g, 13, _LR_SPLIT - 1, 7, 8)              # upper lower: 2-wide
    _fill(g, _LR_SPLIT, 21,     6, 8)              # bottom 7 rows: 3-wide
    return _grid_to_rows(g)

_GLYPHS: list[list[int]] = [
    _dex("T UL UR LL LR B"),       # 0
    _dex_one(),                     # 1  centred stem + serif + base
    _dex("T UR M LL B"),           # 2
    _dex("T UR M LR B"),           # 3
    _dex("UL UR M LR"),            # 4
    _dex("T UL M LR B"),           # 5
    _dex("T UL M LL LR B"),        # 6
    _dex_seven(),                   # 7  diagonal step + lopsided lower
    _dex("T UL UR M LL LR B"),     # 8
    _dex("T UL UR M LR B"),        # 9
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

def _rasterize_time_matrix(
    draw: ImageDraw.ImageDraw,
    h1: int, h2: int, m1: int, m2: int,
    colon_on: bool,
    C_ON: tuple, C_OFF: tuple,
) -> None:
    """Rasterize the unified 54×24 time grid in a single pass.

    Every cell is C_ON (active glyph dot or colon dot) or C_OFF (everything
    else — background, margins, inter-digit gaps).  No separate matrices.
    """
    digit_slots = ((_H1_COL, h1), (_H2_COL, h2), (_M1_COL, m1), (_M2_COL, m2))

    for grid_row in range(GRID_ROWS):
        for grid_col in range(GRID_COLS):
            active = False

            # Check digit glyph slots
            for start_col, digit in digit_slots:
                gc = grid_col - start_col
                if 0 <= gc < GLYPH_W:
                    gr = grid_row - GLYPH_ROW_OFFSET
                    if 0 <= gr < GLYPH_H:
                        active = bool(_GLYPHS[digit % 10][gr] & (1 << (10 - gc)))
                    break  # cell belongs to this digit's column range; stop checking

            # Check colon (only if not already claimed by a digit)
            if not active and colon_on and (grid_row, grid_col) in _COLON_CELLS:
                active = True

            px = GRID_X0 + grid_col * TS
            py = GRID_Y0 + grid_row * TS
            draw.rectangle([px, py, px + TC - 1, py + TC - 1],
                           fill=C_ON if active else C_OFF)


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
        _rasterize_time_matrix(d, h1, h2, m1, m2, t.tm_sec % 2 == 0, C_ON, C_OFF)

        _MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN",
                   "JUL","AUG","SEP","OCT","NOV","DEC"]
        _DAYS   = ["MON","TUE","WED","THU","FRI","SAT","SUN"]
        day_str  = _DAYS[t.tm_wday]
        date_str = f"{t.tm_mday:02d} {_MONTHS[t.tm_mon - 1]} {t.tm_year}"

        CHAR_H_DOT = (_F1.GLYPH_H * DS - DG) if _HAS_F1 else 16
        block_top  = GRID_Y0 + DIGIT_H + 12   # 141 px
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
    _rasterize_time_matrix(d, h1, h2, m1, m2, t.tm_sec % 2 == 0, C_ON, C_OFF)

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
    # A — active dot in H2 (digit "0", glyph col 0, grid row 6)
    #     grid col = _H2_COL + 0 = 14  →  px = GRID_X0 + 14*TS = 3+70 = 73
    #     grid row 6  →  py = GRID_Y0 + 6*TS = 10+30 = 40
    px_A = (73, 41)   # centre of that dot

    # B — inter-digit gap col (col 13, between H1 and H2) at same y
    #     px = GRID_X0 + 13*TS = 3+65 = 68
    px_B = (68, 41)

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
