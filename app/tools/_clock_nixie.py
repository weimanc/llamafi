"""_clock_nixie.py — Nixie Tube renderer for preview_clock.py.

Vacuum-tube Nixie simulation (per M-CLOCK-NIXIE.md):
  - Each digit inside a tall dark rounded-rect tube with hex mesh anode texture.
  - Thin wire cathode glyph (Roboto-Thin) at near-white warm base colour.
  - Three-pass additive bloom: tight corona + orange cloud + wide ambient.
  - Outer glow bleeds past the tube glass onto the black canvas.
  - Ghost cathodes (all inactive digits dim) toggled with 'h'.

Imported by preview_clock.py as:
    from _clock_nixie import NixieRenderer
"""
from __future__ import annotations

import math
import pathlib
import time as _time
from abc import ABC, abstractmethod

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ── font helpers ───────────────────────────────────────────────────────────────

_WIRE_FONT_PATHS = [
    "/usr/share/fonts/google-roboto/Roboto-Thin.ttf",
    "/usr/share/fonts/google-roboto/Roboto-Light.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Light.ttf",
    "/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Thin.otf",
]
_DATE_FONT_PATHS = [
    "/usr/share/fonts/google-roboto/Roboto-Thin.ttf",
    "/usr/share/fonts/google-roboto/Roboto-Light.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Light.ttf",
]


