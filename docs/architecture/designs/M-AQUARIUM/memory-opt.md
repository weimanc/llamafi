# Design — Aquarium Memory Optimisation (M-AQUARIUM-OPT)

> Owner: Architect
> Status: draft — gradient cache section superseded (see note below)
> Date: 2026-05-28
> ADR: [ADR-033](../../decisions/ADR-033.md) — gradient cache heap migration (pending supersession)

> **Note:** The gradient cache section (Change 1) of this doc has been superseded by
> [M-AQUARIUM-DEMOSCENE / demoscene-opt.md](demoscene-opt.md) Change 1, which reduces
> `_gradientBandCache` from 19,800 B to a 2,304 B x-tile static member — making heap
> migration unnecessary. ADR-033 status is pending update to `superseded`.
> **Remaining scope of this milestone:** pool right-sizing only (Change 2 below).

---

## 1. Problem Statement

RAM audit (2026-05-28) identified `AquariumApp` as the largest single consumer of static DRAM
outside of system libraries. Two distinct issues:

| Issue | Location | Size | Impact |
|---|---|---|---|
| `_gradientBandCache[275×36]` member array | `.bss` (always resident) | 19.3 KB | Persists even while app is suspended; blocks that 19 KB from being usable by TLS or other heap allocations indefinitely |
| `_fishPool[48]` oversized vs `AQ_FISH_COUNT=16` | `.bss` | ~1.5 KB | 32 idle slots never used |
| `_bubbles[50]` oversized vs `AQ_BUBBLE_COUNT=10` | `.bss` | ~1.1 KB | 40 idle slots never used |

**Total recoverable static RAM: ~22 KB**

The `_gradientBandCache` issue was anticipated in `overview.md` Open Question #2
("if heap pressure causes linker complaints, move to `heap_caps_malloc`"). This milestone
resolves it proactively based on measured data rather than waiting for a linker error.

### Context: ESP32 heap budget

From the linker map (`cyd2usb_winamp/firmware.map`):

```
.dram0.data   26.1 KB   (initialised globals)
.dram0.bss    73.1 KB   (zero-init globals)
─────────────────────────
Total static  99.2 KB
```

Persistent heap consumers: task stacks ~28 KB (ours) + ~50 KB (system). Ephemeral peaks:
mbedTLS handshake ~40 KB per task. With 320 KB total DRAM and ~170 KB reaching the heap,
margin is tight when Aquarium is active and a TLS operation fires simultaneously.

---

## 2. Change 1 — Gradient Cache Heap Migration

### Current

```cpp
// aquariumApp.h (member declaration)
uint16_t _gradientBandCache[AQ_CANVAS_W * AQ_BACKGROUND_GRADIENT_H];  // 275×36×2 = 19,800 B in .bss
bool     _gradientBandCached = false;
```

### Target

```cpp
// aquariumApp.h (member declaration)
uint16_t* _gradientBandCache     = nullptr;   // heap pointer; nullptr = not allocated
bool      _gradientBandCached    = false;
```

#### Lifecycle

| Event | Action |
|---|---|
| `init()` | `_gradientBandCache = new uint16_t[AQ_CANVAS_W * AQ_BACKGROUND_GRADIENT_H]` |
| `resume()` | Same allocation |
| `suspend()` | `delete[] _gradientBandCache; _gradientBandCache = nullptr; _gradientBandCached = false;` |
| `_buildGradCache()` (internal) | Guards already present; no change needed |
| `drawBackground()` | Change `if (!_gradientBandCached)` to `if (!_gradientBandCache || !_gradientBandCached)` — allocate-null case skips the cache push and falls through to fillSprite only |

The allocation is **19,800 bytes** (`275 × 36 × sizeof(uint16_t)`). It is contiguous and
must succeed before the sprite allocation — failing to allocate the cache is non-fatal:
`drawBackground()` falls back to `fillSprite(AQ_BG_COLOR)` (solid black), losing the dithered
blue gradient but not crashing. The cache-miss path already exists in the current code.

#### `kMargin` update

`_calcDynamicSize()` uses `(maxAllocHeap - kMargin) / AQ_CANVAS_W` to size the sprite.
The original `kMargin = 8192` assumed only the sprite needed to come from that contiguous
budget. After this change, the gradient cache (19,800 B) is also a heap allocation. The
margin must cover it:

```cpp
static constexpr uint32_t kMargin = 19800 + 8192;  // cache + headroom = 27992
```

This ensures `_calcDynamicSize()` leaves enough room for the cache before deriving sprite height.

#### Allocation order in `init()` / `resume()`

The sprite must be allocated **before** the gradient cache — it is the larger, harder-to-fit
block and must claim the contiguous region that `_calcDynamicSize()` sized for it. The cache
at 19.8 KB can fill fragmented space left behind.

```
1. _calcDynamicSize()                          // uses updated kMargin=27992
2. _canvas.createSprite(AQ_CANVAS_W, _canvasH) // takes the big contiguous block
3. if sprite alloc fails → skip cache alloc, _spriteReady = false
4. allocate _gradientBandCache (19 800 B)      // fits in remaining space
5. if cache alloc fails → _gradientBandCached = false (fallback to solid fill)
```

