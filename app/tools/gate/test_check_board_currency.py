#!/usr/bin/env python3
"""Negative tests for check_board_currency.py — BP-068. TASK-669.

This gate lands GREEN on a 72-row ledger, so "PASS, no findings" is exactly what
it would print if `evaluate()` never fired at all. Every arm here therefore
drives the real `evaluate()` against a THROWAWAY board and an INJECTED commit
list — the fixtures never touch this repository's git history, so the next
commit anyone makes cannot silently invalidate an arm (and an arm cannot
accidentally start passing because someone reconciled a board).

Arms:
  N1-N3   one per check: B1, B2, B3 each fire on their own defect.
  C1-C3   the three controls that must NOT flag — a PARTIAL row with a commit,
          a DONE row citing a hash, a row blocked on a genuinely open task.
  E1-E2   the escapes suppress their own check and no other.
  L1-L5   the ledger: keyed suppression, staleness, malformed rows, absence.
  M1-M2   the MUTATION arms — B1 and B3 reconstructed from this week's real
          defects, as literal board text from the tree before `0dba35a`.
  P1-P3   properties of the parser that the checks silently depend on.
  B5      the "Next free id" claim (TASK-716/BP-077/LL-154) — a correct claim,
          an off-by-one, THE TRAP (a claim's own token must not make it agree
          with itself), same-line stale history not leaking back in, and the
          claim/corpus split.
  B6      a ledger's own declared row-count — matching, mismatched, a dated
          historical count (never a finding, BP-077 clause 4), a claim line
          that goes missing (a finding, not silence), and the real specs
          against the real tree today.

No DUT, no serial port, no build, no network, no git.
Run: python3 app/tools/gate/test_check_board_currency.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _case_runner  # noqa: E402

import check_board_currency as C                          # noqa: E402

BOARD = "docs/project/tasks-fixture.md"


def board(*lines, rel: str = BOARD) -> list:
    """Parse literal board text — the real parser, not a hand-built Row."""
    return C.parse_board(rel, "\n".join(lines))


def row(tid: str, status: str, title: str = "a title", pri: str = "P2") -> str:
    return f"| TASK-{tid} | {pri} | {status} | {title} |"


def one(fs, needle):
    hits = [f for f in fs if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {fs}"
    return hits


def none(fs):
    assert not fs, f"expected no findings, got {fs}"


def only(fs, cid):
    """Exactly the findings of one check, and no others."""
    others = [f for f in fs if not f.startswith(cid)]
    assert not others, f"expected only {cid} findings, also got {others}"
    assert fs, f"expected at least one {cid} finding"


# ── N1-N3: one arm per check ─────────────────────────────────────────────────

def case_b1_open_row_with_a_commit():
    """The row says nothing landed; a commit subject says otherwise."""
    rows = board(row("101", "OPEN — @Developer"))
    fs = C.evaluate(rows, {"101": ["deadbee"]})
    only(fs, "B1")
    one(fs, "TASK-101")
    one(fs, "`deadbee`")


def case_b1_fires_for_blocked_too():
    """BLOCKED is the other half of B1's set — the audit's rows read BLOCKED,
    not OPEN, so an arm written only against OPEN would have missed all of it."""
    only(C.evaluate(board(row("101", "BLOCKED — TASK-999")), {"101": ["deadbee"]}), "B1")


def case_b2_closed_row_with_no_hash():
    rows = board(row("102", "**DONE 2026-09-07**"))
    fs = C.evaluate(rows, {})
    only(fs, "B2")
    one(fs, "no commit subject names this id either")


def case_b2_names_the_candidate_hash_when_the_log_has_one():
    """The finding must be actionable: if the log offers a hash, say which."""
    one(C.evaluate(board(row("102", "**DONE**")), {"102": ["cafe123"]}), "`cafe123`")


def case_b2_fires_on_each_closed_word():
    for word in C.CLOSED_STATUSES:
        only(C.evaluate(board(row("102", f"**{word} 2026-09-07**")), {}), "B2")


def case_b3_blocked_on_a_closed_task():
    rows = board(row("103", "BLOCKED — TASK-104"),
                 row("104", "**DONE 2026-09-06** (`abc1234`)"))
    fs = C.evaluate(rows, {})
    only(fs, "B3")
    one(fs, "TASK-103 reads BLOCKED on TASK-104")


def case_b3_accepts_the_blocked_on_form_too():
    """Both spellings occur live: `BLOCKED — TASK-X` and `BLOCKED on TASK-X`."""
    rows = board(row("103", "OPEN — @VE · BLOCKED on TASK-104"),
                 row("104", "**DONE** (`abc1234`)"))
    only(C.evaluate(rows, {}), "B3")


def case_b3_fires_on_ruled_and_resolved_predecessors():
    """B3's closed set is deliberately WIDER than B2's: a RULED predecessor is
    just as gone as a DONE one, and rulings are named as entry criteria here."""
    for word in ("RULED", "RESOLVED"):
        rows = board(row("103", "BLOCKED — TASK-104"),
                     row("104", f"**{word} 2026-09-03**"))
        one(C.evaluate(rows, {}), f"which reads {word}")


# ── C1-C3: the controls that must not flag ───────────────────────────────────

def case_control_partial_row_with_a_commit():
    """C1. PARTIAL is the visible author declaration B1 accepts."""
    none(C.evaluate(board(row("201", "**PARTIAL 2026-09-02 — rung 2 done**")),
                    {"201": ["deadbee", "f00ba12"]}))


def case_control_done_row_citing_a_hash():
    """C2. The shape BP-069 asks for, and the shape B2 must never punish."""
    none(C.evaluate(board(row("202", "**DONE 2026-09-07** (`f66a4d2`)")), {}))


def case_control_blocked_on_a_genuinely_open_task():
    """C3. The whole point of B3 is that it distinguishes a live constraint from
    a dead one. A gate that flagged this would make every blocked row a failure
    and would be switched off inside a week."""
    rows = board(row("203", "BLOCKED — TASK-204"),
                 row("204", "OPEN — @Developer"))
    none(C.evaluate(rows, {}))


def case_control_blocked_on_a_task_with_no_row_at_all():
    """A predecessor on a board this run did not read resolves to nothing, and
    an unresolvable id is not evidence of a closure. Fail QUIET, not loud."""
    none(C.evaluate(board(row("203", "BLOCKED — TASK-9999")), {}))


def case_control_open_row_with_no_commits_is_silent():
    none(C.evaluate(board(row("205", "OPEN — @VE")), {}))


# ── E1-E2: the escapes are narrow ────────────────────────────────────────────

def case_partial_does_not_excuse_b2():
    """An escape excuses its own check only. This is a live row shape —
    `**DONE 2026-09-01 — host-tested; DUT verification PARTIAL**` — and the word
    PARTIAL in it must not buy the row out of citing where it landed."""
    only(C.evaluate(board(row("301", "**DONE 2026-09-01 — host-tested; "
                                     "DUT verification PARTIAL**")), {}), "B2")


def case_a_leading_partial_is_unclassified_for_b2():
    """The other side of the same coin, asserted so it is a decision and not a
    surprise: `**PARTIAL DONE ...**` has PARTIAL as its leading token, so it is
    outside B2's vocabulary entirely and owes no hash. Limit 6. Widening B2 to
    reach it would mean deciding what a partial closure means, which is the
    author's call and not this gate's."""
    none(C.evaluate(board(row("306", "**PARTIAL DONE 2026-09-02 — inert landing**")), {}))


def case_docs_marker_does_not_excuse_b1():
    """(docs) is B2's escape. It must not silence B1."""
    only(C.evaluate(board(row("302", "OPEN — @PM (docs)")), {"302": ["deadbee"]}), "B1")


