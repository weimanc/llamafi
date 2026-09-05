#!/usr/bin/env python3
"""check_plan_integrity.py — ids exist once. TASK-611 / M-HARNESS2 R46.

R46: **a test id MUST bind to exactly one body and one declaration.** Five ways
the corpus breaks that, each RE-MEASURED for this task rather than inherited from
WP-Z — three of its four figures had moved (see the ledger's re-measurement
table):

  P1  two bodies      — one id, two executable functions, different oracles and
                        different reporting (`A-15`). TASK-603 executed the
                        adjudication for `T_PLR_25`; this is the gate that keeps
                        the shape from growing back.
  P2  two declarations— one id, two `###` plan entries. `test_plan.md`'s
                        `serialdbg-audit-001` section re-declares nine ids as
                        `### T176 fix — …` work items, and C6 reads a status out
                        of BOTH, so which entry binds is ambiguous.
  P3  collision       — the id's plan entry and its body describe different
                        tests (`F-2`/`G-11`: `T237`, `T276`, `T231`, all three
                        ids minted from a TASK number that already named a plan
                        heading). Mechanised as ZERO shared content words
                        between the plan heading title and the body's own title;
                        see `_overlap` for why that threshold and not a ratio.
  P5  manual-but-    — the plan says `[MANUAL]` or `[Blocked: …]` and a body is
      executable        registered anyway. `F-2`'s third id (`T231`) and both of
                        `G-12`/`H-13`'s Teletext rows. Same defect as P3, caught
                        by a fact instead of a word count.
  P4  stale retirement— an id in `retired_test_ids.md` whose plan entry does not
                        say it is retired, so the plan still reads as coverage
                        (`G-12`'s shape, generalised past the six rows).

WHY A NEW GATE RATHER THAN MORE C6. C6 is a BINDING check: does every executable
id have a doc entry, and does the declared status match reality. It is id-keyed
by construction and deliberately so — row-keying reported 62 undeclared rows for
8 genuinely undeclared ids (`check_docs.py:620-624`). Every finding here is about
MULTIPLICITY or about the CONTENT of the binding, both of which id-keying throws
away before C6 sees them. Merging these into C6 would mean un-keying it.

LANDING. P1, P2 and P4 read ZERO today and are blocking there — P2's six were
fixed in this task by retitling the nine `### T176 fix — …` work items that were
being parsed as second declarations. P3's three and P5's three are on a dated
shrink-only ledger, `docs/verification/plan_integrity_exceptions.md`: resolving
either means RENAMING a live test id, which changes what the suite runs and is
@VE's artifact, not a gate's.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_plan_integrity.py [--verbose] [--print-rows]
"""

from __future__ import annotations

import argparse
import ast
import datetime
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

LEDGER_REL = "docs/verification/plan_integrity_exceptions.md"
RETIRED_REL = "docs/verification/retired_test_ids.md"

TEST_ID_RE = re.compile(r"T\d{3}[a-z]?|T_[A-Z0-9]+(?:_[A-Z0-9]+)*_\d+[a-z]?")
HEADING_RE = re.compile(r"^#{2,6}\s+`?([A-Za-z0-9_]+)`?\s*(.*)$")
#: `–\`26\`` / `-\`03\`` immediately after the id: a family RANGE heading.
FAMILY_RANGE_RE = re.compile(r"^\s*[–—-]\s*`?\d+`?")
#: A plan annotation saying the id has no automated body.
UNRUNNABLE_RE = re.compile(r"\[(?:MANUAL|Blocked)[^\]]*\]", re.I)
_SEP_RE = re.compile(r":?-{2,}:?")
_TASK_RE = re.compile(r"^TASK-\d+$")

KINDS = ("two-bodies", "two-declarations", "collision", "manual-but-executable",
         "stale-retirement")

#: Documents that are HISTORICAL records, not the live plan. A second heading in
#: an archive is not a second declaration — it is the previous one. Same split
#: `check_docs.is_exempt()` makes, restated here rather than imported: this gate
#: may not import from `app/tools/` beyond the two registry builders, and a
#: three-name tuple is cheaper to read than the coupling.
ARCHIVE_MARKERS = ("-archive", "/archive/", "/reviews/", "regression_suite/")

