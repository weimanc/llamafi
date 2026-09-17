#!/usr/bin/env python3
"""Negative tests for check_production_symbols.py — BP-068 ("a gate that has
never been seen to fail is not a gate"). TASK-707.

`find_markers()` is pure — a list of `nm` output lines in, a list of markers
found out — precisely so this file can drive every interesting case without
needing real `.elf` files or a working `pio` toolchain. `main()` itself is
exercised only against real ELFs by the gate's own --verbose run in TASK-707's
verification, not here.

Cases:
  * a marker symbol present in a "production" fixture -> that IS the
    production-side failure this gate exists to catch.
  * a clean fixture (no markers) -> PASS shape.
  * the debug-sanity-check direction: a marker missing from the "debug"
    fixture list -> also a failure (the check itself would be broken).
  * word-boundary correctness: a longer name that merely contains a marker as
    a substring must NOT count as a hit.

No DUT, no serial port, no build, no network.
Run: python3 app/tools/gate/test_check_production_symbols.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _case_runner  # noqa: E402

import check_production_symbols as C                      # noqa: E402


def one(fs, needle):
    hits = [f for f in fs if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {fs}"
    return hits


def none(fs):
    assert not fs, f"expected no findings, got {fs}"


# ── find_markers() itself ────────────────────────────────────────────────────

def case_marker_present_is_found():
    lines = ["0000000000012345 T cmdGet(char const*)"]
    found = C.find_markers(lines, markers=("cmdGet", "cmdSet"))
    assert found == ["cmdGet"], found


def case_no_markers_present_is_empty():
    lines = ["0000000000012345 T setup()", "0000000000012346 T loop()"]
    found = C.find_markers(lines, markers=("cmdGet", "cmdSet"))
    none(found)


def case_undefined_row_still_counts():
    """A marker can show up as `U <name>` (referenced, not defined here) —
    that still proves the name was linked into this ELF and must count."""
    lines = ["                 U dbgTimeSet(long, bool)"]
    found = C.find_markers(lines, markers=("dbgTimeSet",))
    assert found == ["dbgTimeSet"], found


def case_substring_prefix_does_not_false_positive():
    """A longer, unrelated name that merely starts with a marker's spelling
    must not count — this is the word-boundary property that keeps the list
    maintainable instead of turning into a prefix-match trap."""
    lines = ["0000000000012345 T cmdGetSomethingElseEntirely(char const*)"]
    found = C.find_markers(lines, markers=("cmdGet",))
    none(found)


def case_multiple_markers_all_found():
    lines = [
        "0000000000012345 T cmdGet(char const*)",
        "0000000000012346 T cmdSet(char const*)",
        "0000000000012347 T dbgTimeThaw()",
    ]
    found = C.find_markers(lines, markers=("cmdGet", "cmdSet", "dbgTimeThaw", "cmdTap"))
    assert found == ["cmdSet", "cmdGet", "dbgTimeThaw"] or found == sorted(
        ["cmdGet", "cmdSet", "dbgTimeThaw"]), found
    assert set(found) == {"cmdGet", "cmdSet", "dbgTimeThaw"}, found


# ── the two directions main() drives, via find_markers() fixtures ──────────
# (main() itself needs real ELF files on disk; these cases pin the SAME logic
# main() runs its findings through, without needing pio or a flashed board.)

def case_production_fixture_with_a_marker_must_fail():
    """The production-side check: any marker hit in the "production" symbol
    table is exactly the regression T089/TASK-707 exists to catch — a
    SERIAL_DEBUG-guarded function got compiled into a shipping build."""
    prod_lines = ["0000000000012345 T cmdScreenDump(char const*)"]
    prod_hits = C.find_markers(prod_lines)
    assert prod_hits == ["cmdScreenDump"], prod_hits
    # main()'s failure branch is `if prod_hits:` — non-empty means FAIL.
    assert prod_hits, "a marker in the production fixture must be a finding"


def case_clean_production_fixture_passes():
    prod_lines = ["0000000000012345 T setup()", "0000000000012346 T loop()"]
    prod_hits = C.find_markers(prod_lines)
    none(prod_hits)


def case_debug_fixture_missing_a_marker_must_fail():
    """The sanity-check direction: if the DEBUG build doesn't even contain a
    marker, the marker list itself is broken (stale/renamed) and the
    production-side PASS above would mean nothing. main() computes this as
    `set(MARKER_SYMBOLS) - set(debug_hits)`."""
    debug_lines = [f"0000000000012345 T {m}(char const*)"
                   for m in C.MARKER_SYMBOLS if m != "dbgTimeThaw"]
    debug_hits = C.find_markers(debug_lines)
    debug_misses = sorted(set(C.MARKER_SYMBOLS) - set(debug_hits))
    assert debug_misses == ["dbgTimeThaw"], debug_misses


def case_debug_fixture_with_every_marker_passes():
    debug_lines = [f"0000000000012345 T {m}(char const*)" for m in C.MARKER_SYMBOLS]
    debug_hits = C.find_markers(debug_lines)
    debug_misses = sorted(set(C.MARKER_SYMBOLS) - set(debug_hits))
    none(debug_misses)


# ── missing-ELF refusal (no build, no network — just checks the message) ────

def case_missing_elf_message_names_the_build_command():
    msg = C._missing_elf_message("/nonexistent/firmware.elf", "cyd2usb_winamp")
    assert "pio run -e cyd2usb_winamp" in msg, msg
    assert "/nonexistent/firmware.elf" in msg, msg


def case_main_refuses_cleanly_when_prod_elf_absent(monkeypatch=None):
    """main() must exit 2 (not crash, not attempt a build) when the production
    ELF is missing. Point both ELF paths at nonexistent files."""
    orig_prod, orig_debug = C.PROD_ELF, C.DEBUG_ELF
    try:
        C.PROD_ELF = "/nonexistent/does-not-exist-prod.elf"
        C.DEBUG_ELF = "/nonexistent/does-not-exist-debug.elf"
        rc = C.main([])
        assert rc == 2, rc
    finally:
        C.PROD_ELF, C.DEBUG_ELF = orig_prod, orig_debug


CASES = [
    ("marker present is found",                  case_marker_present_is_found),
    ("no markers present is empty",               case_no_markers_present_is_empty),
    ("undefined (U) row still counts",            case_undefined_row_still_counts),
    ("substring prefix is not a false positive",  case_substring_prefix_does_not_false_positive),
    ("multiple markers all found",                case_multiple_markers_all_found),
    ("production fixture WITH a marker fails",    case_production_fixture_with_a_marker_must_fail),
    ("clean production fixture passes",           case_clean_production_fixture_passes),
    ("debug fixture MISSING a marker fails",      case_debug_fixture_missing_a_marker_must_fail),
    ("debug fixture with every marker passes",    case_debug_fixture_with_every_marker_passes),
    ("missing-ELF message names the pio command", case_missing_elf_message_names_the_build_command),
    ("main() refuses cleanly, no ELF, rc=2",      case_main_refuses_cleanly_when_prod_elf_absent),
]


def main() -> int:
    return _case_runner.run_cases("test_check_production_symbols", CASES)


if __name__ == "__main__":
    sys.exit(main())
