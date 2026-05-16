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

- Width 280: extra 5px on right is scrollbar track / unused.
- Height 186: shorter than canonical 232 — y=110..185 contains additional bottom-bar button states (4 × 19px groups), not used for normal rendering.
- Cyan `(0,198,255)` appears at y=20, 41, 71, 110, 129, 148, 167 — these are **palette fill pixels at band boundaries**, not structural separators. Winamp uses hardcoded y-offsets, not cyan detection.
- Title band still 20px (y=0..19), bottom bar still 38px (y=72..109) — canonical heights confirmed.

---

## Not in PLEDIT.BMP

- Individual track rows (no sprite)
- Row highlight sprite (no sprite — flat fill from PLEDIT.TXT)
- Currently-playing indicator icon
- Scrollbar thumb (separate widget, not in PLEDIT.BMP in Audacious)
