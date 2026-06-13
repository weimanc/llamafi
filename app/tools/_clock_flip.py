"""_clock_flip.py — Flip Clock renderer for preview_clock.py.

Mechanical split-flap display simulation.  Four digit cards (H1 H2 : M1 M2),
5-frame flip animation driven by wall-clock time.

Rendering model (per M-CLOCK-FLIP.md):
  - Each card has a top half and bottom half separated by a thin split line.
  - Bottom plate always shows the *new* digit (swapped at animation start).
  - Top flap falls (shrinks toward centre) then new top rises.
  - Cards: dark-grey rounded rectangles; top half slightly lighter than bottom.

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
    "/usr/share/fonts/google-roboto/Roboto-Black.ttf",        # preferred — bold, clean 0
    "/usr/share/fonts/google-noto/NotoSans-ExtraBold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
]

_DATE_FONT_PATHS = [
    "/usr/share/fonts/google-roboto/Roboto-Regular.ttf",      # lighter weight for date
    "/usr/share/fonts/open-sans/OpenSans-Regular.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
]


def _load_date_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _DATE_FONT_PATHS:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


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


# ── colour palette ────────────────────────────────────────────────────────────

# Background levels (b key cycles)
_BG_LEVELS = [
    (10, 10, 12),   # near-black housing (default) — cards stand out clearly
    (18, 18, 20),   # dark charcoal
    (28, 26, 24),   # warm dark
]

# Card colours — noticeably lighter than the housing
_C_TOP_DEFAULT     = (55, 55, 62)   # top half
_C_BOT_DEFAULT     = (40, 40, 46)   # bottom half — slightly darker for depth
_C_OUTLINE_DEFAULT = (75, 75, 88)   # card border
# Split: hinge groove is the darkest element — shadowed recess between the two flaps
_C_SPLIT_EDGE_TOP = (18, 18, 20)    # 1px shadow at base of top flap
_C_SPLIT_GAP      = ( 5,  5,  6)    # very dark groove — clearly different from BG
_C_SPLIT_EDGE_BOT = (72, 72, 84)    # 1px highlight at crown of bottom plate

# Text / colon
_C_TEXT_DEFAULT   = (242, 242, 235)  # warm white
_C_COLON_DEFAULT  = (230, 230, 222)  # bright warm white — prominent dots

# ── layout constants ──────────────────────────────────────────────────────────

_CARD_W       = 56    # card width (px)
_CARD_HALF_H  = 38    # height of each card half (px)
_CARD_GAP     = 2     # hinge gap (px)
_CARD_TOTAL_H = _CARD_HALF_H * 2 + _CARD_GAP   # 78
_CARD_R       = 6     # corner radius

# 4 × 56 + inner gaps(4 px × 2) + colon gutter(18) = 250 px; margins 12 px each side
_CARD_XS  = [13, 73, 147, 207]   # left-x of H1, H2, M1, M2
_COLON_CX = (73 + 56 + 147) // 2   # x-centre of colon gap → 138
_COLON_R  = 8   # half-side of colon dot square (16×16 px dots)

# Cards sit near the top; date centred in the lower half
_CARD_Y   = 8

# Colon dots centred in each card half
_COLON_Y1 = _CARD_Y + _CARD_HALF_H // 2
_COLON_Y2 = _CARD_Y + _CARD_HALF_H + _CARD_GAP + _CARD_HALF_H // 2

# Date text — pushed into the lower third of the canvas for visual balance
_DATE_Y   = 155

# Font size for card digits — Roboto-Black is compact; 40pt fills the half-card well
_DIGIT_FONT_SIZE = 40

# Frame animation table: (top_flap_h, top_shows_next, bot_h)
_FRAME_TABLE = [
    (38, False, 38),   # 0 = stable
    (27, False, 38),   # 1 — flap falling, old top
    (14, False, 38),   # 2
    ( 4, False, 38),   # 3 — near edge-on
    (38, True,  27),   # 4 — new top rising
]


# ── FlipRenderer ─────────────────────────────────────────────────────────────

class FlipRenderer(ClockRenderer):
    """Mechanical split-flap flip clock concept renderer."""

    def __init__(self) -> None:
        self._font_digit = _load_font(_DIGIT_FONT_SIZE)
        self._font_date  = _load_date_font(14)

        # Per-card animation state
        self._digits: list[dict] = [
            {"current": 0, "next": 0, "frame": 0, "last_flip_t": 0.0}
            for _ in range(4)
        ]

        self._frame_ms: int = 80
        self._bg_idx: int   = 0

        self._C_BG      = _BG_LEVELS[0]
        self._C_TOP     = _C_TOP_DEFAULT
        self._C_BOT     = _C_BOT_DEFAULT
        self._C_OUTLINE = _C_OUTLINE_DEFAULT
        # split line colours are module-level constants, not instance state
        self._C_TEXT    = _C_TEXT_DEFAULT
        self._C_COLON   = _C_COLON_DEFAULT

    # ── public interface ──────────────────────────────────────────────────────

    def help_text(self) -> str:
        return "f/F=frame speed  b=bg darkness"

    def param_dict(self) -> dict:
        return {
            "CARD_W": _CARD_W, "CARD_HALF_H": _CARD_HALF_H,
            "CARD_GAP": _CARD_GAP, "CARD_R": _CARD_R,
            "frame_ms": self._frame_ms,
            "C_BG":     self._C_BG,
            "C_TOP":    self._C_TOP,
            "C_BOT":    self._C_BOT,
            "C_OUTLINE": self._C_OUTLINE,
            "C_TEXT":   self._C_TEXT,
            "C_COLON":  self._C_COLON,
        }

    def on_key(self, key: str) -> bool:
        if key == "f":
            self._frame_ms = max(20, self._frame_ms - 10)
            return True
        if key in ("F", "shift+f"):
            self._frame_ms = min(200, self._frame_ms + 10)
            return True
        if key == "b":
            self._bg_idx = (self._bg_idx + 1) % len(_BG_LEVELS)
            self._C_BG   = _BG_LEVELS[self._bg_idx]
            return True
        return False

    # ── render ────────────────────────────────────────────────────────────────

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        draw = ImageDraw.Draw(img)
        now  = _time.time()

        # Background
        draw.rectangle([0, 0, self.CANVAS_W - 1, self.CANVAS_H - 1],
                       fill=self._C_BG)

        # Resolve target digits
        targets = [t.tm_hour // 10, t.tm_hour % 10,
                   t.tm_min  // 10, t.tm_min  % 10]

        self._update_animation(targets, now)

        # Draw cards
        for card_x, ds in zip(_CARD_XS, self._digits):
            self._draw_card(draw, card_x, _CARD_Y, ds)

        # Colon dots
        for cy in (_COLON_Y1, _COLON_Y2):
            draw.rectangle(
                [_COLON_CX - _COLON_R, cy - _COLON_R,
                 _COLON_CX + _COLON_R - 1, cy + _COLON_R - 1],
                fill=self._C_COLON,
            )

        # Date line
        self._draw_date(draw, t)

    # ── animation ─────────────────────────────────────────────────────────────

    def _update_animation(self, targets: list[int], now: float) -> None:
        frame_s = self._frame_ms / 1000.0
        for i, ds in enumerate(self._digits):
            if ds["frame"] == 0:
                if ds["current"] != targets[i]:
                    ds["next"]        = targets[i]
                    ds["frame"]       = 1
                    ds["last_flip_t"] = now
            else:
                if (now - ds["last_flip_t"]) >= frame_s:
                    ds["frame"] += 1
                    ds["last_flip_t"] = now
                    if ds["frame"] >= len(_FRAME_TABLE):
                        ds["current"] = ds["next"]
                        ds["frame"]   = 0

    # ── card drawing ──────────────────────────────────────────────────────────

    def _draw_card(self, draw: ImageDraw.ImageDraw,
                   cx: int, cy: int, ds: dict) -> None:
        """Render one flip card according to M-CLOCK-FLIP.md pipeline."""
        frame   = ds["frame"]
        current = ds["current"]
        nxt     = ds["next"] if frame > 0 else current

        top_h, top_is_next, bot_h = _FRAME_TABLE[frame]
        top_digit = nxt if top_is_next else current
        bot_digit = nxt

        W  = _CARD_W
        H  = _CARD_TOTAL_H
        HH = _CARD_HALF_H
        G  = _CARD_GAP
        R  = _CARD_R
        mid_y = cy + HH  # y of the hinge gap top edge

        # ── 1. Card background ────────────────────────────────────────────────
        # Top half: TL + TR rounded, BR + BL square (flat at split)
        draw.rounded_rectangle(
            [cx, cy, cx + W - 1, mid_y - 1], radius=R, fill=self._C_TOP,
            corners=(True, True, False, False))
        # Bottom half: BL + BR rounded, TL + TR square (flat at split)
        draw.rounded_rectangle(
            [cx, mid_y + G, cx + W - 1, cy + H - 1], radius=R, fill=self._C_BOT,
            corners=(False, False, True, True))
        # Card border — full card outline (drawn before gap so gap shows inside it)
        draw.rounded_rectangle(
            [cx, cy, cx + W - 1, cy + H - 1],
            radius=R, outline=self._C_OUTLINE, width=1)
        # Hinge gap: inset 1px so the card outline remains visible on left/right edges
        draw.rectangle(
            [cx + 1, mid_y, cx + W - 2, mid_y + G - 1], fill=_C_SPLIT_GAP)

        # ── 2. Bottom plate (always new digit, static once anim starts) ───────
        # Digit centered across the FULL card height so the split lands at the
        # digit's natural midpoint — only the bottom half is clipped in.
        if bot_h > 0:
            bot_y0 = mid_y + G
            bot_y1 = bot_y0 + HH - 1
            reveal_top = bot_y1 - bot_h + 1
            draw.rectangle(
                [cx + 1, reveal_top, cx + W - 2, bot_y1], fill=self._C_BOT)
            self._draw_digit_clipped(
                draw, bot_digit,
                cx, cy, W, H, self._C_BOT,   # ref = full card
                clip_y0=reveal_top, clip_y1=bot_y1,
            )

        # ── 3. Top flap (falls from full → 0, then new digit rises) ──────────
        # Same full-card reference so the top half of the digit aligns with the
        # bottom half above.
        if top_h > 0:
            flap_y0 = cy
            flap_y1 = cy + top_h - 1
            draw.rectangle(
                [cx + 1, flap_y0, cx + W - 2, flap_y1], fill=self._C_TOP)
            self._draw_digit_clipped(
                draw, top_digit,
                cx, cy, W, H, self._C_TOP,   # ref = full card
                clip_y0=flap_y0, clip_y1=flap_y1,
            )

        # ── 4. Drop shadow on bottom plate (phase 1 — flap falling) ──────────
        if frame > 0 and not top_is_next and top_h > 0:
            shadow_h  = max(2, top_h // 4)
            shadow_y0 = mid_y + G
            shadow_y1 = min(shadow_y0 + shadow_h, cy + H - 1)
            draw.rectangle(
                [cx + 1, shadow_y0, cx + W - 2, shadow_y1], fill=(0, 0, 0))

        # ── 5. Layered split — inset 1px to keep card outline on left/right ─────
        # shadow at base of top flap
        draw.rectangle([cx + 1, mid_y - 1, cx + W - 2, mid_y - 1],
                       fill=_C_SPLIT_EDGE_TOP)
        # groove fill
        draw.rectangle([cx + 1, mid_y,     cx + W - 2, mid_y + G - 1],
                       fill=_C_SPLIT_GAP)
        # highlight at crown of bottom plate
        draw.rectangle([cx + 1, mid_y + G - 1, cx + W - 2, mid_y + G - 1],
                       fill=_C_SPLIT_EDGE_BOT)

    def _draw_digit_clipped(
        self,
        draw: ImageDraw.ImageDraw,
        digit: int,
        rect_x: int, rect_y: int, rect_w: int, rect_h: int,
        bg_colour: tuple,
        clip_y0: int, clip_y1: int,
    ) -> None:
        """Draw digit centred in (rect_x, rect_y, rect_w, rect_h), clipped to clip_y0..clip_y1."""
        if clip_y1 < clip_y0:
            return

        text = str(digit)
        bb   = draw.textbbox((0, 0), text, font=self._font_digit)
        tw   = bb[2] - bb[0]
        th   = bb[3] - bb[1]
        tx   = rect_x + (rect_w - tw) // 2 - bb[0]
        ty   = rect_y + (rect_h - th) // 2 - bb[1]

        tmp   = Image.new("RGB", (rect_w, rect_h), bg_colour)
        tmp_d = ImageDraw.Draw(tmp)
        tmp_d.text((tx - rect_x, ty - rect_y), text,
                   font=self._font_digit, fill=self._C_TEXT)

        src_y0 = max(0, clip_y0 - rect_y)
        src_y1 = min(rect_h - 1, clip_y1 - rect_y)
        if src_y1 < src_y0:
            return

        strip = tmp.crop((0, src_y0, rect_w, src_y1 + 1))
        img   = draw._image  # type: ignore[attr-defined]
        img.paste(strip, (rect_x, rect_y + src_y0))

    # ── secondary elements ────────────────────────────────────────────────────

    def _draw_date(self, draw: ImageDraw.ImageDraw, t: _time.struct_time) -> None:
        _DAYS   = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        _MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        s = f"{_DAYS[t.tm_wday]}  {t.tm_mday:02d} {_MONTHS[t.tm_mon - 1]} {t.tm_year}"
        c_date = tuple(int(v * 0.82) for v in self._C_TEXT)  # ~18% dimmer than digits
        draw.text((137, _DATE_Y), s, font=self._font_date,
                  fill=c_date, anchor="mt")


# ── standalone sanity test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    renderer = FlipRenderer()
    img = Image.new("RGB", (275, 240), (0, 0, 0))
    t   = _time.localtime()
    renderer.render(img, t)

    out = pathlib.Path("/tmp/flip_test.png")
    img.save(out)
    print(f"FlipRenderer OK — saved to {out}")

    assert renderer.on_key("f")  is True
    assert renderer.on_key("F")  is True
    assert renderer.on_key("b")  is True
    assert renderer.on_key("x")  is False
    print("on_key OK")

    d = renderer.param_dict()
    assert "frame_ms" in d and "C_BG" in d
    print("param_dict OK")

    sys.exit(0)
