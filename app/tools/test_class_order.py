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

TASK-624 EXTENDS THE TABLE WITH `UNMET` (ADR-066 D5 / IFC-008 I3+I4, R38):

    | stubbed UNMET   | assertion                                              |
    | HEALTH          | exit 4 BY PRECEDENCE (D4 rule 1), everything NOT-RUN   |
    | CORE            | exit 1; APP/FEATURE NOT-RUN; zero other verdicts       |
    | FEATURE (alone) | exit 1 anyway (D4 rule 2) — nothing to blame, still    |
    |                 | blocks; NOT exit 4; visible in its own summary block   |

plus two arms on the vocabulary itself: that UNMET and NOT-RUN cannot collapse
into synonyms, and THE MUTATION PROOF — the string predicate this row replaces
is demonstrably False on a verdict that must block.

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


def _dispatch_factory(failing=(), unmet=()):
    ran = []

    def dispatch(tid):
        ran.append(tid)
        if tid in failing:
            R.fail(tid, "stubbed failure")
        elif tid in unmet:
            R.unmet(tid, "stubbed unestablished premise")
        else:
            R.pass_(tid)
    return dispatch, ran


def _run(failing=(), health_failed=(), class_order=True, health_phase=None,
         health_mode="gate", unmet=(), health_unmet=(), health_skip=()):
    """TASK-597: `health_phase` is independent of `class_order` — same as
    runner.py's `_health_on` vs `_gate_on`. Defaulting it to `class_order`
    when unset reproduces every pre-TASK-597 call site's behaviour exactly
    (health ran iff class_order did); pass it explicitly to exercise the new
    property (health_phase=True, class_order=False)."""
    if health_phase is None:
        health_phase = class_order
    R.reset()
    dispatch, ran = _dispatch_factory(failing, unmet)
    health_calls = []

    def run_health(ids):
        health_calls.append(list(ids))
        for tid in ids:
            if tid in health_failed:
                R.fail(tid, "stubbed health failure")
            elif tid in health_unmet:
                R.unmet(tid, "stubbed unestablished health premise")
            elif tid in health_skip:
                R.skip(tid, "stubbed configuration skip")
            else:
                R.pass_(tid)
        # DELIBERATELY the production predicate, not `t in health_failed`:
        # health.py:run_health() decides with `verdict_of(t) in BLOCKING`, and
        # an arm that reimplemented the decision would assert nothing about it.
        return [t for t in ids if R.verdict_of(t) in R.BLOCKING]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _gate.run_suite(SELECTED, META, dispatch, class_order=class_order,
                             health_ids=["H1"] if health_phase else (),
                             run_health=run_health if health_phase else None,
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


def arm_health_skip_is_not_pass():
    """C-4 / TASK-588. A SKIPped HEALTH id is neither FAIL nor UNMET, so it is
    not in `run_health`'s returned `failed` list and does not block — that part
    is unchanged and correct (R28: a SKIP is green). What was wrong is the
    banner: `health_phase` used to print the literal `[health] PASS — ... knows
    which network it is on ...` sentence unconditionally in this branch, even
    though `_triage.health_verdict` calls the identical run `degraded(H1)`. The
    fix makes the banner ask `health_verdict` first."""
    print("\n── C-4 arm — a SKIPped HEALTH id must not be announced as PASS ──")
    rc, ran, res, out, calls = _run(health_skip=("H1",))
    check(rc == 0 and sorted(ran) == sorted(SELECTED),
          f"a SKIP still gates nothing — the suite runs normally (rc={rc}, ran={ran})")
    check(res.get("H1", "").startswith("SKIP"),
          f"the SKIPped health id keeps its RESULTS row — popping it would hide "
          f"the very thing the banner must now name: {res.get('H1')!r}")
    check("[health] PASS — the board answers correct data, knows which "
          "network it is on, and can switch apps." not in out,
          "the old literal PASS sentence must NOT appear — T_DH_02's network "
          "claim did not run, so nothing may assert it")
    check("degraded(H1)" in out,
          f"the banner must be built from the same verdict `_triage.health_verdict` "
          f"reports for this run (`degraded(H1)`), not a hardcoded literal: {out!r}")


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


def arm_health_id_selection():
    """TASK-597 / EXP-040 — `--health-ids`' selection logic, pure.

    Pins what CAN be pinned host-side. What cannot: that runner.py hands the
    SELECTED set to the gate rather than the full registry. The first cut of
    this change filtered `health_selected` and then passed `health_tests` to
    `run_suite`, so the flag parsed, every host check passed, the selftest
    grepped the command line and agreed — and the gate ran all four ids. Only
    reading a real run's `── HEALTH class ──` line caught it. A replay-driven
    test over runner.main() (TASK-628's engine) is the instrument that would;
    it does not exist yet, and this docstring is the honest marker for that.
    """
    from suite.serialdbg.runner import select_health_ids as sel
    print("\n── TASK-597 — --health-ids narrows the HEALTH class, or refuses ──")
    H = ["T_DH_01", "T_DH_02", "T_DH_05", "T_DH_03"]
    check(sel(H, None) == H, "no spec means the whole class, unreordered")
    check(sel(H, "T_DH_01,T_DH_03") == ["T_DH_01", "T_DH_03"], "a subset is the subset")
    # The class's own ordering constraint outranks the caller's spelling:
    # ADR-064 D4 puts T_DH_05 before the mutating T_DH_03, so selection must
    # never be an opportunity to reorder the class.
    check(sel(H, "T_DH_03,T_DH_01") == ["T_DH_01", "T_DH_03"],
          "spec order does not reorder the class")
    check(sel(H, " T_DH_01 , T_DH_03 ") == ["T_DH_01", "T_DH_03"], "whitespace tolerated")
    try:
        sel(H, "T_DH_99")
        check(False, "an unknown id must refuse, not narrow silently")
    except SystemExit as e:
        check("T_DH_99" in str(e), f"the refusal names the id: {e}")


def arm_health_subset_still_blocks():
    """TASK-597 / EXP-040 — a NARROWED health phase is still a gate.

    run/player-gate asks for T_DH_01,T_DH_03 and deliberately not T_DH_02/05.
    The risk that buys is obvious once stated: a subset is a smaller premise,
    and a smaller premise that also stopped BLOCKING would be worse than the
    decorative gate E-13 found — it would look checked and gate nothing.

    So this drives the gate with a single-member health set and asserts the
    full blocking contract still holds: exit 4, nothing dispatched, every id
    NOT-RUN and attributed to the health id that failed. BP-068: a gate never
    observed to fail is not a gate, and this one was decorative for its whole
    life before TASK-597.
    """
    print("\n── TASK-597 — a SUBSET health phase still blocks and still exits 4 ──")
    rc, ran, res, out, calls = _run(health_failed=("H1",), class_order=False,
                                     health_phase=True)
    check(rc == 4, f"a one-id health set still exits 4 (got {rc})")
    check(ran == [], f"nothing was dispatched behind a failed subset: {ran}")
    check(all(res.get(t, "").startswith("NOT-RUN: blocked-by=HEALTH/H1")
              for t in SELECTED),
          f"every id is attributed to the subset member that failed: {res}")
    check("[HEALTH-FAIL]" in out, "the operator is told, not only the artifact")


def arm_health_phase_without_class_order():
    """TASK-597 — E-13: the HEALTH gate must be reachable WITHOUT adopting
    class ordering (TASK-617 RULED 2026-09-03 holds --class-order OFF). This
    is the property runner.py's `--health-phase` flag exists to deliver:
    `class_order=False` (registry order, no CORE blocking — TASK-566 stays
    inert) while the HEALTH gate itself still runs, blocks and exits 4."""
    print("\n── TASK-597 — --health-phase runs HEALTH WITHOUT class ordering ──")
    rc, ran, res, out, calls = _run(health_failed=("H1",), class_order=False,
                                     health_phase=True)
    check(rc == 4, f"exit 4 with class_order=False (got {rc})")
    check(ran == [], f"no CORE/APP/FEATURE id was dispatched (ran={ran})")
    check(calls == [["H1"]], f"the health gate ran exactly once: {calls}")
    blocked = {t: res.get(t, "<missing>") for t in SELECTED}
    check(all(v.startswith("NOT-RUN: blocked-by=HEALTH/H1")
              for v in blocked.values()),
          f"every id is NOT-RUN(blocked-by=HEALTH/H1) with class ordering OFF: "
          f"{blocked}")

    # A PASSING health gate with class_order=False: the suite runs, but in
    # REGISTRY order — the reordering stays gated on --class-order alone, not
    # on the health phase running.
    rc, ran, res, out, calls = _run(class_order=False, health_phase=True)
    check(rc == 0 and ran == SELECTED,
          f"health passes; suite runs in REGISTRY order, unreordered: ran={ran}")
    check("[order] class-ordered" not in out,
          "--health-phase alone must not turn on --class-order's reordering")

    # A CORE failure with class_order=False + health_phase=True must NOT block
    # APP/FEATURE — that blocking is still --class-order's (TASK-566, still
    # held OFF); only the HEALTH gate itself becomes real.
    rc, ran, res, out, calls = _run(failing=("C1",), class_order=False,
                                     health_phase=True)
    check(rc == 1 and sorted(ran) == sorted(SELECTED),
          f"a CORE failure blocks nothing with class_order=False "
          f"(rc={rc}, ran={ran})")
    check(not any(v.startswith("NOT-RUN") for v in res.values()),
          "no NOT-RUN row — CORE blocking is still class_order's, not "
          "health_phase's")


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


# ── TASK-624 arms: the typed verdict, and `UNMET` ────────────────────────────
#
# ADR-066 D5 / IFC-008 I3+I4, and R38's own verification clause: "the inversion
# selftest's `UNMET` arm asserts the ABSENCE of any other verdict among the
# blocked ids, not merely the presence of `NOT-RUN` — a weaker form passes a
# runner that emits both."
#
# WHY THESE ARMS EXIST AT ALL. WP-C found `T-BUSY-05` passing on exactly the
# regression it existed to catch, and TASK-573 was a gate printing REGRESS on a
# token that had shipped for years. A change to gating without a test that
# proves the gate BLOCKS repeats that class of defect one level up (BP-068).

_OTHER_VERDICTS = (R.Verdict.PASS, R.Verdict.FAIL, R.Verdict.SKIP,
                   R.Verdict.FLAKY_PASS, R.Verdict.UNMET)


def arm_unmet_core():
    print("\n── TASK-624 arm CORE/UNMET — an unmet CORE premise BLOCKS (R38) ──")
    rc, ran, res, out, _ = _run(unmet=("C1",))
    check(rc == 1, f"exit 1 — UNMET blocks and owns no code of its own "
                   f"(ADR-066 D4); NOT 0 and NOT 4 (got {rc})")
    check(R.verdict_of("C1") is R.Verdict.UNMET,
          f"the CORE id's verdict is UNMET, not SKIP: {res.get('C1')!r}")
    check("C2" in ran and R.verdict_of("C2") is R.Verdict.PASS,
          "the OTHER CORE id still runs — an unmet premise does not invalidate "
          "its own class, exactly as a CORE FAIL does not")
    for tid in ("A1", "F1", "F2"):
        check(res.get(tid, "") == "NOT-RUN: blocked-by=CORE/C1",
              f"{tid} is NOT-RUN(blocked-by=CORE/C1): {res.get(tid)!r}")
        check(tid not in ran, f"{tid} was never dispatched")
    # THE assertion — absence, not presence (R38's verification clause).
    others = {t: R.verdict_of(t) for t in ("A1", "F1", "F2")
              if R.verdict_of(t) in _OTHER_VERDICTS}
    check(not others,
          f"ZERO PASS/FAIL/SKIP/FLAKY-PASS/UNMET among the blocked ids: {others}")


def arm_unmet_health():
    print("\n── TASK-624 arm HEALTH/UNMET — exit 4 by PRECEDENCE, not by UNMET ──")
    rc, ran, res, out, _ = _run(health_unmet=("H1",))
    check(rc == 4,
          f"exit 4 — ADR-066 D4 rule 1: the unmet premise IS attributable to a "
          f"class failure that fired, so the existing precedence sets the code "
          f"and UNMET changes nothing (got {rc})")
    check(ran == [], f"no CORE/APP/FEATURE id was dispatched at all (ran={ran})")
    check(all(res.get(t, "") == "NOT-RUN: blocked-by=HEALTH/H1" for t in SELECTED),
          f"every id is NOT-RUN(blocked-by=HEALTH/H1)")
    others = {t: R.verdict_of(t) for t in SELECTED
              if R.verdict_of(t) in _OTHER_VERDICTS}
    check(not others, f"and ZERO other verdicts among them: {others}")
    check("[HEALTH-FAIL] H1" in out,
          "the summary names the failing health id — an UNMET health check has "
          "NOT certified the board (`C-4`)")


def arm_health_run_health_is_typed():
    print("\n── TASK-624 — health.run_health()'s OWN predicate, not the stub's ──")
    # arm_unmet_health above drives _gate through an INJECTED run_health. That
    # proves the gate, not the production decision, so this arm calls the real
    # `health.run_health()` with its registry stubbed. Without it, health.py
    # could quietly go back to `startswith("FAIL")` with every other arm green.
    import suite.serialdbg.health as health
    saved = dict(health.HEALTH_TESTS)
    try:
        health.HEALTH_TESTS.clear()
        health.HEALTH_TESTS["T_DH_01"] = lambda dut: R.pass_("T_DH_01")
        health.HEALTH_TESTS["T_DH_02"] = lambda dut: R.unmet(
            "T_DH_02", "`get wifiCfg` never answered, so nothing was compared")
        R.reset()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            failed = health.run_health(None, ["T_DH_01", "T_DH_02"])
        check(failed == ["T_DH_02"],
              f"an UNMET health check is REPORTED FAILING by run_health() — a "
              f"health check whose own premise did not hold has not certified "
              f"the board (`C-4`, R38). Got {failed}")
        check(R.verdict_of("T_DH_01") is R.Verdict.PASS,
              "and the passing one is untouched")
    finally:
        health.HEALTH_TESTS.clear()
        health.HEALTH_TESTS.update(saved)
        R.reset()


def arm_unmet_alone():
    print("\n── TASK-624 arm UNMET ALONE — nothing to blame, and it still exits 1 ──")
    rc, ran, res, out, _ = _run(unmet=("F1",))
    check(rc == 1,
          f"exit 1 — ADR-066 D4 rule 2: a premise that failed on its own, with "
          f"no class failure to attribute it to, still blocks (got {rc})")
    check(sorted(ran) == sorted(SELECTED),
          "a FEATURE UNMET blocks nothing — FEATURE is not a gating class")
    check("F1" not in R.BLOCKED_BY,
          "and it carries NO attribution: that is the whole difference from "
          "NOT-RUN (IFC-008 I3)")
    check("── UNMET (1)" in out and "premise was never established" in out,
          "R38: it is VISIBLE in the summary, in its own block, not folded "
          "into NOT-RUN")
    check("1 unmet (premise not established)" in out,
          "and it is counted on the one-line summary")
    # `E-14`: the declared-flake block repeats rows in the `  <id>: <STATUS>`
    # shape and run/player-gate's sed parses those ids TWICE. The UNMET block
    # must not add a second instance of that finding.
    parseable = [ln for ln in out.splitlines()
                 if ln.startswith("  F1: UNMET")]
    check(len(parseable) == 1,
          f"exactly ONE line in the whole summary matches player-gate's "
          f"`^  <id>: <STATUS>` sed — the UNMET block must not re-emit a "
          f"parseable row (`E-14`): {parseable}")
    # exit 4 is explicitly wrong here — ADR-066 D4's third bullet.
    check(rc != 4, "NOT exit 4: four PASSes in this run are trustworthy, and 4 "
                   "tells every consumer to discard all of them")
    # And the same in the INERT default, because this one is a results-layer
    # property: TASK-584's residue callers are not under the order switch.
    rc2, _, _, _, _ = _run(unmet=("F1",), class_order=False)
    check(rc2 == 1, f"and exit 1 with the order switch OFF too (got {rc2})")


def arm_unmet_is_not_not_run():
    print("\n── TASK-624 — UNMET and NOT-RUN cannot collapse into synonyms (I3) ──")
    R.reset()
    # 1. NOT-RUN ALWAYS carries an attribution — an unattributed one is refused.
    for bad in ("", None, "HEALTH"):
        try:
            R.not_run("X1", bad)
            check(False, f"not_run(tid, {bad!r}) was ACCEPTED — an unattributed "
                         f"NOT-RUN is an UNMET wearing the wrong name")
        except ValueError:
            check(True, f"not_run(tid, {bad!r}) is refused: NOT-RUN always names "
                        f"the class failure that blocked it")
    # 2. UNMET may NEVER carry one.
    try:
        R.unmet("X2", "blocked-by=CORE/C1")
        check(False, "unmet() ACCEPTED an attribution — that is exactly how "
                     "UNMET becomes a second spelling of NOT-RUN")
    except ValueError:
        check(True, "unmet() refuses an attribution (ADR-066 D2)")
    # 3. The biconditional, on real records.
    R.reset()
    R.not_run("N1", "CORE/C1")
    R.unmet("U1", "the app never reached READY")
    check(R.BLOCKED_BY == {"N1": "CORE/C1"},
          f"BLOCKED_BY holds the NOT-RUN row and ONLY it: {R.BLOCKED_BY}")
    check(R.verdict_of("N1") is R.Verdict.NOT_RUN
          and R.verdict_of("U1") is R.Verdict.UNMET,
          "and the two verdicts are distinct enum members")
    check(R.check_verdict_invariants() == [],
          "a well-formed pair violates nothing")
    # 4. The checker has teeth: forge the collapse and it must be caught.
    R.BLOCKED_BY["U1"] = "CORE/C1"
    bad = R.check_verdict_invariants()
    check(any("only NOT-RUN may" in v for v in bad),
          f"an UNMET that acquired an attribution IS caught: {bad}")
    R.BLOCKED_BY.pop("U1")
    R.BLOCKED_BY.pop("N1")
    bad = R.check_verdict_invariants()
    check(any("NOT-RUN with no blocked_by" in v for v in bad),
          f"and a NOT-RUN that lost its attribution is caught too: {bad}")
    R.reset()


def arm_typed_not_prefix():
    print("\n── TASK-624 — THE MUTATION PROOF: the string predicate misses UNMET ──")
    R.reset()
    R.unmet("U1", "the app never reached READY")
    record = R.RESULTS["U1"]
    # The line _gate.py:129 used to be. This is the defect, demonstrated: it is
    # False on a verdict that MUST block, which is why 31 CORE ids gated nothing.
    legacy = record.startswith("FAIL")
    typed = R.verdict_of("U1") in R.BLOCKING
    check(legacy is False,
          f"the LEGACY predicate `record.startswith('FAIL')` is False on "
          f"{record!r} — restore that line and the gate stops blocking")
    check(typed is True,
          "the TYPED predicate `verdict_of(tid) in BLOCKING` is True — the "
          "gate blocks (R31/R38)")
    # And a SKIP, which is what these ids record TODAY, is green under both:
    # the fix is the vocabulary, not only the predicate.
    R.reset()
    R.skip("S1", "same precondition, spelled the old way")
    check(R.RESULTS["S1"].startswith("FAIL") is False
          and (R.verdict_of("S1") in R.BLOCKING) is False,
          "a SKIP still gates nothing under EITHER predicate — R28's point: "
          "the vocabulary had to gain UNMET, a typed gate alone was not enough")
    # The enum cannot be prefix-tested by accident.
    check(R.Verdict.FAIL != "FAIL" and not hasattr(R.Verdict.FAIL, "startswith"),
          "Verdict is a plain Enum, not a str subclass: `== \"FAIL\"` is False "
          "and `.startswith` does not exist, so IFC-008 I1's shape cannot be "
          "written against it by accident")
    # I2 with teeth: a record this layer did not write is REFUSED, not defaulted.
    try:
        R.RESULTS["Z1"] = "PROBABLY-FINE: whatever"
        check(False, "an unknown record string was ACCEPTED — pre-TASK-624 that "
                     "was silently neither-failed-nor-anything, i.e. green")
    except R.UnknownVerdict:
        check(True, "an unknown record string is refused (IFC-008 I2)")
    R.reset()


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
    arm_health_skip_is_not_pass()
    arm_core()
    arm_app()
    arm_inert()
    arm_health_phase_without_class_order()
    arm_health_subset_still_blocks()
    arm_health_id_selection()
    arm_ordering()
    arm_health_downgrades()
    arm_unmet_core()
    arm_unmet_health()
    arm_health_run_health_is_typed()
    arm_unmet_alone()
    arm_unmet_is_not_not_run()
    arm_typed_not_prefix()
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
