#!/usr/bin/env python3
"""check_bound_origin.py — R44, delta-scoped. TASK-613.

R44 (docs/verification/M-HARNESS2-requirements.md:732-737, SHOULD): a numeric
bound in an assertion should cite either a parsed firmware constant or a
dated measurement with its method. The board row (docs/project/tasks-harness2.md)
scopes this task to a DELTA gate: a bound YOU TOUCH must cite its origin.
Over a thousand existing literals in the corpus are explicitly OUT of scope —
retrofitting them would drown the gate on day one, the same trap C1-delta
(check_docs.py) was built to avoid for doc citations.

WHAT COUNTS AS "A NUMERIC BOUND" (measured, see the module docstring's task
for the corpus scan). Scope is deliberately narrow, in two independent ways:

  1. Only literals inside a REGISTERED TEST BODY — a function that is a value
     in its module's `TESTS = {...}` dict — or in that same test's `bounds=`
     declaration on its `@meta(...)` decorator. Helper/infra functions
     (`_order.py`'s edge-shape analysis, `_meta.py`'s own recursion guard,
     `_helpers.py`'s generic accessors) are not assertions about DUT
     behaviour and are excluded entirely — measured: including them roughly
     doubled the candidate count with zero real bounds among the additions
     (index checks, sentinel checks, a static-analysis depth guard).

  2. Only INEQUALITY comparisons (`<`, `>`, `<=`, `>=`, including a chained
     `lo <= x <= hi` range, which is two inequality nodes) against a numeric
     literal, excluding the literal values {-1, 0, 1}. `==`/`!=` comparisons
     are excluded outright: measured across app/tools/suite/serialdbg/*.py,
     97 of 238 numeric-literal comparisons are `==`/`!=` against {-1,0,1}
     (`!= 0`, `> 0`, `== 1` — R44's own named trivia) and the remaining
     `==`/`!=` cases (89) are almost all exact-match checks against a
     protocol/state code or an expected exact count (`consecutiveFailures
     != 3`, `caps != 15`, `count != 20`) — identity claims, not thresholds
     with a margin that could be measured or derived, which is what R44's
     rationale (a leak bound, a no-loop window, a skip-pace interval) is
     about. Excluding trivia values from inequalities too (`heap <= 0`,
     `chart_len <= 0`) removes "is this set at all" checks, which carry no
     magnitude to justify.

  Applying both restrictions to the live corpus (measured 2026-09-20) finds
  29 candidate bounds total (26 in test bodies, 3 in `bounds={}` dicts) out
  of the original 238 numeric-literal comparisons — a ~88% reduction. Of
  those 29, eyeball review puts roughly 6 (~20%) as defensible "minimum
  sample size" preconditions rather than true thresholds (`len(pre) < 3`,
  `1 <= so <= 3`) rather than a measured/derived bound; the false-positive
  cost of flagging them anyway, when TOUCHED, is one added comment — cheap,
  and this is a SHOULD, so the narrower-but-imperfect rule is preferred over
  hand-tuning a name-based heuristic that would itself need justifying.

WHAT COUNTS AS A CITATION. The window searched is: the flagged line and 2
lines above/below it; the whole body of the enclosing test function (this
repo's convention is a decision block near the TOP of a test that a later
raw literal doesn't repeat, e.g. clock.py:190-206 documents T_CLK_11's 4096
many lines before the `if leak >= 4096:` that uses it); the test's
`@meta(...)` decorator (which is where a `bounds={}` value itself lives); and
any contiguous `#`-comment block immediately above that decorator. Within
that window, a citation is any of:

  * a `TASK-NNN` or `ADR-NNN` reference,
  * a `path.ext:NNN` or `path.ext:SYMBOL_NAME` citation (check_docs.py's own
    CITE_RE shape, generalised to a bare uppercase symbol as well as a line
    number, since a firmware citation more often names a `#define`/constexpr
    than a line),
  * the word "measured" co-occurring with an ISO date (`YYYY-MM-DD`) anywhere
    in the window.

`check_no_mirrors.py`'s registered (suite symbol, firmware symbol) PAIRS are
NOT treated as a citation here, on purpose: those pairs cover STRUCTURAL
mirrors (coordinates, enum values, app counts/slots) asserted equal to a
firmware fact at gate time — a different failure mode (R42/R43) from an
assertion THRESHOLD (a leak/latency/byte margin, R44). No pair in that
register's nine entries names a threshold, and nothing here special-cases a
literal just because check_no_mirrors happens to also run against the same
file — doing so would need the literal's exact source position machine-
matched to a pair definition (no such index exists; check_no_mirrors's pairs
are individually hand-coded functions, not a registry with recorded source
locations) and would silently full-corpus-launder the SEPARATE claim that a
citation exists.

`bounds={key: N}` declarations ARE in scope (decision, not left implicit):
they are numeric bounds recorded in the test's metadata, not merely in its
prose — `T_CLK_11`'s `bounds={"info.heap": 4096}` is R44's own cited example
of an unjustified 4096-byte leak bound, and it is a `bounds=` entry, not a
body literal. Excluding `bounds={}` would let exactly the defect R44 names
walk straight through this gate.

DELTA SCOPE. Only a bound on a line ADDED by the diff (git diff -M -C
--unified=0 <base>, TASK-613 reusing check_docs.py's C1-delta plumbing via
lib.gitdelta — see that module's docstring for why this is the one copy) AND
whose stripped text was not already present verbatim in the corpus at the
base rev (the same "relocated debt, not new debt" carve-out C1-delta uses)
is checked. An empty diff has no added lines, so this gate reads 0 by
construction on an unchanged tree — the "lands at zero" ruling doesn't need
its own ledger the way C6/ROWLEN's did.

    python3 app/tools/gate/check_bound_origin.py [--base SPEC] [--quiet]
"""
from __future__ import annotations