If the gradient cache allocation fails, `drawBackground()` falls back to
`_canvas.fillSprite(AQ_BG_COLOR)` — solid black, no dithered gradient. That path already
exists via the `_gradientBandCached` flag.

#### Retry path (tick `!_spriteReady` branch)

The existing retry allocates only the sprite. After this change, any previously allocated
gradient cache must be freed before re-entering the allocation sequence, to avoid stranding
19.8 KB on the heap across retry attempts:

```cpp
// At top of retry attempt:
delete[] _gradientBandCache;
_gradientBandCache  = nullptr;
_gradientBandCached = false;
// then proceed with createSprite → cache alloc as above
```

#### Deallocation order in `suspend()`

```
1. _canvas.deleteSprite()
2. delete[] _gradientBandCache; _gradientBandCache = nullptr;
3. _gradientBandCached = false;
```

---

## 3. Change 2 — Right-Size Pool Arrays

### Fish pool

The upstream allocated `_fishPool[48]` ("pool size unchanged" per `overview.md §9`) to match
the original source. With `Preferences` dropped (ADR-031), `AQ_FISH_COUNT` is the permanent
runtime maximum. No code path ever activates more than `AQ_FISH_COUNT` fish.

```cpp
// Before
static constexpr int AQ_FISH_POOL_MAX = 48;
Fish _fishPool[AQ_FISH_POOL_MAX];           // 48 × ~48 B = ~2,304 B

// After
static constexpr int AQ_FISH_POOL_MAX = AQ_FISH_COUNT;  // = 16
Fish _fishPool[AQ_FISH_POOL_MAX];           // 16 × ~48 B = ~768 B
```

**Saving: ~1,536 B from `.bss`**

No logic change — all loops already guard on `i < _fishCount` (which is `≤ AQ_FISH_COUNT`).
Remove the constant `AQ_FISH_POOL_MAX` entirely; use `AQ_FISH_COUNT` directly as the array bound.

### Bubble pool

Same pattern. `AQ_BUBBLE_COUNT = 10` is the permanent active count.

```cpp
// Before
static constexpr int AQ_BUBBLE_POOL_MAX = 50;
Bubble _bubbles[AQ_BUBBLE_POOL_MAX];        // 50 × ~28 B = ~1,400 B

// After — remove AQ_BUBBLE_POOL_MAX, size directly
Bubble _bubbles[AQ_BUBBLE_COUNT];           // 10 × ~28 B = ~280 B
```

**Saving: ~1,120 B from `.bss`**

`applyBubblePopulation()` iterates `i < AQ_BUBBLE_POOL_MAX` today — change to `i < AQ_BUBBLE_COUNT`.

---

## 4. Summary of Changes

| Change | File | `.bss` delta |
|---|---|---|
| Gradient cache → heap pointer | `aquariumApp.h` | −19,800 B |
| `_fishPool[48]` → `[16]` | `aquariumApp.h` | −~1,536 B |
| `_bubbles[50]` → `[10]` | `aquariumApp.h` | −~1,120 B |
| **Total** | | **−~22,456 B (~21.9 KB)** |

No changes to `.data`, IRAM, or flash.

---

## 5. Effect on Heap Headroom

When aquarium is **suspended** (the common case — user is on another app):

| Before | After |
|---|---|
| 19.3 KB locked in .bss | 0 KB locked — cache freed with sprite |
| ~100 KB free heap | ~120 KB free heap |

When aquarium is **active**:

| Before | After |
|---|---|
| 19.3 KB in .bss + sprite on heap | 19.3 KB on heap (cache) + sprite on heap |
| Same total heap consumed | Same total heap consumed |

The gradient cache migration does not save heap when the app is active — it converts a `.bss`
reservation into an equivalent heap allocation. The benefit is on suspend: those 19 KB return
to the free pool, giving mbedTLS and other allocations more room.

---

## 6. Relationship to ADR-032

ADR-032 (heap arbitration) solves the SSL-vs-sprite contention at runtime via a yield
protocol. M-AQUARIUM-OPT reduces the static floor, giving that protocol more margin to work
with. The two changes are independent and may be implemented in either order.

---

## 7. VE Acceptance Criteria

| # | Test | Method |
|---|---|---|
| 1 | Fish count = 16 on init | Serial `get snapshot` or visual count |
| 2 | Bubble count = 10 on init | Visual |
| 3 | Blue gradient visible on init | Visual |
| 4 | Gradient correct after suspend/resume cycle | Visual |
| 5 | Solid-fill fallback if cache alloc fails | Force OOM in debug build (reduce pool, validate no crash) |
| 6 | check_build.sh passes | CI |
| 7 | `.bss` reduced ≥ 20 KB vs baseline | `nm` or map diff |

---

## 8. Open Questions Closed

Resolves `overview.md` Open Question #2: "gradientBandCache as member vs. heap".
