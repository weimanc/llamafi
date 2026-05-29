# Design — AquariumApp Demoscene Optimisations (M-AQUARIUM-DEMOSCENE)

> Owner: Architect
> Status: draft
> Date: 2026-05-28
> Supersedes: seaweed-opt.md (absorbed), ADR-033 gradient heap migration (see §9)

---

## Guiding principle

> *Never store what you can compute. Cache only the minimum repeating unit.*

The aquarium's `.bss` footprint carries several arrays that were cached for convenience
but are either pure functions of a loop index, have a natural tiling period far smaller
than the stored region, or are reconstructible from data already stored elsewhere.
80s game programmers and the C64 demoscene eliminated these habitually — not because
they were clever, but because they had no choice. The techniques transfer directly.

---

## 1.5. Phase plan

Six changes are grouped into four implementation phases plus one pool right-sizing carry-over
from M-AQUARIUM-OPT. Each phase is independently compilable and verifiable.

| Phase | Changes | DRAM delta | Rationale for grouping |
|---|---|---|---|
| **P1 — Gradient tile** | Change 1 | −17,496 B | Largest single saving; zero fish/seaweed coupling; self-contained |
| **P2 — Seaweed** | Changes 4+5 | −145 B | Seaweed-only scope; no fish dependency |
| **P3 — Fish glyph subsystem** | Changes 2+3 | −1,380 B | Tightly coupled: dropping `_fishMirroredLeft` forces inline mirror in drawFish, which then dictates the per-char-width design |
| **P4 — Fish struct packing** | Change 6 | −~192 B | Type-only changes; independent of glyph subsystem |
| **P5 — Pool right-sizing** | M-AQUARIUM-OPT carry | −~2,336 B | Constant change only; no logic touch |

Recommended implementation order: P1 → P2 → P3 → P4 → P5.  
P2 and P3 may be swapped; P4 requires P3 (since P3 changes Fish-usage sites that P4
also touches). P5 is always last (trivially safe).

Context budget per phase: P3 is the largest (rewrites `drawFish`, `initFishGlyphMetrics`,
five helper methods, two member groups). Implement P3 alone in its own session.

---

## 2. Member inventory and target

Current `.bss` members addressed by this milestone:

| Member | Size | Nature |
|---|---|---|
| `_gradientBandCache[275×36]` | 19,800 B | Tiles every 32 px in x — over-cached |
| `_fishMirroredLeft[12][28]` | 336 B | Computable on the fly from existing right-string + `_mirrorBracket()` |
| `_fishGlyphOffsetRight[12][28]` | 672 B | Cumulative widths — only per-char widths needed |
| `_fishGlyphOffsetLeft[12][28]` | 672 B | Same |
| `_seaweedBaseX[12]` | 48 B | Pure formula of `i` |
| `_seaweedAmp[12]` | 48 B | Pure formula of `i` |
| `_seaweedHeightNoise[12]` | 48 B | Pure formula of `i` → flash const |
| `_seaweedCached` | 1 B | Flag for the above |
| **Total** | **21,625 B** | |

Fish struct packing addresses a further ~80–120 B across the pool.

---

## 3. Change 1 — Gradient: replace full cache with x-tile

### Why the full cache is over-sized

`_buildGradCache()` fills `_gradientBandCache[275 × gradH]` one pixel at a time. The
Bayer threshold function is:

```cpp
kB[((y/4)&7)*8 + ((x/4)&7)] << 2
```

The **x-component repeats with period 32** (`8 steps × scale 4`). For a fixed row `y`,
the dither threshold at column `x` equals the threshold at column `x + 32`. The gradient
base value `(y * 255) / (gradH - 1)` varies per row but not per column. Therefore, for
any row, the entire 275-pixel span is just the 32-pixel tile tiled 8.6 times.

### The tile

Replace the full cache with a per-row, 32-pixel-wide tile:

