#pragma once
// shell/shellDispatch.h — shell-level dispatch helpers shared between
// main.cpp's production touch path and the debug console's injected-touch
// path (M-SRCLAYOUT Stage E / TASK-471). Declarations only; bodies that
// aren't trivial one-liners stay defined once in main.cpp, same "why" as
// every other extern split this stage made: these used to be reachable by
// the debug console files only because they were textually downstream of
// main.cpp's own globals, which stopped being true the moment those files
// became their own translation units.

#include "appShell.h"     // AppId
#include "shell/appTable.h"   // g_apps[]

namespace shell {
// Sets busy flag and immediately repaints only the active-slot indicator.
// Defined once in main.cpp (needs renderActiveIndicator + winampDisplay,
// both already reachable there). `forced` (TASK-617) marks a busy raised by
// the debug `set shellBusy 1` path rather than a real hasPendingAsync() —
// see shellState.h's `busyForced` comment. Real call sites never pass it;
// it defaults to false, which also clears any stale forced flag on a real
// setBusy() call.
void setBusy(bool busy, bool forced = false);

// TASK-245 / ADR-046: error state of the currently-active app — drives the red
// active-bar (precedence error > busy/connecting > idle). Owned by the app
// instance, so it survives app switch and is re-read on every repaint.
// Trivial and stateless — inline, same reasoning as isPlayerModeApp() below.
inline bool activeError() {
    return g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->hasError();
}
// TASK-245 amendment / ADR-046: connecting state of the active app — amber bar
// until the app's first data result resolves (boot reads amber, not green).
inline bool activeConnecting() {
    return g_apps[(int)currentAppId] && g_apps[(int)currentAppId]->isConnecting();
}
}

// ── Taskbar tap feedback (M-TASKBAR-FEEDBACK / TASK-279) ──────────────────
// Shared between main.cpp's production touch path (appHandleInput) and the
// debug console's injection drain (debug/serialConsole/console.cpp) — same
// "Defined once in appShell.cpp" convention as resolvePlayerTap() below
// (setBusy() above is still defined in main.cpp).
void shellTbPress(int y);
void shellTbCancel();
void shellTbRelease(int releaseY);

// TASK-413 / ADR-059 D6 (amended DEV-1): the player slot's taskbar tap has a
// second meaning no other slot has — restore the persisted mode when tapped
// from another app, but CYCLE (Spotify -> WebRadio -> Player -> Spotify) and
// persist when tapped while the player is already active. Defined once in
// appShell.cpp (M-SRCLAYOUT Stage E / TASK-471), called from both dispatch
// sites (shellTbRelease() there, and cmdTap()/cmdPlayerCycle() here) so the
// decision cannot drift between them.
AppId resolvePlayerTap(AppId tapped, bool playerAlreadyActive);

// TASK-413: the three player-mode AppIds are the only ones this returns true
// for. Trivial and stateless — kept inline rather than adding a declaration +
// out-of-line definition for a three-way `||`.
inline bool isPlayerModeApp(AppId id) {
  return id == AppId::Spotify || id == AppId::WebRadio || id == AppId::LocalPlayer;
}
