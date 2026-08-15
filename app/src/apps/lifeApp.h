#pragma once
// apps/lifeApp.h — LifeApp, moved verbatim out of main.cpp (M-SRCLAYOUT).
// Pure move: no logic change, no reordering.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "settingsStorage.h"

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
