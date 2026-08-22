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

// 1. Cheap yellow display (Using TFT-eSPI library)
// #define YELLOW_DISPLAY

// 2. Matrix Displays (Like the ESP32 Trinity)
// #define MATRIX_DISPLAY

// 3. Winamp 2 skin renderer on CYD2USB (M3 — uses gen/ atlas)
// #define WINAMP_DISPLAY

// If no defines are set, it will default to CYD
#if !defined(YELLOW_DISPLAY) && !defined(MATRIX_DISPLAY) && !defined(WINAMP_DISPLAY)
#define YELLOW_DISPLAY // Default to Yellow Display for display type
#endif

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

// TASK-426 A/B control for the boot cascade's per-candidate retry. The thing
// under test only happens during setup(), so a plain serial toggle cannot reach
// it — the flag has to survive the reset that starts the run, which RTC slow
// memory does (across a SOFTWARE reset; an EN/RTS reset clears the RTC domain
// and was what silently made both arms run the control on the first attempt).
//
// Debug builds only, and cookie-guarded: RTC_NOINIT starts as garbage, so
// without the cookie a cold boot could disable the retry by accident — in a
// production build that would be a real, randomly-appearing regression. Prod
// compiles this to a constant false and always retries.
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

#include <FS.h>
#include "SPIFFS.h"
#include <time.h>     // configTime(), time(); needed for NTP sync at boot (time-001)
#include <esp_ota_ops.h>  // esp_ota_get_app_description() for serialdbg-001 boot banner (Arduino-ESP32 2.0.x; esp-idf 5.x renames this to <esp_app_desc.h>)
#include <esp_log.h>      // esp_log_level_set() for ADR-042 E1 HTTPClient log suppression
#include <esp_task_wdt.h> // esp_task_wdt_init() — extended timeout for dataTask TLS
#include <esp_heap_caps.h> // T_MB_PROBE_00: caps-split heap probes (TASK-261 Phase 0)
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
#ifdef WINAMP_DISPLAY
#include "winamp/vuMeter.h"
#endif
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
#include "taskbar/taskbar.h"
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

// WINAMP_DISPLAY is checked first so that envs which define it on top of
// YELLOW_DISPLAY (cyd2usb_winamp inherits common_cyd) pick the Winamp renderer.
#if defined WINAMP_DISPLAY

#include "winamp/winampDisplay.h"
WinampDisplay winampDisplay;
SpotifyDisplay *spotifyDisplay = &winampDisplay;

#elif defined YELLOW_DISPLAY

#include "cheapYellowLCD.h"
CheapYellowDisplay cyd;
SpotifyDisplay *spotifyDisplay = &cyd;

#elif defined MATRIX_DISPLAY
#include "matrixDisplay.h"
MatrixDisplay matrixDisplay;
SpotifyDisplay *spotifyDisplay = &matrixDisplay;

#endif
// ----------------------------

#ifdef NFC_ENABLED
#include "nfc.h"
#endif

// ── TASK-261/267 A-lite heap probes (caps-split diagnostic) ──
// The mb_arena itself ships in production (TASK-262 promotion — MEMBUDGET_PHASE1 now in
// cyd2usb_winamp; arena acquired JIT in WebRadioApp::_play(), released in ::suspend()).
// These verbose boot/CP probes are pure diagnostics, so they are SERIAL_DEBUG-gated —
// they do NOT ship in production (the call sites become no-ops, zero runtime cost).
//
// Arena size (TASK-261 Phase 2 DUT finding): 24 K covers Helix-only (9 structs,
// 23,216 B aligned) with 1.4 K slack; 40 K exhausted the DMA pool on first
// connecttohost(). InBuff (6.4 K) uses regular calloc (allocated once/session, no churn).
#if defined(MEMBUDGET_PHASE1) && defined(SERIAL_DEBUG)
// T_MB_PROBE_00: caps-split heap probe — fires at boot milestones so the DUT log
// captures them without needing a serial command.
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
void setBusy(bool busy) {
    shell::state().busy = busy;
    if (busy) shell::state().busySetMs = millis();
    renderActiveIndicator(tft, currentAppId,
                          winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                          busy, activeError(), activeConnecting());
}
}

