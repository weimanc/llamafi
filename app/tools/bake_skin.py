#!/usr/bin/env python3
"""Bake a Winamp 2 .wsz skin into RGB565 C arrays + layout header.

Tier 1 scope: main background, transport buttons, bitmap font (raw atlas).
Output: gen/skin_assets.c, gen/skin_layout.h

Usage:
  python3 bake_skin.py -i ../skins/winamp2_base.wsz -o ../SpotifyDiyThing/gen
  python3 bake_skin.py -i ../skins/winamp2_base.wsz -o ../SpotifyDiyThing/gen --preview /tmp/skin_preview.png
"""
import argparse
import io
import pathlib
import struct
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image, ImageDraw


def to_rgb565_le(img: Image.Image) -> bytes:
    """RGB565 little-endian byte string for an image."""
    rgb = img.convert("RGB")
    out = bytearray(rgb.width * rgb.height * 2)
    i = 0
    for r, g, b in rgb.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[i] = v & 0xFF
        out[i + 1] = v >> 8
        i += 2
    return bytes(out)


def emit_array(name: str, data: bytes, w: int, h: int, fp) -> None:
    fp.write(f"// {name}: {w}x{h}, {len(data)} bytes RGB565 LE\n")
    fp.write(f"const uint16_t {name}[{w * h}] = {{\n")
    # 12 words per line keeps the file readable but compact.
    for i in range(0, len(data), 24):
        chunk = data[i:i + 24]
        words = [
            f"0x{chunk[j + 1]:02x}{chunk[j]:02x}"
            for j in range(0, len(chunk), 2)
        ]
        fp.write("  " + ", ".join(words) + ",\n")
    fp.write("};\n\n")


def open_skin(wsz_path: pathlib.Path) -> tuple[zipfile.ZipFile, str]:
    z = zipfile.ZipFile(wsz_path)
    # Skins are usually packaged inside a single directory; detect it.
    prefix = ""
    for name in z.namelist():
        if name.endswith("/") and "/" not in name.rstrip("/"):
            prefix = name
            break
    return z, prefix


