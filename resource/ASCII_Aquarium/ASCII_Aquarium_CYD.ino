// ASCII_Aquarium_CYD.ino | Version: v1.67

// Optional manual edit notes: America/Winnipeg (Central Time) — use 12-hour style (e.g. 3:45 PM), not 24-hour.
#include <Arduino.h>
#include <cstring>
#include <FS.h>
#include <SPI.h>
#include <Preferences.h>
#include <SD.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <XPT2046_Touchscreen.h>
#include <time.h>

/*
  Desktop ASCII Aquarium for ESP32-2432S028R (CYD)
  Display: ILI9341 320x240 with TFT_eSPI
  Touch:   XPT2046

  CYD pin reference (commonly used board mapping):
    TFT_CS   = 15
    TFT_DC   = 2
    TFT_RST  = 4
    TFT_MOSI = 13
    TFT_SCLK = 14
    TFT_MISO = 12
    TFT_BL   = 21

    TOUCH_CS  = 33
    TOUCH_IRQ = 36
    TOUCH_CLK = 25
    TOUCH_MOSI= 32
    TOUCH_MISO= 39

    BOOT button = 0
    SD_CS      = 5
    SD_SCLK    = 18
    SD_MISO    = 19
    SD_MOSI    = 23

  NOTE:
  TFT pins are configured in TFT_eSPI User_Setup / User_Setup_Select.h.
*/

/** Shown run label in HUD title (must match line-1 banner when you release builds). */
static constexpr const char* kSketchVersionLabel = "v1.67";

// ------------------------------ CYD Touch Pins -------------------------------
static const int TOUCH_CS_PIN = 33;
static const int TOUCH_IRQ_PIN = 36;
static const int TOUCH_CLK_PIN = 25;
static const int TOUCH_MISO_PIN = 39;
static const int TOUCH_MOSI_PIN = 32;

// Touch calibration (adjust if needed for your panel)
static const int TOUCH_RAW_MIN_X = 250;
static const int TOUCH_RAW_MAX_X = 3850;
static const int TOUCH_RAW_MIN_Y = 220;
static const int TOUCH_RAW_MAX_Y = 3850;

// ------------------------------ Button / SD Capture --------------------------
static const int BOOT_BUTTON_PIN = 0;
static const unsigned long BOOT_BUTTON_DEBOUNCE_MS = 180UL;

// Common CYD microSD wiring. If your board revision differs, adjust these only.
static const int AQUARIUM_TFT_CS_PIN = 15;
static const int AQUARIUM_TFT_SCK_PIN = 14;
static const int AQUARIUM_TFT_MISO_PIN = 12;
static const int AQUARIUM_TFT_MOSI_PIN = 13;
static const int SD_CS_PIN = 5;
static const int SD_SCK_PIN = 18;
static const int SD_MISO_PIN = 19;
static const int SD_MOSI_PIN = 23;
static const uint32_t SD_SPI_FREQUENCY = 1000000UL;
static constexpr const char* CAPTURE_DIR = "/AQCAP";
static constexpr const char* SEQUENCE_DIR = "/AQSEQ";
static const unsigned long CAPTURE_RECORD_FRAME_MS = 50UL;  // 20 fps virtual time while recording.

// ------------------------------ Display Geometry -----------------------------
static const int SCREEN_W = 320;
static const int SCREEN_H = 240;
static const uint16_t BG_COLOR = TFT_BLACK;  // #000000
static const int SEA_LEVEL_Y = SCREEN_H - 36;
static const int BACKGROUND_GRADIENT_H = SCREEN_H / 4;

// ------------------------------ Settings UI ----------------------------------
static const int SETTINGS_PANEL_X = 40;
static const int SETTINGS_PANEL_Y = 24;
static const int SETTINGS_PANEL_W = 240;
static const int SETTINGS_PANEL_H = 208;
static const int SETTINGS_CLOSE_X = SETTINGS_PANEL_X + SETTINGS_PANEL_W - 34;
static const int SETTINGS_CLOSE_Y = SETTINGS_PANEL_Y + 8;
static const int SETTINGS_CLOSE_W = 24;
static const int SETTINGS_CLOSE_H = 24;
static const int SETTINGS_VALUE_RIGHT_X = SETTINGS_PANEL_X + 156;
static const int SETTINGS_MINUS_X = SETTINGS_PANEL_X + 166;
static const int SETTINGS_PLUS_X = SETTINGS_PANEL_X + 202;
static const int SETTINGS_BUTTON_W = 30;
static const int SETTINGS_BUTTON_H = 24;
static const int SETTINGS_ACTION_X = SETTINGS_PANEL_X + 134;
static const int SETTINGS_ACTION_W = 98;
static const int SETTINGS_ROW_START_Y = SETTINGS_PANEL_Y + 36;
static const int SETTINGS_ROW_GAP = 34;
static const int SETTINGS_TAB_Y = SETTINGS_PANEL_Y + SETTINGS_PANEL_H - 30;
static const int SETTINGS_TAB_H = 22;
static const int SETTINGS_TAB_GAP = 4;
static const int SETTINGS_TANK_TAB_X = SETTINGS_PANEL_X + 5;
static const int SETTINGS_TANK_TAB_W = 48;
static const int SETTINGS_SEAWEED_TAB_X = SETTINGS_TANK_TAB_X + SETTINGS_TANK_TAB_W + SETTINGS_TAB_GAP;
static const int SETTINGS_SEAWEED_TAB_W = 62;
static const int SETTINGS_CLOCK_TAB_X = SETTINGS_SEAWEED_TAB_X + SETTINGS_SEAWEED_TAB_W + SETTINGS_TAB_GAP;
static const int SETTINGS_CLOCK_TAB_W = 50;
static const int SETTINGS_BACKGROUND_TAB_X = SETTINGS_CLOCK_TAB_X + SETTINGS_CLOCK_TAB_W + SETTINGS_TAB_GAP;
static const int SETTINGS_BACKGROUND_TAB_W = 58;
static const int CLOCK_ROW_1_Y = SETTINGS_PANEL_Y + 36;
static const int CLOCK_ROW_2_Y = SETTINGS_PANEL_Y + 60;
static const int CLOCK_ROW_3_Y = SETTINGS_PANEL_Y + 84;
static const int CLOCK_ROW_4_Y = SETTINGS_PANEL_Y + 108;
static const int CLOCK_ROW_5_Y = SETTINGS_PANEL_Y + 132;
static const int CLOCK_FIELD_NAV_Y = SETTINGS_PANEL_Y + 157;
static const int CLOCK_FIELD_PREV_X = SETTINGS_PANEL_X + 12;
static const int CLOCK_FIELD_NEXT_X = SETTINGS_PANEL_X + 76;
static const int CLOCK_FIELD_NAV_W = 56;
static const int CLOCK_FIELD_NAV_H = 18;
static const int CLOCK_STYLE_BUTTON_X = SETTINGS_PANEL_X + 92;
static const int CLOCK_STYLE_BUTTON_W = 66;
static const int CLOCK_STYLE_PANEL_X = 46;
static const int CLOCK_STYLE_PANEL_Y = 54;
static const int CLOCK_STYLE_PANEL_W = 228;
static const int CLOCK_STYLE_PANEL_H = 176;
static const int CLOCK_STYLE_CLOSE_X = CLOCK_STYLE_PANEL_X + CLOCK_STYLE_PANEL_W - 32;
static const int CLOCK_STYLE_CLOSE_Y = CLOCK_STYLE_PANEL_Y + 8;
static const int CLOCK_STYLE_CLOSE_W = 24;
static const int CLOCK_STYLE_CLOSE_H = 22;
static const int CLOCK_STYLE_ROW_1_Y = CLOCK_STYLE_PANEL_Y + 40;
static const int CLOCK_STYLE_ROW_2_Y = CLOCK_STYLE_PANEL_Y + 74;
static const int CLOCK_STYLE_ROW_3_Y = CLOCK_STYLE_PANEL_Y + 104;
static const int CLOCK_STYLE_ROW_4_Y = CLOCK_STYLE_PANEL_Y + 134;
static const int CLOCK_STYLE_LABEL_X = CLOCK_STYLE_PANEL_X + 14;
static const int CLOCK_STYLE_LEFT_X = CLOCK_STYLE_PANEL_X + 104;
static const int CLOCK_STYLE_RIGHT_X = CLOCK_STYLE_PANEL_X + 164;
static const int CLOCK_STYLE_CHOICE_W = 54;
static const int CLOCK_STYLE_SWATCH_X = CLOCK_STYLE_LEFT_X;
static const int CLOCK_STYLE_SWATCH_W = 28;
static const int CLOCK_STYLE_COLOR_BUTTON_X = CLOCK_STYLE_RIGHT_X;
static const int CLOCK_STYLE_COLOR_BUTTON_W = 54;
static const int CLOCK_COLOR_PANEL_X = 20;
static const int CLOCK_COLOR_PANEL_Y = 38;
static const int CLOCK_COLOR_PANEL_W = 280;
static const int CLOCK_COLOR_PANEL_H = 164;
static const int CLOCK_COLOR_CLOSE_X = CLOCK_COLOR_PANEL_X + CLOCK_COLOR_PANEL_W - 32;
static const int CLOCK_COLOR_CLOSE_Y = CLOCK_COLOR_PANEL_Y + 8;
static const int CLOCK_COLOR_CLOSE_W = 24;
static const int CLOCK_COLOR_CLOSE_H = 22;
static const int CLOCK_COLOR_GRID_X = CLOCK_COLOR_PANEL_X + 14;
static const int CLOCK_COLOR_GRID_Y = CLOCK_COLOR_PANEL_Y + 46;
static const int CLOCK_COLOR_SWATCH_W = 26;
static const int CLOCK_COLOR_SWATCH_H = 22;
static const int CLOCK_COLOR_SWATCH_GAP_X = 7;
static const int CLOCK_COLOR_SWATCH_GAP_Y = 10;
static const int CLOCK_COLOR_SWATCH_COLS = 8;
static const int ASCII_CLOCK_ROWS = 6;
static const int ASCII_CLOCK_GLYPH_GAP = 1;
static const int ASCII_CLOCK_CHAR_W = 6;
static const int ASCII_CLOCK_ROW_H = 10;
static const int ASCII_CLOCK_Y = 68;
static const int CLOCK_FLIP_SPRITE_W = 192;
static const int CLOCK_FLIP_SPRITE_H = 20;
static const uint16_t CLOCK_FLIP_TRANSPARENT = 0x0801;  // Dark magenta key colour, outside the clock palette.

static const int CORNER_BUTTON_W = 28;
static const int CORNER_BUTTON_H = 20;
static const int CORNER_BUTTON_Y = 3;
static const int DEBUG_BUTTON_X = 7;
static const int WIFI_BUTTON_X = SCREEN_W - 70;
static const int SETTINGS_CORNER_BUTTON_X = SCREEN_W - 35;
static const int RESPAWN_BUTTON_Y = CORNER_BUTTON_Y + CORNER_BUTTON_H + 4;
static const int SEAHORSE_TEST_BUTTON_X = SETTINGS_CORNER_BUTTON_X;
static const int SEAHORSE_TEST_BUTTON_Y = RESPAWN_BUTTON_Y + CORNER_BUTTON_H + 4;
static const int OCTOPUS_TEST_BUTTON_X = SETTINGS_CORNER_BUTTON_X;
static const int OCTOPUS_TEST_BUTTON_Y = SEAHORSE_TEST_BUTTON_Y + CORNER_BUTTON_H + 4;

static const int WIFI_PANEL_X = 8;
static const int WIFI_PANEL_Y = 28;
static const int WIFI_PANEL_W = 304;
static const int WIFI_PANEL_H = 208;
static const int WIFI_CLOSE_X = WIFI_PANEL_X + WIFI_PANEL_W - 32;
static const int WIFI_CLOSE_Y = WIFI_PANEL_Y + 8;
static const int WIFI_CLOSE_W = 24;
static const int WIFI_CLOSE_H = 22;
static const int WIFI_ROW_START_Y = WIFI_PANEL_Y + 42;
static const int WIFI_ROW_GAP = 31;
static const int WIFI_ROW_H = 22;
static const int WIFI_LABEL_X = WIFI_PANEL_X + 14;
static const int WIFI_VALUE_RIGHT_X = WIFI_PANEL_X + 198;
static const int WIFI_OFF_X = WIFI_PANEL_X + 214;
static const int WIFI_ON_X = WIFI_PANEL_X + 260;
static const int WIFI_TOGGLE_W = 38;
static const int WIFI_ACTION_X = WIFI_PANEL_X + 228;
static const int WIFI_ACTION_W = 70;
static const int WIFI_LIST_ROW_COUNT = 5;
static const int WIFI_LIST_ROW_Y = WIFI_PANEL_Y + 56;
static const int WIFI_LIST_ROW_H = 23;
static const int WIFI_KEY_START_Y = WIFI_PANEL_Y + 68;
static const int WIFI_KEY_H = 18;
static const int WIFI_KEY_GAP = 3;
static const int WIFI_KEYBOARD_SPECIAL_Y = WIFI_PANEL_Y + 153;
static const int WIFI_KEYBOARD_ACTION_Y = WIFI_PANEL_Y + 179;

static const int CAPTURE_BUTTON_X = SCREEN_W - 105;
static const int CAPTURE_PANEL_X = 36;
static const int CAPTURE_PANEL_Y = 46;
static const int CAPTURE_PANEL_W = 248;
static const int CAPTURE_PANEL_H = 154;
static const int CAPTURE_CLOSE_X = CAPTURE_PANEL_X + CAPTURE_PANEL_W - 32;
static const int CAPTURE_CLOSE_Y = CAPTURE_PANEL_Y + 8;
static const int CAPTURE_CLOSE_W = 24;
static const int CAPTURE_CLOSE_H = 22;
static const int CAPTURE_ROW_START_Y = CAPTURE_PANEL_Y + 40;
static const int CAPTURE_ROW_GAP = 28;
static const int CAPTURE_ROW_H = 22;
static const int CAPTURE_LABEL_X = CAPTURE_PANEL_X + 14;
static const int CAPTURE_VALUE_RIGHT_X = CAPTURE_PANEL_X + 154;
static const int CAPTURE_ACTION_X = CAPTURE_PANEL_X + 162;
static const int CAPTURE_ACTION_W = 70;

enum SettingsTab {
  SETTINGS_TAB_TANK,
  SETTINGS_TAB_SEAWEED,
  SETTINGS_TAB_CLOCK,
  SETTINGS_TAB_BACKGROUND
};

enum ClockField {
  CLOCK_FIELD_YEAR,
  CLOCK_FIELD_MONTH,
  CLOCK_FIELD_DAY,
  CLOCK_FIELD_HOUR,
  CLOCK_FIELD_MINUTE,
  CLOCK_FIELD_COUNT
};

enum ClockDisplayStyle {
  CLOCK_STYLE_SMALL_TEXT,
  CLOCK_STYLE_ASCII,
  CLOCK_STYLE_COUNT
};

enum ClockSmallPosition {
  CLOCK_SMALL_TOP,
  CLOCK_SMALL_BOTTOM,
  CLOCK_SMALL_POSITION_COUNT
};

enum WifiPanelMode {
  WIFI_PANEL_MAIN,
  WIFI_PANEL_NETWORKS,
  WIFI_PANEL_PASSWORD
};

enum KeyboardMode {
  KEYBOARD_LOWER,
  KEYBOARD_UPPER,
  KEYBOARD_SYMBOLS
};

// ------------------------------ Aquarium Controls ----------------------------
static const int MIN_FISH = 6;
static const int MAX_FISH = 36;
static const int DEFAULT_FISH = 16;

static const int MIN_BUBBLES = 0;
static const int MAX_BUBBLES = 50;
static const int DEFAULT_BUBBLES = 10;

static const int DEFAULT_OCTOPUS_FREQUENCY = 1;
static const int OCTOPUS_FREQUENCY_OPTIONS[] = {1, 2, 4, 6, 12, 60};
static constexpr int OCTOPUS_FREQUENCY_OPTION_COUNT =
    sizeof(OCTOPUS_FREQUENCY_OPTIONS) / sizeof(OCTOPUS_FREQUENCY_OPTIONS[0]);
static const int DEFAULT_SEAHORSE_FREQUENCY = 1;
static const int SEAHORSE_FREQUENCY_OPTIONS[] = {1, 2, 4, 6, 12, 60};
static constexpr int SEAHORSE_FREQUENCY_OPTION_COUNT =
    sizeof(SEAHORSE_FREQUENCY_OPTIONS) / sizeof(SEAHORSE_FREQUENCY_OPTIONS[0]);

static const float MIN_SWAY = 0.25f;
static const float MAX_SWAY = 2.5f;
static const float DEFAULT_SWAY = 1.10f;

static const float MIN_SEAWEED_LENGTH = 0.80f;
static const float MAX_SEAWEED_LENGTH = 1.60f;
static const float DEFAULT_SEAWEED_LENGTH = 1.35f;

static const float MIN_SEAWEED_LENGTH_RANDOMNESS = 0.00f;
static const float MAX_SEAWEED_LENGTH_RANDOMNESS = 0.50f;
static const float DEFAULT_SEAWEED_LENGTH_RANDOMNESS = 0.35f;

static const int MAX_FLAKES = 16;
static const int MAX_FISH_POOL = 48;

static const float FISH_SWIM_WAVE_AMPLITUDE = 1.5f;
static const float FISH_SWIM_WAVE_SPEED = 5.6f;  // 30% slower than the first wave test
static const float FISH_SWIM_WAVE_SPACING = 0.85f;

static const float FISH_AVOID_RADIUS_X = 52.0f;
static const float FISH_AVOID_RADIUS_Y = 20.0f;
static const float FISH_AVOID_STRENGTH = 4.2f;
static const float FISH_CENTER_Y_OFFSET = 7.0f;

static const float OCTOPUS_EXIT_PAD = 42.0f;
static const float OCTOPUS_CENTER_Y_OFFSET = 8.0f;
static const float OCTOPUS_FISH_AVOID_RADIUS_X = 76.0f;
static const float OCTOPUS_FISH_AVOID_RADIUS_Y = 34.0f;
static const float OCTOPUS_FISH_AVOID_STRENGTH = 8.0f;
static const float OCTOPUS_FISH_CLEAR_RADIUS_X = 46.0f;
static const float OCTOPUS_FISH_CLEAR_RADIUS_Y = 22.0f;

static const float SEAHORSE_EXIT_PAD = 48.0f;
static const float SEAHORSE_CENTER_X_OFFSET = 15.0f;
static const float SEAHORSE_CENTER_Y_OFFSET = 24.0f;
static const float SEAHORSE_FISH_AVOID_RADIUS_X = 58.0f;
static const float SEAHORSE_FISH_AVOID_RADIUS_Y = 38.0f;
static const float SEAHORSE_FISH_AVOID_STRENGTH = 6.0f;
static const float SEAHORSE_FISH_CLEAR_RADIUS_X = 34.0f;
static const float SEAHORSE_FISH_CLEAR_RADIUS_Y = 28.0f;
static const float SEAHORSE_SPEED_BOOST = 1.18f;
static const float VISITOR_CLEAR_RADIUS_X = 56.0f;
static const float VISITOR_CLEAR_RADIUS_Y = 38.0f;

enum BackgroundMode {
  BACKGROUND_BLACK,
  BACKGROUND_BLUE_GRADIENT,
  BACKGROUND_PURPLE_GRADIENT,
  BACKGROUND_FLOWERS,
  BACKGROUND_MODE_COUNT
};
static const BackgroundMode DEFAULT_BACKGROUND_MODE = BACKGROUND_BLUE_GRADIENT;

static const int CLOCK_MIN_YEAR = 2024;
static const int CLOCK_MAX_YEAR = 2099;
static const int DEFAULT_CLOCK_YEAR = 2026;
static const int DEFAULT_CLOCK_MONTH = 1;
static const int DEFAULT_CLOCK_DAY = 1;
static const int DEFAULT_CLOCK_HOUR = 12;
static const int DEFAULT_CLOCK_MINUTE = 0;

static constexpr const char* CLOCK_NTP_1 = "pool.ntp.org";
static constexpr const char* CLOCK_NTP_2 = "time.nist.gov";
static constexpr const char* CLOCK_NTP_3 = "time.google.com";
static const int DEFAULT_TIMEZONE_INDEX = 5;  // Central time, matching the original hard-coded default.

static const int MAX_WIFI_NETWORKS = 12;
static const int WIFI_SSID_MAX_LEN = 32;
static const int WIFI_PASS_MAX_LEN = 64;
static const unsigned long WIFI_CONNECT_TIMEOUT_MS = 18000UL;
static const unsigned long WIFI_RECONNECT_DELAY_MS = 15000UL;
static const unsigned long NTP_RETRY_MS = 5000UL;
static const unsigned long NTP_REFRESH_MS = 3600000UL;

// ------------------------------ Objects --------------------------------------
struct Flake {
  bool active;
  float x, y;
  float vy;
  uint16_t color;
};

struct Bubble {
  bool active;
  float x, y;
  float baseX;
  float vy;
  float phase;
  float swayAmp;
  uint16_t color;
};

struct FishSpecies {
  const char* right;  // ASCII-only, faces right; mirrored at boot for vx < 0 (Font 2 safe)
  uint16_t baseColor;
};

struct Fish {
  bool active;
  int type;
  float x, y;
  float vx, vy;
  float speed;
  float phase;
  float wanderBias;
  int visualWidth;
  uint16_t displayColor;
  uint16_t renderColor;
  float depthBrightness;
};

struct Octopus {
  bool active;
  float x;
  float y;
  float baseY;
  float vx;
  float phase;
  float colorPhase;
  unsigned long nextSpawnMs;
};

struct Seahorse {
  bool active;
  bool facingRight;
  float x;
  float y;
  float baseY;
  float vx;
  float phase;
  float finPhase;
  unsigned long nextSpawnMs;
};

struct TimezoneOption {
  const char* label;
  const char* posix;
};

struct AsciiClockGlyph {
  char c;
  const char* rows[ASCII_CLOCK_ROWS];
};

static const TimezoneOption timezoneOptions[] = {
    {"UTC", "UTC0"},
    {"Hawaii", "HST10"},
    {"Alaska", "AKST9AKDT,M3.2.0/2,M11.1.0/2"},
    {"Pacific", "PST8PDT,M3.2.0/2,M11.1.0/2"},
    {"Mountain", "MST7MDT,M3.2.0/2,M11.1.0/2"},
    {"Central", "CST6CDT,M3.2.0/2,M11.1.0/2"},
    {"Eastern", "EST5EDT,M3.2.0/2,M11.1.0/2"},
    {"Atlantic", "AST4ADT,M3.2.0/2,M11.1.0/2"},
    {"Newfound", "NST3:30NDT,M3.2.0/2,M11.1.0/2"},
    {"UTC-3", "UTC3"},
    {"UTC-2", "UTC2"},
    {"UTC-1", "UTC1"},
    {"UK", "GMT0BST,M3.5.0/1,M10.5.0/2"},
    {"Central EU", "CET-1CEST,M3.5.0/2,M10.5.0/3"},
    {"Eastern EU", "EET-2EEST,M3.5.0/3,M10.5.0/4"},
    {"UTC+3", "UTC-3"},
    {"Iran", "IRST-3:30"},
    {"Gulf", "GST-4"},
    {"UTC+5", "UTC-5"},
    {"India", "IST-5:30"},
    {"UTC+6", "UTC-6"},
    {"UTC+7", "UTC-7"},
    {"China", "CST-8"},
    {"Japan", "JST-9"},
    {"Darwin", "ACST-9:30"},
    {"Sydney", "AEST-10AEDT,M10.1.0/2,M4.1.0/3"},
    {"UTC+11", "UTC-11"},
    {"New Zealand", "NZST-12NZDT,M9.5.0/2,M4.1.0/3"},
    {"UTC+13", "UTC-13"},
    {"UTC+14", "UTC-14"},
};
static constexpr int TIMEZONE_COUNT = sizeof(timezoneOptions) / sizeof(timezoneOptions[0]);

