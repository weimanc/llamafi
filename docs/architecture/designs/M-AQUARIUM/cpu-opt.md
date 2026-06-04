# Design — Aquarium + VuMeter CPU Optimisation (M-AQUARIUM-CPU-OPT)

> Owner: Architect
> Status: draft
> Date: 2026-06-04
> Amended: 2026-06-04 — extended to cover vuMeter.h hotspots and shared math utility
> Feeds: ADR-038 (pending)
> Related: demoscene-opt.md (memory; already shipped), M-PERF-profiling.md

---

## Guiding principle

> *Replace transcendental functions with table lookups. Replace division with
> multiplication. Never call `sqrt` when you want `1/sqrt`.*

Demoscene-opt addressed DRAM footprint. This document addresses CPU time.
The aquarium calls ~150–200 `sinf`/`cosf` invocations and ~70–100 `sqrtf`
invocations per frame. A codebase-wide scan (§10) also found `vuMeter.h:tickWave`
calling 76 `sinf` per frame — the single largest trig hotspot outside the aquarium.
On the ESP32 Xtensa LX7 these are software-emulated at 60–120 cycles each. The
techniques below eliminate the bulk of this cost across both components.

---

## 1. Context

### 1.1 Hot-path inventory (per frame, 30 fps target)

| Category | Site | Calls/frame | Cycles each | Budget (240 MHz) |
|---|---|---|---|---|
| `sinf`/`cosf` — fish wander | `updateFish:662-663` | 32 | ~80 | ~11 µs |
| `sinf`/`cosf` — fish wave draw | `drawFish:1022-1023` | 32 | ~80 | ~11 µs |
| `sinf` — flake sway | `updateFlakes:543` | 16 | ~80 | ~5 µs |
| `sinf` — bubble sway | `updateBubbles:554` | 10 | ~80 | ~3 µs |
| `sinf` — speed pulse | `updateFish:727` | 16 | ~80 | ~5 µs |
| `sinf` — octopus draw | `drawOctopus:1049-1063` | 10 | ~80 | ~3 µs |
| `sinf` — seahorse draw | `drawSeahorse:1087-1091` | 6 | ~80 | ~2 µs |
| `sinf` — seaweed branches | `_seaweedBranches:955` | up to 60 | ~80 | ~20 µs |
| `sinf`/`cosf` — crab legs | `drawCrab:1411-1412` | 2+8 | ~80 | ~3 µs |
| `sinf` — visitor bob | `updateOctopus:777`, `updateSeahorse:809-813` | 4 | ~80 | ~1 µs |
| **trig subtotal** | | **~196** | | **~65 µs/frame** |
| `sqrtf` — fish velocity norm | `updateFish:723` | 16 | ~60 | ~4 µs |
| `sqrtf` — fish-fish repel | `updateFish:687` | up to 240 | ~60 | ~60 µs |
| `sqrtf` — steer from octopus | `_steerFromOctopus:576` | up to 16 | ~60 | ~4 µs |
| `sqrtf` — steer from seahorse | `_steerFromSeahorse:590` | up to 16 | ~60 | ~4 µs |
| `1/sqrtf` — push out of oct/sh | `_pushOut*:610,630` | up to 32 | ~80 | ~11 µs |
| `1/sqrtf` — visitor sep | `keepVisitorsSeparated:834` | 1 | ~80 | <1 µs |
| **sqrt subtotal** | | **~320 worst / ~80 typical** | | **~50 µs typical** |
| div by radius constants | repel loop `updateFish:684-690` | 240 | ~8 | ~8 µs |
| div by radius constants | `_steer*`, `_pushOut*` | up to 256 | ~8 | ~9 µs |
| velocity normalize divides | `updateFish:725` | 32 | ~8 | ~1 µs |
| `nearCount` divides | `updateFish:695-696` | 4 | ~8 | <1 µs |
| `time()`+`localtime_r()` | `updateClock:847` | 30 | ~500 | ~63 µs |
| **Total estimated per frame** | | | | **~200–250 µs** |

