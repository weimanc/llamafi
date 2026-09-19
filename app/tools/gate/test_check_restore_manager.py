#!/usr/bin/env python3
"""test_check_restore_manager.py — the negative suite for TASK-602's two halves.

BP-068: a gate without a negative test is not a gate. BP-074: an assertion whose
precondition never occurred is inconclusive, not a pass — so every arm constructs
the violation it claims to catch and asserts the finding CODE, not a non-empty
list.

Four subjects, and the fourth is new (TASK-673):

  A. the CHECKER (`check_restore_manager.py`) — and specifically the property R17
     asks for and a `finally`-grep cannot give: **four fixtures that a static
     "is there a restore near this set?" match would accept, all of which leak,
     are each flagged.** That is the arm that distinguishes this gate from the
     one R17 warns against.

  B. the MANAGERS (`lib.dut.Dut.saved` / `.injected`) — do they restore on the
     failure path, does an unreadable snapshot stop the body running rather than
     restore to a guess, and is a refused restore LOUD.

  C. the ratchet, in both directions, plus M6 — the stale-credit check on
     `DELEGATING_MANAGERS`, which is the one clause that can silently grant an
     amnesty to every call site of a helper.

  D. the RUNTIME arm (TASK-673): `lib.canfail._restore_leaks()` at the unit
     level (fires on a genuine no-restore-attempted path, stays quiet on a
     manager restore whether it lands before OR after the poisoned verdict —
     the exact ordering that broke the first draft, pinned by name — and
     reports, but does not FLAG, a set-back that was attempted and missed the
     transcript), then the same property end-to-end through a real recorded
     transcript and `CF.sweep()`, then `check_restore_manager.py`'s own
     aggregation (`SELF_REARMING_VARS` filtering, an unrecorded id contributing
     nothing, the shrink-only ledger in both directions) and the live corpus.

No DUT, no serial port, no network. The Dut is never constructed: the manager arms
drive unbound methods against a stub (R48 / TASK-609). Section D's end-to-end
fixtures record a REAL transcript off a scripted device (same shape as
`gate/test_check_can_go_red.py`'s `Device`/`FakeSerial`/`record()`) and run the
REAL `lib.canfail.sweep()` over it — nothing here re-implements the engine.

    python3 app/tools/gate/test_check_restore_manager.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_restore_manager as C                                   # noqa: E402
from lib.dut import Dut, BadField, NoAnswer, RestoreFailed          # noqa: E402
from lib import canfail as CF                                       # noqa: E402
from lib import replay as RP                                        # noqa: E402
from lib import results as R                                        # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


def codes(findings):
    return sorted({f.split()[0] for f in findings})


def n_hits(src, mech=frozenset()):
    return len(C.unrestored_mutations(src, mech))


# ── A. the checker, and the four look-alike restores ─────────────────────────
#
# Every fixture below contains a `set` and a restore that a static match for
# "a `finally:` restoring something" would accept. All four leak.

# (1) the restore is on the pass path only — `C-15`.
A1_PASS_PATH_ONLY = '''
def t(dut, tid):
    dut.cmd("set playerMode 2")
    if not ok(dut):
        fail(tid, "no"); return
    dut.cmd("set playerMode 0")
'''

# (2) `finally:` restores a DIFFERENT variable than the body set.
A2_WRONG_VAR = '''
def t(dut, tid):
    dut.cmd("set clockStyle 3")
    try:
        body(dut)
    finally:
        dut.cmd("set playerMode 0")
'''

# (3) `finally:` restores from a DEFAULTED read — `C-12`/`D-15`/`E-4`.
A3_DEFAULTED_SNAPSHOT = '''
def t(dut, tid):
    before = dut.cmd("get playerMode").get("val", 0)
    dut.cmd("set playerMode 2")
    try:
        body(dut)
    finally:
        dut.cmd(f"set playerMode {before}")
'''

# (4) `finally:` restores to a GUESSED constant with an unacknowledged `cmd`.
A4_GUESSED_CONSTANT = '''
def t(dut, tid):
    dut.cmd("set bgPoll 0")
    try:
        body(dut)
    finally:
        dut.cmd("set bgPoll 1")
'''

# The one shape that is credited.
A5_MANAGER = '''
def t(dut, tid):
    with dut.saved("playerMode", set_to=2):
        body(dut)
'''

A6_INJECTED = '''
def t(dut, tid):
    with dut.injected("triggerHeatmap", 1, clear_to=0):
        body(dut)
'''

A7_DELEGATE = '''
def t(dut, tid):
    with _bgpoll_suspended(dut):
        dut.cmd("set bgPoll 0")
'''

# The manager covers a DIFFERENT variable than the body writes — the credit must
# be keyed on the name, or the gate becomes "is there any `with` nearby".
A8_MANAGER_WRONG_VAR = '''
def t(dut, tid):
    with dut.saved("playerMode"):
        dut.cmd("set clockStyle 3")
'''

# The write is in the `with` ITEM, i.e. evaluated before the manager is armed.
A9_WRITE_IN_ITEM = '''
def t(dut, tid):
    with dut.saved("playerMode"), open(dut.cmd("set clockStyle 3")):
        pass
'''

# Controls: things that are not device writes at all.
A10_CONTROL = '''
def t(dut, tid):
    d = {}
    d["set playerMode"] = 1
    cfg.cmd("settings")
    subprocess.run(["set", "playerMode"])
    dut.cmd("get playerMode")
    dut.cmd("tap 100 100")
'''


def test_checker():
    print("A. the checker")
    for name, src in (("pass-path-only (C-15)", A1_PASS_PATH_ONLY),
                      ("finally restores the wrong var", A2_WRONG_VAR),
                      ("finally restores a defaulted read", A3_DEFAULTED_SNAPSHOT),
                      ("finally restores a guessed constant", A4_GUESSED_CONSTANT)):
        check(f"A: flags {name}", n_hits(src) >= 1,
              f"got {n_hits(src)} hits, expected >= 1")
    check("A: credits `with dut.saved(...)`", n_hits(A5_MANAGER) == 0,
          C.unrestored_mutations(A5_MANAGER))
    check("A: credits `with dut.injected(...)`", n_hits(A6_INJECTED) == 0,
          C.unrestored_mutations(A6_INJECTED))
    check("A: credits a registered delegating manager", n_hits(A7_DELEGATE) == 0,
          C.unrestored_mutations(A7_DELEGATE))
    check("A: a manager over another var is NOT credit",
          n_hits(A8_MANAGER_WRONG_VAR) == 1, C.unrestored_mutations(A8_MANAGER_WRONG_VAR))
    check("A: a write in the `with` item is outside the manager",
          n_hits(A9_WRITE_IN_ITEM) == 1, C.unrestored_mutations(A9_WRITE_IN_ITEM))
    check("A: `set injclear` is a clear, not a mutation (TASK-635)",
          n_hits('def t(d):\n    d.cmd("set injclear 1", timeout=2.0)\n') == 0)
    check("A: a real key next to it is still counted",
          n_hits('def t(d):\n    d.cmd("set injclearX 1")\n') == 1)
    check("A: control — non-device calls are untouched", n_hits(A10_CONTROL) == 0,
          C.unrestored_mutations(A10_CONTROL))
    check("A: f-string var is read from the leading literal",
          C.unrestored_mutations('def t(d):\n    d.cmd(f"set prRange {n}")\n') == [(2, "prRange")],
          C.unrestored_mutations('def t(d):\n    d.cmd(f"set prRange {n}")\n'))
    check("A: a dynamic var name is counted, unnamed",
          C.unrestored_mutations('def t(d):\n    d.cmd(f"set {v} 1")\n') == [(2, None)],
          C.unrestored_mutations('def t(d):\n    d.cmd(f"set {v} 1")\n'))
    check("A: SELF_REARMING_VARS (cooldown) is not counted",
          n_hits('def t(d):\n    d.cmd("set cooldown 0")\n') == 0)
    check("A: the mechanism exemption applies ONLY to the named functions",
          n_hits('def _restore(self, v):\n    self.set_val("x", 1)\n',
                 C.MECHANISM_FUNCS) == 0
          and n_hits('def _restore(self, v):\n    self.set_val("x", 1)\n') == 1)


# ── B. the managers ──────────────────────────────────────────────────────────

class _StubDut:
    """A Dut-shaped object answering from a canned reply list. Never opens a port;
    the managers are called as unbound methods against it, so what is under test
    is the SHIPPED code, not a copy."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.sent = []

    def send(self, cmd):
        self.sent.append(cmd)

    def read_json(self, timeout=3.0):
        if not self._replies:
            raise TimeoutError("stub: nothing left")
        return self._replies.pop(0)

    read_reply = Dut.read_reply
    get_val = Dut.get_val
    set_val = Dut.set_val
    saved = Dut.saved
    injected = Dut.injected
    _restore = Dut._restore


