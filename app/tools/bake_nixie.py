#!/usr/bin/env python3
"""bake_nixie.py — bake the Nixie clock's wire-glyph + bloom pipeline to flash.

M-CLOCK-NIXIE.md documents the gap: shipped ClockApp::_drawNixie() draws a
flat drawRoundRect outline + plain tft.drawString digit — none of the
wire-glyph / hex-mesh / 3-pass-bloom pipeline _clock_nixie.py already
implements for the host preview tool. TFT_eSPI has no Gaussian blur, so the
fix is the same pattern already used for the Winamp skin (bake_skin.py) and
taskbar icons (gen_taskbar_icons.py): render the expensive part on the host
with PIL, bake it to a flash-resident array, use it at runtime. Zero extra
RAM — ESP32 flash is memory-mapped, pushImage/array reads straight out of
.rodata.

Renders at the CONCEPT tube geometry (48x110, r18 — _clock_nixie.py's
TUBE_W/TUBE_H/TUBE_R), resynced 2026-07-18 per user direction after a
side-by-side screendump comparison against preview_clock.py.

LUMINANCE-ONLY bake (M-CLOCK-THEMES.md, TASK-345), not RGB565. Every colour
source in _clock_nixie.py's tube composite (mesh, tube background, wire
glyph, all three bloom passes) is a per-channel constant scale of C_WIRE —
Gaussian blur and per-channel scalar multiply are both linear, so for a
single-hue source image render(C_WIRE) == render(WHITE) scaled channel-wise
by C_WIRE/255, exactly (not an approximation, for the glyph/bloom/mesh
layers — see one documented exception below for the darkest background
pixels). So: bake once with C_WIRE=(255,255,255) and store luminance
(uint8_t, not uint16_t RGB565 — half the bytes, since a white bake has
equal R=G=B always). ClockApp::_tintNixieGlyph() reconstructs any theme's
colour from this at runtime: pixel = color565(R*lum/255, G*lum/255,
B*lum/255). Cost: 10 x 48x110 × 1 byte = 52.8 KB flat, regardless of theme
count (was 103.1 KB for a single RGB565 amber-only bake before this
change — this is cheaper AND theme-flexible).

Known minor inexactness: _clock_nixie.py's c_bg computation has a
`max(v*0.02, 3 if i==0 else 0)` floor on the background tint's R channel,
which isn't a pure linear scale of C_WIRE when C_WIRE's R channel is low
(e.g. green/blue themes) — reconstructing from a white bake under-floors
the R channel of the tube's darkest unlit background pixels by a few
units out of 255. Invisible in practice (near-black region against a
black canvas); not worth the added runtime complexity to correct.

Only the glow CONTENT is baked (mesh + wire digit + bloom, clipped to the
tube's rounded-rect mask). The glass outline, glow strokes, and pin
shadows stay as cheap runtime drawRoundRect/fillRect calls in
_drawNixie() — baking those would cost flash for zero visual gain, and
(post M-CLOCK-THEMES) already read the theme colour directly at runtime.

Outputs:
  app/gen/nixie_glyphs.cpp   — const uint8_t nixie_glyph_0..9[48/2*110] (4-bit packed luminance, TASK-353)
  app/gen/nixie_glyphs.h     — extern decls + nixie_glyph_ptrs[10]
  app/tools/icon_drafts/NIXIE_SHEET.png  — host contact sheet (--sheet, amber preview)

Run:
  ~/proj/esp/venv/bin/python3 app/tools/bake_nixie.py --sheet
"""
import argparse
import sys
import time as _time
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import _clock_nixie as nx

# ── tube geometry — always the concept's, so bake and preview can't drift ───
TUBE_W = nx.TUBE_W
TUBE_H = nx.TUBE_H
TUBE_R = nx.TUBE_R

C_WHITE = (255, 255, 255)         # bake source — luminance-only, tinted at runtime
C_PREVIEW = (255, 125, 8)         # amber — --sheet preview only, not baked

OUT_DIR = HERE.parent / "gen"
SHEET_OUT = HERE / "icon_drafts" / "NIXIE_SHEET.png"


def _build_tube_mask() -> Image.Image:
    mask = Image.new("L", (TUBE_W, TUBE_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, TUBE_W - 1, TUBE_H - 1], radius=TUBE_R, fill=255)
    return mask


def render_digit(digit: int, mask: Image.Image, c_wire: tuple) -> Image.Image:
    """Mesh + wire glyph + 3-pass bloom, clipped to the tube mask. Reuses
    _clock_nixie.py's bloom math verbatim (same renderer as the host preview
    tool) so the baked sprite and the preview tool never drift apart."""
    c_bg = tuple(max(int(v * 0.02), 3 if i == 0 else 0) for i, v in enumerate(c_wire))
    mesh = nx._build_mesh(TUBE_W, TUBE_H, c_wire)

    tube = Image.new("RGB", (TUBE_W, TUBE_H), c_bg)
    tube = ImageChops.add(tube, mesh)

    wire = Image.new("RGB", (TUBE_W, TUBE_H), (0, 0, 0))
    renderer = nx.NixieRenderer()   # default wire_size (88pt) — TUBE_H now matches concept
    renderer._draw_wire_digit(wire, digit, c_wire)
    bloom = renderer._make_bloom(wire)

    tube = ImageChops.add(tube, ImageChops.add(bloom, wire))
    tube.paste(Image.new("RGB", (TUBE_W, TUBE_H), (0, 0, 0)),
               mask=ImageChops.invert(mask))
    return tube