At 30 fps the tick budget is 33 ms. The aquarium competes with Spotify HTTP polling
(blocking, ~100–2000 ms burst) on the same core. The ~250 µs baseline is acceptable,
but high trig counts leave headroom for future fish-count increases and reduce
thermal load during continuous animation.

---

## 2. Goals

1. Reduce per-frame trig cost by ≥ 60% (≥ 120 calls/frame avoided).
2. Eliminate `1/sqrtf` pattern entirely.
3. Eliminate all floating-point division by compile-time-constant denominators.
4. Eliminate the `time()`+`localtime_r()` syscall overhead from the 30 Hz tick.
5. Produce a benchmark harness that quantifies before/after so gains are not assumed.

Non-goals: fixed-point arithmetic for physics (pervasive, brittle, no DUT demand);
DMA blit optimisation (addressed in M-PERF); fish-count reduction.

---

## 3. Measurement strategy

### 3.1 ESP32 cycle counter

Xtensa LX7 exposes a 32-bit cycle counter via `xthal_get_ccount()`. At 240 MHz
it overflows in ~17 seconds — sufficient for per-tick measurement.

```cpp
// Pattern: wrap any block
uint32_t t0 = xthal_get_ccount();
// ... block under test ...
uint32_t elapsed_cycles = xthal_get_ccount() - t0;
float elapsed_us = elapsed_cycles / 240.0f;
```

No instrumentation overhead: `xthal_get_ccount()` is a single `rsr a2, CCOUNT`
instruction (~2 cycles).

### 3.2 Instrumentation sites

Add four `uint32_t` rolling-average accumulators to `AquariumApp` (member, no heap):

```cpp
uint32_t _perfCycUpdate = 0;   // updateFish + updateBubbles + updateFlakes + visitors
uint32_t _perfCycDraw   = 0;   // drawFish + drawOctopus + drawSeahorse + drawCrab + drawSeaweed
uint32_t _perfCycTick   = 0;   // full tick() body
uint32_t _perfFrames    = 0;   // frame counter
```

Wrap `tick()` body regions:

```cpp
void tick() override {
    uint32_t t_tick = xthal_get_ccount();

    // ... existing dt/clock code ...

    uint32_t t_upd = xthal_get_ccount();
    updateFlakes(dt);
    updateCrab(dt);
    updateBubbles(dt);
    updateFish(dt);
    updateOctopus(_aquariumNowMs, dt);
    updateSeahorse(_aquariumNowMs, dt);
    keepVisitorsSeparated();
    _perfCycUpdate += xthal_get_ccount() - t_upd;

    uint32_t t_draw = xthal_get_ccount();
    renderFrame();
    _perfCycDraw += xthal_get_ccount() - t_draw;

    _perfCycTick += xthal_get_ccount() - t_tick;
    ++_perfFrames;

    // Print rolling average every 300 frames (~10 s at 30 fps).
    // Use Serial.printf only — no heap.
    if (_perfFrames >= 300) {
        float div = _perfFrames * 240.0f;
        Serial.printf("[aq perf] tick=%.0fus upd=%.0fus draw=%.0fus frames=%lu\n",
            _perfCycTick / div, _perfCycUpdate / div, _perfCycDraw / div,
            (unsigned long)_perfFrames);
        _perfCycUpdate = _perfCycDraw = _perfCycTick = _perfFrames = 0;
    }
}
```

This gives three numbers every 10 seconds:
- `tick` — total; the wall-clock budget consumed per frame
- `upd` — physics; dominated by `updateFish` trig + sqrt
- `draw` — render; dominated by seaweed/octopus/seahorse trig + strip blits

### 3.3 Capture protocol

1. Build with `cyd2usb_winamp_debug` (SERIAL_DEBUG, same speed as prod).
2. Open monitor. Navigate to Aquarium. Let settle for 30 seconds.
3. Capture three consecutive `[aq perf]` lines — this is the **baseline**.
4. Apply one optimisation phase.
5. Rebuild, flash, repeat capture — this is the **after** measurement.
6. Record in the VE table below (§7).

