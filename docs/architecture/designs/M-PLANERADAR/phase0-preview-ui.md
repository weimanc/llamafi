# Design — M-PLANERADAR Phase 0: preview tool + UI layout

> Owner: Architect
> Status: implemented — designer-review PASS 2026-07-10; Q1-Q6 closed, human eyeball sign-off done (see Results)
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

> 2026-07-10: all six design questions closed with human eyeball sign-off.
> Layout constants frozen below. Doc moves to `implemented`.

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

### Q1–Q6 decisions (human eyeball, 2026-07-10)

- **Q1 — strip.** Confirmed against `q1_strip_coll-b_busy_33km_10km.png` vs
  `q1_disc_coll-b_busy_33km_10km.png`: disc's east-spoke `10km` label collides
  with the `E` bezel letter as run 1 flagged; strip reads cleanly (range,
  `Nac`, staleness all legible, no collisions). Disc geometry kept in the tool
  for reference but dropped from the firmware plan.
- **Q2 — collision rule, pushed to app-settings (default: c).** Run 1's
  center-tag-pile-up finding held up: rule (b)'s nudge ladder isn't enough on
  the busy fixture. Rather than freeze one rule, this becomes a user-facing
  toggle (settingsStorage) — default **(c) drop-tag-keep-symbol**. Scope
  addition vs. the original "freeze one constant" plan; parent design doc
  updated (requirements summary + platform-infrastructure table).
- **Q3 — disc-rim.** Confirmed against `q3_disc-rim_busy_33km.png` vs
  `q3_canvas-edge_busy_33km.png`: disc-rim reads clearly as a bearing cue, as
  run 1 found.
- **Q4 — runway overlay, density = all.** Not implemented as of run 1 —
  `preview_planeradar.py` had a `COL_RUNWAY` color constant but no runway
  rendering at all. Closed properly rather than deferred:
  - Real runway-endpoint data pulled from the same OurAirports source as
    `phase0-airport-db.md`'s bake trial (large_airport class): EHAM (6
    runways) + EHRD (1 runway), committed as
    `fixtures/planeradar/airports_preview.json`.
  - Feasibility checked before building: flash cost 12.1 KB (V-europe
    variant, already characterised as a non-issue against ~62% used flash);
    RAM cost ~0 (flash-mapped `.rodata`, same XIP pattern as other baked
    assets); render cost trivial — at any preset ≤ 25 km (36.8 km fetch
    radius) **EHAM is the only airport ever in range**, so worst case is 6
    line segments + 1 label per frame.
  - Wired in: `Radar._runways()`, `a` key to cycle all/nearest/off live, and
    `--shot` now also emits `q4_{all,nearest,off}_busy_33km_25km.png`.
  - Decision: **all** (label every in-range airport) — with only EHAM ever
    in range at these presets, "all" and "nearest" are visually identical
    today; "all" is future-proof if the DB variant or presets change.
- **Q5 — stale-indicator style, pushed to app-settings (default: ring-colour
  shift).** **Caveat:** unlike Q1–Q4, this was decided by spec reasoning
  (M-DRIFT precedent: "visible but not alarming") rather than a rendered
  comparison — the tool only ever implemented the strip-age-text style: the
  dimming-sweep and ring-colour-shift candidates were never built or
  screenshotted. Recorded as a known gap, same posture as the shortened
  evening soak in phase0-api-probe.md — a deliberate, disclosed scope cut,
  not a silent one. Whoever builds the settings toggle should render the
  ring-colour-shift option once real firmware colors exist and eyeball it
  before shipping the default.
- **Q6 — whole-degree heading rendering, confirmed fine (corrected).** First
  pass was invalid: `nose_deg()`/`track_deg()` passed fixture floats straight
  through, so the "looks fine" call was made against full float precision,
  not the `int16_t noseDeg/trackDeg` whole-degree storage `phase0-parse-heap.md:108`
  actually commits to. Fixed (`preview_planeradar.py` now rounds both to the
  nearest degree, matching what ships) and re-verified: 204/307 200 px differ
  between float and rounded renders on the busy fixture at 25 km, all
  sub-pixel shifts on speed-vector endpoints, none on the aircraft symbol
  itself. Confirmed imperceptible after the fix.