def case_docs_marker_satisfies_b2():
    none(C.evaluate(board(row("303", "**DONE 2026-09-04** — five rulings (docs)")), {}))


def case_hash_may_be_cited_in_the_title_not_only_the_status():
    """Live rows cite the hash in either cell; B2 reads the whole row."""
    none(C.evaluate(board(row("304", "**DONE**", "landed in `8927b16`")), {}))


def case_unbackticked_hex_is_not_a_citation():
    """`deadbee` in prose is a word. Requiring backticks is what stops B2 from
    being satisfied by an accident of vocabulary."""
    only(C.evaluate(board(row("305", "**DONE**", "the deadbeef path was removed")), {}), "B2")


# ── L1-L5: the ledger ────────────────────────────────────────────────────────

def case_ledger_suppresses_exactly_its_key():
    """One row, one finding. Not the same id on another board, not another
    check on the same id."""
    rows = board(row("401", "OPEN"), rel=BOARD) + board(row("401", "OPEN"),
                                                        rel="docs/project/tasks-other.md")
    ledger = {("stale-open", BOARD, "TASK-401"): "ledger:9"}
    fs = C.evaluate(rows, {"401": ["deadbee"]}, ledger)
    only(fs, "B1")
    one(fs, "tasks-other.md")


def case_ledger_kind_is_not_interchangeable():
    """A stale-open exemption must not excuse an uncited closure."""
    ledger = {("stale-open", BOARD, "TASK-402"): "ledger:9"}
    fs = C.evaluate(board(row("402", "**DONE**")), {}, ledger)
    one(fs, "B2 ")
    # and the mis-kinded row is itself reported as stale, so it cannot sit there
    one(fs, "B4 ")


