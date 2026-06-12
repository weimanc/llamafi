"""_clock_vfd.py — VFD (Vacuum Fluorescent Display) clock renderer.

Imported by preview_clock.py as `_clock_vfd`; exposes `VFDRenderer`.
PIL-only (no pygame). Standalone test: python3 _clock_vfd.py → /tmp/vfd_test.png
"""
from __future__ import annotations

import pathlib
import time as _time
from PIL import Image, ImageDraw, ImageFont

# ── canvas ────────────────────────────────────────────────────────────────────

CANVAS_W = 275
CANVAS_H = 240
CENTRE_X = 137   # horizontal centre of app canvas

# ── font paths (same search list as preview_clock.py) ────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
    "/usr/share/fonts/google-noto/NotoSansMono-ExtraBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]

def _find_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)

# ── 7-segment definitions ─────────────────────────────────────────────────────

# Bit mask order: a b c d e f g  (bit 6 = a, bit 0 = g)
SEGS = [
    0b1111110,   # 0  a b c d e f
    0b0110000,   # 1      b c
    0b1101101,   # 2  a b   d e   g
    0b1111001,   # 3  a b c d     g
    0b0110011,   # 4      b c   f g
    0b1011011,   # 5  a   c d   f g
    0b1011111,   # 6  a   c d e f g
    0b1110000,   # 7  a b c
    0b1111111,   # 8  a b c d e f g
    0b1111011,   # 9  a b c d   f g
]

# Segment coordinate offsets relative to cell top-left (x, y).
# Each entry: (dx1, dy1, dx2, dy2)  — absolute rects once cell origin is added.
_SEG_OFFSETS = [
    # a  top horiz
    (5,  2,  37,  7),
    # b  top-right vert
    (38, 5,  42,  28),
    # c  bot-right vert
    (38, 36, 42,  59),
    # d  bot horiz
    (5,  57, 37,  62),
    # e  bot-left vert
    (0,  36, 4,   59),
    # f  top-left vert
    (0,  5,  4,   28),
    # g  middle horiz
    (5,  30, 37,  34),
]

# ── segment drawing helper ────────────────────────────────────────────────────

def _draw_seg(
    draw: ImageDraw.ImageDraw,
    x1: int, y1: int, x2: int, y2: int,
    active: bool,
    C_ON: tuple, C_GLOW: tuple, C_OFF: tuple,
) -> None:
    """Draw one segment at absolute pixel coordinates."""
    if active:
        # glow halo: expand 1px each side
        draw.rectangle([x1 - 1, y1 - 1, x2 + 1, y2 + 1], fill=C_GLOW)
        draw.rectangle([x1,     y1,     x2,     y2    ], fill=C_ON)
    else:
        draw.rectangle([x1, y1, x2, y2], fill=C_OFF)

# ── digit drawing ─────────────────────────────────────────────────────────────

def _draw_digit(
    draw: ImageDraw.ImageDraw,
    digit: int,
    cx: int, cy: int,
    C_ON: tuple, C_GLOW: tuple, C_OFF: tuple,
) -> None:
    """Draw a 7-segment digit.  (cx, cy) is the top-left corner of the 42×64 cell."""
    mask = SEGS[digit % 10]
    for bit_idx, (dx1, dy1, dx2, dy2) in enumerate(_SEG_OFFSETS):
        seg_bit = 6 - bit_idx          # bit 6=a down to bit 0=g
        active  = bool(mask & (1 << seg_bit))
        _draw_seg(
            draw,
            cx + dx1, cy + dy1,
            cx + dx2, cy + dy2,
            active,
            C_ON, C_GLOW, C_OFF,
        )

# ── colour themes ─────────────────────────────────────────────────────────────

_THEMES = [
    # name, C_SEG_ON,         C_SEG_GLOW,    C_DATE_DIM
    ("teal",  (0, 210, 230),   (0,  80,  90),  (0, 140, 160)),
    ("amber", (0, 180,  60),   (0,  60,  20),  (0, 120,  40)),
    ("blue",  (60, 100, 255),  (20,  40,  90),  (40,  70, 180)),
    ("green", (0, 220,  80),   (0,  80,  30),  (0, 150,  55)),
]

