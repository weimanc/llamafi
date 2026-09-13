#pragma once
// armedInjectors.h — TASK-635 (M-HARNESS2 R14), the one table `get armed`
// and `set injclear` both expand. See
// docs/architecture/designs/M-HARNESS2-armed-state-task635.md §2 — this is
// binding, not a paraphrase. No bitmask, no stored "armed" state: every
// predicate below reads the EXISTING variable the injector already sets, so
// `get armed` can never drift from what is actually armed. The one
// exception is `arenaHold`'s `s_consoleArenaHold` (1 B), because
// `mb_arena_active()` is also true during real playback and so cannot
// distinguish a console-held arena from one held by a real stream.
//
// Only compiled under SERIAL_DEBUG (same convention as the rest of
// debug/serialConsole/) — both call sites (cmdGet.cpp, cmdSet.cpp) already
// guard their whole body that way.
//
// X(name, armedExpr, clearStmt)
//   armedExpr — a bool-valued expression, evaluated once, no side effects.
//   clearStmt — a statement (braces/comma-expr allowed) that undoes the
//               armed state; only ever invoked when armedExpr was true.
//
// Membership is TASK-635 §2.2's three-clause rule; the exclusions (bod*,
// logLevel/logKeep, wifiPs, beaconWatch, cooldown, nvsSsid) are named with
// their reasons in the design doc §2.2, not repeated here — this file is
// the "in" list only.

#ifdef SERIAL_DEBUG

#include "debug/timeInject.h"   // dbgTimeFrozen()/dbgTimeThaw()
#include "audio/audioEngine.h"  // s_aeDmaFloorOverride, AE_I2S_DMA_FLOOR_BYTES,
                                 // s_aeNoArenaInject, s_aeFailAudioInject
#include "mem/arena/mb_arena.h" // mb_arena_release()
#include "dataTask.h"           // dataTask::debug{Peek,Break,Clear}Cert*,
                                 // debug{Force,Peek}PlaneRadarParseFail,
                                 // dbgGeocodeState/dbgClearGeocodeInject
#include "spotifyTask.h"       // spotifyTask::dbgArmedWedge()/dbgBgPollOff()
#include "shell/appTable.h"     // g_WebRadioApp, g_PlaneRadarApp,
                                 // g_TeletextApp, g_backlight
#include "shell/shellState.h"   // shell::state().busyForced (TASK-617)
#include "shell/shellDispatch.h" // shell::setBusy() (TASK-617)

// TASK-426 A/B cookie pair (boot/boot.cpp, RTC_NOINIT_ATTR) — declared
// extern here rather than pulling in boot.cpp's setup()-scoped
// casRetryDisabled() (static inline, not exported). Value must stay in
// lockstep with boot.cpp's kCasRetryCookie / cmdSet.cpp's copy.
extern uint32_t g_casRetryCookie;
extern uint32_t g_casRetryOff;
static constexpr uint32_t kArmedInjCasRetryCookie = 0x426AB1FEu;

// TASK-635's one new byte (cmdSet.cpp) — set/cleared by `set arenaHold`.
extern bool s_consoleArenaHold;

static inline bool dbgArmedGeocode() {
    bool parked = false;
    dataTask::dbgGeocodeState(&parked, nullptr, nullptr);
    return parked;
}

#define ARMED_INJECTORS_TABLE(X)                                             \
  X(nowFrozen,                                                               \
    dbgTimeFrozen(nullptr),                                                  \
    dbgTimeThaw())                                                           \
  X(aeDmaFloor,                                                              \
    (s_aeDmaFloorOverride != AE_I2S_DMA_FLOOR_BYTES),                        \
    (s_aeDmaFloorOverride = AE_I2S_DMA_FLOOR_BYTES))                         \
  X(aeNoArena,                                                               \
    s_aeNoArenaInject,                                                       \
    (s_aeNoArenaInject = false))                                             \
  X(aeFailAudio,                                                             \
    s_aeFailAudioInject,                                                     \
    (s_aeFailAudioInject = false))                                           \
  X(arenaHold,                                                               \
    s_consoleArenaHold,                                                      \
    (mb_arena_release(), s_consoleArenaHold = false))                        \
  X(casRetryOff,                                                             \
    (g_casRetryCookie == kArmedInjCasRetryCookie && g_casRetryOff != 0),     \
    (g_casRetryCookie = 0))                                                  \
  X(certbreak,                                                               \
    (dataTask::debugPeekCertBreak() >= 0),                                   \
    dataTask::debugClearCertBreak())                                        \
  X(prForceParseFail,                                                        \
    (dataTask::debugPeekForcedParseFailCount() > 0),                         \
    dataTask::debugForcePlaneRadarParseFail(0))                             \
  X(geocode,                                                                 \
    dbgArmedGeocode(),                                                       \
    dataTask::dbgClearGeocodeInject())                                      \
  X(wrDeadUrls,                                                              \
    g_WebRadioApp.dbgArmedWrDeadUrls(),                                      \
    g_WebRadioApp.dbgSet("wrDeadUrls", "0"))                                \
  X(wrPosbarSimDrain,                                                        \
    g_WebRadioApp.dbgArmedPosbarSimDrain(),                                  \
    g_WebRadioApp.dbgSet("wrPosbarSimDrain", "0"))                          \
  X(prInject,                                                                \
    g_PlaneRadarApp.dbgArmedInjected(),                                      \
    g_PlaneRadarApp.dbgSet("prClearInject", "1"))                          \
  X(teletextContent,                                                         \
    g_TeletextApp.dbgArmedInjectedContent(),                                 \
    g_TeletextApp.dbgClearInjectedContent())                                \
  X(ldrRaw,                                                                  \
    g_backlight.injected(),                                                  \
    g_backlight.injectLdr(-1))                                               \
  X(spotifyWedge,                                                            \
    spotifyTask::dbgArmedWedge(),                                            \
    spotifyTask::dbg_set("spotifyWedge", "0"))                             \
  X(bgPollOff,                                                               \
    spotifyTask::dbgBgPollOff(),                                             \
    spotifyTask::dbg_set("bgPoll", "1"))                                    \
  X(shellBusy,                                                               \
    shell::state().busyForced,                                              \
    shell::setBusy(false))

#endif  // SERIAL_DEBUG
