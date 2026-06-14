# M-CLOCK-NIXIE — Nixie Tube Clock Renderer Physics

> Owner: Architect  
> Status: Phase 0 POC — digit mechanism approved, clock/date layout open for iteration  
> Date: 2026-06-14  
> Part of: [M-CLOCK-STYLES.md](M-CLOCK-STYLES.md) — Style 2  
> See also: [clock.md](M-MULTIAPP/clock.md), [M-SETTINGS-APP-WIRE.md](M-SETTINGS-APP-WIRE.md)

---

## Status summary

| Layer | State |
|-------|-------|
| Concept analysis | **Done** — physics doc from `resource/nixieclock_concept.jpg.png` |
| Host renderer | **Done** — `app/tools/_clock_nixie.py` (`NixieRenderer`) |
| Preview tool | **Done** — `app/tools/preview_clock.py --style nixie` |
| Glyph system | **Done** — Roboto-Thin 88 pt; ghost cathodes implemented (off by default) |
| Colour themes | **Done in POC** — 4 themes, `c` key cycles; settings wiring pending |
| Colon afterglow | **Done** — 1 Hz blink, 80 ms ramp-up, 500 ms exponential decay |
| Clock/date layout | **Open — iteration needed** — see open items below |
| Firmware renderer | Not started |

---

## Purpose

Detailed render physics for the Nixie Tube clock style.
The milestone structure, style enum, dispatch, and settings wiring live in
`M-CLOCK-STYLES.md`. This doc covers the tube housing model, wire cathode
glyph system, multi-pass bloom pipeline, ghost cathode effect, colour themes,
and firmware path.

---

## Visual concept

Classic Nixie vacuum tube display (Burroughs B-5750, ZM1042 style).
Black background. Each digit lives inside a tall dark capsule — the glass tube
envelope. Behind the glass: a very faint hexagonal wire-mesh anode grid.
Active digit cathode wire glows bright warm orange; glow accumulates into a
soft cloud that fills much of the tube interior.

```
  ┌──────────────────────────────────────────────────────────────┐
  │  ╭────╮  ╭────╮        ╭────╮  ╭────╮                       │
  │  │ ░░ │  │░░░░│  •  •  │░░░ │  │░░░░│  ← glowing wire digit │
  │  │░  ░│  │   ░│        │░   │  │░   │                        │
  │  │░  ░│  │  ░░│        │░░░░│  │░░░░│  ← hex mesh behind     │
  │  │ ░░ │  │░░  │        │   ░│  │   ░│                        │
  │  ╰────╯  ╰────╯        ╰────╯  ╰────╯                        │
  │                THU  12 JUN 2026                               │
  └──────────────────────────────────────────────────────────────┘
               near-black bg  (0, 0, 0)
```

Default colour theme: **amber** — wire core `(255, 125, 8)`, bloom tint deep orange.

---

## Rendering model — fundamental constraint

> **A Nixie tube is a glowing wire seen through glass and a wire-mesh anode.
> Every rendering decision follows from this.**

**Wrong approach**: draw a filled digit glyph and blur it.
Filled shapes produce uniform rectangular blobs, not the wire-fire look.

**Correct approach: render thin wire strokes, bloom them in multiple passes,
composite additively inside a tube mask.**

```
Step 1 — Tube background (per tube)
  tube_buf ← warm near-black fill
  paint hexagonal mesh dots at very low contrast

Step 2 — Wire glyph (per tube)
  wire_buf ← black
  draw digit using thin-weight font at WIRE_COLOUR (bright warm white)
  → wire_buf: hairline digit strokes, no blur

Step 3 — Multi-pass bloom
  p1 = GaussianBlur(wire_buf, r=BLOOM_R1) × BLOOM_S1   # tight corona
  p2 = GaussianBlur(wire_buf, r=BLOOM_R2) × BLOOM_S2   # orange cloud
  p3 = GaussianBlur(wire_buf, r=BLOOM_R3) × BLOOM_S3   # wide ambient
  bloom = add(p1, add(p2, p3))

Step 4 — Composite inside tube
  tube_buf = add(tube_buf, add(bloom, wire_buf))
  clip to tube rounded-rect mask

Step 5 — Outer bleed
  bleed = GaussianBlur(tube_buf, r=BLEED_R) × BLEED_S
  paste bleed onto canvas before tube (creates warm outer glow)

Step 6 — Glass overlay
  draw tube outline on canvas (rounded rect, dark orange-brown)
  optional: 1px specular highlight arc on left edge of glass
```

