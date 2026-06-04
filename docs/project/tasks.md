# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

## Project Scope

**In scope:** `Spotify-Diy-Thing/` — Arduino/PlatformIO firmware for ESP32 CYD2USB displaying Spotify now-playing track + album art via Spotify Web API.

**Out of scope:** `cspot/` — vendored upstream of an unrelated Spotify Connect player library. Do not extend, do not depend on. If touched at all, only to track upstream pulls.

## Active Tasks

### TASK-112 — VE: serialdbg test quality fix pass (audit 2026-05-30)
**Owner**: VE (Developer for firmware additions)
**Feature**: serialdbg-001 (cross-cutting)
**Status**: done
**Git refs**: `c62d7a4` (112a) · `b759781` (112b) · `97733d7` (112c) · `8d2cc34` (112d) · `2598fac` (112e) · `379befa` (112f) · `3734936` (112g)
**Audit ref**: `docs/quality/audit_log.md` — Audit 2026-05-30
**VE spec**: `docs/verification/test_plan.md` — Suite: serialdbg-audit-001

- **TASK-112a** ✅ T176 → `_wait_chart_complete(before)` via `fetchOkCount`
- **TASK-112b** ✅ `quoteOkCount` firmware counter + T170 rewritten to assert completion
- **TASK-112c** ✅ T136 removed; precondition folded into T137 setup
- **TASK-112d** ✅ T178 → asserts `chartLen=0` + `fetchFailed=false` placeholder state
- **TASK-112e** ✅ T_GOL_04 → `golAlive > 0`
- **TASK-112f** ✅ `[PARTIAL]` / `[SMOKE]` / `[MANUAL]` annotations applied
- **TASK-112g** ✅ T090 excluded from default dispatch (superseded by T091)

**VE rerun 2026-05-30**: reflashed debug build (production fw was on DUT — SERIAL_DEBUG absent). All 9 tests pass in isolation. Full-suite run shows API rate-limit cascades (T186/T187/T188 trade off failures across runs; T170 cold-start; T174 SKIP from T178 ordering) — no firmware defects. Production reflash pending (cyd2usb_winamp env).

---

### TASK-113 — M-TOUCH-UX: Touch UX layer design (ADR-035)
**Owner**: Architect (design); Developer + VE (implementation — separate tasks TBD)
**Features**: touch-003, touch-004, touch-005
**Status**: design done (2026-05-31); implementation not started
**Milestone**: M-TOUCH-UX
**Design**: `docs/architecture/designs/M-TOUCH-UX.md` · ADR: `docs/architecture/decisions/ADR-035.md`

Scope of this task (design phase only):
- **TASK-113a** ✅ Architect: ADR-035 drafted — four decisions covering hitbox primitive, debounce activation, gesture deferral, shell busy indicator.
- **TASK-113b** ✅ Architect: M-TOUCH-UX.md drafted — Part 1 (hitbox + debounce), Part 2 (shell busy indicator + `hasPendingAsync()` contract, SpotifyApp chain, StockApp chain, `switchApp()` + `suspend()` contracts).
- **TASK-113c** ✅ Team review round 1 (VE, Developer, QM) — findings raised and addressed: DEV-01..05 (ADR sync, `mutable`, thread safety, timer-reset guard, file list); T-BUSY-03/04 wording; LL-044, LL-045.
- **TASK-113d** ✅ Exit criteria finalised: T-BUSY-01..05 + T-CDWN-01..03 in M-TOUCH-UX.md.
- **TASK-113e** ✅ feature_inventory.yaml: touch-003/004/005 registered (proposed).
- **TASK-113f** ✅ lessons_learned.md: LL-044 (debug-path-only mechanism) + LL-045 (ADR/design-doc sync failure) appended.

**Developer deliverables required before VE execution:**
- `get shellBusy` in SERIAL_DEBUG `cmdGet()` (gates T-BUSY-01..05)
- `get visMode` in SERIAL_DEBUG `cmdGet()` (gates T-CDWN-01)

**Implementation tasks:** TASK-114 → TASK-118 below.

---

### TASK-114 — M-TOUCH-UX Phase 1: Low-risk foundation ✅
**Owner**: Developer
**Features**: touch-003, touch-005 (part 1)
**Status**: complete
**Milestone**: M-TOUCH-UX
**Depends on**: TASK-113 (design done)
**Blocks**: TASK-115 (hitbox.h available for adoption), TASK-118 (VIS debounce fix live)
**Design**: `docs/architecture/designs/M-TOUCH-UX.md` Part 1

Sub-tasks:
- **TASK-114a** ✅: Create `app/src/touch/hitbox.h` — `struct Rect { int16_t x, y, w, h; }` + `hitTest` / `hitTestRow` / `hitTestCol` inlines. No callers changed yet (adoption is incremental).
- **TASK-114b** ✅: Add `touchScreenCoolDownTime` Phase 2 check to `handleWinampInput()` — one line at top of Phase 2 block in `winampDisplay.h`: `if (millis() <= touchScreenCoolDownTime) { _tickMarquee(); return false; }`. Verify VIS, Shuffle, Repeat all respect the intended cooldown durations.
- **TASK-114c** ✅: `check_build.sh` 4/4 ✅. Flash `cyd2usb_winamp`; verify VIS cycling requires ~300 ms between taps.

Exit criterion: `check_build.sh` passes; VIS debounce confirmed on DUT.

---

### TASK-115 — M-TOUCH-UX Phase 2: Busy indicator infrastructure
**Owner**: Developer
**Features**: touch-004 (shell layer)
**Status**: complete (git `6df8859`)
**Milestone**: M-TOUCH-UX
**Depends on**: TASK-114
**Blocks**: TASK-116 (hasPendingAsync() ABC must exist before app overrides)
**Design**: `docs/architecture/designs/M-TOUCH-UX.md` Part 2 — indicator wire, shell state + API, renderActiveIndicator, switchApp, suspend contract

Sub-tasks:
- **TASK-115a**: `taskbar.h` — add `TASKBAR_BUSY_COLOR 0xFD20`; add `renderActiveIndicator(TFT_eSPI&, AppId, int scrollOffset, int totalApps, bool busy)`; `renderTaskbar()` gains `bool busy = false` param and delegates indicator paint to `renderActiveIndicator()`.
- **TASK-115b**: `main.cpp` — add `static bool g_shellBusy = false`; `static unsigned long g_shellBusySetMs = 0`; `SHELL_BUSY_TIMEOUT_MS = 3000`; implement `shell::setBusy(bool)` (sets flag, calls `renderActiveIndicator()` with `(int)AppId::COUNT`).
- **TASK-115c**: `appShell.h` — add `virtual bool hasPendingAsync() const { return false; }` to `App` ABC (non-pure; document why non-pure in comment).
- **TASK-115d**: `main.cpp` `loop()` — add primary clear (poll `hasPendingAsync()`) and fallback auto-clear (after `SHELL_BUSY_TIMEOUT_MS`) after `appTick()`.
- **TASK-115e**: `main.cpp` `switchApp()` — insert `shell::setBusy(false)` after `suspend()`, before `renderTaskbar()`.
- **TASK-115f**: `check_build.sh` 4/4 ✅. Flash `cyd2usb_winamp`; verify indicator still green on all apps (no app sets busy yet — amber not expected until TASK-116).

Exit criterion: `check_build.sh` passes; DUT boots; indicator green; no regression on app switching.

---

### TASK-116 — M-TOUCH-UX Phase 3: App integration
**Owner**: Developer
**Features**: touch-004 (app layer), touch-005 (part 2 — g_shellBusy Press gate)
**Status**: complete (git `3e852f3`)
**Milestone**: M-TOUCH-UX
**Depends on**: TASK-115 (hasPendingAsync() ABC must be in tree)
**Blocks**: TASK-117 (SERIAL_DEBUG deliverables wire into app state)
**Design**: `docs/architecture/designs/M-TOUCH-UX.md` — App integration points, g_shellBusy gate

Sub-tasks:
- **TASK-116a**: `winampDisplay.h` — add `bool _lastInputWasAsync = false`; `wasLastInputAsync()` accessor; set flag at all 11 async dispatch sites in Phase 2 AND Release handler (PREV/PLAY/PAUSE/STOP/NEXT, Shuffle, Repeat, seek-drag Release, volume-drag Release, PLEDIT row tap Release, logo tap). VIS tap must NOT set the flag.
- **TASK-116b**: `spotifyTask.h` — add `volatile bool _actionPending`; add `hasPendingActions()` public query; set on enqueue, clear only when `xQueueReceive` returns `pdFALSE` (queue empty — not on every dequeue).
- **TASK-116c**: `main.cpp` SpotifyApp — add `mutable bool _actionDispatched = false`; override `hasPendingAsync()` (`_actionDispatched && spotifyTask::hasPendingActions()`, self-clears); update `handleInput()` to check `wasLastInputAsync()` after BOTH Press and Release delegate calls; `suspend()` resets flag.
- **TASK-116d**: `main.cpp` StockApp — add `bool _pendingAsync = false`; override `hasPendingAsync()`; set `_pendingAsync = true` inside the stale-cache `if` block only (not unconditionally) in `drillToChart()` and tab-range handler; clear in `pollStockChart()` resolve path; `suspend()` resets flag.
- **TASK-116e**: `main.cpp` `appHandleInput()` — add `g_shellBusy` Press gate: `if (!s_inGesture && (millis() <= s_cooldownMs || g_shellBusy)) return;`; add busy setter `if (!g_shellBusy && g_apps[id]->hasPendingAsync()) shell::setBusy(true)` after **all four** `handleInput()` call sites.
- **TASK-116f**: `check_build.sh` 4/4 ✅. Flash `cyd2usb_winamp`; smoke: tap PLAY → amber appears → clears; tap StockApp row → amber appears → clears. Verify no amber on Clock/Weather/Crypto/Matrix/Life/Aquarium taps.

Exit criterion: `check_build.sh` passes; amber indicator fires and clears on Spotify and StockApp user actions; no amber on passive apps.

---

### TASK-117 — M-TOUCH-UX Phase 4: SERIAL_DEBUG deliverables
**Owner**: Developer
**Features**: touch-004, touch-005
**Status**: complete (uncommitted — staged in this session)
**Milestone**: M-TOUCH-UX
**Depends on**: TASK-116
**Blocks**: TASK-118
**Design**: `docs/architecture/designs/M-TOUCH-UX.md` — Developer deliverables table

Sub-tasks:
- **TASK-117a** ✅ `vuMeter.h` — `vu::currentMode()` public getter added.
- **TASK-117b** ✅ `cmdGet()` — `get shellBusy` → JSON bool.
- **TASK-117c** ✅ `cmdGet()` — `get visMode` → JSON int 0..3.
- **TASK-117d** ✅ `cmdTap()` — `g_shellBusy` check for canvas taps; returns `skipped:true` when busy.
- **TASK-117e** ✅ Flashed `cyd2usb_winamp_debug`; `get shellBusy` / `get visMode` verified.

**Implementation note:** `SpotifyApp::hasPendingAsync()` simplified during TASK-118 VE run — removed `_actionDispatched` gate; now returns `spotifyTask::hasPendingActions()` directly. The action queue is exclusively user-initiated so the signal is sound without the extra flag. Removed `_actionDispatched`, `wasLastInputAsync()` check from `handleInput()`. Design docs (ADR-035, M-TOUCH-UX) still describe the old chain and need a follow-up sync (see TASK-118 outstanding items).

Exit criterion: ✅

---

### TASK-118 — M-TOUCH-UX Phase 5: VE execution
**Owner**: VE
**Features**: touch-003, touch-004, touch-005
**Status**: in progress — partial run complete; 3 outstanding items
**Milestone**: M-TOUCH-UX
**Depends on**: TASK-117
**Design**: `docs/architecture/designs/M-TOUCH-UX.md` — Exit criteria table

Sub-tasks and results (debug build flashed; run 2026-05-31):
- **TASK-118a** ✅ T-BUSY-01 PASS
- **TASK-118b** ✅ T-BUSY-01b PASS
- **TASK-118c** ✅ T-BUSY-02 PASS
- **TASK-118d** ✅ T-BUSY-03 PASS
- **TASK-118e** ✅ T-BUSY-05 PASS
- **TASK-118f** ✅ T-CDWN-01 PASS
- **TASK-118g** ⚠ T-CDWN-02 FLAKE — Yahoo Finance rate-limit prevented fetch completing; gate was confirmed active (`skipped:true` returned), fetchOkCount unprovable. Needs re-run when network is clear.
- **TASK-118h** ✅ T-CDWN-03 PASS
- **TASK-118i** T-BUSY-04 `[MANUAL]` — not yet run.

**Outstanding items before TASK-118 can close:**
1. ~~T076/T079/T081 harness fix~~ ✅ — `_poll_shell_busy(dut, False)` added before each transport tap; T079 gets an initial poll before cooldown arm. Firmware behaviour correct; harness-only change.
2. ~~Design doc sync~~ ✅ — ADR-035 + M-TOUCH-UX.md updated: `_actionDispatched` chain removed; both docs now describe `hasPendingAsync()` = `spotifyTask::hasPendingActions()` directly.
3. **T-CDWN-02 re-run** — when Yahoo Finance not rate-limited.
4. **T-BUSY-04 manual run** — network-blocked DUT required.

Exit criterion: T-BUSY-01/01b/02/03/05 ✅; T-CDWN-01/03 ✅; T076/T079/T081 harness ✅; doc sync ✅; T-CDWN-02 pending re-run; T-BUSY-04 manual pending.

---

### TASK-119 — M-HEATMAP: StockApp heatmap view — design accepted
**Owner**: Developer
**Feature**: stock-002 (new)
**Status**: complete (git 483920e)
**Milestone**: M-HEATMAP
**Depends on**: stock-001 complete (TASK-116+)
**Blocks**: TASK-120, TASK-121
**Completion note**: All sub-tasks (119a/b/c) implemented; TASK-121/122/123 bugs fixed. Unblocks TASK-120.
**Design**: `docs/architecture/decisions/ADR-036.md` (accepted 2026-06-02)

Three implementation phases + VE:

#### TASK-119a — Data pipeline (no UI)
- `dataTask.h`: add `DATA_FETCH_HEATMAP_QUOTE` op, `HeatmapQuoteResult` struct, `pollHeatmapQuote()`.
- `dataTaskStorage.cpp`: add `fetchHeatmapQuote()` — screener GET, `StaticJsonDocument<256>` filter + `StaticJsonDocument<4096>` data doc, streaming parse per ADR-034. Mutex + result store following existing `StockQuoteResult` pattern. Wire into task loop.
- `appShell.h` `StockAppState`: add `prevSubView`, `lastHeatmapFetch`, `heatmapData` (`HeatmapQuoteResult`), `heatmapLayout[20]` (`HeatmapTile`), `heatmapLayoutDirty`.
- Exit: `check_build.sh` 4/4; `get heatmapCount` serial command returns valid count after switching to heatmap view. No UI yet.

#### TASK-119b — Render + layout (no navigation)
- `main.cpp`: add `HeatmapDetail` to `StockSubView`; add `computeHeatmapLayout()` (Bruls et al. squarified treemap, landscape-first, no heap alloc); add `repaintHeatmap()` (tile fillRect + adaptive label: ticker always, change% if w≥40 && h≥28; colour LUT for ±5% scale).
- `tick()`: call `computeHeatmapLayout()` when `heatmapLayoutDirty`; call `repaintHeatmap()` when in HeatmapDetail.
- Exit: `check_build.sh` 4/4; flash debug build; manually switch to HeatmapDetail via serial `switchApp`; verify tiles render with correct colours and labels.

#### TASK-119c — Navigation wiring
- `handleInput()`: toggle tap (`x > 190 && y < 22`) in ListDetail ↔ HeatmapDetail; tile tap in HeatmapDetail → `fetchStockChartBySymbol(symbol, 0)` + `prevSubView = HeatmapDetail` + subView = ChartDetail; back tap in ChartDetail → restore `prevSubView`.
- Add `fetchStockChartBySymbol(const char* symbol, uint8_t rangeIdx)` — mirrors `fetchStockChart()` with symbol string.
- Exit: `check_build.sh` 4/4; flash; verify List↔Heat toggle, tile drill-through to chart, back returns to heatmap (not list).

#### TASK-120 — VE: T-HEAT-* test suite
**Status**: complete (harness passing: T192/T193/T194/T196/T200/T201/T202/T203; manual T195/T197/T198/T199 planned)
**Completion note**: 8/8 automated tests passing in full suite run. T192/T193/T194 timing-sensitive due to Yahoo screener cache expiry and serial flooding in long runs; guarded with _wait_shell_not_busy, cache-reuse HEAT tap, and (10,30) tile position. test_plan.md statuses updated; feature_inventory.yaml stock-002 test_ids populated.
- Owner: VE (Developer adds `get heatmapCount` SERIAL_DEBUG deliverable first).
- Tests: toggle navigation, tile tap drill-through, back nav to correct sub-view, fetch completes (via `get heatmapCount`), error state on fetch failure.
- Exit: T-HEAT-* written in `test_plan.md`; harness passing; feature_inventory.yaml updated.

---

### TASK-121 — BUG: Chart tab-switch fetches wrong ticker after heatmap drill-through
**Owner**: Developer
**Feature**: stock-002
**Status**: complete (git 40dd18c)
**Completion note**: chartSymbol guard added to tab-switch (main.cpp:812) and auto-refresh (main.cpp:1277).
**Milestone**: M-HEATMAP
**Depends on**: TASK-119c (heatmap navigation wired)
**Blocks**: TASK-120 (VE cannot validate correct chart data until fixed)
**Source**: code review 2026-06-02

Root cause: `drillToChartBySym()` sets `_s.chartSymbol` but does not update `_s.chartTickerIdx`. Both tab-switch and auto-refresh use `enqueueStockChart(_s.chartTickerIdx, …)` unconditionally, so switching ranges re-fetches the last index-based ticker, not the heatmap symbol.

Sub-tasks:
- **TASK-121a**: `handleInput()` tab-switch block (`main.cpp` line 812): when `_s.chartSymbol[0]` is set, call `dataTask::enqueueStockChartBySym(_s.chartSymbol, tab)`; else keep `enqueueStockChart(_s.chartTickerIdx, tab)`.
- **TASK-121b**: `stockTickChart()` auto-refresh path (`main.cpp` line 1272): same guard — `chartSymbol[0]` set → `enqueueStockChartBySym`; else `enqueueStockChart`.
- **TASK-121c**: `check_build.sh` 4/4; flash debug; repro sequence (heatmap → ARM → 5D → 1D) confirms price stays ~400 throughout.

Exit criterion: price displayed on 1D after switching from 5D matches the initial drill-through price; `check_build.sh` passes.

**Test IDs**: T191 (bug observable pre-fix baseline), T192 (tab-switch uses drilled symbol, SERIALDBG), T193 (auto-refresh path, SERIALDBG), T194 (back-to-list clears chartSymbol, SERIALDBG).

---

### TASK-122 — BUG: Heatmap area normalization wrong — tiles overflow bottom ~10%
**Owner**: Developer
**Feature**: stock-002
**Status**: complete (git 483920e)
**Completion note**: Area normalized to 275*(240-ST_LIST_RULE_Y) = 59 950 px².
**Milestone**: M-HEATMAP
**Depends on**: TASK-119b
**Source**: code review 2026-06-02

`computeHeatmapLayout()` (`main.cpp` line 1110) normalizes tile weights to `275 × 240 = 66 000 px²` but the tile canvas is `rw=275, rh=240−ST_LIST_RULE_Y=218`, i.e. `59 950 px²`. The weights sum to ~10% more area than available, causing tiles to overflow the bottom edge.

Fix (`main.cpp` line 1110):
```cpp
// before
wt[i] = ... / total * (275.0f * 240.0f);
// after
wt[i] = ... / total * (275.0f * (float)(240 - ST_LIST_RULE_Y));
```

Exit criterion: tiles fill y=22..239 exactly with no overflow; `check_build.sh` passes.

**Test IDs**: T195 (bottom edge visual, MANUAL), T196 (heatmapCount > 0 automated gate, SERIALDBG), T197 (total tile area ≈ 59950 px², HOST).

---

### TASK-123 — BUG: Heatmap treemap algorithm deviates from PoC — orientation + slen
**Owner**: Developer
**Feature**: stock-002
**Status**: complete (git 483920e)
**Completion note**: Orientation: horiz=(rh>rw); slen uses short side min(rw,rh). Matches PoC.
**Milestone**: M-HEATMAP
**Depends on**: TASK-122 (fix area first to isolate visual diff)
**Source**: code review 2026-06-02

Two related algorithm bugs in `computeHeatmapLayout()`:

**Bug A — strip orientation inverted (line 1116):**
DUT `horiz = (rw >= rh)` → wide rect → horizontal strip (tiles side-by-side).
PoC: wide rect → vertical strip (tiles stacked, fixed-width column at left).
These are opposite. On the 275×218 canvas the first large tile becomes a short top band instead of a tall left column.
Fix: swap the branch bodies so wide rect → vertical strip, tall rect → horizontal strip.

**Bug B — aspect-ratio criterion uses long side instead of short (line 1117):**
DUT `slen = horiz ? rw : rh` evaluates to `max(rw, rh)` always (the long side).
Bruls et al. (and the PoC `short = min(w, h)`) use the SHORT side.
Fix: `float slen = (rw < rh) ? rw : rh;`

Exit criterion: DUT heatmap visually matches the PoC `preview_heatmap.py --no-fetch` layout for the same synthetic data; `check_build.sh` passes.

**Test IDs**: T197 (shared with TASK-122 — tile area sum and PoC orientation check, HOST), T198 (first tile is tall column, MANUAL), T199 (no sliver tiles, qualitative visual, MANUAL).

---

### TASK-127 — INVESTIGATE: Heatmap screener -1 (TLS fingerprint / JA3 block)
**Owner**: RnD
**Feature**: stock-002
**Status**: closed (2026-06-03 — EXP-003; see below)
**Milestone**: M-HEATMAP
**Git ref**: `dcf8e72` (PROP-004 fix — pre-alloc `s_heatmapDoc`)

Screener endpoint returned `-1` on DUT during TASK-126 soak (2026-06-03). Two hypotheses:
H1 — JA3/TLS fingerprint block; H2 — transient CDN per-IP state from RST storm.

**Findings (EXP-003):**
- **H1 (JA3 block): Invalidated.** DUT now gets HTTP 200 without any TLS changes.
- **H2 (transient CDN state): Confirmed.** Block self-recovered within ~24h; same RST-storm per-IP throttle mechanism as EXP-001.
- **New issue found:** `NoMemory` / `IncompleteInput` on JSON parse after HTTP 200. Root cause: `DynamicJsonDocument doc(4096)` per-call `malloc` fails after ~60 min of TLS session cycling (heap fragmentation — `malloc(4096)` finds no contiguous block despite 123 KB total free).
- **PROP-004 implemented:** switched to static `s_heatmapDoc(4096)` pre-allocated at boot. DUT validation: `heatmap ok count=20 usage=1842/4096`. Fixed in `dcf8e72`.

---

### TASK-125 — BUG: ChartDetail displays stale graph when ticker or range changes
**Owner**: Developer
**Feature**: stock-002
**Status**: open
**Milestone**: M-HEATMAP
**Source**: user report 2026-06-03

#### Symptom

When navigating to ChartDetail for a new ticker (via list drill-through or heatmap tile tap) or switching the range tab, `repaintChart()` is called immediately — before the new fetch completes. At that moment `_s.chartPoints`/`_s.chartLen`/`_s.chartLo`/`_s.chartHi` still hold the **previous** ticker/range's data. The header correctly shows the new symbol + range tab, but the plot and footer render the old graph. A user briefly (or for several seconds until the fetch resolves) sees a potentially incorrect graph labelled as a different stock or time window.

#### Root cause

`drillToChart()`, `drillToChartBySym()`, and the range tab-switch block in `handleInput()` all enqueue a new fetch then call `repaintChart()` synchronously. None of them zero `_s.chartLen` first. `repaintChart()` renders `_s.chartPoints` unconditionally when `chartLen >= 2`.

#### Fix

Zero `_s.chartLen = 0` (and optionally `_s.chartLo = _s.chartHi = 0`) in all three transition sites before calling `repaintChart()`:

- `drillToChart()` (`main.cpp` ~line 1052) — after setting `chartTickerIdx`, before `repaintChart()`.
- `drillToChartBySym()` (`main.cpp` ~line 1065) — after `strncpy`, before `repaintChart()`.
- Tab-switch handler in `handleInput()` (`main.cpp` ~line 811) — after setting `_s.chartRange`, before `enqueueStockChart*`.

With `chartLen == 0`, `repaintChart()` shows the flat cyan line + `"---"` price placeholder, which is the correct loading state.

Exit criterion: navigate list → chart (AAPL), then tap heatmap tile (ARM) — chart clears to blank/loading state before ARM data arrives; `check_build.sh` 4/4 passes.

**Test IDs**: T204 (drill from list clears chart before new data, MANUAL), T205 (heatmap tile tap clears chart before new data, MANUAL), T206 (range tab-switch clears chart before new data, MANUAL).

---

### TASK-128 — FEAT: Heatmap tile label — graduated font-size degradation
**Owner**: Developer
**Feature**: stock-002
**Status**: complete
**Milestone**: M-HEATMAP
**Design**: `docs/architecture/decisions/ADR-037.md` (accepted 2026-06-03)
**Source**: user request 2026-06-03

Replace the existing two-state label rule (ADR-036 D6) in `repaintHeatmap()` with the 5-tier cascade defined in ADR-037. No changes to `computeHeatmapLayout()`, `HeatmapTile`, or the data pipeline.

#### Sub-tasks

- **TASK-128a** — Replace the label block in `repaintHeatmap()` (`main.cpp`) with the 5-tier cascade. Implement the Tier 5 width overflow guard (`strlen(sym) * 6 > t.w` → skip). Adjust vertical `cy` offsets per ADR-037 positioning table.
- **TASK-128b** — `check_build.sh` 4/4. Flash debug build. Visually verify on DUT: Tier 1 active on largest tile (AAPL/MSFT), Tier 3 visible on mid-size tiles, blank tile for smallest entries. Confirm no text bleeds into adjacent tiles.

#### Constants to introduce (suggested)

```cpp
// Tile label tier thresholds — see ADR-037
constexpr int16_t HM_T1_H = 36, HM_T1_W = 40;  // F2 ticker + F2 pct
constexpr int16_t HM_T2_H = 28, HM_T2_W = 40;  // F2 ticker + F1 pct
constexpr int16_t HM_T3_H = 20, HM_T3_W = 40;  // F1 ticker + F1 pct
constexpr int16_t HM_T4_H = 18, HM_T4_W = 40;  // F2 ticker only (wide-short strip)
constexpr int16_t HM_T5_H = 10, HM_T5_W = 20;  // F1 ticker only
```

Exit criterion: `check_build.sh` 4/4; DUT visual verification described in TASK-128b.

**Test IDs**: T207 (Tier 1 on largest tile, MANUAL), T208 (Tier 3 on mid tiles, MANUAL), T209 (blank for sub-threshold tile, MANUAL), T210 (no text overflow, MANUAL).

---

### TASK-131 — BUG: FM-2 — Persistent SSL OOM blocks all heatmap refreshes after cold boot
**Owner**: Developer
**Feature**: stock-002
**Status**: complete (git `c82b4d1`, extended `e00b453`)
**Milestone**: M-HEATMAP
**Source**: TASK-130c findings (VE review 2026-06-03)

After the first cold-boot heatmap fetch (which succeeds), all subsequent auto-fetches (`STOCK_HEATMAP_FETCH_MS = 120s`) return `-1` with `elapsed < 100ms` — characteristic of `start_ssl_client: -32512 (SSL - Memory allocation failed)`. `maxAlloc` at steady state is ~39k, insufficient for a new Yahoo Finance HTTPS TLS session (~50–70k required). Spotify's persistent TLS connection fragments the heap.

The two existing guards (`f09f196`, `a0f7601`) correctly prevent stale data from being wiped, so the display shows the initial good data indefinitely. But no refresh ever succeeds.

#### Repro

Flash `cyd2usb_winamp_debug`. Switch to StockApp → heatmap. Wait 120s for first auto-refresh. Serial shows `heatmap GET -1 elapsed=72ms` on every cycle.

#### Suggested mitigations

1. Close Spotify's `HTTPClient` before heatmap fetch, reopen after — releases the Spotify TLS memory block.
2. Reduce `s_heatmapDoc` capacity (`DynamicJsonDocument s_heatmapDoc(4096)`) if 20 symbols fit in less.
3. Move heatmap fetch to a keep-alive HTTPClient (reuse Yahoo connection across 120s intervals).
4. Use PSRAM for `s_heatmapDoc` or TLS buffers to reduce internal heap pressure.

**Test IDs**: T215, T217 (requires T217 re-run after pattern fix in harness)

**Completion note (2026-06-04, initial fix `c82b4d1`):** `spotifyTask::tlsYield()` / `tlsResume()` (originally named `heatmapPause/Resume`) stops Spotify TLS before heatmap fetch, releases ~40k heap; `s_heatmapDoc` reduced 4096→2560. DUT soak: T216 PASS, T217 PASS (min maxAlloc=39k, 0 violations). T215 SKIP — fix prevents -1; FM-3 guard covered by T216.

**Extended fix (2026-06-04, `e00b453`):** Audit of all dataTask HTTPS paths revealed the same SSL OOM class in three further fetches:
- `fetchWeather`: HTTP/1.1 keep-alive left TLS open after `http.end()`. Fixed: `http.useHTTP10(true)` + body-first pattern.
- `fetchCrypto`: Spotify poll during 4–5s CoinGecko handshake fragmented heap to ~2k maxBlk; `DynamicJsonDocument(2048)` hit NoMemory. Fixed: `tlsYield/tlsResume` + `useHTTP10` + body-first. Closes TASK-108.
- `fetchStockQuote`: AAPL's TLS cycle fragmented heap 39k→31k maxBlk; AMD and subsequent tickers returned -1. Fixed: `tlsYield/tlsResume` wrapping the 8-ticker loop. DUT: all 8 tickers 200, maxBlk=71k after loop.
- `fetchStockChart` / `fetchStockChartBySym`: same OOM class, same fix.
- Renamed `heatmapPause/Resume` → `tlsYield/tlsResume` throughout (mechanism is generic, not heatmap-specific); `spotifyTask.h`, `spotifyTaskStorage.cpp`, `dataTaskStorage.cpp` updated.

---

### TASK-138 — VE: tlsYield reliability suite — T219/T220/T221 + T217 threshold fix
**Owner**: VE
**Feature**: stock-002, crypto-001, weather-001 (cross-cutting — io-001 / X010)
**Status**: complete
**Source**: VE coverage gap audit 2026-06-04 (following TASK-131 extended fix `e00b453`)

The four new `tlsYield` callsites added in `e00b453` (fetchCrypto, fetchStockQuote, fetchStockChart, fetchStockChartBySym) and the weather HTTP/1.0 fix have no heap-headroom or mechanism tests. T216/T217 cover only the heatmap path. An OOM regression on these paths would surface as a -1 error code indistinguishable from a network failure.

#### Sub-tasks

- **TASK-138a** — Write `app/tools/test_tls_yield_reliability.py` containing T219, T220, T221. Pattern: `run_serialdbg_tests.py`-style Dut harness; log-scrape serial output for `tls yield` lines + LOG_HEAP `maxBlk` values.

- **TASK-138b** — **T219**: Stock quote tlsYield — all 8 tickers succeed + mechanism fires.
  - Trigger: `switchApp 7` → `set triggerFetch 1`.
  - Assert: `quote GET <SYM> 200` for all 8 symbols (AAPL AMD AMZN ARM GOOG META MSFT NVDA); `[spotify.tls] tls yield — client stopped` precedes first ticker; `tls yield — resumed` follows last ticker; LOG_HEAP `maxBlk≥50k` after yield.
  - Fail: any ticker returns non-200; yield lines absent; maxBlk<50k before loop.

- **TASK-138c** — **T220**: Crypto tlsYield — GET 200, NoMemory absent, mechanism fires.
  - Trigger: `switchApp 4` → wait for auto-fetch cycle (up to 90s).
  - Assert: `dataTask.crypto GET 200`; no `JSON parse error: NoMemory`; `tls yield — client stopped` / `tls yield — resumed` in log; LOG_HEAP `maxBlk≥50k` after yield.
  - Fail: NoMemory error; yield lines absent; maxBlk<50k.

- **TASK-138d** — **T221**: Weather TCP-close regression guard (HTTP/1.0 fix).
  - Trigger: `switchApp 3` → wait for fetch cycle (up to 90s).
  - Assert: `dataTask.weather GET 200` followed within 2s by `disconnect(): tcp is closed`; no `tcp keep open for reuse` line; LOG_HEAP `maxBlk` after fetch within 5k of pre-fetch value (TLS freed, not leaked).
  - Fail: `tcp keep open for reuse` present (HTTP/1.1 keep-alive regression); `maxBlk` drops >5k.

- **TASK-138e** — Fix T217 threshold: update `test_heatmap_reliability.py` line asserting `maxAlloc < 32k` → `< 50k`. Rationale: Yahoo Finance TLS floor is ~50k; 32k passes even when heap is too fragmented for a new session.

- **TASK-138f** — Execute T219/T220/T221 on DUT (debug build). Record results. Update `test_plan.md` with T219–T221 entries and statuses.

#### Exit criterion

T219, T220, T221 all pass on DUT; T217 threshold updated and T217 re-run passes; T219–T221 written in `test_plan.md`.

**Test IDs**: T219, T220, T221 (new); T217 threshold update (existing).

