# M-MULTIAPP — Taskbar

> Part of: [overview.md](overview.md)
> Updated: 2026-05-25 — scrolling design added (wrap-around, N > 6 apps)

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
feel mushy and overshoot easily. Instead we adopt the **structural pattern** from
PLEDIT — dead zone, drag state, integer-step accumulation — but drive steps
directly from finger displacement with no velocity:

| Concept | PLEDIT source | Taskbar adaptation |
|---------|---------------|-------------------|
| Tap-vs-drag dead zone | `SCROLL_DEAD_ZONE_PX = 1` | same constant, re-used |
| Drag state enum | `D_PLEDIT_SCROLL` in `DragState` | add `D_TASKBAR_SCROLL` |
| Drag start Y | `_dragStartY` | `_tbDragStartY` (separate field) |
| Integer step accumulation | `_scrollAccum` + `steps` | same pattern, no velocity term |
| Wrap-around clamp | `max(0, min(max, offset+steps))` | `(offset + steps + N) % N` |
| Dirty flag + redraw | `_pleditScrollDirty` | call `renderTaskbar()` directly |

The velocity fields (`_scrollVelocity`, `_scrollSpeedK`) are **not** ported —
they are PLEDIT-specific and have no value here.

### State additions (WinampDisplay private section)

```cpp
// Taskbar scroll
int    _tbScrollOffset  = 0;          // index of top visible app slot (0..N-1)
int    _tbDragStartY    = 0;
float  _tbScrollAccum   = 0.0f;
```

`_tbScrollOffset` replaces the hardcoded `slot = p.y / 40` mapping in the
hit-test. It is the only persistent scroll state.

### Scroll arithmetic

```cpp
// Advance N steps (positive = scroll down / higher IDs visible):
const int totalApps = (int)AppId::COUNT;
_tbScrollOffset = (_tbScrollOffset + steps + totalApps) % totalApps;
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

## Hit-test (updated — scroll-aware)

In `WinampDisplay::checkForInput()`, the taskbar first-pass becomes:

```cpp
if (p.x >= 275) {
    if (dragState == D_IDLE) {
        // record drag start for tap-vs-scroll discrimination
        _tbDragStartY = p.y;
        dragState = D_TASKBAR_SCROLL;  // tentative; resolved on move/up
    }
    // consume — do not fall through to Winamp hit-tests
    return;
}
```

On **move** while `dragState == D_TASKBAR_SCROLL`:
```cpp
const int dy = p.y - _tbDragStartY;
const float eff = max(0.0f, (float)abs(dy) - (float)SCROLL_DEAD_ZONE_PX);
_tbScrollAccum += (dy < 0 ? 1.0f : -1.0f) * eff * 0.04f;  // tune constant
const int steps = (int)_tbScrollAccum;
if (steps != 0) {
    _tbScrollAccum -= (float)steps;
    const int N = (int)AppId::COUNT;
    _tbScrollOffset = (_tbScrollOffset + steps + N) % N;
    renderTaskbar(tft, currentAppId, _tbScrollOffset, N);
}
```

On **up** while `dragState == D_TASKBAR_SCROLL`:
```cpp
const bool isTap = abs(p.y - _tbDragStartY) < SCROLL_DEAD_ZONE_PX * 3;
if (isTap) {
    const int slot    = p.y / TASKBAR_SLOT_H;          // 0..5
    const int appIdx  = (_tbScrollOffset + slot) % (int)AppId::COUNT;
    if (appIdx != (int)currentAppId) {
        switchApp(static_cast<AppId>(appIdx));
    }
}
_tbScrollAccum = 0.0f;
dragState = D_IDLE;
touchScreenCoolDownTime = millis() + 300;
```

The tap dead zone for switch is 3× the scroll dead zone (3 px) to prevent
accidental app switches during short swipes.

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
