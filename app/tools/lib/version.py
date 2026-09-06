#!/usr/bin/env python3
"""lib/version.py — what harness produced this artifact. TASK-645 / R30.

THE GAP. `premise.harness_version` shipped in TASK-608 reading
`artifact.SCHEMA_VERSION` — the version of the *document format*, which the
document already carries under `schema.version`. So the field said "1.1" for
every run ever made by every version of the harness, and R30's question — *what
code produced this?* — had no source in the tree at all. That is the field
TASK-645 is here to give a source.

THE CONSTRAINT decides the design: derivable with **no network and no build**,
at the end of every run, cheap enough that nobody notices.

WHY A CONTENT HASH IS THE PRIMARY IDENTITY, AND GIT ONLY PROVENANCE.

  * `git describe` answers "which commit is checked out", which is not the same
    question. This project works on master directly with no feature branches
    (LL/BP on the board), so the tree is uncommitted for most of the working
    day: `--dirty` would mark nearly every run and distinguish none of them
    from each other. Two runs an hour apart with a rewritten oracle between
    them would carry the SAME describe string. An artifact whose premise cannot
    tell those two runs apart is exactly the failure R30 names.
  * A hash over the harness source answers the question asked. It changes when
    and only when the code that ran changed, it needs no `.git` (an exported
    tree, a worktree, a CI checkout), and it is comparable across machines.
  * Git is still worth carrying, because a hash alone cannot be looked up. So
    the commit, the describe string and the dirty flag ride ALONGSIDE as
    provenance, all three `null` when git is unavailable — never substituted
    for the hash and never used to compute the id.

WHAT COUNTS AS "THE HARNESS". `app/tools/**/*.py` and `run/*` — the Python that
decides verdicts and the shell that decides which firmware, port and flags it
decides them under. `run/` is IN deliberately: `run/test-sync` choosing a
different env than `run/test` is a difference in what the run means, and a
version that ignored it would call two materially different runs the same.

EXCLUDED, and why: `__pycache__` (a build product), `.runs/` (the artifacts
themselves — including them would make every run's version depend on how many
runs preceded it), and anything untracked-and-generated under `app/gen`, which
is not under either root anyway.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess

#: app/tools/lib -> repo root
ROOT = pathlib.Path(__file__).resolve().parents[3]

#: (relative root, filename predicate). Ordered, and both are hashed together.
_ROOTS = (
    ("app/tools", lambda n: n.endswith(".py")),
    ("run", lambda n: not n.endswith((".pyc", "~"))),
)

_SKIP_DIRS = {"__pycache__", ".runs", ".git", "node_modules"}

#: cached for the process — the harness cannot change under its own feet mid-run,
#: and hashing once keeps this off the end-of-run path more than once.
_CACHE: dict = {}


def harness_files(root: pathlib.Path = None) -> list:
    root = pathlib.Path(root or ROOT)
    out: list = []
    for rel, keep in _ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for fn in sorted(filenames):
                if keep(fn):
                    p = pathlib.Path(dirpath) / fn
                    if p.is_file():
                        out.append(p)
    return sorted(out, key=lambda p: str(p.relative_to(root)))


def source_hash(root: pathlib.Path = None) -> tuple:
    """-> (sha256 hex, file count). Deterministic across machines.

    The relative path and the byte length go into the digest with the content,
    so a rename or a truncation is a different hash even when the bytes that
    remain are identical.
    """
    root = pathlib.Path(root or ROOT)
    h = hashlib.sha256()
    n = 0
    for p in harness_files(root):
        rel = str(p.relative_to(root)).replace(os.sep, "/")
        try:
            data = p.read_bytes()
        except OSError:
            continue
        h.update(rel.encode())
        h.update(b"\0")
        h.update(str(len(data)).encode())
        h.update(b"\0")
        h.update(data)
        h.update(b"\n")
        n += 1
    return h.hexdigest(), n


def _git(*args, root: pathlib.Path = None):
    """A git query, or None. Never raises, never touches the network."""
    try:
        out = subprocess.run(
            ("git", "-C", str(root or ROOT)) + args,
            capture_output=True, text=True, timeout=5,
            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def harness_identity(root: pathlib.Path = None, use_cache: bool = True) -> dict:
    """R30's "harness version", typed.

    `id` is the ONE field a reader compares. It is the content hash, prefixed
    so it can never be mistaken for a git sha: `src-<12 hex>`.
    """
    key = str(root or ROOT)
    if use_cache and key in _CACHE:
        return dict(_CACHE[key])
    digest, count = source_hash(root)
    commit = _git("rev-parse", "HEAD", root=root)
    describe = _git("describe", "--always", "--tags", "--dirty", root=root)
    status = _git("status", "--porcelain", root=root)
    ident = {
        "id": f"src-{digest[:12]}",
        "source_sha256": digest,
        "source_files": count,
        "source_roots": [r for r, _ in _ROOTS],
        # Provenance only. Never folded into `id` — see the module docstring.
        "git_commit": commit,
        "git_describe": describe,
        # None, not False, when git could not be asked: "we do not know whether
        # the tree was dirty" is a different statement from "it was clean".
        "git_dirty": None if status is None else bool(status.strip()),
    }
    _CACHE[key] = dict(ident)
    return ident


def main(argv=None) -> int:                                    # pragma: no cover
    import json
    print(json.dumps(harness_identity(), indent=2))
    return 0


if __name__ == "__main__":                                     # pragma: no cover
    import sys
    sys.exit(main())
