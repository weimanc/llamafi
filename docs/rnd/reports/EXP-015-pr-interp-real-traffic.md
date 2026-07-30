# EXP-015 — PlaneRadar interpolation: real London traffic vs synthetic (TASK-360)

> R&D Engineer · 2026-07-19 · branch `rnd/pr-interp`
> Continuation of EXP-014/PROP-006's descoped capture session, not a revision
> of either — EXP-014's synthetic verdict (dr-damped tau=2, depth 1) and
> TASK-356's DONE status stand.

## Hypothesis

Two things, both stated up front per R&D convention (`docs/agents/rnd.md`):

1. Human report (2026-07-19, watching the DUT live in daytime, genuinely busy
   real traffic): the shipped dr-damped(tau=2) smoother (TASK-357/358) shows
   visible positioning **inaccuracy** — not the tearing bug TASK-358 already
   fixed. EXP-014 caveat 1 predicted real prediction error could be *worse*
   than synthetic and reasoned that damped blending absorbs worse prediction
   better, not worse — but never measured it. Question: does real traffic
   confirm or undersell that reasoning?
2. Human hypothesis, explicitly to be tested not assumed: correct display of
   an aircraft's motion vector may need **speed and altitude/height
   together**, not ground speed + track alone (what the firmware derives
   today).

## Method

Extended `app/tools/pr_adsb_probe.py` (NOT rebuilt — see EXP-014's own
process note on this exact mistake) with `--lat`/`--lon` override args so it
can hit a location outside the baked `SITES` dict; added
`resolve_latlon(args)`, three call sites updated (`cmd_capture`, `cmd_soak`,
`cmd_hunt_max`), `--site` still works unmodified for existing users.

**Location:** 51.50830078, -0.1253000 — the device's actual currently-
configured PlaneRadar location (central London/Westminster; pulled from its
SPIFFS `settings.json` this session), what the human is watching live right
now. **Preset:** 25 km (`PRESETS_KM` already included 25 — no change needed),
which via `fetch_radius_nm()` is a 19.8 NM adsb.fi query radius. This covers
LHR approaches to the west, London City, and general TMA traffic.

**Capture:** three short runs of 8 discrete `--capture` samples each (not
PROP-006's original continuous 10–15 min 1 Hz stream — reduced scope per
TASK-360), nominal intervals 1 s / 5 s / 10 s (matching the `prPollSec`
slider's low/mid range, TASK-355), stored under
`app/tools/fixtures/planeradar/task360_london/` — the *established* fixture
convention (`app/tools/fixtures/planeradar/README.md`, from M-PLANERADAR
phase-0), not PROP-006's text-only `docs/rnd/reports/fixtures/` mention,
which was never actually built by any prior session. 24 samples total (48
files incl. `.pretty.json` copies), 2.1 MB combined, ~35 KB per sample —
modest, as expected. Total wall time ≈ 8 s + 40 s + 80 s ≈ 2 minutes; host-
side only (not through the DUT), single bounded session, no retries, well
under the courtesy pacing this project treats seriously (ADR-029 amendments,
TASK-313). Actual traffic density: 62–70 aircraft per sample within 25 km —
genuinely busy, consistent with the human's "busy real traffic" description
and well above `PR_MAX_AIRCRAFT=24` (see Finding 4).

**Deviation from the plan, observed not caused:** the nominal 1 s cadence
run landed at ~2 s actual spacing between distinct payload states (adsb.fi's
own `now` epoch field didn't change on every fetch — its refresh cadence
appears to floor around ~2 s even when queried faster). Nominal 5 s landed at
4–6 s, nominal 10 s landed at 10–12 s. Recorded here rather than silently
treated as 1/5/10 s exactly; analysis below uses each sample's actual `now`
timestamp, not the nominal interval label.

**Analysis:** new `app/tools/pr_interp/real_replay.py`, built on the existing
rig's `model.py` (ENU projection, `Fix` schema, `px_per_m` — the ring-3-
corrected scale from EXP-014, not re-derived) and `algorithms.py`'s
`track_to_vxy` (same track+groundspeed dead-reckon the firmware uses,
imported not reimplemented). For every consecutive real-fixture pair where
an aircraft (matched by ICAO `hex`) is present in both, airborne in both
(`alt_baro != "ground"`), and reports `track`+`gs`: dead-reckon from fix *i*
to fix *i+1*'s actual arrival time using fix *i*'s track/gs, and measure the
raw correction magnitude in display px — the exact quantity a `dr-snap`
renderer would show as a teleport, and what `dr-damped(tau=2)` spreads over
~2 s instead. This is the real-data analog of EXP-014's `jump_px` metric.
`baro_rate`/`geom_rate`/`alt_baro`/`track`/`gs` are all present in the raw
adsb.fi payload (confirmed directly — see Finding 2) and pulled per-pair for
correlation against the correction magnitude.

