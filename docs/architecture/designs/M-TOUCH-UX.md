# Design — Touch UX Layer (M-TOUCH-UX)

> Owner: Architect
> Status: proposed (2026-05-31)
> ADR: ADR-035
> Addresses: scattered hitbox arithmetic; missing UX feedback for async actions

---

## Problem summary

1. **Scattered hitbox arithmetic.** Every app that needs regions reinvents `(y - START_Y) / ROW_H` and `(x - TABS_X) / COL_W` inline. No shared primitive.

2. **Silent touch registration.** Tap a StockApp row → chart fetch begins. Tap a Spotify transport button → HTTP action queues. The display does not change immediately. The user cannot tell whether the tap landed. They tap again. Two actions fire.

Old-style solution: cursor becomes a sand-glass. Our equivalent: the taskbar's 3 px active indicator bar turns amber.

---

## Part 1 — Hitbox primitive (`touch/hitbox.h`)

### What it provides

```cpp
// app/src/touch/hitbox.h
#pragma once
#include <stdint.h>

struct Rect { int16_t x, y, w, h; };

// Returns true if (px, py) is inside r (exclusive right/bottom edge).
inline bool hitTest(const Rect& r, int px, int py) {
    return px >= r.x && px < r.x + r.w
        && py >= r.y && py < r.y + r.h;
}

// Returns 0-based row index for py, or -1 if outside r vertically.
inline int hitTestRow(const Rect& r, int rowH, int py) {
    if (py < r.y || py >= r.y + r.h) return -1;
    return (py - r.y) / rowH;
}

// Returns 0-based column index for px, or -1 if outside r horizontally.
inline int hitTestCol(const Rect& r, int colW, int px) {
    if (px < r.x || px >= r.x + r.w) return -1;
    return (px - r.x) / colW;
}
```

### Adoption pattern — StockApp (before / after)

**Before** (`StockApp::handleInput`, list sub-view):
```cpp
if (y >= ST_LIST_ROW_START_Y && y < ST_CANVAS_Y + ST_CANVAS_H) {
    int rowIdx = constrain((y - ST_LIST_ROW_START_Y) / ST_LIST_ROW_H,
                           0, STOCK_TICKER_COUNT - 1);
    drillToChart((uint8_t)rowIdx);
    return true;
}
```

**After**:
```cpp
static constexpr Rect LIST_ROWS = {
    0, ST_LIST_ROW_START_Y, ST_CANVAS_X2 + 1,
    ST_LIST_ROW_H * STOCK_TICKER_COUNT
};
int row = hitTestRow(LIST_ROWS, ST_LIST_ROW_H, y);
if (row >= 0) { drillToChart((uint8_t)row); return true; }
```

**Before** (chart tabs):
```cpp
uint8_t tab = (uint8_t)constrain((x - ST_CHART_TABS_X) / ST_CHART_TAB_W, 0, 3);
```

**After**:
```cpp
static constexpr Rect TABS = { ST_CHART_TABS_X, ST_CHART_HEADER_Y, ST_CHART_TAB_W * 4, ST_CHART_HEADER_H };
int tab = hitTestCol(TABS, ST_CHART_TAB_W, x);
if (tab >= 0) { ... }
```

### What does NOT change

- `TouchPhase` enum and the `App::handleInput(TouchPhase, int, int)` interface — unchanged.
- The shell's gesture state machine (`s_inGesture`, `s_cooldownMs`) — unchanged.
- `WinampDisplay` hit-testing internals — the named hitbox functions (`hitTestVolume`, `hitTestPosbar`) are already well-structured; adopt `Rect` there only if it simplifies code.

### Debounce: two layers, both central

**Layer 1 — shell `s_cooldownMs` (existing):** 200 ms after a consumed Press; 300 ms after a taskbar drag end. Blocks the next Press at `appHandleInput()`. Covers hardware digitizer bounce and gesture re-fire.

