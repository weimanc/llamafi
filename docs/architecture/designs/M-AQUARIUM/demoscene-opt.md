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
`_mirrorBracket()` to each character. Used in `drawFish()` when `f.vx < 0`.

### Change

Drop the array. In `drawFish()`, when the fish faces left, iterate the right-facing string
in reverse inline:

```cpp
// _glyphStr(f) already returns species right-string
// For left-facing, walk it backwards, applying _mirrorBracket()
const char* right = _species()[f.type].right;
uint8_t len = _glyphLen(f);    // already stored: _fishGlyphLenRight / Left
for (int c = len - 1; c >= 0; --c) {
    char gl = _mirrorBracket(right[c]);
    // draw gl at computed x offset (see Change 3)
}
```

`_mirrorBracket()` is a 10-case switch on a single character — essentially free on the
ESP32 FPU. Max glyph length is 10 characters.

`initFishMirrors()` is deleted entirely.

**`.bss` saving: 336 B.**

---

## 5. Change 3 — Glyph offsets: drop cumulative arrays, store per-char widths

### Current

```cpp
int16_t _fishGlyphOffsetRight[AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28×2 = 672 B
int16_t _fishGlyphOffsetLeft [AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28×2 = 672 B
```

These store the cumulative pixel x-offset of each character within its glyph string,
pre-computed from `_canvas.textWidth(prefix)` in `initFishGlyphMetrics()`. Used in
`drawFish()` to position each character.

### Why they are over-specified

The draw loop only needs `offsetRight[type][c]` to advance x by the width of character
`c`. The cumulative form `offset[c] = sum of widths[0..c-1]` is what the loop needs, but
it can be reconstructed at draw time by accumulating a running x offset:

```cpp
uint8_t _fishCharWidthRight[AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28×1 = 336 B  (per-char widths)
uint8_t _fishCharWidthLeft [AQ_GLYPH_COUNT][AQ_GLYPH_BUF];  // 12×28×1 = 336 B
```

In `drawFish()` replace:

```cpp
// Before:
int cx2 = int(f.x) + offsets[c];

// After:
xpos += _fishCharWidthRight[f.type][c];   // accumulate
int cx2 = int(f.x) + xpos;
```

`initFishGlyphMetrics()` now stores `_canvas.textWidth(singleChar)` per character
instead of `_canvas.textWidth(prefix)` per prefix. Same number of calls.

For left-facing fish (Change 2), the per-char width of the right string is used in
reverse order (since `_mirrorBracket` doesn't change character width).

**`.bss` saving: 1,008 B (1,344 → 336 B).**

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
`_seaweedCached` flag.

**`_seaweedHeightNoise`**: `sinf` of a compile-time argument series. `sinf` is not
`constexpr` in C++14, but a `static const float` array with a literal initialiser is
placed in `.rodata` (flash) by the Xtensa toolchain — zero DRAM cost:

```cpp
// Class scope, definition in aquariumApp.h:
static const float kHeightNoise[AQ_SEAWEED_ROOTS];
```

```cpp
// Values: sinf(i * 2.173f + 0.61f) for i = 0..11.
// Recompute from formula at implementation time; values below are illustrative.
const float AquariumApp::kHeightNoise[AQ_SEAWEED_ROOTS] = {
     0.573f,  0.974f,  0.407f, -0.421f, -0.992f, -0.614f,
     0.160f,  0.769f,  0.990f,  0.464f, -0.309f, -0.946f,
};
```

**`.bss` saving: 145 B. `.rodata` cost: 48 B (flash).**

---

## 7. Change 5 — Seaweed phase hoisting (CPU, no memory)

`_swayPoint(u, bx, y0, bh, sw, t, bi)` is called ~10 times per root per frame. Its
two `sinf` arguments contain a time-and-index-dependent component that is constant
across all segments of the same root in the same frame:

```
body   arg: t×(1.05+i×0.025)×SWAY + i×0.72   ← constant per root-frame
ripple arg: t×0.72×SWAY + i×1.31              ← constant per root-frame
```

Hoist these into `drawSeaweed()`'s per-root loop and pass them into `_swayPoint`:

```cpp
float phaseBody   = t * (1.05f + i*0.025f) * AQ_SWAY + i*0.72f;
float phaseRipple = t * 0.72f * AQ_SWAY + i*1.31f;
// _swayPoint now takes phaseBody, phaseRipple instead of t, bi
float body   = sinf(phaseBody   - u*5.1f);
float ripple = sinf(phaseRipple + u*9.0f);
```

`sinf` call count is **unchanged** (2 per segment; u varies per segment so the sinf
cannot be eliminated without a lookup table). Saves ~10 float multiply-adds per segment
× ~120 calls/frame = ~1,200 arithmetic ops/frame — negligible on the ESP32 FPU but
makes the data flow explicit and the function signature cleaner.

Update `_seaweedBranches` similarly (it also calls `_swayPoint`).

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

| Change | `.bss` delta | Notes |
|---|---|---|
| Gradient x-tile `[36][32]` | −17,496 B | Replaces heap migration from ADR-033 |
| Drop `_fishMirroredLeft` | −336 B | Mirror on the fly |
| Glyph offsets → per-char widths | −1,008 B | Accumulate at draw time |
| Seaweed arrays → inline | −97 B | Two-expression formulas |
| `_seaweedHeightNoise` → flash const | −48 B DRAM, +48 B flash | |
| `_seaweedCached` flag | −1 B | |
| Fish struct packing | −~192 B | Three fields narrowed |
| **Total DRAM** | **−19,178 B (~18.7 KB)** | |

Combined with M-AQUARIUM-OPT pool right-sizing (~2.7 KB), total `.bss` reduction is
approximately **21.4 KB** — returning the aquarium's `.bss` contribution from ~24 KB
to ~2.6 KB.

---

## 11. Files affected

| File | Changes |
|---|---|
| `app/src/aquarium/aquariumApp.h` | All member removals, replacements, and method updates described above |

No other files. No interface changes. No new FreeRTOS tasks or heap allocations.

---

## 12. VE Acceptance Criteria

| # | Test | Method |
|---|---|---|
| 1 | Gradient renders; colour transitions visible top-to-bottom | Visual, DUT |
| 2 | Seaweed sways continuously; 12 stalks; correct heights | Visual, 30 s |
| 3 | Fish swim in both directions; mirrored glyphs correct | Visual |
| 4 | Fish character spacing correct (no overlap, no gaps vs baseline) | Visual comparison |
| 5 | Aquarium survives suspend/resume (switch away and back) | Manual app-switch |
| 6 | `check_build.sh` passes | CI |
| 7 | `.bss` ≤ baseline − 18 KB (linker map diff) | Map comparison |
| 8 | [Optional] DUT dither quality check — if scanline-only variant chosen in Change 1, verify gradient looks acceptable vs tiled version | Visual A/B on DUT |
