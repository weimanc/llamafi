"""_clock_nixie.py — Nixie Tube clock renderer for preview_clock.py.

Imported by preview_clock.py as _clock_nixie; exposes NixieRenderer.
PIL only (no pygame). Standalone — no project imports.

Test:
    python3 app/tools/_clock_nixie.py   →  /tmp/nixie_test.png
"""
from __future__ import annotations

import pathlib
import random
import time as _time
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

# ── colour palette ────────────────────────────────────────────────────────────

C_BG          = (0, 0, 0)
C_GLOW_OUTER  = (40, 10, 0)
C_GLOW_MID    = (80, 20, 0)
C_TUBE_BORDER = (200, 100, 20)
C_TUBE_FILL   = (8, 3, 0)
C_DIGIT       = (255, 230, 160)
C_COLON       = (200, 120, 30)
C_DATE        = (200, 130, 40)
C_DATE_SUB    = (160, 100, 30)

# Tube border colour presets cycled by 'c'
_BORDER_PRESETS: list[Tuple[int, int, int]] = [
    (200, 100,  20),   # amber
    (220,  60,  10),   # orange-red
    (200, 170,  20),   # gold
    (230, 200, 160),   # warm white
]

# Background presets cycled by 'b'
_BG_PRESETS: list[Tuple[int, int, int]] = [
    (0,   0,   0),    # black
    (8,   4,   0),    # very dark brown
    (0,   0,  12),    # very dark navy
]

# ── font loader ───────────────────────────────────────────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
    "/usr/share/fonts/google-noto/NotoSansMono-ExtraBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


# ── rainbow helper ────────────────────────────────────────────────────────────

def rainbow_color(i: int, total: int = 60) -> Tuple[int, int, int]:
    h = int(i * 255 / total)
    if h < 85:
        return (255 - h * 3, h * 3, 0)
    elif h < 170:
        h -= 85
        return (0, 255 - h * 3, h * 3)
    else:
        h -= 170
        return (h * 3, 0, 255 - h * 3)


# ── layout constants ──────────────────────────────────────────────────────────

CANVAS_W = 275
CANVAS_H = 240

TUBE_W  = 48
TUBE_H  = 70
TUBE_R  = 24   # corner radius (makes it oval-like)

# Tube top-y: centres the 70px tube in a 80px time area with 5px top margin
TUBE_TOP_Y = (80 - TUBE_H) // 2 + 5    # = 10

# Tube left-x positions
TUBE_X: dict[str, int] = {
    "H1": 34,
    "H2": 86,
    "M1": 141,
    "M2": 193,
}

COLON_X = 137   # x of colon dots
COLON_Y1 = 33
COLON_Y2 = 57

SEC_DOT_Y   = 94   # vertical centre of seconds dots
SEC_DOT_X0  =  8
SEC_DOT_X1  = 263
SEC_DOT_SPAN = SEC_DOT_X1 - SEC_DOT_X0   # 255 px for 59 gaps

DATE_DAY_Y  = 155
DATE_DATE_Y = 185

DAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ── NixieRenderer ─────────────────────────────────────────────────────────────

