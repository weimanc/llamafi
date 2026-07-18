#!/usr/bin/env python3
"""gen_icon_natives.py — native-resolution re-author of soft taskbar icons.

TASK-334 (ADR-051 Option B): renders replacement icon pairs DIRECTLY at
TASKBAR_ICON_W × TASKBAR_ICON_H (from gen/shell_layout.h) so the bake step
is a pass-through — no resample between what's approved here and what ships.

Scope (2026-07-18 human triage of BAKED_SHEET.png at 36×36):
  life      — was 56% fill, uneven blocks; exact-pixel glider, no AA at all
  clock     — 32→36 upscale softness; programmatic circle+hands
  weather   — both variants crisp; programmatic sun+cloud
  matrix    — 32→36 softness; programmatic diagonal pill
  settings  — 32→36 softness; re-rendered from settings.svg master
  stock     — 32→36 softness; re-rendered from stock.svg master
  aquarium  — 1px ASCII-fish strokes never survived resampling; redrawn
              with 2px grid-aligned strokes
  teletext  — line spacing uneven after 40→36 resample; border supersampled,
              horizontal lines drawn at exact pixels (2px lines, 4px gaps);
              bbox pulled in to 30px (square glyphs read optically larger)
  crypto    — (2nd triage round) circle redrawn native + ₿ from bitcoin.svg
  aquarium  — (2nd round) ASCII fish now rendered as literal TEXT: mono font
              auto-sized down until the packed glyphs fit, binarized to hard
              pixels — no vector redraw, no resample

Untouched: spotify (fine as-is), planeradar (TASK-333).

Curved shapes draw at an INTEGER supersample factor (SS) and take exactly
one LANCZOS down to the target — even AA, no double-resample. Rectilinear
pixel art (life blocks, teletext lines) is drawn 1:1 with no resample.

Outputs candidate PNGs to app/tools/icon_drafts/native/ and a full
candidate contact sheet (candidates merged over current icons) via
gen_taskbar_icons.py --sheet to app/tools/icon_drafts/NATIVE_SHEET.png.
Nothing under app/icons/taskbar/ is touched — copy in only after human
approval (--install does the copy).

Run:
  ~/proj/esp/venv/bin/python3 app/tools/gen_icon_natives.py
  ~/proj/esp/venv/bin/python3 app/tools/gen_icon_natives.py --install
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
ICONS_DIR = HERE.parent / "icons" / "taskbar"
OUT_DIR = HERE / "icon_drafts" / "native"

_LAYOUT = (HERE.parent / "gen" / "shell_layout.h").read_text()
W = int(re.search(r"#define\s+TASKBAR_ICON_W\s+(\d+)", _LAYOUT).group(1))
H = int(re.search(r"#define\s+TASKBAR_ICON_H\s+(\d+)", _LAYOUT).group(1))

SS = 8  # integer supersample factor for curved shapes

WHITE = (255, 255, 255, 255)

# Active-variant palette, sampled from the shipped _active PNGs (2026-07-18)
CLOCK_BEIGE = (231, 209, 178, 255)      # flat tint — active clock is one colour
WEATHER_SUN = (247, 222, 80, 255)
WEATHER_CLOUD = (247, 247, 190, 255)
MATRIX_RED_DARK = (144, 0, 0, 255)
MATRIX_RED_BRIGHT = (224, 32, 32, 255)
MATRIX_GREY = (200, 200, 200, 255)
LIFE_COLORS = {                          # per-block gradient, blue → orange
    (1, 0): (0, 94, 255, 255),
    (2, 1): (52, 94, 203, 255),
    (0, 2): (100, 94, 155, 255),
    (1, 2): (152, 94, 103, 255),
    (2, 2): (200, 94, 55, 255),
}
SETTINGS_ORANGE = (240, 128, 0, 255)
STOCK_GREEN = (0, 192, 64, 255)
AQUARIUM_CYAN = (0, 224, 240, 255)
TELETEXT_CYAN = (0, 208, 208, 255)
CRYPTO_GOLD = (240, 192, 0, 255)

MONO_FONT = "/usr/share/fonts/google-noto-vf/NotoSansMono[wght].ttf"


def canvas_ss():
    return Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))


def down(img_ss: Image.Image) -> Image.Image:
    return img_ss.resize((W, H), Image.LANCZOS)


def s(v):
    return round(v * SS)


# ── clock ─────────────────────────────────────────────────────────────────────

def draw_clock(color) -> Image.Image:
    """Circle outline + hands at 12:00 / ~4:30 (matches clock.svg's pose)."""
    img = canvas_ss()
    d = ImageDraw.Draw(img)
    cx = cy = W / 2.0
    r = 16.0                      # bbox 33px → 92% fill
    stroke = 3.0
    d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)],
              outline=color, width=s(stroke))
    d.line([s(cx), s(cy), s(cx), s(cy - 10.5)], fill=color, width=s(2.5))
    d.line([s(cx), s(cy), s(cx + 7.5), s(cy + 7.5)], fill=color, width=s(2.5))
    return down(img)


