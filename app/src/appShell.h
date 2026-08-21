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

