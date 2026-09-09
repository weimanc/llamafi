// debug/serialConsole/cmdMisc.cpp — switchapp / info / screendump / colorprobe,
// out-of-line (M-SRCLAYOUT Stage E / TASK-471). Body compiles only under
// SERIAL_DEBUG; the .cpp itself is always compiled, same convention as
// appTable.cpp / cmdSystem.cpp.
#include "debug/serialConsole/cmdMisc.h"

#ifdef SERIAL_DEBUG
#include <Arduino.h>
#include <string.h>
#include <TFT_eSPI.h>
#include <esp_ota_ops.h>   // esp_ota_get_app_description() for `info`
#include <esp_task_wdt.h>  // esp_task_wdt_reset() during screendump's ~18s stream
#include <mbedtls/base64.h>
#include "appShell.h"      // AppId, switchApp()
#include "spotifyTask.h"
#include "debug/bodWatch.h"   // TASK-557: BOD polled inside the burst, not after it

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

// ADR-064 D1/D3 (TASK-638): a device-computed signature over the panel's own
// GRAM, on demand only (D2 — never from a render or tick path, never on a
// timer). `get sig <x> <y> <w> <h>` reuses screendump's band loop with the
// base64 + Serial.write replaced by a rolling FNV-1a and three counters:
//   hash            FNV-1a 32 over the corrected RGB565 words, row-major
//   inkCount        pixels whose colour != bgColor
//   distinctColors  distinct RGB565 values seen (saturates at 256: "many")
//   bgColor         the most frequent colour in the region
// The structural pair (inkCount, distinctColors) is the load-bearing half:
// a solid rectangle scores 0 and 1 with no golden and no time freeze (D3).
// 0 B static RAM — the band and the colour table are malloc'd per call.
static inline uint32_t fnv1a32(uint32_t h, uint16_t v) {
  h ^= (uint8_t)(v & 0xFF);  h *= 16777619u;
  h ^= (uint8_t)(v >> 8);    h *= 16777619u;
  return h;
}

void readbackSignature(const char *args) {
  int x = 0, y = 0, w = SCREEN_W, h = SCREEN_H;
  if (args && *args) sscanf(args, "%d %d %d %d", &x, &y, &w, &h);
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  if (w <= 0 || x + w > SCREEN_W) w = SCREEN_W - x;
  if (h <= 0 || y + h > SCREEN_H) h = SCREEN_H - y;
  if (w <= 0 || h <= 0) {
    Serial.println("{\"ok\":false,\"cmd\":\"get\",\"var\":\"sig\",\"error\":\"empty region\"}");
    return;
  }
  static const int kBandRows = 8;
  static const int kTable = 256;                        // open addressing, 2^8
  uint16_t *band = (uint16_t *)malloc(sizeof(uint16_t) * w * kBandRows);
  uint16_t *tcol = (uint16_t *)malloc(sizeof(uint16_t) * kTable);
  uint32_t *tcnt = (uint32_t *)malloc(sizeof(uint32_t) * kTable);
  if (!band || !tcol || !tcnt) {
    free(band); free(tcol); free(tcnt);
    Serial.println("{\"ok\":false,\"cmd\":\"get\",\"var\":\"sig\",\"error\":\"alloc failed\"}");
    return;
  }
  memset(tcnt, 0, sizeof(uint32_t) * kTable);
  uint32_t hash = 2166136261u;
  int distinct = 0;
  bool saturated = false;
  for (int ry = 0; ry < h; ry += kBandRows) {
    esp_task_wdt_reset();                               // D8: TWDT 15 s, panic=true
    int rows = min(kBandRows, h - ry);
    tft.readRect(x, y + ry, w, rows, band);
    for (int i = 0; i < w * rows; i++) {
      uint16_t v = band[i];
      v = (uint16_t)((v << 8) | (v >> 8));              // undo readRect's pushRect swap (TASK-340)
      hash = fnv1a32(hash, v);
      // colour table: linear probe from a cheap hash of the colour
      int slot = (int)(((uint32_t)v * 2654435761u) >> 24) & (kTable - 1);
      bool placed = false;
      for (int k = 0; k < kTable; k++) {
        int sl = (slot + k) & (kTable - 1);
        if (tcnt[sl] == 0) {
          if (distinct < kTable) { tcol[sl] = v; tcnt[sl] = 1; distinct++; }
          else saturated = true;
          placed = true; break;
        }
        if (tcol[sl] == v) { tcnt[sl]++; placed = true; break; }
      }
      if (!placed) saturated = true;
    }
  }
  uint32_t bgCount = 0; uint16_t bg = 0;
  for (int sl = 0; sl < kTable; sl++)
    if (tcnt[sl] > bgCount) { bgCount = tcnt[sl]; bg = tcol[sl]; }
  const uint32_t total = (uint32_t)w * (uint32_t)h;
  Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"sig\",\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d,"
                "\"hash\":\"%08x\",\"inkCount\":%u,\"distinctColors\":%d,\"saturated\":%s,"
                "\"bgColor\":%u,\"px\":%u,\"last\":true}\n",
                x, y, w, h, (unsigned)hash, (unsigned)(total - bgCount), distinct,
                saturated ? "true" : "false", (unsigned)bg, (unsigned)total);
  free(band); free(tcol); free(tcnt);
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

