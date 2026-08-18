#pragma once
// apps/weatherApp.h — WeatherApp, moved verbatim out of main.cpp (M-SRCLAYOUT).
// Pure move: no logic change, no reordering.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "util/timeFmt.h"

// ── WeatherApp (weather.md) ───────────────────────────────────────────
#define WEATHER_FETCH_MS  60000UL
#define WX_LEFT_CX   68
#define WX_RIGHT_CX 206
#define WX_TOP_CY    60   // top row MC_DATUM centre y  (y:0..119)
#define WX_BOT_CY   180   // bottom row MC_DATUM centre y (y:121..239)

class WeatherApp : public App {
public:
  void init() override {
    repaintWeather();
    enqueueWx();   // WIRE2-G4: coords from settings, snapshotted at enqueue
    _s.lastDataFetch = millis();
  }
  void resume()  override {
    // WIRE2-G4 resume-diff (StockApp pattern): coords changed in Settings
    // while we were away → zero the fetch timestamp so the next tick
    // refetches immediately with the new location.
    if (g_settings.lat != _cfgLat || g_settings.lon != _cfgLon)
      _s.lastDataFetch = 0;
    repaintWeather();
  }
  void suspend() override {}
  void tick()    override { weatherTick(); }
  bool handleInput(TouchPhase, int, int) override { return false; }
  // TASK-518 (P4): NO hasInFlightOp() override, deliberately. Weather has
  // async work, but it holds NO member that expresses "a fetch is in flight" —
  // weatherTick() enqueues on a 60 s cadence and consumes whatever
  // pollWeather() hands back; _s.lastDataFetch is a timestamp, not a pending
  // flag. The in-flight fact lives entirely in dataTask, which is why `get
  // idle` counts the dataTask queue as its own term: a weather fetch in flight
  // shows up there (dataq/inFlight), not here. Inheriting the App default
  // (== hasPendingAsync() == false) is therefore honest for the app-level term
  // rather than a gap. Adding a _wxPending bool was considered and rejected:
  // it would have to be cleared by a poll that only fires on delivery, so a
  // dropped result would latch it true until the next cadence tick.
  //
  // isConnecting() NOT reusable: !s_wxDataReady is a never-had-data latch, set
  // once on the first good fetch and never re-armed.
  // TASK-245 / ADR-046: amber "connecting" bar until the first weather fetch lands.
  bool isConnecting() const override { return !s_wxDataReady; }
  // TASK-246: red bar when the last weather fetch failed (cleared on next success).
  bool hasError() const override { return _wxErr; }

private:
  WeatherAppState _s   = {};
  int             _lsec = -1;
  bool            _wxErr = false;
  float           _cfgLat = 0.0f;   // WIRE2-G4: coords snapshotted at each
  float           _cfgLon = 0.0f;   //   enqueue; resume() diffs vs g_settings

  // WIRE2-G4: single enqueue path — snapshot g_settings coords for the
  // resume-diff and hand them to dataTask (which re-snapshots under mux).
  void enqueueWx() {
    _cfgLat = g_settings.lat;
    _cfgLon = g_settings.lon;
    dataTask::enqueueWeather(_cfgLat, _cfgLon);
  }