// TASK-413 / ADR-059 D6: the three player-mode AppIds, and the reverse lookup.
// TASK-422: the argument is resolved through the compiled-in set first, so a
// persisted (or serial-injected) mode this build does not have lands on the first
// compiled-in mode's app instead of an app that was never instantiated.
static inline AppId appIdForPlayerMode(uint8_t mode) {
  switch ((PlayerMode)playerModeResolve(mode)) {
    case PlayerMode::WebRadio: return AppId::WebRadio;
    case PlayerMode::Player:   return AppId::LocalPlayer;
    default:                   return AppId::Spotify;
  }
}
// isPlayerModeApp() moved to shell/shellDispatch.h (M-SRCLAYOUT Stage E /
// TASK-471) — the debug console files need it too, now that they're their
// own translation units.

// TASK-259/260/413: the taskbar "player" slot (AppId::Spotify) restores whichever
// player mode (Spotify | WebRadio | Player) was last active — read from the
// persisted setting. WebRadio/LocalPlayer are eject-only / excluded from the
// taskbar, so a taskbar tap only ever surfaces AppId::Spotify here; we redirect to
// the persisted mode's app.
static AppId resolvePlayerSlot(AppId tapped) {
  if (tapped != AppId::Spotify) return tapped;
  return appIdForPlayerMode(g_settings.playerMode);
}

// TASK-260 §4: persist the player mode, immediate-save with an unchanged-value skip
// (flash-wear). Called from the eject toggles in both directions (the Settings UI
// writes g_settings.playerMode + saveSettings() directly via its own cycle handler).
void persistPlayerMode(uint8_t mode) {
  if (g_settings.playerMode == mode) return;   // unchanged-value skip
  g_settings.playerMode = mode;
  SettingsStorage::save();
}

// TASK-413 / ADR-059 D6 (amended DEV-1): the player slot's taskbar tap has a
// second meaning no other slot has — restore the persisted mode when tapped from
// another app, but CYCLE (Spotify -> WebRadio -> Player -> Spotify) and persist
// when tapped while the player is already active. switchApp() early-returns on
// same-app, and the two dispatch sites that can land a tap on this slot
// (shellTbRelease() below, and cmdTap()'s SERIAL_DEBUG "tap" injection) guard
// same-app differently — so this decision lives in ONE shared helper called from
// both, not duplicated into either. Non-player-slot taps pass through unchanged.
AppId resolvePlayerTap(AppId tapped, bool playerAlreadyActive) {
  if (tapped != AppId::Spotify) return tapped;
  if (!playerAlreadyActive) return resolvePlayerSlot(tapped);
  // TASK-422: iterate the compiled-in set, not a hardcoded 0->1->2. On a
  // single-mode build playerModeNext() returns the current mode, persistPlayerMode()
  // skips the unchanged write and switchApp() early-returns on same-app — so tapping
  // the active player slot is a genuine no-op rather than a repaint or a save.
  uint8_t next = playerModeNext(g_settings.playerMode);
  persistPlayerMode(next);
  return appIdForPlayerMode(next);
}

// cmdPlayerCycle moved to debug/serialConsole/console.cpp (M-SRCLAYOUT
// Stage E / TASK-471), alongside kCmds[] which is its only caller.

// ── Taskbar tap feedback (M-TASKBAR-FEEDBACK / TASK-279) ──────────────────
// Single shared helper set [VE-3-1 + DEV-3-6]: paint + stable-prefix log live here,
// invoked from BOTH dispatch sites (appHandleInput and drainInjectionQueue) so the
// injected path the measurement plan depends on cannot drift from production.
// Press-anchored commit [DEV-3-2]: the slot captured at Press is also the slot the
// tap commits — release-y is never re-resolved (resistive-panel jitter inside the
// dead zone could otherwise highlight slot A and switch slot B).
// (the two press-anchor fields are ShellState::tbPressedSlot / ::tbPressedApp)

