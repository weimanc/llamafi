# M-MULTIAPP — Taskbar

> Part of: [overview.md](overview.md)
> Updated: 2026-05-26 — scroll UX revised: 1:1 positional + LP filter + 3 px dead zone (post-implementation UX tuning)

## Role

The taskbar is a **45×240 px vertical icon strip** on the right edge of the
screen. It is always visible and always hit-testable, regardless of which app
is active. It is not a FreeRTOS task; it is a persistent rendering layer and
a first-priority zone in the input dispatch chain.

## RTOS clarification

> "Is the taskbar the concurrent app in the RTOS sense?"

No. The taskbar is not a FreeRTOS task. Concurrency in this project is used
for **network I/O** (spotifyTask, future dataTask) to avoid blocking the render
loop. The taskbar has no I/O — it is a strip of icons drawn once and hit-tested
on every touch event. "Always present" means: its hit-box is checked first in
`checkForInput()` before the active app gets the event. If the tap lands in
x: 275..319, the taskbar consumes it and triggers an app switch; otherwise the
event is passed to the active app.

The **only** RTOS-flavoured concept the taskbar introduces is that its rendered
pixels must not be overwritten by any app. This is enforced by the canvas
constraint (see layout.md), not by a task priority or mutex.

## Icon layout (N apps, 6 visible slots, 45×240)

The taskbar always shows exactly **6 slots** (the full 240 px height). With more
than 6 apps registered, the strip scrolls to reveal the rest. Apps 7 and 8
(Settings, Stock) are already designed; further apps may follow.

```
y=0   +-------+
      |  [S]  |  scrollOffset+0
y=40  +-------+
      |  [C]  |  scrollOffset+1
y=80  +-------+
      |  [W]  |  scrollOffset+2
y=120 +-------+
      |  [€]  |  scrollOffset+3
y=160 +-------+
      |  [M]  |  scrollOffset+4
y=200 +-------+
      |  [G]  |  scrollOffset+5
y=240 +-------+
```

Slot `i` (0..5) renders app `(scrollOffset + i) % totalApps`.

Each icon cell: 45 wide × 40 tall.
Icon glyph: 24×24 px centred in the cell (10 px padding left/right, 8 px top/bottom).
Active indicator: 3 px vertical bar on the left edge of the active cell (x=275, y=cell_top..cell_top+39), colour `0x07E0` (Spotify green, `TASKBAR_ACTIVE_COLOR` in `gen/shell_layout.h`).

## Aesthetics (resolved — preview tooling pass complete)

Resolved values locked in `gen/shell_layout.h` (exported by `preview_layout.py`):

1. **Background** — `TASKBAR_BG_RGB565 = 0x2104` (very dark grey, close to `#111`).
2. **Icon style** — Winamp 5×6 bitmap glyphs from TEXT.BMP, centred in 24×24 cells using `SKIN_GLYPH` table.
3. **Active indicator** — `TASKBAR_ACTIVE_STYLE = 'A'` (3 px left-edge bar, `TASKBAR_ACTIVE_COLOR = 0x07E0`).
4. **Separator lines** — `TASKBAR_SEP_ENABLED = 1` with `TASKBAR_SEP_COLOR = 0x4208` (mid-grey rules).
5. **Icon source** — extracted from the WSZ skin's TEXT.BMP at bake time; same atlas as firmware `SKIN_GLYPH`.

## Scroll model

### Why a new model rather than straight PLEDIT reuse

PLEDIT scroll uses a **velocity accumulator** (`tickScroll`, `_scrollVelocity`,
`_scrollSpeedK`). That model is designed for a long queue (unlimited items) where
fractional-step inertia feels natural.

The taskbar has at most ~10–12 items. Velocity inertia on a 6-slot strip would
feel mushy and overshoot easily. The taskbar uses a **1:1 positional model**:
finger displacement from the press origin maps directly to slot offset, smoothed
by an LP filter to absorb digitizer jitter.

| Concept | PLEDIT source | Taskbar adaptation |
|---------|---------------|-------------------|
| Tap-vs-drag dead zone | `SCROLL_DEAD_ZONE_PX = 1` | **`TB_SCROLL_DEAD_ZONE_PX = 3`** (separate constant) |
| Drag state enum | `D_PLEDIT_SCROLL` in `DragState` | add `D_TASKBAR_SCROLL` |
| Drag start Y | `_dragStartY` | `_tbDragStartY` (separate field) |
| Offset at press | — | `_tbDragBaseOff` (positional anchor) |
| Scroll amount | velocity accumulator | **1:1**: `steps = (int)(-smoothedDy / SLOT_H)` |
| Jitter suppression | — | **LP filter** on raw dy: `accum += (raw − accum) × 0.4` |
| Tap detection | `abs(dy) < DEAD_ZONE * 3` | **`_tbIsScrolling` flag** (set once dead zone exceeded) |
| Wrap-around | `max(0, min(max, offset))` | `((_tbDragBaseOff + steps) % N + N) % N` |
| Dirty flag + redraw | `_pleditScrollDirty` | call `renderTaskbar()` directly |

