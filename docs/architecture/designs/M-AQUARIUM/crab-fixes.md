# Design — Crab Post-Implementation Fixes

> Owner: Architect
> Status: draft
> Date: 2026-05-30
> Tracked-as: (pending task creation)
> Supersedes: crab.md §2, §4, §8 (where contradicted below)

---

## Context / pain points

Crab implemented per `crab.md`. Issues observed on DUT plus one enhancement:

| ID | Issue |
|----|-------|
| CRAB-FIX-001 | Crab chars have a black background; fish chars are transparent |
| CRAB-FIX-002 | Leg row misaligned — 4 legs on left side only; want 4 per side, symmetric |
| CRAB-FIX-003 | Crab stuck at one spot; no x movement |
| CRAB-FIX-004 | Seaweed trig cost forces two-zone split; fish floor constraint; 22 KB heap locked — replace with displacement LUT + uniform strips |
| CRAB-FIX-005 | Crab Y is fixed; add gentle full-body sway like fish swim wave |
| CRAB-FIX-006 | Leg raise char `'` too high — replace with `.` |
| CRAB-FIX-007 | Crab too aggressive; add post-meal sleep + satiated cooldown + tap-to-wake |
| CRAB-FIX-008 | ZZZ column sway too subtle; increase to ±4 px X, add ±2 px Y |
| CRAB-FIX-009 | Crab never moves in Y; add slow vertical wandering |

---

## CRAB-FIX-001 — Transparent char background

### Root cause

`drawCrab()` calls `_seaweedCanvas.setTextColor(TFT_RED, 0)` — two-arg form.  
In TFT_eSPI the two-arg form paints a solid fill-rectangle behind every glyph; `0` = `TFT_BLACK`.  
`drawFish()` calls `_canvas.setTextColor(color)` — single-arg, which leaves the background transparent.  
The comment `// transparent bg` in the original spec was incorrect.

### Fix

```cpp
// drawCrab() — replace:
_seaweedCanvas.setTextColor(TFT_RED, 0);
// with:
_seaweedCanvas.setTextColor(TFT_RED);
```

One character change. No other impact.

---

## CRAB-FIX-002 — Leg row alignment — 4 legs per side

### Root cause

`crab.md` specified one leg string starting at `lx = cx + CRAB_CHAR_W`. This placed all 4 legs under the left half of the body only. Font-2 glyph measurements show:

| String | Width |
|--------|-------|
| `,` (single comma) | 3 px |
| `,,,,` (4 commas) | 12 px |
| `v(._.)v` body | 49 px (`v`=8, `(`=7, `.`=5, `_`=9, `.`=5, `)`=7, `v`=8) |

### Fix design

Draw two separate 4-comma strings — one per side — at the same `y`, mirrored about the body centre.

**Placement geometry:**

```
body:        cx ←————————— 49 px —————————→ cx+49
left legs:   cx+6 ←12px→ cx+18
right legs:                    cx+31 ←12px→ cx+43
             gap from body edge = 6 px both sides ✓
```

Left start is unchanged: `lx = cx + CRAB_CHAR_W` (= cx+6).  
Right start is the mirror: `rx = cx + _crabBodyW - CRAB_CHAR_W - legStrW`.

**New members:**

```cpp
int16_t _crabBodyW = 49;   // measured once in init(); default matches font-2 measurement
```

**Measurement in `init()`, after `_canvas.setTextFont(2)`:**

```cpp
_crabBodyW = (int16_t)_canvas.textWidth("v(._.)v");
```

**Draw — two calls instead of one:**

```cpp
int16_t legStrW = (int16_t)_seaweedCanvas.textWidth(",,,,");
int lx = cx + CRAB_CHAR_W;
int rx = cx + _crabBodyW - CRAB_CHAR_W - legStrW;
_seaweedCanvas.drawString(leftLegs,  lx, ly);
_seaweedCanvas.drawString(rightLegs, rx, ly);
```

**Walk animation — left and right in opposite phase (offset by 2 frames):**

`kLegFrames` stays as 4-char strings (unchanged):
```cpp
static const char* kLegFrames[4] = { "',,,", ",',,", ",,',", ",,,' " };
```

