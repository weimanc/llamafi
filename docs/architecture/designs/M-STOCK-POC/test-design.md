# M-STOCK-POC — VE Test Suite Design (T169–T185)

> Owner: Architect  
> Implements: TASK-110  
> Updated: 2026-05-29  
> Baseline firmware: `cyd2usb_winamp_debug`

---

## 1. Corrected Canvas / Zone Geometry

All coordinates derived from constants in `app/src/main.cpp` (lines 693–711) and `app/src/appShell.h` (lines 88–105). The TASK-110 spec was written before the 6→8 ticker expansion and before the full-canvas (y:0..239) model was confirmed.

### 1.1 List view zones

| Zone | x-range | y-range | Derived from |
|------|---------|---------|--------------|
| Full canvas | 0..274 | 0..239 | `ST_CANVAS_X2=274`, `ST_CANVAS_H=240` |
| Header text | `ST_LIST_COL_SYMBOL=5` | y=`ST_LIST_HEADER_Y=5` | header drawn at y=5 |
| Rule line | 5..274 | y=`ST_LIST_RULE_Y=22` | `drawFastHLine(5, 22, ...)` |
| Row area (all 8) | 0..274 | 25..232 | `ST_LIST_ROW_START_Y=25`, 8×`ST_LIST_ROW_H=26` = 208 px → y_end=233 (last row top=233, not drawn past canvas) |
| Row 0 (AAPL) | 0..274 | 25..50 | index 0 |
| Row 1 (AMD) | 0..274 | 51..76 | index 1 |
| Row 2 (AMZN) | 0..274 | 77..102 | index 2 |
| Row 3 (ARM) | 0..274 | 103..128 | index 3 |
| Row 4 (GOOG) | 0..274 | 129..154 | index 4 |
| Row 5 (META) | 0..274 | 155..180 | index 5 |
| Row 6 (MSFT) | 0..274 | 181..206 | index 6 |
| Row 7 (NVDA) | 0..274 | 207..232 | index 7 |
| Symbol column | x=5 | per row | `ST_LIST_COL_SYMBOL=5` |
| Price column | x=55 | per row | `ST_LIST_COL_PRICE=55` |
| Change column | x=270 (TR_DATUM) | per row | `ST_LIST_COL_CHANGE=270` |

Row centre y for row i: `ST_LIST_ROW_START_Y + i*ST_LIST_ROW_H + 11` = `25 + 26i + 11` = `36 + 26i`.

| Row | Ticker | Centre tap y |
|-----|--------|--------------|
| 0 | AAPL | 36 |
| 1 | AMD | 62 |
| 2 | AMZN | 88 |
| 3 | ARM | 114 |
| 4 | GOOG | 140 |
| 5 | META | 166 |
| 6 | MSFT | 192 |
| 7 | NVDA | 218 |

### 1.2 Chart view zones

| Zone | x-range | y-range | Derived from |
|------|---------|---------|--------------|
| Full canvas | 0..274 | 0..239 | same as list |
| Header bar | 0..274 | 0..17 | `ST_CHART_HEADER_Y=0`, `ST_CHART_HEADER_H=18` |
| Back button | 0..29 | 0..17 | `ST_CHART_BACK_W=30`; tap target: `(10, 7)` |
| Ticker+price label | 30..129 | 0..17 | `ST_CHART_TICKER_X=30` |
| Tab strip | 130..273 | 0..17 | `ST_CHART_TABS_X=130`, `ST_CHART_TAB_W=36` |
| Tab 0 (1D) | 130..165 | 0..17 | `(x-130)/36=0`; centre: `(148, 7)` |
| Tab 1 (5D) | 166..201 | 0..17 | `(x-130)/36=1`; centre: `(184, 7)` |
| Tab 2 (1M) | 202..237 | 0..17 | `(x-130)/36=2`; centre: `(220, 7)` |
| Tab 3 (YTD) | 238..273 | 0..17 | `(x-130)/36=3`; centre: `(256, 7)` |
| Plot area | 0..274 | 18..213 | `ST_CHART_PLOT_Y=18`, `ST_CHART_PLOT_H=196` → y_end = 18+196-1 = 213 |
| Footer | 0..274 | y=214 | `ST_CHART_FOOTER_Y=214` |

