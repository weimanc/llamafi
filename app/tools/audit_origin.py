#!/usr/bin/env python3
"""
PC-side origin-relative audit (TASK-082 / T141–T146).

Verifies every winamp render and hit-test site is correctly origin-relative,
as a pre-gate for the M-MULTIAPP originX shift (22 → 0).

T141 — static grep: no bare integer X in tft draw/fill/pushImage calls.
T142 — TRANSPORT zone boundary tests at both originX values.
T143 — POSBAR + VOLUME boundary tests at both origins.
T144 — PLEDIT Z1/Z2 boundary tests + cross-origin shift regression.
T145 — right-margin gap and left-gutter DEADZONE tests.
T146 — full boundary regression at originX=0 (TASK-081 exit gate).

Usage:
  python3 tools/audit_origin.py              # all tests
  python3 tools/audit_origin.py --grep-only  # T141 only
  python3 tools/audit_origin.py --visual     # also emit gen/origin_audit.png
"""
import argparse
import pathlib
import re
import sys

TOOLS_DIR = pathlib.Path(__file__).parent
APP_DIR   = TOOLS_DIR.parent
GEN_DIR   = APP_DIR / "gen"
SRC_DIR   = APP_DIR / "src"
WINAMP_H  = SRC_DIR / "winamp" / "winampDisplay.h"
LAYOUT_H  = GEN_DIR / "skin_layout.h"
VUMETER_H = SRC_DIR / "winamp" / "vuMeter.h"

SCREEN_W, SCREEN_H = 320, 240


# TASK-251: parse the VIS rect from vuMeter.h (its real owner) rather than
# hand-mirroring it here — kills the last silent-drift constant in this audit.
def load_vis_rect(path=VUMETER_H):
    want = {"RECT_X": None, "LEFT_Y": None, "RECT_W": None, "VIS_H": None}
    for line in open(path):
        m = re.match(r'\s*constexpr\s+int\s+(\w+)\s*=\s*(\d+)', line)
        if m and m.group(1) in want:
            want[m.group(1)] = int(m.group(2))
    missing = [k for k, v in want.items() if v is None]
    if missing:
        raise SystemExit(f"audit_origin: VIS const(s) not found in {path}: {missing}")
    return want["RECT_X"], want["LEFT_Y"], want["RECT_W"], want["VIS_H"]


VIS_RECT_X, VIS_LEFT_Y, VIS_RECT_W, VIS_H = load_vis_rect()


# ── Layout ────────────────────────────────────────────────────────────────────

def load_layout(path=LAYOUT_H):
    """Parse skin_layout.h → {name: int} for all integer #defines."""
    d = {}
    for line in open(path):
        m = re.match(r'#define\s+(\w+)\s+(\d+)', line)
        if m:
            d[m.group(1)] = int(m.group(2))
    return d


def calc_origin_x(S):
    """Derive originX — mirrors firmware init and coords.py."""
    return (SCREEN_W - S["WINDOW_W"]) // 2


# ── Simulator ─────────────────────────────────────────────────────────────────

