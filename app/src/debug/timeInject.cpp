// debug/timeInject.cpp — ADR-064 D5 (TASK-638). See timeInject.h.
#include "debug/timeInject.h"

#ifdef SERIAL_DEBUG
#include <sys/time.h>

static time_t s_frozenEpoch = 0;
static bool   s_frozen      = false;

void dbgTimeSet(time_t epoch, bool freeze) {
  struct timeval tv = { epoch, 0 };
  settimeofday(&tv, nullptr);
  s_frozenEpoch = epoch;
  s_frozen = freeze;
}

void dbgTimeThaw() { s_frozen = false; }

bool dbgTimeFrozen(time_t *epochOut) {
  if (epochOut) *epochOut = s_frozenEpoch;
  return s_frozen;
}

bool dbgLocalTime(struct tm *out) {
  if (s_frozen) {
    localtime_r(&s_frozenEpoch, out);
    return true;
  }
  return getLocalTime(out);
}
#endif
