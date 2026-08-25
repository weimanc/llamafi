#!/usr/bin/env python3
"""check_docs.py — documentation staleness gate (TASK-475, M-DOCLIFE phase 4).

Implements the mechanically-detectable half of M-DOCLIFE (decay modes D1-D4) as
specified in docs/architecture/designs/M-DOCLIFE-check-docs-spec.md.

Checks
------
  C1-full   every `file.ext:NNN` citation resolves to an existing file with >= NNN lines   (advisory)
  C1-delta  the same, restricted to citations NEWLY ADDED in a diff                        (BLOCKING)
  C2        every TASK-/ADR-/IFC-/X0NN identifier referenced exists                        (BLOCKING)
  C3        every `cyd2usb*` build-env name in docs exists in app/platformio.ini           (advisory)
  C4        Status: uses the closed vocabulary (decisions/designs/interfaces)  (BLOCKING)
  C5        relative .md links resolve                                                     (BLOCKING)
  C6        test-id binding: registry <-> docs/verification            (BLOCKING, see below)

Phase 1 blocked on C5 and C1-delta only: both read 0 on ship day, and a gate
that fails on day one gets switched off. Phase 2 (TASK-475, 2026-08-25) added
C2: it has read 0 since phase 1 and still does at promotion time. Phase 4
(same day) added C4, once TASK-508's ~189-header migration landed and
re-measurement read 0. Phase 3 (C3) remains advisory: unblocked (ADR-061 D8 /
TASK-467 landed) but the count is 58 occurrences across 10 unknown env names,
not near zero — promoting it is a scope call for a human, not a mechanical
one, per this session's own escalation discipline.

Rules that are easy to get wrong, and are therefore spelled out here:

  * Counting is PER-OCCURRENCE everywhere, never per-unique-id. C2 originally
    quoted 39 unique ids where the same corpus holds 138 occurrences.
  * Exemptions govern which files are SCANNED, never which files are usable as
    RESOLUTION SOURCES. 356 TASK- ids resolve only in the exempt tasks-archive.md;
    a resolver that honours the exemption scores 1261 false failures.
  * C1 suppresses FENCED CODE BLOCKS ONLY, plus an explicit
    `<!-- check-docs: ignore-line -->` marker. It must NOT suppress inline
    backticks: backticked `file.h:123` is the normal citation form in this
    corpus, and suppressing it hides ~96% of all citations (604 -> 21) while
    still reporting PASS.
  * docs/ is searched RECURSIVELY. A doc citing a sibling doc by basename
    (M-SRCLAYOUT-main-decomposition.md:4) is a correct citation; a flat root
    list calls it broken.
  * A `NNN-MMM` line range is checked against its HIGHER bound, which is the
    one a shrinking file breaks first.
"""

from __future__ import annotations

import argparse
import ast
import glob
import os
import re
import subprocess
import sys
import urllib.parse

# ── Corpus definition (spec §1) ───────────────────────────────────────────────

EXEMPT_BASENAMES = {"tasks-archive.md", "lessons_learned.md", "audit_log.md"}
EXEMPT_DIR_PREFIXES = ("docs/rnd/",)
EXEMPT_SUFFIXES = ("-review.md",)

# Extra gated files outside docs/. CLAUDE.md is gated: stated explicitly because
# it is load-bearing (C1 reads 279/598 without it, 280/599 with it at efab524).
EXTRA_GATED = ("CLAUDE.md",)

# C1 resolution roots. docs/ is additionally indexed recursively by basename.
RESOLVE_ROOTS = (".", "app", "app/src", "app/tools", "docs")

CITE_EXT = "h|cpp|py|ini|sh|yaml|json|md"
CITE_RE = re.compile(r"([\w./-]+\.(?:" + CITE_EXT + r")):(\d+)(?:-(\d+))?")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
IGNORE_MARKER = "<!-- check-docs: ignore-line -->"

TASK_RE = re.compile(r"\bTASK-(\d+)")
ADR_RE = re.compile(r"\bADR-(\d+)")
IFC_RE = re.compile(r"\bIFC-(\d+)")
X_RE = re.compile(r"\bX(0\d{2})\b")
ENV_RE = re.compile(r"\bcyd2usb[A-Za-z0-9_]*")


def is_exempt(rel: str) -> bool:
    """True if `rel` is a historical record: never SCANNED, always RESOLVABLE."""
    base = os.path.basename(rel)
    if base in EXEMPT_BASENAMES:
        return True
    if rel.startswith(EXEMPT_DIR_PREFIXES):
        return True
    return base.endswith(EXEMPT_SUFFIXES)


