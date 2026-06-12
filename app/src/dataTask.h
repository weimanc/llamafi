#pragma once
// dataTask.h — async HTTP fetch task for Weather and Crypto apps (M-MULTIAPP).
// FreeRTOS task queues fetch requests; results written under spinlock.
// Apps call enqueue() when cache is stale; poll*() to consume new data.
// TLS: WiFiClientSecure + hardcoded root CA PEMs per ADR-029.

#include <Arduino.h>

namespace dataTask {

enum FetchType : uint8_t {
    DATA_FETCH_WEATHER          = 0,
    DATA_FETCH_CRYPTO           = 1,
    DATA_FETCH_STOCK_QUOTE      = 2,
    DATA_FETCH_STOCK_CHART      = 3,
    DATA_FETCH_HEATMAP_QUOTE    = 4,
    DATA_FETCH_STOCK_CHART_BY_SYM = 5,
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

// Copy latest result into *out; returns true if new data since last poll.
// Caller must supply a valid pointer. Thread-safe (spinlock).
bool pollWeather(WeatherResult *out);
bool pollCrypto(CryptoResult *out);
int  lastCryptoHttpCode();  // last HTTP response code from CoinGecko (0 = never fetched)
bool pollStockQuote(StockQuoteResult *out);
bool pollStockChart(StockChartResult *out);
bool pollHeatmapQuote(HeatmapQuoteResult *out);

void configureStockTickers(const char tickers[8][8]);
void configureCrypto(const char ids[6][16], const char* ccy);

}  // namespace dataTask