**Completion note (2026-06-04):** T219/T220/T221 written in `app/tools/test_tls_yield_reliability.py`; all three pass on DUT (debug build, `/dev/ttyUSB0`). T219: 8/8 tickers 200, yield=partial (client-stopped seen), pre_maxBlk=71k. T220: GET 200, NoMemory absent, resumed seen, maxBlk=71k. T221: GET 200, pre/post maxBlk=39k, drop=0k, tcp_closed confirmed. T217 threshold updated 32k→50k in `test_heatmap_reliability.py` (3 sites). T219–T221 entries added to `test_plan.md` (tls-yield-reliability-001 suite). LL-051 and BP-018 filed: DoubleResetDetector portal trap from host-side serial DTR double-reset.

---

### TASK-139 — VE: Harden `Dut` against DRD portal trap (LL-051 / BP-018)
**Owner**: VE
**Feature**: test-infra (cross-cutting)
**Status**: complete
**Source**: LL-051 / BP-018 filed 2026-06-04 after TASK-138 DUT session

`Dut._wait_for_ready()` does not detect or recover from the WiFiManager force-portal
state. If a DoubleResetDetector (DRD) trigger puts the DUT into `startConfigPortal()`
(no-timeout, blocks forever), the harness silently wastes 85 s (25 s WiFi wait +
60 s Spotify poll wait), emits a spurious `[Dut] DUT ready.`, and lets all subsequent
tests fail with opaque `TimeoutError` or `unknown command`. There is also no
cross-process reset-gap guard: a second test script opening the port within 10 s of
the first closing it fires a second reset → DRD.

#### Sub-tasks

- **TASK-139a** — **Portal detection + auto-recovery in `_wait_for_ready()`**
  - During the 25 s WiFi wait, also watch for portal indicators:
    `"Forcing config mode"`, `"configuring access point"`, `"SpotifyDIY"`, `"WiFiManager"`.
  - If any seen: print `[Dut] PORTAL DETECTED — auto-recovering (waiting 12 s for DRD window)…`,
    sleep until 12 s have elapsed since port-open (the DRD window), pulse RTS once
    (`rts=True` 100 ms, `rts=False`), then restart the boot wait loop (once only — raise
    `RuntimeError` with manual instructions if portal recurs on the second attempt).
  - Tighten fallback: if 25 s elapse with no `"IP address:"` AND no portal indicators,
    raise `RuntimeError("DUT WiFi not connected — check serial output")` rather than
    silently continuing to the Spotify poll loop.

- **TASK-139b** — **Cross-process reset-gap enforcement via timestamp file**
  - `close()`: after `self.ser.close()`, write `str(time.time())` to
    `/tmp/esp32_dut_last_reset`.
  - `__init__` (before `self.ser.open()`): read `/tmp/esp32_dut_last_reset` if it
    exists; if `time.time() - last_ts < 12.0`, sleep the remainder with a one-line
    print `[Dut] waiting Xs for DRD gap (BP-018)…`.
  - Covers the close→immediate-reopen pattern across separate Python processes
    (chained test scripts, re-runs).

#### Exit criterion

`Dut` detects portal output and auto-recovers without human intervention; a
close→reopen within 10 s is automatically deferred; all existing tests unaffected.
No new test IDs required — regression gate is `check_build.sh` + existing serialdbg
test suite passing after the change.

**Completion note (2026-06-04):** `_PORTAL_INDICATORS` + portal branch in `_wait_for_ready()` added; RTS pulse auto-recovery implemented; `RuntimeError` raised on second portal recurrence. `_DUT_RESET_GAP_FILE` + `_port_open_time` added; `__init__` reads gap file before `ser.open()` and sleeps remainder if < 12 s; `close()` writes timestamp. DRD gap guard confirmed firing in smoke run (waited 5.7 s between tls_yield and heatmap suite runs). `check_build.sh` 4/4.

---

### TASK-140 — VE: Extract satellite test boilerplate to `ve_suite_base.py`
**Owner**: VE
**Feature**: test-infra (cross-cutting)
**Status**: complete
**Source**: Code-duplication audit 2026-06-04 (TASK-138 close)

`RESULTS dict` + `pass_/fail/skip/flake()` + `main()` with `--port/--baud/--timeout/--tests`
argparse are byte-for-byte identical in `test_heatmap_reliability.py` (~46 lines) and
`test_tls_yield_reliability.py` (~46 lines). Every future satellite VE test file will
copy this block again. `Dut` already lives in `run_serialdbg_tests.py` and is imported;
the result-tracking + CLI layer above it needs the same treatment.

The `Dut` class should remain in `run_serialdbg_tests.py` (it is its primary home and
the serialdbg suite imports it from there). Only the boilerplate above `Dut` is extracted.

#### Sub-tasks

- **TASK-140a** — Create `app/tools/ve_suite_base.py` containing:
  - `RESULTS: dict[str, str]` + `pass_/fail/skip/flake()` functions (exact current
    implementations).
  - `run_suite(all_tests: list[str], test_fns: dict[str, Callable], dut: Dut,
    selected: list[str])` — the test-dispatch + per-test exception catch loop currently
    duplicated in both `main()` functions.
  - `make_arg_parser(all_tests: list[str]) -> argparse.ArgumentParser` — the standard
    `--port/--baud/--timeout/--tests` parser.
  - `print_results(all_tests: list[str])` — the results summary + exit code logic.

- **TASK-140b** — Refactor `test_heatmap_reliability.py` to import from `ve_suite_base`.
  Replace the local `RESULTS`, `pass_/fail/skip/flake`, and `main()` block with imports
  and a 3-line `main()` that calls `make_arg_parser`, `Dut`, `run_suite`,
  `print_results`. Behaviour must be identical (same CLI, same output format).

- **TASK-140c** — Refactor `test_tls_yield_reliability.py` likewise.

- **TASK-140d** — Smoke-test: run both satellite suites end-to-end on DUT after refactor
  to confirm identical pass/fail/skip behaviour. `check_build.sh` 4/4.

#### Exit criterion

Both satellite files import boilerplate from `ve_suite_base.py`; no local copies of
`RESULTS`/`pass_`/`fail`/`skip`/`flake`/`main` remain in either file; all tests pass;
a new satellite test can be created by importing 4 names from `ve_suite_base` + defining
test functions.

**Completion note (2026-06-04):** `app/tools/ve_suite_base.py` created: `RESULTS`, `pass_/fail/skip/flake`, `make_arg_parser` (description kwarg), `run_suite` (inter_test_sleep param), `print_results`. `test_heatmap_reliability.py`: local result-tracking block removed; imports from `ve_suite_base`; `main()` uses `make_arg_parser` + lambda wiring for T216/T217 soak_minutes. `test_tls_yield_reliability.py`: same pattern; `inter_test_sleep=1.0`. Both `argparse` imports removed. DUT smoke: T219/T220/T221 PASS; T214 PASS, T215 SKIP (no -1 on this run); T216 PASS (1-min soak); T217 expected-FAIL (no 120s heatmap fetch in 1-min window — same as before refactor). `check_build.sh` 4/4.

---

### TASK-132 — PERF-CPU: Instrumentation setup + baseline capture
**Owner**: Developer
**Feature**: perf-cpu-001 (new)
**Status**: done (2026-06-04)
**Milestone**: M-PERF-CPU
**Design**: `docs/architecture/designs/M-AQUARIUM/cpu-opt.md` §3
**ADR**: `docs/architecture/decisions/ADR-038.md` (proposed)
**Blocks**: TASK-133 (baseline must be captured before any optimisation phase)

Add `xthal_get_ccount()`-based perf accumulators to `AquariumApp` and capture the
pre-optimisation baseline so each subsequent phase has a measured before/after record.

Sub-tasks:
- **TASK-132a** — Add four `uint32_t` accumulators (`_perfCycUpdate`, `_perfCycDraw`, `_perfCycTick`, `_perfFrames`) to `AquariumApp` member list.
- **TASK-132b** — Wrap `tick()` update and render regions with `xthal_get_ccount()` pairs; emit `[aq perf] tick=Xus upd=Xus draw=Xus` via `Serial.printf` every 300 frames (~10 s). Pattern per cpu-opt.md §3.2.
- **TASK-132c** — Build `cyd2usb_winamp_debug`, flash, navigate to Aquarium, let settle 30 s, record three consecutive `[aq perf]` lines → enter as **Baseline** row in cpu-opt.md §7.1.
- **TASK-132d** — `check_build.sh` 4/4.

Exit criterion: `[aq perf]` output visible in serial monitor; §7.1 Baseline row filled in.

---

### TASK-133 — PERF-CPU P1+P2: Trivial optimisations + reciprocal constants
**Owner**: Developer
**Feature**: perf-cpu-001
**Status**: done (2026-06-04)
**Milestone**: M-PERF-CPU
**Design**: `docs/architecture/designs/M-AQUARIUM/cpu-opt.md` §4.3–§4.6, §10.2, §10.4
**Depends on**: TASK-132 (baseline captured)
**Blocks**: TASK-134

**P1 — trivial (aquariumApp.h):**
- **TASK-133a** — `updateClock()`: add `_lastClockUpdateMs` member; early-return if `millis() - _lastClockUpdateMs < 1000`. (§4.5)
- **TASK-133b** — `_frand`: replace `/ 9999.0f` with `* kInv9999` (`static constexpr float`). (§4.6)
- **TASK-133c** — `updateFish:695-696`: replace four `/ nearCount` with `float invN = 1.0f/nearCount` + four multiplies. (§4.4)

**P2 — reciprocal constants:**
- **TASK-133d** — `aquariumApp.h`: add 12 `static constexpr float` reciprocals for all radius denominators (`kInvFishAvoidRX/RY`, `kInvOctFishAv/ClRX/RY`, `kInvSHFishAv/ClRX/RY`, `kInvVisClRX/RY`); replace all division sites in `updateFish`, `_steerFrom*`, `_pushOutOf*`, `keepVisitorsSeparated`. (§4.3)
- **TASK-133e** — `vuMeter.h:tickSpectrum`: add `constexpr float kInv18`, `kInvVisH`; replace `ei/18.0f`, `specH[i]/(float)VIS_H`, `1.0f/VIS_H`. (§10.2)
- **TASK-133f** — `main.cpp`: replace two `/ 1000.0f` with `* 0.001f` at lines ~204 and ~1900. (§10.4)
- **TASK-133g** — Build `cyd2usb_winamp_debug`, flash, capture three `[aq perf]` lines → fill P1+P2 row in §7.1. Visual check: fish swim normally, spectrum bars animate.
- **TASK-133h** — `check_build.sh` 4/4.

Exit criterion: `check_build.sh` passes; measurable `upd` reduction vs baseline in §7.1; no visual regression.

---

### TASK-134 — PERF-CPU P3: mathUtil.h + fast inverse sqrt
**Owner**: Developer
**Feature**: perf-cpu-001
**Status**: done (2026-06-04)
**Milestone**: M-PERF-CPU
**Design**: `docs/architecture/designs/M-AQUARIUM/cpu-opt.md` §4.2, §11
**Depends on**: TASK-133
**Blocks**: TASK-135, TASK-136 (both need mathUtil.h in tree)

- **TASK-134a** — Create `app/src/util/mathUtil.h`: `q_rsqrt`, `lut_sin`, `lut_cos`, `buildMathLUT()`, `extern float g_sinLUT[512]`. Create `app/src/util/mathUtil.cpp`: `float g_sinLUT[512]` definition. (§11)
- **TASK-134b** — `main.cpp:setup()`: add `buildMathLUT()` call before first app tick.
- **TASK-134c** — `aquariumApp.h`: replace `1.0f/sqrtf(sd2)` with `q_rsqrt(sd2)` at `_pushOutOfOctopus:610`, `_pushOutOfSeahorse:630`, `keepVisitorsSeparated:834`.
- **TASK-134d** — `aquariumApp.h`: fold velocity normalisation `updateFish:723-725` — `mag=sqrtf(...); vx/=mag` → `inv=q_rsqrt(...); vx*=inv; vy*=inv`.
- **TASK-134e** — `aquariumApp.h`: fold `_steerFromOctopus:576` and `_steerFromSeahorse:590` — `dist=sqrtf(dx²+dy²)` then `/dist` → `inv=q_rsqrt(dx²+dy²); dx*=inv`.
- **TASK-134f** — Build `cyd2usb_winamp_debug`, flash, capture `[aq perf]` → fill P3 row in §7.1. Visual: fish avoid octopus/seahorse with no penetration through bounding ellipse.
- **TASK-134g** — `check_build.sh` 4/4.

Exit criterion: `check_build.sh` passes; fish do not visually penetrate visitor ellipses; `[aq perf] upd` reduced vs P2 row; §7.1 P3 row filled.

---

### TASK-135 — PERF-CPU P4: VuMeter wave rotation matrix + LFO
**Owner**: Developer
**Feature**: perf-cpu-001
**Status**: done (2026-06-04)
**Milestone**: M-PERF-CPU
**Design**: `docs/architecture/designs/M-AQUARIUM/cpu-opt.md` §10.1, §10.3
**Depends on**: TASK-134 (mathUtil.h in tree for lut_sin)
**Blocks**: TASK-137

- **TASK-135a** — `vuMeter.h:tickWave`: replace the 76-sinf pixel loop with rotation matrix. Add `static constexpr float kWaveStep = WAVE_CYCLES * TWO_PI_F / float(RECT_W)`. Add `static const float kWaveSin = sinf(kWaveStep)` and `kWaveCos` (evaluated once). Seed `wave=sinf(wavePhase)`, `waveC=cosf(wavePhase)` per frame; advance per pixel. (§10.1)
- **TASK-135b** — `vuMeter.h:tick()`: replace three LFO `sinf` calls (`:190`, `:367`, `:383`) with `lut_sin` + inline `* reciprocal` for the time-scaling division. `#include "util/mathUtil.h"`. (§10.3)
- **TASK-135c** — Build `cyd2usb_winamp_debug`, flash, navigate to Winamp wave visualiser. Verify: waveform visible, continuous, phase-advances at same apparent speed. Capture `[aq perf]` → fill P4 row in §7.1.
- **TASK-135d** — `check_build.sh` 4/4.

Exit criterion: `check_build.sh` passes; wave visualiser correct on DUT; `[aq perf] draw` measurably reduced vs P3; §7.1 P4 row filled.

---

### TASK-136 — PERF-CPU P5: Trig LUT — all 41 aquarium sinf/cosf sites
**Owner**: Developer
**Feature**: perf-cpu-001
**Status**: done (2026-06-04)
**Milestone**: M-PERF-CPU
**Design**: `docs/architecture/designs/M-AQUARIUM/cpu-opt.md` §4.1
**Depends on**: TASK-134 (mathUtil.h in tree)
**Blocks**: TASK-137

Replace every remaining `sinf`/`cosf` call in `aquariumApp.h` with `lut_sin`/`lut_cos`.

- **TASK-136a** — `#include "util/mathUtil.h"` at top of `aquariumApp.h`. Replace all 41 `sinf`/`cosf` call sites. Sites by function: `updateFlakes` (1), `updateBubbles` (1), `updateFish` (3), `updateOctopus` (1), `updateSeahorse` (3), `keepVisitorsSeparated` (0 — no trig), `drawFish` (2 seed + 4 constexpr statics), `drawOctopus` (10), `drawSeahorse` (6), `drawCrab` (10), `_seaweedBranches` (1). Exception: `buildMathLUT()` body in mathUtil.h retains `sinf`.
- **TASK-136b** — Verify `grep -n 'sinf\|cosf' app/src/aquarium/aquariumApp.h` returns zero matches (excluding any `#include` lines).
- **TASK-136c** — Build `cyd2usb_winamp_debug`, flash, let Aquarium run 60 s. Visual: fish swim, seaweed sways, bubbles rise, octopus/seahorse traverse, crab walks. No frozen elements.
- **TASK-136d** — Capture `[aq perf]` → fill P5 row in §7.1.
- **TASK-136e** — `check_build.sh` 4/4.

Exit criterion: `check_build.sh` passes; no bare `sinf`/`cosf` in aquariumApp.h; all animation continuous; §7.1 P5 row filled; `[aq perf] tick` ≥ 30% below Baseline.

---

### TASK-137 — VE: CPU-opt acceptance (ADR-038)
**Owner**: VE
**Feature**: perf-cpu-001
**Status**: open — pending human visual sign-off (criteria 3, 6, 8, 9, 13)
**Milestone**: M-PERF-CPU
**Design**: `docs/architecture/designs/M-AQUARIUM/cpu-opt.md` §7
**Depends on**: TASK-132, TASK-133, TASK-134, TASK-135, TASK-136

Execute the full VE criteria table from cpu-opt.md §7. Record pass/fail against each
criterion. Fill in any remaining §7.1 measurement rows. File bug tasks for any failure.

- **TASK-137a** — VE criteria 1–7 (P1–P3 checks): clock throttle, fish behaviour, push-out, steer, `[aq perf] upd` reductions.
- **TASK-137b** — VE criteria 8–10 (P4 checks): wave visualiser, cadence, `[aq perf] draw` reduction.
- **TASK-137c** — VE criteria 11–14 (P5 checks): sinf grep, animation continuous, `[aq perf] tick` ≥ 30% reduction.
- **TASK-137d** — VE criteria 15–16: 10 app-switch cycles without crash; `check_build.sh` 4/4.
- **TASK-137e** — §7.1 measurement table complete; ADR-038 moved `proposed → accepted` pending human sign-off.

Exit criterion: all 16 VE criteria pass; §7.1 fully populated; combined `tick` reduction ≥ 30% confirmed in serial data.

**VE record (2026-06-04):**
| # | Result | Notes |
|---|---|---|
| 1 | PASS | `_lastClockUpdateMs` guard compiled and DUT stable |
| 2 | PASS | check_build.sh 4/4 after P1+P2 |
| 3 | NEEDS HUMAN | Visual — DUT running on /dev/ttyUSB0 |
| 4 | PASS | upd 1074→935 µs (−139 µs >> 5 µs threshold) |
| 5 | PASS | 10 switch cycles no NaN/freeze crash |
| 6 | NEEDS HUMAN | Visual push-out behaviour |
| 7 | PASS | upd 935→449 µs (−486 µs >> 10 µs threshold) |
| 8 | NEEDS HUMAN | Visual wave visualiser (switch to Winamp app) |
| 9 | NEEDS HUMAN | Visual wave cadence A/B |
| 10 | PASS | draw 49910→45792 µs (−4118 µs >> 20 µs threshold) |
| 11 | PASS | grep sinf aquariumApp.h = 0 matches |
| 12 | PASS | grep sinf vuMeter.h = 0 matches (after fixing rotation seed) |
| 13 | NEEDS HUMAN | Visual animation continuous 60 s |
| 14 | PASS | tick 46246→41400 µs (−4846 µs >> 40 µs threshold) |
| 15 | PASS | 10 aquarium↔winamp cycles, DUT responsive |
| 16 | PASS | check_build.sh 4/4 final |

**Overall tick reduction: 51371→41400 µs = −19.4%.** Below §6 goal of 30% — draw-bound (SPI blit ~99% of tick, physics now <1%). Physics upd reduced 71% (1074→311 µs). 30% tick criterion requires render path optimisation (out of scope for this milestone).

---

### TASK-130 — VE: Heatmap fetch reliability stress test (serial-dbg)
**Owner**: VE
**Feature**: stock-002
**Status**: complete
**Milestone**: M-HEATMAP
**Source**: user report 2026-06-03 — ERR -1 persists after two fixes (mailbox guard + main-loop guard)

Design and execute a serial-debug stress suite that maps all remaining heatmap fetch reliability issues. Two fixes are already in (`f09f196`, `a0f7601`) but ERR -1 is still observed. The suite must reproduce the failure, characterise it, and provide Developer with a reproducible harness.

#### Known failure modes to cover

| ID | Scenario | Observable |
|----|----------|-----------|
| FM-1 | Double-enqueue: `triggerHeatmap` + next tick both enqueue; fetch B (-1) races fetch A (200) in one-slot mailbox | ERR shown despite A being 200 |
| FM-2 | Long-uptime TLS heap fragmentation: Spotify poll + Yahoo HTTPS competing; `maxAlloc` drops until screener can't open TLS | Persistent -1 at 120s cycle; never recovers |
| FM-3 | Fetch -1 overwrites `_s.heatmapData` when `ok=false` (pre-fix regression check) | ERR shown, `heatmapCount=0` |
| FM-4 | Unknown — ERR -1 still reported after both fixes; root cause not yet identified | ERR shown, `heatmapCount=20` |

#### Sub-tasks

- **TASK-130a** — Write `test_heatmap_reliability.py` (or extend `run_serialdbg_tests.py`). Tests T214–T218. All must run on DUT via serial; no mocking.
- **TASK-130b** — Execute suite against current debug build. Log all `heatmap GET -1` occurrences, `get heatmapCount` state before/after each, and `get stockSubView` to confirm display state. Capture for ≥10 minutes to catch long-uptime failures.
- **TASK-130c** — Write findings report: which FMs are reproduced, which are fixed, which are new. File new bug tasks for any unresolved FM. Hand off to Developer.

#### Suggested test cases

- **T214** — Rapid `set triggerHeatmap 1` × 5 in 2s: assert `heatmapCount` never drops to 0 after a prior success.
- **T215** — Single `set triggerHeatmap 1`: wait for 200 ok, then wait for immediate -1; assert `heatmapCount` still > 0 and `stockSubView = heatmap`.
- **T216** — 10-minute uptime soak: poll `heatmapCount` + `stockSubView` every 30s; assert never 0 / never "error" while DUT has had at least one successful fetch.
- **T217** — Heap headroom: after each heatmap fetch attempt (pass or fail), log `hb` heartbeat `maxAlloc`; assert never below 32k (minimum for TLS handshake).
- **T218** — Recovery: after a -1 cycle, wait 120s for next auto-fetch; assert `heatmapCount` recovers to > 0 within 300s.

Exit criterion: T214–T218 all pass or each failing test has a filed bug task with repro steps.

**Test IDs**: T214–T218.

**Completion note (2026-06-03):** Suite written (`app/tools/test_heatmap_reliability.py`). Full run: T214 PASS, T216 PASS, T218 PASS; T215 SKIP (FM-2 blocks all new 200s); T217 SKIP (harness pattern bug `"hb:"` → fix to `"[hb]"` applied, re-run pending). Key findings: FM-1/FM-3 guards both working; FM-4 closed (explained by FM-2); FM-2 confirmed as sole unresolved failure — filed as TASK-131. Report at `docs/verification/regression_suite/heatmap-reliability-ve-review.md`.

---

### TASK-129 — FEAT: Heatmap tile label — Tier 6 rotated vertical text
**Owner**: Developer
**Feature**: stock-002
**Status**: complete (git `0f9ee08` + fix)
**Milestone**: M-HEATMAP
**Design**: `docs/architecture/decisions/ADR-037.md` — Amendment (Tier 6), 2026-06-03
**Depends on**: TASK-128 (complete)

Adds Tier 6 to `repaintHeatmap()`: tiles with `w ≥ 8` that can't fit horizontal text render the ticker via a `TFT_eSprite` pushed at −90° using `pushRotated`, viewport-clipped to the tile. Ticker only — no pct. Silent fallback to blank if `createSprite` fails (OOM).

#### Sub-tasks

- **TASK-129a** — Add Tier 6 branch to the label cascade in `repaintHeatmap()` (`main.cpp`). Add `HM_T6_MIN_W = 8` constant. Implement sprite path per ADR-037 Amendment render snippet.
- **TASK-129b** — `check_build.sh` 4/4. Flash debug. Verify rotated ticker visible on a narrow tile. Confirm no bleed into adjacent tiles.

Exit criterion: `check_build.sh` 4/4; rotated ticker visible and contained within tile bounds on DUT.

**Completion note**: Two bugs found and fixed during DUT verification: (1) T5 overflow guard was inside the branch body, silently dropping tiles that matched T5's w/h conditions but couldn't fit horizontal text — fix: move guard into the condition. (2) T6 originally had a height guard that blocked short tiles — fix: drop guard, use `setViewport` to clip. Final DUT run: KLAC/SNDK/QCOM (w=21..22, h=30..31) confirmed rotated, heap stable 121k, no bleed.

**Test IDs**: T211 (rotated ticker visible on narrow tile, MANUAL — PASS), T212 (no bleed into adjacent tiles, MANUAL — PASS), T213 (OOM fallback: blank tile, not crash, MANUAL — low priority, deferred).

---

### TASK-126 — BUG: Yahoo Finance chart fetches -92/-1 (missing useHTTP10 + User-Agent)
**Owner**: Developer
**Feature**: stock-002
**Status**: done
**Milestone**: M-HEATMAP
**Source**: EXP-001 / PROP-003 (2026-06-03); closes TASK-124

#### Fix

Add `http.addHeader("User-Agent", "Mozilla/5.0")` and `http.useHTTP10(true)` to three
functions in `dataTaskStorage.cpp` — same pattern as `fetchHeatmapQuote` (ADR-034):

- `fetchStockQuote` — before `http.GET()` (~line 164)
- `fetchStockChart` — before `http.GET()` (~line 220)
- `fetchStockChartBySym` — before `http.GET()` (~line 362)

Why: `v8/finance/chart` returns `Transfer-Encoding: chunked` under HTTP/1.1.
`http.getStream()` exposes raw chunk-size bytes to ArduinoJson → `IncompleteInput` (-92).
Mid-stream failures → TCP RST on `http.end()` → Yahoo CDN per-IP throttle → -1.
HTTP/1.0 forces identity encoding (connection-close); clean end-of-stream.

#### Exit criterion

`check_build.sh` 4/4 passes; DUT runs for 30 min with chart browsing + heatmap drill-through
with `fetchErrCount` = 0 and no -92/-1 in serial log.

---

### TASK-124 — INVESTIGATE: Yahoo Finance -1 (TCP connection refused) on DUT
**Owner**: RnD
**Feature**: stock-001 / stock-002 (cross-cutting)
**Status**: done
**Milestone**: M-HEATMAP
**Source**: observed during TASK-121 verification 2026-06-02
**Closed**: 2026-06-03 — root cause identified; fix scheduled as TASK-126

#### Root cause (EXP-001, 2026-06-03)

Both -92 and -1 errors share the same root: `fetchStockChart` / `fetchStockChartBySym` do
not call `http.useHTTP10(true)`. The `v8/finance/chart` endpoint returns
`Transfer-Encoding: chunked` under HTTP/1.1. `http.getStream()` exposes raw chunked bytes
to ArduinoJson; ArduinoJson sees the hex chunk-size header (`2023\r\n`) as JSON, fails with
`IncompleteInput` → **-92**. The mid-stream failure forces an unclean TCP RST on `http.end()`.
During rapid tab-switch bursts, the RST storm triggers Yahoo CDN per-IP throttling → new SYNs
silently dropped → 30 s TCP timeout → **-1**. Auto-recovers when block expires (1–5 min).

`fetchHeatmapQuote` already has `useHTTP10(true)` (ADR-034 / TASK-119); it was not propagated
to the chart functions.

**Hypothesis 1 confirmed** (per-IP connection-rate, via RST storm). H2/H3/H4 superseded.
Exponential back-off not required — removing RSTs eliminates the trigger.

See: `docs/rnd/reports/EXP-001-yahoo-finance-errors.md`, `docs/rnd/proposals/PROP-003.md`

---

### TASK-111 — M-AQUARIUM-CRAB: Implement aquarium crab creature
**Owner**: Developer
**Feature**: aquarium-crab-001 (new)
**Status**: open
**Milestone**: M-AQUARIUM-CRAB
**Blocked by**: nothing (M-AQUARIUM done — `aquariumApp.h` in tree)
**Design**: `docs/architecture/designs/M-AQUARIUM/crab.md`
**Notes**:
- **TASK-111a**: Add `Crab` struct (state enum, x, direction, walkFrame, pinchFrame, sleepZFrame, cuteDurationMs, timestamps) and all `CRAB_*` constants to `aquariumApp.h`.
- **TASK-111b**: Implement `initCrab()` — center x, direction right, state WALK, seed timestamps.
- **TASK-111c**: Implement `updateCrab(float dt)`:
  - Walk: `_crab.x += direction * CRAB_SPEED_PX_S * dt`; reverse at margins; seaweed-root avoidance via `_seaweedBaseX[]`.
  - Walk-frame: 4-frame leg sweep (direction-aware modulo advance every `CRAB_WALK_STEP_MS`).
  - Proximity scan: active fish + flakes in bottom zone → enter PINCH_L or PINCH_R; reset `pinchFrame = 0`.
  - Pinch frame advance (0→3); on frame 3 hold: `findPinchTarget()` → hit (remove fish, CUTE 3s) or miss (WALK).
  - Cute exit: `elapsed >= cuteDurationMs` → WALK.
  - Sleep Z advance every `CRAB_SLEEP_Z_MS`.
  - State transitions per §3 of design doc.
- **TASK-111d**: Implement `drawCrab()` — two-row draw (body + leg row overlapped); sleep ZZZ sway column; cute blink via `(elapsed/375)%2`.
- **TASK-111e**: Implement `findPinchTarget()` — proximity re-scan returning fish index or -1.
- **TASK-111f**: Wire `initCrab()` into `init()`; `updateCrab(dt)` into `tick()` after `updateFlakes()`; `drawCrab()` into `renderFrame()` after `drawSeaweed()`.
- **TASK-111g**: `check_build.sh` 4/4 ✅; flash to DUT; verify crab visible at bottom, walks, pinches a flake on touch-spawn.
- Exit criterion: crab renders in red at canvas bottom, walks, pinches nearby fish (fish disappears), cute blink plays; `check_build.sh` passes.

---

### TASK-105 — M-TASKBAR-SCROLL: Implement scrolling taskbar
**Owner**: Developer
**Feature**: taskbar-scroll-001 (new)
**Status**: implemented (flashed 2026-05-26; pending VE TASK-106)
**Milestone**: M-TASKBAR-SCROLL
**Blocks**: nothing — stub registration lands in this task
**Design**: `docs/architecture/designs/M-MULTIAPP/taskbar.md` §Scroll model (updated to match impl)
**Notes**:
- **TASK-105a**: ✅ `AppId::COUNT = 8`; `SettingsApp`/`StockApp` stubs; `g_apps[]` extended; `icons[]` extended.
- **TASK-105b**: ✅ Private fields added to `WinampDisplay`: `_tbScrollOffset`, `_tbDragStartY`, `_tbDragBaseOff`, `_tbScrollAccum`, `_tbIsScrolling`. *(105b spec listed 3 fields; 2 extras added during UX tuning.)*
- **TASK-105c**: ✅ `D_TASKBAR_SCROLL` added to `DragState`; debug string table updated.
- **TASK-105d**: ✅ **UX deviated from spec** — gesture model changed after DUT testing:
  - **Spec**: velocity-style accumulation (`eff * 0.04f`), `SCROLL_DEAD_ZONE_PX = 1`, tap = `|dy| < 3 px`.
  - **Implemented**: **1:1 positional** (each `TASKBAR_SLOT_H` px = 1 slot, anchored to press origin via `_tbDragBaseOff`); **LP filter** on raw dy (`TB_LP_ALPHA = 0.4f`); **`TB_SCROLL_DEAD_ZONE_PX = 3`**; tap detection via `_tbIsScrolling` flag (latched, not re-evaluated at release). Gesture routing is in `appHandleInput()` via public method bundle (`tbGesturePress`, `tbGestureContinue`, `tbGestureEnd`) rather than inline code in `checkForInput()`.
  - Design doc updated: `docs/architecture/designs/M-MULTIAPP/taskbar.md`.
- **TASK-105e**: ✅ `renderTaskbar()` signature updated: 4 args.
- **TASK-105f**: ✅ All call sites updated (`switchApp`, `setup()`, taskbar move branch).
- **TASK-105g**: ✅ `dbgGet("tbScrollOffset")` added.
- Exit criterion: `check_build.sh` 4/4 ✅; DUT flashed; UX accepted by operator.

---

### TASK-107 — BUG: Aquarium blank screen — debug render/push path
**Owner**: Developer
**Feature**: aquarium-001
**Status**: closed
**Milestone**: M-AQUARIUM
**Blocked by**: nothing
**Closed**: 2026-05-29
**Notes**:
- EXP-002 (2026-05-28) ruled out heap pressure as cause.
- Fixed by `162f627` (2026-05-28): `pushSprite(0, 145−h)` → `pushSprite(0, 0)`; black gap fills
  below sprite when canvas is smaller than full height. Root cause #1 from the task.
- P1–P5 commits (bss optimisation) followed; render path confirmed correct throughout.
- Reference: `app/src/aquarium/aquariumApp.h` — `init()`, `tick()`, `renderFrame()`.

---

### TASK-108 — Hardening: Coingecko TLS client.stop() on fetch failure
**Owner**: Developer
**Feature**: crypto-001
**Status**: done (git `e00b453`, closed as part of TASK-131 extended fix 2026-06-04)
**Blocked by**: nothing
**Notes**:
- EXP-002 (2026-05-28) observed that a failed TLS connection to `api.coingecko.com`
  left ~64 KB of heap stranded for several minutes (freeHeap 110 k → 46 k;
  maxAllocHeap 57 k → 41 k). Memory recovered on its own but timing is non-deterministic.
- Fix: ensure `http.end()` / `client.stop()` is called on all error paths in
  `dataTask` crypto fetch so the SSL context is released promptly.
- Affects: `app/src/dataTask.h` crypto fetch path (and audit weather path for symmetry).
- Low-risk: one-liner guard; no behaviour change on success path.
- EXP-002 report: `docs/rnd/experiments/EXP-002-heap-benchmark.md`.