```cpp
// Before (member):
uint16_t _gradientBandCache[AQ_CANVAS_W * AQ_BACKGROUND_GRADIENT_H];  // 275×36×2 = 19,800 B

// After (member):
uint16_t _gradTile[AQ_BACKGROUND_GRADIENT_H][32];  // 36×32×2 = 2,304 B
```

`_buildGradCache()` is replaced by `_buildGradTile()` which fills only `[gradH][32]`
(1,152 pixel computations instead of 9,900 — 8.6× less work at build time too).

### Render

`drawBackground()` renders each row by tiling from the 32-pixel strip:

```cpp
void drawBackground() {
    _canvas.fillSprite(AQ_BG_COLOR);
    int gradH = _canvasH / 4;
    if (!_gradientBandCached) {
        _buildGradTile();
        _gradientBandCached = true;
    }
    uint16_t rowBuf[AQ_CANVAS_W];                      // 550 B on the stack, transient
    for (int y = 0; y < gradH; ++y) {
        for (int x = 0; x < AQ_CANVAS_W; ++x)
            rowBuf[x] = _gradTile[y][x & 31];          // x & 31 == x % 32
        _canvas.pushImage(0, y, AQ_CANVAS_W, 1, rowBuf);
    }
}
```

The `rowBuf[275]` is stack-allocated inside `drawBackground()` — 550 B live only during
the gradient render call, which happens once per frame. No persistent allocation.

**`.bss` saving: 17,496 B (19,800 → 2,304 B).**

This approach **eliminates the need for ADR-033's heap pointer migration** — 2,304 B is
acceptable as a static member. The fragmentation concerns, kMargin rework, and
alloc/free lifecycle from `memory-opt.md` §2 do not apply. See §9.

### Alternative: scanline colour, no dithering

If 2,304 B is still undesirable, or if the 8-bit sprite's palette quantisation already
smooths the gradient enough that Bayer dithering adds no visible value (worth checking on
DUT), the cache can be eliminated entirely:

```cpp
void drawBackground() {
    _canvas.fillSprite(AQ_BG_COLOR);
    int gradH = _canvasH / 4;
    for (int y = 0; y < gradH; ++y) {
        int base = (y * 255) / (gradH - 1);
        int r, g, b;
        _gradAtT(kBlue, kStops, 9, base, r, g, b);
        _canvas.drawFastHLine(0, y, AQ_CANVAS_W, _rgb888to565(r, g, b));
    }
}
```

**Zero stored bytes. 36 HLine calls per frame.** If dithering is visually irrelevant in
8-bit mode, this is the right choice. Evaluate on DUT before committing to the tile
approach.

---

## 4. Change 2 — Mirror fish on the fly; drop `_fishMirroredLeft`

### Current

```cpp
char _fishMirroredLeft[AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28 = 336 B
```

Built in `initFishMirrors()` by iterating the right-facing string in reverse and applying
`_mirrorBracket()` to each character. Used in `drawFish()` when `f.vx < 0` via `_glyphStr()`.

### Change

Drop the array. In `drawFish()`, when the fish faces left, iterate the right-facing string
in reverse inline (see §5.3 for the complete draw loop). `_mirrorBracket()` is a 10-case
switch on a single character — free on the ESP32 FPU. Max glyph length is 10 characters.

`initFishMirrors()` is deleted entirely.

### Members also dropped in this phase

These members exist only to service the left-mirror path and become dead code once
`_fishMirroredLeft` is gone:

```cpp
// Dropped in P3:
char    _fishMirroredLeft[AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 336 B
uint8_t _fishGlyphLenLeft[AQ_GLYPH_COUNT];                 //  12 B
int16_t _fishGlyphWidthLeft[AQ_GLYPH_COUNT];               //  24 B
```

`_fishGlyphLenLeft[i]` equals `_fishGlyphLenRight[i]` always (mirror doesn't change
string length). `_fishGlyphWidthLeft[i]` equals `_fishGlyphWidthRight[i]` because
`_mirrorBracket` swaps bracket pairs — in TFT Font 2 each bracket/angle pair has equal
pixel width (assumption: symmetric glyphs; verify on DUT if any fish species produces
misaligned left-facing tail).

