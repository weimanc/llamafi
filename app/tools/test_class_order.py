#!/usr/bin/env python3
"""test_class_order.py — EC-G8, the inversion test. TASK-566 / M-TESTARCH §9.

THIS IS THE MACHINE FORM OF THE DESIGN'S THESIS, and it exists because every
other exit criterion asserts that the machinery EXISTS while none asserted the
property the machinery is FOR:

    a class-N failure must never be reportable as a class-N+1 failure.

Parameterised over the ladder, stubbed, host-only — no DUT, no port, no build
(the `test_serial_classify.py` stub-the-serial pattern, BP-068).

    | stubbed failure | assertion                                              |
    | RIG             | zero results printed at all; exit 3                    |
    | HEALTH          | every CORE/APP/FEATURE id NOT-RUN(blocked-by=HEALTH/…);|
    |                 | ZERO PASS, FAIL, SKIP or FLAKY-PASS among them; exit 4 |
    | CORE            | the failing id is FAIL; every APP/FEATURE id is        |
    |                 | NOT-RUN(blocked-by=CORE/…); exit 1                     |
    | APP             | the failing id is FAIL; FEATURE ids RUN NORMALLY —     |
    |                 | this arm asserts the DROP of rule 5 (§4.2), so per-app  |
    |                 | blocking cannot silently come back                     |

THE ASSERTION IS ON THE ABSENCE OF ANY OTHER VERDICT, not on the presence of
NOT-RUN. A weaker form passes a runner that emits both, which is exactly the
failure mode §2.2 measured: 200 ids reported as FAIL when none of them ran.

Two further arms that are not in EC-G8's table and earn their place anyway:

  * THE INERT ARM. With `class_order=False` — today's shipped default, and the
    state @PM's ruling holds TASK-566 in — the loop must reproduce today's
    behaviour exactly: registry order, no health phase, nothing blocked, exit
    0/1. A landing that is supposed to change nothing needs a test saying so.
  * THE ADJUDICATION ARM. `_order.unadjudicated()` must be empty. @VE §18.6(c)
    requires the 0->1-edge enumeration as a PRECONDITION of the switch rather
    than an output of it; this is what stops a new order-fragile test being
    added without anyone adjudicating it.

    python3 app/tools/test_class_order.py
"""

from __future__ import annotations

import io
import os
import contextlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import results as R                                        # noqa: E402
from suite.serialdbg import _gate, _order                           # noqa: E402

FAILURES: list = []


def check(cond, msg):
    print(("  [PASS] " if cond else "  [FAIL] ") + msg)
    if not cond:
        FAILURES.append(msg)


#: A miniature ladder. Ids are synthetic on purpose: this asserts the PROPERTY,
#: not the live registry, and binding it to real ids would make it fail for
#: reasons that have nothing to do with the property.
META = {
    "H1": {"cls": "HEALTH", "scope": "shell"},
    "C1": {"cls": "CORE", "scope": "shell"},
    "C2": {"cls": "CORE", "scope": "shell"},
    "A1": {"cls": "APP", "scope": "Stock"},
    "F1": {"cls": "FEATURE", "scope": "Stock"},
    "F2": {"cls": "FEATURE", "scope": "Clock"},
}
SELECTED = ["F1", "A1", "C1", "F2", "C2"]        # deliberately NOT class order


def _dispatch_factory(failing=()):
    ran = []

    def dispatch(tid):
        ran.append(tid)
        if tid in failing:
            R.fail(tid, "stubbed failure")
        else:
            R.pass_(tid)
    return dispatch, ran


def _run(failing=(), health_failed=(), class_order=True, health_mode="gate"):
    R.reset()
    dispatch, ran = _dispatch_factory(failing)
    health_calls = []

    def run_health(ids):
        health_calls.append(list(ids))
        for tid in ids:
            if tid in health_failed:
                R.fail(tid, "stubbed health failure")
            else:
                R.pass_(tid)
        return [t for t in ids if t in health_failed]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _gate.run_suite(SELECTED, META, dispatch, class_order=class_order,
                             health_ids=["H1"], run_health=run_health,
                             health_mode=health_mode, exit_on_finish=False,
                             emit=print)
    return rc, ran, dict(R.RESULTS), buf.getvalue(), health_calls


def _verdict(rec):
    return rec.split(":", 1)[0].split("(")[0]


