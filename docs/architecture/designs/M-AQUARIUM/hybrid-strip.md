# Design — AquariumApp Hybrid Strip Renderer (M-AQUARIUM-HYBRID)

> Owner: Architect
> Status: draft
> Date: 2026-05-29
> Supersedes: fullheight.md (which proposed a 275×240 single sprite — infeasible at runtime heap)

---

## Problem

A full-height 275×240 8bpp sprite costs 66,000 B heap. `maxAllocHeap` at steady-state is
~57,332 B — ~9 KB short. Simply top-anchoring a smaller sprite (e.g. 193px) leaves a
static dead zone at the bottom and constrains entity swim bounds.

---

## Approach

Split the display into two independently-rendered layers:

```
y:  0 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
         STRIP ZONE  (275 × 160 px)
         4 passes × 40 px strip buffer
         → gradient · fish · bubbles ·
           flakes · clock · octopus ·
           seahorse
y:160 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
         SEAWEED ZONE  (275 × 80 px)
         one persistent sprite
         → seaweed · rising bubbles
y:240 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
```

The strip buffer is re-used for all 4 passes; only one 11 KB allocation is live at render
time alongside the 22 KB seaweed sprite. Total heap: **33,000 B** — 24 KB below the
observed 57 KB limit.

---

## Constants

| Constant | Value | Notes |
|---|---|---|
| `AQ_CANVAS_W` | 275 | Unchanged |
| `AQ_STRIP_H` | 40 | Strip buffer height — one pass |
| `AQ_STRIP_COUNT` | 4 | 4 × 40 = 160 px strip zone |
| `AQ_SEAWEED_Y` | 160 | Display y where seaweed sprite begins (`AQ_STRIP_H × AQ_STRIP_COUNT`) |
| `AQ_SEAWEED_SPRITE_H` | 80 | Seaweed sprite height — fills y:160..239 |
| `AQ_CANVAS_H` | 240 | Total display height (informational; no single sprite this size) |
| `AQ_SEA_LEVEL_Y` | 152 | `AQ_SEAWEED_Y − 8` — fish/visitor ceiling, keeps entities in strip zone |
| `AQ_BACKGROUND_GRADIENT_H` | 40 | `AQ_STRIP_H × 1` — gradient fills strip 0 exactly |

`AQ_BACKGROUND_GRADIENT_H = 40` is a happy coincidence: the gradient (top quarter of the
water column = 160/4 = 40 px) exactly matches one strip. Strip 0 draws the gradient;
strips 1–3 draw black background + entities.

---

## Sprites

### Strip buffer `_canvas` (275 × 40)

Existing `TFT_eSprite _canvas{&tft}` resized to `AQ_CANVAS_W × AQ_STRIP_H`.
Re-used for all 4 passes. `createSprite(275, 40)` = **11,000 B** heap.

### Seaweed sprite `_seaweedCanvas` (275 × 80)

New `TFT_eSprite _seaweedCanvas{&tft}` member.
`createSprite(275, 80)` = **22,000 B** heap.

Readiness: both sprites must succeed. A single `_spriteReady` flag covers both — if either
`createSprite` returns `nullptr`, `_spriteReady = false` and the retry loop attempts both.
`deleteSprite()` called on both in `suspend()`.

---

## Coordinate system

### Strip zone

Each pass `s` covers display rows `[s × AQ_STRIP_H, (s+1) × AQ_STRIP_H)`.
Entity y-coordinates are transformed into strip-local space by subtracting `stripY = s × AQ_STRIP_H`.

TFT_eSPI clips drawing operations at sprite boundaries automatically — no explicit
per-entity culling is required for correctness. Soft culling (skip `drawChar` if
`cy_local < -16 || cy_local >= AQ_STRIP_H + 16`) is applied only to `drawFish` for
performance, since `drawChar` is called per character and fish can span many strips.

### Seaweed sprite

Seaweed sprite's local y=0 corresponds to display y=160.
Seaweed roots are at display `y0 = AQ_CANVAS_H − 2 = 238`, so in sprite-local space:
```
y0_local = 238 − AQ_SEAWEED_Y = 78
```
Seaweed extends upward by `bh` (max 72 px) → sprite-local top = `78 − 72 = 6`.
Branches extend a further ~10 px above tips → minimum local y ≈ −4, which clips
at the sprite top (y=0). Branch clipping at the seaweed/strip boundary is acceptable
and invisible in practice (seaweed tips rarely reach full height simultaneously).

Seaweed drawing uses `_seaweedCanvas` as target. All `drawLine` and `drawChar` calls
go to `_seaweedCanvas`; no y-offset arithmetic is needed in `drawSeaweed()` itself —
only `y0_local` replaces `_canvasH − 2`.