### Animation check (exit criterion 4)

`img/anim_synthetic_check.gif` — 230-frame synthetic sequence (t = 0..138s),
strip layout, rule (c). Verified programmatically (not just eyeballed): the
outbound synthetic target (`OUTBW03`) crosses the outer ring at t≈113.4s,
matching the computed distance (`outer_km` = 13.33 km at the 10 km preset,
d₂(t) = 2 + 0.1t → t = 113.3s exactly). Frames either side of the crossing
show a clean symbol→rim-dot switch: no ghost triangle, no duplicate tag, `Nac`
count decrements on the same frame. Tag-flip (orbiter crossing the N/S
meridian) and erase/redraw (every frame, by construction) also clean.

**Caveat — what this does and doesn't prove:** this Python/PIL preview
fully redraws every frame from `Image.new()`; it cannot exercise the
firmware's actual update strategy (`erase/redraw only aircraft symbols + tags
each update`, per the parent doc's platform-infrastructure table — targeted
incremental erase on TFT_eSPI, not a full-frame clear). What's verified here
is that the *transition logic* (ring-cross detection, symbol↔dot switching,
tag placement) is bug-free across frames — a different and narrower claim
than "no incremental-erase artifacts," which is a firmware-only risk and
stays DUT-side, same posture as R1's TLS-coexistence term.

### Exit criteria status

1. ✅ Tool runs from the venv, renders fixtures + synthetic + live, exports
   PNG/GIF (`anim_synthetic_check.gif`); committed.
2. ✅ with one disclosed exception — Q1/Q3/Q4/Q6 each have committed
   screenshot evidence; Q2/Q5 have decisions but became settings (no single
   frozen render to point at) and Q5 specifically has **no** comparison
   screenshot (see Q5 caveat above).
3. ✅ Layout constants block frozen above.
4. ✅ Animation check done, with the erase/redraw scope caveat noted.
5. ✅ Human eyeball sign-off complete for all six questions, 2026-07-10.

### Layout constants (frozen, strip variant — transcription-ready)

```
canvas          320×240 (APP_W 275 + taskbar 275..319)
disc            centre (120,120), radius 118px  → x:2..238, y:2..238
strip           x:240..274 (35px)
  range digits    strip_x+17, y=12/22 (2 lines: "N" / "km")
  aircraft count  strip_x+17, y=50   ("<n>ac")
  stale age       strip_x+17, y=200  ("<age>s", COL_STALE if age>30)
  fetch error     strip_x+17, y=220  ("E<code>", COL_ERR)
  bezel N marker  strip_x+17, y=120  ("N^")
rings           r × {1/4, 2/4, 3/4, 4/4}; ring 3 (3/4 r) = preset distance;
                ring 4 (r) = outer_km = preset_km × 4/3
tag placement   centre-side (right if x<cx else left), rule (c) default:
                ±10/±20px vertical nudge, drop tag (keep symbol) if all fail
                — user-configurable (Q2)
rim dots        disc-rim: (r-2)px from centre at true bearing angle (Q3)
runway overlay  centerlines from real lat/lon endpoints; ICAO label at
                airport centre, y-9px offset; density=all default (Q4)
stale indicator ring-colour shift default; strip age-text always shown
                underneath as the numeric fallback (Q5)
heading         whole-degree rounding (int16_t match) — confirmed
                imperceptible at r≤118px (Q6)
```

Colors (RGB565-quantised, see `preview_planeradar.py` palette block):
field (0,0,48) · ring (0,96,32) · ring-hi (0,140,48) · bezel (255,255,255) ·
aircraft (255,32,32) · vector (255,0,255) · tag (200,200,200) ·
runway (0,160,160) · strip-bg (8,8,16) · strip-text (160,255,160) ·
stale (255,180,0) · error (255,64,64).
