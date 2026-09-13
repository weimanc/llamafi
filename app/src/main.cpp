/*******************************************************************
    Displays Album Art on a 320 x 240 ESP32.

    Parts:
    ESP32 With Built in 320x240 LCD with Touch Screen (ESP32-2432S028R)
    https://github.com/witnessmenow/Spotify-Diy-Thing#hardware-required

 *******************************************************************/

// ----------------------------
// Display type
// ---------------------------

// This project currently supports the following displays
// (Uncomment the required #define)

// 1. Cheap yellow display (Using TFT-eSPI library) — RETIRED. ADR-061 D9
// consequences: "no longer a supported target" (human decision, 2026-08-15).
// The implementing class (CheapYellowDisplay, cheapYellowLCD.h/.cpp) was
// deleted in TASK-470 once WinampDisplay no longer depended on it (TASK-469
// flattened it onto SpotifyDisplay directly). Note: `YELLOW_DISPLAY` the
// *macro* is still defined unconditionally by every CYD env (`[common_cyd]`
// in platformio.ini) for an unrelated reason — boot.cpp's GPIO0
// forceRefreshToken gate keys off it too, independently of display
// selection — so it isn't safe to repurpose this identifier for anything
// else without checking that use as well.
// #define YELLOW_DISPLAY

// 2. Matrix Displays (Like the ESP32 Trinity)
// #define MATRIX_DISPLAY

// 3. Winamp 2 skin renderer on CYD2USB (M3 — uses gen/ atlas)
// #define WINAMP_DISPLAY

// Album art disabled while the i.scdn.co fetch hang is unresolved.
// Comment out to re-enable.
#define DISABLE_ALBUM_ART 1

// NFC disabled per TASK-004: PN532 not wired on this dev unit.
// Code uses #ifdef NFC_ENABLED, so commenting (not setting to 0) is what disables it.
//#define NFC_ENABLED 1

// This causes issues in certain circumstances e.g. Play an album and let it auto play to related songs
bool writeContextToNfc = true;

// ----------------------------
// ----------------------------
// Standard Libraries
// ----------------------------
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_wifi.h>   // TASK-282: esp_wifi_set_ps (wifiPs A/B toggle)

// TASK-426 A/B control for the boot cascade's per-candidate retry
// (casRetryDisabled(), g_casRetryCookie, g_casRetryOff) moved into boot.cpp
// (M-SRCLAYOUT Stage E / TASK-471) — used exclusively by setup()'s WiFi
// cascade. cmdSet.cpp's `extern uint32_t g_casRetryCookie/g_casRetryOff`
// still resolve to the same externally-linked RTC_NOINIT_ATTR globals,
// wherever they're defined.

#include <FS.h>
#include "SPIFFS.h"
#include <time.h>     // configTime(), time(); needed for NTP sync at boot (time-001)
#include <esp_ota_ops.h>  // esp_ota_get_app_description() for serialdbg-001 boot banner (Arduino-ESP32 2.0.x; esp-idf 5.x renames this to <esp_app_desc.h>)
#include <esp_log.h>      // esp_log_level_set() for ADR-042 E1 HTTPClient log suppression
#include <esp_task_wdt.h> // esp_task_wdt_init() — extended timeout for dataTask TLS
#include <mbedtls/base64.h> // SERIAL_DEBUG `screendump` command — TFT readback encoding
// TASK-427: SD.h/SPI.h now also needed by SD_BOOT_MOUNT builds (cyd2usb_player) that
// don't define SERIAL_DEBUG — the boot mount itself moved out of the SERIAL_DEBUG gate.
// sd_diskio.h/ff.h/ffconf.h stay SERIAL_DEBUG-only: only the bring-up probes (`sdmbr`,
// `sdmem`) use them.
#if defined(SERIAL_DEBUG) || defined(SD_BOOT_MOUNT)
#include <SD.h>   // TASK-408: sdprobe bring-up probe, own VSPI bus (SD/FS is not otherwise linked)
#include <SPI.h>
#endif
#ifdef SERIAL_DEBUG
#include <sd_diskio.h>  // TASK-408: raw-sector access for `sdmbr` (below SD/FatFs)
#include <ff.h>   // TASK-408: FATFS/FIL sizes — the mount's real memory cost (see cmdSdMem)
#include "ffconf.h" // TASK-408: FF_VOLUMES — kept for anyone re-investigating the deferred
                    // live-mount corruption (see setup()'s sdProbeBootMount() comment)
#endif

// ----------------------------
// Additional Libraries
// ----------------------------

#include <SpotifyArduino.h>

// including a "spotify_server_cert" variable
// header is included as part of the SpotifyArduino libary
#include <SpotifyArduinoCert.h>

#include <ArduinoJson.h>

