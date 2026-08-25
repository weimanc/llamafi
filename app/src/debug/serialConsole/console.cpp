// debug/serialConsole/console.cpp — dispatch core, out-of-line (M-SRCLAYOUT
// Stage E / TASK-471). kCmds[]/kNumCmds/the injection ring are declared in
// consoleShared.h; this TU owns their one definition, plus cmdReconnect (the
// one command that ships in every build, ADR-021 Decision 4) and
// cmdPlayerCycle (M-TESTBASE §8 — SERIAL_DEBUG only, "body stays in this
// file" per the original design, just relocated with the file itself).
#include "debug/serialConsole/console.h"

#include <Arduino.h>
#include <string.h>
#include "debug/serialConsole/consoleShared.h"
#include "appShell.h"                     // AppId, currentAppId, TouchPhase, switchApp
#include "shell/appTable.h"               // g_apps[]
#include "shell/shellDispatch.h"          // resolvePlayerTap/isPlayerModeApp/shell::*
#include "shell/shellState.h"             // shell::state()
#include "shell/taskbar.h"                 // TASKBAR_APP_COUNT, renderTaskbar
#include "settingsStorage.h"              // g_settings
#include "spotifyTask.h"
#include "logSink.h"                      // LOG_D

#ifdef SERIAL_DEBUG
#include "winamp/winampDisplay.h"
#include "debug/serialConsole/cmdTouch.h"
#include "debug/serialConsole/cmdGet.h"
#include "debug/serialConsole/cmdSet.h"
#include "debug/serialConsole/cmdMisc.h"
#include "debug/serialConsole/cmdSd.h"
#include "debug/serialConsole/cmdSystem.h"

extern WinampDisplay winampDisplay;       // defined in main.cpp
#endif

extern TFT_eSPI tft;                      // defined in main.cpp / display backend

// TASK-056c/h: `reconnect` (TLS reset + force poll) is the one command that
// ships in every build, not just SERIAL_DEBUG ones (ADR-021 Decision 4).
static void cmdReconnect(const char *) {
  spotifyTask::resetTls();
  spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
  Serial.println("{\"ok\":true,\"cmd\":\"reconnect\"}");
}

// TASK-056e: touch-injection ring buffer (SERIAL_DEBUG only). Definitions
// only (declared in consoleShared.h) — cmdTouch.cpp's cmdDrag/cmdRelease/
// cmdTap write these, from a different translation unit.
#ifdef SERIAL_DEBUG
InjectionStep s_injectQueue[64];
int s_injectHead = 0, s_injectTail = 0;
bool s_dragPending = false;
bool s_injectIsFirst = false;  // first non-release item → Press, rest → Move
int s_pendingDragX1, s_pendingDragY1,
    s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps;
int s_injectTotal = 0;  // total steps for LOG_D %d/%d
// TASK-277 (VE-1-1/DEV-1-2): the release step dispatches at the LAST sample's
// coordinates, not (0,0) — otherwise a drag's Release lands outside every
// hit-test region and gesture-end logic sees garbage geometry.
int s_lastInjectX = 0, s_lastInjectY = 0;
// TASK-277 (VE-1-3): bare `release` command marks its sentinel so the drain
// emits {"cmd":"release"} instead of the drag JSON.
bool s_bareRelease = false;

// ── M-TESTBASE §8: the mode-cycle OPERATION, decoupled from its hit-surface ──
// The gesture that cycles player mode has moved once already (eject -> taskbar
// slot, TASK-413/414) and the move silently broke the harness once and a design
// document once, because both bound to the GESTURE when they meant the
// OPERATION. Tests call this; exactly one test (T_PMT_00) asserts that the
// surface named by `get playerBind` still reaches it.
//
// Deliberately calls the SAME shared helper both production dispatch sites call
// (ADR-059 D6 amendment) rather than re-deriving the cycle — a second cycle path
// is the TASK-406 defect class this decision exists to prevent.
static void cmdPlayerCycle(const char *) {
  const uint8_t before = g_settings.playerMode;
  AppId target = resolvePlayerTap(AppId::Spotify, isPlayerModeApp(currentAppId));
  switchApp(target);
  Serial.printf("{\"ok\":true,\"cmd\":\"playerCycle\","
                "\"from\":%u,\"to\":%u,\"appId\":%d,\"last\":true}\n",
                (unsigned)before, (unsigned)g_settings.playerMode, (int)target);
}
#endif

