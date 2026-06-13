# M-PREVIEW-FRAMEWORK — Common preview tool framework

> Architect design doc · 2026-06-13
> Status: **done — implemented 2026-06-13** (TASK-192). One implementation note: `pygame.K_Q` does not exist in pygame; `PreviewWindow.handle_event` uses `pg.K_q`. Exit-criteria separator pixel corrected below.

---

## Problem

Six host-side preview tools in `app/tools/` duplicate the same geometry
constants, taskbar-rendering logic, icon loader, GIF writer, and pygame window
management. Every addition to the app list must be applied in three or more
places, and the duplicated taskbar implementations have already diverged (e.g.
`preview_heatmap.py` uses text labels instead of PNG icons, and its colour
constants differ from the other tools).

---

## Goal

Extract the shared code into a single `app/tools/preview_common.py` module.
After the migration:

- No tool defines its own copy of `SCREEN_W`, taskbar constants, or `write_gif`.
- The taskbar rendered by every tool is visually identical and driven from the
  same `APP_ORDER` source as the firmware (`app_ids_gen.py`).
- Adding a new app to `appRegistry.h` and re-running `gen_app_registry.py`
  requires zero changes to any preview tool (except tools for unreleased apps,
  which use the explicit override pattern documented below).

---

## Duplication map

The table below names the exact constant/function in each tool that `preview_common.py` will replace.

| Symbol | `preview_layout.py` | `preview_clock.py` | `preview_vis.py` | `preview_wave.py` | `preview_heatmap.py` | `preview_teletext.py` |
|--------|--------------------|--------------------|------------------|--------------------|----------------------|----------------------|
| `SCREEN_W`, `SCREEN_H` | L42-43 | (not defined; uses `_skin` parse) | L67-68 | (not defined) | L45-46 | L38-39 |
| `TASKBAR_X`, `TASKBAR_W` | L46-47 | (not defined) | (not defined) | (not defined) | L47-48 | L40-41 |
| `APP_W`, `APP_H` | (implicit) | (not defined) | (not defined) | (not defined) | L49-50 | L42-43 |
| `TASKBAR_SLOT_H` | L49 | `_TASKBAR_SLOT_H` L176 | (not used) | (not used) | `TASKBAR_SLOT_H` L75 | `_SLOT_H` L69 |
| `TASKBAR_SLOT_COUNT` | L48 | `_TASKBAR_SLOT_COUNT` L175 | (not used) | (not used) | `TASKBAR_SLOT_COUNT` L76 | `_SLOT_COUNT` L70 |
| `TASKBAR_ICON_W/H` | L50 | `_TASKBAR_ICON_W/H` L177-178 | (not used) | (not used) | (not used) | `_ICON_W/H` L71-72 |
| BG colour `(32,32,32)` | (in render) | `_TASKBAR_BG` L179 | (not used) | (not used) | `C_TASKBAR_BG (14,14,28)` L101 | `_TB_BG` L73 |
| Active colour `(0,255,0)` | (in render) | `_TASKBAR_ACTIVE_COL` L180 | (not used) | (not used) | `C_GREEN (0,155,0)` L96 | `_TB_ACTIVE` L74 |
| Sep colour `(64,64,64)` | (in render) | `_TASKBAR_SEP_COL` L181 | (not used) | (not used) | `C_TASKBAR_SEP (35,35,55)` L102 | `_TB_SEP` L75 |
| App name list | (not used) | `_APP_NAMES` L173-174 (9 apps) | (not used) | (not used) | hardcoded `["S","C","W","$","M","St"]` L589 | `_APP_NAMES` L78-79 (10 apps, Teletext appended) |
| `_load_icon()` | (not used) | L184-192 PIL | (not used) | (not used) | (not implemented — text only) | L388-398 pygame |
| `_draw_taskbar()` / `_render_taskbar()` / `draw_taskbar()` | (separate design-tool scope) | PIL L195-220 | (not used) | (not used) | PIL L586-608 (text labels) | pygame L400-414 |
| `write_gif()` | (not used) | (not used) | L308-322 | L52-66 | (not used) | (not used) |
| pygame `+/-` scale / `q` quit handler | N/A | per-tool | per-tool | N/A | per-tool | per-tool |

