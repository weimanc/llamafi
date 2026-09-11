// debug/bodWatch.cpp — TASK-557 supply telemetry. See bodWatch.h.
#include "debug/bodWatch.h"

#ifdef BOD_WATCH
#include <Arduino.h>
#include "soc/rtc_cntl_reg.h"
#include "soc/soc.h"
#include "driver/rtc_cntl.h"   // rtc_isr_register()
#include "esp_rom_sys.h"       // esp_rom_delay_us() — ISR-safe busy wait
#include "esp_timer.h"         // esp_timer_get_time()
#include <string.h>            // strcmp() — F-6 boot-window tag check

// esp_brownout_disable() deregisters IDF's own brownout ISR (which panics and
// restarts the chip — exactly what this module exists to avoid) so this
// module's handler can own the RTC brownout interrupt instead. Exported from
// the precompiled libesp_system.a (TASK-678 F-1 step 0, confirmed via `nm`)
// but not declared in any public header of this IDF (4.4 / Arduino-ESP32
// 2.0.17) — `esp_system/port/public_compat/brownout.h` exists but is not on
// this build's include path, so it is declared here instead.
extern "C" void esp_brownout_disable(void);

// RTC_NOINIT survives a SW reset (not a power cycle), which is exactly the
// scope needed: `bod <n>` then `reboot` sweeps the boot-window threshold
// without a reflash. Guarded by a magic so a cold boot falls back to 7.
RTC_NOINIT_ATTR static uint32_t s_bootThresMagic;
RTC_NOINIT_ATTR static uint8_t  s_bootThres;
RTC_NOINIT_ATTR static uint8_t  s_bootMit;      // TASK-557 mitigation mask
RTC_NOINIT_ATTR static uint8_t  s_descendPersist;   // F-6: 0/1, survives `reboot`
RTC_NOINIT_ATTR static uint32_t s_quietMsPersist;   // F-6: survives `reboot`
#define BOD_BOOT_MAGIC 0xB0D7A15Eu

static uint32_t s_trips = 0;
static uint8_t  s_thres = 0;
static bool     s_armed = false;
static bool     s_isrInstalled = false;

// ── F-1: interrupt-driven ring ──────────────────────────────────────────
// Bounded spin measuring how long BROWN_OUT_DET stays asserted; 1-2 ms is
// the design's own cap (PROP-011-rig-ground-truth.md §3.1) — long enough to
// separate an inrush spike from a slow sag, short enough that a shared RTC
// ISR stall stays tolerable on a rig build.
#define BOD_SPIN_CAP_US 2000
// Per-ladder-step settle spin. UNMEASURED — the ground-truth doc calls this
// out explicitly: "comparator settle time after a threshold write is
// unknown — measure it first". This value is a placeholder pending that DUT
// measurement (PROP-011-runbook.md §1 F-1 acceptance, left OPEN for the next
// reflash); too short and `minLevel` under-reports depth.
#define BOD_LADDER_SETTLE_US 5

#define BOD_RING_SIZE 64
struct BodRingEntry {
  uint32_t tUs;
  uint16_t durUs;
  uint8_t  minLevel;
  uint8_t  ctx;
};
static volatile BodRingEntry s_ring[BOD_RING_SIZE];
static volatile uint8_t  s_ringHead = 0;    // next write slot — ISR-owned
static volatile uint8_t  s_ringTail = 0;    // next read slot — consumer-owned
static volatile uint32_t s_ringDrops = 0;   // entries lost to a full ring
static volatile uint32_t s_ringCount = 0;   // total events captured since arm
static volatile uint32_t s_firstUs = 0;
static volatile uint32_t s_lastUs = 0;
static volatile uint8_t  s_minLevelEver = 8;   // 8 = "never tripped"
static volatile uint16_t s_maxDurUs = 0;
static volatile uint8_t  s_phaseAtFirst = 0xFF;
static volatile uint32_t s_histByLevel[8] = {0, 0, 0, 0, 0, 0, 0, 0};
// One event per re-arm. The ISR disarms INT_ENA on exit; loop() re-arms it
// at most every 200 ms and only once DET has cleared. A level-asserted latch
// re-fired the ISR back-to-back on the first F-1 flash (2026-09-11): loopTask
// starved, TASK_WDT at 15 s, boot loop. Rate-limiting in the consumer makes a
// storm impossible by construction; `holdoffs` counts how often the rail was
// still low at re-arm time, which is itself a duration measurement.
static volatile uint8_t  s_isrDisarmed = 0;
static volatile uint32_t s_rearms = 0;
static volatile uint32_t s_holdoffs = 0;

