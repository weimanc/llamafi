# Handover — pick up the test-harness programme

> Owner: Project Manager
> Status: accepted
> Opened: 2026-09-04 · Programme: [M-HARNESS2](../verification/M-HARNESS2-requirements.md)

This file exists so a session can be started with one sentence and still follow the process.
It is a pointer, not a plan: **the board is the plan.**

---

## The prompt

Paste this, and nothing else:

> Continue the M-HARNESS2 programme. Read `docs/project/HANDOVER.md`, then take the next
> unblocked row from `docs/project/tasks-harness2.md` in phase order and execute it under the
> standing rules. Report what you did and what the gates said; commit only what passes.

That is the whole handover. Everything below is what the reader will find when they follow it.

---

## Where the work lives

| what | where |
|---|---|
| **The sequence** — every task, in phase order, with dependencies and stop criteria | [`tasks-harness2.md`](tasks-harness2.md) |
| Why each task exists — 55 numbered requirements | [`M-HARNESS2-requirements.md`](../verification/M-HARNESS2-requirements.md) |
| What was cut and why (~60 days) | [PM review §4.1](M-HARNESS2-PM-review.md) |
| The evidence under all of it — 216 tests audited one by one | [`reviews/M-TESTQUAL-Z-findings-review.md`](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| The four reviews that reshaped the proposal | [Architect](../architecture/designs/M-HARNESS2-architect-review.md) · [Developer](../architecture/designs/M-HARNESS2-DEV-review.md) · [QM](../quality/M-HARNESS2-QM-review.md) · [PM](M-HARNESS2-PM-review.md) |
| Roles, ownership, who decides what | [`docs/agents/AGENTS.md`](../agents/AGENTS.md) |
| Rules with teeth | [`best_practices.md`](../quality/best_practices.md) — BP-073 and BP-074 are new and bind this work |
| The machine, the run scripts, the DUT workflow | [`CLAUDE.md`](../../CLAUDE.md) · [`dut_workflow.md`](../process/dut_workflow.md) |

**Read order for a cold session:** this file → the board's header and your phase's criteria → the
requirement your row cites. Three documents, not fifteen. The audit packages are evidence to cite
when a row's justification is challenged, not required reading.

---

## Standing rules — these are not negotiable per-task

1. **No gate lands advisory.** A new check lands at zero, or blocking with a dated, owned,
   shrink-only ledger whose stale rows are themselves failures. `check_docs` C3 is the standing
   demonstration of the alternative: advisory since it was written, 58 failures then, 60 now.
2. **No declaration without a mechanical check behind it.** A field a hurried author can fill with
   a plausible lie is not a control (QM review §4).
3. **A gate without a negative test is not a gate** (BP-068). Prove it can fail, in the same commit.
4. **Move, never delete.** No id's last remaining row is deleted, whatever file it sits in. A copy
   that outlives its original is not a copy — see [board-reset proposal §7.1](M-HARNESS2-board-reset-proposal.md).
5. **The DUT is pinned.** TASK-557 keeps the board on the `-DBOD_WATCH` debug build. Restoring
   production is forbidden; rebuilding and flashing *the same debug env* is permitted, provided
   `-DBOD_WATCH` survives (human ruling, 2026-09-03). Never kill a `run/flash*`/`run/test*` script
   mid-flight — it races the trap-guarded restore.
6. **Never import a module under `app/tools/` to inspect it — read it.** Six of them used to run a
   DUT suite at import; `check_import_safety` now enforces that they do not, and that gate is the
   only reason importing is safe at all.
7. **Write long documents incrementally**, saving as you go. Five agent runs on this programme were
   killed mid-flight by session limits; the ones that wrote as they went lost a tail, the one that
   held its work in memory lost a package.

---

## How to execute a row

1. **Pick** the first row in the lowest phase whose status is `OPEN` and which is not `BLOCKED`.
   Phase order is real: a phase's entry criterion is stated once at the head of its section.
2. **Read** the requirement the row cites. The row is a pointer; the requirement is the spec.
3. **Build it**, with its negative test.
4. **Run** `./run/check` and `./run/check-docs`. Both must pass. Report the wall clock — phase 1's
   exit criterion caps `run/check` at 90 s and it is at ~118 s today.
5. **Commit** with the task id in the subject, and **close the row in the same session** with the
   commit hash. A board that lags the tree is how this project got a 51-row mirror that disclaimed
   itself.
6. **If a phase's stop criterion fires, stop and escalate.** They exist because three of them can
   cancel work that is already scheduled — most sharply, if the phase 2 session refutes all three
   injector clusters, phase 3 is cancelled outright.

---

## State as of 2026-09-04

**61 rows, ~81 engineer-days, six phases. Six rows closed.**

| phase | rows | open | blocked | days | status |
|---|---|---|---|---|---|
| 0 — decisions | 6 | 2 | 0 | ~1 | 4 discharged; TASK-619 (@Architect) and TASK-622 (five ADRs) remain |
| 1 — host-only foundation | 21 | 7 | 11 | ~28.5 | **in progress, committed** — day 1 landed `8927b16` |
| 2 — the 80-minute DUT session | 11 | 2 | 9 | ~6 | scheduled; runs in parallel with phase 1 |
| 3 — order and state hygiene | 6 | 0 | 6 | ~7.5 | blocked on TASK-557 and phase 2 |
| 4 — observability contract | 4 | 0 | 4 | ~10 | blocked on TASK-622's ADRs |
| 5 — ratchets | 13 | 0 | 13 | ~28.5 | blocked on phases 1 and 3 |

**Only phase 1 is funded.** Everything else is sequenced, not committed.

**Next unblocked row:** phase 1's `TASK-624` — the typed verdict and the `UNMET` bucket, which is
what unblocks most of the rest of the phase. `TASK-622` (file the five ADRs) is the other thing
worth doing early: it is a day of writing that unblocks all of phase 4.

**What is deliberately not here:** ~60 engineer-days cut at review. Do not re-file one without
reading why it was cut — several were cut for having no completion condition, and re-filing them
restores exactly that defect.