def hit_test(sx, sy, ox, S, oy=0):
    """
    Mirror firmware injectTouch dispatch (winampDisplay.h).
    Returns zone name string or 'DEADZONE'.

    PLEDIT Y uses absolute screen Y, matching the documented firmware mismatch
    (TASK-080 finding table); safe while originY=0.
    """
    wy = sy - oy

    # 1. Transport — cumulative-width scan, mirrors hitTestTransport
    by0, by1 = oy + S["CB_PREV_Y"], oy + S["CB_PREV_Y"] + 18
    if by0 <= sy < by1:
        seg = [("PREV",  S["CB_PREV_W"]),  ("PLAY",  S["CB_PLAY_W"]),
               ("PAUSE", S["CB_PAUSE_W"]), ("STOP",  S["CB_STOP_W"]),
               ("NEXT",  S["CB_NEXT_W"])]
        cur = ox + S["CB_PREV_X"]
        for name, w in seg:
            if sx < cur:
                break
            if sx < cur + w:
                return name
            cur += w

    # 2. Posbar
    if (ox + S["POSBAR_X"] <= sx < ox + S["POSBAR_X"] + S["POSBAR_W"]
            and S["POSBAR_Y"] <= wy < S["POSBAR_Y"] + S["POSBAR_H"]):
        return "POSBAR"

    # 3. Shuffle (dispatched before VOLUME in firmware)
    if (ox + S["SHUFFLE_X"] <= sx < ox + S["SHUFFLE_X"] + S["SHUFFLE_W"]
            and S["SHUFFLE_Y"] <= wy < S["SHUFFLE_Y"] + S["SHUFFLE_H"]):
        return "SHUFFLE"

    # 4. Repeat
    if (ox + S["REPEAT_X"] <= sx < ox + S["REPEAT_X"] + S["REPEAT_W"]
            and S["REPEAT_Y"] <= wy < S["REPEAT_Y"] + S["REPEAT_H"]):
        return "REPEAT"

    # 5. VIS
    if (ox + VIS_RECT_X <= sx < ox + VIS_RECT_X + VIS_RECT_W
            and VIS_LEFT_Y <= wy < VIS_LEFT_Y + VIS_H):
        return "VIS"

    # 6. Volume (after shuffle/repeat/vis in dispatch)
    if (ox + S["VOLUME_X"] <= sx < ox + S["VOLUME_X"] + S["VOLUME_FRAME_W"]
            and S["VOLUME_Y"] <= wy < S["VOLUME_Y"] + S["VOLUME_H"]):
        return "VOLUME"

    # 7–8. PLEDIT — firmware else branch; py vs absolute PLEDIT_ROWS_Y
    py       = sy - oy
    rows_top = S["PLEDIT_ROWS_Y"]
    rows_bot = rows_top + S["PLEDIT_ROW_COUNT"] * S["PLEDIT_ROW_H"]

    if (rows_top <= py < rows_bot
            and ox + S["PLEDIT_CONTENT_X"] + S["PLEDIT_CONTENT_W"] <= sx
            < ox + S["PLEDIT_W"]):
        return "PLEDIT-Z2"

    if (rows_top <= py < rows_bot
            and ox + S["PLEDIT_CONTENT_X"] <= sx
            < ox + S["PLEDIT_CONTENT_X"] + S["PLEDIT_CONTENT_W"]):
        return "PLEDIT-Z1"

    # 9. Logo
    if (ox + S["LOGO_X"] <= sx < ox + S["LOGO_X"] + S["LOGO_W"]
            and S["LOGO_Y"] <= wy < S["LOGO_Y"] + S["LOGO_H"]):
        return "LOGO"

    return "DEADZONE"


# ── Zone geometry ─────────────────────────────────────────────────────────────

def build_zones(S, ox):
    """Return {name: (sx0, sy0, w, h)} screen-absolute at given origin ox."""
    rows_y = S["PLEDIT_ROWS_Y"]
    rows_h = S["PLEDIT_ROW_COUNT"] * S["PLEDIT_ROW_H"]
    z2_w   = S["PLEDIT_W"] - S["PLEDIT_CONTENT_X"] - S["PLEDIT_CONTENT_W"]
    return {
        "PREV":      (ox + S["CB_PREV_X"],  S["CB_PREV_Y"],  S["CB_PREV_W"],  18),
        "PLAY":      (ox + S["CB_PLAY_X"],  S["CB_PLAY_Y"],  S["CB_PLAY_W"],  18),
        "PAUSE":     (ox + S["CB_PAUSE_X"], S["CB_PAUSE_Y"], S["CB_PAUSE_W"], 18),
        "STOP":      (ox + S["CB_STOP_X"],  S["CB_STOP_Y"],  S["CB_STOP_W"],  18),
        "NEXT":      (ox + S["CB_NEXT_X"],  S["CB_NEXT_Y"],  S["CB_NEXT_W"],  18),
        "POSBAR":    (ox + S["POSBAR_X"],   S["POSBAR_Y"],   S["POSBAR_W"],   S["POSBAR_H"]),
        "VOLUME":    (ox + S["VOLUME_X"],   S["VOLUME_Y"],   S["VOLUME_FRAME_W"], S["VOLUME_H"]),
        "SHUFFLE":   (ox + S["SHUFFLE_X"],  S["SHUFFLE_Y"],  S["SHUFFLE_W"],  S["SHUFFLE_H"]),
        "REPEAT":    (ox + S["REPEAT_X"],   S["REPEAT_Y"],   S["REPEAT_W"],   S["REPEAT_H"]),
        "VIS":       (ox + VIS_RECT_X,      VIS_LEFT_Y,      VIS_RECT_W,      VIS_H),
        "LOGO":      (ox + S["LOGO_X"],     S["LOGO_Y"],     S["LOGO_W"],     S["LOGO_H"]),
        "PLEDIT-Z2": (ox + S["PLEDIT_CONTENT_X"] + S["PLEDIT_CONTENT_W"],
                      rows_y, z2_w, rows_h),
        "PLEDIT-Z1": (ox + S["PLEDIT_CONTENT_X"], rows_y, S["PLEDIT_CONTENT_W"], rows_h),
    }