```cpp
const char* leftLegs  = (walking) ? kLegFrames[c.walkFrame]          : ",,,,";
const char* rightLegs = (walking) ? kLegFrames[(c.walkFrame + 2) & 3] : ",,,,";
```

Result at each frame:

| walkFrame | left | right | effect |
|-----------|------|-------|--------|
| 0 | `',,,` | `,,,'` | outer legs up |
| 1 | `,',,` | `,,',` | inner-outer up |
| 2 | `,,',` | `,',,` | inner-outer up (swapped) |
| 3 | `,,,,'` | `',,,` | outer legs up (swapped) |

### Constants

`CRAB_W_PX` remains `7 * CRAB_CHAR_W = 42` (body width for edge bounds) — no change needed.

---

## CRAB-FIX-003 — Crab stuck at spawn position

### Root cause

The seaweed avoidance loop in `updateCrab()` fires immediately at spawn because the initial x (`AQ_CANVAS_W * 0.5f = 137.5`) overlaps seaweed root 6 (≈ 149.1 px). When the collision fires it resets `nextX = c.x` and flips `c.direction`; the next frame the same overlap fires and flips direction back. Crab oscillates in place indefinitely.

### Decision — remove seaweed avoidance entirely

The crab renders in `_seaweedCanvas` **after** `drawSeaweed()`, so it already composites on top of seaweed. There is no visual interaction between the crab and seaweed roots that the player would perceive. The avoidance logic has no payoff and is the direct cause of the stuck bug.

### Fix

Delete the seaweed avoidance loop from `updateCrab()`:

```cpp
// remove entirely:
for (int i = 0; i < AQ_SEAWEED_ROOTS; ++i) {
    float sw = _seaweedBaseX[i];
    if (nextX < sw + float(CRAB_SEAWEED_PAD_PX) &&
        nextX + float(CRAB_W_PX) > sw - float(CRAB_SEAWEED_PAD_PX)) {
        c.direction = -c.direction;
        nextX = c.x;
        break;
    }
}
```

The spawn x (`AQ_CANVAS_W * 0.5f`) is fine once the avoidance loop is gone — no change needed to `initCrab()`.

Also remove the now-dead constants `CRAB_SEAWEED_PAD_PX`.

---

## CRAB-FIX-004 — Seaweed displacement LUT + canvas unification

### Problem

Two compounding issues:
1. `drawSeaweed()` is the most expensive render call — 12 stalks × ~10 `sinf`/`cosf` calls each ≈ 120+ trig ops per frame.
2. The dedicated `_seaweedCanvas` (275×80, 22 KB heap) exists specifically to avoid recomputing that trig on every strip pass. It creates an architectural split that bars fish, octopus, and seahorse from y:160–239 (the fish floor bug from the original CRAB-FIX-004).

### Insight

Every seaweed stalk is the same canonical waveform. They differ only in phase offset, speed, height, and x position. The demoscene answer: precompute one full animation cycle of the canonical waveform as a **displacement table in flash**, then instance it per stalk with per-stalk parameters. Zero `sinf` at render time.

With trig eliminated, seaweed rendering becomes cheap enough to run inside the strip loop alongside fish. `_seaweedCanvas` is no longer needed. The two-zone split collapses. Fish, crab, and all other entities render uniformly across all 240px.

### LUT design

Precompute x-displacement at 32 phase steps × 8 height samples (matching the 7 spine segments):

```cpp
// PROGMEM flash — 32 × 8 × 1 B = 256 B
// int8_t: signed pixel offset from root x, canonical stalk (bh ≈ 50)
static const int8_t kSeaweedDisp[32][8] PROGMEM;
```

Generated offline (Python, run once, result embedded as a literal array):

```python
import math, struct

PHASES = 32
SEGS   = 8          # u = 0/7 .. 7/7
AQ_SWAY = 1.10
bh      = 50.0      # canonical stalk height
amp     = 7.0       # mid-range amplitude

result = []
for p in range(PHASES):
    t = p * (2 * math.pi / PHASES)
    sw           = math.sin(t * 0.8 * AQ_SWAY) * amp
    phase_body   = t * 1.05 * AQ_SWAY
    phase_ripple = t * 0.72 * AQ_SWAY
    row = []
    for s in range(SEGS):
        u = s / (SEGS - 1)
        bend   = sw * u * (0.20 + u * 0.80)
        travel = math.sin(phase_body - u * 5.1) * (1.5 + bh * 0.055) * u * u
        detail = math.sin(phase_ripple + u * 9.0) * 1.2 * u
        dx = bend + travel + detail
        row.append(max(-127, min(127, int(round(dx)))))
    result.append(row)
```

