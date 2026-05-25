# Design — Aquarium App (M-AQUARIUM)

> Owner: Architect
> Status: draft
> Date: 2026-05-25
> Source: `resource/ASCII_Aquarium/ASCII_Aquarium_CYD.ino` (v1.67, 4123 lines)
> ADR: [ADR-031](../../decisions/ADR-031.md) — sprite viewport 275 px, 8-bit depth, Preferences dropped

---

## 1. Feature Scope

### Included

| Feature | Source function(s) | Notes |
|---|---|---|
| Fish simulation — 12 species, mirrored glyphs, schooling, wander, avoid | `updateFish()`, `initFishMirrors()`, `initFishGlyphMetrics()`, `applyFishPopulation()`, `spreadInitialFishLayout()`, `keepFishOutsideOctopus()`, `keepFishOutsideSeahorse()` | Pool capped at `AQ_FISH_COUNT` = 16 (not 48) |
| Bubbles — sway, rise, color | `updateBubbles()`, `applyBubblePopulation()`, `drawBubbles()` | Pool capped at `AQ_BUBBLE_COUNT` = 10 (not 50) |
| Flakes (food drops) — sink, attract fish | `spawnFlake()`, `updateFlakes()`, `drawFlakes()` | Triggered by touch |
| Seaweed — sway, branches, color gradient | `drawSeaweed()`, `drawSeaweedBranches()`, `seaweedPointAt()` | Constants baked in; `static` cache becomes class member |
| Octopus visitor | `spawnOctopus()`, `updateOctopus()`, `drawOctopus()`, `drawOctopusGlyph()` | Frequency constant `AQ_OCTOPUS_FREQ` = 1 |
| Seahorse visitor | `spawnSeahorse()`, `updateSeahorse()`, `drawSeahorse()`, `drawSeahorseGlyph()` | Frequency constant `AQ_SEAHORSE_FREQ` = 1 |
| Visitor separation | `keepVisitorsSeparated()` | Unchanged |
| Background — blue gradient only | `drawBackground()`, `drawCachedTopGradientBackground()`, `drawVerticalGradientStops()` | `backgroundMode` hard-wired to `BACKGROUND_BLUE_GRADIENT`; other modes removed |
| Frame render via sprite | `renderFrame()` | Canvas 275×240; `canvas.pushSprite(0,0)` |
| Clock overlay — small-text, top, white | `drawClock()` | Style fixed to `CLOCK_STYLE_SMALL_TEXT`; reads `time(nullptr)` directly; `clockVisible` always `true` |
| Touch-to-feed | `handleInput(Press, x, y)` → `spawnFlake(x,y)` | See §7 |

### Excluded (with rationale)

| Feature | Rationale |
|---|---|
| Settings UI (all 4 tabs: Tank, Seaweed, Clock, Background) | Not useful at fixed constants; eliminating it removes ~700 lines and all `settingsOpen` / panel state |
| WiFi panel + keyboard UI | Host `main.cpp` owns WiFi; double-ownership would conflict |
| NTP management (`serviceInternetTime`, `serviceWifi`) | `configTime()` already called at boot in `main.cpp`; app reads `time(nullptr)` directly |
| SD card / BMP capture (`saveBmpToSd`, `saveNextCaptureFrame`, VSPI, `SD.h`) | Dev tool, no hardware in our board config |
| HUD toggle (top-left corner button) + corner debug buttons (D/C/W/S/R/H/O) | Reduces clutter; `hudVisible` always `false` |
| Capture panel | Dependent on SD; dropped with SD |
| `Preferences` / `loadPersistentState()` / `saveSettings()` | See ADR-031; replaced by compile-time constants |
| `serviceBootButton()` | BOOT button is not relevant in multi-app shell |
| ASCII-art clock style + `clockFlipSprite` | Requires a second sprite (192×20 + 275×240 simultaneously), excess heap pressure; small-text style is sufficient |
| Clock "flip horizontal" mode | Only needed with ASCII-art style |
| Timezone management UI | Shell NTP timezone is already configured at boot |
| Background modes other than blue gradient | Simplicity; purple, flowers not material to the port |
| FPS counter (`fps`, `frameCount`, `fpsTimer`) | Not exposed in our HUD; perf tracked by shell `perf::` instead |
| `bmpRowBuffer[SCREEN_W * 3]` (960 bytes) | SD dropped |
| XPT2046_Touchscreen, SPIClass (HSPI/VSPI) | Shell owns touch via `CYD28_TouchscreenR`; touch delivered through `handleInput()` |

