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
| CRAB-FIX-009 | Crab never moves in Y; add diagonal walk (Y coupled to X, 4 px range) |
| CRAB-FIX-010 | Leg sway runs full speed when stationary; reduce amp+frequency when not walking |
| CRAB-FIX-011 | Left claw pinch misaligns body and legs — variable-width body string shifts everything right |
| CRAB-FIX-012 | Fish proximity wakes sleeping crab; satiated cooldown not preventing re-feeding |
| CRAB-FIX-013 | No fish scatter on pinch strike — add radial flee burst within one body-width |
| CRAB-FIX-014 | Crab catches fish too reliably; reduce fish hit to 1-in-6 chance (flake rate unchanged) |

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

Replace `'` with `.` in `kLegFrames`, and draw legs in a darker red than the body:

```cpp
// before:
static const char* kLegFrames[4] = { "',,,", ",',,", ",,',", ",,,' " };
// after:
static const char* kLegFrames[4] = { ".,,,", ",.,," , ",,.," , ",,,." };
```

New constant for leg colour (body stays `TFT_RED`):
```cpp
static constexpr uint16_t CRAB_LEG_COLOR = _RGB565(160, 0, 0);  // dark red
```

In `drawCrab()`, set colour before drawing leg strings:
```cpp
_seaweedCanvas.setTextColor(CRAB_LEG_COLOR);
_seaweedCanvas.drawString(leftLegs,  lx, ly);
_seaweedCanvas.drawString(rightLegs, rx, ly);

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

New colour constant — dark red-purple, distinct from the crab body red:
```cpp
static constexpr uint16_t CRAB_SLEEP_Z_COLOR = _RGB565(120, 0, 80);  // dark red-purple
```

In the ZZZ draw loop, set colour once before the loop, then draw with sway:
```cpp
_seaweedCanvas.setTextColor(CRAB_SLEEP_Z_COLOR);
float swayX = sinf(nowSec * CRAB_SLEEP_SWAY_SPEED + phase) * CRAB_SLEEP_SWAY_AMP;
float swayY = cosf(nowSec * CRAB_SLEEP_SWAY_SPEED + phase) * CRAB_SLEEP_SWAY_Y_AMP;
_seaweedCanvas.drawChar(uint16_t(ch), zx + (int)swayX, zy + (int)swayY);
```

The `cosf` reuses the same angle already computed for `sinf` — no extra trig call if the compiler hoists it, or cache `cos` alongside `sin` in the loop.

---

## CRAB-FIX-009 — Crab diagonal walk (sideways like a real crab)

### Problem

Crab is glued to `CRAB_Y_LOCAL`. Real crabs walk sideways — the natural gait is diagonal, not purely horizontal. Y should only change when X is also changing; no independent up/down wandering.

### Design

Add `float y` and `float vy` to the Crab struct. `vy` is a slow Y velocity that is applied only while walking. Y is bounded to a 4 px range so the diagonal is subtle.

**New Crab struct fields:**
```cpp
float y;    // current Y; init = CRAB_Y_LOCAL
float vy;   // Y velocity (px/s); randomised on direction reversal
```

**Y bounds:**
```cpp
static constexpr int   CRAB_Y_MIN        = CRAB_Y_LOCAL - 4;  // 4 px total range
static constexpr int   CRAB_Y_MAX        = CRAB_Y_LOCAL;
static constexpr float CRAB_VY_MAX_PX_S  = 1.0f;              // keeps diagonal shallow
```

**Movement — in `updateCrab()` WALK state, after X is updated:**

Y moves only when X moves (coupled):
```cpp
c.y += c.vy * dt;
c.y  = _clamp(c.y, float(CRAB_Y_MIN), float(CRAB_Y_MAX));
// bounce vy at Y bounds so crab doesn't freeze against the wall:
if (c.y <= float(CRAB_Y_MIN) || c.y >= float(CRAB_Y_MAX)) c.vy = -c.vy;
```

**Randomise `vy` on X direction reversal** (edge hit or seaweed avoidance removed, but edge reversal remains):
```cpp
// where direction flips:
c.direction = -c.direction;
c.vy = _frand(-CRAB_VY_MAX_PX_S, CRAB_VY_MAX_PX_S);
```

Also set a random `vy` in `initCrab()`:
```cpp
_crab.vy = _frand(-CRAB_VY_MAX_PX_S, CRAB_VY_MAX_PX_S);
```

Y is **not updated** in SLEEP, PINCH, or CUTE states — crab stays put while not walking.

**In `drawCrab()`:** replace all `CRAB_Y_LOCAL` references with `(int)_crab.y`. ZZZ column anchor updates accordingly.

---

## CRAB-FIX-010 — Leg wave fades to idle when crab is not walking

### Problem

Leg sway runs at full amplitude and speed regardless of crab state. When the crab is standing still (SLEEP, PINCH, CUTE) the legs should barely twitch — reduced amplitude and frequency — rather than scrambling at walking pace.

### Design

A single float `legWaveIntensity` in the Crab struct acts as a scalar on both amplitude and speed. It lerps toward 1.0 while walking and toward a low idle value in all other states. One field, no extra per-frame branches in the draw path.

**New Crab struct field:**
```cpp
float legWaveIntensity;   // 0..1; init = 1.0f
```

**New constants:**
```cpp
static constexpr float CRAB_LEG_WAVE_IDLE_SCALE = 0.15f;  // 15% amp+speed at rest
static constexpr float CRAB_LEG_WAVE_LERP_RATE  = 2.0f;   // transition speed (units/s)
```

**In `updateCrab()`, at the end of every state's update block:**
```cpp
float waveTarget = (_crab.state == Crab::State::WALK) ? 1.0f : CRAB_LEG_WAVE_IDLE_SCALE;
_crab.legWaveIntensity += (waveTarget - _crab.legWaveIntensity) * CRAB_LEG_WAVE_LERP_RATE * dt;
```

At `CRAB_LEG_WAVE_LERP_RATE = 2.0`, the transition covers most of the range in ~0.5 s — snappy enough to feel responsive, slow enough to look organic.

**In `drawCrab()`, scale both amplitude and speed before the leg draw loop:**
```cpp
float effectiveAmp   = CRAB_LEG_WAVE_AMP   * _crab.legWaveIntensity;
float effectiveSpeed = CRAB_LEG_WAVE_SPEED  * _crab.legWaveIntensity;
float waveBase = _timeSec() * effectiveSpeed + _crab.phase;
float wave  = sinf(waveBase);
float waveC = cosf(waveBase);
// ... rest of leg draw loop unchanged, using effectiveAmp in place of CRAB_LEG_WAVE_AMP
```

No change to the draw loop structure — only the two scalars change.

---

## CRAB-FIX-011 — Left claw pinch body/leg misalignment

### Root cause

The crab body string in PINCH frames is wider than the idle `v(._.)v` because a claw character is prepended or appended. TFT_eSPI Font-2 glyph widths are variable, so the string drawn at `cx` pushes the right edge further right than usual. The left-legs anchor `lx = cx + CRAB_CHAR_W` and right-legs anchor `rx = cx + _crabBodyW - ...` are both computed from the same `cx`, so:

- **Left claw active** — the extended body string is wider; the whole body shifts right from `cx` (which is the top-left anchor). The right edge moves right, dragging the right leg group with it. The left edge stays at `cx` so legs appear misaligned under a wider body.
- **Right claw active** — the extension is on the right side; `cx` is unchanged, right edge shifts right. Left legs stay correct; right legs follow the new right edge. User confirms right claw looks acceptable — no fix needed.

### Design

Anchor the **right edge** of the body at a constant screen position during left-claw frames. The visible invariant is: right side of crab does not move when left claw extends.

Define a stable right-edge anchor:

```cpp
// resolved once in drawCrab(); used for left-claw compensation
int crabRightEdge = (int)_crab.x + _crabBodyW;   // right edge of idle body
```

For each PINCH frame, measure the actual body string width:

```cpp
int16_t frameBodyW = (int16_t)_seaweedCanvas.textWidth(bodyStr);
```

When the active claw is **left** (`direction == +1` means facing right → left claw leads; adjust for whichever directional convention `drawCrab()` uses):

```cpp
int drawCx = (leftClawActive)
    ? crabRightEdge - frameBodyW   // anchor right edge; shift cx left
    : (int)_crab.x;                // normal: anchor left edge