#: The ledgers. Their rows are keyed by test id and parse as plan headings /
#: table rows; without this every ledger row would grandfather itself in. Same
#: rule and same reason as `check_docs.LEDGER_RELS`.
LEDGER_RELS = (
    LEDGER_REL,
    RETIRED_REL,
    "docs/verification/id_binding_exceptions.md",
    "docs/verification/flake_class_exceptions.md",
    "docs/verification/gating_class_declarations.md",
    "docs/verification/defaulted_reads_ratchet.md",
    "docs/verification/unrestored_mutations_ratchet.md",
    "docs/verification/rowlen_exceptions.md",
)

_STOP = frozenset("""the a an and or of to in for on with is are be by from that this it
its as at not no than then when while after before all any each per via new old set get
test tests id ids""".split())


def _is_test_id(s: str) -> bool:
    return bool(TEST_ID_RE.fullmatch(s))


def _is_archive(rel: str) -> bool:
    return any(m in rel for m in ARCHIVE_MARKERS)


# ── the executable side ──────────────────────────────────────────────────────

def registry_bodies(root: str = None) -> dict:
    """-> {id: [(module, lineno, funcname)]} for every id bound to a body.

    Reads the same registry shapes `check_docs.test_registries` discovers, but
    keeps the TARGET rather than the first location, because the whole point of
    P1 is the second target C6 discards.
    """
    root = root or ROOT
    out: dict = {}
    for path in sorted(glob.glob(os.path.join(root, "app", "tools", "**", "*.py"),
                                 recursive=True)):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if "/gate/" in rel:                      # gate fixtures are not the suite
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any(n == "ALL" or "TEST" in n.upper() for n in names):
                continue
            val = node.value
            if isinstance(val, ast.Dict):
                for k, v in zip(val.keys, val.values):
                    if not (isinstance(k, ast.Constant) and isinstance(k.value, str)
                            and _is_test_id(k.value)):
                        continue
                    fn = v.id if isinstance(v, ast.Name) else (
                        v.attr if isinstance(v, ast.Attribute) else None)
                    out.setdefault(k.value, []).append((rel, k.lineno, fn))
            elif isinstance(val, (ast.List, ast.Tuple)):
                for e in val.elts:
                    tid = fn = None
                    if isinstance(e, ast.Constant) and isinstance(e.value, str) \
                            and _is_test_id(e.value):
                        tid, fn = e.value, None
                    elif isinstance(e, (ast.Tuple, ast.List)) and len(e.elts) >= 2 \
                            and isinstance(e.elts[0], ast.Constant) \
                            and isinstance(e.elts[0].value, str) \
                            and _is_test_id(e.elts[0].value):
                        tid = e.elts[0].value
                        fn = e.elts[1].id if isinstance(e.elts[1], ast.Name) else None
                    elif isinstance(e, ast.Name) and _is_test_id(e.id.upper()):
                        tid, fn = e.id.upper(), e.id
                    if tid:
                        out.setdefault(tid, []).append((rel, e.lineno, fn))
    return out


def body_titles(root: str = None) -> dict:
    """-> {(module, funcname): title} — what the BODY says it tests.

    The title is the first `print(...)` in the function, which every family in
    this suite opens with (`print(f"{tid}  <what this test does>")`), falling
    back to the docstring's first line. Both are the author's own one-line
    description; neither is a mirror of the plan, which is the property P3
    needs.
    """
    root = root or ROOT
    out: dict = {}
    for path in sorted(glob.glob(os.path.join(root, "app", "tools", "**", "*.py"),
                                 recursive=True)):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            title = None
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                        and n.func.id == "print" and n.args:
                    a = n.args[0]
                    if isinstance(a, ast.JoinedStr):
                        txt = "".join(v.value for v in a.values
                                      if isinstance(v, ast.Constant))
                    elif isinstance(a, ast.Constant) and isinstance(a.value, str):
                        txt = a.value
                    else:
                        continue
                    if txt.strip():
                        title = txt.strip()
                        break
            if title is None:
                doc = ast.get_docstring(fn) or ""
                title = doc.strip().split("\n")[0] if doc.strip() else None
            if title:
                out[(rel, fn.name)] = title
    return out


# ── the plan side ────────────────────────────────────────────────────────────

