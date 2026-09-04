#!/usr/bin/env python3
"""Negative tests for check_flake_class.py — BP-068. TASK-623 / M-HARNESS2 R37.

A gate that has never been seen to fail is not a gate, and this one has a
particular way of failing silently: it lands with one ledger row, so the naive
green result "PASS, no findings" is indistinguishable from "the ledger swallowed
everything". Cases L1-L3 exist for that — they prove the ledger suppresses
exactly one keyed finding, refuses a malformed row, and fails when a row goes
stale.

Every case drives `evaluate()` with fixtures. `evaluate()` is pure for exactly
this reason: the live registry has one violation in it, so a test that could only
observe the live state could never see the interesting transitions.

No DUT, no serial port, no build, no network.
Run: python3 app/tools/gate/test_check_flake_class.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import check_flake_class as C                            # noqa: E402
from lib import flaky as _flaky                          # noqa: E402
import suite.serialdbg as _suite                         # noqa: E402


def rec(cls: str, declared: bool = False, tid: str = "T_X_01") -> dict:
    return {tid: {"id": tid, "cls": cls, "scope": "shell", "effect": "mutating",
                  "cls_declared": declared}}


def one(fs, needle):
    hits = [f for f in fs if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {fs}"
    return hits


def none(fs):
    assert not fs, f"expected no findings, got {fs}"


# ── F1: a declared flake on a gating class ───────────────────────────────────

def case_declared_flake_on_each_gating_class():
    """Every gating class, not just CORE — a check written against one class is
    a check that misses the next one."""
    for cls in C.GATING:
        fs = C.evaluate({"T_X_01": object()}, {}, rec(cls))
        one(fs, "F1 T_X_01")
        one(fs, cls)


def case_feature_flake_is_fine():
    """The positive control: FEATURE is where a declared flake belongs. Five of
    the six live declarations are FEATURE and must stay silent."""
    none(C.evaluate({"T_X_01": object()}, {}, rec("FEATURE")))


def case_message_names_seeded_versus_declared():
    """T091's CORE is SEEDED, not declared — the finding must say so, because
    the fix differs: a seeded class is TASK-591's to declare or demote."""
    one(C.evaluate({"T_X_01": object()}, {}, rec("CORE", declared=False)), "(seeded)")
    one(C.evaluate({"T_X_01": object()}, {}, rec("CORE", declared=True)), "(declared)")


# ── F2: a candidate on a gating class ────────────────────────────────────────

def case_candidate_on_gating_class():
    fs = C.evaluate({}, {"T_X_01": "note"}, rec("CORE"))
    one(fs, "F2 T_X_01")


def case_candidate_on_feature_is_fine():
    none(C.evaluate({}, {"T_X_01": "note"}, rec("FEATURE")))


def case_candidate_is_not_ledger_exemptable():
    """F2 is at zero today, so it has no exemption path. A ledger row keyed on
    a candidate must NOT suppress it — and must itself be reported stale."""
    ledger = {("gating-flake", "T_X_01"): "ledger.md:1"}
    fs = C.evaluate({}, {"T_X_01": "note"}, rec("CORE"), ledger)
    one(fs, "F2 T_X_01")
    one(fs, "F4")


# ── F3: a declaration for an id nothing dispatches ───────────────────────────

def case_declared_flake_for_unregistered_id():
    fs = C.evaluate({"T_GHOST": object()}, {}, {})
    one(fs, "F3 T_GHOST")


def case_candidate_for_unregistered_id():
    fs = C.evaluate({}, {"T_GHOST": "note"}, {})
    one(fs, "F3 T_GHOST")


# ── F4 and the ledger ────────────────────────────────────────────────────────

def case_ledger_suppresses_exactly_its_key():
    """L1 — the row suppresses T_X_01 and nothing else. A second violating id
    must still be reported, or the ledger is a wildcard."""
    meta = {}
    meta.update(rec("CORE", tid="T_X_01"))
    meta.update(rec("CORE", tid="T_X_02"))
    ledger = {("gating-flake", "T_X_01"): "ledger.md:1"}
    fs = C.evaluate({"T_X_01": 1, "T_X_02": 1}, {}, meta, ledger)
    assert not [f for f in fs if "T_X_01" in f], f"T_X_01 should be exempt: {fs}"
    one(fs, "F1 T_X_02")


