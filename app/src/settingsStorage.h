#pragma once
#include <Arduino.h>

// Persists all runtime app settings to /settings.json on SPIFFS.
//
// Excluded — own files / own owners:
//   WiFi + Spotify creds  → /spotify_diy_config.json  (configFile.h / WiFiManager)
//   Touch calibration     → /cal.json                 (TouchCalStorage — history ring-buffer)

#define SETTINGS_JSON "/settings.json"

// ---- Enums ----------------------------------------------------------------

enum class DateFmt       : uint8_t { DMY = 0, MDY = 1, YMD = 2 };
enum class LedMode       : uint8_t { Off = 0, Static = 1, Pulse = 2, Clock = 3 };
enum class AppSpeed      : uint8_t { Slow = 0, Normal = 1, Fast = 2 };
enum class StockViewMode : uint8_t { List = 0, Chart = 1, Heatmap = 2 };
enum class MatrixColor   : uint8_t { Green = 0, White = 1, Amber = 2 };
enum class LifeColors    : uint8_t { Rainbow = 0, Mono = 1 };

// ---- Settings struct -------------------------------------------------------

struct AppSettings {

    // --- Time & Location (time-settings.md) ---
    char    posixTz[48];    // POSIX tz rule, e.g. "GMT0BST,M3.5.0/1,M10.5.0"
    char    tzName[32];     // display name, e.g. "Europe/London"
    char    city[24];       // selected city name; "" = none
    float   lat;
    float   lon;
    bool    fmt24h;         // true = 24h; false = 12h AM/PM
    DateFmt dateFmt;        // DMY / MDY / YMD

    // --- Display (display-settings.md) ---
    bool    dispAuto;       // true = LDR auto-brightness
    uint8_t dispLevel;      // 1..10 (used when dispAuto = false)
    int16_t ldrLow;         // ADC floor  for auto-brightness mapping
    int16_t ldrHigh;        // ADC ceiling for auto-brightness mapping

    // --- LED (led-settings.md) ---
    LedMode ledMode;
    uint8_t ledHue;   // 0..255 — HSV hue (0=red, 85≈green, 170≈blue)
    uint8_t ledSat;   // 0..255 — HSV saturation
    uint8_t ledVal;   // 0..255 — HSV value (brightness)

    // --- Stock (settings.md §Applications) ---
    char          stockTickers[8][8];   // up to 7-char symbol + NUL
    StockViewMode stockMode;

    // --- Crypto ---
    char    cryptoCoins[6][16];
    char    cryptoCcy[4];               // "USD" | "EUR"

    // --- Aquarium ---
    uint8_t  aquariumFish;              // 4 / 8 / 12 / 16
    AppSpeed aquariumSpeed;

    // --- Matrix ---
    MatrixColor matrixColor;
    AppSpeed    matrixSpeed;

    // --- Life ---
    AppSpeed   lifeSpeed;
    LifeColors lifeColors;

    // --- Teletext (ADR-044) ---
    uint16_t teletextPage;        // starting page on resume (default 101)
    uint8_t  teletextPollSecs;    // refresh cadence: 30/60/120 s (default 60)
    uint8_t  teletextCountry;     // 0 = NOS/NL; reserved until multi-country lands
    bool     teletextAutoAdvance; // reserved; no UI until subpage auto-advance implemented
};

extern AppSettings g_settings;

// ---- Storage API -----------------------------------------------------------

namespace SettingsStorage {
    void load();   // SPIFFS → g_settings; per-key defaults applied for missing entries
    void save();   // g_settings → SPIFFS
}
