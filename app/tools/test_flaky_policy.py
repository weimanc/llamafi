#!/usr/bin/env python3
"""test_flaky_policy.py — T_FLK_01..22, negative tests for the flaky-set gate.

BP-068: a gate ships with tests that break it the way it is meant to catch.
Every schema rule in lib/flaky.py and every branch of the policy in
lib/results.py is exercised here by feeding it a file or a call sequence that
SHOULD be rejected, and asserting it actually is. Host-side only, no DUT, <1 s.

Run directly, or via app/tools/smoke_test.sh step 5.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import flaky as F          # noqa: E402
from lib import results as R        # noqa: E402

RESULTS: dict[str, str] = {}


def _p(tid, detail=""):
    RESULTS[tid] = "PASS"
    print(f"  [PASS] {tid}" + (f"  {detail}" if detail else ""))


def _f(tid, reason):
    RESULTS[tid] = f"FAIL: {reason}"
    print(f"  [FAIL] {tid}  {reason}")


_TMP = pathlib.Path(tempfile.mkdtemp(prefix="flakypolicy_"))
_N = [0]


def _write(text: str) -> pathlib.Path:
    _N[0] += 1
    p = _TMP / f"flaky_{_N[0]}.yaml"
    p.write_text(text, encoding="utf-8")
    return p


GOOD_ENTRY = """
flaky:
  - id: T_DEMO
    suite: run_serialdbg_tests
    since: 2026-08-01
    evidence: "1 fail in 3 runs"
    symptom: "no dequeued action"
    dependency: "[NETWORK]"
    owner: "@VE"
    task: TASK-520
    review_by: 2099-01-01
"""

# Schema-valid in every respect EXCEPT that its review date has passed: since
# must move too, or the entry trips the `review_by precedes since` rule instead
# and T_FLK_14/16 would pass for the wrong reason.
EXPIRED_ENTRY = (GOOD_ENTRY.replace("review_by: 2099-01-01", "review_by: 2000-01-01")
                           .replace("since: 2026-08-01", "since: 1999-01-01"))


def _use(path):
    """Point the loader at `path` and drop all cached/recorded state."""
    import os
    if path is None:
        os.environ.pop(F.ENV_OVERRIDE, None)
    else:
        os.environ[F.ENV_OVERRIDE] = str(path)
    F.reset_cache()
    R.reset()


def _expect_error(tid: str, yaml_text: str, needle: str, *, path=None):
    """Load a deliberately broken file and require a FlakyError mentioning `needle`."""
    p = path if path is not None else _write(yaml_text)
    try:
        F.load(p)
    except F.FlakyError as e:
        if needle.lower() in str(e).lower():
            _p(tid, f"rejected: {e}")
        else:
            _f(tid, f"rejected but wrong message: {e}  (wanted {needle!r})")
        return
    except Exception as e:
        _f(tid, f"wrong exception type {type(e).__name__}: {e}")
        return
    _f(tid, f"ACCEPTED a file that must be rejected ({needle})")


# ── schema negatives ─────────────────────────────────────────────────────────

def t_flk_01():
    """The shipped file parses and both declared ids are DECLARED today."""
    _use(None)
    try:
        reg = F.load()
    except F.FlakyError as e:
        _f("T_FLK_01", f"the real docs/verification/flaky.yaml does not load: {e}")
        return
    if not reg.entries:
        _f("T_FLK_01", "real file parsed but declares nothing")
        return
    bad = [t for t in reg.entries if reg.status(t)[0] != F.DECLARED]
    if bad:
        _f("T_FLK_01", f"declared ids not usable today (expired?): {bad}")
        return
    _p("T_FLK_01", f"{sorted(reg.entries)} declared, {sorted(reg.candidates)} candidates")


def t_flk_02():
    _expect_error("T_FLK_02", GOOD_ENTRY.replace('    owner: "@VE"\n', ""),
                  "missing/empty required field")


def t_flk_03():
    _expect_error("T_FLK_03", GOOD_ENTRY.replace("    review_by: 2099-01-01\n", ""),
                  "missing/empty required field")


def t_flk_04():
    _expect_error("T_FLK_04", GOOD_ENTRY.replace("task: TASK-520", "task: someday"),
                  "TASK-123")


def t_flk_05():
    _expect_error("T_FLK_05", GOOD_ENTRY + GOOD_ENTRY.split("flaky:")[1], "duplicate")


def t_flk_06():
    _expect_error("T_FLK_06", GOOD_ENTRY + """
