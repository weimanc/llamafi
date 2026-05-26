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
// Library Defines - Need to be defined before library import
// ----------------------------

#define ESP_DRD_USE_SPIFFS true

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

// ----------------------------
// Additional Libraries - each one of these will need to be installed.
// ----------------------------

#include <WiFiManager.h>
// Captive portal for configuring the WiFi

// If installing from the library manager (Search for "WifiManager")
// https://github.com/tzapu/WiFiManager

#include <ESP_DoubleResetDetector.h>
// A library for checking if the reset button has been pressed twice
// Can be used to enable config mode
// Can be installed from the library manager (Search for "ESP_DoubleResetDetector")
// https://github.com/khoih-prog/ESP_DoubleResetDetector

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

#include "spotifyDisplay.h"

#include "spotifyLogic.h"

#include "configFile.h"

#include "serialPrint.h"

#include "WifiManagerHandler.h"

#include "dnsOverride.h"

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

// ----------------------------
// App shell
// ----------------------------
#include "appShell.h"
#include "taskbar/taskbar.h"
#include "dataTask.h"

AppId currentAppId = AppId::Spotify;

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

void drawWifiManagerMessage(WiFiManager *myWiFiManager)
{
  spotifyDisplay->drawWifiManagerMessage(myWiFiManager);
}

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
  void tick() override {
    {
      static unsigned long _lastScrollMs = 0;
      unsigned long now = millis();
      float dt = (_lastScrollMs == 0) ? 0.0f : (now - _lastScrollMs) / 1000.0f;
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
static SpotifyApp g_spotifyApp;
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
static ClockApp g_clockApp;

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
    if (now - _lastTickMs < MATRIX_TICK_MS) return;
    _lastTickMs = now;
    for (int i = 0; i < MATRIX_STREAMS; i++) {
      tft.setTextColor(TFT_WHITE, TFT_BLACK);
      char hC = random(33, 126);
      tft.drawChar(hC, _s.rain[i].x, (int)_s.rain[i].y, 2);
      tft.setTextColor(TFT_GREEN, TFT_BLACK);
      tft.drawChar(_s.rain[i].lastChar, _s.rain[i].x, (int)_s.rain[i].y - 20, 2);
      tft.fillRect(_s.rain[i].x, (int)_s.rain[i].y - (_s.rain[i].length * 20),
                   20, 20, TFT_BLACK);
      _s.rain[i].lastChar = hC;
      _s.rain[i].y += _s.rain[i].speed;
      if (_s.rain[i].y > MATRIX_CANVAS_H + (_s.rain[i].length * 20))
        _s.rain[i].y = -20.0f;
    }
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
  }
};
static MatrixApp g_matrixApp;

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
static WeatherApp g_weatherApp;

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

static const char* CRYPTO_SYMBOLS[CRYPTO_COIN_COUNT] =
    {"BTC","ETH","BNB","SOL","XRP","ADA"};

static String formatCryptoPrice(const char* sym, float price) {
  if (strcmp(sym,"XRP")==0 || strcmp(sym,"ADA")==0) return String(price, 4);
  return (price >= 1000.0f) ? String((int)price) : String(price, 2);
}

class CryptoApp : public App {
public:
  void init() override {
    repaintCrypto();
    dataTask::enqueue(dataTask::DATA_FETCH_CRYPTO);
    _s.lastCryptoFetch = millis();
  }
  void resume()  override { repaintCrypto(); }
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
      tft.drawString(CRYPTO_SYMBOLS[i], CX_COL_SYM, yPos + 11, 2);
      tft.setTextColor(0x07FF);
      tft.drawString(_s.lastCryptoFetch ? formatCryptoPrice(CRYPTO_SYMBOLS[i], _s.prices[i])
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
};
static CryptoApp g_cryptoApp;

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
  static uint8_t s_nextGrid[GOL_GRID_W][GOL_GRID_H];

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
          uint8_t r = (x * 4 + s.hueShift) % 255;
          uint8_t g = (y * 2 + s.hueShift / 2) % 255;
          tft.fillRect(x * GOL_CELL_PX, y * GOL_CELL_PX,
                       GOL_CELL_FILL, GOL_CELL_FILL,
                       tft.color565(r, g, 255 - r));
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
            uint8_t r = (x * 4 + s.hueShift) % 255;
            uint8_t g = (y * 2 + s.hueShift / 2) % 255;
            tft.fillRect(x * GOL_CELL_PX, y * GOL_CELL_PX,
                         GOL_CELL_FILL, GOL_CELL_FILL,
                         tft.color565(r, g, 255 - r));
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
    if (now - _lastTickMs < GOL_TICK_MS) return;
    _lastTickMs = now;
    stepGeneration(_s);
  }
};
uint8_t LifeApp::s_nextGrid[GOL_GRID_W][GOL_GRID_H];
static LifeApp g_lifeApp;

