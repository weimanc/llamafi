#!/usr/bin/env python3
"""Negative tests for check_no_mirrors.py — BP-068. TASK-606 / M-HARNESS2 R42.

A mirror-equality gate that has never been seen to fail is not a gate — the
exact failure mode R42 exists to convert into a build failure is a SILENT one,
so this suite pins that silence is impossible at every layer:

  * the generic firmware-source parsers (`find_define_int`, `find_constexpr_int`,
    `find_enum_values`, `find_all_string_arrays`) return the right value when
    the symbol is present, and a clearly-absent value (never `0`, never a
    false "found") when it is not;
  * a pair that agrees passes (`Finding.ok is True`);
  * a pair that disagrees is a finding, not a skip;
  * a pair whose firmware symbol cannot be found by name is ALSO a finding —
    this is the specific failure mode `gen_get_keys.py`'s glob missed 43 of
    111 keys by (TASK-600/R7): a parser that returns "nothing matched" must
    not be indistinguishable from "matched and it's fine";
  * the live corpus (today's actual suite + firmware source) is AT ZERO —
    every registered pair agrees right now, which is this gate's whole
    justification for landing MUST/blocking on day one rather than advisory.

NO LEDGER. Unlike `check_flake_class.py`/`check_test_meta.py`, this gate does
not carry a grandfather ledger, and this suite does not pin a "stale ledger
row" case for that reason: ruling 1 requires a gate land "at zero, or
blocking with a ... ledger" — this one lands AT ZERO (every one of the
register entries agrees once seeded), so no ledger exists to go stale.
(TASK-715 removed A-8 and H-12 outright once clock.py/teletext.py stopped
mirroring — the register is now seven entries, not the original nine; a
pair with no remaining suite-side literal to compare would just compare a
parsed value to itself, so it was deleted, not converted.) The
correct thing for this suite to pin instead is that no such ledger
mechanism/path was quietly added (a ledger nobody wrote the "shrink-only,
dated, owned" rules for is worse than no ledger) — `test_no_ledger_mechanism_exists`
below.

No DUT, no serial port, no build, no network.
Run: python3 app/tools/gate/test_check_no_mirrors.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import _case_runner  # noqa: E402

import check_no_mirrors as C  # noqa: E402


# ── generic parser primitives ───────────────────────────────────────────────

def case_define_int_basic():
    text = "#define FOO 42   // a comment\n#define BAR 7\n"
    assert C.find_define_int(text, "FOO") == 42
    assert C.find_define_int(text, "BAR") == 7


def case_define_int_missing_is_none():
    text = "#define FOO 42\n"
    assert C.find_define_int(text, "NOPE") is None


def case_define_int_non_numeric_is_none():
    # e.g. `#define S_CANVAS_W APP_CANVAS_W` — an alias, not a literal. Must
    # not silently coerce to some int (there is none to coerce to).
    text = "#define ALIAS SOME_OTHER_SYMBOL\n"
    assert C.find_define_int(text, "ALIAS") is None


def case_constexpr_int_basic_all_types():
    text = (
        "static constexpr uint8_t A = 21;\n"
        "constexpr int16_t B = 28;\n"
        "static constexpr int C = -3;\n"
        "constexpr uint32_t D = 12000;\n"
    )
    assert C.find_constexpr_int(text, "A") == 21
    assert C.find_constexpr_int(text, "B") == 28
    assert C.find_constexpr_int(text, "C") == -3
    assert C.find_constexpr_int(text, "D") == 12000


def case_constexpr_int_missing_is_none():
    text = "static constexpr int A = 1;\n"
    assert C.find_constexpr_int(text, "NOPE") is None


def case_constexpr_expr_returns_raw_text_not_a_guessed_int():
    # TASKBAR_APP_COUNT's real shape: an expression, not a literal. Must not
    # be silently coerced or evaluated — the caller (check_c13) is expected
    # to fall back to a different, generated source for the number and use
    # this only as a structural sanity check.
    text = "static constexpr int TASKBAR_APP_COUNT = (int)AppId::Settings + 1;\n"
    val = C.find_constexpr_int(text, "TASKBAR_APP_COUNT")
    assert val == "(int)AppId::Settings + 1", val


def case_enum_values_defaults_and_explicit():
    text = (
        "enum FetchType : uint8_t {\n"
        "    A = 0,\n"
        "    B = 1,\n"
        "    C = 2,\n"
        "    D = 5,\n"
        "    E,\n"
        "};\n"
    )
    vals = C.find_enum_values(text, "FetchType")
    assert vals == {"A": 0, "B": 1, "C": 2, "D": 5, "E": 6}, vals


def case_enum_values_missing_enum_is_empty_not_partial():
    text = "enum OtherType { X = 0 };\n"
    assert C.find_enum_values(text, "FetchType") == {}


def case_string_array_all_occurrences_found():
    text = (
        'static const char* kPmNames[]  = { "Spotify", "WebRadio", "Player" };\n'
        "other code here\n"
        'static const char* kPmNames[] = { "Spotify", "WebRadio", "DRIFTED" };\n'
    )
    arrays = C.find_all_string_arrays(text, "kPmNames")
    assert arrays == [
        ("Spotify", "WebRadio", "Player"),
        ("Spotify", "WebRadio", "DRIFTED"),
    ], arrays


def case_string_array_missing_is_empty_list_not_none():
    assert C.find_all_string_arrays("no arrays here", "kPmNames") == []


# ── Finding-level: agree / disagree / not-found, via a real check function ──

def case_h19_pair_agrees_when_help_string_matches_app_count():
    fake_text = '{ "switchApp", cmdSwitchApp, "switch active app by id", "<appId 0..12>" },\n'
    with mock.patch.object(C, "_read", return_value=fake_text):
        f = C.check_h19()
    assert f.ok is True, f.note
    assert f.suite_val == 12 and f.fw_val == 12


def case_h19_pair_is_a_finding_when_values_disagree():
    """A drifted literal must produce ok=False — this is the live-drift case
    ruling 1 says to report loudly, not silently average away."""
    fake_text = '{ "switchApp", cmdSwitchApp, "switch active app by id", "<appId 0..8>" },\n'
    with mock.patch.object(C, "_read", return_value=fake_text):
        f = C.check_h19()
    assert f.ok is False
    assert f.suite_val == 8 and f.fw_val == 12


def case_h19_pair_is_a_finding_when_symbol_not_found():
    """No 'switchApp' row at all in the (fake) firmware source -> ok=False,
    NOT a silent skip/pass. This is the check_get_keys.py scar (TASK-600/R7):
    'nothing matched' must never read the same as 'matched and it's fine'."""
    fake_text = "// switchApp row was deleted\n"
    with mock.patch.object(C, "_read", return_value=fake_text):
        f = C.check_h19()
    assert f.ok is False
    assert f.suite_val is None


