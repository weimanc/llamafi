# Design — M-TESTBASE phase 1: a base test framework, scoped to the 3-mode player

> Owner: Architect + VE
> Status: **proposed, revised after @Architect design review** — 2026-08-17
> Review record: §7. Five blockers were upheld; P2/P3/P4 are re-scoped and P0 is new.
> Goal (human, 2026-08-16): *reduce the noise that is making M-WINAMP-PLAYER unimplementable.*
> Parent: [M-TESTARCH](M-TESTARCH-test-architecture.md) · [M-QUALITY map](M-QUALITY-improvement-map.md) ·
> [VE review](M-TESTARCH-VE-review.md)
> Serves: [M-WINAMP-PLAYER](M-WINAMP-PLAYER-local-playback.md) — Spotify / WebRadio / LocalPlayer

**This document deliberately drops most of the quality programme.** M-QUALITY maps nine areas; this
plan funds four items and explicitly defers the rest. The selection criterion is single and strict:
**does it reduce the noise in the 3-mode player, now?** Everything that does not, waits — including
work this same author argued for two documents ago.

---

## 1. The whack-a-mole is not diffuse. It is located.

Measured against `cross_feature_matrix.yaml` (65 interactions):

| Measure | Value |
|---|---|
| Interactions involving the player surface | **26 of 65 (40 %)** — for one of thirteen apps |
| High-risk interactions with **zero** test coverage | 8 |
| …**of those, in the player area** | **7 of 8** |