# ── contrast modes ────────────────────────────────────────────────────────────

# Each entry: label, C_SEG_OFF override (None = use default based on theme)
_CONTRAST_MODES = [
    "standard",       # OFF = (0, 35, 42)  teal-ish dim
    "high_contrast",  # OFF = (0, 0, 0)   completely dark
    "low_contrast",   # OFF = (0, 55, 65) brighter inactive
]

# ── VFDRenderer ───────────────────────────────────────────────────────────────

class VFDRenderer:
    """VFD (Vacuum Fluorescent Display) style clock renderer."""

    CANVAS_W = CANVAS_W
    CANVAS_H = CANVAS_H

    def __init__(self) -> None:
        self._font_day  = _find_font(18)
        self._font_date = _find_font(16)

        # Colour palette (mutable via key handlers)
        self._C_BG       = (0,   5,  18)
        self._glow_g     = 80          # green channel of C_SEG_GLOW
        self._theme_idx  = 0
        self._contrast   = 0           # index into _CONTRAST_MODES
        self._bg_blue    = 18          # blue channel of C_BG

    # ── palette helpers ───────────────────────────────────────────────────────

    def _palette(self):
        """Return (C_SEG_ON, C_SEG_GLOW, C_SEG_OFF, C_DATE_DIM)."""
        _, c_on, (_, glow_g_base, glow_b_base), c_date = _THEMES[self._theme_idx]

        # Glow: keep hue proportional but allow green channel tuning
        glow_r = int(c_on[0] * self._glow_g / 210) if c_on[0] else 0
        glow_g = self._glow_g
        glow_b = int(glow_b_base * self._glow_g / 80) if glow_b_base else 0
        c_glow = (glow_r, glow_g, glow_b)

        # OFF colour depends on contrast mode
        if self._contrast == 0:    # standard — dim teal proportional to theme
            off_scale = 0.17
            c_off = (
                int(c_on[0] * off_scale),
                int(c_on[1] * off_scale),
                int(c_on[2] * off_scale),
            )
        elif self._contrast == 1:  # high contrast — fully dark
            c_off = (0, 0, 0)
        else:                       # low contrast — brighter inactive
            off_scale = 0.27
            c_off = (
                int(c_on[0] * off_scale),
                int(c_on[1] * off_scale),
                int(c_on[2] * off_scale),
            )

        return c_on, c_glow, c_off, c_date

    def _bg_color(self) -> tuple:
        return (self._C_BG[0], self._C_BG[1], self._bg_blue)

    # ── layout constants ──────────────────────────────────────────────────────
    # Cell w=42, gap=2 between adjacent cells, colon_w=18
    # Total: 4×42 + 3×2 + 18 = 192px
    # Left margin: (275-192)//2 = 41

    _CELL_W     = 42
    _CELL_H     = 64
    _GAP        = 2
    _COLON_W    = 18
    _MARGIN_L   = 41   # (275 - 192) // 2

    # x origins for each digit cell and colon — spec values:
    #   H1=41  H2=85  colon=129..146  M1=147  M2=191  right=233
    _X_H1  = 41
    _X_H2  = 85
    _X_COL = 129   # colon occupies 129..146 (18px wide)
    _X_M1  = 147
    _X_M2  = 191

    # Vertical position of cell top within time box (y:5..85)
    # TIME_BOX height = 80, cell = 64 → top = 5 + (80-64)//2 = 5+8 = 13
    _CELL_TOP_Y = 13

    # Colon dot x centre
    _COL_DOT_X0 = 133   # _X_COL + (colon_w // 2) - 2 → 129 + 9 - 4 = 134, fine-tuned
    _COL_DOT_X1 = 137

    def __init_layout(self):
        """Recalculate layout constants (called once; values are class-level above)."""
        pass   # layout is fixed; defined as class attrs above

    # ── render ────────────────────────────────────────────────────────────────

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        draw = ImageDraw.Draw(img)
        C_BG = self._bg_color()
        C_ON, C_GLOW, C_OFF, C_DATE = self._palette()

        # Background fill
        draw.rectangle([0, 0, CANVAS_W - 1, CANVAS_H - 1], fill=C_BG)

        # ── 7-segment digits ─────────────────────────────────────────────────
        hour = t.tm_hour
        minute = t.tm_min

        digits = [
            hour   // 10,
            hour   %  10,
            minute // 10,
            minute %  10,
        ]

        xs = [self._X_H1, self._X_H2, self._X_M1, self._X_M2]
        for i, d in enumerate(digits):
            _draw_digit(draw, d, xs[i], self._CELL_TOP_Y, C_ON, C_GLOW, C_OFF)

        # ── colon ────────────────────────────────────────────────────────────
        c_colon = C_ON if (t.tm_sec % 2 == 0) else C_OFF
        col_cx = self._X_COL + self._COLON_W // 2
        draw.rectangle([col_cx - 2, 30, col_cx + 2, 34], fill=c_colon)
        draw.rectangle([col_cx - 2, 50, col_cx + 2, 54], fill=c_colon)

        # ── seconds strip (y=93..105) ────────────────────────────────────────
        for i in range(60):
            x0 = 8 + i * (3 + 1)   # 4px stride
            lit = i < t.tm_sec
            c = C_ON if lit else C_OFF
            draw.rectangle([x0, 93, x0 + 2, 105], fill=c)

        # ── date area (y=115..235) ────────────────────────────────────────────
        _DAY_NAMES = [
            "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
            "FRIDAY", "SATURDAY", "SUNDAY",
        ]
        day_name = _DAY_NAMES[t.tm_wday]
        date_str = f"{t.tm_mday:02d}.{t.tm_mon:02d}.{t.tm_year}"

        draw.text((CENTRE_X, 160), day_name,
                  font=self._font_day, fill=C_ON, anchor="mm")
        draw.text((CENTRE_X, 188), date_str,
                  font=self._font_date, fill=C_DATE, anchor="mm")

    # ── key handler ───────────────────────────────────────────────────────────

    def on_key(self, key: str) -> bool:
        if key == "g":
            self._glow_g = min(120, self._glow_g + 10)
            return True
        elif key == "G" or key == "shift+g":
            self._glow_g = max(20, self._glow_g - 10)
            return True
        elif key == "s":
            self._contrast = (self._contrast + 1) % len(_CONTRAST_MODES)
            return True
        elif key == "c":
            self._theme_idx = (self._theme_idx + 1) % len(_THEMES)
            return True
        elif key == "b":
            self._bg_blue = min(80, self._bg_blue + 5)
            self._C_BG = (self._C_BG[0], self._C_BG[1], self._bg_blue)
            return True
        return False

    # ── help / params ─────────────────────────────────────────────────────────

    def help_text(self) -> str:
        return (
            "g/G=glow brightness  s=segment contrast cycle  "
            "c=colour theme cycle  b=background blue++"
        )

    def param_dict(self) -> dict:
        C_ON, C_GLOW, C_OFF, C_DATE = self._palette()
        return {
            "style":         "vfd",
            "theme":         _THEMES[self._theme_idx][0],
            "contrast_mode": _CONTRAST_MODES[self._contrast],
            "C_BG":          self._bg_color(),
            "C_SEG_ON":      C_ON,
            "C_SEG_GLOW":    C_GLOW,
            "C_SEG_OFF":     C_OFF,
            "C_DATE_DIM":    C_DATE,
            "glow_g":        self._glow_g,
            "bg_blue":       self._bg_blue,
        }


# ── standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = _time.struct_time((2026, 6, 12, 10, 34, 27, 3, 163, 1))
    renderer = VFDRenderer()
    img = Image.new("RGB", (CANVAS_W, CANVAS_H))
    renderer.render(img, t)
    out = "/tmp/vfd_test.png"
    img.save(out)
    print(f"VFDRenderer OK  →  {out}")
