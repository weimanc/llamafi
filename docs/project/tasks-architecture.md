# M-ARCH — architecture work board (M-SRCLAYOUT · M-CODEQUAL · M-TOOLING · M-DOCLIFE)

> Owner: Project Manager · Split out of [tasks.md](tasks.md) on 2026-08-16.
>
> **Why this file exists.** A 2026-08-16 Architect pass produced nine design documents, two ADRs and
> three IFCs, reserving 35 task ids. Filing those inline would have taken `tasks.md` from ~1 200
> lines back past 2 500, undoing the archive sweep done the day before. Same treatment as the
> M-WINAMP-PLAYER board.
>
> **Read this first — the honest state.** Three refactor commits (`a044f5d`, `78caa95`, `b36f184`)
> **already landed** ahead of ADR sign-off. **As of 2026-08-16 they are reviewed and DUT-verified
> (TASK-488) and the owed ≥3-run baseline is taken (TASK-497) — nothing was reverted.** What that
> does *not* change: by ADR-060 D0's measure they created **zero components** — `main.cpp` went
> 5 880 → 1 726 lines, which is readability, not physical design. **TASK-453 and TASK-454 are filed
> as landed-and-verified, not as open work.**
>
> Closed entries go to [tasks-archive.md](tasks-archive.md).