def _ok(var, val=None):
    r = {"ok": True, "var": var}
    if val is not None:
        r["val"] = val
    return r


def test_managers():
    print("B. the managers")

    # B1 — restore runs on the FAILURE path. `C-15` is exactly this.
    d = _StubDut([_ok("playerMode", 2), _ok("playerMode"), _ok("playerMode")])
    try:
        with d.saved("playerMode", set_to=0):
            raise RuntimeError("the body failed")
    except RuntimeError as e:
        body_propagated = str(e) == "the body failed"
    check("B1: the body's exception still propagates", body_propagated is True)
    check("B1: and the restore ran anyway",
          d.sent[-1] == "set playerMode 2", d.sent)

    # B2 — an unreadable snapshot stops the BODY, it does not restore to a guess.
    ran = []
    d = _StubDut([])                       # nothing answers `get playerMode`
    try:
        with d.saved("playerMode"):
            ran.append(1)
    except NoAnswer:
        raised = "NoAnswer"
    except Exception as e:                 # noqa: BLE001
        raised = type(e).__name__
    else:
        raised = "none"
    check("B2: an unread snapshot raises NoAnswer (-> UNMET)", raised == "NoAnswer", raised)
    check("B2: and the body never ran", ran == [], ran)
    check("B2: and nothing was written back",
          not any(s.startswith("set ") for s in d.sent), d.sent)

    # B2b — the device REFUSED the read: BadField (-> FAIL), same containment.
    d = _StubDut([{"ok": False, "var": "playerMode"}])
    check("B2b: a refused snapshot raises BadField (-> FAIL)",
          _raises(lambda: _enter_saved(d, "playerMode"), BadField))

    # B3 — an UNACKNOWLEDGED restore is loud. This is why set_val returns the
    # reply: `dut.cmd` would have accepted `ok:false` silently.
    d = _StubDut([_ok("playerMode", 2), {"ok": False, "var": "playerMode"}])
    try:
        with d.saved("playerMode"):
            pass
    except RestoreFailed:
        loud = True
    except Exception as e:                 # noqa: BLE001
        loud = f"wrong exception: {type(e).__name__}"
    else:
        loud = "silent — the restore was refused and nobody heard"
    check("B3: a refused restore raises RestoreFailed", loud is True, loud)

    # B4 — a failing restore UNDER a failing body annotates, never replaces.
    d = _StubDut([_ok("playerMode", 2), {"ok": False, "var": "playerMode"}])
    try:
        with d.saved("playerMode"):
            raise ValueError("the real verdict")
    except ValueError as e:
        kept = str(e) == "the real verdict"
        annotated = len(getattr(e, "restore_errors", [])) == 1
    check("B4: the body's verdict survives a failed restore", kept is True)
    check("B4: and the restore failure is attached, not swallowed", annotated is True)

    # B5 — injected() clears with the value the CALLER named, on the failure path.
    d = _StubDut([_ok("triggerHeatmap"), _ok("triggerHeatmap")])
    try:
        with d.injected("triggerHeatmap", 1, clear_to=0):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    check("B5: injected() clears on the failure path",
          d.sent == ["set triggerHeatmap 1", "set triggerHeatmap 0"], d.sent)

    # B6 — injected() has no default clearing value. BP-073 as an API.
    check("B6: clear_to is mandatory",
          _raises(lambda: Dut.injected(_StubDut([]), "x", 1), TypeError))

    # B7 — set_to with several variables is a programming error, not a silent
    # write of one of them.
    check("B7: set_to= with 2 variables raises",
          _raises(lambda: _enter_saved(_StubDut([_ok("a", 1), _ok("b", 1)]),
                                       "a", "b", set_to=0), ValueError))


