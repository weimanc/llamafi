#!/usr/bin/env python3
"""check_board_currency.py — the record must not lag the work. TASK-669.

THE MEASURED FAILURE. The PM audit of 2026-09-07 (`0dba35a`) found that the
record lags the work by **exactly one session, every time**: `TASK-634` read
BLOCKED while the session it describes had landed twice; `TASK-579`/`580` read
BLOCKED though both were confirmed and fixed on hardware; `TASK-581` read BLOCKED
and was in fact REFUTED; `TASK-588`/`595`/`597` had been silently unblocked for
days; and **seven Phase 3/5 rows named a `BLOCKED — TASK-X` predecessor that had
since closed**, so a cold session reading only the boards would have started work
that is still blocked, or re-run an 80-minute hardware session whose results were
already written down.

Every one of those was found by a human reading two boards side by side, four
days late. None of them is a judgement call. All of them are mechanically
detectable from two inputs that **the row's own author does not control**: the
boards, and `git log`. That is the project's own evidence about what survives —
`LL-127` sat open for a year while the defect it named was misattributed, and
`check_docs` C3 was advisory long enough to grow — against ROWLEN, C6,
`golden.sha256` and the flake registry's expiry, which hold because each reads a
fact the declarer cannot edit. This gate is built to that constraint and to no
other.

WHAT IT ASSERTS
---------------

  B1  a row reads OPEN or BLOCKED while a **commit subject names its id**.
      Something landed under that id and the row still says nothing has. The
      subject line is used because `feat(TASK-566): ...` is this project's
      standing convention, so the signal is already there to be read.

  B2  a row reads DONE / CLOSED / FIXED / LANDED and **cites no commit hash**.
      BP-069 already says a row is a pointer — id, priority, status, a one-line
      title, a design-doc link, **a commit hash**. B2 is the half of BP-069 that
      was never enforced: a closed row with no hash is a claim with no address,
      and the next reader cannot check it without re-deriving the whole session.

  B3  a row reads `BLOCKED — TASK-X` (or `BLOCKED on TASK-X`) where **X resolves
      to a closed status**. This is the audit's structural finding, not its
      staleness finding: the row is not merely out of date, it actively
      misdirects, because the named constraint is gone and the real one — a
      phase entry, usually — is unnamed. Nine rows on the pre-audit tree.

  B4  a ledger row whose finding no longer occurs. The clause that makes the
      exception list shrink-only, lifted verbatim from ROWLEN and C6.

THE ESCAPES, AND WHY THERE ARE ONLY TWO
---------------------------------------

  `PARTIAL` anywhere in the status cell satisfies B1. "Landed, not finished" is
  a real and common state on this board — `TASK-566` is the standing example —
  and B1's whole complaint is that the row is silent about a commit that exists.
  A row that says PARTIAL is not silent. It is an **explicit, visible author
  declaration**, which is the point: the escape costs a word on the board where
  the next reader will see it, not a line in a config file where nobody will.

  `(docs)` anywhere in the row satisfies B2. Some work closes in a document, not
  in code — a ruling, an adjudication, a disposition — and there is no hash to
  cite because there is nothing to cite it *for*. `TASK-616`/`617`/`618` are
  rulings; `TASK-644` is five specification gaps closed in the documents that own
  them. Demanding a hash there would make the honest row the failing one, which
  is exactly the trap `check_docs` C3 died of.

  **Nothing else, deliberately.** If a third escape looks necessary, that is a
  finding about the rule and belongs in front of @QM as one — not in this file.

WHAT THIS GATE CANNOT SEE. Read this before quoting a green result.
-------------------------------------------------------------------

  1. **It reads ids in commit SUBJECTS only.** A body-only `TASK-NNN` is
     invisible. This is not a corner case here: the two hardware sessions the
     audit was written about are `d3a3600` "test(phase 2): the first hardware
     session ..." and `f66a4d2` "fix(phase 2B): both confirmed clusters fixed on
     hardware", and **neither names a task id at all**. B1 would not have caught
     `TASK-634`. That is the single most important sentence in this docstring:
     the gate is downstream of a convention, and where the convention lapses the
     gate is blind. B3 caught those rows instead, which is why there are three
     checks and not one.

  2. **It knows something LANDED under an id. It never knows the work is
     FINISHED.** `9193467` "docs(PM): land the harness programme as its own
     board — TASK-579..643" names `TASK-579` in its subject and is a board-filing
     commit, not the work. B1 fires on it. The finding is still worth having —
     it says "this id has commit traffic and your row says otherwise, reconcile
     it" — but a B1 hit is a **prompt to look**, never a verdict that the task is
     done, and it must never be auto-closed on.

  3. **It cannot see work that was done but not committed.** The failure mode
     the audit actually names — a thorough review written, no board touched —
     is invisible until the review lands in a commit. A row that is stale in the
     working tree, or stale against a review sitting in a chat log, reads green
     here.

  4. **It cannot see a finding nobody filed.** The audit's seven hardware
     findings (`TASK-662`..`668`) sat unfiled in a review's "for @PM" list. There
     was no row for them to be stale *against*. No gate over the boards can see
     an absent row; that half of the rule is a human obligation and stays one.

  5. **B2 checks CITATION, not truth.** A backticked hex string satisfies it. A
     wrong hash, or one from another repo, passes.

  6. **Status is read as the first ALL-CAPS token of the status cell.** Rows
     whose status is prose (`SKELETON`, `UNBLOCKED`, `MECHANISM MEASURED`) fall
     into none of the three sets and are silently out of scope. That is
     deliberate — inventing a status vocabulary the boards do not use would make
     the gate the author of the record rather than a reader of it — but it means
     the counts below are of *classified* rows, not of all rows.

A reader must not take a PASS here as "the board is true". It is "the board does
not contradict the commit log in the three ways this file names".

LANDING. B1 and B3 land BLOCKING. B3 reads **0** on the post-`0dba35a` tree and
9 on the tree before it, so the PM's reconciliation is what put it at zero and
this gate is what keeps it there. B1 reads **4**, all on
`tasks-architecture.md` — the one board the reconciliation did not touch — and
all four are ledgered with the hash the gate found, so they are named and dated
rather than pending. B2 reads **68** of 124 classified closed rows: far too many
to clear in the commit that lands the gate, so it opens on the same dated,
shrink-only ledger ROWLEN uses, on the same bargain (an advisory count is
scrolled past; a ledger row that stops failing is itself a failure).

No DUT, no build, no network. Sub-second plus one `git log`.

    python3 app/tools/gate/check_board_currency.py [--verbose]
"""

