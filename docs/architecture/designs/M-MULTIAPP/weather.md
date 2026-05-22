# M-MULTIAPP — Weather App Design

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md)
> Source reference: `resource/5in1/5in1 cyberdeck CYD 2.8inch.txt` — `runWeather()` / `updateWeather()`

---

## Source algorithm

```cpp
// --- globals ---
float cTemp = 0, cHum = 0, cWind = 0;
unsigned long lastDataFetch = 0;
String LAT = "41.03";
String LON = "21.33";

void updateWeather() {
  HTTPClient http;
  http.begin("https://api.open-meteo.com/v1/forecast?latitude="+LAT+"&longitude="+LON+
             "&current=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=auto");
  if (http.GET() == 200) {
    JsonDocument doc; deserializeJson(doc, http.getString());
    cTemp = doc["current"]["temperature_2m"];
    cHum  = doc["current"]["relative_humidity_2m"];
    cWind = doc["current"]["wind_speed_10m"];
  }
  http.end();
}

void runWeather() {
  if (modeChanged) {
    tft.fillScreen(TFT_BLACK); tft.drawRect(0, 0, 240, 25, 0x07FF);
    tft.setTextColor(0xFFFF); tft.drawCentreString("CYBER WEATHER HUD", 120, 5, 1);
    tft.drawRoundRect(5,   30, 112, 140, 8, 0xF81F);   // TIME     (pink)
    tft.drawRoundRect(122, 30, 112, 140, 8, 0xFFE0);   // TEMP     (yellow)
    tft.drawRoundRect(5,  175, 112, 140, 8, 0x07FF);   // HUMIDITY (cyan)
    tft.drawRoundRect(122,175, 112, 140, 8, 0x07E0);   // WIND     (green)
    tft.setTextColor(0xF81F); tft.drawCentreString("TIME",     61,  35, 2);
    tft.setTextColor(0xFFE0); tft.drawCentreString("TEMP",    178,  35, 2);
    tft.setTextColor(0x07FF); tft.drawCentreString("HUMIDITY", 61, 180, 2);
    tft.setTextColor(0x07E0); tft.drawCentreString("WIND",    178, 180, 2);
    tft.setTextColor(0xFFE0); tft.drawCentreString(String(cTemp,1)+"C",  178, 90, 4);
    tft.setTextColor(0x07FF); tft.drawCentreString(String((int)cHum)+"%",  61,240, 4);
    tft.setTextColor(0x07E0); tft.drawCentreString(String(cWind,1),       178,240, 4);
    tft.drawCentreString("km/h", 178, 290, 2);
    modeChanged = false;
  }
  struct tm ti;
  if (getLocalTime(&ti)) {
    static int lsec = -1;
    if (ti.tm_sec != lsec) {
      tft.fillRect(10, 75, 102, 60, TFT_BLACK);
      char tS[6]; strftime(tS, 6, "%H:%M", &ti);
      tft.setTextColor(0xF81F); tft.drawCentreString(tS, 61, 100, 4);
      int32_t rssi = WiFi.RSSI(); int bars = (rssi>-50)?4:(rssi>-70)?3:(rssi>-85)?2:1;
      for (int i=0;i<4;i++) tft.fillRect(210+(i*6),18-(i*3),4,(i*3)+3,(i<bars)?0x07E0:0x3186);
      lsec = ti.tm_sec;
    }
  }
}
```

Source portrait layout (240×320), including a 25 px header bar:

| Panel | Rect | Centre x | Value y |
|-------|------|----------|---------|
| TIME (pink) | x=5, y=30, w=112, h=140 | 61 | 100 |
| TEMP (yellow) | x=122, y=30, w=112, h=140 | 178 | 90 |
| HUMIDITY (cyan) | x=5, y=175, w=112, h=140 | 61 | 240 |
| WIND (green) | x=122, y=175, w=112, h=140 | 178 | 240+290 |

RSSI bars drawn in header (x=210..228, y=6..18) every second alongside time.

---

## Location

Hemel Hempstead, UK:

```cpp
#define WEATHER_LAT  "51.75"     // 51.7526° N
#define WEATHER_LON  "-0.47"     // 0.4692° W
#define WEATHER_TZ   "Europe/London"   // explicit — handles BST/GMT correctly
```

Replaces source's hardcoded `LAT="41.03"`, `LON="21.33"` (Macedonia).

API URL (adapted):
```
https://api.open-meteo.com/v1/forecast
  ?latitude=51.75&longitude=-0.47
  &current=temperature_2m,relative_humidity_2m,wind_speed_10m
  &timezone=Europe/London
```

`timezone=Europe/London` preferred over `timezone=auto` — fixes timezone for a
device without GPS, ensures NTP-derived local time matches the API response.

---