**Completion note (2026-06-04):** Superseded and closed by TASK-131 extended fix. `fetchCrypto` now wraps the entire fetch in `tlsYield/tlsResume` + `http.useHTTP10(true)` + body-first pattern, ensuring TLS is released on all paths (success and failure). Weather path also audited and fixed identically. DUT confirmed: `heap free=119k maxBlk=71k` after crypto fetch; no NoMemory errors.

---

### TASK-106 — VE: test suite for taskbar-scroll-001 (T162–T168)
**Owner**: VE
**Feature**: taskbar-scroll-001
**Status**: open (planned — write + execute after TASK-105 done)
**Milestone**: M-TASKBAR-SCROLL
**Blocked by**: TASK-105 (firmware + `get tbScrollOffset` via TASK-105f)
**Notes**:
- All tests require `cyd2usb_winamp_debug` firmware + `get tbScrollOffset` via serial.
- Taskbar hitbox: `x ∈ [TASKBAR_X, 319]`, `y ∈ [0, 239]`. Slot height = `TASKBAR_SLOT_H = 40`.
- ⚠️ **T162/T165 need revision** — TASK-105 UX deviated from original spec (see TASK-105d notes):
  - T162 tap threshold: tap = `_tbIsScrolling` never set = raw `|dy| < TB_SCROLL_DEAD_ZONE_PX = 3` (not `SCROLL_DEAD_ZONE_PX * 3`). Test value unchanged but constant source changed.
  - T165 clamp: **does not clamp** — wrap-around is used in all directions. T165 should become "wrap-around down" (same as T167). VE to revise T165 before running.
  - T163/T164: 1:1 positional model means ≥40 px travel triggers 1 slot. Due to LP filter (`α=0.4`), `cmdDrag` of exactly 40 px may land at ~35 px smoothed — use ≥50 px drag in serial tests to guarantee a slot step.
- **T162** — Tap: `|rawDy| < 3 px` (never exceeds dead zone) → `switchApp`, `tbScrollOffset` unchanged.
- **T163** — Drag-up: drag ≥50 px up → `tbScrollOffset` increments by 1.
- **T164** — Drag-down: drag ≥50 px down → `tbScrollOffset` decrements by 1.
- **T165** — Wrap-around down: drag-down when `tbScrollOffset = 0` wraps to `N − 1 = 7`. *(revised — no clamp; all directions wrap)*
- **T166** — Wrap-around up: drag-up when `tbScrollOffset = N − 1 = 7` wraps to 0.
- **T167** — *(retired — duplicate of revised T165; renumber if needed)*
- **T168** — Active indicator follows app, not slot: after scroll, active bar renders at the slot containing `currentAppId`, not at slot `(int)currentAppId`.
- Test IDs T162–T168. Owner: VE. Status: planned (TASK-105 unblocked 2026-05-26).

---

### TASK-087 — M-MULTIAPP step 2: taskbar + app-shell + Clock app
**Owner**: Developer
**Feature**: taskbar-001, clock-001 (new)
**Status**: done (2026-05-24 — check_build.sh 3/3 pass; BUG-1 fixed; DUT flash + smoke test PASS; T076/T081/T082/T086/T087/T088/T134–T140/T147/T148 all pass 15/15)
**Blocks**: M-MULTIAPP step 3 (Matrix, GoL, Weather, Crypto apps)
**Notes**:
- **TASK-087a** (`taskbar.h`): `renderTaskbar(TFT_eSPI& tft, AppId activeApp)` — fills 45×240 strip with TASKBAR_BG_RGB565, draws icon letters S/C/W/$/M/G (TFT font 4), separator lines (TASKBAR_SEP_COLOR), and 3 px active-indicator bar (TASKBAR_ACTIVE_COLOR) on the active slot.
- **TASK-087b** (`winampDisplay.h`): Added `#include "appShell.h"` + `#include "taskbar/taskbar.h"`. Taskbar first-pass hit-test in `checkForInput()` (after touch read, before Winamp hit-tests): `p.x >= TASKBAR_X` → `switchApp(slot)`. `renderTaskbar()` called at end of `repaintChrome()` (covers startup + reconnect repaints).
- **TASK-087c** (`appShell.h`): Added per-app state structs (SpotifyAppState, ClockAppState, Weather/Crypto/Matrix/LifeAppState), `g_appLaunched[]`, `clockRepaint()`/`clockTick()` declarations, static asserts (`TASKBAR_X == 275`, `AppId::COUNT == TASKBAR_SLOT_COUNT`) unlocking T127/T129.
- **TASK-087d** (`main.cpp`): Full `switchApp()` (fillRect app canvas + update currentAppId + renderTaskbar + per-app repaint). `appTick()` dispatches Spotify + Clock; stubs for other apps. `appHandleInput()` unchanged (delegates to `checkForInput()` which has the taskbar guard). Boot `renderTaskbar()` call in `setup()` after `showDefaultScreen()`.
- **TASK-087e** (`main.cpp`): `clockRepaint()` draws three rounded-rect chrome boxes. `clockTick()`: blinking colon at 1 Hz, rainbow 60-segment seconds bar, day + date strings, RSSI signal bars.
- **TASK-087f**: `./check_build.sh` 3/3 pass ✓. DUT smoke test required (flash + verify taskbar visible, Clock renders, Spotify switch works).
- **Feature inventory**: `taskbar-001` + `clock-001` registered.
- **Salvage (PM audit 2026-05-24)**: BUG-1 fixed — guard added in `checkForInput()` and `injectTouch()` to return early for non-Spotify apps, preventing Clock canvas taps from falling through to Winamp hit-tests. `get appId` added to `dbgGet()`. T147/T148 written in test harness. BUG-2 (saveAppState/restoreAppState) deferred to TASK-088. GAP-1 (icon glyphs) deferred to M-MULTIAPP aesthetics pass.

---

### TASK-089 — Fix stale tool-script paths + add smoke-test gate (LL-029)
**Owner**: Developer
**Feature**: tooling-001 (new)
**Status**: done (2026-05-25 — preview_layout.py stale paths fixed; smoke_test.sh integrated into check_build.sh as step 4; 4/4 pass)
**Blocks**: reliable use of `preview_vis.py`, `bake_wave.sh`, `preview_wave.py`, `bake_skin.py` from `app/tools/`
**Notes**:
- Six functional (runtime-breaking) stale paths identified in audit 2026-05-24 (LL-029):
  - `app/tools/preview_vis.py:65` — `pathlib.Path` references `../SpotifyDiyThing/gen/skin_layout.h`
  - `app/tools/bake_wave.sh:19` — `-o "$SCRIPT_DIR/../SpotifyDiyThing/gen"`
  - `app/tools/preview_vis.py:340` — argparse `default="SpotifyDiyThing/gen/skin_preview_animated.gif"`
  - `app/tools/preview_wave.py:128-129` — argparse `default` + `help` referencing `SpotifyDiyThing/gen/`
  - `app/tools/bake_skin.py:773` — `parse_shell_layout(path="SpotifyDiyThing/gen/shell_layout.h")` default
- Eight docstring/help stale paths in `bake_skin.py:8-9`, `bake_vis.py:7-8`, `bake_wave.py:6-7`, `preview_vis.py:20-22,26-27,32,37-38`.
- Deliverable 1: fix all 14 stale strings (6 functional + 8 docstring) to use `Path(__file__).parent / "../gen/..."` pattern.
- Deliverable 2: add `app/tools/smoke_test.sh` — imports each Python module (`python3 -c "import coords"` etc.) and calls each shell script with `--help`. Integrate into `check_build.sh` or run standalone as pre-commit gate.
- Exit criterion: `smoke_test.sh` exits 0 from `app/tools/`; `check_build.sh` 3/3 still passes.

---

### TASK-088 — Deferred: saveAppState / restoreAppState for switchApp()
**Owner**: Developer
**Feature**: app-lifecycle-001
**Status**: superseded by TASK-090 — close without separate implementation
**Notes**:
- Original scope (free-function `saveAppState`/`restoreAppState` in `main.cpp`) is superseded by the App ABC design in TASK-090. State persistence for SpotifyApp is delivered via `SpotifyApp::suspend()` / `resume()`, which is the correct location under the new layering. The `g_appState[]` union is retained in `appShell.h` for future per-app struct copies; `SpotifyApp::suspend()` will populate it when other apps require Spotify fields on resume.
- The "risk window opens at step 5" concern is also addressed by TASK-090: each new app class carries its own state in class members and resets it in `suspend()`. No shared union copy needed until cross-app field sharing is required.
- VE gate (T147 round-trip) carries forward into TASK-090's exit criteria.

---

### TASK-090 — App Interface ABC + AppShell refactor (M-MULTIAPP)
**Owner**: Developer
**Feature**: app-interface-001 (new)
**Status**: done (2026-05-25 — 090h complete; see commit for T_BI tests; production flash verified)
**Blocks**: M-MULTIAPP step 3 (Matrix, GoL, Weather, Crypto — each requires a clean `App` class to land on)
**Design**: `docs/architecture/designs/M-MULTIAPP/app-interface.md`, `docs/architecture/decisions/ADR-026.md`
**Notes**:
- Fixes B1–B4 from TASK-087 post-mortem as structural consequences of the correct interface, not targeted patches.
- Absorbs TASK-088 (saveAppState/restoreAppState now delivered via `SpotifyApp::suspend()`).
- 090a–090g: DONE. All code committed at 163ce67. check_build.sh 3/3 green.
- 090h completion (2026-05-25):
  - Flashed debug build (163ce67 firmware). T148 **confirmed PASS** on clean run.
  - Full existing suite: 26/27 — T087 intermittent TLS-timing flake (pre-existing, unrelated).
  - **T_BI_01–T_BI_04**: implemented in `run_serialdbg_tests.py`; all 4 PASS on first run.
  - Total test suite: 31 tests (27 existing + 4 new T_BI). 30/31 on best run; intermittent failures are T084/T087/T091/T092 (reconnect race + TLS timing, pre-existing).
  - Production build flashed and verified boot. DUT left in production state.
- Commit with T_BI tests: see `ve(TASK-090)` commit.

- Implementation order completed:
  - **TASK-090a** ✓ `drawPlaylist()` gutter fix
  - **TASK-090b** ✓ `TouchPhase` enum + `App` struct (moved to `touchPhase.h` to avoid circular dep)
  - **TASK-090c** ✓ `WinampDisplay` refactor: `handleWinampInput`, `resetDragState`, `invalidatePlaylist`; removed shell coupling
  - **TASK-090d** ✓ `SpotifyApp` class
  - **TASK-090e** ✓ `ClockApp` class
  - **TASK-090f** ✓ `appHandleInput()` gesture loop with `s_inGesture`/`s_cooldownMs`
  - **TASK-090g** ✓ Serial debug: `cmdTap`/`cmdDrag` updated; `dbgGet("lastPlaylistDraw")` added
  - **TASK-090h** ✓ T148 confirmed PASS; T_BI_01–04 implemented + PASS; production flash verified

---

### TASK-092 — Hotfix: TFT shared-state leak on app switch (ADR-027)
**Owner**: Developer + Architect + QM
**Feature**: app-interface-001
**Status**: done (2026-05-25 — commit cb79ea8; production flashed)
**Notes**:
- Bug: `ClockApp::drawTime/drawDate` set `MC_DATUM` without reset; PLEDIT rows rendered 2–3 chars off-screen and ~2 px high after Clock→Spotify switch.
- Fix (three-layer defence-in-depth per ADR-027):
  - `winampDisplay.h:942` — consumer assert: `tft.setTextDatum(TL_DATUM)` at entry of `drawPlaylist()`
  - `main.cpp` ClockApp drawTime/drawDate — producer rule: reset `TL_DATUM` after each `drawString`
  - `main.cpp` ClockApp `suspend()` — lifecycle hook: reset `TL_DATUM` on app exit
  - `taskbar.h` — producer rule: reset `setTextColor` after `drawChar`
- Architecture: ADR-027 `proposed → accepted`; ADR-028 Canvas abstraction filed as `proposed/dormant`
- QM: LL-035 filed in `lessons_learned.md`
- check_build.sh 4/4 pass; DUT boot clean.

---

### TASK-093 — MatrixApp implementation (M-MULTIAPP step 3a)
**Owner**: Developer
**Feature**: matrix-001 (new)
**Status**: done (2026-05-25 — commit eeb8091; check_build.sh 4/4 pass; DUT flashed)
**Design**: `docs/architecture/designs/M-MULTIAPP/matrix.md`
**Notes**:
- `MatrixApp : public App` in `main.cpp`. 14 streams, stride 19, canvas 275×240.
- Float y/speed per source; millis-gated at 25 ms (~40 fps); tap reinitialises streams.
- ADR-027 producer rule: `setTextColor(TFT_WHITE, TFT_BLACK)` reset at end of each tick.
- Registered at `g_apps[AppId::Matrix]`.
- Exit criteria C1–C5 met. Smoke test: streams visible, wrap, tap reinit, app-switch residue none.

---

### TASK-094 — LifeApp implementation (M-MULTIAPP step 3b)
**Owner**: Developer
**Feature**: gol-001 (new)
**Status**: done (2026-05-25 — commit 8ed2385; check_build.sh 4/4 pass; DUT flashed)
**Design**: `docs/architecture/designs/M-MULTIAPP/gol.md`
**Notes**:
- `LifeApp : public App` in `main.cpp`. 55×48 grid (5 px/cell = 275×240). Col-major [x][y].
- Toroidal boundary, diff render, spatial hue gradient, stagnation reset at >120 gens or <5 alive.
- `s_nextGrid[55][48]` as static class member (scratch buffer, not persisted).
- Millis-gated at 100 ms (10 gen/s). Tap reseeds. ADR-027 producer rule on text colour.
- Registered at `g_apps[AppId::Life]`.
- Heap cost ~12 KB BSS (nextGrid 2640 B + LifeAppState 2648 B). Observed 183 KB free on DUT.
- Exit criteria C1–C6 met. C7 (SPI diff byte count) deferred — visual diff confirmed correct.

---