// F-a: pressed-slot highlight, same loop iteration as the Press sample.
void shellTbPress(int y) {
  int slot = y / TASKBAR_SLOT_H;
  if (slot < 0 || slot >= TASKBAR_SLOT_COUNT) return;  // y is 0..239 → 0..5, defensive
  shell::state().tbPressedSlot = slot;
  shell::state().tbPressedApp  = (winampDisplay.tbScrollOffset() + slot) % TASKBAR_APP_COUNT;
  renderTaskbarSlot(tft, slot, currentAppId,
                    winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                    shell::state().busy, shell::activeError(), shell::activeConnecting(),
                    /*pressed=*/true);
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] tb-press slot=%d\n", slot);
#endif
}

// F-a: cancel the highlight — scroll-start (dead zone exceeded) or a tap that
// resolves to the already-active app. Idempotent.
void shellTbCancel() {
  if (shell::state().tbPressedSlot < 0) return;
  renderTaskbarSlot(tft, shell::state().tbPressedSlot, currentAppId,
                    winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                    shell::state().busy, shell::activeError(), shell::activeConnecting(),
                    /*pressed=*/false);
  shell::state().tbPressedSlot = -1;
  shell::state().tbPressedApp  = -1;
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] tb-press-cancel\n");
#endif
}

// F-b: transient amber bar on the tapped (press-anchored) slot, painted BEFORE
// switchApp()'s heavy work — never a reverse app→slot lookup [QM-3-1]:
// resolvePlayerSlot() can return WebRadio, which deliberately has no slot (LL-085).
// switchApp()'s final renderTaskbar overwrites it with the real state.
static void shellTbCommit(int slot) {
  if (slot < 0 || slot >= TASKBAR_SLOT_COUNT) return;
  tft.fillRect(TASKBAR_X, slot * TASKBAR_SLOT_H, 3, TASKBAR_SLOT_H, TASKBAR_BUSY_COLOR);
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] tb-commit slot=%d\n", slot);
#endif
}

// Shared taskbar-release resolution — both dispatch sites call this so tap commit,
// press-anchoring, and the feedback paints stay identical [VE-3-1].
void shellTbRelease(int releaseY) {
  const int pressedSlot = shell::state().tbPressedSlot;
  const int pressedApp  = shell::state().tbPressedApp;
  int appIdx = (int)currentAppId;
  if (winampDisplay.tbGestureEnd(releaseY, TASKBAR_APP_COUNT, &appIdx)) {
    if (pressedApp >= 0) appIdx = pressedApp;  // press-anchored commit [DEV-3-2]
    // TASK-413: cycle when the player slot is tapped while already active, restore
    // otherwise — resolvePlayerTap() owns both decisions (ADR-059 D6).
    AppId target = resolvePlayerTap(static_cast<AppId>(appIdx), isPlayerModeApp(currentAppId));
    if (target != currentAppId) {
      shell::state().tbPressedSlot = -1;
      shell::state().tbPressedApp  = -1;
      shellTbCommit(pressedSlot);
      switchApp(target);
      return;
    }
  }
  shellTbCancel();  // no-switch tap or scroll release: restore if still highlighted
}

void switchApp(AppId next) {
  if (next == currentAppId) return;
  const unsigned long t0 = millis();  // TASK-279 (L-d): per-phase instrumentation
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] leaving %d  heap=%lu maxAlloc=%lu minFree=%lu\n",
    (int)currentAppId,
    (unsigned long)ESP.getFreeHeap(),
    (unsigned long)ESP.getMaxAllocHeap(),
    (unsigned long)ESP.getMinFreeHeap());
  const int fromApp = (int)currentAppId;
