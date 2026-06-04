# Design — Time & Location Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04
> Part of: M-MULTIAPP Settings (`time` tab)
> See also: [settings.md](settings.md), [keyboard-widget.md](keyboard-widget.md)

---

## Context / pain points

The current implementation has three hard-coded limitations:

1. **No timezone.** `configTime(0, 0, ...)` syncs to UTC. The clock app
   displays UTC regardless of the user's location.
2. **No DST.** There is no automatic daylight-saving transition.
3. **Format locked.** `drawTime()` uses 24h snprintf; `drawDate()` uses
   `DD/MM/YYYY` — both in `main.cpp` with no runtime switch.

---

## Goals

1. User selects their city from a predefined list → lat/lon and timezone
   auto-populated.
2. DST transitions handled automatically — no manual toggle required.
3. 12h / 24h clock format switchable at runtime.
4. Date format switchable: `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD`.
5. All values persisted to SPIFFS; applied at next boot via `configTzTime()`.

---

## DST — automatic via POSIX timezone string

`configTzTime(const char* tz, ...)` (ESP32 Arduino `<time.h>`) accepts a
POSIX timezone rule string. DST transition dates and clock-change rules are
encoded directly in the string — no separate toggle is needed.

```cpp
// Replace in main.cpp::setup():
// Before:
configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");

// After:
configTzTime(g_timeSettings.posixTz,
             "pool.ntp.org", "time.google.com", "time.cloudflare.com");
```

`getLocalTime(&t)` then returns local time with DST already applied.
`t.tm_isdst` is 1 during DST, 0 otherwise — available if needed for display.

POSIX string examples:

| Location | POSIX string |
|----------|-------------|
| London | `GMT0BST,M3.5.0/1,M10.5.0` |
| New York | `EST5EDT,M3.2.0,M11.1.0` |
| Los Angeles | `PST8PDT,M3.2.0,M11.1.0` |
| Berlin | `CET-1CEST,M3.5.0,M10.5.0/3` |
| Sydney | `AEST-10AEDT,M10.1.0,M4.1.0/3` |
| UTC | `UTC0` |

Default if no setting persisted: `UTC0`.

---

## City / timezone data

A `const CityEntry[]` array in flash covers ~50 cities. Each entry encodes
city name, country, lat/lon, POSIX timezone string, and display timezone name.

```cpp
struct CityEntry {
    const char* city;      // "London"
    const char* country;   // "GB"
    float       lat;       //  51.5074
    float       lon;       //  -0.1278
    const char* posixTz;   // "GMT0BST,M3.5.0/1,M10.5.0"
    const char* tzName;    // "Europe/London"
};

extern const CityEntry g_cities[];
extern const uint8_t   g_cityCount;   // ~50
```

Selecting a city in the city picker auto-fills **all three**: lat, lon, and
timezone. The user can manually override lat/lon afterwards (e.g. to use their
exact coordinates rather than the city centre) without changing the timezone.

Memory: 50 cities × ~80 bytes = ~4 KB in flash. Acceptable.

---

## Tab content layout

The `time` tab uses the list-row pattern from
[settings.md §List-row content pattern](settings.md) with two section headers.

```
+-----------------------------------+
|  Location                         |   section header
|  City           London         >  |   → city picker (secondary list)
|  Latitude       51.50°         >  |   → keyboard (numeric, optional override)
|  Longitude      -0.12°         >  |   → keyboard (numeric, optional override)
|  ─────────────────────────────── |
|  Clock & Date                     |   section header
|  Timezone       Europe/London  >  |   → timezone picker (secondary list)
|  Clock          24h               |   → cycle: 12h ↔ 24h
|  Date           DD/MM/YYYY        |   → cycle: DMY → MDY → YMD → DMY
+-----------------------------------+
```

8 rows × 26px = 208px — fits within the 212px content panel.

`>` indicator on rows that open a secondary view. Cycle-on-tap rows show
the current value only.

---

## City picker (secondary list)