def plan_headings(root: str = None) -> dict:
    """-> {id: [(rel, lineno, title, is_archive)]} over docs/verification/."""
    root = root or ROOT
    out: dict = {}
    base = os.path.join(root, "docs", "verification")
    for path in sorted(glob.glob(os.path.join(base, "**", "*.md"), recursive=True)):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if rel in LEDGER_RELS:
            continue
        arch = _is_archive(rel)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh.read().split("\n"), 1):
                m = HEADING_RE.match(line.strip())
                if not m or not _is_test_id(m.group(1)):
                    continue
                rest = m.group(2)
                # A FAMILY heading — `### \`T_PLR_01\`–\`26\` — implemented family`
                # — names a RANGE, not this id. It is neither a second declaration
                # of the first id nor a description of its body, so counting it as
                # either produces a finding about a heading that is doing its job.
                if FAMILY_RANGE_RE.match(rest):
                    continue
                title = rest.lstrip("—–-— ").strip()
                out.setdefault(m.group(1), []).append((rel, i, title, arch))
    return out


def retired_ids(root: str = None) -> dict:
    """-> {id: 'rel:line'} from the retirement register's table rows."""
    root = root or ROOT
    out: dict = {}
    path = os.path.join(root, RETIRED_REL)
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh.read().split("\n"), 1):
            s = line.strip()
            if not s.startswith("|"):
                continue
            first = s.strip("|").split("|")[0].strip("`* ")
            if _is_test_id(first):
                out[first] = f"{RETIRED_REL}:{i}"
    return out


# ── P3's comparison ──────────────────────────────────────────────────────────

def _toks(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(w) > 2 and w not in _STOP}


def _overlap(plan_title: str, body_title: str) -> int:
    """Shared content words. ZERO is the threshold, and deliberately not a ratio.

    A ratio needs a cutoff nobody can defend and moves with title length. Zero
    shared content words between two one-line descriptions of the SAME test is a
    fact, not a score: the measured distribution over this corpus has the three
    known collisions at 0 and 1 and every honest pair at 3 or more, and the two
    at 1 are the two the same finding names.
    """
    return len(_toks(plan_title) & _toks(body_title))


# ── findings ─────────────────────────────────────────────────────────────────

def findings(root: str = None) -> list:
    """-> [(kind, id, message)]. Pure over the tree; the ledger is applied later."""
    root = root or ROOT
    bodies = registry_bodies(root)
    titles = body_titles(root)
    plan = plan_headings(root)
    retired = retired_ids(root)
    out: list = []

    # P1 — two bodies.
    for tid, locs in sorted(bodies.items()):
        targets = {(m, f) for m, _l, f in locs if f}
        if len(targets) > 1:
            where = "; ".join(f"{m}:{l}->{f}" for m, l, f in locs)
            out.append(("two-bodies", tid,
                        f"{tid} -> {len(targets)} executable bodies ({where}). R46: "
                        f"an id binds to ONE body; two bodies means two oracles and "
                        f"two verdicts under one name"))

    # P2 — two declarations in the live plan.
    for tid, ents in sorted(plan.items()):
        live = [e for e in ents if not e[3]]
        if len(live) > 1:
            where = "; ".join(f"{r}:{l}" for r, l, _t, _a in live)
            out.append(("two-declarations", tid,
                        f"{tid} -> {len(live)} plan entries ({where}). C6 reads a "
                        f"status out of each, so which one binds is ambiguous"))

    # P3 — the plan entry and the body describe different tests.
    for tid, locs in sorted(bodies.items()):
        live = [e for e in plan.get(tid, []) if not e[3]]
        if len(live) != 1:
            continue                       # P2's case, or no entry at all (C6.1's)
        btitles = [titles.get((m, f)) for m, _l, f in locs if f]
        btitles = [t for t in btitles if t]
        if not btitles:
            continue
        ptitle = live[0][2]
        if not _toks(ptitle):
            continue
        if max(_overlap(ptitle, bt) for bt in btitles) == 0:
            out.append(("collision", tid,
                        f"{tid} -> plan {live[0][0]}:{live[0][1]} says "
                        f"{ptitle[:60]!r}; the body says {btitles[0][:60]!r}. No "
                        f"content word in common — the id names two different tests"))

    # P5 — the plan says the id cannot be run automatically; a body runs it anyway.
    # The second half of `F-2` (`T231`, whose plan entry is a MANUAL Aquarium
    # check and whose body is a Stock test) and both of `G-12`/`H-13`'s Teletext
    # rows. It is the same defect as P3 — the entry does not describe the body —
    # caught by a fact rather than by a word count, and it is exact: the plan
    # says "no automated body exists" and one is registered.
    for tid, locs in sorted(bodies.items()):
        for rel, ln, title, arch in plan.get(tid, []):
            if arch or not UNRUNNABLE_RE.search(title):
                continue
            out.append(("manual-but-executable", tid,
                        f"{tid} -> plan {rel}:{ln} declares it "
                        f"{UNRUNNABLE_RE.search(title).group(0)} while "
                        f"{locs[0][0]}:{locs[0][1]} registers an executable body. "
                        f"One of the two is describing a different test"))

    # P4 — a retired id whose live plan entry does not say so.
    for tid, where in sorted(retired.items()):
        for rel, ln, title, arch in plan.get(tid, []):
            if arch:
                continue
            blob = _plan_block(root, rel, ln)
            if "retir" in blob.lower() or "TASK-603" in blob or "deleted" in blob.lower():
                continue
            out.append(("stale-retirement", tid,
                        f"{tid} -> retired at {where}, but its plan entry "
                        f"{rel}:{ln} still reads as coverage and says nothing about "
                        f"the retirement"))
    return out


