// dataTaskStorage.cpp — FreeRTOS task body + HTTP fetch for Weather / Crypto.
// Implements the dataTask namespace declared in dataTask.h.
// Pattern mirrors spotifyTask: queue + spinlock-protected result structs.
// TLS: per ADR-029 each fetch stack-allocates a WiFiClientSecure, calls
// setCACert(), then passes it to http.begin(client, url). No persistent
// TLS connection; 60 s cadence makes setup overhead negligible.

#include "dataTask.h"
#include "dataTaskCerts.h"
#include "spotifyTask.h"
#include "logSink.h"

#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <esp_heap_caps.h>
#include <climits>
#include <cmath>
#include <initializer_list>
#include "gen/mem_layout.h"

namespace dataTask {

// Logs free heap and largest contiguous block before/after each TLS session.
// Largest block (maxBlk) is the operative metric: a new TLS handshake needs
// ~50–70 k contiguous; if maxBlk < 50 k the fetch will return -1 (SSL OOM).
#define LOG_HEAP(tag) \
    LOG_D(tag, "heap free=%uk maxBlk=%uk", \
          (unsigned)(heap_caps_get_free_size(MALLOC_CAP_8BIT)         / 1024), \
          (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)/ 1024))

// --- internal types ----------------------------------------------------------

struct Request { uint8_t type; uint8_t param0; uint8_t param1; char symbol[8]; };

// M-MEMPLAN §8: allocator that backs a BasicJsonDocument with a static overlay
// region from mem_layout.h. allocate() returns the pre-assigned buffer once;
// deallocate()/reallocate() are no-ops / in-place — the region is never freed.
struct StaticRegionAllocator {
    void* buf;
    size_t cap;
    void* allocate(size_t n) {
        if (n <= cap) return buf;
        LOG_E("memplan", "overlay alloc overflow: need %u cap %u", (unsigned)n, (unsigned)cap);
        return nullptr;
    }
    void deallocate(void*) {}
    void* reallocate(void* p, size_t n) {
        if (n <= cap) return p;
        LOG_E("memplan", "overlay realloc overflow: need %u cap %u", (unsigned)n, (unsigned)cap);
        return nullptr;
    }
};

// --- module state ------------------------------------------------------------

static QueueHandle_t s_queue       = nullptr;
static TaskHandle_t  s_taskHandle  = nullptr;
static volatile uint32_t s_pendingMask = 0;   // TASK-250: in-flight/queued fetch-type bits

// TASK-299: dispatch observability — written only by dataTask (dispatch loop /
// fetchWebRadioStations) except the wrEnqueues/wrDrops counters (caller task);
// all read lock-free from cmdGet (single-word volatiles, staleness acceptable).
static volatile int8_t   s_dbgInFlight   = -1;
static volatile uint32_t s_dbgInFlightMs = 0;
static volatile int8_t   s_dbgWrPhase    = -1;
static volatile uint32_t s_dbgWrPhaseMs  = 0;
static volatile uint32_t s_dbgWrEnqueues = 0;
static volatile uint32_t s_dbgWrDrops    = 0;

static portMUX_TYPE  s_weatherMux  = portMUX_INITIALIZER_UNLOCKED;
static WeatherResult s_weatherResult;
static bool          s_weatherNew  = false;

static portMUX_TYPE  s_cryptoMux       = portMUX_INITIALIZER_UNLOCKED;
static CryptoResult  s_cryptoResult;
static bool          s_cryptoNew        = false;
static int           s_cryptoLastCode   = 0;

static portMUX_TYPE    s_stockQuoteMux    = portMUX_INITIALIZER_UNLOCKED;
static StockQuoteResult s_stockQuoteResult;
static bool             s_stockQuoteNew   = false;

static portMUX_TYPE    s_stockChartMux    = portMUX_INITIALIZER_UNLOCKED;
static StockChartResult s_stockChartResult;
static bool             s_stockChartNew   = false;

// Progress indicators — written by Core 0 (dataTask), read by Core 1 (serial handler).
// volatile int8_t is a single byte; byte writes on Xtensa LX6 are atomic, no lock needed.
// -1=idle, 0..N-1=phase/step currently in progress.
static volatile int8_t s_stockQuoteProgress = -1;  // ticker index 0-7 in flight
static volatile int8_t s_weatherFetchPhase  = -1;  // 0=TLS, 1=GET, 2=parse
static volatile int8_t s_cryptoFetchPhase   = -1;  // 0=TLS, 1=GET, 2=parse
static volatile int8_t s_stockChartProgress = -1;  // 0=TLS, 1=GET, 2=parse

static portMUX_TYPE       s_heatmapMux    = portMUX_INITIALIZER_UNLOCKED;
static HeatmapQuoteResult s_heatmapResult;
static bool               s_heatmapNew    = false;

// TASK-240 (2026-06-24): trimmed 20→14 KB after measuring high-water across ALL
// fetchers on DUT (Architect ruling, ADR-045 amendment). Worst case is the
// WebRadio multi-page fetch at 8984 B used (weather/crypto/stock peak ~6000 B);
// 14 KB leaves a 5.4 KB / 60% margin and still sits above the historical 12 KB
// overflow point (old non-streaming code, the reason for the original 12→20 bump).
// Reclaims 6 KB of resident heap. Watermark queryable via `get stacks`.
#ifdef WEBRADIO_ONLY
// TASK-255 Lane A: WebRadio is the only fetcher (others compiled out), high-water
// 8.9 KB (TASK-240) → trim to 11 KB; frees ~3 KB heap toward the no-PSRAM decoder.
constexpr UBaseType_t kStackBytes  = 11 * 1024;
#else
constexpr UBaseType_t kStackBytes  = 14 * 1024;
#endif
constexpr UBaseType_t kPriority    = 1;
constexpr BaseType_t  kPinnedCpu   = APP_CPU_NUM;

// WIRE2-G4: weather coords travel with the enqueue (enqueuePlaneRadar snapshot
// pattern) — URL built task-side at fetch time from the last snapshot. The
// timezone param is dropped: the parser only reads current.temperature/
// humidity/wind, none of which are timezone-shaped (design §4-G4; if a daily
// forecast is ever added, use timezone=auto). 0,0 until the first
// enqueueWeather() — the generic enqueue(DATA_FETCH_WEATHER) path fetches
// with whatever was last snapshotted.
static const char WEATHER_URL_FMT[] =
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=%.4f&longitude=%.4f"
    "&current=temperature_2m,relative_humidity_2m,wind_speed_10m";
static float        s_pendingWxLat = 0.0f;
static float        s_pendingWxLon = 0.0f;
static portMUX_TYPE s_pendingWxMux = portMUX_INITIALIZER_UNLOCKED;

static char        s_cryptoIds[6][16] = {
    "bitcoin","ethereum","binancecoin","solana","ripple","cardano"
};
static char        s_cryptoCcy[4]     = "usd";
static portMUX_TYPE s_cryptoConfigMux = portMUX_INITIALIZER_UNLOCKED;

static char        s_stockTickers[8][8]  = {"AAPL","AMD","AMZN","ARM","GOOG","META","MSFT","NVDA"};
static portMUX_TYPE s_stockTickersMux    = portMUX_INITIALIZER_UNLOCKED;
static const char* STOCK_RANGE_STR[4]    = {"1d","5d","1mo","ytd"};
static const char* STOCK_INTERVAL_STR[4] = {"5m","60m","1d","1wk"};
static const char  STOCK_URL_BASE[]      = "https://query1.finance.yahoo.com/v8/finance/chart/";
// TASK-249: multi-symbol spark endpoint — one request returns price+prevClose for
// all tickers (replaces the 8 sequential per-ticker chart GETs). Response is keyed
// by symbol: { "AAPL": {chartPreviousClose, close:[...]}, ... }.
static const char  STOCK_SPARK_URL[]     = "https://query1.finance.yahoo.com/v8/finance/spark?symbols=";

static const char  HEATMAP_URL[] =
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    "?scrIds=ms_technology&count=20&formatted=false";

// --- fetch functions ---------------------------------------------------------

// TASK-223: shared TLS+HTTP open-and-GET boilerplate. Pins the root CA (or
// falls back to setInsecure() when insecure=true), forces HTTP/1.0 so
// http.end() actually frees the TLS session, opens the connection, and issues
// the GET. Returns OPENHTTPS_BEGIN_FAILED if http.begin() fails, else the
// GET() result code (NB: HTTPClient's own HTTPC_ERROR_* codes are small
// negatives, -1..-11, so a plain -1 sentinel here would be indistinguishable
// from a real HTTPC_ERROR_CONNECTION_REFUSED from GET() after a *successful*
// begin() — callers need to tell those apart to decide whether http.end() is
// needed (begin failed → nothing to end; GET failed post-begin → must end()).
// INT_MIN can't collide with any HTTPClient return value.
static constexpr int OPENHTTPS_BEGIN_FAILED = INT_MIN;

// TASK-318 (M-CERT-ERRCODE): pinned-CA verify failure surfaced as its own
// errorCode. HTTPClient collapses a failed TLS handshake into a generic
// -1 HTTPC_ERROR_CONNECTION_REFUSED; the underlying mbedTLS code survives in
// WiFiClientSecure::_lastError. -0x2700 (X509_CERT_VERIFY_FAILED, -9984) is
// the one code that means "the pinned root no longer builds the chain" —
// substitute -120 so pin rot names itself on the app error row / `get dataq`
// / heartbeat instead of masquerading as a dead host. Checked only when
// GET() already failed AND the stored error is exactly -0x2700 (a stale or
// different code falls through to the raw HTTPClient code as before).
// Reserved band -120..-129: TLS-layer sentinels (see dataTask.h).
static constexpr int CERT_VERIFY_FAILED = -120;

// TASK-341: shared substitution, factored out of openHttps() so the fetchers
// that hand-roll begin()/GET() instead of going through it (their divergence
// is deliberate — extra headers/streaming-filter parse between begin() and
// GET() that openHttps()'s atomic begin+GET can't accommodate) get the same
// -120 surfacing with a two-line call, not a copy-pasted check. Checked only
// when GET() already failed; a stale-but-different lastError() code falls
// through to the raw HTTPClient code unchanged.
static int certSentinel(WiFiClientSecure& tls, int code) {
    if (code < 0) {
        char ebuf[8];   // text unused; lastError() is the int accessor
        if (tls.lastError(ebuf, sizeof(ebuf)) == -0x2700)
            return CERT_VERIFY_FAILED;
    }
    return code;
}

// TASK-344 (M-CERT-ERRCODE): SERIAL_DEBUG test hook state for `set certbreak
// <app>` — one-shot, cross-task like s_prForceParseFailCount above. -1 = no
// break armed; otherwise the FetchType value whose next fetch should use the
// wrong root.
static portMUX_TYPE s_certBreakMux    = portMUX_INITIALIZER_UNLOCKED;
static int          s_certBreakTarget = -1;

// If `type` is currently armed, consumes the arm (clears it) and returns
// true — the "next fetch" contract is genuinely one-shot regardless of
// whether the caller goes on to actually use the wrong root (it always
// does, but the consume happens here so a fetcher that bails out early for
// an unrelated reason, e.g. queue coalescing, doesn't leave a stale arm).
static bool consumeCertBreak(FetchType type) {
    bool hit = false;
    portENTER_CRITICAL_SAFE(&s_certBreakMux);
    if (s_certBreakTarget == (int)type) { s_certBreakTarget = -1; hit = true; }
    portEXIT_CRITICAL_SAFE(&s_certBreakMux);
    return hit;
}

// Picks an already-pinned root that is guaranteed to be the WRONG one for
// `type` — reuses existing dataTaskCerts.h constants (no new fixture PEM to
// author/maintain/expiry-track) rather than embedding a dedicated dummy
// cert. The four distinct roots actually in use are: ISRG Root X1
// (weather/crypto/webradio/geocode via OPEN_METEO_ROOT_CA and its aliases),
// DigiCert Global Root G2 (the four yahoo/stock fetchers), USERTrust RSA CA
// (teletext), and GTS Root R4 (planeradar, PLANERADAR_ROOT_CA). Yahoo/stock
// gets PLANERADAR_ROOT_CA (GTS R4, never DigiCert); everything else gets
// YAHOO_FINANCE_ROOT_CA (DigiCert G2, never ISRG/USERTrust/GTS) — covers
// all 10 FetchType values with a guaranteed cross-CA mismatch.
static const char* wrongCaFor(FetchType type) {
    switch (type) {
        case DATA_FETCH_STOCK_QUOTE:
        case DATA_FETCH_STOCK_CHART:
        case DATA_FETCH_HEATMAP_QUOTE:
        case DATA_FETCH_STOCK_CHART_BY_SYM:
            return PLANERADAR_ROOT_CA;
        default:
            return YAHOO_FINANCE_ROOT_CA;
    }
}

static int openHttps(WiFiClientSecure& tls, HTTPClient& http, const char* url,
                      const char* rootCA, bool insecure) {
    if (insecure) tls.setInsecure();
    else          tls.setCACert(rootCA);
    http.useHTTP10(true);   // force Connection:close so http.end() frees TLS
    if (!http.begin(tls, url)) return OPENHTTPS_BEGIN_FAILED;
    int code = http.GET();
    return insecure ? code : certSentinel(tls, code);   // begin() succeeded — caller still http.end()s
}

