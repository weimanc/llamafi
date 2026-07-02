// wifiDiag — TASK-274 (M-WIFI-DIAG Phase 1): WiFi link-event ground truth.
//
// One WiFi.onEvent handler logs every WiFi event with millis + disconnect
// reason code. Ships in ALL builds (design OQ1: production Spotify polling
// suffers the same outages; field forensics only exist if the sensor ships).
// The "[wifi-ev]" prefix is a STABLE grep contract — harnesses parse it.
//
// begin() MUST run before the first WiFi.begin() or events are missed.
#pragma once
#include <stdint.h>

namespace wifiDiag {

// Counters consumed by the SERIAL_DEBUG `get wifi` accessor (design §3.2).
// Written from the WiFi event task, read from loop — volatile is sufficient
// for these monotonic diagnostics (no compound read-modify-write races that
// matter: worst case a poll sees a half-updated pair one poll early).
extern volatile uint32_t discCount;       // STA_DISCONNECTED events since boot
extern volatile uint8_t  lastDiscReason;  // reason code of the last disconnect
extern volatile uint32_t lastDiscMs;      // millis() of the last disconnect
extern volatile uint32_t lastGotIpMs;     // millis() of the last GOT_IP (outage end bound)

void begin();  // register the event handler — call BEFORE WiFi.begin()

}  // namespace wifiDiag
