// debug/serialConsole/cmdSet.cpp — `set` — debug variable writes, out-of-line
// (M-SRCLAYOUT Stage E / TASK-471). Body compiles only under SERIAL_DEBUG;
// the .cpp itself is always compiled, same convention as appTable.cpp /
// cmdSystem.cpp / cmdMisc.cpp / cmdTouch.cpp / cmdGet.cpp.
#include "debug/serialConsole/cmdSet.h"
#include "debug/timeInject.h"             // dbgTimeSet/Thaw (ADR-064 D5)
#include "debug/armedInjectors.h"         // ARMED_INJECTORS_TABLE (TASK-635, M-HARNESS2 R14)

#ifdef SERIAL_DEBUG
#include <Arduino.h>
#include <string.h>
#include <ctype.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_heap_caps.h>
#include <esp_task_wdt.h>
#include "appShell.h"                     // AppId, currentAppId
#include "shell/appTable.h"               // g_apps[]/every g_XApp + *DbgSet(), pulls
                                           // webRadioApp.h/localPlayerApp.h and therefore
                                           // audio/audioEngine.h (mb_arena.h), player/
                                           // fileBrowser.h, settings/keyboardWidget.h
#include "dataTask.h"
#include "spotifyTask.h"
#include "wifiDiag.h"
#include "settingsStorage.h"              // g_settings, SettingsStorage, PR_NUM_LOCS
#include "spotifyDisplay.h"               // SpotifyDisplay
#include "logSink.h"                      // logsink namespace
#include "debug/bodWatch.h"               // bodWatchFault() (TASK-678 F-1)

extern SpotifyDisplay *spotifyDisplay;    // defined in main.cpp (build-variant display)
void prepareForReboot();                  // main.cpp — TASK-451: teardown + flush before a restart
void persistPlayerMode(uint8_t mode);     // main.cpp — TASK-260/M-PLAYER-STATE

// TASK-426 A/B: cookie-guarded RTC_NOINIT flag disabling the boot-candidate
// retry — see main.cpp's own copy of this comment for the full "why", and
// casRetryDisabled() there for the reader. This command only WRITES the two
// RTC_NOINIT words; they must stay the exact symbols main.cpp defines
// (RTC_NOINIT_ATTR globals are real storage, not textually-shared statics,
// once this became its own translation unit).
extern uint32_t g_casRetryCookie;
extern uint32_t g_casRetryOff;
static constexpr uint32_t kCasRetryCookie = 0x426AB1FEu;

// TASK-635 (M-HARNESS2 R14 / armedInjectors.h): the one new byte of state
// this task adds. mb_arena_active() is also true during real playback, so
// it can't be the `arenaHold` armed predicate on its own — this flag marks
// only "the console asked for the hold", set/cleared by `set arenaHold`
// below and read by armedInjectors.h from both cmdGet.cpp and cmdSet.cpp.
bool s_consoleArenaHold = false;