def _decode_via_imagemagick(raw: bytes) -> Image.Image:
    # Pillow's BI_RLE8 decoder fails on some Winamp BMPs (e.g. TEXT.BMP).
    # ImageMagick handles them; round-trip through PNG.
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as src, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as dst:
        src.write(raw)
        src.flush()
        subprocess.run(["magick", src.name, dst.name], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return Image.open(dst.name).copy()


def _decode_bmp_rle8(raw: bytes) -> Image.Image | None:
    """Spec-compliant BI_RLE8 decoder for 8-bit Windows BMPs.

    Returns None if `raw` is not an 8 bpp RLE-compressed BMP — caller
    should then fall through to Pillow / ImageMagick.

    Pillow's RLE8 decoder silently produces garbage on some Winamp skin
    BMPs (verified 2026-05-09 on BALANCE.BMP in base-2.91.wsz: ~56 %
    pixel mismatch vs both a manual decode AND ffmpeg, which agree
    byte-for-byte). ImageMagick fails outright (`unable to runlength
    decode`) on the same files. We do the decode ourselves so the
    output is deterministic and traceable.
    """
    if len(raw) < 54 or raw[:2] != b'BM':
        return None
    pixel_offset = struct.unpack_from('<I', raw, 10)[0]
    dib_size     = struct.unpack_from('<I', raw, 14)[0]
    width        = struct.unpack_from('<i', raw, 18)[0]
    height_signed = struct.unpack_from('<i', raw, 22)[0]
    bpp          = struct.unpack_from('<H', raw, 28)[0]
    compression  = struct.unpack_from('<I', raw, 30)[0]
    if bpp != 8 or compression != 1:
        return None

    pal_off = 14 + dib_size
    palette = [
        (raw[pal_off + i*4 + 2], raw[pal_off + i*4 + 1], raw[pal_off + i*4])
        for i in range(256)
    ]
    bottom_up = height_signed > 0
    h = abs(height_signed)
    out = [[0] * width for _ in range(h)]

    p = pixel_offset
    x = 0
    y = h - 1 if bottom_up else 0
    while p + 1 < len(raw):
        n = raw[p]; v = raw[p + 1]; p += 2
        if n == 0:
            if v == 0:                        # end-of-line
                x = 0
                y = y - 1 if bottom_up else y + 1
            elif v == 1:                      # end-of-bitmap
                break
            elif v == 2:                      # delta(dx, dy)
                if p + 1 >= len(raw): break
                dx = raw[p]; dy = raw[p + 1]; p += 2
                x += dx
                y = y - dy if bottom_up else y + dy
            else:                             # absolute run of v indexed pixels
                run = v
                for i in range(run):
                    if 0 <= y < h and 0 <= x < width and p + i < len(raw):
                        out[y][x] = raw[p + i]
                    x += 1
                p += run
                if run & 1:                   # 16-bit padded
                    p += 1
        else:                                  # encoded run: n × v
            for _ in range(n):
                if 0 <= y < h and 0 <= x < width:
                    out[y][x] = v
                x += 1

    img = Image.new('RGB', (width, h))
    pixels = img.load()
    for j in range(h):
        row = out[j]
        for i in range(width):
            pixels[i, j] = palette[row[i]]
    return img


def load_bmp(z: zipfile.ZipFile, prefix: str, fname: str) -> Image.Image:
    target = (prefix + fname).upper()
    for n in z.namelist():
        if n.upper() == target:
            raw = z.read(n)
            # Try the manual BI_RLE8 decoder FIRST. Pillow silently
            # mis-decodes some Winamp RLE8 BMPs without raising — the
            # try/except below would never catch it.
            manual = _decode_bmp_rle8(raw)
            if manual is not None:
                return manual
            try:
                img = Image.open(io.BytesIO(raw))
                img.load()
                return img
            except (ValueError, OSError):
                return _decode_via_imagemagick(raw)
    raise FileNotFoundError(f"{fname} not found in skin (prefix={prefix!r})")


# Winamp 2 text.bmp font: 31 cols × 3 rows of 5×6 glyphs.
# Row 0: A-Z, ", @, 3 trailing blanks. Row 1: digits + punctuation. Row 2: rarely
# populated in classic skins beyond ? and *. Spaces in CHAR_MAP mean "blank cell"
# (kept for column alignment); unmapped ASCII resolves to BLANK_GLYPH.
GLYPH_W, GLYPH_H = 5, 6
CHAR_MAP = [
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ\"@   ",
    "0123456789\x85:.()-'!_+\\/[]^&%,=$#",
    "?*                             ",
]
BLANK_COL, BLANK_ROW = 29, 0  # known-empty cell in row 0


def build_glyph_table() -> list[tuple[int, int]]:
    pos = {}
    for r, row in enumerate(CHAR_MAP):
        for c, ch in enumerate(row):
            if ch == " " or ch == "\x85":
                if ch == "\x85":
                    pos[ord("\x85")] = (c, r)  # ellipsis
                continue
            pos.setdefault(ord(ch), (c, r))
    table = []
    blank = (BLANK_COL, BLANK_ROW)
    for code in range(128):
        ch = chr(code)
        if ch.islower():
            table.append(pos.get(ord(ch.upper()), blank))
        else:
            table.append(pos.get(code, blank))
    return table


# Winamp 2 main-window standard sprite layout for cbuttons.bmp.
# Top row (y=0) is normal, bottom row (y=18) is pressed.
CBUTTON_SPRITES = [
    ("PREV",  0, 23, 18),
    ("PLAY", 23, 23, 18),
    ("PAUSE", 46, 23, 18),
    ("STOP", 69, 23, 18),
    ("NEXT", 92, 22, 18),
]

# Screen positions on the 275x116 main window.
CBUTTON_POSITIONS = [
    ("PREV",  16, 88),
    ("PLAY",  39, 88),
    ("PAUSE", 62, 88),
    ("STOP",  85, 88),
    ("NEXT", 108, 88),
]


# Tier-3 sprite sheets baked as separate atlases (the runtime renders
# them dynamically). MONOSTER moved out per ADR-014 — it's now composited
# onto MAIN_BG at bake time (static "STEREO lit / mono dim").
# VOLUME.BMP loaded raw, then post-processed into a 6-keyframe atlas
# (5 source frames + synthesised KEYFRAME_NONE) per ADR-014 Amendment 1.
# SHUFREP loaded raw and post-processed into a packed 75x30 atlas
# (4 sprites: REPEAT_OFF/ON + SHUFFLE_OFF/ON, normal-state only) for
# the chrome-001 shuffle/repeat indicators driven by Spotify state.
TIER3_SHEETS = ["NUMBERS.BMP", "POSBAR.BMP", "PLAYPAUS.BMP", "VOLUME.BMP",
                 "SHUFREP.BMP"]

# Static-decoration sources composited onto MAIN_BG at bake time per
# ADR-014. Loaded but never emitted as their own atlas. SHUFREP added
# 2026-05-09 for the EQ-off + PL-on indicator pair.
COMPOSITE_SOURCES = ["TITLEBAR.BMP", "BALANCE.BMP", "MONOSTER.BMP", "TEXT.BMP",
                      "SHUFREP.BMP"]

# Winamp's transparency-key colour for BALANCE (cyan-ish). Pixels matching
# this in the source BMP get skipped during composite so MAIN_BG shows
# through. Tolerance handles palette quantisation.
BALANCE_TRANSPARENT_RGB = (0, 198, 255)
BALANCE_TRANSPARENT_TOL = 30

# Per-sheet sprite UVs. Values are canonical Winamp 2.x main-window layout.
NUMBERS_LAYOUT = {
    "DIGIT_W": 9, "DIGIT_H": 13,
}  # eleven 9x13 cells across; index 0..9 = digits, index 10 = blank/minus

POSBAR_LAYOUT = {
    "POSBAR_BG":      (  0, 0, 248, 10),
    "POSBAR_THUMB_N": (248, 0,  29, 10),
    "POSBAR_THUMB_P": (278, 0,  29, 10),
    "POSBAR_X": 16, "POSBAR_Y": 72,
}

PLAYPAUS_LAYOUT = {
    # 9x9 status icons. Index in canonical Winamp order.
    "PP_PLAY":   ( 0, 0, 9, 9),
    "PP_PAUSE":  ( 9, 0, 9, 9),
    "PP_STOP":   (18, 0, 9, 9),
    "PP_OFF":    (27, 0, 9, 9),
    "PP_X": 26, "PP_Y": 28,  # main-window screen position for the indicator
}

# Winamp 2.x VOLUME slider — 28 frames stacked vertically in source BMP
# at 15 px stride, each 68×13. Per ADR-014 Amendment 1 §A1.3 we keep
# 5 keyframes (low/quarter/mid/threequarter/max) + synthesise a 6th
# KEYFRAME_NONE for "no active device". Atlas layout in emitted form:
#   row 0 = NONE, row 1 = KF0, row 2 = KF1, row 3 = KF2, row 4 = KF3, row 5 = KF4
# (NONE first so it's the easiest to eyeball in the atlas dump.)
VOLUME_FRAME_W = 68
VOLUME_FRAME_H = 13
VOLUME_FRAME_STRIDE = 15
VOLUME_KEYFRAMES = [0, 7, 14, 20, 27]  # source-frame indices (A1.3)

VOLUME_LAYOUT = {
    "VOLUME_KEYFRAME_NONE": (0,  0, 68, 13),
    "VOLUME_KEYFRAME_0":    (0, 13, 68, 13),
    "VOLUME_KEYFRAME_1":    (0, 26, 68, 13),
    "VOLUME_KEYFRAME_2":    (0, 39, 68, 13),
    "VOLUME_KEYFRAME_3":    (0, 52, 68, 13),
    "VOLUME_KEYFRAME_4":    (0, 65, 68, 13),
    "VOLUME_X": 107, "VOLUME_Y": 57,
    "VOLUME_W": 68, "VOLUME_H": 13,
}

# Volume knob — per ADR-016, shares the BALANCE.BMP knob crop. Single
# 14×11 sprite, emitted as a separate uint16_t array (308 bytes flash)
# rather than padded into the 68-wide SKIN_VOLUME atlas.
VOLUME_KNOB_SOURCE_RECT = (15, 422, 14, 11)
VOLUME_KNOB_W = 14
VOLUME_KNOB_H = 11
# Synthetic key used to pass the cropped knob image through the
# extras dict to emit_assets / emit_layout_header alongside the other
# atlases. NOT a real BMP filename in the .wsz.
VOLUME_KNOB_KEY = "VOLUME_KNOB.BMP"

# PLEDIT playlist editor chrome (ADR-018, Amendment 1 — 2026-05-15).
# Sprite positions from Audacious skin.cc / playlist-widget.cc (canonical
# Winamp 2.x implementation). See docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md.
#
# base-2.91.wsz PLEDIT.BMP is 280×186 (non-standard width; 275+5 scrollbar extra).
# Band layout (y axis, Audacious-confirmed):
#   Title focused:  y=0..19  (20px)   ← skin_draw_playlistwin_frame y=focused?0:21
#   Title inactive: y=21..40 (20px)   ← unused in our single-window layout
#   Frame sides:    y=42..70 (29px)   ← left tile(0,42,12,29) + right tile(32,42,19,29)
#   Bottom bar:     y=72..109 (38px)  ← left/menu(0,72,125,38) + right/btns(126,72,150,38)
# y=111+: additional button states (hover/press) — not used in normal rendering.
#
# Cyan (0,198,255) at y=20,41,71,110: skin-artwork palette bytes at band
# boundaries; Winamp uses hardcoded offsets, NOT these as delimiters.
#
# ROW RENDERING: playlist-widget.cc uses flat fillRect only — NO BMP sprites.
# Colours from PLEDIT.TXT: Normal=#00FF00, Current=#FFFFFF,
#   NormalBG=#000000, SelectedBG=#0000C6.
PLEDIT_BODY_BG_RGB     = (29, 29, 45)   # empirical from PLEDIT.BMP body area
PLEDIT_SELECTED_BG_RGB = (0, 0, 198)    # SelectedBG #0000C6 from PLEDIT.TXT
PLEDIT_TRANSPARENT_KEY = (0, 198, 255)  # standard Winamp skin transparency key
PLEDIT_TRANSPARENT_TOL = 30             # tolerance matches BALANCE constant

PLEDIT_TITLE_Y0      = 0
PLEDIT_TITLE_H_SRC   = 20   # y=0..19, confirmed Audacious focused band
PLEDIT_BOTTOM_Y0_SRC = 72   # corrected: was 111; Audacious y=72..109
PLEDIT_BOTTOM_H_SRC  = 38   # corrected: was 18; Audacious h=38
PLEDIT_SRC_W         = 280  # full BMP width (275 content + 5 scrollbar extra)

# Title bar sprite geometry (Audacious skin_draw_playlistwin_frame — focused band).
# Left corner 25px, then tile the 25px repeat unit, then right corner 25px.
PLEDIT_TITLE_LEFT_X   = 0    # left corner (0,y,25,20)
PLEDIT_TITLE_LEFT_W   = 25
PLEDIT_TITLE_TILE_X   = 127  # repeat unit (127,y,152,y+20) — 25px
PLEDIT_TITLE_TILE_W   = 25
PLEDIT_TITLE_RIGHT_X  = 153  # right corner (153,y,178,y+20) — 25px
PLEDIT_TITLE_RIGHT_W  = 25

# Bottom bar sprite geometry: two fixed sections, no tiling.
# Left (menu/ADD/REM/SEL): (0,72,125,38); Right (scroll/close): (126,72,276,38).
PLEDIT_BOTTOM_LEFT_W  = 125
PLEDIT_BOTTOM_RIGHT_W = 150  # 276-126

# Frame side tile dimensions (Audacious: left tile (0,42,12,29), right tile (32,42,19,29)).
PLEDIT_SIDE_LEFT_W  = 12
PLEDIT_SIDE_RIGHT_W = 19
PLEDIT_SIDE_H_SRC   = 29   # y=42..70

# Scrollbar thumb sprite (TASK-051e) — normal state, BMP x=52, y=54, 9×17.
PLEDIT_THUMB_X0  = 52
PLEDIT_THUMB_Y0  = 54
PLEDIT_THUMB_W   = 9
PLEDIT_THUMB_H   = 17
PLEDIT_THUMB_KEY = "PLEDIT_THUMB.BMP"

# Display layout constants (emitted to skin_layout.h).
# PLEDIT_DISPLAY_W = 275 matches MAIN.BMP (main window width); left 125 + right 150 = 275.
PLEDIT_DISPLAY_Y        = 116
PLEDIT_DISPLAY_W        = 275  # matches main window width (MAIN.BMP = 275px)
PLEDIT_DISPLAY_TITLE_H  = PLEDIT_TITLE_H_SRC   # 20
PLEDIT_DISPLAY_BOTTOM_H = PLEDIT_BOTTOM_H_SRC  # 38
PLEDIT_DISPLAY_ROW_H    = 13   # 5×13=65px fits 66px available row area (20+65+38=123 of 124px)
PLEDIT_DISPLAY_ROW_COUNT = 5
# Derived:
PLEDIT_DISPLAY_ROWS_Y   = PLEDIT_DISPLAY_Y + PLEDIT_DISPLAY_TITLE_H
PLEDIT_DISPLAY_BOTTOM_Y = PLEDIT_DISPLAY_ROWS_Y + PLEDIT_DISPLAY_ROW_COUNT * PLEDIT_DISPLAY_ROW_H

# Display content area (between frame sides).
PLEDIT_CONTENT_X = PLEDIT_SIDE_LEFT_W                                       # 12
PLEDIT_CONTENT_W = PLEDIT_DISPLAY_W - PLEDIT_SIDE_LEFT_W - PLEDIT_SIDE_RIGHT_W  # 244

# Synthetic atlas keys.
PLEDIT_BG_KEY              = "PLEDIT_BG.BMP"               # 275×58 composite (title 20px + bottom 38px)
PLEDIT_SIDES_KEY           = "PLEDIT_SIDES.BMP"            # 31×29 side tiles (preview composite, not emitted)
PLEDIT_LEFT_SIDE_KEY       = "PLEDIT_LEFT_SIDE.BMP"        # 12×29 left frame tile
PLEDIT_RIGHT_SIDE_KEY      = "PLEDIT_RIGHT_SIDE.BMP"       # 19×29 right frame tile (incl. scrollbar)
PLEDIT_TITLE_INACTIVE_KEY  = "PLEDIT_TITLE_INACTIVE.BMP"   # 275×20 inactive title composite (M-CONN)
# TASK-053a (M-CONN): inactive title bar strip — TITLEBAR.BMP crop (27,14,302,28) = 275×14.
TITLEBAR_INACTIVE_KEY = "TITLEBAR_INACTIVE.BMP"

# LOGO tap zone (M-CONN TASK-053f): window-local coordinates.
LOGO_X, LOGO_Y, LOGO_W, LOGO_H = 243, 84, 32, 32

# Sample track list for skin_preview — gives a realistic feel without dynamic data.
# Row 0 is the "current" track (white text); rows 1-3 are normal (green text).
PLEDIT_PREVIEW_ROWS = [
    "1. DJ MIKE LLAMA - LLAMA WHIPPIN' INTRO   0:05",
    "2. DIABLO SWING ORCHESTRA - HEROINES       5:22",
    "3. ECLECTEK - WE ARE GOING TO ECLEFUNK     3:10",
    "4. AUTO-PILOT - SEVENTEEN                  3:34",
    "5. INFECTED MUSHROOM - BECOMING INSANE     7:16",
]

AUX_SPRITES = [VOLUME_KNOB_KEY, PLEDIT_BG_KEY, PLEDIT_LEFT_SIDE_KEY, PLEDIT_RIGHT_SIDE_KEY,
               TITLEBAR_INACTIVE_KEY, PLEDIT_TITLE_INACTIVE_KEY, PLEDIT_THUMB_KEY]


def extract_volume_knob(balance_bmp: Image.Image, log: list = None) -> Image.Image:
    """Crop the 14×11 knob sprite from BALANCE.BMP per ADR-016 §1. Same
    coordinates the static-composite path already uses for the balance
    knob — single source of truth across BALANCE + VOLUME."""
    x, y, w, h = VOLUME_KNOB_SOURCE_RECT
    knob = balance_bmp.crop((x, y, x + w, y + h)).convert("RGB")
    if log is not None:
        log.append({
            "label": "volume_knob",
            "source": "BALANCE.BMP (shared with balance-knob composite per ADR-016)",
            "src_rect": f"({x}, {y}, {w}, {h})",
            "target": f"runtime: VOLUME_X + (percent*54)/100, VOLUME_Y+1, {w}, {h}",
            "rendered": knob,
        })
    return knob


def _replace_colour(img: Image.Image, key_rgb: tuple, tol: int,
                    replacement: tuple) -> Image.Image:
    """Return a copy of img with pixels within tol of key_rgb replaced."""
    out = img.convert("RGB").copy()
    px = out.load()
    w, h = out.size
    kr, kg, kb = key_rgb
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - kr) <= tol and abs(g - kg) <= tol and abs(b - kb) <= tol:
                px[x, y] = replacement
    return out


