// debug/serialConsole/cmdSd.cpp — SD bring-up probes (TASK-408 et al),
// out-of-line (M-SRCLAYOUT Stage E / TASK-471). Body compiles only under
// SERIAL_DEBUG; the .cpp itself is always compiled, same convention as
// appTable.cpp / cmdSystem.cpp / cmdMisc.cpp / cmdTouch.cpp / cmdGet.cpp /
// cmdSet.cpp.
#include "debug/serialConsole/cmdSd.h"

#ifdef SERIAL_DEBUG
#include <Arduino.h>
#include <string.h>
#include <stdlib.h>
#include <SD.h>
#include <SPI.h>
#include <sd_diskio.h>   // TASK-408: raw-sector access for `sdmbr` (below SD/FatFs)
#include <ff.h>          // TASK-408: FATFS/FIL sizes — the mount's real memory cost
#include "ffconf.h"      // TASK-408: FF_VOLUMES
#include <esp_heap_caps.h>
#include <esp_task_wdt.h>
#include <mbedtls/base64.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>   // uxTaskGetStackHighWaterMark
// TASK-521's sdopendir probe calls the POSIX layer directly, one level below
// Arduino's FS wrapper, so it needs these explicitly.
#include <dirent.h>
#include <errno.h>
#include <sys/stat.h>
#include <fcntl.h>       // TASK-424: F_GETFD, to ask whether our own fd is still registered
#include "debug/serialConsole/consoleShared.h"   // kSdCsPin/.../s_sdReady/sdMountAttempt

static const char *sdCardTypeName(sdcard_type_t t) {
  switch (t) {
    case CARD_MMC:  return "MMC";
    case CARD_SD:   return "SDSC";
    case CARD_SDHC: return "SDHC";
    case CARD_NONE: return "NONE";
    default:        return "UNKNOWN";
  }
}

// TASK-408 root-cause instrument. `esp_vfs_fat_register()` returns ESP_ERR_NO_MEM from
// two distinct places: the FF_VOLUMES context table being full, and a plain calloc()
// failing. This separates them — it prints the exact contiguous block SD.begin() will
// ask for at each max_files setting, then actually tries to calloc that block and
// reports which sizes the live heap can still serve.
void cmdSdMem(const char *) {
  // MALLOC_CAP_INTERNAL alone over-reports what a plain calloc() can be served: it
  // counts the 32-bit-only D/IRAM region, which is not byte-addressable. The number
  // that actually gates the mount is the INTERNAL|8BIT largest free block.
  const uint32_t kByteCap = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
  Serial.printf("{\"probe\":\"sdmem\",\"FF_VOLUMES\":%d,\"FF_MAX_SS\":%d,\"FF_FS_TINY\":%d,"
                "\"FF_USE_LFN\":%d,\"sizeofFATFS\":%u,\"sizeofFIL\":%u,"
                "\"freeInt\":%u,\"lfbInt\":%u,\"minFreeInt\":%u,"
                "\"free8\":%u,\"lfb8\":%u,\"freeDma\":%u,\"lfbDma\":%u,"
                "\"mounted\":%s}\n",
                (int)FF_VOLUMES, (int)FF_MAX_SS, (int)FF_FS_TINY, (int)FF_USE_LFN,
                (unsigned)sizeof(FATFS), (unsigned)sizeof(FIL),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_free_size(kByteCap),
                (unsigned)heap_caps_get_largest_free_block(kByteCap),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA),
                s_sdReady ? "true" : "false");

  // Largest single byte-addressable block the live heap can actually serve, by
  // bisection. `lfb8` is the allocator's view of its biggest free span; this is the
  // number that decides whether SD.begin() survives, and the two can differ by the
  // block header and alignment.
  {
    size_t lo = 0, hi = 65536;
    while (lo + 64 < hi) {
      size_t mid = (lo + hi) / 2;
      void *p = malloc(mid);
      if (p) { free(p); lo = mid; } else { hi = mid; }
      esp_task_wdt_reset();
    }
    Serial.printf("{\"probe\":\"sdmem\",\"maxCallocB\":%u}\n", (unsigned)lo);
  }

  // vfs_fat_ctx_t is private to the IDF, but its layout is FATFS + a handful of
  // scalars + FIL[max_files]; 128 B covers the scalars and any padding with margin.
  const unsigned kCtxOverhead = 128;
  static const uint8_t kSlots[] = { 1, 2, 3, 5 };
  for (unsigned i = 0; i < sizeof(kSlots); i++) {
    size_t need = sizeof(FATFS) + kCtxOverhead + (size_t)kSlots[i] * sizeof(FIL);
    void *p = calloc(1, need);
    bool got = (p != nullptr);
    if (p) free(p);
    bool last = (i + 1 == sizeof(kSlots));
    Serial.printf("{\"probe\":\"sdmem\",\"maxFiles\":%u,\"ctxBytes\":%u,\"callocOk\":%s,"
                  "\"lfb8\":%u,\"last\":%s}\n",
                  (unsigned)kSlots[i], (unsigned)need, got ? "true" : "false",
                  (unsigned)heap_caps_get_largest_free_block(kByteCap),
                  last ? "true" : "false");
    esp_task_wdt_reset();
  }
}

// Live mount attempt from the serial-command context, i.e. with spotifyTask/dataTask
// alive — the exact path that was reported as failing.
void cmdSdMount(const char *args) {
  int maxFiles = kSdMaxFiles;
  unsigned freqHz = 0;
  sscanf(args, "%d %u", &maxFiles, &freqHz);
  if (maxFiles < 1) maxFiles = 1;
  if (maxFiles > 10) maxFiles = 10;
  if (freqHz >= 400000 && freqHz <= 40000000) s_sdFreqHz = freqHz;
  if (s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmount\",\"error\":\"already mounted\"}");
    return;
  }
  s_sdReady = sdMountAttempt("live", (uint8_t)maxFiles);
  Serial.printf("{\"ok\":%s,\"cmd\":\"sdmount\",\"mounted\":%s}\n",
                s_sdReady ? "true" : "false", s_sdReady ? "true" : "false");
}

// Unmount and report the heap actually handed back. This is the clean T_SD_06
// measurement: a mount-cost delta taken across SD.begin() during boot is polluted by
// WiFi/NTP/task-start allocations landing in the same window, but the free() side of
// an idle unmount is not.
void cmdSdUmount(const char *) {
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdumount\",\"error\":\"not mounted\"}");
    return;
  }
  size_t freeBefore = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbBefore = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  SD.end();
  s_sdSPI.end();
  s_sdSpiUp = false;
  s_sdReady = false;
  size_t freeAfter = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  size_t lfbAfter = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
  Serial.printf("{\"ok\":true,\"cmd\":\"sdumount\",\"reclaimedB\":%ld,"
                "\"freeIntBefore\":%u,\"freeIntAfter\":%u,"
                "\"lfbIntBefore\":%u,\"lfbIntAfter\":%u}\n",
                (long)freeAfter - (long)freeBefore,
                (unsigned)freeBefore, (unsigned)freeAfter,
                (unsigned)lfbBefore, (unsigned)lfbAfter);
}