// RGB565 theme colours (names match your list)
static constexpr uint16_t RGB565(uint8_t r, uint8_t g, uint8_t b) {
  return uint16_t((r & 0xF8) << 8 | (g & 0xFC) << 3 | (b >> 3));
}

uint16_t scaleRgb565(uint16_t color, float brightness) {
  if (brightness < 0.0f) brightness = 0.0f;
  if (brightness > 1.0f) brightness = 1.0f;
  uint16_t r = (uint16_t)(((color >> 11) & 0x1F) * brightness);
  uint16_t g = (uint16_t)(((color >> 5) & 0x3F) * brightness);
  uint16_t b = (uint16_t)((color & 0x1F) * brightness);
  return (uint16_t)((r << 11) | (g << 5) | b);
}

uint16_t randomBubbleColor() {
  return RGB565((uint8_t)random(0, 5), (uint8_t)random(8, 24), (uint8_t)random(45, 106));
}

uint16_t randomFoodColor() {
  // Keep food orange but vary brightness/tint slightly for a natural look.
  return RGB565((uint8_t)random(220, 256), (uint8_t)random(118, 166), (uint8_t)random(0, 34));
}

static const uint16_t DEFAULT_ASCII_CLOCK_COLOR = RGB565(0, 20, 95);
static const uint16_t DEFAULT_SMALL_CLOCK_COLOR = TFT_WHITE;

static const uint16_t kClockColorPalette[] = {
    DEFAULT_ASCII_CLOCK_COLOR,
    TFT_WHITE,
    TFT_LIGHTGREY,
    TFT_DARKGREY,
    RGB565(255, 40, 40),
    RGB565(255, 128, 20),
    RGB565(255, 220, 40),
    RGB565(160, 255, 40),
    RGB565(40, 220, 80),
    RGB565(0, 180, 120),
    RGB565(0, 220, 220),
    RGB565(80, 180, 255),
    RGB565(40, 80, 255),
    RGB565(120, 80, 255),
    RGB565(220, 60, 255),
    RGB565(255, 120, 200),
    RGB565(100, 0, 0),
    RGB565(130, 56, 0),
    RGB565(116, 108, 18),
    RGB565(0, 82, 30),
    RGB565(0, 76, 76),
    RGB565(0, 0, 156),
    RGB565(58, 20, 120),
    RGB565(156, 120, 255),
};
static constexpr int CLOCK_COLOR_COUNT = sizeof(kClockColorPalette) / sizeof(kClockColorPalette[0]);

static const AsciiClockGlyph kAsciiClockStandardGlyphs[] = {
    {'0', {"  ___", " / _ \\", "| | | |", "| |_| |", " \\___/", ""}},
    {'1', {" _", "/ |", "| |", "| |", "|_|", ""}},
    {'2', {" ____", "|___ \\", "  __) |", " / __/", "|_____|", ""}},
    {'3', {" _____", "|___ /", "  |_ \\", " ___) |", "|____/", ""}},
    {'4', {" _  _", "| || |", "| || |_", "|__   _|", "   |_|", ""}},
    {'5', {" ____", "| ___|", "|___ \\", " ___) |", "|____/", ""}},
    {'6', {"  __", " / /_", "| '_ \\", "| (_) |", " \\___/", ""}},
    {'7', {" _____", "|___  |", "   / /", "  / /", " /_/", ""}},
    {'8', {"  ___", " ( _ )", " / _ \\", "| (_) |", " \\___/", ""}},
    {'9', {"  ___", " / _ \\", "| (_) |", " \\__, |", "  /_/", ""}},
    {':', {" ", " _", "(_)", " _", "(_)", " "}},
    {' ', {" ", " ", " ", " ", " ", " "}},
    {'a', {"", "  __ _", " / _` |", "| (_| |", " \\__,_|", ""}},
    {'m', {"", " _ __ ___", "| '_ ` _ \\", "| | | | | |", "|_| |_| |_|", ""}},
    {'p', {"", " _ __", "| '_ \\", "| |_) |", "| .__/", "|_|"}},
};

static const size_t kFishGlyphBuf = 28;

// Printable ASCII only (Font 2). Use ' instead of °, * instead of bullets, etc.
FishSpecies fishSpecies[] = {
    {/* Small Green */ "><>", RGB565(80, 200, 120)},                         // Emerald
    {/* Blue Dart */ ">)))'>", RGB565(0, 150, 255)},                         // Azure
    {/* Pink Bubble */ "oO0", TFT_PINK},                                      // Pink
    {/* Golden Emperor */ "><((( '>", RGB565(255, 184, 0)},                   // Amber
    {/* Purple Jellyfish */ "~~{o}", TFT_VIOLET},                              // Violet
    {/* Red Snapper */ "><(((o>", TFT_RED},                                   // Red
    {/* Orange Wrasse */ "><((((>`", TFT_ORANGE},
    {/* Teal Glider */ "><((( '>", RGB565(0, 180, 170)},
    {/* Royal Indigo */ "}>{{{{* >", RGB565(75, 0, 156)},                    // Indigo
    {/* Lilac Starfish */ "><((( *>", RGB565(200, 120, 255)},
    {/* Pink Tetra */ ">(')>", RGB565(255, 158, 200)},
    {/* Yellow Minnow */ ">'>", TFT_YELLOW},
};
static constexpr int GLYPH_COUNT = sizeof(fishSpecies) / sizeof(fishSpecies[0]);

static char fishMirroredLeft[GLYPH_COUNT][kFishGlyphBuf];
static uint8_t fishGlyphLenRight[GLYPH_COUNT];
static uint8_t fishGlyphLenLeft[GLYPH_COUNT];
static int16_t fishGlyphWidthRight[GLYPH_COUNT];
static int16_t fishGlyphWidthLeft[GLYPH_COUNT];
static int16_t fishGlyphOffsetRight[GLYPH_COUNT][kFishGlyphBuf];
static int16_t fishGlyphOffsetLeft[GLYPH_COUNT][kFishGlyphBuf];

static char mirrorAsciiBracket(char c) {
  switch (c) {
    case '>':
      return '<';
    case '<':
      return '>';
    case '(':
      return ')';
    case ')':
      return '(';
    case '{':
      return '}';
    case '}':
      return '{';
    case '[':
      return ']';
    case ']':
      return '[';
    default:
      return c;
  }
}

static bool buildMirroredGlyph(const char* right, char* leftOut, size_t outCap) {
  size_t n = strlen(right);
  if (n == 0 || n + 1 > outCap) return false;
  for (size_t i = 0; i < n; ++i) {
    unsigned char u = static_cast<unsigned char>(right[i]);
    if (u < 32 || u > 126) return false;
    leftOut[i] = mirrorAsciiBracket(right[n - 1 - i]);
  }
  leftOut[n] = '\0';
  return true;
}

static void initFishMirrors() {
  for (int i = 0; i < GLYPH_COUNT; ++i) {
    if (!buildMirroredGlyph(fishSpecies[i].right, fishMirroredLeft[i], kFishGlyphBuf)) {
      strncpy(fishMirroredLeft[i], fishSpecies[i].right, kFishGlyphBuf - 1);
      fishMirroredLeft[i][kFishGlyphBuf - 1] = '\0';
    }
  }
}

inline const char* fishGlyphDrawing(const Fish& f) {
  return (f.vx >= 0.0f) ? fishSpecies[f.type].right : fishMirroredLeft[f.type];
}

// Occasional non-canonical hue for variety (~1 in 5 fish)
static const uint16_t kAltFishColors[] = {
    TFT_CYAN, TFT_MAGENTA, TFT_WHITE, TFT_SKYBLUE, TFT_GOLD,
    TFT_ORANGE, TFT_GREENYELLOW, TFT_DARKGREY};
static const int kAltFishColorCount = sizeof(kAltFishColors) / sizeof(kAltFishColors[0]);

// ------------------------------ Globals --------------------------------------
TFT_eSPI tft = TFT_eSPI();
TFT_eSprite canvas = TFT_eSprite(&tft);
TFT_eSprite clockFlipSprite = TFT_eSprite(&tft);
SPIClass touchSPI(HSPI);
SPIClass sdSPI(VSPI);
XPT2046_Touchscreen touch(TOUCH_CS_PIN, TOUCH_IRQ_PIN);
Preferences prefs;

Fish fishPool[MAX_FISH_POOL];
Flake flakes[MAX_FLAKES];
Bubble bubbles[MAX_BUBBLES];
Octopus octopus;
Seahorse seahorse;

int fishTargetCount = DEFAULT_FISH;
int bubbleTargetCount = DEFAULT_BUBBLES;
int octopusFrequency = DEFAULT_OCTOPUS_FREQUENCY;
int seahorseFrequency = DEFAULT_SEAHORSE_FREQUENCY;
float seaweedSwaySpeed = DEFAULT_SWAY;
float seaweedLength = DEFAULT_SEAWEED_LENGTH;
float seaweedLengthRandomness = DEFAULT_SEAWEED_LENGTH_RANDOMNESS;
bool hudVisible = false;  // HUD + corner H/S hidden until top-left toggle
bool settingsOpen = false;
SettingsTab activeSettingsTab = SETTINGS_TAB_TANK;
BackgroundMode backgroundMode = DEFAULT_BACKGROUND_MODE;

bool clockVisible = false;
bool clockUse24Hour = false;
bool clockUseInternetTime = false;
ClockDisplayStyle clockDisplayStyle = CLOCK_STYLE_SMALL_TEXT;
ClockSmallPosition clockSmallPosition = CLOCK_SMALL_TOP;
bool clockStylePanelOpen = false;
bool clockColorPanelOpen = false;
bool clockFlipHorizontal = false;
uint16_t clockSmallTextColor = DEFAULT_SMALL_CLOCK_COLOR;
uint16_t clockAsciiTextColor = DEFAULT_ASCII_CLOCK_COLOR;
bool clockFlipSpriteReady = false;
int timezoneIndex = DEFAULT_TIMEZONE_INDEX;
int clockYear = DEFAULT_CLOCK_YEAR;
int clockMonth = DEFAULT_CLOCK_MONTH;
int clockDay = DEFAULT_CLOCK_DAY;
int clockHour = DEFAULT_CLOCK_HOUR;
int clockMinute = DEFAULT_CLOCK_MINUTE;
unsigned long clockLastMinuteMs = 0;
ClockField activeClockField = CLOCK_FIELD_HOUR;

bool wifiPanelOpen = false;
WifiPanelMode wifiPanelMode = WIFI_PANEL_MAIN;
KeyboardMode keyboardMode = KEYBOARD_LOWER;
bool wifiEnabled = false;
bool wifiRadioStarted = false;
bool wifiScanInProgress = false;
bool wifiConnecting = false;
bool wifiConnected = false;
bool wifiConnectionFailed = false;
bool wifiSavePendingCredentials = false;
bool wifiTimeConfigured = false;
bool wifiTimeSynced = false;
char wifiStatusText[40] = "Off";
char wifiSsid[WIFI_SSID_MAX_LEN + 1] = "";
char wifiPass[WIFI_PASS_MAX_LEN + 1] = "";
char pendingWifiSsid[WIFI_SSID_MAX_LEN + 1] = "";
char pendingWifiPass[WIFI_PASS_MAX_LEN + 1] = "";
char wifiPasswordBuffer[WIFI_PASS_MAX_LEN + 1] = "";
char wifiNetworkNames[MAX_WIFI_NETWORKS][WIFI_SSID_MAX_LEN + 1];
int wifiNetworkRssi[MAX_WIFI_NETWORKS];
bool wifiNetworkOpen[MAX_WIFI_NETWORKS];
int wifiNetworkCount = 0;
int wifiNetworkPage = 0;
unsigned long wifiConnectStartMs = 0;
unsigned long wifiLastReconnectMs = 0;
unsigned long wifiLastNtpAttemptMs = 0;
unsigned long wifiLastNtpSyncMs = 0;

bool bootButtonLastReading = false;
bool bootButtonStablePressed = false;
unsigned long bootButtonLastChangeMs = 0;

bool capturePanelOpen = false;
bool captureSdReady = false;
bool captureIndexReady = false;
bool captureSinglePending = false;
bool captureSequenceEnabled = false;
unsigned long captureNextImageIndex = 1;
unsigned long captureNextSequenceIndex = 1;
unsigned long captureStatusMs = 0;
unsigned long captureToastUntilMs = 0;
char captureStatusText[48] = "SD not checked";
char captureLastFile[40] = "";
char captureSequenceDir[24] = "/AQSEQ";
uint8_t bmpRowBuffer[SCREEN_W * 3];

unsigned long lastMs = 0;
// Animation clock. During sequence capture it advances one video frame per saved BMP,
// so slow SD writes do not create skipped motion in the exported image sequence.
unsigned long aquariumNowMs = 0;
unsigned long fpsTimer = 0;
unsigned long frameCount = 0;
float fps = 0.0f;

unsigned long lastTouchMs = 0;
const unsigned long TOUCH_DEBOUNCE_MS = 160;
bool spriteReady = false;
bool touchReady = false;
uint16_t gradientBandCache[SCREEN_W * BACKGROUND_GRADIENT_H];
BackgroundMode gradientBandCacheMode = BACKGROUND_MODE_COUNT;
bool settingsDirty = false;
unsigned long settingsDirtyMs = 0;
unsigned long lastSettingsSaveMs = 0;
static const unsigned long SETTINGS_SAVE_DELAY_MS = 1200UL;
static const unsigned long CLOCK_AUTOSAVE_INTERVAL_MS = 300000UL;

void beginInternetTimeSync();

void cacheGlyphMetrics(const char* txt, uint8_t& lenOut, int16_t& widthOut, int16_t offsetsOut[]) {
  char prefix[kFishGlyphBuf];
  size_t len = strlen(txt);
  if (len >= kFishGlyphBuf) len = kFishGlyphBuf - 1;

  for (size_t c = 0; c < len; ++c) {
    memcpy(prefix, txt, c);
    prefix[c] = '\0';
    offsetsOut[c] = (int16_t)tft.textWidth(prefix);
  }

  lenOut = (uint8_t)len;
  widthOut = (int16_t)tft.textWidth(txt);
}

void initFishGlyphMetrics() {
  for (int i = 0; i < GLYPH_COUNT; ++i) {
    cacheGlyphMetrics(fishSpecies[i].right, fishGlyphLenRight[i], fishGlyphWidthRight[i], fishGlyphOffsetRight[i]);
    cacheGlyphMetrics(fishMirroredLeft[i], fishGlyphLenLeft[i], fishGlyphWidthLeft[i], fishGlyphOffsetLeft[i]);
  }
}

// ------------------------------ Utility --------------------------------------
template <typename T>
T clampVal(T v, T lo, T hi) {
  return (v < lo) ? lo : ((v > hi) ? hi : v);
}

void copySafe(char* out, size_t outCap, const char* src) {
  if (outCap == 0) return;
  if (!src) src = "";
  strncpy(out, src, outCap - 1);
  out[outCap - 1] = '\0';
}

void appendCharSafe(char* out, size_t outCap, char c) {
  size_t len = strlen(out);
  if (len + 1 >= outCap) return;
  out[len] = c;
  out[len + 1] = '\0';
}

void removeLastChar(char* out) {
  size_t len = strlen(out);
  if (len > 0) out[len - 1] = '\0';
}

void formatShortText(char* out, size_t outCap, const char* src, size_t maxChars) {
  if (outCap == 0) return;
  if (!src) src = "";
  if (outCap < 4) {
    copySafe(out, outCap, src);
    return;
  }
  size_t len = strlen(src);
  if (len <= maxChars || maxChars < 4) {
    copySafe(out, outCap, src);
    return;
  }

  size_t copyLen = maxChars - 3;
  if (copyLen > outCap - 4) copyLen = outCap - 4;
  strncpy(out, src, copyLen);
  out[copyLen] = '\0';
  strncat(out, "...", outCap - strlen(out) - 1);
}

void markSettingsDirty() {
  settingsDirty = true;
  settingsDirtyMs = millis();
}

float aquariumTimeSec() {
  return aquariumNowMs * 0.001f;
}

void setCaptureStatus(const char* status, bool toast = false) {
  copySafe(captureStatusText, sizeof(captureStatusText), status);
  captureStatusMs = millis();
  if (toast) captureToastUntilMs = captureStatusMs + 2400UL;
}

void beginCaptureSdBus() {
  pinMode(AQUARIUM_TFT_CS_PIN, OUTPUT);
  pinMode(SD_CS_PIN, OUTPUT);
  digitalWrite(AQUARIUM_TFT_CS_PIN, HIGH);
  digitalWrite(SD_CS_PIN, HIGH);
  sdSPI.begin(SD_SCK_PIN, SD_MISO_PIN, SD_MOSI_PIN);
  sdSPI.setFrequency(SD_SPI_FREQUENCY);
}

void restoreTftBus() {
  TFT_eSPI::getSPIinstance().begin(AQUARIUM_TFT_SCK_PIN, AQUARIUM_TFT_MISO_PIN, AQUARIUM_TFT_MOSI_PIN, -1);
}

void writeLE16(File& file, uint16_t value) {
  uint8_t bytes[2] = {(uint8_t)(value & 0xFF), (uint8_t)(value >> 8)};
  file.write(bytes, sizeof(bytes));
}

void writeLE32(File& file, uint32_t value) {
  uint8_t bytes[4] = {
      (uint8_t)(value & 0xFF),
      (uint8_t)((value >> 8) & 0xFF),
      (uint8_t)((value >> 16) & 0xFF),
      (uint8_t)((value >> 24) & 0xFF)};
  file.write(bytes, sizeof(bytes));
}

void capturePath(char* out, size_t outCap, bool sequence, unsigned long index) {
  if (sequence) {
    snprintf(out, outCap, "%s/SEQ_%06lu.BMP", captureSequenceDir, index);
  } else {
    snprintf(out, outCap, "%s/SCR_%06lu.BMP", CAPTURE_DIR, index);
  }
}

unsigned long findNextCaptureIndex(bool sequence, unsigned long startIndex) {
  char path[40];
  unsigned long limit = sequence ? 999999UL : 9999UL;
  unsigned long index = clampVal(startIndex, 1UL, limit);
  while (index <= limit) {
    capturePath(path, sizeof(path), sequence, index);
    if (!SD.exists(path)) return index;
    index++;
  }
  return 1UL;
}

bool ensureCaptureSdReady() {
  beginCaptureSdBus();

  bool justMounted = false;
  if (!captureSdReady) {
    SD.end();
    delay(12);
    captureSdReady = SD.begin(SD_CS_PIN, sdSPI, SD_SPI_FREQUENCY);
    justMounted = captureSdReady;
  }

  if (!captureSdReady) {
    captureSdReady = false;
    captureIndexReady = false;
    captureSequenceEnabled = false;
    capturePanelOpen = true;
    setCaptureStatus("SD begin failed");
    return false;
  }

  if (justMounted && SD.cardType() == CARD_NONE) {
    SD.end();
    captureSdReady = false;
    captureIndexReady = false;
    captureSequenceEnabled = false;
    capturePanelOpen = true;
    setCaptureStatus("No card");
    return false;
  }

  SD.mkdir(CAPTURE_DIR);
  SD.mkdir(SEQUENCE_DIR);
  if (!captureIndexReady) {
    // Avoid scanning old sequence frames here. A card with thousands of BMPs in
    // /AQSEQ can otherwise look frozen while Check probes every old filename.
    captureNextImageIndex = clampVal(captureNextImageIndex, 1UL, 9999UL);
    captureNextSequenceIndex = 1;
    captureIndexReady = true;
  }
  if (!captureSequenceEnabled) {
    unsigned long cardMb = (unsigned long)(SD.cardSize() / (1024ULL * 1024ULL));
    char status[48];
    snprintf(status, sizeof(status), "SD OK %luMB", cardMb);
    setCaptureStatus(status);
  }
  return true;
}

bool checkCaptureSdReady() {
  captureSdReady = false;
  captureIndexReady = false;
  bool ready = ensureCaptureSdReady();
  restoreTftBus();
  return ready;
}

bool beginCaptureSequenceSession() {
  beginCaptureSdBus();
  for (int attempt = 0; attempt < 8; ++attempt) {
    unsigned long sessionId = (unsigned long)esp_random();
    if (sessionId == 0) sessionId = millis();
    snprintf(captureSequenceDir, sizeof(captureSequenceDir), "%s/S%08lX", SEQUENCE_DIR, sessionId);
    if (SD.mkdir(captureSequenceDir)) {
      captureNextSequenceIndex = 1;
      restoreTftBus();
      return true;
    }
  }

  copySafe(captureSequenceDir, sizeof(captureSequenceDir), SEQUENCE_DIR);
  setCaptureStatus("Seq dir failed");
  restoreTftBus();
  return false;
}

bool saveBmpToSd(TFT_eSprite& s, const char* path) {
  File file = SD.open(path, FILE_WRITE);
  if (!file) {
    setCaptureStatus("File open failed");
    captureSequenceEnabled = false;
    capturePanelOpen = true;
    return false;
  }

  const uint32_t rowSize = SCREEN_W * 3UL;
  const uint32_t pixelBytes = rowSize * SCREEN_H;
  const uint32_t fileSize = 54UL + pixelBytes;

  file.write((const uint8_t*)"BM", 2);
  writeLE32(file, fileSize);
  writeLE16(file, 0);
  writeLE16(file, 0);
  writeLE32(file, 54);
  writeLE32(file, 40);
  writeLE32(file, SCREEN_W);
  writeLE32(file, SCREEN_H);
  writeLE16(file, 1);
  writeLE16(file, 24);
  writeLE32(file, 0);
  writeLE32(file, pixelBytes);
  writeLE32(file, 2835);
  writeLE32(file, 2835);
  writeLE32(file, 0);
  writeLE32(file, 0);

  for (int y = SCREEN_H - 1; y >= 0; --y) {
    for (int x = 0; x < SCREEN_W; ++x) {
      uint16_t color = s.readPixel(x, y);
      int o = x * 3;
      bmpRowBuffer[o + 0] = (uint8_t)(((color & 0x1F) * 255) / 31);
      bmpRowBuffer[o + 1] = (uint8_t)((((color >> 5) & 0x3F) * 255) / 63);
      bmpRowBuffer[o + 2] = (uint8_t)((((color >> 11) & 0x1F) * 255) / 31);
    }
    if (file.write(bmpRowBuffer, rowSize) != rowSize) {
      file.close();
      setCaptureStatus("Write failed");
      captureSequenceEnabled = false;
      capturePanelOpen = true;
      return false;
    }
  }

  file.close();
  return true;
}

bool saveNextCaptureFrame(TFT_eSprite& s, bool sequence, bool showToast) {
  if (!ensureCaptureSdReady()) {
    restoreTftBus();
    return false;
  }

  char path[40];
  unsigned long& index = sequence ? captureNextSequenceIndex : captureNextImageIndex;
  if (!sequence) index = findNextCaptureIndex(false, index);
  capturePath(path, sizeof(path), sequence, index);

  if (!saveBmpToSd(s, path)) {
    restoreTftBus();
    return false;
  }

  index++;
  copySafe(captureLastFile, sizeof(captureLastFile), path);
  char status[48];
  snprintf(status, sizeof(status), "Saved %s", strrchr(path, '/') ? strrchr(path, '/') + 1 : path);
  setCaptureStatus(status, showToast);
  restoreTftBus();
  return true;
}