def case_stale_ledger_row_is_a_failure():
    """B4 — the clause that makes the list shrink-only. The row was fixed; the
    exemption must now go."""
    ledger = {("stale-open", BOARD, "TASK-403"): "ledger:9"}
    fs = C.evaluate(board(row("403", "**DONE** (`abc1234`)")), {"403": ["abc1234"]}, ledger)
    only(fs, "B4")
    one(fs, "The ledger can only shrink")


def case_stale_fires_when_the_row_is_deleted_entirely():
    ledger = {("stale-open", BOARD, "TASK-404"): "ledger:9"}
    only(C.evaluate([], {}, ledger), "B4")


def case_malformed_ledger_rows_are_errors():
    text = "\n".join([
        "| board | row | kind | why | owner | since |",
        "|---|---|---|---|---|---|",
        f"| `{BOARD}` | `TASK-501` | not-a-kind | why | TASK-669 | 2026-09-07 |",
        f"| `{BOARD}` | `line 42` | stale-open | why | TASK-669 | 2026-09-07 |",
        f"| `{BOARD}` | `TASK-503` | stale-open | why | @PM | 2026-09-07 |",
        f"| `{BOARD}` | `TASK-504` | stale-open | why | TASK-669 | last tuesday |",
        f"| `{BOARD}` | `TASK-505` | stale-open |",
    ])
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "led.md")
        Path(p).write_text(text, encoding="utf-8")
        rows, errors = C.parse_ledger(p)
    assert not rows, f"no malformed row may be admitted, got {rows}"
    for needle in ("not exemptable", "keyed on the row's own TASK- id",
                   "must be a TASK-NNN id", "ISO YYYY-MM-DD", "needs 6"):
        one(errors, needle)


def case_prose_tables_in_the_ledger_header_are_not_rows():
    """The ledger file carries explanatory tables. They must not parse as
    exemptions, and must not be reported as malformed ones either."""
    text = "\n".join([
        "| check | findings | note |",
        "|---|---|---|",
        "| **B1** stale-open | 4 | all four on one board |",
        "",
        "| board | row | kind | why | owner | since |",
        "|---|---|---|---|---|---|",
        f"| `{BOARD}` | `TASK-601` | stale-open | why | TASK-669 | 2026-09-07 |",
    ])
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "led.md")
        Path(p).write_text(text, encoding="utf-8")
        rows, errors = C.parse_ledger(p)
    none(errors)
    assert list(rows) == [("stale-open", BOARD, "TASK-601")], rows


def case_absent_ledger_is_not_a_crash_and_grandfathers_nothing():
    with tempfile.TemporaryDirectory() as d:
        rows, errors = C.parse_ledger(os.path.join(d, "nope.md"))
    assert rows == {} and errors == []
    only(C.evaluate(board(row("601", "OPEN")), {"601": ["deadbee"]}, rows), "B1")


# ── M1-M2: the mutation arms, from this week's real defects ──────────────────
#
# Literal rows from docs/project/tasks-harness2.md at 0dba35a^, so the arm
# fails if the gate ever stops catching the thing it was built for. The commit
# list is injected, not read from git.

