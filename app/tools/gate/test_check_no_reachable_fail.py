#!/usr/bin/env python3
"""test_check_no_reachable_fail.py — the R34 gate's negative suite. TASK-603.

BP-068: a gate without a negative test is not a gate. A checker that never
demonstrates a RED is indistinguishable from a checker that always returns 0,
and the corpus already contains one cell (`T-BUSY-05`) whose whole defect was
that nobody had ever seen it fail.

Six arms. Four are synthetic bodies mirroring the four shapes in the gate's
docstring, run through `analyse()` in-process. One of those four is the
**control**: a body with a plain reachable `fail()` that MUST NOT be flagged —
without it the suite would pass on a gate that flagged everything, which is the
cheapest way to fake a green gate.

The fifth arm is the **ledger's own rules** (shape/owner/date/archived-owner).

The sixth is a **mutation arm over the live corpus**, in the shape
`test_class_order.py` uses for TASK-553 and `spike/task584_residue_verdicts.py`
demonstrated for this exact defect: take a real id that the gate currently
passes, rewrite its body in memory into each of the four defective shapes, and
assert the gate's count rises by exactly one each time. A gate that cannot
detect the regression it was written for is `T-BUSY-05` with a different
subject.

    python3 app/tools/gate/test_check_no_reachable_fail.py
"""

from __future__ import annotations

import os
import sys
import textwrap
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_no_reachable_fail as G                    # noqa: E402
from suite.serialdbg import build_all_tests            # noqa: E402

FAILURES: list = []


def check(name: str, got, want) -> None:
    if got == want:
        print(f"  [ok]   {name}")
    else:
        print(f"  [FAIL] {name}: got {got!r}, want {want!r}")
        FAILURES.append(name)


# ── synthetic bodies ─────────────────────────────────────────────────────────
#
# Compiled into a module whose __module__ starts with "suite.serialdbg" so the
# gate's own reachability filter accepts the helpers — the filter is part of
# what is under test, so it is not bypassed.

SYNTH = '''
class DeviceReadError(Exception):
    pass


def _appid_is(dut, app_name) -> bool:
    """The canonical shape-4 helper: the default lives in the except arm, where
    check_defaulted_reads.py cannot see it."""
    try:
        return dut.get_str("appId", field="name") == app_name
    except DeviceReadError:
        return False


def _switch_to(dut, app_name) -> bool:
    """Wrapper — swallows only transitively. The fixpoint must reach it."""
    dut.cmd("tap 1 1")
    return _appid_is(dut, app_name)


def _honest_switch(dut, app_name) -> bool:
    """Same shape, no swallowed read: this one must NOT be called swallowing."""
    return dut.get_str("appId", field="name") == app_name


def control_ok(dut):
    """CONTROL ARM — a plain reachable fail(). Must not be flagged."""
    print("control")
    v = dut.get_int("chartLen")
    if v != 0:
        fail("CTL", "chartLen wrong")
        return
    pass_("CTL", "ok")


def control_helper_guarded_but_not_sole(dut):
    """A helper-guarded fail() that is NOT the only one. Must not be flagged:
    the finding is about an id whose ONLY verdict rides on the swallowed read."""
    if not _switch_to(dut, "Stock"):
        fail("CTL2", "could not switch")
        return
    if dut.get_int("chartLen") != 0:
        fail("CTL2", "chartLen wrong")
        return
    pass_("CTL2", "ok")


def control_honest_bool_guard(dut):
    """Guarded by a bool helper that does NOT swallow. Must not be flagged."""
    if not _honest_switch(dut, "Stock"):
        fail("CTL3", "could not switch")
        return
    pass_("CTL3", "ok")


def shape1_no_fail(dut):
    """No fail() anywhere in the reachable source."""
    print("shape1")
    if not _switch_to(dut, "Stock"):
        skip("S1", "could not switch")
        return
    pass_("S1", "ok")


def shape2_lone_skip(dut):
    """One unconditional skip() and nothing else."""
    print("shape2")
    skip("S2", "merged into another id — run that one")


def shape3_tautological_guard(dut):
    """A guard on a reply field whose truthiness was already required above."""
    r_app = dut.cmd("get appId")
    name = r_app["name"]
    if not r_app.get("ok"):
        fail("S3", "get appId failed")
        return
    if name != "Stock":
        pass_("S3", "ok")


def shape4_sole_fail_behind_swallow(dut):
    """The only fail() is guarded by an error-swallowing bool helper."""
    print("shape4")
    if not _switch_to(dut, "Stock"):
        fail("S4", "could not switch to Stock")
        return
    pass_("S4", "ok")
'''


def build_synth():
    mod = types.ModuleType("suite.serialdbg._synthetic_r34")
    mod.__dict__["__name__"] = "suite.serialdbg._synthetic_r34"
    src_path = os.path.join(HERE, "testdata", "_r34_synthetic.py")
    os.makedirs(os.path.dirname(src_path), exist_ok=True)
    with open(src_path, "w", encoding="utf-8") as fh:
        fh.write(SYNTH)
    # Executed from a real file so inspect.getsource() works — the gate reads
    # source, so an exec'd-from-string module would not exercise it.
    code = compile(SYNTH, src_path, "exec")
    for name in ("fail", "skip", "pass_", "print"):
        mod.__dict__.setdefault(name, lambda *a, **k: None)
    exec(code, mod.__dict__)
    sys.modules["suite.serialdbg._synthetic_r34"] = mod
    for v in mod.__dict__.values():
        if isinstance(v, types.FunctionType):
            v.__module__ = "suite.serialdbg._synthetic_r34"
    return mod