The velocity fields (`_scrollVelocity`, `_scrollSpeedK`) are **not** ported.

### State additions (WinampDisplay private section)

```cpp
// Taskbar scroll (M-TASKBAR-SCROLL)
int   _tbScrollOffset = 0;    // index of top visible app slot (0..N-1); only persistent field
int   _tbDragStartY   = 0;    // Y at press; used for dead-zone and tap-slot calculation
int   _tbDragBaseOff  = 0;    // _tbScrollOffset captured at press; positional 1:1 anchor
float _tbScrollAccum  = 0.0f; // LP-filtered pixel displacement from _tbDragStartY
bool  _tbIsScrolling  = false; // latched true once dead zone exceeded; blocks tap-on-release

static constexpr int   TB_SCROLL_DEAD_ZONE_PX = 3;   // px before scroll engages
static constexpr float TB_LP_ALPHA             = 0.4f; // EMA weight (0=frozen, 1=raw)
```

### Scroll arithmetic

Positional 1:1, anchored to press origin. Finger-up (negative raw dy) increases offset:

```cpp
_tbScrollAccum += ((float)rawDy - _tbScrollAccum) * TB_LP_ALPHA;  // LP filter
const int steps     = (int)(-_tbScrollAccum / TASKBAR_SLOT_H);    // 1:1 slot mapping
const int newOffset = ((_tbDragBaseOff + steps) % N + N) % N;      // wrap-around
```

Wrap-around is free: modulo naturally cycles from the last app back to slot 0.

### Rendering signature change

```cpp
void renderTaskbar(TFT_eSPI& tft, AppId activeApp,
                   int scrollOffset, int totalApps);
```

Inner loop becomes:

```cpp
for (int i = 0; i < TASKBAR_SLOT_COUNT; ++i) {
    int appIdx = (scrollOffset + i) % totalApps;
    // draw icons[appIdx], active indicator if appIdx == (int)activeApp
}
```

`renderTaskbar()` is called whenever `_tbScrollOffset` changes (scroll) **or**
`activeApp` changes (app switch). Not called on every tick.

### Scroll position indicator

A minimal 2×(slot_h-4) px indicator column on the right edge of the taskbar
(x = TASKBAR_X + TASKBAR_W - 2) shows which portion of the app list is visible.
It moves proportionally: `indicatorY = (scrollOffset * 240) / totalApps`.
Deferred to implementation; not required for first scroll pass.

## Hit-test (scroll-aware)

Taskbar gesture routing lives in `appHandleInput()` in `main.cpp` (not
`WinampDisplay::checkForInput()`). Three branches, dispatched via
`winampDisplay.tbIsDragging()` and the public method bundle on `WinampDisplay`:

**Press** (`p.x >= TASKBAR_X`, `tbIsDragging() == false`):
```cpp
winampDisplay.tbGesturePress(p.y);
// captures _tbDragStartY, _tbDragBaseOff, resets _tbScrollAccum/_tbIsScrolling
// sets dragState = D_TASKBAR_SCROLL
```

**Move** (`p.x >= TASKBAR_X`, `tbIsDragging() == true`):
```cpp
if (winampDisplay.tbGestureContinue(p.y, (int)AppId::COUNT))
    renderTaskbar(tft, currentAppId, winampDisplay.tbScrollOffset(), (int)AppId::COUNT);
// tbGestureContinue: LP-filters rawDy, sets _tbIsScrolling once dead zone exceeded,
// computes 1:1 steps, updates _tbScrollOffset, returns true if offset changed
```

**Release** (`!touched`, `tbIsDragging() == true`):
```cpp
int appIdx = (int)currentAppId;
if (winampDisplay.tbGestureEnd(s_lastTouchY, (int)AppId::COUNT, &appIdx))
    if (appIdx != (int)currentAppId) switchApp(static_cast<AppId>(appIdx));
// tbGestureEnd: tap = !_tbIsScrolling; resets drag state; fills outAppIdx for tap
```

**Tap detection**: `_tbIsScrolling` is latched the first time `|rawDy| >= TB_SCROLL_DEAD_ZONE_PX (= 3)`. If it was never set, the release is a tap. This gives a clean binary separation — no `abs(dy)` comparison at release time.

## Rendering

`renderTaskbar()` — free function in `taskbar.h`:

- Called from `repaintChrome()` on startup (scrollOffset=0, full redraw).
- Called from `switchApp()` to update the active indicator.
- Called inline during taskbar drag to reflect in-progress scroll.
- Draws the 45×240 background fill, all 6 icon glyphs (index via `scrollOffset`),
  active indicator bar for `currentAppId`, and (deferred) scroll position dot.

Not called on every loop iteration when idle.

## Dependency on preview pass

Icon glyphs and active-indicator colour are locked by the preview tooling
pass. Implementation of `renderTaskbar()` is blocked on that decision.