PRE_AUDIT_ROWS = [
    "| TASK-633 | P1 | **DONE 2026-09-06** — 14 entry points + `lib.sh` | verify-and-refuse |",
    "| TASK-634 | P1 | BLOCKED — TASK-633 | run the 80-minute session and file its dated records |",
    "| TASK-579 | P1 | BLOCKED — TASK-634 | the WebRadio forced-connect-fail injector nothing clears |",
    "| TASK-580 | P1 | BLOCKED — TASK-634 | the heatmap injector wedges the sub-view |",
    "| TASK-624 | P1 | **DONE 2026-09-04** (`8927b16`) | closed verdict enum incl. `UNMET` |",
    "| TASK-588 | P2 | BLOCKED — TASK-624 | a second unblocked row |",
    "| TASK-597 | P2 | BLOCKED — TASK-624 | a third unblocked row |",
]


def case_mutation_b3_reconstructs_the_audits_structural_defect():
    """`TASK-634` read `BLOCKED — TASK-633` while TASK-633 was already DONE —
    the audit's headline: a cold session reads that, sees the predecessor
    closed, and starts work that is still blocked. TASK-588/597 are the
    "silently unblocked for days" half of the same finding."""
    rows = C.parse_board("docs/project/tasks-harness2.md", "\n".join(PRE_AUDIT_ROWS))
    fs = C.evaluate(rows, {})
    hits = [f for f in fs if f.startswith("B3")]
    ids = sorted(f.split("TASK-")[1].split(" ")[0] for f in hits)
    assert ids == ["588", "597", "634"], ids
    one(fs, "TASK-634 reads BLOCKED on TASK-633, which reads DONE")


def case_mutation_b3_is_silent_on_the_reconciled_row():
    """The fix `0dba35a` wrote names the live constraint and then explains the
    old one in the same cell. B3 must read the FIRST id after the marker, or it
    fires on the correction and the gate teaches people not to write it."""
    fixed = ("| TASK-635 | P2 | BLOCKED — **phase entry (TASK-557)**; its row "
             "predecessor TASK-608 is DONE | a row |")
    rows = C.parse_board("docs/project/tasks-harness2.md", "\n".join([
        fixed,
        "| TASK-557 | P1 | **MECHANISM MEASURED 2026-09-02** | the supply sag |",
        "| TASK-608 | P3 | **DONE 2026-09-05** (`abc1234`) | the run artifact |",
    ]))
    none([f for f in C.evaluate(rows, {}) if f.startswith("B3")])


def case_mutation_b1_reconstructs_a_real_stale_open_row():
    """`TASK-573` still reads OPEN on tasks-architecture.md while `2a43a11`
    "fix(TASK-573): player-gate dropped FLAKY-PASS ..." landed the fix. One of
    the four findings this gate produced on its first live run."""
    rows = C.parse_board("docs/project/tasks-architecture.md", "\n".join([
        "| TASK-573 | P2 | **OPEN — filed 2026-09-01 by @PM** | player-gate phantom regression |",
    ]))
    fs = C.evaluate(rows, {"573": ["2a43a11", "f449d9f"]})
    only(fs, "B1")
    one(fs, "2 commit subject(s) name it")


def case_mutation_b1_would_not_have_caught_task_634():
    """THE LIMIT, PINNED. The two hardware-session commits are `d3a3600`
    "test(phase 2): ..." and `f66a4d2` "fix(phase 2B): ..." — neither names a
    task id, so the commit index has no entry for 634 and B1 is blind to it.
    This arm exists so the docstring's most important sentence cannot quietly
    stop being true: if someone widens the index to commit bodies, this fails
    and the claim gets rewritten rather than left standing."""
    idx = C.index_commits([
        ("d3a3600", "test(phase 2): the first hardware session — two clusters confirmed"),
        ("f66a4d2", "fix(phase 2B): both confirmed clusters fixed on hardware; 36 of 58"),
    ])
    assert idx == {}, f"expected no ids from these subjects, got {idx}"
    rows = C.parse_board("docs/project/tasks-harness2.md",
                         "| TASK-634 | P1 | BLOCKED — TASK-633 | run the session |")
    none([f for f in C.evaluate(rows, idx) if f.startswith("B1")])


# ── P1-P3: parser properties the checks depend on ────────────────────────────

