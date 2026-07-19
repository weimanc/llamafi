# EXP-014 — PlaneRadar interpolation study (PROP-006 / TASK-356)

> R&D Engineer · 2026-07-19 · branch `rnd/pr-interp` (commits e1f61ff..b302033)
> Verdict: **VALIDATED — dr-damped(tau=2), history depth 1** (human eyeball
> sign-off 2026-07-19: "tau=2 is good enough")

## Question

Which interpolation algorithm × per-aircraft history depth gives the
smoothest perceived motion on the radar disc across poll cadences
1/5/10/15/30 s (the `prPollSec` slider range, TASK-355)?

## Method

Host rig under `app/tools/pr_interp/` on the rnd branch: synthetic ground
truth (5 manoeuvre scenarios: cruise, standard-rate turn, holding racetrack,
decelerating approach, accelerating climbout) sampled through
firmware-faithful quantization (whole-degree track, int knots, 8 m GPS
jitter, 5% dropout); four-rung ladder scored at 30 fps in display pixels
(118 px outer ring = preset × 4/3 km, matching `preview_planeradar.Radar`);
eyeball harness renders all 5 planes + all algorithms colour-coded on the
real radar chrome. Full matrix: `baseline_synth.md` on the branch.

## Results (10 s default cadence, mean over scenarios)

| algorithm | depth | RMS px | max jump px | note |
|---|---|---|---|---|
| dr-snap | 1 | 0.6 | **9.6** | accurate but teleports on every fix |
| **dr-damped(tau=2)** | **1** | **0.7** | **0.1** | winner — accuracy of DR, no teleport |
| dr-damped(tau=1) | 1 | 0.6 | 0.3 | leaks visible jump |
| dr-damped(tau=4) | 1 | 0.8 | 0.1 | no gain over tau=2, slower settle |
| delayed-lerp | 2 | 10.4 | 11.4 | one full interval stale |
| catmull-rom | 3 | 10.5 | 12.1 | never beats lerp → depth 3 unjustified |

Pattern holds at every cadence 1–30 s. At 30 s dr-damped degrades gracefully
(10 px RMS, 1.5 px jump) while delayed rungs reach ~45 px staleness.

## Caveats (recorded, dispositioned)

1. **Model-match bias:** synthetic truth integrates the same track+gs
   kinematics DR extrapolates, flattering absolute DR accuracy. Disposition:
   does not change the ranking or the mechanism — a *worse* real-world
   prediction produces *bigger* corrections, which is precisely what damped
   blending absorbs and snap does not. The 1 s ground-truth capture session
   (429-budget logistics) was therefore **descoped by human decision**; real-
   feed behaviour is verified instead during the production task's DUT
   phase, which runs on the live feed by construction.
2. Jitter metric has a near-freeze artifact on clamped lerp — used only as a
   tiebreaker, never load-bearing above.

## Graduation recommendation → TASK-357

Dead-reckon each aircraft from its last fix (track+gs — the firmware already
derives the vector for the speed line) and, on each new fix, decay the
rendered-vs-predicted offset exponentially with **tau = 2 s** instead of
snapping. Depth 1: state per aircraft = last fix + one 2-component offset —
no history arrays, fixed-point friendly, trivially bounded for ~20 aircraft.
Cap extrapolation when a fix goes stale (hand off to the existing
`prStaleStyle` treatment rather than flying a ghost). The real firmware cost
is not the math but the **repaint strategy**: smooth motion needs periodic
per-aircraft dirty-rect redraws (~10 Hz) instead of repaint-on-fetch — that
is the core design question TASK-357 must answer.

Process note: the rig's first cut wrongly rebuilt existing tools
(`pr_adsb_probe`, `preview_planeradar`, `preview_common`) standalone — caught
by the human, rebased in a24a9a1/509e725; the standalone version also
carried a ~1.5× projection-scale error the reused code prevented. Lesson
filed (inventory `app/tools/` first); LL candidate for QM.
