// debug/serialConsole/cmdGet.cpp — `get` — debug variable reads, out-of-line
// (M-SRCLAYOUT Stage E / TASK-471). Body compiles only under SERIAL_DEBUG;
// the .cpp itself is always compiled, same convention as appTable.cpp /
// cmdSystem.cpp / cmdMisc.cpp / cmdTouch.cpp.
#include "debug/serialConsole/cmdGet.h"
#include "debug/serialConsole/cmdMisc.h"   // readbackSignature (ADR-064 D1)
#include "debug/timeInject.h"             // dbgTimeFrozen (ADR-064 D5)
#include "debug/bodWatch.h"               // BodSnapshot / bodWatchGetSnapshot() (TASK-678 F-1)

#ifdef SERIAL_DEBUG
#include <Arduino.h>
#include <string.h>
#include <time.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_heap_caps.h>
#include <esp_task_wdt.h>
#include "appShell.h"                     // AppId, currentAppId
#include "shell/appTable.h"               // g_apps[], every g_XApp + *DbgGet(), pulls
                                           // webRadioApp.h/localPlayerApp.h and therefore
                                           // audio/audioEngine.h, winamp/winampDisplay.h,
                                           // winamp/vuMeter.h transitively
#include "shell/shellState.h"             // shell::state()
#include "dataTask.h"
#include "spotifyTask.h"
#include "wifiDiag.h"
#include "settingsStorage.h"              // g_settings, SettingsStorage, PR_NUM_LOCS
#include "spotifyDisplay.h"               // SpotifyDisplay
#include "util/timeFmt.h"                 // clockHour/clockAmPm/fmtDate
#include "util/asciiFold.h"               // textfold::foldUtf8

extern WinampDisplay winampDisplay;       // defined in main.cpp
extern SpotifyDisplay *spotifyDisplay;    // defined in main.cpp (build-variant display)