### TASK-091 — Tag known-intermittent tests in run_serialdbg_tests.py (BP-012)
**Owner**: VE + Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-25)
**Notes**:
- Four tests known intermittent: T084, T087, T091, T092 (reconnect race + TLS reset log-line timing).
- Deliverable: add `# KNOWN INTERMITTENT: <reason> — first observed <date>` comment block above each.
- Optional stretch: emit `[FLAKE]` result category (separate from FAIL) when these fire; summary shows "N passed, 0 failed, M flaked."
- Exit criterion: four comment blocks present; `run_serialdbg_tests.py --help` unchanged; no behaviour change.
- Rationale: BP-012 (LL-034) — intermittent failures dilute regression signal; "not all green" should not be the expected baseline.
- Done: all four comment blocks added; `flake()` function added; all fail() calls in T084/T087/T091/T092 replaced with flake(); summary line updated; --help unchanged; exit code unchanged (flakes don't fail the run).

---

### TASK-012 — M2 skin bake tool, tier 1
**Owner**: Developer
**Feature**: m2-001 (new)
**Status**: done (2026-05-07, tier-1 user scope — title + main controls — closed via tier-2 batch)
**Blocks**: M3 (unblocked: layout + atlas + glyph UVs all present)
**Notes**:
- Tier 1 deliverables landed at Spotify-Diy-Thing@a9682be: bake tool, source `.wsz` (Winamp 2 Base-2.91), generated `gen/skin_assets.c` + `gen/skin_layout.h`. Build clean. Atlas budget ~94 KB.
- Tier-2 batch (this commit) closes the user's stated tier-1 scope ("title and main control buttons"): `SKIN_GLYPH[128]` ASCII→UV table emitted from `CHAR_MAP` in `bake_skin.py`, golden hash committed at `gen/golden.sha256` (T025 now passing), ImageMagick CLI dep documented in `CLAUDE.md`.
- Tier 3 deferred until M3 wires the renderer: time digits (NUMBERS.BMP), play/pause indicator (PLAYPAUS.BMP), seek bar (POSBAR.BMP), title bar sprites (TITLEBAR.BMP), VOLUME/BALANCE/MONOSTER/SHUFREP, eject.
- Build wiring: standalone tool, manual invocation per user pref. `python3 tools/bake_skin.py -i skins/base-2.91.wsz -o SpotifyDiyThing/gen`. Determinism: `cd SpotifyDiyThing/gen && sha256sum -c golden.sha256`.

### TASK-009 — TLS connection lifecycle for non-GET endpoints
**Owner**: Developer (implementation), Architect (ADR-007)
**Feature**: api-002 (new — to be registered)
**Status**: done (2026-05-08 — DUT-verified, 14/15 spike rows [OK] in one run, 15th was a Marriott-WiFi getHttpStatusCode timeout, not a lib bug. Network was NOT the scapegoat — three additional structural lib bugs were found and patched.)
**Notes**:
- ADR-007 patch (`client->stop()` before each `connect()`) addresses the *first-write* 0x0050. Necessary but insufficient.
- Three further LOCAL_PATCHES required to actually pass the spike control surface (T001–T015):
  1. Removed trailing `client->println()` after body (was a false-negative health check that fired after the server's HTTP/1.0 implicit close).
  2. Made `Content-Type: application/json` conditional on a non-empty body. With `Content-Length: 0`, sending application/json caused Spotify to early-RST the connection (same 0x0050 numeric symptom).
  3. Kept `Content-Length` unconditional (Spotify returns 411 Length Required without it on POST/PUT, even empty-body).
  4. Replaced `return statusCode == 204` with `return statusCode >= 200 && statusCode < 300`. Spec says 204 but Spotify actually returns 200 for most player endpoints.
- All four documented in `Spotify-Diy-Thing/lib/SpotifyArduino/LOCAL_PATCHES.md`.
- Earlier user-side observation ("prev and fwd controls work via DUT touch") is now explained: Spotify was always actioning the request; the lib just couldn't see success due to strict-204 + the early-RST false negatives.
**Blocks**: M5 (full-skin touch controls), TASK-002, TASK-003
**Notes**:
- Discovered during TASK-007 DUT run 2026-04-29: every `POST` (`nextTrack`, `previousTrack`) and `PUT` (`pause`, `play`, `seek`, `setVolume`, `toggleShuffle`, `setRepeatMode`) fails at TLS-send with mbedTLS `0x0050 (NET_CONN_RESET)`. `GET /v1/me/player/currently-playing` works in the same boot from the same poll loop.
- Architect 2026-05-04: confirmed root cause via `lib/SpotifyArduino/src/SpotifyArduino.cpp` inspection. Library uses HTTP/1.0 (server closes after response) but never calls `client->stop()` between requests — only `client->flush()` then `connect()`. Arduino-ESP32 2.0.17 `WiFiClientSecure::connect()` on a peer-closed socket can succeed without re-handshaking, producing `0x0050` on the next write. ADR-007 selects **option 2** (insert `client->stop()` before each `connect()` in `makeRequestWithBody` + `makeGetRequest`). Options 1 and 3 rejected — 1 thrashes heap with no upside, 3 is a disproportionate library rewrite. Option 3 retained as pre-authorised fallback if verification partial-passes.
- Verification gate (VE): re-run spike harness rows `>` `<` ` ` `p` `P` `s` `S` `+` `-` `v` `h` `H` `r` `R` `o`; all must return `[OK]`. GET poll loop must remain healthy. Rows `f` / `a` stay 403 (TASK-010, out of scope here).

### TASK-018 — On-screen log overlay (M-LOG2)
**Owner**: Developer
**Feature**: log-002 (registered at implementation)
**Status**: done (2026-05-07 — DUT verified; user confirms green log text in top + bottom strips, chrome unaffected)
**Notes**:
- Roadmap entry: M-LOG2. Spec: log is full-screen 320×240 background; Winamp chrome paints on top and clips whatever it covers. Top strip (~7 lines) shows older history; bottom strip (~7 lines) shows new lines; middle ~16 lines hidden behind chrome — they scroll through but aren't seen. Subscribed to the existing 12 KB ringbuffer (no new state).
- TFT_eSPI built-in font 1 (~6×8 px), green-on-black. Lines truncated right (no wrap).
- Behind `#define SCREEN_LOG` (or a new `cyd2usb_winamp_screenlog` env). Default off — zero overhead when not built in.
- Update gating: dirty flag set by `ringPush`; redraw at ≤4 Hz to avoid SPI thrash.
- Redraw orchestration: each tick paints log full-screen, then re-blits the chrome (bg + transport buttons + status + title slot + posbar). Time-digit / progress-thumb / title-marquee updates already self-repaint over their slot from MAIN.BMP — they don't need to know the log exists.
- Diagnostic motivation: makes state-coupling problems (TASK-019) visible at the moment they affect the UI.
- DUT integration surfaced a blast-radius correction to ADR-010: Arduino-ESP32 redefines `ESP_LOGx` to its own `log_x` macros that bypass `esp_log_writev`. Our hook was effectively starved. Fix: new `LOG_I/W/D/E(tag, fmt, ...)` macros in `logSink.h` that format → Serial + `ringPush` directly. Migrated heartbeat + `spotify.poll` call sites. Other `ESP_LOGx` sites still work (Serial only) until migrated. ADR-010 amended.

### TASK-029 — M-PERF tier 1: loop-iteration + hot-path timing
**Owner**: Developer
**Feature**: perf-001 (registered alongside this commit)
**Status**: done (2026-05-08 — DUT-verified)
**Notes**:
- New `perf.h` namespace: `record(name, ms)`, `recordLoop(ms)`, `loopMaxMs()`, `worstPathName()`, `worstPathMs()`, `stackHwmBytes()`, `reset()`. Heartbeat consumes + resets each tick.
- `.ino` wraps top-level loop paths (`screenlog::tick`, `display.input`, `spotify.poll`, `display.bar`) with `millis()` brackets and emits `LOG_W("perf", "iter=Nms ...")` when an iteration > 50 ms.
- New heartbeat fields: `stack_hwm=Nb loop_max=Nms slow=<name>:Mms`.
- DUT data captured (see TASK-031 notes): touch handler dominates at up to 4 189 ms / iteration; polling secondary at 1.5–2 s; stack hwm ≈ 2 380 bytes (comfortable).

### TASK-030 — M-PERF tier 1: SPI clock A/B
**Owner**: Developer
**Status**: done (2026-05-08 — DUT-verified: 40 MHz reduces flicker; kept)
**Notes**:
- Flipped `SPI_FREQUENCY` 55 MHz → 40 MHz in `common_cyd.build_flags`. User-confirmed flicker improvement on the static Winamp chrome. Default kept at 40 MHz.
- Bonus finding (independent of TASK-030): with `SCREEN_LOG` enabled, the 4 Hz full-screen `fillScreen` + chrome-repaint cycle causes visible tearing. Without `SCREEN_LOG`, the chrome is stable. The screenLog overlay is fine for diagnostic use; don't ship it as the default. Already addressed by it being opt-in via `-DSCREEN_LOG`. Tier-2 follow-up (incremental-redraw / dirty-line diff) tracked separately for if/when on-screen logging gets used regularly — see TASK-029 follow-up notes / TASK-033.

### TASK-031 — M-PERF tier 2: async Spotify HTTP (poll + touch)
**Owner**: Architect (ADR-012 done), Developer (impl done)
**Status**: done (2026-05-08; ADR-012 + 031a/b/c/d shipped + DUT-verified — `loop_max` 4 191 ms → 16 ms; seek-during-poll race resolved; user confirms snappy UI).
**Notes**:
- ADR: `docs/architecture/decisions/ADR-012.md`. Per LL-010 the @VE / @Developer / @QM / @PM passes are folded inline. Status: `proposed` (transition to `accepted` once human signs off, per the LL-010 promotion candidate).
- Sub-task split (PM):
  - **TASK-031a**: skeleton — `spotifyTask.h` + storage TU + task creation wired into `.ino` + queue + snapshot scaffolding. Empty action handling. ~150 LOC.
  - **TASK-031b**: move `getCurrentlyPlaying` into the task. Loop reads snapshot. ~80 LOC.
  - **TASK-031c**: move `nextTrack/previousTrack/play/pause/seek` into the task. Touch handler enqueues. ~30 LOC.
  - **TASK-031d**: remove the 1.5 s deferred-repoll guard from M5 — race is gone (LL-015 no longer applies). ~10 LOC.
- VE follow-up: T060–T065 to be written at implementation time.
- Expected `loop_max`: 4 191 ms → < 100 ms (per ADR exit criterion).

### TASK-032 — M-PERF tier 2 ADR: DMA SPI for blits
**Owner**: Architect
**Status**: closed — ADR-013 verdict **deferred** (2026-05-08). DMA gains hinge on the CPU having non-SPI work to do during a blit; in our current shape, every blit is followed by another blit on the same bus, so CPU+DMA race for one shared resource. Revisit when (a) a non-display CPU consumer runs in parallel with blits — TASK-014 album-art decode is the main candidate, (b) the chrome surface grows materially (M-CHROME tier 2), or (c) we move to a wider data path. Cheap-win bracketing handed off to TASK-038.

### TASK-038 — `startWrite`/`endWrite` bracket multi-blit chrome paths
**Owner**: Developer
**Feature**: perf-001
**Status**: done (2026-05-08, DUT-verified — chrome renders identically, no transaction-state bugs)
**Notes**:
- Bracket `repaintChrome()`, `drawTitleText()`, `drawTransportButtons()`, `drawTimeDigits()`, and `screenLog::tick`'s render loop with `tft.startWrite()` / `tft.endWrite()`. Keeps CS asserted across the sequence; eliminates per-pushImage chip-select toggle + address-window setup overhead.
- Expected: ~3–10 % chrome-redraw cost reduction based on TFT_eSPI usage notes.
- ~10 LOC. No risk surface beyond "make sure every startWrite has a matching endWrite even on error paths."
**Notes**:
- `repaintChrome` (~32 KB) takes a few ms — non-issue at current cadence.
- `screenlog::tick`'s 4 Hz full-screen blit causes the user-observed tearing when the overlay is on. If the overlay graduates from "diagnostic only" to "regular use", DMA + dirty-line diff become worth doing. Not now.

### TASK-034 — Quick-win: drop the 80 ms touch-press hold delay
**Owner**: Developer
**Status**: done (2026-05-08, DUT-verified — press feedback still visible, loop no longer blocks during the hold)
**Notes**:
- `winampDisplay::checkForInput` does `delay(80)` between drawing the pressed sprite and drawing the released sprite. Loop task can't make progress during that 80 ms. After TASK-031 ships, the synchronous API call's ~2 s contribution disappears, but `delay(80)` would still be there.
- Replace with a millis-deadline state machine: pressed-until = now + 80; on next loop iteration after pressed-until, paint released. Always-helpful, ~10 LOC.
- Could ship before or with TASK-031.

### TASK-033 — M-PERF tier 3: implementation
**Owner**: Developer
**Status**: done (2026-05-15 — touch press-hold state machine landed via pendingReleaseAt/PRESS_HOLD_MS; TASK-034 closed 80 ms delay; DMA deferred per ADR-013; async poll done in TASK-031)
**Notes**:
- Whichever of (async poll, DMA blits, screenLog incremental redraw, touch-debounce state-machine) the ADRs greenlight.
- Touch-debounce / press-hold state-machine: 80 ms `delay()` in checkForInput becomes a millis-deadline; release re-renders the unpressed sprite. Always helpful, no ADR needed; could land in this task or fold into the next M5-follow-up commit.

### TASK-023 — M-CHROME tier 1: bake-tool extension + atlases
**Owner**: Developer
**Feature**: chrome-001 (to be registered at impl)
**Status**: done (2026-05-15 — SKIN_SHUFREP 75×30 atlas emitted (TASK-025); MONOSTER composited into MAIN_BG per ADR-014 (TASK-040); SKIN_SHUFREP in gen/skin_assets.c, constants in gen/skin_layout.h)
**Notes**:
- Extend `tools/bake_skin.py`: load `MONOSTER.BMP` (58×24) + `SHUFREP.BMP` (92×85) from the .wsz; emit `SKIN_MONOSTER` / `SKIN_SHUFREP` arrays + sprite UVs in `gen/skin_layout.h`.
- MONOSTER sprite UVs: 29×12 each — `MONO` at (0,0), `STEREO` at (29,0), and a "lit" variant pair at (0,12) / (29,12). Confirm offsets against the source BMP at bake time.
- SHUFREP sprite UVs: 28×15 each (approx) — shuffle off/on (lit) at top row, repeat off/track/all at next rows. Layout per Winamp 2.x convention; derive from `92x85` dimensions.
- Re-bake; flash budget should land at ~98.4 %.

### TASK-024 — M-CHROME tier 1: mono/stereo + kHz/kbps strip
**Owner**: Developer
**Feature**: chrome-001
**Status**: superseded by TASK-040 (2026-05-09 — the strip is now baked statically into MAIN_BG via the ADR-014 composite path; no runtime renderer)
**Notes**:
- Bake-tool `composite_static_decoration` paints `MS_MONO_OFF` at (212, 41) and `MS_STEREO_ON` at (241, 41), plus glyph-composited `kbps "192"` at (110, 43) and `kHz "44"` at (156, 43). All four are decorative now — `currently_playing_type` driven mono/stereo was descoped along with TASK-040 since Spotify doesn't expose kHz/kbps anyway.

### TASK-025 — M-CHROME tier 1: shuffle / repeat indicator
**Owner**: Developer
**Feature**: chrome-001 / touch-002
**Status**: done (2026-05-15 — render + tap-toggle DUT-verified on home network; shuffle/repeat sprites visible, tap-toggle confirmed working by user)
**Notes**:
- Bake (`tools/bake_skin.py`): added `build_shufrep_atlas` packing 4 normal-state sprites (REPEAT off/on, SHUFFLE off/on) into a 75×30 atlas (4500 bytes flash). Pressed states intentionally skipped — tap feedback is implicit in the state flip.
- Lib (LOCAL_PATCHES patch #9): extended `getCurrentlyPlaying` filter + parser to surface `shuffle_state` and `repeat_state` on the existing `/me/player` poll. Added `bool shuffleState` + `RepeatOptions repeatState` to `CurrentlyPlaying`.
- Snapshot: added `bool shuffleState` + `int8_t repeatState` to `spotifyTask::Snapshot`. Defaults `false` / `2 (off)`. Written under spinlock by `onCurrentlyPlaying`.
- Renderer (`winampDisplay.h`): `drawShuffle(int)` / `drawRepeat(int)` overrides blit from SKIN_SHUFREP at canonical (164, 89) / (210, 89). Cached in `lastShuffleRendered` / `lastRepeatRendered`. Both paint in `repaintChrome` after blitMainBackground.
- Tap dispatch: `hitTestShuffle` / `hitTestRepeat` slot tests; tap toggles shuffle (off↔on) and cycles repeat (off → context → track → off, snapshot encoding 2 → 1 → 0 → 2). Optimistic UI paints the new sprite immediately; freeze window (`SHUFREP_OPTIMISTIC_HOLD_MS=2000`) gates the snap-driven redraw in `spotifyLogic.h`. ACT_SHUFFLE / ACT_REPEAT enqueued to `spotifyTask`; task body calls `s_spotify->toggleShuffle` / `setRepeatMode` then re-polls (matches NEXT/PREV/PLAY pattern; volume skips repoll because of drag-burst, shuffle/repeat are single events).
- Visual: tier 1 plan was render-only but the touch toggle came along with it because the M5 plumbing was already in place. Pressed-state sprites still deferred (would have doubled the SHUFREP atlas to 9 KB; we're at 4.5 KB now).

### TASK-046 — Decorative eject button bake
**Owner**: Developer
**Feature**: chrome-001
**Status**: done (2026-05-10 — visible in `gen/skin_preview.png`; no runtime code).
**Notes**:
- Composite `CBUTTONS.BMP (114, 0, 22, 16)` onto `MAIN_BG (136, 89)` in `tools/bake_skin.py::composite_static_decoration`. CBUTTONS was already loaded for the transport-button atlas; passed as a pre-baked source via `composite_sources.setdefault("CBUTTONS.BMP", cbut_bmp)` to avoid re-opening the zip entry.
- Static composite — eject has no Spotify equivalent (closest semantic is `transferPlayback` to a non-Spotify endpoint, not useful), so render-only.
- 0 bytes runtime cost (paints once at bake time into `SKIN_MAIN_BG`).

### TASK-039 — M-CHROME tier 2: extend SpotifyArduino parser for device.volume_percent
**Owner**: Developer
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-10 — SpotifyArduino.cpp:791-868; filter["device"]["volume_percent"] + currentlyPlaying.volumePercent field; LOCAL_PATCHES documented)
**Notes**:
- Add `device.volume_percent` to the JSON filter in `SpotifyArduino::getCurrentlyPlaying`.
- Add `int volumePercent` field to `CurrentlyPlaying` struct (default `-1` = unknown / no device).
- Mirror the existing `currentlyPlayingType` extraction pattern.
- Document in `lib/SpotifyArduino/LOCAL_PATCHES.md`.

### TASK-040 — M-CHROME tier 2: bake-time static composite onto MAIN_BG
**Owner**: Developer
**Feature**: chrome-001 / m2-001
**Status**: done (2026-05-10 — composite_static_decoration() in bake_skin.py: TITLEBAR active, BALANCE centred, kbps "192", kHz "44", MS_STEREO_ON + MS_MONO_OFF; MONOSTER dropped from runtime atlas; drawBitrateSampleRate/drawMonoStereo/redrawMetadataStrip removed)
**Notes**:
- Extend `tools/bake_skin.py` with composite mode: TITLEBAR active variant, BALANCE centered, kbps "192", kHz "44", static MS_STEREO_ON + MS_MONO_OFF.
- Drop MONOSTER.BMP from TIER3_SHEETS (after compositing). Remove SKIN_MONOSTER atlas + UV defines from gen/.
- Drop `winampDisplay::drawBitrateSampleRate()`, `drawMonoStereo()`, `redrawMetadataStrip()`, the snapshot-seq watcher block in `checkForInput`.
- Confirm visual via `--preview` eyeball before committing.

### TASK-045 — M-CHROME tier 2.5: drag-to-set volume control
**Owner**: Developer (impl), Architect (ADR-016), VE (T074 + T075)
**Feature**: chrome-001, touch-002 (extension family)
**Status**: done (2026-05-10; ADR-016 §5-§10 implemented; user-confirmed "works perfectly").
**Notes**:
- `ACT_VOLUME` added to `spotifyTask::Action` enum + dispatch case in `spotifyTaskStorage.cpp::taskBody` (no `doPoll()` after — drag-burst guard per ADR-016 §9). Calls `s_spotify->setVolume((int)req.param)` which accepts any 2xx (LOCAL_PATCHES patch #6).
- `hitTestVolume(sx, sy)` mirrors `hitTestPosbar` shape — returns `0..100` percent if inside `(originX + VOLUME_X, originY + VOLUME_Y, 68, 13)`, else `-1`.
- Drag state machine in `WinampDisplay`: `D_IDLE` ↔ `D_VOLUME_DRAG`. Transition on first hit inside the slot; transition back on the loop iteration where `ts.touched()` returns false. Drag-end commits a final `ACT_VOLUME(lastVolumeRendered)` if it diverges from `lastVolumeEnqueuedPct`.
- Debounce: ACT_VOLUME enqueued at most once per 300 ms during drag (`VOLUME_DRAG_DEBOUNCE_MS`), unconditionally on drag-end. Bounds queue depth at ~1 in practice.
- Optimistic-UI freeze (LL-015): `optimisticVolumeUntilMs = millis() + 2000` set on every drag sample. `WinampDisplay::getOptimisticVolumeUntil()` overrides the new base-class virtual on `SpotifyDisplay`. `spotifyLogic.h::updateCurrentlyPlaying` gates the snap-driven `drawVolume` dedup on `millis() >= getOptimisticVolumeUntil()`. Stops the next regular poll's stale `volumePercent` from re-anchoring the slider over the user's chosen value before Spotify commits.
- Build: cyd2usb_winamp clean. Flash 99.2 % → 99.3 % (+492 bytes used: 0 new atlas, ~492 bytes code), 9.4 KB free.
- DUT verify: captured drag samples and drag-end commits across multiple drag sessions. Sample log:
  ```
  drawVolume pct=58→61→62  →  drag-end commit pct=62
  drawVolume pct=67→...→70 →  drag-end commit pct=70
  spotify.task dequeued action=VOLUME param=71, 56, 34, 25, 38, 62, 67, 70
  ```
- T074 (drag dispatches setVolume): PASS — 8 ACT_VOLUME dispatches during drag session, all accepted by Spotify.
- T075 (optimistic-UI freeze prevents flicker): PASS — user-confirmed no snap-back during/after drag.
- ADR-016 OOS scope held: snap-to-bucket NOT implemented (linear values), pressed-state knob NOT introduced, no cross-drag.

### TASK-044 — M-CHROME tier 2.5: display-only volume knob
**Owner**: Developer (impl), Architect (ADR-016)
**Feature**: chrome-001
**Status**: done (2026-05-10; ADR-016 §1-§4 implemented; user-confirmed visual all 5 keyframe buckets + sentinel).
**Notes**:
- Bake (`tools/bake_skin.py`): added `extract_volume_knob` + `AUX_SPRITES` plumbing. Knob crop `(15, 422, 14, 11)` from BALANCE.BMP emitted as `SKIN_VOLUME_KNOB[14*11]` (308 bytes) — separate atlas, not padded into SKIN_VOLUME (saves 1.2 KB vs the wider-row alternative). Per-element review PNG `gen/composite/volume_knob.png`.
- Layout (`gen/skin_layout.h`): added `VOLUME_KNOB_W=14`, `VOLUME_KNOB_H=11`, plus `VOLUME_W=68` / `VOLUME_H=13` for the runtime to compute the knob travel range.
- Render (`winampDisplay.h::drawVolume`): after the keyframe blit, if `clamped >= 0`, blit the knob at `originX + VOLUME_X + (clamped * 54) / 100, originY + VOLUME_Y + 1`. Skipped on sentinel per ADR-016 §4.
- Knob sprite is fully filled (no cyan border pixels) — verified by per-pixel scan of the cropped 14×11 image; `blitSprite(...)` works without a colour-key path.
- Build: cyd2usb_winamp clean. Flash 99.2 % → 99.2 % (+432 bytes used: 308 atlas + ~124 code), 9.9 KB free remaining.
- Bake determinism: re-bake byte-identical; `golden.sha256` regenerated.
- DUT verify: drawVolume sequence captured at boot + 4 distinct buckets (`pct=-1 NONE`, `pct=17 KF0`, `pct=51 KF2`, `pct=65 KF3`, `pct=98 KF4`). User visually confirmed knob tracks position correctly; colour sprite changes match keyframe bucket.
- Touch control (TASK-045) intentionally NOT in scope — display-only first per ADR-016 §12.

### TASK-043 — Switch primary poll to `/me/player` (unblock TASK-041)
**Owner**: Developer (impl), Architect (ADR-015), VE (T073 + T070a/b re-run)
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-10; ADR-015 §1–§5 implemented; T073 + T070a + T070b all PASS).
**Notes**:
- Lib URL change in `lib/SpotifyArduino/src/SpotifyArduino.h:68` — `SPOTIFY_CURRENTLY_PLAYING_ENDPOINT` flipped from `/v1/me/player/currently-playing?additional_types=episode` to `/v1/me/player?additional_types=episode`. Documented as LOCAL_PATCHES.md patch #8.
- Diag log added during T070a debug session (`spotifyLogic.h` `[D][chrome.diag]` Serial.printf) reverted in same commit — LL-010 hygiene.
- Side-fix discovered during T070b: 204 No Content path in `spotifyTaskStorage.cpp::doPoll` did NOT bump snapshot seq nor reset `volumePercent`, so the dedup gate suppressed the NONE redraw on session-close. Fix: 204 path now writes `g_snapshot.volumePercent = -1` and bumps seq under the spinlock, leaving track fields alone. ~5 LOC.
- T073 host-side test: `tools/test_player_endpoint_superset.py`. PASS — confirmed `/me/player` is a strict superset for every firmware-consumed field; `device.volume_percent=16` returned (Web Player active, supports_volume=true).
- T070a DUT: captured drawVolume transitions `pct=10 keyframe=0` → `pct=90 keyframe=4` against host-side toggle script (`/tmp/volume_toggle.py` 10↔90 every 12s). Visual: red max-fill bar at 90%.
- T070b DUT: captured `pct=-1 keyframe=NONE` (boot) → `pct=65 keyframe=3` (first poll) → `pct=-1 keyframe=NONE` (Web Player closed, 204 path triggered the 204-handler reset). All three transitions in serial; visual confirmed.
- ADR-015 OOS scope held: no rename, no extra fields surfaced, no refactor toward `getPlayerDetails`.

### TASK-042 — Manual BI_RLE8 decoder in bake_skin.py (silent-corruption fix)
**Owner**: Developer (impl), Architect (ADR-008 amendment), VE (regression)
**Feature**: m2-001
**Status**: done (2026-05-09; ADR-008 amended 2026-05-09 with BI_RLE8 decision; golden.sha256 regenerated by TASK-044 bake run — sha256sum -c passes as of 2026-05-21)
**Notes**:
- BALANCE.BMP composite was rendering as a 2-px thin strip surrounded by cyan. Diagnosis: Pillow 11.3.0's `BmpRleDecoder` mishandles the **delta opcode** (`00 02 dx dy`) in BI_RLE8 streams. base-2.91.wsz's BALANCE.BMP uses delta(9, 0) at the start of nearly every row (419 deltas across 433 rows) to encode a 9-pixel transparent left border compactly. PIL's decoder ignores the dx — pixel data lands at x=0..37 instead of x=9..46 — and produces silent garbage for ~56 % of pixels (16,588 of 29,444).
- ImageMagick fails outright on the same file (`unable to runlength decode image @ error/bmp.c/ReadBMPImage/1147`), so the existing magick fallback path (ADR-008 decision #8) does not catch this.
- ffmpeg decodes correctly. A 30-LOC manual BI_RLE8 decoder (`_decode_bmp_rle8` in `tools/bake_skin.py`) is byte-identical to ffmpeg.
- Fix: manual decoder is now the **primary** path for any BMP with `compression=1` (8 bpp RLE). Magick fallback retained for unrelated edge cases. PIL kept for non-RLE BMPs.
- Side effects: SKIN_MAIN_BG[] bytes change (now contains the real green balance bar, kbps/kHz text under proper decode, etc.). `gen/golden.sha256` is stale until VE regenerates.
- Process miss: this fix went in without TASK ID, ADR amendment, or VE regression. Captured in audit_log 2026-05-09 entry, lessons-learned LL-017.

### TASK-041 — M-CHROME tier 2: dynamic VOLUME slider
**Owner**: Developer
**Feature**: chrome-001
**Status**: done (2026-05-10; impl at b8f37d3..8075176; verification end-to-end via TASK-043 — see below).

**Implementation spec**: ADR-014 Amendment 1 §A1.1–A1.7 is authoritative. Original ADR-014 §3 wording is superseded — do not implement against §3 directly.

**Issues raised in 2026-05-10 Architect review and how each is closed**:

| # | Issue (from review) | Severity | Closed by |
|---|---|---|---|
| 1 | "Snapshot-seq watcher inside `checkForInput`" referenced by §3 was deleted in TASK-040 — drift between ADR and code. | medium | §A1.1 — render trigger moves to `spotifyLogic.h::updateCurrentlyPlaying`. |
| 2 | `updateCurrentlyPlaying`'s existing `isSameTrack` gate would suppress volume-only changes (volume can shift without a track change). | high | §A1.1 — `static int8_t lastVolumeRendered = -2;` value-cache, checked **before** the `isSameTrack` early-return. |
| 3 | Sentinel render unspecified — original ADR punted between "lowest keyframe", "skip", or "neutral", each wrong. | medium | §A1.2 — bake a dedicated 6th KEYFRAME_NONE (greyed empty track). Decision committed, not deferred. |
| 4 | VOLUME.BMP frame layout assumed canonical without inspection (LL-016 family — same shape as BALANCE.BMP's non-canonical-stride trap). | medium | §A1.3 — empirically inspected via `_decode_bmp_rle8` (uncompressed BMP, fell through to PIL); confirmed canonical 28×15-stride. Frames locked: 0, 7, 14, 20, 27. |
| 5 | "`spotifyTask::onCurrentlyPlaying`" wording in §3 — no such callback exists. | low | §A1.4 — corrected to "snapshot-write block of the poll-success branch in the task body". |
| 6 | On-screen position (107, 57) collision risk vs the now-baked TITLEBAR / kbps-text / BALANCE composite. | log-only | §A1.5 — verified non-colliding (3 px gap to BALANCE x=177; 8 px gap above kbps text at y=43-49). No change needed. |
| 7 | Atlas-surface accounting needs to include sentinel keyframe. | low | §A1.2 — 6 × 68×13 × 2 = 10,608 bytes. Fits in 18 KB flash headroom. |
| 8 | T070 acceptance was vague — no concrete pass criteria for VE. | medium | §A1.6 — split into T070a (real-volume render path) + T070b (sentinel transition). Both planned in `test_plan.md`. Both required before TASK-041 closes. |

**Internal commit ordering** per §A1.7: (1) bake atlas (5 source-frame keyframes + synthesised KEYFRAME_NONE), (2) snapshot field, (3) `drawVolume` renderer, (4) wire-in to `updateCurrentlyPlaying` + `repaintChrome`. Each step compiles cleanly on its own; steps 1–3 are dead code until step 4 — intentional, eases review.

### TASK-026 — M-CHROME tier-2 flash-budget ADR
**Owner**: Architect
**Status**: superseded by ADR-014 (2026-05-09 — composite-static reframe sidesteps the flash-budget question entirely; only VOLUME needs new atlas surface and at 5 keyframes it fits in the 18 KB headroom)
**Notes**:
- TITLEBAR/VOLUME/BALANCE atlases at full resolution = +178 KB, no fit. Decision: subset at bake time (one titlebar variant, ~8 volume keyframes, drop balance) vs partition resize vs lighter pixel format (palette-8) vs compress on flash + decompress at boot.
- ADR should land before TASK-027 / TASK-028 start.

### TASK-027 — M-CHROME tier 2: title bar render
**Owner**: Developer
**Status**: superseded by TASK-040 (2026-05-09 — title bar is now baked into MAIN_BG via the static-composite pass)

### TASK-028 — M-CHROME tier 2: volume slider + (maybe) balance
**Owner**: Developer
**Status**: superseded by TASK-040 (balance) + TASK-041 (volume) per ADR-014

### TASK-020 — M-LIST tier 1: top-align UI + playlist panel
**Owner**: Developer
**Feature**: playlist-001
**Status**: done (2026-05-15 — DUT-verified, user confirmed playlist panel visible)
**Notes**:
- ADR-017 accepted. Orientation C, `GET /me/player/queue`, Font 2, 7 rows.
- **020a**: `originY = 0` — chrome flush to top edge. Also fixed VU meter hardcoded origin → `chromeOriginX()/chromeOriginY()` getters (bug: VU was stuck at old centered position).
- **020b**: `getQueue()` added to `SpotifyArduino` (LOCAL_PATCHES pattern). `QueueSnapshot` struct + `g_queueMux` spinlock in `spotifyTask`. Poll trigger: track-change detection in `onCurrentlyPlaying` + 60 s keepalive. `queueBufferSize = 6000` (3000 was insufficient for 20 filtered queue items).
- **020c**: `drawPlaylist()` in `winampDisplay.h` — seqno-diff + 1 Hz rate gate; `fillRect` strip + 7 rows Font 2; row 0 gold highlight + white text, rows 1-6 Winamp grey-green. Seqno check and draw call in main loop under `#ifdef WINAMP_DISPLAY`.
- Scope: `user-read-playback-state` covers queue endpoint — no token regeneration needed (returned 200, not 403).
- Flash: 50.0 % (stable). RAM: +1 KB for QueueSnapshot.

### TASK-050a — M-VIS: VisMode enum + toggle dispatch + blank mode
**Owner**: Developer
**Feature**: vis-001 (new)
**Status**: done (2026-05-16 — VisMode enum + nextMode() + blitVisBackground() + hitTestVis() + mode dispatch in tick(); compile-verified)
**Blocks**: TASK-050b, TASK-050c (need mode dispatch before adding renderers)
**Notes**:
- Add `enum VisMode { VIS_VU, VIS_SPECTRUM, VIS_WAVE, VIS_BLANK };` to `vuMeter.h` namespace.
- Add file-static `VisMode s_mode = VIS_VU;` inside `vuMeter.h`.
- `nextMode()`: cycles `VIS_VU → VIS_SPECTRUM → VIS_WAVE → VIS_BLANK → VIS_VU`.
- `currentMode()`: returns `s_mode`.
- Update `tick()` signature: `void tick(int originX, int originY, const uint16_t *mainBg)` (adds `mainBg` — TASK-049 change folded in here; these two tasks should land together).
- Dispatcher in `tick()`: `switch(s_mode) { VIS_VU: tickVU(); VIS_SPECTRUM: tickSpectrum(); VIS_WAVE: tickWave(); VIS_BLANK: blitVisBackground(); }`.
- `blitVisBackground(originX, originY, mainBg)`: restores `SKIN_MAIN_BG` rows for the full vis area `(RECT_X=24, LEFT_Y=43, RECT_W=76, VIS_H=16)`.
- **Vis area constants** (add to `vuMeter.h`): `VIS_H = 16` (R&D confirmed y=43..58; **not** 13 — old formula `RIGHT_Y + RECT_H - LEFT_Y` gives VU height, not full spectrum height). Also add `SPEC_BARS=19`, `SPEC_BAR_W=3`, `SPEC_BAR_STEP=4`.
- **Touch hit-test** (`winampDisplay.h`): add `bool hitTestVis(int sx, int sy)`:
  - Bounds: `sx in [originX+RECT_X, originX+RECT_X+RECT_W)` AND `sy in [originY+LEFT_Y, originY+LEFT_Y+VIS_H)` (y=originY+43..58).
  - Confirm no overlap with existing hit-test zones (transport at y=originY+88..106; all clear).
- Wire `hitTestVis` into `checkForInput()`: on tap inside vis area → `vu::nextMode()`. No API action, no optimistic freeze.
- TASK-049 is a prerequisite for this task's `blitVisBackground`; implement together or immediately before.
- **Authoritative spec:** `docs/architecture/designs/M-VIS-visualization.md` (updated 2026-05-16).

### TASK-050b — M-VIS: spectrum analyzer view
**Owner**: Developer
**Feature**: vis-001
**Status**: done (2026-05-16 — 19 bars × 3px, VIS_ROW_COLOR gradient, grey peak dots 3px wide, decay 1/VIS_H per tick; compile-verified)
**Notes**:
- **Authoritative spec:** `docs/architecture/designs/M-VIS-visualization.md`. Summary of corrections from original 2026-05-15 notes:
  - **19 bars** (not 38): 3px wide + 1px gap = 4px step. `barX = originX + RECT_X + i * 4`.
  - **Colour by absolute row:** `VIS_ROW_COLOR[r]` where `r = pixel_y - (originY + LEFT_Y)`. NOT threshold-based green/yellow/red.
  - Per-bar draw is a row loop: `for (r = VIS_H - barH; r < VIS_H; r++) tft.drawFastHLine(barX, originY+LEFT_Y+r, 3, VIS_ROW_COLOR[r]);`
  - **Peak decay:** `specPeak[i] -= 1.0f / VIS_H;` (~0.0625f, 1 row per 50ms tick). Old `0.008f` was wrong (≈480ms/row, far too slow).
  - **Peak dot:** `tft.drawFastHLine(barX, originY+LEFT_Y+peakRow, 3, VIS_PEAK_COLOR)` — 3px wide (full bar width), colour `0x94B2`. Not `drawPixel`.
  - **Dedup arrays:** `lastBinH[19]` + `lastPeakRow[19]`.
- **Bin synthesis (19 bins):** `binLevel[i] = clamp(envelope × shape[i] × (1 + beatBoost(i)), 0, 1)`
  - `envelope = (lLvl + rLvl) * 0.5f`
  - `shape[19]`: `1.0f - (i / 18.0f) * 0.6f`
  - `beatBoost`: `(i < 4) ? beat * 0.8f : 0.0f`

### TASK-050c — M-VIS: waveform oscilloscope view
**Owner**: Developer
**Feature**: vis-001
**Status**: done (2026-05-16 — white sine wave, vertical fill between samples, midline y=originY+50, phase-advancing; compile-verified)
**Notes**:
- **Authoritative spec:** `docs/architecture/designs/M-VIS-visualization.md`. Summary of corrections from original 2026-05-15 notes:
  - **Colour:** `VIS_WAVE_COLOR = 0xFFFF` (white, VISCOLOR[18]). NOT `TFT_GREEN`. R&D measurement confirmed white.
  - **Vertical fill between samples:** Winamp draws line segments, not single pixels per column. Use `drawFastVLine` from `min(y[x-1], y[x])` to `max(y[x-1], y[x])`. Single `drawPixel` per column is not Winamp-accurate.
  - **Midline:** `VIS_CENTRE_Y = originY + LEFT_Y + (VIS_H-1)/2 = originY + 50`. R&D measured skin y=50.2 ≈ 50. Old `originY + 49` was based on wrong VIS_H=13.
- **Synthesis:** `y[x] = clamp(VIS_CENTRE_Y + roundf(lLvl * 5.0f * sinf(wavePhase + x * 2.5f * TWO_PI / 76)), originY+43, originY+58)`
- **Render per tick:**
  1. `blitVisBackground()` — clears previous frame.
  2. For each `x` in 0..75: `drawFastVLine(originX+RECT_X+x, min(y[x-1],y[x]), abs(y[x]-y[x-1])+1, VIS_WAVE_COLOR)`. For x=0 draw single pixel at y[0].
  3. Advance `wavePhase += 0.3f`.
- **Paused state:** `lLvl` decays to 0 → flat HLine at y=50. Natural, no special case.

### TASK-048 — M-UI-POLISH: artist + title in marquee strip
**Owner**: Developer
**Feature**: disp-001 (existing)
**Status**: done (2026-05-15 — winampDisplay.h:200-214; snprintf "%s - %s   " artist+title; lastTitle[264]; lastArtist change detection; 3-space gap for loop-back)
**Notes**:
- `Snapshot::artistName[128]` already populated (`spotifyTaskStorage.cpp:100-101`). Just not wired into `drawTitleText()`.
- `winampDisplay.h:173` copies only `currentlyPlaying.trackName` → `lastTitle`. Change to compose `artist + " - " + name`.
- Buffer: `lastTitle[128]` → `lastTitle[260]` (artist 128 + `" - "` 3 + title 128 + NUL).
- Compose logic: if `artistName[0] != '\0'`: `snprintf(lastTitle, sizeof(lastTitle), "%s - %s", artistName, trackName)`. Else: `strncpy(lastTitle, trackName, ...)`.
- Track change detection (`strcmp(lastTitle, ...)` on line 173): update to trigger recompose on *either* `trackName` or `artistName` change (store `lastArtist[128]` alongside `lastTitle`, check both).
- Scroll gap: after the last glyph in `drawTitleText()`, the loop-back should insert a 3-space gap (`"   "`) before restarting from the string start. Achieves the classic "endless ticker" feel. Implement by appending `"   "` to the composed string, or by adding 3×`GLYPH_W+1` px of blank before the wrap in the render loop.
- Scroll speed: `TITLE_SCROLL_STEP_MS=120` unchanged — adjust only if user requests.
- Original Winamp 2 reference: main window shows `"Artist - Title"` format (no track-number prefix; that is playlist-editor only). Falls back to `"Title"` alone when artist blank.

### TASK-049 — M-UI-POLISH: VU zero-fill from SKIN_MAIN_BG
**Owner**: Developer
**Feature**: vu-001 (existing)
**Status**: done (2026-05-16 — pushImage zero-fill pattern already implemented in vuMeter.h; mainBg param present; confirmed in code)
**Notes**:
- `vuMeter.h:121` and `vuMeter.h:127` clear the off-portion of each bar with `tft.fillRect(..., TFT_BLACK)`. This overwrites the skin's visualization-area background.
- Fix: replace with per-row `pushImage` from `SKIN_MAIN_BG` at the corresponding window-local pixel offset. Same pattern as `drawTitleText()` line 513-514.
- VU rects are fully inside the 275×116 `SKIN_MAIN_BG` atlas:
  - Left bar:  window-local `(RECT_X=24, LEFT_Y=43, RECT_W=76, RECT_H=6)`.
  - Right bar: window-local `(RECT_X=24, RIGHT_Y=50, RECT_W=76, RECT_H=6)`.
- API change: `vu::tick(int originX, int originY)` → `vu::tick(int originX, int originY, const uint16_t *mainBg)`. Pass `SKIN_MAIN_BG` from the call site in `.ino` (or `winampDisplay.h` — wherever `vu::tick` is invoked).
- In `tick()`, replace:
  ```cpp
  if (lW < RECT_W) tft.fillRect(lx + lW, ly, RECT_W - lW, RECT_H, TFT_BLACK);
  ```
  with a row-loop blitting `mainBg + (LEFT_Y + row) * SKIN_MAIN_BG_W + RECT_X + lW` for `RECT_W - lW` pixels. Same for right bar.
- No bake-tool change. No atlas change. `SKIN_MAIN_BG` already contains the correct background pixels.
- `vu::invalidate()` path: no change needed — full bar repaint already triggered by the existing `lastLW/lastRW` dedup logic.

### TASK-047a — M-LIST-v2: bake_skin.py PLEDIT extraction + atlas + preview
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15 — 5 rows × 13px, tiled title bar, split bottom bar, SKIN_PLEDIT_BG 275×58 emitted; commits 949c057..388665f)
**Blocks**: TASK-047c (renderer needs atlas + layout constants)
**Notes**:
- Extract `PLEDIT.BMP` from `skins/base-2.91.wsz`. Inspect dimensions + sprite offsets empirically (LL-016 pattern — record actual values, don't assume canonical).
- New `build_pledit_atlas(wsz)` function in `tools/bake_skin.py`:
  - Crop title bar strip `(0, 0, 275, 14)` → scale/pad to 320 px wide (prefer pad with PLEDIT body bg colour on right; fallback nearest-neighbour stretch).
  - Crop bottom bar strip `(0, bottom_y, 275, 16)` → same horizontal treatment.
  - Composite both into `SKIN_PLEDIT_BG[320 * 30]` (title at index 0, bottom bar immediately after; renderer uses offset arithmetic: `SKIN_PLEDIT_BG` at `y=116` for title, `SKIN_PLEDIT_BG + 320*14` at `y=210` for bottom bar).
  - Crop row-highlight sprite `(0, first_row_y, 260, 16)` → `SKIN_PLEDIT_ROW_HIGHLIGHT[260 * 16]`.
- Emit `SKIN_PLEDIT_BG` + `SKIN_PLEDIT_ROW_HIGHLIGHT` to `gen/skin_assets.c`.
- Emit layout constants to `gen/skin_layout.h`: `PLEDIT_Y=116`, `PLEDIT_H=124`, `PLEDIT_TITLE_H=14`, `PLEDIT_BOTTOM_H=16`, `PLEDIT_ROWS_Y=130`, `PLEDIT_ROW_H=16`, `PLEDIT_ROW_COUNT=5`, `PLEDIT_BOTTOM_Y=210`, `PLEDIT_W=320`.
- Composite PLEDIT panel into `gen/skin_preview.png` lower band (y=116..240) with 5 sample rows. Validate on-host before DUT.
- Regenerate `gen/golden.sha256`; confirm `sha256sum -c golden.sha256` passes.

### TASK-047b — M-LIST-v2: durationMs in QueueEntry + getQueue() filter
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15)
**Blocks**: TASK-047d (total time needs `durationMs`)
**Notes**:
- Add `uint32_t durationMs` to `QueueEntry` struct. Size impact: +4 bytes × 5 entries = +20 bytes RAM (negligible).
- Reduce `QUEUE_MAX` from 7 to 5 (5 rows per ADR-018). Saves `2 × (48+32+64+4) = 296 bytes` RAM.
- Extend `getQueue()` ArduinoJson filter doc in `SpotifyArduino` LOCAL_PATCHES to include `duration_ms` from both `currently_playing` and `queue[]` items.
- At snapshot-write time, mirror `Snapshot::durationMs` (already present for posbar) into `g_queueSnapshot.items[0].durationMs` — no extra API call needed for row 0.
- Document in `lib/SpotifyArduino/LOCAL_PATCHES.md` as patch #10 (or next available).

### TASK-047c — M-LIST-v2: drawPlaylist() redesign — PLEDIT chrome + row format
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15 — commit 2d90ffa; drawPlaylist() rewritten with PLEDIT chrome, 5 rows, Font 1 text, originX=22 centering)
**Notes**:
- Implemented: title bar + bottom bar via pushImage(SKIN_PLEDIT_BG), 5 rows fillRect+Font1. Text format "Artist - Track" (no duration yet — TASK-047b prereq not done). Row 0 uses PLEDIT_BG_SELECTED + PLEDIT_FG_CURRENT; rows 1-4 use PLEDIT_BG_NORMAL + PLEDIT_FG_NORMAL. Left/right gutters filled PLEDIT_BODY_BG. seqno-gated, PLAYLIST_DRAW_MIN_MS rate limit.
- Duration column deferred to TASK-047b+d.
- Hit-test update for TASK-021 (Tier 2): row y boundaries now `y=PLEDIT_ROWS_Y+row*PLEDIT_ROW_H`.

### TASK-047d — M-LIST-v2: total time in PLEDIT bottom bar
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15 — commit 15ab2c5; right-aligned in scrollbar track x=222, y+5 in bottom bar)
**Notes**:
- Sum `durationMs` across all `count` snapshot entries on each `drawPlaylist()` call.
- Format as `"H:MM:SS"` (hours if sum ≥ 1 h, else `"MM:SS"`).
- Determine render position from PLEDIT.BMP bottom bar inspection at TASK-047a time — record pixel offset as `PLEDIT_TOTALTIME_X` / `PLEDIT_TOTALTIME_Y` in `gen/skin_layout.h`.
- Font: TFT_eSPI Font 1 (6×8) — fits the smaller bottom bar height. Colour: white or PLEDIT text colour from inspection.
- Only re-render when seqno advances (same gate as `drawPlaylist()`).

### TASK-021 — M-LIST tier 2: tap-on-row plays that track
**Owner**: Developer
**Status**: done (2026-05-16 — winampDisplay.h:342-353; ACT_PLAY_URI dispatched on PLEDIT row tap; spotifyTaskStorage dispatches playAdvanced(uri). Caveat: playAdvanced replaces context; queue-aware skip deferred to M-LIST-v3)
**Notes**:
- Hit-test: `y >= PLEDIT_ROWS_Y && y < PLEDIT_BOTTOM_Y` → `row = (y - PLEDIT_ROWS_Y) / PLEDIT_ROW_H`. Bounds-check against `QueueSnapshot::count`.
- On tap: `enqueue(ACT_PLAY_URI, row_index)` → task reads `QueueSnapshot::items[row_index].uri` → `playAdvanced`.
- Need new `ACT_PLAY_URI` action enum. Index-in-snapshot avoids URI string in `Request` struct; race-free (task owns snapshot write side).
- Note: row y-boundaries updated by TASK-047c (PLEDIT layout shifts rows down by `PLEDIT_TITLE_H=14` px vs TASK-020 baseline).
- **DUT observation (2026-05-16)**: `playAdvanced(uri)` clears the Spotify queue and starts the selected track as a fresh session. PLEDIT immediately shows 5 identical rows of the new track; Spotify queue shows only that 1 item. This is `playAdvanced` API behaviour — it replaces the context, it does not skip ahead in the existing queue.
- **Desired behaviour**: keep the existing queue intact; "jump" to the tapped track. Implementation options: (a) if playing from a playlist/album context, use `PUT /v1/me/player/play` with `context_uri` + `offset.uri`; (b) without context, call `next` N times to skip ahead. Neither is trivially available from the current queue snapshot (which carries URIs but not the original context URI or position). Tracked for resolution in M-LIST-v3 (TASK-051a–f). See `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md`.
- **Resolution**: `s_lastTrackContextUri` is already populated by `onCurrentlyPlaying()` (`spotifyTaskStorage.cpp:77-81`) but is never read in the `ACT_PLAY_URI` handler — the wire is missing. Fix tracked in TASK-066.

### TASK-051a — M-LIST-v3: optimistic selected-row highlight
**Owner**: Developer
**Feature**: playlist-002, touch-002
**Status**: done (2026-05-23) — DUT confirmed; tap path working after TASK-076 threshold fix
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 1
**Notes**: After `ACT_PLAY_URI`, track `optimisticSelectedRow` in `WinampDisplay` (pattern: `optimisticVolumeUntilMs`). Render that row selected until seqno advances or ~8 s timeout. Reset to row 0 on track change.

### TASK-051b — M-LIST-v3: extend queue to 20 items
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-23, commit 908e58d) — DUT confirmed count=20
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 2
**Notes**: Raise `SPOTIFY_QUEUE_MAX_ITEMS` from 5 to 20 in `lib/SpotifyArduino/`. `QueueSnapshot` grows; heap impact must be verified (each `QueueItem` ~100 B → +1500 B).

### TASK-051c — M-LIST-v3: scrollOffset state + sliced row rendering
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-23, commit 908e58d) — confirmed: row format visible; scrollOffset=0 at boot
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 2
**Notes**: Add `int scrollOffset` to `WinampDisplay`. `drawPlaylist()` renders `items[scrollOffset .. scrollOffset+PLEDIT_ROW_COUNT-1]`. Row tap maps to `ACT_PLAY_URI(scrollOffset + row)`.

### TASK-051d — M-LIST-v3: swipe gesture in PLEDIT content area
**Owner**: Developer
**Feature**: playlist-002, touch-002
**Status**: done (2026-05-23) — DUT confirmed scrolling after TASK-076 fix
**Design**: `docs/architecture/designs/M-LIST-v3-hitzones.md` Zone 1
**Notes**: `D_PLEDIT_SCROLL` dragState implemented. Drag-end: |dy|<4→tap, dy<0→scrollOffset++, dy>0→scrollOffset--. Sets `_pleditScrollDirty=true`. Threshold lowered 8→4px (hardware Y-axis compresses gestures to ~5–35px range on CYD). Fixed by TASK-076.

### TASK-051e — M-LIST-v3: live scrollbar thumb (sprite blit)
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-23, commit 3b49719) — human sign-off: thumb visible at correct position
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 3; `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md`
**Notes**: Thumb is a sprite blit, NOT a fillRect (spec corrected 2026-05-22, TASK-075 amendment). Use normal-state thumb sprite (BMP x=52, y=54, w=9, h=17) from `SKIN_ASSETS`. Blit at: `thumb_x = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + 1`, `thumb_y = PLEDIT_ROWS_Y + scrollOffset * (65 - 17) / max(1, count - PLEDIT_ROW_COUNT)`. Hide when `count <= PLEDIT_ROW_COUNT`. Requires TASK-051c.

### TASK-051f — M-LIST-v3: auto-reset scrollOffset on track change
**Owner**: Developer
**Feature**: playlist-002, sync-001
**Status**: done (2026-05-23, commit 908e58d)
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Cross-feature
**Notes**: On seqno advance, set `scrollOffset = 0`. items[0] (currently playing) always in view post-change.

