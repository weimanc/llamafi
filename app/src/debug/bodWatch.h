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
bool     bodWatchPoll(const char *tag);       // true if a trip was latched (logs)
bool     bodWatchPollQuiet(void);             // same, but silent — safe inside a burst
void     bodWatchClear(void);                 // drop a stale latch before a measurement
void     bodWatchTick(void);                  // rate-limited poll for loop()
uint32_t bodWatchTrips(void);
uint8_t  bodWatchThres(void);
// Persisted across a SW reset in RTC memory, so the arm threshold for the NEXT
// boot can be chosen from the console. The boot-window sag happens long before
// the console exists, so a runtime setter alone cannot sweep it.
void     bodWatchSetBootThres(uint8_t thres);
uint8_t  bodWatchBootThres(void);
// TASK-557 mitigation experiment. Bitmask, persisted in the same RTC_NOINIT
// block as the boot threshold, applied by boot.cpp across the WiFi-init window
// only (bit 0 = backlight off, bit 1 = reduced WiFi TX power). Runtime-selected
// rather than a build flag so a variant x threshold sweep costs a reboot, not a
// reflash — and so the whole experiment is one revert of one #ifdef block.
void     bodWatchSetBootMit(uint8_t mask);
uint8_t  bodWatchBootMit(void);
#else
static inline void     bodWatchArm(uint8_t)        {}
static inline bool     bodWatchPoll(const char *)  { return false; }
static inline bool     bodWatchPollQuiet(void)     { return false; }
static inline void     bodWatchClear(void)         {}
static inline void     bodWatchTick(void)          {}
static inline uint32_t bodWatchTrips(void)         { return 0; }
static inline uint8_t  bodWatchThres(void)         { return 0; }
static inline void     bodWatchSetBootThres(uint8_t) {}
static inline uint8_t  bodWatchBootThres(void)     { return 7; }
static inline void     bodWatchSetBootMit(uint8_t) {}
static inline uint8_t  bodWatchBootMit(void)       { return 0; }
#endif
