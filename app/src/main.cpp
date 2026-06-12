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

#include <FS.h>
#include "SPIFFS.h"
#include <time.h>     // configTime(), time(); needed for NTP sync at boot (time-001)
#include <esp_ota_ops.h>  // esp_ota_get_app_description() for serialdbg-001 boot banner (Arduino-ESP32 2.0.x; esp-idf 5.x renames this to <esp_app_desc.h>)
#include <esp_log.h>      // esp_log_level_set() for ADR-042 E1 HTTPClient log suppression

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

#include "serialPrint.h"


#include "httpsDate.h"

#include "logSink.h"
#include "logServer.h"
#include "logHeartbeat.h"
#include "perf.h"
#include "spotifyTask.h"
#ifdef SCREEN_LOG
#include "screenLog.h"
#endif
#ifdef WINAMP_DISPLAY
#include "winamp/vuMeter.h"
#endif
#include "util/mathUtil.h"

// ----------------------------
// App shell
// ----------------------------
#include "appShell.h"
#include "taskbar/taskbar.h"
#include "dataTask.h"
#include "settingsStorage.h"

AppId currentAppId = AppId::Spotify;
static AppId g_previousAppId = AppId::Spotify;

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
    return winampDisplay.handleWinampInput(phase, x, y);
  }
};
static SpotifyApp g_SpotifyApp;
#endif // WINAMP_DISPLAY

// ── ClockApp (TASK-090e) ───────────────────────────────────────────────
class ClockApp : public App {
public:
  void init()    override { repaint(); }
  void resume()  override { repaint(); }
  void suspend() override { tft.setTextDatum(TL_DATUM); }
  void tick() override {
    if (millis() - s_lastTickMs < 1000) return;
    s_lastTickMs = millis();
    drawTime();
    drawSecondsBar();
    drawDate();
    drawRssi();
  }
  bool handleInput(TouchPhase, int, int) override { return false; }
private:
  unsigned long s_lastTickMs = 0;
  void repaint() {
    tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
    tft.drawRoundRect(5,   5, 265,  80, 10, 0xF81F);
    tft.drawRoundRect(5,  88, 265,  47, 10, 0x07FF);
    tft.drawRoundRect(5, 138, 265,  97, 10, 0xFFE0);
    s_lastTickMs = 0;
    tick();
  }
  void drawTime() {
    struct tm t;
    if (!getLocalTime(&t)) return;
    char tBuf[16];
    if (t.tm_sec % 2 == 0) snprintf(tBuf, sizeof(tBuf), "%02d:%02d", t.tm_hour, t.tm_min);
    else                    snprintf(tBuf, sizeof(tBuf), "%02d %02d", t.tm_hour, t.tm_min);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString(tBuf, 137, 45, 6);
    tft.setTextDatum(TL_DATUM);
  }
  void drawSecondsBar() {
    struct tm t;
    if (!getLocalTime(&t)) return;
    for (int i = 0; i < 60; ++i) {
      uint16_t c = (i < t.tm_sec) ? tft.color565(
          (int)(sinf((float)i / 60.0f * TWO_PI)                   * 127 + 128),
          (int)(sinf((float)i / 60.0f * TWO_PI + TWO_PI / 3.0f)  * 127 + 128),
          (int)(sinf((float)i / 60.0f * TWO_PI + 2*TWO_PI / 3.0f)* 127 + 128)
      ) : (uint16_t)0x07FF;
      tft.fillRect(8 + (int)((float)i * 4.3f), 100, 2, 25, c);
    }
  }
  void drawDate() {
    struct tm t;
    if (!getLocalTime(&t)) return;
    const char* days[] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString(days[t.tm_wday], 137, 170, 4);
    char dBuf[16];
    snprintf(dBuf, sizeof(dBuf), "%02d/%02d/%04d", t.tm_mday, t.tm_mon + 1, t.tm_year + 1900);
    tft.drawString(dBuf, 137, 200, 4);
    tft.setTextDatum(TL_DATUM);
  }
  void drawRssi() {
    int rssi = WiFi.RSSI();
    int bars = (rssi > -55) ? 4 : (rssi > -65) ? 3 : (rssi > -75) ? 2 : 1;
    for (int i = 0; i < 4; ++i) {
      uint16_t c = (i < bars) ? TFT_GREEN : (uint16_t)0x4208;
      tft.fillRect(240 + i * 7, 228 - (i + 1) * 5, 5, (i + 1) * 5, c);
    }
  }
};
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
    dataTask::enqueue(dataTask::DATA_FETCH_WEATHER);
    _s.lastDataFetch = millis();
  }
  void resume()  override { repaintWeather(); }
  void suspend() override {}
  void tick()    override { weatherTick(); }
  bool handleInput(TouchPhase, int, int) override { return false; }

