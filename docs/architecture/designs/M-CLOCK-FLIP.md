# M-CLOCK-FLIP — Flip Clock Renderer Physics

> Owner: Architect  
> Status: design — not started  
> Date: 2026-06-13  
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

| # | Op | Region | Notes |
|---|-----|--------|-------|
| 1 | Panel background | Full panel rect | Dark gray, corner radius `R` |
| 2 | Top half content | Clip `y=[0, mid)` | Full digit glyph at panel centre, lighter tone |
| 3 | Bottom half content | Clip `y=[mid, h)` | Same digit, slightly darker tone |
| 4 | Gradient overlay | Both halves | Subtle luminance ramp — adds depth without texture |
| 5 | Split line | `y=mid`, 1–2 px | Near-black bar; the hinge gap |

Top-half fill is `BG_TOP`; bottom-half fill is `BG_BOT` (`BG_BOT` is ~10% darker
than `BG_TOP`). Gradient is a 4-stop linear overlay from the panel edges inward;
amplitude ≤ 15% — aim for depth, not contrast.

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

| frame | t    | flap_h (half=30 px) | content on flap | bottom plate |
|-------|------|---------------------|-----------------|--------------|
| 0     | —    | 30 (stable)         | OLD top         | OLD bottom   |
| 1     | 0.20 | 24                  | OLD top clipped | NEW bottom   |
| 2     | 0.40 | 10                  | OLD top clipped | NEW bottom   |
| 3     | 0.60 | 10                  | NEW top clipped | NEW bottom   |
| 4     | 0.80 | 24                  | NEW top clipped | NEW bottom   |
| 5→0   | 1.0  | 30 (stable)         | NEW top         | NEW bottom   |

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
6. [× 4] Split line          (always, drawn after flap so it's crisp)
7. [× 4] Gradient overlay    (optional depth pass)
8. Colon separator           (two filled squares, static)
9. Date label                (small text below panels)
```

---

## Parameters

| Parameter | Symbol | Proposed value | Drives |
|-----------|--------|---------------|--------|
| Panel width | `P_W` | 46 px | Card geometry |
| Panel height | `P_H` | 62 px | Card geometry |
| Split y (within panel) | `MID` | 30 px | `P_H/2` minus 1 (2 px gap) |
| Gap line height | `GAP` | 2 px | Hinge illusion |
| Corner radius | `R` | 5 px | Panel feel |
| Inter-panel gap | `GUTTER` | 4 px | Spacing |
| Top half background | `BG_TOP` | `0x2945` | Warm dark |
| Bottom half background | `BG_BOT` | `0x18C3` | Slightly darker |
| Digit colour | `C_DIGIT` | `0xFFF0` | Warm cream white |
| Split line colour | `C_SPLIT` | `0x0861` | Near-black |
| Panel border colour | `C_BORDER` | `0x4208` | Subtle edge |
| Flip duration | `FLIP_MS` | 150 ms | 5 frames × 30 ms |
| Frame interval (animating) | — | 30 ms (≈33 fps) | `tick()` gate |
| Shadow height (phase 1) | — | 8 px max | Depth drama |
| Gradient amplitude | — | ≤15% luminance | Depth, not contrast |

All values are initial proposals. Phase 0 (`preview_clock.py --style flip`)
is the authoritative tuning session — approved values replace these.

---

## Colon separator

Two filled squares, fixed, no blink (split-flap displays do not blank the
colon). Positioned in the gutter between the HH and MM pairs.

```
Square size: 5 × 5 px
Colour: C_DIGIT (0xFFF0)
Position: centred horizontally in colon gutter
  top dot:    y = panel_top + 12
  bottom dot: y = panel_top + 44
```

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