# ── arm 1: RIG ───────────────────────────────────────────────────────────────

def arm_rig():
    print("\n── EC-G8 arm RIG — zero results printed at all; exit 3 ──")
    import suite.serialdbg.runner as runner
    R.reset()
    R.pass_("F1", "a result that exists before the abort")
    buf = io.StringIO()
    code = None
    with contextlib.redirect_stdout(buf):
        try:
            runner._setup_fail("device-vanished", "stub")
        except SystemExit as e:
            code = e.code
    out = buf.getvalue()
    check(code == 3, f"exit 3 (got {code})")
    check("── Results ──" not in out,
          "no results block is printed — a RIG abort has no results to report")
    check("F1: PASS" not in out,
          "not even an already-recorded result leaks into a RIG abort")
    check("RIG condition" in out, "the sentence is selected by cls, not typed")


# ── arm 2: HEALTH ────────────────────────────────────────────────────────────

def arm_health():
    print("\n── EC-G8 arm HEALTH — everything NOT-RUN; zero other verdicts; exit 4 ──")
    rc, ran, res, out, _ = _run(health_failed=("H1",))
    check(rc == 4, f"exit 4, NOT 1 and NOT 0 (got {rc})")
    check(ran == [], f"no CORE/APP/FEATURE test was dispatched at all (ran={ran})")
    blocked = {t: res.get(t, "<missing>") for t in SELECTED}
    check(all(v.startswith("NOT-RUN: blocked-by=HEALTH/H1")
              for v in blocked.values()),
          f"every id is NOT-RUN(blocked-by=HEALTH/H1): {blocked}")
    # THE assertion — absence of any other verdict, not presence of NOT-RUN.
    others = {t: v for t, v in blocked.items()
              if _verdict(v) in ("PASS", "FAIL", "SKIP", "FLAKY-PASS")}
    check(not others, f"ZERO PASS/FAIL/SKIP/FLAKY-PASS among the blocked: {others}")
    check("[HEALTH-FAIL] H1" in out, "the summary names the failing health id")
    check(res.get("H1", "").startswith("FAIL"),
          "the FAILING health check keeps its RESULTS row, so the gate parsers "
          "and any archived log carry the reason (§4.5)")
    # run/player-gate's parser is a line-oriented sed; the row must match it.
    row = [ln for ln in out.splitlines() if ln.startswith("  F1: ")]
    check(row and row[0] == "  F1: NOT-RUN: blocked-by=HEALTH/H1",
          f"the printed row is exactly what player-gate's sed matches: {row}")


def arm_health_passes_no_row():
    print("\n── HEALTH passes: a premise, not a result (§4.5) ──")
    rc, ran, res, out, calls = _run()
    check(calls == [["H1"]], f"the gate phase ran the health class once: {calls}")
    check("H1" not in res,
          "a PASSING health check contributes NO RESULTS row — otherwise every "
          "run's pass count inflates and §4 rule 7's bookkeeping stops adding up")
    check(rc == 0 and sorted(ran) == sorted(SELECTED),
          f"and the suite then runs normally (rc={rc}, ran={ran})")


# ── arm 3: CORE ──────────────────────────────────────────────────────────────

def arm_core():
    print("\n── EC-G8 arm CORE — failing id is FAIL, APP/FEATURE NOT-RUN, exit 1 ──")
    rc, ran, res, out, _ = _run(failing=("C1",))
    check(rc == 1, f"exit 1 — a CORE failure IS a statement about the firmware "
                   f"(got {rc})")
    check(res["C1"].startswith("FAIL"), "the failing CORE id is a genuine FAIL")
    check("C2" in ran and res["C2"] == "PASS",
          "the OTHER CORE id still runs — a CORE failure does not invalidate "
          "its own class")
    for tid in ("A1", "F1", "F2"):
        check(res.get(tid, "").startswith("NOT-RUN: blocked-by=CORE/C1"),
              f"{tid} is NOT-RUN(blocked-by=CORE/C1): {res.get(tid)!r}")
        check(tid not in ran, f"{tid} was never dispatched")
    check(_verdict(res["A1"]) == "NOT-RUN" and _verdict(res["F1"]) == "NOT-RUN",
          "and they carry no other verdict")


# ── arm 4: APP — this arm asserts a DROP ─────────────────────────────────────

