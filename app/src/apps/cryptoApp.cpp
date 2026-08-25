// apps/cryptoApp.cpp — CryptoApp method bodies, out-of-line (M-SRCLAYOUT Stage E).
#include "apps/cryptoApp.h"

// TASK-471: was `static` in the old all-inline header, sharing internal
// linkage by declaration order with settings/appsSection.h's forward decl.
// Now a separate TU (cryptoApp.cpp) needs external linkage for that
// cross-TU call to resolve, so this is no longer static.
const char* cgIdToDisplay(const char* id) {
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

void CryptoApp::init() {
  dataTask::configureCrypto(
      const_cast<const char(*)[16]>(g_settings.cryptoCoins),
      g_settings.cryptoCcy);
  repaintCrypto();
  dataTask::enqueue(dataTask::DATA_FETCH_CRYPTO);
  _s.lastCryptoFetch = millis();
}

void CryptoApp::resume() {
  dataTask::configureCrypto(
      const_cast<const char(*)[16]>(g_settings.cryptoCoins),
      g_settings.cryptoCcy);
  repaintCrypto();
  _s.lastCryptoFetch = 0;  // force fresh fetch on next tick
}

void CryptoApp::tick() { cryptoTick(); }

void CryptoApp::repaintCrypto() {
  tft.fillRect(0, CX_CANVAS_Y, APP_CANVAS_W, CX_CANVAS_H, TFT_BLACK);   // M-CODEQUAL C5 (TASK-461)
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

void CryptoApp::cryptoTick() {
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
      _dataReady = true;
      _cxErr = false;
      repaintCrypto();
    } else {
      _cxErr = true;   // TASK-246: failed fetch → red bar
    }
  }
}

#ifdef SERIAL_DEBUG
bool CryptoApp::dbgGet(const char* var, char* buf, int len) const {
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
