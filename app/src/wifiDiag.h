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
// Written from the WiFi event task (`arduino_events`, framework-owned,
// priority 19 — M-CONCURRENCY §1's sixth context), read from loop. A lone
// field read (logHeartbeat's discCount, superviseTick's lastDiscMs) is fine
// as a bare volatile — worst case a poll sees a half-updated *pair* one poll
// early, which is the "matters" this comment used to wave away. It does NOT
// cover reading more than one of these as one logical group: `arduino_events`
// runs at priority 19 and can preempt loopTask between any two of these
// reads, so a group read can pair a NEW lastDiscMs with a STALE
// lastDiscReason across a disconnect that lands mid-read (M-CONCURRENCY §5
// G7, TASK-544). Use discSnapshot() for any read that touches more than one
// of these four together.
extern volatile uint32_t discCount;       // STA_DISCONNECTED events since boot
extern volatile uint8_t  lastDiscReason;  // reason code of the last disconnect
extern volatile uint32_t lastDiscMs;      // millis() of the last disconnect
extern volatile uint32_t lastGotIpMs;     // millis() of the last GOT_IP (outage end bound)

// TASK-544 (G7): atomic copy of all four counters above, taken under the
// same portMUX onEvent() writes under — mirrors dataTask's own "portMUX +
// copy into caller storage" pattern (M-CONCURRENCY R5 mechanism 1). Use this
// instead of reading the bare volatiles whenever more than one field is
// consumed together (e.g. `get wifi`'s JSON, which prints all four).
struct DiscSnapshot {
    uint32_t discCount;
    uint8_t  lastDiscReason;
    uint32_t lastDiscMs;
    uint32_t lastGotIpMs;
};
DiscSnapshot discSnapshot();

void begin();  // register the event handler — call BEFORE WiFi.begin()

// TASK-283: link supervisor. The Arduino core's auto-reconnect can wedge after
// a long AP absence (observed twice 2026-07-03: NO_AP_FOUND storm burns out →
// reason=39 → zero further reconnect attempts for 40+ min; reboot-only
// recovery). superviseTick() re-kicks a dead link with WiFi.disconnect()+
// WiFi.begin() — armed after the first GOT_IP this boot, or explicitly via
// superviseArm() when boot found stored credentials but its connect windows
// expired before any GOT_IP (TASK-296: an AP storm at boot time otherwise
// left the device parked forever). A boot with NO credentials stays unarmed
// (never fights the no-credentials settings-UI flow). Kicks only after
// WIFI_SUP_DOWN_MS continuously down, paced at WIFI_SUP_PACE_MS, forever (an
// AP can be absent for hours — the MX5600's 2.4 GHz radio proved it; no
// finite retry budget). Call from loop(); caller suppresses it while the
// Settings app owns the radio. Ships in ALL builds — production parks dead
// without it.
extern volatile uint32_t superviseKicks;   // re-kicks issued since boot
void superviseTick();
void superviseArm();   // TASK-296: arm without a GOT_IP (creds known, boot connect failed)

// TASK-426: candidate list for the supervisor's kicks.
//
// A kick used to be a bare WiFi.begin(). That overload is `get_config →
// set_config → connect` — it reuses whatever STA config is already resident
// and never reloads NVS or the saved list. The boot cascade leaves the LAST
// candidate it tried resident, so when that candidate is a dead SSID (a saved
// network whose AP is gone) every kick re-attacks the dead SSID forever and
// the live AP is never retried — reboot-only recovery even at -58 dBm.
// Observed 2026-08-09: 9+ kicks over 5 min, zero recovery; with the dead entry
// removed the very first kick reconnected in 225 ms.
//
// Registering candidates makes each kick target a real SSID explicitly and
// rotate on to the next one, so no single dead entry can wedge recovery.
// Registration is optional: with none registered the kick falls back to the
// historic bare WiFi.begin().
static constexpr uint8_t kSupMaxCandidates = 6;   // WIFI_MAX_SAVED(5) + /wifi_creds.json
void superviseClearCandidates();
bool superviseAddCandidate(const char* ssid, const char* pass);  // false if full/invalid
uint8_t superviseCandidateCount();

#ifdef SERIAL_DEBUG
// TASK-282 (M-WIFI-DIAG Phase 2): frame-level instruments for the H-A/H-C split
// the Phase-1 reason codes can't make (BEACON_TIMEOUT is ambiguous — design §5).
// Debug-build only; production keeps the Phase-1 sensor unchanged.
//
// Beacon watcher: promiscuous-mode management-frame tap, filtered to the
// associated BSSID on the current channel. Per-beacon rx_ctrl gives RSSI and
// the PHY noise floor — evidence at the antenna, below the stack's timeout
// logic. gap events > 1 s are queued in the callback and printed by poll()
// from loop context as stable-prefix "[beacon]" lines.
//
// TASK-544 (G6): the callback (`promiscCb`) runs on the closed-source WiFi
// driver task — core 0, priority 23 (M-CONCURRENCY §1's sixth context) —
// while every reader here runs on loopTask, core 1. That is a genuine
// cross-core simultaneous access, not a same-core preemption race like every
// other crossing in this file: "safe by scheduling" does not apply even in
// principle. `volatile` alone does not make a seven-field read-modify-write
// atomic across cores. Fields stay `volatile` (debug-build direct reads
// elsewhere are unaffected), but any write in `promiscCb` and any read of
// more than one field together goes through the portMUX below — the same
// M1 mechanism `dataTask`'s own result slots already use.
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
// Atomic copy of every field above, taken under the same portMUX promiscCb
// writes under. Use this instead of reading `beaconStats.*` directly
// whenever more than one field is consumed together (cmdGet.cpp's `get
// beacon`, poll()'s own [beacon] line).
BeaconStats beaconStatsSnapshot();

bool beaconWatchStart();  // needs an associated STA (locks to its BSSID); false if not connected
void beaconWatchStop();
bool beaconWatchActive();
void poll();              // print queued [beacon] gap lines — call from loop()
#endif

}  // namespace wifiDiag