def _enter_saved(d, *vars_, **kw):
    with Dut.saved(d, *vars_, **kw):
        pass


def _raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception as e:                 # noqa: BLE001
        return f"wrong exception: {type(e).__name__}: {e}"
    return "no exception raised"


# ── C. the ratchet and the stale credit ──────────────────────────────────────

def test_ratchet():
    print("C. the ratchet")
    counts = {"suite/a.py": 3, "lib/dut.py": 0}
    check("C1: over cap fails (M1)",
          codes(C.evaluate(counts, {"suite/a.py": (2, "x:1")})) == ["M1"])
    check("C2: at cap passes",
          C.evaluate(counts, {"suite/a.py": (3, "x:1")}) == [])
    check("C3: a stale cap fails (M2) — the ratchet bites both ways",
          codes(C.evaluate(counts, {"suite/a.py": (9, "x:1")})) == ["M2"])
    check("C4: a row for a module that is gone fails (M3)",
          codes(C.evaluate({"suite/a.py": 0}, {"suite/gone.py": (1, "x:1")})) == ["M3"])
    check("C5: a lib/ row fails (M5) even at the real count",
          "M5" in codes(C.evaluate({"lib/dut.py": 2}, {"lib/dut.py": (2, "x:1")})))
    check("C6: no ledger row means cap 0",
          codes(C.evaluate({"suite/a.py": 1}, {})) == ["M1"])

    # M6 — the clause that can hand out an amnesty. A registry entry credits every
    # call site of a helper; when the helper stops delegating, the credit is a lie.
    real = C.DELEGATING_MANAGERS
    try:
        C.DELEGATING_MANAGERS = {"_no_such_helper_anywhere": frozenset({"x"})}
        check("C7: a registry entry with no helper fails (M6)",
              codes(C.check_delegates()) == ["M6"], C.check_delegates())
    finally:
        C.DELEGATING_MANAGERS = real
    check("C8: the live registry passes M6", C.check_delegates() == [],
          C.check_delegates())

    # And the live tree: the ledger is real, and the ratchet is satisfied.
    counts, _detail = C.scan()
    ledger, lerrs = C.parse_ledger()
    check("C9: the shipped ledger parses with no malformed rows", lerrs == [], lerrs)
    check("C10: the shipped tree is within its ratchet",
          C.evaluate(counts, ledger) == [], C.evaluate(counts, ledger))
    check("C11: lib/ is at zero, structurally",
          counts.get("lib/dut.py") == 0, counts.get("lib/dut.py"))
    check("C12: _bgpoll_suspended is credited, so its callers are too",
          counts.get("suite/serialdbg/_helpers.py", 99) <= 2)


