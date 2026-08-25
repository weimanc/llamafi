#!/usr/bin/env python3
"""test_check_docs.py — T_DOC_01..T_DOC_15 for run/check-docs (TASK-475, TASK-521, TASK-482).

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
    # TASK-475 phases 2 and 4 (2026-08-25): C2 and C4 are now blocking
    # alongside C5, so the fixture's [n/N] counted-blocking-check count is 3
    # (C4 itself is clean in the fixture — both its Status: headers already
    # conform — so it counts but never fails here).
    check(tid, "[3/3]" in out, "standalone output missing [n/N] progress line")

    # Advisory-only failure must exit 0. Copy the fixture and repair the one
    # broken link (C5) and the four broken ids (C2, now blocking too),
    # leaving C1/C3 advisory failures in place.
    with tempfile.TemporaryDirectory() as tmp:
        alt = os.path.join(tmp, "fx")
        shutil.copytree(FIXTURE, alt)
        main = os.path.join(alt, "docs", "architecture", "designs", "M-FIX-main.md")
        text = open(main).read().replace("[missing](M-FIX-missing.md)",
                                         "[nested again](M-FIX-nested.md)")
        text = text.replace("Broken: TASK-999, ADR-999, IFC-999, X099.",
                             "Broken: TASK-100, ADR-001, IFC-001, X001.")
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
    # TASK-511: these were `== 234` / `== 69`, i.e. live-corpus counts used as pass
    # conditions — exactly what this file's own docstring forbids ("live numbers are
    # observations, never pass conditions"). Adding four design documents in one
    # session turned gate 9 red for a reason unrelated to the checker's behaviour.
    # Assert the *invariants* instead and print the counts as observations.
    print(f"    [obs] live corpus: {len(c.gated)} gated, {len(c.exempt)} exempt")
    check(tid, len(c.gated) > 0, "live gated corpus must be non-empty")
    check(tid, len(c.exempt) > 0, "live exempt set must be non-empty")
    check(tid, len(c.gated) > len(c.exempt),
          f"gated ({len(c.gated)}) must exceed exempt ({len(c.exempt)})")
    check(tid, not (set(c.gated) & set(c.exempt)),
          "gated and exempt must be disjoint")
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


# ── C6 — id binding (TASK-521, M-TESTARCH §6) ────────────────────────────────
#
# BP-068: every one of T_DOC_10..14 breaks C6 the way C6 is meant to catch, and
# asserts the failure MESSAGE, not just a count. Each also carries its positive
# control in the same tree, so a check that fired for an unrelated reason — or
# that fires unconditionally — cannot pass.
#
# These build throwaway trees rather than using the frozen fixture: C6 reads
# app/tools/*.py, and the frozen fixture deliberately has none (it prints
# "skipped (no executable registries)" in golden.txt, which is itself the
# assertion that C6 fails closed on a corpus it cannot measure).

def c6_tree(tmp: str, name: str, registry: list[str], docs: dict[str, str],
            ledger: str | None = None) -> str:
    """A minimal root: one executable registry + a docs/verification/ corpus."""
    root = os.path.join(tmp, name)
    os.makedirs(os.path.join(root, "app", "tools"), exist_ok=True)
    with open(os.path.join(root, "app", "tools", "run_fx_tests.py"), "w") as fh:
        fh.write("ALL_TESTS = [\n" + "".join(f"    {i!r},\n" for i in registry) + "]\n")
    for rel, text in docs.items():
        write(root, rel, text)
    if ledger is not None:
        write(root, "docs/verification/id_binding_exceptions.md", ledger)
    return root


def c6(root: str):
    return cd.check_c6(cd.Corpus(root))


PLAN_HDR = "# Test Plan\n\n| id | Covers | Status |\n|---|---|---|\n"
LEDGER_HDR = "# Ledger\n\n| id | kind | why | owner | since |\n|---|---|---|---|---|\n"


def t_doc_10() -> None:
    """NEGATIVE: an executable id with no doc row must fail C6.1."""
    tid = "T_DOC_10"
    with tempfile.TemporaryDirectory() as tmp:
        # Positive control first: both registry ids have rows -> clean.
        ok = c6_tree(tmp, "ok", ["T_FX_01", "T_FX_02"],
                     {"docs/verification/test_plan.md": PLAN_HDR
                      + "| `T_FX_01` | a | `impl` |\n| `T_FX_02` | b | `impl` |\n"})
        r0 = c6(ok)
        check(tid, r0.failures == [], f"positive control must be clean, got {r0.failures}")

        # Break it exactly one way: drop T_FX_02's row.
        bad = c6_tree(tmp, "bad", ["T_FX_01", "T_FX_02"],
                      {"docs/verification/test_plan.md": PLAN_HDR
                       + "| `T_FX_01` | a | `impl` |\n"})
        r = c6(bad)
        check(tid, len(r.failures) == 1, f"exactly 1 orphan expected, got {r.failures}")
        check(tid, any("T_FX_02" in f and "no entry in docs/verification/" in f
                       for f in r.failures),
              f"orphan message must name the id and the reason, got {r.failures}")
        check(tid, "1 orphan" in r.summary, f"summary must count the orphan: {r.summary}")
        # The orphan is reported against the REGISTRY location, so the reader is
        # sent to the code that runs, not to a doc that does not mention it.
        check(tid, any("run_fx_tests.py" in f for f in r.failures),
              f"orphan must cite the registry site, got {r.failures}")


def t_doc_11() -> None:
    """NEGATIVE: a row marked `impl` with no body must fail C6.3 — the teeth.

    And it must fail even WITH a ledger row trying to grandfather it: C6.3 is
    the check LL-140 is about, and an exemption for it would be an exemption
    from the point.
    """
    tid = "T_DOC_11"
    with tempfile.TemporaryDirectory() as tmp:
        bad = c6_tree(tmp, "stale", ["T_FX_01"],
                      {"docs/verification/test_plan.md": PLAN_HDR
                       + "| `T_FX_01` | a | `impl` |\n| `T_FX_09` | ghost | `impl` |\n"})
        r = c6(bad)
        check(tid, any("T_FX_09" in f and "declared `impl`" in f and "no executable registry" in f
                       for f in r.failures),
              f"stale `impl` must be reported as such, got {r.failures}")
        check(tid, "1 mismatched" in r.summary, f"summary must count it: {r.summary}")

        # A `resv` row that DOES have a body is the same defect mirrored.
        rev = c6_tree(tmp, "resv", ["T_FX_01"],
                      {"docs/verification/test_plan.md": PLAN_HDR
                       + "| `T_FX_01` | a | `resv` |\n"})
        rr = c6(rev)
        check(tid, any("T_FX_01" in f and "declared `resv`" in f and "body is registered" in f
                       for f in rr.failures),
              f"`resv` with a body must be reported, got {rr.failures}")

        # `blocked` is deliberately unconstrained, in BOTH directions.
        for reg, why in ((["T_FX_01"], "with a body"), ([], "without a body")):
            b = c6_tree(tmp, f"blk{len(reg)}", reg or ["T_FX_00"],
                        {"docs/verification/test_plan.md": PLAN_HDR
                         + "| `T_FX_01` | a | `blocked` — TASK-1 |\n"
                         + "| `T_FX_00` | b | `impl` |\n"})
            rb = c6(b)
            check(tid, not any("T_FX_01" in f and "mismatch" not in f and "declared" in f
                               for f in rb.failures),
                  f"`blocked` {why} must not be a mismatch, got {rb.failures}")

        # THE LOAD-BEARING ONE: the ledger cannot suppress a mismatch.
        led = c6_tree(tmp, "ledgered", ["T_FX_01"],
                      {"docs/verification/test_plan.md": PLAN_HDR
                       + "| `T_FX_01` | a | `impl` |\n| `T_FX_09` | ghost | `impl` |\n"},
                      ledger=LEDGER_HDR + "| `T_FX_09` | mismatch | wishful | TASK-1 | 2026-08-18 |\n")
        rl = c6(led)
        check(tid, any("T_FX_09" in f and "no executable registry" in f for f in rl.failures),
              f"a ledger row must NOT suppress a mismatch, got {rl.failures}")
        check(tid, any("admits no exceptions" in f for f in rl.failures),
              f"the bad ledger kind must itself be reported, got {rl.failures}")
        # HONEST NOTE, from mutation testing: the no-exception property is held
        # by TWO independent mechanisms — the kind guard above, and the fact
        # that suppression is keyed on (kind, id) so a `mismatch` finding can
        # never match a ledger row of an exemptable kind. Deleting the third,
        # belt-and-braces `kind != "mismatch"` test in check_c6 changes no
        # observable behaviour and NO test catches it. Recorded rather than
        # papered over (the T_DOC_05 precedent). The constant is pinned instead:
        check(tid, "mismatch" not in cd.LEDGER_KINDS,
              f"`mismatch` must never become an exemptable kind: {cd.LEDGER_KINDS}")


def t_doc_12() -> None:
    """NEGATIVE: a doc row with no status at all must fail C6.2."""
    tid = "T_DOC_12"
    with tempfile.TemporaryDirectory() as tmp:
        bad = c6_tree(tmp, "nostatus", ["T_FX_01", "T_FX_02"], {
            "docs/verification/test_plan.md":
                "# Test Plan\n\n| id | Covers |\n|---|---|\n"
                "| `T_FX_01` | no status column at all |\n",
            "docs/verification/regression_suite/fx.md":
                PLAN_HDR + "| `T_FX_02` | empty status cell |  |\n",
        })
        r = c6(bad)
        ids = {f.split(": ")[1].split(" ->")[0] for f in r.failures}
        check(tid, ids == {"T_FX_01", "T_FX_02"},
              f"both the missing column and the empty cell must fail, got {sorted(ids)}")
        check(tid, all("declares no status" in f for f in r.failures),
              f"message must say what is missing, got {r.failures}")
        check(tid, "2 undeclared" in r.summary, f"summary must count them: {r.summary}")

        # POSITIVE CONTROL, and the id-keyed rule: the SAME id declared once
        # anywhere is declared. A family table with no status column plus a
        # detail table that has one is the live corpus's normal shape, and
        # row-keying reports it as broken.
        ok = c6_tree(tmp, "twice", ["T_FX_01"], {
            "docs/verification/test_plan.md":
                "# Test Plan\n\n| id | Covers |\n|---|---|\n| `T_FX_01` | family row |\n"
                "\n| id | Covers | Status |\n|---|---|---|\n| `T_FX_01` | detail row | `impl` |\n",
        })
        check(tid, c6(ok).failures == [],
              f"an id declared in a second table must count as declared: {c6(ok).failures}")

        # The `### T001` entry form declares via a **Status**: field.
        ok2 = c6_tree(tmp, "heading", ["T001"], {
            "docs/verification/test_plan.md":
                "# Test Plan\n\n### T001 — [f-1] a thing\n- **Type**: unit\n"
                "- **Status**: passing\n",
        })
        check(tid, c6(ok2).failures == [],
              f"a **Status**: field must count as declared: {c6(ok2).failures}")

        # An "Expected result" column is criteria, not a status. Reading it as
        # one would make every spec table look declared.
        bad2 = c6_tree(tmp, "expected", ["T_FX_01"], {
            "docs/verification/test_plan.md":
                "# Test Plan\n\n| id | Expected result |\n|---|---|\n"
                "| `T_FX_01` | exits 0 |\n",
        })
        check(tid, any("T_FX_01" in f for f in c6(bad2).failures),
              "an 'Expected result' column must not be read as a status")


def t_doc_13() -> None:
    """The ledger is a gate, not an amnesty: it must shrink and stay honest."""
    tid = "T_DOC_13"
    with tempfile.TemporaryDirectory() as tmp:
        docs = {"docs/verification/test_plan.md": PLAN_HDR + "| `T_FX_01` | a | `impl` |\n"}
        good_row = "| `T_FX_02` | orphan | not registered yet | TASK-1 | 2026-08-18 |\n"

        # A well-formed row suppresses exactly its own finding.
        ok = c6_tree(tmp, "led-ok", ["T_FX_01", "T_FX_02"], docs,
                     ledger=LEDGER_HDR + good_row)
        r = c6(ok)
        check(tid, r.failures == [], f"a valid exception must suppress, got {r.failures}")
        check(tid, "1 orphan" in r.summary and "1 on the ledger" in r.summary
              and "0 unexcepted" in r.summary,
              f"the debt must stay VISIBLE in the summary, got {r.summary}")

        # STALE: the id gets its row, so the exception no longer applies.
        stale = c6_tree(tmp, "led-stale", ["T_FX_01", "T_FX_02"],
                        {"docs/verification/test_plan.md": PLAN_HDR
                         + "| `T_FX_01` | a | `impl` |\n| `T_FX_02` | b | `impl` |\n"},
                        ledger=LEDGER_HDR + good_row)
        rs = c6(stale)
        check(tid, any("stale exception" in f and "T_FX_02" in f for f in rs.failures),
              f"a stale exception must FAIL so the list shrinks, got {rs.failures}")

        # No owning task / no ISO date -> the row is rejected.
        for row, want in (
            ("| `T_FX_02` | orphan | why | @VE | 2026-08-18 |\n", "no owning TASK- id"),
            ("| `T_FX_02` | orphan | why | TASK-1 | soon |\n", "no ISO date"),
        ):
            rb = c6(c6_tree(tmp, "led" + want[:6].replace(" ", ""),
                            ["T_FX_01", "T_FX_02"], docs, ledger=LEDGER_HDR + row))
            check(tid, any(want in f for f in rb.failures),
                  f"ledger row {row.strip()!r} must be rejected ({want}), got {rb.failures}")

        # SELF-REFERENCE: the ledger's own rows must not count as coverage.
        # Without this the ledger grandfathers itself into existence — every
        # `orphan` row becomes a doc entry, clearing the orphan and creating a
        # fresh `undeclared` finding in its place. Found by building it.
        check(tid, not any("id_binding_exceptions.md" in f for f in c6(ok).failures),
              "the ledger must not be scanned as a plan")


def t_doc_14() -> None:
    """Registry discovery + the exemption split, at the mechanism."""
    tid = "T_DOC_14"
    with tempfile.TemporaryDirectory() as tmp:
        # DISCOVERY, not a whitelist: a NEW satellite suite binds with no edit
        # to check_docs.py. This is the mechanism the 41 live orphans arrived
        # through, so it is asserted rather than assumed.
        root = c6_tree(tmp, "disc", ["T_FX_01"],
                       {"docs/verification/test_plan.md": PLAN_HDR
                        + "| `T_FX_01` | a | `impl` |\n"})
        for fname, body in (
            ("test_sat_dict.py", 'ALL_TESTS = {"T_SAT_01": None}\n'),
            ("test_sat_pairs.py", 'TESTS = [("T_SAT_02", None)]\n'),
            ("test_sat_fns.py", "def t_sat_03():\n    pass\n\n\nALL = [t_sat_03]\n"),
        ):
            with open(os.path.join(root, "app", "tools", fname), "w") as fh:
                fh.write(body)
        found = {f.split(": ")[1].split(" ->")[0] for f in c6(root).failures}
        check(tid, found == {"T_SAT_01", "T_SAT_02", "T_SAT_03"},
              f"all three registry SHAPES must be discovered, got {sorted(found)}")

        # EXEMPTION SPLIT, reusing is_exempt(): a historical record RESOLVES a
        # registry id (no orphan) but can never DECLARE its status (no
        # undeclared complaint either). Same rule as C2's tasks-archive case.
        ex = c6_tree(tmp, "exempt", ["T_FX_07"], {
            "docs/verification/test_plan.md": PLAN_HDR + "| `T_FX_01` | a | `impl` |\n",
            "docs/verification/regression_suite/old-ve-review.md":
                "# Old\n\n| id | Covers |\n|---|---|\n| `T_FX_07` | reviewed once |\n",
        })
        rex = c6(ex)
        check(tid, not any("T_FX_07" in f for f in rex.failures),
              f"an exempt file must resolve C6.1 and be silent on C6.2, got {rex.failures}")
        # CONTROL: the identical file, not exempt, IS held to C6.2.
        ctl = c6_tree(tmp, "notexempt", ["T_FX_07"], {
            "docs/verification/test_plan.md": PLAN_HDR + "| `T_FX_01` | a | `impl` |\n",
            "docs/verification/regression_suite/old-notes.md":
                "# Old\n\n| id | Covers |\n|---|---|\n| `T_FX_07` | reviewed once |\n",
        })
        check(tid, any("T_FX_07" in f and "declares no status" in f for f in c6(ctl).failures),
              "the same table in a NON-exempt file must fail C6.2 — otherwise the "
              "exempt case above passes for the wrong reason")

        # FAIL CLOSED: no registries at all is a skip with a stated reason, not
        # a silent pass that reports 100% binding.
        bare = os.path.join(tmp, "bare")
        write(bare, "docs/verification/test_plan.md", PLAN_HDR + "| `T_FX_01` | a | `impl` |\n")
        rb = c6(bare)
        check(tid, rb.skipped and "no executable registries" in rb.summary,
              f"a corpus with no registries must skip loudly, got {rb.summary!r}")


# ── T_DOC_15 — SPIKE retirement check (TASK-482, M-TOOLING §4 rule 3) ───────

def t_doc_15() -> None:
    """NEGATIVE: a spike/task<NNN>_* whose TASK-NNN is archived must fail.

    Positive control (task number NOT archived) must stay clean in the same
    tree, so the check cannot be passing/failing for an unrelated reason.
    Also proves only the LEADING task number is checked (task123_456_x.py
    with 123 archived but 456 not) and that a non-spike-shaped filename in
    app/tools/ (no task<NNN>_ prefix) is ignored entirely.
    """
    tid = "T_DOC_15"
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "spike")
        write(root, "docs/project/tasks-archive.md",
              "| TASK-100 | DONE | archived |\n| TASK-123 | DONE | archived |\n")
        write(root, "app/tools/task100_old_spike.py", "# archived task -> retire\n")
        write(root, "app/tools/task200_live_spike.py", "# open task -> keep\n")
        write(root, "app/tools/task123_456_pair_spike.py", "# leading number only\n")
        write(root, "app/tools/helpers.py", "# not a spike filename at all\n")

        r = cd.check_spike_retirement(cd.Corpus(root))
        check(tid, r.total == 3,
              f"exactly 3 spike-shaped files expected (helpers.py must not "
              f"match), got {r.total}")
        flagged = {f.split(":")[0] for f in r.failures}
        check(tid, flagged == {"app/tools/task100_old_spike.py",
                               "app/tools/task123_456_pair_spike.py"},
              f"exactly the archived-leading-number spikes must be flagged, got {flagged}")
        check(tid, not any("task200_live_spike.py" in f for f in r.failures),
              "positive control: an open task's spike must not be flagged")
        check(tid, any("TASK-100" in f for f in r.failures)
              and not any("TASK-200" in f for f in r.failures),
              "message must name the archived task id")
        check(tid, "2 retirement-due of 3 spike scripts" in r.summary,
              f"summary must count both dimensions: {r.summary}")


TESTS = [("T_DOC_01", t_doc_01), ("T_DOC_02", t_doc_02), ("T_DOC_03", t_doc_03),
         ("T_DOC_04", t_doc_04), ("T_DOC_05", t_doc_05), ("T_DOC_06", t_doc_06),
         ("T_DOC_07", t_doc_07), ("T_DOC_08", t_doc_08), ("T_DOC_09", t_doc_09),
         ("T_DOC_10", t_doc_10), ("T_DOC_11", t_doc_11), ("T_DOC_12", t_doc_12),
         ("T_DOC_13", t_doc_13), ("T_DOC_14", t_doc_14), ("T_DOC_15", t_doc_15)]


def main() -> int:
    print("=== test_check_docs.py — T_DOC_01..15 ===")
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