// ── F-6: adaptive-descent depth ──────────────────────────────────────────
// s_thres doubles as "the level currently armed" once descent is live — it
// still starts at (and the ISR ladder still bases itself on, and restores
// to) the boot-configured level, but bodWatchRearm() may now move it down
// after a trip, or bodWatchTick() may move it back up after a quiet spell.
// s_baseLevel is the fixed ceiling (the boot threshold at bodWatchArm()
// time) that quiet-timeout steps never rise above.
#define BOD_DESCEND_QUIET_MS_DEFAULT 30000
static bool     s_descendEnabled = false;
static uint8_t  s_baseLevel = 7;
static uint8_t  s_floor = 8;             // 8 = descent has never stepped down
static uint32_t s_stepsDown = 0;
static uint32_t s_stepsUp = 0;
static uint32_t s_quietMs = BOD_DESCEND_QUIET_MS_DEFAULT;
static unsigned long s_lastLevelChangeMs = 0;

// Context shadow — plain globals the ISR only READS. Written exclusively
// from non-ISR (loop/setup) code via the bodWatchSetCtx*() setters, so the
// ISR never calls a driver function to learn "what was the board doing"
// (PROP-011-rig-ground-truth.md §3.1's "context" row).
static volatile uint8_t s_ctxBoot = 0;        // bits [2:0]
static volatile uint8_t s_ctxWifiUp = 0;      // bit 3
static volatile uint8_t s_ctxSdBusy = 0;      // bit 4
static volatile uint8_t s_ctxBacklight = 0;   // bits [7:5], bucketed 0..7

static inline uint8_t packCtx() {
  return (uint8_t)((s_ctxBoot & 0x07) |
                    ((s_ctxWifiUp & 1) << 3) |
                    ((s_ctxSdBusy & 1) << 4) |
                    ((s_ctxBacklight & 0x07) << 5));
}

// Shared by the real ISR and bodWatchFault()'s synthetic invocation. Not
// itself the ISR handler (it needs no IRAM_ATTR restrictions of its own
// beyond what its caller already observes), but must stay printf/malloc/
// lock-free to remain safe when the real ISR calls it.
static void IRAM_ATTR bodCaptureEvent(uint32_t tUs, uint16_t durUs, uint8_t minLevel) {
  const uint8_t ctx = packCtx();

  uint8_t next = (uint8_t)((s_ringHead + 1) % BOD_RING_SIZE);
  if (next == s_ringTail) {
    // Ring full: drop the oldest. Both indices are nominally single-owner
    // (head=producer, tail=consumer) — this is the one place that
    // invariant bends, accepted as a documented simplification for an
    // instrument, not a safety-critical path.
    s_ringDrops++;
    s_ringTail = (uint8_t)((s_ringTail + 1) % BOD_RING_SIZE);
  }
  s_ring[s_ringHead].tUs = tUs;
  s_ring[s_ringHead].durUs = durUs;
  s_ring[s_ringHead].minLevel = minLevel;
  s_ring[s_ringHead].ctx = ctx;
  s_ringHead = next;

  s_ringCount++;
  if (s_ringCount == 1) {
    s_firstUs = tUs;
    s_phaseAtFirst = ctx;
  }
  s_lastUs = tUs;
  if (minLevel < s_minLevelEver) s_minLevelEver = minLevel;
  if (durUs > s_maxDurUs) s_maxDurUs = durUs;
  if (minLevel < 8) s_histByLevel[minLevel]++;
  s_trips = s_ringCount;
}

