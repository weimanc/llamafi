/*******************************************************************
    Displays Album Art on a 320 x 240 ESP32.

    Parts:
    ESP32 With Built in 320x240 LCD with Touch Screen (ESP32-2432S028R)
    https://github.com/witnessmenow/Spotify-Diy-Thing#hardware-required

 *******************************************************************/

// ----------------------------
// Display type
// ---------------------------

// This project currently supports the following displays
// (Uncomment the required #define)

// 1. Cheap yellow display (Using TFT-eSPI library)
// #define YELLOW_DISPLAY

// 2. Matrix Displays (Like the ESP32 Trinity)
// #define MATRIX_DISPLAY

// 3. Winamp 2 skin renderer on CYD2USB (M3 — uses gen/ atlas)
// #define WINAMP_DISPLAY

// If no defines are set, it will default to CYD
#if !defined(YELLOW_DISPLAY) && !defined(MATRIX_DISPLAY) && !defined(WINAMP_DISPLAY)
#define YELLOW_DISPLAY // Default to Yellow Display for display type
#endif

// Album art disabled while the i.scdn.co fetch hang is unresolved.
// Comment out to re-enable.
#define DISABLE_ALBUM_ART 1

// NFC disabled per TASK-004: PN532 not wired on this dev unit.
// Code uses #ifdef NFC_ENABLED, so commenting (not setting to 0) is what disables it.
//#define NFC_ENABLED 1

// This causes issues in certain circumstances e.g. Play an album and let it auto play to related songs
bool writeContextToNfc = true;

// ----------------------------
// ----------------------------
// Standard Libraries
// ----------------------------
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_wifi.h>   // TASK-282: esp_wifi_set_ps (wifiPs A/B toggle)

// TASK-426 A/B control for the boot cascade's per-candidate retry. The thing
// under test only happens during setup(), so a plain serial toggle cannot reach
// it — the flag has to survive the reset that starts the run, which RTC slow
// memory does (across a SOFTWARE reset; an EN/RTS reset clears the RTC domain
// and was what silently made both arms run the control on the first attempt).
//
// Debug builds only, and cookie-guarded: RTC_NOINIT starts as garbage, so
// without the cookie a cold boot could disable the retry by accident — in a
// production build that would be a real, randomly-appearing regression. Prod
// compiles this to a constant false and always retries.
#ifdef SERIAL_DEBUG
static constexpr uint32_t kCasRetryCookie = 0x426AB1FEu;
RTC_NOINIT_ATTR uint32_t g_casRetryCookie;
RTC_NOINIT_ATTR uint32_t g_casRetryOff;
static inline bool casRetryDisabled() {
  return g_casRetryCookie == kCasRetryCookie && g_casRetryOff != 0;
}
#else
static inline bool casRetryDisabled() { return false; }
#endif

#include <FS.h>
#include "SPIFFS.h"
#include <time.h>     // configTime(), time(); needed for NTP sync at boot (time-001)
#include <esp_ota_ops.h>  // esp_ota_get_app_description() for serialdbg-001 boot banner (Arduino-ESP32 2.0.x; esp-idf 5.x renames this to <esp_app_desc.h>)
#include <esp_log.h>      // esp_log_level_set() for ADR-042 E1 HTTPClient log suppression
#include <esp_task_wdt.h> // esp_task_wdt_init() — extended timeout for dataTask TLS
#include <esp_heap_caps.h> // T_MB_PROBE_00: caps-split heap probes (TASK-261 Phase 0)
#include <mbedtls/base64.h> // SERIAL_DEBUG `screendump` command — TFT readback encoding
// TASK-427: SD.h/SPI.h now also needed by SD_BOOT_MOUNT builds (cyd2usb_player) that
// don't define SERIAL_DEBUG — the boot mount itself moved out of the SERIAL_DEBUG gate.
// sd_diskio.h/ff.h/ffconf.h stay SERIAL_DEBUG-only: only the bring-up probes (`sdmbr`,
// `sdmem`) use them.
#if defined(SERIAL_DEBUG) || defined(SD_BOOT_MOUNT)
#include <SD.h>   // TASK-408: sdprobe bring-up probe, own VSPI bus (SD/FS is not otherwise linked)
#include <SPI.h>
#endif
#ifdef SERIAL_DEBUG
#include <sd_diskio.h>  // TASK-408: raw-sector access for `sdmbr` (below SD/FatFs)
#include <ff.h>   // TASK-408: FATFS/FIL sizes — the mount's real memory cost (see cmdSdMem)
#include "ffconf.h" // TASK-408: FF_VOLUMES — kept for anyone re-investigating the deferred
                    // live-mount corruption (see setup()'s sdProbeBootMount() comment)
#endif

// ----------------------------
// Additional Libraries
// ----------------------------

#include <SpotifyArduino.h>

// including a "spotify_server_cert" variable
// header is included as part of the SpotifyArduino libary
#include <SpotifyArduinoCert.h>

#include <ArduinoJson.h>

WiFiClientSecure client;

//------- Replace the following! ------

// Country code, including this is advisable
// SPOTIFY_MARKET moved to common_cyd build_flags so both .ino and
// spotifyTaskStorage.cpp see the same value (TASK-031b).
#ifndef SPOTIFY_MARKET
#define SPOTIFY_MARKET "IE"
#endif
//------- ---------------------- ------

// ----------------------------
// Internal includes
// ----------------------------
#include "refreshToken.h"
char clientId[200];
char clientSecret[200];

#include "spotifyDisplay.h"

#include "spotifyLogic.h"

#include "configFile.h"

#include "httpsDate.h"

#include "logSink.h"
#include "logServer.h"
#include "logHeartbeat.h"
#include "wifiDiag.h"
#include "perf.h"
#include "spotifyTask.h"
#ifdef SCREEN_LOG
#include "screenLog.h"
#endif
#ifdef WINAMP_DISPLAY
#include "winamp/vuMeter.h"
#endif
#include "util/mathUtil.h"
#include "util/timeFmt.h"   // WIRE2-G2/G3: shared 12h/24h + dateFmt helpers
#include "util/tftViewportRepair.h"   // TASK-359: heatmap rotated-text clip migrated onto the shared helper

// ----------------------------
// Memory overlay layout (Phase 1: declarative budget only — no buffers wired yet)
// ----------------------------
#include "gen/mem_layout.h"

// ----------------------------
// App shell
// ----------------------------
#include "appShell.h"
#include "taskbar/taskbar.h"
#include "dataTask.h"
#include "settingsStorage.h"

AppId currentAppId = AppId::Spotify;
static AppId g_previousAppId = AppId::Spotify;
// TASK-259/260/413: the "player" is one slot with three modes {Spotify | WebRadio |
// Player}. Tapping the taskbar icon while the player is already active cycles the
// mode and persists (resolvePlayerTap); returning to the player from another app
// restores the last-active one instead of always landing on Spotify. The mode is the
// persisted single source of truth g_settings.playerMode (TASK-260) — written by the
// eject toggles + taskbar cycle + Settings UI, read by resolvePlayerSlot. v2 boot
// (OQ-BOOT): cold-boot enters the persisted mode (see the boot-into-mode redirect at
// the end of setup()); auto-play is the webRadioAutoplay knob (WebRadio only).

#ifdef TOUCH_DEBUG_OVERLAY
#include "debug/touchDebugOverlay.h"
TouchDebugOverlay g_touchDebug;
#endif

// ----------------------------
// Display Handling Code
// ----------------------------

// WINAMP_DISPLAY is checked first so that envs which define it on top of
// YELLOW_DISPLAY (cyd2usb_winamp inherits common_cyd) pick the Winamp renderer.
#if defined WINAMP_DISPLAY

#include "winamp/winampDisplay.h"
WinampDisplay winampDisplay;
SpotifyDisplay *spotifyDisplay = &winampDisplay;

#elif defined YELLOW_DISPLAY

#include "cheapYellowLCD.h"
CheapYellowDisplay cyd;
SpotifyDisplay *spotifyDisplay = &cyd;

#elif defined MATRIX_DISPLAY
#include "matrixDisplay.h"
MatrixDisplay matrixDisplay;
SpotifyDisplay *spotifyDisplay = &matrixDisplay;

#endif
// ----------------------------

#ifdef NFC_ENABLED
#include "nfc.h"
#endif

#ifdef SPIKE_MODE
#include "spikeMode.h"
#endif

// ── TASK-261/267 A-lite heap probes (caps-split diagnostic) ──
// The mb_arena itself ships in production (TASK-262 promotion — MEMBUDGET_PHASE1 now in
// cyd2usb_winamp; arena acquired JIT in WebRadioApp::_play(), released in ::suspend()).
// These verbose boot/CP probes are pure diagnostics, so they are SERIAL_DEBUG-gated —
// they do NOT ship in production (the call sites become no-ops, zero runtime cost).
//
// Arena size (TASK-261 Phase 2 DUT finding): 24 K covers Helix-only (9 structs,
// 23,216 B aligned) with 1.4 K slack; 40 K exhausted the DMA pool on first
// connecttohost(). InBuff (6.4 K) uses regular calloc (allocated once/session, no churn).
#if defined(MEMBUDGET_PHASE1) && defined(SERIAL_DEBUG)
// T_MB_PROBE_00: caps-split heap probe — fires at boot milestones so the DUT log
// captures them without needing a serial command.
static void mb_heap_probe(const char *tag) {
    Serial.printf("[membudget] %s freeInt=%u lfbInt=%u freeDma=%u lfbDma=%u\n",
        tag,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
}
#else
static inline void mb_heap_probe(const char *) {}   // no-op (production / non-debug)
#endif

// ── App dispatch (M-MULTIAPP, TASK-087c/d) ─────────────────────────────

bool g_appLaunched[(int)AppId::COUNT] = {};

// ── SpotifyApp (TASK-090d) ─────────────────────────────────────────────
#ifdef WINAMP_DISPLAY
class SpotifyApp : public App {
public:
  void init() override {
    winampDisplay.showDefaultScreen();
  }
  void resume() override {
    winampDisplay.repaintChrome();
    winampDisplay.invalidatePlaylist();
    // TASK-352: restore the default volume-commit seam (WebRadio may have
    // wired its own on the way out) and seed the slider from the current
    // snapshot rather than whatever pct repaintChrome() just redrew from
    // its lastVolumeRendered cache (could be WebRadio's, from before eject).
    winampDisplay.setVolumeSink(nullptr);
    spotifyTask::Snapshot snap;
    spotifyTask::copySnapshot(&snap);
    winampDisplay.drawVolume(snap.volumePercent);
  }
  void suspend() override {
    winampDisplay.resetDragState();
  }
  // spotifyTask action queue is exclusively user-initiated (play/pause/next/prev/
  // volume/shuffle/repeat/seek) — hasPendingActions() true means a user tap is
  // still in flight. cmdTap also enqueues via injectTouch(), so this path covers
  // both production touches (via handleInput) and injected taps.
  bool hasPendingAsync() const override {
    return spotifyTask::hasPendingActions();
  }
  // TASK-245 / ADR-046: red taskbar bar on a persistent 403 (authorization
  // refused — e.g. owner-account Premium lapsed). Self-clears on the next
  // successful poll (see spotifyTask::authError()).
  // TASK-366: OR'd with degraded() (>=2 consecutive non-403 failures — network/
  // timeout/DNS) so a sustained non-auth poll problem also shows red, not just
  // 403s. Both are sticky latches owned by spotifyTask; this endpoint just ORs.
  bool hasError() const override {
    return spotifyTask::authError() || spotifyTask::degraded();
  }
  // TASK-245 amendment / ADR-046: amber "connecting" bar at boot until the first
  // poll resolves (then green on success, red on persistent 403).
  bool isConnecting() const override {
    return spotifyTask::connecting();
  }
  void tick() override {
    {
      static unsigned long _lastScrollMs = 0;
      unsigned long now = millis();
      float dt = (_lastScrollMs == 0) ? 0.0f : (now - _lastScrollMs) * 0.001f;
      _lastScrollMs = now;
      winampDisplay.tickScroll(dt);
    }
    {
      // TASK-350: vu::tick() no longer reads spotifyTask state internally —
      // read the snapshot here at the Spotify call site, byte-identical to
      // the old inline behaviour.
      spotifyTask::Snapshot snap;
      spotifyTask::copySnapshot(&snap);
      const bool playing = snap.valid && snap.isPlaying && songStartMillis != 0;
      const long elapsed = playing ? (long)(millis() - (unsigned long)songStartMillis) : 0L;
      vu::tick(winampDisplay.chromeOriginX(), winampDisplay.chromeOriginY(), SKIN_MAIN_BG,
               playing, elapsed);
    }
    winampDisplay.drawPlaylist();
#ifdef NFC_ENABLED
    if (writeContextToNfc) {
      nfcLoop(lastTrackUri, lastTrackContextUri);
    } else {
      nfcLoop(lastTrackUri);
    }
#endif
    { unsigned long _t = millis(); updateCurrentlyPlaying(false);
      perf::record("spotify.poll", millis() - _t); }
    { unsigned long _t = millis(); updateProgressBar();
      perf::record("display.bar", millis() - _t); }
  }
  bool handleInput(TouchPhase phase, int x, int y) override {
    // TASK-414 / ADR-059 D6: eject is freed from "switch to WebRadio" (the
    // taskbar player-slot cycle from TASK-413 owns app switching now) and
    // becomes "load media from this source" — same TLS-reset + force-poll
    // reconnect as the Winamp logo tap (TASK-053f), via the shared
    // tryReconnect() (winampDisplay.h) so both affordances share one
    // cooldown. Duplicating the affordance is harmless; silently deleting a
    // recovery path is not, so the logo tap keeps its own behaviour
    // unchanged.
    if (phase == TouchPhase::Release && winampDisplay.hitTestEject(x, y)) {
        if (winampDisplay.tryReconnect()) {
          LOG_I("touch", "eject tap → TLS reset + force poll");
        }
        return true;
    }
    return winampDisplay.handleWinampInput(phase, x, y);
  }
};
static SpotifyApp g_SpotifyApp;
#endif // WINAMP_DISPLAY

// ── ClockApp (M-CLOCK-STYLES) ─────────────────────────────────────────
#include "clockApp.h"
static ClockApp g_ClockApp;

// ── VE instrumentation statics (consumed by SERIAL_DEBUG cmdGet) ─────────────
static bool s_wxDataReady   = false;   // set true when WeatherApp receives first fetch
static bool s_cxDataReady   = false;   // set true when CryptoApp receives first fetch
static int  s_golAliveCount = -1;      // -1 = GoL never ticked; ≥0 = last alive count

// ── MatrixApp (matrix.md) ──────────────────────────────────────────────
#define MATRIX_STREAMS    14
#define MATRIX_STRIDE     19
#define MATRIX_TICK_MS    25
#define MATRIX_CANVAS_W  275
#define MATRIX_CANVAS_H  240

class MatrixApp : public App {
public:
  void init() override {
    initMatrixState();
    repaintMatrix();
  }
  void resume() override {
    _applyMatrixSettings();
    repaintMatrix();
  }
  void suspend() override {}
  void tick() override { matrixTick(); }
  bool handleInput(TouchPhase phase, int, int) override {
    if (phase == TouchPhase::Press) {
      initMatrixState();
      repaintMatrix();
      return true;
    }
    return false;
  }
private:
  MatrixAppState _s;
  unsigned long  _lastTickMs = 0;
  uint16_t      _headColor = TFT_WHITE;
  uint16_t      _tailColor = TFT_GREEN;
  unsigned long _tickMs    = MATRIX_TICK_MS;

  void _applyMatrixSettings() {
    switch (g_settings.matrixColor) {
      case MatrixColor::White: _tailColor = 0xBDF7; break;
      case MatrixColor::Amber: _tailColor = 0xFD20; break;
      default:                 _tailColor = TFT_GREEN; break;
    }
    _headColor = TFT_WHITE;
    switch (g_settings.matrixSpeed) {
      case AppSpeed::Slow: _tickMs = 60; break;
      case AppSpeed::Fast: _tickMs = 10; break;
      default:             _tickMs = MATRIX_TICK_MS; break;
    }
  }

  void initMatrixState() {
    for (int i = 0; i < MATRIX_STREAMS; i++) {
      _s.rain[i].x        = i * MATRIX_STRIDE + 2;
      _s.rain[i].y        = (float)random(-400, 0);
      _s.rain[i].speed    = (float)random(5, 15);
      _s.rain[i].length   = random(15, 40);
      _s.rain[i].lastChar = ' ';
    }
    _s.initialised = true;
  }

  void repaintMatrix() {
    tft.fillRect(0, 0, MATRIX_CANVAS_W, MATRIX_CANVAS_H, TFT_BLACK);
  }

  void matrixTick() {
    unsigned long now = millis();
    if (now - _lastTickMs < _tickMs) return;
    _lastTickMs = now;
    for (int i = 0; i < MATRIX_STREAMS; i++) {
      tft.setTextColor(_headColor, TFT_BLACK);
      char hC = random(33, 126);
      tft.drawChar(hC, _s.rain[i].x, (int)_s.rain[i].y, 2);
      tft.setTextColor(_tailColor, TFT_BLACK);
      tft.drawChar(_s.rain[i].lastChar, _s.rain[i].x, (int)_s.rain[i].y - 20, 2);
      tft.fillRect(_s.rain[i].x, (int)_s.rain[i].y - (_s.rain[i].length * 20),
                   20, 20, TFT_BLACK);
      _s.rain[i].lastChar = hC;
      _s.rain[i].y += _s.rain[i].speed;
      if (_s.rain[i].y > MATRIX_CANVAS_H + (_s.rain[i].length * 20))
        _s.rain[i].y = -20.0f;
    }
    tft.setTextColor(_headColor, TFT_BLACK);
  }

#ifdef SERIAL_DEBUG
public:
  bool dbgGet(const char* var, char* buf, int len) const {
    static const char* kC[] = {"green","white","amber"};
    if (strcmp(var, "matrixColor") == 0) {
      snprintf(buf, len, "\"var\":\"matrixColor\",\"val\":\"%s\",\"last\":true",
               kC[(uint8_t)g_settings.matrixColor % 3]);
      return true;
    }
    if (strcmp(var, "matrixTickMs") == 0) {
      snprintf(buf, len, "\"var\":\"matrixTickMs\",\"val\":%lu,\"last\":true", _tickMs);
      return true;
    }
    return false;
  }
#endif
};
static MatrixApp g_MatrixApp;

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
static WeatherApp g_WeatherApp;

// ── CryptoApp (crypto.md) ─────────────────────────────────────────────
#define CRYPTO_FETCH_MS   60000UL
#define CRYPTO_COIN_COUNT 6
#define CX_CANVAS_Y    0
#define CX_CANVAS_H  240
#define CX_HEADER_Y    5
#define CX_RULE_Y     22
#define CX_ROW_Y0     25
#define CX_ROW_H      36   // 6 rows × 36 px = 216; row 5 divider lands at y=239
#define CX_COL_SYM     5
#define CX_COL_PRC    55
#define CX_COL_CHG   270

static const char* cgIdToDisplay(const char* id) {
  if (strcmp(id, "bitcoin")      == 0) return "BTC";
  if (strcmp(id, "ethereum")     == 0) return "ETH";
  if (strcmp(id, "binancecoin")  == 0) return "BNB";
  if (strcmp(id, "solana")       == 0) return "SOL";
  if (strcmp(id, "ripple")       == 0) return "XRP";
  if (strcmp(id, "cardano")      == 0) return "ADA";
  if (strcmp(id, "dogecoin")     == 0) return "DOGE";
  if (strcmp(id, "avalanche-2")  == 0) return "AVAX";
  if (strcmp(id, "matic-network")== 0) return "MATIC";
  if (strcmp(id, "chainlink")    == 0) return "LINK";
  if (strcmp(id, "polkadot")     == 0) return "DOT";
  if (strcmp(id, "litecoin")     == 0) return "LTC";
  return id;
}

static String formatCryptoPrice(float price) {
  if (price < 1.0f)     return String(price, 4);
  if (price < 1000.0f)  return String(price, 2);
  return String((int)price);
}

class CryptoApp : public App {
public:
  void init() override {
    dataTask::configureCrypto(
        const_cast<const char(*)[16]>(g_settings.cryptoCoins),
        g_settings.cryptoCcy);
    repaintCrypto();
    dataTask::enqueue(dataTask::DATA_FETCH_CRYPTO);
    _s.lastCryptoFetch = millis();
  }
  void resume() override {
    dataTask::configureCrypto(
        const_cast<const char(*)[16]>(g_settings.cryptoCoins),
        g_settings.cryptoCcy);
    repaintCrypto();
    _s.lastCryptoFetch = 0;  // force fresh fetch on next tick
  }
  void suspend() override {}
  void tick()    override { cryptoTick(); }
  bool handleInput(TouchPhase, int, int) override { return false; }
  // TASK-245 / ADR-046: amber "connecting" bar until the first crypto fetch lands.
  bool isConnecting() const override { return !s_cxDataReady; }
  // TASK-246: red bar when the last crypto fetch failed (cleared on next success).
  bool hasError() const override { return _cxErr; }

private:
  CryptoAppState _s = {};
  bool           _cxErr = false;

  void repaintCrypto() {
    tft.fillRect(0, CX_CANVAS_Y, 275, CX_CANVAS_H, TFT_BLACK);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(0xFFE0);
    tft.drawString("CRYPTO TERMINAL", CX_COL_SYM, CX_HEADER_Y, 2);
    tft.drawFastHLine(0, CX_RULE_Y, 270, 0x07FF);
    int yPos = CX_ROW_Y0;
    for (int i = 0; i < CRYPTO_COIN_COUNT; i++) {
      tft.setTextColor(0xFFFF);
      tft.drawString(cgIdToDisplay(g_settings.cryptoCoins[i]), CX_COL_SYM, yPos + 11, 2);
      tft.setTextColor(0x07FF);
      tft.drawString(_s.lastCryptoFetch ? formatCryptoPrice(_s.prices[i])
                                        : String("---"), CX_COL_PRC, yPos + 11, 2);
      if (!_s.lastCryptoFetch) {
        tft.setTextColor(0x7BEF);
        tft.drawRightString("---", CX_COL_CHG, yPos + 11, 2);
      } else {
        tft.setTextColor((_s.changes[i] >= 0) ? (uint16_t)0x07E0 : (uint16_t)0xF800);
        tft.drawRightString(String(_s.changes[i], 1) + "%", CX_COL_CHG, yPos + 11, 2);
      }
      yPos += CX_ROW_H;
      tft.drawFastHLine(0, yPos - 2, 270, 0x2104);
    }
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void cryptoTick() {
    unsigned long now = millis();
    if (!_s.lastCryptoFetch || now - _s.lastCryptoFetch > CRYPTO_FETCH_MS) {
      dataTask::enqueue(dataTask::DATA_FETCH_CRYPTO);
      _s.lastCryptoFetch = now;
    }
    dataTask::CryptoResult r;
    if (dataTask::pollCrypto(&r)) {
      _s.lastCryptoFetch = now;
      if (r.ok) {
        for (int i = 0; i < CRYPTO_COIN_COUNT; i++) {
          _s.prices[i]  = r.prices[i];
          _s.changes[i] = r.changes[i];
        }
        s_cxDataReady = true;
        _cxErr = false;
        repaintCrypto();
      } else {
        _cxErr = true;   // TASK-246: failed fetch → red bar
      }
    }
  }

#ifdef SERIAL_DEBUG
public:
  bool dbgGet(const char* var, char* buf, int len) const {
    for (int i = 0; i < 6; i++) {
      char key[16]; snprintf(key, sizeof(key), "cryptoCoin%d", i);
      if (strcmp(var, key) == 0) {
        snprintf(buf, len, "\"var\":\"%s\",\"val\":\"%s\",\"last\":true",
                 key, g_settings.cryptoCoins[i]);
        return true;
      }
    }
    if (strcmp(var, "cryptoCcy") == 0) {
      snprintf(buf, len, "\"var\":\"cryptoCcy\",\"val\":\"%s\",\"last\":true",
               g_settings.cryptoCcy);
      return true;
    }
    if (strcmp(var, "cryptoLastFetch") == 0) {
      snprintf(buf, len, "\"var\":\"cryptoLastFetch\",\"val\":%lu,\"last\":true",
               _s.lastCryptoFetch);
      return true;
    }
    if (strcmp(var, "cryptoHttpCode") == 0) {
      snprintf(buf, len, "\"var\":\"cryptoHttpCode\",\"val\":%d,\"last\":true",
               dataTask::lastCryptoHttpCode());
      return true;
    }
    return false;
  }
#endif
};
static CryptoApp g_CryptoApp;

// ── LifeApp (gol.md) ──────────────────────────────────────────────────
#define GOL_GRID_W       55
#define GOL_GRID_H       48
#define GOL_CELL_PX       5
#define GOL_CELL_FILL     4
#define GOL_TICK_MS     100
#define GOL_STAGNATION  120
#define GOL_MIN_ALIVE     5
#define GOL_INIT_DENSITY 20

class LifeApp : public App {
public:
  void init() override { spawnLife(_s); resume(); }

  void resume() override {
    _applyLifeSettings();
    tft.fillRect(0, 0, GOL_GRID_W * GOL_CELL_PX, GOL_GRID_H * GOL_CELL_PX, TFT_BLACK);
    repaintLife(_s);
  }

  void suspend() override {}

  void tick() override { golTick(); }

  bool handleInput(TouchPhase phase, int, int) override {
    if (phase == TouchPhase::Press) {
      spawnLife(_s);
      resume();
      return true;
    }
    return false;
  }

private:
  LifeAppState  _s;
  unsigned long _lastTickMs = 0;
  unsigned long _tickMs    = GOL_TICK_MS;
  bool          _monoColor = false;
  static uint8_t s_nextGrid[GOL_GRID_W][GOL_GRID_H];

  void _applyLifeSettings() {
    switch (g_settings.lifeSpeed) {
      case AppSpeed::Slow: _tickMs = 200; break;
      case AppSpeed::Fast: _tickMs =  40; break;
      default:             _tickMs = GOL_TICK_MS; break;
    }
    _monoColor = (g_settings.lifeColors == LifeColors::Mono);
  }

  void spawnLife(LifeAppState &s) {
    for (int x = 0; x < GOL_GRID_W; x++)
      for (int y = 0; y < GOL_GRID_H; y++)
        s.grid[x][y] = (random(100) < GOL_INIT_DENSITY) ? 1 : 0;
    s.sameCountTimer = 0;
    s.hueShift = 0;
    s.lastCellCount = 0;
    s.initialised = true;
  }

  void repaintLife(LifeAppState &s) {
    tft.fillRect(0, 0, GOL_GRID_W * GOL_CELL_PX, GOL_GRID_H * GOL_CELL_PX, TFT_BLACK);
    for (int x = 0; x < GOL_GRID_W; x++) {
      for (int y = 0; y < GOL_GRID_H; y++) {
        if (s.grid[x][y] > 0) {
          uint16_t cellColor;
          if (_monoColor) {
            cellColor = TFT_WHITE;
          } else {
            uint8_t r = (x * 4 + s.hueShift) % 255;
            uint8_t g = (y * 2 + s.hueShift / 2) % 255;
            cellColor = tft.color565(r, g, 255 - r);
          }
          tft.fillRect(x * GOL_CELL_PX, y * GOL_CELL_PX,
                       GOL_CELL_FILL, GOL_CELL_FILL,
                       cellColor);
        }
      }
    }
  }

  void stepGeneration(LifeAppState &s) {
    int totalAlive = 0;
    for (int x = 0; x < GOL_GRID_W; x++) {
      for (int y = 0; y < GOL_GRID_H; y++) {
        int n = 0;
        for (int dx = -1; dx <= 1; dx++)
          for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            if (s.grid[(x+dx+GOL_GRID_W)%GOL_GRID_W]
                      [(y+dy+GOL_GRID_H)%GOL_GRID_H] > 0) n++;
          }
        if (s.grid[x][y] > 0)
          s_nextGrid[x][y] = (n == 2 || n == 3) ? 1 : 0;
        else
          s_nextGrid[x][y] = (n == 3) ? 1 : 0;
        if (s_nextGrid[x][y] > 0) totalAlive++;
      }
    }
    for (int x = 0; x < GOL_GRID_W; x++) {
      for (int y = 0; y < GOL_GRID_H; y++) {
        if (s.grid[x][y] != s_nextGrid[x][y]) {
          if (s_nextGrid[x][y] > 0) {
            uint16_t cellColor;
            if (_monoColor) {
              cellColor = TFT_WHITE;
            } else {
              uint8_t r = (x * 4 + s.hueShift) % 255;
              uint8_t g = (y * 2 + s.hueShift / 2) % 255;
              cellColor = tft.color565(r, g, 255 - r);
            }
            tft.fillRect(x * GOL_CELL_PX, y * GOL_CELL_PX,
                         GOL_CELL_FILL, GOL_CELL_FILL,
                         cellColor);
          } else {
            tft.fillRect(x * GOL_CELL_PX, y * GOL_CELL_PX,
                         GOL_CELL_FILL, GOL_CELL_FILL, TFT_BLACK);
          }
        }
        s.grid[x][y] = s_nextGrid[x][y];
      }
    }
    tft.fillRect(215, 0, 55, 15, TFT_BLACK);
    tft.setTextColor(0x07FF);
    tft.drawRightString(String(totalAlive), 270, 2, 2);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);

    s_golAliveCount = totalAlive;
    if (totalAlive == s.lastCellCount) s.sameCountTimer++;
    else                               s.sameCountTimer = 0;
    s.lastCellCount = totalAlive;
    s.hueShift += 3;

    if (totalAlive < GOL_MIN_ALIVE || s.sameCountTimer > GOL_STAGNATION) {
      spawnLife(s);
      resume();
    }
  }

  void golTick() {
    unsigned long now = millis();
    if (now - _lastTickMs < _tickMs) return;
    _lastTickMs = now;
    stepGeneration(_s);
  }

#ifdef SERIAL_DEBUG
public:
  bool dbgGet(const char* var, char* buf, int len) const {
    if (strcmp(var, "lifeColors") == 0) {
      snprintf(buf, len, "\"var\":\"lifeColors\",\"val\":\"%s\",\"last\":true",
               _monoColor ? "mono" : "rainbow");
      return true;
    }
    if (strcmp(var, "lifeTickMs") == 0) {
      snprintf(buf, len, "\"var\":\"lifeTickMs\",\"val\":%lu,\"last\":true", _tickMs);
      return true;
    }
    return false;
  }
#endif
};
uint8_t LifeApp::s_nextGrid[GOL_GRID_W][GOL_GRID_H];
static LifeApp g_LifeApp;

// ── SettingsApp constants (TASK-141a) ─────────────────────────────────
#define SETTINGS_HEADER_H         28
#define SETTINGS_CONTENT_Y        28
#define SETTINGS_CONTENT_H       212
#define SETTINGS_CAT_COUNT         7
#define SETTINGS_ROW_H            26
#define SETTINGS_ROW_COL_LABEL     8
#define SETTINGS_ROW_COL_VALUE   268
#define SETTINGS_ROW_MAX           8
#define SETTINGS_BG_RGB565      0x2104
#define SETTINGS_SEP_COLOR      0x4208
#define SETTINGS_HEADER_TXT     0xFFFF
#define SETTINGS_LABEL_COLOR    0xFFFF
#define SETTINGS_VALUE_COLOR    0x07FF
#define SETTINGS_CHEVRON_COLOR  0x4208
#define SETTINGS_CANCEL_COLOR   0xC8A0

#include "settings/wifiSection.h"
#include "settings/timeSection.h"
#include "settings/displaySection.h"
#include "settings/appsSection.h"
#include "settings/ledSection.h"
#include "settings/keyboardWidget.h"
#include "settings/calibrationFlow.h"
#include "settings/systemSection.h"

class SettingsApp : public App {
public:
  void init() override {
    _sections[0] = &_wifi;
    _sections[1] = &_time;
    _sections[2] = &_cal;
    _sections[3] = &_disp;
    _sections[4] = &_led;
    _sections[5] = &_apps;
    _sections[6] = &_system;
    repaintCategoryList();
  }

  void resume() override {
    _snapshot = g_settings;
    if (_activeSection) _activeSection->repaint();
    else repaintCategoryList();
  }

  bool hasPendingAsync() const override { return _apps.isValidating(); }