**Key divergences noted:**

- `preview_heatmap.py` uses `C_TASKBAR_BG = (14,14,28)` and `C_TASKBAR_SEP = (35,35,55)` — a dark navy palette instead of the firmware's `(32,32,32)` / `(64,64,64)`. After migration it will use the canonical values.
- `preview_heatmap.py` renders text labels `["S","C","W","$","M","St"]` instead of PNG icons and hardcodes only 6 apps with no scroll support.
- `preview_teletext.py` appends `"teletext"` to the app list manually (L78-79) because Teletext has not yet landed in `appRegistry.h`. This is the intended "unreleased app override" pattern.
- `preview_vis.py` and `preview_wave.py` do not render the taskbar at all — they render the WinampApp (which sits in a 275-wide sub-window) without a shell frame. They share only `write_gif()`.

---

## Module location

`app/tools/preview_common.py`

Same directory as the existing tools. Import with:

```python
from preview_common import (
    SCREEN_W, SCREEN_H, APP_W, APP_H, TASKBAR_X, TASKBAR_W,
    TASKBAR_SLOT_H, TASKBAR_SLOT_COUNT, TASKBAR_ICON_W, TASKBAR_ICON_H,
    TASKBAR_BG, TASKBAR_ACTIVE_COL, TASKBAR_SEP_COL,
    APP_ORDER, load_icon_pil, load_icon_pygame, draw_taskbar_pil, draw_taskbar_pygame,
    write_gif, PreviewWindow,
)
```

---

## Public API

### Constants

All values match the firmware's `gen/shell_layout.h` canonical values (M-SHELL-LAYOUT, done). (ADR-041 established `app_ids_gen.py` as canonical registry; `gen/shell_layout.h` established by M-SHELL-LAYOUT).

```
SCREEN_W  = 320      # total display width
SCREEN_H  = 240      # total display height
TASKBAR_X = 275      # x at which taskbar begins
TASKBAR_W = 45       # taskbar width in px
APP_W     = 275      # usable app canvas width  (0..274)
APP_H     = 240      # usable app canvas height (0..239)

TASKBAR_SLOT_H     = 40    # height of each taskbar slot in px (6 × 40 == 240)
TASKBAR_SLOT_COUNT = 6     # number of visible slots in the taskbar
TASKBAR_ICON_W     = 24    # icon width in px
TASKBAR_ICON_H     = 24    # icon height in px

TASKBAR_BG         = (32, 32, 32)    # slot background — matches 0x2104 RGB565
TASKBAR_ACTIVE_COL = (0, 255, 0)     # active-app indicator bar — matches 0x07E0 RGB565
TASKBAR_SEP_COL    = (64, 64, 64)    # slot separator line — matches 0x4208 RGB565
```

### `APP_ORDER`

```
APP_ORDER: list[str]
```

Re-exported from `app_ids_gen.py` (canonical registry established by M-APP-REGISTRY / ADR-041). Contains the 9 current app names in
registry order: `['Spotify', 'Clock', 'Weather', 'Crypto', 'Matrix', 'Life',
'Settings', 'Stock', 'Aquarium']`.

The module exports a copy: `APP_ORDER = list(app_ids_gen.APP_ORDER)`. Mutations to the exported list do not affect `app_ids_gen.APP_ORDER`.

Treat as read-only. The module provides a defensive copy, but tools for unreleased apps must use a separate local variable (e.g. `_APP_ORDER = APP_ORDER + ['Teletext']`) rather than mutating the module-level list.

The internal icon filename lookup lower-cases each name:
`"Spotify"` → `spotify.png` / `spotify_active.png`.

### `load_icon_pil(name, active) → Image.Image | None`

Load a PIL RGBA Image from `app/icons/taskbar/<name>[_active].png`.
Resizes to `(TASKBAR_ICON_W, TASKBAR_ICON_H)` using LANCZOS if the source is
a different size. Returns `None` if the file does not exist (fallback: no icon
rendered for that slot).

`name` is the lower-cased app name, e.g. `"spotify"`, `"teletext"`.

Result is **not cached** — callers that call in a tight loop (pygame
`draw_taskbar_pygame`) should pass `app_order` once per frame, not per slot.
Caching is an implementation detail left to the module; the public contract is
stateless from the caller's perspective.

