#pragma once
// apps/matrixApp.h — MatrixApp component (M-SRCLAYOUT Stage E / TASK-471).
// Self-contained per D0/SF.11: declares its own dependencies rather than
// relying on main.cpp's include order. Method bodies live in matrixApp.cpp.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "settingsStorage.h"  // g_settings, AppSpeed, MatrixColor

#include "display/tft.h"

#define MATRIX_STREAMS    14
#define MATRIX_STRIDE     19
#define MATRIX_TICK_MS    25
// M-CODEQUAL C5 (TASK-461): was an independent `275` literal; now the one
// canonical source (gen/shell_layout.h's APP_CANVAS_W, visible via
// appShell.h's include of it above).
#define MATRIX_CANVAS_W  APP_CANVAS_W
#define MATRIX_CANVAS_H  240

struct MatrixAppState {
    struct Column {
        int   x;
        float y;
        float speed;
        int   length;
        char  lastChar;
    } rain[MATRIX_STREAMS];
    bool initialised;
};

class MatrixApp : public App {
public:
  // TASK-518 (P4): no hasInFlightOp() override — pure local animation, no
  // async work of any kind. Inherits the App default (false), which is true.

  void init() override;
  void resume() override;
  void suspend() override {}
  void tick() override;
  bool handleInput(TouchPhase phase, int, int) override;

#ifdef SERIAL_DEBUG
  bool dbgGet(const char* var, char* buf, int len) const;
#endif

private:
  MatrixAppState _s;
  unsigned long  _lastTickMs = 0;
  uint16_t      _headColor = TFT_WHITE;
  uint16_t      _tailColor = TFT_GREEN;
  unsigned long _tickMs    = MATRIX_TICK_MS;

  void _applyMatrixSettings();
  void initMatrixState();
  void repaintMatrix();
  void matrixTick();
};
