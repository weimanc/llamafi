#!/usr/bin/env python3
"""test_check_timeout_literals.py — negative suite for check_timeout_literals.py
(BP-068: a gate without a negative test is not a gate). TASK-607 / M-HARNESS2 R24.

Pins:

  * a module over its ledgered cap FAILS (T1);
  * a ledger row above the real count (stale, i.e. headroom) FAILS (T2);
  * a ledger row exactly AT the real count PASSES;
  * a ledger row naming a module that does not exist FAILS (T3);
  * a row missing a TASK id, or an owner that isn't `TASK-NNN`, or a bad/missing
    ISO date, or a wildcard module name, each FAIL (T4);
  * the scan regex only matches `timeout=` at a bare-numeric-literal position:
    `timeout=TIMEOUT`, `timeout=TIMEOUT_SLOW`, `timeout=some_var`,
    `timeout=_FETCH_TIMEOUT` all count as ZERO — those are already policy
    users or named constants, which is the entire point of the gate;
  * a `timeout=` outside `app/tools/suite/` (e.g. in `app/tools/lib/`) is out
    of scope and must not be counted.

No DUT, no serial port, no filesystem writes outside a temp dir.

    python3 app/tools/gate/test_check_timeout_literals.py
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_timeout_literals as C                                  # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


def codes(findings):
    return sorted({f.split()[0] for f in findings})


# ── the scan regex: what counts, what does not ───────────────────────────────

def test_scan_regex_only_matches_bare_numeric_literals():
    src = (
        "dut.cmd('a', timeout=3.0)\n"
        "dut.cmd('b', timeout=TIMEOUT)\n"
        "dut.cmd('c', timeout=TIMEOUT_SLOW)\n"
        "dut.cmd('d', timeout=some_var)\n"
        "dut.cmd('e', timeout=_FETCH_TIMEOUT)\n"
        "dut.cmd('f', timeout=15)\n"
        "dut.cmd('g', timeout=2.5)\n"
    )
    hits = C.TIMEOUT_LITERAL_RE.findall(src)
    check("bare-literal-only: exactly the 3 numeric call sites counted",
          sorted(hits) == sorted(["timeout=3.0", "timeout=15", "timeout=2.5"]),
          hits)


def _write_suite_tree(root, modules):
    """modules: {relpath-under-suite: content}. Returns the app/tools root."""
    suite = os.path.join(root, "suite")
    lib = os.path.join(root, "lib")
    os.makedirs(suite, exist_ok=True)
    os.makedirs(lib, exist_ok=True)
    for rel, content in modules.items():
        p = os.path.join(suite, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
    return root


def test_lib_out_of_scope():
    with tempfile.TemporaryDirectory() as d:
        _write_suite_tree(d, {"a.py": "x(timeout=3.0)\n"})
        with open(os.path.join(d, "lib", "dut.py"), "w", encoding="utf-8") as fh:
            fh.write("x(timeout=3.0)\nx(timeout=5.0)\n")
        counts, _detail = C.scan(root=d)
        check("lib/ is out of scope (scan walks suite/ only)",
              "lib/dut.py" not in counts and set(counts) == {"suite/a.py"},
              counts)
        check("suite/ file counted correctly", counts.get("suite/a.py") == 1, counts)


# ── the ledger evaluator: T1-T4 ──────────────────────────────────────────────

def _ledger_row(mod, cap, owner="TASK-607", since="2026-09-20"):
    return f"| `{mod}` | {cap} | {owner} | {since} |\n"


def _write_ledger(rows_md):
    header = "| module | cap | owner | since |\n|---|---|---|---|\n"
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("# ratchet\n\n" + header + rows_md)
    return path


def test_t1_over_cap_fails():
    ledger_path = _write_ledger(_ledger_row("suite/a.py", 1))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"suite/a.py": 2}, ledger)
        check("T1: module over its cap fails", "T1" in codes(findings), findings)
    finally:
        os.remove(ledger_path)


def test_t2_stale_row_fails():
    ledger_path = _write_ledger(_ledger_row("suite/a.py", 5))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"suite/a.py": 2}, ledger)
        check("T2: cap above real count (stale) fails", "T2" in codes(findings),
              findings)
    finally:
        os.remove(ledger_path)


def test_cap_exactly_at_real_count_passes():
    ledger_path = _write_ledger(_ledger_row("suite/a.py", 2))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"suite/a.py": 2}, ledger)
        check("cap == real count: no findings", findings == [], findings)
    finally:
        os.remove(ledger_path)


def test_t3_unknown_module_fails():
    ledger_path = _write_ledger(_ledger_row("suite/does_not_exist.py", 3))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"suite/a.py": 0}, ledger)
        check("T3: ledger row for nonexistent module fails",
              "T3" in codes(findings), findings)
    finally:
        os.remove(ledger_path)


def test_t4_missing_task_owner_fails():
    ledger_path = _write_ledger(_ledger_row("suite/a.py", 2, owner="bob"))
    try:
        _ledger, errs = C.parse_ledger(path=ledger_path)
        check("T4: non-TASK owner fails", "T4" in codes(errs), errs)
    finally:
        os.remove(ledger_path)


def test_t4_bad_date_fails():
    ledger_path = _write_ledger(_ledger_row("suite/a.py", 2, since="not-a-date"))
    try:
        _ledger, errs = C.parse_ledger(path=ledger_path)
        check("T4: malformed date fails", "T4" in codes(errs), errs)
    finally:
        os.remove(ledger_path)


def test_t4_wildcard_module_fails():
    ledger_path = _write_ledger(_ledger_row("suite/*.py", 2))
    try:
        _ledger, errs = C.parse_ledger(path=ledger_path)
        check("T4: wildcard module name fails", "T4" in codes(errs), errs)
    finally:
        os.remove(ledger_path)


def test_absent_ledger_fails_closed():
    ledger, errs = C.parse_ledger(path="/nonexistent/path/ratchet.md")
    findings = errs + C.evaluate({"suite/a.py": 1}, ledger)
    check("absent ledger fails closed (every nonzero module over cap 0)",
          "T1" in codes(findings), findings)


def test_live_ledger_is_clean():
    """The real ledger against the real live tree, end to end — the same call
    `main()` makes. Not a fixture: this is the actual gate the repo carries."""
    counts, _detail = C.scan()
    ledger, lerrs = C.parse_ledger()
    findings = lerrs + C.evaluate(counts, ledger)
    check("live ledger: check_timeout_literals.py is clean today",
          findings == [], findings)


TESTS = [
    test_scan_regex_only_matches_bare_numeric_literals,
    test_lib_out_of_scope,
    test_t1_over_cap_fails,
    test_t2_stale_row_fails,
    test_cap_exactly_at_real_count_passes,
    test_t3_unknown_module_fails,
    test_t4_missing_task_owner_fails,
    test_t4_bad_date_fails,
    test_t4_wildcard_module_fails,
    test_absent_ledger_fails_closed,
    test_live_ledger_is_clean,
]


def main() -> int:
    for t in TESTS:
        t()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)}/{len(TESTS)} checks failed")
        return 1
    print(f"OK: {len(TESTS)}/{len(TESTS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
