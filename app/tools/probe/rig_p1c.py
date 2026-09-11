#!/usr/bin/env python3
"""probe/rig_p1c.py — PROP-011 X-P1c driver (TASK-677 H-1).

Reproduces EXP-026 §1 step 5's sequence — the one a throwaway script drove by
hand on 2026-09-11 — as a repeatable, committed tool:

  1. stamp phase=X-P1c-begin
  2. baseline `get bod`
  3. for each --secs value, in order: record the monitor log's current byte
     offset, stamp phase=X-P1c-run secs=N, send `set scanLoop N`, sleep
     N + --settle seconds, slice the log from the recorded offset, pull the
     scanLoop command's own JSON reply plus a count of `[bod] TRIP` and
     `reason=201` lines out of that slice, then `get bod`
  4. `get wifiCfg`, stamp phase=X-P1c-end

W' and trips/retry are derived from the JSON fields per PROP-011-runbook.md
§0.2 (r201*0.1s, and disc for retries), not from the rate-limited
`reason=201` line count — that count is still reported since EXP-026 §2
reported it too, for continuity with that transcript.

Talks to the board ONLY through the existing tmux monitor (lib.monitor_tmux)
— never opens the serial port (PROP-011-runbook.md §0.1 rule 1). `--dry-run`
prints the exact command/stamp sequence it would run and touches nothing.

    python3 probe/rig_p1c.py --secs 60,60,60,120 --out /tmp/p1c.jsonl
    python3 probe/rig_p1c.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from lib import monitor_tmux as mt  # noqa: E402
from lib import rigwatch  # noqa: E402

_SCANLOOP_RE = re.compile(r'\{"ok":true,"cmd":"set","var":"scanLoop"[^\n]*\}')
_BOD_GET_RE = re.compile(r'\{"ok":true,"cmd":"get","var":"bod"[^\n]*\}')
_TRIP_RE = re.compile(r"\[bod\] TRIP")
_REASON201_RE = re.compile(r"reason=201")

DEFAULT_SETTLE_S = 30.0
#: how long to wait for a reply after a query command (get bod, get wifiCfg)
QUERY_WAIT_S = 2.0


def _last_json(text: str, pattern: re.Pattern) -> dict | None:
    matches = pattern.findall(text)
    if not matches:
        return None
    try:
        return json.loads(matches[-1])
    except ValueError:
        return None


def parse_slice(text: str) -> dict:
    """Pure: the per-run numbers out of one log slice. Split out so the
    fixture-based tests below exercise it without tmux/time at all."""
    return {
        "scanLoop": _last_json(text, _SCANLOOP_RE),
        "tripsInSlice": len(_TRIP_RE.findall(text)),
        "reason201InSlice": len(_REASON201_RE.findall(text)),
    }


def parse_bod(text: str) -> dict | None:
    return _last_json(text, _BOD_GET_RE)


def get_bod() -> dict | None:
    off = mt.size()
    mt.send("get bod")
    time.sleep(QUERY_WAIT_S)
    return parse_bod(mt.read_from(off))


def run_one(secs: int, settle_s: float) -> dict:
    off = mt.size()
    rigwatch.stamp("note", phase="X-P1c-run", secs=str(secs))
    mt.send(f"set scanLoop {secs}")
    time.sleep(secs + settle_s)
    text = mt.read_from(off)
    result = parse_slice(text)
    result["secs"] = secs
    result["bod"] = get_bod()
    return result


def summary_line(r: dict) -> str:
    sl = r.get("scanLoop") or {}
    return (f"{r['secs']:>6}  {sl.get('r201', '?'):>6}  {sl.get('disc', '?'):>6}  "
           f"{r['tripsInSlice']:>12}  {r['reason201InSlice']:>16}")


def _dry_run(secs_list: list[int], settle_s: float) -> None:
    print("[dry-run] stamp phase=X-P1c-begin")
    print("[dry-run] send: get bod  (baseline)")
    for s in secs_list:
        print(f"[dry-run] stamp phase=X-P1c-run secs={s}")
        print(f"[dry-run] send: set scanLoop {s}")
        print(f"[dry-run] sleep {s + settle_s:.0f}s, slice log, send: get bod")
    print("[dry-run] send: get wifiCfg")
    print("[dry-run] stamp phase=X-P1c-end")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--secs", default="60,60,60,120",
                    help="comma-separated scanLoop durations, run in order "
                        "(default matches EXP-026)")
    ap.add_argument("--settle", type=float, default=DEFAULT_SETTLE_S,
                    help="extra seconds past --secs before slicing the log")
    ap.add_argument("--out", help="append one JSON line per run here too")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    secs_list = [int(s) for s in a.secs.split(",") if s.strip()]
    if not secs_list:
        ap.error("--secs produced no values")

    if a.dry_run:
        _dry_run(secs_list, a.settle)
        return 0

    out_fh = open(a.out, "a", encoding="utf-8") if a.out else None
    try:
        rigwatch.stamp("note", phase="X-P1c-begin")
        baseline = get_bod()
        print(f"baseline: {json.dumps(baseline)}")

        results = []
        for s in secs_list:
            r = run_one(s, a.settle)
            results.append(r)
            line = json.dumps(r)
            print(line)
            if out_fh:
                out_fh.write(line + "\n")

        off = mt.size()
        mt.send("get wifiCfg")
        time.sleep(QUERY_WAIT_S)
        wifi_cfg_text = mt.read_from(off)
        rigwatch.stamp("note", phase="X-P1c-end")

        print(f"\nget wifiCfg: {wifi_cfg_text.strip().splitlines()[-1] if wifi_cfg_text.strip() else '(no reply)'}")
        print("\nsummary:")
        print(f"{'secs':>6}  {'r201':>6}  {'disc':>6}  {'tripsInSlice':>12}  {'reason201InSlice':>16}")
        for r in results:
            print(summary_line(r))
    finally:
        if out_fh:
            out_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