const SerialCmd kCmds[] = {
  { "reconnect", cmdReconnect, "TLS reset + force poll", "" },
#ifdef SERIAL_DEBUG
  { "tap",  cmdTap,  "inject touch point",              "<x> <y>"                            },
  { "drag", cmdDrag, "inject touch drag (queue-drain)", "<x1> <y1> <x2> <y2> <steps> [hold]" },
  { "release", cmdRelease, "end a held injected gesture", ""                                 },
  { "tick", cmdTick, "inject synthetic scroll ticks",   "[n=1] [dtMs=20]"                    },
  { "get",  cmdGet,  "read internal state",             "<snapshot|backoff|heap|stacks|cooldown|shellCooldown>"    },
  { "set",  cmdSet,  "write debug state",               "<backoff|cooldown> <val>"            },
  { "switchApp", cmdSwitchApp, "switch active app by id", "<appId 0..8>"                      },
  { "playerCycle", cmdPlayerCycle, "M-TESTBASE: cycle player mode via resolvePlayerTap (surface-independent)", "" },
  { "info", cmdInfo, "git+elf+build+snapshot summary",  ""                                   },
  { "screendump", cmdScreenDump, "read back TFT GRAM, base64 RGB565 bands", "[x=0] [y=0] [w=320] [h=240]" },
  { "colorprobe", cmdColorProbe, "TASK-340: fillRect/pushRect known values, readRect them back", "" },
  { "sdprobe", cmdSdProbe, "TASK-408: SD card mount/heap/LFN/listDir/read-bench probe", "[reads=5000]" },
  { "sdcycle", cmdSdCycle, "TASK-408 T_SD_08: N live mount/unmount cycles, heap drift", "[cycles=20]" },
  { "sdmem", cmdSdMem, "TASK-408: FATFS ctx sizing + contiguous-calloc ladder", "" },
  { "sdmount", cmdSdMount, "TASK-408: live mount attempt at N slots, optional SPI Hz", "[maxFiles] [freqHz]" },
  { "sdumount", cmdSdUmount, "TASK-408: unmount, report heap actually returned", "" },
  { "sdclean", cmdSdClean, "TASK-408: delete sdprobe fixtures (/probelist, /probebench.bin)", "" },
  { "sdwrite", cmdSdWrite, "TASK-408: isolated sequential write of N 512B chunks", "[chunks=64] [heapCheckEvery=0]" },
  { "sdls", cmdSdLs, "TASK-408: list a directory with sizes", "[dir=/] [q=quiet | n=quiet,no stat]" },
  { "sdopendir", cmdSdOpenDir, "TASK-521: raw opendir() with errno/timing/heap — which mechanism fails", "[dir=/]" },
  { "sdslots", cmdSdSlots, "TASK-521: how many open-file slots are free right now", "<file>" },
  { "sdmbr", cmdSdMbr, "TASK-408: raw sector 0 / partition table / volume ID (no mount needed)", "" },
  { "sdread", cmdSdRead, "TASK-408: read-only benchmark against an existing file", "<reads> <path>" },
  { "sdmkdir", cmdSdMkdir, "TASK-415: create a directory (test fixtures)", "<path>" },
  { "sdput", cmdSdPut, "TASK-415: write/append <=90 B of base64 to a file (test fixtures)", "<w|a> <base64|-> <path>" },
  { "help",   cmdHelp,   "list commands",                   ""                                   },
  { "reboot", cmdReboot, "software reset (ESP.restart)",   ""                                   },
  { "advance", cmdAdvance, "TASK-418: step the play-order engine, no audio (ADR-059 D12)", "<next|prev>" },
#endif
};
const int kNumCmds = sizeof(kCmds) / sizeof(kCmds[0]);

