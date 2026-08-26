#!/usr/bin/env python3
"""Print every `get` key the SERIAL_DEBUG console implements, comma-separated.

Two sources, both scanned statically so the list cannot drift from firmware:
  1. cmdGet.cpp's own `strcmp(args, "key")` chain (M-SRCLAYOUT Stage E /
     TASK-471 moved the body out of cmdGet.h into cmdGet.cpp; this script
     wasn't updated at the time and silently produced zero keys ever since —
     found and fixed incidentally while executing TASK-504);
  2. the per-app/per-display `dbgGet()` chains cmdGet.cpp delegates to.

Used by run/task488 to drive T_488_10 ("every key resolves — no 'unknown'").
"""

from __future__ import annotations

import glob
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
CMDGET = ROOT / "app/src/debug/serialConsole/cmdGet.cpp"

_DBGGET = re.compile(r"bool\s+dbgGet\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?\{")
_STRCMP = re.compile(r'strcmp\(\s*\w+\s*,\s*"([A-Za-z0-9_]+)"')


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


def collect() -> list[str]:
    keys: set[str] = set()
    if CMDGET.exists():
        keys |= set(re.findall(r'strcmp\(args,\s*"([A-Za-z0-9_]+)"', CMDGET.read_text()))
    for f in sorted(glob.glob(str(ROOT / "app/src/**/*.h"), recursive=True)):
        src = pathlib.Path(f).read_text(errors="replace")
        for m in _DBGGET.finditer(src):
            keys |= set(_STRCMP.findall(_body(src, m.end() - 1)))
    return sorted(keys)


if __name__ == "__main__":
    ks = collect()
    if not ks:
        print("ERROR: no get keys found — did cmdGet.h move?", file=sys.stderr)
        sys.exit(1)
    print(",".join(ks))