---

## 2. Module Boundary

Single header: `app/src/aquarium/aquariumApp.h`

The class `AquariumApp` is self-contained and owns:
- All simulation structs (`Flake`, `Bubble`, `FishSpecies`, `Fish`, `Octopus`, `Seahorse`)
- All helper types (`AsciiClockGlyph` — kept for the `kAsciiClockStandardGlyphs` glyph table, which `drawClock` indirectly references for metric data even in small-text mode if the upstream helper calls it — verify during implementation; if unused in small-text path, drop it)
- All constants (see §9)
- `TFT_eSprite _canvas` — private member; lifecycle in §8
- All private methods for update, draw, and init (see §4 for the full list lifted from `loop()` + `setup()`)
- A single global reference to the `tft` object declared in `main.cpp` (already `extern TFT_eSPI tft` in the codebase via `cheapYellowLCD.h` / TFT_eSPI macros)

What the class does **not** own:
- `tft` hardware object (owned by `main.cpp` / display layer)
- WiFi, NTP, SD
- Touch hardware (delivered via `handleInput()`)
- Any FreeRTOS task

No `.cpp` companion file is needed; the simulation is compute-bound with no long-running work offloadable to a task.

---

## 3. State Struct in appShell.h

```cpp
struct AquariumAppState {
    bool initialised;   // true after first init() call
};
```

The full simulation state (fish pool, bubble pool, flakes, octopus, seahorse, timing fields) lives inside `AquariumApp` as private members, **not** in this struct. `AquariumAppState` exists only to satisfy the pattern used by other apps (ClockAppState, LifeAppState) for the `g_appLaunched` first-launch gate.

Add to `appShell.h` after `LifeAppState`:

```cpp
struct AquariumAppState {
    bool initialised;
};
```

---

## 4. App Shell Wiring

### 4a. AppId enum — bump COUNT to 7

In `appShell.h`:

```cpp
enum class AppId : uint8_t {
    Spotify   = 0,
    Clock     = 1,
    Weather   = 2,
    Crypto    = 3,
    Matrix    = 4,
    Life      = 5,
    Aquarium  = 6,   // added
    COUNT     = 7,   // was 6
};
```

### 4b. TASKBAR_SLOT_COUNT — bump to 7

In `app/src/gen/shell_layout.h`:

```diff
-#define TASKBAR_SLOT_COUNT    6
+#define TASKBAR_SLOT_COUNT    7
```

`TASKBAR_SLOT_H = 240 / 7 = 34 px` (integer division; was 40). The taskbar slot height is recomputed by the taskbar renderer as `240 / TASKBAR_SLOT_COUNT`, so no other constant changes. Verify that `TASKBAR_SLOT_H` is not hardcoded anywhere else — it is not: the shell uses the `#define` throughout.

> **Note**: `shell_layout.h` is listed as "do not edit by hand" (generated by `tools/preview_layout.py`). However, for a slot count bump this is an acceptable direct edit; the preview tool regenerates it from the skin. Update `TASKBAR_SLOT_COUNT` there and note in the PR that the preview tool should be re-run after to keep the PNG in sync.

The `static_assert((int)AppId::COUNT == TASKBAR_SLOT_COUNT)` in `appShell.h` enforces this at compile time — it will fail until both values are set to 7.

### 4c. g_apps registry — add entry

In `main.cpp`, inside the `#ifdef WINAMP_DISPLAY` block:

```cpp
#include "aquarium/aquariumApp.h"
static AquariumApp g_aquariumApp;

App* g_apps[(int)AppId::COUNT] = {
  &g_spotifyApp,    // AppId::Spotify   = 0
  &g_clockApp,      // AppId::Clock     = 1
  &g_weatherApp,    // AppId::Weather   = 2
  &g_cryptoApp,     // AppId::Crypto    = 3
  &g_matrixApp,     // AppId::Matrix    = 4
  &g_lifeApp,       // AppId::Life      = 5
  &g_aquariumApp,   // AppId::Aquarium  = 6
};
```

