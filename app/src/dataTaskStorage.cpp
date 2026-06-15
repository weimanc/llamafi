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

// --- module state ------------------------------------------------------------

static QueueHandle_t s_queue       = nullptr;
static TaskHandle_t  s_taskHandle  = nullptr;

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

// Bumped 12→20 KB: fetchWebRadioStations TLS + streaming ArduinoJson overflowed 12 KB (TASK-208 DUT).
constexpr UBaseType_t kStackBytes  = 20 * 1024;
constexpr UBaseType_t kPriority    = 1;
constexpr BaseType_t  kPinnedCpu   = APP_CPU_NUM;

static const char WEATHER_URL[] =
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=51.75&longitude=-0.47"
    "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
    "&timezone=Europe/London";

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

static const char  HEATMAP_URL[] =
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    "?scrIds=ms_technology&count=20&formatted=false";

// --- fetch functions ---------------------------------------------------------

static void fetchWeather() {
    s_weatherFetchPhase = 0;  // TLS + http.begin
    LOG_HEAP("dataTask.weather");
    WiFiClientSecure tls;
    tls.setCACert(OPEN_METEO_ROOT_CA);
    HTTPClient http;
    http.useHTTP10(true);   // force Connection:close so http.end() frees TLS
    if (!http.begin(tls, WEATHER_URL)) {
        LOG_W("dataTask.weather", "http.begin failed");
        s_weatherFetchPhase = -1;
        return;
    }
    s_weatherFetchPhase = 1;  // GET in flight
    unsigned long t0 = millis();
    int code = http.GET();
    LOG_D("dataTask.weather", "GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    String body;
    if (code == 200) body = http.getString();
    else             LOG_W("dataTask.weather", "http %d", code);
    http.end();             // TLS freed here (HTTP/1.0 close)
    LOG_HEAP("dataTask.weather");
    if (code == 200) {
        s_weatherFetchPhase = 2;  // JSON parse
        DynamicJsonDocument doc(1024);
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
    tls.setCACert(COINGECKO_ROOT_CA);
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
    int code = http.GET();
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
        DynamicJsonDocument doc(2048);
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
    spotifyTask::tlsYield();         // free Spotify TLS before 8 consecutive Yahoo handshakes
    LOG_HEAP("dataTask.stock");   // before 8-ticker TLS loop
    char tickers[8][8];
    portENTER_CRITICAL_SAFE(&s_stockTickersMux);
    memcpy(tickers, s_stockTickers, sizeof(tickers));
    portEXIT_CRITICAL_SAFE(&s_stockTickersMux);
    StockQuoteResult r;
    r.ok = true;
    for (int i = 0; i < 8 && r.ok; i++) {
        s_stockQuoteProgress = (int8_t)i;  // which ticker is currently being fetched
        String url = String(STOCK_URL_BASE) + tickers[i] + "?interval=1d&range=1d";
        WiFiClientSecure tls;
        tls.setCACert(YAHOO_FINANCE_ROOT_CA);
        HTTPClient http;
        if (!http.begin(tls, url)) {
            LOG_W("dataTask.stock", "http.begin failed sym=%s", tickers[i]);
            r.ok = false; r.errorCode = -100;
            break;
        }
        http.addHeader("User-Agent", "Mozilla/5.0");
        http.useHTTP10(true);
        unsigned long t0 = millis();
        int code = http.GET();
        LOG_D("dataTask.stock", "quote GET %s %d elapsed=%lums",
              tickers[i], code, (unsigned long)(millis() - t0));
        if (code != 200) {
            r.ok = false; r.errorCode = code;
            http.end();
            break;
        }
        // Filter tree: chart→result[0]→meta→{regularMarketPrice,chartPreviousClose}
        // 5-level path × 2 leaves; ArduinoJson ~80B minimum; <128> gives headroom.
        // HOST TEST: test_yahoo_finance_api.py T_SF_03 QUOTE_DOC_BYTES=256.
        StaticJsonDocument<128> filter;
        filter["chart"]["result"][0]["meta"]["regularMarketPrice"] = true;
        filter["chart"]["result"][0]["meta"]["chartPreviousClose"] = true;
        StaticJsonDocument<256> doc;
        DeserializationError err = deserializeJson(doc, http.getStream(),
                                       DeserializationOption::Filter(filter));
        http.end();
        if (err) {
            LOG_W("dataTask.stock", "JSON err sym=%s: %s", tickers[i], err.c_str());
            r.ok = false; r.errorCode = -90 - (int)err.code();
            break;
        }
        auto meta       = doc["chart"]["result"][0]["meta"];
        float price     = meta["regularMarketPrice"].as<float>();
        float prev      = meta["chartPreviousClose"].as<float>();
        r.prices[i]     = price;
        r.changePct[i]  = (prev != 0.0f) ? (price - prev) / prev * 100.0f : 0.0f;
    }
    s_stockQuoteProgress = -1;  // idle
    portENTER_CRITICAL_SAFE(&s_stockQuoteMux);
    s_stockQuoteResult = r;
    s_stockQuoteNew    = true;
    portEXIT_CRITICAL_SAFE(&s_stockQuoteMux);
    if (r.ok) LOG_D("dataTask.stock", "quote ok aapl=%.2f msft=%.2f", r.prices[0], r.prices[1]);
    LOG_HEAP("dataTask.stock");   // after 8-ticker TLS loop
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
    s_stockChartProgress = 0;  // TLS + http.begin
    WiFiClientSecure tls;
    tls.setCACert(YAHOO_FINANCE_ROOT_CA);
    HTTPClient http;
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.stock", "chart http.begin failed");
        r.ok = false; r.errorCode = -100;
    } else {
        http.addHeader("User-Agent", "Mozilla/5.0");
        http.useHTTP10(true);
        s_stockChartProgress = 1;  // GET in flight
        unsigned long t0 = millis();
        int code = http.GET();
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
    tls.setCACert(TELETEXT_NOS_ROOT_CA);
    HTTPClient http;
    http.useHTTP10(true);
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.teletext", "http.begin failed page=%u", page);
        portENTER_CRITICAL_SAFE(&s_teletextMux);
        s_teletextState.lastHttpCode = -1;
        portEXIT_CRITICAL_SAFE(&s_teletextMux);
        spotifyTask::tlsResume();
        return;
    }
    unsigned long t0 = millis();
    int code = http.GET();
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
static DynamicJsonDocument s_heatmapDoc(2560);

// --- webradio state ----------------------------------------------------------

static portMUX_TYPE           s_webRadioMux        = portMUX_INITIALIZER_UNLOCKED;
static WebRadioStationsResult s_webRadioResult;
static bool                   s_webRadioNew         = false;
static char                   s_pendingCountry[4]   = "NL";
static portMUX_TYPE           s_pendingCountryMux   = portMUX_INITIALIZER_UNLOCKED;

// Pre-allocated: 100 stations × ~115 B filtered JSON ≈ 11.5 kB; 14336 gives headroom.
static DynamicJsonDocument s_webRadioDoc(14336);

static const char* kRadioBrowserMirrors[3] = {
    "de1.api.radio-browser.info",
    "nl1.api.radio-browser.info",
    "at1.api.radio-browser.info",
};

static void fetchHeatmapQuote() {
    // TASK-131: stop Spotify's TLS connection before allocating our own.
    // Spotify's persistent session holds ~40 k of heap; at steady state
    // maxAlloc ≈ 39 k — not enough for a new Yahoo Finance TLS handshake
    // (~50–70 k). tlsYield() blocks until the spotify task has called
    // client.stop(); tlsResume() (below) releases it to reconnect.
    spotifyTask::tlsYield();
    LOG_HEAP("dataTask.stock");   // after Spotify TLS freed — expect maxBlk ≥ 50k

    WiFiClientSecure tls;
    tls.setCACert(YAHOO_FINANCE_ROOT_CA);
    HTTPClient http;
    if (!http.begin(tls, HEATMAP_URL)) {
        LOG_W("dataTask.stock", "heatmap http.begin failed");
        HeatmapQuoteResult r; r.ok = false; r.errorCode = -100;
        portENTER_CRITICAL_SAFE(&s_heatmapMux);
        s_heatmapResult = r; s_heatmapNew = true;
        portEXIT_CRITICAL_SAFE(&s_heatmapMux);
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
    int code = http.GET();
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
    s_stockChartProgress = 0;  // TLS + http.begin
    LOG_HEAP("dataTask.stock");
    WiFiClientSecure tls;
    tls.setCACert(YAHOO_FINANCE_ROOT_CA);
    HTTPClient http;
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.stock", "chart-sym http.begin failed sym=%s", symbol);
        r.ok = false; r.errorCode = -100;
    } else {
        http.addHeader("User-Agent", "Mozilla/5.0");
        http.useHTTP10(true);
        s_stockChartProgress = 1;  // GET in flight
        unsigned long t0 = millis();
        int code = http.GET();
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

static void fetchWebRadioStations() {
    char country[4];
    portENTER_CRITICAL_SAFE(&s_pendingCountryMux);
    strlcpy(country, s_pendingCountry, sizeof(country));
    portEXIT_CRITICAL_SAFE(&s_pendingCountryMux);

    // tlsYield() stops spotifyTask and waits up to 90 s for its ack. With
    // Spotify's SO_RCVTIMEO capped at 15 s, worst-case blocking is 60 s
    // (two API calls each with one retry). After the ack the shared TLS
    // session is freed (~50 KB), giving the local WiFiClientSecure below
    // enough contiguous heap for its own handshake.
    spotifyTask::tlsYield();
    LOG_HEAP("dataTask.webradio");

    // Reset result in-place; dataTask is sole writer — no lock needed for the fill.
    s_webRadioResult        = WebRadioStationsResult{};
    strlcpy(s_webRadioResult.countryCode, country, sizeof(s_webRadioResult.countryCode));

    bool fetchDone = false;
    for (int mi = 0; mi < 3 && !fetchDone; mi++) {
        char url[128];
        snprintf(url, sizeof(url),
            "https://%s/json/stations/search"
            "?countrycode=%s&codec=MP3&hidebroken=true&order=votes&limit=100",
            kRadioBrowserMirrors[mi], country);

        WiFiClientSecure tls;
        tls.setCACert(RADIO_BROWSER_ROOT_CA);
        HTTPClient http;
        http.useHTTP10(true);
        if (!http.begin(tls, url)) {
            LOG_W("dataTask.webradio", "http.begin failed mirror=%d", mi);
            s_webRadioResult.lastHttpCode = -1;
            continue;
        }
        http.addHeader("User-Agent", "ESPSpotify/1.0");
        unsigned long t0 = millis();
        int code = http.GET();
        s_webRadioResult.lastHttpCode = code;
        LOG_D("dataTask.webradio", "GET mirror=%d %d elapsed=%lums",
              mi, code, (unsigned long)(millis() - t0));
        if (code != 200) {
            LOG_W("dataTask.webradio", "http %d mirror=%d", code, mi);
            http.end();
            continue;
        }

        // Filter: extract only 3 fields per array element.
        // [0]["field"]=true pattern applies to all array elements in ArduinoJson v6.
        StaticJsonDocument<128> filter;
        filter[0]["name"]         = true;
        filter[0]["url_resolved"] = true;
        filter[0]["bitrate"]      = true;
        s_webRadioDoc.clear();
        DeserializationError err = deserializeJson(s_webRadioDoc, http.getStream(),
                                       DeserializationOption::Filter(filter));
        http.end();
        if (err) {
            LOG_W("dataTask.webradio", "JSON err mirror=%d: %s", mi, err.c_str());
            continue;
        }

        s_webRadioResult.count = 0;
        for (JsonVariantConst entry : s_webRadioDoc.as<JsonArrayConst>()) {
            if (s_webRadioResult.count >= 100) break;
            const char* name = entry["name"].as<const char*>();
            const char* urlr = entry["url_resolved"].as<const char*>();
            if (!name || !urlr || !urlr[0]) continue;
            uint8_t idx = s_webRadioResult.count;
            strlcpy(s_webRadioResult.stations[idx].name, name,
                    sizeof(s_webRadioResult.stations[0].name));
            strlcpy(s_webRadioResult.stations[idx].url,  urlr,
                    sizeof(s_webRadioResult.stations[0].url));
            s_webRadioResult.stations[idx].bitrate = entry["bitrate"].as<uint16_t>();
            s_webRadioResult.count++;
        }
        s_webRadioResult.ok = true;
        fetchDone = true;
        LOG_D("dataTask.webradio", "ok mirror=%d country=%s count=%u",
              mi, country, s_webRadioResult.count);
    }

    // Brief spinlock — only marks the flag, not the 15 kB struct copy.
    portENTER_CRITICAL_SAFE(&s_webRadioMux);
    s_webRadioNew = true;
    portEXIT_CRITICAL_SAFE(&s_webRadioMux);

    spotifyTask::tlsResume();
    LOG_HEAP("dataTask.webradio");
}

// --- task body ---------------------------------------------------------------

static void taskBody(void *) {
    LOG_I("dataTask", "task started stack=%uB", (unsigned)kStackBytes);
    for (;;) {
        Request req;
        BaseType_t got = xQueueReceive(s_queue, &req, portMAX_DELAY);
        if (got != pdTRUE) continue;
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
            default: break;
        }
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

void enqueue(FetchType type) {
    if (!s_queue) return;
    Request req = { (uint8_t)type };
    if (xQueueSend(s_queue, &req, 0) != pdTRUE) {
        LOG_W("dataTask", "queue full — dropped type=%d", (int)type);
    }
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

void enqueueWebRadioStations(const char* countryCode) {
    if (!s_queue || !countryCode || !countryCode[0]) return;
    portENTER_CRITICAL_SAFE(&s_pendingCountryMux);
    strlcpy(s_pendingCountry, countryCode, sizeof(s_pendingCountry));
    portEXIT_CRITICAL_SAFE(&s_pendingCountryMux);
    Request req = {}; req.type = DATA_FETCH_WEBRADIO_STATIONS;
    if (xQueueSend(s_queue, &req, 0) != pdTRUE)
        LOG_W("dataTask", "queue full — dropped webradio stations country=%s", countryCode);
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

}  // namespace dataTask