**Plot pixel bounds (T176):** line segments confined to `y ∈ [18, 213]`. The renderer uses `y0 = ST_CHART_PLOT_Y + ST_CHART_PLOT_H - 2 - (int)((price - lo) * yScale)` which gives y ∈ [18, 213] when `yScale = (ST_CHART_PLOT_H - 2) / rng = 194 / rng`.

---

## 2. Serial Debug Hooks Required

### 2.1 Firmware additions — `StockApp::dbgGet` / `StockApp::dbgSet`

`StockApp._s` is a private `StockAppState` member. The free functions `cmdGet` / `cmdSet` in `main.cpp` cannot access it. The pattern used for `WinampDisplay` is to add `dbgGet(const char* var, char* buf, int len) const` and `dbgSet(const char* var, const char* val)` public methods on the class, then call them from `cmdGet` / `cmdSet`.

**Step 1 — add `dbgGet` / `dbgSet` to `StockApp` class (public section):**

```cpp
bool dbgGet(const char* var, char* buf, int len) const {
    if (strcmp(var, "stockSubView") == 0) {
        snprintf(buf, len, "\"var\":\"stockSubView\",\"val\":\"%s\",\"last\":true",
                 _s.subView == StockSubView::ChartDetail ? "chart" : "list");
        return true;
    }
    if (strcmp(var, "stockChartTicker") == 0) {
        snprintf(buf, len, "\"var\":\"stockChartTicker\",\"val\":\"%s\",\"last\":true",
                 _s.tickers[_s.chartTickerIdx]);
        return true;
    }
    if (strcmp(var, "stockChartRange") == 0) {
        const char* rstr = (_s.chartRange == StockRange::D1)  ? "D1"
                         : (_s.chartRange == StockRange::D5)  ? "D5"
                         : (_s.chartRange == StockRange::Mo1) ? "Mo1" : "Ytd";
        snprintf(buf, len, "\"var\":\"stockChartRange\",\"val\":\"%s\",\"last\":true", rstr);
        return true;
    }
    if (strcmp(var, "lastQuoteFetch") == 0) {
        snprintf(buf, len, "\"var\":\"lastQuoteFetch\",\"val\":%lu,\"last\":true",
                 _s.lastQuoteFetch);
        return true;
    }
    if (strcmp(var, "lastChartFetch") == 0) {
        snprintf(buf, len, "\"var\":\"lastChartFetch\",\"val\":%lu,\"last\":true",
                 _s.lastChartFetch);
        return true;
    }
    return false;
}

bool dbgSet(const char* var, const char* val) {
    if (strcmp(var, "fetchFailed") == 0) {
        _s.fetchFailed = (val && strcmp(val, "0") != 0);
        return true;
    }
    if (strcmp(var, "fetchErrorCode") == 0) {
        _s.fetchErrorCode = val ? atoi(val) : 0;
        return true;
    }
    if (strcmp(var, "triggerFetch") == 0 && val && strcmp(val, "1") == 0) {
        // Force immediate re-fetch by zeroing the timestamps
        _s.lastQuoteFetch = 0;
        _s.lastChartFetch = 0;
        return true;
    }
    return false;
}
```

**Step 2 — expose a global accessor in `main.cpp` (after `static StockApp g_stockApp;`):**

```cpp
// Serial debug accessor — parallel to spotifyDisplay->dbgGet/dbgSet pattern.
static bool stockDbgGet(const char* var, char* buf, int len) {
    return g_stockApp.dbgGet(var, buf, len);
}
static bool stockDbgSet(const char* var, const char* val) {
    return g_stockApp.dbgSet(var, val);
}
```

**Step 3 — wire into `cmdGet` / `cmdSet` in `main.cpp`:**

In `cmdGet`, add before the `unknown var` fallthrough:
```cpp
if (stockDbgGet(args, buf, sizeof(buf))) {
    if (buf[0]) Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
}
```

