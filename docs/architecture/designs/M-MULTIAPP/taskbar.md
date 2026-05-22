# M-MULTIAPP — Taskbar

> Part of: [overview.md](overview.md)

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

## Icon layout (6 apps, 45×240)

```
y=0   +-------+
      |  [S]  |  Spotify / Winamp   ← active indicator
y=40  +-------+
      |  [C]  |  Clock
y=80  +-------+
      |  [W]  |  Weather
y=120 +-------+
      |  [€]  |  Crypto
y=160 +-------+
      |  [M]  |  Matrix rain
y=200 +-------+
      |  [G]  |  Game of Life
y=240 +-------+
```

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

## Hit-test

In `WinampDisplay::checkForInput()` (winampDisplay.h:220), add a first-pass
check before all existing hit-tests:

```cpp
if (p.x >= 275) {
    int slot = p.y / 40;            // 0..5
    if (slot != currentAppId) {
        switchApp(static_cast<AppId>(slot));
    }
    // consume event — do not fall through to Winamp hit-tests
    touchScreenCoolDownTime = millis() + 300;
    return;
}
```

The taskbar check is an absolute screen-coordinate test (x ≥ 275), so it is
independent of `originX` and works regardless of which app is active.

## Rendering

`renderTaskbar()` — new free function or `WinampDisplay` method:

- Called once from `repaintChrome()` on startup, and again whenever the active
  app changes (to update the active indicator).
- Draws the 45×240 background fill.
- Blits each icon glyph to its cell centre.
- Draws the active indicator bar for `currentAppId`.

Not called on every loop iteration — the taskbar is static between app switches.

## Dependency on preview pass

Icon glyphs and active-indicator colour are locked by the preview tooling
pass. Implementation of `renderTaskbar()` is blocked on that decision.