def shapes(tid, fn):
    return sorted(s for s, _m in G.analyse(tid, fn))


def main() -> int:
    print("=== R34 gate negative suite (TASK-603) ===")
    m = build_synth()

    # ── arms 1-4: the four shapes, plus three controls ───────────────────────
    print("\n-- synthetic arms --")
    check("control: a plain reachable fail() is NOT flagged",
          shapes("CTL", m.control_ok), [])
    check("control: a helper-guarded fail() that is not the sole one is NOT flagged",
          shapes("CTL2", m.control_helper_guarded_but_not_sole), [])
    check("control: a NON-swallowing bool guard is NOT flagged",
          shapes("CTL3", m.control_honest_bool_guard), [])
    check("shape 1: no fail() in reachable source",
          shapes("S1", m.shape1_no_fail), [1])
    check("shape 2: one unconditional skip() (also has no fail())",
          shapes("S2", m.shape2_lone_skip), [1, 2])
    check("shape 3: guard on a reply field already required upstream",
          shapes("S3", m.shape3_tautological_guard), [3])
    check("shape 4: sole fail() behind an error-swallowing bool helper",
          shapes("S4", m.shape4_sole_fail_behind_swallow), [4])

    # the fixpoint itself — _switch_to swallows only through _appid_is
    funcs = G.reachable_functions(m.shape4_sole_fail_behind_swallow)
    sw = G.swallowing_helpers(funcs)
    check("fixpoint: _appid_is is swallowing", "_appid_is" in sw, True)
    check("fixpoint: _switch_to is swallowing transitively", "_switch_to" in sw, True)
    check("fixpoint: _honest_switch is NOT swallowing",
          "_honest_switch" in G.swallowing_helpers(
              G.reachable_functions(m.control_honest_bool_guard)), False)

    # ── arm 5: the ledger's own rules ────────────────────────────────────────
    print("\n-- ledger rules --")
    import tempfile
    bad = textwrap.dedent("""
        | id | shape | why | owner | since |
        |---|---|---|---|---|
        | `T001` | 9 | bad shape | TASK-603 | 2026-09-05 |
        | `T002` | 1 | no owner | none | 2026-09-05 |
        | `T003` | 1 | no date | TASK-603 | soon |
        | `T004` | 1 | archived owner | TASK-242 | 2026-09-05 |
    """)
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, os.path.dirname(G.LEDGER_REL)), exist_ok=True)
        with open(os.path.join(td, G.LEDGER_REL), "w", encoding="utf-8") as fh:
            fh.write(bad)
        # reuse the real archive so TASK-242's archived-ness is the real fact
        os.makedirs(os.path.join(td, "docs", "project"), exist_ok=True)
        real = os.path.join(ROOT, "docs", "project", "tasks-archive.md")
        with open(os.path.join(td, "docs", "project", "tasks-archive.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(open(real, encoding="utf-8", errors="replace").read()
                     if os.path.exists(real) else "TASK-242")
        _l, errs = G.parse_ledger(td)
    joined = " | ".join(errs)
    check("ledger: a bad shape is rejected", "is not one of 1/2/3/4" in joined, True)
    check("ledger: a row with no owning task is rejected",
          "no owning TASK- id" in joined, True)
    check("ledger: a row with no ISO date is rejected",
          "no ISO date" in joined, True)
    check("ledger: a row owned by an ARCHIVED task is rejected",
          "is ARCHIVED" in joined, True)

    # ── arm 5b: an UNOBSERVABLE record above a live body (§1.1, H-2) ─────────
    print("\n-- UNOBSERVABLE with a live body --")
    unobs = G.parse_unobservable(ROOT)
    check("register: the six UNOBSERVABLE ids are parsed", len(unobs), 6)
    tests_live = build_all_tests()
    resurrect = sorted(unobs)[0]
    fails, _n, _c = G.evaluate({**tests_live, resurrect: m.control_ok}, ROOT)
    check(f"a live body under an UNOBSERVABLE record ({resurrect}) is a FAILURE",
          any("STILL REGISTERED" in f and resurrect in f for f in fails), True)

    # ── arm 6: mutation over the LIVE corpus ─────────────────────────────────
    #
    # Pick a real id the gate passes today, rewrite its body into each defective
    # shape, and require the count to rise by exactly one. This is the arm that
    # proves the gate can see the regression in the code it actually guards, as
    # opposed to in a fixture written to be seen.
    print("\n-- mutation arm over the live corpus --")
    tests = build_all_tests()
    base_fail, _n, base_counts = G.evaluate(tests, ROOT)
    check("baseline: the live corpus is green", base_fail, [])

    victim = next(t for t in ("T137", "T170", "T180", "T231")
                  if t in tests and not G.analyse(t, tests[t]))
    print(f"  victim id: {victim}")
    for shape, fn in ((1, m.shape1_no_fail),
                      (2, m.shape2_lone_skip),
                      (3, m.shape3_tautological_guard),
                      (4, m.shape4_sole_fail_behind_swallow)):
        mutated = dict(tests)
        mutated[victim] = fn
        fails, _n2, counts = G.evaluate(mutated, ROOT)
        rose = counts[shape] - base_counts[shape]
        check(f"mutation shape {shape}: the shape-{shape} count rises by exactly 1",
              rose, 1)
        check(f"mutation shape {shape}: it is reported, not swallowed by the ledger",
              any(victim in f for f in fails), True)

    print()
    if FAILURES:
        print(f"=== {len(FAILURES)} arm(s) failed: {FAILURES} ===")
        return 1
    print("=== every arm holds, including the three controls that must not flag ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
