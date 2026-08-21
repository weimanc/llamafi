#pragma once
// apps/cryptoApp.h — CryptoApp component (M-SRCLAYOUT Stage E / TASK-471).
// Self-contained per D0/SF.11. Method bodies live in cryptoApp.cpp.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"

extern TFT_eSPI tft;

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

struct CryptoAppState {
    float         prices[CRYPTO_COIN_COUNT];
    float         changes[CRYPTO_COIN_COUNT];
    unsigned long lastCryptoFetch;
};

const char* cgIdToDisplay(const char* id);

class CryptoApp : public App {
public:
  void init() override;
  void resume() override;
  void suspend() override {}
  void tick()    override;
  bool handleInput(TouchPhase, int, int) override { return false; }
  // TASK-518 (P4): NO hasInFlightOp() override — identical reasoning to
  // WeatherApp. Crypto holds no pending flag; cryptoTick() enqueues on a
  // cadence and consumes whatever pollCrypto() returns, so the in-flight fact
  // lives in dataTask and reaches `get idle` through its dataq term.
  // isConnecting() NOT reusable: !_dataReady is a never-had-data latch.
  // TASK-245 / ADR-046: amber "connecting" bar until the first crypto fetch lands.
  bool isConnecting() const override { return !_dataReady; }
  // TASK-246: red bar when the last crypto fetch failed (cleared on next success).
  bool hasError() const override { return _cxErr; }

  // TASK-471: `_dataReady` used to be a composition-root static
  // (`s_cxDataReady`) read directly by cmdGet.h; not reachable once this app
  // left main.cpp's translation unit, so it is now a real member + accessor.
  bool dataReady() const { return _dataReady; }

#ifdef SERIAL_DEBUG
  bool dbgGet(const char* var, char* buf, int len) const;
#endif

private:
  CryptoAppState _s = {};
  bool           _cxErr = false;
  bool           _dataReady = false;

  void repaintCrypto();
  void cryptoTick();
};