`_activateFish` currently uses both widths:
```cpp
// Before:
int rw = _fishGlyphWidthRight[f.type], lw = _fishGlyphWidthLeft[f.type];
f.visualWidth = (rw > lw) ? rw : lw;

// After:
f.visualWidth = _fishGlyphWidthRight[f.type];
```

### Helper methods dropped

```cpp
// All three deleted — logic inlined into drawFish() (see §5.3):
const char*    _glyphStr(const Fish& f) const;      // returned _fishMirroredLeft
const int16_t* _glyphOffsets(const Fish& f) const;  // returned _fishGlyphOffsetLeft/Right
uint8_t        _glyphLen(const Fish& f) const;       // returned _fishGlyphLenLeft/Right
```

`_glyphVisW` retains its fallback `strlen(_species()[f.type].right) * 12` — uses only
the right string. No change needed.

**`.bss` saving: 336 B (array) + 12 B + 24 B (length/width members) = 372 B.**

---

## 5. Change 3 — Glyph offsets: drop cumulative arrays, store per-char widths

### Current

```cpp
int16_t _fishGlyphOffsetRight[AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28×2 = 672 B
int16_t _fishGlyphOffsetLeft [AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28×2 = 672 B
```

Built in `initFishGlyphMetrics()` via `_cacheGlyphMetrics()`. Used in `drawFish()` as
`offsets[c]` — the cumulative x-pixel position of character `c` from the fish origin.

### Why they are over-specified

`offset[c] = sum(width[0..c-1])`. The draw loop uses it as:
```cpp
int cx2 = int(f.x) + offsets[c];
```
which is just a running x accumulation. Storing the cumulative form is unnecessary;
the loop can maintain `xpos` directly from per-char widths.

### New member (one array, not two)

With Change 2 dropping `_fishMirroredLeft`, there is no separate left-string whose
per-char widths might differ from the right string. The left draw path iterates the
right string in reverse, so it reuses `_fishCharWidthRight` in reverse index order.
Only one width array is needed.

```cpp
// Replaces both _fishGlyphOffsetRight and _fishGlyphOffsetLeft:
uint8_t _fishCharWidthRight[AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28×1 = 336 B
```

`uint8_t` is sufficient: TFT Font 2 per-character pixel widths are 6–14 px, well within 0–255.

### 5.1 New `initFishGlyphMetrics()`

`_cacheGlyphMetrics()` is deleted. The new function computes per-char widths directly:

```cpp
void initFishGlyphMetrics() {
    const FishSpecies* sp = _species();
    for (int i = 0; i < AQ_GLYPH_COUNT; ++i) {
        const char* right = sp[i].right;
        size_t n = strlen(right);
        if (n >= AQ_GLYPH_BUF) n = AQ_GLYPH_BUF - 1;
        _fishGlyphLenRight[i] = uint8_t(n);
        int16_t totalW = 0;
        for (size_t c = 0; c < n; ++c) {
            char tmp[2] = {right[c], '\0'};
            uint8_t w = uint8_t(_canvas.textWidth(tmp));
            _fishCharWidthRight[i][c] = w;
            totalW += w;
        }
        _fishGlyphWidthRight[i] = totalW;
    }
}
```

Same number of `textWidth` calls as before (`n` per species, one per character).

### 5.2 `_cacheGlyphMetrics()` deleted

No longer needed. `initFishMirrors()` is also gone (Change 2). Init sequence in `init()`
becomes:

```cpp
// Before: initFishMirrors(); initFishGlyphMetrics();
// After:
initFishGlyphMetrics();
```

### 5.3 New `drawFish()` inner loop (P3 combined result)

This is the complete replacement for the per-fish draw block. It inlines both the mirror
logic (Change 2) and the running-x accumulation (Change 3):

