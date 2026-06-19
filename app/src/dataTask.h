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
    WebRadioStation stations[100];
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
void enqueueWebRadioStations(const char* countryCode);

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

}  // namespace dataTask
