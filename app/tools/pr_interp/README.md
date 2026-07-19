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
| `preview_interp.py` | eyeball harness on the REAL radar renderer (`preview_planeradar.Radar` + `PreviewWindow`): all 5 scenario planes fly at once, every enabled algorithm overlaid colour-coded per plane. Keys: `1..6` toggle algos, `c`/`v` cadence, `s` solo-plane cycle, `SPACE` pause, `r` restart, `+`/`-` scale, `q` quit; `--headless DIR [--gif]` |
| `capture_adsb.py` | the ONE-session real-data capture (refuses without `--ack`; 429-budget protocol in PROP-006); `fixtures_load()` returns the same Fix schema |
| `baseline_synth.md` | committed score matrix on synthetic truth (see caveats!) |
| `real_replay.py` | TASK-360/EXP-015: replays real captured fixes (`app/tools/fixtures/planeradar/task360_london/`) through the same track+gs dead-reckon math, scores raw one-hop correction magnitude, correlates against turning/speed/altitude — real-vs-synthetic check + speed+altitude hypothesis test |

## Reuse (added after review — the first cut wrongly built standalone)

- `capture_adsb.py` imports `fetch()`/`ac_list()`/`SITES`/`fetch_radius_nm()`
  from `app/tools/pr_adsb_probe.py` (the phase-0 probe) instead of
  re-implementing the API access — the probe knows the real response shape
  and the calibrated fetch-radius derivation.
- `model.py` imports `PRESETS_KM` from the probe (LL-114: no mirroring) and
  uses its ring-3 projection derivation — the first cut assumed preset km =
  disc edge (118 px) and overstated every px metric by ~1.5×; corrected to
  `107 / (preset × 4/3)` px/km.
- `preview_interp.py --headless --gif` uses `preview_common.write_gif`
  (M-PREVIEW-FRAMEWORK) for report animations.
- `preview_interp.py` (round 2, after eyeball feedback) renders through
  `preview_planeradar.Radar` (device palette, rings, glyphs, vectors, tags,
  taskbar) and adopts `preview_common.PreviewWindow` — the round-1
  "PIL-blit doesn't fit" rationale dissolved once the frame WAS a PIL image.
- Projection recalibrated again to match `Radar.project`: **118 px outer
  ring = preset × 4/3 km** (px/km = 88.5/preset). The probe's 107 px is the
  reference project's pre-scale-up grid radius — display metrics use 118.
- Worktree note: `dut_fonts.py` reads TFT_eSPI's `glcdfont.c` from
  `Spotify-Diy-Thing/.pio/` (untracked upstream dir) — in an rnd worktree,
  symlink it from the main checkout:
  `ln -s ~/proj/esp_spotify/Spotify-Diy-Thing <worktree>/Spotify-Diy-Thing`.

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

**TASK-360/EXP-015 update (2026-07-19):** caveat 1's "pending real-fixture
confirmation" is now checked against real London traffic — see
`docs/rnd/reports/EXP-015-pr-interp-real-traffic.md`. Headline: real
one-hop DR corrections (mean 0.29 px, max 4.80 px, n=762) are smaller than
the synthetic dr-snap worst case (9.6 px), and the turning/speed-change
mechanism is confirmed (not altitude — that hypothesis is refuted on this
data). No graduation change; two non-smoother candidate explanations for the
human's observed inaccuracy flagged for PM follow-up instead.

## Baseline read (synthetic, 2026-07-19, ring-3-corrected scale)

`dr-damped` is the standout on synthetic data: at the 10 s default cadence it
holds <1 px RMS with ~0.2 px max correction jump, vs `dr-snap`'s ~9 px
teleports and the delayed rungs' ~10 px staleness error (see
`baseline_synth.md` for the full matrix). `catmull-rom` (depth 3) does not
beat `delayed-lerp` (depth 2) anywhere that matters — depth 3 is currently
unjustified. tau=2 s looks like the sweet spot (tau=1 leaks jump, tau=4 only
helps jitter). **Pending real-fixture confirmation before any graduation
claim** (caveat 1).
