# Design — M-PR-MOTION: PlaneRadar poll-interval setting + motion-smoothing research

> Owner: Architect
> Status: scheduled — designed 2026-07-18 (human request), filed as TASK-355
> (production slider) + TASK-356 / PROP-006 (RnD host study). Production
> interpolation task is deliberately NOT filed — it waits for the study's
> graduation proposal (AGENTS.md R&D protocol).
> Deps: M-PLANERADAR (closed), M-SETTINGS-STYLE (SliderWidget), ADR-050
> (settings wiring), TASK-313 (fetch pacing evidence)

## Intent (human, 2026-07-18)

1. The PlaneRadar poll interval becomes a **settings slider, 1 s minimum**
   (today: fixed `PR_POLL_MS = 10000`).
2. **Interpolation for smooth plane motion** is wanted — but first a
   **host-side research/preview**: number of samples vs interpolation
   algorithm, to find what actually looks smooth before any firmware work.

## Item A — poll-interval slider (TASK-355)

### Setting

- New `AppSettings` field: `uint8_t prPollSec`, **range 1–30, default 10**
  (10 = exact current behaviour). Persisted like every PlaneRadar row (rides
  the section save); **ADR-050 step-7 wiring gate applies** (load + save +
  runtime consumer).
- UI: a `SliderWidget` row in the PlaneRadar settings submenu — reuse the
  WR-3 max-volume idiom wholesale (`appsSection.h:101/:181`), including its
  Press/Move/Release routing. Label shows the live value ("Poll: 10 s").

### Firmware behaviour

- `planeRadarApp` reads `g_settings.prPollSec * 1000UL` in the tick gate
  (`:200`) instead of the constant. Read live each tick — an interval edit
  applies on the next tick, no resume-diff/refetch machinery needed (the
  value only gates *when* the next enqueue happens).
- Keep `PR_POLL_MS` as the default-seed constant or replace with
  `PR_POLL_DEFAULT_SEC`; `_forceNow()` (`:409`) must derive from the same
  live value.

### The 1 s setting, honestly

The human chose a 1 s floor knowing the tradeoffs; the firmware makes it
degrade gracefully rather than forbidding it:

- The existing `_pendingFetch` gate already serializes fetches, and TASK-313
  measured ~4.3 s wall time per device GET (Cloudflare edge pacing). So at
  settings below ~5 s the app becomes **fetch-completion-paced** (~4–5 s
  effective) — self-limiting, no request pile-up, still inside adsb.fi's
  1 req/s courtesy limit. Document this in the design and the field comment;
  do not add a hidden clamp.
- Known costs at low settings (recorded, not blocking): Spotify is
  HTTP-silent during each fetch (tlsYield), so near-continuous fetching
  squeezes the Spotify poll loop; and the per-IP 429 budget shared with host
  probes drains faster (host-probe ≥60 s rule stays).
- TASK-313's parse-error-only retry is unaffected.

### Verification

- **T_PRM_01 (DUT):** slider round-trip (set 1 / 10 / 30, reboot, value
  persists); `get` observable for the live interval.
- **T_PRM_02 (DUT):** at setting=1, inter-fetch spacing settles at
  fetch-completion pace (~4–5 s), no enqueue pile-up (`_pendingFetch` never
  double-fires), no Spotify heartbeat regression over a 5-min window.
- `run/check` 7/7 incl. step-7 wiring gate.

## Item B — interpolation research on host (TASK-356 / PROP-006)

Registered as **PROP-006**
(`docs/rnd/proposals/PROP-006-pr-interpolation-study.md`). Architect framing:

- The question is exactly the human's: **history depth (number of samples)
  × interpolation algorithm** → smoothest perceived motion on a 275×240
  display, under real poll cadences (sweep 1/5/10/15/30 s — the item-A
  slider range).
- Candidate ladder (cheap-first): dead-reckoning from track+groundspeed with
  snap correction (the M-PLANERADAR design's original "M4-style follow-up");
  dead-reckoning with damped correction (alpha-beta style blend — kills the
  teleport artifact); one-poll-delayed linear interpolation; 3-point
  Catmull-Rom (delayed). History depth 1–3 samples per aircraft.
- Ground truth problem: the study needs ~1 s reference captures, but the
  standing host-probe rule is ≥60 s (shared per-IP 429 budget, TASK-313).
  The proposal must schedule capture deliberately: one bounded session from
  a network that is NOT the DUT's egress IP, or a DUT-quiet window with the
  budget burn accepted and logged. This is a protocol point, not a detail —
  it's why the rule exists.
- Preview: pygame animation harness (venv has pygame; M-PREVIEW-FRAMEWORK
  conventions) replaying captures — downsample ground truth to each cadence,
  reconstruct with each algorithm × depth, render side-by-side; metrics: RMS
  position error (px at each range preset), max correction jump (px — the
  teleport artifact), heading jitter; plus the human eyeball, which is the
  actual acceptance criterion for "smooth".
- Graduation constraints (so the study measures the right thing): math must
  be fixed-point-friendly and bounded per tick for ~20 aircraft on the
  no-PSRAM board; history RAM ≈ depth × aircraft-struct additions, keep it
  in the low KB; must degrade sanely when a plane's data goes stale
  (`prStaleStyle` interplay).

Production integration is NOT part of this milestone — the study delivers an
EXP report + recommendation; PM files the firmware task only after human
review of the graduation proposal.

## Effort / risk

Item A small (field + slider row + one constant-to-live-read change; the
WR-3 slider idiom is copy-adjacent). Item B is host-only and bounded by its
capture session; its only real risk is the 429-budget capture logistics,
handled above.