> The `check_build.sh` golden hash must pass after each phase.

---

## 4. Design space

### 4.1 Option A — sin/cos lookup table (LUT)

**Mechanism.** Precompute a 512-entry float array at `init()`. Index by quantising
the angle modulo 2π into 0..511.

```cpp
// 512 × 4B = 2,048B DRAM (or IRAM for cache-free access)
static float s_sinLUT[512];

static void _buildSinLUT() {
    for (int i = 0; i < 512; ++i)
        s_sinLUT[i] = sinf(i * (6.28318f / 512.f));
}

static inline float lut_sin(float a) {
    // Wrap to [0, 2π), map to [0, 512), truncate
    int i = (int)(a * (512.f / 6.28318f)) & 511;
    return s_sinLUT[i];
}
static inline float lut_cos(float a) { return lut_sin(a + 1.5708f); }
```

**Precision.** Step = 2π/512 ≈ 0.012 rad; max error ≈ ±sin(0.006) ≈ ±0.006.
All call sites use sin for visual wiggle offsets (1–8 px amplitude). A ±0.006
error at 6 px amplitude = ±0.04 px — imperceptible.

**Speed.** `xthal_get_ccount()` before/after one `lut_sin` call: ~4–6 cycles
(one multiply + one AND + one array load). vs ~80 cycles for `sinf`. **13–20×
speedup per call.** 196 calls/frame × 74 cycles saved = ~14,500 cycles/frame
≈ **60 µs saved per frame at 240 MHz**.

**Cost.** 2,048 B DRAM. ESP32 has 320 KB DRAM; demoscene-opt freed ~21 KB from
`AquariumApp` alone, so this is well-covered.

**Alternative A2 — PROGMEM float LUT.** Move `s_sinLUT` to flash. Saves 2 KB DRAM.
Cost: cache miss penalty. 512 × 4B = 2 KB fills ~8 cache lines (32B each on LX7);
repeated random access by varied phases will mostly hit. Estimated ~8–12 cycles/call
vs 4–6 in DRAM — still 7–10× faster than `sinf`. Use if 2 KB DRAM is tight.

**Alternative A3 — 256-entry int16_t LUT.** 512 B, scaled by 32767. Saves 1.5 KB
vs A. Requires a multiply-by-scale at each call site. Adds one instruction; still
much faster than `sinf`. Max error ±0.010. Acceptable for visual use.

**Lean: A (DRAM float LUT, 512 entries).** Demoscene-opt already freed the headroom.
Best speed, zero precision concern, one-line call-site change.

---

### 4.2 Option B — fast inverse square root

**Mechanism.** Quake III `Q_rsqrt` — one integer bit trick + one Newton-Raphson step.

```cpp
static inline float q_rsqrt(float x) {
    float xh = 0.5f * x;
    int32_t i; memcpy(&i, &x, 4);
    i = 0x5f3759df - (i >> 1);
    memcpy(&x, &i, 4);
    return x * (1.5f - xh * x * x);   // ~3% max error; one NR step
}
```

**Sites:**

| Site | Current | Replacement |
|---|---|---|
| `_pushOutOfOctopus:610` | `1.0f / sqrtf(sd2)` | `q_rsqrt(sd2)` |
| `_pushOutOfSeahorse:630` | `1.0f / sqrtf(sd2)` | `q_rsqrt(sd2)` |
| `keepVisitorsSeparated:834` | `1.0f / sqrtf(sd2)` | `q_rsqrt(sd2)` |
| `updateFish:723-725` | `mag=sqrtf(...)` then `vx/=mag` | `inv=q_rsqrt(...); vx*=inv` |
| `_steerFromOctopus:576` | `dist=sqrtf(...)` then `/dist` | fold: `inv=q_rsqrt(dx²+dy²); (dx*inv)*(dy*inv)` |
| `_steerFromSeahorse:590` | same | same |

