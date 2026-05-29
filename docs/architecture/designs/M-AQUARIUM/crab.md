# Design — Aquarium Crab (M-AQUARIUM-CRAB)

> Owner: Architect
> Status: draft
> Date: 2026-05-29

---

## 1. Feature Scope

One red ASCII crab that lives on the bottom of the aquarium canvas.

| Behaviour | Description |
|---|---|
| Walk | Crab moves left/right slowly along the bottom, reversing at canvas edges and seaweed roots |
| Pinch | When a fish or food flake enters range, extends the nearest claw toward the target for a short burst |
| Emote: normal | Default walking / idle |
| Emote: cute (idle) | Rare random double-blink; 1.5 s total (base→cute→base→cute→base) |
| Emote: cute (hit) | Triggered on successful pinch; 3 s duration; target fish removed from pool |
| Emote: sleep | Very rare; triggered after a long period with no nearby targets |

---

## 2. ASCII Sprites

Font: TFT font 2 (~6 px/char wide, ~14 px tall). `v` = open claw. `,` = leg down. `'` = leg raised.

The crab is **two rows**, drawn with the leg row overlapping the body row by `CRAB_LEG_OVERLAP_PX` (8 px), so legs appear attached rather than floating beneath.

```
row 0 (body):  v(._.)v        y = CRAB_Y
row 1 (legs):   ,,,,          y = CRAB_Y + CRAB_LEG_OVERLAP_PX
```

Leg row x offset: `cx + CRAB_CHAR_W` — starts under the `(` bracket, centred beneath the body.

---

### Walk — 4-frame leg cycle

One raised leg (`'`) sweeps through 4 positions. Sweep direction matches walk direction.

```
Frame 0:  ',,,     (raised at pos 1)
Frame 1:  ,',,     (raised at pos 2)
Frame 2:  ,,',     (raised at pos 3)
Frame 3:  ,,,'     (raised at pos 4)
```

Walking right → frames advance 0→1→2→3→0  
Walking left  → frames advance 3→2→1→0→3

Body row `v(._.)v` is static during walk; only the leg row changes.

---

### Pinch — 4-frame sequence per claw

Body row plays the 4-frame claw animation. Leg row stays at `,,,,` (crab stationary while pinching).

Frame 0 is the neutral rest state. Frame 1 is the new "look up" beat — eyes shift from `._. ` to `°_°` as the crab spots the target. Frames 2–3 keep the `°_°` eyes and add the claw motion from the original design.

**Right claw:**
```
Frame 0:  v(._.)v   +  ,,,,     at rest, not yet aware
Frame 1:  v(o_o)v   +  ,,,,     spots target — wide-eyed, claws still open
Frame 2:  v(o_O)V   +  ,,,,     right eye widens toward target; claw raises (V at y - CRAB_CLAW_RISE_PX)
Frame 3:  v(o_o(|)  +  ,,,,     claw snaps closed, eyes settle
```

**Left claw:**
```
Frame 0:  v(._.)v   +  ,,,,
Frame 1:  v(o_o)v   +  ,,,,     spots target
Frame 2:  V(O_o)v   +  ,,,,     left eye widens toward target; claw raises (V at y - CRAB_CLAW_RISE_PX)
Frame 3:  (|)(o_o)v +  ,,,,     claw snaps closed, eyes settle
```

Frame 2 is a split draw (two `drawString` calls): body with claw char replaced by space at `y = CRAB_Y`, then the raised `V` alone at `y = CRAB_Y - CRAB_CLAW_RISE_PX`. Frames 0, 1, 3 are single `drawString` calls.

---

### Emotes

**Cute:** alternates between base and cute face — a double-blink. Each phase lasts `CRAB_CUTE_BLINK_MS` (375 ms). Sequence: base → cute → base → cute → base.

```
v(._.)v  +  ,,,,    phase 0 (base)
v(^.^)v  +  ,,,,    phase 1 (cute)
v(._.)v  +  ,,,,    phase 2 (base)
v(^.^)v  +  ,,,,    phase 3 (cute)
v(._.)v  +  ,,,,    phase 4 (base) → exit
```

Two durations share the same animation:
- **Idle cute** (`CRAB_CUTE_IDLE_MS = 1500 ms`) — triggered randomly; exits to WALK after phase 4.
- **Hit cute** (`CRAB_CUTE_HIT_MS = 3000 ms`) — triggered on successful pinch; plays two full cycles (8 phases); exits to WALK after.

