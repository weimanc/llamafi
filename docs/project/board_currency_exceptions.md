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
| `docs/project/tasks-architecture.md` | `TASK-474` | uncited-closure | pre-rule closure, uncited; the log offers `087f283` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-489` | uncited-closure | pre-rule closure, uncited; the log offers `575a034` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-490` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-493` | uncited-closure | pre-rule closure, uncited; the log offers `0622f79` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-494` | uncited-closure | pre-rule closure, uncited; the log offers `0a90625` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-497` | uncited-closure | pre-rule closure, uncited; the log offers `bd7282d` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-500` | uncited-closure | pre-rule closure, uncited; the log offers `55ad417` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-501` | uncited-closure | pre-rule closure, uncited; the log offers `9957f4f` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-502` | uncited-closure | pre-rule closure, uncited; the log offers `f250433` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-504` | uncited-closure | pre-rule closure, uncited; the log offers `2951b42` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-507` | uncited-closure | pre-rule closure, uncited; no commit subject names this id | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-533` | uncited-closure | pre-rule closure, uncited; the log offers `905a0dd` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-534` | uncited-closure | pre-rule closure, uncited; the log offers `5b087b5` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-535` | uncited-closure | pre-rule closure, uncited; the log offers `4ef73b1` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-540` | uncited-closure | pre-rule closure, uncited; the log offers `045b797` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-543` | uncited-closure | pre-rule closure, uncited; the log offers `91e3758` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-545` | uncited-closure | pre-rule closure, uncited; the log offers `39c7df6` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-546` | uncited-closure | pre-rule closure, uncited; the log offers `4ac9c6a` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-547` | uncited-closure | pre-rule closure, uncited; the log offers `3555e0d` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-548` | uncited-closure | pre-rule closure, uncited; the log offers `aceeebe` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-550` | uncited-closure | pre-rule closure, uncited; the log offers `c2e9c30` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-551` | uncited-closure | pre-rule closure, uncited; the log offers `a4a80b5` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-552` | uncited-closure | pre-rule closure, uncited; the log offers `6800280` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-554` | uncited-closure | pre-rule closure, uncited; the log offers `dc4abca` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-555` | uncited-closure | pre-rule closure, uncited; the log offers `4c7381e` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-556` | uncited-closure | pre-rule closure, uncited; the log offers `520d5ab` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-558` | uncited-closure | pre-rule closure, uncited; the log offers `9707998` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-559` | uncited-closure | pre-rule closure, uncited; the log offers `f5d3d07` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-560` | uncited-closure | pre-rule closure, uncited; the log offers `67f6c26` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-561` | uncited-closure | pre-rule closure, uncited; the log offers `3596a7b` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-563` | uncited-closure | pre-rule closure, uncited; the log offers `a9ab248` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-564` | uncited-closure | pre-rule closure, uncited; the log offers `1ae7557` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-565` | uncited-closure | pre-rule closure, uncited; the log offers `66d0b95` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-570` | uncited-closure | pre-rule closure, uncited; the log offers `3cd37a3` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-571` | uncited-closure | pre-rule closure, uncited; the log offers `25394ce` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-572` | uncited-closure | pre-rule closure, uncited; the log offers `7e5a874` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-573` | stale-open | pre-rule: work landed under this id (`2a43a11`) and the row was never reconciled | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-574` | stale-open | pre-rule: work landed under this id (`6e5f866`) and the row was never reconciled | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-575` | uncited-closure | pre-rule closure, uncited; the log offers `8181a8d` | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-576` | stale-open | pre-rule: work landed under this id (`e58c2a3`) and the row was never reconciled | TASK-669 | 2026-09-07 |
| `docs/project/tasks-architecture.md` | `TASK-577` | stale-open | pre-rule: work landed under this id (`2fd8c0e`) and the row was never reconciled | TASK-669 | 2026-09-07 |
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
