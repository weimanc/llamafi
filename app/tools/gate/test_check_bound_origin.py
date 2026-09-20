#!/usr/bin/env python3
"""test_check_bound_origin.py — negative suite for check_bound_origin.py. BP-068.

TASK-613 / R44 (docs/verification/M-HARNESS2-requirements.md:732-737). A
delta gate that has never been seen to fire is not proof it works — this
suite builds a throwaway git repo shaped like the real
`app/tools/suite/serialdbg/` corpus (a module with a `TESTS` dict and a
registered test function) and pins the four claims the task ruling asks for:

  * a newly-added uncited bound IS a finding;
  * the same bound WITH a citation is NOT a finding;
  * a bound that merely MOVED (present verbatim at the base rev, anywhere in
    the corpus) is NOT a finding;
  * the trivia rule (equality comparisons, and inequality against
    {-1, 0, 1}) holds in both directions — trivia is never flagged even when
    newly added and uncited, and a real bound is flagged even when it LOOKS
    small-ish but isn't trivia.

Also pins the two non-obvious scoping calls this task made: a literal inside
a non-test helper function (not in `TESTS`) is never a candidate, and a
`bounds={}` declaration on `@meta(...)` IS in scope (R44's own named 4096
example is exactly this shape).

No DUT, no serial port, no build, no network.
Run: python3 app/tools/gate/test_check_bound_origin.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_bound_origin as C  # noqa: E402
import _case_runner  # noqa: E402

SUITE_REL = "app/tools/suite/serialdbg"


def git(repo: str, *args: str) -> str:
    return subprocess.run(("git", "-C", repo) + args, capture_output=True,
                          text=True, check=True).stdout


def new_repo(tmp: str) -> str:
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, SUITE_REL))
    subprocess.run(("git", "init", "-q", repo), check=True)
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "T_BND")
    return repo


BASE_MODULE = '''\
def t_example(dut):
    """T_EX_01: example."""
    val = dut.get_int("thing")
    if val != 0:
        return
{extra}
    return val


def _helper_not_a_test(dut):
    depth = 0
    if depth > 6:
        return


TESTS = {{
    "T_EX_01": t_example,
}}
'''


def write_module(repo: str, extra: str = "") -> None:
    path = os.path.join(repo, SUITE_REL, "example.py")
    with open(path, "w") as fh:
        fh.write(BASE_MODULE.format(extra=extra))


def commit(repo: str, msg: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def failures(repo: str, base: str = "HEAD") -> list[str]:
    rc, fails, _summary = C.run(repo, base, quiet=True)
    return fails


# ── a newly-added uncited bound is a finding ────────────────────────────────

def case_new_uncited_bound_is_a_finding():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        write_module(repo, extra='    if val > 12345:\n        return\n')
        fails = failures(repo)
        assert len(fails) == 1, f"expected exactly 1 finding, got {fails}"
        assert "12345" in fails[0]


# ── the same bound WITH a citation is not a finding ─────────────────────────

def case_cited_bound_is_not_a_finding():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        write_module(repo, extra=(
            '    if val > 12345:  # TASK-999: derived from foo.h:LIMIT\n'
            '        return\n'))
        fails = failures(repo)
        assert fails == [], f"expected no findings, got {fails}"


def case_dated_measurement_citation_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        write_module(repo, extra=(
            '    if val > 12345:  # measured 2026-09-20, N=10, worst 9000\n'
            '        return\n'))
        fails = failures(repo)
        assert fails == [], f"expected no findings, got {fails}"


def case_symbol_citation_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        write_module(repo, extra=(
            '    if val > 12345:  # firmware.h:MAX_LIMIT\n'
            '        return\n'))
        fails = failures(repo)
        assert fails == [], f"expected no findings, got {fails}"


# ── a bound that merely moved (present at base) is not a finding ───────────

def case_relocated_bound_is_not_a_finding():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo, extra='    if val > 12345:\n        return\n')
        commit(repo, "base")
        # Same exact bound line, now duplicated elsewhere in the corpus —
        # the text existed verbatim at the base rev, so it is relocated
        # debt, not new debt.
        write_module(repo, extra=(
            '    if val > 12345:\n'
            '        return\n'
            '    if val > 12345:\n'
            '        return\n'))
        fails = failures(repo)
        assert fails == [], f"a relocated (duplicated) bound must not fire: {fails}"


# ── trivia rule holds in both directions ────────────────────────────────────

def case_trivia_inequality_not_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        write_module(repo, extra=(
            '    if val > 0:\n'
            '        return\n'
            '    if val < 1:\n'
            '        return\n'
            '    if val >= -1:\n'
            '        return\n'))
        fails = failures(repo)
        assert fails == [], f"trivia values {{-1,0,1}} must never be candidates: {fails}"


def case_equality_not_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        write_module(repo, extra=(
            '    if val == 42:\n'
            '        return\n'
            '    if val != 99:\n'
            '        return\n'))
        fails = failures(repo)
        assert fails == [], f"==/!= comparisons must never be candidates: {fails}"


def case_real_bound_still_flagged_when_small_but_not_trivia():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        write_module(repo, extra='    if val > 2:\n        return\n')
        fails = failures(repo)
        assert len(fails) == 1, f"a non-trivia inequality bound (2) must be a candidate: {fails}"


# ── scoping calls ────────────────────────────────────────────────────────────

def case_non_test_helper_not_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        module = BASE_MODULE.format(extra="") + "\n"  # no-op baseline
        # Bump the helper's guard to a new, uncited, non-trivia value.
        module = module.replace("if depth > 6:", "if depth > 77:")
        with open(os.path.join(repo, SUITE_REL, "example.py"), "w") as fh:
            fh.write(module)
        fails = failures(repo)
        assert fails == [], (
            f"a literal in a function not in TESTS must never be a candidate: {fails}")


def case_bounds_kwarg_in_scope():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        module = '''\
def meta(**kw):
    def _wrap(fn):
        fn._meta = kw
        return fn
    return _wrap


@meta(oracle={"thing": "THRESHOLD"}, bounds={"thing": 4096})
def t_example(dut):
    """T_EX_01: example."""
    val = dut.get_int("thing")
    if val != 0:
        return
    return val


TESTS = {
    "T_EX_01": t_example,
}
'''
        with open(os.path.join(repo, SUITE_REL, "example.py"), "w") as fh:
            fh.write(module)
        fails = failures(repo)
        assert len(fails) == 1 and "4096" in fails[0], (
            f"an uncited bounds={{}} entry must be a finding (R44's own named "
            f"example): {fails}")



def case_unrelated_task_mention_elsewhere_in_the_body_does_not_cite_a_bound():
    """The window must attach a citation to the NUMBER, not to the test.

    Found by planting, not by reading: an earlier draft searched the whole
    enclosing function body, and an uncited `collisions > 7777` planted in the
    real `t_plr_22` PASSED, because that body mentions TASK-695 in an unrelated
    comment about restoring `plCursor`. Most suite bodies cite some task for
    some reason, so a body-wide window agrees with almost anything.

    Both directions are pinned: an unrelated reference does NOT cite the bound,
    and a function-scope comment that NAMES the literal still does — which is
    how one comment documenting several bounds keeps working.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo)
        commit(repo, "base")
        body = (
            "def t_example(dut):\n"
            '    """T_EX_01: example."""\n'
            "    # `set plCursor` moves real state (TASK-695 B-4) — restore it.\n"
            "    # on every exit path, not just the fall-through below.\n"
            "    collisions = 0\n"
            "    errors = []\n"
            "    seen = 0\n"
            "    if collisions > 7777:\n"
            "        return\n"
            "    return collisions\n"
            "\n\n"
            "TESTS = {\n"
            '    "T_EX_01": t_example,\n'
            "}\n"
        )
        path = os.path.join(repo, SUITE_REL, "example.py")
        with open(path, "w") as fh:
            fh.write(body)
        fails = failures(repo)
        assert len(fails) == 1 and "7777" in fails[0], (
            "an unrelated TASK- reference elsewhere in the body must NOT count "
            f"as this bound's citation: {fails}")

        with open(path, "w") as fh:
            fh.write(body.replace(
                "    # `set plCursor`",
                "    # 7777 is the ceiling, measured 2026-09-20 over 5 runs.\n"
                "    # `set plCursor`"))
        assert failures(repo) == [], (
            "a function-scope comment that NAMES the literal is a citation")


