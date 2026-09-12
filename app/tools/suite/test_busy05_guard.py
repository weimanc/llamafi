#!/usr/bin/env python3
"""test_busy05_guard.py — negative suite for T-BUSY-05's post-switch guard.
TASK-582 (M-HARNESS2 Phase 2, P1), WP-C finding C-1.

WHY THIS EXISTS. The guard T-BUSY-05 used to run at the end of its body was

    if any(b is not True for b in results):
        bad = [str(r) for r in results if r is not False]
        if bad:
            fail(...)
            return
    pass_(...)

`any(b is not True for b in results)` is False exactly when every reading is
`True` — i.e. exactly when the amber never cleared, the one outcome the test
exists to catch. That shape falls through to `pass_()` on its own total
regression. Three `skip()` exits sit upstream of it, so the assertion is only
reached when all three of its preconditions hold — which is part of why an
inversion this total survived unnoticed. This suite pins
the FIXED adjudicator, `suite.serialdbg.shell._busy05_verdict`, against
the truth table the finding specified, so the inversion cannot come back
unnoticed. Host-only: no DUT, no port, no build.

    | arm            | results               | verdict |
    | all-clear       | [False, False, False] | pass    |
    | never-cleared   | [True, True, True]    | fail    | <- the regression
    | partial         | [True, False, False]  | fail    |
    | unreadable      | [None, None, None]    | unmet   |

The unreadable arm is not decoration: `_get_shell_busy` returns `None` when
`get shellBusy` itself fails, and a `None` folded into the boolean logic used
to be indistinguishable from "not busy" as far as `pass_()` was concerned. Per
TASK-596/R18 and lib/results.py's UNMET vocabulary, a read that never
succeeded asserts nothing about the firmware and must not silently become a
PASS (or a FAIL, which would blame the firmware for a serial hiccup) — it is
`unmet()`.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # app/tools/

from suite.serialdbg.shell import _busy05_verdict  # noqa: E402

FAILURES: list = []


def check(arm: str, cond: bool, detail: str):
    if cond:
        print(f"  [ok]   {arm}  {detail}")
    else:
        print(f"  [FAIL] {arm}  {detail}")
        FAILURES.append(arm)


def main() -> int:
    print("test_busy05_guard.py — T-BUSY-05 post-switch guard (TASK-582/C-1)")

    outcome, msg = _busy05_verdict([False, False, False])
    check("all-clear", outcome == "pass", f"[False]*3 -> {outcome} ({msg})")

    # This is the regression proper: the pre-fix guard passed on this input.
    outcome, msg = _busy05_verdict([True, True, True])
    check("never-cleared (C-1)", outcome == "fail",
          f"[True]*3 -> {outcome} ({msg}) — must FAIL, not pass on the amber "
          f"never clearing")

    outcome, msg = _busy05_verdict([True, False, False])
    check("partial", outcome == "fail",
          f"[True,False,False] -> {outcome} ({msg})")

    outcome, msg = _busy05_verdict([None, None, None])
    check("unreadable", outcome == "unmet",
          f"[None]*3 -> {outcome} ({msg}) — a failed read must not stand in "
          f"for a real reading (TASK-596/R18)")

    # A single failed read among otherwise-good ones still can't assert
    # anything about the firmware — unmet, not a firmware verdict either way.
    outcome, msg = _busy05_verdict([False, None, False])
    check("one unreadable among clears", outcome == "unmet",
          f"[False,None,False] -> {outcome} ({msg})")

    if FAILURES:
        print(f"FAIL: {len(FAILURES)} arm(s) failed: {FAILURES}")
        return 1
    print(f"OK: all {5} arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
