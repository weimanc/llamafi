#!/usr/bin/env python3
"""check_get_keys.py — the generated `get`-key list may not under-enumerate.
TASK-600 / M-HARNESS2 R7.

WHY THIS EXISTS. `gen/gen_get_keys.py` claims two sources: cmdGet.cpp's own
`strcmp(args, "key")` chain, and the per-app `dbgGet()` chains it delegates to.
The second source produced **nothing at all** for months — its glob was
`app/src/**/*.h` while every body had moved to a `.cpp`, and its definition
regex did not match an out-of-line `bool CryptoApp::dbgGet(...)` even when
pointed at the right file. The measured effect: **43 keys enumerated against
111 that exist**, so `run/task488`'s "every key resolves — no unknown" check
covered about 39 % of the surface while reporting a clean sweep (WP-A `A-3`).

WHAT IT ASSERTS — three things, all blocking, all at zero today:

  G1  every `dbgGet` definition in the tree was VISITED by the generator.
      This is the real check. The oracle is a deliberately DUMBER full-tree
      scan — any line mentioning `dbgGet` that looks like a definition, over
      every source extension — so it over-approximates and can therefore only
      ever accuse the generator, never excuse it. Comparing the generator
      against a copy of its own algorithm would prove nothing, which is the
      trap this check is written to avoid.

  G2  the key count does not fall below MIN_KEYS. BP-024's console convention
      is additive-only with no renames, and M-TESTARCH §10 OQ-C closed on that
      evidence, so a DROP is by definition a defect — either a key was removed
      against the convention, or the generator regressed the way it just did.
      The floor is raised deliberately when keys are added; it is a shrink-only
      ledger with one row in it.

  G3  the generator produces a non-empty list at all — the failure mode that
      shipped silently once already (TASK-471 -> TASK-504).

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_get_keys.py [--list]
"""

from __future__ import annotations

import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, os.path.join(TOOLS, "gen"))

from gen_get_keys import collect_with_sites   # noqa: E402

#: The floor, measured 2026-09-03 immediately after TASK-600's fix (43 -> 111),
#: raised to 112 on 2026-09-06 when TASK-645 added `get boardId` (the board
#: identity the run artifact's premise needs). RAISE this when keys are added; a
#: drop is a finding, not a reason to lower it.
MIN_KEYS = 115   # TASK-635 added `get armed` (M-HARNESS2 R14); was 114 after
                 # TASK-678's `get bod` (F-1, PROP-011-rig-ground-truth.md §3.1)

#: Extensions the oracle will not open. Everything else under app/src/ is read
#: as text, INCLUDING extensions the generator's own globs do not list — that is
#: the point: if a `dbgGet` body ever lands in a `.cxx`, `.inc` or `.ino`, the
#: oracle sees it and the generator does not, and G1 fires.
_ORACLE_SKIP_EXT = (".png", ".bmp", ".jpg", ".bin", ".o", ".a", ".ttf", ".wsz")


def oracle_files() -> list:
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "app", "src")):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in sorted(filenames):
            if not fn.lower().endswith(_ORACLE_SKIP_EXT):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def oracle_sites() -> set:
    """(rel, line) for every `dbgGet` definition a dumb full-tree scan finds.

    Independent of the generator on BOTH axes that failed: the file set (every
    file under app/src/, not a glob list) and the definition pattern (any
    non-comment `dbgGet(` that is not a declaration and not a call).
    """
    out = set()
    for f in oracle_files():
        p = pathlib.Path(f)
        rel = str(p.resolve().relative_to(ROOT)).replace("\\", "/")
        lines = p.read_text(errors="replace").split("\n")
        for i, ln in enumerate(lines, 1):
            s = ln.split("//")[0]
            if "dbgGet" not in s or "(" not in s:
                continue
            if s.rstrip().endswith(";"):
                continue            # a declaration, not a definition
            if "." in s.split("dbgGet")[0][-2:] or "->" in s:
                continue            # a CALL through an instance, not a definition
            tail = "".join(lines[i - 1:i + 2])
            if "{" in tail.split("dbgGet", 1)[1]:
                out.add((rel, i))
    return out


def evaluate(keys, visited, oracle, min_keys: int = MIN_KEYS) -> list:
    """Pure: the three findings, so the negative suite can drive it directly."""
    out = []
    missed = sorted(oracle - set(visited))
    for rel, line in missed:
        out.append(f"G1 {rel}:{line}: a dbgGet definition the generator never "
                   f"read — its glob or its definition regex does not reach it")
    if not keys:
        out.append("G3 gen_get_keys.py produced NO keys — the console surface "
                   "cannot be empty; the scanner is broken")
    elif len(keys) < min_keys:
        out.append(f"G2 the key count fell to {len(keys)}, below the floor "
                   f"{min_keys}. The console is additive-only (BP-024), so a "
                   f"drop is either a removed key or a regressed scanner — "
                   f"never a reason to lower the floor")
    return out


def main(argv) -> int:
    keys, visited = collect_with_sites()
    oracle = oracle_sites()
    findings = evaluate(keys, visited, oracle)
    print(f"check_get_keys: {len(keys)} keys from {len(visited)} dbgGet "
          f"bodies + cmdGet.cpp (floor {MIN_KEYS}); full-tree scan of "
          f"{len(oracle_files())} files finds {len(oracle)} bodies")
    if "--list" in argv:
        for k in keys:
            print(f"    {k}")
    if findings:
        print(f"\nFAIL: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    print("  PASS  the generator reads every dbgGet body in the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