---

## Render loop

```cpp
void renderFrame() {
    float t = _timeSec();

    // ── Seaweed sprite (one pass) ──────────────────────────────────────────
    _seaweedCanvas.fillSprite(AQ_BG_COLOR);
    drawSeaweed(t);                     // uses _seaweedCanvas; y0_local = 78
    drawBubbles(_seaweedCanvas, AQ_SEAWEED_Y);   // bubbles below strip zone
    _seaweedCanvas.pushSprite(0, AQ_SEAWEED_Y);

    // ── Strip passes ───────────────────────────────────────────────────────
    for (int s = 0; s < AQ_STRIP_COUNT; ++s) {
        int sy = s * AQ_STRIP_H;
        _canvas.fillSprite(AQ_BG_COLOR);
        if (s == 0) drawBackground();   // gradient in strip 0 only
        if (s == 0) drawClock();
        drawBubbles(_canvas, sy);       // bubbles in this strip's y-range
        drawFlakes(sy);
        drawFish(sy);
        drawOctopus(sy);
        drawSeahorse(sy);
        _canvas.pushSprite(0, sy);
    }
}
```

`drawBackground()` and `drawClock()` run only on strip 0. All other draw calls run on
every strip pass; TFT_eSPI clips entities that fall outside the strip.

---

## Per-function changes

### `drawSeaweed(float t)`

Replace `_canvas` → `_seaweedCanvas` throughout.
Replace `int y0 = _canvasH − 2` → `int y0 = AQ_SEAWEED_Y_LOCAL` where:
```cpp
static constexpr int AQ_SEAWEED_Y_LOCAL = AQ_CANVAS_H - 2 - AQ_SEAWEED_Y;  // 78
```
No other changes needed — `drawLine` clips at seaweed sprite boundaries.

### `drawBubbles(TFT_eSprite& canvas, int zoneY)`

Signature changes: takes `canvas` reference and `zoneY` (the y-origin of that canvas in
display space). Each bubble's y in canvas-local space = `b.y − zoneY`.

Called twice per frame: once for the seaweed sprite (`canvas=_seaweedCanvas, zoneY=160`),
once per strip pass (`canvas=_canvas, zoneY=sy`). TFT_eSPI clips bubbles that fall
outside either canvas — bubbles appear in whichever zone they physically occupy, with a
seamless visual crossover at y=160.

### `drawFish(int stripY)`

Add `int stripY` parameter. Inside the per-character loop:
```cpp
int cy2_local = cy2 - stripY;
// Soft cull: skip if clearly outside strip
if (cy2_local < -(int)_canvas.fontHeight() || cy2_local >= AQ_STRIP_H) {
    // advance wave phasor anyway to keep body-wave phase correct
    float nw = wave*kCos + waveC*kSin;
    waveC = waveC*kCos - wave*kSin;
    wave = nw;
    xpos += int16_t(cw[rc]);
    continue;
}
_canvas.drawChar(uint16_t(gl), cx2, cy2_local);
```
x-coordinates are unchanged (no horizontal offset).

### `drawFlakes(int stripY)`, `drawOctopus(int stripY)`, `drawSeahorse(int stripY)`

Same pattern: subtract `stripY` from all y-coordinates before drawing. TFT_eSPI clips
anything outside `[0, AQ_STRIP_H)`.

### `drawBackground()`

No y-offset needed — strip 0 has `sy=0`, so display y = canvas y. Loop unchanged:
```cpp
int gradH = AQ_BACKGROUND_GRADIENT_H;  // = 40 = AQ_STRIP_H exactly
for (int y = 0; y < gradH; ++y) { ... }
```

### `drawClock()`

`AQ_CLOCK_Y = 4` is within strip 0 (y:0..39). No change needed.

### `_gradTile[AQ_BACKGROUND_GRADIENT_H][32]`

`AQ_BACKGROUND_GRADIENT_H` = 40 (was 60 at 240px, 48 at 193px). Size: 2,560 B.

### `init()` / `resume()` / `suspend()` / `tick()`

Create/delete both sprites. Both must succeed for `_spriteReady = true`.
`tft.setTextFont(2)` called on the sprite that draws fish — `_canvas`. The seaweed
sprite uses default font (font 1) for bubble glyphs, same as before.

Remove all `fillRect` TFT calls above/below sprites — no black-gap fills needed.
The seaweed sprite covers y:160..239; strips cover y:0..159. Together: full 240px. No gaps.

---

## Entity spawn bounds

