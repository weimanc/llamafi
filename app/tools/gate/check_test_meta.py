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
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(ROOT, "app", "gen"))

from app_ids_gen import APP_ORDER                     # noqa: E402
import suite.serialdbg as _suite                      # noqa: E402
from suite.serialdbg import _meta                     # noqa: E402
from suite.serialdbg import _order                    # noqa: E402
from read_keys import READ_KEYS as _READ_KEYS         # noqa: E402 (generated, TASK-641)


# ── R35: a class is DECLARED for every gating id, never defaulted (TASK-591) ──
#
# The rest of this file asserts the record is WELL-FORMED. This section asserts
# one thing about it is TRUE: that a class which can stop the run was chosen by
# a person who wrote down why, and not applied by `_meta.seed_cls()` because the
# id's scope happened to be `shell`/`taskbar`/`boot`/`spotify-chrome`.
#
# WHY IT LIVES HERE AND NOT IN A NEW FILE. R35 is a property of the (cls, scope,
# effect) record, and this gate already owns that record: it builds it once,
# reconciles the two registries, and prints the census. A parallel checker would
# rebuild the same records, and would have to re-derive the RIG/HEALTH/CORE set
# from the same two modules — a second place for the gating set to be defined,
# which is precisely the defect `check_flake_class.py:79` avoided by deriving
# GATING from `_order.CORE_BLOCKS` rather than typing it. One record, one gate.
#
# The set is derived, not typed, for the same reason: adding a class above
# FEATURE must widen this check automatically, not silently narrow it.
GATING = tuple(c for c in _meta.CLASSES if c not in _order.CORE_BLOCKS)

LEDGER_REL = "docs/verification/gating_class_declarations.md"

#: Only G1 is exemptable. G3 is at zero today, and an exemption kind with no
#: rows is an invitation to open one (the R37 ledger's rule 4).
EXEMPTABLE = ("undeclared-gating-class",)

#: A reason is a SENTENCE, not a tag. `scope_reason`/`effect_reason` are
#: deliberately one-word — they separate a considered placement from a typo. A
#: `cls_reason` has to carry an argument about the rest of the run, so a length
#: floor is the cheapest thing that rejects `cls_reason="core"` outright. It
#: cannot check that the argument is GOOD; writing 43 of them is the audit
#: (R35's own verification note), and this only stops the null case.
MIN_CLS_REASON = 80