def arm_app():
    print("\n── EC-G8 arm APP — FEATURE runs normally; rule 5 stays DROPPED ──")
    rc, ran, res, out, _ = _run(failing=("A1",))
    check(rc == 1, f"exit 1 (got {rc})")
    check(res["A1"].startswith("FAIL"), "the failing APP id is a genuine FAIL")
    for tid in ("F1", "F2"):
        check(res.get(tid) == "PASS" and tid in ran,
              f"{tid} RAN and produced a real verdict — per-app FEATURE blocking "
              f"was dropped (§4.2/§15) and must not creep back")
    check(not any(v.startswith("NOT-RUN") for v in res.values()),
          "nothing at all is NOT-RUN on an APP failure")


# ── the inert arm — the state this task actually ships in ────────────────────

def arm_inert():
    print("\n── INERT (--class-order off, the shipped default) — nothing changes ──")
    rc, ran, res, out, calls = _run(class_order=False)
    check(ran == SELECTED, f"registry order is preserved exactly: {ran}")
    check(calls == [], "the HEALTH gate phase does not run at all")
    check(rc == 0, f"exit 0 (got {rc})")
    rc, ran, res, _, _ = _run(failing=("C1",), class_order=False)
    check(rc == 1 and ran == SELECTED,
          f"a CORE failure blocks NOTHING and exits 1 (rc={rc}, ran={ran})")
    check(not any(v.startswith("NOT-RUN") for v in res.values()),
          "no NOT-RUN row is ever produced with the switch off")


def arm_ordering():
    print("\n── class_order() — ascending, and STABLE inside a class (§4 rule 1) ──")
    got = _order.class_order(SELECTED, META)
    check(got == ["C1", "C2", "A1", "F1", "F2"],
          f"classes ascending, today's relative order kept within each: {got}")
    check(_order.class_order(["F1", "X9"], {"F1": {"cls": "FEATURE"}}) ==
          ["F1", "X9"],
          "an id with no record sorts with FEATURE — as unblocking as an "
          "undeclared one")
    before, after = ["a", "b", "c"], ["c", "a", "b"]
    check(_order.inverted_pairs(before, after) == [("a", "c"), ("b", "c")],
          "inverted_pairs enumerates exactly the flipped pairs")


def arm_health_downgrades():
    print("\n── DUT_HEALTH=warn|skip — the suite runs, the premise is stamped ──")
    rc, ran, res, out, calls = _run(health_failed=("H1",), health_mode="warn")
    check(sorted(ran) == sorted(SELECTED),
          "warn: the suite runs anyway")
    check(_gate.NOT_ESTABLISHED in out,
          "warn: the summary is stamped 'health not established', so a "
          "downgraded gate can never be silently absent from a quoted result")
    rc, ran, res, out, calls = _run(health_failed=("H1",), health_mode="skip")
    check(calls == [], "skip: the checks do not run")
    check(_gate.NOT_ESTABLISHED in out, "skip: the summary is stamped too")


def arm_adjudication():
    print("\n── @VE §18.6(c) — the 0->1-edge enumeration is a PRECONDITION ──")
    import suite.serialdbg as _suite
    tests = _suite.build_all_tests()
    missing = _order.unadjudicated(tests)
    check(not missing,
          f"every 0->1-edge candidate the scanner finds is adjudicated in "
          f"_order.EDGE_ADJUDICATION (unadjudicated: {missing})")
    bad = {t: v for t, (v, _w) in _order.EDGE_ADJUDICATION.items()
           if v not in _order.EDGE_VERDICTS}
    check(not bad, f"every verdict is in the closed vocabulary: {bad}")
    cand = _order.edge_candidates(tests)
    check("T_PMT_04" in cand,
          "the TASK-553 reference case is still detected — if this ever goes "
          "quiet the scanner has stopped working, not the suite")


def main():
    print("── test_class_order.py — EC-G8 inversion test (TASK-566) ──")
    arm_rig()
    arm_health()
    arm_health_passes_no_row()
    arm_core()
    arm_app()
    arm_inert()
    arm_ordering()
    arm_health_downgrades()
    arm_adjudication()
    R.reset()
    print("")
    if FAILURES:
        print(f"test_class_order.py: {len(FAILURES)} FAILED")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("test_class_order.py: all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