class NixieRenderer:
    """Warm vintage Nixie Tube clock, PIL-only, for preview_clock.py."""

    CANVAS_W = CANVAS_W
    CANVAS_H = CANVAS_H

    def __init__(self) -> None:
        self._font_digit = _load_font(42)
        self._font_day   = _load_font(20)
        self._font_date  = _load_font(18)

        # mutable palette state
        self._c_bg          = _BG_PRESETS[0]
        self._c_glow_outer  = C_GLOW_OUTER
        self._c_glow_mid    = list(C_GLOW_MID)    # list so R is mutable
        self._c_tube_border = _BORDER_PRESETS[0]
        self._c_tube_fill   = C_TUBE_FILL
        self._c_digit       = list(C_DIGIT)

        self._border_preset_idx = 0
        self._bg_preset_idx     = 0

        self._flicker_on = True
        self._flicker: float = 1.0

    # ── public interface ──────────────────────────────────────────────────────

    def help_text(self) -> str:
        return (
            "g/G=glow up/down  c=cycle tube colour  "
            "v=toggle flicker  b=cycle background"
        )

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        """Fill 275×240 canvas with Nixie tube clock for time t."""
        draw = ImageDraw.Draw(img)

        # background
        draw.rectangle([0, 0, CANVAS_W - 1, CANVAS_H - 1], fill=self._c_bg)

        # flicker update
        if self._flicker_on:
            self._flicker = 0.9 + random.random() * 0.15
        else:
            self._flicker = 1.0

        # tubes
        digits = [
            ("H1", f"{t.tm_hour:02d}"[0]),
            ("H2", f"{t.tm_hour:02d}"[1]),
            ("M1", f"{t.tm_min:02d}"[0]),
            ("M2", f"{t.tm_min:02d}"[1]),
        ]
        for slot, ch in digits:
            self._draw_tube(draw, TUBE_X[slot], TUBE_TOP_Y, ch)

        # colon
        R = 4
        draw.ellipse([COLON_X - R, COLON_Y1 - R, COLON_X + R, COLON_Y1 + R],
                     fill=C_COLON)
        draw.ellipse([COLON_X - R, COLON_Y2 - R, COLON_X + R, COLON_Y2 + R],
                     fill=C_COLON)

        # seconds dot arc
        for i in range(60):
            x = SEC_DOT_X0 + int(i * (SEC_DOT_SPAN / 59))
            lit = i < t.tm_sec
            c = (200, 100, 20) if lit else (40, 15, 0)
            draw.ellipse([x - 1, SEC_DOT_Y - 1, x + 1, SEC_DOT_Y + 1], fill=c)

        # date area
        centre_x = CANVAS_W // 2   # 137

        # day name
        day_name = DAYS_LONG[t.tm_wday]
        draw.text(
            (centre_x, DATE_DAY_Y),
            day_name,
            font=self._font_day,
            fill=C_DATE,
            anchor="mm",
        )

        # date string e.g. "12 Jun 2026"
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        date_str = f"{t.tm_mday:02d} {months[t.tm_mon - 1]} {t.tm_year}"
        draw.text(
            (centre_x, DATE_DATE_Y),
            date_str,
            font=self._font_date,
            fill=C_DATE_SUB,
            anchor="mm",
        )

    def on_key(self, key: str) -> bool:
        """Handle a style-specific keypress.  Return True if redraw needed."""
        if key == "g":
            self._c_glow_mid[0] = min(150, self._c_glow_mid[0] + 10)
            return True
        elif key == "G":
            self._c_glow_mid[0] = max(20, self._c_glow_mid[0] - 10)
            return True
        elif key == "c":
            self._border_preset_idx = (self._border_preset_idx + 1) % len(_BORDER_PRESETS)
            self._c_tube_border = _BORDER_PRESETS[self._border_preset_idx]
            return True
        elif key == "v":
            self._flicker_on = not self._flicker_on
            return True
        elif key == "b":
            self._bg_preset_idx = (self._bg_preset_idx + 1) % len(_BG_PRESETS)
            self._c_bg = _BG_PRESETS[self._bg_preset_idx]
            return True
        return False

    def param_dict(self) -> dict:
        return {
            "c_bg":           self._c_bg,
            "c_glow_outer":   tuple(self._c_glow_outer),
            "c_glow_mid":     tuple(self._c_glow_mid),
            "c_tube_border":  self._c_tube_border,
            "c_tube_fill":    self._c_tube_fill,
            "c_digit":        tuple(self._c_digit),
            "flicker_on":     self._flicker_on,
            "border_preset":  self._border_preset_idx,
            "bg_preset":      self._bg_preset_idx,
        }

    # ── private helpers ───────────────────────────────────────────────────────

    def _draw_tube(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        ch: str,
    ) -> None:
        """Draw a single Nixie tube with digit ch at top-left (x, y)."""
        # bounding rect
        x0, y0 = x, y
        x1, y1 = x + TUBE_W - 1, y + TUBE_H - 1
        cx = x0 + TUBE_W // 2
        cy = y0 + TUBE_H // 2

        # Layer 0: outer dark halo (expanded 4 px each side)
        draw.rounded_rectangle(
            [x0 - 4, y0 - 4, x1 + 4, y1 + 4],
            radius=TUBE_R + 4,
            fill=tuple(self._c_glow_outer),
        )

        # Layer 1: glow ring (expanded 2 px)
        draw.rounded_rectangle(
            [x0 - 2, y0 - 2, x1 + 2, y1 + 2],
            radius=TUBE_R + 2,
            fill=tuple(self._c_glow_mid),
        )

        # Layer 2: tube border + fill
        draw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=TUBE_R,
            outline=self._c_tube_border,
            width=2,
            fill=self._c_tube_fill,
        )

        # Layer 3: digit text with flicker
        f = self._flicker
        dc = (
            int(self._c_digit[0] * f),
            int(self._c_digit[1] * f),
            int(self._c_digit[2] * f),
        )
        # clamp to valid range
        dc = (min(255, dc[0]), min(255, dc[1]), min(255, dc[2]))

        draw.text(
            (cx, cy),
            ch,
            font=self._font_digit,
            fill=dc,
            anchor="mm",
        )

        # pin shadow: two narrow dark rects at tube bottom-inside
        shadow_y0 = y1 - 8
        shadow_y1 = y1 - 4
        shadow_c  = (4, 1, 0)
        draw.rectangle([cx - 8, shadow_y0, cx - 6, shadow_y1], fill=shadow_c)
        draw.rectangle([cx + 6, shadow_y0, cx + 8, shadow_y1], fill=shadow_c)


# ── standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    r = NixieRenderer()

    # Use a representative time: 10:08:37 on a Thursday
    t = time.struct_time((2026, 6, 12, 10, 8, 37, 3, 163, 1))

    img = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    r.render(img, t)
    out = "/tmp/nixie_test.png"
    img.save(out)
    print(f"NixieRenderer OK  →  {out}")