  void suspend() override {
    if (_activeSection) { _activeSection->leave(); _activeSection = nullptr; }
    _s.section = -1;
  }

  void tick() override {
    if (_activeSection) {
      SectionResult tr = _activeSection->tick();
      if (tr == SectionResult::NavigateHome) {
        _activeSection->leave();
        _activeSection = nullptr;
        _s.section = -1;
        switchApp(g_previousAppId);
        return;
      }
      if (_activeSection == &_cal && _cal.justSaved()) {
        _cal.clearJustSaved();
        ts.setCalibration(g_calData.xMin, g_calData.xMax,
                          g_calData.yMin, g_calData.yMax);
      }
      if (_activeSection == &_cal && _cal.stepping()) {
        CYD28_TS_Point raw = ts.getPointRaw();
        bool pressed    = (raw.z > CAL_Z_THRESHOLD);
        bool wasPressed = (_lastCalZ > CAL_Z_THRESHOLD);
        _lastCalZ = raw.z;
        if (pressed)
          _cal.handleInputRaw(TouchPhase::Press, raw.x, raw.y);
        else if (wasPressed)
          _cal.handleInputRaw(TouchPhase::Release, raw.x, raw.y);
      }
    }
  }

  void openSection(int idx) { _onCategoryTap(idx); }

  bool handleInput(TouchPhase phase, int x, int y) override {
    if (_activeSection) {
      SectionResult r = _activeSection->handleInput(phase, x, y);
      if (r == SectionResult::GoBack) _popSection();
      return true;
    }
    if (_s.section >= 0) {
      // stub section (Touch Cal / LED) — honour back tap only
      if (phase == TouchPhase::Release && y < SETTINGS_HEADER_H && x < 60)
        _popSection();
      return true;
    }
    if (phase != TouchPhase::Release) return false;
    if (y < SETTINGS_HEADER_H && x < 60) { switchApp(g_previousAppId); return true; }
    int cancelRowTop = SETTINGS_CONTENT_Y + SETTINGS_CAT_COUNT * SETTINGS_ROW_H + 1;
    if (y >= cancelRowTop && y < cancelRowTop + SETTINGS_ROW_H) { _cancel(); return true; }
    int row = (y - SETTINGS_HEADER_H) / SETTINGS_ROW_H;
    if (row >= 0) _onCategoryTap(row);
    return true;
  }

#ifdef SERIAL_DEBUG
  bool dbgGet(const char* var, char* buf, int len) const {
    if (strcmp(var, "settingsSection") == 0) {
      snprintf(buf, len, "\"var\":\"settingsSection\",\"section\":%d,\"last\":true", _s.section);
      return true;
    }
    if (strcmp(var, "settingsAppSubmenu") == 0) {
      snprintf(buf, len, "\"var\":\"settingsAppSubmenu\",\"submenu\":%d,\"last\":true", _apps.submenu());
      return true;
    }
    if (strcmp(var, "wifiSaved") == 0) {
      // TASK-401 / VE-2-1: row index <-> SSID mapping + LRU state for an
      // automated harness — same dbgGet-chain pattern as
      // "settingsAppSubmenu" above (_apps.submenu()). _wifi.dbgSavedCount()
      // also triggers the lazy migrate+load if this is the first touch this
      // boot, so `get wifiSaved` works standalone without a prior
      // Settings->WiFi navigation.
      uint8_t n = _wifi.dbgSavedCount();
      int off = snprintf(buf, len, "\"var\":\"wifiSaved\",\"count\":%d,\"entries\":[", (int)n);
      if (off < 0) off = 0;
      if (off > len) off = len;
      for (uint8_t i = 0; i < n && off < len; i++) {
        SavedWifiNet e = _wifi.dbgSavedEntry(i);
        int w = snprintf(buf + off, (size_t)(len - off),
                          "%s{\"ssid\":\"%s\",\"lastUsedMs\":%lu}",
                          i ? "," : "", e.ssid, e.lastUsedMs);
        if (w < 0) break;
        off += w;
        if (off > len) off = len;
      }
      if (off < len) snprintf(buf + off, (size_t)(len - off), "],\"last\":true");
      return true;
    }
    return false;
  }

  // M-HOME-LOCATION H-5: confirm-screen divergence km (T-HOME-05 observable),
  // surfaced through `get prloc` — house dbgGet-chain pattern.
  int prDivKm() const { return _apps.prDivKm(); }
#endif

private:
  struct State { int8_t section = -1; } _s;

  WifiSection        _wifi;
  TimeSection        _time;
  CalibrationFlow    _cal;
  DisplaySection     _disp;
  AppsSection        _apps;
  LedSection         _led;
  SystemSection      _system;
  int16_t            _lastCalZ = 0;
  AppSettings        _snapshot;
  SettingsSection* _sections[SETTINGS_CAT_COUNT];
  SettingsSection* _activeSection = nullptr;

  void _popSection() {
    if (_activeSection) { _activeSection->leave(); _activeSection = nullptr; }
    _s.section = -1;
    repaintCategoryList();
  }

  void _cancel() {
    g_settings = _snapshot;
    SettingsStorage::save();
    switchApp(g_previousAppId);
  }

  void _onCategoryTap(int idx) {
    if (idx < 0 || idx >= SETTINGS_CAT_COUNT) return;
    _s.section = (int8_t)idx;
    // All SETTINGS_CAT_COUNT sections are wired in the ctor (_sections[0..6]),
    // so this is always non-null; the guard is kept as cheap defence only.
    if (_sections[idx]) {
      _activeSection = _sections[idx];
      _activeSection->enter();
    }
  }

  void repaintHeader(const char* title) {
    tft.fillRect(0, 0, 275, SETTINGS_HEADER_H, SETTINGS_BG_RGB565);
    tft.setTextColor(SETTINGS_HEADER_TXT);
    tft.setTextDatum(ML_DATUM);
    tft.drawString("< back", 4, 14, 2);
    tft.setTextDatum(MR_DATUM);
    tft.drawString(title, 271, 14, 2);
    tft.drawFastHLine(0, SETTINGS_HEADER_H - 1, 275, SETTINGS_SEP_COLOR);
    tft.setTextDatum(TL_DATUM);
  }

  void repaintCategoryList() {
    static const char* kLabels[SETTINGS_CAT_COUNT] = {
      "WiFi", "Time & Location", "Touch Calibration",
      "Display", "LED", "Applications", "System"
    };
    repaintHeader("Settings");
    tft.fillRect(0, SETTINGS_CONTENT_Y, 275, SETTINGS_CONTENT_H, SETTINGS_BG_RGB565);
    for (int i = 0; i < SETTINGS_CAT_COUNT; i++) {
      int y   = SETTINGS_CONTENT_Y + i * SETTINGS_ROW_H;
      int mid = y + SETTINGS_ROW_H / 2;
      tft.setTextDatum(ML_DATUM);
      tft.setTextColor(SETTINGS_LABEL_COLOR);
      tft.drawString(kLabels[i], SETTINGS_ROW_COL_LABEL, mid, 2);
      tft.setTextDatum(MR_DATUM);
      tft.setTextColor(SETTINGS_CHEVRON_COLOR);
      tft.drawString(">", SETTINGS_ROW_COL_VALUE, mid, 2);
    }
    int sepY = SETTINGS_CONTENT_Y + SETTINGS_CAT_COUNT * SETTINGS_ROW_H;
    tft.drawFastHLine(0, sepY, S_CANVAS_W, SETTINGS_SEP_COLOR);
    int cancelMid = sepY + 1 + SETTINGS_ROW_H / 2;
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(SETTINGS_CANCEL_COLOR);
    tft.drawString("Cancel", SETTINGS_ROW_COL_LABEL, cancelMid, 2);
    tft.setTextDatum(TL_DATUM);
  }

};
static SettingsApp g_SettingsApp;
LedFlow      g_ledFlow;
BacklightFlow g_backlight;   // WIRE2-G5: backlight owner (ADR-050)
KeyboardWidget g_keyboard;
SPickerList g_countryPicker;   // M-COUNTRY-PICKER: shared modal country picker (settingsWidgets.h)
#ifdef SERIAL_DEBUG
static bool settingsDbgGet(const char* v, char* b, int l) { return g_SettingsApp.dbgGet(v, b, l); }
#endif

// ── StockApp (stock.md) ───────────────────────────────────────────────
#define STOCK_TICKER_COUNT      8
#define STOCK_QUOTE_FETCH_MS    60000UL
#define STOCK_CHART_FETCH_D1    60000UL
#define STOCK_CHART_FETCH_SLOW  300000UL
#define STOCK_HEATMAP_FETCH_MS  120000UL

// Tile label tier thresholds — see ADR-037
constexpr int16_t HM_T1_H = 36, HM_T1_W = 40;
constexpr int16_t HM_T2_H = 28, HM_T2_W = 40;
constexpr int16_t HM_T3_H = 20, HM_T3_W = 40;
constexpr int16_t HM_T4_H = 18, HM_T4_W = 40;
constexpr int16_t HM_T5_H = 10, HM_T5_W = 20;
constexpr int16_t HM_T6_MIN_W = 8;           // minimum tile width for rotated text
constexpr int16_t HM_T6_SEP   = 2;           // gap (px) between sym and pct in rotated sprite

#define ST_CANVAS_Y           0
#define ST_CANVAS_H         240
#define ST_CANVAS_X2        274
#define ST_LIST_HEADER_Y      5
#define ST_LIST_RULE_Y       22
#define ST_LIST_ROW_START_Y  25
#define ST_LIST_ROW_H        26
#define ST_LIST_COL_SYMBOL    5
#define ST_LIST_COL_PRICE    55
#define ST_LIST_COL_CHANGE  270
#define ST_CHART_HEADER_Y     0
#define ST_CHART_HEADER_H    18
#define ST_CHART_BACK_W      30
#define ST_CHART_TICKER_X    30
#define ST_CHART_TABS_X     130
#define ST_CHART_TAB_W       36
#define ST_CHART_PLOT_Y      18
#define ST_CHART_PLOT_H     196
#define ST_CHART_FOOTER_Y   214

static uint16_t heatmapColour(float pct) {
    if (pct > 5.0f) pct = 5.0f;
    if (pct < -5.0f) pct = -5.0f;
    if (pct >= 0.0f) {
        float t = pct / 5.0f;
        uint8_t r = (uint8_t)(4.0f * (1.0f - t));
        uint8_t g = (uint8_t)(8.0f + 55.0f * t);
        uint8_t b = (uint8_t)(4.0f * (1.0f - t));
        return ((uint16_t)r << 11) | ((uint16_t)g << 5) | b;
    } else {
        float t = (-pct) / 5.0f;
        uint8_t r = (uint8_t)(4.0f + 27.0f * t);
        uint8_t g = (uint8_t)(8.0f * (1.0f - t));
        uint8_t b = (uint8_t)(4.0f * (1.0f - t));
        return ((uint16_t)r << 11) | ((uint16_t)g << 5) | b;
    }
}

static String formatStockPrice(float price) {
  if (price >= 1000.0f) return String((int)price);
  if (price >= 10.0f)   return String(price, 2);
  return String(price, 4);
}

class StockApp : public App {
  bool _pendingAsync = false;
  bool _everHadData  = false;  // TASK-245: any successful fetch (quote/chart/heatmap) yet?
  StockViewMode _appliedMode = StockViewMode::List;  // TASK-231: last launch-view applied
public:
  bool hasPendingAsync() const override { return _pendingAsync; }
  // TASK-245 / ADR-046: amber "connecting" bar until the first successful fetch
  // (any sub-view) lands; green thereafter.
  bool isConnecting() const override { return !_everHadData; }
  // TASK-246: red bar when the last fetch failed (_s.fetchFailed; set on a failed
  // quote/chart/heatmap result, cleared on success).
  bool hasError() const override { return _s.fetchFailed; }
  // TASK-384: the chart/heatmap "back to list" zones — same geometry
  // handleInput() checks at ST_CHART_HEADER_Y/ST_LIST_RULE_Y — never start a
  // new fetch, so they're safe to process even while a fetch is in flight.
  bool isNavigationTap(int x, int y) const override {
    if (_s.subView == StockSubView::ChartDetail)
      return y >= ST_CHART_HEADER_Y && y < ST_CHART_HEADER_Y + ST_CHART_HEADER_H
             && x < ST_CHART_BACK_W * 2;
    if (_s.subView == StockSubView::HeatmapDetail)
      return y < ST_LIST_RULE_Y && x > 190;
    return false;
  }
  void init() override {
    for (int i = 0; i < 8; i++)
      strlcpy(_s.tickers[i], g_settings.stockTickers[i], 8);
    dataTask::configureStockTickers(
        const_cast<const char(*)[8]>(g_settings.stockTickers));
    _s.subView     = StockSubView::List;
    _s.prevSubView = StockSubView::List;
    // TASK-247: do NOT blindly fetch the 8-ticker list quote here — when launching
    // into Heatmap/Chart mode that ~16 s batch (8 sequential Yahoo GETs) is wasted
    // and queues *ahead* of the view's real fetch. _applyLaunchView() enqueues only
    // what the launch view needs (List → quote, Heatmap → screener, Chart → chart).
    _applyLaunchView();   // TASK-231: honour Settings → Stock mode
  }

  void resume() override {
    bool changed = false;
    for (int i = 0; i < 8; i++) {
      if (strcmp(_s.tickers[i], g_settings.stockTickers[i]) != 0) {
        strlcpy(_s.tickers[i], g_settings.stockTickers[i], 8);
        changed = true;
      }
    }
    if (changed) {
      dataTask::configureStockTickers(
          const_cast<const char(*)[8]>(g_settings.stockTickers));
      _s.lastQuoteFetch = 0;
    }
    // TASK-231: if the launch-view setting changed since we last applied it
    // (e.g. the user just changed it in Settings), honour it now; otherwise
    // preserve whatever sub-view the user navigated to in-session.
    if (g_settings.stockMode != _appliedMode) {
      _applyLaunchView();
      return;
    }
    switch (_s.subView) {
      case StockSubView::List:          repaintList();    break;
      case StockSubView::ChartDetail:   repaintChart();   break;
      case StockSubView::HeatmapDetail: repaintHeatmap(); break;
    }
  }

  // TASK-231: enter the view configured by Settings → Stock "mode". Chart and
  // Heatmap have preconditions (a selected ticker / a fetched dataset) that only
  // the drill/enter helpers set up, so reuse them rather than just assigning
  // _s.subView — that is why init() previously hardcoded List. List is the
  // back-navigation base for both detail views.
  void _applyLaunchView() {
    _appliedMode = g_settings.stockMode;
    switch (g_settings.stockMode) {
      case StockViewMode::Chart:   drillToChart(0); break;   // first configured ticker
      case StockViewMode::Heatmap: enterHeatmap();  break;
      case StockViewMode::List:
      default:
        _s.subView     = StockSubView::List;
        _s.prevSubView = StockSubView::List;
        dataTask::enqueue(dataTask::DATA_FETCH_STOCK_QUOTE);  // TASK-247: only when List is the launch view
        _s.lastQuoteFetch = millis();
        repaintList();
        break;
    }
  }

  void suspend() override { _pendingAsync = false; }

  void tick() override {
    switch (_s.subView) {
      case StockSubView::List:          stockTickQuotes();  break;
      case StockSubView::ChartDetail:   stockTickChart();   break;
      case StockSubView::HeatmapDetail: stockTickHeatmap(); break;
    }
  }

  bool handleInput(TouchPhase phase, int x, int y) override {
    if (phase != TouchPhase::Release)
      return (_s.subView == StockSubView::ChartDetail ||
              _s.subView == StockSubView::HeatmapDetail);

    if (_s.subView == StockSubView::List) {
      if (y < ST_LIST_RULE_Y && x > 190) { enterHeatmap(); return true; }
      if (_s.fetchFailed) return true;
      if (y >= ST_LIST_ROW_START_Y && y < ST_CANVAS_Y + ST_CANVAS_H) {
        int rowIdx = constrain((y - ST_LIST_ROW_START_Y) / ST_LIST_ROW_H,
                               0, STOCK_TICKER_COUNT - 1);
        drillToChart((uint8_t)rowIdx);
        return true;
      }
    } else if (_s.subView == StockSubView::HeatmapDetail) {
      if (y < ST_LIST_RULE_Y && x > 190) { backToPrevView(); return true; }
      for (uint8_t i=0; i<_s.heatmapData.count; i++) {
        const HeatmapTile& t = _s.heatmapLayout[i];
        if (x>=t.x && x<t.x+t.w && y>=t.y && y<t.y+t.h) {
          drillToChartBySym(_s.heatmapData.symbols[t.tickerIdx], 0);
          return true;
        }
      }
      return true;
    } else {
      if (y >= ST_CHART_HEADER_Y && y < ST_CHART_HEADER_Y + ST_CHART_HEADER_H) {
        if (x < ST_CHART_BACK_W * 2) {
          backToPrevView();
          return true;
        }
        if (!_s.fetchFailed && x >= ST_CHART_TABS_X) {
          uint8_t tab = (uint8_t)constrain((x - ST_CHART_TABS_X) / ST_CHART_TAB_W, 0, 3);
          _s.chartRange     = (StockRange)tab;
          _s.chartLen = 0; _s.chartLo = _s.chartHi = 0;
          if (_s.chartSymbol[0])
            dataTask::enqueueStockChartBySym(_s.chartSymbol, tab);
          else
            dataTask::enqueueStockChart(_s.chartTickerIdx, tab);
          _s.lastChartFetch = millis();
          _pendingAsync     = true;
          return true;
        }
      }
      return true;
    }
    return false;
  }

  bool dbgGet(const char* var, char* buf, int len) const {
    if (strcmp(var, "stockSubView") == 0) {
      snprintf(buf, len, "\"var\":\"stockSubView\",\"val\":\"%s\",\"last\":true",
               _s.subView == StockSubView::HeatmapDetail ? "heatmap" :
               _s.subView == StockSubView::ChartDetail   ? "chart"   : "list");
      return true;
    }
    if (strcmp(var, "stockChartTicker") == 0) {
      snprintf(buf, len, "\"var\":\"stockChartTicker\",\"val\":\"%s\",\"last\":true",
               _s.chartSymbol[0] ? _s.chartSymbol : _s.tickers[_s.chartTickerIdx]);
      return true;
    }
    if (strcmp(var, "stockChartRange") == 0) {
      const char* r = (_s.chartRange == StockRange::D1)  ? "D1"
                    : (_s.chartRange == StockRange::D5)  ? "D5"
                    : (_s.chartRange == StockRange::Mo1) ? "Mo1" : "Ytd";
      snprintf(buf, len, "\"var\":\"stockChartRange\",\"val\":\"%s\",\"last\":true", r);
      return true;
    }
    if (strcmp(var, "lastQuoteFetch") == 0) {
      snprintf(buf, len, "\"var\":\"lastQuoteFetch\",\"val\":%lu,\"last\":true",
               _s.lastQuoteFetch);
      return true;
    }
    if (strcmp(var, "lastChartFetch") == 0) {
      snprintf(buf, len, "\"var\":\"lastChartFetch\",\"val\":%lu,\"last\":true",
               _s.lastChartFetch);
      return true;
    }
    if (strcmp(var, "fetchErrCount") == 0) {
      snprintf(buf, len, "\"var\":\"fetchErrCount\",\"val\":%u,\"last\":true",
               _s.fetchErrCount);
      return true;
    }
    if (strcmp(var, "fetchOkCount") == 0) {
      snprintf(buf, len, "\"var\":\"fetchOkCount\",\"val\":%u,\"last\":true",
               _s.fetchOkCount);
      return true;
    }
    if (strcmp(var, "quoteOkCount") == 0) {
      snprintf(buf, len, "\"var\":\"quoteOkCount\",\"val\":%u,\"last\":true",
               _s.quoteOkCount);
      return true;
    }
    if (strcmp(var, "chartLen") == 0) {
      snprintf(buf, len, "\"var\":\"chartLen\",\"val\":%u,\"last\":true",
               _s.chartLen);
      return true;
    }
    if (strcmp(var, "fetchFailed") == 0) {
      snprintf(buf, len, "\"var\":\"fetchFailed\",\"val\":%s,\"last\":true",
               _s.fetchFailed ? "true" : "false");
      return true;
    }
    if (strcmp(var, "heatmapCount") == 0) {
      snprintf(buf, len, "\"var\":\"heatmapCount\",\"val\":%u,\"last\":true",
               _s.heatmapData.count);
      return true;
    }
    for (int i = 0; i < 8; i++) {
      char key[16]; snprintf(key, sizeof(key), "stockTicker%d", i);
      if (strcmp(var, key) == 0) {
        snprintf(buf, len, "\"var\":\"%s\",\"val\":\"%s\",\"last\":true",
                 key, _s.tickers[i]);
        return true;
      }
    }
    return false;
  }

  bool dbgSet(const char* var, const char* val) {
    if (strcmp(var, "fetchFailed") == 0) {
      _s.fetchFailed = val && strcmp(val, "0") != 0;
      return true;
    }
    // TASK-247: force the launch-view mode so VE can deterministically exercise
    // List (0) / Chart (1) / Heatmap (2) regardless of persisted settings. Takes
    // effect on the next Stock launch/resume (resume() re-applies on mode change).
    if (strcmp(var, "stockMode") == 0) {
      int m = val ? atoi(val) : 0;
      if (m < 0 || m > 2) return false;
      g_settings.stockMode = (StockViewMode)m;
      return true;
    }
    if (strcmp(var, "fetchErrorCode") == 0) {
      _s.fetchErrorCode = val ? atoi(val) : 0;
      return true;
    }
    if (strcmp(var, "triggerFetch") == 0 && val && strcmp(val, "1") == 0) {
      _s.lastQuoteFetch = 0;
      _s.lastChartFetch = 0;
      _s.chartLen       = 0;
      _s.fetchFailed    = false;
      // TASK-300: also drop any parked (undelivered) chart result — "reset
      // chart fetch state" must include it, or the next drill-in's first tick
      // pops the stale result and the T178 placeholder check reads its len.
      dataTask::StockChartResult discard;
      dataTask::pollStockChart(&discard);
      return true;
    }
    if (strcmp(var, "fetchErrCount") == 0) {
      _s.fetchErrCount = 0;
      return true;
    }
    if (strcmp(var, "fetchOkCount") == 0) {
      _s.fetchOkCount = 0;
      return true;
    }
    if (strcmp(var, "quoteOkCount") == 0) {
      _s.quoteOkCount = 0;
      return true;
    }
    if (strcmp(var, "triggerHeatmap") == 0) {
      // Enter heatmap sub-view and trigger an immediate fetch (debug/testing).
      _s.prevSubView    = _s.subView;
      _s.subView        = StockSubView::HeatmapDetail;
      _s.lastHeatmapFetch = 0;  // force immediate fetch on next tick
      repaintHeatmap();
      return true;
    }
    return false;
  }

private:
  StockAppState _s = {};