### `load_icon_pygame(name, active) → pygame.Surface | None`

Pygame equivalent of `load_icon_pil`. Loads and scales via `pygame.image.load`
and `pygame.transform.scale`. Results are cached in a module-level dict keyed
by `(name, active)` — pygame Surface creation is expensive and called every
frame. Returns `None` if the file does not exist.

This function is the pygame counterpart that `preview_teletext.py`'s current
`_load_icon()` (L388-398) implements locally.

### `draw_taskbar_pil(img, active_app, scroll_offset=0, app_order=None) → None`

Draw the taskbar strip onto a PIL `Image` object in-place.

Parameters:
- `img` — PIL Image (mode `RGB` or `RGBA`), full 320×240.
- `active_app` — name of the currently active app, e.g. `"Clock"`. Case must
  match the entry in `app_order`. If the name is not found in the visible
  window, no active indicator is drawn.
- `scroll_offset` — index into `app_order` of the first visible slot.
  Visible slots are `app_order[scroll_offset % N]` through
  `app_order[(scroll_offset + TASKBAR_SLOT_COUNT - 1) % N]` (wrap-around,
  mirrors firmware `renderTaskbar` modulo logic).
- `app_order` — override list. If `None`, uses module-level `APP_ORDER`.
  Pass a list to support unreleased apps or test scenarios.

Implementation mirrors `preview_clock.py:_draw_taskbar()` (L195-220), which is
the reference implementation. Replaces:
- `preview_clock.py:_draw_taskbar()` L195-220
- `preview_heatmap.py:_render_taskbar()` L586-608

### `draw_taskbar_pygame(surface, active_app, scroll_offset=0, app_order=None) → None`

Pygame equivalent of `draw_taskbar_pil`. Draws directly into a `pygame.Surface`
object.

Parameters: identical semantics to `draw_taskbar_pil`.

Implementation mirrors `preview_teletext.py:draw_taskbar()` (L400-414).
Replaces `preview_teletext.py:draw_taskbar()`.

The two flavours exist because four tools render into a PIL Image (then optionally
convert to pygame for display), while `preview_teletext.py` renders directly
into a pygame Surface throughout. Providing both avoids forcing a PIL round-trip
on the teletext tool.

### `write_gif(frames, out_path, fps=20) → None`

Write a list of PIL Images as an animated GIF using median-cut quantisation.

Parameters:
- `frames` — `list[Image.Image]`, mode `RGB` or `RGBA`.
- `out_path` — `str | pathlib.Path` destination.
- `fps` — frames per second; converts to `duration_ms = round(1000 / fps)`.

Prints a one-line summary: path, size in KB, frame count, fps.

Replaces:
- `preview_vis.py:write_gif()` L308-322
- `preview_wave.py:write_gif()` L52-66

The two existing implementations are identical in structure. The only difference
is that `preview_vis.py` uses `FPS` (module constant) as default and `preview_wave.py`
uses `FPS = 20`. The common module fixes the default at 20 and callers pass
their own `fps` when they differ.

### Class `PreviewWindow(title, scale=2)`

Wraps a pygame display window for preview tools that render a scaled view of
the 320×240 device canvas.

**Constructor:**
- `title: str` — window caption.
- `scale: int` — initial scale factor; window is `(SCREEN_W * scale, SCREEN_H * scale)`.

**Properties:**
- `scale: int` — read/write. Setting this property recreates the pygame display
  surface at the new size.

**Methods:**

`handle_event(event) → bool`

Process a single pygame event. Handles:
- `+` / `=` key: increment `scale` (max 4), recreate surface. Returns `True`.
- `-` key: decrement `scale` (min 1), recreate surface. Returns `True`.
- `q` / `Q` / `pygame.QUIT`: calls `sys.exit(0)`. Never returns.
- Any other event: returns `False`.

Returning `True` signals the caller that the display size changed and it should
re-render immediately rather than skip the frame.

`blit_pil(img) → None`

Convert a PIL Image to a pygame Surface, scale it to `(SCREEN_W * scale,
SCREEN_H * scale)` using `pygame.transform.scale`, and blit it to the display
surface at `(0, 0)`. Does not call `pygame.display.flip()`.

