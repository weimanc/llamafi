# M-MULTIAPP — App Interface and AppShell Refactor

> Owner: Architect
> Status: draft — awaiting review
> Date: 2026-05-25
> Part of: [overview.md](overview.md)
> Feeds: ADR-026
> Supersedes: partial spec in [app-lifecycle.md](app-lifecycle.md) §switchApp and §Per-app tick and input dispatch

---

## Context

M-MULTIAPP step 2 (TASK-087 / commit 1c3ee13) shipped the taskbar strip, `switchApp()`, and the Clock app. A post-mortem identified four active defects with a single common root: the `App` lifecycle interface specified in `app-lifecycle.md` was not implemented. Instead, app dispatch is ad-hoc switch statements in `main.cpp`, and `WinampDisplay` owns taskbar hit-testing and calls `switchApp()` directly.

### Bug catalogue

| # | Symptom | Root cause | Severity |
|---|---------|-----------|----------|
| B1 | Taskbar shows S/C/W at boot; $/M/G appear only after a tap | `drawPlaylist()` right-gutter `fillRect(275, 116, 45, 124, BLACK)` wipes slots 3–5; `renderTaskbar()` not called afterward | High — always visible |
| B2 | Winamp transport sprites appear on Clock canvas | `pendingReleaseAt` deferred paint in `WinampDisplay::checkForInput()` fires before the `currentAppId != Spotify` guard | High — repro on any transport tap before switching |
| B3 | PLEDIT blank after switching back to Spotify | `repaintChrome()` repaints y=0–115 only; PLEDIT (y=116–239) not cleared; `drawPlaylist()` won't redraw unless seqno changes | High — always repros |
| B4 | PLEDIT row text starts left of visible area after extended runtime | `scrollOffset` potentially stale on resume; intermittent | Medium — unknown repro |

All four are symptoms of the same structural gap: no `suspend`/`resume` contract, and `WinampDisplay` bleeding into the shell's responsibilities.

---

## Goals

1. **`App` interface** — `init`, `resume`, `suspend`, `tick`, `handleInput` — implemented by every app. Shell only sees the interface.
2. **`WinampDisplay` decoupled from the shell** — no `#include "appShell.h"`, no `currentAppId` references, no `switchApp()` calls inside `WinampDisplay`.
3. **Taskbar input owned by the shell** — `appHandleInput()` in `main.cpp` checks `p.x >= TASKBAR_X` before delegating to the active app. Apps never see taskbar taps.
4. **Bugs B1–B4 fixed as consequences** of the correct lifecycle, not as patches.
5. **Zero new RAM cost** — apps are statically allocated; no heap, no vtable overhead beyond what we already pay for `SpotifyDisplay`.

---

## Design

### App interface

Declared in `appShell.h`. Pure virtual; statically allocated concrete instances.

```cpp
// Gesture phase delivered by the shell on every loop() iteration.
// Press  — first sample of a new finger-down gesture.
// Move   — continued samples while finger remains down.
// Release — finger lifted; x/y are last known coords.
enum class TouchPhase : uint8_t { Press, Move, Release };

struct App {
    // Called once on first switch to this app.
    virtual void init()    = 0;

    // Called on every subsequent switch to this app, after canvas cleared.
    // Must repaint the full app canvas (x: 0..TASKBAR_X-1, y: 0..239).
    virtual void resume()  = 0;

    // Called when switching away.
    // REQUIRED: reset all drag/gesture state before returning.
    // The shell guarantees suspend() is called before any switchApp() completes,
    // but suspend() must be idempotent — never assume a Release was delivered.
    virtual void suspend() = 0;

    // Called every loop() when this app is active.
    virtual void tick()    = 0;

    // Called by the shell on every loop() with the current gesture state.
    // Shell tracks the gesture lifecycle; apps do not call ts.touched() directly.
    // Taskbar taps are consumed by the shell before this is called.
    // x, y: app-canvas coordinates (x < TASKBAR_X).
    // Release: x/y are the last known coords from the preceding Move/Press.
    // Return true if the Press was consumed (shell applies inter-gesture cooldown).
    // Return value is ignored for Move and Release phases.
    virtual bool handleInput(TouchPhase phase, int x, int y) = 0;

    virtual ~App() = default;
};
```