_BLOCK_CACHE: dict = {}


def _plan_block(root: str, rel: str, lineno: int, span: int = 25) -> str:
    """The heading's own block — enough lines to carry a retirement note."""
    key = (root, rel)
    if key not in _BLOCK_CACHE:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            _BLOCK_CACHE[key] = fh.read().split("\n")
    lines = _BLOCK_CACHE[key]
    return "\n".join(lines[lineno - 1:lineno - 1 + span])


# ── the ledger ───────────────────────────────────────────────────────────────

def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({(kind, id): 'rel:line'}, [errors]). Absent file fails closed."""
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
            header = cells
            continue
        if len(cells) < 5:
            continue
        tid, kind = cells[0].strip("`* "), cells[1].strip("`* ").lower()
        owner, since = cells[3].strip("`* "), cells[4].strip("`* ")
        where = f"{rel}:{i}"
        if not _is_test_id(tid):
            errors.append(f"L {where}: {tid!r} is not a test id — a row names one id")
            continue
        if kind not in KINDS:
            errors.append(f"L {where}: kind {kind!r} is not one of {list(KINDS)}")
            continue
        if not _TASK_RE.match(owner):
            errors.append(f"L {where}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"L {where}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[(kind, tid)] = where
    return rows, errors


def evaluate(found: list, ledger: dict) -> tuple:
    """-> (failures, n_excepted). A stale ledger row is itself a failure."""
    fails: list = []
    used: set = set()
    for kind, tid, msg in found:
        key = (kind, tid)
        if key in ledger:
            used.add(key)
            continue
        fails.append(f"{kind.upper()} {msg}")
    for key, where in sorted(ledger.items()):
        if key not in used:
            fails.append(f"STALE {where}: the {key[0]} finding for {key[1]} no "
                         f"longer occurs — delete the row. This ledger only shrinks")
    return fails, len(used)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--print-rows", action="store_true",
                    help="print today's findings as ledger rows")
    args = ap.parse_args()

    found = findings()
    ledger, lerrs = parse_ledger()
    fails, n_exc = evaluate(found, ledger)
    fails = lerrs + fails

    if args.print_rows:
        for kind, tid, msg in found:
            print(f"| `{tid}` | {kind} | {msg[:120]} | TASK-611 | "
                  f"{datetime.date.today().isoformat()} |")
    if args.verbose:
        by: dict = {}
        for kind, _tid, _m in found:
            by[kind] = by.get(kind, 0) + 1
        print(f"plan-integrity findings: {len(found)} "
              f"({', '.join(f'{k}={v}' for k, v in sorted(by.items())) or 'none'}); "
              f"{len(ledger)} ledger rows, {n_exc} used")

    if fails:
        print(f"FAIL: check_plan_integrity.py — {len(fails)} finding(s) "
              f"(TASK-611 / R46):")
        for f in fails:
            print(f"  {f}")
        return 1
    print(f"OK: check_plan_integrity.py — {len(found)} finding(s), all on the "
          f"dated shrink-only ledger ({len(ledger)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