private:
  WeatherAppState _s   = {};
  int             _lsec = -1;

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
    char tS[6]; strftime(tS, 6, "%H:%M", &ti);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(0xF81F, TFT_BLACK);
    tft.drawString(tS, WX_LEFT_CX, WX_TOP_CY, 4);
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
      dataTask::enqueue(dataTask::DATA_FETCH_WEATHER);
      _s.lastDataFetch = millis();
    }
    dataTask::WeatherResult r;
    if (dataTask::pollWeather(&r)) {
      _s.cTemp = r.cTemp; _s.cHum = r.cHum; _s.cWind = r.cWind;
      _s.lastDataFetch = millis();
      s_wxDataReady = true;
      repaintWeatherValues();
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

private:
  CryptoAppState _s = {};

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
    if (dataTask::pollCrypto(&r) && r.ok) {
      for (int i = 0; i < CRYPTO_COIN_COUNT; i++) {
        _s.prices[i]  = r.prices[i];
        _s.changes[i] = r.changes[i];
      }
      _s.lastCryptoFetch = now;
      s_cxDataReady = true;
      repaintCrypto();
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
      _activeSection->tick();
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
    if (_sections[idx]) {
      _activeSection = _sections[idx];
      _activeSection->enter();
    } else {
      _repaintStub();
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

  void _repaintStub() {
    static const char* kLabels[SETTINGS_CAT_COUNT] = {
      "WiFi", "Time & Location", "Touch Calibration",
      "Display", "LED", "Applications"
    };
    repaintHeader(kLabels[_s.section]);
    tft.fillRect(0, SETTINGS_CONTENT_Y, 275, SETTINGS_CONTENT_H, SETTINGS_BG_RGB565);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(SETTINGS_SEP_COLOR);
    tft.drawString("(not implemented)", 137, 120, 2);
    tft.setTextDatum(TL_DATUM);
  }
};
static SettingsApp g_SettingsApp;
LedFlow      g_ledFlow;
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
public:
  bool hasPendingAsync() const override { return _pendingAsync; }
  void init() override {
    for (int i = 0; i < 8; i++)
      strlcpy(_s.tickers[i], g_settings.stockTickers[i], 8);
    dataTask::configureStockTickers(
        const_cast<const char(*)[8]>(g_settings.stockTickers));
    _s.subView     = StockSubView::List;
    _s.prevSubView = StockSubView::List;
    repaintList();
    dataTask::enqueue(dataTask::DATA_FETCH_STOCK_QUOTE);
    _s.lastQuoteFetch = millis();
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
    switch (_s.subView) {
      case StockSubView::List:          repaintList();    break;
      case StockSubView::ChartDetail:   repaintChart();   break;
      case StockSubView::HeatmapDetail: repaintHeatmap(); break;
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
    if (strcmp(var, "fetchErrorCode") == 0) {
      _s.fetchErrorCode = val ? atoi(val) : 0;
      return true;
    }
    if (strcmp(var, "triggerFetch") == 0 && val && strcmp(val, "1") == 0) {
      _s.lastQuoteFetch = 0;
      _s.lastChartFetch = 0;
      _s.chartLen       = 0;
      _s.fetchFailed    = false;
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
      } else if (!_s.heatmapData.ok) {
        // No good data yet — propagate error so screen shows it
        _s.heatmapData        = r;
        _s.heatmapLayoutDirty = true;
      }
      // else: keep last good data on screen; transient fetch error is silently retried
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
      _pendingAsync = false;
      if (r.ok) {
        memcpy(_s.chartPoints, r.points, r.len * sizeof(float));
        _s.chartLen       = r.len;
        _s.chartLo        = r.lo;
        _s.chartHi        = r.hi;
        _s.fetchFailed    = false;
        _s.fetchErrorCode = 0;
        _s.fetchOkCount++;
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

#ifdef SERIAL_DEBUG
static bool matrixDbgGet(const char* v, char* b, int l)   { return g_MatrixApp.dbgGet(v, b, l); }
static bool lifeDbgGet(const char* v, char* b, int l)     { return g_LifeApp.dbgGet(v, b, l); }
static bool cryptoDbgGet(const char* v, char* b, int l)   { return g_CryptoApp.dbgGet(v, b, l); }
static bool aquariumDbgGet(const char* v, char* b, int l) { return g_AquariumApp.dbgGet(v, b, l); }
#endif

// ── App registry + shell gesture state (TASK-090f) ────────────────────

#ifdef WINAMP_DISPLAY
App* g_apps[(int)AppId::COUNT] = {
#define APP_X(Name, icon, cfg) &g_##Name##App,
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
// Sets busy flag and immediately repaints only the active-slot indicator.
void setBusy(bool busy) {
    g_shellBusy = busy;
    if (busy) g_shellBusySetMs = millis();
    renderActiveIndicator(tft, currentAppId,
                          winampDisplay.tbScrollOffset(), (int)AppId::COUNT, busy);
}
}

void switchApp(AppId next) {
  if (next == currentAppId) return;
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] leaving %d  heap=%lu maxAlloc=%lu minFree=%lu\n",
    (int)currentAppId,
    (unsigned long)ESP.getFreeHeap(),
    (unsigned long)ESP.getMaxAllocHeap(),
    (unsigned long)ESP.getMinFreeHeap());
#endif
  if (g_apps[(int)currentAppId]) g_apps[(int)currentAppId]->suspend();
  shell::setBusy(false);   // clear before new taskbar paint (TASK-115e)
  tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
  if (next == AppId::Settings) g_previousAppId = currentAppId;
  currentAppId = next;
  if (g_apps[(int)next]) {
    if (!g_appLaunched[(int)next]) {
      g_appLaunched[(int)next] = true;
      g_apps[(int)next]->init();
    } else {
      g_apps[(int)next]->resume();
    }
  }
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] entered %d  heap=%lu maxAlloc=%lu minFree=%lu\n",
    (int)next,
    (unsigned long)ESP.getFreeHeap(),
    (unsigned long)ESP.getMaxAllocHeap(),
    (unsigned long)ESP.getMinFreeHeap());
#endif
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), (int)AppId::COUNT);
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
        if (winampDisplay.tbGestureContinue(p.y, (int)AppId::COUNT))
          renderTaskbar(tft, currentAppId,
                        winampDisplay.tbScrollOffset(), (int)AppId::COUNT);
      } else {
        winampDisplay.tbGesturePress(p.y);
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
      int appIdx = (int)currentAppId;
      if (winampDisplay.tbGestureEnd(s_lastTouchY, (int)AppId::COUNT, &appIdx))
        if (appIdx != (int)currentAppId) switchApp(static_cast<AppId>(appIdx));
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
  g_keyboard.tick();
  if (g_apps[(int)id]) g_apps[(int)id]->tick();
}