def _load_font(paths: list, size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


# ── ClockRenderer stub ─────────────────────────────────────────────────────────

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


# ── colour themes ──────────────────────────────────────────────────────────────

_THEMES = [
    {"name": "amber", "C_WIRE": (255, 125,   8)},   # warm orange — matches concept
    {"name": "red",   "C_WIRE": (255,  45,  10)},
    {"name": "green", "C_WIRE": ( 50, 255,  80)},
    {"name": "blue",  "C_WIRE": ( 70, 150, 255)},
]

# ── layout constants ───────────────────────────────────────────────────────────

TUBE_W = 48
TUBE_H = 110
TUBE_R = 18

TUBE_Y = 8

_TUBE_GAP   = 6
_COLON_W    = 22
_MARGIN_X   = (275 - 4 * TUBE_W - 2 * _TUBE_GAP - _COLON_W) // 2  # 24

TUBE_XS = [
    _MARGIN_X,                                          # H1 = 24
    _MARGIN_X + TUBE_W + _TUBE_GAP,                    # H2 = 78
    _MARGIN_X + 2 * TUBE_W + _TUBE_GAP + _COLON_W,    # M1 = 148
    _MARGIN_X + 3 * TUBE_W + 2 * _TUBE_GAP + _COLON_W, # M2 = 202
]
COLON_CX = TUBE_XS[1] + TUBE_W + _COLON_W // 2        # 137

DATE_Y = TUBE_Y + TUBE_H + 22   # 124

# Bloom defaults (tunable via keys)
_BLOOM_R1 = 2.5   # tight corona
_BLOOM_R2 = 8.0   # orange cloud
_BLOOM_R3 = 18.0  # wide ambient
_BLOOM_S1 = 1.8
_BLOOM_S2 = 1.2
_BLOOM_S3 = 0.7
_BLEED_R  = 10.0
_BLEED_S  = 0.45

# Colon afterglow: fast ramp-up, slow exponential decay
_COLON_RAMP_MS  = 80    # ms to reach full brightness on turn-on
_COLON_DECAY_MS = 500   # ms time constant tau for exponential decay on turn-off


# ── tube mask ──────────────────────────────────────────────────────────────────

def _build_tube_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask


_TUBE_MASK = _build_tube_mask(TUBE_W, TUBE_H, TUBE_R)


# ── hex mesh texture ───────────────────────────────────────────────────────────

def _build_mesh(w: int, h: int, c_wire: tuple) -> Image.Image:
    mesh = Image.new("RGB", (w, h), (0, 0, 0))
    d    = ImageDraw.Draw(mesh)
    mc   = tuple(max(1, int(v * 0.075)) for v in c_wire)
    cell = 4
    dot  = 1
    for row in range(h // cell + 2):
        for col in range(w // cell + 2):
            ox = (row % 2) * (cell // 2)
            cx = col * cell + ox
            cy = row * cell
            d.rectangle([cx - dot, cy - dot, cx + dot, cy + dot], fill=mc)
    return mesh


# ── NixieRenderer ─────────────────────────────────────────────────────────────

class NixieRenderer(ClockRenderer):
    """Vacuum-tube Nixie clock concept renderer."""

    def __init__(self) -> None:
        self._theme_idx  = 0
        self._wire_size  = 88
        self._font_wire  = _load_font(_WIRE_FONT_PATHS, self._wire_size)
        self._font_date  = _load_font(_DATE_FONT_PATHS, 13)
        self._ghost      = False

        self._bloom_r1   = _BLOOM_R1
        self._bloom_r2   = _BLOOM_R2
        self._bloom_r3   = _BLOOM_R3
        self._bloom_s2   = _BLOOM_S2
        self._bleed_r    = _BLEED_R
        self._bleed_s    = _BLEED_S

        # Colon afterglow state
        self._colon_level    = 1.0   # current brightness 0.0–1.0
        self._colon_was_on   = True
        self._colon_change_t = _time.time()

    # ── public interface ───────────────────────────────────────────────────────

    def help_text(self) -> str:
        return "c=theme  h=ghost  g/G=cloud±  b/B=cloud bright  r/R=ambient±"

    def param_dict(self) -> dict:
        t = _THEMES[self._theme_idx]
        return {
            "TUBE_W": TUBE_W, "TUBE_H": TUBE_H, "TUBE_R": TUBE_R,
            "TUBE_Y": TUBE_Y, "TUBE_XS": TUBE_XS, "DATE_Y": DATE_Y,
            "theme": t["name"], "C_WIRE": t["C_WIRE"],
            "wire_size": self._wire_size,
            "bloom_r1": self._bloom_r1,
            "bloom_r2": self._bloom_r2, "bloom_s2": self._bloom_s2,
            "bloom_r3": self._bloom_r3,
            "bleed_r":  self._bleed_r,  "bleed_s":  self._bleed_s,
        }

    def on_key(self, key: str) -> bool:
        if key == "c":
            self._theme_idx = (self._theme_idx + 1) % len(_THEMES)
            return True
        if key == "h":
            self._ghost = not self._ghost
            return True
        if key == "g":
            self._bloom_r2 = min(24.0, self._bloom_r2 + 1.0);  return True
        if key in ("G", "shift+g"):
            self._bloom_r2 = max(2.0,  self._bloom_r2 - 1.0);  return True
        if key == "b":
            self._bloom_s2 = min(3.0,  self._bloom_s2 + 0.05); return True
        if key in ("B", "shift+b"):
            self._bloom_s2 = max(0.2,  self._bloom_s2 - 0.05); return True
        if key == "r":
            self._bloom_r3 = min(40.0, self._bloom_r3 + 2.0);  return True
        if key in ("R", "shift+r"):
            self._bloom_r3 = max(4.0,  self._bloom_r3 - 2.0);  return True
        return False

    # ── render ─────────────────────────────────────────────────────────────────

    def render(self, img: Image.Image, t: _time.struct_time) -> None:
        c_wire = _THEMES[self._theme_idx]["C_WIRE"]
        c_bg   = tuple(max(int(v * 0.02), 3 if i == 0 else 0)
                       for i, v in enumerate(c_wire))

        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, self.CANVAS_W - 1, self.CANVAS_H - 1], fill=(0, 0, 0))

        digits = [
            t.tm_hour // 10, t.tm_hour % 10,
            t.tm_min  // 10, t.tm_min  % 10,
        ]
        mesh = _build_mesh(TUBE_W, TUBE_H, c_wire)

        for digit, tx in zip(digits, TUBE_XS):
            self._draw_tube(img, tx, TUBE_Y, digit, c_wire, c_bg, mesh)

        self._update_colon_afterglow()
        c_colon = tuple(int(v * self._colon_level) for v in c_wire)
        self._draw_colon(img, c_colon)
        self._draw_date(img, t, c_wire)

    # ── tube ───────────────────────────────────────────────────────────────────

    def _draw_tube(self, canvas: Image.Image, tx: int, ty: int,
                   digit: int, c_wire: tuple, c_bg: tuple,
                   mesh: Image.Image) -> None:

        # 1. tube background + mesh
        tube = Image.new("RGB", (TUBE_W, TUBE_H), c_bg)
        tube = ImageChops.add(tube, mesh)

        # 2. wire glyph buffer
        wire = Image.new("RGB", (TUBE_W, TUBE_H), (0, 0, 0))
        if self._ghost:
            self._draw_ghost_digits(wire, digit, c_wire)
        self._draw_wire_digit(wire, digit, c_wire)

        # 3. bloom
        bloom = self._make_bloom(wire)

        # 4. composite, clip to tube mask
        tube = ImageChops.add(tube, ImageChops.add(bloom, wire))
        tube.paste(Image.new("RGB", (TUBE_W, TUBE_H), (0, 0, 0)),
                   mask=ImageChops.invert(_TUBE_MASK))

        # 5. outer bleed — paste before tube so glass sits on top
        bleed = tube.filter(ImageFilter.GaussianBlur(radius=self._bleed_r))
        bleed = bleed.point(lambda x: min(255, int(x * self._bleed_s)))
        pad = max(1, int(self._bleed_r * 1.5))
        # blit bleed additively, clamped to canvas bounds
        bx0, by0 = max(0, tx - pad), max(0, ty - pad)
        bx1, by1 = min(canvas.width, tx + TUBE_W + pad), min(canvas.height, ty + TUBE_H + pad)
        region = canvas.crop((bx0, by0, bx1, by1))
        bleed_crop = bleed.crop((bx0 - (tx - pad), by0 - (ty - pad),
                                 bx0 - (tx - pad) + (bx1 - bx0),
                                 by0 - (ty - pad) + (by1 - by0)))
        canvas.paste(ImageChops.add(region, bleed_crop), (bx0, by0))

        # 6. paste tube
        canvas.paste(tube, (tx, ty), mask=_TUBE_MASK)

        # 7. glass outline + pin shadow
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle([tx, ty, tx + TUBE_W - 1, ty + TUBE_H - 1],
                            radius=TUBE_R, outline=(50, 22, 5), width=1)
        px = tx + TUBE_W // 2
        py = ty + TUBE_H
        d.rectangle([px - 7, py, px - 5, py + 2], fill=(8, 3, 0))
        d.rectangle([px + 4, py, px + 6, py + 2], fill=(8, 3, 0))

    # ── glyph helpers ──────────────────────────────────────────────────────────

    def _draw_wire_digit(self, buf: Image.Image, digit: int,
                         c_wire: tuple, scale: float = 1.0) -> None:
        d    = ImageDraw.Draw(buf)
        text = str(digit)
        bb   = d.textbbox((0, 0), text, font=self._font_wire)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx = (TUBE_W - tw) // 2 - bb[0]
        ty = (TUBE_H - th) // 2 - bb[1]
        fill = tuple(min(255, int(v * scale)) for v in c_wire)
        d.text((tx, ty), text, font=self._font_wire, fill=fill)

    def _draw_ghost_digits(self, buf: Image.Image, active: int,
                           c_wire: tuple) -> None:
        for d in range(10):
            if d != active:
                self._draw_wire_digit(buf, d, c_wire, scale=0.04)

    # ── bloom ──────────────────────────────────────────────────────────────────

    def _make_bloom(self, wire: Image.Image) -> Image.Image:
        def _pass(r: float, s: float) -> Image.Image:
            b = wire.filter(ImageFilter.GaussianBlur(radius=r))
            return b.point(lambda x: min(255, int(x * s)))

        p1 = _pass(self._bloom_r1, _BLOOM_S1)
        p2 = _pass(self._bloom_r2, self._bloom_s2)
        p3 = _pass(self._bloom_r3, _BLOOM_S3)
        return ImageChops.add(p1, ImageChops.add(p2, p3))

    # ── colon afterglow ────────────────────────────────────────────────────────

    def _update_colon_afterglow(self) -> None:
        """Compute colon glow level: fast ramp-up, exponential phosphor decay."""
        now     = _time.time()
        frac    = now % 1.0
        colon_on = frac < 0.5   # on for first half-second, off for second half

        if colon_on != self._colon_was_on:
            self._colon_change_t = now
            self._colon_was_on   = colon_on

        elapsed_ms = (now - self._colon_change_t) * 1000.0

        if colon_on:
            # linear ramp: 0 → 1 over _COLON_RAMP_MS
            self._colon_level = min(1.0, elapsed_ms / _COLON_RAMP_MS)
        else:
            # exponential decay: tau = _COLON_DECAY_MS
            self._colon_level = math.exp(-elapsed_ms / _COLON_DECAY_MS)

    # ── colon ──────────────────────────────────────────────────────────────────

    def _draw_colon(self, canvas: Image.Image, c_wire: tuple) -> None:
        if max(c_wire) < 2:
            return   # fully decayed — skip bloom computation
        r    = 3
        cy1  = TUBE_Y + TUBE_H // 3
        cy2  = TUBE_Y + 2 * TUBE_H // 3

        for cy in (cy1, cy2):
            # render dot + bloom on a small buffer, paste additively
            bsize = 60
            dot_buf = Image.new("RGB", (bsize, bsize), (0, 0, 0))
            dc = ImageDraw.Draw(dot_buf)
            mid = bsize // 2
            dc.ellipse([mid - r, mid - r, mid + r, mid + r], fill=c_wire)
            bloom = self._make_bloom(dot_buf)
            composite = ImageChops.add(dot_buf, bloom)

            px = COLON_CX - bsize // 2
            py = cy - bsize // 2
            # additive paste onto canvas
            bx0, by0 = max(0, px), max(0, py)
            bx1, by1 = min(canvas.width, px + bsize), min(canvas.height, py + bsize)
            reg  = canvas.crop((bx0, by0, bx1, by1))
            comp_crop = composite.crop((bx0 - px, by0 - py,
                                        bx0 - px + (bx1 - bx0),
                                        by0 - py + (by1 - by0)))
            canvas.paste(ImageChops.add(reg, comp_crop), (bx0, by0))

    # ── date ───────────────────────────────────────────────────────────────────

    def _draw_date(self, canvas: Image.Image, t: _time.struct_time,
                   c_wire: tuple) -> None:
        _DAYS   = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        _MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        s = f"{_DAYS[t.tm_wday]}  {t.tm_mday:02d} {_MONTHS[t.tm_mon - 1]} {t.tm_year}"
        c_date = tuple(int(v * 0.60) for v in c_wire)

        d = ImageDraw.Draw(canvas)
        d.text((137, DATE_Y), s, font=self._font_date, fill=c_date, anchor="mt")

        # flanking bullet dots
        bb = d.textbbox((0, 0), s, font=self._font_date)
        hw = (bb[2] - bb[0]) // 2 + 10
        mh = (bb[3] - bb[1]) // 2
        c_dot = tuple(int(v * 0.32) for v in c_wire)
        for sx in (-hw, hw):
            d.ellipse([137 + sx - 2, DATE_Y + mh - 2,
                       137 + sx + 2, DATE_Y + mh + 2], fill=c_dot)


# ── standalone sanity test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    renderer = NixieRenderer()
    img = Image.new("RGB", (275, 240), (0, 0, 0))
    t   = _time.struct_time((2026, 6, 13, 8, 42, 0, 4, 164, 1))
    renderer.render(img, t)

    out = pathlib.Path("/tmp/nixie_test.png")
    img.save(out)
    print(f"NixieRenderer OK — saved to {out}")

    assert renderer.on_key("c") is True
    assert renderer.on_key("h") is True
    assert renderer.on_key("g") is True
    assert renderer.on_key("x") is False
    print("on_key OK")
    d = renderer.param_dict()
    assert "TUBE_W" in d and "theme" in d
    print("param_dict OK")
    sys.exit(0)