  void repaintError() {
    tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xF800, TFT_BLACK);
    tft.setTextFont(2);
    tft.drawString("STOCK FETCH FAILED", 137, 100);
    char buf[24];
    snprintf(buf, sizeof(buf), "NET ERR  %d", _s.fetchErrorCode);
    tft.drawString(buf, 137, 125);
    tft.setTextColor(0x7BEF, TFT_BLACK);
    tft.setTextFont(1);
    tft.drawString("retrying in 60s...", 137, 150);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void repaintList() {
    if (_s.fetchFailed) { repaintError(); return; }
    tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(0xFFE0);
    tft.drawString("STOCK TERMINAL", ST_LIST_COL_SYMBOL, ST_LIST_HEADER_Y, 2);
    // Toggle button — tap to enter HeatmapDetail
    tft.setTextDatum(TR_DATUM);
    tft.setTextColor(0x07E0, TFT_BLACK);
    tft.drawString("HEAT>", ST_CANVAS_X2 - 2, ST_LIST_HEADER_Y, 2);
    tft.setTextDatum(TL_DATUM);
    tft.drawFastHLine(ST_LIST_COL_SYMBOL, ST_LIST_RULE_Y,
                      ST_CANVAS_X2 - ST_LIST_COL_SYMBOL, 0x4208);
    int yPos = ST_LIST_ROW_START_Y;
    for (int i = 0; i < STOCK_TICKER_COUNT; i++) {
      int base = yPos + 11;
      tft.setTextColor(0xFFFF);
      tft.drawString(_s.tickers[i], ST_LIST_COL_SYMBOL, base, 2);
      tft.setTextColor(0x07FF);
      tft.drawString(_s.lastQuoteFetch
                       ? formatStockPrice(_s.prices[i])
                       : String("---"),
                     ST_LIST_COL_PRICE, base, 2);
      tft.setTextDatum(TR_DATUM);
      if (!_s.lastQuoteFetch) {
        tft.setTextColor(0x7BEF);
        tft.drawString("---", ST_LIST_COL_CHANGE, base, 2);
      } else {
        tft.setTextColor((_s.changePct[i] >= 0) ? (uint16_t)0x07E0 : (uint16_t)0xF800);
        String pct = (_s.changePct[i] >= 0 ? String("+") : String(""))
                     + String(_s.changePct[i], 1) + "%";
        tft.drawString(pct, ST_LIST_COL_CHANGE, base, 2);
      }
      tft.setTextDatum(TL_DATUM);
      yPos += ST_LIST_ROW_H;
    }
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void repaintChart() {
    if (_s.fetchFailed) { repaintError(); return; }
    tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);

    // header: back glyph + ticker + price
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(0xFFFF);
    tft.drawString("<", 5, ST_CHART_HEADER_Y, 2);
    String hdr = String(_s.chartSymbol[0] ? _s.chartSymbol : _s.tickers[_s.chartTickerIdx]);
    hdr += (_s.chartLen > 0)
             ? (" " + formatStockPrice(_s.chartPoints[_s.chartLen - 1]))
             : " ---";
    tft.drawString(hdr, ST_CHART_TICKER_X, ST_CHART_HEADER_Y, 2);

    // range tabs
    static const char* TAB_LABELS[4] = {"1D","5D","1M","YTD"};
    for (int t = 0; t < 4; t++) {
      int tx = ST_CHART_TABS_X + t * ST_CHART_TAB_W;
      if ((uint8_t)_s.chartRange == (uint8_t)t)
        tft.fillRect(tx, ST_CHART_HEADER_Y, ST_CHART_TAB_W, ST_CHART_HEADER_H, 0x4208);
      tft.setTextDatum(MC_DATUM);
      tft.setTextColor(0xFFFF);
      tft.drawString(TAB_LABELS[t], tx + ST_CHART_TAB_W / 2, ST_CHART_HEADER_Y + 7, 2);
    }
    tft.setTextDatum(TL_DATUM);

    // plot area
    if (_s.chartLen < 2) {
      tft.drawFastHLine(0, ST_CHART_PLOT_Y + ST_CHART_PLOT_H / 2,
                        ST_CANVAS_X2 + 1, 0x07FF);
    } else {
      float xStep  = (float)ST_CANVAS_X2 / (_s.chartLen - 1);
      float rng    = _s.chartHi - _s.chartLo;
      if (rng < 0.001f) rng = 0.001f;
      float yScale = (float)(ST_CHART_PLOT_H - 2) / rng;
      for (int i = 1; i < (int)_s.chartLen; i++) {
        int x0 = (int)((i - 1) * xStep);
        int x1 = (int)(i       * xStep);
        int y0 = ST_CHART_PLOT_Y + ST_CHART_PLOT_H - 2
                 - (int)((_s.chartPoints[i - 1] - _s.chartLo) * yScale);
        int y1 = ST_CHART_PLOT_Y + ST_CHART_PLOT_H - 2
                 - (int)((_s.chartPoints[i]     - _s.chartLo) * yScale);
        tft.drawLine(x0, y0, x1, y1, 0x07FF);
      }
    }

    // footer
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(0x7BEF);
    if (_s.chartLen == 0) {
      tft.drawString("lo: ---", 5, ST_CHART_FOOTER_Y, 1);
      tft.setTextDatum(TR_DATUM);
      tft.drawString("hi: ---", ST_CANVAS_X2 - 5, ST_CHART_FOOTER_Y, 1);
    } else {
      tft.drawString(String("lo: ") + String(_s.chartLo, 2), 5, ST_CHART_FOOTER_Y, 1);
      tft.setTextDatum(TR_DATUM);
      tft.drawString(String("hi: ") + String(_s.chartHi, 2),
                     ST_CANVAS_X2 - 5, ST_CHART_FOOTER_Y, 1);
    }
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void drillToChart(uint8_t tickerIdx) {
    _s.prevSubView    = _s.subView;
    _s.chartTickerIdx = tickerIdx;
    _s.chartSymbol[0] = '\0';
    _s.chartRange     = StockRange::D1;
    _s.subView        = StockSubView::ChartDetail;
    // TASK-380: always fetch on drill-in, keyed to the tapped ticker — a prior
    // fetch for a DIFFERENT ticker within STOCK_CHART_FETCH_D1 previously made
    // this look "still fresh" via a recency-only guard and silently skipped
    // the request. Matches drillToChartBySym()/the tab-switch handler, which
    // already enqueue unconditionally on any symbol/range change.
    dataTask::enqueueStockChart(tickerIdx, (uint8_t)StockRange::D1);
    _s.lastChartFetch = millis();
    _pendingAsync      = true;
    _s.chartLen = 0; _s.chartLo = _s.chartHi = 0;
    repaintChart();
  }

  void drillToChartBySym(const char* sym, uint8_t rangeIdx) {
    _s.prevSubView = _s.subView;
    strncpy(_s.chartSymbol, sym, 7); _s.chartSymbol[7] = '\0';
    _s.chartRange  = (StockRange)rangeIdx;
    _s.subView     = StockSubView::ChartDetail;
    dataTask::enqueueStockChartBySym(sym, rangeIdx);
    _s.lastChartFetch = millis();
    _pendingAsync     = true;
    _s.chartLen = 0; _s.chartLo = _s.chartHi = 0;
    repaintChart();
  }

  void enterHeatmap() {
    _s.prevSubView = StockSubView::List;
    _s.subView     = StockSubView::HeatmapDetail;
    if (!_s.lastHeatmapFetch) {
      dataTask::enqueueHeatmapQuote();
      _s.lastHeatmapFetch = millis();
    }
    repaintHeatmap();
  }

  void backToPrevView() {
    _s.subView = _s.prevSubView;
    if (_s.subView == StockSubView::List)        _s.chartSymbol[0] = '\0';
    if (_s.subView == StockSubView::HeatmapDetail) _s.prevSubView = StockSubView::List;
    switch (_s.subView) {
      case StockSubView::List:          repaintList();    break;
      case StockSubView::HeatmapDetail: repaintHeatmap(); break;
      default:                          repaintList();    break;
    }
  }

  void computeHeatmapLayout() {
    uint8_t n = _s.heatmapData.count;
    if (n == 0) { _s.heatmapLayoutDirty = false; return; }
    if (n > 20) n = 20;

    // Insertion-sort order[] by marketCap descending
    uint8_t order[20];
    for (uint8_t i=0; i<n; i++) order[i]=i;
    for (uint8_t i=1; i<n; i++) {
      uint8_t k=order[i]; int j=i-1;
      while (j>=0 && _s.heatmapData.marketCap[order[j]] < _s.heatmapData.marketCap[k])
        { order[j+1]=order[j]; j--; }
      order[j+1]=k;
    }

    // Normalize weights to canvas area px²
    float total=0;
    for (uint8_t i=0; i<n; i++) total += _s.heatmapData.marketCap[order[i]];
    if (total == 0.0f) total = 1.0f;
    float wt[20];
    for (uint8_t i=0; i<n; i++)
      wt[i] = _s.heatmapData.marketCap[order[i]] / total * (275.0f * (float)(240 - ST_LIST_RULE_Y));

    // Squarified treemap — iterative strip layout (y=22..239, top row reserved for header)
    float rx=0, ry=ST_LIST_RULE_Y, rw=275, rh=240-ST_LIST_RULE_Y;
    uint8_t si=0;
    while (si < n && rw > 0.5f && rh > 0.5f) {
      bool horiz = (rh > rw);
      float slen = (rw < rh) ? rw : rh;

      float sum=0, smax=0, smin=1e30f;
      uint8_t ei = si;

      for (uint8_t i=si; i<n; i++) {
        float ns = sum + wt[i];
        float nx = (wt[i] > smax) ? wt[i] : smax;
        float ni = (i==si || wt[i] < smin) ? wt[i] : smin;
        float nw = (slen*slen*nx/(ns*ns) > ns*ns/(slen*slen*ni)) ?
                    slen*slen*nx/(ns*ns) : ns*ns/(slen*slen*ni);
        float ow = (i==si) ? 1e30f :
                   (slen*slen*smax/(sum*sum) > sum*sum/(slen*slen*smin) ?
                    slen*slen*smax/(sum*sum) : sum*sum/(slen*slen*smin));
        if (nw <= ow || i==si) { sum=ns; smax=nx; smin=ni; ei=i+1; }
        else break;
      }

      // Flush strip [si..ei) into remaining rect
      if (horiz) {
        float sh = sum / rw;
        float cx = rx;
        for (uint8_t i=si; i<ei; i++) {
          float tw = wt[i] / sh;
          HeatmapTile& t = _s.heatmapLayout[i];
          t.x = (int16_t)roundf(cx);
          t.y = (int16_t)roundf(ry);
          t.h = (int16_t)roundf(sh);
          t.w = (i==ei-1) ? (int16_t)(roundf(rx+rw) - t.x)
                           : (int16_t)(roundf(cx+tw) - t.x);
          t.tickerIdx = order[i];
          cx += tw;
        }
        ry += sh; rh -= sh;
      } else {
        float sw = sum / rh;
        float cy = ry;
        for (uint8_t i=si; i<ei; i++) {
          float th = wt[i] / sw;
          HeatmapTile& t = _s.heatmapLayout[i];
          t.x = (int16_t)roundf(rx);
          t.y = (int16_t)roundf(cy);
          t.w = (int16_t)roundf(sw);
          t.h = (i==ei-1) ? (int16_t)(roundf(ry+rh) - t.y)
                           : (int16_t)(roundf(cy+th) - t.y);
          t.tickerIdx = order[i];
          cy += th;
        }
        rx += sw; rw -= sw;
      }
      si = ei;
    }
    _s.heatmapLayoutDirty = false;
  }

  void repaintHeatmap() {
    tft.fillRect(0, ST_CANVAS_Y, ST_CANVAS_X2 + 1, ST_CANVAS_H, TFT_BLACK);
    // Header strip (y=0..21) — title left, LIST toggle right
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(0xFFE0, TFT_BLACK);
    tft.drawString("MKTCAP HEAT", ST_LIST_COL_SYMBOL, ST_LIST_HEADER_Y, 2);
    tft.setTextDatum(TR_DATUM);
    tft.setTextColor(0x07E0, TFT_BLACK);
    tft.drawString("<LIST", ST_CANVAS_X2 - 2, ST_LIST_HEADER_Y, 2);
    tft.setTextDatum(TL_DATUM);
    tft.drawFastHLine(ST_LIST_COL_SYMBOL, ST_LIST_RULE_Y,
                      ST_CANVAS_X2 - ST_LIST_COL_SYMBOL, 0x4208);
    if (!_s.heatmapData.ok && _s.heatmapData.errorCode == 0) {
      tft.setTextDatum(MC_DATUM);
      tft.setTextColor(0x7BEF, TFT_BLACK);
      tft.drawString("LOADING...", 137, 120, 2);
      tft.setTextDatum(TL_DATUM);
      tft.setTextColor(TFT_WHITE, TFT_BLACK);
      return;
    }
    if (!_s.heatmapData.ok) {
      tft.setTextDatum(MC_DATUM);
      tft.setTextColor(0xF800, TFT_BLACK);
      tft.drawString("HEATMAP FETCH FAILED", 137, 100, 2);
      char buf[20]; snprintf(buf, sizeof(buf), "ERR %d", _s.heatmapData.errorCode);
      tft.drawString(buf, 137, 125, 2);
      tft.setTextColor(0x7BEF, TFT_BLACK);
      tft.drawString("retry in 120s", 137, 150, 1);
      tft.setTextDatum(TL_DATUM);
      tft.setTextColor(TFT_WHITE, TFT_BLACK);
      return;
    }
    tft.setTextDatum(MC_DATUM);
    for (uint8_t i=0; i<_s.heatmapData.count; i++) {
      const HeatmapTile& t = _s.heatmapLayout[i];
      if (t.w <= 0 || t.h <= 0) continue;
      float pct = _s.heatmapData.changePct[t.tickerIdx];
      uint16_t col = heatmapColour(pct);
      tft.fillRect(t.x, t.y, t.w, t.h, col);
      tft.drawRect(t.x, t.y, t.w, t.h, 0x2104);
      int16_t cx = t.x + t.w / 2;
      int16_t cy = t.y + t.h / 2;
      tft.setTextColor(TFT_WHITE, col);
      const char* sym = _s.heatmapData.symbols[t.tickerIdx];
      char pb[10]; snprintf(pb, sizeof(pb), "%+.1f%%", pct);
      if (t.h >= HM_T1_H && t.w >= HM_T1_W) {
        tft.drawString(sym, cx, cy - 9, 2);
        tft.drawString(pb,  cx, cy + 9, 2);
      } else if (t.h >= HM_T2_H && t.w >= HM_T2_W) {
        tft.drawString(sym, cx, cy - 5, 2);
        tft.drawString(pb,  cx, cy + 9, 1);
      } else if (t.h >= HM_T3_H && t.w >= HM_T3_W) {
        tft.drawString(sym, cx, cy - 5, 1);
        tft.drawString(pb,  cx, cy + 5, 1);
      } else if (t.h >= HM_T4_H && t.w >= HM_T4_W) {
        tft.drawString(sym, cx, cy - 5, 1);
        tft.drawString(pb,  cx, cy + 5, 1);
      } else if (t.h >= HM_T5_H && t.w >= HM_T5_W && (size_t)(strlen(sym) * 6) <= (size_t)t.w) {
        tft.drawString(sym, cx, cy, 1);
      } else if (t.w >= HM_T6_MIN_W) {
        TFT_eSprite spr(&tft);
        uint8_t  slen = (uint8_t)strlen(sym);
        uint8_t  plen = (uint8_t)strlen(pb);
        uint16_t symW = (uint16_t)slen * 6;
        uint16_t pctW = (uint16_t)plen * 6;
        // After -90° rotation sprite-left→screen-bottom, sprite-right→screen-top.
        // Layout [pct|SEP|sym] so sym lands above pct on screen.
        bool showRotPct = (t.h >= (int16_t)(symW + HM_T6_SEP + pctW));
        uint16_t sprW   = showRotPct ? (pctW + HM_T6_SEP + symW) : symW;
        if (spr.createSprite(sprW, 8)) {
          spr.fillSprite(col);
          spr.setTextFont(1);
          spr.setTextColor(TFT_WHITE, col);
          if (showRotPct) {
            spr.drawString(pb,  0,                0, 1);
            spr.drawString(sym, pctW + HM_T6_SEP, 0, 1);
          } else {
            spr.drawString(sym, 0, 0, 1);
          }
          spr.setPivot(sprW / 2, 4);
          tft.setPivot(cx, cy);
          withViewportRepair(tft, t.x, t.y, t.w, t.h, [&]{
            spr.pushRotated(-90, col);
          });
          spr.deleteSprite();
        }
      }
    }
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }

  void stockTickHeatmap() {
    unsigned long now = millis();
    if (!_s.lastHeatmapFetch || now - _s.lastHeatmapFetch > STOCK_HEATMAP_FETCH_MS) {
      dataTask::enqueueHeatmapQuote();
      _s.lastHeatmapFetch = now;
    }
    dataTask::HeatmapQuoteResult r;
    if (dataTask::pollHeatmapQuote(&r)) {
      if (r.ok) {
        _s.heatmapData        = r;
        _s.heatmapLayoutDirty = true;
        _everHadData = true;   // TASK-245: first data → bar leaves amber
        _s.fetchFailed = false; // TASK-246: clear red on success
      } else if (!_s.heatmapData.ok) {
        // No good data yet — propagate error so screen shows it
        _s.heatmapData        = r;
        _s.heatmapLayoutDirty = true;
        _s.fetchFailed = true;  // TASK-246: failed heatmap fetch, no good data → red
      }
      // else: keep last good data on screen; transient fetch error is silently retried
      // (no red — we still have valid data to show)
    }
    if (_s.heatmapLayoutDirty) {
      computeHeatmapLayout();
      repaintHeatmap();
    }
  }

  void stockTickQuotes() {
    unsigned long now = millis();
    if (!_s.lastQuoteFetch || now - _s.lastQuoteFetch > STOCK_QUOTE_FETCH_MS) {
      dataTask::enqueue(dataTask::DATA_FETCH_STOCK_QUOTE);
      _s.lastQuoteFetch = now;
    }
    dataTask::StockQuoteResult r;
    if (dataTask::pollStockQuote(&r)) {
      if (r.ok) {
        for (int i = 0; i < STOCK_TICKER_COUNT; i++) {
          _s.prices[i]    = r.prices[i];
          _s.changePct[i] = r.changePct[i];
        }
        _s.fetchFailed    = false;
        _s.fetchErrorCode = 0;
        _s.quoteOkCount++;
        _everHadData = true;   // TASK-245: first data → bar leaves amber
      } else {
        _s.fetchFailed    = true;
        _s.fetchErrorCode = r.errorCode;
        _s.fetchErrCount++;
      }
      repaintList();
    }
  }

  void stockTickChart() {
    unsigned long now      = millis();
    unsigned long fetchMs  = (_s.chartRange == StockRange::D1)
                               ? STOCK_CHART_FETCH_D1 : STOCK_CHART_FETCH_SLOW;
    if (!_s.lastChartFetch || now - _s.lastChartFetch > fetchMs) {
      if (_s.chartSymbol[0])
        dataTask::enqueueStockChartBySym(_s.chartSymbol, (uint8_t)_s.chartRange);
      else
        dataTask::enqueueStockChart(_s.chartTickerIdx, (uint8_t)_s.chartRange);
      _s.lastChartFetch = now;
    }
    dataTask::StockChartResult r;
    if (dataTask::pollStockChart(&r)) {
      // TASK-300: a result parked while nobody was in chart view (back-out
      // before fetch returned, app switch, range change) can belong to a
      // superseded request — rendering it here shows the wrong symbol/range.
      // Discard on identity mismatch and keep waiting for our own fetch.
      const char* want = _s.chartSymbol[0] ? _s.chartSymbol
                                           : _s.tickers[_s.chartTickerIdx];
      if (strcmp(r.symbol, want) != 0 || r.rangeIdx != (uint8_t)_s.chartRange) {
        LOG_D("stock", "chart drop stale result sym=%s range=%u (want %s/%u)",
              r.symbol, r.rangeIdx, want, (unsigned)_s.chartRange);
        return;
      }
      _pendingAsync = false;
      if (r.ok) {
        memcpy(_s.chartPoints, r.points, r.len * sizeof(float));
        _s.chartLen       = r.len;
        _s.chartLo        = r.lo;
        _s.chartHi        = r.hi;
        _s.fetchFailed    = false;
        _s.fetchErrorCode = 0;
        _s.fetchOkCount++;
        _everHadData = true;   // TASK-245: first data → bar leaves amber
      } else {
        _s.fetchFailed    = true;
        _s.fetchErrorCode = r.errorCode;
        _s.fetchErrCount++;
      }
      repaintChart();
    }
  }
};
static StockApp g_StockApp;
static bool stockDbgGet(const char* v, char* b, int l) { return g_StockApp.dbgGet(v, b, l); }
static bool stockDbgSet(const char* v, const char* val) { return g_StockApp.dbgSet(v, val); }

#include "aquarium/aquariumApp.h"
static AquariumApp g_AquariumApp;

#include "teletextApp.h"
static TeletextApp g_TeletextApp;
static bool teletextDbgGet(const char* v, char* b, int l) { return g_TeletextApp.dbgGet(v, b, l); }
static bool teletextDbgSet(const char* v, const char* val) { return g_TeletextApp.dbgSet(v, val); }

#include "planeRadarApp.h"
static PlaneRadarApp g_PlaneRadarApp;
static bool planeRadarDbgGet(const char* v, char* b, int l) { return g_PlaneRadarApp.dbgGet(v, b, l); }
static bool planeRadarDbgSet(const char* v, const char* val) { return g_PlaneRadarApp.dbgSet(v, val); }

#ifdef WINAMP_DISPLAY
#include "webRadioApp.h"
static WebRadioApp g_WebRadioApp;
static bool webRadioDbgGet(const char* v, char* b, int l) { return g_WebRadioApp.dbgGet(v, b, l); }
static bool webRadioDbgSet(const char* v, const char* val) { return g_WebRadioApp.dbgSet(v, val); }

#include "localPlayerApp.h"
static LocalPlayerApp g_LocalPlayerApp;   // TASK-413: placeholder, real UI is TASK-415+
#endif

#ifdef SERIAL_DEBUG
static bool matrixDbgGet(const char* v, char* b, int l)   { return g_MatrixApp.dbgGet(v, b, l); }
static bool lifeDbgGet(const char* v, char* b, int l)     { return g_LifeApp.dbgGet(v, b, l); }
static bool cryptoDbgGet(const char* v, char* b, int l)   { return g_CryptoApp.dbgGet(v, b, l); }
static bool aquariumDbgGet(const char* v, char* b, int l) { return g_AquariumApp.dbgGet(v, b, l); }
#endif

// ── App registry + shell gesture state (TASK-090f) ────────────────────

#ifdef WINAMP_DISPLAY
App* g_apps[(int)AppId::COUNT] = {
#define APP_X(Name, icon, cfg, disp) &g_##Name##App,
#include "appRegistry.h"
#undef APP_X
};
#else
App* g_apps[(int)AppId::COUNT] = {};
#endif

static bool          s_inGesture  = false;
static int           s_lastTouchX = 0, s_lastTouchY = 0;
static unsigned long s_cooldownMs = 0;

// ── Shell busy state (M-TOUCH-UX TASK-115b) ───────────────────────────────
static bool          g_shellBusy      = false;
static unsigned long g_shellBusySetMs = 0;
static constexpr unsigned long SHELL_BUSY_TIMEOUT_MS = 3000;

namespace shell {
// TASK-245 / ADR-046: error state of the currently-active app — drives the red
// active-bar (precedence error > busy/connecting > idle). Owned by the app
// instance, so it survives app switch and is re-read on every repaint.
inline bool activeError() {
    return g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->hasError();
}
// TASK-245 amendment / ADR-046: connecting state of the active app — amber bar
// until the app's first data result resolves (boot reads amber, not green).
inline bool activeConnecting() {
    return g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->isConnecting();
}
// Sets busy flag and immediately repaints only the active-slot indicator.
void setBusy(bool busy) {
    g_shellBusy = busy;
    if (busy) g_shellBusySetMs = millis();
    renderActiveIndicator(tft, currentAppId,
                          winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                          busy, activeError(), activeConnecting());
}
}

// TASK-413 / ADR-059 D6: the three player-mode AppIds, and the reverse lookup.
static inline AppId appIdForPlayerMode(uint8_t mode) {
  switch ((PlayerMode)mode) {
    case PlayerMode::WebRadio: return AppId::WebRadio;
    case PlayerMode::Player:   return AppId::LocalPlayer;
    default:                   return AppId::Spotify;
  }
}
static inline bool isPlayerModeApp(AppId id) {
  return id == AppId::Spotify || id == AppId::WebRadio || id == AppId::LocalPlayer;
}

// TASK-259/260/413: the taskbar "player" slot (AppId::Spotify) restores whichever
// player mode (Spotify | WebRadio | Player) was last active — read from the
// persisted setting. WebRadio/LocalPlayer are eject-only / excluded from the
// taskbar, so a taskbar tap only ever surfaces AppId::Spotify here; we redirect to
// the persisted mode's app.
static AppId resolvePlayerSlot(AppId tapped) {
  if (tapped != AppId::Spotify) return tapped;
  return appIdForPlayerMode(g_settings.playerMode);
}

// TASK-260 §4: persist the player mode, immediate-save with an unchanged-value skip
// (flash-wear). Called from the eject toggles in both directions (the Settings UI
// writes g_settings.playerMode + saveSettings() directly via its own cycle handler).
void persistPlayerMode(uint8_t mode) {
  if (g_settings.playerMode == mode) return;   // unchanged-value skip
  g_settings.playerMode = mode;
  SettingsStorage::save();
}

// TASK-413 / ADR-059 D6 (amended DEV-1): the player slot's taskbar tap has a
// second meaning no other slot has — restore the persisted mode when tapped from
// another app, but CYCLE (Spotify -> WebRadio -> Player -> Spotify) and persist
// when tapped while the player is already active. switchApp() early-returns on
// same-app, and the two dispatch sites that can land a tap on this slot
// (shellTbRelease() below, and cmdTap()'s SERIAL_DEBUG "tap" injection) guard
// same-app differently — so this decision lives in ONE shared helper called from
// both, not duplicated into either. Non-player-slot taps pass through unchanged.
static AppId resolvePlayerTap(AppId tapped, bool playerAlreadyActive) {
  if (tapped != AppId::Spotify) return tapped;
  if (!playerAlreadyActive) return resolvePlayerSlot(tapped);
  uint8_t next = (g_settings.playerMode + 1) % 3;
  persistPlayerMode(next);
  return appIdForPlayerMode(next);
}

// ── Taskbar tap feedback (M-TASKBAR-FEEDBACK / TASK-279) ──────────────────
// Single shared helper set [VE-3-1 + DEV-3-6]: paint + stable-prefix log live here,
// invoked from BOTH dispatch sites (appHandleInput and drainInjectionQueue) so the
// injected path the measurement plan depends on cannot drift from production.
// Press-anchored commit [DEV-3-2]: the slot captured at Press is also the slot the
// tap commits — release-y is never re-resolved (resistive-panel jitter inside the
// dead zone could otherwise highlight slot A and switch slot B).
static int s_tbPressedSlot = -1;  // visible slot highlighted at Press; -1 = none
static int s_tbPressedApp  = -1;  // press-anchored app index (highlight == commit)

// F-a: pressed-slot highlight, same loop iteration as the Press sample.
static void shellTbPress(int y) {
  int slot = y / TASKBAR_SLOT_H;
  if (slot < 0 || slot >= TASKBAR_SLOT_COUNT) return;  // y is 0..239 → 0..5, defensive
  s_tbPressedSlot = slot;
  s_tbPressedApp  = (winampDisplay.tbScrollOffset() + slot) % TASKBAR_APP_COUNT;
  renderTaskbarSlot(tft, slot, currentAppId,
                    winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                    g_shellBusy, shell::activeError(), shell::activeConnecting(),
                    /*pressed=*/true);
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] tb-press slot=%d\n", slot);
#endif
}

// F-a: cancel the highlight — scroll-start (dead zone exceeded) or a tap that
// resolves to the already-active app. Idempotent.
static void shellTbCancel() {
  if (s_tbPressedSlot < 0) return;
  renderTaskbarSlot(tft, s_tbPressedSlot, currentAppId,
                    winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                    g_shellBusy, shell::activeError(), shell::activeConnecting(),
                    /*pressed=*/false);
  s_tbPressedSlot = -1;
  s_tbPressedApp  = -1;
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] tb-press-cancel\n");
#endif
}

// F-b: transient amber bar on the tapped (press-anchored) slot, painted BEFORE
// switchApp()'s heavy work — never a reverse app→slot lookup [QM-3-1]:
// resolvePlayerSlot() can return WebRadio, which deliberately has no slot (LL-085).
// switchApp()'s final renderTaskbar overwrites it with the real state.
static void shellTbCommit(int slot) {
  if (slot < 0 || slot >= TASKBAR_SLOT_COUNT) return;
  tft.fillRect(TASKBAR_X, slot * TASKBAR_SLOT_H, 3, TASKBAR_SLOT_H, TASKBAR_BUSY_COLOR);
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] tb-commit slot=%d\n", slot);
#endif
}

// Shared taskbar-release resolution — both dispatch sites call this so tap commit,
// press-anchoring, and the feedback paints stay identical [VE-3-1].
static void shellTbRelease(int releaseY) {
  const int pressedSlot = s_tbPressedSlot;
  const int pressedApp  = s_tbPressedApp;
  int appIdx = (int)currentAppId;
  if (winampDisplay.tbGestureEnd(releaseY, TASKBAR_APP_COUNT, &appIdx)) {
    if (pressedApp >= 0) appIdx = pressedApp;  // press-anchored commit [DEV-3-2]
    // TASK-413: cycle when the player slot is tapped while already active, restore
    // otherwise — resolvePlayerTap() owns both decisions (ADR-059 D6).
    AppId target = resolvePlayerTap(static_cast<AppId>(appIdx), isPlayerModeApp(currentAppId));
    if (target != currentAppId) {
      s_tbPressedSlot = -1;
      s_tbPressedApp  = -1;
      shellTbCommit(pressedSlot);
      switchApp(target);
      return;
    }
  }
  shellTbCancel();  // no-switch tap or scroll release: restore if still highlighted
}

void switchApp(AppId next) {
  if (next == currentAppId) return;
  const unsigned long t0 = millis();  // TASK-279 (L-d): per-phase instrumentation
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] leaving %d  heap=%lu maxAlloc=%lu minFree=%lu\n",
    (int)currentAppId,
    (unsigned long)ESP.getFreeHeap(),
    (unsigned long)ESP.getMaxAllocHeap(),
    (unsigned long)ESP.getMinFreeHeap());
  const int fromApp = (int)currentAppId;
#endif
  if (g_apps[(int)currentAppId]) g_apps[(int)currentAppId]->suspend();
  shell::setBusy(false);   // clear before new taskbar paint (TASK-115e)
  const unsigned long tSuspend = millis();
  tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
  const unsigned long tWipe = millis();
  if (next == AppId::Settings) g_previousAppId = currentAppId;
  currentAppId = next;
  // TASK-260: the player mode is NOT tracked here — it is written only by the deliberate
  // eject toggles + Settings UI (persistPlayerMode / _cyclePlayer). Tracking navigation
  // would clobber the persisted mode at boot, since v1 boots to the Spotify view.
  // TASK-264 (Q3-a): drop Spotify TLS when WebRadio is active (reclaims ~50 K arena).
  // Non-blocking — setWebRadioActive() only sets flags, never calls tlsYield().
#ifndef DISABLE_SPOTIFY
  spotifyTask::setWebRadioActive(next == AppId::WebRadio);
#endif
  if (g_apps[(int)next]) {
    if (!g_appLaunched[(int)next]) {
      g_appLaunched[(int)next] = true;
      g_apps[(int)next]->init();
    } else {
      g_apps[(int)next]->resume();
    }
  }
  const unsigned long tInit = millis();
#ifdef SERIAL_DEBUG
  // Keep this line's position (before renderTaskbar): the E0/E1 tap-to-switch-committed
  // clock is defined against it (M-TASKBAR-FEEDBACK §Measurement plan).
  Serial.printf("[shell] entered %d  heap=%lu maxAlloc=%lu minFree=%lu\n",
    (int)next,
    (unsigned long)ESP.getFreeHeap(),
    (unsigned long)ESP.getMaxAllocHeap(),
    (unsigned long)ESP.getMinFreeHeap());
#endif
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
  const unsigned long tEnd = millis();
  perf::record("shell.switch", tEnd - t0);  // 10th of MAX_PATHS=10 — see perf.h budget
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] switch %d->%d suspend=%lums wipe=%lums init=%lums "
                "taskbar=%lums total=%lums\n",
                fromApp, (int)next, tSuspend - t0, tWipe - tSuspend, tInit - tWipe,
                tEnd - tInit, tEnd - t0);
#endif
}

void appHandleInput(AppId) {
  bool touched = ts.touched();
  if (touched) {
    CYD28_TS_Point p = ts.getPointScaled();
    spotifyTask::resetBackoff();
    if (p.x >= TASKBAR_X) {
      if (s_inGesture && g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, s_lastTouchX, s_lastTouchY);
        s_inGesture = false;
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
      }
      s_lastTouchY = p.y;  // track for release
      if (winampDisplay.tbIsDragging()) {
        if (winampDisplay.tbGestureContinue(p.y, TASKBAR_APP_COUNT))
          renderTaskbar(tft, currentAppId,
                        winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                        false, shell::activeError(), shell::activeConnecting());
        // TASK-279 (F-a): scroll started (dead zone exceeded) → cancel the press
        // highlight. tbIsScrolling() is the DEV-3-1 accessor; idempotent after
        // the first cancel.
        if (winampDisplay.tbIsScrolling()) shellTbCancel();
      } else {
        winampDisplay.tbGesturePress(p.y);
        shellTbPress(p.y);  // TASK-279 (F-a): highlight in the same iteration
      }
      return;
    }
    // TASK-384: a pure-navigation tap bypasses the busy gate (see
    // isNavigationTap()'s doc comment) — cooldown debounce still applies.
    bool navTapBypass = g_apps[(int)currentAppId] &&
                         g_apps[(int)currentAppId]->isNavigationTap(p.x, p.y);
    if (!s_inGesture && (millis() <= s_cooldownMs || (g_shellBusy && !navTapBypass))) return;
    s_lastTouchX = p.x; s_lastTouchY = p.y;
    if (!s_inGesture) {
      s_inGesture = true;
      if (g_apps[(int)currentAppId]) {
        bool consumed = g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Press, p.x, p.y);
        if (consumed) s_cooldownMs = millis() + 200;
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
#ifdef TOUCH_DEBUG_OVERLAY
        g_touchDebug.onTouch(p.x, p.y);
#endif
      }
    } else {
      if (g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(TouchPhase::Move, p.x, p.y);
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
#ifdef TOUCH_DEBUG_OVERLAY
        g_touchDebug.onTouch(p.x, p.y);
#endif
      }
    }
  } else {
    if (winampDisplay.tbIsDragging()
#ifdef SERIAL_DEBUG
        && !winampDisplay._injectingDrag
#endif
    ) {
      shellTbRelease(s_lastTouchY);  // TASK-279: shared commit path [VE-3-1]
      s_cooldownMs = millis() + 300;
    } else if (s_inGesture) {
      s_inGesture = false;
      if (g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, s_lastTouchX, s_lastTouchY);
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
      }
      s_cooldownMs = millis() + 200;
    }
  }
}

void appTick(AppId id) {
  g_ledFlow.tick();
  g_backlight.tick();   // WIRE2-G5: auto-brightness in every app, not just Settings→Display
  g_keyboard.tick();
  if (g_apps[(int)id]) g_apps[(int)id]->tick();
}

#ifdef SD_BOOT_MOUNT
static void sdProbeBootMount();  // TASK-408: defined ahead of the SERIAL_DEBUG command
                                  // block (TASK-427), called from setup()
#endif

