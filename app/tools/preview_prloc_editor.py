#!/usr/bin/env python3
"""preview_prloc_editor.py — TASK-317 (M-PR-LOCATIONS Phase-0): static frames
for the Settings → Applications → PlaneRadar "Locations" sub-view and the
~8-state slot editor (slot list, source fork, lookup chain, manual chain,
confirm, delete).

Standalone tool. Does NOT import or modify preview_planeradar.py — this is a
Settings-UI preview, not a radar-canvas preview, and the two eyeball gates
(strip layout vs editor screen-flow) are independent per the design doc.

Renders headless (no pygame window) — this is a static-frame layout/wording
tap-target review, not an interaction rehearsal (per the design doc: "static
frames are enough — the point is layout + wording + tap-target sizes, not
interaction").

Geometry mirrors app/src/settings/settingsSection.h (S_CANVAS_W/H,
S_HEADER_H, S_CONTENT_Y, S_ROW_H, colour palette) and the button/spinner
conventions in app/src/settings/wifiSection.h (repaintConnecting/_drawSpinner,
Retry/Cancel button layout) and app/src/settings/keyboardWidget.h (OK/action
key colour language) — hardcoded here (not parsed from the headers) since
this tool predates the C++ these constants will land in; see BP-048 lineage
(preview decides layout before firmware code exists).

Font: dut_fonts.Font2 (TFT_eSPI Font16 / setTextFont(2)) — the only font
size settingsSection.h's row/header helpers ever use, so this is the
pixel-accurate on-device look, not a TrueType approximation. The contact
sheet's captions use PIL's default bitmap font (host-only review aid, not
on-device UI).

Data: NL postcode 2513AA (The Hague) is the real phase-0 probe result
(docs/architecture/designs/M-PR-LOCATIONS/phase0-geocode-probe.md) —
lat 52.0795389, display_name "2513 AA, Centrum, Den Haag, Zuid-Holland,
Nederland". Longitude wasn't recorded in the probe's committed table (only
lat was); 4.3132 is The Hague's real longitude, used here as realistic
fill, not a probed value — flagged in TASK-317's tasks.md close-out note.

Usage:
    ~/proj/esp/venv/bin/python3 app/tools/preview_prloc_editor.py
"""
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

_HERE = pathlib.Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import dut_fonts

# ── output location ───────────────────────────────────────────────────────────

OUT_DIR = _HERE.parent.parent / "docs" / "architecture" / "designs" / "M-PR-LOCATIONS" / "img"

# ── geometry (mirrors app/src/settings/settingsSection.h) ─────────────────────

S_CANVAS_W    = 275
S_CANVAS_H    = 240
S_HEADER_H    = 28
S_CONTENT_Y   = 28
S_CONTENT_H   = 212
S_ROW_H       = 26
S_ROW_HDR_H   = 22
S_COL_LABEL   = 8
S_COL_VALUE   = 268
S_BACK_ZONE_W = 60

# ── colour palette (RGB565 → RGB; mirrors settingsSection.h) ──────────────────

S_BG         = (33, 32, 33)      # 0x2104
S_SEP        = (66, 65, 66)      # 0x4208
S_HDR_TXT    = (255, 255, 255)   # 0xFFFF
S_LABEL      = (255, 255, 255)   # 0xFFFF
S_VALUE      = (0, 255, 255)     # 0x07FF cyan
S_VALUE_ON   = (0, 255, 0)       # 0x07E0 green
S_VALUE_OFF  = (123, 125, 123)   # 0x7BEF grey
S_SUBHDR     = (255, 255, 0)     # 0xFFE0 yellow
S_CHEVRON    = (66, 65, 66)      # 0x4208
S_ERROR      = (255, 64, 64)     # M-PLANERADAR palette "error" red equivalent
S_DANGER_BG  = (150, 20, 20)     # not-in-firmware-yet: destructive-action button fill
S_ACCENT_BG  = S_VALUE_ON        # default/recommended-choice button fill

# ── PR_* constants (from M-PR-LOCATIONS-location-presets.md) ──────────────────

PR_NUM_LOCS  = 4
PR_LABEL_MAX = 5

