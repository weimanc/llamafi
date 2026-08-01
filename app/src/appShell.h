#pragma once
// appShell.h — app registry, state structs, and dispatch (M-MULTIAPP, TASK-087c).

#include <Arduino.h>
#include "gen/shell_layout.h"
#include "touchPhase.h"
#include "dataTask.h"

struct App {
    virtual void init()    = 0;
    virtual void resume()  = 0;
    virtual void suspend() = 0;
    virtual void tick()    = 0;
    virtual bool handleInput(TouchPhase phase, int x, int y) = 0;
    // Return true while async work initiated by handleInput() is still in flight.
    // Self-clears when the work completes. Shell polls this after every tick().
    // Non-pure: apps with no async input need not override (safe default = false).
    virtual bool hasPendingAsync() const { return false; }
    // TASK-245 / ADR-046: return true while the app is in a sustained error state
    // (an auth/HTTP failure that won't self-heal by retrying — e.g. a Spotify 403).
    // Sticky: the app sets it on detection and clears it on the next success; the
    // shell does no latching, it only reads this to colour the taskbar active-slot
    // indicator red (precedence error > busy/connecting > idle). Safe default =
    // false, so offline apps need not override.
    virtual bool hasError() const { return false; }
    // TASK-245 amendment / ADR-046: return true while the app is establishing its
    // data connection and has no result yet (e.g. before the first Spotify poll
    // resolves). Renders the active-slot indicator amber (working) — so the bar
    // reads amber at boot rather than green (false "all-good") until we know the
    // state. Amber here collapses with the busy state; error (red) still wins.
    // Safe default = false.
    virtual bool isConnecting() const { return false; }
    // TASK-384: return true when (x, y) is a pure-navigation tap for the app's
    // CURRENT state — one that changes what's on screen without starting any
    // new async work (e.g. Stock's chart/heatmap "back" zone, Teletext's
    // STRIP_BACK). The shell's g_shellBusy pre-dispatch gate normally drops
    // every tap while the app's own hasPendingAsync() is true, to stop a tap
    // from stacking a redundant fetch on top of one already in flight — but
    // that gate has no way to tell "will start a new fetch" apart from "just
    // navigates", so it silently swallowed navigation taps too (confirmed on
    // real hardware, not just the serial test harness — see TASK-384). This
    // lets an app explicitly except specific screen regions, mirroring how
    // the taskbar tap already bypasses the busy gate entirely for the same
    // reason (switching away is always safe). Safe default = false — apps
    // with no async work, or no in-app navigation-while-pending case, need
    // not override.
    virtual bool isNavigationTap(int x, int y) const { (void)x; (void)y; return false; }
    virtual ~App() = default;
};

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

struct SpotifyAppState {
    int           lastThumbPx;
    int           lastSeconds;
    char          lastTitle[264];
    int           lastVolumeRendered;
    int           lastShuffleRendered;
    int           lastRepeatRendered;
    int           currentStatusUv;
    int           titleScrollOffset;
    unsigned long titleScrollDeadline;
    uint8_t       visMode;
};

struct ClockAppState   { bool initialised; };

struct WeatherAppState {
    float         cTemp, cHum, cWind;
    unsigned long lastDataFetch;
};

struct CryptoAppState {
    float         prices[6];
    float         changes[6];
    unsigned long lastCryptoFetch;
};

struct MatrixAppState {
    struct Column {
        int   x;
        float y;
        float speed;
        int   length;
        char  lastChar;
    } rain[14];
    bool initialised;
};

struct LifeAppState {
    uint8_t  grid[55][48];
    uint16_t hueShift;
    int      lastCellCount;
    int      sameCountTimer;
    bool     initialised;
};

struct AquariumAppState {
    bool initialised;
};

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

// First-launch tracking — indexed by (int)AppId.
extern bool g_appLaunched[(int)AppId::COUNT];

// Sanity checks (T127/T129): catch compile-time drift between appShell.h and shell_layout.h.
static_assert(TASKBAR_X == 275,                           "TASKBAR_X drift vs appShell");
// AppId::COUNT (9) intentionally exceeds TASKBAR_SLOT_COUNT (6) — taskbar scrolls (M-TASKBAR-SCROLL).

