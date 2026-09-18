#pragma once
// apps/weatherApp.h — WeatherApp component (M-SRCLAYOUT Stage E / TASK-471).
// Self-contained per D0/SF.11. Method bodies live in weatherApp.cpp.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <time.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "util/timeFmt.h"

#include "display/tft.h"

#define WEATHER_FETCH_MS  60000UL
#define WX_LEFT_CX   68
#define WX_RIGHT_CX 206
#define WX_TOP_CY    60   // top row MC_DATUM centre y  (y:0..119)
#define WX_BOT_CY   180   // bottom row MC_DATUM centre y (y:121..239)

struct WeatherAppState {
    float         cTemp, cHum, cWind;
    unsigned long lastDataFetch;
};

class WeatherApp : public App {
public:
  void init() override;
  void resume()  override;
  void suspend() override {}
  void tick()    override;
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
  // isConnecting() NOT reusable: !_dataReady is a never-had-data latch, set
  // once on the first good fetch and never re-armed.
  // TASK-245 / ADR-046: amber "connecting" bar until the first weather fetch lands.
  bool isConnecting() const override { return !_dataReady; }
  // TASK-246: red bar when the last weather fetch failed (cleared on next success).
  bool hasError() const override { return _wxErr; }

  // TASK-471: `_dataReady` used to be a composition-root static (`s_wxDataReady`)
  // read directly by cmdGet.h; that stopped being reachable once this app left
  // main.cpp's translation unit, so it is now a real member with an accessor.
  bool dataReady() const { return _dataReady; }

private:
  WeatherAppState _s   = {};
  int             _lsec = -1;
  bool            _wxErr = false;
  bool            _dataReady = false;
  float           _cfgLat = 0.0f;   // WIRE2-G4: coords snapshotted at each
  float           _cfgLon = 0.0f;   //   enqueue. TASK-706: resume() no longer
                                     //   diffs these against g_settings — it
                                     //   now unconditionally drains+refetches
                                     //   on every resume, which subsumes the
                                     //   coord-change case. Left in place: any
                                     //   future resume-time diagnostics that
                                     //   want "did the coords actually change"
                                     //   can still read them.

  // WIRE2-G4: single enqueue path — snapshot g_settings coords and hand them
  // to dataTask (which re-snapshots under mux).
  void enqueueWx();
  void weatherDrawChrome();
  void repaintWeatherValues();
  void repaintWeatherTime();
  void repaintWeather();
  void weatherTick();
};
