# M-CLOCK-FLIP — Flip Clock Renderer Physics

> Owner: Architect  
> Status: shipped (TASK-193, 2026-06-13 — `ClockApp::_drawFlip()` in `app/src/clockApp.h`);
> **bug-fixed + polished (TASK-337, 2026-07-18)**; **resynced to the
> `preview_clock.py`/`_clock_flip.py` concept tool (TASK-337 follow-up,
> 2026-07-18)**. TASK-193 had a real rendering bug — each half-card drew
> the *full* digit glyph with no clipping, so a digit rendered whole
> twice, stacked (reported as "each digit is shown twice"). Fixed via
> `tft.setViewport()` clipping around a shared split-line anchor —
> matches this doc's intended physical model (each half-card shows only
> its half of one glyph). Colon is no longer static squares — now round
> dots blinking at 1Hz (still **not** the animated 45°-rotating flip-dot
> disc described below — that needs a tick-gate architecture change for
> the 500ms cadence, deferred).
>
> **Second pass superseded the gradient.** TASK-337's first pass added
> the 4-stop luminance-ramp gradient this doc originally specified
> (§"Static render" below) and it was DUT-verified pixel-exact — but
> when checked side-by-side against `preview_clock.py` (the tool this
> doc's own Parameters section names as "the authoritative tuning
> session"), the concept never actually used a gradient at all: it draws
> **flat** `C_TOP`/`C_BOT` per half-card plus a 3-tone hinge bevel
> (shadow / dark groove / highlight — see updated Parameters table). The
> gradient values below had been carried through as "proposed" without
> ever running that tuning pass for card colour — only the colon disc
> got it. User chose "match the concept" over the already-implemented
> gradient — the gradient/`_scaleColor565` code was **removed**, replaced
> with the concept's flat-fill + bevel pipeline, and panel geometry
> (`P_W/P_H/MID/R`, panel `x` positions) resynced to the concept's exact
> pixel constants too. Digit colour switched from amber (`0xFFF0`) to the
> concept's warm-white (`0xF79D`). DUT-verified pixel-exact via
> `screendump` post-TASK-340. Font-6 digit swap (from the original
> TASK-337 pass) retained; sizing/position still open per user feedback,
> see TASK-337 in `docs/project/tasks.md`.  
> Date: 2026-06-14 (last updated 2026-07-18)  
> Part of: [M-CLOCK-STYLES.md](M-CLOCK-STYLES.md) — Style 1  
> See also: [clock.md](M-MULTIAPP/clock.md)

---

## Purpose

Detailed render physics for the split-flap flip clock style. The high-level
milestone (style enum, dispatch, settings wiring, Phase 0 concept tool) lives
in `M-CLOCK-STYLES.md`. This doc covers the per-digit layer model, animation
geometry, and parameter table that the implementation must follow.

---

## Visual anatomy

```
┌──────────────────────────────────────────────┐  ← clock body
│  ┌────┐  ┌────┐       ┌────┐  ┌────┐         │
│  │ 0  │  │ 8  │  · ·  │ 4  │  │ 2  │         │
│  └────┘  └────┘       └────┘  └────┘         │
│               THU 12 JUN 2026                 │
└──────────────────────────────────────────────┘
```

Each digit panel:

```
┌──────────────────┐  ← panel bg  (dark gray, rounded-rect)
│   TOP HALF       │  ← upper digit half  (lighter gradient top→mid)
├──────────────────┤  ← split line  (1–2 px, near-black)
│   BOTTOM HALF    │  ← lower digit half  (darker gradient mid→bottom)
└──────────────────┘
```

---

## Static render — per panel, 5 draw ops (back → front)

> **Superseded 2026-07-18** (see status header): the gradient overlay (row 4
> below) was implemented, DUT-verified, then **removed** — the concept tool
> this doc defers to for approved values never actually used a gradient.
> Op 4 is now a flat fill (no overlay pass) plus a 3-tone hinge bevel drawn
> as part of the split line (see updated Parameters table).

| # | Op | Region | Notes |
|---|-----|--------|-------|
| 1 | Panel background | Full panel rect | Dark gray, corner radius `R` |
| 2 | Top half content | Clip `y=[0, mid)` | Full digit glyph at panel centre, `BG_TOP` fill |
| 3 | Bottom half content | Clip `y=[mid, h)` | Same digit, `BG_BOT` fill (flat, no gradient) |
| 4 | ~~Gradient overlay~~ | — | **Removed** — concept uses flat fills, not a ramp |
| 5 | Split line (3-tone bevel) | `y=mid-1..mid+GAP-1` | Shadow row / dark groove / highlight row — see `C_SPLIT_*` |

Top-half fill is flat `BG_TOP`; bottom-half fill is flat `BG_BOT` — no gradient
ramp. Depth instead comes from the 3-row hinge bevel: a 1px shadow row at the
base of the top flap, the dark groove fill, and a 1px highlight row at the
crown of the bottom plate.

---

## The flip mechanism — fundamental constraint

> **Only the top flap moves.** The bottom plate always shows the new digit's
> bottom half. It was pre-positioned before the animation started.

```
t = 0.0   [OLD_top | OLD_bot]   ← fully stable
          ─────────────────────
t = 0.25  [OLD_top ↓ shrinking | NEW_bot visible behind]
t = 0.50  [flap edge-on (0 px) | NEW_bot]
          ─────────────────────
t = 0.75  [NEW_top ↑ growing   | NEW_bot]
t = 1.0   [NEW_top | NEW_bot]   ← fully stable
```

The bottom plate flips to `NEW` the instant the animation starts. The falling
top flap hides this transition in the first frames, so the switch is invisible.

---

## Flap height formula

```
half = panel_h / 2

Phase 1  (t = 0.0 → 0.5)  OLD digit falling:
    flap_h = half * cos(t * π)          # half → 0

Phase 2  (t = 0.5 → 1.0)  NEW digit rising:
    flap_h = half * cos((1.0 - t) * π)  # 0 → half
```

`cos` gives natural ease-in / ease-out without a separate easing function.
The flap is always **anchored at the split line** and extends upward — its
bottom edge is pinned at `mid_y`, its top edge moves.

### Discrete frame table (5-frame approximation)

For firmware (no float trig), sample the formula at 5 even steps:

| frame | t    | flap_h (half=38 px, resynced 2026-07-18) | content on flap | bottom plate |
|-------|------|-------------------------------------------|-----------------|--------------|
| 0     | —    | 38 (stable)         | OLD top         | OLD bottom   |
| 1     | 0.20 | 30                  | OLD top clipped | NEW bottom   |
| 2     | 0.40 | 13                  | OLD top clipped | NEW bottom   |
| 3     | 0.60 | 13                  | NEW top clipped | NEW bottom   |
| 4     | 0.80 | 30                  | NEW top clipped | NEW bottom   |
| 5→0   | 1.0  | 38 (stable)         | NEW top         | NEW bottom   |

"Clipped" = digit drawn into the flap rect at full scale; TFT `setClipRect`
masks the overflow. The digit is not stretched — only the visible window shrinks.

---

## Animation render pipeline (per active digit, per frame)

Draw in this order each frame while `frame > 0`:

```
1. Panel background          (full panel rect, always)
2. Bottom plate              (new digit, lower half, static)
3. Drop shadow               (phase 1 only: gradient rect from flap bottom
                              edge downward, alpha ∝ (1 - t/0.5))
4. Flap rect background      (BG_TOP fill, height = flap_h, anchored at mid)
5. Flap digit content        (digit glyph, clipped to flap rect)
6. Split line                (1–2 px near-black bar at mid_y, always on top)
```

Shadow is a filled rect `[mid_y, mid_y + shadow_h]` where
`shadow_h = 8 px * (1 - t*2)` in phase 1, zero in phase 2.
Colour: `0x0000` (black) at ~40% alpha — simulate via a blended fill or a
darkened version of `BG_BOT`.

---

## Full-screen render pipeline (back → front)

```
1. Clock body                (dark charcoal rounded-rect, full canvas region)
2. [× 4] Panel background    (per digit)
3. [× 4] Bottom plate        (per digit, static or new digit if animating)
4. [× 4] Shadow rect         (animating digits only)
5. [× 4] Flap rect           (animating: clipped old/new; stable: full top half)
6. [× 4] Split line (3-tone bevel) (always, drawn after flap so it's crisp)
7. ~~Gradient overlay~~      (removed 2026-07-18 — concept uses flat fills)
8. Colon separator           (two round flip-dots, blink 1Hz)
9. Date label                (small text below panels)
```

---

## Parameters

| Parameter | Symbol | Value | Drives |
|-----------|--------|---------------|--------|
| Panel width | `P_W` | 56 px | Card geometry — **approved from concept, 2026-07-18** |
| Panel height | `P_H` | 78 px | Card geometry — **approved from concept, 2026-07-18** |
| Split y (within panel) | `MID` | 38 px | `P_H/2` minus 1 (2 px gap) |
| Gap line height | `GAP` | 2 px | Hinge illusion |
| Corner radius | `R` | 6 px | Panel feel — **approved from concept, 2026-07-18** |
| Inter-panel gap | `GUTTER` | 4 px | Spacing (18 px at the colon gutter) |
| Top half background | `BG_TOP` | `0x31A7` | Concept `C_TOP` (55,55,62), flat fill — **approved from concept, 2026-07-18** |
| Bottom half background | `BG_BOT` | `0x2945` | Concept `C_BOT` (40,40,46), flat fill — **approved from concept, 2026-07-18** |
| Digit colour | `C_DIGIT` | `0xF79D` | Concept `C_TEXT` (242,242,235), warm white — **approved from concept, 2026-07-18** |
| Split — shadow row | `C_SPLIT_EDGE_TOP` | `0x1082` | Concept (18,18,20) — 1px shadow at base of top flap |
| Split — groove fill | `C_SPLIT_GAP` | `0x0020` | Concept (5,5,6) — dark groove |
| Split — highlight row | `C_SPLIT_EDGE_BOT` | `0x4A4A` | Concept (72,72,84) — 1px highlight at crown of bottom plate |
| Panel border colour | `C_BORDER` | `0x4A4B` | Concept `C_OUTLINE` (75,75,88) — **approved from concept, 2026-07-18** |
| Clock body / housing | — | `0x0841` | Concept housing bg (10,10,12) — **approved from concept, 2026-07-18** |
| Flip duration | `FLIP_MS` | 150 ms | 5 frames × 30 ms |
| Frame interval (animating) | — | 30 ms (≈33 fps) | `tick()` gate |
| Shadow height (falling flap) | — | `max(2, flap_h/4)` px, flat black | Concept formula — **approved from concept, 2026-07-18** |
| ~~Gradient amplitude~~ | — | **removed** | Concept uses flat fills, not a luminance ramp |

Geometry, card colours, split-bevel colours, border, housing colour, and the
shadow-height formula were re-derived directly from
`app/tools/_clock_flip.py`'s `FlipRenderer` (the concept tool this doc
originally deferred to but whose card-colour tuning pass was never actually
run) and ported to RGB565 — see the 2026-07-18 status-header entry. Values
marked "approved from concept" replace the original initial proposals.

