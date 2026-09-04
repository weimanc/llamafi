#!/usr/bin/env python3
r"""Print every `get` key the SERIAL_DEBUG console implements, comma-separated.

Two sources, both scanned statically so the list cannot drift from firmware:
  1. cmdGet.cpp's own `strcmp(args, "key")` chain (M-SRCLAYOUT Stage E /
     TASK-471 moved the body out of cmdGet.h into cmdGet.cpp; this script
     wasn't updated at the time and silently produced zero keys ever since —
     found and fixed incidentally while executing TASK-504);
  2. the per-app/per-display `dbgGet()` chains cmdGet.cpp delegates to.

Used by run/task488 to drive T_488_10 ("every key resolves — no 'unknown'").

TASK-600 / M-HARNESS2 R7 — WHY THIS SCANNED 43 OF 71+ KEYS FOR MONTHS.
Source 2 had two independent blind spots, and each on its own was enough:

  * the glob was `app/src/**/*.h`, so every `dbgGet()` body M-SRCLAYOUT moved
    into a `.cpp` was invisible;
  * the definition regex was `bool\s+dbgGet\s*\(`, which does not match an
    out-of-line definition — `bool CryptoApp::dbgGet(const char*, ...) const {`
    carries a `Class::` qualifier, and every `.cpp` body has one.

Fixing only the glob would have found the files and still matched nothing. Both
are fixed here, and `gate/check_get_keys.py` now asserts — blocking, in
`run/check` — that the set of `dbgGet` definitions this script VISITS equals the
set a deliberately dumber full-tree scan can find. `collect()` therefore returns
its visited sites as well as its keys: a generator that cannot say what it read
cannot be checked for what it missed (WP-A `A-3`).
"""

from __future__ import annotations

import glob
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
CMDGET = ROOT / "app/src/debug/serialConsole/cmdGet.cpp"

#: A `dbgGet` DEFINITION, in-class or out-of-line. The `(?:\w+::)?` group is the
#: half TASK-600 added: every body that moved to a `.cpp` is qualified.
_DBGGET = re.compile(
    r"bool\s+(?:[A-Za-z_]\w*::)?dbgGet\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?\{")
_STRCMP = re.compile(r'strcmp\(\s*\w+\s*,\s*"([A-Za-z0-9_]+)"')

#: Every extension a firmware source can carry. Not `*.h` — see the module
#: docstring; and not a bare `*` either, so a stray `.md` or `.json` under
#: app/src/ is not scanned as C++.
SOURCE_GLOBS = ("app/src/**/*.h", "app/src/**/*.hpp",
                "app/src/**/*.cpp", "app/src/**/*.cc")


def source_files() -> list[str]:
    """Every firmware source file, sorted and de-duplicated."""
    out: set[str] = set()
    for pat in SOURCE_GLOBS:
        out |= set(glob.glob(str(ROOT / pat), recursive=True))
    return sorted(out)


def _body(src: str, brace_pos: int) -> str:
    depth = 0
    for j in range(brace_pos, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[brace_pos:j]
    return src[brace_pos:]


def collect_with_sites() -> tuple[list[str], set[tuple[str, int]]]:
    """-> (sorted keys, the set of `(repo-relative file, line)` dbgGet bodies read).

    The second half exists for `gate/check_get_keys.py`: the failure mode this
    generator had was not a wrong key, it was a body it never opened, and only
    the visited-site set makes that checkable.
    """
    keys: set[str] = set()
    sites: set[tuple[str, int]] = set()
    if CMDGET.exists():
        keys |= set(re.findall(r'strcmp\(args,\s*"([A-Za-z0-9_]+)"', CMDGET.read_text()))
    for f in source_files():
        src = pathlib.Path(f).read_text(errors="replace")
        rel = str(pathlib.Path(f).resolve().relative_to(ROOT)).replace("\\", "/")
        for m in _DBGGET.finditer(src):
            sites.add((rel, src.count("\n", 0, m.start()) + 1))
            keys |= set(_STRCMP.findall(_body(src, m.end() - 1)))
    return sorted(keys), sites


def collect() -> list[str]:
    return collect_with_sites()[0]


if __name__ == "__main__":
    ks = collect()
    if not ks:
        print("ERROR: no get keys found — did cmdGet.h move?", file=sys.stderr)
        sys.exit(1)
    print(",".join(ks))
