# Design — Seaweed Procedural Optimisation (M-AQUARIUM-SEAWEED)

> Owner: Architect
> Status: draft
> Date: 2026-05-28

---

## 1. Problem Statement

`AquariumApp` caches three seaweed root arrays as private member fields:

```cpp
float _seaweedBaseX[AQ_SEAWEED_ROOTS];        // 48 B  .bss
float _seaweedAmp[AQ_SEAWEED_ROOTS];          // 48 B  .bss
float _seaweedHeightNoise[AQ_SEAWEED_ROOTS];  // 48 B  .bss
bool  _seaweedCached;                         //  1 B  .bss
```

Total: **145 bytes in `.bss`**, resident for the firmware lifetime.

All three arrays are pure deterministic functions of the root index `i` (0..11).
They contain no random numbers, no runtime input, no state. They do not change after
`init()`. Storing them is unnecessary — they can be computed inline or placed in flash.

Additionally, `_swayPoint()` is called once per segment per stalk (7 segments × 12 roots +
branches ≈ 120 calls per frame). Its argument expressions include a time-and-index-dependent
phase component that is identical for every segment of the same root in the same frame.
This component is currently recomputed inside `_swayPoint()` on every call.

---

## 2. The Seaweed Rendering Model

For context, each frame `drawSeaweed(t)` does:

```
for each root i (0..11):
    sw  = sin(t × freq_i × SWAY  +  i×0.7)  ×  amp_i     ← lateral lean this frame
    bh  = clamp(32 × SEAWEED_LEN × hv, 18, 72)            ← stalk height (constant)

    for seg 1..7:
        u  = seg / 7                                       ← 0=base → 1=tip
        (nx, ny) = _swayPoint(u, bx, y0, bh, sw, t, i)
        drawLine(prev → next, color)
        drawLine(prev+1 → next+1, darkgreen)               ← thickness pass

    _seaweedBranches(i, ...)                               ← 2–5 more drawLine calls
```

`_swayPoint` computes:

```
body   = sinf( t×(1.05+i×0.025)×SWAY  -  u×5.1  +  i×0.72 )
ripple = sinf( t×0.72×SWAY            +  u×9.0   +  i×1.31 )
bend   = sw × u × (0.20 + u×0.80)
travel = body × (1.5 + bh×0.055) × u²
detail = ripple × 1.2 × u
ox = bx + bend + travel + detail
oy = y0 - bh × u                       ← y is purely linear; only x sways
```

The y-coordinate is **dead straight** — it is proportional to `u` alone and never
deviates. Only x sways. This is important for future rendering improvements.

---

## 3. Change 1 — Drop `_seaweedBaseX` and `_seaweedAmp`; compute inline

Both arrays are trivially derived from `i`:

```cpp
// _seaweedBaseX[i]:
float bx = 10.0f + i * (AQ_CANVAS_W - 20.0f) / (AQ_SEAWEED_ROOTS - 1);

// _seaweedAmp[i]:
float amp = 5.0f + (i % 4) * 2.0f;
```

Replace the array lookups in `drawSeaweed()` with these two expressions.
Remove both member arrays and the `_seaweedCached` flag.

**Saves: 97 B from `.bss`**. No observable behaviour change.

---

## 4. Change 2 — `_seaweedHeightNoise` → `static const` (flash)

`heightNoise[i] = sinf(i × 2.173f + 0.61f)` for `i` in `0..11`.

`sinf` is not `constexpr` in C++14, so a `constexpr` array is not portable. However,
`static const float` initialised with a literal array is placed in `.rodata` by the
Xtensa-ESP32 toolchain — flash, not DRAM. Replace the member array with a file-scope
or class-scope `static const` table:

```cpp
// In aquariumApp.h, inside AquariumApp class:
static const float kHeightNoise[AQ_SEAWEED_ROOTS];
```

```cpp
// In a companion .cpp, or as an inline definition in the header:
// Values: sinf(i * 2.173f + 0.61f) for i = 0..11
// Verified at implementation time against the formula.
const float AquariumApp::kHeightNoise[AQ_SEAWEED_ROOTS] = {
     0.573f,  0.974f,  0.407f, -0.421f, -0.992f, -0.614f,
     0.160f,  0.769f,  0.990f,  0.464f, -0.309f, -0.946f,
};
```

