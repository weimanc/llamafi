# Design — M-PLANERADAR Phase 0: preview tool + UI layout

> Owner: Architect
> Status: draft — designer-review PASS 2026-07-10; tool built, interactive session pending (see Results)
> Date: 2026-07-10
> Parent: [M-PLANERADAR-plane-radar-app.md](../M-PLANERADAR-plane-radar-app.md)
> Closes: OQ4 (side strip vs on-disc bezel); freezes layout + tag-collision rule before firmware
> Depends: phase0-api-probe (fixtures; live mode reuses the probe's fetch)

## Context / pain points

The reference renderer (`radar_display.cpp`, 714 lines) was designed for a
**round** 240×240 display: N/S/E/W letters at the bezel, range label on the
east spoke, tags placed toward the centre. Our canvas is a **rectangular**
275×240 (taskbar at x:275..319) — the disc gains a 35 px side strip and loses
the physical round bezel. Every layout judgement this implies (what moves to
the strip, how tags avoid each other on a busier default location, how rim
dots read on a square canvas) is cheap to iterate in pygame and expensive on a
flash-cycle loop. M-TELETEXT proved the pattern: its preview tool closed all
four of its open layout questions before firmware started.

## Goals

1. `app/tools/preview_planeradar.py` on `preview_common.py`
   (M-PREVIEW-FRAMEWORK): full 320×240 render including taskbar, 1×/2×/3×
   zoom, PNG/GIF export.
2. Close OQ4 with side-by-side screenshots: side-strip layout vs
   reference-style on-disc furniture.
3. Freeze: disc geometry, strip content, tag-placement + collision rule,
   rim-dot treatment, runway/label rendering, colors — as a constants block
   ready to transcribe into a firmware header.
4. Interaction model rehearsal: tap-to-cycle-range feel at real cadence
   (fixture sequence playback), stale-data indicator.

## Design

### Design space — canvas geometry (two variants; lean = strip, the tool decides)

```
canvas 275×240 (full-screen rule — memory: all non-Spotify apps y:0..239)
disc   centre (120,120), radius 118   → x:2..238
strip  x:240..274 (35 px)             → range label, fetch status/error code,
                                        aircraft count, stale-age indicator
```

Alternative under test for OQ4: disc centre (137,120) with on-disc N/E/S/W and
east-spoke range label (straight port of reference furniture), no strip. The
strip variant is the expected winner (error codes and staleness need a home
that doesn't collide with traffic), but the tool decides, not this doc.

### Rendering parity rules

The tool must render only what TFT_eSPI can render cheaply, so what you
preview is what you ship:

- RGB565 palette from `radar_theme.h` equivalents (dark-blue field, subdued
  green rings/crosshair, red triangles, magenta vectors, teal runways) —
  stored once as (r,g,b) tuples with their RGB565 values alongside.
- No anti-aliasing, no alpha. Lines via integer Bresenham-equivalent
  (`pygame.draw.line` width 1), triangle = 3-line polygon fill.
- Fonts: render with the project's baked-font bitmaps (as
  `preview_teletext.py` does) — not system TTF — so tag/label footprints are
  pixel-accurate.

### Data sources (three, switchable)

1. **Fixture replay** (default, deterministic): single fixture or a directory
   sequence at simulated 10 s cadence (accelerated ×N for iteration).
2. **Live**: import the fetch from `pr_adsb_probe.py` (probe exposes a
   `fetch(lat, lon, dist_nm)` function precisely so the tool can reuse it).
3. **Synthetic**: parametric generator (M inbound aircraft, crossing tracks,
   one hovering at ring edge, one beyond fetch radius) for animation checks —
   symbol erase/redraw correctness, ring-crossing transition (rim dot → full
   symbol), tag flip when an aircraft crosses the E/W axis.

### Design questions the tool must answer (the OQ4 block)

| # | Question | Candidates |
|---|---|---|
| Q1 | Strip vs on-disc furniture | see geometry above |
| Q2 | Tag collision rule | (a) reference rule only (centre-side placement); (b) + vertical nudge on overlap; (c) + drop tag, keep symbol, when nudge fails |
| Q3 | Rim-dot treatment on a square canvas | dots on disc rim (reference) vs on canvas edge at true bearing |
| Q4 | Runway label density at 25 km over Schiphol | all ICAO labels vs nearest-only vs toggle-off default |
| Q5 | Stale-data indicator form | strip age text (`12s`) vs dimming sweep vs ring colour shift (M-DRIFT pattern says: visible but not alarming) |
| Q6 | Whole-degree heading rendering | confirm 1° steps look smooth at r≤118 px (phase0-parse-heap OQ) |

Each closes with a screenshot pair committed under
`docs/architecture/designs/M-PLANERADAR/img/` and a one-line decision in
Results.

### Keyboard/mouse map (host stand-ins for touch)

| Input | Maps to |
|---|---|
| Click on disc | tap → cycle range preset (the firmware gesture) |
| `f` | next fixture in sequence |
| `s` | toggle synthetic mode |
| `1/2/3` | zoom |
| `g` | record GIF (via `preview_common.write_gif`) |
| `p` | save PNG screenshot |

## Open questions

- Does the strip need a fetch-in-flight spinner distinct from the stale-age
  indicator, or is `hasPendingAsync`'s shell busy cue enough? (Tool mocks
  both; decision recorded in Results.)

## Exit criteria

1. Tool runs from the venv, renders fixtures + synthetic + live, exports
   PNG/GIF; committed with the M-PREVIEW-FRAMEWORK conventions.
2. Q1–Q6 each closed with committed screenshot evidence and a decision line.
3. Layout constants block (disc centre/radius, strip rects, tag offsets,
   colors as RGB565) frozen in this doc's Results — transcription-ready for
   the firmware header.
4. Animation check on synthetic mode: ring-crossing, tag flip, erase/redraw
   leave no artefacts at 1× zoom.
5. Human eyeball sign-off on the winning layout (this is a looks judgement —
   same as M-VIS's "looks great" gate).

## Results

> Tool built + first render pass 2026-07-10. Interactive session with human
> eyeball (exit criterion 5) still pending — the committed screenshots are the
> evidence base for it.

### Run 1 (headless `--shot` mode, 16 PNGs in `img/`)

Rendered: Q1 both layouts × Q2 all three collision rules × {real morning-wave
busy fixture, synthetic}; Q3 both rim-dot modes. Font = firmware Font1 via
`dut_fonts.py` (pixel-accurate footprints).

Observations for the interactive session:

1. **Center tag pile-up** — on the busy fixture, aircraft stacked near the
   centre defeat rule (b)'s ±10/±20 px vertical nudge (two tags interleave
   illegibly). Q2 likely needs (c) drop-on-fail, or a bigger nudge ladder —
   compare `q1_strip_coll-b_…` vs `coll-c_…`.
2. **Speed vectors are not ring-clipped** — caught in run 1, fixed same
   session (binary clip at the outer ring, reference parity); all PNGs
   re-rendered with the fix.
3. **Real-data quirk caught**: a `-200 ft` altitude tag (below-sea-level NL
   traffic / baro offset) rendered fine — negative altitudes are real inputs
   the firmware formatter must accept.
4. Strip layout reads well at 10 km on the busy fixture (range, `Nac` count,
   staleness slot all legible); disc layout's east-spoke `10km` label collides
   with the `E` bezel letter — point against the disc variant, to confirm
   interactively.
5. Rim dots (Q3 disc-rim mode) read clearly as a bearing cue on the busy
   fixture ring.

### Pending

Interactive Q1–Q6 closure with screenshots per decision, layout-constants
freeze, animation/GIF check, human sign-off.