`g_appLaunched` is sized as `bool g_appLaunched[(int)AppId::COUNT]` — it auto-expands to 7 with no code change.

### 4d. cmdGet appId — add name string

In the `cmdGet` handler in `main.cpp`, add:

```cpp
: currentAppId == AppId::Aquarium ? "Aquarium"
```

to the ternary chain for the `"appId"` var query.

---

## 5. Viewport Adaptation

### Sprite dimensions

The upstream sketch creates `canvas` at `SCREEN_W × SCREEN_H` = 320×240. The app canvas is **275×240**, matching the left viewport boundary `TASKBAR_X = 275`.

```cpp
// In AquariumApp::init() / resume():
_canvas.setColorDepth(8);
_spriteReady = (_canvas.createSprite(AQ_CANVAS_W, AQ_CANVAS_H) != nullptr);
if (_spriteReady) _canvas.setTextFont(2);
```

Where:
```cpp
static constexpr int AQ_CANVAS_W = 275;
static constexpr int AQ_CANVAS_H = 240;
```

### SCREEN_W references

Every occurrence of `SCREEN_W` in ported code becomes `AQ_CANVAS_W` (275). Affected sites include:

| Site | Original expression | Ported expression |
|---|---|---|
| Background gradient buffer width | `SCREEN_W * BACKGROUND_GRADIENT_H` | `AQ_CANVAS_W * AQ_BACKGROUND_GRADIENT_H` |
| Fish spawn x range | `frand(-42, SCREEN_W + 12)` | `frand(-42.0f, AQ_CANVAS_W + 12.0f)` |
| Fish candidateX range | `frand(10.0f, SCREEN_W - f.visualWidth - 10.0f)` | `frand(10.0f, AQ_CANVAS_W - f.visualWidth - 10.0f)` |
| Bubble baseX | `frand(8.0f, SCREEN_W - 8.0f)` | `frand(8.0f, AQ_CANVAS_W - 8.0f)` |
| Fish schooling wrap `sdx` | `SCREEN_W * 0.5f` | `AQ_CANVAS_W * 0.5f` |
| Fish wrap pad exit | `SCREEN_W + wrapPad` | `AQ_CANVAS_W + wrapPad` |
| Octopus spawn x | `SCREEN_W + OCTOPUS_EXIT_PAD` / `SCREEN_W * 0.5f` | same with `AQ_CANVAS_W` |
| Seahorse spawn x | `SCREEN_W + SEAHORSE_EXIT_PAD` / `SCREEN_W * 0.5f - 16.0f` | same with `AQ_CANVAS_W` |
| Seaweed root spacing | `10 + i * (SCREEN_W - 20.0f) / (roots - 1)` | `10 + i * (AQ_CANVAS_W - 20.0f) / (roots - 1)` |
| Clock draw x | `SCREEN_W / 2` | `AQ_CANVAS_W / 2` |
| ASCII clock centering | `(SCREEN_W - artPixelW) / 2` | `(AQ_CANVAS_W - artPixelW) / 2` |
| Touch x-clamp check | `sx >= 0 && sx < SCREEN_W` | Not applicable — shell clamps touch x to `[0, TASKBAR_X)` before delivery |
| gradientBandCache width | `SCREEN_W * BACKGROUND_GRADIENT_H` | `AQ_CANVAS_W * AQ_BACKGROUND_GRADIENT_H` |

**No upstream constant named `SCREEN_W` must survive into `aquariumApp.h`**; every occurrence is replaced with `AQ_CANVAS_W` to eliminate the naming collision and make the remapping explicit.

### gradientBandCache

The upstream declares `uint16_t gradientBandCache[SCREEN_W * BACKGROUND_GRADIENT_H]` as a file-scope global (320 × 60 = 19200 bytes). Ported to `AquariumApp` as a private member array:

```cpp
uint16_t _gradientBandCache[AQ_CANVAS_W * AQ_BACKGROUND_GRADIENT_H]; // 275×60 = 16500 bytes
```