void requestSingleCapture() {
  captureSinglePending = true;
  setCaptureStatus("Saving BMP...");
}

void stopCaptureRecording(bool showToast) {
  if (!captureSequenceEnabled) return;
  captureSequenceEnabled = false;
  setCaptureStatus("Recording stopped", showToast);
}

void setCaptureSequenceEnabled(bool enabled) {
  if (!enabled) {
    stopCaptureRecording(false);
    return;
  }

  if (checkCaptureSdReady() && beginCaptureSequenceSession()) {
    captureSequenceEnabled = true;
    capturePanelOpen = false;
    settingsOpen = false;
    wifiPanelOpen = false;
    hudVisible = false;
    captureToastUntilMs = 0;
    setCaptureStatus("Recording frames");
  }
}

float frand(float a, float b) {
  return a + (b - a) * (float)random(0, 10000) / 9999.0f;
}

int fishVisualWidth(const Fish& f) {
  if (f.visualWidth > 0) return f.visualWidth;
  return (int)strlen(fishGlyphDrawing(f)) * 12;  // Font 2 fallback before metrics init
}

inline int activeFishLimit() {
  return clampVal(fishTargetCount, 0, MAX_FISH_POOL);
}

inline int activeBubbleLimit() {
  return clampVal(bubbleTargetCount, 0, MAX_BUBBLES);
}

int normalizeOctopusFrequency(int value) {
  int best = OCTOPUS_FREQUENCY_OPTIONS[0];
  int bestDiff = abs(value - best);
  for (int i = 1; i < OCTOPUS_FREQUENCY_OPTION_COUNT; ++i) {
    int diff = abs(value - OCTOPUS_FREQUENCY_OPTIONS[i]);
    if (diff < bestDiff) {
      best = OCTOPUS_FREQUENCY_OPTIONS[i];
      bestDiff = diff;
    }
  }
  return best;
}

int normalizeSeahorseFrequency(int value) {
  int best = SEAHORSE_FREQUENCY_OPTIONS[0];
  int bestDiff = abs(value - best);
  for (int i = 1; i < SEAHORSE_FREQUENCY_OPTION_COUNT; ++i) {
    int diff = abs(value - SEAHORSE_FREQUENCY_OPTIONS[i]);
    if (diff < bestDiff) {
      best = SEAHORSE_FREQUENCY_OPTIONS[i];
      bestDiff = diff;
    }
  }
  return best;
}

void cycleOctopusFrequency(int delta) {
  int current = normalizeOctopusFrequency(octopusFrequency);
  int index = 0;
  for (int i = 0; i < OCTOPUS_FREQUENCY_OPTION_COUNT; ++i) {
    if (OCTOPUS_FREQUENCY_OPTIONS[i] == current) {
      index = i;
      break;
    }
  }

  index += delta;
  if (index < 0) index = OCTOPUS_FREQUENCY_OPTION_COUNT - 1;
  if (index >= OCTOPUS_FREQUENCY_OPTION_COUNT) index = 0;
  octopusFrequency = OCTOPUS_FREQUENCY_OPTIONS[index];
  if (!octopus.active) octopus.nextSpawnMs = 0;
  markSettingsDirty();
}

void cycleSeahorseFrequency(int delta) {
  int current = normalizeSeahorseFrequency(seahorseFrequency);
  int index = 0;
  for (int i = 0; i < SEAHORSE_FREQUENCY_OPTION_COUNT; ++i) {
    if (SEAHORSE_FREQUENCY_OPTIONS[i] == current) {
      index = i;
      break;
    }
  }

  index += delta;
  if (index < 0) index = SEAHORSE_FREQUENCY_OPTION_COUNT - 1;
  if (index >= SEAHORSE_FREQUENCY_OPTION_COUNT) index = 0;
  seahorseFrequency = SEAHORSE_FREQUENCY_OPTIONS[index];
  if (!seahorse.active) seahorse.nextSpawnMs = 0;
  markSettingsDirty();
}

unsigned long octopusSpawnIntervalMs() {
  int frequency = normalizeOctopusFrequency(octopusFrequency);
  return 3600000UL / (unsigned long)frequency;
}

unsigned long seahorseSpawnIntervalMs() {
  int frequency = normalizeSeahorseFrequency(seahorseFrequency);
  return 3600000UL / (unsigned long)frequency;
}

inline uint8_t fishGlyphLength(const Fish& f) {
  return (f.vx >= 0.0f) ? fishGlyphLenRight[f.type] : fishGlyphLenLeft[f.type];
}

inline const int16_t* fishGlyphOffsets(const Fish& f) {
  return (f.vx >= 0.0f) ? fishGlyphOffsetRight[f.type] : fishGlyphOffsetLeft[f.type];
}

int screenMapX(int rawX) {
  rawX = clampVal(rawX, TOUCH_RAW_MIN_X, TOUCH_RAW_MAX_X);
  return map(rawX, TOUCH_RAW_MIN_X, TOUCH_RAW_MAX_X, 0, SCREEN_W - 1);
}

int screenMapY(int rawY) {
  rawY = clampVal(rawY, TOUCH_RAW_MIN_Y, TOUCH_RAW_MAX_Y);
  return map(rawY, TOUCH_RAW_MIN_Y, TOUCH_RAW_MAX_Y, 0, SCREEN_H - 1);
}

bool readTouchPoint(int& sx, int& sy) {
  if (!touchReady) return false;
  if (!touch.touched()) return false;
  TS_Point p = touch.getPoint();
  sx = screenMapX(p.x);
  sy = screenMapY(p.y);
  return (sx >= 0 && sx < SCREEN_W && sy >= 0 && sy < SCREEN_H);
}

bool isLeapYear(int year) {
  return ((year % 4 == 0) && (year % 100 != 0)) || (year % 400 == 0);
}

int daysInMonth(int year, int month) {
  static const uint8_t daysByMonth[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  month = clampVal(month, 1, 12);
  if (month == 2 && isLeapYear(year)) return 29;
  return daysByMonth[month - 1];
}

void normalizeClockDate() {
  clockYear = clampVal(clockYear, CLOCK_MIN_YEAR, CLOCK_MAX_YEAR);
  clockMonth = clampVal(clockMonth, 1, 12);
  clockDay = clampVal(clockDay, 1, daysInMonth(clockYear, clockMonth));
  clockHour = clampVal(clockHour, 0, 23);
  clockMinute = clampVal(clockMinute, 0, 59);
}

void incrementClockDay() {
  clockDay++;
  if (clockDay > daysInMonth(clockYear, clockMonth)) {
    clockDay = 1;
    clockMonth++;
    if (clockMonth > 12) {
      clockMonth = 1;
      if (clockYear < CLOCK_MAX_YEAR) clockYear++;
    }
  }
}

void decrementClockDay() {
  clockDay--;
  if (clockDay < 1) {
    clockMonth--;
    if (clockMonth < 1) {
      clockMonth = 12;
      if (clockYear > CLOCK_MIN_YEAR) clockYear--;
    }
    clockDay = daysInMonth(clockYear, clockMonth);
  }
}

void addClockMinute(int delta) {
  if (delta > 0) {
    clockMinute++;
    if (clockMinute >= 60) {
      clockMinute = 0;
      clockHour++;
      if (clockHour >= 24) {
        clockHour = 0;
        incrementClockDay();
      }
    }
  } else if (delta < 0) {
    clockMinute--;
    if (clockMinute < 0) {
      clockMinute = 59;
      clockHour--;
      if (clockHour < 0) {
        clockHour = 23;
        decrementClockDay();
      }
    }
  }
}

void updateClock(unsigned long now) {
  while (now - clockLastMinuteMs >= 60000UL) {
    clockLastMinuteMs += 60000UL;
    addClockMinute(1);
  }
}

void resetClockTick() {
  clockLastMinuteMs = millis();
}

void selectClockField(int delta) {
  int next = (int)activeClockField + delta;
  if (next < 0) next = CLOCK_FIELD_COUNT - 1;
  if (next >= CLOCK_FIELD_COUNT) next = 0;
  activeClockField = (ClockField)next;
}

void adjustClockField(int delta) {
  switch (activeClockField) {
    case CLOCK_FIELD_YEAR:
      clockYear = clampVal(clockYear + delta, CLOCK_MIN_YEAR, CLOCK_MAX_YEAR);
      break;
    case CLOCK_FIELD_MONTH:
      clockMonth += delta;
      if (clockMonth < 1) clockMonth = 12;
      if (clockMonth > 12) clockMonth = 1;
      break;
    case CLOCK_FIELD_DAY:
      clockDay += delta;
      if (clockDay < 1) clockDay = daysInMonth(clockYear, clockMonth);
      if (clockDay > daysInMonth(clockYear, clockMonth)) clockDay = 1;
      break;
    case CLOCK_FIELD_HOUR:
      clockHour += delta;
      if (clockHour < 0) clockHour = 23;
      if (clockHour > 23) clockHour = 0;
      break;
    case CLOCK_FIELD_MINUTE:
      clockMinute += delta;
      if (clockMinute < 0) clockMinute = 59;
      if (clockMinute > 59) clockMinute = 0;
      break;
    default:
      break;
  }
  normalizeClockDate();
  resetClockTick();
  markSettingsDirty();
}

const char* clockFieldName() {
  switch (activeClockField) {
    case CLOCK_FIELD_YEAR:
      return "Year";
    case CLOCK_FIELD_MONTH:
      return "Month";
    case CLOCK_FIELD_DAY:
      return "Day";
    case CLOCK_FIELD_HOUR:
      return "Hour";
    case CLOCK_FIELD_MINUTE:
      return "Minute";
    default:
      return "Clock";
  }
}

void formatClockFieldValue(char* out, size_t outCap) {
  switch (activeClockField) {
    case CLOCK_FIELD_YEAR:
      snprintf(out, outCap, "%d", clockYear);
      break;
    case CLOCK_FIELD_MONTH:
      snprintf(out, outCap, "%02d", clockMonth);
      break;
    case CLOCK_FIELD_DAY:
      snprintf(out, outCap, "%02d", clockDay);
      break;
    case CLOCK_FIELD_HOUR:
      if (clockUse24Hour) {
        snprintf(out, outCap, "%02d", clockHour);
      } else {
        int h = clockHour % 12;
        if (h == 0) h = 12;
        snprintf(out, outCap, "%d %s", h, clockHour < 12 ? "AM" : "PM");
      }
      break;
    case CLOCK_FIELD_MINUTE:
      snprintf(out, outCap, "%02d", clockMinute);
      break;
    default:
      snprintf(out, outCap, "--");
      break;
  }
}

void formatClockDisplay(char* out, size_t outCap) {
  static const char* monthNames[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
  if (clockUse24Hour) {
    snprintf(out, outCap, "%s %02d  %02d:%02d", monthNames[clockMonth - 1], clockDay, clockHour, clockMinute);
  } else {
    int h = clockHour % 12;
    if (h == 0) h = 12;
    snprintf(out, outCap, "%s %02d  %d:%02d %s", monthNames[clockMonth - 1], clockDay, h, clockMinute,
             clockHour < 12 ? "AM" : "PM");
  }
}

void formatClockTimeOnly(char* out, size_t outCap, bool includeMeridiem) {
  if (clockUse24Hour) {
    snprintf(out, outCap, "%02d:%02d", clockHour, clockMinute);
  } else {
    int h = clockHour % 12;
    if (h == 0) h = 12;
    if (includeMeridiem) {
      snprintf(out, outCap, "%d:%02d %s", h, clockMinute, clockHour < 12 ? "am" : "pm");
    } else {
      snprintf(out, outCap, "%d:%02d", h, clockMinute);
    }
  }
}

const AsciiClockGlyph& asciiClockGlyphFor(char c) {
  for (size_t i = 0; i < sizeof(kAsciiClockStandardGlyphs) / sizeof(kAsciiClockStandardGlyphs[0]); ++i) {
    if (kAsciiClockStandardGlyphs[i].c == c) return kAsciiClockStandardGlyphs[i];
  }
  return kAsciiClockStandardGlyphs[11];  // Space
}

int asciiClockGlyphWidth(const AsciiClockGlyph& glyph) {
  int width = 1;
  for (int row = 0; row < ASCII_CLOCK_ROWS; ++row) {
    int rowWidth = strlen(glyph.rows[row]);
    if (rowWidth > width) width = rowWidth;
  }
  return width;
}

int asciiClockTextCols(const char* text) {
  int cols = 0;
  for (size_t i = 0; text[i] != '\0'; ++i) {
    if (i > 0) cols += ASCII_CLOCK_GLYPH_GAP;
    cols += asciiClockGlyphWidth(asciiClockGlyphFor(text[i]));
  }
  return cols;
}

void appendAsciiClockGlyphRow(char* out, size_t outCap, const AsciiClockGlyph& glyph, int row) {
  int width = asciiClockGlyphWidth(glyph);
  int rowLen = strlen(glyph.rows[row]);
  for (int col = 0; col < width; ++col) {
    appendCharSafe(out, outCap, col < rowLen ? glyph.rows[row][col] : ' ');
  }
}

void trimTrailingSpaces(char* out) {
  int len = strlen(out);
  while (len > 0 && out[len - 1] == ' ') {
    out[--len] = '\0';
  }
}

char mirroredClockChar(char c) {
  switch (c) {
    case '/': return '\\';
    case '\\': return '/';
    case '(': return ')';
    case ')': return '(';
    case '[': return ']';
    case ']': return '[';
    case '{': return '}';
    case '}': return '{';
    case '<': return '>';
    case '>': return '<';
    default: return c;
  }
}

void mirrorClockTextInPlace(char* text) {
  int len = strlen(text);
  for (int i = 0; i < len / 2; ++i) {
    char left = mirroredClockChar(text[i]);
    char right = mirroredClockChar(text[len - 1 - i]);
    text[i] = right;
    text[len - 1 - i] = left;
  }
  if (len % 2 == 1) {
    text[len / 2] = mirroredClockChar(text[len / 2]);
  }
}

uint16_t activeClockTextColor() {
  return (clockDisplayStyle == CLOCK_STYLE_ASCII) ? clockAsciiTextColor : clockSmallTextColor;
}

void setActiveClockTextColor(uint16_t color) {
  if (clockDisplayStyle == CLOCK_STYLE_ASCII) {
    clockAsciiTextColor = color;
  } else {
    clockSmallTextColor = color;
  }
  markSettingsDirty();
}

const TimezoneOption& currentTimezone() {
  timezoneIndex = clampVal(timezoneIndex, 0, TIMEZONE_COUNT - 1);
  return timezoneOptions[timezoneIndex];
}

void cycleTimezone(int delta) {
  timezoneIndex += delta;
  if (timezoneIndex < 0) timezoneIndex = TIMEZONE_COUNT - 1;
  if (timezoneIndex >= TIMEZONE_COUNT) timezoneIndex = 0;
  wifiTimeConfigured = false;
  wifiTimeSynced = false;
  if (clockUseInternetTime && wifiConnected) {
    beginInternetTimeSync();
  }
  markSettingsDirty();
}

const char* backgroundModeName() {
  switch (backgroundMode) {
    case BACKGROUND_BLACK:
      return "Black";
    case BACKGROUND_BLUE_GRADIENT:
      return "Blue Fade";
    case BACKGROUND_PURPLE_GRADIENT:
      return "Purple Fade";
    case BACKGROUND_FLOWERS:
      return "Flowers";
    default:
      return "Background";
  }
}

void cycleBackgroundMode(int delta) {
  int next = (int)backgroundMode + delta;
  if (next < 0) next = BACKGROUND_MODE_COUNT - 1;
  if (next >= BACKGROUND_MODE_COUNT) next = 0;
  backgroundMode = (BackgroundMode)next;
  markSettingsDirty();
}

int color5To8(int v5) { return (v5 << 3) | (v5 >> 2); }
int color6To8(int v6) { return (v6 << 2) | (v6 >> 4); }

int bayer8Threshold(int x, int y, int scale) {
  static const uint8_t kBayer8x8[64] = {
      0, 48, 12, 60, 3, 51, 15, 63,
      32, 16, 44, 28, 35, 19, 47, 31,
      8, 56, 4, 52, 11, 59, 7, 55,
      40, 24, 36, 20, 43, 27, 39, 23,
      2, 50, 14, 62, 1, 49, 13, 61,
      34, 18, 46, 30, 33, 17, 45, 29,
      10, 58, 6, 54, 9, 57, 5, 53,
      42, 26, 38, 22, 41, 25, 37, 21};
  int sx = x / scale;
  int sy = y / scale;
  return kBayer8x8[(sy & 7) * 8 + (sx & 7)] << 2;
}

void gradientRgbAtT(const uint16_t* colors, const uint8_t* stops, int count, int t255, int& r8, int& g8, int& b8) {
  if (count <= 0) {
    r8 = g8 = b8 = 0;
    return;
  }
  if (t255 <= stops[0]) {
    r8 = color5To8((colors[0] >> 11) & 0x1F);
    g8 = color6To8((colors[0] >> 5) & 0x3F);
    b8 = color5To8(colors[0] & 0x1F);
    return;
  }
  if (t255 >= stops[count - 1]) {
    r8 = color5To8((colors[count - 1] >> 11) & 0x1F);
    g8 = color6To8((colors[count - 1] >> 5) & 0x3F);
    b8 = color5To8(colors[count - 1] & 0x1F);
    return;
  }

  for (int i = 1; i < count; ++i) {
    if (t255 <= stops[i]) {
      int t0 = stops[i - 1];
      int t1 = stops[i];
      int seg = t1 - t0;
      int blend = (seg > 0) ? ((t255 - t0) * 255) / seg : 255;
      int inv = 255 - blend;
      int c0r = color5To8((colors[i - 1] >> 11) & 0x1F);
      int c0g = color6To8((colors[i - 1] >> 5) & 0x3F);
      int c0b = color5To8(colors[i - 1] & 0x1F);
      int c1r = color5To8((colors[i] >> 11) & 0x1F);
      int c1g = color6To8((colors[i] >> 5) & 0x3F);
      int c1b = color5To8(colors[i] & 0x1F);
      r8 = (c0r * inv + c1r * blend) / 255;
      g8 = (c0g * inv + c1g * blend) / 255;
      b8 = (c0b * inv + c1b * blend) / 255;
      return;
    }
  }
}

uint16_t rgb565From888(int r8, int g8, int b8) {
  return RGB565((uint8_t)clampVal(r8, 0, 255), (uint8_t)clampVal(g8, 0, 255), (uint8_t)clampVal(b8, 0, 255));
}

uint16_t swap565(uint16_t color) {
  return (uint16_t)((color << 8) | (color >> 8));
}

void drawVerticalGradientStops(TFT_eSprite& s, const uint16_t* colors, const uint8_t* stops, int stopCount, int gradientHeight,
                               int ditherScale, int ditherAmplitude) {
  int drawH = clampVal(gradientHeight, 2, SCREEN_H);
  int yMax = drawH - 1;
  for (int y = 0; y < drawH; ++y) {
    int baseT255 = (y * 255) / yMax;

    for (int x = 0; x < SCREEN_W; ++x) {
      int threshold = bayer8Threshold(x, y, ditherScale) - 128;
      int sampleT255 = clampVal(baseT255 + (threshold * ditherAmplitude) / 128, 0, 255);
      int r8, g8, b8;
      gradientRgbAtT(colors, stops, stopCount, sampleT255, r8, g8, b8);
      s.drawPixel(x, y, rgb565From888(r8, g8, b8));
    }
  }
}

void buildGradientBandCache(const uint16_t* colors, const uint8_t* stops, int stopCount, int ditherScale, int ditherAmplitude) {
  for (int y = 0; y < BACKGROUND_GRADIENT_H; ++y) {
    int baseT255 = (y * 255) / (BACKGROUND_GRADIENT_H - 1);
    for (int x = 0; x < SCREEN_W; ++x) {
      int threshold = bayer8Threshold(x, y, ditherScale) - 128;
      int sampleT255 = clampVal(baseT255 + (threshold * ditherAmplitude) / 128, 0, 255);
      int r8, g8, b8;
      gradientRgbAtT(colors, stops, stopCount, sampleT255, r8, g8, b8);
      gradientBandCache[y * SCREEN_W + x] = swap565(rgb565From888(r8, g8, b8));
    }
  }
}

void drawTopGradientBackground(TFT_eSprite& s, const uint16_t* colors, const uint8_t* stops, int stopCount) {
  s.fillSprite(BG_COLOR);
  drawVerticalGradientStops(s, colors, stops, stopCount, BACKGROUND_GRADIENT_H, 4, 28);
}

void drawCachedTopGradientBackground(TFT_eSprite& s, BackgroundMode mode, const uint16_t* colors, const uint8_t* stops,
                                     int stopCount) {
  if (gradientBandCacheMode != mode) {
    buildGradientBandCache(colors, stops, stopCount, 4, 28);
    gradientBandCacheMode = mode;
  }
  s.fillSprite(BG_COLOR);
  s.pushImage(0, 0, SCREEN_W, BACKGROUND_GRADIENT_H, gradientBandCache);
}

struct PixelFlowerSpec {
  int cx;
  int cy;
  int radius;
  float rotation;
  uint16_t color;
};

struct PixelFlowerPoint {
  int16_t x;
  int16_t y;
};

static const PixelFlowerSpec kDefaultPixelFlowers[] = {
    {70, 70, 58, 6.28318f, RGB565(0, 26, 76)},
    {248, 72, 58, 6.82318f, RGB565(0, 22, 66)},
    {202, 156, 28, 3.14159f, RGB565(116, 108, 18)},
};
static PixelFlowerSpec pixelFlowers[sizeof(kDefaultPixelFlowers) / sizeof(kDefaultPixelFlowers[0])];
static constexpr int kPixelFlowerCount = sizeof(pixelFlowers) / sizeof(pixelFlowers[0]);
static const int PIXEL_FLOWER_SEGMENTS = 80;
static PixelFlowerPoint pixelFlowerPoints[kPixelFlowerCount][PIXEL_FLOWER_SEGMENTS + 1];
static bool pixelFlowerGeometryDirty = true;

void savePersistentState() {
  prefs.begin("ascii-aq", false);
  prefs.putUChar("ver", 3);
  prefs.putInt("fish", fishTargetCount);
  prefs.putInt("bubbles", bubbleTargetCount);
  prefs.putInt("oct_freq", octopusFrequency);
  prefs.putInt("seah_freq", seahorseFrequency);
  prefs.putFloat("sway", seaweedSwaySpeed);
  prefs.putFloat("sea_len", seaweedLength);
  prefs.putFloat("sea_rand", seaweedLengthRandomness);
  prefs.putUChar("bg_mode", (uint8_t)backgroundMode);
  prefs.putBool("clock_on", clockVisible);
  prefs.putBool("clock_24h", clockUse24Hour);
  prefs.putBool("clock_net", clockUseInternetTime);
  prefs.putUChar("clk_style", (uint8_t)clockDisplayStyle);
  prefs.putUChar("clk_pos", (uint8_t)clockSmallPosition);
  prefs.putBool("clk_flip", clockFlipHorizontal);
  prefs.putUShort("clk_s_col", clockSmallTextColor);
  prefs.putUShort("clk_a_col", clockAsciiTextColor);
  prefs.putInt("tz_idx", timezoneIndex);
  prefs.putInt("clk_year", clockYear);
  prefs.putInt("clk_month", clockMonth);
  prefs.putInt("clk_day", clockDay);
  prefs.putInt("clk_hour", clockHour);
  prefs.putInt("clk_min", clockMinute);
  prefs.putBool("wifi_on", wifiEnabled);
  prefs.putString("wifi_ssid", wifiSsid);
  prefs.putString("wifi_pass", wifiPass);
  prefs.putBytes("flowers", pixelFlowers, sizeof(pixelFlowers));
  prefs.end();
  settingsDirty = false;
  lastSettingsSaveMs = millis();
}

void loadPersistentState() {
  memcpy(pixelFlowers, kDefaultPixelFlowers, sizeof(pixelFlowers));
  wifiSsid[0] = '\0';
  wifiPass[0] = '\0';

  prefs.begin("ascii-aq", true);
  uint8_t version = prefs.getUChar("ver", 0);
  if (version != 0) {
    fishTargetCount = prefs.getInt("fish", DEFAULT_FISH);
    bubbleTargetCount = prefs.getInt("bubbles", DEFAULT_BUBBLES);
    octopusFrequency = prefs.getInt("oct_freq", DEFAULT_OCTOPUS_FREQUENCY);
    seahorseFrequency = prefs.getInt("seah_freq", DEFAULT_SEAHORSE_FREQUENCY);
    if (version < 2 && seahorseFrequency == 2) {
      seahorseFrequency = DEFAULT_SEAHORSE_FREQUENCY;
    }
    seaweedSwaySpeed = prefs.getFloat("sway", DEFAULT_SWAY);
    seaweedLength = prefs.getFloat("sea_len", DEFAULT_SEAWEED_LENGTH);
    seaweedLengthRandomness = prefs.getFloat("sea_rand", DEFAULT_SEAWEED_LENGTH_RANDOMNESS);
    backgroundMode = (BackgroundMode)prefs.getUChar("bg_mode", (uint8_t)DEFAULT_BACKGROUND_MODE);
    clockVisible = prefs.getBool("clock_on", false);
    clockUse24Hour = prefs.getBool("clock_24h", false);
    clockUseInternetTime = prefs.getBool("clock_net", false);
    clockDisplayStyle = (ClockDisplayStyle)prefs.getUChar("clk_style", (uint8_t)CLOCK_STYLE_SMALL_TEXT);
    clockSmallPosition = (ClockSmallPosition)prefs.getUChar("clk_pos", (uint8_t)CLOCK_SMALL_TOP);
    clockFlipHorizontal = prefs.getBool("clk_flip", false);
    clockSmallTextColor = prefs.getUShort("clk_s_col", DEFAULT_SMALL_CLOCK_COLOR);
    clockAsciiTextColor = prefs.getUShort("clk_a_col", DEFAULT_ASCII_CLOCK_COLOR);
    timezoneIndex = prefs.getInt("tz_idx", DEFAULT_TIMEZONE_INDEX);
    clockYear = prefs.getInt("clk_year", DEFAULT_CLOCK_YEAR);
    clockMonth = prefs.getInt("clk_month", DEFAULT_CLOCK_MONTH);
    clockDay = prefs.getInt("clk_day", DEFAULT_CLOCK_DAY);
    clockHour = prefs.getInt("clk_hour", DEFAULT_CLOCK_HOUR);
    clockMinute = prefs.getInt("clk_min", DEFAULT_CLOCK_MINUTE);
    wifiEnabled = prefs.getBool("wifi_on", false);
    prefs.getString("wifi_ssid", wifiSsid, sizeof(wifiSsid));
    prefs.getString("wifi_pass", wifiPass, sizeof(wifiPass));
    size_t flowerBytes = prefs.getBytesLength("flowers");
    if (flowerBytes == sizeof(pixelFlowers)) {
      prefs.getBytes("flowers", pixelFlowers, sizeof(pixelFlowers));
    }
  }
  prefs.end();

  fishTargetCount = clampVal(fishTargetCount, MIN_FISH, MAX_FISH);
  bubbleTargetCount = clampVal(bubbleTargetCount, MIN_BUBBLES, MAX_BUBBLES);
  octopusFrequency = normalizeOctopusFrequency(octopusFrequency);
  seahorseFrequency = normalizeSeahorseFrequency(seahorseFrequency);
  seaweedSwaySpeed = clampVal(seaweedSwaySpeed, MIN_SWAY, MAX_SWAY);
  seaweedLength = clampVal(seaweedLength, MIN_SEAWEED_LENGTH, MAX_SEAWEED_LENGTH);
  seaweedLengthRandomness = clampVal(seaweedLengthRandomness, MIN_SEAWEED_LENGTH_RANDOMNESS, MAX_SEAWEED_LENGTH_RANDOMNESS);
  if ((int)backgroundMode < 0 || backgroundMode >= BACKGROUND_MODE_COUNT) backgroundMode = DEFAULT_BACKGROUND_MODE;
  if ((int)clockDisplayStyle < 0 || clockDisplayStyle >= CLOCK_STYLE_COUNT) clockDisplayStyle = CLOCK_STYLE_SMALL_TEXT;
  if ((int)clockSmallPosition < 0 || clockSmallPosition >= CLOCK_SMALL_POSITION_COUNT) clockSmallPosition = CLOCK_SMALL_TOP;
  timezoneIndex = clampVal(timezoneIndex, 0, TIMEZONE_COUNT - 1);
  if (!wifiEnabled) clockUseInternetTime = false;
  normalizeClockDate();
  gradientBandCacheMode = BACKGROUND_MODE_COUNT;
  pixelFlowerGeometryDirty = true;
  settingsDirty = false;
}

void serviceSettingsPersistence(unsigned long now) {
  if (settingsDirty && now - settingsDirtyMs >= SETTINGS_SAVE_DELAY_MS) {
    savePersistentState();
    return;
  }
  if (now - lastSettingsSaveMs >= CLOCK_AUTOSAVE_INTERVAL_MS) {
    savePersistentState();
  }
}

void setWifiStatus(const char* text) {
  copySafe(wifiStatusText, sizeof(wifiStatusText), text);
}

const char* internetTimeStatus() {
  if (!clockUseInternetTime) return "Manual";
  if (!wifiEnabled) return "WiFi Off";
  if (!wifiConnected) return wifiConnecting ? "Connecting" : "Waiting WiFi";
  return wifiTimeSynced ? "Synced" : "Syncing";
}

void ensureWifiRadioStarted() {
  if (wifiRadioStarted) return;
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  wifiRadioStarted = true;
}

void clearWifiScanResults() {
  wifiNetworkCount = 0;
  wifiNetworkPage = 0;
  for (int i = 0; i < MAX_WIFI_NETWORKS; ++i) {
    wifiNetworkNames[i][0] = '\0';
    wifiNetworkRssi[i] = 0;
    wifiNetworkOpen[i] = false;
  }
}

bool wifiSsidAlreadyListed(const char* ssid) {
  for (int i = 0; i < wifiNetworkCount; ++i) {
    if (strncmp(wifiNetworkNames[i], ssid, WIFI_SSID_MAX_LEN) == 0) return true;
  }
  return false;
}

void startWifiScan() {
  if (!wifiEnabled) return;
  ensureWifiRadioStarted();
  if (wifiConnecting) {
    wifiConnecting = false;
    wifiSavePendingCredentials = false;
    WiFi.disconnect(false);
  }
  clearWifiScanResults();
  WiFi.scanDelete();
  WiFi.scanNetworks(true, true);
  wifiScanInProgress = true;
  setWifiStatus("Scanning...");
}

void finishWifiScanIfReady() {
  if (!wifiScanInProgress) return;
  int scanResult = WiFi.scanComplete();
  if (scanResult == WIFI_SCAN_RUNNING) return;

  wifiScanInProgress = false;
  clearWifiScanResults();
  if (scanResult < 0) {
    setWifiStatus("Scan failed");
    WiFi.scanDelete();
    return;
  }

  for (int i = 0; i < scanResult && wifiNetworkCount < MAX_WIFI_NETWORKS; ++i) {
    String ssid = WiFi.SSID(i);
    if (ssid.length() == 0) continue;
    if (wifiSsidAlreadyListed(ssid.c_str())) continue;

    copySafe(wifiNetworkNames[wifiNetworkCount], sizeof(wifiNetworkNames[wifiNetworkCount]), ssid.c_str());
    wifiNetworkRssi[wifiNetworkCount] = WiFi.RSSI(i);
    wifiNetworkOpen[wifiNetworkCount] = (WiFi.encryptionType(i) == WIFI_AUTH_OPEN);
    wifiNetworkCount++;
  }

  WiFi.scanDelete();
  setWifiStatus(wifiNetworkCount > 0 ? "Select network" : "No networks found");
}

void beginInternetTimeSync() {
  if (!wifiConnected) return;
  const TimezoneOption& tz = currentTimezone();
  configTzTime(tz.posix, CLOCK_NTP_1, CLOCK_NTP_2, CLOCK_NTP_3);
  wifiTimeConfigured = true;
  wifiLastNtpAttemptMs = 0;
  wifiTimeSynced = false;
}

bool syncClockFromSystemTime(bool markDirty) {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 10)) return false;

  clockYear = timeInfo.tm_year + 1900;
  clockMonth = timeInfo.tm_mon + 1;
  clockDay = timeInfo.tm_mday;
  clockHour = timeInfo.tm_hour;
  clockMinute = timeInfo.tm_min;
  normalizeClockDate();
  unsigned long now = millis();
  unsigned long secondOffsetMs = (unsigned long)clampVal(timeInfo.tm_sec, 0, 59) * 1000UL;
  clockLastMinuteMs = (now > secondOffsetMs) ? (now - secondOffsetMs) : now;
  wifiTimeSynced = true;
  wifiLastNtpSyncMs = now;
  if (markDirty) markSettingsDirty();
  return true;
}

