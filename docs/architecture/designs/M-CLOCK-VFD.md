# M-CLOCK-VFD — VFD Dot-Matrix Clock Renderer Physics

> Owner: Architect  
> Status: POC done — Phase 3 (firmware) not started  
> Date: 2026-06-13  
> Part of: [M-CLOCK-STYLES.md](M-CLOCK-STYLES.md) — Style 3  
> See also: [clock.md](M-MULTIAPP/clock.md), [M-SETTINGS-APP-WIRE.md](M-SETTINGS-APP-WIRE.md)

---

## Status summary

| Layer | State |
|-------|-------|
| Host renderer | **Done** — `app/tools/_clock_vfd.py` (`VFDRenderer`) |
| Preview tool | **Done** — `app/tools/preview_clock.py --style vfd` |
| Glyph system | **Done** — Dexter v2 (`_dex()` + `_GLYPHS`) |
| Colour themes | **Done in POC** — 4 themes, `c` key cycles; settings wiring pending |
| Firmware renderer | Not started |

---

## Purpose

Detailed render physics for the VFD (Vacuum Fluorescent Display) clock style.
The milestone structure, style enum, dispatch, and settings wiring live in
`M-CLOCK-STYLES.md`. This doc covers the rendering model, grid geometry, glyph
system, bloom pipeline, colour themes, and firmware path that the implementation
must follow.

---

## Visual concept

Classic VFD calculator / cassette deck display (Pioneer stereo, Denon deck).
Dark navy background. Phosphor dot-matrix digits — active dots emit strongly,
inactive dots show faint ambient glow. Adjacent active dots accumulate glow at
their shared boundary.

```
  ┌─────────────────────────────────────────────────────────┐
  │  ░░░░  ░░░░ ░░░░░░ ░░░░  ░░░░  ← bright active dots    │
  │  ░  ░  ░  ░   ░   ░  ░  ░  ░                           │
  │  ░░░░  ░░░░   ░   ░░░░  ░░░░  ← dim inactive dots      │
  │                                                         │
  │            ▓ ▓▓▓ ▓▓ ▓▓▓ ▓▓▓▓  ← date lines             │
  └─────────────────────────────────────────────────────────┘
         dark navy bg  (0, 5, 18)
```

Default colour theme: **teal** — `(0, 210, 230)` active, `(0, 13, 14)` inactive.

---

## Rendering model — fundamental constraint

> **The display is a continuous rasterized phosphor surface, not a set of
> isolated glowing dots.** Every rendering decision follows from this.

**Wrong approach**: draw each active dot with its own per-dot glow halo.
Creates halos that overwrite each other, non-uniform brightness, looks artificial.

**Correct approach: rasterize first, blur second, composite additively.**

```
Step 1 — Grid pass (rasterize, no glow)
  sharp_buf ← C_BG fill
  For every cell in the 54×24 unified grid:
    if active:   paint C_ON  flat rect (no glow)
    if inactive: paint C_OFF flat rect
  → sharp_buf: clean sharp dot grid, zero glow

Step 2 — Bloom pass
  bloom = GaussianBlur(sharp_buf, radius=BLOOM_R)
  bloom = bloom × BLOOM_SCALE  (additive brightness multiplier)

Step 3 — Composite (additive)
  output = ImageChops.add(sharp_buf, bloom)
```

**Why additive, not alpha-composite?**
Real phosphor emits light. `ImageChops.add` (capped at 255) is the correct
blend mode. Clusters of adjacent active dots accumulate stronger glow at shared
boundaries — physically accurate and visually correct.

**Why blur the whole grid, not just active dots?**
Off-dots are `C_OFF` (≤6% of C_ON). Their blur contribution is negligible.
Blurring the full grid is simpler and produces authentic faint ambient glow from
even inactive dots.

---

## Grid geometry — unified time matrix

One 54-column × 24-row grid covers the full time area. Digits share the grid;
inter-digit gaps are ordinary off-dot columns.

```
GRID_COLS = 54
GRID_ROWS = 24
TC = 4    (dot cell size, px)
TG = 1    (gap between dots, px)
TS = 5    (stride = TC + TG)

GRID_X0 = 3   (left margin px)
GRID_Y0 = 10  (top of time matrix, px from canvas top)

Total width check: 3 + 54×5 − 1 + 3 = 275 px ✓

Column layout:
  cols  0- 1  left margin  (2 off-cols)
  cols  2-12  H1 glyph     (11 active cols)
  col  13     H1/H2 gap    (1 off-col)
  cols 14-24  H2 glyph
  cols 25-28  colon area   (dots at col 26, rows 7-8 and 15-16, each 2×2 cells)
  cols 29-39  M1 glyph
  col  40     M1/M2 gap    (1 off-col)
  cols 41-51  M2 glyph
  cols 52-53  right margin (2 off-cols)
```