Phase index: `(elapsed / CRAB_CUTE_BLINK_MS) % 2` — odd = cute face, even = base face.  
Exit: `elapsed >= _crab.cuteDurationMs`.

**Sleep:** body + static legs + animated vertical `zZzz` column above the head.
```
v(-.-)v  +  ,,,,
```

#### Sleep ZZZ animation

A column of 4 characters (`z`/`Z`) is drawn vertically above the crab's head, bottom-to-top. One capital `Z` sweeps upward through 4 positions (frame 0 = bottom, frame 3 = top), then loops back to 0. The column sways left/right using the same sinf-based formula as the seaweed.

```
Frame 0   Frame 1   Frame 2   Frame 3       ← sleepZFrame
  z         z         z         Z           ← top    (highest y offset)
  z         z         Z         z
  z         Z         z         z
  Z         z         z         z           ← bottom (CRAB_Y - CRAB_SLEEP_BASE_Y)
```

**Spacing:** characters placed every `CRAB_SLEEP_STEP_PX` = 7 px (half of font-2 height ~14 px).

**Sway:** each character's x is offset by:
```cpp
float phase = i * CRAB_SLEEP_SWAY_PHASE;   // phase shifts with height index
float swayX = sinf(nowSec * CRAB_SLEEP_SWAY_SPEED + phase) * CRAB_SLEEP_SWAY_AMP;
```
Higher characters have larger phase offset → column bends like a seaweed frond.

**X anchor:** centred over the crab body — `cx + 3 * CRAB_CHAR_W` (middle of `v(._.)v`).

---

## 3. State Machine

```
          ┌──────────────────────────────────────┐
          │                 WALK                 │◄─────────────────────────┐
          └──┬────────────┬──────────┬───────────┘                          │
             │ target     │ rare     │ long idle                             │
             ▼ in range   ▼ roll    ▼ (no targets)                         │
         PINCH_L/R      CUTE        SLEEP ─── duration elapsed ─────────────┤
             │  (miss)                                                       │
             ├──────────────────────────────────────────────────────────────┘
             │  (hit → remove fish)
             ▼
           CUTE (hit, 3 s) ────── duration elapsed ──────────────────────────┘
```

| Transition | Condition |
|---|---|
| WALK → PINCH_L/R | fish or flake within `CRAB_PINCH_RANGE_PX` and in bottom zone; side = sign of dx; `pinchFrame` reset to 0 |
| PINCH frame 3 → WALK (miss) | hold expires, proximity re-check finds no target; `pinchFrame` reset to 0 |
| PINCH frame 3 → CUTE (hit) | hold expires, proximity re-check finds target; target fish removed from pool; `cuteDurationMs = CRAB_CUTE_HIT_MS` |
| WALK → CUTE (idle) | random roll `< CRAB_CUTE_CHANCE` per tick, no nearby targets; `cuteDurationMs = CRAB_CUTE_IDLE_MS` |
| CUTE → WALK | `elapsed >= _crab.cuteDurationMs` |
| WALK → SLEEP | no targets detected for `CRAB_IDLE_SLEEP_MS` |
| SLEEP → WALK | `CRAB_SLEEP_MS` elapsed, OR target detected (wakes up) |

---

## 4. Positioning

- **Y** is fixed: `CRAB_Y = AQ_CANVAS_H - CRAB_FOOT_PX` (≈ 214). Bottom of leg row sits 4 px from canvas edge (`CRAB_BOTTOM_MARGIN_PX = 4`).
- **X** wanders as a `float` in `[CRAB_MARGIN_PX, AQ_CANVAS_W - CRAB_W_PX - CRAB_MARGIN_PX]`.
- On reaching either bound, `direction` flips.
- **Seaweed avoidance:** each `updateCrab()` step checks if the crab's next x would place its body overlapping any seaweed root ± `CRAB_SEAWEED_PAD_PX`. If so, reverse direction immediately. Seaweed root x-positions must be accessible from `drawCrab()` — expose them via a small accessor or pass them in as an array. See §9 for integration note.

---

## 5. Proximity Check

Each `updateCrab()` call, scan:

1. **Flakes:** `_flakes[i].active && fabsf(_flakes[i].x - _crab.x) < CRAB_PINCH_RANGE_PX && _flakes[i].y > CRAB_BOTTOM_ZONE_Y`
2. **Fish:** active fish (`_fishPool[i].active`) within `CRAB_PINCH_RANGE_PX` horizontally and `_fishPool[i].y > CRAB_BOTTOM_ZONE_Y`

First match found → enter `PINCH_L` or `PINCH_R` (whichever side the target is on; tie → `PINCH_R`).

