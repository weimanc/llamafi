#pragma once
// shell/shellDispatch.h — shell-level dispatch helpers shared between
// main.cpp's production touch path and the debug console's injected-touch
// path (M-SRCLAYOUT Stage E / TASK-471). Declarations only; bodies that
// aren't trivial one-liners stay defined once in main.cpp, same "why" as
// every other extern split this stage made: these used to be reachable by
// the debug console files only because they were textually downstream of
// main.cpp's own globals, which stopped being true the moment those files
// became their own translation units.

#include "appShell.h"   // AppId

namespace shell {
// Sets busy flag and immediately repaints only the active-slot indicator.
// Defined once in main.cpp (needs renderActiveIndicator + winampDisplay,
// both already reachable there).
void setBusy(bool busy);
}

// TASK-413 / ADR-059 D6 (amended DEV-1): the player slot's taskbar tap has a
// second meaning no other slot has — restore the persisted mode when tapped
// from another app, but CYCLE (Spotify -> WebRadio -> Player -> Spotify) and
// persist when tapped while the player is already active. Defined once in
// main.cpp, called from both dispatch sites (shellTbRelease() there, and
// cmdTap()/cmdPlayerCycle() here) so the decision cannot drift between them.
AppId resolvePlayerTap(AppId tapped, bool playerAlreadyActive);

// TASK-413: the three player-mode AppIds are the only ones this returns true
// for. Trivial and stateless — kept inline rather than adding a declaration +
// out-of-line definition for a three-way `||`.
inline bool isPlayerModeApp(AppId id) {
  return id == AppId::Spotify || id == AppId::WebRadio || id == AppId::LocalPlayer;
}
