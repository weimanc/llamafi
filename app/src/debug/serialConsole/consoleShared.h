#pragma once
// debug/serialConsole/consoleShared.h — state shared across the debug console
// command files and main.cpp (M-SRCLAYOUT Stage E / TASK-471). Every symbol
// here used to be reachable by the command files only because they were
// textually pasted into main.cpp at a fixed point downstream of these
// definitions — declarations only; the one definition of each stays in
// main.cpp (drainInjectionQueue()/etc.), except the SD boot mount, which has
// its own component (sd/sdMount.h/.cpp) below.

// ── serial command dispatch table (serialdbg-001, TASK-056c) ──────────────
// 4-field struct; help + args iterated by cmdHelp (TASK-056i).
typedef void (*cmd_fn)(const char *args);
struct SerialCmd {
  const char *name;
  cmd_fn      fn;
  const char *help;
  const char *args;
};

extern const SerialCmd kCmds[];
extern const int kNumCmds;

// ── touch-injection ring buffer (TASK-056e, SERIAL_DEBUG only) ─────────────
// drainInjectionQueue() (main.cpp) pops one step per loop() iteration — no
// delay(). cmdDrag/cmdRelease (cmdTouch.h) fill the queue and return.
#ifdef SERIAL_DEBUG
struct InjectionStep { int sx, sy; bool release; };
extern InjectionStep s_injectQueue[64];
extern int s_injectHead, s_injectTail;
extern bool s_dragPending;
extern bool s_injectIsFirst;  // first non-release item → Press, rest → Move
extern int s_pendingDragX1, s_pendingDragY1,
           s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps;
extern int s_injectTotal;  // total steps for LOG_D %d/%d
// TASK-277 (VE-1-1/DEV-1-2): the release step dispatches at the LAST sample's
// coordinates, not (0,0) — otherwise a drag's Release lands outside every
// hit-test region and gesture-end logic sees garbage geometry.
extern int s_lastInjectX, s_lastInjectY;
// TASK-277 (VE-1-3): bare `release` command marks its sentinel so the drain
// emits {"cmd":"release"} instead of the drag JSON.
extern bool s_bareRelease;
#endif

// ── SD boot mount (TASK-408, SD_BOOT_MOUNT only) ───────────────────────────
// kSdCsPin/s_sdFreqHz/s_sdReady/sdMountAttempt()/etc. now declared by
// sd/sdMount.h, their own component (M-SRCLAYOUT Stage E / TASK-471) — that
// header already self-guards on SD_BOOT_MOUNT.
#include "sd/sdMount.h"
