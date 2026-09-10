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

THE ARTIFACT IS THE MACHINE INTERFACE (TASK-608, ADR-066 D1, IFC-008, R29/R30):

  `print_results` still prints the human summary and its shape is UNCHANGED —
  archived logs and a year of habits read it. What stops is MACHINES reading it.
  Every run now also emits a schema-versioned JSON document (lib/artifact.py),
  and the three consumers that parsed the printed text read that instead:
  `run/player-gate`'s sed, `lib/baseline.py`'s ROW_RE, and
  `test_triage_context.py`'s re.match.

  `lib/` NEVER IMPORTS A SUITE (M-TOOLING), so the premise fields only a suite
  can know — the ELF hash, the board, the class order, the id selection and its
  reason — are INSTALLED into this layer by the runner via
  `set_premise_provider()`, exactly as `set_fail_context()` is. With no provider
  installed (every host unit test, and the five unrelated suites) the artifact
  still emits, carrying the premise fields this layer can know by itself and
  `null` for the rest. A null field is an honest "this run did not state it";
  an absent artifact would be a silent one.

  THE FIVE UNRELATED CALLERS ARE UNTOUCHED. Emitting a file changes no verdict
  and no return code, and none of them installs a provider or reads an artifact.
"""

from __future__ import annotations

import datetime
import enum
import os
import sys
import time
import uuid
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

#: tid -> {"started_at", "ended_at", "elapsed_s", "_t0"} (R30). Maintained by
#: `RESULTS.set_typed`; `started_at`/`_t0` only exist if a dispatch loop called
#: `begin()`. A retried flake keeps its FIRST `_t0`, so the elapsed of a
#: FLAKY-PASS spans both attempts — which is the honest number for "what this
#: id cost this run", and the one a per-class budget wants.
TIMING: dict[str, dict] = {}

# ── TASK-631 / Dev D3: the last 20 exchanges behind a blocking verdict ────────
#
# WHAT PROBLEM. Triage reads a serial log by hand today: find the run, find the
# id in it, scroll back to the commands that led there. The log is a different
# artefact from the verdict, is not always kept, and after `run/test` restores
# firmware it is frequently the only evidence left — of a board that has since
# been reset (TASK-426's lesson, one layer down).
#
# WHERE IT LIVES. The ARTIFACT, never the text summary. The summary is
# line-oriented and `run/player-gate` parsed it with sed for years; TASK-573 is
# what a summary line that silently fails to parse costs. A twenty-line dump per
# FAIL would also bury the one line a human is looking for. Mode P (TASK-571)
# already puts the ONE-line triage context in the text; this is its machine half.
#
# WHY FAIL **AND** UNMET. `BLOCKING`, not `{FAIL}`. An UNMET is a `NoAnswer` —
# the device stopped answering — and the twenty commands before the silence are
# the most useful twenty lines the harness can hand anybody. Carrying them for a
# FAIL and withholding them for an UNMET would make the more mysterious of the
# two verdicts the less evidenced one.

#: tid -> [exchange, ...], captured at the moment the blocking verdict was
#: written. Empty on a green run, and on any run with no provider installed.
EXCHANGES: dict[str, list] = {}

#: `fn(tid) -> list`, installed by the runner from `lib.replay.FailRing`.
#: `lib/` never imports a suite and the runner owns the `Dut`, so this follows
#: the same installed-hook shape as `set_fail_context`/`set_meta_provider`.
_EXCHANGE_PROVIDER: Optional[Callable[[str], list]] = None


def set_exchange_provider(provider: Optional[Callable[[str], list]]) -> None:
    """Install (or, with None, remove) the fail-context exchange provider."""
    global _EXCHANGE_PROVIDER
    _EXCHANGE_PROVIDER = provider


def _capture_exchanges(tid: str) -> None:
    """Snapshot the ring for `tid`. Silent on any error, always.

    Same rule as `fail_context`: this is a reporting affordance, and a broken
    one must never change a run's verdict. A traceback out of `set_typed` would
    do exactly that — it would turn a recorded FAIL into an unrecorded crash.
    """
    if _EXCHANGE_PROVIDER is None:
        return
    try:
        rows = _EXCHANGE_PROVIDER(tid)
    except Exception:
        return
    if rows:
        EXCHANGES[tid] = list(rows)


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def begin(tid: str) -> None:
    """Mark `tid` dispatched, for the artifact's per-id elapsed (R30).

    Optional by design: the five unrelated `print_results` callers do not call
    it and their artifacts simply carry `elapsed_s: null`. A harness that lied
    about elapsed would be worse than one that admits it did not measure.
    """
    TIMING[tid] = {"started_at": _utcnow(), "ended_at": None,
                   "elapsed_s": None, "_t0": time.monotonic()}


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
        # R30 wants per-record timestamps and elapsed. `ended` is free — it is
        # the moment the verdict was written. `started` is only knowable to a
        # dispatch loop, so it comes from begin() and is None otherwise; an
        # elapsed this layer cannot measure is reported as null rather than
        # invented from the verdict time.
        TIMING[tid] = {
            "started_at": (TIMING.get(tid) or {}).get("started_at"),
            "ended_at": _utcnow(),
            "elapsed_s": (None if (TIMING.get(tid) or {}).get("_t0") is None
                          else round(time.monotonic()
                                     - TIMING[tid]["_t0"], 3)),
            "_t0": (TIMING.get(tid) or {}).get("_t0"),
        }
        if verdict is Verdict.NOT_RUN:
            BLOCKED_BY[tid] = record.split(_BLOCKED_BY_MARK, 1)[-1].strip()
        else:
            BLOCKED_BY.pop(tid, None)
        # TASK-631. Snapshot HERE and not at document-build time: by then the
        # next test has already overwritten the ring, and the twenty exchanges
        # the artifact would carry would be the wrong test's. Only for a
        # blocking verdict — a green run never builds a payload at all, which is
        # the "costs nothing a user would notice" clause, kept mechanically
        # rather than promised.
        if verdict in BLOCKING:
            _capture_exchanges(tid)

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
        TIMING.clear()
        EXCHANGES.clear()

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

# ── the artifact's installed premise (TASK-608 / R30) ────────────────────────
#
# `lib/` never imports a suite (M-TOOLING §3). The premise fields only a suite
# can know are INSTALLED here by the runner, the same shape and for the same
# reason as set_fail_context() above. Two hooks, both optional, both silent on
# error: an artifact is a record, and a broken record must never change a run's
# verdict.

_PREMISE: Optional[Callable[[], dict]] = None
_META: Optional[Callable[[], dict]] = None

#: This process's run identity. `run_token` is the staleness nonce (lib/artifact
#: L2): a consumer that owns the path exports RESULTS_RUN_TOKEN and the reader
#: refuses any artifact carrying a different one. Generated when absent so a run
#: nobody instrumented still has a unique identity.
RUN_TOKEN = os.environ.get("RESULTS_RUN_TOKEN") or uuid.uuid4().hex[:16]
RUN_STARTED_AT = _utcnow()
_RUN_T0 = time.monotonic()


def set_premise_provider(provider: Optional[Callable[[], dict]]) -> None:
    """Install (or, with None, remove) the run-premise provider (R30)."""
    global _PREMISE
    _PREMISE = provider


def set_meta_provider(provider: Optional[Callable[[], dict]]) -> None:
    """Install the `{tid: {cls, scope, effect}}` provider.

    Feeds the artifact's per-id class/scope/effect (IFC-008 "per-id") and the
    per-scope SKIP census in the summary (TASK-627).
    """
    global _META
    _META = provider


def _call(provider, what: str) -> dict:
    if provider is None:
        return {}
    try:
        out = provider()
    except Exception as e:
        print(f"[artifact] {what} provider failed ({type(e).__name__}: {e}) — "
              f"the artifact will carry nulls for it")
        return {}
    return dict(out or {})


def _structured_reason(verdict: Verdict, record: str) -> dict:
    """R32 / IFC-008 I7: a code plus prose, not prose alone.

    The code is the verdict token plus, where the record already names one, the
    machine-set discriminator this layer itself wrote — `blocked-by`,
    `flake-reproduced`, `flake-never-retried`, `premise-unmet`. Deliberately NOT
    a taxonomy of test-body prose: inventing reason codes for messages 195 test
    bodies write freehand would be a mirror of the prose, not a structure over
    it. Grouping across runs works on `code` today and gets finer as bodies are
    taught to pass one (TASK-630's row).
    """
    body = record.split(":", 1)[1].strip() if ":" in record else ""
    code = verdict.value
    if verdict is Verdict.NOT_RUN:
        code = "blocked-by-class"
    elif verdict is Verdict.UNMET:
        code = "premise-unmet"
    elif verdict is Verdict.FAIL and "declared flake REPRODUCED" in record:
        code = "flake-reproduced"
    elif verdict is Verdict.FAIL and "never retried" in record:
        code = "flake-never-retried"
    return {"code": code, "prose": body, "record": record}


def build_document(exit_code: int, health_fail: Optional[str] = None,
                   violations: Optional[list] = None,
                   order: Optional[list] = None) -> dict:
    """The IFC-008 document for the run recorded in this process.

    Additive-only within SCHEMA_MAJOR — a new key here is a MINOR bump, a
    removed or re-meant one is a MAJOR bump and every reader must be taught.
    """
    from . import artifact as _artifact           # deferred: artifact reads us
    from . import flaky as _fl
    from . import version as _version

    try:
        harness = _version.harness_identity()
    except Exception as e:                        # never fail a run for a label
        harness = {"id": None, "error": f"{type(e).__name__}: {e}"}
    meta = _call(_META, "meta")
    premise = _call(_PREMISE, "premise")
    # `order` orders; it never SELECTS. print_results(all_tests) filters its
    # PRINTED rows to the caller's list, and a row recorded under an id outside
    # that list is invisible in the text — which is exactly how a cell scores
    # MISSING in a gate (TASK-573). The artifact carries every recorded id, in
    # the caller's order first and anything else after it.
    ids = [t for t in (order or []) if t in RESULTS]
    ids += [t for t in RESULTS if t not in set(ids)]

    reg, _err = _fl.get_registry()
    counts = {v.value: 0 for v in Verdict}
    per_class: dict = {}
    rows = []
    for tid in ids:
        record = RESULTS[tid]
        v = VERDICTS[tid]
        m = meta.get(tid) or {}
        t = TIMING.get(tid) or {}
        counts[v.value] += 1
        cls = m.get("cls")
        bucket = per_class.setdefault(
            cls or "UNCLASSED",
            {"elapsed_s": 0.0, "counts": {}, "measured_ids": 0})
        bucket["counts"][v.value] = bucket["counts"].get(v.value, 0) + 1
        if t.get("elapsed_s") is not None:
            bucket["elapsed_s"] = round(bucket["elapsed_s"] + t["elapsed_s"], 3)
            bucket["measured_ids"] += 1
        row_exchanges = EXCHANGES.get(tid) if v in BLOCKING else None
        rows.append({
            "id": tid,
            "verdict": v.value,
            "cls": cls,
            "scope": m.get("scope"),
            "effect": m.get("effect"),
            "blocked_by": BLOCKED_BY.get(tid),
            "started_at": t.get("started_at"),
            "ended_at": t.get("ended_at"),
            "elapsed_s": t.get("elapsed_s"),
            "reason": _structured_reason(v, record),
            # TASK-631, schema 1.1 (additive). Present ONLY on a blocking
            # verdict and ONLY when a ring was installed; `null` everywhere else
            # says "not recorded", which is different from "there were none".
            "exchanges": row_exchanges,
        })
    for bucket in per_class.values():
        # An elapsed summed over only SOME of a class's ids is not that class's
        # elapsed. Say which it is rather than letting a budget read a partial
        # sum as a total (R53's measurement is the consumer).
        bucket["elapsed_complete"] = (
            bucket["measured_ids"] == sum(bucket["counts"].values()))

    return {
        "schema": {"name": _artifact.SCHEMA_NAME,
                   "version": _artifact.SCHEMA_VERSION},
        "run": {
            "run_token": RUN_TOKEN,
            "started_at": RUN_STARTED_AT,
            "ended_at": _utcnow(),
            "elapsed_s": round(time.monotonic() - _RUN_T0, 3),
            "exit_code": exit_code,
            "counts": counts,
            "health_fail": health_fail,
            "unmet": [r["id"] for r in rows if r["verdict"] == "UNMET"],
            "not_run": {r["id"]: r["blocked_by"] for r in rows
                        if r["verdict"] == "NOT-RUN"},
            "invariant_violations": list(violations or []),
            # TASK-677 / PROP-011 §5 P0 / schema 1.3 (additive, optional).
            "rig": _rig_section(),
        },
        "premise": {
            # R30's list. What this layer can know by itself is filled in; the
            # rest comes from the installed provider and is null when no
            # provider is installed — an honest "this run did not state it".
            # TASK-645. Was `_artifact.SCHEMA_VERSION` — the version of the
            # DOCUMENT FORMAT, which the document already carries two keys up
            # under `schema.version`. R30 asks what CODE produced the run, and
            # that had no source in the tree at all. It does now: a content hash
            # over `app/tools/**/*.py` + `run/*`, with git alongside as
            # provenance. See lib/version.py for why the hash is the identity
            # and `git describe` is not. ~19 ms, no network, no build.
            "harness_version": harness["id"],
            "harness": harness,
            "entry_point": premise.get("entry_point")
                           or os.path.basename(sys.argv[0] or "?"),
            "argv": premise.get("argv") or list(sys.argv[1:]),
            "flake_registry_path": str(reg.path) if reg else None,
            "flake_registry_sha256": _fl.registry_sha256(),
            "elf": premise.get("elf"),
            "elf_expected": premise.get("elf_expected"),
            "build_env": premise.get("build_env"),
            "board": premise.get("board"),
            "generation": premise.get("generation"),
            "class_order_in_force": premise.get("class_order_in_force"),
            "class_order": premise.get("class_order"),
            "selection": premise.get("selection"),
            "downgraded_gates": premise.get("downgraded_gates") or [],
        },
        "per_class": per_class,
        "results": rows,
    }


def _rig_section() -> Optional[dict]:
    """TASK-677 / PROP-011 §5 P0 / schema 1.3. `None` unless RIGWATCH=1 (see
    run/local.env.example) — a public checkout's artifacts are byte-for-byte
    unaffected by this task, other than the one new optional key.

    Imports lib.rigwatch lazily and NEVER raises: a summary read is a file
    read (rigwatch never opens the serial port — see its module docstring),
    but "the summary could not be computed" must not cost the run its
    artifact, which is the one thing R29 actually requires.

    The window is this run's own — from RUN_STARTED_AT to now — which is why
    this is called from build_document() rather than computed once at import:
    the run's `ended_at` is not known until the artifact is being assembled.
    """
    if os.environ.get("RIGWATCH", "") != "1":
        return None
    try:
        from . import rigwatch as _rigwatch
        # RUN_STARTED_AT is an ISO-8601 UTC string (see _utcnow()); rigwatch's
        # since-parsing only understands an epoch float or a duration, so
        # convert here rather than teach rigwatch a third format for one
        # caller.
        started = datetime.datetime.strptime(
            RUN_STARTED_AT, "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=datetime.timezone.utc).timestamp()
        summ = _rigwatch.summarize(started)
        note = _rigwatch.annotate_run_rig(summ)
        return {
            "reenum": summ["reenum"],
            "unexplained_boots": summ["unexplained_boots"],
            "bod_trips": summ["bod_trips"],
            "wifi_disc": summ["wifi_disc"],
            "event_count": len(summ["events"]),
            "annotation": note,
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def write_artifact(exit_code: int, health_fail: Optional[str] = None,
                   violations: Optional[list] = None,
                   order: Optional[list] = None):
    """Emit the run artifact. -> the path, or None if it could not be written.

    Never raises: R29 makes the artifact the interface, but a run that produced
    real verdicts and then failed to write a file must still report those
    verdicts and still return its own rc. The failure is printed, loudly, so it
    cannot be mistaken for "the consumer had nothing to read because nothing
    ran" — which is the reading the consumer must NOT make (lib/artifact L3).
    """
    from . import artifact as _artifact
    try:
        doc = build_document(exit_code, health_fail, violations, order)
        path = os.environ.get(_artifact.ENV_PATH) or _artifact.default_path(
            RUN_TOKEN, RUN_STARTED_AT)
        return _artifact.write(path, doc)
    except Exception as e:
        print(f"\n[artifact] FAILED to write the run artifact "
              f"({type(e).__name__}: {e}). The verdicts above stand; any gate "
              f"reading the artifact will refuse this run rather than score it.")
        return None


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
    from .artifact import SCHEMA_VERSION as _ARTIFACT_VERSION
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

    if skipped:
        # TASK-627 / QM §7 and LL-148. `skip()` prints GREEN and nothing
        # aggregated it, so cluster C10 — the heatmap injector wedging a
        # sub-view — emitted seven identical skip lines every run for a year and
        # was invisible in all of them. A per-scope count is what makes a wedged
        # FAMILY visible: one scope holding most of a run's skips is a shape a
        # reader notices, where seven lines scattered through 195 are not.
        # Counted per SCOPE, not per class, because a wedge is a property of the
        # app under test. Ids with no record (`meta` unavailable, or a suite
        # with no meta provider at all) are counted under `?` rather than
        # dropped — a census that silently omits what it cannot classify is the
        # same defect one altitude up.
        meta = _call(_META, "meta")
        by_scope: dict = {}
        for tid, v in VERDICTS.items():
            if v is Verdict.SKIP:
                sc = (meta.get(tid) or {}).get("scope") or "?"
                by_scope.setdefault(sc, []).append(tid)
        print(f"\n── SKIP by scope ({skipped}) ──")
        for sc, tids in sorted(by_scope.items(),
                               key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"  {sc:<20} {len(tids):>3}  {', '.join(sorted(tids))}")
        print("  A SKIP is a statement about the CONFIGURATION. A whole scope")
        print("  skipping is usually a statement about the RUN — a wedged app,")
        print("  a precondition nothing re-establishes — and that is an UNMET")
        print("  wearing a green coat (R28). Check the scope with the most.")

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

    # R29 / ADR-066 D1: the machine interface. Written LAST, so `exit_code` is
    # the code the process will actually return — an artifact whose exit_code
    # disagreed with the process's would be a second interface to reconcile.
    # Emitted for every caller, including the five unrelated ones: it changes no
    # verdict and no rc, and a suite that emits nothing has no premise on record.
    path = write_artifact(rc, health_fail=health_fail, violations=violations,
                          order=order)
    if path:
        # IFC-008's transport clause: "a JSON file written once per run, at a
        # path the run reports". Printed, so a human reading a log can find it.
        print(f"\n[artifact] {path}  (schema {_ARTIFACT_VERSION}, run_token "
              f"{RUN_TOKEN})")

    if exit_on_finish:
        sys.exit(rc)
    return rc
