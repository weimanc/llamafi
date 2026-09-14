#!/usr/bin/env python3
"""test_check_gating_offline.py — the negative suite for TASK-626 / R36.

BP-068. Three subjects, and the middle one is the reason this file is long:

  A. the checker FIRES on each of the four dependences, through a HELPER — the
     shape a body-level grep misses and the only reason the closure walk exists.
  B. the checker does NOT fire on the near misses. Every one of these was a live
     false positive during development, and each would have accused a clean id:
       * comparing `get appId`'s name against "WebRadio" is not driving WebRadio
         (`_restore_spotify` does this, and eight gating ids call it);
       * a DOCSTRING that explains a fetch is not a fetch (one shared diagnostic
         helper's docstring names `fetchOkCount`, `chartLen` and
         `stockChartProgress` in prose, and it is reached from most of the
         corpus);
       * a FEATURE id may depend on whatever it likes.
     A gate that cannot be shown to stay quiet is a gate that will be turned off.
  C. the live tree — the eight ids, the zero, and the ledger arithmetic — so the
     numbers in the ledger document are the gate's own and cannot drift from it.

No DUT, no serial port, no network.

    python3 app/tools/gate/test_check_gating_offline.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_gating_offline as C                                    # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


class Pkg:
    """A throwaway `suite/serialdbg`-shaped package of one module."""

    def __init__(self, src):
        self.dir = tempfile.mkdtemp(prefix="gateoff_")
        with open(os.path.join(self.dir, "fam.py"), "w") as fh:
            fh.write(src)

    def findings(self, cls="CORE", tid="T-X-01"):
        fns, reg = C.load_package(self.dir)
        return C.findings({tid: {"cls": cls}}, fns, reg)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        shutil.rmtree(self.dir, ignore_errors=True)


def kinds(found):
    return sorted({k for k, _t, _m in found})


HELPER_DEEP = '''
def _leaf(dut):
    dut.cmd("get chartLen")

def _mid(dut):
    _leaf(dut)

def t_x_01(dut):
    _mid(dut)

TESTS = {"T-X-01": t_x_01}
'''

CLEAN = '''
def t_x_01(dut):
    dut.cmd("get shellBusy")
    dut.cmd("tap 100 100")

TESTS = {"T-X-01": t_x_01}
'''


def test_fires():
    print("A. the checker fires")
    with Pkg(HELPER_DEEP) as p:
        check("A1: a network key TWO helpers deep is found",
              kinds(p.findings()) == ["network-key"], p.findings())
    with Pkg('''
def t_x_01(dut):
    _wait_chart_complete(dut, 0)

def _wait_chart_complete(dut, before):
    pass

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("A2: a blocking network helper is found",
              kinds(p.findings()) == ["network-helper"], p.findings())
    with Pkg('''
def t_x_01(dut):
    dut.wait_for_queue(min_count=2, timeout=30.0)

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("A3: a live-Spotify precondition (a Dut METHOD, not a package "
              "function) is found",
              kinds(p.findings()) == ["network-helper"], p.findings())
    with Pkg('''
def t_x_01(dut):
    _switch_to(dut, "Weather")

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("A4: an app that fetches on activation is found",
              kinds(p.findings()) == ["network-app"], p.findings())
    with Pkg('''
APP_SLOT = {}
def t_x_01(dut):
    apps = [(n, APP_SLOT[n]) for n in ["Clock", "Weather", "Crypto"]]
    for name, slot in apps:
        dut.cmd(f"switchApp {slot}")

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("A5: a DYNAMIC APP_SLOT lookup — T-BUSY-03's shape — is found",
              kinds(p.findings()) == ["network-app"], p.findings())
    with Pkg('''
import os
def t_x_01(dut):
    if not os.path.exists("lib/SpotifyArduino"):
        fail("T-X-01", "no")

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("A6: B-2's host-file-layout shape is found",
              kinds(p.findings()) == ["host-file-layout"], p.findings())


def test_stays_quiet():
    print("B. the checker stays quiet")
    with Pkg(CLEAN) as p:
        check("B1: control — an offline-satisfiable body is clean",
              p.findings() == [], p.findings())
    with Pkg(HELPER_DEEP) as p:
        check("B2: a FEATURE id may depend on whatever it likes",
              p.findings(cls="FEATURE") == [], p.findings(cls="FEATURE"))
    with Pkg('''
def _restore_spotify(dut):
    r = dut.cmd("get appId")
    if r.get("name") in ("WebRadio", "LocalPlayer"):
        _tb_set_offset(dut, 0)
    return True

def t_x_01(dut):
    _restore_spotify(dut)

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("B3: COMPARING against an app name is not driving that app",
              p.findings() == [], p.findings())
    with Pkg('''
def _snapshot(dut):
    """Diagnostic snapshot. Compare fetchOkCount and chartLen against the
    clean-boot baseline; stockChartProgress tells queued from parked."""
    return ""

def t_x_01(dut):
    _snapshot(dut)

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("B4: a DOCSTRING naming fetch keys is not a fetch",
              p.findings() == [], p.findings())
    with Pkg('''
APP_SLOT = {}
def t_x_01(dut):
    x, y = tap_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {x} {y}")

TESTS = {"T-X-01": t_x_01}
''') as p:
        check("B5: a CONSTANT APP_SLOT lookup for a passive app is clean",
              p.findings() == [], p.findings())


def test_ledger_and_live():
    print("C. the ledger and the live tree")
    found = [("network-key", "T-A", "…"), ("network-app", "T-A", "…")]
    fails, used = C.evaluate(found, {})
    check("C1: an unledgered finding fails", len(fails) == 2 and used == 0, fails)
    led = {("network-key", "T-A"): "l:1", ("network-app", "T-A"): "l:2"}
    check("C2: a ledgered finding passes", C.evaluate(found, led)[0] == [], led)
    check("C3: a row whose finding is gone fails as STALE",
          len(C.evaluate([], led)[0]) == 2, C.evaluate([], led)[0])
    check("C4: a row does not cover the same id under another kind",
          len(C.evaluate([("network-helper", "T-A", "…")],
                         {("network-key", "T-A"): "l:1"})[0]) == 2)

    # `host-file-layout` is NOT exemptable, and that has to be enforced by the
    # PARSER, not by nobody having written the row.
    tmp = tempfile.mkdtemp(prefix="gateoff_led_")
    path = os.path.join(tmp, "l.md")
    with open(path, "w") as fh:
        fh.write("| id | kind | why | owner | since |\n|---|---|---|---|---|\n"
                 "| `T133` | host-file-layout | x | TASK-617 | 2026-09-05 |\n")
    rows, errs = C.parse_ledger(path)
    check("C5: a host-file-layout row is REFUSED by the parser",
          rows == {} and len(errs) == 1, (rows, errs))
    with open(path, "w") as fh:
        fh.write("| id | kind | why | owner | since |\n|---|---|---|---|---|\n"
                 "| `T133` | network-key | x | nobody | 2026-09-05 |\n"
                 "| `T134` | network-key | x | TASK-617 | soon |\n")
    rows, errs = C.parse_ledger(path)
    check("C6: a row without a TASK owner and an ISO date is refused",
          rows == {} and len(errs) == 2, (rows, errs))
    shutil.rmtree(tmp, ignore_errors=True)

    meta = C._load_meta()
    fns, reg = C.load_package()
    live = C.findings(meta, fns, reg)
    ids = sorted({t for _k, t, _m in live})
    # C7/C8 used to assert the eight ids of the 2026-09-05 measurement were all
    # still reported. That is a census frozen as a literal, and it went red on
    # 2026-09-06 for the one change it should have been happiest about: the
    # human's TASK-626 rulings, which demoted five of the eight out of CORE, split
    # `T-CDWN-02`'s live-Yahoo half off, and re-pointed `T-BUSY-03` at the four
    # passive apps. A positive control that fails when the finding it describes is
    # FIXED teaches the next person to delete the control. The two arms below
    # assert the invariants instead: what the ruling removed stays removed, and
    # the live set and the ledger are the same set.
    RULED_OUT = {"T-BUSY-01", "T-BUSY-01b", "T-BUSY-05", "T-CDWN-03",
                 "T-BUSY-03", "T_X07_01"}
    check("C7: the six ids ruled on 2026-09-06 no longer report — demotions, a "
          "split and a re-point, not a ledger edit",
          not (set(ids) & RULED_OUT), sorted(set(ids) & RULED_OUT))
    check("C8: the live findings and the shipped ledger name the SAME ids — a "
          "finding off the ledger, or a row with no finding, is the failure",
          set(ids) == {k[1] for k in C.parse_ledger()[0]},
          (ids, sorted({k[1] for k in C.parse_ledger()[0]})))
    check("C9: the host-file-layout count is ZERO (T133's demotion held)",
          [f for f in live if f[0] == "host-file-layout"] == [],
          [f[1] for f in live if f[0] == "host-file-layout"])
    ledger, lerrs = C.parse_ledger()
    check("C10: the shipped ledger parses clean", lerrs == [], lerrs)
    check("C11: the live tree is clean against its ledger",
          C.evaluate(live, ledger)[0] == [], C.evaluate(live, ledger)[0])
    # Inverted 2026-09-14: T_BI_03's demotion took the live count to zero. The
    # arm now pins the MET state, so a new gating id that needs the network
    # fails here as a regression of TASK-617 (ii), not only as a ledger row.
    check("C12: TASK-617's exit criterion (ii) is MET — no gating id needs the "
          "outside world", len(ids) == 0, ids)


def main():
    test_fires()
    test_stays_quiet()
    test_ledger_and_live()
    print()
    if FAILURES:
        print(f"FAIL: test_check_gating_offline.py — {len(FAILURES)} arm(s) "
              f"failed: " + ", ".join(FAILURES))
        return 1
    print("OK: test_check_gating_offline.py — all arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