**Precision.** 3% error on force magnitudes used for visual push/steer — not physics simulation. The crab `_scatterFish:1173` also uses sqrtf; scatter is a one-shot impulse. 3% scatter error is undetectable.

**Speed.** `q_rsqrt`: ~10–15 cycles. `sqrtf`: ~60 cycles. `1.0f/sqrtf`: ~80 cycles.
Savings: ~65 cycles per replaced site. ~8 sites × 16 fish typical = ~8,000 cycles/frame
≈ **33 µs saved per frame**.

**Alternative B2 — `arm_sqrt_q15` (CMSIS-DSP).** Available on ESP-IDF, fixed-point.
Requires converting physics to Q15 at call sites — invasive. Not recommended here.

**Lean: B (q_rsqrt).** Zero dependencies, single function, surgical call-site changes.

---

### 4.3 Option C — reciprocal constants for float division

**Mechanism.** Every division `dx / RADIUS_X` where `RADIUS_X` is a `constexpr float`
can become `dx * kInvRadiusX` where `kInvRadiusX = 1.0f / RADIUS_X` is also
`constexpr`. Float multiply is ~4 cycles; float divide is ~8 cycles. Compiler with
`-O2` *may* already do this for constexpr denominators, but it is not guaranteed
when mixed with non-const numerators.

**Constants needed** (all appear in the inner fish-loop):

```cpp
static constexpr float kInvFishAvoidRX   = 1.0f / FISH_AVOID_RADIUS_X;    // 1/52
static constexpr float kInvFishAvoidRY   = 1.0f / FISH_AVOID_RADIUS_Y;    // 1/20
static constexpr float kInvOctFishAvRX   = 1.0f / OCTOPUS_FISH_AVOID_RADIUS_X;  // 1/76
static constexpr float kInvOctFishAvRY   = 1.0f / OCTOPUS_FISH_AVOID_RADIUS_Y;  // 1/34
static constexpr float kInvOctFishClRX   = 1.0f / OCTOPUS_FISH_CLEAR_RADIUS_X;  // 1/46
static constexpr float kInvOctFishClRY   = 1.0f / OCTOPUS_FISH_CLEAR_RADIUS_Y;  // 1/22
static constexpr float kInvSHFishAvRX    = 1.0f / SEAHORSE_FISH_AVOID_RADIUS_X; // 1/58
static constexpr float kInvSHFishAvRY    = 1.0f / SEAHORSE_FISH_AVOID_RADIUS_Y; // 1/38
static constexpr float kInvSHFishClRX    = 1.0f / SEAHORSE_FISH_CLEAR_RADIUS_X; // 1/34
static constexpr float kInvSHFishClRY    = 1.0f / SEAHORSE_FISH_CLEAR_RADIUS_Y; // 1/28
static constexpr float kInvVisClRX       = 1.0f / VISITOR_CLEAR_RADIUS_X;       // 1/56
static constexpr float kInvVisClRY       = 1.0f / VISITOR_CLEAR_RADIUS_Y;       // 1/38
```

**Speed.** ~4 cycles saved per division. The repel inner loop has 4 divisions ×
up to 240 iterations = ~960 div calls worst case; ~3,840 cycles saved ≈ **16 µs/frame**.

**Lean: C (constexpr reciprocals).** Trivially safe, zero logic change. Low effort.
Add in the same PR as any other change.

---

### 4.4 Option D — `nearCount` reciprocal

Exactly one `1/nearCount` integer division converted to `float invN`:

```cpp
// Before (lines 695-696):
avgVX /= nearCount; avgVY /= nearCount;
scx   /= nearCount; scy   /= nearCount;

// After:
float invN = 1.0f / nearCount;
avgVX *= invN; avgVY *= invN;
scx   *= invN; scy   *= invN;
```

3 divisions removed, 1 added. Activates only when same-species fish cluster.
Negligible per-frame savings but costs nothing to apply.

**Lean: D (do it, trivial).**

---

### 4.5 Option E — `updateClock` throttle

