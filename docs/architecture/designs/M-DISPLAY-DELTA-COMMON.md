# Design — Display repair: is the delta engine worth generalizing?

> Owner: Architect
> Status: draft
> Date: 2026-07-19
> Feeds: ADR-052 (proposed)
> Tracked-as: none yet (PM to file the PlaneRadar follow-up task; this design
> is scoped to the shared-infra question, not the PlaneRadar implementation)
> Registers: viewport-repair-001 · X037

## Context / pain points

TASK-354 (`M-CLOCK-FACE-COMMON.md` §Part 1, shipped 1401e9f) fixed a whole-
face flicker in Clock's Flip/Nixie faces: both redrew their entire static
layer every second purely because the colon blinked. Root cause, generalized:
on this board's unbuffered SPI display, any erase-then-redraw of pixels that
didn't actually need to change is visible to the eye, independent of how fast
the MCU does it. The fix was a **discrete-slot delta engine** — compute
`FaceFrame{digs[4], colon}` once per tick, diff against a cached copy, hand
each face only the slots that changed.

TASK-357 (dr-damped(tau=2) motion smoothing, shipped 1f66252) introduced the
identical anti-pattern in a new shape. `planeRadarApp.h`'s `tick()` now runs
`_render()` at ~10 Hz whenever `_motionDirty()` says *any single aircraft's*
dead-reckoned position crossed a pixel. `_render()` (`planeRadarApp.h:931`)
unconditionally:

1. `_erasePrev()` — erases **every** previously-drawn aircraft footprint
   (moved or not), `:1010`.
2. `_redrawGridStatics()` — redraws all 4 range rings, crosshair, and every
   in-range runway centerline + ICAO label, `:756`.
3. Redraws **every** aircraft's symbol/vector/tag from scratch with full
   tag-occlusion recompute (`occ[]`/`_placeTag`), `:940-1004`.

The human reported this as visible "twitchy" tearing and explicitly named
the Clock precedent unprompted — this is the same bug, not a new one. TASK-357
already sketched (but did not implement — "Deferred to the human DUT session")
a per-aircraft dirty-rect fix using `_motionPx()` as a free, storage-free
dirty check (it's a pure function of stored state + time, so evaluating it at
"last redraw" vs "now" tells you whether a specific aircraft actually moved,
with zero extra bookkeeping — the mechanism `_motionDirty()` already uses at
the whole-scene level, `:732`).

Researched this session (not yet used anywhere — `grep -rn setViewport
app/src/` returns nothing): TFT_eSPI's `setViewport(x,y,w,h,vpDatum=false)`
clips every subsequent draw call (`drawCircle`, `fillRect`, `drawLine`,
`fillTriangle`, `drawString`, …) at the individual-pixel level via
`drawPixel`'s bounds check. Confirmed by reading `TFT_eSPI.cpp`:

```cpp
void TFT_eSPI::setViewport(int32_t x, int32_t y, int32_t w, int32_t h, bool vpDatum) {
  ...
  // Clip viewport to screen area
  if (x<0) { w += x; x = 0; }
  if (y<0) { h += y; y = 0; }
  if ((x + w) > width() ) { w = width()  - x; }
  if ((y + h) > height() ) { h = height() - y; }
  if (w < 1 || h < 1) { ... _vpOoB = true; return; }   // fully off-screen: no-op, no crash
  ...
}
```

Auto-clips to screen bounds and no-ops safely on a degenerate box — callers
don't need to pre-clamp. With `vpDatum=false`, absolute screen coordinates
are preserved (clip-only, no origin shift). Practical consequence: an app's
existing "redraw the whole static layer" function can be reused **verbatim**
under a small viewport to cheaply repair just a dirty rectangle, instead of
writing new per-app clip/geometry code.

The coordinator's preliminary (unvalidated) framing, given to the human: the
two data points (Clock's discrete-slot diff, PlaneRadar's continuous-2-D
sprite motion) feel different enough in kind that unifying them risks
premature generalization, but the viewport-repair *technique* looks cleanly
generic. This design validates or corrects that framing against the actual
inventory rather than rubber-stamping it.

## Survey — repaint pattern per app/feature

Grounded in `docs/project/feature_inventory.yaml`,
`docs/project/cross_feature_matrix.yaml`, and direct reading of the app
sources under `app/src/` (not names/memory).

