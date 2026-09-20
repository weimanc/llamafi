#!/usr/bin/env python3
"""check_wait_expiry.py — R22's own verification clause: "a gate flags any
bounded loop whose expiry path leads to pass_()." TASK-607 / M-HARNESS2 R22.

THE DEFECT R22 NAMES. "A wait is a failure bound, not a sampling budget"
(docs/verification/M-HARNESS2-requirements.md:451-457). A bounded poll loop
(`while ... time.monotonic() < deadline`) that FALLS THROUGH — its condition
never observed true, the deadline simply expiring — must never reach a
`pass_()` call without an intervening decision on what the loop actually saw.
If it does, the test passes because a WINDOW ran out, not because anything
was observed: exactly the reductio M-TESTARCH §3b.4 gives ("a test that a fast
network can defeat is sampling a window it does not control").

WHAT THIS GATE DOES NOT SEE, MEASURED AT REVIEW AND STATED BEFORE THE ZERO IS
READ AS AN ALL-CLEAR. The scan is INTRA-FUNCTION: it finds a loop and the
`pass_()` in the same body. This suite's dominant wait shape is
cross-function — eleven helpers own the loop (`_wait_for_log`,
`_wait_shell_not_busy`, `_wait_wr_count`, …) and the CALLER decides. Planted
at review, still reads zero:

    seen = _wait_for_log(dut, "never-appears-marker", timeout_s=8.0)
    if seen:
        fail(tid, "marker appeared"); return
    pass_(tid, "no marker within 8s")          # <- passes BECAUSE it expired

That body passes exactly when the window runs out, which is R22's defect, and
this gate is blind to it. So the zero below means "no loop falls through to
pass_() in its own body", NOT "no test passes because a window expired". The
cross-function arm — follow a call into a helper that owns a bounded loop, and
grade the caller's expiry branch — is owed on TASK-717.

An absence check (pass = the marker did NOT appear, R12) is a legitimate
version of that shape, which is why the arm has to GRADE the branch rather
than flag every caller: the taxonomy already has a name for it (`ABSENCE`,
docs/architecture/designs/M-HARNESS2-falsifier-taxonomy.md §3), and R22's own
clause asks for "an explicit decision", not for the shape to be banned.

WHAT THIS GATE COUNTS (decidable subset only — same discipline as
`check_no_reachable_fail.py`'s SHAPE 1-4: a full data-flow/dominance analysis
is not attempted and must not be). For every bounded `while` loop — one whose
`test` expression's source contains `time.monotonic`, `deadline`, or
`elapsed` (the exact idiom this corpus uses, confirmed against all 64 such
loops across 8 `suite/` modules on 2026-09-20) — walk forward through the
REST OF ITS ENCLOSING BLOCK (function body, `if`/`else` arm, `try`/`except`
arm; nested blocks are walked too, each on their own). Stop as soon as any of
these is reached, because each is a DECISION on the loop's outcome or ends
the path outright:

  * `return` / `raise` — the path ends here, nothing after it is reachable
    through the fall-through edge;
  * an `if` statement — by construction a decision point (SHAPE 3's own
    limitation applies here too: whether its condition actually inspects the
    loop's outcome is not verified, only that SOME branch exists before any
    `pass_()` — the same "decidable necessary condition, not sufficient"
    posture as the sibling gates in this directory);
  * a `fail(`, `skip(`, or `unmet(` call — a verdict already reached; nothing
    to flag.

If instead the walk reaches a bare, top-level `pass_(` call before any of the
above — a straight-line fall-through from loop-expiry into a pass — that is
the T1 finding: this loop's expiry path reaches `pass_()` with no decision in
between.

WHAT IT DOES NOT SEE (documented, not silently absent, per QM's rot rule).
A while loop's outcome consumed by a HELPER FUNCTION that returns a bool,
with the decision made in the CALLER (a different function) — the actual
shape this corpus uses throughout (`if not _wait_chart_complete(...): fail();
return` in one function, `while time.monotonic() < deadline: ...` in
another) — is invisible to a single-function AST walk by construction, and is
also not the defect: the decision instructions above are simply verifying
that the decision point exists in whichever function the pass_() call lives
in, which is exactly the wait-helper convention the corpus already follows
(every `_wait_*` helper returns bool/count on both the observed and the
expired path; nothing in `suite/` calls `pass_()` directly inside a bounded
loop's own function without an intervening `if`). An inverted `if` condition,
or one that checks something OTHER than the loop's own outcome, is the
SHAPE-3-shaped gap this gate shares with `check_no_reachable_fail.py`: a
necessary condition, not a sufficient one. Runtime replay
(`check_can_go_red.py`) is the sufficient half, same division of labour as
that gate's own docstring describes.

MEASURED 2026-09-20 (TASK-607 / R22), BEFORE any `poll_until` migration: 64
bounded while-loops matching the idiom above across 8 `suite/` modules
(shell.py 22, _helpers.py 10, player.py 8, webradio.py 8, planeradar.py 7,
stock.py 5, teletext.py 2, health.py 2) — **0 findings**. AFTER migrating six
wait helpers onto `lib.dut.poll_until` (the R22 shared wait-primitive half of
this task; see that function's docstring), five of those six loops lived in
`suite/` and were replaced by function calls, so the SAME scan now reads **59**
across the same 8 modules (shell.py 22, _helpers.py 9, player.py 8,
planeradar.py 7, webradio.py 7, stock.py 3, teletext.py 2, health.py 1) —
still **0 findings**. (The sixth migrated helper, `wait_for_queue`, lives in
`lib/dut.py`, out of this gate's scope per R22's own verification clause.)
Every one of the 59 either `return`s/`break`s on its observed condition
inside the loop and returns a plain bool/count/`False` on expiry (the
`_wait_*` helper convention), or is consumed by a caller that decides with an
`if` before ever reaching `pass_()`. Lands **blocking at zero, no ledger** —
same posture as `check_flake_class.py`'s F1-F8 and `check_get_keys.py`: a
defect this gate can see is not "shrinking", it is categorically absent, so a
shrink-only ratchet would just be headroom to reintroduce it.

  T1  a bounded while loop's fall-through path reaches a bare `pass_(...)`
      call before any `return`/`raise`/`if`/`fail(`/`skip(`/`unmet(`.

Scope: `app/tools/suite/` (R22's verification clause: a wait becoming a
sampling budget is a TEST-BODY defect; `app/tools/lib/` wait primitives are
covered by the fact that every `_wait_*`/`wait_*` helper this gate's sibling
work (R22's other half) touches returns its outcome rather than calling
`pass_()` itself — `lib/` has no `pass_()` callers to begin with).

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_wait_expiry.py [--verbose] [--list <module>]
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

SCAN_ROOT = "suite"  # app/tools/suite/ — R22's verification clause

_BOUND_MARKERS = ("time.monotonic", "deadline", "elapsed")
_VERDICT_CALLS = frozenset({"fail", "skip", "unmet"})
_PASS_CALL = "pass_"


def _call_name(node: ast.AST) -> "str | None":
    if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
        return None
    fn = node.value.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _is_bounded_while(node: ast.While, src: str) -> bool:
    seg = ast.get_source_segment(src, node.test) or ""
    return any(marker in seg for marker in _BOUND_MARKERS)


def _walk_block(body: list, src: str, findings: list, rel: str) -> None:
    """Scan one statement list (a function body, or one `if`/`try` arm) for
    T1, then recurse into every nested block regardless of whether this block
    itself held a hit — a bounded loop can sit inside an `if`/`try` arm too."""
    for i, stmt in enumerate(body):
        if isinstance(stmt, ast.While) and _is_bounded_while(stmt, src):
            j = i + 1
            while j < len(body):
                s = body[j]
                if isinstance(s, (ast.Return, ast.Raise, ast.If)):
                    break
                name = _call_name(s)
                if name in _VERDICT_CALLS:
                    break
                if name == _PASS_CALL:
                    findings.append(
                        f"T1 {rel}:{stmt.lineno}: bounded while loop's "
                        f"fall-through reaches pass_() at line {s.lineno} "
                        f"with no return/if/fail/skip/unmet in between — "
                        f"this loop can pass on expiry alone (R22)")
                    break
                j += 1
        for field in ("body", "orelse", "finalbody"):
            sub = getattr(stmt, field, None)
            if isinstance(sub, list):
                _walk_block(sub, src, findings, rel)
        if isinstance(stmt, ast.Try):
            for handler in stmt.handlers:
                _walk_block(handler.body, src, findings, rel)


def scan(root: str = None) -> tuple:
    """-> ({module: count}, [findings]) over app/tools/suite/."""
    root = root or TOOLS
    counts: dict = {}
    findings: list = []
    base = os.path.join(root, SCAN_ROOT)
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
                tree = ast.parse(src, filename=path)
            except SyntaxError as exc:
                findings.append(f"T1 {rel}: SyntaxError parsing file: {exc}")
                counts[rel] = 0
                continue
            mod_findings: list = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _walk_block(node.body, src, mod_findings, rel)
            counts[rel] = len(mod_findings)
            findings.extend(mod_findings)
    return counts, findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--list", metavar="MODULE",
                    help="print bounded-while line numbers for one module "
                         "(diagnostic, not the finding list)")
    args = ap.parse_args()

    counts, findings = scan()

    if args.list:
        root = TOOLS
        path = os.path.join(root, args.list)
        if not os.path.exists(path):
            print(f"no such module: {args.list}", file=sys.stderr)
            return 2
        with open(path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        tree = ast.parse(src, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.While) and _is_bounded_while(node, src):
                print(f"{args.list}:{node.lineno}: bounded while")

    if args.verbose:
        total_loops = 0
        for mod, cnt in counts.items():
            path = os.path.join(TOOLS, mod)
            with open(path, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            tree = ast.parse(src, filename=path)
            total_loops += sum(
                1 for node in ast.walk(tree)
                if isinstance(node, ast.While) and _is_bounded_while(node, src))
        print(f"bounded while-loops scanned: {total_loops} across "
              f"{sum(1 for v in counts.values() if v is not None)} modules; "
              f"{len(findings)} finding(s)")

    if findings:
        print(f"FAIL: check_wait_expiry.py — {len(findings)} finding(s) "
              f"(TASK-607 / R22):")
        for f in findings:
            print(f"  {f}")
        return 1
    print("OK: check_wait_expiry.py — 0 bounded loops fall through to "
          "pass_() unconditionally (blocking at zero, no ledger).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