void setup()
{
  Serial.begin(115200);

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
  {
    int duty = map(constrain((int)g_settings.dispLevel, 1, 10), 1, 10, 25, 255);
    ledcWrite(0, (uint32_t)duty);   // apply stored brightness before first frame
  }
  // RGB LED channels (ch1=R/GPIO4, ch2=G/GPIO16, ch3=B/GPIO17).
  ledcSetup(LED_R_CH, 5000, 8); ledcAttachPin(LED_R_PIN, LED_R_CH);
#if !NFC_ENABLED
  ledcSetup(LED_G_CH, 5000, 8); ledcAttachPin(LED_G_PIN, LED_G_CH);
#endif
  ledcSetup(LED_B_CH, 5000, 8); ledcAttachPin(LED_B_PIN, LED_B_CH);
  g_ledFlow.applyMode();

  refreshToken[0] = '\0';
  fetchConfigFile(refreshToken, clientId, clientSecret);

  // WiFi boot: NVS credentials → SPIFFS wifi_creds.json → open WiFi settings.
  // Priority chain mirrors WifiSection connect flow (C4: NVS-backed persist).
  bool wifiConnected = false;
#ifdef HARDCODED_WIFI_SSID
  WiFi.persistent(true);
  WiFi.mode(WIFI_STA);
  WiFi.begin(HARDCODED_WIFI_SSID, HARDCODED_WIFI_PASS);
  Serial.print("Connecting to hardcoded SSID " HARDCODED_WIFI_SSID);
  { unsigned long dl = millis() + 30000;
    while (WiFi.status() != WL_CONNECTED && millis() < dl) { delay(250); Serial.print("."); }
    Serial.println(); }
  wifiConnected = (WiFi.status() == WL_CONNECTED);
  if (!wifiConnected) Serial.println("[wifi] hardcoded connect failed, trying NVS");
#endif
  if (!wifiConnected) {
    WiFi.persistent(true);
    WiFi.mode(WIFI_STA);
    WiFi.begin();  // reconnect from NVS (no args)
    { unsigned long dl = millis() + 10000;
      while (WiFi.status() != WL_CONNECTED && millis() < dl) delay(100); }
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
          Serial.printf("[wifi] Connecting from SPIFFS: %s\n", ssid);
          WiFi.persistent(false);  // don't corrupt NVS if creds are wrong (TASK-167)
          WiFi.mode(WIFI_STA);
          WiFi.begin(ssid, pass);
          { unsigned long dl = millis() + 30000;
            while (WiFi.status() != WL_CONNECTED && millis() < dl) { delay(250); Serial.print("."); }
            Serial.println(); }
          wifiConnected = (WiFi.status() == WL_CONNECTED);
          if (wifiConnected) {
            WiFi.persistent(true);
            WiFi.begin(ssid, pass);  // persist verified creds to NVS
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
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    // Leave WiFi in a clean disconnected STA state so WifiSection scan works.
    // WiFi.begin() (NVS attempt above) leaves auto-reconnect armed; disable it
    // so the subsequent scanNetworks() call is not blocked by a reconnect loop.
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false);
    Serial.println("[wifi] no credentials — will open WiFi settings after init");
  }



  // time-001: SNTP sync before any TLS. ESP32 has no RTC; without this the
  // clock starts ~1970 and mbedTLS rejects current Spotify certs (notBefore
  // in the future), surfacing as a generic "send_ssl_data 0x0050" failure.
  // 5 s bounded wait, non-fatal on timeout.
  configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
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
  spotifyTask::begin(&spotify);
  dataTask::begin();

  // Boot: init the Spotify app via the App interface, then draw taskbar.
  if (g_apps[(int)AppId::Spotify]) {
    g_appLaunched[(int)AppId::Spotify] = true;
    g_apps[(int)AppId::Spotify]->init();
  } else {
    spotifyDisplay->showDefaultScreen();
  }
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), (int)AppId::COUNT);
  if (!wifiConnected) {
    switchApp(AppId::Settings);
    g_SettingsApp.openSection(0);
  }
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

