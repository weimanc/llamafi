#!/usr/bin/env python3
"""gen_taskbar_icons.py — Bake taskbar icon PNGs to RGB565 C arrays.

Reads:  app/icons/taskbar/<app>.png  (inactive, white-on-transparent)
        app/icons/taskbar/<app>_active.png  (active, colored)
Writes: app/gen/taskbar_icons.c
        app/gen/taskbar_icons.h

Icons are resized to TASKBAR_ICON_W × TASKBAR_ICON_H (from gen/shell_layout.h),
alpha-composited over TASKBAR_BG_RGB565, then stored as uint16_t RGB565 arrays.

ADR-051 (Option B): a source PNG whose dimensions already equal
TASKBAR_ICON_W × TASKBAR_ICON_H passes through with NO resample — the source
is the shipped icon (WYSIWYG for natively-authored pixel art). Only
mismatched (imported hi-res) sources take the LANCZOS resize path.

Every bake prints per-icon fill ratios (alpha>128 bbox ÷ target, per axis)
and warns — never fails — when the major axis lands outside
[FILL_WARN_LO, FILL_WARN_HI]. Minor axis is unchecked (wide-flat glyphs are
legal).

Usage:
  ~/proj/esp/venv/bin/python3 app/tools/gen_taskbar_icons.py
  python3 app/tools/gen_taskbar_icons.py --icons-dir app/icons/taskbar --out-dir app/gen
  python3 app/tools/gen_taskbar_icons.py --sheet   # + app/tools/icon_drafts/BAKED_SHEET.png
"""

import argparse
import re
import sys
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------------------
# App list — must match appRegistry.h order exactly.
# ---------------------------------------------------------------------------
APPS = [
    "spotify",
    "clock",
    "weather",
    "crypto",
    "matrix",
    "life",
    "settings",
    "stock",
    "aquarium",
    "teletext",
    "planeradar",
]

# ---------------------------------------------------------------------------
# Defaults (may be overridden by --icon-size or parsed from shell_layout.h)
# ---------------------------------------------------------------------------
DEFAULT_ICON_W = 24
DEFAULT_ICON_H = 24
DEFAULT_BG_RGB565 = 0x2104  # ~#212021

# ADR-051 warn-only fill band: major-axis bbox fill outside this range gets a
# WARN line at bake time (100% = edge-to-edge, the PlaneRadar overshoot mode).
FILL_WARN_LO = 0.85
FILL_WARN_HI = 0.97


def rgb565_to_rgb8(val: int):
    r = ((val >> 11) & 0x1F) * 255 // 31
    g = ((val >> 5) & 0x3F) * 255 // 63
    b = (val & 0x1F) * 255 // 31
    return (r, g, b)


def to_rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def prepare_icon(img: Image.Image, w: int, h: int) -> tuple[Image.Image, bool]:
    """RGBA at target size. ADR-051 Option B: exact-dimension sources pass
    through untouched (the PNG is the shipped icon); only mismatched sources
    get the LANCZOS resample. Returns (rgba, resampled)."""
    img = img.convert("RGBA")
    if img.size == (w, h):
        return img, False
    return img.resize((w, h), Image.LANCZOS), True


