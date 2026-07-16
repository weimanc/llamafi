# Design — Time & Location Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04 (updated 2026-06-05 — whiteboard decisions applied; updated 2026-06-06 — implementation audit; naming, sort order, picker layout corrected to match impl)
> Part of: M-MULTIAPP Settings (`time` tab)
> See also: [settings.md](settings.md)
> **Note (TASK-327, 2026-07-16):** the city-picker scrollbar step arrows are now drawn/
> hit-tested via the settings widget kit's `SButton` (at the scrollbar's own 18×20
> rects — same coordinates, so tap geometry below is still accurate).

## Whiteboard decisions (2026-06-05)

| Topic | Decision |
|-------|----------|
| Struct | No separate `TimeSettings` — use `g_settings` (AppSettings) directly. `SettingsStorage::save()` covers persistence. |
| Lat/lon | Dropped — no weather app; location fields not needed in UI. `lat`/`lon` remain in AppSettings for future use but are not exposed in TimeSection. |
| Timezone picker | Dropped — timezone always follows city selection. |
| City scroll | Right-side scrollbar (18 px strip) with ▲/▼ tap buttons; 6 city rows visible per page. |

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
    int8_t      utcHours;  //  0  (UTC offset hours, signed)
    int8_t      utcMins;   //  0  (UTC offset minutes, 0 or 30 or 45)
    bool        groupBreak;// true = draw separator above this row in picker
};

static const CityEntry kCities[];       // defined in cities.h (flash)
static const uint8_t   kCityCount;      // derived from array size (~82 cities)
```

Selecting a city in the city picker auto-fills **all three**: lat, lon, and
timezone. The user can manually override lat/lon afterwards (e.g. to use their
exact coordinates rather than the city centre) without changing the timezone.

Memory: ~82 cities × ~100 bytes ≈ 8–10 KB in flash. Acceptable.

---

## Tab content layout

The `time` tab uses the list-row pattern with two section headers.
Lat/lon dropped (no weather app). Timezone picker dropped (follows city).

```
+-----------------------------------+
|  Location                         |   section header (22 px)
|  City           London         >  |   → city picker; S_CHEVRON
|  ─────────────────────────────── |
|  Clock & Date                     |   section header (22 px)
|  Timezone       Europe/London     |   read-only, follows city; S_VALUE (cyan)
|  Clock          24h               |   cycle: 12h ↔ 24h
|  Date           DD/MM/YYYY        |   cycle: DMY → MDY → YMD → DMY
+-----------------------------------+
```

5 content rows + 2 section headers = 5×26 + 2×22 = 174 px — fits 212 px panel.

City row has `>` chevron. Timezone row is read-only display (no chevron, no tap).

---

## City picker (secondary view)

Replaces the content panel while active. Header shows "Select city" + `< back`.
Sorted **east-to-west by UTC offset** (UTC+12 first, UTC−10 last); within each
UTC group, by population. A 1px separator line (`S_SEP`) divides UTC groups
(`groupBreak` field). Current city highlighted in `S_VALUE_ON`. UTC offset
column (e.g. `"+9"`, `"-5:30"`) rendered left of a vertical separator at x=50;
city name at x=58; country at x=246.

```
+----+------------------------------+--+
| +9 | Tokyo        JP   (current) |▲ |   scrollbar strip (x=257..274)
|    | Seoul        KR              |  |
├────┼──────────────────────────────┤  |   groupBreak separator
| +8 | Beijing      CN              |░░|   thumb proportional to list position
|    | Singapore    SG              |  |
|    | Perth        AU              |  |
|    |                              |▼ |
+----+------------------------------+--+
```

**Scrollbar geometry** (right strip, x=257..274, 18 px wide):

| Zone | y range | Action |
|------|---------|--------|
| ▲ button | `S_CONTENT_Y .. S_CONTENT_Y+20` | `_cityOffset--` (clamped) |
| ▼ button | `220..240` | `_cityOffset++` (clamped) |
| Thumb track | between | no tap action in Phase 1 |

6 city rows visible per page (S_CONTENT_H / S_ROW_H = 8, minus 2 for buttons = 6).
City row width clipped to x=0..256 to leave room for scrollbar.

On city tap:
1. Copy `city`, `posixTz`, `tzName`, `lat`, `lon` from `kCities[i]` into `g_settings`.
2. Call `configTzTime(g_settings.posixTz, "pool.ntp.org", "time.google.com", "time.cloudflare.com")`.
3. `saveSettings()`.
4. Return to Main view.

Timezone picker: **dropped** — timezone always follows city selection.

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

## Storage

No separate `TimeSettings` struct or namespace. All fields live in `AppSettings`
(`settingsStorage.h`) and are persisted by `SettingsStorage::save()`.

Relevant `AppSettings` fields:

```cpp
char    posixTz[48];   // "GMT0BST,M3.5.0/1,M10.5.0"
char    tzName[32];    // "Europe/London"
char    city[24];      // "London"
float   lat;           // retained in struct; not exposed in TimeSection UI
float   lon;
bool    fmt24h;
DateFmt dateFmt;
```

`SettingsStorage::load()` called in `setup()` before `configTzTime()`.

---

## Boot sequence

```cpp
// main.cpp::setup() — replace configTime() block:
SettingsStorage::load();
configTzTime(g_settings.posixTz,
             "pool.ntp.org", "time.google.com", "time.cloudflare.com");
