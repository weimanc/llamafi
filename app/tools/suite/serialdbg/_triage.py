"""suite/serialdbg/_triage.py — mode P, passive failure triage. TASK-571.

M-TESTARCH §14.2 / EC-T1: **every FAIL in every run carries the session's health
verdict, its `last-phase=`, the generation tag, and the failing test's own
`(cls, scope)`.** That answers "was the board a valid subject when this run
started" at the point of the failure, instead of leaving it to the tribal
knowledge §1 proves unreliable.

PASSIVE MEANS PASSIVE. Nothing here issues a command, opens a port, or re-runs a
step. Every field is read from state the session ALREADY holds — `Dut.gen_tag()`
and `Dut.last_phase()` are accessors over lines `_TeeSerial.readline()` observed
on the way past, and the health verdict is read out of `RESULTS`, which is a
dict. So mode P cannot perturb the session it is reporting on, which is the
whole reason it is the only mode in scope.

MODES D AND I ARE **CUT** (design §19/§20, @PM on all three reviewers'
recommendation) and are deliberately not built, stubbed, or referenced from any
code path. Mode D would execute further steps inside a session that has already
failed, on a rig whose stability is unresolved and non-stationary (TASK-557);
mode I reboots. Both are re-proposals conditioned on TASK-557 closing, not
half-finished work. There is likewise no standalone triage entry point, so EC-T5
holds by construction: nothing here can reset the board before reading it.

DEGRADATION WHEN THE HEALTH CLASS DOES NOT EXIST. This reports
`health=unavailable(no-HEALTH-class;TASK-565)` when no id in the registry
resolves to `cls=HEALTH`, rather than inventing an "ok" nobody measured — a
health verdict asserted from the absence of health checks is precisely the §1
failure mode.

TASK-565 landed `T_DH_01..03` and the verdict started reporting for real with
NO change in this file, exactly as designed. The branch above is kept as the
guard it always was: if the health registry ever stops resolving, the honest
answer is still "unavailable", never "ok". `test_triage_context.py`'s T_TRI_22
pins the live registry against exactly that silent reversion.

WHAT THE VERDICT MEANS IN A SUITE RUN TODAY. The UNCONDITIONAL health gate is
TASK-566 (§4.1), so until it lands a plain `run/test` runs no health check and
reports `health=not-run(0/3)` — true, and in the designed vocabulary. `ok`
appears when the ids were explicitly selected (`run/test-targeted T_DH_01,…`, or
`run/dut-health`, which is the same phase reached by another name).
"""

from __future__ import annotations

from lib.results import (BLOCKING, RESULTS, UnknownVerdict, Verdict,
                         classify)


def _verdict(record):
    """The typed verdict of a record string, or None if it is unclassifiable.

    `health_verdict()` takes an INJECTED results dict, so it cannot read the
    shared `VERDICTS` store; it classifies instead. None is deliberately not a
    verdict — every test below treats it as "not a PASS".
    """
    try:
        return classify(record)
    except UnknownVerdict:
        return None

#: what a field renders as when the session cannot supply it.
UNKNOWN = "?"

#: EC-T1 field order, and it is the order the design lists them in.
_FIELDS = ("health", "last-phase", "gen", "cls", "scope")


def _q(value: str) -> str:
    """Quote a value that contains whitespace. `last-phase` is `"<n> <name>"`
    (`6 ready`), and an unquoted space inside a `key=value` line makes the field
    boundary ambiguous to every reader, human or sed."""
    text = str(value)
    return f'"{text}"' if (not text or " " in text) else text


def health_verdict(meta: dict, results: dict = None) -> str:
    """The session's HEALTH-class verdict, read from what has already run.

    Never re-runs a check — that would be mode D. The verdict describes the
    HEALTH ids this run actually executed, and says so when there were none.
    """
    results = RESULTS if results is None else results
    ids = [tid for tid, rec in (meta or {}).items() if rec.get("cls") == "HEALTH"]
    if not ids:
        return "unavailable(no-HEALTH-class;TASK-565)"
    ran = {tid: results[tid] for tid in ids if tid in results}
    if not ran:
        return f"not-run(0/{len(ids)})"
    # TYPED (TASK-624, R31 — which covers REPORTING as well as gating).
    # `BLOCKING` is {FAIL, UNMET}: a health check whose own premise never held
    # did not certify the board, and `C-4` is the finding that such a run gets
    # announced as healthy anyway. `_verdict` tolerates an injected results dict
    # holding something this layer never wrote — the conservative answer for an
    # unclassifiable record is "not a PASS", which is what falls out below.
    failed = sorted(t for t, v in ran.items() if _verdict(v) in BLOCKING)
    if failed:
        return f"FAIL({','.join(failed)})"
    # FLAKY-PASS is explicitly NOT a PASS (lib/results.py's policy, bucket 2),
    # and neither is a SKIP. Either one means the board was not shown healthy,
    # so it must not read as `ok`.
    other = sorted(t for t, v in ran.items() if _verdict(v) is not Verdict.PASS)
    if other:
        return f"degraded({','.join(other)})"
    if len(ran) < len(ids):
        return f"ok({len(ran)}/{len(ids)})"
    return "ok"


def context(tid: str, dut=None, meta: dict = None, results: dict = None) -> str:
    """The one-line mode-P context for a failing id."""
    rec = (meta or {}).get(tid) or {}
    last_phase = None
    gen = None
    if dut is not None:
        try:
            last_phase = dut.last_phase()
        except Exception:
            last_phase = None
        try:
            gen = dut.gen_tag()
        except Exception:
            gen = None
    values = {
        "health": health_verdict(meta or {}, results),
        # "none" is not "?": no phase line was ever seen, which is itself an
        # observation, whereas "?" means we could not ask.
        "last-phase": _q(last_phase) if last_phase else ("none" if dut is not None else UNKNOWN),
        "gen": gen or UNKNOWN,
        "cls": rec.get("cls", UNKNOWN),
        "scope": rec.get("scope", UNKNOWN),
    }
    return "[triage] " + " ".join(f"{k}={values[k]}" for k in _FIELDS)


def make_provider(dut, meta: dict):
    """A `lib.results.set_fail_context()` provider bound to this session."""
    def _provider(tid: str) -> str:
        return context(tid, dut=dut, meta=meta)
    return _provider


def install(dut, meta: dict) -> bool:
    """Turn mode P on for this session. Returns whether it took.

    Mode P is unconditional (EC-T1) but never load-bearing: if the registry
    cannot be built, the run proceeds with unannotated FAILs rather than
    aborting. A reporting affordance that can abort a run is worse than no
    affordance.
    """
    from lib import results as _results
    try:
        _results.set_fail_context(make_provider(dut, meta))
        return True
    except Exception as e:                                    # pragma: no cover
        print(f"  [triage] mode P unavailable ({type(e).__name__}: {e}) — "
              f"FAILs will carry no health context")
        return False