void cmdSet(const char *args) {
  char var[32], val[128];  // val widened to 128 to accommodate wrUrl (104-byte station URLs)

  // TASK-325 (M-SERIALDBG, VE-PRL-1 blocker): KeyboardWidget injection.
  // kbText carries the full remaining string verbatim (UK postcodes etc.
  // contain spaces) and kbOk/kbCancel take no value at all — neither fits
  // the generic single var/val split below, so both are special-cased
  // against the raw `args` first (same drain-all-bytes-at-once lesson as
  // the "set prloc" reparse below: don't assume a fixed token count).
  // Injection/commit/cancel route through KeyboardWidget's own
  // injectText()/commitFromHost()/cancelFromHost() — same callbacks, same
  // cleanup as a real tap (BP-047/LL-110: no duplicated logic here).
  if (strncmp(args, "kbText", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *text = (args[6] == ' ') ? args + 7 : "";
    if (!g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbText\","
                      "\"error\":\"no active keyboard\"}");
      return;
    }
    g_keyboard.injectText(text);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbText\","
                  "\"len\":%d,\"maxLen\":%d}\n",
                  (int)g_keyboard.len(), (int)g_keyboard.maxLen());
    return;
  }
  if (strcmp(args, "kbOk") == 0) {
    if (!g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbOk\","
                      "\"error\":\"no active keyboard\"}");
      return;
    }
    bool wasEmpty = (g_keyboard.len() == 0);  // OK is disabled/no-op when empty on-screen too
    g_keyboard.commitFromHost();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbOk\",\"submitted\":%s}\n",
                  wasEmpty ? "false" : "true");
    return;
  }
  if (strcmp(args, "kbCancel") == 0) {
    if (!g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbCancel\","
                      "\"error\":\"no active keyboard\"}");
      return;
    }
    g_keyboard.cancelFromHost();
    Serial.println("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbCancel\"}");
    return;
  }
  // TASK-320 (VE-PRL-2): park a synthetic geocode result for the NEXT
  // pollGeocode(). Two forms, both multi-token (raw-args parse like prloc):
  //   set geocode <lat> <lon> [display text…]   — success result
  //   set geocode err <code>                    — failure result (e.g. -96)
  // Structural isolation lives in dataTask (parked slot checked before the
  // real one; enqueueGeocode() no-ops while parked) — this command only
  // builds the result. seq is stamped by debugInjectGeocode() itself.
  if (strncmp(args, "geocode ", 8) == 0) {
    const char* rest = args + 8;
    dataTask::GeocodeResult r;
    // Third form (DUT smoke / T_PRL_01b): `set geocode fetch <CC> <postcode…>`
    // triggers a REAL enqueueGeocode() — the editor (TASK-321) doesn't exist
    // yet, so this is the only on-device path to exercise the live fetcher
    // (UA/TLS/parse). Postcode = remainder verbatim (may contain a space).
    // Checked before the lat/lon form ("fetch" would otherwise parse as a
    // 0.0-lat injection). Result observable via `get geocode` (new=true).
    if (strncmp(rest, "fetch ", 6) == 0) {
      char cc[4]; int consumed = 0;
      if (sscanf(rest + 6, "%3s %n", cc, &consumed) < 1 || rest[6 + consumed] == '\0') {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"usage: geocode fetch <CC> <postcode>\"}");
        return;
      }
      uint8_t seq = dataTask::enqueueGeocode(cc, rest + 6 + consumed);
      Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"geocode\","
                    "\"fetch\":true,\"seq\":%u}\n", (unsigned)seq);
      return;
    }
    if (strncmp(rest, "err ", 4) == 0) {
      r.ok = false;
      r.errorCode = atoi(rest + 4);
      if (r.errorCode == 0) {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"err needs nonzero code\"}");
        return;
      }
    } else {
      char latBuf[16], lonBuf[16]; int consumed = 0;
      if (sscanf(rest, "%15s %15s %n", latBuf, lonBuf, &consumed) < 2) {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"usage: geocode <lat> <lon> [display] | geocode err <code>\"}");
        return;
      }
      r.ok  = true;
      r.lat = atof(latBuf);
      r.lon = atof(lonBuf);
      if (r.lat < -90.0f || r.lat > 90.0f || r.lon < -180.0f || r.lon > 180.0f) {
        Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"geocode\","
                        "\"error\":\"lat/lon out of range\"}");
        return;
      }
      strlcpy(r.display, rest + consumed, sizeof(r.display));  // may be empty
    }
    dataTask::debugInjectGeocode(r);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"geocode\","
                  "\"parked\":true,\"resOk\":%s,\"errorCode\":%d}\n",
                  r.ok ? "true" : "false", r.errorCode);
    return;
  }
  // TASK-325 smoke helper: open the keyboard directly (no touch navigation
  // needed) so kbText/kbOk/kbCancel are DUT-testable standalone. Submitted/
  // cancelled text is echoed as JSON for host asserts.
  //   set kbShow [maxLen] [mode]   (mode 0=Full 1=UpperAlpha; defaults 10, 0)
  if (strncmp(args, "kbShow", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    int maxLen = 10, mode = 0;
    sscanf(args + 6, "%d %d", &maxLen, &mode);
    if (g_keyboard.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"kbShow\","
                      "\"error\":\"keyboard already active\"}");
      return;
    }
    g_keyboard.show("dbg kbShow", "",
                    mode == 1 ? KeyboardWidget::Mode::UpperAlpha : KeyboardWidget::Mode::Full,
                    (uint8_t)maxLen,
                    [](const char* text, void*) {
                      Serial.printf("{\"evt\":\"kbSubmit\",\"text\":\"%s\"}\n", text);
                    },
                    [](void*) { Serial.println("{\"evt\":\"kbCancel\"}"); },
                    nullptr);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"kbShow\","
                  "\"maxLen\":%d,\"mode\":%d}\n", maxLen, mode);
    return;
  }

  // TASK-410 (T_AE_07/09/10): drive the audio engine's FILE arm directly — no
  // LocalPlayer app yet (TASK-413+), so this is the only entry point. Global
  // (engine-level, not per-app dbgSet), like wifiKick/wifiDisc. Special-cased
  // against raw args, same as kbText above: real filenames on this card carry
  // spaces ("01 - Tomorrow Comes Today.mp3"), which the %127s split below
  // would truncate at the first one. A bare `set aePlayFile` (no path) falls
  // back to the hardcoded default path the gate uses.
  if (strncmp(args, "aePlayFile", 10) == 0 && (args[10] == '\0' || args[10] == ' ')) {
    const char* path = (args[10] == ' ' && args[11] != '\0') ? args + 11 : "/test.mp3";
    bool posted = aeConnectFile(path);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"aePlayFile\",\"path\":\"%s\"}\n",
                  posted ? "true" : "false", path);
    return;
  }
  // TASK-415: load an M3U into the Player mode's index. Special-cased against
  // raw args for the same reason `set aePlayFile` is — real paths on this card
  // carry spaces, which the %127s split below truncates at the first one.
  // Persists as the last playlist, so a reboot into Player mode reopens it.
  // ADR-064 D5 (TASK-638): `set now <epoch> [freeze]` | `set now thaw`.
  // Raw-args special case: the optional word does not fit the var/val split.
  if (strncmp(args, "now", 3) == 0 && (args[3] == '\0' || args[3] == ' ')) {
    const char *rest = args + 3;
    while (*rest == ' ') rest++;
    if (strcmp(rest, "thaw") == 0) {
      dbgTimeThaw();
      Serial.println("{\"ok\":true,\"cmd\":\"set\",\"var\":\"now\",\"frozen\":false}");
      return;
    }
    long epoch = 0; char word[8] = {0};
    const int n = sscanf(rest, "%ld %7s", &epoch, word);
    if (n < 1 || epoch < 1600000000L) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"now\","
                     "\"error\":\"usage: set now <epoch>=1600000000 [freeze] | set now thaw\"}");
      return;
    }
    const bool freeze = (n == 2 && strcmp(word, "freeze") == 0);
    dbgTimeSet((time_t)epoch, freeze);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"now\",\"epoch\":%ld,\"frozen\":%s}\n",
                  epoch, freeze ? "true" : "false");
    return;
  }
  if (strncmp(args, "plLoad", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *path = (args[6] == ' ' && args[7] != '\0') ? args + 7 : "";
    if (!*path) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"plLoad\","
                     "\"error\":\"usage: set plLoad <path>\"}");
      return;
    }
    const bool ok = g_LocalPlayerApp.dbgLoad(path);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"plLoad\",\"path\":\"%s\"}\n",
                  ok ? "true" : "false", path);
    return;
  }
  // TASK-415: play a row by index — tap-to-play without needing the row's
  // screen coordinates (which depend on the live scroll offset).
  if (strncmp(args, "plPlay", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    int idx = -1;
    if (sscanf(args + 6, "%d", &idx) != 1 || idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"plPlay\","
                     "\"error\":\"usage: set plPlay <idx>\"}");
      return;
    }
    const bool ok = g_LocalPlayerApp.dbgPlayRow((uint16_t)idx);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"plPlay\",\"idx\":%d}\n",
                  ok ? "true" : "false", idx);
    return;
  }
  // TASK-442: lower/disable the I2S DMA floor so the "is the floor too strict
  // on this variant?" A/B can be run on hardware. 0 disables the check.
  if (strncmp(args, "aeDmaFloor", 10) == 0 && (args[10] == '\0' || args[10] == ' ')) {
    int v = -1;
    if (sscanf(args + 10, "%d", &v) != 1 || v < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"aeDmaFloor\","
                     "\"error\":\"usage: set aeDmaFloor <bytes|0>\"}");
      return;
    }
    s_aeDmaFloorOverride = (size_t)v;
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"aeDmaFloor\",\"val\":%u}\n",
                  (unsigned)s_aeDmaFloorOverride);
    return;
  }
  // TASK-444 gate: reproduce a stale arena free on demand. The natural trigger
  // needs the two engine arms to alternate with a teardown in between, which no
  // test in this repo does (and T_AE_15, which would, is blocked). This runs the
  // exact sequence in four lines instead: take the arena, allocate from it,
  // release it, then free the pointer. Before PATCH-ARENA-STALE-1 that last step
  // called libc free() on memory heap_caps_free() had already returned.
  // NOTE: invoke as `set arenaStaleFree` with NO value. cmdSet routes a
  // two-token "set <var> <val>" through the var-based dispatch further down,
  // which does not know this name and answers "unknown var" — measured, not
  // guessed (2026-08-15: the no-value form fired the refusal, the "1" form did
  // not). The command takes no argument anyway; it is a fixed four-step probe.
  if (strncmp(args, "arenaStaleFree", 14) == 0 &&
      (args[14] == '\0' || args[14] == ' ')) {
#ifdef MEMBUDGET_PHASE1
    const uint32_t before = mb_arena_stale_free_total();
    if (!mb_arena_acquire()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"arenaStaleFree\","
                     "\"error\":\"arena would not acquire\"}");
      return;
    }
    void* p = mb_arena_alloc(128);
    mb_arena_release();
    mb_arena_free(p);          // the stale free — must be REFUSED, not passed to libc
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"arenaStaleFree\","
                  "\"ptr\":\"%p\",\"staleBefore\":%u,\"staleAfter\":%u,\"alive\":true}\n",
                  p, (unsigned)before, (unsigned)mb_arena_stale_free_total());