def build_pledit_atlas(pledit_bmp: Image.Image, log: list = None) -> Image.Image:
    """Construct a PLEDIT_DISPLAY_W × 58 atlas from PLEDIT.BMP chrome sprites.

    Canonical construction (Audacious skin_draw_playlistwin_frame / playlistwin.cc):

    Title bar (y=0..19 in atlas, 20px):
      left corner (0,y,25,20) | tile repeat unit (127,y,25,20) × N | right corner (153,y,25,20)
      For PLEDIT_DISPLAY_W=275: 25 + 9×25 + 25 = 275. No raw-crop; cyan separators excluded.

    Bottom bar (y=20..57 in atlas, 38px):
      left section  (0,72,125,38) at atlas x=0
      right section (126,72,276,38) at atlas x=(PLEDIT_DISPLAY_W - PLEDIT_BOTTOM_RIGHT_W)
      For width=275: 125 + 150 = 275 — sections abut exactly, no gap.

    Cyan (0,198,255) separator pixels are never included in the crop rectangles above.
    """
    src = pledit_bmp.convert("RGB")
    y = PLEDIT_TITLE_Y0

    # ── Title bar ──
    left_corner  = src.crop((PLEDIT_TITLE_LEFT_X,  y,
                              PLEDIT_TITLE_LEFT_X  + PLEDIT_TITLE_LEFT_W,  y + PLEDIT_TITLE_H_SRC))
    tile_unit    = src.crop((PLEDIT_TITLE_TILE_X,  y,
                              PLEDIT_TITLE_TILE_X  + PLEDIT_TITLE_TILE_W,  y + PLEDIT_TITLE_H_SRC))
    right_corner = src.crop((PLEDIT_TITLE_RIGHT_X, y,
                              PLEDIT_TITLE_RIGHT_X + PLEDIT_TITLE_RIGHT_W, y + PLEDIT_TITLE_H_SRC))

    title_bar = Image.new("RGB", (PLEDIT_DISPLAY_W, PLEDIT_TITLE_H_SRC), PLEDIT_BODY_BG_RGB)
    title_bar.paste(left_corner, (0, 0))
    tx = PLEDIT_TITLE_LEFT_W
    while tx < PLEDIT_DISPLAY_W - PLEDIT_TITLE_RIGHT_W:
        clip_w = min(PLEDIT_TITLE_TILE_W, PLEDIT_DISPLAY_W - PLEDIT_TITLE_RIGHT_W - tx)
        title_bar.paste(tile_unit.crop((0, 0, clip_w, PLEDIT_TITLE_H_SRC)), (tx, 0))
        tx += PLEDIT_TITLE_TILE_W
    title_bar.paste(right_corner, (PLEDIT_DISPLAY_W - PLEDIT_TITLE_RIGHT_W, 0))

    # ── Bottom bar: two fixed sections ──
    y0 = PLEDIT_BOTTOM_Y0_SRC
    h  = PLEDIT_BOTTOM_H_SRC
    left_sec  = src.crop((0,   y0, PLEDIT_BOTTOM_LEFT_W,                y0 + h))
    right_sec = src.crop((PLEDIT_BOTTOM_LEFT_W + 1,  y0,
                           PLEDIT_BOTTOM_LEFT_W + 1 + PLEDIT_BOTTOM_RIGHT_W, y0 + h))

    bottom_bar = Image.new("RGB", (PLEDIT_DISPLAY_W, h), PLEDIT_BODY_BG_RGB)
    bottom_bar.paste(left_sec,  (0, 0))
    bottom_bar.paste(right_sec, (PLEDIT_DISPLAY_W - PLEDIT_BOTTOM_RIGHT_W, 0))

    # ── Pack into atlas ──
    atlas_h = PLEDIT_DISPLAY_TITLE_H + PLEDIT_DISPLAY_BOTTOM_H
    bg = Image.new("RGB", (PLEDIT_DISPLAY_W, atlas_h), PLEDIT_BODY_BG_RGB)
    bg.paste(title_bar,  (0, 0))
    bg.paste(bottom_bar, (0, PLEDIT_DISPLAY_TITLE_H))

    if log is not None:
        log.append({
            "label": "pledit_title_bar",
            "source": "PLEDIT.BMP",
            "src_rect": f"left(0,{y},25,20) + tile(127,{y},25,20)×N + right(153,{y},25,20)",
            "target": f"(0, 0, {PLEDIT_DISPLAY_W}, {PLEDIT_DISPLAY_TITLE_H}) in SKIN_PLEDIT_BG",
            "rendered": title_bar,
        })
        log.append({
            "label": "pledit_bottom_bar",
            "source": "PLEDIT.BMP",
            "src_rect": f"left(0,{y0},125,38) + right(126,{y0},150,38)",
            "target": f"(0, {PLEDIT_DISPLAY_TITLE_H}, {PLEDIT_DISPLAY_W}, {PLEDIT_DISPLAY_BOTTOM_H}) in SKIN_PLEDIT_BG",
            "rendered": bottom_bar,
        })

    return bg


def build_volume_atlas(volume_bmp: Image.Image, log: list = None) -> Image.Image:
    """Pack 5 source-keyframe crops + a synthesised KEYFRAME_NONE into
    one 68×78 atlas. KEYFRAME_NONE is row 0 (sentinel); KF0..KF4 follow.

    KEYFRAME_NONE synthesis (A1.2): copy KEYFRAME_0 (minimum non-zero
    fill — only a small green run at the left), detect green-dominant
    pixels, replace each with the groove colour sampled from x=63 of
    the same row (rightmost column = deep empty groove). Track outline
    (border pixels are dark, not green) survives the substitution."""
    src = volume_bmp.convert("RGB")
    keyframes = []
    for src_idx in VOLUME_KEYFRAMES:
        y0 = src_idx * VOLUME_FRAME_STRIDE
        keyframes.append(src.crop((0, y0, VOLUME_FRAME_W, y0 + VOLUME_FRAME_H)))

    # Synthesise NONE from KF0.
    none_img = keyframes[0].copy()
    out_px = none_img.load()
    src_px = keyframes[0].load()
    groove = [src_px[VOLUME_FRAME_W - 5, y] for y in range(VOLUME_FRAME_H)]
    for y in range(VOLUME_FRAME_H):
        for x in range(VOLUME_FRAME_W):
            r, g, b = src_px[x, y]
            # Green-dominant heuristic — Winamp fill colours run
            # green→yellow→red so KF0's fill block is unambiguously green.
            if g > r + 20 and g > b + 20:
                out_px[x, y] = groove[y]

    atlas = Image.new("RGB", (VOLUME_FRAME_W, VOLUME_FRAME_H * 6))
    atlas.paste(none_img,    (0, 0))
    for i, kf in enumerate(keyframes):
        atlas.paste(kf, (0, (i + 1) * VOLUME_FRAME_H))

    if log is not None:
        log.append({
            "label": "volume_keyframe_none",
            "source": "VOLUME.BMP (synthesised from KEYFRAME_0)",
            "src_rect": "green-dominant pixels → groove colour at x=63",
            "target": "(0, 0, 68, 13) in SKIN_VOLUME atlas",
            "rendered": none_img.copy(),
        })
        for i, kf in enumerate(keyframes):
            src_idx = VOLUME_KEYFRAMES[i]
            log.append({
                "label": f"volume_keyframe_{i}",
                "source": "VOLUME.BMP",
                "src_rect": f"(0, {src_idx * VOLUME_FRAME_STRIDE}, 68, 13) — frame {src_idx}",
                "target": f"(0, {(i + 1) * VOLUME_FRAME_H}, 68, 13) in SKIN_VOLUME atlas",
                "rendered": kf.copy(),
            })

    return atlas


# Winamp 2.x SHUFREP — packed runtime atlas: 4 normal-state sprites
# (REPEAT off/on, SHUFFLE off/on) at 75×30. Pressed states intentionally
# omitted to keep flash budget tight; tap feedback is implicit in the
# state flip itself.
SHUFREP_PACKED_W = 75
SHUFREP_PACKED_H = 30

SHUFREP_LAYOUT = {
    "SR_REPEAT_OFF":  ( 0,  0, 28, 15),
    "SR_SHUFFLE_OFF": (28,  0, 47, 15),
    "SR_REPEAT_ON":   ( 0, 15, 28, 15),
    "SR_SHUFFLE_ON":  (28, 15, 47, 15),
    "SHUFFLE_X": 164, "SHUFFLE_Y": 89, "SHUFFLE_W": 47, "SHUFFLE_H": 15,
    "REPEAT_X":  211, "REPEAT_Y":  89, "REPEAT_W":  28, "REPEAT_H":  15,
}