# ── D. the runtime arm (TASK-673) ────────────────────────────────────────────

class _FakeWitness:
    """A canned `_RestoreWitness`-shaped object — `log`/`verdict_at`/`verdict`
    are all `_restore_leaks()` reads. Exercises the REAL shipped function with
    exact control over the ordering that matters, no replay engine needed."""

    def __init__(self, log, verdict_at, verdict=R.Verdict.FAIL):
        self.log, self.verdict_at, self.verdict = log, verdict_at, verdict


def _kinds(leaks):
    return sorted(leak.kind for leak in leaks)


def test_runtime_unit():
    print("D1. _restore_leaks() at the unit level")

    # D1a — the C-15 shape: mutated, never touched again. THE finding.
    w = _FakeWitness([("set x 1", True)], verdict_at=1)
    check("D1a: no later set at all -> NO_RESTORE_ATTEMPTED",
          _kinds(CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w))
          == ["NO_RESTORE_ATTEMPTED"])

    # D1b — a manager restore that lands AFTER the verdict (the textbook shape
    # the design doc describes) is clean.
    w = _FakeWitness([("set x 1", True), ("set x 0", True)], verdict_at=1)
    check("D1b: an acked set-back AFTER the verdict is clean",
          CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w) == [])

    # D1c — THE REGRESSION PIN. `T-CDWN-02`'s shape: the manager restore fires
    # on `with`-exit, BEFORE the later `fail()` that records the verdict — both
    # commands land before `verdict_at`. The first draft of this rule only
    # looked "from the verdict onward" and flagged this as a leak; it must not.
    w = _FakeWitness([("set x 1", True), ("set x 0", True)], verdict_at=2)
    check("D1c: an acked set-back BEFORE the verdict (T-CDWN-02's shape) is "
          "clean, not a leak",
          CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w) == [],
          CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w))

    # D1d — a set-back WAS attempted but every attempt missed the transcript:
    # its own kind, never counted as NO_RESTORE_ATTEMPTED, never silently clean.
    w = _FakeWitness([("set x 1", True), ("set x 0", False)], verdict_at=1)
    check("D1d: an attempted-but-unacked set-back is its own kind, not a leak",
          _kinds(CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w))
          == ["RESTORE_ATTEMPTED_UNRECORDED"])

    # D1e — no verdict this arm cares about (PASS/SKIP under poison) -> [].
    w = _FakeWitness([("set x 1", True)], verdict_at=None)
    check("D1e: verdict_at is None -> []",
          CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w) == [])

    # D1f — a `set` that only ever appears AFTER the verdict was never
    # established as a mutation this path made; not a finding.
    w = _FakeWitness([("get x", True), ("set x 1", True)], verdict_at=1)
    check("D1f: a set that only occurs at/after the verdict is not a mutation",
          CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w) == [])

    # D1g — a MISSED mutation attempt before the verdict cannot occur in a real
    # run (it would have voided the row before a verdict was ever written), but
    # the function must not crash or misclassify if handed one directly: an
    # unacked `set` before the verdict is not treated as an established
    # mutation (only an acked one is, per the docstring).
    w = _FakeWitness([("set x 1", False)], verdict_at=1)
    check("D1g: an unacked pre-verdict set is not a mutation",
          CF._restore_leaks(CF.Poison.PERTURB, CF.Extent.AT, 0, w) == [])