| App / feature id | Current repaint pattern | Flicker risk | Benefits from shared viewport-repair primitive? |
|---|---|---|---|
| **planeradar-001** (`app/src/planeRadarApp.h`) | Whole-scene `_render()`/`_erasePrev()`/`_redrawGridStatics()` fires at ~10 Hz gated on `_motionDirty()` (TASK-357). Erases/redraws *all* aircraft + *all* grid statics even when one aircraft moved. | **Has it** — human-reported twitchy tearing, this session. | **Yes.** Primary, currently-only consumer: scope `_redrawGridStatics()`'s repair (post-erase) to the dirty aircraft's bounding box(es) instead of the whole disc. Not yet implemented — deferred by TASK-357 itself. |
| **clock-001** (`app/src/clockApp.h`) | Post-TASK-354: discrete `FaceFrame` diff engine, `drawDigit(i)`/`drawColon()` hooks fire only on change. No viewport geometry involved — colon/digit redraws are self-contained shapes (fillCircle/tube tint), not "static layer under a moving 2-D sprite." | **Fixed** (Flip/Nixie, TASK-354) / **never had it** (Digital, VFD — self-gated pre-354). | **No.** Nothing to scope — the engine's per-slot draws don't damage a static layer that needs repair. Retrofitting onto a viewport abstraction would add surface area to a DUT-proven fix for zero benefit. |
| **webradio-001** (`app/src/webRadioApp.h`) | Independently solved: `_pleditDirty` is a "row-region-only repaint marker (not `_dirty`)" (`:1165`); position bar does "targeted POSBAR blit only — no full repaint" (`:625`); velocity-scroll gesture explicitly avoided a `_dirty`-triggers-full-repaint path that made the thumb jump (`:592-594`). | **Already solved, own way.** Direct region-scoped `fillRect`/blit, no shape-list to replay under a static layer. | **No evidence of need.** Its dynamic elements sit over Winamp skin art restored by direct pixel blit, not by replaying a procedural static-layer function — different mechanism, already correct. |
| **VU meter / spectrum / wave** (`app/src/winamp/vuMeter.h`) | Per-column dirty diff (`lDirty`/`rDirty` on bar-width change, `tickVU():128`) + **pixel-exact restore from the known skin background buffer** (`pushImage(... mainBg ...)`) rather than redrawing shapes. A fourth independently-invented technique. | **Already solved, own way.** | **No.** Restoring known pixels from a buffer is strictly cheaper and more precise than viewport-scoped shape replay; nothing to gain by switching mechanisms. |
| **weather-001 / crypto-001** (`app/src/main.cpp`) | `repaintWeatherTime()` gates on `tm_sec` change and erases only the TIME tile's `fillRect`; `repaintWeatherValues()` fires only on a landed fetch result (~60 s cadence). Field-scoped, not scene-scoped. | **Doesn't apply.** Low frequency (1 Hz gate, 60 s fetch), field-scoped erase, no continuous motion. | **No.** |
| **matrix-001** (`app/src/main.cpp`, `MatrixApp`) | Continuously redraws per-glyph-cell every tick by construction (draw head char, redraw tail char, blank the row ahead) — there is no "static layer" distinct from the dynamic content to begin with. | **Doesn't apply** — not the same bug shape (nothing static to protect). | **No.** |
| **gol-001** (Game of Life, `app/src/main.cpp`) | feature_inventory.yaml: "Diff render (only changed cells repainted)" — a fifth independently-invented diff mechanism, cell-grid-shaped. | **Already solved, own way.** | **No.** |
| **Stock app** (`app/src/main.cpp`, `StockApp`) | `repaintList()`/`repaintChart()`/`repaintHeatmap()` are full-canvas (`fillRect(0,0,275,240,...)`) but fire only on view entry / navigation / ~60 s poll landing — no per-tick animation loop. | **Doesn't apply.** Infrequent full repaint on discrete state change is not the anti-pattern (the anti-pattern is *per-tick* replay driven by *any* sub-element changing). | **No.** |
| **Aquarium** (`app/src/aquarium/aquariumApp.h`, ADR-031) | Renders into an off-screen `TFT_eSprite` canvas, single atomic `pushSprite()` per frame (`:1551`). A **third, architecturally distinct** strategy: double-buffer the whole scene instead of diffing it. | **Structurally immune by construction** — no erase/redraw race with the display is possible, the display only ever sees one complete, already-composited frame. | **No — different strategy, not a variant of the same problem.** Worth naming explicitly as the third valid pattern in this space (see Design space below). Note: Aquarium currently has **no `feature_inventory.yaml` entry** at all (pre-existing registry gap, out of scope for this design — flagged for Developer/PM, not fixed here). |