static void IRAM_ATTR bodIsr(void *arg) {
  (void)arg;
  if (!s_armed) return;

  const int64_t t0 = esp_timer_get_time();

  // Bounded spin: how long does the comparator stay tripped. First shape
  // information — an inrush spike clears fast, a slow sag does not.
  int64_t tEnd = t0;
  while ((REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_DET) &&
         (tEnd - t0) < BOD_SPIN_CAP_US) {
    tEnd = esp_timer_get_time();
  }
  const int64_t durUs64 = tEnd - t0;
  const uint16_t durUs = (uint16_t)((durUs64 > 0xFFFF) ? 0xFFFF : durUs64);

  // Depth ladder: lower the threshold one level at a time while DET stays
  // asserted, down to 0; restore the armed level on exit either way.
  uint8_t minLevel = s_thres;
  uint8_t lvl = s_thres;
  while (lvl > 0) {
    lvl--;
    REG_SET_FIELD(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_DBROWN_OUT_THRES, lvl);
    esp_rom_delay_us(BOD_LADDER_SETTLE_US);
    if (!(REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_DET)) break;
    minLevel = lvl;
  }
  REG_SET_FIELD(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_DBROWN_OUT_THRES, s_thres);

  bodCaptureEvent((uint32_t)t0, durUs, minLevel);

  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  REG_CLR_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_BROWN_OUT_INT_ENA);
  s_isrDisarmed = 1;
}

// Consumer-side re-arm (see s_isrDisarmed). Never called from the ISR.
// isBootWindow: true only for the drain that follows boot.cpp's own
// bodWatchPoll("wifi-end") — that trip stays at the boot threshold so B_boot
// (the reboot-per-level sweep) remains comparable even with descent on.
static void bodWatchRearm(bool isBootWindow) {
  if (!s_armed || !s_isrDisarmed) return;
  if (REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_DET) {
    s_holdoffs++;           // rail still low — try again next tick
    return;
  }
  if (s_descendEnabled && !isBootWindow) {
    // The event being re-armed after fired at s_thres, so s_thres is a level
    // that TRIPPED — that is what `floor` means. Recording the level we step
    // down TO would report one below anything ever observed.
    if (s_thres < s_floor) s_floor = s_thres;
    // "Quiet" means no trips, not no level changes: a board tripping steadily
    // at level 0 (no step possible) must not be stepped up by the timer.
    s_lastLevelChangeMs = millis();
    if (s_thres > 0) {
      const uint8_t nextLevel = (uint8_t)(s_thres - 1);
      REG_SET_FIELD(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_DBROWN_OUT_THRES, nextLevel);
      s_thres = nextLevel;
      s_stepsDown++;
      Serial.printf("[bod] arm level=%u reason=descend\n", (unsigned)nextLevel);
    }
  }
  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  REG_SET_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_BROWN_OUT_INT_ENA);
  s_isrDisarmed = 0;
  s_rearms++;
}