def test_replied_ok():
    """`_replied_ok()` — THE SECOND REGRESSION PIN. `acked` must mean "the
    reply says ok:true", not "the lookup found an exchange". A REFUSE poison
    hits the transcript (no `TranscriptMiss`) but answers `{"ok":false,...}`;
    conflating the two flagged `T-BUSY-01b`'s and `T085`'s properly-restored
    mutations as leaks (see `lib/canfail.py`'s docstring)."""
    print("D1h. _replied_ok() — hit-the-transcript vs actually-acked")
    check("D1h: a healthy ok:true reply is acked",
          CF._replied_ok(['{"ok":true,"cmd":"set","var":"x"}']) is True)
    check("D1i: a REFUSE-poisoned ok:false reply is NOT acked, even though "
          "the exchange existed",
          CF._replied_ok(['{"ok":false,"err":"poisoned","var":"x"}']) is False)
    check("D1j: SILENCE (no lines at all) is not acked",
          CF._replied_ok([]) is False)
    check("D1k: a non-JSON debug line with no JSON reply is not acked",
          CF._replied_ok(["[shell] some debug chatter"]) is False)
    check("D1l: a debug line followed by a real ok:true reply IS acked "
          "(scans every line, not just the first)",
          CF._replied_ok(["[shell] chatter",
                          '{"ok":true,"cmd":"set","var":"x"}']) is True)


# ── D2. end-to-end through a real transcript and the real sweep ─────────────

class _Device:
    """A tiny stateful scripted device: `get x` answers whatever the last
    `set x <v>` wrote (default 0)."""

    def __init__(self):
        self.x = 0

    def handle(self, line):
        w = line.split()
        if w[:2] == ["get", "x"]:
            return [{"ok": True, "var": "x", "val": self.x}]
        if w[:2] == ["set", "x"]:
            self.x = int(w[2])
            return [{"ok": True, "var": "x"}]
        return [{"ok": True, "cmd": w[0] if w else "?"}]


class _FakeSerial:
    def __init__(self, dev, clock):
        self.dev, self.clock, self.out = dev, clock, []

    def write(self, b):
        for r in self.dev.handle(b.decode().strip()):
            self.out.append(json.dumps(r))
        return len(b)

    def flush(self):
        pass

    def readline(self):
        if self.out:
            return (self.out.pop(0) + "\n").encode()
        self.clock.tick()
        return b""


