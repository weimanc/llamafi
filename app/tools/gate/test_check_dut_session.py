#!/usr/bin/env python3
"""test_check_dut_session.py — negative suite for check_dut_session.py
(BP-068: a gate without a negative test is not a gate). TASK-599 / M-HARNESS2 R47.

Pins:

  * a module over its ledgered cap FAILS (T1);
  * a ledger row above the real count (stale, i.e. headroom) FAILS (T2);
  * a ledger row exactly AT the real count PASSES;
  * a ledger row naming a module that does not exist FAILS (T3);
  * a row missing a TASK id, or an owner that isn't `TASK-NNN`, or a bad/missing
    ISO date, or a wildcard module name, each FAIL (T4);
  * a ledger row naming a file under `lib/` FAILS (T5) — that is the one
    structurally exempt location and must never carry a row;
  * the scan is AST-based, not textual: a file whose DOCSTRING, COMMENT, or a
    regex/string LITERAL merely mentions `serial.Serial(` counts as ZERO real
    constructions — only an actual `ast.Call` node shaped `serial.Serial(...)`
    counts. This is the fix for the defect the gate shipped with (see its
    module docstring): a textual scan of a file whose whole job is describing
    the pattern necessarily also matches its own description of the pattern;
  * THE SELF-REFERENCE CASE, PINNED EXPLICITLY: `check_dut_session.py` itself
    (which discusses `serial.Serial(` at length in its own docstring) is not a
    finding — scanning the gate's own source file finds zero real
    `serial.Serial(...)` calls;
  * a `serial.Serial(` construction under `app/tools/lib/` is out of scope and
    must not be counted.

No DUT, no serial port, no filesystem writes outside a temp dir.

    python3 app/tools/gate/test_check_dut_session.py
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import check_dut_session as C                                       # noqa: E402

FAILURES: list = []


def check(name, cond, detail=""):
    if cond is True:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail or cond}")
        FAILURES.append(name)


def codes(findings):
    return sorted({f.split()[0] for f in findings})


def _write_tree(root, files):
    """files: {relpath-under-app/tools: content}. Returns the app/tools root."""
    for rel, content in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
    return root


# ── the AST scan: what counts, what does not ─────────────────────────────────

def test_real_call_counts():
    with tempfile.TemporaryDirectory() as d:
        _write_tree(d, {"a.py": (
            "import serial\n"
            "def open_it(port):\n"
            "    return serial.Serial(port, 115200)\n"
        )})
        counts, _detail = C.scan(root=d)
        check("a real serial.Serial(...) call counts as 1",
              counts.get("a.py") == 1, counts)


def test_docstring_mention_does_not_count():
    with tempfile.TemporaryDirectory() as d:
        _write_tree(d, {"a.py": (
            '"""This module talks about serial.Serial( a lot, in prose,\n'
            'because it is a gate that polices the pattern textually in\n'
            'someone\'s old design. serial.Serial( again for good measure."""\n'
            "x = 1\n"
        )})
        counts, _detail = C.scan(root=d)
        check("a docstring mention of serial.Serial( counts as 0",
              counts.get("a.py", 0) == 0, counts)


def test_comment_mention_does_not_count():
    with tempfile.TemporaryDirectory() as d:
        _write_tree(d, {"a.py": (
            "# TODO: stop calling serial.Serial( here eventually\n"
            "x = 1\n"
        )})
        counts, _detail = C.scan(root=d)
        check("a comment mention of serial.Serial( counts as 0",
              counts.get("a.py", 0) == 0, counts)


def test_regex_literal_does_not_count():
    with tempfile.TemporaryDirectory() as d:
        _write_tree(d, {"a.py": (
            "import re\n"
            'PATTERN = re.compile(r"serial\\.Serial\\(")\n'
        )})
        counts, _detail = C.scan(root=d)
        check("a regex literal spelling serial.Serial( counts as 0",
              counts.get("a.py", 0) == 0, counts)


def test_stubbed_string_fixture_does_not_count():
    """Mirrors test_check_import_safety.py's shape: it writes the literal text
    `serial.Serial(...)` into a STRING that gets fed to another process/probe
    as source text for a *different* file — never a Call node in this file."""
    with tempfile.TemporaryDirectory() as d:
        _write_tree(d, {"a.py": (
            "def probe():\n"
            "    src = \"import serial\\nserial.Serial('/dev/ttyUSB0', 115200)\\n\"\n"
            "    return src\n"
        )})
        counts, _detail = C.scan(root=d)
        check("a string literal containing serial.Serial( text counts as 0",
              counts.get("a.py", 0) == 0, counts)


def test_self_reference_case_pinned():
    """THE case this gate shipped broken on: scanning the gate's own source
    file must find zero real constructions, with no allowlist involved."""
    counts, _detail = C.scan()
    self_rel = "gate/check_dut_session.py"
    check(f"{self_rel} scans to 0 real serial.Serial( calls (self-reference)",
          counts.get(self_rel, 0) == 0, counts.get(self_rel))


