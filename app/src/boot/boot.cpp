// boot/boot.cpp — setup(), the Arduino boot sequence, in its own translation
// unit (M-SRCLAYOUT Stage E / TASK-471).
//
// PURE MOVE. Not one line of the body below is edited from what Stage C
// (TASK-455) moved out of main.cpp into boot/boot.h as an inline-in-header
// block. The contract for this stage is `git diff -M` rename similarity plus
// a byte-identical firmware.bin on every build env (TASK-488's precedent — a
// "pure move" claim is settled by comparing the compiled binaries, LL-137,
// and that check costs minutes where a suite run costs an hour). Verified
// here via .map dram0_0_seg (0 B delta vs. every prior Stage E conversion)
// plus the full 12-gate run/check.
//
// setup()'s ORDERING is load-bearing — TASK-288 (a WiFi-wait loop starving
// the watchdog), TASK-404 (an NVS->SPIFFS WiFi race), TASK-426 (a
// NO_AP_FOUND wedge from stale STA config) all trace back to disturbing some
// piece of this sequence. This file exists ONLY to give the function a
// translation unit and the #includes it needs to resolve standalone; it is
// not a rewrite, reorder, or cleanup of anything inside setup() itself.
//
// setup() keeps its exact name/signature (see boot.h) — the lowest-risk
// shape, chosen over the design doc's (M-SRCLAYOUT-main-decomposition.md
// D1a) original `bootSequence()`-rename-plus-wrapper proposal. The
// Arduino/ESP-IDF runtime only needs a globally-linked, non-static
// `void setup()` reachable at link time; it does not need to be textually
// present in main.cpp. So main.cpp no longer #includes boot/boot.h — no
// wrapper function, no rename, less code churn, same safety property (one
// function, one place, one meaning).
//
// Two helpers used exclusively by setup() moved here from main.cpp
// alongside it, verbatim — same "give the body a home with its exclusive
// dependencies" reasoning appShell.cpp used for its own static helpers:
//   - mb_heap_probe()     T_MB_PROBE_00 caps-split heap probe
//   - casRetryDisabled()  TASK-426 A/B control, + its RTC_NOINIT_ATTR globals
// Neither is referenced anywhere else in the codebase (confirmed by a full
// grep before this move). cmdSet.cpp's `extern uint32_t
// g_casRetryCookie/g_casRetryOff` are unaffected — externally-linked globals
// resolve to whichever TU defines them, regardless of which one that is.

#include "boot/boot.h"

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_wifi.h>       // esp_wifi_get_config() — NVS candidate check in the WiFi cascade
#include <FS.h>
#include "SPIFFS.h"
#include <time.h>            // configTzTime(), time() — NTP sync
#include <esp_ota_ops.h>     // esp_ota_get_app_description() — serialdbg-001 boot banner
#include <esp_log.h>         // esp_log_level_set() — ADR-042 E1 HTTPClient log suppression
#include <esp_task_wdt.h>    // esp_task_wdt_init/deinit/add/reset
#include <esp_heap_caps.h>   // mb_heap_probe() — caps-split heap probe

#include <SpotifyArduino.h>
#include <SpotifyArduinoCert.h>   // spotify_server_cert
#include <ArduinoJson.h>

#include "secret.h"             // redact() (inline)
#include "spotifyDisplay.h"     // SpotifyDisplay abstract interface
#include "httpsDate.h"          // fetchHttpsDate()/buildEpoch() (inline)

#include "logSink.h"
#include "logServer.h"
#include "wifiDiag.h"
#include "spotifyTask.h"
#include "dataTask.h"
#include "settingsStorage.h"     // g_settings, PlayerMode, SettingsStorage::load()
#include "util/mathUtil.h"       // buildMathLUT()

#include "appShell.h"            // AppId, currentAppId, switchApp
#include "shell/shellState.h"    // shell::state()
#include "shell/shellDispatch.h" // shell::activeError()/activeConnecting()
#include "shell/taskbar.h"       // renderTaskbar(), TASKBAR_APP_COUNT
#include "shell/appTable.h"      // g_apps[], g_SettingsApp, g_ledFlow, g_backlight — and,
                                  // transitively (via apps/settingsApp.h): settings/wifiSection.h
                                  // (SavedWifiNet, WIFI_MAX_SAVED, WIFI_NETWORKS_JSON,
                                  // kWifiNetworksJsonCapacity) and settings/calibrationFlow.h
                                  // (TouchCalStorage, g_calData) — same pattern appShell.cpp and
                                  // console.cpp used.
#include "sd/sdMount.h"          // sdProbeBootMount()
#include "CYD28_TouchscreenR.h"  // CYD28_TouchR / CYD28_TS_Point (for `ts` below)

// TASK-501: WINAMP_DISPLAY is unconditionally defined — no #ifdef needed.
#include "winamp/winampDisplay.h"
extern WinampDisplay winampDisplay;   // defined in main.cpp

#ifdef NFC_ENABLED
#include "nfc.h"
#endif

