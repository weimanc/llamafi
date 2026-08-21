#pragma once
// apps/lifeApp.h — LifeApp component (M-SRCLAYOUT Stage E / TASK-471).
// Self-contained per D0/SF.11. Method bodies live in lifeApp.cpp.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "settingsStorage.h"

extern TFT_eSPI tft;

#define GOL_GRID_W       55
#define GOL_GRID_H       48
#define GOL_CELL_PX       5
#define GOL_CELL_FILL     4
#define GOL_TICK_MS     100
#define GOL_STAGNATION  120
#define GOL_MIN_ALIVE     5
#define GOL_INIT_DENSITY 20

struct LifeAppState {
    uint8_t  grid[GOL_GRID_W][GOL_GRID_H];
    uint16_t hueShift;
    int      lastCellCount;
    int      sameCountTimer;
    bool     initialised;
};

class LifeApp : public App {
public:
  // TASK-518 (P4): no hasInFlightOp() override — pure local simulation, no
  // async work of any kind. Inherits the App default (false), which is true.

  void init() override { spawnLife(_s); resume(); }
  void resume() override;
  void suspend() override {}
  void tick() override { golTick(); }
  bool handleInput(TouchPhase phase, int, int) override;

  // TASK-471: was a composition-root static (`s_golAliveCount`) read directly
  // by cmdGet.h; not reachable once this app left main.cpp's translation
  // unit, so it is now a real member + accessor.
  int golAliveCount() const { return _golAliveCount; }

#ifdef SERIAL_DEBUG
  bool dbgGet(const char* var, char* buf, int len) const;
#endif

private:
  LifeAppState  _s;
  unsigned long _lastTickMs = 0;
  unsigned long _tickMs    = GOL_TICK_MS;
  bool          _monoColor = false;
  int           _golAliveCount = -1;   // -1 = never ticked; ≥0 = last alive count
  static uint8_t s_nextGrid[GOL_GRID_W][GOL_GRID_H];

  void _applyLifeSettings();
  void spawnLife(LifeAppState &s);
  void repaintLife(LifeAppState &s);
  void stepGeneration(LifeAppState &s);
  void golTick();
};