// ... NTP sync wait (unchanged) ...
```

---

## TimeSection class sketch

```cpp
// app/src/settings/timeSection.h

enum class TimeView : uint8_t { Main, CityPicker };

class TimeSection : public SettingsSection {
public:
    const char* title() const override {
        return (_view == TimeView::CityPicker) ? "Select city" : "Time & Location";
    }

    void enter() override {
        _view       = TimeView::Main;
        _cityOffset = 0;
        repaint();
    }

    void leave() override {}   // no async; nothing to cancel

    void tick() override {}    // purely reactive; no polling needed

    void repaint() override {
        drawHeader();
        clearContent();
        (_view == TimeView::Main) ? repaintMain() : repaintCityPicker();
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return SectionResult::Continue;

        if (isBackTap(x, y)) {
            if (_view == TimeView::CityPicker) {
                _view = TimeView::Main;
                repaint();
                return SectionResult::Continue;
            }
            return SectionResult::GoBack;
        }

        if (_view == TimeView::Main)       _handleMainTap(x, y);
        else                               _handlePickerTap(x, y);
        return SectionResult::Continue;
    }

private:
    // ---- State ---------------------------------------------------------------
    TimeView _view       = TimeView::Main;
    uint8_t  _cityOffset = 0;   // top visible city index in picker

    static constexpr uint8_t kPickerRows = 6;   // visible rows (8 - 2 for scroll buttons)

    // ---- Scrollbar geometry (right strip) ------------------------------------
    static constexpr int16_t kSbX     = 257;   // scrollbar left edge
    static constexpr int16_t kSbW     =  18;   // scrollbar width
    static constexpr int16_t kSbUpY0  = S_CONTENT_Y;
    static constexpr int16_t kSbUpY1  = S_CONTENT_Y + 20;
    static constexpr int16_t kSbDnY0  = 220;
    static constexpr int16_t kSbDnY1  = 240;
    static constexpr int16_t kRowW    = 256;   // city row width (leaves room for scrollbar)

    // ---- Main view -----------------------------------------------------------

    void repaintMain() {
        // Section header: Location
        int y = drawRows(nullptr, 0, "Location");   // draws sub-header, returns y after it

        // City row with chevron
        char cityVal[26];
        strlcpy(cityVal, g_settings.city[0] ? g_settings.city : "None", sizeof(cityVal));
        drawChevronRow(y, "City");
        // overwrite value with actual city name (drawChevronRow draws ">"; redraw value col)
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(S_VALUE);
        tft.drawString(cityVal, S_COL_VALUE - 14, y + S_ROW_H / 2, 2);
        tft.setTextDatum(TL_DATUM);
        y += S_ROW_H;

        drawSep(y); y += 4;

        // Section header: Clock & Date
        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(S_SUBHDR);
        tft.drawString("Clock & Date", S_COL_LABEL, y + 4, 2);
        tft.drawFastHLine(S_COL_LABEL, y + S_ROW_HDR_H - 1, S_CANVAS_W - S_COL_LABEL, S_SEP);
        y += S_ROW_HDR_H;

        // Timezone row (read-only)
        drawRow(y, { "Timezone",
                     g_settings.tzName[0] ? g_settings.tzName : "UTC",
                     S_LABEL, S_VALUE });
        y += S_ROW_H;

        // Clock format row
        drawRow(y, { "Clock",
                     g_settings.fmt24h ? "24h" : "12h",
                     S_LABEL, S_VALUE_ON });
        y += S_ROW_H;

        // Date format row
        static const char* kDateFmtStr[] = { "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD" };
        drawRow(y, { "Date",
                     kDateFmtStr[(int)g_settings.dateFmt],
                     S_LABEL, S_VALUE_ON });
    }