// T_SD_08: N live mount/unmount cycles against the same VSPI session, from the same
// serial-command execution context as sdprobe (concurrent tasks alive) — reuses the
// already-good boot-established path rather than a fresh live mount (which is exactly
// what's broken; see sdProbeBootMount()'s comment). Leaves SD mounted on return.
void cmdSdCycle(const char *args) {
  int cycles = 20;
  sscanf(args, "%d", &cycles);
  if (cycles < 1) cycles = 1;
  if (cycles > 200) cycles = 200;

  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdcycle\",\"error\":\"not mounted at boot\"}");
    return;
  }

  size_t baseline = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  Serial.printf("{\"ok\":true,\"cmd\":\"sdcycle\",\"cycles\":%d,\"baselineFreeInt\":%u}\n",
                cycles, (unsigned)baseline);

  int okCount = 0;
  for (int i = 0; i < cycles; i++) {
    SD.end();
    s_sdSPI.end();
    s_sdSPI.begin(kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    s_sdSpiUp = true;
    bool ok = SD.begin(kSdCsPin, s_sdSPI, s_sdFreqHz, "/sd", kSdMaxFiles);
    size_t freeNow = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    long drift = (long)baseline - (long)freeNow;
    bool last = (i + 1 == cycles);
    Serial.printf("{\"probe\":\"sdcycle\",\"i\":%d,\"ok\":%s,\"freeInt\":%u,\"driftB\":%ld,\"last\":%s}\n",
                  i, ok ? "true" : "false", (unsigned)freeNow, drift, last ? "true" : "false");
    if (ok) { okCount++; } else { s_sdReady = false; break; }
    esp_task_wdt_reset();
  }
  s_sdReady = (okCount == cycles);
}

// ── TASK-415: host → card file upload, for test fixtures ─────────────────────
// `sdmkdir <path>` and `sdput <w|a> <base64> <path>` — the path comes LAST because
// real paths on this card contain spaces and the args split does not quote.
//
// This exists because the M3U gate fixtures have to get onto the card somehow and
// the alternative is a human with a card reader. It is test tooling, SERIAL_DEBUG
// only, and it is emphatically NOT the "playlist persistence" that TASK-424 says
// must not be built on this write path: each call is one open/write/close of <=108
// bytes, which is the short-burst pattern that measurably works, and no product
// feature depends on it. TASK-421's save path is still blocked on TASK-424.
//
// The 160-byte serial line buffer sets the chunk size: ~120 base64 characters, so
// 90 bytes per call. app/tools/sd_put.py drives it.
void cmdSdMkdir(const char *args) {
  if (!s_sdReady) { Serial.println("{\"ok\":false,\"cmd\":\"sdmkdir\",\"error\":\"not mounted\"}"); return; }
  if (!args || !*args) { Serial.println("{\"ok\":false,\"cmd\":\"sdmkdir\",\"error\":\"usage: sdmkdir <path>\"}"); return; }
  const bool existed = SD.exists(args);
  const bool ok = existed || SD.mkdir(args);
  Serial.printf("{\"ok\":%s,\"cmd\":\"sdmkdir\",\"path\":\"%s\",\"existed\":%s}\n",
                ok ? "true" : "false", args, existed ? "true" : "false");
}

void cmdSdPut(const char *args) {
  if (!s_sdReady) { Serial.println("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"not mounted\"}"); return; }
  char op = 0;
  char b64[144];
  if (!args || sscanf(args, "%c %143s", &op, b64) != 2 || (op != 'w' && op != 'a')) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"usage: sdput <w|a> <base64|-> <path>\"}");
    return;
  }
  // Path is everything after the base64 field — spaces and all.
  const char *p = strstr(args, b64);
  const char *path = p ? p + strlen(b64) : nullptr;
  while (path && *path == ' ') path++;
  if (!path || !*path) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"missing path\"}");
    return;
  }
  uint8_t bin[112];
  size_t  olen = 0;
  if (strcmp(b64, "-") != 0) {   // "-" = no payload (create/truncate only)
    const int rc = mbedtls_base64_decode(bin, sizeof(bin), &olen,
                                         (const unsigned char *)b64, strlen(b64));
    if (rc != 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"base64 decode rc=%d\"}\n", rc);
      return;
    }
  }
  File f = SD.open(path, op == 'w' ? FILE_WRITE : FILE_APPEND);
  if (!f) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdput\",\"error\":\"open failed\",\"path\":\"%s\"}\n", path);
    return;
  }
  const size_t wrote = olen ? f.write(bin, olen) : 0;
  f.flush();                       // durability: fflush + fsync
  // What makes this size() trustworthy is the write() above, NOT the flush:
  // File::size() re-stats only when `_written` is set, which write() sets and
  // flush() does not touch (vfs_api.cpp:438-447, :411-419). Corrected 2026-08-31
  // — this comment used to credit the flush, and cmdSdWrite's startSizeB bug was
  // read through that wrong model for weeks. See the note in cmdSdWrite below.
  const size_t total = f.size();
  f.close();
  Serial.printf("{\"ok\":%s,\"cmd\":\"sdput\",\"op\":\"%c\",\"wrote\":%u,\"sizeB\":%u,\"path\":\"%s\"}\n",
                (wrote == olen) ? "true" : "false", op,
                (unsigned)wrote, (unsigned)total, path);
}