### App registry

`main.cpp` holds one static instance per app and a pointer array:

```cpp
static SpotifyApp  g_spotifyApp;   // wraps WinampDisplay
static ClockApp    g_clockApp;
// future: WeatherApp, CryptoApp, MatrixApp, LifeApp

App* g_apps[(int)AppId::COUNT] = {
    &g_spotifyApp,   // AppId::Spotify = 0
    &g_clockApp,     // AppId::Clock   = 1
    // ...
};
```

### Revised `switchApp()`

```cpp
void switchApp(AppId next) {
    if (next == currentAppId) return;

    // 1. Let active app save its state.
    g_apps[(int)currentAppId]->suspend();

    // 2. Clear app canvas. Taskbar strip (x >= TASKBAR_X) is untouched.
    tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);

    currentAppId = next;

    // 3. Incoming app: init (first launch) or resume (subsequent).
    if (!g_appLaunched[(int)next]) {
        g_appLaunched[(int)next] = true;
        g_apps[(int)next]->init();
    } else {
        g_apps[(int)next]->resume();
    }

    // 4. Taskbar active indicator updated last, over the app's repaint.
    renderTaskbar(tft, currentAppId);
}
```

### Revised `appHandleInput()`

Shell owns the taskbar check and drives the gesture state machine. Apps never call `ts.touched()` directly.

```cpp
// Module-level shell gesture state (main.cpp).
static bool          s_inGesture    = false;
static int           s_lastTouchX   = 0, s_lastTouchY = 0;
static unsigned long s_cooldownMs   = 0;   // inter-gesture cooldown

void appHandleInput(AppId) {
    bool touched = ts.touched();

    if (touched) {
        CYD28_TS_Point p = ts.getPointScaled();
        spotifyTask::resetBackoff();

        // Taskbar: highest priority. Synthesise Release first if mid-gesture.
        if (p.x >= TASKBAR_X) {
            if (s_inGesture) {
                g_apps[(int)currentAppId]->handleInput(
                    TouchPhase::Release, s_lastTouchX, s_lastTouchY);
                s_inGesture = false;
            }
            int slot = (int)p.y / TASKBAR_SLOT_H;
            if (slot >= 0 && slot < (int)AppId::COUNT)
                switchApp(static_cast<AppId>(slot));
            s_cooldownMs = millis() + 300;
            return;
        }

        // Inter-gesture cooldown gate (applies to Press only).
        if (!s_inGesture && millis() <= s_cooldownMs) return;

        s_lastTouchX = p.x; s_lastTouchY = p.y;
        if (!s_inGesture) {
            s_inGesture = true;
            bool consumed = g_apps[(int)currentAppId]->handleInput(
                TouchPhase::Press, p.x, p.y);
            if (consumed) s_cooldownMs = millis() + 200;
        } else {
            g_apps[(int)currentAppId]->handleInput(
                TouchPhase::Move, p.x, p.y);
        }

    } else if (s_inGesture) {
        // Finger lifted — guaranteed Release delivery.
        s_inGesture = false;
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, s_lastTouchX, s_lastTouchY);
        s_cooldownMs = millis() + 200;
    }
}
```

**Cooldown ownership:**

- **Inter-gesture cooldown** (`s_cooldownMs`) — shell-owned. Blocks the next Press for 200–300ms after a Release or taskbar tap. Prevents gesture re-fire.
- **Intra-gesture debounce** (volume enqueue rate-limiting at 3/s, logo-tap 2 s lockout) — app-owned, internal to each `handleInput()` implementation. These are semantic concerns, not input-layer concerns.

