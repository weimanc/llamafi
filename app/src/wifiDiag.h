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

#ifdef SERIAL_DEBUG
// TASK-282 (M-WIFI-DIAG Phase 2): frame-level instruments for the H-A/H-C split
// the Phase-1 reason codes can't make (BEACON_TIMEOUT is ambiguous — design §5).
// Debug-build only; production keeps the Phase-1 sensor unchanged.
//
// Beacon watcher: promiscuous-mode management-frame tap, filtered to the
// associated BSSID on the current channel. Per-beacon rx_ctrl gives RSSI and
// the PHY noise floor — evidence at the antenna, below the stack's timeout
// logic. gap events > 1 s are queued in the callback (WiFi task context) and
// printed by poll() from loop context as stable-prefix "[beacon]" lines.
struct BeaconStats {
    volatile uint32_t count;        // beacons from our BSSID since watch start
    volatile uint32_t gapMaxMs;     // max inter-beacon gap observed
    volatile uint32_t gapsOver1s;   // gaps > 1000 ms (≈10 beacon intervals lost)
    volatile uint32_t lastMs;       // millis() of last beacon from our BSSID
    volatile int32_t  lastRssi;     // RSSI of last beacon (dBm)
    volatile int32_t  noiseFloor;   // PHY noise floor of last beacon (dBm)
    volatile uint32_t otherMgmt;    // mgmt frames seen from other BSSIDs (sanity: rx alive)
};
extern BeaconStats beaconStats;

bool beaconWatchStart();  // needs an associated STA (locks to its BSSID); false if not connected
void beaconWatchStop();
bool beaconWatchActive();
void poll();              // print queued [beacon] gap lines — call from loop()
#endif

}  // namespace wifiDiag