static void fetchWeather() {
    s_weatherFetchPhase = 0;  // TLS + http.begin
    // WIRE2-G4: read back the coords snapshotted by enqueueWeather() under the
    // same mux (matches fetchPlaneRadar's read of its pending slot).
    float lat, lon;
    portENTER_CRITICAL_SAFE(&s_pendingWxMux);
    lat = s_pendingWxLat;
    lon = s_pendingWxLon;
    portEXIT_CRITICAL_SAFE(&s_pendingWxMux);
    char url[160];
    snprintf(url, sizeof(url), WEATHER_URL_FMT, lat, lon);
    // Log the complete query so a host curl can replicate this request exactly
    // (WebRadio full-URL precedent — VE hooks on it).
    LOG_D("dataTask.weather", "url=%s", url);
    // BP-031: yield Spotify's TLS before our own handshake — contention is about
    // concurrent open sessions, not response size (LL-071/T272). Matches crypto
    // below. Was previously omitted here despite BP-031 citing weather as
    // conforming — fixed 2026-06-21 (TASK-222).
    spotifyTask::tlsYield();
    LOG_HEAP("dataTask.weather");
    WiFiClientSecure tls;
    tls.setCACert(consumeCertBreak(DATA_FETCH_WEATHER)
                      ? wrongCaFor(DATA_FETCH_WEATHER) : OPEN_METEO_ROOT_CA);  // TASK-344
    HTTPClient http;
    http.useHTTP10(true);   // force Connection:close so http.end() frees TLS
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.weather", "http.begin failed");
        s_weatherFetchPhase = -1;
        spotifyTask::tlsResume();  // BP-031: every exit path
        return;
    }
    s_weatherFetchPhase = 1;  // GET in flight
    unsigned long t0 = millis();
    int code = certSentinel(tls, http.GET());  // TASK-341
    LOG_D("dataTask.weather", "GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    String body;
    if (code == 200) body = http.getString();
    else             LOG_W("dataTask.weather", "http %d", code);
    http.end();             // TLS freed here (HTTP/1.0 close)
    LOG_HEAP("dataTask.weather");
    if (code == 200) {
        s_weatherFetchPhase = 2;  // JSON parse
        // M-MEMPLAN §8 (TASK-326): backed by MEM_weather_doc (same overlay region).
        BasicJsonDocument<StaticRegionAllocator> doc(
            1024, StaticRegionAllocator{MEM_weather_doc, 1024u});
        DeserializationError err = deserializeJson(doc, body);
        if (!err) {
            WeatherResult r;
            r.ok    = true;
            r.cTemp = doc["current"]["temperature_2m"].as<float>();
            r.cHum  = doc["current"]["relative_humidity_2m"].as<float>();
            r.cWind = doc["current"]["wind_speed_10m"].as<float>();
            portENTER_CRITICAL_SAFE(&s_weatherMux);
            s_weatherResult = r;
            s_weatherNew    = true;
            portEXIT_CRITICAL_SAFE(&s_weatherMux);
            LOG_D("dataTask.weather", "ok temp=%.1f hum=%.0f wind=%.1f",
                  r.cTemp, r.cHum, r.cWind);
        } else {
            LOG_W("dataTask.weather", "JSON parse error: %s", err.c_str());
        }
    }
    s_weatherFetchPhase = -1;
    spotifyTask::tlsResume();  // BP-031: release Spotify task to reconnect
}

static void fetchCrypto() {
    // CoinGecko TLS takes ~4-5s; Spotify polls every 5s and can fire mid-connect,
    // fragmenting the heap enough that DynamicJsonDocument(2048) hits NoMemory.
    // Pause Spotify TLS first (same mechanism as heatmap) to give the alloc clean
    // contiguous heap. HTTP/1.0 ensures http.end() frees TLS before JSON parse.
    spotifyTask::tlsYield();

    char ids[6][16];
    char ccy[4];
    portENTER_CRITICAL_SAFE(&s_cryptoConfigMux);
    memcpy(ids, s_cryptoIds, sizeof(ids));
    strlcpy(ccy, s_cryptoCcy, sizeof(ccy));
    portEXIT_CRITICAL_SAFE(&s_cryptoConfigMux);
    for (char* p = ccy; *p; p++) *p = tolower((unsigned char)*p);

    String cryptoUrl = "https://api.coingecko.com/api/v3/simple/price?ids=";
    for (int i = 0; i < 6; i++) {
        if (i > 0) cryptoUrl += ',';
        cryptoUrl += ids[i];
    }
    cryptoUrl += "&vs_currencies=";
    cryptoUrl += ccy;
    cryptoUrl += "&include_24hr_change=true";

    s_cryptoFetchPhase = 0;  // TLS + http.begin
    LOG_HEAP("dataTask.crypto");
    WiFiClientSecure tls;
    tls.setCACert(consumeCertBreak(DATA_FETCH_CRYPTO)
                      ? wrongCaFor(DATA_FETCH_CRYPTO) : COINGECKO_ROOT_CA);  // TASK-344
    HTTPClient http;
    http.useHTTP10(true);   // force Connection:close so http.end() frees TLS
    if (!http.begin(tls, cryptoUrl)) {
        LOG_W("dataTask.crypto", "http.begin failed");
        s_cryptoFetchPhase = -1;
        spotifyTask::tlsResume();
        return;
    }
    s_cryptoFetchPhase = 1;  // GET in flight
    unsigned long t0 = millis();
    int code = certSentinel(tls, http.GET());  // TASK-341
    s_cryptoLastCode = code;
    LOG_D("dataTask.crypto", "GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    String body;
    if (code == 200) body = http.getString();
    else             LOG_W("dataTask.crypto", "http %d", code);
    http.end();             // TLS freed here (HTTP/1.0 close)
    spotifyTask::tlsResume();
    LOG_HEAP("dataTask.crypto");
    if (code == 200) {
        s_cryptoFetchPhase = 2;  // JSON parse
        // M-MEMPLAN §8 (TASK-269): backed by MEM_crypto_doc (same overlay region).
        BasicJsonDocument<StaticRegionAllocator> doc(
            2048, StaticRegionAllocator{MEM_crypto_doc, 2048u});
        DeserializationError err = deserializeJson(doc, body);
        if (!err) {
            CryptoResult r;
            r.ok = true;
            for (int i = 0; i < 6; i++) {
                char changeKey[24];
                snprintf(changeKey, sizeof(changeKey), "%s_24h_change", ccy);
                r.prices[i]  = doc[ids[i]][ccy].as<float>();
                r.changes[i] = doc[ids[i]][changeKey].as<float>();
            }
            portENTER_CRITICAL_SAFE(&s_cryptoMux);
            s_cryptoResult = r;
            s_cryptoNew    = true;
            portEXIT_CRITICAL_SAFE(&s_cryptoMux);
            LOG_D("dataTask.crypto", "ok %s=%.2f %s=%.2f ids=%s ccy=%s",
                  ids[0], r.prices[0], ids[1], r.prices[1], ids[0], ccy);
        } else {
            LOG_W("dataTask.crypto", "JSON parse error: %s", err.c_str());
        }
    }
    s_cryptoFetchPhase = -1;
}

static void fetchStockQuote() {
    spotifyTask::tlsYield();      // free Spotify TLS before the Yahoo handshake
    LOG_HEAP("dataTask.stock");
    char tickers[8][8];
    portENTER_CRITICAL_SAFE(&s_stockTickersMux);
    memcpy(tickers, s_stockTickers, sizeof(tickers));
    portEXIT_CRITICAL_SAFE(&s_stockTickersMux);

    // TASK-249: ONE multi-symbol spark request replaces the old 8 sequential
    // per-ticker chart GETs — 8 TLS handshakes (~16 s) → 1 (~2 s). Validated on
    // host (test_yahoo_finance_api.py T_SF_08). Response is keyed by symbol:
    //   { "AAPL": {chartPreviousClose, close:[...]}, ... }
    // price = last non-null close; changePct from chartPreviousClose.
    String syms;
    for (int i = 0; i < 8; i++)
        if (tickers[i][0]) { if (syms.length()) syms += ','; syms += tickers[i]; }

    StockQuoteResult r;
    s_stockQuoteProgress = 0;
    if (syms.length() == 0) {
        r.ok = true;                 // nothing configured — succeed empty
    } else {
        String url = String(STOCK_SPARK_URL) + syms + "&interval=1d&range=1d";
        WiFiClientSecure tls;
        tls.setCACert(consumeCertBreak(DATA_FETCH_STOCK_QUOTE)
                          ? wrongCaFor(DATA_FETCH_STOCK_QUOTE) : YAHOO_FINANCE_ROOT_CA);  // TASK-344
        HTTPClient http;
        if (!http.begin(tls, url)) {
            LOG_W("dataTask.stock", "spark http.begin failed");
            r.ok = false; r.errorCode = -100;
        } else {
            http.addHeader("User-Agent", "Mozilla/5.0");
            http.useHTTP10(true);    // identity encoding so getStream() yields clean JSON
            unsigned long t0 = millis();
            int code = certSentinel(tls, http.GET());  // TASK-341
            LOG_D("dataTask.stock", "spark GET %d elapsed=%lums",
                  code, (unsigned long)(millis() - t0));
            if (code != 200) {
                r.ok = false; r.errorCode = code;
                http.end();
            } else {
                // Wildcard filter: keep {chartPreviousClose, close} for every symbol key.
                // Filtered payload ~614 B for 8 symbols; <1536> doc gives headroom.
                StaticJsonDocument<96> filter;
                filter["*"]["chartPreviousClose"] = true;
                filter["*"]["close"]              = true;
                StaticJsonDocument<1536> doc;
                DeserializationError err = deserializeJson(doc, http.getStream(),
                                               DeserializationOption::Filter(filter));
                http.end();
                if (err) {
                    LOG_W("dataTask.stock", "spark JSON err: %s", err.c_str());
                    r.ok = false; r.errorCode = -90 - (int)err.code();
                } else {
                    r.ok = true;
                    for (int i = 0; i < 8; i++) {
                        if (!tickers[i][0]) { r.prices[i] = 0; r.changePct[i] = 0; continue; }
                        JsonVariantConst e = doc[tickers[i]];
                        float prev  = e["chartPreviousClose"] | 0.0f;
                        float price = 0.0f;
                        for (JsonVariantConst v : e["close"].as<JsonArrayConst>())
                            if (!v.isNull()) price = v.as<float>();   // last non-null = current
                        r.prices[i]    = price;
                        r.changePct[i] = (prev != 0.0f) ? (price - prev) / prev * 100.0f : 0.0f;
                    }
                }
            }
        }
    }
    s_stockQuoteProgress = -1;  // idle
    portENTER_CRITICAL_SAFE(&s_stockQuoteMux);
    s_stockQuoteResult = r;
    s_stockQuoteNew    = true;
    portEXIT_CRITICAL_SAFE(&s_stockQuoteMux);
    if (r.ok) LOG_D("dataTask.stock", "spark ok aapl=%.2f msft=%.2f", r.prices[0], r.prices[1]);
    LOG_HEAP("dataTask.stock");
    spotifyTask::tlsResume();
}

static void fetchStockChart(uint8_t tickerIdx, uint8_t rangeIdx) {
    if (tickerIdx >= 8 || rangeIdx >= 4) return;
    char tickers[8][8];
    portENTER_CRITICAL_SAFE(&s_stockTickersMux);
    memcpy(tickers, s_stockTickers, sizeof(tickers));
    portEXIT_CRITICAL_SAFE(&s_stockTickersMux);
    spotifyTask::tlsYield();
    String url = String(STOCK_URL_BASE) + tickers[tickerIdx]
                 + "?interval=" + STOCK_INTERVAL_STR[rangeIdx]
                 + "&range="    + STOCK_RANGE_STR[rangeIdx];
    LOG_D("dataTask.stock", "chart START %s range=%s heap free=%uk maxBlk=%uk",
          tickers[tickerIdx], STOCK_RANGE_STR[rangeIdx],
          (unsigned)(heap_caps_get_free_size(MALLOC_CAP_8BIT)          / 1024),
          (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT) / 1024));
    StockChartResult r;
    strlcpy(r.symbol, tickers[tickerIdx], sizeof(r.symbol));
    r.rangeIdx = rangeIdx;
    s_stockChartProgress = 0;  // TLS + http.begin
    WiFiClientSecure tls;
    tls.setCACert(consumeCertBreak(DATA_FETCH_STOCK_CHART)
                      ? wrongCaFor(DATA_FETCH_STOCK_CHART) : YAHOO_FINANCE_ROOT_CA);  // TASK-344
    HTTPClient http;
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.stock", "chart http.begin failed");
        r.ok = false; r.errorCode = -100;
    } else {
        http.addHeader("User-Agent", "Mozilla/5.0");
        http.useHTTP10(true);
        s_stockChartProgress = 1;  // GET in flight
        unsigned long t0 = millis();
        int code = certSentinel(tls, http.GET());  // TASK-341
        LOG_D("dataTask.stock", "chart GET %s range=%s %d elapsed=%lums",
              tickers[tickerIdx], STOCK_RANGE_STR[rangeIdx],
              code, (unsigned long)(millis() - t0));
        if (code != 200) {
            r.ok = false; r.errorCode = code;
            http.end();
        } else {
            LOG_D("dataTask.stock", "chart pre-json heap free=%uk maxBlk=%uk",
                  (unsigned)(heap_caps_get_free_size(MALLOC_CAP_8BIT)          / 1024),
                  (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT) / 1024));
            // Filter: extract only close[] — D1 response is ~8 KB (78×5m candles);
            // full parse needs >16384 B pool and cascades a dirty TCP RST into
            // the Spotify keep-alive connection. Filter reduces pool to <2 KB.
            // Tree: chart→result[0]→indicators→quote[0]→close, 5 levels × 1 leaf, ~56B min.
            // HOST TEST: test_yahoo_finance_api.py T_SF_06 CHART_MAX_POINTS=110.
            s_stockChartProgress = 2;  // JSON parse (streaming)
            StaticJsonDocument<128> filter;
            filter["chart"]["result"][0]["indicators"]["quote"][0]["close"] = true;
            StaticJsonDocument<2048> doc;
            DeserializationError err = deserializeJson(doc, http.getStream(),
                                           DeserializationOption::Filter(filter));
            http.end();
            LOG_D("dataTask.stock", "chart post-json heap free=%uk maxBlk=%uk err=%s",
                  (unsigned)(heap_caps_get_free_size(MALLOC_CAP_8BIT)          / 1024),
                  (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT) / 1024),
                  err.c_str());
            if (err) {
                LOG_W("dataTask.stock", "chart JSON err: %s", err.c_str());
                r.ok = false; r.errorCode = -90 - (int)err.code();
            } else {
                JsonArray closeArr =
                    doc["chart"]["result"][0]["indicators"]["quote"][0]["close"].as<JsonArray>();
                r.len = 0;
                r.lo  = 1e30f;
                r.hi  = -1e30f;
                for (JsonVariant v : closeArr) {
                    if (v.isNull()) continue;
                    float val = v.as<float>();
                    r.points[r.len++] = val;
                    if (val < r.lo) r.lo = val;
                    if (val > r.hi) r.hi = val;
                    if (r.len >= 110) break;
                }
                if (r.lo > r.hi) { r.lo = 0.0f; r.hi = 1.0f; }
                r.ok = true;
                LOG_D("dataTask.stock", "chart ok len=%u lo=%.2f hi=%.2f", r.len, r.lo, r.hi);
            }
        }
    }
    s_stockChartProgress = -1;  // idle
    portENTER_CRITICAL_SAFE(&s_stockChartMux);
    s_stockChartResult = r;
    s_stockChartNew    = true;
    portEXIT_CRITICAL_SAFE(&s_stockChartMux);
    spotifyTask::tlsResume();
}