from __future__ import annotations

import argparse
import datetime
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

# ── Corpus ───────────────────────────────────────────────────────────────────
# The same glob ROWLEN uses, for the same reason it was changed to a glob
# (TASK-647 D1): tasks-harness2.md was created 2026-09-03 and a hardcoded tuple
# never saw a line of it. A board is in scope the day it is created.
BOARD_GLOB = "docs/project/tasks*.md"
BOARD_EXEMPT = {"tasks-archive.md"}

LEDGER_REL = "docs/project/board_currency_exceptions.md"

ROW_RE = re.compile(r"^\|\s*\*{0,2}TASK-(\d+)\*{0,2}\s*\|")
#: The declared status is the FIRST all-caps token in the status cell. See
#: limit 6 — prose statuses classify as nothing and are out of scope.
STATUS_TOKEN_RE = re.compile(r"[A-Z][A-Z-]{2,}")
#: A backticked short hash. Bare hex is NOT accepted: an unbackticked 7-char
#: word is far more often a word than a commit.
HASH_RE = re.compile(r"`[0-9a-f]{7,40}`")
PARTIAL_RE = re.compile(r"\bPARTIAL\b")
DOCS_MARKER = "(docs)"
#: `BLOCKED — TASK-X` / `BLOCKED on TASK-X`. The FIRST id within a short window
#: after the marker is the blocker. That window matters: the reconciled rows
#: read `BLOCKED — **phase entry (TASK-557)**; its row predecessor TASK-608 is
#: DONE`, where TASK-557 is the live constraint and TASK-608 is prose ABOUT the
#: defect this check found. A regex that swept the whole cell would fire on the
#: correction.
BLOCKER_RE = re.compile(r"BLOCKED\b[^|]{0,40}?TASK-(\d+)")
TASK_ID_RE = re.compile(r"^TASK-\d+$")
SEP_RE = re.compile(r":?-{2,}:?")