> **Serial injection:** `drainInjectionQueue()` currently calls `wd->injectTouch(sx, sy)` / `wd->injectRelease()` on `WinampDisplay` directly. With this refactor, call `winampDisplay.handleWinampInput(TouchPhase::Press/Move/Release, sx, sy)` directly — bypassing the shell gesture tracker is intentional for the injection path, which drives its own sequencing. `_injectingDrag` guard and the injection queue remain in SERIAL_DEBUG builds only.

### Revised `appTick()`

```cpp
void appTick(AppId id) {
    g_apps[(int)id]->tick();
}
```

All app-specific tick logic moves into the concrete `tick()` implementations.

---

## Concrete app implementations

### SpotifyApp

Thin wrapper around `WinampDisplay`. Lives in `main.cpp` or a new `spotifyApp.h`.

```cpp
class SpotifyApp : public App {
public:
    void init() override {
        winampDisplay.showDefaultScreen();   // resets all cache fields + full repaint
    }

    void resume() override {
        // Repaint main window chrome from cached fields.
        winampDisplay.repaintChrome();
        // Force PLEDIT repaint on next tick (fixes B3).
        winampDisplay.invalidatePlaylist();
    }

    void suspend() override {
        // Reset all WinampDisplay drag/gesture state (layering rule 6).
        // Must be called before any app switch — never assume Release was delivered.
        winampDisplay.resetDragState();   // dragState = D_IDLE; pendingReleaseAt = 0
        // TASK-088 (saveAppState) will add explicit snapshot field copies here.
    }

    void tick() override {
        vu::tick(winampDisplay.chromeOriginX(), winampDisplay.chromeOriginY(), SKIN_MAIN_BG);
        winampDisplay.drawPlaylist();
#ifdef NFC_ENABLED
        // nfcLoop omitted for brevity
#endif
        updateCurrentlyPlaying(false);
        updateProgressBar();
    }

    bool handleInput(TouchPhase phase, int x, int y) override {
        return winampDisplay.handleWinampInput(phase, x, y);
    }
};
```

**Key WinampDisplay changes required:**

1. **Remove `#include "appShell.h"` from `winampDisplay.h`.**
2. **Remove `checkForInput()` override** — the `ts.touched()` read and taskbar check move to the shell. The override on `SpotifyDisplay` is retired; serial debug callers updated separately (see serial injection note above).
3. **Add `handleWinampInput(TouchPhase phase, int x, int y)`** — the current `checkForInput()` hit-test body, now driven by the shell's pre-classified gesture. The `pendingReleaseAt` deferred-paint block triggers on `TouchPhase::Release` (or remains as a millis() check that fires when called — either works since `handleWinampInput` is called every loop via `SpotifyApp::handleInput`). It naturally only runs when Spotify is the active app (fixes B2).
4. **Add `resetDragState()`** — `dragState = D_IDLE; pendingReleaseAt = 0; _injectingDrag = false`. Called from `SpotifyApp::suspend()`.
5. **Add `invalidatePlaylist()`** — resets `lastQueueSeqno = 0xFFFFFFFF`, sets `_pleditScrollDirty = true`. Call from `SpotifyApp::resume()` (fixes B3).
6. **Fix `drawPlaylist()` gutter** (fixes B1):
   ```cpp
   // Before:
   if (rightEdge < screenWidth)
       tft.fillRect(rightEdge, PLEDIT_Y, screenWidth - rightEdge, PLEDIT_H, TFT_BLACK);
   // After:
   if (rightEdge < TASKBAR_X)
       tft.fillRect(rightEdge, PLEDIT_Y, TASKBAR_X - rightEdge, PLEDIT_H, TFT_BLACK);
   ```
7. **Remove `renderTaskbar()` call** from `repaintChrome()`. Taskbar rendering is the shell's responsibility; `repaintChrome()` paints only the Winamp canvas.

### ClockApp

Currently inline in `main.cpp` as free functions. Promote to a class.