Five apps had already invented their own local fix for this same problem
class before TASK-354 or this design existed (VU meter, WebRadio, Weather/
Digital's string-cache, Game of Life) — plus Aquarium sidesteps it entirely
with a different strategy (full double-buffer). That is strong evidence the
*problem* recurs, and equally strong evidence that each *solution* is
legitimately shaped by its own data (bar width vs. region vs. field-string vs.
cell-grid vs. whole-sprite-buffer) — not evidence that one abstraction should
own all of them.

## Goals

1. Stop PlaneRadar's TASK-357-induced tearing without touching the
   correctness-critical parts of the already-hardened `_render()` pipeline
   (tag occlusion, symbol geometry, disc-containment invariants) — scope
   *only* the static-layer repair and per-aircraft erase/redraw to dirty
   aircraft.
2. Answer, from evidence rather than pattern-matching on two examples,
   whether "compute a delta, redraw only what changed" deserves a shared
   framework.
3. Extract only what is genuinely reusable now. Do not build infrastructure
   the inventory doesn't support.

## Design space (options + tradeoffs)

**A. Unified "dirty-rect sprite" base class/framework.** Every app's dynamic
elements subclass a common abstraction (`erase()`, `draw()`, `boundingBox()`
hooks); an engine owns diff + erase + redraw + viewport scoping generically,
the way TASK-354's `FaceFrame` engine owns Clock's four faces.
- *Pro:* maximal reuse; forces discipline on future apps.
- *Con:* the seven existing instances (Clock ×2 sub-cases, VU meter,
  WebRadio, Weather/Digital, Game of Life, Aquarium's opposite strategy) use
  six structurally different data shapes — discrete slot arrays, 1-D bar
  widths, scroll-offset regions, gated field strings, toroidal grid cells,
  and whole-sprite double-buffering. None share code today; each is small,
  correct, and (where applicable) DUT-proven. A base class expressive enough
  to cover a 2-D dead-reckoned sprite with rotation + tag occlusion *and* a
  4-digit slot array *and* a scroll region *and* "redraw the whole thing into
  a RAM sprite" would either be so abstract it adds indirection without
  removing duplication, or would only really fit the one new consumer
  (PlaneRadar) — i.e., built to be general on a two-example sample for the
  2-D sub-case. Retrofitting Clock's fresh, DUT-proven TASK-354 engine for
  framework purity is pure risk (touching working, measured code) for no
  measured payoff.
- **Rejected** — exactly the premature-generalization risk the human/
  coordinator flagged going in; the survey confirms it rather than merely
  assuming it.

**B. Small stateless viewport-repair helper.** `withViewportRepair(tft, x,
y, w, h, repairFn)` wraps `setViewport`/`resetViewport` around a caller-
supplied redraw callback — typically an app's *existing* whole-static-layer
function, called unmodified. Lives in `app/src/util/`, the existing home for
stateless cross-app helpers (`mathUtil.h`, `timeFmt.h`).
- *Pro:* ~15 lines, zero new state or class hierarchy, works with any app's
  existing static-redraw function verbatim (no per-app clip/geometry code to
  write), directly unblocks PlaneRadar's deferred follow-up, touches nothing
  that already works.
- *Con:* doesn't give a future app a turnkey "just subclass this" story —
  each app still writes its own per-element dirty check and erase/redraw
  pair, same as all six apps that already do this today.
- **Leaned.**

**C. No shared code — PlaneRadar inlines `setViewport`/`resetViewport`
calls directly.**
- *Pro:* zero new surface area.
- *Con:* TFT_eSPI's viewport is a single **non-stacking global rectangle** —
  a forgotten `resetViewport()` on any exit path silently clips every
  subsequent draw call app-wide until the next full repaint happens to reset
  it. That's a nasty, easy-to-introduce bug class for a technique that is
  brand new to this codebase (zero prior call sites to copy the invariant
  from). A one-function wrapper is cheap insurance to pin the invariants
  (auto-clip to screen, no nesting, `vpDatum=false` convention) once, in one
  place, rather than trusting every future call site to get it right from
  scratch.
- **Rejected** — B's cost is low enough that C's savings aren't worth the
  footgun risk.

## Lean / decision

**B.** Ship one small header, `app/src/util/tftViewportRepair.h`:

```cpp
#pragma once
#include <TFT_eSPI.h>

// Clip every subsequent draw call to [x,y,w,h] (absolute screen coords,
// vpDatum=false — no origin shift), run `repairFn` — typically an app's
// EXISTING whole-static-layer redraw function, called verbatim — then
// always restore the full-screen viewport before returning.
//
// Invariants (confirmed by reading TFT_eSPI.cpp's setViewport()):
//  - out-of-bounds/degenerate boxes are handled internally (_vpOoB inhibits
//    all drawing; no pre-clamping needed, no crash on a bad box)
//  - the viewport is a single non-stacking global — repairFn must NOT itself
//    call setViewport/resetViewport (no reentrancy)
//  - clips PIXEL WRITES only, not the CPU cost of repairFn's shape-iteration
//    loop — see Open questions for when that distinction matters
template <typename Fn>
inline void withViewportRepair(TFT_eSPI& tft, int32_t x, int32_t y,
                                int32_t w, int32_t h, Fn&& repairFn) {
    tft.setViewport(x, y, w, h, false);
    repairFn();
    tft.resetViewport();
}
```

**No changes to Clock's shipped delta engine.** `M-CLOCK-FACE-COMMON.md` is
not amended beyond a cross-reference note — its discrete-slot mechanism has
no static-layer-under-a-moving-sprite shape to repair, so there is nothing
for this helper to do there.

**No changes to WebRadio, VU meter, Weather/Digital, Game of Life, or
Aquarium.** All six already handle their own case correctly by their own
(different) mechanism; this decision adds no surface area to any of them.

**PlaneRadar (the one live consumer, follow-up not yet filed as a task):**
when implemented, the per-aircraft dirty-rect fix sketched in TASK-357's
notes calls `withViewportRepair()` around `_redrawGridStatics()` (unmodified)
scoped to each dirty aircraft's erase+redraw bounding box, instead of that
function running full-disc on every ~10 Hz tick that has *any* dirty
aircraft. The per-aircraft erase (a plain `fillRect` over the old footprint)
and redraw (symbol/vector/tag) don't need the helper themselves — they
already only touch their own aircraft's pixels; it's specifically the grid-
statics *repair* step (rings/crosshair/runways getting stomped by the erase
rect) that currently over-scopes to the whole disc and is what the helper
fixes.

## Open questions

1. **Per-aircraft vs. union bbox.** Does the PlaneRadar implementation call
   `withViewportRepair()` once per dirty aircraft, or compute one bounding
   union across all dirty aircraft this tick and clip once? Both are cheap
   at ≤24 aircraft (`PR_MAX_AIRCRAFT`); left to Developer's implementation
   judgement, not an architectural fork.
2. **CPU cost is a non-goal, stated explicitly.** `withViewportRepair()`
   reduces SPI *write* volume (the actual driver of the reported visible
   tearing) proportional to the dirty box area, but does **not** reduce the
   CPU cost of `_redrawGridStatics()`'s shape-iteration loop (4 circles, 2
   lines, up to 240 runway distance-checks) — TFT_eSPI clips at the
   `drawPixel` level, so the loop still runs, it just writes nothing outside
   the box. By inspection this loop is cheap (float compares, no display
   I/O) at PlaneRadar's ≤240-airport scale, so leaving it unscoped is fine
   today. A future static-layer function with an expensive *generation* step
   (not just an expensive *pixel count*) would need its own bbox-aware
   early-out, which this helper deliberately does not provide — flag for
   whoever hits that case rather than solve it speculatively now.
3. **When does a real sprite base class become justified?** If a *third*
   continuous-2-D-motion app appears (beyond Clock's discrete slots and
   PlaneRadar's dead-reckoned aircraft) with the same dirty-rect-motion
   shape, that's the point to revisit Option A with three data points
   instead of pattern-matching on two. Not before.
4. **PlaneRadar follow-up task filing** is a PM decision, not settled here —
   this design only commits the shared-infra question.

## Exit criteria

- `app/src/util/tftViewportRepair.h` exists, single function, no class, no
  per-app state — built when the PlaneRadar follow-up is implemented (not a
  standalone task; it's ~15 lines with one call site initially).
- PlaneRadar's per-aircraft dirty-rect follow-up uses it for
  `_redrawGridStatics()` repair scoped to dirty-aircraft bounding box(es);
  `run/check` + a DUT eyeball (BP-048 — this is a visual) + a screendump-diff
  assertion analogous to `clock_delta_smoke.py` ("steady per-aircraft motion
  tick touches ≤ the dirty aircraft's own footprint pixels outside its erase/
  redraw box") land together with that task.
- Clock, WebRadio, VU meter, Weather/Crypto/Digital, Game of Life, Aquarium:
  zero diffs. Verifying "no change" for these is part of exit criteria
  precisely because the temptation this design rejects is to touch them for
  framework consistency.
- ADR-052 moves `proposed` → `accepted` on human sign-off; this design's
  `Status` moves `draft` → `accepted` in lockstep.