**Why additive composite?**
Nixie wire emits light. `ImageChops.add` (capped at 255) is the correct
blend mode. The tight corona pass bleeds white-hot at the wire core;
the wide ambient pass fills the tube with warm orange fog — matching
the authentic phosphor-orange character of a real Nixie discharge.

---

## Tube housing geometry

### Tube shape

A tall rounded rectangle — corner radius is large enough to give a capsule
feel without being a full pill (which would obscure digit area).

```
TUBE_W  = 48    (px — tube outer width)
TUBE_H  = 110   (px — tube outer height)   ← Phase 0 approved
TUBE_R  = 18    (px — corner radius)        ← Phase 0 approved
TUBE_Y  =  8    (px — top of tubes on canvas)
```

Aspect ratio: 48:110 ≈ 1:2.3 — tall capsule matching reference concept.

### Canvas layout (four tubes + colon)

```
Canvas: 275 × 240 px  (app canvas, taskbar excluded)

TUBE_GAP    = 6    (px gap between H1/H2 and M1/M2 pairs)
COLON_W     = 22   (px reserved for the colon dot column)
MARGIN_X    = (275 − 4×TUBE_W − 2×TUBE_GAP − COLON_W) // 2
            = (275 − 192 − 12 − 22) // 2 = 24 px

Tube left-x values:
  H1: MARGIN_X                         = 24
  H2: MARGIN_X + TUBE_W + TUBE_GAP     = 78
  M1: MARGIN_X + 2×TUBE_W + TUBE_GAP + COLON_W = 148
  M2: MARGIN_X + 3×TUBE_W + 2×TUBE_GAP + COLON_W = 202

Colon centre-x: 78 + TUBE_W + COLON_W//2 = 78 + 48 + 11 = 137

Tube top-y:
  TUBE_Y =  8   (near canvas top; date occupies lower canvas)
  Tube bottom: TUBE_Y + TUBE_H = 118

Date baseline-y: DATE_Y = TUBE_Y + TUBE_H + 22 = 140
```

Phase 0 approved — `p` key in preview tool prints full param dict.

### Hex mesh texture

The anode wire-mesh in a real Nixie tube creates a fine hexagonal grid
visible behind the digit. Rendered as a uniform dot pattern at very low
contrast — the mesh gives the tube interior depth and authenticates the
"seen through glass" look.

```
MESH_CELL  = 4    (px — centre-to-centre of mesh dots)
MESH_DOT_R = 1    (px radius of each dot → 3×3 solid square)
MESH_COLOUR = (C_ON[0]×0.08, C_ON[1]×0.08, C_ON[2]×0.08)
            ≈ (20, 14, 3) for amber default
```

Generation: nested loop over x, y from 0..TUBE_W, 0..TUBE_H stepping
MESH_CELL. Offset alternate rows by MESH_CELL//2 for hex stagger.
Applied before the wire glyph (bloom naturally dims it to near-invisible).

---

## Wire glyph system

### Font selection

The Nixie digit must look like a **thin wire cathode** — a continuous,
rounded, low-width stroke, not a filled shape.

Preferred font (thin weight, clean numerals): `Roboto-Thin` or
`NotoSans-Thin`. The font is rendered at `WIRE_FONT_SIZE` with no
additional outline or fill beyond the single stroke the font provides.

At thin weight, the rasterized stroke is 1–3 px wide — the bloom
builds the apparent body of the digit from these hairlines.

```
WIRE_FONT_SIZE = 88    (Phase 0 approved)
```

Font path priority list:
```python
_WIRE_FONT_PATHS = [
    "/usr/share/fonts/google-roboto/Roboto-Thin.ttf",
    "/usr/share/fonts/google-roboto/Roboto-Light.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Light.ttf",
    "/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Thin.otf",
]
```