In `cmdSet`, add before the `unknown var` fallthrough:
```cpp
if (stockDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
}
```

Note: `dbgSet("fetchFailed"/"fetchErrorCode"/"triggerFetch")` mutates `_s` directly but does not call `repaintList()` or `repaintError()`. The test harness must either (a) trigger a tap/tick to force repaint, or (b) accept that the display update is deferred to the next `tick()` call. For error-injection tests (T183–T185), the test should call `set fetchFailed 1` then wait one tick interval (~33 ms at 30 fps) before checking display state. Simpler: call `set fetchFailed 1` then `set fetchErrorCode -1`, then inject a touch on the canvas (any y ≥ 25) — `handleInput` returns early on `fetchFailed` and `tick()` will call `repaintList()` on the next quote-poll cycle. Design alternative: add `repaintNow` as a third set var — deferred to implementer judgment.

### 2.2 JSON response formats

| Command | Example JSON response |
|---------|-----------------------|
| `get stockSubView` | `{"ok":true,"cmd":"get","var":"stockSubView","val":"list","last":true}` |
| `get stockSubView` (chart) | `{"ok":true,"cmd":"get","var":"stockSubView","val":"chart","last":true}` |
| `get stockChartTicker` | `{"ok":true,"cmd":"get","var":"stockChartTicker","val":"NVDA","last":true}` |
| `get stockChartRange` | `{"ok":true,"cmd":"get","var":"stockChartRange","val":"D1","last":true}` |
| `get lastQuoteFetch` | `{"ok":true,"cmd":"get","var":"lastQuoteFetch","val":12345678,"last":true}` |
| `get lastChartFetch` | `{"ok":true,"cmd":"get","var":"lastChartFetch","val":12345678,"last":true}` |
| `set fetchFailed 1` | `{"ok":true,"cmd":"set","var":"fetchFailed","val":"1"}` |
| `set fetchFailed 0` | `{"ok":true,"cmd":"set","var":"fetchFailed","val":"0"}` |
| `set fetchErrorCode -1` | `{"ok":true,"cmd":"set","var":"fetchErrorCode","val":"-1"}` |
| `set triggerFetch 1` | `{"ok":true,"cmd":"set","var":"triggerFetch","val":"1"}` |

All responses follow the existing pattern from `cmdGet`/`cmdSet` in `main.cpp:1490–1536`.

---

## 3. Stock App Switching Strategy

### 3.1 Problem

`_switch_to(dut, name, slot)` taps `_c.tap_taskbar_slot(slot)` which maps directly to `slot * TASKBAR_SLOT_H + TASKBAR_SLOT_H // 2` on the physical taskbar. At `tbScrollOffset=0`, visible slots 0..5 map to AppIds 0..5 (Spotify..Life). Stock is AppId=7; it is never in a visible slot when `tbScrollOffset=0`.

To reach Stock, the taskbar must be scrolled first.

### 3.2 Option A — Taskbar scroll + slot tap (no firmware change)

`tbScrollOffset` is already readable via `get tbScrollOffset` (implemented in `WinampDisplay::dbgGet`). The harness can:

1. Read `get tbScrollOffset`.
2. Drag the taskbar to set `tbScrollOffset = 2` (Stock appears at visual slot 5, AppId=(2+5)%9=7) or `tbScrollOffset = 3` (Stock at visual slot 4, AppId=(3+4)%9=7).
3. Tap the appropriate visual slot.
4. Verify `get appId → "Stock"`.

Scroll mechanics (from `taskbar.md`): drag along y on x ∈ [275, 319], LP filter (α=0.4), 1:1 positional, 50 px safe margin per slot step. To scroll from `tbScrollOffset=0` to `tbScrollOffset=2`: drag up by ≥ 100 px: `drag 297 200 297 100 10`.

Wrap-around: `(dragBaseOff + steps) % N`. With N=9, from offset 0 a 100 px drag up (negative rawDy → positive steps) gives `steps = -(-100) / 40 = 2` → offset 2. Verify with `get tbScrollOffset == 2` before tapping.

