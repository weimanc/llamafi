#pragma once
// dataTask.h — async HTTP fetch task for Weather and Crypto apps (M-MULTIAPP).
// FreeRTOS task queues fetch requests; results written under spinlock.
// Apps call enqueue() when cache is stale; poll*() to consume new data.
// TLS: WiFiClientSecure + hardcoded root CA PEMs per ADR-029.

#include <Arduino.h>

namespace dataTask {

enum FetchType : uint8_t {
    DATA_FETCH_WEATHER = 0,
    DATA_FETCH_CRYPTO  = 1,
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

// Spawn the FreeRTOS task. Call once in setup(), after WiFi is connected.
void begin();

// Post a fetch request. Non-blocking (drops if queue full).
void enqueue(FetchType type);

// Copy latest result into *out; returns true if new data since last poll.
// Caller must supply a valid pointer. Thread-safe (spinlock).
bool pollWeather(WeatherResult *out);
bool pollCrypto(CryptoResult *out);

}  // namespace dataTask