`updateClock()` calls `time(nullptr)` (POSIX syscall, ~300–600 cycles) and
`localtime_r()` (~100–200 cycles) every tick (30×/second). The clock only needs
updating once per second.

```cpp
void updateClock() {
    unsigned long now = millis();
    if (now - _lastClockUpdateMs < 1000) return;
    _lastClockUpdateMs = now;
    time_t t = time(nullptr);
    struct tm ti;
    localtime_r(&t, &ti);
    _clockHour   = ti.tm_hour;
    _clockMinute = ti.tm_min;
}
```

Adds one `unsigned long _lastClockUpdateMs` member. Saves ~500 cycles × 29 skipped
calls/second = **~60 µs/second** (~2 µs/frame amortised). Low absolute saving but
correct behaviour (calling `time()` at 30 Hz is never necessary).

**Lean: E (do it, trivial).**

---

### 4.6 Option F — `_frand` reciprocal

`_frand` divides by `9999.0f`. Called at spawn time, not per-frame. Cosmetic.

```cpp
static constexpr float kInv9999 = 1.0f / 9999.0f;
return a + (b - a) * float(random(0, 10000)) * kInv9999;
```

**Lean: F (include in the same PR as C, zero risk).**

---

## 5. Rejected / deferred options

| Option | Reason |
|---|---|
| `arm_sqrt_q15` (CMSIS fixed-point sqrt) | Requires Q15 physics conversion at all call sites — invasive, fragile, no DUT demand |
| Fixed-point fish physics | Same as above; float physics is clean and correct |
| Per-fish trig elimination (integrate analytically) | Physics model is too complex; wander/flock forces are not periodic closed-forms |
| IRAM placement of `s_sinLUT` | IRAM is 192 KB and more scarce than DRAM; cache-in-DRAM is sufficient given LUT is 2 KB |
| Reduce fish count | Functional regression; the user has 16 fish |
| Phase caching across tick (seaweed) | Already addressed in demoscene-opt §7; sinf count unchanged there |

---

## 6. Implementation phases

Ordered by effort and independence. Each phase is independently compilable and verifiable.

| Phase | Changes | Files | Estimated saving | Risk |
|---|---|---|---|---|
| **P1 — Trivial** | E (clock throttle), F (`_frand`), D (`nearCount`) | aquariumApp.h | ~2 µs/frame | Negligible |
| **P2 — Reciprocals** | C (12 constexpr reciprocals); vuMeter §10.2 (3 reciprocals) | aquariumApp.h, vuMeter.h | ~18 µs/frame | Low; mechanical substitution |
| **P3 — Fast rsqrt** | B (q_rsqrt at 6 sites in aquariumApp.h) | mathUtil.h (new), aquariumApp.h | ~33 µs/frame | Low; 3% error acceptable |
| **P4 — Wave rotation** | §10.1 rotation matrix in tickWave | vuMeter.h | ~50 µs/frame | Low; well-understood pattern |
| **P5 — Shared LUT** | §11 mathUtil.h LUT; replace 41 aquarium + 3 vuMeter sinf/cosf sites | mathUtil.h, aquariumApp.h, vuMeter.h | ~75 µs/frame | Medium; most call sites |

Total estimated saving after all phases: **~178 µs/frame** from a ~300 µs combined
aquarium + vuMeter baseline → projected ~120 µs/frame (**~40% reduction**).

P4 (wave rotation) is independent of P5 (LUT) and delivers large savings before the LUT
is written. Implement P4 in its own session. P3 introduces `mathUtil.h` which P5 also
uses — implement P3 before P5.

---

## 7. VE acceptance criteria

Each phase: run `check_build.sh`, capture three `[aq perf]` lines before and after,
record in table. Visual check: aquarium runs continuously for 60 seconds, fish swim
naturally, no visible animation discontinuity.