```cpp
void drawFish() {
    _canvas.setTextFont(2);
    _canvas.setTextSize(1);
    _canvas.setTextDatum(TL_DATUM);
    const float t = _timeSec();
    const float waveBase = t * FISH_SWIM_WAVE_SPEED;
    static const float kSin = sinf(FISH_SWIM_WAVE_SPACING);
    static const float kCos = cosf(FISH_SWIM_WAVE_SPACING);
    for (int i = 0; i < _fishCount; ++i) {
        Fish& f = _fishPool[i];
        if (!f.active) continue;
        const char*    right = _species()[f.type].right;
        const uint8_t* cw    = _fishCharWidthRight[f.type];
        uint8_t        len   = _fishGlyphLenRight[f.type];
        bool           goRight = (f.vx >= 0.0f);
        float angle  = waveBase + f.phase;
        float wave   = sinf(angle);
        float waveC  = cosf(angle);
        _canvas.setTextColor(f.renderColor);
        int16_t xpos = 0;
        for (uint8_t c = 0; c < len; ++c) {
            uint8_t rc  = goRight ? c : uint8_t(len - 1 - c);   // index into right[]
            char    gl  = goRight ? right[rc] : _mirrorBracket(right[rc]);
            if (gl != ' ') {
                float yo  = wave * FISH_SWIM_WAVE_AMPLITUDE;
                int   cx2 = int(f.x) + xpos;
                int   cy2 = int(f.y) + int(yo + (yo >= 0.0f ? 0.5f : -0.5f));
                _canvas.drawChar(uint16_t(gl), cx2, cy2);
            }
            xpos += int16_t(cw[rc]);
            float nw = wave*kCos + waveC*kSin;
            waveC = waveC*kCos - wave*kSin;
            wave = nw;
        }
    }
}
```

Key invariants preserved:
- Wave phasor (`wave`, `waveC`) advances once per character regardless of direction,
  so body-wave animation cadence is unchanged.
- For right-facing fish: `rc = c`, `gl = right[c]`, `xpos` accumulates left-to-right —
  identical output to before.
- For left-facing fish: `rc = len-1-c` iterates right string in reverse; `_mirrorBracket`
  flips brackets; `xpos` accumulates using `cw[rc]` (width of the character being drawn).
  Total x-span equals `_fishGlyphWidthRight[f.type]` (sum of all char widths), same as
  the old left path.

**`.bss` saving (Change 3 only): 1,008 B (1,344 offset arrays removed, 336 width array added).**
Combined P3 (Changes 2+3): 372 B (§4) + 1,008 B (§5) = **1,380 B total**.

---

## 6. Change 4 — Seaweed root data: inline + flash const

All three seaweed root arrays are pure, deterministic functions of the root index `i`:

```cpp
_seaweedBaseX[i]       = 10.0f + i * (AQ_CANVAS_W - 20.0f) / (AQ_SEAWEED_ROOTS - 1)
_seaweedAmp[i]         = 5.0f + (i % 4) * 2.0f
_seaweedHeightNoise[i] = sinf(i * 2.173f + 0.61f)
```

**`_seaweedBaseX` and `_seaweedAmp`**: two-expression formulas of `i`. Replace array
lookups in `drawSeaweed()` with the inline formulas. Remove both member arrays and the
`_seaweedCached` flag. Remove the `init()` reset of `_seaweedCached`.

**`_seaweedHeightNoise`**: `sinf` of a compile-time argument series. `sinf` is not
`constexpr` in C++14, but a `static const float` array with a literal initialiser is
placed in `.rodata` (flash) by the Xtensa toolchain — zero DRAM cost:

```cpp
// Class scope (inside AquariumApp, before members):
static const float kHeightNoise[AQ_SEAWEED_ROOTS];
```

### 6.1 kHeightNoise exact values

Compute with:
```python
import math
vals = [math.sin(i * 2.173 + 0.61) for i in range(12)]
print(", ".join(f"{v:.4f}f" for v in vals))
```

Expected output (verify before committing):
```
0.5729f, 0.3508f, -0.9686f, 0.7399f, 0.9014f, -0.8814f,
-0.1423f, 0.7763f, 0.9877f, 0.4695f, -0.3000f, -0.9530f
```