def case_stale_ledger_row_fails():
    """L2 — the property that makes the list shrink-only. The id is now
    FEATURE, so the finding is gone and the row must go with it."""
    ledger = {("gating-flake", "T_X_01"): "ledger.md:7"}
    fs = C.evaluate({"T_X_01": 1}, {}, rec("FEATURE"), ledger)
    one(fs, "F4 ledger.md:7")
    one(fs, "delete this row")


def case_stale_row_also_fires_when_the_declaration_is_removed():
    """The other retirement path: the flaky.yaml entry is deleted."""
    fs = C.evaluate({}, {}, rec("CORE"), {("gating-flake", "T_X_01"): "ledger.md:7"})
    one(fs, "F4")


def case_malformed_ledger_rows_are_errors():
    """L3 — a row missing its owning task or its date is a failure, not a
    silently skipped row; that is how an exemption ledger becomes an amnesty."""
    body = (
        "| id | kind | why | owner | since |\n"
        "|---|---|---|---|---|\n"
        "| `T_A` | gating-flake | reason | TASK-591 | 2026-09-04 |\n"
        "| `T_B` | gating-flake | reason | not-a-task | 2026-09-04 |\n"
        "| `T_C` | gating-flake | reason | TASK-591 | 4th Sept |\n"
        "| `T_D` | wildcard | reason | TASK-591 | 2026-09-04 |\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "led.md")
        Path(p).write_text(body, encoding="utf-8")
        rows, errors = C.parse_ledger(p)
        assert set(rows) == {("gating-flake", "T_A")}, rows
        assert len(errors) == 3, errors
        assert any("must be a TASK-NNN" in e for e in errors), errors
        assert any("ISO YYYY-MM-DD" in e for e in errors), errors
        assert any("not exemptable" in e for e in errors), errors


def case_missing_ledger_is_not_a_crash():
    rows, errors = C.parse_ledger(os.path.join(C.ROOT, "does-not-exist.md"))
    assert rows == {} and errors == []


def case_missing_ledger_fails_closed():
    """TASK-591. The ledger is GONE, so the absent path is now the live path and
    its safety property has to be proved, not assumed: absent parses to zero
    rows, zero rows grandfather nothing, so a gating flake declared tomorrow is
    caught with no ledger present. Losing the file can only make the gate
    stricter — never quieter."""
    rows, errors = C.parse_ledger(os.path.join(C.ROOT, "does-not-exist.md"))
    meta = {"T_Z": {"cls": "CORE", "cls_declared": True}}
    fs = C.evaluate({"T_Z": {}}, {}, meta, rows)
    one(fs, "F1 T_Z")
    assert not errors, errors


def case_absent_ledger_passes_when_there_is_nothing_to_exempt():
    """The other direction, and the state the corpus is actually in: no file, no
    declared gating flake, no findings. A clean pass, not a silent one."""
    rows, errors = C.parse_ledger(os.path.join(C.ROOT, "does-not-exist.md"))
    meta = {"T_Z": {"cls": "FEATURE", "cls_declared": True}}
    none(C.evaluate({"T_Z": {}}, {}, meta, rows))
    assert not errors, errors


def case_f4_staleness_still_works_from_zero_rows():
    """F4 is the rule that makes the list shrink-only, and it must not have been
    quietly disabled by the ledger reaching zero. With no rows there is nothing
    to be stale, and with one row whose finding no longer occurs it still
    fires — the same code path, driven both ways."""
    meta = {"T_Z": {"cls": "FEATURE", "cls_declared": True}}
    none(C.evaluate({"T_Z": {}}, {}, meta, {}))
    stale = C.evaluate({"T_Z": {}}, {}, meta,
                       {("gating-flake", "T_Z"): "docs/gone.md:44"})
    one(stale, "F4 docs/gone.md:44")


def case_empty_ledger_file_is_a_finding():
    """F5. A file left behind with a header and no rows is a half-finished
    retirement, and an empty exemption list is where the next amnesty starts."""
    import tempfile
    from pathlib import Path
    body = ("# ledger\n\n| id | kind | why | owner | since |\n|---|---|---|---|---|\n")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "led.md")
        Path(p).write_text(body, encoding="utf-8")
        rows, errors = C.parse_ledger(p)
    assert rows == {}, rows
    one(errors, "holds no rows")


