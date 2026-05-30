#pragma once
// appShell.h — app registry, state structs, and dispatch (M-MULTIAPP, TASK-087c).

#include <Arduino.h>
#include "gen/shell_layout.h"
#include "touchPhase.h"

struct App {
    virtual void init()    = 0;
    virtual void resume()  = 0;
    virtual void suspend() = 0;
    virtual void tick()    = 0;
    virtual bool handleInput(TouchPhase phase, int x, int y) = 0;
    virtual ~App() = default;
};

enum class AppId : uint8_t {
    Spotify  = 0,
    Clock    = 1,
    Weather  = 2,
    Crypto   = 3,
    Matrix   = 4,
    Life     = 5,
    Settings = 6,
    Stock    = 7,
    Aquarium = 8,
    COUNT    = 9,
};

extern AppId currentAppId;

// Dispatch — implemented in main.cpp.
void appTick(AppId id);
void appHandleInput(AppId id);
void switchApp(AppId next);

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

enum class StockSubView : uint8_t { List = 0, ChartDetail = 1 };
enum class StockRange   : uint8_t { D1 = 0, D5 = 1, Mo1 = 2, Ytd = 3 };

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
    uint16_t      fetchErrCount;   // cumulative -99 errors since boot; never auto-clears
    uint16_t      fetchOkCount;    // cumulative successful chart fetches since boot; never auto-clears
    uint16_t      quoteOkCount;    // cumulative successful quote fetches since boot; never auto-clears
};

// First-launch tracking — indexed by (int)AppId.
extern bool g_appLaunched[(int)AppId::COUNT];

// Sanity checks (T127/T129): catch compile-time drift between appShell.h and shell_layout.h.
static_assert(TASKBAR_X == 275,                           "TASKBAR_X drift vs appShell");
// AppId::COUNT (9) intentionally exceeds TASKBAR_SLOT_COUNT (6) — taskbar scrolls (M-TASKBAR-SCROLL).

