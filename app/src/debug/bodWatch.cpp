// debug/bodWatch.cpp — TASK-557 supply telemetry. See bodWatch.h.
#include "debug/bodWatch.h"

#ifdef BOD_WATCH
#include <Arduino.h>
#include "soc/rtc_cntl_reg.h"
#include "soc/soc.h"

// RTC_NOINIT survives a SW reset (not a power cycle), which is exactly the
// scope needed: `bod <n>` then `reboot` sweeps the boot-window threshold
// without a reflash. Guarded by a magic so a cold boot falls back to 7.
RTC_NOINIT_ATTR static uint32_t s_bootThresMagic;
RTC_NOINIT_ATTR static uint8_t  s_bootThres;
#define BOD_BOOT_MAGIC 0xB0D7A15Eu

static uint32_t s_trips = 0;
static uint8_t  s_thres = 0;
static bool     s_armed = false;

void bodWatchArm(uint8_t thres) {
  if (thres > 7) thres = 7;
  const uint32_t before = REG_READ(RTC_CNTL_BROWN_OUT_REG);
  // Captured BEFORE we clear it: ESP-IDF's own brownout path on ESP32 is the
  // interrupt (its ISR panics and restarts), not the hardware reset — rstEna
  // reads 0 out of the box. Whether intEna reads 1 here decides whether that
  // handler is what turns a supply sag into a reboot loop.
  const uint32_t intEnaBefore = REG_READ(RTC_CNTL_INT_ENA_REG) & RTC_CNTL_BROWN_OUT_INT_ENA;

  // INT_ENA stays OFF deliberately. ESP-IDF installs a brownout ISR that
  // panics ("Brownout detector was triggered"), which would destroy exactly
  // the observation we want. The RAW status latches without the interrupt
  // being enabled, so the dip is recorded and the chip keeps running.
  REG_CLR_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_BROWN_OUT_INT_ENA);

  REG_SET_FIELD(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_DBROWN_OUT_THRES, thres);
  REG_SET_BIT(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_BROWN_OUT_ENA);
  // The whole point: detect without resetting. RISK, stated plainly — a real
  // deep brownout will no longer reset the chip, so a flash/SD write in flight
  // during a sag can corrupt. That is why this is -DBOD_WATCH on the debug env
  // and never production.
  REG_CLR_BIT(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_BROWN_OUT_RST_ENA);

  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  s_thres = thres;
  s_armed = true;
  s_trips = 0;

  const uint32_t after = REG_READ(RTC_CNTL_BROWN_OUT_REG);
  // regBefore carries the level ESP-IDF booted with (sdkconfig says
  // CONFIG_ESP32_BROWNOUT_DET_LVL=0), so the two values together confirm the
  // write landed rather than assuming it did.
  Serial.printf("[bod] armed thres=%u regBefore=0x%08x regAfter=0x%08x "
                "ena=%d rstEna=%d intEnaBefore=%d intEna=%d\n",
                (unsigned)thres, (unsigned)before, (unsigned)after,
                (after & RTC_CNTL_BROWN_OUT_ENA) ? 1 : 0,
                (after & RTC_CNTL_BROWN_OUT_RST_ENA) ? 1 : 0,
                intEnaBefore ? 1 : 0,
                (REG_READ(RTC_CNTL_INT_ENA_REG) & RTC_CNTL_BROWN_OUT_INT_ENA) ? 1 : 0);
}

void bodWatchClear(void) {
  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
}

// Silent variant. Printing from inside a burst would interleave with the burst
// itself — which is precisely the artefact that made an earlier run look like
// 0.4% link loss — so a measurement loop counts trips and reports afterwards.
bool bodWatchPollQuiet(void) {
  if (!s_armed) return false;
  if (!(REG_READ(RTC_CNTL_INT_RAW_REG) & RTC_CNTL_BROWN_OUT_INT_RAW)) return false;
  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  s_trips++;
  return true;
}

uint8_t bodWatchThres(void) { return s_thres; }

void bodWatchSetBootThres(uint8_t thres) {
  if (thres > 7) thres = 7;
  s_bootThres = thres;
  s_bootThresMagic = BOD_BOOT_MAGIC;
}

uint8_t bodWatchBootThres(void) {
  return (s_bootThresMagic == BOD_BOOT_MAGIC && s_bootThres <= 7) ? s_bootThres : 7;
}

bool bodWatchPoll(const char *tag) {
  if (!s_armed) return false;
  if (!(REG_READ(RTC_CNTL_INT_RAW_REG) & RTC_CNTL_BROWN_OUT_INT_RAW)) return false;
  const uint32_t reg = REG_READ(RTC_CNTL_BROWN_OUT_REG);
  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  s_trips++;
  // `det` is the live comparator; `TRIP` is the latch. det=0 with a TRIP means
  // the rail already recovered by the time we looked, which is the expected
  // shape for a transient and is why the latch is what we poll.
  Serial.printf("[bod] TRIP tag=%s t=%lums thres=%u trips=%lu det=%d\n",
                tag ? tag : "?", (unsigned long)millis(), (unsigned)s_thres,
                (unsigned long)s_trips, (reg & RTC_CNTL_BROWN_OUT_DET) ? 1 : 0);
  return true;
}

void bodWatchTick(void) {
  static unsigned long last = 0;
  const unsigned long now = millis();
  if (now - last < 200) return;   // the latch holds; polling faster buys nothing
  last = now;
  bodWatchPoll("run");
}

uint32_t bodWatchTrips(void) { return s_trips; }
#endif  // BOD_WATCH
