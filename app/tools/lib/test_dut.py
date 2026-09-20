#!/usr/bin/env python3
"""test_dut.py — negative/positive suite for `lib.dut.poll_until`, the R22
wait contract (BP-068: a shared primitive without a test is not a contract).
TASK-607 / M-HARNESS2 R22.

R22 (docs/verification/M-HARNESS2-requirements.md:451-457, MUST): "Every wait
MUST terminate on an observed condition and MUST report the actual elapsed
time on both the pass and the fail path; a test MUST NOT pass merely because
a window expired." `poll_until` is the one shared primitive six of the
corpus's eleven wait helpers now call — this pins its contract directly,
independent of any one call site:

  * a `check()` that returns truthy inside the window terminates the wait
    IMMEDIATELY (does not keep polling to the deadline) and reports `ok=True`
    with the elapsed time actually spent, not the bound;
  * a `check()` that never returns truthy reports `ok=False` at (at least)
    the requested bound, with the value from its last attempt;
  * `check()` is polled on the caller's `interval`, not some fixed default —
    a wait helper's own cadence (0.3s/1.0s/2.0s/3.0s across the six migrated
    call sites) is preserved;
  * an exception raised inside `check()` propagates — `poll_until` does not
    swallow anything; catching a lost read is the caller's job, same as
    every pre-migration `_wait_*` loop already did;
  * a `timeout` of 0 (or already-elapsed) never calls `check()` at all and
    reports `ok=False`, `elapsed~=0` — matches the pre-migration
    `while time.monotonic() < deadline` idiom's own boundary, not a
    do-while that always samples once.

No DUT, no serial port, no network. Sub-second (uses real short sleeps, not
a virtual clock — the intervals under test are all <= 0.05s).

    python3 app/tools/lib/test_dut.py
"""

from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

from lib.dut import poll_until                                      # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


def main() -> int:
    print("== lib.dut.poll_until contract suite ==")

    # B1 — succeeds on the Nth attempt, terminates immediately (does not
    # keep polling to the bound), and elapsed reflects the attempts actually
    # made, not the full timeout.
    calls = []
    def succeeds_third():
        calls.append(time.monotonic())
        return len(calls) >= 3
    t0 = time.monotonic()
    ok, value, elapsed = poll_until(succeeds_third, timeout=5.0, interval=0.02)
    real_elapsed = time.monotonic() - t0
    check("B1 ok=True on eventual success", ok is True)
    check("B1 value is the truthy check() return", value is True)
    check("B1 exactly 3 attempts made (not polled to the 5s bound)",
          len(calls) == 3, len(calls))
    check("B1 reported elapsed is close to real elapsed (both paths measured "
          "the same way)", abs(elapsed - real_elapsed) < 0.05,
          (elapsed, real_elapsed))
    check("B1 terminated far under the 5s bound (didn't wait it out)",
          elapsed < 1.0, elapsed)

    # B2 — never succeeds: reports ok=False at (at least) the bound, with the
    # last value from check(), never merely because pass_() was reachable —
    # this is the harness-level mirror of what check_wait_expiry.py polices
    # statically in the corpus.
    attempts = []
    def never_succeeds():
        attempts.append(1)
        return False
    t0 = time.monotonic()
    ok, value, elapsed = poll_until(never_succeeds, timeout=0.1, interval=0.02)
    real_elapsed = time.monotonic() - t0
    check("B2 ok=False on expiry", ok is False)
    check("B2 value is the last (falsy) check() return", value is False)
    check("B2 at least one attempt was made", len(attempts) >= 1, len(attempts))
    check("B2 elapsed is close to real elapsed on the FAIL path too "
          "(R22: report actual elapsed on BOTH paths)",
          abs(elapsed - real_elapsed) < 0.05, (elapsed, real_elapsed))
    check("B2 elapsed is at least the requested bound", elapsed >= 0.1, elapsed)

    # B3 — polls on the CALLER's interval, not a hardcoded default.
    stamps = []
    def record_and_fail():
        stamps.append(time.monotonic())
        return False
    poll_until(record_and_fail, timeout=0.15, interval=0.05)
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    check("B3 inter-attempt gaps match the requested interval (~0.05s)",
          all(0.03 <= g <= 0.09 for g in gaps), gaps)

    # B4 — an exception inside check() propagates; poll_until swallows nothing.
    def raises():
        raise ValueError("simulated lost read")
    try:
        poll_until(raises, timeout=1.0, interval=0.01)
        check("B4 exception inside check() propagates", False,
              "no exception raised")
    except ValueError as exc:
        check("B4 exception inside check() propagates", str(exc) == "simulated lost read")

    # B5 — a zero/already-elapsed timeout calls check() zero times and
    # reports ok=False, elapsed~=0 (matches the pre-migration
    # `while time.monotonic() < deadline` idiom: the loop body never runs
    # if the deadline has already passed when the loop starts).
    zero_calls = []
    def never_called():
        zero_calls.append(1)
        return True
    ok, value, elapsed = poll_until(never_called, timeout=0.0, interval=0.01)
    check("B5 check() never called when timeout<=0", zero_calls == [], zero_calls)
    check("B5 ok=False with a zero timeout", ok is False)
    check("B5 elapsed ~= 0", elapsed < 0.02, elapsed)

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("OK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
