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
#include "taskbar/taskbar.h"
#include "dataTask.h"
#include "settingsStorage.h"

AppId currentAppId = AppId::Spotify;
static AppId g_previousAppId = AppId::Spotify;
// TASK-259/260/413: the "player" is one slot with three modes {Spotify | WebRadio |
// Player}. Tapping the taskbar icon while the player is already active cycles the
// mode and persists (resolvePlayerTap); returning to the player from another app
// restores the last-active one instead of always landing on Spotify. The mode is the
// persisted single source of truth g_settings.playerMode (TASK-260) — written by the
// eject toggles + taskbar cycle + Settings UI, read by resolvePlayerSlot. v2 boot
// (OQ-BOOT): cold-boot enters the persisted mode (see the boot-into-mode redirect at
// the end of setup()); auto-play is the webRadioAutoplay knob (WebRadio only).

#ifdef TOUCH_DEBUG_OVERLAY
#include "debug/touchDebugOverlay.h"
TouchDebugOverlay g_touchDebug;
#endif

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

bool g_appLaunched[(int)AppId::COUNT] = {};

// ── SpotifyApp (TASK-090d) ─────────────────────────────────────────────
// TASK-496/467: WINAMP_DISPLAY is defined by every buildable env
// (ADR-061 D8 demoted the one env that didn't, [env:cyd2usb], to a
// non-building base section) — the #ifdef here was unconditionally
// true and has been removed.
#include "apps/spotifyApp.h"
static SpotifyApp g_SpotifyApp;

// ── ClockApp (M-CLOCK-STYLES) ─────────────────────────────────────────
#include "clockApp.h"
static ClockApp g_ClockApp;

// ── VE instrumentation statics (consumed by SERIAL_DEBUG cmdGet) ─────────────
static bool s_wxDataReady   = false;   // set true when WeatherApp receives first fetch
static bool s_cxDataReady   = false;   // set true when CryptoApp receives first fetch
static int  s_golAliveCount = -1;      // -1 = GoL never ticked; ≥0 = last alive count

#include "apps/matrixApp.h"
static MatrixApp g_MatrixApp;

#include "apps/weatherApp.h"
static WeatherApp g_WeatherApp;

#include "apps/cryptoApp.h"
static CryptoApp g_CryptoApp;

#include "apps/lifeApp.h"
static LifeApp g_LifeApp;

#include "apps/settingsApp.h"
static SettingsApp g_SettingsApp;
LedFlow      g_ledFlow;
BacklightFlow g_backlight;   // WIRE2-G5: backlight owner (ADR-050)
KeyboardWidget g_keyboard;
SPickerList g_countryPicker;   // M-COUNTRY-PICKER: shared modal country picker (settingsWidgets.h)
#ifdef SERIAL_DEBUG
static bool settingsDbgGet(const char* v, char* b, int l) { return g_SettingsApp.dbgGet(v, b, l); }
#endif

#include "apps/stockApp.h"
static StockApp g_StockApp;
static bool stockDbgGet(const char* v, char* b, int l) { return g_StockApp.dbgGet(v, b, l); }
static bool stockDbgSet(const char* v, const char* val) { return g_StockApp.dbgSet(v, val); }

#include "aquarium/aquariumApp.h"
static AquariumApp g_AquariumApp;

#include "teletextApp.h"
static TeletextApp g_TeletextApp;
static bool teletextDbgGet(const char* v, char* b, int l) { return g_TeletextApp.dbgGet(v, b, l); }
static bool teletextDbgSet(const char* v, const char* val) { return g_TeletextApp.dbgSet(v, val); }

#include "planeRadarApp.h"
static PlaneRadarApp g_PlaneRadarApp;
static bool planeRadarDbgGet(const char* v, char* b, int l) { return g_PlaneRadarApp.dbgGet(v, b, l); }
static bool planeRadarDbgSet(const char* v, const char* val) { return g_PlaneRadarApp.dbgSet(v, val); }