OPEN_STATUSES = ("OPEN", "BLOCKED")
#: B2's set, exactly as specified. Kept narrow on purpose.
CLOSED_STATUSES = ("DONE", "CLOSED", "FIXED", "LANDED")
#: B3's set is WIDER, and the asymmetry is deliberate. B3 asks "is the named
#: constraint gone?", and a RULED or RESOLVED predecessor is just as gone as a
#: DONE one — `TASK-616`/`617`/`618` are RULED and are named as entry criteria.
#: B2 asks "does this row cite where it landed?", and a ruling has no hash to
#: cite, so widening B2 the same way would manufacture findings whose only fix
#: is a false citation.
BLOCKER_CLOSED_STATUSES = CLOSED_STATUSES + ("RULED", "RESOLVED")

#: The three exemptable kinds, one per check. B4 is not exemptable — an
#: exemption for the staleness clause would make the ledger permanent.
EXEMPTABLE = ("stale-open", "uncited-closure", "closed-blocker")
KIND_OF = {"B1": "stale-open", "B2": "uncited-closure", "B3": "closed-blocker"}


# ── Inputs ───────────────────────────────────────────────────────────────────

class Row:
    """One parsed board row. `raw` is the whole line: B2 reads the title too."""

    __slots__ = ("tid", "board", "lineno", "status", "raw")

    def __init__(self, tid, board, lineno, status, raw):
        self.tid, self.board, self.lineno = tid, board, lineno
        self.status, self.raw = status, raw

    @property
    def token(self) -> str:
        m = STATUS_TOKEN_RE.search(self.status)
        return m.group(0) if m else ""

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Row TASK-{self.tid} {self.board}:{self.lineno} {self.token}>"


def board_files(root: str = ROOT) -> list:
    out = []
    for path in sorted(glob.glob(os.path.join(root, BOARD_GLOB))):
        if os.path.basename(path) in BOARD_EXEMPT:
            continue
        out.append(os.path.relpath(path, root).replace(os.sep, "/"))
    return out


def parse_board(rel: str, text: str) -> list:
    rows = []
    for lineno, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        m = ROW_RE.match(s)
        if not m:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        status = cells[2] if len(cells) > 2 else ""
        rows.append(Row(m.group(1), rel, lineno, status, s))
    return rows


def read_boards(root: str = ROOT) -> list:
    rows = []
    for rel in board_files(root):
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            rows.extend(parse_board(rel, fh.read()))
    return rows


def git_subjects(root: str = ROOT, rev: str = "HEAD") -> list:
    """-> [(hash, subject)] over the whole history. Raises on a git failure.

    SUBJECTS ONLY (`%s`). Limit 1: a `TASK-NNN` in a commit body is invisible
    here. That is a real hole, and it is named in the docstring rather than
    papered over by reading `%B`, because a body mention is as often "see
    TASK-x" context as it is "this lands TASK-x", and a check that fires on
    context is a check that gets exempted.
    """
    out = subprocess.run(
        ["git", "-C", root, "log", rev, "--pretty=%h%x1f%s"],
        capture_output=True, text=True, check=True).stdout
    pairs = []
    for line in out.split("\n"):
        if "\x1f" in line:
            h, s = line.split("\x1f", 1)
            pairs.append((h, s))
    return pairs


#: `TASK-633/587` and `TASK-649/650/651` are this project's standing shorthand for
#: one commit landing several ids, so the trailing numbers are indexed too.
#: A RANGE is deliberately NOT expanded: `docs(PM): land the harness programme
#: — TASK-579..643` would otherwise tag sixty-five ids onto a board-filing
#: commit and hand B1 sixty-five findings that name no work at all.
MULTI_ID_RE = re.compile(r"TASK-(\d+)((?:/\d+)*)")