void setup()
{
  // Extend TWDT from 5→15s: dataTask TLS handshakes (webradio station list,
  // stock quotes) can take 6-10s on cold start and starve the CPU0 idle task.
  // SpotifyTask avoids this via tlsYield(), but dataTask has no such mechanism.
  // esp_task_wdt_init() is a no-op when already initialized; must deinit first.
  esp_task_wdt_deinit();
  esp_task_wdt_init(15, true);
  esp_task_wdt_add(NULL);  // re-subscribe loopTask (current task)
  esp_task_wdt_add(xTaskGetIdleTaskHandleForCPU(0));  // re-subscribe CPU0 idle

  // TASK-410 / ADR-059 D12: capture loopTask's own handle once, here — setup()
  // runs on loopTask, same task loop() will run on for the rest of the process
  // lifetime. audioEngine.h's aeDrainEof() asserts against this.
  g_loopTaskHandle = xTaskGetCurrentTaskHandle();

  Serial.begin(115200);

#ifdef SD_BOOT_MOUNT
  // TASK-408 (2026-08-07): mount SD here, synchronously, and hold the session for
  // the process lifetime — NOT the lazy per-mode-entry mount M-SDFS §5 assumes.
  //
  // `SD.begin()` needs ONE contiguous byte-addressable internal block of
  // `sizeof(vfs_fat_ctx_t) + max_files * sizeof(FIL)` (see kSdMaxFiles). At boot that
  // is trivial — the largest free 8-bit block is ~110 KB. Once WebRadio is playing it
  // is ~5 KB, and the mount fails with `esp_vfs_fat_register` → ESP_ERR_NO_MEM, which
  // is that calloc failing and NOT (as first read) the FF_VOLUMES table being full.
  // DUT-reproduced both ways: mounts at every heap state above the ctx size, fails at
  // every state below it, at every max_files setting. `sdmem` prints both numbers.
  //
  // So a lazy mount is only ever as reliable as the heap happens to be at the moment
  // the user enters the mode, and LocalPlayer needs the card mounted *and* the Helix
  // arena acquired at the same time. Mounting before any of that exists is the design,
  // not a workaround.
  //
  // TASK-427: gated on SD_BOOT_MOUNT, not SERIAL_DEBUG — production (cyd2usb_winamp)
  // does not define it and never mounts (sdReady() stubs to false there); the dedicated
  // cyd2usb_player variant and cyd2usb_winamp_debug both define it.
  sdProbeBootMount();
#endif

  // TASK-267: arena is acquired JIT in WebRadioApp::_play(), NOT at boot (so the
  // station fetch isn't starved — TASK-265). Boot baseline probe (debug-only).
  mb_heap_probe("boot-baseline");

  // serialdbg-001 (TASK-056b): unconditional boot banner. Carved out of the
  // SERIAL_DEBUG gate per ADR-021 Decision 4 as a production-safe diagnostic
  // — gives any host (test rig or end user) a deterministic way to confirm
  // which firmware is actually flashed without round-tripping a command.
  // GIT_REV comes from scripts/inject_git_hash.py; "n/a" when undefined
  // (e.g. non-debug envs that skip the pre-script).
  {
    const esp_app_desc_t *d = esp_ota_get_app_description();
    char elf[9];
    snprintf(elf, sizeof(elf), "%02x%02x%02x%02x",
             d->app_elf_sha256[0], d->app_elf_sha256[1],
             d->app_elf_sha256[2], d->app_elf_sha256[3]);
    Serial.printf("[boot] git=%s elf=%s build=%s %s\n",
#ifdef GIT_REV
        GIT_REV,
#else
        "n/a",
#endif
        elf, __DATE__, __TIME__);
  }

#ifdef SERIAL_DEBUG
  // ADR-042 E1: suppress verbose HTTPClient log that garbles serial JSON responses.
  esp_log_level_set("HTTPClient",  ESP_LOG_NONE);
  esp_log_level_set("HTTP_CLIENT", ESP_LOG_NONE);
#endif
  logsink::begin();

  spotifyDisplay->displaySetup(&spotify);

#ifdef NFC_ENABLED
  if (nfcSetup(&spotify, spotifyDisplay))
  {
    Serial.println("NFC Good");
  }
  else
  {
    Serial.println("NFC Bad");
  }
#endif

  bool spiffsInitSuccess = SPIFFS.begin(false) || SPIFFS.begin(true);
  if (!spiffsInitSuccess)
  {
    Serial.println("SPIFFS initialisation failed!");
    while (1)
      yield();
  }
  Serial.println("\r\nInitialisation done.");

  // settings-001: load persisted settings, then set up backlight PWM.
  // tft.init() (inside displaySetup above) uses digitalWrite(TFT_BL, HIGH) —
  // no LEDC channel is configured. Take over GPIO21 now so ledcWrite() works.
  SettingsStorage::load();
  TouchCalStorage::load();
  if (g_calData.valid)
    ts.setCalibration(g_calData.xMin, g_calData.xMax, g_calData.yMin, g_calData.yMax);
  analogReadResolution(12);        // TASK-151: ensure 12-bit ADC for LDR on GPIO34
  ledcSetup(0, 5000, 8);           // 5 kHz, 8-bit — channel 0 matches TFT_LEDC_CHANNEL
  ledcAttachPin(TFT_BL, 0);        // redirect GPIO21 from digital to LEDC
  // WIRE2-G5: owner applies the stored mode before first frame — honours
  // dispAuto (one LDR sample → mapped duty) instead of unconditionally
  // applying the manual dispLevel like the old inline block did.
  g_backlight.applyMode();
  // RGB LED channels (ch1=R/GPIO4, ch2=G/GPIO16, ch3=B/GPIO17).
  ledcSetup(LED_R_CH, 5000, 8); ledcAttachPin(LED_R_PIN, LED_R_CH);
#if !NFC_ENABLED
  ledcSetup(LED_G_CH, 5000, 8); ledcAttachPin(LED_G_PIN, LED_G_CH);
#endif
  ledcSetup(LED_B_CH, 5000, 8); ledcAttachPin(LED_B_PIN, LED_B_CH);
  g_ledFlow.applyMode();

#ifdef WINAMP_DISPLAY
  // M-BOOT-UI (TASK-364, ADR-055 decision 1): paint the Winamp chrome now —
  // a flash-resident composite blit, no heap/network cost — instead of
  // leaving the screen solid black through the WiFi/NTP phases below. This
  // is an *additional* direct call to the renderer, not a reorder of the
  // existing g_apps[(int)AppId::Spotify]->init() + renderTaskbar() block
  // further down (main.cpp ~2415) — that block is unchanged, and its
  // second pass becomes a harmless, idempotent repaint (design doc §1).
  winampDisplay.showDefaultScreen();
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
  winampDisplay.setTitle("STARTING UP...");
#endif

  refreshToken[0] = '\0';
  fetchConfigFile(refreshToken, clientId, clientSecret);

  // TASK-274 (M-WIFI-DIAG): link-event ground truth. Must register before the
  // first WiFi.begin() below or early events (incl. the boot-window drop E1)
  // are missed. Ships in all builds — [wifi-ev] is a stable log contract.
  wifiDiag::begin();

  // WiFi boot: NVS credentials → saved networks (/wifi_networks.json, or
  // legacy single-entry /wifi_creds.json pre-migration) → open WiFi settings.
  // Priority chain mirrors WifiSection connect flow (C4: NVS-backed persist).
  // TASK-296: wifiCredsKnown tracks whether ANY source held credentials —
  // "connect failed with stored creds" (AP storm at boot) must not be treated
  // as "no credentials", or the device parks dead in the Settings screen.
  // TASK-404: this used to also try a HARDCODED_WIFI_SSID stage ahead of NVS,
  // sourced from a wifi_creds.h shim — removed 2026-08-06 after discovering
  // that shim was never actually wired into the build (wrong file path, no
  // #include anywhere), making the whole stage permanently dead code. NVS is
  // the real first stage now.
  bool wifiConnected  = false;
  bool wifiCredsKnown = false;
  {
#ifdef WINAMP_DISPLAY
    winampDisplay.setTitle("WI-FI: CONNECTING...");  // M-BOOT-UI (TASK-364) §2
#endif
    WiFi.persistent(true);
    WiFi.mode(WIFI_STA);
    // TASK-296: driver is up after mode() — a non-empty stored SSID means NVS
    // holds credentials even if the connect window below expires.
    wifi_config_t nvsCfg;
    if (esp_wifi_get_config(WIFI_IF_STA, &nvsCfg) == ESP_OK && nvsCfg.sta.ssid[0] != 0)
      wifiCredsKnown = true;
    WiFi.begin();  // reconnect from NVS (no args)
    { unsigned long dl = millis() + 10000;
      // TASK-288: feed the TWDT every iteration — this loop's own deadline can
      // chain into the SPIFFS fallback loop below with zero resets in
      // between, so cumulative un-fed time (not any single loop's deadline)
      // is what was tripping task_wdt during a flaky-AP boot.
      while (WiFi.status() != WL_CONNECTED && millis() < dl) {
        delay(100); esp_task_wdt_reset();
#ifdef WINAMP_DISPLAY
        winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
#endif
      } }
    wifiConnected = (WiFi.status() == WL_CONNECTED);
  }
  if (!wifiConnected) {
    // TASK-404: the NVS attempt above leaves autoReconnect at its default
    // true, so a failed attempt keeps retrying the same (bad) NVS creds in
    // the background (WiFiGeneric.cpp's STA_DISCONNECTED handler calls
    // WiFi.disconnect()+WiFi.begin() itself on every reconnectable-reason
    // disconnect). If the SPIFFS stage below calls its own WiFi.begin()
    // while that background retry is still mid-attempt, esp_wifi_connect()
    // returns ESP_ERR_WIFI_CONN ("sta is connecting, return error") and the
    // SPIFFS attempt silently no-ops — the fallback cascade doesn't actually
    // try the SPIFFS creds until the background retry happens to be between
    // attempts, which is why recovery only reliably happened via the
    // separate background wifiDiag supervisor ~60-85s later. Stop the NVS
    // stage's background retry and let the driver settle before handing
    // control to SPIFFS's own explicit attempt.
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false);
    { unsigned long dl = millis() + 300;
      while (millis() < dl) { delay(20); esp_task_wdt_reset(); }
    }
    // TASK-426: a full driver stop/start here (WIFI_OFF → WIFI_STA, confirmed
    // by STA_STOP/STA_START in the event log) was tried and does NOT help — the
    // first candidate still failed at ~2.7 s. So the cross-stage problem is not
    // an in-flight scan surviving into the next stage, and lengthening this
    // settle is not the fix. See the per-candidate retry below for what is.
  }
  if (!wifiConnected) {
    // Gather saved-network candidates from two merged sources:
    //  - /wifi_networks.json: TASK-401's saved-network store (up to
    //    WIFI_MAX_SAVED entries), tried most-recently-used first, so a
    //    renamed/rotated AP that's still in the saved list gets found
    //    without a trip through Settings.
    //  - /wifi_creds.json: the operator-facing provisioning file (run/setup,
    //    or a hand-pushed SPIFFS image per the "pre-baked SPIFFS files" doc'd
    //    workflow). Always merged in at highest priority, even when
    //    /wifi_networks.json already has entries — it's the file a human
    //    just edited/pushed to fix a credential, and the saved-network list
    //    can otherwise sit stale (e.g. across an SSID rename) until
    //    Settings->WiFi is opened and reconnects manually.
    // +1 sizing: /wifi_creds.json's entry can add one candidate beyond
    // WIFI_MAX_SAVED's cap on /wifi_networks.json entries (dedup'd by SSID,
    // so it only ever adds — never evicts — a saved entry).
    SavedWifiNet cand[WIFI_MAX_SAVED + 1];
    uint8_t candCount = 0;
    if (SPIFFS.exists(WIFI_NETWORKS_JSON)) {
      File f = SPIFFS.open(WIFI_NETWORKS_JSON, "r");
      if (f) {
        DynamicJsonDocument doc(kWifiNetworksJsonCapacity);
        if (deserializeJson(doc, f) == DeserializationError::Ok) {
          for (JsonVariantConst v : doc["networks"].as<JsonArrayConst>()) {
            if (candCount >= WIFI_MAX_SAVED) break;
            const char* ssid = v["ssid"] | "";
            if (!ssid[0]) continue;
            strlcpy(cand[candCount].ssid, ssid, sizeof(cand[0].ssid));
            strlcpy(cand[candCount].pass, v["pass"] | "", sizeof(cand[0].pass));
            cand[candCount].lastUsedMs = v["lastUsedMs"] | 0UL;
            candCount++;
          }
        }
        f.close();
      }
    }
    if (SPIFFS.exists("/wifi_creds.json")) {
      File f = SPIFFS.open("/wifi_creds.json", "r");
      if (f) {
        StaticJsonDocument<256> doc;
        if (deserializeJson(doc, f) == DeserializationError::Ok) {
          const char* ssid = doc["ssid"] | "";
          if (ssid[0]) {
            int8_t existing = -1;
            for (uint8_t i = 0; i < candCount; i++) {
              if (strcmp(cand[i].ssid, ssid) == 0) { existing = (int8_t)i; break; }
            }
            uint8_t slot = (existing >= 0) ? (uint8_t)existing : candCount;
            if (existing >= 0 || candCount < WIFI_MAX_SAVED + 1) {
              strlcpy(cand[slot].ssid, ssid, sizeof(cand[0].ssid));
              strlcpy(cand[slot].pass, doc["pass"] | "", sizeof(cand[0].pass));
              cand[slot].lastUsedMs = 0xFFFFFFFFUL;  // always tried first
              if (existing < 0) candCount++;
            }
          }
        }
        f.close();
      }
    }
    // Most-recently-used first (small N — plain insertion sort). Best-effort:
    // saved lastUsedMs values are millis()-since-boot from whichever session
    // last wrote them, so cross-boot ordering is a heuristic, not a true
    // timestamp compare — /wifi_creds.json's sentinel above is exempt, it's
    // always meant to sort first.
    for (uint8_t i = 1; i < candCount; i++) {
      SavedWifiNet key = cand[i];
      int8_t j = i - 1;
      while (j >= 0 && cand[j].lastUsedMs < key.lastUsedMs) {
        cand[j + 1] = cand[j];
        j--;
      }
      cand[j + 1] = key;
    }
    if (candCount > 0) wifiCredsKnown = true;  // TASK-296

    // TASK-426: hand the (already MRU-sorted) candidates to the supervisor so
    // its kicks target real SSIDs instead of replaying whatever config the
    // cascade below happens to leave resident. Registered before the attempts
    // so a supervisor armed on ANY exit path from here has them.
    wifiDiag::superviseClearCandidates();
    for (uint8_t i = 0; i < candCount; i++)
      wifiDiag::superviseAddCandidate(cand[i].ssid, cand[i].pass);

    const char* connectedSsid = nullptr;
    const char* connectedPass = nullptr;
    for (uint8_t i = 0; i < candCount && !wifiConnected; i++) {
#ifdef WINAMP_DISPLAY
      winampDisplay.setTitle("WI-FI: CONNECTING...");  // M-BOOT-UI (TASK-364) §2
#endif
      Serial.printf("[wifi] Connecting from saved networks (%u/%u): %s\n",
                    (unsigned)(i + 1), (unsigned)candCount, cand[i].ssid);
      WiFi.persistent(false);  // don't corrupt NVS if creds are wrong (TASK-167)
      WiFi.mode(WIFI_STA);
      WiFi.begin(cand[i].ssid, cand[i].pass);
      // Bounded per-candidate probe: trimmed from the old single-network 30s
      // window so a full sweep of stale saved networks stays bounded (up to
      // WIFI_MAX_SAVED=5 candidates * 10s = 50s worst case, vs. 150s at the
      // old per-network timeout would have cost). A real, present AP
      // associates in ~1s per the TASK-404 boot log; NO_AP_FOUND retries
      // fire every ~2.4s, so 10s covers several rejection cycles before
      // moving on, not a hair trigger.
      { unsigned long dl = millis() + 10000;
        // TASK-426: auto-reconnect is off for the whole cascade (TASK-404's
        // fix for cross-stage collisions), which has the side effect that a
        // candidate gets exactly ONE connect attempt — nothing re-issues it.
        // A transient NO_AP_FOUND therefore burns the rest of the 10 s window
        // as dead air. Measured with a stale SSID in NVS: the first attempt for
        // the live AP failed ~2.7 s in, then the window idled to 10 s and the
        // cascade gave up, while the very next attempt at the SAME ssid (via
        // auto-reconnect, once re-armed) associated. Re-issue on each observed
        // failure instead, using discCount as the "that attempt finished" edge.
        uint32_t seenDisc = wifiDiag::discCount;
        const bool casNoRetry = casRetryDisabled();
        Serial.printf("[wifi] cascade retry %s\n",
                      casNoRetry ? "DISABLED (A/B control)" : "on");
        // TASK-288: see hardcoded-SSID loop above — feed TWDT every iteration.
        while (WiFi.status() != WL_CONNECTED && millis() < dl) {
          delay(250); Serial.print("."); esp_task_wdt_reset();
          if (!casNoRetry && wifiDiag::discCount != seenDisc) {
            seenDisc = wifiDiag::discCount;
            if (millis() < dl) { Serial.print("r"); WiFi.begin(cand[i].ssid, cand[i].pass); }
          }
#ifdef WINAMP_DISPLAY
          winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
#endif
        }
        Serial.println(); }
      if (WiFi.status() == WL_CONNECTED) {
        wifiConnected = true;
        connectedSsid = cand[i].ssid;
        connectedPass = cand[i].pass;
      } else {
        WiFi.disconnect(false);
      }
    }

    if (wifiConnected) {
      WiFi.persistent(true);
      WiFi.begin(connectedSsid, connectedPass);  // persist verified creds to NVS
#ifdef WINAMP_DISPLAY
      winampDisplay.setTitle("WI-FI: CONNECTING...");  // M-BOOT-UI (TASK-364) §2, re-assoc settle
#endif
      // TASK-290: this re-begin DEAUTHS the just-verified association
      // (observed [wifi-ev] reason=8 ~150ms after GOT_IP) and the code
      // below read localIP() before re-association finished — boot
      // proceeded with "IP address: 0.0.0.0" whenever the NVS attempt
      // missed its window and this saved-network path ran. Wait (bounded,
      // TWDT-fed per TASK-288) for the re-association to settle.
      { unsigned long dl = millis() + 15000;
        while (WiFi.status() != WL_CONNECTED && millis() < dl) {
          delay(100); esp_task_wdt_reset();
#ifdef WINAMP_DISPLAY
          winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
#endif
        } }
      wifiConnected = (WiFi.status() == WL_CONNECTED);
      Serial.println("[wifi] saved-network credentials saved to NVS");
    } else if (candCount > 0) {
      Serial.println("[wifi] all saved-network connect attempts failed");
      // TASK-426: the loop above leaves its LAST candidate resident in the STA
      // config, and auto-reconnect (armed just below) re-attacks that resident
      // config every ~2.4 s via a bare WiFi.begin(). When the last candidate is
      // a dead SSID that is an unrecoverable wedge — auto-reconnect never tries
      // anything else, so a live AP at -58 dBm goes untouched until reboot.
      // Re-point at the best (MRU-first) candidate so the 60 s of auto-reconnect
      // before the supervisor's first kick is spent on the likeliest AP.
      // persistent(false) — the candidate is unverified, and committing an
      // unverified SSID to NVS is how the stale-NVS state gets created.
      WiFi.persistent(false);
      WiFi.begin(cand[0].ssid, cand[0].pass);
    }
  }

  if (wifiConnected) {
#ifdef WINAMP_DISPLAY
    winampDisplay.setTitle("WI-FI: CONNECTED");  // M-BOOT-UI (TASK-364) §2
#endif
    // TASK-272: disable modem power-save. With the default WIFI_PS_MIN_MODEM the
    // radio dozes after idle periods; the first TCP connect after ~30-45 s of
    // network quiet then fails with EHOSTUNREACH (errno 118) for tens of seconds
    // (observed 2026-07-02 killing every WebRadio post-idle connect; TASK-238 gate
    // read 0/10 because auto-skip burned the station list inside the outage and
    // parked terminal). Mains/USB-powered device — the ~40 mA cost is irrelevant.
    WiFi.setSleep(false);
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else if (wifiCredsKnown) {
    // TASK-296: stored credentials exist but every connect window expired —
    // seen 2026-07-08 when a bursty-AP NO_AP_FOUND/AUTH_FAIL storm spanned the
    // whole boot chain (and once via the TASK-290 persist re-begin deauth whose
    // 15 s settle-wait expired under the same storm). The old path demoted this
    // to "no credentials": setAutoReconnect(false) + auto-open Settings, whose
    // foreground suppresses superviseTick() — a permanent park needing manual
    // reset. Instead: leave auto-reconnect armed and arm the supervisor so the
    // link self-heals when the AP settles.
    WiFi.setAutoReconnect(true);
    wifiDiag::superviseArm();
#ifdef WINAMP_DISPLAY
    winampDisplay.setTitle("WI-FI: RETRY IN BG");  // M-BOOT-UI (TASK-364) §2
#endif
    Serial.println("[wifi] connect failed with stored credentials — reconnect + supervisor armed");
  } else {
    // Leave WiFi in a clean disconnected STA state so WifiSection scan works.
    // WiFi.begin() (NVS attempt above) leaves auto-reconnect armed; disable it
    // so the subsequent scanNetworks() call is not blocked by a reconnect loop.
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false);
#ifdef WINAMP_DISPLAY
    winampDisplay.setTitle("WI-FI SETUP NEEDED");  // M-BOOT-UI (TASK-364) §2
#endif
    Serial.println("[wifi] no credentials — will open WiFi settings after init");
  }
  mb_heap_probe("post-wifi");  // TASK-261 Phase 0 milestone M1

  // TASK-288: fresh watchdog budget before NTP sync + spotifyRefreshToken()
  // below — none of setup()'s WiFi-connect wait loops fed the TWDT before
  // this fix, so a flaky AP requiring more than one fallback attempt could
  // already have consumed most of the 15s window before reaching here.
  esp_task_wdt_reset();

  // time-001: SNTP sync before any TLS. ESP32 has no RTC; without this the
  // clock starts ~1970 and mbedTLS rejects current Spotify certs (notBefore
  // in the future), surfacing as a generic "send_ssl_data 0x0050" failure.
  // 5 s bounded wait, non-fatal on timeout.
  // WIRE2-G1: apply the persisted TZ rule at boot (SettingsStorage::load()
  // ran above) instead of hardcoded UTC; fresh device defaults to "UTC0" —
  // identical behaviour. The epoch wait below is TZ-independent.
#ifdef WINAMP_DISPLAY
  winampDisplay.setTitle("TIME: SYNCING...");  // M-BOOT-UI (TASK-364) §2
#endif
  configTzTime(g_settings.posixTz, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  unsigned long ntpStart = millis();
  unsigned long ntpDeadline = ntpStart + 5000;
  while (time(nullptr) < 1700000000UL && millis() < ntpDeadline) {
    delay(50);
    yield();
#ifdef WINAMP_DISPLAY
    winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
#endif
  }
  time_t now = time(nullptr);
  if (now >= 1700000000UL) {
    Serial.printf("[time] synced epoch=%ld in %lums\n", (long)now, millis() - ntpStart);
  } else {
    Serial.printf("[time] NTP sync failed after %lums, trying HTTPS-Date fallback\n",
                  millis() - ntpStart);
#ifdef WINAMP_DISPLAY
    winampDisplay.setTitle("TIME: HTTPS FALLBACK...");  // M-BOOT-UI (TASK-364) §2
#endif
    time_t httpsT;
    if (fetchHttpsDate("connectivitycheck.gstatic.com", httpsT)) {
      struct timeval tv = {httpsT, 0};
      settimeofday(&tv, nullptr);
      Serial.printf("[time] HTTPS-Date set epoch=%ld\n", (long)httpsT);
    } else {
      time_t b = buildEpoch();
      struct timeval tv = {b, 0};
      settimeofday(&tv, nullptr);
      Serial.printf("[time] WARN: NTP+HTTPS-Date failed, falling back to build epoch=%ld\n", (long)b);
    }
  }

  spotifySetup(spotifyDisplay, clientId, clientSecret);

#if defined YELLOW_DISPLAY

  pinMode(0, INPUT); // has an internal pullup
  bool forceRefreshToken = digitalRead(0) == LOW;
  if (forceRefreshToken)
  {
    Serial.println("GPIO 0 is low, forcing refreshToken");
  }

#else
  bool forceRefreshToken = false;

#endif

  // Check if we have a refresh Token
  if (forceRefreshToken || refreshToken[0] == '\0')
  {

    spotifyDisplay->drawRefreshTokenMessage();
    Serial.println("Launching refresh token flow");
    if (launchRefreshTokenFlow(&spotify, clientId))
    {
      Serial.printf("Refresh token acquired: %s\n", redact(refreshToken));
      saveConfigFile(refreshToken, clientId, clientSecret);
    }
  }

  // TASK-363 (M-SPOTIFY-BOOT-GATE, ADR-054 decision 1): computed once, must
  // mirror the boot-switch condition below (main.cpp ~line 2407) exactly —
  // NOT raw playerMode alone. If WiFi isn't up yet, the boot-switch keeps
  // currentAppId == Spotify (visibly on screen) regardless of the persisted
  // preference, and that visible app must still be allowed to connect once
  // WiFi comes up via the background supervisor; seeding from raw
  // playerMode would silently strand it idle.
  bool bootIntoWebRadio = wifiConnected && (g_settings.playerMode == (uint8_t)PlayerMode::WebRadio);

  // TASK-363 companion 1 (Finding 2/3): under bootIntoWebRadio, skip the
  // eager network-calling refreshAccessToken() leg — it opens a real TLS
  // connect on the same shared `client` spotifyTask uses, independent of
  // any gate on begin(). setRefreshToken() alone primes the library with
  // zero network; SpotifyArduino's autoTokenRefresh (default true) already
  // refreshes lazily before the first real API call, which under this
  // design only happens after an explicit toggle-to-Spotify. The
  // forceRefreshToken/launchRefreshTokenFlow() credential-bootstrap path
  // above is unaffected — stays unconditional.
  if (bootIntoWebRadio) {
    spotify.setRefreshToken(refreshToken);
    Serial.println("[boot] spotify=idle (playerMode=webradio) — refresh deferred to first toggle");
  } else {
    spotifyRefreshToken(refreshToken);
  }

  // refreshToken.h flow would have held port 80. Stand up permanent /log server now.
  logsink::serverBegin();

  // ADR-012 / TASK-031a: spawn the async Spotify HTTP task. Skeleton at
  // this stage — task dequeues + logs but doesn't issue API calls yet.
  // 031b/c migrate the actual calls in.
#ifndef DISABLE_SPOTIFY
  // TASK-363 (M-SPOTIFY-BOOT-GATE, ADR-054 decision 1): seed the task idle
  // before its first loop iteration when booting straight into WebRadio —
  // closes the boot race where setWebRadioActive(true) (from the
  // switchApp(WebRadio) call below) arrived too late to stop the first
  // self-issued ACT_POLL from connecting TLS ~5s after begin().
  spotifyTask::begin(&spotify, bootIntoWebRadio);
#else
  // TASK-255 (M-WEBRADIO-NOPSRAM): the SOLE functional guard. Skipping begin()
  // means reqQueue / s_tlsYieldedSem stay null, so tlsYield()/tlsResume() (and
  // every spotifyTask:: accessor) no-op via their existing null-guards — no
  // session to free → BP-031 n/a in this variant (default build unchanged; see
  // docs/architecture/designs/M-WEBRADIO-SPOTIFY-DISABLE.md). Frees the ~10 KB
  // task stack + ~50 KB TLS for the no-PSRAM WebRadio decoder.
  Serial.println("[boot] spotify=off");   // V0 readiness token (harness scrapes pre-shell)
#endif
  mb_heap_probe("post-spotifyTask");  // TASK-261 Phase 0 milestone M2
  dataTask::begin();
  mb_heap_probe("post-dataTask");     // TASK-261 Phase 0 milestone M3

  // Boot: init the Spotify app via the App interface, then draw taskbar.
  if (g_apps[(int)AppId::Spotify]) {
    g_appLaunched[(int)AppId::Spotify] = true;
    g_apps[(int)AppId::Spotify]->init();
  } else {
    spotifyDisplay->showDefaultScreen();
  }
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
  // TASK-296: only a genuinely credential-less boot auto-opens Settings. A
  // creds-known offline boot stays on the normal shell (supervisor owns the
  // link; Settings foreground would suppress it — the park-dead chain).
  if (!wifiConnected && !wifiCredsKnown) {
    switchApp(AppId::Settings);
    g_SettingsApp.openSection(0);
  }
  // TASK-260 v2 (OQ-BOOT): cold-boot directly into the persisted player mode. After the
  // Spotify app's boot init() above (so switchApp's suspend() tears it down cleanly),
  // enter WebRadio if that was the last-active mode. Whether a station then auto-plays is
  // governed by the existing webRadioAutoplay knob — these compose. Skipped when offline
  // (no network for the station fetch — including the TASK-296 creds-known offline boot).
  // TASK-363: reuses bootIntoWebRadio computed above (same condition, computed once) —
  // this switchApp(WebRadio) call's setWebRadioActive(true) is now purely confirmatory,
  // the idle flag was already seeded before spotifyTask::begin() ran.
  else if (bootIntoWebRadio) {
    switchApp(AppId::WebRadio);
  }
  // TASK-413: LocalPlayer has no network dependency (SD-backed), so unlike WebRadio
  // its boot restore isn't gated on wifiConnected — it only needs the offline/no-creds
  // Settings branch above to have not already claimed the boot screen.
  else if (g_settings.playerMode == (uint8_t)PlayerMode::Player) {
    switchApp(AppId::LocalPlayer);
  }
  mb_heap_probe("post-init-idle");    // TASK-261 Phase 0 milestone M4 (steady idle)
  buildMathLUT();

#ifdef SPIKE_MODE
  spike::setup(&spotify);
#endif
}

// ── serial command dispatcher (serialdbg-001, TASK-056c) ───────────────
// Table-driven replacement for the old TASK-053e strcmp chain. Non-debug
// commands (reconnect, the boot-time `[boot]` line) are always compiled
// in per ADR-021 Decision 4; SERIAL_DEBUG-gated commands (tap, drag, get,
// set, info, help) are added by sub-tasks d-i.
//
// Output convention: every command emits exactly one JSON object on one
// '\n'-terminated line. Hosts parse with `json.loads(line)`.

static void cmdReconnect(const char *) {
  spotifyTask::resetTls();
  spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
  Serial.println("{\"ok\":true,\"cmd\":\"reconnect\"}");
}

// 4-field struct; help + args iterated by cmdHelp (TASK-056i).
typedef void (*cmd_fn)(const char *args);
struct SerialCmd {
  const char *name;
  cmd_fn      fn;
  const char *help;
  const char *args;
};

// TASK-056e: touch-injection ring buffer (SERIAL_DEBUG only).
// drainInjectionQueue() pops one step per loop() iteration — no delay().
// cmdDrag fills the queue and returns; JSON response emitted on release step.
#ifdef SERIAL_DEBUG
struct InjectionStep { int sx, sy; bool release; };
static InjectionStep s_injectQueue[64];
static int s_injectHead = 0, s_injectTail = 0;
static bool s_dragPending = false;
static bool s_injectIsFirst = false;  // first non-release item → Press, rest → Move
static int s_pendingDragX1, s_pendingDragY1,
           s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps;
static int s_injectTotal = 0;  // total steps for LOG_D %d/%d
// TASK-277 (VE-1-1/DEV-1-2): the release step dispatches at the LAST sample's
// coordinates, not (0,0) — otherwise a drag's Release lands outside every
// hit-test region and gesture-end logic sees garbage geometry.
static int s_lastInjectX = 0, s_lastInjectY = 0;
// TASK-277 (VE-1-3): bare `release` command marks its sentinel so the drain
// emits {"cmd":"release"} instead of the drag JSON.
static bool s_bareRelease = false;

// Forward declarations so kCmds[] can reference the handlers before they
// are defined (they must appear after kCmds[] to see kNumCmds).
static void cmdTap(const char *);
static void cmdDrag(const char *);
static void cmdRelease(const char *);
static void cmdTick(const char *);
static void cmdGet(const char *);
static void cmdSet(const char *);
static void cmdSwitchApp(const char *);
static void cmdInfo(const char *);
static void cmdScreenDump(const char *);
static void cmdColorProbe(const char *);
static void cmdSdProbe(const char *);
static void cmdSdCycle(const char *);
static void cmdSdMem(const char *);
static void cmdSdMount(const char *);
static void cmdSdUmount(const char *);
static void cmdSdClean(const char *);
static void cmdSdWrite(const char *);
static void cmdSdLs(const char *);
static void cmdSdRead(const char *);
static void cmdSdMbr(const char *);
static void cmdSdMkdir(const char *);
static void cmdSdPut(const char *);
static void cmdHelp(const char *);
static void cmdReboot(const char *);
#endif

static const SerialCmd kCmds[] = {
  { "reconnect", cmdReconnect, "TLS reset + force poll", "" },
#ifdef SERIAL_DEBUG
  { "tap",  cmdTap,  "inject touch point",              "<x> <y>"                            },
  { "drag", cmdDrag, "inject touch drag (queue-drain)", "<x1> <y1> <x2> <y2> <steps> [hold]" },
  { "release", cmdRelease, "end a held injected gesture", ""                                 },
  { "tick", cmdTick, "inject synthetic scroll ticks",   "[n=1] [dtMs=20]"                    },
  { "get",  cmdGet,  "read internal state",             "<snapshot|backoff|heap|stacks|cooldown|shellCooldown>"    },
  { "set",  cmdSet,  "write debug state",               "<backoff|cooldown> <val>"            },
  { "switchApp", cmdSwitchApp, "switch active app by id", "<appId 0..8>"                      },
  { "info", cmdInfo, "git+elf+build+snapshot summary",  ""                                   },
  { "screendump", cmdScreenDump, "read back TFT GRAM, base64 RGB565 bands", "[x=0] [y=0] [w=320] [h=240]" },
  { "colorprobe", cmdColorProbe, "TASK-340: fillRect/pushRect known values, readRect them back", "" },
  { "sdprobe", cmdSdProbe, "TASK-408: SD card mount/heap/LFN/listDir/read-bench probe", "[reads=5000]" },
  { "sdcycle", cmdSdCycle, "TASK-408 T_SD_08: N live mount/unmount cycles, heap drift", "[cycles=20]" },
  { "sdmem", cmdSdMem, "TASK-408: FATFS ctx sizing + contiguous-calloc ladder", "" },
  { "sdmount", cmdSdMount, "TASK-408: live mount attempt at N slots, optional SPI Hz", "[maxFiles] [freqHz]" },
  { "sdumount", cmdSdUmount, "TASK-408: unmount, report heap actually returned", "" },
  { "sdclean", cmdSdClean, "TASK-408: delete sdprobe fixtures (/probelist, /probebench.bin)", "" },
  { "sdwrite", cmdSdWrite, "TASK-408: isolated sequential write of N 512B chunks", "[chunks=64] [heapCheckEvery=0]" },
  { "sdls", cmdSdLs, "TASK-408: list a directory with sizes", "[dir=/] [q=quiet | n=quiet,no stat]" },
  { "sdmbr", cmdSdMbr, "TASK-408: raw sector 0 / partition table / volume ID (no mount needed)", "" },
  { "sdread", cmdSdRead, "TASK-408: read-only benchmark against an existing file", "<reads> <path>" },
  { "sdmkdir", cmdSdMkdir, "TASK-415: create a directory (test fixtures)", "<path>" },
  { "sdput", cmdSdPut, "TASK-415: write/append <=90 B of base64 to a file (test fixtures)", "<w|a> <base64|-> <path>" },
  { "help",   cmdHelp,   "list commands",                   ""                                   },
  { "reboot", cmdReboot, "software reset (ESP.restart)",   ""                                   },
#endif
};
static constexpr int kNumCmds = sizeof(kCmds) / sizeof(kCmds[0]);

// TASK-056e: drain one injection step per loop() iteration.
static inline void drainInjectionQueue() {
#ifdef SERIAL_DEBUG
  if (s_injectHead == s_injectTail) return;
  InjectionStep &step = s_injectQueue[s_injectHead % 64];
#ifdef WINAMP_DISPLAY
  if (step.release) {
    if (winampDisplay.tbIsDragging()) {
      // Taskbar drag release — TASK-279: same shared commit path as production
      // [VE-3-1]. TASK-280: also set the same 300 ms post-gesture cooldown
      // appHandleInput() sets after its shellTbRelease() call, so the injected
      // path can't double-fire faster than a real gesture could.
      shellTbRelease(s_lastTouchY);
      s_cooldownMs = millis() + 300;
      renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
    } else {
      // TASK-277 reroute (VE-1-1 blocker + DEV-1-2): dispatch to the ACTIVE
      // app's handleInput at the last sample's coordinates — previously
      // hardwired to winampDisplay.handleWinampInput(Release, 0, 0), so an
      // injected WebRadio drag delivered Press/Move to one machine and
      // Release to another (gesture never ended). Documented behaviour
      // deltas: (i) injected Releases now pass SpotifyApp's eject intercept
      // with real coords; (ii) every app now sees injected Releases.
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(TouchPhase::Release,
                                               s_lastInjectX, s_lastInjectY);
    }
    winampDisplay._injectingDrag = false;
    s_dragPending = false;
    if (s_bareRelease) {
      s_bareRelease = false;
      Serial.printf("{\"ok\":true,\"cmd\":\"release\",\"x\":%d,\"y\":%d}\n",
                    s_lastInjectX, s_lastInjectY);
    } else {
      Serial.printf("{\"ok\":true,\"cmd\":\"drag\","
                    "\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                    s_pendingDragX1, s_pendingDragY1,
                    s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps);
    }
  } else {
    LOG_D("serial", "inject sample %d/%d sx=%d sy=%d",
          s_injectHead + 1, s_injectTotal - 1, step.sx, step.sy);
    if (step.sx >= TASKBAR_X) {
      // Taskbar zone: route to gesture handlers, not app handleInput.
      s_lastTouchY = step.sy;
      if (!winampDisplay.tbIsDragging()) {
        winampDisplay.tbGesturePress(step.sy);
        shellTbPress(step.sy);  // TASK-279 (F-a): same shared paint as production
      } else {
        if (winampDisplay.tbGestureContinue(step.sy, TASKBAR_APP_COUNT))
          renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
        // TASK-279 (F-a): cancel the highlight at scroll-start [DEV-3-1].
        if (winampDisplay.tbIsScrolling()) shellTbCancel();
      }
    } else {
      // TASK-277 reroute (VE-1-6): canvas samples go to the active app —
      // Spotify's path is unchanged in effect (SpotifyApp::handleInput
      // forwards Press/Move to handleWinampInput; eject intercept is
      // Release-only), and every other app now receives injected drags.
      s_lastInjectX = step.sx;
      s_lastInjectY = step.sy;
      TouchPhase ph = s_injectIsFirst ? TouchPhase::Press : TouchPhase::Move;
      s_injectIsFirst = false;
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(ph, step.sx, step.sy);
    }
  }
#else
  (void)step;
#endif
  ++s_injectHead;
#endif
}

