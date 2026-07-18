# Design — Clock face common infrastructure: colon/delta engine + Nixie storage

> Owner: Architect
> Status: accepted — footprint part (4-bit) implemented as TASK-353; shared
> engine part filed as TASK-354 (open, awaiting scheduling)
> Date: 2026-07-18
> Depends on: M-CLOCK-STYLES, M-CLOCK-THEMES (TASK-345), M-CLOCK-TAP-CYCLE (TASK-346)

## Part 1 — the colon, and what it revealed about code reuse

### How each face draws ":" today

| Face | Colon rendering | Per-second work | Delta cache |
|---|---|---|---|
| Digital | font-6 glyph overdrawn white/black (`clockApp.h:224`) | colon glyph only | `_lastHourStr`/`_lastAmPm` gate digit erases |
| Flip | 2 `fillCircle` flip-dots | **full-face**: body `fillRect` + colon + all 4 panels | `_fd[].shown` exists but does not gate the redraw |
| Nixie | 2 halo+core `fillCircle` pairs | **full-face**: 275-px-wide wipe + re-tint + re-push all 4 sprites (~42 KB SPI + 21k multiplies) | none |
| VFD | 8 grid dots (`_drawVFDColon`) | colon cells only | `_vfdDigs[]`/`_vfdColonOn` |

All four compute the same two facts per tick — `digs[4]` from
`clockHour()`/`tm_min`, and `colonOn = (tm_sec % 2 == 0)` — in four
separate copies. What they *do* with those facts diverges: VFD and
Digital gate their redraws on change; Flip and Nixie redraw everything
every second because the colon blink drags the whole face with it (the
user-visible flicker). VFD's own header comment records that it had the
identical bug and was fixed with a cache — the fix never propagated to
the other faces. That is the reuse failure, not the four colon *styles*
(which are legitimately per-face art).

### Duplication inventory

- Time→digits split: 3 near-identical copies (`_drawFlip`, `_drawNixie`,
  `_drawVFD`), 1 string variant (`_drawDigital`).
- Colon parity: 4 copies.
- Change gating: 2 independent private implementations (Digital strings,
  VFD digit cache), 2 missing.
- Already shared correctly: `_drawDate`/`_drawRssi`, style dispatch,
  tick-rate gating, theme tables.

### Proposal (TASK-354): one delta engine, four renderers

Invert the structure — the engine owns *when*, faces own *how*:

```cpp
struct FaceFrame { uint8_t digs[4]; bool colon; };   // computed once per tick

// per-face hooks (function table or switch — no vtable needed):
//   drawStatic()          — background/frames, on repaint() only
//   drawDigit(i, val)     — one digit slot
//   drawColon(on)         — self-erasing both states
//   animate()             — optional (Flip's flap frames while _fd active)
```

Engine tick: compute `FaceFrame`, diff against cached copy, call
`drawDigit` only for changed slots, `drawColon` only on parity flip,
delegate to `animate()` while an animation is in flight. Effects:

- Flip + Nixie flicker fixed **by construction** (their per-second work
  drops to two/four `fillCircle`s), not by hand-adding a third and
  fourth private cache.
- Three copies of the time-split and four of the colon parity collapse
  into one.
- The next face (user has form here — 4 faces and counting) gets delta
  redraw for free instead of re-importing the bug.

Fit notes (honest edges): Digital's 12h mode renders `"9:41"` with a
variable-width hour — it keeps its string-compare erase inside
`drawDigit(0/1)` or models the hour as one slot; Flip's mid-animation
ticks bypass the digit diff via `animate()`. Neither breaks the model;
both stay inside their face's renderer.

Scope: refactor + the two flicker fixes land together (they are the same
change). VE: existing screendump eyeballs per face + a new
"steady-state second tick repaints ≤ colon pixels" assertion via
screendump diff between two consecutive seconds.

## Part 2 — Nixie storage footprint