# ── realistic content (phase-0 probe: NL postcode 2513AA / The Hague) ─────────

DISPLAY_NAME_FULL = "2513 AA, Centrum, Den Haag, Zuid-Holland, Nederland"
DISPLAY_NAME_FW   = DISPLAY_NAME_FULL[:47]   # GeocodeResult.display[48] firmware buffer
HAGUE_LAT = 52.0795
HAGUE_LON = 4.3132

SLOTS = [
    {"label": "HOME", "lat": 52.079, "lon": 4.313,  "filled": True,  "active": True},
    {"label": "LDN",  "lat": 51.501, "lon": -0.142, "filled": True,  "active": False},
    {"label": "",     "lat": 0.0,    "lon": 0.0,     "filled": False, "active": False},
    {"label": "BERL", "lat": 52.532, "lon": 13.405, "filled": True,  "active": False},
]

# ── fonts ──────────────────────────────────────────────────────────────────────

F1, F2 = dut_fonts.load()

# ── drawing helpers ─────────────────────────────────────────────────────────────


def new_canvas() -> Image.Image:
    return Image.new("RGB", (S_CANVAS_W, S_CANVAS_H), S_BG)


def draw_header(draw: ImageDraw.ImageDraw, title: str) -> None:
    draw.rectangle([0, 0, S_CANVAS_W - 1, S_HEADER_H - 1], fill=S_BG)
    F2.draw_left(draw, 4, S_HEADER_H // 2, "< back", fg=S_HDR_TXT)
    F2.draw_right(draw, S_CANVAS_W - 4, S_HEADER_H // 2, title, fg=S_HDR_TXT)
    draw.line([0, S_HEADER_H - 1, S_CANVAS_W - 1, S_HEADER_H - 1], fill=S_SEP)


def draw_row(draw: ImageDraw.ImageDraw, y: int, label: str, value: str,
             label_fg=S_LABEL, value_fg=S_VALUE, row_h: int = S_ROW_H) -> None:
    mid = y + row_h // 2
    F2.draw_left(draw, S_COL_LABEL, mid, label, fg=label_fg)
    F2.draw_right(draw, S_COL_VALUE, mid, value, fg=value_fg)


def draw_sub_header(draw: ImageDraw.ImageDraw, y: int, text: str) -> int:
    F2.draw_left(draw, S_COL_LABEL, y + 4 + F2.CHAR_H // 2, text, fg=S_SUBHDR)
    draw.line([S_COL_LABEL, y + S_ROW_HDR_H - 1, S_CANVAS_W - 1, y + S_ROW_HDR_H - 1],
              fill=S_SEP)
    return y + S_ROW_HDR_H


def draw_active_bar(draw: ImageDraw.ImageDraw, y: int, row_h: int = S_ROW_H) -> None:
    """3px green accent bar — same visual language as the taskbar active
    indicator (preview_common.py TASKBAR_ACTIVE_COL)."""
    draw.rectangle([0, y, 2, y + row_h - 1], fill=S_VALUE_ON)


def draw_button(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                 label: str, bg, fg, disabled: bool = False) -> None:
    if disabled:
        bg = S_BG
        fg = S_VALUE_OFF
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=bg, outline=S_SEP)
    F2.draw_centered(draw, x + w // 2, y + h // 2, label, fg=fg)


def draw_spinner(draw: ImageDraw.ImageDraw, cx: int, cy: int, frame: str = "|") -> None:
    F2.draw_centered(draw, cx, cy, frame, fg=S_VALUE)


def wrap_to_width(text: str, max_w: int, font=F2) -> list[str]:
    """Greedy word-wrap using measured Font2 pixel widths."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        if font.text_width(cand) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def save(img: Image.Image, name: str) -> pathlib.Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    img.save(path)
    print(f"wrote {path} ({path.stat().st_size} B)")
    return path


# ── frame 1: Locations sub-view (slot list) ────────────────────────────────────

def frame_slotlist() -> Image.Image:
    img = new_canvas()
    draw = ImageDraw.Draw(img)
    draw_header(draw, "Locations")

    y = S_CONTENT_Y
    for slot in SLOTS:
        if slot["active"]:
            draw_active_bar(draw, y)
        if slot["filled"]:
            coord = f"{slot['lat']:.3f},{slot['lon']:.3f}"
            label_fg = S_VALUE_ON if slot["active"] else S_LABEL
            draw_row(draw, y, slot["label"], coord, label_fg=label_fg)
        else:
            F2.draw_centered(draw, S_CANVAS_W // 2, y + S_ROW_H // 2,
                              "-- empty --", fg=S_VALUE_OFF)
        y += S_ROW_H

    y += 10
    F2.draw_left(draw, S_COL_LABEL, y + F2.CHAR_H // 2, "Tap a slot to edit",
                 fg=S_VALUE_OFF)
    return img


# ── frame 2/2b: coordinate-source fork ─────────────────────────────────────────

BTN_FORK_X = 16
BTN_FORK_W = S_CANVAS_W - 2 * BTN_FORK_X   # 243
BTN_FORK_H = 40
BTN_FORK_GAP = 10
BTN_FORK_Y0 = 70


def _frame_source_fork(slot_label: str, coord: str, slot0: bool) -> Image.Image:
    img = new_canvas()
    draw = ImageDraw.Draw(img)
    draw_header(draw, f"Edit {slot_label}")

    # Current-value context row
    draw_row(draw, S_CONTENT_Y, "Current", coord, value_fg=S_VALUE_OFF)

    y = BTN_FORK_Y0
    draw_button(draw, BTN_FORK_X, y, BTN_FORK_W, BTN_FORK_H,
                "Lookup  (country + postcode)", bg=S_ACCENT_BG, fg=(0, 0, 0))
    y += BTN_FORK_H + BTN_FORK_GAP
    draw_button(draw, BTN_FORK_X, y, BTN_FORK_W, BTN_FORK_H,
                "Manual  (lat / lon)", bg=S_SEP, fg=S_HDR_TXT)
    y += BTN_FORK_H + BTN_FORK_GAP

    if slot0:
        draw_button(draw, BTN_FORK_X, y, BTN_FORK_W, BTN_FORK_H,
                    "Delete", bg=None, fg=None, disabled=True)
        y += BTN_FORK_H + 6
        F2.draw_centered(draw, S_CANVAS_W // 2, y + F2.CHAR_H // 2,
                          "slot 0 is always defined", fg=S_VALUE_OFF)
    else:
        draw_button(draw, BTN_FORK_X, y, BTN_FORK_W, BTN_FORK_H,
                    "Delete", bg=S_DANGER_BG, fg=S_HDR_TXT)

    return img


def frame_source_fork() -> Image.Image:
    return _frame_source_fork("LDN", "51.501,-0.142", slot0=False)


def frame_source_fork_slot0() -> Image.Image:
    return _frame_source_fork("HOME", "52.079,4.313", slot0=True)


# ── frame 3: lookup pending (spinner) ──────────────────────────────────────────

def frame_lookup_pending() -> Image.Image:
    img = new_canvas()
    draw = ImageDraw.Draw(img)
    draw_header(draw, "Edit HAGUE")

    draw_row(draw, S_CONTENT_Y, "Country", "NL")
    draw_row(draw, S_CONTENT_Y + S_ROW_H, "Postcode", "2513AA")

    cy = S_CONTENT_Y + 2 * S_ROW_H + 40
    F2.draw_centered(draw, S_CANVAS_W // 2, cy, "Looking up...", fg=S_LABEL)
    draw_spinner(draw, S_CANVAS_W // 2, cy + 28, "/")
    F2.draw_centered(draw, S_CANVAS_W // 2, cy + 52, "fetching from Nominatim",
                      fg=S_VALUE_OFF)
    return img


# ── frame 4: lookup confirm (Save / Retry / Cancel) ────────────────────────────

BTN3_MARGIN = 8
BTN3_GAP = 8
BTN3_W = (S_CANVAS_W - 2 * BTN3_MARGIN - 2 * BTN3_GAP) // 3
BTN3_H = 40
BTN3_Y = 192


def _draw_3btn_row(draw: ImageDraw.ImageDraw, labels_bgs_fgs) -> None:
    x = BTN3_MARGIN
    for i, (label, bg, fg) in enumerate(labels_bgs_fgs):
        w = BTN3_W if i < 2 else (S_CANVAS_W - BTN3_MARGIN - x)
        draw_button(draw, x, BTN3_Y, w, BTN3_H, label, bg=bg, fg=fg)
        x += w + BTN3_GAP


def frame_lookup_confirm() -> Image.Image:
    img = new_canvas()
    draw = ImageDraw.Draw(img)
    draw_header(draw, "Edit HAGUE")

    y = S_CONTENT_Y + 4
    lines = wrap_to_width(DISPLAY_NAME_FW, S_CANVAS_W - 2 * S_COL_LABEL)
    for ln in lines[:2]:
        F2.draw_left(draw, S_COL_LABEL, y + F2.CHAR_H // 2, ln, fg=S_VALUE)
        y += F2.CHAR_H + 2
    if len(lines) > 2:
        F2.draw_left(draw, S_COL_LABEL, y + F2.CHAR_H // 2, "...", fg=S_VALUE_OFF)
        y += F2.CHAR_H + 2

    y += 8
    draw_row(draw, y, "Lat", f"{HAGUE_LAT:.4f}")
    y += S_ROW_H
    draw_row(draw, y, "Lon", f"{HAGUE_LON:.4f}")

    _draw_3btn_row(draw, [
        ("Save",   S_ACCENT_BG, (0, 0, 0)),
        ("Retry",  S_SEP,       S_HDR_TXT),
        ("Cancel", S_SEP,       S_HDR_TXT),
    ])
    return img


# ── frame 5: lookup error (Retry / Cancel) ─────────────────────────────────────

BTN2_MARGIN = 16
BTN2_GAP = 27
BTN2_W = (S_CANVAS_W - 2 * BTN2_MARGIN - BTN2_GAP) // 2
BTN2_H = 40
BTN2_Y = 178


def frame_lookup_error() -> Image.Image:
    img = new_canvas()
    draw = ImageDraw.Draw(img)
    draw_header(draw, "Edit HAGUE")

    draw_row(draw, S_CONTENT_Y, "Country", "NL", value_fg=S_VALUE_OFF)
    draw_row(draw, S_CONTENT_Y + S_ROW_H, "Postcode", "1000ZZ", value_fg=S_VALUE_OFF)

    ey = S_CONTENT_Y + 2 * S_ROW_H + 30
    F2.draw_centered(draw, S_CANVAS_W // 2, ey, "-96 GEOCODE_NO_MATCH", fg=S_ERROR)
    F2.draw_centered(draw, S_CANVAS_W // 2, ey + 20, "postcode not found", fg=S_VALUE_OFF)

    x = BTN2_MARGIN
    draw_button(draw, x, BTN2_Y, BTN2_W, BTN2_H, "Retry", bg=S_ACCENT_BG, fg=(0, 0, 0))
    x += BTN2_W + BTN2_GAP
    draw_button(draw, x, BTN2_Y, BTN2_W, BTN2_H, "Cancel", bg=S_SEP, fg=S_HDR_TXT)
    return img


# ── frame 6: manual confirm (Save / Cancel) ────────────────────────────────────

def frame_manual_confirm() -> Image.Image:
    img = new_canvas()
    draw = ImageDraw.Draw(img)
    draw_header(draw, "Edit HAGUE")

    y = S_CONTENT_Y
    draw_row(draw, y, "Lat", f"{HAGUE_LAT:.4f}")
    y += S_ROW_H
    draw_row(draw, y, "Lon", f"{HAGUE_LON:.4f}")
    y += S_ROW_H + 12

    F2.draw_left(draw, S_COL_LABEL, y + F2.CHAR_H // 2,
                 "Range: lat -90..90", fg=S_VALUE_OFF)
    y += F2.CHAR_H + 4
    F2.draw_left(draw, S_COL_LABEL, y + F2.CHAR_H // 2,
                 "        lon -180..180", fg=S_VALUE_OFF)

    x = BTN2_MARGIN
    draw_button(draw, x, BTN2_Y, BTN2_W, BTN2_H, "Save", bg=S_ACCENT_BG, fg=(0, 0, 0))
    x += BTN2_W + BTN2_GAP
    draw_button(draw, x, BTN2_Y, BTN2_W, BTN2_H, "Cancel", bg=S_SEP, fg=S_HDR_TXT)
    return img


# ── contact sheet ────────────────────────────────────────────────────────────────

def _pil_wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """Greedy word-wrap against a PIL font's measured pixel width."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        w_px = draw.textbbox((0, 0), cand, font=font)[2]
        if w_px <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_contact_sheet(frames: list[tuple[str, str, Image.Image]]) -> Image.Image:
    """frames: list of (filename, caption, PIL Image). Host-review aid only —
    captions use PIL's default bitmap font (not on-device UI)."""
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    scale = 0.85
    thumb_w = int(S_CANVAS_W * scale)
    thumb_h = int(S_CANVAS_H * scale)
    pad = 18
    line_h = 15
    cap_lines_max = 3   # caption wraps to at most this many lines
    caption_h = cap_lines_max * line_h + line_h + 8   # + filename line + gap

    cell_w = thumb_w + pad
    cell_h = thumb_h + caption_h + pad

    sheet_w = cols * cell_w + pad
    sheet_h = rows * cell_h + pad + 34  # +34 title band

    sheet = Image.new("RGB", (sheet_w, sheet_h), (16, 16, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        title_font = ImageFont.load_default(size=16)
        cap_font = ImageFont.load_default(size=12)
    except TypeError:
        title_font = ImageFont.load_default()
        cap_font = ImageFont.load_default()

    draw.text((pad, 8), "TASK-317 -- M-PR-LOCATIONS editor screen-flow "
                          "(eyeball gate)", fill=(255, 255, 255), font=title_font)

    for i, (fname, caption, img) in enumerate(frames):
        col = i % cols
        row = i // cols
        x0 = pad + col * cell_w
        y0 = 34 + pad + row * cell_h

        thumb = img.resize((thumb_w, thumb_h), Image.LANCZOS)
        sheet.paste(thumb, (x0, y0))
        draw.rectangle([x0, y0, x0 + thumb_w - 1, y0 + thumb_h - 1],
                       outline=(90, 90, 90))

        cap_lines = _pil_wrap(draw, caption, cap_font, thumb_w)[:cap_lines_max]
        cy = y0 + thumb_h + 6
        for ln in cap_lines:
            draw.text((x0, cy), ln, fill=(200, 200, 200), font=cap_font)
            cy += line_h
        draw.text((x0, y0 + thumb_h + caption_h - line_h), fname,
                  fill=(120, 120, 120), font=cap_font)

    return sheet


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    frame_specs = [
        ("editor_slotlist.png", "1. Locations sub-view -- slot list, "
         "active marker, empty slot", frame_slotlist),
        ("editor_source_fork.png", "2. Source fork (non-empty slot) -- "
         "Lookup / Manual / Delete", frame_source_fork),
        ("editor_source_fork_slot0.png", "2b. Source fork, slot 0 -- "
         "Delete disabled (not deletable)", frame_source_fork_slot0),
        ("editor_lookup_pending.png", "3. Lookup pending -- spinner, "
         "entered country/postcode", frame_lookup_pending),
        ("editor_lookup_confirm.png", "4. Lookup confirm -- display_name, "
         "lat/lon, Save/Retry/Cancel", frame_lookup_confirm),
        ("editor_lookup_error.png", "5. Lookup error -- decoded error line, "
         "Retry/Cancel", frame_lookup_error),
        ("editor_manual_confirm.png", "6. Manual confirm -- entered lat/lon, "
         "validation hint, Save/Cancel", frame_manual_confirm),
    ]

    rendered: list[tuple[str, str, Image.Image]] = []
    for fname, caption, fn in frame_specs:
        img = fn()
        save(img, fname)
        rendered.append((fname, caption, img))

    sheet = build_contact_sheet(rendered)
    save(sheet, "editor_frames_sheet.png")


if __name__ == "__main__":
    main()
