"""shell_layout.py — single shared parser for gen/shell_layout.h (LL-114).

Host tools must read firmware taskbar constants by PARSING the generated
header, never by mirrored literals: mirrors rot silently until a human
reaches for the tool (preview_layout's TEXT.BMP glyphs, preview_common's
hardcoded 24×24 feeding --export's write path — both found 2026-07-18).

Usage:
    from shell_layout import defines
    d = defines()                      # parse app/gen/shell_layout.h
    d["TASKBAR_ICON_W"], d["TASKBAR_BG_RGB565"], ...

`defines(path)` accepts an explicit header path (CLI tools with a
--layout flag). Char-literal defines (TASKBAR_ACTIVE_STYLE 'A') come back
as the single-character string.
"""
from __future__ import annotations

import pathlib
import re

DEFAULT_HEADER = pathlib.Path(__file__).parent.parent / "gen" / "shell_layout.h"

_DEFINE_RE = re.compile(
    r"^#define\s+(\w+)\s+(0x[0-9A-Fa-f]+|\d+|'.')", re.MULTILINE)


def defines(path: pathlib.Path | str = DEFAULT_HEADER) -> dict:
    """All #define'd int/hex/char constants from shell_layout.h as a dict."""
    text = pathlib.Path(path).read_text()
    out: dict = {}
    for name, val in _DEFINE_RE.findall(text):
        if val.startswith("'"):
            out[name] = val[1]
        elif val.startswith("0x"):
            out[name] = int(val, 16)
        else:
            out[name] = int(val)
    return out


def rgb565_to_rgb8(v: int) -> tuple[int, int, int]:
    """RGB565 → RGB8 tuple (bit-replication, matches gen_taskbar_icons)."""
    r = ((v >> 11) & 0x1F) * 255 // 31
    g = ((v >> 5) & 0x3F) * 255 // 63
    b = (v & 0x1F) * 255 // 31
    return (r, g, b)