import argparse
import ast
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from lib import gitdelta as GD  # noqa: E402

SUITE_DIR = "app/tools/suite/serialdbg"
INEQ = (ast.Lt, ast.Gt, ast.LtE, ast.GtE)
TRIVIA_VALUES = {-1, 0, 1}

CITE_EXT = "h|hpp|cpp|c|py"
CITE_RE = re.compile(r"\b[\w./-]+\.(?:" + CITE_EXT + r"):(?:\d+|[A-Za-z_][A-Za-z0-9_]*)\b")
TASK_RE = re.compile(r"\bTASK-\d+\b")
ADR_RE = re.compile(r"\bADR-\d+\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
MEASURED_RE = re.compile(r"\bmeasured\b", re.IGNORECASE)


def is_gated_path(rel: str) -> bool:
    """True if `rel` is a flat *.py file directly inside SUITE_DIR.

    Deliberately non-recursive (no transcripts/ subdir — that holds JSON
    fixtures, not code) and deliberately not scoped further to "test family"
    modules only: `_helpers.py`/`_order.py`/`_meta.py` are included in the
    corpus walk (so a bound moved INTO one of them still hits the verbatim
    carve-out correctly), even though `is_bound_candidate` below never finds
    a candidate there today (no `TESTS` dict).
    """
    rel = rel.replace(os.sep, "/")
    if os.path.dirname(rel) != SUITE_DIR:
        return False
    return rel.endswith(".py")


def has_citation(window: str) -> bool:
    if TASK_RE.search(window) or ADR_RE.search(window) or CITE_RE.search(window):
        return True
    if MEASURED_RE.search(window) and DATE_RE.search(window):
        return True
    return False


def _decorator_call(fn: ast.FunctionDef, name: str) -> ast.Call | None:
    for d in fn.decorator_list:
        if not isinstance(d, ast.Call):
            continue
        target = d.func
        if isinstance(target, ast.Name) and target.id == name:
            return d
        if isinstance(target, ast.Attribute) and target.attr == name:
            return d
    return None


def _registered_test_names(tree: ast.Module) -> set[str]:
    """Function names that are values in this module's `TESTS = {...}` dict.

    This is the actual test registry (`build_all_tests()` assembles it from
    each family's `TESTS`), not "every function decorated with @meta" — most
    test bodies in this corpus carry NO `@meta` decorator at all (undeclared
    axes fall back to seeded defaults per `_meta.py`), so keying off the
    decorator would silently exclude most real test bodies.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "TESTS" not in targets:
                continue
            for v in node.value.values:
                if isinstance(v, ast.Name):
                    names.add(v.id)
                elif isinstance(v, ast.Attribute):
                    names.add(v.attr)
    return names




def _without_line(text: str, line: str) -> str:
    """`text` with the bound's own source line removed — see `prose_window`."""
    stripped = line.strip()
    return "\n".join(ln for ln in text.split("\n") if ln.strip() != stripped)

def _names_literal(text: str, value) -> bool:
    """Does `text` mention this literal, so a function-scope comment can be
    read as a citation OF THIS BOUND rather than of the test in general?

    Accepts the number as written (`4096`), with underscores (`30_000`) and
    with thousands separators (`30,000`), because all three appear in this
    suite's prose.
    """
    raw = repr(value) if isinstance(value, float) else str(value)
    variants = {raw, raw.replace("_", ""), f"{value:,}" if isinstance(value, int) else raw}
    return any(re.search(r"(?<![\w.])" + re.escape(v) + r"(?![\w.])", text)
               for v in variants)

def _comment_block_above(lines: list[str], start_line: int) -> str:
    """Contiguous `#`/blank lines immediately above `start_line` (1-based)."""
    out = []
    i = start_line - 2  # 0-based index of the line just above start_line (1-based)
    while i >= 0:
        s = lines[i].strip()
        if s == "" or s.startswith("#"):
            out.append(lines[i])
            i -= 1
        else:
            break
    out.reverse()
    return "\n".join(out)


class Candidate:
    __slots__ = ("file", "lineno", "value", "kind", "window", "stmt_text")

    def __init__(self, file, lineno, value, kind, window, stmt_text):
        self.file = file
        self.lineno = lineno
        self.value = value
        self.kind = kind          # "body" or "bounds"
        self.window = window
        self.stmt_text = stmt_text


def find_candidates(rel: str, content: str) -> list[Candidate]:
    """Every bound candidate in `content` (the HEAD-side text of `rel`)."""
    try:
        tree = ast.parse(content, filename=rel)
    except SyntaxError:
        return []
    lines = content.split("\n")
    test_names = _registered_test_names(tree)
    out: list[Candidate] = []

    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name not in test_names:
            continue
        fn_start = fn.lineno
        fn_end = getattr(fn, "end_lineno", fn.lineno)
        body_text = "\n".join(lines[fn_start - 1:fn_end])
        meta_call = _decorator_call(fn, "meta")
        deco_text = ""
        comment_above = ""
        if meta_call is not None:
            d_start = meta_call.lineno
            d_end = getattr(meta_call, "end_lineno", d_start)
            deco_text = "\n".join(lines[d_start - 1:d_end])
            comment_above = _comment_block_above(lines, d_start)
        docstring = ast.get_docstring(fn) or ""
        shared_window = "\n".join([comment_above, deco_text, docstring, body_text])
        # PROSE ONLY, for the function-scope half of the citation test. The
        # body cannot be used there: it CONTAINS the literal by construction —
        # the bound is a line of it — so "does the function mention this
        # number" is trivially true against code and says nothing. Comments
        # and the docstring are where a human explains a number.
        body_comments = "\n".join(ln for ln in lines[fn_start - 1:fn_end]
                                   if ln.strip().startswith("#"))
        prose_window = "\n".join([comment_above, deco_text, docstring,
                                   body_comments])

        # ── body inequality literals ────────────────────────────────────
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            consts: list[tuple[ast.AST, float | int]] = []
            for op, comparator in zip(node.ops, node.comparators):
                if (isinstance(op, INEQ) and isinstance(comparator, ast.Constant)
                        and isinstance(comparator.value, (int, float))
                        and not isinstance(comparator.value, bool)):
                    consts.append((comparator, comparator.value))
            if (isinstance(node.left, ast.Constant)
                    and isinstance(node.left.value, (int, float))
                    and not isinstance(node.left.value, bool)
                    and node.ops and isinstance(node.ops[0], INEQ)):
                consts.append((node.left, node.left.value))
            for src_node, value in consts:
                if value in TRIVIA_VALUES:
                    continue
                lineno = src_node.lineno
                local_lo = max(fn_start, lineno - 2) - 1
                local_hi = min(fn_end, lineno + 2)
                local_window = "\n".join(lines[local_lo:local_hi])
                # THE WINDOW IS LOCAL, PLUS A FUNCTION-SCOPE CITATION THAT
                # NAMES THE NUMBER. Measured on the real tree: an earlier
                # draft searched the whole enclosing body, and an uncited
                # `collisions > 7777` planted in `t_plr_22` PASSED — because
                # that body mentions TASK-695 in an unrelated comment about
                # restoring `plCursor`. Most suite bodies cite some task for
                # some reason, so a body-wide window makes this gate agree
                # with almost anything. A citation has to be attached to the
                # number, not merely co-located with it: either it is local to
                # the statement, or the function-scope prose names the literal
                # itself (which is how a shared comment documenting several
                # bounds still counts).
                scoped = (prose_window
                          if _names_literal(_without_line(prose_window,
                                                          lines[lineno - 1]), value)
                          else "")
                out.append(Candidate(
                    rel, lineno, value, "body",
                    scoped + "\n" + local_window,
                    lines[lineno - 1].strip()))

        # ── bounds={...} declaration ────────────────────────────────────
        if meta_call is not None:
            for kw in meta_call.keywords:
                if kw.arg != "bounds" or not isinstance(kw.value, ast.Dict):
                    continue
                for v in kw.value.values:
                    if (isinstance(v, ast.Constant)
                            and isinstance(v.value, (int, float))
                            and not isinstance(v.value, bool)):
                        lineno = v.lineno
                        out.append(Candidate(
                            rel, lineno, v.value, "bounds",
                            shared_window, lines[lineno - 1].strip()))
    return out


def run(root: str, base_spec: str, quiet: bool) -> tuple[int, list[str], str]:
    """Returns (exit_code, failure_lines, summary)."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return 0, [], "skipped (not a git work tree)"

    pathspec = (f"{SUITE_DIR}/*.py",)
    added = GD.diff_added_lines(root, base_spec, *pathspec)

    if ".." not in base_spec:
        untracked = GD.git(root, "ls-files", "--others", "--exclude-standard", "--", *pathspec)
        for rel in untracked.split("\n"):
            rel = rel.strip()
            if not rel or not is_gated_path(rel):
                continue
            try:
                with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            added.setdefault(rel, [])
            for i, line in enumerate(text.split("\n"), 1):
                added[rel].append((i, line))

    base = GD.base_rev(base_spec)
    verbatim = GD.corpus_lines_at(root, base, is_gated_path)

    failures: list[str] = []
    total_new_bounds = 0
    for rel in sorted(added):
        if not is_gated_path(rel):
            continue
        added_linenos = {ln for ln, _text in added[rel]}
        added_texts = {ln: text for ln, text in added[rel]}
        content = GD.head_side(root, base_spec, rel)
        if content is None:
            continue
        candidates = find_candidates(rel, content)
        for c in candidates:
            if c.lineno not in added_linenos:
                continue
            stripped = added_texts[c.lineno].strip()
            if stripped and stripped in verbatim:
                continue  # relocated debt, not new debt
            total_new_bounds += 1
            if not has_citation(c.window):
                failures.append(
                    f"{rel}:{c.lineno}: {c.kind} bound {c.value!r} in `{c.stmt_text}` "
                    f"-> no TASK-/ADR- reference, file:line/file:SYMBOL citation, or dated "
                    f"measurement in the test's decorator/comment/body")

    summary = f"{len(failures)} uncited of {total_new_bounds} newly touched bounds (base {base_spec})"
    return (1 if failures else 0), failures, summary


def main(argv: list[str] | None = None) -> int:
    default_root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    ap = argparse.ArgumentParser(description="R44 delta-scoped bound-origin gate (TASK-613).")
    ap.add_argument("--root", default=default_root)
    ap.add_argument("--base", default=os.environ.get("CHECK_BOUND_ORIGIN_BASE", "HEAD"),
                    help="delta base: a rev, or a range A..B. Env: CHECK_BOUND_ORIGIN_BASE")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    rc, failures, summary = run(args.root, args.base, args.quiet)
    if not args.quiet:
        print("=== check_bound_origin (R44 delta) ===")
    for f in failures:
        print(f"    {f}")
    label = "FAIL" if rc else "PASS"
    print(f"{'    ' if args.quiet else ''}{label}  bound-origin: {summary}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