def case_the_flake_ledger_is_actually_gone():
    """The retirement itself, asserted rather than assumed: T091 is no longer a
    gating class, so the file its only row lived in must not exist."""
    assert not os.path.exists(os.path.join(C.ROOT, C.LEDGER_REL)), (
        f"{C.LEDGER_REL} still exists, but its last row was retired")
    meta = _suite.build_all_meta()
    assert meta["T091"]["cls"] == "FEATURE", meta["T091"]["cls"]
    assert meta["T091"]["cls_declared"], "T091 is FEATURE by seed, not by declaration"


# ── derivation and live state ────────────────────────────────────────────────

def case_gating_set_is_the_expected_triple():
    """The derivation is from `_order.CORE_BLOCKS`, not a typed list. Pin it: if
    the ladder gains a blocking class this fails here rather than silently
    narrowing what the gate covers."""
    assert C.GATING == ("RIG", "HEALTH", "CORE"), C.GATING


def case_live_ledger_parses_to_nothing():
    """TASK-591: the ledger is retired, so the live parse is the absent path."""
    rows, errors = C.parse_ledger()
    assert rows == {} and errors == [], (rows, errors)


def case_live_registry_state_is_at_zero():
    """The honesty check, inverted by the demotion. The corpus now holds ZERO
    F1s, so the gate is blocking at zero with no ledger — and this test is what
    stops that claim from being a comment. If a flake is ever declared on a
    gating id again, this fails and the programme rule applies: fix it or demote
    it, and only then consider re-opening a ledger."""
    reg, err = _flaky.get_registry()
    assert err is None, err
    meta = _suite.build_all_meta()
    violations = sorted(t for t in reg.entries
                        if (meta.get(t) or {}).get("cls") in C.GATING)
    assert violations == [], violations
    # T091 is still a declared flake — the contradiction was resolved by moving
    # its class, not by deleting the flake entry, and that must stay true or the
    # demotion was doing something other than what it claimed.
    assert "T091" in reg.entries, sorted(reg.entries)


def case_live_run_is_green_with_the_ledger():
    reg, err = _flaky.get_registry()
    assert err is None, err
    ledger, errors = C.parse_ledger()
    assert not errors, errors
    none(C.evaluate(reg.entries, reg.candidates, _suite.build_all_meta(), ledger))


CASES = [
    ("F1a declared flake on every gating class", case_declared_flake_on_each_gating_class),
    ("F1b FEATURE flake is fine",                case_feature_flake_is_fine),
    ("F1c seeded vs declared is named",          case_message_names_seeded_versus_declared),
    ("F2a candidate on a gating class",          case_candidate_on_gating_class),
    ("F2b candidate on FEATURE is fine",         case_candidate_on_feature_is_fine),
    ("F2c a candidate is not exemptable",        case_candidate_is_not_ledger_exemptable),
    ("F3a declaration for an unknown id",        case_declared_flake_for_unregistered_id),
    ("F3b candidate for an unknown id",          case_candidate_for_unregistered_id),
    ("L1  the ledger suppresses one key only",   case_ledger_suppresses_exactly_its_key),
    ("L2  a stale row is a failure",             case_stale_ledger_row_fails),
    ("L3  stale on declaration removal too",     case_stale_row_also_fires_when_the_declaration_is_removed),
    ("L4  malformed rows are errors",            case_malformed_ledger_rows_are_errors),
    ("L5  a missing ledger is not a crash",      case_missing_ledger_is_not_a_crash),
    ("L6  a missing ledger fails CLOSED",        case_missing_ledger_fails_closed),
    ("L7  absent + nothing to exempt = pass",    case_absent_ledger_passes_when_there_is_nothing_to_exempt),
    ("L8  F4 staleness works from zero rows",    case_f4_staleness_still_works_from_zero_rows),
    ("L9  an empty ledger FILE is a finding",    case_empty_ledger_file_is_a_finding),
    ("D1  GATING derives to RIG/HEALTH/CORE",    case_gating_set_is_the_expected_triple),
    ("P1  the flake ledger is retired",          case_the_flake_ledger_is_actually_gone),
    ("P2  the live corpus is AT zero",           case_live_registry_state_is_at_zero),
    ("P3  live run is green with no ledger",     case_live_run_is_green_with_the_ledger),
]


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"test_check_flake_class: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
