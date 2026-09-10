// debug/bodWatch.cpp — TASK-557 supply telemetry. See bodWatch.h.
#include "debug/bodWatch.h"

#ifdef BOD_WATCH
#include <Arduino.h>
#include "soc/rtc_cntl_reg.h"
#include "soc/soc.h"
#include "driver/rtc_cntl.h"   // rtc_isr_register()
#include "esp_rom_sys.h"       // esp_rom_delay_us() — ISR-safe busy wait
#include "esp_timer.h"         // esp_timer_get_time()

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

  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
  REG_SET_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_BROWN_OUT_INT_ENA);

  s_thres = thres;
  s_armed = true;
  s_trips = 0;
  s_ringHead = s_ringTail = 0;
  s_ringDrops = 0;
  s_ringCount = 0;
  s_firstUs = s_lastUs = 0;
  s_minLevelEver = 8;
  s_maxDurUs = 0;
  s_phaseAtFirst = 0xFF;
  for (int i = 0; i < 8; i++) s_histByLevel[i] = 0;

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

void bodWatchClear(void) {
  REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_BROWN_OUT_INT_CLR);
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
  while (ringDrainOne(&ev)) {
    any = true;
    Serial.printf("[bod] TRIP tag=%s t=%lums thres=%u trips=%lu det=%d "
                  "us=%lu dur=%u min=%u ctx=%02x\n",
                  tag ? tag : "?", (unsigned long)millis(), (unsigned)s_thres,
                  (unsigned long)s_trips,
                  (REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_DET) ? 1 : 0,
                  (unsigned long)ev.tUs, (unsigned)ev.durUs, (unsigned)ev.minLevel,
                  (unsigned)ev.ctx);
  }
  return any;
}

// Silent variant — safe inside a tight loop (serialburst): drains without
// printing so a caller can count locally and report once, afterwards.
bool bodWatchPollQuiet(void) {
  if (!s_armed) return false;
  BodRingEntry ev;
  bool any = false;
  while (ringDrainOne(&ev)) any = true;
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

// ── F-5: BOD_POLICY stub ────────────────────────────────────────────────
// Debug env leaves BOD_POLICY undefined (observe only, per the runbook's
// stated default); a production policy build would define it low. Defined
// unconditionally here so the loop()-side check below compiles either way.
#ifndef BOD_POLICY
#define BOD_POLICY 8   // 8 = above the ladder's max depth (7) -> never trips
#endif
static bool g_bodDeep = false;

static void bodWatchPolicyCheck(BodRingEntry *ev) {
  if (ev->minLevel <= BOD_POLICY && ev->durUs >= 500) g_bodDeep = true;
}

void bodWatchTick(void) {
  static unsigned long last = 0;
  const unsigned long now = millis();
  if (now - last < 200) return;   // the ring holds; draining faster buys nothing
  last = now;

  BodRingEntry ev;
  while (ringDrainOne(&ev)) {
    s_trips = s_ringCount;
    Serial.printf("[bod] TRIP tag=run t=%lums thres=%u trips=%lu det=%d "
                  "us=%lu dur=%u min=%u ctx=%02x\n",
                  (unsigned long)millis(), (unsigned)s_thres, (unsigned long)s_trips,
                  (REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_DET) ? 1 : 0,
                  (unsigned long)ev.tUs, (unsigned)ev.durUs, (unsigned)ev.minLevel,
                  (unsigned)ev.ctx);
    bodWatchPolicyCheck(&ev);
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
