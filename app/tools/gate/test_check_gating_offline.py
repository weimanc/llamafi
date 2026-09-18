#!/usr/bin/env python3
"""test_check_gating_offline.py — the negative suite for TASK-626 / R36.

BP-068. Four subjects, and the middle two are the reason this file is long:

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
  D. the RUNTIME arm (TASK-674): synthetic transcripts exercise the same three
     properties R36's requirements-doc rulings insist on for a runtime gate —
     fires on a genuine recorded dependence, stays quiet on a clean recording
     and on a FEATURE id, and a stale ledger row over a (now-clean) runtime
     finding is itself a failure, exactly like the static arm's C3.

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
from lib import replay as RP                                        # noqa: E402
from app_ids_gen import APP_SLOT                                    # noqa: E402

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


def _transcript(tid, cmds):
    """A minimal Transcript with one exchange per `cmds` entry, in order."""
    t = RP.Transcript(tid, elf="deadbeef", build_env="test", recorded_at="now",
                      gen="0")
    for cmd in cmds:
        t.add(cmd, ["{\"ok\":true}"])
    return t


def _dump(tmpdir, transcripts: dict):
    for tid, t in transcripts.items():
        t.save(os.path.join(tmpdir, f"{tid}.json"))


def test_runtime_arm():
    print("D. the runtime arm (TASK-674)")

    # D1: a genuine recorded dependence FIRES — no closure, read straight off
    # the transcript's own command set.
    tmp = tempfile.mkdtemp(prefix="gateoff_rt_")
    try:
        _dump(tmp, {"T-RT-01": _transcript(
            "T-RT-01", ["get shellBusy", "get chartLen", "tap 10 10"])})
        transcripts, errs = C.load_transcripts(tmp)
        check("D1a: the transcript loads with no errors", errs == [], errs)
        meta = {"T-RT-01": {"cls": "CORE"}}
        found = C.runtime_findings(meta, transcripts)
        check("D1b: a recorded `get chartLen` fires network-key",
              [k for k, _t, _m in found] == ["network-key"], found)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # D2: the clean case — no network key or app switch anywhere in the
    # recording — stays quiet.
    tmp = tempfile.mkdtemp(prefix="gateoff_rt_")
    try:
        _dump(tmp, {"T-RT-02": _transcript(
            "T-RT-02", ["get shellBusy", "tap 10 10",
                        f"switchApp {APP_SLOT['Clock']}"])})
        transcripts, _ = C.load_transcripts(tmp)
        found = C.runtime_findings({"T-RT-02": {"cls": "CORE"}}, transcripts)
        check("D2: a clean recording (incl. a switch to a PASSIVE app) is quiet",
              found == [], found)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # D3: `switchApp <slot>` resolved through the SAME codegen the firmware and
    # suite use (`app_ids_gen.APP_SLOT`), not a hand-kept name table — fires
    # when the slot names a NETWORK_APPS app.
    tmp = tempfile.mkdtemp(prefix="gateoff_rt_")
    try:
        _dump(tmp, {"T-RT-03": _transcript(
            "T-RT-03", [f"switchApp {APP_SLOT['Weather']}"])})
        transcripts, _ = C.load_transcripts(tmp)
        found = C.runtime_findings({"T-RT-03": {"cls": "HEALTH"}}, transcripts)
        check("D3: a recorded switchApp to Weather fires network-app",
              [k for k, _t, _m in found] == ["network-app"], found)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # D4: a FEATURE id may depend on whatever it likes — same rule as B2, at
    # runtime.
    tmp = tempfile.mkdtemp(prefix="gateoff_rt_")
    try:
        _dump(tmp, {"T-RT-04": _transcript("T-RT-04", ["get chartLen"])})
        transcripts, _ = C.load_transcripts(tmp)
        found = C.runtime_findings({"T-RT-04": {"cls": "FEATURE"}}, transcripts)
        check("D4: a FEATURE id's recorded network key is not policed",
              found == [], found)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # D5: an id with NO transcript contributes nothing — it is a census line
    # (UNRECORDED), never a finding. `runtime_findings` must not synthesise
    # one from meta alone.
    found = C.runtime_findings({"T-RT-05": {"cls": "CORE"}}, {})
    check("D5: an unrecorded gating id is not a finding", found == [], found)

    # D6: a runtime-only finding is caught by the SAME ledger/evaluate path as
    # the static arm — one requirement, one ledger, not a parallel mechanism.
    rt_found = [("network-key", "T-RT-06", "…")]
    check("D6a: an unledgered runtime finding fails",
          len(C.evaluate(rt_found, {})[0]) == 1, C.evaluate(rt_found, {}))
    led = {("network-key", "T-RT-06"): "l:1"}
    check("D6b: a ledgered runtime finding passes",
          C.evaluate(rt_found, led)[0] == [], C.evaluate(rt_found, led))

    # D7: a stale ledger row over a runtime finding that no longer occurs is
    # itself a failure — the ledger can only shrink, same as C3.
    check("D7: a stale row for a runtime-only kind fails as STALE",
          len(C.evaluate([], led)[0]) == 1, C.evaluate([], led))

    # D8: a transcript file whose recorded id does not match its filename is
    # refused by the loader (same shape check_can_go_red's loader makes).
    tmp = tempfile.mkdtemp(prefix="gateoff_rt_")
    try:
        _transcript("T-WRONG-ID", ["get chartLen"]).save(
            os.path.join(tmp, "T-RT-08.json"))
        transcripts, errs = C.load_transcripts(tmp)
        check("D8: a filename/id mismatch is refused, not silently accepted",
              transcripts == {} and len(errs) == 1, (transcripts, errs))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # D9: the live corpus's runtime arm is clean against the shipped ledger —
    # same invariant as C11, for the mechanism that reads transcripts instead
    # of source.
    live_meta = C._load_meta()
    live_transcripts, live_errs = C.load_transcripts()
    check("D9a: the shipped transcript corpus loads with no errors",
          live_errs == [], live_errs)
    live_rt = C.runtime_findings(live_meta, live_transcripts)
    ledger, _ = C.parse_ledger()
    check("D9b: the live runtime arm is clean against the shipped ledger",
          C.evaluate(live_rt, ledger)[0] == [], C.evaluate(live_rt, ledger)[0])


def main():
    test_fires()
    test_stays_quiet()
    test_ledger_and_live()
    test_runtime_arm()
    print()
    if FAILURES:
        print(f"FAIL: test_check_gating_offline.py — {len(FAILURES)} arm(s) "
              f"failed: " + ", ".join(FAILURES))
        return 1
    print("OK: test_check_gating_offline.py — all arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