**Layer 2 — WinampDisplay `touchScreenCoolDownTime` (bug fix):** `touchScreenCoolDownTime` is already set by several handlers inside `handleWinampInput()` — VIS (300 ms), Shuffle (250 ms), Repeat (250 ms) — but is **only checked in the SERIAL_DEBUG `injectTouch()` path, never in production**. In production these regions get the shell's 200 ms cooldown only, which is shorter than intended and causes the VIS cycling problem (too easy to skip past a mode).

Fix: add a single check at the top of Phase 2 in `handleWinampInput()`:

```cpp
// Phase 2 — D_IDLE only: run hit-tests.
if (millis() <= touchScreenCoolDownTime) {
    _tickMarquee();
    return false;
}
```

This makes `touchScreenCoolDownTime` effective in production for the first time. No existing value changes; the intended durations are already correct:

| Region | `touchScreenCoolDownTime` set | Before fix | After fix |
|--------|-------------------------------|------------|-----------|
| VIS | 300 ms | 200 ms (shell only) | 300 ms |
| Shuffle | 250 ms | 200 ms (shell only) | 250 ms |
| Repeat | 250 ms | 200 ms (shell only) | 250 ms |
| Transport | not set | 200 ms (correct) | unchanged |

Per-app debounce (e.g., `VOLUME_DRAG_DEBOUNCE_MS`) is separate semantic rate-limiting — it belongs in the app and is unaffected. No new generic debounce class is needed.

### Gesture recognition: deferred

The `Press / Move / Release` 3-phase pipeline handles all current interactions. A gesture recognizer (long-press, swipe-direction discrimination, pinch) would add recognizer latency to every tap. Deferred until a concrete interaction need.

---

## Part 2 — Shell busy indicator

### Indicator wire

The active-app indicator is a 3 px wide, `TASKBAR_SLOT_H` (40 px) tall vertical bar on the left edge of the active slot, painted by `renderTaskbar()`. Its colour is currently `TASKBAR_ACTIVE_COLOR = 0x07E0` (green) unconditionally.

**Change:** add a second colour `TASKBAR_BUSY_COLOR = 0xFD20` (amber). The indicator uses the busy colour when the shell busy flag is set.

```
Normal:   ███  green  0x07E0
Busy:     ███  amber  0xFD20
```

The rest of the taskbar (background, icon glyphs, separators) is unchanged. Only the 3×40 px bar changes colour.

### Shell state + API

In `main.cpp`:

```cpp
// Shell busy state — amber indicator while set.
static bool          g_shellBusy      = false;
static unsigned long g_shellBusySetMs = 0;

// Called by apps when async work starts or completes.
// Immediately repaints only the active-slot indicator.
namespace shell {
void setBusy(bool busy) {
    g_shellBusy = busy;
    if (busy) g_shellBusySetMs = millis();
    renderActiveIndicator(tft, currentAppId,
                          winampDisplay.tbScrollOffset(), (int)AppId::COUNT, busy);
}
}
```

Two clear paths in `loop()` (after `appTick()`):

```cpp
// Primary: clear as soon as the active app reports no in-flight work.
if (g_shellBusy && g_apps[(int)currentAppId] &&
    !g_apps[(int)currentAppId]->hasPendingAsync())
    shell::setBusy(false);

// Fallback: auto-clear after timeout regardless (safety net for any gap).
if (g_shellBusy && millis() - g_shellBusySetMs > SHELL_BUSY_TIMEOUT_MS)
    shell::setBusy(false);
```

`SHELL_BUSY_TIMEOUT_MS = 3000` — defined in `main.cpp`. The primary path clears the indicator within one loop iteration of the result arriving; the fallback handles cases where `hasPendingAsync()` never self-clears.

### `renderActiveIndicator()` — new function in `taskbar.h`

Repaints only the indicator strip for the active slot. Does not touch any other pixel.