#include "display/tft.h"
extern CYD28_TouchR ts;           // defined once, in cheapYellowLCD.h's touchScreen.h chain

// The following are defined exactly once, directly in main.cpp's translation
// unit (main.cpp #includes spotifyLogic.h / refreshToken.h / configFile.h
// itself, unguarded and non-inline — a second #include of any of them here
// would duplicate-define their globals/functions at link time). Declared
// extern here instead, same convention as tft/ts/winampDisplay above.
extern SpotifyDisplay   *spotifyDisplay;     // display backend, set in main.cpp's #if block
extern SpotifyArduino    spotify;            // defined in spotifyLogic.h (included by main.cpp)
extern char              clientId[200];      // defined in main.cpp
extern char              clientSecret[200];  // defined in main.cpp
extern char              refreshToken[400];  // defined in refreshToken.h (included by main.cpp)

bool fetchConfigFile(char *refreshToken, char *clientId, char *clientSecret);   // configFile.h
void saveConfigFile(char *refreshToken, char *clientId, char *clientSecret);    // configFile.h
bool launchRefreshTokenFlow(SpotifyArduino *spotifyObj, char *clientId);        // refreshToken.h
void spotifySetup(SpotifyDisplay *theDisplay, const char *clientId, const char *clientSecret);  // spotifyLogic.h
void spotifyRefreshToken(const char *refreshToken);                             // spotifyLogic.h

// TASK-426 A/B control for the boot cascade's per-candidate retry — moved
// here from main.cpp, verbatim; only used by setup()'s WiFi cascade below.
// See main.cpp's note at the old definition site for the RTC_NOINIT_ATTR
// rationale (must survive the SOFTWARE reset that starts a debug run).
#ifdef SERIAL_DEBUG
static constexpr uint32_t kCasRetryCookie = 0x426AB1FEu;
RTC_NOINIT_ATTR uint32_t g_casRetryCookie;
RTC_NOINIT_ATTR uint32_t g_casRetryOff;
static inline bool casRetryDisabled() {
  return g_casRetryCookie == kCasRetryCookie && g_casRetryOff != 0;
}
#else
static inline bool casRetryDisabled() { return false; }
#endif