| # | Phase | Test | Method | Pass condition |
|---|---|---|---|---|
| 1 | P1 | Clock throttle: serial log shows time advancing at 1 Hz cadence | Serial monitor | No sub-second flicker in clock display |
| 2 | P1 | `check_build.sh` passes | CI | Exit 0 |
| 3 | P2 | Fish repel, push-out, steer behaviour visually unchanged | Visual, 60 s | Fish separate normally; no clumping or pass-through |
| 4 | P2 | `[aq perf] upd=` reduced vs baseline | Serial measurement | Measurable reduction (≥5 µs) |
| 5 | P3 | Fish velocity normalisation: no NaN, no degenerate zero-speed fish | Visual + serial | Fish continue swimming; no freezes |
| 6 | P3 | Push-out forces: fish do not penetrate octopus/seahorse bounding ellipse | Visual | Fish visibly avoid visitors |
| 7 | P3 | `[aq perf] upd=` reduced vs P2 baseline | Serial measurement | Measurable reduction (≥10 µs) |
| 8 | P4 | Wave visualizer renders continuous sinusoidal waveform | Visual, 30 s | No flattening, no phase jump |
| 9 | P4 | Wave advances smoothly left-to-right at same apparent speed as before | Visual A/B vs pre-P4 | No visible cadence change |
| 10 | P4 | `[aq perf] draw=` reduced vs P3 baseline (vuMeter runs in same tick) | Serial measurement | Measurable reduction (≥20 µs) |
| 11 | P5 | All aquarium sinf/cosf replaced; no bare calls remain in aquariumApp.h | `grep -n sinf aquariumApp.h` | Only `_buildSinLUT` body line |
| 12 | P5 | vuMeter LFO sinf replaced; no bare calls remain in vuMeter.h | `grep -n sinf vuMeter.h` | Zero matches |
| 13 | P5 | Animation continuous: fish wave, seaweed sway, bubble sway all present | Visual, 60 s | No frozen or jittery elements |
| 14 | P5 | `[aq perf] tick=` reduced vs P4 baseline | Serial measurement | Combined ≥ 40 µs reduction |
| 15 | All | Aquarium + winamp both survive 10 app-switch cycles without crash | Manual | No sprite alloc failure, no restart |
| 16 | All | `check_build.sh` passes after final phase | CI | Exit 0 |

### 7.1 Measurement record (fill in during implementation)

| Phase | `tick` µs before | `tick` µs after | `upd` µs before | `upd` µs after | Notes |
|---|---|---|---|---|---|
| Baseline | — | — | — | — | Pre-any-CPU-opt |
| P1 | | | | | |
| P2 | | | | | |
| P3 | | | | | |
| P4 | | | | | |
| P5 | | | | | |

---

## 8. Files affected

| File | Changes |
|---|---|
| `app/src/util/mathUtil.h` | **New file.** `q_rsqrt`, `lut_sin`, `lut_cos`, `buildMathLUT()`. Single include for all consumers. |
| `app/src/aquarium/aquariumApp.h` | LUT init call, 41 sinf/cosf → lut_sin/lut_cos, q_rsqrt at 6 sites, 12 reciprocal constexpr, clock throttle, 4 perf counters |
| `app/src/winamp/vuMeter.h` | tickWave rotation matrix, 3 reciprocals, 3 LFO sinf → lut_sin |
| `app/src/main.cpp` | `buildMathLUT()` call in `setup()`; 2 millis `* 0.001f` substitutions |

No new FreeRTOS tasks. No heap allocations. No interface changes.

---

## 9. Open questions

1. **PROGMEM vs DRAM for LUT.** If heap pressure resurfaces (Spotify TLS allocates
   ~10–20 KB transiently), consider moving `s_sinLUT` to PROGMEM with `pgm_read_float`.
   Profile first — premature move to PROGMEM costs ~4 extra cycles per call.

2. **q_rsqrt accuracy adequacy.** The 3% error bound is theoretical worst-case. Run
   VE criterion 6 on DUT to confirm fish do not visually penetrate visitor ellipses.
   If they do, add a second Newton-Raphson step (reduces error to ~0.09%).

