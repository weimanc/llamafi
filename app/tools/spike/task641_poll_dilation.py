#!/usr/bin/env python3
"""spike/task641_poll_dilation.py — can a POLLED oracle be falsified from a
healthy transcript? Measured on the real T_MA_03 body, host-only.

TASK-641 / M-HARNESS2-falsifier-taxonomy.md §3. `lib/test_replay.py` N4d showed
that freezing `lastPlaylistDraw` makes `_check_residue` poll past the end of the
recording: a transcript miss, correctly a void. This spike asks whether the
window ELAPSING — virtual-time dilation, which the engine already has — lets the
frozen arm reach its verdict inside the recorded exchanges, with the healthy
control still passing at the same dilation. No reply is invented either way.

Result 2026-09-08: dilation 1/5/50 -> miss at occurrence #2 of 2 (void);
dilation 100 and 1000 -> FAIL 12/12 exchanges, no miss; control PASS at both.
That is the measurement that makes `POLL` its own shape with its own operator.

Host-only: the scripted device is `test_replay.Device`; nothing opens a port.

    python3 app/tools/spike/task641_poll_dilation.py
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (TOOLS, os.path.join(TOOLS, "suite")):
    if p not in sys.path:
        sys.path.insert(0, p)

DILATIONS = (1.0, 5.0, 50.0, 100.0, 1000.0)
TID = "T_MA_03"


def main() -> int:
    import lib.test_replay as TR                      # the fixture, not the suite
    from lib import dispatch as D
    from lib import replay as RP
    from serialdbg import build_all_tests

    TR.TESTS = build_all_tests()
    body = TR.TESTS[TID]
    t_ok, v = TR.record(TR.Device())
    n = len(t_ok.exchanges)
    print(f"{TID}: recorded {v.value if v else v}, {n} exchanges, "
          f"`get lastPlaylistDraw` x{t_ok.count_of('get lastPlaylistDraw')}\n")

    frozen = {"v": None}

    def freeze(o):
        if frozen["v"] is None:
            frozen["v"] = o["ms"]
        return dict(o, ms=frozen["v"])

    t_frozen = t_ok.mutate(lambda c, _n, o: o.get("var") == "lastPlaylistDraw", freeze)

    def run(dut):
        D.run_body(TID, body, dut)

    print(f"{'dilation':>9}  {'arm':8s}  verdict  used   miss")
    confirmed_at = None
    for dil in DILATIONS:
        rows = {}
        for name, t in (("frozen", t_frozen), ("control", t_ok)):
            frozen["v"] = None
            with contextlib.redirect_stdout(io.StringIO()):
                verdict, _rec, used, _clk, miss, _err = RP._run_once(TID, run, t, dil)
            rows[name] = (verdict, used, miss)
            vv = verdict.value if verdict else "-"
            print(f"{dil:>9.0f}  {name:8s}  {vv:7s}  {used:>2}/{n}  "
                  f"{'MISS ' + str(miss)[:48] if miss else 'no'}")
        fv, _fu, fm = rows["frozen"]
        cv, _cu, cm = rows["control"]
        if (confirmed_at is None and fm is None and cm is None
                and fv is not None and fv.value == "FAIL" and cv is not None and cv.value == "PASS"):
            confirmed_at = dil

    print()
    if confirmed_at is None:
        print("NOT falsifiable by freeze+dilation within the recording at any tried dilation")
        return 1
    print(f"CONFIRMED: freeze + dilation {confirmed_at:.0f} falsifies {TID} inside the "
          f"recording; control PASSes at the same dilation. POLL is a shape.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
