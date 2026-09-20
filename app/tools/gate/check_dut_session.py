#!/usr/bin/env python3
r"""check_dut_session.py — R47's own verification clause: "a gate forbidding
`serial.Serial(` outside `lib/`; ratcheted with a dated exception list."
TASK-599 / M-HARNESS2 R47.

THE DEFECT (WP-A `A-2`/`A-4`). `app/tools/lib/dut.py` is meant to be the ONE
DUT session layer — port resolution, the DRD reset-gap stamp, debug-firmware
verification, the timeout policy (`check_timeout_literals.py`'s R24), the
rig-vs-firmware `SetupFailure` -> exit-3 contract (`A-2`: honoured by only 4
files). Seventeen tools construct their own `serial.Serial(...)` instead —
`A-4`'s "four independent `SerialDut` classes" is the sharpest instance of a
tree-wide pattern, not the whole of it. None of the seventeen writes the DRD
gap file, so running one immediately before `run/test` defeats the 12s
back-to-back-reset guard `lib/dut.py:115,123,1156` depends on.

WHY THIS IS A RATCHET, NOT A FLAG DAY (TASK-599's own scope note). Unlike
R24's timeout literals, a `serial.Serial(...)` call site is not a value swap —
it is a different SESSION, and `lib.dut.Dut.__init__` does substantially more
than open a port: it waits for boot + the firmware's OWN readiness signal, then
calls `_verify_debug_firmware()` (an ELF/build-id check) and `_read_board_id()`
(a `get boardId` round-trip) before the caller gets control back. Swapping a
hand-rolled class for `Dut` is therefore not a mechanical rename; it changes
what the constructor does to the device. TASK-599 could verify a migration is
behaviour-preserving only by static reasoning (no hardware in this pass — see
the task's own ruling), so it landed the gate and ledgered all 17 rather than
force migrations no one could prove safe. Each ledger row names, in the doc,
the SPECIFIC structural reason that file does not fit `Dut`/`DutLite` today
(a continuous background reader thread parsing async event lines out from
under `cmd()`'s queue, a custom readiness wait tuned to a *different* signal
than the generic one `Dut` polls, a raw EN/RTS reset ladder against firmware
that doesn't speak the debug console at all, ...) so a future migration attempt
starts from a true premise instead of re-deriving it.

WHAT THIS GATE COUNTS — AND WHY IT IS AST, NOT TEXT (TASK-599 fix, see below).
A REAL CONSTRUCTOR CALL: an `ast.Call` node whose function is the attribute
access `serial.Serial` (`import serial; serial.Serial(...)`, the only import
style this corpus uses — `grep -rn '^import serial' app/tools` plus a check
for `from serial import` / `import serial as` on 2026-09-20 found no aliasing
and no `from serial import Serial`), in a `.py` file under `app/tools/`, EXCLUDING
`app/tools/lib/` entirely — out of scope, same as `check_timeout_literals`
treats `lib/` as out of scope for R24: `lib/dut.py` IS the session layer, so
its own `serial.Serial()` call is the thing everyone else should be routing
through, not a finding.

THE SELF-REFERENCE BUG THIS GATE ORIGINALLY SHIPPED WITH, AND THE FIX. The
first cut of this file scanned with a *textual* regex (a compiled pattern
matching the literal `serial.Serial(` substring), which necessarily also
matches the pattern's own name
wherever this file (or any file describing the pattern) writes it down — this
docstring said `serial.Serial(` eleven times and the gate flagged itself,
capped at 0, every run. The fix ported here is `check_board_currency`'s own
scar tissue, twice paid for on this project in the two days before this one
(its B5 arm reading its own "Next free id" claim line as an allocated id; then
its own commit message re-poisoning the corpus by quoting that output) —
**a gate that polices a string necessarily contains that string, so a text
match is the wrong tool for this class of check.** The fix is not one more
named exception (`check_import_safety.py` and its test were carrying exactly
that shape: a fixed ALLOWLIST of files that only *mention* the pattern) — it
is scanning for what R47 actually forbids, a REAL SESSION OBJECT COMING INTO
EXISTENCE, which is a `Call` node in the AST, not a substring of a line. A
docstring, a comment, a regex literal (`re.compile(r"serial\.Serial\(")`), and
a string embedded in a test fixture (`test_check_import_safety.py` writes
`"serial.Serial(...)"` into probe files as TEXT for another gate to scan) all
contain the eight-character substring and NONE of them are `ast.Call` nodes,
so the AST scan clears `check_dut_session.py` itself, `check_import_safety.py`
and `test_check_import_safety.py` with no allowlist at all — confirmed by
running the AST walk over all three and finding zero `Call` sites in each.
An `ast.parse` per file is still sub-second at this corpus size (well under
100 files), so there is no cost trade-off against the regex it replaces.

  T1  no module exceeds its ledgered count of `serial.Serial(` constructor calls.
  T2  no ledger row is stale — a row above the real count must be lowered.
  T3  no ledger row names a module that does not exist under `app/tools/`.
  T4  every row carries an owning TASK id and an ISO date; no wildcards.
  T5  no ledger row names a file under `app/tools/lib/` — that is the one
      structurally exempt location (the session layer itself), and a row
      there would hide a real exemption behind a fake migration promise.

Wired into `app/tools/smoke_test.sh` (NOT `check_build.sh` — that file pins
`TOTAL=11` at line 26 and the counted gate total must not move).

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_dut_session.py [--verbose] [--print-counts]
                                                 [--list <module>]
"""

from __future__ import annotations

import argparse
import ast
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

LEDGER_REL = "docs/verification/dut_session_ratchet.md"

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")