def fill_ratios(img: Image.Image) -> tuple[float, float]:
    """Per-axis bbox fill of alpha>128 ÷ canvas — the M-ICON-PIXELART
    measuring convention (matches the design doc's shipped-icon table)."""
    alpha = img.split()[3].point(lambda v: 255 if v > 128 else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        return 0.0, 0.0
    return (bbox[2] - bbox[0]) / img.width, (bbox[3] - bbox[1]) / img.height


def img_to_rgb565_array(img: Image.Image, w: int, h: int, bg_rgb: tuple) -> list[int]:
    """Alpha-composite a w×h RGBA over bg, return list of RGB565 uint16."""
    bg = Image.new("RGBA", (w, h), bg_rgb + (255,))
    bg.paste(img, mask=img.split()[3])
    rgb = bg.convert("RGB")
    import numpy as np
    arr = np.array(rgb)
    return [to_rgb565(int(r), int(g), int(b)) for r, g, b in arr.reshape(-1, 3)]


def parse_shell_layout(path: Path) -> dict:
    """Extract taskbar geometry + colours from shell_layout.h (shared
    parser per LL-114; per-key defaults preserved for partial headers)."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from shell_layout import defines as shell_defines

    d = shell_defines(path)
    return {
        "icon_w": d.get("TASKBAR_ICON_W", DEFAULT_ICON_W),
        "icon_h": d.get("TASKBAR_ICON_H", DEFAULT_ICON_H),
        "bg": d.get("TASKBAR_BG_RGB565", DEFAULT_BG_RGB565),
        # sheet-only (simulated slot rendering, mirrors taskbar.h)
        "taskbar_w": d.get("TASKBAR_W", 45),
        "slot_h": d.get("TASKBAR_SLOT_H", 40),
        "active_color": d.get("TASKBAR_ACTIVE_COLOR", 0x07E0),
        "sep_enabled": d.get("TASKBAR_SEP_ENABLED", 1),
        "sep_color": d.get("TASKBAR_SEP_COLOR", 0x4208),
    }


def array_to_img(data: list[int], w: int, h: int) -> Image.Image:
    """Decode a baked RGB565 array back to RGB8 — the sheet shows the true
    quantized pixels that ship, not the pre-quantization composite."""
    img = Image.new("RGB", (w, h))
    img.putdata([rgb565_to_rgb8(v) for v in data])
    return img


def render_sheet(arrays: dict, fills: dict, layout: dict, out_path: Path) -> None:
    """BAKED_SHEET.png — every icon pair at true baked size (NN-upscaled)
    inside a simulated slot: taskbar bg + 1px separator + 3px active-indicator
    bar on the active variant, per taskbar.h's drawSlot. Host inspection
    surface (ADR-051): iterate here, DUT is the final eyeball gate only."""
    from PIL import ImageDraw, ImageFont

    scale = 4
    slot_w, slot_h = layout["taskbar_w"], layout["slot_h"]
    icon_w, icon_h = layout["icon_w"], layout["icon_h"]
    off_x = (slot_w - icon_w) // 2   # taskbar.h iconOffX/iconOffY
    off_y = (slot_h - icon_h) // 2
    bg_rgb = rgb565_to_rgb8(layout["bg"])
    sep_rgb = rgb565_to_rgb8(layout["sep_color"])
    act_rgb = rgb565_to_rgb8(layout["active_color"])

    def slot_img(icon: Image.Image, active: bool) -> Image.Image:
        slot = Image.new("RGB", (slot_w, slot_h), bg_rgb)
        slot.paste(icon, (off_x, off_y))
        d = ImageDraw.Draw(slot)
        if layout["sep_enabled"]:
            d.line([(0, slot_h - 1), (slot_w - 1, slot_h - 1)], fill=sep_rgb)
        if active:
            d.rectangle([0, 0, 2, slot_h - 1], fill=act_rgb)
        return slot.resize((slot_w * scale, slot_h * scale), Image.NEAREST)

    pad, label_w = 12, 260
    cell_w, cell_h = slot_w * scale, slot_h * scale
    sheet_w = label_w + 2 * cell_w + 4 * pad
    sheet_h = len(APPS) * (cell_h + pad) + pad + 20
    sheet = Image.new("RGB", (sheet_w, sheet_h), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    d.text((pad, 4), f"baked {icon_w}x{icon_h} in {slot_w}x{slot_h} slot — "
                     f"inactive | active — fill = alpha-bbox / target",
           fill=(200, 200, 200), font=font)

    y = pad + 20
    for app in APPS:
        for i, suffix in enumerate(("", "_active")):
            var = f"taskbar_icon_{app}{suffix}"
            icon = array_to_img(arrays[var], icon_w, icon_h)
            sheet.paste(slot_img(icon, active=bool(i)),
                        (label_w + pad + i * (cell_w + pad), y))
        fw, fh = fills[f"taskbar_icon_{app}"]
        fwa, fha = fills[f"taskbar_icon_{app}_active"]
        d.text((pad, y + cell_h // 2 - 12),
               f"{app}\n  fill {fw:.0%}x{fh:.0%} | {fwa:.0%}x{fha:.0%}",
               fill=(230, 230, 230), font=font)
        y += cell_h + pad

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    print(f"Wrote {out_path}")


def format_array(name: str, data: list[int], w: int, h: int) -> str:
    lines = [f"const uint16_t {name}[{w * h}] = {{"]
    row_size = w
    for row in range(h):
        chunk = data[row * row_size:(row + 1) * row_size]
        lines.append("    " + ", ".join(f"0x{v:04X}" for v in chunk) + ",")
    lines.append("};")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--icons-dir", default="app/icons/taskbar",
                        help="Directory containing <app>.png and <app>_active.png")
    parser.add_argument("--out-dir", default="app/gen",
                        help="Output directory for .c and .h files")
    parser.add_argument("--layout", default="app/gen/shell_layout.h",
                        help="Path to shell_layout.h (for ICON_W/H and BG color)")
    parser.add_argument("--icon-size", type=int, default=None,
                        help="Override icon size (square). Ignores --layout sizes.")
    parser.add_argument("--sheet", action="store_true",
                        help="Also write the host-inspection contact sheet (BAKED_SHEET.png)")
    parser.add_argument("--sheet-out", default="app/tools/icon_drafts/BAKED_SHEET.png",
                        help="Contact sheet output path (with --sheet)")
    args = parser.parse_args()

    icons_dir = Path(args.icons_dir)
    out_dir = Path(args.out_dir)
    layout_path = Path(args.layout)

    # Resolve icon dimensions + background color
    if layout_path.exists():
        layout = parse_shell_layout(layout_path)
    else:
        print(f"Warning: {layout_path} not found, using defaults ({DEFAULT_ICON_W}×{DEFAULT_ICON_H})",
              file=sys.stderr)
        layout = {
            "icon_w": DEFAULT_ICON_W, "icon_h": DEFAULT_ICON_H, "bg": DEFAULT_BG_RGB565,
            "taskbar_w": 45, "slot_h": 40,
            "active_color": 0x07E0, "sep_enabled": 1, "sep_color": 0x4208,
        }
    if args.icon_size:
        layout["icon_w"] = layout["icon_h"] = args.icon_size
    icon_w, icon_h, bg_rgb565 = layout["icon_w"], layout["icon_h"], layout["bg"]

    bg_rgb = rgb565_to_rgb8(bg_rgb565)
    print(f"Icon size: {icon_w}×{icon_h}, bg: #{bg_rgb[0]:02X}{bg_rgb[1]:02X}{bg_rgb[2]:02X} (0x{bg_rgb565:04X})")

    # Load and convert all icons
    arrays: dict[str, list[int]] = {}
    fills: dict[str, tuple[float, float]] = {}
    missing = []

    for app in APPS:
        for suffix, var_suffix in [("", ""), ("_active", "_active")]:
            filename = icons_dir / f"{app}{suffix}.png"
            if not filename.exists():
                missing.append(str(filename))
                continue
            src = Image.open(filename)
            src_size = src.size
            rgba, resampled = prepare_icon(src, icon_w, icon_h)
            fw, fh = fill_ratios(rgba)
            var_name = f"taskbar_icon_{app}{var_suffix}"
            arrays[var_name] = img_to_rgb565_array(rgba, icon_w, icon_h, bg_rgb)
            fills[var_name] = (fw, fh)
            path_note = "resized" if resampled else "PASS-THROUGH"
            print(f"  {var_name}: {filename.name} "
                  f"({src_size[0]}x{src_size[1]} {path_note}, fill {fw:.0%}x{fh:.0%})")
            major = max(fw, fh)
            if not (FILL_WARN_LO <= major <= FILL_WARN_HI):
                print(f"    WARN: {var_name} major-axis fill {major:.0%} outside "
                      f"[{FILL_WARN_LO:.0%}, {FILL_WARN_HI:.0%}] (ADR-051 band; warn-only)")

    if missing:
        print(f"\nError: missing icon files:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Write .c file
    # -----------------------------------------------------------------------
    c_lines = [
        "// AUTO-GENERATED by tools/gen_taskbar_icons.py — do not edit by hand.",
        "// Re-run: ~/proj/esp/venv/bin/python3 app/tools/gen_taskbar_icons.py",
        '#include "taskbar_icons.h"',
        "",
    ]
    for var_name, data in arrays.items():
        c_lines.append(format_array(var_name, data, icon_w, icon_h))
        c_lines.append("")

    # Lookup table — two pointers per app, indexed by (int)AppId
    c_lines.append("const TaskbarIconPair kTaskbarIcons[(int)AppId::COUNT] = {")
    for app in APPS:
        c_lines.append(f"    {{ taskbar_icon_{app}, taskbar_icon_{app}_active }},  // AppId::{app.capitalize()}")
    c_lines.append("};")
    c_lines.append("")

    c_path = out_dir / "taskbar_icons.cpp"
    c_path.write_text("\n".join(c_lines))
    print(f"\nWrote {c_path}")

    # -----------------------------------------------------------------------
    # Write .h file
    # -----------------------------------------------------------------------
    h_lines = [
        "// AUTO-GENERATED by tools/gen_taskbar_icons.py — do not edit by hand.",
        "// Re-run: ~/proj/esp/venv/bin/python3 app/tools/gen_taskbar_icons.py",
        "#pragma once",
        '#include <stdint.h>',
        '#include "appShell.h"',
        "",
        f"#define TASKBAR_ICON_BAKED_W {icon_w}",
        f"#define TASKBAR_ICON_BAKED_H {icon_h}",
        f"#define TASKBAR_ICON_BAKED_PX ({icon_w} * {icon_h})",
        # TASK-242: number of baked icon pairs — taskbar.h static_asserts this
        # equals TASKBAR_APP_COUNT so a taskbar app can never be missing an icon.
        f"#define TASKBAR_ICON_COUNT {len(APPS)}",
        "",
        "struct TaskbarIconPair {",
        "    const uint16_t* inactive;",
        "    const uint16_t* active;",
        "};",
        "",
    ]

    for app in APPS:
        cap = app.capitalize()
        h_lines.append(f"extern const uint16_t taskbar_icon_{app}[TASKBAR_ICON_BAKED_PX];")
        h_lines.append(f"extern const uint16_t taskbar_icon_{app}_active[TASKBAR_ICON_BAKED_PX];")
    h_lines.append("")
    h_lines.append("// Indexed by (int)AppId — one pair per app.")
    h_lines.append("extern const TaskbarIconPair kTaskbarIcons[(int)AppId::COUNT];")
    h_lines.append("")

    h_path = out_dir / "taskbar_icons.h"
    h_path.write_text("\n".join(h_lines))
    print(f"Wrote {h_path}")

    if args.sheet:
        render_sheet(arrays, fills, layout, Path(args.sheet_out))


if __name__ == "__main__":
    main()