candidates:
  - id: T_DEMO
    note: "also a candidate"
""", "both declared and a candidate")


def t_flk_07():
    _expect_error("T_FLK_07", "flaky:\n  - id: T_X\n   bad: [indent\n", "parse error")


def t_flk_08():
    _expect_error("T_FLK_08", "", "not found", path=_TMP / "definitely_absent.yaml")


def t_flk_09():
    _expect_error("T_FLK_09", GOOD_ENTRY + "\nflakey:\n  - id: typo\n",
                  "unknown top-level key")


def t_flk_10():
    _expect_error("T_FLK_10", GOOD_ENTRY.replace("review_by: 2099-01-01",
                                                 "review_by: 2026-07-01"),
                  "precedes since")


def t_flk_11():
    _expect_error("T_FLK_11", GOOD_ENTRY + "\ncandidates:\n  - id: T_OTHER\n",
                  "note` is required")


def t_flk_12():
    _expect_error("T_FLK_12", GOOD_ENTRY.replace("review_by: 2099-01-01",
                                                 'review_by: "2099-1-1"'),
                  "iso yyyy-mm-dd")


def t_flk_13():
    """Empty-field detection: a present-but-blank field is still missing."""
    _expect_error("T_FLK_13", GOOD_ENTRY.replace('evidence: "1 fail in 3 runs"',
                                                 'evidence: ""'),
                  "missing/empty required field")


def t_flk_14():
    """The linter exits 1 on an expired entry and 0 on the same file in date."""
    p = _write(EXPIRED_ENTRY)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(io.StringIO()):
        rc_expired = F.check(p)
        rc_ignored = F.check(p, check_expiry=False)
    msg = buf.getvalue().strip().replace("\n", " ")
    if rc_expired != 1:
        _f("T_FLK_14", f"linter returned {rc_expired} for an EXPIRED entry, wanted 1")
    elif "review_by" not in msg:
        _f("T_FLK_14", f"linter failed but message names no date: {msg}")
    elif rc_ignored != 0:
        _f("T_FLK_14", f"--no-expiry returned {rc_ignored}, wanted 0")
    else:
        _p("T_FLK_14", f"rc=1 / --no-expiry rc=0; msg: {msg}")


# ── runtime policy negatives ─────────────────────────────────────────────────

def _run(tid, path, body):
    """Drive one test id through the real dispatcher and return (result, output)."""
    _use(path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R.run_with_flake_retry(tid, body)
    return R.RESULTS.get(tid, "<none>"), buf.getvalue()


def t_flk_15():
    """Undeclared id: flake() becomes FAIL and there is NO retry."""
    calls = []

    def body():
        calls.append(1)
        R.flake("T_NOT_DECLARED", "network hiccup")

    res, out = _run("T_NOT_DECLARED", _write(GOOD_ENTRY), body)
    if not res.startswith("FAIL") or "UNDECLARED" not in res:
        _f("T_FLK_15", f"wanted FAIL/UNDECLARED, got: {res}")
    elif len(calls) != 1:
        _f("T_FLK_15", f"undeclared flake was retried ({len(calls)} attempts)")
    else:
        _p("T_FLK_15", res)


def t_flk_16():
    """Expired declaration: FAIL naming review_by and the owning task."""
    def body():
        R.flake("T_DEMO", "same old symptom")

    res, _ = _run("T_DEMO", _write(EXPIRED_ENTRY), body)
    if not res.startswith("FAIL") or "EXPIRED" not in res:
        _f("T_FLK_16", f"wanted FAIL/EXPIRED, got: {res}")
    elif "2000-01-01" not in res or "TASK-520" not in res:
        _f("T_FLK_16", f"FAIL message omits review_by or task: {res}")
    else:
        _p("T_FLK_16", res)


def t_flk_17():
    """Declared + passes on retry: FLAKY-PASS, both outcomes, NOT a PASS."""
    n = [0]

    def body():
        n[0] += 1
        if n[0] == 1:
            R.flake("T_DEMO", "first attempt symptom")
        else:
            R.pass_("T_DEMO")

    res, out = _run("T_DEMO", _write(GOOD_ENTRY), body)
    if n[0] != 2:
        _f("T_FLK_17", f"declared flake was not retried exactly once ({n[0]} attempts)")
    elif res == "PASS":
        _f("T_FLK_17", "recorded a bare PASS — the retry is invisible to the reader")
    elif not res.startswith("FLAKY-PASS") or "first attempt symptom" not in res:
        _f("T_FLK_17", f"wanted FLAKY-PASS carrying both outcomes, got: {res}")
    elif "attempt2 PASS" not in res:
        _f("T_FLK_17", f"second outcome not reported: {res}")
    else:
        _p("T_FLK_17", res)


def t_flk_18():
    """Declared but reproduces on retry: FAIL, not a flake."""
    def body():
        R.flake("T_DEMO", "symptom again")

    res, _ = _run("T_DEMO", _write(GOOD_ENTRY), body)
    if not res.startswith("FAIL") or "REPRODUCED" not in res:
        _f("T_FLK_18", f"wanted FAIL/REPRODUCED, got: {res}")
    else:
        _p("T_FLK_18", res)


def t_flk_19():
    """Declared, then hard-fails on retry: FAIL carrying attempt 1."""
    n = [0]

    def body():
        n[0] += 1
        if n[0] == 1:
            R.flake("T_DEMO", "attempt one")
        else:
            R.fail("T_DEMO", "real breakage")

    res, _ = _run("T_DEMO", _write(GOOD_ENTRY), body)
    if not res.startswith("FAIL") or "attempt one" not in res or "real breakage" not in res:
        _f("T_FLK_19", f"wanted FAIL naming both attempts, got: {res}")
    else:
        _p("T_FLK_19", res)


def t_flk_20():
    """Unreadable declaration file: fail CLOSED, not open."""
    def body():
        R.flake("T_DEMO", "symptom")

    res, _ = _run("T_DEMO", _TMP / "definitely_absent.yaml", body)
    if not res.startswith("FAIL") or "unreadable" not in res:
        _f("T_FLK_20", f"wanted FAIL/unreadable (fail-closed), got: {res}")
    else:
        _p("T_FLK_20", res)


def t_flk_21():
    """A declared flake that no dispatcher ever retried is a FAIL, not silence."""
    _use(_write(GOOD_ENTRY))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R.flake("T_DEMO", "orphaned claim")     # note: no run_with_flake_retry
        rc = R.print_results(exit_on_finish=False)
    res = R.RESULTS.get("T_DEMO", "<none>")
    if not res.startswith("FAIL") or "never retried" not in res:
        _f("T_FLK_21", f"wanted FAIL/never retried, got: {res}")
    elif rc != 1:
        _f("T_FLK_21", f"summary exit code {rc}, wanted 1")
    else:
        _p("T_FLK_21", res)


def t_flk_22():
    """Summary buckets: FLAKY-PASS is counted and printed apart from passes."""
    _use(_write(GOOD_ENTRY))
    n = [0]

    def body():
        n[0] += 1
        R.flake("T_DEMO", "sym") if n[0] == 1 else R.pass_("T_DEMO")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R.pass_("T_OK")
        R.skip("T_SK", "no hardware")
        R.run_with_flake_retry("T_DEMO", body)
        rc = R.print_results(exit_on_finish=False)
    out = buf.getvalue()
    want = "1 passed, 0 failed, 1 skipped, 1 declared-flake (passed on retry)"
    if want not in out:
        _f("T_FLK_22", f"summary line wrong; wanted {want!r} in:\n{out}")
    elif "Declared flakes (retried; NOT counted as passes)" not in out:
        _f("T_FLK_22", "no separate declared-flake section in the summary")
    elif "TASK-520" not in out or "review_by" not in out:
        _f("T_FLK_22", "declared-flake section omits owning task / review_by")
    elif rc != 0:
        _f("T_FLK_22", f"exit code {rc} for a flaky-pass-only run, wanted 0")
    else:
        _p("T_FLK_22", want)


ALL = [t_flk_01, t_flk_02, t_flk_03, t_flk_04, t_flk_05, t_flk_06, t_flk_07,
       t_flk_08, t_flk_09, t_flk_10, t_flk_11, t_flk_12, t_flk_13, t_flk_14,
       t_flk_15, t_flk_16, t_flk_17, t_flk_18, t_flk_19, t_flk_20, t_flk_21,
       t_flk_22]


def main() -> int:
    print("T_FLK_01..22  flaky-set policy gate (TASK-520, BP-068)")
    for fn in ALL:
        try:
            fn()
        except Exception as e:
            import traceback
            _f(fn.__name__.upper(), f"Exception: {type(e).__name__}: {e}")
            traceback.print_exc()
    _use(None)
    failed = [t for t, v in RESULTS.items() if v.startswith("FAIL")]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
