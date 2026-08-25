#pragma once
// apps/settingsApp.h — SettingsApp component (M-SRCLAYOUT Stage E / TASK-471).
// Self-contained per D0/SF.11. Method bodies live in settingsApp.cpp.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "shell/shellState.h"   // ShellState::previous (M-SRCLAYOUT D3)
#include "settingsStorage.h"
#include "CYD28_TouchscreenR.h"   // CYD28_TouchR — class decl only, for the extern below
#include "ui/palette.h"           // M-CODEQUAL C6 (TASK-463): UI_BG_COLOR/UI_SEP_COLOR

extern TFT_eSPI  tft;
extern CYD28_TouchR ts;   // defined once, in cheapYellowLCD.h's touchScreen.h chain

// ── SettingsApp constants (TASK-141a) ─────────────────────────────────
#define SETTINGS_HEADER_H         28
#define SETTINGS_CONTENT_Y        28
#define SETTINGS_CONTENT_H       212
#define SETTINGS_CAT_COUNT         7
#define SETTINGS_ROW_H            26
#define SETTINGS_ROW_COL_LABEL     8
#define SETTINGS_ROW_COL_VALUE   268
#define SETTINGS_ROW_MAX           8
// M-CODEQUAL C6 (TASK-463): were independent literals; now aliases for the
// one canonical source (ui/palette.h).
#define SETTINGS_BG_RGB565      UI_BG_COLOR
#define SETTINGS_SEP_COLOR      UI_SEP_COLOR
#define SETTINGS_HEADER_TXT     0xFFFF
#define SETTINGS_LABEL_COLOR    0xFFFF
#define SETTINGS_VALUE_COLOR    0x07FF
#define SETTINGS_CHEVRON_COLOR  UI_SEP_COLOR
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
  void init() override;
  void resume() override;

  bool hasPendingAsync() const override { return _apps.isValidating(); }

  // TASK-518 (P4): Settings has no async work of its own — the operations
  // belong to whichever section is pushed, so this delegates instead of
  // reusing hasPendingAsync(), which hardcodes ONE section's ONE operation
  // (_apps.isValidating()) and is blind to the geocode lookup in that same
  // section and to WifiSection's connect. With no section pushed, the
  // category list is a pure render — idle.
  //
  // isConnecting() was not reusable because SettingsApp does not implement it
  // at all: it inherits App's `return false`, which would report a device
  // mid-WiFi-connect as quiescent.
  bool hasInFlightOp() const override {
    return _activeSection ? _activeSection->hasInFlightOp() : false;
  }

  void suspend() override {
    if (_activeSection) { _activeSection->leave(); _activeSection = nullptr; }
    _s.section = -1;
  }

  void tick() override;

  void openSection(int idx) { _onCategoryTap(idx); }

  bool handleInput(TouchPhase phase, int x, int y) override;

#ifdef SERIAL_DEBUG
  bool dbgGet(const char* var, char* buf, int len) const;

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

  void _popSection();
  void _cancel();
  void _onCategoryTap(int idx);
  void repaintHeader(const char* title);
  void repaintCategoryList();
};
