# EXP-040 — what a HEALTH phase actually costs `run/player-gate` → subset `T_DH_01` + `T_DH_03`

> Owner: R&D · registered 2026-09-12 · operator: Opus · instrument: `run/dut-health`, unmodified.
> Decides the open half of **TASK-597** ([tasks-harness2.md](../../project/tasks-harness2.md)).
> Governing design doc for the gate: [M-TESTBASE phase 1](../../architecture/designs/M-TESTBASE-phase1-player-gate.md)
> — which, note, says **nothing** about a health premise; see §5.
>
> **§1–§5 were registered BEFORE the measurement** (commit `425d44d`), §6–§8 written after it from
> two runs on 2026-09-12. §3's decision rule and §4's falsifiers are as registered and were not
> edited once the numbers existed — that is the whole value of the split, and `git log -p` on this
> file is the check.

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

## 6. Results — measured 2026-09-12, two runs

`./run/flash-player` then `DUT_ENV=cyd2usb_player ./run/dut-health`, twice. Both exit **0**.

| field | run 1 | run 2 |
|---|---|---|
| board id / source | `d48afcc8eed0` / efuse-mac | same |
| build_env · elf · expected | `cyd2usb_player` · `1f00a52c` · `1f00a52c` | same |
| generation | 15.1 | 16.1 |
| `T_DH_01` | PASS (`variant=off playerMode=Spotify`) | PASS |
| `T_DH_02` | **PASS** — `ip=192.168.1.181 ssid='<home-ssid>'` | PASS |
| `T_DH_05` | PASS — 25/25 round trips bit-exact | PASS |
| `T_DH_03` entry → neighbour → exit | **Spotify → Clock → Spotify**, idle at each step | same |
| `freeInt` before → after | 118832 → 118832 (**Δ 0**) | 118844 → 118844 (**Δ 0**) |
| `lfbInt` before → after | 73716 → 73716 (**Δ 0**) | 73716 → 73716 (**Δ 0**) |

**§3 rule applied in order.** Row 1 does not match (`T_DH_02` PASSes). Row 2 does not match
(neighbour was Clock, not Spotify; Δ`lfbInt` = 0 < 4 096). **Row 3 matches** — all four pass and
Δ`lfbInt` < 4 096.

> **Premise adopted: subset `T_DH_01` + `T_DH_03`.**

Row 4 also matches on the data, and is deliberately ordered second: adopting the network premise
requires an explicit judgement that it *is* one for local SD playback, and this measurement cannot
supply that. `T_DH_02` passing costs nothing — but the concern was never cost. It was that
`T_DH_02` can fail for a reason irrelevant to local playback and then refuse the gate, and a
passing run says nothing about an intermittent one. The ordering was written for exactly this
outcome and is honoured rather than re-argued now that the numbers are in.

## 7. What the Q2 answer does and does not settle

**The Spotify excursion did not occur, and is bounded — but was never exercised.** The neighbour is
`"Clock" if entry != "Clock" else "Spotify"`, and entry was Spotify both times, so the branch that
worried §1 was not taken. That is not the same as disproving it.

What bounds it: **every `runner.py` invocation opens the port, and opening the port resets the
board** (the `gen` increment, 15.1 then 16.1, is that reset). So a leg's entry app is always the
*boot default*, never what a previous leg left behind — and on `cyd2usb_player` the boot default is
Spotify, observed twice. The hazard therefore requires the boot default itself to become Clock.

**Residual condition, to re-check if it ever changes:** if `cyd2usb_player`'s boot app becomes
Clock, `T_DH_03`'s neighbour becomes Spotify, and this experiment must be re-run before the subset
is trusted. Recorded here rather than left to memory.

**The arena answer is unambiguous and stronger than the threshold needed.** Δ`lfbInt` = 0 and
Δ`freeInt` = 0 on both runs, from fresh `get heap` reads either side of the phase — not a cached
line. The 4 096 B prior was never approached, so §3's instruction about re-arguing a near-threshold
result does not apply.

## 8. Next step, and the falsifier that governs it

§4 holds one live falsifier against the adopted option: *"Any subset at all is wrong if
per-entry-point health selection costs more code than the coupling it removes — if it exceeds ~40
lines, re-open the question."*

`health_selected = list(health_tests)` is all-or-nothing today (`runner.py`), so the subset needs a
`--health-ids` selector: an argparse entry, validation against the health registry, the assignment,
one line in `run/player-gate`, and a test arm. **Size it against the 40-line budget before building
it.** If it exceeds the budget, the honest move is the full class with `T_DH_02`'s refusal risk
accepted and written into M-TESTBASE — not a larger mechanism justified after the fact.

Whichever lands, the decision belongs in
[M-TESTBASE phase 1](../../architecture/designs/M-TESTBASE-phase1-player-gate.md) per BP-065 — the
document that currently does not mention health at all (§5.1).