---

## Colon separator — flip-dot style (proposed; partially shipped)

> **Known accepted cosmetic deviation, updated 2026-07-18 (TASK-337).**
> This section describes the original animated-disc design. TASK-193
> originally shipped two fully **static** `5×5` filled squares — no
> rotation, no blink, no ON/OFF cadence at all. TASK-337 fixed the "never
> blinks" part: the colon is now two `fillCircle` dots (round, not square)
> blinking at **1 Hz** using `t.tm_sec` parity — the same cadence Digital
> style's colon already uses. The **animated 45°-rotating disc** and its
> **500 ms ON / 500 ms OFF** cadence below are still not implemented —
> that would need the tick gate to run at ≤500ms even when no digit is
> flipping (currently 1000ms when idle), an architecture change judged
> out of scope for a polish pass. Retained here as a documented future
> enhancement beyond the current round dots.

The colon uses **animated flip-dot discs**, not static squares. Each dot is a
circular disc that rotates on a 45° diagonal axis, showing a cream-white front
face when ON and a near-black back face when OFF. The blink cadence is
**500 ms ON / 500 ms OFF** (matches a mechanical flip-dot display rhythm).

### Geometry

```
Disc radius:     5 px  (10 px diameter — fits the 18 px colon gutter)
Rotation axis:   45° diagonal
Animation:       80 ms mechanical flip (cos-based foreshortening)
Position:        centred horizontally in colon gutter (cx ≈ 138)
  top dot:    y = panel_top + 16
  bottom dot: y = panel_top + 44
```