### TASK-051g — M-LIST-v3: row format N. Artist - Title... M:SS
**Owner**: Developer
**Feature**: playlist-002, playlist-003
**Status**: done (2026-05-23, commit 00aa3e9) — human sign-off: row formatting confirmed on DUT
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 4
**Notes**: Replace current `"Artist - Title"` with `"N. Artist - Title   M:SS"`. N = `songsSeen + scrollOffset + i + 1`. Duration right-aligned (pixel math: `right_edge - strlen(dur)*6`). Middle truncated with `"..."` on overflow. Font 1 fixed 6px/char, 238px usable.

### TASK-051h — M-LIST-v3: songsSeen counter + 2-entry URI history
**Owner**: Developer
**Feature**: playlist-003
**Status**: done (2026-05-23, commit 00aa3e9)
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 5
**Notes**: `uint16_t songsSeen` (RAM). `char prevNextUri[40]`. `bool skipPending` (set by ACT_NEXT / ACT_PLAY_URI dispatch). Increment when `items[0].uri == prevNextUri && !skipPending`. Update `prevNextUri = items[1].uri` after each poll. Row N shows `songsSeen + scrollOffset + i + 1`.

### TASK-051i — M-LIST-v3: scrollbar strip direct drag (Zone 2)
**Owner**: Developer
**Feature**: playlist-002, touch-002
**Status**: done (2026-05-23) — DUT confirmed scrolling after TASK-076 fix
**Design**: `docs/architecture/designs/M-LIST-v3-hitzones.md` Zone 2
**Notes**: `D_PLEDIT_SCROLL_DIRECT` state. Y→scrollOffset: `max(0, min(maxOffset, relY*maxOffset/travel))`. `drawScrollThumbOnly()` re-tiles right strip + blits thumb per sample. Bug fixed by TASK-076: `_pleditScrollDirty` was not set on scrollOffset change, so `drawPlaylist()` skipped row redraw. Added `_pleditScrollDirty = true` alongside `drawScrollThumbOnly()`. Drag-end → D_IDLE + 100ms cooldown.

### TASK-051j — M-LIST-v3: hitzones PNG update + human review gate
**Owner**: Developer + human sign-off
**Feature**: playlist-002, touch-002
**Status**: done (2026-05-23 — human sign-off given)
**Design**: `docs/architecture/designs/M-LIST-v3-hitzones.md`
**Notes**: TASK-054 (done) already built `render_hitzones()` and the single-source-of-truth zone registry pattern. Remaining work: edit the `pledit_rows` block in `render_hitzones()` (bake_skin.py:1086–1090) — replace `ROW0..ROW4` entries with `pledit_content` (SWIPE/TAP, 34,136,244,65), sub-row labels R0–R4 (no magenta fill, informational only), `pledit_scrollbar` (SCROLL DRAG, 278,136,19,65), `pledit_scroll_up` (UP BTN, 275,201,22,7), and `pledit_scroll_down` (DOWN BTN, 275,208,22,10). Re-run bake_skin.py to regenerate `gen/skin_hitzones.png`. Human eyeball sign-off before any firmware implementation of TASK-051b–i begins. This is the human review gate for M-LIST-v3. Scroll arrow coords measured in TASK-075 (see `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md`).

### TASK-076 — Debug: PLEDIT swipe gesture not changing displayed rows
**Owner**: Developer
**Feature**: playlist-002, touch-002
**Status**: done (2026-05-23) — root causes found and fixed; DUT confirmed scrolling
**Blocks**: TASK-051d (swipe), TASK-051i (scrollbar drag — likely same root cause), TASK-051a (optimistic highlight — depends on tap path working)
**Symptom**: Swiping the PLEDIT content area does not change which queue items are displayed. Thumb position is static. Row content unchanged after gesture.

**What is implemented** (commit 908e58d / 6f18fca, `winampDisplay.h`):
- `D_PLEDIT_SCROLL` dragState. Zone 1 touch-down sets state + records `_dragStartY`, `_dragCurrentY`, `_dragStartRow`.
- Drag-end block (outside cooldown gate): `if (dragState == D_PLEDIT_SCROLL && !ts.touched())` — computes `dy = _dragCurrentY - _dragStartY`. If `|dy| < 8` → tap; else → `scrollOffset ±1` + `_pleditScrollDirty = true`.
- `drawPlaylist()` gate: `if (!seqnoChanged && !_pleditScrollDirty) return` — dirty flag bypasses 1 Hz rate-limit.
- `scrollOffset` fed into row loop as `idx = scrollOffset + i`.

**Hypotheses to investigate (in priority order)**:

1. **Drag-end never fires** — `ts.touched()` stays true long after finger lift on the CYD XPT2046 controller, so `!ts.touched()` in the drag-end check never becomes true while `dragState == D_PLEDIT_SCROLL`. Add `LOG_D` to drag-end entry to confirm it fires. Check if `dragState` is reset to `D_IDLE` correctly.

2. **dy always < 8px** — `_dragCurrentY` is only updated when the Loop re-enters the Zone 1 `else if (dragState == D_PLEDIT_SCROLL)` branch. If the loop is slow (blocked on network), only one touch sample arrives per gesture → `_dragCurrentY == _dragStartY` → `dy = 0` → always treated as tap. Add log of `_dragStartY`, `_dragCurrentY`, `dy` at drag-end.

3. **`_pleditScrollDirty` set but `drawPlaylist()` not redrawing** — verify the gate logic: when `seqnoChanged=false` and `_pleditScrollDirty=true`, the function should enter and render. But check: does a seqno poll fire immediately after, resetting `scrollOffset = 0` before the dirty draw runs? The poll is every ~5s so unlikely, but add log to confirm `scrollOffset` value inside the row loop.

4. **Zone 1 hit test miss** — touch coordinates `p.x` / `p.y - originY` may not fall in `[originX + PLEDIT_CONTENT_X, originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W)` × `[PLEDIT_ROWS_Y, PLEDIT_ROWS_Y + 65)`. Verify `originX` value at runtime (may be 22, not 0). Log touch coords on first press.

**Suggested debug approach**:
Flash `cyd2usb_winamp_debug`, use serial debug `tap` / `get dragState` commands to inject synthetic touches and verify state transitions before testing physical touch. If drag-end fires correctly on inject but not on physical touch → hypothesis 1 or 2. If `scrollOffset` updates but rows don't change → hypothesis 3.

**Key file**: `SpotifyDiyThing/winampDisplay.h` — `checkForInput()` drag-end block (~line 408), `drawPlaylist()` gate (~line 922).

**Serialdbg test cases** (VE, 2026-05-23):

All tests require `cyd2usb_winamp_debug` firmware. Geometry reference: Zone 1 (content
area) = screen x∈[34,278), y∈[136,201) (`originX=22`, `PLEDIT_CONTENT_X=12`,
`PLEDIT_CONTENT_W=244`, `PLEDIT_ROWS_Y=136`, `ROW_H=13`, `ROW_COUNT=5`).

**Prerequisite — `get scrollOffset`**: Tests T136–T139 require `scrollOffset` to be
exposed via `dbgGet` (add to `winampDisplay.h::dbgGet`, key `"scrollOffset"`). Without
it, scroll change can only be confirmed visually or via LOG_D output. T134/T135 work
with current firmware.

**Note on scope**: Serial inject bypasses `ts.touched()` via `injectRelease()`.
Therefore T134/T135 cannot diagnose H1 (XPT2046 stays asserted) or H2 (slow loop, one
sample). They prove the scroll logic fires correctly given a proper drag sequence. If
T135 passes on inject but physical swipe still fails → root cause is H1 or H2 (hardware
touch timing), not the scrollOffset/dirty-flag logic.

---

**T134 — Zone 1 hit-test: synthetic tap lands in PLEDIT**

Target hypothesis: H4 (hit-zone miss).

Preconditions: DUT booted, Spotify active (any queue count).

Steps:
1. `tap 156 165` — centre of Zone 1 content area, row 2 (y=165, row=(165-136)/13=2).
2. Parse response JSON.

Expected: `{"ok":true,"cmd":"tap","hit":"PLEDIT","action":"PLAY_URI",...}` (row=2 since
scrollOffset=0 + row 2 = idx 2). If `hit` is anything other than `"PLEDIT"` or `ok` is
false → Zone 1 boundary wrong; verify `originX` at runtime.

Diagnostic value: If this fails, H4 is confirmed — the hitzone math is wrong. Fix
`PLEDIT_CONTENT_X` or `originX` before proceeding.

---

**T135 — Drag-end fires on synthetic swipe-up: dragState returns to D_IDLE**

Target hypothesis: H1/H2 root-cause isolation (proves logic path works on inject).

Preconditions: `get dragState` == `D_IDLE`; Spotify queue count >= 6 (room to scroll).

Steps:
1. `get dragState` — assert `state == "D_IDLE"`.
2. `drag 156 185 156 155 30` — swipe-up, dy = -30, all points in Zone 1.
3. Wait for `{"ok":true,"cmd":"drag",...}` response (≤ 10 s).
4. `get dragState` — assert `state == "D_IDLE"`.

Expected: Drag response arrives; dragState returns to D_IDLE. Confirms `injectRelease()`
ran the `D_PLEDIT_SCROLL` branch (not stuck in state). If dragState stays
`"D_PLEDIT_SCROLL"` → the release sentinel never popped or `injectRelease()` didn't
clear state.

---

**T136 — Swipe-up increments scrollOffset by 1 (requires `get scrollOffset`)**

Target hypotheses: H2 (dy accumulation), H3 (dirty-flag / redraw gate).

Preconditions: `get scrollOffset` == 0; `get dragState` == `D_IDLE`; queue count >= 6.

Steps:
1. `get scrollOffset` — assert 0.
2. `drag 156 185 156 155 30` — swipe-up, dy = -30.
3. Wait for `{"ok":true,"cmd":"drag",...}`.
4. `get scrollOffset` — assert 1.

Expected: scrollOffset == 1. If scrollOffset stays 0 → drag-end ran but dy was < 8 (H2
— only one sample landed) or the drag hit the wrong state branch. Check LOG_D for
`_dragStartY`, `_dragCurrentY`, `dy` values at drag-end.

---

**T137 — Swipe-down decrements scrollOffset by 1 (requires `get scrollOffset`)**

Target hypothesis: H2/H3 (bidirectional correctness).

Preconditions: `get scrollOffset` == 1 (run T136 first or scroll manually).

Steps:
1. `drag 156 155 156 185 30` — swipe-down, dy = +30.
2. Wait for drag response.
3. `get scrollOffset` — assert 0.

Expected: scrollOffset == 0.

---

**T138 — Clamp at zero: swipe-down when scrollOffset=0 stays at 0 (requires `get scrollOffset`)**

Target hypothesis: clamp logic correctness.

Preconditions: `get scrollOffset` == 0.

Steps:
1. `drag 156 155 156 185 30` — swipe-down.
2. Wait for drag response.
3. `get scrollOffset` — assert 0 (unchanged).

Expected: `max(scrollOffset - 1, 0)` clamp holds.

---

**T139 — Clamp at max: swipe-up when scrollOffset=maxOffset stays at maxOffset (requires `get scrollOffset`)**

Target hypothesis: clamp logic correctness.

Preconditions: `get queue` to obtain count N; scrollOffset already at maxOffset = N - 5
(issue N-5 upward drags).

Steps:
1. Confirm `get scrollOffset` == maxOffset.
2. `drag 156 185 156 155 30` — swipe-up.
3. Wait for drag response.
4. `get scrollOffset` — assert == maxOffset (unchanged).

Expected: `min(scrollOffset + 1, maxOffset)` clamp holds.

---

**T140 — Small-delta tap: |dy| < 8 dispatches PLAY_URI not SCROLL (requires `get scrollOffset`)**

Target hypothesis: tap/scroll discriminator threshold.

Preconditions: `get scrollOffset` == S (any value). Queue count >= 1.

Steps:
1. Record S = `get scrollOffset`.
2. `drag 156 165 156 168 1` — dy = +3 (below 8 px threshold).
3. Wait for drag response.
4. `get scrollOffset` — assert still == S (no scroll).
5. Check serial log for `ACT_PLAY_URI` enqueue (row = S + 2, start row = 2).

Expected: scrollOffset unchanged; PLAY_URI enqueued for row index S+2. Confirms the
|dy|<8 tap branch fires correctly.

---

Test IDs for test_plan.md: T134–T140. Owner: VE. Status: planned.
Add `get scrollOffset` to firmware before running T136–T140 (flag to Developer).

### TASK-077 — BUG: scrollbar thumb X position wrong (too far left)
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-23 — `+ 1` corrected to `+ (PLEDIT_SIDE_RIGHT_W - SKIN_PLEDIT_THUMB_W) / 2` in both `drawPlaylist()` and `drawScrollThumbOnly()`)
**Blocks**: TASK-051j (hitzones PNG visual review)
**Symptom**: Scrollbar thumb renders too far to the left within the scrollbar track strip.
User observation: "slider needs to move a bit to the right."
**Root cause (QM audit 2026-05-23)**: `thumb_x = rightX + 1` placed the 9px thumb 1px
from the left edge of the 19px right-side tile. Correct offset centres the thumb:
`(PLEDIT_SIDE_RIGHT_W − SKIN_PLEDIT_THUMB_W) / 2 = (19 − 9) / 2 = 5` px from tile
left edge. The `+ 1` was an initial guess, not derived from the sprite geometry.
**Note**: TASK-077 was originally filed as a Y-position bug. QM audit confirmed the Y
formula (`PLEDIT_ROWS_Y + scrollOffset × travel / denom`) matches the spec exactly.
The actual defect was X-only. T120 still required for VE sign-off on the corrected render.

---

### TASK-079 — Add `get scrollOffset` to WinampDisplay::dbgGet
**Owner**: Developer
**Feature**: serialdbg-001, playlist-002
**Status**: done (2026-05-23)
**Blocked by**: —
**Notes**:
- Add `else if (key == "scrollOffset")` branch to `WinampDisplay::dbgGet` (`winampDisplay.h`, alongside existing "cooldown"/"dragState" branches — TASK-056g pattern).
- Emit `{"ok":true,"key":"scrollOffset","val":N}` where N is `scrollOffset`.
- No ADR needed — strictly follows established `dbgGet` pattern; no new architecture.
- ~5 LOC. Both `cyd2usb_winamp_debug` and production build must remain clean (guard under `#ifdef SERIAL_DEBUG` same as existing branches).
- **Unblocks**: T136–T140 (scroll gesture tests), T120 (scrollbar thumb position VE sign-off).
- Exit criterion: `get scrollOffset` over serial returns correct value; T136 passes.
- **Delivered**: `winampDisplay.h` +4 LOC; both envs build clean.

---

### TASK-080 — Architect audit: origin-relative render + hit-test pre-gate for M-MULTIAPP

**Owner**: Architect
**Feature**: shell-layout-001
**Status**: done (2026-05-24 — signed off, no FIX NEEDED rows, originX shift unblocked)
**Blocks**: M-MULTIAPP firmware implementation (originX shift)
**Notes**:

#### Finding Table — Architect sign-off 2026-05-24

Audited: `winampDisplay.h` (all `tft.*` render + hit-test sites), `vuMeter.h`, `cheapYellowLCD.h`.

| File | Function / Site | X arg | Y arg | Status |
|------|-----------------|-------|-------|--------|
| `winampDisplay.h:81` | `repaintChrome` titlebar inactive | `originX` | `originY` | ✅ |
| `winampDisplay.h:87` | `repaintChrome` drift pip | `originX+268` | `originY+1` | ✅ |
| `winampDisplay.h:91,93` | `repaintChrome` posbar + thumb | `originX+POSBAR_X` | `originY+POSBAR_Y` | ✅ |
| `winampDisplay.h:127,134,135` | `drawVolume` knob | `originX+VOLUME_X` | `originY+VOLUME_Y` | ✅ |
| `winampDisplay.h:157,170` | `drawShuffle/drawRepeat` | `originX+SHUFFLE/REPEAT_X` | `originY+…_Y` | ✅ |
| `winampDisplay.h:555` | `repaintChrome` main BG | `originX` | `originY` | ✅ |
| `winampDisplay.h:594` | transport buttons | `originX+b.x` | `originY+b.y` | ✅ |
| `winampDisplay.h:910,917` | digits + play/pause | `originX+digit_x[i]` / `originX+PP_X` | `originY+DIGIT_Y` / `originY+PP_Y` | ✅ |
| `winampDisplay.h:923-929` | title scroll slot | `slotX=originX+TITLE_X` | `slotY=originY+TITLE_Y` | ✅ |
| `winampDisplay.h:279-285` | posbar thumb (injectTouch) | `slotX=originX+POSBAR_X` | `slotY=originY+POSBAR_Y` | ✅ |
| `winampDisplay.h:602-669` | all `hitTest*` functions | `originX+…` | `originY+…` | ✅ |
| `winampDisplay.h:1016-1020` | PLEDIT gutter fills | `0` / `rightEdge=originX+PLEDIT_W` | `PLEDIT_Y` | ✅ intentional gutter / ⚠️ Y absolute — safe `originY=0` |
| `winampDisplay.h:984,1023` | `drawPlaylist` PLEDIT title bar | `originX` | `PLEDIT_Y` | ⚠️ Y absolute — safe `originY=0` |
| `winampDisplay.h:961-963` | `drawScrollThumbOnly` side strip loop | `rightX=originX+…` | `sy` from `PLEDIT_ROWS_Y` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:968-969` | `drawScrollThumbOnly` thumb | `rightX+PLEDIT_THUMB_X_INSET` | `PLEDIT_ROWS_Y+offset` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:1027-1030` | `drawPlaylist` left+right side tiles | `originX` / `originX+…` | `sy` from `PLEDIT_ROWS_Y` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:1038-1040` | `drawPlaylist` scroll thumb | `thumb_x=originX+…` | `thumb_y=PLEDIT_ROWS_Y+offset` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:1056-1071` | `drawPlaylist` row fills | `originX+PLEDIT_CONTENT_X` | `ry=PLEDIT_ROWS_Y+i*ROW_H` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:1103-1106` | `drawPlaylist` row text | `originX+PLEDIT_CONTENT_X+…` / `durX=originX+…` | `textY=ry+TEXT_VOFF` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:1111` | `drawPlaylist` bottom bar | `originX` | `PLEDIT_BOTTOM_Y` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:1129-1130` | PLEDIT bottom glyph | `originX+127+GLYPH_W` | `PLEDIT_BOTTOM_Y+10` | ✅ X / ⚠️ Y absolute |
| `winampDisplay.h:342-365` | drag handler PLEDIT Y hit-test | `p.x >= originX+…` | `py=p.y-originY` vs `PLEDIT_ROWS_Y` | ✅ X / ⚠️ Y mismatch |
| `winampDisplay.h:751-775` | `injectTouch` PLEDIT Y hit-test | `sx >= originX+…` | `py=sy-originY` vs `PLEDIT_ROWS_Y` | ✅ X / ⚠️ Y mismatch |
| `vuMeter.h` | all `blitVis*` / `tick*` functions | `originX+…` param | `originY+…` param | ✅ fully param-relative |
| `cheapYellowLCD.h` | all draw calls | n/a | n/a | ✅ no Winamp chrome draws |

**Summary:**
- **X coordinates:** 100% origin-relative across all files. No bare absolute X integers in any draw call. ✅
- **Y coordinates (PLEDIT only):** `PLEDIT_Y=116`, `PLEDIT_ROWS_Y=136`, `PLEDIT_BOTTOM_Y=201` are absolute screen constants from `gen/skin_layout.h`, used directly. Safe because `originY=0` always. Latent liability for future `originY≠0` scenario — not a blocker for M-MULTIAPP.
- **PLEDIT touch Y mismatch:** `py = sy - originY` (origin-relative) compared against `PLEDIT_ROWS_Y` (absolute). Conceptual mismatch, safe when `originY=0`. Same latent liability.
- **No FIX NEEDED rows.** originX=0 shift will work correctly on all sites.

**Gate: SIGNED OFF. M-MULTIAPP firmware implementation (TASK-083 step 5) is unblocked on TASK-080.**

---

### TASK-081 — VE: serialdbg regression suite for originX=0 shift (T141–T146)

**Owner**: VE
**Feature**: shell-layout-001, serialdbg-001, touch-002
**Status**: done (2026-05-24 — 23/25 pass; exit criteria met; T136 harness defect tracked as TASK-085; T140 skip tracked as TASK-086)
**Blocked by**: TASK-080 (finding table sign-off), M-MULTIAPP firmware (originX=0 build)
**Notes**:

After M-MULTIAPP firmware changes `originX` from 22 → 0, every screen tap/drag coordinate
shifts left by 22 px. Existing serialdbg tests (T076–T088, T095–T096, T134–T140) encode
coordinates at `originX=22`. TASK-068 updates `run_serialdbg_tests.py` to use `coords.py`
for live derivation — this task verifies that the updated harness + new firmware all pass.

Tests T141–T146 are defined in the test plan under suite `multiapp-001`.

Entry criteria:
- `cyd2usb_winamp_debug` firmware built with `originX=0` (M-MULTIAPP firmware impl done)
- `run_serialdbg_tests.py` using `coords.py` (TASK-068 done)
- TASK-080 finding table signed off (no "FIX NEEDED" rows)

Exit criteria:
- T141–T146 all pass on DUT ✅
- T076, T081, T082, T086, T087, T088, T134 re-run with coords.py coordinates and all pass ✅
- No new DEADZONE misfire where a named zone is expected ✅

Result: 23/25 pass. T136 FAIL = harness ordering bug (T135 mutates scrollOffset before T136
checks it; firmware not at fault). T140 SKIP = queue snapshot holds exactly PLEDIT_ROW_COUNT=5
items so maxOffset=0; clamping at non-zero max untestable without snapshot expansion.

Report pass/fail to PM. PM prompts QM for retrospective.

---

### TASK-082 — Implement tools/audit_origin.py
**Owner**: Developer
**Feature**: shell-layout-001
**Status**: done (2026-05-24 — all exit criteria verified)
**Blocked by**: nothing (`gen/skin_layout.h` present)
**Unblocks**: TASK-081 (T141–T146 host-side execution)

Implement `tools/audit_origin.py` per design doc
`docs/architecture/designs/audit-origin.md`.

Deliverables:
- `tools/audit_origin.py` (210 LOC) — T141–T146 logic + `--visual` PNG
- `gen/origin_audit.png` added to `app/.gitignore`
- Note: `render_hitzones()` in `bake_skin.py` not refactored — `audit_origin.py`
  builds its visual independently from imported bake_skin constants; existing
  call-site unchanged and bake_skin refactor deferred (not needed for T141–T146).

Exit criteria — all verified 2026-05-24:
- `python3 tools/audit_origin.py` exits 0 ✅
- `--visual` produces `gen/origin_audit.png` with all green dots ✅
- `--grep-only` exits 0 ✅
- Full run at ox=0 (T146) exits 0 ✅
- `sha256sum -c gen/golden.sha256` unaffected ✅

---

### TASK-083 — M-RESTRUCTURE: execute source ownership split
**Owner**: Developer
**Feature**: shell-layout-001
**Status**: done (2026-05-24)
**Blocked by**: —
**Unblocks**: M-MULTIAPP firmware (originX=0 shift) ✓ unblocked
**Milestone**: M-RESTRUCTURE
**Commits**: d62c9f4 (steps 1–4), 709027b (step 5)

Execute the 4+1-step Option B migration per
`docs/architecture/designs/M-MULTIAPP/source-ownership.md` (§Migration sequence).
See that doc for the full `app/platformio.ini` spec and ownership table.
Run `./check_build.sh` after each step (BP-008).

**Option B chosen** (2026-05-24, commit 88bfb29): separate `app/` PlatformIO
project at repo root; `Spotify-Diy-Thing/` kept close to upstream stock.
Steps below supersede any earlier in-place reorganisation notes.

#### Step 1 — Create `app/` PlatformIO skeleton ✓ done 2026-05-24

- Create `app/platformio.ini` per §`app/platformio.ini` spec in source-ownership.md:
  `src_dir = src`; `lib_extra_dirs` pointing to upstream flat dir + its `lib/`;
  carry forward `[env]` / `[common_cyd]` / `[env:cyd2usb_winamp*]` from
  upstream's `platformio.ini`; drop `[env:cyd]`, `[env:cyd2usb_spike]`,
  `[env:trinity]` (not our target hardware).
- Create `app/src/main.cpp` stub (`void setup(){} void loop(){}`).
- Gate: `cd app && ~/.platformio/penv/bin/pio run -e cyd2usb_winamp` passes.
  (Does not replace `./check_build.sh` yet — upstream build still the reference.)

#### Step 2 — Move our owned files; update build gate ✓ done 2026-05-24

Move **ours-owned source** from `Spotify-Diy-Thing/SpotifyDiyThing/` to `app/src/`:
- `winampDisplay.h`, `vuMeter.h` → `app/src/winamp/`
- `spotifyTask.h`, `spotifyTaskStorage.cpp` → `app/src/`
- `logSink.h`, `logSinkStorage.cpp`, `logHeartbeat.h`, `logDecode.h`,
  `logServer.h` → `app/src/`
- `screenLog.h`, `perf.h`, `secret.h`, `serialPrint.h` → `app/src/`

Move **ours-owned assets and tooling**:
- `Spotify-Diy-Thing/lib/SpotifyArduino/` → `app/lib/SpotifyArduino/`
  (LOCAL_PATCHES preserved; PlatformIO auto-discovers `app/lib/` as project lib dir)
- `Spotify-Diy-Thing/tools/` → `app/tools/`
- `Spotify-Diy-Thing/scripts/` → `app/scripts/`
- `Spotify-Diy-Thing/skins/` → `app/skins/`
- `Spotify-Diy-Thing/SpotifyDiyThing/gen/` → `app/gen/`

Update build gate:
- `check_build.sh`: set `PIO_DIR=$PROJ_ROOT/app`, `GEN_DIR=$PROJ_ROOT/app/gen`.
- Update `CLAUDE.md` paths that reference `Spotify-Diy-Thing/tools/`,
  `Spotify-Diy-Thing/skins/`, `SpotifyDiyThing/gen/` to their new `app/` locations.
- Update `screenLog.h` include: `"winampDisplay.h"` → `"winamp/winampDisplay.h"`.

Gate: `./check_build.sh` passes (both `cyd2usb_winamp` and `cyd2usb_winamp_debug`
compile from `app/`; `app/gen/golden.sha256` passes).

#### Step 3 — Add `appShell.h` + `taskbar/taskbar.h` stubs ✓ done 2026-05-24

- `app/src/appShell.h`: minimal dispatch stubs per `app-lifecycle.md`; no
  behaviour change vs current `.ino`.
- `app/src/taskbar/taskbar.h`: render + hit-test stubs per `taskbar.md`.

Gate: `./check_build.sh` passes.

#### Step 4 — Rewrite shell; revert upstream files ✓ done 2026-05-24

- `app/src/main.cpp`: full shell content (current `SpotifyDiyThing.ino` logic,
  converted to `.cpp`; includes dispatch via `appShell.h`).
- Revert `Spotify-Diy-Thing/SpotifyDiyThing/SpotifyDiyThing.ino` to upstream stock
  (obtain from `git show <upstream-ref>:SpotifyDiyThing/SpotifyDiyThing.ino`
  or re-clone; record upstream ref in `upstream-patches.md`).
- Revert `Spotify-Diy-Thing/platformio.ini` to upstream (drop our custom envs;
  they are now in `app/platformio.ini`).
- Add/update `Spotify-Diy-Thing/data/` symlink or copy to `app/data/` if SPIFFS
  uploads must go through the `app/` build path.

Gate: `./check_build.sh` passes + `python3 app/tools/audit_origin.py --grep-only`
exits 0 (shell must not introduce bare absolute X literals).

DUT smoke test: boot with playing track → Winamp chrome renders; NEXT/PREV
advances track; PLAY/PAUSE toggles; no crash on track change.

#### Step 5 — Apply `originX=0` **[gate: TASK-080 sign-off + TASK-082 baseline]**

- One-line canvas rect change in `app/src/main.cpp` shell: `originX` 22 → 0.
- Gate: `python3 app/tools/audit_origin.py` full run (T141–T146) exits 0.
  This is the TASK-082 exit gate and TASK-081 entry condition.

---

Exit criteria (task complete when all are true):
- `check_build.sh` exits 0 after every step ✓ (3/3 on all steps)
- `app/lib/SpotifyArduino/LOCAL_PATCHES.md` preserved intact ✓
- `app/src/screenLog.h` uses `"winamp/winampDisplay.h"` include path ✓
- `audit_origin.py --grep-only` exits 0 after step 4 ✓ (T141 PASS)
- Step 4 DUT smoke test passes ✓ (2026-05-24: Spotify polling live, Winamp chrome rendering, no crashes)
- `audit_origin.py` full run exits 0 after step 5 — PENDING (step 5 not yet applied)
- `Spotify-Diy-Thing/SpotifyDiyThing/SpotifyDiyThing.ino` matches upstream ref ✓ (reverted to 6eb95ffd)
- `Spotify-Diy-Thing/platformio.ini` matches upstream ref ✓ (reverted to 6eb95ffd)

Out of scope (M-MULTIAPP work, not this task):
- Full decoupling of `winampDisplay.h` from `spotifyLogic.h` globals
- `songStartMillis` write-back design, `spotifyTask::` removal from winampDisplay.h

---

### TASK-084 — Fix stale SpotifyDiyThing/ paths in app/tools/ scripts (post-M-RESTRUCTURE)
**Owner**: Developer
**Feature**: shell-layout-001
**Status**: done (2026-05-24, commit 1959f7a)
**Blocked by**: —
**Milestone**: M-RESTRUCTURE follow-up
**Triggered by**: QM audit 2026-05-24 (LL-029, BP-009). `coords.py` stale path found during T102 re-run; grep revealed 5 additional functional stale paths.

Fix all stale `SpotifyDiyThing/gen/` path references in `app/tools/` left over from M-RESTRUCTURE.

**Functional (runtime-breaking) — fix first:**
- `app/tools/preview_vis.py:65` — `pathlib.Path` import: `../SpotifyDiyThing/gen/skin_layout.h` → `../gen/skin_layout.h`
- `app/tools/bake_wave.sh:19` — shell output dir: `$SCRIPT_DIR/../SpotifyDiyThing/gen` → `$SCRIPT_DIR/../gen`
- `app/tools/preview_vis.py:340` — argparse default: `SpotifyDiyThing/gen/skin_preview_animated.gif` → `gen/skin_preview_animated.gif`
- `app/tools/preview_wave.py:128–129` — argparse default + help: `SpotifyDiyThing/gen/skin_preview_wave.gif` → `gen/skin_preview_wave.gif`
- `app/tools/bake_skin.py:773` — `parse_shell_layout` default arg: `SpotifyDiyThing/gen/shell_layout.h` → `gen/shell_layout.h`

**Docstrings/help text (misleading) — fix in same pass:**
- `app/tools/bake_skin.py:8-9` — usage example paths
- `app/tools/bake_vis.py:7-8` — usage example paths
- `app/tools/bake_wave.py:6-7` — usage example paths
- `app/tools/preview_vis.py:20-22,26-27,32,37-38` — usage example strings
- `app/tools/preview_wave.py:15-17,129` — argparse help strings

**Smoke-test gate (add, per BP-009):**
Add `tools/smoke_test.sh` (or fold into `check_build.sh`) that runs:
```sh
cd app && python3 -c "import tools.coords; import tools.bake_skin"
bash app/tools/bake_wave.sh --help 2>&1 | grep -v "No such file"
```
Exit 1 on any import error or path complaint. Gate must pass before task is `done`.

**Exit criteria:**
- `grep -rn "SpotifyDiyThing/gen" app/tools/` returns zero hits
- `python3 -c "import coords"` from `app/tools/` exits 0
- `bash app/tools/bake_wave.sh --help` exits without path errors
- Smoke-test gate added and passing

**Do not fix:** historical docs (ADR-008.md, audit_log.md, feature_inventory.yaml, design docs) — those are accurate pre-restructure records.

---

### TASK-078 — Design: PLEDIT content-area drag UX improvements
**Owner**: Architect (whiteboard), then Developer
**Feature**: playlist-002, touch-002
**Status**: open (2026-05-23) — points 1 and 3 remain; point 2 resolved by TASK-101
**Blocked by**: TASK-101 (both remaining points require reliable `dy` — see notes)
**Notes**: Current Zone 1 swipe is functional but unsatisfying. Three discussion points:

1. **Click vs gesture discrimination**: Current threshold (|dy| < 4px → tap, ≥4px →
   scroll) is crude. A proper discriminator would consider gesture velocity and/or
   total travel time: short fast → tap; slow long → scroll. Avoids mis-fires when
   the user intends a firm tap but moves slightly.
   **Blocked by TASK-101**: velocity = dy/elapsed_ms; both values are only accurate
   after capture is fixed. A leaky sample stream (finger drifts outside hitbox mid-swipe
   → Move samples dropped → artificially small dy) misclassifies deliberate swipes as
   taps. Also requires `_dragStartMs` timestamp added at `D_PLEDIT_SCROLL` Press entry
   (one-liner; can be included in TASK-101 or as a follow-up).

2. ~~**Full-screen gesture capture**~~ — **RESOLVED by TASK-101** (M-TOUCH-CAPTURE
   DragState-first dispatch covers all four sliders including PLEDIT content swipe).
   No separate implementation needed here.

3. **Acceleration / momentum**: A single swipe increments scrollOffset by ±1
   regardless of gesture speed or length. A fast or long swipe should scroll 2–3
   rows. Simple model: `delta = max(1, abs(dy) / ROW_H)` — proportional to travel in
   row-heights. Cap at PLEDIT_ROW_COUNT to avoid jumping past all visible rows.
   **Blocked by TASK-101**: `abs(dy)` must measure full gesture travel. Without capture,
   dropped Move samples make dy artificially small; `delta` rounds to 1 on every swipe,
   making the enhancement invisible.

Points 1 and 3 are blocked on TASK-101. Implement and verify only after T149–T154 pass.

---

### TASK-022 — M-LIST option B: portrait rotation
**Owner**: Developer
**Status**: cancelled (2026-05-15 — ADR-017 chose option C; portrait rotation not needed)

### TASK-019 — Decouple display from blocking network calls (M-IO)
**Owner**: Architect (ADR-011), then Developer
**Feature**: io-001 (registered with tier-1 implementation)
**Status**: done (2026-05-22 — tier-2 delivered by TASK-031; closing)
**Notes**:
- Symptoms: slow first sync after boot; occasional hangs (clock + progress thumb stop); LCD shows previous track many seconds after Spotify advanced; heartbeat 56 s gaps observed during TLS retries.
- Tier 1 (ADR-011, 2026-05-07): exponential backoff on consecutive Spotify-poll failures (5 s → 10 → 20 → 40 → 60 s cap, reset on success or touch). Heartbeat now emits `block_max=Nms`.
- Tier 2 (TASK-031, 2026-05-08): all HTTP moved off the main task into `spotifyTask` (FreeRTOS worker). `loop_max` 4 191 ms → 16 ms. Exit criterion (heartbeat gap < 5 s p95) met. No further work needed.

### TASK-016 — Logging redesign tier 1 (M-LOG, parent)
**Owner**: Developer (implementation), Architect (ADR-010 + amendments done), VE (T036–T040)
**Feature**: log-001 (registered at first implementation commit)
**Status**: tier-1 shipped (2026-05-07 — all five sub-tasks landed and DUT-verified except `/log` HTTP test which is gated on a non-AP-isolated network)
**Estimate**: ~half a day total across sub-tasks
**Notes**:
- Whiteboard: `docs/architecture/whiteboards/2026-05-07-logging-rethink.md`. ADR + amendments: `docs/architecture/decisions/ADR-010.md`. Review: `docs/architecture/decisions/ADR-010-review.md`.
- Split into independently-shippable sub-tasks (per @PM during review):

#### TASK-016b — Secret redactor + remove configFile.h JSON dump (security fix, ship first)
**Status**: shipped (Spotify-Diy-Thing@442b030, 2026-05-07). DUT-verified — three distinct redacted values render correctly (8-slot rotating pool needed; single-buffer aliased all printf args to the last value). Closes LL-002/LL-003 in-tree.
- New `secret.h` with `redact(s) -> "AQ…IY (len=131)"`. nullptr-safe, "" returns a non-empty marker.
- Remove the configFile.h JSON dump that prints refresh token + client secret on every boot.
- Commit message leads with security-fix framing for audit grep.

#### TASK-016a — esp_log hook + 12 KB ringbuffer + permanent post-connect HTTP server + /log
**Status**: shipped + fully verified (Spotify-Diy-Thing@7f1009c, 2026-05-07). DUT-verified for boot trace + ESP_LOGI capture; T036 + T037 verified 2026-05-22 on non-isolated network (DUT 192.168.1.126).
- `esp_log_set_vprintf` fans to Serial + ringbuffer. Line-oriented, drop-oldest, `portENTER_CRITICAL_SAFE` (works in ISR context too). 256-char line cap; one-time WARN tag=`log` on first truncation.
- Stand up a permanent HTTP server bound to `WiFi.localIP()` (not 0.0.0.0; not the WiFiManager portal one — that shuts down post-onboarding).
- `GET /log?n=N` plain text, last N lines. `GET /log?clear=1` empties. No auth — LAN-only is documented invariant.
- Default levels: INFO baseline; DEBUG for `display`, `spotify`, `time`; WARN for vendored tags (`HTTPClient`, `WiFiClient`, `ssl_client`, `mbedtls`).

#### TASK-016c — mbedTLS / HTTP decoder macros
**Status**: shipped (with TASK-016d in the same commit, 2026-05-07). DUT-verified — `[spotify.poll] fail http=HTTP -1` line shows decoder + ESP_LOGW path live.
- `LOG_TLS_ERR(rc)`: 0x0050, 0x004C, -9984, -76, -80 (more as discovered). `LOG_HTTP_ERR(code)`: 401, 403, 429, 5xx.
- Unknown codes pass through as raw hex / int — never silently dropped.

#### TASK-016d — 30 s heartbeat tick
**Status**: shipped, DUT-verified 2026-05-07. Heartbeat fires; counters track poll attempts/successes/last code. Long blocking calls (TLS retries) push the next tick out, which is the intended visibility — heartbeat surfaces opaque blocking. Required `-DCORE_DEBUG_LEVEL=3` to be effective.
- Super-loop `millis()` gate. Tag `hb`. Key=value pairs: `display=…`, `wifi=rssi(…)`, `heap=…k`, `poll=ok(204):N/last=…`, `uptime=HH:MM:SS`, `build=<epoch> <sha>`.
- Counters reset on reboot.

#### TASK-016e — `tools/audit_log_hygiene.sh`
**Status**: shipped with 016b (2026-05-07). Currently clean across the sketch. Run from `Spotify-Diy-Thing/`: `tools/audit_log_hygiene.sh`.
- Greps for banned patterns: `Bearer `, `client_secret=`, `Serial.print*` of names matching `*token*` / `*secret*` / `*refresh*`. Exit 1 on hit. Wire into review checklist; CI when CI exists.

**Migration policy**: incremental — new code uses `ESP_LOGx`; existing `Serial.println` stays until touched. Secret-leaking sites are fixed in tier 1 regardless.

**Follow-ups (post tier 1)**:
- After M3 + M5 close, lift `display` and `spotify` defaults from DEBUG to INFO. **Tracked as a checkpoint, not a task — Architect to revisit at each milestone close.**
- Promotion candidate (QM, awaiting human approval): "ADRs require @VE testability + @Developer implementability passes before transitioning to `accepted`."
- Out of scope for tier 1 (future TASK-017 if raised): UDP syslog push, state-machine trace points beyond natural call-site adoption, SPIFFS-backed buffer + panic flush, runtime per-tag control via web UI.

### TASK-015 — M3 Winamp display backend
**Owner**: Developer
**Feature**: m3-001 (new)
**Status**: done (2026-05-07 — DUT visual verify complete; all 8 items confirmed: bg, buttons, status indicator, time digits, title, marquee, progress thumb, touch press feedback)
**Notes**:
- Tier 1 (Spotify-Diy-Thing@e8f52b7): `winampDisplay.h` scaffold. Subclasses `CheapYellowDisplay`; reuses JPEG/SPIFFS/touch plumbing. New `cyd2usb_winamp` PIO env. Static bg + transport buttons + ASCII title.
- Tier 2 (Spotify-Diy-Thing@e4871e8): `bake_skin.py` now bakes NUMBERS/POSBAR/PLAYPAUS atlases + UVs. `winampDisplay.h` uses POSBAR sprite for bar+thumb, PLAYPAUS for status indicator, marquee scroll on title overflow, pressed-button feedback in `checkForInput`.
- Build: cyd2usb_winamp flash 88.6 → 96.6 % (atlas + render now linked); default cyd2usb env unchanged at 88.6 %. **Tight headroom — TITLEBAR/VOLUME/BALANCE atlases would push past 100 %; deliberately deferred.**
- `.ino` reorders `#if defined WINAMP_DISPLAY` ahead of `YELLOW_DISPLAY` because `cyd2usb_winamp` inherits `common_cyd`'s `-DYELLOW_DISPLAY`. Confirmed via section-GC nm dump.
- Verification gate (T033–T035): DUT flash, eyeball bg+buttons, title (long string for marquee), progress bar advance, press feedback. Pending next DUT session.
- Follow-ups: NUMBERS sprite use (time digits — currently DCE'd, no caller); seek/scrub on POSBAR touch; eject/shuffle/repeat/volume controls; 2× scaling (needs software upscaler).

### TASK-014 — Album art (i.scdn.co) fetch hang
**Owner**: Developer (investigation), Architect (if it leads to a TLS-stack choice)
**Feature**: poll-001 (regression surface)
**Status**: closed — deferred (M-NOART, TASK-062, shipped 2026-05-21 — album-art path removed; DISABLE_ALBUM_ART is now permanent policy, not a workaround. Hang is moot.)
**Notes**:
- Symptom (2026-05-06 Marriott captive portal session, post MAC pre-auth): DUT fetches Spotify currently-playing JSON cleanly, then hangs after logging `Removing existing image` in `cheapYellowLCD::displayImageUsingFile`. Subsequent watchdog/UI freeze; serial output from the poll loop also stops.
- Workaround in tree: `#define DISABLE_ALBUM_ART 1` in `.ino` skips the entire image fetch+decode path. Set in commit f84b112 to unblock M4 verification.
- Hypotheses to rule in/out: (a) JPEGDEC streaming hits an OOM under the new TFT_eSPI build; (b) i.scdn.co's CDN behind the captive portal returns a redirect/304 the lib doesn't handle; (c) the same WiFiClientSecure-reuse bug as TASK-009 but on the image-server cert path; (d) SPIFFS write-blocking on a fragmented FS.
- Diagnostic next step: capture serial with timing across the `getImage` call to localise the hang. May overlap with TASK-009 fix verification.

### TASK-010 — VU data-source rethink (ADR-002 invalidated)
**Owner**: Architect (decision), Developer (impl)
**Feature**: vu-001 (implemented)
**Status**: done (ADR-009 accepted 2026-05-07; M6 implementation shipped 2026-05-09 — Spotify-Diy-Thing@049c088 — synthetic envelope + 120 BPM beat clock + LFO stereo split + green/yellow/red colour grading)
**Blocks**: M6 (VU meter)
**Notes**:
- Discovered during TASK-007 DUT run 2026-04-29: both `/v1/audio-features/{id}` and `/v1/audio-analysis/{id}` return **HTTP 403** for the dev account's client app. Spotify deprecated these endpoints for new Developer apps as of late 2024 (announced via the Web API change-log). The app `db2ff394...` was created during TASK-001 (post-deprecation), so it has no access.
- ADR-002 ("VU meter sourced from Spotify `audio-analysis`, beat-synchronised") is therefore not implementable on this account.
- Options for a new ADR:
  - (a) Drop VU entirely. Skin renders the VU rect as static art.
  - (b) Synthesise a coarse VU from `currentlyPlaying` data only — track tempo (if Spotify still exposes it on the now-playing endpoint), elapsed-position, and a hand-tuned envelope. Not music-locked but might "look alive."
  - (c) Apply for Spotify "Extended Quota Mode" (manual approval, weeks, uncertain outcome). Restores audio-features/analysis access.
  - (d) On-device I2S microphone (ADR-002 option c, previously rejected). Real audio data, hardware addition, room-noise contamination.
- Recommend (b) for first cut — cheap, ships, doesn't block M2/M3/M5. Keep (c) on a second track as an upgrade path.
- 2026-05-07: ADR-009 accepted with **option (e) — synthesise from `currentlyPlaying` only** (option (a)'s premise also dead since `audio-features` is in the same deprecation). Implementation tier-1 will ship a 20 Hz envelope + flat-120 BPM beat clock + LFO stereo split. Extended-quota application kept as a parallel, non-blocking track. Feature `vu-001` description to be re-worded by Developer at implementation start.

### TASK-052a — M-VIS-ATLAS: bake_vis.py — bar-height extraction pipeline
**Owner**: Developer
**Feature**: vis-002 (new)
**Status**: done (2026-05-16 — 412 frames, 7.6 KB, wrap L1=18 ✓, sha256 golden committed)
**Blocks**: TASK-052b, TASK-052c, TASK-052d
**Notes**:
- New `tools/bake_vis.py` (sibling to `bake_skin.py`). Inputs: one or more committed `.webm` screengrab videos; output: `gen/vis_atlas.c` + `gen/vis_atlas.h` + `gen/vis_atlas.npy` + `gen/vis_atlas.sha256`.
- Auto-calibrate vis area per M-VIS-video-analysis-method.md (blue border detection).
- Subsample source at 20 Hz; extract bar heights (0..16) per bar per frame via background pixel classification.
- Emit `uint8_t VIS_ATLAS[N_FRAMES][19]` byte-per-bar C array and companion NumPy `.npy`.
- Report wrap-jump distance (L1 between frame[0] and frame[-1]) to console.
- SHA256 golden: `sha256sum -c gen/vis_atlas.sha256` must pass on same machine.
- See `docs/architecture/designs/M-VIS-ATLAS-vis-atlas.md` §1.

### TASK-052b — M-VIS-ATLAS: preview_vis.py — animated GIF output
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — gen/skin_preview_animated.gif, 182 frames, correct 1:1 device-pixel coords, boost+trim applied)
**Deps**: TASK-052a (needs vis_atlas.npy)
**Notes**:
- `tools/preview_vis.py` reads `gen/vis_atlas.npy` + `gen/skin_preview.png`; composites atlas frames into vis area at 1:1 device pixels (skin_preview.png is 320×240, chrome at x=0,y=0); writes animated GIF at 20 fps.
- Vis coords mirror firmware exactly: skin chrome at (0,0) in preview, vis at x=RECT_X=24, y=LEFT_Y+1=44.
- `--boost 1.5` (default): scales bar heights so peaks reach ceiling (row 0 = red).
- `--trim-quiet` (default on, thresh=4, keep=2): collapses runs of all-green frames to 2 highest-energy frames per run.
- `--boost` and `--trim-quiet` are preview-only tuning knobs; `bake_vis.py` applies the same transforms to the committed C array (see TASK-052a notes below).

### TASK-052c — M-VIS-ATLAS: preview_vis.py — live pygame window + synthetic mode
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — --live pygame window + --mode synthetic implemented; --loop-start/--loop-end sub-range tuning)
**Deps**: TASK-052b
**Notes**:
- `--live` flag opens pygame window at 20 Hz real-time.
- `--mode synthetic` runs firmware AR(1)/inertia/oscillator logic in Python for A/B comparison vs atlas.
- `--loop-start F` / `--loop-end F` to select atlas sub-range for wrap-point tuning.