After tests: restore `tbScrollOffset` to 0 by dragging down (positive rawDy → negative steps). Helper: `drag 297 100 297 200 10`.

**Proposed helper function for the test harness:**

```python
def _switch_to_stock(dut: Dut, timeout: float = 5.0) -> bool:
    """Scroll taskbar to tbScrollOffset=2, tap slot 5 (Stock), verify appId=Stock."""
    import time
    # Ensure taskbar is at offset 0 first (scroll down to reset).
    r = dut.cmd("get tbScrollOffset", timeout=timeout)
    cur = r.get("val", 0)
    if cur != 0:
        # Drag down enough to get to 0 (modular, so wrap may occur; just ensure 0).
        dut.cmd("drag 297 100 297 220 15", timeout=timeout)
        time.sleep(0.3)
        r = dut.cmd("get tbScrollOffset", timeout=timeout)
        if r.get("val", -1) != 0:
            return False  # cannot normalise
    # Scroll up 2 slots: drag from y=200 to y=100 (100 px, 10 steps).
    dut.set_cooldown_zero()
    dut.cmd("drag 297 200 297 100 10", timeout=timeout)
    time.sleep(0.2)
    r = dut.cmd("get tbScrollOffset", timeout=timeout)
    if r.get("val") != 2:
        return False
    # Tap slot 5 (visual slot 5 at tbScrollOffset=2 → AppId=(2+5)%9=7=Stock).
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(5)
    dut.cmd(f"tap {sx} {sy}", timeout=timeout)
    time.sleep(0.4)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Stock"


def _restore_from_stock(dut: Dut, timeout: float = 5.0) -> bool:
    """Return to Spotify and reset taskbar to tbScrollOffset=0."""
    import time
    # Tap slot 5 at offset 0 = Life; need to scroll back first.
    # Drag taskbar down to restore offset 0 (from offset 2, drag down 2 slots).
    dut.set_cooldown_zero()
    dut.cmd("drag 297 100 297 200 10", timeout=timeout)
    time.sleep(0.2)
    r = dut.cmd("get tbScrollOffset", timeout=timeout)
    # Now offset should be 0; tap slot 0 = Spotify.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(0)
    dut.cmd(f"tap {sx} {sy}", timeout=timeout)
    time.sleep(0.4)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Spotify"
```

### 3.3 Option B — Add `switchApp <id>` serial command

A new `cmdSwitchApp` handler in `main.cpp` that calls `switchApp(static_cast<AppId>(id))` directly. Eliminates scroll state dependency. Simpler harness.

```
switchApp 7   →  {"ok":true,"cmd":"switchApp","id":7,"name":"Stock"}
```

**Trade-off:** Adds a firmware command that bypasses the taskbar entirely; `tbScrollOffset` is unchanged. Tests that verify taskbar-driven switching can't use it. Tests that only need "stock app active" benefit from the simplicity. Does not conflict with the existing `switchApp()` C++ function — it's already a free function in `main.cpp:1047`.

### 3.4 Recommendation

**Implement Option B (`switchApp <id>` serial command) as the primary mechanism for test setup.** Rationale:

- Tests T169–T185 are unit tests of Stock app behaviour, not taskbar scroll behaviour. Taskbar scroll is already covered by T136–T140.
- Option A creates test fragility: if `tbScrollOffset` cannot be normalised (e.g. because a prior test left a partial drag in flight), the Stock tests fail for a reason unrelated to Stock.
- The `switchApp` C++ function already exists and is safe to call from the serial handler.
- The command should **not** modify `tbScrollOffset`; the taskbar's visual state will be stale but that is acceptable for test setup.

A separate test (T169 or a new T_STB_01) can verify the taskbar-driven path specifically. The serial command is debug-build-only (`#ifdef SERIAL_DEBUG`).

**One test that must use the taskbar path:** T182 (canvas isolation, clean session state). That test needs to switch to Stock via the UI path to confirm nothing from the chart or prior session leaks through. For T182 use `_switch_to_stock()` (Option A). All other tests use `switchApp 7`.