// TASK-496/467: WINAMP_DISPLAY is unconditionally defined (see note above); #ifdef removed.
#include "webRadioApp.h"
static WebRadioApp g_WebRadioApp;
static bool webRadioDbgGet(const char* v, char* b, int l) { return g_WebRadioApp.dbgGet(v, b, l); }
static bool webRadioDbgSet(const char* v, const char* val) { return g_WebRadioApp.dbgSet(v, val); }

#include "localPlayerApp.h"
static LocalPlayerApp g_LocalPlayerApp;   // TASK-413: placeholder, real UI is TASK-415+

#ifdef SERIAL_DEBUG
static bool matrixDbgGet(const char* v, char* b, int l)   { return g_MatrixApp.dbgGet(v, b, l); }
static bool lifeDbgGet(const char* v, char* b, int l)     { return g_LifeApp.dbgGet(v, b, l); }
static bool cryptoDbgGet(const char* v, char* b, int l)   { return g_CryptoApp.dbgGet(v, b, l); }
static bool aquariumDbgGet(const char* v, char* b, int l) { return g_AquariumApp.dbgGet(v, b, l); }
#endif

// ── App registry + shell gesture state (TASK-090f) ────────────────────

// TASK-496/467: WINAMP_DISPLAY is unconditionally defined (see note above);
// the {} else-branch (populated by no buildable env) is removed.
App* g_apps[(int)AppId::COUNT] = {
#define APP_X(Name, icon, cfg, disp) &g_##Name##App,
#include "appRegistry.h"
#undef APP_X
};

static bool          s_inGesture  = false;
static int           s_lastTouchX = 0, s_lastTouchY = 0;
static unsigned long s_cooldownMs = 0;

// ── Shell busy state (M-TOUCH-UX TASK-115b) ───────────────────────────────
static bool          g_shellBusy      = false;
static unsigned long g_shellBusySetMs = 0;
static constexpr unsigned long SHELL_BUSY_TIMEOUT_MS = 3000;

