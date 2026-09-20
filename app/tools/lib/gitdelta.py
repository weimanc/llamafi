"""gitdelta.py — shared plumbing for delta-scoped ("touched lines only") gates.

TASK-613 lifted this out of `gate/check_docs.py`'s C1-delta (TASK-475), which
had it first, rather than let a second copy grow in `check_bound_origin.py`
(TASK-613, R44). `check_no_mirrors.py`'s own docstring calls out the exact
failure mode a copied walk causes here: a near-identical duplicate of this
same plumbing already caused a stale-behaviour bug this week (gen_get_keys.py
vs its own glob, TASK-600/R7) — so this is the ONE copy, and both gates
import it.

What every delta gate needs, in order:

  1. `git(root, *args)` — run git in `root`, return stdout. Every git call a
     delta gate makes goes through this so the subprocess plumbing is written
     once.
  2. `base_rev(spec)` — a `--base` value is either a bare rev (`HEAD~1`) or a
     range (`a..b`); the LEFT side of a range is what "at the base" means for
     the verbatim carve-out below. A bare rev is its own base.
  3. `corpus_lines_at(root, rev, is_gated)` — every line of every file at
     `rev` whose repo-relative path satisfies `is_gated`, stripped. This is
     the carve-out that makes a delta gate survivable: a line already present
     at the base rev is RELOCATED debt, not NEW debt. A file move or a
     function move re-adds lines a naive `git diff` would call "added" —
     without this set, the gate fires on code it did not author. `is_gated`
     is a predicate, not a hardcoded suffix check, because `check_docs.py`'s
     corpus (`docs/**.md` + `CLAUDE.md`) and `check_bound_origin.py`'s corpus
     (`app/tools/suite/serialdbg/*.py`) are different filesets — the walk and
     the batch-cat-file plumbing are identical, only the predicate differs.

Callers still do their own `git diff -M -C --unified=0 <base_spec>` and their
own per-file "what's visible on the head side" pass (fenced-block stripping
for docs, AST parsing for Python) — those parts are corpus-shaped and stay in
each gate. Only the git plumbing above is common.
"""
from __future__ import annotations

import os
import re
import subprocess


def git(root: str, *args: str) -> str:
    return subprocess.run(("git", "-C", root) + args, capture_output=True,
                          text=True, check=False).stdout


def base_rev(spec: str) -> str:
    return spec.split("..")[0] if ".." in spec else spec


def corpus_lines_at(root: str, rev: str, is_gated) -> set[str]:
    """Every line of every file at `rev` satisfying `is_gated(path)`, stripped.

    `is_gated` takes a repo-relative, forward-slash path and returns bool.
    """
    listing = git(root, "ls-tree", "-r", "--name-only", rev)
    paths = [p for p in listing.split("\n") if p and is_gated(p)]
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


def head_side(root: str, base_spec: str, rel: str) -> str | None:
    """Content of `rel` on the RIGHT-hand side of the comparison.

    A range spec (`a..b`) reads `rel` at `b` (or HEAD if `b` is empty, i.e.
    `a..`); a bare rev reads the WORKING TREE, not the rev itself — a delta
    gate compares the tree you are about to commit against a base, not two
    historical revs. `None` means the file does not exist on that side
    (deleted, or never existed).
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


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def diff_added_lines(root: str, base_spec: str, *pathspec: str) -> dict[str, list[tuple[int, str]]]:
    """`{path: [(new_lineno, text), ...]}` for every line ADDED by the diff.

    Uses `--unified=0` so every emitted line is either a deletion (which does
    not advance the new-side line counter) or an addition (which does) —
    there are no context lines to skip. This is the line-NUMBERED sibling of
    `check_docs.py`'s own `check_c1_delta`, which only needs line TEXT (its
    verbatim carve-out matches on content, not position); a gate whose
    citation window depends on surrounding source structure (an AST node's
    `lineno`) needs the position too.
    """
    diff = git(root, "diff", "-M", "-C", "--unified=0", base_spec, "--", *pathspec)
    result: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    newln = 0
    for line in diff.split("\n"):
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = None if target == "/dev/null" else (
                target[2:] if target.startswith(("a/", "b/")) else target)
            continue
        if line.startswith("@@"):
            m = _HUNK_RE.match(line)
            if m:
                newln = int(m.group(1))
            continue
        if current is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            result.setdefault(current, []).append((newln, line[1:]))
            newln += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass  # deletion: does not consume a new-side line number
    return result