def _record(tid, body):
    """A REAL Transcript, off a REAL recording of `body` against `_Device` —
    same shape as `gate/test_check_can_go_red.py`'s `record()`."""
    clock = RP.VirtualClock()
    d = object.__new__(Dut)
    d.ser = _FakeSerial(_Device(), clock)
    d._owner_thread = threading.current_thread()
    d.port, d.elf, d.elf_expected, d.build_env = "fake", "ab", "ab", "e"
    R.RESULTS.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        with RP.virtual_time(clock):
            with RP.recording(d, tid) as rec:
                body(d)
    R.RESULTS.clear()
    return rec.transcript


def _leaky_body(dut):
    dut.cmd("set x 1")
    v = dut.get_int("x")
    if v != 1:
        R.fail("T_RT_LEAK", "x wrong"); return
    R.pass_("T_RT_LEAK")


def _early_restore_body(dut):
    """T-CDWN-02's exact shape: the manager's restore fires on `with`-exit,
    strictly BEFORE the `fail()` below it that reads the check's own result."""
    v = [None]
    with dut.injected("x", 1, clear_to=0):
        v[0] = dut.get_int("x")
    if v[0] != 1:
        R.fail("T_RT_EARLY", "x wrong"); return
    R.pass_("T_RT_EARLY")


def _managed_body_no_assertion(dut):
    """`T-BUSY-01b`'s exact shape, minimised: a properly `dut.saved(...)`
    -managed mutation, and NO `fail()` call anywhere in the body itself — the
    only way this can go FAIL/UNMET at all is a dispatch-arm accident (a
    REFUSE/SILENCE-poisoned `set`/`get` raising `BadField`/`NoAnswer`/
    `TimeoutError`), never an assertion. That is deliberate: it keeps `sweep()`
    from ever stopping early on an ASSERTION grade, so the search runs the
    FULL grid — including REFUSE on the mutating `set x 1` itself — and every
    resulting restore-evidence read is exercised, not just the first one found.
    """
    with dut.saved("x", set_to=1):
        dut.get_int("x")
    R.pass_("T_RT_REFUSED")


def test_runtime_end_to_end():
    print("D2. end-to-end: a real transcript through the real sweep")

    t = _record("T_RT_LEAK", _leaky_body)
    s = CF.sweep("T_RT_LEAK", _leaky_body, t)
    check("D2a: the leaky body goes RED", s.outcome is CF.Outcome.RED, s.outcome)
    check("D2b: and the sweep's OWN byproduct names the leak",
          _kinds(s.restore_leaks) == ["NO_RESTORE_ATTEMPTED"], s.restore_leaks)

    t2 = _record("T_RT_EARLY", _early_restore_body)
    s2 = CF.sweep("T_RT_EARLY", _early_restore_body, t2)
    check("D2c: the early-restore body still goes RED",
          s2.outcome is CF.Outcome.RED, s2.outcome)
    check("D2d: REGRESSION PIN — a manager restore that lands before the "
          "verdict is NOT reported as a leak, end-to-end",
          s2.restore_leaks == [], s2.restore_leaks)

    # D2e — SECOND REGRESSION PIN (T-BUSY-01b's shape): a REFUSE poison on the
    # MUTATING `set` itself must not be read as an established mutation. The
    # body never calls fail() itself, so any FAIL/UNMET observed here can only
    # come from a REFUSE/SILENCE-poisoned exchange aborting the body — exactly
    # the shape that produced the false positive. NOTE: poisoning the
    # RESTORE's OWN exchange (a later position) with REFUSE/SILENCE is a
    # DIFFERENT, legitimate case — the mutation genuinely happened and the
    # set-back genuinely wasn't acked, which is exactly what
    # `RESTORE_ATTEMPTED_UNRECORDED` exists for — so this pin checks for the
    # absence of `NO_RESTORE_ATTEMPTED` specifically, not an empty list.
    t3 = _record("T_RT_REFUSED", _managed_body_no_assertion)
    s3 = CF.sweep("T_RT_REFUSED", _managed_body_no_assertion, t3)
    check("D2e: the body actually reaches a blocking outcome (the poisons "
          "found SOMETHING to break, so the next check is not vacuous — "
          "BP-074)",
          s3.outcome in (CF.Outcome.RED_WITHOUT_ASSERTION, CF.Outcome.RED),
          s3.outcome)
    check("D2f: REGRESSION PIN — a REFUSE (or SILENCE) on the MUTATING `set` "
          "itself is never reported as NO_RESTORE_ATTEMPTED: nothing was ever "
          "mutated, so there is nothing to leak",
          "NO_RESTORE_ATTEMPTED" not in _kinds(s3.restore_leaks),
          s3.restore_leaks)
    check("D2g: ...while a REFUSE/SILENCE on the RESTORE's OWN exchange "
          "(a genuine mutation, an unanswerable set-back) is still reported, "
          "correctly, as RESTORE_ATTEMPTED_UNRECORDED — not silently dropped",
          set(_kinds(s3.restore_leaks)) == {"RESTORE_ATTEMPTED_UNRECORDED"},
          s3.restore_leaks)


