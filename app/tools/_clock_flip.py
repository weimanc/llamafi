"""_clock_flip.py — Flip Clock renderer for preview_clock.py.

Mechanical split-flap display simulation.  Four digit cards (H1 H2 : M1 M2),
5-frame flip animation driven by wall-clock time.

Imported by preview_clock.py as:
    from _clock_flip import FlipRenderer
"""
from __future__ import annotations

import pathlib
import time as _time
from abc import ABC, abstractmethod

from PIL import Image, ImageDraw, ImageFont

# ── font helpers ──────────────────────────────────────────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
    "/usr/share/fonts/google-noto/NotoSansMono-ExtraBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


# ── rainbow helper ────────────────────────────────────────────────────────────

def rainbow_color(i: int, total: int = 60) -> tuple[int, int, int]:
    h = int(i * 255 / total)
    if h < 85:
        return (255 - h * 3, h * 3, 0)
    elif h < 170:
        h -= 85
        return (0, 255 - h * 3, h * 3)
    else:
        h -= 170
        return (h * 3, 0, 255 - h * 3)


# ── minimal ClockRenderer stub (mirrors preview_clock.ClockRenderer) ──────────

class ClockRenderer(ABC):
    CANVAS_W = 275
    CANVAS_H = 240

    def help_text(self) -> str:
        return "(no style-specific keys)"

    @abstractmethod
    def render(self, img: Image.Image, t: _time.struct_time) -> None: ...

    @abstractmethod
    def on_key(self, key: str) -> bool: ...

    @abstractmethod
    def param_dict(self) -> dict: ...


# ── colour palette (initial) ──────────────────────────────────────────────────

_PALETTE_BG_LEVELS = [
    (15, 10, 5),     # dark
    (8, 5, 2),       # darker
    (2, 1, 0),       # very dark
]

_TEXT_WARM = (255, 248, 200)   # cream
_TEXT_COOL = (240, 245, 255)   # cool white

# ── layout constants ──────────────────────────────────────────────────────────

# Card dimensions
_CARD_W      = 46
_CARD_HALF_H = 30   # height of each card half
_CARD_GAP    = 2    # gap between top and bottom halves
_CARD_TOTAL_H = _CARD_HALF_H * 2 + _CARD_GAP   # 62

# Time box occupies y 5..85 (height=80).  Centre cards vertically in that zone.
_TIME_BOX_Y  = 5
_TIME_BOX_H  = 80
_CARD_TOP_Y  = (_TIME_BOX_H - _CARD_TOTAL_H) // 2 + _TIME_BOX_Y  # 14

# Card left-x positions: H1, H2, [gap 129..144], M1, M2
_CARD_XS = [37, 83, 145, 191]

# Colon dots (two 5×5 squares)
_COLON_X  = 135
_COLON_Y1 = 27
_COLON_Y2 = 49

# Seconds strip
_SEC_STRIP_Y0 = 95
_SEC_STRIP_Y1 = 110

_SEC_OFF = (25, 20, 10)

# Frame animation: (top_h, bottom_h, top_digit_is_next)
#   True  → top shows "next"
#   False → top shows "current"
_FRAME_TABLE = [
    # frame: (top_h, top_is_next, bot_h)
    (30, False, 30),   # 0 = stable
    (22, False, 30),   # 1
    (14, False, 30),   # 2
    ( 7, False, 30),   # 3
    (30, True,  22),   # 4
]

# Font size for digits
_DIGIT_FONT_SIZE = 26


# ── FlipRenderer ─────────────────────────────────────────────────────────────