Definition in `.cpp` body (or at end of `aquariumApp.h` after the class closing `}`):
```cpp
const float AquariumApp::kHeightNoise[AquariumApp::AQ_SEAWEED_ROOTS] = {
     0.5729f,  0.3508f, -0.9686f,  0.7399f,  0.9014f, -0.8814f,
    -0.1423f,  0.7763f,  0.9877f,  0.4695f, -0.3000f, -0.9530f,
};
```

Since `aquariumApp.h` is a single-header class, the definition goes **after** the class
closing brace, still inside the header guard, not in a `.cpp`. Same pattern as any other
`static const` float array defined in a header.

### 6.2 New `drawSeaweed()` opening (P2 change)

```cpp
void drawSeaweed(float t) {
    // _seaweedCached, _seaweedBaseX, _seaweedAmp, _seaweedHeightNoise all gone
    for (int i = 0; i < AQ_SEAWEED_ROOTS; ++i) {
        float bx = 10.0f + i * (AQ_CANVAS_W - 20.0f) / float(AQ_SEAWEED_ROOTS - 1);
        float amp = 5.0f + (i % 4) * 2.0f;
        float sw  = sinf(t*(0.8f+0.09f*i)*AQ_SWAY + i*0.7f) * amp;
        float hv  = 1.0f + AQ_SEAWEED_RAND * kHeightNoise[i];
        // ... rest unchanged
    }
}
```

`bx` and `amp` are two adds/multiplies per root — negligible vs the `sinf` calls already
in the loop.

**`.bss` saving: 145 B (48+48+48+1). `.rodata` cost: 48 B (flash).**

---

## 7. Change 5 — Seaweed phase hoisting (CPU, no memory)

`_swayPoint(u, bx, y0, bh, sw, t, bi)` is called ~10 times per root per frame (7 spine
segments + branches). Its two `sinf` arguments contain a time-and-index-dependent
component that is constant across all segments of the same root in the same frame:

```
body   arg: t×(1.05+bi×0.025)×SWAY − u×5.1 + bi×0.72   ← (t,bi) part constant per root-frame
ripple arg: t×0.72×SWAY + u×9.0 + bi×1.31               ← (t,bi) part constant per root-frame
```

### 7.1 New signature

```cpp
// Before:
void _swayPoint(float u, float bx, int y0, float bh, float sw,
                float t, int bi, float& ox, float& oy);

// After:
void _swayPoint(float u, float bx, int y0, float bh, float sw,
                float phaseBody, float phaseRipple, float& ox, float& oy);
```

### 7.2 New `_swayPoint` body

```cpp
void _swayPoint(float u, float bx, int y0, float bh, float sw,
                float phaseBody, float phaseRipple, float& ox, float& oy) {
    u = _clamp(u, 0.0f, 1.0f);
    float body   = sinf(phaseBody   - u*5.1f);
    float ripple = sinf(phaseRipple + u*9.0f);
    float bend   = sw * u * (0.20f + u*0.80f);
    float travel = body * (1.5f + bh*0.055f) * u * u;
    float detail = ripple * 1.2f * u;
    ox = bx + bend + travel + detail;
    oy = y0 - bh * u;
}
```

### 7.3 Hoisting in `drawSeaweed()` (combined with Change 4 result)

```cpp
for (int i = 0; i < AQ_SEAWEED_ROOTS; ++i) {
    float bx  = 10.0f + i * (AQ_CANVAS_W - 20.0f) / float(AQ_SEAWEED_ROOTS - 1);
    float amp = 5.0f + (i % 4) * 2.0f;
    float sw  = sinf(t*(0.8f+0.09f*i)*AQ_SWAY + i*0.7f) * amp;
    float hv  = 1.0f + AQ_SEAWEED_RAND * kHeightNoise[i];
    float bh  = _clamp(32.0f * AQ_SEAWEED_LEN * hv, 18.0f, 72.0f);
    int   y0  = _canvasH - 2;

    float phaseBody   = t * (1.05f + i*0.025f) * AQ_SWAY + i*0.72f;   // hoisted
    float phaseRipple = t * 0.72f * AQ_SWAY + i*1.31f;                 // hoisted

    float px = bx, py = float(y0);
    for (int seg = 1; seg <= 7; ++seg) {
        float u = float(seg) / 7;
        float nx, ny;
        _swayPoint(u, bx, y0, bh, sw, phaseBody, phaseRipple, nx, ny);
        // ... color/draw lines unchanged
    }
    _seaweedBranches(i, bh, sw, phaseBody, phaseRipple, bx, y0);  // pass phases, not t+bi
}
```

