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

namespace dataTask {

// --- internal types ----------------------------------------------------------

struct Request { uint8_t type; };

// --- module state ------------------------------------------------------------

static QueueHandle_t s_queue       = nullptr;
static TaskHandle_t  s_taskHandle  = nullptr;

static portMUX_TYPE  s_weatherMux  = portMUX_INITIALIZER_UNLOCKED;
static WeatherResult s_weatherResult;
static bool          s_weatherNew  = false;

static portMUX_TYPE  s_cryptoMux   = portMUX_INITIALIZER_UNLOCKED;
static CryptoResult  s_cryptoResult;
static bool          s_cryptoNew   = false;

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
        DeserializationError err = deserializeJson(doc, http.getString());
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
        DeserializationError err = deserializeJson(doc, http.getString());
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

// --- task body ---------------------------------------------------------------

static void taskBody(void *) {
    LOG_I("dataTask", "task started stack=%uB", (unsigned)kStackBytes);
    for (;;) {
        Request req;
        BaseType_t got = xQueueReceive(s_queue, &req, portMAX_DELAY);
        if (got != pdTRUE) continue;
        switch (req.type) {
            case DATA_FETCH_WEATHER: fetchWeather(); break;
            case DATA_FETCH_CRYPTO:  fetchCrypto();  break;
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

}  // namespace dataTask
