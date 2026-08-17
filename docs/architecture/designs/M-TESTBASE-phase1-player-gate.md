# Design — M-TESTBASE phase 1: a base test framework, scoped to the 3-mode player

> Owner: Architect + VE
> Status: **proposed, revised after @Architect + @VE review (round 2, consensus)** — 2026-08-17
> Review record: §7. VE **overturned B1** and resized P0; P3 is now 3 new ids, not 15 cells.
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
> `T_PLR_01..26` (and the specified family runs to `T_PLR_41` — see P0), and `app/tools/test_playorder_player.py:9` documents that **T_PLR_20-24/26 — the
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

> **CORRECTED AGAIN — @VE, P0 execution, 2026-08-17. The "seven with zero coverage" list was drifted
> in *both* directions, and now there is status data instead of guesses.** Three of the seven have
> running bodies today (`X057`, `X061` fully; `X052` partially). Two the list never flagged —
> **`X053` and `X054`** (plus `X059`) — are as uncovered as any it did.
>
> **The genuinely uncovered set is `X053`, `X054`, `X059`, `X062`, `X064`, plus the `X055` seqno
> half** — five and a half, overlapping the original seven by three. The matrix's *bookkeeping* claim
> (7 of 8 high-risk rows read `test_coverage: []`) was accurate; the *inference* that the couplings
> were untested was not.
>
> Worse, in the other direction: the only three populated rows in the whole X050–X064 range
> (`X050`, `X051`, `X063`) cite `T_AE_11`–`16`, **none of which has a body anywhere in `app/tools`**
> — verified. The three populated rows are less honest than the twelve empty ones.

**Conclusion: the noise is concentrated, not diffuse — five and a half genuinely uncovered couplings
in the one subsystem being actively built.** That is a far smaller problem than the quality
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

### 3.4 The baseline argument — overturned by @VE, and the lever is different

The first draft claimed a trustworthy ADR-059 D13 baseline is impossible on today's suite, and that
P1's timeout policy is what would make one meaningful. **@VE, who owns that process, rejects both
halves — and is right.**

**A ≥3-run baseline *was* taken**, under TASK-497. It measured **4:1 environmental noise with a stable
core of 6 ids**. So the question was never possible-vs-impossible; it is that the baseline yields a
small stable core. And **the noise is environmental (network/DUT), not timeout literals** — P1 will
not move that ratio. P1 remains a good item on its own merits; it is **not** the precondition this
section claimed.

Minimum to make a D13 baseline meaningful, VE's ranking by effect per unit cost:

1. **A machine-readable declared flaky set.** The knowledge exists, scattered in annotations (`T169`
   network, `T_PR_05` `[NETWORK]`, `T_WR_TLS_01`); the artifact does not. A `flaky.yaml` the runner
   reads and reports separately is the cheapest change and the one **D13 literally requires**.
2. **Partition the suite by dependency class** — `[NETWORK]` / `[SD]` / `[AUDIO]` / `[PURE]` — and
   baseline over `[PURE]`+`[SD]` only. The 4:1 noise concentrates in `[NETWORK]`.
3. **Pre-declare the pass set as a file of ids, not a count.** "≥3 runs" without the identity of what
   passed is the exact failure TASK-488 hit.
4. *Then* P1's timeout policy — real, but second-order.

**Consequence for the sequencing in §3.3: a trustworthy baseline for the player gate specifically is
achievable now, at a fraction of the assumed cost**, because the player suite is mostly network-free —
`run_serialdbg_tests.py:260` already notes `T_PLR_08`–`12` as *"a suite that touches no network at
all"*. §3.3's order stands on the P4/Stage-D collision, which is independently verified; it no longer
stands on a baseline argument.


### 3.5 One debt owed before C

**TASK-464 is due now, at the end of Stage B**: 308 `main.cpp:NNN` citations across 49 documentation
files, plus 44 `main.cpp` references in `feature_inventory.yaml`, already invalidated. M-SRCLAYOUT
says pay it **once** at the end of B, not per-stage. Starting C/D without it lets those citations rot
further and makes the sweep larger.


