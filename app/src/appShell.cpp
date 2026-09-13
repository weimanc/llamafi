// appShell.cpp — shell dispatch bodies, out-of-line (M-SRCLAYOUT Stage E /
// TASK-471). appShell.h stays where it is (already the real header nearly
// every app file includes by this exact path); this TU just gives its
// declared dispatch functions (switchApp/appHandleInput/appTick/
// persistPlayerMode) and the taskbar-tap-feedback group (resolvePlayerTap,
// shellTbPress/Cancel/Release, both declared in shell/shellDispatch.h) their
// one out-of-line definition. The design doc's original ~360-line estimate
// for this split (docs/architecture/designs/M-SRCLAYOUT-main-decomposition.md,
// D1) is stale — ShellState itself already moved out in Stage D
// (shell/shellState.h/.cpp) — so what's actually here is just the dispatch
// logic, moved verbatim from main.cpp.
#include "appShell.h"

#include <Arduino.h>
#include "settingsStorage.h"               // g_settings, PlayerMode, playerModeResolve/Next
#include "shell/shellState.h"              // shell::state()
#include "shell/shellDispatch.h"           // resolvePlayerTap/shellTb*/isPlayerModeApp/shell::*
#include "shell/taskbar.h"                 // TASKBAR_X/SLOT_H/APP_COUNT, renderTaskbar*
#include "shell/appTable.h"                // g_apps[], g_ledFlow, g_backlight, g_keyboard
#include "spotifyTask.h"
#include "perf.h"
#include "debug/touchDebugOverlay.h"       // g_touchDebug (self-guarded on TOUCH_DEBUG_OVERLAY)
#include "CYD28_TouchscreenR.h"            // CYD28_TouchR / CYD28_TS_Point

// TASK-501: WINAMP_DISPLAY is unconditionally defined (every buildable env
// extends [env:cyd2usb_winamp] — see app/platformio.ini and TASK-496/467's
// own note in shell/appTable.cpp) — no #ifdef needed.
#include "winamp/winampDisplay.h"
extern WinampDisplay winampDisplay;       // defined in main.cpp

#include "display/tft.h"
extern CYD28_TouchR ts;                   // defined once, in touchScreen.h/.cpp

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
  if (g_apps[(int)id]) {
    g_apps[(int)id]->tick();
#ifdef SERIAL_DEBUG
    // ADR-063 D4 (TASK-637): shell-owned progress, bumped around the
    // dispatch the shell already owns — see appShell.h for why appRepaints
    // tracks appTicks 1:1 for now.
    if ((int)id < (int)AppId::COUNT) {
      g_appTicks[(int)id]++;
      g_appRepaints[(int)id]++;
    }
#endif
  }
}

#ifdef SERIAL_DEBUG
uint32_t g_appTicks[(int)AppId::COUNT]    = {0};
uint32_t g_appRepaints[(int)AppId::COUNT] = {0};

namespace {
const char* dbgAppName(AppId id) {
#define APP_X(Name, icon, cfg, disp) #Name,
    static const char* kNames[] = {
#include "appRegistry.h"
    };
#undef APP_X
    return ((int)id < (int)AppId::COUNT) ? kNames[(int)id] : "Unknown";
}
}  // namespace

bool dbgAppIsActive(AppId owner) { return currentAppId == owner; }

void dbgRefuseInactive(const char* cmd, const char* var, AppId owner) {
  Serial.printf("{\"ok\":false,\"cmd\":\"%s\",\"var\":\"%s\","
                "\"error\":\"inactiveApp\",\"owner\":\"%s\",\"active\":\"%s\",\"last\":true}\n",
                cmd, var, dbgAppName(owner), dbgAppName(currentAppId));
}
#endif