void startWifiConnect(const char* ssid, const char* pass, bool savePendingCredentials) {
  if (!wifiEnabled || !ssid || ssid[0] == '\0') return;
  ensureWifiRadioStarted();
  copySafe(pendingWifiSsid, sizeof(pendingWifiSsid), ssid);
  copySafe(pendingWifiPass, sizeof(pendingWifiPass), pass ? pass : "");
  wifiSavePendingCredentials = savePendingCredentials;
  wifiConnecting = true;
  wifiConnected = false;
  wifiConnectionFailed = false;
  wifiTimeSynced = false;
  wifiConnectStartMs = millis();
  wifiLastReconnectMs = wifiConnectStartMs;
  WiFi.disconnect(false);
  WiFi.begin(pendingWifiSsid, pendingWifiPass);
  setWifiStatus("Connecting...");
}

void setWifiEnabled(bool enabled) {
  if (wifiEnabled == enabled && enabled) {
    if (wifiSsid[0] != '\0' && !wifiConnected && !wifiConnecting) {
      startWifiConnect(wifiSsid, wifiPass, false);
    } else if (wifiSsid[0] == '\0' && !wifiScanInProgress) {
      startWifiScan();
    }
    return;
  }

  wifiEnabled = enabled;
  if (!wifiEnabled) {
    wifiScanInProgress = false;
    wifiConnecting = false;
    wifiConnected = false;
    wifiConnectionFailed = false;
    wifiSavePendingCredentials = false;
    wifiTimeConfigured = false;
    wifiTimeSynced = false;
    clockUseInternetTime = false;
    pendingWifiSsid[0] = '\0';
    pendingWifiPass[0] = '\0';
    clearWifiScanResults();
    WiFi.scanDelete();
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    wifiRadioStarted = false;
    setWifiStatus("Off");
    markSettingsDirty();
    return;
  }

  ensureWifiRadioStarted();
  setWifiStatus("Starting...");
  markSettingsDirty();
  if (wifiSsid[0] != '\0') {
    startWifiConnect(wifiSsid, wifiPass, false);
  } else {
    startWifiScan();
  }
}

void serviceInternetTime(unsigned long now) {
  if (!clockUseInternetTime || !wifiConnected) return;
  if (!wifiTimeConfigured) beginInternetTimeSync();

  bool needsRetry = !wifiTimeSynced && (wifiLastNtpAttemptMs == 0 || now - wifiLastNtpAttemptMs >= NTP_RETRY_MS);
  bool needsRefresh = wifiTimeSynced && (now - wifiLastNtpSyncMs >= NTP_REFRESH_MS);
  if (!needsRetry && !needsRefresh) return;

  wifiLastNtpAttemptMs = now;
  if (syncClockFromSystemTime(true)) {
    setWifiStatus("Connected");
  }
}

void serviceWifi(unsigned long now) {
  if (!wifiEnabled) return;
  ensureWifiRadioStarted();
  finishWifiScanIfReady();

  bool connectedNow = (WiFi.status() == WL_CONNECTED);
  if (connectedNow) {
    if (!wifiConnected) {
      wifiConnected = true;
      wifiConnecting = false;
      wifiConnectionFailed = false;
      if (wifiSavePendingCredentials) {
        copySafe(wifiSsid, sizeof(wifiSsid), pendingWifiSsid);
        copySafe(wifiPass, sizeof(wifiPass), pendingWifiPass);
        wifiSavePendingCredentials = false;
      }
      clockUseInternetTime = true;
      beginInternetTimeSync();
      setWifiStatus("Connected");
      savePersistentState();
    }
    serviceInternetTime(now);
    return;
  }

  if (wifiConnected) {
    wifiConnected = false;
    wifiTimeConfigured = false;
    wifiTimeSynced = false;
    setWifiStatus("Disconnected");
  }

  if (wifiConnecting) {
    if (now - wifiConnectStartMs >= WIFI_CONNECT_TIMEOUT_MS) {
      wifiConnecting = false;
      wifiConnectionFailed = true;
      wifiSavePendingCredentials = false;
      WiFi.disconnect(false);
      setWifiStatus("Connect failed");
    }
    return;
  }

  if (wifiSsid[0] != '\0' && (wifiLastReconnectMs == 0 || now - wifiLastReconnectMs >= WIFI_RECONNECT_DELAY_MS)) {
    startWifiConnect(wifiSsid, wifiPass, false);
  } else if (wifiSsid[0] == '\0' && !wifiScanInProgress && wifiNetworkCount == 0) {
    startWifiScan();
  }
}

uint16_t randomFlowerColor(int index) {
  if (index == kPixelFlowerCount - 1) {
    return RGB565((uint8_t)random(92, 146), (uint8_t)random(84, 126), (uint8_t)random(8, 28));
  }
  return RGB565((uint8_t)random(0, 10), (uint8_t)random(18, 38), (uint8_t)random(46, 96));
}

void randomizeFlowers() {
  pixelFlowers[0].cx = random(42, 98);
  pixelFlowers[0].cy = random(50, 86);
  pixelFlowers[0].radius = random(50, 63);
  pixelFlowers[0].rotation = frand(0.0f, 6.28318f);
  pixelFlowers[0].color = randomFlowerColor(0);

  pixelFlowers[1].cx = random(214, 278);
  pixelFlowers[1].cy = random(48, 90);
  pixelFlowers[1].radius = random(50, 63);
  pixelFlowers[1].rotation = frand(0.0f, 6.28318f);
  pixelFlowers[1].color = randomFlowerColor(1);

  pixelFlowers[2].cx = random(162, 248);
  pixelFlowers[2].cy = random(124, SEA_LEVEL_Y - 18);
  pixelFlowers[2].radius = random(20, 34);
  pixelFlowers[2].rotation = frand(0.0f, 6.28318f);
  pixelFlowers[2].color = randomFlowerColor(2);
  pixelFlowerGeometryDirty = true;
  markSettingsDirty();
}

void drawThickLine(TFT_eSprite& s, int x0, int y0, int x1, int y1, uint16_t color) {
  s.drawLine(x0, y0, x1, y1, color);
  s.drawLine(x0 + 1, y0, x1 + 1, y1, color);
  s.drawLine(x0, y0 + 1, x1, y1 + 1, color);
  s.drawLine(x0 - 1, y0, x1 - 1, y1, color);
  s.drawLine(x0, y0 - 1, x1, y1 - 1, color);
}

void drawActionRow(TFT_eSprite& s, int rowY, const char* label, const char* actionLabel) {
  const int centerY = rowY + SETTINGS_BUTTON_H / 2;
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, SETTINGS_PANEL_X + 12, centerY);
  drawButton(s, SETTINGS_ACTION_X, rowY, SETTINGS_ACTION_W, SETTINGS_BUTTON_H, actionLabel, TFT_CYAN, TFT_DARKGREEN);
}

void rebuildPixelFlowerGeometry() {
  if (!pixelFlowerGeometryDirty) return;

  for (int flowerIndex = 0; flowerIndex < kPixelFlowerCount; ++flowerIndex) {
    const PixelFlowerSpec& flower = pixelFlowers[flowerIndex];
    for (int i = 0; i <= PIXEL_FLOWER_SEGMENTS; ++i) {
      float theta = flower.rotation + (6.28318f * i) / PIXEL_FLOWER_SEGMENTS;
      float petal = 0.5f + 0.5f * sinf(theta * 5.0f);
      float r = flower.radius * (0.58f + 0.42f * petal);
      pixelFlowerPoints[flowerIndex][i].x = (int16_t)(flower.cx + (int)(cosf(theta) * r));
      pixelFlowerPoints[flowerIndex][i].y = (int16_t)(flower.cy + (int)(sinf(theta) * r));
    }
  }

  pixelFlowerGeometryDirty = false;
}

void drawPixelFlower(TFT_eSprite& s, int flowerIndex, uint16_t color) {
  for (int i = 1; i <= PIXEL_FLOWER_SEGMENTS; ++i) {
    const PixelFlowerPoint& prev = pixelFlowerPoints[flowerIndex][i - 1];
    const PixelFlowerPoint& point = pixelFlowerPoints[flowerIndex][i];
    drawThickLine(s, prev.x, prev.y, point.x, point.y, color);
  }
}

void drawFlowerBackground(TFT_eSprite& s) {
  s.fillSprite(BG_COLOR);
  rebuildPixelFlowerGeometry();
  for (int i = 0; i < kPixelFlowerCount; ++i) {
    drawPixelFlower(s, i, pixelFlowers[i].color);
  }
}

void drawBackground(TFT_eSprite& s, float tSec) {
  (void)tSec;
  static const uint8_t kGradientStops[] = {0, 18, 42, 74, 112, 156, 204, 232, 255};
  static const uint16_t kBlueGradientColors[] = {
      RGB565(0, 8, 255),
      RGB565(0, 6, 228),
      RGB565(0, 5, 198),
      RGB565(0, 4, 164),
      RGB565(0, 3, 126),
      RGB565(0, 2, 90),
      RGB565(0, 1, 58),
      RGB565(0, 0, 30),
      BG_COLOR,
  };
  static const uint16_t kPurpleGradientColors[] = {
      RGB565(108, 6, 220),
      RGB565(92, 4, 194),
      RGB565(74, 3, 166),
      RGB565(58, 2, 136),
      RGB565(42, 2, 104),
      RGB565(28, 1, 72),
      RGB565(18, 0, 46),
      RGB565(8, 0, 22),
      BG_COLOR,
  };
  switch (backgroundMode) {
    case BACKGROUND_BLACK:
      s.fillSprite(BG_COLOR);
      break;
    case BACKGROUND_BLUE_GRADIENT:
      drawCachedTopGradientBackground(s, BACKGROUND_BLUE_GRADIENT, kBlueGradientColors, kGradientStops, 9);
      break;
    case BACKGROUND_PURPLE_GRADIENT:
      drawCachedTopGradientBackground(s, BACKGROUND_PURPLE_GRADIENT, kPurpleGradientColors, kGradientStops, 9);
      break;
    case BACKGROUND_FLOWERS:
      drawFlowerBackground(s);
      break;
    default:
      s.fillSprite(BG_COLOR);
      break;
  }
}

// ------------------------------ Aquarium Logic -------------------------------
void spawnFlake(float x, float y) {
  for (int i = 0; i < MAX_FLAKES; i++) {
    if (!flakes[i].active) {
      flakes[i].active = true;
      flakes[i].x = x;
      flakes[i].y = y;
      flakes[i].vy = frand(22.0f, 48.0f);
      flakes[i].color = randomFoodColor();
      return;
    }
  }
}

float randomFishDepthBrightness() {
  int roll = random(100);
  if (roll < 28) return frand(0.48f, 0.64f);
  if (roll < 70) return frand(0.66f, 0.84f);
  return frand(0.88f, 1.0f);
}

void refreshFishRenderColor(Fish& f) {
  f.renderColor = scaleRgb565(f.displayColor, f.depthBrightness);
}

void refreshFishDepth(Fish& f) {
  f.depthBrightness = randomFishDepthBrightness();
  refreshFishRenderColor(f);
}

void activateFish(Fish& f, bool activeNow) {
  f.active = activeNow;
  if (!activeNow) return;
  f.type = random(0, GLYPH_COUNT);
  int rightWidth = fishGlyphWidthRight[f.type];
  int leftWidth = fishGlyphWidthLeft[f.type];
  f.visualWidth = (rightWidth > leftWidth) ? rightWidth : leftWidth;
  if (f.visualWidth <= 0) f.visualWidth = (int)strlen(fishSpecies[f.type].right) * 12;
  f.displayColor = fishSpecies[f.type].baseColor;
  if (random(100) < 20) {
    f.displayColor = kAltFishColors[random(0, kAltFishColorCount)];
  }
  refreshFishDepth(f);
  f.x = frand(-42, SCREEN_W + 12);  // allow natural side entry
  f.y = frand(20, SEA_LEVEL_Y - 10);
  f.vx = frand(-1.0f, 1.0f);
  f.vy = frand(-0.5f, 0.5f);
  f.speed = frand(14.0f, 30.0f);
  f.phase = frand(0.0f, 6.28318f);
  f.wanderBias = frand(0.4f, 1.3f);
}

void applyFishPopulation() {
  fishTargetCount = clampVal(fishTargetCount, MIN_FISH, MAX_FISH);
  for (int i = 0; i < MAX_FISH_POOL; i++) {
    bool shouldBeActive = (i < fishTargetCount);
    if (shouldBeActive && !fishPool[i].active) activateFish(fishPool[i], true);
    if (!shouldBeActive && fishPool[i].active) fishPool[i].active = false;
  }
}

bool fishSpawnClear(int fishIndex, float x, float y, float minGapX, float minGapY) {
  Fish& f = fishPool[fishIndex];
  float centerX = x + f.visualWidth * 0.5f;
  float centerY = y + FISH_CENTER_Y_OFFSET;
  int fishCount = activeFishLimit();
  for (int i = 0; i < fishCount; ++i) {
    if (i == fishIndex || !fishPool[i].active) continue;
    Fish& other = fishPool[i];
    float otherCenterX = other.x + other.visualWidth * 0.5f;
    float otherCenterY = other.y + FISH_CENTER_Y_OFFSET;
    if (fabsf(otherCenterX - centerX) < minGapX && fabsf(otherCenterY - centerY) < minGapY) return false;
  }
  return true;
}

void spreadInitialFishLayout() {
  int fishCount = activeFishLimit();
  float minGapX = FISH_AVOID_RADIUS_X * 0.92f;
  float minGapY = FISH_AVOID_RADIUS_Y * 1.05f;
  for (int i = 0; i < fishCount; ++i) {
    Fish& f = fishPool[i];
    if (!f.active) continue;

    float bestX = f.x;
    float bestY = f.y;
    bool placed = false;
    for (int attempt = 0; attempt < 80; ++attempt) {
      float candidateX = frand(10.0f, SCREEN_W - f.visualWidth - 10.0f);
      float candidateY = frand(18.0f, SEA_LEVEL_Y - 18.0f);
      bestX = candidateX;
      bestY = candidateY;
      if (fishSpawnClear(i, candidateX, candidateY, minGapX, minGapY)) {
        placed = true;
        break;
      }
    }

    f.x = bestX;
    f.y = bestY;
    if (!placed) {
      f.y = clampVal(f.y + frand(-8.0f, 8.0f), 18.0f, (float)SEA_LEVEL_Y - 18.0f);
    }
    f.vx = (random(100) < 50) ? -1.0f : 1.0f;
    f.vy = frand(-0.22f, 0.22f);
  }
}

