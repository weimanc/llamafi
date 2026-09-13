// shell/shellState.cpp — the single definition of the shell's state object.
// M-SRCLAYOUT D3/D4, ADR-060 D3/D4. TASK-456 (Stage D).
//
// This is the first real COMPONENT (.h + .cpp) M-SRCLAYOUT has produced, and the
// project's 8th translation unit. It is deliberately a thin one: it depends only
// on appShell.h (AppId), so it compiles standing alone — unlike the app headers,
// which cannot yet (see shell/appTable.h's header comment for the mechanism).

#include "shell/shellState.h"

// File-scope static, NOT a function-local one (ADR-060 D4 — see shellState.h).
// Every initialiser is a constant expression, so this is constant-initialised
// and placed deterministically; nothing runs before main().
//
// The values are exactly the ones the nine variables this replaces carried in
// main.cpp. Two are NOT zero and are load-bearing: tbPressedSlot/tbPressedApp
// start at -1, and shellTbCancel()/shellTbPress() test `< 0` for "no slot
// highlighted" — zero would mean slot 0.
static constexpr ShellState kShellInit = {
    false,            // busy
    0,                // busySetMs
    false,            // busyForced (TASK-617)
    AppId::Spotify,   // previous
    {},               // launched[] — all false
    false,            // inGesture
    0, 0,             // lastTouchX, lastTouchY
    0,                // cooldownMs
    -1,               // tbPressedSlot  (-1 = none; NOT zero)
    -1,               // tbPressedApp   (-1 = none; NOT zero)
};

// BP-068 — the negative test for the initialiser above, paid at compile time.
// A POSITIONAL aggregate initialiser is silently wrong if anyone reorders
// ShellState's members: the two -1s land on `cooldownMs` and `tbPressedSlot`,
// every taskbar press commits slot 0, and nothing fails to build. Asserting the
// two non-zero values (and the two that are only correct by coincidence of being
// zero) makes that reorder a compile error instead.
//
// VERIFIED NEGATIVE (BP-068, not asserted — run): swapping the declarations of
// `lastTouchX` and `tbPressedSlot` in shellState.h — same type, so the compiler
// has nothing else to object to — fails the build with exactly two of these
// four, naming both drifted fields:
//   error: static assertion failed: ShellState initialiser drifted:
//          tbPressedSlot must start at -1 ...
//   error: static assertion failed: ShellState initialiser drifted:
//          the busy/gesture fields must start zeroed
static_assert(kShellInit.tbPressedSlot == -1,
              "ShellState initialiser drifted: tbPressedSlot must start at -1 "
              "(0 is slot 0, not 'no slot' — see shellTbCancel's `< 0` test)");
static_assert(kShellInit.tbPressedApp == -1,
              "ShellState initialiser drifted: tbPressedApp must start at -1 "
              "(shellTbRelease treats >= 0 as a press-anchored commit)");
static_assert(kShellInit.previous == AppId::Spotify,
              "ShellState initialiser drifted: previous must start at AppId::Spotify");
static_assert(!kShellInit.busy && kShellInit.busySetMs == 0 &&
              !kShellInit.busyForced &&
              !kShellInit.inGesture && kShellInit.cooldownMs == 0 &&
              kShellInit.lastTouchX == 0 && kShellInit.lastTouchY == 0,
              "ShellState initialiser drifted: the busy/gesture fields must start zeroed");

static ShellState s_shell = kShellInit;

namespace shell {
ShellState& state() { return s_shell; }
}