  void weatherDrawChrome() {
    tft.drawRoundRect(0,   0,   137, 120, 5, 0xF81F);  // TIME,     top-left
    tft.drawRoundRect(138, 0,   137, 120, 5, 0xFFE0);  // TEMP,     top-right
    tft.drawRoundRect(0,   121, 137, 119, 5, 0x07FF);  // HUMIDITY, bottom-left
    tft.drawRoundRect(138, 121, 137, 119, 5, 0x07E0);  // WIND,     bottom-right
    tft.setTextDatum(MC_DATUM);
    // M-HOME-LOCATION §6: title the TIME tile with the selected city when one
    // is set (visible confirmation the coordinate wiring works); "TIME" else.
    // Truncated to the 137px box; OQ3 (label-vs-refined-coords divergence)
    // accepted for v1 by human sign-off.
    char timeLbl[14];
    if (g_settings.city[0]) snprintf(timeLbl, sizeof(timeLbl), "%.12s", g_settings.city);
    else                    strlcpy(timeLbl, "TIME", sizeof(timeLbl));
    tft.setTextColor(0xF81F); tft.drawString(timeLbl,    WX_LEFT_CX,  8,   2);
    tft.setTextColor(0xFFE0); tft.drawString("TEMP",     WX_RIGHT_CX, 8,   2);
    tft.setTextColor(0x07FF); tft.drawString("HUMIDITY", WX_LEFT_CX,  129, 2);
    tft.setTextColor(0x07E0); tft.drawString("WIND",     WX_RIGHT_CX, 129, 2);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void repaintWeatherValues() {
    tft.setTextDatum(MC_DATUM);
    tft.fillRect(143, 20, 126, 90, TFT_BLACK);   // TEMP value area (below label)
    tft.setTextColor(0xFFE0, TFT_BLACK);
    tft.drawString(_s.lastDataFetch ? String(_s.cTemp, 1) + "C" : "---", WX_RIGHT_CX, WX_TOP_CY, 4);
    tft.fillRect(5, 148, 127, 60, TFT_BLACK);    // HUMIDITY value area
    tft.setTextColor(0x07FF, TFT_BLACK);
    tft.drawString(_s.lastDataFetch ? String((int)_s.cHum) + "%" : "---", WX_LEFT_CX, WX_BOT_CY, 4);
    tft.fillRect(143, 148, 126, 75, TFT_BLACK);  // WIND value + unit area
    tft.setTextColor(0x07E0, TFT_BLACK);
    tft.drawString(_s.lastDataFetch ? String(_s.cWind, 1) : "---", WX_RIGHT_CX, 174, 4);
    tft.drawString("km/h", WX_RIGHT_CX, 208, 2);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void repaintWeatherTime() {
    struct tm ti;
    if (!getLocalTime(&ti)) return;
    if (ti.tm_sec == _lsec) return;
    _lsec = ti.tm_sec;
    tft.fillRect(5, 20, 127, 90, TFT_BLACK);    // TIME value area
    // WIRE2-G2: hour via shared helper — 12h drops the leading zero (%d);
    // AM/PM (when 12h) sits under the time, still inside the tile erase rect.
    char tS[8];
    snprintf(tS, sizeof(tS), g_settings.fmt24h ? "%02d:%02d" : "%d:%02d",
             clockHour(ti), ti.tm_min);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xF81F, TFT_BLACK);
    tft.drawString(tS, WX_LEFT_CX, WX_TOP_CY, 4);
    const char* wxAp = clockAmPm(ti);
    if (wxAp) tft.drawString(wxAp, WX_LEFT_CX, WX_TOP_CY + 28, 2);
    int32_t rssi = WiFi.RSSI();
    int bars = (rssi > -50) ? 4 : (rssi > -70) ? 3 : (rssi > -85) ? 2 : 1;
    for (int i = 0; i < 4; i++) {
      tft.fillRect(249 + (i * 6), 14 - ((i * 3) + 3), 4, (i * 3) + 3,
                   (i < bars) ? (uint16_t)0x07E0 : (uint16_t)0x3186);
    }
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void repaintWeather() {
    tft.fillRect(0, 0, 275, 240, TFT_BLACK);
    weatherDrawChrome();
    repaintWeatherValues();
    repaintWeatherTime();
  }

  void weatherTick() {
    if (!_s.lastDataFetch || millis() - _s.lastDataFetch > WEATHER_FETCH_MS) {
      enqueueWx();   // WIRE2-G4: coords from settings, snapshotted at enqueue
      _s.lastDataFetch = millis();
    }
    dataTask::WeatherResult r;
    if (dataTask::pollWeather(&r)) {
      _s.lastDataFetch = millis();
      if (r.ok) {                       // TASK-246: only consume valid data
        _s.cTemp = r.cTemp; _s.cHum = r.cHum; _s.cWind = r.cWind;
        s_wxDataReady = true;
        _wxErr = false;
        repaintWeatherValues();
      } else {
        _wxErr = true;                  // failed fetch → red bar (was silently shown as 0s)
      }
    }
    repaintWeatherTime();
  }
};
