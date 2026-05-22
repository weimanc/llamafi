# M-MULTIAPP — Screen Layout

> Part of: [overview.md](overview.md)

## Current geometry

| Constant | Value | Source |
|----------|-------|--------|
| Screen width | 320 px | `cheapYellowLCD.h:82` |
| Screen height | 240 px | `cheapYellowLCD.h:83` |
| Rotation | 1 (landscape) | `cheapYellowLCD.h:90` |
| Winamp window W | 275 px | `winampDisplay.h: WINDOW_W` |
| Winamp window H | 116 px | `winampDisplay.h: WINDOW_H` |
| PLEDIT H | 124 px | `gen/skin_layout.h: PLEDIT_H` |
| Current originX | 22 px (centred) | `winampDisplay.h:49` |
| Current originY | 0 px | `winampDisplay.h:50` |

Note: 116 + 124 = 240 — the main window + PLEDIT exactly fill screen height.

## Target geometry

```
x=0                    x=275  x=320
+----------------------+------+
|                      |      |  y=0
|  Winamp main window  | TASK |
|     275 × 116        |  BAR |
+----------------------+  45  |
|                      |  ×   |
|  PLEDIT / app canvas | 240  |
|     275 × 124        |      |
+----------------------+      |
                        y=240 +
```

- **Winamp / left canvas:** x: 0..274, y: 0..239 (275×240)
- **Taskbar strip:** x: 275..319, y: 0..239 (45×240)

## Changes to `winampDisplay.h`

`displaySetup()` line 49 currently:
```cpp
originX = (screenWidth - WINDOW_W) / 2;  // = 22
```

Change to:
```cpp
originX = 0;
```

All downstream coordinates are `originX`-relative — no other geometry
constants need changing. The PLEDIT hit-test (line 345) and all `blitSprite`
calls use `originX` as the base.

## Canvas constraint for non-Winamp apps

Apps other than Spotify render into the **app canvas**: x: 0..274, y: 116..239
(275×124). The Winamp chrome occupies y: 0..115 permanently. Apps must not
write outside this rectangle. The taskbar (x: 275..319) is off-limits to all
apps.

Exception: Clock, Matrix, GoL are visually distinct enough that they could
use the full 275×240 left canvas (overwriting the Winamp chrome region) if the
Winamp chrome is suspended. This is a future option — initial implementation
constrains all apps to 275×124.

## Orientation mismatch — 5in1 source apps

The 5in1 reference project (`resource/5in1`) targets **portrait** mode:
`tft.setRotation(0)`, 240 wide × 320 tall. All render coordinates in
Clock, Weather, Crypto, Matrix, and Game of Life are written for that
portrait canvas.

This device runs **landscape**: `tft.setRotation(1)`, 320 wide × 240 tall
(set in `cheapYellowLCD.h:90`). The app canvas available to ported apps is
**275 wide × 240 tall** (full left column) or **275 wide × 124 tall**
(below Winamp chrome only).

Neither canvas matches the 5in1 source dimensions. The 5in1 code must not
be used verbatim — coordinates and layout must be rewritten for landscape.

### Dimension mapping

| 5in1 portrait | Our landscape canvas (full left column) |
|---------------|----------------------------------------|
| width = 240   | height = 240  (matches)               |
| height = 320  | width = 275   (shorter by 45 px)      |

The portrait x-axis maps to our landscape y-axis; the portrait y-axis maps
to our landscape x-axis. Pixel counts do not transpose cleanly — each app's
render logic must be rewritten for the 275×240 (or 275×124) target rather
than mechanically transposing coordinates.

### Per-app notes

- **Clock** — small fixed layout; straightforward to re-layout for landscape.
- **Weather** — 2×2 grid of rounded rects; grid cell sizes need recalculation.
- **Crypto** — vertical list; fits naturally in landscape with adjusted column widths.
- **Matrix rain** — column count and glyph positions are x-driven; swap axes,
  adjust column count for 275 px width. `GRID_W` / column stride changes.
- **Game of Life** — `GRID_W=48, GRID_H=60` at 5 px/cell = 240×300 in portrait.
  For landscape 275×240: use `GRID_W=55, GRID_H=48` at 5 px/cell = 275×240.
  Grid state array dimensions change; state struct in app-lifecycle.md must
  be updated accordingly.

### TFT rotation setting

Do **not** change `tft.setRotation()` per app. The display stays at rotation 1
for all apps. Each app renders to landscape coordinates natively.

## Right-strip background

The taskbar background is baked as a 45×240 solid or textured rectangle at
init time. It is never cleared by the display driver's `tft.fillScreen()` —
that call is replaced by a constrained `tft.fillRect(0, 0, 275, 240, TFT_BLACK)`
in `switchApp()`.