### Flip-dot animation

The disc is rendered as a foreshortened ellipse. At rotation angle `θ` (0 =
front face, π = back face):

```
semi_a = DOT_R                       # constant — horizontal extent
semi_b = |cos(θ)| × DOT_R           # collapses to 0 at θ = π/2 (edge-on)
```

When `semi_b < 1 px` (edge-on), draw only the 45° hairline axis in rim colour.
Otherwise draw a filled polygon with 48 vertices, colour = front or back face
depending on sign of `cos(θ)`.

```
ON  transition (back → front):  θ: π → 0  over COLON_FLIP_MS
OFF transition (front → back):  θ: 0 → π  over COLON_FLIP_MS
```

### Colour constants (approved from preview_clock.py)

| Symbol | RGB | Notes |
|--------|-----|-------|
| `C_COLON_FRONT` | (232, 224, 208) | Disc front face — cream white |
| `C_COLON_BACK`  | (30, 29, 36)    | Disc back face — near black |
| `C_COLON_RIM`   | (88, 84, 100)   | Disc rim / edge-on hairline |
| `COLON_DOT_R`   | 5 px            | Disc radius |
| `COLON_FLIP_MS` | 80 ms           | Mechanical flip duration |

---

## Sub-second tick (firmware)

The flip animation requires ~30 ms granularity. The existing 1 000 ms gate
must be narrowed while any digit is animating.

