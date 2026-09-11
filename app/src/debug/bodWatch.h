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
//
// TASK-678 (F-1) adds an interrupt-driven capture path on top of the polled
// latch above (still kept — `bod`/`bodmit`'s reboot-sweep workflow and
// serialburst's inline poll are unchanged): a lock-free ring of {timestamp,
// duration, per-event depth, context}, drained by loop() into an extended
// `[bod] TRIP` line and `get bod`'s JSON. See PROP-011-rig-ground-truth.md
// §3.1 for the design and PROP-011-runbook.md §1 F-1 for the acceptance
// criteria.

#include <stdint.h>

// A snapshot of the ring's running stats — `get bod`'s payload. Defined
// unconditionally (cheap, header-only) so cmdGet.cpp can include this header
// without an #ifdef just to name the type; the accessor itself is a no-op
// stub without BOD_WATCH.
struct BodSnapshot {
  uint32_t count;         // total events captured since bodWatchArm()
  uint32_t dropped;       // ring overflow — events lost to drop-oldest
  uint32_t firstUs;       // esp_timer_get_time() of the first event
  uint32_t lastUs;        // esp_timer_get_time() of the most recent event
  uint8_t  minLevel;      // lowest threshold level any event's ladder reached (8 = never tripped)
  uint16_t maxDurUs;      // longest bounded-spin duration observed
  uint32_t hist[8];       // count of events whose ladder bottomed at each level
  uint8_t  phaseAtFirst;  // boot-phase context byte captured at the first event
  uint8_t  thres;         // threshold currently armed
  bool     armed;
  uint32_t rearms;        // consumer-side INT re-arms since arm (one per captured event)
  uint32_t holdoffs;      // re-arm attempts skipped because DET was still asserted
  bool     disarmed;      // ISR has fired and loop() has not yet re-armed it
};

#ifdef BOD_WATCH
void     bodWatchArm(uint8_t thres);          // thres 0..7, 7 = highest voltage
bool     bodWatchPoll(const char *tag);       // true if a trip was latched (logs)
bool     bodWatchPollQuiet(void);             // same, but silent — safe inside a burst
void     bodWatchClear(void);                 // drop a stale latch before a measurement
void     bodWatchTick(void);                  // rate-limited poll + ring-drain for loop()
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

// ── F-1: interrupt-driven capture ──────────────────────────────────────────
void     bodWatchGetSnapshot(BodSnapshot *out);   // `get bod`
// Console `mark <label>` — stamps esp_timer_get_time() only; no ring entry.
void     bodWatchMark(const char *label);
// `set fault bod <level>` — invokes the same event-capture path a real trip
// takes, with a synthetic minLevel, so the R34 runtime gate can prove the
// harness parses `[bod] TRIP`/`get bod` without a real supply sag.
void     bodWatchFault(uint8_t level);
// Context shadow — plain globals the ISR reads (no driver calls from ISR
// context); pushed from loop()-side code that already knows these values
// (boot.cpp's BOOTPHASE macro, the WiFi/backlight mitigation window, the SD
// boot-mount call). Safe to call from any non-ISR context at any time.
void     bodWatchSetCtxBoot(uint8_t phase);
void     bodWatchSetCtxWifi(bool up);
void     bodWatchSetCtxBacklight(uint8_t duty8);   // raw 0..255 LEDC duty
void     bodWatchSetCtxSdBusy(bool busy);
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
static inline void     bodWatchGetSnapshot(BodSnapshot *out) { if (out) *out = BodSnapshot{}; }
static inline void     bodWatchMark(const char *)  {}
static inline void     bodWatchFault(uint8_t)      {}
static inline void     bodWatchSetCtxBoot(uint8_t) {}
static inline void     bodWatchSetCtxWifi(bool)    {}
static inline void     bodWatchSetCtxBacklight(uint8_t) {}
static inline void     bodWatchSetCtxSdBusy(bool)  {}
#endif
