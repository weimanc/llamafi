#pragma once
// dataTask.h — async HTTP fetch task for Weather, Crypto, Stock, and Teletext apps.
// FreeRTOS task queues fetch requests; results written under spinlock.
// Apps call enqueue() when cache is stale; poll*() to consume new data.
// TLS: WiFiClientSecure + hardcoded root CA PEMs per ADR-029 / ADR-044.

#include <Arduino.h>

namespace dataTask {

enum FetchType : uint8_t {
    DATA_FETCH_WEATHER          = 0,
    DATA_FETCH_CRYPTO           = 1,
    DATA_FETCH_STOCK_QUOTE      = 2,
    DATA_FETCH_STOCK_CHART      = 3,
    DATA_FETCH_HEATMAP_QUOTE    = 4,
    DATA_FETCH_STOCK_CHART_BY_SYM = 5,
    DATA_FETCH_TELETEXT_PAGE    = 6,
    DATA_FETCH_WEBRADIO_STATIONS = 7,
};

struct WeatherResult {
    bool  ok    = false;
    float cTemp = 0.0f;
    float cHum  = 0.0f;
    float cWind = 0.0f;
};

struct CryptoResult {
    bool  ok          = false;
    float prices[6]   = {};
    float changes[6]  = {};
};

struct StockQuoteResult {
    bool  ok           = false;
    float prices[8]    = {};
    float changePct[8] = {};
    int   errorCode    = 0;
};

struct StockChartResult {
    bool    ok          = false;
    float   points[110] = {};
    uint8_t len         = 0;
    float   lo          = 0.0f;
    float   hi          = 0.0f;
    int     errorCode   = 0;
};

struct HeatmapQuoteResult {
    bool    ok              = false;
    int     errorCode       = 0;
    uint8_t count           = 0;
    char    symbols[20][8]  = {};
    float   prices[20]      = {};
    float   changePct[20]   = {};
    float   marketCap[20]   = {};
};

// TASK-224: station list cap. limit=30 in the radio-browser.info query is an
// intentional heap mitigation (commit dafa4a4, TLS+Spotify heap coexistence),
// not a bug — this constant drives the query limit, the result array sizes
// (here and in webRadioApp.h's _stations[]), and the fill-loop bound so all
// four stay in agreement.
static constexpr uint8_t WR_MAX_STATIONS = 30;

// TASK-232: the radio-browser list is HTTPS-dominated (~73% for NL), but HTTPS
// audio streams can't be played on this no-PSRAM board — the audio-stream mbedTLS
// handshake hits SSL mem-alloc failure (~40 KB contiguous unavailable). So the
// fetch keeps only http:// streams and pages through the votes-ordered list
// (page size = WR_MAX_STATIONS, which fits the 5 KB s_webRadioDoc) until it has
// WR_MAX_STATIONS playable stations or it has scanned WR_FETCH_MAX_PAGES pages.
// ~27% HTTP means ~4 pages to fill 30; 5 gives margin without unbounded fetching.
static constexpr uint8_t WR_FETCH_MAX_PAGES = 5;

// WebRadioStation / WebRadioStationsResult — written by fetchWebRadioStations(),
// read by WebRadioApp::tick() via pollWebRadioStations().
struct WebRadioStation {
    char     name[48];   // station display name (truncated)
    char     url[104];   // url_resolved (pre-resolved direct stream URL)
    uint16_t bitrate;    // kbps (0 = unknown)
};
struct WebRadioStationsResult {
    bool    ok           = false;
    int     lastHttpCode = 0;
    uint8_t count        = 0;
    char    countryCode[4] = {};
    char    jsonErr[24]  = {};
    bool    tlsInsecure  = false;  // always false since TASK-236 removed the setInsecure()
                                    // fallback (ADR-029 gate at T_WR_TLS_01 proved it never
                                    // fired). Field kept as a quarterly-check observability
                                    // surface (get wrLastHttp) — flips only if pinning ever
                                    // regresses, which it can no longer silently do.
    WebRadioStation stations[WR_MAX_STATIONS];
};

// TeletextState — written by fetchTeletext(), read by TeletextApp::tick() via pollTeletext().
// cells[25][40] stores raw ISO-8859-1 bytes from the <pre> block; decoded by the renderer.
struct TeletextState {
    bool     ready              = false; // true after first successful fetch
    uint16_t page               = 101;  // current page (from metadata or request)
    uint16_t prevPage           = 0;    // pn=p_ (0 if absent)
    uint16_t nextPage           = 0;    // pn=n_ (0 if absent)
    uint16_t subpageNext        = 0;    // pn=ns page (0 if absent)
    uint16_t subpagePrev        = 0;    // pn=ps page (0 if absent)
    uint8_t  subpageNextSub     = 0;    // pn=ns subpage index e.g. "617-2" → 2
    uint8_t  subpagePrevSub     = 0;    // pn=ps subpage index
    uint16_t ftlTargets[4]      = {};   // fast-text link page numbers
    char     ftlLabels[4][12]   = {};   // fast-text row-24 label text (trimmed)
    uint8_t  cells[25][40]      = {};   // raw cell bytes (ISO-8859-1)
    int      lastHttpCode       = 0;    // last http.GET() return value
};

// Spawn the FreeRTOS task. Call once in setup(), after WiFi is connected.
void begin();

// Post a fetch request. Non-blocking (drops if queue full).
void enqueue(FetchType type);

// Post a chart fetch for one ticker/range. Non-blocking (drops if queue full).
void enqueueStockChart(uint8_t tickerIdx, uint8_t rangeIdx);

// Post a heatmap screener fetch. Non-blocking (drops if queue full).
void enqueueHeatmapQuote();

// Post a chart fetch by symbol string (for heatmap drill-through). Non-blocking.
void enqueueStockChartBySym(const char* symbol, uint8_t rangeIdx);

// Post a teletext page fetch. sub=0 for base page, 1-15 for subpage (e.g. 617-2).
// Non-blocking (drops if queue full).
void enqueueTeletextPage(uint16_t page, uint8_t sub = 0);

// Set country code for station list fetch, then enqueue the fetch.
// countryCode: ISO 3166-1 alpha-2, e.g. "NL". Non-blocking.
// bitrateCap: radio-browser bitrateMax kbps filter (0 = no cap). TASK-221 — the
// design prefers ≤ 96 kbps streams for stall tolerance on the small ring buffer.
void enqueueWebRadioStations(const char* countryCode, uint8_t bitrateCap);

// TASK-289: abandon an in-flight (or queued) station fetch — called by
// WebRadioApp::_play() when playback starts while the fetch is still pending.
// Playback's arena/decoder allocations would starve the fetch's TLS handshake
// anyway (-32512); abandoning early skips the doomed attempt and the fetch is
// re-tried on the next resume() with a quiet heap. Non-blocking; sets a flag
// the mirror loop checks before each handshake.
void abortWebRadioFetch();

// Copy latest result into *out; returns true if new data since last poll.
// Caller must supply a valid pointer. Thread-safe (spinlock).
bool pollWeather(WeatherResult *out);
bool pollCrypto(CryptoResult *out);
int  lastCryptoHttpCode();  // last HTTP response code from CoinGecko (0 = never fetched)
bool pollStockQuote(StockQuoteResult *out);
bool pollStockChart(StockChartResult *out);
bool pollHeatmapQuote(HeatmapQuoteResult *out);
bool pollTeletext(TeletextState *out);
int  lastTeletextHttpCode(); // last HTTP response code from teletekst-data.nos.nl

bool pollWebRadioStations(WebRadioStationsResult *out);

void configureStockTickers(const char tickers[8][8]);
void configureCrypto(const char ids[6][16], const char* ccy);

// Live progress indicators — safe to read from any core without locking.
// -1 = idle (function not running), 0..N = step currently in progress.
// stockQuoteProgress: ticker index 0-7 currently being fetched.
// weatherFetchPhase / cryptoFetchPhase / stockChartProgress: 0=TLS, 1=GET, 2=parse.
int8_t stockQuoteProgress();
int8_t weatherFetchPhase();
int8_t cryptoFetchPhase();
int8_t stockChartProgress();

// TASK-299: queue/dispatch observability (get dataq). Discriminates the three
// "station fetch never ran" signatures: request never enqueued (queue full),
// enqueued but never dequeued (dataTask wedged in a prior fetcher), or
// dispatched but parked in spotifyTask::tlsYield().
struct DbgQueueState {
    uint8_t  queueWaiting;   // requests sitting in the queue right now
    uint32_t pendingMask;    // TASK-250 coalescing bits (param-less fetches)
    int8_t   inFlight;       // FetchType currently dispatched, -1 = idle
    uint32_t inFlightMs;     // millis() when the in-flight dispatch started (0 = n/a)
    int8_t   wrPhase;        // WR fetch: -1 idle, 0 in tlsYield, 1 fetching mirrors, 2 done
    uint32_t wrPhaseMs;      // millis() of the last wrPhase transition (0 = never)
    uint32_t wrEnqueues;     // enqueueWebRadioStations() calls accepted since boot
    uint32_t wrDrops;        // enqueueWebRadioStations() calls dropped (queue full)
};
void dbgQueueState(DbgQueueState* out);

// TASK-240: stack instrumentation. stackHighWaterBytes = minimum free stack ever
// seen (the watermark); stackSizeBytes = configured size. used = size - highWater.
size_t stackHighWaterBytes();
size_t stackSizeBytes();

}  // namespace dataTask
