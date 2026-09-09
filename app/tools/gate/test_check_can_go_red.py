#!/usr/bin/env python3
"""test_check_can_go_red.py — negative suite for the runtime R34 gate (TASK-671).

Everything here is host-only and needs no board: synthetic bodies are recorded
through the REAL `RecordingSerial` off a scripted device (the same fixture shape
as `lib/test_replay.py`), and the REAL sweep, dispatch arms and gate evaluation
run over the recordings. The bodies are the shapes the gate exists to tell apart:

  honest       typed reads, `fail()` on its subject                -> RED
  inverted     `C-1`'s shape over a typed read: the guard can never
               be true, but DROP trips the BadField arm            -> RED-WITHOUT-ASSERTION (contract)
  skipper      `D-2`'s shape: every deviation is a skip()          -> NEVER-RED
  pair         guard over two reads of one key, AND a later read
               that must stay healthy for the fail() to be reached -> RED, only via AT
  crasher      raw `cmd()`, `r["val"]`, no fail()                  -> RED-WITHOUT-ASSERTION (accident)
  flaker       every non-pass exit is `flake()`, undeclared        -> RED-WITHOUT-ASSERTION (accident/policy)
  contract     typed read only, nothing compared                   -> RED-WITHOUT-ASSERTION (contract)
  unhealthy    recorded from a device that made the body SKIP      -> BASELINE-NOT-PASS

Then the gate's own logic — ledger parsing, stale rows, wrong-outcome rows,
archived owners, the transcript loader — and the MUTATION ARM: the poisons are
replaced with the identity and the RED body must stop being RED (R10's
verification clause). A sweep that still reports RED with no poison applied is
a sweep that reports RED for free.

    python3 app/tools/gate/test_check_can_go_red.py [-v]
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

from lib import canfail as CF                                   # noqa: E402
from lib import replay as RP                                    # noqa: E402
from lib import results as R                                    # noqa: E402
from lib.dut import DeviceReadError, Dut                        # noqa: E402
import check_can_go_red as G                                    # noqa: E402

FAILURES: list = []
VERBOSE = "-v" in sys.argv


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'BAD '}{name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


# ── the scripted device and the real recorder ────────────────────────────────

class Device:
    def __init__(self, app="Clock", x=5):
        self.app, self.x = app, x

    def handle(self, line):
        w = line.split()
        if w[:2] == ["get", "x"]:
            return [{"ok": True, "var": "x", "val": self.x}]
        if w[:2] == ["get", "appId"]:
            return [{"ok": True, "var": "appId", "val": 3, "name": self.app}]
        if w[:2] == ["get", "shellCooldown"]:
            return [{"ok": True, "var": "shellCooldown", "remainingMs": 0}]
        return [{"ok": True, "cmd": w[0] if w else "?"}]


class FakeSerial:
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

    def gen_tag(self):
        return "g1"


def record(tid, body, device=None):
    clock = RP.VirtualClock()
    d = object.__new__(Dut)
    d.ser = FakeSerial(device or Device(), clock)
    d._owner_thread = threading.current_thread()
    d.port, d.elf, d.elf_expected, d.build_env = "fake", "ab", "ab", "e"
    R.RESULTS.clear()
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        with RP.virtual_time(clock):
            with RP.recording(d, tid) as rec:
                body(d)
    R.RESULTS.clear()
    return rec.transcript


# ── the bodies ───────────────────────────────────────────────────────────────

def honest(dut):
    if dut.get_str("appId", field="name") != "Clock":
        R.fail("T_CGR_01", "wrong app"); return
    if dut.get_int("x") != 5:
        R.fail("T_CGR_01", "x"); return
    R.pass_("T_CGR_01")


def inverted(dut):
    v = dut.get_int("x")
    if v != v:                       # C-1: passes exactly on the regression
        R.fail("T_CGR_02", "unreachable"); return
    R.pass_("T_CGR_02")


def skipper(dut):
    try:
        v = dut.get_int("x")
    except DeviceReadError:
        R.skip("T_CGR_03", "n/a"); return
    if v != 5:
        R.skip("T_CGR_03", "board not in state"); return
    if v == 5 and v != 5:
        R.fail("T_CGR_03", "impossible")
    R.pass_("T_CGR_03")


def pair(dut):
    a = dut.get_int("x")
    b = dut.get_int("x")
    on_clock = dut.get_str("appId", field="name") == "Clock"
    if a != b and on_clock:
        R.fail("T_CGR_04", "x moved"); return
    R.pass_("T_CGR_04")


def crasher(dut):
    r = dut.cmd("get x")
    if r["val"] == 5:
        R.pass_("T_CGR_05")
    else:
        R.skip("T_CGR_05", "n/a")


def flaker(dut):
    r = dut.cmd("get x")
    if r.get("val") != 5:
        R.flake("T_CGR_06", "jitter"); return
    R.pass_("T_CGR_06")


def contract(dut):
    dut.get_int("x")
    R.pass_("T_CGR_07")


from lib.results import fail as _fail_by_name, pass_ as _pass_by_name   # noqa: E402


def byname(dut):
    """`honest`, but with fail/pass_ imported BY NAME the way every real suite
    module does it. The first real recording graded zero assertions because the
    witness rebound `results.fail` and never saw these calls."""
    if dut.get_int("x") != 5:
        _fail_by_name("T_CGR_10", "x"); return
    _pass_by_name("T_CGR_10")


def unhealthy(dut):
    if dut.get_str("appId", field="name") != "Clock":
        R.skip("T_CGR_08", "not on Clock"); return
    R.pass_("T_CGR_08")


BODIES = {"T_CGR_01": honest, "T_CGR_02": inverted, "T_CGR_03": skipper,
          "T_CGR_04": pair, "T_CGR_05": crasher, "T_CGR_06": flaker,
          "T_CGR_07": contract, "T_CGR_08": unhealthy, "T_CGR_10": byname}

LEDGER_HEAD = ("# ledger\n\n| id | outcome | why | owner | since |\n|---|---|---|---|---|\n")


def write_root(rows: str, archive: str = "") -> str:
    root = tempfile.mkdtemp(prefix="cgr_")
    (pathlib.Path(root) / "docs" / "verification").mkdir(parents=True)
    (pathlib.Path(root) / "docs" / "project").mkdir(parents=True)
    (pathlib.Path(root) / G.LEDGER_REL).write_text(LEDGER_HEAD + rows)
    (pathlib.Path(root) / "docs" / "project" / "tasks-archive.md").write_text(archive)
    return root


def main() -> int:
    print("TASK-671 can-go-red gate — negative suite\n")

    print("A — the sweep on the eight shapes")
    ts = {tid: record(tid, b) for tid, b in BODIES.items() if tid != "T_CGR_08"}
    ts["T_CGR_08"] = record("T_CGR_08", unhealthy, Device(app="Weather"))
    sw = {tid: CF.sweep(tid, BODIES[tid], ts[tid]) for tid in BODIES}
    for s in sw.values():
        if VERBOSE:
            print(s.line())
    RWA = CF.Outcome.RED_WITHOUT_ASSERTION
    want = {"T_CGR_01": CF.Outcome.RED, "T_CGR_02": RWA,
            "T_CGR_03": CF.Outcome.NEVER_RED, "T_CGR_04": CF.Outcome.RED,
            "T_CGR_05": RWA, "T_CGR_06": RWA, "T_CGR_07": RWA,
            "T_CGR_08": CF.Outcome.BASELINE_NOT_PASS, "T_CGR_10": CF.Outcome.RED}
    for tid, o in want.items():
        check(f"A {tid} ({BODIES[tid].__name__}) -> {o.value}",
              sw[tid].outcome is o, sw[tid].line().strip())
    check("A honest's evidence is an ASSERTION under PERTURB",
          sw["T_CGR_01"].evidence.grade is CF.Grade.ASSERTION
          and sw["T_CGR_01"].evidence.poison is CF.Poison.PERTURB,
          str(sw["T_CGR_01"].evidence))
    check("A pair went red via the AT extent", sw["T_CGR_04"].evidence.extent is CF.Extent.AT,
          str(sw["T_CGR_04"].evidence))
    check("A inverted's only red is CONTRACT (the typed read it never looks at)",
          sw["T_CGR_02"].grades[CF.Grade.CONTRACT] > 0
          and sw["T_CGR_02"].grades[CF.Grade.ACCIDENT] == 0
          and sw["T_CGR_02"].grades[CF.Grade.POLICY] == 0, sw["T_CGR_02"].line().strip())
    check("A contract-only body is graded CONTRACT, never ASSERTION",
          sw["T_CGR_07"].grades[CF.Grade.CONTRACT] > 0 and "contract" in sw["T_CGR_07"].detail,
          sw["T_CGR_07"].line().strip())
    check("A crasher recorded ACCIDENT only; flaker recorded ACCIDENT and POLICY",
          sw["T_CGR_05"].grades[CF.Grade.POLICY] == 0
          and sw["T_CGR_05"].grades[CF.Grade.ACCIDENT] > 0
          and sw["T_CGR_06"].grades[CF.Grade.POLICY] > 0
          and sw["T_CGR_06"].grades[CF.Grade.ACCIDENT] > 0)
    for tid in ("T_CGR_02", "T_CGR_03", "T_CGR_07"):
        check(f"A {tid}'s search was exhaustive (1 + 8 poison/extent x N positions)",
              sw[tid].replays == 1 + 8 * sw[tid].n_exchanges,
              f"{sw[tid].replays} replays, {sw[tid].n_exchanges} exchanges")

    print("\nB — the same body, ONWARD-only order cannot see pair (why AT exists)")
    onward_only = tuple(pe for pe in CF.ORDER if pe[1] is CF.Extent.ONWARD)
    s = CF.sweep("T_CGR_04", pair, ts["T_CGR_04"], order=onward_only)
    check("B pair is not RED under ONWARD-only poisons (a later read must stay healthy)",
          s.outcome is not CF.Outcome.RED, s.line().strip())

    print("\nC — MUTATION ARM: with the poisons disabled, RED must disappear")
    orig = CF.poison_transcript
    try:
        CF.poison_transcript = lambda t, p, e, k: t          # identity: no poison
        s1 = CF.sweep("T_CGR_01", honest, ts["T_CGR_01"])
        s7 = CF.sweep("T_CGR_07", contract, ts["T_CGR_07"])
    finally:
        CF.poison_transcript = orig
    check("C honest is no longer RED with the poison removed",
          s1.outcome is CF.Outcome.NEVER_RED, s1.line().strip())
    check("C contract has no red at all with the poison removed",
          s7.outcome is CF.Outcome.NEVER_RED, s7.line().strip())
    s1b = CF.sweep("T_CGR_01", honest, ts["T_CGR_01"])
    check("C the poison is restored afterwards (honest RED again)",
          s1b.outcome is CF.Outcome.RED)

    print("\nD — MUTATION ARM: with the fail witness blinded, POLICY cannot be told apart")
    orig_grade = CF._grade
    try:
        CF._grade = lambda arm, w, tid: (CF.Grade.ASSERTION if arm is CF._dispatch.Arm.BODY
                                         else orig_grade(arm, w, tid))
        s6 = CF.sweep("T_CGR_06", flaker, ts["T_CGR_06"])
    finally:
        CF._grade = orig_grade
    check("D a grader that trusts every body fail() calls flaker RED — the witness "
          "is what stops it", s6.outcome is CF.Outcome.RED, s6.line().strip())

    print("\nE — the gate over the shapes")
    tests = dict(BODIES)
    tests["T_CGR_09"] = honest                       # registered, unrecorded
    root = write_root("")
    failures, notes, census = G.evaluate(tests, ts, root, cross_check=False)
    blocking_ids = {"T_CGR_02", "T_CGR_03", "T_CGR_05", "T_CGR_06", "T_CGR_07"}
    got = {f.split(" ->")[0] for f in failures}
    check("E exactly the five blocking shapes fail with an empty ledger",
          got == blocking_ids, f"{sorted(got)}")
    check("E T_CGR_08 (BASELINE-NOT-PASS) is a note with a re-record instruction, not a failure",
          any("T_CGR_08" in n and "re-record" in n for n in notes)
          and not any("T_CGR_08" in f for f in failures))
    check("E T_CGR_09 is UNRECORDED in the census",
          any(s.tid == "T_CGR_09" for s in census[CF.Outcome.UNRECORDED]))
    check("E three RED in the census (honest, pair, byname)",
          len(census[CF.Outcome.RED]) == 3, str([s.tid for s in census[CF.Outcome.RED]]))

    print("\nF — the ledger")
    rows = ("| `T_CGR_02` | RED-WITHOUT-ASSERTION | inverted guard, TASK-582 | TASK-582 | 2026-09-08 |\n"
            "| `T_CGR_03` | NEVER-RED | skips | TASK-999 | 2026-09-08 |\n"
            "| `T_CGR_05` | RED-WITHOUT-ASSERTION | raw cmd | TASK-999 | 2026-09-08 |\n"
            "| `T_CGR_06` | RED-WITHOUT-ASSERTION | flake | TASK-999 | 2026-09-08 |\n"
            "| `T_CGR_07` | RED-WITHOUT-ASSERTION | typed read, no compare | TASK-999 | 2026-09-08 |\n")
    root = write_root(rows)
    failures, notes, _ = G.evaluate(tests, ts, root, cross_check=False)
    check("F a complete, correct ledger brings the gate to zero", failures == [], str(failures))

    root = write_root(rows + "| `T_CGR_01` | NEVER-RED | stale | TASK-999 | 2026-09-08 |\n")
    failures, _, _ = G.evaluate(tests, ts, root, cross_check=False)
    check("F a row for an id that sweeps RED is a STALE row and fails",
          any("T_CGR_01" in f and "stale" in f for f in failures), str(failures))

    bad = rows.replace("| `T_CGR_05` | RED-WITHOUT-ASSERTION |", "| `T_CGR_05` | NEVER-RED |")
    root = write_root(bad)
    failures, _, _ = G.evaluate(tests, ts, root, cross_check=False)
    check("F a row naming the WRONG outcome fails",
          any("T_CGR_05" in f and "must name what is true" in f for f in failures),
          str(failures))

    root = write_root(rows, archive="TASK-999 archived long ago")
    failures, _, _ = G.evaluate(tests, ts, root, cross_check=False)
    check("F a row whose owner is ARCHIVED fails",
          sum("ARCHIVED" in f for f in failures) == 4, str(failures))

    nodate = rows.replace("| 2026-09-08 |\n", "| |\n", 1)
    root = write_root(nodate)
    failures, _, _ = G.evaluate(tests, ts, root, cross_check=False)
    check("F a row with no ISO date fails",
          any("no ISO date" in f for f in failures), str(failures))

    root = write_root(rows + "| `T_CGR_09` | NEVER-RED | unrecorded | TASK-999 | 2026-09-08 |\n")
    failures, notes, _ = G.evaluate(tests, ts, root, cross_check=False)
    check("F a row for an UNRECORDED id is a note (unverifiable), not a failure",
          failures == [] and any("T_CGR_09" in n and "unverifiable" in n for n in notes),
          str(failures) + str(notes))

    print("\nG — the transcript loader")
    d = tempfile.mkdtemp(prefix="cgr_t_")
    for tid, t in ts.items():
        t.save(pathlib.Path(d) / f"{tid}.json")
    (pathlib.Path(d) / "T_CGR_77.json").write_text("{not json")
    ts["T_CGR_01"].save(pathlib.Path(d) / "T_CGR_88.json")      # misnamed
    loaded, errs = G.load_transcripts(d)
    check("G nine transcripts round-trip through disk", len(loaded) == 9, str(sorted(loaded)))
    check("G an unreadable file is an error, not a silent skip",
          any("T_CGR_77" in e for e in errs), str(errs))
    check("G a file whose name and id disagree is an error",
          any("T_CGR_88" in e for e in errs), str(errs))
    loaded, errs = G.load_transcripts(pathlib.Path(d) / "nope")
    check("G a missing directory is zero transcripts and zero errors",
          loaded == {} and errs == [])

    print("\nH — the injected sweep (evaluate cannot pass vacuously)")
    def vacuous(tid, fn, t):
        return CF.Sweep(tid, CF.Outcome.RED, evidence=CF.Evidence(
            CF.Poison.PERTURB, CF.Extent.AT, 0, "x", CF.Grade.ASSERTION, "FAIL: x"))
    root = write_root(rows)
    failures, _, _ = G.evaluate(tests, ts, root, sweep=vacuous, cross_check=False)
    check("H a sweep that says RED for everything makes every ledger row STALE (5 failures)",
          sum("stale" in f for f in failures) == 5, str(failures))

    print()
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL: {f}")
        print(f"\n=== {len(FAILURES)} check(s) FAILED ===")
        return 1
    print("=== can-go-red negative suite: all checks passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
