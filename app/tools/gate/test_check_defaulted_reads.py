#!/usr/bin/env python3
"""test_check_defaulted_reads.py — the negative suite for TASK-596's two halves.

BP-068: a gate without a negative test is not a gate. BP-074: an assertion whose
precondition never occurred is inconclusive, not a pass — so every arm here
constructs the violation it claims to catch and asserts the finding CODE, not
merely a non-empty finding list. A test that asserted `findings != []` would pass
on a checker that reported one wrong thing about everything.

Two subjects, because TASK-596 shipped two mechanisms:

  A. the CHECKER (`check_defaulted_reads.py`) — does it see a defaulted reply
     read, does it ignore a plain dict, does the ratchet bite in both directions.
  B. the ACCESSOR (`lib.dut.Dut.get_*`) — does it RAISE where the old code
     returned a passing default, and does it raise the RIGHT exception, since the
     whole design rests on NoAnswer -> UNMET and BadField -> FAIL being different
     verdicts.

  C. the REGRESSION ITSELF (`G-2`) — the proof that the Stock fetch oracle can no
     longer be satisfied by a failed read. This is the arm that matters: A and B
     assert the machinery exists, C asserts what it was for.

No DUT, no serial port, no network. The Dut used here is never constructed — the
accessor arms drive an unbound method against a stub, so importing this file
cannot open a port (R48 / TASK-609).

    python3 app/tools/gate/test_check_defaulted_reads.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_defaulted_reads as C                                   # noqa: E402
from lib.dut import Dut, BadField, NoAnswer                         # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def codes(findings):
    return sorted({f.split()[0] for f in findings})


# ── A. the checker ───────────────────────────────────────────────────────────

SRC_VIOLATION = '''
def t(dut):
    r = dut.cmd("get fetchOkCount")
    return int(r.get("val", -1))
'''

SRC_HELPER_VIOLATION = '''
def t(dut):
    r = _stock_get(dut, "chartLen")
    return r.get("val", 0)
'''

SRC_CLEAN = '''
def t(dut):
    return dut.get_int("fetchOkCount")
'''

SRC_NOT_A_REPLY = '''
def t(meta):
    rec = REGISTRY[meta]
    return rec.get("cls", "FEATURE")
'''

SRC_ONE_ARG = '''
def t(dut):
    r = dut.cmd("get stockSubView")
    return r.get("val") == "list"
'''

SRC_LOOP_VAR = '''
def t(dut):
    for r in dut.read_json_multi():
        if r.get("ok", False):
            return r
'''


def test_checker():
    print("A. the checker")
    check("a defaulted reply read is counted",
          [k for _, k in C.defaulted_reads(SRC_VIOLATION)] == ["val"],
          C.defaulted_reads(SRC_VIOLATION))
    check("a defaulted read through the _stock_get pass-through is counted",
          len(C.defaulted_reads(SRC_HELPER_VIOLATION)) == 1)
    check("a typed read is not counted",
          C.defaulted_reads(SRC_CLEAN) == [])
    check("a default on a NON-reply dict is not counted",
          C.defaulted_reads(SRC_NOT_A_REPLY) == [])
    check("a ONE-arg .get() is not counted (None is the failing direction)",
          C.defaulted_reads(SRC_ONE_ARG) == [])
    check("a reply bound by a for-loop target is tainted",
          len(C.defaulted_reads(SRC_LOOP_VAR)) == 1)

    # The ratchet, both directions.
    check("D1: over cap is a finding",
          codes(C.evaluate({"suite/x.py": 4}, {"suite/x.py": (3, "l:1")})) == ["D1"])
    check("D1: no row at all means cap 0",
          codes(C.evaluate({"suite/x.py": 1}, {})) == ["D1"])
    check("at cap is clean",
          C.evaluate({"suite/x.py": 3}, {"suite/x.py": (3, "l:1")}) == [])
    check("D2: UNDER cap is ALSO a finding — the ledger must be lowered",
          codes(C.evaluate({"suite/x.py": 1}, {"suite/x.py": (3, "l:1")})) == ["D2"])
    check("D3: a row for a module that does not exist is a finding",
          codes(C.evaluate({}, {"suite/gone.py": (3, "l:1")})) == ["D3"])
    check("D5: lib/ may not be ledgered at all",
          "D5" in codes(C.evaluate({"lib/dut.py": 2}, {"lib/dut.py": (5, "l:1")})),
          C.evaluate({"lib/dut.py": 2}, {"lib/dut.py": (5, "l:1")}))
    check("zero everywhere with no ledger is clean",
          C.evaluate({"suite/x.py": 0}, {}) == [])

    # D4 — the ledger's own shape. Driven through parse_ledger with fixtures.
    import tempfile
    for body, want in (
        ("| `suite/x.py` | 3 | TASK-596 | 2026-09-04 |", []),
        ("| `suite/*.py` | 3 | TASK-596 | 2026-09-04 |", ["D4"]),
        ("| `suite/x.py` | many | TASK-596 | 2026-09-04 |", ["D4"]),
        ("| `suite/x.py` | 3 | somebody | 2026-09-04 |", ["D4"]),
        ("| `suite/x.py` | 3 | TASK-596 | soon |", ["D4"]),
    ):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("| module | cap | owner | since |\n|---|---|---|---|\n" + body + "\n")
            p = fh.name
        rows, errs = C.parse_ledger(p)
        os.unlink(p)
        check(f"D4 ledger shape: {body[:34]!r}...",
              codes(errs) == want and (bool(rows) == (want == [])),
              (rows, errs))

    # An absent ledger must fail CLOSED, not grandfather everything.
    rows, errs = C.parse_ledger(os.path.join(TOOLS, "no-such-ledger.md"))
    check("an absent ledger parses to zero rows (fails closed)",
          rows == {} and errs == [])
    check("...and with zero rows a real count is a D1",
          codes(C.evaluate({"suite/x.py": 1}, rows)) == ["D1"])

    # The live tree is the ratchet's own fixture: it must be clean right now,
    # otherwise every arm above is testing a checker nobody could land.
    counts = C.scan()
    ledger, lerrs = C.parse_ledger()
    check("the live tree is within its ratchet",
          C.evaluate(counts, ledger) == [] and lerrs == [],
          lerrs + C.evaluate(counts, ledger))
    check("lib/ is at zero and stays there",
          all(v == 0 for k, v in counts.items() if k.startswith("lib/")),
          {k: v for k, v in counts.items() if k.startswith("lib/") and v})


# ── B. the accessor ──────────────────────────────────────────────────────────

class _StubDut:
    """A Dut-shaped object that answers from a canned reply list. Never opens a
    port; `Dut.get_int` etc. are called as unbound methods against it, so what is
    under test is the SHIPPED code, not a copy of it."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.sent = []

    def send(self, cmd):
        self.sent.append(cmd)

    def read_json(self, timeout=3.0):
        if not self._replies:
            raise TimeoutError("stub: nothing left")
        return self._replies.pop(0)

    # the methods under test, bound to this stub
    def cmd(self, cmd_str, timeout=3.0, drain_shell_cooldown=True):
        self.send(cmd_str)
        return self.read_json(timeout)

    read_reply = Dut.read_reply
    get_val = Dut.get_val
    get_int = Dut.get_int
    get_str = Dut.get_str
    get_bool = Dut.get_bool
    get_float = Dut.get_float
    set_val = Dut.set_val