static void handleSerialCommands() {
  static char buf[160];  // widened: 64 was too small for long-URL commands (wrUrl, wrDeadUrls)
  static int  len = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      buf[len] = '\0';
      if (len > 0) {
        // Split "name args" at first space; args may be "".
        char *sp = strchr(buf, ' ');
        const char *args = sp ? sp + 1 : "";
        if (sp) *sp = '\0';
        bool handled = false;
        for (int i = 0; i < kNumCmds; ++i) {
          if (strcmp(buf, kCmds[i].name) == 0) {
            kCmds[i].fn(args);
            handled = true;
            break;
          }
        }
        if (!handled) {
          Serial.printf("{\"ok\":false,\"error\":\"unknown command\",\"cmd\":\"%s\"}\n", buf);
        }
      }
      len = 0;
    } else if (len < (int)sizeof(buf) - 1) {
      buf[len++] = c;
    } else {
      // Buffer full before newline — drop the partial, WARN, resync on next '\n'.
      // (Next newline will be misaligned; host-side scripts must treat the
      // following line as garbage.)
      Serial.println("{\"ok\":false,\"error\":\"line too long\"}");
      len = 0;
    }
  }
}

// TASK-408 (M-SDFS phase-0): own VSPI bus — SCK18/MISO19/MOSI23/CS5 — entirely free of
// the HSPI TFT bus and the touch controller's own SPI (see M-SDFS-sd-card-exploration.md
// §2). The mount is established once in setup() and held — see sdProbeBootMount()'s call
// site for why a lazy per-mode-entry mount cannot be relied on here.
//
// TASK-427: this block — the statics, `sdMountAttempt()`, `sdProbeBootMount()`, and
// `sdReady()` — is gated on SD_BOOT_MOUNT, not SERIAL_DEBUG, so it compiles into any
// variant that wants the boot mount without pulling in the rest of the SERIAL_DEBUG
// command surface (`cyd2usb_player`). `cyd2usb_winamp_debug` defines both, so every
// existing T_PLR/T_SD gate is unaffected. `cyd2usb_winamp` (production) defines
// neither — no mount, sdReady() stubs to false, Player mode degrades to "No SD card".
// That remains deliberate: an unconditional boot mount costs ~13 KB of permanently-held
// contiguous internal heap (FATFS window + max_files × FIL), which TASK-425 measured
// does not fit alongside the Spotify TLS working set and the Helix arena — see
// TASK-431. The interactive bring-up probes below this SERIAL_DEBUG gate — `sdmem`,
// `sdmount`/`sdumount` (live commands), `sdcycle`, `sdls`, `sdread`, `sdwrite`,
// `sdclean`, `sdprobe` (the full T_SD_01–09 sweep) — stay SERIAL_DEBUG-only and
// reference the statics/functions defined here.
#ifdef SD_BOOT_MOUNT
static const int kSdCsPin = 5;
static const int kSdSckPin = 18;
static const int kSdMisoPin = 19;
static const int kSdMosiPin = 23;
// SPI clock for data transfers (card identification always runs at 400 kHz inside
// ff_sd_initialize, and the library caps this at 25 MHz). 20 MHz, not the 4 MHz the
// M-SDFS bring-up plan suggested: on the SDHC card, 4 MHz reproducibly panics inside
// FatFs mid-read (2/2 runs; `validate()` sees obj->fs == NULL after ff_req_grant())
// while 20 MHz is clean (3/3) and 40x faster. Runtime-settable via `sdmount`.
static uint32_t s_sdFreqHz = 20000000;

// Open-file slots requested of SD.begin(). This is the single dominant term in the
// mount's memory cost, not a throughput knob: esp_vfs_fat_register() allocates
// `sizeof(vfs_fat_ctx_t) + max_files * sizeof(FIL)` as ONE contiguous internal
// block, and this IDF build has FF_MAX_SS=4096 (CONFIG_WL_SECTOR_SIZE) with
// FF_FS_TINY=0 (CONFIG_FATFS_PER_FILE_CACHE=1) — so FATFS carries a 4 KB window
// buffer and every FIL carries its own 4 KB sector cache. The Arduino default of
// 5 therefore asks for ~25 KB in one piece. See `sdmem`.
//
// TASK-416: bumped 2 -> 3. m3u::PlaylistIndex keeps the playlist File open for
// the session (audio decoder + playlist = 2, TASK-415's own accounting), and
// fileBrowser.h now holds a THIRD handle open across ticks — the directory
// SD.open() plus the File openNextFile() returns. TASK-425 measured this
// exact bump on this exact DUT (2026-08-11, cyd2usb_winamp_debug, mount-first):
// `sdmount 3` mounts cleanly (heapDelta 19 252 B, sdumount reclaimedB 19 252 B,
// exact agreement) leaving lfb8=12 788 B — enough to browse (no arena
// contention: TASK-431 already confines all Player-mode PLAYBACK to
// cyd2usb_player, where Spotify's ~39 KB TLS working set is compiled out
// entirely and isn't resident to compete for it; browsing-only headroom on
// this debug build was never the constraint). On cyd2usb_player itself the
// margin is not remotely close: TASK-427's DUT evidence shows free
// heap/largest-block in the ~50-120 KB range around a play attempt, so this
// one extra ~4 KB FIL slot is nowhere near the constraint there either. Single
// constant, not `#ifdef`'d per variant — TASK-425/427/431 already established
// that mount-size tuning is not the lever that matters once Spotify's TLS
// working set is out of the picture.
static const uint8_t kSdMaxFiles = 3;

static SPIClass s_sdSPI(VSPI);
static bool s_sdReady = false;
static bool s_sdSpiUp = false;
static size_t s_sdBootFreeIntBefore = 0, s_sdBootFreeIntAfter = 0;
static size_t s_sdBootLfbIntBefore = 0, s_sdBootLfbIntAfter = 0;

// One mount attempt with full before/after heap accounting, usable from setup()
// and from a live serial command. `tag` names the call site in the JSON line.
static bool sdMountAttempt(const char *tag, uint8_t maxFiles) {
  size_t freeBefore = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbBefore = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  size_t lfb8Before = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!s_sdSpiUp) {
    s_sdSPI.begin(kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    s_sdSpiUp = true;
  }
  unsigned long t0 = millis();
  bool ok = SD.begin(kSdCsPin, s_sdSPI, s_sdFreqHz, "/sd", maxFiles);
  unsigned long elapsedMs = millis() - t0;
  size_t freeAfter = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbAfter = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  Serial.printf("{\"probe\":\"sdmount\",\"tag\":\"%s\",\"maxFiles\":%u,\"mounted\":%s,"
                "\"elapsedMs\":%lu,\"heapDeltaB\":%ld,"
                "\"freeIntBefore\":%u,\"freeIntAfter\":%u,"
                "\"lfbIntBefore\":%u,\"lfbIntAfter\":%u,\"lfb8Before\":%u,\"lfb8After\":%u}\n",
                tag, (unsigned)maxFiles, ok ? "true" : "false", elapsedMs,
                (long)freeBefore - (long)freeAfter,
                (unsigned)freeBefore, (unsigned)freeAfter,
                (unsigned)lfbBefore, (unsigned)lfbAfter,
                (unsigned)lfb8Before,
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  s_sdBootFreeIntBefore = freeBefore;
  s_sdBootFreeIntAfter = freeAfter;
  s_sdBootLfbIntBefore = lfbBefore;
  s_sdBootLfbIntAfter = lfbAfter;
  return ok;
}

static void sdProbeBootMount() {
  s_sdReady = sdMountAttempt("boot", kSdMaxFiles);
  if (!s_sdReady && s_sdSpiUp) { s_sdSPI.end(); s_sdSpiUp = false; }
}

// TASK-415: the boot mount's outcome, for code outside this file (LocalPlayerApp
// must degrade to "No SD card" rather than opening files against a dead mount).
// A function, not an extern on s_sdReady, so the mount state stays owned here.
bool sdReady() { return s_sdReady; }

#else  // !SD_BOOT_MOUNT
// TASK-427: builds without SD_BOOT_MOUNT (today: cyd2usb_winamp production) compile no
// SD mount at all. Same symbol, honest answer — LocalPlayerApp degrades to "No SD card".
bool sdReady() { return false; }
#endif // SD_BOOT_MOUNT

// ── SERIAL_DEBUG command implementations (TASK-056e/h/i) ─────────────
// All compile only when SERIAL_DEBUG is defined (cyd2usb_winamp_debug env).
// Each emits exactly one '\n'-terminated JSON object (ADR-021 invariant),
// except `get snapshot` which may emit two via multi-part protocol.
#ifdef SERIAL_DEBUG

static void cmdTap(const char *args) {
  int x, y;
  if (sscanf(args, "%d %d", &x, &y) != 2) {
    Serial.println("{\"ok\":false,\"cmd\":\"tap\",\"error\":\"bad args — tap <x> <y>\"}");
    return;
  }
#ifdef WINAMP_DISPLAY
  // Taskbar handled at shell level — WinampDisplay must not reference switchApp.
  if (x >= TASKBAR_X) {
    int slot   = (int)y / TASKBAR_SLOT_H;
    int appIdx = (winampDisplay.tbScrollOffset() + slot) % TASKBAR_APP_COUNT;
    // TASK-280/413: route through the production resolve path — a tap on the
    // player slot must restore the persisted mode, or cycle it if already active,
    // same as shellTbRelease()/switchApp() do for real taps and injected drags.
    AppId target = resolvePlayerTap(static_cast<AppId>(appIdx), isPlayerModeApp(currentAppId));
    switchApp(target);
    winampDisplay.lastTouchResult = { "TASKBAR", -1, "APP_SWITCH", 0, -1, false };
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"TASKBAR\",\"action\":\"APP_SWITCH\",\"skipped\":false}\n", x, y);
    return;
  }
  // TASK-384: a pure-navigation tap (e.g. Stock's chart-back zone) bypasses
  // the busy gate — it doesn't start new async work, so there's nothing for
  // the gate to protect against here. See isNavigationTap()'s doc comment.
  bool navTapBypass = g_apps[(int)currentAppId] &&
                       g_apps[(int)currentAppId]->isNavigationTap(x, y);
  if (g_shellBusy && !navTapBypass) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"CANVAS\",\"action\":\"NONE\",\"skipped\":true}\n", x, y);
    return;
  }
  // Non-Spotify app dispatch: route tap to active app's handleInput when the
  // app implements real canvas interaction (Stock). Other apps retain BUG-1
  // guard (hit=CLOCK) — they don't need tap dispatch in tests.
  if (currentAppId != AppId::Spotify) {
    if (currentAppId == AppId::Stock && g_apps[(int)AppId::Stock]) {
      g_apps[(int)AppId::Stock]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Stock]->handleInput(TouchPhase::Release, x, y);
      if (!g_shellBusy && g_apps[(int)AppId::Stock]->hasPendingAsync())
        shell::setBusy(true);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"STOCK\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::Settings && g_apps[(int)AppId::Settings]) {
      g_apps[(int)AppId::Settings]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Settings]->handleInput(TouchPhase::Release, x, y);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"SETTINGS\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::Teletext && g_apps[(int)AppId::Teletext]) {
      g_apps[(int)AppId::Teletext]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Teletext]->handleInput(TouchPhase::Release, x, y);
      if (!g_shellBusy && g_apps[(int)AppId::Teletext]->hasPendingAsync())
        shell::setBusy(true);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"TELETEXT\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::PlaneRadar && g_apps[(int)AppId::PlaneRadar]) {
      g_apps[(int)AppId::PlaneRadar]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::PlaneRadar]->handleInput(TouchPhase::Release, x, y);
      if (!g_shellBusy && g_apps[(int)AppId::PlaneRadar]->hasPendingAsync())
        shell::setBusy(true);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"PLANERADAR\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::LocalPlayer && g_apps[(int)AppId::LocalPlayer]) {
      // TASK-415: same shape as the WebRadio branch below, and for the same
      // reason — injectTouch() runs handleWinampInput()'s Press phase, which
      // is what anchors a PLEDIT row tap in the shared PleditView. Without it
      // the harness could reach eject and transport but never a row, and the
      // real-touch path and cmdTap would be anchoring against different state
      // (the TASK-406 defect class). The reply reports lastTouchResult so row
      // taps are observable, not just CONSUMED/NONE.
      winampDisplay.injectTouch(x, y);
      g_apps[(int)AppId::LocalPlayer]->handleInput(TouchPhase::Release, x, y);
      // TASK-416: same busy-set-on-Release-starts-async-work shape as the
      // Stock/Teletext/PlaneRadar branches above — an eject tap that opens
      // the browser (or a row tap into a subdirectory) starts a page walk,
      // and T_PLR_14 needs g_shellBusy to actually go true here to exercise
      // the isNavigationTap() bypass at cmdTap's own busy-gate check above,
      // not just observe it as dead code.
      if (!g_shellBusy && g_apps[(int)AppId::LocalPlayer]->hasPendingAsync())
        shell::setBusy(true);
      const auto &lp = winampDisplay.lastTouchResult;
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"%s\",\"row\":%d,\"action\":\"%s\",\"skipped\":%s}\n",
                    x, y, lp.region, lp.transportPressed, lp.action,
                    lp.skipped ? "true" : "false");
    } else if (currentAppId == AppId::WebRadio && g_apps[(int)AppId::WebRadio]) {
      // WebRadio: injectTouch populates lastTouchResult for the response;
      // WebRadioApp::handleInput executes the action (eject/transport/PLEDIT).
      // TASK-387: the vis-zone is WebRadioApp's own authoritative handler
      // (vu::nextMode(appHasSpectrum=true) — vuMeter.h). injectTouch's Press
      // call reaches the *same* screen coordinates via handleWinampInput's
      // hitVis branch (that function is shared chrome, otherwise correctly
      // reused for Spotify's real touch path) and would silently fire a
      // second, differently-flagged vu::nextMode() call first — pre-existing
      // latent bug (harmless while nextMode() took no args, since both calls
      // did the same step; surfaced now because the two calls diverge).
      // Skip injectTouch for this one zone and build the diagnostic result
      // directly instead of double-mutating the vis mode.
      if (x >= vu::RECT_X && x < vu::RECT_X + vu::RECT_W &&
          y >= vu::LEFT_Y && y < vu::LEFT_Y + vu::VIS_H) {
        winampDisplay.lastTouchResult = { "VIS", -1, "VIS", 0, -1, false };
      } else {
        winampDisplay.injectTouch(x, y);
      }
      g_apps[(int)AppId::WebRadio]->handleInput(TouchPhase::Release, x, y);
      const auto &wr = winampDisplay.lastTouchResult;
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"%s\",\"action\":\"%s\",\"skipped\":%s}\n",
                    x, y, wr.region, wr.action, wr.skipped ? "true" : "false");
    } else if (currentAppId == AppId::Clock && g_apps[(int)AppId::Clock]) {
      // M-CLOCK-TAP-CYCLE (TASK-346): clock now has real canvas interaction
      // (face/theme cycle zones) — no async, so no setBusy propagation.
      g_apps[(int)AppId::Clock]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Clock]->handleInput(TouchPhase::Release, x, y);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"CLOCKAPP\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else {
      winampDisplay.lastTouchResult = { "CLOCK", -1, "NONE", 0, -1, false };
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"CLOCK\",\"action\":\"NONE\",\"skipped\":false}\n", x, y);
    }
    return;
  }
  winampDisplay.injectTouch(x, y);
  winampDisplay.injectRelease();
  // Eject: injectTouch only sets lastTouchResult; SpotifyApp::handleInput must
  // be called directly to execute the TLS-reset + force-poll reconnect
  // (TASK-414).
  if (strcmp(winampDisplay.lastTouchResult.action, "EJECT") == 0) {
    g_apps[(int)AppId::Spotify]->handleInput(TouchPhase::Release, x, y);
  }
  if (!g_shellBusy && g_apps[(int)AppId::Spotify]->hasPendingAsync())
    shell::setBusy(true);
  const auto &r = winampDisplay.lastTouchResult;
  if (strcmp(r.region, "TRANSPORT") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"pressed\":%d,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.transportPressed, r.action,
                  r.skipped ? "true" : "false");
  } else if (strcmp(r.region, "PLEDIT") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"row\":%d,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.transportPressed, r.action,
                  r.skipped ? "true" : "false");
  } else if (strcmp(r.region, "POSBAR") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"seekMs\":%ld,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.seekMs, r.action,
                  r.skipped ? "true" : "false");
  } else if (strcmp(r.region, "VOLUME") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"volumePct\":%ld,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.volumePct, r.action,
                  r.skipped ? "true" : "false");
  } else {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.action, r.skipped ? "true" : "false");
  }
#else
  Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                "\"hit\":\"NONE\",\"action\":\"NONE\",\"skipped\":false}\n", x, y);
#endif
}