WiFiClientSecure client;

//------- Replace the following! ------

// Country code, including this is advisable
// SPOTIFY_MARKET moved to common_cyd build_flags so both .ino and
// spotifyTaskStorage.cpp see the same value (TASK-031b).
#ifndef SPOTIFY_MARKET
#define SPOTIFY_MARKET "IE"
#endif
//------- ---------------------- ------

// ----------------------------
// Internal includes
// ----------------------------
#include "refreshToken.h"
char clientId[200];
char clientSecret[200];

#include "spotifyDisplay.h"

#include "spotifyLogic.h"

#include "configFile.h"

#include "httpsDate.h"

#include "logSink.h"
#include "logServer.h"
#include "logHeartbeat.h"
#include "wifiDiag.h"
#include "perf.h"
#include "spotifyTask.h"
#ifdef SCREEN_LOG
#include "screenLog.h"
#endif
#include "winamp/vuMeter.h"   // TASK-501: WINAMP_DISPLAY is unconditionally defined
#include "util/mathUtil.h"
#include "util/timeFmt.h"   // WIRE2-G2/G3: shared 12h/24h + dateFmt helpers
#include "util/tftViewportRepair.h"   // TASK-359: heatmap rotated-text clip migrated onto the shared helper

// ----------------------------
// Memory overlay layout (Phase 1: declarative budget only — no buffers wired yet)
// ----------------------------
#include "gen/mem_layout.h"

// ----------------------------
// App shell
// ----------------------------
#include "appShell.h"
#include "shell/shellState.h"   // ShellState + shell::state() (M-SRCLAYOUT D3)
#include "shell/shellDispatch.h"   // resolvePlayerTap/isPlayerModeApp/shell::setBusy (M-SRCLAYOUT Stage E)
#include "shell/taskbar.h"
#include "dataTask.h"
#include "settingsStorage.h"

AppId currentAppId = AppId::Spotify;
// TASK-259/260/413: the "player" is one slot with three modes {Spotify | WebRadio |
// Player}. Tapping the taskbar icon while the player is already active cycles the
// mode and persists (resolvePlayerTap); returning to the player from another app
// restores the last-active one instead of always landing on Spotify. The mode is the
// persisted single source of truth g_settings.playerMode (TASK-260) — written by the
// eject toggles + taskbar cycle + Settings UI, read by resolvePlayerSlot. v2 boot
// (OQ-BOOT): cold-boot enters the persisted mode (see the boot-into-mode redirect at
// the end of setup()); auto-play is the webRadioAutoplay knob (WebRadio only).

// g_touchDebug now defined in touchDebugOverlay.cpp (M-SRCLAYOUT Stage E /
// TASK-471) — header is self-guarded, no need to double-gate the include.
#include "debug/touchDebugOverlay.h"

// ----------------------------
// Display Handling Code
// ----------------------------

// WINAMP_DISPLAY is checked first — every currently-building env defines it
// (cyd2usb_winamp and everything that extends it). The plain-CYD branch
// (YELLOW_DISPLAY, CheapYellowDisplay) was deleted in TASK-470 (ADR-061 D9
// step 4): no supported env selected it, and WinampDisplay no longer
// depends on that class after TASK-469's flatten.
#if defined WINAMP_DISPLAY

#include "winamp/winampDisplay.h"
WinampDisplay winampDisplay;
SpotifyDisplay *spotifyDisplay = &winampDisplay;

#elif defined MATRIX_DISPLAY
#include "matrixDisplay.h"
MatrixDisplay matrixDisplay;
SpotifyDisplay *spotifyDisplay = &matrixDisplay;

#endif
// ----------------------------

#ifdef NFC_ENABLED
#include "nfc.h"
#endif

// mb_heap_probe() (T_MB_PROBE_00 caps-split heap probe) moved into boot.cpp
// (M-SRCLAYOUT Stage E / TASK-471) — used exclusively from setup()'s boot
// milestones. Same SERIAL_DEBUG/MEMBUDGET_PHASE1-gated no-op contract.

// ── App dispatch (M-MULTIAPP, TASK-087c/d) ─────────────────────────────

#include "shell/appTable.h"   // COMPOSITION ROOT — the 13 App instances + g_apps[],
                             // moved verbatim, M-SRCLAYOUT Stage D (TASK-456)

// ── Shell state (M-SRCLAYOUT D3 / TASK-456) ───────────────────────────────
// The gesture flags (TASK-090f), the busy gate (M-TOUCH-UX TASK-115b), the
// first-launch table and the taskbar press-anchor all live in ShellState now —
// one owned struct in shell/shellState.cpp, reached through shell::state().
static constexpr unsigned long SHELL_BUSY_TIMEOUT_MS = 3000;

