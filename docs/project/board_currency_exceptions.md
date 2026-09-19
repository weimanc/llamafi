# Board-currency exceptions — the ledger for `check_board_currency.py`

> Owner: **@Developer** · Machine-read by `app/tools/gate/check_board_currency.py` (checks **B1**,
> **B2**, **B3**; the staleness clause **B4** is not exemptable)
> Opened **2026-09-07** by [TASK-669](tasks.md) · Rule: **LL-147**, a BP candidate awaiting human
> sign-off, in [lessons_learned.md](../quality/lessons_learned.md) — *the commit that lands the work
> updates the row in the same commit*. Sibling of [BP-069](../quality/best_practices.md), which says
> what a row **is**; this says **when it is written**.

## What this file is

`check_board_currency.py` asserts that a `tasks*.md` row does not contradict the commit log. It
reads two inputs the row's author does not control — the boards, and `TASK-NNN` in **commit
subjects** — and reports three contradictions: a row reading OPEN/BLOCKED with commit traffic
(**B1**), a closed row citing no hash (**B2**), and a row blocked on a task that has closed
(**B3**). The gate's own docstring is its specification, **including the four things it cannot
see**; read it before quoting a green result.

It lands **blocking**, against this ledger, on the bargain ROWLEN and C6 already made on this
project: blocking-plus-a-dated-shrink-only-ledger is strictly stronger than advisory-at-any-count,
because an advisory count is scrolled past and a ledger row that stops failing is **itself a
failure**.

## Opening size, measured 2026-09-07 against the post-`0dba35a` tree

| check | findings | note |
|---|---|---|
| **B1** stale-open | **4** | all four on `tasks-architecture.md` — the one board the PM's reconciliation did not touch. **These are not amnesty**: each is a live, actionable finding, listed here so it is dated and owned rather than lost in a report. @PM's to clear. |
| **B2** uncited-closure | **68** | of 124 classified closed rows. Too many to clear in the commit that lands the gate; this is the pre-rule backlog, and every row here names the hash the log offers where one exists. |
| **B3** closed-blocker | **0** | **9 on the tree before `0dba35a`.** The PM's reconciliation is what put B3 at zero; this gate is what keeps it there. It is therefore blocking at zero with no ledger rows at all. |

## The rules that make this a gate and not an amnesty

1. A row here suppresses **one** finding, keyed on `(kind, board file, the row's own TASK- id)`.
   Never on a line number: board rows move on every edit, and a key that moves is an exemption that
   silently transfers to a different row. The board is part of the key so an exemption cannot follow
   an id onto a different board.
2. **A stale row is a BLOCKING failure (B4).** When a row stops producing its finding — a hash is
   added, a status is corrected, a blocker is renamed — this gate fails with `stale exception …
   delete this row` until the row here is removed. **The list can only shrink.**
3. There is **no file, directory or wildcard exemption**, and `B4` itself is not exemptable.
4. Every row carries an owning `TASK-` id and an ISO `since` date, both machine-checked. A malformed
   row is a blocking failure, not a skipped one.
5. When the last row goes, **delete this file**. An exemption list holding zero rows is a
   half-finished retirement and the shape the next amnesty grows back from.

## The rows

| board | row | kind | why | owner | since |
|---|---|---|---|---|---|
| `docs/project/tasks-harness2.md` | `TASK-564` | uncited-closure | pre-rule closure, uncited; the log offers `1ae7557` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-574` | stale-open | pre-rule: work landed under this id (`6e5f866`) and the row was never reconciled | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-576` | stale-open | pre-rule: work landed under this id (`e58c2a3`) and the row was never reconciled | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-577` | stale-open | pre-rule: work landed under this id (`2fd8c0e`) and the row was never reconciled | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-581` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-583` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-584` | uncited-closure | pre-rule closure, uncited; the log offers `d95a13c` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-585` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-587` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-591` | uncited-closure | pre-rule closure, uncited; the log offers `930c51b` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-596` | uncited-closure | pre-rule closure, uncited; the log offers `7f8109e` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-598` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-602` | uncited-closure | pre-rule closure, uncited; the log offers `17e973e` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-603` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-608` | uncited-closure | pre-rule closure, uncited; the log offers `86184b1` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-611` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-619` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-622` | uncited-closure | pre-rule closure, uncited; the log offers `6c5f6c1` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-624` | uncited-closure | pre-rule closure, uncited; the log offers `2e277fd` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-625` | uncited-closure | pre-rule closure, uncited; the log offers `0c24803` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-626` | uncited-closure | pre-rule closure, uncited; the log offers `372b7a2` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-627` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-628` | uncited-closure | pre-rule closure, uncited; the log offers `284193f` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-629` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-630` | uncited-closure | pre-rule closure, uncited; the log offers `c607672` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-631` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-632` | uncited-closure | pre-rule closure, uncited; the log offers `61f5af7` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-633` | uncited-closure | pre-rule closure, uncited; the log offers `26ba5af` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-644` | uncited-closure | pre-rule closure, uncited; the log offers `81b1ee9` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-645` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-646` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-647` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-661` | uncited-closure | pre-rule closure, uncited; the log offers `2ae9374` | TASK-669 | 2026-09-07 |
| `docs/project/tasks.md` | `TASK-659` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks.md` | `TASK-660` | uncited-closure | pre-rule closure, uncited; the log offers `bd38844` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-harness2.md` | `TASK-679` | stale-open | the only commit naming it is its own filing (`7f24f9f`, "file TASK-679 …"), the docstring's case 2 — no work has landed; B4 retires this row when the status changes | TASK-679 | 2026-09-11 |
| `docs/project/tasks-harness2.md` | `TASK-682` | stale-open | the only commit naming it is the board reconciliation that filed it (`30fe518`, "…TASK-682"), the docstring's case 2 — no work has landed; B4 retires this row when the status changes | TASK-682 | 2026-09-12 |
| `docs/project/tasks.md` | `TASK-710` | stale-open | the only commit naming it is TASK-693's triage that filed it (`6a0f3144`), the docstring's case 2 — no work has landed; B4 retires this row when the status changes | TASK-710 | 2026-09-17 |
| `docs/project/tasks.md` | `TASK-711` | stale-open | the only commit naming it is TASK-693's triage that filed it (`6a0f3144`), the docstring's case 2 — no work has landed; B4 retires this row when the status changes | TASK-711 | 2026-09-17 |
| `docs/project/tasks.md` | `TASK-702` | stale-open | the only commit naming it is the scope-tension design note itself (`67d1b935`), the docstring's case 2 — no work has landed, the row is honestly BLOCKED pending a human ruling; B4 retires this row when the status changes | TASK-702 | 2026-09-17 |
| `docs/project/tasks-harness2.md` | `TASK-672` | stale-open | the only commit naming it is the PM correction that says it is NOT unblocked (`cae26a8a`, "TASK-672 still needs a field-level instrument"), the docstring's case 2 — no work has landed; B4 retires this row when the status changes | TASK-672 | 2026-09-19 |
| `docs/project/tasks-harness2.md` | `TASK-613` | stale-open | the only commit naming it is TASK-606's hash-citation commit (`b52ab87f`), which unblocked it and said so in its subject — the docstring's case 2; no work on 613 has landed. B4 retires this row when the status changes | TASK-613 | 2026-09-19 |