// TASK-557: a checkable serial stream, so host-side data loss can be correlated
// against the brownout comparator's own trips (bodWatch) in the SAME stream.
//
// Why not esptool's bulk read: that runs in the ROM bootloader, where the
// application — and therefore bodWatch — is not loaded, so it can measure loss
// or the supply, never both at once. Emitting from the app puts `[bod] TRIP`
// lines inline with the data, which is what makes the correlation possible.
//
// Line format:  #<seq> <pad chars> <sum8hex>
// The sum is over seq + every pad byte, so the host detects a corrupted line as
// well as a missing one. Sequence numbers make a GAP unambiguous: with no flow
// control anywhere in this chain (DTR/RTS are consumed by the auto-reset
// circuit), a dropped byte is otherwise invisible.
void cmdSerialBurst(const char *args) {
  int lines = 2000, pad = 64;
  sscanf(args, "%d %d", &lines, &pad);
  if (lines < 1) lines = 1;
  if (pad < 8) pad = 8;
  if (pad > 200) pad = 200;

  char buf[208];
  memset(buf, 'A', pad);
  buf[pad] = 0;

  // Drop any latch left over from the boot-window sag, or the burst would
  // inherit a trip it did not cause. Without this the measurement says nothing
  // about the burst at all.
  bodWatchClear();

  Serial.printf("{\"probe\":\"burst\",\"phase\":\"begin\",\"lines\":%d,\"pad\":%d,"
                "\"thres\":%u,\"t\":%lu}\n",
                lines, pad, (unsigned)bodWatchThres(), (unsigned long)millis());
  const unsigned long t0 = millis();
  int bodTrips = 0, firstTripSeq = -1;
  for (int i = 0; i < lines; i++) {
    uint32_t sum = (uint32_t)i;
    for (int k = 0; k < pad; k++) sum += (uint8_t)buf[k];
    Serial.printf("#%d %s %08x\n", i, buf, (unsigned)sum);
    // The burst is the point, so keep the watchdog fed rather than pacing it.
    if ((i & 63) == 0) esp_task_wdt_reset();
    // Polled HERE, not in loop(): this command blocks loop() for its whole
    // duration, so bodWatchTick() cannot run and a trip during the burst would
    // otherwise be attributed to whatever ran next. Silent — see bodWatchPollQuiet.
    if (bodWatchPollQuiet()) {
      if (firstTripSeq < 0) firstTripSeq = i;
      bodTrips++;
    }
  }
  const unsigned long ms = millis() - t0;
  Serial.printf("{\"probe\":\"burst\",\"phase\":\"end\",\"lines\":%d,\"elapsedMs\":%lu,"
                "\"bodTrips\":%d,\"firstTripSeq\":%d,\"thres\":%u}\n",
                lines, ms, bodTrips, firstTripSeq, (unsigned)bodWatchThres());
}


// TASK-557: read BOD state, and choose the threshold the NEXT boot arms with.
// The boot-window sag lands ~1.5 s in, long before the console exists, so
// sweeping it needs the value to survive the reboot — hence RTC_NOINIT.
void cmdBod(const char *args) {
  int t = -1;
  if (args && args[0] && sscanf(args, "%d", &t) == 1 && t >= 0 && t <= 7) {
    bodWatchSetBootThres((uint8_t)t);
    Serial.printf("{\"ok\":true,\"cmd\":\"bod\",\"bootThres\":%d,"
                  "\"note\":\"takes effect on next reboot\"}\n", t);
    return;
  }
  Serial.printf("{\"ok\":true,\"cmd\":\"bod\",\"thresNow\":%u,\"bootThres\":%u,"
                "\"tripsSinceArm\":%lu}\n",
                (unsigned)bodWatchThres(), (unsigned)bodWatchBootThres(),
                (unsigned long)bodWatchTrips());
}

// TASK-557: choose the boot-inrush mitigation the NEXT boot applies across its
// WiFi-init window. Bit 0 = backlight off, bit 1 = reduced WiFi TX power; 0 is
// the unmitigated control. Same RTC_NOINIT survival trick as `bod` above, for
// the same reason — the window closes long before the console exists.
void cmdBodMit(const char *args) {
  int m = -1;
  if (args && args[0] && sscanf(args, "%d", &m) == 1 && m >= 0 && m <= 3) {
    bodWatchSetBootMit((uint8_t)m);
    Serial.printf("{\"ok\":true,\"cmd\":\"bodmit\",\"bootMit\":%d,"
                  "\"note\":\"takes effect on next reboot\"}\n", m);
    return;
  }
  Serial.printf("{\"ok\":true,\"cmd\":\"bodmit\",\"bootMit\":%u}\n",
                (unsigned)bodWatchBootMit());
}
#endif // SERIAL_DEBUG
