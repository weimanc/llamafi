# pr_interp — PROP-006 interpolation study rig (TASK-356)

Host-side study: which interpolation algorithm × history depth gives the
smoothest PlaneRadar motion across poll cadences 1/5/10/15/30 s
(the `prPollSec` slider range). See `docs/rnd/proposals/
PROP-006-pr-interpolation-study.md` and `docs/architecture/designs/
M-PR-MOTION.md` item B.

All tools run with the project venv: `~/proj/esp/venv/bin/python3`.

| file | what |
|---|---|
| `model.py` | Fix schema (mirrors firmware `PrAircraft` quantization), ENU + px projection |
| `synth.py` | synthetic ground truth: cruise / turn / holding / approach / climbout, 1 Hz sampling with whole-degree track, int knots, 8 m GPS jitter, 5% dropout |
| `algorithms.py` | the ladder: `dr-snap` (depth 1) · `dr-damped(tau)` (depth 1) · `delayed-lerp` (depth 2) · `catmull-rom` (depth 3) |
| `score.py` | cadence × algorithm matrix → RMS px / p95 px / max jump px / heading jitter; `--md` writes the table |
| `preview_interp.py` | pygame eyeball harness (keys a/z algo, c/v cadence, s scenario); `--headless DIR` renders PNGs |
| `capture_adsb.py` | the ONE-session real-data capture (refuses without `--ack`; 429-budget protocol in PROP-006); `fixtures_load()` returns the same Fix schema |
| `baseline_synth.md` | committed score matrix on synthetic truth (see caveats!) |

## Read the baseline with these caveats

1. **Model-match bias:** synthetic truth integrates the same track+gs
   kinematics dead-reckoning extrapolates, so the DR rungs are flattered.
   Real ADS-B adds feed aggregation latency, track/gs staleness relative to
   position, and wind-crab effects. The DR-vs-delayed *gap* will shrink on
   real fixtures — that is exactly what the capture session must measure.
2. **Jitter metric artifact:** `delayed-lerp` freezes at segment end when the
   next fix is late (clamp f=1); near-zero px steps make the heading
   estimate thrash, inflating `jit_degs`. Treat jitter as a tiebreaker, not
   a headline number, until the metric gets a step floor.

## Baseline read (synthetic, 2026-07-19)

`dr-damped` is the standout on synthetic data: at the 10 s default cadence it
holds ~1 px RMS with ≤0.4 px max correction jump, vs `dr-snap`'s 12.8 px
teleports and the delayed rungs' ~15 px staleness error. `catmull-rom` (depth
3) does not beat `delayed-lerp` (depth 2) anywhere that matters — depth 3 is
currently unjustified. tau=2 s looks like the sweet spot (tau=1 leaks jump,
tau=4 only helps jitter). **Pending real-fixture confirmation before any
graduation claim** (caveat 1).