Values fit comfortably in `int8_t` (observed range ≈ −12..+12 px at canonical height).

### Per-stalk scaling

Each stalk has its own `bh` (height, set from `kHeightNoise`). The `travel` term scales with `(1.5 + bh*0.055)`. Rather than a second LUT dimension, multiply the LUT displacement by `bh / 50.0f` at render time — accurate for the dominant `travel` term, negligible error on `bend` and `detail`. One float multiply per segment, no trig.

### Per-stalk phase advance

Each stalk needs a phase index that advances over time at its own rate:

```cpp
// per-stalk derived constants (computed once in init, stored in small arrays):
float _seaweedSpeed[AQ_SEAWEED_ROOTS];   // advance rate (rad/s) — varies per root
float _seaweedPhase[AQ_SEAWEED_ROOTS];   // initial phase offset
```

At render time:
```cpp
uint8_t phaseIdx = (uint8_t)(int(t * _seaweedSpeed[i] * PHASES / TWO_PI
                                 + _seaweedPhase[i]) & (PHASES - 1));
```

One integer add + mask per stalk. No trig.

### Rendering with LUT

`drawSeaweed()` inner loop becomes:

```cpp
for (int i = 0; i < AQ_SEAWEED_ROOTS; ++i) {
    float bx   = 10.0f + i * (AQ_CANVAS_W - 20.0f) / float(AQ_SEAWEED_ROOTS - 1);
    float bh   = _clamp(32.0f * AQ_SEAWEED_LEN * (1.0f + AQ_SEAWEED_RAND * kHeightNoise[i]), 18.0f, 72.0f);
    float scale = bh / 50.0f;
    uint8_t pi  = phaseIdx(i, t);
    float px = bx, py = float(y0);
    for (int s = 1; s < 8; ++s) {
        float nx = bx + (int8_t)pgm_read_byte(&kSeaweedDisp[pi][s]) * scale;
        float ny = float(y0) - bh * s / 7.0f;
        uint16_t col = (s < 3) ? TFT_DARKGREEN : (s < 6) ? TFT_GREEN : TFT_GREENYELLOW;
        _canvas.drawLine(int(px), int(py) - stripY, int(nx), int(ny) - stripY, col);
        _canvas.drawLine(int(px)+1, int(py) - stripY, int(nx)+1, int(ny) - stripY, TFT_DARKGREEN);
        px = nx; py = ny;
    }
}
```

Branches: interpolate x between adjacent LUT samples at fractional `u`. Acceptable approximation.

### Canvas architecture change

With seaweed now strip-renderable, `_seaweedCanvas` is dropped:

| Before | After |
|--------|-------|
| `_canvas` 275×40, 4 strip passes → y:0–159 | `_canvas` 275×40, **6** strip passes → y:0–239 |
| `_seaweedCanvas` 275×80, 1 pass → y:160–239 | *(removed)* |
| Total heap: 11 KB + 22 KB = **33 KB** | Total heap: **11 KB** |

`AQ_STRIP_COUNT` changes from 4 → 6. `AQ_SEAWEED_Y`, `AQ_SEAWEED_SPRITE_H`, `AQ_SEAWEED_Y_LOCAL` constants removed. `_seaweedCanvas` member removed.

`drawSeaweed()`, `drawCrab()`, and all entities that currently draw to `_seaweedCanvas` are redirected to `_canvas` with the `stripY` offset convention already used by fish.

### Fish floor resolved

With a uniform strip model, the fish y-clamp relaxes from `[14, 146]` to `[14, AQ_CANVAS_H − 20]`. Fish, octopus, and seahorse can descend into the seaweed zone. Draw order within each strip naturally determines layering: seaweed drawn before fish → fish appear in front of seaweed fronds.