// activeError()/activeConnecting() now inline in shell/shellDispatch.h
// (M-SRCLAYOUT Stage E / TASK-471) — trivial and stateless, same reasoning as
// isPlayerModeApp().
namespace shell {
// Sets busy flag and immediately repaints only the active-slot indicator.
// `forced` (TASK-617) is true only for the debug `set shellBusy 1` path;
// see shellState.h's `busyForced` comment for why loop()'s primary
// auto-clear must skip it.
void setBusy(bool busy, bool forced) {
    shell::state().busy = busy;
    shell::state().busyForced = busy && forced;
    if (busy) shell::state().busySetMs = millis();
    renderActiveIndicator(tft, currentAppId,
                          winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                          busy, activeError(), activeConnecting());
}
}

// appIdForPlayerMode/resolvePlayerSlot/persistPlayerMode/resolvePlayerTap/
// shellTbPress/shellTbCancel/shellTbCommit/shellTbRelease/switchApp/
// appHandleInput/appTick all moved to appShell.cpp (M-SRCLAYOUT Stage E /
// TASK-471), pure move, bodies verbatim. persistPlayerMode/switchApp/
// appHandleInput/appTick are declared in appShell.h; resolvePlayerTap and
// the shellTb* group are declared in shell/shellDispatch.h.

// sdProbeBootMount()/sdMountAttempt()/sdReady() now defined in sd/sdMount.cpp
// (M-SRCLAYOUT Stage E / TASK-471) — included ahead of boot/boot.h, which
// calls sdProbeBootMount() from bootSequence().
#include "sd/sdMount.h"

// setup() now lives in boot/boot.cpp, its own translation unit
// (M-SRCLAYOUT Stage E / TASK-471). It keeps its exact name/signature —
// the Arduino/ESP-IDF runtime finds it by symbol at link time, it doesn't
// need to be textually present here. boot/boot.h (a bare `void setup();`
// declaration) is kept for discoverability but nothing includes it.

// cmdReconnect/kCmds[]/kNumCmds/the injection ring/drainInjectionQueue()/
// handleSerialCommands() all moved to debug/serialConsole/console.cpp
// (M-SRCLAYOUT Stage E / TASK-471) — declarations for the two loop()-called
// entry points below.
#include "debug/serialConsole/console.h"
#include "debug/bodWatch.h"   // TASK-557 supply telemetry

// TASK-451: an intentional reboot must not eat a deferred settings write.
// `tickDeferredSave(force)` only skips the retry INTERVAL — it cannot conjure
// heap, so on a reboot issued while audio is playing the retry fails exactly as
// the original save did (DUT-measured: prPollSec set during playback, rebooted,
// value gone, `deferred save landed` never printed). The engine has to go first:
// aeTeardownFile() returns the arena + Audio + pump, and THEN the 6 144 B
// document can be built. Harmless here by construction — the device is about to
// restart anyway, so stopping audio a few ms early costs nothing.
// A crash reset still loses a pending write; this covers the paths we control.
void prepareForReboot() {
#ifdef MEMBUDGET_PHASE1
  aeTeardownFile(/*connecting=*/false);
#endif
  SettingsStorage::tickDeferredSave(/*force=*/true);
}