class SettingsApp : public App {
public:
  void init()    override {}
  void resume()  override { _dirty = true; }
  void suspend() override {}
  void tick()    override {
    if (!_dirty) return;
    tft.fillRect(0, 0, TASKBAR_X, 240, TFT_DARKGREY);
    tft.setTextColor(TFT_WHITE, TFT_DARKGREY);
    tft.drawString("SETTINGS", 60, 110, 4);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    _dirty = false;
  }
  bool handleInput(TouchPhase, int, int) override { return false; }
private:
  bool _dirty = false;
};
static SettingsApp g_settingsApp;

class StockApp : public App {
public:
  void init()    override {}
  void resume()  override { _dirty = true; }
  void suspend() override {}
  void tick()    override {
    if (!_dirty) return;
    tft.fillRect(0, 0, TASKBAR_X, 240, TFT_NAVY);
    tft.setTextColor(TFT_WHITE, TFT_NAVY);
    tft.drawString("STOCK", 80, 110, 4);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    _dirty = false;
  }
  bool handleInput(TouchPhase, int, int) override { return false; }
private:
  bool _dirty = false;
};
static StockApp g_stockApp;

#include "aquarium/aquariumApp.h"
static AquariumApp g_aquariumApp;

// ── App registry + shell gesture state (TASK-090f) ────────────────────

#ifdef WINAMP_DISPLAY
App* g_apps[(int)AppId::COUNT] = {
  &g_spotifyApp,    // AppId::Spotify   = 0
  &g_clockApp,      // AppId::Clock     = 1
  &g_weatherApp,    // AppId::Weather   = 2
  &g_cryptoApp,     // AppId::Crypto    = 3
  &g_matrixApp,     // AppId::Matrix    = 4
  &g_lifeApp,       // AppId::Life      = 5
  &g_settingsApp,   // AppId::Settings  = 6
  &g_stockApp,      // AppId::Stock     = 7
  &g_aquariumApp,   // AppId::Aquarium  = 8
};
#else
App* g_apps[(int)AppId::COUNT] = {};
#endif

static bool          s_inGesture  = false;
static int           s_lastTouchX = 0, s_lastTouchY = 0;
static unsigned long s_cooldownMs = 0;

void switchApp(AppId next) {
  if (next == currentAppId) return;
  if (g_apps[(int)currentAppId]) g_apps[(int)currentAppId]->suspend();
  tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
  currentAppId = next;
  if (g_apps[(int)next]) {
    if (!g_appLaunched[(int)next]) {
      g_appLaunched[(int)next] = true;
      g_apps[(int)next]->init();
    } else {
      g_apps[(int)next]->resume();
    }
  }
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
    if (!s_inGesture && millis() <= s_cooldownMs) return;
    s_lastTouchX = p.x; s_lastTouchY = p.y;
    if (!s_inGesture) {
      s_inGesture = true;
      if (g_apps[(int)currentAppId]) {
        bool consumed = g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Press, p.x, p.y);
        if (consumed) s_cooldownMs = millis() + 200;
      }
    } else {
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(TouchPhase::Move, p.x, p.y);
    }
  } else {
    if (winampDisplay.tbIsDragging()) {
      int appIdx = (int)currentAppId;
      if (winampDisplay.tbGestureEnd(s_lastTouchY, (int)AppId::COUNT, &appIdx))
        if (appIdx != (int)currentAppId) switchApp(static_cast<AppId>(appIdx));
      s_cooldownMs = millis() + 300;
    } else if (s_inGesture) {
      s_inGesture = false;
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, s_lastTouchX, s_lastTouchY);
      s_cooldownMs = millis() + 200;
    }
  }
}