This lives in the class instance which is a `static` local in `main.cpp` — stack-allocated at program start. 16.5 KB is acceptable; `LifeApp` already carries a 2.9 KB grid in a similar static instance. If heap pressure becomes an issue, this array can be moved to a `heap_caps_malloc(MALLOC_CAP_8BIT)` allocation in `init()` and freed in `suspend()`.

### pushSprite origin

```cpp
_canvas.pushSprite(0, 0);  // always top-left; taskbar occupies x=275..319
```

---

## 6. Clock Integration

The upstream sketch maintains a software clock (`clockHour`, `clockMinute`, `clockLastMinuteMs`) updated once per minute by `updateClock(now)`, plus an optional WiFi NTP sync.

The ported app discards that mechanism entirely. `AquariumApp::updateClock()` reads system time directly:

```cpp
void updateClock() {
    time_t now = time(nullptr);
    struct tm ti;
    localtime_r(&now, &ti);
    _clockHour   = ti.tm_hour;
    _clockMinute = ti.tm_min;
}
```

`updateClock()` is called once per `tick()` before `renderFrame()`. Because it calls `time()` + `localtime_r()` (no I/O), the overhead is negligible.

`drawClock()` in the ported class reads `_clockHour` and `_clockMinute` from member variables. The upstream's `formatClockDisplay()` helper is retained but trimmed to small-text only:

```cpp
void formatClockDisplay(char* out, size_t cap) {
    snprintf(out, cap, "%02d:%02d", _clockHour, _clockMinute);
}
```

Clock is always visible (`_clockVisible = true`), always at top of screen (`y = 4`), always white, always small-text font-2 style. No runtime toggle.

The `clockFlipSprite` (used exclusively for the ASCII-art horizontal-mirror mode) is **not created** — that mode is dropped.

---

## 7. Touch → Feed Mapping

The upstream `processTouch()` guards against settings/HUD zones before calling `spawnFlake`. In the ported app, those zones do not exist. Any Press in the app viewport `[0..274] × [0..239]` spawns a flake at the touch point.

```cpp
bool handleInput(TouchPhase phase, int x, int y) override {
    if (phase == TouchPhase::Press) {
        spawnFlake((float)x, (float)y);
        return true;
    }
    return false;
}
```

Move and Release are ignored (no drag interaction in the aquarium).

The app returns `true` on Press to trigger the shell cooldown (200 ms), preventing rapid multi-spawn on a slow finger lift.

---

## 8. Sprite Lifecycle

Following the same pattern as `LifeApp` (which uses the `tft` directly) and consistent with the `AquariumApp` using a sprite:

| Event | Action |
|---|---|
| `init()` | `_canvas.createSprite(275, 240)` — first launch; also calls simulation init (fish, bubbles, seaweed cache) |
| `resume()` | `_canvas.createSprite(275, 240)` — re-entry after another app was active; sprite was deleted on suspend |
| `suspend()` | `_canvas.deleteSprite()` — releases heap; sets `_spriteReady = false` |
| `tick()` | Runs simulation update + `renderFrame()` only if `_spriteReady` |

The 275×240 8-bit sprite consumes **66 000 bytes** (275 × 240 × 1) from the internal heap. The ESP32-2432S028R has no PSRAM; `createSprite` allocates from the internal heap only. 66 KB is half the 16-bit cost and leaves adequate headroom alongside the Winamp skin atlas and other runtime allocations.

Deleting the sprite on `suspend()` ensures that when the user is on any other app, the 66 KB is returned to the heap, available for Winamp skin operations.

---

## 9. Constants

All values below replace runtime-settable `Preferences` fields. They are `static constexpr` members of `AquariumApp` (or file-scope `constexpr` at the top of `aquariumApp.h`).

