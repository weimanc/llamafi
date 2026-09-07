#!/usr/bin/env python3
"""test_progress_atoms.py — negative suite for the M-DATATASK-PROGRESS oracle.
TASK-657 (oracle sweep A-6), BP-068.

WHY THIS EXISTS. The finding this oracle answers was that a test can READ a
value on every poll and still assert nothing about it — T170 reads
`stockQuoteProgress` in its loop and only ever uses it to enrich a failure
message, so a T170 PASS is precisely the outcome in which the atom's value was
never checked. An oracle written to fix that failure mode is exactly the kind of
oracle that can quietly have it: `_progress_atom_verdict` could return "pass" on
an observation in which nothing was observed, and nothing would say so.

So this suite breaks the oracle the four specific ways it exists to catch, plus
two ways the OBSERVER could lie to it. Host-only: no DUT, no port, no build,
no network. ~0.1 s.

    | arm | break                                    | required outcome |
    | N1  | atom never leaves the -1 sentinel        | fail             |
    | N2  | atom takes a value outside its domain    | fail             |
    | N2b | ...as classified by the OBSERVER, not by  | fail             |
    |     | the test fixture (see the arm's docstring)|                  |
    | N2c | stockQuoteProgress takes a ticker index    | fail             |
    |     | (a value the pre-TASK-660 [0,7] bound      |                  |
    |     | accepted, and the real {0,-1} domain does  |                  |
    |     | not) — proves the narrowing bites          |                  |
    | N3  | atom never returns to -1 after the fetch | fail             |
    | N4  | no fetch completed inside the window     | unmet, not fail  |
    | P1  | a clean, correct observation             | pass             |
    | N5  | the observer's completion oracle is the  | the observer must|
    |     | atom itself (the T170 shape)             | not use the atom |
    | N6  | the observer reports polls it never made | polls == reality |
    | N7  | done() is ALREADY TRUE when the window   | unmet, not fail, |
    |     | opens (the latched-`*Ready` shape)       | and 0 samples    |

N4 is not decoration. A window in which no fetch ran proves nothing about the
atom, and scoring it `fail` would make the id flaky on a slow network — which is
how a real assertion gets weakened into a proxy a year later.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from suite.serialdbg._helpers import (            # noqa: E402
    _observe_progress_atom, _progress_atom_verdict, _PROGRESS_ATOM_DOMAIN,
)

FAILURES: list = []


def check(arm: str, cond: bool, detail: str):
    if cond:
        print(f"  [ok]   {arm}  {detail}")
    else:
        print(f"  [FAIL] {arm}  {detail}")
        FAILURES.append(arm)


def obs(seen, *, completed=True, returned_idle=True, polls=None, var="weatherFetchPhase"):
    """Build an observation record the way _observe_progress_atom would."""
    lo, hi = _PROGRESS_ATOM_DOMAIN[var]
    nonsentinel = sorted(v for v in seen if v != -1)
    return {
        "polls": len(seen) * 4 if polls is None else polls,
        "seen": sorted(seen),
        "nonsentinel": nonsentinel,
        "bad": sorted(v for v in nonsentinel if not (lo <= v <= hi)),
        "completed": completed,
        "returned_idle": returned_idle,
    }


# ── the verdict function, broken four ways ───────────────────────────────────

def arm_n1():
    """Sentinel-only across a COMPLETED fetch is the milestone's own defect:
    the atom it delivered is not being written. Must be fail, never pass."""
    outcome, msg = _progress_atom_verdict("weatherFetchPhase", obs([-1]))
    check("N1", outcome == "fail", f"sentinel-only -> {outcome}")
    check("N1", "never left" in msg, "message names the actual defect")


def arm_n2():
    """A value outside the documented domain is a contract break — the atom is
    being written, but not with anything its consumers can interpret."""
    outcome, _ = _progress_atom_verdict("cryptoFetchPhase", obs([-1, 0, 1, 9]))
    check("N2", outcome == "fail", f"out-of-domain 9 in [0,2] -> {outcome}")
    # And the boundary must NOT trip it: 2 is inside the domain.
    outcome, _ = _progress_atom_verdict("cryptoFetchPhase", obs([-1, 0, 1, 2]))
    check("N2", outcome == "pass", f"in-domain boundary 2 -> {outcome}")
    outcome, _ = _progress_atom_verdict("stockChartProgress",
                                        obs([-1, 7], var="stockChartProgress"))
    check("N2", outcome == "fail", f"7 illegal for stockChartProgress -> {outcome}")


def arm_n2c():
    """THE NARROWED BOUND MUST BITE (TASK-660, BP-068).

    `stockQuoteProgress` is a busy flag with domain {0, -1} — the firmware
    writes 0 at the top of the spark fetch and -1 at the bottom, and nothing
    else is reachable. Its bound read (0, 7) until TASK-660, copied from a
    `dataTask.h` comment that TASK-249 had already made false. Under [0,7] the
    clause could not fail on any build: the only value a correct build can
    produce is 0, and {0} is inside [0,7].

    This arm is the proof that the narrowing changed an outcome. Each ticker
    index the old bound accepted must now be rejected, so a firmware change
    that reintroduced per-symbol indices would be caught. The old bound is
    asserted dead here on purpose: restoring it turns this arm red."""
    lo, hi = _PROGRESS_ATOM_DOMAIN["stockQuoteProgress"]
    check("N2c", (lo, hi) == (0, 0),
          f"stockQuoteProgress domain is the as-built {{0, -1}}, bound {(lo, hi)}")
    # Every value the vacuous [0,7] bound accepted and the real domain does not.
    for v in range(1, 8):
        outcome, msg = _progress_atom_verdict(
            "stockQuoteProgress", obs([-1, v], var="stockQuoteProgress"))
        check("N2c", outcome == "fail",
              f"ticker-index {v} rejected (old [0,7] accepted it) -> {outcome}")
        check("N2c", str(v) in msg, f"message names the offending value {v}")
    # And the positive control: the one legal in-flight value still passes, so
    # the narrowing did not simply break the id for every observation.
    outcome, _ = _progress_atom_verdict("stockQuoteProgress",
                                        obs([-1, 0], var="stockQuoteProgress"))
    check("N2c", outcome == "pass", f"busy-flag 0 still legal -> {outcome}")

    # END-TO-END through the real observer, for the same reason N2b exists: the
    # fixture computes `bad` itself, so a fixture-only arm would not exercise
    # the classification under test.
    dut = FakeDut("stockQuoteProgress", [-1, 0, 3, -1, -1])
    calls = {"n": 0}

    def done():
        calls["n"] += 1
        return calls["n"] >= 4

    o = _observe_progress_atom(dut, "stockQuoteProgress", done,
                               timeout_s=5.0, test_id="N2c")
    check("N2c", o["bad"] == [3],
          f"observer classified ticker-index 3 as out-of-domain: {o['bad']}")
    outcome, _ = _progress_atom_verdict("stockQuoteProgress", o)
    check("N2c", outcome == "fail", f"end-to-end ticker index -> {outcome}")


def arm_n2b():
    """N2 END-TO-END, and it is here because N2 alone was NOT ENOUGH.

    Found while running the mutations BP-068 requires: deleting the domain
    computation in `_observe_progress_atom` (`bad = []`) left the whole suite
    green, because `obs()` above computes `bad` in the fixture and hands it to
    the verdict function ready-made. The fixture was testing itself. This arm
    drives the real observer against a device emitting an out-of-domain value,
    so the computation that classifies it is the one under test.

    That is the same defect class as the finding this whole oracle answers: a
    value read on every poll but never actually checked."""
    dut = FakeDut("stockChartProgress", [-1, 0, 9, -1, -1])
    calls = {"n": 0}

    def done():
        calls["n"] += 1
        return calls["n"] >= 4

    o = _observe_progress_atom(dut, "stockChartProgress", done,
                               timeout_s=5.0, test_id="N2b")
    check("N2b", o["bad"] == [9], f"observer classified 9 as out-of-domain: {o['bad']}")
    outcome, msg = _progress_atom_verdict("stockChartProgress", o)
    check("N2b", outcome == "fail", f"end-to-end out-of-domain -> {outcome}")
    check("N2b", "9" in msg, "message names the offending value")

    # Positive control on the same path: legal values must survive it.
    dut = FakeDut("weatherFetchPhase", [-1, 0, 1, 2, -1])
    calls = {"n": 0}
    o = _observe_progress_atom(dut, "weatherFetchPhase", done,
                               timeout_s=5.0, test_id="N2b")
    check("N2b", o["bad"] == [], f"legal values produce no bad set: {o['bad']}")


def arm_n3():
    """A stuck atom reports a fetch that is not running — the failure an
    operator would act on wrongly. Must not be papered over by 'it did move'."""
    outcome, msg = _progress_atom_verdict("weatherFetchPhase",
                                          obs([-1, 0, 1], returned_idle=False))
    check("N3", outcome == "fail", f"never returned to idle -> {outcome}")
    check("N3", "did not return to -1" in msg, "message names the stuck atom")


def arm_n4():
    """No fetch completed: the premise did not hold. UNMET, never fail (that
    would make the id flaky on a slow network) and never pass."""
    outcome, msg = _progress_atom_verdict("cryptoFetchPhase",
                                          obs([-1], completed=False))
    check("N4", outcome == "unmet", f"no fetch completed -> {outcome}")
    check("N4", "premise" in msg, "message says the premise did not hold")
    # Even a PERFECT-looking value set is unmet if nothing completed — the
    # completion oracle is what makes the observation mean anything.
    outcome, _ = _progress_atom_verdict("cryptoFetchPhase",
                                        obs([-1, 0, 1, 2], completed=False))
    check("N4", outcome == "unmet", f"good values but no completion -> {outcome}")


def arm_p1():
    """The positive control. Without it the three fails above are satisfied by
    a function that returns 'fail' unconditionally."""
    outcome, msg = _progress_atom_verdict("weatherFetchPhase", obs([-1, 0, 1, 2]))
    check("P1", outcome == "pass", f"clean observation -> {outcome}")
    check("P1", "left the sentinel" in msg, "message states what was observed")


# ── the observer, broken two ways ────────────────────────────────────────────

class FakeDut:
    """Answers `get <var>` from a scripted sequence. Records every command so
    the arms can assert what the observer did and did not ask for."""

    def __init__(self, var, values):
        self.var = var
        self.values = list(values)
        self.asked: list = []

    def get_int(self, var, timeout=3.0):
        self.asked.append(var)
        if var != self.var:
            raise AssertionError(f"observer read {var!r}, expected {self.var!r}")
        return self.values.pop(0) if self.values else -1

    def cmd(self, s, timeout=3.0):                      # pragma: no cover
        self.asked.append(s)
        return {"ok": True}


def arm_n5():
    """THE T170 SHAPE. If the observer ever used the atom as its own completion
    signal, the id would assert a tautology. The completion oracle is a
    callable the caller owns; this arm proves the observer never substitutes."""
    dut = FakeDut("weatherFetchPhase", [-1, 0, 1, 2, -1, -1])
    calls = {"n": 0}

    def done():
        calls["n"] += 1
        return calls["n"] >= 4          # completion decided OUTSIDE the atom

    o = _observe_progress_atom(dut, "weatherFetchPhase", done,
                               timeout_s=5.0, test_id="N5")
    check("N5", all(a == "weatherFetchPhase" for a in dut.asked),
          "observer read only the atom under test, nothing else")
    check("N5", calls["n"] >= 1, "the caller's completion oracle was consulted")
    check("N5", o["completed"] is True, "completion came from done(), not the atom")
    outcome, _ = _progress_atom_verdict("weatherFetchPhase", o)
    check("N5", outcome == "pass", f"end-to-end clean run -> {outcome}")


def arm_n6():
    """A poll count that does not match reality would let N1's message ('never
    left the sentinel across N polls') lie about how hard it looked — the
    number an operator uses to decide whether to believe the result."""
    dut = FakeDut("cryptoFetchPhase", [-1, -1, -1, 0, -1])
    calls = {"n": 0}

    def done():
        calls["n"] += 1
        # >= 6, not >= 5: the entry guard (arm N7) calls done() ONCE before the
        # window opens, so call 1 is the guard and calls 2..6 are the window's
        # five iterations. The arm is about polls matching reality, and reality
        # now includes that first call.
        return calls["n"] >= 6

    o = _observe_progress_atom(dut, "cryptoFetchPhase", done,
                               timeout_s=5.0, test_id="N6")
    reads = [a for a in dut.asked if a == "cryptoFetchPhase"]
    # The idle-confirmation loop reads the atom too, so polls counts the
    # observation window only and must never exceed the total reads.
    check("N6", o["polls"] <= len(reads),
          f"polls={o['polls']} <= reads={len(reads)}")
    check("N6", o["polls"] == 5, f"polls={o['polls']} matches the 5 window reads")
    check("N6", o["seen"] == [-1, 0], f"seen={o['seen']} is the distinct set read")


def arm_n7():
    """The entry guard. A completion oracle that is ALREADY TRUE when the
    observation begins cannot bracket a fetch: the loop exits on its first
    iteration, having sampled an atom that has already returned to its
    sentinel, and N1's message then reports 'never left the -1 sentinel' — a
    red cell naming a firmware gap that is not there.

    That is not hypothetical. It is what T_WX_07 and T_CX_07 both returned on
    their first hardware run (2026-09-06): `(1 polls)`, against latched
    `weatherReady`/`cryptoReady` flags that had been true since the app's first
    successful fetch. The honest verdict is UNMET — the premise (an unstarted
    fetch to watch) did not hold — and no sample should be taken at all."""
    dut = FakeDut("weatherFetchPhase", [-1, -1, -1])
    o = _observe_progress_atom(dut, "weatherFetchPhase", lambda: True,
                               timeout_s=5.0, test_id="N7")
    check("N7", o["preheld"] is True, "done() true at entry -> preheld")
    check("N7", o["polls"] == 0, f"polls={o['polls']} — the atom was not sampled")
    check("N7", dut.asked == [], "the observer read nothing at all")
    outcome, msg = _progress_atom_verdict("weatherFetchPhase", o)
    check("N7", outcome == "unmet", f"preheld oracle -> {outcome} (not fail)")
    check("N7", "already TRUE" in msg, "the message names the real cause")


def main():
    print("=== test_progress_atoms.py — M-DATATASK-PROGRESS oracle negatives ===")
    for fn in (arm_n1, arm_n2, arm_n2b, arm_n2c, arm_n3, arm_n4, arm_p1,
               arm_n5, arm_n6, arm_n7):
        fn()
    if FAILURES:
        print(f"\nFAILED arms: {sorted(set(FAILURES))}")
        return 1
    print("\n=== all arms pass — the oracle breaks the way it is meant to ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
