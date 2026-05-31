#!/usr/bin/env python3
"""dut_fonts.py — PIL renderers for TFT_eSPI Font1 (GLCD 5×7) and Font2 (16px).

Parses font bitmap data directly from the TFT_eSPI library source files so the
host-side preview matches DUT rendering exactly — no TrueType approximation.

Fonts:
    Font1  setTextFont(1) — GLCD 5×7 Adafruit GFX font, 6×8 cell (5px + 1gap, 7px + 1gap)
    Font2  setTextFont(2) — Font16, variable-width 16px, baseline row 13

Usage:
    import dut_fonts
    f1, f2 = dut_fonts.load()         # auto-locate from __file__ → project root
    f2.draw(draw, 5, 10, "NVDA", fg=(255,255,255))
    f1.draw_centered(draw, cx, cy, "+3.2%", fg=(0,200,0))
"""
from __future__ import annotations

import pathlib
import re
from typing import Optional

# ── library path resolution ───────────────────────────────────────────────────

_TOOLS_DIR = pathlib.Path(__file__).parent
_PROJECT_ROOT = _TOOLS_DIR.parent.parent   # app/tools → app → project root
_FONT_DIR = (
    _PROJECT_ROOT
    / "Spotify-Diy-Thing"
    / ".pio" / "libdeps" / "cyd2usb_winamp" / "TFT_eSPI" / "Fonts"
)


# ── Font1 — GLCD 5×7 (setTextFont(1)) ────────────────────────────────────────

class Font1:
    """GLCD Adafruit-GFX 5×7 bitmap font.

    Cell dimensions: 6×8 px (5 glyph cols + 1 gap, 7 glyph rows + 1 gap).
    Format in glcdfont.c: each char = 5 bytes; each byte = one column,
    bit 0 = top row, bit 6 = bottom row.
    """
    CHAR_W  = 6   # advance width (glyph 5 + 1 gap)
    CHAR_H  = 8   # cell height   (glyph 7 + 1 gap)
    GLYPH_W = 5
    GLYPH_H = 7

    def __init__(self, font_dir: pathlib.Path = _FONT_DIR):
        path = font_dir / "glcdfont.c"
        text = path.read_text()
        m = re.search(
            r'font\[\]\s+PROGMEM\s*=\s*\{([^}]+)\}', text, re.DOTALL
        )
        if not m:
            raise ValueError(f"Cannot parse GLCD font array in {path}")
        self._data = [int(v, 16)
                      for v in re.findall(r'0x([0-9A-Fa-f]{2})', m.group(1))]

    # ── glyph access ──────────────────────────────────────────────────────

    def _glyph(self, c: int) -> list[list[bool]]:
        """7 rows × 5 cols bitmap for ASCII code c."""
        if c < 0 or c * 5 + 4 >= len(self._data):
            c = ord('?')
        base = c * 5
        return [
            [bool((self._data[base + col] >> row) & 1)
             for col in range(self.GLYPH_W)]
            for row in range(self.GLYPH_H)
        ]

    # ── drawing ───────────────────────────────────────────────────────────

    def draw(self, draw, x: int, y: int, text: str,
             fg: tuple, bg: Optional[tuple] = None) -> int:
        """Draw string top-left at (x, y). Returns x after last character."""
        fg_pts: list[tuple[int,int]] = []
        bg_pts: list[tuple[int,int]] = []
        cx = x
        for ch in text:
            bm = self._glyph(ord(ch))
            for row_i, row in enumerate(bm):
                for col_i, lit in enumerate(row):
                    pt = (cx + col_i, y + row_i)
                    if lit:
                        fg_pts.append(pt)
                    elif bg is not None:
                        bg_pts.append(pt)
            cx += self.CHAR_W
        if bg_pts:
            draw.point(bg_pts, fill=bg)
        if fg_pts:
            draw.point(fg_pts, fill=fg)
        return cx

    def draw_centered(self, draw, cx: int, cy: int, text: str,
                      fg: tuple, bg: Optional[tuple] = None) -> None:
        """Draw string centered at (cx, cy)."""
        x = cx - self.text_width(text) // 2
        y = cy - self.GLYPH_H // 2
        self.draw(draw, x, y, text, fg, bg)

    def draw_right(self, draw, rx: int, cy: int, text: str,
                   fg: tuple, bg: Optional[tuple] = None) -> None:
        """Draw string right-aligned at x=rx, vertically centered at cy."""
        x = rx - self.text_width(text)
        y = cy - self.GLYPH_H // 2
        self.draw(draw, x, y, text, fg, bg)

    def draw_left(self, draw, lx: int, cy: int, text: str,
                  fg: tuple, bg: Optional[tuple] = None) -> None:
        """Draw string left-aligned at x=lx, vertically centered at cy."""
        y = cy - self.GLYPH_H // 2
        self.draw(draw, lx, y, text, fg, bg)

    def text_width(self, text: str) -> int:
        return len(text) * self.CHAR_W

    def text_height(self) -> int:
        return self.GLYPH_H


# ── Font2 — Font16 variable-width 16px (setTextFont(2)) ──────────────────────