| Entity | Current bound | New bound | Change |
|---|---|---|---|
| Fish y | `[14, AQ_SEA_LEVEL_Y − 6]` | `[14, 146]` | `AQ_SEA_LEVEL_Y = 152` |
| Octopus baseY | `[36, AQ_SEA_LEVEL_Y − 48]` | `[36, 104]` | Within strip zone ✓ |
| Seahorse baseY | `[34, AQ_SEA_LEVEL_Y − 56]` | `[34, 96]` | Within strip zone ✓ |
| Seaweed y0_local | `_canvasH − 2` | `78` | In seaweed sprite local coords ✓ |
| Bubbles baseX, y | Full height | Full height | Split across both sprites ✓ |
| Flakes | Spawn at touch, expire at `AQ_SEA_LEVEL_Y` | Same | Within strip zone ✓ |

---

## Memory

| Item | Size | vs. attempted 240px single sprite |
|---|---|---|
| `_gradTile[40][32]` `.bss` | 2,560 B | −1,280 B |
| `_canvas` heap (275×40) | 11,000 B | −55,000 B |
| `_seaweedCanvas` heap (275×80) | 22,000 B | +22,000 B |
| **Total heap** | **33,000 B** | **−33,000 B** |

33 KB is well within observed `maxAllocHeap = 57,332 B`. Leaves ~24 KB margin for SSL/TLS
buffer spikes.

---

## Tearing

Four sequential `pushSprite` calls with no vsync. On the ILI9341, refresh is ~60 Hz;
at ~15–20 fps rendering, a horizontal seam may be visible between strips if the display
refresh sweeps through mid-render.

Mitigations (in order of preference):
1. **Accept it.** Fish move at 14–30 px/s; the seam is ~1 px and drifts slowly. Likely
   invisible on a screensaver observed from normal distance.
2. **Push top-to-bottom** (already the natural order). The ILI9341 refreshes top-to-bottom;
   rendering in the same direction minimises visible overlap.
3. **Vsync wait** via `tft.readcommand8(ILI9341_RDMODE)` polling — complex, not worth it
   for a screensaver.

---

## Implementation order

| Step | Change | Notes |
|---|---|---|
| 1 | Constants: add `AQ_STRIP_H`, `AQ_STRIP_COUNT`, `AQ_SEAWEED_Y`, `AQ_SEAWEED_SPRITE_H`, `AQ_SEAWEED_Y_LOCAL`; update `AQ_SEA_LEVEL_Y`, `AQ_BACKGROUND_GRADIENT_H` | All derived; check gradient H = strip H |
| 2 | Add `_seaweedCanvas` member; update `init/resume/suspend/tick` to create/delete both | Verify both allocate in serial log |
| 3 | `renderFrame()` — add strip loop; seaweed sprite push | Wire up before adapting draw functions |
| 4 | `drawSeaweed()` — swap canvas, use `AQ_SEAWEED_Y_LOCAL` | Verify seaweed visible on DUT |
| 5 | `drawBubbles()` — add `(TFT_eSprite&, int zoneY)` signature; call from both contexts | Check seamless crossover at y=160 |
| 6 | `drawFish(stripY)`, `drawFlakes(stripY)`, `drawOctopus(stripY)`, `drawSeahorse(stripY)` — add stripY, offset y | Soft-cull fish chars for perf |
| 7 | `drawBackground()`, `drawClock()` — no change needed; called only on strip 0 | Confirm gradient H = 40 |

---

## Files affected

| File | Changes |
|---|---|
| `app/src/aquarium/aquariumApp.h` | All changes above — constants, new sprite member, render loop, draw function signatures |

No other files. No new FreeRTOS tasks.

---

## VE Acceptance Criteria

| # | Test | Method |
|---|---|---|
| 1 | Full 275×240 display covered — no black bands anywhere | Visual, DUT |
| 2 | Serial log: both sprite allocs succeed (`init sprite 275x40 OK`, `seaweed sprite 275x80 OK`) | Serial monitor |
| 3 | Fish swim in y:14..146; none enter seaweed zone | Visual, 60 s |
| 4 | Seaweed visible at bottom, sways; stalks rooted near y=238 | Visual |
| 5 | Bubbles rise continuously from seaweed zone through fish zone | Visual — confirm no discontinuity at y=160 |
| 6 | Gradient visible in top 40 px; transitions to black below | Visual |
| 7 | Clock visible top-centre | Visual |
| 8 | Octopus and seahorse appear, move through strip zone | Visual, wait ≥ 1 h or force-spawn |
| 9 | Touch spawns food flakes at correct position | Functional |
| 10 | `check_build.sh` passes | CI |
| 11 | App-switch 10× — no crash, both sprites reallocate correctly | Manual |
| 12 | Heap after alloc: `maxAllocHeap ≥ 20,000 B` (i.e., 24 KB margin preserved) | Serial log |
