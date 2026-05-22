# PLEDIT.BMP Sprite Layout — Reference

**Source:** Audacious media player (Winamp 2.x skin-compatible open-source reimplementation)
- `src/skins/skin.cc` — `skin_draw_playlistwin_frame()` / `skin_draw_playlistwin_shaded()`
- `src/skins/playlist-widget.cc` — row rendering
- `src/skins/playlistwin.cc` — window assembly
- Repo: https://github.com/audacious-media-player/audacious-plugins

Fetched 2026-05-15 for ADR-018 Amendment 1 (TASK-047a correction).

---

## PLEDIT.BMP — Band layout (canonical 275×232, y axis)

| y range | Content | Notes |
|---|---|---|
| y=0..19 (20px) | **Title bar — focused** | Left corner (0,0,25,20), center tile (26,0,100,20), right corner (153,0,25,20) |
| y=21..40 (20px) | **Title bar — unfocused** | Same x layout, y=21 |
| y=42..70 (29px) | **Frame sides** | Left tile (0,42,12,29), right tile (32,42,19,29). Also shade-mode titlebar within this band. |
| y=72..109 (38px) | **Frame bottom bar** | Left/menu crop (0,72,125,38), right/buttons crop (126,72,150,38) |

Standard BMP is 275×232. The remaining rows (y=110+) contain additional button states or scrollbar elements not used in normal rendering.

### Frame Top sprite coordinates

`y = focused ? 0 : 21`

| Element | x | y | w | h |
|---|---|---|---|---|
| Left corner | 0 | y | 25 | 20 |
| Centre (tiling) | 26 | y | 100 | 20 |
| Right corner | 153 | y | 25 | 20 |
| Tile repeat unit | 127 | y | 25 | 20 |

### Frame Bottom sprite coordinates

| Element | x | y | w | h |
|---|---|---|---|---|
| Left (menu/ADD/REM/SEL…) | 0 | 72 | 125 | 38 |
| Right (scroll/close btns) | 126 | 72 | 150 | 38 |

### Frame Side sprite coordinates (for tiling between title and bottom)

| Element | x | y | w | h |
|---|---|---|---|---|
| Left tile | 0 | 42 | 12 | 29 |
| Right tile | 32 | 42 | 19 | 29 |

---

## Row Rendering — NO BMP SPRITES

Rows are rendered **entirely with flat fillRect + text**. Source: `playlist-widget.cc`.

```
// Normal row background:
set_cairo_color(cr, skin.colors[SKIN_PLEDIT_NORMALBG]);
cairo_paint(cr);

// Selected row highlight:
// cairo_rectangle() + cairo_fill() with SKIN_PLEDIT_SELECTEDBG
```

Colors come from PLEDIT.TXT:
- `Normal=` → text color for non-active tracks
- `Current=` → text color for currently-playing track
- `NormalBG=` → row background fill
- `SelectedBG=` → selected row background fill

**PLEDIT.BMP is NOT used for row backgrounds at any point.**

---

## Window Assembly (from playlistwin.cc)

Track list widget positioned at `(12, 20)` within the frame:
- `x=12`: width of left side tile
- `y=20`: height of title bar

Track list size: `(window_width - 31, window_height - 58)`
- `31 = 12 (left tile) + 19 (right tile)`
- `58 = 20 (title bar) + 38 (bottom bar)`

Row height: **font-driven** (`m_row_height = max(font_pixel_height, 1)`). No hardcoded row height constant in Winamp. Typical values with Winamp's default bitmap fonts: ~13–16 px depending on font size setting.

---

## base-2.91.wsz — Empirical deviations from 275×232 canonical

The skin used in this project (`base-2.91.wsz`) has `PLEDIT.BMP` at **280×186** (not 275×232). Observed with `_decode_bmp_rle8` + Pillow inspection.

- Width 280: extra 5px on right is scrollbar track / unused (see Extra Strip section below).
- Height 186: shorter than canonical 232 — y=110..185 contains additional bottom-bar button states (4 × 19px groups), not used for normal rendering.
- Cyan `(0,198,255)` appears at y=20, 41, 71, 110, 129, 148, 167 — these are **palette fill pixels at band boundaries**, not structural separators. Winamp uses hardcoded y-offsets, not cyan detection.
- Title band still 20px (y=0..19), bottom bar still 38px (y=72..109) — canonical heights confirmed.

---

## Extra strip — x=260..279 (2026-05-22 empirical, bake_skin.py pixel scan)

The extra 20px at x=260..279 contains content only in two bands:

| y range | Content |
|---------|---------|
| y=0..37 (38px) | Blue-dotted scrollbar track texture — dark background with alternating blue dots; solid blue row near bottom. Not used in normal rendering; not extracted by `bake_skin.py`. |
| y=72..109 (38px) | Continuation of the bottom-bar right section (scroll buttons area). Contributes to the scrollbar arrow buttons visible in the bottom bar. |
| y=38..71, y=110..185 | Background only (transparent key `(0,198,255)`). |