def img_to_luminance(img: Image.Image) -> list[int]:
    """White-baked source has R==G==B per pixel — luminance is just any channel."""
    return [r for r, g, b in img.getdata()]


def pack_4bit(data: list[int]) -> list[int]:
    """TASK-353 (M-CLOCK-FACE-COMMON pt 2): quantise 8-bit luminance to 16
    levels and pack two pixels per byte, high nibble = left pixel. Max
    quantisation error is 8/255 — at/below one RGB565 display LSB after the
    runtime theme tint, i.e. visually lossless (measured over the real baked
    set before this change landed). TUBE_W=48 is even, so rows never straddle
    a byte (one row = 24 B) and the runtime band decoder stays trivial."""
    assert TUBE_W % 2 == 0
    q = [(v * 15 + 127) // 255 for v in data]
    return [(q[i] << 4) | q[i + 1] for i in range(0, len(q), 2)]


def format_array(name: str, data: list[int]) -> str:
    packed = pack_4bit(data)
    row_bytes = TUBE_W // 2
    lines = [f"const uint8_t {name}[NIXIE_GLYPH_W / 2 * NIXIE_GLYPH_H] = {{"]
    for row in range(TUBE_H):
        chunk = packed[row * row_bytes:(row + 1) * row_bytes]
        lines.append("    " + ", ".join(str(v) for v in chunk) + ",")
    lines.append("};")
    return "\n".join(lines)


def write_sheet(mask: Image.Image) -> None:
    """Amber preview sheet, for human eyeball — not what's baked (bake is luminance)."""
    digit_imgs = [render_digit(d, mask, C_PREVIEW) for d in range(10)]
    scale = 4
    pad = 8
    cell_w, cell_h = TUBE_W * scale, TUBE_H * scale
    sheet = Image.new("RGB", (10 * (cell_w + pad) + pad, cell_h + 2 * pad), (20, 20, 20))
    for i, img in enumerate(digit_imgs):
        big = img.resize((cell_w, cell_h), Image.NEAREST)
        sheet.paste(big, (pad + i * (cell_w + pad), pad))
    SHEET_OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(SHEET_OUT)
    print(f"Wrote {SHEET_OUT}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheet", action="store_true", help="also write NIXIE_SHEET.png (amber preview)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)

    mask = _build_tube_mask()
    digit_imgs = [render_digit(d, mask, C_WHITE) for d in range(10)]

    cpp_lines = [
        "// AUTO-GENERATED by tools/bake_nixie.py — do not edit by hand.",
        "// Re-run: ~/proj/esp/venv/bin/python3 app/tools/bake_nixie.py",
        '#include "nixie_glyphs.h"',
        "",
    ]
    for d, img in enumerate(digit_imgs):
        data = img_to_luminance(img)
        cpp_lines.append(format_array(f"nixie_glyph_{d}", data))
        cpp_lines.append("")

    h_lines = [
        "// AUTO-GENERATED by tools/bake_nixie.py — do not edit by hand.",
        "// Re-run: ~/proj/esp/venv/bin/python3 app/tools/bake_nixie.py",
        "#pragma once",
        "#include <stdint.h>",
        "",
        f"#define NIXIE_GLYPH_W {TUBE_W}",
        f"#define NIXIE_GLYPH_H {TUBE_H}",
        "#define NIXIE_GLYPH_PACKED_4BIT 1",
        "",
        "// 4-bit packed luminance (TASK-353), two pixels/byte, high nibble =",
        "// left pixel; one row = NIXIE_GLYPH_W/2 bytes. Decode: l = nibble*17",
        "// via the 16-entry per-theme RGB565 LUT in",
        "// ClockApp::_tintNixieGlyph() (M-CLOCK-FACE-COMMON pt 2).",
    ]
    for d in range(10):
        h_lines.append(f"extern const uint8_t nixie_glyph_{d}[NIXIE_GLYPH_W / 2 * NIXIE_GLYPH_H];")
    h_lines.append("")
    h_lines.append("// Indexed 0..9.")
    h_lines.append("extern const uint8_t* const nixie_glyph_ptrs[10];")
    h_lines.append("")

    cpp_lines.append("const uint8_t* const nixie_glyph_ptrs[10] = {")
    cpp_lines.append("    " + ", ".join(f"nixie_glyph_{d}" for d in range(10)) + ",")
    cpp_lines.append("};")
    cpp_lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    cpp_path = out_dir / "nixie_glyphs.cpp"
    h_path = out_dir / "nixie_glyphs.h"
    cpp_path.write_text("\n".join(cpp_lines))
    h_path.write_text("\n".join(h_lines))
    total_bytes = 10 * TUBE_W // 2 * TUBE_H   # 4-bit packed (TASK-353)
    print(f"Wrote {cpp_path} + {h_path} ({total_bytes} bytes / {total_bytes/1024:.1f} KB flash)")

    if args.sheet:
        write_sheet(mask)


if __name__ == "__main__":
    main()