```

Use `drawCx` as the x origin for the body draw **and** for all leg anchor calculations this frame. Result: the right edge of the body stays fixed; the left claw grows leftward; legs stay symmetric under the (possibly narrower) portion of the body they were under before.

**Leg anchors from `drawCx`:**

```cpp
int lx = drawCx + CRAB_CHAR_W;
int rx = drawCx + frameBodyW - CRAB_CHAR_W - legStrW;
```

No new struct fields needed. `_crabBodyW` already cached. `frameBodyW` computed per draw call (cheap — one `textWidth` call).

### Clarification note

"Left claw active" maps to which PINCH frames. In the existing implementation the body strings for PINCH left vs right differ by which side has the claw character. The compensation fires only on the frame variants where the left side of the body string is extended.

---

## CRAB-FIX-012 — Fish must not wake sleeping crab; fix satiated cooldown

### Problems

Two independent issues:

**Issue A — Fish proximity wakes sleeping crab.**  
The SLEEP state timer fires and transitions to WALK regardless of what triggered the original SLEEP entry. If the tick rate is high enough that a fish passes over the crab before `sleepDurationMs` expires, no waking occurs — but the proximity scan in WALK immediately targets the fish and eats it, starting another SLEEP. The net effect is: a school of fish cycling over the crab keeps resetting the meal → sleep → wake → meal loop with no quiet period.

**Issue B — Satiated cooldown not visible.**  
`satiatedUntilMs` is set on `SLEEP→WALK` from a **meal** sleep. However if `sleepDurationMs` and `satiatedUntilMs` share the same `bool` path and `satiatedUntilMs` is never initialised to 0 in `initCrab()`, the condition `now >= c.satiatedUntilMs` is always true (unsigned wraparound). Additionally the cooldown is 30 s, but if the crab immediately re-enters SLEEP after CUTE (which is 3 s), the satiated timer is running while the crab is still asleep — by the time it wakes, the cooldown may already have expired.

### Fix A — Fish must not wake the crab

Fish proximity detection and targeting only runs in `WALK` state. **Do not add any fish-proximity check to the SLEEP state.** The crab in SLEEP must only wake via:
1. `sleepDurationMs` elapsed.
2. Tap (already in CRAB-FIX-007).

No code change needed if the current implementation already satisfies this — audit that SLEEP state update block contains no fish scan. If a fish scan exists there, remove it.

### Fix B — Satiated cooldown starts after CUTE, not before

The timeline should be:

```
PINCH (fish hit) → CUTE (3 s) → SLEEP (mealSleepMs) → WALK
                                                         ↑
                              satiatedUntilMs = now + CRAB_SATIATED_MS set HERE
