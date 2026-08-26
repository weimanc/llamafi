#!/usr/bin/env python3
"""check_suite_serialdbg_names.py — cross-file Name-reference gate for
suite/serialdbg/ (TASK-480/TASK-545).

WHY THIS EXISTS. TASK-480 split run_serialdbg_tests.py (10 005 lines, one flat
module) into one module per app family under suite/serialdbg/. A pure code
MOVE cannot introduce a logic bug, but it can absolutely introduce a missing
IMPORT: a helper that looked private to one family turned out to be called by
another (this happened three times during the split — _drain_data_pipeline,
_tap_and_wait_log, _tb_precondition, each caught only after a DUT run threw
a live NameError). Python does not catch this at import time — a name used
only inside a function body is resolved at CALL time, so a module with a
missing import parses and imports cleanly and then blows up hours into a DUT
run, the most expensive place to find it.

This gate finds it for free, in well under a second, with no DUT involved:
walk every suite/serialdbg/*.py file's AST, and for every function (including
nested closures — a false positive here is exactly the kind of noise that
gets a real gate turned off) collect the names visible to it (builtins,
module-level imports/defs/assignments, its own parameters and locals, and
its enclosing functions' same), then flag any Name loaded but never bound.

Run directly, or via app/tools/smoke_test.sh (run/check gate 9).

    python3 app/tools/gate/check_suite_serialdbg_names.py
"""

from __future__ import annotations

import ast
import builtins
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SUITE_DIR = os.path.join(ROOT, "app", "tools", "suite", "serialdbg")

# Names Python binds implicitly at module scope that never appear as an
# ast.Import/Assign/FunctionDef node — flagging these would be a permanent
# false positive, not a real gap.
_IMPLICIT_MODULE_NAMES = {"__file__", "__name__", "__doc__", "__package__",
                           "__loader__", "__spec__", "__builtins__"}


def _module_level_names(tree: ast.Module) -> set[str]:
    """Names bound at module scope: imports, top-level defs, top-level assigns."""
    names: set[str] = set(dir(builtins)) | _IMPLICIT_MODULE_NAMES

    def _collect_targets(t: ast.expr, into: set[str]) -> None:
        if isinstance(t, ast.Name):
            into.add(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                _collect_targets(e, into)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                _collect_targets(t, names)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.For, ast.With)):
            # module-level `for`/`with` targets (rare in this tree, cheap to cover)
            targets = node.target if isinstance(node, ast.For) else None
            if targets is not None:
                _collect_targets(targets, names)

    return names


def _find_undefined(fn: ast.AST, outer_scope: set[str]) -> list[tuple[str, int]]:
    """Return [(name, lineno)] for every Name loaded in `fn` (and its nested
    functions, recursively) that isn't resolvable from outer_scope + fn's own
    parameters/locals/nested-def-names. This is a deliberately conservative,
    whole-function-body scope (not per-block) — it will not catch a genuine
    use-before-def within one function, only cross-file/cross-scope gaps,
    which is the class of bug this gate exists for.
    """
    problems: list[tuple[str, int]] = []
    local = set(outer_scope)

    args = fn.args
    for arg in list(args.args) + list(args.posonlyargs) + list(args.kwonlyargs):
        local.add(arg.arg)
    if args.vararg:
        local.add(args.vararg.arg)
    if args.kwarg:
        local.add(args.kwarg.arg)

    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            local.add(node.name)
        elif isinstance(node, ast.arg):
            local.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local.add(node.name)

    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in local:
                problems.append((node.id, node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not fn:
            problems.extend(_find_undefined(node, local))

    return problems


def check_file(path: str) -> list[tuple[str, str, int]]:
    """Return [(function_name, undefined_name, lineno)] for one file."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    tree = ast.parse(src, path)
    module_scope = _module_level_names(tree)

    findings: list[tuple[str, str, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for name, lineno in _find_undefined(node, module_scope):
                findings.append((node.name, name, lineno))
    return findings


def main() -> int:
    if not os.path.isdir(SUITE_DIR):
        print(f"  [note] {SUITE_DIR} not found — nothing to check")
        return 0

    files = sorted(f for f in os.listdir(SUITE_DIR) if f.endswith(".py"))
    total_findings = 0
    print("=== check_suite_serialdbg_names.py — cross-file Name-reference gate ===")
    for name in files:
        path = os.path.join(SUITE_DIR, name)
        try:
            findings = check_file(path)
        except SyntaxError as e:
            print(f"  FAIL: suite/serialdbg/{name}: SyntaxError: {e}")
            total_findings += 1
            continue
        if findings:
            for fn, undefined, lineno in findings:
                print(f"  FAIL: suite/serialdbg/{name}:{lineno} in {fn}(): "
                      f"undefined name {undefined!r} (missing import?)")
            total_findings += len(findings)
        else:
            print(f"  [ok] suite/serialdbg/{name}: {len(findings)} undefined names")

    if total_findings:
        print(f"\n=== {total_findings} undefined-name finding(s) — likely a missing "
              f"cross-family import ===")
        return 1
    print(f"\n=== {len(files)} suite/serialdbg/*.py files clean — no undefined names ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
