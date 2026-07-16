#pragma once
// timeFmt.h — shared time/date formatting helpers (M-SETTINGS-WIRE2 G2/G3).
//
// One convergence point for every wall-clock render surface (clockApp x4
// styles, weather TIME tile, aquarium overlay) so the 12h/24h and DMY/MDY/YMD
// settings cannot drift between call sites — the exact drift G2/G3 existed to
// kill. Pure functions over g_settings; no state, no tick (design §4-G2:
// "the ADR-050 owner here is the renderer set, the helper keeps them
// convergent").

#include <Arduino.h>
#include <time.h>
#include "../settingsStorage.h"

// Hour respecting g_settings.fmt24h. 24h: tm_hour as-is (0..23).
// 12h contract (W-6, boundaries normative so call sites cannot diverge):
//   0 -> 12 (midnight, AM), 1..11 -> as-is (AM),
//   12 -> 12 (noon, PM), 13..23 -> minus 12 (PM).
inline uint8_t clockHour(const struct tm& t) {
    if (g_settings.fmt24h) return (uint8_t)t.tm_hour;
    uint8_t h = (uint8_t)(t.tm_hour % 12);
    return (h == 0) ? (uint8_t)12 : h;
}

// "AM" for tm_hour 0..11, "PM" for 12..23 (W-6: 00:xx = AM, 12:xx = PM);
// nullptr in 24h mode — callers skip the label entirely.
inline const char* clockAmPm(const struct tm& t) {
    if (g_settings.fmt24h) return nullptr;
    return (t.tm_hour < 12) ? "AM" : "PM";
}

// Date per g_settings.dateFmt: DMY dd/mm/yyyy | MDY mm/dd/yyyy | YMD
// yyyy/mm/dd — 4-digit year, 2-digit day/month, separator configurable
// (clockApp shared date line uses '/', VFD's own line uses '-').
inline void fmtDate(const struct tm& t, char* buf, size_t len, char sep = '/') {
    int d = t.tm_mday, m = t.tm_mon + 1, y = t.tm_year + 1900;
    switch (g_settings.dateFmt) {
        case DateFmt::MDY: snprintf(buf, len, "%02d%c%02d%c%04d", m, sep, d, sep, y); break;
        case DateFmt::YMD: snprintf(buf, len, "%04d%c%02d%c%02d", y, sep, m, sep, d); break;
        case DateFmt::DMY:
        default:           snprintf(buf, len, "%02d%c%02d%c%04d", d, sep, m, sep, y); break;
    }
}
