# Design — AquariumApp Full-Height Canvas (M-AQUARIUM-FULLHEIGHT)

> Owner: Architect
> Status: approved
> Date: 2026-05-29

---

## Problem

After two fix attempts the aquarium still shows a blank band at the top. Two separate bugs
compound each other:

**Bug 1 — Hard cap at 193 px.**
`AQ_CANVAS_H = 193` is a compile-time ceiling. `_calcDynamicSize()` clamps `_canvasH` to
this value regardless of available heap. With the app space 240 px tall, 47 rows at the top
are always unavailable to the sprite.

**Bug 2 — Bottom-anchored push offset.**
`renderFrame()` calls `_canvas.pushSprite(0, 240 - _canvasH)`. With `_canvasH = 193` the
sprite starts at pixel row 47 — the top 47 rows are `fillRect`-blacked and the sprite sits
below them. Even if `AQ_CANVAS_H` were raised to 240, pushing at `240 - 240 = 0` would
accidentally correct this, but the logic is backwards: the sprite should always push at
`(0, 0)` and the canvas height should equal the full app height.

**Why the P1–P5 demoscene commits don't help by themselves.**
Those commits freed ~21 KB from `.bss` (static DRAM), which increases available heap on
ESP32 (shared DRAM pool). A 275×240 8-bpp sprite costs 66,000 bytes — now achievable.
But neither commit changed `AQ_CANVAS_H` or the push offset, so the blank top persists.

---

## Goal

A full-height aquarium that fills the entire 275×240 app space, with no dynamic shrinking
and no sand strip.

---

## Design

### Constants

| Constant | Old | New | Notes |
|---|---|---|---|
| `AQ_CANVAS_H` | `193` | `240` | Full app-space height |
| `AQ_SEA_LEVEL_Y` | `AQ_CANVAS_H - 36` | `AQ_CANVAS_H - 8` | 36 px was the sand strip; 8 px keeps fish 8 px from the canvas bottom so seaweed roots have room |
| `AQ_BACKGROUND_GRADIENT_H` | `AQ_CANVAS_H / 4 = 48` | `AQ_CANVAS_H / 4 = 60` | Derived automatically; `_gradTile[60][32]` = 3,840 B (was 2,304 B, +1,536 B — still << original 19,800 B) |

`AQ_CANVAS_W = 275` unchanged.

### Remove `_calcDynamicSize()`

The entire method is deleted. It served two purposes:
1. Dynamically size the sprite to available heap — no longer needed (240 px is the target;
   if heap is insufficient the existing retry loop shows the error screen).
2. Scale `_fishCount` proportionally — no longer needed; `_fishCount` is always `AQ_FISH_COUNT`.

Remove the call from `init()` and `resume()`. Remove the member `_fishCount` — replace every
use of `_fishCount` with the constant `AQ_FISH_COUNT`.

Remove the member `_seaLevelY` — replace every use with the constant `AQ_SEA_LEVEL_Y`.

### Sprite push — always `(0, 0)`

```cpp
// Before:
_canvas.pushSprite(0, 240 - _canvasH);

// After:
_canvas.pushSprite(0, 0);
```

### Remove `fillRect` black fills above/below sprite

In `init()` and `resume()`, delete:
```cpp
if (_canvasH < 240)
    tft.fillRect(0, 0, TASKBAR_X, 240 - _canvasH, TFT_BLACK);
```

In the retry success branch of `tick()`, delete:
```cpp
if (_canvasH < 240)
    tft.fillRect(0, _canvasH, TASKBAR_X, 240 - _canvasH, TFT_BLACK);
```

With a 240-px sprite at (0,0), these fills are dead code.

### Touch input — remove push offset

```cpp
// Before:
int spriteY = y - (240 - _canvasH);
if (spriteY >= 0 && spriteY < _canvasH)
    spawnFlake((float)x, (float)spriteY);

// After:
spawnFlake((float)x, (float)y);
```

The guard `spriteY >= 0 && spriteY < _canvasH` is also removed; `handleInput` is only
called when a touch hits the app area (guarded in `appShell`), so y is already in-range.

### Members removed

| Member | Was | Reason |
|---|---|---|
| `int _canvasH` | `= AQ_CANVAS_H` | Replaced by constant |
| `int _seaLevelY` | `= AQ_SEA_LEVEL_Y` | Replaced by constant |
| `int _fishCount` | `= AQ_FISH_COUNT` | Replaced by constant |

`_lastRetryMs` and `_retryShown` remain — the heap-fail error screen is still needed.

### Keep retry loop

The sprite allocation can still fail on first `init()` if SSL/TLS buffers are live.
The existing retry in `tick()` every 500 ms is correct — keep it unchanged (just remove
the `fillRect` inside the success branch as noted above).

---

## Memory impact

| Item | Delta |
|---|---|
| `_gradTile[60][32]` vs `[48][32]` | +1,536 B `.bss` |
| `_canvasH`, `_seaLevelY`, `_fishCount` members removed | −12 B `.bss` |
| Net `.bss` delta | **+1,524 B** |
| Sprite heap (275×240 vs 275×193) | +12,925 B heap at runtime |

Post-demoscene-opt `.bss` for AquariumApp is ~3 KB. After this change: ~4.5 KB. Still well
within budget. Heap requirement increases from ~53 KB to ~66 KB — covered by the ~21 KB
freed from `.bss` by P1–P5.

---

## Files affected

| File | Changes |
|---|---|
| `app/src/aquarium/aquariumApp.h` | All changes above — constants, removed method, push offset, fills, touch |

No other files.

---

## Implementation checklist

1. `AQ_CANVAS_H` → 240
2. `AQ_SEA_LEVEL_Y` → `AQ_CANVAS_H - 8`
3. Delete `_calcDynamicSize()` declaration and definition
4. Delete `_canvasH`, `_seaLevelY`, `_fishCount` members
5. Replace every `_canvasH` with `AQ_CANVAS_H`, every `_seaLevelY` with `AQ_SEA_LEVEL_Y`, every `_fishCount` with `AQ_FISH_COUNT`
6. `pushSprite(0, 240 - _canvasH)` → `pushSprite(0, 0)`
7. Delete `fillRect` black fills in `init()`, `resume()`, and the retry-success branch of `tick()`
8. Simplify `handleInput` touch Y as above

---

## VE Acceptance Criteria

| # | Test | Method |
|---|---|---|
| 1 | Aquarium fills full 275×240 — no black bands at top or bottom | Visual, DUT |
| 2 | Fish swim within visible bounds; none clipped at top or bottom | Visual, 30 s |
| 3 | Seaweed rooted at bottom row; stalks visible in full height | Visual |
| 4 | Gradient occupies top quarter (60 px) of canvas | Visual |
| 5 | Touch spawns flakes at correct Y position | Functional test |
| 6 | `check_build.sh` passes | CI |
| 7 | Sprite allocates on first or second attempt (check serial log) | Serial monitor |
| 8 | App-switch 10× — no crash, no allocation failure after first success | Manual |
