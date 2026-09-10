# Board reset — measurement, diagnosis, and a retire/archive proposal

> Owner: **Project Manager**
> Status: **accepted** — written as a proposal, approved by the human, and **steps 0, 1, 3 and 5 are
> now landed** (§7). Steps 2, 4 and 6 remain as written. §§0–6 are the proposal as it was put; they
> are deliberately not rewritten to match the outcome.
> Written: 2026-09-03
> Question put to me: *can we retire/archive the `task*.md` files and start from a relatively clean
> slate before scheduling the harness re-architecture?*
> Against: [tasks.md](tasks.md) · [tasks-architecture.md](tasks-archive.md#tasks-architecturemd--retired-2026-09-10-verbatim-snapshot) (retired 2026-09-10) ·
> [tasks-winamp-player.md](tasks-winamp-player.md) · [tasks-archive.md](tasks-archive.md) ·
> `app/tools/gate/check_docs.py` · [M-HARNESS2-PM-review.md](M-HARNESS2-PM-review.md) §3a
> Method: static only. No DUT, no serial port, nothing under `app/tools/` imported. Every count
> below is from a command run against the working tree at `f880f52`.
>
> **AS-BUILT, 2026-09-03 — steps 0, 1, 3 and 5 are landed.** The human approved the §6 sequence.
> The proposal text below is unchanged; what actually happened, including the one place the
> measurement was wrong, is in [§7 As-built](#7-as-built--what-actually-happened).

---

## 0. The short answer

**Yes to archiving, but it will not fix what you think it fixes, and on its own it has already
failed once on this project.**

Three things came out of the measurement and they do not point where the question assumes:

1. **`tasks.md` has nothing to archive.** All 13 of its own entries are open or blocked. It holds
   **51 table rows and every single one of them is a mirror of another board** — 39 mirroring
   `tasks-architecture.md`, 12 mirroring `tasks-winamp-player.md` — and the file disclaims both
   mirrors in its own text, twice (`tasks.md:159`, `tasks.md:185`: *"the split file wins"*). The
   main board is not cluttered with finished work. It is cluttered with **a copy of two other
   boards that it tells you not to trust.**
2. **`tasks-architecture.md` is the board with real archival debt** — 89 of 103 rows are closed —
   **and archival still cannot fix its worst problem.** Its single largest row is `TASK-557` at
   **20 680 characters** (`tasks-architecture.md:300`), which is **OPEN**. 16 of its 57 over-length
   rows are on live work. That is a BP-069 row-format problem, not an archival one.
3. **This exact sweep has been run twice.** After the 2026-07-12 pass `tasks.md` sat at 1 274 lines
   and regrew to 9 787 in 34 days — **250 lines/day**. After the 2026-08-15 pass it sat at 1 193 and
   is at 1 422 nineteen days later — **12.7 lines/day**. The variable that changed between those two
   outcomes is not the sweep. It is **BP-069** (2026-08-25) and its `ROWLEN` check. And `ROWLEN` is
   **advisory, reading 66 over-length of 131 rows** — 50 % — which is precisely the decaying-advisory
   shape the M-HARNESS2 review condemns in C3.

So: sweep, yes. But if the sweep lands without promoting the row rule, you are buying the July
outcome, and I would rather say that now than write the next archive note.

---

## 1. What is actually on the three boards today

All figures from the working tree at `f880f52`, 2026-09-03.

### 1.1 Row and line census

| board | lines | own entries | mirror rows | last swept |
|---|---|---|---|---|
| `tasks.md` | **1 422** | 13 prose sections, **0 table rows of its own** | **51** (39 M-ARCH + 12 M-WINAMP) | 2026-08-15 |
| `tasks-architecture.md` | **530** | **103 table rows** | 0 | 2026-08-25 (22 rows) |
| `tasks-winamp-player.md` | **1 334** | 22 heading sections (12 tasks + 10 sub-records) | 0 | never — split out 2026-08-15 |
| `tasks-archive.md` | **19 413** | 520 heading entries, 473 distinct ids | — | it *is* the archive |

### 1.2 Breakdown by status

**`tasks.md` — 13 own entries, and every one is live.** Not one closed entry is sitting on this
board.

| id | lines | status | last touched |
|---|---|---|---|
| TASK-451 | 73 | OPEN — 1 of 5 explained, four remain | 2026-08-15 |
| TASK-243 | 32 | BLOCKED — external (owner-account Premium) | **2026-06-25** |
| TASK-284 | 58 | OPEN — mitigation landed, symptom intermittent | **2026-07-12** |
| TASK-385 | 138 | OPEN — instrumented, unconfirmed | 2026-08-06 |
| TASK-386 | 157 | OPEN — instrumented, 0/1 reproduced | 2026-08-06 |
| TASK-390 | 257 | OPEN — filed for investigation, unconfirmed | 2026-08-06 |
| TASK-403 | 60 | OPEN — feasibility gate cleared, deferred P3 | 2026-08-15 |
| TASK-439 | 26 | OPEN — filed 2026-08-14 | 2026-08-15 |
| TASK-437 | 33 | OPEN — awaiting screen text | 2026-08-15 |
| TASK-438 | 28 | OPEN — filed 2026-08-14 | 2026-08-26 |
| TASK-262 | 52 | BLOCKED — gated **only** on TASK-243 | 2026-08-15 |
| TASK-393 | 300 | OPEN — render-freeze, live-reproduced | 2026-08-15 |

*(the 13th is the `## Open — TASK-386` wrapper heading, 10 lines)*

**Open: 11. Blocked: 2. Done-but-not-archived: 0.** Stale (untouched ≥ 4 weeks): **5 of 13**
(TASK-243, 284, 385, 386, 390). Untouched ≥ 8 weeks: **2** (TASK-243 since 2026-06-25, TASK-284
since 2026-07-12).

**`tasks-architecture.md` — 103 rows.**

| bucket | count |
|---|---|
| DONE / LANDED / superseded / withdrawn / corrected-closed | **~89** |
| OPEN | 8 (TASK-573, 574, 557, 568, 569, 576, 577, 578) |
| PARTIAL (must **not** move) | 3 (TASK-549, 564, 566) |
| DEFERRED | 1 (TASK-567) |
| SKELETON — real open research | 2 (TASK-484, 486) |

**86 % of this board is finished work.** Its own header note at `tasks.md:57-58` already admits the
mirror of it is "a snapshot from before the 2026-08-25 session and is stale in places", and the
`tasks.md:40-41` split-board note calls this board's own live count "61 entries" — it is 14.

**`tasks-winamp-player.md` — 12 tasks, milestone paused.** By line span, roughly **899 of 1 334
lines (67 %) are closed records**:

| span | lines | what |
|---|---|---|
| 187–714 | **528** | TASK-424 + its 4 sub-records — **DONE 2026-09-01** (PATCH-TLS-1). 40 % of the board is one closed bug. |
| 757–830 | 74 | TASK-444 + result — DONE |
| 831–874 | 44 | TASK-445 — DONE |
| 938–1001 | 64 | TASK-443 — withdrawn |
| 1081–1183 | 103 | TASK-422 parts A/B/C records — done parts |
| 1211–1296 | 86 | TASK-429 + gate result — DONE |

Live remainder: TASK-407 (OPEN), 452 (OPEN), 446 (IMPL), 419 (READY), 420/421 (BLOCKED — now
unblocked by TASK-424's close), 422 head (PARTIAL), 428 (OPEN) ≈ **435 lines**.

### 1.3 How the last reorganisation was done, and whether it worked

Commit `1442b10`, 2026-08-15 — *"archive 80 closed tasks, split the M-WINAMP-PLAYER board out"*:
`tasks-archive.md +7 570`, `tasks-winamp-player.md +1 122` (new file), `tasks.md −9 128`.
**8 959 insertions / 8 861 deletions** — near-symmetric, i.e. a genuine *move*, not a deletion. The
pass recorded its own verification at `tasks.md:15`: *"480 distinct task ids across the three files,
no duplicates, none lost"*, plus the trap it hit — *"result/resolution sub-sections are `###`-level
in this project and must travel with their parent task — splitting on heading level alone orphans
them."*

**Did it work?** Partly, and the honest read is more interesting than a yes.

| period | `tasks.md` growth | rate |
|---|---|---|
| after the 2026-07-12 pass (1 274 lines) → 2026-08-15 (9 787) | +8 513 in 34 d | **250 lines/day** |
| after the 2026-08-15 pass (1 193 lines) → 2026-09-02 (1 422) | +229 in 18 d | **12.7 lines/day** |

A 20× collapse — but part of it is displacement, not discipline: the two split files absorbed the
load. `tasks-architecture.md` went 131 → 530 (+399 in 17 d, **23/day**) and
`tasks-winamp-player.md` 1 124 → 1 334 (+210, **12/day**). **Total live-board growth is ~48
lines/day against 250** — a real 5× improvement, not 20×.

The 5× is attributable to **BP-069** (row format, 2026-08-25) and its `ROWLEN` check, not to the
sweep: the July sweep had no row rule and regrew 8× in five weeks; the August sweep had one and did
not. **The sweep is the visible half of the fix and the smaller half.**

One more measurement that reframes the whole question — commits since 2026-08-16:

| board | commits |
|---|---|
| `tasks-architecture.md` | **140** |
| `tasks.md` | 26 |
| `tasks-winamp-player.md` | 15 |

The board that is actually *worked* is the architecture board. `tasks.md` is edited about once every
five days and its own text redirects the reader elsewhere twice.

---

## 2. What a clean slate would actually cost

### 2.1 The gate mechanics that decide this

Read `app/tools/gate/check_docs.py` before moving a single row. Four rules matter and one of them is
counter-intuitive.

* **C2 resolves `TASK-` ids against `docs/project/tasks*.md` — the glob, all four files**
  (`check_docs.py:256`). `tasks-archive.md` is in `EXEMPT_BASENAMES` (`check_docs.py:63`), and the
  exemption split is explicit: **exempt files are never *scanned*, but are always usable as
  *resolution sources*** (`check_docs.py:253-254`, restated for C6 at `check_docs.py:551-553`). The
  docstring gives the reason in numbers: *"356 TASK- ids resolve only in the exempt
  tasks-archive.md; a resolver that honours the exemption scores 1 261 false failures."*
* **Therefore a MOVE between `tasks*.md` files is provably C2-neutral.** Source and destination are
  both inside the glob. This is the single most important fact in this document.
* **A DELETE is not.** Measured: **97 task ids exist only on the three live boards and nowhere in
  the archive; 81 of them are cited by at least one document outside the boards.** Deleting those
  rows instead of moving them produces **476 blocking C2 failures across 34 gated files**, which
  reds out `run/check-docs` and therefore `run/check` gate 11. **Nothing is ever deleted. Everything
  is moved.**
* **C6 is not involved at all.** Its doc side is `docs/verification/` only (`check_docs.py:15`,
  `check_docs.py:651`); task boards are outside its corpus. Today it reads *265 registry ids, 424
  doc ids, 224 bound; 41 orphan / 3 undeclared / 0 mismatched; 44 on the ledger, **0 unexcepted***.
  A board reset cannot move any of those numbers. Do not let anyone claim it as a C6 win.
* **`ROWLEN` deliberately excludes `tasks-archive.md`** (`check_docs.py:366-368`) — *"archived rows
  are expected to be long."* So moving a fat row into the archive **removes its `ROWLEN` violation
  by construction**, without shortening anything. That is legitimate — the archive is where BP-069
  says verbose content goes — but it means the `ROWLEN` count will improve for a reason that is not
  improved writing, and it should be reported as such.

### 2.2 What breaks if rows move

* **Anchors, silently.** C5 checks that a relative `.md` link's *file* exists and **strips the
  `#anchor` before checking** (`check_docs.py:500`). There are **17 anchor links pointing into the
  three live boards** and 27 already pointing into the archive. Move a section and the link still
  passes C5 while landing on a dead anchor. **No gate catches this.** It must be a manual grep step,
  and the existing archived rows show the correct pattern —
  `tasks-archive.md#task-453-full-record-archived-2026-08-25-from-tasks-architecturemd`.
* **`###`-level sub-records orphaning** — the trap the last pass recorded at `tasks.md:15`. On the
  winamp board this is not hypothetical: TASK-424's four `####` sub-records span 192–714 and are
  five separate headings that must travel as one unit.
* **Nothing else.** SPIKE keys off archive membership (`check_docs.py:331-333`) but reads *0
  retirement-due of 0 spike scripts* — there are no spike scripts, so moving ids into the archive
  cannot arm it.

### 2.3 What breaks if rows are deleted

476 blocking C2 failures, 34 files, `run/check` red. Plus the irreversible loss the archive exists
to prevent: this project's boards are the only record of *why* — TASK-424's 528 lines are the
six-week false-trail history that produced LL-"handle goes bad? suspect a close" and PATCH-TLS-1.
**Deletion is not on the table and I will not propose a plan containing one.**

---

## 3. Is the premise right?

The implied diagnosis is that the boards are cluttered enough to obstruct scheduling. **The
obstruction is real. Volume is not what causes it.** Ranked by what I measured:

**1. The primary obstruction is that there is no scheduling surface — `tasks.md` was demoted from
board to index without anyone deciding it.** This is the finding. Evidence:

* It has **zero rows of its own**; 51 of 51 are mirrors.
* Both mirrors disclaim themselves — `tasks.md:159` *"The split file is the entry; this is a
  label"*; `tasks.md:185` *"If a status changes in the split file and not here, the split file
  wins"*; and the M-ARCH section header at `tasks.md:57-58` calls its own rows *"a snapshot from
  before the 2026-08-25 session and stale in places."*
* **The execution sequence — the thing you actually schedule from — is not on the main board at
  all.** It lives at `tasks-architecture.md:105` (`## ▶ EXECUTION SEQUENCE — start here`), and
  `tasks.md:143` points at it.
* So someone opening `tasks.md` to schedule gets 54 lines of preamble, then 136 lines of
  self-disclaimed mirror, then 13 open bugs unrelated to the programme — and the answer is in
  another file.

**Archiving does not fix this. Archiving `tasks.md` would remove nothing, because it holds nothing
closed.** A clean slate aimed at volume would leave the exact obstruction untouched.

**2. The second obstruction is that `tasks-architecture.md` is a record wearing a board's
clothes.** 89 of 103 rows closed; 57 of 103 rows over the BP-069 400-character limit; one row
(TASK-557) at 20 680 characters. **This is the one an archival pass genuinely fixes** — but only
41 of the 57 over-length rows are on closed work. **16 survive any sweep, including the worst one,
because it is open.** TASK-557 needs its measurement record moved into a design doc under BP-069,
which is a different operation from archiving.

**3. Staleness is real but small.** 5 of 13 `tasks.md` entries untouched ≥ 4 weeks; 2 untouched
≥ 8 weeks. Five entries totalling 552 lines (TASK-385, 386, 390) are all "instrumented, unconfirmed,
not reproduced" and have not moved since 2026-08-06. That is a triage debt of about half a day, and
it is a *judgement* problem — no mechanical sweep resolves it.

**4. Volume, last and least.** The live boards total 3 286 lines. That is not large. `tasks.md`'s
own trajectory shows the volume problem was solved on 2026-08-15 and has stayed solved for 19 days.

**Conclusion.** A clean slate as asked — sweep the boards, start fresh — **fixes obstruction 2,
does nothing for 1 and 3, and cannot regress 4.** If it is done without also (a) resolving the
mirror question and (b) making the row rule bite, the measured history says the boards regrow. I
recommend doing it, scoped to what it actually fixes, with the two structural fixes attached.

---

## 4. The proposal

Six steps. Each is one commit. `./run/check-docs` runs after every step and must read **6 passed,
0 failed** with **C2 at 0 unresolvable of ~4 836**. Steps are ordered so the cheap mechanical ones
land first and the judgement-heavy ones can be abandoned without unwinding anything.

### Step 0 — baseline and safety net (5 min, automatable)

```sh
git tag board-reset-base            # the single rollback handle
./run/check-docs 2>&1 | tee /tmp/board-reset-baseline.txt
```

Record today's numbers so every later step is a diff, not an assertion:
**C5** 0/467 · **C6** 0 unexcepted · **C2** 0 of 4 836 · **C4** 0 of 207 · **SPIKE** 0/0 ·
**C1-delta** 0/0 · advisory **C1-full** 293/1037 · **C3** 60/389 · **ROWLEN** 66/131.

### Step 1 — archive the architecture board's closed rows (~2 h; **move automatable, selection needs a human read**)

**File:** `tasks-architecture.md` → `tasks-archive.md`.
**Move:** the ~89 DONE/LANDED/superseded/withdrawn rows.
**Do not move — 14 rows:** TASK-573, 574, 557, 568, 569, 576, 577, 578 (OPEN); TASK-549, 564, 566
(PARTIAL); TASK-567 (DEFERRED); TASK-484, 486 (SKELETON — real open research).

**Human read required on exactly three things**, all of which my status regex got wrong at least
once during measurement and which a script will get wrong too:

* rows whose status text contains both a closure word and a live word (`"DONE … PARTIAL"`,
  `"DONE … the remainder is open"`, `"UNBLOCKED"`);
* the three PARTIAL rows — a PARTIAL row is *live work with a landed prefix*, and archiving one
  silently retires an owed deliverable. TASK-566 is the one that matters: its order switch is HELD
  and the M-HARNESS2 programme depends on it;
* rows already carrying a `[full record in tasks-archive.md](...)` pointer — those are 1-line
  pointers and are the *result* of the last pass. **Leave them.** Re-archiving a pointer produces a
  pointer to a pointer.

**Expected gate movement:** C2 unchanged (both files are inside the `tasks*.md` glob —
`check_docs.py:256`); `ROWLEN` **66 → ~25** (41 of 57 arch violations are on closed rows).
**Preserve the section headings** (`## M-SRCLAYOUT`, `## M-CODEQUAL`, …) with a one-line "all rows
archived 2026-09-03" note rather than deleting them, so the 27 existing archive anchors and the
board's structure survive.

**Mechanical preservation check before committing** — the discipline the 2026-08-15 note used:

```sh
# id sets must be preserved across the move, and the diff must be near-symmetric
git show --stat HEAD | grep tasks-      # insertions ≈ deletions
comm -3 <(grep -ohE 'TASK-[0-9]+' <before>) <(grep -ohE 'TASK-[0-9]+' <after>) | sort -u
```

### Step 2 — archive the winamp board's closed records (~2 h; **not automatable**)

**File:** `tasks-winamp-player.md` → `tasks-archive.md`.
**Move, as whole units including every `####` sub-record:**

| span | id | why |
|---|---|---|
| 187–714 | TASK-424 | DONE 2026-09-01, PATCH-TLS-1. **5 headings, 528 lines, one unit.** |
| 757–830 | TASK-444 | DONE, incl. its `#### result` |
| 831–874 | TASK-445 | DONE |
| 938–1001 | TASK-443 | withdrawn (successor TASK-452 stays) |
| 1081–1183 | TASK-422 A/B/C | done parts; **the TASK-422 head row at 1054 stays** (PARTIAL) |
| 1211–1296 | TASK-429 | DONE, incl. its `#### gate result` |

**Why this is not automatable:** `tasks.md:15` records the exact trap — sub-records are `####`-level
and orphan if you split on heading level. TASK-424 alone is five headings. And TASK-422 is a
*partial* whose closed parts move while its head stays, which no heading-level rule can express.

**Attached, in the same commit:** re-point the 12 anchor links in `tasks.md:167-182` for any moved
id, and grep the repo for the other 5 of the 17 live-board anchors. **C5 will not catch a dead
anchor** (`check_docs.py:500`). Expected: board 1 334 → ~435 lines, 8 live entries.

### Step 3 — resolve the mirror question (~1 h; **needs the human's decision, then automatable**)

This is the step that fixes the actual obstruction, and it is the cheapest one here.

**Delete the two mirror tables** — `tasks.md:63-162` (39 M-ARCH rows) and `tasks.md:164-187`
(12 M-WINAMP rows), **~136 lines** — and replace them with the index the file already behaves like:

```markdown
## Where the work is

| board | scope | live entries | entry point |
|---|---|---|---|
| tasks-architecture.md | M-SRCLAYOUT · M-CODEQUAL · M-TOOLING · M-DOCLIFE · M-TESTARCH | 14 | § ▶ EXECUTION SEQUENCE |
| tasks-winamp-player.md | M-WINAMP-PLAYER (paused) | 8 | § Open — M-WINAMP-PLAYER |
| tasks-harness2.md | M-HARNESS2 + WP-Z (see §4.5) | 63 | § Phase table |
| (this file) | unassigned defects and investigations | 13 | below |
```

**This deletes rows, so check the C2 arithmetic:** it is safe, because every mirrored id is a
*duplicate* — the row exists on the split board too, and both files are inside the `tasks*.md` glob.
Verify mechanically rather than trusting me:

```sh
# must print nothing: no id may exist ONLY in the mirror being deleted
comm -23 <(sed -n '63,187p' docs/project/tasks.md | grep -ohE 'TASK-[0-9]+' | sort -u) \
         <(cat docs/project/tasks-architecture.md docs/project/tasks-winamp-player.md \
             docs/project/tasks-archive.md | grep -ohE 'TASK-[0-9]+' | sort -u)
```

**The human decision this needs:** the mirror exists so ids stay "visible and searchable from the
main board" (`tasks.md:165`). Deleting it trades that for honesty. My recommendation is delete — a
searchable index that is wrong is worse than no index, and both drift warnings concede it is wrong —
but it is a preference about how you navigate your own boards and I will not take it for you.

**Expected gate movement:** `ROWLEN` loses the 9 `tasks.md` violations (all 9 are mirror rows) —
combined with Step 1, **66 → ~16**, and all 16 survivors are on live rows, which is the honest
number.

### Step 4 — closure triage (~4 h; **human read, not automatable, and abandonable**)

Not a sweep. Twelve live entries, each gets a dated disposition. My **candidate** dispositions —
these are proposals, and every one needs someone who knows the symptom:

| id | lines | candidate | reason |
|---|---|---|---|
| TASK-262 | 52 | **WONTFIX** | a cleanup placeholder for spike artefacts, gated *only* on TASK-243, which is an external Premium blocker with no date. It has waited on an unbounded external for months. If TASK-243 ever clears, refile it in ten minutes. |
| TASK-284 | 58 | **close as MITIGATED**, not WONTFIX | untouched since 2026-07-12; the same-mirror retry mitigation landed; the memory record says the truncation "comes and goes, likely rate limiting". Nothing is owed. Keep the finding in the archive. |
| TASK-385, 386, 390 | 552 | **re-confirm or close, dated** | three "instrumented, unconfirmed, 0/1 reproduced" entries, all frozen at 2026-08-06. Give each a single dated decision: does it reproduce on the pinned debug build, yes or no. A "filed for investigation" entry that has not been investigated in four weeks is not a task, it is a note. |
| TASK-243 | 32 | **keep, re-label EXTERNAL-BLOCKED** | it gates 12 permanently-skipped test ids. It must stay visible. But it is not *work* and should not sit in the same list as work. |
| TASK-393 | 300 | **keep, apply BP-069** | live and reproduced; 300 lines of it belong in a design doc, not a board. |
| TASK-451, 403, 437, 438, 439 | 220 | **keep** | all live, all recently touched, all correctly sized or nearly so. |

**Abandonable by design:** if this step is dropped, Steps 1–3 and 5 still stand and the boards are
still better. That is deliberate — it is the only step needing judgement about firmware behaviour
rather than about documents.

### Step 5 — where the M-HARNESS2 + WP-Z rows land (~1 h; automatable once decided)

**Recommendation: a new fourth board, `docs/project/tasks-harness2.md`**, carrying the 63 rows of
[M-HARNESS2-PM-review.md §3a](M-HARNESS2-PM-review.md#3a-the-single-sequenced-programme) — and
**only** those 63. The 15 WP-Z ids subsumed per §2.1 must be dropped **in the same commit**; §7
risk 4 of that review says a separate paste books a month of work twice.

I know a fourth board reads as the opposite of a clean slate, so here is the argument against my own
recommendation and why it loses:

* *Against:* `tasks.md:38-44` calls split boards "stopgaps, not permanent fixtures", to be folded
  back and **deleted** when their active count reaches zero.
* *For:* that rule contemplates exactly this case. A programme board with five phases, named entry
  and exit criteria, and stop-the-work conditions **has a defined death condition** — Phase 5 exits
  or a stop criterion fires — which is more than either existing split board can say.
* *The alternative is worse and is measured:* 63 rows into `tasks.md` takes it from 13 live entries
  to 76 and, at the observed 48 lines/day of live-board growth, straight back toward the file that
  was just cut in half twice.

**Gate note:** all 63 rows land as new ids on a `tasks*.md` file, so C2 gains ~63 resolvable ids and
stays at 0 failures. The twenty-two provisional ids in §3a (the 621-to-643 block) become **real** the
moment this file exists — that is the point, and it is also why this step must not run before the
human has agreed the programme, or the boards acquire 22 ids for work nobody approved.

**A worked demonstration, from writing this very document.** The first draft of this file cited
those provisional ids literally. `./run/check-docs` returned **C2: 3 unresolvable of 4 900** and went
red, because provisional ids resolve nowhere and this file — unlike a `*-review.md` — is inside the
gated corpus (`check_docs.py:63`, `EXEMPT_SUFFIXES`). That is C2 doing exactly its job, and it is the
concrete proof of §2.1's central claim: **the gate is indifferent to which `tasks*.md` file a row
sits in, and lethal about a row that sits in none.**

### Step 6 — make it hold (~2 h; the step that decides whether any of this survives)

Everything above is a one-shot, and this project has measured what one-shots are worth: the
2026-07-12 sweep regrew 8× in five weeks.

**Promote `ROWLEN` from advisory to blocking**, once Steps 1–3 have taken it from 66/131 to ~16, and
land it with the ledger discipline the M-HARNESS2 review makes programme-wide: a dated, owned,
**shrink-only** ledger whose stale rows are themselves blocking failures. This is C6's pattern
(`check_docs.py:526-536`) — the one gate on this project that landed red and *worked* — and it is
the opposite of C3, which is advisory and grew 58 → 60 during the review that diagnosed it.

**TASK-557's row is the test case.** At 20 680 characters it is 51× the limit and it is **open**, so
no archival pass can reach it. Under a blocking `ROWLEN` its measurement record moves into the
M-TESTARCH/TASK-557 design doc and the row becomes a pointer — which is what BP-069 asks for and
what nobody has done because nothing makes them.

**Do not promote it in the same commit as any move.** Land the moves, re-measure, *then* promote on
the measured number. That is TASK-475's own rule, stated at `check_docs.py:249-251`: phase 1 blocks
on what reads 0 — or here, on what reads a number somebody has agreed to own.

### 4.7 What the boards look like afterwards

| board | before | after | content |
|---|---|---|---|
| `tasks.md` | 1 422 lines, 13 live entries, 51 mirror rows | **~1 150 lines, ~8–13 live entries, 0 mirror rows** | unassigned defects + a 4-row index |
| `tasks-architecture.md` | 530 lines, 103 rows (89 closed) | **~190 lines, 14 rows** | the execution sequence and live architecture work only |
| `tasks-winamp-player.md` | 1 334 lines, 12 entries | **~435 lines, 8 entries** | the paused milestone's live work |
| `tasks-harness2.md` | — | **~90 lines, 63 rows** | the programme, one row per task, phase-ordered |
| `tasks-archive.md` | 19 413 lines | **~21 000 lines** | everything closed, still a C2 resolution source |
| `ROWLEN` | 66 of 131 | **~16 of ~98**, then blocking | |

Live board total: **3 286 → ~1 865 lines**, with the mirror gone and one board per thing that is
actually being worked.

---

## 5. Rollback

This is a git repo, master is local-only, and nothing here is pushed. Rollback is total and cheap.

**Before anything:** `git tag board-reset-base` (Step 0).

**Undo everything, at any point:**

```sh
git reset --hard board-reset-base
./run/check-docs        # must read 6 passed, 0 failed; C2 0 of ~4836
```

Safe because master is local-only and never pushed without approval — there is no published history
to rewrite. If any step *was* somehow shared, use `git revert --no-edit <sha>..<sha>` instead and
take the extra commits.

**Undo one step, leaving the others:**

```sh
git revert --no-edit <sha-of-that-step>
./run/check-docs
```

Each step is one commit precisely so this works. Steps 1, 2 and 3 are independent moves and revert
cleanly in any order. Step 5 is additive (a new file) — reverting it deletes the file and returns
the 22 provisional ids to being provisional. Step 6 is a one-line threshold change in
`check_docs.py` and reverts trivially.

**Verify a rollback actually restored content, not just line counts:**

```sh
# must be empty — every id present at base is present now
comm -23 <(git show board-reset-base:docs/project/tasks.md \
             docs/project/tasks-architecture.md 2>/dev/null | grep -ohE 'TASK-[0-9]+' | sort -u) \
         <(cat docs/project/tasks*.md | grep -ohE 'TASK-[0-9]+' | sort -u)
```

**The one thing rollback does not restore:** any anchor link elsewhere in the corpus that was
re-pointed in Step 2. Those edits live in *other* files and must be reverted with the same commit —
which is why Step 2's anchor fixes belong in Step 2's commit and not a follow-up.

---

## 6. Sequence — and where I disagree with the question

The question proposes archival **before** the programme is scheduled. **I recommend splitting it:
the mechanical half goes first, the judgement half goes after Phase 1 has started.**

**Do first, today, ~3 hours:** Step 0, **Step 1** (arch board), **Step 3** (the mirror). Then
**Step 5** (the programme board) as part of scheduling the programme, not before it.

**Do after Phase 1 is underway:** Step 2 (winamp — the milestone is paused, its clutter blocks
nothing), Step 4 (closure triage), Step 6 (promote `ROWLEN`, on a re-measured number).

**Three reasons, and the third is the one I actually care about.**

1. **Steps 1 and 3 are a genuine precondition of Step 5, and only those two.** You cannot land 63
   programme rows onto a board whose own text disclaims itself twice and whose execution sequence
   lives in another file. That is ~3 hours of pure mechanics with a `git tag` behind it. Everything
   *else* in the reset is independent of scheduling and can wait.
2. **Phase 0 is already discharged and Phase 1 has no entry criterion.** The three escalations were
   ruled today; what remains of Phase 0 is a sign-off and five ADR filings. Phase 1's entire
   justification is that it needs no board, no ADR and no decision. Making it wait on a documentation
   sweep invents an entry criterion that the review deliberately does not have.
3. **A full board reset before the programme starts would be the fifth review pass in a row, and I
   named that failure mode in my own document three hours ago.** [M-HARNESS2-PM-review.md
   §7.6](M-HARNESS2-PM-review.md#7-honest-sequencing-risk--how-my-own-plan-fails): *"This is the
   fourth full review pass over one proposal and the programme has consumed zero engineer-days so
   far… If Phase 1 has not started before the next review of anything, that is the finding."* Steps
   2, 4 and 6 total about a day of documentation work with no engineering in it. Spending that day
   *before* day 1 of Phase 1 would make that prediction come true, and it would be my own doing. I
   would rather hand you a board that is 80 % fixed and a programme that has started than a perfect
   board and a fifth review.

**One thing I would not defer: Step 6.** It is scheduled last but it is not optional. The measured
history is unambiguous — the July sweep with no row rule regrew 250 lines/day, the August sweep with
one regrew 48. If Step 6 never lands, the next PM writes the next archive note, and the honest
prediction is that they write it in about five weeks.

---

## 7. As-built — what actually happened

Recorded 2026-09-03, after execution. Rollback handle `board-reset-base` is in place and untouched.

| step | commit | result |
|---|---|---|
| 0 — tag + baseline | — | `board-reset-base` tagged; baseline captured (6 passed / 0 failed, ROWLEN 66/131) |
| 1 — arch board | `7d5a3e4` | **65** discharged rows moved to the archive, each leaving a one-line pointer in the 2026-08-25 shape. **16** kept live. ROWLEN **66 → 27** |
| 3 — the mirror | `b5b3e98` | the 51-row mirror out of `tasks.md`, replaced by the "Where the work is" index |
| 5 — programme board | this change | [tasks-harness2.md](tasks-harness2.md) created — 61 rows, ids TASK-579…TASK-643, 0 over 400 chars |
| 2, 4, 6 | — | deferred per §6: after Phase 1 is underway |

### 7.1 Where the estimate was wrong, and where the analysis was right

**Step 1 kept 16 rows live, not the 14 I listed.** The two additions are correct and my status
classification missed both: **TASK-462** (`UNBLOCKED` reads as closed to a regex and is live work)
and **TASK-575** (`FIXED` host-side with a full `run/test` pass still owed). This is exactly the
hazard §4 Step 1 flagged — *"rows whose status text contains both a closure word and a live word …
which a script will get wrong too"* — and it is why that step was specified as needing a human read
rather than automation. The mechanism worked; my own count was the thing it caught.

**Step 3 hit the C2 hazard from the opposite direction, and this is the important entry.**
§2.3 predicted that *deleting* rows would break C2, and measured the general case at 476 occurrences
across 34 files. Deleting the mirror did break C2 — **41 unresolvable** — but not for the reason
predicted. The mirror rows were not the duplicates §4 Step 3's `comm -23` pre-check assumed:
**earlier archiving passes had already moved those 41 ids' real rows out, leaving the mirror as
their sole remaining home in the `tasks*.md` glob.** A copy that outlives its original is no longer
a copy. It was recovered by moving the whole block into `tasks-archive.md`, which is the same
move-never-delete rule §2.3 states, applied to a case §4 had wrongly cleared as safe.

**The lesson, and it generalises past this board:** the `comm -23` guard in Step 3 was right to
exist and wrong in its direction. It tested *"does this id appear elsewhere?"* against the live
boards plus the archive — but it was written to justify a delete, and the correct rule is that
**no id's last remaining row is ever deleted, whatever file it happens to be sitting in.** A mirror
is only safely deletable while its source still exists, and nothing was checking that invariant over
time. The general form of this is worth carrying: **a duplicate is a claim about the present tense,
and archiving falsifies it silently.**

### 7.2 Step 5 decisions worth recording

* **Ids 579–643 were kept, not renumbered** — verified collision-free against every board and the
  archive (board maximum was 578). WP-Z declared the band renumberable, but the human ruled on
  TASK-616/617/618 *by those ids* on 2026-09-03 and six review documents cross-reference them.
  Renumbering would have invalidated a ruling's own identifiers to save nothing. Next free: **644**.
* **17 ids carry no row**, and the board says so in its header so the double-booking cannot return:
  the 15 subsumed per §2.1 (14 of which keep their id carrying the M-HARNESS2 work, plus **TASK-590**
  retired entirely into TASK-624), and **TASK-586** and **TASK-598**, both inside TASK-603's delete
  list. **TASK-620** was never allocated — it was only the top of WP-Z's reserved band.
* **TASK-575 is named in Phase 3's entry criteria, not given a row.** It lives on the architecture
  board. Copying it across would have rebuilt, on day one, the mirror that Step 3 deleted the same
  morning — which is the whole finding of §3. The board carries an explicit "do not add it" note.

### 7.3 What is still owed

Steps 2, 4 and 6 stand as written. **Step 6 remains the one that decides whether any of this
survives**: `ROWLEN` is advisory at 27 after Step 1 and 18 after Step 3, and the measured history in
§1.3 says that without promoting it the boards regrow. TASK-557's row is still the test case — at
20 680 characters it is open, so no archival pass can reach it.