void respawnFishPopulation() {
  fishTargetCount = clampVal(fishTargetCount, MIN_FISH, MAX_FISH);
  int fishCount = activeFishLimit();
  for (int i = 0; i < MAX_FISH_POOL; ++i) {
    activateFish(fishPool[i], i < fishCount);
  }
  spreadInitialFishLayout();
}

void resetBubble(Bubble& b, bool spreadOut) {
  b.active = true;
  b.baseX = frand(8.0f, SCREEN_W - 8.0f);
  b.x = b.baseX;
  b.y = spreadOut ? frand(4.0f, SCREEN_H + 48.0f) : frand(SCREEN_H - 4.0f, SCREEN_H + 48.0f);
  b.vy = frand(12.0f, 28.0f);
  b.phase = frand(0.0f, 6.28318f);
  b.swayAmp = frand(2.0f, 7.0f);
  b.color = randomBubbleColor();
}

void applyBubblePopulation(bool spreadNew = false) {
  bubbleTargetCount = clampVal(bubbleTargetCount, MIN_BUBBLES, MAX_BUBBLES);
  for (int i = 0; i < MAX_BUBBLES; i++) {
    bool shouldBeActive = (i < bubbleTargetCount);
    if (shouldBeActive && !bubbles[i].active) resetBubble(bubbles[i], spreadNew);
    if (!shouldBeActive && bubbles[i].active) bubbles[i].active = false;
  }
}

void updateFlakes(float dt) {
  float t = aquariumTimeSec();
  for (int i = 0; i < MAX_FLAKES; i++) {
    if (!flakes[i].active) continue;
    flakes[i].y += flakes[i].vy * dt;
    flakes[i].x += sinf(t * 1.2f + i) * 8.0f * dt;
    if (flakes[i].y > SEA_LEVEL_Y) flakes[i].active = false;
  }
}

void updateBubbles(float dt) {
  float t = aquariumTimeSec();
  int bubbleCount = activeBubbleLimit();
  for (int i = 0; i < bubbleCount; i++) {
    if (!bubbles[i].active) continue;
    bubbles[i].y -= bubbles[i].vy * dt;
    bubbles[i].x = bubbles[i].baseX + sinf(t * 1.8f + bubbles[i].phase) * bubbles[i].swayAmp;
    if (bubbles[i].y < -10.0f) resetBubble(bubbles[i], false);
  }
}

int closestFlakeForFish(const Fish& f, float maxDist) {
  int best = -1;
  float bestD2 = maxDist * maxDist;
  for (int i = 0; i < MAX_FLAKES; i++) {
    if (!flakes[i].active) continue;
    float dx = flakes[i].x - f.x;
    float dy = flakes[i].y - f.y;
    float d2 = dx * dx + dy * dy;
    if (d2 < bestD2) {
      bestD2 = d2;
      best = i;
    }
  }
  return best;
}

void steerFishAwayFromOctopus(Fish& f, float fishCenterX, float fishCenterY, float dt) {
  if (!octopus.active) return;

  float dx = fishCenterX - octopus.x;
  float dy = fishCenterY - (octopus.y + OCTOPUS_CENTER_Y_OFFSET);
  float sx = dx / OCTOPUS_FISH_AVOID_RADIUS_X;
  float sy = dy / OCTOPUS_FISH_AVOID_RADIUS_Y;
  float scaledD2 = sx * sx + sy * sy;
  if (scaledD2 <= 0.0001f || scaledD2 >= 1.0f) return;

  float dist = sqrtf(dx * dx + dy * dy) + 0.0001f;
  float push = 1.0f - scaledD2;
  push *= push;
  f.vx += (dx / dist) * push * OCTOPUS_FISH_AVOID_STRENGTH * dt;
  f.vy += (dy / dist) * push * OCTOPUS_FISH_AVOID_STRENGTH * dt;
}

void steerFishAwayFromSeahorse(Fish& f, float fishCenterX, float fishCenterY, float dt) {
  if (!seahorse.active) return;

  float horseCenterX = seahorse.x + SEAHORSE_CENTER_X_OFFSET;
  float horseCenterY = seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
  float dx = fishCenterX - horseCenterX;
  float dy = fishCenterY - horseCenterY;
  float sx = dx / SEAHORSE_FISH_AVOID_RADIUS_X;
  float sy = dy / SEAHORSE_FISH_AVOID_RADIUS_Y;
  float scaledD2 = sx * sx + sy * sy;
  if (scaledD2 <= 0.0001f || scaledD2 >= 1.0f) return;

  float dist = sqrtf(dx * dx + dy * dy) + 0.0001f;
  float push = 1.0f - scaledD2;
  push *= push;
  f.vx += (dx / dist) * push * SEAHORSE_FISH_AVOID_STRENGTH * dt;
  f.vy += (dy / dist) * push * SEAHORSE_FISH_AVOID_STRENGTH * dt;
}

void keepFishOutsideOctopus(Fish& f) {
  if (!octopus.active) return;

  float fishCenterX = f.x + f.visualWidth * 0.5f;
  float fishCenterY = f.y + FISH_CENTER_Y_OFFSET;
  float octoCenterY = octopus.y + OCTOPUS_CENTER_Y_OFFSET;
  float dx = fishCenterX - octopus.x;
  float dy = fishCenterY - octoCenterY;
  float sx = dx / OCTOPUS_FISH_CLEAR_RADIUS_X;
  float sy = dy / OCTOPUS_FISH_CLEAR_RADIUS_Y;
  float scaledD2 = sx * sx + sy * sy;
  if (scaledD2 >= 1.0f) return;

  if (scaledD2 <= 0.0001f) {
    dx = (f.vx >= 0.0f) ? 1.0f : -1.0f;
    dy = (f.vy >= 0.0f) ? 0.35f : -0.35f;
    scaledD2 = (dx / OCTOPUS_FISH_CLEAR_RADIUS_X) * (dx / OCTOPUS_FISH_CLEAR_RADIUS_X) +
               (dy / OCTOPUS_FISH_CLEAR_RADIUS_Y) * (dy / OCTOPUS_FISH_CLEAR_RADIUS_Y);
  }

  float scale = 1.0f / sqrtf(scaledD2);
  float targetCenterX = octopus.x + dx * scale;
  float targetCenterY = octoCenterY + dy * scale;
  f.x += (targetCenterX - fishCenterX) * 0.55f;
  f.y += (targetCenterY - fishCenterY) * 0.55f;
}

void keepFishOutsideSeahorse(Fish& f) {
  if (!seahorse.active) return;

  float fishCenterX = f.x + f.visualWidth * 0.5f;
  float fishCenterY = f.y + FISH_CENTER_Y_OFFSET;
  float horseCenterX = seahorse.x + SEAHORSE_CENTER_X_OFFSET;
  float horseCenterY = seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
  float dx = fishCenterX - horseCenterX;
  float dy = fishCenterY - horseCenterY;
  float sx = dx / SEAHORSE_FISH_CLEAR_RADIUS_X;
  float sy = dy / SEAHORSE_FISH_CLEAR_RADIUS_Y;
  float scaledD2 = sx * sx + sy * sy;
  if (scaledD2 >= 1.0f) return;

  if (scaledD2 <= 0.0001f) {
    dx = (f.vx >= 0.0f) ? 1.0f : -1.0f;
    dy = (f.vy >= 0.0f) ? 0.35f : -0.35f;
    scaledD2 = (dx / SEAHORSE_FISH_CLEAR_RADIUS_X) * (dx / SEAHORSE_FISH_CLEAR_RADIUS_X) +
               (dy / SEAHORSE_FISH_CLEAR_RADIUS_Y) * (dy / SEAHORSE_FISH_CLEAR_RADIUS_Y);
  }

  float scale = 1.0f / sqrtf(scaledD2);
  float targetCenterX = horseCenterX + dx * scale;
  float targetCenterY = horseCenterY + dy * scale;
  f.x += (targetCenterX - fishCenterX) * 0.45f;
  f.y += (targetCenterY - fishCenterY) * 0.45f;
}

void updateFish(float dt) {
  const float t = aquariumTimeSec();
  int fishCount = activeFishLimit();
  float centerX[MAX_FISH_POOL];
  float centerY[MAX_FISH_POOL];
  for (int i = 0; i < fishCount; ++i) {
    Fish& f = fishPool[i];
    if (!f.active) continue;
    centerX[i] = f.x + f.visualWidth * 0.5f;
    centerY[i] = f.y + FISH_CENTER_Y_OFFSET;
  }

  for (int i = 0; i < fishCount; i++) {
    Fish& f = fishPool[i];
    if (!f.active) continue;

    // Wander behavior
    float wanderX = cosf(f.phase + t * 0.9f) * 0.45f * f.wanderBias;
    float wanderY = sinf(f.phase * 1.7f + t * 0.7f) * 0.22f;
    f.vx += wanderX * dt;
    f.vy += wanderY * dt;

    // Schooling with same type (alignment + cohesion)
    float avgVX = 0, avgVY = 0, cx = 0, cy = 0;
    int nearCount = 0;
    float repelX = 0.0f;
    float repelY = 0.0f;
    int repelCount = 0;
    float fCenterX = centerX[i];
    float fCenterY = centerY[i];
    for (int j = 0; j < fishCount; j++) {
      if (i == j || !fishPool[j].active) continue;
      Fish& n = fishPool[j];

      float dx = n.x - f.x;
      float dy = n.y - f.y;
      if (n.type == f.type) {
        float d2 = dx * dx + dy * dy;
        if (d2 < 3600.0f) {  // within ~60px
          avgVX += n.vx;
          avgVY += n.vy;
          cx += n.x;
          cy += n.y;
          nearCount++;
        }
      }

      float sdx = centerX[j] - fCenterX;
      float sdy = centerY[j] - fCenterY;
      if (sdx > SCREEN_W * 0.5f) sdx -= SCREEN_W;
      if (sdx < -SCREEN_W * 0.5f) sdx += SCREEN_W;

      float sx = sdx / FISH_AVOID_RADIUS_X;
      float sy = sdy / FISH_AVOID_RADIUS_Y;
      float scaledD2 = sx * sx + sy * sy;
      if (scaledD2 > 0.0001f && scaledD2 < 1.0f) {
        float dist = sqrtf(sdx * sdx + sdy * sdy) + 0.0001f;
        float push = 1.0f - scaledD2;
        push *= push;
        repelX -= (sdx / dist) * push;
        repelY -= (sdy / dist) * push;
        repelCount++;
      }
    }
    if (nearCount > 0) {
      avgVX /= nearCount;
      avgVY /= nearCount;
      cx /= nearCount;
      cy /= nearCount;
      f.vx += (avgVX - f.vx) * 0.45f * dt;
      f.vy += (avgVY - f.vy) * 0.25f * dt;
      f.vx += (cx - f.x) * 0.0018f;
      f.vy += (cy - f.y) * 0.0012f;
    }

    // Feed-seeking behavior
    int fi = closestFlakeForFish(f, 140.0f);
    if (fi >= 0) {
      float dx = flakes[fi].x - f.x;
      float dy = flakes[fi].y - f.y;
      float d = sqrtf(dx * dx + dy * dy) + 0.0001f;
      f.vx += (dx / d) * 0.95f * dt;
      f.vy += (dy / d) * 0.95f * dt;
      if (d < 8.0f) flakes[fi].active = false;  // "eat"
    }

    steerFishAwayFromOctopus(f, fCenterX, fCenterY, dt);
    steerFishAwayFromSeahorse(f, fCenterX, fCenterY, dt);

    // Gentle steering separation, not hard collision.
    if (repelCount > 0) {
      f.vx += (repelX / repelCount) * FISH_AVOID_STRENGTH * dt;
      f.vy += (repelY / repelCount) * FISH_AVOID_STRENGTH * dt;
    }

    // Vertical edge avoidance only (horizontal uses wraparound)
    if (f.y < 18) f.vy += 0.8f * dt;
    if (f.y > SEA_LEVEL_Y - 8) f.vy -= 0.8f * dt;

    // Normalize velocity and apply speed
    float mag = sqrtf(f.vx * f.vx + f.vy * f.vy);
    if (mag < 0.0001f) {
      f.vx = 1.0f;
      f.vy = 0.0f;
      mag = 1.0f;
    }
    f.vx /= mag;
    f.vy /= mag;

    float fishSpeed = f.speed + sinf(t * 3.2f + f.phase) * 4.0f;
    f.x += f.vx * fishSpeed * dt;
    f.y += f.vy * fishSpeed * dt;
    keepFishOutsideOctopus(f);
    keepFishOutsideSeahorse(f);

    // Horizontal wrap keeps fish flowing off-screen and re-entering smoothly
    int w = fishVisualWidth(f);
    float wrapPad = (float)w + 10.0f;
    if (f.x > SCREEN_W + wrapPad) {
      f.x = -wrapPad;
      refreshFishDepth(f);
    }
    if (f.x < -wrapPad) {
      f.x = SCREEN_W + wrapPad;
      refreshFishDepth(f);
    }
    f.y = clampVal(f.y, 14.0f, (float)SEA_LEVEL_Y - 6.0f);
  }
}

bool timeReached(unsigned long now, unsigned long target) {
  return (long)(now - target) >= 0;
}

void scheduleOctopusSpawn(unsigned long now) {
  octopus.nextSpawnMs = now + octopusSpawnIntervalMs();
}

void spawnOctopus(unsigned long now) {
  bool fromLeft = (random(100) < 50);
  octopus.active = true;
  octopus.vx = fromLeft ? frand(4.5f, 8.0f) : -frand(4.5f, 8.0f);
  octopus.x = fromLeft ? -OCTOPUS_EXIT_PAD : (SCREEN_W + OCTOPUS_EXIT_PAD);
  octopus.baseY = frand(36.0f, (float)SEA_LEVEL_Y - 48.0f);
  octopus.y = octopus.baseY;
  octopus.phase = frand(0.0f, 6.28318f);
  octopus.colorPhase = frand(0.0f, 6.28318f);
  scheduleOctopusSpawn(now);
}

void spawnOctopusAtCenter(unsigned long now) {
  octopus.active = true;
  octopus.x = SCREEN_W * 0.5f;
  octopus.baseY = SEA_LEVEL_Y * 0.55f;
  octopus.y = octopus.baseY;
  octopus.vx = (random(100) < 50) ? -frand(3.8f, 6.5f) : frand(3.8f, 6.5f);
  octopus.phase = frand(0.0f, 6.28318f);
  octopus.colorPhase = frand(0.0f, 6.28318f);
  scheduleOctopusSpawn(now);
}

void updateOctopus(unsigned long now, float dt) {
  if (!octopus.active) {
    if (octopus.nextSpawnMs == 0) {
      scheduleOctopusSpawn(now);
    } else if (timeReached(now, octopus.nextSpawnMs)) {
      spawnOctopus(now);
    }
    return;
  }

  float t = now * 0.001f;
  octopus.x += octopus.vx * dt;
  octopus.y = octopus.baseY + sinf(t * 0.45f + octopus.phase) * 6.0f;
  if ((octopus.vx > 0.0f && octopus.x > SCREEN_W + OCTOPUS_EXIT_PAD) ||
      (octopus.vx < 0.0f && octopus.x < -OCTOPUS_EXIT_PAD)) {
    octopus.active = false;
  }
}

void scheduleSeahorseSpawn(unsigned long now) {
  seahorse.nextSpawnMs = now + seahorseSpawnIntervalMs();
}

void spawnSeahorse(unsigned long now) {
  bool fromLeft = (random(100) < 50);
  seahorse.active = true;
  seahorse.facingRight = fromLeft;
  seahorse.vx = fromLeft ? frand(1.6f, 2.9f) * SEAHORSE_SPEED_BOOST
                          : -frand(1.6f, 2.9f) * SEAHORSE_SPEED_BOOST;
  seahorse.x = fromLeft ? -SEAHORSE_EXIT_PAD : (SCREEN_W + SEAHORSE_EXIT_PAD);
  seahorse.baseY = frand(34.0f, (float)SEA_LEVEL_Y - 56.0f);
  seahorse.y = seahorse.baseY;
  seahorse.phase = frand(0.0f, 6.28318f);
  seahorse.finPhase = frand(0.0f, 6.28318f);
  scheduleSeahorseSpawn(now);
}

void spawnSeahorseAtCenter(unsigned long now) {
  seahorse.active = true;
  seahorse.facingRight = (random(100) < 50);
  seahorse.x = SCREEN_W * 0.5f - 16.0f;
  seahorse.baseY = SEA_LEVEL_Y * 0.46f;
  seahorse.y = seahorse.baseY;
  seahorse.vx = seahorse.facingRight ? frand(1.4f, 2.4f) * SEAHORSE_SPEED_BOOST
                                      : -frand(1.4f, 2.4f) * SEAHORSE_SPEED_BOOST;
  seahorse.phase = frand(0.0f, 6.28318f);
  seahorse.finPhase = frand(0.0f, 6.28318f);
  scheduleSeahorseSpawn(now);
}

void updateSeahorse(unsigned long now, float dt) {
  if (!seahorse.active) {
    if (seahorse.nextSpawnMs == 0) {
      scheduleSeahorseSpawn(now);
    } else if (timeReached(now, seahorse.nextSpawnMs)) {
      spawnSeahorse(now);
    }
    return;
  }

  float t = now * 0.001f;
  float pulse = 1.0f + sinf(t * 0.55f + seahorse.phase) * 0.18f;
  seahorse.x += seahorse.vx * pulse * dt;
  seahorse.y = seahorse.baseY + sinf(t * 0.82f + seahorse.phase) * 4.5f +
               sinf(t * 2.15f + seahorse.phase * 1.7f) * 0.9f;

  if ((seahorse.vx > 0.0f && seahorse.x > SCREEN_W + SEAHORSE_EXIT_PAD) ||
      (seahorse.vx < 0.0f && seahorse.x < -SEAHORSE_EXIT_PAD)) {
    seahorse.active = false;
  }
}

void keepVisitorsSeparated() {
  if (!octopus.active || !seahorse.active) return;

  float octoCenterX = octopus.x;
  float octoCenterY = octopus.y + OCTOPUS_CENTER_Y_OFFSET;
  float horseCenterX = seahorse.x + SEAHORSE_CENTER_X_OFFSET;
  float horseCenterY = seahorse.y + SEAHORSE_CENTER_Y_OFFSET;
  float dx = horseCenterX - octoCenterX;
  float dy = horseCenterY - octoCenterY;
  float sx = dx / VISITOR_CLEAR_RADIUS_X;
  float sy = dy / VISITOR_CLEAR_RADIUS_Y;
  float scaledD2 = sx * sx + sy * sy;
  if (scaledD2 >= 1.0f) return;

  if (scaledD2 <= 0.0001f) {
    dx = (seahorse.vx >= octopus.vx) ? 1.0f : -1.0f;
    dy = 0.35f;
    scaledD2 = (dx / VISITOR_CLEAR_RADIUS_X) * (dx / VISITOR_CLEAR_RADIUS_X) +
               (dy / VISITOR_CLEAR_RADIUS_Y) * (dy / VISITOR_CLEAR_RADIUS_Y);
  }

  float scale = 1.0f / sqrtf(scaledD2);
  float targetHorseCenterX = octoCenterX + dx * scale;
  float targetHorseCenterY = octoCenterY + dy * scale;
  float pushX = (targetHorseCenterX - horseCenterX) * 0.18f;
  float pushY = (targetHorseCenterY - horseCenterY) * 0.22f;

  seahorse.x += pushX;
  seahorse.baseY = clampVal(seahorse.baseY + pushY, 24.0f, (float)SEA_LEVEL_Y - 54.0f);
  seahorse.y += pushY;
  octopus.x -= pushX * 0.55f;
  octopus.baseY = clampVal(octopus.baseY - pushY * 0.55f, 28.0f, (float)SEA_LEVEL_Y - 44.0f);
  octopus.y -= pushY * 0.55f;
}

// ------------------------------ Drawing --------------------------------------
void seaweedPointAt(float u, float bx, int y0, float bladeHeight, float sway, float tSec, int bladeIndex, float& x, float& y) {
  u = clampVal(u, 0.0f, 1.0f);
  float bodyWave = sinf(tSec * (1.05f + bladeIndex * 0.025f) * seaweedSwaySpeed - u * 5.1f + bladeIndex * 0.72f);
  float ripple = sinf(tSec * 0.72f * seaweedSwaySpeed + u * 9.0f + bladeIndex * 1.31f);
  float bend = sway * u * (0.20f + u * 0.80f);
  float travel = bodyWave * (1.5f + bladeHeight * 0.055f) * u * u;
  float detail = ripple * 1.2f * u;
  x = bx + bend + travel + detail;
  y = y0 - bladeHeight * u;
}

void drawSeaweedBranches(TFT_eSprite& s, int bladeIndex, float bladeHeight, float sway, float tSec,
                         float bx, int y0) {
  int branchCount = clampVal((int)(bladeHeight / 14.0f), 2, 5);
  for (int b = 0; b < branchCount; ++b) {
    float u = 0.30f + b * 0.14f + ((bladeIndex + b) % 3) * 0.018f;
    if (u > 0.88f) u = 0.88f;

    float px, py;
    seaweedPointAt(u, bx, y0, bladeHeight, sway, tSec, bladeIndex, px, py);

    float side = ((bladeIndex + b) & 1) ? 1.0f : -1.0f;
    float branchLen = 5.5f + ((bladeIndex * 3 + b * 5) % 5);
    float branchWiggle = sinf(tSec * (1.1f + bladeIndex * 0.03f) * seaweedSwaySpeed + bladeIndex + b * 1.7f) * 1.2f;
    int ex = (int)(px + side * (branchLen * 0.58f + fabsf(sway) * 0.05f) + branchWiggle);
    int ey = (int)(py - branchLen * 0.78f);
    uint16_t color = (b & 1) ? TFT_DARKGREEN : TFT_GREEN;
    s.drawLine((int)px, (int)py, ex, ey, color);
  }
}

void drawSeaweed(TFT_eSprite& s, float tSec) {
  static const int roots = 12;
  static bool cached = false;
  static float baseX[roots];
  static float amp[roots];
  static float heightNoise[roots];

  if (!cached) {
    for (int i = 0; i < roots; ++i) {
      baseX[i] = 10 + i * (SCREEN_W - 20.0f) / (roots - 1);
      amp[i] = 5.0f + (i % 4) * 2.0f;
      heightNoise[i] = sinf(i * 2.173f + 0.61f);
    }
    cached = true;
  }

  for (int i = 0; i < roots; i++) {
    float bx = baseX[i];
    float sway = sinf(tSec * (0.8f + 0.09f * i) * seaweedSwaySpeed + i * 0.7f) * amp[i];
    float heightVariation = 1.0f + seaweedLengthRandomness * heightNoise[i];
    float bladeHeight = clampVal(32.0f * seaweedLength * heightVariation, 18.0f, 72.0f);
    int y0 = SCREEN_H - 2;

    float prevX, prevY;
    prevX = bx;
    prevY = y0;
    const int segments = 7;
    for (int seg = 1; seg <= segments; ++seg) {
      float u = (float)seg / segments;
      float x, y;
      seaweedPointAt(u, bx, y0, bladeHeight, sway, tSec, i, x, y);
      uint16_t color = (u < 0.38f) ? TFT_DARKGREEN : ((u < 0.76f) ? TFT_GREEN : TFT_GREENYELLOW);
      s.drawLine((int)prevX, (int)prevY, (int)x, (int)y, color);
      if (u < 0.78f) {
        s.drawLine((int)prevX + 1, (int)prevY, (int)x + 1, (int)y, TFT_DARKGREEN);
      }
      prevX = x;
      prevY = y;
    }
    drawSeaweedBranches(s, i, bladeHeight, sway, tSec, bx, y0);
  }
}