Grid pixel heights:
```
DIGIT_H = 24×4 + 23×1 = 119 px
```

Glyph inner region within the 24-row grid (Dexter v2 active area):
```
GLYPH_W          = 11   (active glyph columns)
GLYPH_H          = 22   (active glyph rows)
GLYPH_ROW_OFFSET =  1   (1-dot top margin above glyph; bottom row = off)
```

Colon: 2×2-cell dots (9×9 px rendered) at grid col 26, blinks at 0.5 Hz:
```
upper dot: grid rows  7-8,  col 26-27
lower dot: grid rows 15-16, col 26-27
```

---

## Glyph system — Dexter v2

Dexter v2 is the default and only digit font. Procedurally generated from a
7-segment-inspired design vocabulary. All glyphs are 11-col × 22-row bitmaps
derived from segment fill rules, not hand-coded row bitmaps.

### Segment definitions

```
T  bar:  rows  0- 1,  cols 2-8   (inset, 7 wide)
M  bar:  rows 10-11,  cols 2-8
B  bar:  rows 20-21,  cols 2-8
UL vert: rows  0-11,  cols 0-1   (2 wide)
UR vert: rows  0-11,  cols 9-10
LL vert: rows 10-21,  cols 0-1
LR vert: rows 10-14,  cols 9-10  (2 wide, upper section)
         rows 15-21,  cols 8-10  (3 wide, lopsided flare at bottom 7 rows)
```

Chamfers: single dot removed at each outer 90° corner where two segments meet
(TL, TR, BL, BR). Gives rounded feel without bezier curves.

### Digit table

| Digit | Segments | Notes |
|-------|----------|-------|
| 0 | T UL UR LL LR B | |
| 1 | — | centred 2-wide stem, serif cap, B base — bespoke |
| 2 | T UR M LL B | |
| 3 | T UR M LR B | |
| 4 | UL UR M LR | |
| 5 | T UL M LR B | |
| 6 | T UL M LL LR B | |
| 7 | — | T bar + UR + diagonal step at rows 11-14 + lopsided lower — bespoke |
| 8 | T UL UR M LL LR B | |
| 9 | T UL UR M LR B | |

Row bit encoding: `bit 10 = col 0` (left), `bit 0 = col 10` (right).
22 rows × 11 cols → 22 `uint16_t` words per glyph → 10 glyphs × 22 × 2 = 440 bytes firmware flash cost.

### Source of truth

`app/tools/_clock_vfd.py` → `_GLYPHS` list (generated by `_dex()` at import time).
For firmware, run `app/tools/gen_vfd_glyphs.py` (to be written in Phase 3) to
emit a `vfd_glyphs.h` C header with the same 10 glyph arrays.

---

## Date rendering

Two lines below the time grid:
```
Line 1:  day abbreviation  "MON".."SUN"
Line 2:  date string       "DD MMM YYYY"

block_top = GRID_Y0 + DIGIT_H + 12 = 10 + 119 + 12 = 141 px
line_gap  = 10 px
```

Font: **Font1** (5×7 GLCD — exact TFT_eSPI Font1 bitmaps via `dut_fonts.py`).
Rendered as 2×2 px dot cells at 3 px stride (DC=2, DG=1, DS=3).
Brightness: `C_DATE = C_ON × 0.68` (slightly dimmer than time digits).

Both date lines are rasterized into `sharp_buf` before the bloom pass — bloom
naturally spreads them.

---

## Bloom parameters

| Param | Symbol | Implemented value | Role |
|-------|--------|------------------|------|
| Blur radius | `BLOOM_R` | 4.0 px | Glow spread |
| Scale factor | `BLOOM_SCALE` | 1.2 | Additive layer intensity |

`BLOOM_SCALE > 1.0` deliberately over-brightens the bloom layer before the
additive composite. Active dots saturate toward white at their core; off-dots
receive visible spill. This matches real VFD phosphor behaviour.

Phase 0 key controls: `g`/`G` steps BLOOM_SCALE ±0.05; `r`/`R` steps BLOOM_R ±0.2.

---

## Colour themes

Four themes are implemented in the POC. **Teal is the default.**

| Index | Name | C_ON (RGB) | Character |
|-------|------|-----------|-----------|
| 0 | teal (default) | `(0, 210, 230)` | Classic VFD cyan-green |
| 1 | amber | `(230, 160, 0)` | Nixie-adjacent warmth |
| 2 | blue | `(60, 120, 255)` | Cold hi-fi look |
| 3 | green | `(0, 220, 80)` | Monochrome terminal |

