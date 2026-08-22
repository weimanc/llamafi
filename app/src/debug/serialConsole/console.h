#pragma once
// debug/serialConsole/console.h — dispatch core: injection ring, the drain
// loop() calls per-iteration, and serial line parsing (M-SRCLAYOUT Stage E /
// TASK-471). SerialCmd/kCmds[]/kNumCmds and the injection-ring statics are
// declared in consoleShared.h — every command file needs those but not these
// two loop()-called entry points.

// TASK-056e: drain one injection step per loop() iteration. Always compiled
// (no-op body when SERIAL_DEBUG is off, matching consoleShared.h's ring).
void drainInjectionQueue();

// Reads and dispatches complete lines off Serial against kCmds[]. Always
// compiled — the `reconnect` command (ADR-021 Decision 4) ships in every
// build, not just SERIAL_DEBUG ones.
void handleSerialCommands();
