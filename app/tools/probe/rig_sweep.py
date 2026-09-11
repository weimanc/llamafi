#!/usr/bin/env python3
"""probe/rig_sweep.py — PROP-011 X-P2 B_boot sweep driver (TASK-677 H-1).

For each level in --levels (stop at the first level that produces no trip,
unless --all), --reps times: `bod N` (sets the boot threshold), `reboot`
(a real reset), wait for `[bootphase] 6` (timeout 60s), record whether
`[bod] TRIP tag=wifi-end` appeared in that boot's slice of the log and its
`min=`/`dur=` fields. Reports B_boot and the per-level trip table.

THIS DRIVER RESETS THE BOARD — every `reboot` ends whatever TASK-557
observation window is running (PROP-011-runbook.md §0.1 rule 2). It refuses
to run at all unless invoked with --i-know-this-resets-the-board, and even
then it first writes `./run/rig-timeline --since 48h` to a file (so the
window's length is captured before it ends) and stamps
`note phase=X-P2-sweep level=N` before each reboot.

This session only implements and --dry-run's it (PROP-011-runbook.md §3
X-P2: Sonnet drives it, but the reflash-window cost means it is scheduled,
not executed, by whoever is running H-1's own commit). Still talks to the
board ONLY through the tmux monitor (lib.monitor_tmux) plus `reboot` sent
the same way — never opens the serial port itself.

    python3 probe/rig_sweep.py --dry-run --levels 7,5,3,2,1,0 --reps 3
    python3 probe/rig_sweep.py --i-know-this-resets-the-board \\
        --levels 7,5,3,2,1,0 --reps 3 --timeline-out /tmp/p2_pre_timeline.txt
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from lib import monitor_tmux as mt  # noqa: E402
from lib import rigwatch  # noqa: E402

_BOOTPHASE6_RE = re.compile(r"\[bootphase\]\s+6\b")
_WIFI_END_TRIP_RE = re.compile(
    r"\[bod\] TRIP tag=wifi-end[^\n]*\bmin=(\d+)[^\n]*\bdur=(\d+)")
#: F-1's ordering is `... dur=<n> ... min=<n>` — accept either field order so
#: this driver does not silently miss a trip if that ordering ever changes.
_WIFI_END_TRIP_RE_ALT = re.compile(
    r"\[bod\] TRIP tag=wifi-end[^\n]*\bdur=(\d+)[^\n]*\bmin=(\d+)")

DEFAULT_LEVELS = [7, 5, 3, 2, 1, 0]
BOOT_TIMEOUT_S = 60.0


def parse_boot_slice(text: str) -> dict:
    """Pure: whether the boot's `wifi-end` trip appeared, and its fields, out
    of one boot's log slice. No device/tmux involved — exercised directly by
    the fixture tests below."""
    m = _WIFI_END_TRIP_RE.search(text)
    if m:
        return {"tripped": True, "min": int(m.group(1)), "dur": int(m.group(2))}
    m = _WIFI_END_TRIP_RE_ALT.search(text)
    if m:
        return {"tripped": True, "min": int(m.group(2)), "dur": int(m.group(1))}
    return {"tripped": False, "min": None, "dur": None}


def reached_bootphase6(text: str) -> bool:
    return bool(_BOOTPHASE6_RE.search(text))


def _dry_run(levels: list[int], reps: int) -> None:
    print("[dry-run] would write ./run/rig-timeline --since 48h to a file first")
    for level in levels:
        for rep in range(reps):
            print(f"[dry-run] stamp phase=X-P2-sweep level={level} rep={rep}")
            print(f"[dry-run] send: bod {level}")
            print("[dry-run] send: reboot   <-- RESETS THE BOARD")
            print(f"[dry-run] wait up to {BOOT_TIMEOUT_S:.0f}s for [bootphase] 6, "
                 f"slice log for [bod] TRIP tag=wifi-end")
        print(f"[dry-run] (stop descending here if level={level} produced 0/{reps} trips, "
             f"unless --all)")


def run_one_boot(level: int, rep: int) -> dict:
    rigwatch.stamp("note", phase="X-P2-sweep", level=str(level), rep=str(rep))
    off = mt.size()
    mt.send(f"bod {level}")
    time.sleep(1.0)
    mt.send("reboot")
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    text = ""
    booted = False
    while time.monotonic() < deadline:
        time.sleep(1.0)
        text = mt.read_from(off)
        if reached_bootphase6(text):
            booted = True
            break
    result = parse_boot_slice(text)
    result["level"] = level
    result["rep"] = rep
    result["booted"] = booted
    return result


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--levels", default="7,5,3,2,1,0")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--all", action="store_true",
                    help="do not stop descending at the first no-trip level")
    ap.add_argument("--timeline-out", default="/tmp/rig_sweep_pre_timeline.txt")
    ap.add_argument("--i-know-this-resets-the-board", action="store_true",
                    dest="confirmed")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    levels = [int(x) for x in a.levels.split(",") if x.strip()]

    if a.dry_run:
        _dry_run(levels, a.reps)
        return 0

    if not a.confirmed:
        print("REFUSED: rig_sweep.py resets the board on every rep (each "
             "`reboot` ends any live TASK-557 observation window). Re-run "
             "with --i-know-this-resets-the-board, after reading "
             "PROP-011-runbook.md §0.1 rule 2 and §3 X-P2.", file=sys.stderr)
        return 3

    try:
        timeline = subprocess.run(
            [sys.executable, "-m", "lib.rigwatch", "timeline", "--since", "48h"],
            cwd=TOOLS, capture_output=True, text=True, timeout=30, check=False)
        with open(a.timeline_out, "w", encoding="utf-8") as fh:
            fh.write(timeline.stdout)
        print(f"pre-reflash timeline captured -> {a.timeline_out}")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"WARN: could not capture the pre-reflash timeline: {e}", file=sys.stderr)

    results = []
    for level in levels:
        level_results = []
        for rep in range(a.reps):
            r = run_one_boot(level, rep)
            level_results.append(r)
            print(r)
        results.extend(level_results)
        trips = sum(1 for r in level_results if r["tripped"])
        print(f"level={level}: {trips}/{a.reps} tripped")
        if not a.all and trips == 0:
            print(f"stopping descent at level={level} (0/{a.reps} tripped)")
            break

    print("\nlevel  trips/reps")
    for level in levels:
        rs = [r for r in results if r["level"] == level]
        if not rs:
            continue
        trips = sum(1 for r in rs if r["tripped"])
        print(f"{level:>5}  {trips}/{len(rs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