```cpp
// Repaints the 3px active indicator for the slot showing activeApp.
// Call when busy state changes; call also from renderTaskbar() to avoid duplication.
// totalApps must match the value passed to renderTaskbar() — always (int)AppId::COUNT.
inline void renderActiveIndicator(TFT_eSPI& tft, AppId activeApp,
                                  int scrollOffset, int totalApps, bool busy) {
    uint16_t col = busy ? TASKBAR_BUSY_COLOR : TASKBAR_ACTIVE_COLOR;
    for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i) {
        int appIdx = (scrollOffset + i) % totalApps;
        if (appIdx == (int)activeApp) {
            int slotY = i * TASKBAR_SLOT_H;
            tft.fillRect(TASKBAR_X, slotY, 3, TASKBAR_SLOT_H, col);
            return;
        }
    }
}
```

`renderTaskbar()` calls `renderActiveIndicator()` internally instead of painting the bar inline — no duplicated constant.

### `TASKBAR_BUSY_COLOR` placement

```cpp
#define TASKBAR_BUSY_COLOR   0xFD20   // amber — busy/processing indicator
```

**Define this constant in `taskbar.h`, not in `app/gen/shell_layout.h`.** `shell_layout.h` is covered by `app/gen/golden.sha256`; any manual addition invalidates `check_build.sh` check 3/4. `taskbar.h` is a hand-written file not in the golden hash — adding the constant there keeps the generated file clean and avoids a check_build failure. `TASKBAR_ACTIVE_COLOR` is in `shell_layout.h` because it is exported by the preview tool; `TASKBAR_BUSY_COLOR` is a firmware-only constant and does not need to be in the generated file.

### `hasPendingAsync()` canonical contract

`hasPendingAsync()` means **async work is currently in flight** — not "the last input triggered async." Every override must self-clear when the work completes. The shell polls this in `loop()` and clears the indicator immediately when it returns false.

```cpp
// appShell.h — App ABC addition:
// Return true while async work initiated by handleInput() is still in flight.
// Self-clears when the work completes (result polled, queue drained).
// Shell checks this after every handleInput() call AND on every loop() iteration.
// Default false — apps with no async input need not override.
// Note: intentionally non-pure virtual — breaks the "all methods pure" convention
// of App; justified because a no-op default is safe and avoids forcing every
// app subclass to add a boilerplate override.
virtual bool hasPendingAsync() const { return false; }
```

`appHandleInput()` calls `handleInput()` at four locations (Release-on-taskbar-interrupt, Press, Move, Release-on-finger-up). The busy setter **must appear after every one of these four call sites**, not only after Press. `StockApp` dispatches async work on Release (not Press), so a setter placed only at the Press site will never fire for Stock.

```cpp
// Pattern repeated after each of the 4 handleInput() call sites:
g_apps[id]->handleInput(phase, x, y);
if (!g_shellBusy && g_apps[id]->hasPendingAsync()) shell::setBusy(true);
```

The `!g_shellBusy` guard prevents resetting `g_shellBusySetMs` on Move events while already busy (would delay the auto-clear fallback timer).

The `loop()` poll clears busy as soon as `hasPendingAsync()` returns false.

### App integration points

**StockApp — internal flag (self-clearing):**

```cpp
// StockApp private:
bool _pendingAsync = false;

bool hasPendingAsync() const override { return _pendingAsync; }
void suspend()        override { /* existing logic */ _pendingAsync = false; }

void drillToChart(uint8_t idx) {
    // Only set _pendingAsync when a fetch is actually enqueued (cache stale check).
    // If the cache is still fresh, no fetch fires and pollStockChart() will never
    // deliver a result — leaving _pendingAsync=true would stall amber until timeout.
    if (!_s.lastChartFetch || millis() - _s.lastChartFetch > STOCK_CHART_FETCH_INTERVAL) {
        dataTask::enqueueStockChart(idx, ...);
        _pendingAsync = true;    // loop() polling will set amber next iteration
    }
    repaintChart();
}

void stockTickChart() {
    if (dataTask::pollStockChart(&r)) {
        _pendingAsync = false;   // loop() polling clears amber next iteration
        repaintChart();
    }
}
```

Same pattern for tab range changes: `_pendingAsync = true` only inside the `if` block that calls `enqueueStockChart`; cleared on `pollStockChart()` resolve.