## 4. Phase 1 — five items, in order

### P0 — transcribe the existing coverage table *(@VE; not derivation, and smaller than stated)*

> **CORRECTED — @VE, 2026-08-17. P0 is not new work.** The interaction→id table already exists for
> **all fifteen** X050–X064 at `M-WINAMP-PLAYER-VE-review.md:215-231`, written before ADR-059 was
> signed. And the family is **41 ids, not 26** — `T_PLR_27`–`41` are fully specified with method and
> pass criteria at `M-WINAMP-PLAYER-local-playback.md:452-511`. Every count in this document's first
> draft, and in the @Architect review's finding M1, was off by fifteen.

What P0 actually is: **transcription plus one column the existing table lacks — implementation
status.** VE's own verdict on its predecessor: *"A coverage table without an implementation-status
column is how 'covered' and 'green' got conflated across this whole document set."*

The real bookkeeping debt: `T_PLR_*` appears in `test_plan.md` exactly **four** times, all incidental.
**41 ids specified in Architect-owned design docs; zero registered in the VE-owned plan.**

Two defects to fix while transcribing:

- **`T_PLR_17`/`T_PLR_18` are swapped.** `M-WINAMP-PLAYER-local-playback.md:466-467` assigns 17 =
  "WebRadio unchanged", 18 = "Spotify unchanged"; the runner implements them the other way round
  (`run_serialdbg_tests.py:5957` is Spotify). `ADR-059.md:396` cites both as baseline ids, so **every
  citation is currently ambiguous.**
- Seven ids (`06`,`07`,`08`,`10`,`11`,`12`,`16`) map to no interaction. **That is correct, not a
  defect** — they are single-feature ids and the matrix records feature *pairs*. Do not manufacture
  interactions for them.

Owner: **@VE**. Host-side, no DUT, no firmware.

> **DONE 2026-08-17** (`116c64f`). 44 ids registered in `test_plan.md` — **26 `impl`, 8 `blocked`,
> 10 `resv`**, zero unknown rows — plus the X050–X064 table with a status column, and a proposed
> `test_coverage:` patch at `docs/verification/regression_suite/m-winamp-player-coverage.md` for
> @Developer to apply. The `T_PLR_17`/`18` swap is fixed **in the spec, not the code**: the runner's
> numbering is load-bearing in five closed quality artifacts and a passed gate. Two board items
> surfaced for @PM: `T_PLR_39`'s blocker is stale (TASK-442 closed), and `T_PLE_14` is still
> unspecified anywhere.


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

> **@VE proposed a third missing observable (`get pleditRepaints`); rejected on evidence.** It **is**
> implemented, at `winamp/winampDisplay.h:1306`, inside the per-app `dbgGet` chain rather than under
> `debug/` — which is where VE's grep looked. `gen_get_keys.py` finds it because it parses the
> delegated chains too. **B4's count of two stands.**

**Honest scope: aggregation of ~6 existing keys, plus 2 new observables** (a `viewOrder` accessor, and
the bound `PlaylistSource`), with the playlist fields N/A in 2 of 3 modes. The order hashes are cheap
(≤256 × `uint16_t`). Still the right item — it is just not free, and the claim that it makes X062
observable does not survive §7 B5.

Design rule, per M-TESTARCH §4 I1: **additive-only, VE-gated field set.** Extend, never rename.