---

## 4. Corrected T169–T185 Specifications

Each entry notes what changed from the TASK-110 spec. Unchanged tests are marked **[spec correct]**.

### T169 (L1) — Full canvas bounds check

**Corrected from TASK-110:** "sub-canvas y:116..239" → full canvas y:0..239.

- Precondition: Stock not previously activated in this session (pre-fetch state).
- Action: `switchApp 7`; wait 200 ms.
- Assert: `get stockSubView == "list"`. Pixel verification: no StockApp draw touches y < 0 or y > 239, x > 274. (Serial-only proxy: `get appId == "Stock"` plus known-good init; full pixel capture is a stretch goal.)
- Firmware note: `repaintList()` fills `fillRect(0, 0, 275, 240, TFT_BLACK)` — overflow is impossible by construction. The test serves as a regression guard for future canvas-origin changes.
- Pass criterion: `appId == "Stock"`, `stockSubView == "list"`, no firmware crash.

### T170 (L2) — Pre-fetch placeholders

**Corrected from TASK-110:** "all 6 price/change fields" → all 8 tickers.

- Precondition: first activation of Stock in session (clean boot or `lastQuoteFetch=0` via `set triggerFetch` reset — but `triggerFetch` only zeros the timestamp, not the displayed values; a clean session is required for true pre-fetch state). Run before T173.
- Action: `switchApp 7` immediately after boot (before first fetch completes); `get lastQuoteFetch`.
- Assert: `lastQuoteFetch == 0` (fetch not yet returned). `get stockSubView == "list"`. Pixel proxy: harness cannot read TFT pixels directly; instead it calls `get lastQuoteFetch` — if 0, the display code renders `"---"` for all 8 rows (code path: `_s.lastQuoteFetch ? formatStockPrice(...) : String("---")`).
- Timing: `init()` enqueues `DATA_FETCH_STOCK_QUOTE` and immediately sets `_s.lastQuoteFetch = millis()` — so `lastQuoteFetch` is never 0 after `init()`. Pre-fetch placeholder state (`lastQuoteFetch != 0` but result not yet received) is the correct check. The display shows `"---"` if `lastQuoteFetch != 0` but prices array is all-zero and no result has been polled. Serial cannot distinguish zero-prices from "---" — this test is best run within the first second of activation and checked via `get lastQuoteFetch > 0` plus confirming `get appId == "Stock"`. **Flag: this test may require a firmware addition** (`get stockPricesReady` bool) to be deterministic.
- Pass criterion (pragmatic): `appId == "Stock"`, `lastQuoteFetch > 0`, test completes within 2 s of `switchApp`.

### T171 (L3) — Colour coding

**[spec correct]** — does not reference canvas bounds or ticker count.

- Precondition: live quote fetch completed (`lastQuoteFetch` advanced, prices received).
- Action: `switchApp 7`; wait for `lastQuoteFetch` to advance (poll `get lastQuoteFetch` every 500 ms, timeout 65 s).
- Assert: pixel check (serial proxy not feasible for colour). This test requires either (a) a `get stockChangePct[i]` accessor or (b) tolerance of "data-dependent" result. With the `dbgGet` additions, add `stockChangePct` as a future getter returning a JSON array. For now: skip if no pixel read capability; mark as manual verification.
- Pass criterion: SKIP on automated run unless `get stockChangePct` implemented. Document as requiring mock data injection for determinism.

### T172 (L4) — App switch residue

**Corrected from TASK-110:** "no stock row residue above y=116" → no stock residue in Winamp chrome (y < 0 not possible; real concern is Winamp chrome region, not a fixed y threshold). Winamp chrome occupies y: 0..239 in the Winamp sub-canvas (x: 0..274). Stock paints the same region.