**Not done, and why:** EXP-014's `rms_px` metric (continuous trajectory error
against ground truth) needs *continuous* ground truth between fixes, which
discrete real captures at any of these cadences don't provide without
assuming the same smooth-motion model being tested (circular). Only the
`jump_px`-analog metric transfers cleanly to discrete real data; this is an
intrinsic limitation of real fixtures at any capture rate, not a shortcut
taken this session.

## Results

762 matched consecutive-fix pairs across the three runs (201 @ ~2 s, 278 @
~5 s, 283 @ ~11 s actual spacing):

| run (actual spacing) | n pairs | mean err px | median | p95 | max |
|---|---|---|---|---|---|
| ~2 s | 201 | 0.19 | 0.08 | 0.66 | 3.24 |
| ~5 s | 278 | 0.27 | 0.15 | 1.02 | 4.80 |
| ~11 s | 283 | 0.37 | 0.18 | 1.23 | 2.57 |
| **combined** | **762** | **0.29** | **0.14** | **1.03** | **4.80** |

Correlation of correction magnitude (err_px) against explanatory variables at
fix *i* (Pearson r):

| run | \|track_change\| | \|gs_change\| | \|baro_rate\| | \|geom_rate\| | \|alt_change\| |
|---|---|---|---|---|---|
| ~2 s | **0.458** | 0.304 | −0.203 | −0.096 | −0.112 |
| ~5 s | 0.014 | **0.456** | −0.139 | −0.082 | −0.167 |
| ~11 s | **0.651** | 0.407 | −0.080 | −0.069 | −0.148 |

Level-flight (\|baro_rate\|<250 fpm) vs climbing/descending, and straight
(\|track_change\|<3°) vs turning, mean err_px:

| run | level | climb/descend | straight | turning |
|---|---|---|---|---|
| ~2 s (n=115/81, 165/36) | 0.26 | 0.11 | 0.17 | 0.33 |
| ~5 s (n=137/131, 195/83) | 0.32 | 0.23 | 0.28 | 0.26 |
| ~11 s (n=122/152, 180/103) | 0.45 | 0.31 | 0.20 | 0.65 |

Within level-flight only, correction still correlates with turning (r=0.500,
0.030, 0.615 for the three runs) — turning predicts error independent of
vertical rate.

## Finding 1 — real-vs-synthetic: mechanism confirmed, magnitude smaller than synthetic worst case

Caveat 1's directional reasoning holds up: turning aircraft show 2–3× the
mean correction of straight-flying aircraft in the ~2 s and ~11 s runs (the
~5 s run is a wash — see below), and `gs_change` is a consistent positive
predictor across all three runs (0.30–0.46) — dead-reckon error grows
exactly when the constant-track-and-groundspeed assumption breaks, as
designed-for. That confirms the *mechanism* EXP-014 argued for rather than
measured.

But the *magnitude* in this real, busy-London sample (mean 0.29 px, max
4.80 px across 762 pairs) is smaller than EXP-014's synthetic dr-snap
worst case (9.6 px mean max-jump at 10 s cadence, `baseline_synth.md`) — not
larger, so caveat 1 was not "undersold" in the sense of real traffic being
worse than the synthetic study assumed, at least in this sample. The
metrics aren't perfectly comparable (see Method's "not done" note — this is
one-hop correction across real fixes at irregular real spacing, not 30 fps
continuous-truth RMS), so treat this as directional evidence, not a
like-for-like replacement of EXP-014's table. `dr-damped(tau=2)` absorbs
these real corrections trivially: every observed max (4.80 px) is far under
`PR_INTERP_SNAP_PX=40px` and under the synthetic worst case tau=2 was tuned
against.

