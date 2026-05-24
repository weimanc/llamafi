"""Coordinate helpers for test scripts — reads gen/skin_layout.h at import time.

ORIGIN_X is derived from SCREEN_W and WINDOW_W so this module needs no changes
when M-MULTIAPP shifts originX from 22 to 0.
"""
import re
import pathlib

_GEN = pathlib.Path(__file__).parent / "../SpotifyDiyThing/gen/skin_layout.h"


def _parse(path):
    d = {}
    for line in open(path):
        m = re.match(r'#define\s+(\w+)\s+([^/]+)', line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


S = _parse(_GEN)

SCREEN_W = 320
SCREEN_H = 240
ORIGIN_X = (SCREEN_W - int(S["WINDOW_W"])) // 2   # 22 pre-M-MULTIAPP; 0 after

# VIS area constants — from vuMeter.h (not in skin_layout.h).
_VIS_RECT_X = 24
_VIS_RECT_W = 76
_VIS_LEFT_Y = 43
_VIS_H      = 16


def tap_button(name: str) -> tuple[int, int]:
    """Screen centre of a named transport button. name: PREV|PLAY|PAUSE|STOP|NEXT"""
    x = ORIGIN_X + int(S[f"CB_{name}_X"]) + int(S[f"CB_{name}_W"]) // 2
    y = int(S[f"CB_{name}_Y"]) + int(S[f"CB_{name}_H"]) // 2
    return x, y


def button_left_x(name: str) -> int:
    """Left screen x of transport button (inclusive edge)."""
    return ORIGIN_X + int(S[f"CB_{name}_X"])


def button_right_x(name: str) -> int:
    """Right screen x of transport button (exclusive = first pixel outside)."""
    return ORIGIN_X + int(S[f"CB_{name}_X"]) + int(S[f"CB_{name}_W"])


def transport_y() -> int:
    """Y centre of the transport button row."""
    return int(S["CB_PREV_Y"]) + int(S["CB_PREV_H"]) // 2


def tap_logo() -> tuple[int, int]:
    return (ORIGIN_X + int(S["LOGO_X"]) + int(S["LOGO_W"]) // 2,
            int(S["LOGO_Y"]) + int(S["LOGO_H"]) // 2)


def tap_shuffle() -> tuple[int, int]:
    return (ORIGIN_X + int(S["SHUFFLE_X"]) + int(S["SHUFFLE_W"]) // 2,
            int(S["SHUFFLE_Y"]) + int(S["SHUFFLE_H"]) // 2)


def tap_repeat() -> tuple[int, int]:
    return (ORIGIN_X + int(S["REPEAT_X"]) + int(S["REPEAT_W"]) // 2,
            int(S["REPEAT_Y"]) + int(S["REPEAT_H"]) // 2)


def tap_vis() -> tuple[int, int]:
    return (ORIGIN_X + _VIS_RECT_X + _VIS_RECT_W // 2,
            _VIS_LEFT_Y + _VIS_H // 2)


def tap_posbar() -> tuple[int, int]:
    return (ORIGIN_X + int(S["POSBAR_X"]) + int(S["POSBAR_W"]) // 2,
            int(S["POSBAR_Y"]) + int(S["POSBAR_H"]) // 2)


def vol_drag_x() -> tuple[int, int]:
    """(x_start, x_end) inclusive screen x range for a volume drag."""
    x0 = ORIGIN_X + int(S["VOLUME_X"])
    return x0, x0 + int(S["VOLUME_FRAME_W"]) - 1


def vol_drag_y() -> int:
    """Y centre of the volume hitzone."""
    return int(S["VOLUME_Y"]) + int(S["VOLUME_H"]) // 2


def posbar_bounds() -> tuple[int, int, int, int]:
    """(x0, x1, y0, y1) inclusive screen coords of the POSBAR hitzone."""
    x0 = ORIGIN_X + int(S["POSBAR_X"])
    x1 = x0 + int(S["POSBAR_W"]) - 1
    y0 = int(S["POSBAR_Y"])
    y1 = y0 + int(S["POSBAR_H"]) - 1
    return x0, x1, y0, y1


def vol_bounds() -> tuple[int, int, int, int]:
    """(x0, x1, y0, y1) inclusive screen coords of the VOLUME hitzone."""
    x0 = ORIGIN_X + int(S["VOLUME_X"])
    x1 = x0 + int(S["VOLUME_FRAME_W"]) - 1
    y0 = int(S["VOLUME_Y"])
    y1 = y0 + int(S["VOLUME_H"]) - 1
    return x0, x1, y0, y1


def pledit_tap(row: int) -> tuple[int, int]:
    """Screen centre of PLEDIT content row (0-based)."""
    x = ORIGIN_X + int(S["PLEDIT_CONTENT_X"]) + int(S["PLEDIT_CONTENT_W"]) // 2
    y = (int(S["PLEDIT_Y"]) + int(S["PLEDIT_TITLE_H"])
         + row * int(S["PLEDIT_ROW_H"]) + int(S["PLEDIT_ROW_H"]) // 2)
    return x, y


def pledit_content_zone() -> tuple[int, int, int, int]:
    """(x0, x1, y0, y1) inclusive screen coords of PLEDIT Zone 1 (content area)."""
    x0 = ORIGIN_X + int(S["PLEDIT_CONTENT_X"])
    x1 = x0 + int(S["PLEDIT_CONTENT_W"]) - 1
    y0 = int(S["PLEDIT_ROWS_Y"])
    y1 = y0 + int(S["PLEDIT_ROW_COUNT"]) * int(S["PLEDIT_ROW_H"]) - 1
    return x0, x1, y0, y1


def pledit_swipe(direction: str) -> tuple[int, int, int, int]:
    """(x1, y1, x2, y2) for a ±30 px vertical swipe through Zone 1 centre.
    direction: 'up' → scrollOffset++ (dy=-30), 'down' → scrollOffset-- (dy=+30).
    """
    x, _ = pledit_tap(2)   # x-centre of content area
    x0, x1, y0, y1 = pledit_content_zone()
    mid_y = (y0 + y1) // 2
    if direction == "up":
        return x, mid_y + 15, x, mid_y - 15   # dy = -30
    else:
        return x, mid_y - 15, x, mid_y + 15   # dy = +30