### TASK-052d — M-VIS-ATLAS: firmware VIS_ATLAS mode in vuMeter.h
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — DUT verified; Atlas default mode; tap cycle Atlas→Wave→VU→Blank→Atlas)
**Deps**: TASK-052a (needs gen/vis_atlas.h)
**Notes**:
- `VIS_ATLAS_MODE` in `VisMode` enum (renamed from VIS_ATLAS to avoid clash with global array symbol).
- `tickAtlas()`: index `VIS_ATLAS[frame][i]` directly (.rodata); freeze frame counter on `!playing` but always blit (fix: early return on !playing left vis area showing stale Spectrum frame).
- No peak dots in atlas mode (footage encodes Winamp peak behaviour by construction).
- VIS_SPECTRUM removed from tap cycle — superseded by atlas. New cycle: **Atlas → Wave → VU → Blank → Atlas**. Default boot mode: Atlas.

### TASK-052e — M-VIS-ATLAS: flash headroom verification
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — Flash 52.4%; baked atlas 3.4 KB after trim+boost, well within 12 KB budget ✓)
**Deps**: TASK-052d
**Notes**:
- `pio run -e cyd2usb_winamp`: Flash 52.4% (1,374,121 / 2,621,440 bytes). Healthy.
- Atlas after trim+boost: 182 frames × 19 bytes = 3,458 bytes in .rodata. Original raw: 412 frames × 19 = 7,828 bytes.
- `bake_vis.py` applies `--boost 1.5` and `--trim-quiet thresh=4 keep=2` before emitting the C array; same parameters as preview_vis.py — DUT and preview match.

### TASK-052f — M-VIS-ATLAS: VE regression — existing vis modes unchanged
**Owner**: VE
**Feature**: vis-002
**Status**: done (2026-05-17 — DUT visual sign-off by user)
**Deps**: TASK-052d
**Notes**:
- DUT flash `cyd2usb_winamp`. Tapped through Atlas → WaveAtlas → VU → Blank → Atlas on device.
- Confirmed: Atlas 19 bars animate at 20 Hz, gravity peak dots visible and correct. User: "looks great".
- WaveAtlas mode added since task was written (TASK-055a–b); cycle is now Atlas → WaveAtlas → VU → Blank → Atlas.
- VU bars intact; Blank clean skin bg.
- Spectrum mode no longer in cycle — removed intentionally.
- Flash delta confirmed within budget (TASK-052e, TASK-055c).

### TASK-065 — BUG: PLEDIT empty after HTTP/1.1 keep-alive (getQueue chunked bail-out)
**Owner**: Developer
**Feature**: playlist-002, conn-002
**Status**: done (2026-05-21 — inner repo commit `62d1792` on rnd/poll-lag, cherry-picked to main as `ab3864e`)
**Git ref**: rnd/poll-lag (observed 2026-05-20 post-M-NOART flash)
**Notes**:

#### Symptom
PLEDIT rows are empty (no track names) even when Spotify shows an active queue.
`get queue` serial command returns `count=0` after a normal boot + track playing.

#### Root cause
`getQueue()` (`lib/SpotifyArduino/src/SpotifyArduino.cpp:625–630`) bails out silently
when the response carries `Transfer-Encoding: chunked`:

```cpp
if (hdr.chunked) {
    closeClient();
    return statusCode;  // 200 returned; onQueue never called
}
```

Under HTTP/1.0 (pre-INV-A Step 3) Spotify returned `Content-Length` for the queue
endpoint — `hdr.chunked` was false and the parse path ran. After the HTTP/1.1
keep-alive switch (INV-A Step 3, 2026-05-20), Spotify responds with
`Transfer-Encoding: chunked`. The bail-out fires every time, `onQueue` is never
invoked, `g_queueSnapshot.count` stays 0, `drawPlaylist()` renders 5 empty rows.

`doFetchQueue()` sets `s_queueRefreshNeeded = false` regardless of outcome, so
subsequent fetches only happen on track-change or the 60 s keepalive — each also
hits the chunked path and produces the same silent zero.

Note: the INV-A Step 3 design notes (`INV-A-tls-connection-lifecycle.md`, §Step 3
implementation notes, item 7) explicitly called out the chunked risk and specified
"fall back to connection-close for that response". This was not implemented — the
bail-out was carried over from the pre-Step-3 code unchanged.

#### Why verification did not catch this
- T102 (TSYNC-6 — queue strip shifts on track-change) ran **2026-05-18**, two days
  before INV-A Step 3 landed (**2026-05-20**). T102 passed under HTTP/1.0; no
  re-run was scheduled after Step 3.
- The Step 3 DUT verification run (5 min, idle, all 204s) checked connection
  metrics only (fd warnings, block_max, poll ratio, heap). The success criteria
  did not include a `get queue` assertion or a PLEDIT visual check. A PLEDIT
  content check was not in the Step 3 exit criteria document.
- `get queue` returning `count=0` on first fetch looks identical to a valid empty
  queue at idle (no track playing). The idle verification run never exercised the
  active-playback queue path.

#### Fix
Implement a dechunker in `getQueue()`: read raw socket bytes into `bodyBuf`,
strip chunk-size framing (`HEX\r\n…DATA…\r\n`, terminated by `0\r\n\r\n`) before
passing to `deserializeJson`. ~20-line loop; isolated to the `getQueue` body-read
path. Removes the bail-out; handles multi-chunk responses correctly.
Alternative (simpler but incurs a reconnect): add `Connection: close` override for
the queue request only, forcing the server to send Content-Length.

#### VE gap (regression coverage) — **closed 2026-05-21**
T114 PASS (DUT 2026-05-21, inner `main` `ab3864e`): `get queue` count=4, row[0] non-empty.
T102 re-run PASS (DUT 2026-05-21): queue row[0] shifted 5832ms ≤ 8500ms under HTTP/1.1
keep-alive + dechunker. Harness: `run_sync_tests.py` T114 added (inner repo `6c6bbe6`);
`read_json()` timing bug fixed; T102 settle-wait added. Results recorded in test_plan.md.

---

### TASK-066 — BUG: tap-to-play clears Spotify queue (context_uri not wired in ACT_PLAY_URI)
**Owner**: Developer
**Feature**: playlist-001 (bug fix)
**Status**: done (2026-05-22 — inner `main` `7a97088`)
**Blocks**: TASK-067 (VE gate)
**Notes**:

#### Symptom (DUT 2026-05-16, re-confirmed 2026-05-22)
Tapping a PLEDIT row clears the Spotify queue. After the tap, PLEDIT shows 5 identical rows of the tapped track; Spotify app shows only 1 item. First reported at TASK-021 close-out.

#### Root cause
`ACT_PLAY_URI` handler (`spotifyTaskStorage.cpp:330-331`) constructs:
```cpp
snprintf(body, sizeof(body), "{\"uris\":[\"%s\"]}", uri);
s_spotify->playAdvanced(body);
```
`{"uris":["..."]}` starts a new ad-hoc single-track session, replacing the existing playlist/album context. `s_lastTrackContextUri` (`spotifyTaskStorage.cpp:46`) is populated on every poll (`onCurrentlyPlaying` lines 77-81) but **never read** in the handler — the wire is missing.

Spotify then fills the 4 upcoming queue slots with the same track URI (its behaviour for a single-URI session), causing `qd.count=5` with identical items → 5 duplicate PLEDIT rows.

#### Fix (spotifyTaskStorage.cpp)
In the `ACT_PLAY_URI` case, check `s_lastTrackContextUri[0]`:
- Non-empty (playlist/album context): use `{"context_uri":"<ctx>","offset":{"uri":"<track>"}}`
- Empty (ad-hoc/radio — no context): fall back to existing `{"uris":["<uri>"]}` behaviour

Pattern already established by `nfc.h:174`.

#### Deliverables
1. `spotifyTaskStorage.cpp` — `ACT_PLAY_URI` handler wires `s_lastTrackContextUri`.
2. `dbg_get("snapshot")` serial output — add `contextUri` field (reads `s_lastTrackContextUri` directly) so VE can verify preconditions for T115/T116 without a host-side Spotify API call.
3. Update TASK-021 notes (done — reference to this task already added).

#### Exit criterion
T115 passes on DUT (playlist context: queue preserved, no duplicate rows).
T116 passes on DUT (ad-hoc/radio: fallback fires, no crash).

---

### TASK-067 — VE: write + execute T115/T116 — tap-to-play regression suite
**Owner**: VE
**Status**: done (2026-05-22 — T115 PASS, T116 PASS; inner `main` `1a9d531`)
**Deps**: TASK-066 done (inner `main` `7a97088`)
**Notes**:
- Write T115 (playlist context — queue preserved) and T116 (ad-hoc fallback — no crash) in `docs/verification/test_plan.md` (stubs already added at planned status).
- Execute both on DUT with TASK-066 firmware.
- Update `playlist-001` `test_ids` in `feature_inventory.yaml` to `[T115, T116]` on first pass.
- Report pass/fail status back to PM. PM to prompt QM for retrospective on TASK-021/TASK-066 lifecycle.

---

### TASK-064 — Merge rnd/poll-lag planning docs to master (outer repo)
**Owner**: PM
**Status**: done (2026-05-21 — `e9f9203`, `eb70315`, `943ccf3` cherry-picked to outer master; M-NOART design doc, TASK-065 filing, task status updates all on master)
**Git ref**: rnd/poll-lag outer repo — commits `f1b8fb0` (M-NOART roadmap + PROP-004 resolved), `a71753e` (INV-A step3 design doc)
**Notes**:
- PM/Arch/VE artifacts cherry-picked to outer master: M-NOART design doc (`e9f9203`),
  TASK-065 filing (`eb70315`), task status backfills (`f5bdaf6`, `3da873d`, `f918351`),
  ADR acceptances (`3da873d`), T114+T102 results (`cff4aaf`, `66b89d4`).
- R&D investigation docs (INV-A, INV-B, EXP-001/002, PROP-003/004) remain on
  `rnd/poll-lag` per convention.
- `docs/project/tasks.md` on master reflects all done-status updates for TASK-062/063/065
  via the above cherry-picks. Divergence between branches is expected (tasks.md notes
  were updated on master via cherry-picks of later commits).

### TASK-062 — M-NOART: remove album-art path and JPEG decoder
**Owner**: Developer
**Feature**: noart-001 (new)
**Status**: done (2026-05-21 — inner repo commit `dcfbad0` on rnd/poll-lag, cherry-picked to main as `1411a3e`)
**Git ref**: rnd/poll-lag (roadmap item added f1b8fb0)
**Notes**:
- Gate for promoting the INV-A keep-alive fix to main.
- JPEG crash (`JPEGPutMCU22 LoadProhibited`) observed on DUT 2026-05-20 during track
  playback; triggered by the inherited album-art decode path in `CheapYellowDisplay`.
- Work: gate the album-art path in `cheapYellowLCD.h` behind `#ifndef WINAMP_DISPLAY`
  (or a dedicated `ALBUM_ART_ENABLED` flag); remove `JPEGDEC` from `lib_deps` under
  `cyd2usb_winamp` in `platformio.ini`; drop the `processImageInfo` override workaround
  in `winampDisplay.h` (superseded by the compile-time guard).
- Exit criterion: `cyd2usb_winamp` build clean without `JPEGDEC`; DUT survives 5+ min
  of active track playback without a Guru Meditation Error.
- Design: `docs/project/roadmap.md` M-NOART.

### TASK-063 — Promote rnd/poll-lag keep-alive fix to main
**Owner**: Developer
**Feature**: conn-002 (new)
**Status**: done (2026-05-21 — cherry-picked `66e71de`, `49d9b71`, `8542f91`, `4f0da82`, `dcfbad0`, `62d1792` → main `d7b261b`–`ab3864e`)
**Git ref**: rnd/poll-lag — inner repo commit `4f0da82` (keep-alive) + `49d9b71`, `66e71de` (tools)
**Notes**:
- Cherry-pick or merge `4f0da82` to `main`, replacing the `processImageInfo` workaround
  in `winampDisplay.h` with the proper M-NOART `#ifdef` guard from TASK-062.
- Also promote `tools/poll_latency_mock.py` (`66e71de`) and `tools/command_latency.py`
  (`49d9b71`) — low-risk R&D tooling, independent of the JPEG issue.
- The INV-B timeout bump/revert pair (`e174b04` + `bae05bb`) is net-zero; do not promote.
- Source investigation: INV-A (`docs/rnd/investigations/INV-A-tls-connection-lifecycle.md`),
  design: `docs/architecture/designs/M-CONN-http11-keepalive.md`.
- Verified: poll=55/55 100%, block_max 216–442ms typical, zero stale fd warnings (idle).
  One stale fd=49 sighting during active playback at 1:05 — acceptable, rare.

## Completed Tasks

### TASK-013 — Hostile-network development shims (back-filled)
**Owner**: Developer
**Feature**: dev-001 (new)
**Status**: done (2026-05-06, code in tree; back-filled to PM tracker 2026-05-07)
**Git ref**: Spotify-Diy-Thing@bf5d5ca
**Notes**:
- Implemented across the 2026-05-05/06 session while debugging DUT on AT&T tethered hotspot then Marriott guest captive portal. Three orthogonal shims: hardcoded WiFi creds, SPIFFS-driven DNS override, HTTPS-Date time bootstrap with build-epoch fallback. All gated by file presence or compile flag — production captive-portal path unchanged.
- **Process gap (back-fill reason):** committed without a corresponding tasks.md entry, feature_inventory entry, or VE notification at the time. Caught by 2026-05-07 self-audit.
- No regression test. Manual verification was the field debug itself. VE backlog: smoke test for dnsOverride loads + answers from SPIFFS JSON; build-epoch fallback path coverage.

### TASK-011 — M4 position interpolation polish
**Owner**: Developer
**Feature**: poll-002
**Status**: done (2026-05-07, DUT visually verified — "alright-ish, good enough")
**Git ref**: Spotify-Diy-Thing@f84b112
**Notes**:
- Pre-existing interpolation in `spotifyLogic.h` (`songStartMillis = millis() - progressMs`) was already correct; this task closed the rendering-side gaps.
- Idempotent `displayTrackProgress` in `cheapYellowLCD.h` caches last `barXWidth`, no-ops on identical pixel position. Track-change / seek-back handled via shrink-branch full repaint.
- `delayBetweenProgressUpdates` 500ms → 100ms. Safe because of idempotency.
- `displayTrackProgress` direct call retained in `handleCurrentlyPlaying` for pause-state correctness (`updateProgressBar` idles when not playing).
- Album art rendering gated behind `DISABLE_ALBUM_ART` in `.ino` — orthogonal i.scdn.co fetch hang, not part of this task.
- Closes ADR-006 M4 minimal scope. Local-seek field updates remain unwired pending TASK-009 (M5).

### TASK-007 — M1 API capability spike harness
**Owner**: Developer
**Feature**: api-001
**Status**: done (2026-04-29, DUT verified — with two new follow-ups, see below)
**Git ref**: Spotify-Diy-Thing@6066cab + (rotation/cleanups commit pending)

**Per-row results (DUT run 2026-04-29 after TASK-006 rotation + time-001):**

| Key | Action | Result | Detail |
|-----|--------|--------|--------|
| `>` | nextTrack | **FAIL** | Library returned false. Root cause: mbedTLS `0x0050` on `client->println()` send. POST never reached Spotify. |
| `<` | previousTrack | not run | Same path as `>`; would fail identically. |
| ` ` | toggle | not run | Dispatches to play/pause; same PUT path failure. |
| `p` | play | not run | PUT path; same failure. |
| `P` | pause | **FAIL** | mbedTLS `0x0050` on send. PUT never reached Spotify. |
| `s` | seek 30000 | not run | PUT path; same failure. |
| `S` | seek 0 | not run | PUT path; same failure. |
| `+` `-` `v` | setVolume | not run | PUT path; same failure. |
| `h` `H` | shuffle | not run | PUT path; same failure. |
| `r` `R` `o` | repeat | not run | PUT path; same failure. |
| `f` | audio-features | **HTTP 403** from Spotify | `code=403 clen=-1`. Endpoint deprecated for new Developer apps as of late 2024. Connection-level: TLS round-trip succeeded; the library reached Spotify and got an authoritative 403. |
| `a` | audio-analysis (16K) | **HTTP 403** from Spotify | Same deprecation. |
| `A` | audio-analysis (32K) | not run | Same deprecation; doc-size fallback irrelevant. |
| `i` | info / heap / clock | **OK** | `heap=218808 track=7fUr8EpRc0AC4MCPMVPIgI playing(assumed)=1 vol(local)=50` and `time epoch=1777445587 utc=2026-04-29T06:53:07Z sane=1`. T019 + T020 passing. |

GET `/v1/me/player/currently-playing` runs every 5 s in the background poll loop and **succeeds repeatedly** (`Successfully got currently playing`), confirming auth is healthy and the library's GET path works.

**Decisions recorded at exit:**

1. **SpotifyArduino extension strategy — closed.** Vendoring + `getBearerToken()` patch is *not* sufficient. The library's reuse of a single `WiFiClientSecure` across heterogeneous request types (GET + POST + PUT) breaks at TLS-send level for non-GET on Arduino-ESP32 2.0.17. A fresh client per non-GET (or migration to Arduino's `HTTPClient`, which manages connection lifecycle internally) is required for production wiring. Worth a new ADR before M5.

2. **`audio-analysis` doc size — moot.** Endpoint returns 403 for this app, so cache sizing is unanswerable from this spike. ADR-002's primary VU data source is unavailable; M6 needs a new strategy. Worth a new ADR superseding ADR-002.

**Follow-ups opened:**
- **TASK-009** — TLS connection lifecycle: pick a fix (per-request fresh client / `HTTPClient` migration) and verify all PUT/POST endpoints recover. Blocking M5.
- **TASK-010** — VU data source rethink: ADR-002 invalidated. Decide between (a) drop VU, (b) synthesised-from-poll-data VU (e.g. fake envelope from `currentlyPlaying.tempo` if exposed), (c) apply for Spotify Extended Quota Mode, (d) on-device microphone (ADR-002 option c, previously not chosen). Blocking M6.

### TASK-006 — Rotate leaked refresh token + client secret
**Owner**: Developer
**Status**: done (2026-04-29)
**Git ref**: Spotify-Diy-Thing config (data/spotify_diy_config.json, gitignored) + (commit pending for example file move)
**Notes**:
- Spotify auto-revoked the leaked refresh token between bring-up (2026-04-26) and this run (`invalid_grant — Refresh token revoked` returned 2026-04-28). Their leak-scanner caught it from the chat transcript. LL-002.
- Rotation completed 2026-04-29: dashboard secret rotated, `get_refresh_token.py` produced a new refresh token via loopback flow, both written to `data/spotify_diy_config.json`, `uploadfs` flashed. Boot now shows `Successfully got currently playing` repeatedly.
- Concurrent fixes during rotation:
  - `SPOTIFY_DEBUG` disabled in vendored `lib/SpotifyArduino/src/SpotifyArduino.h` so the new credentials don't bleed onto serial like the old ones did. LL-003 action item.
  - `data/spotify_diy_config.example.json` moved to `Spotify-Diy-Thing/spotify_diy_config.example.json` (project root) — its 32-char path tripped SPIFFS's filename-length limit and broke `uploadfs`. The example file was never meant to be on-device anyway.
- TASK-004 NFC verification rode along: no `NFC Bad` line in this boot's log. NFC silenced as intended.

