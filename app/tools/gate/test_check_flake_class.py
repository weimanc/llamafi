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

import datetime
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import _case_runner  # noqa: E402

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


def case_t091_retirement_still_holds():
    """T091's own 2026-09-04 retirement (TASK-591) is untouched by the
    TASK-595 reopening below — it is still FEATURE, still declared, and still
    has no `gating-flake` row of its own."""
    meta = _suite.build_all_meta()
    assert meta["T091"]["cls"] == "FEATURE", meta["T091"]["cls"]
    assert meta["T091"]["cls_declared"], "T091 is FEATURE by seed, not by declaration"
    rows, errors = C.parse_ledger()
    assert not errors, errors
    assert ("gating-flake", "T091") not in rows, rows


def case_the_ledger_is_retired_again():
    """TASK-595's sweep reopened this ledger for exactly one row — T084, CORE,
    an `undeclared-flake-call` that could not be declared (that is an F1) and
    whose conversion needed hardware the host-only sweep did not have.

    The hardware run happened the same day: T084 PASSed 3/3 against a verified
    build, and the race its "KNOWN INTERMITTENT" comment blamed was removed at
    source by running the round-trip inside `_bgpoll_suspended`. Its four
    `flake()` calls became typed reads plus `fail()`, the F7 finding stopped
    occurring, and the row went stale — so the file was deleted per its own
    retirement rule, for the second time (the first was T091/TASK-591).

    This case pins the END state, not the interlude: no ledger file, and T084
    still CORE with a reachable fail(). If a future sweep reopens the ledger it
    must do so deliberately and update this case, which is the point."""
    assert not os.path.exists(os.path.join(C.ROOT, C.LEDGER_REL)), (
        f"{C.LEDGER_REL} exists again — if that is deliberate, say which row "
        f"and why here; an exemption kind with no rows is an invitation to "
        f"open one")
    rows, errors = C.parse_ledger()
    assert not errors, errors
    assert rows == {} or set(rows) == set(), rows
    meta = _suite.build_all_meta()
    assert meta["T084"]["cls"] == "CORE", meta["T084"]["cls"]


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
    """The full live check, exactly as main() drives it: F1-F8 together, over
    the real registry, the real ledger, and the real call-site scan."""
    reg, err = _flaky.get_registry()
    assert err is None, err
    ledger, errors = C.parse_ledger()
    assert not errors, errors
    call_sites = C.flake_call_sites()
    none(C.evaluate(reg.entries, reg.candidates, _suite.build_all_meta(), ledger,
                    call_sites=call_sites, today=datetime.date.today()))


# ── F6: a declaration with no call site (TASK-595 / C-7) ────────────────────

def case_f6_declared_with_no_call_site():
    """T_PLR_17/T_PMT_04/T_WR_COEX_01's exact shape before TASK-595 removed
    their declarations: declared, class FEATURE (not gating — F1 must stay
    silent), zero real flake() call sites."""
    fs = C.evaluate({"T_X_01": object()}, {}, rec("FEATURE"), call_sites={})
    one(fs, "F6 T_X_01")
    assert not [f for f in fs if f.startswith("F1")], fs


def case_f6_declared_with_a_call_site_is_fine():
    fs = C.evaluate({"T_X_01": object()}, {}, rec("FEATURE"),
                    call_sites={"T_X_01": ["shell.py:1"]})
    none(fs)


def case_f6_skipped_when_call_sites_none():
    """Back-compat: every pre-TASK-595 fixture call omits call_sites, and must
    keep behaving exactly as it did before F6 existed."""
    none(C.evaluate({"T_X_01": object()}, {}, rec("FEATURE")))


# ── F7: a real call site for an undeclared id (TASK-595 / C-7) ──────────────

def case_f7_call_site_undeclared():
    """T084/T092/T_PLR_07/T_WR_EJECT_01's exact shape before TASK-595: a real
    flake() call site naming an id with no flaky.yaml entry."""
    fs = C.evaluate({}, {}, rec("FEATURE"), call_sites={"T_X_01": ["shell.py:9"]})
    one(fs, "F7 T_X_01")
    one(fs, "shell.py:9")


def case_f7_call_site_declared_is_fine():
    fs = C.evaluate({"T_X_01": object()}, {}, rec("FEATURE"),
                    call_sites={"T_X_01": ["shell.py:9"]})
    none(fs)


def case_f7_ledger_suppresses_its_key_only():
    """T084's live shape: CORE, undeclared, ledgered under
    'undeclared-flake-call' — F7 goes quiet for T084 but a second undeclared
    CORE id (T_X_02) must still be reported, or the ledger is a wildcard."""
    meta = {}
    meta.update(rec("CORE", tid="T_X_01"))
    meta.update(rec("CORE", tid="T_X_02"))
    ledger = {("undeclared-flake-call", "T_X_01"): "ledger.md:1"}
    fs = C.evaluate({}, {}, meta, ledger,
                    call_sites={"T_X_01": ["a.py:1"], "T_X_02": ["a.py:2"]})
    assert not [f for f in fs if "T_X_01" in f], fs
    one(fs, "F7 T_X_02")


def case_f7_stale_ledger_row_fails():
    """The call site is gone (the flake() call was removed or the id was
    declared) — the row must go with it, exactly like F1's L2."""
    ledger = {("undeclared-flake-call", "T_X_01"): "ledger.md:3"}
    fs = C.evaluate({}, {}, rec("CORE"), ledger, call_sites={})
    one(fs, "F4 ledger.md:3")
    one(fs, "delete this row")


