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

**Updated 2026-08-22** — the 2026-08-16 version of this table was stale (still listed TASK-478 and
the 455/456/471/472 decision as pending; both are long done). Corrected against `git log` and each
task's own row rather than carried forward. **Do these in order**; everything not listed stays
filed and unscheduled.

| # | Do | Why this position |
|---|---|---|
| ~~**1**~~ **DONE 2026-08-16** | ~~**TASK-488 + TASK-497 — one DUT block**~~ | Three refactor commits sit on master unreviewed with no baseline. Everything in M-SRCLAYOUT is gated on this, and **the cost of delay compounds**: each further commit on top widens the blame surface from one to four. Same hardware session covers both — 488's byte-identity/`.map` review and 497's retrospective ≥3-run baseline. |
| ~~**1a**~~ **DONE** | *(prerequisite, ~15 lines)* ~~**write TASK-488's pass criteria first**~~ | Its DUT procedure is currently one sentence — *"a pass over app switching, taskbar cycling, eject and Settings navigation"* — with no id, steps, iteration count or fail condition. Compare `T_AE_04`, which specifies ×10 and a 100 ms bound. **Running 488 without criteria is closing against a proxy (BP-061)**: nothing visibly breaks, it gets called verified. |
| ~~**2**~~ **DONE 2026-08-22** | ~~**Decide 455/456/471/472 on what 488 finds**~~ | **488 found nothing wrong — continuation, not rework.** TASK-471 (Stage E, every component conversion) and TASK-472 (Stage F, `stock/` split + levelization audit) both landed and are DUT-verified (**TASK-529**). `main.cpp` 1042 → 357 lines. TASK-530 (the audit's own follow-up — 5 apps that never moved into `apps/`) also done. See these four tasks' own rows for the full record. |
| ~~**3**~~ **PHASES 1, 2, 4 DONE** — phase 3 advisory by choice, phase 5 optional | **TASK-475** — `run/check-docs` | Phase 1 shipped (`b0d0202`): C5 + C1-`delta` blocking. Phase 2 (`5e46d92`) and phase 4 (`579775c`) shipped 2026-08-25: C2 and C4 both blocking now, both re-verified at 0 immediately before promotion. Phase 3 (C3) is unblocked (ADR-061 D8 / TASK-467 landed) but its count — 58 occurrences across 10 unknown env names, mostly historical ADR references to renamed/retired `cyd2usb*` envs — is not near zero, so it was left advisory and reported rather than force-promoted. Phase 5 (C1-full) needs the 279-citation backlog cleared first; the spec itself says this "likely stays advisory permanently... on purpose." Read TASK-475's own row in full — it records two independent reviews (@Architect, @VE) that each found real defects in the phase-1 landing. |
| ~~**4**~~ **DONE** | ~~**TASK-478** — `tools/lib/dut.py`~~ | Landed (`989c1ea`). Unblocked 479/480, both still OPEN. |
| ~~**5**~~ **DONE 2026-08-22** | ~~**TASK-458** — RAII guards — **with TASK-495 as its first commit**~~ | Real bug class with a proven instance (TASK-222). Both landed as two commits: TASK-495 (`1df8b33`) then TASK-458 (`15d3c55`). See their own rows for the full record, including a live double-`tlsResume()` defect found and fixed as a side effect. |
| **6** | **M-WINAMP-PLAYER** | Still paused, 12 entries in `tasks-winamp-player.md`. @PM would put **TASK-424** (SD write panic, card-independent) ahead of most of this board if DUT time is scarce. |

**Already done, do not re-schedule:** TASK-466 (build gate, 3 → 11 envs), 467, 477, 491, 496, 488,
497 (all 2026-08-16) — plus **TASK-471, 472, 478, 529, 530, 495, 458, 459, 460** (2026-08-21/25,
this session). **Next in sequence is #6, M-WINAMP-PLAYER (still paused) or TASK-424 if DUT time is
scarce.** TASK-475 phases 2–5 are also available and cheap if DUT time is the constraint instead.
New follow-ups from the TASK-488 verification: 503–506 (503 already DONE, see its own row).
TASK-535 (new, 2026-08-25) needs a live DUT run of TASK-460's four converted fetch paths once this
rig's WiFi comes back — blocked this session by a rig-wide AP outage, A/B-confirmed unrelated to
the code change (see TASK-460's own row).

**Not scheduled by design:** the four skeletons (483–486), the M-CODEQUAL remainder (461–463), the
ADR-061 decommission tail (465, 468–470), M-TOOLING 479–482, and the handoff/registry debt (489–494,
500–502).

---

## Owed before anything else proceeds

| task | pri | status | title |
|---|---|---|---|
| **TASK-488** | **P1** | **DONE 2026-08-16** — verified, nothing reverted | review `a044f5d` / `78caa95` / `b36f184` per M-SRCLAYOUT §7a, and take the owed DUT baseline |
| **TASK-529** | **P1** | **DONE 2026-08-22** — DUT baseline taken, clean | take the owed DUT baseline for TASK-471/472 (`2a2f83e`..`7669460`, 16 commits) — same discipline as TASK-488. **Correction: the original filing of this task wrongly stated "no DUT in this environment" — a DUT was connected on `/dev/ttyUSB0` the whole session; that was an unverified assumption baked into three subagent prompts, caught by the user, not a real environment limit.** Once corrected, the baseline was taken for real. `run/task488` (39 app switches, taskbar, 9 player-mode cycles, 7 Settings sections): **T_488_04-09 all PASS**. T_488_10 FAIL is a stale test-harness artifact (`_EXPECTED_CMDS` hardcoded from `b36f184~1`, months before `playerCycle`/`sdopendir`/`sdslots` existed — `missing=[]` proves nothing was dropped by this session's work). T_488_11 FAIL (heap decline over repeated sweeps) matches already-documented pre-existing drift (TASK-504/505), reproduced on pre-refactor firmware too — not a regression. Additional ad-hoc DUT check for TASK-472 specifically (`app/tools/lib/dut.py`, one-off scripts, real serial + real network fetches, not the `run/task488` harness which predates the Stock split): **List, Chart, and Heatmap all verified working end-to-end** — `quoteOkCount` advanced after a forced List fetch, `fetchOkCount` advanced after a real tap-drill into Chart (drove production touch dispatch, not just a debug shortcut), `heatmapCount` reached 20 after a forced Heatmap fetch — confirming the `StockChart`/`StockHeatmap` split's shared-state design (friend + back-reference into the one `StockAppState`) works under live conditions, not just in source review. Production firmware restored via `run/flash` on completion |

**TASK-488's full result table, pass criteria, and closed-gate note archived 2026-08-22** — see
[tasks-archive.md § TASK-488](tasks-archive.md#task-488-full-result--pass-criteria-archived-2026-08-22-from-tasks-architecturemd).
Summary: all three commits verified pure moves, nothing reverted; `T_488_01`–`10` PASS, `T_488_11`
(heap-stability threshold) FAILED as written but not attributable to the commits (byte-identical
binaries, A/B on hardware reproduced the same decline on pre-refactor firmware too) — redesign
filed as TASK-504, the pre-existing settling behaviour as TASK-505. The `T_488_*` ids themselves
are registered canonically in `docs/verification/test_plan.md`, not here.

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
| TASK-458 | **P2** | **DONE 2026-08-22** (`15d3c55`, after TASK-495's `1df8b33`) | C2 — `TlsYieldGuard` RAII guard. **Scope note (orchestrator decision, not the design doc's literal scope):** the `HttpSession` half of C2 was deliberately deferred — `http.begin()`/`http.end()` pairing in `dataTaskStorage.cpp` was already correctly balanced on every path (no proven bug, unlike tlsYield/tlsResume), so converting it would have added real risk across several different control-flow shapes (streaming parse, mirror-loop retries) for a DRY win only. Filed as follow-up below, not silently dropped. Added `spotifyTask::TlsYieldGuard` (`spotifyTask.h`) and converted all 8 functions in `dataTaskStorage.cpp` that owned a `tlsYield()`/`tlsResume()` pair (`fetchWeather`, `fetchCrypto`, `fetchStockQuote`, `fetchStockChartWithRetry`, `fetchTeletext`, `fetchHeatmapQuote`, `fetchGeocode`, `fetchWebRadioStations`); `fetchPlaneRadar()` intentionally left on the manual pattern (not one of the 8, out of scope). **Live defect found and fixed as a side effect**: `fetchTeletext()` called `spotifyTask::tlsResume()` *twice* on its "no `<pre>` block" path — once unconditionally right after `http.end()`, again in the early-return branch. Harmless today only because `tlsResume()`'s decrement is guarded at 0 (`spotifyTaskStorage.cpp:782-790`), but a genuine extra release; the guard conversion collapses it to exactly one release, structurally. Also extended `app/tools/check_app_conformance.py`'s A5 (TLS bracket) check to recognize a `TlsYieldGuard` local as an unconditional bracket, alongside the existing per-exit-path scan for the manual pattern (kept fully intact, still the live check for `fetchPlaneRadar()`); updated `test_check_app_conformance.py`'s mutation suite to match, including a synthetic fixture preserving regression coverage for the original TASK-222 bug shape now that no real function can reproduce it. Verified independently by the orchestrator, not just the subagent's report: diff read in full, `test_check_app_conformance.py` re-run (11/11), `run/check` re-run (12/12, including PlaneRadar's A5 PASS proving the manual-pattern scan is untouched), `cyd2usb_winamp_debug` rebuilt (`dram0_0_seg`/`_bss_end` delta confirmed 0 B — matches the reported 116604 B baseline exactly), DUT confirmed healthy post-restore (fresh uptime on `spotify-mon`, matching the reflash timestamp). DUT fetch-cycle check (`get dataq`, 5 apps) showed no stranded `tlsYieldCount` on any exit path including error paths. |
| TASK-459 | P3 | **DONE 2026-08-25** (`5225208`) | C2b — migrate `s_aeSpotifyYielded` to a transferable guard, per M-CODEQUAL's own instruction (§4, §12's C9 note): this is the *one* guard type in the codebase where move must be defined rather than deleted. `spotifyTask::TlsYieldGuard` (`spotifyTask.h`) gained a move ctor/assignment and a `none()` factory (`ok_==false`, no `tlsYield()`/`tlsTryYield()` call — safe as an idle file-static default). `audioEngine.cpp`'s `s_aeSpotifyYielded` bool became `static TlsYieldGuard s_aeTlsGuard`, acquired in `aeConnectFile()` (`TlsYieldGuard(AE_CONNECT_FILE_TLS_TRYYIELD_MS)`, moved in on success) and released via `s_aeTlsGuard = TlsYieldGuard::none()` at the same three call sites the bool was cleared at (`aeDrainEof()`, `aeConnectFile()`'s `aeEnsureAudio()`-failure rollback, `aeStopFile()`) — move-assignment's `if (ok_) tlsResume();` reproduces the old `if (flag) { tlsResume(); flag=false; }` exactly, so ordering is unchanged, not just net effect. **Corrected assumption, checked against source before touching anything:** the task board text (this row, previously) said this "touches audio teardown ordering (`T_AE_04`)" — false. `T_AE_04` (`app/tools/test_ae04_teardown.py`) exercises WebRadio's own eject-mid-CONNECTING path (`s_wrPumpRequest`/`wrTeardownPumpTask()`, driven directly by `webRadioApp.cpp`), which never touches `aeConnectFile`/`aeStopFile`/`aeTeardownFile` or the flag/guard this task migrates — those are exclusively `LocalPlayerApp`'s FILE-arm (confirmed by grep: only `localPlayerApp.cpp` calls any of the three). Verified: `run/check` 11/11 (all 6 firmware envs, `golden.sha256`, tool smoke incl. `check_app_conformance` A5/A6, app-registry + mem_layout staleness, check-docs) — the repo currently reports 11 gates end-to-end though `run/check`'s own header comment claims 12 (pre-existing header/count drift, unrelated to this task, not fixed here). **DUT**: (1) `run/ae04` run twice — once against this change, once against a `git stash`-reverted baseline of the same two files — both scored an identical `0/5 cycles clean`, "pump gone but no `wrpump: torn down (...)` line" on every cycle; A/B-confirmed pre-existing and unrelated to this change (consistent with the code-path finding above), not a regression — flagged as a new follow-up below (TASK-533), not fixed here (a live-network-dependent harness issue, not obviously a firmware defect, and out of this task's scope). (2) Since `T_AE_04` doesn't exercise the changed code, ran `run/browser-player` instead (`cyd2usb_player`, TASK-416/`T_PLR_13` playback half) — the actual DUT path that exercises `aeConnectFile()`/`aeStopFile()`: **PASS**, 200-entry directory walk in 0.3 s with playback continuous throughout, no reset. |
| TASK-533 | P3 | OPEN — new, filed 2026-08-25 | `run/ae04` (`T_AE_04`) currently fails 0/5 clean on unmodified `master` (confirmed via `git stash` A/B during TASK-459) — "pump gone but no `wrpump: torn down (...)` line" every cycle. Pre-existing, not caused by TASK-459 (that migration's code is never on `T_AE_04`'s call path — see TASK-459's row). Needs its own DUT investigation: either the dead-IP raw-TCP timeout (`10.255.255.1:1`) is now resolving/failing differently on this network (ICMP unreachable instead of a silent blackhole, changing which teardown branch fires) or there's a real regression somewhere between whenever `T_AE_04` last passed and now — not diagnosed here, out of scope for TASK-459. |
| TASK-460 | P2 | **DONE 2026-08-25** (`98c56da`) | C1 — consolidated the **four buffered fetches only** (`fetchWeather`, `fetchCrypto`, `fetchTeletext`, `fetchGeocode`) onto one shared skeleton, per `M-CODEQUAL-duplication-and-abstraction.md` §2's revised design (the streaming five and `fetchWebRadioStations` are out of scope, per the corrected row above). Added `httpFetchJsonBuffered(WiFiClientSecure&, const BufferedFetchCfg&, ParseFn)` in `dataTaskStorage.cpp` — `BufferedFetchCfg{url, rootCa, certTag, phaseSlot, logTag, userAgent}`, parse callback is a template parameter (lambda, no captures required to decay to a function pointer, but capturing lambdas work too since `ParseFn` is deduced per call site) — `-std=gnu++11`, no `std::function`, no heap allocation for the callback. It owns the cert-break substitution (`consumeCertBreak`/`wrongCaFor`), `http.useHTTP10(true)`, `begin()`/`GET()`/`certSentinel()`, buffering the body, `http.end()`, and phase-slot bookkeeping (nullable — Teletext/Geocode track no phase, same as before). Each of the four converted functions keeps its own `WiFiClientSecure tls;` and `spotifyTask::TlsYieldGuard tlsGuard;` declared locally, in that order, exactly as before — **deliberate, not the design doc's literal `{url, rootCa, certTag, phaseSlot}` illustration**: `check_app_conformance.py`'s A5 scan attributes an HTTPS session-open site to an app by the site's *enclosing function*; moving the `WiFiClientSecure` declaration into the shared skeleton would have collapsed all four sites into one generic, unattributable function and broken a currently-passing gate (see below). Both preconditions used as designed: `TlsYieldGuard` (TASK-458, `15d3c55`) replaces the manual `tlsYield`/`tlsResume` bookkeeping inside each caller; TASK-495's crypto resume-after-parse fix (`1df8b33`) is untouched because the guard's scope is still the whole calling function, so resume timing is unaffected by where the shared skeleton call sits inside it. `T_CQ_02` (named in this row's prior text) does not exist in the repo and was not authored — no test plan or design-doc section actually specifies it; used the tests that do exist instead (see Verified below). TASK-223's `openHttps()` (used only by Teletext/Geocode, always with `insecure=false`) is dead after the migration — removed. **Test-suite maintenance required by the refactor, not incidental:** `test_check_app_conformance.py`'s BP-068 mutation `case_a5_guard_removed` anchored on the literal adjacency of `TlsYieldGuard tlsGuard;` and the now-relocated `LOG_HEAP("dataTask.teletext")` inside `fetchTeletext()`; re-anchored to the still-Teletext-unique `BufferedFetchCfg{url, TELETEXT_NOS_ROOT_CA, DATA_FETCH_TELETEXT_PAGE,` initializer that now follows the guard and the (kept-in-caller) `WiFiClientSecure` declaration — same mutation intent (dropping the guard must still FAIL Teletext's A5), verified the mutation still fires. Documented, intentional (non-behavioral) harmonizations: Geocode's `http.end()` now always runs before its parse (previously after, for the 200 case only) — the body is already fully buffered by `getString()` either way, so this only moves when the TLS socket is torn down, not what gets parsed, and leaves slightly more heap headroom during the JSON parse; Geocode gains the GET-elapsed `LOG_D` and post-`http.end()` `LOG_HEAP` lines the other three already had; Teletext's GET-elapsed log line loses its `page=%u` suffix (generic now, logged before the callback — which still knows the page — runs), while its begin-failed and non-200 messages keep `page=%u` exactly as before, reconstructed in the callback. **Verified:** `run/build` compiles clean (`cyd2usb_winamp`). `run/check` 11/11 (matches TASK-459's count; the header's stale "12-gate" claim is unrelated, not fixed here). `test_check_app_conformance.py` 11/11 (including the re-anchored guard-removal mutation). `check_app_conformance.py` against the live corpus: Weather/Crypto/Teletext all A5 PASS, correctly attributed to their own function (Geocode was never a registered `APP_ORDER` app and was unattributed before this change too, like Heatmap — not a regression). **DUT: blocked this session by a rig-wide WiFi outage, A/B-confirmed unrelated to this change** — both configured SSIDs (`<home-ssid>`, `<home-ssid>`) fail to associate (`STA_DISCONNECTED reason=201`, `NO_AP_FOUND`) from the first attempt at `t=3.2s`, before WiFi comes up and therefore before any `dataTask` fetch code — changed or not — can run. Confirmed via the TASK-459 A/B pattern: `git stash`, flashed clean `a6cf610` debug and watched 40s of serial (identical failure signature/timing), `git stash pop`, reflashed this change's debug build and watched 150s more (identical again, zero associations on either build); `run/serialdbg_tests.py --tests T272` also hit the same `[SETUP-FAIL] wifi-not-connected`. No T220/T221/T272 run or manual `set geocode fetch`/`set certbreak` check was possible as a result — not fabricated as a pass. Filed as TASK-535 below. Production firmware restored to the DUT before finishing. |
| TASK-535 | P3 | **DONE 2026-08-25** | Live DUT check of TASK-460's four converted fetch paths, once the human resolved the AP's RF visibility (moved the DUT within range of `<home-ssid>`; `get wifi` confirmed `status:3` / real RSSI (-49..-52) / a real IP before any test ran). **T221 (Weather): PASS** — GET 200, heap recovers within the 5k-drop bound (`pre_maxBlk=39k post_maxBlk=39k drop=0k`), `http.end()`-before-parse ordering intact. **T272 (Teletext): PASS on retry** — first attempt SKIPped on a genuine `-120` (`CERT_VERIFY_FAILED`) from `teletekst-data.nos.nl` seen *before* any `certbreak` was armed this run; `run/check-datatask-certs` (host-side, independent of the DUT) verified that same pinned root cleanly against the live server at the same time, so this was a transient DUT-side handshake blip (fast ~280ms fail, consistent with an early handshake abort, not a real pin-rot) — re-triggering the same fetch ~45s later passed cleanly (`teletextReady=true`, Spotify's `lastPlaylistDraw` advanced throughout, no TLS contention). **Geocode manual pass: PASS** — `set geocode fetch NL 1012JS` returned a real result (`lat=52.372929 lon=4.894022`, Amsterdam Centrum), correlated by `seq` (its `new` flag is a non-consuming peek per its own TASK-320 comment, so a naive check would false-positive on a stale earlier result — this run's assertion matched the fetch's own returned `seq`, not just `new`). **Cert-break `-120` sentinel: PASS on all four** — `weather` (`GET -120`/`http -120` in the raw log, though this run's own log-scraping helper mistimed its read and reported a false FAIL — the firmware behavior is directly confirmed in the captured serial log, not inferred), `crypto` (`cryptoHttpCode==-120`), `teletext` (`teletextHttpCode==-120`), `geocode` (`errorCode==-120`) — `consumeCertBreak`/`wrongCaFor` living inside the shared `httpFetchJsonBuffered()` fires correctly per-tag for all four, the one behaviour TASK-460's static verification couldn't exercise. **T220 (Crypto): FAIL, but A/B-confirmed pre-existing, not a TASK-460 regression** — `maxBlk` after the TLS yield read 33-39k (below the test's 50k bar) on two separate attempts against this session's build, including one after a 45s settle past cold boot (ruling out a first-fetch artifact). Ran the same A/B this task's own row already used once: temporarily checked out `app/src/dataTaskStorage.cpp` at `a6cf610` (`git checkout a6cf610 -- ...`, no other file touched), rebuilt/reflashed debug, re-ran T220 with the same 45s settle — **identical failure, `maxBlk=39k` both before and after the GET** — then restored (`git checkout HEAD -- app/src/dataTaskStorage.cpp`, diff-verified clean against the committed TASK-460 state) and rebuilt. Same heap characteristic on unmodified `master`, so this is a pre-existing property of this device/session (heap fragmentation accumulated over the ~127s of uptime already elapsed with WiFi+Spotify running, or today's specific network conditions) that predates and is unrelated to `httpFetchJsonBuffered()` — not fixed here, not filed as a new follow-up since T220 already exists as a named, currently-red gate for whoever picks it up next (not this task's scope to fix a pre-existing heap-headroom gate). Production firmware restored to the DUT before finishing; the three ad hoc verification scripts used this session were not committed (workspace-only, deleted after use, same convention as `task400_401_dut_verify.py`'s siblings). |
| TASK-512 | P3 | OPEN — new, filed 2026-08-22 | C2 remainder — `HttpSession` RAII guard for `http.begin()`/`http.end()` in `dataTaskStorage.cpp`. Deliberately deferred out of TASK-458 (see its row): the pairing is already correctly balanced on every exit path today, so this is a DRY/consistency win, not a bug fix — lower urgency and higher control-flow risk (streaming parse, mirror-loop retries in `fetchOneMirror`/`fetchStockChartOnce`) than the TlsYieldGuard half was. |
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
| TASK-475 | **P2** | **PHASE 1 DONE 2026-08-16** (`b0d0202`) — phases 2–5 remain |  `run/check-docs` shipped: C5 + C1-`delta` blocking, C1-full/C2/C3 advisory, C4 unruled; counted gate 12; `T_DOC_01`–`09` registered. **Phase 2 (C2 blocking) is a one-line promotion — C2 already reads 0.** Phase 3 needs ADR-061 D8; phase 4 needs TASK-508. Baselines re-taken at `efab524`: C5 **0** (blocking day one, holds), C1 **280/599** advisory + `delta` blocking, C2 **0** via [A1]'s glob, C3 **9**, C4 **struck, order 100–200** → TASK-508. Amendments [A1] C2 resolution set (138 false failures), [A2] `delta` diff base defined, [A3] C4 baseline struck. **Then @Architect-reviewed: falsified 3 of the amendments' own numbers, found 11 further defects; 5 were handoff-blocking and are now fixed** (failure unit, exemption-vs-resolver, C3 detection rule, OQ1 contradiction, split-file carve-out), plus §5a exit criteria added. **Then @VE-reviewed, which found the killer**: C1-`delta` fails on the amendment commit itself, twice — once on an illustrative `file.h` line 46 (needs a suppression rule) and once on a **correct** citation C1's flat root list cannot resolve (10 of 282 failures are the checker's fault). E4's pinned live numbers were stale on arrival (280/599 → **282/601**), environment-dependent (**286** in a clean checkout — three citations resolve only via the untracked sibling repo) and self-contradictory (C3 is 60 occurrences / 9 names). Exit criteria rebuilt as E1–E9 around a **committed fixture corpus**; `T_DOC_01`–`09` reserved in `test_plan.md` **before** the harness, per E9.

**PHASE 2 DONE 2026-08-25** (`5e46d92`). Re-verified C2 read 0 immediately before flipping it (`0 unresolvable of 4038 id references`, live corpus) — not assumed from this row's own "already reads 0" note. `check_c2`'s `Result` now carries `blocking=True` and moved from `run()`'s advisory list to its blocking list; module docstring and the `run/check`/`check_build.sh` "documentation gate (...) clean" summary strings updated to name C2. Fixture consequence: `test_check_docs.py`'s `T_DOC_01` fixture now has **two** counted blocking checks (C5 + C2, `[2/2]` not `[1/1]`), and its advisory-only-exit-0 scenario had to start repairing C2's four deliberately-broken fixture ids too, not just C5's broken link — updated, not worked around. Regenerated `golden.txt` for the moved C2 block. Verified: `python3 app/tools/test_check_docs.py` 14/14, `./run/check` 11/11 (full firmware matrix, not just `--docs-only`, since this touches tooling `run/check` itself invokes). Phases 3–4 remain: phase 3 needs ADR-061 D8 (see TASK-467 — already landed, so phase 3 is actually unblocked, just not yet done); phase 4 needs TASK-508's migration (now landed, see TASK-508's row) and its own re-measurement before promoting. Phase 5's own definition (§5a exit criteria) has not been characterized against this state — see the follow-up filed alongside this session's report.

**PHASE 4 DONE 2026-08-25** (`579775c`), same session as phase 2. Precondition (TASK-508's migration) had just landed; re-measured C4 at 0/189 immediately before promoting (see TASK-508's row) — not assumed. Same one-line promotion shape as phase 2: `blocking=True`, moved to `run()`'s blocking list. Fixture consequence: `T_DOC_01`'s counted-blocking count is now 3 (C5, C2, C4); C4 is clean in the fixture (both its Status: headers already conformed) so it counts but never fails there. Verified: `test_check_docs.py` 14/14, `run/check` 11/11 (full firmware matrix). **Phase 3 (C3) deliberately left advisory** — unblocked (ADR-061 D8 / TASK-467 landed) but the live count is **58 occurrences across 10 unknown env names** (`cyd2usb`, `cyd2usb_spike`, `cyd2usb_base`, `cyd2usb_webradio_16k`, `cyd2usb_winamp_debug_ceefaxspike`, etc. — mostly historical ADR references to envs since renamed by D8's own `cyd2usb`→`cyd2usb_base` demotion or retired outright, e.g. TASK-531's `cyd2usb_webradio_16k`), not near zero. Forcing this to blocking would break the gate on debt nobody has cleaned up — reported, not decided, here; needs a PM/Architect call on whether to clean the historical citations, retire the check's scope to exclude *-review.md-adjacent historical ADRs, or leave phase 3 advisory indefinitely (the way §4's own C1-full precedent already argues for). **Only C1-full (phase 5) remains open**, and the spec's own §4 text says it "likely stays advisory permanently... on purpose." |
| TASK-508 | P2 | **RULINGS DONE 2026-08-23 — remaining work is a migration, not a decision** | C4 status-vocabulary: all three sub-decisions made (human rulings, see `M-DOCLIFE-check-docs-spec.md` §C4 for full detail). **(a)** dropped invented `partially landed`; closed vocabulary is now `proposed`/`accepted`/`done`/`implemented`/`resolved`/`closed`/`applied`/`retired`/`superseded`/`rejected` (`draft`/`planned` fold into `proposed`). **(b)** exact match — the `Status:` field holds only the bare word, nothing else on the line. **(c)** header-only — a truthful in-body status update elsewhere in the doc does not offset a stale header. **Real consequence of (b)**: this is BP-065's own as-built-section structure, finally enforced — almost every real header today crams commit/date/rationale inline, so the ~100–200-header migration is a reformat (extract inline detail into a proper as-built section), not a word-swap. BP-065 (`best_practices.md`) updated to match. **Remaining scope is now Developer/PM execution** (do the migration, re-measure the failure count, then promote C4 from advisory to blocking) — not an open Architect question.

**MIGRATION DONE 2026-08-25** (`6361ef3`). Migrated 189 `Status:` headers across `docs/architecture/{decisions,designs,interfaces}/` (recursive — includes `M-AQUARIUM/`, `M-MULTIAPP/`, `M-PLANERADAR/`, `M-PR-LOCATIONS/` subdirectories, which a first pass missed by globbing non-recursively) to the closed vocabulary, exact match, header-only. Inline commit/date/rationale moved to a new `As-built:` line under each; multi-line blockquote `Status:` blocks kept their continuation lines byte-identical (only the first line was rewritten) specifically so `run/check`'s C1-`delta` gate wouldn't see pre-existing citations inside them as newly-added — it did, on the first attempt, before this fix (a pre-existing broken citation inside `M-PR-LOCATIONS-location-presets.md`'s continuation text briefly tripped it). ~160 headers were mechanical (already-closed word + inline text, or `draft`/`planned`). **~28 used a term outside the ruling's explicit list** — mapped by conservative synonym judgment (documented per-file in the migration script, not re-litigated here): `shipped`→`done`, `approved`/`decided`→`accepted`, `audited`/`final`/`"reviewed + restructured"`→`done`, `scheduled`/`skeleton`/`stub`/`"design draft"`/`"sketch / proposed"`/`"POC scope(d)"`→`proposed`, `parked`(×2)→`rejected`, `"feeds ADR-010 (accepted)"`→`superseded`. Two are genuinely borderline and flagged here for Architect confirmation rather than silently accepted: `M-QUALITY-improvement-map.md`'s `map` and `NEW-APP-CHECKLIST.md`/`M-MULTIAPP/upstream-patches.md`'s `active` — both are living index/reference docs, not decisions with a real lifecycle, and were mapped to `accepted` (in force) for lack of a better closed-vocabulary fit; the closed vocabulary itself may not be the right tool for this doc *class*, which is a scope question this task didn't have standing to decide. **14 files in scope have no `Status:` field at all** (`ADR-017-api-candidates.md`, both `README.md`s, `IFC-001`–`003`, `M-MEMBUDGET`/`M-MEMPLAN`/`M-PLAYER-STATE`/`M-RECLAIM`/`M-WIFI-DIAG`, `M-MULTIAPP/{app-lifecycle,layout,preview-tooling,taskbar}.md`, `M-STOCK-POC/test-design.md`) — left untouched (presence, not vocabulary, is a different, unruled question) — **filed as follow-up TASK-534 below**. Also implemented `check_docs.py`'s `check_c4` (previously an always-skip stub) matching all three rulings exactly, and regenerated `app/tools/testdata/check_docs/golden.txt` for the one line it changes. Verified: `python3 app/tools/test_check_docs.py` 14/14, `./run/check --docs-only` clean. **Re-measured C4: 0 non-conforming of 189 Status: headers** (was "rule undefined"; TASK-475 phase 4's precondition). |
| TASK-534 | P3 | OPEN — new, filed 2026-08-25 | 14 architecture docs in C4's scope have no `Status:` field at all (list in TASK-508's row above) — not a C4 vocabulary failure (C4 checks the word, not presence) but a real gap BP-065 implies these docs shouldn't have. Needs an Architect/PM call on whether presence becomes a new rule (its own C4b, or folded into C4) before anyone adds headers to these 14 by hand. |
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
| **TASK-495** | P3 | **DONE 2026-08-22** (`1df8b33`) | `fetchCrypto` moves its `tlsResume()` to after its JSON parse, matching `fetchWeather`. Decision made (E-02, resume-AFTER); landed as TASK-458's first commit, exactly as the ordering note below required. |
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
| TASK-500 | P3 | **DONE 2026-08-23** | **Architect ruling: same-core preemption race, not cross-core.** `serialdbg` is `loopTask` (`handleSerialCommands()` runs inline from `loop()`, `main.cpp:269`) — not a separate task. IFC-002 already tabulates `loopTask` and `dataTask` both pinned to core 1 and states system-wide "there is no true parallelism between them... every race here is a preemption race." X015 was one instance of that already-settled general case, not a novel decision — updated its `description` to cite IFC-002 directly and fixed a leftover stray "Core 0" reference in the same entry that TASK-491's original fix had missed. `interaction_type`/`risk` unchanged (both were already correct). |
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