def index_commits(pairs) -> dict:
    """[(hash, subject)] -> {task-id: [hash, ...]}, newest first."""
    idx: dict = {}
    for h, subject in pairs:
        for m in MULTI_ID_RE.finditer(subject):
            ids = [m.group(1)] + [x for x in m.group(2).split("/") if x]
            for tid in ids:
                idx.setdefault(tid, []).append(h)
    return idx


# ── Ledger ───────────────────────────────────────────────────────────────────

def parse_ledger(path: str = None) -> tuple:
    """-> ({(kind, board, TASK-id): 'rel:line'}, [errors]).

    Same shape and same rules as the ROWLEN and C6 ledgers: keyed on the row's
    own id and never on a line number, because board rows move on every edit and
    a key that moves is an exemption that silently transfers to a different row.
    The key carries the board file too, because the same id can appear on two
    boards and an exemption must not follow it across.

        | `docs/project/tasks-x.md` | `TASK-NNN` | kind | why | TASK-NNN | YYYY-MM-DD |

    An ABSENT file parses to zero rows and grandfathers nothing — losing the
    ledger can only make this gate stricter.
    """
    path = path or os.path.join(ROOT, LEDGER_REL)
    rows: dict = {}
    errors: list = []
    if not os.path.exists(path):
        return rows, errors
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    header = None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(SEP_RE.fullmatch(x) for x in cells if x):
            continue
        if header is None:
            header = cells
            continue
        board = cells[0].strip("`* ")
        # A table row whose first cell is not a board path is not a ledger row —
        # this file has prose tables in its header. ROWLEN's ledger parser makes
        # exactly the same call for exactly the same reason. The cost is that a
        # ledger row with a mistyped board path is skipped rather than reported.
        # That direction is safe: a skipped exemption suppresses nothing, so the
        # finding it was written for fires and the author is sent back to the row.
        if not board.startswith("docs/project/"):
            continue
        where = f"{rel}:{i}"
        if len(cells) < 6:
            errors.append(f"{where}: exception row has {len(cells)} cells, needs 6 "
                          f"(board | id | kind | why | owner | since)")
            continue
        tid = cells[1].strip("`* ")
        kind, _why, owner, since = cells[2], cells[3], cells[4].strip("`* "), cells[5].strip("`* ")
        if not TASK_ID_RE.match(tid):
            errors.append(f"{where}: subject {tid!r} -> an exception is keyed on the "
                          f"row's own TASK- id, not on a line number")
            continue
        if kind not in EXEMPTABLE:
            errors.append(f"{where}: kind {kind!r} is not exemptable "
                          f"(allowed: {', '.join(EXEMPTABLE)})")
            continue
        if not TASK_ID_RE.match(owner):
            errors.append(f"{where}: {tid} -> owner {owner!r} must be a TASK-NNN id")
            continue
        try:
            datetime.date.fromisoformat(since)
        except ValueError:
            errors.append(f"{where}: {tid} -> since {since!r} is not an ISO YYYY-MM-DD date")
            continue
        rows[(kind, board, tid)] = where
    return rows, errors


# ── The checks ───────────────────────────────────────────────────────────────

