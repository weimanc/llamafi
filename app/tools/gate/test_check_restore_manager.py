#!/usr/bin/env python3
"""test_check_restore_manager.py — the negative suite for TASK-602's two halves.

BP-068: a gate without a negative test is not a gate. BP-074: an assertion whose
precondition never occurred is inconclusive, not a pass — so every arm constructs
the violation it claims to catch and asserts the finding CODE, not a non-empty
list.

Three subjects:

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

No DUT, no serial port, no network. The Dut is never constructed: the manager arms
drive unbound methods against a stub (R48 / TASK-609).

    python3 app/tools/gate/test_check_restore_manager.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_restore_manager as C                                   # noqa: E402
from lib.dut import Dut, BadField, NoAnswer, RestoreFailed          # noqa: E402

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


def main():
    test_checker()
    test_managers()
    test_ratchet()
    print()
    if FAILURES:
        print(f"FAIL: test_check_restore_manager.py — {len(FAILURES)} arm(s) failed: "
              + ", ".join(FAILURES))
        return 1
    print("OK: test_check_restore_manager.py — all arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