### 7.4 Updated `_seaweedBranches` signature

```cpp
// Before:
void _seaweedBranches(int bi, float bh, float sw, float t, float bx, int y0);

// After:
void _seaweedBranches(int bi, float bh, float sw,
                      float phaseBody, float phaseRipple, float bx, int y0);
```

Inside `_seaweedBranches`, the one `_swayPoint` call passes `phaseBody, phaseRipple`
directly. The `bwig` sinf still uses `t` and `bi` — keep local `t` parameter or
recompute: since `_seaweedBranches` no longer receives `t`, the `bwig` line must be
updated too:

```cpp
// bwig uses: t*(1.1f+bi*0.03f)*AQ_SWAY + bi + b*1.7f
// = (phaseBody - bi*0.72f) / (1.05f+bi*0.025f) ... complex to reconstruct
// Simplest: add float t parameter back just for bwig, or accept a slight approximation.
```

**Recommendation:** keep `float t` as a parameter to `_seaweedBranches` for the `bwig`
calculation only. The signature becomes:

```cpp
void _seaweedBranches(int bi, float bh, float sw,
                      float phaseBody, float phaseRipple,
                      float t, float bx, int y0);
```

This is the cleanest split: hoisted phases for the two `_swayPoint` calls, raw `t` for
the one `bwig` term that is not worth further refactoring.

`sinf` call count is **unchanged** (2 per segment; `u` varies per segment so the sinf
cannot be eliminated without a LUT). Saves ~40 float multiply-adds per root-frame
(10 calls × 4 MACs avoided per call). Negligible on ESP32 FPU but makes data flow explicit.

**`.bss` saving: 0. CPU saving: ~40 MACs/root/frame (cosmetic).**

---

## 8. Change 6 — Fish struct field packing

```cpp
struct Fish {
    bool     active;          // 1 B
    int      type;            // 4 B  ← waste: range 0..11
    float    x, y;            // 8 B
    float    vx, vy;          // 8 B
    float    speed;           // 4 B  ← waste: range 14..30
    float    phase;           // 4 B
    float    wanderBias;      // 4 B  ← waste: range 0.4..1.3
    int      visualWidth;     // 4 B  ← waste: range ~30..90 px
    uint16_t displayColor;    // 2 B
    uint16_t renderColor;     // 2 B
    float    depthBrightness; // 4 B
};   // ~48 B with alignment
```

Practical packing — fields where the type is clearly wrong, no physics refactor needed:

| Field | Current | Packed | Saving/fish |
|---|---|---|---|
| `type` | `int` | `uint8_t` | ~3 B |
| `speed` | `float` (14..30) | `uint8_t` (integer speed) | ~3 B |
| `visualWidth` | `int` (30..90) | `uint8_t` | ~3 B |

`x`, `y`, `vx`, `vy`, `phase`, `wanderBias`, `depthBrightness` are all used directly
in floating-point physics math every frame. Converting them to fixed-point would require
pervasive changes to `updateFish()` for modest savings. Not recommended here.

Grouping the three `uint8_t` fields together avoids alignment padding waste:

```cpp
struct Fish {
    float    x, y, vx, vy, phase, wanderBias, depthBrightness;  // 28 B
    uint16_t displayColor, renderColor;                           //  4 B
    uint8_t  speed;                                               //  1 B
    uint8_t  type;                                                //  1 B
    uint8_t  visualWidth;                                         //  1 B
    bool     active;                                              //  1 B
};  // 36 B — was ~48 B
```

