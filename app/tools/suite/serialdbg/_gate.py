"""suite/serialdbg/_gate.py — the class-ordered dispatch loop. TASK-566.

M-TESTARCH §4's gating semantics, in one function, with the DUT injected.

  RIG    -> `_setup_fail()` in runner.py: exit 3, zero results printed.
  HEALTH -> exit 4, every other id NOT-RUN(blocked-by=HEALTH/<id>), zero FAILs.
  CORE   -> the failing id is a real FAIL and exit is 1; every APP/FEATURE id is
            NOT-RUN(blocked-by=CORE/<id>). "Failing" is `lib.results.BLOCKING`
            = {FAIL, UNMET}, matched as an ENUM MEMBER, never a string prefix
            (TASK-624, ADR-066 D5 / IFC-008 I1, R31/R38).
  APP    -> FAIL. Blocks NOTHING — rule 5 was DROPPED (§4.2/§15) because the
            registry cannot express per-app blocking and blocking ALL FEATURE
            on one app's failure bought little.
  FEATURE-> FAIL. Blocks nothing.

WHY THE DUT IS INJECTED. EC-G8 — the inversion test — is the machine form of
this document's whole thesis, and it is host-only by requirement: "stub a
class-N failure and assert that no id of class N+1 carries any verdict other
than NOT-RUN". That is only possible if the loop that implements the property
can run without a board. `dispatch` and `run_health` are callables; nothing in
here imports serial or touches a port.

THE ORDER SWITCH IS OFF BY DEFAULT AND THAT IS DELIBERATE (@PM ruling on the
TASK-566 row; @VE §18.6). `class_order=False` reproduces today's behaviour
exactly — registry order, no health phase, no blocking, exit 0/1 — so this file
LANDS the machinery without changing a single run. Flipping it is a separate,
gated decision that needs an interleaved A/B at one commit, the undeclared
flake candidates adjudicated before run 1, and the 0->1-edge enumeration in
hand. TASK-557 (the rig's supply sag) is unresolved and non-stationary, and a
reordered suite changes what 557 is measuring (design §7).
"""

from __future__ import annotations

from lib.results import (BLOCKING, RESULTS, Verdict, not_run, print_results,
                         verdict_of)

from suite.serialdbg import _order

#: `DUT_HEALTH` (design §6 R1/R2, same shape as `DUT_BOOT_GATE`).
#:   gate  the default: a health failure blocks the run and exits 4
#:   warn  run the checks, print the failure, RUN THE SUITE ANYWAY
#:   skip  do not run the checks at all
#: Both downgrades stamp the summary with `health not established`, so a
#: downgraded gate can never be silently absent from a result someone later
#: quotes — and `run/player-gate` refuses to emit a verdict at all under either
#: (@VE ruling §18.2: a gate run whose health premise was downgraded is not a
#: gate run).
HEALTH_MODES = ("gate", "warn", "skip")

NOT_ESTABLISHED = "health not established"


def health_phase(health_ids, run_health, mode="gate", emit=print):
    """Run the HEALTH class. -> (failed_ids, blocking) where `blocking` says
    whether the caller must stop.

    Never via `run_with_flake_retry` (§4.4): retrying a health check doubles its
    cost, re-runs the one mutating check, and produces a FLAKY-PASS with no
    defined meaning for a binary "is this board a valid subject".
    """
    if mode == "skip":
        emit(f"[health] SKIPPED by DUT_HEALTH=skip — {NOT_ESTABLISHED}. "
             f"No claim in this run's summary rests on a checked board.")
        return ([], False)
    emit(f"\n── HEALTH class ── {list(health_ids)}")
    ids = list(health_ids)
    failed = run_health(ids)
    if not failed:
        # §4.5: a PASSING health gate contributes NO RESULTS row — it is reported
        # in the `[health]` premise line instead. Otherwise every run's pass count
        # inflates by three and §4 rule 7's NOT-RUN bookkeeping stops adding up.
        # A FAILING one keeps its row, so the gate parsers and any archived log
        # carry the reason.
        for tid in ids:
            if verdict_of(tid) is Verdict.PASS:
                RESULTS.pop(tid)
        emit("[health] PASS — the board answers correct data, knows which "
             "network it is on, and can switch apps. It is fit to test. "
             "(No RESULTS row: a passing gate is a premise, not a result.)")
        return ([], False)
    emit(f"\n[HEALTH-FAIL] {','.join(failed)} — this board is NOT a valid test "
         f"subject right now. Every result a suite produced against it would be "
         f"uninterpretable.")
    if mode == "warn":
        emit(f"[health] DOWNGRADED by DUT_HEALTH=warn — {NOT_ESTABLISHED}. "
             f"The suite runs anyway; nothing it reports is a premise-checked "
             f"result.")
        return (failed, False)
    return (failed, True)