def is_gated_path(rel: str) -> bool:
    """True if `rel` is inside the gated corpus at all (before exemptions).

    Deliberately narrow: only docs/**.md and the EXTRA_GATED files. Everything
    else in the tree — including this checker's own fixture corpus under
    app/tools/testdata/ — is outside the corpus and is never scanned, in
    full-corpus mode or in delta mode.
    """
    rel = rel.replace(os.sep, "/")
    if rel in EXTRA_GATED:
        return True
    return rel.startswith("docs/") and rel.endswith(".md")


class Corpus:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.all_docs = sorted(
            os.path.relpath(p, self.root).replace(os.sep, "/")
            for p in glob.glob(os.path.join(self.root, "docs", "**", "*.md"), recursive=True)
        )
        self.exempt = [p for p in self.all_docs if is_exempt(p)]
        gated = [p for p in self.all_docs if not is_exempt(p)]
        for extra in EXTRA_GATED:
            if os.path.exists(os.path.join(self.root, extra)):
                gated.append(extra)
        self.gated = gated
        self._lines: dict[str, int | None] = {}
        # Recursive basename index over docs/ — every file, not only .md.
        self.docs_index: dict[str, list[str]] = {}
        for dirpath, _dirnames, filenames in os.walk(os.path.join(self.root, "docs")):
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), self.root).replace(os.sep, "/")
                self.docs_index.setdefault(fn, []).append(rel)

    def abspath(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    def line_count(self, rel: str) -> int | None:
        if rel in self._lines:
            return self._lines[rel]
        try:
            with open(self.abspath(rel), "rb") as fh:
                n = sum(1 for _ in fh)
        except (OSError, ValueError):
            n = None
        self._lines[rel] = n
        return n

    def read(self, rel: str) -> str:
        with open(self.abspath(rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def resolve_citation(self, cited: str, bound: int) -> str | None:
        """Return the resolving path, or None. `bound` is the higher line bound."""
        for root in RESOLVE_ROOTS:
            cand = os.path.normpath(os.path.join(root, cited)).replace(os.sep, "/")
            if cand.startswith(".."):
                continue
            n = self.line_count(cand)
            if n is not None and n >= bound:
                return cand
        # Recursive docs/ fallback, basename only.
        for cand in self.docs_index.get(os.path.basename(cited), []):
            n = self.line_count(cand)
            if n is not None and n >= bound:
                return cand
        return None


def strip_fenced(text: str) -> list[str]:
    """Blank out fenced code blocks, preserving line numbering.

    Inline backticks are deliberately NOT stripped — see module docstring.
    """
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return out


def scannable_lines(text: str) -> list[tuple[int, str]]:
    """(lineno, text) pairs with fenced blocks and marker lines removed."""
    result = []
    for i, line in enumerate(strip_fenced(text), 1):
        if IGNORE_MARKER in line:
            continue
        result.append((i, line))
    return result


class Result:
    def __init__(self, cid: str, blocking: bool):
        self.cid = cid
        self.blocking = blocking
        self.failures: list[str] = []
        self.total = 0
        self.summary = ""
        self.skipped = False

    @property
    def ok(self) -> bool:
        return self.skipped or not self.failures


# ── C1 ────────────────────────────────────────────────────────────────────────

def citations_in(text: str):
    """Yield (lineno, cited_path, higher_bound, raw)."""
    for lineno, line in scannable_lines(text):
        for m in CITE_RE.finditer(line):
            lo = int(m.group(2))
            hi = int(m.group(3)) if m.group(3) else lo
            yield lineno, m.group(1), max(lo, hi), m.group(0)


def check_c1_full(c: Corpus) -> Result:
    r = Result("C1-full", blocking=False)
    for rel in c.gated:
        for lineno, cited, bound, raw in citations_in(c.read(rel)):
            r.total += 1
            if c.resolve_citation(cited, bound) is None:
                r.failures.append(f"{rel}:{lineno}: {raw} -> no file resolves with >= {bound} lines")
    r.summary = f"{len(r.failures)} broken of {r.total} citations"
    return r


# ── C2 ────────────────────────────────────────────────────────────────────────

def check_c2(c: Corpus) -> Result:
    # TASK-475 phase 2: promoted advisory -> blocking, 2026-08-25. C2 has read
    # 0 since TASK-475 phase 1 (efab524) and still reads 0 at promotion time —
    # verified immediately before this edit, not assumed from the board note.
    r = Result("C2", blocking=True)
    # Resolution sources. Exemptions do NOT apply here: tasks-archive.md is the
    # only home of 356 ids, and skipping it costs 1261 false failures.
    task_ids: set[str] = set()
    boards = sorted(glob.glob(os.path.join(c.root, "docs", "project", "tasks*.md")))
    for b in boards:
        with open(b, encoding="utf-8", errors="replace") as fh:
            task_ids |= set(TASK_RE.findall(fh.read()))

    def _ids(dirname: str, pattern: re.Pattern) -> set[str]:
        d = os.path.join(c.root, dirname)
        if not os.path.isdir(d):
            return set()
        found: set[str] = set()
        for fn in os.listdir(d):
            found |= set(pattern.findall(fn))
        return found

    adr_ids = _ids("docs/architecture/decisions", ADR_RE)
    ifc_ids = _ids("docs/architecture/interfaces", IFC_RE)
    x_ids: set[str] = set()
    xf = os.path.join(c.root, "docs", "project", "cross_feature_matrix.yaml")
    if os.path.exists(xf):
        with open(xf, encoding="utf-8", errors="replace") as fh:
            x_ids = set(X_RE.findall(fh.read()))

    known = ((TASK_RE, task_ids, "TASK-"), (ADR_RE, adr_ids, "ADR-"),
             (IFC_RE, ifc_ids, "IFC-"), (X_RE, x_ids, "X"))
    for rel in c.gated:
        for lineno, line in scannable_lines(c.read(rel)):
            for pattern, universe, prefix in known:
                for m in pattern.finditer(line):
                    r.total += 1
                    if m.group(1) not in universe:
                        r.failures.append(
                            f"{rel}:{lineno}: {prefix}{m.group(1)} -> id not found in its registry")
    r.summary = f"{len(r.failures)} unresolvable of {r.total} id references"
    return r


# ── C3 ────────────────────────────────────────────────────────────────────────

def check_c3(c: Corpus) -> Result:
    r = Result("C3", blocking=False)
    ini = os.path.join(c.root, "app", "platformio.ini")
    if not os.path.exists(ini):
        r.skipped = True
        r.summary = "skipped (no app/platformio.ini)"
        return r
    with open(ini, encoding="utf-8", errors="replace") as fh:
        envs = set(re.findall(r"^\[env:([^\]]+)\]", fh.read(), re.M))
    names: set[str] = set()
    for rel in c.gated:
        for lineno, line in scannable_lines(c.read(rel)):
            for m in ENV_RE.finditer(line):
                r.total += 1
                if m.group(0) not in envs:
                    names.add(m.group(0))
                    r.failures.append(
                        f"{rel}:{lineno}: {m.group(0)} -> no [env:{m.group(0)}] in app/platformio.ini")
    r.summary = (f"{len(r.failures)} occurrences of {len(names)} unknown env names "
                 f"(of {r.total} cyd2usb* references)")
    return r


# ── C4 ────────────────────────────────────────────────────────────────────────

C4_CLOSED_VOCAB = {
    "proposed", "accepted", "done", "implemented", "resolved", "closed",
    "applied", "retired", "superseded", "rejected",
}
C4_FOLD = {"draft": "proposed", "planned": "proposed"}
C4_SCOPE_DIRS = (
    "docs/architecture/decisions/",
    "docs/architecture/designs/",
    "docs/architecture/interfaces/",
)
# README.md in those directories is an index, not a decision/design/interface
# record with a lifecycle — never expected to carry a Status: field at all.
C4_SCOPE_EXCLUDE_BASENAMES = {"README.md"}

STATUS_HEADER_RE = re.compile(r'^(?P<prefix>\s*>?\s*)(?P<pre>\*{0,2})Status(?P<post>\*{0,2})\s*:\s*(?P<rest>.*)$')


def check_c4(c: Corpus) -> Result:
    """Status: header uses the closed vocabulary (TASK-508 human rulings, 2026-08-23).

    Scope: docs/architecture/{decisions,designs,interfaces}/ only (§C4 — applied
    corpus-wide the vocabulary means something different in roadmap.md/
    quality_manager.md/test docs, which is not what this checks). Exemptions
    (EXEMPT_*, incl. *-review.md) still apply on top, same as every other check.

    Rule (per the human rulings, all three):
      (a) closed vocabulary is proposed/accepted/done/implemented/resolved/
          closed/applied/retired/superseded/rejected; draft and planned fold
          into proposed.
      (b) EXACT match — the Status: field's value must be the bare word and
          NOTHING else on the line (case-insensitive, trailing punctuation
          stripped). Rationale/commit/date belongs in a separate as-built
          section (BP-065), not on the Status: line.
      (c) HEADER-ONLY — only the first Status:/**Status**: line in a file (the
          doc's own header) is checked. A truthful in-body status remark
          elsewhere does not offset a stale header, and is not scanned as a
          second header either.

    A file in scope with no Status: header at all is NOT a failure here — C4
    checks vocabulary of an existing field, not its presence (a different,
    unruled question; see TASK-508's own follow-up note).
    """
    # TASK-475 phase 4: promoted advisory -> blocking, 2026-08-25, now that
    # TASK-508's migration has landed (6361ef3) and re-measurement reads 0.
    r = Result("C4", blocking=True)
    for rel in c.gated:
        if not rel.startswith(C4_SCOPE_DIRS):
            continue
        if os.path.basename(rel) in C4_SCOPE_EXCLUDE_BASENAMES:
            continue
        lines = c.read(rel).split("\n")
        for lineno, line in enumerate(lines[:20], start=1):
            m = STATUS_HEADER_RE.match(line)
            if not m:
                continue
            r.total += 1
            value = m.group("rest").strip()
            bare = value.strip("*").strip()
            word = bare.lower().rstrip(".,;:")
            if word in C4_FOLD:
                r.failures.append(
                    f"{rel}:{lineno}: Status: {value!r} -> "
                    f"'{word}' should fold into 'proposed' (TASK-508 ruling (a))")
            elif word not in C4_CLOSED_VOCAB:
                r.failures.append(
                    f"{rel}:{lineno}: Status: {value!r} -> "
                    f"not an exact closed-vocabulary word (TASK-508 ruling (b))")
            break  # header-only (c): first Status: line in the file only
    r.summary = f"{len(r.failures)} non-conforming of {r.total} Status: headers"
    return r


# ── C5 ────────────────────────────────────────────────────────────────────────

def check_c5(c: Corpus) -> Result:
    r = Result("C5", blocking=True)
    for rel in c.gated:
        base_dir = os.path.dirname(rel)
        for lineno, line in scannable_lines(c.read(rel)):
            for m in LINK_RE.finditer(line):
                target = m.group(1)
                if "://" in target or target.startswith(("#", "mailto:")):
                    continue
                target = target.split("#")[0]
                if not target or not target.endswith(".md"):
                    continue
                r.total += 1
                cand = os.path.normpath(
                    os.path.join(base_dir, urllib.parse.unquote(target))).replace(os.sep, "/")
                if not os.path.exists(c.abspath(cand)):
                    r.failures.append(f"{rel}:{lineno}: {target} -> link target does not exist")
    r.summary = f"{len(r.failures)} broken of {r.total} relative .md links"
    return r


# ── C6 — test-id binding (M-TESTARCH §6, TASK-521) ────────────────────────────
#
# WHAT IT ASSERTS, in three parts. They are one Result because they are one
# invariant read from two ends: the executable registries and the VE-owned plan
# must describe the same set of tests.
#
#   C6.1  orphan     — every id in an executable registry resolves to an entry
#                      in docs/verification/. Measured 41 today.
#   C6.2  undeclared — every id that HAS a doc entry declares a status somewhere
#                      among its entries. Measured 8 today.
#   C6.3  mismatch   — the declared status matches reality: `impl` => the id is
#                      in a registry; `resv` => it is not. Measured 0 today.
#
# WHY THIS IS BLOCKING RATHER THAN ADVISORY, given a 49-failure red count.
# TASK-475's own rule is "phase 1 blocks on what reads 0 today", and with the
# ledger below the UNEXCEPTED count is 0. A blocking check plus a ledger that
# cannot grow silently is strictly stronger than an advisory check with 49
# permanent failures: advisory failures are scrolled past, which is the exact
# mechanism by which "covered" and "green" got conflated (LL-140). The debt is
# not hidden — every run prints the ledger size, and a ledger row whose failure
# no longer occurs is itself a BLOCKING failure, so the list can only shrink.
#
# C6.3 ADMITS NO EXCEPTIONS. A ledger row of kind `mismatch` is an error. A
# stale `impl` is the specific defect this check exists for; an exemption for it
# would be an exemption from the point.
#
# SCOPE RULES, and why each is the way it is:
#
#   * Status VOCABULARY is not policed here. C6.2 asserts a status field is
#     PRESENT; whether the value is drawn from a closed vocabulary is C4's
#     question and is undefined pending TASK-508. C6.3 acts only on the three
#     binding values (`impl`/`resv`/`blocked`) established by P0 (116c64f).
#     `blocked` is deliberately unconstrained: a blocked test may or may not
#     have a body, that is what "blocked" means.
#   * Binding is ID-KEYED, not row-keyed. The same id is routinely written twice
#     — a family table with no status column plus a detail table or a `###`
#     entry that carries one. Row-keying reports 62 undeclared rows for 8
#     genuinely undeclared ids.
#   * Exemptions reuse is_exempt() and reuse its existing split: exempt files
#     are never SCANNED for status (so `*-review.md` cannot declare one), but
#     are always usable as RESOLUTION SOURCES for C6.1. Same rule as C2 and the
#     tasks-archive.md case in the module docstring. No second mechanism.
#   * T_DOC_* — the checker's own tests — are NOT special-cased. They are
#     registered in test_plan.md like everything else (`test_plan.md:89-97` and
#     the detail table below it), and they bind. A self-test family that could
#     not satisfy the gate it ships with would be the finding, not the rule.

TEST_ID_RE = re.compile(r"T\d{3}[a-z]?|T_[A-Z0-9]+(?:_[A-Z0-9]+)*_\d+[a-z]?")
STATUS_COL_RE = re.compile(r"^\**\s*(?:status|result|outcome)\s*\**$", re.I)
STATUS_FIELD_RE = re.compile(r"\*\*Status\*\*\s*:\s*([^\n]*)")
HEADING_ID_RE = re.compile(r"^#{2,6}\s+`?([A-Za-z0-9_]+)`?\b")
BINDING_RE = re.compile(r"`?(impl|resv|blocked)`?\b")
SEP_CELL_RE = re.compile(r":?-{2,}:?")
LEDGER_REL = "docs/verification/id_binding_exceptions.md"
LEDGER_KINDS = ("orphan", "undeclared")


def _is_test_id(s: str) -> bool:
    return bool(TEST_ID_RE.fullmatch(s))


def _row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def test_registries(root: str) -> dict[str, str]:
    """id -> "path:line" for every executable test registry under app/tools/.

    DISCOVERED, not whitelisted: any module-level assignment to a name called
    `ALL` or containing `TEST` whose value is a dict of id keys, or a list of
    ids / (id, fn) pairs / references to functions named after ids. A new
    satellite suite is therefore picked up with no edit here — which is the
    point, since the last three orphan families all arrived that way.
    """
    reg: dict[str, str] = {}
    tools = os.path.join(root, "app", "tools")
    if not os.path.isdir(tools):
        return reg
    for path in sorted(glob.glob(os.path.join(tools, "*.py"))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any(n == "ALL" or "TEST" in n.upper() for n in names):
                continue
            found: set[str] = set()
            val = node.value
            if isinstance(val, ast.Dict):
                for k in val.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                            and _is_test_id(k.value):
                        found.add(k.value)
            elif isinstance(val, (ast.List, ast.Tuple)):
                for e in val.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str) \
                            and _is_test_id(e.value):
                        found.add(e.value)
                    elif isinstance(e, (ast.Tuple, ast.List)) and e.elts \
                            and isinstance(e.elts[0], ast.Constant) \
                            and isinstance(e.elts[0].value, str) \
                            and _is_test_id(e.elts[0].value):
                        found.add(e.elts[0].value)
                    elif isinstance(e, ast.Name) and _is_test_id(e.id.upper()):
                        # `ALL = [t_flk_01, ...]` — a list of function objects.
                        found.add(e.id.upper())
            for tid in found:
                reg.setdefault(tid, f"{rel}:{node.lineno}")
    return reg


def doc_test_entries(c: Corpus) -> dict[str, list[tuple[str, str, bool]]]:
    """id -> [(file:line, status_text)] over docs/verification/.

    Two entry forms, both real in this corpus:
      * a table row whose first cell is a test id, status taken from a column
        headed Status/Result/Outcome (NOT "Expected result" — that column holds
        criteria, and reading it as a status makes every spec table look
        declared);
      * a `### T001 — ...` / `### \\`T_CC_01\\`...` heading, status taken from a
        `**Status**:` field in the following 30 lines (the persona's entry
        format, verification_engineer.md:43).
    Each entry is (location, status_text, scanned). Exempt files contribute
    entries with scanned=False: they RESOLVE C6.1 but can neither declare a
    status nor be accused of failing to — C6.2 skips any id whose every entry is
    in a historical record. Same split as C2, one mechanism (is_exempt).
    """
    entries: dict[str, list[tuple[str, str, bool]]] = {}
    # The exception ledger is EXCLUDED. Its rows are keyed by test id and parse
    # as doc entries, so without this the ledger grandfathers its own rows into
    # existence: every `orphan` row became a doc entry, which cleared the orphan
    # and created a fresh `undeclared` finding in its place. A ledger row is a
    # record of missing coverage, never coverage.
    docs = [p for p in c.all_docs
            if p.startswith("docs/verification/") and p != LEDGER_REL]
    for rel in docs:
        scan_status = not is_exempt(rel)
        lines = c.read(rel).split("\n")
        header: list[str] | None = None
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("|"):
                cells = _row_cells(s)
                if all(SEP_CELL_RE.fullmatch(x) for x in cells if x):
                    continue
                if header is None:
                    header = cells
                    continue
                tid = cells[0].strip("`* ")
                if not _is_test_id(tid):
                    continue
                cols = [k for k, h in enumerate(header) if STATUS_COL_RE.match(h)]
                status = cells[cols[0]] if cols and cols[0] < len(cells) else ""
                entries.setdefault(tid, []).append(
                    (f"{rel}:{i}", status.strip() if scan_status else "", scan_status))
                continue
            header = None
            m = HEADING_ID_RE.match(s)
            if not m or not _is_test_id(m.group(1)):
                continue
            block = "\n".join(lines[i:i + 30])
            fm = STATUS_FIELD_RE.search(block)
            status = fm.group(1).strip() if (fm and scan_status) else ""
            entries.setdefault(m.group(1), []).append((f"{rel}:{i}", status, scan_status))
    return entries


def _parse_ledger(c: Corpus) -> tuple[dict[tuple[str, str], str], list[str]]:
    """Return ({(kind, id): "ledger:line"}, [malformed-row errors])."""
    ledger: dict[tuple[str, str], str] = {}
    errors: list[str] = []
    path = c.abspath(LEDGER_REL)
    if not os.path.exists(path):
        return ledger, errors
    header: list[str] | None = None
    for i, line in enumerate(c.read(LEDGER_REL).split("\n"), 1):
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = _row_cells(s)
        if all(SEP_CELL_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = cells
            continue
        tid = cells[0].strip("`* ")
        if not _is_test_id(tid):
            continue
        where = f"{LEDGER_REL}:{i}"
        kind = cells[1].strip("`* ").lower() if len(cells) > 1 else ""
        owner = cells[3].strip() if len(cells) > 3 else ""
        since = cells[4].strip() if len(cells) > 4 else ""
        if kind not in LEDGER_KINDS:
            errors.append(f"{where}: kind '{kind}' -> C6.3 (mismatch) admits no "
                          f"exceptions; valid kinds are {list(LEDGER_KINDS)}")
            continue
        if not TASK_RE.search(owner):
            errors.append(f"{where}: {tid} -> exception has no owning TASK- id")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
            errors.append(f"{where}: {tid} -> exception has no ISO date in 'since'")
        ledger[(kind, tid)] = where
    return ledger, errors


def check_c6(c: Corpus) -> Result:
    r = Result("C6", blocking=True)
    reg = test_registries(c.root)
    if not reg:
        r.skipped = True
        r.summary = "skipped (no executable registries under app/tools/)"
        return r
    entries = doc_test_entries(c)
    ledger, r.failures = _parse_ledger(c)
    used: set[tuple[str, str]] = set()
    raw: list[tuple[str, str, str]] = []          # (kind, id, message)

    # C6.1 — every registry id resolves to a doc entry.
    for tid in sorted(set(reg) - set(entries)):
        raw.append(("orphan", tid,
                    f"{reg[tid]}: {tid} -> executable, but no entry in docs/verification/"))
    # C6.2 — every id with a doc entry declares a status somewhere.
    for tid, ents in sorted(entries.items()):
        if any(st for _loc, st, _sc in ents):
            continue
        if not any(sc for _loc, _st, sc in ents):
            continue          # historical records only — nothing to declare
        raw.append(("undeclared", tid,
                    f"{ents[0][0]}: {tid} -> doc entry declares no status "
                    f"(Status/Result column, or a **Status**: field)"))
    # C6.3 — declared status must match reality. No exceptions.
    for tid, ents in sorted(entries.items()):
        toks = set()
        for _loc, st, _sc in ents:
            m = BINDING_RE.match(st.lstrip("*` "))
            if m:
                toks.add(m.group(1))
        if "impl" in toks and tid not in reg:
            raw.append(("mismatch", tid,
                        f"{ents[0][0]}: {tid} -> declared `impl` but is in no "
                        f"executable registry"))
        elif toks == {"resv"} and tid in reg:
            raw.append(("mismatch", tid,
                        f"{ents[0][0]}: {tid} -> declared `resv` but a body is "
                        f"registered at {reg[tid]}"))

    counts = {"orphan": 0, "undeclared": 0, "mismatch": 0}
    excepted = 0
    for kind, tid, msg in raw:
        counts[kind] += 1
        key = (kind, tid)
        if kind != "mismatch" and key in ledger:
            used.add(key)
            excepted += 1
            continue
        r.failures.append(msg)
    # A ledger row whose failure no longer occurs is itself a failure: that is
    # what makes the list shrink rather than calcify into fiction.
    for key, where in sorted(ledger.items()):
        if key not in used:
            r.failures.append(f"{where}: {key[1]} -> stale exception, the '{key[0]}' "
                              f"finding no longer occurs; delete this row")
    r.total = len(reg) + len(entries)
    bound = len(set(reg) & set(entries))
    r.summary = (f"{len(reg)} registry ids, {len(entries)} doc ids, {bound} bound; "
                 f"{counts['orphan']} orphan / {counts['undeclared']} undeclared / "
                 f"{counts['mismatch']} mismatched; {excepted} on the ledger, "
                 f"{len(r.failures)} unexcepted")
    return r


# ── C1-delta ──────────────────────────────────────────────────────────────────

def _git(root: str, *args: str) -> str:
    return subprocess.run(("git", "-C", root) + args, capture_output=True,
                          text=True, check=False).stdout


def _base_rev(spec: str) -> str:
    return spec.split("..")[0] if ".." in spec else spec


def _corpus_lines_at(root: str, rev: str) -> set[str]:
    """Every line of every corpus .md file at `rev`, stripped.

    Backs the verbatim carve-out: a line that already existed at the base rev is
    relocated debt, not new debt. Without it a document split — which this repo
    does — fires the blocking gate on content it did not author.
    """
    listing = _git(root, "ls-tree", "-r", "--name-only", rev)
    paths = [p for p in listing.split("\n") if p and is_gated_path(p)]
    if not paths:
        return set()
    stdin = "".join(f"{rev}:{p}\n" for p in paths)
    proc = subprocess.run(("git", "-C", root, "cat-file", "--batch"),
                          input=stdin.encode(), capture_output=True, check=False)
    out = proc.stdout
    lines: set[str] = set()
    pos = 0
    while pos < len(out):
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        header = out[pos:nl].decode("utf-8", "replace")
        parts = header.split()
        if len(parts) < 3 or not parts[-1].isdigit():
            pos = nl + 1
            continue
        size = int(parts[-1])
        blob = out[nl + 1:nl + 1 + size]
        for line in blob.decode("utf-8", "replace").split("\n"):
            s = line.strip()
            if s:
                lines.add(s)
        pos = nl + 1 + size + 1
    return lines


def _head_side(root: str, base_spec: str, rel: str) -> str | None:
    """Content of `rel` on the RIGHT-hand side of the comparison.

    Needed so C1-delta can apply exactly the same fenced-block and
    ignore-marker suppression as C1-full. The spec requires one resolver and
    one suppression rule across both modes: if they disagree about whether a
    citation is even visible, the delta gate fails on lines the advisory check
    never counted.
    """
    if ".." in base_spec:
        head = base_spec.split("..")[-1] or "HEAD"
        out = subprocess.run(("git", "-C", root, "show", f"{head}:{rel}"),
                             capture_output=True, text=True, check=False)
        return out.stdout if out.returncode == 0 else None
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def check_c1_delta(c: Corpus, base_spec: str) -> Result:
    r = Result("C1-delta", blocking=True)
    root = c.root
    if not os.path.isdir(os.path.join(root, ".git")):
        r.skipped = True
        r.summary = "skipped (not a git work tree)"
        return r

    diff = _git(root, "diff", "-M", "-C", "--unified=0", base_spec, "--", "*.md")

    added: list[tuple[str, str]] = []   # (path, line_text)
    current: str | None = None
    for line in diff.split("\n"):
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current = None
            else:
                current = target[2:] if target.startswith(("a/", "b/")) else target
            continue
        if line.startswith("+") and not line.startswith("+++"):
            if current and is_gated_path(current) and not is_exempt(current):
                added.append((current, line[1:]))

    # Untracked .md inside the gated corpus: every line counts as added. Only
    # meaningful for the default working-tree comparison.
    if ".." not in base_spec:
        untracked = _git(root, "ls-files", "--others", "--exclude-standard", "--", "*.md")
        for rel in untracked.split("\n"):
            rel = rel.strip()
            if not rel or not is_gated_path(rel) or is_exempt(rel):
                continue
            try:
                with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
                    for line in fh.read().split("\n"):
                        added.append((rel, line))
            except OSError:
                pass

    base = _base_rev(base_spec)
    verbatim = _corpus_lines_at(root, base)

    # Group added lines per file so fenced-block state is evaluated per file.
    by_file: dict[str, list[str]] = {}
    for rel, text in added:
        by_file.setdefault(rel, []).append(text)

    for rel, texts in sorted(by_file.items()):
        content = _head_side(root, base_spec, rel)
        if content is None:
            continue
        # Same suppression as C1-full: fenced blocks blanked, marker lines
        # dropped. An added line is only checked if it survives that filter on
        # the head side, so the two modes cannot disagree about visibility.
        visible: dict[str, list[int]] = {}
        for lineno, line in scannable_lines(content):
            s = line.strip()
            if s:
                visible.setdefault(s, []).append(lineno)
        for text in texts:
            stripped = text.strip()
            if not stripped:
                continue
            if stripped not in visible:
                continue          # inside a fenced block, or marker-suppressed
            if stripped in verbatim:
                continue          # relocated debt, not new debt
            where = f"{rel}:{visible[stripped][0]}"
            for m in CITE_RE.finditer(text):
                lo = int(m.group(2))
                hi = int(m.group(3)) if m.group(3) else lo
                bound = max(lo, hi)
                r.total += 1
                if c.resolve_citation(m.group(1), bound) is None:
                    r.failures.append(
                        f"{where}: {m.group(0)} -> newly added citation resolves to no file "
                        f"with >= {bound} lines")
    r.summary = f"{len(r.failures)} broken of {r.total} newly added citations (base {base_spec})"
    return r


# ── Driver ────────────────────────────────────────────────────────────────────

def run(root: str, base_spec: str, quiet: bool, no_git: bool) -> int:
    c = Corpus(root)

    blocking: list[Result] = [check_c5(c), check_c6(c), check_c2(c), check_c4(c)]
    # C6 prints its ledger arithmetic even when clean. A blocking check that is
    # invisible on the happy path cannot be distinguished from one that was
    # silently skipped — the failure mode TASK-511 hit from the other side.
    for _r in blocking:
        if _r.cid == "C6" and not _r.failures and not quiet:
            # A SKIP is not an OK. Labelling one as the other is the same
            # conflation this line exists to prevent.
            print(f"    [{'skip' if getattr(_r, 'skipped', False) else 'ok'}] C6: {_r.summary}")
    if no_git:
        skipped = Result("C1-delta", blocking=True)
        skipped.skipped = True
        skipped.summary = "skipped (--no-git)"
        advisory_extra = [skipped]
    else:
        blocking.append(check_c1_delta(c, base_spec))
        advisory_extra = []

    advisory: list[Result] = advisory_extra + [
        check_c1_full(c), check_c3(c)]

    counted = [r for r in blocking if not r.skipped]
    total = len(counted)

    if not quiet:
        print("=== Doc check ===")
        print()

    n = 0
    for r in counted:
        n += 1
        if not quiet:
            print(f"[{n}/{total}] {r.cid}")
        for f in r.failures:
            print(f"    {f}")
        if quiet:
            if r.failures:
                print(f"    FAIL  {r.cid}: {r.summary}")
        else:
            print(f"  {'PASS' if r.ok else 'FAIL'}  {r.cid}: {r.summary}")

    indent = "    " if quiet else ""
    for r in blocking + advisory:
        if r in counted:
            continue
        note = "" if r.skipped else " (advisory, not counted)"
        print(f"{indent}[warn] {r.cid}{note}: {r.summary}")
        # §3: every failure prints file:line: <what> -> <why>. Advisory detail is
        # the actionable half of an advisory check, so it is shown standalone —
        # and suppressed under --quiet, where check-docs occupies one gate slot.
        if not quiet:
            for f in r.failures:
                print(f"    {f}")

    passed = sum(1 for r in counted if r.ok)
    failed = total - passed
    if not quiet:
        print()
        print(f"=== Results: {passed} passed, {failed} failed ===")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    default_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap = argparse.ArgumentParser(description="Documentation staleness gate (TASK-475).")
    ap.add_argument("--root", default=default_root,
                    help="repo root to check (default: this tool's repo)")
    ap.add_argument("--base", default=os.environ.get("CHECK_DOCS_BASE", "HEAD"),
                    help="C1-delta base: a rev, or a range A..B. Env: CHECK_DOCS_BASE")
    ap.add_argument("--quiet", action="store_true",
                    help="one gate slot: no banner, no Results tail (for check_build.sh)")
    ap.add_argument("--no-git", action="store_true",
                    help="skip C1-delta (fixture corpora are not git work trees)")
    args = ap.parse_args(argv)
    return run(args.root, args.base, args.quiet, args.no_git)


if __name__ == "__main__":
    sys.exit(main())