### Wire colour

The rasterized glyph is drawn at near-white-orange — the bloom will
tint it. At the core the wire appears white-hot; the bloom produces
the orange envelope.

```
C_WIRE = (255, 125, 8)    # deep warm orange — Phase 0 approved (amber theme)
```

### Ghost cathodes (optional layer)

In a real Nixie tube, all 10 digit cathodes are physically present.
Inactive cathodes are faintly visible through the active glyph's bloom.

```
GHOST_ALPHA = 0.04    # fraction of C_WIRE for inactive digits
```

Render all 10 digits at `C_WIRE × GHOST_ALPHA` before rendering the
active digit. Implemented and toggleable via `h` key in the preview tool.
Default **off** — ghost cathodes are visually striking but add per-frame
bloom cost for 9 extra glyphs.

---

## Bloom parameters

Three passes — tight corona, orange cloud, wide ambient.

| Pass | Symbol | Default radius | Default scale | Effect |
|------|--------|---------------|--------------|--------|
| 1 — corona | `BLOOM_R1` | 2.5 px | 1.8 | White-hot core halo |
| 2 — cloud | `BLOOM_R2` | 8 px | 1.2 | Orange body of glow |
| 3 — ambient | `BLOOM_R3` | 18 px | 0.7 | Warm fog fills tube |

Outer tube bleed:

| Symbol | Default | Effect |
|--------|---------|--------|
| `BLEED_R` | 10 px | Blur radius for outer spill |
| `BLEED_S` | 0.45 | Scale applied to bleed layer |

Phase 0 key controls:
- `g` / `G` — step BLOOM_R2 ±1 px (adjust cloud size)
- `b` / `B` — step BLOOM_S2 ±0.05 (adjust cloud intensity)
- `r` / `R` — step BLOOM_R3 ±2 px (adjust ambient fill)

All three bloom images are computed from `wire_buf` (the glyph-only black
image), not from `tube_buf`. Tinting to orange comes naturally from
`C_WIRE`; no per-channel colour correction needed.

---

## Colour themes

**Amber is the default** (authentic to most historical Nixie tubes).

| Index | Name | C_WIRE (core) | Character |
|-------|------|--------------|-----------|
| 0 | amber (default) | `(255, 125, 8)` | Classic Nixie deep orange |
| 1 | red | `(255, 45, 10)` | High-voltage neon |
| 2 | green | `(50, 255, 80)` | Rare Nixie / oscilloscope |
| 3 | blue | `(70, 150, 255)` | Cold modern look |

All derived colours (mesh, ghost, tube bg) scale from C_WIRE at runtime.

```
C_TUBE_BG = (max(C_WIRE[0]×0.02, 5), C_WIRE[1]×0.015, C_WIRE[2]×0.01)
           ≈ (5, 2, 0) for amber default
```

### Settings wiring

Colour theme is exposed in Settings > Applications > Clock
(visible when `clockStyle == Nixie`):

```cpp
uint8_t nixieTheme;  // 0=amber 1=red 2=green 3=blue
```

`appsSection.h` cycles `nixieTheme` on tap, same pattern as `vfdTheme`.

---

## Render pipeline — implementation (host, PIL)

```python
def render(img: Image.Image, t: time.struct_time) -> None:
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))

    for digit, tube_x in zip(time_digits, TUBE_XS):
        tube_rect = (tube_x, TUBE_Y, tube_x + TUBE_W, TUBE_Y + TUBE_H)

        # tube background + mesh
        tube_buf = _draw_tube_bg(tube_rect)

        # wire glyph
        wire_buf = Image.new("RGB", (TUBE_W, TUBE_H), (0, 0, 0))
        _draw_wire_digit(wire_buf, digit)

        # bloom
        bloom = _bloom(wire_buf)

        # composite
        tube_buf = ImageChops.add(tube_buf, ImageChops.add(bloom, wire_buf))
        tube_buf = _apply_tube_mask(tube_buf, TUBE_W, TUBE_H, TUBE_R)

        # outer bleed (before pasting tube)
        bleed = tube_buf.filter(GaussianBlur(radius=BLEED_R)).point(
            lambda x: int(x * BLEED_S))
        canvas.paste(bleed, (tube_x, TUBE_Y), mask=...)

        # paste tube
        canvas.paste(tube_buf, (tube_x, TUBE_Y))

        # glass outline
        _draw_glass(canvas, tube_rect)

    _draw_colon(canvas)
    _draw_date(canvas, t)
    img.paste(canvas, (0, 0))
```