// Raw sector reader, below the FatFs layer, so a card that initialises over SPI but
// carries no mountable volume can still be identified. Answers the only question a
// "no valid FAT volume" mount failure leaves open: what IS on the card.
void cmdSdMbr(const char *) {
  if (s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"unmount first (sdumount)\"}");
    return;
  }
  if (!s_sdSpiUp) {
    s_sdSPI.begin(kSdSckPin, kSdMisoPin, kSdMosiPin, kSdCsPin);
    s_sdSpiUp = true;
  }
  uint8_t pdrv = sdcard_init(kSdCsPin, &s_sdSPI, (int)s_sdFreqHz);
  if (pdrv == 0xFF) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"sdcard_init failed\"}");
    return;
  }
  // sdcard_init() only claims a drive slot — the card is not identified until FatFs
  // calls disk_initialize() from f_mount. Without this the card reads back as
  // CARD_NONE with a nonsense sector count. The mount is EXPECTED to fail here (that
  // is the whole point); it leaves the card initialised, which is what raw reads need.
  bool mountOk = sdcard_mount(pdrv, "/sdraw", 1, false);
  Serial.printf("{\"probe\":\"sdmbr\",\"initMountOk\":%s}\n", mountOk ? "true" : "false");

  Serial.printf("{\"probe\":\"sdmbr\",\"cardType\":\"%s\",\"sectors\":%u,\"sectorSizeB\":%u,"
                "\"capacityMB\":%u}\n",
                sdCardTypeName(sdcard_type(pdrv)), (unsigned)sdcard_num_sectors(pdrv),
                (unsigned)sdcard_sector_size(pdrv),
                (unsigned)((uint64_t)sdcard_num_sectors(pdrv) * sdcard_sector_size(pdrv) / (1024 * 1024)));

  uint8_t *buf = (uint8_t *)malloc(512);
  if (!buf) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"alloc\"}");
    sdcard_uninit(pdrv);
    return;
  }

  // Sector 0, then whatever the first MBR entry points at. A card formatted as one
  // big volume with no partition table puts the boot sector at 0 instead.
  // With no card in the slot the driver still hands back a pdrv and reports a nonsense
  // geometry (CARD_UNKNOWN, ~31 k sectors), so the summary must not read ok:true just
  // because the calls returned. Track whether anything was actually readable.
  bool cardUsable = (sdcard_type(pdrv) != CARD_NONE && sdcard_type(pdrv) != CARD_UNKNOWN);
  bool sector0Ok = false;
  uint32_t probeSectors[2] = { 0, 0 };
  int nProbe = 1;
  if (sd_read_raw(pdrv, buf, 0)) {
    sector0Ok = true;
    bool sig = (buf[510] == 0x55 && buf[511] == 0xAA);
    // OEM name at +3 is "EXFAT   " for exFAT, "MSDOS"/"mkfs.fat"/etc for FAT.
    char oem[9] = {0};
    memcpy(oem, buf + 3, 8);
    for (int i = 0; i < 8; i++) if (oem[i] < 32 || oem[i] > 126) oem[i] = '.';
    uint8_t ptype = buf[0x1BE + 4];
    uint32_t plba = (uint32_t)buf[0x1BE + 8] | ((uint32_t)buf[0x1BE + 9] << 8) |
                    ((uint32_t)buf[0x1BE + 10] << 16) | ((uint32_t)buf[0x1BE + 11] << 24);
    Serial.printf("{\"probe\":\"sdmbr\",\"sector\":0,\"bootSig\":%s,\"oem\":\"%s\","
                  "\"part0Type\":\"0x%02X\",\"part0Lba\":%u}\n",
                  sig ? "true" : "false", oem, ptype, (unsigned)plba);
    if (plba > 0 && plba < sdcard_num_sectors(pdrv)) { probeSectors[1] = plba; nProbe = 2; }
  } else {
    Serial.println("{\"probe\":\"sdmbr\",\"sector\":0,\"readFailed\":true}");
  }

  for (int i = 0; i < nProbe; i++) {
    if (i == 0) continue;   // already reported above
    if (!sd_read_raw(pdrv, buf, probeSectors[i])) {
      Serial.printf("{\"probe\":\"sdmbr\",\"sector\":%u,\"readFailed\":true}\n",
                    (unsigned)probeSectors[i]);
      continue;
    }
    char oem[9] = {0}, fstype[9] = {0}, fstype32[9] = {0};
    memcpy(oem, buf + 3, 8);
    memcpy(fstype, buf + 0x36, 8);     // FAT12/FAT16
    memcpy(fstype32, buf + 0x52, 8);   // FAT32
    for (int k = 0; k < 8; k++) {
      if (oem[k] < 32 || oem[k] > 126) oem[k] = '.';
      if (fstype[k] < 32 || fstype[k] > 126) fstype[k] = '.';
      if (fstype32[k] < 32 || fstype32[k] > 126) fstype32[k] = '.';
    }
    uint16_t bytesPerSec = (uint16_t)buf[11] | ((uint16_t)buf[12] << 8);
    Serial.printf("{\"probe\":\"sdmbr\",\"sector\":%u,\"oem\":\"%s\",\"fsType\":\"%s\","
                  "\"fsType32\":\"%s\",\"bytesPerSector\":%u,\"bootSig\":%s}\n",
                  (unsigned)probeSectors[i], oem, fstype, fstype32, (unsigned)bytesPerSec,
                  (buf[510] == 0x55 && buf[511] == 0xAA) ? "true" : "false");
  }
  free(buf);
  if (mountOk) sdcard_unmount(pdrv);
  sdcard_uninit(pdrv);
  s_sdSPI.end();
  s_sdSpiUp = false;
  if (!cardUsable || !sector0Ok) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdmbr\",\"error\":\"no readable card\","
                  "\"cardUsable\":%s,\"sector0Ok\":%s}\n",
                  cardUsable ? "true" : "false", sector0Ok ? "true" : "false");
    return;
  }
  Serial.println("{\"ok\":true,\"cmd\":\"sdmbr\"}");
}

// TASK-521 root-cause instrument. `SD.open(dir)` fails during playback with
// `VFSFileImpl(): opendir(...) failed`, and that log line carries no errno — so
// every candidate mechanism (a full max_files table, a contiguous-heap
// shortfall, FATFS mutex contention with the audio pump, a 200-entry directory
// specifically) produces the SAME message. This calls the raw POSIX opendir()
// directly, one level below Arduino's FS wrapper, and reports the errno plus the
// wall time and the live byte-addressable heap. The mapping is unambiguous:
//   ENOMEM(12)    — ff_memalloc(sizeof(vfs_fat_dir_t)) or FatFs FR_NOT_ENOUGH_CORE
//   ENFILE(23)    — FR_TOO_MANY_OPEN_FILES, i.e. the open-handle table (kSdMaxFiles)
//   ETIMEDOUT(116)— FR_TIMEOUT, i.e. FF_FS_TIMEOUT contention on the FATFS mutex
//   EIO(5)/ENODEV — a real card/disk error
// The trailing malloc ladder prices the exact allocation vfs_fat_opendir makes
// (~700 B: FF_DIR + FILINFO + struct dirent + the DIR header) against what the
// heap can actually serve at that instant.
void cmdSdOpenDir(const char *args) {
  char path[96] = "/";
  if (args && args[0]) strlcpy(path, args, sizeof(path));
  // Strip a trailing slash exactly as fileBrowser::open() does, so this probe
  // exercises the same string the browser hands to the VFS.
  {
    size_t n = strlen(path);
    if (n > 1 && path[n - 1] == '/') path[n - 1] = '\0';
  }
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdopendir\",\"error\":\"not mounted\"}");
    return;
  }
  const uint32_t kByteCap = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
  char full[128];
  snprintf(full, sizeof(full), "/sd%s", (path[0] == '/') ? path : "/");

  const size_t free8Before = heap_caps_get_free_size(kByteCap);
  const size_t lfb8Before = heap_caps_get_largest_free_block(kByteCap);
  const unsigned stackFree = (unsigned)uxTaskGetStackHighWaterMark(nullptr);

  // stat() first: it resolves the same directory entry through the same FATFS
  // mutex but makes NO heap allocation of its own. stat OK + opendir ENOMEM
  // separates "the filesystem cannot see the directory" from "the filesystem
  // saw it and could not allocate the handle".
  struct stat st;
  errno = 0;
  const unsigned long ts0 = micros();
  const int strc = stat(full, &st);
  const unsigned long statUs = micros() - ts0;
  const int statErrno = errno;

  errno = 0;
  const unsigned long t0 = micros();
  DIR *d = opendir(full);
  const unsigned long elapsedUs = micros() - t0;
  const int e = errno;
  if (d) closedir(d);

  Serial.printf("{\"probe\":\"sdopendir\",\"path\":\"%s\",\"statOk\":%s,\"statErrno\":%d,"
                "\"isDir\":%s,\"statUs\":%lu,\"opendirOk\":%s,\"errno\":%d,"
                "\"elapsedUs\":%lu,\"free8Before\":%u,\"lfb8Before\":%u,"
                "\"stackFreeB\":%u}\n",
                path, (strc == 0) ? "true" : "false", statErrno,
                (strc == 0 && S_ISDIR(st.st_mode)) ? "true" : "false", statUs,
                d ? "true" : "false", e, elapsedUs,
                (unsigned)free8Before, (unsigned)lfb8Before, stackFree);

  // What a plain malloc can be served right now, at the sizes that matter.
  static const size_t kSizes[] = { 256, 512, 700, 1024, 2048, 4096 };
  for (unsigned i = 0; i < sizeof(kSizes) / sizeof(kSizes[0]); i++) {
    void *p = malloc(kSizes[i]);
    const bool got = (p != nullptr);
    if (p) ::free(p);
    Serial.printf("{\"probe\":\"sdopendir\",\"mallocB\":%u,\"ok\":%s}\n",
                  (unsigned)kSizes[i], got ? "true" : "false");
    esp_task_wdt_reset();
  }
  Serial.printf("{\"ok\":%s,\"cmd\":\"sdopendir\",\"path\":\"%s\",\"errno\":%d,"
                "\"lfb8\":%u,\"free8\":%u}\n",
                d ? "true" : "false", path, e,
                (unsigned)heap_caps_get_largest_free_block(kByteCap),
                (unsigned)heap_caps_get_free_size(kByteCap));
}