Same secondary-list pattern as the `app` tab submenu. Replaces the content
panel while active; `< back` returns to the main time tab.

```
+-----------------------------------+
|  < time         Select city       |
+-----------------------------------+
|  Amsterdam   NL                   |
|  Berlin      DE                   |
|  London      GB         (current) |
|  Los Angeles US                   |
|  New York    US                   |
|  Paris       FR                   |
|  Sydney      AU                   |
|  Tokyo       JP                   |
|  ...                              |
+-----------------------------------+
```

List sorted alphabetically by city name. Current city highlighted with
`SETTINGS_VALUE_ON` (green) on the right column.

On tap: set `g_timeSettings.city`, `lat`, `lon`, `posixTz`, `tzName`.
Call `configTzTime(posixTz, ...)` immediately to apply at runtime without
reboot. Write to SPIFFS. Return to main time tab.

---

## Timezone picker (secondary list)

Available if the user wants a timezone that differs from the auto-selected
city timezone (unusual but possible — e.g. a device in one timezone displaying
another city's time for weather). Shows the same city list filtered to unique
timezones, or a flat list of POSIX timezone names.

On tap: updates `posixTz` and `tzName` only (lat/lon unchanged).
Calls `configTzTime(posixTz, ...)` immediately.

---

## 12h / 24h format

Cycle-on-tap. Stored as `fmt24h: true/false`.

**Clock app changes — `drawTime()` (`main.cpp:255`):**

```cpp
void drawTime() {
    struct tm t;
    if (!getLocalTime(&t)) return;
    char tBuf[12];
    bool colon = (t.tm_sec % 2 == 0);
    if (g_timeSettings.fmt24h) {
        snprintf(tBuf, sizeof(tBuf), colon ? "%02d:%02d" : "%02d %02d",
                 t.tm_hour, t.tm_min);
        tft.drawString(tBuf, 137, 45, 6);
    } else {
        int h12 = t.tm_hour % 12;
        if (h12 == 0) h12 = 12;
        snprintf(tBuf, sizeof(tBuf), colon ? "%2d:%02d" : "%2d %02d",
                 h12, t.tm_min);
        tft.drawString(tBuf, 120, 45, 6);          // shift left to make room
        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(0xBDD7, TFT_BLACK);
        tft.drawString(t.tm_hour < 12 ? "AM" : "PM", 224, 38, 2);  // small, top-right
    }
}
```

12h mode uses font 6 for the digits (same as 24h) but shifts the x position
left to make room for the `AM`/`PM` label rendered at font 2 in the top-right
of the time cell. No font size change needed.

---

## Date format

Three formats, cycle-on-tap. Stored as `dateFmt: "DMY" | "MDY" | "YMD"`.

| Value | Format | Example |
|-------|--------|---------|
| `DMY` | `DD/MM/YYYY` | `04/06/2026` |
| `MDY` | `MM/DD/YYYY` | `06/04/2026` |
| `YMD` | `YYYY-MM-DD` | `2026-06-04` |

**Clock app changes — `drawDate()` (`main.cpp:278`):**

```cpp
void drawDate() {
    struct tm t;
    if (!getLocalTime(&t)) return;
    const char* days[] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
    tft.drawString(days[t.tm_wday], 137, 170, 4);
    char dBuf[16];
    int d = t.tm_mday, m = t.tm_mon + 1, y = t.tm_year + 1900;
    switch (g_timeSettings.dateFmt) {
        case DateFmt::MDY: snprintf(dBuf, sizeof(dBuf), "%02d/%02d/%04d", m, d, y); break;
        case DateFmt::YMD: snprintf(dBuf, sizeof(dBuf), "%04d-%02d-%02d", y, m, d); break;
        default:           snprintf(dBuf, sizeof(dBuf), "%02d/%02d/%04d", d, m, y); break;
    }
    tft.drawString(dBuf, 137, 200, 4);
}
```

---

## Persistence — `/settings.json` schema (time section)

```json
{
  "time": {
    "posixTz":  "GMT0BST,M3.5.0/1,M10.5.0",
    "tzName":   "Europe/London",
    "city":     "London",
    "lat":       51.5074,
    "lon":       -0.1278,
    "fmt24h":    true,
    "dateFmt":  "DMY"
  }
}
```

Defaults (if key absent):

| Field | Default |
|-------|---------|
| `posixTz` | `"UTC0"` |
| `tzName` | `"UTC"` |
| `city` | `""` (none selected) |
| `lat` | `0.0` |
| `lon` | `0.0` |
| `fmt24h` | `true` |
| `dateFmt` | `"DMY"` |

---

## TimeSettings struct

```cpp
enum class DateFmt : uint8_t { DMY = 0, MDY = 1, YMD = 2 };

struct TimeSettings {
    char    posixTz[48];   // POSIX tz string, e.g. "GMT0BST,M3.5.0/1,M10.5.0"
    char    tzName[32];    // display name, e.g. "Europe/London"
    char    city[24];      // selected city, e.g. "London"
    float   lat;
    float   lon;
    bool    fmt24h;
    DateFmt dateFmt;
};

extern TimeSettings g_timeSettings;

namespace TimeSettingsStorage {
    void load();           // reads /settings.json["time"] → g_timeSettings
    void save();           // writes g_timeSettings → /settings.json["time"]
    void applyTz();        // calls configTzTime(g_timeSettings.posixTz, ...)
}
```

`TimeSettingsStorage::load()` called in `setup()` before `configTzTime()`.
`TimeSettingsStorage::applyTz()` also called immediately on timezone change
(city tap or timezone picker tap) to apply without reboot.

---

## Boot sequence

```cpp
// main.cpp::setup() — replace configTime() block:
TimeSettingsStorage::load();
TimeSettingsStorage::applyTz();     // configTzTime(posixTz, ntp1, ntp2, ntp3)
// ... NTP sync wait (unchanged) ...
```

---

## State struct (TimeFlow)

```cpp
enum class TimeFlowView : uint8_t {
    Main, CityPicker, TimezonePicker
};

struct TimeFlowState {
    TimeFlowView view = TimeFlowView::Main;
    uint8_t      cityScroll;      // top visible city index
    uint8_t      tzScroll;        // top visible timezone index
};
```

---

## Open questions

1. **City list completeness** — ~50 cities covers major metros. If a user's
   city is absent, they fall back to manual lat/lon + timezone picker.
   The city list is a `const` array in flash — adding entries requires
   reflash. Consider a future "custom city" entry that stores a name +
   lat/lon + tz manually.
2. **Lat/lon precision** — `float` (6–7 sig figs) is sufficient for weather
   API calls. Store as `float` in the struct; JSON with 4 decimal places.
3. **NTP server** — currently hardcoded to `pool.ntp.org` / `time.google.com`
   / `time.cloudflare.com`. Expose as an advanced row if needed (corporate
   networks). Deferred.
4. **Offline timezone apply** — `configTzTime()` can be called before NTP
   sync; the tz rule applies to whatever time is currently set (even the
   build-epoch fallback). This is correct behaviour — no guard needed.

---

## Exit criteria

- **C1** — Selecting a city writes `posixTz`, `lat`, `lon` to SPIFFS and
  calls `configTzTime()` immediately; clock app reflects new timezone on
  next `drawTime()` call.
- **C2** — DST transitions happen automatically — no manual interaction
  required. Verified by setting tz to a DST-observing region and checking
  `tm_isdst` flag after simulated transition.
- **C3** — 12h mode: time displays as `H:MM AM/PM`; AM/PM label visible
  without overlapping digit area.
- **C4** — 24h mode: time displays as `HH:MM` (unchanged from current).
- **C5** — Date format cycles correctly through all three variants; displayed
  date matches `struct tm` fields.
- **C6** — Settings survive `ESP.restart()`; `configTzTime()` re-applied on
  boot from persisted `posixTz`.
- **C7** — Default (no SPIFFS entry): UTC, 24h, DMY — identical to current
  behaviour.