def build_shufrep_atlas(shufrep_bmp: Image.Image, log: list = None) -> Image.Image:
    """Crop the 4 normal-state sprites from canonical SHUFREP.BMP layout
    and pack them into a 75×30 atlas. Source layout (Winamp 2 spec):
    REPEAT off/on at (0,0)/(0,30) 28×15, SHUFFLE off/on at (28,0)/(28,30)
    47×15. Verified visually against base-2.91 (zoomed inspection
    2026-05-10) — top two rows are normal-state OFF, next two ON; the
    1st and 3rd are unpressed which is what we want."""
    src = shufrep_bmp.convert("RGB")
    rep_off = src.crop((0, 0, 28, 15))
    shu_off = src.crop((28, 0, 75, 15))
    rep_on  = src.crop((0, 30, 28, 45))
    shu_on  = src.crop((28, 30, 75, 45))

    atlas = Image.new("RGB", (SHUFREP_PACKED_W, SHUFREP_PACKED_H))
    atlas.paste(rep_off, (0, 0))
    atlas.paste(shu_off, (28, 0))
    atlas.paste(rep_on,  (0, 15))
    atlas.paste(shu_on,  (28, 15))

    if log is not None:
        for label, src_rect, dst_rect, rendered in [
            ("shufrep_repeat_off",  "(0, 0, 28, 15)",   "(0, 0, 28, 15)",   rep_off),
            ("shufrep_shuffle_off", "(28, 0, 47, 15)",  "(28, 0, 47, 15)",  shu_off),
            ("shufrep_repeat_on",   "(0, 30, 28, 15)",  "(0, 15, 28, 15)",  rep_on),
            ("shufrep_shuffle_on",  "(28, 30, 47, 15)", "(28, 15, 47, 15)", shu_on),
        ]:
            log.append({
                "label":    label,
                "source":   "SHUFREP.BMP",
                "src_rect": src_rect,
                "target":   f"{dst_rect} in SKIN_SHUFREP atlas",
                "rendered": rendered.copy(),
            })

    return atlas


# Winamp 2.x mono/stereo cluster — single 58x24 atlas, 29x12 sprites.
# Verified against the actual base-2.91 BMP (zoomed inspection
# 2026-05-09): TOP row = ON (lit / green), BOTTOM row = OFF (dim / grey);
# LEFT column = STEREO, RIGHT column = MONO.
MONOSTER_LAYOUT = {
    "MS_STEREO_ON":  (0,  0, 29, 12),
    "MS_MONO_ON":    (29, 0, 29, 12),
    "MS_STEREO_OFF": (0, 12, 29, 12),
    "MS_MONO_OFF":   (29,12, 29, 12),
    "MS_X": 212, "MS_Y": 41,
}


def composite_text(main_bg: Image.Image, font: Image.Image, text: str, x: int, y: int,
                    log: list = None, label: str = None) -> None:
    """Paste 5x6 glyphs from TEXT.BMP onto main_bg at (x, y), char by char.
    The glyph's dark pixels become MAIN_BG's existing dark pixels at the
    paste position — no transparency masking needed because the metadata
    region is black on the source MAIN.BMP.

    If `log` is provided, a row is appended to it AND a per-element PNG of
    the rendered text is written via the caller-supplied composite-dir."""
    table = build_glyph_table()
    width = max(1, len(text) * (GLYPH_W + 1) - 1)
    rendered = Image.new("RGB", (width, GLYPH_H), (0, 0, 0))
    dx = 0
    for ch in text:
        code = ord(ch)
        if code >= 128:
            code = ord('?')
        col, row = table[code]
        u, v = col * GLYPH_W, row * GLYPH_H
        glyph = font.crop((u, v, u + GLYPH_W, v + GLYPH_H)).convert("RGB")
        rendered.paste(glyph, (dx, 0))
        dx += GLYPH_W + 1
    main_bg.paste(rendered, (x, y))
    if log is not None and label is not None:
        log.append({
            "label": label,
            "source": "TEXT.BMP (per-glyph composite)",
            "src_rect": f"glyphs from CHAR_MAP for {text!r}",
            "target": f"({x}, {y}, {width}, {GLYPH_H})",
            "rendered": rendered,
        })


def composite_with_transparency(main_bg: Image.Image, src: Image.Image, x: int, y: int,
                                 key_rgb: tuple, tol: int) -> None:
    """Paste src onto main_bg at (x, y); skip pixels whose colour is
    within tol of key_rgb (Winamp transparency convention)."""
    src_rgb = src.convert("RGB")
    src_pixels = src_rgb.load()
    bg_pixels = main_bg.load()
    bx, by = main_bg.size
    sx, sy = src_rgb.size
    for j in range(sy):
        if y + j < 0 or y + j >= by:
            continue
        for i in range(sx):
            if x + i < 0 or x + i >= bx:
                continue
            r, g, b = src_pixels[i, j]
            if (abs(r - key_rgb[0]) <= tol and
                abs(g - key_rgb[1]) <= tol and
                abs(b - key_rgb[2]) <= tol):
                continue
            bg_pixels[x + i, y + j] = (r, g, b)


def composite_static_decoration(main_bg: Image.Image, sources: dict, log: list = None) -> None:
    """ADR-014: paint TITLEBAR active variant, balance centered, kbps/kHz
    text, and the static MS_STEREO_ON / MS_MONO_OFF onto MAIN_BG before
    it's emitted as RGB565. Source BMPs are loaded but never become their
    own SKIN_* atlas — the runtime never sees them.

    If `log` is provided, each composite step appends a dict describing
    source file / source rect / target placement, plus the rendered
    sub-image — used to emit per-element PNGs + MANIFEST.md."""
    def record(label, src_file, src_rect, target_rect, rendered):
        if log is None: return
        log.append({
            "label": label,
            "source": src_file,
            "src_rect": src_rect,
            "target": target_rect,
            "rendered": rendered,
        })

    # TITLEBAR active variant + OAIDV clutterbar.
    if "TITLEBAR.BMP" in sources:
        tb = sources["TITLEBAR.BMP"]
        crop = tb.crop((27, 0, 27 + 275, 14)).convert("RGB")
        main_bg.paste(crop, (0, 0))
        record("titlebar_active", "TITLEBAR.BMP", "(27, 0, 275, 14)", "(0, 0, 275, 14)", crop)
        cb = tb.crop((304, 0, 312, 43)).convert("RGB")
        main_bg.paste(cb, (10, 22))
        record("clutterbar_OAIDV", "TITLEBAR.BMP", "(304, 0, 8, 43)", "(10, 22, 8, 43)", cb)

    # BALANCE slider. The XMMS canonical spec (15-px frame stride, bar
    # sub-rect at (15, 9, 38, 13) within each frame) DOES NOT MATCH this
    # skin. Empirical scan of base-2.91's BALANCE.BMP found bars at
    # irregular y positions (y=9 with stride 11 to y=20, then non-uniform
    # strides of 35/36/5/etc). User-confirmed coordinates this round:
    #
    #   Frame 0 bar: source (9, 1, 38, 13) — visibly thick bar
    #   Knob normal: source (15, 422, 14, 11) — XMMS spec, matches this skin
    #
    # We bake only frame 0 (visually prominent, semantically "max-L
    # deflection" but balance is decoration-only — no API source). On-screen:
    # bar at (177, 57), knob centered on top at (189, 58).
    if "BALANCE.BMP" in sources:
        bal = sources["BALANCE.BMP"]
        bal_frame = bal.crop((9, 1, 9 + 38, 1 + 13))
        composite_with_transparency(main_bg, bal_frame, 177, 57,
                                    BALANCE_TRANSPARENT_RGB,
                                    BALANCE_TRANSPARENT_TOL)
        record("balance_bar_frame0", "BALANCE.BMP",
               "(9, 1, 38, 13) — empirical for this skin (XMMS spec mismatch)",
               "(177, 57, 38, 13)", bal_frame.convert("RGB"))
        bal_thumb = bal.crop((15, 422, 15 + 14, 422 + 11))
        composite_with_transparency(main_bg, bal_thumb, 189, 58,
                                    BALANCE_TRANSPARENT_RGB,
                                    BALANCE_TRANSPARENT_TOL)
        record("balance_knob_normal", "BALANCE.BMP", "(15, 422, 14, 11)",
               "(189, 58, 14, 11)", bal_thumb.convert("RGB"))

    # kbps "192" + kHz "44" — small font glyphs from TEXT.BMP.
    if "TEXT.BMP" in sources:
        font = sources["TEXT.BMP"]
        composite_text(main_bg, font, "192", 110, 43, log=log, label="kbps_192")
        composite_text(main_bg, font, "44",  156, 43, log=log, label="khz_44")

    # MS static "music-mode" composite per ADR-014.
    if "MONOSTER.BMP" in sources:
        ms = sources["MONOSTER.BMP"]
        mono_off = ms.crop((29, 12, 58, 24)).convert("RGB")
        main_bg.paste(mono_off, (212, 41))
        record("monoster_mono_off", "MONOSTER.BMP", "(29, 12, 29, 12)",
               "(212, 41, 29, 12)", mono_off)
        stereo_on = ms.crop((0, 0, 29, 12)).convert("RGB")
        main_bg.paste(stereo_on, (241, 41))
        record("monoster_stereo_on", "MONOSTER.BMP", "(0, 0, 29, 12)",
               "(241, 41, 29, 12)", stereo_on)

    # EQ-off + PL-on toggles from SHUFREP.BMP.
    if "SHUFREP.BMP" in sources:
        sr = sources["SHUFREP.BMP"]
        eq_off = sr.crop((0, 61, 23, 73)).convert("RGB")
        main_bg.paste(eq_off, (218, 58))
        record("shufrep_eq_off", "SHUFREP.BMP", "(0, 61, 23, 12)",
               "(218, 58, 23, 12)", eq_off)
        pl_on = sr.crop((23, 73, 46, 85)).convert("RGB")
        main_bg.paste(pl_on, (242, 58))
        record("shufrep_pl_on", "SHUFREP.BMP", "(23, 73, 23, 12)",
               "(242, 58, 23, 12)", pl_on)

    # Eject button — decorative bake from CBUTTONS.BMP. Same atlas the
    # transport buttons live in. Static composite rather than runtime
    # blit because eject has no Spotify equivalent (the closest semantic
    # would be "transferPlayback to a non-Spotify device" — not useful).
    if "CBUTTONS.BMP" in sources:
        cb = sources["CBUTTONS.BMP"]
        eject = cb.crop((114, 0, 114 + 22, 16)).convert("RGB")
        main_bg.paste(eject, (136, 89))
        record("eject_decorative", "CBUTTONS.BMP", "(114, 0, 22, 16)",
               "(136, 89, 22, 16)", eject)