The seven: `X052` (SD × LocalPlayer, two tasks on the filesystem), `X054` (pleditView absorbed
`drawPlaylist()` wholesale), `X055` (WebRadio's independently-evolved PLEDIT copy), `X057` + `X064`
(taskbar asserts WebRadio is the **last** `AppId`), `X061` (capability mask rewrites the Spotify-only
zone hardcoding), `X062` (**shuffle permutes `playOrder[]`; `viewOrder[]` — what PLEDIT renders and
what SAVE writes — is never touched**).

**That is the shape of whack-a-mole, written down in the project's own artifacts before anyone asked.**
Every one is a *shared-state or dependency* coupling between two modes. Fix mode A, break mode B, with
no test that can observe the break — because no test covers any of them.

Churn agrees: `main.cpp` 164 commits, `webRadioApp.h` 57, `winampDisplay.h` 31, and **30 of ~93
player-area commits carry a fix/revert/regress marker in the subject line.**

> **CORRECTED — @Architect review, 2026-08-17. "No test covers any of them" is overstated, and this
> document made the error it warned about.** 26 of the 56 orphan runner ids M-TESTARCH §1 counts are
> `T_PLR_01..26`, and `app/tools/test_playorder_player.py:9` documents that **T_PLR_20-24/26 — the
> shuffle bag — already exercise X062's subject** on `cyd2usb_winamp_debug` via the
> `advance` / `set plCursor` / `get plOrder` surface. `winamp/winampDisplay.h:158` likewise cites
> `T_PLR_17` for the CAP_TRANSPORT invariant behind X061. Both interactions still record
> `test_coverage: []`.
>
> M-TESTARCH §1 proved that `cross_feature_matrix.yaml` is drifted **in both directions**; this
> document then built its case on the un-drifted reading of that same file. **What is established is
> that the seven couplings are untested *as interactions*, and that the bookkeeping cannot tell us how
> much of the underlying mechanics is already covered.** That is still a real problem — but it makes
> **P0 (§4) the first item, not P1.**

**Conclusion: the noise is concentrated, not diffuse — seven couplings in the one subsystem being
actively built, of unknown existing coverage.** That is a far smaller problem than the quality
programme, and the first move against it is free.

## 2. Why the instrumentation cannot see it

Thirty player-related debug keys exist: `wrState`, `wrPlaying`, `wrIdx`, `wrPump`, `wrEject`,
`wrHeap`, `plCount`, `plOrder`, `plCursor`, `plMem`, `playerMode`, `aePlay`, `arenaStats` …

**They are organised by implementation silo, not by contract.** `wr*` answers questions about
WebRadio; `pl*` about the playlist model; `aePlay` about the audio engine. To ask *"is the player slot
in a consistent state?"* — the only question that matters at a mode transition — you must issue eight
commands, correlate them by hand, and know which subset applies to the current mode.

**A cross-mode bug is invisible to a per-mode observation.** X061, X062 and X055 are precisely
cross-mode, and precisely unobservable. This is what "serial dbg designed for testing" means in
practice: the debug surface should expose the **contract that spans the modes**, not mirror the
modules that implement them.

## 3. Sequencing against M-SRCLAYOUT — interleaved at one seam, not sequential

**Amended 2026-08-16.** The first draft said "fix the instrument first" flatly. That is too coarse:
it misses a real collision between P4 and Stage D, and it reads as though all `main.cpp` work must
wait. It must not.

### 3.1 What the landed stages actually bought

M-SRCLAYOUT is blunt about its own Stages A/B:

> *"A and B moved text into headers; that shrank `main.cpp` but produced **no components** — the
> headers are not self-contained... the translation-unit count is unchanged at 8. Measured against
> D0's table, the tree after B violates SF.1, SF.11 and Lakos exactly as thoroughly as it did before."*

Two stages have bought line-count, not structure. **The structural payoff is Stage E** (per-component
`.h`/`.cpp` conversion — also the gate for the T1 unit tier), and E needs D, which needs C. Three
stages out. That is the honest cost of the `main.cpp` thread, and it is why phase 1 does not queue
behind it.

### 3.2 Coupling: phase 1 against Stages C/D/E

| Item | Reads | Relocated by C/D/E? |
|---|---|---|
| **P1** `lib/dut.py` | host Python only | **no** — zero coupling |
| **P2** `get player` | `g_settings.playerMode` (settingsStorage, L1); `wr*`/`ae*`/`pl*` (L1/L3) | **no** — none of it moves |
| **P3** transition matrix | host test bodies over P2 | **no** |
| **P4** `get idle` | `g_shellBusy`, `g_apps[]` | **YES — Stage D moves exactly these into `ShellState` / `appTable` (D0c, D3)** |

Three of four are insulated from the decomposition. One collides squarely.

### 3.3 The recommended order

1. **P1 → P2 → P3, now.** They touch nothing C/D/E relocates. This is the player noise fix and it is
   independent of the refactor.
2. **Stage C** (`setup()` → `boot/`, 631 lines verbatim). Unblocked — TASK-488 discharged the A/B
   review obligation and TASK-497's ≥3-run baseline was taken. Does not touch the player surface.
3. **Stage D *with* P4, as one piece of work.** D creates `ShellState`; `isIdle()` is a method on it.
   Writing `get idle` first means writing it twice; folding it into D costs almost nothing extra.
4. **Stage E.** The only stage with structural payoff, and the precondition for T1.

### 3.4 Why the test work is a precondition, not merely parallel

Each of C/D/E owes a `T_SRC_01` baseline: ≥3 full runs with the flaky set pre-declared (ADR-059 D13).
**A baseline taken on today's suite — 252 unnamed sleeps, no declared flaky set, 56 orphan ids —
cannot distinguish a regression from noise.** P1's single timeout policy and a declared flaky set are
what make that baseline mean anything.

That is the sequencing argument, and it comes from the project's own D13 rule rather than a
preference. The earlier framing ("you cannot use a broken instrument to verify the repair of the
workbench") stands as the intuition; §3.2 is the part that decides the order.

### 3.5 One debt owed before C

**TASK-464 is due now, at the end of Stage B**: 308 `main.cpp:NNN` citations across 49 documentation
files, plus 44 `main.cpp` references in `feature_inventory.yaml`, already invalidated. M-SRCLAYOUT
says pay it **once** at the end of B, not per-stage. Starting C/D without it lets those citations rot
further and makes the sweep larger.


## 4. Phase 1 — five items, in order

### P0 — reconcile the 26 orphan `T_PLR` ids against X052–X064 *(new, and it is free)*

**Do this before anything else is scheduled.** 26 of the 56 orphan runner ids are `T_PLR_01..26`;
`test_playorder_player.py:9` and `winamp/winampDisplay.h:158` both name specific ones as covering the exact
subjects of X062 and X061, while the matrix records `test_coverage: []` for both.

Output: a mapping table, interaction → covering test ids (or *genuinely uncovered*). Host-side, ~1 h,
no DUT, no firmware. **It may retire P3 cells before they are built**, and it is the only item here
that costs nothing. It also supplies exit criterion 3's missing half: without it, "every failing cell
maps to a named X0NN" produces reds that map to tests already passing under other names.

Owner: **@VE** — this is `test_plan.md`/`cross_feature_matrix` bookkeeping, VE's artifacts.


### P1 — `lib/dut.py`, scoped hard *(the enabler; everything else needs it)*

Extract `Dut` out of the 10 229-line suite. **Scope discipline: this is not TASK-480.** Do not split
the test bodies. Extract only:

- `Dut`, `_TeeSerial`, `SetupFailure`, the boot/ready cascade
- **`resolve_port()`** delegating to `run/port` — kills **13** argparse `/dev/ttyUSB0` defaults (25 files reference the literal at all)
- **one timeout policy** replacing **701** numeric `timeout=` literals: a default, a slow-op override, nothing else
- promote the private names the 16 importers already reach for (`_switch_to`, `_restore_spotify`)

Host-verifiable. No DUT time. Migrate the 16 importers a few per commit.

### P2 — `get player`: one aggregated state vector *(the instrumentation that adds value)*

A single key answering the whole player-slot contract in one line, identical shape in all three modes:

```
mode · caps mask · engine state · arena held · source bound
· playOrder len+hash · viewOrder len+hash · pending flags · last error
```

> **RE-SCOPED — @Architect review, 2026-08-17. "Aggregation, not new state" was wrong on two of the
> nine fields.** `viewOrder` is exposed **nowhere**: `PlaylistIndex::_view` is private with only
> `idAtView()` / `viewRowOfId()` accessors (`player/m3u.h:255-310`), while `playOrder` has `dbgOrder()`
> (`localPlayerApp.h:636`, `get plOrder`). Nothing reports **which `PlaylistSource` is bound** to
> PLEDIT — M5's whole subject. Both are new firmware surface, not aggregation.
>
> **And "identical shape in all three modes" is nominal.** `playOrder`/`viewOrder` exist only in
> LocalPlayer (`g_LocalPlayerApp::_pl`); Spotify's PLEDIT is `SpotifyQueueSource` over
> `copyQueueSnapshot()` (`winamp/winampDisplay.h:71`), WebRadio's is `StationListSource`
> (`webRadioApp.h:129`). Two of three modes report **N/A** for the two fields §4 claimed would make
> X062 observable.

**Honest scope: aggregation of ~6 existing keys, plus 2 new observables** (a `viewOrder` accessor, and
the bound `PlaylistSource`), with the playlist fields N/A in 2 of 3 modes. The order hashes are cheap
(≤256 × `uint16_t`). Still the right item — it is just not free, and the claim that it makes X062
observable does not survive §7 B5.

Design rule, per M-TESTARCH §4 I1: **additive-only, VE-gated field set.** Extend, never rename.

### P3 — the mode-transition matrix *(the base framework, testing the core feature)*

> **RE-DERIVED — @Architect review, 2026-08-17. The 9-transition domain does not exist in the
> firmware, and two of the seven invariants do not belong here.** Verified in source:
> `persistPlayerMode()` (`main.cpp:380`) opens `if (g_settings.playerMode == mode) return;` — the three
> diagonal cells are no-ops, so **21 of the 63 cells were vacuous**. `set playerMode`
> (`debug/serialConsole/cmdSet.h:651`) is documented *"Pure persist (no app switch)… Use the eject toggle to actually
> switch the live player slot"* — there is **no command that forces an arbitrary live transition**.
> And `playerModeNext()` (`settingsStorage.h:77`) is a **successor-only cycle**, so the reachable
> direct-transition set is **3 edges** (S→W, W→L, L→S); S→L is two hops, not one.

**Real domain: 3 edges × 5 invariants ≈ 15 cells.** At that size the generator framing was
over-engineering on a product the state machine does not offer — **these are 5 hand-written
parameterised bodies over a 3-edge list, not a code generator.** The M-TESTARCH §2.3 conformance-matrix
pattern still applies to 13 apps and 58 settings fields; it does not apply to 3 modes.

| id | Invariant at a transition | From | Status |
|---|---|---|---|
| `M1` | previous mode's audio engine fully torn down | X052, `T_AE_04` | keep |
| `M2` | arena released or transferred; no leak across the transition | X052, TASK-425/442 | keep |
| `M3` | UI zones match the new mode's capability mask | **X061** | keep — but see P0, `T_PLR_17` may cover it |
| `M4` | `playOrder`/`viewOrder` consistent; SAVE writes what is displayed | **X062** | keep, **but must read from the card** — §7 B5 |
| `M5` | the correct playlist source is bound to PLEDIT | **X054, X055** | keep — needs the new observable (P2) |
| ~~`M6`~~ | ~~taskbar slot + `AppId` tail~~ | X057, X064 | **DROPPED — already enforced at T0.** `taskbar/taskbar.h:42-63` carries three `static_assert`s for exactly this. M-TESTARCH §2b's own rule — *a test goes in the lowest tier that can falsify the claim* — puts it at compile time, where it is already green |
| ~~`M7`~~ | ~~`playerMode` survives reboot~~ | settings `S5` | **DROPPED from P3 — it is settings row `S5`, not a transition invariant.** Nine reboots (the most expensive operation in the suite) for one persisted byte. Test it once |

#### P3's blocker: the three modes do not coexist in one build

`app/platformio.ini:193` — `cyd2usb_player` inherits `cyd2usb_winamp_debug`'s flags **and adds
`-DDISABLE_SPOTIFY`**. `docs/project/tasks-winamp-player.md:263` records that local playback works on
`cyd2usb_player` and that skipping the arena on the Spotify-enabled build *"produces zero tracks"*.

So: on the Spotify debug build LocalPlayer cannot decode; on the player build Spotify does not exist.
**Exit criterion 5 as originally written — "a mode fix that breaks another mode fails in the same
run" — is forbidden by the build matrix.** No document in this set mentioned build variants at all.

The mitigating fact, from P0's evidence: `T_PLR_20-24/26` already run the shuffle/cursor/end-of-list
**state machine** on `cyd2usb_winamp_debug` without decoding audio. So the split is likely
*state-machine rows on the Spotify build, decode-dependent rows (M1, M2) on the player build* — **but
that split is VE's call to make, and it is the open question §7 hands to VE.** Until it is answered,
P3 is not schedulable.


### P4 — `get idle`: one quiescence predicate *(kills the settling sleeps)*

> **RE-SCOPED — @Architect review, 2026-08-17. It is not one key, and it is not one day.**
> `isConnecting()` does not mean the same thing in two apps. Transient-operation semantics:
> `webRadioApp.h:797` (`_state == CONNECTING`), `localPlayerApp.h:404` (`_connecting`).
> Never-had-data semantics: `teletextApp.h:152` (`!_ready`), `planeRadarApp.h:268`
> (`!_everHadResult`), `apps/cryptoApp.h:67` (`!s_cxDataReady`).
>
> Worse for this rig: `spotifyTaskStorage.cpp:658` — `connecting()` returns
> `s_lastSuccessfulPollMs == 0`, latching false only on the first 200/204. **Under TASK-243 (Premium
> lapsed, 403 — still live) that never happens, so `get idle` would report never-quiet in Spotify mode
> on the actual DUT.**
>
> ANDing these is precisely the failure §2 diagnoses — a per-mode observation used to answer a
> cross-mode question — reproduced inside the fix.
>
> Also: **"none is aggregated" was false.** `debug/serialConsole/cmdGet.h:198-215` — `get activeError`
> already ANDs `hasError()` + `isConnecting()` for the active app. The precedent exists; P4 should
> extend it and will inherit its per-app-contract problem.

**Honest scope:** either a new `hasInFlightOp()` predicate distinct from `isConnecting()`, added
across the `App` interface and its 13 implementations, or a documented contract split of
`isConnecting()` itself. That is an interface change with a `NEW-APP-CHECKLIST` entry, not a debug key.

**It is still worth doing, and still the cheapest probe of the synchronisation thesis** — mode
transitions are exactly where "is it finished?" is unanswerable today, and 252 settling sleeps in the
runner (539 across `app/tools`) are the standing cost. But it lands **with Stage D** (§3.2), and it
must be priced as an interface change.


## 5. Explicitly deferred — and this is the point of the document

| Deferred | Why it does not serve phase 1 |
|---|---|
| **TASK-480 runner split** | large, and it is the *regression suite* — high risk, and it does not make one player bug visible. **P1 is the part of it that pays now** |
| TASK-481 directory move / taxonomy | churns every doc path; zero signal improvement |
| T1 host unit tier + Arduino shim | genuinely valuable, needs D0, and `m3u.h` (2 commits, quiet) is not where the noise is |
| Correlation IDs / `watch` subscribe | phase 2. Gated on P4 producing evidence |
| C1 fetch consolidation, C3 table dispatch, C5 geometry, C6 palette | quality debt, not player noise |
| Conformance matrix for all 13 apps | the *pattern* is proven by P3 on the 3 modes first. Generalise after |
| `main.cpp` decomposition | continue **after** phase 1 — see §3 |

**Aquarium's zero conformance coverage, the 41 features with no `test_ids`, the 176 non-resolving ids
— all real, all deferred.** They are not what is making the player unimplementable.

## 6. Order, cost, and what "done" means

| # | Item | DUT time | Verifiable by |
|---|---|---|---|
| **P0** | reconcile 26 `T_PLR` ids ↔ X052–X064 | **none** | a mapping table with no "unknown" rows |
| P1 | `lib/dut.py` + port + timeout policy | none | imports resolve; suite runs unchanged |
| P2 | `get player` (6 aggregated + 2 new observables) | minutes | key returns in all 3 modes, N/A where honest |
| P3 | 3 edges × 5 invariants ≈ 15 cells | **blocked on the build-variant answer** | lands red; every red maps to a named X0NN |
| P4 | `hasInFlightOp()` / `get idle` | minutes | **lands with Stage D**; interface change, priced as one |

P0 first — it is free and it resizes P3. Then P1. P2 and P3 follow; P4 rides with Stage D.

**Exit criteria — revised:**

1. `lib/dut.py` exists; 16 importers migrated; **zero** argparse `/dev/ttyUSB0` defaults (13 today);
   one timeout policy.
2. `get player` returns the full vector in all three modes, reporting **N/A** rather than a fake value
   where a field does not apply.
3. Every failing matrix cell maps to a named `X0NN` **or to an existing `T_PLR` id from P0**.
4. The seven high-risk interactions have reserved ids in `test_plan.md` (VE), whether or not the cells
   pass yet.
5. ~~A mode fix that breaks another mode fails in the same run.~~ **Withdrawn — the build matrix
   forbids it** (§4, P3's blocker). Replacement, pending VE's split: *a mode fix that breaks another
   mode fails in the phase-1 gate*, where the gate is defined as both builds run in sequence. **The
   objective is unchanged; the word "run" was wrong.**

**Preconditions nobody had written down:**

- **SD card state.** Every LocalPlayer row needs `/playlists/*.m3u` present; `test_playorder_player.py`
  uses a fixture pushed once via `sd_put.py` and never regenerated. Name it as a phase-1 precondition.
- **X062 cannot be closed from RAM.** Its own notes require host-side verification **from the card**,
  *"not by re-reading through the same structure that produced the write"*. M4 as designed reads the
  in-RAM `viewOrder` hash — the check X062 explicitly rejects. Either add an SD-extraction arm
  (`run/spiffs`/`sd_put` pull + host compare) or **state plainly that phase 1 observes X062 and does
  not close it.**

**Not promised:** phase 1 does not clean up the suite, build a unit tier, or reduce the 209 test
bodies. It makes the 3-mode player observable and its couplings testable.

## 7. Review record — @Architect, 2026-08-17

Five blockers upheld, all verified in source before acceptance:

| id | Finding | Effect |
|---|---|---|
| **B1** | the 3 modes do not coexist in one build (`-DDISABLE_SPOTIFY`) | exit criterion 5 withdrawn; P3 blocked pending VE |
| **B2** | no live-transition command; `playerModeNext()` is successor-only | 63 cells → ~15; generator → 5 hand-written bodies |
| **B3** | `isConnecting()` means two different things across 13 apps; Spotify's never latches under a 403 | P4 re-priced as an interface change |
| **B4** | `viewOrder` and the bound `PlaylistSource` are exposed nowhere | P2 = aggregation **+ 2 new observables**, N/A in 2 of 3 modes |
| **B5** | X062 must be verified from the card, not from RAM | M4 as designed cannot falsify it |
| **M1** | 26 orphan `T_PLR` ids may already cover these interactions | **P0 added, ahead of P1** |

**One risk retired.** Debug-build headroom measured from `cyd2usb_winamp_debug/firmware.map`:
`dram0_0_seg` 124 580 B, `.dram0.bss` ending `0x3ffda188` against a segment end of `0x3ffdc200` —
**≈ 8 312 B free.** P2/P4 are `printf` handlers whose format strings land in `.rodata`, not
`.dram0.bss`. The institutional memory of "0 B / 40 B headroom" (2026-07-29 / 08-02) is **stale by
~8 KB** — re-derive, never cite it.

**Open, handed to @VE:** the two-build verification split (which invariants are provable on
`cyd2usb_winamp_debug` without decode, which need `cyd2usb_player`), the P0 mapping table, id
allocation for what survives, and whether a trustworthy D13 baseline is achievable on today's suite.