void cmdGet(const char *args) {
  // TASK-401: widened 256 -> 512. `get wifiSaved` (5 entries x up to a
  // 32-char ssid + 10-digit lastUsedMs) needs up to ~390 B; 256 silently
  // truncated it. Every other dbgGet-chain caller below stays well under
  // either size, so this is a pure headroom increase, not a behavior change.
  char buf[512]; buf[0] = '\0';
  // TASK-255 (M-WEBRADIO-NOPSRAM): build-variant query (V0). Lets the harness pick a
  // Spotify-poll-free readiness path and lets V2 assert the variant.
  // ADR-064 D1 (TASK-638): panel-readback signature, ON DEMAND ONLY (D2).
  if (strncmp(args, "sig", 3) == 0 && (args[3] == '\0' || args[3] == ' ')) {
    readbackSignature(args + 3);
    return;
  }
  // ADR-064 D5 (TASK-638): the injected/frozen wall time the Clock family reads.
  if (strcmp(args, "now") == 0) {
    time_t frozenAt = 0;
    const bool frozen = dbgTimeFrozen(&frozenAt);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"now\",\"epoch\":%ld,"
                  "\"frozen\":%s,\"frozenEpoch\":%ld,\"last\":true}\n",
                  (long)time(nullptr), frozen ? "true" : "false", (long)frozenAt);
    return;
  }
  // TASK-678 (F-1): structured `get bod` — the B covariate every suite test
  // can read before/after its body (PROP-011-rig-ground-truth.md §3.1 item
  // 1). hist[] is indexed by ladder-bottomed level (0..7); minLevel=8 means
  // no event has been captured since the last `bod <n>`/`reboot` arm.
  if (strcmp(args, "bod") == 0) {
    BodSnapshot s;
    bodWatchGetSnapshot(&s);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"bod\",\"count\":%lu,"
                  "\"dropped\":%lu,\"firstUs\":%lu,\"lastUs\":%lu,\"minLevel\":%u,"
                  "\"maxDurUs\":%u,\"hist\":[%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu],"
                  "\"phaseAtFirst\":%u,\"thres\":%u,\"armed\":%s,\"last\":true}\n",
                  (unsigned long)s.count, (unsigned long)s.dropped,
                  (unsigned long)s.firstUs, (unsigned long)s.lastUs,
                  (unsigned)s.minLevel, (unsigned)s.maxDurUs,
                  (unsigned long)s.hist[0], (unsigned long)s.hist[1],
                  (unsigned long)s.hist[2], (unsigned long)s.hist[3],
                  (unsigned long)s.hist[4], (unsigned long)s.hist[5],
                  (unsigned long)s.hist[6], (unsigned long)s.hist[7],
                  (unsigned)s.phaseAtFirst, (unsigned)s.thres,
                  s.armed ? "true" : "false");
    return;
  }
  if (strcmp(args, "variant") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"variant\",\"spotify\":\"%s\",\"last\":true}\n",
#ifdef DISABLE_SPOTIFY
                  "off"
#else
                  "on"
#endif
                  );
    return;
  }
  // TASK-645 (M-HARNESS2 R30 / ADR-066 D3): the BOARD's own identity, so a run
  // artifact can say which physical board produced it. The host had nothing but
  // `{port, baud}`, which is a fact about the CABLE — a USB re-enumeration
  // renames /dev/ttyUSB0 to /dev/ttyUSB1 on the same board, and moving a second
  // board onto the free node gives two different boards the same premise. The
  // efuse MAC is factory-programmed, survives re-enumeration, reflashing and an
  // NVS wipe, and is the one number on the device nothing in this project can
  // change. Additive per ADR-065 D4; read-only; no state touched.
  if (strcmp(args, "boardId") == 0) {
    uint64_t mac = ESP.getEfuseMac();     // 48-bit, low bytes first
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"boardId\","
                  "\"val\":\"%02x%02x%02x%02x%02x%02x\",\"src\":\"efuse-mac\","
                  "\"rev\":%u,\"last\":true}\n",
                  (unsigned)((mac >> 0)  & 0xFF), (unsigned)((mac >> 8)  & 0xFF),
                  (unsigned)((mac >> 16) & 0xFF), (unsigned)((mac >> 24) & 0xFF),
                  (unsigned)((mac >> 32) & 0xFF), (unsigned)((mac >> 40) & 0xFF),
                  (unsigned)ESP.getChipRevision());
    return;
  }
  // TASK-410 (T_AE_07/09/10): raw engine state for `set aePlayFile` — isRunning()
  // and the pump's result enum, independent of WebRadioApp's own dbgGet (which
  // reads WRPlayState, never touched by aeConnectFile()'s bypass path).
  if (strcmp(args, "aePlay") == 0) {
    bool running = false;
    uint32_t filePos = 0, fileSize = 0, curSec = 0, durSec = 0;
    if (s_wr_audio && xSemaphoreTake(s_wrAudioMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
      running = s_wr_audio->isRunning();
      filePos = s_wr_audio->getFilePos();
      fileSize = s_wr_audio->getFileSize();
      curSec = s_wr_audio->getAudioCurrentTime();
      durSec = s_wr_audio->getAudioFileDuration();
      xSemaphoreGive(s_wrAudioMutex);
    }
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"aePlay\",\"alive\":%d,"
                  "\"running\":%d,\"pumpResult\":%u,\"eofPending\":%d,"
                  "\"filePos\":%u,\"fileSize\":%u,\"curSec\":%u,\"durSec\":%u,\"last\":true}\n",
                  (int)wrPumpAlive(), (int)running, (unsigned)s_wrPumpResult,
                  (int)s_aeEofPending, (unsigned)filePos, (unsigned)fileSize,
                  (unsigned)curSec, (unsigned)durSec);
    return;
  }
  // TASK-274 (M-WIFI-DIAG §3.2): WiFi ground truth for outage attribution.
  // ms = device→host clock anchor; disc*/lastGotIpMs from the wifiDiag handler.
  // Field set VE-gated (BP-024) — extend, don't rename.
  if (strcmp(args, "wifi") == 0) {
    // TASK-544 (G7): one atomic snapshot instead of four direct field reads
    // that could pair a fresh field with a stale one across a disconnect
    // landing mid-read (arduino_events is priority 19, preempts loopTask
    // between any two of these).
    wifiDiag::DiscSnapshot ds = wifiDiag::discSnapshot();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifi\","
                  "\"ms\":%lu,\"status\":%d,\"rssi\":%d,\"ip\":\"%s\",\"ch\":%d,"
                  "\"discCount\":%lu,\"lastDiscReason\":%u,\"lastDiscMs\":%lu,"
                  "\"lastGotIpMs\":%lu,\"kicks\":%lu,\"last\":true}\n",
                  (unsigned long)millis(), (int)WiFi.status(),
                  (WiFi.status() == WL_CONNECTED) ? (int)WiFi.RSSI() : 0,
                  WiFi.localIP().toString().c_str(), (int)WiFi.channel(),
                  (unsigned long)ds.discCount,
                  (unsigned)ds.lastDiscReason,
                  (unsigned long)ds.lastDiscMs,
                  (unsigned long)ds.lastGotIpMs,
                  (unsigned long)wifiDiag::superviseKicks);
    return;
  }
  // TASK-299: dataTask queue/dispatch + tlsYield-handshake snapshot. The three
  // "station fetch never ran" signatures read as: wrDrops advanced = request
  // never enqueued; queueWaiting>0 with inFlight stuck on another type =
  // wedged behind a prior fetcher; wrPhase=0 with old wrPhaseMs = parked in
  // tlsYield (yieldCount/tlsStopped show the handshake side).
  if (strcmp(args, "dataq") == 0) {
    dataTask::DbgQueueState q;
    dataTask::dbgQueueState(&q);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"dataq\",\"ms\":%lu,"
                  "\"queueWaiting\":%u,\"pendingMask\":%lu,\"inFlight\":%d,"
                  "\"inFlightMs\":%lu,\"wrPhase\":%d,\"wrPhaseMs\":%lu,"
                  "\"wrEnqueues\":%lu,\"wrDrops\":%lu,"
                  "\"yieldCount\":%u,\"tlsStopped\":%s,"
                  "\"spAct\":%d,\"spActMs\":%lu,\"last\":true}\n",
                  (unsigned long)millis(),
                  (unsigned)q.queueWaiting, (unsigned long)q.pendingMask,
                  (int)q.inFlight, (unsigned long)q.inFlightMs,
                  (int)q.wrPhase, (unsigned long)q.wrPhaseMs,
                  (unsigned long)q.wrEnqueues, (unsigned long)q.wrDrops,
                  (unsigned)spotifyTask::tlsYieldCount(),
                  spotifyTask::tlsStoppedFlag() ? "true" : "false",
                  (int)spotifyTask::taskActivity(),
                  (unsigned long)spotifyTask::taskActivityMs());
    return;
  }
  // TASK-344 (M-CERT-ERRCODE): peek whether a `set certbreak <app>` arm is
  // still pending (armed=false once the target fetch has consumed it).
  if (strcmp(args, "certbreak") == 0) {
    int armed = dataTask::debugPeekCertBreak();
    if (armed < 0) {
      Serial.println("{\"ok\":true,\"cmd\":\"get\",\"var\":\"certbreak\","
                      "\"armed\":false,\"last\":true}");
    } else {
      Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"certbreak\","
                    "\"armed\":true,\"type\":%d,\"last\":true}\n", armed);
    }
    return;
  }
  // TASK-282: beacon-watcher stats — evidence at the antenna. count/gapMax/
  // gapsOver1s split BEACON_TIMEOUT into "beacons stopped arriving" (H-A/H-C)
  // vs "beacons fine, stack timed out" (H-B). otherMgmt proves rx was alive.
  if (strcmp(args, "beacon") == 0) {
    // TASK-544 (G6): one atomic snapshot instead of seven direct field reads
    // racing promiscCb on a different core.
    wifiDiag::BeaconStats bs = wifiDiag::beaconStatsSnapshot();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"beacon\","
                  "\"active\":%s,\"count\":%lu,\"gapMaxMs\":%lu,\"gapsOver1s\":%lu,"
                  "\"lastAgoMs\":%lu,\"rssi\":%ld,\"noiseFloor\":%ld,"
                  "\"otherMgmt\":%lu,\"last\":true}\n",
                  wifiDiag::beaconWatchActive() ? "true" : "false",
                  (unsigned long)bs.count,
                  (unsigned long)bs.gapMaxMs,
                  (unsigned long)bs.gapsOver1s,
                  (unsigned long)(bs.lastMs ? millis() - bs.lastMs : 0),
                  (long)bs.lastRssi,
                  (long)bs.noiseFloor,
                  (unsigned long)bs.otherMgmt);
    return;
  }
  // TASK-282: async scan result — reports every AP whose SSID matches ours
  // (multi-BSSID roaming visible) plus total network count.
  if (strcmp(args, "wifiScan") == 0) {
    int16_t n = WiFi.scanComplete();
    if (n < 0) {
      // TASK-473 (G1, M-CONCURRENCY §5): WIFI_SCAN_RUNNING is the only
      // non-terminal state — auto-reconnect (silenced by the `set wifiScan`
      // handler in cmdSet.cpp) must stay off until the scan is actually
      // done, or the driver's reconnect retries can collide with it exactly
      // as they did before TASK-436's fix, just async instead of sync.
      // WIFI_SCAN_FAILED (idle, no scan outstanding) is terminal too.
      if (n != WIFI_SCAN_RUNNING) WiFi.setAutoReconnect(true);
      Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifiScan\","
                    "\"state\":\"%s\",\"last\":true}\n",
                    n == WIFI_SCAN_RUNNING ? "running" : "idle");
      return;
    }
    WiFi.setAutoReconnect(true);   // scan completed with results — re-arm now
    String own = WiFi.SSID();
    // TASK-426: matches:[] alone is ambiguous — an empty `own` (STA configured
    // but never associated) produces the same output as "target AP absent".
    // Dump own + the full scan list so the two cases are distinguishable.
    Serial.printf("[wifiScan] own=\"%s\" n=%d\n", own.c_str(), (int)n);
    for (int i = 0; i < n; i++)
      Serial.printf("[wifiScan]   ssid=\"%s\" bssid=%s rssi=%d ch=%d enc=%d\n",
                    WiFi.SSID(i).c_str(), WiFi.BSSIDstr(i).c_str(),
                    (int)WiFi.RSSI(i), (int)WiFi.channel(i),
                    (int)WiFi.encryptionType(i));
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifiScan\",\"total\":%d,"
                  "\"matches\":[", (int)n);
    bool first = true;
    for (int i = 0; i < n; i++) {
      if (WiFi.SSID(i) != own) continue;
      Serial.printf("%s{\"bssid\":\"%s\",\"rssi\":%d,\"ch\":%d}",
                    first ? "" : ",", WiFi.BSSIDstr(i).c_str(),
                    (int)WiFi.RSSI(i), (int)WiFi.channel(i));
      first = false;
    }
    Serial.printf("],\"last\":true}\n");
    WiFi.scanDelete();
    return;
  }
  // TASK-426: dump the STA connect config. A scan that finds the AP while
  // esp_wifi_connect() returns NO_AP_FOUND means connect is filtering it out:
  // a stale bssid/channel pin or an rssi/authmode threshold are the candidates.
  if (strcmp(args, "wifiCfg") == 0) {
    wifi_config_t c = {};
    esp_err_t e = esp_wifi_get_config(WIFI_IF_STA, &c);
    Serial.printf("[wifiCfg] err=%d ssid=\"%s\" pwlen=%u bssid_set=%d "
                  "bssid=%02x:%02x:%02x:%02x:%02x:%02x ch=%u "
                  "scan_method=%d sort=%d thr_rssi=%d thr_auth=%d pmf_r=%d\n",
                  (int)e, (const char*)c.sta.ssid,
                  (unsigned)strlen((const char*)c.sta.password),
                  (int)c.sta.bssid_set,
                  c.sta.bssid[0], c.sta.bssid[1], c.sta.bssid[2],
                  c.sta.bssid[3], c.sta.bssid[4], c.sta.bssid[5],
                  (unsigned)c.sta.channel,
                  (int)c.sta.scan_method, (int)c.sta.sort_method,
                  (int)c.sta.threshold.rssi, (int)c.sta.threshold.authmode,
                  (int)c.sta.pmf_cfg.required);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"wifiCfg\",\"last\":true}\n");
    return;
  }
  // appId — shell-owned; WinampDisplay cannot reference currentAppId.
  if (strcmp(args, "ip") == 0) {
    // TASK-248: LAN IP so the stress harness can read logs over the /log HTTP ring
    // (off the CH340 serial bottleneck) while keeping commands on serial.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"ip\",\"ip\":\"%s\",\"last\":true}\n",
                  WiFi.localIP().toString().c_str());
    return;
  }
  if (strcmp(args, "appId") == 0) {
#define APP_X(Name, icon, cfg, disp) #Name,
    static const char* kAppNames[] = {
#include "appRegistry.h"
    };
#undef APP_X
    const char* nm = ((int)currentAppId < (int)AppId::COUNT)
                   ? kAppNames[(int)currentAppId] : "Unknown";
    Serial.printf("{\"ok\":true,\"cmd\":\"get\","
                  "\"var\":\"appId\",\"id\":%d,\"name\":\"%s\",\"last\":true}\n",
                  (int)currentAppId, nm);
    return;
  }
  if (strcmp(args, "activeError") == 0) {
    // TASK-245 / ADR-046: active app's error + connecting state (drive the
    // red / amber active-bar) + the Spotify sources so VE can assert the
    // boot-amber → green/red path.
    bool ae = g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->hasError();
    bool ac = g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->isConnecting();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"activeError\","
                  "\"active\":%s,\"connecting\":%s,"
                  "\"spotifyAuthError\":%s,\"spotifyDegraded\":%s,\"spotifyConnecting\":%s,"
                  "\"last\":true}\n",
                  ae ? "true" : "false",
                  ac ? "true" : "false",
                  spotifyTask::authError() ? "true" : "false",
                  // TASK-366: surfaced alongside spotifyAuthError so VE can assert the
                  // two sticky latches independently (both OR into `active`/hasError()).
                  spotifyTask::degraded() ? "true" : "false",
                  spotifyTask::connecting() ? "true" : "false");
    return;
  }
  // TASK-518 (M-TESTBASE P4): QUIESCENCE. One honest answer to "is the device
  // finished doing what I asked?", so a host test can poll this instead of
  // guessing with a sleep() (252 of them in run_serialdbg_tests.py alone,
  // 539 across app/tools, calibrated against 2 named constants).
  //
  // Three contributing terms, ALL reported alongside the verdict, because a
  // bare "idle":false is undiagnosable — the caller has to be able to say WHY
  // it is still waiting without issuing six more commands:
  //   shellBusy — the shell pre-dispatch gate, `shell::state().busy` since
  //               M-SRCLAYOUT Stage D (was main.cpp's g_shellBusy). A switchApp or a
  //               long handleInput is running; taps are being dropped)
  //   appOp     — the ACTIVE app's hasInFlightOp(): an operation THAT APP
  //               STARTED is still running. NOT isConnecting(), which means
  //               two different things across the 13 apps and, for Spotify,
  //               never latches false under this rig's live 403 (TASK-243).
  //               See App::hasInFlightOp() for the whole contract.
  //   dataq     — dataTask queue depth + the FetchType currently dispatched
  //               (-1 = none). This is the term that covers the apps holding
  //               no pending flag of their own (Weather, Crypto, and Stock's
  //               cadence refreshes) — their fetches are observable only here.
  //
  // Deliberately NOT a term: spotifyTask's background cadence poll. It is not
  // an operation anyone asked for, and a Spotify-mode device would never read
  // idle if it were. `get dataq` still exposes spAct for that.
  //
  // Field set is additive-only (BP-024) — extend, never rename.
  if (strcmp(args, "idle") == 0) {
    const int ai = (int)currentAppId;
    const bool appOp = g_apps[ai] && g_apps[ai]->hasInFlightOp();
    dataTask::DbgQueueState q;
    dataTask::dbgQueueState(&q);
    const bool dq = (q.queueWaiting > 0) || (q.inFlight >= 0);
    const bool idle = !shell::state().busy && !appOp && !dq;
#define APP_X(Name, icon, cfg, disp) #Name,
    // const-const so the pointer array is a constant expression and lands in
    // .rodata (flash), not .dram0.data — `get appId`'s otherwise-identical
    // table is non-const and does cost RAM. Debug-build headroom is ~8 KB
    // (M-TESTBASE §7) but there is no reason to spend any of it here.
    static const char* const kIdleAppNames[] = {
#include "appRegistry.h"
    };
#undef APP_X
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"idle\",\"ms\":%lu,"
                  "\"idle\":%s,\"shellBusy\":%s,\"appOp\":%s,"
                  "\"dataq\":%u,\"dataqInFlight\":%d,"
                  "\"appId\":%d,\"appName\":\"%s\",\"last\":true}\n",
                  (unsigned long)millis(),
                  idle       ? "true" : "false",
                  shell::state().busy ? "true" : "false",
                  appOp      ? "true" : "false",
                  (unsigned)q.queueWaiting, (int)q.inFlight,
                  ai,
                  (ai < (int)AppId::COUNT) ? kIdleAppNames[ai] : "Unknown");
    return;
  }
  if (strcmp(args, "stacks") == 0) {
    // TASK-240: report each task's configured stack size + watermark (min free
    // ever). used = size - free; trim target = used + margin. Also include the
    // current free heap + largest block so a fetch session can be correlated.
    size_t dF = dataTask::stackHighWaterBytes(),  dS = dataTask::stackSizeBytes();
    size_t sF = spotifyTask::stackHighWaterBytes(), sS = spotifyTask::stackSizeBytes();
    // TASK-278: wrPump only exists while WebRadio has played at least once this
    // session — report 0/0/0 before then (wrPumpAlive() gates the size too, so
    // "used" doesn't read as a false full-stack allocation). webRadioApp.h is
    // only compiled under WINAMP_DISPLAY, which TASK-501 made unconditional
    // (every buildable env defines it — see include above / app/platformio.ini).
    size_t wS = wrPumpAlive() ? wrPumpStackSizeBytes() : 0;
    size_t wF = wrPumpStackHighWaterBytes();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"stacks\","
                  "\"dataSize\":%u,\"dataFree\":%u,\"dataUsed\":%u,"
                  "\"spotSize\":%u,\"spotFree\":%u,\"spotUsed\":%u,"
                  "\"wrPumpSize\":%u,\"wrPumpFree\":%u,\"wrPumpUsed\":%u,"
                  "\"heapFree\":%u,\"heapMaxAlloc\":%u,\"last\":true}\n",
                  (unsigned)dS,(unsigned)dF,(unsigned)(dS-dF),
                  (unsigned)sS,(unsigned)sF,(unsigned)(sS-sF),
                  (unsigned)wS,(unsigned)wF,(unsigned)(wS>wF?wS-wF:0),
                  (unsigned)ESP.getFreeHeap(),(unsigned)ESP.getMaxAllocHeap());
    return;
  }
  // T_MB_PROBE_00 (TASK-261 Phase 0): caps-split heap query — internal vs DMA pool,
  // free + largest_free_block each. Distinguishes the two pools so fragmentation in
  // the INTERNAL (large) pool is visible separately from the scarce DMA pool.
  // TASK-443 option (e) decision probe — `get heapHist`. Answers the one question
  // that separates ruling option (a) (retire the arena from the FILE path) from
  // option (e) (keep it, but reserve the decoder's nine blocks instead of one
  // 24 576 B block): does this heap actually have somewhere to put nine smaller
  // allocations, or is it one big block and dust?
  //
  // Two independent measurements, both under MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT
  // — the SAME cap the arena allocates with. Reading the 32-bit-inclusive figure
  // here and comparing it against an 8-bit one is the BP-055 error that made
  // TASK-435 look like a regression for four days.
  //
  //  1. A hole histogram: how many blocks of 8708 / 4096 / 1024 B can be held at
  //     once, each class measured from the same starting state and freed after.
  //     8708 is SubbandInfo_t, the decoder's largest single allocation.
  //  2. The real thing: call MP3Decoder_AllocateBuffers() with the arena INACTIVE,
  //     so its nine allocations take mb_arena_alloc()'s libc fallback — exactly
  //     what option (e)/(a) would do in production. No hardcoded size table, no
  //     new patch to the vendored fork, real sizes, real allocator path. The
  //     [mbdbg] helix line the decoder already prints reports all nine sizes.
  if (strcmp(args, "heapHist") == 0) {
    // Declared here rather than #including mp3_decoder.h at the top of this TU:
    // the header pulls the whole Helix type set into a translation unit that has
    // no other business with it, and these two symbols are the vendored library's
    // public API (mp3_decoder.h:458-459), stable across the pinned v2.3.0.
    extern bool MP3Decoder_AllocateBuffers(void);
    extern void MP3Decoder_FreeBuffers(void);

    constexpr uint32_t CAP8 = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    // Refuse while an engine exists: AllocateBuffers() would stomp a live decoder.
    if (s_wr_audio || wrPumpAlive()) {
      Serial.println("{\"ok\":false,\"cmd\":\"get\",\"var\":\"heapHist\","
                     "\"error\":\"engine up — stop playback first\",\"last\":true}");
      return;
    }
    const size_t free0 = heap_caps_get_free_size(CAP8);
    const size_t lfb0  = heap_caps_get_largest_free_block(CAP8);

    // (1) hole histogram
    static const size_t kClasses[3] = { 8708, 4096, 1024 };
    int counts[3] = { 0, 0, 0 };
    void* held[48];
    for (int c = 0; c < 3; c++) {
      int n = 0;
      while (n < 48) {
        void* p = heap_caps_malloc(kClasses[c], CAP8);
        if (!p) break;
        held[n++] = p;
      }
      counts[c] = n;
      for (int i = 0; i < n; i++) free(held[i]);
      esp_task_wdt_reset();
    }

    // (2) the real nine, through the real path, arena inactive
    const bool helixOk = MP3Decoder_AllocateBuffers();
    const size_t freeH = heap_caps_get_free_size(CAP8);
    const size_t lfbH  = heap_caps_get_largest_free_block(CAP8);
    MP3Decoder_FreeBuffers();
    const size_t free1 = heap_caps_get_free_size(CAP8);
    const size_t lfb1  = heap_caps_get_largest_free_block(CAP8);

    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"heapHist\","
                  "\"free8\":%u,\"lfb8\":%u,"
                  "\"n8708\":%d,\"n4096\":%d,\"n1024\":%d,"
                  "\"helixOk\":%s,\"free8Helix\":%u,\"lfb8Helix\":%u,"
                  "\"free8After\":%u,\"lfb8After\":%u,\"last\":true}\n",
                  (unsigned)free0, (unsigned)lfb0,
                  counts[0], counts[1], counts[2],
                  helixOk ? "true" : "false",
                  (unsigned)freeH, (unsigned)lfbH,
                  (unsigned)free1, (unsigned)lfb1);
    return;
  }
  if (strcmp(args, "heap") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"heap\","
                  "\"freeInt\":%u,\"lfbInt\":%u,"
                  "\"freeDma\":%u,\"lfbDma\":%u,\"last\":true}\n",
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
    return;
  }
  if (strcmp(args, "weatherReady") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"weatherReady\","
                  "\"ready\":%s,\"last\":true}\n", g_WeatherApp.dataReady() ? "true" : "false");
    return;
  }
  if (strcmp(args, "cryptoReady") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"cryptoReady\","
                  "\"ready\":%s,\"last\":true}\n", g_CryptoApp.dataReady() ? "true" : "false");
    return;
  }
  if (strcmp(args, "cryptoHttpCode") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"cryptoHttpCode\","
                  "\"val\":%d,\"last\":true}\n", dataTask::lastCryptoHttpCode());
    return;
  }
  if (strcmp(args, "stockQuoteProgress") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"stockQuoteProgress\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::stockQuoteProgress());
    return;
  }
  if (strcmp(args, "weatherFetchPhase") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"weatherFetchPhase\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::weatherFetchPhase());
    return;
  }
  if (strcmp(args, "cryptoFetchPhase") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"cryptoFetchPhase\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::cryptoFetchPhase());
    return;
  }
  if (strcmp(args, "stockChartProgress") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"stockChartProgress\","
                  "\"val\":%d,\"last\":true}\n", (int)dataTask::stockChartProgress());
    return;
  }
  if (strcmp(args, "golAlive") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"golAlive\","
                  "\"count\":%d,\"last\":true}\n", g_LifeApp.golAliveCount());
    return;
  }
  if (strcmp(args, "shellBusy") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"shellBusy\","
                  "\"busy\":%s,\"last\":true}\n", shell::state().busy ? "true" : "false");
    return;
  }
  if (strcmp(args, "shellCooldown") == 0) {
    // TASK-294: shell-level post-gesture cooldown (ShellState::cooldownMs) remaining.
    // Distinct from winampDisplay's `cooldown` var (TASK-052 dead-zone-tap
    // force-poll cooldown in SpotifyApp) despite the similar name.
    unsigned long now = millis();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"shellCooldown\","
                  "\"remainingMs\":%lu,\"last\":true}\n",
                  (shell::state().cooldownMs > now) ? (shell::state().cooldownMs - now) : 0UL);
    return;
  }
  if (strcmp(args, "visMode") == 0) {
    vu::VisMode m = vu::currentMode();
    int mi = (m == vu::VIS_ATLAS_MODE) ? 0
           : (m == vu::VIS_VU)         ? 1
           : (m == vu::VIS_BLANK)      ? 2
           : (m == vu::VIS_WAVE_ATLAS) ? 3
           : (m == vu::VIS_SPECTRUM)   ? 4
           : (m == vu::VIS_WAVE)       ? 5 : -1;
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"visMode\","
                  "\"mode\":%d,\"last\":true}\n", mi);
    return;
  }
  if ((spotifyDisplay && spotifyDisplay->dbgGet(args, buf, sizeof(buf)))
      || spotifyTask::dbg_get(args, buf, sizeof(buf))) {
    // buf[0]=='\0' means the owner used multi-part Serial.printf directly.
    if (buf[0]) {
      Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    }
    return;
  }
  if (settingsDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (stockDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
#ifdef SERIAL_DEBUG
  if (matrixDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (lifeDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (cryptoDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (aquariumDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
#endif
  if (teletextDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (planeRadarDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  // TASK-501: WINAMP_DISPLAY is unconditionally defined — no #ifdef needed.
  if (webRadioDbgGet(args, buf, sizeof(buf))) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",%s}\n", buf);
    return;
  }
  if (strcmp(args, "clockStyle") == 0) {
    static const char* kSN[] = {"digital","flip","nixie","vfd"};
    uint8_t cs = (uint8_t)g_settings.clockStyle % 4;
    // M-CLOCK-TAP-CYCLE (TASK-346): themes + dirty added — dirty is the
    // un-flushed-change flag that makes deferred persistence testable
    // without pulling settings.json (pair with `get settingsSaveCount`).
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"clockStyle\","
                  "\"val\":%d,\"name\":\"%s\",\"nixieTheme\":%d,\"vfdTheme\":%d,"
                  "\"dirty\":%s,\"last\":true}\n", cs, kSN[cs],
                  (int)g_settings.nixieTheme, (int)g_settings.vfdTheme,
                  g_ClockApp.dbgStyleDirty() ? "true" : "false");
    return;
  }
  if (strcmp(args, "clockLastAction") == 0) {
    // M-CLOCK-TAP-CYCLE (TASK-346): tap-zone outcome observable
    // (TAP_FACE / TAP_THEME / TAP_THEME_NA / DEBOUNCE) — prLastAction's
    // role for the clock's two hit boxes.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"clockLastAction\","
                  "\"val\":\"%s\",\"last\":true}\n", g_ClockApp.dbgLastAction());
    return;
  }
  // ── M-TESTBASE P2: `get player` — the whole player-slot contract, one line ──
  // WHY THIS EXISTS: the ~30 player debug keys are organised by implementation
  // silo (wr* / pl* / aePlay / arenaStats), so answering "is the player slot
  // consistent?" took eight commands correlated by hand, with a different
  // subset valid per mode. A cross-mode bug is invisible to a per-mode
  // observation — which is exactly what X055/X061/X062 are.
  //
  // HONEST SCOPE (@Architect review B4): this is aggregation of existing state
  // PLUS two genuinely new observables — PlSrcKind (nothing reported which
  // source was driving PLEDIT) and viewOrder (PlaylistIndex::_view was private
  // with no accessor). Playlist fields are LocalPlayer-only and report
  // "n/a" elsewhere, deliberately, rather than a plausible-looking zero.
  //
  // Field set is ADDITIVE-ONLY and VE-gated (BP-024): extend, never rename.
  if (strcmp(args, "player") == 0) {
    static const char* kPmNames[]  = { "Spotify", "WebRadio", "Player" };
    static const char* kSrcNames[] = { "None", "SpotifyQueue", "StationList", "LocalPlaylist" };
    const uint8_t pm = g_settings.playerMode;
    const uint8_t sk = (uint8_t)winampDisplay.pleditLastSrcKind();
    const int ai = (int)currentAppId;
    const bool pend = g_apps[ai] && g_apps[ai]->hasPendingAsync();
    const bool err  = g_apps[ai] && g_apps[ai]->hasError();
    const bool conn = g_apps[ai] && g_apps[ai]->isConnecting();

    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"player\","
                  "\"mode\":%u,\"modeName\":\"%s\","
                  "\"caps\":%u,\"srcKind\":%u,\"srcName\":\"%s\","
                  "\"arenaHeld\":%d,\"pending\":%d,\"err\":%d,\"connecting\":%d,",
                  (unsigned)pm, (pm < 3) ? kPmNames[pm] : "unknown",
                  (unsigned)winampDisplay.playerCaps(),
                  (unsigned)sk, (sk < 4) ? kSrcNames[sk] : "unknown",
                  (int)mb_arena_active(), (int)pend, (int)err, (int)conn);

    // Playlist half — LocalPlayer only. X062's subject: playOrder vs viewOrder.
    // The hashes are order-sensitive (FNV-1a over the u16 sequence) so a
    // permutation is detectable without dumping up to 256 entries per poll.
    if (pm == 2) {
      g_LocalPlayerApp.dbgPlayerVector();
    } else {
      Serial.printf("\"plCount\":null,\"playHash\":null,\"viewHash\":null,"
                    "\"note\":\"n/a — playOrder/viewOrder exist only in LocalPlayer\",");
    }
    Serial.printf("\"last\":true}\n");
    return;
  }
  // ── M-TESTBASE §8: which hit-surface currently owns the mode-cycle ──────────
  // The ONE place the gesture->operation binding is stated for tests. T_PMT_00
  // reads this to locate the live surface; T_PMT_01-03 never tap a coordinate
  // at all, they call `playerCycle`. Relocating the cycle to a different
  // surface should edit THIS STRING and T_PMT_00, and nothing else.
  //
  // History that makes the indirection worth its bytes: the binding moved from
  // the eject button to the taskbar player slot (TASK-413/414, ADR-059 D6) and
  // the move silently invalidated the test harness once and a design document
  // once. Both had hardcoded the old surface.
  if (strcmp(args, "playerBind") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"playerBind\","
                  "\"op\":\"playerCycle\",\"region\":\"TASKBAR_SLOT\","
                  "\"appId\":%d,\"helper\":\"resolvePlayerTap\","
                  "\"note\":\"cycle fires when the player slot is tapped while the player is active\","
                  "\"last\":true}\n", (int)AppId::Spotify);
    return;
  }
  if (strcmp(args, "playerMode") == 0) {   // TASK-260/413 (VE: agent-driven persist/settings tests)
    static const char* kPmNames[] = { "Spotify", "WebRadio", "Player" };
    uint8_t pm = g_settings.playerMode;   // true value — §6.1: no longer collapsed to a bool
    const char* name = (pm < 3) ? kPmNames[pm] : "unknown";
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"playerMode\","
                  "\"val\":%d,\"name\":\"%s\",\"last\":true}\n",
                  pm, name);
    return;
  }
  // ── TASK-415 / ADR-059 D12: LocalPlayer playlist observables ─────────────
  // These read the app instance directly, not currentAppId, so a test can
  // assert on a loaded playlist without the mode being on screen — same
  // always-reachable contract as `get wrStation`. The index is only allocated
  // while the mode is resumed, so the honest answer off-screen is count=0.
  if (strcmp(args, "plCount") == 0) { g_LocalPlayerApp.dbgReport(); return; }
  if (strcmp(args, "plMem")   == 0) { g_LocalPlayerApp.dbgMem();    return; }
  if (strncmp(args, "plRow", 5) == 0 && (args[5] == '\0' || args[5] == ' ')) {
    int idx = 0;
    if (sscanf(args + 5, "%d", &idx) != 1 || idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"get\",\"var\":\"plRow\","
                     "\"error\":\"usage: get plRow <idx>\"}");
      return;
    }
    g_LocalPlayerApp.dbgRow((uint16_t)idx);
    return;
  }
  // TASK-416 / ADR-059 D12: file browser observables — T_PLR_13-16 drive the
  // walk and navigation deterministically from here rather than only via taps.
  if (strcmp(args, "fbState") == 0) { g_LocalPlayerApp.dbgFbState(); return; }
  // TASK-418 / ADR-059 D12: the play-order engine's own observability —
  // T_PLR_20-24 exercise the shuffle bag, all four end-of-list cells and
  // prev-history without any real playback.
  if (strcmp(args, "plOrder")  == 0) { g_LocalPlayerApp.dbgOrder();  return; }
  if (strcmp(args, "plCursor") == 0) { g_LocalPlayerApp.dbgCursor(); return; }
  // OQ1 (design §11): the UTF-8 -> renderable-ASCII fold, testable without a
  // card. Everything a PLEDIT row can contain goes through this one helper.
  if (strncmp(args, "plFold", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *in = (args[6] == ' ') ? args + 7 : "";
    char out[96];
    textfold::foldUtf8(in, out, sizeof(out));
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plFold\","
                  "\"in\":\"%s\",\"out\":\"%s\",\"last\":true}\n", in, out);
    return;
  }
  if (strcmp(args, "kb") == 0) {
    // TASK-325 (M-SERIALDBG, VE-PRL-1 blocker): cheap KeyboardWidget state
    // dump for host assertions after kbText/kbOk/kbCancel — same diagnostic-
    // surface role as `get dataq` / `get wrStation` elsewhere.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"kb\","
                  "\"active\":%s,\"len\":%d,\"maxLen\":%d,\"mode\":%d,\"last\":true}\n",
                  g_keyboard.active() ? "true" : "false",
                  (int)g_keyboard.len(), (int)g_keyboard.maxLen(),
                  (int)g_keyboard.mode());
    return;
  }
  if (strcmp(args, "pick") == 0) {
    // M-COUNTRY-PICKER (CP-8): SPickerList observable — scroll offset +
    // highlighted index, so T-CPICK assertions aren't coordinate-guesswork
    // against a scroll-state-dependent list (same role as `get kb`).
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"pick\","
                  "\"active\":%s,\"offset\":%d,\"highlightIdx\":%d,\"last\":true}\n",
                  g_countryPicker.active() ? "true" : "false",
                  (int)g_countryPicker.dbgOffset(),
                  (int)g_countryPicker.dbgHighlight());
    return;
  }
  if (strcmp(args, "prloc") == 0) {
    // M-PR-LOCATIONS (TASK-319): per-slot dump + active index — the
    // diagnostic surface for every T_PRL test (same role `get wrStation` /
    // `get dataq` play elsewhere). No lastGeocode field: the geocode fetcher
    // is TASK-320, still unimplemented — a placeholder here would just be a
    // stub nobody can populate, so it's omitted rather than shipped half-wired.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"prloc\","
                  "\"active\":%d,\"locs\":[", (int)g_settings.prActiveLoc);
    for (int i = 0; i < PR_NUM_LOCS; i++) {
      Serial.printf("%s{\"i\":%d,\"label\":\"%s\",\"lat\":%.6f,\"lon\":%.6f}",
                    i ? "," : "", i, g_settings.prLocs[i].label,
                    g_settings.prLocs[i].lat, g_settings.prLocs[i].lon);
    }
    // M-HOME-LOCATION H-5: "home" = the home mirror (g_settings.lat/lon =
    // prLocs[0]) — otherwise unreadable from the harness; "divKm" = the
    // confirm-screen divergence observable (T-HOME-05), 0 when n/a.
    Serial.printf("],\"home\":{\"lat\":%.6f,\"lon\":%.6f},\"divKm\":%d,\"last\":true}\n",
                  g_settings.lat, g_settings.lon, g_SettingsApp.prDivKm());
    return;
  }
  if (strcmp(args, "geocode") == 0) {
    // TASK-320: non-consuming peek at the geocode slot (the editor is the
    // real pollGeocode() consumer — this must not steal its result).
    bool parked = false, hasNew = false;
    dataTask::GeocodeResult r;
    dataTask::dbgGeocodeState(&parked, &hasNew, &r);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"geocode\","
                  "\"parked\":%s,\"new\":%s,\"resOk\":%s,\"errorCode\":%d,"
                  "\"seq\":%u,\"lat\":%.6f,\"lon\":%.6f,\"display\":\"%s\",\"last\":true}\n",
                  parked ? "true" : "false", hasNew ? "true" : "false",
                  r.ok ? "true" : "false", r.errorCode,
                  (unsigned)r.seq, r.lat, r.lon, r.display);
    return;
  }
  // WIRE2 (§6d, W-7): shared G1+G2/G3 observable — the harness asserts the
  // formatted strings computed from getLocalTime + the timeFmt helpers (the
  // exact code path the renderers use), never scraped pixels. hour is emitted
  // as rendered (12h drops the leading zero); ampm is null in 24h mode.
  if (strcmp(args, "clockRender") == 0) {
    struct tm t;
    if (!getLocalTime(&t)) {
      Serial.println("{\"ok\":false,\"cmd\":\"get\",\"var\":\"clockRender\","
                     "\"error\":\"time not synced\"}");
      return;
    }
    char hBuf[4], dBuf[16];
    snprintf(hBuf, sizeof(hBuf), g_settings.fmt24h ? "%02d" : "%d", clockHour(t));
    fmtDate(t, dBuf, sizeof(dBuf), '/');
    const char* ap = clockAmPm(t);
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"clockRender\","
                  "\"hour\":\"%s\",\"min\":\"%02d\",\"ampm\":%s%s%s,"
                  "\"date\":\"%s\",\"fmt24h\":%s,\"dateFmt\":%d,\"last\":true}\n",
                  hBuf, t.tm_min,
                  ap ? "\"" : "", ap ? ap : "null", ap ? "\"" : "",
                  dBuf, g_settings.fmt24h ? "true" : "false",
                  (int)g_settings.dateFmt);
    return;
  }
  // WIRE2-G5 (§6 debug hooks, W-7): backlight owner observable — T-SETW-14
  // asserts the duty tracks injected LDR values outside the Settings screen.
  if (strcmp(args, "duty") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"duty\","
                  "\"duty\":%d,\"ldrRaw\":%d,\"auto\":%s,\"injected\":%s,"
                  "\"last\":true}\n",
                  g_backlight.currentDuty(), (int)g_backlight.ldrRaw(),
                  g_settings.dispAuto ? "true" : "false",
                  g_backlight.injected() ? "true" : "false");
    return;
  }
  // T-WRSET-04: completed-SPIFFS-write counter for SettingsStorage::save()
  // (see settingsStorage.cpp) — lets VE prove ADR-050 rule 3 coalesced-save
  // discipline (one save per suspend/eject) with a hard counter instead of
  // parsing "SettingsStorage: saved" log lines. Pair with `set settingsSave`
  // (WIRE2 §6 W-1) to force a save and confirm the counter advances by
  // exactly one.
  if (strcmp(args, "settingsSaveCount") == 0) {
    // TASK-429: the fail counters ride along on the existing var so a test can
    // assert "the save did not silently vanish" in one call.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"settingsSaveCount\","
                  "\"count\":%u,\"failAlloc\":%u,\"failOverflow\":%u,"
                  "\"failWrite\":%u,\"pending\":%s,\"last\":true}\n",
                  (unsigned)SettingsStorage::debugSaveCount(),
                  (unsigned)SettingsStorage::debugSaveFailAlloc(),
                  (unsigned)SettingsStorage::debugSaveFailOverflow(),
                  (unsigned)SettingsStorage::debugSaveFailWrite(),
                  SettingsStorage::savePending() ? "true" : "false");
    return;
  }
  Serial.printf("{\"ok\":false,\"cmd\":\"get\","
                "\"error\":\"unknown var\",\"var\":\"%s\"}\n", args);
}
#endif // SERIAL_DEBUG
