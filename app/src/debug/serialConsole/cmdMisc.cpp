// debug/serialConsole/cmdMisc.cpp — switchapp / info / screendump / colorprobe,
// out-of-line (M-SRCLAYOUT Stage E / TASK-471). Body compiles only under
// SERIAL_DEBUG; the .cpp itself is always compiled, same convention as
// appTable.cpp / cmdSystem.cpp.
#include "debug/serialConsole/cmdMisc.h"

#ifdef SERIAL_DEBUG
#include <Arduino.h>
#include <TFT_eSPI.h>
#include <esp_ota_ops.h>   // esp_ota_get_app_description() for `info`
#include <esp_task_wdt.h>  // esp_task_wdt_reset() during screendump's ~18s stream
#include <mbedtls/base64.h>
#include "appShell.h"      // AppId, switchApp()
#include "spotifyTask.h"

#include "display/tft.h"

void cmdSwitchApp(const char *args) {
  int id = -1;
  if (sscanf(args, "%d", &id) != 1 || id < 0 || id >= (int)AppId::COUNT) {
    Serial.printf("{\"ok\":false,\"cmd\":\"switchApp\","
                  "\"error\":\"bad id — range 0..%d\"}\n", (int)AppId::COUNT - 1);
    return;
  }
  switchApp(static_cast<AppId>(id));
  Serial.printf("{\"ok\":true,\"cmd\":\"switchApp\",\"id\":%d}\n", id);
}

void cmdInfo(const char *) {
  spotifyTask::Snapshot snap;
  spotifyTask::copySnapshot(&snap);
  const esp_app_desc_t *d = esp_ota_get_app_description();
  char elf[9];
  snprintf(elf, sizeof(elf), "%02x%02x%02x%02x",
           d->app_elf_sha256[0], d->app_elf_sha256[1],
           d->app_elf_sha256[2], d->app_elf_sha256[3]);
  Serial.printf(
    "{\"ok\":true,\"cmd\":\"info\","
    "\"git\":\"%s\",\"elf\":\"%s\",\"build\":\"%s %s\","
    "\"heap\":%lu,\"isPlaying\":%s,\"progressMs\":%ld,"
    "\"durationMs\":%ld,\"volumePct\":%d,"
    "\"shuffle\":%s,\"repeat\":%d,\"consecutiveFailures\":%u}\n",
#ifdef GIT_REV
    GIT_REV,
#else
    "n/a",
#endif
    elf, __DATE__, __TIME__,
    (unsigned long)ESP.getFreeHeap(),
    snap.isPlaying ? "true" : "false",
    snap.progressMs,
    snap.durationMs,
    (int)snap.volumePercent,
    snap.shuffleState ? "true" : "false",
    (int)snap.repeatState,
    spotifyTask::dbg_getFailureCount());
}

// Reads back the live TFT GRAM over SPI (MISO wired, TFT_MISO=12,
// SPI_READ_FREQUENCY=2.5MHz — see app/platformio.ini, lowered from 20MHz by
// TASK-340: 20MHz was signal-integrity-unreliable on this board's MISO read)
// and streams it out as base64 RGB565 bands. Lets a host tool pull an exact
// screenshot instead of
// a human eyeballing the DUT — see app/tools/screendump.py.
void cmdScreenDump(const char *args) {
  // M-CODEQUAL C5 (TASK-461): was raw 320/240 literals — SCREEN_W/SCREEN_H
  // are the whole-panel dims (this command reads back the full physical
  // display, not just the app canvas).
  int x = 0, y = 0, w = SCREEN_W, h = SCREEN_H;
  sscanf(args, "%d %d %d %d", &x, &y, &w, &h);
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  if (w <= 0 || x + w > SCREEN_W) w = SCREEN_W - x;
  if (h <= 0 || y + h > SCREEN_H) h = SCREEN_H - y;
  if (w <= 0 || h <= 0) {
    Serial.println("{\"ok\":false,\"cmd\":\"screendump\",\"error\":\"empty region\"}");
    return;
  }

  static const int kBandRows = 8;                       // 320*8*2 = 5120 B/band
  // TASK-423: heap-allocated per invocation (was function-static) — returns
  // the 12 KB to the heap between screendump calls instead of pinning it in
  // .bss for the life of the process; this command runs ~18s on-demand from
  // a host tool, not on any hot path, so the malloc cost is irrelevant.
  const size_t kB64Size = ((SCREEN_W * kBandRows * 2 + 2) / 3) * 4 + 8;
  uint16_t *s_band = (uint16_t *)malloc(sizeof(uint16_t) * SCREEN_W * kBandRows);
  unsigned char *s_b64 = (unsigned char *)malloc(kB64Size);
  if (!s_band || !s_b64) {
    free(s_band);
    free(s_b64);
    Serial.println("{\"ok\":false,\"cmd\":\"screendump\",\"error\":\"alloc failed\"}");
    return;
  }

  Serial.printf("{\"ok\":true,\"cmd\":\"screendump\",\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d,\"bpp\":16}\n",
                x, y, w, h);

  for (int ry = 0; ry < h; ry += kBandRows) {
    // TASK-288 pattern: a full-canvas dump is ~30 bands x ~590ms of Serial.write
    // at 115200 baud (~18s total) — comfortably over the 15s TWDT panic timeout
    // (esp_task_wdt_init(15, true), main.cpp setup()) with zero feeds otherwise.
    // Without this the loop task panics mid-dump and the device hard-resets —
    // the host then keeps reading post-reboot output none the wiser, silently
    // splicing in whatever the fresh boot's default screen happens to show.
    esp_task_wdt_reset();
    int rows = min(kBandRows, h - ry);
    tft.readRect(x, y + ry, w, rows, s_band);
    // TASK-340: tft.readRect() (vendored TFT_eSPI.cpp ~line 1412-1413) returns
    // each pixel byte-swapped ("Swapped colour byte order for compatibility
    // with pushRect()") — deliberate upstream behaviour so its output can be
    // fed straight back into pushRect(), but NOT standard RGB565. Undo it
    // here so the stream this command emits is true RGB565, matching what
    // screendump.py's rgb565_to_rgb888() already (correctly) assumes.
    // DUT-confirmed via `colorprobe` (main.cpp cmdColorProbe): a systematic
    // fillRect/pushRect + readRect sweep matched this byte-swap exactly,
    // 25/25, once SPI_READ_FREQUENCY was lowered — see next comment.
    for (int i = 0; i < w * rows; i++) {
      uint16_t v = s_band[i];
      s_band[i] = (v << 8) | (v >> 8);
    }
    size_t inLen = (size_t)w * rows * 2;
    size_t outLen = 0;
    mbedtls_base64_encode(s_b64, kB64Size, &outLen, (const unsigned char *)s_band, inLen);
    Serial.printf("SCREENDUMP:BAND %d %d ", ry, rows);
    Serial.write(s_b64, outLen);
    Serial.println();
  }
  Serial.println("SCREENDUMP:END");
  free(s_band);
  free(s_b64);
}

