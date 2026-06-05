# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.


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


---

> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
