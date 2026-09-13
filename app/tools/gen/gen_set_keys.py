#!/usr/bin/env python3
r"""Print every console `set` key the SERIAL_DEBUG console implements.

Modeled directly on `gen_get_keys.py` (TASK-600 / M-HARNESS2 R7) — same two-
source shape, same "return the visited sites too" discipline (WP-A A-3: a
generator that cannot say what it read cannot be checked for what it missed).

Three sources, all scanned statically:

  1. `cmdSet.cpp`'s own top-level commands. Most of the file is a single
     `strcmp(var, "key")` chain after a `sscanf(args, "%31s %127s", var, val)`
     split, but a number of commands (`kbText`, `now`, `geocode`, `fault bod`,
     `scanLoop`, …) take multi-token or raw arguments that don't fit that
     split, and are special-cased against the raw `args` pointer with
     `strncmp(args, "key", N)` / `strcmp(args, "key")` BEFORE the split runs.
     Both shapes are scanned; a trailing space some of those literals carry
     (`"geocode "`, `"fault "`) is stripped so the emitted key matches what a
     harness actually types.
  2. Per-app `dbgSet` bodies — `bool Class::dbgSet(const char*, const char*)`,
     in-class or out-of-line, anywhere under app/src. Same glob/regex fix
     TASK-600 made for `dbgGet` (out-of-line `Class::` bodies live in .cpp).
  3. `spotifyTask::dbg_set` — a lone exception to the `dbgSet` name (the
     module predates the `dbgGet`/`dbgSet` convention). Matched by the same
     regex, widened to accept the `dbg_set` spelling.

Used by `gate/check_armed_injectors.py` (TASK-635 §2.5) to assert every `set`
key is either a declared armed injector (`app/src/debug/armedInjectors.h`) or
is named in that gate's own `NOT_INJECTORS` table with a reason.

KNOWN LIMIT (documented per the TASK-635 prompt, not silently swallowed):
this script does not enumerate *other* top-level console commands (`get`,
`tap`, …) or other consoles' arming surfaces (e.g. `cmdMisc.cpp`/
`cmdSystem.cpp`/`cmdSd.cpp`/`cmdTouch.cpp` top-level commands that are not
routed through `cmdSet.cpp`). Scope is `set` + `dbgSet`/`dbg_set` keys only —
cheap to extract and the entire membership surface armedInjectors.h's design
doc (§2.2) reasons about. A command that arms state through some OTHER
console verb would not be caught by this generator or its gate.
"""

from __future__ import annotations

import glob
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
CMDSET = ROOT / "app/src/debug/serialConsole/cmdSet.cpp"

#: A `dbgSet`/`dbg_set` DEFINITION, in-class or out-of-line. `dbg_?[Ss]et`
#: covers both the normal `dbgSet` convention and spotifyTask's lone
#: `dbg_set` holdout.
_DBGSET = re.compile(
    r"bool\s+(?:[A-Za-z_]\w*::)?dbg_?[Ss]et\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?\{")
_STRCMP_VAR = re.compile(r'strcmp\(\s*var\s*,\s*"([A-Za-z0-9_]+)"')

#: cmdSet.cpp's own two shapes: raw-`args` special cases taken BEFORE the
#: `sscanf(args, "%31s %127s", var, val)` split (multi-token / free-form
#: commands), and the `strcmp(var, "key")` chain taken after it.
_ARGS_KEY = re.compile(r'str(?:n)?cmp\(\s*args\s*,\s*"([A-Za-z0-9_ ]+)"')

SOURCE_GLOBS = ("app/src/**/*.h", "app/src/**/*.hpp",
                "app/src/**/*.cpp", "app/src/**/*.cc")


def source_files() -> list[str]:
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
    """-> (sorted keys, the set of `(repo-relative file, line)` dbgSet/dbg_set
    bodies read). See `gen_get_keys.collect_with_sites` for why the second
    half exists — it is what a completeness gate over THIS generator would
    check, mirroring `check_get_keys.py`'s G1, should one ever be added."""
    keys: set[str] = set()
    sites: set[tuple[str, int]] = set()
    if CMDSET.exists():
        src = CMDSET.read_text()
        for m in _ARGS_KEY.finditer(src):
            keys.add(m.group(1).strip())
        keys |= set(_STRCMP_VAR.findall(src))
    for f in source_files():
        src = pathlib.Path(f).read_text(errors="replace")
        rel = str(pathlib.Path(f).resolve().relative_to(ROOT)).replace("\\", "/")
        for m in _DBGSET.finditer(src):
            sites.add((rel, src.count("\n", 0, m.start()) + 1))
            keys |= set(_STRCMP_VAR.findall(_body(src, m.end() - 1)))
    return sorted(keys), sites


def collect() -> list[str]:
    return collect_with_sites()[0]


if __name__ == "__main__":
    ks = collect()
    if not ks:
        print("ERROR: no set keys found — did cmdSet.cpp move?", file=sys.stderr)
        sys.exit(1)
    print(",".join(ks))
