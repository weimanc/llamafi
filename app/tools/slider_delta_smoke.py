#!/usr/bin/env python3
"""slider_delta_smoke.py — TASK-365 (SliderWidget flicker fix) DUT check.

Why a plain before/after content diff can't test the flicker bug itself:
the old render() and the new renderDynamic() both draw the SAME correct
final pixels for any given (value, disabled) state — the bug was wasted
*intermediate* SPI writes (full-row erase then identical redraw), not
wrong output. That's a timing/liveness artifact, not a content diff one;
BP-048 (drag it live, eyeball no flash) is what actually catches it. This
script instead proves the thing a content diff CAN catch: that the new
scoped/diffed repaint (kZoneX0..kZoneX1 for track+knob, kValueX0..canvas
edge for the value number, label cell only on text change) reaches the
IDENTICAL pixel state a full ground-truth render() would — i.e. no stale
knob/digit artifacts left behind by the narrower erase rects, and the
Auto row above is never touched by a Level-row drag.

Method: drag the brightness Level slider start-to-end (value 1 -> 10,
exercising the 1-digit -> 2-digit value-cell width change too) using only
the incremental onMove()/onRelease() path (renderDynamic()), dump the
Auto+Level rows. Then leave and re-enter the Display section, which forces
a fresh full render() at the same settled value (dispLevel persists via
saveSettings() on release) — dump the same region again. Byte-identical
= the diffed path and the full path agree; a zone-bound bug (stale
pixels, wrong erase width) would show up as a nonzero diff.
"""
import sys
import time
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from screendump import DutLite, dump_with_retry, autodetect_port  # noqa: E402

SETTINGS_APP_ID = 10
DISPLAY_SECTION = 3
CONTENT_Y = 28
ROW_H = 26
DUMP_Y, DUMP_H = CONTENT_Y, 2 * ROW_H   # Auto row + Level row only (LDR row below is env-dependent)

CATEGORY_ROW = lambda i: (137, CONTENT_Y + i * ROW_H + 13)
AUTO_ROW_MID = (137, CONTENT_Y + 0 * ROW_H + 13)
BACK = (30, 14)

# sliderWidget.h track geometry (kKnobCX0/kKnobCX1) — same for every slider
# instance regardless of min/max, since it's the pixel track, not the value.
KNOB_CX0, KNOB_CX1 = 75, 241
LEVEL_ROW_MID_Y = CONTENT_Y + 1 * ROW_H + 13   # 67

results = []


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def tap(dut, x, y):
    dut.cmd(f"tap {x} {y}")
    time.sleep(0.15)


def section(dut):
    r = dut.cmd("get settingsSection")
    return r.get("section") if r.get("ok") else None


port = autodetect_port()
print(f"== opening {port} (DTR reset) ==", flush=True)
dut = DutLite(port)

boot = dut.cmd("get duty")
report("A0 debug cmd loop ready", boot.get("ok", False), str(boot))

dut.cmd(f"switchApp {SETTINGS_APP_ID}")
time.sleep(0.3)

tap(dut, *CATEGORY_ROW(DISPLAY_SECTION))
report("A1 Display section entered", section(dut) == DISPLAY_SECTION, str(section(dut)))

# Slider only responds while dispAuto is off — force it off if needed,
# restore it at the end (side effect, same convention as settings_kit_smoke.py).
d0 = dut.cmd("get duty")
orig_auto = bool(d0.get("auto"))
if orig_auto:
    tap(dut, *AUTO_ROW_MID)
d1 = dut.cmd("get duty")
report("B0 dispAuto off for the test", not d1.get("auto"), str(d1))

# Drive value to the MIN extreme first (single tap = Press+Release at the
# same x — DisplaySection's handleInput forwards both phases on a plain tap),
# so the drag below always climbs 1 -> 10 regardless of whatever value the
# slider started at.
tap(dut, KNOB_CX0, LEVEL_ROW_MID_Y)

# Drag the full track — every intermediate sample goes through onMove() ->
# renderDynamic(), the exact path TASK-365 changed. 8 steps crosses the
# 1-digit -> 2-digit value-label boundary ("1".."9" -> "10") on the way.
dut.cmd(f"drag {KNOB_CX0} {LEVEL_ROW_MID_Y} {KNOB_CX1} {LEVEL_ROW_MID_Y} 8")

incr_canvas = dump_with_retry(dut, 0, DUMP_Y, 275, DUMP_H)
report("C0 post-drag dump captured", incr_canvas is not None, "")

# Ground truth: leave the section and come back. DisplaySection::enter() ->
# repaint() -> SliderWidget::render() (the untouched full-draw path) at the
# now-persisted dispLevel=10.
tap(dut, *BACK)
report("D0 back to category list", section(dut) == -1, str(section(dut)))
tap(dut, *CATEGORY_ROW(DISPLAY_SECTION))
report("D1 Display re-entered (fresh repaint)", section(dut) == DISPLAY_SECTION, str(section(dut)))

truth_canvas = dump_with_retry(dut, 0, DUMP_Y, 275, DUMP_H)
report("D2 ground-truth dump captured", truth_canvas is not None, "")

diff = incr_canvas != truth_canvas
ndiff = int(diff.sum())
report("T_SLIDER_DELTA incremental renderDynamic() path matches fresh render()",
       ndiff == 0, f"{ndiff} px differ (Auto+Level rows, y{DUMP_Y}..{DUMP_Y+DUMP_H})")

# restore dispAuto
if orig_auto and not dut.cmd("get duty").get("auto"):
    tap(dut, *AUTO_ROW_MID)
tap(dut, *BACK)
dut.cmd(f"switchApp 0")

npass = sum(1 for _, ok, _ in results if ok)
nfail = len(results) - npass
print(f"\n== TASK-365 SLIDER DELTA SMOKE: {npass}/{len(results)} PASS ==", flush=True)
sys.exit(1 if nfail else 0)