> ## ⚠ @PM verdict, 2026-08-16 — read before scheduling anything here
>
> **This board should lose to closing M-WINAMP-PLAYER, and the count is inflated.**
>
> **On the count:** 47 entries, but **~10–12 are actually actionable** without a design decision
> first. The rest are BLOCKED on the five-deep serial chain, SKELETON (research prompts with "no
> conclusions" by design), or gated on an unresolved question. *"47 tasks"* must not be quoted
> without that caveat.
>
> **On the altitude — the finding that matters:** M-WINAMP-PLAYER has 12 open entries and was
> **paused by the human over work quality**. Its PM note diagnoses three failure modes. **This board
> reproduces two of them, on a compressed timescale, in the same week**: nine design docs and 47
> tasks in one day; three commits landed ahead of ADR sign-off with no baseline (BP-062's
> "measurement without conditions", and D13 skipped outright); and a review chain that found errors
> in *every document it reviewed* — 8 of 9 confirmed, including an invariant false about its own
> example. **Higher volume, lower verification, same week, same shop.** Scheduling 47 new
> architecture tasks while 12 paused player tasks sit unresolved is the wrong order regardless of how
> good TASK-458/466/475/478 are individually.
>
> Escalated as **E-05**. The Architect does not overrule this.
>
> ### Human ruling, 2026-08-16: **M-ARCH is prioritised. PM's recommendation is overruled.**
>
> **This is CLOSED, not open.** PM's case is preserved below for the record, **not as a live
> objection** — do not reopen it. *(Clarified 2026-08-16 on PM's own request: a cold agent skimming
> "PM's case intact" could misread it as unresolved.)*
>
> Recorded rather than quietly applied, because PM's reasoning stands on its own and the next reader
> should see both. PM's case — that this board reproduces two of M-WINAMP-PLAYER's diagnosed failure
> modes while that paused milestone waits — is **not withdrawn and is not wrong**. The human has
> weighed it and chosen differently, which is theirs to do.
>
> What does **not** change under this ruling: **TASK-488 still gates the M-SRCLAYOUT chain** (three
> commits landed unreviewed and un-baselined; prioritising the programme does not un-land them)
> — *gate satisfied 2026-08-16: 488 and 497 both closed, chain unblocked* — and
> **BP-066 now applies to everything on this board** — no document here gates work or is cited as
> fact until independently reviewed. Prioritising the programme raises the value of both, not less.

**Priority key**: P1 blocking · P2 should-do · P3 nice-to-have · P4 watch

---

## ▶ EXECUTION SEQUENCE — start here

Current as of 2026-08-16 end-of-session. Derived from @PM's review, adjusted for what has since
landed. **Do these in order**; everything not listed stays filed and unscheduled.

| # | Do | Why this position |
|---|---|---|
| ~~**1**~~ **DONE 2026-08-16** | ~~**TASK-488 + TASK-497 — one DUT block**~~ | Three refactor commits sit on master unreviewed with no baseline. Everything in M-SRCLAYOUT is gated on this, and **the cost of delay compounds**: each further commit on top widens the blame surface from one to four. Same hardware session covers both — 488's byte-identity/`.map` review and 497's retrospective ≥3-run baseline. |
| ~~**1a**~~ **DONE** | *(prerequisite, ~15 lines)* ~~**write TASK-488's pass criteria first**~~ | Its DUT procedure is currently one sentence — *"a pass over app switching, taskbar cycling, eject and Settings navigation"* — with no id, steps, iteration count or fail condition. Compare `T_AE_04`, which specifies ×10 and a 100 ms bound. **Running 488 without criteria is closing against a proxy (BP-061)**: nothing visibly breaks, it gets called verified. |
| **2** | **Decide 455/456/471/472 on what 488 finds** | **488 found nothing wrong — continuation, not rework.** Do not pre-schedule. They may need rework rather than continuation. Note ADR-060 authorises **A+B only** — C–F need a new ADR regardless. |
| **3** | **TASK-475** — `run/check-docs` | Unblocked, cheap, self-correcting from then on. C5 blocking day one, C1 in `delta` mode. |
| **4** | **TASK-478** — `tools/lib/dut.py` | Unblocked, cheap; its absence caused three of M-TOOLING's five findings. Unblocks 479/480. |
| **5** | **TASK-458** — RAII guards — **with TASK-495 as its first commit** | Real bug class with a proven instance (TASK-222). 495 is parked but **must land in front of this** — see its ordering note. |
| **6** | **M-WINAMP-PLAYER** | Still paused, 12 entries. @PM would put **TASK-424** (SD write panic, card-independent) ahead of most of this board if DUT time is scarce. |

**Already done, do not re-schedule:** TASK-466 (build gate, 3 → 11 envs), 467, 477, 491, 496 — all
landed 2026-08-16, `run/check` 11/11 — plus **TASK-488 and TASK-497**, closed 2026-08-16 in one DUT
block. **Next in sequence is now #3 (TASK-475).** New follow-ups from the verification: 503–506.

**Not scheduled by design:** the four skeletons (483–486), the M-CODEQUAL remainder (459–463), the
ADR-061 decommission tail (465, 468–470), M-TOOLING 479–482, and the handoff/registry debt (489–494,
500–502).

---

## Owed before anything else proceeds

| task | pri | status | title |
|---|---|---|---|
| **TASK-488** | **P1** | **DONE 2026-08-16** — verified, nothing reverted | review `a044f5d` / `78caa95` / `b36f184` per M-SRCLAYOUT §7a, and take the owed DUT baseline |
| **TASK-529** | **P1** | **DONE 2026-08-22** — DUT baseline taken, clean | take the owed DUT baseline for TASK-471/472 (`2a2f83e`..`7669460`, 16 commits) — same discipline as TASK-488. **Correction: the original filing of this task wrongly stated "no DUT in this environment" — a DUT was connected on `/dev/ttyUSB0` the whole session; that was an unverified assumption baked into three subagent prompts, caught by the user, not a real environment limit.** Once corrected, the baseline was taken for real. `run/task488` (39 app switches, taskbar, 9 player-mode cycles, 7 Settings sections): **T_488_04-09 all PASS**. T_488_10 FAIL is a stale test-harness artifact (`_EXPECTED_CMDS` hardcoded from `b36f184~1`, months before `playerCycle`/`sdopendir`/`sdslots` existed — `missing=[]` proves nothing was dropped by this session's work). T_488_11 FAIL (heap decline over repeated sweeps) matches already-documented pre-existing drift (TASK-504/505), reproduced on pre-refactor firmware too — not a regression. Additional ad-hoc DUT check for TASK-472 specifically (`app/tools/lib/dut.py`, one-off scripts, real serial + real network fetches, not the `run/task488` harness which predates the Stock split): **List, Chart, and Heatmap all verified working end-to-end** — `quoteOkCount` advanced after a forced List fetch, `fetchOkCount` advanced after a real tap-drill into Chart (drove production touch dispatch, not just a debug shortcut), `heatmapCount` reached 20 after a forced Heatmap fetch — confirming the `StockChart`/`StockHeatmap` split's shared-state design (friend + back-reference into the one `StockAppState`) works under live conditions, not just in source review. Production firmware restored via `run/flash` on completion |

#### TASK-488 — result, 2026-08-16

**All three commits are verified as pure moves. Nothing was reverted.** Run by a fresh agent against
the pass criteria below; harness is `app/tools/test_task488_partb.py`, driver `run/task488`, raw logs
in the session scratchpad.

| id | verdict | evidence |
|---|---|---|
| `T_488_01` | **PASS** | All 14 moved blocks byte-identical **and contiguous, in original order**. Removed-vs-added line multisets differ only by added preamble (`#pragma once`, includes, header comment) plus, for `a044f5d`, the 19 struct lines it declares deleted. |
| `T_488_02` | **PASS** | `SpotifyAppState` / `ClockAppState` / `AquariumAppState`: **0** code references at `a044f5d~1`. Only design docs mention them → TASK-503. |
| `T_488_03` | **PASS** (stronger than asked) | `.text`/`.rodata`/`.data`/`.bss` extents **identical to the byte** at `a044f5d~1`, `b36f184` and HEAD — 0 B delta, not "<512 B". `firmware.bin` differs by 66 B (prod) / 73 B (debug): build timestamp, injected git hash, app-descriptor SHA256, image checksum. Nothing else. |
| `T_488_04` | **PASS** | 39/39 switches landed on the requested id; no reboot, WDT or Guru Meditation. |
| `T_488_05` | **PASS (partial)** | Aquarium — one of the three deleted-struct apps — logged `init` on cycle 1 only and `resume` on cycles 2 and 3, exactly as specified. **The other eleven apps emit no init/resume marker**, so the criterion is not observable for them without firmware instrumentation, which is out of scope for a verification-only session. Recorded as not-observable, not inferred. |
| `T_488_06` | **PASS** | Clock style `[3,3,3]`, Aquarium fish `[8,8,8]` across three re-entries each; Spotify probe readable throughout. |
| `T_488_07` | **PASS** | 15 taps over 3 scroll rounds; every slot landed on the app its icon showed. |
| `T_488_08` | **PASS** | 9/9 mode transitions, `playerMode` tracked each one. |
| `T_488_09` | **PASS** | All 7 sections entered (`section` 0..6) and each returned to the category list. |
| `T_488_10` | **PASS** | `help` lists exactly the 26-command `kCmds[]` set, which a static diff confirms is unchanged from `b36f184~1`; all **108** `get` keys resolve, none "unknown". This is the criterion most likely to catch a bad console move, and it is clean. |
| `T_488_11` | **FAIL as written — NOT ATTRIBUTABLE** | See below. |

**`T_488_11` — why no commit was reverted.** The criterion fails its literal threshold but cannot
implicate these commits, on two independent grounds:

1. **The binaries are the same machine code.** `cyd2usb_winamp_debug` at `78caa95~1` and at HEAD
   differ by 73 bytes, all of it build metadata. Heap behaviour cannot differ between them.
2. **A/B on hardware.** The same test flashed against pre-refactor firmware reproduced the same
   decline, slightly **worse**: −7548 B on sweep 3 versus HEAD's −3756 B.

The criterion is also not measurable as specified on this DUT: entering WebRadio / LocalPlayer takes
and releases the ~48 KB A-lite audio arena, which swamps the signal — one pre-refactor sweep read
**+39144 B**. With the players excluded the per-sweep deltas were −10576, −8580, **+24**: front-loaded
allocation reaching steady state, not an unbounded leak. An idle control of equal duration drifted
0 B / +40 B / −32 B across runs, so the harness itself is sound.

**This is a deliberate deviation** from the handover's "on any Part B failure, revert the offending
commit". There is no offending commit; reverting would not move the number. Redesign of the criterion
is TASK-504; the pre-existing settling behaviour is TASK-505.

### TASK-488 — pass criteria

*Written 2026-08-16. Previously this task's procedure was one sentence with no id, steps, iteration
count or fail condition — below the bar `T_AE_04` sets (×10 iterations, a 100 ms bound). Running it
as written would have been closing against a proxy (BP-061): nothing visibly breaks, it gets called
verified.*

**Scope.** `a044f5d` (App interface → `app.h`, three unused state structs deleted), `78caa95` (seven
App classes → `apps/`), `b36f184` (SERIAL_DEBUG console → `debug/serialConsole/`). All three claim to
be **pure moves**. The claim is unverified.

#### Part A — static, host-only, no DUT (do this first; it may fail the whole task cheaply)

| id | Check | PASS | FAIL |
|---|---|---|---|
| `T_488_01` | Each moved block is byte-identical. For every block: `git show <commit>~1:app/src/main.cpp \| sed -n 'A,Bp' > /tmp/before` vs the same span extracted from its new file | **every diff empty** | any non-empty diff → the commit is not a pure move; stop and re-scope the task |
| `T_488_02` | Deleted structs were truly unreferenced: `git grep -c '\bSpotifyAppState\b' a044f5d~1` etc., excluding `appShell.h` | 0 for all three | any hit → a deletion removed live code |
| `T_488_03` | Production binary essentially unchanged. Build `cyd2usb_winamp` at `a044f5d~1` and at HEAD; compare `.text`/`.rodata`/`.data`/`.bss` extents from the `.map` | deltas explained by `__FILE__`/`__LINE__` shifts only; **no section moves >512 B** | a larger delta means something other than a move happened |

#### Part B — DUT. **Flash `cyd2usb_winamp_debug`.** Requires the device.

Run each step **three full cycles** unless stated. Three, not one: `g_appLaunched[]` makes the first
visit to an app call `init()` and every later visit `resume()` — a one-pass sweep exercises only
`init()` and would miss a broken `resume()` entirely. That is the specific bug class these commits
could introduce.

| id | Procedure | PASS | FAIL |
|---|---|---|---|
| `T_488_04` | `switchapp 0` … `switchapp 12` in order, ×3 cycles (39 switches). After each, `info` | every switch reports the requested id; every app renders; **no reboot, no WDT, no Guru Meditation** across all 39 | any wrong id, blank screen, or reset |
| `T_488_05` | Same sweep, watching `init`/`resume` in the serial log | each app logs **`init` exactly once** (cycle 1) and **`resume` on cycles 2 and 3** | an app that re-inits, or never resumes |
| `T_488_06` | **Spotify, Clock, Aquarium specifically** — the three whose state structs `a044f5d` deleted. Enter, leave, re-enter ×3 each | state persists across re-entry as before (Clock keeps its style, Aquarium its fish, Spotify its track) | any state reset that did not reset before |
| `T_488_07` | Taskbar: tap every visible slot, scroll, tap again — ×3 | each tap lands on the app its icon shows | any slot→app mismatch (the TASK-413 remap shape) |
| `T_488_08` | Eject from each player mode: Spotify → WebRadio → Player → Spotify, ×3 | the cycle completes and `get playerMode` tracks it | a mode that will not leave, or lands wrong |
| `T_488_09` | Settings: open, enter and leave **all seven sections**, ×1 (Settings was a moved class) | every section renders and returns cleanly | any section blank, or a return that lands elsewhere |
| `T_488_10` | Debug surface (whole console moved by `b36f184`): `help`, then **`get` on every key it lists** | `help` lists the same command set as before the move; **every key resolves** — no "unknown" | any missing command or unresolvable key |
| `T_488_11` | Heap stability: `get heap` before cycle 1 and after cycle 3 of `T_488_04` | free heap after ≥ before − 2 KB | a monotonic decline suggests a changed static lifetime |

#### Explicitly NOT a pass

- **"I flashed it and it looked fine."** That is the proxy this section exists to prevent.
- `./run/check` green. It proves compilation, not behaviour, and was already green when these commits
  landed unverified.
- Part A passing alone. Byte-identical text can still change behaviour via include order or static
  init order — that is what Part B is for.
- Any part **skipped** because the device was busy. Record it as skipped; do not infer it.

#### On failure

A failing `T_488_01` means a commit is mis-described, not necessarily broken — re-scope and re-review.
A failing Part B means **revert the offending commit** rather than patch forward: these are moves, so
reverting is cheap and the alternative is debugging a refactor nobody has verified.

**Pairs with TASK-497** — the retrospective ≥3-run baseline runs in the same DUT session, against
`78caa95~1` and then HEAD. One hardware block covers both.

---

**TASK-488 — review the three landed refactor commits**
**Owner**: human + VE · **Design**: [M-SRCLAYOUT §5a, §7a](../architecture/designs/M-SRCLAYOUT-main-decomposition.md)
Three commits assert pure moves. That assertion is unverified by anyone but their author. §7a gives
the recipe: `git show -M --stat`, byte-identity diffs of each moved block against
`git show <commit>~1:app/src/main.cpp`, `.map` extents before/after, and the zero-reference proof for
the three deleted structs (`SpotifyAppState`, `ClockAppState`, `AquariumAppState`). `run/check` 7/7
covers compile + smoke only — the DUT pass over app switching, taskbar cycling, eject and Settings
navigation has **not** been run. **Nothing in this board should land until this closes.**

> **CLOSED 2026-08-16.** Performed in full; all three commits verified, nothing reverted. Result
> table above. The gate this paragraph describes is lifted.

---

## M-SRCLAYOUT — decompose main.cpp ([design](../architecture/designs/M-SRCLAYOUT-main-decomposition.md) · [ADR-060](../architecture/decisions/ADR-060.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-453 | — | **LANDED, VERIFIED 2026-08-16** | Stage A — 7 app classes → `apps/*.h` (`78caa95`) |
| TASK-454 | — | **LANDED, VERIFIED 2026-08-16** | Stage B — SERIAL_DEBUG console → `debug/serialConsole/*.h` (`b36f184`) |
| TASK-455 | — | **LANDED** (`8cb5578`) — pure move proven by symbol identity, per design doc §5 | Stage C — `setup()` (621 lines) → `boot/boot.h`, verbatim (D1a) |
| TASK-456 | — | **LANDED, DUT-VERIFIED** (`825da41` part 1, `63aad48` part 2, `ca74819`) | Stage D — `shell/appTable.h` composition root + `ShellState` (D2/D3/D4) |
| **TASK-471** | P3 | **DONE 2026-08-22** — 28 commits (`2a2f83e`..`0bcd0c2`); DUT baseline taken and clean, **TASK-529** | Stage E — component conversion; real `.h`/`.cpp` pairs, self-contained (D0). **Every entry in the design doc's D1 target tree is now landed**: all 13 apps + `audioEngine`/`appTable` (prior sessions); all 6 `debug/serialConsole/cmd*.h` files + `console.h/.cpp` + `touchDebugOverlay.h/.cpp`; the production `sd/sdMount.h/.cpp` (ADR-061 D4 — not under `debug/`); `shell/taskbar.h/.cpp` (relocated from `taskbar/`); `appShell.cpp` (dispatch/switchApp/appHandleInput/appTick/persistPlayerMode/resolvePlayerTap/shellTb* group — kept at its existing path rather than relocating, re-scoped down from the doc's stale ~360-line estimate since `ShellState` left in Stage D already); and **`boot/boot.cpp`** (`0bcd0c2` — the 636-line `setup()` body, the highest-risk conversion in the stage given its documented boot-ordering incident history, TASK-288/404/426). `main.cpp`: **1042 → 357 lines** across this session. Every one of the 12 conversions this session measured **0 B `dram0_0_seg` delta**; `boot.cpp`'s `setup()` body was additionally diffed byte-for-byte against its pre-move text (0 lines differ) given its own header's "pure move, byte-identical .map" contract. `run/check` 12/12 held after every commit, including `cyd2usb_player`/`cyd2usb_winamp` production-env builds. Four hardcoded test-tool anchors (`check_player_binding.py`'s `EXPECTED_CALLERS` + its two body-location checks, `check_app_conformance.py`'s `CMDGET` constant) were updated to new file locations along the way — pure-move ledger corrections, not behaviour changes. The `taskbar`/`appShell`/`boot` conversions were done by subagents under PM orchestration; each was independently re-verified (build, `.map` delta, byte-diff where applicable, `run/check`) by the orchestrator before being accepted, per the user's "you orchestrate, you control, you ensure the quality" instruction. **`stock/`'s 3-way split (TASK-472) is a separate, not-yet-started task** — not part of TASK-471's scope. TASK-494 (the feature-inventory join key) is now unblocked, per its own row above ("Blocked until components exist (TASK-471)") |
| **TASK-472** | P3 | **DONE 2026-08-22** — `stock/` split + DUT-verified (`7669460`/TASK-529), levelization audit complete | Stage F — `stock/` → 3 components (**done**: `stockApp`/`stockChart`/`stockHeatmap`, `StockAppState` kept unified as one shared data model per the design doc's own wording, `StockChart`/`StockHeatmap` reach it via a `StockApp&` back-reference + `friend`; the three debug counters' distinct ownership — `fetchErrCount` List+Chart, `fetchOkCount` Chart-only, `quoteOkCount` List-only — verified against the pre-split code and preserved exactly, independently re-checked by the orchestrator by reading the new source, not just trusting the subagent's report, and DUT-confirmed live), `sd/sdMount` (**already landed under TASK-471**, `3f06f9c`). **Levelization audit (D0d) — done, real dependency-graph check, not a doc re-read**: (1) zero app-to-app includes anywhere — the only level-3→level-3 edges are `stock/`'s own internal structure (`stockChart`/`stockHeatmap` → `stockApp.h` via this session's back-reference pattern), which is one app's internal decomposition, not a cross-app violation, same shape `winamp/pleditView.h` precedent; (2) zero level-0/1 file includes `apps/` or `shell/`, checked both directions across the whole tree; (3) **the doc's one flagged violation is confirmed closed, not just "accepted"**: read `winampDisplay.h` directly — it no longer references `AppId`/`currentAppId`/player-mode globals at all, it uses a `_playerCaps` bitmask (`CAP_TRANSPORT`/`SEEK`/`SHUFFLE`/`REPEAT`) set via `setPlayerCaps()` from the app layer; ADR-059's capability mask genuinely landed. One necessary, intentional exception found: `shell/appTable.h` (level 2, the composition root) includes all 13 apps (level 3) — the sole place level 2 depends on level 3, required because its job is constructing every app instance; D0d's "level 2 may depend on 1, 0" phrasing should note this exception explicitly (doc fix, not a code fix). **Real gap surfaced, filed as TASK-530**: 5 of 13 apps (`clockApp`/`teletextApp`/`planeRadarApp`/`webRadioApp`/`localPlayerApp`) got the Stage E `.h`/`.cpp` split but never moved into `apps/`, despite D1's target tree explicitly placing all of them there — causes no actual dependency violation (confirmed above), but the directory layout doesn't match the design doc's stated end-state |
| **TASK-530** | P4 | **DONE 2026-08-22** (`fc8b713`) | moved `clockApp`, `teletextApp`, `planeRadarApp`, `webRadioApp`, `localPlayerApp` from `app/src/` top level into `apps/` via `git mv`, per D1's target tree. All 13 apps now correctly placed (`apps/` × 11, `stock/` × 1, `aquarium/` × 1). Pure relocation, done by subagent under PM orchestration, independently re-verified: 0 B `.map` `dram0_0_seg` delta, old paths confirmed fully cleared, `cyd2usb_winamp_debug`/`cyd2usb_winamp`/`cyd2usb_player`/`cyd2usb_webradio` all build clean, `run/check` 12/12 including Teletext/PlaneRadar/WebRadio/LocalPlayer's A5/A6 conformance rows |
| TASK-457 | P3 | OPEN | hygiene — `appRegistry.h` double-include comment, `currentAppId`/`g_previousAppId` unify |
| TASK-464 | — | **LANDED** (`f8bae91`) — 331 `main.cpp:NNN` cites across 57 files converted to symbol references (scope was larger than filed: 308/49); TASK-503 folded in; `run/check --docs-only` PASS | documentation-reference sweep, paid once at end of Stage B |

## M-CODEQUAL — duplication and abstraction ([design](../architecture/designs/M-CODEQUAL-duplication-and-abstraction.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-458 | **P2** | **UNBLOCKED** — but see the TASK-495 ordering note | C2 — `TlsYieldGuard` / `HttpSession` RAII guards. **Highest value in this board**: fixes a bug class with a proven production instance (TASK-222). *@PM: the table said OPEN while this file's own prose said "gates TASK-458" — corrected. **Fold TASK-495 in as 458's first step**, not a separate schedulable item; it is a 30-minute decision, not a build.* |
| TASK-459 | P3 | BLOCKED on 458 | C2b — migrate `s_aeSpotifyYielded` to a transferable guard. Touches audio teardown ordering (`T_AE_04`) |
| TASK-460 | P2 | BLOCKED on 458 | C1 — consolidate the nine `fetch*()` functions onto one skeleton |
| TASK-461 | P2 | OPEN | C5 — one canonical canvas/window constant across firmware, bake and previews. 275 has **six names in three layers** |
| TASK-462 | P3 | **UNBLOCKED** (454 verified) | C3 — table-driven `cmdGet`/`cmdSet` (1 308 lines → a table) |
| TASK-463 | P3 | OPEN | C4 debug-code convention + C6 shared UI palette |

## ADR-061 — build-variant hygiene ([ADR](../architecture/decisions/ADR-061.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-465 | P3 | OPEN | D1–D5 — debug/production convention across `app/src`; propose to QM as a BP |
| TASK-466 | — | **LANDED** (`dff3263`) | D6+D7 — full-matrix build gate (66 s measured) + three name-consistency checks |
| TASK-467 | — | **LANDED** (`0b1d13e`) | D8 — decommission: `cyd2usb`→base, `matrixDisplay.h`, `SPIKE_MODE`, ceefax leftovers, 10 libdeps orphans, doc corrections |
| TASK-468 | P2 | OPEN | D9 step 1 — `display/tft.{h,cpp}` component; rehome the 797-call-site global |
| TASK-469 | P3 | BLOCKED on 468 | D9 step 2 — flatten `WinampDisplay` onto `SpotifyDisplay` |
| TASK-470 | P3 | BLOCKED on 469 | D9 step 3 — delete `cheapYellowLCD.h` and `[cyd2usb_base]` |

## M-CONCURRENCY / IFC ([design](../architecture/designs/M-CONCURRENCY-task-ownership-contract.md) · [IFC-002](../architecture/interfaces/IFC-002.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-473 | P2 | OPEN | close the contract's gaps — G1 WiFi radio arbiter (three bugs: X014, TASK-436, TASK-404), G2 assert I2/I3, G3 dual mirrors |

## M-DOCLIFE — document decay ([design](../architecture/designs/M-DOCLIFE-keeping-design-docs-alive.md) · [spec](../architecture/designs/M-DOCLIFE-check-docs-spec.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-475 | **P2** | **PHASE 1 DONE 2026-08-16** (`b0d0202`) — phases 2–5 remain |  `run/check-docs` shipped: C5 + C1-`delta` blocking, C1-full/C2/C3 advisory, C4 unruled; counted gate 12; `T_DOC_01`–`09` registered. **Phase 2 (C2 blocking) is a one-line promotion — C2 already reads 0.** Phase 3 needs ADR-061 D8; phase 4 needs TASK-508. Baselines re-taken at `efab524`: C5 **0** (blocking day one, holds), C1 **280/599** advisory + `delta` blocking, C2 **0** via [A1]'s glob, C3 **9**, C4 **struck, order 100–200** → TASK-508. Amendments [A1] C2 resolution set (138 false failures), [A2] `delta` diff base defined, [A3] C4 baseline struck. **Then @Architect-reviewed: falsified 3 of the amendments' own numbers, found 11 further defects; 5 were handoff-blocking and are now fixed** (failure unit, exemption-vs-resolver, C3 detection rule, OQ1 contradiction, split-file carve-out), plus §5a exit criteria added. **Then @VE-reviewed, which found the killer**: C1-`delta` fails on the amendment commit itself, twice — once on an illustrative `file.h:46` (needs a suppression rule) and once on a **correct** citation C1's flat root list cannot resolve (10 of 282 failures are the checker's fault). E4's pinned live numbers were stale on arrival (280/599 → **282/601**), environment-dependent (**286** in a clean checkout — three citations resolve only via the untracked sibling repo) and self-contradictory (C3 is 60 occurrences / 9 names). Exit criteria rebuilt as E1–E9 around a **committed fixture corpus**; `T_DOC_01`–`09` reserved in `test_plan.md` **before** the harness, per E9. |
| TASK-508 | P2 | OPEN — **blocks `run/check-docs` phase 4** | C4 status-vocabulary migration: **order 100–200** architecture-doc headers (the exact count is undefined until the matching rule is — @Architect measured 100–218 across eight plausible readings, so **91 was struck**) use `done`/`planned`/`implemented`/`resolved`/`updated`/`draft` instead of the closed vocabulary. Filed by amendment [A3] to the check-docs spec, which had quoted 67 corpus-wide hits as the reason to scope C4 — scoped, it is 91. Needs an Architect ruling on how landed work is spelled, and on whether C4 matches on prefix (M-SRCLAYOUT's header is `partially landed; Stages A and B VERIFIED …`). |
| TASK-474 | P3 | OPEN | PM/QM process items — `docs-touched:` in exit criteria, closed status vocabulary, reservations land immediately |

## M-TOOLING — host tool architecture ([design](../architecture/designs/M-TOOLING-host-tool-architecture.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-478 | — | **LANDED** (`989c1ea`) | `tools/lib/dut.py` — one DUT session helper, delegating to `run/port`. Re-scoped in landing: `Dut` already existed with 16 importers, so this was an extraction + `resolve_port()` + one timeout policy, not a build |
| TASK-479 | P3 | OPEN (478 landed) | migrate 33 port-resolution copies + 29 send/expect loops onto it |
| TASK-480 | P2 | OPEN (478 landed; still behind 479) | split `run_serialdbg_tests.py` (10 229 lines, 128 tests) into `suite/serialdbg/`, mirroring the VE taxonomy. **≥3 baseline runs owed first** |
| TASK-481 | P3 | BLOCKED on 480 | directory + naming taxonomy; pair with TASK-464 (breaks doc paths) |
| TASK-482 | P3 | BLOCKED on 475 | spike retirement rule — a `task<NNN>_*` whose task is archived fails `run/check-docs`. All 6 current spikes fail immediately |

## Vendoring / `app/lib` ([ADR-060 D2b](../architecture/decisions/ADR-060.md))

| task | pri | status | title |
|---|---|---|---|
| TASK-476 | P3 | OPEN | relocate `mb_arena` → `app/src/mem/arena`. **Blocked on an unanswered question**: can a PlatformIO `lib/` dir include from `src/`? Answer that first |
| TASK-477 | — | **LANDED** (`f2730cc`) | fix `mb_arena.h`'s header comment — it claims production is "byte-clean"; `platformio.ini:93` defines `MEMBUDGET_PHASE1` in `[env:cyd2usb_winamp]` |

## Skeletons — problems with a home, not yet designed

Each has a **SKELETON** banner: a starting point, no conclusions, expect to restructure rather than
fill in.

| task | pri | status | title |
|---|---|---|---|
| TASK-483 | P3 | SKELETON | [M-TESTARCH](../architecture/designs/M-TESTARCH-test-architecture.md) — test architecture. **VE owns OQ1**: a host unit tier may not be worth it here |
| TASK-484 | P3 | SKELETON | [M-ERRMODEL](../architecture/designs/M-ERRMODEL-error-model.md) — four overlapping error conventions; IFC-001 already ships the `errorCode==0` ambiguity |
| TASK-485 | P2 | SKELETON | [M-LEVELS](../architecture/designs/M-LEVELS-dependency-audit.md) — audit D2a's asserted levels. **No include graph has ever been generated**; the audit may contradict D2a |
| TASK-486 | P3 | SKELETON | [M-VENDORING](../architecture/designs/M-VENDORING-upstream-policy.md) — five vendored trees, five conventions, no upstream refs recorded |
| ~~TASK-487~~ | — | **FOLDED into TASK-493** | @PM: a five-minute re-read, not a milestone thread. Carry it as a checklist line on the `architecture.md` sync, not a standalone task id. The doc stays. |

## Handoff debt — reservations the Architect owed and did not perform

These are the failure AGENTS.md rule 10 was written to prevent, reproduced by the pass that cited
the rule. Filed 2026-08-16 after a second sweep for uncaptured items.

| task | pri | status | title |
|---|---|---|---|
| TASK-489 | P2 | **DONE 2026-08-16** | reserve X065 in `cross_feature_matrix.yaml` — Developer completes |
| TASK-490 | P2 | **DONE 2026-08-16** | reserve `T_CC_`/`T_SRC_`/`T_CQ_` families in `test_plan.md` — VE completes |
| TASK-491 | — | **LANDED** (`e2f70db`) | correct X015 — it claims `dataTask` runs on Core 0; it pins to `APP_CPU_NUM` |
| TASK-492 | P3 | OPEN | retire `handleVolumeGesturePublic()` — M-AUDIO-ENGINE OQ2's surviving half |
| TASK-493 | P2 | OPEN | sync `architecture.md` — its diagram still shows `loop()` as the app shell |
| TASK-494 | P3 | OPEN | `feature_inventory.files:` → `components:` once components exist |

**TASK-489 / TASK-490 — reservations performed.** M-SRCLAYOUT's header claimed *"registers as
X065"*; the matrix contained no such row. M-CONCURRENCY mined 24 matrix entries and registered none
back. ~19 test ids (`T_CC_01–05`, `T_SRC_01–08`, `T_CQ_01–06`) existed only inside design docs, with
`test_plan.md` — which VE owns — untouched. Both now carry **reservations**, explicitly marked
incomplete: Developer corrects and completes the matrix row, VE writes the test entries and may
rename or discard any of them. The Architect reserves; it does not fill in other roles' files.

**TASK-491 — X015 is factually wrong.** It states *"dataTask fetch functions … run on Core 0"*.
`dataTaskStorage.cpp:117` pins to `APP_CPU_NUM` (core 1), and `git log -S'PRO_CPU_NUM'` shows it
never did otherwise. The entry's *conclusion* (spinlock-published results) is correct; its stated
reason is not. Matters because IFC-002 §1.1 turns on all four contexts sharing one core — a reader
who believes X015 will reason about SMP races that cannot occur. Developer owns the file.

**TASK-492 — `handleVolumeGesturePublic()`.** M-AUDIO-ENGINE OQ2 had two halves. The first — the
Spotify-hardcoded `handleWinampInput()` — **is fixed**: ADR-059 D7's capability mask landed and
`winampDisplay.h:593-597` gates every zone on `_playerCaps`. The second is the workaround that
hardcoding forced: `handleVolumeGesturePublic()` at `winampDisplay.h:696`, still called from
`webRadioApp.h:821`. OQ2 is explicit that it must be retired **in its own commit, never as a side
effect** — it shares the `D_VOLUME_DRAG` state machine (TASK-352), and WebRadio's volume-drag path
already cost TASK-406 a missing-log-line bug.

**TASK-493 — `architecture.md` sync.** AGENTS.md rule 8 makes this the Architect's job. Line 49 still
draws `loop() — app shell (appShell.h)`, which the three landed commits and ADR-060 D0/D1 both
contradict. **Do it after TASK-488**, not before: the living spec should reflect *validated*
implementation, and none of it is validated yet.

**TASK-494 — the inventory join key.** `feature_inventory.files:` is the only mapping between the
functional decomposition (81 features) and the physical one (~28 components). It broke the moment
Stages A/B landed. Pointing it at components instead of files makes it survive moves — and makes
"31 of 81 features list `main.cpp`" into a metric rather than noise. Blocked until components exist
(TASK-471).

---

---

## From the @Developer review, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| **TASK-495** | P3 | **PARKED 2026-08-16 — decided, not implemented** | `fetchCrypto` moves its `tlsResume()` to after its JSON parse, matching `fetchWeather`. Decision made (E-02, resume-AFTER); the two-line change is deliberately not scheduled. **Read the ordering note below before touching TASK-458 or TASK-460.** |
| TASK-496 | — | **LANDED** (`33b3003`) | `appRegistry.h` has no conditional-compilation column; 3 of 13 apps are `#ifdef WINAMP_DISPLAY` |

> ### ⚠ PARKED 2026-08-16 — read this before starting TASK-458 or TASK-460
>
> **The decision is made; the code change is not.** Parking is safe *on its own* — the divergence has
> existed for months and no reported symptom is attributed to it. What is **not** safe is doing
> TASK-458 or TASK-460 while this stays parked.
>
> A `TlsYieldGuard` scoped to end-of-function, or the C1 fetch consolidation, **normalises crypto to
> resume-after as a side effect.** That happens to be the correct outcome — so it would not be a
> *bug*, it would be an **untracked behaviour change buried inside a refactor.** If crypto then
> misbehaves, nothing distinguishes "the guard broke it" from "the timing change broke it", which is
> exactly the diagnostic trap `tasks-winamp-player.md`'s post-mortem is about.
>
> **Therefore: if TASK-458 or TASK-460 is scheduled, TASK-495 lands first, as its own commit.** Two
> lines, ten minutes, bisectable. It is not worth scheduling alone, and it must not be skipped in
> front of those two.
>
> **RESOLVED 2026-08-16 (E-02, human): resume-AFTER the parse.** `fetchCrypto` changes to match
> `fetchWeather`; the stale comment at `dataTaskStorage.cpp:262-265` claiming they already match
> becomes true. Rationale: resume-before hands heap back sooner but lets the Spotify task reconnect
> *during* a parse — the TASK-289 shape. Resume-after is the safer of the two and is what the
> `TlsYieldGuard` scoped to end-of-function would produce anyway, so TASK-458 no longer has to change
> behaviour silently. **TASK-458 is unblocked**; do this as its first commit, separately, so the
> behaviour change is reviewable on its own.
>
> *Original finding, retained:*
> **TASK-495 — a live divergence, found by review, verified in source.** `fetchWeather` resumes the
Spotify TLS session **after** its JSON parse (`dataTaskStorage.cpp:311`; parse `:289-309`).
`fetchCrypto` resumes **before** its parse (`:360`; parse `:362-386`). The comment at `:262-265`
asserts weather *"matches crypto below"* — it does not. One of these is wrong, or the difference is
deliberate and undocumented; nobody currently knows which. **This must be settled before TASK-458's
`TlsYieldGuard` lands**, because a guard scoped to end-of-function silently moves crypto's resume to
after its parse — changing when Spotify may reconnect and re-take heap mid-parse. A refactor must not
make that decision by accident. Blocks TASK-460 (C1) and gates TASK-458.

**TASK-496 — the composition root cannot be built as designed.** `main.cpp:242-245` / `:296-303` gate
`SpotifyApp`, `WebRadioApp` and `LocalPlayerApp` behind `#ifdef WINAMP_DISPLAY`, and `:314-321`
already forks `g_apps[]` — populated under that flag, `{}` otherwise. ADR-060 D2's X-macro sketch has
no conditional mechanism. Resolve by **retiring `cyd2usb`** (ADR-061 D8 already proposes demoting it —
so TASK-496 and TASK-467 are interdependent) or by adding a conditional column to the registry.
Un-gated today because `check_build.sh` builds only `WINAMP_DISPLAY` envs — which is ADR-061 D6's
argument arriving from a second direction. **Blocks TASK-456.**

---

## From the @VE review, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| **TASK-497** | **P2** | **DONE 2026-08-16** — 3 runs at HEAD; base-tree half retired on evidence | retrospective ≥3-run DUT baseline for the landed Stages A/B. *@PM: worth paying for — it is the only way left to recover D13's guarantee, and the cost is bounded and one-time. But it needs the same DUT block as 488's diff review. **One scheduling block, not two.*** |
| TASK-498 | P3 | OPEN | `T_SRC_09` — regression test for IFC-003 I9 (the TASK-384 swallow shape) |
| TASK-499 | P3 | OPEN | a `T_CC_` id for M-CONCURRENCY G1: enumerate every `WiFi.` call site against the known-safe set |

**TASK-497 — the baseline window is not closed, but it now costs double.** ADR-059 D13 and
`T_SRC_01` both require ≥3 full runs *before* a stage lands. Stages A (`78caa95`) and B (`b36f184`)
landed without one. @VE's ruling: because both are claimed **pure text moves**, the pre-refactor tree
still exists in git — checkout `78caa95~1`, run the suite 3×, then diff against 3 fresh runs on
master. That **does** recover D13's actual guarantee (no test passing in all baselines fails after).
What it cannot recover is catching a regression *live*, when a bisect would have been cheap.
**"We'll trust the diff review instead" is explicitly insufficient** — that is the
review-reinforces-a-wrong-frame failure the milestone note called out. Pairs with TASK-488.

**TASK-497 — result, 2026-08-16.** Three full `./run/test` runs at HEAD (`3d300e4`), same DUT
session as TASK-488, sleep-inhibited, each trap-restoring production.

| run | passed | failed | skipped | flaked |
|---|---|---|---|---|
| 1 | 138 | 15 | 47 | 5 |
| 2 | 133 | 17 | 51 | 4 |
| 3 | 134 | 16 | 51 | 4 |

**Stable core — failed in all three runs (6):** `T_WR_TLS_01`, `T_WR_COEX_01`, `T_WR_VOL_03`,
`T_WR_EJECT_02`, `T_PLR_06`, `T_PRM_02`. `T_WR_TLS_01` is the root — station fetch failed on every
mirror (the TASK-284 truncation shape) — and the four other WebRadio/Player ids all need a station
list, so they cascade from it. None sits near the moved code.

**Union across the three runs: 29 ids — so 23 of 29 failures are run-specific.** Environmental noise
outweighs deterministic failure on this rig by roughly 4:1. Run 2's extra failures were a network
degradation visible in the diagnostics as the dataTask backoff counter climbing `cf=17→19` (`T186`,
`T188`, `T192`, `T193`, `T204`, `T-BUSY-01`, `T272`); run 1's extra failures were missing SD fixtures.

**That ratio is the baseline's real product.** D13's guarantee — *no test passing in all baselines
fails after* — can only be read against the 6-id core; a single post-change run proves close to
nothing here. Anyone comparing a future run against this baseline must compare **sets**, per LL-104.

**The base-tree half was retired on evidence, with human sign-off.** The plan was 3 runs at
`78caa95~1` then 3 at HEAD. `T_488_03` established that the debug binaries at those two trees are the
same machine code (73 bytes of build metadata apart), so the base-tree runs would have executed an
identical binary. The human chose to skip them. `78caa95~1` **does** build (verified), so the option
is still open if the ruling is ever revisited.

**TASK-499 — G1 has no test id at all.** M-CONCURRENCY calls the missing WiFi arbiter "the largest
unclosed gap" and then reserves nothing for it. If OQ1 there resolves to *document-only*, that
decision itself needs an id whose job is proving the three known collisions (X014, TASK-436,
TASK-404) have no fourth sibling waiting.

---

## Follow-ups raised by the TASK-467/496 implementation, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| TASK-500 | P3 | OPEN | X015 also calls `serialdbg` "Core 1" — but Arduino's `loop()` defaults to `CONFIG_ARDUINO_RUNNING_CORE=1`, the same core `dataTask` pins to. The entry may describe a **same-core**, not cross-core, interaction — which changes its framing, not just a label. Architect call. |
| TASK-501 | P3 | OPEN | ~20 further `#ifdef WINAMP_DISPLAY` blocks remain in `main.cpp` after TASK-496. The same logic applies — every env now defines the flag — but the implementing agent correctly stayed in scope rather than sweeping them. |
| TASK-502 | P3 | OPEN | `docs/process/project_run_scripts.md` and `dut_workflow.md` still say "5-gate". Stale before this session; now 11. **Widened 2026-08-16:** its § *Script → dut_workflow.md cross-reference* table is also missing **six** scripts — `ae04`, `wr-soak`, `stress`, `pr-soak`, `wr-gate` and the new `task488`. CLAUDE.md lists all of them, so the two disagree; fix the table in one pass rather than per-script. |

---

## Follow-ups raised by the TASK-488 verification, 2026-08-16

| task | pri | status | title |
|---|---|---|---|
| TASK-503 | — | **DONE**, via TASK-464 (`f8bae91`) | Design docs describing `SpotifyAppState` / `ClockAppState` / `AquariumAppState`. All five sites checked (`app-lifecycle.md`, `clock.md`, `source-ownership.md`, `M-AQUARIUM/overview.md`, `roadmap.md`) now carry an explicit "removed/superseded, deleted in `a044f5d`, retained as design record" note ahead of the struct text — none present the types as live. |
| TASK-504 | **P2** | OPEN | **`T_488_11` is not measurable as written** — redesign it. Entering WebRadio / LocalPlayer takes and releases the ~48 KB A-lite arena, which swamps a before/after free-heap read (one pre-refactor sweep measured **+39144 B**). Options: exclude the two player apps (`--no-players`, already implemented), or force arena release before sampling. Also mandate a same-duration **idle control** — a bare before/after at two uptimes cannot separate a leak from settling drift, which is what made the first run's −6768 B unreadable. |
| TASK-505 | P3 | OPEN | Free internal heap falls ~10 KB then ~8.6 KB over the first two 33-switch app sweeps, then flattens (+24 B on the third). **Pre-existing** — reproduced on pre-refactor firmware — so not a TASK-488 regression, but nobody has established whether the plateau is genuine or just a slower slope. Wants a longer sweep count on a quiet rig. |
| TASK-507 | P2 | **DONE 2026-08-16** | **`T_488_04`–`T_488_11` exist as a harness (`app/tools/test_task488_partb.py`) but are not registered in `docs/verification/test_plan.md`** — eight ids with pass criteria, a driver script and a green run, invisible to the VE artifact that is supposed to be the test inventory. @VE to register, with `T_488_11` marked as the known-unmeasurable one pending TASK-504. Same class of gap TASK-490 was filed to prevent. |
| TASK-506 | P3 | OPEN | `./run/test` leaves user settings mutated: after the TASK-497 runs, `settings.json` came back with `clock.style` vfd→digital, `planeRadar.rangeIdx` 3→1 and `pollSec` 30→10, `player.mode`/`playlist`/`repeat` changed, and four `webRadio` fields including `volumePct` 55→49. BP-049's snapshot made it recoverable, but the suite should restore what it changes — `T_PRM_01` failing "prPollSec not persisted" is the same defect seen from inside. |

---

## PM note — the honest read

This board was produced in a single day by one Architect pass, and its shape reflects that. Three
things a scheduler should know:

1. ~~**Nothing here is verified.**~~ **Superseded 2026-08-16.** TASK-488 closed: Stages A and B
   (`a044f5d`, `78caa95`, `b36f184`) are verified pure moves — byte-identical blocks, identical
   `.map` extents, and a DUT pass over app switching, taskbar, eject, Settings and the whole debug
   console. TASK-497's 3-run baseline is taken. The chain below is unblocked; TASK-455 can start.
2. **The dependency chain is long and mostly serial** — 488 → 455 → 456 → 471 → 472. Anything
   promising "main.cpp under 40 lines" is five tasks away, not one.
3. **Four tasks are independently valuable and unblocked today**: TASK-458 (RAII guards, fixes a real
   bug class), TASK-466 (build matrix — an env has been broken for months), TASK-475
   (`run/check-docs`), TASK-478 (`lib/dut.py`). If this board gets partially scheduled, those four
   are the ones that pay for themselves without the rest.