```

The cooldown clock starts the moment the crab **wakes**, not when it falls asleep. Ensure `satiatedUntilMs` is assigned at the `SLEEP→WALK` transition (already the design intent in CRAB-FIX-007, but verify the implementation matches).

**Initialisation fix** — in `initCrab()`:

```cpp
_crab.satiatedUntilMs = 0;   // explicitly zero; 0 = hungry
```

The gate condition `now >= c.satiatedUntilMs` is then always true at init (crab starts hungry). Use a separate boolean or check `c.satiatedUntilMs != 0` before evaluating the timestamp comparison to avoid the `uint32_t` wraparound trap:

```cpp
bool satiated = (c.satiatedUntilMs != 0) && (now < c.satiatedUntilMs);
if (!satiated) {
    // fish scan
}
```

Clear `satiatedUntilMs` on SLEEP entry from idle (not meal) to prevent stale values:

```cpp
// WALK→SLEEP from idle timeout:
c.satiatedUntilMs = 0;
```

---

## CRAB-FIX-013 — Fish scatter on pinch strike

### Design

When the crab executes a pinch strike (PINCH state reaches the hit/miss frame — the same frame where a fish is consumed if one is in range), all fish within a scatter radius receive a brief flee impulse directed away from the crab centre. The radius is one crab body width (`CRAB_W_PX`).

**New constants:**

```cpp
static constexpr float CRAB_SCATTER_RADIUS_PX  = float(CRAB_W_PX);   // ≈ 42 px
static constexpr float CRAB_SCATTER_SPEED_PX_S = 80.0f;              // flee burst speed
static constexpr uint32_t CRAB_SCATTER_FLEE_MS = 600;                // flee duration
```

**Trigger point — in `updateCrab()`, at the PINCH strike frame transition:**

```cpp
// existing: check for fish hit, consume if found
// new: after that check, scatter nearby fish
_scatterFish((int)_crab.x + _crabBodyW / 2, (int)_crab.y);
```

**`_scatterFish(int cx, int cy)` — new method on `AquariumApp`:**

```cpp
void _scatterFish(int cx, int cy) {
    for (auto& f : _fish) {
        if (!f.alive) continue;
        float dx = f.x - float(cx);
        float dy = f.y - float(cy);
        float dist = sqrtf(dx * dx + dy * dy);
        if (dist > CRAB_SCATTER_RADIUS_PX) continue;
        // direction away from crab centre; handle dist == 0 gracefully
        float nx = (dist > 0.5f) ? dx / dist : (f.x < cx ? -1.0f : 1.0f);
        float ny = (dist > 0.5f) ? dy / dist : -1.0f;
        f.vx = nx * CRAB_SCATTER_SPEED_PX_S;
        f.vy = ny * CRAB_SCATTER_SPEED_PX_S;
        f.fleeUntilMs = millis() + CRAB_SCATTER_FLEE_MS;
    }
}
```

**New field on Fish struct:**

```cpp
uint32_t fleeUntilMs;   // 0 = normal; >0 = fleeing until this timestamp
```

**In `updateFish()` — while `fleeUntilMs` is active:**

- Use `f.vx`, `f.vy` directly as the fish velocity (override normal swim logic).
- Do **not** apply the normal speed/direction randomisation.
- On expiry (`now >= f.fleeUntilMs`), set `f.fleeUntilMs = 0` and let normal swim logic resume. The fish naturally blends back to its usual behaviour via the existing velocity smoothing.

**Boundary handling** — existing edge-clamp logic still fires during flee, so fish cannot scatter off screen.

**Eaten fish** — the consumed fish is already removed before `_scatterFish` runs; it will not be iterated (its `alive` flag is false).

---

## CRAB-FIX-014 — Fish hit probability: 1-in-6

### Problem

The crab lands every fish that enters pinch range with certainty. Combined with the proximity-targeting already in the design, it can clear a school quickly. A 1-in-6 random miss makes the crab feel fallible without requiring a change to the triggering geometry.

### Design

At the PINCH strike frame, before applying a fish hit, roll a single random check:

```cpp
static constexpr int CRAB_FISH_HIT_CHANCE = 6;   // 1-in-N success

