// apps/settingsApp.cpp — SettingsApp method bodies, out-of-line (M-SRCLAYOUT Stage E).
#include "apps/settingsApp.h"

void SettingsApp::init() {
  _sections[0] = &_wifi;
  _sections[1] = &_time;
  _sections[2] = &_cal;
  _sections[3] = &_disp;
  _sections[4] = &_led;
  _sections[5] = &_apps;
  _sections[6] = &_system;
  repaintCategoryList();
}

void SettingsApp::resume() {
  _snapshot = g_settings;
  if (_activeSection) _activeSection->repaint();
  else repaintCategoryList();
}

void SettingsApp::tick() {
  if (_activeSection) {
    SectionResult tr = _activeSection->tick();
    if (tr == SectionResult::NavigateHome) {
      _activeSection->leave();
      _activeSection = nullptr;
      _s.section = -1;
      switchApp(shell::state().previous);
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

bool SettingsApp::handleInput(TouchPhase phase, int x, int y) {
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
  if (y < SETTINGS_HEADER_H && x < 60) { switchApp(shell::state().previous); return true; }
  int cancelRowTop = SETTINGS_CONTENT_Y + SETTINGS_CAT_COUNT * SETTINGS_ROW_H + 1;
  if (y >= cancelRowTop && y < cancelRowTop + SETTINGS_ROW_H) { _cancel(); return true; }
  int row = (y - SETTINGS_HEADER_H) / SETTINGS_ROW_H;
  if (row >= 0) _onCategoryTap(row);
  return true;
}

#ifdef SERIAL_DEBUG
bool SettingsApp::dbgGet(const char* var, char* buf, int len) const {
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
#endif

void SettingsApp::_popSection() {
  if (_activeSection) { _activeSection->leave(); _activeSection = nullptr; }
  _s.section = -1;
  repaintCategoryList();
}

void SettingsApp::_cancel() {
  g_settings = _snapshot;
  SettingsStorage::save();
  switchApp(shell::state().previous);
}

void SettingsApp::_onCategoryTap(int idx) {
  if (idx < 0 || idx >= SETTINGS_CAT_COUNT) return;
  _s.section = (int8_t)idx;
  // All SETTINGS_CAT_COUNT sections are wired in the ctor (_sections[0..6]),
  // so this is always non-null; the guard is kept as cheap defence only.
  if (_sections[idx]) {
    _activeSection = _sections[idx];
    _activeSection->enter();
  }
}

void SettingsApp::repaintHeader(const char* title) {
  tft.fillRect(0, 0, 275, SETTINGS_HEADER_H, SETTINGS_BG_RGB565);
  tft.setTextColor(SETTINGS_HEADER_TXT);
  tft.setTextDatum(ML_DATUM);
  tft.drawString("< back", 4, 14, 2);
  tft.setTextDatum(MR_DATUM);
  tft.drawString(title, 271, 14, 2);
  tft.drawFastHLine(0, SETTINGS_HEADER_H - 1, 275, SETTINGS_SEP_COLOR);
  tft.setTextDatum(TL_DATUM);
}

void SettingsApp::repaintCategoryList() {
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