// TASK-056e: drain one injection step per loop() iteration.
void drainInjectionQueue() {
#ifdef SERIAL_DEBUG
  if (s_injectHead == s_injectTail) return;
  InjectionStep &step = s_injectQueue[s_injectHead % 64];
  // TASK-501: WINAMP_DISPLAY is unconditionally defined — the (void)step;
  // no-WINAMP_DISPLAY placeholder this #ifdef used to guard against is gone.
  if (step.release) {
    if (winampDisplay.tbIsDragging()) {
      // Taskbar drag release — TASK-279: same shared commit path as production
      // [VE-3-1]. TASK-280: also set the same 300 ms post-gesture cooldown
      // appHandleInput() sets after its shellTbRelease() call, so the injected
      // path can't double-fire faster than a real gesture could.
      shellTbRelease(shell::state().lastTouchY);
      shell::state().cooldownMs = millis() + 300;
      renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
    } else {
      // TASK-277 reroute (VE-1-1 blocker + DEV-1-2): dispatch to the ACTIVE
      // app's handleInput at the last sample's coordinates — previously
      // hardwired to winampDisplay.handleWinampInput(Release, 0, 0), so an
      // injected WebRadio drag delivered Press/Move to one machine and
      // Release to another (gesture never ended). Documented behaviour
      // deltas: (i) injected Releases now pass SpotifyApp's eject intercept
      // with real coords; (ii) every app now sees injected Releases.
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(TouchPhase::Release,
                                               s_lastInjectX, s_lastInjectY);
    }
    winampDisplay._injectingDrag = false;
    s_dragPending = false;
    if (s_bareRelease) {
      s_bareRelease = false;
      Serial.printf("{\"ok\":true,\"cmd\":\"release\",\"x\":%d,\"y\":%d}\n",
                    s_lastInjectX, s_lastInjectY);
    } else {
      Serial.printf("{\"ok\":true,\"cmd\":\"drag\","
                    "\"x1\":%d,\"y1\":%d,\"x2\":%d,\"y2\":%d,\"steps\":%d}\n",
                    s_pendingDragX1, s_pendingDragY1,
                    s_pendingDragX2, s_pendingDragY2, s_pendingDragSteps);
    }
  } else {
    LOG_D("serial", "inject sample %d/%d sx=%d sy=%d",
          s_injectHead + 1, s_injectTotal - 1, step.sx, step.sy);
    if (step.sx >= TASKBAR_X) {
      // Taskbar zone: route to gesture handlers, not app handleInput.
      shell::state().lastTouchY = step.sy;
      if (!winampDisplay.tbIsDragging()) {
        winampDisplay.tbGesturePress(step.sy);
        shellTbPress(step.sy);  // TASK-279 (F-a): same shared paint as production
      } else {
        if (winampDisplay.tbGestureContinue(step.sy, TASKBAR_APP_COUNT))
          renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), TASKBAR_APP_COUNT,
                false, shell::activeError(), shell::activeConnecting());
        // TASK-279 (F-a): cancel the highlight at scroll-start [DEV-3-1].
        if (winampDisplay.tbIsScrolling()) shellTbCancel();
      }
    } else {
      // TASK-277 reroute (VE-1-6): canvas samples go to the active app —
      // Spotify's path is unchanged in effect (SpotifyApp::handleInput
      // forwards Press/Move to handleWinampInput; eject intercept is
      // Release-only), and every other app now receives injected drags.
      s_lastInjectX = step.sx;
      s_lastInjectY = step.sy;
      TouchPhase ph = s_injectIsFirst ? TouchPhase::Press : TouchPhase::Move;
      s_injectIsFirst = false;
      if (g_apps[(int)currentAppId])
        g_apps[(int)currentAppId]->handleInput(ph, step.sx, step.sy);
    }
  }
  ++s_injectHead;
#endif
}

void handleSerialCommands() {
  static char buf[160];  // widened: 64 was too small for long-URL commands (wrUrl, wrDeadUrls)
  static int  len = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      buf[len] = '\0';
      if (len > 0) {
        // Split "name args" at first space; args may be "".
        char *sp = strchr(buf, ' ');
        const char *args = sp ? sp + 1 : "";
        if (sp) *sp = '\0';
        bool handled = false;
        for (int i = 0; i < kNumCmds; ++i) {
          if (strcmp(buf, kCmds[i].name) == 0) {
            kCmds[i].fn(args);
            handled = true;
            break;
          }
        }
        if (!handled) {
          Serial.printf("{\"ok\":false,\"error\":\"unknown command\",\"cmd\":\"%s\"}\n", buf);
        }
      }
      len = 0;
    } else if (len < (int)sizeof(buf) - 1) {
      buf[len++] = c;
    } else {
      // Buffer full before newline — drop the partial, WARN, resync on next '\n'.
      // (Next newline will be misaligned; host-side scripts must treat the
      // following line as garbage.)
      Serial.println("{\"ok\":false,\"error\":\"line too long\"}");
      len = 0;
    }
  }
}