**SpotifyApp — via spotifyTask queue depth (simplified):**

`SpotifyApp::hasPendingAsync()` queries the spotifyTask action queue directly — no intermediate dispatch flag:

```cpp
// SpotifyApp (as implemented):
bool hasPendingAsync() const override {
    return spotifyTask::hasPendingActions();
}
bool handleInput(TouchPhase phase, int x, int y) override {
    return winampDisplay.handleWinampInput(phase, x, y);
}
void suspend() override { winampDisplay.resetDragState(); }
```

The spotifyTask action queue is exclusively user-initiated (PREV, PLAY, PAUSE, STOP, NEXT, Shuffle, Repeat, seek, volume, PLEDIT row tap, reconnect). `hasPendingActions()` true means a user tap is still in flight. `cmdTap` also enqueues via `injectTouch()`, so both production touches and injected taps are covered.

`WinampDisplay._lastInputWasAsync` / `wasLastInputAsync()` remain in `winampDisplay.h` (always-on, non-SERIAL_DEBUG) but are not consumed by `SpotifyApp` — the direct queue query made the flag-chain unnecessary. `WinampDisplay` has zero shell dependency.

`spotifyTask::hasPendingActions()` — a new public query on the task, returning true while the action queue is non-empty. **Thread safety:** implementation must use a `volatile bool _actionPending` flag. **Semantics:** the flag is cleared only when `xQueueReceive` returns `pdFALSE` (queue empty after dequeue), not on every dequeue. Clearing on every dequeue would cause `hasPendingAsync()` to return false between queued items when multiple actions are enqueued, making the amber indicator flash for each action. Developer to confirm the existing queue implementation uses `xQueueReceive` (FreeRTOS queue) before coding.

No app ever calls `shell::setBusy()` directly.

**WeatherApp / CryptoApp / MatrixApp / LifeApp / ClockApp:** No user-initiated async actions. No `setBusy()` calls needed.

### App switch while busy — `switchApp()` clears busy

`switchApp()` calls `shell::setBusy(false)` immediately after `suspend()` and before `renderTaskbar()`. This ensures:
- The suspended app's `_pendingAsync` is reset by `suspend()` (see contract above). SpotifyApp has no such flag — its queue drains independently.
- The new active slot is always painted green on switch, regardless of prior busy state.

```cpp
void switchApp(AppId next) {
    if (next == currentAppId) return;
    g_apps[(int)currentAppId]->suspend();
    shell::setBusy(false);   // ← clear before new taskbar paint.
                             // Note: currentAppId is still the OLD app here.
                             // setBusy(false) calls renderActiveIndicator() on the old slot
                             // (paints it green), then renderTaskbar() below overwrites it.
                             // Net result is correct; the intermediate paint is harmless.
    tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
    currentAppId = next;
    // ... init/resume ...
    renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(),
                  (int)AppId::COUNT, false);        // always green on switch
}
```

### `suspend()` contract addition

The existing `suspend()` layering rule (rule 6) states: "must always reset drag/gesture state."

**Addition:** `suspend()` must also reset any `_pendingAsync` flag, so `hasPendingAsync()` returns false immediately after suspension. This prevents the shell's `loop()` polling from seeing stale in-flight state on the newly-active app. SpotifyApp has no such flag — `spotifyTask::hasPendingActions()` self-clears as the queue drains, and `switchApp()` calls `shell::setBusy(false)` before the new app's taskbar paint.

### Full repaint path

`renderTaskbar()` signature gains `bool busy` param (default `false`):

```cpp
void renderTaskbar(TFT_eSPI& tft, AppId activeApp, int scrollOffset,
                   int totalApps, bool busy = false);
```

Internally delegates to `renderActiveIndicator()`. Default preserves all existing callers. `switchApp()` always passes `false`. The only caller that passes `g_shellBusy` is future code that repaints the taskbar while the shell remains in a busy state (e.g., a taskbar scroll during a pending fetch).

---

