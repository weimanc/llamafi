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
    // STRIP_BACK). The shell's busy pre-dispatch gate (ShellState::busy)
    // normally drops
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
    // TASK-518 (M-TESTBASE P4): QUIESCENCE. Return true while an operation
    // THIS APP STARTED is still running. Backs `get idle`, so a host test can
    // ask "is the device finished doing what I asked?" instead of guessing
    // with a sleep() (252 of them in run_serialdbg_tests.py alone).
    //
    // ── The contract, stated once, because it is the trap ──────────────────
    // "In flight" means a TRANSIENT operation with a start and an end. It is
    // NOT "I have never had data". An app that is idle-but-empty IS idle:
    // a device that will never fetch again is quiescent, not busy.
    //
    // This is why isConnecting() is NOT the predicate and must not be ANDed
    // in wholesale (M-TESTBASE §4 P4, blocker B3 — isConnecting() carries two
    // incompatible meanings across the 13 apps):
    //   transient-op semantics (reusable here):
    //     webRadioApp.h  `_state == WRPlayState::CONNECTING`
    //     localPlayerApp.h `_connecting`
    //   never-had-data-yet semantics (NOT reusable here):
    //     teletextApp.h `!_ready` · planeRadarApp.h `!_everHadResult`
    //     apps/cryptoApp.h `!s_cxDataReady` · apps/weatherApp.h `!s_wxDataReady`
    //     apps/stockApp.h `!_everHadData`
    //     spotifyTaskStorage.cpp connecting() == `s_lastSuccessfulPollMs == 0`,
    //       which latches false only on the FIRST 200/204 — under this rig's
    //       live 403 (TASK-243) that never happens, so anything ANDing it
    //       reports never-quiet forever on the actual DUT.
    //
    // ── Default ───────────────────────────────────────────────────────────
    // Defaults to hasPendingAsync(), which is already contractually
    // "async work initiated by handleInput() is still in flight, self-clearing"
    // — i.e. a strict subset of this predicate, with the right transient
    // shape. Consequences: an app with no async work at all inherits false
    // (safe default, no override needed), and a NEW app that wires only
    // hasPendingAsync() per NEW-APP-CHECKLIST item 1 gets a conservative
    // answer rather than a silent "idle" lie. Override when the app has
    // in-flight work hasPendingAsync() does not cover (a stream connect, a
    // file open, a second fetch channel) — see NEW-APP-CHECKLIST item 1b.
    //
    // Whatever backs it MUST self-clear on both the success and the failure
    // path. A term that can latch true turns `get idle` into a permanent
    // "busy", which is worse than the sleep() it replaces.
    virtual bool hasInFlightOp() const { return hasPendingAsync(); }
    virtual ~App() = default;
};
