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

PASSIVE TRIAGE — MODE P (TASK-571, M-TESTARCH §14.2/EC-T1):

  Every FAIL carries the session's health verdict, its `last-phase=`, the
  generation tag and the failing id's own `(cls, scope)`. Nothing re-runs and
  nothing is issued to the device: mode P reads state the session has ALREADY
  observed, so it cannot perturb the run it is reporting on. Modes D
  (in-session descent) and I (isolation re-run) are CUT by @PM (design §20) and
  are deliberately not built, stubbed or referenced here.

  This layer only holds the HOOK. `lib/` never imports a suite (M-TOOLING), so
  the context STRING is built by suite/serialdbg/_triage.py and installed with
  set_fail_context() by the runner once the session exists. With no provider
  installed — every host-side unit test, and every other suite — fail() behaves
  exactly as it did before.

THE `NOT-RUN` BUCKET (TASK-566, M-TESTARCH §4 rule 7 / §4.4):

  `NOT-RUN` is a FOURTH result bucket — never a PASS, never a SKIP, never a
  FAIL. It means "no verdict was reached for this id, because a lower class
  failed first". A summary reading `12 passed, 1 failed, 200 not-run (blocked
  by HEALTH/T_DH_02)` cannot be misread as a firmware verdict, which
  `200 failed` can be and was (§2.2).

  It is deliberately NOT a SKIP: a SKIP is a statement about the test ("not
  applicable to this configuration"), a NOT-RUN is a statement about the RUN.
  Conflating them is how a blocked suite reads green.

  EXIT 4 IS OPT-IN AND NEVER TOUCHES THE SHARED DEFAULT (@VE ruling, design
  §18.4). `print_results` has six callers, five of which are unrelated suites
  that know nothing about health classes; `rc = 0 if failed == 0 else 1` stays
  exactly as it was and the health case passes `health_fail=<id>`. A run with
  zero FAILs and 200 NOT-RUN must exit 4, not 0 — that is the single line where
  "silently green" was most likely to reappear, so it is a parameter a caller
  must ask for rather than a condition inferred from the bucket counts.

THE VERDICT IS A TYPE, AND `UNMET` JOINS THE VOCABULARY (TASK-624, ADR-066
D2/D4/D5, IFC-008 I1-I5, R28/R31/R38):

  `Verdict` is a CLOSED enum — PASS, FAIL, SKIP, FLAKY-PASS, FLAKE, NOT-RUN,
  UNMET — and it is deliberately a PLAIN `enum.Enum`, not a `str` subclass:
  `Verdict.FAIL == "FAIL"` is False and `Verdict.FAIL.startswith(...)` does not
  exist, so the shape this replaces (`RESULTS.get(tid,"").startswith("FAIL")`,
  _gate.py:129) cannot be written against it by accident.

  `RESULTS` keeps its `tid -> record string` shape — five of this module's six
  callers, `run/player-gate`'s sed and every archived log depend on it, and
  retiring it is TASK-608, not this row. The TYPED store `VERDICTS` is
  maintained in lockstep by `RESULTS` itself (see `_ResultsDict`), so the two
  can never disagree: there is one write path, not two stores to keep in sync.
  Gates read `verdict_of(tid)`. Nothing gates on a prefix.

  A record string this module did not produce is REFUSED, loudly, by
  `classify()` raising — that is IFC-008 I2 ("only the results layer writes a
  verdict") with teeth. An unrecognised record used to be silently non-FAIL,
  i.e. silently green.

  `UNMET` vs `NOT-RUN` — the distinction is load-bearing (ADR-066 D2, IFC-008
  I3) and is enforced MECHANICALLY here, not by convention:

    NOT-RUN  never dispatched, because an earlier CLASS failure blocked it.
             ALWAYS carries `blocked-by=<CLASS>/<id>`. `not_run()` REFUSES an
             empty or unshaped attribution, and every NOT-RUN row has an entry
             in `BLOCKED_BY`.
    UNMET    dispatched, but its OWN premise was not established, so it
             asserted nothing. It frequently has NOTHING to blame, so it never
             carries an attribution: `unmet()` REFUSES a `blocked-by=` premise
             and no UNMET row may appear in `BLOCKED_BY`.

  `check_verdict_invariants()` states both directions as a biconditional and
  `print_results` runs it on every run; a violation prints and forces rc>=1.

  `UNMET` BLOCKS AND EXITS 1 (ADR-066 D4, IFC-008 I4). It owns no exit code of
  its own — exactly as NOT-RUN owns none. If a class failure already fired,
  precedence sets 3/4/1 unchanged; otherwise `rc = 0 if failed == 0 else 1`
  becomes `rc = 0 if (failed == 0 and unmet == 0) else 1`. THIS DOES NOT CHANGE
  THE FIVE UNRELATED CALLERS: `unmet()` is new, none of them calls it, so their
  UNMET count is 0 and their rc arithmetic is byte-for-byte what it was. It is
  therefore NOT an opt-in parameter like `health_fail` — there is no behaviour
  to opt out of until a caller records an UNMET on purpose. Exit 4 is NOT used:
  a run of 200 PASS and one UNMET produced 200 trustworthy results, and 4 means
  "no result in this run is trustworthy" (ADR-066 D4, third bullet).
"""

from __future__ import annotations

import enum
import sys
from typing import Callable, Optional

from . import flaky as _flaky

# ── the closed verdict vocabulary (ADR-066 D2 / IFC-008) ─────────────────────


class Verdict(enum.Enum):
    """The CLOSED verdict vocabulary. A gate matches a member (IFC-008 I1).

    A plain Enum on purpose — see the module docstring. The `.value` is the
    canonical token as it appears in a record string and in `run/player-gate`'s
    parser alternation; it is for FORMATTING, never for gating.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    FLAKY_PASS = "FLAKY-PASS"
    FLAKE = "FLAKE"
    NOT_RUN = "NOT-RUN"
    UNMET = "UNMET"

    def __str__(self) -> str:                       # for messages only
        return self.value


#: R28's "may a gate treat it as green?" column, as a set. SKIP is green because
#: it is a statement about the CONFIGURATION; UNMET is not, because it is a
#: statement about the RUN.
GREEN = frozenset({Verdict.PASS, Verdict.SKIP})

#: What a GATING class (RIG/HEALTH/CORE) blocks on — R38. UNMET is in here and
#: that is the whole point of the requirement: an unestablished premise in a
#: gating class must block the classes above it exactly as a FAIL does.
BLOCKING = frozenset({Verdict.FAIL, Verdict.UNMET})

#: Record token -> verdict. Keys are what `classify()` sees after it has cut the
#: record at its first `:` and at its first `(` — so `FLAKE(awaiting mandated
#: retry): jitter` and `FAIL: boom  [triage] ...` both reduce to one token.
_TOKENS = {v.value: v for v in Verdict}


class UnknownVerdict(ValueError):
    """A record string no verdict in the closed vocabulary explains.

    Raised rather than defaulted. IFC-008 I2 says only the results layer writes
    a verdict; a record nobody here produced is a bug in the caller, and the
    pre-TASK-624 behaviour — it is not `FAIL`, so it counts as neither failed
    nor anything else, and the run stays green — is the defect class this whole
    row exists to remove.
    """


def classify(record: str) -> Verdict:
    """The record string -> its `Verdict`. Raises `UnknownVerdict` otherwise.

    This is the COMPATIBILITY path, for the two host unit tests that poke
    `RESULTS[tid] = ...` directly. Every write this module makes carries its
    verdict explicitly and never round-trips through here.
    """
    token = str(record).split(":", 1)[0].split("(", 1)[0].strip()
    try:
        return _TOKENS[token]
    except KeyError:
        raise UnknownVerdict(
            f"{record!r} is not a verdict in the closed vocabulary "
            f"({', '.join(v.value for v in Verdict)}). Only lib/results.py may "
            f"write a verdict (IFC-008 I2); a suite body may not."
        ) from None


# ── result tracking ──────────────────────────────────────────────────────────

#: tid -> Verdict. Never assigned to directly; `RESULTS` maintains it.
VERDICTS: dict[str, Verdict] = {}

#: tid -> `<CLASS>/<id>`, for NOT-RUN rows ONLY. The mechanical half of the
#: NOT-RUN/UNMET split (IFC-008 I3): membership here is a biconditional with
#: `VERDICTS[tid] is Verdict.NOT_RUN`, asserted by check_verdict_invariants().
BLOCKED_BY: dict[str, str] = {}

_BLOCKED_BY_MARK = "blocked-by="


class _ResultsDict(dict):
    """`RESULTS`, with `VERDICTS` and `BLOCKED_BY` maintained in lockstep.

    A `dict` subclass rather than two parallel stores because two stores drift
    and one of the drifting halves is the one gates read. Here there is exactly
    one write path, and it is impossible to record a string without recording
    its type.
    """

    def set_typed(self, tid: str, verdict: Verdict, record: str) -> None:
        """The authoritative write: the verdict is GIVEN, not inferred."""
        if not isinstance(verdict, Verdict):
            raise TypeError(f"verdict must be a Verdict, got {verdict!r}")
        dict.__setitem__(self, tid, record)
        VERDICTS[tid] = verdict
        if verdict is Verdict.NOT_RUN:
            BLOCKED_BY[tid] = record.split(_BLOCKED_BY_MARK, 1)[-1].strip()
        else:
            BLOCKED_BY.pop(tid, None)

    def __setitem__(self, tid, record):             # compatibility path
        self.set_typed(tid, classify(record), record)

    def __delitem__(self, tid):
        dict.__delitem__(self, tid)
        VERDICTS.pop(tid, None)
        BLOCKED_BY.pop(tid, None)

    def pop(self, tid, *default):
        out = dict.pop(self, tid, *default)   # first: a KeyError must not leave
        VERDICTS.pop(tid, None)               # the stores half-updated
        BLOCKED_BY.pop(tid, None)
        return out

    def clear(self):
        dict.clear(self)
        VERDICTS.clear()
        BLOCKED_BY.clear()

    def setdefault(self, *a, **k):                  # not used; refuse it
        raise NotImplementedError("use RESULTS[tid] = record")

    def update(self, *a, **k):                      # not used; refuse it
        raise NotImplementedError("use RESULTS[tid] = record")


RESULTS: dict[str, str] = _ResultsDict()


def verdict_of(tid: str) -> Optional[Verdict]:
    """THE typed accessor every gate reads (IFC-008 I1). `None` = no record.

    `None` is not a verdict and must never be treated as one: an id with no
    record produced no result at all.
    """
    return VERDICTS.get(tid)


def is_green(tid: str) -> bool:
    """R28's green column, typed. An id with NO record is not green."""
    return VERDICTS.get(tid) in GREEN


def check_verdict_invariants() -> list:
    """IFC-008 I2/I3, stated mechanically. -> list of violation strings.

    I3 is a BICONDITIONAL and is checked in both directions on purpose: the
    failure mode ADR-066 D2 warns about is `UNMET` quietly becoming a second
    spelling of `NOT-RUN`, and that shows up first as an UNMET row that has
    acquired an attribution.
    """
    bad = []
    for tid, record in RESULTS.items():
        v = VERDICTS.get(tid)
        if v is None:
            bad.append(f"{tid}: a record with no typed verdict ({record!r})")
            continue
        if v is Verdict.NOT_RUN:
            if tid not in BLOCKED_BY or not BLOCKED_BY[tid]:
                bad.append(f"{tid}: NOT-RUN with no blocked_by — IFC-008 I3 "
                           f"says NOT-RUN ALWAYS names the class failure that "
                           f"blocked it ({record!r})")
        else:
            if tid in BLOCKED_BY:
                bad.append(f"{tid}: {v} carries blocked_by="
                           f"{BLOCKED_BY[tid]!r} — only NOT-RUN may")
            if v is Verdict.UNMET and _BLOCKED_BY_MARK in record:
                bad.append(f"{tid}: UNMET carrying an attribution ({record!r}) "
                           f"— an UNMET is its own unestablished premise, not a "
                           f"second spelling of NOT-RUN (ADR-066 D2)")
    for tid in BLOCKED_BY:
        if tid not in RESULTS:
            bad.append(f"{tid}: blocked_by with no record at all")
    return bad

# ── mode P: the fail-context hook (TASK-571) ─────────────────────────────────

#: Present in an annotated FAIL record. Also the idempotence guard: a record
#: that already carries the marker is never annotated twice.
TRIAGE_MARKER = "[triage]"

#: tid -> single-line context, or None. Installed by the runner; never by lib/.
_FAIL_CONTEXT: Optional[Callable[[str], Optional[str]]] = None


def set_fail_context(provider: Optional[Callable[[str], Optional[str]]]) -> None:
    """Install (or, with None, remove) the mode-P context provider."""
    global _FAIL_CONTEXT
    _FAIL_CONTEXT = provider


def fail_context(tid: str) -> str:
    """The suffix to append to a FAIL record for `tid` — `""` if there is none.

    Fails SILENTLY and returns `""` on any provider error. Mode P is a
    reporting affordance; a broken one must never change a run's verdict, and a
    traceback out of fail() would do exactly that.
    """
    if _FAIL_CONTEXT is None:
        return ""
    try:
        ctx = _FAIL_CONTEXT(tid)
    except Exception:
        return ""
    if not ctx:
        return ""
    # One line, always. run/player-gate parses the summary with a line-oriented
    # sed (`^  <id>: <STATUS>...`); a newline here would push the remainder onto
    # a line that regex cannot account for. TASK-573 was exactly this class of
    # defect — a status string that silently failed to parse.
    return "  " + " ".join(str(ctx).split())


def _annotate(tid: str, record: str) -> str:
    """Append the mode-P context to a FAIL record, once."""
    if TRIAGE_MARKER in record:
        return record
    return record + fail_context(tid)


# tid -> reason, set by flake() and consumed by run_with_flake_retry(). A tid
# left in here at summary time never got its mandated retry.
_PENDING_FLAKE: dict[str, str] = {}

_PENDING_PREFIX = "FLAKE(awaiting mandated retry)"


def reset() -> None:
    """Clear all recorded state (used by the policy's own tests)."""
    RESULTS.clear()
    _PENDING_FLAKE.clear()


def pass_(tid: str, detail: str = ""):
    RESULTS.set_typed(tid, Verdict.PASS, "PASS")
    print(f"  [PASS] {tid}" + (f"  {detail}" if detail else ""))


def fail(tid: str, reason: str):
    record = _annotate(tid, f"FAIL: {reason}")
    RESULTS.set_typed(tid, Verdict.FAIL, record)
    print(f"  [FAIL] {tid}  {record[len('FAIL: '):]}")


def skip(tid: str, reason: str):
    """NOT APPLICABLE TO THIS CONFIGURATION — and nothing else (R28).

    A `skip()` whose reason is really "the precondition did not hold" is
    `unmet()`, not this. That conflation is the finding this vocabulary exists
    to fix: 31 of 43 CORE ids exit through a `skip()` that names a CORE
    precondition, and a SKIP is green (WP-C `C-5`).
    """
    RESULTS.set_typed(tid, Verdict.SKIP, f"SKIP: {reason}")
    print(f"  [SKIP] {tid}  {reason}")


#: Exit 4 — "the board is not a valid subject" (M-TESTARCH §4 rule 3). Distinct
#: from 3 ("the host could not address a board"), and that 3-vs-4 split IS the
#: payload. Every consumer in design §4.1 was taught it in the same commit
#: (EC-G7): run/player-gate, run/test, run/test-targeted, run/test-sync.
HEALTH_FAIL_EXIT = 4

#: The blocked-result prefix. `run/player-gate`'s parser matches this token
#: whole (`FLAKY-PASS|NOT-RUN|PASS|FAIL|SKIP|FLAKE`, longest-first) — TASK-573.
NOT_RUN_PREFIX = "NOT-RUN"


#: The unmet-premise token. `run/player-gate`'s parser matches it whole, next to
#: the other six (TASK-624).
UNMET_PREFIX = "UNMET"


def not_run(tid: str, blocked_by: str):
    """Record that `tid` never ran because `blocked_by` (a `CLASS/<id>` string)
    failed first. Deliberately silent: the blocked set is the whole remaining
    suite, and 200 lines of `[NOT-RUN]` would bury the one line that matters.
    The rows are printed in the summary, where the gate parsers read them.

    The attribution is MANDATORY and shaped (IFC-008 I3). An unattributed
    NOT-RUN is an UNMET wearing the wrong name, and that is precisely how the
    two collapse into synonyms.
    """
    if not blocked_by or "/" not in str(blocked_by):
        raise ValueError(
            f"not_run({tid!r}) needs a `<CLASS>/<id>` attribution, got "
            f"{blocked_by!r}. NOT-RUN ALWAYS names the class failure that "
            f"blocked it (IFC-008 I3); a verdict with nothing to blame is "
            f"unmet(), not this.")
    RESULTS.set_typed(tid, Verdict.NOT_RUN,
                      f"{NOT_RUN_PREFIX}: blocked-by={blocked_by}")


def unmet(tid: str, premise: str):
    """Record that `tid` WAS dispatched but its own premise never held, so it
    asserted nothing (R28, ADR-066 D2).

    NOT a SKIP: a SKIP says "not applicable to this configuration", which is
    green and is a statement about the CONFIGURATION. An UNMET is a statement
    about the RUN, and it is never green.

    NOT a NOT-RUN: a NOT-RUN was never dispatched and always names the class
    failure that blocked it. An UNMET frequently has nothing to blame — which
    is why an attribution is REFUSED here rather than merely omitted. If you
    have a `<CLASS>/<id>` to name, the id was blocked, and that is `not_run()`.

    Printed, unlike not_run(): an UNMET is a per-id event a reader wants at the
    point it happened, and there are not 200 of them in a blocked suite.
    """
    premise = str(premise)
    if _BLOCKED_BY_MARK in premise:
        raise ValueError(
            f"unmet({tid!r}) was given an attribution ({premise!r}). An UNMET "
            f"carries its unestablished premise and nothing to blame; a verdict "
            f"blocked by a named class failure is not_run() (IFC-008 I3).")
    RESULTS.set_typed(tid, Verdict.UNMET, f"{UNMET_PREFIX}: {premise}")
    print(f"  [UNMET] {tid}  premise not established: {premise}")


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
    RESULTS.set_typed(tid, Verdict.FLAKE, f"{_PENDING_PREFIX}: {reason}")
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
    v2 = verdict_of(tid)

    if reason2 is not None:
        RESULTS.set_typed(tid, Verdict.FAIL, _annotate(
            tid, f"FAIL: declared flake REPRODUCED on retry — "
                 f"attempt1 FLAKE({reason1}) | attempt2 FLAKE({reason2})"))
        print(f"  [FAIL] {tid}  declared flake reproduced on retry — not a flake, a failure")
    elif v2 is Verdict.PASS:
        RESULTS.set_typed(tid, Verdict.FLAKY_PASS,
                          f"FLAKY-PASS: attempt1 FLAKE({reason1}) | attempt2 PASS")
        print(f"  [FLAKY-PASS] {tid}  passed on retry — reported separately, NOT counted as PASS")
    elif v2 in (Verdict.SKIP, Verdict.UNMET):
        # Typed, and now covering UNMET too: a retry that could not establish
        # its premise resolved nothing, exactly as a skipped retry resolves
        # nothing. An unresolved flake must never be quieter than a resolved one.
        RESULTS.set_typed(tid, Verdict.FAIL, _annotate(
            tid, f"FAIL: attempt1 FLAKE({reason1}) | attempt2 {r2} (retry could not run)"))
        print(f"  [FAIL] {tid}  retry {v2} — a declared flake cannot be resolved by a "
              f"verdict that asserted nothing")
    else:
        RESULTS.set_typed(tid, Verdict.FAIL, _annotate(
            tid, f"FAIL: attempt1 FLAKE({reason1}) | attempt2 "
                 f"{r2 or 'no result recorded'}"))
        print(f"  [FAIL] {tid}  failed on retry")


def _finalize() -> None:
    """Convert any never-retried declared flake into a FAIL."""
    for tid, reason in list(_PENDING_FLAKE.items()):
        RESULTS.set_typed(tid, Verdict.FAIL, _annotate(
            tid, f"FAIL: declared flake was never retried — this suite's dispatch "
                 f"loop does not call run_with_flake_retry(); policy requires one "
                 f"retry with both outcomes reported. Original claim: {reason}"))
    _PENDING_FLAKE.clear()


# ── results summary ──────────────────────────────────────────────────────────

def print_results(all_tests: Optional[list] = None, exit_on_finish: bool = True,
                  health_fail: Optional[str] = None) -> int:
    """Print the summary. Returns the exit code (and exits, unless told not to).

    `health_fail` is the OPT-IN exit-4 parameter (TASK-566, @VE ruling §18.4):
    pass the failing HEALTH id and the run exits 4 — "the board was not a valid
    subject", not "the firmware failed". It is a parameter and not an inference
    from the NOT-RUN count precisely because five of this function's six callers
    are unrelated suites; the `failed == 0` half of the rc line below is
    untouched.

    `UNMET` is the one bucket that moves rc without a parameter (ADR-066 D4,
    IFC-008 I4), and it can only do so for a caller that recorded one on
    purpose: `unmet()` is new in TASK-624 and the five unrelated callers do not
    call it, so their UNMET count is 0 and their rc arithmetic is unchanged.

    Counting is TYPED throughout (R31) — not one `startswith` remains.
    """
    _finalize()
    print("\n── Results ──────────────────────────────────")
    violations = check_verdict_invariants()
    counts = {v: 0 for v in Verdict}
    for v in VERDICTS.values():
        counts[v] += 1
    passed = counts[Verdict.PASS]
    failed = counts[Verdict.FAIL]
    skipped = counts[Verdict.SKIP]
    flaky_pass = [t for t, v in VERDICTS.items() if v is Verdict.FLAKY_PASS]
    blocked = [t for t, v in VERDICTS.items() if v is Verdict.NOT_RUN]
    unmet_ids = [t for t, v in VERDICTS.items() if v is Verdict.UNMET]

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

    if blocked:
        # R4's mitigation, verbatim: "a shrinking NOT-RUN count is a gate; an
        # invisible one is a fiction". The blocker is named on the same line as
        # the count so no reader has to go looking for why.
        by = sorted(set(BLOCKED_BY.values()))
        print(f"\n── NOT-RUN ({len(blocked)}) — blocked by {', '.join(by)} ──")
        print("  These ids produced NO VERDICT. They are not passes, not skips,")
        print("  and say nothing at all about the firmware.")

    if unmet_ids:
        # R38: "MUST be visible in the summary and the artifact". Its own block,
        # NOT folded into the NOT-RUN one — these ids DID run, and there is
        # deliberately no "blocked by" line here because an UNMET usually has
        # nothing to blame (ADR-066 D2).
        print(f"\n── UNMET ({len(unmet_ids)}) — the premise was never established ──")
        print("  These ids WERE dispatched and asserted NOTHING. Not a skip: a")
        print("  skip is a statement about the configuration, this is a statement")
        print("  about the run. Never green, and it exits 1.")
        for tid in unmet_ids:
            # NOT the `  <id>: <STATUS>` shape. That shape is what
            # run/player-gate's line-oriented sed matches, and repeating a row
            # here would make the comparator parse the same id twice — `E-14`,
            # which is the finding filed against exactly this block's
            # FLAKY-PASS neighbour above. Four spaces and a bullet, so the row
            # above stays the only parseable one.
            print(f"    · {tid}  {RESULTS[tid][len('UNMET: '):]}")

    summary = (f"\n{passed} passed, {failed} failed, {skipped} skipped, "
               f"{len(flaky_pass)} declared-flake (passed on retry)")
    if unmet_ids:
        summary += f", {len(unmet_ids)} unmet (premise not established)"
    if blocked:
        by = sorted(set(BLOCKED_BY.values()))
        summary += f", {len(blocked)} not-run (blocked by {', '.join(by)})"
    print(summary)

    if violations:
        # IFC-008 I2/I3 broken IN THIS RUN. Loud and blocking: the whole point
        # of the invariant is that UNMET and NOT-RUN cannot quietly become
        # synonyms, and a quiet violation is how that would happen.
        print(f"\n[VERDICT-INVARIANT] {len(violations)} violation(s) — the "
              f"NOT-RUN/UNMET split or the typed record is broken:")
        for v in violations:
            print(f"  - {v}")

    # ADR-066 D4 / IFC-008 I4: UNMET blocks and exits 1, and owns no code of its
    # own. If a class failure already fired, `health_fail` below (or the caller's
    # own precedence) sets 3/4 and this 1 is superseded — exactly as NOT-RUN's is.
    rc = 0 if (failed == 0 and not unmet_ids and not violations) else 1
    if health_fail:
        # Opt-in ONLY (§18.4). Deliberately the last word: a HEALTH failure
        # outranks whatever the partial result set happened to contain, because
        # none of it is trustworthy.
        print(f"\n[HEALTH-FAIL] {health_fail} — the board was not a valid test "
              f"subject. Exit 4, NOT 1: nothing here is a statement about the "
              f"firmware.")
        rc = HEALTH_FAIL_EXIT
    if exit_on_finish:
        sys.exit(rc)
    return rc
