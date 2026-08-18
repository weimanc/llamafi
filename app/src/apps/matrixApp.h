#pragma once
// apps/matrixApp.h — MatrixApp, moved verbatim out of main.cpp (M-SRCLAYOUT).
// Pure move: no logic change, no reordering.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"

// ── MatrixApp (matrix.md) ──────────────────────────────────────────────
#define MATRIX_STREAMS    14
#define MATRIX_STRIDE     19
#define MATRIX_TICK_MS    25
#define MATRIX_CANVAS_W  275
#define MATRIX_CANVAS_H  240

class MatrixApp : public App {
public:
  // TASK-518 (P4): no hasInFlightOp() override — pure local animation, no
  // async work of any kind. Inherits the App default (false), which is true.

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
