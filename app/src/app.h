#pragma once
// app.h — the App interface. One file, one job (M-SRCLAYOUT).
//
// Moved verbatim out of appShell.h, which had accumulated four unrelated
// concerns: this interface, the AppId enum, the shell dispatch declarations,
// and eight per-app private state structs. Every app that needs App had to
// drag in all of it.

#include "touchPhase.h"

struct App {
    virtual void init()    = 0;
    virtual void resume()  = 0;
    virtual void suspend() = 0;
    virtual void tick()    = 0;
    virtual bool handleInput(TouchPhase phase, int x, int y) = 0;
    // Return true while async work initiated by handleInput() is still in flight.
    // Self-clears when the work completes. Shell polls this after every tick().
    // Non-pure: apps with no async input need not override (safe default = false).
    virtual bool hasPendingAsync() const { return false; }
    // TASK-245 / ADR-046: return true while the app is in a sustained error state
    // (an auth/HTTP failure that won't self-heal by retrying — e.g. a Spotify 403).
    // Sticky: the app sets it on detection and clears it on the next success; the
    // shell does no latching, it only reads this to colour the taskbar active-slot
    // indicator red (precedence error > busy/connecting > idle). Safe default =
    // false, so offline apps need not override.
    virtual bool hasError() const { return false; }
    // TASK-245 amendment / ADR-046: return true while the app is establishing its
    // data connection and has no result yet (e.g. before the first Spotify poll
    // resolves). Renders the active-slot indicator amber (working) — so the bar
    // reads amber at boot rather than green (false "all-good") until we know the
    // state. Amber here collapses with the busy state; error (red) still wins.
    // Safe default = false.
    virtual bool isConnecting() const { return false; }
    // TASK-384: return true when (x, y) is a pure-navigation tap for the app's
    // CURRENT state — one that changes what's on screen without starting any
    // new async work (e.g. Stock's chart/heatmap "back" zone, Teletext's
    // STRIP_BACK). The shell's g_shellBusy pre-dispatch gate normally drops
    // every tap while the app's own hasPendingAsync() is true, to stop a tap
    // from stacking a redundant fetch on top of one already in flight — but
    // that gate has no way to tell "will start a new fetch" apart from "just
    // navigates", so it silently swallowed navigation taps too (confirmed on
    // real hardware, not just the serial test harness — see TASK-384). This
    // lets an app explicitly except specific screen regions, mirroring how
    // the taskbar tap already bypasses the busy gate entirely for the same
    // reason (switching away is always safe). Safe default = false — apps
    // with no async work, or no in-app navigation-while-pending case, need
    // not override.
    virtual bool isNavigationTap(int x, int y) const { (void)x; (void)y; return false; }
    virtual ~App() = default;
};