class _NoSleep:
    """`time` with `sleep` neutered; everything else (monotonic) delegates."""

    def __init__(self, real):
        self._real = real

    def sleep(self, s):
        # NOT a no-op: the poll loops are bounded by monotonic(), so a zero sleep
        # spins them 20 000 times and costs MORE than the real 1 s tick. Compress
        # instead — the loop still ticks, several times, in milliseconds.
        self._real.sleep(min(s, 0.005))

    def __getattr__(self, name):
        return getattr(self._real, name)


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception as e:
        return f"wrong exception: {type(e).__name__}: {e}"
    return "no exception raised"


def test_accessor():
    print("B. the accessor")
    ok = {"ok": True, "cmd": "get", "var": "fetchOkCount", "val": 7}

    check("a good read returns the value",
          Dut.get_int(_StubDut([ok]), "fetchOkCount") == 7)

    check("NO reply at all -> NoAnswer (premise unestablished -> UNMET)",
          raises(lambda: Dut.get_int(_StubDut([]), "fetchOkCount"), NoAnswer) is True)

    # THE RACED REPLY — WP-C's hazard and G-2's stated trigger. read_json returns
    # the FIRST json line; under the stock quote flood that line is somebody
    # else's answer. Correlation must reject it rather than adjudicate it.
    other = {"ok": True, "cmd": "get", "var": "quoteOkCount", "val": 999}
    check("a reply for a DIFFERENT var is not accepted as this var's answer",
          raises(lambda: Dut.get_int(_StubDut([other]), "fetchOkCount"), NoAnswer) is True)
    check("...but a later correctly-labelled reply IS found behind it",
          Dut.get_int(_StubDut([other, ok]), "fetchOkCount") == 7)

    check("ok:false (renamed/deleted debug key) -> BadField (a real defect -> FAIL)",
          raises(lambda: Dut.get_int(
              _StubDut([{"ok": False, "cmd": "get", "var": "fetchOkCount",
                         "error": "unknown var"}]), "fetchOkCount"), BadField) is True)
    check("a reply with no `val` field -> BadField",
          raises(lambda: Dut.get_int(
              _StubDut([{"ok": True, "var": "fetchOkCount"}]), "fetchOkCount"),
              BadField) is True)
    check("val:null -> BadField",
          raises(lambda: Dut.get_int(
              _StubDut([{"ok": True, "var": "fetchOkCount", "val": None}]),
              "fetchOkCount"), BadField) is True)
    check("a string where an int was asked for -> BadField",
          raises(lambda: Dut.get_int(
              _StubDut([{"ok": True, "var": "x", "val": "list"}]), "x"), BadField) is True)
    check("a bool where an int was asked for -> BadField (JSON true is not 1)",
          raises(lambda: Dut.get_int(
              _StubDut([{"ok": True, "var": "x", "val": True}]), "x"), BadField) is True)
    check("an int where a str was asked for -> BadField",
          raises(lambda: Dut.get_str(
              _StubDut([{"ok": True, "var": "x", "val": 3}]), "x"), BadField) is True)
    check("get_bool accepts true/false and 0/1, rejects 2",
          Dut.get_bool(_StubDut([{"ok": True, "var": "x", "val": False}]), "x") is False
          and Dut.get_bool(_StubDut([{"ok": True, "var": "x", "val": 1}]), "x") is True
          and raises(lambda: Dut.get_bool(
              _StubDut([{"ok": True, "var": "x", "val": 2}]), "x"), BadField) is True)
    check("a non-`val` field is readable and typed",
          Dut.get_int(_StubDut([{"ok": True, "var": "lastPlaylistDraw", "ms": 42}]),
                      "lastPlaylistDraw", field="ms") == 42)
    check("a reply with NO `var` is accepted (correlation is best-effort)",
          Dut.get_int(_StubDut([{"ok": True, "val": 5}]), "anything") == 5)

    # R18's restore clause: a `set` nobody acknowledged is not a restore.
    check("set_val raises when the device refuses the write",
          raises(lambda: Dut.set_val(
              _StubDut([{"ok": False, "cmd": "set", "var": "stockMode"}]),
              "stockMode", 0), BadField) is True)
    check("set_val raises when nothing answers the write",
          raises(lambda: Dut.set_val(_StubDut([]), "stockMode", 0), NoAnswer) is True)

    # There must be no way to ask for a default back.
    check("there is no try_get_* / default= escape hatch on Dut",
          not [n for n in dir(Dut) if n.startswith("try_get")]
          and "default" not in Dut.get_val.__code__.co_varnames)


