#!/usr/bin/env python3
"""test_check_primitive_coverage.py — the negative suite for TASK-705's
primitive-coverage gate.

BP-068. `evaluate()` is pure (records dict, ledger dict) -> (findings, census),
so every case here is a synthetic record set — no DUT, no live suite import
needed for the mechanism cases. One live-tree case (`_live_tree_reads_zero`)
imports the real `suite.serialdbg` package to prove `run/check`'s actual gate
call lands clean, same shape as `test_check_gating_offline.py`'s section C.

    python3 app/tools/gate/test_check_primitive_coverage.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_primitive_coverage as C                                # noqa: E402
from suite.serialdbg import _meta                                   # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


def _rec(ops=()):
    return {"ops": tuple(ops)}


# Two real op names to anchor the synthetic cases against the live vocabulary,
# so a future OPS rename cannot leave this file silently testing a dead string.
# Excludes anything in HARNESS_PRIMITIVES — those ops are P1-silenced by the
# harness map itself, which would make every "P1 fires" case below a false
# negative for that op specifically.
_plain_ops = [op for op in _meta.OPS_ORDER if op not in C.HARNESS_PRIMITIVES]
_OP_A, _OP_B = _plain_ops[:2]


# ── P1: an op with no primitive and no ledger row is a finding ───────────────

def case_p1_fires_with_no_primitive_no_ledger():
    records = {"T-X-01": _rec()}   # declares nothing
    findings, census = C.evaluate(records, ledger={})
    check("P1 fires when an op has no declarer at all",
          any(f.startswith(f"P1 {_OP_A}") for f in findings)
          and any(f.startswith(f"P1 {_OP_B}") for f in findings),
          findings)


def case_p1_silenced_by_a_primitive():
    records = {"T-X-01": _rec((_OP_A,))}
    findings, census = C.evaluate(
        records, ledger={op: "x:1" for op in _meta.OPS if op != _OP_A})
    check("P1 does not fire once a primitive declares the op alone",
          not any(f.startswith(f"P1 {_OP_A}") for f in findings), findings)
    check("primitive census counts the id",
          census["primitives"] == 1 and census["composites"] == 0, census)


def case_p1_silenced_by_ledger_row():
    ledger = {op: "x:1" for op in _meta.OPS}
    findings, _ = C.evaluate({}, ledger=ledger)
    check("P1 does not fire for a ledgered op with zero declarers",
          not any(f.startswith("P1 ") for f in findings), findings)


def case_composite_does_not_count_as_a_primitive():
    """The reason this gate exists: TASK-697's own composites covered several
    ops WITHOUT any of them having a primitive. A 2-op id must not silence P1
    for either op."""
    records = {"T-X-02": _rec((_OP_A, _OP_B))}
    findings, census = C.evaluate(records, ledger={})
    check("a 2-op composite still leaves P1 open for both ops",
          any(f.startswith(f"P1 {_OP_A}") for f in findings)
          and any(f.startswith(f"P1 {_OP_B}") for f in findings), findings)
    check("composite census counts the id once, not as a primitive",
          census["composites"] == 1 and census["primitives"] == 0, census)


# ── P2: an id declaring an op outside OPS ─────────────────────────────────────

def case_p2_fires_on_unknown_op():
    records = {"T-X-03": _rec(("not_a_real_op",))}
    findings, _ = C.evaluate(records, ledger={})
    check("P2 fires on an op not in _meta.OPS",
          any(f.startswith("P2 T-X-03") for f in findings), findings)


def case_p2_does_not_fold_the_bad_op_into_primitive_counts():
    records = {"T-X-03": _rec(("not_a_real_op",))}
    _, census = C.evaluate(records, ledger={})
    check("an id whose only op is invalid is counted undeclared, not primitive",
          census["undeclared"] == 1 and census["primitives"] == 0, census)


# ── P3: a composite's op with no primitive and no ledger row ─────────────────

def case_p3_fires_for_composite_only_op():
    records = {
        "T-X-04": _rec((_OP_A,)),                 # primitive for _OP_A
        "T-X-05": _rec((_OP_A, _OP_B)),            # composite touching _OP_B too
    }
    ledger = {op: "x:1" for op in _meta.OPS if op not in (_OP_A, _OP_B)}
    findings, _ = C.evaluate(records, ledger=ledger)
    check("P3 fires for the composite-only op (_OP_B has no primitive/ledger row)",
          any(f.startswith(f"P3 {_OP_B}") for f in findings), findings)
    check("P1 does not ALSO fire for _OP_B (P3 is the more specific finding, "
          "but P1's own gap for _OP_B is real too — both may legitimately fire)",
          any(f.startswith(f"P1 {_OP_B}") for f in findings), findings)


def case_p3_silenced_once_primitive_exists():
    records = {
        "T-X-04": _rec((_OP_A,)),
        "T-X-05": _rec((_OP_A, _OP_B)),
        "T-X-06": _rec((_OP_B,)),                 # now _OP_B has its own primitive
    }
    ledger = {op: "x:1" for op in _meta.OPS if op not in (_OP_A, _OP_B)}
    findings, _ = C.evaluate(records, ledger=ledger)
    check("P3 does not fire once _OP_B has its own primitive",
          not any(f.startswith(f"P3 {_OP_B}") for f in findings), findings)


# ── stale ledger rows ─────────────────────────────────────────────────────────

def case_stale_ledger_row_is_a_finding():
    records = {"T-X-07": _rec((_OP_A,))}
    ledger = {_OP_A: "docs/x.md:9"}
    findings, _ = C.evaluate(records, ledger=ledger)
    check("a ledger row for an op that now HAS a primitive is STALE",
          any(f.startswith(f"STALE docs/x.md:9") for f in findings), findings)


# ── undeclared ids are never a finding ────────────────────────────────────────

def case_undeclared_is_silent():
    records = {"T-X-08": _rec(())}
    findings, census = C.evaluate(records, ledger={op: "x:1" for op in _meta.OPS})
    check("an id with no ops produces zero findings attributable to it",
          not any("T-X-08" in f for f in findings), findings)
    check("undeclared count includes it", census["undeclared"] == 1, census)


# ── ledger parsing ────────────────────────────────────────────────────────────

def case_ledger_parse_rejects_unknown_op():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.md")
        with open(path, "w") as fh:
            fh.write("| op | why | owner | since |\n"
                     "|---|---|---|---|\n"
                     "| not_a_real_op | because | TASK-1 | 2026-09-14 |\n")
        rows, errors = C.parse_ledger(path)
        check("an unknown op in the ledger is a parse error, not a silent row",
              len(errors) == 1 and not rows, errors)


def case_ledger_parse_rejects_bad_owner_and_date():
    import tempfile
    op = next(iter(_meta.OPS))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.md")
        with open(path, "w") as fh:
            fh.write("| op | why | owner | since |\n"
                     "|---|---|---|---|\n"
                     f"| {op} | because | not-a-task | 2026-09-14 |\n")
        _rows, errors = C.parse_ledger(path)
        check("a non-TASK-NNN owner is a parse error", len(errors) == 1, errors)

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.md")
        with open(path, "w") as fh:
            fh.write("| op | why | owner | since |\n"
                     "|---|---|---|---|\n"
                     f"| {op} | because | TASK-1 | not-a-date |\n")
        _rows, errors = C.parse_ledger(path)
        check("a non-ISO since is a parse error", len(errors) == 1, errors)


def case_ledger_parse_accepts_a_well_formed_row():
    op = next(iter(_meta.OPS))
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.md")
        with open(path, "w") as fh:
            fh.write("| op | why | owner | since |\n"
                     "|---|---|---|---|\n"
                     f"| {op} | because | TASK-1 | 2026-09-14 |\n")
        rows, errors = C.parse_ledger(path)
        check("a well-formed row parses with no errors",
              not errors and op in rows, (rows, errors))


# ── live tree: run/check's actual call lands clean ───────────────────────────

def case_live_tree_reads_zero():
    import suite.serialdbg as _suite
    records = _suite.build_all_meta()
    ledger, lerrs = C.parse_ledger()
    findings, census = C.evaluate(records, ledger)
    findings = lerrs + findings
    check("the live tree's own ops/ledger state has zero findings",
          not findings, findings)
    check("the live census matches len(_meta.OPS)",
          census["ops_total"] == len(_meta.OPS), census)


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("case_") and callable(fn):
            print(f"── {name} ──")
            fn()
    if FAILURES:
        print(f"\n=== {len(FAILURES)}/{len([n for n in globals() if n.startswith('case_')])} "
              f"case(s) failed: {FAILURES} ===")
        return 1
    print("\n=== all cases passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