def boundary_cases(x0, y0, w, h):
    """4 inside (1px inset per edge) + 4 outside (1px beyond per edge).
    Returns [(sx, sy, expect_inside), ...]."""
    cx, cy = x0 + w // 2, y0 + h // 2
    return (
        [(x0 + 1, cy, True), (x0 + w - 2, cy, True),
         (cx, y0 + 1, True), (cx, y0 + h - 2, True)] +
        [(x0 - 1, cy, False), (x0 + w, cy, False),
         (cx, y0 - 1, False), (cx, y0 + h, False)]
    )


# ── T141 ──────────────────────────────────────────────────────────────────────

_DRAW_RE   = re.compile(r'tft\s*\.\s*(draw\w+|fill\w+|pushImage)\s*\(([^,)]*)',
                         re.MULTILINE)
_STR_FIRST = {"drawString", "drawCentreString", "drawNumber", "drawFloat", "fillScreen"}
_BARE_INT  = re.compile(r'^\s*[1-9]\d*\s*$')


def t141_grep(src=WINAMP_H):
    """T141: no bare integer ≥1 as the X argument of any tft draw/fill/pushImage call."""
    text = src.read_text()
    failures = []
    for m in _DRAW_RE.finditer(text):
        method, first = m.group(1), m.group(2).strip()
        if method in _STR_FIRST:
            continue
        if _BARE_INT.match(first):
            lineno = text[:m.start()].count('\n') + 1
            failures.append(
                f"{src.name}:{lineno}: tft.{method}({first},...) — bare integer X"
            )
    return failures


# ── Boundary helpers ──────────────────────────────────────────────────────────

def zone_boundary_failures(S, ox, tag):
    """4-inside + 4-outside for every zone at ox. Returns failure strings."""
    out = []
    for name, rect in build_zones(S, ox).items():
        for sx, sy, expect in boundary_cases(*rect):
            result = hit_test(sx, sy, ox, S)
            if (result == name) != expect:
                side = "inside" if expect else "outside"
                out.append(f"{tag} {name} {side} ({sx},{sy}) ox={ox} → {result!r}")
    return out


def cross_origin_failures(S, ox_from, ox_to):
    """
    Shift regression signal: the rightmost pixel of each zone at ox_from
    must NOT register in that zone at ox_to (zone shifted left by ox_from-ox_to).
    A hardcoded absolute X boundary would still fire here — that's the bug we catch.
    """
    out = []
    for name, (x0, y0, w, h) in build_zones(S, ox_from).items():
        sx, sy = x0 + w - 1, y0 + h // 2
        if hit_test(sx, sy, ox_from, S) != name:
            continue  # geometry sanity — skip, don't false-flag
        if hit_test(sx, sy, ox_to, S) == name:
            out.append(
                f"cross_origin {name}: right-edge sx={sx} still in zone at ox={ox_to} "
                f"— X boundary may be hardcoded"
            )
    return out


def t145_margin_failures(S, ox_current, ox_zero=0):
    """T145: right-margin gap (at ox=0) and left-gutter (at ox_current) must be DEADZONE."""
    out = []
    mid_y = S["CB_PREV_Y"] + 9   # mid-transport row Y

    # At ox_zero: x >= WINDOW_W must be DEADZONE (taskbar gap opens here)
    for sx in (ox_zero + S["WINDOW_W"], SCREEN_W - 1):
        r = hit_test(sx, mid_y, ox_zero, S)
        if r != "DEADZONE":
            out.append(f"T145 right-margin ox={ox_zero}: sx={sx} → {r!r}")

    # At ox_current>0: left gutter [0, ox_current) must be DEADZONE
    if ox_current > 0:
        for sx in (0, ox_current - 1):
            r = hit_test(sx, mid_y, ox_current, S)
            if r != "DEADZONE":
                out.append(f"T145 left-gutter ox={ox_current}: sx={sx} → {r!r}")

    return out


# ── Visual ────────────────────────────────────────────────────────────────────