Full implementation target: `app/tools/_clock_nixie.py`. Standalone test:
```sh
python3 app/tools/_clock_nixie.py   # → /tmp/nixie_test.png
```

---

## Colon

Two circular dots centred in the colon column, vertically aligned with
the upper and lower thirds of the tube height.

```
COLON_CX    = 137                        (canvas x)
COLON_DOT_R = 3                          (dot radius px — Phase 0 approved)
COLON_Y1    = TUBE_Y + TUBE_H // 3      (upper dot)
COLON_Y2    = TUBE_Y + 2 × TUBE_H // 3  (lower dot)
```

Each dot gets the same three-pass bloom as the wire glyph: render a
filled circle at `C_WIRE × colon_level`, bloom, paste additively.

### Blink + phosphor afterglow

The colon blinks at 1 Hz with a realistic phosphor afterglow — fast
ignition, slow decay — matching the gas-discharge character of real
Nixie tubes.

```
Blink:   ON  for t % 1.0 < 0.5   (first half-second)
         OFF for t % 1.0 ≥ 0.5   (second half-second)

Turn-on  (ramp):  colon_level = min(1.0, elapsed_ms / COLON_RAMP_MS)
Turn-off (decay): colon_level = exp(−elapsed_ms / COLON_DECAY_MS)

COLON_RAMP_MS  =  80   (ms — snappy ignition strike)
COLON_DECAY_MS = 500   (ms — tau of exponential phosphor tail)
```

Decay profile at key elapsed times:
| Elapsed | Level |
|---------|-------|
| 0 ms | 1.00 (full on) |
| 100 ms | 0.82 |
| 250 ms | 0.61 |
| 500 ms | 0.37 |
| 1000 ms | 0.14 |
| 1500 ms | 0.05 |

The bloom computation is skipped when `colon_level × max(C_WIRE) < 2`
to avoid wasted GPU/CPU time at the tail end of decay.

### Inter-tube bleed note

The colon sits 11 px from both H2 (left) and M1 (right). Each
neighbour's outer bleed (`BLEED_R=10`) falls on the colon region,
creating asymmetric ambient light proportional to the active glyph
mass distribution in each adjacent digit. This is physically authentic
and is **not corrected** — it is consistent with how real Nixie panels
illuminate each other.

---

## Date rendering

Small thin text below the tubes:

```
Format:  "THU  12 JUN 2026"
Font:    Roboto-Thin at 13 pt
Colour:  C_WIRE × 0.65   (dimmer than digits; minimal bloom)
Anchor:  centre-top at (137, DATE_Y)
DATE_Y = TUBE_Y + TUBE_H + 22
```

Flanking bullet dots (matching concept):
```
Dot colour: C_WIRE × 0.4
Dot radius: 2 px
Dot x:  137 ± (text_half_width + 10)
Dot y:  DATE_Y + font_half_height
```

No multi-pass bloom on date — apply single GaussianBlur(r=3) × 0.6
so the text has a gentle glow without dominating the frame.

---

## Tube glass

Glass effect layers (drawn after compositing, on the canvas):

1. **Tube outline**: 1px rounded rect, colour `(50, 22, 5)` — dark warm brown.
2. **Specular highlight** (optional): 1px vertical line on the left-inner
   edge of the tube, `(80, 40, 10)`, from `TUBE_Y + TUBE_R` to
   `TUBE_Y + TUBE_H - TUBE_R` — simulates reflected room light on glass.
3. **Pin shadow**: two 1×3 px dark rects at tube bottom centre — represents
   the wire pins at the base of a real Nixie tube envelope.

