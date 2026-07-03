// wifiDiag — TASK-274 implementation. See wifiDiag.h.
#include "wifiDiag.h"
#include <WiFi.h>
#include <stdio.h>
#ifdef SERIAL_DEBUG
#include <esp_wifi.h>
#include <string.h>
#endif

namespace wifiDiag {

volatile uint32_t discCount     = 0;
volatile uint8_t  lastDiscReason = 0;
volatile uint32_t lastDiscMs    = 0;
volatile uint32_t lastGotIpMs   = 0;

// Flap guard (design §3.1 / QM OQ1 condition): a pathological AP must not
// storm the serial log. Budget of events per rolling minute; excess is
// counted and summarized when the window rolls.
static constexpr uint8_t  kMaxLinesPerMin = 10;
static uint32_t s_winStartMs  = 0;
static uint8_t  s_winLines    = 0;
static uint32_t s_suppressed  = 0;

static const char* evName(WiFiEvent_t ev) {
    switch (ev) {
        case ARDUINO_EVENT_WIFI_STA_START:        return "STA_START";
        case ARDUINO_EVENT_WIFI_STA_STOP:         return "STA_STOP";
        case ARDUINO_EVENT_WIFI_STA_CONNECTED:    return "STA_CONNECTED";
        case ARDUINO_EVENT_WIFI_STA_DISCONNECTED: return "STA_DISCONNECTED";
        case ARDUINO_EVENT_WIFI_STA_GOT_IP:       return "STA_GOT_IP";
        case ARDUINO_EVENT_WIFI_STA_LOST_IP:      return "STA_LOST_IP";
        case ARDUINO_EVENT_WIFI_STA_AUTHMODE_CHANGE: return "STA_AUTHMODE";
        default:                                  return "EV";
    }
}

static void onEvent(WiFiEvent_t ev, WiFiEventInfo_t info) {
    const uint32_t now = millis();

    // Counters update unconditionally — the flap guard limits LINES, never data.
    if (ev == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
        discCount      = discCount + 1;
        lastDiscReason = info.wifi_sta_disconnected.reason;
        lastDiscMs     = now;
    } else if (ev == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
        lastGotIpMs = now;
    }

    // Rolling-minute line budget.
    if (now - s_winStartMs >= 60000UL) {
        if (s_suppressed) {
            char sbuf[64];
            snprintf(sbuf, sizeof(sbuf), "[wifi-ev] t=%lu suppressed=%lu\n",
                     (unsigned long)now, (unsigned long)s_suppressed);
            Serial.print(sbuf);   // single write — no line tearing (VE-8)
        }
        s_winStartMs = now;
        s_winLines   = 0;
        s_suppressed = 0;
    }
    if (s_winLines >= kMaxLinesPerMin) { s_suppressed++; return; }
    s_winLines++;

    // Assemble the full line in one buffer, emit with ONE write (VE-8: the
    // handler runs on the WiFi event task; interleaved printf tears lines).
    char buf[112];
    if (ev == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
        snprintf(buf, sizeof(buf), "[wifi-ev] t=%lu ev=%d %s reason=%u\n",
                 (unsigned long)now, (int)ev, evName(ev),
                 (unsigned)info.wifi_sta_disconnected.reason);
    } else if (ev == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
        snprintf(buf, sizeof(buf), "[wifi-ev] t=%lu ev=%d %s ip=%s\n",
                 (unsigned long)now, (int)ev, evName(ev),
                 IPAddress(info.got_ip.ip_info.ip.addr).toString().c_str());
    } else {
        snprintf(buf, sizeof(buf), "[wifi-ev] t=%lu ev=%d %s\n",
                 (unsigned long)now, (int)ev, evName(ev));
    }
    Serial.print(buf);
}

void begin() {
    s_winStartMs = millis();
    WiFi.onEvent(onEvent);
}

#ifdef SERIAL_DEBUG
// ── TASK-282: promiscuous beacon watcher ─────────────────────────────────────

BeaconStats beaconStats = {};

static bool     s_watchActive = false;
static uint8_t  s_bssid[6]    = {};
// Pending gap event, written in the promiscuous callback (WiFi task), drained
// by poll() (loop task). Single-slot latest-wins — same volatile discipline as
// the Phase-1 counters; a lost intermediate gap line is acceptable, the
// gapsOver1s counter never misses.
static volatile uint32_t s_pendGapMs  = 0;
static volatile uint32_t s_pendAtMs   = 0;
static volatile bool     s_pendFlag   = false;

static void promiscCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (type != WIFI_PKT_MGMT) return;
    const wifi_promiscuous_pkt_t* p = (const wifi_promiscuous_pkt_t*)buf;
    const uint8_t* fr = p->payload;
    // Beacon: type/subtype 0x80 (mgmt, subtype 8). addr3 = BSSID at offset 16.
    if (fr[0] != 0x80) return;
    if (memcmp(fr + 16, s_bssid, 6) != 0) {
        beaconStats.otherMgmt = beaconStats.otherMgmt + 1;
        return;
    }
    const uint32_t now  = millis();
    const uint32_t last = beaconStats.lastMs;
    if (last != 0) {
        const uint32_t gap = now - last;
        if (gap > beaconStats.gapMaxMs) beaconStats.gapMaxMs = gap;
        if (gap > 1000u) {
            beaconStats.gapsOver1s = beaconStats.gapsOver1s + 1;
            s_pendGapMs = gap;
            s_pendAtMs  = now;
            s_pendFlag  = true;
        }
    }
    beaconStats.lastMs     = now;
    beaconStats.count      = beaconStats.count + 1;
    beaconStats.lastRssi   = p->rx_ctrl.rssi;
    beaconStats.noiseFloor = p->rx_ctrl.noise_floor;
}

bool beaconWatchStart() {
    if (WiFi.status() != WL_CONNECTED) return false;
    memcpy(s_bssid, WiFi.BSSID(), 6);
    memset((void*)&beaconStats, 0, sizeof(beaconStats));
    s_pendFlag = false;
    wifi_promiscuous_filter_t filt = { .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT };
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_promiscuous_rx_cb(&promiscCb);
    esp_wifi_set_promiscuous(true);
    s_watchActive = true;
    return true;
}

void beaconWatchStop() {
    esp_wifi_set_promiscuous(false);
    esp_wifi_set_promiscuous_rx_cb(nullptr);
    s_watchActive = false;
}

bool beaconWatchActive() { return s_watchActive; }

void poll() {
    if (!s_pendFlag) return;
    s_pendFlag = false;
    char buf[96];
    snprintf(buf, sizeof(buf), "[beacon] t=%lu gap=%lums rssi=%ld nf=%ld\n",
             (unsigned long)s_pendAtMs, (unsigned long)s_pendGapMs,
             (long)beaconStats.lastRssi, (long)beaconStats.noiseFloor);
    Serial.print(buf);   // single write — same no-tearing rule as [wifi-ev]
}
#endif  // SERIAL_DEBUG

}  // namespace wifiDiag