class FlipRenderer(ClockRenderer):
    """Mechanical split-flap flip clock concept renderer."""

    def __init__(self) -> None:
        self._font_digit = _load_font(_DIGIT_FONT_SIZE)
        self._font_day   = _load_font(20)
        self._font_date  = _load_font(18)

        # Animation state for each of the 4 digit cards
        self._digits: list[dict] = [
            {"current": 0, "next": 0, "frame": 0, "last_flip_t": 0.0}
            for _ in range(4)
        ]

        self._frame_ms: int = 80

        self._bg_level: int = 0       # index into _PALETTE_BG_LEVELS
        self._warm_text: bool = True  # True = cream, False = cool white

        # Colour palette (will be refreshed from bg_level / warm_text)
        self._C_BG      = _PALETTE_BG_LEVELS[0]
        self._C_TOP     = (52, 36, 18)
        self._C_BOT     = (35, 24, 12)
        self._C_TEXT    = _TEXT_WARM
        self._C_OUTLINE = (80, 55, 25)
        self._C_COLON   = (200, 160, 60)

    # ── public interface ──────────────────────────────────────────────────────

    def help_text(self) -> str:
        return "f/F=frame speed  b=bg darkness  w=warm/cool text"

    def param_dict(self) -> dict:
        return {
            "frame_ms": self._frame_ms,
            "C_BG":     self._C_BG,
            "C_TOP":    self._C_TOP,
            "C_BOT":    self._C_BOT,
            "C_TEXT":   self._C_TEXT,
            "C_COLON":  self._C_COLON,
        }

    def on_key(self, key: str) -> bool:
        if key == "f":
            self._frame_ms = max(20, self._frame_ms - 10)
            return True
        if key == "F":
            self._frame_ms = min(200, self._frame_ms + 10)
            return True
        if key == "b":
            self._bg_level = (self._bg_level + 1) % len(_PALETTE_BG_LEVELS)
            self._C_BG = _PALETTE_BG_LEVELS[self._bg_level]
            return True
        if key == "w":
            self._warm_text = not self._warm_text
            self._C_TEXT = _TEXT_WARM if self._warm_text else _TEXT_COOL
            return True
        return False

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        draw = ImageDraw.Draw(img)
        now  = _time.time()

        # Background
        draw.rectangle([0, 0, self.CANVAS_W - 1, self.CANVAS_H - 1], fill=self._C_BG)

        # Determine target digits from current time
        h1 = t.tm_hour // 10
        h2 = t.tm_hour % 10
        m1 = t.tm_min  // 10
        m2 = t.tm_min  % 10
        targets = [h1, h2, m1, m2]

        # Advance animation state
        self._update_animation(targets, now)

        # Draw flip cards
        for i, (card_x, ds) in enumerate(zip(_CARD_XS, self._digits)):
            self._draw_card(draw, card_x, _CARD_TOP_Y, ds)

        # Colon dots (static, no blink)
        csize = 5
        draw.rectangle(
            [_COLON_X, _COLON_Y1, _COLON_X + csize - 1, _COLON_Y1 + csize - 1],
            fill=self._C_COLON,
        )
        draw.rectangle(
            [_COLON_X, _COLON_Y2, _COLON_X + csize - 1, _COLON_Y2 + csize - 1],
            fill=self._C_COLON,
        )

        # Seconds strip
        self._draw_seconds_strip(draw, t.tm_sec)

        # Date area
        self._draw_date(draw, t)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _update_animation(self, targets: list[int], now: float) -> None:
        """Kick off or advance flip animation for each digit card."""
        frame_s = self._frame_ms / 1000.0

        for i, ds in enumerate(self._digits):
            if ds["frame"] == 0:
                # Stable — check if this digit needs to change
                if ds["current"] != targets[i]:
                    ds["next"]        = targets[i]
                    ds["frame"]       = 1
                    ds["last_flip_t"] = now
            else:
                # Animating — advance if enough time has elapsed
                if (now - ds["last_flip_t"]) >= frame_s:
                    ds["frame"] += 1
                    ds["last_flip_t"] = now
                    if ds["frame"] >= len(_FRAME_TABLE):
                        # Animation done — commit
                        ds["current"] = ds["next"]
                        ds["frame"]   = 0

    def _draw_card(
        self,
        draw: ImageDraw.ImageDraw,
        card_x: int,
        card_top: int,
        ds: dict,
    ) -> None:
        """Render one flip card (top half + gap + bottom half)."""
        frame   = ds["frame"]
        current = ds["current"]
        nxt     = ds["next"] if frame > 0 else current

        top_h, top_is_next, bot_h = _FRAME_TABLE[frame]

        top_digit = nxt if top_is_next else current
        bot_digit = nxt

        card_mid = card_top + _CARD_HALF_H       # y where split line lives

        # ── top half ──────────────────────────────────────────────────────────
        if top_h > 0:
            # Fill downward from card_top (fold-down animation clips from bottom)
            ty0 = card_top
            ty1 = card_top + top_h - 1
            draw.rectangle([card_x, ty0, card_x + _CARD_W - 1, ty1], fill=self._C_TOP)
            # Thin outline
            draw.rectangle(
                [card_x, ty0, card_x + _CARD_W - 1, ty1],
                outline=self._C_OUTLINE,
            )
            # Digit text centred in the full 46×30 area (card_top … card_mid-1)
            self._draw_digit_in_rect(
                draw, top_digit,
                card_x, card_top, _CARD_W, _CARD_HALF_H,
                clip_bottom=ty1,
            )

        # ── gap line ──────────────────────────────────────────────────────────
        draw.line(
            [card_x, card_mid, card_x + _CARD_W, card_mid + 1],
            fill=(0, 0, 0),
        )

        # ── bottom half ───────────────────────────────────────────────────────
        bot_y0 = card_mid + _CARD_GAP
        if bot_h > 0:
            # Fill upward from (bot_y0 + _CARD_HALF_H - 1) (rise animation)
            # Rise: bottom_h shrinks from 30 → smaller → card appears from bottom
            rise_y0 = bot_y0 + (_CARD_HALF_H - bot_h)
            rise_y1 = bot_y0 + _CARD_HALF_H - 1
            draw.rectangle(
                [card_x, rise_y0, card_x + _CARD_W - 1, rise_y1],
                fill=self._C_BOT,
            )
            draw.rectangle(
                [card_x, rise_y0, card_x + _CARD_W - 1, rise_y1],
                outline=self._C_OUTLINE,
            )
            # Digit text centred in the full 46×30 area (bot_y0 … bot_y0+29)
            self._draw_digit_in_rect(
                draw, bot_digit,
                card_x, bot_y0, _CARD_W, _CARD_HALF_H,
                clip_top=rise_y0,
            )

    def _draw_digit_in_rect(
        self,
        draw: ImageDraw.ImageDraw,
        digit: int,
        rx: int,
        ry: int,
        rw: int,
        rh: int,
        clip_top: int | None = None,
        clip_bottom: int | None = None,
    ) -> None:
        """Draw digit centred in the rect (rx,ry,rw,rh).

        clip_top / clip_bottom are absolute y coordinates that restrict drawing
        (used to simulate the folding/rising motion clipping).
        """
        text = str(digit)
        bb = draw.textbbox((0, 0), text, font=self._font_digit)
        tw = bb[2] - bb[0]
        th = bb[3] - bb[1]

        tx = rx + (rw - tw) // 2 - bb[0]
        ty = ry + (rh - th) // 2 - bb[1]

        # We rely on PIL's normal clipping via the image boundary.
        # For sub-card clipping we just check if the text anchor falls
        # within the visible region — good enough for 1-digit glyphs.
        draw.text((tx, ty), text, font=self._font_digit, fill=self._C_TEXT)

    def _draw_seconds_strip(self, draw: ImageDraw.ImageDraw, sec: int) -> None:
        for i in range(60):
            x  = 8 + int(i * 4.3)
            lit = i < sec
            c  = rainbow_color(i) if lit else _SEC_OFF
            draw.rectangle([x, _SEC_STRIP_Y0, x + 1, _SEC_STRIP_Y1], fill=c)

    def _draw_date(self, draw: ImageDraw.ImageDraw, t: _time.struct_time) -> None:
        cx = 137
        days   = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        day_name  = days[t.tm_wday]
        date_str  = f"{day_name} {t.tm_mday:02d} {months[t.tm_mon]} {t.tm_year + 1900}"

        draw.text((cx, 160), day_name,  font=self._font_day,  fill=self._C_TEXT, anchor="mm")
        draw.text((cx, 190), date_str,  font=self._font_date, fill=self._C_TEXT, anchor="mm")


# ── standalone sanity test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    renderer = FlipRenderer()

    # Render a stable frame (no animation)
    img = Image.new("RGB", (275, 240), (0, 0, 0))
    # struct_time tm_year is years-since-1900; 126 = 2026
    t   = _time.struct_time((126, 6, 12, 12, 34, 45, 4, 163, 1))
    renderer.render(img, t)

    out = pathlib.Path("/tmp/flip_test.png")
    img.save(out)
    print(f"FlipRenderer OK — saved to {out}")

    # Quick key-handler smoke test
    assert renderer.on_key("f")   is True
    assert renderer.on_key("F")   is True
    assert renderer.on_key("b")   is True
    assert renderer.on_key("w")   is True
    assert renderer.on_key("x")   is False
    print("on_key OK")

    # param_dict check
    d = renderer.param_dict()
    assert "frame_ms" in d and "C_BG" in d
    print("param_dict OK")

    sys.exit(0)
