# M-MULTIAPP — App Lifecycle and State

> Part of: [overview.md](overview.md)

## App enum

```cpp
enum class AppId : uint8_t {
    Spotify  = 0,
    Clock    = 1,
    Weather  = 2,
    Crypto   = 3,
    Matrix   = 4,
    Life     = 5,
    COUNT    = 6,
};
```

Defined in a new header `appShell.h`. `currentAppId` lives as a module-level
variable alongside the app state union.

## State structs

Each app declares a POD state struct. All are kept in RAM simultaneously
(total ~3.8 KB — dominated by the GoL grid). On switch the active app's
state is written back to its slot; the incoming app's state is restored.

```cpp
struct SpotifyAppState {
    // WinampDisplay render cache — enough to repaintChrome() without a poll
    int  lastThumbPx;
    int  lastSeconds;
    char lastTitle[264];
    int  lastVolumeRendered;
    int  lastShuffleRendered;
    int  lastRepeatRendered;
    int  currentStatusUv;
    // scroll state
    int  titleScrollOffset;
    unsigned long titleScrollDeadline;
    // VisMode
    uint8_t visMode;
};

struct ClockAppState {
    // stateless — time is always available via getLocalTime()
};

struct WeatherAppState {
    float cTemp, cHum, cWind;
    unsigned long lastDataFetch;
};

struct CryptoAppState {
    float prices[9];
    float changes[9];
    unsigned long lastCryptoFetch;
};

struct MatrixAppState {
    struct Column {
        int   x;
        float y;       // float per source — fractional scroll position
        float speed;   // float per source — fractional pixels per tick
        int   length;
        char  lastChar;
    } rain[14];
    bool initialised;
};

struct LifeAppState {
    // Grid sized for landscape 275×240 canvas at 5 px/cell: 55 cols × 48 rows
    // (5in1 source used portrait 48×60 at GRID_W=48, GRID_H=60; see layout.md)
    // Col-major [x][y] — matches source convention; see gol.md for rationale.
    uint8_t  grid[55][48];      // 0=dead, 1=alive (binary per source)
    uint16_t hueShift;          // global colour drift, += 3 per generation
    int      lastCellCount;     // live-cell count from previous generation
    int      sameCountTimer;    // gens without liveCount change → stagnation reset
    bool     initialised;
};

union AppStateStore {
    SpotifyAppState  spotify;
    ClockAppState    clock;
    WeatherAppState  weather;
    CryptoAppState   crypto;
    MatrixAppState   matrix;
    LifeAppState     life;
} g_appState[static_cast<int>(AppId::COUNT)];
```

The union-per-slot layout wastes some RAM (each slot sized to the largest
member) but avoids heap allocation and pointer arithmetic.
Largest slot: LifeAppState ~2.9 KB → total ≤ 6 × 2.9 KB ≈ 17.4 KB.

If RAM is tight, replace the union array with individual named structs
(one per app, always allocated). Total named-struct cost: ~3.8 KB. Prefer
named structs — avoids the union footprint multiplier.

## switchApp()

```cpp
void switchApp(AppId next) {
    if (next == currentAppId) return;

    // 1. Save active app's transient state into g_appState[currentAppId]
    saveAppState(currentAppId);

    // 2. Clear the app canvas (left 275 × 240 columns only)
    tft.fillRect(0, 0, 275, 240, TFT_BLACK);

    currentAppId = next;

    // 3. Restore (or init) incoming app state
    bool firstLaunch = !g_appLaunched[static_cast<int>(next)];
    if (firstLaunch) {
        initAppState(next);
        g_appLaunched[static_cast<int>(next)] = true;
    } else {
        restoreAppState(next);
    }

    // 4. Re-render taskbar active indicator
    renderTaskbar();

    // 5. Call the incoming app's full repaint
    repaintApp(next);
}
```

`saveAppState` / `restoreAppState` copy between live WinampDisplay fields
(or app-local variables) and the corresponding `g_appState[]` slot.

## Per-app tick and input dispatch

Main `loop()` gains two dispatch calls:

```cpp
appTick(currentAppId);          // replaces Winamp-specific tick blocks
appHandleInput(currentAppId);   // called instead of spotifyDisplay->checkForInput()
```

`appHandleInput()` first checks the taskbar hit-zone (x ≥ 275); if not a
taskbar tap, delegates to the active app's input handler.

`appTick()` for Spotify calls the existing `vu::tick()`, `winampDisplay.drawPlaylist()`,
`updateCurrentlyPlaying()`, and `updateProgressBar()`. For other apps it calls
their own render/update function.

## Network apps (Weather, Crypto)

Weather and Crypto need periodic HTTP fetches. They share a `dataTask`
FreeRTOS task (same pattern as spotifyTask):

- A request queue (`xQueueCreate`, 4 slots, `struct DataRequest { uint8_t type; }`).
- A result mutex (`portMUX_TYPE`) protecting a `DataResult` struct.
- `dataTask::enqueue(DATA_FETCH_WEATHER)` / `DATA_FETCH_CRYPTO` posted by the
  app tick when cache is stale (> N minutes old).
- `dataTask` fetches, parses JSON, writes result under spinlock.
- App tick reads result under spinlock, updates its `g_appState[]` slot.

`dataTask` is created by a new `dataTask::begin()` call in `setup()`, alongside
`spotifyTask::begin()`. It only runs when Weather or Crypto is active (or when
a cached fetch expires in the background — TBD in dataTask design).

Clock (NTP), Matrix, and GoL require no network task.

## Spotify app specifics

When switching away from Spotify:
- `saveAppState(Spotify)` copies WinampDisplay's render-cache fields into
  `g_appState[0].spotify`.
- `spotifyTask` keeps running in the background — it continues polling Spotify
  and updating the snapshot under the spinlock. The snapshot is stale-proof.

When switching back:
- `restoreAppState(Spotify)` copies saved fields back into WinampDisplay.
- `repaintChrome()` redraws the full Winamp chrome from the restored cache.
- No extra poll needed — the snapshot already contains the latest data.

This is safe because WinampDisplay state and spotifyTask state are already
decoupled via the spinlock-protected snapshot.