The dotted-blue track texture at y=0..37 is an **alternate scrollbar track style** not rendered in the standard PLEDIT frame. It does not contain a separate thumb sprite. Normal rendering uses `SKIN_PLEDIT_RIGHT_SIDE` (x=32..50, y=42..70) as the scrollbar track visual.

---

## Scrollbar thumb — confirmed synthesised (2026-05-22)

Pixel scan of all PLEDIT.BMP regions confirmed: **no scrollbar thumb sprite exists in the BMP**. Audacious draws the thumb as a synthetic filled rectangle over the track tile.

### Implementation specification (for TASK-051e)

The right-side frame tile (`SKIN_PLEDIT_RIGHT_SIDE`, 19×29, tiled vertically) provides the scrollbar track visual. The thumb is a `fillRect` overlay:

| Parameter | Value |
|-----------|-------|
| Thumb width | 17px (`PLEDIT_SIDE_RIGHT_W - 2` for 1px border each side) |
| Thumb height | `max(5, PLEDIT_ROW_COUNT * track_h / count)` where `track_h = PLEDIT_ROW_COUNT * PLEDIT_ROW_H = 65px` |
| Thumb X | `originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + 1` |
| Thumb Y | `PLEDIT_ROWS_Y + scrollOffset * (track_h - thumb_h) / max(1, count - PLEDIT_ROW_COUNT)` |
| Thumb fill colour | `0x6B4F` (RGB565 of `(106,106,122)`) — the lighter stripe in the right-side tile |
| Hide condition | `count <= PLEDIT_ROW_COUNT` — no scroll possible, no thumb drawn |

These colours derive from `SKIN_PLEDIT_RIGHT_SIDE`'s own palette so the thumb blends with the track tile:
- `(41, 41, 64)` = `0x2948` — dominant dark fill (406/551px)
- `(106, 106, 122)` = `0x6B4F` — light stripe (87/551px) → **thumb fill**
- `(29, 29, 45)` = `0x18E5` — background

---

---

## Scroll arrow buttons — measured 2026-05-22 (TASK-075)

Located at the far right of the bottom bar right section.  
Source atlas: `right_sec` crop from PLEDIT.BMP pasted at atlas x=125; x-mapping: `atlas_x = BMP_x − 1`.

### Sprite coordinates in PLEDIT.BMP

| Element | BMP x | BMP y | w | h | Notes |
|---------|-------|-------|---|---|-------|
| Scroll-UP button | 254..274 | 72..78 | 21 | 7 | Entire button zone (normal state) |
| Scroll-DOWN button | 254..274 | 79..88 | 21 | 10 | Entire button zone (normal state) |
| UP glyph (▲ pixels) | 261..268 | 74..77 | 8 | 4 | Light-gray upward triangle within button |
| DOWN glyph (▼ pixels) | 261..268 | 80..83 | 8 | 4 | Light-gray downward triangle within button |

Glyph color: `(106, 106, 122)` = `0x6B4F` (same shade as scrollbar thumb fill).

The UP▲ glyph widens from 2px (tip at y=74) to 8px (base at y=77).  
The DOWN▼ glyph narrows from 8px (base at y=80) to 2px (tip at y=83).

**No pressed-state sprites** — PLEDIT.BMP y=110..185 bands are entirely transparent (cyan) in this column for base-2.91.wsz. Pressed feedback must be synthesised if desired.

The diagonal staircase at x=261..269, y=91..103 (visible below the buttons) is decorative skin artwork — not a clickable element. Not used by the renderer.

### Screen hitzone coordinates (originX=22, PLEDIT_BOTTOM_Y=201)

| Zone | Screen x | Screen y | w | h | Action |
|------|----------|----------|---|---|--------|
| Scroll-UP tap | 275..296 | 201..207 | 22 | 7 | scrollOffset− (scroll toward start) |
| Scroll-DOWN tap | 275..296 | 208..217 | 22 | 10 | scrollOffset+ (scroll toward end) |
| UP glyph center | 282..289 | 203..206 | 8 | 4 | (glyph only, for reference) |
| DOWN glyph center | 282..289 | 209..212 | 8 | 4 | (glyph only, for reference) |

Note: these buttons are small for touch input (7–10px tall). If the CYD touchscreen precision is insufficient, expand the tap zones to split the full 38px bottom bar height equally (19px each: y=201..219 for UP, y=220..238 for DOWN).

### Standalone vs drag

Scroll arrows are **standalone tappable zones** — each tap scrolls the playlist by exactly 1 item. They complement but do not replace Zone 2 (direct drag on the right-side scrollbar strip). Wiring is tracked in TASK-051i.

---

## Not in PLEDIT.BMP

- Individual track rows (no sprite)
- Row highlight sprite (no sprite — flat fill from PLEDIT.TXT)
- Currently-playing indicator icon
- Scrollbar thumb (confirmed absent 2026-05-22 — synthesised via `fillRect`, see above)
- Scroll arrow pressed state (absent in base-2.91.wsz — see Scroll arrow buttons section above)