// TASK-521 companion instrument: how many of the mount's kSdMaxFiles open-file
// slots are actually FREE right now. Opens the same regular file repeatedly
// until the VFS refuses, then closes them all. If this reports >=1 free slot at
// the same instant that opendir() fails, the "the handle table is full" story
// is dead — measured, not argued.
void cmdSdSlots(const char *args) {
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdslots\",\"error\":\"not mounted\"}");
    return;
  }
  if (!args || !args[0]) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdslots\",\"error\":\"usage: sdslots <file>\"}");
    return;
  }
  // kSdMaxFiles is small; +2 headroom proves the ceiling is real rather than
  // just running out of probe slots.
  const int kMax = (int)kSdMaxFiles + 2;
  File held[16];
  int got = 0;
  for (int i = 0; i < kMax && i < 16; i++) {
    File f = SD.open(args, FILE_READ);
    if (!f) break;
    held[got++] = f;
    esp_task_wdt_reset();
  }
  Serial.printf("{\"ok\":true,\"cmd\":\"sdslots\",\"path\":\"%s\",\"maxFiles\":%u,"
                "\"freeSlotsObserved\":%d,\"triedUpTo\":%d}\n",
                args, (unsigned)kSdMaxFiles, got, kMax);
  for (int i = 0; i < got; i++) held[i].close();
}

// Plain directory listing with sizes — needed to pick a pre-existing, cleanly
// written file to benchmark reads against.
void cmdSdLs(const char *args) {
  // `sdls <dir> q` suppresses the per-entry lines: at 115200 baud the Serial writes
  // dominate the walk, so the timing is only meaningful with them off.
  char dir[64] = "/", flag[8] = {0};
  if (args && args[0]) { sscanf(args, "%63s %7s", dir, flag); }
  bool quiet = (flag[0] == 'q' || flag[0] == 'Q' || flag[0] == 'n' || flag[0] == 'N');
  // `n` also skips File::size(). That call is a path-based stat, which FatFs resolves by
  // scanning the directory from its start — so doing it per entry makes a listing O(n^2)
  // in directory size. Comparing `q` against `n` prices what showing file sizes costs
  // browse-001, as opposed to what walking the directory costs.
  bool doStat = !(flag[0] == 'n' || flag[0] == 'N');
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdls\",\"error\":\"not mounted\"}");
    return;
  }
  File d = SD.open(dir);
  if (!d || !d.isDirectory()) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdls\",\"error\":\"not a directory\",\"dir\":\"%s\"}\n", dir);
    if (d) d.close();
    return;
  }
  int n = 0;
  unsigned long t0 = micros();
  while (n < 400) {
    File e = d.openNextFile();
    if (!e) break;
    if (!quiet) {
      Serial.printf("{\"probe\":\"sdls\",\"name\":\"%s\",\"dir\":%s,\"sizeB\":%u}\n",
                    e.name(), e.isDirectory() ? "true" : "false", (unsigned)e.size());
    } else if (doStat) {
      (void)e.size();   // the per-entry stat -- see doStat above
    }
    e.close();
    n++;
    esp_task_wdt_reset();
  }
  unsigned long elapsedMs = (micros() - t0) / 1000;
  d.close();
  // With `q` this is the walk cost alone; without it the Serial writes dominate.
  Serial.printf("{\"ok\":true,\"cmd\":\"sdls\",\"count\":%d,\"elapsedMs\":%lu}\n",
                n, elapsedMs);
}

// Read-only sustained benchmark against a caller-chosen path. Same measurement as
// sdprobe's bench phase, but it never writes, so it can be pointed at a file the
// card already carried rather than one this probe created.
void cmdSdRead(const char *args) {
  // Read count FIRST, then the rest of the line as the path: real filenames on this
  // card contain spaces, so the path has to be the unbounded trailing field.
  char path[96] = {0};
  int reads = 5000, consumed = 0;
  if (!args || sscanf(args, "%d %n", &reads, &consumed) != 1 || !args[consumed]) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdread\",\"error\":\"usage: sdread <reads> <path>\"}");
    return;
  }
  strlcpy(path, args + consumed, sizeof(path));
  if (reads < 100) reads = 100;
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdread\",\"error\":\"not mounted\"}");
    return;
  }
  File f = SD.open(path, FILE_READ);
  if (!f) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdread\",\"error\":\"open failed\",\"path\":\"%s\"}\n", path);
    return;
  }
  size_t fileSize = f.size();
  static const uint32_t kEdgeUs[] = {
    250, 500, 1000, 2000, 4000, 8000, 16000, 32000, 50000, 100000, 0xFFFFFFFFu
  };
  const int kNB = (int)(sizeof(kEdgeUs) / sizeof(kEdgeUs[0]));
  uint32_t bk[kNB];
  memset(bk, 0, sizeof(bk));
  static uint8_t rbuf[512];
  uint32_t maxUs = 0;
  size_t bytes = 0;
  int zeroReads = 0, wraps = 0;
  unsigned long t0all = micros();
  for (int i = 0; i < reads; i++) {
    unsigned long t0 = micros();
    size_t n = f.read(rbuf, sizeof(rbuf));
    unsigned long t1 = micros();
    uint32_t dt = (uint32_t)(t1 - t0);
    if (dt > maxUs) maxUs = dt;
    for (int b = 0; b < kNB; b++) { if (dt <= kEdgeUs[b]) { bk[b]++; break; } }
    if (n == 0) {
      // A failed physical read latches the stdio stream's error flag, and seek()
      // does not clear it — every later read then returns 0 instantly, which ends
      // the measurement early and understates sustained throughput. Reopen instead,
      // resuming at the offset reached, and count the recoveries.
      zeroReads++;
      size_t resumeAt = (size_t)f.position();
      f.close();
      f = SD.open(path, FILE_READ);
      if (!f) { break; }
      if (resumeAt + sizeof(rbuf) < fileSize) f.seek(resumeAt); else { f.seek(0); wraps++; }
    } else {
      bytes += n;
    }
    if ((i % 50) == 0) esp_task_wdt_reset();
  }
  unsigned long elapsedUs = micros() - t0all;
  f.close();

  uint32_t p50 = 0, p99 = 0, cum = 0;
  uint32_t need50 = (uint32_t)((reads * 50 + 99) / 100);
  uint32_t need99 = (uint32_t)((reads * 99 + 99) / 100);
  for (int b = 0; b < kNB; b++) {
    cum += bk[b];
    if (!p50 && cum >= need50) p50 = kEdgeUs[b];
    if (!p99 && cum >= need99) { p99 = kEdgeUs[b]; break; }
  }
  if (p50 > maxUs) p50 = maxUs;
  if (p99 > maxUs) p99 = maxUs;

  char histo[192];
  int off = 0;
  for (int b = 0; b < kNB && off < (int)sizeof(histo) - 12; b++) {
    off += snprintf(histo + off, sizeof(histo) - off, "%s%lu", b ? "," : "",
                    (unsigned long)bk[b]);
  }
  Serial.printf("{\"ok\":true,\"cmd\":\"sdread\",\"path\":\"%s\",\"fileB\":%u,"
                "\"reads\":%d,\"zeroReads\":%d,\"wraps\":%d,\"bytes\":%u,"
                "\"elapsedMs\":%lu,\"throughputKBps\":%.1f,"
                "\"p50Ms\":%.2f,\"p99Ms\":%.2f,\"maxMs\":%.2f,\"histo\":[%s]}\n",
                path, (unsigned)fileSize, reads, zeroReads, wraps, (unsigned)bytes,
                (unsigned long)(elapsedUs / 1000),
                elapsedUs ? ((float)bytes / 1024.0f) / ((float)elapsedUs / 1000000.0f) : 0.0f,
                p50 / 1000.0f, p99 / 1000.0f, maxUs / 1000.0f, histo);
}