def case_status_is_the_leading_token_not_a_substring():
    """`**UNBLOCKED**` is not BLOCKED, and a DONE row narrating "opening the
    port" is not OPEN. The first prototype of this gate produced three false B1
    findings on exactly these two rows."""
    rows = board(row("701", "**UNBLOCKED** (454 verified)"),
                 row("702", "**DONE 2026-09-01 — the harness has been opening the "
                            "port inside its own reset window** (`f5d3d07`)"))
    none(C.evaluate(rows, {"701": ["deadbee"], "702": ["f5d3d07"]}))


def case_a_closed_predecessor_named_in_a_done_rows_prose_is_not_b2():
    """A reconciled BLOCKED row narrates "predecessor TASK-602 is DONE" inside
    its status cell. Reading the closed vocabulary anywhere in the cell — the
    prototype's other bug — turned nine such rows into phantom B2 findings."""
    rows = board(row("703", "BLOCKED — **phase entry (TASK-557)**; its row "
                            "predecessor TASK-602 is DONE"))
    none([f for f in C.evaluate(rows, {}) if f.startswith("B2")])


def case_unclassified_statuses_are_out_of_scope():
    """SKELETON, MECHANISM MEASURED, DEFERRED, PHASES — real statuses on these
    boards that fall into none of the three sets. Silence is the documented
    behaviour (limit 6); this arm makes it a decision rather than an accident."""
    rows = board(row("704", "SKELETON"), row("705", "**DEFERRED — after TASK-566**"),
                 row("706", "**MECHANISM MEASURED 2026-09-02**"))
    none(C.evaluate(rows, {"704": ["a"], "705": ["b"], "706": ["c"]}))


def case_bold_wrapped_ids_and_non_row_lines_parse_correctly():
    text = "\n".join([
        "some prose naming TASK-801 that is not a row",
        "| task | pri | status | title |",
        "|---|---|---|---|",
        "| **TASK-802** | P1 | OPEN | a bold id |",
        "| T_PLR_13 | P1 | OPEN | not a task row |",
    ])
    rows = C.parse_board(BOARD, text)
    assert [r.tid for r in rows] == ["802"], [r.tid for r in rows]


def case_index_reads_subjects_and_orders_newest_first():
    """`feat(TASK-633/587): ...` is a live subject on this project — the slash
    list is one commit landing several ids and every one of them is indexed."""
    idx = C.index_commits([("aaa1111", "feat(TASK-900): a thing"),
                           ("bbb2222", "fix(TASK-900/901/902): three things")])
    assert idx == {"900": ["aaa1111", "bbb2222"],
                   "901": ["bbb2222"], "902": ["bbb2222"]}, idx


def case_index_does_not_expand_a_range():
    """`TASK-579..643` on a board-filing commit must tag 579 and nothing else.
    Expanding it would hand B1 sixty-five findings that name no work."""
    idx = C.index_commits([("9193467", "docs(PM): land the harness programme "
                                       "as its own board — TASK-579..643")])
    assert idx == {"579": ["9193467"]}, idx


def case_board_corpus_excludes_the_archive_and_is_discovered():
    """The corpus is a glob, never a hand-written tuple — ROWLEN's TASK-647
    lesson, where a board created on 2026-09-03 went unscanned for two days."""
    files = C.board_files()
    assert files, "the board glob found nothing"
    assert all("tasks-archive.md" not in f for f in files), files
    assert "docs/project/tasks-harness2.md" in files, files


# ── B5: the "Next free id" claim ────────────────────────────────────────────

def case_b5_correct_claim_passes():
    """max in use is 100 (a doc) and 102 (a commit) -> 103 is correct, no finding."""
    claims = {"docs/project/tasks-fixture.md":
              "prose. **Next free id: TASK-103.** more prose naming TASK-100."}
    corpus = [claims["docs/project/tasks-fixture.md"], "fix(TASK-102): a thing"]
    fs = C.evaluate_next_free(claims, corpus)
    none(fs)


def case_b5_off_by_one_is_a_finding():
    claims = {"docs/project/tasks-fixture.md":
              "prose naming TASK-100.\n**Next free id: TASK-102.**"}
    fs = C.evaluate_next_free(claims, list(claims.values()))
    only(fs, "B5")
    one(fs, "TASK-102")
    one(fs, "TASK-101")  # the correct claim


