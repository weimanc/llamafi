#!/usr/bin/env python3
"""gen_icon_drafts.py — DRAFT generator for taskbar icon redesign proposals.

Not wired into run/bake-icons. Produces candidate PNGs + a contact sheet
under app/tools/icon_drafts/ for human review before any file under
app/icons/taskbar/ is touched.

Covers two in-flight design requests:
  1. PlaneRadar taskbar icon redesign (2 rings, +30% cross weight,
     single aircraft dart replacing the two dots).
  2. WebRadio "active" indicator via an on-DUT orange->red recolour
     filter applied to the existing spotify_active.png (winamp bolt),
     rather than baking a dedicated webradio icon.

Run:
  ~/proj/esp/venv/bin/python3 app/tools/gen_icon_drafts.py
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
ICONS_DIR = HERE.parent / "icons" / "taskbar"
OUT_DIR = HERE / "icon_drafts"
OUT_DIR.mkdir(exist_ok=True)

SS = 10          # supersample factor for anti-aliasing
TASKBAR_BG = (0x21, 0x08, 0x21)  # approx RGB of TASKBAR_BG_RGB565 0x2104

# ---------------------------------------------------------------------------
# Base geometry measured off the CURRENT (shipped) planeradar.png: outer ring
# radius 16, canvas 40 (margin 4 -> the ring fills 16/20 = 80% of the
# half-canvas), cross half-width 1.0 (2px thick), ring stroke 2.0,
# aircraft-dot offset from centre (-7.3, +9.7) i.e. 75.9% of outer_r out
# along a ~127 deg bearing, dart nose/tail lengths 7.0/4.2.
#
# BUG in the previous pass: "30% bigger diameter" was implemented by scaling
# outer_r AND the margin/canvas together. gen_taskbar_icons.py always resizes
# the source PNG down to the fixed 24x24 baked slot, so only the RATIO of
# ring-radius to canvas-size survives that resize -- scaling both by the same
# factor preserves the ratio exactly, i.e. a no-op on the shipped icon. (This
# is why it "still looked small": it WAS still the same size, just rendered
# from a bigger source that got scaled back down.)
#
# Fix: grow the ring's FILL RATIO of the canvas, canvas itself fixed. Other
# icons in this set already run near-full-bleed -- crypto.png's bbox (which
# includes the outer edge of its stroke) fills 95% of its 40x40 canvas.
# Match that exactly: solve the ring's CENTRELINE radius so that
# centreline + half the stroke width lands at 95% of the half-canvas, a
# genuine ~+19pp visual size increase over the original 80% fill -- this is
# what actually reads as "the circle got bigger" post-bake, unlike the
# previous scale-both approach.
CANVAS = 44
CENTER = CANVAS / 2.0            # 22.0
TARGET_FILL = 1.02                # pre-antialiasing target; supersample+LANCZOS
                                   # downsize softens the true edge under the
                                   # alpha>128 bbox threshold, so this
                                   # overshoot lands the MEASURED fill at 0.93
                                   # (empirically tuned against crypto.png's
                                   # measured 0.95 -- 1.03+ clips the 44x44
                                   # canvas outright, so this is as close as
                                   # it gets without the ring touching the
                                   # frame edge)
_RING_W_RATIO = 0.125            # ring stroke width as a fraction of OUTER_R
OUTER_R = (TARGET_FILL * CENTER) / (1.0 + _RING_W_RATIO / 2.0)
INNER_R = OUTER_R * 0.5625       # same ratio to OUTER_R as before (9/16)
RING_W = OUTER_R * _RING_W_RATIO
CROSS_HW = OUTER_R * 0.0625      # same ratio to OUTER_R as before (1.0/16)

# Aircraft dart: sized as a ratio of OUTER_R (not of the app's PR_R=118 --
# the app's real nose_len=7/PR_R=118 ratio is ~5%, which on a 20px icon
# radius is ~1px, i.e. invisible; matching it literally would be the
# opposite of legible). Keeps the app's dart PROPORTIONS (nose:tail ratio
# 7:4, wing_angle) and its bottom-left-quadrant placement ratio, scaled up
# to a size that actually reads at icon scale.
_base_outer_r, _base_ac_dx, _base_ac_dy = 16.0, -7.3, 9.7
_ac_offset_mag = math.hypot(_base_ac_dx, _base_ac_dy) / _base_outer_r  # ratio, ~0.759
_ac_bearing = math.atan2(_base_ac_dy, _base_ac_dx)                     # ~127 deg, unchanged
AC_DX = _ac_offset_mag * OUTER_R * math.cos(_ac_bearing)
AC_DY = _ac_offset_mag * OUTER_R * math.sin(_ac_bearing)
AC_NOSE_LEN = 0.44 * OUTER_R     # 8.8px -- clearly a triangle, not a speck
AC_TAIL_LEN = 0.26 * OUTER_R     # 5.2px
AC_WING_ANGLE = 2.5  # radians -- an angle, does not scale

WHITE = (255, 255, 255, 255)
# PR_COL_AIRCRAFT = 0xF904 decoded to RGB8
AIRCRAFT_RED = (255, 33, 33, 255)
# PR_COL_RING = 0x0304 decoded to RGB8 (in-app crosshair/ring colour)
RING_GREEN_INAPP = (0, 99, 33, 255)
# existing planeradar_active.png accent (sampled)
ACCENT_GREEN = (0, 255, 0, 255)
ACCENT_CYAN = (64, 220, 255, 255)
# "blue background" fill candidates
BG_BLUE = (18, 54, 140, 255)


def s(v):
    return int(round(v * SS))


def draw_planeradar(circle_cross_color, aircraft_color=None, bg_fill=None,
                     include_aircraft=True):
    big = Image.new("RGBA", (CANVAS * SS, CANVAS * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)

    cx, cy = CENTER, CENTER
    cross_len = OUTER_R          # bars flush to circle bbox, as in the original

    if bg_fill is not None:
        d.ellipse([s(cx - OUTER_R), s(cy - OUTER_R), s(cx + OUTER_R), s(cy + OUTER_R)],
                   fill=bg_fill)

    # two concentric rings
    for r in (OUTER_R, INNER_R):
        d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)],
                   outline=circle_cross_color, width=s(RING_W))

    # cross, flush to outer ring bbox
    d.rectangle([s(cx - cross_len), s(cy - CROSS_HW), s(cx + cross_len), s(cy + CROSS_HW)],
                fill=circle_cross_color)
    d.rectangle([s(cx - CROSS_HW), s(cy - cross_len), s(cx + CROSS_HW), s(cy + cross_len)],
                fill=circle_cross_color)

    if include_aircraft:
        ac = aircraft_color or circle_cross_color
        # bottom-left quadrant, same radial slot (scaled) as the old dot
        acx, acy = cx + AC_DX, cy + AC_DY
        heading = math.radians(-40)  # pointing up-right, away from centre
        tip = (acx + AC_NOSE_LEN * math.cos(heading), acy + AC_NOSE_LEN * math.sin(heading))
        left = (acx + AC_TAIL_LEN * math.cos(heading + AC_WING_ANGLE),
                 acy + AC_TAIL_LEN * math.sin(heading + AC_WING_ANGLE))
        right = (acx + AC_TAIL_LEN * math.cos(heading - AC_WING_ANGLE),
                  acy + AC_TAIL_LEN * math.sin(heading - AC_WING_ANGLE))
        d.polygon([s(tip[0]), s(tip[1]), s(left[0]), s(left[1]), s(right[0]), s(right[1])],
                   fill=ac)

    return big.resize((CANVAS, CANVAS), Image.LANCZOS)


def composite_on(img, bg_rgb):
    bg = Image.new("RGBA", img.size, bg_rgb + (255,))
    bg.paste(img, mask=img.split()[3])
    return bg.convert("RGB")


def upscale(img, factor, nearest=True):
    return img.resize((img.width * factor, img.height * factor),
                       Image.NEAREST if nearest else Image.LANCZOS)


def simulate_baked(img_rgba, bake_w=24, bake_h=24, bg_rgb=TASKBAR_BG):
    """Mimic gen_taskbar_icons.py: resize to baked size, alpha-composite over
    the taskbar bg. Shows what actually ships to the DUT (RGB565 quantization
    itself is skipped here as it's visually negligible for a preview)."""
    small = img_rgba.resize((bake_w, bake_h), Image.LANCZOS)
    return composite_on(small, bg_rgb)


# ---------------------------------------------------------------------------
# WebRadio: orange -> red recolour filter, simulating an on-DUT runtime filter
# over the EXISTING spotify_active.png (the winamp bolt icon already used for
# the player slot) rather than baking a whole new webradio icon.
#
# v1 was a flat RGB-channel threshold (r>140, b<120, g<r-30) that only caught
# the deep saturated orange (251,140,0), missing the pale highlight orange
# (255,204,128) -- its B channel (128) sits just above the b<120 cutoff.
# v2 (below): both shades measured at H=~33-36 deg, S=1.0 / S=0.5 respectively
# (colorsys.rgb_to_hsv) -- same hue family, just different saturation. A hue
# rotation catches both by construction and preserves the original tonal
# design (the highlight stays a lighter/less-saturated tint of the body
# colour, same as the source art), rather than an ad-hoc per-channel hack.
# ---------------------------------------------------------------------------
import colorsys


def recolor_hue_rotate(img_rgba, hue_shift_deg=-30, hue_lo=20, hue_hi=50,
                        sat_min=0.35, sat_boost=1.0):
    """Rotate hue by hue_shift_deg for any pixel whose hue falls in
    [hue_lo, hue_hi] and whose saturation exceeds sat_min (excludes the
    achromatic white/grey/black line art, which has S~0). Optionally scales
    saturation by sat_boost afterwards (clamped to 1.0) to keep the rotated
    highlight from reading as too pale/pink. Runs on the same cheap per-pixel
    loop as v1 -- HSV<->RGB conversion is a handful of comparisons/multiplies,
    trivial for a 24x24 slot at repaint time on the ESP32."""
    img = img_rgba.convert("RGBA")
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            hdeg = h * 360
            if s < sat_min or not (hue_lo <= hdeg <= hue_hi):
                continue
            hdeg = (hdeg + hue_shift_deg) % 360
            s2 = min(1.0, s * sat_boost)
            r2, g2, b2 = colorsys.hsv_to_rgb(hdeg / 360, s2, v)
            px[x, y] = (round(r2 * 255), round(g2 * 255), round(b2 * 255), a)
    return img


def main():
    variants = {
        "active_green": dict(circle_cross_color=ACCENT_GREEN, aircraft_color=AIRCRAFT_RED, bg_fill=BG_BLUE),
    }

    inactive = draw_planeradar(WHITE, aircraft_color=None, bg_fill=None, include_aircraft=False)
    inactive.save(OUT_DIR / "planeradar_inactive_draft.png")

    actives = {}
    for name, kw in variants.items():
        img = draw_planeradar(**kw, include_aircraft=True)
        img.save(OUT_DIR / f"planeradar_{name}_draft.png")
        actives[name] = img

    # WebRadio filter demo -- v2 candidates (hue-rotation, catches both orange
    # shades) vs the v1 flat-channel filter for reference (kept faithful to
    # what actually shipped, not the new helper, so the comparison is honest).
    def recolor_orange_to_red_v1(img_rgba):
        img = img_rgba.convert("RGBA")
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                if r > 140 and b < 120 and g < r - 30:
                    px[x, y] = (r, int(g * 0.25), b, a)
        return img

    spotify_active = Image.open(ICONS_DIR / "spotify_active.png").convert("RGBA")
    webradio_variants = {
        "webradio_v1_flat_channel": recolor_orange_to_red_v1(spotify_active),
        "webradio_v2_hue_rotate_-30": recolor_hue_rotate(spotify_active, hue_shift_deg=-30),
        "webradio_v2_hue_rotate_-30_satboost": recolor_hue_rotate(spotify_active, hue_shift_deg=-30, sat_boost=1.4),
        "webradio_v2_hue_rotate_-33": recolor_hue_rotate(spotify_active, hue_shift_deg=-33),
    }

    for name, img in webradio_variants.items():
        img.save(OUT_DIR / f"{name}_draft.png")

    # -----------------------------------------------------------------------
    # Contact sheet: for each candidate show (a) clean supersampled render,
    # (b) simulated 24x24-baked-then-upscaled result (what ships), on the
    # real taskbar bg colour.
    # -----------------------------------------------------------------------
    cell = 200
    pad = 16
    label_h = 24
    cols = 2
    rows_imgs = [("inactive", inactive)] + [(n, i) for n, i in actives.items()] \
        + [("spotify_active (orig)", spotify_active)] \
        + list(webradio_variants.items())

    sheet_w = cols * cell + (cols + 1) * pad
    sheet_h = len(rows_imgs) * (cell // 2 + label_h) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (40, 40, 40))
    from PIL import ImageFont
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    dctx = ImageDraw.Draw(sheet)

    y = pad
    row_h = cell // 2
    for name, img in rows_imgs:
        big_preview = composite_on(upscale(img, 6, nearest=False), TASKBAR_BG)
        baked_preview = upscale(simulate_baked(img.convert("RGBA")), 8)

        dctx.text((pad, y), f"{name}  (left: clean draft, right: simulated 24x24 baked)",
                   fill=(230, 230, 230), font=font)
        y2 = y + label_h
        bp = big_preview.resize((row_h, row_h))
        kp = baked_preview.resize((row_h, row_h))
        sheet.paste(bp, (pad, y2))
        sheet.paste(kp, (pad * 2 + row_h, y2))
        y = y2 + row_h + pad

    sheet.save(OUT_DIR / "CONTACT_SHEET.png")
    print(f"Wrote drafts + contact sheet to {OUT_DIR}")


if __name__ == "__main__":
    main()
