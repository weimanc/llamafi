#!/usr/bin/env python3
"""test_check_docs.py — T_DOC_01..T_DOC_09 for run/check-docs (TASK-475).

Registered in docs/verification/test_plan.md under the T_DOC_ family, reserved
by @VE before this harness existed. Host-side only: no DUT, no serial, no
network. Run directly, or via app/tools/smoke_test.sh (run/check gate 9).

    python3 app/tools/test_check_docs.py

Every count assertion runs against the frozen fixture at
testdata/check_docs/ or a throwaway git repo in mktemp — never the live tree.
The live corpus moved 280 -> 282 inside a single commit and reads 286 in a
clean checkout, so live numbers are observations, never pass conditions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "testdata", "check_docs")
GOLDEN = os.path.join(FIXTURE, "golden.txt")
CHECKER = os.path.join(HERE, "check_docs.py")

sys.path.insert(0, HERE)
import check_docs as cd  # noqa: E402

FAILURES: list[str] = []


def check(tid: str, cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(f"{tid}: {msg}")
        print(f"  FAIL  {tid}: {msg}")


def run_cli(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, CHECKER, *args],
                          capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout + proc.stderr


# ── throwaway git repos ───────────────────────────────────────────────────────

def git(repo: str, *args: str) -> str:
    return subprocess.run(("git", "-C", repo, *args), capture_output=True,
                          text=True, check=True).stdout


def new_repo(tmp: str) -> str:
    """A minimal repo with a gated docs/ corpus and a 10-line resolution target."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "docs", "project"))
    os.makedirs(os.path.join(repo, "app", "src"))
    with open(os.path.join(repo, "app", "src", "main.cpp"), "w") as fh:
        fh.write("".join(f"// line {i}\n" for i in range(1, 11)))
    subprocess.run(("git", "init", "-q", repo), check=True)
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "T_DOC")
    return repo