// Pre-allocated at startup (unfragmented heap) and reused per fetch cycle to avoid
// malloc failure after long-uptime TLS cycling (PROP-004 / EXP-003).
// Capacity: 20 symbols × ~120 B each ≈ 2.4 kB peak usage; 2560 gives headroom.
static portMUX_TYPE   s_teletextMux    = portMUX_INITIALIZER_UNLOCKED;
static TeletextState  s_teletextState;
static bool           s_teletextNew    = false;

static const char TELETEXT_URL_BASE[] = "https://teletekst-data.nos.nl/page/";

// Parse a 3-digit page ref string (e.g. "101", "617-2") into page number. Returns 0 on fail.
static uint16_t parsePage(const char* s) {
    if (!s || !s[0]) return 0;
    int v = atoi(s);
    return (v >= 100 && v <= 899) ? (uint16_t)v : 0;
}

// Parse subpage index from "617-2" → 2. Returns 0 if no dash suffix.
static uint8_t parseSubpage(const char* s) {
    if (!s) return 0;
    const char* dash = strchr(s, '-');
    if (!dash || !dash[1]) return 0;
    int sub = atoi(dash + 1);
    return (sub >= 1 && sub <= 15) ? (uint8_t)sub : 0;
}

static void fetchTeletext(uint16_t page, uint8_t sub) {
    char url[64];
    if (sub > 0)
        snprintf(url, sizeof(url), "%s%u-%u", TELETEXT_URL_BASE, page, (unsigned)sub);
    else
        snprintf(url, sizeof(url), "%s%u", TELETEXT_URL_BASE, page);
    // T272 confirmed TLS heap contention: spotifyTask holds ~40k at steady state,
    // leaving maxAlloc<50k — insufficient for a new TLS handshake. Same fix as
    // fetchCrypto/fetchStockQuote/fetchHeatmapQuote. Supersedes ADR-044 item 9.
    spotifyTask::tlsYield();
    LOG_HEAP("dataTask.teletext");
    WiFiClientSecure tls;
    HTTPClient http;
    unsigned long t0 = millis();
    int code = openHttps(tls, http, url,
        consumeCertBreak(DATA_FETCH_TELETEXT_PAGE)
            ? wrongCaFor(DATA_FETCH_TELETEXT_PAGE) : TELETEXT_NOS_ROOT_CA,  // TASK-344
        /*insecure=*/false);
    if (code == OPENHTTPS_BEGIN_FAILED) {
        LOG_W("dataTask.teletext", "http.begin failed page=%u", page);
        portENTER_CRITICAL_SAFE(&s_teletextMux);
        s_teletextState.lastHttpCode = -1;
        portEXIT_CRITICAL_SAFE(&s_teletextMux);
        spotifyTask::tlsResume();
        return;
    }
    LOG_D("dataTask.teletext", "GET page=%u %d elapsed=%lums", page, code, (unsigned long)(millis() - t0));
    String body;
    if (code == 200) body = http.getString();
    else             LOG_W("dataTask.teletext", "http %d page=%u", code, page);
    http.end();
    spotifyTask::tlsResume();
    LOG_HEAP("dataTask.teletext");

    TeletextState st = {};
    st.lastHttpCode = code;

    if (code != 200) {
        portENTER_CRITICAL_SAFE(&s_teletextMux);
        s_teletextState.lastHttpCode = code;
        portEXIT_CRITICAL_SAFE(&s_teletextMux);
        return;
    }

    st.page = page;

    // --- Parse navigation metadata (lines before <pre> of form KEY=VALUE) ---
    {
        uint16_t ftlIdx = 0;
        int lineStart = 0;
        int blen = body.length();
        for (int i = 0; i <= blen; i++) {
            char c = (i < blen) ? body[i] : '\n';
            if (c == '\n' || c == '\r') {
                if (i > lineStart) {
                    // Check if line starts with '<' (HTML) — skip those
                    char first = body[lineStart];
                    if (first != '<') {
                        // Find '=' delimiter
                        int eq = -1;
                        for (int j = lineStart; j < i; j++) {
                            if (body[j] == '=') { eq = j; break; }
                        }
                        if (eq > lineStart) {
                            char key[8] = {}; char val[32] = {};
                            int klen = eq - lineStart;
                            if (klen < 8) {
                                body.substring(lineStart, eq).toCharArray(key, sizeof(key));
                                body.substring(eq+1, i).toCharArray(val, sizeof(val));
                                // Trim leading/trailing whitespace from key and val
                                char *kp = key; while (*kp == ' ') kp++;
                                char *vp = val; while (*vp == ' ') vp++;
                            }
                            char *kp = key; while (*kp == ' ') kp++;
                            char *vp = val; while (*vp == ' ') vp++;

                            if (strcmp(kp, "pn") == 0) {
                                if (strncmp(vp, "p_", 2) == 0) st.prevPage    = parsePage(vp+2);
                                if (strncmp(vp, "n_", 2) == 0) st.nextPage    = parsePage(vp+2);
                                if (strncmp(vp, "ns", 2) == 0) { st.subpageNext = parsePage(vp+2); st.subpageNextSub = parseSubpage(vp+2); }
                                if (strncmp(vp, "ps", 2) == 0) { st.subpagePrev = parsePage(vp+2); st.subpagePrevSub = parseSubpage(vp+2); }
                            } else if (strcmp(kp, "ftl") == 0 && ftlIdx < 4) {
                                // Format: "101-p" → extract page number before '-'
                                char pgstr[8] = {};
                                for (int k = 0; vp[k] && vp[k] != '-' && k < 7; k++) pgstr[k] = vp[k];
                                st.ftlTargets[ftlIdx] = parsePage(pgstr);
                                ftlIdx++;
                            }
                        }
                    }
                    // Stop parsing metadata once we hit <pre>
                    if (body[lineStart] == '<' && body.indexOf("<pre>", lineStart) == lineStart) break;
                }
                lineStart = i + 1;
            }
        }
    }

    // --- Extract <pre>...</pre> content (1000 bytes) ---
    // String::indexOf uses strstr() which stops at '\0'. The NOS response body
    // contains null bytes (teletext control codes), so use null-safe memcmp for </pre>.
    const char* raw    = body.c_str();
    int         rawLen = (int)body.length();
    int preStart = body.indexOf("<pre>");  // <pre> always before any null bytes
    int preEnd   = -1;
    if (preStart >= 0) {
        for (int i = preStart + 5; i <= rawLen - 6; i++) {
            if (memcmp(raw + i, "</pre>", 6) == 0) { preEnd = i; break; }
        }
    }
    if (preStart < 0 || preEnd < 0) {
        LOG_W("dataTask.teletext", "no <pre> block page=%u", page);
        portENTER_CRITICAL_SAFE(&s_teletextMux);
        s_teletextState.lastHttpCode = code;
        portEXIT_CRITICAL_SAFE(&s_teletextMux);
        spotifyTask::tlsResume();
        return;
    }
    int contentStart = preStart + 5;
    int contentLen   = preEnd - contentStart;
    // Fill cells row by row (clamp to 25×40)
    for (int r = 0; r < 25; r++) {
        for (int ci = 0; ci < 40; ci++) {
            int idx = r * 40 + ci;
            st.cells[r][ci] = (idx < contentLen)
                ? (uint8_t)(raw[contentStart + idx]) : 0x20;
        }
    }

    // --- Extract fast-text labels from row 24 ---
    // Scan row 24 for colored text segments; map color index to ftl button order [1,2,3,6]
    {
        static const uint8_t kFtlColors[4] = { 1, 2, 3, 6 };  // red, green, yellow, cyan
        char segBuf[48] = {};
        int segIdx = 0;
        uint8_t curFg = 7;
        uint8_t row24[40];
        memcpy(row24, st.cells[24], 40);

        for (int i = 0; i < 4; i++) {
            char lblBuf[12] = {};
            int llen = 0;
            curFg = 7;
            for (int ci = 0; ci < 40; ci++) {
                uint8_t c = row24[ci];
                if (c >= 0x01 && c <= 0x07) { curFg = c; continue; }
                if (c >= 0x10 && c <= 0x17) { curFg = c & 0x07; continue; }
                if (c < 0x20) continue;
                if (curFg == kFtlColors[i] && llen < 11) lblBuf[llen++] = (char)c;
            }
            // Trim
            while (llen > 0 && lblBuf[llen-1] == ' ') llen--;
            lblBuf[llen] = '\0';
            strlcpy(st.ftlLabels[i], lblBuf, sizeof(st.ftlLabels[i]));
        }
    }

    st.ready = true;
    LOG_D("dataTask.teletext", "ok page=%u prev=%u next=%u ftl=%u/%u/%u/%u",
          st.page, st.prevPage, st.nextPage,
          st.ftlTargets[0], st.ftlTargets[1], st.ftlTargets[2], st.ftlTargets[3]);

    portENTER_CRITICAL_SAFE(&s_teletextMux);
    s_teletextState = st;
    s_teletextNew   = true;
    portEXIT_CRITICAL_SAFE(&s_teletextMux);
}

// Pre-allocated at startup (unfragmented heap) and reused per fetch cycle to avoid
// malloc failure after long-uptime TLS cycling (PROP-004 / EXP-003).
// Capacity: 20 symbols × ~120 B each ≈ 2.4 kB peak usage; 2560 gives headroom.
// M-MEMPLAN §8 (TASK-269): backed by the static overlay region MEM_heatmap_doc
// (s_overlay_any_foreground[2560] in BSS). Allocator returns the fixed buffer;
// deallocate is a no-op. Safe because heatmap and crypto parses are serial.
static BasicJsonDocument<StaticRegionAllocator> s_heatmapDoc(
    2560, StaticRegionAllocator{MEM_heatmap_doc, 2560u});

// --- webradio state ----------------------------------------------------------

static portMUX_TYPE           s_webRadioMux        = portMUX_INITIALIZER_UNLOCKED;
static WebRadioStationsResult s_webRadioResult;
static bool                   s_webRadioNew         = false;
// TASK-289: set by abortWebRadioFetch() (loopTask), read by the mirror loop
// (dataTask). Cleared when a fetch begins, so an abort raised while the fetch
// waits in tlsYield() — the common interleave — is seen before mirror 1.
static volatile bool          s_webRadioFetchAbort  = false;
static char                   s_pendingCountry[4]   = "NL";
static uint8_t                s_pendingBitrateCap   = 0;   // TASK-221: bitrateMax kbps (0=off)
static portMUX_TYPE           s_pendingCountryMux   = portMUX_INITIALIZER_UNLOCKED;