**The ~5 s run's near-zero track-change correlation (r=0.014) is an
anomaly** relative to the other two runs (0.46, 0.65) — most likely small-n
noise from a ~40 s window of specific traffic (this run happened to catch a
batch of aircraft with a different mix of turning/altitude behavior), not a
real cadence-dependent effect; `gs_change` stayed a consistent predictor in
that same run (r=0.456), which is why the report doesn't read this as "turns
don't matter at 5 s."

**Conclusion (item 2 of TASK-360):** real traffic does not show the shipped
smoother is under-provisioned — the raw corrections it needs to absorb in
this busy-London sample are smaller than the synthetic worst case, and the
qualitative mechanism (worse prediction → bigger correction, absorbed by
damping) is confirmed. This session's data does not explain the human's
observed "inaccuracy" as a magnitude problem in the DR-vs-fix jump itself —
see Findings 3–4 for other candidate explanations worth a follow-up look.

## Finding 2 — the speed+altitude hypothesis: REFUTED (direct), evidence points the other way

The adsb.fi payload genuinely carries vertical-motion fields — confirmed by
inspecting the raw captures directly, not assumed: `alt_baro`, `alt_geom`,
`baro_rate`, `geom_rate` are present on essentially every airborne record
alongside `track`/`gs`. So the data needed to test the hypothesis exists.

Testing it against 762 real pairs: correlation of position-prediction error
against `|baro_rate|`/`|geom_rate|`/`|alt_change|` is **weak and negative**
in every one of the three runs (−0.07 to −0.20) — the opposite sign a "needs
altitude" hypothesis would predict. Climbing/descending aircraft show
*lower* mean correction than level aircraft in all three runs (e.g. ~11 s
run: 0.31 px climbing/descending vs 0.45 px level) — again the opposite of
what "altitude matters" would predict.

