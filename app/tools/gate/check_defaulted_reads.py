#!/usr/bin/env python3
"""check_defaulted_reads.py — no oracle or restore may be satisfied by a default.
TASK-596 / M-HARNESS2 R18.

THE DEFECT. A suite body reads device state as `int(r.get("val", 0))`. When the
reply is missing, wrong-shaped, or belongs to a different question, the read
yields the default, the default is the same TYPE as a real reading, and the
comparison that follows cannot tell the difference. WP-A counted seven distinct
defaults for that one field, six of them values a comparison can pass on. WP-G
then found what that costs: `_stock_ok_count` returned `-1`, `_wait_chart_complete(-1)`
was satisfied by its own first poll, and the Stock family's central fetch oracle
was an unconditional pass across nine ids (`G-2`). TASK-585 fixed that instance.
This gate exists so the shape cannot grow back.

R18 IS A RATCHET (§12 of the requirements), not a flag day: the count is the
migration plan. So the gate is blocking, and it is blocking against a DATED,
PER-FILE, SHRINK-ONLY ledger — `docs/verification/defaulted_reads_ratchet.md`.
A file may hold at most the number of defaulted reply reads its row allows. Land
one more and the gate is red; delete some and the gate REQUIRES the row be
lowered to match (a ratchet that is not tightened when it can be is a ratchet
that has stopped ratcheting, and is how a ledger becomes wallpaper).

WHAT IT COUNTS — and the reason it is a taint walk rather than a grep. A grep for
`.get("val",` finds 31 sites and misses every reply field that is not called
`val` (`ms`, `name`, `busy`, `remainingMs`, `count`, …); WP-A's own histogram is
that grep, which is why its figure understates the surface by a factor of five.
This walks each module, marks the local names bound from a device-reply call
(`dut.cmd`, `dut.read_json`, `dut.read_json_multi`, `read_reply`, and the family
wrappers that return a raw reply dict), and counts two-argument `.get(<str>, <expr>)`
calls on those names. Non-reply dicts — meta records, registries, coordinate
tables — are untouched, because they were never a device read and defaulting one
is not a lie about hardware.

WHAT IT DELIBERATELY DOES NOT COUNT. A one-argument `r.get("val")` yields `None`,
which is not a value a numeric or string comparison passes on — it is the
failing direction, and converting those is a different (larger, lower-value)
migration. Counting them here would triple the ledger without separating the
sites that can manufacture a green.

  D1  no module exceeds its ledgered count.
  D2  no ledger row is stale — a row above the real count must be lowered.
  D3  no ledger row names a module that does not exist.
  D4  the ledger is not a blanket: every row carries an owning TASK id and an
      ISO date, and there are no wildcards.
  D5  `lib/` itself holds ZERO defaulted reply reads, unledgered and
      unexemptable. The accessor lives there; a default in the shared layer is
      the one that reaches every caller at once.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_defaulted_reads.py [--verbose] [--print-counts]
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

LEDGER_REL = "docs/verification/defaulted_reads_ratchet.md"

#: Methods on a Dut whose return value IS a device reply dict.
REPLY_METHODS = frozenset({"cmd", "read_json", "read_json_multi", "read_reply"})

#: Free functions in the suite that return a raw reply dict unchanged. These are
#: pass-throughs, not accessors: a default on their result is the same defect one
#: call deep. Deliberately a short, explicit list — a heuristic on the NAME
#: ("anything starting with `_get`") would silently start counting, or stop
#: counting, whenever somebody renamed a helper.
REPLY_HELPERS = frozenset({"_stock_get"})

#: Scanned roots, relative to app/tools.
SCAN_ROOTS = ("suite", "lib")

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")


def _is_reply_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if isinstance(fn, ast.Attribute) and fn.attr in REPLY_METHODS:
        return True
    if isinstance(fn, ast.Name) and fn.id in REPLY_HELPERS:
        return True
    return False


def defaulted_reads(src: str) -> list:
    """-> [(lineno, key)] for every two-arg `.get()` on a device reply.

    Pure and string-in, so the negative suite can drive it with fixtures rather
    than with files on disk.
    """
    tree = ast.parse(src)
    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    hits: dict = {}
    for scope in scopes:
        tainted = set()
        for n in ast.walk(scope):
            if isinstance(n, ast.Assign) and _is_reply_call(n.value):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        tainted.add(t.id)
            elif isinstance(n, ast.For) and _is_reply_call(n.iter):
                if isinstance(n.target, ast.Name):
                    tainted.add(n.target.id)
            elif isinstance(n, ast.withitem) and _is_reply_call(n.context_expr):
                if isinstance(n.optional_vars, ast.Name):
                    tainted.add(n.optional_vars.id)
        for n in ast.walk(scope):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "get" and len(n.args) == 2):
                continue
            if not (isinstance(n.args[0], ast.Constant)
                    and isinstance(n.args[0].value, str)):
                continue
            recv = n.func.value
            if (isinstance(recv, ast.Name) and recv.id in tainted) or _is_reply_call(recv):
                hits[(n.lineno, n.col_offset)] = n.args[0].value
    return [(ln, key) for (ln, _col), key in sorted(hits.items())]


def scan(root: str = None) -> dict:
    """-> {module_rel_path: count} over SCAN_ROOTS."""
    root = root or TOOLS
    out: dict = {}
    for sub in SCAN_ROOTS:
        base = os.path.join(root, sub)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                with open(path, encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
                try:
                    out[rel] = len(defaulted_reads(src))
                except SyntaxError as e:
                    out[rel] = -1
                    print(f"  (unparseable: {rel}: {e})", file=sys.stderr)
    return out


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({module: (cap, 'rel:line')}, [errors]).

    Same shape and same rules as the other two ledgers in this repo
    (`check_docs.py:_parse_ledger`, `check_flake_class.py:parse_ledger`): an
    owning TASK id and an ISO `since` date on every row, no wildcards.

    AN ABSENT FILE FAILS CLOSED: it parses to zero rows, so every module with a
    nonzero count is over its (absent) cap and the gate goes red. The ledger can
    only ever make this check more lenient, so losing it cannot hide anything.
    """
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
            errors.append(f"D4 {rel}:{i}: module {mod!r} is a wildcard — a ratchet "
                          f"row names one file")
            continue
        try:
            cap = int(cap_s)
        except ValueError:
            errors.append(f"D4 {rel}:{i}: cap {cap_s!r} is not an integer")
            continue
        if not _TASK_RE.match(owner):
            errors.append(f"D4 {rel}:{i}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"D4 {rel}:{i}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[mod] = (cap, f"{rel}:{i}")
    return rows, errors


def evaluate(counts: dict, ledger: dict) -> list:
    """Pure: the findings. `counts` is {module: n}, `ledger` is {module: (cap, where)}."""
    out: list = []
    for mod in sorted(counts):
        n = counts[mod]
        if n < 0:
            out.append(f"D1 {mod}: unparseable — the ratchet cannot be measured")
            continue
        cap, where = ledger.get(mod, (0, None))
        if mod.startswith("lib/") and mod in ledger:
            out.append(
                f"D5 {mod}: `lib/` may not hold a ratchet row at all ({where}). The "
                f"typed accessor lives here; a defaulted reply read in the shared "
                f"layer reaches every caller at once. Delete the row and the read")
            cap = 0
        if n > cap:
            out.append(
                f"D1 {mod}: {n} defaulted reply reads, cap {cap}"
                + (f" ({where})" if where else " (no ledger row)")
                + f". A `.get(<key>, <literal>)` on a device reply gives a failed "
                  f"read the same type as a real one — R18. Use dut.get_int/"
                  f"get_str/get_bool/get_val, which raise")
        elif n < cap:
            out.append(
                f"D2 {where}: {mod} is ledgered at {cap} but holds {n} — lower the "
                f"row to {n}. The ledger is shrink-only, and a cap above the real "
                f"count is headroom to reintroduce the defect")
    for mod, (cap, where) in sorted(ledger.items()):
        if mod not in counts:
            out.append(f"D3 {where}: {mod} is ledgered but no such module exists — "
                       f"delete the row")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--print-counts", action="store_true",
                    help="print the per-module counts (how you refresh the ledger)")
    args = ap.parse_args()

    counts = scan()
    ledger, lerrs = parse_ledger()
    findings = lerrs + evaluate(counts, ledger)

    if args.print_counts:
        for mod in sorted(counts):
            if counts[mod]:
                print(f"| `{mod}` | {counts[mod]} | TASK-596 | "
                      f"{datetime.date.today().isoformat()} |")
    if args.verbose:
        total = sum(v for v in counts.values() if v > 0)
        print(f"defaulted reply reads: {total} across "
              f"{sum(1 for v in counts.values() if v > 0)} modules; "
              f"{len(ledger)} ledger rows")

    if findings:
        print(f"FAIL: check_defaulted_reads.py — {len(findings)} finding(s) "
              f"(TASK-596 / R18):")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"OK: check_defaulted_reads.py — "
          f"{sum(v for v in counts.values() if v > 0)} defaulted reply reads, "
          f"all within the shrink-only ratchet ({len(ledger)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