def case_b5_self_reference_does_not_make_the_claim_agree_with_itself():
    """THE TRAP. A lone claim naming a number far above every real id in use
    must still be flagged — the claim line's own token must not count as
    evidence that the number is correct. Real ids top out at 100; the claim
    says 9000 and would "agree with itself" if the scanner read its own line
    like any other."""
    claims = {"docs/project/tasks-fixture.md":
              "prose naming TASK-100.\n**Next free id: TASK-9000.**"}
    fs = C.evaluate_next_free(claims, list(claims.values()))
    only(fs, "B5")
    one(fs, "TASK-101")  # the correct claim, derived from the real max (100), not 9000


def case_b5_same_line_stale_history_does_not_leak_back_in():
    """`tasks-harness2.md`'s real claim line narrates its OWN former stale value
    ("...until then... TASK-685...") on the SAME line as the current claim.
    That mention must not count as a live id in use either — the whole line is
    dropped, not just the claimed token. (A real, unrelated id — TASK-99 — sits
    on a separate line so the corpus is not simply empty.)"""
    claims = {"docs/project/tasks-fixture.md":
              "prose naming TASK-99.\n"
              "**Next free id: TASK-100.** This line read TASK-685 until fixed."}
    fs = C.evaluate_next_free(claims, list(claims.values()))
    none(fs)  # if TASK-685 leaked in, expected would jump to 686 and this would fire


def case_b5_reads_across_boards_and_the_corpus_separately():
    """The claim can live on one board while the highest id in use lives on
    another (or in the commit log) — corpus_texts is the union, claim_sources
    is just where claims are looked for."""
    claims = {"docs/project/tasks-fixture.md": "**Next free id: TASK-501.**"}
    corpus = ["docs/project/tasks-other.md text naming TASK-500."]
    fs = C.evaluate_next_free(claims, corpus)
    none(fs)


def case_find_next_free_claims_accepts_both_wordings():
    assert C.find_next_free_claims("f", "**Next free id: TASK-5.**")[0][1] == 5
    assert C.find_next_free_claims("f", "**Next free task id: TASK-7**")[0][1] == 7
    assert C.find_next_free_claims("f", "no claim on this line") == []


# ── B6: a ledger's declared row count ───────────────────────────────────────

def _spec(path, claim_pat, row_pat):
    import re
    return {"path": path,
            "claim_re": re.compile(claim_pat, re.M),
            "row_re": re.compile(row_pat, re.M)}


def case_b6_matching_count_passes():
    spec = _spec("docs/verification/fixture-ledger.md",
                 r"^\*\*(\d+) rows\*\*", r"^\| `T\d+` \| kind \|")
    text = "\n".join(["| `T1` | kind |", "| `T2` | kind |", "**2 rows**"])
    fs = C.evaluate_ledger_counts([spec], {spec["path"]: text})
    none(fs)


def case_b6_mismatched_count_fails():
    spec = _spec("docs/verification/fixture-ledger.md",
                 r"^\*\*(\d+) rows\*\*", r"^\| `T\d+` \| kind \|")
    text = "\n".join(["| `T1` | kind |", "**2 rows**"])
    fs = C.evaluate_ledger_counts([spec], {spec["path"]: text})
    only(fs, "B6")
    one(fs, "declares **2 rows**")
    one(fs, "holds 1")


def case_b6_a_dated_historical_count_is_not_a_finding_because_it_has_no_spec():
    """BP-077 clause 4: a dated measurement ('9 rows at the first recording,
    2026-09-09') is evidence, not a live claim, and must never be flagged.
    LEDGER_COUNT_SPECS's claim_re is anchored to each file's present-tense
    wording precisely so a dated sentence like this one never matches it —
    proven here on the real specs, not a fixture, so a future spec that
    widens the regex to also catch dated text is the thing this pins against."""
    text = ("The first recording, 2026-09-09, put **9 rows** on this ledger; "
            "T204 was later removed and none of the historical counts changed.")
    for spec in C.LEDGER_COUNT_SPECS:
        assert not spec["claim_re"].search(text), (
            f"{spec['path']}'s claim_re matched a DATED historical sentence — "
            f"it would flag evidence as a finding")