// --- planeradar state ---------------------------------------------------------

static portMUX_TYPE      s_planeRadarMux    = portMUX_INITIALIZER_UNLOCKED;
static PlaneRadarResult  s_planeRadarResult;
static bool              s_planeRadarNew    = false;

// Request params snapshotted by enqueuePlaneRadar() (caller's task), read back
// by fetchPlaneRadar() (dataTask) — same pattern as s_pendingCountry above.
static float             s_pendingPrLat     = 52.3676f;  // reference default (Amsterdam area)
static float             s_pendingPrLon     = 4.9041f;
static float             s_pendingPrDistNm  = 8.0f;      // ~10 km default preset
static uint8_t           s_pendingPrEpoch   = 0;         // VE-PRL-6 identity echo (TASK-323)
static portMUX_TYPE      s_pendingPrMux     = portMUX_INITIALIZER_UNLOCKED;

// SERIAL_DEBUG test hook (set prForceParseFail <n>, TASK-361): written by the
// main/serial-command task, consumed by dataTask inside prFetchOnce() —
// cross-task, needs the same spinlock discipline as every other pending-*
// slot above, even though it's a single int.
static int               s_prForceParseFailCount = 0;
static portMUX_TYPE      s_prForceFailMux   = portMUX_INITIALIZER_UNLOCKED;

// --- Geocode (M-PR-LOCATIONS / TASK-320) ------------------------------------
// Pending-config slot per the s_pendingCountry / s_pendingPr* pattern above —
// NOT the Request.symbol[8] payload, which can't hold a UK full postcode
// ("SW1A 1AA" = 8 chars + NUL, DEV-2). Snapshotted by fetchGeocode() under
// the mux. s_geoSeq is the request identity counter echoed in GeocodeResult
// (DEV-1/TASK-300); bumped by every accepted enqueueGeocode().
// s_geoInjected parks a SERIAL_DEBUG synthetic result (set geocode …):
// pollGeocode() consumes it BEFORE looking at the real slot, and
// enqueueGeocode() is a no-op while it is parked, so a concurrent real fetch
// can never overwrite injected state (VE-PRL-2 / the TASK-276 bug shape).
static char          s_pendingGeoCountry[4]  = "";
static char          s_pendingGeoPostcode[12] = "";
static uint8_t       s_geoSeq                = 0;
static portMUX_TYPE  s_pendingGeoMux         = portMUX_INITIALIZER_UNLOCKED;

static GeocodeResult s_geocodeResult;
static bool          s_geocodeNew            = false;
static GeocodeResult s_geoInjectedResult;
static bool          s_geoInjected           = false;
static portMUX_TYPE  s_geocodeMux            = portMUX_INITIALIZER_UNLOCKED;

static const char GEOCODE_URL_BASE[] = "https://nominatim.openstreetmap.org/search";
// Nominatim usage policy requires an identifying UA (default UAs get 403 —
// verified, phase0-geocode-probe.md); same string the phase-0 probe used.
static const char GEOCODE_UA[]       = "esp32-cyd-multiapp/1.0 (github.com/weimanc; device)";

// WebRadio station-page parse-buffer capacity. WR_MAX_STATIONS (30) stations ×
// ~115 B filtered JSON ≈ 3.45 kB; 5120 gives headroom. Shrunk from 14336 (sized
// for 100 stations) when the array caps were reconciled to limit=30 (TASK-224).
// TASK-239 (ADR-045 amendment): the doc is now a per-fetch LOCAL in
// fetchWebRadioStations() — allocated after tlsYield() (maxAlloc ≥ 50 KB) and
// freed before tlsResume(), not held resident — reclaiming ~5 KB during WebRadio
// playback. Freeing before the audio path's first alloc is the whole point.
// TASK-326: budgeted in mem_manifest.yaml as webradio_stations_doc
// (placement: runtime, like decoder/inbuf) — live across mirror TLS
// handshakes, so it cannot be a planner-placed overlay tenant.
static constexpr size_t WR_DOC_CAP = 5120;

// TASK-289: minimum contiguous block for a radio-browser TLS handshake attempt.
// Every observed successful fetch ran with maxBlk ≥ 47 KB; with WebRadio playback
// concurrently holding the heap (arena + decoder + I2S), maxBlk sits ≤ ~38 KB and
// every handshake is doomed to -32512 (SSL alloc fail). 40 KB cleanly splits the
// two observed populations.
static constexpr size_t WR_FETCH_MIN_TLS_BLOCK = 40 * 1024;

// TASK-265 (2026-06-28): nl1/at1 are decommissioned (no DNS records); de1 + the
// all.api round-robin alias both resolve to IPv4 (91.98.4.78) and verify against
// the pinned ISRG Root X1, so an IPv4-only ESP32 can reach them. Keeping the two
// live hosts. (Production fix — also belongs on master, not just the arena branch.)
//
// 2026-07-13: all.api goes FIRST now, de1 demoted to fallback. Root-caused a
// "wrong station list" report by adding raw-page + resolved-IP debug logging
// (see fetchOneMirror/appendHttpStations) — de1 was returning a clean HTTP 200
// but a stale/desynced slice of the DB (missing the actual top-voted NL
// stations, e.g. NPO Radio 1/2, entirely) while all.api's own load-balancer
// served the correct canonical data for the identical query at the same
// moment. The per-mirror loop treats any 200 as final and never falls
// through, so pinning de1 first meant a de1 sync outage silently stuck the
// device on bad data instead of failing over. all.api exists precisely to
// route around a single unhealthy named mirror — use it as the primary.
static const char* kRadioBrowserMirrors[] = {
    "all.api.radio-browser.info",
    "de1.api.radio-browser.info",
};
static constexpr int WR_MIRROR_COUNT =
    (int)(sizeof(kRadioBrowserMirrors) / sizeof(kRadioBrowserMirrors[0]));

static void fetchHeatmapQuote() {
    // TASK-131: stop Spotify's TLS connection before allocating our own.
    // Spotify's persistent session holds ~40 k of heap; at steady state
    // maxAlloc ≈ 39 k — not enough for a new Yahoo Finance TLS handshake
    // (~50–70 k). tlsYield() blocks until the spotify task has called
    // client.stop(); tlsResume() (below) releases it to reconnect.
    spotifyTask::tlsYield();
    LOG_HEAP("dataTask.stock");   // after Spotify TLS freed — expect maxBlk ≥ 50k

    WiFiClientSecure tls;
    tls.setCACert(consumeCertBreak(DATA_FETCH_HEATMAP_QUOTE)
                      ? wrongCaFor(DATA_FETCH_HEATMAP_QUOTE) : YAHOO_FINANCE_ROOT_CA);  // TASK-344
    HTTPClient http;
    if (!http.begin(tls, HEATMAP_URL)) {
        LOG_W("dataTask.stock", "heatmap http.begin failed");
        HeatmapQuoteResult r; r.ok = false; r.errorCode = -100;
        portENTER_CRITICAL_SAFE(&s_heatmapMux);
        s_heatmapResult = r; s_heatmapNew = true;
        portEXIT_CRITICAL_SAFE(&s_heatmapMux);
        spotifyTask::tlsResume();  // BP-031: resume on the early-return path too,
                                   // else a begin() failure leaves Spotify paused
        return;
    }
    // Screener endpoint requires a browser-like User-Agent; without it the
    // response is 200 OK but returns an empty quotes array.
    http.addHeader("User-Agent", "Mozilla/5.0");
    // Force HTTP/1.0 to avoid Transfer-Encoding: chunked. The screener endpoint
    // returns chunked encoding under HTTP/1.1, which embeds hex chunk-size headers
    // (e.g. "2913\r\n") in the raw stream. http.getStream() returns the raw
    // WiFiClient stream without decoding chunks; ArduinoJson then parses the
    // leading "2913" as a JSON number and never reaches the finance object, giving
    // count=0 with err=Ok. HTTP/1.0 forces identity encoding (close-delimited)
    // so getStream() yields clean JSON that ArduinoJson can parse correctly.
    http.useHTTP10(true);
    unsigned long t0 = millis();
    int code = certSentinel(tls, http.GET());  // TASK-341
    LOG_D("dataTask.stock", "heatmap GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    HeatmapQuoteResult r;
    if (code != 200) {
        r.ok = false; r.errorCode = code;
        http.end();
    } else {
        // Filter: 4 fields per quote entry; raw payload ~54 kB → filtered ~2.4 kB.
        // s_heatmapDoc pre-allocated at startup (avoids malloc failure from heap
        // fragmentation after long uptime TLS cycling). See PROP-004 / EXP-003.
        StaticJsonDocument<256> filter;
        filter["finance"]["result"][0]["quotes"][0]["symbol"]                    = true;
        filter["finance"]["result"][0]["quotes"][0]["marketCap"]                 = true;
        filter["finance"]["result"][0]["quotes"][0]["regularMarketPrice"]        = true;
        filter["finance"]["result"][0]["quotes"][0]["regularMarketChangePercent"]= true;
        s_heatmapDoc.clear();
        LOG_D("dataTask.stock", "heatmap doc cap=%u", (unsigned)s_heatmapDoc.capacity());
        DeserializationError err = deserializeJson(s_heatmapDoc, http.getStream(),
                                       DeserializationOption::Filter(filter));
        http.end();
        if (err) {
            LOG_W("dataTask.stock", "heatmap JSON err: %s", err.c_str());
            r.ok = false; r.errorCode = -90 - (int)err.code();
        } else {
            JsonArrayConst quotes =
                s_heatmapDoc["finance"]["result"][0]["quotes"].as<JsonArrayConst>();
            r.ok = true;
            for (JsonVariantConst q : quotes) {
                if (r.count >= 20) break;
                const char* sym = q["symbol"].as<const char*>();
                if (!sym) continue;
                strncpy(r.symbols[r.count], sym, 7); r.symbols[r.count][7] = '\0';
                r.prices[r.count]    = q["regularMarketPrice"].as<float>();
                r.changePct[r.count] = q["regularMarketChangePercent"].as<float>();
                r.marketCap[r.count] = q["marketCap"].as<float>();
                r.count++;
            }
            if (r.count == 0)
                LOG_W("dataTask.stock", "heatmap parse ok but count=0 — unexpected empty quotes array");
            else
                LOG_D("dataTask.stock", "heatmap ok count=%u usage=%u/%u",
                      r.count, (unsigned)s_heatmapDoc.memoryUsage(),
                      (unsigned)s_heatmapDoc.capacity());
        }
    }
    portENTER_CRITICAL_SAFE(&s_heatmapMux);
    // Don't overwrite an unread good result with a bad one.
    if (r.ok || !s_heatmapNew || !s_heatmapResult.ok) {
        s_heatmapResult = r;
        s_heatmapNew    = true;
    }
    portEXIT_CRITICAL_SAFE(&s_heatmapMux);
    spotifyTask::tlsResume();  // release Spotify task to reconnect
    LOG_HEAP("dataTask.stock");   // after heatmap TLS freed
}

static void fetchStockChartBySym(const char* symbol, uint8_t rangeIdx) {
    if (!symbol || symbol[0] == '\0' || rangeIdx >= 4) return;
    spotifyTask::tlsYield();
    String url = String(STOCK_URL_BASE) + symbol
                 + "?interval=" + STOCK_INTERVAL_STR[rangeIdx]
                 + "&range="    + STOCK_RANGE_STR[rangeIdx];
    StockChartResult r;
    strlcpy(r.symbol, symbol, sizeof(r.symbol));
    r.rangeIdx = rangeIdx;
    s_stockChartProgress = 0;  // TLS + http.begin
    LOG_HEAP("dataTask.stock");
    WiFiClientSecure tls;
    tls.setCACert(consumeCertBreak(DATA_FETCH_STOCK_CHART_BY_SYM)
                      ? wrongCaFor(DATA_FETCH_STOCK_CHART_BY_SYM) : YAHOO_FINANCE_ROOT_CA);  // TASK-344
    HTTPClient http;
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.stock", "chart-sym http.begin failed sym=%s", symbol);
        r.ok = false; r.errorCode = -100;
    } else {
        http.addHeader("User-Agent", "Mozilla/5.0");
        http.useHTTP10(true);
        s_stockChartProgress = 1;  // GET in flight
        unsigned long t0 = millis();
        int code = certSentinel(tls, http.GET());  // TASK-341
        LOG_D("dataTask.stock", "chart-sym GET %s %d elapsed=%lums",
              symbol, code, (unsigned long)(millis() - t0));
        if (code != 200) {
            r.ok = false; r.errorCode = code;
            http.end();
        } else {
            s_stockChartProgress = 2;  // JSON parse (streaming)
            StaticJsonDocument<128> filter;
            filter["chart"]["result"][0]["indicators"]["quote"][0]["close"] = true;
            StaticJsonDocument<2048> doc;
            DeserializationError err = deserializeJson(doc, http.getStream(),
                                           DeserializationOption::Filter(filter));
            http.end();
            if (err) {
                LOG_W("dataTask.stock", "chart-sym JSON err: %s", err.c_str());
                r.ok = false; r.errorCode = -90 - (int)err.code();
            } else {
                JsonArray closeArr =
                    doc["chart"]["result"][0]["indicators"]["quote"][0]["close"].as<JsonArray>();
                r.lo = 1e30f; r.hi = -1e30f;
                for (JsonVariant v : closeArr) {
                    if (v.isNull()) continue;
                    float val = v.as<float>();
                    r.points[r.len++] = val;
                    if (val < r.lo) r.lo = val;
                    if (val > r.hi) r.hi = val;
                    if (r.len >= 110) break;
                }
                if (r.lo > r.hi) { r.lo = 0.0f; r.hi = 1.0f; }
                r.ok = true;
                LOG_D("dataTask.stock", "chart-sym ok sym=%s len=%u", symbol, r.len);
            }
        }
    }
    s_stockChartProgress = -1;  // idle
    portENTER_CRITICAL_SAFE(&s_stockChartMux);
    s_stockChartResult = r;
    s_stockChartNew    = true;
    portEXIT_CRITICAL_SAFE(&s_stockChartMux);
    LOG_HEAP("dataTask.stock");
    spotifyTask::tlsResume();
}

