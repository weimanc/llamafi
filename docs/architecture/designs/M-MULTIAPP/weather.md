# M-MULTIAPP — Weather App Design

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md)
> Source reference: `resource/5in1/5in1 cyberdeck CYD 2.8inch.txt` — `runWeather()` / `updateWeather()`

---

## Source algorithm

**Data fetch** (`updateWeather()`, called every 60 s in `loop()`):
```cpp
http.begin("https://api.open-meteo.com/v1/forecast?latitude="+LAT+
           "&longitude="+LON+"&current=temperature_2m,relative_humidity_2m,
           wind_speed_10m&timezone=auto");
// parses: cTemp (float), cHum (float), cWind (float)
```

**Render** (`runWeather()`):
- Static chrome drawn once on `modeChanged`: header bar + 4 rounded rect panels.
- Time panel (top-left) updates every second via `lsec` guard.
- Temp / Humidity / Wind panels: static after initial draw (update only on next fetch).

Portrait layout (240×320):

| Panel | Position | Size | Content |
|-------|----------|------|---------|
| Header | x=0, y=0 | 240×25 | "CYBER WEATHER HUD" |
| Time | x=5, y=30 | 112×140 | HH:MM, big font |
| Temp | x=122, y=30 | 112×140 | °C |
| Humidity | x=5, y=175 | 112×140 | % |
| Wind | x=122, y=175 | 112×140 | km/h |

2×2 grid of panels, each with a label + value.

---

## Landscape adaptation

Canvas: **275×124 sub-canvas** (y:116..239) — Weather is a data display, not
a full-screen visual effect. Winamp chrome stays visible above.

At 275×124 the 2×2 panel grid fits comfortably:

```
x=0        x=138      x=275
+----------+----------+  y=116
| TEMP     | HUMIDITY |
| XX.X°C   | XX%      |  y=178
+----------+----------+
| WIND     | TIME     |
| XX.X km/h| HH:MM    |  y=240
+----------+----------+
```

Each panel: ~137×62 px. Header bar "CYBER WEATHER HUD" either omitted
(Winamp chrome above already identifies the device) or drawn as a single
line at y=116 before the panels.

Coordinates, label text, and value text sizing port from source — only the
absolute y positions shift by +116 and the panel dimensions scale down.

---

## Data fetch integration

Source fetched in `loop()` unconditionally every 60 s regardless of current mode.
In the shell: fetch is driven by `dataTask` (see `app-lifecycle.md`) when
Weather app is active, or on a background timer. `WeatherAppState.lastDataFetch`
tracks staleness.

API endpoint, JSON parse logic, and LAT/LON configuration port verbatim.
LAT/LON must be configurable (not hardcoded) — add to `configFile.h` schema
or a `#define` in a config header. Current source hardcodes them.

---

## State

```cpp
struct WeatherAppState {
    float cTemp, cHum, cWind;
    unsigned long lastDataFetch;
};
```

On `restoreAppState(Weather)`: repaint chrome + panels from cached state
immediately. If `lastDataFetch == 0`, trigger a fetch before first paint.

---

## Open questions

1. **LAT/LON configuration** — hardcoded in source. Must be user-configurable
   for a general-purpose device. Add to SPIFFS config (`configFile.h`) or
   expose via WiFiManager captive portal.
2. **Panel layout** — 2×2 proposed above. Confirm label/value font sizes
   fit 137×62 panels on physical display.
3. **Header bar** — include or omit in sub-canvas layout?