Proximity check runs only while state is `WALK` or `SLEEP`. A crab already pinching does not re-trigger until it returns to `WALK`.

---

## 6. Constants

```cpp
static constexpr int   CRAB_CHAR_W           = 6;     // font-2 char width (px) — tune on DUT
static constexpr int   CRAB_CHAR_H           = 14;   // font-2 char height (px)
static constexpr int   CRAB_W_PX             = 7 * CRAB_CHAR_W;   // body row width (42 px)
static constexpr int   CRAB_LEG_OVERLAP_PX   = 8;    // leg row offset below body row
static constexpr int   CRAB_BOTTOM_MARGIN_PX = 4;    // gap between bottom of leg row and canvas edge
static constexpr int   CRAB_FOOT_PX          = CRAB_BOTTOM_MARGIN_PX + CRAB_CHAR_H + CRAB_LEG_OVERLAP_PX; // 26
static constexpr int   CRAB_Y                = AQ_CANVAS_H - CRAB_FOOT_PX;  // body row y (~214)
static constexpr int   CRAB_MARGIN_PX        = 8;
static constexpr float CRAB_SPEED_PX_S       = 12.0f;
static constexpr int   CRAB_PINCH_RANGE_PX   = 45;
static constexpr int   CRAB_BOTTOM_ZONE_Y    = AQ_CANVAS_H - 80; // only pinch targets in lower 80px
static constexpr uint32_t CRAB_WALK_STEP_MS  = 200;  // ms per walk frame (4 frames = 800 ms/cycle)
static constexpr uint32_t CRAB_PINCH_FRAME_MS = 180; // ms per pinch frame (3 frames = 540 ms)
static constexpr uint32_t CRAB_PINCH_HOLD_MS  = 200; // hold on closed-claw frame before returning
static constexpr int   CRAB_CLAW_RISE_PX     = 3;    // y lift for raised-claw frame
static constexpr float CRAB_CUTE_CHANCE      = 0.0004f;
static constexpr uint32_t CRAB_CUTE_BLINK_MS = 375;   // ms per blink phase (1500 ms / 4 phases)
static constexpr uint32_t CRAB_CUTE_IDLE_MS  = 1500;  // random idle cute: 2 blinks
static constexpr uint32_t CRAB_CUTE_HIT_MS   = 3000;  // successful pinch cute: 4 blinks
static constexpr uint32_t CRAB_IDLE_SLEEP_MS = 20000;
static constexpr uint32_t CRAB_SLEEP_MS      = 5000;
static constexpr int   CRAB_SEAWEED_PAD_PX    = 6;
// Sleep ZZZ column
static constexpr int   CRAB_SLEEP_BASE_Y      = 16;   // px above CRAB_Y where bottom z sits
static constexpr int   CRAB_SLEEP_STEP_PX     = 7;    // half font-2 height — tight overlap
static constexpr int   CRAB_SLEEP_Z_COUNT     = 4;
static constexpr uint32_t CRAB_SLEEP_Z_MS     = 400;  // ms per Z position advance
static constexpr float CRAB_SLEEP_SWAY_AMP    = 2.0f; // px max horizontal sway
static constexpr float CRAB_SLEEP_SWAY_SPEED  = 1.5f; // rad/s (≈ seaweed AQ_SWAY rate)
static constexpr float CRAB_SLEEP_SWAY_PHASE  = 0.5f; // phase shift per height index
```

---

## 7. Struct

```cpp
struct Crab {
    enum class State : uint8_t { WALK, PINCH_L, PINCH_R, CUTE, SLEEP };

    float    x;
    int8_t   direction;        // +1 right, -1 left
    State    state;
    uint8_t  walkFrame;        // 0-3; leg sweep position; advances in direction order
    uint8_t  pinchFrame;       // 0-2; valid in PINCH_L/R only
    uint8_t  sleepZFrame;      // 0-3; which position holds the capital Z (0=bottom)
    uint32_t cuteDurationMs;   // CRAB_CUTE_IDLE_MS or CRAB_CUTE_HIT_MS — set on CUTE entry
    uint32_t stateEnteredMs;
    uint32_t walkFrameMs;
    uint32_t pinchFrameMs;
    uint32_t sleepZFrameMs;
    uint32_t lastTargetSeenMs;
};
```

---

## 8. Draw Function