def case_b6_missing_claim_line_is_itself_a_finding():
    """If a doc rewrite drops or reword the declared-count line, the check must
    not go silently blind — it must say so, not print PASS forever."""
    spec = _spec("docs/verification/fixture-ledger.md",
                 r"^\*\*(\d+) rows\*\* \(as of", r"^\| `T\d+` \| kind \|")
    text = "| `T1` | kind |\nno declared count here at all"
    fs = C.evaluate_ledger_counts([spec], {spec["path"]: text})
    only(fs, "B6")
    one(fs, "found none")


def case_b6_absent_path_is_silent():
    spec = _spec("docs/verification/fixture-ledger.md", r"^\*\*(\d+) rows\*\*", r"^\| `T\d+` \|")
    none(C.evaluate_ledger_counts([spec], {}))


def case_b6_real_specs_currently_agree_with_the_tree():
    """Not a fixture: reads the real repo files the four ledgers this task
    named live at, and asserts the two with a live, unambiguous, present-tense
    declared count (`can_go_red_ledger.md`, `id_binding_exceptions.md`)
    currently match. `unrestored_mutations_ratchet.md`'s '14 rows' and
    board_currency_exceptions.md's '68'/'0' are dated ('Opened ...', 'Opening
    size, measured ...') and are deliberately NOT in LEDGER_COUNT_SPECS at all
    — see the spec table's own docstring."""
    texts = {}
    for spec in C.LEDGER_COUNT_SPECS:
        full = os.path.join(C.ROOT, spec["path"])
        if not os.path.exists(full):
            continue
        with open(full, encoding="utf-8", errors="replace") as fh:
            texts[spec["path"]] = fh.read()
    none(C.evaluate_ledger_counts(C.LEDGER_COUNT_SPECS, texts))


def case_b5_a_body_quoting_the_gate_cannot_poison_the_corpus():
    """B5g (TASK-716, found by dogfooding on the day it landed).

    The gate prints "expected TASK-NNN". A commit message that QUOTES that
    line — as this gate's own landing commit did — put `TASK-717` into the
    git corpus while no such id was allocated, and a body-wide scan read it
    back as evidence. The claim then demanded 718 for an id nobody held.

    Self-reference one level out from the claim-line trap: the claim line is
    excluded, but anything that can quote the gate could still poison it.
    The corpus is therefore ALLOCATION evidence only — board rows and commit
    SUBJECTS — and this pins that a body-shaped mention is inert.
    """
    board = "| TASK-100 | P2 | DONE | a row |\n**Next free id: TASK-101**\n"
    poison = ("feat(TASK-100): land it\n\n"
              "check_board_currency: 2 claims expected TASK-717\n")
    # Allocation evidence: the board row + a subject. The poisoning line is a
    # BODY line and must never reach max_task_id().
    corpus = [board, "feat(TASK-100): land it"]
    none(C.evaluate_next_free({"docs/project/tasks.md": board}, corpus))
    # And the proof that it would have broken: feed the body in as if it were
    # corpus text, the way the first implementation did.
    one(C.evaluate_next_free({"docs/project/tasks.md": board},
                             corpus + [poison]), "TASK-718")