> **Implementation note:** recompute these 12 values from the formula before committing;
> the values above are approximations for illustration only.

Reference inside `drawSeaweed()` replaces `_seaweedHeightNoise[i]` → `kHeightNoise[i]`.
Remove the member field.

**Saves: 48 B from `.bss`. Adds 48 B to `.rodata` (flash) — zero DRAM cost.**

---

## 5. Change 3 — Hoist per-root phase constants out of `_swayPoint`

`_swayPoint` is called up to ~120 times per frame. Its two `sinf` arguments each contain
a component that is constant for all segments of the same root in the same frame:

| Component | Constant per root-frame | Varies per segment |
|---|---|---|
| body arg | `t×(1.05+i×0.025)×SWAY + i×0.72` | `- u×5.1` |
| ripple arg | `t×0.72×SWAY + i×1.31` | `+ u×9.0` |

Currently `_swayPoint` receives `t` and `bi` and recomputes these from scratch each call.
Hoist the constant part into `drawSeaweed()`'s per-root loop:

```cpp
// Per-root, per-frame — computed once:
float phaseBody   = t * (1.05f + i*0.025f) * AQ_SWAY + i*0.72f;
float phaseRipple = t * 0.72f * AQ_SWAY + i*1.31f;

// Pass into _swayPoint instead of t + bi:
float body   = sinf(phaseBody   - u*5.1f);
float ripple = sinf(phaseRipple + u*9.0f);
```

Update `_swayPoint` signature to accept `phaseBody` and `phaseRipple` directly, removing
the `t` and `bi` parameters. Update `_seaweedBranches` similarly (it calls `_swayPoint`).

**Saves: ~10 float multiplications and additions per segment × ~120 calls/frame = ~1200
float ops/frame eliminated.** Not a material gain on the ESP32 FPU at 240 MHz, but it
makes the data flow explicit — the time-dependent and index-dependent parts are separated
from the per-segment traversal.

The `sinf` call count is **unchanged** (2 per segment call); the savings are purely in
argument construction arithmetic.

---

## 6. Summary

| Change | `.bss` delta | `.rodata` delta | CPU delta |
|---|---|---|---|
| Drop `_seaweedBaseX` + `_seaweedAmp` | −96 B | 0 | negligible |
| `_seaweedHeightNoise` → flash const | −48 B | +48 B | negligible |
| Drop `_seaweedCached` bool | −1 B | 0 | — |
| Hoist phase constants | 0 | 0 | −~1200 float ops/frame |
| **Total** | **−145 B DRAM** | **+48 B flash** | minor |

The seaweed itself is already the right architecture — fully procedural, no bitmaps, no
stored keyframes. These changes remove the unnecessary caching layer on top of what was
already a pure computation.

---

## 7. What is not changed

- The seaweed rendering algorithm is unchanged. All visual output is identical.
- The `sinf` call count per frame is unchanged (~240 calls across all roots, segments,
  and branches). If CPU pressure from `sinf` becomes a concern in future, a fast-sine
  approximation (e.g. 4-term minimax polynomial) is a separate improvement that would
  reduce per-call cost ~3–5× with no visual regression at this animation fidelity.
- The `drawLine` call count is unchanged.

---

## 8. Files affected

| File | Change |
|---|---|
| `app/src/aquarium/aquariumApp.h` | Remove 3 member arrays + `_seaweedCached`; add `static const kHeightNoise[]`; update `drawSeaweed()`, `_swayPoint()`, `_seaweedBranches()` |
| `app/src/aquarium/aquariumApp.h` (or companion `.cpp`) | Define `kHeightNoise` initialiser |

No other files are affected. No interface changes.

---

## 9. VE Acceptance Criteria

| # | Test | Method |
|---|---|---|
| 1 | Seaweed renders at correct positions on init | Visual, DUT |
| 2 | Seaweed sways continuously — no freeze or pop | Visual, 30 s observation |
| 3 | 12 stalks visible, heights vary as before | Visual |
| 4 | Branch frequency matches pre-change (2–5 per stalk) | Visual |
| 5 | Sprite resume after app-switch shows seaweed immediately | Switch away and back |
| 6 | check_build.sh passes | CI |
| 7 | `.bss` ≤ baseline − 140 B (map diff) | Map file comparison |