void drawFlakes(TFT_eSprite& s) {
  s.setTextSize(1);
  s.setTextDatum(MC_DATUM);
  for (int i = 0; i < MAX_FLAKES; i++) {
    if (!flakes[i].active) continue;
    s.setTextColor(flakes[i].color);
    s.drawString("*", (int)flakes[i].x, (int)flakes[i].y);
  }
}

void drawBubbles(TFT_eSprite& s) {
  s.setTextSize(1);
  s.setTextDatum(MC_DATUM);
  int bubbleCount = activeBubbleLimit();
  for (int i = 0; i < bubbleCount; i++) {
    if (!bubbles[i].active) continue;
    s.setTextColor(bubbles[i].color);
    s.drawString("o", (int)bubbles[i].x, (int)bubbles[i].y);
  }
}

void drawFish(TFT_eSprite& s) {
  s.setTextSize(1);
  s.setTextDatum(TL_DATUM);
  const float t = aquariumTimeSec();
  const float waveBase = t * FISH_SWIM_WAVE_SPEED;
  static const float waveStepSin = sinf(FISH_SWIM_WAVE_SPACING);
  static const float waveStepCos = cosf(FISH_SWIM_WAVE_SPACING);
  int fishCount = activeFishLimit();
  for (int i = 0; i < fishCount; i++) {
    Fish& f = fishPool[i];
    if (!f.active) continue;
    const char* txt = fishGlyphDrawing(f);
    const int16_t* glyphOffsets = fishGlyphOffsets(f);
    uint8_t len = fishGlyphLength(f);
    float waveAngle = waveBase + f.phase;
    float wave = sinf(waveAngle);
    float waveCos = cosf(waveAngle);
    s.setTextColor(f.renderColor);
    for (uint8_t c = 0; c < len; ++c) {
      if (txt[c] != ' ') {
        float yOffset = wave * FISH_SWIM_WAVE_AMPLITUDE;
        int charX = (int)f.x + glyphOffsets[c];
        int charY = (int)f.y + (int)(yOffset + ((yOffset >= 0.0f) ? 0.5f : -0.5f));
        s.drawChar((uint16_t)txt[c], charX, charY);
      }

      float nextWave = wave * waveStepCos + waveCos * waveStepSin;
      waveCos = waveCos * waveStepCos - wave * waveStepSin;
      wave = nextWave;
    }
  }
}

uint16_t octopusColor(float tSec) {
  int r = 205 + (int)(42.0f * sinf(tSec * 0.18f + octopus.colorPhase));
  int g = 78 + (int)(38.0f * sinf(tSec * 0.13f + octopus.colorPhase + 2.1f));
  int b = 178 + (int)(58.0f * sinf(tSec * 0.16f + octopus.colorPhase + 4.2f));
  return rgb565From888(r, g, b);
}

void drawOctopusGlyph(TFT_eSprite& s, const char* glyph, int x, int y) {
  if (!glyph || glyph[0] == '\0') return;
  s.drawChar((uint16_t)glyph[0], x, y);
}

void drawOctopus(TFT_eSprite& s) {
  if (!octopus.active) return;
  float t = aquariumTimeSec();
  int cx = (int)octopus.x;
  int cy = (int)octopus.y;

  s.setTextSize(1);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(octopusColor(t));

  float topWave = sinf(t * 1.25f + octopus.phase) * 1.4f;
  drawOctopusGlyph(s, "(", cx - 13, cy + (int)topWave);
  drawOctopusGlyph(s, ".", cx - 3, cy - 5);
  drawOctopusGlyph(s, ".", cx + 7, cy - 5);
  drawOctopusGlyph(s, ")", cx + 16, cy - (int)topWave);

  static const char* tentacleGlyphs[] = {"(", "(", "(", ")", ")", ")"};
  static const int tentacleX[] = {-24, -16, -8, 2, 10, 18};
  for (int i = 0; i < 6; ++i) {
    float wave = sinf(t * 1.75f + octopus.phase + i * 0.72f);
    int x = cx + tentacleX[i] + (int)(wave * 1.4f);
    int y = cy + 13 + (int)(wave * 2.2f);
    drawOctopusGlyph(s, tentacleGlyphs[i], x, y);
  }
}

uint16_t seahorseColor(float tSec) {
  int r = 238 + (int)(12.0f * sinf(tSec * 0.11f + seahorse.phase));
  int g = 142 + (int)(18.0f * sinf(tSec * 0.16f + seahorse.phase + 1.4f));
  int b = 48 + (int)(12.0f * sinf(tSec * 0.13f + seahorse.phase + 2.8f));
  return rgb565From888(r, g, b);
}

char mirrorSeahorseGlyph(char glyph) {
  switch (glyph) {
    case '/': return '\\';
    case '\\': return '/';
    case '[': return ']';
    case ']': return '[';
    case '(': return ')';
    case ')': return '(';
    case '<': return '>';
    case '>': return '<';
    default: return glyph;
  }
}

void drawSeahorseGlyph(TFT_eSprite& s, char glyph, int x, int y) {
  s.drawChar((uint16_t)glyph, x, y);
}

void drawSeahorse(TFT_eSprite& s) {
  if (!seahorse.active) return;
  static const char* seahorseLeftRows[] = {
      "  ^^  ",
      " / o) ",
      "[__-/ ",
      "  /|  ",
      " / |  ",
      " \\ |  ",
      "  ( ) ",
      "  \\_/ ",
  };
  static const int SEAHORSE_ART_ROWS = sizeof(seahorseLeftRows) / sizeof(seahorseLeftRows[0]);
  static const int SEAHORSE_ART_COLS = 6;
  static const int SEAHORSE_CELL_W = 5;
  static const int SEAHORSE_ROW_H = 6;

  float t = aquariumTimeSec();
  int x = (int)seahorse.x;
  int y = (int)seahorse.y;
  int sway = (int)(sinf(t * 1.15f + seahorse.phase) * 1.2f);
  int finFlutter = (int)(sinf(t * 10.0f + seahorse.finPhase) * 1.2f);
  const char* finGlyph = (sinf(t * 12.0f + seahorse.finPhase) > 0.0f) ? "~" : "-";

  s.setTextSize(1);
  s.setTextFont(1);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(seahorseColor(t));

  for (int row = 0; row < SEAHORSE_ART_ROWS; ++row) {
    const char* line = seahorseLeftRows[row];
    int len = strlen(line);
    int rowSway = (row >= 1 && row <= 3) ? sway : 0;
    for (int col = 0; col < SEAHORSE_ART_COLS; ++col) {
      char glyph = (col < len) ? line[col] : ' ';
      if (glyph == ' ') continue;
      int drawCol = col;
      if (seahorse.facingRight) {
        drawCol = SEAHORSE_ART_COLS - 1 - col;
        glyph = mirrorSeahorseGlyph(glyph);
      }
      drawSeahorseGlyph(s, glyph, x + drawCol * SEAHORSE_CELL_W + rowSway, y + row * SEAHORSE_ROW_H);
    }
  }

  s.setTextColor(rgb565From888(255, 188, 82));
  int finX = seahorse.facingRight ? x + 5 + finFlutter : x + 20 + finFlutter;
  s.drawString(finGlyph, finX, y + 24);
  s.setTextFont(2);
}

void drawAsciiClockBackground(TFT_eSprite& s) {
  if (!clockVisible || clockDisplayStyle != CLOCK_STYLE_ASCII) return;

  char timeText[16];
  formatClockTimeOnly(timeText, sizeof(timeText), false);
  int artCols = asciiClockTextCols(timeText);
  int artPixelW = artCols * ASCII_CLOCK_CHAR_W;
  int x = (SCREEN_W - artPixelW) / 2;
  if (x < 0) x = 0;
  int y = ASCII_CLOCK_Y;

  s.setTextFont(1);
  s.setTextSize(1);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(clockAsciiTextColor);

  for (int row = 0; row < ASCII_CLOCK_ROWS; ++row) {
    char rowBuf[96] = "";
    for (size_t i = 0; timeText[i] != '\0'; ++i) {
      if (i > 0) {
        for (int gap = 0; gap < ASCII_CLOCK_GLYPH_GAP; ++gap) appendCharSafe(rowBuf, sizeof(rowBuf), ' ');
      }
      appendAsciiClockGlyphRow(rowBuf, sizeof(rowBuf), asciiClockGlyphFor(timeText[i]), row);
    }
    if (clockFlipHorizontal) {
      mirrorClockTextInPlace(rowBuf);
    }
    trimTrailingSpaces(rowBuf);
    if (rowBuf[0] != '\0') s.drawString(rowBuf, x, y + row * ASCII_CLOCK_ROW_H);
  }

  s.setTextFont(2);
}

void drawMirroredSmallClock(TFT_eSprite& s, const char* line, int y) {
  if (!clockFlipSpriteReady) {
    char fallback[32];
    copySafe(fallback, sizeof(fallback), line);
    mirrorClockTextInPlace(fallback);
    s.setTextDatum(TC_DATUM);
    s.drawString(fallback, SCREEN_W / 2, y);
    return;
  }

  clockFlipSprite.setTextFont(2);
  clockFlipSprite.setTextSize(1);
  clockFlipSprite.setTextDatum(TL_DATUM);
  clockFlipSprite.fillSprite(CLOCK_FLIP_TRANSPARENT);
  uint16_t transparentKey = clockFlipSprite.readPixel(0, CLOCK_FLIP_SPRITE_H - 1);
  clockFlipSprite.setTextColor(clockSmallTextColor, CLOCK_FLIP_TRANSPARENT);
  clockFlipSprite.drawString(line, 0, 0);

  int textW = clockFlipSprite.textWidth(line);
  if (textW <= 0) return;
  int drawW = clampVal(textW, 1, CLOCK_FLIP_SPRITE_W);
  int destX = (SCREEN_W - drawW) / 2;

  for (int py = 0; py < CLOCK_FLIP_SPRITE_H; ++py) {
    int destY = y + py;
    if (destY < 0 || destY >= SCREEN_H) continue;
    for (int px = 0; px < drawW; ++px) {
      uint16_t color = clockFlipSprite.readPixel(px, py);
      if (color != transparentKey) {
        s.drawPixel(destX + drawW - 1 - px, destY, color);
      }
    }
  }
}

void drawClock(TFT_eSprite& s) {
  if (!clockVisible || clockDisplayStyle != CLOCK_STYLE_SMALL_TEXT) return;
  char line[32];
  formatClockDisplay(line, sizeof(line));
  s.setTextSize(1);
  s.setTextDatum(TC_DATUM);
  s.setTextColor(clockSmallTextColor);
  int y = (clockSmallPosition == CLOCK_SMALL_TOP) ? 4 : (SCREEN_H - 18);
  if (clockFlipHorizontal) {
    drawMirroredSmallClock(s, line, y);
  } else {
    s.drawString(line, SCREEN_W / 2, y);
  }
}

void drawHud(TFT_eSprite& s) {
  if (!hudVisible) return;
  constexpr int kHudTextYStart = 32;   // Below corners so long labels avoid H overlap
  constexpr int kHudTextLineDY = 16;   // Font 2-ish second line spacing
  constexpr int kHudTextX = 8;

  s.setTextSize(1);
  s.setTextColor(TFT_WHITE, BG_COLOR);
  s.setTextDatum(TL_DATUM);

  // Draw hidden HUD chrome first.
  drawButton(s, DEBUG_BUTTON_X, CORNER_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H, "D", TFT_WHITE, TFT_DARKGREEN);
  drawButton(s, CAPTURE_BUTTON_X, CORNER_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H, "C",
             capturePanelOpen ? TFT_NAVY : TFT_WHITE, capturePanelOpen ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, WIFI_BUTTON_X, CORNER_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H, "W",
             wifiPanelOpen ? TFT_NAVY : TFT_WHITE, wifiPanelOpen ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, SETTINGS_CORNER_BUTTON_X, CORNER_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H, "S", TFT_WHITE, TFT_DARKGREEN);
  drawButton(s, SETTINGS_CORNER_BUTTON_X, RESPAWN_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H, "R", TFT_WHITE, TFT_DARKGREEN);
  drawButton(s, SEAHORSE_TEST_BUTTON_X, SEAHORSE_TEST_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H, "H",
             TFT_WHITE, TFT_DARKGREEN);
  drawButton(s, OCTOPUS_TEST_BUTTON_X, OCTOPUS_TEST_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H, "O",
             TFT_WHITE, TFT_DARKGREEN);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(TFT_WHITE, BG_COLOR);

  char title[48];
  snprintf(title, sizeof(title), "ASCII Aquarium %s", kSketchVersionLabel);
  s.drawString(title, kHudTextX, kHudTextYStart);

  char line[64];
  snprintf(line, sizeof(line), "Fish:%d  FPS:%2.1f", fishTargetCount, fps);
  s.drawString(line, kHudTextX, kHudTextYStart + kHudTextLineDY);
}

void drawButton(TFT_eSprite& s, int x, int y, int w, int h, const char* label, uint16_t fg, uint16_t bg) {
  s.fillRoundRect(x, y, w, h, 4, bg);
  s.drawRoundRect(x, y, w, h, 4, fg);
  s.setTextColor(fg, bg);
  s.setTextDatum(MC_DATUM);
  s.drawString(label, x + w / 2, y + h / 2);
}

void drawSettingRow(TFT_eSprite& s, int rowY, const char* label, const char* value) {
  const int controlY = rowY;
  const int centerY = controlY + SETTINGS_BUTTON_H / 2;
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, SETTINGS_PANEL_X + 12, centerY);

  s.setTextDatum(MR_DATUM);
  s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
  s.drawString(value, SETTINGS_VALUE_RIGHT_X, centerY);

  drawButton(s, SETTINGS_MINUS_X, controlY, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H, "-", TFT_WHITE, TFT_DARKGREEN);
  drawButton(s, SETTINGS_PLUS_X, controlY, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H, "+", TFT_WHITE, TFT_DARKGREEN);
}

void drawSettingToggleRow(TFT_eSprite& s, int rowY, const char* label, const char* leftLabel, const char* rightLabel,
                          bool leftActive, bool rightActive) {
  const int controlY = rowY;
  const int centerY = controlY + SETTINGS_BUTTON_H / 2;
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, SETTINGS_PANEL_X + 12, centerY);

  drawButton(s, SETTINGS_MINUS_X, controlY, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H, leftLabel,
             leftActive ? TFT_NAVY : TFT_WHITE, leftActive ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, SETTINGS_PLUS_X, controlY, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H, rightLabel,
             rightActive ? TFT_NAVY : TFT_WHITE, rightActive ? TFT_CYAN : TFT_DARKGREEN);
}

void drawSettingStatusRow(TFT_eSprite& s, int rowY, const char* label, const char* value) {
  const int centerY = rowY + SETTINGS_BUTTON_H / 2;
  char shortValue[18];
  formatShortText(shortValue, sizeof(shortValue), value, 14);
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, SETTINGS_PANEL_X + 12, centerY);
  s.setTextDatum(MR_DATUM);
  s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
  s.drawString(shortValue, SETTINGS_PANEL_X + SETTINGS_PANEL_W - 16, centerY);
}

void drawWifiPanelBase(TFT_eSprite& s, const char* title) {
  s.fillRoundRect(WIFI_PANEL_X, WIFI_PANEL_Y, WIFI_PANEL_W, WIFI_PANEL_H, 8, TFT_NAVY);
  s.drawRoundRect(WIFI_PANEL_X, WIFI_PANEL_Y, WIFI_PANEL_W, WIFI_PANEL_H, 8, TFT_CYAN);
  s.setTextSize(1);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(title, WIFI_PANEL_X + 10, WIFI_PANEL_Y + 10);
  drawButton(s, WIFI_CLOSE_X, WIFI_CLOSE_Y, WIFI_CLOSE_W, WIFI_CLOSE_H, "X", TFT_WHITE, TFT_RED);
}

void drawWifiToggleRow(TFT_eSprite& s, int rowY, const char* label, bool offActive, bool onActive) {
  int centerY = rowY + WIFI_ROW_H / 2;
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, WIFI_LABEL_X, centerY);
  drawButton(s, WIFI_OFF_X, rowY, WIFI_TOGGLE_W, WIFI_ROW_H, "OFF",
             offActive ? TFT_NAVY : TFT_WHITE, offActive ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, WIFI_ON_X, rowY, WIFI_TOGGLE_W, WIFI_ROW_H, "ON",
             onActive ? TFT_NAVY : TFT_WHITE, onActive ? TFT_CYAN : TFT_DARKGREEN);
}

void drawWifiStatusRow(TFT_eSprite& s, int rowY, const char* label, const char* value) {
  char shortValue[24];
  int centerY = rowY + WIFI_ROW_H / 2;
  formatShortText(shortValue, sizeof(shortValue), value, 19);
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, WIFI_LABEL_X, centerY);
  s.setTextDatum(MR_DATUM);
  s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
  s.drawString(shortValue, WIFI_PANEL_X + WIFI_PANEL_W - 16, centerY);
}

void drawWifiActionRow(TFT_eSprite& s, int rowY, const char* label, const char* value, const char* actionLabel) {
  char shortValue[18];
  int centerY = rowY + WIFI_ROW_H / 2;
  formatShortText(shortValue, sizeof(shortValue), value, 13);
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, WIFI_LABEL_X, centerY);
  s.setTextDatum(MR_DATUM);
  s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
  s.drawString(shortValue, WIFI_VALUE_RIGHT_X, centerY);
  drawButton(s, WIFI_ACTION_X, rowY, WIFI_ACTION_W, WIFI_ROW_H, actionLabel, TFT_CYAN, TFT_DARKGREEN);
}

void drawWifiStepRow(TFT_eSprite& s, int rowY, const char* label, const char* value) {
  char shortValue[20];
  int centerY = rowY + WIFI_ROW_H / 2;
  formatShortText(shortValue, sizeof(shortValue), value, 15);
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, WIFI_LABEL_X, centerY);
  s.setTextDatum(MR_DATUM);
  s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
  s.drawString(shortValue, WIFI_VALUE_RIGHT_X, centerY);
  drawButton(s, WIFI_OFF_X, rowY, WIFI_TOGGLE_W, WIFI_ROW_H, "-", TFT_WHITE, TFT_DARKGREEN);
  drawButton(s, WIFI_ON_X, rowY, WIFI_TOGGLE_W, WIFI_ROW_H, "+", TFT_WHITE, TFT_DARKGREEN);
}