// Issues one GET against a single mirror with the given TLS mode and, on HTTP
// 200, parses the response into the caller-supplied parse doc. Returns the HTTP code, or a
// negative HTTPClient connection/handshake/verify error code, or -100 on a
// JSON parse error after a successful 200.
static int fetchOneMirror(const char* mirror, const char* country, uint8_t bitrateCap,
                          unsigned offset, JsonDocument& doc) {
    char url[192];
    // limit= is an intentional heap mitigation (commit dafa4a4), not a bug —
    // driven by WR_MAX_STATIONS (TASK-224) so the query, the result arrays,
    // and the fill-loop bound below all agree. It also bounds one page to what
    // the 5 KB parse doc holds; offset pages through the list (TASK-232).
    int n = snprintf(url, sizeof(url),
        "https://%s/json/stations/search"
        "?countrycode=%s&codec=MP3&hidebroken=true&order=votes&reverse=true&limit=%u&offset=%u",
        mirror, country, (unsigned)WR_MAX_STATIONS, offset);
    // TASK-221: cap drain rate for the small ring buffer. radio-browser's param
    // is camelCase bitrateMax (host-verified — snake_case bitrate_max is ignored).
    // bitrate=0 (unknown) still passes the server filter, which is acceptable here.
    if (bitrateCap > 0 && n > 0 && n < (int)sizeof(url))
        snprintf(url + n, sizeof(url) - n, "&bitrateMax=%u", (unsigned)bitrateCap);
    // Log the complete query so a host curl can replicate this request exactly
    // (must stay below the bitrateMax append — the cap silently reshapes the
    // station list, so a log of the base URL alone is actively misleading).
    LOG_D("dataTask.webradio", "url=%s", url);

    WiFiClientSecure tls;
    // Pinned root only (ADR-029). The setInsecure() fallback was removed in
    // TASK-236 after the T_WR_TLS_01 gate proved it never fired — a verify
    // failure now surfaces as a connection error and the mirror is skipped,
    // rather than being silently downgraded to an unverified session.
    tls.setCACert(consumeCertBreak(DATA_FETCH_WEBRADIO_STATIONS)
                      ? wrongCaFor(DATA_FETCH_WEBRADIO_STATIONS) : RADIO_BROWSER_ROOT_CA);  // TASK-344
    HTTPClient http;
    http.useHTTP10(true);
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.webradio", "http.begin failed mirror=%s", mirror);
        return -1;
    }
    http.addHeader("User-Agent", "ESPSpotify/1.0");
    unsigned long t0 = millis();
    // TASK-341: custom path is deliberate (per-mirror skip-on-fail), but still
    // gets the -120 sentinel so a rotted radio-browser pin doesn't masquerade
    // as an ordinary dead mirror.
    int code = certSentinel(tls, http.GET());
    LOG_I("dataTask.webradio", "GET mirror=%s code=%d elapsed=%lums",
          mirror, code, (unsigned long)(millis() - t0));
    if (code != 200) {
        http.end();
        return code;
    }

    // Filter: extract only 3 fields per array element.
    // [0]["field"]=true pattern applies to all array elements in ArduinoJson v6.
    StaticJsonDocument<128> filter;
    filter[0]["name"]         = true;
    filter[0]["url_resolved"] = true;
    filter[0]["bitrate"]      = true;
    doc.clear();
    DeserializationError err = deserializeJson(doc, http.getStream(),
                                   DeserializationOption::Filter(filter));
    http.end();
    if (err) {
        strlcpy(s_webRadioResult.jsonErr, err.c_str(), sizeof(s_webRadioResult.jsonErr));
        LOG_W("dataTask.webradio", "JSON err mirror=%s: %s", mirror, err.c_str());
        return -100;
    }
    return 200;
}

// Appends the http:// stations from the just-parsed page in `doc` into
// s_webRadioResult (up to WR_MAX_STATIONS total). https:// streams are skipped:
// they can't be played on this no-PSRAM board (TASK-232). Returns the number of
// raw entries seen in this page — the caller uses a short page (< WR_MAX_STATIONS)
// as the signal that the list is exhausted and stops paging.
static unsigned appendHttpStations(JsonDocument& doc) {
    unsigned seen = 0;
    for (JsonVariantConst entry : doc.as<JsonArrayConst>()) {
        seen++;
        if (s_webRadioResult.count >= WR_MAX_STATIONS) continue;  // keep counting 'seen'
        const char* name = entry["name"].as<const char*>();
        const char* urlr = entry["url_resolved"].as<const char*>();
        if (!name || !urlr || !urlr[0]) continue;
        if (strncasecmp(urlr, "http://", 7) != 0) continue;  // skip https:// (and anything else)
        uint8_t idx = s_webRadioResult.count;
        strlcpy(s_webRadioResult.stations[idx].name, name,
                sizeof(s_webRadioResult.stations[0].name));
        strlcpy(s_webRadioResult.stations[idx].url,  urlr,
                sizeof(s_webRadioResult.stations[0].url));
        s_webRadioResult.stations[idx].bitrate = entry["bitrate"].as<uint16_t>();
        s_webRadioResult.count++;
    }
    return seen;
}

// --- planeradar fetch ---------------------------------------------------------

static const char PLANERADAR_URL_BASE[] = "https://opendata.adsb.fi/api/v3/lat/";

// One-char-pushback wrapper over an Arduino Stream: legC's scanner (below)
// consumes the '{' that opens each aircraft object while hunting for the next
// one, so it must be handed back to deserializeJson() along with the rest of
// the stream. Mirrors PrependReader in
// app/tools/host/pr_parse_trial/main.cpp exactly (ADR-048 transcription target),
// just over Arduino's Stream interface instead of the host trial's byte-buffer shim.
class PrStreamPrepend {
public:
    PrStreamPrepend(char c, Stream& s) : _c(c), _s(s) {}
    int read() {
        if (_has) { _has = false; return (unsigned char)_c; }
        return _s.read();
    }
    size_t readBytes(char* buf, size_t n) {
        size_t off = 0;
        if (_has && n > 0) { buf[0] = _c; _has = false; off = 1; }
        if (off >= n) return off;
        return off + _s.readBytes(buf + off, n - off);
    }
private:
    char    _c;
    bool    _has = true;
    Stream& _s;
};

// pickF/copyTrimmed/fillRecord/insertNearest below are a direct transcription of
// app/tools/host/pr_parse_trial/main.cpp's legC helpers (ADR-048) — the phase-0
// trial IS the design spec for this fetcher; do not re-derive the fallback
// chains or truncation policy independently of that file.
static float prPickF(JsonObjectConst o, std::initializer_list<const char*> keys, float dflt) {
    for (const char* k : keys) {
        JsonVariantConst v = o[k];
        if (v.is<float>() || v.is<int>()) return v.as<float>();
    }
    return dflt;
}

static void prCopyTrimmed(JsonObjectConst o, const char* key, char* out, size_t cap) {
    out[0] = '\0';
    const char* s = o[key].as<const char*>();
    if (!s) return;
    size_t n = strnlen(s, cap - 1);
    while (n > 0 && s[n - 1] == ' ') --n;
    memcpy(out, s, n);
    out[n] = '\0';
}

// showGround: pr_parse_trial's main() always calls with false — ground/taxiing
// traffic is excluded at parse time (not just render time) so it can't crowd
// out overflying traffic out of the PR_MAX_AIRCRAFT nearest-first cap. The
// INT32_MIN "GND" sentinel stays part of the record shape for a future
// showGround=true call site (e.g. a settings toggle); unreachable today.
static bool prFillRecord(JsonObjectConst plane, PrAircraft* ac, bool showGround) {
    if (!plane["lat"].is<float>() || !plane["lon"].is<float>()) return false;
    const char* ab = plane["alt_baro"].as<const char*>();
    bool ground = ab && strcmp(ab, "ground") == 0;
    if (ground && !showGround) return false;

    ac->lat    = plane["lat"].as<float>();
    ac->lon    = plane["lon"].as<float>();
    ac->distNm = prPickF(plane, {"dst"}, 1e9f);
    ac->noseDeg  = (int16_t)lroundf(prPickF(plane, {"true_heading", "mag_heading", "track", "dir"}, 0));
    ac->trackDeg = (int16_t)lroundf(prPickF(plane, {"track", "true_heading", "mag_heading", "dir"}, 0));
    ac->gsKnots  = (int16_t)lroundf(prPickF(plane, {"gs", "tas", "ias"}, 0));
    if (ground) {
        ac->altFt = INT32_MIN;
    } else if (plane["alt_baro"].is<float>() || plane["alt_baro"].is<int>()) {
        ac->altFt = (int32_t)lroundf(plane["alt_baro"].as<float>());
    } else if (plane["alt_geom"].is<float>() || plane["alt_geom"].is<int>()) {
        ac->altFt = (int32_t)lroundf(plane["alt_geom"].as<float>());
    } else {
        ac->altFt = INT32_MAX;
    }
    prCopyTrimmed(plane, "flight", ac->callsign, sizeof(ac->callsign));
    if (!ac->callsign[0]) prCopyTrimmed(plane, "hex", ac->callsign, sizeof(ac->callsign));
    prCopyTrimmed(plane, "t", ac->type, sizeof(ac->type));
    return true;
}

// Nearest-first replace-farthest insertion (ADR-048 truncation policy) — 'kept'
// count is tracked by the caller (r.count); this only decides which slot to
// (over)write once the array is full.
static void prInsertNearest(PrAircraft* kept, uint8_t& keptCount, uint8_t cap, const PrAircraft& ac) {
    if (keptCount < cap) { kept[keptCount++] = ac; return; }
    uint8_t far = 0;
    for (uint8_t i = 1; i < keptCount; i++)
        if (kept[i].distNm > kept[far].distNm) far = i;
    if (ac.distNm < kept[far].distNm) kept[far] = ac;
}

// ADR-048 leg C — chunked per-object filtered parse. Scans the raw stream for
// the "ac" array, then deserializes ONE aircraft object at a time through a
// 15-field filter into a small reused doc (docCap ~4 KB measured peak,
// independent of aircraft count — see ADR-048). Returns 0 on success (result
// aircraft/count filled), or a negative internal error code (see dataTask.h's
// PlaneRadarResult comment for the code list) with 'result' left at defaults.
// TASK-361: 'scanned' (out) is the count of "ac" array objects this attempt
// fully deserialized before returning — on success it's the true traffic
// density (unlike result.count, which is capped at PR_MAX_AIRCRAFT by the
// nearest-first insert); on a mid-array parse failure it's how far the
// attempt got before truncation. Diagnostic-only — not consumed by render
// logic, just logged, so a busy-traffic soak can correlate failure rate
// against real payload size instead of guessing from HTTP code alone.
static int prParseStream(Stream& stream, PlaneRadarResult& result, uint16_t& scanned) {
    scanned = 0;
    // Scan for "ac" key then its '['.
    const char* pat = "\"ac\"";
    int pi = 0, c;
    while ((c = stream.read()) != -1) {
        if (c == pat[pi]) { if (!pat[++pi]) break; }
        else pi = (c == pat[0]) ? 1 : 0;
    }
    if (c == -1) return -111;  // no "ac" key found
    while ((c = stream.read()) != -1 && c != '[') {
        if (!isspace(c) && c != ':') return -112;  // bad ac value
    }
    if (c == -1) return -113;  // truncated before array

    StaticJsonDocument<768> filter;
    for (const char* k : {"lat", "lon", "dst", "dir", "track", "true_heading",
                          "mag_heading", "gs", "tas", "ias", "alt_baro",
                          "alt_geom", "flight", "hex", "t"})
        filter[k] = true;
    // Reused per-object doc — ADR-048's measured ~4 KB fixed peak, independent
    // of traffic (only this doc's memory is live at any time, not the array).
    // M-MEMPLAN §8: backed by the static overlay region MEM_planeradar_doc
    // (manifest entry planeradar_doc) — off the tight dataTask stack (TASK-240)
    // and off the heap; dataTask serialization guarantees exclusivity with the
    // crypto/heatmap tenants of the same region.
    BasicJsonDocument<StaticRegionAllocator> doc(
        4096, StaticRegionAllocator{MEM_planeradar_doc, 4096u});
    uint16_t n = 0;
    for (;;) {
        do { c = stream.read(); } while (c != -1 && (isspace(c) || c == ','));
        if (c == ']') break;
        if (c == -1) { scanned = n; return -114; }      // truncated mid-array
        if (c != '{') { scanned = n; return -115; }     // unexpected byte
        PrStreamPrepend pr('{', stream);
        DeserializationError err = deserializeJson(doc, pr,
                                       DeserializationOption::Filter(filter));
        if (err) {
            LOG_W("dataTask.planeradar", "parse error at object %u: %s", n, err.c_str());
            scanned = n;
            return -90 - (int)err.code();
        }
        PrAircraft ac{};
        if (prFillRecord(doc.as<JsonObjectConst>(), &ac, /*showGround=*/false))
            prInsertNearest(result.aircraft, result.count, PR_MAX_AIRCRAFT, ac);
        n++;
    }
    result.ok = true;
    scanned = n;
    return 0;
}

