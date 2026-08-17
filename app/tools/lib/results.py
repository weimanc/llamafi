#!/usr/bin/env python3
"""lib/results.py — the ONE result-recording layer for every VE suite (TASK-520).

ve_suite_base.py and run_serialdbg_tests.py each carried their own byte-identical
copies of RESULTS / pass_ / fail / skip / flake and their own summary block. That
duplication is exactly why the flaky policy had nowhere to live: implementing it
twice guarantees the two halves drift, and the runner's copy is the one that
actually runs the 130-test suite. Both modules now re-export from here (same
pattern, same reason, as lib/dut.py in M-TESTBASE P1), so RESULTS is a single
shared dict and the policy is enforced once.

THE FLAKY POLICY (flaky.yaml header, M-TESTARCH §7, ADR-059 D13):

  1. flake(tid) for an id NOT declared in docs/verification/flaky.yaml records a
     FAIL, naming the missing declaration. Same for an id whose review_by has
     passed, and same if flaky.yaml itself cannot be read (fail closed).
  2. A declared flake is retried ONCE and BOTH outcomes are reported. The retry
     is driven by the dispatch loop (run_with_flake_retry) because flake() is
     called from inside the test body and cannot re-invoke it.
       attempt 2 PASS      -> FLAKY-PASS   (its own bucket; NOT a pass)
       attempt 2 flake/fail-> FAIL         (a flake that reproduces is a failure)
     A declared flake that is never retried — a suite with its own dispatch loop
     that does not call run_with_flake_retry — is also a FAIL. An unresolved
     flake must never be quieter than a resolved one.
  3. Enforced by lib/flaky.py's schema (owner + task + review_by all required).
  4. The summary counts FLAKY-PASS separately from passed/failed/skipped and
     prints both attempts, so a reader cannot mistake one for the other.

INTERPRETATION NOTES (things the policy text does not state, decided here):
  - "retried once" is one retry, not retry-until-green.
  - A reproduced flake exits non-zero. The policy fixes reporting, not the exit
    code; treating a twice-observed failure as green would defeat the point.
  - A test that calls fail() directly is a FAIL even if declared flaky. Declaring
    an id does not blanket-excuse it; only flake() consults the declaration.
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from . import flaky as _flaky

# ── result tracking ──────────────────────────────────────────────────────────

RESULTS: dict[str, str] = {}

# tid -> reason, set by flake() and consumed by run_with_flake_retry(). A tid
# left in here at summary time never got its mandated retry.
_PENDING_FLAKE: dict[str, str] = {}

_PENDING_PREFIX = "FLAKE(awaiting mandated retry)"


def reset() -> None:
    """Clear all recorded state (used by the policy's own tests)."""
    RESULTS.clear()
    _PENDING_FLAKE.clear()


def pass_(tid: str, detail: str = ""):
    RESULTS[tid] = "PASS"
    print(f"  [PASS] {tid}" + (f"  {detail}" if detail else ""))


def fail(tid: str, reason: str):
    RESULTS[tid] = f"FAIL: {reason}"
    print(f"  [FAIL] {tid}  {reason}")


def skip(tid: str, reason: str):
    RESULTS[tid] = f"SKIP: {reason}"
    print(f"  [SKIP] {tid}  {reason}")


def flake(tid: str, reason: str):
    """Claim `tid` flaked. Honoured only if flaky.yaml declares it, unexpired."""
    reg, err = _flaky.get_registry()
    if err is not None:
        fail(tid, f"flake() claimed but the declared flaky set is unreadable "
                  f"({err}) — failing closed. Original claim: {reason}")
        return
    state, entry = reg.status(tid)
    if state == _flaky.UNDECLARED:
        hint = ""
        if tid in reg.candidates:
            hint = (f" It is listed under `candidates:` ({reg.candidates[tid]}) — "
                    f"a candidate is not a declaration; measure it and promote it.")
        fail(tid, f"UNDECLARED flake — no entry for {tid} in {reg.path.name} "
                  f"(ADR-059 D13 / M-TESTARCH §7: declare BEFORE the run, with "
                  f"owner, task and review_by).{hint} Original claim: {reason}")
        return
    if state == _flaky.EXPIRED:
        fail(tid, f"EXPIRED flake declaration — review_by {entry.review_by} has passed "
                  f"(owner {entry.owner}, {entry.task}). Re-justify the entry or delete "
                  f"it; until then this is a FAIL. Original claim: {reason}")
        return
    _PENDING_FLAKE[tid] = reason
    RESULTS[tid] = f"{_PENDING_PREFIX}: {reason}"
    print(f"  [FLAKE] {tid}  declared ({entry.task}, review_by {entry.review_by})  {reason}")


# ── mandated single retry ────────────────────────────────────────────────────

def run_with_flake_retry(tid: str, run_once: Callable[[], None]) -> None:
    """Run a test body; if it recorded a DECLARED flake, run it once more.

    `run_once` must be self-contained, including its own exception handling —
    both dispatch loops already wrap the body in try/except and record fail().
    """
    run_once()
    reason1 = _PENDING_FLAKE.pop(tid, None)
    if reason1 is None:
        return

    print(f"  [RETRY] {tid}  declared flake — mandated retry (attempt 1: {reason1})")
    RESULTS.pop(tid, None)
    run_once()
    reason2 = _PENDING_FLAKE.pop(tid, None)
    r2 = RESULTS.get(tid, "")

    if reason2 is not None:
        RESULTS[tid] = (f"FAIL: declared flake REPRODUCED on retry — "
                        f"attempt1 FLAKE({reason1}) | attempt2 FLAKE({reason2})")
        print(f"  [FAIL] {tid}  declared flake reproduced on retry — not a flake, a failure")
    elif r2 == "PASS":
        RESULTS[tid] = f"FLAKY-PASS: attempt1 FLAKE({reason1}) | attempt2 PASS"
        print(f"  [FLAKY-PASS] {tid}  passed on retry — reported separately, NOT counted as PASS")
    elif r2.startswith("SKIP"):
        RESULTS[tid] = f"FAIL: attempt1 FLAKE({reason1}) | attempt2 {r2} (retry could not run)"
        print(f"  [FAIL] {tid}  retry SKIPped — a declared flake cannot be resolved by a skip")
    else:
        RESULTS[tid] = (f"FAIL: attempt1 FLAKE({reason1}) | attempt2 "
                        f"{r2 or 'no result recorded'}")
        print(f"  [FAIL] {tid}  failed on retry")


def _finalize() -> None:
    """Convert any never-retried declared flake into a FAIL."""
    for tid, reason in list(_PENDING_FLAKE.items()):
        RESULTS[tid] = (f"FAIL: declared flake was never retried — this suite's dispatch "
                        f"loop does not call run_with_flake_retry(); policy requires one "
                        f"retry with both outcomes reported. Original claim: {reason}")
    _PENDING_FLAKE.clear()


# ── results summary ──────────────────────────────────────────────────────────

def print_results(all_tests: Optional[list] = None, exit_on_finish: bool = True) -> int:
    """Print the summary. Returns the exit code (and exits, unless told not to)."""
    _finalize()
    print("\n── Results ──────────────────────────────────")
    passed = sum(1 for v in RESULTS.values() if v == "PASS")
    failed = sum(1 for v in RESULTS.values() if v.startswith("FAIL"))
    skipped = sum(1 for v in RESULTS.values() if v.startswith("SKIP"))
    flaky_pass = [t for t, v in RESULTS.items() if v.startswith("FLAKY-PASS")]

    order = [t for t in all_tests if t in RESULTS] if all_tests else list(RESULTS)
    for tid in order:
        print(f"  {tid}: {RESULTS[tid]}")

    if flaky_pass:
        # Bucket 4 of the policy: declared flakes are reported on their own, with
        # both attempts, so nobody reads "130 passed" and counts these among them.
        print("\n── Declared flakes (retried; NOT counted as passes) ──")
        reg, err = _flaky.get_registry()
        for tid in flaky_pass:
            print(f"  {tid}: {RESULTS[tid]}")
            entry = reg.entries.get(tid) if reg else None
            if entry:
                print(f"      owner {entry.owner}  {entry.task}  "
                      f"review_by {entry.review_by}  suite {entry.suite}")

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped, "
          f"{len(flaky_pass)} declared-flake (passed on retry)")
    rc = 0 if failed == 0 else 1
    if exit_on_finish:
        sys.exit(rc)
    return rc