Baseline after M-CLOCK-THEMES: 10 × 48×110 × 1 B luminance = 51.6 KB
flash, tinted per-theme at runtime. Measured options (2026-07-18, script
over the real baked data):

| Technique | Size | Measured basis | Verdict |
|---|---|---|---|
| 8-bit luminance (baseline) | 51.6 KB | — | superseded |
| **4-bit luminance + 16-entry LUT** | **25.8 KB** | max err 8/255, mean 3.9 | **implemented (TASK-353)** |
| zlib/LZ over 8-bit | 30.9 KB | 60% ratio — hex mesh defeats LZ | rejected: worse than 4-bit AND needs a decompressor |
| naive RLE | 73.9 KB | 143% — mesh has no runs | rejected |
| post-hoc layer split (min-common + residual) | 35.0 KB | residual 84% nonzero | rejected — entanglement, see below |
| bake-side layer separation | est. 4–8 KB | half-res residual 13.2 KB pre-pack | **documented future** (below) |

### 4-bit (TASK-353, implemented)

Quantise at bake time (`l4 = round(l·15/255)`), pack two pixels per byte
(high nibble = left pixel; 48-px row = 24 B, no row straddle). Runtime
decode via a 16-entry RGB565 LUT built per theme
(`lut[i] = color565(th.r·i·17/255, …)`, 128 B for all four themes,
rebuilt only on theme change) — which **replaces** the previous
three-multiplies-per-pixel tint, so the hot loop gets cheaper, not
dearer.

Why lossless in practice: max quantisation error is 8/255 *in
luminance*, before the theme multiply scales it further down; the
display's RGB565 red/blue channels have 5-bit (8-step) granularity, so
the error is at or below one display LSB. Verified numerically at bake
review time and by DUT screendump eyeball across themes.

### Bake-side layer separation (documented, NOT implemented)

The reason generic compression fails is that one bitmap entangles two
signals with opposite character: the **hex mesh** (high-frequency,
regular, identical across all 10 digits) and the **wire glyph + bloom**
(smooth, Gaussian, per-digit). Post-hoc separation can't recover them
(measured above), but the bake pipeline *constructs* them as separate
layers before compositing — so keep them separate:

1. **Mesh + tube background → procedural on device.** It is a regular
   hex lattice `_clock_nixie.py::_build_mesh()` draws from a handful of
   parameters — port that loop to C (code, ~0 B data). Drawn once into
   the band buffer before the glow is added.
2. **Wire + bloom glow → baked per digit, aggressively reduced.** The
   glow layer is Gaussian-smooth, so it tolerates half-resolution
   storage + bilinear upscale + 4-bit packing: measured 13.2 KB at
   half-res/8-bit → ~6.6 KB at 4-bit, for all 10 digits.
3. **Composite at render**: `pixel = clamp(mesh + glow)` per band —
   valid iff the bake's composite is (or is made) additive;
   `render_digit()` currently uses `ImageChops.add` for mesh-over-bg
   plus bloom screening — the screen-blend pass must be re-derived or
   switched to add at bake time and re-eyeballed.

Estimated total: 4–8 KB (≈10× below today's 25.8 KB), CPU cost one add +
clamp per pixel on top of the LUT fetch — noise on a 240 MHz part, and
the user has explicitly noted CPU headroom is not a concern. Prereqs:
bake restructure, C mesh renderer, composite-linearity verification,
full theme × digit eyeball sweep. Worth scheduling only if flash
pressure returns (738 KB free today) or a 5th+ face lands; recorded here
so the analysis doesn't have to be re-derived.

## Cost summary

TASK-353 (done): −25.8 KB flash, hot loop cheaper, zero RAM change (band
buffer unchanged), bake tool +quantise/pack, `_tintNixieGlyph` +LUT.
TASK-354 (open): no assets; deletes duplicated tick code; fixes both
remaining flicker faces; small risk in Flip animation interplay —
mitigated by keeping `animate()` as a pass-through hook.