```cpp
void tick() override {
    unsigned long now  = millis();
    bool flipping      = _anyFlipActive();
    unsigned long gate = flipping ? 30 : 1000;
    if (now - _lastTickMs < gate) return;
    _lastTickMs = now;

    drawFlip();
    if (!flipping) {
        drawSecondsBar();
        drawDate();
        drawRssi();
    }
}
```

`_anyFlipActive()` returns `true` if any `FlipDigit::frame > 0`.

When `drawFlip()` detects a digit change:
1. Set `fd.next = newDigit`, `fd.frame = 1`.
2. Set `fd.botShown = fd.next` immediately (bottom plate switches before the
   animation paints — the falling flap hides the instant swap).
3. Each subsequent call to `drawFlip()` increments `fd.frame`, renders the
   frame, and resets `fd.frame = 0` and `fd.shown = fd.next` at frame 5.

---

## `FlipDigit` struct

```cpp
struct FlipDigit {
    uint8_t shown;    // digit currently in top half (0..9)
    uint8_t next;     // digit to flip to
    uint8_t botShown; // digit shown in bottom half (may differ during frame 1)
    uint8_t frame;    // 0 = stable; 1..5 = animating
};
FlipDigit _fd[4];     // H1, H2, M1, M2
```

---

## Relationship to M-CLOCK-STYLES.md

`M-CLOCK-STYLES.md` owns:
- Phase 0 concept tool spec and approved constants block
- Style enum + dispatch stub
- Settings wiring
- Exit criteria C4 (flip animation timing)

This doc owns:
- Render physics (layer model, flap formula, pipeline order)
- Frame table
- Parameter table
- `FlipDigit` struct
- Sub-second tick design

When Phase 0 is complete, approved constants from `preview_clock.py --style flip`
override the proposed values in the **Parameters** table above and are also
copied into the **Approved constants** block in `M-CLOCK-STYLES.md`.
