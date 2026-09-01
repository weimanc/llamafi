#!/usr/bin/env python3
"""check_test_meta.py — the (cls, scope, effect) record gate. TASK-570.

WHY THIS EXISTS. M-TESTARCH §13.3 settles the test record in one pass and then
makes a specific bet: the value is SEEDED from the family module and the id
prefix, and a hand DECLARATION overrides the seed. That bet only holds if
something enforces the invariants, because every one of them fails silently:

  * an id that resolves to no scope is invisible to `--scope` and nobody notices
    (it just never shows up in a selection);
  * a declaration with no reason is indistinguishable from a typo, and §13.3's
    whole argument for allowing overrides is that a REASON is what separates a
    considered placement from a slip;
  * a scope outside the enum selects nothing, quietly;
  * two enum values differing only by case (`Spotify` vs the old `spotify`) are
    a live defect in a CLI value — one `.lower()` in a resolver and the wrong set
    runs with no error printed. §13.3 renamed the value to kill this; this gate
    is what stops it being reintroduced;
  * a hand-typed scope that merely restates the seed is exactly what EC-D2
    forbids ("zero hand-typed scope values among them"), and it rots the moment
    a family is renamed.

The gate deliberately does NOT assert seed == declaration. An equality gate
would reject the suite's most deliberate placements on day one (the T_PMT_*
cross-mode cells), which is how implementers learn to weaken a gate.

It also prints the census, so a DROP in the seeded count is visible in the run
log rather than being a documentation edit somebody has to remember.

No DUT, no build, no network. Run directly, or via app/tools/smoke_test.sh
(run/check gate 9).

    python3 app/tools/gate/check_test_meta.py
"""

from __future__ import annotations

import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from app_ids_gen import APP_ORDER                     # noqa: E402
import suite.serialdbg as _suite                      # noqa: E402
from suite.serialdbg import _meta                     # noqa: E402


def evaluate(records: dict, scopes=None, classes=None, effects=None) -> list:
    """Pure: records -> list of findings. Takes the enums as arguments so the
    negative suite can mutate them without touching the module."""
    scopes = tuple(scopes if scopes is not None else _meta.SCOPES)
    classes = tuple(classes if classes is not None else _meta.CLASSES)
    effects = tuple(effects if effects is not None else _meta.EFFECTS)
    out: list = []

    # (c) the enum itself — case-sensitively, and no case-only collisions.
    seen_lower: dict = {}
    for s in scopes:
        prev = seen_lower.get(s.lower())
        if prev is not None and prev != s:
            out.append(f"scope enum has a case-only collision: {prev!r} vs {s!r} "
                       f"— a CLI value that differs only by case selects the wrong "
                       f"set silently (M-TESTARCH §13.3)")
        seen_lower[s.lower()] = s

    for tid, r in records.items():
        # (a) every id resolves.
        if not r.get("scope") or r["scope"] == _meta.UNKNOWN_SCOPE:
            out.append(f"{tid}: no scope — neither seeded nor declared")
        elif r["scope"] not in scopes:
            out.append(f"{tid}: scope {r['scope']!r} is not in the enum "
                       f"({', '.join(scopes)})")
        if r.get("cls") not in classes:
            out.append(f"{tid}: cls {r.get('cls')!r} is not in {classes}")
        # every step declares an effect, and it is one of the three (EC-S1).
        if r.get("effect") not in effects:
            out.append(f"{tid}: effect {r.get('effect')!r} is not in {effects}")

        # (b) every OVERRIDE carries a reason.
        if r.get("scope_declared"):
            if not r.get("scope_reason"):
                out.append(f"{tid}: declares scope={r['scope']!r} with no "
                           f"scope_reason — a declaration without a reason cannot "
                           f"be told from a typo (M-TESTARCH §13.3)")
            # EC-D2: no hand-typed value where the seeder already derives one.
            if r["scope"] == r.get("scope_seed"):
                out.append(f"{tid}: declares scope={r['scope']!r}, which is exactly "
                           f"what the {r.get('scope_seeded_by')} seed already "
                           f"derives — hand-typing a seeded value is what EC-D2 "
                           f"forbids. Drop the scope= and keep scope_reason= if "
                           f"the placement needs a note.")
        if r.get("effect_declared") and not r.get("effect_reason"):
            out.append(f"{tid}: declares effect={r['effect']!r} with no effect_reason")
        if r.get("cls_declared") and r["cls"] not in classes:
            out.append(f"{tid}: declares cls={r['cls']!r}, not in {classes}")

        # The seeder must reach every id in an app family module. A catch-all
        # outside shell.py means a family module stopped mapping to its app —
        # a rename would otherwise silently lose that family's whole id set.
        if r.get("scope_seeded_by") == "catch-all" and r.get("module") != "shell":
            out.append(f"{tid}: module {r['module']!r} seeds nothing — it no longer "
                       f"matches an APP_ORDER app. Renaming a family module must "
                       f"not silently drop its ids out of --scope.")

    return out