// TASK-313 fix experiment (TASK-361 extends the caller to a 2nd,
// radius-capped retry): a single fresh-connection attempt against a given
// URL, filling 'r' with either a parsed result or an error code. Shared by
// fetchPlaneRadar()'s first try and both of its parse-error retries
// (BP-047) — each call opens its own WiFiClientSecure/HTTPClient so a
// "retry" is a genuinely new TLS connection, not a reused stream. Returns
// the raw HTTP code (or -100 if http.begin() itself failed) so the caller
// can gate each retry on exactly "code==200 but parse failed" without
// inferring it from errorCode's sign (which parse errors and non-200 codes
// can both produce).
static int prFetchOnce(const char* url, PlaneRadarResult& r, uint16_t& scanned) {
    scanned = 0;
    // TASK-361 VE test hook: consume one forced-failure credit if armed
    // (set prForceParseFail <n>) — bypasses the network entirely so the
    // fetch/retry/retry2 cascade can be exercised deterministically. See
    // dataTask.h's doc comment for why real Cloudflare conditions can't be
    // relied on to reproduce "both attempts fail" on demand.
    bool forced = false;
    portENTER_CRITICAL_SAFE(&s_prForceFailMux);
    if (s_prForceParseFailCount > 0) { s_prForceParseFailCount--; forced = true; }
    portEXIT_CRITICAL_SAFE(&s_prForceFailMux);
    if (forced) {
        LOG_D("dataTask.planeradar", "FORCED synthetic parse failure (VE injection)");
        r.ok = false; r.errorCode = -92;   // IncompleteInput sentinel, matches the real observed code
        return 200;   // pretend HTTP succeeded so code==200 && !r.ok gates the caller's retry logic
    }
    WiFiClientSecure tls;
    tls.setCACert(consumeCertBreak(DATA_FETCH_PLANERADAR)
                      ? wrongCaFor(DATA_FETCH_PLANERADAR) : PLANERADAR_ROOT_CA);  // TASK-344
    HTTPClient http;
    http.useHTTP10(true);   // identity encoding so getStream() yields clean JSON
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.planeradar", "http.begin failed");
        r.ok = false; r.errorCode = -100;
        return -100;
    }
    unsigned long t0 = millis();
    // TASK-341: custom path is deliberate (radius-capped retry cascade), but
    // still gets the -120 sentinel — shared by the first try and both
    // TASK-361 retries since they all funnel through this one function.
    int code = certSentinel(tls, http.GET());
    // TASK-361: declared Content-Length alongside the existing timing log —
    // http.useHTTP10(true) forces identity encoding (no chunked transfer), so
    // this is a real byte count, not -1. Lets a soak correlate truncation
    // against response size instead of guessing from HTTP code alone.
    int declaredSize = http.getSize();
    LOG_D("dataTask.planeradar", "GET %d elapsed=%lums size=%d",
          code, (unsigned long)(millis() - t0), declaredSize);
    if (code != 200) {
        // Distinct, unmolested HTTP code (incl. 429) reaches the app — the
        // phase-0 limit probe measured ~33% 429s at the nominal 1 req/s
        // courtesy limit; skip-don't-retry is inherent here (single-shot
        // fetch per enqueue, driven by the app's 10 s cadence timer, no
        // internal retry loop to suppress). TASK-313's retry (in the caller)
        // is scoped to parse errors only — it never fires here.
        r.ok = false; r.errorCode = code;
        http.end();
        return code;
    }
    int rc = prParseStream(http.getStream(), r, scanned);
    http.end();
    if (rc != 0) { r.ok = false; r.errorCode = rc; r.count = 0; }
    return code;
}

// TASK-361: radius cap for the 2nd (size-reducing) retry — see the retry
// cascade's comment in fetchPlaneRadar() below for the full rationale.
static constexpr float PR_RETRY2_MAX_NM = 10.0f;

static void fetchPlaneRadar() {
    float lat, lon, distNm;
    uint8_t epoch;
    portENTER_CRITICAL_SAFE(&s_pendingPrMux);
    lat = s_pendingPrLat; lon = s_pendingPrLon; distNm = s_pendingPrDistNm;
    epoch = s_pendingPrEpoch;
    portEXIT_CRITICAL_SAFE(&s_pendingPrMux);

    spotifyTask::tlsYield();   // BP-031: free Spotify TLS before our own handshake
    LOG_HEAP("dataTask.planeradar");

    char url[128];
    snprintf(url, sizeof(url), "%s%.4f/lon/%.4f/dist/%.1f",
             PLANERADAR_URL_BASE, lat, lon, distNm);

    PlaneRadarResult r;
    uint16_t scanned = 0;
    int code = prFetchOnce(url, r, scanned);

    // TASK-313: adsb.fi (Cloudflare-fronted) prompt-clean-EOFs mid-body on
    // ~9% of fetches (evidence phase — TLS-fingerprint edge treatment, not a
    // stall, not rate-limit-coupled). Hypothesis: the truncation is
    // transient per-connection, so a single immediate retry on a brand-new
    // connection recovers it. Retry ONLY when the HTTP transaction itself
    // succeeded (code==200) but the body failed to parse; never on a non-200
    // code (incl. 429) or a connect/begin failure — those stay
    // skip-don't-retry per prFetchOnce's comment.
    if (code == 200 && !r.ok) {
        LOG_D("dataTask.planeradar", "parse rc=%d scanned=%u -> retry", r.errorCode, (unsigned)scanned);
        vTaskDelay(pdMS_TO_TICKS(300));
        PlaneRadarResult retryResult;   // fresh result — no stale partial state
        uint16_t retryScanned = 0;
        int retryCode = prFetchOnce(url, retryResult, retryScanned);
        LOG_D("dataTask.planeradar", "retry ok=%d rc=%d scanned=%u",
              (int)retryResult.ok, retryResult.errorCode, (unsigned)retryScanned);
        r = retryResult;   // second attempt's outcome (success or error) wins
        scanned = retryScanned;

        // TASK-361: the full-radius retry ALSO failed with a parse error —
        // per the confirmed size-scaling data (30-min soaks at Hong Kong/
        // LHR/JFK), same-size retries are NOT independent draws in this
        // regime (JFK's 62KB+ bucket: retry-also-failed ~69%, well above
        // what an independent per-connection redraw would predict) — a 3rd
        // same-size attempt has weak, diminishing-returns odds. Instead,
        // shrink the query radius for this final attempt: the app already
        // discards everything past PR_MAX_AIRCRAFT nearest aircraft
        // (prInsertNearest below), so a smaller radius rarely changes what
        // gets displayed once there's enough density to have produced a
        // large response in the first place (host-probed at JFK:
        // dist=20nm->111 aircraft/56.5KB vs dist=4nm->35/16.6KB — still
        // comfortably over the 24-slot cap, at ~3.4x less data). This only
        // ever fires on a cycle that's already failed twice at full radius
        // and would otherwise fall back to PR_STALE_S dead-reckoning, so a
        // radius-limited fresh frame is a strict improvement — no change to
        // the common case (first attempt succeeds) at all.
        if (retryCode == 200 && !retryResult.ok) {
            float smallDistNm = distNm * 0.5f;
            if (smallDistNm > PR_RETRY2_MAX_NM) smallDistNm = PR_RETRY2_MAX_NM;
            char smallUrl[128];
            snprintf(smallUrl, sizeof(smallUrl), "%s%.4f/lon/%.4f/dist/%.1f",
                     PLANERADAR_URL_BASE, lat, lon, smallDistNm);
            LOG_D("dataTask.planeradar", "retry also failed rc=%d -> radius-capped retry2 distNm=%.1f",
                  retryResult.errorCode, (double)smallDistNm);
            vTaskDelay(pdMS_TO_TICKS(300));
            PlaneRadarResult retry2Result;   // fresh result — no stale partial state
            uint16_t retry2Scanned = 0;
            prFetchOnce(smallUrl, retry2Result, retry2Scanned);
            LOG_D("dataTask.planeradar", "retry2 ok=%d rc=%d scanned=%u",
                  (int)retry2Result.ok, retry2Result.errorCode, (unsigned)retry2Scanned);
            r = retry2Result;   // third attempt's outcome (success or error) wins
            scanned = retry2Scanned;
        }
    }

    r.epoch = epoch;   // VE-PRL-6: echo the snapshot taken at enqueue time, not a later one
    // TASK-361: 'scanned' is this cycle's FINAL attempt's true "ac" object
    // count (see prParseStream) — on success it's real traffic density
    // uncapped by PR_MAX_AIRCRAFT; on failure it's how far the parse got.
    // Diagnostic-only, not otherwise consumed.
    LOG_D("dataTask.planeradar", "ok=%d errorCode=%d count=%u scanned=%u epoch=%u",
          (int)r.ok, r.errorCode, (unsigned)r.count, (unsigned)scanned, (unsigned)r.epoch);
    // TASK-368 (measurement only): nearest-first roster this cycle, so a
    // host-side diff across cycles can tell boundary churn (aircraft
    // entering/leaving near rank PR_MAX_AIRCRAFT) apart from mid-disc
    // motion-vector error — the two candidate explanations for "inaccurate
    // tracking" EXP-015 couldn't distinguish from jump_px alone.
    if (r.ok) {
        char roster[300]; size_t rp = 0;
        for (uint8_t i = 0; i < r.count && rp < sizeof(roster) - 10; i++) {
            int n = snprintf(roster + rp, sizeof(roster) - rp, "%s,%.1f;",
                              r.aircraft[i].callsign[0] ? r.aircraft[i].callsign : "?",
                              (double)r.aircraft[i].distNm);
            if (n > 0) rp += (size_t)n;
        }
        LOG_D("dataTask.planeradar", "roster %s", roster);
    }

    portENTER_CRITICAL_SAFE(&s_planeRadarMux);
    s_planeRadarResult = r;
    s_planeRadarNew    = true;
    portEXIT_CRITICAL_SAFE(&s_planeRadarMux);
    LOG_HEAP("dataTask.planeradar");
    spotifyTask::tlsResume();
}

// Minimal percent-encoder for the geocode query values (no urlEncode helper
// exists anywhere in this firmware — DEV review). Unreserved chars (RFC 3986:
// alnum, '-', '.', '_', '~') pass through; everything else — notably the
// space in a UK full postcode — becomes %XX. Truncates safely at dstLen.
static void geoUrlEncode(char* dst, size_t dstLen, const char* src) {
    static const char hex[] = "0123456789ABCDEF";
    size_t o = 0;
    for (const char* p = src; *p && o + 4 <= dstLen; p++) {
        unsigned char c = (unsigned char)*p;
        if (isalnum(c) || c == '-' || c == '.' || c == '_' || c == '~') {
            dst[o++] = (char)c;
        } else {
            dst[o++] = '%';
            dst[o++] = hex[c >> 4];
            dst[o++] = hex[c & 0xF];
        }
    }
    dst[o] = '\0';
}

