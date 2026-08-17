#!/usr/bin/env python3
"""check_player_binding.py — M-TESTBASE §8.4: the mode-cycle binding gate.

WHY THIS EXISTS. The gesture that cycles player mode moved once already — eject
button -> taskbar player slot (TASK-413 `434b18d`, TASK-414 `07250ca`,
ADR-059 D6) — and the move broke things twice:

  1. The test harness, August 2026. TASK-414's own commit message: "eject was
     WebRadio's only entry path in the test harness, silently un-migrated since
     TASK-413 added the taskbar-cycle path." Three call sites were fixed by hand.
  2. A design document, ten months later, written with that commit message
     available, which specified a test battery driving the *old* surface.

Nothing failed either time. TASK-413 added a dispatch path and left the harness
on the old one, and every build gate stayed green. This file is the missing
mechanism: it asserts the binding CHAIN is intact, so the next relocation is a
loud failure instead of a silent one.

THE CHAIN, and what breaks if a link goes missing:

    resolvePlayerTap()          the one helper that owns restore-vs-cycle
      <- production dispatch    a tap on the taskbar player slot
      <- serial injection       the harness's tap path
      <- cmdPlayerCycle         the OPERATION, surface-independent (M-TESTBASE §8)
    get playerBind              states WHICH surface currently owns the cycle
    T_PMT_00                    the ONE test that reads playerBind and taps it

Remove `playerCycle` and every T_PMT test still "runs" and asserts nothing.
Add a fourth dispatch site without updating the docs and production diverges
from the harness again — the TASK-406 defect class ADR-059 D6's amendment
exists to prevent.

Run directly, or via app/tools/smoke_test.sh (run/check gate 9).

    python3 app/tools/check_player_binding.py [--strict]
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "app", "src")

# The call sites the design documents claim. Each entry is (path, why).
# ADDING A ROW HERE IS A DESIGN DECISION: a new caller of resolvePlayerTap is a
# new way to reach the mode cycle, and ADR-059 D6's amendment is explicit that a
# cycle reachable from one dispatch site but not another is the defect class the
# shared helper exists to prevent. Update ADR-059 D6 and M-TESTBASE §8 with it.
# file -> (expected call count, why). The COUNT matters, not just the filename:
# a negative test proved that checking filenames alone lets a NEW dispatch site
# be added inside main.cpp undetected — which is precisely the TASK-413 failure
# this gate exists to prevent.
EXPECTED_CALLERS = {
    "main.cpp": (2, "production taskbar dispatch + cmdPlayerCycle (ADR-059 D6, M-TESTBASE §8)"),
    "debug/serialConsole/cmdTouch.h": (1, "SERIAL_DEBUG tap injection (harness path)"),
}

failures: list[str] = []
notes: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def read(rel: str) -> str:
    p = os.path.join(SRC, rel)
    if not os.path.exists(p):
        failures.append(f"missing file: app/src/{rel}")
        return ""
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main() -> int:
    strict = "--strict" in sys.argv

    # ── 1. resolvePlayerTap exists and is defined exactly once ───────────────
    main_cpp = read("main.cpp")
    defs = re.findall(r"^static\s+AppId\s+resolvePlayerTap\s*\(", main_cpp, re.M)
    check(len(defs) == 1,
          f"resolvePlayerTap must be defined exactly once in main.cpp, found {len(defs)}")

    # ── 2. its callers are exactly the documented set ────────────────────────
    found: dict[str, int] = {}
    for dirpath, _dirs, files in os.walk(SRC):
        for fn in files:
            if not fn.endswith((".h", ".cpp")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, SRC)
            with open(full, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
            # Strip // comments AND double-quoted string literals before counting.
            # The gate's own first run found this: kCmds[]'s help text reads
            # "...cycle player mode via resolvePlayerTap (surface-independent)",
            # and `resolvePlayerTap\s*\(` matched the space before the paren —
            # so a HELP STRING was counted as a dispatch site. A binding gate that
            # miscounts its own subject is worse than no gate. (M-CODEQUAL §13.2:
            # in this codebase a grep-derived count is a hypothesis.)
            stripped = re.sub(r"//[^\n]*", "", body)
            stripped = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', stripped)
            n = len(re.findall(r"\bresolvePlayerTap\s*\(", stripped))
            if rel == "main.cpp":
                n -= len(defs)          # the definition is not a call
            if n > 0:
                found[rel] = n

    unexpected = sorted(set(found) - set(EXPECTED_CALLERS))
    missing = sorted(set(EXPECTED_CALLERS) - set(found))
    for rel, (want, why) in EXPECTED_CALLERS.items():
        got = found.get(rel, 0)
        if got and got != want:
            failures.append(
                f"CALL COUNT CHANGED in app/src/{rel}: {got} call(s), documented {want} "
                f"({why}).\n"
                f"        A new dispatch path to the mode cycle is a design decision, not a "
                f"refactor — it is how TASK-413 left the harness on the old surface with every "
                f"gate green.\n"
                f"        Update ADR-059 D6 + M-TESTBASE §8, then update EXPECTED_CALLERS here.")

    for rel in unexpected:
        failures.append(
            f"UNDOCUMENTED caller of resolvePlayerTap: app/src/{rel} ({found[rel]}x).\n"
            f"        A new dispatch path to the mode cycle is a design decision, not a "
            f"refactor.\n"
            f"        Update ADR-059 D6 + M-TESTBASE §8, then add it to EXPECTED_CALLERS here.")
    for rel in missing:
        failures.append(
            f"DOCUMENTED caller has disappeared: app/src/{rel} "
            f"({EXPECTED_CALLERS[rel][1]}).\n"
            f"        If the binding moved, T_PMT_00 and `get playerBind` must move with it.")

    # ── 3. the surface-independent operation still exists ────────────────────
    check("cmdPlayerCycle" in main_cpp,
          "cmdPlayerCycle is gone — T_PMT_01-03 drive the OPERATION through it; "
          "without it they assert nothing")
    check(re.search(r'\{\s*"playerCycle"\s*,\s*cmdPlayerCycle', main_cpp) is not None,
          'playerCycle is not registered in kCmds[] — the command is unreachable from the shell')
    check(re.search(r"resolvePlayerTap\s*\(", main_cpp[main_cpp.find("cmdPlayerCycle"):]
                    if "cmdPlayerCycle" in main_cpp else "") is not None,
          "cmdPlayerCycle does not call resolvePlayerTap — it must reuse the shared helper, "
          "not re-derive the cycle (ADR-059 D6 amendment)")

    # ── 4. the binding observable still exists ───────────────────────────────
    cmdget = read("debug/serialConsole/cmdGet.h")
    check('strcmp(args, "playerBind")' in cmdget,
          "`get playerBind` is gone — it is the ONE place the gesture->operation binding "
          "is stated, and T_PMT_00 reads it to locate the live surface")
    check('strcmp(args, "player")' in cmdget,
          "`get player` is gone — T_PMT_01-03 assert the whole vector it returns")

    # ── 5. the binding test still exists and still reads playerBind ──────────
    runner = os.path.join(HERE, "run_serialdbg_tests.py")
    if os.path.exists(runner):
        with open(runner, encoding="utf-8", errors="replace") as fh:
            rb = fh.read()
        # Match the REGISTRY ENTRY, not the id anywhere. A negative test caught
        # this: deleting `"T_PMT_00": t_pmt_00,` from ALL_TESTS left the id in the
        # body's own pass_()/fail() strings, so a substring check still passed
        # while the test no longer ran at all.
        check(re.search(r'"T_PMT_00"\s*:\s*t_pmt_00', rb) is not None,
              "T_PMT_00 is not registered in ALL_TESTS — the binding test is the only "
              "thing that notices when the surface moves, and an unregistered test "
              "never runs")
        check("get playerBind" in rb,
              "no test reads `get playerBind` — the observable exists but nothing checks it, "
              "which is how the binding rotted the first two times")
    else:
        notes.append("run_serialdbg_tests.py not found — skipped the test-side checks")

    # ── report ───────────────────────────────────────────────────────────────
    print("=== check_player_binding.py — M-TESTBASE §8.4 ===")
    for rel, n in sorted(found.items()):
        why = EXPECTED_CALLERS.get(rel, (None, "UNDOCUMENTED"))[1]
        print(f"  [ok] resolvePlayerTap caller: app/src/{rel} ({n}x) — {why}")
    for n in notes:
        print(f"  [note] {n}")
    if failures:
        print()
        for f in failures:
            print(f"  FAIL: {f}")
        print(f"\n=== {len(failures)} binding check(s) failed ===")
        return 1
    print("\n=== player-mode binding chain intact ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
