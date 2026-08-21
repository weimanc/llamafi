// debug/serialConsole/cmdTouch.cpp — touch injection, out-of-line
// (M-SRCLAYOUT Stage E / TASK-471). Body compiles only under SERIAL_DEBUG;
// the .cpp itself is always compiled, same convention as appTable.cpp /
// cmdSystem.cpp / cmdMisc.cpp.
#include "debug/serialConsole/cmdTouch.h"

#ifdef SERIAL_DEBUG
#include <Arduino.h>
#include <string.h>
#include "appShell.h"                    // AppId, currentAppId, TouchPhase
#include "shell/appTable.h"              // g_apps[], g_WebRadioApp
#include "shell/shellDispatch.h"         // setBusy, resolvePlayerTap, isPlayerModeApp
#include "shell/shellState.h"            // shell::state()
#include "debug/serialConsole/consoleShared.h"  // injection ring buffer
#include "taskbar/taskbar.h"             // TASKBAR_APP_COUNT
#include "winamp/winampDisplay.h"
#include "winamp/vuMeter.h"

extern WinampDisplay winampDisplay;      // defined in main.cpp

void cmdTap(const char *args) {
  int x, y;
  if (sscanf(args, "%d %d", &x, &y) != 2) {
    Serial.println("{\"ok\":false,\"cmd\":\"tap\",\"error\":\"bad args — tap <x> <y>\"}");
    return;
  }
#ifdef WINAMP_DISPLAY
  // Taskbar handled at shell level — WinampDisplay must not reference switchApp.
  if (x >= TASKBAR_X) {
    int slot   = (int)y / TASKBAR_SLOT_H;
    int appIdx = (winampDisplay.tbScrollOffset() + slot) % TASKBAR_APP_COUNT;
    // TASK-280/413: route through the production resolve path — a tap on the
    // player slot must restore the persisted mode, or cycle it if already active,
    // same as shellTbRelease()/switchApp() do for real taps and injected drags.
    AppId target = resolvePlayerTap(static_cast<AppId>(appIdx), isPlayerModeApp(currentAppId));
    switchApp(target);
    winampDisplay.lastTouchResult = { "TASKBAR", -1, "APP_SWITCH", 0, -1, false };
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"TASKBAR\",\"action\":\"APP_SWITCH\",\"skipped\":false}\n", x, y);
    return;
  }
  // TASK-384: a pure-navigation tap (e.g. Stock's chart-back zone) bypasses
  // the busy gate — it doesn't start new async work, so there's nothing for
  // the gate to protect against here. See isNavigationTap()'s doc comment.
  bool navTapBypass = g_apps[(int)currentAppId] &&
                       g_apps[(int)currentAppId]->isNavigationTap(x, y);
  if (shell::state().busy && !navTapBypass) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"CANVAS\",\"action\":\"NONE\",\"skipped\":true}\n", x, y);
    return;
  }
  // Non-Spotify app dispatch: route tap to active app's handleInput when the
  // app implements real canvas interaction (Stock). Other apps retain BUG-1
  // guard (hit=CLOCK) — they don't need tap dispatch in tests.
  if (currentAppId != AppId::Spotify) {
    if (currentAppId == AppId::Stock && g_apps[(int)AppId::Stock]) {
      g_apps[(int)AppId::Stock]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Stock]->handleInput(TouchPhase::Release, x, y);
      if (!shell::state().busy && g_apps[(int)AppId::Stock]->hasPendingAsync())
        shell::setBusy(true);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"STOCK\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::Settings && g_apps[(int)AppId::Settings]) {
      g_apps[(int)AppId::Settings]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Settings]->handleInput(TouchPhase::Release, x, y);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"SETTINGS\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::Teletext && g_apps[(int)AppId::Teletext]) {
      g_apps[(int)AppId::Teletext]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Teletext]->handleInput(TouchPhase::Release, x, y);
      if (!shell::state().busy && g_apps[(int)AppId::Teletext]->hasPendingAsync())
        shell::setBusy(true);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"TELETEXT\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::PlaneRadar && g_apps[(int)AppId::PlaneRadar]) {
      g_apps[(int)AppId::PlaneRadar]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::PlaneRadar]->handleInput(TouchPhase::Release, x, y);
      if (!shell::state().busy && g_apps[(int)AppId::PlaneRadar]->hasPendingAsync())
        shell::setBusy(true);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"PLANERADAR\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else if (currentAppId == AppId::LocalPlayer && g_apps[(int)AppId::LocalPlayer]) {
      // TASK-415: same shape as the WebRadio branch below, and for the same
      // reason — injectTouch() runs handleWinampInput()'s Press phase, which
      // is what anchors a PLEDIT row tap in the shared PleditView. Without it
      // the harness could reach eject and transport but never a row, and the
      // real-touch path and cmdTap would be anchoring against different state
      // (the TASK-406 defect class). The reply reports lastTouchResult so row
      // taps are observable, not just CONSUMED/NONE.
      winampDisplay.injectTouch(x, y);
      g_apps[(int)AppId::LocalPlayer]->handleInput(TouchPhase::Release, x, y);
      // TASK-416: same busy-set-on-Release-starts-async-work shape as the
      // Stock/Teletext/PlaneRadar branches above — an eject tap that opens
      // the browser (or a row tap into a subdirectory) starts a page walk,
      // and T_PLR_14 needs ShellState::busy to actually go true here to exercise
      // the isNavigationTap() bypass at cmdTap's own busy-gate check above,
      // not just observe it as dead code.
      if (!shell::state().busy && g_apps[(int)AppId::LocalPlayer]->hasPendingAsync())
        shell::setBusy(true);
      const auto &lp = winampDisplay.lastTouchResult;
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"%s\",\"row\":%d,\"action\":\"%s\",\"skipped\":%s}\n",
                    x, y, lp.region, lp.transportPressed, lp.action,
                    lp.skipped ? "true" : "false");
    } else if (currentAppId == AppId::WebRadio && g_apps[(int)AppId::WebRadio]) {
      // WebRadio: injectTouch populates lastTouchResult for the response;
      // WebRadioApp::handleInput executes the action (eject/transport/PLEDIT).
      // TASK-387: the vis-zone is WebRadioApp's own authoritative handler
      // (vu::nextMode(appHasSpectrum=true) — vuMeter.h). injectTouch's Press
      // call reaches the *same* screen coordinates via handleWinampInput's
      // hitVis branch (that function is shared chrome, otherwise correctly
      // reused for Spotify's real touch path) and would silently fire a
      // second, differently-flagged vu::nextMode() call first — pre-existing
      // latent bug (harmless while nextMode() took no args, since both calls
      // did the same step; surfaced now because the two calls diverge).
      // Skip injectTouch for this one zone and build the diagnostic result
      // directly instead of double-mutating the vis mode.
      if (x >= vu::RECT_X && x < vu::RECT_X + vu::RECT_W &&
          y >= vu::LEFT_Y && y < vu::LEFT_Y + vu::VIS_H) {
        winampDisplay.lastTouchResult = { "VIS", -1, "VIS", 0, -1, false };
      } else {
        winampDisplay.injectTouch(x, y);
      }
      g_apps[(int)AppId::WebRadio]->handleInput(TouchPhase::Release, x, y);
      const auto &wr = winampDisplay.lastTouchResult;
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"%s\",\"action\":\"%s\",\"skipped\":%s}\n",
                    x, y, wr.region, wr.action, wr.skipped ? "true" : "false");
    } else if (currentAppId == AppId::Clock && g_apps[(int)AppId::Clock]) {
      // M-CLOCK-TAP-CYCLE (TASK-346): clock now has real canvas interaction
      // (face/theme cycle zones) — no async, so no setBusy propagation.
      g_apps[(int)AppId::Clock]->handleInput(TouchPhase::Press, x, y);
      bool consumed = g_apps[(int)AppId::Clock]->handleInput(TouchPhase::Release, x, y);
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"CLOCKAPP\",\"action\":\"%s\",\"skipped\":false}\n",
                    x, y, consumed ? "CONSUMED" : "NONE");
    } else {
      winampDisplay.lastTouchResult = { "CLOCK", -1, "NONE", 0, -1, false };
      Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                    "\"hit\":\"CLOCK\",\"action\":\"NONE\",\"skipped\":false}\n", x, y);
    }
    return;
  }
  winampDisplay.injectTouch(x, y);
  winampDisplay.injectRelease();
  // Eject: injectTouch only sets lastTouchResult; SpotifyApp::handleInput must
  // be called directly to execute the TLS-reset + force-poll reconnect
  // (TASK-414).
  if (strcmp(winampDisplay.lastTouchResult.action, "EJECT") == 0) {
    g_apps[(int)AppId::Spotify]->handleInput(TouchPhase::Release, x, y);
  }
  if (!shell::state().busy && g_apps[(int)AppId::Spotify]->hasPendingAsync())
    shell::setBusy(true);
  const auto &r = winampDisplay.lastTouchResult;
  if (strcmp(r.region, "TRANSPORT") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"pressed\":%d,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.transportPressed, r.action,
                  r.skipped ? "true" : "false");
  } else if (strcmp(r.region, "PLEDIT") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"row\":%d,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.transportPressed, r.action,
                  r.skipped ? "true" : "false");
  } else if (strcmp(r.region, "POSBAR") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"seekMs\":%ld,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.seekMs, r.action,
                  r.skipped ? "true" : "false");
  } else if (strcmp(r.region, "VOLUME") == 0) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"volumePct\":%ld,\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.volumePct, r.action,
                  r.skipped ? "true" : "false");
  } else {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                  "\"hit\":\"%s\",\"action\":\"%s\",\"skipped\":%s}\n",
                  x, y, r.region, r.action, r.skipped ? "true" : "false");
  }
