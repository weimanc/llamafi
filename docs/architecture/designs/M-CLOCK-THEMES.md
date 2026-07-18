# Design — Nixie + VFD colour theme picker (settings-exposed)

> Owner: Architect
> Status: implemented
> Date: 2026-07-18
> Feeds: implemented directly (no separate ADR — single self-contained decision, see "Lean / decision")
> Tracked-as: TASK-345
> Registers: clock-themes-001 · X036

## Context / pain points

Both `M-CLOCK-NIXIE.md` and `M-CLOCK-VFD.md` have carried a fully-specified
"Future / post-MVP — colour theme picker (DOCUMENTED, NOT IMPLEMENTED)"
section since TASK-193 — 4 named themes each (Nixie: amber/red/green/blue;
VFD: teal/amber/blue/green), a `nixieTheme`/`vfdTheme` `AppSettings` field,
and an `appsSection.h` cycle-row sketch. Never built. User asked to build it
now, immediately after two passes (TASK-336, TASK-337) resyncing both
styles' rendering to their concept tools.

VFD is trivial: `_drawVFD()` fills dot cells with flat runtime colour
constants (`0x069C` on / `0x0061` off / `0x0473` date) — retheming is
"read a theme-indexed colour instead of a hardcoded one," no new machinery.

Nixie is not trivial. `ClockApp::_drawNixie()` `pushImage()`s a **baked**
sprite (`app/gen/nixie_glyphs.cpp`, `bake_nixie.py`) — the wire-glyph +
hex-mesh + 3-pass-bloom composite is rendered once on the host (PIL has
Gaussian blur; TFT_eSPI does not) and stored pre-coloured as RGB565. The
naive extension — bake one full sprite set per theme — is the actual design
question here.

## Goals

- Nixie and VFD both get a `Settings > Applications > Clock` colour-theme
  row, visible only when that style is the active `clockStyle`, cycling on
  tap, persisted, matching the docs' existing name lists exactly (no
  renumbering — those names are already the user-facing contract).
- Nixie's bake cost should not scale linearly with theme count. Four
  themes must not cost 4× the flash of one.
- No visual regression versus the current single-amber bake — theme output
  must be pixel-identical to "bake this theme directly," not an
  approximation.

## Design space (options + tradeoffs)

**A. Bake N full RGB565 sprite sets, one per theme, pick at pushImage time.**
Zero new runtime logic — literal extension of what exists. Cost: 4 ×
103.1 KB = 412.4 KB flash for Nixie alone (vs. 738 KB currently free,
71.8% used pre-this-change) — over half the remaining headroom for a
cosmetic feature, and doesn't scale if a 5th theme is ever wanted.
Rejected on cost.

**B. Bake once as flat white, tint via a runtime colour-multiply blit.**
Every colour source in `_clock_nixie.py`'s tube composite — mesh, tube
background, wire glyph, all three bloom passes — is *derived from
`C_WIRE` by a constant per-channel scale factor* (`mc = v*0.075`,
`c_bg = v*0.02`, bloom passes are `blur(wire).point(x*scale)` where `wire`
is a flat fill of one RGB tuple). Gaussian blur and per-channel scalar
multiply are both linear, channel-independent operations, so for a
single-hue source image:

```
render(C_WIRE) == render(WHITE) scaled channel-wise by C_WIRE/255
```

exactly — not an approximation. So: bake once with `C_WIRE=(255,255,255)`,
store **luminance only** (`uint8_t`, not `uint16_t` RGB565 — half the
bytes, since the three channels are always equal for a white bake), and at
render time compute `pixel = color565(R*lum/255, G*lum/255, B*lum/255)`
per theme colour into a small static scratch buffer, then `pushImage()`
that. Cost: **51.5 KB total**, flat, regardless of theme count — cheaper
than even the *current single-theme* 103.1 KB bake, because RGB565→uint8
luminance halves the per-pixel storage. Runtime cost: one 48×110 = 5280-
pixel tint loop per digit per redraw (only on digit change, not every
tick) — trivial on a 240 MHz dual-core ESP32.

**C. Runtime-tint at draw time by reading back and rescaling the existing
amber bake** (no re-bake). Amber's R channel saturates almost immediately
(`C_WIRE.R=255`), so it carries no usable dynamic range to invert; G
(`base=125`, peak observed `210`) is the only channel with headroom, and
even that's a lossy, approximate reconstruction of the true luminance —
double quantization (baked-amber's own RGB565 rounding, then an inverse
scale guess) for zero benefit over just re-baking correctly. Rejected —
strictly worse than B on both accuracy and effort.

## Lean / decision

**Option B.** Re-bake `nixie_glyphs.cpp/h` as `uint8_t` luminance arrays
(`bake_nixie.py --C_WIRE white`, store `img.getdata()` luminance channel
only). Add a `_tintNixieGlyph(digit, themeColour) -> uint16_t*` helper in
`clockApp.h` that fills a `static uint16_t s_tintBuf[TUBE_W*TUBE_H]` scratch
buffer from the luminance sprite + the active theme's `(R,G,B)`, then
`pushImage()` that instead of `nixie_glyph_ptrs[digit]` directly. Theme
colour table lives in `clockApp.h` next to the existing `kFp*`/`kT*`
constant blocks, copied verbatim from `M-CLOCK-NIXIE.md`'s theme table
(same 4 entries, same order, same names — this doc is the source of
truth already, not re-derived).

VFD: no bake involved, so no analogous machinery needed — just index a
4-entry `kVfdTheme[]` colour table by `g_settings.vfdTheme` instead of the
hardcoded `0x069C`/`0x0061`/`0x0473` constants, copied verbatim from
`M-CLOCK-VFD.md`'s table.

Settings: `nixieTheme`, `vfdTheme` — `uint8_t`, default 0, same shape as
existing `matrixColor`/`lifeColors` fields (no new settings pattern
needed). `appsSection.h`'s `_repaintClock()`/`_cycleClock()` gain a
conditional second row exactly matching both docs' pre-written
`_repaintVFDTheme()`/`_cycleVFDTheme()` sketch, generalized to cover both
styles from one function (avoids duplicating the row-index/tap-dispatch
logic for what is structurally the same row).

## Open questions

- None blocking. Contrast-mode (VFD's secondary "standard/high/low"
  setting) stays unexposed per `M-CLOCK-VFD.md`'s own note ("not exposed
  to the user. Ship standard mode only") — this pass doesn't revisit that
  call.

## Exit criteria

- `nixieTheme`/`vfdTheme` fields wired (ADR-050 gate), settings row visible
  only for the matching `clockStyle`, cycles + persists + repaints live.
- DUT-verified via `screendump`: at least one non-default theme per style,
  confirming actual on-device colour (not just "it compiles").
- Flash cost checked against budget (`run/check` gate 1/2 — build success
  is the only automated flash-size gate this project has; no dedicated
  flash-budget script exists, unlike the RAM `mem_layout` gate).
- `M-CLOCK-NIXIE.md` / `M-CLOCK-VFD.md` "Future / post-MVP" sections
  flipped from "DOCUMENTED, NOT IMPLEMENTED" to shipped, with a pointer to
  this design doc.
