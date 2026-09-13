#pragma once
// appShell.h — app registry, state structs, and dispatch (M-MULTIAPP, TASK-087c).

#include <Arduino.h>
#include "gen/shell_layout.h"
#include "touchPhase.h"
#include "dataTask.h"

#include "app.h"   // the App interface (M-SRCLAYOUT)

enum class AppId : uint8_t {
#define APP_X(Name, icon, cfg, disp) Name,
#include "appRegistry.h"
#undef APP_X
    COUNT,
};

extern AppId currentAppId;

// Dispatch — implemented in main.cpp.
void appTick(AppId id);
void appHandleInput(AppId id);
void switchApp(AppId next);

// M-PLAYER-STATE / TASK-260: persist the player slot's mode (Spotify=0 | WebRadio=1)
// to settings, immediate-save with an unchanged-value skip (§4). Called from the eject
// toggles in both directions. Implemented in main.cpp. Arg is PlayerMode-as-uint8_t.
void persistPlayerMode(uint8_t mode);

// ── ADR-063 D3/D4 — shell-side identity guard + tick/repaint counters ─────
// (TASK-637, "the shell half" — Arch review M-HARNESS2 §1.2/§2.2). Neither
// needs D1's App::dbgGet virtual nor D2's g_apps[]-only delegation: the
// guard is applied directly at each per-app key's EXISTING delegation call
// site in cmdGet.cpp, so D1/D2 are deferred to whichever later per-app
// commit (TASK-593) actually needs the generalized interface.
//
// NOTE — three of the thirteen apps are deliberately NOT gated by this
// guard: Spotify, WebRadio, LocalPlayer. All three share the taskbar's
// "player slot" and have an established always-reachable contract for at
// least part of their key surface (see localPlayerApp's plCount/plMem/
// plRow/fbState/plOrder/plCursor comment in cmdGet.cpp: "read the app
// instance directly, not currentAppId... same always-reachable contract as
// `get wrStation`" — TASK-415/ADR-059 D12). Gating them requires a
// key-by-key review this shell-half commit does not do; that review is
// per-app work and belongs to TASK-593.
#ifdef SERIAL_DEBUG
// True iff `owner` is the currently active app. A key's handler must call
// this — and dbgRefuseInactive() on false — before answering, for every key
// this guard covers. D3: "a per-app key is refused with a named error when
// its owning app is not the active app," enforced once here rather than as
// thirteen hand-written app-side observables.
bool dbgAppIsActive(AppId owner);

// Prints the standard `{"ok":false,...,"error":"inactiveApp",...}` refusal
// for `cmd` ("get" only, so far — see TASK-637's commit note on `set`) on
// `var`, owned by `owner`, while a different app is active. The error is
// named so a host test can tell "wrong app" apart from "key does not
// exist" (T_APPKEY_01's own requirement). Caller must `return` immediately
// after calling this.
void dbgRefuseInactive(const char* cmd, const char* var, AppId owner);
// Keys that stay answerable while their owner is inactive, because their value
// is not live app state: a persisted setting, or a one-way latch that records
// app history. Named one by one with the reason at the definition (appShell.cpp),
// never by family. Found by the first full DUT run of the guard (2026-09-13),
// which refused three ids that read these cross-app by design.
bool dbgKeyReachableInactive(const char* var);

// D4: shell-owned, per-app progress counters — incremented by the shell
// around its own appTick() dispatch, never by the app itself. A counter the
// app increments in its own tick is a counter the app can be wrong about in
// exactly the way A-8 is trying to catch. Exposed read-only via
// `get appTicks` (cmdGet.cpp).
//
// No repaint counter: the shell has no per-app "did I redraw" signal without
// changing App::tick()'s return contract across thirteen overrides (a sweep D6
// forbids). A key named appRepaints that counted ticks would be a lie, and the
// console is additive-only, so it could never be taken back. It lands when the
// signal exists (TASK-593).
extern uint32_t g_appTicks[(int)AppId::COUNT];
#endif

// --- Per-app state structs (app-lifecycle.md) ---

// WeatherAppState moved into apps/weatherApp.h (M-SRCLAYOUT Stage E / TASK-471).
// CryptoAppState moved into apps/cryptoApp.h (M-SRCLAYOUT Stage E / TASK-471).
// MatrixAppState moved into apps/matrixApp.h (M-SRCLAYOUT Stage E / TASK-471).
// LifeAppState moved into apps/lifeApp.h (M-SRCLAYOUT Stage E / TASK-471).
// StockSubView/StockRange/HeatmapTile/StockAppState moved into apps/stockApp.h
// (M-SRCLAYOUT Stage E / TASK-471).

// First-launch tracking moved into ShellState::launched[] — see
// shell/shellState.h (M-SRCLAYOUT D3 / TASK-456).

// Sanity checks (T127/T129): catch compile-time drift between appShell.h and shell_layout.h.
static_assert(TASKBAR_X == 275,                           "TASKBAR_X drift vs appShell");
// AppId::COUNT (9) intentionally exceeds TASKBAR_SLOT_COUNT (6) — taskbar scrolls (M-TASKBAR-SCROLL).