namespace shell {
// TASK-245 / ADR-046: error state of the currently-active app — drives the red
// active-bar (precedence error > busy/connecting > idle). Owned by the app
// instance, so it survives app switch and is re-read on every repaint.
inline bool activeError() {
    return g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->hasError();
}
// TASK-245 amendment / ADR-046: connecting state of the active app — amber bar
// until the app's first data result resolves (boot reads amber, not green).
inline bool activeConnecting() {
    return g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->isConnecting();
}
// Sets busy flag and immediately repaints only the active-slot indicator.
void setBusy(bool busy) {
    g_shellBusy = busy;
    if (busy) g_shellBusySetMs = millis();
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
static inline bool isPlayerModeApp(AppId id) {
  return id == AppId::Spotify || id == AppId::WebRadio || id == AppId::LocalPlayer;
}

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
static AppId resolvePlayerTap(AppId tapped, bool playerAlreadyActive) {
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

#ifdef SERIAL_DEBUG
// ── M-TESTBASE §8: the mode-cycle OPERATION, decoupled from its hit-surface ──
// The gesture that cycles player mode has moved once already (eject -> taskbar
// slot, TASK-413/414) and the move silently broke the harness once and a design
// document once, because both bound to the GESTURE when they meant the
// OPERATION. Tests call this; exactly one test (T_PMT_00) asserts that the
// surface named by `get playerBind` still reaches it.
//
// Deliberately calls the SAME shared helper both production dispatch sites call
// (ADR-059 D6 amendment) rather than re-deriving the cycle — a second cycle path
// is the TASK-406 defect class this decision exists to prevent.
static void cmdPlayerCycle(const char *) {
  const uint8_t before = g_settings.playerMode;
  AppId target = resolvePlayerTap(AppId::Spotify, isPlayerModeApp(currentAppId));
  switchApp(target);
  Serial.printf("{\"ok\":true,\"cmd\":\"playerCycle\","
                "\"from\":%u,\"to\":%u,\"appId\":%d,\"last\":true}\n",
                (unsigned)before, (unsigned)g_settings.playerMode, (int)target);
}
#endif

// ── Taskbar tap feedback (M-TASKBAR-FEEDBACK / TASK-279) ──────────────────
// Single shared helper set [VE-3-1 + DEV-3-6]: paint + stable-prefix log live here,
// invoked from BOTH dispatch sites (appHandleInput and drainInjectionQueue) so the
// injected path the measurement plan depends on cannot drift from production.
// Press-anchored commit [DEV-3-2]: the slot captured at Press is also the slot the
// tap commits — release-y is never re-resolved (resistive-panel jitter inside the
// dead zone could otherwise highlight slot A and switch slot B).
static int s_tbPressedSlot = -1;  // visible slot highlighted at Press; -1 = none
static int s_tbPressedApp  = -1;  // press-anchored app index (highlight == commit)

// F-a: pressed-slot highlight, same loop iteration as the Press sample.
static void shellTbPress(int y) {
  int slot = y / TASKBAR_SLOT_H;
  if (slot < 0 || slot >= TASKBAR_SLOT_COUNT) return;  // y is 0..239 → 0..5, defensive
  s_tbPressedSlot = slot;
  s_tbPressedApp  = (winampDisplay.tbScrollOffset() + slot) % TASKBAR_APP_COUNT;
  renderTaskbarSlot(tft, slot, currentAppId,
                    winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                    g_shellBusy, shell::activeError(), shell::activeConnecting(),
                    /*pressed=*/true);
#ifdef SERIAL_DEBUG
  Serial.printf("[shell] tb-press slot=%d\n", slot);
#endif
}

// F-a: cancel the highlight — scroll-start (dead zone exceeded) or a tap that
// resolves to the already-active app. Idempotent.
static void shellTbCancel() {
  if (s_tbPressedSlot < 0) return;
  renderTaskbarSlot(tft, s_tbPressedSlot, currentAppId,
                    winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                    g_shellBusy, shell::activeError(), shell::activeConnecting(),
                    /*pressed=*/false);
  s_tbPressedSlot = -1;
  s_tbPressedApp  = -1;
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
static void shellTbRelease(int releaseY) {
  const int pressedSlot = s_tbPressedSlot;
  const int pressedApp  = s_tbPressedApp;
  int appIdx = (int)currentAppId;
  if (winampDisplay.tbGestureEnd(releaseY, TASKBAR_APP_COUNT, &appIdx)) {
    if (pressedApp >= 0) appIdx = pressedApp;  // press-anchored commit [DEV-3-2]
    // TASK-413: cycle when the player slot is tapped while already active, restore
    // otherwise — resolvePlayerTap() owns both decisions (ADR-059 D6).
    AppId target = resolvePlayerTap(static_cast<AppId>(appIdx), isPlayerModeApp(currentAppId));
    if (target != currentAppId) {
      s_tbPressedSlot = -1;
      s_tbPressedApp  = -1;
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
  if (next == AppId::Settings) g_previousAppId = currentAppId;
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
    if (!g_appLaunched[(int)next]) {
      g_appLaunched[(int)next] = true;
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
      if (s_inGesture && g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, s_lastTouchX, s_lastTouchY);
        s_inGesture = false;
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
      }
      s_lastTouchY = p.y;  // track for release
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
    if (!s_inGesture && (millis() <= s_cooldownMs || (g_shellBusy && !navTapBypass))) return;
    s_lastTouchX = p.x; s_lastTouchY = p.y;
    if (!s_inGesture) {
      s_inGesture = true;
      if (g_apps[(int)currentAppId]) {
        bool consumed = g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Press, p.x, p.y);
        if (consumed) s_cooldownMs = millis() + 200;
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
#ifdef TOUCH_DEBUG_OVERLAY
        g_touchDebug.onTouch(p.x, p.y);
#endif
      }
    } else {
      if (g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(TouchPhase::Move, p.x, p.y);
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
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
      shellTbRelease(s_lastTouchY);  // TASK-279: shared commit path [VE-3-1]
      s_cooldownMs = millis() + 300;
    } else if (s_inGesture) {
      s_inGesture = false;
      if (g_apps[(int)currentAppId]) {
        g_apps[(int)currentAppId]->handleInput(
            TouchPhase::Release, s_lastTouchX, s_lastTouchY);
        if (!g_shellBusy && g_apps[(int)currentAppId]->hasPendingAsync())
          shell::setBusy(true);
      }
      s_cooldownMs = millis() + 200;
    }
  }
}

void appTick(AppId id) {
  g_ledFlow.tick();
  g_backlight.tick();   // WIRE2-G5: auto-brightness in every app, not just Settings→Display
  g_keyboard.tick();
  if (g_apps[(int)id]) g_apps[(int)id]->tick();
}

#ifdef SD_BOOT_MOUNT
static void sdProbeBootMount();  // TASK-408: defined ahead of the SERIAL_DEBUG command
                                  // block (TASK-427), called from setup()
#endif

#include "boot/boot.h"   // setup() — moved verbatim, M-SRCLAYOUT Stage C (TASK-455)

// ── serial command dispatcher (serialdbg-001, TASK-056c) ───────────────
// Table-driven replacement for the old TASK-053e strcmp chain. Non-debug
// commands (reconnect, the boot-time `[boot]` line) are always compiled
// in per ADR-021 Decision 4; SERIAL_DEBUG-gated commands (tap, drag, get,
// set, info, help) are added by sub-tasks d-i.
//
// Output convention: every command emits exactly one JSON object on one
// '\n'-terminated line. Hosts parse with `json.loads(line)`.

static void cmdReconnect(const char *) {
  spotifyTask::resetTls();
  spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
  Serial.println("{\"ok\":true,\"cmd\":\"reconnect\"}");
}

// 4-field struct; help + args iterated by cmdHelp (TASK-056i).
typedef void (*cmd_fn)(const char *args);
struct SerialCmd {
  const char *name;
  cmd_fn      fn;
  const char *help;
  const char *args;
};

// TASK-056e: touch-injection ring buffer (SERIAL_DEBUG only).
// drainInjectionQueue() pops one step per loop() iteration — no delay().
// cmdDrag fills the queue and returns; JSON response emitted on release step.
#ifdef SERIAL_DEBUG
struct InjectionStep { int sx, sy; bool release; };
static InjectionStep s_injectQueue[64];
static int s_injectHead = 0, s_injectTail = 0;
static bool s_dragPending = false;
static bool s_injectIsFirst = false;  // first non-release item → Press, rest → Move
static int s_pendingDragX1, s_pendingDragY1,
           s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps;
static int s_injectTotal = 0;  // total steps for LOG_D %d/%d
// TASK-277 (VE-1-1/DEV-1-2): the release step dispatches at the LAST sample's
// coordinates, not (0,0) — otherwise a drag's Release lands outside every
// hit-test region and gesture-end logic sees garbage geometry.
static int s_lastInjectX = 0, s_lastInjectY = 0;
// TASK-277 (VE-1-3): bare `release` command marks its sentinel so the drain
// emits {"cmd":"release"} instead of the drag JSON.
static bool s_bareRelease = false;

// Forward declarations so kCmds[] can reference the handlers before they
// are defined (they must appear after kCmds[] to see kNumCmds).
static void cmdTap(const char *);
static void cmdDrag(const char *);
static void cmdRelease(const char *);
static void cmdTick(const char *);
static void cmdGet(const char *);
static void cmdSet(const char *);
static void cmdSwitchApp(const char *);
static void cmdPlayerCycle(const char *);
static void cmdInfo(const char *);
static void cmdScreenDump(const char *);
static void cmdColorProbe(const char *);
static void cmdSdProbe(const char *);
static void cmdSdCycle(const char *);
static void cmdSdMem(const char *);
static void cmdSdMount(const char *);
static void cmdSdUmount(const char *);
static void cmdSdClean(const char *);
static void cmdSdWrite(const char *);
static void cmdSdLs(const char *);
static void cmdSdRead(const char *);
static void cmdSdMbr(const char *);
static void cmdSdMkdir(const char *);
static void cmdSdPut(const char *);
static void cmdHelp(const char *);
static void cmdReboot(const char *);
static void cmdAdvance(const char *);
#endif

static const SerialCmd kCmds[] = {
  { "reconnect", cmdReconnect, "TLS reset + force poll", "" },
#ifdef SERIAL_DEBUG
  { "tap",  cmdTap,  "inject touch point",              "<x> <y>"                            },
  { "drag", cmdDrag, "inject touch drag (queue-drain)", "<x1> <y1> <x2> <y2> <steps> [hold]" },
  { "release", cmdRelease, "end a held injected gesture", ""                                 },
  { "tick", cmdTick, "inject synthetic scroll ticks",   "[n=1] [dtMs=20]"                    },
  { "get",  cmdGet,  "read internal state",             "<snapshot|backoff|heap|stacks|cooldown|shellCooldown>"    },
  { "set",  cmdSet,  "write debug state",               "<backoff|cooldown> <val>"            },
  { "switchApp", cmdSwitchApp, "switch active app by id", "<appId 0..8>"                      },
  { "playerCycle", cmdPlayerCycle, "M-TESTBASE: cycle player mode via resolvePlayerTap (surface-independent)", "" },
  { "info", cmdInfo, "git+elf+build+snapshot summary",  ""                                   },
  { "screendump", cmdScreenDump, "read back TFT GRAM, base64 RGB565 bands", "[x=0] [y=0] [w=320] [h=240]" },
  { "colorprobe", cmdColorProbe, "TASK-340: fillRect/pushRect known values, readRect them back", "" },
  { "sdprobe", cmdSdProbe, "TASK-408: SD card mount/heap/LFN/listDir/read-bench probe", "[reads=5000]" },
  { "sdcycle", cmdSdCycle, "TASK-408 T_SD_08: N live mount/unmount cycles, heap drift", "[cycles=20]" },
  { "sdmem", cmdSdMem, "TASK-408: FATFS ctx sizing + contiguous-calloc ladder", "" },
  { "sdmount", cmdSdMount, "TASK-408: live mount attempt at N slots, optional SPI Hz", "[maxFiles] [freqHz]" },
  { "sdumount", cmdSdUmount, "TASK-408: unmount, report heap actually returned", "" },
  { "sdclean", cmdSdClean, "TASK-408: delete sdprobe fixtures (/probelist, /probebench.bin)", "" },
  { "sdwrite", cmdSdWrite, "TASK-408: isolated sequential write of N 512B chunks", "[chunks=64] [heapCheckEvery=0]" },
  { "sdls", cmdSdLs, "TASK-408: list a directory with sizes", "[dir=/] [q=quiet | n=quiet,no stat]" },
  { "sdmbr", cmdSdMbr, "TASK-408: raw sector 0 / partition table / volume ID (no mount needed)", "" },
  { "sdread", cmdSdRead, "TASK-408: read-only benchmark against an existing file", "<reads> <path>" },
  { "sdmkdir", cmdSdMkdir, "TASK-415: create a directory (test fixtures)", "<path>" },
  { "sdput", cmdSdPut, "TASK-415: write/append <=90 B of base64 to a file (test fixtures)", "<w|a> <base64|-> <path>" },
  { "help",   cmdHelp,   "list commands",                   ""                                   },
  { "reboot", cmdReboot, "software reset (ESP.restart)",   ""                                   },
  { "advance", cmdAdvance, "TASK-418: step the play-order engine, no audio (ADR-059 D12)", "<next|prev>" },
#endif
};
static constexpr int kNumCmds = sizeof(kCmds) / sizeof(kCmds[0]);

// TASK-056e: drain one injection step per loop() iteration.
static inline void drainInjectionQueue() {
#ifdef SERIAL_DEBUG
  if (s_injectHead == s_injectTail) return;
  InjectionStep &step = s_injectQueue[s_injectHead % 64];
#ifdef WINAMP_DISPLAY
  if (step.release) {
    if (winampDisplay.tbIsDragging()) {
      // Taskbar drag release — TASK-279: same shared commit path as production
      // [VE-3-1]. TASK-280: also set the same 300 ms post-gesture cooldown
      // appHandleInput() sets after its shellTbRelease() call, so the injected
      // path can't double-fire faster than a real gesture could.
      shellTbRelease(s_lastTouchY);
      s_cooldownMs = millis() + 300;
      renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
    } else {
      // TASK-277 reroute (VE-1-1 blocker + DEV-1-2): dispatch to the ACTIVE
      // app's handleInput at the last sample's coordinates — previously
      // hardwired to winampDisplay.handleWinampInput(Release, 0, 0), so an
      // injected WebRadio drag delivered Press/Move to one machine and
      // Release to another (gesture never ended). Documented behaviour
      // deltas: (i) injected Releases now pass SpotifyApp's eject intercept
      // with real coords; (ii) every app now sees injected Releases.
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(TouchPhase::Release,
                                               s_lastInjectX, s_lastInjectY);
    }
    winampDisplay._injectingDrag = false;
    s_dragPending = false;
    if (s_bareRelease) {
      s_bareRelease = false;
      Serial.printf("{\"ok\":true,\"cmd\":\"release\",\"x\":%d,\"y\":%d}\n",
                    s_lastInjectX, s_lastInjectY);
    } else {
      Serial.printf("{\"ok\":true,\"cmd\":\"drag\","
                    "\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                    s_pendingDragX1, s_pendingDragY1,
                    s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps);
    }
  } else {
    LOG_D("serial", "inject sample %d/%d sx=%d sy=%d",
          s_injectHead + 1, s_injectTotal - 1, step.sx, step.sy);
    if (step.sx >= TASKBAR_X) {
      // Taskbar zone: route to gesture handlers, not app handleInput.
      s_lastTouchY = step.sy;
      if (!winampDisplay.tbIsDragging()) {
        winampDisplay.tbGesturePress(step.sy);
        shellTbPress(step.sy);  // TASK-279 (F-a): same shared paint as production
      } else {
        if (winampDisplay.tbGestureContinue(step.sy, TASKBAR_APP_COUNT))
          renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
        // TASK-279 (F-a): cancel the highlight at scroll-start [DEV-3-1].
        if (winampDisplay.tbIsScrolling()) shellTbCancel();
      }
    } else {
      // TASK-277 reroute (VE-1-6): canvas samples go to the active app —
      // Spotify's path is unchanged in effect (SpotifyApp::handleInput
      // forwards Press/Move to handleWinampInput; eject intercept is
      // Release-only), and every other app now receives injected drags.
      s_lastInjectX = step.sx;
      s_lastInjectY = step.sy;
      TouchPhase ph = s_injectIsFirst ? TouchPhase::Press : TouchPhase::Move;
      s_injectIsFirst = false;
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(ph, step.sx, step.sy);
    }
  }
#else
  (void)step;
#endif
  ++s_injectHead;
#endif
}

static void handleSerialCommands() {
  static char buf[160];  // widened: 64 was too small for long-URL commands (wrUrl, wrDeadUrls)
  static int  len = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      buf[len] = '\0';
      if (len > 0) {
        // Split "name args" at first space; args may be "".
        char *sp = strchr(buf, ' ');
        const char *args = sp ? sp + 1 : "";
        if (sp) *sp = '\0';
        bool handled = false;
        for (int i = 0; i < kNumCmds; ++i) {
          if (strcmp(buf, kCmds[i].name) == 0) {
            kCmds[i].fn(args);
            handled = true;
            break;
          }
        }
        if (!handled) {
          Serial.printf("{\"ok\":false,\"error\":\"unknown command\",\"cmd\":\"%s\"}\n", buf);
        }
      }
      len = 0;
    } else if (len < (int)sizeof(buf) - 1) {
      buf[len++] = c;
    } else {
      // Buffer full before newline — drop the partial, WARN, resync on next '\n'.
      // (Next newline will be misaligned; host-side scripts must treat the
      // following line as garbage.)
      Serial.println("{\"ok\":false,\"error\":\"line too long\"}");
      len = 0;
    }
  }
}

// TASK-408 (M-SDFS phase-0): own VSPI bus — SCK18/MISO19/MOSI23/CS5 — entirely free of
// the HSPI TFT bus and the touch controller's own SPI (see M-SDFS-sd-card-exploration.md
// §2). The mount is established once in setup() and held — see sdProbeBootMount()'s call
// site for why a lazy per-mode-entry mount cannot be relied on here.
//
// TASK-427: this block — the statics, `sdMountAttempt()`, `sdProbeBootMount()`, and
// `sdReady()` — is gated on SD_BOOT_MOUNT, not SERIAL_DEBUG, so it compiles into any
// variant that wants the boot mount without pulling in the rest of the SERIAL_DEBUG
// command surface (`cyd2usb_player`). `cyd2usb_winamp_debug` defines both, so every
// existing T_PLR/T_SD gate is unaffected. `cyd2usb_winamp` (production) defines
// neither — no mount, sdReady() stubs to false, Player mode degrades to "No SD card".
// That remains deliberate: an unconditional boot mount costs ~13 KB of permanently-held
// contiguous internal heap (FATFS window + max_files × FIL), which TASK-425 measured
// does not fit alongside the Spotify TLS working set and the Helix arena — see
// TASK-431. The interactive bring-up probes below this SERIAL_DEBUG gate — `sdmem`,
// `sdmount`/`sdumount` (live commands), `sdcycle`, `sdls`, `sdread`, `sdwrite`,
// `sdclean`, `sdprobe` (the full T_SD_01–09 sweep) — stay SERIAL_DEBUG-only and
// reference the statics/functions defined here.
#ifdef SD_BOOT_MOUNT
static const int kSdCsPin = 5;
static const int kSdSckPin = 18;
static const int kSdMisoPin = 19;
static const int kSdMosiPin = 23;
// SPI clock for data transfers (card identification always runs at 400 kHz inside
// ff_sd_initialize, and the library caps this at 25 MHz). 20 MHz, not the 4 MHz the
// M-SDFS bring-up plan suggested: on the SDHC card, 4 MHz reproducibly panics inside
// FatFs mid-read (2/2 runs; `validate()` sees obj->fs == NULL after ff_req_grant())
// while 20 MHz is clean (3/3) and 40x faster. Runtime-settable via `sdmount`.
static uint32_t s_sdFreqHz = 20000000;

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
static const uint8_t kSdMaxFiles = 3;

static SPIClass s_sdSPI(VSPI);
static bool s_sdReady = false;
static bool s_sdSpiUp = false;
static size_t s_sdBootFreeIntBefore = 0, s_sdBootFreeIntAfter = 0;
static size_t s_sdBootLfbIntBefore = 0, s_sdBootLfbIntAfter = 0;

// One mount attempt with full before/after heap accounting, usable from setup()
// and from a live serial command. `tag` names the call site in the JSON line.
static bool sdMountAttempt(const char *tag, uint8_t maxFiles) {
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

static void sdProbeBootMount() {
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

// ── SERIAL_DEBUG command implementations (TASK-056e/h/i) ─────────────
// All compile only when SERIAL_DEBUG is defined (cyd2usb_winamp_debug env).
// Each emits exactly one '\n'-terminated JSON object (ADR-021 invariant),
// except `get snapshot` which may emit two via multi-part protocol.
#ifdef SERIAL_DEBUG

#include "debug/serialConsole/cmdTouch.h"

#include "debug/serialConsole/cmdGet.h"

#include "debug/serialConsole/cmdSet.h"

#include "debug/serialConsole/cmdMisc.h"
// SERIAL_DEBUG) — see the block just above the SERIAL_DEBUG command section below.
#include "debug/serialConsole/cmdSd.h"

#include "debug/serialConsole/cmdSystem.h"
#endif // SERIAL_DEBUG

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
  if (g_shellBusy && g_apps[(int)currentAppId] &&
      !g_apps[(int)currentAppId]->hasPendingAsync())
      shell::setBusy(false);
  // Fallback: auto-clear after timeout (safety net).
  if (g_shellBusy && millis() - g_shellBusySetMs > SHELL_BUSY_TIMEOUT_MS)
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
                            TASKBAR_APP_COUNT, g_shellBusy, err, conn);
    }
  }

  unsigned long _loopMs = millis() - _loopStart;
  perf::recordLoop(_loopMs);
  if (_loopMs > 50) {
    LOG_W("perf", "iter=%lums (worst path so far: %s:%ums)",
          _loopMs, perf::worstPathName(), (unsigned)perf::worstPathMs());
  }
}