static void cmdDrag(const char *args) {
  int x1, y1, x2, y2, steps;
  char tail[8] = {0};
  int n = sscanf(args, "%d %d %d %d %d %7s", &x1, &y1, &x2, &y2, &steps, tail);
  bool hold = (n == 6 && strcmp(tail, "hold") == 0);
  if (n < 5 || (n == 6 && !hold) || steps < 1 || steps > 62) {
    Serial.println("{\"ok\":false,\"cmd\":\"drag\","
                   "\"error\":\"bad args — drag <x1> <y1> <x2> <y2> <steps=1..62> [hold]\"}");
    return;
  }
#ifdef WINAMP_DISPLAY
  winampDisplay._injectingDrag = true;
#endif
  s_injectHead = s_injectTail = 0;
  s_injectIsFirst = true;  // first dequeued sample → Press, rest → Move
  for (int i = 0; i <= steps; ++i) {
    s_injectQueue[s_injectTail++ % 64] = {
      x1 + (x2 - x1) * i / steps,
      y1 + (y2 - y1) * i / steps,
      false
    };
  }
  // TASK-277 (VE-1-3): `hold` suppresses the release sentinel — the gesture
  // stays anchored so mid-gesture events (auto-skip) are agent-testable; a
  // later bare `release` ends it. _injectingDrag stays set until that release.
  if (!hold)
    s_injectQueue[s_injectTail++ % 64] = { 0, 0, true };  // release sentinel
  s_pendingDragX1 = x1; s_pendingDragY1 = y1;
  s_pendingDragX2 = x2; s_pendingDragY2 = y2;
  s_pendingDragSteps = steps;
  s_injectTotal = s_injectTail;
  s_dragPending = !hold;
  if (hold) {
    // No release step will pop → respond now (the normal contract emits the
    // JSON from drainInjectionQueue at release-pop).
    Serial.printf("{\"ok\":true,\"cmd\":\"drag\",\"hold\":true,"
                  "\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                  x1, y1, x2, y2, steps);
  }
  // Non-hold: JSON response emitted by drainInjectionQueue() when release pops.
}

// TASK-277 (VE-1-3): end a held gesture — enqueue a release step dispatched at
// the last injected sample's coordinates.
static void cmdRelease(const char *) {
  s_bareRelease = true;
  s_injectQueue[s_injectTail++ % 64] = { 0, 0, true };
  // JSON response emitted by drainInjectionQueue() when the step pops.
}

static void cmdTick(const char *args) {
  int n = 1, dtMs = 20;
  sscanf(args, "%d %d", &n, &dtMs);
  if (n < 1)    n    = 1;
  if (dtMs < 1) dtMs = 20;
#ifdef WINAMP_DISPLAY
  // TASK-277 [VE-1-5]: drive the ACTIVE app's integrator when WebRadio is up.
  // The reply's scrollOffset field stays Spotify-only — WebRadio tests assert
  // via `get wrScroll` exclusively.
  if (currentAppId == AppId::WebRadio) {
    for (int i = 0; i < n; ++i)
      g_WebRadioApp.tickScrollDebug(dtMs * 0.001f);
  } else {
    for (int i = 0; i < n; ++i)
      winampDisplay.tickScroll(dtMs * 0.001f);
  }
  char sbuf[64]; int scrollOff = 0;
  if (winampDisplay.dbgGet("scrollOffset", sbuf, sizeof(sbuf)))
    sscanf(sbuf, "\"key\":\"scrollOffset\",\"val\":%d", &scrollOff);
  Serial.printf("{\"ok\":true,\"cmd\":\"tick\",\"steps\":%d,\"dtMs\":%d,"
                "\"scrollOffset\":%d}\n", n, dtMs, scrollOff);
#else
  Serial.printf("{\"ok\":true,\"cmd\":\"tick\",\"steps\":%d,\"dtMs\":%d,"
                "\"scrollOffset\":0}\n", n, dtMs);
#endif
}

static void cmdGet(const char *args) {
  // TASK-401: widened 256 -> 512. `get wifiSaved` (5 entries x up to a
  // 32-char ssid + 10-digit lastUsedMs) needs up to ~390 B; 256 silently
  // truncated it. Every other dbgGet-chain caller below stays well under
  // either size, so this is a pure headroom increase, not a behavior change.
  char buf[512]; buf[0] = '\0';
  // TASK-255 (M-WEBRADIO-NOPSRAM): build-variant query (V0). Lets the harness pick a
  // Spotify-poll-free readiness path and lets V2 assert the variant.
  if (strcmp(args, "variant") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"variant\",\"spotify\":\"%s\",\"last\":true}\n",
#ifdef DISABLE_SPOTIFY
                  "off"
#else
                  "on"
#endif
                  );
    return;
  }
  // TASK-410 (T_AE_07/09/10): raw engine state for `set aePlayFile` — isRunning()
  // and the pump's result enum, independent of WebRadioApp's own dbgGet (which
  // reads WRPlayState, never touched by aeConnectFile()'s bypass path).
  if (strcmp(args, "aePlay") == 0) {
    bool running = false;
    uint32_t filePos = 0, fileSize = 0, curSec = 0, durSec = 0;
    if (s_wr_audio && xSemaphoreTake(s_wrAudioMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
      running = s_wr_audio->isRunning();
      filePos = s_wr_audio->getFilePos();
      fileSize = s_wr_audio->getFileSize();
      curSec = s_wr_audio->getAudioCurrentTime();
      durSec = s_wr_audio->getAudioFileDuration();
      xSemaphoreGive(s_wrAudioMutex);
    }
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"aePlay\",\"alive\":%d,"
                  "\"running\":%d,\"pumpResult\":%u,\"eofPending\":%d,"
                  "\"filePos\":%u,\"fileSize\":%u,\"curSec\":%u,\"durSec\":%u,\"last\":true}\n",
                  (int)wrPumpAlive(), (int)running, (unsigned)s_wrPumpResult,
                  (int)s_aeEofPending, (unsigned)filePos, (unsigned)fileSize,
                  (unsigned)curSec, (unsigned)durSec);
    return;
  }
  // TASK-274 (M-WIFI-DIAG §3.2): WiFi ground truth for outage attribution.
  // ms = device→host clock anchor; disc*/lastGotIpMs from the wifiDiag handler.
  // Field set VE-gated (BP-024) — extend, don't rename.
  if (strcmp(args, "wifi") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifi\","
                  "\"ms\":%lu,\"status\":%d,\"rssi\":%d,\"ip\":\"%s\",\"ch\":%d,"
                  "\"discCount\":%lu,\"lastDiscReason\":%u,\"lastDiscMs\":%lu,"
                  "\"lastGotIpMs\":%lu,\"kicks\":%lu,\"last\":true}\n",
                  (unsigned long)millis(), (int)WiFi.status(),
                  (WiFi.status() == WL_CONNECTED) ? (int)WiFi.RSSI() : 0,
                  WiFi.localIP().toString().c_str(), (int)WiFi.channel(),
                  (unsigned long)wifiDiag::discCount,
                  (unsigned)wifiDiag::lastDiscReason,
                  (unsigned long)wifiDiag::lastDiscMs,
                  (unsigned long)wifiDiag::lastGotIpMs,
                  (unsigned long)wifiDiag::superviseKicks);
    return;
  }
  // TASK-299: dataTask queue/dispatch + tlsYield-handshake snapshot. The three
  // "station fetch never ran" signatures read as: wrDrops advanced = request
  // never enqueued; queueWaiting>0 with inFlight stuck on another type =
  // wedged behind a prior fetcher; wrPhase=0 with old wrPhaseMs = parked in
  // tlsYield (yieldCount/tlsStopped show the handshake side).
  if (strcmp(args, "dataq") == 0) {
    dataTask::DbgQueueState q;
    dataTask::dbgQueueState(&q);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"dataq\",\"ms\":%lu,"
                  "\"queueWaiting\":%u,\"pendingMask\":%lu,\"inFlight\":%d,"
                  "\"inFlightMs\":%lu,\"wrPhase\":%d,\"wrPhaseMs\":%lu,"
                  "\"wrEnqueues\":%lu,\"wrDrops\":%lu,"
                  "\"yieldCount\":%u,\"tlsStopped\":%s,"
                  "\"spAct\":%d,\"spActMs\":%lu,\"last\":true}\n",
                  (unsigned long)millis(),
                  (unsigned)q.queueWaiting, (unsigned long)q.pendingMask,
                  (int)q.inFlight, (unsigned long)q.inFlightMs,
                  (int)q.wrPhase, (unsigned long)q.wrPhaseMs,
                  (unsigned long)q.wrEnqueues, (unsigned long)q.wrDrops,
                  (unsigned)spotifyTask::tlsYieldCount(),
                  spotifyTask::tlsStoppedFlag() ? "true" : "false",
                  (int)spotifyTask::taskActivity(),
                  (unsigned long)spotifyTask::taskActivityMs());
    return;
  }
  // TASK-344 (M-CERT-ERRCODE): peek whether a `set certbreak <app>` arm is
  // still pending (armed=false once the target fetch has consumed it).
  if (strcmp(args, "certbreak") == 0) {
    int armed = dataTask::debugPeekCertBreak();
    if (armed < 0) {
      Serial.println("{\"ok\":true,\"cmd\":\"get\",\"var\":\"certbreak\","
                      "\"armed\":false,\"last\":true}");
    } else {
      Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"certbreak\","
                    "\"armed\":true,\"type\":%d,\"last\":true}\n", armed);
    }
    return;
  }
  // TASK-282: beacon-watcher stats — evidence at the antenna. count/gapMax/
  // gapsOver1s split BEACON_TIMEOUT into "beacons stopped arriving" (H-A/H-C)
  // vs "beacons fine, stack timed out" (H-B). otherMgmt proves rx was alive.
  if (strcmp(args, "beacon") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"beacon\","
                  "\"active\":%s,\"count\":%lu,\"gapMaxMs\":%lu,\"gapsOver1s\":%lu,"
                  "\"lastAgoMs\":%lu,\"rssi\":%ld,\"noiseFloor\":%ld,"
                  "\"otherMgmt\":%lu,\"last\":true}\n",
                  wifiDiag::beaconWatchActive() ? "true" : "false",
                  (unsigned long)wifiDiag::beaconStats.count,
                  (unsigned long)wifiDiag::beaconStats.gapMaxMs,
                  (unsigned long)wifiDiag::beaconStats.gapsOver1s,
                  (unsigned long)(wifiDiag::beaconStats.lastMs
                      ? millis() - wifiDiag::beaconStats.lastMs : 0),
                  (long)wifiDiag::beaconStats.lastRssi,
                  (long)wifiDiag::beaconStats.noiseFloor,
                  (unsigned long)wifiDiag::beaconStats.otherMgmt);
    return;
  }
  // TASK-282: async scan result — reports every AP whose SSID matches ours
  // (multi-BSSID roaming visible) plus total network count.
  if (strcmp(args, "wifiScan") == 0) {
    int16_t n = WiFi.scanComplete();
    if (n < 0) {
      Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifiScan\","
                    "\"state\":\"%s\",\"last\":true}\n",
                    n == WIFI_SCAN_RUNNING ? "running" : "idle");
      return;
    }
    String own = WiFi.SSID();
    // TASK-426: matches:[] alone is ambiguous — an empty `own` (STA configured
    // but never associated) produces the same output as "target AP absent".
    // Dump own + the full scan list so the two cases are distinguishable.
    Serial.printf("[wifiScan] own=\"%s\" n=%d\n", own.c_str(), (int)n);
    for (int i = 0; i < n; i++)
      Serial.printf("[wifiScan]   ssid=\"%s\" bssid=%s rssi=%d ch=%d enc=%d\n",
                    WiFi.SSID(i).c_str(), WiFi.BSSIDstr(i).c_str(),
                    (int)WiFi.RSSI(i), (int)WiFi.channel(i),
                    (int)WiFi.encryptionType(i));
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifiScan\",\"total\":%d,"
                  "\"matches\":[", (int)n);
    bool first = true;
    for (int i = 0; i < n; i++) {
      if (WiFi.SSID(i) != own) continue;
      Serial.printf("%s{\"bssid\":\"%s\",\"rssi\":%d,\"ch\":%d}",
                    first ? "" : ",", WiFi.BSSIDstr(i).c_str(),
                    (int)WiFi.RSSI(i), (int)WiFi.channel(i));
      first = false;
    }
    Serial.printf("],\"last\":true}\n");
    WiFi.scanDelete();
    return;
  }
  // TASK-426: dump the STA connect config. A scan that finds the AP while
  // esp_wifi_connect() returns NO_AP_FOUND means connect is filtering it out:
  // a stale bssid/channel pin or an rssi/authmode threshold are the candidates.
  if (strcmp(args, "wifiCfg") == 0) {
    wifi_config_t c = {};
    esp_err_t e = esp_wifi_get_config(WIFI_IF_STA, &c);
    Serial.printf("[wifiCfg] err=%d ssid=\"%s\" pwlen=%u bssid_set=%d "
                  "bssid=%02x:%02x:%02x:%02x:%02x:%02x ch=%u "
                  "scan_method=%d sort=%d thr_rssi=%d thr_auth=%d pmf_r=%d\n",
                  (int)e, (const char*)c.sta.ssid,
                  (unsigned)strlen((const char*)c.sta.password),
                  (int)c.sta.bssid_set,
                  c.sta.bssid[0], c.sta.bssid[1], c.sta.bssid[2],
                  c.sta.bssid[3], c.sta.bssid[4], c.sta.bssid[5],
                  (unsigned)c.sta.channel,
                  (int)c.sta.scan_method, (int)c.sta.sort_method,
                  (int)c.sta.threshold.rssi, (int)c.sta.threshold.authmode,
                  (int)c.sta.pmf_cfg.required);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifiCfg\",\"last\":true}\n");
    return;
  }
  // appId — shell-owned; WinampDisplay cannot reference currentAppId.
  if (strcmp(args, "ip") == 0) {
    // TASK-248: LAN IP so the stress harness can read logs over the /log HTTP ring
    // (off the CH340 serial bottleneck) while keeping commands on serial.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"ip\",\"ip\":\"%s\",\"last\":true}\n",
                  WiFi.localIP().toString().c_str());
    return;
  }
  if (strcmp(args, "appId") == 0) {
#define APP_X(Name, icon, cfg, disp) #Name,
    static const char* kAppNames[] = {
#include "appRegistry.h"
    };
#undef APP_X
    const char* nm = ((int)currentAppId < (int)AppId::COUNT)
                   ? kAppNames[(int)currentAppId] : "Unknown";
    Serial.printf("{\"ok\":true,\"cmd\":\"get\","
                  "\"var\":\"appId\",\"id\":%d,\"name\":\"%s\",\"last\":true}\n",
                  (int)currentAppId, nm);
    return;
  }
  if (strcmp(args, "activeError") == 0) {
    // TASK-245 / ADR-046: active app's error + connecting state (drive the
    // red / amber active-bar) + the Spotify sources so VE can assert the
    // boot-amber → green/red path.
    bool ae = g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->hasError();
    bool ac = g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->isConnecting();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"activeError\","
                  "\"active\":%s,\"connecting\":%s,"
                  "\"spotifyAuthError\":%s,\"spotifyDegraded\":%s,\"spotifyConnecting\":%s,"
                  "\"last\":true}\n",
                  ae ? "true" : "false",
                  ac ? "true" : "false",
                  spotifyTask::authError() ? "true" : "false",
                  // TASK-366: surfaced alongside spotifyAuthError so VE can assert the
                  // two sticky latches independently (both OR into `active`/hasError()).
                  spotifyTask::degraded() ? "true" : "false",
                  spotifyTask::connecting() ? "true" : "false");
    return;
  }
  if (strcmp(args, "stacks") == 0) {
    // TASK-240: report each task's configured stack size + watermark (min free
    // ever). used = size - free; trim target = used + margin. Also include the
    // current free heap + largest block so a fetch session can be correlated.
    size_t dF = dataTask::stackHighWaterBytes(),  dS = dataTask::stackSizeBytes();
    size_t sF = spotifyTask::stackHighWaterBytes(), sS = spotifyTask::stackSizeBytes();
    // TASK-278: wrPump only exists while WebRadio has played at least once this
    // session — report 0/0/0 before then (wrPumpAlive() gates the size too, so
    // "used" doesn't read as a false full-stack allocation). webRadioApp.h is
    // only compiled under WINAMP_DISPLAY (see include above).
#ifdef WINAMP_DISPLAY
    size_t wS = wrPumpAlive() ? wrPumpStackSizeBytes() : 0;
    size_t wF = wrPumpStackHighWaterBytes();
#else
    size_t wS = 0, wF = 0;
#endif
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"stacks\","
                  "\"dataSize\":%u,\"dataFree\":%u,\"dataUsed\":%u,"
                  "\"spotSize\":%u,\"spotFree\":%u,\"spotUsed\":%u,"
                  "\"wrPumpSize\":%u,\"wrPumpFree\":%u,\"wrPumpUsed\":%u,"
                  "\"heapFree\":%u,\"heapMaxAlloc\":%u,\"last\":true}\n",
                  (unsigned)dS,(unsigned)dF,(unsigned)(dS-dF),
                  (unsigned)sS,(unsigned)sF,(unsigned)(sS-sF),
                  (unsigned)wS,(unsigned)wF,(unsigned)(wS>wF?wS-wF:0),
                  (unsigned)ESP.getFreeHeap(),(unsigned)ESP.getMaxAllocHeap());
    return;
  }
  // T_MB_PROBE_00 (TASK-261 Phase 0): caps-split heap query — internal vs DMA pool,
  // free + largest_free_block each. Distinguishes the two pools so fragmentation in
  // the INTERNAL (large) pool is visible separately from the scarce DMA pool.
  if (strcmp(args, "heap") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"heap\","
                  "\"freeInt\":%u,\"lfbInt\":%u,"
                  "\"freeDma\":%u,\"lfbDma\":%u,\"last\":true}\n",
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
    return;
  }
  if (strcmp(args, "weatherReady") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"weatherReady\","
                  "\"ready\":%s,\"last\":true}\n", s_wxDataReady ? "true" : "false");
    return;
  }
  if (strcmp(args, "cryptoReady") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"cryptoReady\","
                  "\"ready\":%s,\"last\":true}\n", s_cxDataReady ? "true" : "false");
    return;
  }
  if (strcmp(args, "cryptoHttpCode") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"cryptoHttpCode\","
                  "\"val\":%d,\"last\":true}\n", dataTask::lastCryptoHttpCode());
    return;
  }
  if (strcmp(args, "stockQuoteProgress") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"stockQuoteProgress\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::stockQuoteProgress());
    return;
  }
  if (strcmp(args, "weatherFetchPhase") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"weatherFetchPhase\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::weatherFetchPhase());
    return;
  }
  if (strcmp(args, "cryptoFetchPhase") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"cryptoFetchPhase\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::cryptoFetchPhase());
    return;
  }
  if (strcmp(args, "stockChartProgress") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"stockChartProgress\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::stockChartProgress());
    return;
  }
  if (strcmp(args, "golAlive") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"golAlive\","
                  "\"count\":%d,\"last\":true}\n", s_golAliveCount);
    return;
  }
  if (strcmp(args, "shellBusy") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"shellBusy\","
                  "\"busy\":%s,\"last\":true}\n", g_shellBusy ? "true" : "false");
    return;
  }
  if (strcmp(args, "shellCooldown") == 0) {
    // TASK-294: shell-level post-gesture cooldown (s_cooldownMs) remaining.
    // Distinct from winampDisplay's `cooldown` var (TASK-052 dead-zone-tap
    // force-poll cooldown in SpotifyApp) despite the similar name.
    unsigned long now = millis();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"shellCooldown\","
                  "\"remainingMs\":%lu,\"last\":true}\n",
                  (s_cooldownMs > now) ? (s_cooldownMs - now) : 0UL);
    return;
  }
  if (strcmp(args, "visMode") == 0) {
    vu::VisMode m = vu::currentMode();
    int mi = (m == vu::VIS_ATLAS_MODE) ? 0
           : (m == vu::VIS_VU)         ? 1
           : (m == vu::VIS_BLANK)      ? 2
           : (m == vu::VIS_WAVE_ATLAS) ? 3
           : (m == vu::VIS_SPECTRUM)   ? 4
           : (m == vu::VIS_WAVE)       ? 5 : -1;
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"visMode\","
                  "\"mode\":%d,\"last\":true}\n", mi);
    return;
  }
  if ((spotifyDisplay && spotifyDisplay->dbgGet(args, buf, sizeof(buf)))
      || spotifyTask::dbg_get(args, buf, sizeof(buf))) {
    // buf[0]=='\0' means the owner used multi-part Serial.printf directly.
    if (buf[0]) {
      Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    }
    return;
  }
  if (settingsDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (stockDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
#ifdef SERIAL_DEBUG
  if (matrixDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (lifeDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (cryptoDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (aquariumDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
#endif
  if (teletextDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (planeRadarDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
#ifdef WINAMP_DISPLAY
  if (webRadioDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
#endif
  if (strcmp(args, "clockStyle") == 0) {
    static const char* kSN[] = {"digital","flip","nixie","vfd"};
    uint8_t cs = (uint8_t)g_settings.clockStyle % 4;
    // M-CLOCK-TAP-CYCLE (TASK-346): themes + dirty added — dirty is the
    // un-flushed-change flag that makes deferred persistence testable
    // without pulling settings.json (pair with `get settingsSaveCount`).
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"clockStyle\","
                  "\"val\":%d,\"name\":\"%s\",\"nixieTheme\":%d,\"vfdTheme\":%d,"
                  "\"dirty\":%s,\"last\":true}\n", cs, kSN[cs],
                  (int)g_settings.nixieTheme, (int)g_settings.vfdTheme,
                  g_ClockApp.dbgStyleDirty() ? "true" : "false");
    return;
  }
  if (strcmp(args, "clockLastAction") == 0) {
    // M-CLOCK-TAP-CYCLE (TASK-346): tap-zone outcome observable
    // (TAP_FACE / TAP_THEME / TAP_THEME_NA / DEBOUNCE) — prLastAction's
    // role for the clock's two hit boxes.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"clockLastAction\","
                  "\"val\":\"%s\",\"last\":true}\n", g_ClockApp.dbgLastAction());
    return;
  }
  if (strcmp(args, "playerMode") == 0) {   // TASK-260/413 (VE: agent-driven persist/settings tests)
    static const char* kPmNames[] = { "Spotify", "WebRadio", "Player" };
    uint8_t pm = g_settings.playerMode;   // true value — §6.1: no longer collapsed to a bool
    const char* name = (pm < 3) ? kPmNames[pm] : "unknown";
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"playerMode\","
                  "\"val\":%d,\"name\":\"%s\",\"last\":true}\n",
                  pm, name);
    return;
  }
  // ── TASK-415 / ADR-059 D12: LocalPlayer playlist observables ─────────────
  // These read the app instance directly, not currentAppId, so a test can
  // assert on a loaded playlist without the mode being on screen — same
  // always-reachable contract as `get wrStation`. The index is only allocated
  // while the mode is resumed, so the honest answer off-screen is count=0.
  if (strcmp(args, "plCount") == 0) { g_LocalPlayerApp.dbgReport(); return; }
  if (strcmp(args, "plMem")   == 0) { g_LocalPlayerApp.dbgMem();    return; }
  if (strncmp(args, "plRow", 5) == 0 && (args[5] == '\0' || args[5] == ' ')) {
    int idx = 0;
    if (sscanf(args + 5, "%d", &idx) != 1 || idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"get\",\"var\":\"plRow\","
                     "\"error\":\"usage: get plRow <idx>\"}");
      return;
    }
    g_LocalPlayerApp.dbgRow((uint16_t)idx);
    return;
  }
  // TASK-416 / ADR-059 D12: file browser observables — T_PLR_13-16 drive the
  // walk and navigation deterministically from here rather than only via taps.
  if (strcmp(args, "fbState") == 0) { g_LocalPlayerApp.dbgFbState(); return; }
  // OQ1 (design §11): the UTF-8 -> renderable-ASCII fold, testable without a
  // card. Everything a PLEDIT row can contain goes through this one helper.
  if (strncmp(args, "plFold", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *in = (args[6] == ' ') ? args + 7 : "";
    char out[96];
    textfold::foldUtf8(in, out, sizeof(out));
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plFold\","
                  "\"in\":\"%s\",\"out\":\"%s\",\"last\":true}\n", in, out);
    return;
  }
  if (strcmp(args, "kb") == 0) {
    // TASK-325 (M-SERIALDBG, VE-PRL-1 blocker): cheap KeyboardWidget state
    // dump for host assertions after kbText/kbOk/kbCancel — same diagnostic-
    // surface role as `get dataq` / `get wrStation` elsewhere.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"kb\","
                  "\"active\":%s,\"len\":%d,\"maxLen\":%d,\"mode\":%d,\"last\":true}\n",
                  g_keyboard.active() ? "true" : "false",
                  (int)g_keyboard.len(), (int)g_keyboard.maxLen(),
                  (int)g_keyboard.mode());
    return;
  }
  if (strcmp(args, "pick") == 0) {
    // M-COUNTRY-PICKER (CP-8): SPickerList observable — scroll offset +
    // highlighted index, so T-CPICK assertions aren't coordinate-guesswork
    // against a scroll-state-dependent list (same role as `get kb`).
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"pick\","
                  "\"active\":%s,\"offset\":%d,\"highlightIdx\":%d,\"last\":true}\n",
                  g_countryPicker.active() ? "true" : "false",
                  (int)g_countryPicker.dbgOffset(),
                  (int)g_countryPicker.dbgHighlight());
    return;
  }
  if (strcmp(args, "prloc") == 0) {
    // M-PR-LOCATIONS (TASK-319): per-slot dump + active index — the
    // diagnostic surface for every T_PRL test (same role `get wrStation` /
    // `get dataq` play elsewhere). No lastGeocode field: the geocode fetcher
    // is TASK-320, still unimplemented — a placeholder here would just be a
    // stub nobody can populate, so it's omitted rather than shipped half-wired.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"prloc\","
                  "\"active\":%d,\"locs\":[", (int)g_settings.prActiveLoc);
    for (int i = 0; i < PR_NUM_LOCS; i++) {
      Serial.printf("%s{\"i\":%d,\"label\":\"%s\",\"lat\":%.6f,\"lon\":%.6f}",
                    i ? "," : "", i, g_settings.prLocs[i].label,
                    g_settings.prLocs[i].lat, g_settings.prLocs[i].lon);
    }
    // M-HOME-LOCATION H-5: "home" = the home mirror (g_settings.lat/lon =
    // prLocs[0]) — otherwise unreadable from the harness; "divKm" = the
    // confirm-screen divergence observable (T-HOME-05), 0 when n/a.
    Serial.printf("],\"home\":{\"lat\":%.6f,\"lon\":%.6f},\"divKm\":%d,\"last\":true}\n",
                  g_settings.lat, g_settings.lon, g_SettingsApp.prDivKm());
    return;
  }
  if (strcmp(args, "geocode") == 0) {
    // TASK-320: non-consuming peek at the geocode slot (the editor is the
    // real pollGeocode() consumer — this must not steal its result).
    bool parked = false, hasNew = false;
    dataTask::GeocodeResult r;
    dataTask::dbgGeocodeState(&parked, &hasNew, &r);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"geocode\","
                  "\"parked\":%s,\"new\":%s,\"resOk\":%s,\"errorCode\":%d,"
                  "\"seq\":%u,\"lat\":%.6f,\"lon\":%.6f,\"display\":\"%s\",\"last\":true}\n",
                  parked ? "true" : "false", hasNew ? "true" : "false",
                  r.ok ? "true" : "false", r.errorCode,
                  (unsigned)r.seq, r.lat, r.lon, r.display);
    return;
  }
  // WIRE2 (§6d, W-7): shared G1+G2/G3 observable — the harness asserts the
  // formatted strings computed from getLocalTime + the timeFmt helpers (the
  // exact code path the renderers use), never scraped pixels. hour is emitted
  // as rendered (12h drops the leading zero); ampm is null in 24h mode.
  if (strcmp(args, "clockRender") == 0) {
    struct tm t;
    if (!getLocalTime(&t)) {
      Serial.println("{\"ok\":false,\"cmd\":\"get\",\"var\":\"clockRender\","
                     "\"error\":\"time not synced\"}");
      return;
    }
    char hBuf[4], dBuf[16];
    snprintf(hBuf, sizeof(hBuf), g_settings.fmt24h ? "%02d" : "%d", clockHour(t));
    fmtDate(t, dBuf, sizeof(dBuf), '/');
    const char* ap = clockAmPm(t);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"clockRender\","
                  "\"hour\":\"%s\",\"min\":\"%02d\",\"ampm\":%s%s%s,"
                  "\"date\":\"%s\",\"fmt24h\":%s,\"dateFmt\":%d,\"last\":true}\n",
                  hBuf, t.tm_min,
                  ap ? "\"" : "", ap ? ap : "null", ap ? "\"" : "",
                  dBuf, g_settings.fmt24h ? "true" : "false",
                  (int)g_settings.dateFmt);
    return;
  }
  // WIRE2-G5 (§6 debug hooks, W-7): backlight owner observable — T-SETW-14
  // asserts the duty tracks injected LDR values outside the Settings screen.
  if (strcmp(args, "duty") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"duty\","
                  "\"duty\":%d,\"ldrRaw\":%d,\"auto\":%s,\"injected\":%s,"
                  "\"last\":true}\n",
                  g_backlight.currentDuty(), (int)g_backlight.ldrRaw(),
                  g_settings.dispAuto ? "true" : "false",
                  g_backlight.injected() ? "true" : "false");
    return;
  }
  // T-WRSET-04: completed-SPIFFS-write counter for SettingsStorage::save()
  // (see settingsStorage.cpp) — lets VE prove ADR-050 rule 3 coalesced-save
  // discipline (one save per suspend/eject) with a hard counter instead of
  // parsing "SettingsStorage: saved" log lines. Pair with `set settingsSave`
  // (WIRE2 §6 W-1) to force a save and confirm the counter advances by
  // exactly one.
  if (strcmp(args, "settingsSaveCount") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"settingsSaveCount\","
                  "\"count\":%u,\"last\":true}\n",
                  (unsigned)SettingsStorage::debugSaveCount());
    return;
  }
  Serial.printf("{\"ok\":false,\"cmd\":\"get\","
                "\"error\":\"unknown var\",\"var\":\"%s\"}\n", args);
}

static void cmdSet(const char *args) {
  char var[32], val[128];  // val widened to 128 to accommodate wrUrl (104-byte station URLs)

  // TASK-325 (M-SERIALDBG, VE-PRL-1 blocker): KeyboardWidget injection.
  // kbText carries the full remaining string verbatim (UK postcodes etc.
  // contain spaces) and kbOk/kbCancel take no value at all — neither fits
  // the generic single var/val split below, so both are special-cased
  // against the raw `args` first (same drain-all-bytes-at-once lesson as
  // the "set prloc" reparse below: don't assume a fixed token count).
  // Injection/commit/cancel route through KeyboardWidget's own
  // injectText()/commitFromHost()/cancelFromHost() — same callbacks, same
  // cleanup as a real tap (BP-047/LL-110: no duplicated logic here).
  if (strncmp(args, "kbText", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *text = (args[6] == ' ') ? args + 7 : "";
    if (!g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbText\","
                      "\"error\":\"no active keyboard\"}");
      return;
    }
    g_keyboard.injectText(text);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbText\","
                  "\"len\":%d,\"maxLen\":%d}\n",
                  (int)g_keyboard.len(), (int)g_keyboard.maxLen());
    return;
  }
  if (strcmp(args, "kbOk") == 0) {
    if (!g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbOk\","
                      "\"error\":\"no active keyboard\"}");
      return;
    }
    bool wasEmpty = (g_keyboard.len() == 0);  // OK is disabled/no-op when empty on-screen too
    g_keyboard.commitFromHost();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbOk\",\"submitted\":%s}\n",
                  wasEmpty ? "false" : "true");
    return;
  }
  if (strcmp(args, "kbCancel") == 0) {
    if (!g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbCancel\","
                      "\"error\":\"no active keyboard\"}");
      return;
    }
    g_keyboard.cancelFromHost();
    Serial.println("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbCancel\"}");
    return;
  }
  // TASK-320 (VE-PRL-2): park a synthetic geocode result for the NEXT
  // pollGeocode(). Two forms, both multi-token (raw-args parse like prloc):
  //   set geocode <lat> <lon> [display text…]   — success result
  //   set geocode err <code>                    — failure result (e.g. -96)
  // Structural isolation lives in dataTask (parked slot checked before the
  // real one; enqueueGeocode() no-ops while parked) — this command only
  // builds the result. seq is stamped by debugInjectGeocode() itself.
  if (strncmp(args, "geocode ", 8) == 0) {
    const char* rest = args + 8;
    dataTask::GeocodeResult r;
    // Third form (DUT smoke / T_PRL_01b): `set geocode fetch <CC> <postcode…>`
    // triggers a REAL enqueueGeocode() — the editor (TASK-321) doesn't exist
    // yet, so this is the only on-device path to exercise the live fetcher
    // (UA/TLS/parse). Postcode = remainder verbatim (may contain a space).
    // Checked before the lat/lon form ("fetch" would otherwise parse as a
    // 0.0-lat injection). Result observable via `get geocode` (new=true).
    if (strncmp(rest, "fetch ", 6) == 0) {
      char cc[4]; int consumed = 0;
      if (sscanf(rest + 6, "%3s %n", cc, &consumed) < 1 || rest[6 + consumed] == '\0') {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"usage: geocode fetch <CC> <postcode>\"}");
        return;
      }
      uint8_t seq = dataTask::enqueueGeocode(cc, rest + 6 + consumed);
      Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"geocode\","
                    "\"fetch\":true,\"seq\":%u}\n", (unsigned)seq);
      return;
    }
    if (strncmp(rest, "err ", 4) == 0) {
      r.ok = false;
      r.errorCode = atoi(rest + 4);
      if (r.errorCode == 0) {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"err needs nonzero code\"}");
        return;
      }
    } else {
      char latBuf[16], lonBuf[16]; int consumed = 0;
      if (sscanf(rest, "%15s %15s %n", latBuf, lonBuf, &consumed) < 2) {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"usage: geocode <lat> <lon> [display] | geocode err <code>\"}");
        return;
      }
      r.ok  = true;
      r.lat = atof(latBuf);
      r.lon = atof(lonBuf);
      if (r.lat < -90.0f || r.lat > 90.0f || r.lon < -180.0f || r.lon > 180.0f) {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"lat/lon out of range\"}");
        return;
      }
      strlcpy(r.display, rest + consumed, sizeof(r.display));  // may be empty
    }
    dataTask::debugInjectGeocode(r);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"geocode\","
                  "\"parked\":true,\"resOk\":%s,\"errorCode\":%d}\n",
                  r.ok ? "true" : "false", r.errorCode);
    return;
  }
  // TASK-325 smoke helper: open the keyboard directly (no touch navigation
  // needed) so kbText/kbOk/kbCancel are DUT-testable standalone. Submitted/
  // cancelled text is echoed as JSON for host asserts.
  //   set kbShow [maxLen] [mode]   (mode 0=Full 1=UpperAlpha; defaults 10, 0)
  if (strncmp(args, "kbShow", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    int maxLen = 10, mode = 0;
    sscanf(args + 6, "%d %d", &maxLen, &mode);
    if (g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbShow\","
                      "\"error\":\"keyboard already active\"}");
      return;
    }
    g_keyboard.show("dbg kbShow", "",
                    mode == 1 ? KeyboardWidget::Mode::UpperAlpha : KeyboardWidget::Mode::Full,
                    (uint8_t)maxLen,
                    [](const char* text, void*) {
                      Serial.printf("{\"evt\":\"kbSubmit\",\"text\":\"%s\"}\n", text);
                    },
                    [](void*) { Serial.println("{\"evt\":\"kbCancel\"}"); },
                    nullptr);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbShow\","
                  "\"maxLen\":%d,\"mode\":%d}\n", maxLen, mode);
    return;
  }

  // TASK-410 (T_AE_07/09/10): drive the audio engine's FILE arm directly — no
  // LocalPlayer app yet (TASK-413+), so this is the only entry point. Global
  // (engine-level, not per-app dbgSet), like wifiKick/wifiDisc. Special-cased
  // against raw args, same as kbText above: real filenames on this card carry
  // spaces ("01 - Tomorrow Comes Today.mp3"), which the %127s split below
  // would truncate at the first one. A bare `set aePlayFile` (no path) falls
  // back to the hardcoded default path the gate uses.
  if (strncmp(args, "aePlayFile", 10) == 0 && (args[10] == '\0' || args[10] == ' ')) {
    const char* path = (args[10] == ' ' && args[11] != '\0') ? args + 11 : "/test.mp3";
    bool posted = aeConnectFile(path);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"aePlayFile\",\"path\":\"%s\"}\n",
                  posted ? "true" : "false", path);
    return;
  }
  // TASK-415: load an M3U into the Player mode's index. Special-cased against
  // raw args for the same reason `set aePlayFile` is — real paths on this card
  // carry spaces, which the %127s split below truncates at the first one.
  // Persists as the last playlist, so a reboot into Player mode reopens it.
  if (strncmp(args, "plLoad", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *path = (args[6] == ' ' && args[7] != '\0') ? args + 7 : "";
    if (!*path) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"plLoad\","
                     "\"error\":\"usage: set plLoad <path>\"}");
      return;
    }
    const bool ok = g_LocalPlayerApp.dbgLoad(path);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"plLoad\",\"path\":\"%s\"}\n",
                  ok ? "true" : "false", path);
    return;
  }
  // TASK-415: play a row by index — tap-to-play without needing the row's
  // screen coordinates (which depend on the live scroll offset).
  if (strncmp(args, "plPlay", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    int idx = -1;
    if (sscanf(args + 6, "%d", &idx) != 1 || idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"plPlay\","
                     "\"error\":\"usage: set plPlay <idx>\"}");
      return;
    }
    const bool ok = g_LocalPlayerApp.dbgPlayRow((uint16_t)idx);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"plPlay\",\"idx\":%d}\n",
                  ok ? "true" : "false", idx);
    return;
  }
  // TASK-416 (T_PLR_13-16): open a directory in the file browser without a
  // tap — real card paths carry spaces, same raw-args shape as plLoad above.
  if (strncmp(args, "fbOpen", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *path = (args[6] == ' ' && args[7] != '\0') ? args + 7 : "/";
    const bool ok = g_LocalPlayerApp.dbgFbOpen(path);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"fbOpen\",\"path\":\"%s\"}\n",
                  ok ? "true" : "false", path);
    return;
  }
  // TASK-416: select a browser row by index (descend / play / load) exactly
  // as if it were tapped — screen coordinates depend on the live scroll offset.
  if (strncmp(args, "fbSelect", 8) == 0 && (args[8] == '\0' || args[8] == ' ')) {
    int idx = -1;
    if (sscanf(args + 8, "%d", &idx) != 1 || idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"fbSelect\","
                     "\"error\":\"usage: set fbSelect <idx>\"}");
      return;
    }
    const bool ok = g_LocalPlayerApp.dbgFbSelect((int16_t)idx);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"fbSelect\",\"idx\":%d}\n",
                  ok ? "true" : "false", idx);
    return;
  }
  // TASK-416 (T_PLR_14): the browser's back/up affordance — the isNavigationTap
  // regression this exercises is about the REAL tap path, not this debug
  // shortcut, but this is what T_PLR_13/15/16 use to drive ascend/close.
  if (strcmp(args, "fbCancel") == 0) {
    const bool ok = g_LocalPlayerApp.dbgFbCancel();
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"fbCancel\"}\n", ok ? "true" : "false");
    return;
  }
  if (sscanf(args, "%31s %127s", var, val) != 2) {
    Serial.println("{\"ok\":false,\"cmd\":\"set\",\"error\":\"bad args\"}");
    return;
  }
  // M-COUNTRY-PICKER (CP-4): `set pick <CC>` selects on the ACTIVE SPickerList
  // by ISO code — fires onSelect exactly like a row tap (same callback, same
  // hide/cleanup; the kbText/kbOk submit-equivalent idiom). Errors when no
  // picker is active or the code isn't in the table.
  if (strcmp(var, "pick") == 0) {
    if (!g_countryPicker.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"pick\","
                      "\"error\":\"no active picker\"}");
      return;
    }
    if (g_countryPicker.pickByCode(val)) {
      Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"pick\","
                    "\"code\":\"%s\"}\n", val);
    } else {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"pick\","
                    "\"error\":\"unknown code\",\"code\":\"%s\"}\n", val);
    }
    return;
  }
  // TASK-425: standalone decoder-arena hold, independent of any stream. Lets the
  // arena-first SD/arena memory table be re-measured without dragging in WebRadio's
  // ~40 KB TLS fetch (mb_arena_acquire()/release() are the same calls WebRadioApp::
  // _play()/suspend() make — no duplicated logic, just called directly). No new
  // static state here: mb_arena.cpp already owns its own statics, this command only
  // calls through and reports heap. `set arenaHold 1` acquires (idempotent — a
  // second call while held is a no-op, same as production), `set arenaHold 0`
  // releases. Reports free heap + largest free (INTERNAL|8BIT, the byte-addressable
  // number that actually gates SD.begin()) so the caller can diff before/after
  // against a clean heap.
  if (strcmp(var, "arenaHold") == 0) {
    const uint32_t kByteCap = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    bool want = (atoi(val) != 0);
    bool ok;
    if (want) {
      ok = mb_arena_acquire();
    } else {
      mb_arena_release();
      ok = true;
    }
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"arenaHold\",\"held\":%s,"
                  "\"freeInt\":%u,\"lfbInt\":%u,\"free8\":%u,\"lfb8\":%u}\n",
                  ok ? "true" : "false", mb_arena_active() ? "true" : "false",
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_free_size(kByteCap),
                  (unsigned)heap_caps_get_largest_free_block(kByteCap));
    return;
  }
  // TASK-248: runtime log-volume control (for stress soaks). `set logLevel <d|i|w|e>`
  // sets the min severity emitted by LOG_x; `set logKeep <prefix>` always keeps tags
  // matching the prefix regardless of level (e.g. logKeep dataTask). `set logKeep -`
  // clears the keep filter.
  if (strcmp(var, "logLevel") == 0) {
    logsink::logMinLevel() = logsink::logRank(toupper((unsigned char)val[0]));
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"logLevel\",\"val\":\"%s\"}\n", val);
    return;
  }
  if (strcmp(var, "logKeep") == 0) {
    strlcpy(logsink::logKeepPrefix(), (val[0] == '-') ? "" : val, 24);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"logKeep\",\"val\":\"%s\"}\n", val);
    return;
  }
  // TASK-282 (M-WIFI-DIAG Phase 2): modem power-save A/B. Beacon timeouts are
  // classically DTIM/modem-sleep interactions (TASK-272 implicates PS; the
  // "ping keepalive masks flapping" observation is a PS signature). 0 = PS off.
  if (strcmp(var, "wifiPs") == 0) {
    bool on = (val[0] == '1');
    esp_err_t e = esp_wifi_set_ps(on ? WIFI_PS_MIN_MODEM : WIFI_PS_NONE);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"wifiPs\",\"val\":%d}\n",
                  e == ESP_OK ? "true" : "false", on ? 1 : 0);
    return;
  }
  // TASK-282: beacon watcher on/off (needs associated STA to lock BSSID).
  if (strcmp(var, "beaconWatch") == 0) {
    bool ok = (val[0] == '1') ? wifiDiag::beaconWatchStart()
                              : (wifiDiag::beaconWatchStop(), true);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"beaconWatch\",\"val\":%c}\n",
                  ok ? "true" : "false", val[0]);
    return;
  }
  // TASK-282: async scan kick — poll result via `get wifiScan` (scan-on-park
  // evidence: is the BSSID on the air when NO_AP_FOUND says it isn't?).
  if (strcmp(var, "wifiScan") == 0) {
    WiFi.scanNetworks(/*async=*/true);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"wifiScan\",\"val\":1}\n");
    return;
  }
  // TASK-426 A/B: software reset. An EN-pin/RTS reset clears the RTC domain, so
  // the casRetry flag below arrives as garbage and BOTH arms silently run the
  // control — which is exactly what happened on the first attempt at this A/B.
  // ESP.restart() is a software reset and preserves RTC memory, so the arm
  // selection actually reaches setup().
  if (strcmp(var, "reboot") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"reboot\"}\n");
    Serial.flush();
    delay(50);
    ESP.restart();
    return;
  }
  // TASK-426 A/B: `set casRetry 0` disables the per-candidate retry for the
  // NEXT boot (survives a software reset in RTC memory), `1` re-enables it.
  if (strcmp(var, "casRetry") == 0) {
    g_casRetryCookie = kCasRetryCookie;
    g_casRetryOff    = (val[0] == '0') ? 1u : 0u;
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"casRetry\",\"disabled\":%u}\n",
                  (unsigned)g_casRetryOff);
    return;
  }
  // TASK-426 repro hook: commit an arbitrary SSID to NVS so the stale-NVS
  // precondition can be recreated on demand. Without this the bug is only
  // reachable by renaming a real AP out from under a device that had already
  // associated with the old name — which is how it was found, and is not a
  // regression test anyone can re-run. Pair with a saved list holding the LIVE
  // SSID, then reset: the boot NVS stage burns its window on the dead SSID and
  // the cascade behind it must still connect.
  if (strcmp(var, "nvsSsid") == 0) {
    WiFi.persistent(true);          // FLASH storage — this is the point
    WiFi.mode(WIFI_STA);
    // Both args cast: mixing `char[]` with a string literal makes the
    // begin(char*,char*) / begin(const char*,const char*) pair ambiguous.
    WiFi.begin((const char*)val, (const char*)"notarealpassword");
    delay(100);
    WiFi.disconnect(false);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"nvsSsid\",\"val\":\"%s\"}\n", val);
    return;
  }
  // TASK-426: quiesced connect — the control for a NO_AP_FOUND wedge. While
  // wedged, autoreconnect re-fires esp_wifi_connect() every ~2.4s and the
  // supervisor kicks every 30s, so any connect under test is contended. This
  // silences both, waits for in-flight attempts to drain, then does exactly ONE
  // begin() and reports what it actually did — separating "connect genuinely
  // cannot find this AP" from "connect never got a clean run".
  if (strcmp(var, "wifiKick") == 0) {
    wifi_config_t c = {};
    esp_wifi_get_config(WIFI_IF_STA, &c);
    Serial.printf("[wifiKick] quiescing; ssid=\"%s\"\n", (const char*)c.sta.ssid);
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false, false);
    // TASK-288 discipline: every bounded wait in this file feeds the TWDT.
    // Without it this command's own waits panic-reset the board mid-diagnosis
    // (observed on the first TASK-426 build — the reset looked like a wedge
    // recovery and nearly cost a false conclusion).
    { unsigned long dl = millis() + 1500;      // let in-flight attempts drain
      while (millis() < dl) { delay(100); esp_task_wdt_reset(); } }
    Serial.printf("[wifiKick] armed, single begin()\n");
    WiFi.begin();
    uint32_t t0 = millis();
    wl_status_t st = WL_DISCONNECTED;
    while (millis() - t0 < 20000) {
      st = (wl_status_t)WiFi.status();
      if (st == WL_CONNECTED) break;
      delay(250); esp_task_wdt_reset();
    }
    Serial.printf("[wifiKick] result status=%d elapsed=%lums ip=%s rssi=%d\n",
                  (int)st, (unsigned long)(millis() - t0),
                  WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
    WiFi.setAutoReconnect(true);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"wifiKick\",\"status\":%d}\n", (int)st);
    return;
  }
  // TASK-274 (QM-2 positive control): force a disconnect so the [wifi-ev]
  // sensor can be proven live before attribution-by-absence is trusted.
  // Expect a STA_DISCONNECTED line (reason=8 ASSOC_LEAVE) then auto-reconnect.
  if (strcmp(var, "wifiDisc") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"wifiDisc\",\"val\":\"%s\"}\n", val);
    WiFi.disconnect();
    delay(200);
    WiFi.begin();   // reconnect from NVS creds
    return;
  }
  // TASK-344 (M-CERT-ERRCODE): `set certbreak <app>` arms a one-shot wrong-
  // root-CA swap for the named fetcher's next attempt (T_CERT_ERR_01). Global
  // (cross-app) like logLevel/wifiPs above, not per-app dbgSet — certbreak
  // targets a dataTask::FetchType, not any one App's own state.
  if (strcmp(var, "certbreak") == 0) {
    static const struct { const char* name; dataTask::FetchType type; } kCertBreakApps[] = {
        {"weather",       dataTask::DATA_FETCH_WEATHER},
        {"crypto",        dataTask::DATA_FETCH_CRYPTO},
        {"stockquote",    dataTask::DATA_FETCH_STOCK_QUOTE},
        {"stockchart",    dataTask::DATA_FETCH_STOCK_CHART},
        {"heatmap",       dataTask::DATA_FETCH_HEATMAP_QUOTE},
        {"stockchartsym", dataTask::DATA_FETCH_STOCK_CHART_BY_SYM},
        {"teletext",      dataTask::DATA_FETCH_TELETEXT_PAGE},
        {"webradio",      dataTask::DATA_FETCH_WEBRADIO_STATIONS},
        {"planeradar",    dataTask::DATA_FETCH_PLANERADAR},
        {"geocode",       dataTask::DATA_FETCH_GEOCODE},
    };
    for (const auto& a : kCertBreakApps) {
      if (strcmp(val, a.name) == 0) {
        dataTask::debugBreakCert(a.type);
        Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"certbreak\",\"app\":\"%s\"}\n", val);
        return;
      }
    }
    Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"certbreak\","
                  "\"error\":\"unknown app\",\"app\":\"%s\"}\n", val);
    return;
  }
  if ((spotifyDisplay && spotifyDisplay->dbgSet(var, val))
      || spotifyTask::dbg_set(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  if (stockDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  if (teletextDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  if (planeRadarDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
#ifdef WINAMP_DISPLAY
  if (webRadioDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
#endif
  // WIRE2 (§6 debug hooks, W-1): force a save — T-SETW-01/02's load→RAM→save
  // leg; nothing saves at boot, so without this a spiffs pull returns the
  // pushed bytes verbatim and proves nothing. Value is ignored ("set
  // settingsSave 1" per house two-token syntax).
  if (strcmp(var, "settingsSave") == 0) {
    SettingsStorage::save();
    Serial.println("{\"ok\":true,\"cmd\":\"set\",\"var\":\"settingsSave\",\"saved\":true}");
    return;
  }
  // WIRE2-G5 (§4-G5, W-7): sticky LDR override for T-SETW-14 — the harness
  // cannot darken the room. -1 clears; while set, BacklightFlow samples the
  // injected value instead of the ADC.
  if (strcmp(var, "ldrRaw") == 0) {
    int v = atoi(val);
    if (v < -1 || v > 4095) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"ldrRaw\","
                     "\"error\":\"range -1..4095 (-1 clears)\"}");
      return;
    }
    g_backlight.injectLdr((int16_t)v);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"ldrRaw\",\"val\":%d}\n", v);
    return;
  }
  // WIRE2-G2 (§6 debug hooks, W-7): 12h/24h toggle. Mirrors clockStyle below,
  // incl. the resume-if-current-app repaint trick for Clock.
  if (strcmp(var, "fmt24h") == 0) {
    if (val[1] != '\0' || (val[0] != '0' && val[0] != '1')) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"fmt24h\","
                     "\"error\":\"bad val — use 0|1\"}");
      return;
    }
    g_settings.fmt24h = (val[0] == '1');
    SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"fmt24h\",\"val\":%d}\n",
                  g_settings.fmt24h ? 1 : 0);
    return;
  }
  // WIRE2-G3 (§6 debug hooks, W-7): date format. 0-2 or dmy/mdy/ymd.
  if (strcmp(var, "dateFmt") == 0) {
    static const char* kDF[] = {"dmy", "mdy", "ymd"};
    int idx = -1;
    for (int i = 0; i < 3; i++) if (strcasecmp(val, kDF[i]) == 0) { idx = i; break; }
    if (idx < 0) { if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 2) idx = -1; }
    if (idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"dateFmt\","
                     "\"error\":\"bad val — use 0-2 or dmy/mdy/ymd\"}");
      return;
    }
    g_settings.dateFmt = (DateFmt)idx;
    SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"dateFmt\",\"val\":%d,"
                  "\"name\":\"%s\"}\n", idx, kDF[idx]);
    return;
  }
  if (strcmp(var, "clockStyle") == 0) {
    static const char* kSN[] = {"digital","flip","nixie","vfd"};
    int idx = -1;
    for (int i = 0; i < 4; i++) if (strcmp(val, kSN[i]) == 0) { idx = i; break; }
    if (idx < 0) { char tmp[2]; if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 3) idx = -1; }
    if (idx < 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                    "\"error\":\"bad val — use 0-3 or digital/flip/nixie/vfd\"}\n");
      return;
    }
    g_settings.clockStyle = (ClockStyle)idx;
    SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"clockStyle\",\"val\":%d,\"name\":\"%s\"}\n", idx, kSN[idx]);
    return;
  }
  if (strcmp(var, "nixieTheme") == 0 || strcmp(var, "vfdTheme") == 0) {
    // M-CLOCK-THEMES (TASK-345): same name/index tables as appsSection.h's
    // cycle rows and the M-CLOCK-NIXIE.md/M-CLOCK-VFD.md theme tables.
    bool isNixie = (strcmp(var, "nixieTheme") == 0);
    static const char* kNixieN[] = {"amber","red","green","blue"};
    static const char* kVfdN[]   = {"teal","amber","blue","green"};
    const char** names = isNixie ? kNixieN : kVfdN;
    int idx = -1;
    for (int i = 0; i < 4; i++) if (strcmp(val, names[i]) == 0) { idx = i; break; }
    if (idx < 0) { if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 3) idx = -1; }
    if (idx < 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"error\":\"bad val — use 0-3 or %s/%s/%s/%s\"}\n",
                    names[0], names[1], names[2], names[3]);
      return;
    }
    if (isNixie) g_settings.nixieTheme = (uint8_t)idx; else g_settings.vfdTheme = (uint8_t)idx;
    SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"%s\",\"val\":%d,\"name\":\"%s\"}\n",
                  var, idx, names[idx]);
    return;
  }
  if (strcmp(var, "playerMode") == 0) {   // TASK-260/413 (VE: agent-driven persist/boot tests)
    static const char* kPmNames[] = { "Spotify", "WebRadio", "Player" };
    int idx = -1;
    if      (strcasecmp(val, "spotify")  == 0) idx = 0;
    else if (strcasecmp(val, "webradio") == 0) idx = 1;
    else if (strcasecmp(val, "player")   == 0) idx = 2;
    else if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 2) idx = -1;
    if (idx < 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                    "\"error\":\"bad val — use 0-2 or spotify/webradio/player\"}\n");
      return;
    }
    // Pure persist (no app switch): sets + saves the mode so a reboot exercises the v2
    // boot-into-mode path. Use the eject toggle to actually switch the live player slot.
    persistPlayerMode((uint8_t)idx);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"playerMode\",\"val\":%d,\"name\":\"%s\"}\n",
                  idx, kPmNames[idx]);
    return;
  }
  if (strcmp(var, "prloc") == 0) {
    // M-PR-LOCATIONS (TASK-319): two sub-forms sharing the "prloc" var, both
    // carrying more tokens than the generic var/val split above captures —
    // reparse the raw `args` past "prloc " instead of relying on the
    // single-token `val` (drain-all-bytes-at-once lesson: don't assume a
    // fixed token count for multi-field commands).
    const char *rest = args + strlen(var);
    while (*rest == ' ') rest++;

    int idx;
    if (sscanf(rest, "active %d", &idx) == 1) {
      // "set prloc active <i>" — programmatic switch (T_PRL_02 etc.), so
      // switch-side effects are testable independently of strip tap
      // hit-testing. Calls the same shared primitive the strip tap uses
      // (design DEV-3/QM-1's _setActiveLoc — BP-047/LL-110: never a second
      // inline copy of the sequence).
      if (idx < 0 || idx >= (int)PR_NUM_LOCS || g_settings.prLocs[idx].label[0] == '\0') {
        Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                      "\"error\":\"bad or empty slot — active <i> needs 0..%d, non-empty\"}\n",
                      PR_NUM_LOCS - 1);
        return;
      }
      if (currentAppId == AppId::PlaneRadar) {
        // _setActiveLoc() does TFT drawing (disc repaint, strip statics) —
        // only safe to call while PlaneRadar actually owns the screen.
        // Same guard shape as `set clockStyle`'s `if (currentAppId ==
        // AppId::Clock) g_ClockApp.resume();` above.
        g_PlaneRadarApp._setActiveLoc((uint8_t)idx);
      } else {
        // Settings-side only: mirror + persist so the switch survives to
        // the next PlaneRadar resume() (which repaints from g_settings
        // fresh); no result-state reset/re-fetch needed since the app
        // isn't polling while suspended.
        g_settings.prActiveLoc = (uint8_t)idx;
        g_settings.prLat = g_settings.prLocs[idx].lat;
        g_settings.prLon = g_settings.prLocs[idx].lon;
        SettingsStorage::save();
      }
      Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"prloc\",\"active\":%d}\n", idx);
      return;
    }

    char label[16]; float lat, lon;
    if (sscanf(rest, "%d %15s %f %f", &idx, label, &lat, &lon) != 4) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"error\":"
                      "\"bad args — set prloc <i> <label> <lat> <lon> | set prloc active <i>\"}");
      return;
    }
    if (idx < 0 || idx >= (int)PR_NUM_LOCS) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                    "\"error\":\"bad index — 0..%d\"}\n", PR_NUM_LOCS - 1);
      return;
    }
    if (strlen(label) > PR_LABEL_MAX) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                    "\"error\":\"label too long — max %d chars\"}\n", PR_LABEL_MAX);
      return;
    }
    if (lat < -90.0f || lat > 90.0f || lon < -180.0f || lon > 180.0f) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                      "\"error\":\"out of range — lat -90..90, lon -180..180\"}");
      return;
    }
    for (char *p = label; *p; p++) *p = (char)toupper((unsigned char)*p);
    strlcpy(g_settings.prLocs[idx].label, label, sizeof(g_settings.prLocs[idx].label));
    g_settings.prLocs[idx].lat = lat;
    g_settings.prLocs[idx].lon = lon;
    // M-HOME-LOCATION H-3: this writer refreshed NO mirror before — editing
    // the active slot left the radar on stale coords until reboot/switch, and
    // slot-0 edits would have left weather stale. The shared matrix helper
    // fixes both obligations (home iff idx==0, active iff idx==prActiveLoc).
    SettingsStorage::prSlotWritten((uint8_t)idx);
    SettingsStorage::save();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"prloc\",\"i\":%d,"
                  "\"label\":\"%s\",\"lat\":%.6f,\"lon\":%.6f}\n",
                  idx, g_settings.prLocs[idx].label, lat, lon);
    return;
  }
  Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                "\"error\":\"unknown var\",\"var\":\"%s\"}\n", var);
}

