#!/usr/bin/env python3
"""check_production_symbols.py — the production ELF carries zero SERIAL_DEBUG
symbols. TASK-707, automating T089 (docs/verification/test_plan.md), whose
only prior evidence was a one-time manual `strings | grep -c SERIAL_DEBUG` run
on 2026-05-17. Nothing has re-verified it since, and every `#ifdef
SERIAL_DEBUG` block added in the meantime (dozens, across app/src/) has
shipped leaning on that single five-month-old data point.

WHY `nm`, NOT `strings`/`grep`. TASK-707 asks for this explicitly. A text grep
over the ELF is a coincidence detector in both directions:

  * false positive — any string literal anywhere in the binary that happens to
    contain "SERIAL_DEBUG" (a log message, a comment baked into __FILE__/
    assert text, a docstring some tool embeds) fails a build that shipped no
    debug code at all.
  * false negative — a debug-only symbol whose *name* does not literally
    contain "SERIAL_DEBUG" (which is every symbol here — `cmdGet`, `dbgTimeSet`,
    etc. are gated BY the macro, not named after it) is invisible to that grep
    entirely. The 2026-05-17 manual run passed only because nothing was being
    checked for.

`nm` reads the ELF's actual linked symbol table. A marker symbol appearing
there is not "a string that looks like debug code somewhere in the binary" —
it is a compiled, linked function or object, which cannot exist unless the
translation unit that defines it was compiled with SERIAL_DEBUG set.

MARKER CHOICE: a small curated list, not a name-pattern regex. The candidates
below are not "functions related to debugging" — they are functions whose
*entire definition* sits inside a single `#ifdef SERIAL_DEBUG` / `#endif` pair
that spans the whole translation unit (see each file's own header comment,
e.g. cmdGet.cpp: "Body compiles only under SERIAL_DEBUG; the .cpp itself is
always compiled"). That means in a production build these names are not
merely unreferenced (which dead-code elimination could remove either way) —
they are never compiled at all, so their absence from the symbol table is a
structural property of the source, not an artifact of the linker's garbage
collection settings. A regex like `serialConsole|dbgTime` would be broader but
weaker: it would also match comments, unrelated symbols that happen to share a
prefix, or a future refactor's unrelated helper — the curated list is
maintainable specifically because failing it means "one of these exact named
functions got linked into production", which is always a real regression to
look at, not a naming coincidence to explain away.

    cmdGet, cmdSet              debug/serialConsole/cmdGet.cpp, cmdSet.cpp
    cmdSwitchApp, cmdInfo,
    cmdScreenDump, cmdColorProbe,
    cmdSerialBurst              debug/serialConsole/cmdMisc.cpp
    cmdReboot, cmdAdvance,
    cmdHelp                     debug/serialConsole/cmdSystem.cpp
    cmdSdMem, cmdSdProbe        debug/serialConsole/cmdSd.cpp
    cmdTap                      debug/serialConsole/cmdTouch.cpp
    dbgTimeSet, dbgTimeThaw,
    dbgTimeFrozen               debug/timeInject.cpp (ADR-064 D5; timeInject.h
                                 itself only declares these under SERIAL_DEBUG,
                                 so there is no dangling-declaration case to
                                 confuse this list either)

Regressing this gate looks like: someone hoists a `cmdXxx` handler (or
`dbgTimeXxx`) out from under its `#ifdef SERIAL_DEBUG` guard — accidentally
(a merge that widens the guard's scope) or on purpose without updating the
call sites that assume it doesn't exist in production (e.g. `armedInjectors.h`
consumers, or anything reachable from the always-shipped console dispatch
table in console.cpp). Either way the fix is the same: put the guard back, or
if the function is meant to ship now, retire its marker row here with a
comment saying why.

WHAT IT ASSERTS.

  1. `nm -C` over the production ELF (`cyd2usb_winamp`) contains NONE of the
     marker symbols.
  2. `nm -C` over the DEBUG ELF (`cyd2usb_winamp_debug`) contains ALL of the
     marker symbols — the sanity check that this list can actually tell a
     debug build from a production one, not just "is this name linked into
     anything, ever, anywhere". Without this arm, a marker list that has
     silently gone stale (e.g. every one of these functions got renamed) would
     PASS the production check for the wrong reason: not because production is
     clean, but because the check no longer means anything.

Building the ELF is NOT this script's job — it assumes both already exist
(built by an earlier `run/check`/smoke_test.sh step, or manually) and refuses
with a clear message naming the `pio run` command if either is missing. This
script never builds, flashes, or opens a serial port.

    python3 app/tools/gate/check_production_symbols.py [--verbose]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
APP = os.path.dirname(TOOLS)
ROOT = os.path.dirname(APP)

PROD_ENV = "cyd2usb_winamp"
DEBUG_ENV = "cyd2usb_winamp_debug"

PROD_ELF = os.path.join(APP, ".pio", "build", PROD_ENV, "firmware.elf")
DEBUG_ELF = os.path.join(APP, ".pio", "build", DEBUG_ENV, "firmware.elf")

#: See the module docstring for why each of these, and what regressing looks
#: like. Every entry here is a bare (unmangled, undemangled) C++ function name
#: with no namespace — matched against `nm -C` output with a word boundary so
#: e.g. "cmdGet" cannot accidentally match a future "cmdGetSomethingElse".
MARKER_SYMBOLS: tuple[str, ...] = (
    "cmdGet", "cmdSet",
    "cmdSwitchApp", "cmdInfo", "cmdScreenDump", "cmdColorProbe", "cmdSerialBurst",
    "cmdReboot", "cmdAdvance", "cmdHelp",
    "cmdSdMem", "cmdSdProbe",
    "cmdTap",
    "dbgTimeSet", "dbgTimeThaw", "dbgTimeFrozen",
)


def _marker_regex(name: str) -> re.Pattern:
    # `\b` before is enough on the left (names are ASCII identifiers); on the
    # right we require the following char NOT continue an identifier — cheaper
    # and just as safe as demanding a literal "(" (works for both functions
    # and, if a future marker is a plain object, non-function symbols too).
    return re.compile(r'\b' + re.escape(name) + r'\b(?!\w)')


def run_nm(elf_path: str) -> list[str]:
    """All symbol names (demangled) nm reports for an ELF, defined or not —
    a marker's ABSENCE from this whole list is the strong claim (never
    compiled), so both tables are relevant."""
    proc = subprocess.run(
        ["nm", "-C", "--defined-only", elf_path],
        capture_output=True, text=True, check=True)
    proc_undef = subprocess.run(
        ["nm", "-C", "-u", elf_path],
        capture_output=True, text=True, check=True)
    # Kept as whole lines, not split into fields: every caller only
    # substring/regex-searches this list, and the raw line already contains
    # the demangled name regardless of whether it's a defined or undefined
    # row.
    lines = []
    for line in (proc.stdout + "\n" + proc_undef.stdout).splitlines():
        line = line.strip()
        if line:
            lines.append(line)
    return lines


def find_markers(symbol_lines: list[str], markers: tuple[str, ...] = MARKER_SYMBOLS) -> list[str]:
    """Pure: which markers appear (as a real identifier, not a prefix) in a
    list of `nm` output lines. Returns the sorted list of markers found."""
    haystack = "\n".join(symbol_lines)
    found = []
    for m in markers:
        if _marker_regex(m).search(haystack):
            found.append(m)
    return sorted(found)


def _missing_elf_message(elf_path: str, env: str) -> str:
    return (f"{elf_path} does not exist.\n"
            f"  This gate reads an already-built ELF; it does not build one.\n"
            f"  Run:  cd app && pio run -e {env}\n"
            f"  (or ~/.platformio/penv/bin/pio if pio is not on PATH), then re-run this gate.")


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv

    if not os.path.isfile(PROD_ELF):
        print(f"FAIL: {_missing_elf_message(PROD_ELF, PROD_ENV)}", file=sys.stderr)
        return 2
    if not os.path.isfile(DEBUG_ELF):
        print(f"FAIL: {_missing_elf_message(DEBUG_ELF, DEBUG_ENV)}", file=sys.stderr)
        return 2

    prod_lines = run_nm(PROD_ELF)
    debug_lines = run_nm(DEBUG_ELF)

    prod_hits = find_markers(prod_lines)
    debug_hits = find_markers(debug_lines)
    debug_misses = sorted(set(MARKER_SYMBOLS) - set(debug_hits))

    print(f"check_production_symbols: {len(MARKER_SYMBOLS)} marker symbols, "
          f"checked against {PROD_ENV} (production) and {DEBUG_ENV} (debug)")
    if verbose:
        print(f"  production ELF: {PROD_ELF}")
        print(f"  debug ELF:      {DEBUG_ELF}")
        print(f"  markers: {', '.join(MARKER_SYMBOLS)}")

    failures: list[str] = []
    if prod_hits:
        failures.append(
            f"{len(prod_hits)} SERIAL_DEBUG marker symbol(s) linked into the "
            f"PRODUCTION ELF ({PROD_ENV}): {', '.join(prod_hits)} — one of "
            f"these was compiled outside its SERIAL_DEBUG guard")
    if debug_misses:
        failures.append(
            f"{len(debug_misses)} marker symbol(s) MISSING from the DEBUG ELF "
            f"({DEBUG_ENV}): {', '.join(debug_misses)} — the marker list has "
            f"gone stale (renamed/removed symbols) and can no longer prove "
            f"anything about production; update MARKER_SYMBOLS")

    if failures:
        print(f"\nFAIL: {len(failures)} finding(s)")
        for f in failures:
            print(f"  {f}")
        return 1

    print(f"  PASS  0/{len(MARKER_SYMBOLS)} markers in production; "
          f"{len(debug_hits)}/{len(MARKER_SYMBOLS)} markers confirmed present "
          f"in debug (the check can tell the builds apart)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