void appTick(AppId id) {
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

  logsink::begin();

  bool forceConfig = false;

  drd = new DoubleResetDetector(DRD_TIMEOUT, DRD_ADDRESS);
  if (drd->detectDoubleReset())
  {
    Serial.println(F("Forcing config mode as there was a Double reset detected"));
    forceConfig = true;
  }

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

  // Initialise SPIFFS, if this fails try .begin(true)
  // NOTE: I believe this formats it though it will erase everything on
  // spiffs already! In this example that is not a problem.
  // I have found once I used the true flag once, I could use it
  // without the true flag after that.
  bool spiffsInitSuccess = SPIFFS.begin(false) || SPIFFS.begin(true);
  if (!spiffsInitSuccess)
  {
    Serial.println("SPIFFS initialisation failed!");
    while (1)
      yield(); // Stay here twiddling thumbs waiting
  }
  Serial.println("\r\nInitialisation done.");

  refreshToken[0] = '\0';
  if (!fetchConfigFile(refreshToken, clientId, clientSecret))
  {
    // Failed to fetch config file, need to launch Wifi Manager
    forceConfig = true;
  }

  setupWiFiManager(forceConfig, refreshToken, &saveConfigFile, &drawWifiManagerMessage);

  // If we are here we should be connected to the Wifi
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  // dns-override: optional, no-op if /host_overrides.json is missing.
  // Workaround for upstreams that block DNS for tethered clients.
  dnsOverrideSetup();

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

  // Onboarding (WiFiManager portal + refreshToken.h flow) is done; both
  // would have held port 80. Stand up the permanent /log server now.
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
static void cmdInfo(const char *);
static void cmdHelp(const char *);
#endif

static const SerialCmd kCmds[] = {
  { "reconnect", cmdReconnect, "TLS reset + force poll", "" },
#ifdef SERIAL_DEBUG
  { "tap",  cmdTap,  "inject touch point",              "<x> <y>"                            },
  { "drag", cmdDrag, "inject touch drag (queue-drain)", "<x1> <y1> <x2> <y2> <steps>"        },
  { "tick", cmdTick, "inject synthetic scroll ticks",   "[n=1] [dtMs=20]"                    },
  { "get",  cmdGet,  "read internal state",             "<snapshot|backoff|heap|cooldown>"    },
  { "set",  cmdSet,  "write debug state",               "<backoff|cooldown> <val>"            },
  { "info", cmdInfo, "git+elf+build+snapshot summary",  ""                                   },
  { "help", cmdHelp, "list commands",                   ""                                   },
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
    winampDisplay.handleWinampInput(TouchPhase::Release, 0, 0);
    winampDisplay._injectingDrag = false;
    s_dragPending = false;
    Serial.printf("{\"ok\":true,\"cmd\":\"drag\","
                  "\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                  s_pendingDragX1, s_pendingDragY1,
                  s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps);
  } else {
    LOG_D("serial", "inject sample %d/%d sx=%d sy=%d",
          s_injectHead + 1, s_injectTotal - 1, step.sx, step.sy);
    if (s_injectIsFirst) {
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
  // BUG-1 guard: Winamp hit-zones only valid when Spotify is active.
  if (currentAppId != AppId::Spotify) {
    winampDisplay.lastTouchResult = { "CLOCK", -1, "NONE", 0, -1, false };
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"CLOCK\",\"action\":\"NONE\",\"skipped\":false}\n", x, y);
    return;
  }
  winampDisplay.injectTouch(x, y);
  winampDisplay.injectRelease();
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
    winampDisplay.tickScroll(dtMs / 1000.0f);
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
    const char* nm = currentAppId == AppId::Spotify ? "Spotify"
                   : currentAppId == AppId::Clock   ? "Clock"
                   : currentAppId == AppId::Weather ? "Weather"
                   : currentAppId == AppId::Crypto  ? "Crypto"
                   : currentAppId == AppId::Matrix  ? "Matrix"
                   : currentAppId == AppId::Life     ? "Life"
                   : currentAppId == AppId::Settings ? "Settings"
                   : currentAppId == AppId::Stock    ? "Stock"
                   : currentAppId == AppId::Aquarium ? "Aquarium"
                   : "Unknown";
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
  if (strcmp(args, "golAlive") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"golAlive\","
                  "\"count\":%d,\"last\":true}\n", s_golAliveCount);
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
  Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                "\"error\":\"unknown var\",\"var\":\"%s\"}\n", var);
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

  drd->loop();
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

  unsigned long _loopMs = millis() - _loopStart;
  perf::recordLoop(_loopMs);
  if (_loopMs > 50) {
    LOG_W("perf", "iter=%lums (worst path so far: %s:%ums)",
          _loopMs, perf::worstPathName(), (unsigned)perf::worstPathMs());
  }
}