// Isolated sequential write: nothing but open / write x N / close, so a write-path
// fault can be separated from anything the earlier sdprobe phases leave behind.
void cmdSdWrite(const char *args) {
  int chunks = 64, checkEvery = 0, append = 0;
  sscanf(args, "%d %d %d", &chunks, &checkEvery, &append);
  if (chunks < 1) chunks = 1;
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdwrite\",\"error\":\"not mounted\"}");
    return;
  }
  static uint8_t wbuf[512];
  memset(wbuf, 0xA5, sizeof(wbuf));
  // Must be sampled BEFORE the open: FILE_WRITE is "w" and truncates.
  // Short-circuited on `append` deliberately: in truncating mode the start size
  // is 0 by definition and no lookup is needed, which keeps this function's
  // stated contract intact for the path the TASK-424 panic repro drives —
  // "nothing but open / write x N / close" (see the header comment above). An
  // unconditional SD.exists() here would put an extra FatFs operation in front
  // of every isolated-write trial, which is precisely the confounder that
  // contract exists to exclude.
  const bool existed = append ? SD.exists("/probebench.bin") : false;
  // Append mode builds the read fixture in short bursts: sustained single-open
  // writes are what fail on this card, short open/write/close bursts are not.
  File f = SD.open("/probebench.bin", append ? FILE_APPEND : FILE_WRITE);
  if (!f) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdwrite\",\"error\":\"open failed\"}");
    return;
  }
  // TASK-424, 2026-08-31. `startSizeB` used to be a bare `f.size()` taken right
  // after the open, which is not a size at all on a freshly created file:
  //
  //   size_t VFSFileImpl::size() const {          // vfs_api.cpp:438
  //     if (_written) _getStat();                 // only re-stats AFTER a write
  //     return _stat.st_size;                     // else: whatever _stat holds
  //   }
  //
  // and the constructor fills `_stat` only on the "file already exists" branch
  // (`stat(temp,&_stat)`, vfs_api.cpp:295) — the create-new branch never stats,
  // and `_stat` is not in the member init list. So the value read back was
  // uninitialised memory. That is the whole origin of this task's "~1 GB file
  // size" symptom: every recorded value (1073678476, 1073628004, 1073676676 …)
  // decodes to 0x3FFExxxx/0x3FFFxxxx — an ESP32 DRAM address, i.e. a stale
  // pointer sitting in the unpopulated struct. `endSizeB` below never showed it
  // because it reopens FILE_READ on an existing file, which does populate _stat.
  //
  // An `f.flush()` here does NOT fix it — flush() only does fflush+fsync and
  // never touches `_stat` or `_written` (vfs_api.cpp:411-419). What makes
  // cmdSdPut's size correct is its *write* setting `_written`, not its flush.
  //
  // So derive the value rather than reading it: "w" truncates at open, making
  // the start size 0 by definition, and in append mode `_stat` really is
  // populated whenever the file pre-existed.
  const unsigned startSizeB = (append && existed) ? (unsigned)f.size() : 0u;
  Serial.printf("{\"probe\":\"sdwrite\",\"phase\":\"opened\",\"chunks\":%d,"
                "\"append\":%d,\"startSizeB\":%u}\n",
                chunks, append, startSizeB);
  size_t total = 0;
  unsigned long t0 = millis();
  for (int i = 0; i < chunks; i++) {
    size_t n = f.write(wbuf, sizeof(wbuf));
    total += n;
    if (n != sizeof(wbuf)) {
      Serial.printf("{\"probe\":\"sdwrite\",\"shortWrite\":%u,\"atChunk\":%d}\n",
                    (unsigned)n, i);
      break;
    }
    // The FIL that f_write faults on lives inside the mount's heap block, so a
    // stomped allocator structure would show up here before the fault does.
    if (checkEvery > 0 && ((i + 1) % checkEvery) == 0) {
      if (!heap_caps_check_integrity_all(true)) {
        Serial.printf("{\"probe\":\"sdwrite\",\"heapCorruptAtChunk\":%d}\n", i);
        break;
      }
    }
    esp_task_wdt_reset();
  }
  unsigned long elapsedMs = millis() - t0;
  f.close();
  size_t endSize = 0;
  { File chk = SD.open("/probebench.bin", FILE_READ); if (chk) { endSize = chk.size(); chk.close(); } }
  Serial.printf("{\"ok\":true,\"cmd\":\"sdwrite\",\"bytes\":%u,\"endSizeB\":%u,"
                "\"elapsedMs\":%lu,\"kBps\":%.1f}\n",
                (unsigned)total, (unsigned)endSize, elapsedMs,
                elapsedMs ? ((float)total / 1024.0f) / ((float)elapsedMs / 1000.0f) : 0.0f);
}

// ─────────────────────── TASK-424 instrumentation ───────────────────────
// `sdwrite`'s panic is `validate()` (ff.c:3465) faulting with
// EXCVADDR=0x00000001 — the FIL's `obj.fs` holds the literal integer 1 where a
// `FATFS*` belongs. Every session so far inferred that from the crash dump.
// Nothing has ever *watched* that word while the writes run, so we still don't
// know which chunk turns it, whether anything around it changes with it, or
// whether the same word first goes to 0 (which is what a `f.write()` returning
// 0 with no sd_diskio error looks like: validate() rejects a NULL fs with
// FR_INVALID_OBJECT instead of faulting on it).
//
// The FIL is reachable without esp_vfs_fat's private types.
// `esp_vfs_fat_register()` allocates ONE contiguous `vfs_fat_ctx_t` whose final
// member is `FIL files[max_files]`, with `FATFS fs` sitting earlier in the same
// block (sd_diskio.cpp's sdcard_mount passes &fs straight out of it). `obj.fs`
// is FIL's first word. So: take the FATFS* that f_getfree() hands back, scan
// forward through the block for any word equal to it, and each hit is an open
// file's slot — the exact 4 bytes that go bad.
//
// The loop then re-reads that word after every chunk and stops the moment it
// changes, BEFORE the next f_write() dereferences it. A clean stop is the
// point: a panic prints a backtrace, this prints the value, the chunk index,
// and the surrounding struct.
static void sdDumpWords(const char *tag, const uint32_t *from, int words) {
  char buf[320];
  int off = snprintf(buf, sizeof(buf), "{\"probe\":\"sdfilwatch\",\"dump\":\"%s\","
                     "\"at\":\"0x%08x\",\"w\":[", tag, (unsigned)(uintptr_t)from);
  for (int i = 0; i < words && off < (int)sizeof(buf) - 16; i++) {
    off += snprintf(buf + off, sizeof(buf) - off, "%s\"0x%08x\"", i ? "," : "",
                    (unsigned)from[i]);
  }
  snprintf(buf + off, sizeof(buf) - off, "]}");
  Serial.println(buf);
}