### Memory delta

| Item | Before | After |
|------|--------|-------|
| `_seaweedCanvas` heap | 22,000 B | 0 |
| `kSeaweedDisp` flash | 0 | 256 B |
| `_seaweedSpeed/Phase` arrays | 0 | 96 B `.bss` |
| **Net heap saving** | | **−22,000 B** |

---

## CRAB-FIX-005 — Leg row per-character Y sway

### Design

Body row `v(._.)v` is drawn static at `CRAB_Y_LOCAL` — no sway, directly positioned.

Leg row characters are drawn individually (like fish chars) with a per-character Y offset from a sine wave. This makes the legs appear to scramble underfoot while the body stays planted.

**Same technique as fish** (`drawFish()` line ~987): maintain a `wave`/`waveC` pair rotated by a fixed angle step per character, accumulate from the same `waveBase = _timeSec() * speed`.

**New constants:**

```cpp
static constexpr float CRAB_LEG_WAVE_SPEED   = 4.0f;   // rad/s — lively but not frantic
static constexpr float CRAB_LEG_WAVE_AMP     = 2.0f;   // ±2 px → 4 px total Y range
static constexpr float CRAB_LEG_WAVE_SPACING = 0.85f;  // same spacing constant as fish
```

**New field in `Crab` struct:**

```cpp
float phase;   // set once at initCrab(); offsets leg wave start
```

Set in `initCrab()`:
```cpp
_crab.phase = _frand(0.0f, 6.28318f);
```

**Draw loop for each leg string** (left and right, same approach):

```cpp
// shared wave state — initialised once, advanced per char
float waveBase = _timeSec() * CRAB_LEG_WAVE_SPEED + _crab.phase;
float wave  = sinf(waveBase);
float waveC = cosf(waveBase);
static const float kLegSin = sinf(CRAB_LEG_WAVE_SPACING);
static const float kLegCos = cosf(CRAB_LEG_WAVE_SPACING);

// draw left legs char by char
for (int i = 0; i < 4; ++i) {
    char ch = leftLegs[i];
    int yo  = (int)(wave * CRAB_LEG_WAVE_AMP);
    _seaweedCanvas.drawChar(uint16_t(ch), lx + i * legCharW, ly + yo);
    float nw = wave * kLegCos + waveC * kLegSin;
    waveC    = waveC * kLegCos - wave  * kLegSin;
    wave     = nw;
}
// draw right legs — continue the same wave (seamless ripple across all 8 legs)
for (int i = 0; i < 4; ++i) {
    char ch = rightLegs[i];
    int yo  = (int)(wave * CRAB_LEG_WAVE_AMP);
    _seaweedCanvas.drawChar(uint16_t(ch), rx + i * legCharW, ly + yo);
    float nw = wave * kLegCos + waveC * kLegSin;
    waveC    = waveC * kLegCos - wave  * kLegSin;
    wave     = nw;
}
```

`legCharW` = measured width of a single `,` = 3 px (from font-2 table; can be measured as `_seaweedCanvas.textWidth(",")` or hardcoded as `CRAB_LEG_CHAR_W = 3`).

The wave is **continuous across both leg groups** — left 4 chars advance the wave state, right 4 pick up from where left left off, giving a single ripple rolling across all 8 legs.

Body row, ZZZ column, and all other draw calls remain at fixed `CRAB_Y_LOCAL`.

---

## CRAB-FIX-006 — Leg raise character: `'` → `.`

### Problem

The apostrophe (`'`) renders near the top of the character cell — visually it looks like the leg is flying upward rather than being subtly lifted. The period (`.`) sits at the baseline mid-height, giving a much more subtle "foot lifted slightly off the ground" impression.

### Fix

Replace `'` with `.` in `kLegFrames`:

```cpp
// before:
static const char* kLegFrames[4] = { "',,,", ",',,", ",,',", ",,,' " };
// after:
static const char* kLegFrames[4] = { ".,,,", ",.,," , ",,.," , ",,," };
```

One-line change. No logic, no constant, no struct change.

---

## CRAB-FIX-007 — Post-meal sleep + satiated cooldown + tap-to-wake

### Problem