- Action: `_restore_spotify(dut)` (Spotify→Stock via `switchApp 7` → back to Spotify via `switchApp 0`).
- Assert: `lastPlaylistDraw` advances within 3 s (same as `_check_residue` helper). This confirms Winamp repainted over the Stock canvas. Use existing `_check_residue(dut, "T172")`.
- Pass criterion: `lastPlaylistDraw` advances from baseline within 3 s.

### T173 (L5) — Resume cache

**[spec correct]** — no canvas-bound reference.

- Precondition: Stock activated and quote fetch complete; `lastQuoteFetch` captured.
- Action: `switchApp 0` (away); wait 5 s; `switchApp 7` (back).
- Assert: `get lastQuoteFetch` unchanged (same value as captured); `get stockSubView == "list"`.
- Pass criterion: `lastQuoteFetch` unchanged; `stockSubView == "list"`.

### T174 (L6) — Row drill-in

**Corrected from TASK-110:** "row 2 (NVDA)" → NVDA is at row 7 (index 7), tap y=218, x=137. Test retargeted to verify drill-in for an arbitrary row; recommend row 7 (NVDA) or row 0 (AAPL) for determinism.

**Recommended rewrite:** tap row 7 (NVDA), verify `stockChartTicker == "NVDA"`.

- Precondition: Stock active, `stockSubView == "list"`, `fetchFailed == false`.
- Action: `injectTouch`/`tap 137 218` (NVDA row centre).
- Assert: `get stockSubView == "chart"`, `get stockChartTicker == "NVDA"`.
- Pass criterion: both asserts true within 1 s.

**Secondary variant T174b:** tap row 0 (AAPL, y=36):
- `tap 137 36` → `stockSubView == "chart"`, `stockChartTicker == "AAPL"`.

### T175 (C1) — Back navigation

**Corrected from TASK-110:** back zone is `x < ST_CHART_BACK_W(30)` AND `y < ST_CHART_HEADER_H(18)`, so tap `(10, 7)` — not `(x=10, y=120)`.

- Precondition: `stockSubView == "chart"` (enter via T174).
- Action: `tap 10 7` (back zone: x=10 < 30, y=7 < 18).
- Assert: `get stockSubView == "list"`.
- Pass criterion: `stockSubView == "list"` within 1 s.

### T176 (C2) — Plot bounds

**Corrected from TASK-110:** "y:132..223 bounds" → y:18..213. Derived: `ST_CHART_PLOT_Y=18`, plot bottom = `18 + 196 - 2 = 212` (effective pixel range y ∈ [18, 212] per renderer; footer at 214).

- Precondition: `stockSubView == "chart"`, chart fetch complete (`lastChartFetch > 0`, `chartLen ≥ 2`).
- Assert: All rendered line pixels fall within y ∈ [18, 213]. Serial proxy: `get lastChartFetch > 0` confirms data received; pixel verification is manual or future pixel-read extension.
- Pass criterion (automated): `lastChartFetch > 0`, `appId == "Stock"`, `stockSubView == "chart"`, no firmware crash. Full pixel assertion is manual.

### T177 (C3) — Range tab

**Corrected from TASK-110:** "x=183, y=120" → tap `(184, 7)`. Tab 1 (5D) left edge = `ST_CHART_TABS_X + 1 * ST_CHART_TAB_W = 130 + 36 = 166`, centre x = `166 + 18 = 184`, y = `ST_CHART_HEADER_H / 2 = 7`.

- Precondition: `stockSubView == "chart"`.
- Action: capture `lastChartFetch` baseline; `tap 184 7`.
- Assert: `get stockChartRange == "D5"`. `get lastChartFetch` resets to 0 after tab tap (the implementation sets `_s.lastChartFetch = 0` on tab change in `handleInput`); then `stockTickChart()` sets it to `millis()` on next `enqueueStockChart` call — so the harness should see `lastChartFetch` reset to 0 immediately, then advance within ~1 tick.
- Pass criterion: `stockChartRange == "D5"`, `lastChartFetch` advances from 0 within 2 s.

### T178 (C4) — Pre-fetch placeholder

**[spec correct]** — no canvas-bound reference.

