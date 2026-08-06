# Design — M-WEBRADIO-POSBAR-SLEW: bound the buffer-fullness bar's visual travel per second

> Owner: Architect
> Status: **accepted** (2026-08-06, human sign-off)
> Date: 2026-08-06
> Feeds: — (no ADR — same class of decision as M-WEBRADIO-POSBAR-SMOOTH:
> a display-refresh tuning fix, not a novel architectural decision)
> Tracked-as: TASK-405
> Registers: — (modifies the existing `webradio-001` feature in place, no
> new feature id, no new cross-feature edge — reuses the `perf.h` `MAX_PATHS`
> budget already committed as X049 by TASK-402; no new instrumentation site)

**Revision note (2026-08-06, same day):** folded in VE's testability review
(`docs/architecture/designs/M-WEBRADIO-POSBAR-SLEW-VE-review.md`, verdict
approve-with-changes, one blocker). VE-1 (§Lean step 4, `lastSkipReason`'s
three-way contract corrected — it does not need to collapse), VE-2 (§Lean new
step 6 + §Exit criteria, added the `wrPosbarSimDrain` debug hook — the doc's
original OQ2 test method didn't actually reach a testable state), VE-3
(§Exit criteria, explicit ≥3-trial protocol against SLAM! specifically). VE-4
(informational, simulation-fidelity caveat) and VE-5 (process note on OQ3)
folded as footnotes, no structural change needed for either.

## Addendum (2026-08-06, live-eyeball follow-up) — hysteresis dead-band near the ceiling

The slew limiter above was implemented, DUT-verified (mechanism), and passed regression — but
the actual live-eyeball exit criterion (≥3 trials against SLAM!, VE-3) surfaced a real gap:
**"the buffer SLOWLY fills [good], but once full, the posbar still keeps jumping around multiple
times a second."** The slew limiter bounds redraw *magnitude* (≤2pts/tick) but not *direction-
reversal frequency* — and reversals, not total range, turn out to be what reads as "jumping
around" to a human eye.

**Host-only evaluation of five filter-shape alternatives, all against the same real captured
traces + synthetic connect/hiccup/drop scenarios used above (no DUT time spent until a candidate
looked genuinely better on paper):**

1. **Fixed-gain critically-damped spring-damper** (same formula family as `vuMeter.h`'s
   `updateSpectrumBar` — literally P+D control, `Kp=b`, `Kd=(1-a)`, on a double-integrator; the
   `vuMeter.h` constants themselves turned out to be underdamped for this recurrence, corrected
   via `b ≤ (1-√a)²`). Real tradeoff, not a tuning gap: damping heavy enough to kill ceiling
   jitter (`a=0.98`, worst-2s-range 2-7pts) also made a genuine connection-drop **never** reach
   50% visible within the test window — worse than the slew limiter already shipped. A linear
   P+D controller has no way to distinguish "small noise" from "large real change" — both just
   feed the same `Kp·error` term.
2. **Dual-rate / gain-scheduled spring-damper** (switch to fast params when `|error|` is large).
   Failed worse — confirmed via direct measurement that single-sample noise on this signal
   routinely exceeds any reasonable magnitude threshold (0.7-0.8% of samples exceed a threshold
   of 25), so the "large error = real signal" assumption a magnitude gate depends on doesn't hold
   here: our noise *is* large-amplitude, just short-lived. A **persistence-gated** variant (only
   switch after the error lasts N ms) was worse still — traced to a genuine "bumpless transfer"
   bug: velocity accumulated under fast dynamics bled off far too slowly under the heavy
   regime's much slower damping constant after a mode switch, producing large overshoot.
   Zeroing velocity on switch cut this ~2-3x but still left it ~3x worse than the plain slew
   limiter on the stations that matter.
3. **Asymmetric slew** (rise_step=2 unchanged, fall_step swept slower). No improvement on the
   worst real stations at any fall_step — traced to reversals happening *within* a single
   network-delivery burst (raw itself flips direction multiple times mid-burst), not as a clean
   rise-then-fall; damping only the fall side doesn't touch reversals the rise side is equally
   responsible for.
4. **Asymmetric EMA** (attack/release envelope follower, fed directly from raw). Worse across
   the board (80-97pt worst-range) — same root cause as spring-damper variants that skip the
   existing EMA pre-stage: a single large raw sample punches straight through.
5. **Plain step-size reduction** (`MAX_STEP_PER_TICK` below 2). Range scales down linearly as
   expected, but reversal *count* stayed flat (a smaller step just makes the same number of
   direction flips smaller, not less frequent), and connection-drop visibility — already
   borderline at step=2 — never resolved at any smaller step.

**Winning approach: hysteresis dead-band near the ceiling, layered on top of the existing
slew mechanism (not a replacement).** Once the drawn value AND the smoothed target are both
`>= WR_POSBAR_FREEZE_ENTER_PCT` (90), freeze — skip the slew step entirely, regardless of how
much the underlying value wiggles above that line. Only resume once the target drops below
`WR_POSBAR_FREEZE_EXIT_PCT` (80); the gap between the two thresholds is the hysteresis band
itself, preventing the boundary from becoming a new chatter source (classic Schmitt-trigger
construction). This sidesteps the noise-vs-signal problem the gain-scheduled attempts hit —
it doesn't need to *distinguish* them, it just declines to report precision that conveys no
useful information once the bar already reads "essentially full."

Host-only results: real-trace steady-state reversals-per-2s-window dropped **5→0** (worst
stations), essentially unchanged on already-calm ones, across every enter/exit pair tried
(85-90 / 65-80). Synthetic connection-drop-from-98 cost only **+0.2 to +0.6s** added latency to
50%/95%-visible versus the plain slew limiter's own already-accepted ~5.4s/10.3s baseline —
negligible. A recoverable non-underrun hiccup while near-full (dips to 60, no real drop) was
almost entirely absorbed (86-92 shown vs. raw's 60). One early candidate pairing (`enter=80`,
close to the test's own 81-point checkpoint) showed an apparent stall that traced to a test-
methodology coincidence, not the mechanism — `enter=90, exit=80` had no such issue and was
selected as the shipped constants.

**Implementation** (`webRadioApp.h`): `WR_POSBAR_FREEZE_ENTER_PCT=90` / `_EXIT_PCT=80` constants;
`_posbarFrozen` bool state, reset alongside the existing per-PLAYING-session and `wrBufPct`-
force-write hygiene resets (a stale freeze must not survive a reconnect or a debug override,
same discipline as the existing `_posbarSimDrainActive` reset); `PosbarSkipReason` gains a
fourth value `FROZEN` (`get wrPosbar`'s `lastSkipReason`, plus a new explicit `"frozen"` boolean
field) — `CONVERGED` keeps its TASK-405-original meaning ("eligible tick, already at target"),
distinct from `FROZEN` ("dead-band actively holding"), so OQ1-style tuning can still tell them
apart. Un-freeze check runs before this tick's own step (so a genuine decline starts escaping
the same tick it crosses EXIT, not one tick late).

**DUT verification** (`task405_slew_verify.py`, extended): three consecutive clean confirmations
of the freeze mechanism itself — froze exactly at the seeded near-ceiling value, held constant
while `bufPctRaw` kept changing underneath it (proving the freeze doesn't stop the underlying
computation, only the display step), correctly un-froze once the target crossed `EXIT_PCT`, and
still reached 0 afterward (no permanent stuck state). Two flaky failures across four DUT runs
this session — a pre-existing `wrBufPct`-vs-concurrent-real-playback race (documented, predates
this change) and one polling-aliasing artifact in an unrelated code path (`<80`, never reaches
the freeze threshold) that cleared on a smoother-polling rerun — both attributable to a literal
mid-session USB disconnect/reconnect event on the DUT rig, not the implementation. `run/check`
6/6 both envs. Regression: `T_WR_EJECT_01/02`, `T_WR_ERR_01-04` 6/6 clean.

**Live-eyeball confirmation (2026-08-06, same day):** human on the physical LCD — "POSBAR no
longer jitters."

**Status:** **CLOSED.** Implemented, DUT-verified (mechanism + regression), and live-eyeball
confirmed.

## Context / pain points

TASK-402 (`M-WEBRADIO-POSBAR-SMOOTH.md`, implemented + DUT-verified 2026-08-05)
added EMA smoothing (`WR_POSBAR_EMA_ALPHA=0.2f`) and a minimum-redraw-interval
gate (`WR_POSBAR_MIN_REDRAW_MS=200`) to the WebRadio posbar. Both constants
were explicitly left as DUT-tuning open questions (OQ1/OQ2), pending a
dedicated longer session — never done at implementation time.

Picking up that pending session (2026-08-06), the human live-observed the bar
on the physical LCD while playing SLAM! and reported it "oscillates," making
"about 4 changes in 1 second." That rate is suspicious on its own: it sits
almost exactly at the `MIN_REDRAW_MS=200` ceiling (5 redraws/sec max) — the
time-gate is not limiting anything here, meaning the delta-threshold gate
(`≥2` smoothed points) is being satisfied on nearly every eligible tick.

### Measurement method

Built `app/tools/task402_posbar_trace.py` (ad hoc, not added to
`run_serialdbg_tests.py`, same convention as `task399_402_dut_verify.py`) to
capture ground truth before proposing anything. It reuses `Dut` /
`_ensure_webradio` / `_webradio_enter_with_stations` / `_wait_wr_state` from
`run_serialdbg_tests.py` rather than re-deriving them (per this project's own
"extend, don't fork" convention).

Method:
1. Flash `cyd2usb_winamp_debug`, enter WebRadio, fetch a real station list
   (radio-browser.info, NL, live).
2. Select up to 5 stations spread across the loaded list (index diversity ->
   bitrate/mirror diversity), plus a forced `--include-name SLAM` match so
   the exact station the human was watching is always included.
3. Per station: `set wrPlay <idx>`, wait for `wrState==PLAYING`, sleep 3s
   past the connect-time fill transient (TASK-266 precedent), then poll
   `get wrPosbar` back-to-back (no fixed inter-poll delay — sample rate is
   whatever the serial round-trip allows, measured at ~20-90ms per sample,
   i.e. well above Nyquist for anything the human eye would call
   "oscillating") for a fixed window (40-45s), recording `bufPctRaw`,
   `bufPctSmoothed`, `bufPctDrawn`, `redraws`, `lastSkipReason`. `get
   wrState` is interleaved every 5th sample (state changes far slower than
   buffer %) and forward-filled, so `PLAYING`-only segments can be isolated
   from `CONNECTING`/stall-retry segments after the fact — this matters
   because `_play()` force-resets `_bufPct=0` on every reconnect attempt
   (`webRadioApp.h:1861`) and the recompute/smoothing block only runs while
   `_state==PLAYING` (`webRadioApp.h:933`), so a raw reading of 0 is
   ambiguous between "buffer genuinely empty" and "not playing right now"
   without this filter.
4. Raw CSVs + manifest kept under `app/tools/rnd_logs/task402_trace_<ts>/`.
5. DUT restored to production firmware (`run/flash`) after each capture —
   this script does not leave debug firmware flashed.

Two capture runs were done (5 stations each; one station per run failed to
reach `PLAYING` at all inside the window — a real connect failure, not a
tool bug, see Findings). Total: 4-5 stations per run with usable `PLAYING`
data, ~40-45s each, ~1150-2000 samples per station.

### Analysis results

**Filtering to `wrState==PLAYING` was necessary and revealing on its own.**
`PLAYING` fraction of the capture window ranged from 0.15 to 0.99 across
stations — some spent the *majority* of a 40s window not actually playing at
all (repeated `CONNECTING`/stall-retry cycling). This is a real, separate
signal (same family as TASK-390/391/393/398's known connect-reliability
findings), not a smoothing defect, and is called out below as a finding, not
folded into this design's fix.

**Within genuine `PLAYING` segments, the raw buffer ratio does not jitter —
it swings the *entire* 0-100 range in well under two seconds, repeatedly.**
Example (`Radio 10`, `PLAYING`, t=3.5-4.9s of one capture):

```
t=3.519 raw= 75   t=3.938 raw= 93   t=4.250 raw=100   t=4.550 raw= 66
t=3.611 raw= 93   t=4.008 raw= 93   t=4.341 raw= 93    t=4.604 raw= 53
t=3.675 raw= 93   t=4.110 raw=100   t=4.407 raw= 93    t=4.655 raw= 40
t=3.726 raw= 90   t=4.160 raw=100                       t=4.717 raw= 21
```
0 -> 100 -> 21, inside 1.4 seconds. This is a genuine, physically-driven
burst-fill/rapid-drain cycle (small ring buffer + bursty TCP chunk delivery
from the mirror), not measurement noise — confirmed across 3 of 5 stations,
with burst recurrence ranging from every few seconds (`Radio 10`) to
sub-second back-to-back bursts (`100% NL`, e.g. four >20-point jumps within
1.3s late in that capture).

**Root cause of the reported "oscillation" is now precise: the existing gate
bounds redraw *frequency* (≤5/sec, confirmed working exactly as designed)
but places no bound on redraw *magnitude*.** A single redraw can jump by up
to ~80 points because the delta-threshold (`≥2`) is a *minimum* to trigger a
redraw, not a *cap* on how far it moves once triggered. Rate-limited but
unbounded-amplitude motion still reads as jarring to a human eye, exactly as
reported.

**Quantified via host-side simulation against the real captured raw traces**
(not synthetic data) — metric: worst-case value range within any sliding
2-second window (the human's own framing), comparing today's implementation
against a candidate slew-rate limiter (see Lean):

| Station | Today (worst 2s-window range) | Slew-limited, 2pts/200ms-tick |
|---|---|---|
| Radio 10 | 95 pts | 18 pts |
| SLAM! | 96 pts | 20 pts |
| 100% NL | 92 pts | 20 pts |
| Slam! Mixmarathon | 20 pts | 18 pts |
| Radio Noordvaarder | 15 pts | 16 pts |

Today, 3 of 5 stations can visually traverse *nearly the entire bar* within
any 2-second window. The simulated slew limiter bounds this to ~18-20 points
by construction (≤10 redraw ticks/2s × 2pts/tick), not by tuning luck — the
two stations that were already calm (20/15 pts) are essentially unaffected.

**Caveat (VE-4):** the simulation applies the EMA update once per captured
sample (external serial-poll rate, ~20-90ms/sample) as a proxy for the real
per-`tick()` update rate — order-of-magnitude consistent with this project's
own heartbeat `loop_max` values (24-85ms under similar load) but never
independently confirmed against a real on-device tick counter. Doesn't change
the qualitative conclusion (frequency was already bounded, magnitude wasn't),
but the exact 18-20pt figures should be treated as directionally right, not
exact, until the DUT verification step re-measures them for real.

## Goals

- Bound the posbar's visual travel within any 2-second window to a value
  that reads as smooth motion, not a flash — informed by the above (~18-20
  pts felt like the right order of magnitude from the simulation; final
  call is still a human eyeball on the physical LCD, same discipline
  M-WEBRADIO-POSBAR-SMOOTH's own exit criteria used).
- Do not regress TASK-402/253's own prior fixes: still no full-groove
  reblit per redraw (Option E stays), still no wide static hysteresis
  (TASK-253's original problem).
- Do not hide a genuine depleting-buffer trend indefinitely — a real,
  sustained drain toward empty must still become visible within a few
  seconds, even though a single-burst spike no longer flashes through
  immediately. (The posbar is explicitly a cosmetic/informational surface —
  TASK-263's `wrUnderruns`/`_minBufPct` is the objective stall metric,
  "operator should still confirm by ear" per that task's own comment — so
  some added lag on pathological bursts is an acceptable trade, not a
  safety regression.)

## Design space (options + tradeoffs)

**A. Lower `WR_POSBAR_EMA_ALPHA` further (e.g. 0.2 -> 0.05).** Simplest
change, zero new code. Rejected as insufficient on its own: EMA has no hard
bound on response to a step/burst input — the simulation's 92-96pt worst-case
figures already include the *existing* 0.2 EMA; a lower alpha would still
let a value move by an unbounded amount within 2 seconds, just less than
today, with no way to state a firm guarantee. Also directly trades against
the "must still show a real trend in time" goal in the wrong direction
(heavier lag, no floor).

**B. Widen the delta-threshold gate (e.g. `≥2` -> `≥10`).** Rejected outright
— this is exactly the TASK-253 regression M-WEBRADIO-POSBAR-SMOOTH's own doc
already flagged and refused to repeat (a wide hysteresis threshold was cut
from 15 to 2 specifically to fix visible 33px thumb jumps). Widening it back
up trades one visible-jump problem for another.

**C. Slew-rate limiter on the displayed value, fed by the existing EMA.**
Keep `_bufPctSmoothed` computed exactly as today (EMA on raw, glitch
rejection). Replace the delta-threshold gate with: each `MIN_REDRAW_MS`-gated
tick, advance `_bufPctDrawn` toward `_bufPctSmoothed` by at most
`WR_POSBAR_MAX_STEP_PER_TICK` points (clamped both directions), not straight
to the target. This gives a *provable* bound on 2-second-window travel
(≤ (2000/`MIN_REDRAW_MS`) × `MAX_STEP_PER_TICK`), unlike A, and does not
reopen TASK-253's threshold-width problem like B — the "threshold" is now a
per-tick rate, not a jump-trigger width. Directly validated against real
captured device data (see Analysis), not just reasoned about.

**D. Windowed min/max/median filter (e.g. median of last N samples).**
Would also flatten bursts, but has no simple redraw-cadence story (the
existing partial-diff blit machinery — Option E from TASK-402 — assumes a
single scalar target per redraw, not a window recompute) and doesn't map
cleanly onto the existing `MIN_REDRAW_MS`-tick redraw loop without extra
state (a ring buffer of raw samples, more RAM on a board with a documented
history of DRAM budget fights — `[[feedback_dram_bss_static_buffers]]`).
Rejected: C achieves the same practical goal with less new state and a
cleaner fit to the existing tick loop.

## Lean / decision

**Adopt C.** Concretely, in `webRadioApp.h`'s existing gated-redraw block
(around line 995, replacing the current `deltaOk`/`intervalOk` pair):

1. Keep computing `_bufPctSmoothed` via the existing EMA
   (`WR_POSBAR_EMA_ALPHA`) every tick, unchanged — still the glitch-rejection
   stage before anything gets drawn.
2. Keep `WR_POSBAR_MIN_REDRAW_MS` as the tick-eligibility gate, unchanged.
3. Replace the delta-threshold check with a slew step: on each eligible
   tick, move `_bufPctDrawn` toward `_bufPctSmoothed` by at most a new
   constant `WR_POSBAR_MAX_STEP_PER_TICK`; redraw only if that step actually
   changes the drawn value (a `0`-magnitude step is a no-op redraw skip,
   same as today's "delta" skip reason, just computed differently).
4. **(VE-1, corrected)** `lastSkipReason`'s three-way contract does **not**
   collapse — all three values stay independently meaningful under the slew
   design, they just get a new mapping: `INTERVAL` unchanged (time-gate
   blocked this tick); the old `DELTA` case is re-derived as "drawn value
   already equals the rounded smoothed target, nothing to step" (rename to
   `CONVERGED` if the old name reads as misleading post-change — naming
   only, not a functional change); `NONE` unchanged ("we stepped/redrew this
   tick"). OQ1's own tuning pass needs this distinction to tell "the bar
   isn't moving because the buffer is genuinely flat" apart from "the bar
   isn't moving because the time-gate is holding it back" — the same
   ambiguity TASK-402's own VE-4 finding already fixed once for the
   original delta/interval pair; this design must not silently lose it.
5. `set wrBufPct` (TASK-402 VE-1) keeps its existing bypass behavior
   unchanged — force-writes and draws immediately, still documented as not
   exercising the gated/slewed path.
6. **(VE-2)** New debug hook: `set wrPosbarSimDrain <startPct>[,<stepPerTick>]`
   — seeds `_bufPct` to `startPct`, then decrements it by `stepPerTick`
   (default a small fixed amount, e.g. 1) each real tick **through the
   normal, non-bypassing code path** (feeds the raw input the EMA/slew logic
   already consumes — does *not* call `_drawPosbar()` directly, unlike `set
   wrBufPct`). Needed because neither existing debug hook can exercise OQ2:
   `wrDeadUrls` never reaches `PLAYING` (TASK-395's own finding, re-confirmed
   for this doc), and `set wrBufPct` bypasses both gates by design. Mirrors
   `wrDeadUrls`'s own "deterministic synthetic injection for testability"
   precedent, applied to the one exit criterion that otherwise has no way to
   be met on purpose.

**Starting constant: `WR_POSBAR_MAX_STEP_PER_TICK = 2`** (points per
`MIN_REDRAW_MS`-gated tick), per the simulation table above — worst-case
2-second-window travel ~18-20 points across the traced stations, a ~5x
reduction from today's 92-96 point worst case on the jitteriest stations,
with the two already-calm stations essentially unaffected. `3` is the
documented faster alternative (~27-30pt worst case) if `2` reads as
noticeably laggy on the live eyeball check — **this constant is a candidate
from host-side simulation against real captured data, not a DUT-confirmed
final value**; the live-eyeball exit criterion below still governs.

Not adopted: A (no hard bound), B (repeats TASK-253's regression), D (more
state, worse fit to existing redraw-tick machinery for no demonstrated
benefit over C).

## Open questions

- **OQ1 (final `WR_POSBAR_MAX_STEP_PER_TICK` value).** `2` is the
  simulation-informed starting point; needs the same live-human-eyeball
  confirmation M-WEBRADIO-POSBAR-SMOOTH's own exit criteria required for
  OQ1/OQ2 — a tool capture can't judge "does this look smooth," and
  `run/screendump`/any fresh serial connection resets the DUT via DTR,
  perturbing exactly the continuous playback being judged.
- **OQ2 (does slowing worst-case full-range traversal to ~10s, at
  `MAX_STEP_PER_TICK=2`, ever meaningfully delay noticing a real approaching
  stall).** Argued acceptable in Goals (posbar is cosmetic, `wrUnderruns` is
  the objective metric). **(VE-2, was a blocker until this doc added Lean
  step 6):** neither existing debug hook could actually test this
  deterministically — `wrDeadUrls` never reaches `PLAYING`, `set wrBufPct`
  bypasses the gate — which is exactly how TASK-402's own OQ1/OQ2 went
  unresolved for over a day. The new `wrPosbarSimDrain` hook (Lean step 6)
  makes this testable on purpose instead of by waiting for a real stall.
- **OQ3 (the connect-reliability finding).** 2 of 5 traced stations spent
  most or all of their capture window failing to reach `PLAYING` at all.
  Real, and consistent with the already-tracked TASK-390/391/393/398 thread
  — not this design's problem to solve, flagged so it isn't silently lost.
  **(VE-5)** No action item created here — explicit PM disposition needed
  (either "folded as a data point into the existing TASK-390/391/393/398
  thread" or "stays anecdotal, no new task"), not a silent non-decision.

## Exit criteria

- Host-side: simulation (already done, in Analysis above) shows the
  candidate constant beats today's worst-case 2-second-window range on every
  traced station, and does not regress the two already-calm ones. **Done.**
- DUT: implement per Lean, `./run/check` 6/6 both envs, no DRAM/BSS
  regression (reuses existing fields — `_bufPctDrawn`/`_bufPctSmoothed`
  already exist from TASK-402, no new static storage expected).
- DUT: `get wrPosbar` mechanism check (mirrors TASK-402's own VE-1/redraw-
  cadence verification) — `set wrBufPct` bypass still works, real-playback
  polling shows redraws bounded by the new per-tick step, `lastSkipReason`
  still reports all three values with their corrected (VE-1) meanings.
- DUT: **live human eyeball on the physical LCD** (or phone-camera video,
  not a tool-assisted capture — same DTR-reset caveat as
  M-WEBRADIO-POSBAR-SMOOTH's own exit criteria), **≥3 trials (VE-3), against
  SLAM! specifically at minimum** (the originally-reported station, not
  "whichever reproduces live") — confirms the bar now reads as smooth, not a
  flash, resolving OQ1. Additional trials against Radio 10 / 100% NL
  encouraged given their equally-bad baseline numbers, but SLAM! is the
  non-negotiable minimum since it's the one actually complained about.
- DUT: **(VE-2)** using the new `wrPosbarSimDrain` hook, seed a high value
  and let it drain to 0 through the real gated/slewed path — confirms the
  decline is visibly reflected on screen well before it completes, not
  hidden until it's already at zero. Resolves OQ2 deterministically instead
  of waiting on a real stall.
- Regression: existing WebRadio DUT suite (auto-skip, eject, ICY marquee,
  vis-mode toggles) unaffected — this design touches only the posbar's
  redraw-gating logic, not playback/state logic, same scope boundary as
  TASK-402's own design.
