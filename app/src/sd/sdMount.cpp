// sd/sdMount.cpp — the boot-time SD mount, out-of-line (M-SRCLAYOUT
// Stage E / TASK-471). PRODUCTION code — always compiled; SD_BOOT_MOUNT
// gates the real mount, matching main.cpp's own build-variant convention.
#include "sd/sdMount.h"

#include <esp_heap_caps.h>

#ifdef SD_BOOT_MOUNT
const int kSdCsPin = 5;
const int kSdSckPin = 18;
const int kSdMisoPin = 19;
const int kSdMosiPin = 23;
// SPI clock for data transfers (card identification always runs at 400 kHz inside
// ff_sd_initialize, and the library caps this at 25 MHz). 20 MHz, not the 4 MHz the
// M-SDFS bring-up plan suggested: on the SDHC card, 4 MHz reproducibly panics inside
// FatFs mid-read (2/2 runs; `validate()` sees obj->fs == NULL after ff_req_grant())
// while 20 MHz is clean (3/3) and 40x faster. Runtime-settable via `sdmount`.
uint32_t s_sdFreqHz = 20000000;

// Open-file slots requested of SD.begin(). This is the single dominant term in the
// mount's memory cost, not a throughput knob: esp_vfs_fat_register() allocates
// `sizeof(vfs_fat_ctx_t) + max_files * sizeof(FIL)` as ONE contiguous internal
// block, and this IDF build has FF_MAX_SS=4096 (CONFIG_WL_SECTOR_SIZE) with
// FF_FS_TINY=0 (CONFIG_FATFS_PER_FILE_CACHE=1) — so FATFS carries a 4 KB window
// buffer and every FIL carries its own 4 KB sector cache. The Arduino default of
// 5 therefore asks for ~25 KB in one piece. See `sdmem`.
//
// TASK-416: bumped 2 -> 3. m3u::PlaylistIndex keeps the playlist File open for
// the session (audio decoder + playlist = 2, TASK-415's own accounting), and
// fileBrowser.h now holds a THIRD handle open across ticks — the directory
// SD.open() plus the File openNextFile() returns. TASK-425 measured this
// exact bump on this exact DUT (2026-08-11, cyd2usb_winamp_debug, mount-first):
// `sdmount 3` mounts cleanly (heapDelta 19 252 B, sdumount reclaimedB 19 252 B,
// exact agreement) leaving lfb8=12 788 B — enough to browse (no arena
// contention: TASK-431 already confines all Player-mode PLAYBACK to
// cyd2usb_player, where Spotify's ~39 KB TLS working set is compiled out
// entirely and isn't resident to compete for it; browsing-only headroom on
// this debug build was never the constraint). On cyd2usb_player itself the
// margin is not remotely close: TASK-427's DUT evidence shows free
// heap/largest-block in the ~50-120 KB range around a play attempt, so this
// one extra ~4 KB FIL slot is nowhere near the constraint there either. Single
// constant, not `#ifdef`'d per variant — TASK-425/427/431 already established
// that mount-size tuning is not the lever that matters once Spotify's TLS
// working set is out of the picture.
const uint8_t kSdMaxFiles = 3;

SPIClass s_sdSPI(VSPI);
bool s_sdReady = false;
bool s_sdSpiUp = false;
size_t s_sdBootFreeIntBefore = 0, s_sdBootFreeIntAfter = 0;
size_t s_sdBootLfbIntBefore = 0, s_sdBootLfbIntAfter = 0;

// One mount attempt with full before/after heap accounting, usable from setup()
// and from a live serial command. `tag` names the call site in the JSON line.
bool sdMountAttempt(const char *tag, uint8_t maxFiles) {
  size_t freeBefore = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbBefore = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  size_t lfb8Before = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!s_sdSpiUp) {
    s_sdSPI.begin(kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    s_sdSpiUp = true;
  }
  unsigned long t0 = millis();
  bool ok = SD.begin(kSdCsPin, s_sdSPI, s_sdFreqHz, "/sd", maxFiles);
  unsigned long elapsedMs = millis() - t0;
  size_t freeAfter = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbAfter = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  Serial.printf("{\"probe\":\"sdmount\",\"tag\":\"%s\",\"maxFiles\":%u,\"mounted\":%s,"
                "\"elapsedMs\":%lu,\"heapDeltaB\":%ld,"
                "\"freeIntBefore\":%u,\"freeIntAfter\":%u,"
                "\"lfbIntBefore\":%u,\"lfbIntAfter\":%u,\"lfb8Before\":%u,\"lfb8After\":%u}\n",
                tag, (unsigned)maxFiles, ok ? "true" : "false", elapsedMs,
                (long)freeBefore - (long)freeAfter,
                (unsigned)freeBefore, (unsigned)freeAfter,
                (unsigned)lfbBefore, (unsigned)lfbAfter,
                (unsigned)lfb8Before,
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  s_sdBootFreeIntBefore = freeBefore;
  s_sdBootFreeIntAfter = freeAfter;
  s_sdBootLfbIntBefore = lfbBefore;
  s_sdBootLfbIntAfter = lfbAfter;
  return ok;
}

void sdProbeBootMount() {
  s_sdReady = sdMountAttempt("boot", kSdMaxFiles);
  if (!s_sdReady && s_sdSpiUp) { s_sdSPI.end(); s_sdSpiUp = false; }
}

// TASK-415: the boot mount's outcome, for code outside this file (LocalPlayerApp
// must degrade to "No SD card" rather than opening files against a dead mount).
// A function, not an extern on s_sdReady, so the mount state stays owned here.
bool sdReady() { return s_sdReady; }

#else  // !SD_BOOT_MOUNT
// TASK-427: builds without SD_BOOT_MOUNT (today: cyd2usb_winamp production) compile no
// SD mount at all. Same symbol, honest answer — LocalPlayerApp degrades to "No SD card".
bool sdReady() { return false; }
#endif // SD_BOOT_MOUNT