    void _handleMainTap(int x, int y) {
        (void)x;
        // City row: y in S_CONTENT_Y + S_ROW_HDR_H .. +S_ROW_H
        int cityRowY = S_CONTENT_Y + S_ROW_HDR_H;
        if (y >= cityRowY && y < cityRowY + S_ROW_H) {
            _view = TimeView::CityPicker;
            repaint();
            return;
        }

        // Rows below sep + "Clock & Date" header:
        int baseY = cityRowY + S_ROW_H + 4 + S_ROW_HDR_H;   // after sep (4px) + header

        // Timezone row (baseY): read-only — no tap
        // Clock row (baseY + S_ROW_H):
        if (y >= baseY + S_ROW_H && y < baseY + 2 * S_ROW_H) {
            g_settings.fmt24h = !g_settings.fmt24h;
            saveSettings();
            repaint();
            return;
        }
        // Date row (baseY + 2*S_ROW_H):
        if (y >= baseY + 2 * S_ROW_H && y < baseY + 3 * S_ROW_H) {
            g_settings.dateFmt = (DateFmt)(((int)g_settings.dateFmt + 1) % 3);
            saveSettings();
            repaint();
        }
    }

    // ---- City picker view ----------------------------------------------------

    void repaintCityPicker() {
        _drawScrollbar();
        int y = S_CONTENT_Y;
        uint8_t end = min((int)_cityOffset + kPickerRows, (int)kCityCount);
        for (uint8_t i = _cityOffset; i < end; i++) {
            bool current = (strncmp(kCities[i].city, g_settings.city,
                                    sizeof(g_settings.city)) == 0);
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(S_LABEL);
            // clip text to kRowW to avoid overwriting scrollbar
            tft.drawString(kCities[i].city, S_COL_LABEL, y + S_ROW_H / 2, 2);
            tft.setTextDatum(MR_DATUM);
            tft.setTextColor(current ? S_VALUE_ON : S_VALUE_OFF);
            tft.drawString(kCities[i].country, kRowW - 4, y + S_ROW_H / 2, 2);
            tft.setTextDatum(TL_DATUM);
            y += S_ROW_H;
        }
    }

    void _handlePickerTap(int px, int py) {
        // Scrollbar taps
        if (px >= kSbX) {
            if (py >= kSbUpY0 && py < kSbUpY1 && _cityOffset > 0) {
                _cityOffset--;
                repaintCityPicker();
            } else if (py >= kSbDnY0 && py < kSbDnY1 &&
                       _cityOffset + kPickerRows < kCityCount) {
                _cityOffset++;
                repaintCityPicker();
            }
            return;
        }

        // City row tap
        int row = (py - S_CONTENT_Y) / S_ROW_H;
        if (row < 0 || row >= kPickerRows) return;
        uint8_t idx = _cityOffset + (uint8_t)row;
        if (idx >= kCityCount) return;

        _selectCity(idx);
    }

    void _selectCity(uint8_t idx) {
        strlcpy(g_settings.city,     kCities[idx].city,     sizeof(g_settings.city));
        strlcpy(g_settings.tzName,   kCities[idx].tzName,   sizeof(g_settings.tzName));
        strlcpy(g_settings.posixTz,  kCities[idx].posixTz,  sizeof(g_settings.posixTz));
        g_settings.lat = kCities[idx].lat;
        g_settings.lon = kCities[idx].lon;
        configTzTime(g_settings.posixTz,
                     "pool.ntp.org", "time.google.com", "time.cloudflare.com");
        saveSettings();
        _view = TimeView::Main;
        repaint();
    }

    // ---- Scrollbar -----------------------------------------------------------