```cpp
class ClockApp : public App {
public:
    void init()    override { repaint(); }
    void resume()  override { repaint(); }
    void suspend() override {}

    void tick() override {
        if (millis() - s_lastTickMs < 1000) return;
        s_lastTickMs = millis();
        drawTime();
        drawSecondsBar();
        drawDate();
        drawRssi();
    }

    bool handleInput(TouchPhase, int, int) override { return false; }

private:
    void repaint() {
        tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
        tft.drawRoundRect(5,   5, 265,  80, 10, 0xF81F);
        tft.drawRoundRect(5,  88, 265,  47, 10, 0x07FF);
        tft.drawRoundRect(5, 138, 265,  97, 10, 0xFFE0);
        s_lastTickMs = 0;   // force immediate draw
        tick();
    }
    unsigned long s_lastTickMs = 0;
    // drawTime(), drawSecondsBar(), drawDate(), drawRssi() — refactored from clockTick()
};
```

### Future apps (Weather, Crypto, Matrix, Life)

Each will be a class implementing `App`. No impact on the shell once this refactor lands.

---

## Migration: what moves where

| Current location | Moves to |
|-----------------|---------|
| `WinampDisplay::checkForInput()` taskbar block | `appHandleInput()` in `main.cpp` |
| `WinampDisplay::checkForInput()` Winamp hit-tests | `WinampDisplay::handleWinampInput(int x, int y)` |
| `WinampDisplay::checkForInput()` `pendingReleaseAt` block | triggers on `TouchPhase::Release` in `handleWinampInput()` — only called when Spotify active |
| `WinampDisplay::repaintChrome()` `renderTaskbar()` call | removed; shell calls it after `resume()` |
| `clockRepaint()` / `clockTick()` free functions in `main.cpp` | `ClockApp::repaint()` / `ClockApp::tick()` private methods |
| `appTick()` switch body | `App::tick()` implementations |
| `appHandleInput()` body | split: taskbar portion stays; app portion delegates to `App::handleInput()` |
| `#include "appShell.h"` in `winampDisplay.h` | removed; WinampDisplay has no shell dependency |

### What does NOT move

