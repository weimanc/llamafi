#pragma once
// debug/bodWatch.h — TASK-557 supply telemetry.
//
// The ESP32 classic has no VDD ADC (S2/S3/C3 do; this chip does not), so the
// brownout detector's comparator is the ONLY on-die supply sensing available.
// This turns it into an instrument instead of a reset source: raise the
// threshold to the top of its range, disable the reset, and read the LATCHED
// interrupt status so a microsecond dip is still recorded by a slow poll.
//
// It reports on VDD3P3, not the 5 V input — see TASK-557. It cannot say the
// rail is "fine", only that it did or did not fall below the selected
// threshold (~2.43-2.80 V across the 8 levels per ESP-IDF's Kconfig).
//
// Compiled in only under -DBOD_WATCH (debug env). No-ops otherwise.

#include <stdint.h>

#ifdef BOD_WATCH
void     bodWatchArm(uint8_t thres);          // thres 0..7, 7 = highest voltage
bool     bodWatchPoll(const char *tag);       // true if a trip was latched
void     bodWatchTick(void);                  // rate-limited poll for loop()
uint32_t bodWatchTrips(void);
#else
static inline void     bodWatchArm(uint8_t)        {}
static inline bool     bodWatchPoll(const char *)  { return false; }
static inline void     bodWatchTick(void)          {}
static inline uint32_t bodWatchTrips(void)         { return 0; }
#endif
