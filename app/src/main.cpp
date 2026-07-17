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

#include <FS.h>
#include "SPIFFS.h"
#include <time.h>     // configTime(), time(); needed for NTP sync at boot (time-001)
#include <esp_ota_ops.h>  // esp_ota_get_app_description() for serialdbg-001 boot banner (Arduino-ESP32 2.0.x; esp-idf 5.x renames this to <esp_app_desc.h>)
#include <esp_log.h>      // esp_log_level_set() for ADR-042 E1 HTTPClient log suppression
#include <esp_task_wdt.h> // esp_task_wdt_init() — extended timeout for dataTask TLS
#include <esp_heap_caps.h> // T_MB_PROBE_00: caps-split heap probes (TASK-261 Phase 0)

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
// TASK-259/260: the "player" is one slot with two modes {Spotify | WebRadio}. Eject
// toggles the mode; returning to the player from the taskbar restores the last-active
// one instead of always landing on Spotify. The mode is the persisted single source of
// truth g_settings.playerMode (TASK-260) — written by the eject toggles + Settings UI,
// read by resolvePlayerSlot. v2 boot (OQ-BOOT): cold-boot enters the persisted mode (see
// the boot-into-mode redirect at the end of setup()); auto-play is the webRadioAutoplay knob.

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
  bool hasError() const override {
    return spotifyTask::authError();
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
    vu::tick(winampDisplay.chromeOriginX(), winampDisplay.chromeOriginY(), SKIN_MAIN_BG);
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
    // M-WEBRADIO: eject button → switch to WebRadio (intercept before winampDisplay).
    if (phase == TouchPhase::Release && winampDisplay.hitTestEject(x, y)) {
        persistPlayerMode((uint8_t)PlayerMode::WebRadio);   // TASK-260
        switchApp(AppId::WebRadio);
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
    tft.setTextColor(0xF81F); tft.drawString("TIME",     WX_LEFT_CX,  8,   2);
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
#define SETTINGS_CAT_COUNT         6
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

class SettingsApp : public App {
public:
  void init() override {
    _sections[0] = &_wifi;
    _sections[1] = &_time;
    _sections[2] = &_cal;
    _sections[3] = &_disp;
    _sections[4] = &_led;
    _sections[5] = &_apps;
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
    return false;
  }
#endif

private:
  struct State { int8_t section = -1; } _s;

  WifiSection        _wifi;
  TimeSection        _time;
  CalibrationFlow    _cal;
  DisplaySection     _disp;
  AppsSection        _apps;
  LedSection         _led;
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
    // All SETTINGS_CAT_COUNT sections are wired in the ctor (_sections[0..5]),
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
      "Display", "LED", "Applications"
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
    if (!_s.lastChartFetch || millis() - _s.lastChartFetch > STOCK_CHART_FETCH_D1) {
      dataTask::enqueueStockChart(tickerIdx, (uint8_t)StockRange::D1);
      _s.lastChartFetch = millis();
      _pendingAsync     = true;
    }
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
          tft.setViewport(t.x, t.y, t.w, t.h);
          tft.setPivot(cx, cy);
          spr.pushRotated(-90, col);
          tft.resetViewport();
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

// TASK-259/260: the taskbar "player" slot (AppId::Spotify) restores whichever player
// mode (Spotify | WebRadio) was last active — read from the persisted setting. WebRadio
// is eject-only / excluded from the taskbar, so a taskbar tap only ever surfaces
// AppId::Spotify here; we redirect to WebRadio when that's the persisted mode.
static AppId resolvePlayerSlot(AppId tapped) {
  if (tapped != AppId::Spotify) return tapped;
  return (g_settings.playerMode == (uint8_t)PlayerMode::WebRadio) ? AppId::WebRadio
                                                                  : AppId::Spotify;
}

// TASK-260 §4: persist the player mode, immediate-save with an unchanged-value skip
// (flash-wear). Called from the eject toggles in both directions (the Settings UI
// writes g_settings.playerMode + saveSettings() directly via its own cycle handler).
void persistPlayerMode(uint8_t mode) {
  if (g_settings.playerMode == mode) return;   // unchanged-value skip
  g_settings.playerMode = mode;
  SettingsStorage::save();
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
    AppId target = resolvePlayerSlot(static_cast<AppId>(appIdx));  // TASK-259
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
    if (!s_inGesture && (millis() <= s_cooldownMs || g_shellBusy)) return;
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

  Serial.begin(115200);

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

  refreshToken[0] = '\0';
  fetchConfigFile(refreshToken, clientId, clientSecret);

  // TASK-274 (M-WIFI-DIAG): link-event ground truth. Must register before the
  // first WiFi.begin() below or early events (incl. the boot-window drop E1)
  // are missed. Ships in all builds — [wifi-ev] is a stable log contract.
  wifiDiag::begin();

  // WiFi boot: NVS credentials → SPIFFS wifi_creds.json → open WiFi settings.
  // Priority chain mirrors WifiSection connect flow (C4: NVS-backed persist).
  // TASK-296: wifiCredsKnown tracks whether ANY source held credentials —
  // "connect failed with stored creds" (AP storm at boot) must not be treated
  // as "no credentials", or the device parks dead in the Settings screen.
  bool wifiConnected  = false;
  bool wifiCredsKnown = false;
#ifdef HARDCODED_WIFI_SSID
  wifiCredsKnown = true;
  WiFi.persistent(true);
  WiFi.mode(WIFI_STA);
  WiFi.begin(HARDCODED_WIFI_SSID, HARDCODED_WIFI_PASS);
  Serial.print("Connecting to hardcoded SSID " HARDCODED_WIFI_SSID);
  { unsigned long dl = millis() + 30000;
    // TASK-288: feed the TWDT every iteration — this loop's own 30s deadline
    // already exceeds the runtime 15s watchdog window on its own, and it can
    // also chain into the NVS/SPIFFS fallback loops below with zero resets
    // in between, so cumulative un-fed time (not any single loop's deadline)
    // is what was tripping task_wdt during a flaky-AP boot.
    while (WiFi.status() != WL_CONNECTED && millis() < dl) { delay(250); Serial.print("."); esp_task_wdt_reset(); }
    Serial.println(); }
  wifiConnected = (WiFi.status() == WL_CONNECTED);
  if (!wifiConnected) Serial.println("[wifi] hardcoded connect failed, trying NVS");
#endif
  if (!wifiConnected) {
    WiFi.persistent(true);
    WiFi.mode(WIFI_STA);
    // TASK-296: driver is up after mode() — a non-empty stored SSID means NVS
    // holds credentials even if the connect window below expires.
    wifi_config_t nvsCfg;
    if (esp_wifi_get_config(WIFI_IF_STA, &nvsCfg) == ESP_OK && nvsCfg.sta.ssid[0] != 0)
      wifiCredsKnown = true;
    WiFi.begin();  // reconnect from NVS (no args)
    { unsigned long dl = millis() + 10000;
      // TASK-288: see hardcoded-SSID loop above — feed TWDT every iteration.
      while (WiFi.status() != WL_CONNECTED && millis() < dl) { delay(100); esp_task_wdt_reset(); } }
    wifiConnected = (WiFi.status() == WL_CONNECTED);
  }
  if (!wifiConnected && SPIFFS.exists("/wifi_creds.json")) {
    File f = SPIFFS.open("/wifi_creds.json", "r");
    if (f) {
      StaticJsonDocument<256> doc;
      if (deserializeJson(doc, f) == DeserializationError::Ok) {
        const char* ssid = doc["ssid"] | "";
        const char* pass = doc["pass"] | "";
        if (strlen(ssid) > 0) {
          wifiCredsKnown = true;  // TASK-296
          Serial.printf("[wifi] Connecting from SPIFFS: %s\n", ssid);
          WiFi.persistent(false);  // don't corrupt NVS if creds are wrong (TASK-167)
          WiFi.mode(WIFI_STA);
          WiFi.begin(ssid, pass);
          { unsigned long dl = millis() + 30000;
            // TASK-288: see hardcoded-SSID loop above — feed TWDT every iteration.
            while (WiFi.status() != WL_CONNECTED && millis() < dl) { delay(250); Serial.print("."); esp_task_wdt_reset(); }
            Serial.println(); }
          wifiConnected = (WiFi.status() == WL_CONNECTED);
          if (wifiConnected) {
            WiFi.persistent(true);
            WiFi.begin(ssid, pass);  // persist verified creds to NVS
            // TASK-290: this re-begin DEAUTHS the just-verified association
            // (observed [wifi-ev] reason=8 ~150ms after GOT_IP) and the code
            // below read localIP() before re-association finished — boot
            // proceeded with "IP address: 0.0.0.0" whenever the NVS attempt
            // missed its window and this SPIFFS path ran. Wait (bounded,
            // TWDT-fed per TASK-288) for the re-association to settle.
            { unsigned long dl = millis() + 15000;
              while (WiFi.status() != WL_CONNECTED && millis() < dl) { delay(100); esp_task_wdt_reset(); } }
            wifiConnected = (WiFi.status() == WL_CONNECTED);
            Serial.println("[wifi] SPIFFS credentials saved to NVS");
          } else {
            Serial.println("[wifi] SPIFFS connect failed");
          }
        }
      }
      f.close();
    }
  }

  if (wifiConnected) {
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
    Serial.println("[wifi] connect failed with stored credentials — reconnect + supervisor armed");
  } else {
    // Leave WiFi in a clean disconnected STA state so WifiSection scan works.
    // WiFi.begin() (NVS attempt above) leaves auto-reconnect armed; disable it
    // so the subsequent scanNetworks() call is not blocked by a reconnect loop.
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false);
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
  configTzTime(g_settings.posixTz, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  unsigned long ntpStart = millis();
  unsigned long ntpDeadline = ntpStart + 5000;
  while (time(nullptr) < 1700000000UL && millis() < ntpDeadline) {
    delay(50);
    yield();
  }
  time_t now = time(nullptr);
  if (now >= 1700000000UL) {
    Serial.printf("[time] synced epoch=%ld in %lums\n", (long)now, millis() - ntpStart);
  } else {
    Serial.printf("[time] NTP sync failed after %lums, trying HTTPS-Date fallback\n",
                  millis() - ntpStart);
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

  spotifyRefreshToken(refreshToken);

  // refreshToken.h flow would have held port 80. Stand up permanent /log server now.
  logsink::serverBegin();

  // ADR-012 / TASK-031a: spawn the async Spotify HTTP task. Skeleton at
  // this stage — task dequeues + logs but doesn't issue API calls yet.
  // 031b/c migrate the actual calls in.
#ifndef DISABLE_SPOTIFY
  spotifyTask::begin(&spotify);
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
  else if (wifiConnected && g_settings.playerMode == (uint8_t)PlayerMode::WebRadio) {
    switchApp(AppId::WebRadio);
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
    // TASK-280: route through the production resolve path — a tap on the player
    // slot must redirect to WebRadio when that's the persisted mode, same as
    // shellTbRelease()/switchApp() do for real taps and injected drags.
    AppId target = resolvePlayerSlot(static_cast<AppId>(appIdx));
    switchApp(target);
    winampDisplay.lastTouchResult = { "TASKBAR", -1, "APP_SWITCH", 0, -1, false };
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"TASKBAR\",\"action\":\"APP_SWITCH\",\"skipped\":false}\n", x, y);
    return;
  }
  if (g_shellBusy) {
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
    } else if (currentAppId == AppId::WebRadio && g_apps[(int)AppId::WebRadio]) {
      // WebRadio: injectTouch populates lastTouchResult for the response;
      // WebRadioApp::handleInput executes the action (eject/transport/PLEDIT).
      winampDisplay.injectTouch(x, y);
      g_apps[(int)AppId::WebRadio]->handleInput(TouchPhase::Release, x, y);
      const auto &wr = winampDisplay.lastTouchResult;
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"%s\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, wr.region, wr.action);
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
  // be called directly to execute switchApp(AppId::WebRadio).
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
  char buf[256]; buf[0] = '\0';
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
                  "\"spotifyAuthError\":%s,\"spotifyConnecting\":%s,\"last\":true}\n",
                  ae ? "true" : "false",
                  ac ? "true" : "false",
                  spotifyTask::authError() ? "true" : "false",
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
           : (m == vu::VIS_WAVE_ATLAS) ? 3 : -1;
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
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"clockStyle\","
                  "\"val\":%d,\"name\":\"%s\",\"last\":true}\n", cs, kSN[cs]);
    return;
  }
  if (strcmp(args, "playerMode") == 0) {   // TASK-260 (VE: agent-driven persist/settings tests)
    uint8_t pm = g_settings.playerMode ? 1 : 0;
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"playerMode\","
                  "\"val\":%d,\"name\":\"%s\",\"last\":true}\n",
                  pm, pm ? "WebRadio" : "Spotify");
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
    Serial.printf("],\"last\":true}\n");
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

  if (sscanf(args, "%31s %127s", var, val) != 2) {
    Serial.println("{\"ok\":false,\"cmd\":\"set\",\"error\":\"bad args\"}");
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
  if (strcmp(var, "playerMode") == 0) {   // TASK-260 (VE: agent-driven persist/boot tests)
    int idx = -1;
    if      (strcasecmp(val, "spotify")  == 0) idx = 0;
    else if (strcasecmp(val, "webradio") == 0) idx = 1;
    else if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 1) idx = -1;
    if (idx < 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                    "\"error\":\"bad val — use 0/1 or spotify/webradio\"}\n");
      return;
    }
    // Pure persist (no app switch): sets + saves the mode so a reboot exercises the v2
    // boot-into-mode path. Use the eject toggle to actually switch the live player slot.
    persistPlayerMode((uint8_t)idx);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"playerMode\",\"val\":%d,\"name\":\"%s\"}\n",
                  idx, idx ? "WebRadio" : "Spotify");
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