- `SpotifyDisplay*` / `spotifyDisplay` pointer — kept for the WiFiManager and refresh-token flow (those callers don't switch apps; they run before the main loop). Decouple as a separate task if needed.
- `g_appLaunched[]`, `g_apps[]` — `main.cpp` module-level.
- `g_appState[]` union — kept for TASK-088 (`saveAppState`/`restoreAppState`). `SpotifyApp::suspend()` will fill it when TASK-088 lands.

---

## Bug fix summary

| Bug | Fixed by |
|-----|---------|
| B1 (taskbar wipe) | `drawPlaylist()` gutter: `screenWidth` → `TASKBAR_X` |
| B2 (Winamp sprites on Clock) | `pendingReleaseAt` block stays in `handleWinampInput()`; only called when Spotify active |
| B3 (PLEDIT blank on resume) | `SpotifyApp::resume()` calls `invalidatePlaylist()` after `repaintChrome()` |
| B4 (text left-overflow) | `invalidatePlaylist()` resets `scrollOffset` via the seqno change path; add `scrollOffset = max(0, min(scrollOffset, max(0, qs.count - PLEDIT_ROW_COUNT)))` clamp at top of `drawPlaylist()` |

---

## Layering rules (new, binding)

These are the invariants this refactor enforces. Violations are architecture bugs.

1. **`WinampDisplay` has no `appShell.h` dependency.** It does not include `AppId`, `currentAppId`, `switchApp()`, or `g_apps[]`.
2. **Taskbar hit-testing lives exclusively in `appHandleInput()`** in `main.cpp`. No app's `handleInput()` checks `p.x >= TASKBAR_X`.
3. **`App::resume()` is responsible for painting the full app canvas.** No app assumes any pixels are pre-cleared by the caller (the shell does clear, but the app must not depend on it).
4. **`App::tick()` must be idempotent** — calling it when state hasn't changed must produce no visible change (no flicker from redundant draws).
5. **`renderTaskbar()` is called by the shell only** — from `switchApp()` and from setup after `init()`. Not from any `App` implementation.
6. **`App::suspend()` must always reset drag/gesture state**, even if no Release event was delivered. The shell guarantees a synthesised Release before any `switchApp()`, but `suspend()` is the belt-and-suspenders: it must be idempotent and leave no gesture state active.
7. **Apps do not call `ts.touched()`** — the shell is the sole reader of the touch hardware. `handleInput(phase, x, y)` is the app's only touch signal.

---

## Verification impact

### Existing tests — expected behaviour

- **T147/T148** — Spotify↔Clock switch round-trip. Must still pass. Additionally verify taskbar slots 4–6 are visible after the first `drawPlaylist()` call post-boot (B1 regression guard). No harness change needed — slots visible means the gutter fix is in effect.
- **T076/T081/T082** — transport button hit-test. `handleWinampInput(TouchPhase, x, y)` replaces `checkForInput()`; screen coordinates unchanged; tests should pass without modification.
- **T086/T087/T088** — PLEDIT scroll tests. The B4 `scrollOffset` clamp (`max(0, min(scrollOffset, max(0, count - PLEDIT_ROW_COUNT)))`) is identical to the `maxOffset` bound already computed in the drag handlers. No existing test exercises a scroll position that the clamp would alter differently. Run T086–T088 unmodified as a regression gate.

### B4 clamp — architect note to VE

The clamp is a guard against out-of-bounds `scrollOffset` on resume; it is **not** a confirmed fix for B4. Root cause remains unconfirmed (intermittent, unknown repro). If B4 recurs after the refactor, do not patch further without a serial-debug repro trace. Escalate to Architect.

### New tests

---

**T_BI_01 — PLEDIT repaint on Spotify resume**

VE challenge: "assert PLEDIT rows drawn within 100ms" has no serial observable — `get snapshot` exposes playback state, not draw timing.

Corrected mechanism: Developer adds `"lastPlaylistDraw"` to `dbgGet`, returning `lastPlaylistDrawMs` (already a `WinampDisplay` member). Test sequence:

```
tap <taskbar_clock>      # switch to Clock
wait 2000                # let spotifyTask tick; seqno may change
get lastPlaylistDraw     # note t_before
tap <taskbar_spotify>    # switch to Spotify (triggers invalidatePlaylist())
poll get lastPlaylistDraw every 50ms, timeout 500ms
assert lastPlaylistDraw > t_before   # drawPlaylist() ran post-resume
```

If `lastPlaylistDraw` advances, the `invalidatePlaylist()` + seqno-change path fired. This is fully observable via serial.

Developer deliverable: expose `lastPlaylistDrawMs` in `dbgGet("lastPlaylistDraw", ...)`.

---

**T_BI_02 — no Winamp render bleed onto Clock canvas**

VE challenge: "`lastTouchResult` doesn't track render calls; `pendingReleaseAt` fires as a timer, not a touch event — unobservable via serial."

VE is correct. The `pendingReleaseAt` deferred paint is a timer-fired SPI write with no observable serial side-effect. **This is intentionally a structural guarantee, not a runtime assertion.**

Under the new interface, `pendingReleaseAt` only fires inside `handleWinampInput()`, which is only called from `SpotifyApp::handleInput()`, which is only called when `currentAppId == Spotify`. The proof is in the layering, not in a runtime check.

Corrected test goal: verify the structural precondition (app switched correctly, event consumed) rather than the render absence (unobservable):

```
tap <PLAY button>               # sets pendingReleaseAt = now + 80ms
# within 80ms:
tap <taskbar_clock>             # shell synthesises Release → switchApp(Clock)
wait 200ms                      # pendingReleaseAt window passes
get appId                       # assert == 1 (Clock)
get lastTouchResult             # assert action == "APP_SWITCH"
```

If `appId == Clock` and `lastTouchResult.action == "APP_SWITCH"`, the shell consumed the taskbar tap and the app switch completed. Whether `pendingReleaseAt` would have fired is moot — `handleWinampInput()` was never called after the switch. The structural proof is sufficient; no pixel assertion needed.

---

**T_BI_03 — suspend() clears drag state mid-gesture**

New test, not present in original spec. Covers layering rule 6.

Sequence:

```
tap <taskbar_spotify>           # ensure Spotify active
drag <PLEDIT start> partial     # begin drag, do NOT release
# while drag is in progress (s_inGesture == true):
tap <taskbar_clock>             # shell: synthesise Release, then switchApp
get appId                       # assert == 1 (Clock)
wait 500ms
tap <taskbar_spotify>           # switch back to Spotify
# assert PLEDIT draws correctly (use T_BI_01 mechanism):
poll get lastPlaylistDraw until advances
get scrollOffset                # assert >= 0 (drag state was reset)
```

`get scrollOffset` requires `scrollOffset` exposed in `dbgGet` — it already is (existing `dbgGet("scrollOffset")`). No new Developer deliverable needed beyond T_BI_01's `lastPlaylistDraw`.

---

**T_BI_04 — Release delivery after finger lift**

VE challenge: existing transport tests cover Press; Release delivery (the timer-fire path for deferred sprite paint) has no explicit test.

Under the new model, `TouchPhase::Release` is delivered when `s_inGesture && !ts.touched()`. The `pendingReleaseAt` paint triggers on Release in `handleWinampInput()`. Observable via `lastTouchResult`:

```
tap <PLAY button>               # Press → pendingReleaseAt set; lastTouchResult.action = "PLAY"
# finger lifts — shell delivers Release on next loop
wait 150ms                      # past the 80ms pendingReleaseAt window
get lastTouchResult             # assert region == "TRANSPORT", action == "PLAY"
# visual: button sprite should be in released state
```

This verifies the Release path ran without asserting pixel content. If the DUT crashes or hangs, Release was not delivered correctly.

### Interface method coverage summary

| Method | Covered by |
|--------|-----------|
| `init()` | T147 first-switch path |
| `resume()` | T_BI_01 (Spotify), T147/T148 (Clock) |
| `suspend()` | T_BI_03 mid-gesture switch |
| `tick()` | All existing tests (runs every loop) |
| `handleInput(Press)` | T076/T081/T082/T086–T088 |
| `handleInput(Move)` | Volume drag tests (T096 series), PLEDIT drag |
| `handleInput(Release)` | T_BI_04 (new) |

Developer deliverables to enable new tests:
1. `dbgGet("lastPlaylistDraw")` → returns `lastPlaylistDrawMs` as integer ms timestamp.
2. `dbgGet("appId")` → already exists (from TASK-087 salvage). Confirm still present post-refactor.
3. `dbgGet("scrollOffset")` → already exists. Confirm still present post-refactor.

VE to own T_BI_01 through T_BI_04 test scripts; Developer to implement the one new dbgGet entry.

---

## Resolved decisions

1. **`checkForInput()` retired.** Serial debug callers (`cmdTap`/`cmdDrag`) call `winampDisplay.handleWinampInput(phase, sx, sy)` directly on the concrete class, bypassing the shell gesture tracker intentionally. `injectTouch()`/`injectRelease()` wrappers on `WinampDisplay` may be retained as thin shims that translate to `handleWinampInput` calls, or deleted if no other caller remains after the refactor.

2. **Shell owns touch read; apps receive `TouchPhase`.** `appHandleInput()` is the sole caller of `ts.touched()`. Shell tracks `s_inGesture`, delivers `Press`/`Move`/`Release` events. Apps do not re-poll `ts`. Drag continuation in `WinampDisplay` is driven by repeated `Move` deliveries on each loop — no change to the drag logic, only to who triggers it.

## Open question

1. **`SpotifyDisplay*` pointer** — `spotifyDisplay` is used by `drawWifiManagerMessage()` and the pre-main-loop setup flow. Once the App ABC lands, should the `SpotifyDisplay` vtable be retired entirely? Deferred; not in scope for this refactor.