#endif
  if (g_apps[(int)currentAppId]) g_apps[(int)currentAppId]->suspend();
  shell::setBusy(false);   // clear before new taskbar paint (TASK-115e)
  const unsigned long tSuspend = millis();
  tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
  const unsigned long tWipe = millis();
  if (next == AppId::Settings) shell::state().previous = currentAppId;
  currentAppId = next;
  // TASK-260: the player mode is NOT tracked here — it is written only by the deliberate
  // eject toggles + Settings UI (persistPlayerMode / _cyclePlayer). Tracking navigation
  // would clobber the persisted mode at boot, since v1 boots to the Spotify view.
  // TASK-264 (Q3-a): drop Spotify TLS when WebRadio is active (reclaims ~50 K arena).
  // Non-blocking — setWebRadioActive() only sets flags, never calls tlsYield().
  // TASK-448: LocalPlayer qualifies for the identical reason WebRadio does —
  // it is a non-Spotify player that owns the audio path and the arena, so
  // Spotify's TLS must stay down while it is foreground. Without this, the
  // boot switchApp(AppId::LocalPlayer) below immediately CLEARS the idle flag
  // that begin(startIdle=true) had just seeded, and the task self-issues its
  // first ACT_POLL ~5 s later anyway — measured on cyd2usb_winamp_debug:
  // begin ok startIdle=1, then `Refresh of the Access token is due` and
  // lfbDma 65524 -> maxAlloc=41k. The begin() gate alone is NOT sufficient;
  // this predicate is the durable half of the same decision.
#ifndef DISABLE_SPOTIFY
  spotifyTask::setWebRadioActive(next == AppId::WebRadio ||
                                 next == AppId::LocalPlayer);
#endif
  if (g_apps[(int)next]) {
    if (!shell::state().launched[(int)next]) {
      shell::state().launched[(int)next] = true;
      g_apps[(int)next]->init();
    } else {
      g_apps[(int)next]->resume();
    }
  }
  const unsigned long tInit = millis();
#ifdef SERIAL_DEBUG
  // Keep this line's position (before renderTaskbar): the E0/E1 tap-to-switch-committed
  // clock is defined against it (M-TASKBAR-FEEDBACK §Measurement plan).
  Serial.printf("[shell] entered %d  heap=%lu maxAlloc=%lu minFree=%lu\n",
    (int)next,
    (unsigned long)ESP.getFreeHeap(),
    (unsigned long)ESP.getMaxAllocHeap(),
    (unsigned long)ESP.getMinFreeHeap());
#endif
  renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
  const unsigned long tEnd = millis();
  perf::record("shell.switch", tEnd - t0);  // 10th of MAX_PATHS=10 — see perf.h budget
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] switch %d->%d suspend=%lums wipe=%lums init=%lums "
                "taskbar=%lums total=%lums\n",
                fromApp, (int)next, tSuspend - t0, tWipe - tSuspend, tInit - tWipe,
                tEnd - tInit, tEnd - t0);
#endif
}