void bodWatchArm(uint8_t thres) {
  if (thres > 7) thres = 7;
  const uint32_t before = REG_READ(RTC_CNTL_BROWN_OUT_REG);
  const uint32_t intEnaBefore = REG_READ(RTC_CNTL_INT_ENA_REG) & RTC_CNTL_BROWN_OUT_INT_ENA;

  // Take over the shared RTC brownout interrupt from IDF's own panic-and-
  // restart handler (see esp_brownout_disable()'s declaration above).
  if (!s_isrInstalled) {
    esp_brownout_disable();
    rtc_isr_register(bodIsr, NULL, RTC_CNTL_BROWN_OUT_INT_ENA_M);
    s_isrInstalled = true;
  }

  REG_SET_FIELD(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_DBROWN_OUT_THRES, thres);
  REG_SET_BIT(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_BROWN_OUT_ENA);
  // The whole point: detect without resetting. RISK, stated plainly — a real
  // deep brownout will no longer reset the chip, so a flash/SD write in flight
  // during a sag can corrupt. That is why this is -DBOD_WATCH on the debug env
  // and never production.
  REG_CLR_BIT(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_BROWN_OUT_RST_ENA);
  // Parity with the polled build that ran 40 h without a reset:
  // esp_brownout_disable() zeroes PD_RF_ENA and CLOSE_FLASH_ENA (regAfter
  // read 0x7bff0000 against the old 0x7bffc000). Put them back exactly as
  // they were, so the interrupt path is the ONLY thing under test.
  {
    const uint32_t hwBits = RTC_CNTL_BROWN_OUT_PD_RF_ENA_M | RTC_CNTL_BROWN_OUT_CLOSE_FLASH_ENA_M;
    REG_WRITE(RTC_CNTL_BROWN_OUT_REG,
              (REG_READ(RTC_CNTL_BROWN_OUT_REG) & ~hwBits) | (before & hwBits));
  }

  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  REG_SET_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_BROWN_OUT_INT_ENA);

  s_thres = thres;
  s_armed = true;
  s_trips = 0;
  s_isrDisarmed = 0;
  s_rearms = 0;
  s_holdoffs = 0;
  s_ringHead = s_ringTail = 0;
  s_ringDrops = 0;
  s_ringCount = 0;
  s_firstUs = s_lastUs = 0;
  s_minLevelEver = 8;
  s_maxDurUs = 0;
  s_phaseAtFirst = 0xFF;
  for (int i = 0; i < 8; i++) s_histByLevel[i] = 0;

  // F-6: live state seeded from the RTC_NOINIT-persisted values (same magic
  // guard as bootThres/bootMit) so `bod descend on` survives a `reboot`, but
  // a cold boot (magic garbage) always comes up off/default — the correct
  // control state.
  s_baseLevel = thres;
  s_descendEnabled = (s_bootThresMagic == BOD_BOOT_MAGIC) && (s_descendPersist != 0);
  s_quietMs = (s_bootThresMagic == BOD_BOOT_MAGIC && s_quietMsPersist >= 1000)
                  ? s_quietMsPersist : BOD_DESCEND_QUIET_MS_DEFAULT;
  s_floor = 8;
  s_stepsDown = 0;
  s_stepsUp = 0;
  s_lastLevelChangeMs = millis();

  const uint32_t after = REG_READ(RTC_CNTL_BROWN_OUT_REG);
  // regBefore carries the level ESP-IDF booted with (sdkconfig says
  // CONFIG_ESP32_BROWNOUT_DET_LVL=0), so the two values together confirm the
  // write landed rather than assuming it did.
  Serial.printf("[bod] armed thres=%u regBefore=0x%08x regAfter=0x%08x "
                "ena=%d rstEna=%d intEnaBefore=%d intEna=%d isr=%d\n",
                (unsigned)thres, (unsigned)before, (unsigned)after,
                (after & RTC_CNTL_BROWN_OUT_ENA) ? 1 : 0,
                (after & RTC_CNTL_BROWN_OUT_RST_ENA) ? 1 : 0,
                intEnaBefore ? 1 : 0,
                (REG_READ(RTC_CNTL_INT_ENA_REG) & RTC_CNTL_BROWN_OUT_INT_ENA) ? 1 : 0,
                s_isrInstalled ? 1 : 0);
}

static bool ringDrainOne(BodRingEntry *out);

// Callers (serialburst) use this to start a measurement from zero. With the
// ISR path the latch is cleared by the ISR itself, so "clear" has to mean
// "discard events captured before now" — otherwise a boot-window trip still
// sitting in the ring is counted as the burst's own.
void bodWatchClear(void) {
  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  BodRingEntry ev;
  while (ringDrainOne(&ev)) {}
}

static bool ringDrainOne(BodRingEntry *out) {
  if (s_ringHead == s_ringTail) return false;
  uint8_t tail = s_ringTail;
  out->tUs = s_ring[tail].tUs;
  out->durUs = s_ring[tail].durUs;
  out->minLevel = s_ring[tail].minLevel;
  out->ctx = s_ring[tail].ctx;
  s_ringTail = (uint8_t)((tail + 1) % BOD_RING_SIZE);
  return true;
}