def render_visual(S, out_path=GEN_DIR / "origin_audit.png"):
    """Single 320×240 PNG of the shipped layout (originX=0). Zone outlines (magenta)
    from skin_layout.h + green/red dots for boundary pass/fail. TASK-251: the legacy
    centered originX=22 panel was dropped — the firmware left-aligns the window
    (originX=0, taskbar on the right), so 22 was never a real config."""
    from PIL import Image, ImageDraw

    ox_vals  = [0]
    skin_src = GEN_DIR / "skin_preview.png"
    skin     = Image.open(skin_src).convert("RGB") if skin_src.exists() else None
    canvas   = Image.new("RGB", (SCREEN_W, SCREEN_H), (20, 20, 20))
    draw     = ImageDraw.Draw(canvas)

    for i, ox in enumerate(ox_vals):
        dx = i * SCREEN_W
        if skin:
            canvas.paste(skin, (dx + ox, 0))
        draw.line([(dx, 0), (dx, SCREEN_H - 1)], fill=(60, 60, 60), width=1)
        draw.text((dx + 4, 4), f"originX={ox}", fill=(200, 200, 200))
        for name, (x0, y0, w, h) in build_zones(S, ox).items():
            draw.rectangle([dx + x0, y0, dx + x0 + w - 1, y0 + h - 1],
                           outline=(200, 0, 200), width=1)
        for name, rect in build_zones(S, ox).items():
            for sx, sy, expect in boundary_cases(*rect):
                ok  = (hit_test(sx, sy, ox, S) == name) == expect
                col = (0, 220, 0) if ok else (220, 0, 0)
                draw.ellipse([dx + sx - 2, sy - 2, dx + sx + 2, sy + 2], fill=col)

    canvas.save(out_path)
    print(f"  visual → {out_path.name}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grep-only", action="store_true")
    p.add_argument("--visual",    action="store_true")
    args = p.parse_args()

    S     = load_layout()
    ox    = calc_origin_x(S)
    fails = []

    def section(tag, new_fails):
        nonlocal fails
        if new_fails:
            for f in new_fails:
                print(f"  FAIL  {f}")
        else:
            print(f"  PASS")
        fails.extend(new_fails)

    print(f"T141  static grep — no bare X integers in draw calls")
    section("T141", t141_grep())
    if args.grep_only:
        return 1 if fails else 0

    print(f"T142  TRANSPORT boundary (ox={ox} and ox=0)")
    transport = {"PREV", "PLAY", "PAUSE", "STOP", "NEXT"}
    t142 = []
    for test_ox in (ox, 0):
        for name, rect in build_zones(S, test_ox).items():
            if name not in transport:
                continue
            for sx, sy, expect in boundary_cases(*rect):
                if (hit_test(sx, sy, test_ox, S) == name) != expect:
                    side = "inside" if expect else "outside"
                    t142.append(f"T142 {name} {side} ({sx},{sy}) ox={test_ox}")
    section("T142", t142)

    print(f"T143  POSBAR + VOLUME boundary (ox={ox} and ox=0)")
    t143 = []
    for test_ox in (ox, 0):
        for name in ("POSBAR", "VOLUME"):
            for sx, sy, expect in boundary_cases(*build_zones(S, test_ox)[name]):
                if (hit_test(sx, sy, test_ox, S) == name) != expect:
                    side = "inside" if expect else "outside"
                    t143.append(f"T143 {name} {side} ({sx},{sy}) ox={test_ox}")
    section("T143", t143)

    print(f"T144  PLEDIT Z1/Z2 boundary + cross-origin shift regression")
    t144 = []
    for test_ox in (ox, 0):
        for name in ("PLEDIT-Z1", "PLEDIT-Z2"):
            for sx, sy, expect in boundary_cases(*build_zones(S, test_ox)[name]):
                if (hit_test(sx, sy, test_ox, S) == name) != expect:
                    side = "inside" if expect else "outside"
                    t144.append(f"T144 {name} {side} ({sx},{sy}) ox={test_ox}")
    t144 += cross_origin_failures(S, ox, 0)
    section("T144", t144)

    print(f"T145  canvas corners + right-margin gap")
    section("T145", t145_margin_failures(S, ox))

    print(f"T146  full boundary regression at ox=0")
    section("T146", zone_boundary_failures(S, 0, "T146"))

    if args.visual:
        print("visual")
        render_visual(S)

    if fails:
        print(f"\nFAILED — {len(fails)} check(s):")
        for f in fails:
            print(f"  {f}")
        return 1
    print(f"\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
