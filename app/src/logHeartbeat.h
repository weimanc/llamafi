#pragma once
// logHeartbeat.h — 30 s INFO heartbeat tick (ADR-010, TASK-016d).
//
// Single-line key=value status, tag=`hb`. Super-loop tick (per ADR-010
// open-question lean), millis()-gated. Counters are reset on reboot.
// Format is deliberately greppable:
//
//   I (12345) hb: display=winamp wifi=rssi(-58) heap=128k uptime=00:42:18 build=2026-05-07-114500
//
// Optional poll counters and last-status are wired in by call sites
// (spotifyLogic) via heartbeat::recordPoll(); none of the existing
// code touches them yet, so for now those fields stay zero.

#include <Arduino.h>
#include <WiFi.h>
#include <esp_log.h>

#include "logSink.h"
#include "perf.h"
#include "spotifyTask.h"

extern uint32_t g_lastRenderMs;  // TASK-059: defined in spotifyLogic.h

namespace heartbeat {

constexpr unsigned long PERIOD_MS = 30000;

inline unsigned long &nextTickRef()      { static unsigned long t = 0; return t; }
inline uint32_t      &pollAttemptsRef()  { static uint32_t v = 0; return v; }
inline uint32_t      &pollSuccessRef()   { static uint32_t v = 0; return v; }
inline int           &lastHttpRef()      { static int v = 0; return v; }
inline uint32_t      &blockMaxMsRef()    { static uint32_t v = 0; return v; }

inline void recordPoll(bool ok, int httpCode) {
  pollAttemptsRef()++;
  if (ok) pollSuccessRef()++;
  lastHttpRef() = httpCode;
}

// ADR-011: track the longest synchronous Spotify call since the last
// heartbeat. Reset to 0 inside tick() after emitting.
inline void recordBlock(uint32_t ms) {
  if (ms > blockMaxMsRef()) blockMaxMsRef() = ms;
}

inline const char *displayName() {
#if defined WINAMP_DISPLAY
  return "winamp";
#elif defined YELLOW_DISPLAY
  return "cyd";
#elif defined MATRIX_DISPLAY
  return "matrix";
#else
  return "?";
#endif
}

inline void formatUptime(char *buf, size_t bufsz, unsigned long ms) {
  unsigned long s = ms / 1000;
  unsigned long h = s / 3600;
  unsigned long m = (s / 60) % 60;
  unsigned long sec = s % 60;
  snprintf(buf, bufsz, "%02lu:%02lu:%02lu", h, m, sec);
}

inline void tick() {
  unsigned long now = millis();
  if (now < nextTickRef()) return;
  nextTickRef() = now + PERIOD_MS;

  char up[12];
  formatUptime(up, sizeof(up), now);
  int rssi = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  uint32_t heap = ESP.getFreeHeap();
  uint32_t blockMax = blockMaxMsRef();
  blockMaxMsRef() = 0;  // window resets each emit

  uint32_t loopMax = perf::loopMaxMs();
  const char *worstName = perf::worstPathName();
  uint32_t worstMs = perf::worstPathMs();
  uint32_t stackHwm = perf::stackHwmBytes();
  perf::reset();

  uint32_t lastPollAgeMs  = spotifyTask::lastSuccessfulPollAgeMs();
  uint32_t nextPollMs     = spotifyTask::nextPollInMs();
  uint32_t lastRenderAgeMs = (g_lastRenderMs == 0) ? 0
                              : (uint32_t)(now - g_lastRenderMs);

  LOG_I("hb",
        "display=%s wifi=rssi(%d) heap=%uk stack_hwm=%ub uptime=%s "
        "poll=%u/%u last=%d block_max=%ums "
        "loop_max=%ums slow=%s:%ums "
        "last_poll_age_ms=%lu next_poll_in_ms=%lu last_render_age_ms=%lu "
        "build=%s-%s",
        displayName(),
        rssi,
        (unsigned)(heap / 1024),
        (unsigned)stackHwm,
        up,
        (unsigned)pollSuccessRef(), (unsigned)pollAttemptsRef(),
        lastHttpRef(),
        (unsigned)blockMax,
        (unsigned)loopMax,
        worstName, (unsigned)worstMs,
        (unsigned long)lastPollAgeMs, (unsigned long)nextPollMs,
        (unsigned long)lastRenderAgeMs,
        __DATE__, __TIME__);
}

}  // namespace heartbeat
