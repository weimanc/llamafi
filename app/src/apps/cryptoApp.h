#pragma once
// apps/cryptoApp.h — CryptoApp, moved verbatim out of main.cpp (M-SRCLAYOUT).
// Pure move: no logic change, no reordering.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"

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

static const char* cgIdToDisplay(const char* id) {
  if (strcmp(id, "bitcoin")      == 0) return "BTC";
  if (strcmp(id, "ethereum")     == 0) return "ETH";
  if (strcmp(id, "binancecoin")  == 0) return "BNB";
  if (strcmp(id, "solana")       == 0) return "SOL";
  if (strcmp(id, "ripple")       == 0) return "XRP";
  if (strcmp(id, "cardano")      == 0) return "ADA";
  if (strcmp(id, "dogecoin")     == 0) return "DOGE";
  if (strcmp(id, "avalanche-2")  == 0) return "AVAX";
  if (strcmp(id, "matic-network")== 0) return "MATIC";
  if (strcmp(id, "chainlink")    == 0) return "LINK";
  if (strcmp(id, "polkadot")     == 0) return "DOT";
  if (strcmp(id, "litecoin")     == 0) return "LTC";
  return id;
}

static String formatCryptoPrice(float price) {
  if (price < 1.0f)     return String(price, 4);
  if (price < 1000.0f)  return String(price, 2);
  return String((int)price);
}

class CryptoApp : public App {
public:
  void init() override {
    dataTask::configureCrypto(
        const_cast<const char(*)[16]>(g_settings.cryptoCoins),
        g_settings.cryptoCcy);
    repaintCrypto();
    dataTask::enqueue(dataTask::DATA_FETCH_CRYPTO);
    _s.lastCryptoFetch = millis();
  }
  void resume() override {
    dataTask::configureCrypto(
        const_cast<const char(*)[16]>(g_settings.cryptoCoins),
        g_settings.cryptoCcy);
    repaintCrypto();
    _s.lastCryptoFetch = 0;  // force fresh fetch on next tick
  }
  void suspend() override {}
  void tick()    override { cryptoTick(); }
  bool handleInput(TouchPhase, int, int) override { return false; }
  // TASK-518 (P4): NO hasInFlightOp() override — identical reasoning to
  // WeatherApp. Crypto holds no pending flag; cryptoTick() enqueues on a
  // cadence and consumes whatever pollCrypto() returns, so the in-flight fact
  // lives in dataTask and reaches `get idle` through its dataq term.
  // isConnecting() NOT reusable: !s_cxDataReady is a never-had-data latch.
  // TASK-245 / ADR-046: amber "connecting" bar until the first crypto fetch lands.
  bool isConnecting() const override { return !s_cxDataReady; }
  // TASK-246: red bar when the last crypto fetch failed (cleared on next success).
  bool hasError() const override { return _cxErr; }

private:
  CryptoAppState _s = {};
  bool           _cxErr = false;

  void repaintCrypto() {
    tft.fillRect(0, CX_CANVAS_Y, 275, CX_CANVAS_H, TFT_BLACK);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(0xFFE0);
    tft.drawString("CRYPTO TERMINAL", CX_COL_SYM, CX_HEADER_Y, 2);
    tft.drawFastHLine(0, CX_RULE_Y, 270, 0x07FF);
    int yPos = CX_ROW_Y0;
    for (int i = 0; i < CRYPTO_COIN_COUNT; i++) {
      tft.setTextColor(0xFFFF);
      tft.drawString(cgIdToDisplay(g_settings.cryptoCoins[i]), CX_COL_SYM, yPos + 11, 2);
      tft.setTextColor(0x07FF);
      tft.drawString(_s.lastCryptoFetch ? formatCryptoPrice(_s.prices[i])
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
    if (dataTask::pollCrypto(&r)) {
      _s.lastCryptoFetch = now;
      if (r.ok) {
        for (int i = 0; i < CRYPTO_COIN_COUNT; i++) {
          _s.prices[i]  = r.prices[i];
          _s.changes[i] = r.changes[i];
        }
        s_cxDataReady = true;
        _cxErr = false;
        repaintCrypto();
      } else {
        _cxErr = true;   // TASK-246: failed fetch → red bar
      }
    }
  }

#ifdef SERIAL_DEBUG
public:
  bool dbgGet(const char* var, char* buf, int len) const {
    for (int i = 0; i < 6; i++) {
      char key[16]; snprintf(key, sizeof(key), "cryptoCoin%d", i);
      if (strcmp(var, key) == 0) {
        snprintf(buf, len, "\"var\":\"%s\",\"val\":\"%s\",\"last\":true",
                 key, g_settings.cryptoCoins[i]);
        return true;
      }
    }
    if (strcmp(var, "cryptoCcy") == 0) {
      snprintf(buf, len, "\"var\":\"cryptoCcy\",\"val\":\"%s\",\"last\":true",
               g_settings.cryptoCcy);
      return true;
    }
    if (strcmp(var, "cryptoLastFetch") == 0) {
      snprintf(buf, len, "\"var\":\"cryptoLastFetch\",\"val\":%lu,\"last\":true",
               _s.lastCryptoFetch);
      return true;
    }
    if (strcmp(var, "cryptoHttpCode") == 0) {
      snprintf(buf, len, "\"var\":\"cryptoHttpCode\",\"val\":%d,\"last\":true",
               dataTask::lastCryptoHttpCode());
      return true;
    }
    return false;
  }
#endif
};