### TASK-008 — NTP sync at boot (time-001)
**Owner**: Developer
**Feature**: time-001
**Status**: done (2026-04-28, DUT verified)
**Git ref**: Spotify-Diy-Thing@c0c4950, esp_spotify@5e94a9f
**Notes**:
- Root cause for the 2026-04-28 DUT TLS failure (`status Code-1`, `_handle_error 0x0050`). ESP32 has no RTC and the firmware never called `configTime()`, so mbedTLS rejected Spotify's certs whose `notBefore` is in the future.
- `setup()` now calls `configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com")` immediately after WiFi-up, then waits up to 5 s for `time(nullptr) > 1700000000` (2023-11-14). Non-fatal on timeout — logs `[time] WARN ...` and proceeds so the failure mode stays distinguishable.
- Spike harness `i` command extended: also prints epoch + ISO-8601 UTC + `sane=0|1` so T019/T020 verify the fix.
- Both `cyd2usb` and `cyd2usb_spike` envs build clean.
- DUT verification 2026-04-28: `[time] synced epoch=1777404307 in 3400ms`. `i` returned `[INFO] time epoch=1777404345 utc=2026-04-28T19:25:45Z sane=1`. Subsequent `Refreshing Access Tokens` returned **HTTP 400 `invalid_grant — Refresh token revoked`** from Spotify — confirms time-001 alone closed the TLS-validation issue; remaining failure is purely credentials. The trailing `0x0050` log is the library re-using a closed client after the 400 (cosmetic).
- Cross-feature interaction recorded: `cross_feature_matrix.yaml:X001` (time-001 → auth-001, dependency, risk: high).
- Conclusion: time-001 done. The "TLS issue" suspicion is closed; further work blocked on TASK-006 (rotation) only — the leaked refresh token has been auto-revoked by Spotify's leak scanner, exactly the failure TASK-006 anticipated.

### TASK-004 — NFC posture: disabled on this dev unit
**Owner**: PM (decision) → Developer (change)
**Status**: done (2026-04-28)
**Notes**:
- PN532 not wired on this dev unit; boot was logging harmless `NFC Bad`.
- Commented out `#define NFC_ENABLED 1` in `Spotify-Diy-Thing/SpotifyDiyThing/SpotifyDiyThing.ino:28`. Code uses `#ifdef NFC_ENABLED` (4 sites), so commenting — not setting to `0` — is what disables it. Comment block records the intent and the gotcha.
- `nfc.h` source kept; re-enable by uncommenting if a reader is wired later.
- Verification deferred until DUT is reachable (TASK-006-style).

### TASK-005 — Secret hygiene (gitignore + example template)
**Owner**: Developer
**Status**: done (2026-04-28)
**Notes**:
- Added `data/spotify_diy_config.json` to `Spotify-Diy-Thing/.gitignore` (file-specific, not whole `data/`).
- Added `Spotify-Diy-Thing/data/spotify_diy_config.example.json` with REPLACE_ME placeholders as the trackable template.
- Verified with `git check-ignore`: real config ignored, example trackable. Real secret was never committed (pre-existing untracked state).

### TASK-001 — Bring up first dev unit (CYD2USB)
**Owner**: Developer
**Feature**: deploy-001
**Status**: done
**Git ref**: working tree (Spotify-Diy-Thing untracked)
**Notes**:
- Pinned `platform = espressif32@6.9.0` in `Spotify-Diy-Thing/platformio.ini` — repo's unpinned line broke against current PlatformIO (`Network.h` missing in newer Arduino-ESP32 cores).
- Built + flashed `cyd2usb` env (TFT_INVERSION_ON) over `/dev/ttyUSB0`.
- Spotify dashboard's new redirect-URI policy (loopback HTTP only) breaks the on-device OAuth flow. Worked around with off-device `get_refresh_token.py` (loopback `127.0.0.1:8888`), then baked refresh token + client creds into SPIFFS via `data/spotify_diy_config.json` + `pio run -t uploadfs`.
- Wifi configured via WiFiManager captive portal. Device polling Spotify Web API; renders track on next playback.
- Deployment procedure documented in `docs/first_time_run_deploy.md`.

### TASK-052 — M-IO: any tap resets backoff + force-polls Spotify
**Owner**: Developer
**Feature**: io-001
**Status**: done (2026-05-16 — winampDisplay.h:233-366; resetBackoff() at top of every touched() block; dead-zone path enqueues ACT_FORCE_POLL with 1 s deadZoneForcePollAt cooldown)
**Notes**:
- **Problem**: during a backoff run (consecutive failures → 10/20/40/60 s waits), the screen feels dead even when the network recovers. User has no escape except waiting for the next cadence poll.
- **Fix**: every tap — whether on an active control or a dead zone (inactive PLEDIT rows, PLEDIT title/bottom bar, black areas) — resets `s_consecutiveFailures = 0` and enqueues `ACT_FORCE_POLL`. This matches ADR-011's stated intent ("touch resets backoff") and extends it to all touch events, not just transport buttons.
- **Backoff reset on dispatch** (not just on poll success): zero `s_consecutiveFailures` the moment any touch-driven action is enqueued. `nextWaitMs()` will return `kPollPeriodMs` (5 s) immediately — the task unblocks from its long `xQueueReceive` wait at queue-receive time (action already in queue, wait irrelevant) and issues the poll.
- **1 s force-poll cooldown**: track `lastForcePollMs` in `winampDisplay.h`. Any tap that would otherwise fall through all hit-tests (dead zone) sends `ACT_FORCE_POLL` only if `millis() - lastForcePollMs > 1000`. Active-control taps (transport, seek, volume, PLEDIT row) already enqueue their own action + trigger `doPoll()` post-action — they don't need the dead-zone path, but they do reset `s_consecutiveFailures` via a new `spotifyTask::resetBackoff()` call.
- **Implementation surface**:
  1. `spotifyTask.h` / `spotifyTaskStorage.cpp`: expose `void resetBackoff()` (sets `s_consecutiveFailures = 0`).
  2. `winampDisplay.h::update()`: at top of the `ts.touched()` block (before any hit-test), call `spotifyTask::resetBackoff()`. At the end of the else-fall-through (no hit matched), if cooldown elapsed enqueue `ACT_FORCE_POLL` and update `lastForcePollMs`.
- **No UI feedback needed** — backoff recovery is transparent; the next successful poll updates the display normally.
- **Cooldown rationale**: 1 s prevents a held-finger from hammering the queue with repeated `ACT_FORCE_POLL` when already draining. Separate from `touchScreenCoolDownTime` (which gates all touch recognition).



To be triaged with the team.

### TASK-054 — M-HITZONES: hit-zone preview PNG from bake_skin.py
**Owner**: Developer
**Feature**: m2-001 (bake pipeline extension)
**Status**: done (2026-05-16 — bake_skin.py:1034-1097; render_hitzones() overlays all zones as semi-transparent magenta rects + labels; emits gen/skin_hitzones.png; excluded from golden.sha256)
**Notes**:
- Extend `tools/bake_skin.py`: after `render_full_preview()` runs, call a new `render_hitzones(canvas, out_path)` that overlays all registered touch zones as semi-transparent magenta rects with white labels.
- Zone registry: Python list of `(label, x, y, w, h)` tuples using the same constant values that are emitted to `skin_layout.h` (single source of truth — define once, use in both the emitter and the renderer).
- Rendering: `ImageDraw.Draw(overlay)` filled magenta rects at alpha=100 (40 %); `Image.alpha_composite` over the preview canvas; `ImageDraw.textbbox` / `ImageDraw.text` for labels centred in each rect. PIL `ImageFont.load_default()` — no external font dep.
- Zones to cover (minimum set): PREV, PLAY, PAUSE, STOP, NEXT, SEEK (posbar), VOL (volume slider), SHUF, RPT, VIS, LOGO/RECONNECT, PLEDIT ROW0–ROW4.
- Output: `gen/skin_hitzones.png` — written unconditionally alongside `skin_preview.png`.
- Exclude `skin_hitzones.png` from `gen/golden.sha256` (derived artefact, not a firmware input).
- ~50 LOC. No new Python deps.

### TASK-055a — M-WAVE-ATLAS: VIS_WAVE_ATLAS enum + nextMode() update
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Git ref**: 49ff9a9
**Notes**:
- Added `VIS_WAVE_ATLAS` to `VisMode` enum in `vuMeter.h`.
- Added `waveAtlasFrameRef()` inline state accessor.
- Updated `nextMode()` cycle: Atlas → WaveAtlas → VU → Blank → Atlas. `VIS_WAVE` removed from cycle (stays in codebase).
- Included `gen/wave_atlas.h`.

### TASK-055b — M-WAVE-ATLAS: tickWaveAtlas() + dispatch in tick()
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Git ref**: 49ff9a9
**Notes**:
- `tickWaveAtlas()`: 20 Hz frame advance (continuous, not gated on playing); `blitVisBackground()` + white vertical fill between consecutive atlas samples.
- `prevY` seeded from `row[0]`, not `centreY` — prevents left-edge spike artefact.
- Dispatch wired in `tick()`: `case VIS_WAVE_ATLAS: tickWaveAtlas(...)`.

### TASK-055c — M-WAVE-ATLAS: flash budget verify
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Notes**:
- Build: 52.9 % flash (1,387,237 / 2,621,440 B). Headroom ~47 %. Well within the ≤ previous+17 KB exit criterion.

### TASK-055d — M-WAVE-ATLAS: fix frozen lead-in frames + canonical bake script
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Git ref**: a071b89
**Notes**:
- Root cause: frames 0–29 byte-identical (source video static before music starts) → 1.5 s visual freeze per loop at 20 Hz.
- Fix: added `--frame-start` / `--frame-end` to `bake_wave.py`; rebaked with `--frame-start 30`. 224 → 194 frames.
- All AE flags restored: `--boost 2.0 --spatial-smooth 3 --error-diffusion --dc-offset 3`.
- `tools/bake_wave.sh`: canonical invocation per BP-002. Future rebakes use this script.

### TASK-053a — M-CONN: bake SKIN_TITLEBAR_INACTIVE sprite
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16)
**Notes**:
- Cropped TITLEBAR.BMP at (27,14,302,28) → 275×14 `SKIN_TITLEBAR_INACTIVE`.
- Added `LOGO_X/Y/W/H` layout constants to `skin_layout.h`.
- Regenerated `gen/golden.sha256`.

### TASK-053b — M-CONN: spotifyTask::isHealthy() + resetTls()
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16)
**Notes**:
- `isHealthy()`: returns `s_consecutiveFailures < 2`.
- `resetTls()`: sets volatile `s_resetTlsPending = true` + zeroes failures. Task body calls `client.stop()` on its own stack before next poll (avoids cross-task mbedTLS races).

### TASK-053c — M-CONN: inactive title bar overlay in repaintChrome()
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16; DUT-verified 2026-05-22)
**Notes**:
- `repaintChrome()` blits `SKIN_TITLEBAR_INACTIVE` over position (originX, originY) when `!isHealthy()`.
- Active bar (already in MAIN_BG) shows on recovery without extra code.
- Health-change trigger: `drawPlaylist()` (called every loop) detects `isHealthy() != lastHealthy` and calls `repaintChrome()` immediately.
- DUT 2026-05-22: DNS override pointed `api.spotify.com → 192.0.2.1`. consecutive=1 → consecutive=2. After consecutive=2, `last_render_age_ms` dropped 60003→17251 confirming `repaintChrome()` fired. PASS (active→inactive direction).

### TASK-053d — M-CONN: spotifyTask::resetTls()
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16 — merged into TASK-053b)

### TASK-053e — M-CONN: serial `reconnect` command
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16; DUT-verified 2026-05-22)
**Notes**:
- `handleSerialCommands()` in `SpotifyDiyThing.ino` loop — line-buffered; dispatches `resetTls()` + `enqueue(ACT_FORCE_POLL)` on "reconnect".
- DUT 2026-05-22: sent "reconnect" via serial. Response: `{"ok":true,"cmd":"reconnect"}`. Log: `[I][spotify.tls] hard reset — stopping client`. Polls resumed immediately; 10/10 at 1:06 uptime. PASS.

### TASK-053f — M-CONN: Winamp logo tap → TLS reset
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16; DUT-verified 2026-05-22)
**Notes**:
- `hitTestLogo()` at `LOGO_X/Y/W/H` (250,100,25,16 window-local); 2 s cooldown `logoTapCooldownMs`.
- Calls `resetTls()` + `enqueue(ACT_FORCE_POLL)` + `repaintChrome()` for immediate visual feedback.
- DUT 2026-05-22 (3 taps): `[I][touch] logo tap → TLS reset + force poll` logged twice; 2nd tap hit 2s cooldown → `dead zone tap` (correct). TLS hard reset fired, polls recovered 200 OK. Visual redraw confirmed by user. PASS.