    void _drawScrollbar() {
        // Background strip
        tft.fillRect(kSbX, S_CONTENT_Y, kSbW, S_CONTENT_H, S_SEP);

        // ▲ button
        tft.fillRect(kSbX, kSbUpY0, kSbW, 20, S_BG);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString("^", kSbX + kSbW / 2, kSbUpY0 + 10, 2);

        // ▼ button
        tft.fillRect(kSbX, kSbDnY0, kSbW, 20, S_BG);
        tft.drawString("v", kSbX + kSbW / 2, kSbDnY0 + 10, 2);
        tft.setTextDatum(TL_DATUM);

        // Thumb (proportional, skips arrow zones)
        int trackY0 = kSbUpY1 + 2;
        int trackH  = kSbDnY0 - trackY0 - 2;
        if (kCityCount > kPickerRows && trackH > 0) {
            int thumbH = max(8, trackH * kPickerRows / kCityCount);
            int thumbY = trackY0 + (_cityOffset * (trackH - thumbH))
                         / (kCityCount - kPickerRows);
            tft.fillRect(kSbX + 3, thumbY, kSbW - 6, thumbH, S_VALUE);
        }
    }
};
```

### Design notes

- **Single file, two views.** `TimeView::Main` and `TimeView::CityPicker` are internal sub-views. `< back` from CityPicker returns to Main (not GoBack) — the section is never truly dismissed from the picker.
- **Tap Y math in `_handleMainTap`.** Row positions are derived from the same y-accumulation as `repaintMain()` — no `tapToRow()` because the layout has mixed-height elements (section headers 22 px, rows 26 px, sep 4 px). Explicit y-range checks are used instead.
- **Scrollbar hides when list fits.** `_drawScrollbar()` draws the thumb only when `kCityCount > kPickerRows`. ▲/▼ buttons always draw but `_handlePickerTap` clamps offsets so they're no-ops at the limits.
- **`configTzTime()` side effect.** Calling it at runtime changes the active tz immediately — `getLocalTime()` in ClockApp will reflect the new timezone on the next tick. No reboot needed.
- **`kCityCount` / `kCities[]`** are declared `extern` in a `cities.h` header (see §City / timezone data). The array lives in flash (`PROGMEM` if needed for size).

## Open questions

1. **City list completeness** — ~50 cities covers major metros. If a user's
   city is absent, the previous selection is preserved. Adding cities requires
   reflash (array is in flash). A "custom entry" (free-text city + manual tz)
   is deferred — requires KeyboardWidget.
2. **NTP server** — hardcoded to `pool.ntp.org` / `time.google.com` /
   `time.cloudflare.com`. Corporate networks may block these. Expose as an
   advanced row if needed — deferred.
3. **Offline timezone apply** — `configTzTime()` can be called before NTP
   sync; the tz rule applies to whatever time is currently set (build-epoch
   fallback). Correct behaviour — no guard needed.
4. ~~**Scrollbar thumb drag**~~ RESOLVED 2026-06-06: Drag implemented via
   pointer-capture pattern (TASK-153). Press on thumb track (y between `kSbUpY1`
   and `kSbDnY0`) captures; Move updates `_cityOffset` proportionally with
   rounding; Release commits and clears drag. ▲/▼ button taps still work on
   Release. `_sbDragging` flag ensures Move events captured even if finger
   drifts left of scrollbar strip.

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

---

## Implementation Status (audit 2026-06-06)

| Area | Status | Notes |
|------|--------|-------|
| Main view (Location/Clock sections, all rows) | ✅ DONE | |
| City picker: 6-row scroll, scrollbar, ▲/▼ | ✅ DONE | |
| City picker: thumb drag (TASK-153) | ✅ DONE | `_sbDragging` flag + pointer capture |
| `_selectCity()` writes all fields + `configTzTime()` | ✅ DONE | |
| 12h/24h cycle, date format DMY/MDY/YMD cycle | ✅ DONE | |
| Naming: `kCities[]` / `kCityCount` | ✅ DONE | Spec updated — was `g_cities`/`g_cityCount` |
| Sort order: east-to-west by UTC offset | ✅ DONE | Spec updated — was alphabetical |
| UTC offset column + group separators | ✅ DONE | Spec updated — additive enhancement |
| C3/C4 — 12h display in `drawTime()` | ⚠ UNVERIFIED | Lives in `main.cpp`; not in `timeSection.h` |
| C6/C7 — boot-time `configTzTime()` | ⚠ UNVERIFIED | Lives in `main.cpp::setup()` |
