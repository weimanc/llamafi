// rig/bare_bod — PROP-011 F-4. Minimal firmware carrying ONLY the brownout
// instrument plus the loads under test, so X-P2 can find which load carries the
// boot-window sag. Rungs (build flags, added on top of each other):
//   (none)        CPU + flash only
//   -DBARE_WIFI   WiFi STA connect (credentials from gitignored secrets.h)
//   -DBARE_TFT    display init + backlight full on
//   -DBARE_SD     SD mount on the CYD's VSPI pins
// -DBARE_BOD_THRES=<0..7> is the level the comparator arms at (default 7).
// Serial lines match the product's formats ([bootphase], [bootreason],
// [bod] armed / TRIP) so rigwatch and rig_ladder.py parse them unchanged.
#include <Arduino.h>
#include <esp_system.h>
#include "debug/bodWatch.h"
#ifdef BARE_WIFI
#include <WiFi.h>
#include "secrets.h"
#endif
#ifdef BARE_TFT
#include <TFT_eSPI.h>
TFT_eSPI tft;
#endif
#ifdef BARE_SD
#include <SPI.h>
#include <SD.h>
SPIClass sdSPI(VSPI);
#endif

#ifndef BARE_BOD_THRES
#define BARE_BOD_THRES 7
#endif

static void phase(int n, const char *name) {
  bodWatchSetCtxBoot((uint8_t)n);
  Serial.printf("[bootphase] %d %s\n", n, name);
}

void setup() {
  Serial.begin(115200);
  phase(0, "reset");
  static const char *kNames[] = {"UNKNOWN", "POWERON", "EXT", "SW", "PANIC", "INT_WDT",
                                 "TASK_WDT", "WDT", "DEEPSLEEP", "BROWNOUT", "SDIO"};
  const int rr = (int)esp_reset_reason();
  Serial.printf("[bootreason] %d %s\n", rr, (rr >= 0 && rr <= 10) ? kNames[rr] : "OUT_OF_RANGE");
  bodWatchArm(BARE_BOD_THRES);
  Serial.printf("[bare] rungs wifi=%d tft=%d sd=%d thres=%d\n",
#ifdef BARE_WIFI
                1,
#else
                0,
#endif
#ifdef BARE_TFT
                1,
#else
                0,
#endif
#ifdef BARE_SD
                1,
#else
                0,
#endif
                BARE_BOD_THRES);

#ifdef BARE_SD
  phase(1, "fs");
  sdSPI.begin(18, 19, 23, 5);
  Serial.printf("[bare] sd mounted=%d\n", (int)SD.begin(5, sdSPI, 20000000, "/sd", 3));
#endif
#ifdef BARE_TFT
  phase(2, "display");
  tft.init();
  tft.setRotation(1);
  tft.fillScreen(TFT_WHITE);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);
#endif
  phase(3, "wifi");
#ifdef BARE_WIFI
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  const unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) delay(100);
  if (WiFi.status() == WL_CONNECTED)
    Serial.printf("[wifi] IP %s\n", WiFi.localIP().toString().c_str());
  else
    Serial.println("[wifi] FAILED");
#endif
  // Same checkpoint name as the product, so tag=wifi-end is the boot-window trip
  // whether or not this rung has WiFi.
  bodWatchPoll("wifi-end");
  phase(6, "ready");
}

void loop() {
  bodWatchTick();
  static unsigned long last = 0;
  if (millis() - last >= 5000) {
    last = millis();
    Serial.printf("[hb] uptime=%lu\n", millis() / 1000);
  }
  delay(10);
}