## Landscape adaptation

Canvas: **275×124 sub-canvas** (y:116..239). Weather is a data display — Winamp
chrome stays visible above. No header bar needed (Winamp chrome already
identifies the device).

### Panel geometry

```
x=0          x=138        x=274
┌────────────┬────────────┐  y=116
│  TIME      │  TEMP      │
│  HH:MM     │  XX.X°C    │  top row h=62
│       [==] │            │  RSSI top-right of canvas
└────────────┴────────────┘  y=178  (1 px gap)
┌────────────┬────────────┐  y=179
│  HUMIDITY  │  WIND      │
│  XX%       │  XX.X      │  bottom row h=60
│            │  km/h      │
└────────────┴────────────┘  y=239
```

Verification:
- Columns: left w=137 (0..137), right w=136 (138..274). Gap 1 px at x=137..138.
- Rows: top h=62 (116..178), bottom h=60 (179..239). Gap 1 px at y=178..179.
- Total height: 62 + 1 + 60 = **123 px + 1 gap = 124 ✓**
- Right edge: 138 + 136 = **274 ✓**
- Bottom edge: 179 + 60 = **239 ✓**

Panel centres:
- Left col: x = 0 + 137/2 = **68**
- Right col: x = 138 + 136/2 = **206**
- Top row: y = 116 + 62/2 = **147**
- Bottom row: y = 179 + 60/2 = **209**

### Chrome draw calls (landscape)

```cpp
void weatherDrawChrome() {
    // TIME — top-left, pink
    tft.drawRoundRect(0,   116, 137, 62, 5, 0xF81F);
    // TEMP — top-right, yellow
    tft.drawRoundRect(138, 116, 136, 62, 5, 0xFFE0);
    // HUMIDITY — bottom-left, cyan
    tft.drawRoundRect(0,   179, 137, 60, 5, 0x07FF);
    // WIND — bottom-right, green
    tft.drawRoundRect(138, 179, 136, 60, 5, 0x07E0);

    // Labels — same colours as source, font 2
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xF81F); tft.drawString("TIME",     68,  120, 2);
    tft.setTextColor(0xFFE0); tft.drawString("TEMP",    206,  120, 2);
    tft.setTextColor(0x07FF); tft.drawString("HUMIDITY", 68,  183, 2);
    tft.setTextColor(0x07E0); tft.drawString("WIND",    206,  183, 2);
}
```

### Weather value repaint

Called once on init and again whenever `dataTask` delivers new data:

```cpp
void repaintWeatherValues(const WeatherAppState &s) {
    tft.setTextDatum(MC_DATUM);

    // TEMP — top-right panel, value centred at (206, 147)
    tft.fillRect(143, 131, 126, 34, TFT_BLACK);   // clear value area
    tft.setTextColor(0xFFE0, TFT_BLACK);
    String tempStr = (s.lastDataFetch == 0) ? "---" : String(s.cTemp, 1) + "C";
    tft.drawString(tempStr, 206, 147, 4);

    // HUMIDITY — bottom-left panel, value centred at (68, 209)
    tft.fillRect(5, 193, 127, 34, TFT_BLACK);
    tft.setTextColor(0x07FF, TFT_BLACK);
    String humStr = (s.lastDataFetch == 0) ? "---" : String((int)s.cHum) + "%";
    tft.drawString(humStr, 68, 209, 4);

    // WIND — bottom-right panel, value centred at (206, 204), unit at 222
    tft.fillRect(143, 193, 126, 46, TFT_BLACK);
    tft.setTextColor(0x07E0, TFT_BLACK);
    String windStr = (s.lastDataFetch == 0) ? "---" : String(s.cWind, 1);
    tft.drawString(windStr, 206, 204, 4);
    tft.drawString("km/h", 206, 222, 2);
}
```

`"---"` shown before the first successful fetch — avoids displaying 0.0°C on
a cold boot.

### Per-second time update

```cpp
void repaintWeatherTime() {
    struct tm ti;
    if (!getLocalTime(&ti)) return;
    static int lsec = -1;
    if (ti.tm_sec == lsec) return;
    lsec = ti.tm_sec;

    // Clear time value area within TIME panel
    tft.fillRect(5, 131, 127, 34, TFT_BLACK);
    char tS[6]; strftime(tS, 6, "%H:%M", &ti);
    tft.setTextColor(0xF81F, TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(tS, 68, 147, 4);   // centred in TIME panel

    // RSSI bars — top-right corner of canvas (inside TEMP panel border)
    int32_t rssi = WiFi.RSSI();
    int bars = (rssi > -50) ? 4 : (rssi > -70) ? 3 : (rssi > -85) ? 2 : 1;
    for (int i = 0; i < 4; i++) {
        tft.fillRect(249 + (i * 6), 128 - ((i * 3) + 3), 4, (i * 3) + 3,
                     (i < bars) ? 0x07E0 : 0x3186);
    }
    // Bar positions: x=249,255,261,267. Heights 3,6,9,12px. Bottom y=128.
    // Tallest bar top: 128-12=116. All within TEMP panel (x=138..274, y=116..178) ✓
}
```