**`.bss` saving: ~12 B × 16 fish = ~192 B.**

---

## 8.5. Phase 5 — Pool right-sizing (carry from M-AQUARIUM-OPT)

Absorbed here so a Developer can implement the full milestone in one place.

### Current constants

```cpp
static constexpr int AQ_FISH_POOL_MAX   = 48;   // allocates 48 Fish; only 16 used
static constexpr int AQ_BUBBLE_POOL_MAX = 50;   // allocates 50 Bubbles; only 10 used
```

### Change

```cpp
static constexpr int AQ_FISH_POOL_MAX   = 16;   // == AQ_FISH_COUNT
static constexpr int AQ_BUBBLE_POOL_MAX = 10;   // == AQ_BUBBLE_COUNT
```

No logic changes. `applyFishPopulation()` and `applyBubblePopulation()` iterate up to
`AQ_FISH_POOL_MAX` / `AQ_BUBBLE_POOL_MAX`; after the constant change they iterate the
exact live count.

`spreadInitialFishLayout()` iterates `_fishCount` (not pool max) — unaffected.

**`.bss` saving:** `Fish` struct is ~48 B currently (36 B after P4); `Bubble` is ~20 B.
- Fish: 32 dead slots × 48 B = ~1,536 B (1,152 B after P4 precedes this)
- Bubbles: 40 dead slots × 20 B = ~800 B
- **Total: ~2,336 B (or ~1,952 B if P4 runs first)**

### Ordering constraint

P5 can run before or after P4. Running P4 first produces a slightly smaller savings
figure for the fish array (36 B × 16 = 576 B vs 48 B × 16 = 768 B — either way correct,
just different numbers in the final linker map). Recommended: P4 → P5.

---

## 9. Relationship to M-AQUARIUM-OPT and ADR-033

`M-AQUARIUM-OPT` addressed the gradient cache via **heap pointer migration** (ADR-033):
move `_gradientBandCache[19,800 B]` from `.bss` to a `new`/`delete[]` heap pointer,
freeing it on suspend.

Change 1 of this milestone **supersedes that approach**. With the x-tile, the gradient
cache shrinks to **2,304 B** — acceptable as a permanent `.bss` member. The heap
pointer, fragmentation concerns, `kMargin` rework, and alloc/free lifecycle from
`memory-opt.md` are unnecessary.

**`M-AQUARIUM-OPT` scope after this milestone ships:**
- Gradient cache section: superseded — close it, `_gradientBandCache` member replaced
  by `_gradTile`, no heap migration needed.
- Pool right-sizing (`_fishPool[48→16]`, `_bubbles[50→10]`): independent — still valid,
  still ~2.7 KB recovered. Keep as-is.
- **ADR-033** should be updated to `Status: superseded` once M-AQUARIUM-DEMOSCENE is
  accepted. The tile approach makes heap migration unnecessary.

---

## 10. Summary

| Phase | Change | `.bss` delta | Notes |
|---|---|---|---|
| P1 | Gradient x-tile `[36][32]` | −17,496 B | Replaces heap migration from ADR-033 |
| P2 | Seaweed arrays → inline | −97 B | `_seaweedBaseX`, `_seaweedAmp`, `_seaweedCached` |
| P2 | `_seaweedHeightNoise` → flash const | −48 B DRAM, +48 B flash | `.rodata` cost |
| P2 | Phase hoisting in `_swayPoint` | 0 | CPU only |
| P3 | Drop `_fishMirroredLeft` + `_glyphLenLeft` + `_glyphWidthLeft` | −372 B | Mirror on the fly |
| P3 | Glyph offsets → per-char widths | −1,008 B | One array instead of two, half element size |
| P4 | Fish struct packing | −~192 B | Three fields narrowed (`type`, `speed`, `visualWidth`) |
| P5 | Pool right-sizing | −~2,336 B | `AQ_FISH_POOL_MAX 48→16`, `AQ_BUBBLE_POOL_MAX 50→10` |
| **Total DRAM** | | **−21,549 B (~21.0 KB)** | |

