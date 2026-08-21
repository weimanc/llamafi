#pragma once
// debug/serialConsole/consoleShared.h — state shared across the debug console
// command files and main.cpp (M-SRCLAYOUT Stage E / TASK-471). Every symbol
// here used to be reachable by the command files only because they were
// textually pasted into main.cpp at a fixed point downstream of these
// definitions — declarations only; the one definition of each stays in
// main.cpp, its original and natural home (drainInjectionQueue()/
// sdMountAttempt()/etc. all still live there too).

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
#ifdef SD_BOOT_MOUNT
#include <SD.h>
#include <SPI.h>
extern const int kSdCsPin;
extern const int kSdSckPin;
extern const int kSdMisoPin;
extern const int kSdMosiPin;
extern uint32_t s_sdFreqHz;
extern const uint8_t kSdMaxFiles;
extern SPIClass s_sdSPI;
extern bool s_sdReady;
extern bool s_sdSpiUp;
extern size_t s_sdBootFreeIntBefore, s_sdBootFreeIntAfter;
extern size_t s_sdBootLfbIntBefore, s_sdBootLfbIntAfter;

// One mount attempt with full before/after heap accounting, usable from setup()
// and from a live serial command. `tag` names the call site in the JSON line.
bool sdMountAttempt(const char *tag, uint8_t maxFiles);
#endif
