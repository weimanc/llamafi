#!/usr/bin/env python3
"""clock_delta_smoke.py — TASK-354 (M-CLOCK-FACE-COMMON pt 1) DUT check.

Steady-state assertion: with the delta engine, a second tick repaints AT
MOST the colon — so two screendumps of the time band taken a few seconds
apart (same minute) must be pixel-identical outside the colon column.
Before TASK-354, Flip and Nixie failed this by construction (full-face
wipe+repaint every second).

Runs the assertion for all four faces. Needs debug firmware. Region:
y0..134 (time band; excludes date/rssi, which legitimately change at
their own cadence). Colon column mask: x120..155 (generous, covers every
face's colon).

The capture pair must land inside one minute (digits change on the
minute boundary). Each ~135-row dump takes ~5-10 s; we wait for an early
tm_sec before starting and retry once if the minute rolled mid-pair.
"""
import sys
import time
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from screendump import DutLite, dump_with_retry, autodetect_port  # noqa: E402

BAND_H  = 135
MASK_X0, MASK_X1 = 120, 156   # colon column (all faces), end-exclusive

results = []


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def wait_for_early_second(max_sec=25):
    """Device is NTP-synced like the host; align pairs inside one minute."""
    while time.localtime().tm_sec >= max_sec:
        time.sleep(1)


def steady_pair(dut):
    wait_for_early_second()
    m0 = time.localtime().tm_min
    a = dump_with_retry(dut, 0, 0, 275, BAND_H)
    time.sleep(2)
    b = dump_with_retry(dut, 0, 0, 275, BAND_H)
    m1 = time.localtime().tm_min
    return a, b, (m0 == m1)


def check_face(dut, name, style):
    dut.cmd(f"set clockStyle {style}")
    time.sleep(2.5)   # repaint + settle (flip animation from force-draw done)
    # Retry on ANY nonzero diff, not just a host-side minute roll: the device
    # clock is NTP-synced independently and can sit seconds off the host, so
    # a digit rollover can land inside the pair while the host guard thinks
    # it's mid-minute. A genuine per-second repaint fails every attempt
    # (identical-value redraws produce identical pixels); a rollover is
    # transient and passes on retry.
    ndiff = -1
    for attempt in (1, 2, 3):
        a, b, same_minute = steady_pair(dut)
        diff = (a != b)
        diff[:, MASK_X0:MASK_X1] = False
        if name == "digital":
            # Digital's seconds bar (y100..125) advances every second by
            # design — per-second content like the colon, not a violation.
            diff[95:130, :] = False
        ndiff = int(diff.sum())
        if ndiff == 0 and same_minute:
            break
        print(f"  [retry] {name}: {ndiff} px diff, host_same_minute={same_minute} "
              f"(attempt {attempt})", flush=True)
    report(f"T_CLK_DELTA {name}: steady second tick repaints <= colon",
           ndiff == 0, f"{ndiff} px changed outside colon column")


port = autodetect_port()
print(f"== opening {port} (DTR reset) ==", flush=True)
dut = DutLite(port)

orig = dut.cmd("get clockStyle")
print("orig:", orig, flush=True)
dut.cmd("switchApp 1")
time.sleep(1.0)

check_face(dut, "digital", 0)
check_face(dut, "flip",    1)
check_face(dut, "nixie",   2)
check_face(dut, "vfd",     3)

# restore pre-test state
dut.cmd(f"set clockStyle {orig.get('val', 0)}")
dut.cmd(f"set nixieTheme {orig.get('nixieTheme', 0)}")
dut.cmd(f"set vfdTheme {orig.get('vfdTheme', 0)}")
dut.cmd("switchApp 0")

npass = sum(1 for _, ok, _ in results if ok)
nfail = len(results) - npass
print(f"\n== TASK-354 DELTA SMOKE: {npass}/{len(results)} PASS ==", flush=True)
sys.exit(1 if nfail else 0)