---

## Open items — design iteration needed

> The core digit mechanism (bloom pipeline, hex mesh, ghost cathodes, colon
> afterglow) is considered approved at Phase 0. The following areas are
> **not yet signed off** and require further visual iteration before Phase 1
> (firmware) can begin.

### OI-1 — Overall clock composition

The current preview establishes the tube rendering correctly but the
**full-canvas composition** has not been iterated. Open questions:

- Tube vertical position and canvas weight — do the tubes sit too high?
  Should they be vertically centred, or offset toward the top third to
  leave breathing room for date elements below?
- Inter-tube spacing — the 6 px gap creates visible cross-bleed between
  adjacent digits. The aesthetic consequence (authentic inter-tube glow
  vs. unwanted light pollution) needs a design decision.
- Canvas background treatment — pure black `(0,0,0)` is the current
  default. A very dark warm-black `(4, 2, 0)` may better complement the
  amber glow without appearing as a solid colour.

### OI-2 — Date area design

The date line is currently a minimal placeholder:
`"THU  12 JUN 2026"` in Roboto-Thin 13 pt at `C_WIRE × 0.60`.

Open questions:
- Font size and weight — 13 pt may be too small; a slightly heavier
  weight (Roboto-Light) at 14–15 pt may read better at device scale.
- Layout format — single-line vs. two-line (day name / numeric date)?
  The concept reference shows a single compact line; explore alternatives.
- Vertical placement — `DATE_Y = 140` leaves ~100 px of canvas below the
  tubes unused. Consider whether additional elements (seconds indicator,
  ambient decoration) belong in that space, or whether the empty canvas
  is intentional (visual rest).
- Glow treatment — current date text has no bloom pass. A single soft
  blur `(r=3, scale=0.5)` may give it the same phosphor character as the
  tubes without competing with the digit glow.
- Flanking bullet dots — currently two small dim dots flank the date
  string. Size, brightness, and whether they should also have a micro-bloom
  are undecided.

### OI-3 — Seconds indicator

The concept reference shows no explicit seconds indicator. Options:
- None (clean, matches concept) — current state
- Subtle dot arc below the tubes (60 dots, lit = elapsed seconds)
- Thin progress bar in the canvas bottom margin

**No decision made.** Raise with designer before implementing.

---

## Firmware renderer (Phase 3)

TFT_eSPI has no Gaussian blur. Same three options as VFD:

### Option A — Pre-baked glyph sprites (recommended)

For each of the 10 digits × 4 colour themes: pre-compute a
`uint16_t[]` sprite (48×90 px, RGB565) with all three bloom passes
burned in. Store in flash.

Flash cost: 10 × 4 × 48 × 110 × 2 bytes = 422.4 KB.
Acceptable with PSRAM; without PSRAM limit to active theme only (~42 KB).

Outer bleed and glass outline are cheap runtime draws. Mesh texture
is also cheap runtime (nested loop, no blur).

### Option B — Concentric ring approximation

After drawing the sharp wire glyph, draw the same glyph multiple times
at increasing `drawRoundRect` / `drawLine` offsets with decreasing
brightness. Three rings, O(digit_strokes × 3). Coarser but zero RAM.

### Option C — Sharp wire only

Authenticate the thin-wire look without bloom. Works well if the
hardware cannot afford Option A or B. The tube housing and mesh texture
still distinguish this from the plain Digital style.

**Decision**: defer to Phase 3. Option A preferred if PSRAM available.

---

## Relationship to M-CLOCK-STYLES.md

`M-CLOCK-STYLES.md` owns:
- Phase 0 concept tool spec and approved constants block
- Style enum + dispatch stub
- Settings wiring skeleton
- Exit criteria C5

This doc owns:
- Tube housing geometry and mesh texture model
- Wire glyph font selection and colour
- Three-pass bloom pipeline + outer bleed
- Ghost cathode option
- Colour themes and settings wiring detail
- Firmware renderer options

When Phase 0 `p`-key approved constants are recorded, they are copied into
the Approved Constants block in `M-CLOCK-STYLES.md` and the parameter tables above.