// One-shot Nominatim structured search (M-PR-LOCATIONS / TASK-320). Query
// contract per phase0-geocode-probe.md: jsonv2, limit=1, addressdetails=0;
// max observed response 459 B -> 1 KB parse doc (measured, BP-001); lat/lon
// arrive as JSON *strings*; "[]" = postcode unknown (-96, distinct from
// network errors so the editor can say "not found"). openHttps() supplies
// the -120 pinned-CA sentinel (TASK-318); NOMINATIM_ROOT_CA carries a
// cross-sign rot risk documented at its #define.
static void fetchGeocode() {
    char country[4], postcode[12];
    uint8_t seq;
    portENTER_CRITICAL_SAFE(&s_pendingGeoMux);
    strlcpy(country,  s_pendingGeoCountry,  sizeof(country));
    strlcpy(postcode, s_pendingGeoPostcode, sizeof(postcode));
    seq = s_geoSeq;
    portEXIT_CRITICAL_SAFE(&s_pendingGeoMux);

    spotifyTask::tlsYield();   // BP-031: free Spotify TLS before our own handshake
    LOG_HEAP("dataTask.geocode");

    char encPost[40];
    geoUrlEncode(encPost, sizeof(encPost), postcode);
    char url[192];
    snprintf(url, sizeof(url),
             "%s?country=%s&postalcode=%s&format=jsonv2&limit=1&addressdetails=0",
             GEOCODE_URL_BASE, country, encPost);

    GeocodeResult r;
    r.seq = seq;

    WiFiClientSecure tls;
    HTTPClient http;
    http.setUserAgent(GEOCODE_UA);   // mandatory (403 on default UA) — set pre-begin
    int code = openHttps(tls, http, url,
        consumeCertBreak(DATA_FETCH_GEOCODE)
            ? wrongCaFor(DATA_FETCH_GEOCODE) : NOMINATIM_ROOT_CA,  // TASK-344
        false);
    if (code == OPENHTTPS_BEGIN_FAILED) {
        r.errorCode = -100;
    } else if (code == 200) {
        DynamicJsonDocument doc(1024);
        DeserializationError err = deserializeJson(doc, http.getString());
        http.end();
        if (err) {
            r.errorCode = -97;   // transaction ok, body unparseable
            LOG_W("dataTask.geocode", "parse error: %s", err.c_str());
        } else if (doc.as<JsonArrayConst>().size() == 0) {
            r.errorCode = -96;   // GEOCODE_NO_MATCH — valid query, unknown postcode
        } else {
            JsonVariantConst hit = doc.as<JsonArrayConst>()[0];
            r.ok  = true;
            r.lat = atof(hit["lat"] | "0");   // strings on the wire (probe)
            r.lon = atof(hit["lon"] | "0");
            strlcpy(r.display, hit["display_name"] | "", sizeof(r.display));
        }
    } else {
        r.errorCode = code;      // HTTP status, HTTPClient negative, or -120
        http.end();
    }
    LOG_D("dataTask.geocode", "%s %s -> ok=%d rc=%d seq=%u",
          country, postcode, (int)r.ok, r.errorCode, (unsigned)seq);

    portENTER_CRITICAL_SAFE(&s_geocodeMux);
    s_geocodeResult = r;
    s_geocodeNew    = true;
    portEXIT_CRITICAL_SAFE(&s_geocodeMux);
    LOG_HEAP("dataTask.geocode");
    spotifyTask::tlsResume();
}

static void fetchWebRadioStations() {
    char    country[4];
    uint8_t bitrateCap;
    portENTER_CRITICAL_SAFE(&s_pendingCountryMux);
    strlcpy(country, s_pendingCountry, sizeof(country));
    bitrateCap = s_pendingBitrateCap;
    portEXIT_CRITICAL_SAFE(&s_pendingCountryMux);

    // TASK-289: arm the abort window — an abortWebRadioFetch() raised any time
    // from here on (typically while we sit in tlsYield() below) skips the
    // mirror handshakes.
    s_webRadioFetchAbort = false;

    // tlsYield() stops spotifyTask and waits up to 90 s for its ack. With
    // Spotify's SO_RCVTIMEO capped at 15 s, worst-case blocking is 60 s
    // (two API calls each with one retry). After the ack the shared TLS
    // session is freed (~50 KB), giving the local WiFiClientSecure below
    // enough contiguous heap for its own handshake.
    s_dbgWrPhase = 0; s_dbgWrPhaseMs = millis();   // TASK-299: entering tlsYield
    spotifyTask::tlsYield();
    s_dbgWrPhase = 1; s_dbgWrPhaseMs = millis();   // TASK-299: yield acked, fetching
    LOG_HEAP("dataTask.webradio");

    // Reset result in-place; dataTask is sole writer — no lock needed for the fill.
    s_webRadioResult        = WebRadioStationsResult{};
    strlcpy(s_webRadioResult.countryCode, country, sizeof(s_webRadioResult.countryCode));
    s_webRadioResult.bitrateCap = bitrateCap;   // WR-1: echo the latched request params for the caller's identity check

    s_webRadioResult.count = 0;
    // TASK-239: the 5 KB parse buffer lives only for the fill loop — allocated
    // here (just after tlsYield(), when maxAlloc ≥ 50 KB so the malloc is safe)
    // and freed at the closing brace below, BEFORE tlsResume() and long before
    // any _play(). Not held resident across playback.
    {
    DynamicJsonDocument webRadioDoc(WR_DOC_CAP);
    for (int mi = 0; mi < WR_MIRROR_COUNT; mi++) {
        const char* mirror = kRadioBrowserMirrors[mi];

        // TASK-289: playback started while we were still fetching — abandon.
        // _play() signals this explicitly (see abortWebRadioFetch()); its
        // arena/decoder allocations would starve the handshake below anyway.
        // -102 distinguishes "abandoned for playback" from the -101 heap guard.
        if (s_webRadioFetchAbort) {
            s_webRadioResult.lastHttpCode = -102;
            LOG_I("dataTask.webradio", "fetch abandoned: playback started");
            break;
        }

        // TASK-289: per-mirror contiguity guard. Since TASK-287 unblocked
        // _play(), a debug wrUrl playback can allocate its arena/decoder WHILE
        // this fetch is between tlsYield() and its first handshake — so the
        // check must run per-attempt, not once up front (observed: maxBlk 47 KB
        // at the post-yield probe, 14 KB by the first GET). Fail fast with a
        // distinct code instead of burning a doomed handshake mid-decode;
        // WebRadioApp re-enqueues on the next resume() when the heap is quiet.
        // A guard-pass followed by a playback alloc mid-handshake can still
        // yield -1 as before — the resume() retry covers that residue too.
        size_t maxBlk = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
        if (maxBlk < WR_FETCH_MIN_TLS_BLOCK) {
            s_webRadioResult.lastHttpCode = -101;
            LOG_W("dataTask.webradio",
                  "fetch skipped: maxBlk=%uk < %uk (TLS would OOM; playback active?)",
                  (unsigned)(maxBlk / 1024),
                  (unsigned)(WR_FETCH_MIN_TLS_BLOCK / 1024));
            break;
        }

        // Page through the votes-ordered list on this mirror, accumulating only
        // playable (http://) stations until we have WR_MAX_STATIONS or run out
        // (TASK-232). TLS is the pinned root CA only (ADR-029); a verify/handshake
        // failure (negative code) skips the mirror — the setInsecure() fallback was
        // removed in TASK-236 (never fired at the T_WR_TLS_01 gate).
        bool mirrorOk = false;
        s_webRadioResult.tlsInsecure = false;  // always false now; kept for observability
        for (uint8_t page = 0; page < WR_FETCH_MAX_PAGES; page++) {
            unsigned offset = (unsigned)page * WR_MAX_STATIONS;
            int code = fetchOneMirror(mirror, country, bitrateCap, offset, webRadioDoc);
            // TASK-284: a JSON parse error (-100, observed as IncompleteInput) on
            // page 0 is a one-off transient stall mid-body-read, not a persistent
            // mirror fault — an identical request re-issued moments later (host
            // curl, or a fresh DUT attempt) succeeds cleanly. Retry the SAME
            // mirror once with a fresh connection before falling through to the
            // next mirror; this is what previously made "both mirrors fail in
            // the same attempt" look like a systemic outage when it was really
            // two independent transient stalls landing back-to-back.
            if (code == -100 && page == 0) {
                LOG_W("dataTask.webradio", "mirror=%s JSON err on page 0 — retrying once", mirror);
                code = fetchOneMirror(mirror, country, bitrateCap, offset, webRadioDoc);
            }
            s_webRadioResult.lastHttpCode = code;
            if (code != 200) {
                if (page == 0)
                    LOG_W("dataTask.webradio", "mirror=%s failed code=%d", mirror, code);
                break;  // page 0 → try next mirror; later page → stop, keep what we have
            }
            mirrorOk = true;
            unsigned seen = appendHttpStations(webRadioDoc);
            if (s_webRadioResult.count >= WR_MAX_STATIONS) break;  // list full
            if (seen < WR_MAX_STATIONS) break;                     // last page reached
        }

        if (mirrorOk) {
            // The mirrors serve the same list, so once one responds we've seen the
            // real data — stop here regardless of how many http stations it yielded
            // rather than re-paging an equivalent mirror.
            s_webRadioResult.ok = (s_webRadioResult.count > 0);
            LOG_I("dataTask.webradio", "ok mirror=%s country=%s count=%u",
                  mirror, country, s_webRadioResult.count);
            break;
        }
    }
    }  // webRadioDoc freed here (TASK-239) — before tlsResume() and before playback

    // Brief spinlock — only marks the flag, not the 15 kB struct copy.
    portENTER_CRITICAL_SAFE(&s_webRadioMux);
    s_webRadioNew = true;
    portEXIT_CRITICAL_SAFE(&s_webRadioMux);

    spotifyTask::tlsResume();
    s_dbgWrPhase = 2; s_dbgWrPhaseMs = millis();   // TASK-299: fetch pass complete
    LOG_HEAP("dataTask.webradio");
}

// --- task body ---------------------------------------------------------------

static void taskBody(void *) {
    LOG_I("dataTask", "task started stack=%uB", (unsigned)kStackBytes);
    for (;;) {
        Request req;
        BaseType_t got = xQueueReceive(s_queue, &req, portMAX_DELAY);
        if (got != pdTRUE) continue;
        s_dbgInFlight = (int8_t)req.type; s_dbgInFlightMs = millis();  // TASK-299
        switch (req.type) {
            case DATA_FETCH_WEATHER:          fetchWeather(); break;
            case DATA_FETCH_CRYPTO:           fetchCrypto();  break;
            case DATA_FETCH_STOCK_QUOTE:      fetchStockQuote(); break;
            case DATA_FETCH_STOCK_CHART:      fetchStockChart(req.param0, req.param1); break;
            case DATA_FETCH_HEATMAP_QUOTE:    fetchHeatmapQuote(); break;
            case DATA_FETCH_STOCK_CHART_BY_SYM: fetchStockChartBySym(req.symbol, req.param1); break;
            case DATA_FETCH_TELETEXT_PAGE: {
                uint16_t pg  = ((uint16_t)(req.param0 & 0x0F) << 8) | req.param1;
                uint8_t  sub = req.param0 >> 4;
                fetchTeletext(pg ? pg : 101, sub);
                break;
            }
            case DATA_FETCH_WEBRADIO_STATIONS: fetchWebRadioStations(); break;
            case DATA_FETCH_PLANERADAR:        fetchPlaneRadar(); break;
            case DATA_FETCH_GEOCODE:           fetchGeocode(); break;
            default: break;
        }
        s_pendingMask &= ~(1u << req.type);   // TASK-250: fetch done — allow re-enqueue
        s_dbgInFlight = -1;                   // TASK-299: dispatch loop idle
    }
}

// --- public API --------------------------------------------------------------

void begin() {
    if (s_taskHandle != nullptr) return;
    s_queue = xQueueCreate(4, sizeof(Request));
    if (!s_queue) {
        LOG_E("dataTask", "xQueueCreate failed");
        return;
    }
    BaseType_t rc = xTaskCreatePinnedToCore(
        &taskBody, "dataTask",
        kStackBytes / sizeof(StackType_t),
        nullptr, kPriority, &s_taskHandle, kPinnedCpu);
    if (rc != pdPASS) {
        LOG_E("dataTask", "xTaskCreatePinnedToCore failed rc=%d", (int)rc);
        s_taskHandle = nullptr;
    }
}

// TASK-250: coalesce duplicate param-less fetches. A stock quote is a ~16 s
// batch (8 sequential Yahoo GETs); without this, a List launch + a triggerFetch
// (or a re-enqueue while one is in flight) stacked multiple in the depth-4 queue,
// each ~16 s, starving every other app's fetch behind them. Bit set on a
// successful enqueue, cleared when the fetcher completes (dispatch loop). Only
// the param-less generic enqueue() dedups — chart/teletext carry params and must
// not coalesce different requests.
void enqueue(FetchType type) {
    if (!s_queue) return;
    uint32_t bit = 1u << (uint8_t)type;
    if (s_pendingMask & bit) return;   // already queued or in flight — coalesce
    Request req = { (uint8_t)type };
    if (xQueueSend(s_queue, &req, 0) != pdTRUE) {
        LOG_W("dataTask", "queue full — dropped type=%d", (int)type);
        return;
    }
    s_pendingMask |= bit;
}

// WIRE2-G4: weather fetch with coords snapshotted at enqueue time.
void enqueueWeather(float lat, float lon) {
    if (!s_queue) return;
    // Snapshot on the caller's task (which owns g_settings) under the mux —
    // fetchWeather() reads it back the same way (enqueuePlaneRadar pattern).
    // Snapshot BEFORE the coalesce check: the slot must always hold the latest
    // coords so a coalesced request still fetches the newest location (W-5).
    portENTER_CRITICAL_SAFE(&s_pendingWxMux);
    s_pendingWxLat = lat;
    s_pendingWxLon = lon;
    portEXIT_CRITICAL_SAFE(&s_pendingWxMux);
    // W-5: unlike enqueuePlaneRadar, KEEP the generic enqueue()'s TASK-250
    // pendingMask coalescing — bit cleared by the dispatch loop after
    // fetchWeather() completes, same as the generic path.
    uint32_t bit = 1u << (uint8_t)DATA_FETCH_WEATHER;
    if (s_pendingMask & bit) return;   // already queued or in flight — coalesce
    Request req = {}; req.type = DATA_FETCH_WEATHER;
    if (xQueueSend(s_queue, &req, 0) != pdTRUE) {
        LOG_W("dataTask", "queue full — dropped weather fetch");
        return;
    }
    s_pendingMask |= bit;
}