#else
    Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"arenaStaleFree\","
                   "\"error\":\"MEMBUDGET_PHASE1 not built\"}");
#endif
    return;
  }
  // TASK-443: run the FILE path WITHOUT the arena, to measure the ruling before
  // accepting it. `set aeNoArena 1` then `set plPlay <n>`.
  if (strncmp(args, "aeNoArena", 9) == 0 && (args[9] == '\0' || args[9] == ' ')) {
    int v = 1;
    sscanf(args + 9, "%d", &v);
    s_aeNoArenaInject = (v != 0);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"aeNoArena\",\"val\":%d}\n",
                  s_aeNoArenaInject ? 1 : 0);
    return;
  }
  // TASK-432: fault-inject a failed Audio allocation so the degrade path can
  // be gated deterministically. With this set, the next play attempt (FILE or
  // WebRadio) must render "play FAILED" / ERROR_UNREACHABLE and leave the
  // shell alive — no abort(), no reset.
  if (strncmp(args, "aeFailAudio", 11) == 0 && (args[11] == '\0' || args[11] == ' ')) {
    int v = 1;
    sscanf(args + 11, "%d", &v);
    s_aeFailAudioInject = (v != 0);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"aeFailAudio\",\"val\":%d}\n",
                  s_aeFailAudioInject ? 1 : 0);
    return;
  }
  // TASK-418 / ADR-059 D12: sets the play-order cursor directly, in
  // whichever domain is active (view row / bag position), WITHOUT decoding
  // audio — T_PLR_21/22 force the end-of-list cells and wrap collisions by
  // jumping straight to the last position rather than playing there.
  if (strncmp(args, "plCursor", 8) == 0 && (args[8] == '\0' || args[8] == ' ')) {
    int n = -1;
    if (sscanf(args + 8, "%d", &n) != 1) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"plCursor\","
                     "\"error\":\"usage: set plCursor <n>\"}");
      return;
    }
    const bool ok = g_LocalPlayerApp.dbgSetCursor(n);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"plCursor\",\"n\":%d}\n",
                  ok ? "true" : "false", n);
    return;
  }
  // TASK-416 (T_PLR_13-16): open a directory in the file browser without a
  // tap — real card paths carry spaces, same raw-args shape as plLoad above.
  if (strncmp(args, "fbOpen", 6) == 0 && (args[6] == '\0' || args[6] == ' ')) {
    const char *path = (args[6] == ' ' && args[7] != '\0') ? args + 7 : "/";
    const bool ok = g_LocalPlayerApp.dbgFbOpen(path);
    // TASK-521: carry the REASON, and emit it without Print::printf's malloc.
    // The reason matters because every failure used to look identical from the
    // harness (test_fbrowser_player.py read a bare ok:false as "fixture
    // missing?" — it never was); the malloc matters because the dominant
    // reason is `nomem`, and Print::printf() silently returns 0 when its own
    // >64 B buffer cannot be allocated, i.e. it drops the reply exactly when
    // there is something to say.
    {
        char b[192];
        int n = snprintf(b, sizeof(b),
                         "{\"ok\":%s,\"cmd\":\"set\",\"var\":\"fbOpen\",\"path\":\"%s\","
                         "\"reason\":\"%s\",\"free8\":%u,\"largest8\":%u}\n",
                         ok ? "true" : "false", path,
                         player::FileBrowser::errName(g_LocalPlayerApp.dbgFbLastError()),
                         (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                         (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL |
                                                                    MALLOC_CAP_8BIT));
        if (n > 0) Serial.write((const uint8_t*)b, (n < (int)sizeof(b)) ? n : sizeof(b) - 1);
    }
    return;
  }
  // TASK-416: select a browser row by index (descend / play / load) exactly
  // as if it were tapped — screen coordinates depend on the live scroll offset.
  if (strncmp(args, "fbSelect", 8) == 0 && (args[8] == '\0' || args[8] == ' ')) {
    int idx = -1;
    if (sscanf(args + 8, "%d", &idx) != 1 || idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"fbSelect\","
                     "\"error\":\"usage: set fbSelect <idx>\"}");
      return;
    }
    const bool ok = g_LocalPlayerApp.dbgFbSelect((int16_t)idx);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"fbSelect\",\"idx\":%d}\n",
                  ok ? "true" : "false", idx);
    return;
  }
  // TASK-416 (T_PLR_14): the browser's back/up affordance — the isNavigationTap
  // regression this exercises is about the REAL tap path, not this debug
  // shortcut, but this is what T_PLR_13/15/16 use to drive ascend/close.
  if (strcmp(args, "fbCancel") == 0) {
    const bool ok = g_LocalPlayerApp.dbgFbCancel();
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"fbCancel\"}\n", ok ? "true" : "false");
    return;
  }
  // TASK-678 (F-1): `set fault bod <level>` — invokes bodWatch's real event-
  // capture path with a synthetic reading, so the R34 runtime gate
  // (check_can_go_red.py) can prove the harness parses `[bod] TRIP`/`get bod`
  // without a real supply sag. Raw-args special case (two sub-tokens), same
  // idiom as `geocode`/`kbShow` above — the generic var/val split below only
  // takes one token each.
  if (strncmp(args, "fault ", 6) == 0) {
    const char *rest = args + 6;
    if (strncmp(rest, "bod ", 4) == 0) {
      int level = -1;
      if (sscanf(rest + 4, "%d", &level) == 1 && level >= 0 && level <= 7) {
        bodWatchFault((uint8_t)level);
        return;
      }
    }
    Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"fault\","
                    "\"error\":\"usage: fault bod <0..7>\"}");
    return;
  }
  // TASK-678 (F-2): `set scanLoop <seconds>` — provoke the NO_AP_FOUND retry
  // loop non-persistently (PROP-011-runbook.md §1 F-2). Bounded 5-300s, TWDT
  // fed, never touches NVS (TASK-426's wedge is exactly a stale NVS write),
  // restores the saved SSID on exit.
  if (strncmp(args, "scanLoop", 8) == 0 && (args[8] == '\0' || args[8] == ' ')) {
    int secs = -1;
    sscanf(args + 8, "%d", &secs);
    if (secs < 5 || secs > 300) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"scanLoop\","
                      "\"error\":\"usage: scanLoop <seconds 5..300>\"}");
      return;
    }
    wifi_config_t saved = {};
    esp_wifi_get_config(WIFI_IF_STA, &saved);
    char savedSsid[33];
    strlcpy(savedSsid, (const char*)saved.sta.ssid, sizeof(savedSsid));

    // NEVER write NVS — TASK-426's wedge is exactly a stale SSID in flash.
    // WiFi.persistent(false) is NOT enough here: Arduino-ESP32 applies it only
    // inside wifiLowLevelInit() (WiFiGeneric.cpp:694), which ran at boot with
    // persistent(true), so the driver's storage is FLASH until told otherwise.
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    WiFi.disconnect(false, false);
    char bogus[40];
    snprintf(bogus, sizeof(bogus), "PROP011-no-such-ap-%lu", (unsigned long)millis());
    WiFi.begin((const char*)bogus, (const char*)"x");   // auto-reconnect stays ON: IDF's own retry loop is the point

    // This command blocks loop() for its whole duration, so bodWatchTick()
    // cannot re-arm the ISR after its first event — the first DUT run read
    // `disarmed:true` and "1 trip in 30 s" was the instrument going blind,
    // not the rail. Poll/re-arm here, the way serialburst does, and report
    // the trips so X-P1c is one JSON line. discCount is the real reason=201
    // event counter (rate-limited [wifi-ev] lines are not); r201 stays as
    // the 100 ms-poll approximation of time spent with no AP.
    uint32_t r201 = 0, bodTrips = 0;
    const uint32_t disc0 = wifiDiag::discCount;
    const unsigned long t0 = millis();
    const unsigned long deadline = t0 + (unsigned long)secs * 1000UL;
    while (millis() < deadline) {
      if (WiFi.status() == WL_NO_SSID_AVAIL) r201++;
      if (bodWatchPollQuiet()) bodTrips++;
      delay(100);
      esp_task_wdt_reset();
    }
    const uint32_t discDelta = wifiDiag::discCount - disc0;

    WiFi.disconnect(false, false);
    delay(100);
    // The driver's RAM config is now the bogus SSID; a bare begin() would
    // reconnect to THAT. Put the saved config back first (storage is still
    // RAM, so this does not touch NVS either), then restore FLASH storage so
    // a later Settings-UI connect persists as it always did.
    esp_wifi_set_config(WIFI_IF_STA, &saved);
    WiFi.begin();
    esp_wifi_set_storage(WIFI_STORAGE_FLASH);
    uint32_t t1 = millis();
    while (millis() - t1 < 20000 && WiFi.status() != WL_CONNECTED) {
      delay(200);
      esp_task_wdt_reset();
    }
    const bool reconnected = (WiFi.status() == WL_CONNECTED);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"scanLoop\",\"secs\":%d,"
                  "\"r201\":%lu,\"disc\":%lu,\"bodTrips\":%lu,\"reconnected\":%d,"
                  "\"savedSsid\":\"%s\"}\n",
                  secs, (unsigned long)r201, (unsigned long)discDelta,
                  (unsigned long)bodTrips, reconnected ? 1 : 0, savedSsid);
    return;
  }
  if (sscanf(args, "%31s %127s", var, val) != 2) {
    Serial.println("{\"ok\":false,\"cmd\":\"set\",\"error\":\"bad args\"}");
    return;
  }
  // M-COUNTRY-PICKER (CP-4): `set pick <CC>` selects on the ACTIVE SPickerList
  // by ISO code — fires onSelect exactly like a row tap (same callback, same
  // hide/cleanup; the kbText/kbOk submit-equivalent idiom). Errors when no
  // picker is active or the code isn't in the table.
  if (strcmp(var, "pick") == 0) {
    if (!g_countryPicker.active()) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"pick\","
                      "\"error\":\"no active picker\"}");
      return;
    }
    if (g_countryPicker.pickByCode(val)) {
      Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"pick\","
                    "\"code\":\"%s\"}\n", val);
    } else {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"pick\","
                    "\"error\":\"unknown code\",\"code\":\"%s\"}\n", val);
    }
    return;
  }
  // TASK-425: standalone decoder-arena hold, independent of any stream. Lets the
  // arena-first SD/arena memory table be re-measured without dragging in WebRadio's
  // ~40 KB TLS fetch (mb_arena_acquire()/release() are the same calls WebRadioApp::
  // _play()/suspend() make — no duplicated logic, just called directly). No new
  // static state here: mb_arena.cpp already owns its own statics, this command only
  // calls through and reports heap. `set arenaHold 1` acquires (idempotent — a
  // second call while held is a no-op, same as production), `set arenaHold 0`
  // releases. Reports free heap + largest free (INTERNAL|8BIT, the byte-addressable
  // number that actually gates SD.begin()) so the caller can diff before/after
  // against a clean heap.
  if (strcmp(var, "arenaHold") == 0) {
    const uint32_t kByteCap = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    bool want = (atoi(val) != 0);
    bool ok;
    if (want) {
      ok = mb_arena_acquire();
      if (ok) s_consoleArenaHold = true;   // TASK-635: armed via the console, not real playback
    } else {
      mb_arena_release();
      ok = true;
      s_consoleArenaHold = false;
    }
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"arenaHold\",\"held\":%s,"
                  "\"freeInt\":%u,\"lfbInt\":%u,\"free8\":%u,\"lfb8\":%u}\n",
                  ok ? "true" : "false", mb_arena_active() ? "true" : "false",
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_free_size(kByteCap),
                  (unsigned)heap_caps_get_largest_free_block(kByteCap));
    return;
  }
  // TASK-635 (M-HARNESS2 R14): clear every currently-armed injector in
  // armedInjectors.h's table (table order), so a leak caught at a test
  // boundary does not also spoil the id that runs next. Each clearStmt
  // only runs for a member whose armedExpr was true, so this never
  // clobbers a real app's own in-flight state (e.g. a real WebRadio
  // station list) that happens to share a variable name.
  if (strcmp(var, "injclear") == 0) {
    char names[256]; names[0] = '\0';
    int n = 0, off = 0;
#define X(name, armedExpr, clearStmt)                                        \
    if (armedExpr) {                                                         \
      clearStmt;                                                             \
      off += snprintf(names + off, sizeof(names) - off, "%s\"%s\"",          \
                       n ? "," : "", #name);                                 \
      n++;                                                                   \
    }
    ARMED_INJECTORS_TABLE(X)
#undef X
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"injclear\",\"n\":%d,"
                  "\"cleared\":[%s]}\n", n, names);
    return;
  }
  // TASK-248: runtime log-volume control (for stress soaks). `set logLevel <d|i|w|e>`
  // sets the min severity emitted by LOG_x; `set logKeep <prefix>` always keeps tags
  // matching the prefix regardless of level (e.g. logKeep dataTask). `set logKeep -`
  // clears the keep filter.
  if (strcmp(var, "logLevel") == 0) {
    logsink::logMinLevel() = logsink::logRank(toupper((unsigned char)val[0]));
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"logLevel\",\"val\":\"%s\"}\n", val);
    return;
  }
  if (strcmp(var, "logKeep") == 0) {
    strlcpy(logsink::logKeepPrefix(), (val[0] == '-') ? "" : val, 24);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"logKeep\",\"val\":\"%s\"}\n", val);
    return;
  }
  // TASK-282 (M-WIFI-DIAG Phase 2): modem power-save A/B. Beacon timeouts are
  // classically DTIM/modem-sleep interactions (TASK-272 implicates PS; the
  // "ping keepalive masks flapping" observation is a PS signature). 0 = PS off.
  if (strcmp(var, "wifiPs") == 0) {
    bool on = (val[0] == '1');
    esp_err_t e = esp_wifi_set_ps(on ? WIFI_PS_MIN_MODEM : WIFI_PS_NONE);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"wifiPs\",\"val\":%d}\n",
                  e == ESP_OK ? "true" : "false", on ? 1 : 0);
    return;
  }
  // TASK-282: beacon watcher on/off (needs associated STA to lock BSSID).
  if (strcmp(var, "beaconWatch") == 0) {
    bool ok = (val[0] == '1') ? wifiDiag::beaconWatchStart()
                              : (wifiDiag::beaconWatchStop(), true);
    Serial.printf("{\"ok\":%s,\"cmd\":\"set\",\"var\":\"beaconWatch\",\"val\":%c}\n",
                  ok ? "true" : "false", val[0]);
    return;
  }
  // TASK-282: async scan kick — poll result via `get wifiScan` (scan-on-park
  // evidence: is the BSSID on the air when NO_AP_FOUND says it isn't?).
  // TASK-473 (G1, M-CONCURRENCY §5): this was the one radio-mutating call
  // site that never got TASK-436's point fix — esp_wifi_scan_start() is
  // refused outright while auto-reconnect's esp_wifi_connect() loop has an
  // attempt in flight, same collision wifiSection.h::_startScan() guards
  // against. Silence auto-reconnect for the duration of the scan; the
  // matching get-side re-arm sits in cmdGet.cpp's wifiScan handler, at the
  // point the scan is observed to have actually finished (async — this call
  // site cannot know that synchronously).
  if (strcmp(var, "wifiScan") == 0) {
    WiFi.setAutoReconnect(false);
    WiFi.scanNetworks(/*async=*/true);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"wifiScan\",\"val\":1}\n");
    return;
  }
  // TASK-426 A/B: software reset. An EN-pin/RTS reset clears the RTC domain, so
  // the casRetry flag below arrives as garbage and BOTH arms silently run the
  // control — which is exactly what happened on the first attempt at this A/B.
  // ESP.restart() is a software reset and preserves RTC memory, so the arm
  // selection actually reaches setup().
  if (strcmp(var, "reboot") == 0) {
    // TASK-429/451: land any deferred settings write before the reset. A save
    // that failed to allocate (audio arena up) is retried at engine teardown or
    // on the loop() tick — neither of which happens if the user reboots first,
    // so the write was silently lost across an INTENTIONAL restart. DUT-measured
    // 2026-08-15 (T_PRM_01's exact signature): `set prPollSec 30` during
    // playback -> failAlloc:1, pending:true -> reboot -> the value reads 10
    // again. force=true skips the retry interval; a crash reset still loses it,
    // which is accepted — this covers the paths we control.
    prepareForReboot();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"reboot\"}\n");
    Serial.flush();
    delay(50);
    ESP.restart();
    return;
  }
  // TASK-426 A/B: `set casRetry 0` disables the per-candidate retry for the
  // NEXT boot (survives a software reset in RTC memory), `1` re-enables it.
  if (strcmp(var, "casRetry") == 0) {
    g_casRetryCookie = kCasRetryCookie;
    g_casRetryOff    = (val[0] == '0') ? 1u : 0u;
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"casRetry\",\"disabled\":%u}\n",
                  (unsigned)g_casRetryOff);
    return;
  }
  // TASK-426 repro hook: commit an arbitrary SSID to NVS so the stale-NVS
  // precondition can be recreated on demand. Without this the bug is only
  // reachable by renaming a real AP out from under a device that had already
  // associated with the old name — which is how it was found, and is not a
  // regression test anyone can re-run. Pair with a saved list holding the LIVE
  // SSID, then reset: the boot NVS stage burns its window on the dead SSID and
  // the cascade behind it must still connect.
  if (strcmp(var, "nvsSsid") == 0) {
    WiFi.persistent(true);          // FLASH storage — this is the point
    WiFi.mode(WIFI_STA);
    // Both args cast: mixing `char[]` with a string literal makes the
    // begin(char*,char*) / begin(const char*,const char*) pair ambiguous.
    WiFi.begin((const char*)val, (const char*)"notarealpassword");
    delay(100);
    WiFi.disconnect(false);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"nvsSsid\",\"val\":\"%s\"}\n", val);
    return;
  }
  // TASK-426: quiesced connect — the control for a NO_AP_FOUND wedge. While
  // wedged, autoreconnect re-fires esp_wifi_connect() every ~2.4s and the
  // supervisor kicks every 30s, so any connect under test is contended. This
  // silences both, waits for in-flight attempts to drain, then does exactly ONE
  // begin() and reports what it actually did — separating "connect genuinely
  // cannot find this AP" from "connect never got a clean run".
  if (strcmp(var, "wifiKick") == 0) {
    wifi_config_t c = {};
    esp_wifi_get_config(WIFI_IF_STA, &c);
    Serial.printf("[wifiKick] quiescing; ssid=\"%s\"\n", (const char*)c.sta.ssid);
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false, false);
    // TASK-288 discipline: every bounded wait in this file feeds the TWDT.
    // Without it this command's own waits panic-reset the board mid-diagnosis
    // (observed on the first TASK-426 build — the reset looked like a wedge
    // recovery and nearly cost a false conclusion).
    { unsigned long dl = millis() + 1500;      // let in-flight attempts drain
      while (millis() < dl) { delay(100); esp_task_wdt_reset(); } }
    Serial.printf("[wifiKick] armed, single begin()\n");
    WiFi.begin();
    uint32_t t0 = millis();
    wl_status_t st = WL_DISCONNECTED;
    while (millis() - t0 < 20000) {
      st = (wl_status_t)WiFi.status();
      if (st == WL_CONNECTED) break;
      delay(250); esp_task_wdt_reset();
    }
    Serial.printf("[wifiKick] result status=%d elapsed=%lums ip=%s rssi=%d\n",
                  (int)st, (unsigned long)(millis() - t0),
                  WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
    WiFi.setAutoReconnect(true);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"wifiKick\",\"status\":%d}\n", (int)st);
    return;
  }
  // TASK-274 (QM-2 positive control): force a disconnect so the [wifi-ev]
  // sensor can be proven live before attribution-by-absence is trusted.
  // Expect a STA_DISCONNECTED line (reason=8 ASSOC_LEAVE) then auto-reconnect.
  if (strcmp(var, "wifiDisc") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"wifiDisc\",\"val\":\"%s\"}\n", val);
    WiFi.disconnect();
    delay(200);
    WiFi.begin();   // reconnect from NVS creds
    return;
  }
  // TASK-344 (M-CERT-ERRCODE): `set certbreak <app>` arms a one-shot wrong-
  // root-CA swap for the named fetcher's next attempt (T_CERT_ERR_01). Global
  // (cross-app) like logLevel/wifiPs above, not per-app dbgSet — certbreak
  // targets a dataTask::FetchType, not any one App's own state.
  if (strcmp(var, "certbreak") == 0) {
    static const struct { const char* name; dataTask::FetchType type; } kCertBreakApps[] = {
        {"weather",       dataTask::DATA_FETCH_WEATHER},
        {"crypto",        dataTask::DATA_FETCH_CRYPTO},
        {"stockquote",    dataTask::DATA_FETCH_STOCK_QUOTE},
        {"stockchart",    dataTask::DATA_FETCH_STOCK_CHART},
        {"heatmap",       dataTask::DATA_FETCH_HEATMAP_QUOTE},
        {"stockchartsym", dataTask::DATA_FETCH_STOCK_CHART_BY_SYM},
        {"teletext",      dataTask::DATA_FETCH_TELETEXT_PAGE},
        {"webradio",      dataTask::DATA_FETCH_WEBRADIO_STATIONS},
        {"planeradar",    dataTask::DATA_FETCH_PLANERADAR},
        {"geocode",       dataTask::DATA_FETCH_GEOCODE},
    };
    for (const auto& a : kCertBreakApps) {
      if (strcmp(val, a.name) == 0) {
        dataTask::debugBreakCert(a.type);
        Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"certbreak\",\"app\":\"%s\"}\n", val);
        return;
      }
    }
    Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"certbreak\","
                  "\"error\":\"unknown app\",\"app\":\"%s\"}\n", val);
    return;
  }
  if ((spotifyDisplay && spotifyDisplay->dbgSet(var, val))
      || spotifyTask::dbg_set(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  if (stockDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  if (teletextDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  if (planeRadarDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  // TASK-501: WINAMP_DISPLAY is unconditionally defined — no #ifdef needed.
  if (webRadioDbgSet(var, val)) {
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"%s\",\"val\":\"%s\"}\n", var, val);
    return;
  }
  // WIRE2 (§6 debug hooks, W-1): force a save — T-SETW-01/02's load→RAM→save
  // leg; nothing saves at boot, so without this a spiffs pull returns the
  // pushed bytes verbatim and proves nothing. Value is ignored ("set
  // settingsSave 1" per house two-token syntax).
  if (strcmp(var, "settingsSave") == 0) {
    // TASK-429: report what actually happened. This printed "saved":true
    // unconditionally while discarding save()'s bool, so a save aborted by the
    // alloc failure (DUT-observed 2026-08-15: `failAlloc:2` while this reply
    // still said true) reads as success to any harness asserting on it. Only
    // `get settingsSaveCount` told the truth.
    const bool saved = SettingsStorage::save();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"settingsSave\",\"saved\":%s}\n",
                  saved ? "true" : "false");
    return;
  }
  // WIRE2-G5 (§4-G5, W-7): sticky LDR override for T-SETW-14 — the harness
  // cannot darken the room. -1 clears; while set, BacklightFlow samples the
  // injected value instead of the ADC.
  if (strcmp(var, "ldrRaw") == 0) {
    int v = atoi(val);
    if (v < -1 || v > 4095) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"ldrRaw\","
                     "\"error\":\"range -1..4095 (-1 clears)\"}");
      return;
    }
    g_backlight.injectLdr((int16_t)v);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"ldrRaw\",\"val\":%d}\n", v);
    return;
  }
  // WIRE2-G2 (§6 debug hooks, W-7): 12h/24h toggle. Mirrors clockStyle below,
  // incl. the resume-if-current-app repaint trick for Clock.
  if (strcmp(var, "fmt24h") == 0) {
    if (val[1] != '\0' || (val[0] != '0' && val[0] != '1')) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"fmt24h\","
                     "\"error\":\"bad val — use 0|1\"}");
      return;
    }
    g_settings.fmt24h = (val[0] == '1');
    // TASK-429: `saved` distinguishes "the value is live in RAM" (always true
    // here) from "it will survive a reboot" (false when the save aborted).
    const bool saved = SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"fmt24h\",\"val\":%d,\"saved\":%s}\n",
                  g_settings.fmt24h ? 1 : 0, saved ? "true" : "false");
    return;
  }
  // WIRE2-G3 (§6 debug hooks, W-7): date format. 0-2 or dmy/mdy/ymd.
  if (strcmp(var, "dateFmt") == 0) {
    static const char* kDF[] = {"dmy", "mdy", "ymd"};
    int idx = -1;
    for (int i = 0; i < 3; i++) if (strcasecmp(val, kDF[i]) == 0) { idx = i; break; }
    if (idx < 0) { if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 2) idx = -1; }
    if (idx < 0) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"dateFmt\","
                     "\"error\":\"bad val — use 0-2 or dmy/mdy/ymd\"}");
      return;
    }
    g_settings.dateFmt = (DateFmt)idx;
    SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"dateFmt\",\"val\":%d,"
                  "\"name\":\"%s\"}\n", idx, kDF[idx]);
    return;
  }
  if (strcmp(var, "clockStyle") == 0) {
    static const char* kSN[] = {"digital","flip","nixie","vfd"};
    int idx = -1;
    for (int i = 0; i < 4; i++) if (strcmp(val, kSN[i]) == 0) { idx = i; break; }
    if (idx < 0) { char tmp[2]; if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 3) idx = -1; }
    if (idx < 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                    "\"error\":\"bad val — use 0-3 or digital/flip/nixie/vfd\"}\n");
      return;
    }
    g_settings.clockStyle = (ClockStyle)idx;
    // TASK-603 (WP-H §1): report save()'s return, exactly as `set fmt24h` above
    // does. Without it T_CLK_08 — "clockStyle persists in settings.json" —
    // could only read the value back through the command that had just written
    // it in RAM, which is true whether or not the save aborted. `saved` is the
    // only persistence observable this command has; it does not prove a reboot
    // survives, and T_CLK_08's own text says so.
    const bool saved = SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"clockStyle\",\"val\":%d,\"name\":\"%s\",\"saved\":%s}\n",
                  idx, kSN[idx], saved ? "true" : "false");
    return;
  }
  if (strcmp(var, "nixieTheme") == 0 || strcmp(var, "vfdTheme") == 0) {
    // M-CLOCK-THEMES (TASK-345): same name/index tables as appsSection.h's
    // cycle rows and the M-CLOCK-NIXIE.md/M-CLOCK-VFD.md theme tables.
    bool isNixie = (strcmp(var, "nixieTheme") == 0);
    static const char* kNixieN[] = {"amber","red","green","blue"};
    static const char* kVfdN[]   = {"teal","amber","blue","green"};
    const char** names = isNixie ? kNixieN : kVfdN;
    int idx = -1;
    for (int i = 0; i < 4; i++) if (strcmp(val, names[i]) == 0) { idx = i; break; }
    if (idx < 0) { if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 3) idx = -1; }
    if (idx < 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"error\":\"bad val — use 0-3 or %s/%s/%s/%s\"}\n",
                    names[0], names[1], names[2], names[3]);
      return;
    }
    if (isNixie) g_settings.nixieTheme = (uint8_t)idx; else g_settings.vfdTheme = (uint8_t)idx;
    SettingsStorage::save();
    if (currentAppId == AppId::Clock) g_ClockApp.resume();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"%s\",\"val\":%d,\"name\":\"%s\"}\n",
                  var, idx, names[idx]);
    return;
  }
  if (strcmp(var, "playerMode") == 0) {   // TASK-260/413 (VE: agent-driven persist/boot tests)
    static const char* kPmNames[] = { "Spotify", "WebRadio", "Player" };
    int idx = -1;
    if      (strcasecmp(val, "spotify")  == 0) idx = 0;
    else if (strcasecmp(val, "webradio") == 0) idx = 1;
    else if (strcasecmp(val, "player")   == 0) idx = 2;
    else if (sscanf(val, "%d", &idx) != 1 || idx < 0 || idx > 2) idx = -1;
    if (idx < 0) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                    "\"error\":\"bad val — use 0-2 or spotify/webradio/player\"}\n");
      return;
    }
    // Pure persist (no app switch): sets + saves the mode so a reboot exercises the v2
    // boot-into-mode path. Use the eject toggle to actually switch the live player slot.
    persistPlayerMode((uint8_t)idx);
    Serial.printf("{\"ok\":true,\"cmd\":\"set\","
                  "\"var\":\"playerMode\",\"val\":%d,\"name\":\"%s\"}\n",
                  idx, kPmNames[idx]);
    return;
  }
  if (strcmp(var, "prloc") == 0) {
    // M-PR-LOCATIONS (TASK-319): two sub-forms sharing the "prloc" var, both
    // carrying more tokens than the generic var/val split above captures —
    // reparse the raw `args` past "prloc " instead of relying on the
    // single-token `val` (drain-all-bytes-at-once lesson: don't assume a
    // fixed token count for multi-field commands).
    const char *rest = args + strlen(var);
    while (*rest == ' ') rest++;

    int idx;
    if (sscanf(rest, "active %d", &idx) == 1) {
      // "set prloc active <i>" — programmatic switch (T_PRL_02 etc.), so
      // switch-side effects are testable independently of strip tap
      // hit-testing. Calls the same shared primitive the strip tap uses
      // (design DEV-3/QM-1's _setActiveLoc — BP-047/LL-110: never a second
      // inline copy of the sequence).
      if (idx < 0 || idx >= (int)PR_NUM_LOCS || g_settings.prLocs[idx].label[0] == '\0') {
        Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                      "\"error\":\"bad or empty slot — active <i> needs 0..%d, non-empty\"}\n",
                      PR_NUM_LOCS - 1);
        return;
      }
      if (currentAppId == AppId::PlaneRadar) {
        // _setActiveLoc() does TFT drawing (disc repaint, strip statics) —
        // only safe to call while PlaneRadar actually owns the screen.
        // Same guard shape as `set clockStyle`'s `if (currentAppId ==
        // AppId::Clock) g_ClockApp.resume();` above.
        g_PlaneRadarApp._setActiveLoc((uint8_t)idx);
      } else {
        // Settings-side only: mirror + persist so the switch survives to
        // the next PlaneRadar resume() (which repaints from g_settings
        // fresh); no result-state reset/re-fetch needed since the app
        // isn't polling while suspended. TASK-473 (G3): routed through the
        // matrix's own active-switch helper instead of a third inline copy.
        SettingsStorage::prActiveLocChanged((uint8_t)idx);
        SettingsStorage::save();
      }
      Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"prloc\",\"active\":%d}\n", idx);
      return;
    }

    char label[16]; float lat, lon;
    if (sscanf(rest, "%d %15s %f %f", &idx, label, &lat, &lon) != 4) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"error\":"
                      "\"bad args — set prloc <i> <label> <lat> <lon> | set prloc active <i>\"}");
      return;
    }
    if (idx < 0 || idx >= (int)PR_NUM_LOCS) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                    "\"error\":\"bad index — 0..%d\"}\n", PR_NUM_LOCS - 1);
      return;
    }
    if (strlen(label) > PR_LABEL_MAX) {
      Serial.printf("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                    "\"error\":\"label too long — max %d chars\"}\n", PR_LABEL_MAX);
      return;
    }
    if (lat < -90.0f || lat > 90.0f || lon < -180.0f || lon > 180.0f) {
      Serial.println("{\"ok\":false,\"cmd\":\"set\",\"var\":\"prloc\","
                      "\"error\":\"out of range — lat -90..90, lon -180..180\"}");
      return;
    }
    for (char *p = label; *p; p++) *p = (char)toupper((unsigned char)*p);
    strlcpy(g_settings.prLocs[idx].label, label, sizeof(g_settings.prLocs[idx].label));
    g_settings.prLocs[idx].lat = lat;
    g_settings.prLocs[idx].lon = lon;
    // M-HOME-LOCATION H-3: this writer refreshed NO mirror before — editing
    // the active slot left the radar on stale coords until reboot/switch, and
    // slot-0 edits would have left weather stale. The shared matrix helper
    // fixes both obligations (home iff idx==0, active iff idx==prActiveLoc).
    SettingsStorage::prSlotWritten((uint8_t)idx);
    SettingsStorage::save();
    Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"prloc\",\"i\":%d,"
                  "\"label\":\"%s\",\"lat\":%.6f,\"lon\":%.6f}\n",
                  idx, g_settings.prLocs[idx].label, lat, lon);
    return;
  }
  Serial.printf("{\"ok\":false,\"cmd\":\"set\","
                "\"error\":\"unknown var\",\"var\":\"%s\"}\n", var);
}
#endif // SERIAL_DEBUG