#else
  Serial.printf("{\"ok\":true,\"cmd\":\"tap\",\"x\":%d,\"y\":%d,"
                "\"hit\":\"NONE\",\"action\":\"NONE\",\"skipped\":false}\n", x, y);
#endif
}

void cmdDrag(const char *args) {
  int x1, y1, x2, y2, steps;
  char tail[8] = {0};
  int n = sscanf(args, "%d %d %d %d %d %7s", &x1, &y1, &x2, &y2, &steps, tail);
  bool hold = (n == 6 && strcmp(tail, "hold") == 0);
  if (n < 5 || (n == 6 && !hold) || steps < 1 || steps > 62) {
    Serial.println("{\"ok\":false,\"cmd\":\"drag\","
                   "\"error\":\"bad args — drag <x1> <y1> <x2> <y2> <steps=1..62> [hold]\"}");
    return;
  }
#ifdef WINAMP_DISPLAY
  winampDisplay._injectingDrag = true;
#endif
  s_injectHead = s_injectTail = 0;
  s_injectIsFirst = true;  // first dequeued sample → Press, rest → Move
  for (int i = 0; i <= steps; ++i) {
    s_injectQueue[s_injectTail++ % 64] = {
      x1 + (x2 - x1) * i / steps,
      y1 + (y2 - y1) * i / steps,
      false
    };
  }
  // TASK-277 (VE-1-3): `hold` suppresses the release sentinel — the gesture
  // stays anchored so mid-gesture events (auto-skip) are agent-testable; a
  // later bare `release` ends it. _injectingDrag stays set until that release.
  if (!hold)
    s_injectQueue[s_injectTail++ % 64] = { 0, 0, true };  // release sentinel
  s_pendingDragX1 = x1; s_pendingDragY1 = y1;
  s_pendingDragX2 = x2; s_pendingDragY2 = y2;
  s_pendingDragSteps = steps;
  s_injectTotal = s_injectTail;
  s_dragPending = !hold;
  if (hold) {
    // No release step will pop → respond now (the normal contract emits the
    // JSON from drainInjectionQueue at release-pop).
    Serial.printf("{\"ok\":true,\"cmd\":\"drag\",\"hold\":true,"
                  "\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                  x1, y1, x2, y2, steps);
  }
  // Non-hold: JSON response emitted by drainInjectionQueue() when release pops.
}

// TASK-277 (VE-1-3): end a held gesture — enqueue a release step dispatched at
// the last injected sample's coordinates.
void cmdRelease(const char *) {
  s_bareRelease = true;
  s_injectQueue[s_injectTail++ % 64] = { 0, 0, true };
  // JSON response emitted by drainInjectionQueue() when the step pops.
}

void cmdTick(const char *args) {
  int n = 1, dtMs = 20;
  sscanf(args, "%d %d", &n, &dtMs);
  if (n < 1)    n    = 1;
  if (dtMs < 1) dtMs = 20;
#ifdef WINAMP_DISPLAY
  // TASK-277 [VE-1-5]: drive the ACTIVE app's integrator when WebRadio is up.
  // The reply's scrollOffset field stays Spotify-only — WebRadio tests assert
  // via `get wrScroll` exclusively.
  if (currentAppId == AppId::WebRadio) {
    for (int i = 0; i < n; ++i)
      g_WebRadioApp.tickScrollDebug(dtMs * 0.001f);
  } else {
    for (int i = 0; i < n; ++i)
      winampDisplay.tickScroll(dtMs * 0.001f);
  }
  char sbuf[64]; int scrollOff = 0;
  if (winampDisplay.dbgGet("scrollOffset", sbuf, sizeof(sbuf)))
    sscanf(sbuf, "\"key\":\"scrollOffset\",\"val\":%d", &scrollOff);
  Serial.printf("{\"ok\":true,\"cmd\":\"tick\",\"steps\":%d,\"dtMs\":%d,"
                "\"scrollOffset\":%d}\n", n, dtMs, scrollOff);
#else
  Serial.printf("{\"ok\":true,\"cmd\":\"tick\",\"steps\":%d,\"dtMs\":%d,"
                "\"scrollOffset\":0}\n", n, dtMs);
#endif
}
#endif // SERIAL_DEBUG
