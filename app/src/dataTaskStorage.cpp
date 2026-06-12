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

static portMUX_TYPE  s_cryptoMux   = portMUX_INITIALIZER_UNLOCKED;
static CryptoResult  s_cryptoResult;
static bool          s_cryptoNew   = false;

static portMUX_TYPE    s_stockQuoteMux    = portMUX_INITIALIZER_UNLOCKED;
static StockQuoteResult s_stockQuoteResult;
static bool             s_stockQuoteNew   = false;

static portMUX_TYPE    s_stockChartMux    = portMUX_INITIALIZER_UNLOCKED;
static StockChartResult s_stockChartResult;
static bool             s_stockChartNew   = false;

static portMUX_TYPE       s_heatmapMux    = portMUX_INITIALIZER_UNLOCKED;
static HeatmapQuoteResult s_heatmapResult;
static bool               s_heatmapNew    = false;

constexpr UBaseType_t kStackBytes  = 10 * 1024;
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
    LOG_HEAP("dataTask.weather");
    WiFiClientSecure tls;
    tls.setCACert(OPEN_METEO_ROOT_CA);
    HTTPClient http;
    http.useHTTP10(true);   // force Connection:close so http.end() frees TLS
    if (!http.begin(tls, WEATHER_URL)) {
        LOG_W("dataTask.weather", "http.begin failed");
        return;
    }
    unsigned long t0 = millis();
    int code = http.GET();
    LOG_D("dataTask.weather", "GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    String body;
    if (code == 200) body = http.getString();
    else             LOG_W("dataTask.weather", "http %d", code);
    http.end();             // TLS freed here (HTTP/1.0 close)
    LOG_HEAP("dataTask.weather");
    if (code == 200) {
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

    LOG_HEAP("dataTask.crypto");
    WiFiClientSecure tls;
    tls.setCACert(COINGECKO_ROOT_CA);
    HTTPClient http;
    http.useHTTP10(true);   // force Connection:close so http.end() frees TLS
    if (!http.begin(tls, cryptoUrl)) {
        LOG_W("dataTask.crypto", "http.begin failed");
        spotifyTask::tlsResume();
        return;
    }
    unsigned long t0 = millis();
    int code = http.GET();
    LOG_D("dataTask.crypto", "GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    String body;
    if (code == 200) body = http.getString();
    else             LOG_W("dataTask.crypto", "http %d", code);
    http.end();             // TLS freed here (HTTP/1.0 close)
    spotifyTask::tlsResume();
    LOG_HEAP("dataTask.crypto");
    if (code == 200) {
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
    WiFiClientSecure tls;
    tls.setCACert(YAHOO_FINANCE_ROOT_CA);
    HTTPClient http;
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.stock", "chart http.begin failed");
        r.ok = false; r.errorCode = -100;
    } else {
        http.addHeader("User-Agent", "Mozilla/5.0");
        http.useHTTP10(true);
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
    portENTER_CRITICAL_SAFE(&s_stockChartMux);
    s_stockChartResult = r;
    s_stockChartNew    = true;
    portEXIT_CRITICAL_SAFE(&s_stockChartMux);
    spotifyTask::tlsResume();
}

// Pre-allocated at startup (unfragmented heap) and reused per fetch cycle to avoid
// malloc failure after long-uptime TLS cycling (PROP-004 / EXP-003).
// Capacity: 20 symbols × ~120 B each ≈ 2.4 kB peak usage; 2560 gives headroom.
static DynamicJsonDocument s_heatmapDoc(2560);

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
        unsigned long t0 = millis();
        int code = http.GET();
        LOG_D("dataTask.stock", "chart-sym GET %s %d elapsed=%lums",
              symbol, code, (unsigned long)(millis() - t0));
        if (code != 200) {
            r.ok = false; r.errorCode = code;
            http.end();
        } else {
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
    portENTER_CRITICAL_SAFE(&s_stockChartMux);
    s_stockChartResult = r;
    s_stockChartNew    = true;
    portEXIT_CRITICAL_SAFE(&s_stockChartMux);
    LOG_HEAP("dataTask.stock");
    spotifyTask::tlsResume();
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

}  // namespace dataTask
