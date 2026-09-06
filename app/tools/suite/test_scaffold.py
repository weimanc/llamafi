#!/usr/bin/env python3
"""test_scaffold.py — the scaffold's negative suite. TASK-630 / BP-068.

A scaffold is only worth having if what it emits is ACCEPTED by the gates a new
test has to pass and REFUSED where a person has to think. Both halves are
asserted here against the REAL gate code — `check_no_reachable_fail.analyse`,
`check_defaulted_reads.defaulted_reads`, `check_restore_manager.unrestored_
mutations`, `check_test_meta.MIN_CLS_REASON`, `check_plan_integrity.HEADING_RE`
and `check_player_binding`'s registry regex — never against a copy of their
rules. A re-implementation of a gate's rule inside its own test is a mirror
(LL-114) and passes exactly when the mirror is wrong.

Blocking at zero from the day it lands. No DUT, no port, no build, no network.

    python3 app/tools/suite/test_scaffold.py
"""

from __future__ import annotations

import ast
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from suite import scaffold                                     # noqa: E402
from suite.serialdbg import _meta                              # noqa: E402
from gate import check_defaulted_reads as _cdr                 # noqa: E402
from gate import check_no_reachable_fail as _cnrf              # noqa: E402
from gate import check_restore_manager as _crm                 # noqa: E402
from gate import check_plan_integrity as _cpi                  # noqa: E402
from gate import check_test_meta as _ctm                       # noqa: E402

FAILURES: list = []
CHECKS = [0]

#: ids the tool must treat as taken, so the collision arm does not depend on
#: what happens to be registered on the day it runs.
KNOWN = {"T_PLR_01", "T240"}


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(msg)


def refuses(msg, **kw):
    """-> True if build() refused. A refusal is the tool working."""
    CHECKS[0] += 1
    try:
        scaffold.build(known_ids=KNOWN, **kw)
    except scaffold.Refusal:
        return True
    FAILURES.append(f"NOT REFUSED: {msg}")
    return False


