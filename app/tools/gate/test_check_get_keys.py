#!/usr/bin/env python3
"""Negative tests for check_get_keys.py and the generator behind it — BP-068.
TASK-600 / M-HARNESS2 R7.

The defect this gate exists for was not a wrong key, it was a body the generator
never opened, and it survived for months because everything downstream reported
a clean sweep over 39 % of the surface. So the cases below break the generator in
each of the two ways it was actually broken — an unreachable file extension and
an unmatched out-of-line definition — and assert the gate fires; two positive
controls guard the other direction.

G1's independence is the property under test in E1. If the oracle ever shares the
generator's file list or its regex, the check degrades into the generator
agreeing with itself, which is exactly what it looked like it was doing before.

No DUT, no build, no network.
Run: python3 app/tools/gate/test_check_get_keys.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "gen"))

import check_get_keys as C                              # noqa: E402
import gen_get_keys as G                                # noqa: E402

_TMP: list[Path] = []

#: An out-of-line body in an extension the generator's globs do not list. Both
#: of the generator's historical blind spots in one file.
PROBE_BODY = """
bool ProbeApp::dbgGet(const char* var, char* buf, int len) const {
  if (strcmp(var, "h2ProbeKeyAlpha") == 0) { return true; }
  if (strcmp(var, "h2ProbeKeyBeta") == 0) { return true; }
  return false;
}
"""


def drop(name: str, body: str) -> Path:
    p = Path(C.ROOT) / "app" / "src" / name
    p.write_text(body, encoding="utf-8")
    _TMP.append(p)
    return p


def one(fs, needle):
    hits = [f for f in fs if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {fs}"
    return hits


def none(fs):
    assert not fs, f"expected no findings, got {fs}"


# ── negative cases ───────────────────────────────────────────────────────────

def case_body_the_generator_cannot_reach():
    """E1 — a real end-to-end regression, not a simulated one.

    The probe lands in `.cxx`, which `SOURCE_GLOBS` does not list. The oracle
    walks every file under app/src/, so it sees the body; the generator does
    not; G1 must fire and must name the file.
    """
    # Cleaned up HERE, not in main()'s finally: the probe lands in the live
    # app/src/ tree, and P1/P2 assert that same tree is clean. Deferring the
    # removal to the end of the run makes this case's fixture into the next
    # case's failure — which is exactly what it did on the first run.
    probe = drop("_h2probe_getkeys.cxx", PROBE_BODY)
    try:
        keys, visited = G.collect_with_sites()
        fs = C.evaluate(keys, visited, C.oracle_sites())
        one(fs, "_h2probe_getkeys.cxx")
        one(fs, "the generator never")
    finally:
        os.remove(probe)
        _TMP.remove(probe)


def case_out_of_line_definition_regex():
    """E2 — the second historical blind spot, isolated.

    With the pre-TASK-600 regex (no `Class::` group) the generator matches
    nothing in a `.cpp`, so every one of the ten real bodies becomes a G1.
    """
    old = G._DBGGET
    try:
        G._DBGGET = re.compile(
            r"bool\s+dbgGet\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?\{")
        keys, visited = G.collect_with_sites()
        assert not visited, "the pre-fix regex should match no out-of-line body"
        fs = C.evaluate(keys, visited, C.oracle_sites())
        assert len(fs) >= 10, f"expected >=10 G1 findings, got {len(fs)}: {fs}"
    finally:
        G._DBGGET = old


def case_pre_fix_glob_finds_nothing():
    """E3 — the state that shipped: `*.h` only. Every body is in a `.cpp`, so
    source 2 contributed zero keys and the tool reported 43 as if complete."""
    old = G.SOURCE_GLOBS
    try:
        G.SOURCE_GLOBS = ("app/src/**/*.h",)
        keys, visited = G.collect_with_sites()
        assert not visited, "pre-fix glob should visit no dbgGet body"
        assert len(keys) < C.MIN_KEYS, (
            f"pre-fix generator should be below the floor, got {len(keys)}")
        fs = C.evaluate(keys, visited, C.oracle_sites())
        one(fs, "below the floor")
    finally:
        G.SOURCE_GLOBS = old


def case_empty_key_list():
    fs = C.evaluate([], set(), set())
    one(fs, "produced NO keys")


def case_count_below_floor():
    fs = C.evaluate(["a", "b"], set(), set(), min_keys=50)
    one(fs, "below the floor")


# ── positive controls ────────────────────────────────────────────────────────

def case_live_tree_is_clean():
    keys, visited = G.collect_with_sites()
    none(C.evaluate(keys, visited, C.oracle_sites()))


def case_declarations_are_not_definitions():
    """The ten `.h` lines are `bool dbgGet(...) const;` — declarations. If the
    oracle counted those, G1 would be permanently red and would be muted within
    a week, which is how a gate dies."""
    sites = C.oracle_sites()
    for rel, _line in sites:
        assert rel.endswith((".cpp", ".cc", ".cxx")), (
            f"oracle counted a non-definition site: {rel}")
    assert len(sites) == 10, f"expected 10 dbgGet bodies, found {len(sites)}"


def case_fix_actually_recovered_the_app_keys():
    """The measurement TASK-600 exists for: keys reachable ONLY through a
    per-app body must now be present. `cmdGet.cpp` alone yielded 43 when this
    was written and 44 since TASK-645 added `get boardId`; the arm asserts the
    RELATIONSHIP (source 2 contributes the bulk), so the literal is a tripwire
    on the source-1 count and is updated with it, never relaxed away."""
    keys, _ = G.collect_with_sites()
    cmdget = set(re.findall(r'strcmp\(args,\s*"([A-Za-z0-9_]+)"',
                            G.CMDGET.read_text()))
    assert len(cmdget) == 48, f"cmdGet.cpp source-1 count changed: {len(cmdget)}"   # 48 since TASK-637 (`get appTicks`, was 47 since TASK-635's `get armed`)
    assert len(keys) > len(cmdget) + 50, (
        f"source 2 is still contributing almost nothing: {len(keys)} total "
        f"vs {len(cmdget)} from cmdGet.cpp")


def case_floor_matches_reality():
    """The floor is a ledger row, so it must equal what the tree actually has —
    a floor set below the truth silently re-admits the regression it exists to
    catch."""
    keys, _ = G.collect_with_sites()
    assert len(keys) == C.MIN_KEYS, (
        f"MIN_KEYS is {C.MIN_KEYS} but the tree has {len(keys)} keys — raise "
        f"the floor in the same commit that adds keys")


CASES = [
    ("E1  a body in an unreachable extension", case_body_the_generator_cannot_reach),
    ("E2  the pre-fix out-of-line regex",       case_out_of_line_definition_regex),
    ("E3  the pre-fix *.h-only glob",           case_pre_fix_glob_finds_nothing),
    ("E4  an empty key list is a finding",      case_empty_key_list),
    ("E5  a count below the floor",             case_count_below_floor),
    ("P1  the live tree is clean",              case_live_tree_is_clean),
    ("P2  declarations are not definitions",    case_declarations_are_not_definitions),
    ("P3  the app keys came back (47 -> 115)",  case_fix_actually_recovered_the_app_keys),
    ("P4  the floor equals reality",            case_floor_matches_reality),
]


def main() -> int:
    failed = 0
    try:
        for name, fn in CASES:
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL  {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  ERROR {name}: {type(e).__name__}: {e}")
    finally:
        for p in _TMP:
            try:
                os.remove(p)
            except OSError:
                pass
    print(f"test_check_get_keys: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
