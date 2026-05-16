# Design — M-VIS Visualization Area

> Owner: Developer
> Status: planned (2026-05-15)
> Tracked-as: TASK-050a–c
> Deps: M6 (VU mode + envelope engine), TASK-049 (SKIN_MAIN_BG restore pattern)

## Scope

Replace fixed synthetic VU meter with tap-cycling visualizer in the confirmed vis area `(x=24, y=43, w=76, h=13 px)`. Tap cycles: **VU → Spectrum → Wave → Blank → VU**. No new API calls — all views derive from existing synthetic envelope engine (`lLvl`, `rLvl`, beat phase, LFO) in `vuMeter.h`.

## Vis area geometry

```
window-local: x=24, y=43, w=76, h=13
VU left bar:  y=43..48  (6px)
gap row:      y=49       from SKIN_MAIN_BG
VU right bar: y=50..55  (6px)
wave midline: y=49 (centre)
```

## Mode specs

**Spectrum:** 38 bars × 2px wide, full 76px (Winamp 2 main-window default). Colours: green 0–50% height, yellow 50–80%, red 80–100%. Static `shape[38]` pink-noise rolloff table (`1 - i/37 × 0.6`). Beat transient injected into low bins (i < 8). Peak dot (1×1 px) per bar rises instantly, falls ~1 px/100 ms.

**Wave:** `y[x] = centre + round(lLvl × 5 × sin(φ + x × 2.5 × 2π / 76))`. Phase `φ` advances +0.3 rad/tick (20 Hz). Restore `SKIN_MAIN_BG` before each frame; draw single green pixels.

**Blank:** restore `SKIN_MAIN_BG` to vis area, then idle.

**Background restore (all modes):** blit `SKIN_MAIN_BG` rows for vis area before draw (same pattern as TASK-049).

## Sub-tasks

| Task | Scope |
|---|---|
| TASK-050a | `VisMode` enum + `nextMode()` + vis hit-test + touch dispatch + blank mode |
| TASK-050b | Spectrum: bin synthesis, bar render, peak dots |
| TASK-050c | Wave: phase-advancing sine, single-pixel line |

## Exit criteria

- Tapping vis area cycles VU → Spectrum → Wave → Blank → VU on DUT.
- Spectrum: 38 bars, green→yellow→red by height, peak dots visible and decaying.
- Wave: smooth sine, amplitude tracks playback level, flat when paused.
- Blank: vis area shows skin background texture only.
- VU mode unchanged (regression check).
- Vis hit-test does not overlap existing touch zones.
- Flash delta ≤ +1% on `cyd2usb_winamp`.
