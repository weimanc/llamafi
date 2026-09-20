#!/usr/bin/env python3
"""test_check_wait_expiry.py — negative suite for check_wait_expiry.py (BP-068:
a gate without a negative test is not a gate). TASK-607 / M-HARNESS2 R22.

Pins:

  * a bounded while loop whose fall-through falls straight into a bare
    `pass_(...)` call is FLAGGED (T1) — this is the exact defect R22 names;
  * the same loop, with an `if` deciding on the loop's outcome BEFORE the
    `pass_()` call, is NOT flagged — a decision point breaks the chain;
  * the same loop, with an explicit `return`/`fail(`/`skip(`/`unmet(` between
    the loop and the `pass_()` call, is NOT flagged for the same reason;
  * a loop that is not "bounded" in the idiom this gate recognises (no
    `time.monotonic`/`deadline`/`elapsed` in its test) is not scanned at all,
    even if it does fall through into `pass_()` — documented scope, not a
    false negative worth widening for (see the module docstring's "WHAT IT
    DOES NOT SEE");
  * a bounded loop nested inside an `if`/`try` arm is still scanned (the
    walk recurses into every block, not just function-top-level statements);
  * a syntactically invalid file is reported as a finding, not a silent skip.

No DUT, no serial port, no filesystem writes outside a temp dir.

    python3 app/tools/gate/test_check_wait_expiry.py
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_wait_expiry as C                                       # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


def codes(findings):
    return sorted({f.split()[0] for f in findings})


def _scan_src(src: str):
    """Write `src` as the sole module under a throwaway suite/ tree and scan it."""
    with tempfile.TemporaryDirectory() as tmp:
        suite_dir = os.path.join(tmp, "suite")
        os.makedirs(suite_dir)
        with open(os.path.join(suite_dir, "fixture.py"), "w") as fh:
            fh.write(src)
        return C.scan(root=tmp)


_UNCONDITIONAL_PASS = '''
import time

def bad_wait_test(dut, tid):
    ok = False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if check(dut):
            ok = True
            break
        time.sleep(1.0)
    pass_(tid, "reached ok state")
'''

_DECIDED_WITH_IF = '''
import time

def good_wait_test(dut, tid):
    ok = False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if check(dut):
            ok = True
            break
        time.sleep(1.0)
    if not ok:
        fail(tid, "condition never observed")
        return
    pass_(tid, "reached ok state")
'''

_DECIDED_WITH_RETURN = '''
import time

def good_wait_helper(dut, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if check(dut):
            return True
        time.sleep(1.0)
    return False

def good_wait_test(dut, tid):
    if not good_wait_helper(dut):
        fail(tid, "condition never observed")
        return
    pass_(tid, "reached ok state")
'''

_UNBOUNDED_LOOP_TO_PASS = '''
def not_scanned(dut, tid):
    n = 0
    while n < 3:
        n += 1
    pass_(tid, "not our idiom — no time.monotonic/deadline/elapsed")
'''

_NESTED_IN_IF = '''
import time

def bad_nested(dut, tid, use_fast_path):
    if use_fast_path:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            time.sleep(0.1)
        pass_(tid, "fast path done")
    else:
        fail(tid, "slow path unimplemented")
'''

_SYNTAX_ERROR = "def broken(:\n    pass\n"


def main() -> int:
    print("== check_wait_expiry.py negative suite ==")

    counts, findings = _scan_src(_UNCONDITIONAL_PASS)
    check("A1 unconditional pass_() after bounded loop is flagged",
          codes(findings) == ["T1"], findings)
    check("A1 exactly one finding", len(findings) == 1, findings)

    counts, findings = _scan_src(_DECIDED_WITH_IF)
    check("A2 an `if` deciding the outcome before pass_() is NOT flagged",
          findings == [], findings)

    counts, findings = _scan_src(_DECIDED_WITH_RETURN)
    check("A3 helper-returns-bool / caller-decides convention is NOT flagged "
          "(the corpus's actual idiom)", findings == [], findings)

    counts, findings = _scan_src(_UNBOUNDED_LOOP_TO_PASS)
    check("A4 a loop outside the bounded idiom (no time.monotonic/deadline/"
          "elapsed) is not scanned even though it falls into pass_()",
          findings == [], findings)

    counts, findings = _scan_src(_NESTED_IN_IF)
    check("A5 a bounded loop nested inside an `if` arm is still scanned",
          codes(findings) == ["T1"], findings)

    counts, findings = _scan_src(_SYNTAX_ERROR)
    check("A6 a syntactically invalid file is reported, not silently skipped",
          len(findings) == 1 and "SyntaxError" in findings[0], findings)

    # A7 — the live corpus itself reads zero, per the module's own docstring
    # claim (measured 2026-09-20 after the R22 poll_until migration: 59
    # bounded loops, 0 findings — 64 before six wait helpers moved onto
    # `poll_until`, five of them in suite/). Pinned here so a regression in
    # either the gate or the corpus is caught by the negative suite too, not
    # just by running the gate directly.
    real_counts, real_findings = C.scan()
    total_loops = 0
    import ast as _ast
    for mod in real_counts:
        path = os.path.join(TOOLS, mod)
        with open(path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        tree = _ast.parse(src, filename=path)
        total_loops += sum(
            1 for node in _ast.walk(tree)
            if isinstance(node, _ast.While) and C._is_bounded_while(node, src))
    check("A7 live corpus: 59 bounded loops (docstring's measured count, "
          "post-poll_until-migration)", total_loops == 59, total_loops)
    check("A7 live corpus: 0 findings (blocking-at-zero posture holds)",
          real_findings == [], real_findings)

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("OK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
