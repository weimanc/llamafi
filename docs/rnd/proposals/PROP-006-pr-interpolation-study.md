# PROP-006 — PlaneRadar interpolation study: samples × algorithm on host

> Owner: R&D Engineer
> Status: **CONCLUDED 2026-07-19 — VALIDATED** (see
> [EXP-014](../reports/EXP-014-pr-interpolation.md)): dr-damped(tau=2),
> depth 1; human eyeball sign-off on synthetic; capture session descoped by
> human decision (mechanism argument + production DUT phase runs on the live
> feed anyway — EXP-014 caveat 1). Production task: TASK-357.
> Was: registered 2026-07-18 (human-commissioned; PM tracked as TASK-356)
> Branch: `rnd/pr-interp` (host tooling only; no firmware)
> Companion: M-PR-MOTION.md item B (Architect framing + graduation constraints)

## Question

Which combination of **per-aircraft history depth (1–3 samples)** and
**interpolation algorithm** gives the smoothest perceived motion on the
275×240 radar view, across poll cadences 1/5/10/15/30 s (the new
`prPollSec` slider range)?

## Method

1. **Capture ground truth** — adsb.fi JSON at ~1 s for 10–15 min over a
   busy preset (LHR fixture slots exist). ⚠ 429-budget protocol: run from a
   network that is not the DUT's egress IP, or in a declared DUT-quiet
   window; one bounded session, save raw responses as fixtures under
   `docs/rnd/reports/fixtures/` (gitignore-size permitting) so the sweep
   never refetches.
2. **Reconstruct** — downsample ground truth to each cadence; feed each
   algorithm × depth; render with a pygame harness (M-PREVIEW-FRAMEWORK
   conventions, venv has pygame) side-by-side with ground truth.
3. **Score** — RMS position error in *display pixels* per range preset; max
   correction jump in px (the teleport artifact — likely the dominant
   perceptual defect); heading jitter. Then the human eyeball pass — the
   real acceptance criterion.

## Algorithm ladder (cheap-first)

| # | Algorithm | History | Latency | Note |
|---|---|---|---|---|
| 1 | Dead-reckon (track+gs), snap correction | 1 | none | the original M-PLANERADAR follow-up idea |
| 2 | Dead-reckon + damped correction (alpha-beta blend) | 1 | none | expected sweet spot — kills teleports |
| 3 | Linear lerp, one poll delayed | 2 | 1 poll | smooth but stale by a full interval |
| 4 | Catmull-Rom, delayed | 3 | 1–2 polls | only if 2 loses the eyeball vote |

Stop descending the ladder as soon as a rung is eyeball-smooth at 10 s —
report the rest as not-needed.

## Kill / honesty gates

- If rung 1 or 2 is indistinguishable from 3–4 at default cadence, say so —
  simplest wins; graduation proposal recommends the cheapest smooth option.
- If nothing looks smooth at 30 s, report that too (sets a floor on useful
  slider values — feeds back into the prPollSec UI copy).
- Graduation constraints from M-PR-MOTION.md apply to the recommendation:
  fixed-point-friendly, bounded per-tick for ~20 aircraft, low-KB history
  RAM, sane stale-data behaviour (`prStaleStyle` interplay).

## Deliverables

EXP report (`docs/rnd/reports/EXP-0xx-pr-interpolation.md`) with the score
matrix + animated-preview screenshots, the fixture set, and — if a rung
validates — a graduation proposal naming algorithm, depth, and correction
policy. Production firmware is out of scope; PM files it after human review.
