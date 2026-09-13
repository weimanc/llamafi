#pragma once
// shell/shellState.h — the shell's own mutable state, as ONE owned struct.
// M-SRCLAYOUT D3/D4, ADR-060 D3/D4. TASK-456 (Stage D).
//
// Replaces nine loose file-scope variables in main.cpp (g_shellBusy,
// g_shellBusySetMs, g_previousAppId, g_appLaunched[], s_inGesture,
// s_lastTouchX/Y, s_cooldownMs, s_tbPressedSlot, s_tbPressedApp). They were
// reachable only by being textually downstream of main.cpp's globals block,
// which is the gravity well ADR-060 exists to drain.
//
// TWO DELIBERATE DEVIATIONS FROM THE SKETCH IN D3, both flagged for Architect
// sign-off rather than decided here:
//
//   * The accessor is `shell::state()`, not the global `shell()` D3 writes.
//     `namespace shell` already exists in main.cpp and owns setBusy() /
//     activeError() / activeConnecting(); a global function named `shell` and a
//     namespace named `shell` cannot coexist in one program — the compiler
//     rejects it outright ("redeclared as different kind of symbol"). The
//     namespace is the older, wider-used name and it is where this state
//     belongs anyway, so the accessor moved into it.
//   * `currentAppId` is NOT a member. D3's own struct sketch omits it while the
//     surrounding prose (and §8, which files the item under TASK-457) says to
//     unify it with `previous`. Following the sketch: it has 85 references
//     across nine files, and D4 mandates an OUT-OF-LINE accessor, so folding it
//     in adds a function call to the single hottest read in the firmware
//     (several per loop() iteration) for a naming win. Deferred, not forgotten.
//
// The object itself is a file-scope `static` in shellState.cpp with an
// out-of-line accessor — NOT a Meyers singleton. D4 rejects the lazy form for
// three target-specific reasons: it hands the timing of allocation to the
// compiler on a board whose dram0_0_seg headroom has measured as low as 0 B;
// C++11 thread-safe statics emit a guard plus __cxa_guard_acquire/release, and
// the concurrency here is real (dataTask, spotifyTask, the audio pump); and the
// static-initialization-order fiasco it defends against is absent, because boot
// order is explicit in setup(). Every initialiser below is a constant
// expression, so s_shell is constant-initialised before any dynamic init runs —
// there is no order to get wrong.

#include <Arduino.h>

#include "appShell.h"   // AppId (X-macro over appRegistry.h)

// No NSDMI: this toolchain is -std=gnu++11 and the struct is initialised with an
// aggregate initialiser in shellState.cpp. Adding default member initialisers
// here would make it a non-aggregate, break that initialiser, and demote the
// object from constant to dynamic initialisation.
struct ShellState {
    // ── busy gate (M-TOUCH-UX TASK-115b) ──
    bool          busy;
    unsigned long busySetMs;
    // TASK-617/M-HARNESS2 R14: set only by the debug `set shellBusy 1` path
    // (armedInjectors.h `shellBusy` entry). A forced busy has no real
    // hasPendingAsync() behind it, so the primary auto-clear in main.cpp's
    // loop() (which fires the instant the active app reports no pending
    // work) would otherwise clear it on the very next tick — this bit is
    // the one piece of new state clause 3 of the armed-injector membership
    // rule allows when "forced" and "real" cannot otherwise be told apart.
    // Still subject to the same SHELL_BUSY_TIMEOUT_MS safety net as a real
    // busy, and cleared by `set shellBusy 0` / `set injclear`.
    bool          busyForced;

    // ── navigation ──
    AppId         previous;                      // Settings' "back" target
    bool          launched[(int)AppId::COUNT];   // first-launch tracking: init() vs resume()

    // ── canvas gesture tracking (TASK-090f) ──
    bool          inGesture;
    int           lastTouchX, lastTouchY;
    unsigned long cooldownMs;

    // ── taskbar press feedback (M-TASKBAR-FEEDBACK / TASK-279) ──
    // Press-anchored: the slot captured at Press is the slot the tap commits.
    int           tbPressedSlot;   // visible slot highlighted at Press; -1 = none
    int           tbPressedApp;    // press-anchored app index (highlight == commit)
};

namespace shell {
// Defined in shellState.cpp. D5 caution applies: this makes shell state easier
// to reach than it was, which can entrench coupling rather than reduce it. New
// code reaching for shell::state() is a review question, not a default — prefer
// a parameter.
ShellState& state();
}