# ── F8: rule 3, an expired declaration (TASK-595 / C-7) ──────────────────────

class _FakeEntry:
    """Just enough of FlakyEntry's shape for F8: `.is_expired()`, `.review_by`,
    `.owner`, `.task`. Not a real dataclass — the point is that F8 must work
    off any object with this shape, the same duck-typing lib/flaky.py itself
    relies on."""
    def __init__(self, review_by, owner="@VE", task="TASK-999"):
        self.review_by = review_by
        self.owner = owner
        self.task = task

    def is_expired(self, today):
        return today > self.review_by


def case_f8_expired_entry_fails():
    entry = _FakeEntry(datetime.date(2026, 1, 1))
    fs = C.evaluate({"T_X_01": entry}, {}, rec("FEATURE"),
                    today=datetime.date(2026, 2, 1))
    one(fs, "F8 T_X_01")
    one(fs, "31 day")


def case_f8_not_expired_is_fine():
    entry = _FakeEntry(datetime.date(2026, 6, 1))
    none(C.evaluate({"T_X_01": entry}, {}, rec("FEATURE"),
                    today=datetime.date(2026, 2, 1)))


def case_f8_skipped_when_today_none():
    """Back-compat: pre-TASK-595 fixtures never pass today= and must not
    suddenly start needing a `.is_expired()` on their sentinel objects."""
    none(C.evaluate({"T_X_01": object()}, {}, rec("FEATURE")))


def case_f8_sentinel_without_review_by_is_exempt():
    """A fixture that DOES pass today= but whose declared value is a bare
    sentinel (no `.is_expired`) must not crash — F8 is opt-in per-entry, not
    just per-call."""
    none(C.evaluate({"T_X_01": object()}, {}, rec("FEATURE"),
                    today=datetime.date(2026, 2, 1)))


# ── flake_call_sites() itself ────────────────────────────────────────────────

def case_flake_call_sites_ignores_prose():
    """A `cls_reason` string that just talks about `flake()` in prose — no
    literal ast.Call — must never be mistaken for a call site. shell.py's own
    T084/T091 cls_reason paragraphs are exactly this shape (they say
    "`flake()`" in a docstring/decorator string, with no arguments)."""
    with tempfile.TemporaryDirectory() as d:
        Path(os.path.join(d, "fake.py")).write_text(
            '"""a module whose docstring mentions flake() and even flake("T_NOPE") '
            'as prose, never as code."""\n'
            "# comment: flake(\"T_ALSO_NOPE\") not a call either\n"
            "def real():\n"
            "    flake(\"T_REAL\", \"a real reason\")\n",
            encoding="utf-8")
        sites = C.flake_call_sites(d)
    assert set(sites) == {"T_REAL"}, sites


def case_flake_call_sites_matches_live_grep():
    """Cross-check against an independent instrument: a plain-text grep for
    `flake("...` should name the same id set the AST scan finds, over the real
    suite tree. If these two disagree, believe neither until it is understood."""
    import re
    import subprocess
    out = subprocess.run(
        ["grep", "-rhoE", r'flake\("[A-Za-z0-9_-]+"', C.SUITE_DIR_REL],
        cwd=C.ROOT, capture_output=True, text=True, check=False).stdout
    grepped = {m.group(1) for m in re.finditer(r'flake\("([A-Za-z0-9_-]+)"', out)}
    assert grepped, "grep found nothing — the fixture path is wrong"
    ast_found = set(C.flake_call_sites())
    assert ast_found == grepped, (ast_found, grepped)


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
    ("P1  T091's 2026-09-04 retirement holds",   case_t091_retirement_still_holds),
    ("P1b the ledger is retired again (zero)",   case_the_ledger_is_retired_again),
    ("P2  the live corpus is AT zero",           case_live_registry_state_is_at_zero),
    ("P3  live run is green at zero rows",       case_live_run_is_green_with_the_ledger),
    ("F6a declared, no call site",               case_f6_declared_with_no_call_site),
    ("F6b declared, has a call site: fine",      case_f6_declared_with_a_call_site_is_fine),
    ("F6c call_sites=None skips F6 (back-compat)", case_f6_skipped_when_call_sites_none),
    ("F7a call site, undeclared",                case_f7_call_site_undeclared),
    ("F7b call site, declared: fine",             case_f7_call_site_declared_is_fine),
    ("F7c ledger suppresses one F7 key only",     case_f7_ledger_suppresses_its_key_only),
    ("F7d stale F7 ledger row fails",             case_f7_stale_ledger_row_fails),
    ("F8a expired entry fails",                   case_f8_expired_entry_fails),
    ("F8b not-yet-expired entry is fine",         case_f8_not_expired_is_fine),
    ("F8c today=None skips F8 (back-compat)",     case_f8_skipped_when_today_none),
    ("F8d sentinel without review_by is exempt",  case_f8_sentinel_without_review_by_is_exempt),
    ("S1  flake_call_sites finds only real Calls", case_flake_call_sites_ignores_prose),
    ("S2  AST call sites == an independent grep", case_flake_call_sites_matches_live_grep),
]


def main() -> int:
    return _case_runner.run_cases("test_check_flake_class", CASES)


if __name__ == "__main__":
    sys.exit(main())