def census(records: dict) -> dict:
    by_scope = collections.Counter(r["scope"] for r in records.values())
    by_cls = collections.Counter(r["cls"] for r in records.values())
    by_effect = collections.Counter(r["effect"] for r in records.values())
    by_how = collections.Counter(r["scope_seeded_by"] for r in records.values())
    return {
        "total": len(records),
        "seeded": by_how["module"] + by_how["prefix"],
        "by_module": by_how["module"],
        "by_prefix": by_how["prefix"],
        "catch_all": by_how["catch-all"],
        "declared": sum(1 for r in records.values() if r["scope_declared"]),
        "scope": by_scope, "cls": by_cls, "effect": by_effect,
    }


def main() -> int:
    findings: list = []
    notes: list = []

    records = _suite.build_all_meta()
    tests = _suite.build_all_tests()

    if set(records) != set(tests):
        findings.append("build_all_meta() and build_all_tests() disagree on the id "
                        f"set: only-meta={sorted(set(records) - set(tests))} "
                        f"only-tests={sorted(set(tests) - set(records))}")

    findings += evaluate(records)

    # The file -> scope map (§13.4). The GLOB is the specification, not
    # app/src/apps/: Stock and Aquarium predate that directory.
    try:
        app_map = _meta.app_source_map(ROOT)
        notes.append(f"app/src/**/*App.cpp -> {len(app_map)} files == APP_ORDER")
    except AssertionError as e:
        findings.append(str(e))

    # The prefix table's values must be in the enum too — it is typed data, and
    # a typo there silently attributes a whole prefix to nothing.
    for pref, sc in _meta.PREFIX_SCOPES.items():
        if sc not in _meta.SCOPES:
            findings.append(f"PREFIX_SCOPES[{pref!r}] = {sc!r} is not in the scope enum")

    # META_OVERRIDES is the escape hatch for registry entries that are not
    # functions. It must not become a second declaration channel for entries
    # that could carry a decorator.
    import importlib
    for fam in _suite._FAMILY_MODULES:
        mod = importlib.import_module(f"suite.serialdbg.{fam}")
        for tid, decl in getattr(mod, "META_OVERRIDES", {}).items():
            if tid not in mod.TESTS:
                findings.append(f"{fam}.META_OVERRIDES has {tid!r}, which is not in "
                                f"its TESTS dict — dead metadata")
            elif mod.TESTS[tid] is not None:
                findings.append(f"{fam}.META_OVERRIDES declares {tid!r}, whose registry "
                                f"entry IS a function — use @meta(...) on it, so the "
                                f"declaration lives next to the code it describes")

    c = census(records)
    print("=== check_test_meta.py — the (cls, scope, effect) record (TASK-570) ===")
    print(f"  ids: {c['total']}   scope seeded: {c['seeded']} "
          f"({c['by_module']} by module + {c['by_prefix']} by prefix), "
          f"catch-all: {c['catch_all']}, declarations: {c['declared']}")
    print(f"  cls:    " + ", ".join(f"{k}={v}" for k, v in sorted(c["cls"].items())))
    print(f"  effect: " + ", ".join(f"{k}={v}" for k, v in sorted(c["effect"].items())))
    print(f"  scope:  " + ", ".join(f"{k}={v}" for k, v in sorted(c["scope"].items())))
    for n in notes:
        print(f"  [note] {n}")

    if findings:
        print()
        for f in findings:
            print(f"  FAIL: {f}")
        print(f"\n=== {len(findings)} record check(s) failed ===")
        return 1
    print("\n=== every id resolves; every override carries a reason ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