def case_a10_fetchtype_finding_when_enum_missing():
    with mock.patch.object(C, "_read", return_value="// no FetchType enum here\n"):
        f = C.check_a10_fetchtype()
    assert f.ok is False
    assert f.fw_val is None


def case_a10_playermodes_finding_when_no_kpmnames_anywhere():
    with mock.patch.object(C, "_read", return_value="// nothing here\n"):
        f = C.check_a10_playermodes()
    assert f.ok is False
    assert "no kPmNames" in f.note


def case_a10_playermodes_finding_when_firmware_copies_disagree_with_each_other():
    """Fabricate the exact confusion the review's own citation had: TWO
    non-identical kPmNames[] copies. Neither can be silently trusted — the
    finding must fire and say so."""
    texts = {
        "app/src/debug/serialConsole/cmdGet.cpp":
            'static const char* kPmNames[] = { "Spotify", "WebRadio", "Player" };\n',
        "app/src/debug/serialConsole/cmdSet.cpp":
            'static const char* kPmNames[] = { "Spotify", "WebRadio", "DRIFTED" };\n',
    }

    def fake_read(path):
        return texts[path]

    with mock.patch.object(C, "_read", side_effect=fake_read):
        f = C.check_a10_playermodes()
    assert f.ok is False
    assert "disagrees across kPmNames copies" in f.note, f.note


# ── the live corpus: at zero, by construction (this gate's own thesis) ─────

def case_live_run_all_pairs_agree():
    findings = C.run_all()
    bad = [f.id for f in findings if not f.ok]
    assert not bad, f"live mirror pairs disagree: {bad}"
    assert len(findings) == 9, (
        f"expected 9 encoded pairs (7 register entries — A-8 and H-12 removed "
        f"by TASK-715 — with A-10 and F-16 each split into sub-pairs), "
        f"got {len(findings)}: {[f.id for f in findings]}"
    )


def case_live_main_exits_zero():
    assert C.main() == 0


# ── no quiet ledger mechanism (see module docstring above) ─────────────────

def test_no_ledger_mechanism_exists():
    assert not hasattr(C, "parse_ledger"), (
        "a ledger mechanism appeared with no shrink-only/dated/owned rules "
        "written for it (ruling 1) — this gate is designed to land at zero, "
        "not to grow an unaudited exemption list"
    )


CASES = [
    ("define_int basic",                      case_define_int_basic),
    ("define_int missing -> None",             case_define_int_missing_is_none),
    ("define_int non-numeric -> None",         case_define_int_non_numeric_is_none),
    ("constexpr_int basic, all types",         case_constexpr_int_basic_all_types),
    ("constexpr_int missing -> None",          case_constexpr_int_missing_is_none),
    ("constexpr_int expr -> raw text",         case_constexpr_expr_returns_raw_text_not_a_guessed_int),
    ("enum_values defaults + explicit",        case_enum_values_defaults_and_explicit),
    ("enum_values missing enum -> {}",         case_enum_values_missing_enum_is_empty_not_partial),
    ("string_array all occurrences",           case_string_array_all_occurrences_found),
    ("string_array missing -> []",             case_string_array_missing_is_empty_list_not_none),
    ("H-19 pair agrees",                       case_h19_pair_agrees_when_help_string_matches_app_count),
    ("H-19 pair disagrees -> finding",         case_h19_pair_is_a_finding_when_values_disagree),
    ("H-19 symbol not found -> finding",       case_h19_pair_is_a_finding_when_symbol_not_found),
    ("A-10a enum missing -> finding",          case_a10_fetchtype_finding_when_enum_missing),
    ("A-10b no kPmNames anywhere -> finding",  case_a10_playermodes_finding_when_no_kpmnames_anywhere),
    ("A-10b firmware copies disagree -> finding", case_a10_playermodes_finding_when_firmware_copies_disagree_with_each_other),
    ("live: all 9 pairs agree",                case_live_run_all_pairs_agree),
    ("live: main() exits 0",                   case_live_main_exits_zero),
    ("no quiet ledger mechanism",              test_no_ledger_mechanism_exists),
]


def main() -> int:
    return _case_runner.run_cases("test_check_no_mirrors", CASES)


if __name__ == "__main__":
    sys.exit(main())
