// wifiDiag — TASK-274 implementation. See wifiDiag.h.
#include "wifiDiag.h"
#include <WiFi.h>
#include <stdio.h>

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

}  // namespace wifiDiag