Starting `.bss` contribution from `AquariumApp`: ~24 KB. After all phases: ~3 KB.

### 10.1 Changed members — before/after

**Removed (P1):**
- `uint16_t _gradientBandCache[275 × 36]` — 19,800 B

**Added (P1):**
- `uint16_t _gradTile[AQ_BACKGROUND_GRADIENT_H][32]` — 2,304 B

**Removed (P2):**
- `float _seaweedBaseX[12]`, `float _seaweedAmp[12]`, `float _seaweedHeightNoise[12]`, `bool _seaweedCached`

**Added (P2):**
- `static const float kHeightNoise[12]` (`.rodata`, flash)

**Removed (P3):**
- `char _fishMirroredLeft[12][28]` — 336 B
- `uint8_t _fishGlyphLenLeft[12]` — 12 B
- `int16_t _fishGlyphWidthLeft[12]` — 24 B
- `int16_t _fishGlyphOffsetRight[12][28]` — 672 B
- `int16_t _fishGlyphOffsetLeft[12][28]` — 672 B

**Added (P3):**
- `uint8_t _fishCharWidthRight[12][28]` — 336 B

**Removed (P3, helper methods):**
- `initFishMirrors()`, `_cacheGlyphMetrics()`, `_glyphStr()`, `_glyphOffsets()`, `_glyphLen()`

**Changed (P4):**
- `Fish::type: int → uint8_t`
- `Fish::speed: float → uint8_t`
- `Fish::visualWidth: int → uint8_t`

**Changed (P5):**
- `AQ_FISH_POOL_MAX: 48 → 16`
- `AQ_BUBBLE_POOL_MAX: 50 → 10`

---

## 11. Files affected

| File | Changes |
|---|---|
| `app/src/aquarium/aquariumApp.h` | All member removals, replacements, and method updates described above |

No other files. No interface changes. No new FreeRTOS tasks or heap allocations.

---

## 12. VE Acceptance Criteria

Criteria are tagged by phase. Run phase-gated subset after each phase lands.

| # | Phase | Test | Method |
|---|---|---|---|
| 1 | P1 | Gradient renders; colour transitions visible top-to-bottom | Visual, DUT |
| 2 | P1 | Gradient re-renders correctly after suspend/resume | Manual app-switch |
| 3 | P1 | `check_build.sh` passes | CI |
| 4 | P1 | `.bss` ≤ baseline − 17 KB (linker map diff) | Map comparison |
| 5 | P1 | [Optional] Dither quality A/B — if scanline-only variant chosen, verify gradient looks acceptable vs tiled | Visual A/B on DUT |
| 6 | P2 | Seaweed sways continuously; 12 stalks visible; heights vary plausibly | Visual, 30 s |
| 7 | P2 | `kHeightNoise` values match `python3 -c "import math; print([round(math.sin(i*2.173+0.61),4) for i in range(12)])"` | Code review |
| 8 | P3 | Fish swim in both directions; left-facing glyphs are mirror images of right-facing | Visual |
| 9 | P3 | Fish character spacing correct — no overlap, no gaps vs pre-P3 baseline screenshot | Visual comparison |
| 10 | P3 | All 12 fish species render correctly in both directions | Visual, cycle species |
| 11 | P3 | `check_build.sh` passes | CI |
| 12 | P4 | Fish struct fields hold correct values after packing (speed 14–30, type 0–11, visualWidth 30–90 — no truncation) | Serial log / assert |
| 13 | P5 | Pool arrays sized correctly in linker map (`_fishPool`: 16 × Fish, `_bubbles`: 10 × Bubble) | Map comparison |
| 14 | All | Aquarium survives 10 app-switch cycles without crash or sprite allocation failure | Manual app-switch |
| 15 | All | `.bss` ≤ baseline − 20 KB (final linker map diff) | Map comparison |