```cpp
static constexpr int   AQ_CANVAS_W           = 275;
static constexpr int   AQ_CANVAS_H           = 240;
static constexpr int   AQ_FISH_COUNT         = 16;    // upstream default 16, pool 48
static constexpr int   AQ_FISH_POOL_MAX      = 48;    // pool size unchanged (only AQ_FISH_COUNT are active)
static constexpr int   AQ_BUBBLE_COUNT       = 10;    // upstream default 10, pool 50
static constexpr int   AQ_BUBBLE_POOL_MAX    = 50;    // pool size unchanged
static constexpr int   AQ_FLAKE_MAX          = 16;    // unchanged from upstream MAX_FLAKES
static constexpr int   AQ_OCTOPUS_FREQ       = 1;     // visits per hour
static constexpr int   AQ_SEAHORSE_FREQ      = 1;     // visits per hour
static constexpr float AQ_SWAY               = 1.10f;
static constexpr float AQ_SEAWEED_LEN        = 1.35f;
static constexpr float AQ_SEAWEED_RAND       = 0.35f;
static constexpr int   AQ_BACKGROUND_GRADIENT_H = AQ_CANVAS_H / 4;  // 60 px
// Clock
static constexpr bool  AQ_CLOCK_VISIBLE      = true;
static constexpr int   AQ_CLOCK_Y            = 4;     // top of viewport
static constexpr uint16_t AQ_CLOCK_COLOR     = 0xFFFF; // TFT_WHITE
```

The upstream simulation physics constants (fish avoid radii, octopus/seahorse exit pads, swim wave parameters, visitor clear radii, etc.) are carried over unchanged as they are tuning parameters for the existing simulation, not user-settable preferences. They are listed in the upstream source at lines 300–327 and should be transcribed as-is into `aquariumApp.h` with `AQ_` prefix for clarity.

---

## 10. Dependency Audit

### Includes to keep

| Include | Reason |
|---|---|
| `<Arduino.h>` | `millis()`, `random()`, `String` |
| `<TFT_eSPI.h>` | `TFT_eSprite`, `tft` reference, color constants |
| `<time.h>` | `time()`, `localtime_r()` for clock integration |
| `<cstring>` | `memset`, `snprintf` (already in Arduino environment but explicit is safer) |
| `<math.h>` / `<cmath>` | `sinf`, `cosf`, `sqrtf`, `fabsf` |

### Includes to drop (vs. upstream)

| Include | Reason dropped |
|---|---|
| `<Preferences.h>` | Replaced by compile-time constants (ADR-031) |
| `<SD.h>` | Capture system dropped |
| `<WiFi.h>` | Shell owns WiFi |
| `<XPT2046_Touchscreen.h>` | Shell owns touch |
| `<SPI.h>` (HSPI/VSPI) | Touch and SD both dropped |
| `<FS.h>` | SD dropped; SPIFFS not used by aquarium |
| `<WiFiManager.h>` | Not applicable in multi-app shell |

---

## 11. Task Breakdown

Ordered implementation steps. Each step should be buildable (or at least compilable) before the next.

