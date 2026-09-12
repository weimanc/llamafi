# EXP-040 — what a HEALTH phase actually costs `run/player-gate` (PRE-REGISTERED, no results yet)

> Owner: R&D · registered 2026-09-12 · operator: Opus · instrument: `run/dut-health`, unmodified.
> Decides the open half of **TASK-597** ([tasks-harness2.md](../../project/tasks-harness2.md)).
> Governing design doc for the gate: [M-TESTBASE phase 1](../../architecture/designs/M-TESTBASE-phase1-player-gate.md)
> — which, note, says **nothing** about a health premise; see §5.
>
> **This document is registered BEFORE the measurement.** §3 fixes the decision rule and §4 states,
> per option, the result that would make it wrong. Nothing in §6 is filled in yet. If you are
> reading §6 and it is still empty, the experiment has not been run.

## 1. The question, and why it is open

WP-E finding `E-13`: `run/player-gate` carries a full exit-4 apparatus — `_HEALTH_FAIL`, a "the
BOARD was not a valid test subject" refusal, and `_assert_health_premise()` refusing to run at all
under `DUT_HEALTH=warn|skip` — while invoking the runner in a way that runs **no health check at
all**. It polices the integrity of a premise it never establishes.

The mechanism half landed 2026-09-12 (`e8ba10f`): `--health-phase` makes the HEALTH gate selectable
without adopting the held `--class-order` switch (TASK-617). The wiring — one line in
`_run_runner_leg()` plus a selftest arm — is **written and deliberately not landed**, because it
changes what a release gate demands of the board in two ways that cannot be settled host-side:

- **`T_DH_02` asserts network health.** The player gate exercises local SD playback and has never
  needed the network. Wiring this makes a wifi blip refuse the gate.
- **`T_DH_03` is declared `effect="mutating"`** and switches to a neighbour app and back. Its
  neighbour is `"Clock" if entry != "Clock" else "Spotify"`. On a `-DDISABLE_SPOTIFY` build
  `g_apps[Spotify]` is still populated (only the network side is compiled out), so the switch
  probably *succeeds* — and "probably" is the problem on an arena-sensitive gate, given TASK-442
  measured Spotify code costing 43 596 B on exactly such a build.

`T_DH_05` is also `effect="mutating"` (GRAM readback, ADR-064 D4).

## 2. The instrument already exists — this experiment adds no code

Stated explicitly because the first draft of this plan proposed building instrumentation that was
already there, which is the failure BP the tooling lesson names (inventory `app/tools` first):

- **Arena cost needs nothing.** On the `--dut-health` path `_health.premise()` is printed **twice** —
  once before the health phase (`runner.py:441`) and again after it (`:450`) — and each line already
  carries `freeInt=` and `lfbInt=`. The cost is the difference between two lines that already print.
- **The neighbour needs nothing.** `T_DH_03` already prints `[T_DH_03] entry appId: <name>`, and the
  neighbour is a pure function of it. The entry value *is* the answer.

**The build guard is the one subtlety.** `run/dut-health` does not call `require_build`, so it never
declares an env; the ELF guard still fires, but from `lib/dut.py`'s ambient
`_DUT_ENV = os.environ.get("DUT_ENV", "cyd2usb_winamp_debug")`. A player-flashed board therefore
refuses a bare `./run/dut-health` with `elf-mismatch` (exit 3) naming the *wrong* wanted build. The
env must be passed explicitly — the pattern `run/lib.sh:30` already documents:

```sh
./run/flash-player                                  # player build on the board
DUT_ENV=cyd2usb_player ./run/dut-health             # HEALTH class, that env's guard
```

Worth recording as a finding in its own right (§5): every other DUT entry point *declares* its build
via `require_build`; this one verifies against whatever `DUT_ENV` happens to hold.

## 3. What to read, and the decision rule — fixed before the data

Run the command above. Read exactly these fields.

| # | question | field |
|---|---|---|
| Q1 | does `T_DH_02` pass on this env? | its own verdict line |
| Q2 | which neighbour does `T_DH_03` pick, and does the switch take? | `[T_DH_03] entry appId:` + its verdict |
| Q3 | what does the health phase cost the arena? | `lfbInt` and `freeInt` on the two `[health]` premise lines |

