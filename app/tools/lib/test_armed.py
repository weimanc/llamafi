#!/usr/bin/env python3
"""test_armed.py — the negative/inversion suite for the TASK-635 armed-state
boundary check (R14, harness half).

Binding design: docs/architecture/designs/M-HARNESS2-armed-state-task635.md
§3/§4. No DUT, no serial port, no build — `lib/armed.py` is pure decision
logic and `_gate.run_suite`'s `boundary`/`boundary_start` hooks are callables,
so the whole property is testable with a scripted stand-in for `get armed`
(same stub-the-serial method as `test_class_order.py`'s EC-G8, BP-068).

Arms:

  1. an armed test FAILs; its successor, dispatched after `set injclear`,
     keeps its OWN PASS — the leak does not spill onto the next id.
  2. an armed test that already recorded a FAIL keeps that original reason
     INSIDE the new one.
  3. the same for SKIP and UNMET — either leaking an injector becomes a FAIL,
     with the original record text preserved.
  4. `get armed` unsupported/timed out (`None`) — no verdict change, and the
     notice prints ONCE per run even across multiple `None` reads.
  5. a session-start leak is cleared and reported, attributed to NO id (no
     `RESULTS` row is created for it).
  6. `set injclear` (represented here by a call-count list, since this suite
     has no DUT to send it to) is issued EXACTLY once per leak — one for the
     session-start leak, one per leaking id — and not at all for a clean or
     `None` read.
  7. `boundary=None`/`boundary_start=None` is inert: the same dispatch script
     run through `_gate.run_suite` with the hooks omitted reproduces the
     verdicts dispatch alone would have produced, with no FAIL rewritten.

    python3 app/tools/lib/test_armed.py [-v]        (exit 0 = all arms pass)
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_TOOLS, os.path.join(_TOOLS, "suite")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import armed as A                                       # noqa: E402
from lib import results as R                                     # noqa: E402
from suite.serialdbg import _gate                                # noqa: E402

VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv
FAILURES: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'BAD '}{name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


# ── unit arms: lib/armed.py's pure functions in isolation ───────────────────

def unit_parse_armed():
    print("\n── parse_armed: wire shapes -> list | None ──")
    check("valid non-empty list",
          A.parse_armed({"ok": True, "cmd": "get", "var": "armed", "n": 2,
                         "armed": ["wrDeadUrls", "nowFrozen"], "last": True})
          == ["wrDeadUrls", "nowFrozen"])
    check("valid empty list",
          A.parse_armed({"ok": True, "cmd": "get", "var": "armed", "n": 0,
                         "armed": [], "last": True}) == [])
    check("unknown-var shape (older firmware, design §2.4) -> None",
          A.parse_armed({"ok": False, "cmd": "get",
                         "error": "unknown var", "var": "armed"}) is None)
    check("timeout represented as reply=None -> None",
          A.parse_armed(None) is None)
    check("ok=true but wrong var -> None (never trust the wrong field)",
          A.parse_armed({"ok": True, "cmd": "get", "var": "duty",
                         "duty": 5}) is None)
    check("ok=true, right var, armed not a list -> None",
          A.parse_armed({"ok": True, "cmd": "get", "var": "armed",
                         "armed": "wrDeadUrls"}) is None)
    check("garbage type -> None",
          A.parse_armed("not a dict") is None)


def unit_leak_reason_and_apply():
    print("\n── leak_reason / apply_leak: original text preserved ──")
    R.reset()
    R.pass_("P1")
    reason = A.leak_reason("P1", ["wrDeadUrls"])
    check("names the injector", "wrDeadUrls" in reason)
    check("keeps the original PASS record", "PASS" in reason)

    A.apply_leak("P1", ["wrDeadUrls"])
    check("apply_leak converts to FAIL", R.verdict_of("P1") is R.Verdict.FAIL)
    check("FAIL record names the injector", "wrDeadUrls" in R.RESULTS["P1"])
    check("FAIL record keeps the original PASS text",
          "PASS" in R.RESULTS["P1"])

    R.reset()
    R.fail("F1", "stubbed failure")
    A.apply_leak("F1", ["certbreak"])
    check("a leak on an already-FAILed id stays FAIL",
          R.verdict_of("F1") is R.Verdict.FAIL)
    check("original FAIL reason text survives inside the new one",
          "stubbed failure" in R.RESULTS["F1"])
    check("new reason also names the leaked injector",
          "certbreak" in R.RESULTS["F1"])

    R.reset()
    R.skip("S1", "not applicable to this configuration")
    A.apply_leak("S1", ["geocode"])
    check("a leaking SKIP becomes FAIL", R.verdict_of("S1") is R.Verdict.FAIL)
    check("original SKIP text survives",
          "not applicable to this configuration" in R.RESULTS["S1"])

    R.reset()
    R.unmet("U1", "stubbed unestablished premise")
    A.apply_leak("U1", ["ldrRaw"])
    check("a leaking UNMET becomes FAIL", R.verdict_of("U1") is R.Verdict.FAIL)
    check("original UNMET text survives",
          "stubbed unestablished premise" in R.RESULTS["U1"])

    R.reset()
    A.apply_leak("EMPTY", [])
    check("an empty armed list is a no-op (no RESULTS row created)",
          "EMPTY" not in R.RESULTS)


def unit_session_start_note_and_notifier():
    print("\n── session_start_note / BoundaryNotifier ──")
    R.reset()
    note = A.session_start_note(["nowFrozen"])
    check("names the injector", "nowFrozen" in note)
    check("session-start note creates NO RESULTS row (attributed to nobody)",
          len(R.RESULTS) == 0)

    notifier = A.BoundaryNotifier()
    n1 = notifier.none_notice()
    n2 = notifier.none_notice()
    n3 = notifier.none_notice()
    check("first None read gets a notice", n1 is not None)
    check("second None read this run is silent", n2 is None)
    check("third None read this run is silent too", n3 is None)


# ── integration arm: through _gate.run_suite's boundary/boundary_start hooks ─

#: FEATURE for everything — class_order stays False, so this exercises ONLY
#: the boundary hook, not the CORE-blocking machinery test_class_order.py
#: already owns.
META = {tid: {"cls": "FEATURE", "scope": "shell"}
        for tid in ("N0", "F1", "S1", "U1", "P1", "P2")}
SELECTED = ["N0", "F1", "S1", "U1", "P1", "P2"]


def _dispatch(tid):
    if tid == "N0":
        R.pass_(tid)
    elif tid == "F1":
        R.fail(tid, "stubbed failure")
    elif tid == "S1":
        R.skip(tid, "not applicable to this configuration")
    elif tid == "U1":
        R.unmet(tid, "stubbed unestablished premise")
    else:
        R.pass_(tid)


def _run_scripted(armed_script, boundary_on=True):
    """`armed_script`: the sequence of `get armed` readings, in call order —
    session-start FIRST, then one per selected id in `SELECTED` order. Mirrors
    runner.py's `_boundary`/`_boundary_start` shape exactly, minus the `Dut`:
    the JSON round-trip is `lib.armed.parse_armed`'s job and is unit-tested
    above, so this integration arm exercises what sits ON TOP of that parse —
    the once-per-run notice, the clear bookkeeping, and `_gate.run_suite`'s
    call timing."""
    R.reset()
    queue = list(armed_script)
    notifier = A.BoundaryNotifier()
    printed: list = []
    clears: list = []

    def _next():
        return queue.pop(0)

    def boundary_start():
        armed_list = _next()
        if armed_list is None:
            note = notifier.none_notice()
            if note:
                printed.append(note)
            return
        if armed_list:
            printed.append(A.session_start_note(armed_list))
            clears.append("start")

    def boundary(tid):
        armed_list = _next()
        if armed_list is None:
            note = notifier.none_notice()
            if note:
                printed.append(note)
            return
        if armed_list:
            A.apply_leak(tid, armed_list)
            clears.append(tid)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _gate.run_suite(
            SELECTED, META, _dispatch, class_order=False,
            boundary=boundary if boundary_on else None,
            boundary_start=boundary_start if boundary_on else None,
            exit_on_finish=False, emit=print)
    return rc, dict(R.RESULTS), printed, clears, buf.getvalue()


def integration_boundary_check():
    print("\n── integration: _gate.run_suite's boundary/boundary_start ──")
    # session-start leak, then: N0 unsupported, F1 leaks, S1 leaks, U1 leaks,
    # P1 clean, P2 unsupported again (notice must NOT reprint).
    script = [
        ["nowFrozen"],   # session start
        None,            # after N0
        ["certbreak"],   # after F1
        ["geocode"],     # after S1
        ["ldrRaw"],      # after U1
        [],              # after P1
        None,            # after P2
    ]
    rc, results, printed, clears, out = _run_scripted(script)

    check("session-start leak creates no RESULTS row for it",
          not any(k not in SELECTED for k in results))
    check("session-start note was printed",
          any("nowFrozen" in p for p in printed))

    check("F1 (already FAIL) stays FAIL, names the leak, keeps original text",
          R.verdict_of("F1") is R.Verdict.FAIL
          and "certbreak" in results["F1"] and "stubbed failure" in results["F1"])
    check("S1 (SKIP) leak becomes FAIL, keeps original SKIP text",
          R.verdict_of("S1") is R.Verdict.FAIL
          and "geocode" in results["S1"]
          and "not applicable to this configuration" in results["S1"])
    check("U1 (UNMET) leak becomes FAIL, keeps original UNMET text",
          R.verdict_of("U1") is R.Verdict.FAIL
          and "ldrRaw" in results["U1"]
          and "stubbed unestablished premise" in results["U1"])

    check("P1 (clean boundary) keeps its own PASS",
          R.verdict_of("P1") is R.Verdict.PASS and results["P1"] == "PASS")
    check("N0's PASS is untouched by a None (unsupported) read",
          R.verdict_of("N0") is R.Verdict.PASS)
    check("P2's PASS is untouched by a second None read",
          R.verdict_of("P2") is R.Verdict.PASS)

    none_notices = [p for p in printed if "unsupported" in p]
    check("the None/unsupported notice printed EXACTLY once across the run "
          "(N0 and P2 both read None)", len(none_notices) == 1)

    check("set injclear issued exactly once per leak: start, F1, S1, U1 — "
          "never for the clean P1 or the two None reads",
          clears == ["start", "F1", "S1", "U1"])
    check("no bare exception reached the summary", "Traceback" not in out)


def integration_inert_without_boundary():
    print("\n── integration: boundary=None / boundary_start=None is inert ──")
    rc, results, printed, clears, out = _run_scripted(
        # Same script, but the hooks are never called (boundary_on=False), so
        # nothing should even be able to consume it. An empty script proves
        # that: if the hooks were wrongly invoked, popping from an empty list
        # would raise and this arm would fail with a traceback.
        [], boundary_on=False)

    check("F1 keeps its OWN FAIL, unrewritten by any boundary check",
          results["F1"] == "FAIL: stubbed failure")
    check("S1 keeps its OWN SKIP, unrewritten",
          results["S1"].startswith("SKIP:"))
    check("U1 keeps its OWN UNMET, unrewritten",
          results["U1"].startswith("UNMET:"))
    check("P1/P2/N0 are plain PASS",
          all(results[t] == "PASS" for t in ("P1", "P2", "N0")))
    check("no clear was ever issued", clears == [])
    check("no boundary notice was ever printed", printed == [])
    check("no bare exception reached the summary", "Traceback" not in out)


def unit_reply_status():
    """Unsupported (announce once) and unreadable (say it every time) must not
    collapse into one notice once the firmware has the key."""
    old = {"ok": False, "cmd": "get", "error": "unknown var", "var": "armed"}
    check("unknown-var reply is UNSUPPORTED",
          A.reply_status(old) == A.UNSUPPORTED)
    check("timeout (None) is UNREADABLE",
          A.reply_status(None) == A.UNREADABLE)
    check("malformed ok reply is UNREADABLE",
          A.reply_status({"ok": True, "var": "armed"}) == A.UNREADABLE)
    check("unreadable note names the boundary",
          "after T1" in A.unreadable_note("after T1"))
    check("clear-failed note names what stayed armed",
          "wrDeadUrls" in A.clear_failed_note("after T1", ["wrDeadUrls"]))


def main() -> int:
    unit_reply_status()
    unit_parse_armed()
    unit_leak_reason_and_apply()
    unit_session_start_note_and_notifier()
    integration_boundary_check()
    integration_inert_without_boundary()

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} arm(s) failed: {FAILURES}")
        return 1
    print("PASS: all arms green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