void appHandleInput(AppId) {
  bool touched = ts.touched();
  if (touched) {
    CYD28_TS_Point p = ts.getPointScaled();
    spotifyTask::resetBackoff();
    if (p.x >= TASKBAR_X) {
      if (shell::state().inGesture && g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, shell::state().lastTouchX, shell::state().lastTouchY);
        shell::state().inGesture = false;
        if (!shell::state().busy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
      }
      shell::state().lastTouchY = p.y;  // track for release
      if (winampDisplay.tbIsDragging()) {
        if (winampDisplay.tbGestureContinue(p.y, TASKBAR_APP_COUNT))
          renderTaskbar(tft, currentAppId,
                        winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                        false, shell::activeError(), shell::activeConnecting());
        // TASK-279 (F-a): scroll started (dead zone exceeded) → cancel the press
        // highlight. tbIsScrolling() is the DEV-3-1 accessor; idempotent after
        // the first cancel.
        if (winampDisplay.tbIsScrolling()) shellTbCancel();
      } else {
        winampDisplay.tbGesturePress(p.y);
        shellTbPress(p.y);  // TASK-279 (F-a): highlight in the same iteration
      }
      return;
    }
    // TASK-384: a pure-navigation tap bypasses the busy gate (see
    // isNavigationTap()'s doc comment) — cooldown debounce still applies.
    bool navTapBypass = g_apps[(int)currentAppId] &&
                         g_apps[(int)currentAppId]->isNavigationTap(p.x, p.y);
    if (!shell::state().inGesture &&
        (millis() <= shell::state().cooldownMs ||
         (shell::state().busy && !navTapBypass))) return;
    shell::state().lastTouchX = p.x; shell::state().lastTouchY = p.y;
    if (!shell::state().inGesture) {
      shell::state().inGesture = true;
      if (g_apps[(int)currentAppId]) {
        bool consumed = g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Press, p.x, p.y);
        if (consumed) shell::state().cooldownMs = millis() + 200;
        if (!shell::state().busy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
#ifdef TOUCH_DEBUG_OVERLAY
        g_touchDebug.onTouch(p.x, p.y);
#endif
      }
    } else {
      if (g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(TouchPhase::Move, p.x, p.y);
        if (!shell::state().busy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
#ifdef TOUCH_DEBUG_OVERLAY
        g_touchDebug.onTouch(p.x, p.y);
#endif
      }
    }
  } else {
    if (winampDisplay.tbIsDragging()
#ifdef SERIAL_DEBUG
        && !winampDisplay._injectingDrag
#endif
    ) {
      shellTbRelease(shell::state().lastTouchY);  // TASK-279: shared commit path [VE-3-1]
      shell::state().cooldownMs = millis() + 300;
    } else if (shell::state().inGesture) {
      shell::state().inGesture = false;
      if (g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, shell::state().lastTouchX, shell::state().lastTouchY);
        if (!shell::state().busy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
      }
      shell::state().cooldownMs = millis() + 200;
    }
  }
}

void appTick(AppId id) {
  g_ledFlow.tick();
  g_backlight.tick();   // WIRE2-G5: auto-brightness in every app, not just Settings→Display
  g_keyboard.tick();
  if (g_apps[(int)id]) g_apps[(int)id]->tick();
}

// sdProbeBootMount()/sdMountAttempt()/sdReady() now defined in sd/sdMount.cpp
// (M-SRCLAYOUT Stage E / TASK-471) — included ahead of boot/boot.h, which
// calls sdProbeBootMount() from bootSequence().
#include "sd/sdMount.h"

#include "boot/boot.h"   // setup() — moved verbatim, M-SRCLAYOUT Stage C (TASK-455)

// cmdReconnect/kCmds[]/kNumCmds/the injection ring/drainInjectionQueue()/
// handleSerialCommands() all moved to debug/serialConsole/console.cpp
// (M-SRCLAYOUT Stage E / TASK-471) — declarations for the two loop()-called
// entry points below.
#include "debug/serialConsole/console.h"

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
#ifdef WINAMP_DISPLAY
  // M-BOOT-UI §6 (TASK-364, ADR-055 decision 5): whole-session background
  // WiFi-reconnect status on the title marquee. Self-contained edge-trigger
  // (deliberately not wifiDiag::superviseTick()'s lastDiscMs anchor — a
  // fresh local anchor sidesteps that staleness class of bug for free, per
  // design doc §6 Q3). Co-located with, and gated by the exact same
  // condition as, superviseTick() above (X042, load-bearing per §6 Q4):
  // Settings already owns and repaints this whole screen region, so an
  // ungated override would blit stray marquee text over the Settings UI.
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
#endif
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

  // Primary busy clear: app reports work done (TASK-115d).
  if (shell::state().busy && g_apps[(int)currentAppId] &&
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