# ── weather ───────────────────────────────────────────────────────────────────

def draw_weather(sun_color, cloud_color) -> Image.Image:
    """Sun (disc + 8 rays) top-right, flat-bottomed cloud bottom-left."""
    img = canvas_ss()
    d = ImageDraw.Draw(img)
    import math
    scx, scy, sr = 23.0, 12.0, 5.5
    d.ellipse([s(scx - sr), s(scy - sr), s(scx + sr), s(scy + sr)], fill=sun_color)
    for i in range(8):
        ang = math.radians(i * 45)
        r0, r1 = sr + 2.0, sr + 6.0
        d.line([s(scx + r0 * math.cos(ang)), s(scy + r0 * math.sin(ang)),
                s(scx + r1 * math.cos(ang)), s(scy + r1 * math.sin(ang))],
               fill=sun_color, width=s(2.0))
    # cloud: lobes only (no base rect — a wide rect reads as a torso), flat
    # bottom cut at base_y; drawn after sun so it overlaps in front
    base_y = 31.0
    lobes = [(8.0, 25.0, 6.0), (14.5, 21.5, 6.5), (20.5, 25.0, 5.5)]
    for lx, ly, lr in lobes:
        d.ellipse([s(lx - lr), s(ly - lr), s(lx + lr), s(ly + lr)], fill=cloud_color)
    d.rounded_rectangle([s(2.0), s(23.5), s(26.0), s(base_y)], radius=s(3.0),
                        fill=cloud_color)
    return down(img)


# ── matrix ────────────────────────────────────────────────────────────────────

def draw_matrix(col_a, col_b, shine=True) -> Image.Image:
    """Diagonal capsule (pill), two halves col_a (lower-left) / col_b."""
    import math
    img = canvas_ss()
    d = ImageDraw.Draw(img)
    x1, y1, x2, y2 = 11.0, 25.0, 25.0, 11.0   # axis endpoints
    r = 8.0                                    # bbox ≈ 31px → 86%
    ux, uy = (x2 - x1), (y2 - y1)
    ln = math.hypot(ux, uy)
    ux, uy = ux / ln, uy / ln
    px, py = -uy, ux                           # perpendicular
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2

    def halfpoly(ax, ay, color):
        # capsule end circle + rect from midline to that end
        d.ellipse([s(ax - r), s(ay - r), s(ax + r), s(ay + r)], fill=color)
        quad = [(mx + px * r, my + py * r), (mx - px * r, my - py * r),
                (ax - px * r, ay - py * r), (ax + px * r, ay + py * r)]
        d.polygon([(s(qx), s(qy)) for qx, qy in quad], fill=color)

    halfpoly(x1, y1, col_a)
    halfpoly(x2, y2, col_b)
    if shine:
        d.ellipse([s(x2 - 2.5), s(y2 - 4.5), s(x2 + 2.0), s(y2 - 0.5)],
                  fill=(255, 255, 255, 200))
    return down(img)


# ── life ──────────────────────────────────────────────────────────────────────

GLIDER = [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]