Derived colours (all computed from C_ON at runtime):
```
C_OFF  = C_ON × off_frac      # inactive dot; off_frac per contrast mode
C_DATE = C_ON × 0.68          # date lines
C_BG   = (0, 5, 18)           # fixed dark navy — same for all themes
```

Contrast modes (secondary setting, optional exposure):

| Mode | off_frac | Character |
|------|---------|-----------|
| standard | 0.06 | Bloom fills gaps; authentic VFD look |
| high | 0.00 | Fully black gaps, maximum bloom drama |
| low | 0.14 | Visible grid texture, less bloom drama |

### Settings wiring

Colour theme is exposed as a user-selectable option in Settings > Applications > Clock.

Add to `AppSettings`:
```cpp
uint8_t vfdTheme;   // 0=teal 1=amber 2=blue 3=green
```

`appsSection.h` cycles `vfdTheme` on tap (only visible when `clockStyle == VFD`):
```cpp
void _repaintVFDTheme() {
    static const char* kT[] = { "teal","amber","blue","green" };
    drawRow(S_CONTENT_Y + ROW_H, { "VFD Colour", kT[g_settings.vfdTheme % 4], S_LABEL, S_VALUE });
}
void _cycleVFDTheme() {
    g_settings.vfdTheme = (g_settings.vfdTheme + 1) % 4;
    saveSettings();
    repaint();
}
```

Contrast mode is **not** exposed to the user in v1. Ship standard mode only;
revisit if there is feedback.

---

## Render pipeline — implementation (host, PIL)

```python
def render(img: Image.Image, t: time.struct_time) -> None:
    C_ON, C_OFF, C_DATE = _palette()

    # Step 1 — sharp grid (no glow)
    sharp = Image.new("RGB", (CANVAS_W, CANVAS_H), C_BG)
    d     = ImageDraw.Draw(sharp)
    _rasterize_time_matrix(d, h1, h2, m1, m2, colon_on, C_ON, C_OFF)
    _rasterize_date_str(d, day_str,  x0, block_top,          C_DATE, C_OFF)
    _rasterize_date_str(d, date_str, x0, block_top + line_h, C_DATE, C_OFF)

    # Step 2 — bloom
    bloom = sharp.filter(ImageFilter.GaussianBlur(radius=BLOOM_R))
    bloom = bloom.point(lambda x: int(x * BLOOM_SCALE))

    # Step 3 — additive composite
    out = ImageChops.add(sharp, bloom)
    img.paste(out, (0, 0))
```

Full implementation: `app/tools/_clock_vfd.py`. Standalone test:
```sh
python3 app/tools/_clock_vfd.py   # → /tmp/vfd_{1_sharp,2_bloom,3_out}.png
```

---

## Firmware renderer (Phase 3)

TFT_eSPI has no Gaussian blur. Three options, in preference order:

### Option A — Pre-baked glyph sprites (recommended)

For each of the 10 digits × 4 colour themes: pre-compute a `uint16_t[]` sprite
(64×119 px, RGB565) with bloom burned in. Store in flash.

- Flash cost: 10 glyphs × 4 themes × 64 × 119 × 2 bytes ≈ 610 KB.
  With PSRAM this is acceptable; without PSRAM, limit to the active theme only
  and re-bake on theme change (~61 KB for one theme, loads in < 1 s from flash).
- Render call: `tft.pushImage(x, GRID_Y0, 64, 119, sprite_ptr)` per digit.
- Date line: rasterized at runtime (22-char max × 5×7 glyph = cheap).

### Option B — Per-row neighbour halo (fallback)

After the sharp grid pass, iterate each row. For each active dot, paint dim
`C_OFF_HALO` rectangles into the four adjacent cells. One pass, O(rows × cols).
Cheaper but less uniform than Option A.

### Option C — Sharp dots only (minimal)

Ship without bloom. Authentic to some real VFD hardware (Sony Watchman,
early Casio calculators had minimal bloom). The concept tool shows the ideal;
firmware is a budget approximation.

**Decision**: defer to Phase 3. Option A preferred if PSRAM available.
Emit `gen/vfd_sprites_<theme>.h` from `app/tools/gen_vfd_sprites.py`
(to be written); sprites are build artefacts, not checked in.

---

## Relationship to M-CLOCK-STYLES.md

`M-CLOCK-STYLES.md` owns:
- Phase 0 concept tool spec and approved constants block
- Style enum + dispatch stub
- Settings wiring skeleton
- Exit criteria C6

This doc owns:
- Rendering model and pipeline
- Unified grid geometry
- Dexter v2 glyph system
- Date dot-matrix geometry
- Bloom parameter definitions
- Colour themes and settings wiring detail
- Firmware renderer options

When Phase 0 `p`-key approved constants are recorded, they are copied into both
the Approved Constants block in `M-CLOCK-STYLES.md` and the parameter tables above.