- Precondition: drill-in just completed, chart fetch not yet returned.
- Assert: `get stockChartRange == "D1"`. Pixel check (manual): flat cyan line at y = `ST_CHART_PLOT_Y + ST_CHART_PLOT_H / 2 = 18 + 98 = 116`. Header shows `"<TICKER ---"`.
- Pass criterion (automated): `stockSubView == "chart"`, `stockChartRange == "D1"`, `lastChartFetch > 0`.

### T179 (C5) — Footer lo/hi

**[spec correct]** — no canvas-bound reference; footer drawn at `ST_CHART_FOOTER_Y=214`.

- Precondition: chart fetch complete.
- Assert: serial proxy — add `get stockChartLo` / `get stockChartHi` getters (future firmware addition); or accept manual-only. With getters: `lo < hi`. Without: SKIP on automated run.
- Pass criterion: manual verification of `lo:` and `hi:` text visible at y=214.

### T180 (C6) — Drill-in default range

**[spec correct]**

- Action: drill to chart from list (any row).
- Assert: `get stockChartRange == "D1"` immediately after drill-in.
- Pass criterion: `stockChartRange == "D1"`.

### T181 (C7) — Back then re-drill

**[spec correct]**

- Action: from chart, `tap 10 7` (back) → verify list; tap row 7 (NVDA, y=218) again.
- Assert: `stockSubView == "chart"`, `stockChartTicker == "NVDA"`.
- Pass criterion: both asserts true within 1 s.

### T182 (cross) — Stock canvas isolation

**Corrected from TASK-110:** "sub-canvas y:116..239" → full canvas y:0..239. The concern is that chart-view state does not bleed into a fresh list repaint. Use `_switch_to_stock()` (Option A, taskbar-driven) for this test to exercise the real UI path.

- Precondition: prior session had Stock in ChartDetail view. Clean state by: enter Stock → drill into chart → switch away → switch back.
- Action: `_switch_to_stock()` (taskbar scroll + slot tap); verify `stockSubView` — if chart, call `tap 10 7` to go to list. Verify `stockSubView == "list"`.
- Assert: `stockSubView == "list"`, `appId == "Stock"`, no residue from chart in the display. Pixel check: manual.
- Pass criterion: `stockSubView == "list"`; `_check_residue` passes after switching back to Spotify (confirms Spotify repaint was clean).

### T183 (error) — Inject fetch error

**[spec correct]** — no canvas-bound reference. Repaint trigger note added.

- Action: `set fetchFailed 1`; `set fetchErrorCode -1`. Wait one tick (~100 ms) for `tick()` to repaint. Tap canvas (e.g. `tap 137 120`) to exercise the `if (_s.fetchFailed) return true;` guard.
- Assert: display shows error screen (manual pixel check). `stockSubView` stays `"list"` (no drill-in allowed). Serial `tap 137 120` response should show `hit=STOCK` or equivalent non-drill action.
- Pass criterion: no crash, no drill-in on tap, error strings rendered (manual).

**Repaint note:** `dbgSet("fetchFailed")` mutates `_s.fetchFailed` but does not call `repaintError()`. The next `stockTickQuotes()` tick calls `repaintList()` which redirects to `repaintError()`. At 30 fps that is ≤ 33 ms. Harness sleep of 100 ms after the `set` is sufficient.

### T184 (error/chart) — Error in chart view

**[spec correct]**

- Action: drill into chart (any ticker); `set fetchFailed 1`; wait 100 ms.
- Assert: error screen shown (manual). `tap 10 7` → `stockSubView == "list"` (back button still works; `handleInput` does not guard the header zone on `fetchFailed` for chart view).
- Pass criterion: `stockSubView == "list"` after `tap 10 7`.

### T185 (error/recovery) — Error clears on success

**[spec correct]**

- Action: `set fetchFailed 1`; wait 100 ms (confirm error). `set triggerFetch 1`; wait up to 65 s for a real fetch to complete (`lastQuoteFetch` advances and `fetchFailed` becomes false).
- Assert: `get lastQuoteFetch` advances. Display returns to normal list (manual).
- Pass criterion: `lastQuoteFetch` advances after `triggerFetch`; no crash. `fetchFailed` must become false — add `get stockFetchFailed` getter if needed, or infer from successful repaint path.