```cpp
static const char* kLegFrames[4] = { "',,,", ",',,", ",,',", ",,,' " };

void drawCrab() {
    _canvas.setTextFont(2);
    _canvas.setTextColor(TFT_RED, 0);  // transparent bg

    int cx  = (int)_crab.x;
    int lx  = cx + CRAB_CHAR_W;       // leg row x: under the '(' bracket
    int ly  = CRAB_Y + CRAB_LEG_OVERLAP_PX;

    // --- body row ---
    switch (_crab.state) {
        case Crab::State::WALK:
            _canvas.drawString("v(._.)v", cx, CRAB_Y);
            break;

        case Crab::State::CUTE: {
            uint32_t elapsed = millis() - _crab.stateEnteredMs;
            bool showCute = ((elapsed / CRAB_CUTE_BLINK_MS) % 2) == 1;
            _canvas.drawString(showCute ? "v(^.^)v" : "v(._.)v", cx, CRAB_Y);
            break;
        }

        case Crab::State::SLEEP:
            _canvas.drawString("v(-.-)v", cx, CRAB_Y);
            break;

        case Crab::State::PINCH_R:
            switch (_crab.pinchFrame) {
                case 0: _canvas.drawString("v(._.)v",  cx, CRAB_Y); break;
                case 1: _canvas.drawString("v(o_o)v",  cx, CRAB_Y); break;
                case 2:
                    _canvas.drawString("v(o_O) ",  cx, CRAB_Y);
                    _canvas.drawString("V", cx + 6 * CRAB_CHAR_W, CRAB_Y - CRAB_CLAW_RISE_PX);
                    break;
                case 3: _canvas.drawString("v(o_o(|)", cx, CRAB_Y); break;
            }
            break;

        case Crab::State::PINCH_L:
            switch (_crab.pinchFrame) {
                case 0: _canvas.drawString("v(._.)v",   cx, CRAB_Y); break;
                case 1: _canvas.drawString("v(o_o)v",   cx, CRAB_Y); break;
                case 2:
                    _canvas.drawString(" (O_o)v",   cx, CRAB_Y);
                    _canvas.drawString("V", cx, CRAB_Y - CRAB_CLAW_RISE_PX);
                    break;
                case 3: _canvas.drawString("(|)(o_o)v", cx, CRAB_Y); break;
            }
            break;
    }

    // --- leg row ---
    const char* legs = (_crab.state == Crab::State::WALK)
                       ? kLegFrames[_crab.walkFrame]
                       : ",,,,";
    _canvas.drawString(legs, lx, ly);

    // --- sleep ZZZ column ---
    if (_crab.state == Crab::State::SLEEP) {
        float nowSec = millis() * 0.001f;
        int   zx     = cx + 3 * CRAB_CHAR_W;  // centre over body
        for (int i = 0; i < CRAB_SLEEP_Z_COUNT; i++) {
            int   zy    = CRAB_Y - CRAB_SLEEP_BASE_Y - i * CRAB_SLEEP_STEP_PX;
            float phase = i * CRAB_SLEEP_SWAY_PHASE;
            float sway  = sinf(nowSec * CRAB_SLEEP_SWAY_SPEED + phase) * CRAB_SLEEP_SWAY_AMP;
            char  c     = (i == _crab.sleepZFrame) ? 'Z' : 'z';
            _canvas.drawChar(c, zx + (int)sway, zy);
        }
    }
}
```

**Cute exit** (in `updateCrab()`):

```cpp
if (_crab.state == Crab::State::CUTE && now - _crab.stateEnteredMs >= _crab.cuteDurationMs) {
    _crab.state          = Crab::State::WALK;
    _crab.stateEnteredMs = now;
}
```

**Walk frame advance** (in `updateCrab()`):

```cpp
if (_crab.state == Crab::State::WALK && now - _crab.walkFrameMs >= CRAB_WALK_STEP_MS) {
    // advance in direction: right = +1 mod 4, left = -1 mod 4
    _crab.walkFrame = (_crab.walkFrame + (_crab.direction > 0 ? 1 : 3)) & 3;
    _crab.walkFrameMs = now;
}
```

**Sleep Z frame advance** (in `updateCrab()`):

```cpp
if (_crab.state == Crab::State::SLEEP && now - _crab.sleepZFrameMs >= CRAB_SLEEP_Z_MS) {
    _crab.sleepZFrame = (_crab.sleepZFrame + 1) % CRAB_SLEEP_Z_COUNT;  // sweeps 0→1→2→3→0
    _crab.sleepZFrameMs = now;
}
```

**Pinch frame advance** (in `updateCrab()`):