## File list

| File | Change |
|------|--------|
| `app/src/touch/hitbox.h` | new |
| `app/src/taskbar/taskbar.h` | add `TASKBAR_BUSY_COLOR 0xFD20` (here, not shell_layout.h — avoids golden hash invalidation); add `renderActiveIndicator(TFT_eSPI&, AppId, int scrollOffset, int totalApps, bool busy)`; `renderTaskbar()` gains `bool busy` param; calls `renderActiveIndicator()` |
| `app/src/main.cpp` | `g_shellBusy`, `g_shellBusySetMs`, `SHELL_BUSY_TIMEOUT_MS`; `shell::setBusy()`; auto-clear in `loop()`; pass `g_shellBusy` to `renderTaskbar()` in `switchApp()` |
| `app/src/appShell.h` | add `hasPendingAsync() const` virtual method (default `false`); extend `suspend()` contract comment |
| `app/src/winamp/winampDisplay.h` | add `touchScreenCoolDownTime` Phase 2 check (one line, top of Phase 2 block); add `_lastInputWasAsync` bool + `wasLastInputAsync()` accessor; set at all async dispatch sites in both Phase 2 and Release-path; no shell dependency |
| `app/src/winamp/vuMeter.h` | add `vu::currentMode()` public getter (wraps the function-local static mode) — required for `get visMode` SERIAL_DEBUG deliverable |
| `app/src/spotifyTask.h` | add `hasPendingActions()` public query; `volatile bool _actionPending` flag cleared only when queue becomes empty (not on every dequeue) |
| `app/src/main.cpp` (SpotifyApp) | `hasPendingAsync()` = `spotifyTask::hasPendingActions()` directly; no `_actionDispatched` flag; `handleInput()` delegates to `winampDisplay.handleWinampInput()` without inspecting `wasLastInputAsync()`; `suspend()` calls `winampDisplay.resetDragState()` only |
| `app/src/main.cpp` (StockApp) | `bool _pendingAsync`; set inside the stale-cache `if` block only (not unconditionally); cleared on `pollStockChart()` resolve; `suspend()` resets flag |
| `app/src/main.cpp` (appHandleInput) | (2b gate) extend Press guard: `if (!s_inGesture && (millis() <= s_cooldownMs \|\| g_shellBusy)) return;`; (busy set) `if (!g_shellBusy && app->hasPendingAsync()) shell::setBusy(true)` after **all four** `handleInput()` call sites (Release-on-taskbar-interrupt, Press, Move, Release-on-finger-up); `cmdTap` must also check `g_shellBusy` before calling `handleInput()` for canvas taps, so injected taps obey the same gate as physical touches |
| `app/src/main.cpp` (loop) | primary clear: poll `hasPendingAsync()` each loop; fallback auto-clear after `SHELL_BUSY_TIMEOUT_MS` |
| `app/src/main.cpp` (switchApp) | call `shell::setBusy(false)` after `suspend()`, before `renderTaskbar()` |
| `app/src/main.cpp` (cmdGet) | add `shellBusy` variable to SERIAL_DEBUG `get` dispatcher |

---

## What does NOT change

- `TouchPhase` enum — no change.
- `appHandleInput()` gesture state machine (Press/Move/Release sequencing, cooldown) — no change.
- Any app that has no user-initiated async work — no override of `hasPendingAsync()` needed.
- SERIAL_DEBUG `cmdTap` / `cmdDrag` injection path — **exception:** `cmdTap` currently calls `g_apps[id]->handleInput()` directly, bypassing `appHandleInput()` and its `g_shellBusy` gate. `cmdTap` must be updated to check `g_shellBusy` before dispatching canvas taps, so injected touches simulate the same gate that physical touches experience. This is a required change — without it, T-CDWN-02 will always produce N+2 fetches regardless of the gate. Taskbar-range taps in `cmdTap` are unaffected (they already bypass the gate by design).

**What does change in the ABC:** `App` gains `hasPendingAsync()` (non-pure virtual, default `false`) and the `suspend()` contract is extended to require resetting any pending-async flag.