---

## 5. Test Dependencies and Ordering

```
T169 — no dep; run first (pre-fetch state best captured at first activation)
T170 — run immediately after T169 (pre-fetch state)
T171 — dep: live data received; run after T173/T172 group
T172 — dep: T169 (Stock activated at least once); uses _check_residue
T173 — dep: T172 (Stock activated, quote received)
T174 — dep: T173 (Stock active, list view, fetch not failed)
T175 — dep: T174 (chart view entered)
T176 — dep: T175 or T178 (chart view, fetch complete)
T177 — dep: chart view active (any tab)
T178 — dep: T174 (drill-in just completed, before fetch returns) — time-sensitive; run before T176
T179 — dep: T176 (chart fetch complete)
T180 — dep: T175 (back to list); re-drill
T181 — dep: T180 (list view)
T182 — dep: T181 (chart view visited at least once); requires taskbar-driven switch
T183 — dep: Stock active (any view); clean state preferred
T184 — dep: chart view active (drill in before injecting error)
T185 — dep: T183 (error state established)
```

**Recommended execution order:** T169, T170, T172, T173, T174, T178, T175, T180, T181, T176, T179, T177, T182, T183, T184, T185, T171.

**Clean session requirement:** T169, T170 must run before any fetch completes. If run mid-session, `lastQuoteFetch` is already > 0 and prices are populated — T170 cannot verify pre-fetch state without resetting. Options: (a) run these first on each boot, (b) add `set resetStockState 1` firmware hook (forces `_s = {}` then `repaintList()`), (c) mark T170 as "boot-only" and document.

---

## 6. Host-Side vs DUT Test Split

### Host-side only (no DUT, no serial)

| ID | File | Description |
|----|------|-------------|
| T_SF_01 | `app/tools/test_yahoo_finance_api.py` | Yahoo Finance quote endpoint reachable |
| T_SF_02 | same | Quote response contains price + changePct fields |
| T_SF_03 | same | Response parses correctly for all 8 tickers |
| T_SF_04 | same | Chart endpoint reachable for D1 range |
| T_SF_05 | same | Chart response contains ≥ 2 price points |
| T_SF_06 | same | Rate limiting / error response handled gracefully |
| T_SF_07 | same | All 4 range types (D1/D5/1M/YTD) return valid data |

Run before DUT work: `python3 app/tools/test_yahoo_finance_api.py`.

### DUT-required (serial debug interface)

All of T169–T185. Requires `cyd2usb_winamp_debug` build, `SERIAL_DEBUG` defined, DUT on `/dev/ttyUSB0`, WiFi up.

T171, T176, T179 require manual pixel verification (or future `get pixel x y` serial command). They can be SKIP-annotated on automated runs.

T170 is best run immediately after boot (within 2 s of `switchApp 7`), before the dataTask returns. It can be skipped if the session is mid-flight.

---

## 7. ADR Reference

No new ADR is required. This document corrects the TASK-110 spec but does not introduce a new architectural decision:

- The `dbgGet`/`dbgSet` pattern on app classes is established (WinampDisplay precedent); extending it to StockApp is implementation, not architecture.
- The `switchApp <id>` serial command (Option B recommendation) is a serial debug extension. If adopted, it should be noted in **ADR-025** (or whichever ADR covers serial debug command extensions) as "added `switchApp <id>` debug command in `cyd2usb_winamp_debug` build." No standalone ADR warranted.
- Canvas bounds `y:0..239` for all non-Spotify apps is already the established rule (see `docs/memory/feedback_fullscreen_canvas.md`). The TASK-110 spec contained stale sub-canvas references from before that rule was locked. This document supersedes those references; no ADR change needed.

If the `switchApp` command is added to firmware, update `docs/project/tasks.md` TASK-110 notes to reference the command and mark the serial debug hooks as implemented.