// Named checkpoint (BOOTPHASE, bodMitExitWifi, ...): drains whatever the ISR
// captured since the last drain (by anyone — bodWatchPoll/PollQuiet/Tick all
// share the one ring) and prints each under this tag. Keeps the existing
// fields (`tag=`, `t=`, `thres=`, `trips=`, `det=`) and ADDS the per-event
// ones (`us=`, `dur=`, `min=`, `ctx=`) — TASK-678 F-1.
bool bodWatchPoll(const char *tag) {
  if (!s_armed) return false;
  bool any = false;
  BodRingEntry ev;
  for (int n = 0; n < BOD_RING_SIZE && ringDrainOne(&ev); n++) {
    any = true;
    Serial.printf("[bod] TRIP tag=%s t=%lums thres=%u trips=%lu det=%d "
                  "us=%lu dur=%u min=%u ctx=%02x\n",
                  tag ? tag : "?", (unsigned long)millis(), (unsigned)s_thres,
                  (unsigned long)s_trips,
                  (REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_DET) ? 1 : 0,
                  (unsigned long)ev.tUs, (unsigned)ev.durUs, (unsigned)ev.minLevel,
                  (unsigned)ev.ctx);
  }
  bodWatchRearm(tag && strcmp(tag, "wifi-end") == 0);
  return any;
}

