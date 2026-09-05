#!/usr/bin/env python3
"""test_check_plan_integrity.py — the negative suite for TASK-611 / R46.

BP-068: a gate without a negative test is not a gate. Every arm builds a small
tree on disk — a plan document and a registry module — and asserts the finding
KIND, never merely that findings exist. Four of the five checks read ZERO on the
live corpus, and a check reading zero is exactly the one whose negative test is
load-bearing: nothing else can distinguish "no violations" from "cannot see one".

  A. each check fires on the shape it names, and its control does not.
  B. the ledger, both directions — an unledgered finding fails, a ledgered one
     passes, and a row whose finding is gone fails as STALE.
  C. the live tree, so the numbers in the ledger document are the gate's own.

No DUT, no serial port, no network.

    python3 app/tools/gate/test_check_plan_integrity.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_plan_integrity as C                                    # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


def kinds(found):
    return sorted({k for k, _t, _m in found})


class Tree:
    """A throwaway repo root: docs/verification/ + app/tools/suite/."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="planint_")
        os.makedirs(os.path.join(self.root, "docs", "verification"))
        os.makedirs(os.path.join(self.root, "app", "tools", "suite"))

    def plan(self, text, name="test_plan.md"):
        with open(os.path.join(self.root, "docs", "verification", name), "w") as fh:
            fh.write(text)
        return self

    def doc(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)
        return self

    def suite(self, text, name="fam.py"):
        with open(os.path.join(self.root, "app", "tools", "suite", name), "w") as fh:
            fh.write(text)
        return self

    def findings(self):
        C._BLOCK_CACHE.clear()
        return C.findings(self.root)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        shutil.rmtree(self.root, ignore_errors=True)


BODY_ONE = '''
def t001(dut):
    print("T001  taskbar tap cycles the mode")

TESTS = {"T001": t001}
'''

BODY_TWO_MODULES_A = '''
def t001(dut):
    print("T001  taskbar tap cycles the mode")

TESTS = {"T001": t001}
'''

BODY_TWO_MODULES_B = '''
def t001_other(dut):
    print("T001  something else entirely")

TESTS = {"T001": t001_other}
'''


def test_checks():
    print("A. the five checks")

    # P1 — two bodies.
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode\n")
        t.suite(BODY_TWO_MODULES_A, "a.py")
        t.suite(BODY_TWO_MODULES_B, "b.py")
        check("A1: two executable bodies -> two-bodies",
              kinds(t.findings()) == ["two-bodies"], t.findings())
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode\n")
        t.suite(BODY_ONE, "a.py")
        check("A1c: control — one body, one entry, no finding",
              t.findings() == [], t.findings())

    # P2 — two declarations.
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode\n\n"
               "### T001 fix — taskbar tap cycles the mode\n")
        t.suite(BODY_ONE)
        check("A2: two live plan entries -> two-declarations",
              "two-declarations" in kinds(t.findings()), t.findings())
    with Tree() as t:
        # the fix applied to the live corpus: the work item no longer LEADS with
        # the id, so it is not a second declaration.
        t.plan("### T001 — taskbar tap cycles the mode\n\n"
               "### Fix for T001 — taskbar tap cycles the mode\n")
        t.suite(BODY_ONE)
        check("A2b: the retitled work item is not a declaration",
              t.findings() == [], t.findings())
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode\n")
        t.doc("docs/verification/test_plan-archive.md",
              "### T001 — an older shape of the same test\n")
        t.suite(BODY_ONE)
        check("A2c: an ARCHIVE entry is not a second declaration",
              t.findings() == [], t.findings())

    # P3 — collision.
    with Tree() as t:
        t.plan("### T001 — [app-settings-wire-001] Crypto currency change\n")
        t.suite(BODY_ONE)
        check("A3: no shared content word -> collision",
              kinds(t.findings()) == ["collision"], t.findings())
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles between the modes\n")
        t.suite(BODY_ONE)
        check("A3c: control — a paraphrase is not a collision",
              t.findings() == [], t.findings())
    with Tree() as t:
        # A FAMILY heading names a range, not this id: neither a declaration of
        # it nor a description of its body. Three live ids hit this shape.
        t.plan("### `T001`–`26` — implemented family (bodies in the runner)\n")
        t.suite(BODY_ONE)
        check("A3f: a family RANGE heading is not a collision",
              t.findings() == [], t.findings())

    # P5 — manual-but-executable.
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode [MANUAL]\n")
        t.suite(BODY_ONE)
        check("A5: [MANUAL] plus a registered body -> manual-but-executable",
              kinds(t.findings()) == ["manual-but-executable"], t.findings())
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode [Blocked: G2]\n")
        t.suite(BODY_ONE)
        check("A5b: [Blocked: …] counts too",
              kinds(t.findings()) == ["manual-but-executable"], t.findings())

    # P4 — stale retirement.
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode\n")
        t.doc(C.RETIRED_REL, "| id | Status |\n|---|---|\n| `T001` | retired |\n")
        check("A4: a retired id whose plan entry says nothing -> stale-retirement",
              kinds(t.findings()) == ["stale-retirement"], t.findings())
    with Tree() as t:
        t.plan("### T001 — taskbar tap cycles the mode\n\n"
               "**Retired 2026-09-05 (TASK-603)** — see retired_test_ids.md\n")
        t.doc(C.RETIRED_REL, "| id | Status |\n|---|---|\n| `T001` | retired |\n")
        check("A4c: control — an entry that says so is not stale",
              t.findings() == [], t.findings())