// Forward declarations so kCmds[] can reference the handlers before they
// are defined (they must appear after kCmds[] to see kNumCmds).
static void cmdTap(const char *);
static void cmdDrag(const char *);
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
  { "drag", cmdDrag, "inject touch drag (queue-drain)", "<x1> <y1> <x2> <y2> <steps>"        },
  { "tick", cmdTick, "inject synthetic scroll ticks",   "[n=1] [dtMs=20]"                    },
  { "get",  cmdGet,  "read internal state",             "<snapshot|backoff|heap|cooldown>"    },
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
      // Taskbar drag release: end gesture (scroll path — y unused for non-tap).
      int appIdx = (int)currentAppId;
      if (winampDisplay.tbGestureEnd(s_lastTouchY, (int)AppId::COUNT, &appIdx))
        if (appIdx != (int)currentAppId) switchApp(static_cast<AppId>(appIdx));
      renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), (int)AppId::COUNT);
    } else {
      winampDisplay.handleWinampInput(TouchPhase::Release, 0, 0);
    }
    winampDisplay._injectingDrag = false;
    s_dragPending = false;
    Serial.printf("{\"ok\":true,\"cmd\":\"drag\","
                  "\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                  s_pendingDragX1, s_pendingDragY1,
                  s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps);
  } else {
    LOG_D("serial", "inject sample %d/%d sx=%d sy=%d",
          s_injectHead + 1, s_injectTotal - 1, step.sx, step.sy);
    if (step.sx >= TASKBAR_X) {
      // Taskbar zone: route to gesture handlers, not handleWinampInput.
      s_lastTouchY = step.sy;
      if (!winampDisplay.tbIsDragging()) {
        winampDisplay.tbGesturePress(step.sy);
      } else {
        if (winampDisplay.tbGestureContinue(step.sy, (int)AppId::COUNT))
          renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), (int)AppId::COUNT);
      }
    } else if (s_injectIsFirst) {
      winampDisplay.handleWinampInput(TouchPhase::Press, step.sx, step.sy);
      s_injectIsFirst = false;
    } else {
      winampDisplay.handleWinampInput(TouchPhase::Move, step.sx, step.sy);
    }
  }
