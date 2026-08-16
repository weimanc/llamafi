# Handover — TASK-488 + TASK-497 (DUT attached)

> Written by the Architect, 2026-08-16, for a fresh agent. Follows **BP-060**: every diagnostic claim
> below is labelled **[MEASURED]**, **[INFERRED]** or **[ASSUMED]**, and **you have standing
> permission to contradict any of it.** If something here does not hold, say so and stop — do not
> work around it.

## Your job, in one line

Three refactor commits are on `master`, unreviewed and never run on hardware. **Verify them, or
revert them.** Then take the baseline that should have been taken before they landed.

## Read first, in this order

1. `docs/project/tasks-architecture.md` → **§ TASK-488 — pass criteria**. Eleven ids, `T_488_01`–`11`,
   with explicit fail conditions and an explicit *not-a-pass* list. **That section is your spec — this
   note does not restate it, and if the two disagree, the spec wins.**
2. `docs/architecture/designs/M-SRCLAYOUT-main-decomposition.md` §5a (what landed) and §7a (the
   static-review recipe).
3. `docs/process/dut_workflow.md` and `CLAUDE.md` § *Run scripts* — the hardware rules.

## What you are verifying — [MEASURED, from `git log`]

| Commit | Claim |
|---|---|
| `a044f5d` | `App` interface → `app.h`; three state structs deleted (`SpotifyAppState`, `ClockAppState`, `AquariumAppState`) |
| `78caa95` | Seven App classes → `apps/*.h` (1 581 lines) |
| `b36f184` | SERIAL_DEBUG console → `debug/serialConsole/*.h` (2 579 lines) |

All three **claim to be pure moves**. That claim is **[ASSUMED]** — it is the thing you are testing.

## What is true, and how well

- **[MEASURED]** `./run/check` is 11/11 green across all 7 envs, as of `86dd2a1`.
- **[MEASURED]** `./run/check` was *also* green when these three commits landed. **It proves
  compilation, not behaviour.** Do not accept it as evidence of correctness.
- **[MEASURED]** No DUT baseline was ever taken for these commits, despite ADR-059 D13 requiring one.
  That is TASK-497.
- **[INFERRED]** Because all three are text moves, the pre-refactor tree still exists in git, so a
  retrospective baseline is still obtainable. This was @VE's ruling and I agree — but it is inference,
  not measurement. If checking out `78caa95~1` turns out not to build, say so immediately; the whole
  of TASK-497 rests on it.
- **[ASSUMED]** That the moves are behaviour-neutral. Four reviewers found 16 defects in this
  session's documents and 15 held. **Assume this claim is wrong until Part A says otherwise.**

## Order of work

1. **Part A first — host only, no device.** It can fail the task in minutes and save you a DUT
   session. If `T_488_01` (byte-identity) fails, **stop and report**; do not proceed to hardware.
2. **Snapshot persisted state before touching the device** — BP-049. `./run/spiffs pull` and keep
   `settings.json` aside with a timestamp. Verify it byte-identical at the end. This is not optional;
   TASK-329 ate real user data and was recoverable only because a snapshot happened to exist.
3. **TASK-497's baseline and TASK-488's Part B share one hardware block.** Run the suite 3× at
   `78caa95~1`, then 3× at `HEAD`, then Part B. Flashing between trees is the expensive part — do not
   split this across two sessions.
4. Part B, per the spec.

## Hardware rules — violating these costs a re-flash or a wedged device

- **Use `run/` scripts only.** Never raw `pio` or `tmux`. They handle port resolution, monitor
  lifecycle and DUT safety. `./run/flash-debug` deliberately leaves the monitor down for the harness.
- **Never externally kill a `run/flash*`, `run/test*` or soak script mid-flight.** No `timeout`, no
  Ctrl-C, no task-stop. They are trap-guarded and race the prod-restore; killing one can boot-loop the
  device. **[MEASURED — four separate occurrences.]** Host sleep is the same risk via USB reset: hold
  `systemd-inhibit --mode=block` for anything long and detached.
- **Do not pipe a long backgrounded `run/test` through `tail`.** It discards the PASS/FAIL summary and
  keeps only the final prod-restore flash. Let the harness capture full output.
- **`T_488_11` measures heap — do not trust any heap number before ~150 s post-reset.**
  **[MEASURED]** `lfb8` read 69620 / 32756 / 30708 at 30 s / 90 s / 150 s on the same boot. Take the
  reading late, and take before/after at the *same* uptime offset or the comparison is meaningless.

## What "done" means

- Every id in the spec is **PASS**, **FAIL**, or **SKIPPED-with-reason**. Not "looked fine".
- **On any Part B failure: revert the offending commit, do not patch forward.** These are moves;
  reverting is cheap, and debugging an unverified refactor is not. This is a standing instruction,
  not a suggestion.
- Report which of the three commits you verified, which you reverted, and the raw evidence.

## What NOT to do

- Do not fix anything you notice in passing. File it. This session's scope is verification only.
- Do not touch `app/src` beyond a revert.
- Do not proceed past a failing `T_488_01`.
- Do not close a criterion you could not run. Mark it skipped.

## If it all passes

Say so plainly, and update `tasks-architecture.md` — mark TASK-488 and TASK-497 done with the
evidence, and change M-SRCLAYOUT §5a's status from *"PENDING REVIEW"* to verified, naming your run.
Six tasks are gated behind this; **the next agent needs to see it closed, not infer it.**