def test_ledger():
    print("B. the ledger")
    found = [("collision", "T237", "…"), ("manual-but-executable", "T231", "…")]
    fails, used = C.evaluate(found, {})
    check("B1: an unledgered finding fails", len(fails) == 2 and used == 0, fails)
    led = {("collision", "T237"): "l:1", ("manual-but-executable", "T231"): "l:2"}
    fails, used = C.evaluate(found, led)
    check("B2: a ledgered finding passes", fails == [] and used == 2, fails)
    fails, _u = C.evaluate([], led)
    check("B3: a row whose finding is gone fails as STALE",
          len(fails) == 2 and all(f.startswith("STALE") for f in fails), fails)
    # The ledger is keyed on (kind, id): the same id under another kind is not
    # covered. Without this a single row would amnesty every check for an id.
    fails, _u = C.evaluate([("two-bodies", "T237", "…")],
                           {("collision", "T237"): "l:1"})
    check("B4: a row does not cover the same id under another kind",
          len(fails) == 2, fails)

    ledger, errs = C.parse_ledger()
    check("B5: the shipped ledger parses with no malformed rows", errs == [], errs)
    check("B6: every shipped row has a valid kind",
          all(k in C.KINDS for k, _t in ledger), sorted(ledger))


def test_live():
    print("C. the live tree")
    found = C.findings()
    by: dict = {}
    for k, _t, _m in found:
        by[k] = by.get(k, 0) + 1
    check("C1: A-15 is HISTORICAL — no id has two bodies today",
          by.get("two-bodies", 0) == 0, by)
    check("C2: no id has two live plan declarations",
          by.get("two-declarations", 0) == 0, by)
    check("C3: no retired id's plan entry still reads as coverage",
          by.get("stale-retirement", 0) == 0, by)
    check("C4: the four F-2/G-11 collisions are all reported",
          {t for k, t, _m in found} >= {"T237", "T276", "T231", "T242"},
          sorted(t for _k, t, _m in found))
    ledger, _e = C.parse_ledger()
    fails, _u = C.evaluate(found, ledger)
    check("C5: the live tree is clean against its ledger", fails == [], fails)


def main():
    test_checks()
    test_ledger()
    test_live()
    print()
    if FAILURES:
        print(f"FAIL: test_check_plan_integrity.py — {len(FAILURES)} arm(s) failed: "
              + ", ".join(FAILURES))
        return 1
    print("OK: test_check_plan_integrity.py — all arms passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