class Font2:
    """TFT_eSPI Font16: variable-width, 16 rows, baseline at row 13.

    Format in Font16.c:
        widtbl_f16[96]  — width in pixels for ASCII 32..127
        chr_f16_XX[N]   — glyph data, XX = hex ASCII code
                          N=16 (1 byte/row) when width ≤ 8
                          N=32 (2 bytes/row) when width 9–16
    Row format: MSB = leftmost pixel.
    Character advance = glyph_width + 1 gap (TFT_eSPI default spacing).
    """
    CHAR_H   = 16
    BASELINE = 13   # 0-based row index of baseline

    def __init__(self, font_dir: pathlib.Path = _FONT_DIR):
        path = font_dir / "Font16.c"
        text = path.read_text()
        self._widths = self._parse_widths(text)
        self._glyphs = self._parse_glyphs(text)

    def _parse_widths(self, text: str) -> list[int]:
        m = re.search(
            r'widtbl_f16\[96\][^{]*\{([^}]+)\}', text, re.DOTALL
        )
        if not m:
            raise ValueError("Cannot parse widtbl_f16")
        body = m.group(1)
        # Remove #else...#endif block (keep #ifdef branch which is always active)
        body = re.sub(r'#else.*?#endif', '', body, flags=re.DOTALL)
        # Strip remaining preprocessor lines and // comments
        body = re.sub(r'#[^\n]*', '', body)
        body = re.sub(r'//[^\n]*', '', body)
        return [int(v) for v in re.findall(r'\d+', body)][:96]

    def _parse_glyphs(self, text: str) -> dict[int, list[int]]:
        glyphs: dict[int, list[int]] = {}
        for m in re.finditer(
            r'chr_f16_([0-9A-Fa-f]+)\[\d+\][^{]*\{([^}]+)\}',
            text, re.DOTALL
        ):
            code = int(m.group(1), 16)
            data = [int(v, 16)
                    for v in re.findall(r'0x([0-9A-Fa-f]{2})', m.group(2))]
            glyphs[code] = data
        return glyphs

    # ── glyph access ──────────────────────────────────────────────────────

    def _glyph(self, c: int) -> tuple[int, list[list[bool]]]:
        """Return (advance_width, 16-row bitmap) for ASCII code c."""
        idx = c - 32
        if idx < 0 or idx >= 96:
            return self._glyph(ord('?'))
        w   = self._widths[idx]
        bpr = (w + 7) // 8            # bytes per row
        raw = self._glyphs.get(c, [0] * (self.CHAR_H * bpr))
        rows = []
        for row in range(self.CHAR_H):
            base = row * bpr
            r = []
            for bit in range(w):
                b_idx = bit // 8
                b_bit = 7 - (bit % 8)  # MSB = leftmost
                val   = raw[base + b_idx] if base + b_idx < len(raw) else 0
                r.append(bool((val >> b_bit) & 1))
            rows.append(r)
        return w + 1, rows             # advance = width + 1 gap

    # ── drawing ───────────────────────────────────────────────────────────

    def draw(self, draw, x: int, y: int, text: str,
             fg: tuple, bg: Optional[tuple] = None) -> int:
        """Draw string top-left at (x, y). Returns x after last character."""
        fg_pts: list[tuple[int,int]] = []
        bg_pts: list[tuple[int,int]] = []
        cx = x
        for ch in text:
            adv, rows = self._glyph(ord(ch))
            for row_i, row in enumerate(rows):
                for col_i, lit in enumerate(row):
                    pt = (cx + col_i, y + row_i)
                    if lit:
                        fg_pts.append(pt)
                    elif bg is not None:
                        bg_pts.append(pt)
            cx += adv
        if bg_pts:
            draw.point(bg_pts, fill=bg)
        if fg_pts:
            draw.point(fg_pts, fill=fg)
        return cx

    def draw_centered(self, draw, cx: int, cy: int, text: str,
                      fg: tuple, bg: Optional[tuple] = None) -> None:
        """Draw string centered at (cx, cy)."""
        x = cx - self.text_width(text) // 2
        y = cy - self.CHAR_H // 2
        self.draw(draw, x, y, text, fg, bg)

    def draw_right(self, draw, rx: int, cy: int, text: str,
                   fg: tuple, bg: Optional[tuple] = None) -> None:
        """Draw string right-aligned at x=rx, vertically centered at cy."""
        x = rx - self.text_width(text)
        y = cy - self.CHAR_H // 2
        self.draw(draw, x, y, text, fg, bg)

    def draw_left(self, draw, lx: int, cy: int, text: str,
                  fg: tuple, bg: Optional[tuple] = None) -> None:
        """Draw string left-aligned at x=lx, vertically centered at cy."""
        y = cy - self.CHAR_H // 2
        self.draw(draw, lx, y, text, fg, bg)

    def text_width(self, text: str) -> int:
        total = 0
        for ch in text:
            idx = ord(ch) - 32
            if 0 <= idx < 96:
                total += self._widths[idx] + 1
        return total

    def text_height(self) -> int:
        return self.CHAR_H


# ── convenience loader ────────────────────────────────────────────────────────

def load(font_dir: pathlib.Path = _FONT_DIR) -> tuple[Font1, Font2]:
    """Return (Font1, Font2) instances from the project's TFT_eSPI library."""
    return Font1(font_dir), Font2(font_dir)
