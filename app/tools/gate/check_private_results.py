#!/usr/bin/env python3
"""check_private_results.py — one results layer, not five. TASK-646 / WP-A A-6.

WHY THIS EXISTS. TASK-520 unified the result layer into `lib/results.py` and
migrated `ve_suite_base.py` and the serialdbg runner onto it. `run_sync_tests.py`
was not migrated, and nobody noticed for a year, because a private copy of a
results layer LOOKS EXACTLY LIKE the shared one at the call site: `pass_(tid)`,
`fail(tid, why)`, `skip(tid, why)`. The divergence is invisible in the test
bodies and total in the reporting.

What those twenty ids lost while nobody was looking: the flaky policy and its
mandated retry, `NOT-RUN`, `UNMET`, the typed store, the verdict invariants, and
— once TASK-608 landed — the run artifact, i.e. any machine interface at all.
`run/test-sync` was a DUT suite whose verdicts existed only as prose.

WHAT IT ASSERTS. Nothing in `app/tools/` may define a verdict recorder except
`lib/results.py`:

  R1  a module-level `def` named `pass_`, `skip`, `flake`, `not_run`, `unmet`,
      `print_results` or `run_with_flake_retry`. These names have exactly one
      meaning in this tree.
  R2  a module-level `def fail(...)` taking TWO OR MORE positional parameters.
      The arity is the discriminator and it is not a heuristic: a verdict
      recorder takes an ID and a reason, while the `fail(msg)` that three host
      probes define is an abort helper that prints and exits — a different
      function with a colliding name, and flagging it would teach people to
      exempt the gate rather than fix it.
  R3  a module-level binding of the name `RESULTS`. The store is the part a
      private copy cannot fake sharing.

Findings are zero today except one ledgered row. No DUT, no build, no network.
Sub-second.

    python3 app/tools/gate/check_private_results.py [--list]
"""

from __future__ import annotations

import ast
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

LEDGER_REL = "docs/verification/private_results_exceptions.md"

#: The one module allowed to define the layer.
OWNER = "app/tools/lib/results.py"

RECORDER_NAMES = ("pass_", "skip", "flake", "not_run", "unmet",
                  "print_results", "run_with_flake_retry")

_SKIP_DIRS = {"__pycache__", ".runs", "testdata", "fixtures"}

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")


def _files(root: str = None):
    root = root or ROOT
    base = os.path.join(root, "app", "tools")
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                yield os.path.relpath(p, root).replace(os.sep, "/"), p


def findings(root: str = None) -> list:
    """-> [(rel, lineno, rule, detail)]."""
    out = []
    for rel, path in _files(root):
        if rel == OWNER:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                tree = ast.parse(fh.read(), path)
        except SyntaxError as e:
            out.append((rel, e.lineno or 1, "R0", f"SyntaxError: {e.msg}"))
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in RECORDER_NAMES:
                    out.append((rel, node.lineno, "R1",
                                f"def {node.name}() — a verdict recorder; "
                                f"import it from lib.results"))
                elif node.name == "fail":
                    args = node.args
                    n = len(args.posonlyargs) + len(args.args)
                    if n >= 2:
                        out.append((rel, node.lineno, "R2",
                                    f"def fail() takes {n} positional args — "
                                    f"that is `fail(tid, reason)`, a verdict "
                                    f"recorder; import it from lib.results"))
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "RESULTS":
                        out.append((rel, node.lineno, "R3",
                                    "a private RESULTS store"))
            elif (isinstance(node, ast.AnnAssign)
                  and isinstance(node.target, ast.Name)
                  and node.target.id == "RESULTS"):
                out.append((rel, node.lineno, "R3", "a private RESULTS store"))
    return out


# ── the ledger (BP-074: blocking, dated, shrink-only) ────────────────────────

def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({(rel, rule): 'ledger:line'}, [malformed-row errors]).

    Same shape and rules as the R37/R36 ledgers: an owning TASK id and an ISO
    `since` date on every row, no wildcards.
    """
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
    rel_led = os.path.relpath(path, ROOT).replace(os.sep, "/")
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
        target, rule, owner, since = (cells[0].strip("`* "), cells[1].strip("`* "),
                                      cells[2].strip("`* "), cells[3].strip("`* "))
        if not _TASK_RE.match(owner):
            errors.append(f"{rel_led}:{i}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"{rel_led}:{i}: since {since!r} is not ISO YYYY-MM-DD")
            continue
        rows[(target, rule)] = f"{rel_led}:{i}"
    return rows, errors


def main() -> int:
    verbose = "--list" in sys.argv
    found = findings()
    ledger, errors = parse_ledger()
    print("=== check_private_results.py — one results layer (TASK-646/A-6) ===")

    unexcepted = []
    used = set()
    for rel, lineno, rule, detail in found:
        if (rel, rule) in ledger:
            used.add((rel, rule))
            if verbose:
                print(f"  [ledgered] {rel}:{lineno} {rule} — {detail}")
            continue
        unexcepted.append((rel, lineno, rule, detail))

    for rel, lineno, rule, detail in unexcepted:
        print(f"  FAIL: {rel}:{lineno}: {rule} {detail}")

    # A ledger row that no longer matches anything is a STALE row, and a stale
    # row is itself a blocking failure (the standing Phase 1 condition). The
    # alternative — a ledger that quietly keeps rows for defects somebody
    # already fixed — is how an exception list stops shrinking.
    stale = sorted(set(ledger) - used)
    for key in stale:
        print(f"  FAIL: {ledger[key]}: stale exception for {key[0]} {key[1]} — "
              f"the finding is gone; delete the row")
    for e in errors:
        print(f"  FAIL: {e}")

    bad = len(unexcepted) + len(stale) + len(errors)
    print(f"\n=== {len(found)} recorder definition(s) outside {OWNER}; "
          f"{len(ledger)} ledgered, {bad} blocking ===")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
