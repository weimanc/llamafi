#!/usr/bin/env python3
"""check_no_reachable_fail.py — R34: every registered id can actually go red.

WHY THIS EXISTS. The M-TESTQUAL audits graded the serialdbg corpus 54 % sound.
The single most expensive defect class they found is not a wrong assertion — it
is an id that **cannot produce a FAIL at all**, and therefore reports green for
its whole life while costing suite time and counting toward the plan's coverage
total. Three ids were one unconditional `skip()`. Six more had no reachable
`fail()` anywhere in their reachable source. One had a `fail()` whose guard
could not be true. And a fourth shape — the one this gate is really for — is
invisible to every check that came before it (§ SHAPE 4 below).

WHAT IT ASSERTS. For every id in `build_all_tests()`, exactly one of:

  1. the body has at least one REACHABLE `fail()`, in the sense of the four
     shapes below; or
  2. the id has a row in the gate's dated, owned, shrink-only ledger
     (docs/verification/no_reachable_fail_ledger.md).

Plus two invariants that are not about any single id:

  * **No body is one unconditional `skip()`.** Counted separately, because it is
    the shape the corpus was growing for want of a deletion procedure
    (docs/process/test_id_retirement.md).
  * **No id in `build_all_tests()` appears in the `UNOBSERVABLE` half of
    docs/verification/retired_test_ids.md.** An `UNOBSERVABLE` record above a
    live green body is not a ledger row, it is `H-2`'s mechanism: five
    M-CLOCK-STYLES exit criteria were booked PASS exactly that way. R4 says the
    body goes; this is what makes "the body goes" enforceable rather than
    aspirational.

THE FOUR SHAPES, and why the fourth is the reason to build this at all.

  SHAPE 1 — no `fail()` anywhere in the reachable source. Trivially decidable.
    Reference cases: T_MA_03, T_GOL_03, T_WX_03, T_CX_03 before TASK-584.

  SHAPE 2 — the body is one unconditional `skip()` and nothing else. Decidable
    without any of shape 3/4's analysis. Reference cases: T136, T171, T179, all
    retired 2026-09-05.

  SHAPE 3 — a `fail()` whose guard cannot be true, given a value already
    established earlier in the same body. **Full dominance analysis is not
    attempted and must not be**: the decidable subset is a guard on a field of a
    reply dict whose truthiness was already required upstream in the same
    function (`if not r.get("ok"): fail(...)` sitting below a successful
    `r["name"]` read off the same reply). Anything outside that local pattern is
    left to review, deliberately. Reference case: T182 before TASK-584.

  SHAPE 4 — a `fail()` guarded only by a helper that swallows its own read error
    and returns a bool. **This is the shape TASK-596's ratchet structurally
    cannot see, and a gate that missed it would report zero while the defect was
    present.** `check_defaulted_reads.py` counts `.get(<key>, <literal>)` on a
    reply; here there is no literal and no `.get` — the default has moved into
    an `except` arm:

        def _appid_is(dut, app_name, timeout=5.0) -> bool:
            try:
                return dut.get_str("appId", field="name", timeout=timeout) == app_name
            except DeviceReadError:
                return False

    The two outcomes the typed accessor exists to separate — *the device said
    another app* and *the device said nothing* — are re-merged into one `False`,
    and every caller spends that `False` on one verdict. Note the helper itself
    is LEGITIMATE: TASK-596 consolidated four hand-rolled copies into it
    deliberately, and its docstring says so. The finding is never "delete the
    helper". It is "this id's only `fail()` cannot distinguish a silent device
    from a wrong answer, so it must read typed at the call site — which is what
    TASK-584 did for T_MA_03, T_GOL_03, T_WX_03, T_CX_03 and T182 — or carry a
    ledger row saying why not". Swallowing is computed to a FIXPOINT: a
    bool-returning helper that returns a call to a swallowing helper swallows
    too (`_switch_to` -> `_appid_is`).

WHAT IT PROVES, AND WHAT IT CANNOT (TASK-671). Everything above is a NECESSARY
condition: a body with no reachable `fail()` cannot go red. It is not
sufficient. "The guard can be true at runtime" is a program-analysis question
this gate deliberately does not attempt (see SHAPE 3), and an inverted guard
(`C-1`), a body that skips on every deviation before its `fail()` is consulted
(`D-2`), or a `fail()` in a helper no path calls all pass here and can never be
red. The sufficient half is answered by EXECUTION, not analysis:
`gate/check_can_go_red.py` (`lib/canfail.py`) runs each recorded body against
its poisoned transcript and reports whether an assertion FAIL was ever
observed. Where both gates speak, the gate compares them. Do not widen the
static analysis here to close that gap — widening it is how a gate starts
lying in the direction that matters.

WHAT IT DOES NOT DO. It does not grade assertions. An id with a reachable
`fail()` on a value it wrote itself is a hollow test and this gate passes it —
that is R2's subject, not R34's. This gate answers exactly one question: **can
this cell ever be red?**

BLOCKING, with a dated shrink-only ledger whose stale rows are themselves
blocking failures — the standing form (`check_defaulted_reads.py`,
`gating_class_declarations.md`, `id_binding_exceptions.md`). Blocking-at-zero is
not available on day one and pretending otherwise is how a gate gets switched
off.

Import discipline: `build_all_tests` is the ONLY thing imported from the suite.
The reachable-source walk is done here, over `fn.__globals__`, rather than by
reusing `_meta._reachable_source` — that helper returns concatenated text, and
this gate needs per-function ASTs.

No DUT, no build, no network. Run directly, or via app/tools/smoke_test.sh
(run/check gate 9).

    python3 app/tools/gate/check_no_reachable_fail.py
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from suite.serialdbg import build_all_tests            # noqa: E402

LEDGER_REL = "docs/verification/no_reachable_fail_ledger.md"
REGISTER_REL = "docs/verification/retired_test_ids.md"
PROCEDURE_REL = "docs/process/test_id_retirement.md"

#: Exception names whose handler returning a constant re-merges "the device said
#: something else" with "the device said nothing". `Exception`/bare-except are in
#: the list because they are strictly worse, not because they are common.
SWALLOWED = {"DeviceReadError", "NoAnswer", "BadField", "TimeoutError",
             "Exception", "OSError", "ValueError"}

MAX_DEPTH = 6
TASK_RE = re.compile(r"\bTASK-(\d+)")
SEP_CELL_RE = re.compile(r":?-{2,}:?")
#: Wider than check_docs' TEST_ID_RE on purpose: that one does not match the
#: hyphenated `T-BUSY-01b` / `T-UART-01` / `T-CDWN-02` family, which IS in
#: build_all_tests(). A ledger that could not name an id the gate can flag would
#: be unusable exactly where the corpus is worst.
TEST_ID_RE = re.compile(r"T\d{3}[a-z]?"
                        r"|T_[A-Z0-9]+(?:_[A-Z0-9]+)*_\d+[a-z]?"
                        r"|T-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+[a-z]?")


# ── source access ─────────────────────────────────────────────────────────────

#: code object -> FunctionDef | None. `inspect.getsource` + `ast.parse` is by far
#: this gate's largest cost (TASK-629): reachable_functions() re-derives the same
#: shared helper's tree once per calling test id, and the negative suite runs the
#: whole evaluation several times over — 22 791 parses, 9 s of run/check's host
#: budget. Keyed on the CODE OBJECT, not on id() and not on the function: the
#: code object is what getsource resolves through, a reloaded module produces a
#: new one (so the mutation arm cannot be served a stale tree), and holding it as
#: the key keeps it alive, which id() would not.
_FUNC_AST_CACHE: dict = {}


def func_ast(fn):
    """The FunctionDef node for `fn`, or None if its source is unavailable."""
    code = getattr(fn, "__code__", None)
    if code is not None and code in _FUNC_AST_CACHE:
        return _FUNC_AST_CACHE[code]
    node = _func_ast_uncached(fn)
    if code is not None:
        _FUNC_AST_CACHE[code] = node
    return node


def _func_ast_uncached(fn):
    try:
        src = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError, IndentationError):
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def reachable_functions(fn, max_depth: int = MAX_DEPTH) -> dict:
    """{qualified name -> function object} for `fn` plus, transitively, every
    suite-level helper it can call. Resolution is through `fn.__globals__`, so
    a helper imported `from ._helpers import _switch_to` is found without this
    gate importing `_helpers` itself."""
    out, seen = {}, set()

    def walk(f, depth):
        if id(f) in seen or depth > max_depth:
            return
        seen.add(id(f))
        node = func_ast(f)
        if node is None:
            return
        out[f"{getattr(f, '__module__', '?')}.{f.__name__}"] = f
        g = getattr(f, "__globals__", {}) or {}
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            name = (sub.func.id if isinstance(sub.func, ast.Name)
                    else sub.func.attr if isinstance(sub.func, ast.Attribute)
                    else None)
            cand = g.get(name)
            if (inspect.isfunction(cand)
                    and str(getattr(cand, "__module__", "")).startswith("suite.serialdbg")):
                walk(cand, depth + 1)

    walk(fn, 0)
    return out


def _called_name(call: ast.Call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def calls_named(node, name: str) -> list:
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call) and _called_name(n) == name]


# ── shape 4: the error-swallowing bool helper ────────────────────────────────

def _returns_only_bools(node) -> bool:
    """True if every `return` in `node` yields something that can only be a
    bool: a bool constant, a comparison, a `not`, or a call to another helper.
    Used together with the `-> bool` annotation, not instead of it."""
    rets = [n for n in ast.walk(node) if isinstance(n, ast.Return) and n.value is not None]
    if not rets:
        return False
    for r in rets:
        v = r.value
        if isinstance(v, ast.Constant) and isinstance(v.value, bool):
            continue
        if isinstance(v, (ast.Compare, ast.BoolOp)):
            continue
        if isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.Not):
            continue
        if isinstance(v, ast.Call):
            continue
        return False
    return True


def _is_bool_helper(node) -> bool:
    ann = node.returns
    if isinstance(ann, ast.Name) and ann.id == "bool":
        return True
    if isinstance(ann, ast.Constant) and ann.value == "bool":
        return True
    return ann is None and _returns_only_bools(node)


def _swallows_directly(node) -> bool:
    """A try/except on a read-failure exception whose handler returns a
    constant. That constant IS the default `check_defaulted_reads.py` looks for,
    relocated where it cannot see it."""
    for h in (n for n in ast.walk(node) if isinstance(n, ast.ExceptHandler)):
        names = set()
        if h.type is None:
            names.add("Exception")
        elif isinstance(h.type, ast.Name):
            names.add(h.type.id)
        elif isinstance(h.type, ast.Tuple):
            names |= {e.id for e in h.type.elts if isinstance(e, ast.Name)}
        elif isinstance(h.type, ast.Attribute):
            names.add(h.type.attr)
        if not (names & SWALLOWED):
            continue
        for r in (n for n in ast.walk(h) if isinstance(n, ast.Return)):
            if isinstance(r.value, ast.Constant):
                return True
    return False


def swallowing_helpers(funcs: dict) -> set:
    """Names of bool-returning helpers that swallow a read error, to a FIXPOINT.
    `_switch_to` does not catch anything itself — it `return`s `_appid_is(...)`,
    which does. Stopping at the direct case would miss every caller of the
    wrapper, which is most of them."""
    nodes = {}
    for qual, f in funcs.items():
        node = func_ast(f)
        if node is not None and _is_bool_helper(node):
            nodes[node.name] = node
    swallow = {n for n, node in nodes.items() if _swallows_directly(node)}
    changed = True
    while changed:
        changed = False
        for name, node in nodes.items():
            if name in swallow:
                continue
            for r in (x for x in ast.walk(node) if isinstance(x, ast.Return)):
                for c in ast.walk(r) if r.value is not None else ():
                    if isinstance(c, ast.Call) and _called_name(c) in swallow:
                        swallow.add(name)
                        changed = True
                        break
                if name in swallow:
                    break
    return swallow


def _guarded_fails(node, swallow: set) -> tuple:
    """(all fail() calls in `node`, those inside an `if` whose test calls a
    swallowing helper)."""
    all_fails = calls_named(node, "fail")
    guarded = []
    for n in ast.walk(node):
        if not isinstance(n, ast.If):
            continue
        if not any(isinstance(c, ast.Call) and _called_name(c) in swallow
                   for c in ast.walk(n.test)):
            continue
        for body in (n.body, n.orelse):
            for stmt in body:
                guarded += calls_named(stmt, "fail")
    return all_fails, [f for f in all_fails if any(f is g for g in guarded)]


# ── shape 2: one unconditional skip() ────────────────────────────────────────

def _is_lone_skip(node) -> bool:
    """The body is a docstring, some prints, and one unconditional `skip()`.
    No branch, no loop, no try — so the skip is not a decision, it is the whole
    test."""
    stmts = [s for s in node.body
             if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                     and isinstance(s.value.value, str))]
    if any(isinstance(s, (ast.If, ast.For, ast.While, ast.Try, ast.With)) for s in stmts):
        return False
    skips = 0
    for s in stmts:
        if isinstance(s, ast.Return) and s.value is None:
            continue
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
            name = _called_name(s.value)
            if name == "skip":
                skips += 1
                continue
            if name in ("print", "pass_"):
                continue
        return False
    return skips == 1


# ── shape 3: a guard on a reply field already required upstream ──────────────

def _tautological_guards(node) -> list:
    """`if not r.get("ok"): fail(...)` sitting BELOW a successful `r[...]` read
    off the same reply. Local pattern match only — see the module docstring on
    why full dominance analysis is deliberately not attempted."""
    subscripted = {}          # reply name -> earliest line read by subscript
    for n in ast.walk(node):
        if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                and isinstance(getattr(n, "ctx", None), ast.Load)):
            ln = getattr(n, "lineno", 0)
            subscripted.setdefault(n.value.id, ln)
            subscripted[n.value.id] = min(subscripted[n.value.id], ln)
    out = []
    for n in ast.walk(node):
        if not isinstance(n, ast.If) or not isinstance(n.test, ast.UnaryOp):
            continue
        if not isinstance(n.test.op, ast.Not):
            continue
        c = n.test.operand
        if not (isinstance(c, ast.Call) and _called_name(c) == "get"
                and isinstance(c.func, ast.Attribute)
                and isinstance(c.func.value, ast.Name)):
            continue
        reply = c.func.value.id
        if reply in subscripted and subscripted[reply] < n.lineno:
            if calls_named(n, "fail"):
                out.append((reply, n.lineno, subscripted[reply]))
    return out


# ── the analysis, one id at a time ───────────────────────────────────────────

def analyse(tid: str, fn) -> list:
    """[(shape, message)] for one id. Empty means the cell can go red."""
    if fn is None:
        return [(1, f"{tid} -> registry entry is not a function; nothing can fail")]
    own = func_ast(fn)
    if own is None:
        return [(1, f"{tid} -> source unavailable; cannot prove a reachable fail()")]

    findings = []
    if _is_lone_skip(own):
        findings.append((2, f"{tid} -> the body is one unconditional skip() and "
                            f"nothing else; it asserts nothing and costs suite time "
                            f"(see {PROCEDURE_REL})"))

    funcs = reachable_functions(fn)
    reachable_fails = 0
    for f in funcs.values():
        node = func_ast(f)
        if node is not None:
            reachable_fails += len(calls_named(node, "fail"))
    if reachable_fails == 0:
        findings.append((1, f"{tid} -> no fail() anywhere in its reachable source "
                            f"({len(funcs)} function(s), depth<={MAX_DEPTH}); the cell "
                            f"can only ever be green or skipped"))
        return findings

    for reply, fail_ln, read_ln in _tautological_guards(own):
        findings.append((3, f"{tid} -> `if not {reply}.get(...)` guarding a fail() at "
                            f"line {fail_ln} of the body, below a `{reply}[...]` read at "
                            f"line {read_ln} that already required the reply; the guard "
                            f"cannot be true"))

    swallow = swallowing_helpers(funcs)
    own_fails, guarded = _guarded_fails(own, swallow)
    if own_fails and len(guarded) == len(own_fails):
        used = sorted({_called_name(c) for n in ast.walk(own) if isinstance(n, ast.If)
                       for c in ast.walk(n.test)
                       if isinstance(c, ast.Call) and _called_name(c) in swallow})
        findings.append((4, f"{tid} -> every fail() in the body ({len(own_fails)}) is "
                            f"guarded by an error-swallowing bool helper "
                            f"({', '.join(used)}); a silent device and a wrong answer "
                            f"produce the same verdict. Read typed at the call site, or "
                            f"carry a ledger row"))
    return findings


# ── the ledger and the UNOBSERVABLE register ─────────────────────────────────

def _rows(path):
    """Markdown table rows as cell lists, header skipped."""
    if not os.path.exists(path):
        return
    header = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            s = line.strip()
            if not s.startswith("|"):
                header = None
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(SEP_CELL_RE.fullmatch(x) for x in cells if x):
                continue
            if header is None:
                header = cells
                continue
            yield i, cells


def archived_tasks(root: str) -> set:
    p = os.path.join(root, "docs", "project", "tasks-archive.md")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8", errors="replace") as fh:
        return set(TASK_RE.findall(fh.read()))


def parse_ledger(root: str) -> tuple:
    """({id: (shape, where)}, [errors]). Rows must be dated, owned, and shaped."""
    ledger, errors = {}, []
    path = os.path.join(root, LEDGER_REL)
    archived = archived_tasks(root)
    for ln, cells in _rows(path):
        tid = cells[0].strip("`* ")
        if not TEST_ID_RE.fullmatch(tid):
            continue
        where = f"{LEDGER_REL}:{ln}"
        shape = cells[1].strip("`* ") if len(cells) > 1 else ""
        owner = cells[3] if len(cells) > 3 else ""
        since = cells[4].strip() if len(cells) > 4 else ""
        if shape not in ("1", "2", "3", "4"):
            errors.append(f"{where}: {tid} -> shape {shape!r} is not one of 1/2/3/4")
        m = TASK_RE.search(owner)
        if not m:
            errors.append(f"{where}: {tid} -> ledger row has no owning TASK- id")
        elif m.group(1) in archived:
            errors.append(f"{where}: {tid} -> owner TASK-{m.group(1)} is ARCHIVED; a row "
                          f"cannot outlive its owner, or the gate reads zero forever")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
            errors.append(f"{where}: {tid} -> ledger row has no ISO date in 'since'")
        ledger[tid] = (shape, where)
    return ledger, errors


def parse_unobservable(root: str) -> dict:
    """{id: where} for the UNOBSERVABLE half of the retirement register. Rows in
    the `deleted` table carry a different Status token and are ignored."""
    out = {}
    path = os.path.join(root, REGISTER_REL)
    for ln, cells in _rows(path):
        tid = cells[0].strip("`* ")
        if not TEST_ID_RE.fullmatch(tid):
            continue
        if len(cells) > 1 and cells[1].strip("`* ").upper().startswith("UNOBSERVABLE"):
            out[tid] = f"{REGISTER_REL}:{ln}"
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def evaluate(tests: dict, root: str) -> tuple:
    """([failures], [notes], counts) — the whole gate, callable from its tests."""
    findings = {}
    for tid, fn in sorted(tests.items()):
        f = analyse(tid, fn)
        if f:
            findings[tid] = f

    ledger, failures = parse_ledger(root)
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    used = set()
    for tid, fs in sorted(findings.items()):
        for shape, msg in fs:
            counts[shape] += 1
            if tid in ledger:
                used.add(tid)
                continue
            failures.append(msg)
    for tid, (_shape, where) in sorted(ledger.items()):
        if tid not in used:
            failures.append(f"{where}: {tid} -> stale ledger row, the finding no longer "
                            f"occurs (or the id is gone); delete this row. The list can "
                            f"only shrink.")

    unobs = parse_unobservable(root)
    for tid, where in sorted(unobs.items()):
        if tid in tests:
            failures.append(f"{where}: {tid} -> recorded UNOBSERVABLE but its body is "
                            f"STILL REGISTERED. An UNOBSERVABLE record above a live green "
                            f"body is not a ledger row, it is how H-2 booked five exit "
                            f"criteria as PASS. Delete the body (see {PROCEDURE_REL} §3).")

    notes = [f"{len(unobs)} UNOBSERVABLE id(s) in {REGISTER_REL}, none registered"
             if not any(t in tests for t in unobs) else
             f"{len(unobs)} UNOBSERVABLE id(s) in {REGISTER_REL}"]
    return failures, notes, counts


def main() -> int:
    tests = build_all_tests()
    failures, notes, counts = evaluate(tests, ROOT)
    ledger, _ = parse_ledger(ROOT)

    print("=== check_no_reachable_fail.py — R34: every id can go red (TASK-603) ===")
    print(f"  ids: {len(tests)}")
    print(f"  shape 1 (no fail() in reachable source):        {counts[1]}")
    print(f"  shape 2 (body is one unconditional skip()):     {counts[2]}")
    print(f"  shape 3 (guard that cannot be true):            {counts[3]}")
    print(f"  shape 4 (only fail() behind a swallowing bool): {counts[4]}")
    print(f"  ledger: {len(ledger)} row(s) in {LEDGER_REL}")
    for n in notes:
        print(f"  [note] {n}")
    print(f"  Phase 1 exit criterion — ids with no reachable fail() or a body that is "
          f"one unconditional skip() = {counts[1] + counts[2]} "
          f"({len(ledger)} ledgered, {counts[1] + counts[2] - len(ledger)} unexcepted)")

    if failures:
        print()
        for f in failures:
            print(f"  FAIL: {f}")
        print(f"\n=== {len(failures)} unexcepted finding(s) ===")
        return 1
    print("\n=== every registered id has a reachable fail(), or a dated ledger row ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