# ── D3. check_restore_manager.py's own aggregation ───────────────────────────

def test_runtime_aggregation():
    print("D3. runtime aggregation, filtering and the ledger")

    class _StubSweep:
        def __init__(self, leaks):
            self.restore_leaks = leaks

    class _Leak:
        def __init__(self, var, kind):
            self.var, self.kind = var, kind
            self.poison, self.extent, self.k = CF.Poison.PERTURB, CF.Extent.AT, 0
            self.cmd, self.verdict = f"set {var} 0", R.Verdict.FAIL

        def __str__(self):
            return f"perturb/at @0 `{self.cmd}` (verdict FAIL) -> {self.kind}"

    real_sweep = CF.sweep
    try:
        CF.sweep = lambda tid, fn, t: _StubSweep(
            [_Leak("cooldown", "NO_RESTORE_ATTEMPTED"),
             _Leak("clockStyle", "NO_RESTORE_ATTEMPTED")])
        ev = C.runtime_evidence("T_FAKE", lambda dut: None, object())
        vars_seen = sorted(v for v, _k, _leak in ev)
        check("D3a: SELF_REARMING_VARS (cooldown) is filtered out of the "
              "runtime arm too",
              vars_seen == ["clockStyle"], vars_seen)
    finally:
        CF.sweep = real_sweep

    # D3b — an id with no transcript contributes nothing (census, not a finding).
    leaks, unrecorded = C.runtime_findings({"T1": lambda d: None}, {})
    check("D3b: an unrecorded id is not a finding",
          leaks == {} and unrecorded == {}, (leaks, unrecorded))

    # D3c/d/e — the shrink-only ledger, both directions, exactly like C1-C3.
    check("D3c: an unledgered runtime finding fails",
          len(C.evaluate_runtime({"x": [("T1", "ev")]}, {})[0]) == 1)
    check("D3d: a ledgered runtime finding passes",
          C.evaluate_runtime({"x": [("T1", "ev")]},
                             {"x": ("T1", "l:1")})[0] == [])
    check("D3e: a stale runtime ledger row (no finding left) fails",
          len(C.evaluate_runtime({}, {"x": ("T1", "l:1")})[0]) == 1)

    # D3f — the live corpus: the shipped ledger matches the arm's OWN findings.
    sys.path.insert(0, TOOLS)
    from suite.serialdbg import build_all_tests           # noqa: PLC0415
    tests = build_all_tests()
    transcripts, t_errors = C.load_transcripts()
    check("D3f: the shipped transcript corpus loads with no errors",
          t_errors == [], t_errors)
    leaks, _unrecorded = C.runtime_findings(tests, transcripts)
    rt_ledger, rt_lerrs = C.parse_runtime_ledger()
    check("D3g: the runtime ledger parses with no malformed rows",
          rt_lerrs == [], rt_lerrs)
    check("D3h: the live runtime arm is clean against the shipped ledger",
          C.evaluate_runtime(leaks, rt_ledger)[0] == [],
          C.evaluate_runtime(leaks, rt_ledger)[0])


def main():
    test_checker()
    test_managers()
    test_ratchet()
    test_runtime_unit()
    test_replied_ok()
    test_runtime_end_to_end()
    test_runtime_aggregation()
    print()
    if FAILURES:
        print(f"FAIL: test_check_restore_manager.py — {len(FAILURES)} arm(s) failed: "
              + ", ".join(FAILURES))
        return 1
    print("OK: test_check_restore_manager.py — all arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