def parse_shell_layout(path="SpotifyDiyThing/gen/shell_layout.h") -> dict:
    """Parse gen/shell_layout.h, stripping inline // comments.
    Returns dict mapping define name → value string.
    Handles int (275), hex (0x07E0), char ('A'), flag (1)."""
    import re as _re
    d = {}
    for line in open(path):
        m = _re.match(r'#define\s+(\w+)\s+([^/]+)', line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def emit_layout_header(out_dir: pathlib.Path, main: Image.Image, cbut: Image.Image, font: Image.Image, extras: dict[str, Image.Image]) -> None:
    with (out_dir / "skin_layout.h").open("w") as f:
        f.write("// Generated by tools/bake_skin.py — do not edit by hand.\n")
        f.write("#pragma once\n#include <stdint.h>\n\n")
        f.write("typedef struct { int16_t u, v, w, h; } SkinUV;\n\n")

        f.write(f"#define WINDOW_W {main.width}\n")
        f.write(f"#define WINDOW_H {main.height}\n\n")

        f.write("// LOGO tap zone (M-CONN TASK-053f) — window-local coordinates.\n")
        f.write(f"#define LOGO_X {LOGO_X}\n")
        f.write(f"#define LOGO_Y {LOGO_Y}\n")
        f.write(f"#define LOGO_W {LOGO_W}\n")
        f.write(f"#define LOGO_H {LOGO_H}\n\n")

        f.write(f"#define SKIN_MAIN_BG_W   {main.width}\n")
        f.write(f"#define SKIN_MAIN_BG_H   {main.height}\n")
        f.write(f"#define SKIN_CBUTTONS_W  {cbut.width}\n")
        f.write(f"#define SKIN_CBUTTONS_H  {cbut.height}\n")
        f.write(f"#define SKIN_FONT_W      {font.width}\n")
        f.write(f"#define SKIN_FONT_H      {font.height}\n\n")

        f.write("extern const uint16_t SKIN_MAIN_BG[];\n")
        f.write("extern const uint16_t SKIN_CBUTTONS[];\n")
        f.write("extern const uint16_t SKIN_FONT[];\n\n")

        f.write("// Transport buttons: UV in CBUTTONS atlas. Top row normal, bottom row (y+18) pressed.\n")
        for name, x, w, h in CBUTTON_SPRITES:
            f.write(f"#define CB_{name}_N (SkinUV){{ {x}, 0, {w}, {h} }}\n")
            f.write(f"#define CB_{name}_P (SkinUV){{ {x}, {h}, {w}, {h} }}\n")
        f.write("\n// Transport button screen positions on main window.\n")
        for name, x, y in CBUTTON_POSITIONS:
            f.write(f"#define CB_{name}_X {x}\n")
            f.write(f"#define CB_{name}_Y {y}\n")
        f.write("\n// Transport button W/H scalars (required by coords.py).\n")
        for name, _x_uv, w, h in CBUTTON_SPRITES:
            f.write(f"#define CB_{name}_W {w}\n")
            f.write(f"#define CB_{name}_H {h}\n")

        f.write("\n// Title/marquee region on main window (Winamp standard).\n")
        f.write("#define TITLE_X 111\n#define TITLE_Y 27\n#define TITLE_W 154\n#define TITLE_H 6\n\n")

        f.write(f"#define GLYPH_W {GLYPH_W}\n#define GLYPH_H {GLYPH_H}\n\n")
        f.write("// Glyph UV lookup, indexed by ASCII (lower-case folded to upper).\n")
        f.write("// Unmapped chars resolve to a blank cell. See CHAR_MAP in tools/bake_skin.py.\n")
        f.write("extern const SkinUV SKIN_GLYPH[128];\n\n")

        # Tier-3 sheets (only those actually loaded — keeps flash budget tight).
        for fname in TIER3_SHEETS:
            img = extras.get(fname)
            if img is None:
                continue
            stem = pathlib.Path(fname).stem
            sym = "SKIN_" + stem
            f.write(f"#define {sym}_W {img.width}\n#define {sym}_H {img.height}\n")
            f.write(f"extern const uint16_t {sym}[];\n")
        f.write("\n")

        if "NUMBERS.BMP" in extras:
            f.write(f"#define DIGIT_W {NUMBERS_LAYOUT['DIGIT_W']}\n")
            f.write(f"#define DIGIT_H {NUMBERS_LAYOUT['DIGIT_H']}\n")
            f.write("// SKIN_NUMBERS sprite for digit n (0-9), or 10 for blank/minus.\n")
            f.write("#define DIGIT_UV(n) (SkinUV){ (int16_t)((n) * DIGIT_W), 0, DIGIT_W, DIGIT_H }\n\n")
        if "POSBAR.BMP" in extras:
            for k, v in POSBAR_LAYOUT.items():
                if isinstance(v, tuple):
                    x, y, w, h = v
                    f.write(f"#define {k} (SkinUV){{ {x}, {y}, {w}, {h} }}\n")
            f.write(f"#define POSBAR_X {POSBAR_LAYOUT['POSBAR_X']}\n")
            f.write(f"#define POSBAR_Y {POSBAR_LAYOUT['POSBAR_Y']}\n")
            f.write(f"#define POSBAR_W {POSBAR_LAYOUT['POSBAR_BG'][2]}\n")
            f.write(f"#define POSBAR_H {POSBAR_LAYOUT['POSBAR_BG'][3]}\n\n")
        if "PLAYPAUS.BMP" in extras:
            for k, v in PLAYPAUS_LAYOUT.items():
                if isinstance(v, tuple):
                    x, y, w, h = v
                    f.write(f"#define {k} (SkinUV){{ {x}, {y}, {w}, {h} }}\n")
            f.write(f"#define PP_X {PLAYPAUS_LAYOUT['PP_X']}\n")
            f.write(f"#define PP_Y {PLAYPAUS_LAYOUT['PP_Y']}\n\n")
        if "MONOSTER.BMP" in extras:
            for k, v in MONOSTER_LAYOUT.items():
                if isinstance(v, tuple):
                    x, y, w, h = v
                    f.write(f"#define {k} (SkinUV){{ {x}, {y}, {w}, {h} }}\n")
            f.write(f"#define MS_X {MONOSTER_LAYOUT['MS_X']}\n")
            f.write(f"#define MS_Y {MONOSTER_LAYOUT['MS_Y']}\n")
        if "VOLUME.BMP" in extras:
            f.write("\n// VOLUME slider — 6-keyframe atlas (5 source + synthesised NONE).\n")
            f.write("// Per ADR-014 Amendment 1 §A1.2/§A1.3.\n")
            for k, v in VOLUME_LAYOUT.items():
                if isinstance(v, tuple):
                    x, y, w, h = v
                    f.write(f"#define {k} (SkinUV){{ {x}, {y}, {w}, {h} }}\n")
            f.write(f"#define VOLUME_X {VOLUME_LAYOUT['VOLUME_X']}\n")
            f.write(f"#define VOLUME_Y {VOLUME_LAYOUT['VOLUME_Y']}\n")
            f.write(f"#define VOLUME_W {VOLUME_LAYOUT['VOLUME_W']}\n")
            f.write(f"#define VOLUME_H {VOLUME_LAYOUT['VOLUME_H']}\n")
            f.write(f"#define VOLUME_FRAME_W {VOLUME_FRAME_W}\n")
        if VOLUME_KNOB_KEY in extras:
            f.write("\n// VOLUME knob — shared with BALANCE knob per ADR-016 §1.\n")
            f.write(f"#define VOLUME_KNOB_W {VOLUME_KNOB_W}\n")
            f.write(f"#define VOLUME_KNOB_H {VOLUME_KNOB_H}\n")
            f.write("extern const uint16_t SKIN_VOLUME_KNOB[];\n")
        if "SHUFREP.BMP" in extras:
            f.write("\n// SHUFREP — packed 75×30 atlas of normal-state sprites.\n")
            f.write("// Pressed-state variants intentionally omitted (flash budget).\n")
            for k, v in SHUFREP_LAYOUT.items():
                if isinstance(v, tuple):
                    x, y, w, h = v
                    f.write(f"#define {k} (SkinUV){{ {x}, {y}, {w}, {h} }}\n")
            for k in ("SHUFFLE_X", "SHUFFLE_Y", "SHUFFLE_W", "SHUFFLE_H",
                      "REPEAT_X",  "REPEAT_Y",  "REPEAT_W",  "REPEAT_H"):
                f.write(f"#define {k} {SHUFREP_LAYOUT[k]}\n")
        if PLEDIT_BG_KEY in extras:
            bg_img = extras[PLEDIT_BG_KEY]
            f.write("\n// PLEDIT playlist editor chrome (ADR-018 Amendment 1, TASK-047a).\n")
            f.write("// Canonical from Audacious skin.cc (Winamp 2.x reimpl):\n")
            f.write(f"//   title bar y=0..{PLEDIT_TITLE_H_SRC-1} ({PLEDIT_TITLE_H_SRC}px),")
            f.write(f" bottom bar y={PLEDIT_BOTTOM_Y0_SRC}..{PLEDIT_BOTTOM_Y0_SRC+PLEDIT_BOTTOM_H_SRC-1} ({PLEDIT_BOTTOM_H_SRC}px).\n")
            f.write("// ROW RENDERING: flat fillRect only — no BMP sprite (playlist-widget.cc).\n")
            f.write("// Colours from PLEDIT.TXT: Normal=#00FF00, Current=#FFFFFF,\n")
            f.write("//   NormalBG=#000000, SelectedBG=#0000C6.\n")
            f.write(f"#define PLEDIT_Y          {PLEDIT_DISPLAY_Y}\n")
            f.write(f"#define PLEDIT_H          {240 - PLEDIT_DISPLAY_Y}\n")
            f.write(f"#define PLEDIT_W          {PLEDIT_DISPLAY_W}\n")
            f.write(f"#define PLEDIT_TITLE_H    {PLEDIT_DISPLAY_TITLE_H}\n")
            f.write(f"#define PLEDIT_BOTTOM_H   {PLEDIT_DISPLAY_BOTTOM_H}\n")
            f.write(f"#define PLEDIT_ROWS_Y     {PLEDIT_DISPLAY_ROWS_Y}\n")
            f.write(f"#define PLEDIT_ROW_H      {PLEDIT_DISPLAY_ROW_H}\n")
            f.write(f"#define PLEDIT_ROW_COUNT  {PLEDIT_DISPLAY_ROW_COUNT}\n")
            f.write(f"#define PLEDIT_BOTTOM_Y   {PLEDIT_DISPLAY_BOTTOM_Y}\n")
            f.write(f"#define PLEDIT_SIDE_LEFT_W  {PLEDIT_SIDE_LEFT_W}\n")
            f.write(f"#define PLEDIT_SIDE_RIGHT_W {PLEDIT_SIDE_RIGHT_W}\n")
            f.write(f"#define PLEDIT_SIDE_H_SRC   {PLEDIT_SIDE_H_SRC}\n")
            f.write(f"#define PLEDIT_CONTENT_X    {PLEDIT_CONTENT_X}\n")
            f.write(f"#define PLEDIT_CONTENT_W    {PLEDIT_CONTENT_W}\n")
            r, g, b = PLEDIT_BODY_BG_RGB
            body_bg_565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            f.write(f"#define PLEDIT_BODY_BG      0x{body_bg_565:04X}U  // RGB565 of ({r},{g},{b})\n")
            f.write(f"#define PLEDIT_FG_NORMAL   0x07E0U  // #00FF00 from PLEDIT.TXT\n")
            f.write(f"#define PLEDIT_FG_CURRENT  0xFFFFU  // #FFFFFF from PLEDIT.TXT\n")
            f.write(f"#define PLEDIT_BG_NORMAL   0x0000U  // #000000 from PLEDIT.TXT\n")
            f.write(f"#define PLEDIT_BG_SELECTED 0x0018U  // #0000C6 from PLEDIT.TXT\n")
            f.write(f"#define SKIN_PLEDIT_BG_W  {bg_img.width}\n")
            f.write(f"#define SKIN_PLEDIT_BG_H  {bg_img.height}\n")
            f.write("extern const uint16_t SKIN_PLEDIT_BG[];\n")
            f.write("extern const uint16_t SKIN_PLEDIT_LEFT_SIDE[];   // 12x29 frame tile\n")
            f.write("extern const uint16_t SKIN_PLEDIT_RIGHT_SIDE[];  // 19x29 frame tile (incl. scrollbar)\n")
        if PLEDIT_THUMB_KEY in extras:
            r, g, b = PLEDIT_TRANSPARENT_KEY
            t565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            thumb_x_inset = (PLEDIT_SIDE_RIGHT_W - PLEDIT_THUMB_W) // 2
            f.write("\n// PLEDIT scrollbar thumb (TASK-051e) — 9×17 from PLEDIT.BMP (x=52,y=54). Transparent key preserved.\n")
            f.write(f"#define SKIN_PLEDIT_THUMB_W {PLEDIT_THUMB_W}\n")
            f.write(f"#define SKIN_PLEDIT_THUMB_H {PLEDIT_THUMB_H}\n")
            f.write(f"#define PLEDIT_THUMB_X_INSET {thumb_x_inset}  // centres thumb in PLEDIT_SIDE_RIGHT_W\n")
            f.write(f"#define PLEDIT_TRANSPARENT_RGB565 0x{t565:04X}U\n")
            f.write("extern const uint16_t SKIN_PLEDIT_THUMB[];\n")
        if TITLEBAR_INACTIVE_KEY in extras:
            tb_i = extras[TITLEBAR_INACTIVE_KEY]
            f.write("\n// TITLEBAR inactive strip (M-CONN TASK-053a) — 275×14 from TITLEBAR.BMP crop (27,14,302,28).\n")
            f.write(f"#define SKIN_TITLEBAR_INACTIVE_W {tb_i.width}\n")
            f.write(f"#define SKIN_TITLEBAR_INACTIVE_H {tb_i.height}\n")
            f.write("extern const uint16_t SKIN_TITLEBAR_INACTIVE[];\n")
        if PLEDIT_TITLE_INACTIVE_KEY in extras:
            pti = extras[PLEDIT_TITLE_INACTIVE_KEY]
            f.write("\n// PLEDIT inactive title strip (M-CONN) — 275×20 from PLEDIT.BMP y=21..40.\n")
            f.write(f"#define SKIN_PLEDIT_TITLE_INACTIVE_W {pti.width}\n")
            f.write(f"#define SKIN_PLEDIT_TITLE_INACTIVE_H {pti.height}\n")
            f.write("extern const uint16_t SKIN_PLEDIT_TITLE_INACTIVE[];\n")


def emit_glyph_table(fp) -> None:
    table = build_glyph_table()
    fp.write("// SKIN_GLYPH[ascii] -> UV in SKIN_FONT atlas.\n")
    fp.write("const SkinUV SKIN_GLYPH[128] = {\n")
    for code, (c, r) in enumerate(table):
        u, v = c * GLYPH_W, r * GLYPH_H
        ch = chr(code) if 32 <= code < 127 else "?"
        fp.write(f"  [{code:3d}] = {{ {u:3d}, {v:2d}, {GLYPH_W}, {GLYPH_H} }}, // '{ch}'\n")
    fp.write("};\n\n")


def emit_assets(out_dir: pathlib.Path, main: Image.Image, cbut: Image.Image, font: Image.Image, extras: dict[str, Image.Image]) -> None:
    with (out_dir / "skin_assets.c").open("w") as f:
        f.write("// Generated by tools/bake_skin.py — do not edit by hand.\n")
        f.write("#include <stdint.h>\n")
        f.write("#include \"skin_layout.h\"\n\n")
        emit_array("SKIN_MAIN_BG",  to_rgb565_le(main), main.width, main.height, f)
        emit_array("SKIN_CBUTTONS", to_rgb565_le(cbut), cbut.width, cbut.height, f)
        emit_array("SKIN_FONT",     to_rgb565_le(font), font.width, font.height, f)
        emit_glyph_table(f)
        for fname in TIER3_SHEETS:
            img = extras.get(fname)
            if img is None:
                continue
            sym = "SKIN_" + pathlib.Path(fname).stem
            emit_array(sym, to_rgb565_le(img), img.width, img.height, f)
        for fname in AUX_SPRITES:
            img = extras.get(fname)
            if img is None:
                continue
            sym = "SKIN_" + pathlib.Path(fname).stem
            emit_array(sym, to_rgb565_le(img), img.width, img.height, f)


def render_preview(main: Image.Image, cbut: Image.Image, out_path: pathlib.Path) -> None:
    """Composite the normal-state buttons onto the main background — sanity check
    that sprite rects line up with their declared screen positions."""
    canvas = main.convert("RGB").copy()
    for name, sx, sy in CBUTTON_POSITIONS:
        ux, uw, uh = next((s[1], s[2], s[3]) for s in CBUTTON_SPRITES if s[0] == name)
        sprite = cbut.crop((ux, 0, ux + uw, uh)).convert("RGB")
        canvas.paste(sprite, (sx, sy))
    canvas.save(out_path)


def render_full_preview(main: Image.Image, cbut: Image.Image,
                         font: Image.Image, extras: dict,
                         out_path: pathlib.Path) -> None:
    """Render the full 320×240 display: main chrome (top 116px) + PLEDIT panel.

    Composites transport buttons and, if PLEDIT atlases are present, the full
    PLEDIT panel (title bar, sample rows with bitmap-font text, bottom bar).
    Written to out_path.
    """
    canvas = Image.new("RGB", (320, 240), PLEDIT_BODY_BG_RGB)

    # Main chrome: 275×116, composited with transport buttons.
    chrome = main.convert("RGB").copy()
    for name, sx, sy in CBUTTON_POSITIONS:
        ux, uw, uh = next((s[1], s[2], s[3]) for s in CBUTTON_SPRITES if s[0] == name)
        sprite = cbut.crop((ux, 0, ux + uw, uh)).convert("RGB")
        chrome.paste(sprite, (sx, sy))
    canvas.paste(chrome, (0, 0))

    pledit_bg = extras.get(PLEDIT_BG_KEY)
    if pledit_bg is None:
        canvas.save(out_path)
        return

    # Title bar at y=PLEDIT_DISPLAY_Y.
    title_strip = pledit_bg.crop((0, 0, PLEDIT_DISPLAY_W, PLEDIT_DISPLAY_TITLE_H))
    canvas.paste(title_strip, (0, PLEDIT_DISPLAY_Y))

    # Rows: flat fillRect (NormalBG) + bitmap-font placeholder text.
    # Row 0 = current track (white text), rows 1-3 = normal (green text from font).
    # Content area inset by frame sides: x=PLEDIT_CONTENT_X, width=PLEDIT_CONTENT_W.
    text_margin = 3
    text_y_off  = (PLEDIT_DISPLAY_ROW_H - GLYPH_H) // 2  # vertically centre 6px glyph in 16px row
    for row_idx in range(PLEDIT_DISPLAY_ROW_COUNT):
        ry = PLEDIT_DISPLAY_ROWS_Y + row_idx * PLEDIT_DISPLAY_ROW_H
        canvas.paste(Image.new("RGB", (PLEDIT_CONTENT_W, PLEDIT_DISPLAY_ROW_H), (0, 0, 0)),
                     (PLEDIT_CONTENT_X, ry))
        if font is not None and row_idx < len(PLEDIT_PREVIEW_ROWS):
            label = PLEDIT_PREVIEW_ROWS[row_idx]
            # Truncate to fit content width.
            max_chars = (PLEDIT_CONTENT_W - text_margin * 2) // (GLYPH_W + 1)
            label = label[:max_chars]
            composite_text(canvas, font, label,
                           PLEDIT_CONTENT_X + text_margin, ry + text_y_off)

    # Frame side tiles tiled vertically over the rows area.
    pledit_sides = extras.get(PLEDIT_SIDES_KEY)
    if pledit_sides is not None:
        left_tile  = pledit_sides.crop((0, 0, PLEDIT_SIDE_LEFT_W, PLEDIT_SIDE_H_SRC))
        right_tile = pledit_sides.crop((PLEDIT_SIDE_LEFT_W, 0,
                                         PLEDIT_SIDE_LEFT_W + PLEDIT_SIDE_RIGHT_W,
                                         PLEDIT_SIDE_H_SRC))
        rows_h = PLEDIT_DISPLAY_ROW_COUNT * PLEDIT_DISPLAY_ROW_H
        for y_off in range(0, rows_h, PLEDIT_SIDE_H_SRC):
            clip_h = min(PLEDIT_SIDE_H_SRC, rows_h - y_off)
            ry = PLEDIT_DISPLAY_ROWS_Y + y_off
            canvas.paste(left_tile.crop((0, 0, PLEDIT_SIDE_LEFT_W, clip_h)), (0, ry))
            canvas.paste(right_tile.crop((0, 0, PLEDIT_SIDE_RIGHT_W, clip_h)),
                         (PLEDIT_DISPLAY_W - PLEDIT_SIDE_RIGHT_W, ry))

    # Bottom bar (38px from atlas y=PLEDIT_DISPLAY_TITLE_H).
    bottom_strip = pledit_bg.crop((0, PLEDIT_DISPLAY_TITLE_H,
                                    PLEDIT_DISPLAY_W, pledit_bg.height))
    canvas.paste(bottom_strip, (0, PLEDIT_DISPLAY_BOTTOM_Y))

    canvas.save(out_path)


def render_hitzones(full_preview: Image.Image, out_path: pathlib.Path) -> None:
    """Emit skin_hitzones.png — same composite as skin_preview.png but with all
    registered touch hit zones overlaid as semi-transparent magenta rectangles
    with white labels. Dev tool only (TASK-054 / M-HITZONES).

    Coordinates are window-local (matching the preview canvas), so overlays
    align visually with the skin elements they correspond to.
    """
    from PIL import ImageFont

    # All rects: (x, y, w, h, label) in window-local / preview-canvas coords.
    # Transport button positions derived from CBUTTON_POSITIONS + CBUTTON_SPRITES.
    _cb_xy  = {n: (x, y) for n, x, y in CBUTTON_POSITIONS}
    _cb_wh  = {n: (w, h) for n, _, w, h in CBUTTON_SPRITES}
    transport = [
        (_cb_xy[n][0], _cb_xy[n][1], _cb_wh[n][0], _cb_wh[n][1], n)
        for n in ("PREV", "PLAY", "PAUSE", "STOP", "NEXT")
    ]
    # Other main-window zones rebuilt from layout dicts.
    other = [
        (POSBAR_LAYOUT["POSBAR_X"],   POSBAR_LAYOUT["POSBAR_Y"],
         POSBAR_LAYOUT["POSBAR_BG"][2], POSBAR_LAYOUT["POSBAR_BG"][3], "SEEK"),
        (VOLUME_LAYOUT["VOLUME_X"],   VOLUME_LAYOUT["VOLUME_Y"],
         VOLUME_FRAME_W,               VOLUME_FRAME_H,                 "VOL"),
        (SHUFREP_LAYOUT["SHUFFLE_X"], SHUFREP_LAYOUT["SHUFFLE_Y"],
         SHUFREP_LAYOUT["SHUFFLE_W"], SHUFREP_LAYOUT["SHUFFLE_H"],     "SHUF"),
        (SHUFREP_LAYOUT["REPEAT_X"],  SHUFREP_LAYOUT["REPEAT_Y"],
         SHUFREP_LAYOUT["REPEAT_W"],  SHUFREP_LAYOUT["REPEAT_H"],      "RPT"),
        (24, 43, 76, 13, "VIS"),   # vu:: constants from firmware vuMeter.h
        (LOGO_X, LOGO_Y, LOGO_W, LOGO_H, "LOGO"),
    ]
    # PLEDIT zones — M-LIST-v3 redesign (TASK-051j).
    # Gesture zones + scroll arrow buttons get magenta fill; sub-row labels informational only.
    _rows_h = PLEDIT_DISPLAY_ROW_COUNT * PLEDIT_DISPLAY_ROW_H  # 65
    # Scroll arrow column: BMP x=254..274 in right_sec → atlas x=253..273 (TASK-075).
    _sa_x = (PLEDIT_DISPLAY_W - PLEDIT_BOTTOM_RIGHT_W) + (254 - (PLEDIT_BOTTOM_LEFT_W + 1))  # 253
    _sa_w = 21
    pledit_fill = [
        (PLEDIT_CONTENT_X,
         PLEDIT_DISPLAY_ROWS_Y,
         PLEDIT_CONTENT_W,
         _rows_h,
         "SWIPE/TAP"),
        (PLEDIT_DISPLAY_W - PLEDIT_SIDE_RIGHT_W,
         PLEDIT_DISPLAY_ROWS_Y,
         PLEDIT_SIDE_RIGHT_W,
         _rows_h,
         "SCROLL DRAG"),
        (_sa_x, PLEDIT_DISPLAY_BOTTOM_Y,      _sa_w,  7, "UP▲"),
        (_sa_x, PLEDIT_DISPLAY_BOTTOM_Y + 7,  _sa_w, 10, "DN▼"),
    ]
    pledit_info = [
        (PLEDIT_CONTENT_X,
         PLEDIT_DISPLAY_ROWS_Y + i * PLEDIT_DISPLAY_ROW_H,
         PLEDIT_CONTENT_W,
         PLEDIT_DISPLAY_ROW_H,
         f"R{i}")
        for i in range(PLEDIT_DISPLAY_ROW_COUNT)
    ]
    fill_zones  = transport + other + pledit_fill
    label_zones = fill_zones + pledit_info

    # Overlap check: no two fill zones may intersect (would indicate layout bug).
    def _rects_overlap(a, b):
        ax, ay, aw, ah, _ = a
        bx, by, bw, bh, _ = b
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by
    overlaps = [
        (za[4], zb[4], za[:4], zb[:4])
        for i, za in enumerate(fill_zones)
        for zb in fill_zones[i + 1:]
        if _rects_overlap(za, zb)
    ]
    if overlaps:
        lines = [f"  {a!r} {ar} overlaps {b!r} {br}" for a, b, ar, br in overlaps]
        raise ValueError("hitzone overlap detected:\n" + "\n".join(lines))

    # Composite: RGBA base + semi-transparent magenta overlay (fill zones only).
    base = full_preview.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for (x, y, w, h, _) in fill_zones:
        draw_ov.rectangle([x, y, x + w - 1, y + h - 1], fill=(255, 0, 255, 102))

    composited = Image.alpha_composite(base, overlay).convert("RGB")

    # Redraw scroll thumb on top of overlay so it's visible through the SCROLL DRAG fill.
    _sample_count = 10
    _track_h = PLEDIT_DISPLAY_ROW_COUNT * PLEDIT_DISPLAY_ROW_H
    _thumb_h = max(5, PLEDIT_DISPLAY_ROW_COUNT * _track_h // _sample_count)
    _thumb_x = PLEDIT_DISPLAY_W - PLEDIT_SIDE_RIGHT_W + 1
    ImageDraw.Draw(composited).rectangle(
        [_thumb_x, PLEDIT_DISPLAY_ROWS_Y,
         _thumb_x + PLEDIT_SIDE_RIGHT_W - 3, PLEDIT_DISPLAY_ROWS_Y + _thumb_h - 1],
        fill=(200, 160, 100))   # gold tint — distinct from magenta zone

    # Labels: white text centred in each zone (all zones including sub-row info labels).
    draw_txt = ImageDraw.Draw(composited)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    for (x, y, w, h, label) in label_zones:
        cx = x + w // 2
        cy = y + h // 2
        if font and hasattr(font, "getbbox"):
            bb = font.getbbox(label)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
        else:
            tw, th = len(label) * 6, 8
        draw_txt.text((cx - tw // 2, cy - th // 2), label,
                      fill=(255, 255, 255), font=font)

    composited.save(out_path)
    print(f"  hitzones  → {out_path.name}  ({len(fill_zones)} fill zones, {len(pledit_info)} info labels)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-i", "--input", required=True, type=pathlib.Path, help=".wsz path")
    p.add_argument("-o", "--out-dir", required=True, type=pathlib.Path, help="output dir for gen/")
    p.add_argument("--preview", type=pathlib.Path, help="optional preview PNG path")
    args = p.parse_args()

    z, prefix = open_skin(args.input)
    main_bmp = load_bmp(z, prefix, "MAIN.BMP").convert("RGB")
    cbut_bmp = load_bmp(z, prefix, "CBUTTONS.BMP")
    font_bmp = load_bmp(z, prefix, "TEXT.BMP")
    extras: dict[str, Image.Image] = {}
    for fname in TIER3_SHEETS:
        try:
            extras[fname] = load_bmp(z, prefix, fname)
        except FileNotFoundError:
            print(f"  (tier 3) {fname} not in skin — skipped")

    # ADR-014 — composite static decoration onto MAIN_BG.
    composite_sources: dict[str, Image.Image] = {}
    for fname in COMPOSITE_SOURCES:
        try:
            composite_sources[fname] = load_bmp(z, prefix, fname)
        except FileNotFoundError:
            print(f"  (composite) {fname} not in skin — skipped")
    # CBUTTONS is loaded as the transport-button atlas, but the eject
    # composite step also reads from it — share the already-loaded copy
    # rather than re-opening the zip entry.
    composite_sources.setdefault("CBUTTONS.BMP", cbut_bmp)
    composite_log: list[dict] = []
    composite_static_decoration(main_bmp, composite_sources, log=composite_log)

    # ADR-014 Amendment 1 §A1.2/§A1.3 — post-process VOLUME.BMP into a
    # 6-keyframe atlas (5 source crops + synthesised KEYFRAME_NONE).
    # This replaces the raw 68×433 source image so emit_assets /
    # emit_layout_header see the packed 68×78 atlas.
    if "VOLUME.BMP" in extras:
        extras["VOLUME.BMP"] = build_volume_atlas(extras["VOLUME.BMP"], log=composite_log)

    # M-CHROME chrome-001 final — pack SHUFREP normal-state sprites into
    # a 75×30 atlas. Replaces the raw 92×85 image so emit sees the
    # packed form. Source still drives the static EQ-off / PL-on
    # composite via composite_sources above.
    if "SHUFREP.BMP" in extras:
        extras["SHUFREP.BMP"] = build_shufrep_atlas(extras["SHUFREP.BMP"], log=composite_log)

    # TASK-053a (M-CONN) — inactive title bar strip from TITLEBAR.BMP.
    # Active crop (27,0,302,14) already composited into MAIN_BG; this is
    # the inactive variant at (27,14,302,28) — emitted as a standalone sprite
    # so repaintChrome() can overlay it when isHealthy() is false.
    if "TITLEBAR.BMP" in composite_sources:
        tb = composite_sources["TITLEBAR.BMP"].convert("RGB")
        titlebar_inactive = tb.crop((27, 14, 302, 28))  # 275×14
        extras[TITLEBAR_INACTIVE_KEY] = titlebar_inactive
        print(f"  TITLEBAR_INACTIVE  {titlebar_inactive.width}x{titlebar_inactive.height}")

    # ADR-016 §1 — VOLUME knob shares the BALANCE knob crop. Synthesised
    # entry under VOLUME_KNOB_KEY (not a real BMP in the .wsz).
    if "BALANCE.BMP" in composite_sources:
        extras[VOLUME_KNOB_KEY] = extract_volume_knob(
            composite_sources["BALANCE.BMP"], log=composite_log)

    # ADR-018 Amendment 1 TASK-047a — PLEDIT chrome: title bar + bottom bar.
    # Row rendering is flat fillRect (Audacious playlist-widget.cc); no row sprite.
    try:
        pledit_bmp = load_bmp(z, prefix, "PLEDIT.BMP")
        pledit_bg = build_pledit_atlas(pledit_bmp, log=composite_log)
        extras[PLEDIT_BG_KEY] = pledit_bg
        print(f"  PLEDIT_BG  {pledit_bg.width}x{pledit_bg.height}  (title 20px + bottom 38px composite)")
        # Side tiles: left (12×29) and right (19×29) emitted separately to skin_assets.c.
        # Also packed into a 31×29 composite for preview rendering.
        pledit_src = pledit_bmp.convert("RGB")
        left_tile  = pledit_src.crop((0,  42, 0  + PLEDIT_SIDE_LEFT_W,  42 + PLEDIT_SIDE_H_SRC))
        right_tile = pledit_src.crop((32, 42, 32 + PLEDIT_SIDE_RIGHT_W, 42 + PLEDIT_SIDE_H_SRC))
        extras[PLEDIT_LEFT_SIDE_KEY]  = left_tile
        extras[PLEDIT_RIGHT_SIDE_KEY] = right_tile
        print(f"  PLEDIT_LEFT_SIDE   {left_tile.width}x{left_tile.height}")
        print(f"  PLEDIT_RIGHT_SIDE  {right_tile.width}x{right_tile.height}  (incl. scrollbar)")
        # TASK-051e: scrollbar thumb (BMP x=52, y=54, 9×17). Transparent pixels kept as-is.
        thumb = pledit_src.crop((PLEDIT_THUMB_X0, PLEDIT_THUMB_Y0,
                                  PLEDIT_THUMB_X0 + PLEDIT_THUMB_W,
                                  PLEDIT_THUMB_Y0 + PLEDIT_THUMB_H))
        extras[PLEDIT_THUMB_KEY] = thumb
        print(f"  PLEDIT_THUMB       {thumb.width}x{thumb.height}  (scrollbar thumb, transparent pixels kept)")
        composite_log.append({
            "label": "pledit_right_side",
            "source": "PLEDIT.BMP",
            "src_rect": f"(32, 42, {PLEDIT_SIDE_RIGHT_W}, {PLEDIT_SIDE_H_SRC})",
            "target": f"SKIN_PLEDIT_RIGHT_SIDE — {PLEDIT_SIDE_RIGHT_W}x{PLEDIT_SIDE_H_SRC} scrollbar track tile (tiled vertically at runtime)",
            "rendered": right_tile,
        })
        composite_log.append({
            "label": "pledit_left_side",
            "source": "PLEDIT.BMP",
            "src_rect": f"(0, 42, {PLEDIT_SIDE_LEFT_W}, {PLEDIT_SIDE_H_SRC})",
            "target": f"SKIN_PLEDIT_LEFT_SIDE — {PLEDIT_SIDE_LEFT_W}x{PLEDIT_SIDE_H_SRC} frame side tile (tiled vertically at runtime)",
            "rendered": left_tile,
        })
        sides_img = Image.new("RGB", (PLEDIT_SIDE_LEFT_W + PLEDIT_SIDE_RIGHT_W, PLEDIT_SIDE_H_SRC))
        sides_img.paste(left_tile,  (0, 0))
        sides_img.paste(right_tile, (PLEDIT_SIDE_LEFT_W, 0))
        extras[PLEDIT_SIDES_KEY] = sides_img
        # M-CONN TASK-053: inactive title bar strip (y=21..40 of PLEDIT.BMP, same tiling).
        PLEDIT_TITLE_INACTIVE_Y0 = 21
        y_i = PLEDIT_TITLE_INACTIVE_Y0
        h_i = PLEDIT_TITLE_H_SRC  # 20px
        left_i  = pledit_src.crop((PLEDIT_TITLE_LEFT_X,  y_i, PLEDIT_TITLE_LEFT_X  + PLEDIT_TITLE_LEFT_W,  y_i + h_i))
        tile_i  = pledit_src.crop((PLEDIT_TITLE_TILE_X,  y_i, PLEDIT_TITLE_TILE_X  + PLEDIT_TITLE_TILE_W,  y_i + h_i))
        right_i = pledit_src.crop((PLEDIT_TITLE_RIGHT_X, y_i, PLEDIT_TITLE_RIGHT_X + PLEDIT_TITLE_RIGHT_W, y_i + h_i))
        title_inactive = Image.new("RGB", (PLEDIT_DISPLAY_W, h_i), PLEDIT_BODY_BG_RGB)
        title_inactive.paste(left_i, (0, 0))
        tx = PLEDIT_TITLE_LEFT_W
        while tx < PLEDIT_DISPLAY_W - PLEDIT_TITLE_RIGHT_W:
            clip_w = min(PLEDIT_TITLE_TILE_W, PLEDIT_DISPLAY_W - PLEDIT_TITLE_RIGHT_W - tx)
            title_inactive.paste(tile_i.crop((0, 0, clip_w, h_i)), (tx, 0))
            tx += PLEDIT_TITLE_TILE_W
        title_inactive.paste(right_i, (PLEDIT_DISPLAY_W - PLEDIT_TITLE_RIGHT_W, 0))
        extras[PLEDIT_TITLE_INACTIVE_KEY] = title_inactive
        print(f"  PLEDIT_TITLE_INACTIVE  {title_inactive.width}x{title_inactive.height}  (y=21..40 inactive variant)")
    except FileNotFoundError:
        print("  PLEDIT.BMP not in skin — PLEDIT atlas skipped")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    emit_assets(args.out_dir, main_bmp, cbut_bmp, font_bmp, extras)
    emit_layout_header(args.out_dir, main_bmp, cbut_bmp, font_bmp, extras)

    # Full 320×240 preview: main chrome + PLEDIT panel. Replaces the old
    # 275×116 main_bmp dump. Kept gitignored (host-only review artefact).
    # Per ADR-014 and ADR-018.
    render_full_preview(main_bmp, cbut_bmp, font_bmp, extras, args.out_dir / "skin_preview.png")

    # TASK-054 / M-HITZONES: hit-zone overlay PNG — same base, magenta zone rects.
    render_hitzones(Image.open(args.out_dir / "skin_preview.png"),
                    args.out_dir / "skin_hitzones.png")

    # Per-element crops + manifest, useful for visually reviewing what each
    # composite step put where. Gitignored.
    if composite_log:
        comp_dir = args.out_dir / "composite"
        comp_dir.mkdir(exist_ok=True)
        manifest_lines = [
            "# Static-composite manifest",
            "",
            "Generated by `tools/bake_skin.py`. Each row is one composite step",
            "that paints onto MAIN_BG before it's emitted as RGB565. Per",
            "[ADR-014](../../../../docs/architecture/decisions/ADR-014.md).",
            "",
            "| Element | Source file | Source crop (x, y, w, h) | Target on MAIN_BG (x, y, w, h) |",
            "|---|---|---|---|",
        ]
        for entry in composite_log:
            label = entry["label"]
            png_name = f"{label}.png"
            entry["rendered"].save(comp_dir / png_name)
            manifest_lines.append(
                f"| [{label}]({png_name}) | `{entry['source']}` | `{entry['src_rect']}` | `{entry['target']}` |"
            )
        manifest_lines.append("")
        manifest_lines.append("All PNGs in this directory are byte-identical to the source-cropped pixels (or, for text, the rendered glyph composite) — they are NOT what the runtime sees on its own; they are what gets pasted into MAIN_BG before flash.")
        manifest_lines.append("")
        (comp_dir / "MANIFEST.md").write_text("\n".join(manifest_lines))
        print(f"  composite/    {len(composite_log)} elements + MANIFEST.md")

    if args.preview:
        render_full_preview(main_bmp, cbut_bmp, font_bmp, extras, args.preview)
        print(f"Preview: {args.preview}")

    bytes_total = sum(b.width * b.height * 2 for b in (main_bmp, cbut_bmp, font_bmp))
    print(f"Wrote {args.out_dir}/skin_assets.c, {args.out_dir}/skin_layout.h")
    print(f"  MAIN_BG    {main_bmp.width}x{main_bmp.height} -> {main_bmp.width * main_bmp.height * 2} bytes")
    print(f"  CBUTTONS   {cbut_bmp.width}x{cbut_bmp.height} -> {cbut_bmp.width * cbut_bmp.height * 2} bytes")
    print(f"  FONT       {font_bmp.width}x{font_bmp.height} -> {font_bmp.width * font_bmp.height * 2} bytes")
    for fname, img in extras.items():
        sz = img.width * img.height * 2
        bytes_total += sz
        print(f"  {pathlib.Path(fname).stem:10s} {img.width}x{img.height} -> {sz} bytes")
    print(f"  total RGB565 {bytes_total} bytes (~{bytes_total // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