def run_suite(selected, meta, dispatch, *, class_order=False, health_ids=(),
              run_health=None, health_mode="gate", emit=print,
              before_summary=None, exit_on_finish=True) -> int:
    """Dispatch `selected` and print the summary. Returns the exit code.

    With `class_order=False` this is today's loop, unchanged and unreordered:
    the health phase does not run, nothing is blocked, and the exit code is
    print_results()'s own 0/1.
    """
    selected = list(selected)
    health_failed = []

    if class_order:
        if health_ids and run_health is not None:
            health_failed, blocking = health_phase(health_ids, run_health,
                                                   health_mode, emit)
            if blocking:
                # §4 rule 3: every CORE/APP/FEATURE id is NOT-RUN. Recording it
                # per id rather than printing one banner is the point — the gate
                # parsers read RESULTS rows, and a cell with no row at all scores
                # MISSING, which reads as a regression (TASK-573's defect exactly).
                for tid in selected:
                    not_run(tid, f"HEALTH/{health_failed[0]}")
                return print_results(exit_on_finish=exit_on_finish,
                                     health_fail=health_failed[0])
        order = _order.class_order(selected, meta)
        if order != selected:
            emit(f"[order] class-ordered: {len(_order.moves(selected, order))} "
                 f"of {len(selected)} ids change position")
        selected = order

    blocked_by = None
    for tid in selected:
        cls = (meta.get(tid) or {}).get("cls", "FEATURE")
        if blocked_by and cls in _order.CORE_BLOCKS:
            not_run(tid, blocked_by)
            continue
        dispatch(tid)
        verdict = verdict_of(tid)
        if class_order and cls == "CORE" and verdict in BLOCKING:
            # TYPED (R31 / IFC-008 I1). This line used to read
            # `RESULTS.get(tid, "").startswith("FAIL")`, and R28's measurement
            # is that the class hierarchy's central promise was delivered by a
            # string-prefix test the COMMON failure mode does not match: 31 of
            # the 43 CORE ids exit through a `skip()` for a CORE precondition
            # that did not hold, and a SKIP is green, so those 31 gated nothing
            # (WP-C `C-5`). `BLOCKING` is {FAIL, UNMET} — R38: an unmet premise
            # in a gating class blocks the classes above it exactly as a FAIL
            # does. Exit stays 1 either way; exit 4 remains reserved for "no
            # result in this run is trustworthy" (§4 rule 4).
            blocked_by = f"CORE/{tid}"
            emit(f"[order] CORE {tid} {verdict} — every remaining APP/FEATURE "
                 f"id is NOT-RUN({blocked_by}). CORE ids continue: a CORE "
                 f"failure does not invalidate its own class.")

    if before_summary is not None:
        # The caller's own end-of-run probes (the TASK-407 exit playerMode
        # snapshot) belong BEFORE the summary: run/player-gate greps the
        # "── Results ──" block, and anything printed after it is noise a reader
        # has to scroll past to find the verdict.
        before_summary()

    # print_results(None) prints every RESULTS row in insertion order, which under
    # the switch IS execution order. Deliberately not `print_results(selected)`:
    # that filters the printed rows to the selection and would silently drop any
    # row a test recorded under another id — and a missing row scores MISSING in
    # run/player-gate, i.e. reads as a regression (TASK-573's defect exactly).
    rc = print_results(exit_on_finish=False)
    if health_failed and health_mode == "warn":
        emit(f"\n[health] {NOT_ESTABLISHED} (DUT_HEALTH=warn, failed: "
             f"{','.join(health_failed)}) — read every line above with that in "
             f"mind.")
    if health_mode == "skip":
        emit(f"\n[health] {NOT_ESTABLISHED} (DUT_HEALTH=skip).")
    if exit_on_finish:
        raise SystemExit(rc)
    return rc