**The rule, in order. Apply the first row that matches.**

| if | then adopt |
|---|---|
| `T_DH_02` FAILs or is UNMET on a healthy board | **subset `T_DH_01` only** — a premise the env cannot satisfy is not a premise |
| `T_DH_03` picks Spotify, or Δ`lfbInt` ≥ 4 096 B | **subset `T_DH_01` only** — the excursion is not free on an arena-sensitive gate |
| all four pass and Δ`lfbInt` < 4 096 B | **subset `T_DH_01` + `T_DH_03`** — switch health is a real premise for a gate that switches modes |
| all four pass, Δ`lfbInt` < 4 096 B, **and** `T_DH_02` is judged a genuine premise for local playback | **full class, the held patch unchanged** |

The 4 096 B threshold is a declared prior, not a measurement: it is ~10 % of the 43 596 B TASK-442
attributed to Spotify on a `DISABLE_SPOTIFY` build, i.e. small enough that the excursion is noise
against a cost already known to matter. If the measured Δ lands near it, say so and re-argue the
threshold in §6 — do not silently round it.

## 4. What would make each option wrong

An experiment that cannot falsify its options is a rationalisation with a table.

- **Subset `T_DH_01` only** is wrong if `T_DH_02` and `T_DH_03` both pass cleanly and cost ~0 —
  then it discards real premise coverage for nothing.
- **Subset `T_DH_01` + `T_DH_03`** is wrong if `T_DH_03` picks Spotify on this build, or if its
  restore does not return the entry app: a mutating excursion that does not restore is worse than
  no check.
- **Full class** is wrong if `T_DH_02` can fail while local SD playback is perfectly testable —
  which is the whole of the concern, and Q1 answers it directly.
- **Any subset at all** is wrong if per-entry-point health selection turns out to cost more code
  than the coupling it removes. `health_selected = list(health_tests)` is all-or-nothing today, so
  a subset is new mechanism; if it exceeds ~40 lines, re-open the question rather than build it.

## 5. Collateral findings, registered here so they are not lost

1. **`M-TESTBASE-phase1-player-gate.md` contains no occurrence of "health".** The gate's refusal
   machinery was built without its governing design doc ever specifying a health premise. That is
   very likely *why* it was built decoratively: nothing said what it had to require, so nothing
   noticed it required nothing. Whichever option §3 selects, the decision belongs in that document
   (BP-065), not only in a commit message.
2. **`run/dut-health` declares no build** (§2). Every other DUT entry point calls `require_build`;
   this one inherits `DUT_ENV`'s default. Not fixed here — named for TASK-597's successor or a
   separate ADR-067 conformance row.
3. **Baseline freshness, checked 2026-09-12.** `player-gate-baseline.md` was last touched
   2026-09-05 (TASK-603). Since then TASK-595 declared **`T_PLR_07`**, an A-leg cell whose baseline
   row reads `PASS`. It calls `flake()`, so it can now resolve `FLAKY-PASS`. `_compare_leg` scores
   `PASS:FLAKY-PASS` in its own bucket — visible, non-fatal, not laundered into a pass — so this is
   **not** a regression, but the row should carry a note once the gate has actually run and produced
   the outcome. Deliberately not edited in advance of evidence. `T_PMT_04` and `T_PLR_17` lost their
   declarations in the same sweep, but neither ever called `flake()`, so neither changes behaviour.

## 6. Results

**NOT YET RUN.** Fill from one `DUT_ENV=cyd2usb_player ./run/dut-health` against a player-flashed
board, recording the board id and ELF the run prints, then apply §3's rule and record which row
matched.

| field | value |
|---|---|
| date / operator | |
| board id / elf / build | |
| `T_DH_01` | |
| `T_DH_02` | |
| `T_DH_03` — entry appId → neighbour | |
| `T_DH_05` | |
| `freeInt` before → after (Δ) | |
| `lfbInt` before → after (Δ) | |
| exit code | |
| **§3 row matched → premise adopted** | |
