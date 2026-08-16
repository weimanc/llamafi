#!/usr/bin/env python3
"""check_docs.py — documentation staleness gate (TASK-475, M-DOCLIFE phase 1).

Implements the mechanically-detectable half of M-DOCLIFE (decay modes D1-D4) as
specified in docs/architecture/designs/M-DOCLIFE-check-docs-spec.md.

Checks
------
  C1-full   every `file.ext:NNN` citation resolves to an existing file with >= NNN lines   (advisory)
  C1-delta  the same, restricted to citations NEWLY ADDED in a diff                        (BLOCKING)
  C2        every TASK-/ADR-/IFC-/X0NN identifier referenced exists                        (advisory)
  C3        every `cyd2usb*` build-env name in docs exists in app/platformio.ini           (advisory)
  C4        Status: uses the closed vocabulary                        (advisory, rule undefined)
  C5        relative .md links resolve                                                     (BLOCKING)

Phase 1 blocks on C5 and C1-delta only: both read 0 today, and a gate that fails
on day one gets switched off.

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
    r = Result("C2", blocking=False)
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

def check_c4(_c: Corpus) -> Result:
    """Present and wired, deliberately count-free.

    The matching rule (exact vs prefix; header-only vs anywhere; *-review.md in
    or out) is undefined, and the count swings 100-218 across plausible
    readings. Two numbers have already been quoted from unstated rules (67, 91)
    and both were wrong, so this prints no number at all until TASK-508 lands.
    """
    r = Result("C4", blocking=False)
    r.skipped = True
    r.summary = "rule undefined pending TASK-508"
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

    blocking: list[Result] = [check_c5(c)]
    if no_git:
        skipped = Result("C1-delta", blocking=True)
        skipped.skipped = True
        skipped.summary = "skipped (--no-git)"
        advisory_extra = [skipped]
    else:
        blocking.append(check_c1_delta(c, base_spec))
        advisory_extra = []

    advisory: list[Result] = advisory_extra + [
        check_c1_full(c), check_c2(c), check_c3(c), check_c4(c)]

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
