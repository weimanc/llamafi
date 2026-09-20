#!/usr/bin/env python3
"""check_timeout_literals.py — R24's own verification clause: "count of numeric
`timeout=` literals in `suite/`, ratcheted to zero." TASK-607 / M-HARNESS2 R24.

THE DEFECT (A-11). `app/tools/lib/dut.py` declares one timeout policy — `TIMEOUT`
(default) and `TIMEOUT_SLOW` (slow-operation override) — and, before TASK-607,
had zero users: 715 numeric `timeout=` literals sat in `app/tools/suite/`, 446 of
them exactly `TIMEOUT`'s default (`3.0`) and 20 exactly `TIMEOUT_SLOW`'s (`10.0`).
A declared policy nobody reads is not a policy, it's a docstring.

WHAT TASK-607 DID. A mechanical, keyword-position-only substitution of the two
EXACT populations: every `timeout=3.0` became `timeout=TIMEOUT`, every
`timeout=10.0` became `timeout=TIMEOUT_SLOW`. Both constants keep their
pre-migration default values, so no call site's effective timeout changed.
446 + 20 = 466 literals migrated; 715 - 466 = 249 remain.

WHY THE REMAINING 249 ARE NOT MIGRATED. They are call-site-specific values —
`2.0`, `5.0`, `8.0`, `15.0`, `20.0`, `30.0`, `65.0`, `120.0`, `180.0`, ... — and
R24's own ruling forbids inventing new policy constants to absorb them ("a
policy with six constants is a rename of the problem, not a fix"). Folding a
value that means something specific (a short poll interval vs. a multi-minute
soak wait) into `TIMEOUT`/`TIMEOUT_SLOW` would be a SILENT BEHAVIOUR CHANGE —
exactly what R24's own migration ruling forbids doing without proof. So they
stay literals, and this gate prices them the way `check_restore_manager.py`
prices R17's 197 (now 181) unmanaged mutations: a dated, per-module,
SHRINK-ONLY ledger — `docs/verification/timeout_literal_ratchet.md` — enforced
in BOTH directions, same shape, same reasoning. A cap above the real count is
headroom to reintroduce the defect and is itself a failure.

WHAT THIS GATE COUNTS. Every occurrence of `timeout=<number>` (an int or float
literal, no leading sign, no scientific notation — none exist in the corpus) in
a `.py` file under `app/tools/suite/`. `timeout=TIMEOUT`, `timeout=TIMEOUT_SLOW`,
`timeout=some_var`, `timeout=_FETCH_TIMEOUT` — anything that isn't a bare numeric
literal at that position — does not match, because those are already policy
users (or named, call-site-specific constants), which is the point.
`app/tools/lib/` is OUT OF SCOPE: R24's verification clause says "in `suite/`",
and the policy module itself living in `lib/` is a different question from
`unrestored_mutations_ratchet.md`'s M5 (which keeps `lib/` at zero-and-
unledgered) — this ratchet has no equivalent rule because the policy module
has no bare numeric `timeout=` literals to count either way.

  T1  no module exceeds its ledgered count of numeric `timeout=` literals.
  T2  no ledger row is stale — a row above the real count must be lowered.
  T3  no ledger row names a module that does not exist under `app/tools/suite/`.
  T4  every row carries an owning TASK id and an ISO date; no wildcards.

Wired into `app/tools/smoke_test.sh` (NOT `check_build.sh` — that file pins
`TOTAL=11` at line 26 and the counted gate total must not move; every host-side
check added since lives inside `check_build.sh`'s gate 8, `smoke_test.sh`).

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_timeout_literals.py [--verbose] [--print-counts]
                                                      [--list <module>]
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

LEDGER_REL = "docs/verification/timeout_literal_ratchet.md"
SCAN_ROOT = "suite"  # app/tools/suite/ — R24's own verification clause: "in suite/"

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")

# `timeout=` immediately followed by a bare numeric literal: int or float,
# no sign (none in the corpus carry one), no scientific notation. Anything
# else at that position (a NAME, an attribute, a call) is already a policy
# user or a named constant and must not match.
TIMEOUT_LITERAL_RE = re.compile(r"timeout=[0-9]+\.?[0-9]*")


def scan(root: str = None) -> tuple:
    """-> ({module: count}, {module: [(line, literal)]}) over app/tools/suite/."""
    root = root or TOOLS
    counts: dict = {}
    detail: dict = {}
    base = os.path.join(root, SCAN_ROOT)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            sites = []
            for i, line in enumerate(lines, 1):
                for m in TIMEOUT_LITERAL_RE.finditer(line):
                    sites.append((i, m.group(0)))
            counts[rel] = len(sites)
            detail[rel] = sites
    return counts, detail


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({module: (cap, 'rel:line')}, [errors]). Same shape as the sibling
    ratchets in this repo (`unrestored_mutations_ratchet.md`,
    `gen_app_registry.py`'s staleness ledger, ...). AN ABSENT FILE FAILS
    CLOSED (zero rows -> every nonzero module is over cap)."""
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
                f"T1 {mod}: {n} numeric timeout= literals, cap {cap}"
                + (f" ({where})" if where else " (no ledger row)")
                + f". Migrate exact TIMEOUT/TIMEOUT_SLOW-default values onto "
                  f"the policy constants (lib.dut.TIMEOUT/TIMEOUT_SLOW), or give "
                  f"a call-site-specific value a named module-level constant — "
                  f"either way the literal moves out of `timeout=<number>` "
                  f"position (R24)")
        elif n < cap:
            out.append(
                f"T2 {where}: {mod} is ledgered at {cap} but holds {n} — lower "
                f"the row to {n}. The ledger is shrink-only, and a cap above "
                f"the real count is headroom to reintroduce the defect")
    for mod, (cap, where) in sorted(ledger.items()):
        if mod not in counts:
            out.append(f"T3 {where}: {mod} is ledgered but no such module exists "
                       f"under app/tools/{SCAN_ROOT}/ — delete the row")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--print-counts", action="store_true",
                    help="print the per-module rows (how you refresh the ledger)")
    ap.add_argument("--list", metavar="MODULE",
                    help="print every numeric timeout= literal in one module")
    args = ap.parse_args()

    counts, detail = scan()
    ledger, lerrs = parse_ledger()
    findings = lerrs + evaluate(counts, ledger)

    if args.print_counts:
        for mod in sorted(counts, key=lambda m: -counts[m]):
            if counts[mod]:
                print(f"| `{mod}` | {counts[mod]} | TASK-607 | "
                      f"{datetime.date.today().isoformat()} |")
    if args.list:
        for ln, lit in detail.get(args.list, []):
            print(f"{args.list}:{ln}: {lit}")
    if args.verbose:
        total = sum(counts.values())
        print(f"numeric timeout= literals: {total} across "
              f"{sum(1 for v in counts.values() if v)} modules; "
              f"{len(ledger)} ledger rows")

    if findings:
        print(f"FAIL: check_timeout_literals.py — {len(findings)} finding(s) "
              f"(TASK-607 / R24):")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"OK: check_timeout_literals.py — {sum(counts.values())} numeric "
          f"timeout= literals, all within the shrink-only ratchet "
          f"({len(ledger)} rows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
