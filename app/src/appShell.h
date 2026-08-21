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

enum class StockSubView : uint8_t { List = 0, ChartDetail = 1, HeatmapDetail = 2 };
enum class StockRange   : uint8_t { D1 = 0, D5 = 1, Mo1 = 2, Ytd = 3 };

struct HeatmapTile { int16_t x, y, w, h; uint8_t tickerIdx; };

struct StockAppState {
    char          tickers[8][8];
    StockSubView  subView;
    float         prices[8];
    float         changePct[8];
    unsigned long lastQuoteFetch;
    uint8_t       chartTickerIdx;
    StockRange    chartRange;
    float         chartPoints[110];
    uint8_t       chartLen;
    float         chartLo, chartHi;
    unsigned long lastChartFetch;
    bool          fetchFailed;
    int           fetchErrorCode;
    uint16_t      fetchErrCount;   // cumulative JSON parse errors since boot (-91..-95); never auto-clears
    uint16_t      fetchOkCount;    // cumulative successful chart fetches since boot; never auto-clears
    uint16_t      quoteOkCount;    // cumulative successful quote fetches since boot; never auto-clears
    StockSubView  prevSubView;
    unsigned long lastHeatmapFetch;
    dataTask::HeatmapQuoteResult heatmapData;
    HeatmapTile   heatmapLayout[20];
    bool          heatmapLayoutDirty;
    char          chartSymbol[8];  // symbol for heatmap drill-through chart
};

// First-launch tracking moved into ShellState::launched[] — see
// shell/shellState.h (M-SRCLAYOUT D3 / TASK-456).

// Sanity checks (T127/T129): catch compile-time drift between appShell.h and shell_layout.h.
static_assert(TASKBAR_X == 275,                           "TASKBAR_X drift vs appShell");
// AppId::COUNT (9) intentionally exceeds TASKBAR_SLOT_COUNT (6) — taskbar scrolls (M-TASKBAR-SCROLL).