const char* keyboardRowText(int row) {
  static const char* lowerRows[] = {"1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"};
  static const char* upperRows[] = {"1234567890", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"};
  static const char* symbolRows[] = {"!@#$%^&*()", "-_=+[]{}", ";:'\",.<>", "/\\?|~`"};
  if (row < 0 || row >= 4) return "";
  if (keyboardMode == KEYBOARD_UPPER) return upperRows[row];
  if (keyboardMode == KEYBOARD_SYMBOLS) return symbolRows[row];
  return lowerRows[row];
}

void keyboardKeyBounds(int row, int keyIndex, int& x, int& y, int& w, int& h) {
  const char* keys = keyboardRowText(row);
  int keyCount = strlen(keys);
  int totalGap = (keyCount - 1) * WIFI_KEY_GAP;
  w = (WIFI_PANEL_W - 22 - totalGap) / keyCount;
  h = WIFI_KEY_H;
  int totalW = w * keyCount + totalGap;
  x = WIFI_PANEL_X + (WIFI_PANEL_W - totalW) / 2 + keyIndex * (w + WIFI_KEY_GAP);
  y = WIFI_KEY_START_Y + row * (WIFI_KEY_H + WIFI_KEY_GAP);
}

void drawKeyboardKeys(TFT_eSprite& s) {
  for (int row = 0; row < 4; ++row) {
    const char* keys = keyboardRowText(row);
    int keyCount = strlen(keys);
    for (int i = 0; i < keyCount; ++i) {
      int x, y, w, h;
      keyboardKeyBounds(row, i, x, y, w, h);
      char label[2] = {keys[i], '\0'};
      drawButton(s, x, y, w, h, label, TFT_WHITE, TFT_DARKGREEN);
    }
  }

  drawButton(s, WIFI_PANEL_X + 18, WIFI_KEYBOARD_SPECIAL_Y, 56, 22, keyboardMode == KEYBOARD_UPPER ? "lower" : "SHIFT",
             keyboardMode == KEYBOARD_UPPER ? TFT_NAVY : TFT_WHITE, keyboardMode == KEYBOARD_UPPER ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, WIFI_PANEL_X + 82, WIFI_KEYBOARD_SPECIAL_Y, 48, 22, keyboardMode == KEYBOARD_SYMBOLS ? "ABC" : "SYM",
             keyboardMode == KEYBOARD_SYMBOLS ? TFT_NAVY : TFT_WHITE, keyboardMode == KEYBOARD_SYMBOLS ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, WIFI_PANEL_X + 138, WIFI_KEYBOARD_SPECIAL_Y, 86, 22, "Space", TFT_WHITE, TFT_DARKGREEN);
  drawButton(s, WIFI_PANEL_X + 232, WIFI_KEYBOARD_SPECIAL_Y, 56, 22, "Del", TFT_WHITE, TFT_DARKGREEN);
}

void drawWifiMainPanel(TFT_eSprite& s) {
  char ssidLabel[24];
  const char* shownSsid = wifiConnecting ? pendingWifiSsid : wifiSsid;
  formatShortText(ssidLabel, sizeof(ssidLabel), shownSsid[0] ? shownSsid : "(none)", 18);

  drawWifiPanelBase(s, "WiFi");
  drawWifiToggleRow(s, WIFI_ROW_START_Y, "WiFi", !wifiEnabled, wifiEnabled);
  drawWifiActionRow(s, WIFI_ROW_START_Y + WIFI_ROW_GAP, "Network", ssidLabel,
                    wifiScanInProgress ? "Wait" : "List");
  drawWifiStatusRow(s, WIFI_ROW_START_Y + WIFI_ROW_GAP * 2, "Status", wifiStatusText);
  drawWifiStatusRow(s, WIFI_ROW_START_Y + WIFI_ROW_GAP * 3, "Time", internetTimeStatus());
  drawWifiStepRow(s, WIFI_ROW_START_Y + WIFI_ROW_GAP * 4, "Timezone", currentTimezone().label);
}

void drawWifiNetworksPanel(TFT_eSprite& s) {
  drawWifiPanelBase(s, "WiFi Networks");
  if (wifiScanInProgress) {
    s.setTextDatum(MC_DATUM);
    s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
    s.drawString("Scanning...", SCREEN_W / 2, WIFI_PANEL_Y + 92);
  } else if (wifiNetworkCount == 0) {
    s.setTextDatum(MC_DATUM);
    s.setTextColor(TFT_WHITE, TFT_NAVY);
    s.drawString("No networks found", SCREEN_W / 2, WIFI_PANEL_Y + 84);
  } else {
    int start = wifiNetworkPage * WIFI_LIST_ROW_COUNT;
    int end = start + WIFI_LIST_ROW_COUNT;
    if (end > wifiNetworkCount) end = wifiNetworkCount;
    for (int i = start; i < end; ++i) {
      int row = i - start;
      int y = WIFI_LIST_ROW_Y + row * WIFI_LIST_ROW_H;
      char ssidShort[24];
      char rssiText[10];
      formatShortText(ssidShort, sizeof(ssidShort), wifiNetworkNames[i], wifiNetworkOpen[i] ? 15 : 18);
      snprintf(rssiText, sizeof(rssiText), "%ddB", wifiNetworkRssi[i]);
      s.fillRoundRect(WIFI_PANEL_X + 12, y, WIFI_PANEL_W - 24, WIFI_LIST_ROW_H - 2, 4, TFT_DARKGREEN);
      s.drawRoundRect(WIFI_PANEL_X + 12, y, WIFI_PANEL_W - 24, WIFI_LIST_ROW_H - 2, 4, TFT_CYAN);
      s.setTextDatum(ML_DATUM);
      s.setTextColor(TFT_WHITE, TFT_DARKGREEN);
      s.drawString(ssidShort, WIFI_PANEL_X + 20, y + (WIFI_LIST_ROW_H - 2) / 2);
      if (wifiNetworkOpen[i]) {
        s.setTextColor(TFT_GREENYELLOW, TFT_DARKGREEN);
        s.drawString("open", WIFI_PANEL_X + 166, y + (WIFI_LIST_ROW_H - 2) / 2);
      }
      s.setTextDatum(MR_DATUM);
      s.setTextColor(TFT_CYAN, TFT_DARKGREEN);
      s.drawString(rssiText, WIFI_PANEL_X + WIFI_PANEL_W - 22, y + (WIFI_LIST_ROW_H - 2) / 2);
    }
  }

  int bottomY = WIFI_PANEL_Y + WIFI_PANEL_H - 30;
  drawButton(s, WIFI_PANEL_X + 18, bottomY, 58, 22, "Back", TFT_CYAN, TFT_DARKGREEN);
  drawButton(s, WIFI_PANEL_X + 84, bottomY, 58, 22, "Scan", TFT_CYAN, TFT_DARKGREEN);
  drawButton(s, WIFI_PANEL_X + 184, bottomY, 54, 22, "Prev", TFT_CYAN, TFT_DARKGREEN);
  drawButton(s, WIFI_PANEL_X + 246, bottomY, 54, 22, "Next", TFT_CYAN, TFT_DARKGREEN);
}

void drawWifiPasswordPanel(TFT_eSprite& s) {
  char title[42];
  char ssidShort[22];
  char passShort[34];
  formatShortText(ssidShort, sizeof(ssidShort), pendingWifiSsid, 15);
  formatShortText(passShort, sizeof(passShort), wifiPasswordBuffer, 29);
  snprintf(title, sizeof(title), "WiFi Password: %s", ssidShort);

  drawWifiPanelBase(s, title);
  s.setTextDatum(TL_DATUM);
  s.fillRoundRect(WIFI_PANEL_X + 12, WIFI_PANEL_Y + 35, WIFI_PANEL_W - 24, 22, 4, TFT_BLACK);
  s.drawRoundRect(WIFI_PANEL_X + 12, WIFI_PANEL_Y + 35, WIFI_PANEL_W - 24, 22, 4, TFT_CYAN);
  s.setTextColor(TFT_GREENYELLOW, TFT_BLACK);
  s.drawString(passShort[0] ? passShort : "password", WIFI_PANEL_X + 18, WIFI_PANEL_Y + 39);

  drawKeyboardKeys(s);
  drawButton(s, WIFI_PANEL_X + 18, WIFI_KEYBOARD_ACTION_Y, 76, 22, "Cancel", TFT_CYAN, TFT_DARKGREEN);
  drawButton(s, WIFI_PANEL_X + 226, WIFI_KEYBOARD_ACTION_Y, 76, 22, "Join", TFT_CYAN, TFT_DARKGREEN);
}

void drawWifiPanel(TFT_eSprite& s) {
  if (!wifiPanelOpen) return;
  if (wifiPanelMode == WIFI_PANEL_NETWORKS) {
    drawWifiNetworksPanel(s);
  } else if (wifiPanelMode == WIFI_PANEL_PASSWORD) {
    drawWifiPasswordPanel(s);
  } else {
    drawWifiMainPanel(s);
  }
}

void drawCaptureValueRow(TFT_eSprite& s, int rowY, const char* label, const char* value, const char* actionLabel) {
  char valueShort[22];
  formatShortText(valueShort, sizeof(valueShort), value, actionLabel && actionLabel[0] ? 15 : 20);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, CAPTURE_LABEL_X, rowY + 4);
  s.setTextDatum(TR_DATUM);
  s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
  s.drawString(valueShort, CAPTURE_VALUE_RIGHT_X, rowY + 4);
  s.setTextDatum(TL_DATUM);
  if (actionLabel && actionLabel[0]) {
    drawButton(s, CAPTURE_ACTION_X, rowY, CAPTURE_ACTION_W, CAPTURE_ROW_H, actionLabel, TFT_CYAN, TFT_DARKGREEN);
  }
}

void drawCapturePanel(TFT_eSprite& s) {
  if (!capturePanelOpen) return;
  s.fillRoundRect(CAPTURE_PANEL_X, CAPTURE_PANEL_Y, CAPTURE_PANEL_W, CAPTURE_PANEL_H, 8, TFT_NAVY);
  s.drawRoundRect(CAPTURE_PANEL_X, CAPTURE_PANEL_Y, CAPTURE_PANEL_W, CAPTURE_PANEL_H, 8, TFT_CYAN);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString("Capture", CAPTURE_PANEL_X + 10, CAPTURE_PANEL_Y + 10);
  drawButton(s, CAPTURE_CLOSE_X, CAPTURE_CLOSE_Y, CAPTURE_CLOSE_W, CAPTURE_CLOSE_H, "X", TFT_WHITE, TFT_RED);

  char fpsLabel[12];
  snprintf(fpsLabel, sizeof(fpsLabel), "%lu", captureNextSequenceIndex);
  drawCaptureValueRow(s, CAPTURE_ROW_START_Y, "SD", captureStatusText, "Check");
  drawCaptureValueRow(s, CAPTURE_ROW_START_Y + CAPTURE_ROW_GAP, "Frames", "Every frame", "Save");
  drawCaptureValueRow(s, CAPTURE_ROW_START_Y + CAPTURE_ROW_GAP * 2, "Next", fpsLabel, "");
  drawCaptureValueRow(s, CAPTURE_ROW_START_Y + CAPTURE_ROW_GAP * 3, "Last", captureLastFile[0] ? captureLastFile : "None", "");
}

void drawCaptureToast(TFT_eSprite& s) {
  unsigned long now = millis();
  if (capturePanelOpen || now >= captureToastUntilMs) return;
  const int w = 190;
  const int h = 38;
  const int x = (SCREEN_W - w) / 2;
  const int y = 32;
  s.fillRoundRect(x, y, w, h, 8, TFT_NAVY);
  s.drawRoundRect(x, y, w, h, 8, TFT_CYAN);
  s.setTextDatum(MC_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(captureStatusText, x + w / 2, y + h / 2);
  s.setTextDatum(TL_DATUM);
}

void drawSettingsTabs(TFT_eSprite& s) {
  bool tankActive = (activeSettingsTab == SETTINGS_TAB_TANK);
  bool seaweedActive = (activeSettingsTab == SETTINGS_TAB_SEAWEED);
  bool clockActive = (activeSettingsTab == SETTINGS_TAB_CLOCK);
  bool backgroundActive = (activeSettingsTab == SETTINGS_TAB_BACKGROUND);
  drawButton(s, SETTINGS_TANK_TAB_X, SETTINGS_TAB_Y, SETTINGS_TANK_TAB_W, SETTINGS_TAB_H, "Tank",
             tankActive ? TFT_NAVY : TFT_CYAN, tankActive ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, SETTINGS_SEAWEED_TAB_X, SETTINGS_TAB_Y, SETTINGS_SEAWEED_TAB_W, SETTINGS_TAB_H, "Seaweed",
             seaweedActive ? TFT_NAVY : TFT_CYAN, seaweedActive ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, SETTINGS_CLOCK_TAB_X, SETTINGS_TAB_Y, SETTINGS_CLOCK_TAB_W, SETTINGS_TAB_H, "Clock",
             clockActive ? TFT_NAVY : TFT_CYAN, clockActive ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, SETTINGS_BACKGROUND_TAB_X, SETTINGS_TAB_Y, SETTINGS_BACKGROUND_TAB_W, SETTINGS_TAB_H, "Backgrd",
             backgroundActive ? TFT_NAVY : TFT_CYAN, backgroundActive ? TFT_CYAN : TFT_DARKGREEN);
}

void drawClockEnableStyleRow(TFT_eSprite& s) {
  const int centerY = CLOCK_ROW_1_Y + SETTINGS_BUTTON_H / 2;
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString("Clock", SETTINGS_PANEL_X + 12, centerY);

  drawButton(s, CLOCK_STYLE_BUTTON_X, CLOCK_ROW_1_Y, CLOCK_STYLE_BUTTON_W, SETTINGS_BUTTON_H, "Style",
             clockStylePanelOpen ? TFT_NAVY : TFT_CYAN, clockStylePanelOpen ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, SETTINGS_MINUS_X, CLOCK_ROW_1_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H, "OFF",
             !clockVisible ? TFT_NAVY : TFT_WHITE, !clockVisible ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, SETTINGS_PLUS_X, CLOCK_ROW_1_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H, "ON",
             clockVisible ? TFT_NAVY : TFT_WHITE, clockVisible ? TFT_CYAN : TFT_DARKGREEN);
}

void drawClockSettings(TFT_eSprite& s) {
  char buf[24];
  drawClockEnableStyleRow(s);
  drawSettingToggleRow(s, CLOCK_ROW_2_Y, "Time", "Man", "Net", !clockUseInternetTime, clockUseInternetTime);
  drawSettingToggleRow(s, CLOCK_ROW_3_Y, "Format", "12h", "24h", !clockUse24Hour, clockUse24Hour);

  if (clockUseInternetTime) {
    drawSettingStatusRow(s, CLOCK_ROW_4_Y, "Internet", internetTimeStatus());
    drawSettingRow(s, CLOCK_ROW_5_Y, "Timezone", currentTimezone().label);
    return;
  }

  formatClockFieldValue(buf, sizeof(buf));
  drawSettingRow(s, CLOCK_ROW_4_Y, clockFieldName(), buf);
  drawSettingRow(s, CLOCK_ROW_5_Y, "Timezone", currentTimezone().label);
  drawButton(s, CLOCK_FIELD_PREV_X, CLOCK_FIELD_NAV_Y, CLOCK_FIELD_NAV_W, CLOCK_FIELD_NAV_H, "Prev", TFT_CYAN, TFT_DARKGREEN);
  drawButton(s, CLOCK_FIELD_NEXT_X, CLOCK_FIELD_NAV_Y, CLOCK_FIELD_NAV_W, CLOCK_FIELD_NAV_H, "Next", TFT_CYAN, TFT_DARKGREEN);
}

void drawClockStyleChoiceRow(TFT_eSprite& s, int rowY, const char* label, const char* leftLabel, const char* rightLabel,
                             bool leftActive, bool rightActive) {
  const int centerY = rowY + SETTINGS_BUTTON_H / 2;
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString(label, CLOCK_STYLE_LABEL_X, centerY);
  drawButton(s, CLOCK_STYLE_LEFT_X, rowY, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H, leftLabel,
             leftActive ? TFT_NAVY : TFT_WHITE, leftActive ? TFT_CYAN : TFT_DARKGREEN);
  drawButton(s, CLOCK_STYLE_RIGHT_X, rowY, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H, rightLabel,
             rightActive ? TFT_NAVY : TFT_WHITE, rightActive ? TFT_CYAN : TFT_DARKGREEN);
}

void drawClockStyleColorRow(TFT_eSprite& s) {
  const int centerY = CLOCK_STYLE_ROW_4_Y + SETTINGS_BUTTON_H / 2;
  s.setTextDatum(ML_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString("Colour", CLOCK_STYLE_LABEL_X, centerY);

  uint16_t color = activeClockTextColor();
  s.fillRoundRect(CLOCK_STYLE_SWATCH_X, CLOCK_STYLE_ROW_4_Y + 3, CLOCK_STYLE_SWATCH_W, SETTINGS_BUTTON_H - 6, 3, color);
  s.drawRoundRect(CLOCK_STYLE_SWATCH_X, CLOCK_STYLE_ROW_4_Y + 3, CLOCK_STYLE_SWATCH_W, SETTINGS_BUTTON_H - 6, 3,
                  color == TFT_WHITE ? TFT_DARKGREY : TFT_WHITE);
  drawButton(s, CLOCK_STYLE_COLOR_BUTTON_X, CLOCK_STYLE_ROW_4_Y, CLOCK_STYLE_COLOR_BUTTON_W, SETTINGS_BUTTON_H,
             "Pick", clockColorPanelOpen ? TFT_NAVY : TFT_CYAN, clockColorPanelOpen ? TFT_CYAN : TFT_DARKGREEN);
}

void drawClockColorPanel(TFT_eSprite& s) {
  if (!clockColorPanelOpen) return;

  s.fillRoundRect(CLOCK_COLOR_PANEL_X, CLOCK_COLOR_PANEL_Y, CLOCK_COLOR_PANEL_W, CLOCK_COLOR_PANEL_H, 8, TFT_NAVY);
  s.drawRoundRect(CLOCK_COLOR_PANEL_X, CLOCK_COLOR_PANEL_Y, CLOCK_COLOR_PANEL_W, CLOCK_COLOR_PANEL_H, 8, TFT_CYAN);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString("Clock Colour", CLOCK_COLOR_PANEL_X + 12, CLOCK_COLOR_PANEL_Y + 12);

  uint16_t selected = activeClockTextColor();
  for (int i = 0; i < CLOCK_COLOR_COUNT; ++i) {
    int col = i % CLOCK_COLOR_SWATCH_COLS;
    int row = i / CLOCK_COLOR_SWATCH_COLS;
    int x = CLOCK_COLOR_GRID_X + col * (CLOCK_COLOR_SWATCH_W + CLOCK_COLOR_SWATCH_GAP_X);
    int y = CLOCK_COLOR_GRID_Y + row * (CLOCK_COLOR_SWATCH_H + CLOCK_COLOR_SWATCH_GAP_Y);
    bool isSelected = (kClockColorPalette[i] == selected);

    if (isSelected) {
      s.drawRoundRect(x - 3, y - 3, CLOCK_COLOR_SWATCH_W + 6, CLOCK_COLOR_SWATCH_H + 6, 5, TFT_WHITE);
    }
    s.fillRoundRect(x, y, CLOCK_COLOR_SWATCH_W, CLOCK_COLOR_SWATCH_H, 4, kClockColorPalette[i]);
    s.drawRoundRect(x, y, CLOCK_COLOR_SWATCH_W, CLOCK_COLOR_SWATCH_H, 4, isSelected ? TFT_YELLOW : TFT_CYAN);
    if (kClockColorPalette[i] == TFT_WHITE) {
      s.drawRoundRect(x + 1, y + 1, CLOCK_COLOR_SWATCH_W - 2, CLOCK_COLOR_SWATCH_H - 2, 3, TFT_DARKGREY);
    }
  }

  drawButton(s, CLOCK_COLOR_CLOSE_X, CLOCK_COLOR_CLOSE_Y, CLOCK_COLOR_CLOSE_W, CLOCK_COLOR_CLOSE_H, "X", TFT_WHITE, TFT_RED);
}

void drawClockStylePanel(TFT_eSprite& s) {
  if (!clockStylePanelOpen) return;

  s.fillRoundRect(CLOCK_STYLE_PANEL_X, CLOCK_STYLE_PANEL_Y, CLOCK_STYLE_PANEL_W, CLOCK_STYLE_PANEL_H, 8, TFT_NAVY);
  s.drawRoundRect(CLOCK_STYLE_PANEL_X, CLOCK_STYLE_PANEL_Y, CLOCK_STYLE_PANEL_W, CLOCK_STYLE_PANEL_H, 8, TFT_CYAN);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString("Clock Style", CLOCK_STYLE_PANEL_X + 12, CLOCK_STYLE_PANEL_Y + 12);

  drawClockStyleChoiceRow(s, CLOCK_STYLE_ROW_1_Y, "Style", "Small", "ASCII",
                          clockDisplayStyle == CLOCK_STYLE_SMALL_TEXT, clockDisplayStyle == CLOCK_STYLE_ASCII);

  if (clockDisplayStyle == CLOCK_STYLE_SMALL_TEXT) {
    drawClockStyleChoiceRow(s, CLOCK_STYLE_ROW_2_Y, "Position", "Top", "Bottom",
                            clockSmallPosition == CLOCK_SMALL_TOP, clockSmallPosition == CLOCK_SMALL_BOTTOM);
  } else {
    const int centerY = CLOCK_STYLE_ROW_2_Y + SETTINGS_BUTTON_H / 2;
    s.setTextDatum(ML_DATUM);
    s.setTextColor(TFT_WHITE, TFT_NAVY);
    s.drawString("Font", CLOCK_STYLE_LABEL_X, centerY);
    s.setTextDatum(MR_DATUM);
    s.setTextColor(TFT_GREENYELLOW, TFT_NAVY);
    s.drawString("Standard", CLOCK_STYLE_PANEL_X + CLOCK_STYLE_PANEL_W - 44, centerY);
  }

  drawClockStyleChoiceRow(s, CLOCK_STYLE_ROW_3_Y, "Flip Clock", "Off", "On",
                          !clockFlipHorizontal, clockFlipHorizontal);
  drawClockStyleColorRow(s);
  drawButton(s, CLOCK_STYLE_CLOSE_X, CLOCK_STYLE_CLOSE_Y, CLOCK_STYLE_CLOSE_W, CLOCK_STYLE_CLOSE_H, "X", TFT_WHITE, TFT_RED);
}

void drawSettingsPanel(TFT_eSprite& s) {
  if (!settingsOpen) return;
  int px = SETTINGS_PANEL_X, py = SETTINGS_PANEL_Y, pw = SETTINGS_PANEL_W, ph = SETTINGS_PANEL_H;
  s.fillRoundRect(px, py, pw, ph, 8, TFT_NAVY);
  s.drawRoundRect(px, py, pw, ph, 8, TFT_CYAN);
  s.setTextDatum(TL_DATUM);
  s.setTextColor(TFT_WHITE, TFT_NAVY);
  s.drawString("Settings", px + 10, py + 10);

  char buf[24];
  if (activeSettingsTab == SETTINGS_TAB_TANK) {
    snprintf(buf, sizeof(buf), "%d", fishTargetCount);
    drawSettingRow(s, SETTINGS_ROW_START_Y, "Fish Population", buf);

    snprintf(buf, sizeof(buf), "%d", bubbleTargetCount);
    drawSettingRow(s, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, "Bubble Amount", buf);

    snprintf(buf, sizeof(buf), "%d/hr", octopusFrequency);
    drawSettingRow(s, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 2, "Octopus Freq", buf);

    snprintf(buf, sizeof(buf), "%d/hr", seahorseFrequency);
    drawSettingRow(s, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 3, "Seahorse Freq", buf);
  } else if (activeSettingsTab == SETTINGS_TAB_SEAWEED) {
    snprintf(buf, sizeof(buf), "%.2f", seaweedSwaySpeed);
    drawSettingRow(s, SETTINGS_ROW_START_Y, "Sway", buf);

    snprintf(buf, sizeof(buf), "%.2f", seaweedLength);
    drawSettingRow(s, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, "Length", buf);

    snprintf(buf, sizeof(buf), "%.2f", seaweedLengthRandomness);
    drawSettingRow(s, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 2, "Length Rand", buf);
  } else if (activeSettingsTab == SETTINGS_TAB_CLOCK) {
    drawClockSettings(s);
  } else {
    drawSettingRow(s, SETTINGS_ROW_START_Y, "Style", backgroundModeName());
    if (backgroundMode == BACKGROUND_FLOWERS) {
      drawActionRow(s, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, "Flowers", "Randomize");
    }
  }

  drawButton(s, SETTINGS_CLOSE_X, SETTINGS_CLOSE_Y, SETTINGS_CLOSE_W, SETTINGS_CLOSE_H, "X", TFT_WHITE, TFT_RED);
  drawSettingsTabs(s);
}

void serviceCaptureAfterDraw(TFT_eSprite& s) {
  if (captureSinglePending) {
    captureSinglePending = false;
    saveNextCaptureFrame(s, false, true);
    return;
  }

  if (!captureSequenceEnabled) return;
  saveNextCaptureFrame(s, true, false);
}

void renderFrame() {
  if (!spriteReady) return;
  float tSec = aquariumTimeSec();
  drawBackground(canvas, tSec);
  drawAsciiClockBackground(canvas);
  drawSeaweed(canvas, tSec);
  drawBubbles(canvas);
  drawFlakes(canvas);
  drawFish(canvas);
  drawOctopus(canvas);
  drawSeahorse(canvas);
  drawClock(canvas);
  drawHud(canvas);
  drawSettingsPanel(canvas);
  drawClockStylePanel(canvas);
  drawClockColorPanel(canvas);
  drawWifiPanel(canvas);
  serviceCaptureAfterDraw(canvas);
  drawCapturePanel(canvas);
  drawCaptureToast(canvas);
  canvas.pushSprite(0, 0);
}

// ------------------------------ Input Handling -------------------------------
bool inside(int x, int y, int rx, int ry, int rw, int rh) {
  return (x >= rx && x < rx + rw && y >= ry && y < ry + rh);
}

void handleWifiPasswordTouch(int x, int y) {
  for (int row = 0; row < 4; ++row) {
    const char* keys = keyboardRowText(row);
    int keyCount = strlen(keys);
    for (int i = 0; i < keyCount; ++i) {
      int keyX, keyY, keyW, keyH;
      keyboardKeyBounds(row, i, keyX, keyY, keyW, keyH);
      if (inside(x, y, keyX, keyY, keyW, keyH)) {
        appendCharSafe(wifiPasswordBuffer, sizeof(wifiPasswordBuffer), keys[i]);
        return;
      }
    }
  }

  if (inside(x, y, WIFI_PANEL_X + 18, WIFI_KEYBOARD_SPECIAL_Y, 56, 22)) {
    keyboardMode = (keyboardMode == KEYBOARD_UPPER) ? KEYBOARD_LOWER : KEYBOARD_UPPER;
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 82, WIFI_KEYBOARD_SPECIAL_Y, 48, 22)) {
    keyboardMode = (keyboardMode == KEYBOARD_SYMBOLS) ? KEYBOARD_LOWER : KEYBOARD_SYMBOLS;
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 138, WIFI_KEYBOARD_SPECIAL_Y, 86, 22)) {
    appendCharSafe(wifiPasswordBuffer, sizeof(wifiPasswordBuffer), ' ');
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 232, WIFI_KEYBOARD_SPECIAL_Y, 56, 22)) {
    removeLastChar(wifiPasswordBuffer);
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 18, WIFI_KEYBOARD_ACTION_Y, 76, 22)) {
    wifiPanelMode = WIFI_PANEL_NETWORKS;
    wifiPasswordBuffer[0] = '\0';
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 226, WIFI_KEYBOARD_ACTION_Y, 76, 22)) {
    startWifiConnect(pendingWifiSsid, wifiPasswordBuffer, true);
    wifiPanelMode = WIFI_PANEL_MAIN;
    return;
  }
}