Crab eats fish too aggressively — no consequence for a kill, no hunger cycle.

### Design

**Three new behavioural layers stacked on the existing state machine:**

#### Layer 1 — Post-meal sleep duration scales with fish size

On a successful pinch hit, sleep duration is proportional to `visualWidth` of the eaten fish:

```cpp
// fish visualWidth range ≈ 12 px (smallest) .. 66 px (largest)
static constexpr uint32_t CRAB_MEAL_SLEEP_MIN_MS = 10000;   // 10 s
static constexpr uint32_t CRAB_MEAL_SLEEP_MAX_MS = 60000;   // 60 s
static constexpr int      CRAB_MEAL_FISH_W_MIN   = 12;
static constexpr int      CRAB_MEAL_FISH_W_MAX   = 66;

uint32_t mealSleepMs = CRAB_MEAL_SLEEP_MIN_MS
    + uint32_t((visualWidth - CRAB_MEAL_FISH_W_MIN)
               * (CRAB_MEAL_SLEEP_MAX_MS - CRAB_MEAL_SLEEP_MIN_MS)
               / (CRAB_MEAL_FISH_W_MAX - CRAB_MEAL_FISH_W_MIN));
```

New field in Crab struct:
```cpp
uint32_t sleepDurationMs;   // set on SLEEP entry; 0 = use CRAB_SLEEP_MS (idle default)
```

On SLEEP entry from a meal: `c.sleepDurationMs = mealSleepMs`.  
On SLEEP entry from idle timeout: `c.sleepDurationMs = CRAB_SLEEP_MS`.  
SLEEP→WALK transition uses `c.sleepDurationMs` instead of the hardcoded constant.

#### Layer 2 — Satiated cooldown (no fish targeting after a meal)

After waking from a **meal sleep**, the crab ignores fish for a cooldown period but will still eat flakes.

New field in Crab struct:
```cpp
uint32_t satiatedUntilMs;   // absolute timestamp; 0 = hungry
```

New constant:
```cpp
static constexpr uint32_t CRAB_SATIATED_MS = 30000;   // 30 s post-wake cooldown
```

On SLEEP→WALK from a meal sleep: `c.satiatedUntilMs = now + CRAB_SATIATED_MS`.  
On SLEEP→WALK from idle sleep: `c.satiatedUntilMs` unchanged (already 0 or expired).

In `updateCrab()` WALK proximity scan — fish targeting gate:
```cpp
// only add fish to pinch candidates if not satiated:
if (now >= c.satiatedUntilMs) {
    // ... existing fish scan
}
// flake scan always runs
```

#### Layer 3 — Tap crab to reduce sleep + satiated timers

In `handleInput()`, before spawning a flake, check if the touch falls on the crab:

```cpp
bool onCrab = (x >= (int)_crab.x && x <= (int)_crab.x + CRAB_W_PX
            && y >= CRAB_Y - 4 && y <= CRAB_Y + CRAB_CHAR_H + CRAB_LEG_OVERLAP_PX + 4);
```

If `onCrab`:
- **In SLEEP:** advance sleep by 8 s (`c.stateEnteredMs -= 8000`), clamped so remaining sleep ≥ 1 s.
- **In WALK (satiated):** reduce `c.satiatedUntilMs` by 10 s per tap, floor at `now`.
- Do **not** spawn a flake on a crab tap.
- Return `true` (input consumed).

New constant:
```cpp
static constexpr uint32_t CRAB_TAP_SLEEP_SKIP_MS   = 8000;
static constexpr uint32_t CRAB_TAP_SATIATED_SKIP_MS = 10000;
```

### State machine delta

```
PINCH frame 3 (fish hit) → CUTE(3 s) → SLEEP(mealSleepMs) → WALK + satiatedUntilMs set
PINCH frame 3 (flake hit) → CUTE(3 s) → WALK (no satiated — flakes don't count)
tap while SLEEP           → stateEnteredMs advanced (wake sooner)
tap while satiated WALK   → satiatedUntilMs reduced (hunger restored sooner)
```

All other transitions unchanged.

---

## CRAB-FIX-008 — ZZZ sway: +2 px in both X and Y

### Problem