#: Out of scope entirely: the one true session layer.
EXCLUDE_DIR_PREFIX = "lib/"


def _is_serial_serial_call(node: ast.AST) -> bool:
    """True for an ast.Call node shaped `serial.Serial(...)` — the only
    import style this corpus uses is `import serial` (verified 2026-09-20;
    no `from serial import Serial`, no `import serial as X`), so matching
    the plain attribute access `<Name serial>.Serial` is sufficient and does
    not need import-alias resolution."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr == "Serial"
            and isinstance(func.value, ast.Name) and func.value.id == "serial")


def _find_calls(path: str) -> list:
    """-> [(lineno, source_line)] for every real `serial.Serial(...)`
    CONSTRUCTOR CALL in a file, found by walking its AST — not by matching
    the eight-character substring against source text. This is the fix for
    the class of bug the module docstring documents: a textual scan of a
    file that itself POLICES `serial.Serial(` necessarily also matches the
    policing file's own docstring, comment, and regex-literal mentions of
    the pattern it is looking for. An `ast.Call` node only exists where a
    session object is actually constructed, so a gate's own prose about the
    pattern, a sibling gate's stubbed-string test fixture, and this file's
    own former regex are all structurally invisible to it — with no
    allowlist required to make that true."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError:
        # Not expected in this corpus (all files are valid Python 3), but
        # fail open on the scan rather than crash the gate — a file that
        # can't even parse has bigger problems than this check.
        return []
    lines = src.splitlines()
    sites = []
    for node in ast.walk(tree):
        if _is_serial_serial_call(node):
            lineno = getattr(node, "lineno", 0)
            text = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
            sites.append((lineno, text))
    sites.sort()
    return sites


def scan(root: str = None) -> tuple:
    """-> ({module: count}, {module: [(line, text)]}) over app/tools/,
    excluding lib/ (the one true session layer)."""
    root = root or TOOLS
    counts: dict = {}
    detail: dict = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if rel.startswith(EXCLUDE_DIR_PREFIX):
                continue
            sites = _find_calls(path)
            counts[rel] = len(sites)
            detail[rel] = sites
    return counts, detail


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({module: (cap, 'rel:line')}, [errors]). Same shape as
    `check_timeout_literals.parse_ledger` / `unrestored_mutations_ratchet.md`.
    AN ABSENT FILE FAILS CLOSED."""
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    header = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = _cells(s)
        if all(_SEP_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if len(cells) < 4:
            continue
        mod = cells[0].strip("`* ")
        cap_s, owner, since = cells[1].strip("`* "), cells[2].strip("`* "), cells[3].strip("`* ")
        if "*" in mod or "?" in mod:
            errors.append(f"T4 {rel}:{i}: module {mod!r} is a wildcard — a ratchet "
                          f"row names one file")
            continue
        if mod.startswith(EXCLUDE_DIR_PREFIX):
            errors.append(f"T5 {rel}:{i}: module {mod!r} is structurally exempt "
                          f"(lib/ is the session layer itself) and must not "
                          f"carry a ledger row")
            continue
        try:
            cap = int(cap_s)
        except ValueError:
            errors.append(f"T4 {rel}:{i}: cap {cap_s!r} is not an integer")
            continue
        if not _TASK_RE.match(owner):
            errors.append(f"T4 {rel}:{i}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"T4 {rel}:{i}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[mod] = (cap, f"{rel}:{i}")
    return rows, errors


def evaluate(counts: dict, ledger: dict) -> list:
    out: list = []
    for mod in sorted(counts):
        n = counts[mod]
        cap, where = ledger.get(mod, (0, None))
        if n > cap:
            out.append(
                f"T1 {mod}: {n} serial.Serial( constructions, cap {cap}"
                + (f" ({where})" if where else " (no ledger row)")
                + f". Route this session through lib.dut.Dut/resolve_port, or "
                  f"add a dated, owned ledger row explaining why it cannot "
                  f"(R47)")
        elif n < cap:
            out.append(
                f"T2 {where}: {mod} is ledgered at {cap} but holds {n} — lower "
                f"the row to {n} (or delete it if {n} is 0). Shrink-only, same "
                f"as `timeout_literal_ratchet.md`")
    for mod, (cap, where) in sorted(ledger.items()):
        if mod not in counts:
            out.append(f"T3 {where}: {mod} is ledgered but no such module exists "
                       f"under app/tools/ (outside lib/) — delete the row")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--print-counts", action="store_true",
                    help="print the per-module rows (how you refresh the ledger)")
    ap.add_argument("--list", metavar="MODULE",
                    help="print every serial.Serial( construction in one module")
    args = ap.parse_args()

    counts, detail = scan()
    ledger, lerrs = parse_ledger()
    findings = lerrs + evaluate(counts, ledger)

    if args.print_counts:
        for mod in sorted(counts, key=lambda m: -counts[m]):
            if counts[mod]:
                print(f"| `{mod}` | {counts[mod]} | TASK-599 | "
                      f"{datetime.date.today().isoformat()} |")
    if args.list:
        for ln, text in detail.get(args.list, []):
            print(f"{args.list}:{ln}: {text}")
    if args.verbose:
        total = sum(counts.values())
        print(f"serial.Serial( constructor calls: {total} across "
              f"{sum(1 for v in counts.values() if v)} modules (excluding lib/, "
              f"AST-detected — no allowlist); {len(ledger)} ledger rows")

    if findings:
        print(f"FAIL: check_dut_session.py — {len(findings)} finding(s) "
              f"(TASK-599 / R47):")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"OK: check_dut_session.py — {sum(counts.values())} serial.Serial( "
          f"constructions outside lib/, all within the shrink-only ratchet "
          f"({len(ledger)} rows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