_TASK_RE = re.compile(r"^TASK-\d+$")
_SEP_RE = re.compile(r":?-{2,}:?")


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: str = None) -> tuple:
    """-> ({(kind, id): 'rel:line'}, [malformed-row errors]).

    Same shape and same rules as the R37 ledger (`check_flake_class.parse_ledger`)
    and the C6 ledger before it: keyed on `(kind, id)`, an owning TASK id and an
    ISO `since` date required, no wildcards of any sort.
    """
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    header = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = _cells(s)
        if all(_SEP_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if len(cells) < 5:
            continue
        tid, kind, owner, since = (cells[0].strip("`* "), cells[1],
                                   cells[3], cells[4])
        if kind not in EXEMPTABLE:
            errors.append(f"{rel}:{i}: kind {kind!r} is not exemptable "
                          f"(allowed: {', '.join(EXEMPTABLE)})")
            continue
        if not _TASK_RE.match(owner.strip("`* ")):
            errors.append(f"{rel}:{i}: owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since.strip("`* "))
        except ValueError:
            errors.append(f"{rel}:{i}: since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[(kind, tid)] = f"{rel}:{i}"
    return rows, errors


def evaluate_gating_classes(records: dict, ledger=None, gating=None) -> list:
    """R35, pure. `records` -> findings; the ledger grandfathers G1 only."""
    ledger = dict(ledger or {})
    gating = tuple(gating if gating is not None else GATING)
    out: list = []
    used: set = set()

    for tid in sorted(records):
        r = records[tid]
        cls = r.get("cls")
        if cls not in gating:
            continue
        reason = (r.get("cls_reason") or "").strip()
        if not r.get("cls_declared") or not reason:
            key = ("undeclared-gating-class", tid)
            if key in ledger:
                used.add(key)
                continue
            how = ("declared with no reason" if r.get("cls_declared")
                   else f"SEEDED from scope {r.get('scope')!r}")
            out.append(
                f"G1 {tid}: class {cls} is {how} — a class that can stop the run "
                f"must be chosen, not defaulted. Add "
                f"@meta(cls={cls!r}, cls_reason=…) saying what makes this test's "
                f"failure mean the rest of the run cannot be trusted. If you "
                f"cannot write that sentence, the id is FEATURE — declare that "
                f"instead (M-HARNESS2 R35)")
        elif len(reason) < MIN_CLS_REASON:
            out.append(
                f"G3 {tid}: cls_reason is {len(reason)} chars — too short to be an "
                f"argument. It must say what makes this test's failure mean the "
                f"rest of the run cannot be trusted, not restate the class name "
                f"(M-HARNESS2 R35). Not exemptable")

    for key, where in sorted(ledger.items()):
        if key not in used:
            out.append(
                f"G2 {where}: stale exception for {key[1]} ({key[0]}) — that id now "
                f"declares its class, so the finding this row suppresses no longer "
                f"occurs. Delete the row. The ledger can only shrink")
    return out


# ── TASK-641: the falsifier record (oracle/premise/falsifier, §7) ───────────
#
# WHY THIS EXISTS. §7 adds a second declaration surface next to (cls, scope,
# effect): which of a body's reads is the ORACLE the claim is about, which is
# a PREMISE, and (by omission) which is INCIDENTAL. Two things fail silently
# if nothing checks them, the same way the (cls, scope, effect) record did
# before this file existed:
#
#   * a shape or falsifier value outside its closed enum has no operator a
#     future driver (TASK-643) could run against it — it would just never
#     fire, and nobody would notice until AC4's confirmed-share number came
#     back wrong for a reason nobody could find by reading the record;
#   * a declared ORACLE key that the body does not actually read is worse
#     than no declaration at all — it tells a future reader (and a future
#     driver) to falsify a read that never happens. Checked against the
#     GENERATED set in app/gen/read_keys.py, the same way `ops` is checked
#     against `OPS` (P2) rather than trusted on the author's word;
#   * an expired `physical` falsifier is exactly `flaky.yaml`'s expired
#     `review_by` (F8) wearing a different name — a record that is no longer
#     backed by anything current must fail loudly, not sit there looking
#     confirmed.
#
# APPROX ids (`read_keys.py`'s static-walk fallback, no transcript): the same
# check applies. APPROX's incompleteness is UNDER-approximation only — a
# dynamic (f-string) read is listed as `unresolved`, never silently dropped,
# and every key the static walk DOES resolve to a literal is a real read the
# same way a transcript-derived key is. So a missing ORACLE key on an APPROX
# id is still evidence of a bad declaration, not a gate artifact — the
# finding just adds a one-line hint pointing at the weaker evidence, in case
# re-running the walk (or recording a transcript) is the actual fix.
_PHYSICAL_RE = re.compile(r"^physical:.+;\s*expires\s+(\d{4}-\d{2}-\d{2})\s*$")

# TASK-714 — the two shapes whose operator needs more than the key name.
# `THRESHOLD`'s operator (`lib.falsify_ops.perturb_threshold`) has to move a
# derived numeric reading by more than a bound it cannot infer from the
# reply's type the way `SNAPSHOT`'s `+1`/`SUBSTRING`'s character scramble can
# — so the bound has to be declared data, checked the same way `ops` is
# checked against `OPS`: an undeclared or malformed bound is an operator with
# nothing to run against, and a `bounds` entry with no `THRESHOLD` key behind
# it is dead data nobody will ever notice going stale (M-HARNESS2 §3 TASK-714
# amendment).
_BOUNDED_SHAPES = frozenset({"THRESHOLD"})


def evaluate_falsifiers(records: dict, read_keys: dict = None, today=None) -> list:
    """Pure: records -> findings. `read_keys` defaults to the generated
    `app/gen/read_keys.py::READ_KEYS`; `today` to `date.today()` — both
    overridable so the negative suite can drive small fixtures without a
    real transcript or the system clock."""
    read_keys = read_keys if read_keys is not None else _READ_KEYS
    today = today if today is not None else datetime.date.today()
    out: list = []

    for tid in sorted(records):
        r = records[tid]
        oracle = r.get("oracle") or {}
        falsifier = r.get("falsifier")
        bounds = r.get("bounds") or {}

        for key, shape in sorted(oracle.items()):
            if shape not in _meta.SHAPES:
                out.append(
                    f"{tid}: oracle {key!r} declares shape {shape!r}, not in "
                    f"{_meta.SHAPES} — a shape outside the enum names no "
                    f"mutation operator, so nothing could ever falsify it "
                    f"(M-HARNESS2 §3)")
            elif shape in _BOUNDED_SHAPES:
                bound = bounds.get(key)
                if bound is None:
                    out.append(
                        f"{tid}: oracle {key!r} declares {shape!r} with no "
                        f"bounds[{key!r}] — the operator does not know how "
                        f"far past the reading counts as 'crossed the bound' "
                        f"without it (M-HARNESS2 §3 TASK-714 amendment)")
                elif isinstance(bound, bool) or not isinstance(bound, (int, float)) \
                        or bound <= 0:
                    out.append(
                        f"{tid}: bounds[{key!r}] = {bound!r} is not a positive "
                        f"number — {shape} moves the reading by MORE than the "
                        f"bound, so a non-positive or non-numeric one names no "
                        f"crossing")

        for key in sorted(bounds):
            if oracle.get(key) not in _BOUNDED_SHAPES:
                out.append(
                    f"{tid}: bounds[{key!r}] is declared but oracle {key!r} "
                    f"is not one of {sorted(_BOUNDED_SHAPES)} (or not declared "
                    f"at all) — dead bound data nothing will ever read")

        rk = read_keys.get(tid)
        known = {k for _kind, k in (rk or {}).get("keys", [])}
        for key in sorted(oracle):
            base = key.split(".", 1)[0]
            if base not in known:
                hint = (" (id is APPROX in read_keys.py — the static walk may "
                         "simply not have resolved this read yet; re-check "
                         "the body, or record a transcript)"
                         if rk and rk.get("status") == "APPROX" else "")
                out.append(
                    f"{tid}: oracle key {key!r} is not in the generated read "
                    f"set for this id{hint} — the record names a read the "
                    f"body does not make (M-HARNESS2 §2)")

        if falsifier and falsifier != "replay":
            m = _PHYSICAL_RE.match(falsifier)
            if not m:
                out.append(
                    f"{tid}: falsifier {falsifier!r} is neither 'replay' nor "
                    f"'physical: <what>; expires YYYY-MM-DD' (M-HARNESS2 §7)")
            else:
                expires = datetime.date.fromisoformat(m.group(1))
                if today > expires:
                    days = (today - expires).days
                    out.append(
                        f"{tid}: physical falsifier expired {expires} — passed "
                        f"{days} day(s) ago. Rule mirrored from flaky.yaml's "
                        f"review_by (F8): an entry past its review date is a "
                        f"FAIL until re-justified, not a silent pass "
                        f"(M-HARNESS2 §3 / PM §4.1)")
    return out


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
    # TASK-565: the HEALTH family is a SECOND registry (design §4.5) — kept out
    # of build_all_tests() so its ids cannot enter default_tests and run twice,
    # kept IN build_all_meta() so mode P's health_verdict() can see the class it
    # reports on. The record set is therefore the UNION, and this gate is what
    # stops a health id from silently existing in neither.
    health = _suite.build_health_tests()
    runnable = set(tests) | set(health)

    if set(records) != runnable:
        findings.append("build_all_meta() and build_all_tests()+build_health_tests() "
                        f"disagree on the id set: "
                        f"only-meta={sorted(set(records) - runnable)} "
                        f"only-tests={sorted(runnable - set(records))}")
    if set(tests) & set(health):
        findings.append(f"health ids leaked into build_all_tests(): "
                        f"{sorted(set(tests) & set(health))} — they would enter "
                        f"default_tests and run twice, the mutating one included "
                        f"(M-TESTARCH §4.5)")
    # Every health id IS the HEALTH class, and only they are. A HEALTH id that
    # is not in HEALTH_TESTS is unreachable by the gate phase; a HEALTH_TESTS
    # entry that did not declare cls would seed to CORE and stop being a health
    # check with nothing printed.
    declared_health = {t for t, r in records.items() if r["cls"] == "HEALTH"}
    if declared_health != set(health):
        findings.append(f"cls=HEALTH and HEALTH_TESTS disagree: "
                        f"cls-only={sorted(declared_health - set(health))} "
                        f"registry-only={sorted(set(health) - declared_health)}")

    findings += evaluate(records)

    # R35 (TASK-591) — every gating class declared, with a written reason.
    ledger, ledger_errors = parse_ledger()
    findings += evaluate_gating_classes(records, ledger) + ledger_errors

    # TASK-641 — the falsifier record (oracle/premise/falsifier, §7).
    findings += evaluate_falsifiers(records)

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
    gating_ids = [t for t, r in records.items() if r["cls"] in GATING]
    reasoned = [t for t in gating_ids
                if records[t].get("cls_declared") and (records[t].get("cls_reason") or "").strip()]
    print(f"  gating ({'/'.join(GATING)}): {len(gating_ids)} ids, "
          f"{len(reasoned)} declared with a written reason, "
          f"{len(ledger)} on the R35 ledger ({LEDGER_REL})")
    oracle_ids = [t for t, r in records.items() if r.get("oracle")]
    falsifier_ids = [t for t, r in records.items() if r.get("falsifier")]
    print(f"  falsifier record (TASK-641): {len(oracle_ids)} id(s) declare an "
          f"oracle, {len(falsifier_ids)} declare a falsifier")
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