// in updateCrab(), at the PINCH strike frame, fish branch only:
bool hitLands = (_rand() % CRAB_FISH_HIT_CHANCE == 0);
if (hitLands) {
    // consume fish, enter CUTE, set mealSleepMs, etc.
} else {
    // miss — still scatter fish (CRAB-FIX-013 fires regardless of hit/miss)
    // transition back to WALK directly (no CUTE, no sleep)
    c.state = Crab::State::WALK;
}
```

`_rand()` should use the same RNG already in the aquarium (e.g. `rand()` seeded at init, or `esp_random()` if available). No new seeding needed.

**Flakes are unaffected.** The hit-check gate wraps the fish branch only; the flake branch retains its existing logic (geometry only — if in range, hit succeeds).

**Scatter still fires on miss.** The pinch extended; nearby fish were startled whether or not the strike landed. `_scatterFish()` is called unconditionally at the strike frame, before the hit/miss branch.

**Miss animation.** On a miss the crab goes directly back to WALK rather than CUTE. This makes misses visually distinct (no celebration) and avoids a 3 s pause for nothing.

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
| CRAB-FIX-009 | Crab walks diagonally (Y coupled to X); ±4 px range, `vy` randomised on X reversal |
| CRAB-FIX-010 | Leg wave fades to 15% amp+speed when not walking; lerps at 2.0/s |
| CRAB-FIX-011 | Left claw pinch: right edge of crab stays fixed; legs remain symmetric under body |
| CRAB-FIX-012 | Sleeping crab ignores fish (only tap/timer wakes it); satiated cooldown active 30 s post-wake, verified on DUT |
| CRAB-FIX-013 | Pinch strike scatters fish within 42 px; fish flee for 600 ms then resume normal swim |
| CRAB-FIX-014 | Fish hit rate is 1-in-6; flake hit unchanged; miss → WALK directly (no CUTE); scatter still fires |