bool pollWeather(WeatherResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_weatherMux);
    if (s_weatherNew) {
        *out        = s_weatherResult;
        s_weatherNew = false;
        got          = true;
    }
    portEXIT_CRITICAL_SAFE(&s_weatherMux);
    return got;
}

bool pollCrypto(CryptoResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_cryptoMux);
    if (s_cryptoNew) {
        *out       = s_cryptoResult;
        s_cryptoNew = false;
        got         = true;
    }
    portEXIT_CRITICAL_SAFE(&s_cryptoMux);
    return got;
}

int lastCryptoHttpCode() { return s_cryptoLastCode; }

void enqueueStockChart(uint8_t tickerIdx, uint8_t rangeIdx) {
    if (!s_queue) return;
    Request req = {}; req.type = DATA_FETCH_STOCK_CHART; req.param0 = tickerIdx; req.param1 = rangeIdx;
    if (xQueueSend(s_queue, &req, 0) != pdTRUE)
        LOG_W("dataTask", "queue full — dropped stock chart idx=%u rng=%u", tickerIdx, rangeIdx);
}

void enqueueHeatmapQuote() {
    if (!s_queue) return;
    Request req = {}; req.type = DATA_FETCH_HEATMAP_QUOTE;
    if (xQueueSend(s_queue, &req, 0) != pdTRUE)
        LOG_W("dataTask", "queue full — dropped heatmap quote");
}

void enqueueStockChartBySym(const char* symbol, uint8_t rangeIdx) {
    if (!s_queue || !symbol) return;
    Request req = {}; req.type = DATA_FETCH_STOCK_CHART_BY_SYM; req.param1 = rangeIdx;
    strncpy(req.symbol, symbol, 7); req.symbol[7] = '\0';
    if (xQueueSend(s_queue, &req, 0) != pdTRUE)
        LOG_W("dataTask", "queue full — dropped chart-sym %s", symbol);
}

bool pollStockQuote(StockQuoteResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_stockQuoteMux);
    if (s_stockQuoteNew) {
        *out           = s_stockQuoteResult;
        s_stockQuoteNew = false;
        got             = true;
    }
    portEXIT_CRITICAL_SAFE(&s_stockQuoteMux);
    return got;
}

bool pollStockChart(StockChartResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_stockChartMux);
    if (s_stockChartNew) {
        *out           = s_stockChartResult;
        s_stockChartNew = false;
        got             = true;
    }
    portEXIT_CRITICAL_SAFE(&s_stockChartMux);
    return got;
}

bool pollHeatmapQuote(HeatmapQuoteResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_heatmapMux);
    if (s_heatmapNew) {
        *out        = s_heatmapResult;
        s_heatmapNew = false;
        got          = true;
    }
    portEXIT_CRITICAL_SAFE(&s_heatmapMux);
    return got;
}

void configureStockTickers(const char tickers[8][8]) {
    portENTER_CRITICAL_SAFE(&s_stockTickersMux);
    for (int i = 0; i < 8; i++)
        strlcpy(s_stockTickers[i], tickers[i], 8);
    portEXIT_CRITICAL_SAFE(&s_stockTickersMux);
}

void configureCrypto(const char ids[6][16], const char* ccy) {
    portENTER_CRITICAL_SAFE(&s_cryptoConfigMux);
    for (int i = 0; i < 6; i++)
        strlcpy(s_cryptoIds[i], ids[i], 16);
    strlcpy(s_cryptoCcy, ccy, 4);
    portEXIT_CRITICAL_SAFE(&s_cryptoConfigMux);
}

int8_t stockQuoteProgress() { return s_stockQuoteProgress; }
int8_t weatherFetchPhase()  { return s_weatherFetchPhase; }
int8_t cryptoFetchPhase()   { return s_cryptoFetchPhase; }
int8_t stockChartProgress() { return s_stockChartProgress; }

// TASK-240: stack instrumentation (uxTaskGetStackHighWaterMark returns words).
size_t stackHighWaterBytes() {
    return s_taskHandle ? (size_t)uxTaskGetStackHighWaterMark(s_taskHandle) * sizeof(StackType_t) : 0;
}
size_t stackSizeBytes() { return (size_t)kStackBytes; }

void enqueueTeletextPage(uint16_t page, uint8_t sub) {
    if (!s_queue) return;
    Request req = {};
    req.type   = DATA_FETCH_TELETEXT_PAGE;
    // High nibble of param0 = sub (0-15); low nibble = page high byte (0-3 for pages 100-899)
    req.param0 = (uint8_t)((sub << 4) | ((page >> 8) & 0x0F));
    req.param1 = (uint8_t)(page & 0xFF);
    if (xQueueSend(s_queue, &req, 0) != pdTRUE)
        LOG_W("dataTask", "queue full — dropped teletext page=%u sub=%u", page, (unsigned)sub);
}

bool pollTeletext(TeletextState *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_teletextMux);
    if (s_teletextNew) {
        *out         = s_teletextState;
        s_teletextNew = false;
        got           = true;
    }
    portEXIT_CRITICAL_SAFE(&s_teletextMux);
    return got;
}

int lastTeletextHttpCode() {
    int code;
    portENTER_CRITICAL_SAFE(&s_teletextMux);
    code = s_teletextState.lastHttpCode;
    portEXIT_CRITICAL_SAFE(&s_teletextMux);
    return code;
}

void enqueueWebRadioStations(const char* countryCode, uint8_t bitrateCap) {
    if (!s_queue || !countryCode || !countryCode[0]) return;
    // Snapshot the request params on the caller's task (which owns g_settings)
    // under the mux — dataTask reads them back the same way (matches country).
    portENTER_CRITICAL_SAFE(&s_pendingCountryMux);
    strlcpy(s_pendingCountry, countryCode, sizeof(s_pendingCountry));
    s_pendingBitrateCap = bitrateCap;
    portEXIT_CRITICAL_SAFE(&s_pendingCountryMux);
    Request req = {}; req.type = DATA_FETCH_WEBRADIO_STATIONS;
    if (xQueueSend(s_queue, &req, 0) != pdTRUE) {
        s_dbgWrDrops++;   // TASK-299: silent-drop counter — visible via get dataq
        LOG_W("dataTask", "queue full — dropped webradio stations country=%s", countryCode);
    } else {
        s_dbgWrEnqueues++;
    }
}

void enqueuePlaneRadar(float lat, float lon, float distNm, uint8_t epoch) {
    if (!s_queue) return;
    portENTER_CRITICAL_SAFE(&s_pendingPrMux);
    s_pendingPrLat    = lat;
    s_pendingPrLon    = lon;
    s_pendingPrDistNm = distNm;
    s_pendingPrEpoch  = epoch;
    portEXIT_CRITICAL_SAFE(&s_pendingPrMux);
    Request req = {}; req.type = DATA_FETCH_PLANERADAR;
    if (xQueueSend(s_queue, &req, 0) != pdTRUE)
        LOG_W("dataTask", "queue full — dropped planeradar fetch");
}

bool pollPlaneRadar(PlaneRadarResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_planeRadarMux);
    if (s_planeRadarNew) {
        *out             = s_planeRadarResult;
        s_planeRadarNew  = false;
        got              = true;
    }
    portEXIT_CRITICAL_SAFE(&s_planeRadarMux);
    return got;
}

uint8_t enqueueGeocode(const char* countryCC, const char* postcode) {
    uint8_t seq;
    // Injection gate first (VE-PRL-2): while a synthetic result is parked,
    // no real fetch may be started — return the pending seq so the caller's
    // identity check matches the injected result it is about to poll.
    portENTER_CRITICAL_SAFE(&s_geocodeMux);
    bool parked = s_geoInjected;
    portEXIT_CRITICAL_SAFE(&s_geocodeMux);

    portENTER_CRITICAL_SAFE(&s_pendingGeoMux);
    if (!parked) {
        s_geoSeq++;
        strlcpy(s_pendingGeoCountry,  countryCC ? countryCC : "", sizeof(s_pendingGeoCountry));
        strlcpy(s_pendingGeoPostcode, postcode  ? postcode  : "", sizeof(s_pendingGeoPostcode));
    }
    seq = s_geoSeq;
    portEXIT_CRITICAL_SAFE(&s_pendingGeoMux);
    if (parked) return seq;

    if (s_queue) {
        Request req = {}; req.type = DATA_FETCH_GEOCODE;
        if (xQueueSend(s_queue, &req, 0) != pdTRUE)
            LOG_W("dataTask", "queue full — dropped geocode %s %s", countryCC, postcode);
    }
    return seq;
}

bool pollGeocode(GeocodeResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_geocodeMux);
    if (s_geoInjected) {              // parked synthetic result wins (consumed once)
        *out          = s_geoInjectedResult;
        s_geoInjected = false;
        got           = true;
    } else if (s_geocodeNew) {
        *out         = s_geocodeResult;
        s_geocodeNew = false;
        got          = true;
    }
    portEXIT_CRITICAL_SAFE(&s_geocodeMux);
    return got;
}

void debugInjectGeocode(const GeocodeResult& r) {
    GeocodeResult inj = r;
    portENTER_CRITICAL_SAFE(&s_pendingGeoMux);
    inj.seq = s_geoSeq;               // pass the caller's identity check
    portEXIT_CRITICAL_SAFE(&s_pendingGeoMux);
    portENTER_CRITICAL_SAFE(&s_geocodeMux);
    s_geoInjectedResult = inj;
    s_geoInjected       = true;
    s_geocodeNew        = false;      // synthetic result supersedes any unconsumed real one
    portEXIT_CRITICAL_SAFE(&s_geocodeMux);
}

void debugForcePlaneRadarParseFail(int n) {
    portENTER_CRITICAL_SAFE(&s_prForceFailMux);
    s_prForceParseFailCount = (n < 0) ? 0 : n;
    portEXIT_CRITICAL_SAFE(&s_prForceFailMux);
}

int debugPeekForcedParseFailCount() {
    int n;
    portENTER_CRITICAL_SAFE(&s_prForceFailMux);
    n = s_prForceParseFailCount;
    portEXIT_CRITICAL_SAFE(&s_prForceFailMux);
    return n;
}

void debugBreakCert(FetchType type) {
    portENTER_CRITICAL_SAFE(&s_certBreakMux);
    s_certBreakTarget = (int)type;
    portEXIT_CRITICAL_SAFE(&s_certBreakMux);
}

int debugPeekCertBreak() {
    int t;
    portENTER_CRITICAL_SAFE(&s_certBreakMux);
    t = s_certBreakTarget;
    portEXIT_CRITICAL_SAFE(&s_certBreakMux);
    return t;
}

void dbgGeocodeState(bool* parked, bool* hasNew, GeocodeResult* last) {
    portENTER_CRITICAL_SAFE(&s_geocodeMux);
    if (parked) *parked = s_geoInjected;
    if (hasNew) *hasNew = s_geocodeNew;
    if (last)   *last   = s_geoInjected ? s_geoInjectedResult : s_geocodeResult;
    portEXIT_CRITICAL_SAFE(&s_geocodeMux);
}

void dbgQueueState(DbgQueueState* out) {
    if (!out) return;
    out->queueWaiting = s_queue ? (uint8_t)uxQueueMessagesWaiting(s_queue) : 0;
    out->pendingMask  = s_pendingMask;
    out->inFlight     = s_dbgInFlight;
    out->inFlightMs   = s_dbgInFlightMs;
    out->wrPhase      = s_dbgWrPhase;
    out->wrPhaseMs    = s_dbgWrPhaseMs;
    out->wrEnqueues   = s_dbgWrEnqueues;
    out->wrDrops      = s_dbgWrDrops;
}

void abortWebRadioFetch() {
    s_webRadioFetchAbort = true;
}

bool pollWebRadioStations(WebRadioStationsResult *out) {
    bool got = false;
    portENTER_CRITICAL_SAFE(&s_webRadioMux);
    got = s_webRadioNew;
    if (got) s_webRadioNew = false;
    portEXIT_CRITICAL_SAFE(&s_webRadioMux);
    // Copy outside critical section — 15 kB copy under spinlock would
    // disable Core 1 interrupts for ~1 ms (unacceptable for touch/display).
    // Sole writer (dataTask) never refills mid-poll in practice.
    if (got) *out = s_webRadioResult;
    return got;
}

// T-WRSET-01 (WR-1) fault-injection hook — see dataTask.h for why this is the
// only reliable way to exercise the discard path. Overwrites the poll slot
// unconditionally, same as a real mirror-loop write would; the caller (set
// wrInjectResult) is responsible for choosing a countryCode/bitrateCap that
// deliberately mismatches the app's current snapshot.
void debugInjectWebRadioResult(const WebRadioStationsResult& r) {
    portENTER_CRITICAL_SAFE(&s_webRadioMux);
    s_webRadioResult = r;
    s_webRadioNew    = true;
    portEXIT_CRITICAL_SAFE(&s_webRadioMux);
}

}  // namespace dataTask