static void cmdSwitchApp(const char *args) {
  int id = -1;
  if (sscanf(args, "%d", &id) != 1 || id < 0 || id >= (int)AppId::COUNT) {
    Serial.printf("{\"ok\":false,\"cmd\":\"switchApp\","
                  "\"error\":\"bad id — range 0..%d\"}\n", (int)AppId::COUNT - 1);
    return;
  }
  switchApp(static_cast<AppId>(id));
  Serial.printf("{\"ok\":true,\"cmd\":\"switchApp\",\"id\":%d}\n", id);
}

static void cmdInfo(const char *) {
  spotifyTask::Snapshot snap;
  spotifyTask::copySnapshot(&snap);
  const esp_app_desc_t *d = esp_ota_get_app_description();
  char elf[9];
  snprintf(elf, sizeof(elf), "%02x%02x%02x%02x",
           d->app_elf_sha256[0], d->app_elf_sha256[1],
           d->app_elf_sha256[2], d->app_elf_sha256[3]);
  Serial.printf(
    "{\"ok\":true,\"cmd\":\"info\","
    "\"git\":\"%s\",\"elf\":\"%s\",\"build\":\"%s %s\","
    "\"heap\":%lu,\"isPlaying\":%s,\"progressMs\":%ld,"
    "\"durationMs\":%ld,\"volumePct\":%d,"
    "\"shuffle\":%s,\"repeat\":%d,\"consecutiveFailures\":%u}\n",
#ifdef GIT_REV
    GIT_REV,
#else
    "n/a",
#endif
    elf, __DATE__, __TIME__,
    (unsigned long)ESP.getFreeHeap(),
    snap.isPlaying ? "true" : "false",
    snap.progressMs,
    snap.durationMs,
    (int)snap.volumePercent,
    snap.shuffleState ? "true" : "false",
    (int)snap.repeatState,
    spotifyTask::dbg_getFailureCount());
}

// Reads back the live TFT GRAM over SPI (MISO wired, TFT_MISO=12,
// SPI_READ_FREQUENCY=2.5MHz — see app/platformio.ini, lowered from 20MHz by
// TASK-340: 20MHz was signal-integrity-unreliable on this board's MISO read)
// and streams it out as base64 RGB565 bands. Lets a host tool pull an exact
// screenshot instead of
// a human eyeballing the DUT — see app/tools/screendump.py.
static void cmdScreenDump(const char *args) {
  int x = 0, y = 0, w = 320, h = 240;
  sscanf(args, "%d %d %d %d", &x, &y, &w, &h);
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  if (w <= 0 || x + w > 320) w = 320 - x;
  if (h <= 0 || y + h > 240) h = 240 - y;
  if (w <= 0 || h <= 0) {
    Serial.println("{\"ok\":false,\"cmd\":\"screendump\",\"error\":\"empty region\"}");
    return;
  }

  static const int kBandRows = 8;                       // 320*8*2 = 5120 B/band
  // TASK-423: heap-allocated per invocation (was function-static) — returns
  // the 12 KB to the heap between screendump calls instead of pinning it in
  // .bss for the life of the process; this command runs ~18s on-demand from
  // a host tool, not on any hot path, so the malloc cost is irrelevant.
  const size_t kB64Size = ((320 * kBandRows * 2 + 2) / 3) * 4 + 8;
  uint16_t *s_band = (uint16_t *)malloc(sizeof(uint16_t) * 320 * kBandRows);
  unsigned char *s_b64 = (unsigned char *)malloc(kB64Size);
  if (!s_band || !s_b64) {
    free(s_band);
    free(s_b64);
    Serial.println("{\"ok\":false,\"cmd\":\"screendump\",\"error\":\"alloc failed\"}");
    return;
  }

  Serial.printf("{\"ok\":true,\"cmd\":\"screendump\",\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d,\"bpp\":16}\n",
                x, y, w, h);

  for (int ry = 0; ry < h; ry += kBandRows) {
    // TASK-288 pattern: a full-canvas dump is ~30 bands x ~590ms of Serial.write
    // at 115200 baud (~18s total) — comfortably over the 15s TWDT panic timeout
    // (esp_task_wdt_init(15, true), main.cpp setup()) with zero feeds otherwise.
    // Without this the loop task panics mid-dump and the device hard-resets —
    // the host then keeps reading post-reboot output none the wiser, silently
    // splicing in whatever the fresh boot's default screen happens to show.
    esp_task_wdt_reset();
    int rows = min(kBandRows, h - ry);
    tft.readRect(x, y + ry, w, rows, s_band);
    // TASK-340: tft.readRect() (vendored TFT_eSPI.cpp ~line 1412-1413) returns
    // each pixel byte-swapped ("Swapped colour byte order for compatibility
    // with pushRect()") — deliberate upstream behaviour so its output can be
    // fed straight back into pushRect(), but NOT standard RGB565. Undo it
    // here so the stream this command emits is true RGB565, matching what
    // screendump.py's rgb565_to_rgb888() already (correctly) assumes.
    // DUT-confirmed via `colorprobe` (main.cpp cmdColorProbe): a systematic
    // fillRect/pushRect + readRect sweep matched this byte-swap exactly,
    // 25/25, once SPI_READ_FREQUENCY was lowered — see next comment.
    for (int i = 0; i < w * rows; i++) {
      uint16_t v = s_band[i];
      s_band[i] = (v << 8) | (v >> 8);
    }
    size_t inLen = (size_t)w * rows * 2;
    size_t outLen = 0;
    mbedtls_base64_encode(s_b64, kB64Size, &outLen, (const unsigned char *)s_band, inLen);
    Serial.printf("SCREENDUMP:BAND %d %d ", ry, rows);
    Serial.write(s_b64, outLen);
    Serial.println();
  }
  Serial.println("SCREENDUMP:END");
  free(s_band);
  free(s_b64);
}

// TASK-340 investigation aid: fills a small on-screen swatch with a *known*
// RGB565 value, then reads it straight back with tft.readRect() and prints
// expected vs. actual as one JSON line per probe. Two probe families:
//   - "fill": tft.fillRect(v) then readRect — exercises the normal write
//     path (color565-quantized 16bpp write) + the 18bpp GRAM read-back.
//   - "push": tft.pushRect() with a raw uint16 array (bypasses fillRect's
//     color565 encode — pushRect disables _swapBytes and writes the words
//     as-is) then readRect — isolates whether a fault survives a pure
//     write/read round trip of an arbitrary bit pattern (0xAAAA/0x5555/
//     0xDEADBEEF-style words), vs. only showing up on "real" colours.
// `actual` is the *raw, unmodified* return from tft.readRect() (i.e.
// including that function's own "swapped for pushRect() compatibility"
// byte swap) — deliberately not pre-corrected, so the transform can be
// derived from this data rather than assumed. See docs/project/tasks.md
// TASK-340 for findings.
static void cmdColorProbe(const char *) {
  static const uint16_t kFillSweep[] = {
    0xF800, 0x07E0, 0x001F, 0xFFFF, 0x0000, 0xF81F, 0x07FF, 0xFFE0,
    0x8000, 0x0400, 0x0010, 0x7800, 0x03E0, 0x000F, 0x4208, 0x9492,
  };
  static const uint16_t kPushSweep[] = {
    0xAAAA, 0x5555, 0x1234, 0x4321, 0xDEAD, 0xBEEF, 0xCAFE, 0x0F0F, 0xF0F0,
  };
  const int px = 40, py = 40, sz = 8;
  const size_t nFill = sizeof(kFillSweep) / sizeof(kFillSweep[0]);
  const size_t nPush = sizeof(kPushSweep) / sizeof(kPushSweep[0]);

  Serial.println("{\"ok\":true,\"cmd\":\"colorprobe\"}");

  for (size_t i = 0; i < nFill; i++) {
    uint16_t v = kFillSweep[i];
    tft.fillRect(px, py, sz, sz, v);
    delay(2);
    uint16_t band[4] = {0};
    tft.readRect(px + 2, py + 2, 2, 2, band);
    bool last = (i + 1 == nFill) && (nPush == 0);
    Serial.printf("{\"probe\":\"fill\",\"expected\":%u,\"actual\":%u,\"last\":%s}\n",
                  (unsigned)v, (unsigned)band[0], last ? "true" : "false");
  }

  for (size_t i = 0; i < nPush; i++) {
    uint16_t v = kPushSweep[i];
    uint16_t block[4] = {v, v, v, v};
    tft.pushRect(px, py, 2, 2, block);
    delay(2);
    uint16_t band[4] = {0};
    tft.readRect(px, py, 2, 2, band);
    bool last = (i + 1 == nPush);
    Serial.printf("{\"probe\":\"push\",\"expected\":%u,\"actual\":%u,\"last\":%s}\n",
                  (unsigned)v, (unsigned)band[0], last ? "true" : "false");
  }
}

// TASK-408/427: SD mount state + sdReady() live here, gated on SD_BOOT_MOUNT (not
// SERIAL_DEBUG) — see the block just above the SERIAL_DEBUG command section below.
static const char *sdCardTypeName(sdcard_type_t t) {
  switch (t) {
    case CARD_MMC:  return "MMC";
    case CARD_SD:   return "SDSC";
    case CARD_SDHC: return "SDHC";
    case CARD_NONE: return "NONE";
    default:        return "UNKNOWN";
  }
}

// TASK-408 root-cause instrument. `esp_vfs_fat_register()` returns ESP_ERR_NO_MEM from
// two distinct places: the FF_VOLUMES context table being full, and a plain calloc()
// failing. This separates them — it prints the exact contiguous block SD.begin() will
// ask for at each max_files setting, then actually tries to calloc that block and
// reports which sizes the live heap can still serve.
static void cmdSdMem(const char *) {
  // MALLOC_CAP_INTERNAL alone over-reports what a plain calloc() can be served: it
  // counts the 32-bit-only D/IRAM region, which is not byte-addressable. The number
  // that actually gates the mount is the INTERNAL|8BIT largest free block.
  const uint32_t kByteCap = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
  Serial.printf("{\"probe\":\"sdmem\",\"FF_VOLUMES\":%d,\"FF_MAX_SS\":%d,\"FF_FS_TINY\":%d,"
                "\"FF_USE_LFN\":%d,\"sizeofFATFS\":%u,\"sizeofFIL\":%u,"
                "\"freeInt\":%u,\"lfbInt\":%u,\"minFreeInt\":%u,"
                "\"free8\":%u,\"lfb8\":%u,\"freeDma\":%u,\"lfbDma\":%u,"
                "\"mounted\":%s}\n",
                (int)FF_VOLUMES, (int)FF_MAX_SS, (int)FF_FS_TINY, (int)FF_USE_LFN,
                (unsigned)sizeof(FATFS), (unsigned)sizeof(FIL),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_free_size(kByteCap),
                (unsigned)heap_caps_get_largest_free_block(kByteCap),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA),
                s_sdReady ? "true" : "false");

  // Largest single byte-addressable block the live heap can actually serve, by
  // bisection. `lfb8` is the allocator's view of its biggest free span; this is the
  // number that decides whether SD.begin() survives, and the two can differ by the
  // block header and alignment.
  {
    size_t lo = 0, hi = 65536;
    while (lo + 64 < hi) {
      size_t mid = (lo + hi) / 2;
      void *p = malloc(mid);
      if (p) { free(p); lo = mid; } else { hi = mid; }
      esp_task_wdt_reset();
    }
    Serial.printf("{\"probe\":\"sdmem\",\"maxCallocB\":%u}\n", (unsigned)lo);
  }

  // vfs_fat_ctx_t is private to the IDF, but its layout is FATFS + a handful of
  // scalars + FIL[max_files]; 128 B covers the scalars and any padding with margin.
  const unsigned kCtxOverhead = 128;
  static const uint8_t kSlots[] = { 1, 2, 3, 5 };
  for (unsigned i = 0; i < sizeof(kSlots); i++) {
    size_t need = sizeof(FATFS) + kCtxOverhead + (size_t)kSlots[i] * sizeof(FIL);
    void *p = calloc(1, need);
    bool got = (p != nullptr);
    if (p) free(p);
    bool last = (i + 1 == sizeof(kSlots));
    Serial.printf("{\"probe\":\"sdmem\",\"maxFiles\":%u,\"ctxBytes\":%u,\"callocOk\":%s,"
                  "\"lfb8\":%u,\"last\":%s}\n",
                  (unsigned)kSlots[i], (unsigned)need, got ? "true" : "false",
                  (unsigned)heap_caps_get_largest_free_block(kByteCap),
                  last ? "true" : "false");
    esp_task_wdt_reset();
  }
}

// Live mount attempt from the serial-command context, i.e. with spotifyTask/dataTask
// alive — the exact path that was reported as failing.
static void cmdSdMount(const char *args) {
  int maxFiles = kSdMaxFiles;
  unsigned freqHz = 0;
  sscanf(args, "%d %u", &maxFiles, &freqHz);
  if (maxFiles < 1) maxFiles = 1;
  if (maxFiles > 10) maxFiles = 10;
  if (freqHz >= 400000 && freqHz <= 40000000) s_sdFreqHz = freqHz;
  if (s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmount\",\"error\":\"already mounted\"}");
    return;
  }
  s_sdReady = sdMountAttempt("live", (uint8_t)maxFiles);
  Serial.printf("{\"ok\":%s,\"cmd\":\"sdmount\",\"mounted\":%s}\n",
                s_sdReady ? "true" : "false", s_sdReady ? "true" : "false");
}

// Unmount and report the heap actually handed back. This is the clean T_SD_06
// measurement: a mount-cost delta taken across SD.begin() during boot is polluted by
// WiFi/NTP/task-start allocations landing in the same window, but the free() side of
// an idle unmount is not.
static void cmdSdUmount(const char *) {
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdumount\",\"error\":\"not mounted\"}");
    return;
  }
  size_t freeBefore = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbBefore = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  SD.end();
  s_sdSPI.end();
  s_sdSpiUp = false;
  s_sdReady = false;
  size_t freeAfter = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbAfter = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  Serial.printf("{\"ok\":true,\"cmd\":\"sdumount\",\"reclaimedB\":%ld,"
                "\"freeIntBefore\":%u,\"freeIntAfter\":%u,"
                "\"lfbIntBefore\":%u,\"lfbIntAfter\":%u}\n",
                (long)freeAfter - (long)freeBefore,
                (unsigned)freeBefore, (unsigned)freeAfter,
                (unsigned)lfbBefore, (unsigned)lfbAfter);
}

// T_SD_08: N live mount/unmount cycles against the same VSPI session, from the same
// serial-command execution context as sdprobe (concurrent tasks alive) — reuses the
// already-good boot-established path rather than a fresh live mount (which is exactly
// what's broken; see sdProbeBootMount()'s comment). Leaves SD mounted on return.
static void cmdSdCycle(const char *args) {
  int cycles = 20;
  sscanf(args, "%d", &cycles);
  if (cycles < 1) cycles = 1;
  if (cycles > 200) cycles = 200;

  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdcycle\",\"error\":\"not mounted at boot\"}");
    return;
  }

  size_t baseline = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  Serial.printf("{\"ok\":true,\"cmd\":\"sdcycle\",\"cycles\":%d,\"baselineFreeInt\":%u}\n",
                cycles, (unsigned)baseline);

  int okCount = 0;
  for (int i = 0; i < cycles; i++) {
    SD.end();
    s_sdSPI.end();
    s_sdSPI.begin(kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    s_sdSpiUp = true;
    bool ok = SD.begin(kSdCsPin, s_sdSPI, s_sdFreqHz, "/sd", kSdMaxFiles);
    size_t freeNow = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    long drift = (long)baseline - (long)freeNow;
    bool last = (i + 1 == cycles);
    Serial.printf("{\"probe\":\"sdcycle\",\"i\":%d,\"ok\":%s,\"freeInt\":%u,\"driftB\":%ld,\"last\":%s}\n",
                  i, ok ? "true" : "false", (unsigned)freeNow, drift, last ? "true" : "false");
    if (ok) { okCount++; } else { s_sdReady = false; break; }
    esp_task_wdt_reset();
  }
  s_sdReady = (okCount == cycles);
}

// ── TASK-415: host → card file upload, for test fixtures ─────────────────────
// `sdmkdir <path>` and `sdput <w|a> <base64> <path>` — the path comes LAST because
// real paths on this card contain spaces and the args split does not quote.
//
// This exists because the M3U gate fixtures have to get onto the card somehow and
// the alternative is a human with a card reader. It is test tooling, SERIAL_DEBUG
// only, and it is emphatically NOT the "playlist persistence" that TASK-424 says
// must not be built on this write path: each call is one open/write/close of <=108
// bytes, which is the short-burst pattern that measurably works, and no product
// feature depends on it. TASK-421's save path is still blocked on TASK-424.
//
// The 160-byte serial line buffer sets the chunk size: ~120 base64 characters, so
// 90 bytes per call. app/tools/sd_put.py drives it.
static void cmdSdMkdir(const char *args) {
  if (!s_sdReady) { Serial.println("{\"ok\":false,\"cmd\":\"sdmkdir\",\"error\":\"not mounted\"}"); return; }
  if (!args || !*args) { Serial.println("{\"ok\":false,\"cmd\":\"sdmkdir\",\"error\":\"usage: sdmkdir <path>\"}"); return; }
  const bool existed = SD.exists(args);
  const bool ok = existed || SD.mkdir(args);
  Serial.printf("{\"ok\":%s,\"cmd\":\"sdmkdir\",\"path\":\"%s\",\"existed\":%s}\n",
                ok ? "true" : "false", args, existed ? "true" : "false");
}

static void cmdSdPut(const char *args) {
  if (!s_sdReady) { Serial.println("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"not mounted\"}"); return; }
  char op = 0;
  char b64[144];
  if (!args || sscanf(args, "%c %143s", &op, b64) != 2 || (op != 'w' && op != 'a')) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"usage: sdput <w|a> <base64|-> <path>\"}");
    return;
  }
  // Path is everything after the base64 field — spaces and all.
  const char *p = strstr(args, b64);
  const char *path = p ? p + strlen(b64) : nullptr;
  while (path && *path == ' ') path++;
  if (!path || !*path) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"missing path\"}");
    return;
  }
  uint8_t bin[112];
  size_t  olen = 0;
  if (strcmp(b64, "-") != 0) {   // "-" = no payload (create/truncate only)
    const int rc = mbedtls_base64_decode(bin, sizeof(bin), &olen,
                                         (const unsigned char *)b64, strlen(b64));
    if (rc != 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"base64 decode rc=%d\"}\n", rc);
      return;
    }
  }
  File f = SD.open(path, op == 'w' ? FILE_WRITE : FILE_APPEND);
  if (!f) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"open failed\",\"path\":\"%s\"}\n", path);
    return;
  }
  const size_t wrote = olen ? f.write(bin, olen) : 0;
  f.flush();                 // size() reads the FIL, which is stale until the
  const size_t total = f.size();   // write is pushed through — 0 B otherwise
  f.close();
  Serial.printf("{\"ok\":%s,\"cmd\":\"sdput\",\"op\":\"%c\",\"wrote\":%u,\"sizeB\":%u,\"path\":\"%s\"}\n",
                (wrote == olen) ? "true" : "false", op,
                (unsigned)wrote, (unsigned)total, path);
}