// Silent variant — safe inside a tight loop (serialburst): drains without
// printing so a caller can count locally and report once, afterwards.
bool bodWatchPollQuiet(void) {
  if (!s_armed) return false;
  BodRingEntry ev;
  bool any = false;
  for (int n = 0; n < BOD_RING_SIZE && ringDrainOne(&ev); n++) any = true;
  bodWatchRearm(false);
  return any;
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

// Shares s_bootThresMagic with the threshold above: one magic guards the whole
// RTC_NOINIT block, so a cold boot (magic garbage) yields mask 0 = unmitigated,
// which is the correct default for a control run.
void bodWatchSetBootMit(uint8_t mask) {
  s_bootMit = (uint8_t)(mask & 0x03);
  s_bootThresMagic = BOD_BOOT_MAGIC;
}

uint8_t bodWatchBootMit(void) {
  return (s_bootThresMagic == BOD_BOOT_MAGIC) ? (uint8_t)(s_bootMit & 0x03) : 0;
}

// ── F-6: adaptive-descent depth ────────────────────────────────────────
// Takes effect immediately (this session), not just on the next boot — the
// RTC_NOINIT write below only makes it survive a `reboot` too, same trick
// as bootThres/bootMit. Resets the floor/step counters: a fresh toggle-on
// starts a fresh descent, not a continuation of a stale one. The printed
// line gives rigwatch's timeline a marker for "descent armed from here".
void bodWatchSetDescend(bool on) {
  s_descendEnabled = on;
  s_descendPersist = on ? 1 : 0;
  s_bootThresMagic = BOD_BOOT_MAGIC;
  s_floor = 8;
  s_stepsDown = 0;
  s_stepsUp = 0;
  s_lastLevelChangeMs = millis();
  if (on) Serial.printf("[bod] arm level=%u reason=manual\n", (unsigned)s_thres);
}

bool bodWatchDescend(void) { return s_descendEnabled; }

void bodWatchSetQuietMs(uint32_t ms) {
  if (ms < 1000) ms = 1000;   // floor so a quiet step can't itself storm
  s_quietMs = ms;
  s_quietMsPersist = ms;
  s_bootThresMagic = BOD_BOOT_MAGIC;
}

uint32_t bodWatchQuietMs(void) { return s_quietMs; }

// ── F-5: BOD_POLICY stub ────────────────────────────────────────────────
// Debug env leaves BOD_POLICY undefined (observe only, per the runbook's
// stated default); a production policy build would define it low. Defined
// unconditionally here so the loop()-side check below compiles either way.
// Deeper = LOWER level, so the policy fires when minLevel <= BOD_POLICY. The
// disabled value must therefore sit BELOW level 0, not above 7 — an earlier
// draft used 8 here, which made every trip a "deep" one.
#ifndef BOD_POLICY
#define BOD_POLICY -1
#endif
static bool g_bodDeep = false;

static void bodWatchPolicyCheck(BodRingEntry *ev) {
  if ((int)ev->minLevel <= (int)(BOD_POLICY) && ev->durUs >= 500) g_bodDeep = true;
}

void bodWatchTick(void) {
  static unsigned long last = 0;
  const unsigned long now = millis();
  if (now - last < 200) return;   // the ring holds; draining faster buys nothing
  last = now;

  BodRingEntry ev;
  for (int n = 0; n < BOD_RING_SIZE && ringDrainOne(&ev); n++) {
    s_trips = s_ringCount;
    Serial.printf("[bod] TRIP tag=run t=%lums thres=%u trips=%lu det=%d "
                  "us=%lu dur=%u min=%u ctx=%02x\n",
                  (unsigned long)millis(), (unsigned)s_thres, (unsigned long)s_trips,
                  (REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_DET) ? 1 : 0,
                  (unsigned long)ev.tUs, (unsigned)ev.durUs, (unsigned)ev.minLevel,
                  (unsigned)ev.ctx);
    bodWatchPolicyCheck(&ev);
  }
  bodWatchRearm(false);

  // F-6: quiet-timeout step back up. Only when fully armed (no event pending
  // re-arm) and strictly below the boot ceiling — the level-change itself is
  // a plain register write, safe from consumer context at any time.
  if (s_armed && s_descendEnabled && !s_isrDisarmed && s_thres < s_baseLevel &&
      (now - s_lastLevelChangeMs) >= s_quietMs) {
    const uint8_t nextLevel = (uint8_t)(s_thres + 1 > s_baseLevel ? s_baseLevel : s_thres + 1);
    // INT is live here and the ISR runs on this core: it reads s_thres and
    // its ladder restores that value to the register on exit. Publish
    // s_thres FIRST, so an ISR landing between the two lines restores the new
    // level rather than silently undoing the step while s_thres claims it.
    s_thres = nextLevel;
    REG_SET_FIELD(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_DBROWN_OUT_THRES, nextLevel);
    s_stepsUp++;
    s_lastLevelChangeMs = now;
    Serial.printf("[bod] arm level=%u reason=quiet\n", (unsigned)nextLevel);
  }

  if (g_bodDeep) {
    g_bodDeep = false;
    Serial.printf("[bod] policy deep=%u dur=%u\n", (unsigned)s_minLevelEver,
                  (unsigned)s_maxDurUs);
#ifdef BOD_POLICY_RESTART
    Serial.flush();
    delay(50);
    ESP.restart();
#endif
  }
}

uint32_t bodWatchTrips(void) { return s_trips; }

// ── F-1: get bod / mark / set fault bod / context shadow ───────────────
void bodWatchGetSnapshot(BodSnapshot *out) {
  if (!out) return;
  out->count = s_ringCount;
  out->dropped = s_ringDrops;
  out->firstUs = s_firstUs;
  out->lastUs = s_lastUs;
  out->minLevel = s_minLevelEver;
  out->maxDurUs = s_maxDurUs;
  for (int i = 0; i < 8; i++) out->hist[i] = s_histByLevel[i];
  out->phaseAtFirst = s_phaseAtFirst;
  out->thres = s_thres;
  out->armed = s_armed;
  out->rearms = s_rearms;
  out->holdoffs = s_holdoffs;
  out->disarmed = s_isrDisarmed ? true : false;
  out->descend = s_descendEnabled;
  out->armedLevel = s_thres;
  out->floor = s_floor;
  out->stepsDown = s_stepsDown;
  out->stepsUp = s_stepsUp;
  out->quietMs = s_quietMs;
}

void bodWatchMark(const char *label) {
  Serial.printf("[mark] %s us=%lld\n", label ? label : "?",
                (long long)esp_timer_get_time());
}

// `set fault bod <level>` — same capture path a real trip takes, with a
// synthetic minLevel and a nominal 1us duration, so R34's runtime gate can
// exercise `[bod] TRIP`/`get bod` parsing without a real supply sag.
void bodWatchFault(uint8_t level) {
  if (level > 7) level = 7;
  bodCaptureEvent((uint32_t)esp_timer_get_time(), 1, level);
  Serial.printf("{\"ok\":true,\"cmd\":\"set\",\"var\":\"fault\",\"synthetic\":\"bod\","
                "\"level\":%u}\n", (unsigned)level);
}

void bodWatchSetCtxBoot(uint8_t phase) { s_ctxBoot = (uint8_t)(phase & 0x07); }
void bodWatchSetCtxWifi(bool up) { s_ctxWifiUp = up ? 1 : 0; }
void bodWatchSetCtxSdBusy(bool busy) { s_ctxSdBusy = busy ? 1 : 0; }
void bodWatchSetCtxBacklight(uint8_t duty8) { s_ctxBacklight = (uint8_t)(duty8 >> 5); }

#endif  // BOD_WATCH