Current ZZZ column only sways in X at ±2 px. User wants more expressiveness: ±4 px X, ±2 px Y.

### Fix

Increase `CRAB_SLEEP_SWAY_AMP` and add a Y component using the cosine of the same wave (90° phase offset from X — gives elliptical rather than straight-line motion):

```cpp
// before:
static constexpr float CRAB_SLEEP_SWAY_AMP   = 2.0f;

// after:
static constexpr float CRAB_SLEEP_SWAY_AMP   = 4.0f;   // X: was 2, now 4
static constexpr float CRAB_SLEEP_SWAY_Y_AMP = 2.0f;   // Y: new
```

In the ZZZ draw loop:
```cpp
float swayX = sinf(nowSec * CRAB_SLEEP_SWAY_SPEED + phase) * CRAB_SLEEP_SWAY_AMP;
float swayY = cosf(nowSec * CRAB_SLEEP_SWAY_SPEED + phase) * CRAB_SLEEP_SWAY_Y_AMP;
_seaweedCanvas.drawChar(uint16_t(ch), zx + (int)swayX, zy + (int)swayY);
```

The `cosf` reuses the same angle already computed for `sinf` — no extra trig call if the compiler hoists it, or cache `cos` alongside `sin` in the loop.

---

## CRAB-FIX-009 — Crab Y wandering

### Problem

Crab is glued to `CRAB_Y_LOCAL`. It never moves vertically, making it feel pinned rather than alive.

### Design

Add `float y` to the Crab struct (alongside existing `float x`). The crab wanders slowly in Y within the bottom zone.

**New Crab struct fields:**
```cpp
float y;          // current Y in canvas-local coords; init = CRAB_Y_LOCAL
float targetY;    // destination the crab drifts toward
```

**Y bounds** (bottom zone, leaves room for legs):
```cpp
static constexpr int CRAB_Y_MIN = CRAB_Y_LOCAL - 35;   // up from floor
static constexpr int CRAB_Y_MAX = CRAB_Y_LOCAL;         // floor
```

**Movement** — in `updateCrab()` WALK state, periodically pick a new `targetY` and drift toward it:
```cpp
// re-target occasionally (reuse existing cute-chance style roll):
if (random(10000) < 3) {   // ~0.03% per tick → new target every ~30 s on average
    c.targetY = _frand(float(CRAB_Y_MIN), float(CRAB_Y_MAX));
}
// drift toward target at fixed speed (slower than X):
float dy = c.targetY - c.y;
float step = CRAB_Y_SPEED_PX_S * dt;
if (fabsf(dy) < step) c.y = c.targetY;
else                   c.y += (dy > 0 ? step : -step);
```

New constant:
```cpp
static constexpr float CRAB_Y_SPEED_PX_S = 4.0f;   // ~1/3 of X speed
```

**In `drawCrab()`:** replace all `CRAB_Y_LOCAL` references with `(int)_crab.y`. ZZZ column anchor updates accordingly. No other draw changes needed.

**SLEEP / PINCH states:** `y` is not updated while not in WALK (crab stays put). `targetY` persists across state changes.

---

## Exit criteria

| ID | Done when |
|----|-----------|
| CRAB-FIX-001 | Crab chars composite cleanly over seaweed background — no black rectangles |
| CRAB-FIX-002 | Four legs visible on each side of body, symmetric, on DUT |
| CRAB-FIX-003 | Crab walks continuously left/right, reverses at edges |
| CRAB-FIX-004 | `_seaweedCanvas` removed; 6-strip model covers full 240px; fish swim into seaweed zone; heap reduced by 22 KB |
| CRAB-FIX-005 | Crab bobs gently at ~1.2 rad/s, ±1–2 px; ZZZ column tracks the bob |
| CRAB-FIX-006 | Leg raise uses `.` — subtle lift at baseline, not `'` flying high |
| CRAB-FIX-007 | Post-meal sleep (10–60 s by fish size); satiated cooldown (30 s, fish-only); tap crab to reduce both |
| CRAB-FIX-008 | ZZZ sways ±4 px X, ±2 px Y (elliptical motion) |
| CRAB-FIX-009 | Crab drifts in Y within ±35 px of floor at 4 px/s; `y` and `targetY` added to struct |