> **DONE 2026-08-17, DUT-verified.** `get player` returns
> `mode · modeName · caps · srcKind · srcName · arenaHeld · pending · err · connecting`, plus
> `plCount · playHash · viewHash · orderIdentical` in Player mode and an explicit
> `"n/a"` note elsewhere. Two new observables landed as predicted: `PlSrcKind` (a **stable enum**,
> per VE's condition — a class-name string would pass silently through a rename) recorded from the
> source that *actually* drove the last PLEDIT draw, and `PlaylistIndex::viewOrder()`, which had no
> accessor at all. Order hashes are FNV-1a over the u16 sequence, so a permutation is detectable
> without dumping 256 entries per poll.
>
> **Memory cost: zero.** `dram0_0_seg` headroom measured **8 312 B before and after** — the review's
> prediction that `printf` handlers land in `.rodata` rather than `.dram0.bss` held exactly.
>
> **It discriminates.** Booted live in Spotify: `srcKind=1 (SpotifyQueue), caps=15`. Booted live in
> WebRadio: `srcKind=2 (StationList), caps=1`. That is X061's subject — the capability mask — visible
> in one observation for the first time.
>
> **B2 confirmed empirically.** Setting `set playerMode 0/1/2` moved `mode` but left `srcKind` and
> `caps` unchanged, because it is pure persist and never switches the live slot. `mode` and `srcKind`
> disagreeing is the instrument working, not a defect.

### P3 — the mode-transition matrix *(the base framework, testing the core feature)*

> **RE-DERIVED — @Architect review, 2026-08-17. The 9-transition domain does not exist in the
> firmware, and two of the seven invariants do not belong here.** Verified in source:
> `persistPlayerMode()` (`main.cpp:380`) opens `if (g_settings.playerMode == mode) return;` — the three
> diagonal cells are no-ops, so **21 of the 63 cells were vacuous**. `set playerMode`
> (`debug/serialConsole/cmdSet.h:651`) is documented *"Pure persist (no app switch)… Use the eject toggle to actually
> switch the live player slot"* — there is **no command that forces an arbitrary live transition**.
> And `playerModeNext()` (`settingsStorage.h:77`) is a **successor-only cycle**, so the reachable
> direct-transition set is **3 edges** (S→W, W→L, L→S); S→L is two hops, not one.

> **DONE 2026-08-17 — `T_PMT_00`–`03`, 4/4 PASS on Leg A, first run.**
> `T_PMT_00  TASKBAR_SLOT slot 0 cycled 0 -> 1` ·
> `T_PMT_01  Spotify -> WebRadio: src=StationList caps=1` ·
> `T_PMT_02  WebRadio -> Player: src=LocalPlaylist caps=15` ·
> `T_PMT_03  Player -> Spotify: src=SpotifyQueue caps=15`.
> **No coordinate appears anywhere except `T_PMT_00`**, which derives one from `get playerBind` —
> so a relocation costs exactly one edit, which was §8's whole objective.
>
> **LEG B RAN, AND IT DID NOT BUY WHAT IT WAS FOR — 2026-08-17.** `T_PMT_00`–`03` are **4/4 PASS on
> `cyd2usb_player`** as well. But leg B exists for **M2, the arena**, and a direct probe shows the
> arena is **never acquired at all** on this path:
>
> | mode (leg B) | `arenaHeld` | `plCount` | `arenaStats` |
> |---|---|---|---|
> | Player | 0 | **0** | active=0 **acquires=0** releases=0 |
> | WebRadio | 0 | n/a | active=0 acquires=0 releases=0 |
> | Spotify | 0 | n/a | active=0 acquires=0 releases=0 |
>
> **`T_PMT_03`'s M2 assertion is therefore vacuous on both legs** — it asserts "still 0" against a
> counter that was never incremented. Mode switching alone does not acquire the arena; **starting
> playback does**, and `plCount=0` says no playlist is loaded, because the SD fixture precondition
> (§6, W2) has never been satisfied on this rig.
>
> **So M2 / X052 remains genuinely uncovered, and this document must not claim otherwise.** Leg B as
> run reproduces leg A. Closing M2 needs a playback arm: push the `sd_put.py` fixture, start playback
> in Player, switch away, then assert `acquires > 0` **and** `active == 0`. Recorded rather than
> quietly counted — this is exactly the "covered vs green" conflation @VE's status column exists to
> prevent, arriving one layer up in the same document that introduced the column.

> **Regression note, and a flake for the pre-declared set.** Running
> `T_PLR_01,05,17,18,19` after the new family, `T_PLR_17` failed once
> (*"no 'dequeued action=SHUFFLE' within 20s"*), then **passed in isolation and passed again on the
> identical five-id sequence** — 1 fail in 3 runs, no mechanism connecting it to this change
> (`T_PLR_01/05/17` never call `playerCycle`). Recorded as a **flake candidate**, not a regression and
> not a clean bill: one failure in three runs is evidence, not a verdict. This is exactly the artifact
> M-TESTARCH §7 wants — a flake with a run count attached instead of a shrug.

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

#### P3 and the build matrix — B1 overturned by @VE, and the gate is two legs

> **B1 WAS WRONG AS STATED — @VE, 2026-08-17, and the correction is verified.** "The three modes do
> not coexist" conflated two different flags. `kPlayerModes[]` (`settingsStorage.h:47-55`) is gated on
> `PLAYER_SPOTIFY` / `PLAYER_WEBRADIO` / `PLAYER_LOCAL` — **not** on `DISABLE_SPOTIFY`, which compiles
> out Spotify's *network stack* only. `cyd2usb_player` deliberately does **not** carry `-DPLAYER_LOCAL`
> (`tasks-winamp-player.md:665-669`, which records that env as *"the playback test vehicle for the
> whole milestone: `T_PLR_01`/`T_PLR_02` cycle all three modes on it and were run green on it today"*).
>
> **All three mode slots, and all three edges, are drivable on both builds.** What does not coexist is
> Spotify's live TLS working set alongside local audio decode (TASK-425/431).

That dissolves most of the blocker. What genuinely needs `cyd2usb_player` is narrow:

| Invariant | Provable on `cyd2usb_winamp_debug`, no decode? |
|---|---|
| **M1** engine teardown | **Partly** — S→W and W→L tear down the *outgoing* engine, no local decode needed. **L→S needs `cyd2usb_player`** (Player must have had an engine to tear down) |
| **M2** arena | **No — `cyd2usb_player` only.** TASK-425 measured that the arena cannot be acquired on `winamp_debug` with the TLS working set resident, in any ordering |
| **M3** capability mask | **Yes** — pure render/hit-test, already green under `T_PLR_17`–`19` |
| **M4a** playOrder | **Yes** — already green under `T_PLR_20`–`24`/`26` |
| **M4b** viewOrder + SAVE | **Neither build** — see below |
| **M5** bound `PlaylistSource` | **Yes**, once P2's observable exists (pure RAM read) |

> **P3 must not use the eject toggle — and this is a REDISCOVERY, not a discovery.** Four eject taps
> in P2's DUT session left `mode=Spotify` unchanged. The binding moved ten months ago and is fully
> documented:
>
> - **`434b18d` (TASK-413)** moved the cycle to the taskbar player slot — `resolvePlayerTap()`,
>   `app/src/main.cpp:393`, called from exactly two dispatch sites (`app/src/main.cpp:467` and
>   `app/src/debug/serialConsole/cmdTouch.h:21`).
> - **`07250ca` (TASK-414)** remapped eject: *"Eject no longer switches player apps (that's the
>   taskbar player-slot cycle from TASK-413 now). It becomes one verb, three realisations."*
> - **[ADR-059 D6](../decisions/ADR-059.md)** is the decision, amended 2026-08-07 (DEV-1).
>
> **Correction to this document's first draft**, which claimed this was new and that it was "the first
> artifact to catch a test design still assuming the old behaviour". Both were wrong: TASK-414 caught
> exactly this ripple in the harness — *"eject was WebRadio's only entry path in the test harness,
> silently un-migrated since TASK-413"* — and fixed three call sites for it.
>
> **What is actually new is worse.** The stale assumption re-entered through a *design document*, written
> with TASK-414's own commit message available. The binding is recorded in an ADR and two commit
> messages, and **nothing executable prevents a new test design from assuming the old surface.** That
> is the argument for §8, and a stronger one than the first draft made.

**Replacement for the withdrawn exit criterion 5** (VE's wording, adopted):

> The phase-1 player gate is **one ordered execution of two legs at the same commit.** *Leg A*
> (`cyd2usb_winamp_debug`): `T_PLR_01`–`24`,`26`, the M3/M4a/M5 cells, and the **S→W** and **W→L**
> transition cells. *Leg B* (`cyd2usb_player`): `test_fbrowser_player.py`, `test_playorder_player.py`,
> the **L→S** cell and all M2 cells. The gate FAILS if any cell in either leg regresses against a
> pre-declared baseline pass set.

Two conditions, or it is theatre: **(a) each leg must contain at least one genuinely cross-mode cell**
— asserting on mode X *after arriving from* mode Y — else it is two per-mode suites concatenated and
the objective is lost; **(b)** the gate costs two flashes and two boots, and `run/task488`'s
`DUT_TREE` two-checkout pattern is the existing precedent for driving it from one script.

#### M4b is not blocked on tooling — it is blocked on TASK-424

> **@VE, sharpening B5.** `player/m3u.h:230` — `_view[_count] = _count; // identity until TASK-420
> reorders`. **`viewOrder` is an identity permutation with no mutator, and there is no SAVE.**
> TASK-420/421 are blocked behind **TASK-424**, an open, deterministically reproducible FatFs
> `LoadProhibited` panic on the SD write path with no fix (`tasks-winamp-player.md:177-215`).

So X062's destructive failure **cannot be provoked**, let alone observed — not for want of a
card-extraction arm, but because the code that would destroy the playlist does not exist yet. Building
the arm against firmware that cannot write is theatre.

**Decision: split M4.** M4a is executable now under `T_PLR_20`–`24`. **M4b ≡ `T_PLR_30`** (already
specified, including the VE-10 precondition that N≥20 and `plOrder != viewOrder` before saving, so a
Fisher-Yates identity cannot fake a pass) — **deferred behind TASK-424.** Phase 1 states plainly that
it **observes X062 and does not close it.**


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
| **P0** | transcribe the X050–X064 table + status column; fix the `T_PLR_17`/`18` swap | **none** | 41 ids registered in `test_plan.md`, no "unknown" rows |
| P1 | `lib/dut.py` + port + timeout policy | none | imports resolve; suite runs unchanged |
| P2 | `get player` (≈6 aggregated + 2 new observables) | minutes | key returns in all 3 modes, **N/A** where honest |
| P3 | **3 new ids** (`T_PMT_01`–`03`), one per edge | two legs | both legs green against a pre-declared pass set |
| P4 | `hasInFlightOp()` / `get idle` | minutes | **lands with Stage D**; interface change, priced as one |

**P3 is ~60 % bookkeeping.** M3 and M4a are already green under existing ids; M1 duplicates the
already-specified `T_PLR_38`. **Net new: three ids, not fifteen cells.**

### 6.1 Id allocation (@VE)

`T_PLR_27`–`41` are **taken**. Do not extend that family — it is partitioned per-task (one block per
TASK's gate), and these cells are cross-mode by construction. New reserved family **`T_PMT_`** (Player
Mode Transition); prefix is free, though `T_PRM_` already exists in the runner and is visually close.

| id | Cell | Leg |
|---|---|---|
| `T_PMT_01` | S→W — full `get player` vector: arena released, source rebound, caps match | A |
| `T_PMT_02` | W→L — same | A |
| `T_PMT_03` | L→S — same, plus outgoing engine teardown | B |

**One id per edge, asserting the whole vector** — not one per edge×invariant. That is precisely what
P2 buys, and 3×5 separate cells throws it away. M1 → write the existing `T_PLR_38`. M3 →
`T_PLR_17`/`18`/`19` after the swap fix. M4a → `T_PLR_20`–`24`. M4b → `T_PLR_30`, deferred.

**Exit criteria — revised:**

1. `lib/dut.py` exists; 16 importers migrated; **zero** argparse `/dev/ttyUSB0` defaults (13 today).
2. `get player` returns the full vector in all three modes, reporting **N/A** rather than a fake value
   where a field does not apply. `M5`'s source field is a **stable enum, not a class-name string** — a
   string silently passes through a rename.
3. Every failing cell maps to a named `X0NN` **or an existing `T_PLR` id from P0**.
4. The seven interactions are registered in `test_plan.md` as **id + owner + source link + status
   only** — criteria stay in the design docs. *(Corrected: the first draft asked VE to restate criteria
   in `test_plan.md`, which `test_plan.md:22-24` warns against in its own voice — "a criterion copied
   into two files diverges (LL-114)". The M-ARCH block at `:14-24` is the shape to copy.)*
5. ~~A mode fix that breaks another mode fails in the same run.~~ **Replaced by the two-leg gate**
   (§4). The objective is unchanged; "run" was the wrong word, and "the modes do not coexist" was the
   wrong reason.

**Preconditions:** SD card must carry `/playlists/*.m3u` (`test_playorder_player.py` uses a fixture
pushed once via `sd_put.py`, never regenerated). **X062 is observed, not closed** — blocked on
TASK-424.


## 7. Review record — two rounds, consensus reached 2026-08-17

**Round 1 — @Architect.** Five blockers, four verified in source before acceptance.

| id | Finding | Outcome |
|---|---|---|
| B1 | the 3 modes do not coexist in one build | **OVERTURNED in round 2** — see below |
| **B2** | no live-transition command; `playerModeNext()` successor-only | **upheld** — 63 cells → 3 edges; generator → hand-written bodies |
| **B3** | `isConnecting()` means two things across 13 apps; Spotify's never latches under the live 403 | **upheld** — P4 re-priced as an interface change |
| **B4** | `viewOrder` and the bound `PlaylistSource` exposed nowhere | **upheld** (count of 2 confirmed against VE's proposed 3) |
| B5 | X062 must be verified from the card | **upheld but superseded** — the binding constraint is TASK-424, not tooling |
| M1 | orphan `T_PLR` ids may already cover these interactions | **upheld and enlarged** — 41 ids, not 26 |

**Round 2 — @VE.** Overturned one blocker, resized two items, corrected the baseline argument.

| VE finding | Adjudication |
|---|---|
| **B1 wrong**: modes are gated by `PLAYER_*`, not `DISABLE_SPOTIFY`; `T_PLR_01`/`02` ran green on `cyd2usb_player` | **ACCEPTED — verified.** `settingsStorage.h:47-55` + `tasks-winamp-player.md:665-669`. The round-1 review verified the *flag* but not its *consequence*, and so did I |
| **P0 is transcription, not derivation** — the table exists at `M-WINAMP-PLAYER-VE-review.md:215-231` | **ACCEPTED — verified** |
| **41 ids, not 26** (`T_PLR_27`–`41` specified at `M-WINAMP-PLAYER-local-playback.md:452-511`) | **ACCEPTED — verified.** Every downstream count was off by fifteen |
| **X062 blocked on TASK-424**, `viewOrder` identity-only with no mutator | **ACCEPTED — verified** at `player/m3u.h:230` |
| **§3.4's baseline claim is wrong**; a D13 baseline *was* taken (TASK-497, 4:1 environmental noise, stable core 6). A declared flaky set, not a timeout policy, is the lever | **ACCEPTED.** §3.4 rewritten |
| `T_PLR_17`/`18` swapped between spec and implementation | **ACCEPTED — verified.** Folded into P0 |
| `get pleditRepaints` is a third missing observable | **REJECTED — verified false.** It exists at `winamp/winampDisplay.h:1306`, in the per-app `dbgGet` chain rather than under `debug/`, which is where VE's grep looked |
| P3 is ~60 % bookkeeping; 3 new ids not 15 cells | **ACCEPTED** |

**One risk retired (round 1, verified).** Debug-build headroom measured from
`cyd2usb_winamp_debug/firmware.map`: `dram0_0_seg` 124 580 B, `.dram0.bss` ending `0x3ffda188` against
a segment end of `0x3ffdc200` — **≈ 8 312 B free.** P2/P4 are `printf` handlers whose format strings
land in `.rodata`, not `.dram0.bss`. The institutional memory of "0 B / 40 B headroom"
(2026-07-29 / 08-02) is **stale by ~8 KB** — re-derive, never cite it.

**Method note worth keeping.** Both reviews were wrong about something, in the same way: each verified
a *fact* and inferred a *consequence* without checking the inference. Round 1 read `-DDISABLE_SPOTIFY`
in `platformio.ini` and concluded the modes were compiled out; round 2 grepped `debug/` for
`pleditRepaints` and concluded it was unimplemented. Both facts were correct; both conclusions were
not. **This is M-CODEQUAL §13.2's counting note one level up — in this codebase a verified fact is
still only a hypothesis about its consequence.** Recommend QM promote it alongside the counting note.

**Still open, and genuinely:** whether `run/task488`'s `DUT_TREE` pattern is the right driver for the
two-leg gate, and whether the `[NETWORK]`/`[SD]`/`[AUDIO]`/`[PURE]` partition (§3.4 item 2) is worth
doing before the player gate or after it.

## 8. Binding robustness — surviving the next relocation

**The problem, stated once.** The gesture that cycles player mode has moved once already (eject →
taskbar player slot, TASK-413/414) and the move broke things twice: the harness in August, and a
design document ten months later. Both breaks share one cause — **downstream artifacts bind to the
gesture when what they mean is the operation.**

That will happen again. `resolvePlayerTap()` is reachable from a taskbar slot today; a future skin,
a hardware button, or a settings row could own it tomorrow. The goal is not to prevent the move. It
is to make the move cost **one edit in one place**.

### 8.1 The rule

> **Tests drive the OPERATION. Exactly one test asserts the GESTURE→operation binding.**

Today every mode-switch in the suite taps a coordinate: 4 `tap_eject()` sites plus
`_ensure_webradio()` and `_switch_to()` walking taskbar pixels. Each is an independent copy of the
assumption "this surface performs that operation". Relocate the surface and every one of them is
silently wrong — they will still tap, still get a JSON reply, and still assert against a mode that
never changed. **That is precisely the failure P2's DUT session reproduced: four taps, a valid
response each time, and no state change.**

Under the rule: N tests call the operation directly, one test asserts the binding. Relocation edits
that one test.

### 8.2 The mechanism — two debug surfaces, both small

| Surface | Kind | What it does |
|---|---|---|
| `playerCycle` | **command** | invokes `resolvePlayerTap(AppId::Spotify, isPlayerModeApp(currentAppId))` + `switchApp()` — the *semantic operation*, no coordinates |
| `get playerBind` | **observable** | reports which region currently owns it: `{"op":"playerCycle","region":"TASKBAR_SLOT","appId":0}` |

`playerCycle` is what `T_PMT_01`–`03` and every future mode-transition test call. `get playerBind` is
what the **single** binding test reads, so it can locate the live surface instead of assuming one.

Both are `SERIAL_DEBUG`-only, both are printf handlers, and P2 measured that class of change at
**zero `.dram0.bss` cost** (headroom 8 312 B, unchanged).

> **BOTH LANDED AND DUT-VERIFIED, 2026-08-17.** `get playerBind` reports
> `op=playerCycle region=TASKBAR_SLOT helper=resolvePlayerTap`. Four `playerCycle` calls, **no
> coordinate anywhere in the test**, drove the full three-way cycle with `get player` confirming each
> arrival:
>
> | from → to | mode | srcKind | caps |
> |---|---|---|---|
> | — | Spotify | `SpotifyQueue` | 15 |
> | 0 → 1 | WebRadio | `StationList` | **1** |
> | 1 → 2 | Player | `LocalPlaylist` | 15 |
> | 2 → 0 | Spotify | `SpotifyQueue` | 15 |
>
> First time all three live modes have been observed in one session, and the capability mask (X061)
> and bound source (X054/X055) discriminate correctly at every step. This is the gesture-free
> transition driver `T_PMT_01`–`03` needed and B2 said did not exist.

This also closes the gap B2 identified — *"there is no command that forces an arbitrary live
transition"* — without inventing a second mode-cycle path in production: `playerCycle` calls the same
shared helper both production dispatch sites call, which is the discipline ADR-059 D6's amendment
imposed for exactly this reason.

### 8.3 Making the other three artifacts robust

The same rule, applied per artifact — each currently states the binding implicitly, which is why none
of them failed when it changed:

- **`feature_inventory.yaml`** — `player-state-001` describes three-valued mode but does not name
  **what performs the cycle**. Add a `binding:` line naming the operation and its current surface, so
  the fact lives in a field rather than in prose that nobody diffs.
- **`cross_feature_matrix.yaml`** — `X056` (player-mode cycling on the taskbar slot) has the surface
  **in its title**. That is the right place for it, and it means X056 is the interaction that must be
  re-read on any relocation. Its `test_coverage` should be the binding test, not the operation tests.
- **`test_plan.md`** — one reserved id for the binding assertion, distinct from the transition ids.
  Proposed: **`T_PMT_00`** — *"the surface reported by `get playerBind` performs `playerCycle`"* —
  deliberately numbered ahead of `T_PMT_01`–`03` because if it fails, their results are meaningless.

### 8.4 The gate

A static check, in the shape this programme keeps reusing (`check_settings_wiring.py`,
`appRegistry.h`, `gen_get_keys.py`): **assert that `resolvePlayerTap` has exactly the call sites the
docs claim.** Two today (`app/src/main.cpp:467`, `app/src/debug/serialConsole/cmdTouch.h:21`) plus
`playerCycle` once it lands. A third appearing without a doc update fails `run/check`.

> **LANDED 2026-08-17 — `app/tools/check_player_binding.py`, wired into `run/check` gate 9.** It
> turned out to be ~180 lines rather than 15, because it asserts the whole chain, not just the call
> sites: `resolvePlayerTap` defined once → **called exactly twice** in `main.cpp` and once in
> `cmdTouch.h` → `playerCycle` registered in `kCmds[]` **and reusing the shared helper** → `get
> playerBind` and `get player` present → `T_PMT_00` registered in `ALL_TESTS` **and** reading
> `playerBind`.
>
> **Four negative tests, and two of them failed the first version — which is the only reason the gate
> is worth anything:**
>
> | Break | First version | Now |
> |---|---|---|
> | extra dispatch site inside `main.cpp` | **passed** — it compared filenames, not counts, so the exact TASK-413 failure slipped through | fails |
> | `playerCycle` unregistered from `kCmds[]` | fails | fails |
> | `get playerBind` deleted | fails | fails |
> | `T_PMT_00` removed from `ALL_TESTS` | **passed** — the id still appeared in the body's own `pass_()`/`fail()` strings, so a substring check matched a test that no longer ran | fails |
>
> The gate's own first run also miscounted: `kCmds[]`'s help text contains
> *"…via resolvePlayerTap (surface-independent)"*, and the pattern matched the space before the
> paren — **a help string counted as a dispatch site.** It now strips string literals as well as
> comments. Three self-inflicted errors in one 180-line file, all found by testing the gate rather
> than reading it, and all of the same family M-CODEQUAL §13.2 names: *a grep-derived count is a
> hypothesis.*

### 8.5 What this does not do

It does not stop someone relocating the surface and forgetting to update `get playerBind` — the
binding observable is itself a mirror of the truth, and LL-114 says mirrors rot. The honest defence is
that `T_PMT_00` fails loudly the moment they disagree, which is the same bargain
`check_settings_wiring.py` makes and the reason it has held.