CASES = [
    ("N1a B1 fires on an OPEN row with a commit", case_b1_open_row_with_a_commit),
    ("N1b B1 fires on BLOCKED too", case_b1_fires_for_blocked_too),
    ("N2a B2 fires on a closed row with no hash", case_b2_closed_row_with_no_hash),
    ("N2b B2 names the candidate hash", case_b2_names_the_candidate_hash_when_the_log_has_one),
    ("N2c B2 fires on each closed word", case_b2_fires_on_each_closed_word),
    ("N3a B3 fires on a closed predecessor", case_b3_blocked_on_a_closed_task),
    ("N3b B3 accepts 'BLOCKED on TASK-X'", case_b3_accepts_the_blocked_on_form_too),
    ("N3c B3 counts RULED/RESOLVED as closed", case_b3_fires_on_ruled_and_resolved_predecessors),
    ("C1  PARTIAL + a commit does not flag", case_control_partial_row_with_a_commit),
    ("C2  DONE citing a hash does not flag", case_control_done_row_citing_a_hash),
    ("C3  blocked on a genuinely open task", case_control_blocked_on_a_genuinely_open_task),
    ("C3b blocker with no row resolves quiet", case_control_blocked_on_a_task_with_no_row_at_all),
    ("C4  OPEN with no commits is silent", case_control_open_row_with_no_commits_is_silent),
    ("E1a PARTIAL does not excuse B2", case_partial_does_not_excuse_b2),
    ("E1c a leading PARTIAL is unclassified", case_a_leading_partial_is_unclassified_for_b2),
    ("E1b (docs) does not excuse B1", case_docs_marker_does_not_excuse_b1),
    ("E2a (docs) satisfies B2", case_docs_marker_satisfies_b2),
    ("E2b a hash in the title counts", case_hash_may_be_cited_in_the_title_not_only_the_status),
    ("E2c unbackticked hex is not a citation", case_unbackticked_hex_is_not_a_citation),
    ("L1  the ledger suppresses one key only", case_ledger_suppresses_exactly_its_key),
    ("L1b kinds are not interchangeable", case_ledger_kind_is_not_interchangeable),
    ("L2  a stale row is a failure", case_stale_ledger_row_is_a_failure),
    ("L2b stale on a deleted row too", case_stale_fires_when_the_row_is_deleted_entirely),
    ("L3  malformed rows are errors", case_malformed_ledger_rows_are_errors),
    ("L4  prose tables are not exemptions", case_prose_tables_in_the_ledger_header_are_not_rows),
    ("L5  an absent ledger fails CLOSED", case_absent_ledger_is_not_a_crash_and_grandfathers_nothing),
    ("M1  B3 reconstructs the real defect", case_mutation_b3_reconstructs_the_audits_structural_defect),
    ("M1b B3 is silent on the correction", case_mutation_b3_is_silent_on_the_reconciled_row),
    ("M2  B1 reconstructs a real stale row", case_mutation_b1_reconstructs_a_real_stale_open_row),
    ("M2b the pinned limit: B1 missed 634", case_mutation_b1_would_not_have_caught_task_634),
    ("P1  status is a token, not a substring", case_status_is_the_leading_token_not_a_substring),
    ("P1b closed words in prose are not B2", case_a_closed_predecessor_named_in_a_done_rows_prose_is_not_b2),
    ("P2  unclassified statuses are silent", case_unclassified_statuses_are_out_of_scope),
    ("P2b bold ids parse, non-rows do not", case_bold_wrapped_ids_and_non_row_lines_parse_correctly),
    ("P3  the index reads subjects only", case_index_reads_subjects_and_orders_newest_first),
    ("P3c a range is not expanded", case_index_does_not_expand_a_range),
    ("P3b the corpus is discovered", case_board_corpus_excludes_the_archive_and_is_discovered),
    ("B5a a correct claim passes", case_b5_correct_claim_passes),
    ("B5b an off-by-one claim is a finding", case_b5_off_by_one_is_a_finding),
    ("B5c THE TRAP: self-reference does not self-agree",
     case_b5_self_reference_does_not_make_the_claim_agree_with_itself),
    ("B5d same-line stale history does not leak in",
     case_b5_same_line_stale_history_does_not_leak_back_in),
    ("B5e claim and corpus are read separately",
     case_b5_reads_across_boards_and_the_corpus_separately),
    ("B5f both claim wordings parse", case_find_next_free_claims_accepts_both_wordings),
    ("B5g a body quoting the gate cannot poison the corpus",
     case_b5_a_body_quoting_the_gate_cannot_poison_the_corpus),
    ("B6a a matching declared count passes", case_b6_matching_count_passes),
    ("B6b a mismatched declared count fails", case_b6_mismatched_count_fails),
    ("B6c a dated historical count is never a finding",
     case_b6_a_dated_historical_count_is_not_a_finding_because_it_has_no_spec),
    ("B6d a missing claim line is a finding, not silence",
     case_b6_missing_claim_line_is_itself_a_finding),
    ("B6e an absent spec path is silent", case_b6_absent_path_is_silent),
    ("B6f the real ledgers agree with the tree today",
     case_b6_real_specs_currently_agree_with_the_tree),
]


def main() -> int:
    return _case_runner.run_cases("test_check_board_currency", CASES)


if __name__ == "__main__":
    sys.exit(main())