def draw_life(colors=None) -> Image.Image:
    """Exact-pixel glider: 10px cells, 2px gaps, no AA, no resample."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cell, gap, org = 10, 2, 1                  # bbox 34px → 94%
    for (cx, cy) in GLIDER:
        col = (colors or {}).get((cx, cy), WHITE)
        x0 = org + cx * (cell + gap)
        y0 = org + cy * (cell + gap)
        d.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=col)
    return img


# ── teletext ──────────────────────────────────────────────────────────────────

def draw_teletext(color) -> Image.Image:
    """Rounded border (supersampled) + text lines at exact pixels:
    2px lines at y=8,14,20,26 — uniform gaps incl. border margins.
    Border bbox 30px (83%): a filled square reads optically larger than a
    round/sparse glyph at equal bbox, so it sits deliberately below the
    ADR-051 band (the WARN is expected and accepted)."""
    img_ss = canvas_ss()
    d = ImageDraw.Draw(img_ss)
    d.rounded_rectangle([s(3), s(3), s(32.99), s(32.99)], radius=s(5),
                        outline=color, width=s(3))
    img = down(img_ss)
    d2 = ImageDraw.Draw(img)
    for y in (8, 14, 20, 26):
        d2.rectangle([8, y, 27, y + 1], fill=color)
    return img


# ── aquarium ──────────────────────────────────────────────────────────────────

def draw_aquarium(color) -> Image.Image:
    """The ASCII fish '><((( *>' rendered as actual TEXT — a mono font at
    the largest size whose glyphs (manually packed: per-char ink boxes,
    1px gaps, baseline-aligned) fit the icon width, binarized to hard
    pixels. No vector redraw, no resample — font hinting does the crisp."""
    from PIL import ImageFont

    text = "><((( *>"
    max_w = 35
    gap, space = 0, 1   # compressed: ink boxes touch, 1px word gap — the
                        # width saved lets the size search pick a larger font

    def glyphs(font, eye_font):
        """[(char-ink-image, ink-bbox)] — getmask gives true ink boxes;
        textbbox would return the mono advance box (identical per char).
        The '*' eye renders from eye_font (one size up): binarization at
        the body size amputates the asterisk's arms into a '^'."""
        out = []
        for ch in text:
            if ch == " ":
                out.append((None, None))
                continue
            m = (eye_font if ch == "*" else font).getmask(ch, mode="L")
            img = Image.frombytes("L", m.size, bytes(m))
            out.append((img, img.getbbox()))
        return out

    def pack_width(gs):
        wsum = sum(space if g is None else (bb[2] - bb[0]) + gap
                   for g, bb in gs)
        return wsum - gap  # no gap after last char

    font = packed = None
    for size in range(16, 6, -1):   # largest size whose packed ink fits
        f = ImageFont.truetype(MONO_FONT, size)
        fe = ImageFont.truetype(MONO_FONT, size + 2)
        gs = glyphs(f, fe)
        if pack_width(gs) <= max_w:
            font, packed = f, gs
            break
    assert font is not None, "fish text cannot fit the icon width"

    # Pack at 1px gaps, preserving each glyph's vertical bearing (the '*'
    # eye sits high, the arcs centred — exactly like terminal output),
    # then binarize to hard pixels (threshold 110).
    mask = Image.new("L", (W, H), 0)
    x = 0
    for g, bb in packed:
        if g is None:
            x += space
            continue
        crop = g.crop(bb)
        # paste through the glyph as its own mask — with gap 0, adjacent
        # ink boxes may overlap by a column; a plain paste would erase the
        # neighbour's edge with this glyph's transparent pixels
        mask.paste(crop, (x, 10 + bb[1]), crop)
        x += (bb[2] - bb[0]) + gap
    mask = mask.point(lambda v: 255 if v >= 110 else 0)

    # Centre the ink bbox on the canvas
    bbox = mask.getbbox()
    glyph = mask.crop(bbox)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    tint = Image.new("RGBA", glyph.size, color)
    tint.putalpha(glyph)
    out.paste(tint, ((W - glyph.width) // 2, (H - glyph.height) // 2), tint)
    return out


# ── crypto ────────────────────────────────────────────────────────────────────

def draw_crypto(color) -> Image.Image:
    """Circle outline (supersampled) + the ₿ glyph from bitcoin.svg."""
    img_ss = canvas_ss()
    d = ImageDraw.Draw(img_ss)
    cx = cy = W / 2.0
    r = 16.0                      # bbox 33px → 92%, matches clock
    d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)],
              outline=color, width=s(3.0))
    img = down(img_ss)
    glyph = render_svg(ICONS_DIR / "bitcoin.svg", color, 20)
    return Image.alpha_composite(img, glyph)