// Raw sector reader, below the FatFs layer, so a card that initialises over SPI but
// carries no mountable volume can still be identified. Answers the only question a
// "no valid FAT volume" mount failure leaves open: what IS on the card.
static void cmdSdMbr(const char *) {
  if (s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"unmount first (sdumount)\"}");
    return;
  }
  if (!s_sdSpiUp) {
    s_sdSPI.begin(kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    s_sdSpiUp = true;
  }
  uint8_t pdrv = sdcard_init(kSdCsPin, &s_sdSPI, (int)s_sdFreqHz);
  if (pdrv == 0xFF) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"sdcard_init failed\"}");
    return;
  }
  // sdcard_init() only claims a drive slot — the card is not identified until FatFs
  // calls disk_initialize() from f_mount. Without this the card reads back as
  // CARD_NONE with a nonsense sector count. The mount is EXPECTED to fail here (that
  // is the whole point); it leaves the card initialised, which is what raw reads need.
  bool mountOk = sdcard_mount(pdrv, "/sdraw", 1, false);
  Serial.printf("{\"probe\":\"sdmbr\",\"initMountOk\":%s}\n", mountOk ? "true" : "false");

  Serial.printf("{\"probe\":\"sdmbr\",\"cardType\":\"%s\",\"sectors\":%u,\"sectorSizeB\":%u,"
                "\"capacityMB\":%u}\n",
                sdCardTypeName(sdcard_type(pdrv)), (unsigned)sdcard_num_sectors(pdrv),
                (unsigned)sdcard_sector_size(pdrv),
                (unsigned)((uint64_t)sdcard_num_sectors(pdrv) * sdcard_sector_size(pdrv) / (1024 * 1024)));

  uint8_t *buf = (uint8_t *)malloc(512);
  if (!buf) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"alloc\"}");
    sdcard_uninit(pdrv);
    return;
  }

  // Sector 0, then whatever the first MBR entry points at. A card formatted as one
  // big volume with no partition table puts the boot sector at 0 instead.
  // With no card in the slot the driver still hands back a pdrv and reports a nonsense
  // geometry (CARD_UNKNOWN, ~31 k sectors), so the summary must not read ok:true just
  // because the calls returned. Track whether anything was actually readable.
  bool cardUsable = (sdcard_type(pdrv) != CARD_NONE && sdcard_type(pdrv) != CARD_UNKNOWN);
  bool sector0Ok = false;
  uint32_t probeSectors[2] = { 0, 0 };
  int nProbe = 1;
  if (sd_read_raw(pdrv, buf, 0)) {
    sector0Ok = true;
    bool sig = (buf[510] == 0x55 && buf[511] == 0xAA);
    // OEM name at +3 is "EXFAT   " for exFAT, "MSDOS"/"mkfs.fat"/etc for FAT.
    char oem[9] = {0};
    memcpy(oem, buf + 3, 8);
    for (int i = 0; i < 8; i++) if (oem[i] < 32 || oem[i] > 126) oem[i] = '.';
    uint8_t ptype = buf[0x1BE + 4];
    uint32_t plba = (uint32_t)buf[0x1BE + 8] | ((uint32_t)buf[0x1BE + 9] << 8) |
                    ((uint32_t)buf[0x1BE + 10] << 16) | ((uint32_t)buf[0x1BE + 11] << 24);
    Serial.printf("{\"probe\":\"sdmbr\",\"sector\":0,\"bootSig\":%s,\"oem\":\"%s\","
                  "\"part0Type\":\"0x%02X\",\"part0Lba\":%u}\n",
                  sig ? "true" : "false", oem, ptype, (unsigned)plba);
    if (plba > 0 && plba < sdcard_num_sectors(pdrv)) { probeSectors[1] = plba; nProbe = 2; }
  } else {
    Serial.println("{\"probe\":\"sdmbr\",\"sector\":0,\"readFailed\":true}");
  }

  for (int i = 0; i < nProbe; i++) {
    if (i == 0) continue;   // already reported above
    if (!sd_read_raw(pdrv, buf, probeSectors[i])) {
      Serial.printf("{\"probe\":\"sdmbr\",\"sector\":%u,\"readFailed\":true}\n",
                    (unsigned)probeSectors[i]);
      continue;
    }
    char oem[9] = {0}, fstype[9] = {0}, fstype32[9] = {0};
    memcpy(oem, buf + 3, 8);
    memcpy(fstype, buf + 0x36, 8);     // FAT12/FAT16
    memcpy(fstype32, buf + 0x52, 8);   // FAT32
    for (int k = 0; k < 8; k++) {
      if (oem[k] < 32 || oem[k] > 126) oem[k] = '.';
      if (fstype[k] < 32 || fstype[k] > 126) fstype[k] = '.';
      if (fstype32[k] < 32 || fstype32[k] > 126) fstype32[k] = '.';
    }
    uint16_t bytesPerSec = (uint16_t)buf[11] | ((uint16_t)buf[12] << 8);
    Serial.printf("{\"probe\":\"sdmbr\",\"sector\":%u,\"oem\":\"%s\",\"fsType\":\"%s\","
                  "\"fsType32\":\"%s\",\"bytesPerSector\":%u,\"bootSig\":%s}\n",
                  (unsigned)probeSectors[i], oem, fstype, fstype32, (unsigned)bytesPerSec,
                  (buf[510] == 0x55 && buf[511] == 0xAA) ? "true" : "false");
  }
  free(buf);
  if (mountOk) sdcard_unmount(pdrv);
  sdcard_uninit(pdrv);
  s_sdSPI.end();
  s_sdSpiUp = false;
  if (!cardUsable || !sector0Ok) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"no readable card\","
                  "\"cardUsable\":%s,\"sector0Ok\":%s}\n",
                  cardUsable ? "true" : "false", sector0Ok ? "true" : "false");
    return;
  }
  Serial.println("{\"ok\":true,\"cmd\":\"sdmbr\"}");
}

// Plain directory listing with sizes — needed to pick a pre-existing, cleanly
// written file to benchmark reads against.
static void cmdSdLs(const char *args) {
  // `sdls <dir> q` suppresses the per-entry lines: at 115200 baud the Serial writes
  // dominate the walk, so the timing is only meaningful with them off.
  char dir[64] = "/", flag[8] = {0};
  if (args && args[0]) { sscanf(args, "%63s %7s", dir, flag); }
  bool quiet = (flag[0] == 'q' || flag[0] == 'Q' || flag[0] == 'n' || flag[0] == 'N');
  // `n` also skips File::size(). That call is a path-based stat, which FatFs resolves by
  // scanning the directory from its start — so doing it per entry makes a listing O(n^2)
  // in directory size. Comparing `q` against `n` prices what showing file sizes costs
  // browse-001, as opposed to what walking the directory costs.
  bool doStat = !(flag[0] == 'n' || flag[0] == 'N');
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdls\",\"error\":\"not mounted\"}");
    return;
  }
  File d = SD.open(dir);
  if (!d || !d.isDirectory()) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdls\",\"error\":\"not a directory\",\"dir\":\"%s\"}\n", dir);
    if (d) d.close();
    return;
  }
  int n = 0;
  unsigned long t0 = micros();
  while (n < 400) {
    File e = d.openNextFile();
    if (!e) break;
    if (!quiet) {
      Serial.printf("{\"probe\":\"sdls\",\"name\":\"%s\",\"dir\":%s,\"sizeB\":%u}\n",
                    e.name(), e.isDirectory() ? "true" : "false", (unsigned)e.size());
    } else if (doStat) {
      (void)e.size();   // the per-entry stat -- see doStat above
    }
    e.close();
    n++;
    esp_task_wdt_reset();
  }
  unsigned long elapsedMs = (micros() - t0) / 1000;
  d.close();
  // With `q` this is the walk cost alone; without it the Serial writes dominate.
  Serial.printf("{\"ok\":true,\"cmd\":\"sdls\",\"count\":%d,\"elapsedMs\":%lu}\n",
                n, elapsedMs);
}

// Read-only sustained benchmark against a caller-chosen path. Same measurement as
// sdprobe's bench phase, but it never writes, so it can be pointed at a file the
// card already carried rather than one this probe created.
static void cmdSdRead(const char *args) {
  // Read count FIRST, then the rest of the line as the path: real filenames on this
  // card contain spaces, so the path has to be the unbounded trailing field.
  char path[96] = {0};
  int reads = 5000, consumed = 0;
  if (!args || sscanf(args, "%d %n", &reads, &consumed) != 1 || !args[consumed]) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdread\",\"error\":\"usage: sdread <reads> <path>\"}");
    return;
  }
  strlcpy(path, args + consumed, sizeof(path));
  if (reads < 100) reads = 100;
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdread\",\"error\":\"not mounted\"}");
    return;
  }
  File f = SD.open(path, FILE_READ);
  if (!f) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdread\",\"error\":\"open failed\",\"path\":\"%s\"}\n", path);
    return;
  }
  size_t fileSize = f.size();
  static const uint32_t kEdgeUs[] = {
    250, 500, 1000, 2000, 4000, 8000, 16000, 32000, 50000, 100000, 0xFFFFFFFFu
  };
  const int kNB = (int)(sizeof(kEdgeUs) / sizeof(kEdgeUs[0]));
  uint32_t bk[kNB];
  memset(bk, 0, sizeof(bk));
  static uint8_t rbuf[512];
  uint32_t maxUs = 0;
  size_t bytes = 0;
  int zeroReads = 0, wraps = 0;
  unsigned long t0all = micros();
  for (int i = 0; i < reads; i++) {
    unsigned long t0 = micros();
    size_t n = f.read(rbuf, sizeof(rbuf));
    unsigned long t1 = micros();
    uint32_t dt = (uint32_t)(t1 - t0);
    if (dt > maxUs) maxUs = dt;
    for (int b = 0; b < kNB; b++) { if (dt <= kEdgeUs[b]) { bk[b]++; break; } }
    if (n == 0) {
      // A failed physical read latches the stdio stream's error flag, and seek()
      // does not clear it — every later read then returns 0 instantly, which ends
      // the measurement early and understates sustained throughput. Reopen instead,
      // resuming at the offset reached, and count the recoveries.
      zeroReads++;
      size_t resumeAt = (size_t)f.position();
      f.close();
      f = SD.open(path, FILE_READ);
      if (!f) { break; }
      if (resumeAt + sizeof(rbuf) < fileSize) f.seek(resumeAt); else { f.seek(0); wraps++; }
    } else {
      bytes += n;
    }
    if ((i % 50) == 0) esp_task_wdt_reset();
  }
  unsigned long elapsedUs = micros() - t0all;
  f.close();

  uint32_t p50 = 0, p99 = 0, cum = 0;
  uint32_t need50 = (uint32_t)((reads * 50 + 99) / 100);
  uint32_t need99 = (uint32_t)((reads * 99 + 99) / 100);
  for (int b = 0; b < kNB; b++) {
    cum += bk[b];
    if (!p50 && cum >= need50) p50 = kEdgeUs[b];
    if (!p99 && cum >= need99) { p99 = kEdgeUs[b]; break; }
  }
  if (p50 > maxUs) p50 = maxUs;
  if (p99 > maxUs) p99 = maxUs;

  char histo[192];
  int off = 0;
  for (int b = 0; b < kNB && off < (int)sizeof(histo) - 12; b++) {
    off += snprintf(histo + off, sizeof(histo) - off, "%s%lu", b ? "," : "",
                    (unsigned long)bk[b]);
  }
  Serial.printf("{\"ok\":true,\"cmd\":\"sdread\",\"path\":\"%s\",\"fileB\":%u,"
                "\"reads\":%d,\"zeroReads\":%d,\"wraps\":%d,\"bytes\":%u,"
                "\"elapsedMs\":%lu,\"throughputKBps\":%.1f,"
                "\"p50Ms\":%.2f,\"p99Ms\":%.2f,\"maxMs\":%.2f,\"histo\":[%s]}\n",
                path, (unsigned)fileSize, reads, zeroReads, wraps, (unsigned)bytes,
                (unsigned long)(elapsedUs / 1000),
                elapsedUs ? ((float)bytes / 1024.0f) / ((float)elapsedUs / 1000000.0f) : 0.0f,
                p50 / 1000.0f, p99 / 1000.0f, maxUs / 1000.0f, histo);
}

// Isolated sequential write: nothing but open / write x N / close, so a write-path
// fault can be separated from anything the earlier sdprobe phases leave behind.
static void cmdSdWrite(const char *args) {
  int chunks = 64, checkEvery = 0, append = 0;
  sscanf(args, "%d %d %d", &chunks, &checkEvery, &append);
  if (chunks < 1) chunks = 1;
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdwrite\",\"error\":\"not mounted\"}");
    return;
  }
  static uint8_t wbuf[512];
  memset(wbuf, 0xA5, sizeof(wbuf));
  // Append mode builds the read fixture in short bursts: sustained single-open
  // writes are what fail on this card, short open/write/close bursts are not.
  File f = SD.open("/probebench.bin", append ? FILE_APPEND : FILE_WRITE);
  if (!f) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdwrite\",\"error\":\"open failed\"}");
    return;
  }
  Serial.printf("{\"probe\":\"sdwrite\",\"phase\":\"opened\",\"chunks\":%d,"
                "\"append\":%d,\"startSizeB\":%u}\n",
                chunks, append, (unsigned)f.size());
  size_t total = 0;
  unsigned long t0 = millis();
  for (int i = 0; i < chunks; i++) {
    size_t n = f.write(wbuf, sizeof(wbuf));
    total += n;
    if (n != sizeof(wbuf)) {
      Serial.printf("{\"probe\":\"sdwrite\",\"shortWrite\":%u,\"atChunk\":%d}\n",
                    (unsigned)n, i);
      break;
    }
    // The FIL that f_write faults on lives inside the mount's heap block, so a
    // stomped allocator structure would show up here before the fault does.
    if (checkEvery > 0 && ((i + 1) % checkEvery) == 0) {
      if (!heap_caps_check_integrity_all(true)) {
        Serial.printf("{\"probe\":\"sdwrite\",\"heapCorruptAtChunk\":%d}\n", i);
        break;
      }
    }
    esp_task_wdt_reset();
  }
  unsigned long elapsedMs = millis() - t0;
  f.close();
  size_t endSize = 0;
  { File chk = SD.open("/probebench.bin", FILE_READ); if (chk) { endSize = chk.size(); chk.close(); } }
  Serial.printf("{\"ok\":true,\"cmd\":\"sdwrite\",\"bytes\":%u,\"endSizeB\":%u,"
                "\"elapsedMs\":%lu,\"kBps\":%.1f}\n",
                (unsigned)total, (unsigned)endSize, elapsedMs,
                elapsedMs ? ((float)total / 1024.0f) / ((float)elapsedMs / 1000.0f) : 0.0f);
}

// Removes the sdprobe fixtures. A watchdog reboot during the bench-file write leaves
// a half-written file behind, and a re-run then measures whatever that left on the
// card rather than a clean sequential file.
static void cmdSdClean(const char *) {
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdclean\",\"error\":\"not mounted\"}");
    return;
  }
  int removed = 0;
  if (SD.exists("/probebench.bin") && SD.remove("/probebench.bin")) removed++;
  char path[40];
  for (int i = 0; i < 400; i++) {
    snprintf(path, sizeof(path), "/probelist/f%03d.txt", i);
    if (SD.exists(path) && SD.remove(path)) removed++;
    if ((i % 20) == 0) esp_task_wdt_reset();
  }
  bool rmdirOk = SD.rmdir("/probelist");
  Serial.printf("{\"ok\":true,\"cmd\":\"sdclean\",\"removed\":%d,\"rmdir\":%s}\n",
                removed, rmdirOk ? "true" : "false");
}

static void cmdSdProbe(const char *args) {
  int reads = 5000, skipWrites = 0;
  sscanf(args, "%d %d", &reads, &skipWrites);
  if (reads < 100) reads = 100;

  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdprobe\",\"error\":\"mount failed\"}");
    return;
  }

  size_t freeIntBefore = s_sdBootFreeIntBefore;
  size_t freeIntAfter = s_sdBootFreeIntAfter;
  size_t lfbIntBefore = s_sdBootLfbIntBefore;
  size_t lfbIntAfter = s_sdBootLfbIntAfter;
  long heapDeltaB = (long)freeIntBefore - (long)freeIntAfter;

  sdcard_type_t cardType = SD.cardType();
  uint64_t cardSizeMB = SD.cardSize() / (1024 * 1024);
  uint64_t totalMB = SD.totalBytes() / (1024 * 1024);
  uint64_t usedMB = SD.usedBytes() / (1024 * 1024);

  // Phase markers: this probe can run for minutes on a contended bus, and a bare
  // silence is indistinguishable from a hang.
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"lfn\"}");
  esp_task_wdt_reset();

  // Long-filename round-trip: >8.3, spaces, mixed case.
  const char *kLfnPath = "/A long name (test) 01.mp3";
  bool lfnOk = false;
  if (!skipWrites) {
    File f = SD.open(kLfnPath, FILE_WRITE);
    if (f) {
      f.write((const uint8_t *)"probe", 5);
      f.close();
      File r = SD.open(kLfnPath, FILE_READ);
      if (r) {
        lfnOk = (strcmp(r.name(), "A long name (test) 01.mp3") == 0);
        r.close();
      }
      SD.remove(kLfnPath);
    }
  }

  // ~200-file directory listing timing. Files created once if absent; setup cost is
  // excluded from the timed window (browse-001 cares about steady-state page cost).
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"mkfiles\"}");
  esp_task_wdt_reset();
  const char *kListDir = "/probelist";
  const int kListFiles = 200;
  if (!skipWrites && !SD.exists(kListDir)) SD.mkdir(kListDir);
  if (!skipWrites) {
    int existing = 0;
    File dir = SD.open(kListDir);
    if (dir) {
      // NOT `for (File e = d.openNextFile(); e; e = d.openNextFile())`: the
      // increment opens the next entry while the current File is still alive, so
      // two open-file slots are needed to walk a directory one entry at a time.
      while (true) {
        File e = dir.openNextFile();
        if (!e) break;
        existing++;
        e.close();
        esp_task_wdt_reset();
      }
      dir.close();
    }
    for (int i = existing; i < kListFiles; i++) {
      char path[40];
      snprintf(path, sizeof(path), "%s/f%03d.txt", kListDir, i);
      File f = SD.open(path, FILE_WRITE);
      if (f) { f.write((const uint8_t *)"x", 1); f.close(); }
      // Every iteration, not every 20th: a single create+write+close on a
      // contended 4 MHz bus can take most of a second, and 20 of them overran
      // the 15 s TWDT outright on the first run of this probe.
      esp_task_wdt_reset();
    }
  }
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"list\"}");
  esp_task_wdt_reset();
  int listCount = 0;
  unsigned long listStartUs = micros();
  {
    File dir = SD.open(kListDir);
    if (dir) {
      while (true) {                       // see the counting loop above
        File e = dir.openNextFile();
        if (!e) break;
        listCount++;
        e.close();
        if ((listCount % 25) == 0) esp_task_wdt_reset();
      }
      dir.close();
    }
  }
  unsigned long listElapsedMs = (micros() - listStartUs) / 1000;

  // Sustained sequential-read benchmark + per-read latency histogram (T_SD_04/05).
  // Bench file created once if absent/undersized; that write is not part of the timed
  // window. Read chunk (512 B) is deliberately smaller than InBuff (6 400 B) so `reads`
  // reads comfortably exceeds the >=2 MB / N>=5 000 bar at the default arg.
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"bench-prepare\"}");
  esp_task_wdt_reset();
  const size_t kChunk = 512;
  const char *kBenchPath = "/probebench.bin";
  size_t benchFileSize = (size_t)reads * kChunk;
  const size_t kBenchFileMax = 1024 * 1024;   // read pass wraps via seek(0)
  if (benchFileSize > kBenchFileMax) benchFileSize = kBenchFileMax;
  // Any file of at least this size is a usable bench target — the read pass wraps
  // with seek(0), so an exact size buys nothing, and demanding one forces a
  // multi-megabyte rewrite on every run.
  const size_t kBenchFileMin = 64 * 1024;
  size_t benchActualSize = 0;
  bool benchFileOk = SD.exists(kBenchPath);
  if (benchFileOk) {
    File existing = SD.open(kBenchPath, FILE_READ);
    if (!existing || existing.size() < kBenchFileMin) {
      benchFileOk = false;
    } else {
      benchActualSize = existing.size();
    }
    if (existing) existing.close();
  }
  if (!benchFileOk && !skipWrites) {
    // Built in short open/write/close bursts rather than one sustained open. A long
    // single-open write reproducibly panics inside FatFs on this board -- on both cards
    // tested and at both 4 and 20 MHz -- while bursts complete cleanly (see tasks.md
    // TASK-408). The fixture is only a means to measure reads, so it is not worth
    // blocking the read benchmark on an unrelated write-path defect.
    static uint8_t wbuf[512];
    memset(wbuf, 0xA5, sizeof(wbuf));
    const int kBurstChunks = 64;
    size_t written = 0;
    bool writeOk = true;
    while (written < benchFileSize && writeOk) {
      File f = SD.open(kBenchPath, written == 0 ? FILE_WRITE : FILE_APPEND);
      if (!f) { writeOk = false; break; }
      for (int c = 0; c < kBurstChunks && written < benchFileSize; c++) {
        if (f.write(wbuf, sizeof(wbuf)) != sizeof(wbuf)) { writeOk = false; break; }
        written += sizeof(wbuf);
        esp_task_wdt_reset();
      }
      f.close();
      esp_task_wdt_reset();
    }
    if (writeOk) {
      File chk = SD.open(kBenchPath, FILE_READ);
      if (chk) {
        benchActualSize = chk.size();
        benchFileOk = (benchActualSize >= kBenchFileMin);
        chk.close();
      }
    }
    Serial.printf("{\"probe\":\"sdphase\",\"phase\":\"bench-create\",\"writtenB\":%u,"
                  "\"ok\":%s}\n", (unsigned)written, benchFileOk ? "true" : "false");
  }

  // Latency distribution as a fixed bucket histogram rather than an array of every
  // sample: at the default 5 000 reads a uint32_t[] is a 20 KB contiguous internal
  // allocation, which is exactly the class of allocation that cannot be served on a
  // live heap here (see cmdSdMem). Percentiles are reported as the containing
  // bucket's upper edge; `maxUs` stays exact, which is what the <=50 ms bar needs.
  static const uint32_t kBucketEdgeUs[] = {
    250, 500, 1000, 2000, 4000, 8000, 16000, 32000, 50000, 100000, 0xFFFFFFFFu
  };
  const int kNumBuckets = (int)(sizeof(kBucketEdgeUs) / sizeof(kBucketEdgeUs[0]));
  uint32_t buckets[kNumBuckets];
  memset(buckets, 0, sizeof(buckets));
  uint32_t maxUsExact = 0;

  Serial.printf("{\"probe\":\"sdphase\",\"phase\":\"bench-read\",\"fileOk\":%s,"
                "\"benchFileB\":%u}\n",
                benchFileOk ? "true" : "false", (unsigned)benchActualSize);
  esp_task_wdt_reset();
  size_t bytesRead = 0;
  unsigned long benchElapsedUs = 0;
  int actualReads = 0;
  if (benchFileOk) {
    File f = SD.open(kBenchPath, FILE_READ);
    if (f) {
      static uint8_t rbuf[512];
      unsigned long benchStartUs = micros();
      for (int i = 0; i < reads; i++) {
        unsigned long t0 = micros();
        size_t n = f.read(rbuf, kChunk);
        if (n == 0) {
          // Same latched-stream-error recovery as cmdSdRead: a failed physical read
          // sets the stdio error flag, seek() does not clear it, and every later read
          // then returns 0 instantly — which ends the measurement early and reports a
          // throughput far below what the card sustains. Reopen and resume.
          size_t resumeAt = (size_t)f.position();
          f.close();
          f = SD.open(kBenchPath, FILE_READ);
          if (!f) break;
          if (resumeAt + kChunk < benchActualSize) f.seek(resumeAt); else f.seek(0);
          t0 = micros();
          n = f.read(rbuf, kChunk);
        }
        unsigned long t1 = micros();
        uint32_t dtUs = (uint32_t)(t1 - t0);
        if (dtUs > maxUsExact) maxUsExact = dtUs;
        for (int b = 0; b < kNumBuckets; b++) {
          if (dtUs <= kBucketEdgeUs[b]) { buckets[b]++; break; }
        }
        actualReads++;
        bytesRead += n;
        // Outside the timed sample window (t0/t1 bracket the read alone), so
        // this does not perturb the latency histogram.
        if ((i % 50) == 0) esp_task_wdt_reset();
      }
      benchElapsedUs = micros() - benchStartUs;
      f.close();
    }
  }

  float throughputKBps = benchElapsedUs > 0
    ? ((float)bytesRead / 1024.0f) / ((float)benchElapsedUs / 1000000.0f)
    : 0.0f;

  uint32_t p50Us = 0, p99Us = 0, maxUs = maxUsExact;
  if (actualReads > 0) {
    uint32_t need50 = (uint32_t)((actualReads * 50 + 99) / 100);
    uint32_t need99 = (uint32_t)((actualReads * 99 + 99) / 100);
    uint32_t cum = 0;
    for (int b = 0; b < kNumBuckets; b++) {
      cum += buckets[b];
      if (!p50Us && cum >= need50) p50Us = kBucketEdgeUs[b];
      if (!p99Us && cum >= need99) { p99Us = kBucketEdgeUs[b]; break; }
    }
    // Never report a bucket edge above the exact worst sample.
    if (p50Us > maxUsExact) p50Us = maxUsExact;
    if (p99Us > maxUsExact) p99Us = maxUsExact;
  }

  {
    char histo[192];
    int off = 0;
    for (int b = 0; b < kNumBuckets && off < (int)sizeof(histo) - 12; b++) {
      off += snprintf(histo + off, sizeof(histo) - off, "%s%lu",
                      b ? "," : "", (unsigned long)buckets[b]);
    }
    Serial.printf("{\"probe\":\"sdhisto\",\"edgesUs\":\"250,500,1k,2k,4k,8k,16k,32k,50k,100k,inf\","
                  "\"counts\":[%s]}\n", histo);
  }

  Serial.printf(
    "{\"ok\":true,\"cmd\":\"sdprobe\","
    "\"cardType\":\"%s\",\"cardSizeMB\":%llu,\"totalMB\":%llu,\"usedMB\":%llu,"
    "\"heapDeltaB\":%ld,\"freeIntBefore\":%u,\"freeIntAfter\":%u,"
    "\"lfbIntBefore\":%u,\"lfbIntAfter\":%u,"
    "\"lfnOk\":%s,"
    "\"listFiles\":%d,\"listElapsedMs\":%lu,"
    "\"benchReads\":%d,\"benchBytes\":%u,\"benchElapsedMs\":%lu,\"throughputKBps\":%.1f,"
    "\"p50Ms\":%.2f,\"p99Ms\":%.2f,\"maxMs\":%.2f}\n",
    sdCardTypeName(cardType), (unsigned long long)cardSizeMB,
    (unsigned long long)totalMB, (unsigned long long)usedMB,
    heapDeltaB, (unsigned)freeIntBefore, (unsigned)freeIntAfter,
    (unsigned)lfbIntBefore, (unsigned)lfbIntAfter,
    lfnOk ? "true" : "false",
    listCount, listElapsedMs,
    actualReads, (unsigned)bytesRead, (unsigned long)(benchElapsedUs / 1000), throughputKBps,
    p50Us / 1000.0f, p99Us / 1000.0f, maxUs / 1000.0f);
}

static void cmdReboot(const char *) {
  Serial.println("{\"ok\":true,\"cmd\":\"reboot\"}");
  Serial.flush();
  delay(50);
  ESP.restart();
}

static void cmdHelp(const char *) {
  // Single JSON line — iterate kCmds[]; table is the single source of truth.
  Serial.print("{\"ok\":true,\"cmd\":\"help\",\"commands\":[");
  for (int i = 0; i < kNumCmds; ++i) {
    if (i > 0) Serial.print(",");
    Serial.printf("{\"name\":\"%s\",\"args\":\"%s\",\"desc\":\"%s\"}",
                  kCmds[i].name, kCmds[i].args, kCmds[i].help);
  }
  Serial.println("]}");
}

#endif // SERIAL_DEBUG

void loop()
{
  unsigned long _loopStart = millis();

  drainInjectionQueue();   // serialdbg-001: pops one injection step per iter (TASK-056e)
  aeDrainEof();            // TASK-410: audio_eof_mp3 flag, loopTask-only (ADR-059 D12)
  handleSerialCommands();
  logsink::serverLoop();
  heartbeat::tick();
#ifdef SERIAL_DEBUG
  wifiDiag::poll();        // TASK-282: drain queued [beacon] gap lines
#endif
  // TASK-283: link supervisor — re-kick a wedged link (all builds). Suppressed
  // while Settings is foreground: WifiSection's scan flow owns the radio and
  // deliberately runs with auto-reconnect off.
  if (currentAppId != AppId::Settings) wifiDiag::superviseTick();
#ifdef WINAMP_DISPLAY
  // M-BOOT-UI §6 (TASK-364, ADR-055 decision 5): whole-session background
  // WiFi-reconnect status on the title marquee. Self-contained edge-trigger
  // (deliberately not wifiDiag::superviseTick()'s lastDiscMs anchor — a
  // fresh local anchor sidesteps that staleness class of bug for free, per
  // design doc §6 Q3). Co-located with, and gated by the exact same
  // condition as, superviseTick() above (X042, load-bearing per §6 Q4):
  // Settings already owns and repaints this whole screen region, so an
  // ungated override would blit stray marquee text over the Settings UI.
  if (currentAppId != AppId::Settings) {
    static uint32_t s_wifiDownSinceMs = 0;
    // OQ5: proposed starting point, not DUT-pinned — VE/DUT to tune, a
    // single adjustable constant.
    constexpr uint32_t WIFI_DOWN_MARQUEE_THRESHOLD_MS = 10000;
    if (WiFi.status() != WL_CONNECTED) {
      if (s_wifiDownSinceMs == 0) {
        s_wifiDownSinceMs = millis();
      } else if (millis() - s_wifiDownSinceMs >= WIFI_DOWN_MARQUEE_THRESHOLD_MS) {
        winampDisplay.showWifiDownOverride();
      }
    } else if (s_wifiDownSinceMs != 0) {
      s_wifiDownSinceMs = 0;
      winampDisplay.clearWifiDownOverride();
    }
  }
#endif
  esp_task_wdt_reset();   // WDT safety: reset after serial+logsink, before appTick
#ifdef SCREEN_LOG
  { unsigned long _t = millis(); screenlog::tick(spotifyDisplay);
    perf::record("screenlog.tick", millis() - _t); }
#endif

#ifdef SPIKE_MODE
  spike::loop();
#endif

  { unsigned long _t = millis(); appHandleInput(currentAppId);
    perf::record("display.input", millis() - _t); }
  esp_task_wdt_reset();   // WDT safety before appTick

  { unsigned long _t = millis(); appTick(currentAppId);
    perf::record("app.tick", millis() - _t); }

  // Primary busy clear: app reports work done (TASK-115d).
  if (g_shellBusy && g_apps[(int)currentAppId] &&
      !g_apps[(int)currentAppId]->hasPendingAsync())
      shell::setBusy(false);
  // Fallback: auto-clear after timeout (safety net).
  if (g_shellBusy && millis() - g_shellBusySetMs > SHELL_BUSY_TIMEOUT_MS)
      shell::setBusy(false);

  // TASK-245 / ADR-046: repaint the active-slot indicator when the active app's
  // error OR connecting state changes asynchronously (e.g. a Spotify 403 arriving
  // between taps, or the first poll resolving boot amber → green). Edge-triggered
  // to avoid per-frame redraws; precedence error > busy/connecting > idle is
  // resolved inside renderActiveIndicator.
  {
    static bool  s_errShown  = false;
    static bool  s_connShown = false;
    static AppId s_errApp    = AppId::COUNT;
    bool err  = shell::activeError();
    bool conn = shell::activeConnecting();
    if (err != s_errShown || conn != s_connShown || currentAppId != s_errApp) {
      s_errShown  = err;
      s_connShown = conn;
      s_errApp    = currentAppId;
      renderActiveIndicator(tft, currentAppId, winampDisplay.tbScrollOffset(),
                            TASKBAR_APP_COUNT, g_shellBusy, err, conn);
    }
  }

  unsigned long _loopMs = millis() - _loopStart;
  perf::recordLoop(_loopMs);
  if (_loopMs > 50) {
    LOG_W("perf", "iter=%lums (worst path so far: %s:%ums)",
          _loopMs, perf::worstPathName(), (unsigned)perf::worstPathMs());
  }
}