# ── C. G-2 itself ────────────────────────────────────────────────────────────

def test_g2_regression():
    print("C. G-2 — the Stock fetch oracle cannot be satisfied by a failed read")
    import suite.serialdbg._helpers as H
    from suite.serialdbg._helpers import _stock_ok_count, _wait_chart_complete
    # The poll loops sleep 1 s per tick against a stub that answers instantly;
    # that is 4 s of wall clock inside run/check for no added coverage. Only the
    # sleeps are stubbed — monotonic() is untouched, so the loops' own deadlines
    # still govern and the arms below still exercise the real control flow.
    H.time = _NoSleep(H.time)

    # (1) The bad read no longer produces a number.
    check("_stock_ok_count RAISES on a bad read instead of returning -1",
          raises(lambda: _stock_ok_count(
              _StubDut([{"ok": False, "cmd": "get", "var": "fetchOkCount"}])),
              BadField) is True)
    check("_stock_ok_count RAISES when nothing answers",
          raises(lambda: _stock_ok_count(_StubDut([])), NoAnswer) is True)

    # (2) And the oracle refuses the sentinel even if a caller invents one. This
    #     is the arm that fails on the pre-TASK-585 tree: `_wait_chart_complete(-1)`
    #     returned True on its first poll, with a real counter of 3 and no fetch.
    class _CountingStub(_StubDut):
        """Answers every `get` with val=3, correctly labelled — a HEALTHY device
        whose counter simply has not moved. That is the case G-2 turned green."""

        def __init__(self):
            super().__init__([])
            self.polls = 0

        def read_json(self, timeout=3.0):
            self.polls += 1
            var = self.sent[-1][4:].strip().split()[0] if self.sent else "?"
            return {"ok": True, "cmd": "get", "var": var, "val": 3}

    stub = _CountingStub()
    check("_wait_chart_complete(-1) REFUSES the sentinel baseline",
          raises(lambda: _wait_chart_complete(stub, -1, timeout_s=0.1), ValueError) is True)
    check("...and it did so without polling the device into a false pass",
          stub.polls == 0, stub.polls)

    # (3) A real baseline still works exactly as before: no advance -> False.
    stub2 = _CountingStub()
    check("a real baseline equal to the current count does NOT pass",
          _wait_chart_complete(stub2, 3, timeout_s=0.1) is False)
    stub3 = _CountingStub()
    check("a real baseline below the current count DOES pass",
          _wait_chart_complete(stub3, 2, timeout_s=0.1) is True)


def main():
    print("test_check_defaulted_reads.py — TASK-596 / TASK-585 negative suite\n")
    test_checker()
    test_accessor()
    test_g2_regression()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} arm(s) failed: {', '.join(FAILURES)}")
        return 1
    print("OK: test_check_defaulted_reads.py — all arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