# ── SVG-derived (settings, stock) ─────────────────────────────────────────────

def render_svg(svg: Path, color, major_px: int) -> Image.Image:
    """Rasterise a Material Symbols SVG via inkscape at high res, crop to the
    glyph bbox, single LANCZOS down so the major axis == major_px, tint via
    alpha, centre on the W×H canvas."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        subprocess.run(
            ["inkscape", str(svg), "-w", "960", "-h", "960",
             "--export-type=png", "-o", str(tmp)],
            check=True, capture_output=True)
        big = Image.open(tmp).convert("RGBA")
    finally:
        tmp.unlink(missing_ok=True)
    bbox = big.split()[3].getbbox()
    big = big.crop(bbox)
    scale = major_px / max(big.size)
    tw, th = max(1, round(big.width * scale)), max(1, round(big.height * scale))
    glyph = big.resize((tw, th), Image.LANCZOS)
    tinted = Image.new("RGBA", glyph.size, color)
    tinted.putalpha(glyph.split()[3])
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(tinted, ((W - tw) // 2, (H - th) // 2), tinted)
    return out


# ── candidate set ─────────────────────────────────────────────────────────────

def build() -> dict:
    return {
        "clock": draw_clock(WHITE),
        "clock_active": draw_clock(CLOCK_BEIGE),
        "weather": draw_weather(WHITE, WHITE),
        "weather_active": draw_weather(WEATHER_SUN, WEATHER_CLOUD),
        "matrix": draw_matrix(MATRIX_GREY, WHITE),
        "matrix_active": draw_matrix(MATRIX_RED_DARK, MATRIX_RED_BRIGHT),
        "life": draw_life(),
        "life_active": draw_life(LIFE_COLORS),
        "teletext": draw_teletext(WHITE),
        "teletext_active": draw_teletext(TELETEXT_CYAN),
        "aquarium": draw_aquarium(WHITE),
        "aquarium_active": draw_aquarium(AQUARIUM_CYAN),
        "crypto": draw_crypto(WHITE),
        "crypto_active": draw_crypto(CRYPTO_GOLD),
        "settings": render_svg(ICONS_DIR / "settings.svg", WHITE, 33),
        "settings_active": render_svg(ICONS_DIR / "settings.svg", SETTINGS_ORANGE, 33),
        "stock": render_svg(ICONS_DIR / "stock.svg", WHITE, 33),
        "stock_active": render_svg(ICONS_DIR / "stock.svg", STOCK_GREEN, 33),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--install", action="store_true",
                    help="Copy approved candidates into app/icons/taskbar/ "
                         "(run only after human approval of NATIVE_SHEET.png)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cands = build()
    for name, img in cands.items():
        img.save(OUT_DIR / f"{name}.png")
    print(f"Wrote {len(cands)} candidates to {OUT_DIR}")

    if args.install:
        for name in cands:
            shutil.copy(OUT_DIR / f"{name}.png", ICONS_DIR / f"{name}.png")
        print(f"Installed {len(cands)} icons into {ICONS_DIR} — re-run "
              f"gen_taskbar_icons.py and regen golden.sha256")
        return

    # Candidate sheet: current icons + candidates merged in a temp dir, run
    # through the real bake pipeline (pass-through applies — candidates are
    # already W×H) so the sheet shows true shipped pixels.
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        for p in ICONS_DIR.glob("*.png"):
            shutil.copy(p, tdir / p.name)
        for name in cands:
            shutil.copy(OUT_DIR / f"{name}.png", tdir / f"{name}.png")
        gen_dir = tdir / "gen"
        gen_dir.mkdir()
        subprocess.run(
            [sys.executable, str(HERE / "gen_taskbar_icons.py"),
             "--icons-dir", str(tdir), "--out-dir", str(gen_dir),
             "--layout", str(HERE.parent / "gen" / "shell_layout.h"),
             "--sheet", "--sheet-out",
             str(HERE / "icon_drafts" / "NATIVE_SHEET.png")],
            check=True)
    print("Candidate sheet: app/tools/icon_drafts/NATIVE_SHEET.png")


if __name__ == "__main__":
    main()