def evaluate(rows, commits, ledger=None) -> list:
    """Pure: the findings, so the negative suite drives it with fixtures.

    `rows` is [Row]; `commits` is {task-id: [hash]} — INJECTED, never read from
    this repo's git history inside here, so a fixture cannot be invalidated by
    the next commit anyone makes (BP-068).
    """
    ledger = dict(ledger or {})
    by_id = {r.tid: r for r in rows}
    out: list = []
    used: set = set()

    def exempt(cid, row) -> bool:
        key = (KIND_OF[cid], row.board, f"TASK-{row.tid}")
        if key in ledger:
            used.add(key)
            return True
        return False

    for row in sorted(rows, key=lambda r: (r.board, int(r.tid))):
        tok = row.token
        tid = row.tid

        # B1 — the row says nothing landed; a commit subject says otherwise.
        if tok in OPEN_STATUSES and not PARTIAL_RE.search(row.status):
            hashes = commits.get(tid) or []
            if hashes and not exempt("B1", row):
                shown = ", ".join(f"`{h}`" for h in hashes[:3])
                more = f" (+{len(hashes) - 3} more)" if len(hashes) > 3 else ""
                out.append(
                    f"B1 {row.board}:{row.lineno}: TASK-{tid} reads {tok} but "
                    f"{len(hashes)} commit subject(s) name it — {shown}{more}. The "
                    f"commit that lands the work updates the row in the same commit; "
                    f"if it landed in part, say PARTIAL and the row is honest again")

        # B2 — the row claims a closure and gives no address for it.
        if tok in CLOSED_STATUSES:
            if not HASH_RE.search(row.raw) and DOCS_MARKER not in row.raw:
                if not exempt("B2", row):
                    hashes = commits.get(tid) or []
                    hint = (f" — the log offers `{hashes[0]}`"
                            if hashes else
                            " — and no commit subject names this id either, so the "
                            "closure has no address at all")
                    out.append(
                        f"B2 {row.board}:{row.lineno}: TASK-{tid} reads {tok} and cites "
                        f"no commit hash{hint}. BP-069 already names the hash as part "
                        f"of a row; add it, or mark the row {DOCS_MARKER} if it closed "
                        f"in a document rather than in code")

        # B3 — the named constraint has gone, so the row misdirects.
        m = BLOCKER_RE.search(row.status)
        if m:
            blocker = by_id.get(m.group(1))
            if blocker is not None and blocker.token in BLOCKER_CLOSED_STATUSES:
                if not exempt("B3", row):
                    out.append(
                        f"B3 {row.board}:{row.lineno}: TASK-{tid} reads BLOCKED on "
                        f"TASK-{m.group(1)}, which reads {blocker.token} "
                        f"({blocker.board}:{blocker.lineno}). A cold session reads this "
                        f"row, sees the predecessor closed, and starts work that may "
                        f"still be blocked. Name the constraint that is actually live, "
                        f"or open the row")

    # B4 — a ledger row whose finding no longer occurs. Shrink-only.
    for key, where in sorted(ledger.items()):
        if key not in used:
            kind, board, tid = key
            out.append(
                f"B4 {where}: stale exception — {tid} in {board} no longer produces "
                f"its {kind} finding; delete this row. The ledger can only shrink")
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    rows = read_boards()
    try:
        pairs = git_subjects()
    except (OSError, subprocess.CalledProcessError) as e:
        # Fail CLOSED and loudly. An unreadable log yields an empty index, which
        # would silently turn B1 off and print PASS — the exact shape of failure
        # this gate exists to stop.
        print(f"FAIL: git log is unreadable ({type(e).__name__}: {e}) — B1 cannot "
              f"be evaluated, so this gate refuses rather than passing on an "
              f"empty commit index")
        return 1
    commits = index_commits(pairs)
    ledger, ledger_errors = parse_ledger()
    findings = evaluate(rows, commits, ledger) + ledger_errors

    classified = sum(1 for r in rows
                     if r.token in OPEN_STATUSES + CLOSED_STATUSES)
    print(f"check_board_currency: {len(rows)} row(s) across {len(board_files())} "
          f"board(s), {classified} with a classified status; {len(commits)} task id(s) "
          f"named in {len(pairs)} commit subject(s); {len(ledger)} ledger row(s)")
    if args.verbose:
        for r in sorted(rows, key=lambda r: (r.board, int(r.tid))):
            print(f"    {r.board}:{r.lineno} TASK-{r.tid} {r.token or '<unclassified>'}"
                  f" commits={len(commits.get(r.tid) or [])}")

    if findings:
        print(f"\nFAIL: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        print(f"\n  The rule: the commit that lands the work updates the row in the "
              f"same commit. Limits are in this file's docstring — a PASS here is "
              f"not a guarantee that the board is true.")
        return 1
    print("  PASS  no board row contradicts the commit log in the three ways B1-B3 name")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