#else
  (void)step;
#endif
  ++s_injectHead;
#endif
}

static void handleSerialCommands() {
  static char buf[64];
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
    int appIdx = (winampDisplay.tbScrollOffset() + slot) % (int)AppId::COUNT;
    switchApp(static_cast<AppId>(appIdx));
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
    } else {
      winampDisplay.lastTouchResult = { "CLOCK", -1, "NONE", 0, -1, false };
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"CLOCK\",\"action\":\"NONE\",\"skipped\":false}\n", x, y);
    }
    return;
  }
  winampDisplay.injectTouch(x, y);
  winampDisplay.injectRelease();
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
  if (sscanf(args, "%d %d %d %d %d", &x1, &y1, &x2, &y2, &steps) != 5
      || steps < 1 || steps > 62) {
    Serial.println("{\"ok\":false,\"cmd\":\"drag\","
                   "\"error\":\"bad args — drag <x1> <y1> <x2> <y2> <steps=1..62>\"}");
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
  s_injectQueue[s_injectTail++ % 64] = { 0, 0, true };  // release sentinel
  s_pendingDragX1 = x1; s_pendingDragY1 = y1;
  s_pendingDragX2 = x2; s_pendingDragY2 = y2;
  s_pendingDragSteps = steps;
  s_injectTotal = s_injectTail;
  s_dragPending = true;
  // JSON response emitted by drainInjectionQueue() when release step pops.
}

static void cmdTick(const char *args) {
  int n = 1, dtMs = 20;
  sscanf(args, "%d %d", &n, &dtMs);
  if (n < 1)    n    = 1;
  if (dtMs < 1) dtMs = 20;
#ifdef WINAMP_DISPLAY
  for (int i = 0; i < n; ++i)
    winampDisplay.tickScroll(dtMs * 0.001f);
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
  // appId — shell-owned; WinampDisplay cannot reference currentAppId.
  if (strcmp(args, "appId") == 0) {
#define APP_X(Name, icon, cfg) #Name,
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
  Serial.printf("{\"ok\":false,\"cmd\":\"get\","
                "\"error\":\"unknown var\",\"var\":\"%s\"}\n", args);
}

static void cmdSet(const char *args) {
  char var[32], val[32];
  if (sscanf(args, "%31s %31s", var, val) != 2) {
    Serial.println("{\"ok\":false,\"cmd\":\"set\",\"error\":\"bad args\"}");
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
#ifdef SCREEN_LOG
  { unsigned long _t = millis(); screenlog::tick(spotifyDisplay);
    perf::record("screenlog.tick", millis() - _t); }
#endif

#ifdef SPIKE_MODE
  spike::loop();
#endif

  { unsigned long _t = millis(); appHandleInput(currentAppId);
    perf::record("display.input", millis() - _t); }

  { unsigned long _t = millis(); appTick(currentAppId);
    perf::record("app.tick", millis() - _t); }

  // Primary busy clear: app reports work done (TASK-115d).
  if (g_shellBusy && g_apps[(int)currentAppId] &&
      !g_apps[(int)currentAppId]->hasPendingAsync())
      shell::setBusy(false);
  // Fallback: auto-clear after timeout (safety net).
  if (g_shellBusy && millis() - g_shellBusySetMs > SHELL_BUSY_TIMEOUT_MS)
      shell::setBusy(false);

  unsigned long _loopMs = millis() - _loopStart;
  perf::recordLoop(_loopMs);
  if (_loopMs > 50) {
    LOG_W("perf", "iter=%lums (worst path so far: %s:%ums)",
          _loopMs, perf::worstPathName(), (unsigned)perf::worstPathMs());
  }
}