---

## Exit criteria (for VE)

| ID | Criterion |
|----|-----------|
| T-BUSY-01 | `switchApp(Stock)` → `tap 137 36` (AAPL row 0) → poll `get shellBusy` until `busy==true` (max 500 ms deadline; miss = test gap, not firmware defect) → poll `get chartLen` until `> 0` (fetch complete) → `get shellBusy` returns `busy==false`. Use poll-until-true for busy, not a single get — loop iteration timing means a single get may miss the transition window. |
| T-BUSY-01b | `switchApp(Stock)` → drill to chart (tap row 0) → tap a range tab (e.g. tab 5D at `tap <ST_CHART_TABS_X + ST_CHART_TAB_W/2> <ST_CHART_HEADER_Y + ST_CHART_HEADER_H/2>`) → poll `get shellBusy` until `busy==true` (max 500 ms). Verifies the tab-range change code path also sets `_pendingAsync`. |
| T-BUSY-02 | `switchApp(Spotify)` → `tap <coords.tap_button("PLAY")>` → poll `get shellBusy` until `busy==true` (max 500 ms); returns `busy==false` within `SHELL_BUSY_TIMEOUT_MS` (3 s) or sooner once `spotifyTask` queue drains. |
| T-BUSY-03 | For each of Clock, Weather, Crypto, Matrix, Life, Aquarium: switch to app, tap anywhere on the app canvas (e.g. centre `137 120`), `get shellBusy` returns `busy==false`. |
| T-BUSY-04 | `[MANUAL]` Auto-clear path: `switchApp(Stock)` → `tap 137 36` → wait 3100 ms without interacting → `get shellBusy` returns `busy==false`. Requires the fetch to still be in-flight at 3 s — run on a network-blocked DUT (WiFi disabled) or with `set fetchFailed 1` pre-injected to hold `_pendingAsync` open. No automated CI path exists without a `set freezeFetch` Developer deliverable; mark manual until that deliverable is added. |
| T-BUSY-05 | `switchApp(Stock)` → `tap 137 36` (amber set) → poll `get shellBusy` until `busy==true` → `switchApp(Spotify)` → poll `get shellBusy` 3× at 20 ms intervals; all must return `busy==false` (detects re-arm if Stock's `suspend()` fails to reset `_pendingAsync`, or if `switchApp()` fails to call `shell::setBusy(false)`). `[VISUAL]` taskbar Spotify slot appears green — manual verification only; harness cannot read pixel colour. |
| T-CDWN-01 | `switchApp(Spotify)` → `set cooldown 0` (zero `touchScreenCoolDownTime`) → `get visMode` (baseline M0) → `tap <VIS x,y>` (tap 1; cycles to M1) → `get visMode == M1` → sleep 220–280 ms (shell `s_cooldownMs` elapsed; `touchScreenCoolDownTime` still live: 300 ms from tap 1) → `tap <VIS x,y>` (tap 2; Phase 2 gate active) → `get visMode == M1` (unchanged; second tap suppressed by `touchScreenCoolDownTime`) → sleep 100 ms → `tap <VIS x,y>` (tap 3; gate elapsed at 320–380 ms) → `get visMode == M2`. Tests the Phase 2 gate specifically — **not** the shell gate (which fires within 200 ms; tapping within 200 ms would only prove the shell gate, not the bug fix). |
| T-CDWN-02 | `switchApp(Stock)` → `get fetchOkCount` (baseline N) → `tap 137 36` (fetch starts) → poll `get shellBusy` until `busy==true` (max 500 ms; ensures gate is active before second tap) → `tap 137 36` (second tap; `g_shellBusy` gate blocks it via `cmdTap` g_shellBusy check) → poll `get shellBusy` until `busy==false` → `get fetchOkCount == N+1` (one fetch, not two). |
| T-CDWN-03 | `switchApp(Stock)` → `tap 137 36` → poll `get shellBusy` until `busy==true` → `tap <taskbar_clock x,y>` (x ≥ 275; taskbar tap executes before the canvas `g_shellBusy` gate) → `get appId == Clock` → `get shellBusy == false`. |

**Developer deliverables required before VE can execute:**

| Deliverable | Gates | Response schema |
|-------------|-------|-----------------|
| `get shellBusy` in SERIAL_DEBUG `cmdGet()` | T-BUSY-01..05, T-CDWN-02/03 | `{"ok":true,"cmd":"get","var":"shellBusy","busy":<bool>,"last":true}` — `busy` is a JSON boolean (`true`/`false`), matching the `weatherReady`/`cryptoReady` convention. |
| `get visMode` in SERIAL_DEBUG `cmdGet()` | T-CDWN-01 | `{"ok":true,"cmd":"get","var":"visMode","mode":<int>,"last":true}` — `mode` is an integer: `0`=`VIS_ATLAS_MODE`, `1`=`VIS_VU`, `2`=`VIS_BLANK`, `3`=`VIS_WAVE_ATLAS`. Requires `vu::currentMode()` getter in `vuMeter.h`. |
| `cmdTap` canvas path checks `g_shellBusy` | T-CDWN-02 | No new JSON field — behavioural change: a `tap` to a canvas coordinate while `g_shellBusy==true` is silently dropped (same as a physical touch through `appHandleInput()`). |

---

## Resolved decisions

1. **`hasPendingAsync()` canonical semantics: "currently in flight."** Both StockApp and SpotifyApp self-clear when work completes. The shell's `loop()` polls and clears the indicator promptly; auto-clear is fallback only. (VE-CH1, VE-CH2)

2. **SpotifyApp chain simplified to direct queue query.** `SpotifyApp::hasPendingAsync()` = `spotifyTask::hasPendingActions()` directly; no `_actionDispatched` flag in SpotifyApp. `WinampDisplay._lastInputWasAsync` / `wasLastInputAsync()` remain in WinampDisplay but are not consumed by SpotifyApp. (VE-CH2)

3. **`switchApp()` clears busy; `suspend()` resets pending flag.** New active slot always painted green on switch. (VE-CH3)

4. **`get shellBusy` is a required Developer deliverable.** Not optional. VE test scripts block on it. (VE-TG1)

5. **Stock quote fetch: silent.** Only user-initiated actions (row tap → chart, tab tap → range) set `_pendingAsync`. Background 60 s quote refresh does not.

6. **`_pendingAsync = true` only when a fetch is actually enqueued.** `drillToChart()` has a stale-cache guard; `_pendingAsync` is set inside that guard only. Unconditional set would leave the indicator stuck amber on a cache hit. (DEV-F5)

7. **`hasPendingActions()` clears `_actionPending` on queue-empty, not on dequeue.** Flag cleared only when `xQueueReceive` returns `pdFALSE`. Clearing on every dequeue would flash amber between queued items. (DEV-F2)

8. **`_lastInputWasAsync` covers Release-path dispatch sites.** Seek-drag, volume-drag, PLEDIT tap fire on Release. `SpotifyApp::handleInput()` checks `wasLastInputAsync()` after both the Press and Release delegate calls. (DEV-F3)

9. **`TASKBAR_BUSY_COLOR` in `taskbar.h`, not `shell_layout.h`.** Avoids invalidating `check_build.sh` golden hash. (DEV-F9)

10. **`cmdTap` canvas path must check `g_shellBusy`.** Without this, injected taps bypass the gate that physical touches experience, making T-CDWN-02 untestable. Taskbar-range taps unaffected. (DEV-F1)

11. **`renderActiveIndicator()` takes `totalApps` param.** Consistent with `renderTaskbar()`; always passed `(int)AppId::COUNT`. (DEV-F6)

12. **T-CDWN-01 tests Phase 2 gate, not shell gate.** Requires `set cooldown 0` + 220–280 ms sleep between tap 1 and tap 2 to reach the `touchScreenCoolDownTime` check after the shell `s_cooldownMs` has elapsed. (VE-F3)