def write(repo: str, rel: str, text: str) -> None:
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def commit(repo: str, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD").strip()


def delta_failures(repo: str, base: str = "HEAD") -> int:
    return len(cd.check_c1_delta(cd.Corpus(repo), base).failures)


BROKEN = ["A citation app/src/ghost.cpp:1 here.",
          "Another app/src/ghost.cpp:2 here.",
          "Third app/src/ghost.cpp:3 here."]


# ── T_DOC_01 — output contract + exit-status semantics ────────────────────────

def t_doc_01() -> None:
    tid = "T_DOC_01"
    rc, out = run_cli("--root", FIXTURE, "--no-git")
    check(tid, rc == 1, f"blocking C5 failure must exit 1, got {rc}")
    check(tid, "=== Doc check ===" in out, "standalone output missing banner")
    check(tid, "=== Results:" in out, "standalone output missing Results tail")
    check(tid, "[1/1] C5" in out, "standalone output missing [n/N] progress line")

    # Advisory-only failure must exit 0. Copy the fixture and repair the one
    # broken link, leaving C1/C2/C3 advisory failures in place.
    with tempfile.TemporaryDirectory() as tmp:
        alt = os.path.join(tmp, "fx")
        shutil.copytree(FIXTURE, alt)
        main = os.path.join(alt, "docs", "architecture", "designs", "M-FIX-main.md")
        text = open(main).read().replace("[missing](M-FIX-missing.md)",
                                         "[nested again](M-FIX-nested.md)")
        open(main, "w").write(text)
        rc2, out2 = run_cli("--root", alt, "--no-git")
        check(tid, rc2 == 0, f"advisory-only failures must exit 0, got {rc2}")
        check(tid, "[warn] C1-full" in out2, "advisory C1 warn line missing on the exit-0 path")

    # --quiet is one gate slot: no banner, no Results tail.
    rc3, out3 = run_cli("--root", FIXTURE, "--no-git", "--quiet")
    check(tid, rc3 == 1, f"--quiet must keep the exit status, got {rc3}")
    check(tid, "=== Doc check ===" not in out3, "--quiet must not print the banner")
    check(tid, "=== Results:" not in out3, "--quiet must not print a second Results tail")


# ── T_DOC_02 — corpus/exemption resolution, incl. the negative test ───────────

def t_doc_02() -> None:
    tid = "T_DOC_02"
    live = os.path.dirname(os.path.dirname(HERE))
    c = cd.Corpus(live)
    check(tid, len(c.gated) == 234, f"live gated corpus must be 234, got {len(c.gated)}")
    check(tid, len(c.exempt) == 69, f"live exempt set must be 69, got {len(c.exempt)}")
    check(tid, "CLAUDE.md" in c.gated, "CLAUDE.md must be gated")

    fx = cd.Corpus(FIXTURE)
    out = "\n".join(cd.check_c1_full(fx).failures + cd.check_c5(fx).failures
                    + cd.check_c3(fx).failures)
    for exempt_marker in ("ghost.cpp:500", "ghost.cpp:501", "ghost.cpp:502",
                          "ghost.cpp:503", "cyd2usb_reviewonly"):
        check(tid, exempt_marker not in out,
              f"exempt file was scanned: {exempt_marker} appeared in failures")

    # NEGATIVE TEST: exempt files must remain RESOLUTION SOURCES. TASK-900 lives
    # only in the exempt tasks-archive.md. A resolver that honours the exemption
    # scores 1261 false failures on the live corpus.
    c2 = cd.check_c2(fx)
    check(tid, not any("TASK-900" in f for f in c2.failures),
          "TASK-900 resolves only in the exempt archive and must still resolve")
    live_c2 = cd.check_c2(c)
    check(tid, len(live_c2.failures) == 0,
          f"live C2 must read 0; {len(live_c2.failures)} suggests the archive "
          f"was dropped as a resolution source")


# ── T_DOC_03 — C1-full golden over the frozen fixture ────────────────────────

def t_doc_03() -> None:
    tid = "T_DOC_03"
    rc, out = run_cli("--root", FIXTURE, "--no-git")
    expected = open(GOLDEN).read()
    check(tid, out == expected,
          "fixture output drifted from golden.txt — diff it; if the change is "
          "intended, regenerate the golden deliberately")
    # The anti-regression case, asserted explicitly rather than incidentally:
    # a BROKEN citation written in inline backticks must be counted. If inline
    # backtick suppression is ever reintroduced, this line disappears.
    check(tid, "M-FIX-main.md:37: app/src/ghost.cpp:7" in out,
          "backticked broken citation not reported — inline-backtick "
          "suppression would hide 96% of the live corpus")
    check(tid, "5 broken of 9 citations" in out, "fixture C1 count changed")
    # Fenced blocks and the ignore marker must NOT be counted.
    for suppressed in ("ghost.cpp:42", "ghost.cpp:44", "nowhere.py:100", "ghost.cpp:43"):
        check(tid, suppressed not in out, f"suppressed citation {suppressed} was counted")
    check(tid, rc == 1, "fixture golden run must exit 1 (C5 is blocking and fails)")


# ── T_DOC_04 — C1-delta reports a known non-zero count ───────────────────────

def t_doc_04() -> None:
    tid = "T_DOC_04"
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write(repo, "docs/board.md", "# Board\nClean line, app/src/main.cpp:5 resolves.\n")
        commit(repo, "A")
        check(tid, delta_failures(repo) == 0, "clean tree must give 0 (vacuous half)")
        # Now introduce two broken citations in the working tree.
        write(repo, "docs/board.md",
              "# Board\nClean line, app/src/main.cpp:5 resolves.\n" + BROKEN[0] + "\n" + BROKEN[1] + "\n")
        check(tid, delta_failures(repo) == 2,
              f"2 newly added broken citations expected, got {delta_failures(repo)}")
        # An untracked gated .md counts every line as added.
        write(repo, "docs/new.md", "# New\n" + BROKEN[2] + "\n")
        check(tid, delta_failures(repo) == 3,
              f"untracked gated .md must contribute, got {delta_failures(repo)}")
        # A file outside the gated corpus must NOT contribute, however broken.
        write(repo, "app/tools/testdata/x/docs/thing.md", "# Not gated\n" + BROKEN[0] + "\n")
        check(tid, delta_failures(repo) == 3,
              "a .md outside docs/ must be invisible to the gate")


# ── T_DOC_05 — document-split carve-out + the two mandatory controls ──────────

def t_doc_05() -> None:
    tid = "T_DOC_05"
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write(repo, "docs/board.md", "# Board\n" + "\n".join(BROKEN) + "\n")
        # An unrelated file that ALREADY EXISTS at the base rev, with content
        # dissimilar enough that git's copy detection will not attribute it.
        write(repo, "docs/unrelated.md", "# Unrelated\n" + "".join(
            f"Distinct prose paragraph number {i}, sharing nothing with the board.\n"
            for i in range(1, 21)))
        rev_a = commit(repo, "A: three broken citations")

        # Split: board.md shrinks, board-part2.md takes the three lines verbatim.
        write(repo, "docs/board.md", "# Board\nSee part 2.\n")
        write(repo, "docs/board-part2.md", "# Board part 2\n" + "\n".join(BROKEN) + "\n")
        commit(repo, "B: split")
        n = delta_failures(repo, rev_a)
        check(tid, n == 0, f"document split must give 0 (relocated debt), got {n}")

        # CONTROL 1 — editing a relocated citation to a NEW broken line must fire.
        write(repo, "docs/board-part2.md",
              "# Board part 2\n" + BROKEN[0] + "\n" + BROKEN[1] + "\n"
              "Third app/src/ghost.cpp:77 here.\n")
        n1 = delta_failures(repo, rev_a)
        check(tid, n1 == 1, f"edit-after-move control must give 1, got {n1}")

        # CONTROL 2 — a genuinely new broken citation in an untouched file.
        git(repo, "checkout", "-q", "--", "docs/board-part2.md")
        write(repo, "docs/other.md", "# Other\nBrand new app/src/ghost.cpp:88 citation.\n")
        n2 = delta_failures(repo, rev_a)
        check(tid, n2 == 1, f"new-broken-citation control must give 1, got {n2}")
        os.remove(os.path.join(repo, "docs", "other.md"))

        # Pure rename, no edit at all.
        git(repo, "mv", "docs/board-part2.md", "docs/board-renamed.md")
        n3 = delta_failures(repo, rev_a)
        check(tid, n3 == 0, f"pure rename must give 0, got {n3}")
        git(repo, "mv", "docs/board-renamed.md", "docs/board-part2.md")

        # ISOLATES THE VERBATIM CARVE-OUT. Every scenario above is carried by
        # `git diff -M -C` rename/copy detection on its own — mutation testing
        # showed that deleting the carve-out left them all green, i.e. they did
        # not test it at all. Here the debt is appended to a file that already
        # existed at the base rev and is too dissimilar to be attributed as a
        # copy, so the three lines arrive as plain `+` lines and ONLY the
        # verbatim-at-base rule keeps them out.
        base_unrelated = open(os.path.join(repo, "docs", "unrelated.md")).read()
        write(repo, "docs/unrelated.md", base_unrelated + "\n".join(BROKEN) + "\n")
        n4 = delta_failures(repo, rev_a)
        check(tid, n4 == 0,
              f"verbatim relocation into an existing unrelated file must give 0, got {n4}")
        # And the same file with a NEW broken citation must still fire, so the
        # carve-out is not a blanket amnesty for touched files.
        write(repo, "docs/unrelated.md", base_unrelated + "Fresh app/src/ghost.cpp:99 here.\n")
        n5 = delta_failures(repo, rev_a)
        check(tid, n5 == 1, f"new citation in the same file must give 1, got {n5}")


# ── T_DOC_06 — CHECK_DOCS_BASE, rev and range ────────────────────────────────

def t_doc_06() -> None:
    tid = "T_DOC_06"
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write(repo, "docs/board.md", "# Board\nclean app/src/main.cpp:5\n")
        rev_a = commit(repo, "A")
        write(repo, "docs/board.md", "# Board\nclean app/src/main.cpp:5\n" + BROKEN[0] + "\n")
        rev_b = commit(repo, "B: one broken")
        write(repo, "docs/board.md",
              "# Board\nclean app/src/main.cpp:5\n" + BROKEN[0] + "\n" + BROKEN[1] + "\n")
        rev_c = commit(repo, "C: two broken")

        check(tid, delta_failures(repo, f"{rev_b}..{rev_c}") == 1,
              "range B..C must report exactly the citation C added")
        check(tid, delta_failures(repo, f"{rev_a}..{rev_c}") == 2,
              "range A..C must report both added citations")
        check(tid, delta_failures(repo, rev_a) == 2,
              "rev A against the worktree must report both")
        check(tid, delta_failures(repo, "HEAD") == 0,
              "clean tree against HEAD must report 0")

        # The env var is the documented override and must reach the checker.
        env = dict(os.environ, CHECK_DOCS_BASE=f"{rev_a}..{rev_c}")
        proc = subprocess.run([sys.executable, CHECKER, "--root", repo],
                              capture_output=True, text=True, check=False, env=env)
        check(tid, "2 broken of 2 newly added citations" in proc.stdout,
              f"CHECK_DOCS_BASE env override not honoured:\n{proc.stdout}")


# ── T_DOC_07 — C2 glob resolution, including a simulated board split ─────────

def t_doc_07() -> None:
    tid = "T_DOC_07"
    with tempfile.TemporaryDirectory() as tmp:
        repo = new_repo(tmp)
        write(repo, "docs/project/tasks.md", "# Board\n| TASK-100 | OPEN |\n")
        write(repo, "docs/notes.md", "Refers to TASK-100 and TASK-200.\n")
        n = len(cd.check_c2(cd.Corpus(repo)).failures)
        check(tid, n == 1, f"TASK-200 is unfiled and must fail; got {n}")

        # Split the board: TASK-200 moves into a NEW tasks-*.md. A hardcoded
        # file list turns this into a repo-wide failure; the glob must follow.
        write(repo, "docs/project/tasks-extra.md", "# Split board\n| TASK-200 | OPEN |\n")
        n2 = len(cd.check_c2(cd.Corpus(repo)).failures)
        check(tid, n2 == 0, f"glob must discover the split board file; got {n2}")


# ── T_DOC_08 — C3 scope ──────────────────────────────────────────────────────

def t_doc_08() -> None:
    tid = "T_DOC_08"
    def flagged_names(res) -> set[str]:
        # Compare the flagged IDENTIFIER, never a substring of the message:
        # "cyd" is a substring of every "cyd2usb_bogus" failure line.
        return {f.split(": ")[-1].split(" ->")[0] for f in res.failures}

    r = cd.check_c3(cd.Corpus(FIXTURE))
    names_fx = flagged_names(r)
    check(tid, "cyd2usb_bogus" in names_fx, "unknown cyd2usb_* env must be flagged")
    check(tid, len(r.failures) == 1, f"fixture C3 must report exactly 1, got {len(r.failures)}")
    # The sibling project's envs are out of scope entirely.
    for other in ("cyd", "trinity"):
        check(tid, other not in names_fx,
              f"{other} belongs to Spotify-Diy-Thing and must not be flagged")
    live = cd.check_c3(cd.Corpus(os.path.dirname(os.path.dirname(HERE))))
    names = flagged_names(live)
    check(tid, "cyd" not in names and "trinity" not in names,
          f"live C3 must not flag the sibling project's envs; got {sorted(names)}")


# ── T_DOC_09 — C5 link integrity ─────────────────────────────────────────────

def t_doc_09() -> None:
    tid = "T_DOC_09"
    r = cd.check_c5(cd.Corpus(FIXTURE))
    check(tid, r.total == 4, f"fixture must present 4 relative .md links, got {r.total}")
    check(tid, len(r.failures) == 1, f"exactly 1 broken link expected, got {len(r.failures)}")
    # Compare flagged link TARGETS, not substrings of the message text — the
    # message itself contains the word "target".
    targets = {f.split(": ")[-1].split(" ->")[0] for f in r.failures}
    check(tid, targets == {"M-FIX-missing.md"},
          f"exactly the missing link must be flagged, got {sorted(targets)}")
    check(tid, not any("ADR-001" in t for t in targets),
          "anchor must be stripped before resolving")
    check(tid, not any("%20" in t or "space" in t for t in targets),
          "URL-encoded link target must resolve")
    check(tid, not any("example.invalid" in t for t in targets),
          "external links must be ignored")


TESTS = [("T_DOC_01", t_doc_01), ("T_DOC_02", t_doc_02), ("T_DOC_03", t_doc_03),
         ("T_DOC_04", t_doc_04), ("T_DOC_05", t_doc_05), ("T_DOC_06", t_doc_06),
         ("T_DOC_07", t_doc_07), ("T_DOC_08", t_doc_08), ("T_DOC_09", t_doc_09)]


def main() -> int:
    print("=== test_check_docs.py — T_DOC_01..09 ===")
    for tid, fn in TESTS:
        before = len(FAILURES)
        try:
            fn()
        except Exception as exc:                      # noqa: BLE001
            FAILURES.append(f"{tid}: raised {exc!r}")
            print(f"  FAIL  {tid}: raised {exc!r}")
        if len(FAILURES) == before:
            print(f"  PASS  {tid}")
    print()
    if FAILURES:
        print(f"=== {len(FAILURES)} assertion(s) failed ===")
        return 1
    print(f"=== all {len(TESTS)} T_DOC tests passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
