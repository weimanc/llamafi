#pragma once
// perf.h — Tier-1 instrumentation for M-PERF (TASK-029).
//
// Tracks two things since the last heartbeat reset:
//   - loop iteration max (per loop() call)
//   - per-named-path max (Spotify poll, display redraw, touch input, etc.)
//
// Reset by heartbeat::tick() after it emits, so the values reported in each
// hb line cover only the window since the last hb. Stack high-water comes
// directly from FreeRTOS — no reset needed; it's monotonic-low.
//
// Usage from a hot path:
//   unsigned long t = millis();
//   doExpensiveThing();
//   perf::record("expensive.thing", millis() - t);
//
// Usage from loop():
//   unsigned long ls = millis();
//   ... loop body ...
//   perf::recordLoop(millis() - ls);

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace perf {

// TASK-278/M-WR-AUDIO-TASK (VE-2-3): 8→10 to fit the trio's shared budget —
// production sites were 5 (+screenlog.tick under SCREEN_LOG) before this;
// TASK-278 adds wr.connect (unconditional) + wr.pump (SERIAL_DEBUG-only,
// cross-task write — see webRadioApp.h OQ3). M-TASKBAR-FEEDBACK adds
// shell.switch, landing at exactly 10 production slots. TASK-402
// (M-WEBRADIO-POSBAR-SMOOTH, cross-feature edge X049) adds wr.posbar,
// 10→11 — single site inside WebRadioApp::_drawPosbar(), see that
// function's own comment for why it isn't instrumented at each caller.
// This constant is the single source of truth for that budget — bump it
// again before adding more.
constexpr int MAX_PATHS = 11;

struct Slot {
  const char *name;     // pointer-compared (always a string literal at call sites)
  uint32_t   maxMs;
};

inline Slot       *slots()       { static Slot s[MAX_PATHS] = {}; return s; }
inline uint32_t   &loopMaxRef()  { static uint32_t v = 0; return v; }

inline void record(const char *name, uint32_t ms) {
  Slot *s = slots();
  for (int i = 0; i < MAX_PATHS; ++i) {
    if (s[i].name == nullptr) {
      s[i].name = name;
      s[i].maxMs = ms;
      return;
    }
    if (s[i].name == name) {
      if (ms > s[i].maxMs) s[i].maxMs = ms;
      return;
    }
  }
  // overflow: silently drop. MAX_PATHS is set conservatively above the
  // count of instrumented paths.
}

inline void recordLoop(uint32_t ms) {
  if (ms > loopMaxRef()) loopMaxRef() = ms;
}

inline uint32_t loopMaxMs() { return loopMaxRef(); }

inline const char *worstPathName() {
  Slot *s = slots();
  const Slot *best = nullptr;
  for (int i = 0; i < MAX_PATHS && s[i].name; ++i) {
    if (best == nullptr || s[i].maxMs > best->maxMs) best = &s[i];
  }
  return best ? best->name : "(none)";
}

inline uint32_t worstPathMs() {
  Slot *s = slots();
  uint32_t best = 0;
  for (int i = 0; i < MAX_PATHS && s[i].name; ++i) {
    if (s[i].maxMs > best) best = s[i].maxMs;
  }
  return best;
}

inline uint32_t stackHwmBytes() {
  return (uint32_t)uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t);
}

inline void reset() {
  Slot *s = slots();
  for (int i = 0; i < MAX_PATHS; ++i) { s[i].name = nullptr; s[i].maxMs = 0; }
  loopMaxRef() = 0;
}

}  // namespace perf