// Scan forward from the FATFS* for words holding that same pointer. Bounded by
// DRAM's top so a mount near the end of the heap can't walk off the mapped
// region. Returns the number of hits, writing up to `cap` addresses out.
static int sdFindFilSlots(const FATFS *fs, uint32_t **out, int cap) {
  const uint32_t target = (uint32_t)(uintptr_t)fs;
  uint32_t *p = (uint32_t *)(uintptr_t)fs;
  int n = 0;
  for (int i = 0; i < 6144 && n < cap; i++) {
    uintptr_t a = (uintptr_t)(p + i);
    if (a >= 0x3FFFFFF0u) break;
    if (p[i] == target) out[n++] = p + i;
  }
  return n;
}

void cmdSdFilWatch(const char *args) {
  int chunks = 512, statusEvery = 0;
  sscanf(args, "%d %d", &chunks, &statusEvery);
  if (chunks < 0) chunks = 0;
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdfilwatch\",\"error\":\"not mounted\"}");
    return;
  }

  DWORD freeClust = 0;
  FATFS *fs = nullptr;
  unsigned long tg = millis();
  // Same call SDFS::totalBytes()/usedBytes() make, and sdprobe already exercises
  // those on this card, so the free-cluster scan is known not to trip the WDT here.
  FRESULT gr = f_getfree("0:", &freeClust, &fs);
  Serial.printf("{\"probe\":\"sdfilwatch\",\"phase\":\"fatfs\",\"res\":%d,"
                "\"fs\":\"0x%08x\",\"fsId\":%u,\"fsType\":%u,\"pdrv\":%u,"
                "\"filSizeB\":%u,\"getfreeMs\":%lu}\n",
                (int)gr, (unsigned)(uintptr_t)fs,
                fs ? (unsigned)fs->id : 0u, fs ? (unsigned)fs->fs_type : 0u,
                fs ? (unsigned)fs->pdrv : 0u, (unsigned)sizeof(FIL),
                (unsigned long)(millis() - tg));
  if (gr != FR_OK || !fs) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdfilwatch\",\"error\":\"no FATFS\"}");
    return;
  }

  // Slots occupied BEFORE our own open — i.e. handles some other part of the
  // firmware is holding. The cross-handle-corruption hypothesis in TASK-424
  // needs this number on the record for every run, not assumed to be zero.
  uint32_t *pre[8];
  const int nPre = sdFindFilSlots(fs, pre, 8);
  for (int i = 0; i < nPre; i++) {
    Serial.printf("{\"probe\":\"sdfilwatch\",\"phase\":\"preOpen\",\"slot\":%d,"
                  "\"addr\":\"0x%08x\",\"offFromFs\":%d}\n",
                  i, (unsigned)(uintptr_t)pre[i],
                  (int)((uintptr_t)pre[i] - (uintptr_t)fs));
  }
  Serial.printf("{\"probe\":\"sdfilwatch\",\"phase\":\"preOpenCount\",\"open\":%d}\n", nPre);

  // fopen() rather than SD.open(): VFSFileImpl is a thin wrapper over exactly
  // this call, so the code path is unchanged, but holding the FILE* ourselves
  // gives us fileno() — and the fd number is the datum that separates "someone
  // closed our descriptor" from "someone stomped the memory". esp_vfs_close()
  // frees the global fd-table entry as well as calling into fatfs, so if the
  // FIL is zeroed while fcntl(fd, F_GETFD) still succeeds, the memset did NOT
  // come from a close of *our* fd.
  FILE *fp = fopen("/sd/probebench.bin", "w");
  if (!fp) {
    Serial.printf("{\"ok\":false,\"cmd\":\"sdfilwatch\",\"error\":\"open failed\","
                  "\"errno\":%d}\n", errno);
    return;
  }
  const int ourFd = fileno(fp);

  uint32_t *post[8];
  const int nPost = sdFindFilSlots(fs, post, 8);
  // Our slot is the one that appeared across the open. If the set didn't grow
  // (shouldn't happen, but say so rather than watching the wrong address) we
  // bail instead of guessing.
  uint32_t *mine = nullptr;
  for (int i = 0; i < nPost; i++) {
    bool seen = false;
    for (int j = 0; j < nPre; j++) if (pre[j] == post[i]) seen = true;
    if (!seen) { mine = post[i]; break; }
  }
  Serial.printf("{\"probe\":\"sdfilwatch\",\"phase\":\"opened\",\"chunks\":%d,"
                "\"slotsAfterOpen\":%d,\"mine\":\"0x%08x\",\"offFromFs\":%d,\"fd\":%d}\n",
                chunks, nPost, (unsigned)(uintptr_t)mine,
                mine ? (int)((uintptr_t)mine - (uintptr_t)fs) : -1, ourFd);
  if (!mine) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdfilwatch\",\"error\":\"slot not identified\"}");
    fclose(fp);
    return;
  }

  volatile uint32_t *watch = (volatile uint32_t *)mine;
  const FIL *fil = (const FIL *)mine;
  const uint32_t target = (uint32_t)(uintptr_t)fs;
  sdDumpWords("filAtOpen", (const uint32_t *)mine, 12);

  static uint8_t wbuf[512];
  memset(wbuf, 0xA5, sizeof(wbuf));
  size_t total = 0;
  int badChunk = -1;
  uint32_t badValue = 0;
  unsigned shortAt = 0;
  bool wasShort = false;
  unsigned long t0 = millis();
  for (int i = 0; i < chunks; i++) {
    size_t n = fwrite(wbuf, 1, sizeof(wbuf), fp);
    total += n;
    const uint32_t now = *watch;
    if (now != target) {
      badChunk = i;
      badValue = now;
      Serial.printf("{\"probe\":\"sdfilwatch\",\"FILCORRUPT\":true,\"atChunk\":%d,"
                    "\"objFs\":\"0x%08x\",\"expected\":\"0x%08x\",\"writeRet\":%u,"
                    "\"bytesSoFar\":%u}\n",
                    i, (unsigned)now, (unsigned)target, (unsigned)n, (unsigned)total);
      errno = 0;
      const int fdFlags = fcntl(ourFd, F_GETFD);
      Serial.printf("{\"probe\":\"sdfilwatch\",\"fdCheck\":%d,\"fd\":%d,"
                    "\"errno\":%d,\"stillOpen\":%s,\"atMs\":%lu}\n",
                    fdFlags, ourFd, errno, fdFlags >= 0 ? "true" : "false",
                    (unsigned long)millis());
      sdDumpWords("filAtFault", (const uint32_t *)mine, 12);
      // Neighbouring slots in the same files[] array: a stomp that overran one
      // handle's FIL into the next shows up here and a targeted 4-byte write
      // does not.
      if ((uintptr_t)mine >= (uintptr_t)fs + sizeof(FIL))
        sdDumpWords("filPrev", (const uint32_t *)((uintptr_t)mine - sizeof(FIL)), 8);
      sdDumpWords("filNext", (const uint32_t *)((uintptr_t)mine + sizeof(FIL)), 8);
      break;   // do NOT write again — the next f_write() is the panic
    }
    if (n != sizeof(wbuf)) {
      wasShort = true;
      shortAt = (unsigned)i;
      Serial.printf("{\"probe\":\"sdfilwatch\",\"shortWrite\":%u,\"atChunk\":%d,"
                    "\"objFs\":\"0x%08x\",\"filErr\":%u,\"filFlag\":\"0x%02x\"}\n",
                    (unsigned)n, i, (unsigned)now, (unsigned)fil->err,
                    (unsigned)fil->flag);
      break;
    }
    if (statusEvery > 0 && ((i + 1) % statusEvery) == 0) {
      Serial.printf("{\"probe\":\"sdfilwatch\",\"chunk\":%d,\"objFs\":\"0x%08x\","
                    "\"objId\":%u,\"fsId\":%u,\"fptr\":%u,\"clust\":%u,\"sect\":%u,"
                    "\"flag\":\"0x%02x\",\"err\":%u}\n",
                    i, (unsigned)now, (unsigned)fil->obj.id, (unsigned)fs->id,
                    (unsigned)fil->fptr, (unsigned)fil->clust, (unsigned)fil->sect,
                    (unsigned)fil->flag, (unsigned)fil->err);
    }
    esp_task_wdt_reset();
  }
  unsigned long elapsedMs = millis() - t0;
  // Closing a FIL whose obj.fs is garbage would fault in the same validate(),
  // so skip the close on a caught corruption and say so — the slot leaks for
  // the rest of this boot, which is acceptable in a probe that is about to be
  // rebooted anyway.
  if (badChunk < 0) fclose(fp);

  size_t endSize = 0;
  if (badChunk < 0) {
    File chk = SD.open("/probebench.bin", FILE_READ);
    if (chk) { endSize = chk.size(); chk.close(); }
  }
  Serial.printf("{\"ok\":true,\"cmd\":\"sdfilwatch\",\"bytes\":%u,\"endSizeB\":%u,"
                "\"elapsedMs\":%lu,\"corruptAtChunk\":%d,\"objFsAtFault\":\"0x%08x\","
                "\"shortWrite\":%s,\"shortAtChunk\":%u,\"closed\":%s}\n",
                (unsigned)total, (unsigned)endSize, elapsedMs, badChunk,
                (unsigned)badValue, wasShort ? "true" : "false", shortAt,
                badChunk < 0 ? "true" : "false");
}