def test_import_safety_files_clear_with_no_allowlist():
    """check_import_safety.py and its test both mention the pattern (as
    docstring/comment prose and as a string fed into a probed file) but never
    construct a real session — they must clear at 0 without being named in
    any exception list (there is none any more; this is the point of AST)."""
    counts, _detail = C.scan()
    for rel in ("gate/check_import_safety.py", "gate/test_check_import_safety.py"):
        check(f"{rel} scans to 0 with no allowlist entry",
              counts.get(rel, 0) == 0, counts.get(rel))
    check("ALLOWLIST no longer exists on the module",
          not hasattr(C, "ALLOWLIST"))


def test_lib_out_of_scope():
    with tempfile.TemporaryDirectory() as d:
        _write_tree(d, {
            "a.py": "import serial\nserial.Serial('x')\n",
            "lib/dut.py": "import serial\nserial.Serial('x')\nserial.Serial('y')\n",
        })
        counts, _detail = C.scan(root=d)
        check("lib/ is out of scope (scan excludes it)",
              "lib/dut.py" not in counts and set(counts) == {"a.py"},
              counts)


# ── the ledger evaluator: T1-T5 ───────────────────────────────────────────────

def _ledger_row(mod, cap, owner="TASK-599", since="2026-09-20"):
    return f"| `{mod}` | {cap} | {owner} | {since} |\n"


def _write_ledger(rows_md):
    header = "| module | cap | owner | since |\n|---|---|---|---|\n"
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("# ratchet\n\n" + header + rows_md)
    return path


def test_t1_over_cap_fails():
    ledger_path = _write_ledger(_ledger_row("a.py", 1))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"a.py": 2}, ledger)
        check("T1: module over its cap fails", "T1" in codes(findings), findings)
    finally:
        os.remove(ledger_path)


def test_t2_stale_row_fails():
    ledger_path = _write_ledger(_ledger_row("a.py", 5))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"a.py": 2}, ledger)
        check("T2: cap above real count (stale) fails", "T2" in codes(findings),
              findings)
    finally:
        os.remove(ledger_path)


def test_cap_exactly_at_real_count_passes():
    ledger_path = _write_ledger(_ledger_row("a.py", 2))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"a.py": 2}, ledger)
        check("cap == real count: no findings", findings == [], findings)
    finally:
        os.remove(ledger_path)


def test_t3_unknown_module_fails():
    ledger_path = _write_ledger(_ledger_row("does_not_exist.py", 3))
    try:
        ledger, errs = C.parse_ledger(path=ledger_path)
        findings = errs + C.evaluate({"a.py": 0}, ledger)
        check("T3: ledger row for nonexistent module fails",
              "T3" in codes(findings), findings)
    finally:
        os.remove(ledger_path)


def test_t4_missing_task_owner_fails():
    ledger_path = _write_ledger(_ledger_row("a.py", 2, owner="bob"))
    try:
        _ledger, errs = C.parse_ledger(path=ledger_path)
        check("T4: non-TASK owner fails", "T4" in codes(errs), errs)
    finally:
        os.remove(ledger_path)


def test_t4_bad_date_fails():
    ledger_path = _write_ledger(_ledger_row("a.py", 2, since="not-a-date"))
    try:
        _ledger, errs = C.parse_ledger(path=ledger_path)
        check("T4: malformed date fails", "T4" in codes(errs), errs)
    finally:
        os.remove(ledger_path)


def test_t4_wildcard_module_fails():
    ledger_path = _write_ledger(_ledger_row("spike/*.py", 2))
    try:
        _ledger, errs = C.parse_ledger(path=ledger_path)
        check("T4: wildcard module name fails", "T4" in codes(errs), errs)
    finally:
        os.remove(ledger_path)


def test_t5_lib_row_fails():
    ledger_path = _write_ledger(_ledger_row("lib/dut.py", 1))
    try:
        _ledger, errs = C.parse_ledger(path=ledger_path)
        check("T5: a ledger row naming a lib/ file fails",
              "T5" in codes(errs), errs)
    finally:
        os.remove(ledger_path)


def test_absent_ledger_fails_closed():
    ledger, errs = C.parse_ledger(path="/nonexistent/path/ratchet.md")
    findings = errs + C.evaluate({"a.py": 1}, ledger)
    check("absent ledger fails closed (every nonzero module over cap 0)",
          "T1" in codes(findings), findings)


def test_live_ledger_is_clean():
    """The real ledger against the real live tree, end to end — the same call
    `main()` makes. Not a fixture: this is the actual gate the repo carries."""
    counts, _detail = C.scan()
    ledger, lerrs = C.parse_ledger()
    findings = lerrs + C.evaluate(counts, ledger)
    check("live ledger: check_dut_session.py is clean today",
          findings == [], findings)


TESTS = [
    test_real_call_counts,
    test_docstring_mention_does_not_count,
    test_comment_mention_does_not_count,
    test_regex_literal_does_not_count,
    test_stubbed_string_fixture_does_not_count,
    test_self_reference_case_pinned,
    test_import_safety_files_clear_with_no_allowlist,
    test_lib_out_of_scope,
    test_t1_over_cap_fails,
    test_t2_stale_row_fails,
    test_cap_exactly_at_real_count_passes,
    test_t3_unknown_module_fails,
    test_t4_missing_task_owner_fails,
    test_t4_bad_date_fails,
    test_t4_wildcard_module_fails,
    test_t5_lib_row_fails,
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