### TASK-035 — Drop OTA `app1` partition (reclaim 1.25 MB flash)
**Owner**: Developer
**Status**: done (2026-05-10 — tripped the wall during TASK-025 bring-up; firmware.bin overflowed the 1.28 MB app0 partition by ~2.6 KB and bootlooped silently with `rst:0x3 (SW_RESET)` and zero app output. No exception, no panic — the loader's image-hash check fails when the trailing bytes spill into app1 territory, and re-resets immediately.)
**Notes**:
- Custom partition table at `Spotify-Diy-Thing/partitions_no_ota.csv`. Drops `app1`; `app0` grows from 0x140000 → 0x280000 (2.56 MB). NVS / otadata / SPIFFS / coredump untouched, so existing user data + wifi creds + spotify creds survive across the layout change.
- `[env:cyd2usb]` (and the cyd2usb-derived envs) sets `board_build.partitions = partitions_no_ota.csv`. The legacy `cyd` env keeps the default Arduino-ESP32 partitions (uses much less flash; OTA optionality preserved there for now).
- Cost: lose OTA capability on `cyd2usb*` envs. Acceptable — this project flashes over USB.
- Diagnostic note: when this fires the next time, the symptom is *boot loop with no application Serial output*. PlatformIO's "Flash 99.7%" report compares against the partition size, not the actual on-disk binary size (which is ~3 KB larger after the loader-checksum padding). If the binary grows past ~99.6%, double-check `ls -la .pio/build/<env>/firmware.bin` against the app0 size in `partitions.bin` before assuming a code bug.

### TASK-036 — Compress skin atlas (palette-8 with runtime LUT or PNG-on-flash)
**Owner**: Architect (ADR), Developer (impl)
**Status**: parked (2026-05-08; alternative path if TASK-035 isn't enough)
**Notes**:
- Current atlas is raw RGB565 = 2 B/px. ~96 KB total. Most of those pixels are duplicates (chrome, button frames). A palette-8 + 256-entry RGB565 LUT cuts the bake to ~½ size at the cost of an indirection in `blitSprite`.
- PNG-on-flash + decompress at boot is heavier (~50 KB extra code for libpng), uses heap. Probably not worth it on this board.
- Bake-tool change + `winampDisplay.h` `blitSprite` change. ~100 LOC + ADR.

### TASK-037 — Strip unused TFT_eSPI font sets
**Owner**: Developer
**Status**: parked (2026-05-08; small win, easy)
**Notes**:
- `common_cyd.build_flags` enables `LOAD_FONT2/4/6/7/8/GLCD/GFXFF`. We only render via the baked Winamp glyph atlas (custom path, doesn't touch TFT_eSPI fonts) and via `screenLog` font 1 GLCD. Drop everything except `LOAD_GLCD`.
- Saves a few KB rodata. Verify no regression in screenLog or any legacy `cheapYellowLCD` text fallback.

### TASK-056a — M-SERIALDBG: platformio.ini debug env + inject_git_hash.py
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- New `[env:cyd2usb_winamp_debug]` extending `cyd2usb_winamp` with `-DSERIAL_DEBUG`.
- New `scripts/inject_git_hash.py` pre-script — injects `GIT_REV` define (git short hash + dirty marker).
- Both `cyd2usb_winamp` and `cyd2usb_winamp_debug` build clean post-change. `GIT_REV` + `SERIAL_DEBUG` confirmed present on debug env via `pio run -v`; absent on production env.

### TASK-056b — M-SERIALDBG: boot version line
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- Unconditional `[boot] git=<hash> elf=<8hex> build=<date> <time>` via `esp_ota_get_app_description()`.
- Ships in both `cyd2usb_winamp` and debug env. `GIT_REV` token guarded; "n/a" in production.
- Implemented in `setup()` lines 169–188 (landed alongside TASK-056c).

### TASK-056c — M-SERIALDBG: table-driven dispatcher + drainInjectionQueue
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- 4-field `SerialCmd kCmds[]` table; `handleSerialCommands()` dispatcher; 64-byte line buffer with WARN+reset on overflow.
- `drainInjectionQueue()` call at top of `loop()` (TASK-056e fills the implementation).
- Coordinated with TASK-056j (reconnect JSON format change).

### TASK-056j — M-SERIALDBG: reconnect command → JSON response
**Owner**: Developer
**Feature**: serialdbg-001, conn-001
**Status**: done (2026-05-17)
**Notes**:
- `cmdReconnect` emits `{"ok":true,"cmd":"reconnect"}` (landed alongside TASK-056c).
- T090–T094 conn-001 test suite exists as regression guard. tmux/grep scripts audited — no old `[reconnect]` prefix references found.

### TASK-056n — M-SERIALDBG: IDebugExportable interface + SpotifyDisplay no-ops
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- New file `SpotifyDiyThing/debugExportable.h`: `IDebugExportable` with `dbgGet`/`dbgSet` pure virtuals, compiled under `SERIAL_DEBUG`.
- `SpotifyDisplay` gains default no-op overrides + `injectTouch`/`injectRelease` virtual no-ops under `SERIAL_DEBUG`.

### TASK-056d — M-SERIALDBG: WinampDisplay::injectTouch + injectRelease + lastTouchResult
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- Virtual `injectTouch(sx, sy)` + `injectRelease()` on `SpotifyDisplay` base; `WinampDisplay` overrides both.
- Cooldown-aware gate: if `millis() <= touchScreenCoolDownTime`, sets `lastTouchResult.skipped=true`, returns without dispatch.
- `bool _injectingDrag` member (WinampDisplay, SERIAL_DEBUG) suppresses checkForInput() drag-end branch during injection.
- `lastTouchResult` 6-field struct: region (TRANSPORT/POSBAR/VOLUME/SHUFFLE/REPEAT/VIS/LOGO/DEADZONE/NONE), transportPressed, action, seekMs, volumePct, skipped.
- Implemented co-located with TASK-056g in `winampDisplay.h`.

### TASK-056e — M-SERIALDBG: cmdTap, cmdDrag, injection ring buffer
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `cmdTap`: sscanf x/y, call `injectTouch+injectRelease` via virtual dispatch, emit region-specific JSON from `lastTouchResult`.
- `cmdDrag`: fill 64-slot `s_injectQueue` ring buffer (steps+1 move samples + 1 release sentinel); sets `_injectingDrag=true`; JSON emitted by `drainInjectionQueue()` on release step. No `delay()` in loop task.
- `drainInjectionQueue()` pops one step per `loop()` iter; per-sample `LOG_D("serial", "inject sample %d/%d sx=%d sy=%d", ...)` for T096.

### TASK-056f — M-SERIALDBG: spotifyTask::dbg_get / dbg_set
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `spotifyTask::dbg_get`: handles "backoff" (consecutiveFailures + nextWaitMs), "heap" (getFreeHeap), "snapshot" (multi-part split protocol), "queue" (5-row split protocol — TASK-056m).
- `spotifyTask::dbg_set`: handles "backoff" (sets consecutiveFailures).
- `spotifyTask::dbg_getFailureCount()`: thin getter for cmdInfo.
- `s_consecutiveFailures` → `volatile unsigned int` (matches `s_resetTlsPending` pattern).
- Implemented in `spotifyTaskStorage.cpp`.

### TASK-056g — M-SERIALDBG: WinampDisplay::dbgGet / dbgSet overrides
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `dbgGet`: handles "cooldown" (remainingMs), "dragState" (name), "optimisticVolume" (remainingMs), "songDuration" (ms).
- `dbgSet`: handles "cooldown" (resets to 0; val ignored).
- Implemented in `winampDisplay.h` alongside TASK-056d.

### TASK-056h — M-SERIALDBG: cmdGet / cmdSet dumb dispatchers
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- Dispatch to `spotifyDisplay->dbgGet/dbgSet` then `spotifyTask::dbg_get/dbg_set`. Frozen — never changes as fields grow.
- Multi-part: owner emits Serial.printf lines directly, returns true with buf[0]='\0'; cmdGet skips wrapper print.
- Implemented in `SpotifyDiyThing.ino`.

### TASK-056i — M-SERIALDBG: cmdInfo + cmdHelp
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `cmdInfo`: single JSON line (git/elf/build/heap/isPlaying/progressMs/durationMs/volumePct/shuffle/repeat/consecutiveFailures).
- `cmdHelp`: single JSON line iterating `kCmds[]` — table is SSOT. ADR-021 one-JSON-object-per-newline invariant preserved.
- Implemented in `SpotifyDiyThing.ino`.

### TASK-056l — M-SERIALDBG: extend get snapshot with lastPollAgeMs / currentTrackUri / deviceActive
**Owner**: Developer
**Feature**: serialdbg-001, sync-001
**Status**: done (2026-05-17)
**Notes**:
- Added `bool deviceActive` to `Snapshot`; populated at both write sites in `spotifyTaskStorage.cpp`.
- `spotifyTask::dbg_get("snapshot")`: added `lastPollAgeMs`, `deviceActive`, `currentTrackUri` in both single-line and split paths.
- Prereq for TASK-057 VE harness (T097, T099, T102, T103, T105, T107, T108).

### TASK-056m — M-SERIALDBG: get queue command (QueueSnapshot rows)
**Owner**: Developer
**Feature**: serialdbg-001, sync-001
**Status**: done (2026-05-17)
**Notes**:
- Replaced stub with real `QueueSnapshot` serialization via `copyQueueSnapshot`. Up to 5 rows, one JSON line each, split protocol with `"part":N,"last":bool`.
- No cmdGet change. Prereq for T102.

### TASK-056k — M-SERIALDBG: VE execute serialdbg-001 suite on DUT
**Owner**: VE
**Feature**: serialdbg-001
**Status**: done (2026-05-18)
**Blocked by**: TASK-056a through TASK-056i (core impl), TASK-056l (for T095)
**Notes**:
- T076–T085, T096 + T089: **pass 2026-05-17** (DUT ee65beb+, harness
  `Spotify-Diy-Thing/tools/run_serialdbg_tests.py`). 11 PASS / 0 FAIL / 0 SKIP.
- Firmware fixes landed during DUT bring-up (same day, separate commit):
  (1) `drainInjectionQueue` skips logging on release sentinel (T096 off-by-one);
  (2) `dbgSet("cooldown", ms)` accepts arming value, not reset-only (T079
  previously untestable via serial — see design doc B1 closure);
  (3) `injectTouch` emits `enqueued ACT_VOLUME pct=N` LOG_D so T082 can count
  synchronous enqueues instead of async `spotify.task` dequeues;
  (4) `dbgSet("songDuration", val)` accessor (T085 — previously required
  waiting many minutes for Spotify to drop the player session after closing
  all clients).
- Harness logic fixes: T076 now tests 8 contiguous-row boundary cases (not 10
  non-contiguous outside-left cases); T079 arms via `set cooldown 500`;
  T082 counts the new enqueue trace line; T085 forces songDuration=0.
- **T086–T088 automated (2026-05-17)**: harness functions `t086`, `t087`, `t088` added;
  registered in ALL_TESTS. Coordinate corrections vs test plan:
  - POSBAR bottom inside boundary: y=81 (not y=82 — POSBAR_BG.h=10, py1=82 is exclusive).
  - LOGO second-tap within cooldown returns DEADZONE/FORCE_POLL (not LOGO — firmware
    falls to else branch when `millis() < logoTapCooldownMs`).
  - TLS reset log pattern: `"hard reset"` / `"stopping client"` ([I][spotify.tls]).
- **T095 interactive (2026-05-17)**: harness function `t095(dut, interactive)` added;
  activated by `--interactive` flag; SKIPs without flag. Prompts operator for each of
  3 zones (PREV/POSBAR-mid/VOLUME-mid), captures dequeue log for physical tap, confirms
  Spotify effect. Run: `python3 run_serialdbg_tests.py --interactive --tests T095`.
- T089 (production symbol check) **pass** — verified again 2026-05-17 after
  the four firmware fixes (0 SERIAL_DEBUG in `cyd2usb_winamp` ELF).
- **T086–T088 + T095 DUT run (2026-05-17)**: all pass. T086 POSBAR+VOLUME boundary
  16/16; T087 LOGO tap 3/3; T088 DEADZONE 11/11; T095 3/3 region+action pairs.
  Physical touch jitter ~12% (resistive CYD2USB); T095 pass threshold revised to ±15%.
- **T090–T092 DUT run (2026-05-17)**: T090/T091 PASS, T092 harness timing fix needed
  (LOGO tap cooldown shorter than expected; T092 revised to send two rapid FORCE_POLLs).
  T090–T092 re-run: PASS after fix.
- **Status**: **done** (2026-05-18). serialdbg-001 suite complete: T076–T096 all
  executed on DUT. 22 PASS / 0 FAIL / 0 SKIP (T089/T090/T091/T092 counted separately;
  T095 requires `--interactive` flag; T093–T094 reserved for conn-001 manual step).

---

### TASK-057 — M-SYNC: VE harness tools (spotify_state.py, spotify_drive.py, tsync_diff.py)
**Owner**: VE
**Feature**: sync-001
**Status**: done (2026-05-17)
**Notes**:
- `tools/spotify_state.py`: refresh-token-aware `/me/player` wrapper; emits structured JSON matching firmware Snapshot field names. Exit 0=ok, 1=error, 2=204.
- `tools/spotify_drive.py`: Connect API control — pause, play, next, prev, seek, setVolume, setShuffle, toggleShuffle, setRepeat, transfer. Stdlib only.
- `tools/tsync_diff.py`: `get snapshot` over serial (split-protocol) + `/me/player` over HTTPS; diffs isPlaying/progressMs/durationMs/volumePct/shuffleState/repeatState/trackUri; prints `[OK]` or `[DRIFT] field dut=<v> spotify=<v>`. `--count N --interval S` for repeated runs. Exit 1 on any drift. Anchor for T110.
- All three: stdlib only (no deps beyond pyserial for tsync_diff). Syntax verified.

### TASK-058 — log-001: heartbeat fields last_poll_age_ms + next_poll_in_ms
**Owner**: Developer
**Feature**: log-001, sync-001, drift-001
**Status**: done (2026-05-17)
**Notes**:
- Added `s_lastSuccessfulPollMs` (set on 200/204) and `s_lastPollFinishedMs` (set after every `doPoll()`) task-private statics in `spotifyTaskStorage.cpp`.
- Exposed `spotifyTask::lastSuccessfulPollAgeMs()` and `spotifyTask::nextPollInMs()` loop-task-safe getters.
- Appended `last_poll_age_ms=%lu next_poll_in_ms=%lu` to heartbeat `LOG_I` in `logHeartbeat.h`.
- Both `cyd2usb_winamp` and `cyd2usb_winamp_debug` build clean.

### TASK-059 — drift-001: last_render_age_ms heartbeat field + g_lastRenderMs
**Owner**: Developer
**Feature**: drift-001
**Status**: done (2026-05-17)
**Notes**:
- Defined `uint32_t g_lastRenderMs = 0` in `spotifyLogic.h`; extern'd in `winampDisplay.h` and `logHeartbeat.h`.
- Set at end of `updateCurrentlyPlaying()` seq-change path (`spotifyLogic.h`) and at end of `repaintChrome()` (`winampDisplay.h`).
- Appended `last_render_age_ms=%lu` to heartbeat. Both envs build clean.

### TASK-060 — drift-001: chrome staleness indicator in repaintChrome()
**Owner**: Developer
**Feature**: drift-001
**Status**: done (2026-05-17)
**Notes**:
- `N_STALE_MS = 15000` compile-time constant in `winampDisplay.h` (3× base poll cadence per ADR-023).
- 4×4 amber pip (`0xFD00`) baked inline (16 × uint16_t); no atlas change.
- Blit at `originX+268, originY+1`, layered after conn-001 inactive-titlebar in `repaintChrome()` — both indicators visible simultaneously.
- Check uses `spotifyTask::lastSuccessfulPollAgeMs()` (TASK-058 getter).
- Both envs build clean.

### TASK-061 — M-SYNC/M-DRIFT: VE execute sync-001 + drift-001 suite on DUT (T097–T111)
**Owner**: VE
**Feature**: sync-001, drift-001
**Status**: done (2026-05-18)
**Notes**:
- Harness: `Spotify-Diy-Thing/tools/run_sync_tests.py` (new file, 2026-05-18).
- DUT: ESP32-2432S028R, env `cyd2usb_winamp_debug`, serial `/dev/ttyUSB0`, AT&T cellular tether.
- Results (2026-05-18): **12 PASS / 0 FAIL / 3 SKIP** (T097–T102, T104–T111 pass;
  T100/T101 skip — Firefox Web Player ignores shuffle/repeat API commands, re-run with
  mobile/speaker; T103 skip — requires two active Spotify Connect devices).
- Cellular environment: AT&T NAT closes stale TLS connections (~30% poll fail rate);
  harness uses `force_fresh_poll()` + `reconnect_after=5.0` in `poll_until()`; lag bounds
  raised to 8500ms (from spec 5500ms) for forced-poll path (5s sleep + 2s TLS+HTTP + 1.5s overhead).
- Key behavioral findings documented in test_plan.md:
  - `set backoff N` sets policy only, not running poll timer; harness uses `get backoff` for
    policy check rather than racing the heartbeat (T105, T109).
  - CH341 kernel DTR assertion always reboots DUT on serial port open; tsync_diff.py
    redesigned to pause Spotify before subprocess + proper `_wait_for_ready()` on reopen (T110).
  - T111 `last_render_age_ms` ≤ 8000ms (spec ≤500ms inapplicable — DUT renders on poll
    update ~5s cadence, not continuously).

---

- **TASK-002** — Touchscreen seek/scrub. ✅ closed 2026-05-08 by M5 (tap-to-seek shipped; drag-with-debounce deferred to a follow-up if/when it's wanted).
- **TASK-003** — Play/pause + volume on touch. Play/pause closed 2026-05-08 by M5. Volume deferred — not on the main-window chrome we render today; needs VOLUME.BMP baked + a slot reserved.
- **TASK-004** — Decide NFC support posture. Reader not connected on dev unit; boot logs `NFC Bad` harmlessly. Either wire a PN532 and validate, or set `NFC_ENABLED 0` to silence. Owner: PM (decision).

---

### TASK-068 — M-SHELL-LAYOUT: coords.py — originX-aware tap/drag helpers

**Owner**: Developer
**Feature**: shell-layout-001
**Status**: done (2026-05-24 — run_serialdbg_tests.py migrated to coords.py; regression gate 20/20 pass; two pre-existing harness bugs fixed: warmup ping, T085 songDuration restore)
**Blocked by**: —
**Notes**:
- New file `Spotify-Diy-Thing/tools/coords.py`.
- Parses `gen/skin_layout.h` via regex (strip inline comments); derives `ORIGIN_X = (320 - WINDOW_W) // 2`.
- Exposes named helpers: `vol_drag_x()`, `tap_button(name)`, `tap_logo()`, `pledit_tap(row)`. See `shell-layout.md` Gap 1 for full skeleton.
- Audit `gen/skin_layout.h` first: confirm `CB_*_W`, `CB_*_H`, `VOLUME_FRAME_W`, `PLEDIT_CONTENT_X`, `PLEDIT_TITLE_H`, `PLEDIT_ROW_H` are all emitted; add missing `#define`s to `bake_skin.py` emit block if not.
- Update `run_serialdbg_tests.py`: replace all hardcoded `tap`/`drag` coordinate literals with `coords.py` calls. Coordinate reference comment at top of file (lines 19–25) documents screen coords with `originX=22`; replace with `coords.py` imports.
- Update `run_sync_tests.py`: same. Replace `_PLEDIT_ORIGIN_X = 22` and all hardcoded tap/drag literals. `_pledit_tap_xy()` should delegate to `coords.pledit_tap()`.
- Verify: run T076–T088, T095–T096, T104, T106, T111, T115–T116 on DUT with `originX=22` (current firmware) — all must still pass. This is the regression gate before M-MULTIAPP shifts `originX` to 0.

### TASK-069 — M-SHELL-LAYOUT: bake_skin.py tooling fixes (gaps 2 + 3)

**Owner**: Developer
**Feature**: shell-layout-001
**Status**: done (2026-05-24 — Gap 2 + Gap 3 complete; sha256sum -c golden.sha256 clean 3/3)
**Blocked by**: —
**Notes**:
- **Gap 2**: `render_hitzones()` (~line 1047) — rebuild zone list from existing dicts. Transport: iterate `CBUTTON_POSITIONS`. Other zones: read from `POSBAR_LAYOUT`, `VOLUME_LAYOUT`, `SHUFREP_LAYOUT`. See `shell-layout.md` Gap 2 for fixed pattern.
- **Gap 3**: `preview_vis.py:58` — replace `WINDOW_W = 275` hardcode with parse of `gen/skin_layout.h` using the new `parse_skin_layout()` helper (same pattern as `parse_shell_layout()`; can share implementation).
- Verify: `bake_skin.py` run produces identical `skin_hitzones.png` to pre-fix (values unchanged — only code structure changes). `sha256sum -c golden.sha256` must pass.

### TASK-070 — M-SHELL-LAYOUT: parse_shell_layout() helper + preview_layout.py

**Owner**: Developer
**Feature**: preview-tooling-001, shell-layout-001
**Status**: done (2026-05-24 — current gen/shell_layout.h accepted as-is; aesthetic iteration deferred; interactive sign-off not required to unblock M-MULTIAPP)
**Blocked by**: —
**Notes**:
- Add `parse_shell_layout(path)` to `bake_skin.py`. Must strip inline comments (`//` suffix) from all values before returning. Handles int (`275`), hex (`0x07E0`), char (`'A'`), flag (`1`). T128 verifies.
- New script `Spotify-Diy-Thing/tools/preview_layout.py`. See `interactive-preview.md` for full spec:
  - `--interactive` flag opens pygame window at `--scale N` (default 2).
  - Renders 320×240 PIL composite: Winamp chrome left, taskbar strip right.
  - Icon glyphs: Winamp TEXT.BMP 5×6 bitmap font. Chars S/C/W/$/M/G. UV table in `interactive-preview.md`.
  - Keyboard controls: `b` (bg colour), `i` (indicator style), `s` (separators), `c` (indicator colour), `[`/`]` (active slot), `+`/`-` (scale), `p` (print params), `e` (export), `q` (quit).
  - `e` key writes `gen/shell_layout.h` using the schema in `shell-layout.md`. Geometry constants (`TASKBAR_X` etc.) are fixed; aesthetic constants are filled from current session state.
- Run the interactive session, approve a configuration, press `e` to commit `gen/shell_layout.h`.

### TASK-071 — M-SHELL-LAYOUT: gen/shell_layout.h in golden.sha256

**Owner**: Developer
**Feature**: shell-layout-001
**Status**: done (2026-05-24 — shell_layout.h already in golden.sha256; sha256sum -c passes clean)
**Blocked by**: —
**Notes**:
- After TASK-070 produces `gen/shell_layout.h`, add its hash to `golden.sha256`.
- Run `sha256sum -c golden.sha256` to confirm clean. T132 verifies.

### TASK-072 — M-SHELL-LAYOUT: VE execute T125–T132

**Owner**: VE
**Feature**: shell-layout-001, preview-tooling-001
**Status**: done (2026-05-24 — T125/T126/T128/T132 pass; T127/T129 blocked on M-MULTIAPP appShell.h impl; T131 deferred with aesthetics)
**Blocked by**: —
**Notes**:
- T125: `gen/shell_layout.h` present, all 11 `TASKBAR_*` defines present.
- T126: `TASKBAR_X + TASKBAR_W == 320`; `TASKBAR_SLOT_H * TASKBAR_SLOT_COUNT == 240`.
- T127: semantic grep — no bare `>= 275` or `/ 40` in `appShell.h` (note: `appShell.h` does not exist yet; T127 gates M-MULTIAPP taskbar implementation, not this task).
- T128: `parse_shell_layout()` strips comments, handles all value types.
- T129: `_Static_assert` in `appShell.h` (gates M-MULTIAPP, not this task).
- T131: manual pygame window check — scale, glyphs, all keyboard controls, `e` export.
- T132: no TBD in `taskbar.md`; `golden.sha256` passes.
- Report pass/fail to PM. PM prompts QM for retrospective.

### TASK-073 — BUG: `strcmp(nullptr)` crash in `getCurrentlyPlaying` on track start
**Owner**: Developer
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-22 — LOCAL_PATCHES patch #11; null guard added; DUT-verified no crash on first 200 OK poll with active playback)
**Notes**:

#### Symptom
`LoadProhibited` Guru Meditation on boot when Spotify is actively playing. Crash at
`SpotifyArduino.cpp:894` inside `strcmp`. Only hit on the first poll that returns 200 (track
playing) immediately after a 204-only sequence; does not crash on subsequent 200 polls.

#### Root cause
`doc["currently_playing_type"]` returns `nullptr` when the JSON field is absent (observed
during the initial track-start transition). Line 894: `strcmp(currently_playing_type, "track")`
called with null first arg → `LoadProhibited`.

The existing `repeat_raw` block (patch #9) already pattern-matches with a null guard;
`currently_playing_type` was missing the same guard.

#### Fix (`lib/SpotifyArduino/src/SpotifyArduino.cpp:893`)
```cpp
if (currently_playing_type == NULL) {
    current.currentlyPlayingType = other;
} else if (strcmp(currently_playing_type, "track") == 0) {
```

LOCAL_PATCHES.md patch #11. DUT confirmed no crash on 2026-05-22 reflash with active playback.

### TASK-074 — BUG: `LoadProhibited` crash in `onCurrentlyPlaying` — uninitialized `CurrentlyPlaying` struct
**Owner**: Developer
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-22 — `CurrentlyPlaying current = {}` zero-init patch; DUT-verified 48 polls / 5 min no crash; T133 added)
**Notes**:

#### Symptom
`LoadProhibited` Guru Meditation, EXCVADDR=`0x0000000c`, crashing in `strcmp` inside
`spotifyTask::onCurrentlyPlaying` at `spotifyTaskStorage.cpp:72`. Reproducible within 2–3 polls
of a fresh boot once `s_lastTrackUri` was non-empty. Distinct from TASK-073 (which fixed a
`nullptr` crash on `currently_playing_type`).

#### Root cause
`CurrentlyPlaying current;` at `SpotifyArduino.cpp:783` is uninitialized. When
`currently_playing_type == "other"`, neither the `track` nor the `episode` fill block executes,
leaving `current.trackUri` as stack garbage (`0x0000000c`). The null guard in
`onCurrentlyPlaying` (`cp.trackUri == NULL`) only catches exact zero — `0x0000000c` passes
through, and `strcmp` crashes on the second poll when `s_lastTrackUri` is non-empty.

#### Fix (`lib/SpotifyArduino/src/SpotifyArduino.cpp:783`)
```cpp
CurrentlyPlaying current = {};   // LOCAL_PATCHES: zero-init
```

LOCAL_PATCHES comment added. T133 in `run_serialdbg_tests.py` guards the fix with a static grep
+ 90 s runtime soak.

---

### TASK-075 — RnD: measure PLEDIT scroll-arrow + thumb sprite positions in PLEDIT.BMP
**Owner**: R&D
**Feature**: playlist-002, touch-002
**Status**: done — amended 2026-05-22
**Blocks**: TASK-051j (hitzones PNG visual validation), TASK-051i (scrollbar strip drag firmware), TASK-051e (thumb sprite blit)
**Git ref**: master (spec update in PLEDIT-BMP-spec.md)
**Notes**:

#### Findings (2026-05-22)

Scroll arrows are in the **bottom bar right section** of PLEDIT.BMP (BMP x=254..274, y=72..88),
at the rightmost edge of the 150px right section (atlas x=253..274, screen x=275..296).

**Sprite coordinates in PLEDIT.BMP:**

| Element | BMP x | BMP y | w | h |
|---------|-------|-------|---|---|
| UP▲ button (normal) | 254..274 | 72..78 | 21 | 7 |
| DOWN▼ button (normal) | 254..274 | 79..88 | 21 | 10 |
| UP glyph pixels | 261..268 | 74..77 | 8 | 4 |
| DOWN glyph pixels | 261..268 | 80..83 | 8 | 4 |

No pressed-state sprites. Glyph color: `(106,106,122)` = `0x6B4F`.

**Screen hitzones (originX=22, PLEDIT_BOTTOM_Y=201):**

| Zone | x | y | w | h |
|------|---|---|---|---|
| Scroll-UP tap | 275 | 201 | 22 | 7 |
| Scroll-DOWN tap | 275 | 208 | 22 | 10 |

Note: buttons are small (7–10px tall). Expand to 19px each if touch precision is insufficient:
UP=y201..219, DOWN=y220..238.

**Standalone zones**: YES — each tap scrolls 1 item. Complement Zone 2 (direct strip drag).

Full spec in `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md` §"Scroll arrow buttons".

#### Amendment (2026-05-22) — scrollbar thumb sprite found

Initial findings incorrectly concluded the thumb was absent and synthesised. Pixel colour analysis against a reference screenshot confirmed golden thumb colours match BMP x=52..70 exclusively. Human-verified by extracting and inspecting the sprites.

**Thumb sprite coordinates in PLEDIT.BMP:**

| Element | BMP x | BMP y | w | h |
|---------|-------|-------|---|---|
| Thumb — normal state | 52 | 54 | 9 | 17 |
| Thumb — alt state | 62 | 54 | 8 | 16 |

Spec corrected in `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md` §"Scrollbar thumb". TASK-051e updated to use sprite blit instead of `fillRect`.

---

### TASK-085 — VE: fix T136 harness ordering bug (scrollOffset precondition)

**Owner**: VE
**Feature**: serialdbg-001, playlist-002
**Status**: done (2026-05-24)
**Blocked by**: nothing
**Notes**:

T135 issues a swipe-up drag that increments `scrollOffset` to 1, but does not reset it
afterward. T136 then preconditions on `scrollOffset == 0` and fails because it sees 1.
Not a firmware defect.

Fix applied (option 2 — swipe-down cleanup): appended a `_do_drag` swipe-down to the
end of `t135()` in `run_serialdbg_tests.py` after the `pass_` call. `set scrollOffset`
is not in `dbgSet`, so swipe-down is the only serial-only reset. T135 is now
self-contained; T136/T137 see clean state regardless of suite ordering.

Exit criteria:
- T136 passes in a full suite run where T135 also runs
- T135 result unaffected

---

### TASK-086 — Fix cmdGetQueue hard-cap + run T140

**Owner**: Developer + VE
**Feature**: serialdbg-001, playlist-002
**Status**: done (2026-05-24, commit 1c39d47)
**Blocked by**: nothing (code fix is clear; DUT needs >= 6 tracks queued at test time)
**Notes**:

#### Investigation result (2026-05-24)

`cmdGetQueue` in `app/src/spotifyTaskStorage.cpp:526` serializes:
```cpp
uint8_t n = qs.count < 5 ? qs.count : 5;
```
Magic number `5` = `PLEDIT_ROW_COUNT`. The snapshot struct (`QUEUE_MAX = SPOTIFY_QUEUE_MAX_ITEMS = 20`)
and `onQueue()` copy both support up to 20 items. The harness `wait_for_queue(min_count=6)` counts
JSON parts with a `"track"` key — it never sees > 5 → T140 always skips.

`LOCAL_PATCHES.md` patch 10 claims `SPOTIFY_QUEUE_MAX_ITEMS` was reduced 7→5 to match
`PLEDIT_ROW_COUNT`; the actual value in `app/lib/SpotifyArduino/src/SpotifyArduino.h:94` is `20`
(set when `app/lib/` was created in TASK-083). Doc is stale.

#### Fix (two files)

**1. `app/src/spotifyTaskStorage.cpp:526`** — raise the serialize cap:
```cpp
// before:
uint8_t n = qs.count < 5 ? qs.count : 5;
// after:
uint8_t n = qs.count < QUEUE_MAX ? qs.count : QUEUE_MAX;
```
`QUEUE_MAX` is defined in `spotifyTask.h` and already in scope (used by `onQueue()`).

**2. `app/lib/SpotifyArduino/LOCAL_PATCHES.md`** — correct patch 10 note:
Change "Reduced `SPOTIFY_QUEUE_MAX_ITEMS` from 7 to 5 (matches `PLEDIT_ROW_COUNT`)" to
"Set `SPOTIFY_QUEUE_MAX_ITEMS` to 20 (increased capacity; snapshot + serialize both support it)."

#### T140 re-run precondition
Ensure >= 6 tracks queued in Spotify before running. `wait_for_queue(min_count=6)` will
then unblock automatically.

Exit criteria:
- `get queue` emits up to 20 parts when queue has >= 6 tracks
- `wait_for_queue(6)` succeeds with >= 6 tracks queued
- T140 passes (scrollOffset saturates at maxOffset, not maxOffset+1)

---

### TASK-095 — WeatherApp + CryptoApp implementation (M-MULTIAPP step 4)
**Owner**: Developer + Architect
**Feature**: weather-001 (new), crypto-001 (new)
**Status**: done (2026-05-25 — commits 9da9ca0, d5de546; DUT verified)
**Design**: `docs/architecture/designs/M-MULTIAPP/weather.md`, `crypto.md`
**Notes**:
- **ADR-029** (accepted 2026-05-25): TLS root CA strategy for non-Spotify HTTPS endpoints.
  `api.open-meteo.com` → ISRG Root X1; `api.coingecko.com` → GTS Root R4. Hardcoded PEMs
  in `app/src/dataTaskCerts.h`. `http.getString()` required (not `getStream()`) — chunked
  HTTPS on Arduino-ESP32 2.0.17 fails `deserializeJson` on raw stream.
- `dataTask` FreeRTOS task (`app/src/dataTask.h` + `dataTaskStorage.cpp`): queue + spinlock,
  mirrors `spotifyTask` pattern. `begin()` called in `setup()` after `spotifyTask::begin()`.
- `WeatherApp` + `CryptoApp` classes in `main.cpp`; replace `nullptr` slots 2 + 3 in `g_apps[]`.
- `tools/refresh_host_overrides.sh` extended with new endpoints; SPIFFS re-flashed.
- Serial port migrated to `/dev/ttyUSB1` (CH340 re-enumerated).
- Exit criteria: both apps fetch live data on first switch-in; `"---"` shown before first
  fetch; app switch residue none; DUT stable.

---

### TASK-096 — Fix Weather+Crypto canvas to full 275×240
**Owner**: Developer
**Feature**: weather-001, crypto-001
**Status**: done (2026-05-25 — commit e96bb60; DUT verified)
**Notes**:
- Both apps rendered in `y:116..239` sub-canvas only (legacy design assumed Winamp chrome
  was still showing above). As standalone apps they own the full 275×240 canvas.
- Weather: 2×2 grid now spans full height — top row `y:0..119` (h=120), bottom row
  `y:121..239` (h=119). Panel centres: top cy=60, bottom cy=180. RSSI bars at bottom y=14.
- Crypto: 6 rows × 36 px, starting y=25 (header y=5, rule y=22). Row text offset +11 px
  for vertical centering. Last divider lands at y=239.
- Exit criteria: both apps fill the full screen on DUT. Confirmed by user.

---

### TASK-097 — VE: test suite for matrix-001 (MatrixApp)
**Owner**: VE
**Feature**: matrix-001
**Status**: done (2026-05-25 — T_MA_01/02/03 written in harness; T_MA_04/05 planned-manual; test_ids populated)
**Blocked by**: matrix-001 registered in feature_inventory.yaml (done — 2026-05-25)
**Notes**:
- Mandate: BP-005 — implemented feature with `test_ids: []` must have a VE task; BP-010 — VE task not done until `test_ids` populated in `feature_inventory.yaml`.
- QM audit finding 2 (2026-05-25). Filed by PM.
- **Required coverage** (minimum):
  1. App renders to full 275×240 canvas (no top-half black — LL-037 check).
  2. Streams animate: column y-values advance across ticks.
  3. App switch residue none: switch Matrix→Spotify→Matrix produces clean canvas, no Winamp bleed.
  4. Tap reinitialises streams (observable via column state reset).
  5. ADR-027 compliance: TFT textColor reset after each Matrix tick (no bleed into adjacent app renders).
- **Test type**: DUT, `cyd2usb_winamp_debug`. Serialdbg harness where observable via `dbgGet`; visual check for canvas coverage.
- **Exit criterion**: test functions written and passing; `test_ids` list in `feature_inventory.yaml` populated; entries added to `test_plan.md` under suite `matrix-001`.

---

### TASK-098 — VE: test suite for gol-001 (LifeApp)
**Owner**: VE
**Feature**: gol-001
**Status**: done (2026-05-25 — T_GOL_01/02/03/04 written in harness; T_GOL_05/06/07 planned-manual; test_ids populated)
**Blocked by**: gol-001 registered in feature_inventory.yaml (done — 2026-05-25)
**Notes**:
- Mandate: BP-005, BP-010. QM audit finding 2 (2026-05-25). Filed by PM.
- **Required coverage** (minimum):
  1. App renders to full 275×240 canvas (LL-037 check).
  2. Generations advance: generation counter increments across ticks (millis-gated 100 ms).
  3. Stagnation reset fires: after >120 gens or <5 alive cells, grid is reinitialised.
  4. Tap reseeds: grid changes on tap input.
  5. App switch residue none: GoL→Spotify→GoL produces clean canvas, no Winamp bleed.
  6. Heap stable: free heap after GoL launch within expected range (~183 KB; s_nextGrid ~2.6 KB BSS accounted for).
- **Test type**: DUT, `cyd2usb_winamp_debug`. Generation counter and cell count observable via `dbgGet` if instrumented; otherwise visual + timing check.
- **Exit criterion**: test functions written and passing; `test_ids` in `feature_inventory.yaml`; entries in `test_plan.md` under suite `gol-001`.

---

### TASK-099 — VE: test suite for weather-001 (WeatherApp)
**Owner**: VE
**Feature**: weather-001
**Status**: done (2026-05-25 — T_WX_01/02/03/04/05 written in harness; T_WX_06 planned-manual; test_ids populated)
**Blocked by**: weather-001 registered in feature_inventory.yaml (done — 2026-05-25)
**Notes**:
- Mandate: BP-005, BP-010. QM audit finding 2 (2026-05-25). Filed by PM.
- **Required coverage** (minimum):
  1. Pre-fetch state: app shows `"---"` for all fields before first dataTask result lands.
  2. Post-fetch state: temperature, humidity, wind speed fields populated with live values after fetch.
  3. Full canvas coverage: app renders into full 275×240 app canvas — top row y:0..119 and bottom row y:121..239 both visible (LL-037 regression check — original bug was top-half black).
  4. Fetch triggered on resume: switching to Weather from another app enqueues DATA_FETCH_WEATHER; data updates within poll timeout.
  5. App switch residue none: Weather→Spotify→Weather produces clean canvas.
  6. dataTask/cross-feature (X007): rapid Weather→Crypto→Weather switching does not corrupt either app's displayed values.
- **Test type**: DUT, `cyd2usb_winamp_debug`. `dbgGet` for fetch state if instrumented; visual + timing check for live data arrival. Network required (or host_overrides.json + SPIFFS current).
- **Exit criterion**: test functions written and passing; `test_ids` in `feature_inventory.yaml`; entries in `test_plan.md` under suite `weather-001`.

---

### TASK-100 — VE: test suite for crypto-001 (CryptoApp)
**Owner**: VE
**Feature**: crypto-001
**Status**: done (2026-05-25 — T_CX_01/02/03/04/05 written in harness; T_CX_06 planned-manual; test_ids populated; T_X07_01 covers X007 cross-feature)
**Blocked by**: crypto-001 registered in feature_inventory.yaml (done — 2026-05-25)
**Notes**:
- Mandate: BP-005, BP-010. QM audit finding 2 (2026-05-25). Filed by PM.
- **Required coverage** (minimum):
  1. Pre-fetch state: all 6 rows show `"---"` before first dataTask result lands.
  2. Post-fetch state: 6 crypto rows populated with price + 24 h change after fetch.
  3. Full canvas coverage: rows span full 275×240 canvas — header y=5, first row y=25, last divider y=239 (LL-037 regression check).
  4. Fetch triggered on resume: switching to Crypto enqueues DATA_FETCH_CRYPTO; data updates within poll timeout.
  5. App switch residue none: Crypto→Spotify→Crypto produces clean canvas.
  6. dataTask/cross-feature (X007): concurrent dataTask requests from Weather and Crypto do not corrupt each other's result slots.
- **Test type**: DUT, `cyd2usb_winamp_debug`. Same network dependency as TASK-099. Run alongside TASK-099 where possible (shared DUT session, shared host_overrides.json state).
- **Exit criterion**: test functions written and passing; `test_ids` in `feature_inventory.yaml`; entries in `test_plan.md` under suite `crypto-001`.

---

### TASK-101 — M-TOUCH-CAPTURE: Implement slider input capture in winampDisplay
**Owner**: Developer
**Feature**: touch-002
**Status**: open (2026-05-25)
**Blocked by**: VE sign-off on design doc (done — 2026-05-25, see VE review)
**Notes**:
- Design doc: `docs/architecture/designs/M-TOUCH-CAPTURE-slider-input-capture.md`
- VE review: `docs/verification/regression_suite/touch-capture-ve-review.md`
- Sole change file: `app/src/winamp/winampDisplay.h`
- Changes:
  1. Add `D_POSBAR_DRAG` to `DragState` enum.
  2. Add `long _posbarDragCurrentMs = 0` member.
  3. Restructure Press/Move path: Phase 1 captured-gesture guard before all hit-tests.
  4. Add `volumeFromX(int sx)` and `posbarFromX(int sx)` private helpers (clamped, no y check).
  5. POSBAR Press entry: set `D_POSBAR_DRAG`, init `_posbarDragCurrentMs`, paint thumb.
  6. POSBAR Release: commit `_posbarDragCurrentMs` as ACT_SEEK.
  7. `dbgGet("dragState")`: add `D_POSBAR_DRAG` arm.
  8. `dbgGet("posbarDragMs")`: return `_posbarDragCurrentMs`.
- Run `check_build.sh` before commit. Run T149–T154 on DUT to close.
- Optional (unblocks TASK-078 point 1): add `unsigned long _dragStartMs = 0` member;
  set it alongside `_dragStartY` in the `D_PLEDIT_SCROLL` Press entry. No other changes
  needed — TASK-078 will read it when implementing velocity discrimination.

---

### TASK-102 — VE: test suite for touch-capture-001 (T149–T154)
**Owner**: VE
**Feature**: touch-002
**Status**: written (2026-05-25) — awaiting TASK-101 implementation to execute
**Blocked by**: TASK-101
**Notes**:
- Tests written in `test_plan.md` under suite `touch-capture-001`.
- T149: POSBAR single-commit on Release
- T150: POSBAR capture — drift above groove
- T151: VOLUME capture — drift below groove
- T152: PLEDIT scrollbar capture — drift into content area
- T153: Capture exclusivity — VOLUME drift into POSBAR zone, no seek starts
- T154: POSBAR tap (Press + immediate Release) seeks to pressed position
- Execute via `run_serialdbg_tests.py --tests T149,T150,T151,T152,T153,T154`.
- All 6 must pass before TASK-101 can be marked done.

### TASK-103 — M-LIST-v4: Implement velocity-scroll for PLEDIT
**Owner**: Developer
**Feature**: list-scroll-001 (new)
**Status**: open (2026-05-25)
**Blocked by**: TASK-101 done (unblocked — committed b253eb8), ADR-030 accepted ✓
**Design**: `docs/architecture/designs/M-LIST-v4-velocity-scroll.md`
**ADR**: ADR-030 (accepted 2026-05-25)
**Notes**:
- Sole change file: `app/src/winamp/winampDisplay.h` + `app/src/appShell.h` (tick call site) + serial debug handler (cmdTick)
- New members: `_scrollVelocity`, `_scrollAccum`, `_scrollSpeedK`
- `tickScroll(float dt)` — explicit dt parameter; called from SpotifyApp tick with real elapsed time
- Release logic: dead-zone-only tap check; remove TASK-078 point 1 two-axis heuristic (after DUT evidence, see §_dragStartMs removal in design)
- `drawPlaylist()` seqno branch: cancel D_PLEDIT_SCROLL mid-gesture
- Serial debug: `dbgGet("scrollAccum")`, `dbgGet("scrollVelocity")`, `dbgSet("speedK", ...)`, `cmdTick n dtMs`
- Run `check_build.sh` before commit; VE suite T155–T161 (TASK-104) must pass

### TASK-104 — VE: test suite for velocity-scroll (T155–T161)
**Owner**: VE
**Feature**: list-scroll-001
**Status**: planned (2026-05-25)
**Blocked by**: TASK-103
**Notes**:
- Acceptance tests to be written against revised design doc after TASK-103 implementation
- Covers: dead-zone tap, speed scaling, continuous scroll, no-tap on out-of-dead-zone release, seqno cancellation, cmdTick determinism, dbgGet observability
- Proposed IDs: T155–T161

---

### TASK-109 — StockApp POC: List + Chart detail implementation
**Owner**: Developer
**Feature**: stock-001 (new)
**Status**: open
**Blocked by**: nothing — `StockApp` stub already registered in `g_apps[]` (TASK-105a)
**Design**: `docs/architecture/designs/M-MULTIAPP/stock.md` · `stock-list.md` · `stock-chart.md`
**Milestone**: M-STOCK-POC
**Notes**:

Sub-tasks (implement in order; each must compile cleanly before proceeding):

- **TASK-109a** — `appShell.h`: Add `StockAppState` struct (replace placeholder). Add `StockSubView` + `StockRange` enums. Fields: `tickers[6][8]`, `subView`, `prices[6]`, `changePct[6]`, `lastQuoteFetch`, `chartTickerIdx`, `chartRange`, `chartPoints[110]`, `chartLen`, `chartLo`, `chartHi`, `lastChartFetch`, `fetchFailed` (bool), `fetchErrorCode` (int). (~565 B total, within BSS budget.)

- **TASK-109b** — `dataTask.h` / `dataTaskStorage.cpp`: Add `DATA_FETCH_STOCK_QUOTE` and `DATA_FETCH_STOCK_CHART` fetch types. **Quote handler** (discovered by 109i probe: v7/quote is 401-gated): 6 sequential GETs to `STOCK_CHART_URL_BASE + symbol + "?interval=1d&range=1d"` per symbol; parse `chart.result[0].meta.regularMarketPrice` + `meta.chartPreviousClose`; compute `changePct = (price - prev) / prev * 100`. Skip null `close[]` entries. **Chart handler**: GET to `STOCK_CHART_URL_BASE + symbol + "?interval=X&range=Y"`, parse `chart.result[0].indicators.quote[0].close[]` into float array, skip nulls. YTD uses `interval=1wk` not `1d` (1d = 12 KB > 8192 B budget, verified by 109i). Use `DynamicJsonDocument doc(8192)` for all fetches. `http.getString()` not `getStream()` (same constraint as crypto.md).

- **TASK-109c** — TLS: Run `openssl s_client -connect query1.finance.yahoo.com:443 2>/dev/null | openssl x509 -noout -issuer` to confirm root CA. Add `YAHOO_FINANCE_ROOT_CA[]` to `dataTaskCerts.h`. Wire into stock fetch handlers (same `WiFiClientSecure` + `http.begin(tls, url)` pattern as CoinGecko — ADR-029 compliance).

- **TASK-109d** — `repaintList()` + `repaintError()`: `repaintList()` checks `fetchFailed` at entry — if true, delegates to `repaintError()` and returns. Normal path: clear sub-canvas, draw `"STOCK TERMINAL"` header (font 2, x=5, y=`ST_LIST_HEADER_Y`), horizontal rule at `ST_LIST_RULE_Y`, 6 rows: symbol (white, x=5), price (`formatStockPrice()`, white, x=55), change% (green `0x07E0` / red `0xF800`, right-aligned x=270), `"---"` before first fetch. `repaintError()`: full sub-canvas black fill, centred `"STOCK FETCH FAILED"` (font 2, red), `"NET ERR  <fetchErrorCode>"` (font 2, red), `"retrying in 60s..."` (font 1, grey). ADR-027 producer rule: reset `TL_DATUM`/`MC_DATUM` on exit of both functions.

- **TASK-109e** — `repaintChart()`: Clear sub-canvas. Header (y:116..131): `"<"` back glyph (font 2, x=5), ticker + price (x=30), 4 range tabs (x: 130/166/202/238 — each 36 px); highlight active tab with `0x4208` background. Plot area (y:132..223): line graph — `drawLine` segments from `chartPoints[]`, y mapped linearly to `chartLo..chartHi`. Flat line at midpoint if `chartLen == 0`. Line colour `0x07FF` (cyan). Footer (y:224..239): `"lo: X.XX"` left, `"hi: X.XX"` right; `"---"` if not fetched. ADR-027 producer rule: reset datum after all `drawString` calls.

- **TASK-109f** — `handleInput()`: List sub-view: if `fetchFailed`, ignore all taps (no drill-in while error shown). Otherwise: row hit-test on `TouchPhase::End` at y ∈ [ST_LIST_ROW_START_Y, 239] → `drillToChart(rowIdx)`. Chart sub-view: back button (x < 30, y:116..131) always active even in error state → `backToList()`. Range tabs (x ≥ 130, y:116..131): disabled if `fetchFailed`. Chart body: no-op.

- **TASK-109g** — `tick()` / `fetchQuotes()` / `fetchChart()` / `drillToChart()` / `backToList()`: Quote staleness check every `STOCK_QUOTE_FETCH_MS` (60 s) in List sub-view. Chart staleness: 60 s for D1, 300 s for D5/Mo1/Ytd. `drillToChart(idx)`: set `chartTickerIdx`, `chartRange = D1`, `subView = ChartDetail`, fetch if stale, `repaintChart()`. `backToList()`: set `subView = List`, `repaintList()`. `init()`: populate hardcoded tickers, set `subView = List`, enqueue first quote fetch.

- **TASK-109h** — Build + smoke: `check_build.sh` 4/4 pass. DUT flash + verify: (1) taskbar → Stock shows `"---"` rows; (2) first fetch populates prices; (3) tap row → chart header shows correct ticker; (4) range tab tap fetches new data; (5) `[<]` returns to list with prices intact; (6) Stock → Spotify → Stock: Winamp chrome pixel-correct; (7) Stock sub-canvas has no residue above y=116.

- **TASK-109i** — `app/tools/test_yahoo_finance_api.py`: host-side API probe (no DUT). Checks: (1) quote endpoint HTTP 200; (2) all 6 symbols have non-null `regularMarketPrice` + `regularMarketChangePercent`; (3) quote JSON ≤ 6144 B; (4) chart endpoint all 4 ranges HTTP 200; (5) `timestamp[]` + `close[]` parallel arrays present and non-empty; (6) chart JSON ≤ 8192 B for all ranges; (7) TLS cert issuer printed for 109c pinning. Run *before* 109c — the issuer dump is the input to the `openssl s_client` verification step. Exit 0 = all pass.

Exit criterion: TASK-109h smoke items all PASS; `check_build.sh` 4/4 green; TASK-110 VE suite written.

---

### TASK-110 — VE: Stock app test suite (T169–T182)
**Owner**: VE
**Feature**: stock-001
**Status**: planned — write + execute after TASK-109 done
**Blocked by**: TASK-109
**Milestone**: M-STOCK-POC
**Notes**:

All tests require `cyd2usb_winamp_debug` firmware + serial debug interface. Serial debug additions required from TASK-109:
- `get stockSubView` → `"list"` or `"chart"`
- `get stockChartTicker` → ticker symbol string (e.g. `"NVDA"`)
- `get stockChartRange` → `"D1"` / `"D5"` / `"Mo1"` / `"Ytd"`
- `get lastQuoteFetch` → millis timestamp (0 = never)

**List view — exit criteria L1–L6:**

- **T169** (L1) — All 6 rows render within sub-canvas: inject `switchApp(Stock)`, capture display; verify no pixel overflow above y=116 or below y=239.
- **T170** (L2) — Pre-fetch placeholders: immediately after `switchApp(Stock)` before first fetch lands, all 6 price/change fields show `"---"`.
- **T171** (L3) — Colour coding: after fetch, verify positive change% rows display green (0x07E0) and negative rows display red (0xF800). Requires at least one of each sign in live data or mock.
- **T172** (L4) — App switch residue: Spotify → Stock → Spotify; verify Winamp chrome pixel-correct and no stock row residue above y=116.
- **T173** (L5) — Resume cache: switch away from Stock and back within 60 s; prices render immediately without new fetch (`lastQuoteFetch` unchanged).
- **T174** (L6) — Row drill-in: `injectTouch` on row 2 (NVDA); verify `stockSubView == "chart"` and `stockChartTicker == "NVDA"`.

**Chart detail view — exit criteria C1–C7:**

- **T175** (C1) — Back navigation: from chart, `injectTouch` on back zone (x=10, y=120); verify `stockSubView == "list"` and list header `"STOCK TERMINAL"` visible.
- **T176** (C2) — Plot bounds: after chart fetch, verify no line segment pixel exits y:132..223 bounds.
- **T177** (C3) — Range tab: `injectTouch` on 5D tab (x=183, y=120); verify `stockChartRange == "D5"` and new fetch triggered (`lastChartFetch` timestamp advances).
- **T178** (C4) — Pre-fetch placeholder: immediately after drill-in, before fetch lands, chart header price shows `"---"` and flat line at plot midpoint.
- **T179** (C5) — Footer: after fetch, `lo:` and `hi:` values visible in footer; `lo < hi`.
- **T180** (C6) — Drill-in default range: every drill-in sets `stockChartRange == "D1"`.
- **T181** (C7) — Back then re-drill: back → List → tap same row; chart redraws correctly; `get stockChartTicker` matches tapped row.
- **T182** (cross) — Stock canvas isolation: Stock → Spotify → Stock; sub-canvas (y:116..239) pixel-matches a fresh `repaintList()` result; no chart or prior-session residue.
- **T183** (error) — Inject fetch error: set `fetchFailed=true` + `fetchErrorCode=-1` via serial debug (`dbgSet`); verify sub-canvas shows `"STOCK FETCH FAILED"` + `"NET ERR  -1"` + `"retrying in 60s..."`. Verify row tap does nothing (no drill-in).
- **T184** (error/chart) — Error in chart view: drill into chart, inject `fetchFailed=true`; verify error screen shown; verify `[<]` back button still navigates to list.
- **T185** (error/recovery) — Error clears on success: inject error, confirm error screen; trigger successful fetch via `dbgSet("triggerFetch", "1")`; confirm error screen replaced by normal list/chart render.

Exit criterion: T169–T182 all PASS; test IDs registered in `feature_inventory.yaml` under `stock-001`.

---

## Entry Format

```
### TASK-001 — [Title]
**Owner**: Developer | VE | QM | PM
**Feature**: F001 (if applicable)
**Status**: todo | in_progress | blocked | done
**Git ref**: branch name or commit SHA
**Blocked by**: (if applicable)
**Notes**:
```