3. **`sinf` in LUT init.** `buildMathLUT()` calls `sinf` 512 times during `setup()`.
   One-time cost (~41,000 cycles, ~170 µs) — acceptable. If startup time ever matters,
   replace with a precomputed PROGMEM table (same pattern as `kHeightNoise` in
   demoscene-opt P2).

4. **vuMeter LFO `now / 700.0f` precision.** `now` is `unsigned long` (ms). At
   ~49 days uptime it wraps. The sinf argument wraps continuously — no issue. The
   `/ 700.0f` → `* (1.0f/700.0f)` substitution is cosmetic.

---

## 10. VuMeter hotspots (codebase scan result)

A scan of `app/src/` (excluding aquarium) found `vuMeter.h` as the only other file
with significant trig and division hotspots. All other files had no per-frame trig or
were already within acceptable bounds.

### 10.1 `tickWave:301-303` — rotation matrix (76 sinf → 2)

`tickWave` computes a sine wave across all 76 pixels of the visualiser by calling
`sinf(wavePhase + x * step)` inside the pixel loop. The angles are evenly spaced
by a fixed step `WAVE_CYCLES * TWO_PI_F / RECT_W`. This is exactly the rotation
matrix pattern already used in `drawFish` and `drawCrab`.

**Current (76 sinf calls):**
```cpp
// vuMeter.h:301-303
for (int x = 0; x < RECT_W; x++) {
    int y = centreY + (int)roundf(lLvl * 5.0f *
                sinf(wavePhase + x * WAVE_CYCLES * TWO_PI_F / RECT_W));
```

**After (2 sinf+cosf at loop entry, then 4 MACs per pixel):**
```cpp
// Precomputed once (static constexpr — step is a compile-time constant):
static constexpr float kWaveStep = WAVE_CYCLES * TWO_PI_F / float(RECT_W);
static const float kWaveSin = sinf(kWaveStep);   // computed once at first call
static const float kWaveCos = cosf(kWaveStep);   // computed once at first call

// Loop:
float wave  = sinf(wavePhase);   // 1 sinf per frame
float waveC = cosf(wavePhase);   // 1 cosf per frame
const float amp = lLvl * 5.0f;
for (int x = 0; x < RECT_W; x++) {
    int y = centreY + (int)(amp * wave + (amp * wave >= 0.0f ? 0.5f : -0.5f));
    // ... clamp + draw unchanged ...
    float nw = wave * kWaveCos + waveC * kWaveSin;
    waveC    = waveC * kWaveCos - wave  * kWaveSin;
    wave     = nw;
}
```

`kWaveStep = 2.5 × 2π / 76 ≈ 0.2066 rad`. `kWaveSin`/`kWaveCos` are `static const`
locals — evaluated once on first call and cached by the compiler.

**Saving: 74 sinf calls eliminated per frame.** Estimated **~50 µs/frame** at 240 MHz.
This is the single largest saving in the entire scan.

**Invariant preserved:** the wave phasor advances by exactly `kWaveStep` per pixel,
so the waveform shape and apparent scroll speed are identical to the original.

---

### 10.2 `tickSpectrum` loop reciprocals (19 iterations × 2 divides)

```cpp
// :200  — inside for (int i = 0; i < SPEC_BARS; i++)
const float shape = 1.0f - (ei / 18.0f) * 0.6f;

// :213
const float smoothLvl = specH[i] / (float)VIS_H;

// :215
specPeak[i] -= 1.0f / VIS_H;
```

`SPEC_BARS = 19`, `VIS_H = 16` — both compile-time constants.

```cpp
// Add in tickSpectrum scope (or file scope):
static constexpr float kInv18   = 1.0f / 18.0f;
static constexpr float kInvVisH = 1.0f / float(VIS_H);   // 1/16 = 0.0625f
static constexpr float kPeakDec = kInvVisH;               // alias for clarity

// Replace:
const float shape     = 1.0f - ei * kInv18 * 0.6f;
const float smoothLvl = specH[i] * kInvVisH;
specPeak[i]          -= kPeakDec;
```

