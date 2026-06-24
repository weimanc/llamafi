#!/usr/bin/env python3
"""gen_taskbar_icons.py — Bake taskbar icon PNGs to RGB565 C arrays.

Reads:  app/icons/taskbar/<app>.png  (inactive, white-on-transparent)
        app/icons/taskbar/<app>_active.png  (active, colored)
Writes: app/gen/taskbar_icons.c
        app/gen/taskbar_icons.h

Icons are resized to TASKBAR_ICON_W × TASKBAR_ICON_H (from gen/shell_layout.h),
alpha-composited over TASKBAR_BG_RGB565, then stored as uint16_t RGB565 arrays.

Usage:
  ~/proj/esp/venv/bin/python3 app/tools/gen_taskbar_icons.py
  python3 app/tools/gen_taskbar_icons.py --icons-dir app/icons/taskbar --out-dir app/gen
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
]

# ---------------------------------------------------------------------------
# Defaults (may be overridden by --icon-size or parsed from shell_layout.h)
# ---------------------------------------------------------------------------
DEFAULT_ICON_W = 24
DEFAULT_ICON_H = 24
DEFAULT_BG_RGB565 = 0x2104  # ~#212021


def rgb565_to_rgb8(val: int):
    r = ((val >> 11) & 0x1F) * 255 // 31
    g = ((val >> 5) & 0x3F) * 255 // 63
    b = (val & 0x1F) * 255 // 31
    return (r, g, b)


def to_rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def img_to_rgb565_array(img: Image.Image, w: int, h: int, bg_rgb: tuple) -> list[int]:
    """Resize img to w×h, alpha-composite over bg, return list of RGB565 uint16."""
    img = img.convert("RGBA").resize((w, h), Image.LANCZOS)
    bg = Image.new("RGBA", (w, h), bg_rgb + (255,))
    bg.paste(img, mask=img.split()[3])
    rgb = bg.convert("RGB")
    import numpy as np
    arr = np.array(rgb)
    return [to_rgb565(int(r), int(g), int(b)) for r, g, b in arr.reshape(-1, 3)]


def parse_shell_layout(path: Path) -> tuple[int, int, int]:
    """Extract ICON_W, ICON_H, BG_RGB565 from shell_layout.h."""
    text = path.read_text()
    w = int(re.search(r"#define\s+TASKBAR_ICON_W\s+(\d+)", text).group(1))
    h = int(re.search(r"#define\s+TASKBAR_ICON_H\s+(\d+)", text).group(1))
    bg = int(re.search(r"#define\s+TASKBAR_BG_RGB565\s+(0x[0-9A-Fa-f]+)", text).group(1), 16)
    return w, h, bg


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
    args = parser.parse_args()

    icons_dir = Path(args.icons_dir)
    out_dir = Path(args.out_dir)
    layout_path = Path(args.layout)

    # Resolve icon dimensions + background color
    if args.icon_size:
        icon_w = icon_h = args.icon_size
        bg_rgb565 = DEFAULT_BG_RGB565
    elif layout_path.exists():
        icon_w, icon_h, bg_rgb565 = parse_shell_layout(layout_path)
    else:
        print(f"Warning: {layout_path} not found, using defaults ({DEFAULT_ICON_W}×{DEFAULT_ICON_H})",
              file=sys.stderr)
        icon_w, icon_h = DEFAULT_ICON_W, DEFAULT_ICON_H
        bg_rgb565 = DEFAULT_BG_RGB565

    bg_rgb = rgb565_to_rgb8(bg_rgb565)
    print(f"Icon size: {icon_w}×{icon_h}, bg: #{bg_rgb[0]:02X}{bg_rgb[1]:02X}{bg_rgb[2]:02X} (0x{bg_rgb565:04X})")

    # Load and convert all icons
    arrays: dict[str, list[int]] = {}
    missing = []

    for app in APPS:
        for suffix, var_suffix in [("", ""), ("_active", "_active")]:
            filename = icons_dir / f"{app}{suffix}.png"
            if not filename.exists():
                missing.append(str(filename))
                continue
            img = Image.open(filename)
            var_name = f"taskbar_icon_{app}{var_suffix}"
            arrays[var_name] = img_to_rgb565_array(img, icon_w, icon_h, bg_rgb)
            print(f"  {var_name}: {filename.name}")

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


if __name__ == "__main__":
    main()