| Step | Task | Files |
|---|---|---|
| 1 | Bump `TASKBAR_SLOT_COUNT` to 7 in `shell_layout.h`; bump `AppId::Aquarium = 6`, `COUNT = 7` in `appShell.h`; add `AquariumAppState` struct; verify `static_assert` compiles | `appShell.h`, `gen/shell_layout.h` |
| 2 | Create `app/src/aquarium/aquariumApp.h` skeleton: `AquariumApp` class with all five virtual methods stubbed; constants block; private member declarations for all pools and timing fields | `aquarium/aquariumApp.h` |
| 3 | Transcribe simulation structs (`Flake`, `Bubble`, `FishSpecies`, `Fish`, `Octopus`, `Seahorse`) into `aquariumApp.h` as inner structs of `AquariumApp` | `aquarium/aquariumApp.h` |
| 4 | Transcribe all physics/simulation helper functions (`updateFish`, `updateBubbles`, `updateFlakes`, `updateOctopus`, `updateSeahorse`, `keepVisitorsSeparated`, `spawnFlake`, `spawnOctopus`, `spawnSeahorse`, population/init functions) as private methods; replace all `SCREEN_W` → `AQ_CANVAS_W` | `aquarium/aquariumApp.h` |
| 5 | Transcribe background + seaweed render functions (`drawBackground`, `drawCachedTopGradientBackground`, `drawSeaweed`, `drawSeaweedBranches`, `seaweedPointAt`); adapt `gradientBandCache` to member array; confirm blue-gradient path only | `aquarium/aquariumApp.h` |
| 6 | Transcribe fish/bubble/flake/octopus/seahorse draw functions (`drawFish`, `drawBubbles`, `drawFlakes`, `drawOctopus`, `drawSeahorse`); bring in glyph tables and metrics | `aquarium/aquariumApp.h` |
| 7 | Implement `drawClock()` as described in §6 (small-text only, `time(nullptr)` path) | `aquarium/aquariumApp.h` |
| 8 | Implement `renderFrame()` calling `drawBackground`, `drawSeaweed`, `drawBubbles`, `drawFlakes`, `drawFish`, `drawOctopus`, `drawSeahorse`, `drawClock`, then `_canvas.pushSprite(0,0)` | `aquarium/aquariumApp.h` |
| 9 | Implement `init()`: zero pools, call `initFishMirrors`, `initFishGlyphMetrics`, `applyFishPopulation`, `spreadInitialFishLayout`, `applyBubblePopulation`; create sprite; seed timing fields | `aquarium/aquariumApp.h` |
| 10 | Implement `resume()` (create sprite, clear screen region), `suspend()` (deleteSprite), `tick()` (dt from millis delta, call updateClock + all update functions + renderFrame), `handleInput()` (Press → spawnFlake) | `aquarium/aquariumApp.h` |
| 11 | Wire into `main.cpp`: `#include "aquarium/aquariumApp.h"`, add `static AquariumApp g_aquariumApp`, add to `g_apps[]`, add `"Aquarium"` to `cmdGet` appId chain | `main.cpp` |
| 12 | Build `cyd2usb_winamp` — fix any compile errors (include order, `tft` extern visibility, type conflicts from `uint16_t` etc.) | — |
| 13 | Build `cyd2usb_winamp_debug` — fix debug-specific issues | — |
| 14 | Run `check_build.sh` — verify both targets pass golden hash | — |
| 15 | Flash to device; manually switch to Aquarium slot in taskbar; observe fish; tap to spawn flakes; switch away and back (verify sprite lifecycle — no crash) | device |

---

## Seaweed Cache Note

The upstream `drawSeaweed()` uses three `static` local arrays (`baseX[roots]`, `amp[roots]`, `heightNoise[roots]`) with a `static bool cached` flag to lazy-init them. Statics inside a method are not safe to reset when the app suspends and resumes. In the ported class, these become private member arrays (12 floats each + a `bool _seaweedCached`) initialized in `init()` and not reset in `suspend()` (the values are deterministic from constants and do not need regeneration on resume).

---

## Open Questions

1. **Taskbar icon for Aquarium**: `shell_layout.h` / `taskbar.h` need a glyph for slot 6. The current taskbar draws a Unicode/ASCII character per slot. A fish glyph (`~` or a custom character) needs to be specified. This is a UI detail, not a blocker for functional implementation.

2. **gradientBandCache as member vs. heap**: 16.5 KB in the class instance (static storage). If total static data causes linker complaints, move it to `heap_caps_malloc(MALLOC_CAP_8BIT)` allocated in `init()` and freed in `suspend()`. No change to the algorithm.

3. **`seaweedSwaySpeed`, `seaweedLength`, `seaweedLengthRandomness`**: currently global float variables referenced across multiple functions. In the ported class these become private members initialized from constants. Verify no function in the simulation modifies them (they should be read-only after init — confirmed: only `drawSeaweed` and `drawSeaweedBranches` read them; `loadPersistentState`/`saveSettings` write them, both dropped).

4. **`AsciiClockGlyph` table**: the small-text clock path (`CLOCK_STYLE_SMALL_TEXT`) does not invoke any `AsciiClockGlyph` lookup. The entire `kAsciiClockStandardGlyphs[]` table and `asciiClockGlyphFor()` / `asciiClockGlyphWidth()` / `appendAsciiClockGlyphRow()` functions can be omitted. Confirm during implementation by tracing `drawClock()` → `formatClockDisplay()` → `snprintf` only.

5. **`dt` clamping**: the upstream clamps `elapsedMs` to `[1, 50]` ms. The ported `tick()` should do the same: `float dt = clampVal(millis() - _lastTickMs, 1UL, 50UL) * 0.001f`.