**Saving: 38 divides/frame → 38 multiplies.** ~4 cycles saved each ≈ **<1 µs/frame**.
Cosmetic, but correct and zero risk.

---

### 10.3 `tick()` LFO sinf calls (3 per tick, use shared LUT)

```cpp
// :190  sinf((float)elapsed / 14000.0f) * 3.0f       — spectrum tilt LFO
// :367  sinf(elapsed / 3000.0f)                       — swell envelope
// :383  sinf(now / 700.0f)                             — stereo beat LFO
```

All are once-per-tick, not in a loop. Apply `lut_sin` from §11:
```cpp
const float tilt  = lut_sin((float)elapsed * (1.0f / 14000.0f)) * 3.0f;
const float swell = MIX_SWELL * (1.0f + lut_sin(elapsed * (1.0f / 3000.0f)));
const float lfo   = lut_sin(now * (1.0f / 700.0f)) * 0.15f;
```

Also apply the division → multiply substitution inline (the division is the argument
to lut_sin anyway, so the reciprocal is free).

**Saving: 3 sinf/tick eliminated.** Small absolute value, correct.

---

### 10.4 `main.cpp` millis divisions (high-frequency)

```cpp
// main.cpp:204  (SpotifyApp tick, scroll delta)
(now - _lastScrollMs) / 1000.0f   →   (now - _lastScrollMs) * 0.001f

// main.cpp:1900 (tickScroll call)
dtMs / 1000.0f   →   dtMs * 0.001f
```

Called at every Winamp display refresh (~30 Hz). Single-line replacements.

---

## 11. Shared math utility (`mathUtil.h`)

### Motivation

The LUT (`s_sinLUT`) and `q_rsqrt` are needed by both `aquariumApp.h` and `vuMeter.h`.
Duplicating a 2 KB array would waste DRAM and create two init paths. A single
`app/src/util/mathUtil.h` centralises both.

### Design

```cpp
// app/src/util/mathUtil.h
#pragma once
#include <cmath>
#include <cstring>

// 512-entry sin LUT, 2 KB DRAM.
// Call buildMathLUT() once from setup() before any lut_sin/lut_cos call.
extern float g_sinLUT[512];

inline void buildMathLUT() {
    for (int i = 0; i < 512; ++i)
        g_sinLUT[i] = sinf(i * (6.28318f / 512.f));
}

inline float lut_sin(float a) {
    return g_sinLUT[(int)(a * (512.f / 6.28318f)) & 511];
}
inline float lut_cos(float a) { return lut_sin(a + 1.5708f); }

inline float q_rsqrt(float x) {
    float xh = 0.5f * x;
    int32_t i; memcpy(&i, &x, 4);
    i = 0x5f3759df - (i >> 1);
    memcpy(&x, &i, 4);
    return x * (1.5f - xh * x * x);
}
```

`g_sinLUT` is defined in a new `app/src/util/mathUtil.cpp`:
```cpp
#include "mathUtil.h"
float g_sinLUT[512];
```

`buildMathLUT()` called once in `main.cpp:setup()` before any app is ticked.

### Size

- `g_sinLUT[512]`: 2,048 B DRAM. One instance, shared by all consumers.
- `mathUtil.cpp`: 8 B (the array definition). Added to PlatformIO build automatically
  via `src_filter` (already includes all `src/` files).

### Include path

```cpp
#include "util/mathUtil.h"   // from aquariumApp.h and vuMeter.h
```

Works because PlatformIO adds `src/` to the include path.

---

## 12. Exit criteria

- All VE criteria in §7 pass.
- `[aq perf]` serial output shows ≥ 30% reduction in `tick` µs vs pre-opt baseline
  (aquarium alone); ≥ 20% reduction in draw µs (vuMeter + aquarium combined).
- `check_build.sh` passes on `cyd2usb_winamp` and `cyd2usb_winamp_debug`.
- ADR-038 authored and accepted.