// T_MB_PROBE_00: caps-split heap probe — moved here from main.cpp, verbatim;
// only used by setup()'s boot milestones below.
#if defined(MEMBUDGET_PHASE1) && defined(SERIAL_DEBUG)
static void mb_heap_probe(const char *tag) {
    Serial.printf("[membudget] %s freeInt=%u lfbInt=%u freeDma=%u lfbDma=%u\n",
        tag,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
}
#else
static inline void mb_heap_probe(const char *) {}   // no-op (production / non-debug)
#endif

void setup()
{
  // Extend TWDT from 5→15s: dataTask TLS handshakes (webradio station list,
  // stock quotes) can take 6-10s on cold start and starve the CPU0 idle task.
  // SpotifyTask avoids this via tlsYield(), but dataTask has no such mechanism.
  // esp_task_wdt_init() is a no-op when already initialized; must deinit first.
  esp_task_wdt_deinit();
  esp_task_wdt_init(15, true);
  esp_task_wdt_add(NULL);  // re-subscribe loopTask (current task)
  esp_task_wdt_add(xTaskGetIdleTaskHandleForCPU(0));  // re-subscribe CPU0 idle

  // TASK-410 / ADR-059 D12: capture loopTask's own handle once, here — setup()
  // runs on loopTask, same task loop() will run on for the rest of the process
  // lifetime. audioEngine.h's aeDrainEof() asserts against this.
  g_loopTaskHandle = xTaskGetCurrentTaskHandle();

  Serial.begin(115200);

#ifdef SD_BOOT_MOUNT
  // TASK-408 (2026-08-07): mount SD here, synchronously, and hold the session for
  // the process lifetime — NOT the lazy per-mode-entry mount M-SDFS §5 assumes.
  //
  // `SD.begin()` needs ONE contiguous byte-addressable internal block of
  // `sizeof(vfs_fat_ctx_t) + max_files * sizeof(FIL)` (see kSdMaxFiles). At boot that
  // is trivial — the largest free 8-bit block is ~110 KB. Once WebRadio is playing it
  // is ~5 KB, and the mount fails with `esp_vfs_fat_register` → ESP_ERR_NO_MEM, which
  // is that calloc failing and NOT (as first read) the FF_VOLUMES table being full.
  // DUT-reproduced both ways: mounts at every heap state above the ctx size, fails at
  // every state below it, at every max_files setting. `sdmem` prints both numbers.
  //
  // So a lazy mount is only ever as reliable as the heap happens to be at the moment
  // the user enters the mode, and LocalPlayer needs the card mounted *and* the Helix
  // arena acquired at the same time. Mounting before any of that exists is the design,
  // not a workaround.
  //
  // TASK-427: gated on SD_BOOT_MOUNT, not SERIAL_DEBUG — production (cyd2usb_winamp)
  // does not define it and never mounts (sdReady() stubs to false there); the dedicated
  // cyd2usb_player variant and cyd2usb_winamp_debug both define it.
  sdProbeBootMount();
#endif

  // TASK-267: arena is acquired JIT in WebRadioApp::_play(), NOT at boot (so the
  // station fetch isn't starved — TASK-265). Boot baseline probe (debug-only).
  mb_heap_probe("boot-baseline");

  // serialdbg-001 (TASK-056b): unconditional boot banner. Carved out of the
  // SERIAL_DEBUG gate per ADR-021 Decision 4 as a production-safe diagnostic
  // — gives any host (test rig or end user) a deterministic way to confirm
  // which firmware is actually flashed without round-tripping a command.
  // GIT_REV comes from scripts/inject_git_hash.py; "n/a" when undefined
  // (e.g. non-debug envs that skip the pre-script).
  {
    const esp_app_desc_t *d = esp_ota_get_app_description();
    char elf[9];
    snprintf(elf, sizeof(elf), "%02x%02x%02x%02x",
             d->app_elf_sha256[0], d->app_elf_sha256[1],
             d->app_elf_sha256[2], d->app_elf_sha256[3]);
    Serial.printf("[boot] git=%s elf=%s build=%s %s\n",
#ifdef GIT_REV
        GIT_REV,
#else
        "n/a",
#endif
        elf, __DATE__, __TIME__);
  }

#ifdef SERIAL_DEBUG
  // ADR-042 E1: suppress verbose HTTPClient log that garbles serial JSON responses.
  esp_log_level_set("HTTPClient",  ESP_LOG_NONE);
  esp_log_level_set("HTTP_CLIENT", ESP_LOG_NONE);
#endif
  logsink::begin();

  spotifyDisplay->displaySetup(&spotify);

#ifdef NFC_ENABLED
  if (nfcSetup(&spotify, spotifyDisplay))
  {
    Serial.println("NFC Good");
  }
  else
  {
    Serial.println("NFC Bad");
  }
#endif

  bool spiffsInitSuccess = SPIFFS.begin(false) || SPIFFS.begin(true);
  if (!spiffsInitSuccess)
  {
    Serial.println("SPIFFS initialisation failed!");
    while (1)
      yield();
  }
  Serial.println("\r\nInitialisation done.");

  // settings-001: load persisted settings, then set up backlight PWM.
  // tft.init() (inside displaySetup above) uses digitalWrite(TFT_BL, HIGH) —
  // no LEDC channel is configured. Take over GPIO21 now so ledcWrite() works.
  SettingsStorage::load();
  TouchCalStorage::load();
  if (g_calData.valid)
    ts.setCalibration(g_calData.xMin, g_calData.xMax, g_calData.yMin, g_calData.yMax);
  analogReadResolution(12);        // TASK-151: ensure 12-bit ADC for LDR on GPIO34
  ledcSetup(0, 5000, 8);           // 5 kHz, 8-bit — channel 0 matches TFT_LEDC_CHANNEL
  ledcAttachPin(TFT_BL, 0);        // redirect GPIO21 from digital to LEDC
  // WIRE2-G5: owner applies the stored mode before first frame — honours
  // dispAuto (one LDR sample → mapped duty) instead of unconditionally
  // applying the manual dispLevel like the old inline block did.
  g_backlight.applyMode();
  // RGB LED channels (ch1=R/GPIO4, ch2=G/GPIO16, ch3=B/GPIO17).
  ledcSetup(LED_R_CH, 5000, 8); ledcAttachPin(LED_R_PIN, LED_R_CH);
#if !NFC_ENABLED
  ledcSetup(LED_G_CH, 5000, 8); ledcAttachPin(LED_G_PIN, LED_G_CH);
#endif
  ledcSetup(LED_B_CH, 5000, 8); ledcAttachPin(LED_B_PIN, LED_B_CH);
  g_ledFlow.applyMode();

  // TASK-501: WINAMP_DISPLAY is unconditionally defined — no #ifdef needed.
  // M-BOOT-UI (TASK-364, ADR-055 decision 1): paint the Winamp chrome now —
  // a flash-resident composite blit, no heap/network cost — instead of
  // leaving the screen solid black through the WiFi/NTP phases below. This
  // is an *additional* direct call to the renderer, not a reorder of the
  // existing g_apps[(int)AppId::Spotify]->init() + renderTaskbar() block
  // further down (main.cpp ~2415) — that block is unchanged, and its
  // second pass becomes a harmless, idempotent repaint (design doc §1).
  winampDisplay.showDefaultScreen();
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
  winampDisplay.setTitle("STARTING UP...");

  refreshToken[0] = '\0';
  fetchConfigFile(refreshToken, clientId, clientSecret);

  // TASK-274 (M-WIFI-DIAG): link-event ground truth. Must register before the
  // first WiFi.begin() below or early events (incl. the boot-window drop E1)
  // are missed. Ships in all builds — [wifi-ev] is a stable log contract.
  wifiDiag::begin();

  // WiFi boot: NVS credentials → saved networks (/wifi_networks.json, or
  // legacy single-entry /wifi_creds.json pre-migration) → open WiFi settings.
  // Priority chain mirrors WifiSection connect flow (C4: NVS-backed persist).
  // TASK-296: wifiCredsKnown tracks whether ANY source held credentials —
  // "connect failed with stored creds" (AP storm at boot) must not be treated
  // as "no credentials", or the device parks dead in the Settings screen.
  // TASK-404: this used to also try a HARDCODED_WIFI_SSID stage ahead of NVS,
  // sourced from a wifi_creds.h shim — removed 2026-08-06 after discovering
  // that shim was never actually wired into the build (wrong file path, no
  // #include anywhere), making the whole stage permanently dead code. NVS is
  // the real first stage now.
  bool wifiConnected  = false;
  bool wifiCredsKnown = false;
  {
    winampDisplay.setTitle("WI-FI: CONNECTING...");  // M-BOOT-UI (TASK-364) §2
    WiFi.persistent(true);
    WiFi.mode(WIFI_STA);
    // TASK-296: driver is up after mode() — a non-empty stored SSID means NVS
    // holds credentials even if the connect window below expires.
    wifi_config_t nvsCfg;
    if (esp_wifi_get_config(WIFI_IF_STA, &nvsCfg) == ESP_OK && nvsCfg.sta.ssid[0] != 0)
      wifiCredsKnown = true;
    WiFi.begin();  // reconnect from NVS (no args)
    { unsigned long dl = millis() + 10000;
      // TASK-288: feed the TWDT every iteration — this loop's own deadline can
      // chain into the SPIFFS fallback loop below with zero resets in
      // between, so cumulative un-fed time (not any single loop's deadline)
      // is what was tripping task_wdt during a flaky-AP boot.
      while (WiFi.status() != WL_CONNECTED && millis() < dl) {
        delay(100); esp_task_wdt_reset();
        winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
      } }
    wifiConnected = (WiFi.status() == WL_CONNECTED);
  }
  if (!wifiConnected) {
    // TASK-404: the NVS attempt above leaves autoReconnect at its default
    // true, so a failed attempt keeps retrying the same (bad) NVS creds in
    // the background (WiFiGeneric.cpp's STA_DISCONNECTED handler calls
    // WiFi.disconnect()+WiFi.begin() itself on every reconnectable-reason
    // disconnect). If the SPIFFS stage below calls its own WiFi.begin()
    // while that background retry is still mid-attempt, esp_wifi_connect()
    // returns ESP_ERR_WIFI_CONN ("sta is connecting, return error") and the
    // SPIFFS attempt silently no-ops — the fallback cascade doesn't actually
    // try the SPIFFS creds until the background retry happens to be between
    // attempts, which is why recovery only reliably happened via the
    // separate background wifiDiag supervisor ~60-85s later. Stop the NVS
    // stage's background retry and let the driver settle before handing
    // control to SPIFFS's own explicit attempt.
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false);
    { unsigned long dl = millis() + 300;
      while (millis() < dl) { delay(20); esp_task_wdt_reset(); }
    }
    // TASK-426: a full driver stop/start here (WIFI_OFF → WIFI_STA, confirmed
    // by STA_STOP/STA_START in the event log) was tried and does NOT help — the
    // first candidate still failed at ~2.7 s. So the cross-stage problem is not
    // an in-flight scan surviving into the next stage, and lengthening this
    // settle is not the fix. See the per-candidate retry below for what is.
  }
  if (!wifiConnected) {
    // Gather saved-network candidates from two merged sources:
    //  - /wifi_networks.json: TASK-401's saved-network store (up to
    //    WIFI_MAX_SAVED entries), tried most-recently-used first, so a
    //    renamed/rotated AP that's still in the saved list gets found
    //    without a trip through Settings.
    //  - /wifi_creds.json: the operator-facing provisioning file (run/setup,
    //    or a hand-pushed SPIFFS image per the "pre-baked SPIFFS files" doc'd
    //    workflow). Always merged in at highest priority, even when
    //    /wifi_networks.json already has entries — it's the file a human
    //    just edited/pushed to fix a credential, and the saved-network list
    //    can otherwise sit stale (e.g. across an SSID rename) until
    //    Settings->WiFi is opened and reconnects manually.
    // +1 sizing: /wifi_creds.json's entry can add one candidate beyond
    // WIFI_MAX_SAVED's cap on /wifi_networks.json entries (dedup'd by SSID,
    // so it only ever adds — never evicts — a saved entry).
    SavedWifiNet cand[WIFI_MAX_SAVED + 1];
    uint8_t candCount = 0;
    if (SPIFFS.exists(WIFI_NETWORKS_JSON)) {
      File f = SPIFFS.open(WIFI_NETWORKS_JSON, "r");
      if (f) {
        DynamicJsonDocument doc(kWifiNetworksJsonCapacity);
        if (deserializeJson(doc, f) == DeserializationError::Ok) {
          for (JsonVariantConst v : doc["networks"].as<JsonArrayConst>()) {
            if (candCount >= WIFI_MAX_SAVED) break;
            const char* ssid = v["ssid"] | "";
            if (!ssid[0]) continue;
            strlcpy(cand[candCount].ssid, ssid, sizeof(cand[0].ssid));
            strlcpy(cand[candCount].pass, v["pass"] | "", sizeof(cand[0].pass));
            cand[candCount].lastUsedMs = v["lastUsedMs"] | 0UL;
            candCount++;
          }
        }
        f.close();
      }
    }
    if (SPIFFS.exists("/wifi_creds.json")) {
      File f = SPIFFS.open("/wifi_creds.json", "r");
      if (f) {
        StaticJsonDocument<256> doc;
        if (deserializeJson(doc, f) == DeserializationError::Ok) {
          const char* ssid = doc["ssid"] | "";
          if (ssid[0]) {
            int8_t existing = -1;
            for (uint8_t i = 0; i < candCount; i++) {
              if (strcmp(cand[i].ssid, ssid) == 0) { existing = (int8_t)i; break; }
            }
            uint8_t slot = (existing >= 0) ? (uint8_t)existing : candCount;
            if (existing >= 0 || candCount < WIFI_MAX_SAVED + 1) {
              strlcpy(cand[slot].ssid, ssid, sizeof(cand[0].ssid));
              strlcpy(cand[slot].pass, doc["pass"] | "", sizeof(cand[0].pass));
              cand[slot].lastUsedMs = 0xFFFFFFFFUL;  // always tried first
              if (existing < 0) candCount++;
            }
          }
        }
        f.close();
      }
    }
    // Most-recently-used first (small N — plain insertion sort). Best-effort:
    // saved lastUsedMs values are millis()-since-boot from whichever session
    // last wrote them, so cross-boot ordering is a heuristic, not a true
    // timestamp compare — /wifi_creds.json's sentinel above is exempt, it's
    // always meant to sort first.
    for (uint8_t i = 1; i < candCount; i++) {
      SavedWifiNet key = cand[i];
      int8_t j = i - 1;
      while (j >= 0 && cand[j].lastUsedMs < key.lastUsedMs) {
        cand[j + 1] = cand[j];
        j--;
      }
      cand[j + 1] = key;
    }
    if (candCount > 0) wifiCredsKnown = true;  // TASK-296

    // TASK-426: hand the (already MRU-sorted) candidates to the supervisor so
    // its kicks target real SSIDs instead of replaying whatever config the
    // cascade below happens to leave resident. Registered before the attempts
    // so a supervisor armed on ANY exit path from here has them.
    wifiDiag::superviseClearCandidates();
    for (uint8_t i = 0; i < candCount; i++)
      wifiDiag::superviseAddCandidate(cand[i].ssid, cand[i].pass);

    const char* connectedSsid = nullptr;
    const char* connectedPass = nullptr;
    for (uint8_t i = 0; i < candCount && !wifiConnected; i++) {
      winampDisplay.setTitle("WI-FI: CONNECTING...");  // M-BOOT-UI (TASK-364) §2
      Serial.printf("[wifi] Connecting from saved networks (%u/%u): %s\n",
                    (unsigned)(i + 1), (unsigned)candCount, cand[i].ssid);
      WiFi.persistent(false);  // don't corrupt NVS if creds are wrong (TASK-167)
      WiFi.mode(WIFI_STA);
      WiFi.begin(cand[i].ssid, cand[i].pass);
      // Bounded per-candidate probe: trimmed from the old single-network 30s
      // window so a full sweep of stale saved networks stays bounded (up to
      // WIFI_MAX_SAVED=5 candidates * 10s = 50s worst case, vs. 150s at the
      // old per-network timeout would have cost). A real, present AP
      // associates in ~1s per the TASK-404 boot log; NO_AP_FOUND retries
      // fire every ~2.4s, so 10s covers several rejection cycles before
      // moving on, not a hair trigger.
      { unsigned long dl = millis() + 10000;
        // TASK-426: auto-reconnect is off for the whole cascade (TASK-404's
        // fix for cross-stage collisions), which has the side effect that a
        // candidate gets exactly ONE connect attempt — nothing re-issues it.
        // A transient NO_AP_FOUND therefore burns the rest of the 10 s window
        // as dead air. Measured with a stale SSID in NVS: the first attempt for
        // the live AP failed ~2.7 s in, then the window idled to 10 s and the
        // cascade gave up, while the very next attempt at the SAME ssid (via
        // auto-reconnect, once re-armed) associated. Re-issue on each observed
        // failure instead, using discCount as the "that attempt finished" edge.
        uint32_t seenDisc = wifiDiag::discCount;
        const bool casNoRetry = casRetryDisabled();
        Serial.printf("[wifi] cascade retry %s\n",
                      casNoRetry ? "DISABLED (A/B control)" : "on");
        // TASK-288: see hardcoded-SSID loop above — feed TWDT every iteration.
        while (WiFi.status() != WL_CONNECTED && millis() < dl) {
          delay(250); Serial.print("."); esp_task_wdt_reset();
          if (!casNoRetry && wifiDiag::discCount != seenDisc) {
            seenDisc = wifiDiag::discCount;
            if (millis() < dl) { Serial.print("r"); WiFi.begin(cand[i].ssid, cand[i].pass); }
          }
          winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
        }
        Serial.println(); }
      if (WiFi.status() == WL_CONNECTED) {
        wifiConnected = true;
        connectedSsid = cand[i].ssid;
        connectedPass = cand[i].pass;
      } else {
        WiFi.disconnect(false);
      }
    }

    if (wifiConnected) {
      WiFi.persistent(true);
      WiFi.begin(connectedSsid, connectedPass);  // persist verified creds to NVS
      winampDisplay.setTitle("WI-FI: CONNECTING...");  // M-BOOT-UI (TASK-364) §2, re-assoc settle
      // TASK-290: this re-begin DEAUTHS the just-verified association
      // (observed [wifi-ev] reason=8 ~150ms after GOT_IP) and the code
      // below read localIP() before re-association finished — boot
      // proceeded with "IP address: 0.0.0.0" whenever the NVS attempt
      // missed its window and this saved-network path ran. Wait (bounded,
      // TWDT-fed per TASK-288) for the re-association to settle.
      { unsigned long dl = millis() + 15000;
        while (WiFi.status() != WL_CONNECTED && millis() < dl) {
          delay(100); esp_task_wdt_reset();
          winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
        } }
      wifiConnected = (WiFi.status() == WL_CONNECTED);
      Serial.println("[wifi] saved-network credentials saved to NVS");
    } else if (candCount > 0) {
      Serial.println("[wifi] all saved-network connect attempts failed");
      // TASK-426: the loop above leaves its LAST candidate resident in the STA
      // config, and auto-reconnect (armed just below) re-attacks that resident
      // config every ~2.4 s via a bare WiFi.begin(). When the last candidate is
      // a dead SSID that is an unrecoverable wedge — auto-reconnect never tries
      // anything else, so a live AP at -58 dBm goes untouched until reboot.
      // Re-point at the best (MRU-first) candidate so the 60 s of auto-reconnect
      // before the supervisor's first kick is spent on the likeliest AP.
      // persistent(false) — the candidate is unverified, and committing an
      // unverified SSID to NVS is how the stale-NVS state gets created.
      WiFi.persistent(false);
      WiFi.begin(cand[0].ssid, cand[0].pass);
    }
  }

  if (wifiConnected) {
    winampDisplay.setTitle("WI-FI: CONNECTED");  // M-BOOT-UI (TASK-364) §2
    // TASK-272: disable modem power-save. With the default WIFI_PS_MIN_MODEM the
    // radio dozes after idle periods; the first TCP connect after ~30-45 s of
    // network quiet then fails with EHOSTUNREACH (errno 118) for tens of seconds
    // (observed 2026-07-02 killing every WebRadio post-idle connect; TASK-238 gate
    // read 0/10 because auto-skip burned the station list inside the outage and
    // parked terminal). Mains/USB-powered device — the ~40 mA cost is irrelevant.
    WiFi.setSleep(false);
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else if (wifiCredsKnown) {
    // TASK-296: stored credentials exist but every connect window expired —
    // seen 2026-07-08 when a bursty-AP NO_AP_FOUND/AUTH_FAIL storm spanned the
    // whole boot chain (and once via the TASK-290 persist re-begin deauth whose
    // 15 s settle-wait expired under the same storm). The old path demoted this
    // to "no credentials": setAutoReconnect(false) + auto-open Settings, whose
    // foreground suppresses superviseTick() — a permanent park needing manual
    // reset. Instead: leave auto-reconnect armed and arm the supervisor so the
    // link self-heals when the AP settles.
    WiFi.setAutoReconnect(true);
    wifiDiag::superviseArm();
    winampDisplay.setTitle("WI-FI: RETRY IN BG");  // M-BOOT-UI (TASK-364) §2
    Serial.println("[wifi] connect failed with stored credentials — reconnect + supervisor armed");
  } else {
    // Leave WiFi in a clean disconnected STA state so WifiSection scan works.
    // WiFi.begin() (NVS attempt above) leaves auto-reconnect armed; disable it
    // so the subsequent scanNetworks() call is not blocked by a reconnect loop.
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(false);
    winampDisplay.setTitle("WI-FI SETUP NEEDED");  // M-BOOT-UI (TASK-364) §2
    Serial.println("[wifi] no credentials — will open WiFi settings after init");
  }
  mb_heap_probe("post-wifi");  // TASK-261 Phase 0 milestone M1

  // TASK-288: fresh watchdog budget before NTP sync + spotifyRefreshToken()
  // below — none of setup()'s WiFi-connect wait loops fed the TWDT before
  // this fix, so a flaky AP requiring more than one fallback attempt could
  // already have consumed most of the 15s window before reaching here.
  esp_task_wdt_reset();

  // time-001: SNTP sync before any TLS. ESP32 has no RTC; without this the
  // clock starts ~1970 and mbedTLS rejects current Spotify certs (notBefore
  // in the future), surfacing as a generic "send_ssl_data 0x0050" failure.
  // 5 s bounded wait, non-fatal on timeout.
  // WIRE2-G1: apply the persisted TZ rule at boot (SettingsStorage::load()
  // ran above) instead of hardcoded UTC; fresh device defaults to "UTC0" —
  // identical behaviour. The epoch wait below is TZ-independent.
  winampDisplay.setTitle("TIME: SYNCING...");  // M-BOOT-UI (TASK-364) §2
  configTzTime(g_settings.posixTz, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  unsigned long ntpStart = millis();
  unsigned long ntpDeadline = ntpStart + 5000;
  while (time(nullptr) < 1700000000UL && millis() < ntpDeadline) {
    delay(50);
    yield();
    winampDisplay.tickMarquee();  // M-BOOT-UI (TASK-364) §3 Option B
  }
  time_t now = time(nullptr);
  if (now >= 1700000000UL) {
    Serial.printf("[time] synced epoch=%ld in %lums\n", (long)now, millis() - ntpStart);
  } else {
    Serial.printf("[time] NTP sync failed after %lums, trying HTTPS-Date fallback\n",
                  millis() - ntpStart);
    winampDisplay.setTitle("TIME: HTTPS FALLBACK...");  // M-BOOT-UI (TASK-364) §2
    time_t httpsT;
    if (fetchHttpsDate("connectivitycheck.gstatic.com", httpsT)) {
      struct timeval tv = {httpsT, 0};
      settimeofday(&tv, nullptr);
      Serial.printf("[time] HTTPS-Date set epoch=%ld\n", (long)httpsT);
    } else {
      time_t b = buildEpoch();
      struct timeval tv = {b, 0};
      settimeofday(&tv, nullptr);
      Serial.printf("[time] WARN: NTP+HTTPS-Date failed, falling back to build epoch=%ld\n", (long)b);
    }
  }

  spotifySetup(spotifyDisplay, clientId, clientSecret);

#if defined YELLOW_DISPLAY

  pinMode(0, INPUT); // has an internal pullup
  bool forceRefreshToken = digitalRead(0) == LOW;
  if (forceRefreshToken)
  {
    Serial.println("GPIO 0 is low, forcing refreshToken");
  }

#else
  bool forceRefreshToken = false;

#endif

  // Check if we have a refresh Token
  if (forceRefreshToken || refreshToken[0] == '\0')
  {

    spotifyDisplay->drawRefreshTokenMessage();
    Serial.println("Launching refresh token flow");
    if (launchRefreshTokenFlow(&spotify, clientId))
    {
      Serial.printf("Refresh token acquired: %s\n", redact(refreshToken));
      saveConfigFile(refreshToken, clientId, clientSecret);
    }
  }

  // TASK-363 (M-SPOTIFY-BOOT-GATE, ADR-054 decision 1): computed once, must
  // mirror the boot-switch condition below (main.cpp ~line 2407) exactly —
  // NOT raw playerMode alone. If WiFi isn't up yet, the boot-switch keeps
  // currentAppId == Spotify (visibly on screen) regardless of the persisted
  // preference, and that visible app must still be allowed to connect once
  // WiFi comes up via the background supervisor; seeding from raw
  // playerMode would silently strand it idle.
  bool bootIntoWebRadio = wifiConnected && (g_settings.playerMode == (uint8_t)PlayerMode::WebRadio);

  // TASK-447: the same argument as TASK-363's, for the two cases it did not
  // cover. MEASURED on cyd2usb_player 2026-08-15: this refresh is a full
  // mbedTLS session costing 43 596 B of the 8-bit internal pool
  // (post-wifi free8 94 124 -> post-spotifyTask 50 528), and it takes the
  // largest free block from 90 100 to 40 948 permanently — the session is torn
  // down, its carve is not. Local playback needs ~47 KB and had 32 032, i.e.
  // the whole shortfall was being spent on a token the build cannot use.
  //   - DISABLE_SPOTIFY: there is no Spotify at all; refreshing is pure cost.
  //   - playerMode == Player: same reasoning TASK-363 applied to WebRadio —
  //     nothing will call the API until the user toggles to Spotify, and
  //     SpotifyArduino's autoTokenRefresh handles it lazily when they do.
  // Mirrors bootIntoWebRadio's wifiConnected guard for the Player case for the
  // identical reason (a not-yet-connected boot leaves Spotify visibly on screen
  // and it must still be able to connect when the supervisor brings WiFi up).
#ifdef DISABLE_SPOTIFY
  const bool deferSpotifyRefresh = true;
#else
  const bool deferSpotifyRefresh =
      bootIntoWebRadio ||
      (wifiConnected && g_settings.playerMode == (uint8_t)PlayerMode::Player);
#endif

  // TASK-363 companion 1 (Finding 2/3): under bootIntoWebRadio, skip the
  // eager network-calling refreshAccessToken() leg — it opens a real TLS
  // connect on the same shared `client` spotifyTask uses, independent of
  // any gate on begin(). setRefreshToken() alone primes the library with
  // zero network; SpotifyArduino's autoTokenRefresh (default true) already
  // refreshes lazily before the first real API call, which under this
  // design only happens after an explicit toggle-to-Spotify. The
  // forceRefreshToken/launchRefreshTokenFlow() credential-bootstrap path
  // above is unaffected — stays unconditional.
  if (deferSpotifyRefresh) {
    spotify.setRefreshToken(refreshToken);
    Serial.printf("[boot] spotify=idle (%s) — refresh deferred, no TLS at boot (TASK-447)\n",
#ifdef DISABLE_SPOTIFY
                  "build has DISABLE_SPOTIFY"
#else
                  bootIntoWebRadio ? "playerMode=webradio" : "playerMode=player"
#endif
                  );
  } else {
    spotifyRefreshToken(refreshToken);
  }

  // refreshToken.h flow would have held port 80. Stand up permanent /log server now.
  logsink::serverBegin();

  // ADR-012 / TASK-031a: spawn the async Spotify HTTP task. Skeleton at
  // this stage — task dequeues + logs but doesn't issue API calls yet.
  // 031b/c migrate the actual calls in.
#ifndef DISABLE_SPOTIFY
  // TASK-363 (M-SPOTIFY-BOOT-GATE, ADR-054 decision 1): seed the task idle
  // before its first loop iteration when booting straight into WebRadio —
  // closes the boot race where setWebRadioActive(true) (from the
  // switchApp(WebRadio) call below) arrived too late to stop the first
  // self-issued ACT_POLL from connecting TLS ~5s after begin().
  //
  // TASK-448: the gate keyed on WebRadio alone, so a Player-mode boot on a
  // Spotify-enabled build deferred the boot refresh (TASK-447) and then handed
  // the memory straight back ~5s later when the task self-issued its first
  // ACT_POLL and refreshed the token anyway (measured: post-init-idle
  // lfbDma=65524 collapsing to a steady-state maxAlloc=41k, indistinguishable
  // from Spotify mode). Reuse deferSpotifyRefresh so the two decisions cannot
  // drift apart again — its DISABLE_SPOTIFY definition (always true) is
  // unreachable from here, this call site being inside #ifndef DISABLE_SPOTIFY.
  spotifyTask::begin(&spotify, deferSpotifyRefresh);
#else
  // TASK-255 (M-WEBRADIO-NOPSRAM): the SOLE functional guard. Skipping begin()
  // means reqQueue / s_tlsYieldedSem stay null, so tlsYield()/tlsResume() (and
  // every spotifyTask:: accessor) no-op via their existing null-guards — no
  // session to free → BP-031 n/a in this variant (default build unchanged; see
  // docs/architecture/designs/M-WEBRADIO-SPOTIFY-DISABLE.md). Frees the ~10 KB
  // task stack + ~50 KB TLS for the no-PSRAM WebRadio decoder.
  Serial.println("[boot] spotify=off");   // V0 readiness token (harness scrapes pre-shell)
#endif
  mb_heap_probe("post-spotifyTask");  // TASK-261 Phase 0 milestone M2
  dataTask::begin();
  mb_heap_probe("post-dataTask");     // TASK-261 Phase 0 milestone M3

  // Boot: init the Spotify app via the App interface, then draw taskbar.
  if (g_apps[(int)AppId::Spotify]) {
    shell::state().launched[(int)AppId::Spotify] = true;
    g_apps[(int)AppId::Spotify]->init();
  } else {
    spotifyDisplay->showDefaultScreen();
  }
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
  // TASK-296: only a genuinely credential-less boot auto-opens Settings. A
  // creds-known offline boot stays on the normal shell (supervisor owns the
  // link; Settings foreground would suppress it — the park-dead chain).
  if (!wifiConnected && !wifiCredsKnown) {
    switchApp(AppId::Settings);
    g_SettingsApp.openSection(0);
  }
  // TASK-260 v2 (OQ-BOOT): cold-boot directly into the persisted player mode. After the
  // Spotify app's boot init() above (so switchApp's suspend() tears it down cleanly),
  // enter WebRadio if that was the last-active mode. Whether a station then auto-plays is
  // governed by the existing webRadioAutoplay knob — these compose. Skipped when offline
  // (no network for the station fetch — including the TASK-296 creds-known offline boot).
  // TASK-363: reuses bootIntoWebRadio computed above (same condition, computed once) —
  // this switchApp(WebRadio) call's setWebRadioActive(true) is now purely confirmatory,
  // the idle flag was already seeded before spotifyTask::begin() ran.
  else if (bootIntoWebRadio) {
    switchApp(AppId::WebRadio);
  }
  // TASK-413: LocalPlayer has no network dependency (SD-backed), so unlike WebRadio
  // its boot restore isn't gated on wifiConnected — it only needs the offline/no-creds
  // Settings branch above to have not already claimed the boot screen.
  else if (g_settings.playerMode == (uint8_t)PlayerMode::Player) {
    switchApp(AppId::LocalPlayer);
  }
  mb_heap_probe("post-init-idle");    // TASK-261 Phase 0 milestone M4 (steady idle)
  buildMathLUT();
}