// Removes the sdprobe fixtures. A watchdog reboot during the bench-file write leaves
// a half-written file behind, and a re-run then measures whatever that left on the
// card rather than a clean sequential file.
void cmdSdClean(const char *) {
  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdclean\",\"error\":\"not mounted\"}");
    return;
  }
  int removed = 0;
  if (SD.exists("/probebench.bin") && SD.remove("/probebench.bin")) removed++;
  char path[40];
  for (int i = 0; i < 400; i++) {
    snprintf(path, sizeof(path), "/probelist/f%03d.txt", i);
    if (SD.exists(path) && SD.remove(path)) removed++;
    if ((i % 20) == 0) esp_task_wdt_reset();
  }
  bool rmdirOk = SD.rmdir("/probelist");
  Serial.printf("{\"ok\":true,\"cmd\":\"sdclean\",\"removed\":%d,\"rmdir\":%s}\n",
                removed, rmdirOk ? "true" : "false");
}

void cmdSdProbe(const char *args) {
  int reads = 5000, skipWrites = 0;
  sscanf(args, "%d %d", &reads, &skipWrites);
  if (reads < 100) reads = 100;

  if (!s_sdReady) {
    Serial.println("{\"ok\":false,\"cmd\":\"sdprobe\",\"error\":\"mount failed\"}");
    return;
  }

  size_t freeIntBefore = s_sdBootFreeIntBefore;
  size_t freeIntAfter = s_sdBootFreeIntAfter;
  size_t lfbIntBefore = s_sdBootLfbIntBefore;
  size_t lfbIntAfter = s_sdBootLfbIntAfter;
  long heapDeltaB = (long)freeIntBefore - (long)freeIntAfter;

  sdcard_type_t cardType = SD.cardType();
  uint64_t cardSizeMB = SD.cardSize() / (1024 * 1024);
  uint64_t totalMB = SD.totalBytes() / (1024 * 1024);
  uint64_t usedMB = SD.usedBytes() / (1024 * 1024);

  // Phase markers: this probe can run for minutes on a contended bus, and a bare
  // silence is indistinguishable from a hang.
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"lfn\"}");
  esp_task_wdt_reset();

  // Long-filename round-trip: >8.3, spaces, mixed case.
  const char *kLfnPath = "/A long name (test) 01.mp3";
  bool lfnOk = false;
  if (!skipWrites) {
    File f = SD.open(kLfnPath, FILE_WRITE);
    if (f) {
      f.write((const uint8_t *)"probe", 5);
      f.close();
      File r = SD.open(kLfnPath, FILE_READ);
      if (r) {
        lfnOk = (strcmp(r.name(), "A long name (test) 01.mp3") == 0);
        r.close();
      }
      SD.remove(kLfnPath);
    }
  }

  // ~200-file directory listing timing. Files created once if absent; setup cost is
  // excluded from the timed window (browse-001 cares about steady-state page cost).
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"mkfiles\"}");
  esp_task_wdt_reset();
  const char *kListDir = "/probelist";
  const int kListFiles = 200;
  if (!skipWrites && !SD.exists(kListDir)) SD.mkdir(kListDir);
  if (!skipWrites) {
    int existing = 0;
    File dir = SD.open(kListDir);
    if (dir) {
      // NOT `for (File e = d.openNextFile(); e; e = d.openNextFile())`: the
      // increment opens the next entry while the current File is still alive, so
      // two open-file slots are needed to walk a directory one entry at a time.
      while (true) {
        File e = dir.openNextFile();
        if (!e) break;
        existing++;
        e.close();
        esp_task_wdt_reset();
      }
      dir.close();
    }
    for (int i = existing; i < kListFiles; i++) {
      char path[40];
      snprintf(path, sizeof(path), "%s/f%03d.txt", kListDir, i);
      File f = SD.open(path, FILE_WRITE);
      if (f) { f.write((const uint8_t *)"x", 1); f.close(); }
      // Every iteration, not every 20th: a single create+write+close on a
      // contended 4 MHz bus can take most of a second, and 20 of them overran
      // the 15 s TWDT outright on the first run of this probe.
      esp_task_wdt_reset();
    }
  }
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"list\"}");
  esp_task_wdt_reset();
  int listCount = 0;
  unsigned long listStartUs = micros();
  {
    File dir = SD.open(kListDir);
    if (dir) {
      while (true) {                       // see the counting loop above
        File e = dir.openNextFile();
        if (!e) break;
        listCount++;
        e.close();
        if ((listCount % 25) == 0) esp_task_wdt_reset();
      }
      dir.close();
    }
  }
  unsigned long listElapsedMs = (micros() - listStartUs) / 1000;

  // Sustained sequential-read benchmark + per-read latency histogram (T_SD_04/05).
  // Bench file created once if absent/undersized; that write is not part of the timed
  // window. Read chunk (512 B) is deliberately smaller than InBuff (6 400 B) so `reads`
  // reads comfortably exceeds the >=2 MB / N>=5 000 bar at the default arg.
  Serial.println("{\"probe\":\"sdphase\",\"phase\":\"bench-prepare\"}");
  esp_task_wdt_reset();
  const size_t kChunk = 512;
  const char *kBenchPath = "/probebench.bin";
  size_t benchFileSize = (size_t)reads * kChunk;
  const size_t kBenchFileMax = 1024 * 1024;   // read pass wraps via seek(0)
  if (benchFileSize > kBenchFileMax) benchFileSize = kBenchFileMax;
  // Any file of at least this size is a usable bench target — the read pass wraps
  // with seek(0), so an exact size buys nothing, and demanding one forces a
  // multi-megabyte rewrite on every run.
  const size_t kBenchFileMin = 64 * 1024;
  size_t benchActualSize = 0;
  bool benchFileOk = SD.exists(kBenchPath);
  if (benchFileOk) {
    File existing = SD.open(kBenchPath, FILE_READ);
    if (!existing || existing.size() < kBenchFileMin) {
      benchFileOk = false;
    } else {
      benchActualSize = existing.size();
    }
    if (existing) existing.close();
  }
  if (!benchFileOk && !skipWrites) {
    // Built in short open/write/close bursts rather than one sustained open. A long
    // single-open write reproducibly panics inside FatFs on this board -- on both cards
    // tested and at both 4 and 20 MHz -- while bursts complete cleanly (see tasks.md
    // TASK-408). The fixture is only a means to measure reads, so it is not worth
    // blocking the read benchmark on an unrelated write-path defect.
    static uint8_t wbuf[512];
    memset(wbuf, 0xA5, sizeof(wbuf));
    const int kBurstChunks = 64;
    size_t written = 0;
    bool writeOk = true;
    while (written < benchFileSize && writeOk) {
      File f = SD.open(kBenchPath, written == 0 ? FILE_WRITE : FILE_APPEND);
      if (!f) { writeOk = false; break; }
      for (int c = 0; c < kBurstChunks && written < benchFileSize; c++) {
        if (f.write(wbuf, sizeof(wbuf)) != sizeof(wbuf)) { writeOk = false; break; }
        written += sizeof(wbuf);
        esp_task_wdt_reset();
      }
      f.close();
      esp_task_wdt_reset();
    }
    if (writeOk) {
      File chk = SD.open(kBenchPath, FILE_READ);
      if (chk) {
        benchActualSize = chk.size();
        benchFileOk = (benchActualSize >= kBenchFileMin);
        chk.close();
      }
    }
    Serial.printf("{\"probe\":\"sdphase\",\"phase\":\"bench-create\",\"writtenB\":%u,"
                  "\"ok\":%s}\n", (unsigned)written, benchFileOk ? "true" : "false");
  }

  // Latency distribution as a fixed bucket histogram rather than an array of every
  // sample: at the default 5 000 reads a uint32_t[] is a 20 KB contiguous internal
  // allocation, which is exactly the class of allocation that cannot be served on a
  // live heap here (see cmdSdMem). Percentiles are reported as the containing
  // bucket's upper edge; `maxUs` stays exact, which is what the <=50 ms bar needs.
  static const uint32_t kBucketEdgeUs[] = {
    250, 500, 1000, 2000, 4000, 8000, 16000, 32000, 50000, 100000, 0xFFFFFFFFu
  };
  const int kNumBuckets = (int)(sizeof(kBucketEdgeUs) / sizeof(kBucketEdgeUs[0]));
  uint32_t buckets[kNumBuckets];
  memset(buckets, 0, sizeof(buckets));
  uint32_t maxUsExact = 0;

  Serial.printf("{\"probe\":\"sdphase\",\"phase\":\"bench-read\",\"fileOk\":%s,"
                "\"benchFileB\":%u}\n",
                benchFileOk ? "true" : "false", (unsigned)benchActualSize);
  esp_task_wdt_reset();
  size_t bytesRead = 0;
  unsigned long benchElapsedUs = 0;
  int actualReads = 0;
  if (benchFileOk) {
    File f = SD.open(kBenchPath, FILE_READ);
    if (f) {
      static uint8_t rbuf[512];
      unsigned long benchStartUs = micros();
      for (int i = 0; i < reads; i++) {
        unsigned long t0 = micros();
        size_t n = f.read(rbuf, kChunk);
        if (n == 0) {
          // Same latched-stream-error recovery as cmdSdRead: a failed physical read
          // sets the stdio error flag, seek() does not clear it, and every later read
          // then returns 0 instantly — which ends the measurement early and reports a
          // throughput far below what the card sustains. Reopen and resume.
          size_t resumeAt = (size_t)f.position();
          f.close();
          f = SD.open(kBenchPath, FILE_READ);
          if (!f) break;
          if (resumeAt + kChunk < benchActualSize) f.seek(resumeAt); else f.seek(0);
          t0 = micros();
          n = f.read(rbuf, kChunk);
        }
        unsigned long t1 = micros();
        uint32_t dtUs = (uint32_t)(t1 - t0);
        if (dtUs > maxUsExact) maxUsExact = dtUs;
        for (int b = 0; b < kNumBuckets; b++) {
          if (dtUs <= kBucketEdgeUs[b]) { buckets[b]++; break; }
        }
        actualReads++;
        bytesRead += n;
        // Outside the timed sample window (t0/t1 bracket the read alone), so
        // this does not perturb the latency histogram.
        if ((i % 50) == 0) esp_task_wdt_reset();
      }
      benchElapsedUs = micros() - benchStartUs;
      f.close();
    }
  }

  float throughputKBps = benchElapsedUs > 0
    ? ((float)bytesRead / 1024.0f) / ((float)benchElapsedUs / 1000000.0f)
    : 0.0f;

  uint32_t p50Us = 0, p99Us = 0, maxUs = maxUsExact;
  if (actualReads > 0) {
    uint32_t need50 = (uint32_t)((actualReads * 50 + 99) / 100);
    uint32_t need99 = (uint32_t)((actualReads * 99 + 99) / 100);
    uint32_t cum = 0;
    for (int b = 0; b < kNumBuckets; b++) {
      cum += buckets[b];
      if (!p50Us && cum >= need50) p50Us = kBucketEdgeUs[b];
      if (!p99Us && cum >= need99) { p99Us = kBucketEdgeUs[b]; break; }
    }
    // Never report a bucket edge above the exact worst sample.
    if (p50Us > maxUsExact) p50Us = maxUsExact;
    if (p99Us > maxUsExact) p99Us = maxUsExact;
  }

  {
    char histo[192];
    int off = 0;
    for (int b = 0; b < kNumBuckets && off < (int)sizeof(histo) - 12; b++) {
      off += snprintf(histo + off, sizeof(histo) - off, "%s%lu",
                      b ? "," : "", (unsigned long)buckets[b]);
    }
    Serial.printf("{\"probe\":\"sdhisto\",\"edgesUs\":\"250,500,1k,2k,4k,8k,16k,32k,50k,100k,inf\","
                  "\"counts\":[%s]}\n", histo);
  }

  Serial.printf(
    "{\"ok\":true,\"cmd\":\"sdprobe\","
    "\"cardType\":\"%s\",\"cardSizeMB\":%llu,\"totalMB\":%llu,\"usedMB\":%llu,"
    "\"heapDeltaB\":%ld,\"freeIntBefore\":%u,\"freeIntAfter\":%u,"
    "\"lfbIntBefore\":%u,\"lfbIntAfter\":%u,"
    "\"lfnOk\":%s,"
    "\"listFiles\":%d,\"listElapsedMs\":%lu,"
    "\"benchReads\":%d,\"benchBytes\":%u,\"benchElapsedMs\":%lu,\"throughputKBps\":%.1f,"
    "\"p50Ms\":%.2f,\"p99Ms\":%.2f,\"maxMs\":%.2f}\n",
    sdCardTypeName(cardType), (unsigned long long)cardSizeMB,
    (unsigned long long)totalMB, (unsigned long long)usedMB,
    heapDeltaB, (unsigned)freeIntBefore, (unsigned)freeIntAfter,
    (unsigned)lfbIntBefore, (unsigned)lfbIntAfter,
    lfnOk ? "true" : "false",
    listCount, listElapsedMs,
    actualReads, (unsigned)bytesRead, (unsigned long)(benchElapsedUs / 1000), throughputKBps,
    p50Us / 1000.0f, p99Us / 1000.0f, maxUs / 1000.0f);
}
#endif // SERIAL_DEBUG