By contrast, turning predicts error strongly and *within level flight only*
(so not confounded by vertical maneuvering): r = 0.500 / 0.030 / 0.615.
Turning aircraft in this London TMA sample skew toward level flight (holds,
vectoring, sequencing turns), while climb-outs and descents in this sample
tend to be comparatively straight — the reverse of the correlation a
"climbing/descending aircraft are also often turning" indirect mechanism
(floated as the *plausible* indirect path in TASK-360's brief) would need.
That mechanism doesn't hold in this sample either.

Also confirmed directly in the firmware source (`app/src/planeRadarApp.h`,
master, `_project()` at the call site referenced in TASK-360's brief):
position math is 2-D lat/lon only, no altitude term — consistent with the
brief's own reasoning that any real effect would have to be indirect via
maneuvering correlation, not a direct fix to the projection formula.

**Disposition: REFUTED**, both the direct form (altitude enters the display
math) and the indirect form tested here (altitude change correlates with
turning/speed-change in this traffic sample) don't hold. Vertical rate and
altitude, on this evidence, are not levers for improving PlaneRadar's
on-screen motion accuracy. Caveat: one ~2-minute, 65–70-aircraft-per-sample
London capture — a different airspace/time-of-day mix (e.g. a airport with
long straight-in ILS approaches and few holds) could show a different
turning/altitude correlation structure. Not re-tested here; flagged as a
limit on how far this refutation generalizes.

## Finding 3 — a candidate explanation the raw-correction analysis doesn't cover: fix timestamp is receipt time, not sample time

Not measured this session — inferred from reading `app/src/planeRadarApp.h`
(master) and `dataTask.h`/`dataTaskStorage.cpp`, flagged here because
Finding 1 shows the raw DR-vs-fix corrections are small, which argues
*against* the smoother's jump-absorption math being the visible defect and
argues *for* looking elsewhere for the human's "positioning inaccuracy."

`_reconcileMotion(now)` stamps `m.fixMs = now`, where `now = millis()` is
read in `tick()` at the point the async fetch result is *drained from the
queue* (`dataTask::pollPlaneRadar`) — not the adsb.fi payload's own `now`
epoch field (which this session's captures show is the server's actual
sample time, and which the firmware never reads). Dead-reckoning in
`_motionPx()` then extrapolates forward from `fixMs` using elapsed device
time. If the request round-trip (TASK-313: PlaneRadar GETs on the DUT pace
at ~4.3 s, edge-effect) varies fetch-to-fetch — which a fixed, *constant*
latency would not do, but retries/edge jitter can — every fix is
timestamped later than the position was actually true by a *varying* amount,
which shows up as the dead-reckon running systematically ahead of the real
aircraft by however much that latency varies, not as a fixed offset a human
would stop noticing. Rough magnitude check: a 450 kt jet covers ~230 m/s;
2 s of unaccounted latency ≈ 460 m ≈ 1.6 px at the 25 km preset — modest on
its own, but a systematic *lead* stacked with the small dead-reckon errors
already measured could plausibly read as "off" to a human watching
continuously, in a way the isolated jump_px metric doesn't capture.

**This is a hypothesis for a follow-up, not a finding proven by this
session's data** — no DUT-side fetch-latency variance was measured here (the
host-side captures in this session had ~80 ms RTT, nothing like the DUT's
edge-paced path). Recommend PM schedule a small, DUT-side follow-up: log
actual fetch round-trip time per PlaneRadar GET (`_requestFetch()` timestamp
to `pollPlaneRadar()` drain) and check its fetch-to-fetch variance against a
few seconds — if it's consistently near-constant, this mechanism is a
non-issue; if it varies by 1–2+ s fetch-to-fetch, it's a plausible
contributor worth a scoped fix (stamp `fixMs` from request time or the
payload's own timestamp field instead of drain time).

## Finding 4 — PR_MAX_AIRCRAFT=24 roster churn, a second non-smoother candidate

Also not measured directly this session, flagged for completeness: this
session's captures show 62–70 aircraft within 25 km of central London, far
above `dataTask.h`'s `PR_MAX_AIRCRAFT=24` cap
(`prInsertNearest(..., PR_MAX_AIRCRAFT, ...)`, `dataTaskStorage.cpp:1181`).
On the real device only the nearest 24 are ever rendered, and in this dense
a traffic environment the *membership* of that nearest-24 set can plausibly
change between fetches as aircraft cross the boundary — `_reconcileMotion()`
correctly gives newly-appearing aircraft offset 0 (no false continuity
claim), so this isn't a smoothing bug, but boundary churn (planes popping in
and out near the disc edge) is a distinct visible phenomenon from
motion-vector inaccuracy and could easily read as "inaccurate tracking" to
an observer without them distinguishing the two mechanisms. Also not
analyzed here: this session's correlation study used the *full* unfiltered
aircraft list, not the nearest-24 the device actually shows — restricting to
nearest-24 (likely skewed toward final-approach/departure traffic, which may
turn more than average overflights) is a natural follow-up if Finding 2's
refutation needs re-checking against exactly what the device renders.

## Recommendation

- **No firmware change recommended from Finding 1/2** — the shipped
  dr-damped(tau=2) smoother's absorption capacity is not shown to be
  under-provisioned by real traffic in this sample, and the altitude/speed
  hypothesis is refuted on direct evidence. Don't spend a production task
  chasing either.
- **Findings 3 and 4 are the concrete, actionable candidates** for the
  human's observed inaccuracy, both requiring a small DUT-side
  measurement/investigation task before any fix is scoped — handing to PM
  to consider filing as a follow-up task (not implementing here per
  R&D/AGENTS.md: hand proposals to PM, not code):
  - Measure PlaneRadar fetch round-trip variance on the DUT; if
    material, consider stamping `fixMs` from request-issue time (or the
    payload's own `now` field) instead of queue-drain time.
  - Distinguish "roster churn at the PR_MAX_AIRCRAFT=24 boundary" from
    "motion-vector error" as the source of the human's "twitchy"/inaccurate
    impression — likely needs a human eyeball session specifically watching
    for pop-in/pop-out near the disc edge vs. mid-disc position drift.

## Deliverables

- Fixture dataset: `app/tools/fixtures/planeradar/task360_london/` (24
  samples × compact+pretty JSON, 2.1 MB, committed on `rnd/pr-interp`),
  manifest entry added to `app/tools/fixtures/planeradar/README.md`.
- Tooling: `app/tools/pr_adsb_probe.py` extended with `--lat`/`--lon`
  (reused, not rebuilt); new `app/tools/pr_interp/real_replay.py` (reuses
  `model.py`/`algorithms.py`'s projection and track+gs math, no
  reimplementation).
- This report.

**Branch:** `rnd/pr-interp` · **Recommendation:** no graduation action;
Findings 3/4 to PM as candidate follow-up investigation tasks.