def compile_body(out):
    """The emitted body -> a live function, the way the gates see one.

    `_meta.seed_effect` and `check_no_reachable_fail.analyse` both walk
    `inspect.getsource`, which needs the text on disk under a linecache entry;
    writing it to a real module file is the only honest way to run the real
    gate over it.
    """
    import tempfile
    fn_name = scaffold.func_name(out["id"])
    src = ("from typing import Any\n"
           # the REAL decorator, not a stub: a stub that returns the
           # function unchanged drops `fn._meta` and the arm would
           # then assert the record resolves from a decorator that
           # was never applied.
           "from suite.serialdbg._meta import meta\n"
           "def fail(*a, **k):\n    pass\n"
           "Dut = Any\n\n" + out["body"])
    d = tempfile.mkdtemp(prefix="scaffold-arm-")
    path = os.path.join(d, "probe_mod.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    mod = types.ModuleType("probe_mod")
    mod.__file__ = path
    sys.modules["probe_mod"] = mod
    with open(path, encoding="utf-8") as fh:
        exec(compile(fh.read(), path, "exec"), mod.__dict__)   # noqa: S102
    return mod.__dict__[fn_name]


# ── A1-A6: what it EMITS is accepted by the gates ────────────────────────────

def arm_reachable_fail():
    for kw in ({"scope": "Stock"},
               {"scope": "LocalPlayer", "effect": "mutating",
                "effect_reason": "writes"}):
        out = scaffold.build("T_SCF_01", known_ids=KNOWN, **kw)
        fn = compile_body(out)
        found = _cnrf.analyse("T_SCF_01", fn)
        check(not found,
              f"R34: the emitted body has no reachable fail() ({kw}): {found}")
        check("skip(" not in out["body"],
              "the skeleton must not use skip() — a skip standing in for an "
              "unmet premise is the C-5 defect (R28)")


def arm_typed_reads():
    out = scaffold.build("T_SCF_02", scope="Stock", known_ids=KNOWN)
    found = _cdr.defaulted_reads(out["body"])
    check(not found, f"R18: the emitted body contains a defaulted read: {found}")
    check("get_int(" in out["body"],
          "R18: the skeleton should demonstrate a typed accessor")


def arm_restore_manager():
    out = scaffold.build("T_SCF_03", scope="Stock", effect="mutating",
                         effect_reason="writes", known_ids=KNOWN)
    check("with dut.saved(" in out["body"],
          "R17: a mutating skeleton must mutate inside the restore manager")
    found = _crm.unrestored_mutations(out["body"])
    check(not found, f"R17: the emitted mutating body leaks state: {found}")
    ro = scaffold.build("T_SCF_04", scope="Stock", known_ids=KNOWN)
    check("dut.saved(" not in ro["body"],
          "a read-only skeleton must not carry a restore manager it does not need")


def arm_record_resolves():
    """The decorator the tool writes must resolve to the record it claims."""
    out = scaffold.build("T_SCF_05", scope="WebRadio", cls="CORE",
                         title="t", known_ids=KNOWN)
    fn = compile_body(out)
    rec = _meta.resolve("T_SCF_05", fn, out["module"])
    check(rec["cls"] == "CORE",
          f"the emitted @meta does not resolve to cls=CORE: {rec['cls']}")
    check(rec["scope"] == "WebRadio",
          f"the emitted record resolves to scope {rec['scope']!r}, not WebRadio")
    check(rec["cls_declared"], "a gating cls must resolve as DECLARED, not seeded")
    check(not rec["scope_declared"],
          "EC-D2: a scope that matches its seed must NOT be hand-typed")


def arm_registry_line():
    out = scaffold.build("T_SCF_06", scope="LocalPlayer", known_ids=KNOWN)
    # The literal shape check_player_binding.py regexes for T_PMT_00, applied to
    # the emitted line: a wrapped or reformatted entry reds run/check.
    pat = r'"T_SCF_06"\s*:\s*t_scf_06'
    check(re.search(pat, out["registry"]) is not None,
          f"the registry line is not in the regexed shape: {out['registry']!r}")
    check(ast.parse("{\n" + out["registry"] + "\n}"),
          "the registry line does not parse inside a dict literal")


def arm_plan_entry():
    out = scaffold.build("T_SCF_07", scope="Clock", title="a title",
                         known_ids=KNOWN)
    head = out["plan"].split("\n", 1)[0]
    m = _cpi.HEADING_RE.match(head)
    check(m is not None and m.group(1) == "T_SCF_07",
          f"the plan heading is not parsed as this id's declaration: {head!r}")
    check(_cpi.UNRUNNABLE_RE.search(out["plan"]) is None,
          "P5: a scaffolded plan entry must not read [MANUAL]/[Blocked] while a "
          "body is registered")
    check(re.search(r"^- \*\*Status\*\*: written \(\d{4}-\d\d-\d\d\)\.$",
                    out["plan"], re.M) is not None,
          "C6 reads a **Status**: field; the emitted entry has none it can parse")
    # P3: the plan title and the body title must share content words. The gate
    # scores ZERO shared words as a collision, so a scaffold whose two halves
    # disagree would mint a finding on the day it is used.
    check(_cpi._overlap("a title", "a title") > 0,
          "P3: the emitted plan title and body title share no content words")


def arm_determinism():
    a = scaffold.build("T_SCF_08", scope="Stock", today="2026-01-01",
                       known_ids=KNOWN)
    b = scaffold.build("T_SCF_08", scope="Stock", today="2026-01-01",
                       known_ids=KNOWN)
    check(a == b, "two builds of the same request differ")


# ── B1-B6: what it REFUSES ───────────────────────────────────────────────────

def arm_refusals():
    refuses("an id that already binds to a body",
            test_id="T_PLR_01", scope="LocalPlayer")
    refuses("an id in retired_test_ids.md / the known set",
            test_id="T240", scope="Stock")
    refuses("a malformed id", test_id="plr40", scope="Stock")
    refuses("a scope outside the enum", test_id="T_SCF_10", scope="spotify")
    # `Weather` has no family module of its own — its ids live in shell.py
    # behind the `T_WX_` prefix — so an id with neither seeds to `shell` and the
    # scope must be DECLARED. That is the one shape that needs the author's word.
    refuses("a scope override with no one-word reason",
            test_id="T_SCF_11", scope="Weather")
    refuses("an effect override with no one-word reason",
            test_id="T_SCF_12", scope="Stock", effect="read-only")
    refuses("a class outside the enum",
            test_id="T_SCF_13", scope="Stock", cls="GATING")


def arm_gating_reason_is_refused():
    """The load-bearing one (Phase 1 standing condition 2, QM §4).

    The tool must NOT emit a `cls_reason` that satisfies the gate. If it ever
    does, a gating class ships with a machine-written justification, which is
    the exact failure mode the declaration exists to prevent.
    """
    out = scaffold.build("T_SCF_14", scope="Stock", cls="CORE", known_ids=KNOWN)
    m = re.search(r'cls_reason="([^"]*)"', out["body"])
    check(m is not None, "a gating scaffold emitted no cls_reason stub at all")
    if m:
        check(len(m.group(1)) < _ctm.MIN_CLS_REASON,
              f"REFUSAL BROKEN: the emitted cls_reason is "
              f"{len(m.group(1))} chars, at or over check_test_meta's floor of "
              f"{_ctm.MIN_CLS_REASON} — a scaffolded gating test would ship "
              f"with a machine-written reason and pass the gate")
        check("TODO" in m.group(1),
              "the cls_reason stub must be visibly a stub")
    check("SCAFFOLD" in out["body"],
          "the emitted oracle must announce itself as a placeholder")


def arm_no_invented_fields():
    """R1/R9's fields do not exist yet; the tool must not spell them."""
    out = scaffold.build("T_SCF_15", scope="Stock", cls="CORE", known_ids=KNOWN)
    for banned in ("claim_class=", "falsifier=", "reads="):
        check(banned not in out["body"],
              f"the scaffold emitted {banned!r} into the record — that field is "
              f"TASK-641/642's and does not exist yet; a second spelling of it "
              f"here would be a second definition")


def main() -> int:
    for arm in (arm_reachable_fail, arm_typed_reads, arm_restore_manager,
                arm_record_resolves, arm_registry_line, arm_plan_entry,
                arm_determinism, arm_refusals, arm_gating_reason_is_refused,
                arm_no_invented_fields):
        try:
            arm()
        except Exception as e:                                 # pragma: no cover
            import traceback
            traceback.print_exc()
            FAILURES.append(f"{arm.__name__} raised {type(e).__name__}: {e}")
    print("=== test_scaffold.py — TASK-630 scaffold negative suite ===")
    for f in FAILURES:
        print(f"  FAIL: {f}")
    print(f"\n=== {CHECKS[0] - len(FAILURES)}/{CHECKS[0]} checks passed ===")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