```cpp
if (_crab.state == Crab::State::PINCH_L || _crab.state == Crab::State::PINCH_R) {
    uint32_t elapsed = now - _crab.pinchFrameMs;
    if (_crab.pinchFrame < 3 && elapsed >= CRAB_PINCH_FRAME_MS) {
        _crab.pinchFrame++;
        _crab.pinchFrameMs = now;
    } else if (_crab.pinchFrame == 3 && elapsed >= CRAB_PINCH_HOLD_MS) {
        // proximity re-check: hit or miss?
        int hitIdx = findPinchTarget();  // returns fish pool index, or -1
        if (hitIdx >= 0) {
            _fishPool[hitIdx].active = false;  // remove fish
            _crab.state          = Crab::State::CUTE;
            _crab.cuteDurationMs = CRAB_CUTE_HIT_MS;
        } else {
            _crab.state          = Crab::State::WALK;
        }
        _crab.pinchFrame     = 0;
        _crab.stateEnteredMs = now;
    }
}
```

`findPinchTarget()` is a private helper that re-runs the proximity scan (same logic as the initial WALK→PINCH trigger) and returns the nearest fish index in range, or -1. Flakes are not removed on hit — they continue sinking.

Background + seaweed are already drawn before `drawCrab()`; transparent text background composites cleanly.

---

## 9. Integration into AquariumApp

### 9a. Private members

```cpp
Crab _crab;
```

### 9b. Seaweed root exposure

`drawSeaweed()` already computes root x-positions into a local or member array (`_seaweedBaseX[]`). `updateCrab()` needs read access to that same array. If `_seaweedBaseX` is already a private member (per `overview.md` §Seaweed Cache Note), pass a pointer or iterate via a getter. If not yet exposed, promote to a private member during this task.

### 9c. Call chain

| Hook | Called from | Call site order |
|---|---|---|
| `initCrab()` | `init()` | After `spreadInitialFishLayout()` |
| `updateCrab(dt)` | `tick()` | After `updateFlakes()`, so flake positions are current |
| `drawCrab()` | `renderFrame()` | After `drawSeaweed()`, before `drawBubbles()` — crab is on the sand, bubbles and fish pass in front |

### 9d. initCrab()

```cpp
void initCrab() {
    uint32_t now           = millis();
    _crab.x                = AQ_CANVAS_W * 0.5f;
    _crab.direction        = 1;
    _crab.state            = Crab::State::WALK;
    _crab.walkFrame        = 0;
    _crab.pinchFrame       = 0;
    _crab.sleepZFrame      = 0;
    _crab.cuteDurationMs   = CRAB_CUTE_IDLE_MS;
    _crab.stateEnteredMs   = now;
    _crab.walkFrameMs      = now;
    _crab.pinchFrameMs     = now;
    _crab.sleepZFrameMs    = now;
    _crab.lastTargetSeenMs = now;
}
```

---

## 10. Task Breakdown

| Step | Action | File |
|---|---|---|
| 1 | Add `Crab` struct and all `CRAB_*` constants to `aquariumApp.h` | `aquarium/aquariumApp.h` |
| 2 | Implement `initCrab()` | `aquarium/aquariumApp.h` |
| 3 | Implement `updateCrab(float dt)` — walk, edge-reverse, seaweed-avoid, proximity check, state transitions | `aquarium/aquariumApp.h` |
| 4 | Implement `drawCrab()` | `aquarium/aquariumApp.h` |
| 5 | Wire `initCrab()` into `init()` | `aquarium/aquariumApp.h` |
| 6 | Wire `updateCrab(dt)` into `tick()` after `updateFlakes()` | `aquarium/aquariumApp.h` |
| 7 | Wire `drawCrab()` into `renderFrame()` after `drawSeaweed()` | `aquarium/aquariumApp.h` |
| 8 | Build `cyd2usb_winamp` + `cyd2usb_winamp_debug`; run `check_build.sh` | — |
| 9 | Flash + DUT verify: crab visible at bottom, walks, pinches a flake on touch-spawn | device |

---

## 11. Open Questions

1. **Seaweed root access**: confirm `_seaweedBaseX[]` is already a private member (overview.md says it should be); if not, promote it during step 3.
2. **Draw order**: placing `drawCrab()` after `drawSeaweed()` but before `drawBubbles()` means bubbles pass in front — visually plausible. If this looks wrong on DUT, move `drawCrab()` to after all fish/bubbles.
3. **Sleep glyph**: `v(-.-)v` — symmetric, matching other emotes. ZZZ column drawn above head via `drawChar` loop; no overflow risk from a trailing character.