void handleWifiNetworksTouch(int x, int y) {
  int bottomY = WIFI_PANEL_Y + WIFI_PANEL_H - 30;
  if (inside(x, y, WIFI_PANEL_X + 18, bottomY, 58, 22)) {
    wifiPanelMode = WIFI_PANEL_MAIN;
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 84, bottomY, 58, 22)) {
    if (!wifiEnabled) {
      setWifiEnabled(true);
    } else {
      startWifiScan();
    }
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 184, bottomY, 54, 22)) {
    if (wifiNetworkPage > 0) wifiNetworkPage--;
    return;
  }
  if (inside(x, y, WIFI_PANEL_X + 246, bottomY, 54, 22)) {
    int maxPage = (wifiNetworkCount <= 0) ? 0 : (wifiNetworkCount - 1) / WIFI_LIST_ROW_COUNT;
    if (wifiNetworkPage < maxPage) wifiNetworkPage++;
    return;
  }

  if (wifiScanInProgress) return;
  if (x < WIFI_PANEL_X + 12 || x >= WIFI_PANEL_X + WIFI_PANEL_W - 12) return;
  if (y < WIFI_LIST_ROW_Y || y >= WIFI_LIST_ROW_Y + WIFI_LIST_ROW_COUNT * WIFI_LIST_ROW_H) return;

  int row = (y - WIFI_LIST_ROW_Y) / WIFI_LIST_ROW_H;
  int index = wifiNetworkPage * WIFI_LIST_ROW_COUNT + row;
  if (index < 0 || index >= wifiNetworkCount) return;

  copySafe(pendingWifiSsid, sizeof(pendingWifiSsid), wifiNetworkNames[index]);
  wifiPasswordBuffer[0] = '\0';
  keyboardMode = KEYBOARD_LOWER;
  if (wifiNetworkOpen[index]) {
    startWifiConnect(pendingWifiSsid, "", true);
    wifiPanelMode = WIFI_PANEL_MAIN;
  } else {
    wifiPanelMode = WIFI_PANEL_PASSWORD;
  }
}

void handleWifiMainTouch(int x, int y) {
  if (inside(x, y, WIFI_OFF_X, WIFI_ROW_START_Y, WIFI_TOGGLE_W, WIFI_ROW_H)) {
    setWifiEnabled(false);
    return;
  }
  if (inside(x, y, WIFI_ON_X, WIFI_ROW_START_Y, WIFI_TOGGLE_W, WIFI_ROW_H)) {
    setWifiEnabled(true);
    return;
  }

  int networkY = WIFI_ROW_START_Y + WIFI_ROW_GAP;
  if (inside(x, y, WIFI_ACTION_X, networkY, WIFI_ACTION_W, WIFI_ROW_H) ||
      inside(x, y, WIFI_LABEL_X, networkY, WIFI_PANEL_W - 28, WIFI_ROW_H)) {
    if (!wifiEnabled) setWifiEnabled(true);
    if (!wifiScanInProgress && wifiNetworkCount == 0) startWifiScan();
    wifiPanelMode = WIFI_PANEL_NETWORKS;
    return;
  }

  int timezoneY = WIFI_ROW_START_Y + WIFI_ROW_GAP * 4;
  if (inside(x, y, WIFI_OFF_X, timezoneY, WIFI_TOGGLE_W, WIFI_ROW_H)) {
    cycleTimezone(-1);
    return;
  }
  if (inside(x, y, WIFI_ON_X, timezoneY, WIFI_TOGGLE_W, WIFI_ROW_H)) {
    cycleTimezone(1);
    return;
  }
}

void handleWifiPanelTouch(int x, int y) {
  if (inside(x, y, WIFI_CLOSE_X, WIFI_CLOSE_Y, WIFI_CLOSE_W, WIFI_CLOSE_H)) {
    wifiPanelOpen = false;
    wifiPanelMode = WIFI_PANEL_MAIN;
    return;
  }

  if (wifiPanelMode == WIFI_PANEL_PASSWORD) {
    handleWifiPasswordTouch(x, y);
  } else if (wifiPanelMode == WIFI_PANEL_NETWORKS) {
    handleWifiNetworksTouch(x, y);
  } else {
    handleWifiMainTouch(x, y);
  }
}

void handleCapturePanelTouch(int x, int y) {
  if (inside(x, y, CAPTURE_CLOSE_X, CAPTURE_CLOSE_Y, CAPTURE_CLOSE_W, CAPTURE_CLOSE_H)) {
    capturePanelOpen = false;
    return;
  }

  if (inside(x, y, CAPTURE_ACTION_X, CAPTURE_ROW_START_Y, CAPTURE_ACTION_W, CAPTURE_ROW_H)) {
    checkCaptureSdReady();
    return;
  }

  int saveY = CAPTURE_ROW_START_Y + CAPTURE_ROW_GAP;
  if (inside(x, y, CAPTURE_ACTION_X, saveY, CAPTURE_ACTION_W, CAPTURE_ROW_H)) {
    setCaptureSequenceEnabled(true);
    return;
  }
}

void handleClockColorPanelTouch(int x, int y) {
  if (inside(x, y, CLOCK_COLOR_CLOSE_X, CLOCK_COLOR_CLOSE_Y, CLOCK_COLOR_CLOSE_W, CLOCK_COLOR_CLOSE_H)) {
    clockColorPanelOpen = false;
    return;
  }

  for (int i = 0; i < CLOCK_COLOR_COUNT; ++i) {
    int col = i % CLOCK_COLOR_SWATCH_COLS;
    int row = i / CLOCK_COLOR_SWATCH_COLS;
    int swatchX = CLOCK_COLOR_GRID_X + col * (CLOCK_COLOR_SWATCH_W + CLOCK_COLOR_SWATCH_GAP_X);
    int swatchY = CLOCK_COLOR_GRID_Y + row * (CLOCK_COLOR_SWATCH_H + CLOCK_COLOR_SWATCH_GAP_Y);
    if (inside(x, y, swatchX - 3, swatchY - 3, CLOCK_COLOR_SWATCH_W + 6, CLOCK_COLOR_SWATCH_H + 6)) {
      setActiveClockTextColor(kClockColorPalette[i]);
      clockColorPanelOpen = false;
      return;
    }
  }
}

void handleClockStylePanelTouch(int x, int y) {
  if (inside(x, y, CLOCK_STYLE_CLOSE_X, CLOCK_STYLE_CLOSE_Y, CLOCK_STYLE_CLOSE_W, CLOCK_STYLE_CLOSE_H)) {
    clockStylePanelOpen = false;
    clockColorPanelOpen = false;
    return;
  }

  if (inside(x, y, CLOCK_STYLE_LEFT_X, CLOCK_STYLE_ROW_1_Y, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H)) {
    clockDisplayStyle = CLOCK_STYLE_SMALL_TEXT;
    clockColorPanelOpen = false;
    markSettingsDirty();
    return;
  }
  if (inside(x, y, CLOCK_STYLE_RIGHT_X, CLOCK_STYLE_ROW_1_Y, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H)) {
    clockDisplayStyle = CLOCK_STYLE_ASCII;
    clockColorPanelOpen = false;
    markSettingsDirty();
    return;
  }

  if (inside(x, y, CLOCK_STYLE_SWATCH_X, CLOCK_STYLE_ROW_4_Y, CLOCK_STYLE_SWATCH_W, SETTINGS_BUTTON_H) ||
      inside(x, y, CLOCK_STYLE_COLOR_BUTTON_X, CLOCK_STYLE_ROW_4_Y, CLOCK_STYLE_COLOR_BUTTON_W, SETTINGS_BUTTON_H)) {
    clockColorPanelOpen = true;
    return;
  }

  if (inside(x, y, CLOCK_STYLE_LEFT_X, CLOCK_STYLE_ROW_3_Y, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H)) {
    clockFlipHorizontal = false;
    markSettingsDirty();
    return;
  }
  if (inside(x, y, CLOCK_STYLE_RIGHT_X, CLOCK_STYLE_ROW_3_Y, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H)) {
    clockFlipHorizontal = true;
    markSettingsDirty();
    return;
  }

  if (clockDisplayStyle == CLOCK_STYLE_SMALL_TEXT) {
    if (inside(x, y, CLOCK_STYLE_LEFT_X, CLOCK_STYLE_ROW_2_Y, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H)) {
      clockSmallPosition = CLOCK_SMALL_TOP;
      markSettingsDirty();
      return;
    }
    if (inside(x, y, CLOCK_STYLE_RIGHT_X, CLOCK_STYLE_ROW_2_Y, CLOCK_STYLE_CHOICE_W, SETTINGS_BUTTON_H)) {
      clockSmallPosition = CLOCK_SMALL_BOTTOM;
      markSettingsDirty();
      return;
    }
  }
}

void serviceBootButton(unsigned long now) {
  bool reading = (digitalRead(BOOT_BUTTON_PIN) == LOW);
  if (reading != bootButtonLastReading) {
    bootButtonLastReading = reading;
    bootButtonLastChangeMs = now;
  }

  if (now - bootButtonLastChangeMs < BOOT_BUTTON_DEBOUNCE_MS) return;
  if (reading == bootButtonStablePressed) return;

  bootButtonStablePressed = reading;
  if (bootButtonStablePressed) {
    requestSingleCapture();
  }
}

void processTouch() {
  if (millis() - lastTouchMs < TOUCH_DEBOUNCE_MS) return;
  int x, y;
  if (!readTouchPoint(x, y)) return;
  lastTouchMs = millis();

  // Top-left: HUD toggle
  if (inside(x, y, 0, 0, 42, 26)) {
    stopCaptureRecording(true);
    hudVisible = !hudVisible;
    if (!hudVisible) {
      wifiPanelOpen = false;
      capturePanelOpen = false;
      settingsOpen = false;
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
    }
    return;
  }

  // Hidden capture menu appears with the HUD controls.
  if (hudVisible && inside(x, y, CAPTURE_BUTTON_X, 0, CORNER_BUTTON_W, 26)) {
    capturePanelOpen = !capturePanelOpen;
    if (capturePanelOpen) {
      settingsOpen = false;
      wifiPanelOpen = false;
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
    }
    return;
  }

  // Hidden WiFi menu appears with the HUD controls.
  if (hudVisible && inside(x, y, WIFI_BUTTON_X, 0, CORNER_BUTTON_W, 26)) {
    wifiPanelOpen = !wifiPanelOpen;
    wifiPanelMode = WIFI_PANEL_MAIN;
    if (wifiPanelOpen) {
      settingsOpen = false;
      capturePanelOpen = false;
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
    }
    return;
  }

  // Top-right: settings toggle
  if (hudVisible && inside(x, y, SCREEN_W - 42, 0, 42, 26)) {
    settingsOpen = !settingsOpen;
    if (settingsOpen) {
      wifiPanelOpen = false;
      capturePanelOpen = false;
    } else {
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
    }
    return;
  }

  // Hidden respawn button under Settings: randomize active fish positions/types.
  if (hudVisible && inside(x, y, SETTINGS_CORNER_BUTTON_X, RESPAWN_BUTTON_Y, CORNER_BUTTON_W, CORNER_BUTTON_H)) {
    respawnFishPopulation();
    return;
  }

  // Hidden creature test spawns for final tuning.
  if (hudVisible && inside(x, y, SEAHORSE_TEST_BUTTON_X, SEAHORSE_TEST_BUTTON_Y,
                           CORNER_BUTTON_W, CORNER_BUTTON_H)) {
    spawnSeahorseAtCenter(aquariumNowMs);
    return;
  }
  if (hudVisible && inside(x, y, OCTOPUS_TEST_BUTTON_X, OCTOPUS_TEST_BUTTON_Y,
                           CORNER_BUTTON_W, CORNER_BUTTON_H)) {
    spawnOctopusAtCenter(aquariumNowMs);
    return;
  }

  if (capturePanelOpen) {
    handleCapturePanelTouch(x, y);
    return;
  }

  if (wifiPanelOpen) {
    handleWifiPanelTouch(x, y);
    return;
  }

  if (clockColorPanelOpen) {
    handleClockColorPanelTouch(x, y);
    return;
  }

  if (clockStylePanelOpen) {
    handleClockStylePanelTouch(x, y);
    return;
  }

  if (settingsOpen) {
    if (inside(x, y, SETTINGS_CLOSE_X, SETTINGS_CLOSE_Y, SETTINGS_CLOSE_W, SETTINGS_CLOSE_H)) {
      settingsOpen = false;
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
      return;
    }

    if (inside(x, y, SETTINGS_TANK_TAB_X, SETTINGS_TAB_Y, SETTINGS_TANK_TAB_W, SETTINGS_TAB_H)) {
      activeSettingsTab = SETTINGS_TAB_TANK;
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
      return;
    }
    if (inside(x, y, SETTINGS_SEAWEED_TAB_X, SETTINGS_TAB_Y, SETTINGS_SEAWEED_TAB_W, SETTINGS_TAB_H)) {
      activeSettingsTab = SETTINGS_TAB_SEAWEED;
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
      return;
    }
    if (inside(x, y, SETTINGS_CLOCK_TAB_X, SETTINGS_TAB_Y, SETTINGS_CLOCK_TAB_W, SETTINGS_TAB_H)) {
      activeSettingsTab = SETTINGS_TAB_CLOCK;
      return;
    }
    if (inside(x, y, SETTINGS_BACKGROUND_TAB_X, SETTINGS_TAB_Y, SETTINGS_BACKGROUND_TAB_W, SETTINGS_TAB_H)) {
      activeSettingsTab = SETTINGS_TAB_BACKGROUND;
      clockStylePanelOpen = false;
      clockColorPanelOpen = false;
      return;
    }

    if (activeSettingsTab == SETTINGS_TAB_TANK) {
      // Fish pop -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        fishTargetCount -= 1;
        applyFishPopulation();
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        fishTargetCount += 1;
        applyFishPopulation();
        markSettingsDirty();
        return;
      }

      // Bubble amount -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        bubbleTargetCount -= 1;
        applyBubblePopulation();
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        bubbleTargetCount += 1;
        applyBubblePopulation();
        markSettingsDirty();
        return;
      }

      // Octopus frequency -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 2, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleOctopusFrequency(-1);
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 2, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleOctopusFrequency(1);
        return;
      }

      // Seahorse frequency -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 3, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleSeahorseFrequency(-1);
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 3, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleSeahorseFrequency(1);
        return;
      }
    } else if (activeSettingsTab == SETTINGS_TAB_SEAWEED) {
      // Seaweed sway -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        seaweedSwaySpeed = clampVal(seaweedSwaySpeed - 0.05f, MIN_SWAY, MAX_SWAY);
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        seaweedSwaySpeed = clampVal(seaweedSwaySpeed + 0.05f, MIN_SWAY, MAX_SWAY);
        markSettingsDirty();
        return;
      }

      // Seaweed length -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        seaweedLength = clampVal(seaweedLength - 0.05f, MIN_SEAWEED_LENGTH, MAX_SEAWEED_LENGTH);
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        seaweedLength = clampVal(seaweedLength + 0.05f, MIN_SEAWEED_LENGTH, MAX_SEAWEED_LENGTH);
        markSettingsDirty();
        return;
      }

      // Seaweed length randomness -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 2, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        seaweedLengthRandomness = clampVal(seaweedLengthRandomness - 0.05f, MIN_SEAWEED_LENGTH_RANDOMNESS, MAX_SEAWEED_LENGTH_RANDOMNESS);
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP * 2, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        seaweedLengthRandomness = clampVal(seaweedLengthRandomness + 0.05f, MIN_SEAWEED_LENGTH_RANDOMNESS, MAX_SEAWEED_LENGTH_RANDOMNESS);
        markSettingsDirty();
        return;
      }
    } else if (activeSettingsTab == SETTINGS_TAB_CLOCK) {
      if (inside(x, y, CLOCK_STYLE_BUTTON_X, CLOCK_ROW_1_Y, CLOCK_STYLE_BUTTON_W, SETTINGS_BUTTON_H)) {
        clockStylePanelOpen = true;
        clockColorPanelOpen = false;
        return;
      }

      if (!clockUseInternetTime && inside(x, y, CLOCK_FIELD_PREV_X, CLOCK_FIELD_NAV_Y, CLOCK_FIELD_NAV_W, CLOCK_FIELD_NAV_H)) {
        selectClockField(-1);
        return;
      }
      if (!clockUseInternetTime && inside(x, y, CLOCK_FIELD_NEXT_X, CLOCK_FIELD_NAV_Y, CLOCK_FIELD_NAV_W, CLOCK_FIELD_NAV_H)) {
        selectClockField(1);
        return;
      }

      // Clock visibility buttons
      if (inside(x, y, SETTINGS_MINUS_X, CLOCK_ROW_1_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        clockVisible = false;
        resetClockTick();
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, CLOCK_ROW_1_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        clockVisible = true;
        resetClockTick();
        markSettingsDirty();
        return;
      }

      // Time source buttons
      if (inside(x, y, SETTINGS_MINUS_X, CLOCK_ROW_2_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        clockUseInternetTime = false;
        resetClockTick();
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, CLOCK_ROW_2_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        clockUseInternetTime = true;
        if (!wifiEnabled) {
          setWifiEnabled(true);
        } else if (wifiConnected) {
          beginInternetTimeSync();
        } else if (!wifiConnecting && wifiSsid[0] != '\0') {
          startWifiConnect(wifiSsid, wifiPass, false);
        } else if (!wifiScanInProgress) {
          startWifiScan();
        }
        markSettingsDirty();
        return;
      }

      // Format buttons
      if (inside(x, y, SETTINGS_MINUS_X, CLOCK_ROW_3_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        clockUse24Hour = false;
        markSettingsDirty();
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, CLOCK_ROW_3_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        clockUse24Hour = true;
        markSettingsDirty();
        return;
      }

      // Timezone -/+
      if (inside(x, y, SETTINGS_MINUS_X, CLOCK_ROW_5_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleTimezone(-1);
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, CLOCK_ROW_5_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleTimezone(1);
        return;
      }

      // Selected clock field -/+
      if (!clockUseInternetTime && inside(x, y, SETTINGS_MINUS_X, CLOCK_ROW_4_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        adjustClockField(-1);
        return;
      }
      if (!clockUseInternetTime && inside(x, y, SETTINGS_PLUS_X, CLOCK_ROW_4_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        adjustClockField(1);
        return;
      }
    } else {
      // Background style -/+
      if (inside(x, y, SETTINGS_MINUS_X, SETTINGS_ROW_START_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleBackgroundMode(-1);
        return;
      }
      if (inside(x, y, SETTINGS_PLUS_X, SETTINGS_ROW_START_Y, SETTINGS_BUTTON_W, SETTINGS_BUTTON_H)) {
        cycleBackgroundMode(1);
        return;
      }
      if (backgroundMode == BACKGROUND_FLOWERS &&
          inside(x, y, SETTINGS_ACTION_X, SETTINGS_ROW_START_Y + SETTINGS_ROW_GAP, SETTINGS_ACTION_W, SETTINGS_BUTTON_H)) {
        randomizeFlowers();
        return;
      }
    }
    return;
  }

  // Feed interaction: tap anywhere else to spawn falling flake
  spawnFlake((float)x, (float)y);
}

// ------------------------------ Setup / Loop ---------------------------------
void setup() {
  Serial.begin(115200);
  randomSeed((uint32_t)esp_random());
  loadPersistentState();
  if (wifiEnabled) {
    setWifiStatus(wifiSsid[0] ? "Starting..." : "Ready to scan");
  }

  tft.init();
  tft.setRotation(1);  // 320x240 landscape
  tft.fillScreen(BG_COLOR);
  tft.setTextWrap(false);
  tft.setTextFont(2);
  tft.setTextColor(TFT_GREEN, BG_COLOR);
  tft.setCursor(10, 10);
  tft.println("ASCII Aquarium booting...");

  // Optional: CYD backlight pin if not already driven by board support
  pinMode(21, OUTPUT);
  digitalWrite(21, HIGH);
  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  bootButtonLastReading = (digitalRead(BOOT_BUTTON_PIN) == LOW);
  bootButtonStablePressed = bootButtonLastReading;
  bootButtonLastChangeMs = millis();
  pinMode(SD_CS_PIN, OUTPUT);
  digitalWrite(SD_CS_PIN, HIGH);

  // Main sprite buffer with fallback to 8-bit if 16-bit alloc fails
  canvas.setColorDepth(16);
  spriteReady = (canvas.createSprite(SCREEN_W, SCREEN_H) != nullptr);
  if (!spriteReady) {
    canvas.setColorDepth(8);
    spriteReady = (canvas.createSprite(SCREEN_W, SCREEN_H) != nullptr);
  }
  if (spriteReady) {
    canvas.setTextFont(2);
    clockFlipSprite.setColorDepth(16);
    clockFlipSpriteReady = (clockFlipSprite.createSprite(CLOCK_FLIP_SPRITE_W, CLOCK_FLIP_SPRITE_H) != nullptr);
    if (clockFlipSpriteReady) clockFlipSprite.setTextFont(2);
    tft.setCursor(10, 28);
    tft.setTextColor(TFT_CYAN, BG_COLOR);
    tft.println("Sprite buffer: OK");
  } else {
    tft.setCursor(10, 28);
    tft.setTextColor(TFT_RED, BG_COLOR);
    tft.println("Sprite alloc failed");
    tft.setCursor(10, 46);
    tft.println("Check TFT config/pins");
  }

  // Touch uses dedicated HSPI lines on most CYD boards
  touchSPI.begin(TOUCH_CLK_PIN, TOUCH_MISO_PIN, TOUCH_MOSI_PIN, TOUCH_CS_PIN);
  touchReady = touch.begin(touchSPI);
  if (touchReady) {
    touch.setRotation(1);
    tft.setCursor(10, 64);
    tft.setTextColor(TFT_GREENYELLOW, BG_COLOR);
    tft.println("Touch: OK");
  } else {
    tft.setCursor(10, 64);
    tft.setTextColor(TFT_ORANGE, BG_COLOR);
    tft.println("Touch not detected");
  }

  for (int i = 0; i < MAX_FLAKES; i++) flakes[i].active = false;
  for (int i = 0; i < MAX_BUBBLES; i++) bubbles[i].active = false;
  for (int i = 0; i < MAX_FISH_POOL; i++) fishPool[i].active = false;
  octopus.active = false;
  octopus.nextSpawnMs = 0;
  seahorse.active = false;
  seahorse.nextSpawnMs = 0;
  initFishMirrors();
  initFishGlyphMetrics();
  applyFishPopulation();
  spreadInitialFishLayout();
  applyBubblePopulation(true);

  delay(350);
  lastMs = millis();
  aquariumNowMs = lastMs;
  clockLastMinuteMs = lastMs;
  lastSettingsSaveMs = lastMs;
  fpsTimer = lastMs;
  frameCount = 0;
}

void loop() {
  unsigned long now = millis();
  unsigned long elapsedMs = now - lastMs;
  lastMs = now;

  // Keep services on real millis(), but decouple visible motion from SD write stalls.
  unsigned long aquariumStepMs = captureSequenceEnabled ? CAPTURE_RECORD_FRAME_MS : clampVal(elapsedMs, 1UL, 50UL);
  aquariumNowMs += aquariumStepMs;
  float dt = aquariumStepMs * 0.001f;

  updateClock(now);
  serviceBootButton(now);
  processTouch();
  serviceWifi(now);
  serviceSettingsPersistence(now);
  updateFlakes(dt);
  updateBubbles(dt);
  updateFish(dt);
  updateOctopus(aquariumNowMs, dt);
  updateSeahorse(aquariumNowMs, dt);
  keepVisitorsSeparated();
  renderFrame();

  frameCount++;
  if (now - fpsTimer >= 500) {
    fps = (frameCount * 1000.0f) / (now - fpsTimer + 1);
    frameCount = 0;
    fpsTimer = now;
  }
}
