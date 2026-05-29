// dataTaskStorage.cpp — FreeRTOS task body + HTTP fetch for Weather / Crypto.
// Implements the dataTask namespace declared in dataTask.h.
// Pattern mirrors spotifyTask: queue + spinlock-protected result structs.
// TLS: per ADR-029 each fetch stack-allocates a WiFiClientSecure, calls
// setCACert(), then passes it to http.begin(client, url). No persistent
// TLS connection; 60 s cadence makes setup overhead negligible.

#include "dataTask.h"
#include "dataTaskCerts.h"
#include "logSink.h"

#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <esp_heap_caps.h>

namespace dataTask {

// --- internal types ----------------------------------------------------------

struct Request { uint8_t type; uint8_t param0; uint8_t param1; };

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

constexpr UBaseType_t kStackBytes  = 10 * 1024;
constexpr UBaseType_t kPriority    = 1;
constexpr BaseType_t  kPinnedCpu   = APP_CPU_NUM;

static const char WEATHER_URL[] =
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=51.75&longitude=-0.47"
    "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
    "&timezone=Europe/London";

static const char CRYPTO_URL[] =
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum,binancecoin,solana,ripple,cardano"
    "&vs_currencies=usd&include_24hr_change=true";

static const char* CRYPTO_IDS[] = {
    "bitcoin","ethereum","binancecoin","solana","ripple","cardano"
};

static const char* STOCK_TICKERS[8]      = {"AAPL","AMD","AMZN","ARM","GOOG","META","MSFT","NVDA"};
static const char* STOCK_RANGE_STR[4]    = {"1d","5d","1mo","ytd"};
static const char* STOCK_INTERVAL_STR[4] = {"5m","60m","1d","1wk"};
static const char  STOCK_URL_BASE[]      = "https://query1.finance.yahoo.com/v8/finance/chart/";

// --- fetch functions ---------------------------------------------------------

static void fetchWeather() {
    WiFiClientSecure tls;
    tls.setCACert(OPEN_METEO_ROOT_CA);
    HTTPClient http;
    if (!http.begin(tls, WEATHER_URL)) {
        LOG_W("dataTask.weather", "http.begin failed");
        return;
    }
    unsigned long t0 = millis();
    int code = http.GET();
    LOG_D("dataTask.weather", "GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    if (code == 200) {
        DynamicJsonDocument doc(1024);
        DeserializationError err = deserializeJson(doc, http.getStream());
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
    } else {
        LOG_W("dataTask.weather", "http %d", code);
    }
    http.end();
}

static void fetchCrypto() {
    WiFiClientSecure tls;
    tls.setCACert(COINGECKO_ROOT_CA);
    HTTPClient http;
    if (!http.begin(tls, CRYPTO_URL)) {
        LOG_W("dataTask.crypto", "http.begin failed");
        return;
    }
    unsigned long t0 = millis();
    int code = http.GET();
    LOG_D("dataTask.crypto", "GET %d elapsed=%lums", code, (unsigned long)(millis() - t0));
    if (code == 200) {
        DynamicJsonDocument doc(2048);
        DeserializationError err = deserializeJson(doc, http.getStream());
        if (!err) {
            CryptoResult r;
            r.ok = true;
            for (int i = 0; i < 6; i++) {
                r.prices[i]  = doc[CRYPTO_IDS[i]]["usd"].as<float>();
                r.changes[i] = doc[CRYPTO_IDS[i]]["usd_24h_change"].as<float>();
            }
            portENTER_CRITICAL_SAFE(&s_cryptoMux);
            s_cryptoResult = r;
            s_cryptoNew    = true;
            portEXIT_CRITICAL_SAFE(&s_cryptoMux);
            LOG_D("dataTask.crypto", "ok btc=%.0f eth=%.0f", r.prices[0], r.prices[1]);
        } else {
            LOG_W("dataTask.crypto", "JSON parse error: %s", err.c_str());
        }
    } else {
        LOG_W("dataTask.crypto", "http %d", code);
    }
    http.end();
}

static void fetchStockQuote() {
    StockQuoteResult r;
    r.ok = true;
    for (int i = 0; i < 8 && r.ok; i++) {
        String url = String(STOCK_URL_BASE) + STOCK_TICKERS[i] + "?interval=1d&range=1d";
        WiFiClientSecure tls;
        tls.setCACert(YAHOO_FINANCE_ROOT_CA);
        HTTPClient http;
        if (!http.begin(tls, url)) {
            LOG_W("dataTask.stock", "http.begin failed sym=%s", STOCK_TICKERS[i]);
            r.ok = false; r.errorCode = -1;
            break;
        }
        unsigned long t0 = millis();
        int code = http.GET();
        LOG_D("dataTask.stock", "quote GET %s %d elapsed=%lums",
              STOCK_TICKERS[i], code, (unsigned long)(millis() - t0));
        if (code != 200) {
            r.ok = false; r.errorCode = code;
            http.end();
            break;
        }
        DynamicJsonDocument doc(8192);
        DeserializationError err = deserializeJson(doc, http.getStream());
        http.end();
        if (err) {
            LOG_W("dataTask.stock", "JSON err sym=%s: %s", STOCK_TICKERS[i], err.c_str());
            r.ok = false; r.errorCode = -99;
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
}

static void fetchStockChart(uint8_t tickerIdx, uint8_t rangeIdx) {
    if (tickerIdx >= 8 || rangeIdx >= 4) return;
    String url = String(STOCK_URL_BASE) + STOCK_TICKERS[tickerIdx]
                 + "?interval=" + STOCK_INTERVAL_STR[rangeIdx]
                 + "&range="    + STOCK_RANGE_STR[rangeIdx];
#ifdef SERIAL_DEBUG
    LOG_D("dataTask.stock", "chart START %s range=%s heap_free=%u heap_min=%u",
          STOCK_TICKERS[tickerIdx], STOCK_RANGE_STR[rangeIdx],
          heap_caps_get_free_size(MALLOC_CAP_8BIT),
          heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT));
#endif
    StockChartResult r;
    WiFiClientSecure tls;
    tls.setCACert(YAHOO_FINANCE_ROOT_CA);
    HTTPClient http;
    if (!http.begin(tls, url)) {
        LOG_W("dataTask.stock", "chart http.begin failed");
        r.ok = false; r.errorCode = -1;
    } else {
        unsigned long t0 = millis();
        int code = http.GET();
        LOG_D("dataTask.stock", "chart GET %s range=%s %d elapsed=%lums",
              STOCK_TICKERS[tickerIdx], STOCK_RANGE_STR[rangeIdx],
              code, (unsigned long)(millis() - t0));
        if (code != 200) {
            r.ok = false; r.errorCode = code;
            http.end();
        } else {
#ifdef SERIAL_DEBUG
            LOG_D("dataTask.stock", "chart pre-json heap_free=%u",
                  heap_caps_get_free_size(MALLOC_CAP_8BIT));
#endif
            DynamicJsonDocument doc(16384);
            DeserializationError err = deserializeJson(doc, http.getStream());
            http.end();
#ifdef SERIAL_DEBUG
            LOG_D("dataTask.stock", "chart post-json heap_free=%u err=%s",
                  heap_caps_get_free_size(MALLOC_CAP_8BIT), err.c_str());
#endif
            if (err) {
                LOG_W("dataTask.stock", "chart JSON err: %s", err.c_str());
                r.ok = false; r.errorCode = -99;
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
}

// --- task body ---------------------------------------------------------------

static void taskBody(void *) {
    LOG_I("dataTask", "task started stack=%uB", (unsigned)kStackBytes);
    for (;;) {
        Request req;
        BaseType_t got = xQueueReceive(s_queue, &req, portMAX_DELAY);
        if (got != pdTRUE) continue;
        switch (req.type) {
            case DATA_FETCH_WEATHER:     fetchWeather(); break;
            case DATA_FETCH_CRYPTO:      fetchCrypto();  break;
            case DATA_FETCH_STOCK_QUOTE: fetchStockQuote(); break;
            case DATA_FETCH_STOCK_CHART: fetchStockChart(req.param0, req.param1); break;
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
    Request req = { (uint8_t)DATA_FETCH_STOCK_CHART, tickerIdx, rangeIdx };
    if (xQueueSend(s_queue, &req, 0) != pdTRUE)
        LOG_W("dataTask", "queue full — dropped stock chart idx=%u rng=%u", tickerIdx, rangeIdx);
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

}  // namespace dataTask