`flip() → None`

Call `pygame.display.flip()`.

**Design note:** `PreviewWindow` deliberately does not own the render loop or
the event loop — those remain in each tool's `main()`. It only encapsulates the
window lifecycle, scale handling, and PIL→pygame conversion. This keeps the
class minimal and avoids entangling it with per-tool clock/timer logic.

**Headless import note:** `PreviewWindow.__init__` lazy-imports `pygame` (i.e. `import pygame` happens inside `__init__`, not at module level). This means tools that only use `write_gif` or `draw_taskbar_pil` can `from preview_common import write_gif` without triggering a `pygame` import, keeping the headless GIF-only path functional for `preview_vis.py` and `preview_wave.py`. Those two tools import `PreviewWindow` only inside the `--live` branch of `main()`, not at module level.

---

## Per-tool migration table

| Tool | Imports from `preview_common` | Drops | Stays |
|------|------------------------------|-------|-------|
| `preview_layout.py` | `SCREEN_W`, `SCREEN_H`, `TASKBAR_X`, `TASKBAR_W`, `TASKBAR_SLOT_H`, `TASKBAR_SLOT_COUNT`, `TASKBAR_ICON_W`, `TASKBAR_ICON_H`, `TASKBAR_BG`, `TASKBAR_ACTIVE_COL`, `TASKBAR_SEP_COL` | Its own constant definitions (L42-53 range). Does NOT import `draw_taskbar_pil` — this tool is the layout design tool and its taskbar rendering is intentionally separate (cycles styles, exports `shell_layout.h`). | bake-skin imports, `open_skin`, style-cycling logic, `--export` path, interactive param loop, `PreviewWindow` (deferred — `preview_layout.py`'s scale and event loop are tightly coupled to its style-cycling parameter model and export path; migrating to `PreviewWindow` is out of scope for M-PREVIEW-FRAMEWORK; it remains a standalone tool) |
| `preview_clock.py` | `SCREEN_W`, `SCREEN_H`, `TASKBAR_X`, `TASKBAR_W`, `APP_W`, `APP_H`, `TASKBAR_SLOT_H`, `TASKBAR_SLOT_COUNT`, `TASKBAR_ICON_W`, `TASKBAR_ICON_H`, `TASKBAR_BG`, `TASKBAR_ACTIVE_COL`, `TASKBAR_SEP_COL`, `APP_ORDER`, `load_icon_pil`, `draw_taskbar_pil`, `PreviewWindow` | `_TASKBAR_SLOT_COUNT` through `_TASKBAR_SEP_COL` (L175-181), `_APP_NAMES` (L173-174), `_ICONS_DIR` (L172), `_load_icon()` (L184-192), `_draw_taskbar()` (L195-220) | `ClockRenderer` ABC, `DigitalRenderer`, `FlipRenderer`, `NixieRenderer`, `VFDRenderer`, style dispatch, `--style`/`--freeze`/`--scale` CLI. **`active_app` mapping:** existing call sites `active_slot = style_key - 1` (L335, L345) are replaced by `active_app="Clock"` — the tool always displays clock styles, so the active app in the shell is always `"Clock"`. There is no concept of the active indicator tracking the clock sub-style. |
| `preview_vis.py` | `SCREEN_W`, `SCREEN_H`, `write_gif`, `PreviewWindow` | `write_gif()` (L308-322) | `_parse_skin_layout()`, `ORIGIN_X/Y`, vis-area constants, `VuBar`, spectrum engine, `VisRenderer`, `--live`/`--out`/`--mode` CLI. **Import note:** `PreviewWindow` is imported only inside the `--live` branch of `main()`, not at module level, preserving the headless GIF-only path. |
| `preview_wave.py` | `write_gif`, `PreviewWindow` | `write_gif()` (L52-66) | `WaveRenderer`, wave atlas loader, `--zoom`/`--out` CLI. **Import note:** `PreviewWindow` is imported only inside the `--live` branch of `main()`, not at module level, preserving the headless GIF-only path. |
| `preview_heatmap.py` | `SCREEN_W`, `SCREEN_H`, `TASKBAR_X`, `TASKBAR_W`, `APP_W`, `APP_H`, `TASKBAR_SLOT_H`, `TASKBAR_SLOT_COUNT`, `TASKBAR_BG`, `TASKBAR_ACTIVE_COL`, `TASKBAR_SEP_COL`, `APP_ORDER`, `load_icon_pil`, `draw_taskbar_pil`, `PreviewWindow` | `TASKBAR_SLOT_H` (L75), `TASKBAR_SLOT_COUNT` (L76), `C_TASKBAR_BG` (L101), `C_TASKBAR_SEP` (L102), `C_GREEN` active-indicator use in `_render_taskbar`, `_render_taskbar()` (L586-608) | `HeatmapPoc`, all stock-specific colours and geometry constants, Yahoo Finance fetch logic, treemap layout, chart renderer, `dut_fonts` usage |
| `preview_teletext.py` | `SCREEN_W`, `SCREEN_H`, `TASKBAR_X`, `TASKBAR_W`, `APP_W`, `APP_H`, `TASKBAR_SLOT_H` (as `_SLOT_H`), `TASKBAR_SLOT_COUNT` (as `_SLOT_COUNT`), `TASKBAR_ICON_W` (as `_ICON_W`), `TASKBAR_ICON_H` (as `_ICON_H`), `TASKBAR_BG` (as `_TB_BG`), `TASKBAR_ACTIVE_COL` (as `_TB_ACTIVE`), `TASKBAR_SEP_COL` (as `_TB_SEP`), `APP_ORDER`, `load_icon_pygame`, `draw_taskbar_pygame`, `PreviewWindow` | `_SLOT_H` through `_TB_SEP` (L69-75), `_ICONS_DIR` (L76), `_APP_NAMES` base definition (L78-79; retained only for `+ ["teletext"]` override call), `_icon_cache` dict (L386), `_load_icon()` (L388-398), `draw_taskbar()` (L400-414) | Teletext page parser, mosaic renderer, `draw_page()`, `draw_nav_strip()`, `draw_fasttext_bar()`, `Keypad` widget, navigation state, NOS HTTP fetch, `_triangle()`, all teletext-specific geometry constants (`CHAR_W`, `CHAR_H`, `COLS`, `ROWS`, `STRIP_*`, etc.) |

**Note on `preview_heatmap.py` colour divergence:** The current `C_TASKBAR_BG = (14,14,28)` and `C_TASKBAR_SEP = (35,35,55)` are local design choices that do not match the firmware. After migration, `preview_heatmap.py` will use `TASKBAR_BG = (32,32,32)` and `TASKBAR_SEP_COL = (64,64,64)` from `preview_common`, making the heatmap preview's taskbar visually consistent with all other tools. This is the desired outcome.

**Note on `preview_heatmap.py` active-indicator visibility:** After migration, the active-indicator for Stock will be invisible at `scroll_offset=0` because Stock is at `APP_ORDER` index 7, outside the 6-slot visible window. `preview_heatmap.py` should use `scroll_offset = APP_ORDER.index('Stock') - (TASKBAR_SLOT_COUNT - 1)` = 2, which positions Stock in the last visible slot, matching the pre-migration behaviour.

---

## app_order extension pattern

Tools for unreleased apps (apps not yet in `appRegistry.h`) append their entry
and pass the result as `app_order` to the taskbar renderers.

Pattern (illustrated for Teletext, which is not yet in `appRegistry.h`):

```python
from preview_common import APP_ORDER, draw_taskbar_pygame

# Teletext not yet in appRegistry.h — append manually until it lands.
_APP_ORDER = APP_ORDER + ["Teletext"]

# In the render path:
draw_taskbar_pygame(canvas, active_app="Teletext",
                   scroll_offset=_tb_scroll, app_order=_APP_ORDER)
```

Once the app lands in `appRegistry.h` and `gen_app_registry.py` is re-run,
the tool drops its local `_APP_ORDER` override and the import picks up the new
`APP_ORDER` automatically.

The `load_icon_pygame` / `load_icon_pil` functions look up
`app/icons/taskbar/<lower(name)>.png`. The icon files must exist before the
tool renders correctly, but missing icons degrade gracefully (slot renders
without an icon, not a crash).

---

## Scroll-offset and active-indicator invariants

These invariants mirror the firmware `renderTaskbar(tft, activeApp, scrollOffset, totalApps)`:

1. **Visible window.** The taskbar shows exactly `TASKBAR_SLOT_COUNT = 6` slots.
   Slot `i` (0-indexed from top) corresponds to `app_order[(scroll_offset + i) % N]`
   where `N = len(app_order)`.

2. **Active indicator.** A 3 px green bar is drawn on the left edge of the slot
   whose app index equals `app_order.index(active_app)`. If the active app is
   not in the current visible window (it scrolled out), no indicator is drawn.

3. **`scroll_offset` is a caller concern.** `preview_common` renderers do not
   mutate or store `scroll_offset` — they accept it as a parameter each call.
   Each tool maintains its own scroll state variable (e.g. `_TB_SCROLL` in
   `preview_teletext.py`) and passes it at render time.

4. **`APP_ORDER` is read-only.** No tool may mutate the module-level `APP_ORDER`.
   Derived lists (with appended unreleased apps) must be separate local variables.

5. **Separator lines.** A horizontal separator is drawn at the bottom edge of each slot except the last (slot `TASKBAR_SLOT_COUNT - 1`). No separator is drawn at the absolute bottom of the taskbar strip.

---

## Exit criteria

All four conditions must be true before M-PREVIEW-FRAMEWORK is marked done:

1. `app/tools/preview_common.py` exists and exports the full public API described above.
2. All 6 tools (`preview_layout.py`, `preview_clock.py`, `preview_vis.py`,
   `preview_wave.py`, `preview_heatmap.py`, `preview_teletext.py`) import their
   shared symbols from `preview_common` and contain no local redefinition of
   `SCREEN_W`, taskbar constants, or `write_gif`. Verified by:
   - `grep -rn "^\s*\(SCREEN_W\|SCREEN_H\|TASKBAR_X\|TASKBAR_W\|APP_W\|APP_H\|TASKBAR_SLOT_H\|TASKBAR_SLOT_COUNT\|TASKBAR_ICON_W\|TASKBAR_ICON_H\|TASKBAR_BG\|TASKBAR_ACTIVE_COL\|TASKBAR_SEP_COL\)\s*=" app/tools/preview_*.py` returns zero hits (excluding comment lines).
   - `grep -n "^def write_gif" app/tools/preview_vis.py app/tools/preview_wave.py` returns zero hits.
   - `python3 -c "from preview_common import SCREEN_W, SCREEN_H, APP_W, APP_H, TASKBAR_X, TASKBAR_W, TASKBAR_SLOT_H, TASKBAR_SLOT_COUNT, TASKBAR_ICON_W, TASKBAR_ICON_H, TASKBAR_BG, TASKBAR_ACTIVE_COL, TASKBAR_SEP_COL, APP_ORDER, load_icon_pil, load_icon_pygame, draw_taskbar_pil, draw_taskbar_pygame, write_gif, PreviewWindow"` succeeds from `app/tools/`.
3. Each tool launches and renders correctly after migration (manual smoke test:
   run each tool, confirm the taskbar is visible and visually identical to the
   pre-migration baseline for tools that render it, confirm GIF output for
   `preview_vis.py` and `preview_wave.py`).
4. `preview_heatmap.py`'s taskbar uses PNG icons (not text labels) with the
   canonical `(32,32,32)` / `(64,64,64)` palette after migration, and uses
   `scroll_offset=2` so Stock appears in slot 5 (last visible slot) with the
   active indicator visible. Verified by sampling `canvas.getpixel((275, 0)) == (32, 32, 32)`
   (BG), `canvas.getpixel((275, 40)) == (64, 64, 64)` (separator — between slot 0 and slot 1;
   reference implementations draw at y=y0+SLOT_H, not y=y1), and
   `canvas.getpixel((275, 5*40+1)) == (0, 255, 0)` (active indicator in slot 5).

---

## Pre-implementation gate

Before Developer begins coding `preview_common.py`, Architect confirms:
- Duplication map line numbers match current source (run `grep -n` checks against live files for any symbols that may have shifted since this doc was written).
- `app/icons/taskbar/` contains PNG files for all apps in `APP_ORDER` (required for `load_icon_pil` / `load_icon_pygame` to return non-None for those slots).