# ── lands at zero by construction ───────────────────────────────────────────

def case_empty_diff_is_zero():
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write_module(repo, extra='    if val > 12345:\n        return\n')
        commit(repo, "base")
        rc, fails, summary = C.run(repo, "HEAD", quiet=True)
        assert rc == 0 and fails == [], f"unchanged tree must read 0: {fails}"
        assert "0 uncited of 0" in summary


# ── live corpus sanity: the checker imports and runs against the real repo ──

def case_live_main_runs():
    proj_root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    rc = subprocess.run([sys.executable, os.path.join(HERE, "check_bound_origin.py"),
                        "--root", proj_root, "--quiet"],
                        capture_output=True, text=True, check=False).returncode
    assert rc == 0, f"live default-base (HEAD) run must be 0 on a clean checkout, got {rc}"


CASES = [
    ("new uncited bound -> finding",           case_new_uncited_bound_is_a_finding),
    ("cited bound (TASK-/file:SYMBOL) -> ok",  case_cited_bound_is_not_a_finding),
    ("dated-measurement citation -> ok",       case_dated_measurement_citation_accepted),
    ("bare file:SYMBOL citation -> ok",        case_symbol_citation_accepted),
    ("relocated (duplicated) bound -> ok",     case_relocated_bound_is_not_a_finding),
    ("trivia inequality {-1,0,1} -> ok",       case_trivia_inequality_not_flagged),
    ("== / != -> ok (never a bound)",          case_equality_not_flagged),
    ("small non-trivia bound (2) -> finding",  case_real_bound_still_flagged_when_small_but_not_trivia),
    ("non-TESTS helper literal -> ok",         case_non_test_helper_not_candidate),
    ("uncited bounds={} kwarg -> finding",     case_bounds_kwarg_in_scope),
    ("body-wide TASK ref does not cite",       case_unrelated_task_mention_elsewhere_in_the_body_does_not_cite_a_bound),
    ("empty diff -> 0 by construction",        case_empty_diff_is_zero),
    ("live repo, default base -> exit 0",      case_live_main_runs),
]


def main() -> int:
    return _case_runner.run_cases("test_check_bound_origin", CASES)


if __name__ == "__main__":
    sys.exit(main())