void loop()
{
  // TASK-557: rate-limited brownout-latch read. The latch holds until cleared,
  // so a transient between iterations is still caught.
  bodWatchTick();

  // M-TESTARCH boot-window observability (TASK-561), phase 6 of 7. Emitted
  // once, from the first loop() iteration: this is the exact instant the
  // serial console becomes answerable, because handleSerialCommands() below
  // is its only pump in the whole firmware. Everything before this line —
  // SPIFFS, settings, display, the WiFi cascade, up to 5 s of NTP — happens
  // with the console deaf, which is why a fixed host-side sleep could never
  // be right. Phases 0-5 are emitted from setup() in boot/boot.cpp.
  static bool s_bootPhaseReadyEmitted = false;
  if (!s_bootPhaseReadyEmitted) {
    s_bootPhaseReadyEmitted = true;
    Serial.printf("[bootphase] %d %s\n", 6, "ready");
    bodWatchPoll("ready");
  }

  unsigned long _loopStart = millis();

  drainInjectionQueue();   // serialdbg-001: pops one injection step per iter (TASK-056e)
  aeDrainEof();            // TASK-410: audio_eof_mp3 flag, loopTask-only (ADR-059 D12)
  handleSerialCommands();
  logsink::serverLoop();
  heartbeat::tick();
  SettingsStorage::tickDeferredSave();   // TASK-429 (b): land a save the heap refused earlier
#ifdef SERIAL_DEBUG
  wifiDiag::poll();        // TASK-282: drain queued [beacon] gap lines
#endif
  // TASK-283: link supervisor — re-kick a wedged link (all builds). Suppressed
  // while Settings is foreground: WifiSection's scan flow owns the radio and
  // deliberately runs with auto-reconnect off.
  // TASK-436: that second clause was aspirational until TASK-436 — nothing in
  // WifiSection actually cleared auto-reconnect, so suppressing the supervisor
  // here bought nothing: the driver's own ~2.4s reconnect loop still refused
  // every esp_wifi_scan_start(). _startScan() now clears it for real.
  if (currentAppId != AppId::Settings) wifiDiag::superviseTick();
  // M-BOOT-UI §6 (TASK-364, ADR-055 decision 5): whole-session background
  // WiFi-reconnect status on the title marquee. Self-contained edge-trigger
  // (deliberately not wifiDiag::superviseTick()'s lastDiscMs anchor — a
  // fresh local anchor sidesteps that staleness class of bug for free, per
  // design doc §6 Q3). Co-located with, and gated by the exact same
  // condition as, superviseTick() above (X042, load-bearing per §6 Q4):
  // Settings already owns and repaints this whole screen region, so an
  // ungated override would blit stray marquee text over the Settings UI.
  // TASK-501: WINAMP_DISPLAY is unconditionally defined, so this block no
  // longer needs its own #ifdef.
  if (currentAppId != AppId::Settings) {
    static uint32_t s_wifiDownSinceMs = 0;
    // OQ5: proposed starting point, not DUT-pinned — VE/DUT to tune, a
    // single adjustable constant.
    constexpr uint32_t WIFI_DOWN_MARQUEE_THRESHOLD_MS = 10000;
    if (WiFi.status() != WL_CONNECTED) {
      if (s_wifiDownSinceMs == 0) {
        s_wifiDownSinceMs = millis();
      } else if (millis() - s_wifiDownSinceMs >= WIFI_DOWN_MARQUEE_THRESHOLD_MS) {
        winampDisplay.showWifiDownOverride();
      }
    } else if (s_wifiDownSinceMs != 0) {
      s_wifiDownSinceMs = 0;
      winampDisplay.clearWifiDownOverride();
    }
  }
  esp_task_wdt_reset();   // WDT safety: reset after serial+logsink, before appTick
#ifdef SCREEN_LOG
  { unsigned long _t = millis(); screenlog::tick(spotifyDisplay);
    perf::record("screenlog.tick", millis() - _t); }
#endif

  { unsigned long _t = millis(); appHandleInput(currentAppId);
    perf::record("display.input", millis() - _t); }
  esp_task_wdt_reset();   // WDT safety before appTick

  { unsigned long _t = millis(); appTick(currentAppId);
    perf::record("app.tick", millis() - _t); }

  // Primary busy clear: app reports work done (TASK-115d). Skipped for a
  // FORCED busy (TASK-617, `set shellBusy 1`): there is no real pending
  // async behind it, so this check would otherwise clear it on the very
  // next tick. A forced busy still falls through to the timeout fallback
  // below, and to explicit `set shellBusy 0` / `set injclear`.
  if (shell::state().busy && !shell::state().busyForced &&
      g_apps[(int)currentAppId] &&
      !g_apps[(int)currentAppId]->hasPendingAsync())
      shell::setBusy(false);
  // Fallback: auto-clear after timeout (safety net).
  if (shell::state().busy && millis() - shell::state().busySetMs > SHELL_BUSY_TIMEOUT_MS)
      shell::setBusy(false);

  // TASK-245 / ADR-046: repaint the active-slot indicator when the active app's
  // error OR connecting state changes asynchronously (e.g. a Spotify 403 arriving
  // between taps, or the first poll resolving boot amber → green). Edge-triggered
  // to avoid per-frame redraws; precedence error > busy/connecting > idle is
  // resolved inside renderActiveIndicator.
  {
    static bool  s_errShown  = false;
    static bool  s_connShown = false;
    static AppId s_errApp    = AppId::COUNT;
    bool err  = shell::activeError();
    bool conn = shell::activeConnecting();
    if (err != s_errShown || conn != s_connShown || currentAppId != s_errApp) {
      s_errShown  = err;
      s_connShown = conn;
      s_errApp    = currentAppId;
      renderActiveIndicator(tft, currentAppId, winampDisplay.tbScrollOffset(),
                            TASKBAR_APP_COUNT, shell::state().busy, err, conn);
    }
  }

  unsigned long _loopMs = millis() - _loopStart;
  perf::recordLoop(_loopMs);
  if (_loopMs > 50) {
    LOG_W("perf", "iter=%lums (worst path so far: %s:%ums)",
          _loopMs, perf::worstPathName(), (unsigned)perf::worstPathMs());
  }
}