### repaintApp(Weather)

```cpp
void repaintWeather(WeatherAppState &s) {
    tft.fillRect(0, 116, 275, 124, TFT_BLACK);   // clear sub-canvas only
    weatherDrawChrome();
    repaintWeatherValues(s);
    repaintWeatherTime();   // draws current time immediately, no wait
}
```

---

## Data fetch integration

Source fetches every 60 s in `loop()` regardless of mode. In the shell,
fetch is driven by `dataTask` (see `app-lifecycle.md`):

- `initAppState(Weather)`: if `s.lastDataFetch == 0`, post `DATA_FETCH_WEATHER`
  to `dataTask` queue immediately.
- `weatherTick()`: if `millis() - s.lastDataFetch > 60000`, post fetch request.
- `dataTask` fetches, parses, writes result under spinlock.
- `weatherTick()` reads result under spinlock; if data changed, calls
  `repaintWeatherValues(s)`.

Fetch interval: 60 s (unchanged from source). Open-Meteo free tier imposes no
hard rate limit at this interval.

---

## appTick integration

```cpp
void weatherTick(WeatherAppState &s) {
    // Data staleness check
    if (s.lastDataFetch == 0 || millis() - s.lastDataFetch > 60000) {
        dataTask::enqueue(DATA_FETCH_WEATHER);
        s.lastDataFetch = millis();   // prevent re-queuing until result lands
    }
    // Check for new data under spinlock
    DataResult result;
    if (dataTask::pollWeather(&result)) {
        s.cTemp = result.cTemp;
        s.cHum  = result.cHum;
        s.cWind = result.cWind;
        s.lastDataFetch = millis();
        repaintWeatherValues(s);
    }
    // Per-second time/RSSI update
    repaintWeatherTime();
}
```

---

## State

```cpp
struct WeatherAppState {
    float cTemp, cHum, cWind;
    unsigned long lastDataFetch;   // 0 = never fetched
};
```

On `restoreAppState(Weather)`: call `repaintWeather(s)` — chrome + cached
values paint immediately. If `lastDataFetch != 0`, data is still valid
(shows last known values). Fetch triggers in `weatherTick` if stale.

---

## Touch input

No weather-specific touch response. Taps fall through without action — weather
is read-only.

---

## Constants

```cpp
#define WEATHER_LAT            "51.75"
#define WEATHER_LON            "-0.47"
#define WEATHER_TZ             "Europe/London"
#define WEATHER_FETCH_MS       60000UL    // 60 s fetch interval

// Panel geometry
#define WX_LEFT_X              0
#define WX_LEFT_W              137
#define WX_RIGHT_X             138
#define WX_RIGHT_W             136
#define WX_TOP_Y               116
#define WX_TOP_H               62
#define WX_BOT_Y               179
#define WX_BOT_H               60
#define WX_LEFT_CX             68     // left col MC_DATUM centre x
#define WX_RIGHT_CX            206    // right col MC_DATUM centre x
#define WX_TOP_CY              147    // top row MC_DATUM centre y
#define WX_BOT_CY              209    // bottom row MC_DATUM centre y
#define WX_LABEL_TOP_Y         120    // label y for top panels
#define WX_LABEL_BOT_Y         183    // label y for bottom panels
#define WX_WIND_UNIT_Y         222    // "km/h" y
#define WX_RSSI_X0             249    // leftmost RSSI bar x
#define WX_RSSI_BOTTOM         128    // RSSI bar bottom y
```

---

## Open questions

None. Location fixed to Hemel Hempstead. Panel geometry calculated. All
lifecycle paths covered.

---

## Exit criteria

- **C1** — Chrome panels rendered within sub-canvas (x:0..274, y:116..239).
  Right edge: 138+136=274 ✓. Bottom: 179+60=239 ✓.
- **C2** — `"---"` shown for all three values before first successful fetch.
- **C3** — Time updates every second; RSSI bars refresh alongside.
- **C4** — After fetch completes, new values appear within one `weatherTick()`
  call. `"---"` replaced by real data.
- **C5** — App switch: Spotify → Weather → Spotify. Winamp chrome pixel-correct;
  no weather panel residue above y=116.
- **C6** — Restore: cached values shown immediately; fetch re-triggered if
  >60 s stale.
- **C7** — `timezone=Europe/London` produces correct HH:MM for both GMT (winter)
  and BST (summer). Verify around a DST boundary if possible.
