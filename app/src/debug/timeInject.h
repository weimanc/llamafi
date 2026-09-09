#pragma once
// debug/timeInject.h — ADR-064 D5 (TASK-638): host-injected, freezable wall time.
//
// A golden render signature over a Clock DIGIT region is only writable if the
// digits are known and stationary. `set now <epoch> [freeze]` sets the system
// clock (settimeofday — SNTP will re-correct it on its next sync) and, with
// `freeze`, pins the value the Clock family READS so the face stops advancing
// while a signature is taken. Only readers that go through dbgLocalTime() see
// the freeze; the RTC keeps running. `set now thaw` releases it.
//
// Cost: two statics (time_t + bool) and one branch, SERIAL_DEBUG only. In a
// production build dbgLocalTime() is getLocalTime() and nothing else exists.
#include <time.h>
#include <Arduino.h>   // getLocalTime()

#ifdef SERIAL_DEBUG
void dbgTimeSet(time_t epoch, bool freeze);
void dbgTimeThaw();
bool dbgTimeFrozen(time_t *epochOut);
bool dbgLocalTime(struct tm *out);
#else
inline bool dbgLocalTime(struct tm *out) { return getLocalTime(out); }
#endif