// TASK-340 investigation aid: fills a small on-screen swatch with a *known*
// RGB565 value, then reads it straight back with tft.readRect() and prints
// expected vs. actual as one JSON line per probe. Two probe families:
//   - "fill": tft.fillRect(v) then readRect — exercises the normal write
//     path (color565-quantized 16bpp write) + the 18bpp GRAM read-back.
//   - "push": tft.pushRect() with a raw uint16 array (bypasses fillRect's
//     color565 encode — pushRect disables _swapBytes and writes the words
//     as-is) then readRect — isolates whether a fault survives a pure
//     write/read round trip of an arbitrary bit pattern (0xAAAA/0x5555/
//     0xDEADBEEF-style words), vs. only showing up on "real" colours.
// `actual` is the *raw, unmodified* return from tft.readRect() (i.e.
// including that function's own "swapped for pushRect() compatibility"
// byte swap) — deliberately not pre-corrected, so the transform can be
// derived from this data rather than assumed. See docs/project/tasks.md
// TASK-340 for findings.
void cmdColorProbe(const char *) {
  static const uint16_t kFillSweep[] = {
    0xF800, 0x07E0, 0x001F, 0xFFFF, 0x0000, 0xF81F, 0x07FF, 0xFFE0,
    0x8000, 0x0400, 0x0010, 0x7800, 0x03E0, 0x000F, 0x4208, 0x9492,
  };
  static const uint16_t kPushSweep[] = {
    0xAAAA, 0x5555, 0x1234, 0x4321, 0xDEAD, 0xBEEF, 0xCAFE, 0x0F0F, 0xF0F0,
  };
  const int px = 40, py = 40, sz = 8;
  const size_t nFill = sizeof(kFillSweep) / sizeof(kFillSweep[0]);
  const size_t nPush = sizeof(kPushSweep) / sizeof(kPushSweep[0]);

  Serial.println("{\"ok\":true,\"cmd\":\"colorprobe\"}");

  for (size_t i = 0; i < nFill; i++) {
    uint16_t v = kFillSweep[i];
    tft.fillRect(px, py, sz, sz, v);
    delay(2);
    uint16_t band[4] = {0};
    tft.readRect(px + 2, py + 2, 2, 2, band);
    bool last = (i + 1 == nFill) && (nPush == 0);
    Serial.printf("{\"probe\":\"fill\",\"expected\":%u,\"actual\":%u,\"last\":%s}\n",
                  (unsigned)v, (unsigned)band[0], last ? "true" : "false");
  }

  for (size_t i = 0; i < nPush; i++) {
    uint16_t v = kPushSweep[i];
    uint16_t block[4] = {v, v, v, v};
    tft.pushRect(px, py, 2, 2, block);
    delay(2);
    uint16_t band[4] = {0};
    tft.readRect(px, py, 2, 2, band);
    bool last = (i + 1 == nPush);
    Serial.printf("{\"probe\":\"push\",\"expected\":%u,\"actual\":%u,\"last\":%s}\n",
                  (unsigned)v, (unsigned)band[0], last ? "true" : "false");
  }
}
#endif // SERIAL_DEBUG
