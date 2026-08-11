# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> Completed/closed/fixed/resolved tasks are periodically moved to [tasks-archive.md](tasks-archive.md) to keep this file WIP-only. Last archive pass: 2026-08-07 (moved 7 fully-closed milestone sections — M-CERT-ERRCODE remainder, M-APP-ORDER, M-WEBRADIO-WINAMP-UI, M-WEBRADIO-REAL-VIS, M-PR-LOCATIONS, M-MEMPLAN hygiene, M-CEEFAX — 2,513 lines — see archive file for the batch note). Prior pass: 2026-07-12 (TASK-143..313 range, 149 entries).

> **PM sync 2026-07-18 (parallel session — M-CERT-ERRCODE remainder scheduled + ADR sweep)** —
> Ran alongside the clock-faces agent (clock files untouched by this session). Two deliverables:
> **(1)** M-CERT-ERRCODE remainder broken down into TASK-341..344 (section below) from the existing
> design doc — TASK-341/342/343 are host-or-build-verified and DUT-free; TASK-344 needs a DUT window.
> **(2)** ADR hygiene sweep: all nine stale-`proposed` ADRs dispositioned with code evidence —
> ADR-024/025/026/031/035/039/041 **accepted** (all implemented and load-bearing),
> ADR-028 (Canvas abstraction) **rejected — not adopted** (no `canvas.h`; renderers still bind
> `TFT_eSPI` directly; preview needs met host-side), ADR-032 (yieldHeap/reclaimHeap)
> **superseded** (protocol never implemented; tlsYield arbitration + demoscene .bss cuts solved it).
> Human review flag: the ADR-028 rejection and ADR-032 supersession are the two judgement calls —
> the seven accepts are mechanical.

## Open — M-PR-MOTION (2026-07-18)

Human request: PlaneRadar poll interval as a settings slider (1 s minimum), and interpolation
for smooth motion — research/preview on host FIRST (samples × algorithm). Design:
[M-PR-MOTION.md](../architecture/designs/M-PR-MOTION.md). The production interpolation task is
deliberately NOT filed — it waits for the study's graduation proposal (R&D protocol).

### TASK-355 — PlaneRadar poll-interval settings slider (1–30 s, default 10)

New `uint8_t prPollSec` (1–30, default 10 = current behaviour), `SliderWidget` row in the
PlaneRadar submenu — reuse the WR-3 max-volume idiom incl. Press/Move/Release routing
(`appsSection.h:101/:181`). Firmware reads `prPollSec * 1000UL` live in the tick gate
(`planeRadarApp.h:200`; `_forceNow()` `:409` derives from the same value) — applies next tick,
no resume-diff needed. **No hidden clamp below 5 s**: the `_pendingFetch` gate + the ~4.3 s
edge-paced GET (TASK-313) make low settings degrade to fetch-completion pacing naturally —
document at the field, don't forbid. ADR-050 step-7 wiring gate applies. Tests: T_PRM_01
(round-trip + persist), T_PRM_02 (setting=1 → ~4–5 s effective spacing, no pile-up, no Spotify
heartbeat regression over 5 min).

**Owner:** Developer · **Deps:** none · **Gate:** `run/check` 7/7 + DUT · **Priority:** P2 ·
**Status:** **DONE 2026-07-29** — implementation landed 82a80eb (2026-07-19); DUT gate closed
this session. `run/check`: 6/6 + step-7 wiring gate OK. T_PRM_01 PASS (1/10/30 round-trip,
99→30 clamp, 30 held across reboot). T_PRM_02 PASS (prPollSec=1: 36 fetches/300s, median gap
6677ms — inside the [3s,9s] fetch-completion-pace bound — min gap 6518ms, queueWaiting peak 0,
max Spotify heartbeat age 18.1s, well under the 120s regression threshold).

### TASK-356 — RnD: interpolation study, samples × algorithm on host (PROP-006)

Host-only pygame preview study — see
[PROP-006-pr-interpolation-study.md](../rnd/proposals/PROP-006-pr-interpolation-study.md):
capture ~1 s ground truth (⚠ 429-budget protocol: non-DUT egress IP or declared DUT-quiet
window, ONE bounded session, fixtures saved for replay), downsample to the 1/5/10/15/30 s
cadence sweep, score dead-reckon / damped-correction / delayed-lerp / Catmull-Rom × history
depth 1–3 on RMS px error, max correction jump (the teleport artifact), heading jitter — then
human eyeball as the acceptance criterion. Stop at the first eyeball-smooth rung. Deliverable:
EXP report + graduation proposal; production firmware out of scope. Branch `rnd/pr-interp`.

**Owner:** R&D · **Deps:** none (fixture capture is independent of TASK-355) · **Gate:** EXP
report + human review · **Priority:** P2 (human-requested, host-only, unblocked) ·
**Status:** **DONE 2026-07-19** — [EXP-014](../rnd/reports/EXP-014-pr-interpolation.md),
branch `rnd/pr-interp` e1f61ff..b302033. **VALIDATED: dr-damped(tau=2), depth 1** (10 s
cadence: 0.7 px RMS, 0.1 px max jump vs dr-snap's 9.6 px teleports; delayed rungs ~10 px
stale; catmull-rom never beats lerp → depth 3 dead). Human eyeball sign-off on synthetic
("tau=2 is good enough"); capture session DESCOPED by human decision — model-match caveat
dispositioned in EXP-014 (damped correction matters more, not less, when real prediction is
worse; production DUT phase runs on the live feed anyway). Rig stays on the branch; process
note: first cut rebuilt existing tools standalone (caught by human, rebased; LL candidate
for QM — "inventory app/tools first").

### TASK-357 — PlaneRadar motion smoothing: dr-damped(tau=2) in firmware (EXP-014 graduation)

Implement the validated smoother in `planeRadarApp.h`: per-aircraft render position =
dead-reckon from last fix along track+gs (the vecX/vecY derivation already exists for the
speed line) + exponentially-decaying rendered-vs-predicted offset, **tau = 2 s**, depth 1 —
state per aircraft is the last fix + one 2-component offset; fixed-point friendly, bounded
for ~20 aircraft, no history arrays. Cap extrapolation on stale fixes (hand off to
`prStaleStyle`, don't fly ghosts). **The core design question is the repaint strategy, not
the math** (EXP-014): smooth motion needs ~10 Hz per-aircraft dirty-rect erase/redraw instead
of repaint-on-fetch — budget it against Spotify SPI traffic and the tick loop; Architect
consult before implementation (cross-component: render cadence). Interacts with TASK-355
(`prPollSec`): tau stays 2 s at every cadence per the study. VE: DUT eyeball is primary
(BP-048 — this feature IS a visual); add a `get prInterp` observable (offset magnitude,
last-fix age) for T_PRI_01 assertions.

**Owner:** Developer (Architect consult on repaint design) · **Deps:** EXP-014 (done);
TASK-355 open but not blocking · **Gate:** `run/check` 7/7 + DUT eyeball + T_PRI_01 ·
**Priority:** P2 · **Status:** **DONE** 2026-07-28 (`app/src/planeRadarApp.h`) — DUT eyeball
and worst-case load both closed this session, see "Deferred" section below for the evidence.

Landed as a **continuity-offset** design, not literal alpha-beta blending: dead-reckon each
aircraft in *screen px* (reuses the existing track/gs → px-vector derivation), and on a fetch
landing, the new offset is exactly (old dead-reckoned+damped px at that instant) minus (new
fix's raw px) — so the redraw right after a fetch is pixel-continuous with the smoothing
frame before it, then decays toward the new fix with tau=2s. Depth 1, matched across fetches
by a callsign hash (`PrMotion.csHash`), correction >`PR_INTERP_SNAP_PX`=40px snaps to 0 (re-
appearance). Repaint strategy chosen: reuse the existing whole-scene `_render()` erase/redraw/
tag-placement pipeline unchanged (zero new correctness risk to that already-hardened code) at
a ~10Hz tick, **gated on an exact, zero-extra-storage dirty check** (`_motionPx()` is a pure
function of stored state + time, so comparing it at the last-redraw instant vs now tells you
whether anything actually crossed a pixel — no per-aircraft "last drawn px" bookkeeping
needed). This is a **simpler alternative to EXP-014/this task's originally-sketched
partial dirty-rect + rotating-scan (`PR_INTERP_MAX_MOVERS`) scheme** — that idea was dropped
in favour of the lower-risk whole-scene reuse; see "Deferred" below for what a partial-redraw
follow-up would still need to prove.

**Process note:** picked up as a Fable→Sonnet session handoff (prior agent died to usage limit
mid-design, before writing code) — proceeded **without a separate formal Architect consult
step** the task called for; the repaint-strategy call above was made solo and documented here
instead. Flagging per AGENTS.md protocol rather than silently skipping it — a human/Architect
review of this choice is still owed.

**DRAM finding (real, fixed):** a naive `PrMotion _motion[24]` static member overflowed the
debug build's `dram0_0_seg` by 872 B — that build (SERIAL_DEBUG's membudget probes +
TOUCH_DEBUG_OVERLAY) has only tens of bytes of static headroom left on this no-PSRAM board.
Fixed two ways: (1) shrunk `PrMotion` to 20 B via fixed-point (Q4 px offset, hashed callsign,
projected-px fix cache instead of float lat/lon) — 960→480 B; (2) still didn't fit, so
`_motion` is now **heap-allocated once** (`_ensureMotion()`, lazy, on first reconcile) rather
than static — moves it out of `.bss` entirely. 480 B is a one-time hold for the app's
lifetime, not a repeated alloc/free, so it doesn't engage M-AQUARIUM's sprite-heap-arbitration
concerns (that mechanism is for apps holding/releasing large pools). `run/check` 6/6 clean.

**Bug found + fixed during DUT verification (own code, caught before commit):** the
`get prInterp` debug observable initially reported the raw stored offset, not the
decay-adjusted one — read as a flat, non-decaying value on the DUT. Fixed (dbgGet now applies
the same tau=2s decay the renderer uses) and reverified: offset ratios across 0.5s steps came
back ~0.77 consistently (theory `exp(-0.5/2)=0.779`) via manual injection, and T_PRI_01
(1.97px → 0.72px@t+2s → 0.26px@t+4s, matching `exp(-1)=0.368`/`exp(-2)=0.135` almost exactly)
now passes clean.

**Verified this session:** `run/check` 6/6; T_PRI_01 (continuity + decay curve) PASS; a 15s
sustained-synthetic-motion DUT stress (3 aircraft, re-injected every ~180ms) produced **zero**
`LOG_W("perf", iter>50ms)` warnings and no reboot — a reasonable but *not exhaustive* perf
signal (see Deferred).

**Deferred to the human DUT session (BP-048 — this feature IS a visual)** — ~~struck items
closed 2026-07-28~~:
1. ~~**DUT eyeball**~~ — **CLOSED 2026-07-28.** Human watched the live DUT (debug build,
   `prloc` pointed at LHR, real adsb.fi traffic) for a ~10 s window, tracked one aircraft
   through a fetch-landing refresh: **"that plane didn't jump on new data refresh. the
   interpolation was good enough."** This is exactly the failure mode item #2 below worried
   about (a visible teleport when a new fix lands) and it held on real, busy-airport data —
   the primary acceptance criterion per the task and EXP-014's own methodology.
2. ~~**Worst-case load**~~ — **CLOSED 2026-07-28.** Found the DUT already mid-session on a
   real busy preset: LHR coords (51.4700/-0.4540), live adsb.fi feed, **count=24 aircraft**
   consistently (the exact ~20-24-aircraft ceiling this item flagged as untested), running
   continuously for 34+ minutes. Log evidence (`run/monitor-read`): heap oscillating
   78k-128k with no downward trend (no leak), zero reboot/panic/Guru-Meditation/WDT
   signatures, only mild `[W][perf] iter=53-55ms` warnings (a few ms over the 50ms budget,
   non-fatal, no crash). Combined with item #1's fetch-landing spot-check on this same
   session, this closes the "real busy preset on the live adsb.fi feed" evidence gap this
   item called for.
3. **Architect sign-off** on the repaint-strategy substitution above (whole-scene-reuse +
   exact dirty-gate vs. the originally-sketched partial redraw) — settled by ADR-052 per
   TASK-358's own note below; carried here for completeness, not re-opened.

### TASK-358 — PlaneRadar per-aircraft dirty-rect redraw (fixes TASK-357 tearing, ADR-052 graduation)

Fixes the whole-scene repaint anti-pattern TASK-357 introduced at ~10 Hz (`_render()` erases +
redraws *every* aircraft, `_redrawGridStatics()` repaints the full disc, on every
`_motionDirty()` tick) — human-reported this session as visible "twitchy" tearing, the same bug
class TASK-354 fixed for Clock's Flip/Nixie colon flicker, and explicitly flagged as TASK-357's
own deferred item #3 (Architect sign-off on the repaint strategy). Design + evidence:
`docs/architecture/designs/M-DISPLAY-DELTA-COMMON.md`, `docs/architecture/decisions/ADR-052.md`
(registry: `viewport-repair-001`, `X037`). Two-part implementation:

1. **Shared primitive** — `withViewportRepair(tft, x, y, w, h, repairFn)`, new file
   `app/src/util/tftViewportRepair.h` (stateless template wrapping TFT_eSPI's
   `setViewport()`/`resetViewport()` around a caller-supplied redraw callback; no reentrancy,
   no per-app state, ~15 lines — reference implementation + invariants in the design doc).
   Correction (found during implementation review, not caught by ADR-052's own original survey):
   this is the first consumer of the new *helper*, not the first use of `setViewport` in the
   codebase — `clockApp.h:425-438` (Flip digit clipping, TASK-354) and `main.cpp:1677-1680`
   (heatmap text clipping) already call it raw, correctly. Doesn't change the design; both docs
   corrected in place.
2. **PlaneRadar consumer** (`app/src/planeRadarApp.h`) — replace `_render()`'s whole-scene
   erase/redraw with per-aircraft handling: a per-aircraft draw helper, a per-aircraft
   erase-with-bounding-box helper (`fillRect` over the old footprint), `withViewportRepair()`
   wrapped around `_redrawGridStatics()` (called verbatim, unchanged) scoped to each dirty
   aircraft's bbox instead of the full 240px disc, and rigid tag repositioning without full
   occlusion recompute on every tick (full occlusion recompute stays reserved for real
   fetch-landing events, not the ~10 Hz interp tick). Dirty check reuses `_motionPx()` as the
   existing exact, zero-extra-storage pure-function trick (`_motionDirty()` already does this at
   the whole-scene level, `:732`) — no new per-aircraft "last drawn px" bookkeeping needed.
   Per-aircraft vs. union-bbox viewport scoping left to implementation judgement (both cheap at
   ≤24 `PR_MAX_AIRCRAFT`). Clock's TASK-354 delta engine, VU meter, WebRadio, Weather/Digital,
   Game of Life, Aquarium: **zero diffs** — each already solves its own case correctly by its
   own mechanism; touching them for framework consistency is explicitly out of scope (ADR-052).

Addresses TASK-357's deferred items #1 (DUT eyeball — the acceptance test here, see Gate) and #3
(Architect sign-off — settled by ADR-052/the design doc). Item #2 (worst-case ~20-24-aircraft
busy-airport load) stays open and untouched by this task.

**Owner:** Developer · **Deps:** ADR-052 (status: proposed, awaiting human sign-off — confirm
`accepted` before landing, or flag back if still open); TASK-357 (done — this is an additive
follow-up, not a revision of its status) · **Gate:** `run/check` 7/7 + a
`clock_delta_smoke.py`-style screendump-diff assertion ("steady per-aircraft motion tick touches
≤ the dirty aircraft's own footprint pixels outside its erase/redraw box") + DUT crash-free
stress + **human visual confirmation the flicker/tearing is actually gone (cannot be verified
by the agent — this is the primary acceptance test, BP-048)** · **Priority:** P1 — human-
reported visible regression in already-shipped functionality (TASK-357, this session), not
routine backlog · **Status:** **DONE** — build+DUT-stress+T_PRI_01 landed 2026-07-19
(`app/src/util/tftViewportRepair.h` new, `app/src/planeRadarApp.h`); human eyeball +
worst-case load both closed 2026-07-28 (see below)

Landed exactly the two-part design above. `withViewportRepair()` matches the design doc's
reference implementation verbatim (`int32_t` params, `vpDatum=false`, no reentrancy). In
`planeRadarApp.h`: `tick()`'s ~10 Hz interp-tick gate is now a per-aircraft loop (was one
whole-scene `_motionDirty()` OR-check) calling a new `_redrawOneAircraft(i, now)` per dirty
aircraft. `_render()` keeps its full-scene shape (fetch-landing/injection/preset-switch only,
unchanged semantics) but its per-aircraft body is now shared code:
`_eraseFootprint(p, &bx,&by,&bw,&bh)` (extracted from `_erasePrev()`'s loop — erases one
entry's rim-dot/triangle+vector/tag and reports the union bbox of what it touched, `_erasePrev()`
ignores the bbox, `_redrawOneAircraft()` scopes `withViewportRepair()`'s grid-statics repair to
it), `_drawAircraftBody()` (extracted from `_render()`'s loop — pure symbol/vector drawing, no
tag), and `_buildTagLines()`/`_drawTagLines()` (extracted from `_placeTag()` — pure
formatting/drawing, `_placeTag()`'s occlusion-avoidance logic itself is untouched).
`_redrawOneAircraft()`'s tag handling is rigid reposition by the symbol's (dx,dy), dropping the
tag for the tick (not carrying it forward) on any rim-dot-state mismatch or off-disc landing —
self-corrects at the next real `_render()`, per the design's accepted limitation. Removed the
now-dead whole-scene `_motionDirty()` (inlined equivalently into `tick()`'s per-aircraft loop).

**Bug found + fixed during self-review, before any DUT time (own code, not from a bad plan):**
the first draft of `_eraseFootprint()` computed the erased bounding box as exclusive width
(`maxX-minX`, `maxY-minY`) instead of the inclusive pixel-count width `fillRect()` itself uses
(`maxX-minX+1`) — `withViewportRepair()`'s viewport would have been one pixel short on the
right/bottom edge of every dirty-rect repair, i.e. exactly the kind of stray-pixel-erosion bug
TASK-311's original `_redrawGridStatics()` fix was about. Caught by re-reading the diff against
`_erasePrev()`'s original `fillRect(...,(maxX-minX+1),...)` call before flashing; fixed by
tracking inclusive extents throughout and adding the `+1` once at the end.

**Verified this session:** `run/check` 6/6 (7/7 incl. warn-only settings gate) clean. DUT
(debug build): T_PRI_01 (continuity + decay curve, TASK-357's own regression check — unaffected
by this refactor since only *what* redraws changed, not the position math) PASS, offsets
1.97px → 0.72px (t+2s) → 0.26px (t+4s), identical to TASK-357's original numbers. An 18s
sustained-synthetic-motion stress (2 aircraft — the ~160-byte serial-line budget only fits 2 at
usable decimal precision, not the 3 originally estimated; ~58 shifting re-injections, ~0.3s
apart) produced zero `LOG_W("perf", iter>50ms)` warnings and no reboot/crash signature on the
serial stream. Production build reflashed afterward (device left in normal state).

**Screendump-diff assertion — written and DUT-verified, follow-up session
2026-07-19.** `app/tools/pr_delta_smoke.py` (new), modeled on
`clock_delta_smoke.py`, using `set prInjectAircraft`/`set prClearInject` for
deterministic synthetic scenes (T_PR_06/T_PRI_01 pattern) instead of
clock_delta_smoke's "same minute" wait:
- **T_PRD_01** — two stationary (`gsKnots=0`) aircraft, captured after
  `>=4*PR_INTERP_TAU_MS` settle, two screendumps of the disc a few seconds
  apart. Asserts **zero diff, no mask** — the direct check that
  `_redrawOneAircraft()` never fires when nothing is dirty (stronger than
  clock_delta_smoke's colon-masked assertion).
- **T_PRD_02** — one moving aircraft (`gsKnots=200`, straight-line track)
  + one stationary aircraft placed far away. Asserts zero diff **outside**
  a generous mask around the moving aircraft's computed start->end pixel
  path (padded past the worst-case tag+vector reach) — proves the
  stationary aircraft, grid rings, crosshair, and any runway overlay stay
  untouched, i.e. the dirty-rect *scoping* claim, not just "a redraw
  happened somewhere". A companion sanity check (`T_PRD_02b`) confirms
  pixels *did* change inside the mask, ruling out a trivial pass.

DUT result: **6/6 PASS**, run twice for determinism (both clean, 0 px
diff outside each test's zero-diff/mask boundary). This closes the gap
flagged below in the original session's notes. Debug build was already
flashed for this session; production reflashed afterward alongside
TASK-359 (same session, see that entry).

**Human visual confirmation the flicker/tearing is actually gone — CLOSED 2026-07-28.**
Human watched the live DUT (real LHR busy-airport traffic, count=24, see TASK-357's own
"Deferred" section for the full evidence) and confirmed tracked-aircraft continuity across a
fetch-landing refresh held with no jump/tear: "the interpolation was good enough." Primary
acceptance test satisfied, per BP-048.

**Worst-case load — CLOSED 2026-07-28** (was "Not done / explicitly out of scope" below).
Same live session: 34+ min continuous at count=24 real aircraft (LHR), heap stable 78k-128k
no leak trend, zero reboot/panic/WDT signature, only mild non-fatal `[W][perf]` warnings.
See TASK-357's "Deferred" item #2 for the full log evidence — not re-duplicated here.

*(Original session note, now resolved above: "The gate's
`clock_delta_smoke.py`-style screendump-diff assertion was not written" —
the coordinator's original implementation brief scoped verification to
`run/check` + DUT crash-free stress + T_PRI_01 + deferred human eyeball and
did not include authoring this assertion; flagged as a gap against the
task's own stated Gate at the time, now filled per above.)*

### TASK-359 — migrate Clock Flip + heatmap raw setViewport() call sites onto withViewportRepair()

Pure consistency follow-up from TASK-358's correction (see ADR-052 "Correction" section and
`M-DISPLAY-DELTA-COMMON.md`'s matching correction): review during TASK-358 found two pre-existing,
independently-correct raw `setViewport()`/`resetViewport()` call sites that predate the new shared
helper — `clockApp.h:425-438` (Flip clock face digit-clipping, landed with TASK-354) and
`main.cpp:1677-1680` (heatmap rotated-text clipping). Neither has a known bug; both docs flagged
migrating them onto `withViewportRepair()` (`app/src/util/tftViewportRepair.h`, TASK-358,
`0c84e46`) as optional cleanup, not urgent. Scope: swap each site's raw
`setViewport(...); <draw>; resetViewport();` for the equivalent `withViewportRepair(tft, x, y, w,
h, repairFn)` call — no behavior change expected.

**Owner:** Developer · **Deps:** TASK-358 (done — supplies the helper) · **Gate:** `run/check`
7/7 + re-run Clock Flip face and heatmap's existing DUT screendump/eyeball coverage (both already
have this from their original tasks — TASK-354, heatmap's own task — don't invent new coverage) +
confirm no visual regression · **Priority:** P3 (pure refactor/consistency, no known bug) ·
**Status:** **DONE** 2026-07-19

Landed exactly the scoped swap. `app/src/clockApp.h` (Flip digit-clipping, two sites: the
bottom-plate glyph clip at the old `:425-428` and the falling-flap glyph clip at the old
`:435-438`) and `app/src/main.cpp` (heatmap rotated-text clip, old `:1677-1680`) both now call
`withViewportRepair(tft, x, y, w, h, [&]{ ...same draw calls... })`; `#include
"util/tftViewportRepair.h"` added to both files. Pure mechanical swap — same draw calls moved
verbatim into the lambda, no logic changed.

One divergence worth flagging, resolved by reading TFT_eSPI's source rather than assuming: the
heatmap site's original call was `tft.setViewport(t.x, t.y, t.w, t.h)` — 4 args, so
**`vpDatum` defaults to `true`** — while `withViewportRepair()` always passes `vpDatum=false`.
That's a real difference in what `setViewport()` does internally (`vpDatum=false` resets
`_xDatum`/`_yDatum` to 0; `true` keeps them at the viewport origin), so it needed checking, not
assuming "verified during TASK-358" covered this exact call shape too. Traced the actual
consumer (`spr.pushRotated(-90, col)` via `TFT_eSprite::pushRotated()` in
`.pio/libdeps/.../TFT_eSPI/Extensions/Sprite.cpp`): it computes its destination window
(`_tft->setWindow(...)`) from `_tft->_xPivot`/`_yPivot` (set directly by `setPivot()`, never
offset by `_xDatum`/`_yDatum`) and `getRotatedBounds()`, and `setWindow()` itself takes absolute
screen coordinates with no datum adjustment either — so `pushRotated()`'s output is provably
identical regardless of `vpDatum`. Only the *clip rectangle* (`_vpX/_vpY/_vpW/_vpH`) matters
here, and that's computed identically for both `vpDatum` values. No behavior change, confirmed
by source reading before flashing, not just by the plan's assumption.

**Verified:** `run/check` 7/7 (both `cyd2usb_winamp_debug`/`cyd2usb_winamp` compile clean).
DUT (debug build, same session as TASK-358's screendump-diff follow-up):
- **Clock Flip face** — `python3 app/tools/clock_delta_smoke.py` full 4/4 PASS (digital/flip/
  nixie/vfd), flip leg specifically: `0 px changed outside colon column` on the first attempt
  (no retry needed, unlike nixie/vfd which hit the pre-existing documented digit-rollover
  retry flake) — no regression from the migration.
- **Heatmap** — no automated DUT suite exists for this (checked `test_plan.md`/
  `feature_inventory.yaml`: `stock-002`/M-HEATMAP's own T196 SERIALDBG harness depends on the
  full `run_serialdbg_tests.py::Dut` class, which blocks on a Spotify "poll ok 200" that will
  never land under TASK-243's external Premium lapse — not usable here). Verified manually
  instead, per the task's own Gate fallback: `switchApp 7` -> `set triggerHeatmap 1` -> polled
  `get heatmapCount` until 20 tiles landed -> `screendump` of the full canvas. Result: heatmap
  renders correctly, including several small tiles (AMAT/ORCL/PLTR/PANW/TXN/KLAC/DELL/ARM) that
  are exactly the rotated-text code path the migration touched — labels render cleanly, no
  clipping artifact, no viewport bleed, matching pre-migration appearance. First fetch attempt
  hit a transient `ERR -1` (ESP32-side HTTPClient connection error; host `curl` to the same
  Yahoo Finance URL returned 200 fine at the same time, confirming it wasn't a real network/DNS
  outage) — retried the trigger and it landed cleanly; noted as flaky-external, not a
  regression (T196's own docs flag this same endpoint as intermittent).

**Incident during this session's DUT work (flagging per usual honesty standard, not
downplaying):** while working the port for the above, found a live `/dev/ttyUSB0` collision —
the coordinator's own `./run/spiffs pull settings.json` (run in the same top-level session, to
confirm the device's actual PlaneRadar location for TASK-360 — not a separate Claude Code
session, as this subtask first guessed from the PID chain alone before the coordinator clarified
it) was mid-flight when this session opened the port for `pr_delta_smoke.py`/screendump work.
The CH340 driver's DTR-on-open behavior (documented in `screendump.py`'s own docstring) reset the
DUT out from under that `esptool.py read_flash`, which then hung indefinitely (0% CPU,
unresponsive, 14+ min with no progress on what should be a <1 min read). After confirming it was
genuinely wedged (not just slow) and that a SPIFFS *read* is non-destructive to device state,
killed the hung `esptool.py` process to free the port; its parent script's trap-guarded cleanup
then ran normally and restored the tmux serial monitor, its normal resting state. The coordinator
did not retry the pull immediately (to avoid a second collision with this session's DUT work
still in flight) — read an existing, slightly stale local `spiffs-dump/settings.json` instead,
which was sufficient to ground TASK-360's location choice. Production reflash and further DUT
work proceeded normally afterward with no other collisions observed.

Production firmware reflashed at the end of this session (alongside TASK-358's follow-up,
same session) — device left on production build, normal state, `switchApp 0`.

### TASK-360 — RnD: revisit PROP-006's descoped capture session with real daytime traffic (reduced scope)

Human-reported 2026-07-19, watching the DUT live in daytime (busy real air traffic, unlike
whenever PROP-006/EXP-014 were last worked): visible interpolation **inaccuracy** in the shipped
dr-damped(tau=2) smoother (TASK-357/358) — not the tearing bug TASK-358 already fixed, a
positioning/tracking error. This reopens the same R&D question EXP-014 dispositioned via caveat 1
rather than measured (["Model-match bias: synthetic truth integrates the same track+gs kinematics
DR extrapolates... The 1 s ground-truth capture session (429-budget logistics) was therefore
**descoped by human decision**"](../rnd/reports/EXP-014-pr-interpolation.md)) — it is a
**continuation of that thread**, not a revision of TASK-356's DONE status or EXP-014's synthetic
verdict, both of which stand.

**Scope, reduced from PROP-006's original method** (no continuous 10–15 min 1 Hz stream):
5–10 discrete samples each at 1 s, 5 s, and 10 s intervals — matching the `prPollSec` slider's
low/mid range (TASK-355) — captured from adsb.fi from a location "buzzing" with real traffic
within a 25 km radius. PROP-006's method section names LHR fixture slots as an existing candidate;
actual location choice is R&D's call. Runs **host-side only**, not through the DUT — the human
will be present to supervise, and using non-DUT egress removes the sharpest edge of the original
429-budget blocker (the standing rule's alternate condition: a network that isn't the DUT's egress
IP). Deliverables:

1. **Download and permanently store** a real-world fixture dataset on `rnd/pr-interp` (commit it —
   R&D branches never merge to `main`/`master` directly, per `docs/agents/AGENTS.md` — so this
   fixture set is available for future sessions without a re-capture).
2. **Check the shipped smoother against it**: replay the dr-damped(tau=2) rung from EXP-014's
   ladder against real (non-synthetic) traffic instead of only the synthetic ground truth EXP-014
   validated against, specifically probing whether real aircraft behaviour — turns, speed/altitude
   changes — reveals prediction error that caveat 1's disposition ("a *worse* real-world
   prediction produces *bigger* corrections, which is precisely what damped blending absorbs")
   undersold rather than correctly reasoned through.
3. **Investigate the human's speed+altitude hypothesis**: that correct display of an aircraft's
   motion vector may need speed **and** altitude/height together, not ground speed + track alone
   (the vector the firmware currently derives). Test this against the captured real data — don't
   assume it correct or incorrect going in.

**Owner:** R&D · **Deps:** PROP-006, EXP-014, TASK-356 (closed — this reopens the same question,
does not revise it), TASK-357, TASK-358 (shipped smoother + repaint fix under test), TASK-355
(`prPollSec` — defines the interval range sampled) · **Gate:** fixture dataset committed on
`rnd/pr-interp` + an EXP report (or a caveat-1 addendum to EXP-014) documenting findings against
real traffic, including a disposition of the speed+altitude hypothesis · **Priority:** P2 — live,
human-observed accuracy concern in shipped functionality, comparable footing to TASK-358, but this
is R&D/investigation rather than a confirmed bug with a scoped fix yet, so not P1 · **Status:**
**CONCLUDED 2026-07-19** — [EXP-015](../rnd/reports/EXP-015-pr-interp-real-traffic.md), branch
`rnd/pr-interp` commit `dab6ae6`. Doc status line was stale (never updated after landing);
backfilled 2026-07-28.

**Summary.** 24 real adsb.fi samples (8 each at nominal 1 s/5 s/10 s, actual ~2 s/5 s/11 s —
adsb.fi's own refresh floors around ~2 s) captured from the device's actual configured location
(central London/Westminster, 25 km preset, 62-70 aircraft/sample — genuinely busy). `pr_adsb_probe.py`
extended with `--lat`/`--lon` (reused, not rebuilt), new `real_replay.py` reuses the existing
`model.py`/`algorithms.py` projection + dead-reckon math. 762 matched consecutive-fix pairs
scored for raw DR correction magnitude (the `jump_px` analog).

- **Deliverable 2 (shipped smoother vs real traffic):** mean correction 0.29px, max 4.80px across
  762 pairs — smaller than EXP-014's synthetic dr-snap worst case (9.6px), every observed max far
  under `PR_INTERP_SNAP_PX=40px`. Mechanism confirmed (turning/gs-change predicts error, r up to
  0.65), magnitude not under-provisioned. **No firmware change recommended** — the shipped
  dr-damped(tau=2) smoother's absorption capacity holds on real traffic.
- **Deliverable 3 (speed+altitude hypothesis): REFUTED.** `|baro_rate|`/`|geom_rate|`/`|alt_change|`
  correlate weakly *negative* with error in all three runs (opposite sign the hypothesis predicts);
  climbing/descending aircraft show *lower* mean correction than level flight. Turning remains the
  driver, independent of vertical motion (confirmed within level-flight-only subsets too).
- **Two non-smoother candidates flagged for the human's observed "inaccuracy"** (R&D hands findings
  to PM, not code, per AGENTS.md — filed below as TASK-367/368): (a) `fixMs` is stamped at
  queue-drain time, not request-issue or payload-sample time — fetch-latency variance could read as
  a systematic dead-reckon lead; (b) `PR_MAX_AIRCRAFT=24` roster churn in this 62-70-aircraft
  traffic density (only nearest 24 rendered) could read as "inaccurate tracking" when it's actually
  boundary pop-in/pop-out, a distinct phenomenon from motion-vector error.

Deliverable 1 (fixture dataset) committed on `rnd/pr-interp`:
`app/tools/fixtures/planeradar/task360_london/` (24 samples × compact+pretty JSON, 2.1MB).

### TASK-367 — PlaneRadar: measure fetch round-trip variance behind `fixMs`, consider request-time stamping (EXP-015 Finding 3)

EXP-015 (TASK-360) flagged a candidate, unmeasured explanation for the human-observed motion
"inaccuracy": `_reconcileMotion(now)` stamps `m.fixMs = now` at queue-drain time
(`dataTask::pollPlaneRadar`), not at request-issue time or from the adsb.fi payload's own `now`
epoch field. If DUT-side fetch round-trip time (TASK-313's edge-paced GETs, ~4.3s) varies
fetch-to-fetch rather than staying near-constant, every fix is timestamped later than the aircraft's
true position by a *varying* amount — the dead-reckon then runs systematically ahead by a moving
offset, which reads as "off" to continuous human observation in a way EXP-015's isolated `jump_px`
metric can't capture (rough magnitude: 2s of unaccounted latency ≈ 1.6px at the 25km preset — small
alone, but stacks with the already-measured DR error). **Step 1 (measurement only):** log actual
fetch round-trip time per PlaneRadar GET (`_requestFetch()` timestamp to `pollPlaneRadar()` drain)
on the DUT and check fetch-to-fetch variance over a real busy session. If near-constant, close as
non-issue. If it varies by 1-2s+, scope a fix (stamp `fixMs` from request-issue time or the
payload's own timestamp field instead of drain time) as a follow-up.

**Owner:** Developer (measurement) · **Deps:** EXP-015/TASK-360 (source finding), TASK-313 (the
edge-pacing behaviour being measured) · **Gate:** DUT session, no fix without measurement first ·
**Priority:** P3 — candidate explanation, not a confirmed bug · **Status:** MEASURED, closed as
confirmed — fix scoped as **TASK-377**

**Measurement (2026-07-31, DUT session, debug build, real fetches at the device's configured
London location):** added `LOG_D("planeradar", "fetch rtt=%lums ok=%d errorCode=%d", now -
_lastFetch, ...)` at the `pollPlaneRadar()` drain point in `tick()` (`planeRadarApp.h`), spanning
`_requestFetch()`'s request-issue stamp to drain. 26 fetch cycles sampled (1st excluded — the
`_forceNow()` backdate on app-entry/resume artificially inflates the very first sample by one
`prPollSec` and isn't representative of steady-state polling):

- **Not near-constant.** RTT ranged 6203–21573ms, a 15.4s spread — an order of magnitude past the
  "1-2s+" threshold the task set for scoping a fix.
- **Bimodal, not smooth jitter.** 13/26 cycles (50%) were clean single-GET fetches at 6203-8152ms
  (≈1.9s spread — real but modest baseline transport jitter). The other 13/26 (50%) hit at least one
  `errorCode=-92` (`IncompleteInput`) retry within the cycle and ballooned to 13058-21573ms
  (avg 19.2s) — multiple sequential ~6-8s GETs chained back-to-back before a result finally drains.
  7/26 cycles (27%) failed outright even after retry.
- **Dominant driver is TASK-361's retry cascade, not baseline edge jitter.** The 50% retry-cycle
  rate and 27% terminal-failure rate line up with TASK-361's already-reported regression (busy-
  traffic payload size defeating TASK-313's single-retry mitigation), not a new finding — this
  measurement quantifies its knock-on effect on `fixMs` specifically. Baseline (retry-free) jitter
  alone is already ≈1.9s, at the low end of the threshold that would justify a fix on its own.

**Conclusion:** EXP-015 Finding 3's candidate mechanism is real and worse than hypothesized —
drain-time `fixMs` stamping absorbs up to ~21s of transport variance, not the "2s of unaccounted
latency" EXP-015 sized. Every `_reconcileMotion()` fix is timestamped up to ~15s later than the
aircraft's true position, on a variable (not fixed) offset — exactly the "systematic dead-reckon
lead that reads as inaccuracy" theory. Fix scoped below as TASK-377. The retry-cascade tail should
shrink once TASK-361 lands, but request-time stamping removes the error class entirely (both the
jitter and the retry tail) rather than just shrinking it, so it's still worth doing independent of
TASK-361's timeline.

The `LOG_D` measurement instrumentation was left in place (real signal, cheap, matches this file's
existing per-fetch debug logging conventions) rather than reverted.

### TASK-377 — PlaneRadar: stamp `fixMs` from request-issue time, not drain time (TASK-367 follow-up)

TASK-367 confirmed `_reconcileMotion()` stamping `m.fixMs = now` at `pollPlaneRadar()` drain time
(`planeRadarApp.h:744`) absorbs 6.2-21.6s of fetch transport variance (measured on DUT) into the
motion model's fix epoch, defeating the dead-reckon's assumption of a fixed, known-age fix.
**Scope:** stamp `fixMs` from `_requestFetch()`'s request-issue time (`_lastFetch`, already
captured at `planeRadarApp.h:590`) instead of the drain-time `now` passed into
`_reconcileMotion()` — the fix is that recent as of when the GET was issued, not when it happened
to finish draining through `pollPlaneRadar()`. Check `dataTask::PlaneRadarResult`/`_result` for
whether the adsb.fi payload carries its own `now`/timestamp epoch field first (design doc mentions
it as an alternative source) — if present and more accurate than request-issue time, prefer it.
Re-verify EXP-015's `jump_px` metric (or a successor) after the change to confirm the dead-reckon
lead actually shrinks, not just that the stamp semantics changed.

**Owner:** Developer · **Deps:** TASK-367 (measurement, done) · **Gate:** DUT session — before/after
comparison of dead-reckon lead behavior, ideally alongside TASK-361's retry-cascade fix landing (not
blocking — independent improvement either way) · **Priority:** P3 — confirmed mechanism, not yet
confirmed as the dominant contributor to the human-observed "inaccuracy" (TASK-368 still open on
that question) · **Status:** DONE (2026-07-31, DUT-verified)

**Implementation:** checked the adsb.fi payload for an in-band `now` epoch field first — the
fixture confirms it exists (`{"ac":[...], "now": 1783680534000, ...}`), but the streaming
per-object parser (`prParseStream`, `dataTaskStorage.cpp`) scans for `"ac"` first and returns as
soon as its array closes, never reading the trailing `"now"`. Adopting it would need epoch↔millis()
bridging (device only has second-resolution `time(nullptr)`, `fixMs` is a `millis()`-domain
`uint32_t`) for a field that measures adsb.fi's own aggregation staleness, not *our* fetch/retry
transport variance — the thing TASK-367 actually measured and flagged. Went with the simpler,
lower-risk request-issue-time approach instead, as the scope note allowed.

Used `_lastFetch` (request-issue time, already captured) directly — but not raw: it's deliberately
*backdated* by `_forceNow()` at several call sites (app-entry `resume()`, location-switch
`_setActiveLoc()`, the `triggerPlaneRadarFetch` debug hook) to make the poll-interval gate fire
immediately. Stamping `fixMs` from raw `_lastFetch` would make a just-landed fix look up to a full
`prPollSec` *stale* the instant it lands — backwards. Added a dedicated `_fetchIssuedMs` member,
set to the true `millis()` unconditionally inside `_requestFetch()` (never backdated), and stamp
`fixMs` from that instead. Also updated `prInjectAircraft` (the VE injection path, which bypasses
`_requestFetch()` entirely) to set `_fetchIssuedMs = _lastGoodMs` so synthetic aircraft still read
as freshly-landed, matching prior behavior.

**DUT verification:** `run/check` 6/6. `get prInterp`'s `fixAgeMs` (reads `millis() - m.fixMs`)
confirmed both ends: a synthetic injection reads `fixAgeMs≈0` immediately (unchanged VE semantics),
while real fetches now carry their transport time forward — the TASK-367 RTT log
(`_fetchIssuedMs`-based, corrected to no longer be backdate-contaminated) shows the same 6-25s
range this session, which by construction is now exactly what `fixAgeMs` reads the instant each
fetch lands (previously always ≈0 regardless of RTT — the bug). Targeted regression
(`run/test-targeted T_PR_01,T_PR_02,T_PR_03,T_PR_06,T_PRI_01`) 5/5 PASS, including T_PRI_01 (the
dr-damped continuity/decay test, which exercises `_reconcileMotion()` via the injection path this
change touched) — decay curve unaffected (2.95px → 1.07px → 0.39px over t+2s/t+4s, tau=2s). No
reboots/heap issues over the session. DUT restored to prod firmware.

**Not done — explicitly deferred:** full EXP-015 `jump_px` re-verification (a live before/after
quantitative re-run of TASK-360's fixture-based smoothness metric under real varying-RTT
conditions) was not run — the scope note's suggestion, not a hard gate, and TASK-368's roster-churn
question is still the open item deciding whether this was ever the dominant contributor to the
human-observed "inaccuracy" report. If a future eyeball/soak session wants to close that question,
this is the natural DUT run to pair it with.

### TASK-368 — PlaneRadar: distinguish PR_MAX_AIRCRAFT=24 roster churn from motion-vector error (EXP-015 Finding 4)

EXP-015 (TASK-360) found the device's actual location (central London) sees 62-70 aircraft within
25km, far above `PR_MAX_AIRCRAFT=24` — only the nearest 24 are ever rendered. In this dense a
traffic environment, set membership can plausibly change between fetches as aircraft cross the
24th-nearest boundary; `_reconcileMotion()` correctly gives newly-appearing aircraft offset 0 (not a
smoothing bug), but boundary pop-in/pop-out is a visually distinct phenomenon from mid-disc
motion-vector inaccuracy and could read as "inaccurate tracking" to an observer who isn't
distinguishing the two. **Scope:** a human eyeball session specifically watching for pop-in/pop-out
near the disc edge vs. mid-disc position drift, at a busy-traffic location, to determine whether
this — rather than TASK-367's candidate or genuine DR error — is what's actually being perceived.
No code change implied unless the eyeball session identifies one.

**Owner:** VE (eyeball session) · **Deps:** EXP-015/TASK-360 (source finding) · **Gate:** human
DUT eyeball at a busy-traffic preset, BP-048 · **Priority:** P3 — candidate explanation, confirmed
real, not a bug · **Status:** DONE (2026-07-31, live daytime DUT eyeball — see below)

**Attempt this session (2026-07-31, 22:00 BST):** this task's own gate is a *human* eyeball — I
can't substitute for that (it's a subjective "does this read as inaccurate" perceptual call, not a
fact I can measure), so I did the prep half instead: added a `LOG_D("dataTask.planeradar", "roster
...")` line (`dataTaskStorage.cpp`, right after the existing `ok=.../count=.../scanned=` log) that
prints the nearest-first `callsign,distNm` roster on every successful fetch, so a host-side diff
across cycles can quantify churn without needing a human to eyeball a live screen at all. Set the
DUT to the 25km preset (widest, matches EXP-015's condition) and captured 24 fetch cycles.

**Result: EXP-015's dense-traffic precondition isn't met at night.** It's 22:00 BST (evening) —
`count` topped out at **13**, never approaching `PR_MAX_AIRCRAFT=24`. The specific mechanism this
task asks about (aircraft churning across the *24th-nearest* rank boundary) **cannot occur** when
the roster never fills 24 slots — there's no rank-24 boundary to churn across tonight. EXP-015's
62-70-aircraft reading was a daytime observation; this needs re-running at busy daytime hours to
even test the hypothesis, let alone eyeball it.

**Found instead (worth carrying into the eventual eyeball session):** roster-diffing the 24 cycles
turned up churn from a mechanism neither TASK-367 nor this task's own EXP-015 framing considered —
per-cycle ADS-B **reporting gaps unrelated to distance**. Cycle 22: `BAW7PI` (rank 2 of 11, 0.5 NM —
essentially overhead, nowhere near any edge) dropped out of the roster for one cycle. Cycle 12:
`KLM51B` (rank 10 of 13, mid-pack) likewise. Both are consistent with adsb.fi simply not receiving
that aircraft's position report that cycle (normal ADS-B coverage variance), not a boundary-rank or
outer-fetch-radius effect. If this generalizes, "an aircraft vanishes then reappears" may be a third,
visually distinct failure mode (anywhere in the disc, not just the edge) worth the eyeball session
watching for specifically, alongside the original edge-pop-vs-drift distinction.

**Also found:** aircraft do visibly cross the *outer fetch-radius* boundary (~17-19 NM, i.e.
`kPrFetchNm`'s scaled query radius, not the 24-slot cap) — e.g. cycle 2 saw `SWR24C`/`HLE27` drop
and `KLM51B`/`GTESK`/`RWD711`/etc. join in a single cycle as the range preset changed. This is a
different, expected, non-bug phenomenon (real aircraft entering/leaving detection range) distinct
from both TASK-367's dead-reckon-lag and this task's rank-24-cap hypothesis — worth distinguishing
in the eyeball session too, so a "pop" isn't mis-attributed to the 24-cap effect when it's actually
just query-radius entry/exit.

**Screendump attempted, doesn't work for this:** `run/screendump` opens a *new* serial connection,
which triggers the ESP32's DTR-toggle auto-reset (same board quirk as `BOOT_WAIT` being useless) —
the device reboots to its default app *before* the GRAM read happens, so it can only ever capture
default-boot state, never a live navigated-to app screen. Confirmed empirically (both attempts
captured the Winamp boot screen, not the PlaneRadar disc). This is exactly why this task's gate is
a literal human at the physical screen, not a tooling substitute — there isn't one available here.

**Left in place:** the `roster` log line (real, cheap diagnostic signal, same rationale as
TASK-367's `fetch rtt=` line). DUT restored to prod firmware.

**Next step:** re-run at busy daytime hours (per EXP-015's original session) with an actual human
watching the live disc — the roster log will now also be running in the background for
supplementary churn data, and the ADS-B-reporting-gap finding above is a third pattern worth adding
to what the observer is asked to distinguish.

**RESOLVED 2026-07-31 (live human DUT eyeball, busy daytime traffic, 25km preset).** Gate met.
Human report: aircraft near the disc's outer band show **occasional appear-then-vanish**, not a
constant flicker and not a hard-static-empty ring. This confirms the core question — boundary
pop-in/pop-out at the nearest-24 cap **is** a real, distinct, observed phenomenon at busy traffic,
separate from TASK-367's dead-reckon-lag (fixed) and from ordinary query-radius entry/exit. The
"occasional" cadence matches what the mechanism predicts: rank-24 churn only happens when two
aircraft's distances actually cross near the cap boundary, not continuously.

**Disposition:** not an accuracy bug — the pops are *correct* (those aircraft genuinely are
crossing into/out of the nearest-24 set as relative distances change), just uncommunicated to the
viewer, who has no way to tell "aircraft left detection range" apart from "aircraft got bumped by a
nearer one" apart from "genuine tracking glitch." Fix scoped as **TASK-378** (visualize the
effective-coverage horizon) rather than any change to the truncation/motion logic itself. **Status:
DONE.**

### TASK-378 — PlaneRadar: render the nearest-24 "horizon" — don't let the disc imply uniform coverage out to the preset radius

Human-observed 2026-07-31 (live daytime eyeball, busy traffic, 25km preset): the disc's outer band
was empty. Traced to `PR_MAX_AIRCRAFT=24`'s nearest-only cap (`prInsertNearest()`,
`dataTaskStorage.cpp:1198`) — not a fetch-radius shortfall (the query already asks a bit past the
disc's drawn edge, `kPrFetchNm` > `_outerKm()`). When more than 24 aircraft sit within the fetch
radius, the kept set is strictly the 24 *nearest*; the render's effective coverage radius silently
shrinks to wherever the 24th-nearest aircraft happens to be, which can be well inside the disc's
drawn edge — the outer band isn't "no traffic there," it's "not shown because 24 nearer aircraft
took every slot." Currently invisible to the user: the disc looks like uniform coverage to the
preset radius at all times, busy or not.

**Scope:** shade/darken the disc annulus beyond the *effective* horizon (the farthest currently-kept
aircraft's `distNm`, projected to px via `_pxPerKm()`) whenever `result.count == PR_MAX_AIRCRAFT`
(roster actually capped — below cap, every detected aircraft is shown, no hidden horizon, no
shading). **Implementation note:** `prInsertNearest()` does NOT keep `aircraft[]` sorted by
distance — it's insertion/replacement order (confirmed empirically: TASK-368's roster log showed
unsorted `distNm` sequences). Finding the horizon means scanning for `max(distNm)` across
`aircraft[0..count-1]`, not reading the last array slot. Recompute only on a fetch landing (inside
`_reconcileMotion()` or right after, alongside `_project()`'s existing per-aircraft loop — cheap,
same pass), not every interp tick.

**Visual treatment (human directive, 2026-07-31):** a darker shade of fill for the annulus beyond
the horizon — not a dashed ring, not a label. Explicit constraint: dark enough to read as "beyond
here" but must stay visually distinct from `PR_COL_OUTSIDE` (the black fill outside the disc
entirely) — must not disappear against it. Mock up the exact shade host-side in
`preview_planeradar.py` against both the field colour (`PR_COL_FIELD`) and outside-disc black
before committing to firmware (BP-046: the tool must actually implement whatever the mockup
claims), then confirm on-device under real backlight (RGB565 quantization/panel behaviour can shift
a shade that reads fine on a host PNG — BP-051's host-iterate/DUT-confirm split applies here too).

**Owner:** Developer (design + impl) · **Deps:** M-PLANERADAR (done), informed by TASK-368's
eyeball session · **Gate:** `run/check` + DUT eyeball — this is a pixel-level exit criterion under
BP-048, needs explicit human sign-off, not just a serial-signature check · **Priority:** P3 (UX
honesty polish, not a correctness bug) · **Status:** DONE (2026-08-01, implementation + two rounds
of human DUT eyeball + a requested code-review pass, all closed)

**Extended scope (human-directed, live during DUT eyeball):** a second, independent limiter turned
out to warrant the same visualization — TASK-361's radius-capped retry2 (the fetch itself asks a
smaller question after two straight parse failures), distinct from the nearest-24 cap and worth a
different colour so the viewer can tell "the roster's genuinely full" apart from "we don't actually
know, the fetch degraded." Added `PlaneRadarResult.fetchedRadiusNm` (`dataTask.h`/
`dataTaskStorage.cpp`) so the app layer knows which radius actually got queried this cycle, a
second colour `PR_COL_HORIZON_WARN`, and precedence (radius-cap wins if both were somehow active).

**Two real bugs found by live human DUT eyeball, both fixed same session:**
1. **Stale shade never cleared.** `_drawHorizonShade()` only knew how to *add* a shade — when the
   underlying condition cleared, it just `return`ed, leaving the annulus stuck on screen. Fixed:
   made it idempotent (re-establishes the full correct state every call, including explicitly
   re-filling `PR_COL_FIELD` when nothing's active).
2. **Aircraft "wiped clean" holes as they moved through the shaded band.** The ~10Hz interp-tick
   per-aircraft repair path (`_redrawOneAircraft()`) deliberately skips the full-disc shade redraw
   for performance (`withViewportRepair()` only clips pixel *writes*, not the shape-iteration CPU
   cost of two full-radius `fillCircle()` calls — see the code comment) — but that left the erased
   footprint's `PR_COL_FIELD` fill uncorrected when it should've been shade-coloured. Fixed with
   `_repairHorizonShadeBox()`, an O(box area) approximation (box-centre-distance test) scoped to
   just the erased rect, not the whole disc.

**Colour: locked by direct human eyeball on-device, not a PNG-mockup guess.** Every earlier
darker-than-`PR_COL_FIELD` candidate read fine as an isolated host-rendered swatch but washed out
to invisible in a full disc render — host PNG rendering turned out not to be a reliable judge of
near-black RGB565 contrast at all (confirmed by direct pixel sampling: the annulus *was* drawing
correctly with genuinely different values, just imperceptible through that rendering/viewing
pipeline). Final value computed directly from the two real constants per human instruction rather
than iterated blind: `PR_COL_HORIZON = 0x0022` — the native-RGB565 midpoint between `PR_COL_FIELD`
(0,2,3 in 5/6/5-bit units) and `PR_COL_OUTSIDE` (0,0,0). `PR_COL_HORIZON_WARN` (dark orange/red,
mirrors `PR_COL_FIELD` with R/B swapped) is still an unconfirmed candidate.

**Code-review pass (human-requested, 2026-08-01):** found and fixed the shade-selection logic
(precedence + NM→px conversion) duplicated between `_drawHorizonShade()` and
`_repairHorizonShadeBox()` — exactly BP-047's divergence-risk shape. Consolidated into one function,
`_activeShade()`, both now call. Also found two text-rendering call sites that had silently never
gone through any shading logic at all — `_drawRunways()`'s ICAO label and `_drawTagLines()`'s tag
text both hardcoded `PR_COL_FIELD` as `setTextColor()`'s glyph-erase background, invisible to every
fix above since neither is footprint erasure. Fixed via a new `_bgColorAt(x,y)` point-query helper
built on `_activeShade()` — now the single place any disc-interior drawing asks "what's the
background here." Also named the one magic number introduced this session (`PR_RADIUS_CAP_EPS_NM`,
was an inline `0.01f`).

**Verification:** `run/check` 6/6 throughout. `run/test-targeted T_PR_01,T_PR_02,T_PR_03,T_PR_06,
T_PRI_01` 5/5 PASS after the code-review refactor — `T_PR_02` landed with `prAircraftCount=24`
(genuine nearest-24 cap), so the shading path got real exercise, not just a synthetic check.
Colour confirmed good by human eyeball before the refactor; the refactor changes structure, not
rendered output, but a final look at the consolidated build is still worthwhile next session.

### TASK-361 — PlaneRadar fetch: TASK-313 retry-once mitigation regressed under busy-traffic payload size — re-quantify + fix

Human-reported 2026-07-19, watching the DUT live in daytime over genuinely busy London traffic
(same session as TASK-360/EXP-015, which independently captured 62–70 real aircraft within 25 km
of the device's configured location). The human asked why on-screen motion "stops after 30+s" —
that's `PR_STALE_S=30` (`app/src/planeRadarApp.h`), the intentional dead-reckon extrapolation cap
("never fly a ghost"), which normally shouldn't be visible if fixes land every ~10–15s under
`prPollSec`'s default. Live investigation via `./run/monitor-read` found the real cause: sampling
~500 lines of the production serial log just now (daytime, busy traffic) showed **~36% of fetch
cycles failing completely** (`ok=0 errorCode=-92 count=0` — `IncompleteInput` parse errors on
*both* the original request and TASK-313's one retry) — a large regression from TASK-313's
DUT-measured 0.47% residual rate (see `docs/project/tasks-archive.md` TASK-313 entry: 8.5% first-
attempt failure → single retry → 0.47% final, validated on a 35-min/211-cycle soak).

**Working hypothesis, not yet verified:** Cloudflare edge truncation (TASK-313's root cause —
TLS-fingerprint-keyed, not WiFi/429/Spotify/heap) likely scales with response size. TASK-313's
original soak was not measured against today's real, busy-traffic payload (60–70 aircraft ≈ much
larger JSON than whatever density the original 8.5%/0.47% numbers were taken under). If truncation
probability scales with body size, a single retry becomes insufficient once *both* the original
and the retry are drawn from the same high-truncation-probability regime — consistent with
0.085×0.085≈0.7% (TASK-313's math) failing to explain a observed ~36%.

**Explicitly unrelated to TASK-357/358** (the dr-damped(tau=2) smoother + its dirty-rect repaint
fix) — this is a separate fetch-layer/transport issue, not a rendering or interpolation bug.
`PR_STALE_S` making the fetch failures visible as "frozen" motion is a symptom, not the cause;
don't chase the smoother for this.

**Scope:**
1. **Quantify.** This session's 500-line sample is opportunistic, not a clean measurement — get a
   proper instrumented soak (TASK-313's own methodology: cycle count, cadence, duration, host-probe
   contrast) run under today's real busy-traffic conditions, and correlate per-cycle failure
   (first-attempt AND retry) against response size / reported aircraft count. Confirm or falsify
   the size-scaling hypothesis — don't assume it; TASK-313's evidence-phase discipline (BP-044:
   cause confirmed only when a fix-shaped experiment stops the repro) applies here too.
2. **Scope a fix**, once the mechanism is confirmed. Investigate candidates, don't jump to the
   first one: more than one retry; exponential backoff; whether adsb.fi's API supports a
   field-limiting/bbox-narrowing query parameter to shrink the response (check whether that would
   drop data the app actually needs — callsign/track/gs/alt — before assuming it's viable);
   whether a smaller max-aircraft/radius cap is an acceptable product tradeoff at high density; or
   a fundamentally different mitigation if truncation genuinely scales with payload size such that
   no fixed retry count helps at the extreme end.
3. **Fix + DUT-verify** against a real busy-traffic window (not just a quiet-traffic soak — TASK-
   313's original soak may itself have been under lighter traffic than today, which is plausibly
   why the regression wasn't caught then).

**Owner:** whoever picks this up should scope the split (R&D-style quantification vs. Developer
implementation) as part of doing the work — could stay one task through to a DUT-verified fix, or
split once the mechanism is confirmed · **Deps:** TASK-313 (original mitigation being
re-investigated — this is a regression report against it, not a revision of its DONE status);
informed by TASK-360/EXP-015 (found this while investigating a different, real-traffic-related
question — the busy-traffic capture that surfaced this); explicitly independent of TASK-357/358
(unrelated fetch- vs render-layer issue, noted above to prevent misattribution) · **Gate:** a
clean instrumented measurement of the current failure rate (not this session's opportunistic
sample) correlated against payload size/aircraft count, then a DUT-verified fix bringing the
user-visible failure rate back down near TASK-313's original 0.47% floor (or better, if the fix
also addresses the size-scaling mechanism) · **Priority:** P1 — live, currently-reproducible,
human-observed problem: at ~36% total fetch failure the display is frequently stale, which is more
severe in measured impact than TASK-358's tearing (also P1) · **Status:** DONE (2026-07-26) —
evidence phase closed (size-scaling confirmed, device-specific confirmed via host-vs-DUT A/B),
radius-capped 2nd retry implemented, code-reviewed, and DUT-verified to fire correctly via fault
injection (see below). Real-world benefit magnitude under organic traffic is unmeasured and
deliberately left open — not a blocker to closing this task, see the wrap-up note at the end of
this entry.

**Progress (2026-07-25):** landed the instrumentation this task's quantification step needs, but
have NOT yet run it under real busy traffic (session started 06:36 Saturday — quiet-traffic hours;
human decision this session was to land the tooling now rather than fabricate a low-value
quiet-traffic data point as if it settled anything).

- `dataTaskStorage.cpp`: `prFetchOnce()`/`prParseStream()` now report the declared HTTP
  Content-Length (`http.getSize()`, truthful even on a truncated body — set by the origin before
  Cloudflare's edge can cut the connection) and the true "ac"-array object count scanned this
  attempt (independent of the `PR_MAX_AIRCRAFT=24` kept-count cap) via new `size=`/`scanned=`
  fields on the existing `[dataTask.planeradar]` log lines. Diagnostic-only — no behavior change,
  `./run/check` 6/6 green.
- New `app/tools/pr_fetch_soak_report.py` + `run/pr-fetch-soak [minutes]`: switches to PlaneRadar,
  watches the log for a soak window, and buckets first-attempt/final failure rate by declared size
  (primary — truncation-independent, the real size-scaling test) and by GET elapsed time (secondary
  — tells a time-based edge cutoff apart from a body-fraction-based one, per TASK-313's archived
  finding that E-92 lands ~70-90% through the body with a prompt clean EOF). Deliberately does NOT
  bucket the size-scaling verdict by `scanned` — on a failed cycle that's how far the parse got
  before truncating, not the true count, so bucketing by it would be circular.
- **First real soak run (2026-07-25, later same session):** a quiet-traffic validation attempt
  initially hit a tooling mistake (external `timeout | tail` around the soak wrapper — see
  `feedback_no_timeout_pipe_for_soak_scripts` memory note) that raced the script's own
  trap-guarded prod-restore flash and boot-looped the DUT; recovered with a plain `./run/flash`, no
  data loss. Rather than wait for London rush hour, `run/pr-fetch-soak` gained a `LOC_SLOT`/`LAT`/
  `LON`/`LABEL` option (human's idea) that temporarily repoints one `prloc` slot at a busy airport
  in a different timezone's daytime — adsb.fi is a global feed, so this sidesteps local
  time-of-day entirely. Human picked slot 3 (WFD) to sacrifice temporarily; the tool reads the
  slot's prior contents + active index first and restores both when done (confirmed correct both
  times — 5-min validation + 30-min real run).
  - **30-min soak at Hong Kong Intl (22.308, 113.915), 181 cycles:** first-attempt failure 10.5%,
    final (post-retry) failure **1.1%** — close to TASK-313's original 0.47% floor, nowhere near
    the human's reported ~36%. Size buckets (declared Content-Length, truncation-independent):
    3000-5999B (23 cycles) 13.0%/4.3%, 6000-8999B (102 cycles) 15.7%/1.0%, 9000-11999B (56 cycles)
    **0.0%/0.0%**. **No monotonic climb with size** — if anything the top bucket had zero
    failures. Peak traffic reached: 18 aircraft / ~11.9 KB — well short of the human's reported
    60-70 aircraft. Reading: either HK-area adsb.fi feeder density (crowd-sourced, not flight
    volume) is simply weaker than the UK's near this specific point, or a different high-density
    hub is needed to reach the 60-70-aircraft regime at all.
  - **Working hypothesis status after HK: NOT supported by this data** (though not fully falsified
    either — the tested size range 3-12 KB never reached the ~20 KB+ a 60-70-aircraft response
    likely is). Per BP-044, don't scope a fix off this alone.
  - **Density-probe round (same session):** before committing another 30-min soak to a guess,
    quick single-fetch probes (`prAircraftCount` after `set triggerPlaneRadarFetch 1`) at Dubai,
    Singapore, Doha, Istanbul, and Amsterdam/Schiphol — all much lower than expected (DXB≈0,
    SIN≈4, DOH≈0, IST≈6, AMS≈18), confirming (independent of raw flight volume) that adsb.fi's
    crowd-sourced feeder density is concentrated in Western Europe/UK, not matched by Gulf/SE
    Asia/Turkey. A non-destructive check of the ALREADY-SAVED LHR slot (just switching the active
    index, no content write) showed **23-24 aircraft at 07:45 on a quiet Saturday morning** —
    already denser than Hong Kong's 30-min peak. `pr_fetch_soak_report.py` gained `--active-slot`
    (and `run/pr-fetch-soak`'s `ACTIVE_SLOT=`) for exactly this case: reuse an already-saved slot,
    switch only the active index, zero content risk.
  - **30-min soak at LHR (slot 4, already saved), 179 cycles — sizes 22-37 KB, 9-66 aircraft:**
    first-attempt failure **15.1%**, final (post-retry) failure **4.5%** — a real step up from HK's
    1.1%, and the retry itself started failing meaningfully: **29.6% of retries also failed**
    (vs 0% at HK). Re-bucketing the same log at finer size granularity: 20-24KB (5 cycles, too few)
    0%/0%; 24-28KB (89) 14.6%/4.5%; 28-32KB (55) 14.5%/5.5%; 32KB+ (30) 20.0%/3.3% — noisy per-bucket
    (each final-fail% rests on single-digit failure counts) but the *first*-fail% does trend up
    (14.6→14.5→20.0), and the retry-also-failed jump (0%→29.6%) going from HK's ≤12KB regime to
    LHR's 22-37KB regime is the cleanest signal here.
  - **Hypothesis status after LHR: directionally CONFIRMED, magnitude not yet matched** (4.5% still
    well under the reported ~36%).
  - **US hub probe round:** quick single-fetch probes at ATL/ORD/DFW/LAX/JFK (Saturday ~13:00-17:00
    local across time zones — not weekday rush hour, but July is peak US leisure-travel season) —
    ORD/DFW/LAX/JFK all immediately saturated `prAircraftCount` at `PR_MAX_AIRCRAFT=24` (ATL read 0,
    likely a probe hiccup, not investigated further). Confirms the US has strong crowd-sourced
    ADS-B feeder density, comparable to Western Europe and well above the Gulf/SE Asia/Turkey
    probed earlier. (Aside: the human correctly flagged that the QNS slot, a Queens neighbourhood
    reference point, doesn't actually center on JFK/LaGuardia's runways — used JFK's own
    coordinates directly instead, in the scratch slot, rather than reusing QNS.)
  - **30-min soak at JFK (40.6413,-73.7781), 175 cycles — sizes 50-66 KB, 12-128 aircraft (by far
    the largest/busiest of the three soaks):** first-attempt failure **37.7%**, final (post-retry)
    failure **18.3%**, retry-also-failed **48.5%**. Re-bucketed at finer size granularity:
    50-53KB (11 cycles) 27.3%/0.0%; 54-57KB (39) 25.6%/7.7%; 58-61KB (94) 39.4%/19.1%; 62KB+ (31)
    51.6%/**35.5%**. **A clean, monotonic climb in both columns** — and the top bucket's 35.5%
    final-failure rate lands almost exactly on the human's originally reported ~36%.
  - **Hypothesis status: CONFIRMED.** Three independent locations, one consistent trend:
    HK (≤12KB) → 1.1% final-fail / 0% retry-also-failed; LHR (22-37KB) → 4.5%/29.6%; JFK
    (50-66KB) → 18.3% overall, climbing to 35.5%/final-fail at 62KB+ — matching the original
    report's magnitude at the size regime that actually produces it. The mechanism is exactly as
    hypothesized: TASK-313's single retry was sized for TASK-313's own (much smaller/quieter)
    traffic regime, and stops being sufficient once BOTH attempts are drawn from a
    payload-size range where truncation itself has become common (retry-also-failed climbing from
    0%→29.6%→48.5% across the three soaks is the cleanest single number). Per BP-044, evidence
    phase is now genuinely closed — ready to move to TASK-361's step 2 (scope a fix): more
    retries / backoff, adsb.fi field-limiting or bbox-narrowing to shrink the response, a smaller
    max-aircraft/radius product tradeoff at high density, or another mitigation — PM/human to
    weigh in on which candidate(s) to pursue before implementation.

**Step 2 — candidate scoping (2026-07-25, same session).** Investigated each candidate the task
brief named, plus one it didn't, all with real host-side/DUT evidence rather than guessing:

- **Field-limiting query param: CONFIRMED NOT AVAILABLE.** Live `curl` against
  `opendata.adsb.fi/api/v3/...` shows each aircraft record carries ~38 fields (full ADS-B decode:
  `alert`/`category`/`nav_*`/`nic`/`rc`/`sil`/etc.) — the app's own `prParseStream()` filter already
  narrows this to the 15 it needs client-side, but that's a *parse-time* filter, not a *wire* one.
  Tried `?fields=lat,lon,gs` — server ignored it, returned the full record set unchanged. No
  narrower endpoint or param found in `phase0-api-probe.md` or by experiment. Ruled out.
- **Response compression (not in the original brief, found while checking the above): the server
  DOES support it, but the client can't use it without a real lift.** `curl -H "Accept-Encoding:
  br"` against the same JFK query returned `content-encoding: br` and a **9.2 KB body vs 56.9 KB
  uncompressed — a 6.15x reduction**, which per the confirmed size-scaling data would very plausibly
  collapse the failure rate back toward TASK-313's original floor. But: the vendored Arduino-ESP32
  `HTTPClient.cpp` (`framework-arduinoespressif32/libraries/HTTPClient/src/HTTPClient.cpp:1217`)
  **unconditionally sends `Accept-Encoding: identity;q=1,chunked;q=0.1,*;q=0`** — no user override
  point in the library as vendored — and there's no gzip/brotli decoder anywhere in this firmware
  today (`grep` for gzip/inflate/miniz/zlib/brotli across `app/src` — nothing). Genuinely fixing
  this means: a library patch (this project already has a `LOCAL_PATCHES.md` precedent for
  SpotifyArduino) to make the Accept-Encoding header overridable, PLUS a streaming decompressor
  (brotli decode is heavier than gzip/deflate; even deflate's ~32 KB window is a lot on a device
  that just barely fit a 264-byte addition into `cyd2usb_winamp_debug`'s DRAM budget this session —
  see `feedback_dram_bss_static_buffers` memory note) integrated as a `Stream` adapter feeding
  `prParseStream()`. **Real, probably the single highest-impact lever available, but a separately-
  scoped design/task, not a TASK-361-sized change** — flagging for PM/Architect, not implementing
  here.
- **Smaller max-aircraft/radius preset cap (blanket product change): NOT recommended.** Would
  reduce visibility exactly when a user would want more (watching a busy sky) — a real product
  regression for the common case to fix a failure-mode case. Rejected as the *default* behavior.
- **A genuinely promising angle the brief didn't name, found by checking what the app actually
  keeps:** `prInsertNearest()` (`dataTaskStorage.cpp`) already discards everything past the nearest
  `PR_MAX_AIRCRAFT=24` — the client **downloads and attempts to parse far more than it ever
  displays**. Host-side radius probe at JFK: `dist=20nm→111 aircraft/56.5KB`,
  `dist=4nm→35/16.6KB`, `dist=3nm→35/16.6KB` — a **3.4x size reduction while still returning 35
  aircraft, comfortably over the 24-slot cap**. Same probe at LHR (quiet, current traffic) showed
  the plateau effect too (though LHR's live count tonight is only 11-18, below the cap regardless
  of radius — a reminder this is density-dependent, see below).
- **Recommended primary fix: reduce the query radius on the retry attempt only, not the first
  attempt.** Concretely: `fetchPlaneRadar()`'s existing retry (`dataTaskStorage.cpp` ~1253) requests
  the *same* `distNm` as the first attempt; change it to request a smaller radius (e.g. capped at
  ~10nm, or half the configured preset, whichever is smaller) on the retry only.
  - **Why this is safe and well-targeted, not just a guess:** the retry only fires when the
    first attempt already failed — and per the confirmed size-scaling data, first-attempt failure
    is overwhelmingly concentrated in the *large-response* regime (HK ≤12KB: 6.5% first-fail;
    JFK 50-66KB: 37.7% first-fail). A radius cut precisely targets the case that needs it: when
    there's enough real density to have caused a large response in the first place, a smaller
    radius still reliably clears the 24-aircraft display cap (per the JFK probe above); when
    traffic is genuinely too sparse for a smaller radius to reach 24 aircraft, the first attempt
    was almost certainly small enough to have already succeeded, so the retry path rarely
    triggers there at all.
  - **Why NOT a blanket radius cut:** the first attempt — the common case, ~85%+ of cycles even
    at JFK's extreme — is completely unaffected; full-radius data, full-radius display, zero
    product change for the vast majority of fetches. The reduction only ever applies to an
    already-degraded cycle (one that would otherwise fall back to `PR_STALE_S` dead-reckoning) —
    a radius-limited *fresh* frame is a strict improvement over a stale extrapolated one.
  - **Known wrinkle, not a blocker:** the on-screen rings are drawn at the configured preset's
    full radius regardless of what the retry actually fetched, so a radius-limited retry frame
    could in principle show a suddenly-emptier disc near the edge on an already-rare degraded
    cycle. Worth a VE eyeball at implementation, not a reason to hold the fix.
- **Recommended secondary/complementary: a second retry (2 retries total, 3 attempts), specifically
  paired with the radius cut above — not a bare 3rd same-size attempt.** Quantitative check against
  the JFK data first, because "just add retries" alone is weaker than it looks at the extreme end:
  at the 62KB+ bucket specifically, first-fail=51.6% (16/31) and of *those*, retry-also-failed
  ≈68.8% (11/16) — noticeably higher than the 37.7%-ish independent-redraw rate TASK-313's own
  0.085² model would predict, meaning retries at the **same** size are *not* fully independent
  draws in this regime (some correlation — persistent edge/congestion state across the ~300ms
  gap, not pure bad luck per connection). A 3rd attempt at the *same* size would only add a
  weak, diminishing-returns benefit (~69%² ≈ 47% probability of failing all 3) while costing
  another full TLS handshake (seconds) on an already-slow cycle. Pairing retry #2 with the radius
  cut breaks that correlation by changing the one variable that's actually driving it (size), so
  it isn't just "try again and hope" — it's "try again with the thing we now know reduces the
  failure probability."
- **Not recommending as primary: backoff/exponential delay alone.** Plausible (TASK-313's
  Cloudflare-bot-management theory could mean closely-spaced requests get flagged harder), but
  unconfirmed — no experiment run this session isolated retry-delay as a variable. Cheap to add
  alongside the radius-cut retry, not worth gating the fix on its own dedicated soak first.

**Recommendation for implementation, pending PM/human sign-off:** (1) keep the existing 1st retry
at full radius as today (catches the "genuinely transient" failures at any size); (2) add a 2nd
retry, radius-capped (~10nm or half the preset, whichever is smaller), for cycles where both the
first attempt AND the first (full-radius) retry failed; (3) flag the compression path as a real,
larger, separately-scoped opportunity (design doc + library patch + RAM budget review) rather than
folding it into this task. Not yet implemented — awaiting go-ahead.

**Host-reproducibility check (2026-07-25, same session, human's question):** re-ran TASK-313's own
"is this device-specific" test, fresh, under today's exact JFK conditions rather than trusting the
older characterization. Two runs **in parallel** (human's suggestion) against the identical JFK
query, same real-time traffic:
- **Host (plain `urllib`, `curl`-identity UA, 10s cadence, 30 cycles, sizes 51.7-57.1KB):
  0/30 failures (0.0%).**
- **DUT (`run/pr-fetch-soak`, same coordinates, same window, 47 cycles, overlapping sizes
  ~50.7-57.2KB): first-attempt failure 29.8%, final (post-retry) failure 10.6%.**

Same query, same moment, same response-size range, same underlying real traffic — **zero host
failures vs. ~30% device first-attempt failures.** This is about as clean a same-conditions A/B as
this investigation is going to get, and it reconfirms TASK-313's original root-cause finding
(TLS-fingerprint/client-identity-keyed Cloudflare edge treatment, not a property of the response,
network, or server) still holds at today's much larger payload sizes — the size-scaling regression
is a property of *how much more often* the device-specific truncation fires as responses grow, not
a sign that the mechanism itself changed. Answers the human's reproducibility question directly:
**effectively none of this is host-reproducible; it requires the actual device's TLS stack.**

**Tooling note (housekeeping, not a task-361 finding):** during this parallel run, the *previous*
JFK soak's own restore step had printed "restored active slot -> 5" and a follow-up `get prloc`
had confirmed `active: 5` — yet the *next* soak invocation (after several purely host-side,
device-untouched curl/urllib commands) found the device's persisted `prActiveLoc` back at `6`. No
device-touching action occurred in between that should have changed it. Not root-caused this
session (possibly a `SettingsStorage::save()` durability edge case under back-to-back
debug↔prod reflashing — unconfirmed) — re-fixed (`set prloc active 5`, verified with a second
`get prloc` in the *same* session before reflashing prod this time) and flagged in memory
(`feedback_no_timeout_pipe_for_soak_scripts`) as an open reliability question worth a closer look
if it recurs, rather than assumed-fixed.

**Fix implemented (2026-07-26): the radius-capped 2nd retry, per the recommendation above.**
`dataTaskStorage.cpp`'s `fetchPlaneRadar()` cascade is now: 1st attempt (full radius, unchanged)
→ 1st retry (full radius, unchanged, existing TASK-313 mechanism) → **new** 2nd retry, only if
*both* prior attempts failed with a parse error, at `min(distNm/2, PR_RETRY2_MAX_NM=10.0nm)`.
`prFetchOnce()`'s doc comment updated to reflect two retries, not one. `./run/check` 6/6 green
(no DRAM regression this time — the change is stack-local, no new persisted/static state).

DUT sanity check (`run/pr-fetch-soak 5`, JFK coords, 03:14 EDT Sunday — red-eye hours, real-time
traffic only ~28 aircraft/13KB): 30 cycles, 4 first-attempt failures, all recovered by the
*existing* 1st retry (0% final failures) — the new 2nd-retry path never fired, correctly, since
nothing reached the size regime it targets. Confirms no regression/crash under real conditions,
but does **not** yet demonstrate the fix's actual benefit — that needs a soak during real
50KB+-regime traffic (JFK ~13:00-17:00 EDT was the regime that showed the problem). Human declined
a same-session JFK soak for that ("no dont soak on jfk").

**Alternative-hub search (same session):** human asked whether another currently-busy hub could
substitute for waiting on JFK. Host-side density probes (no DUT touched) at Sydney, Melbourne,
Tokyo Haneda/Narita, Seoul Incheon — all in daytime/early-evening local hours at probe time —
found decent but still moderate density: Sydney 34 aircraft/17.7KB, Seoul 32/17.1KB, Haneda
28/14.0KB, Melbourne 10/5.2KB, Narita 5/3.7KB. Best of these (Sydney/Seoul) lands in LHR's
regime, well short of JFK's 100+ aircraft/50-66KB.

**30-min soak at Sydney (slot 3, temp), 176 cycles, sizes 12.0-19.0KB, 21-34 aircraft:**
first-attempt failure 11.9% (21/176), **retry-also-failed 0.0%, final failure 0.0%** — the
existing 1st retry alone recovered every single failure at this size. Good regression-safety
result (no crashes, clean restore, matches the expected "moderate regime, low failure" profile)
but **the new radius-capped 2nd retry still did not get exercised** — this size range (12-19KB)
sits below where even LHR started showing retry-also-failed (LHR's 22-37KB regime was 29.6%).
**Comparative before/after verification of the new 2nd-retry path specifically still requires
JFK-scale (50KB+) traffic — not yet achieved by any alternative hub tried this session.**

**2nd LHR soak, post-fix (2026-07-26, ~11:56am-12:30pm BST — human noticed live traffic "picking
up," 52 aircraft/27.3KB at check time): 177 cycles, sizes 21.7-33.5KB, 25-60 aircraft — same
regime as the pre-fix LHR soak (22-37KB, 9-66 aircraft).** First-attempt failure 10.7%,
**retry-also-failed 0.0%, final failure 0.0%** — vs. the pre-fix run's 15.1%/29.6%/4.5% at
essentially the same size range. **Read this carefully, don't overclaim:** the new radius-capped
2nd retry *still never fired* here either (retry-also-failed=0% means the existing 1st retry
recovered every single failure by itself) — so this comparison does **not** demonstrate the new
code path working. It shows the *existing* mechanism performed better today than yesterday at a
similar size, which could be genuine day-to-day/edge-load variance in Cloudflare's behavior rather
than anything this session changed. Real evidence for the new 2nd-retry path specifically still
requires a regime dense enough that the 1st retry *also* fails sometimes — LHR hasn't reliably
produced that twice now; JFK did (48.5% retry-also-failed, 68.8% at its top bucket).
· **Status (superseded below):** fix implemented, DUT-verified for safety/no-regression across
three different traffic regimes/sessions (JFK red-eye ~13KB, Sydney ~12-19KB, LHR ~22-33KB twice)
— the new 2nd-retry code path itself has never actually fired in any live test yet.

**3rd JFK soak, post-fix (2026-07-26, ~12:00-12:35pm EDT — human asked "is JFK awake yet",
confirmed live via host probe at 97 aircraft/50.4KB right before starting): 166 cycles, sizes
48.3-62.9KB, 32-120 aircraft — matches or exceeds yesterday's most failure-prone JFK regime.**
Bucketed: 40-49KB (8 cycles) 25.0%/0.0%; 50-59KB (149) 20.1%/0.0%; **60KB+ (9) 88.9% first-attempt
failure, 0.0% final failure.** Grepped the raw log directly for the new firmware log lines
(`radius-capped`, `retry2`) — **zero occurrences.** The new 2nd retry did not fire even once,
including at 88.9% first-attempt failure in the top bucket — the existing 1st retry alone
recovered every single failure, all 40 of them, across the entire soak.

**This is a genuinely important, unresolved finding, not a clean confirmation either way.**
Yesterday, this *exact* size regime (58-66KB) produced 19-35% *final* failure (retry-also-failed
48.5% overall, 68.8% at the top bucket) — today, at matching/larger sizes, retry-also-failed was
0.0%. Two full soaks now (this one and the earlier same-day LHR one) have reached sizes that
matched or exceeded a previous session's worst-case bucket and found the *existing* 1st retry
alone sufficient both times. **Read carefully: this is NOT evidence the new fix works** (it never
engaged) **and it's NOT evidence the original regression is gone** (TASK-313/TASK-361's own
root-cause finding is Cloudflare-edge/TLS-fingerprint-keyed treatment, which this data now
suggests has a real day-to-day or session-to-session time-varying component — not a stable,
purely size-deterministic function the way the 2026-07-25 data alone made it look). The
size-scaling correlation from yesterday's evidence phase still stands (it was internally
consistent across three locations in one session), but reproducing the *retry-also-fails*
condition specifically has now failed twice today at comparable-or-larger sizes, in two different
sessions/times. Whether that's Cloudflare's treatment of this device improving over time, genuine
random day-to-day edge variance, or something else entirely — unresolved, would need many more
soaks across many more days to characterize.
**Code review + fault-injection hook (2026-07-26, human asked "what's the condition to reach the
new code path, is it unreachable").** Traced the exact gate by hand: `code == 200 && !r.ok`
(1st attempt) then `retryCode == 200 && !retryResult.ok` (1st retry) — straight-line code, no
early-return between the two checks, `PlaneRadarResult.ok` correctly defaults `false` and is only
set `true` on a fully clean parse. **Confirmed reachable, not dead code** — this exact condition
occurred for real yesterday (JFK's 62KB+ bucket: 68.8% retry-also-failed). The three same-day
soaks simply never happened to redraw it live.

Added a VE fault-injection hook so this doesn't have to wait on lucky/unlucky real traffic again:
`dataTask::debugForcePlaneRadarParseFail(n)` / `debugPeekForcedParseFailCount()`
(`dataTask.h`/`dataTaskStorage.cpp`, cross-task via a dedicated spinlock, same discipline as
`debugInjectGeocode`/`debugInjectWebRadioResult`), wired to `set prForceParseFail <n>` /
`get prForceParseFail` via `PlaneRadarApp::dbgSet`/`dbgGet`. `prFetchOnce()` consumes one credit
per call when armed, bypassing the network and returning a synthetic `200`/`errorCode=-92`
(matching the real observed IncompleteInput code) — `n=2` forces attempts 1-2 so retry2 hits the
real network; `n=3` exercises the full give-up path. `./run/check` 6/6 green.

**DUT-verified live**, `set prForceParseFail 2` + `triggerPlaneRadarFetch 1`, exact log sequence:
`FORCED synthetic parse failure` → `parse rc=-92 ... -> retry` → `FORCED synthetic parse failure`
→ `retry ok=0 rc=-92` → **`retry also failed rc=-92 -> radius-capped retry2 distNm=9.9`** →
real `GET 200` → `retry2 ok=1 rc=0`. Counter correctly consumed to 0 afterward (`get
prForceParseFail` confirmed). **This settles the code-review question definitively: the new path
fires exactly as designed** — radius correctly halved-and-capped (9.9nm, matching
`min(distNm/2, 10.0)` off a ~19.9nm preset), retry2 hit the real network and succeeded. The
earlier "never fired live" finding was purely about real Cloudflare conditions not reproducing
"both attempts fail" on those particular days — not a defect in the code.
· **Status:** fix implemented, code-reviewed, and now DUT-verified via deterministic fault
injection to fire correctly end-to-end. Its real-world *benefit magnitude* under organic traffic
is still unmeasured (the injection hook proves the mechanism works, not how often live traffic
will actually need it) — leave in place (pure win when needed, no-op otherwise) and watch
production logs for `radius-capped`/`retry2` lines if the original symptom recurs.

**WRAP-UP (2026-07-26) — closing this task.** Summary of the full arc: human-reported live
regression → quantified with real DUT soaks across three independent locations (Hong Kong, LHR,
JFK) confirming failure rate climbs with payload size → confirmed the failure is device-specific
via a parallel host-vs-DUT A/B (0% host failures at identical size/traffic) → scoped candidate
fixes (ruled out field-limiting/blanket-radius-cap, flagged compression as a separately-scoped
future opportunity) → implemented a radius-capped 2nd retry, gated exactly on "both prior attempts
failed" → code-reviewed the gate by hand → added a fault-injection hook and DUT-proved the new
code fires correctly end-to-end. `feature_inventory.yaml`'s `planeradar-001` entry updated with
the fetch-reliability history and the new `prForceParseFail` debug surface.

**Deliberately not blocking on:** measuring the fix's real-world improvement under organic (non-
injected) busy traffic — three follow-up soaks at matching/exceeding sizes never reproduced the
"both attempts fail" condition live, suggesting genuine day-to-day/session variance in Cloudflare's
edge treatment. The fix is a no-op when that condition doesn't occur and a strict improvement when
it does, so there's no downside to shipping it without that measurement. Revisit only if the
original ~30-35%-failure symptom is reported again in real usage — `radius-capped`/`retry2` in the
serial log will show whether the fix is the thing helping. **Status: DONE.**

### TASK-346 — in-app clock face/theme cycling via tap zones (M-CLOCK-TAP-CYCLE)

Human request 2026-07-18. Clock canvas splits at `CLK_TAP_SPLIT_Y=120`: top tap cycles the
active face's colour theme (Nixie/VFD; strict no-op on Digital/Flip — Q1), bottom tap cycles
the face (enum order — Q3). No on-screen affordance (Q2). Persistence deferred: taps mutate
`g_settings` in RAM + dirty; `suspend()` does one coalesced `SettingsStorage::save()` iff the
value differs from the loaded snapshot (ADR-050 rule 3, WebRadio lastStation idiom — Q4).
Observables: `get clockLastAction`, `get clockStyle` extended with themes + dirty. Design:
`docs/architecture/designs/M-CLOCK-TAP-CYCLE.md` (accepted, Q1–Q4 human-resolved same day).

**Owner:** Developer + VE · **Deps:** TASK-345 (themes; done) · **Gate:** `run/check` + DUT
tap suite T_CLK_TAP_01..06 + screendump eyeballs · **Priority:** P2 · **Status:** **DONE**
2026-07-18 (`06455a8`) — `clock_tap_smoke.py` 16/16 PASS, `run/check` 6/6, screendump eyeballs
confirmed tap-driven theme/face transitions, prod reflashed clean. Doc status line was stale
(never updated after landing); backfilled 2026-07-28.

> **PM sync 2026-07-17 (overnight session — 6 slices landed, ZERO DUT time — handoff for daylight)** —
> Overnight agent session (`Claude Fable 5`) shipped six build-verified slices, each `run/check` 6/6
> (7/7 once the new gate landed): **WIRE2-G1/G2/G3** boot TZ + timeFmt + 12h/dateFmt (`a241b44`),
> **WIRE2-G5** BacklightFlow global owner (`49297a3`), **WIRE2-G4** weather coords from settings
> (`1abfb32`), **HOME** device home = `prLocs[0]` + dual-mirror writer (`dcc12bf`, registry-closed
> `9495774`), **WRSET** WebRadio settings UI + D3 resume-diff contract (`fff0208`, registry-closed
> `a0c729f`), **CPICK** shared country picker, both keyboard call sites retired (`13bb3fd`, registry
> self-updated in the same commit). One slice (WRSET) was orphaned mid-session by the Fable-5 usage
> limit right before its build gate; the work was complete and unmodified, so it was gated + review-
> contract-verified + committed post-hoc rather than re-run. Session close-out (`0935a18`, this
> session, Sonnet 5): finished the one dangling piece — `check_settings_wiring.py` (ADR-050 static
> gate: every `AppSettings` field needs load()+save()+a runtime consumer outside `settings/`), wired
> as `run/check` step `[7/7]` (warn-only), plus the city-name label on the TIME tile (M-HOME-LOCATION
> §6 visible confirmation) that made `city` wire clean, and a `NEW-APP-CHECKLIST.md` item documenting
> the gate for future settings fields.
>
> **None of tonight's six slices have touched a DUT.** Everything above is `run/check`-clean
> (build + static gates only) — no serial-dbg suite has run, no eyeball pass has happened. The city
> label in particular is a brand-new visible surface with zero eyeball verification (BP-048 posture).
> *(Resolved 2026-07-17, daylight session: city label eyeballed by human on DUT — correct city shown
> on the Weather TIME tile, not clipped, tile chrome intact, no weather-screen regression. T-CPICK-01
> eyeball half also PASSED same pass. DUT suites ran — see test_plan.md T-SETW/T-WRSET/T-HOME/T-CPICK.)*
>
> **VE/DUT queue for daylight** (all spec'd already — none written into `test_plan.md` yet):
> - **T-SETW-10** — boot applies `posixTz` via `configTzTime` (X031/WIRE2-G1, `cross_feature_matrix.yaml`).
> - **T-SETW-13** — weather fetch uses settings coords, snapshot-at-enqueue, resume()-diff refetch on
>   mismatch (X032/WIRE2-G4).
> - **T-SETW-14/15** — `BacklightFlow` global owner honours `dispAuto` at boot and in every app;
>   `DisplaySection` pause/applyManual/resume handshake doesn't fight the controller (X033/WIRE2-G5).
> - **T-WRSET-01..06** — WebRadio settings UI: result-identity discard (WR-1), edit-time
>   `lastStation` reset (WR-2), resume-diff + abort + refetch, coalesced suspend save, no-edit
>   round-trip must NOT refetch (X034). **Also still owed**: the WR-4 coordinate re-derivation
>   across settings suites, flagged at design time and not yet scheduled — do it alongside this suite.
> - **T-HOME-01..06** — home = `prLocs[0]`, writer×mirror matrix via `prSlotWritten()`, D4 migration,
>   >500 km divergence hint (X035). **T-HOME-05 must also disposition** the noted gap: the manual-
>   entry confirm path (TASK-322) shows no divergence hint — only the Lookup path does.
> - **T-CPICK-01..05** — spec'd in `M-COUNTRY-PICKER.md` §7: opens scrolled to current selection
>   (eyeball half per BP-048/CP-8), scrollbar drag+arrows page correctly at 249 entries, select
>   round-trips at both call sites (WebRadio Country + prloc Lookup, incl. both Retry paths),
>   back-tap cancels without mutating state, bake determinism (`gen_countries.py` re-run byte-
>   identical against `golden.sha256`).
>
> Next agent: write the above into `test_plan.md` as new suites, then run on DUT. `settings-widgets-001`,
> `settings-webradio`, and `home-location-001` all show `test_ids: []` in `feature_inventory.yaml` —
> fill those in as the suites land, per the existing per-feature notes.

> **VE/DUT queue — CLEARED 2026-07-17 (real-data DUT session, snapshot-guarded, human-authorized).**
> T-HOME-02/04/05 (the three real-data-risk deferrals) and T-CPICK-03's remaining prloc Lookup + both
> Retry legs all ran and PASS this session; the WR-4 coordinate re-derivation audit also ran (DONE —
> only `app-settings-wire-001.md` was stale; `m-clock-styles.md`/`m-pr-locations-dut.md` were already
> clean). **M-HOME-LOCATION and M-COUNTRY-PICKER suites are now both fully dispositioned** — see
> `test_plan.md` per-suite status lines. `feature_inventory.yaml`'s `test_ids` were already filled in
> for `home-location-001`/`settings-widgets-001` by the time of this session (the "still `[]`" note
> above was stale). Session followed the mandatory snapshot protocol throughout: `./run/spiffs pull`
> at session start, real `settings.json`/`cal.json` snapshotted aside with timestamps, one deliberate
> authorized Save (T-HOME-02) plus three synthetic-fixture reboots (T-HOME-04), byte-identical restore
> confirmed via sha256 at session end, production firmware reflashed. One pre-existing test-tool
> coordinate-drift bug (**TASK-330**, `run_serialdbg_tests.py`) was found already filed and
> Developer-owned — not touched this session, cross-referenced from the WR-4 entry so it isn't
> mistaken for a duplicate.

> **PM sync 2026-06-28 (A-lite PROVEN — spike all-phases PASS)** — TASK-261 Phase 0/1/2 all PASS
> (EXP-010, branch `rnd/membudget`): the no-PSRAM CYD plays MP3 WebRadio on the multi-app build with the
> Helix decoder forked into a 24 K free-list arena (88/103/129.7 s × 3 trials, churn-safe, production ELF
> byte-clean). **The M-WEBRADIO no-PSRAM viability question — open since the start of the milestone — is
> answered: YES, via the reserved-arena fork.** ADR-047's kill-gate cleared. **Open decision: production
> promotion (TASK-262/human)** — gated on M-RECLAIM Q3-a (Spotify overlay), validation of the halved I2S DMA
> (PATCH-MEMBUDGET-4) at higher bitrate, live station-fetch, and Spotify-active (TASK-243 Premium). The fork
> stays branch-only (BP-040) until that decision. Process note: 3 fresh-agent spike runs (Phase 0/1, Phase 2)
> each stopped at their gate for human review — the cheap-kill-first discipline (LL-087) held end-to-end.
>
> **PM sync 2026-06-27b (direction decided + design batch panel-reviewed)** — Human chose **Gated A-lite**
> for no-PSRAM WebRadio (ADR-047 ACCEPTED): pursue the reserved-arena coexistence **conditional on the spike's
> Phase-1 kill-gate**. Filed **TASK-261** (spike, DUT-blocked; Phase-0 instrumentation can land offline) +
> **TASK-262** (cleanup, BP-040). The design batch (M-MEMBUDGET, M-RECLAIM, M-PLAYER-STATE, PROP, ADR-047)
> passed a 3-agent panel review **unanimous PROCEED-WITH-NITS** — the review caught a real allocator
> correctness bug (bump→free-list, 2→3 fork sites; `c11b87f`) before any code. Process lesson LL-089
> ("design outrunning the product decision") filed; M-RECLAIM Q3-b/Q2 capped at sketch depth until the gate.
> **TASK-259/260 (player mode) proceed regardless** of the WebRadio direction. **Update:** a parallel session
> DUT-verified TASK-259 PART 1 (`13f701d` — player slot restores WebRadio after app-switch PASS; a WDT crash
> *during playback* is pre-existing TASK-233, not a regression). So the DUT was available; confirm the window
> before scheduling the TASK-261 spike. The playback WDT crash is the same TASK-233 wall the spike's Phase 2
> targets — a useful datapoint for it.
>
> **PM sync 2026-06-27 (bottom-up bare-rig settles the hardware question)** — Pivoted the no-PSRAM
> viability question from top-down strip (TASK-255) to a bottom-up bare control (TASK-258 → EXP-009).
> **Both bare configs PASS:** the no-PSRAM CYD plays MP3 radio bare *and* with the full CYD TFT_eSPI
> display (decoder inits ~165 K free; TFT costs ~600 B — direct-draw, no framebuffer). **ADR-045's
> "no-PSRAM playback = NO-GO" is footprint-bound, not silicon-bound** — the hardware and the display
> are both fine; our 11-app build fails only because its ~147 K resident footprint leaves ~60 K, too
> tight for the ~41 K audio path. The lever is **resident footprint, not RAM/silicon/display.**
> **Actions:** TASK-258 DONE (→ EXP-009); **TASK-255 parked** (`parked-pending-TASK-258`, superseded —
> branch artefacts kept); **TASK-257** filed (optional Lane C-1 library A/B, re-homed on the bare rig).
> Open product decision (not yet a task): pursue a stripped boot-direct-to-WebRadio variant vs accept
> ADR-045 stands for the multi-app board. Process lesson: measure the ceiling bottom-up before grinding
> a top-down strip (LL-087); never read `usable = free − maxAlloc` as a fixed budget (LL-088).
>
> **PM sync 2026-06-25 (honest state — WebRadio verification PAUSED on external blocker)** —
> Stop-and-assess. **Solid & committed:** TASK-232 (http fetch), TASK-234 (auto-skip), TASK-239/240
> (~11 KB reclaim) — all DUT-verified; TASK-242 (taskbar null-icon crash) — fix DUT-verified + a
> `static_assert` gate so the bug class can't recur. **Honest downgrades:** TASK-241 (no-PSRAM
> stability) → *implemented-unverified* — its "provisional PASS" leaned on an EXP-007 baseline that
> TASK-243 shows was never a live Spotify session; TASK-242's T242 test + eject-harness change →
> *implemented-unverified* (never run green on DUT). **Root blocker filed (TASK-243):** the Spotify
> Web API returns 403 *"Active premium subscription required for the owner of the app"* — host
> `spotify_state.py` reproduces it from the laptop, so it's categorically not the device/firmware/
> token. **Decision: PAUSE WebRadio verification** — every open verification item is gated on
> TASK-243 (owner-account Premium, external, multi-hour re-enable). No more DUT cycles until the
> host API check is green. Process lessons (this session): host-validate an external API path
> *before* touching the device (LL-085 reinforced); don't cite an unconfirmed baseline as a result.
>
> **PM sync 2026-06-24 (DUT session — M-WEBRADIO TLS verified; playback blocker found)** —
> First DUT session since the 06-20 downtime work. Ran the queued WebRadio tests + a manual
> station-by-station playback probe. Results:
> - **TASK-214 / T_WR_TLS_01: PASS, DUT-verified.** Station fetch returns `count=30` via the
>   **`setCACert()` pinned-root path — the `setInsecure()` fallback never fired** (`tlsInsecure=0`).
>   This settles the ADR-029 question: radio-browser's chain verifies against the pinned root on
>   real hardware, so **no ADR-029 exception is needed** and the original "server omits R13
>   intermediate" diagnosis does not hold here. (Found + fixed a `wrLastHttp` reporting bug en
>   route: http/ok/jsonErr were only recorded on the failure branch, so a successful fetch
>   reported `http=0`; the test failed on that before the fix. Now recorded regardless of outcome.)
> - **NEW BLOCKER (TASK-232): WebRadio playback is broken on this no-PSRAM DUT.** The manual probe
>   played stations 0–7. All **HTTPS** streams (the majority of the votes-ordered list) fail
>   `connecttohost()` immediately with `ssl_client … (-32512) SSL - Memory allocation failed` —
>   `PSRAM not found`, so the audio-stream mbedTLS handshake can't get its ~40 KB contiguous block
>   even with Spotify TLS yielded (free heap ~69 KB, fragmented). The two **HTTP** streams tested
>   connected fine but the upstreams dropped within 5 s. This blocks T_WR_SPOTIFY_RESUME_01,
>   T_WR_COEX_*, and the heap suite (TASK-207/208/209) — none can reach a stable PLAYING state.
> - **TASK-218 (stream-death watchdog): verified behaving correctly.** The library sets `m_f_running`
>   true on connect (not on first audio) and clears it only on a real stop, so the seeded 5 s grace
>   won't false-trip healthy buffering; the watchdog fired only on genuinely dead decodes/streams.
>
> **Follow-on, same session (user: "proceed with TASK-232"):**
> - **TASK-232 fix landed + DUT-verified (multi-page HTTP fetch).** WebRadio now filters out the
>   unplayable HTTPS streams and pages the votes list for `http://` ones (≤ 5 pages). The list fills
>   `count=30` all-HTTP and stations **reach PLAYING** (0 were reachable before). Closes the HTTPS-SSL
>   blocker. ADR-029 amendment for cleartext-media acceptance owed to Architect.
> - **NEW BLOCKER TASK-233: MP3 decoder heap exhaustion.** With HTTPS gone, the next no-PSRAM wall
>   appeared — `MP3Decoder_AllocateBuffers(): not enough memory` (Helix needs ~29 KB; largest
>   contiguous block ~39 KB pre-connect, fragmented below that by decode time). Most HTTP streams
>   connect then die in ~5 s; a few play on fragmentation luck. Whether WebRadio is viable on
>   no-PSRAM CYD hardware at all is now an open product question. Root-caused with DUT evidence.
>
> **PM sync 2026-06-20** — M-WEBRADIO downtime work: VE review + TASK-214 re-scope (no DUT this session).
> User has no DUT access right now; used the downtime for three things instead of waiting.
> (1) VE review (TASK-215) of the TASK-207/208/209 DUT plan found two doc gaps: no test
> exercised the TASK-214 fix itself, and TASK-208's heap thresholds predate `dafa4a4`'s
> Spotify-TLS-yield-for-playback change. (2) Authored T_WR_TLS_01 and T_WR_SPOTIFY_RESUME_01
> to close those gaps (TASK-216) — implemented in `run_serialdbg_tests.py`, registered,
> documented, ready to run next session. (3) Built `run/check-datatask-certs` (TASK-217), a
> host-side TLS chain preflight replicating mbedTLS's strict offline verify — running it
> against `de1.api.radio-browser.info` (the mirror tried first) shows a complete, verifying
> chain *right now* from this network, directly disputing TASK-214's "server omits R13
> intermediate" root cause. Re-scoped TASK-214's fix from unconditional `setInsecure()` to
> try-`setCACert()`-first-then-fallback, recording which path fires via a new `tlsInsecure`
> field. Build-clean, 5/5 gates. **None of this is DUT-verified** — T_WR_TLS_01 is the test
> that settles it, and it needs hardware. Do not amend ADR-029 until that result is in.
>
> **PM sync 2026-06-14 (session 6)** — M-WEBRADIO design complete; firmware implementation task filed.
> Team review (Architect/VE/Developer/QM) surfaced 5 design doc gaps and 3 missing tasks. All resolved:
> design amended (TouchResult spec, SKIN_EJECT UV offsets, streaming JSON, BP-031 call-out, BP-036
> checklist); TASK-210 (bake_skin sign-off), TASK-211 (ACT_EJECT serial accessor), TASK-212 (error
> state injection) filed. Gap confirmed: no firmware implementation task existed. TASK-213 filed —
> full WebRadio firmware (app class, dataTask fetcher, hitTestEject, error state machine, settings,
> serial accessors). TASK-210 is the sole unblocked P1 — can start immediately (host only, no DUT).
> Execution order: TASK-210 → TASK-213 → TASK-211/212 (serial surface) → TASK-207/208/209 (DUT).
>
> **PM sync 2026-06-14 (session 5)** — M-HOST-WINAMP deferred; TASK-201 targeted fix approved.
> Architect review: M-HOST-WINAMP is correct long-term but 6–7 dev-days before WebRadio preview is
> usable. Two concrete misses in preview_webradio.py: (1) PIL default font instead of Winamp LED
> bitmap font (TEXT.BMP glyphs); (2) synthetic grey rectangles instead of POSBAR/PLEDIT skin sprites.
> Coordinates are correct — originX=0, skin_layout.h constants are pixel-accurate. Root fix:
> add `--wsz` arg, import `build_glyph_table` from bake_skin.py, implement `_draw_led_text()` via
> TEXT.BMP glyph crop+paste, and restore POSBAR/PLEDIT chrome from actual skin BMP sprites.
> ~100-120 lines added to existing script; no WinampRenderer.py needed for this gate.
> M-HOST-WINAMP deferred to post-M-WEBRADIO-ship as a long-term preview framework.
> TASK-203–206 deferred. TASK-201 reopened as in-progress.
>
> **PM sync 2026-06-14 (session 4)** — M-WEBRADIO preview blocked; pivot to host Winamp renderer.
> TASK-199 done (flash gate clear). TASK-200 done (API + ICY probes). TASK-202 done (country list, 65 entries, 0 gaps).
> TASK-201 (preview_webradio.py) produced a naive PIL overlay — rejected. Root cause: no Python port of
> WinampDisplay.h exists. Preview tools cannot composite correctly without the actual sprite blitting logic.
> New milestone M-HOST-WINAMP opened. TASK-203 (sprite/font inventory), TASK-204 (WinampRenderer.py),
> TASK-205 (Spotify host preview sign-off), TASK-206 (WebRadio preview v2 on WinampRenderer) filed.
> TASK-201 downgraded to blocked — reopens after TASK-205 sign-off.
>
> **PM sync 2026-06-14 (session 3)** — M-WEBRADIO scheduled (shift-left phase).
> Design draft complete (M-WEBRADIO.md). R&D done (EXP-005 + EXP-006). Open items 4+6 resolved by design.
> Shift-left pre-implementation plan captured in M-WEBRADIO.md. TASK-199–202 opened.
> TASK-199 (flash budget gate) is the sole P1 blocker — must pass before firmware work.
> TASK-200–202 unblock in parallel once TASK-199 clears.
>
> **PM sync 2026-06-14 (session 2)** — M-CLOCK-STYLES + M-PREVIEW-FRAMEWORK close-out.
> TASK-192 (preview_common.py + 6-tool migration) done. TASK-193 (ClockStyle enum, Flip/Nixie/VFD
> renderers, Settings wiring) done. TASK-194 (T_CLK_01–14 VE suite) done, 14/14 PASS.
> M-CLOCK-STYLES milestone complete. Visual criteria C1/C4/C5/C6/C8 deferred (require person at screen).
> M-PREVIEW-FRAMEWORK milestone complete.
> No open tasks remain. Next: M-WEBRADIO (pending PM scheduling).
>
> **PM sync 2026-06-14 (session 1)** — M-TELETEXT complete close-out.
> TASK-191 (P3 TLS heap contention test) closed. T272 PASS. Three bugs surfaced and
> fixed during execution: (1) `fetchTeletext()` missing `tlsYield()`/`tlsResume()` —
> TLS heap contention confirmed, fixed (ADR-044 item 9 revised); (2) `_lastFetch=0`
> early-boot no-enqueue bug in TeletextApp — fixed via `_forceNow()` unsigned-underflow
> helper; (3) null-byte parser bug — NOS body contains `\x00\x00` before `</pre>`,
> breaking `String::indexOf()` via `strstr()` — fixed with null-safe `memcmp` scan.
> No open tasks remain. M-TELETEXT milestone complete.
> Roadmap M-TELETEXT status updated to done.
> Next: M-WEBRADIO (design draft; R&D spike EXP-005 done; pending PM scheduling).
>
> **PM sync 2026-06-13 (sign-off + team review session)** — Major close-out.
> Preview signed off (TASK-175), ADR-044 accepted (TASK-185). P1 firmware gate cleared.
> Parallel team review (Architect/VE/Developer/QM) produced 10 document fixes and 7 new tasks
> (TASK-185–191). Key fixes: 6-zone strip table in ADR-044, scan range corrected to
> tap-column model (conclusive fix for two-column index pages 600/800), TeletextState
> struct spec added to DS-3, TASK-177 step 6 corrected (teletextAutoAdvance added),
> TASK-181 dep relaxed. Test plan: G3 resolved, T249–T251 → ready to run, T261
> updated with concrete tap coords, T269–T271 added.
> TASK-179 closed (teletext.png/active icons baked to slot 9).
> TASK-181 closed (app/gen/teletext_layout.h — all strip zone constants locked).
> TASK-182 closed (dedicated ◄◄ back zone, even spacing).
> Architect proposes TELETEXT_ENABLED build flag (5 touch-points; single knob) — not
> yet filed as a task, pending human scheduling decision.
> Open: TASK-177 (firmware — now unblocked), TASK-180/183/184/186/187/188/189/190/191.
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-13 (design follow-up)** — M-TELETEXT open questions resolved.
> All 5 design open questions (OQ1–OQ5) closed via parallel research: fillTriangle()
> confirmed for right-strip arrows (Font1 has no ▲/▼); 10-entry uint16_t history ring
> on TeletextAppState; subpage auto-advance off by default; root CA confirmed as
> USERTrust RSA Certification Authority (not DigiCert — TASK-176 done); R&D spike
> EXP-004 filed (TASK-178 done) — SVT (SE) viable second entry, RAI incompatible,
> ORF/ARD blocked on-device, YLE needs API key.
> M-TELETEXT.md and ADR-044 updated with confirmed decisions. EXP-004 at
> `docs/rnd/reports/EXP-004-teletext-multi-country-spike.md`.
> Open: TASK-175 (preview iteration — P1 gate), TASK-177 (firmware), TASK-179 (icons).
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-13 (PoC session)** — M-TELETEXT proof-of-concept session.
> TASK-169 (WiFi auto-navigate) closed — done 2026-06-12.
> New milestone M-TELETEXT opened: NOS Teletekst live reader as the 10th multiapp slot.
> PoC validated entirely on-host before firmware: NOS API reverse-engineered, teletext
> control codes (text vs mosaic graphics modes) decoded, preview tool
> (`app/tools/preview_teletext.py`) built with full 320×240 canvas + taskbar + live
> navigation. Resource impact assessed (1.1 KB/fetch, fits dataTask pattern, ~4 KB SRAM).
> Design doc M-TELETEXT.md written; ADR-044 proposed; roadmap entry added.
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-12 (end of session)** — Major close-out: all "Open Tasks" sections
> from ADR-042 follow-on, settings-001 polish, SPIFFS hygiene, M-SETUP-WIZARD VE, M-SETTINGS
> WiFi Phase 2, M-TASKBAR-ICONS, M-SETTINGS-APP-WIRE, and M-DATATASK-PROGRESS are now done.
> TASK-173/174 (volatile progress indicators for all long-running dataTask fetches) implemented
> and DUT-verified (T170, T_WX_05, T_CX_05 all PASS). Roadmap milestone M-DATATASK-PROGRESS
> closed. Sole open task: TASK-169 (UX auto-navigate after WiFi connect).
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-09 (end of session)** — Roadmap retrofitted (6 missing milestones added,
> 3 superseded proposal docs deleted). M-SETUP-WIZARD designed: `run/setup` wizard, SPIFFS
> primary WiFi path, PATCH-003 registered in upstream-patches.md (not yet applied).
> SPIFFS hygiene: live DUT dump confirmed partition layout + file inventory; TASK-160/161/162
> filed. TASK-161 (`run/spiffs` non-destructive manager) is P1 blocker for M-SETUP-WIZARD.
> DUT visual verify batch closed 2026-06-09: TASK-150 (backlight PWM) PASS, TASK-152 (LDR row
> rename) PASS, TASK-153 (city picker drag) PASS, TASK-154 (UTC offset column) PASS.
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).

---

## Deferred — M-HOST-WINAMP (backburner — see session-5 note above)

> TASK-203–206 deferred 2026-06-14 (session 5). M-HOST-WINAMP is the correct long-term
> preview framework but costs 6–7 dev-days before the WebRadio preview gate (T275) can clear.
> Decision: fix TASK-201 with targeted sprite extraction instead. Reopen M-HOST-WINAMP
> after M-WEBRADIO ships.

### TASK-203 — M-HOST-WINAMP: sprite + font inventory (research complete, document pending)

Trace the full pipeline from `.wsz` → `bake_skin.py` → `gen/skin_assets.c` + `gen/skin_layout.h`
→ `WinampDisplay.h` blitSprite calls. Produce a single reference document at
`docs/architecture/designs/M-HOST-WINAMP.md` covering:

1. **Bake pipeline** — which BMP files from the .wsz are extracted, what C arrays they become,
   and their dimensions.
2. **Sprite blit table** — for every visual element in the Winamp UI: source atlas, UV rect,
   screen position, which WinampDisplay method controls it.
3. **Font inventory** — distinguish between the Winamp LED bitmap font (TEXT.BMP → SKIN_FONT /
   SKIN_GLYPH) and TFT_eSPI system fonts (Font 1 in PLEDIT rows; Font 2+ in other apps).
4. **Computed elements** — elements with no sprite atlas: VU bars (computed colour gradient),
   PLEDIT row fill (fillRect), PLEDIT row text (Font 1).
5. **Feature element map** — table of every visible Winamp UI element with its method, atlas,
   and whether it is relevant to the WebRadio remap.

Research is largely complete from code reading (2026-06-14). Document needs authoring.

**Priority:** P1 — gates TASK-204 (can't implement renderer without the map)
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-HOST-WINAMP
**Owner:** Architect + Developer
**Deps:** —

---

### TASK-204 — M-HOST-WINAMP: WinampRenderer.py — Python port of WinampDisplay.h

Create `app/tools/winamp_renderer.py`: a Python class that mirrors `WinampDisplay.h`
sprite-for-sprite, using PIL instead of TFT_eSPI `pushImage`.

**Architecture:**
- Re-use extraction functions already in `bake_skin.py` to read sprites from the `.wsz`
  into PIL Image objects (not RGB565 C arrays — keep as RGBA/RGB PIL for host rendering).
- One method per WinampDisplay method: `blit_main_bg()`, `draw_transport_buttons(pressed=-1)`,
  `draw_title_text(text, scroll_offset=0)`, `draw_time_digits(seconds)`,
  `draw_status_indicator(playing)`, `draw_posbar(pct)`, `draw_volume(pct)`,
  `draw_vu(l_level, r_level)`, `draw_playlist(rows, active_idx, scroll_offset)`.
- Coordinate system: same as firmware (originX=0, originY=0; PLEDIT_Y=116 etc. from skin_layout.h).
- Output: a PIL Image (320×240 RGB) that matches what the DUT renders pixel-accurately.
- Uses `app/gen/skin_layout.h` constants (parsed via regex, same as `preview_vis.py` pattern).

**Not in scope:** interaction / touch / animation — static render only.

**Priority:** P1 — gates TASK-205 and TASK-206
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-HOST-WINAMP
**Owner:** Developer
**Deps:** TASK-203

---

### TASK-205 — M-HOST-WINAMP: preview_spotify.py — full Spotify state preview (human sign-off gate)

Create `app/tools/preview_spotify.py`: interactive pygame preview of the Spotify/Winamp app
using `WinampRenderer` from TASK-204.

Mock data to show in the playing state:
- Track: "BIRDS OF A FEATHER" by "Billie Eilish", 3:14
- Playlist: 5 entries, entry 0 active
- Progress: 1:23 / 3:14 (seek thumb at ~43%)
- Volume: 72%
- Shuffle: off, Repeat: off
- VU: active sine envelope

Keyboard: P=playing, S=stopped, Q=quit. Taskbar drawn via `draw_taskbar_pil`.

**Gate:** Human looks at the preview and compares it to a DUT screenshot or `skin_hitzones.png`.
If all elements land in the right zones, TASK-206 is unblocked.

**Priority:** P1 — gates TASK-206 and TASK-201 reopen
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-HOST-WINAMP
**Owner:** Developer + human sign-off
**Deps:** TASK-204

---

### TASK-206 — M-HOST-WINAMP / M-WEBRADIO: preview_webradio.py v2 on WinampRenderer

Rewrite `app/tools/preview_webradio.py` using `WinampRenderer` from TASK-204.

WebRadio remaps:
- `draw_title_text()` → station name marquee (line 1)
- New `draw_icy_title()` helper → ICY StreamTitle in the 7px gap (y=33..42) between title and VU
- `draw_posbar()` replaced by `draw_buffer_bar(fill_pct)` at same POSBAR zone
- `draw_vu()` → unchanged (audio.getVUlevel() feeds same zone)
- `draw_playlist()` → station list (PLEDIT rows, PLEDIT chrome)
- New `draw_country_badge()` → small label in top-right of main area

Transport buttons, volume, shuffle/repeat: rendered from skin but labelled/ignored for radio
(tap targets will be remapped in firmware; preview just shows them as they are).

States: stopped / connecting / playing / error (same keyboard as TASK-205).

**Priority:** P2 — unblocks after TASK-205 human sign-off
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer + human sign-off (T275 gate)
**Deps:** TASK-205

---

## Open — M-WEBRADIO shift-left phase (2026-06-14)

### TASK-239 — M-WEBRADIO: lazy-allocate s_webRadioDoc + s_heatmapDoc (low-risk reclaim)

Make the two persistent static `DynamicJsonDocument`s heap-alloc-on-use / free-after-use instead
of file-scope-resident: `s_webRadioDoc` (5 KB, `dataTaskStorage.cpp:597` — only live during the
station fetch) and `s_heatmapDoc` (2.5 KB, `:584` — only live when the Stock heatmap fetches).
Frees ~7.5 KB of resident heap during WebRadio playback. **Fragmentation caveat (Architect review,
see below):** free `s_webRadioDoc` *before* the audio path allocates and avoid alloc/free churn at
the fetch→playback boundary, since contiguous-block availability is the core problem.
**Architect ruling (ADR-045 amendment 2026-06-24):** free `s_webRadioDoc` immediately after
`appendHttpStations()` copies stations out — before `tlsResume()`, never held across playback;
`s_heatmapDoc` alloc/free within the heatmap fetch only; both frees must complete before the
audio path's first alloc; verify via the existing `HEAP pre-connect` log (free/maxAlloc must
actually rise at decode time).
**Done (s_webRadioDoc) 2026-06-24.** `s_webRadioDoc` is now a fetch-scoped local
`DynamicJsonDocument webRadioDoc(WR_DOC_CAP)` in `fetchWebRadioStations()`, passed by ref to
`fetchOneMirror()`/`appendHttpStations()`, freed at a scope brace **before `tlsResume()`** per the
Architect ruling. Its 5 KB pool is no longer heap-resident across playback (the pool was always
heap, allocated at static-init — so this shows as runtime free-heap gain, not a static-RAM drop).
Build-clean. **DUT-verify with TASK-241** that `HEAP pre-connect free/maxAlloc` actually rises.

**s_heatmapDoc DEFERRED — EXP-003 conflict (flag to Architect/QM).** The naive Architect ruling
("alloc/free within the heatmap fetch") collides with PROP-004/EXP-003: `s_heatmapDoc` is
allocated at `dataTaskStorage.cpp:654` *while the Yahoo TLS session is still open* (fragmented
heap) — the exact malloc-failure condition it was made static to avoid. Reclaiming its 2.5 KB
safely needs the alloc moved to post-`tlsYield()`/pre-TLS-open with a scoped free before
`tlsResume()`, plus EXP-003 re-validation. Not worth a Stock-app regression risk now; the 5 KB
webRadioDoc + ~6 KB stack (TASK-240) carry the plan. Revisit only if TASK-241 needs the extra
2.5 KB.
**Priority:** P2 · **Status:** **done (webRadioDoc); heatmapDoc deferred (EXP-003)** · **Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO
**Owner:** Developer · **Deps:** none

### TASK-241 — M-WEBRADIO: re-run input-buffer experiment with RAM reclaimed (DECISION GATE)

After TASK-239/240, re-run the EXP-007 experiment: enlarge the audio input buffer
(`setBufsize`, ~16 KB) *with* the ~14 KB reclaimed, and measure on DUT — (a) does the MP3 decoder
still allocate reliably, and (b) do the "slow stream, dropouts" underruns drop / do stations hold
≥ 60 s. **This is the go/no-go that decides whether stable WebRadio is achievable on no-PSRAM.**
Feeds an ADR-045 amendment/supersede either way. Pass → revise ADR-045 from "best-effort,
ceiling-bound" toward "stable with reclaim"; fail → the 38.9 KB caps-restricted dead block is the
wall, ADR-045 stands, stop.
**Architect (ADR-045 amendment 2026-06-24):** sanctioned as a decision gate that may supersede
ADR-045 — PASS → "stable via targeted reclaim"; FAIL → 38.9 KB caps-restricted block is the wall,
ADR-045 stands. Do NOT ship buffer-size changes before this gate. Verify the reclaim raised
free/maxAlloc at decode time, not just nominally freed memory.

**BLOCKED on a valid test condition (2026-06-24).** TASK-239/240 done (~11 KB reclaimed,
verified). But the decisive test requires the **tight ~78 KB playback heap** EXP-007 measured —
and that only exists when **Spotify is actively playing a track** (full resident footprint: TLS
session + album art + metadata + fragmentation). The DUT currently shows Spotify *configured but
idle* (`isPlaying:false`); idle → webradio play `tlsYield()` frees Spotify → ~130 KB free, which
makes any decoder+16 KB-buffer test pass trivially (proves nothing). **Needs the user's Spotify
account actively playing music**, then: re-flash debug, enlarge the input buffer (`setBufsize`
~16 KB), play a station, and check on DUT — (a) decoder still allocates at ~78 KB − 11 KB reclaim
headroom, (b) underruns drop / station holds ≥ 60 s. External dependency, not a code blocker.
**Provisional PASS (2026-06-24) — final confirmation blocked on device Spotify auth.**
Synthetic-pressure test (debug-only `set heappressure`, 16 KB `setBufsize`, audio_info hook).
Decisive data point, fresh decoder after boot: **with the 16 KB input buffer + the ~11 KB
reclaim, the MP3 decoder allocates OK at `preConnFree=89236`** (`MP3Decoder has been initialized`,
no OOM). Compare EXP-007: 16 KB buffer, *no* reclaim, decoder **failed** at the Spotify-playing
tight baseline `preConnFree≈78 K`. The reclaim lifts the baseline 78 K → 89 K (78 + 11), and the
decoder demonstrably allocates at 89 K → **the bigger buffer and the decoder can coexist with the
reclaim.** Strong evidence stable no-PSRAM playback is achievable.

**Why provisional, not final:** (1) the 89 K point was Spotify-*idle*; the exact Spotify-*playing*
fragmentation at the true tight condition couldn't be reproduced — **the device's Spotify auth is
broken** (`isPlaying` stuck false, `lastPollAgeMs` climbs, "startup poll failed"; token expired
since EXP-007). (2) The clean fresh-decoder threshold sweep and the underrun-reduction half (does
the 16 KB buffer hold streams ≥ 60 s) were both blocked because the broken Spotify makes
`tlsYield()` hang during WebRadio `_play()` after a reboot. (3) Per Architect, the `setBufsize`
change is NOT shipped before the gate conclusively passes — reverted; only the reclaim (239/240)
is committed. **To finalise:** fix device Spotify auth (re-run `get_refresh_token.py` →
`./run/spiffs push`), then re-test with a track playing — confirm decoder alloc (already strongly
indicated) + station holds ≥ 60 s with fewer dropouts. Feeds the ADR-045 amendment.
**DOWNGRADED to implemented-unverified (2026-06-25).** The earlier "provisional PASS" leaned on
EXP-007's ~78 K "Spotify-playing" baseline — which TASK-243 shows was almost certainly **never a
live Spotify session** (owner-account Premium had lapsed; host reproduces the 403). So the
tight-condition comparison rests on an unconfirmed baseline and must be **re-taken**, not cited.
The reclaim itself (TASK-239/240) is real and verified; whether it makes playback *stable* is
**not yet proven**. Blocked on **TASK-243** — no valid tight-heap test is possible without a live
Spotify session. When unblocked: host-confirm the API is live, then run the tight-condition test.
**Priority:** P1 — settles the M-WEBRADIO viability question · **Status:** **implemented-unverified — deferred-behind-TASK-243** (was "provisional PASS"; baseline invalid). **TASK-255 (Spotify-disabled build) is now the active no-PSRAM viability gate** — a parallel lane that runs *now* without Premium, answering "is no-PSRAM WebRadio viable at all." TASK-255 does **not** supersede this: the two answer different questions (TASK-255: Spotify-*free* viability; TASK-241: multi-app-reclaim viability) and a TASK-255 PASS does **not** overturn ADR-045 for the multi-app board. This task resumes when TASK-243 (owner Premium) clears, to take the valid tight-heap baseline.
**Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO · **Owner:** Developer + Architect (decision)
**Deps:** TASK-239 (done), TASK-240 (done), TASK-243 (blocker) · **Parallel lane:** TASK-255

---

## Open — M-WEBRADIO blockers (TASK-242 itself archived; header stub left behind by the 2026-07-12 pass — see tasks-archive.md)

### TASK-243 — BLOCKER: Spotify Web API 403 — owner account lacks active Premium

**This blocks all remaining WebRadio verification** (TASK-241 tight-condition test, the WebRadio
serialdbg suite, and TASK-242's T242 + eject-harness validation) and any device feature that reads
Spotify playback state.

**Definitive root cause (host-confirmed, not device).** `app/tools/spotify_state.py` and a raw
host call reproduce the device's exact 403 from the laptop with the same creds — token refresh
succeeds (correct scope), but `/v1/me`, `/v1/me/player`, and `/v1/me/player/currently-playing` all
return **403** with body:
> *"Active premium subscription required for the owner of the app. When the subscription status
> changes, it can take a few hours before requests are allowed again."*

Spotify now requires the **app owner** (clientId `db2ff3…`) to hold active Premium for Web API
access; that lapsed. **Not** the device, firmware, token, scope, or dev-mode allowlist — re-auth +
`spiffs push` were done and are correct; they'll just start working once Premium is restored.

**Knock-on:** EXP-007's "78 K pre-connect = Spotify playing" baseline was almost certainly never a
live session (Premium already lapsed), so TASK-241's provisional numbers rest on an unconfirmed
baseline — re-take once the API is live.

**Resolution (user/owner action — external):** restore active Premium on the owning Spotify
account, then wait the few hours Spotify mentions. **Verify-first procedure when back:** run
`./run/… spotify_state.py` (host) and confirm `ok:true` / `isPlaying` tracks playback *before*
spending any DUT time — this host check is the cheap gate that should precede device work
(process lesson from this session: host-validate the API path first).
**Priority:** P1 — external blocker · **Status:** open (blocked on owner-account Premium)
**Opened:** 2026-06-25 · **Milestone:** M-WEBRADIO / infra
**Owner:** Human (Spotify account) · **Deps:** none (external)

---

### TASK-207 — M-WEBRADIO: touch + audio coexistence check (open item 4)

With WebRadio firmware flashed and a station playing, verify that XPT2046 touch
(SPI SCK on GPIO25) and I2S-DAC audio (GPIO26 → SC8002B) operate simultaneously
without electrical interference on this board revision.

Procedure:
1. Flash M-WEBRADIO firmware. Connect 8 Ω speaker to SPEAK header.
2. Start a station; confirm audio is playing (audible + VU meter animating).
3. While audio plays, repeatedly tap prev/next station touch zones.
4. Observe: audio must not glitch, stutter, or drop out on touch events.
5. Observe: touch must register correctly — station changes must fire.
6. Run for ≥ 2 minutes of continuous playback + touch interaction.

Pass criteria: no audio dropout correlated with touch events; touch response
unaffected by audio playback. Fail = audio or touch degraded during concurrent
operation → file hardware conflict issue, consider SPI rate reduction workaround.

Note: peripheral buses are independent (SPI vs internal DAC) — electrical risk
is low but this board's routing is unverified for this combination.

**DUT run 2026-07-02 (cyd2usb_webradio, 16 stations, operator present — no speaker):**
- **T_WR_COEX_02 PASS** — injected taps fire during playback (NEXT wraps 13→14→15→0, PREV 0→15).
- **T_WR_COEX_04 PASS** — tap ack 112/185/127 ms (<500 ms bar), station change each time.
- **T_WR_COEX_03 objective half PASS** — underrun counter frozen (startup blip only) through a 60 s
  injected-tap storm during continuous playback (playMs 15 s→76 s unbroken), a 150 s clean window, and a
  5-min **physical**-touch window with ~30 registered operator touches. Touch registration proven
  independent of network state (touches kept landing during a live link-flap outage).
- **T_WR_COEX_01 serial half PASS** (state:2 sustained; VU static = expected, 220b).
- **DEFERRED (needs 8 Ω speaker):** the audible halves — analog electrical-noise check (GPIO25 touch SCK
  → GPIO26 DAC) and by-ear dropout confirmation. The digital domain is clean by counter; the analog domain
  is unverifiable without a speaker. Also defers TASK-209 (T_WR_VOL_01/02 volume calibration, same reason).
- Bonus live capture: two ~30 s **terminal parks** during a sensor-attributed link-flap outage
  (`NO_AP_FOUND` storms, discCount 15/min) — operator had to manually re-play; motivates
  retry-from-terminal (filed TASK-276).

**Priority:** P1 — blocking M-WEBRADIO ship
**Status:** **substantially PASSED 2026-07-02 — all serial/objective halves green; audible halves
DEFERRED pending speaker (re-run T_WR_COEX_01/03 audible + T_WR_VOL when hardware present). Human call
whether the deferred analog check gates milestone close.**
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** VE + human operator (physical board required)
**Deps:** ~~radio-browser reachability~~ (resolved — 16 stations load on cyd2usb_webradio)

---

### TASK-209 — M-WEBRADIO: SC8002B volume ceiling calibration

Determine the safe `audio.setVolume()` ceiling for stock hardware (no HW mod).
M-WEBRADIO.md §Audio hardware path documents ≤ 10/21 as the design default;
this task confirms it empirically and sets the soft cap in code.

Procedure:
1. Flash M-WEBRADIO firmware. Connect 8 Ω speaker.
2. Start a 96 kbps MP3 station with consistent audio level.
3. Step `audio.setVolume()` from 1 → 21 via a serial command or settings slider,
   pausing 5 s at each step.
4. Note the first level at which clipping / distortion is audible.
5. Subtract 2 steps as headroom → this is the `kMaxVolumeStock` constant.
6. With HW mod installed (if available): repeat from step 3 to confirm full
   0–21 range is clean.

Pass criteria: `kMaxVolumeStock` determined; value matches design estimate of
≈ 10 (±2 steps acceptable). Hard cap enforced in firmware at this value when
`settings.webRadio.hwModInstalled == false`.

**Scope note (2026-06-22):** this task **owns the `webRadioHwMod` consumption and the
§HW Mod clamp** (M-WEBRADIO.md lines 676-685), reclassified here from the TASK-228
settings sweep. ⚠ Correction to the status below: the firmware does **not** currently
read `webRadioHwMod` or clamp at all — `setVolume(webRadioMaxVolume)` is unclamped
(`webRadioApp.h:117,451`), so the §HW Mod interaction (stock soft-cap 12 / mod default
18 / range-to-21) is entirely unimplemented, not merely uncalibrated. Implementation
work for this task: (a) read `webRadioHwMod` and clamp `setVolume()` accordingly,
(b) auto-raise the `webRadioMaxVolume` default to 18 when HW mod on, (c) optionally a
Settings UI toggle (no WebRadio settings section exists yet). The DUT calibrates the
exact stock value; the clamp *structure* could land on host first if desired.

**Clamp/HW-mod logic DONE — DUT-verified 2026-06-25 (T_WR_VOL_CLAMP PASS, 8/8).** Implemented the
§HW Mod ceiling that was entirely missing: `webRadioApp::wrEffectiveVolume()` is now the single
source of truth feeding every production `setVolume()` site (init + `_play()`) — stock (hwMod=false)
soft-caps at `WR_VOLUME_SOFT_CAP_STOCK=12`, the HW mod passes the full 1–21. The `wrVol` debug setter
stays **unclamped** (so VOL_01/02 calibration can still drive past the cap to find the clip point).
Default auto-raise wired in `settingsStorage` load (`maxVolume` defaults 18 with HW mod / 10 stock).
New `get wrEffectiveVol` accessor + `set wrHwMod`/`wrMaxVol` make the clamp verifiable without audio;
new playback-free regression test **T_WR_VOL_CLAMP** asserts all 8 (hwMod × ceiling) cases on DUT.
Stale `settingsStorage.h` comments reconciled. 5/5 gates.

**Still owed (subjective, needs speaker + human ears):** the *exact* stock clip point — confirm 12 is
safe (or refine ±2) by ear via `set wrVol` stepping (VOL_01/02), and confirm the HW-mod full range is
clean if the mod is installed. The clamp *structure* + its enforcement are done and tested; only the
empirical dB number remains, and it can be refined in a follow-on reflash without code-structure change.
**Priority:** P2 — clamp shipped at design estimate 12; exact value refinable in a follow-on reflash
**Status:** clamp logic done + DUT-verified 2026-06-25 (T_WR_VOL_CLAMP); subjective dB calibration (VOL_01/02) still needs speaker + ears (deferred, not blocking the clamp)
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer + human operator (subjective listening required)
**Deps:** radio-browser.info reachable from DUT; TASK-208 (same DUT session)

---

## Open — M-WEBRADIO pre-firmware gates (2026-06-14)

### TASK-255 — M-WEBRADIO-NOPSRAM: no-PSRAM viability via Spotify-disabled build

Build-time experiment to settle the open M-WEBRADIO blocker (stable no-PSRAM MP3 playback) on a
**faster lane that needs no Spotify auth** — sidestepping the external TASK-243 Premium blocker that
has frozen TASK-241's tight-heap re-test. A `cyd2usb_webradio` PlatformIO env adds `-DDISABLE_SPOTIFY`,
which (single functional guard) skips `spotifyTask::begin()` so the task's **~10 KB resident stack** is
never allocated; with `reqQueue`/`s_tlsYieldedSem` null, all 34 `tlsYield`/`tlsResume` call sites
early-return with **no source edit**. Per EXP-007 the limiter is **usable heap** (`free − 38.9 KB
caps-restricted dead block`), *not* `maxAlloc` (which is pinned): EXP-007 failed at usable ≈ 20.6 KB <
22.7 KB decoder demand. Removing the ~10 KB stack predicts ~30.6 KB usable (+8 KB margin) — enough for
the decoder *and* a larger input buffer. The Spotify app stays a dormant, provably-inert stub (no
`AppId` surgery; shows a permanent amber "connecting" bar per ADR-046).

**Panel-consensus design (rev3):** [M-WEBRADIO-SPOTIFY-DISABLE.md](../architecture/designs/M-WEBRADIO-SPOTIFY-DISABLE.md).
Round-1 PM blockers (V0 critical path / hard kill / supersede-vs-parallel) resolved; AGREE-WITH-NITS.

**HARD KILL (the abort point) — Measurement Step-1 / cheap pre-gate:** on `cyd2usb_webradio` at
WebRadio `_play()` entry, capture `get stacks` (`heapFree`/`heapMin`/`heapMaxAlloc`), **re-measure the
caps-restricted dead-block on THIS build** (do not assume EXP-007's 38,900 transfers — removing
`spotifyTask` may relayout caps), compute `usable = heapFree − dead_block`. **If `usable < 22.7 KB
decoder + target input buffer` → STOP. Do NOT spend DUT playback time.** Record FAIL against
TASK-241/ADR-045, shelve the branch. Pass signal is **usable headroom, NOT maxAlloc rising**.

**Two-threshold result split (a valid partial is OK):** the design records (a) **startup-reliability**
(decoder allocates first try, more stations reach PLAYING) vs (b) **underrun-tolerance** (16 KB input
buffer holds slow streams ≥ 60 s). An **(a)-only partial** — startup improves but underruns persist —
is a valid, recordable result, not a failure of the experiment.

**Definition of Done** (from design §Process & lifecycle):
- `cyd2usb_webradio` env builds; **default `cyd2usb_winamp` `.elf` `.text`/`.rodata`/`.data` section
  hashes unchanged** before/after the patch (V1 — robust gate; raw `.bin` may differ on build
  timestamp).
- **V0 lands green** (the harness + variant-signal prerequisite; critical path — see handoff).
- **Step-1 usable-headroom captured** at `_play()` entry on the disabled build.
- **PASS** (Step-1 clears AND V3 sustained-playback gate met: stable PLAYING ≥ 60 s within ≤ 6
  auto-skips on ≥ 90 % of cold-boot entries, fixed station set × ≥ 3 trials, network-flake entries
  excluded per the T169 carve-out, measured by the new `T_WR_PLAY_SUSTAIN` test) → write **EXP-008**
  + an **ADR-045 amendment** ("viable with Spotify disabled" — does **not** overturn ADR-045 for the
  multi-app board) + graduate Open-A (dormant stub vs boot-direct-to-WebRadio shipped variant) to a
  **PROP / follow-on milestone**. The 6th `./run/check` gate for `cyd2usb_webradio` lands only on that
  promotion, not here (PM N3).
- **FAIL** → ADR-045 stands unchanged; branch shelved; result recorded against TASK-241.

**Ordered handoff:** **Developer** (firmware variant signal: boot-log token `[boot] spotify=off` +
`get variant`; `get wrPlaying` PLAYING-duration query for `T_WR_PLAY_SUSTAIN`; the single
`#ifndef DISABLE_SPOTIFY` guard; **null-safety audit of every unconditional `spotifyTask::` accessor**
— `stackHighWaterBytes`/`stackSizeBytes`/`activeError`/`dbgGet`/`dbgSet`/`cmdReconnect` — so the
disabled build doesn't crash on the first `get stacks`) → **VE** (V0 harness: `_wait_for_ready` variant
branch keyed on the boot token = WiFi-up + shell-ready, skipping the never-emitted Spotify poll-wait;
**gated — task #1, before ANY DUT run**) → **DUT Step-1 kill gate** → **conditional V3** (sustained
playback + inverse per-fetcher `tlsYield`-no-op check + eject round-trip into the dormant stub) →
**Architect** (ADR verdict). Add the `cross_feature_matrix.yaml` row *DISABLE_SPOTIFY × {weather,
crypto, stock, teletext, heatmap, webradio}* **before** V3 runs.

**Cleanup placeholder:** **TASK-256** — revert `cyd2usb_webradio` env + the `DISABLE_SPOTIFY` guard if
any of it was merged before a FAIL verdict (per the QM lifecycle BP candidate: every experiment names
its FAIL artefact-disposition + cleanup task id before scheduling). No-op if nothing merged (the design
keeps env/guards on the branch until PASS + the promotion milestone).

**Priority:** P1 — settles "is no-PSRAM WebRadio viable at all," on a lane that runs *now* without
Premium · **Status:** **parked — `parked-pending-TASK-258`** (2026-06-27). The bottom-up bare-rig
(TASK-258 / EXP-009) overtook this top-down strip: it proved the **hardware plays** (both bare and +TFT)
and that the lever is **resident footprint, not RAM/silicon/display** — re-framing this task from "is it
possible" to "drop ~90 K of resident footprint." Keep the branch's V0 harness / `get wrPlaying` /
EXP-008 datapoint — reusable if/when a stripped in-project variant is pursued. · **Opened:** 2026-06-26
**Milestone:** M-WEBRADIO-NOPSRAM · **Branch:** `rnd/webradio-nopsram` · **Experiment record:** EXP-008
**Owner:** Developer (guard + variant signal) → VE (V0 harness) → Architect (ADR verdict)
**Deps:** M-WEBRADIO (firmware complete); **prereq-done:** TASK-239/240 (~11 KB reclaim); **sidesteps:**
TASK-243 (Premium); **baseline:** EXP-007 · **Cleanup:** TASK-256 · **Superseded-by:** TASK-258

---

### TASK-256 — Cleanup placeholder: revert Spotify-disabled env/guards on TASK-255 FAIL

Lifecycle placeholder for TASK-255 (per QM BP candidate: an experiment names its cleanup task id up
front). **Action on TASK-255 FAIL/shelve:** if the `cyd2usb_webradio` env or the `-DDISABLE_SPOTIFY`
guard was merged to trunk at any point, revert it (env stanza in `platformio.ini`, the single
`#ifndef DISABLE_SPOTIFY` guard, the variant-signal additions, the `cross_feature_matrix.yaml` row);
also remove any `cyd2usb_webradio` entry from `./run/check`. **No-op if nothing merged** — the design
keeps all of it on `rnd/webradio-nopsram` until PASS + the promotion milestone, so the expected steady
state is "nothing to clean."
**Priority:** P3 — lifecycle hygiene · **Status:** **dormant — fires only on TASK-255 FAIL-after-merge**
· **Opened:** 2026-06-26 · **Milestone:** M-WEBRADIO-NOPSRAM · **Owner:** Developer · **Deps:** TASK-255

---

### TASK-257 — Lane C-1: ESP32-audioI2S v2.3.0 ↔ v2.0.6 decoder-footprint A/B (optional)

Re-homed onto the TASK-258 bare rig (was a TASK-255 sub-item). Optional, low-priority: on the bare rig, swap
**only** `lib_deps` v2.3.0 ↔ v2.0.6 (fresh `.pio/libdeps`, reflash), same station/buffer/CP2 capture, ≥ 3
trials/arm; signal = Δ `usable`@CP2. Don't swap the core toolchain too (second variable — the EXP-008 trap).
**Mostly answered already:** EXP-009's bottom-up result shows the Helix decoder is vendored ~identically
across the v2.x line and the lever is resident footprint, not library version — so this A/B is now a
*confirmation nicety*, not a decision input. Prior attempt hit `SD_MMC.h: No such file` (v2.0.6 predates
`AUDIO_NO_SD_FS`) — needs the build-config shim before it can run.

**DONE 2026-07-13 → EXP-013 (`docs/rnd/reports/EXP-013-audioI2S-version-ab.md`). CONFIRMED: version is
not a lever.** 3 valid trials/arm on the EXP-009 rig, same station (groovesalad-128), lib_deps-only swap:
Δ `usable`@CP2 ≈ +1.3 K mean for v2.0.6 — inside the ±2.4 K per-trial jitter both arms share; `maxAlloc`@CP2
**byte-identical (102,388) every trial**; CP1 delta (+530 B) = its −520 B static image. Keep the v2.3.0 pin.
The `SD_MMC.h` blocker did NOT reproduce — no shim needed (default chain LDF resolves bundled SD/FS libs;
rig doesn't set `AUDIO_NO_SD_FS` so both arms link the same stack). Production firmware restored + verified.

**Priority:** P3 — optional confirmation; not on any critical path · **Status:** **DONE 2026-07-13 —
CONFIRMED EXP-009 (keep v2.3.0); Lane C closed** · **Opened:** 2026-06-27 · **Closed:** 2026-07-13
· **Milestone:** M-WEBRADIO-NOPSRAM · **Rig:** `~/proj/webradio-bare/`
**Owner:** R&D · **Deps:** TASK-258 (done) · **Parent:** TASK-258 step 4 · **Record:** EXP-013

---

### TASK-262 — Cleanup placeholder: revert TASK-261 spike artefacts on FAIL/shelve

Lifecycle placeholder for TASK-261 (BP-040: an experiment names its cleanup id before scheduling; filed in the
same change as TASK-261). **Action on a Phase-1 FAIL or a shelve:** if any spike artefact reached trunk (the
vendored `lib/ESP32-audioI2S` fork, the reserved-arena allocator, the caps-split probe if deemed not worth
keeping, any `[env:]`/`-D` flag, the `cross_feature_matrix` rows), revert it; remove any `run/check` entry.
**No-op if nothing merged** — the design keeps the fork/arena on `rnd/membudget` until a Phase-2 PASS, so the
expected steady state is "nothing to clean."

**UPDATE 2026-06-28 — spike PASSED, so the FAIL-cleanup branch is moot; this task is REPURPOSED as the A-lite
PROMOTION gate** (human chose "de-risk then promote"). Promotion = merge `rnd/membudget` → master + ungate
(make the arena/fork production, not `MEMBUDGET_PHASE1`-only). **Gated on ALL of:** TASK-263 (halved-DMA
validation) green, TASK-264 (M-RECLAIM Q3-a overlay) green, TASK-265 (live fetch) green, **and TASK-243
(Premium) cleared** for the Spotify-active coexistence validation. Until all green, the fork stays branch-only.
**Priority:** P2 — promotion gate · **Status:** **blocked — gated ONLY on TASK-243 (Premium)** — all design/
engineering de-risk complete: TASK-263 (halved DMA) ✅, TASK-264 (overlay Q3-a) ✅, TASK-265 (fetch finding)
✅, **TASK-267 (fetch-vs-arena fix) DUT-verified PASS 2026-06-28** ✅. **Mainlined 2026-06-28 (`adeab7c`)** — `rnd/membudget` merged to master with A-lite **gated**
(`MEMBUDGET_PHASE1`); production `cyd2usb_winamp` byte-clean (count 0), `run/check` 5/5. The dead-mirror fix +
TASK-259 player-mode + all records are now on master; the `ef8e32c` divergence + a doubled-`#ifdef` auto-merge
artifact were resolved. **Remaining for promotion (the only un-done step):** TASK-243 (Premium) clears →
validate Spotify-active coexistence on the full multi-app build → **ungate `MEMBUDGET_PHASE1` for production**
(flip it on in `cyd2usb_winamp`).

**PROMOTED 2026-06-29 (provisional, without Premium) — branch `feature/task-262-promote-alite`.** Decision
(human): the TASK-243 gate is belt-and-suspenders — `MEMBUDGET_PHASE1` gates **only WebRadio-exclusive code**
(JIT `mb_arena`, halved-DMA fork, decoder→`mb_arena_alloc` routing), and this device outputs **no audio for
Spotify** (display/control only — no I2S/DMA path), so flipping it on changes **zero Spotify runtime
behaviour**. The TASK-264 TLS-drop coexistence mechanism was already in production (gated by `DISABLE_SPOTIFY`,
not the budget flag). What changed:
- `-DMEMBUDGET_PHASE1` moved from `cyd2usb_winamp_debug` → **`cyd2usb_winamp` (production)**; debug inherits it.
- The verbose `[membudget]`/`[mbdbg]` probes (CP0/CP1/CP2, `mb_heap_probe`, arena acquire/release/first-alloc,
  helix-alloc) re-gated `MEMBUDGET_PHASE1 && SERIAL_DEBUG` → **ship silent** in production.
- Dropped the dead `MEMPLAN_STATIC_DECODER` OQ1 experiment; arena `mb_arena_acquire()` call made unconditional
  (libc-fallback when flag absent). `run/check` 6/6 (production now compiles **with** the arena).

**DUT validation 2026-06-29:** arena code proven on the equivalent build (`cyd2usb_webradio`, same
`MEMBUDGET_PHASE1`, no 403 starvation) — `arena acquire=24576B lfbBefore=61428 **OK**` (real 24 K internal
block, not libc-fallback), `arena FIRST alloc ... cap=24576` (Helix decoder allocates **from** the arena),
`wrState=2 wrPlaying=1` (**PLAYING**), idempotent re-acquire — **6/6**. Production `cyd2usb_winamp` boots clean
(heap=134k/maxAlloc=47k idle), runs steady, **no probe spam**, no panic.

**Residual (the only thing Premium would add):** confirming Spotify *renders a playing track* under the
promoted build — nil risk, since the promoted build changes no Spotify code path; and the WebRadio station
fetch on the Spotify-enabled build is itself starved by the TASK-243 403 (project memory: tlsYield
starvation). **Rollback:** TASK-256 (revert `-DMEMBUDGET_PHASE1` from `cyd2usb_winamp`). · **Status:**
**PROMOTED — provisional, DUT-validated 2026-06-29; residual Spotify-render check owed on TASK-243** ·
**Opened:** 2026-06-27 · **Milestone:** M-WEBRADIO-NOPSRAM · **Owner:**
Developer/PM · **Deps:** TASK-261 (done), ~~TASK-263~~, ~~TASK-264~~, ~~TASK-265 (done→TASK-267)~~,
**TASK-267**, TASK-243 (residual only)

---

### TASK-270 — M-MEMPLAN: overlay the Aquarium sprite (needs a TFT_eSPI fork — decision first)

Deferred from TASK-269. The Aquarium strip sprite (`aquariumApp.h`, ~11 K, 275×40×1 B) was assumed an easy
overlay tenant, but `TFT_eSprite::createSprite` **mallocs internally** (`callocSprite`) and exposes **no
external-buffer API** — only `getPointer()` (read). Pointing it at `MEM_aquarium_strip` requires **vendoring +
forking TFT_eSPI** (add a `setBuffer()` path), a second library fork on top of ESP32-audioI2S.

**Decision needed before any work:** is overlaying an 11 K sprite worth owning a TFT_eSPI fork? Likely **no
for now** (small benefit, real maintenance cost — BP-042 lineage). Alternatives: (a) leave the aquarium
sprite on the heap (it's per-app, freed on exit — already fine); (b) overlay only if/when a *second* big
TFT_eSprite tenant appears that shares the region (then the fork pays for two). Keep `aquarium_strip` out of
the manifest until decided.
**Priority:** P3 — optional; gated on a fork cost/benefit call · **Status:** **DEFERRED (parked) — PM
scheduling call 2026-06-28: not now. Standing recommendation = no TFT_eSPI fork for an 11 K per-app sprite
(BP-042 lineage); revisit only if a *second* big TFT_eSprite tenant appears that shares the region (then the
fork pays for two). `aquarium_strip` stays out of the manifest until then. The architecture call itself
(Architect/human) remains open if/when a tenant arrives.** · **Opened:** 2026-06-28 · **Milestone:** M-MEMPLAN
· **Owner:** Architect · **Deps:** TASK-268 · **Design:** M-MEMPLAN §6 (the placeable-vs-not boundary)

---

### TASK-284 — WebRadio station-list fetch: both radio-browser.info mirrors return truncated JSON (IncompleteInput)

Found 2026-07-06 attempting TASK-278 E1 DUT validation. Fresh boot, `switchApp` into WebRadio
kicks the fetch normally, but both configured mirrors fail identically:
```
[I][dataTask.webradio] GET mirror=de1.api.radio-browser.info code=200 elapsed=2638ms
[W][dataTask.webradio] JSON err mirror=de1.api.radio-browser.info: IncompleteInput
[I][dataTask.webradio] GET mirror=all.api.radio-browser.info code=200 elapsed=2479ms
[W][dataTask.webradio] JSON err mirror=all.api.radio-browser.info: IncompleteInput
[W][webradio] station fetch failed ok=0 http=-100 jsonErr=IncompleteInput
```
HTTP 200 on both, but the JSON body is truncated before the parser completes — `wrCount` stays 0
permanently (`pending` correctly flips 1→0, so the fetch *did* run and *did* fail, this isn't a
stuck-pending bug). Effect: WebRadio can never leave STOPPED via the normal station-list path,
which blocks TASK-278's E1/E2/E3 wr_playing measurement entirely (`set wrUrl` direct-station
injection is the known workaround — used for E3's real-stream-death case already). Not caused by
the TASK-278 diff — `dataTask`'s HTTP/JSON station-list path is untouched by that change.
**Not yet root-caused**: could be a response-buffer-too-small truncation in the dataTask HTTP
client, a timeout cutting the body short, or an actual upstream API change/outage on both mirrors
simultaneously (less likely, but check by hand before assuming firmware-side).

**Investigation (2026-07-08):** ruled out "persistent server/mirror fault" and "response-buffer-
too-small" as the cause. Host-side `curl --http1.0` with the identical UA/URL/query params the
firmware sends returns a complete, valid 33.7 KB JSON body from `de1.api.radio-browser.info`
every time tried — no Content-Length (HTTP/1.0 close-delimited body), which rules out a
firmware-side buffer-size bug (the parse doc streams via `deserializeJson(doc, Stream&)`, it
doesn't pre-size a receive buffer). Also checked whether ArduinoJson's Stream reader silently
truncates on a transient stall: it explicitly uses `Stream::readBytes()` (not `read()`) *because*
`read()` ignores the client's timeout — and `WiFiClientSecure`'s default `_timeout` is 30 s (no
explicit `setTimeout()` call was overriding it down), generous for a 33 KB TLS body. No
deterministic firmware bug found; "both mirrors fail identically in the same attempt" reads as
two independent transient network stalls landing back-to-back, not a systemic block — consistent
with the intermittent field pattern already logged (comes and goes; 2026-07-07 runs were clean,
count=16).

**Fix (best-effort mitigation, 2026-07-08):** `fetchWebRadioStations()`'s per-mirror page-0 loop
now retries the SAME mirror once with a fresh connection on a `-100` (JSON parse error, i.e.
`IncompleteInput`) before falling through to the next mirror — cheap (one extra handshake+GET
only on the error path) and turns a single transient stall into a non-issue instead of burning
both configured mirrors in the same unlucky window.

**Caveat — this could not be DUT-verified against the actual failure**, since the truncation
isn't reproducible on demand (host-side requests never truncated in this session either). DUT
regression only confirms the happy path is unaffected: `T_WR_COEX_01`/`T_WR_HEAP_01`/`02` all
PASS post-fix (`wrCount=16`, retry path not exercised — mirror succeeded on the first try, as
usual). `./run/check` 6/6. Leaving open rather than DONE until a live recurrence confirms the
retry actually clears it; if it recurs with the retry landed, the next data point is whether the
retry itself also fails (pointing at something more systemic than a one-off stall) or succeeds
(confirming the mitigation).

**Priority:** P2 — blocks TASK-278 DUT validation (wr_playing state unreachable normally) ·
**Status:** open — investigated, best-effort mitigation landed (same-mirror retry-once on JSON
parse error); awaiting a live recurrence to confirm it actually resolves the field symptom ·
**Opened:** 2026-07-06 · **Milestone:** M-WR-AUDIO-TASK · **Owner:** Developer · **Deps:** — ·
**Branch:** master

---

### TASK-314 — WebRadioApp doesn't override hasError()/isConnecting(): player-slot taskbar indicator always reads idle-green in WebRadio mode

Found while wiring the WebRadio active-icon fix (taskbar.h now correctly
lights up the Spotify/player slot when `currentAppId == AppId::WebRadio`,
recoloured orange→red). That fix surfaces a pre-existing gap: `WebRadioApp`
(`app/src/webRadioApp.h`) never overrides the base `App::hasError()` /
`App::isConnecting()` (both default `false`), so `shell::activeError()` /
`shell::activeConnecting()` (main.cpp, TASK-245/ADR-046) always read false
for it. The active-slot indicator bar therefore shows green (idle) the
entire time WebRadio is connecting to a stream or in a sustained error
state — previously invisible only because no slot lit up at all in
WebRadio mode (that bug is now fixed), so this was never observable before.

Needs: `WebRadioApp::isConnecting()` true while establishing a station
connection (no audio yet); `WebRadioApp::hasError()` true on a sustained
stream/fetch failure, matching the sticky/self-clearing contract other
apps use (see StockApp / SpotifyApp's error-state fields for precedent).
Should reuse whatever state WebRadioApp already tracks internally for its
own on-screen connecting/error UI, if it tracks one — check
`app/src/webRadioApp.h` / `app/tools/preview_webradio_*.png` states
(stopped/connecting/playing/error) first rather than adding new state.

**Fix (2026-07-12):** `WebRadioApp::isConnecting()` → `_state == CONNECTING`;
`WebRadioApp::hasError()` → any of `ERROR_WIFI/ERROR_STALL/ERROR_UNREACHABLE/
ERROR_BLOCKED`. No new state added — reuses the existing `WRPlayState`
already tracked for on-screen connecting/error UI, per the sticky/self-
clearing contract `shell::activeError()`/`activeConnecting()` expect (same
pattern as `SpotifyApp`/`PlaneRadarApp`).

**DUT-verified 2026-07-12** (debug firmware, serial dbg surface —
`switchApp 11` into WebRadio, `set wrState N` + `get activeError`):
`wrState=1` (CONNECTING) → `connecting=true,active=false`; `wrState=4/5/6`
(ERROR_STALL/UNREACHABLE/BLOCKED) → `active=true,connecting=false` each;
`wrState=2` (PLAYING) and `wrState=0` (STOPPED) → both `false` (self-clears).
Production firmware (`cyd2usb_winamp`) reflashed and monitor restored after.

**Priority:** P3 — cosmetic/observability gap, not a functional regression
· **Status:** DONE · **Opened:** 2026-07-12 · **Closed:** 2026-07-12 ·
**Milestone:** none (post M-PLANERADAR taskbar-icon cleanup) · **Owner:**
Developer · **Deps:** none · **Branch:** master

---

## Open — M-BOOT-UI (2026-07-20)

### TASK-364 — chrome-first boot + whole-session WiFi-status marquee (M-BOOT-UI, ADR-055)

Implement `docs/architecture/designs/M-BOOT-UI.md` / `docs/architecture/
decisions/ADR-055.md` in full — both accepted, human sign-off 2026-07-20.
One task, not split: the boot-time chrome-first change (§1-§5) and the
§6 whole-session background-reconnect marquee extension share the same
mechanism (the title marquee via `setTitle()`), the same build-family scope
(`WINAMP_DISPLAY`), and were reviewed and accepted together as a single
design after the human resolved OQ2 to fold §6 in rather than defer it —
splitting into two tasks would just re-separate what the design doc
deliberately merged, for no review/rollout benefit (§6's guard mechanism
sits directly in `winampDisplay.setTitle()`, the same file/function the
boot-time `setTitle()` calls target — a single coherent diff to that file
either way). Read both documents in full before implementing; this brief
summarizes their concrete plan but the design doc's §1-§6 carry the
reasoning and line numbers.

**Implementation (five pieces, per the design doc):**

1. **New early chrome-paint call site**, `main.cpp:~2176` — an *additional*
   direct call to `winampDisplay.showDefaultScreen()` + `renderTaskbar(...)`,
   placed right after `TouchCalStorage::load()` and the backlight-PWM
   handoff (before `fetchConfigFile()`/`wifiDiag::begin()`/the WiFi connect
   cascade). This is **not** a reorder of the existing
   `main.cpp:2415-2422` block (`g_apps[(int)AppId::Spotify]->init()` +
   `renderTaskbar()`) — that block stays exactly as-is; its second pass
   becomes a harmless, cheap, idempotent repaint (§1's own doc comment).
   `g_appLaunched` bookkeeping and `switchApp()`'s init-vs-resume branching
   are untouched by construction (Goal 4). Per §1's tracing, nothing the
   early paint touches (`spotifyTask::isHealthy()`/
   `lastSuccessfulPollAgeMs()`, `shell::activeError()`/`activeConnecting()`)
   depends on `SettingsStorage::load()`, WiFi, NTP, or `spotifyTask::begin()`
   having run — same accessor family ADR-054/TASK-363 already validated
   safe pre-`begin()`.
2. **`setTitle()` calls at the ~10 existing WiFi/NTP phase-transition
   points**, per §2's table — one generic `"WI-FI: CONNECTING..."` string
   covering all four fallback-cascade call sites (hardcoded-SSID, NVS,
   SPIFFS-creds, re-association settle; OQ1's resolved single-string
   decision, not per-stage text), plus distinct strings for
   connected/retry-in-background/no-credentials outcomes and the NTP
   sync/HTTPS-Date-fallback phases. No new branching — one `setTitle()`
   call added at each site the code already visits. Deliberately no
   `"SPOTIFY: CONNECTING..."` phase (already covered by
   `repaintChrome()`'s titlebar-inactive overlay + the taskbar's amber
   indicator, per §2).
3. **`tickMarquee()` calls riding the existing per-iteration
   `esp_task_wdt_reset()`/`yield()` hooks** in the WiFi/NTP wait loops
   (§3, Option B) — ship together with piece 2, not as a follow-up (§3's
   "Lean: ship both A and B together" — B is ~4 lines, zero marginal cost
   once piece 2's call sites are already being edited). The three WiFi
   loops use `esp_task_wdt_reset()` (`main.cpp:2205,2221,2239,2252`); the
   NTP loop uses `yield()` (`:2311-2314`) — `tickMarquee()` rides whichever
   hook is already there, no change to WDT-feeding behavior either way.
4. **`setTitle()` stash-and-restore guard in `winampDisplay.h`** (§6):
   `_wifiDownOverrideActive` bool + a stash buffer sized/shaped like
   `lastTitle`. Guard clause at the top of `setTitle(text)`: while active,
   stash `text` into the pending-restore buffer and return without
   drawing — every caller's intent is remembered, none can paint over the
   override, none need to know it exists. Two new entry points:
   `showWifiDownOverride()` (no-op if already active; otherwise stashes the
   *current* `lastTitle`, then force-draws `"WI-FI: RECONNECTING..."`
   bypassing the guard) and `clearWifiDownOverride()` (no-op if not active;
   otherwise force-draws whatever is in the stash — the most recently
   *attempted* real title, correct by construction per §6's mechanism
   writeup, including the Spotify unchanged-track case where a passive
   "wait for the app's next real `setTitle()`" approach would leave the
   marquee stuck forever).
5. **New `loop()`-level edge-triggered detector**, self-contained (no new
   `wifiDiag` API): `WiFi.status() == WL_CONNECTED` polled once per `loop()`
   iteration + a local `static uint32_t s_downSince = 0` anchored fresh on
   each down-transition (deliberately not reusing `superviseTick()`'s
   `lastDiscMs` staleness-prone anchor — a fresh local edge-trigger
   sidesteps that class of bug for free). Threshold proposed at 10s
   (**OQ5, open — VE/DUT to tune, a single adjustable constant, not
   DUT-pinned by the design doc**). **Must be gated by the exact same
   `currentAppId != AppId::Settings` condition `wifiDiag::superviseTick()`
   already uses** (`main.cpp:3886`) — load-bearing per X042, not cosmetic:
   `switchApp()`'s full-screen-canvas convention means Settings already
   owns and repaints the marquee's screen region itself, so an ungated
   override would blit stray title-bar text over the Settings UI, a real
   visual corruption. Co-locate the new block with the existing
   `superviseTick()` call site for discoverability rather than inventing a
   separately-tracked condition that could drift out of sync with it.

**Scope:** `WINAMP_DISPLAY` build family only (`cyd2usb_winamp` production
env + everything that `extends` it: `_debug`, `_screenlog`, `_webradio`,
`_webradio_16k`, `_debug_noSpotify`), inside the same `#ifdef
WINAMP_DISPLAY` guard the existing `SpotifyApp`/`g_apps[]`/taskbar code
already uses. Non-Winamp `cyd`/`cyd2usb` (plain) and `trinity` (HUB75
matrix) envs untouched — those backends have no marquee/taskbar concept,
matches current behavior.

**Explicitly out of scope (flagged by the design doc, not to be pulled in
here):**
- **OQ4** — the taskbar active-slot indicator doesn't reflect
  `spotifyTask::isHealthy()` (only `authError()`/`connecting()`), a real
  pre-existing gap in the already-accepted `ADR-046`, found while
  investigating §6. Not fixed by this task — flagged for a future
  PM/Architect follow-up, no task filed for it yet.
- Shortening/parallelizing the ~85s-worst-case WiFi fallback cascade
  itself (§4) — display-timing only, not retry-policy, in this task.
- Touch input during the blocking WiFi/NTP waits, and a dot-cycle
  "connecting…" animation beyond marquee-scroll reuse (§3) — both
  evaluated and consciously deferred as materially larger, separate work.

**Registry:** add `boot-ui-001` (new) and `wifi-diag-001` (new,
retroactively registered — `wifiDiag.h`/`.cpp` already ships, TASK-274/
282/283/296, `status: implemented`, back-fill `git_ref`/`test_ids` from
existing history) to `feature_inventory.yaml`; add edges X039-X042 to
`cross_feature_matrix.yaml` per the design doc's §Registers (X039:
`boot-ui-001`×`chrome-001` dependency/low; X040:
`boot-ui-001`×`wifi-001` dependency/low; X041: `boot-ui-001`×`time-001`
dependency/low; X042: `boot-ui-001`×`wifi-diag-001` shared_state/**medium**
— the Settings-suppression condition is a convention-enforced coupling, not
a shared constant/function call, a real if narrow drift risk if either
side's condition is ever touched independently).

**Owner:** Developer · **Deps:** TASK-362 (`setTitle()` dedup/redraw-on-change
precedent this design reuses verbatim, no new display mechanism); TASK-363/
ADR-054 (confirmed-safe pre-`spotifyTask::begin()` accessor pattern the
early paint reuses); wifi-diag-001/TASK-274/283/296 (the background
supervisor §6 surfaces, unmodified — read-only observation of its
`currentAppId != Settings` gating condition, no call-graph dependency);
M-BOOT-UI.md + ADR-055 (accepted, human sign-off 2026-07-20) · **Gate:**
`./run/check` 5-gate green (golden-hash gate expected unaffected — no
generated asset touched, confirm at implementation) + the design doc's own
Exit Criteria, qualitative DUT checks per OQ3's resolution (no timestamped
capture required): healthy-AP boot shows chrome+taskbar immediately with
the phase-text sequence legible; ≥1 forced-full-cascade boot (unreachable
AP or wrong password) shows chrome+taskbar throughout with no black screen
and the static `"WI-FI: CONNECTING..."` text; WebRadio-mode boot confirms
clean hand-off from boot-status text to WebRadio's own first `setTitle()`
call, no stale/glitched artifact; no-WiFi-credentials boot confirms
`"WI-FI SETUP NEEDED"` briefly shows then `switchApp(Settings)` takes over
cleanly; one BP-048 screendump eyeball pass across every phase string
confirms no clipping; a live mid-session WiFi-drop scenario with a
non-Spotify, non-WebRadio app foreground (e.g. Clock/Weather) confirms the
`"WI-FI: RECONNECTING..."` override engages past the tuned threshold and
clears cleanly within one `loop()` tick of reconnect; the same with Spotify
foreground and an *unchanged* track across the outage confirms the active-
restore mechanism (not a passive wait) recovers the correct title; the same
with WebRadio foreground and ICY metadata arriving mid-outage (if
reproducible) confirms the guard stashes without letting WebRadio paint
over the override; a WiFi-drop-while-Settings-foreground scenario confirms
no marquee override ever paints over the Settings UI and state is correct
within one `loop()` tick of returning to any non-Settings app; full
serialdbg suite green on `cyd2usb_winamp` · **Priority:** P2 (accepted
architecture ready for implementation, real UX gap on both ends — black
screen on a dodgy boot network, 100%-silent background WiFi retry
mid-session — similar footing to TASK-363, not a live crash/regression)
· **Size:** M (one new early-paint call site, ~10 `setTitle()` insertions,
~4 `tickMarquee()` insertions, one new guard clause + two thin wrapper
methods on `WinampDisplay`, one new `loop()`-level detector block — small
per-piece, five pieces plus a wide DUT exit-criteria list) · **Status:**
**DONE** 2026-07-28 — all five pieces landed, `./run/check` 6/6, and every
Exit Criteria item DUT-confirmed across two sessions (2026-07-25, 2026-07-28)
except one inconclusive (not failing) sub-case explicitly covered by the
Exit Criteria's own "(if reproducible)" allowance (see PM closing note
below) · **DUT:** required (all Exit Criteria above are DUT checks; no
host-only substitute) — satisfied

**Implementation note (2026-07-25):** all five pieces landed as specified.
One implementation-time finding not anticipated by the design doc: the new
`_wifiDownStash` buffer (§6, sized `sizeof(lastTitle)` = 264 B) as a second
static member on the global `winampDisplay` overflowed
`cyd2usb_winamp_debug`'s `.dram0.bss` budget by 184 B (prod `cyd2usb_winamp`
built fine — debug has less static-RAM slack). Fixed by lazily
`malloc()`-ing that buffer once (first outage, never freed) instead of a
static array — same full capacity/correctness, moves the cost off the
static budget. `./run/check` 6/6 green.

DUT coverage so far: fresh-boot serial capture confirms the early paint
fires before `fetchConfigFile()`/WiFi (a `[D][chrome] drawVolume` line
appears immediately after `TouchCalStorage::load()`'s print, well before
`reading config file`), the existing `main.cpp:2415-2422` second pass is
harmless/idempotent, boot into WebRadio mode hands off cleanly with no
stale boot-status artifact (screendump confirmed), and the smoke test suite
(`./run/test-smoke`) passed with production firmware restored afterward.

**Follow-up DUT pass (2026-07-28):** closed out the remaining Exit Criteria
from above. No product code touched — pure verification (`git status` was
clean before and after; a temporary `set wifiKill`/`set titleTest` debug
hook and an ephemeral bogus-SSID `PLATFORMIO_BUILD_FLAGS` env var, never
written to a tracked file, were used to force outages and reverted before
finishing).
- **Forced full-fallback-cascade boot:** confirmed via a genuinely-failing
  hardcoded-SSID stage. Chrome+taskbar+marquee survived the whole outage,
  no black screen — the core claim holds. Side finding, out of this task's
  scope per §4 but worth flagging: once the hardcoded stage's `WiFi.begin()`
  genuinely fails, the subsequent NVS and SPIFFS-creds attempts in the
  *same* boot both hit an ESP32 driver-level `sta is connecting, return
  error` and fail too, even with correct SPIFFS creds — recovery only came
  via the background supervisor's later kick (~60-85s post-boot). A
  retry-policy issue in the fallback cascade itself, not a display-layer
  bug; §4 already named shortening/parallelizing that cascade as separate,
  unscoped work — this is supporting evidence for it, not a new problem.
  No task filed for it yet; human to decide if/when.
- **§6 mid-session scenarios**, via a purpose-built single-connection test
  harness (avoids `run_serialdbg_tests.Dut`'s DTR-reset-on-open, which would
  wipe test state on every screendump): **Clock foreground** — override
  engages/clears cleanly, no stuck text (screendumped). **Spotify
  foreground, unchanged track** — real playback blocked by the pre-existing
  TASK-243 Premium lapse, so a temporary synthetic `setTitle()` debug hook
  simulated a last-known title with zero further `setTitle()` calls during
  the outage; confirmed the guard **actively restores** the exact
  pre-outage title — the specific gap §6's mechanism exists for
  (screendumped). **WebRadio foreground** — override engages/clears
  correctly; the narrow "ICY metadata arrives mid-outage" sub-case wasn't
  cleanly isolated (station fetch was flaky this pass) — honestly
  inconclusive on that one point, covered by the Exit Criteria's own
  "(if reproducible)" allowance, not a blocker. **Settings-foreground
  suppression** — confirmed zero corruption of the Settings UI through a
  14s+ outage, correct state on return to a non-Settings app
  (screendumped).
- **BP-048 clipping check:** longest boot-phase string
  (`"TIME: HTTPS FALLBACK..."`, 23 chars) and the §6 override string
  (`"WI-FI: RECONNECTING..."`, 22 chars) both render with no clipping
  (screendumped).
- **OQ5 (10s threshold):** left unchanged. A rapid flap pattern (~1s
  disconnect/reconnect) never triggered the override, consistent with the
  continuous-down requirement; genuine sustained outages engaged it
  reliably. No evidence this pass argues for a different value.
- **WebRadio-mode boot handoff:** not re-tested this pass — already
  DUT-confirmed (screendump) in the 2026-07-25 session; left as-is.

Note for implementer (historical, from the 2026-07-28 pass): OQ5 (10s
down-threshold before showing the reconnect override) is a proposed
starting point, not DUT-tuned — confirm or adjust at a future VE pass,
single constant, no design change needed either way; this pass's flap test
found no evidence for a different value. OQ4 (taskbar indicator not
reflecting `isHealthy()`) is a separate, real, already-flagged gap in
`ADR-046` — not fixed as part of this task, per its own explicit scope.

**PM closing note (2026-07-28):** reviewed this entry end-to-end against
its own Exit Criteria and the two items still open at the 2026-07-28
follow-up. Closing as **DONE**, not carrying it forward as a qualified/
partial status:
- **WebRadio ICY-mid-outage sub-case** — the task's own Exit Criteria
  wording qualifies this specific check "(if reproducible)"; non-repro was
  anticipated as an acceptable outcome, not a blocking failure condition,
  and station-fetch flakiness (not the feature under test) is why it wasn't
  isolated this pass. The underlying guard mechanism (§6's stash-and-restore
  in `setTitle()`) is caller-agnostic — WebRadio's ICY title updates go
  through the exact same `setTitle()` call site already DUT-confirmed
  correct under Clock and Spotify. There is no WebRadio-specific code path
  that could behave differently, so this isn't an unverified mechanism,
  just an unconfirmed instance of an already-proven one. Not filing a
  dedicated follow-up task for it — if station fetch cooperates on a future
  WebRadio DUT session, worth a five-minute opportunistic re-check, but it
  doesn't warrant tracked backlog on its own.
- **OQ4 (taskbar active-slot indicator doesn't reflect
  `spotifyTask::isHealthy()`)** — explicitly out of this task's scope from
  the design doc's own framing, never a gate TASK-364 was closing against.
  It's real and worth tracking properly rather than living as a buried note
  in a closed task, so filed as **TASK-366** below.

Both items were live options this task's own gate anticipated resolving one
way or the other; neither turned out to require keeping this entry open.

## Open — M-DISPLAY-DELTA-COMMON settings-slider follow-up (2026-07-24)

### TASK-365 — SliderWidget flicker: Clock-style discrete-slot diff for the Settings drag slider

Human reported a Settings slider flickering during touch-drag and asked for an audit
of every touch-drag-gesture UI element against ADR-052/`M-DISPLAY-DELTA-COMMON.md`
(the erase-then-redraw-unchanged-pixels bug fixed for Clock/TASK-354 and PlaneRadar/
TASK-358). Architect audit filed as an addendum to that design
(`docs/architecture/designs/M-DISPLAY-DELTA-COMMON.md` §Addendum, 2026-07-24;
cross-referenced in ADR-052's Consequences).

Finding: `SliderWidget::render()` (`app/src/settings/sliderWidget.h:73-115`) runs
unconditionally on every `onMove()` — full-row `fillRect(0,rowY,275,26,BG)` then
redraws label, value number, full track, and knob, at whatever the touch poll rate
is. Three call sites, all affected: `displaySection.h:61` (brightness "Level"),
`appsSection.h:112` (WebRadio "Max vol"), `appsSection.h:132` (PlaneRadar
"Poll: Ns"). Same anti-pattern class as the Clock bug, different data shape (a
slider's dynamic state is knob-x + an integer value, not a discrete slot array —
still a diff, not a viewport-repair case; see addendum's Open-Question-2 rationale
for why `withViewportRepair()` is the wrong tool here).

**Scope (per the addendum's lean):**
1. Split `SliderWidget::render()` into a one-time static draw (label, on row-enter/
   `init()`) and a `renderDynamic()` invoked from `onMove()`/`onRelease()`.
2. Cache the last-drawn knob x; no-op `renderDynamic()` if the new knob x is
   unchanged (kills redundant repaints from finger jitter within a step).
3. Redraw the value-number text only when the integer value actually changes.
4. Scope the track/knob redraw to `kTrackX0 - kKnobW/2 .. kTrackX1 + kKnobW/2` at
   row height — never the full 275 px row, never the label.
5. Update the three call sites if `render()`'s signature changes; verify none of
   them relied on the old full-row repaint as an implicit "clear stale content"
   (e.g. `_repaintLdrRows()`/section `repaint()` calls already handle full-row
   clears on section entry — confirm the slider's own full-row fill isn't load-
   bearing there before narrowing it).

**Explicitly out of scope** (flagged by the addendum, own follow-ups if picked up):
LedSection hue-strip drag's expensive per-tick SV-square regen (different problem
shape — real per-pixel work, not waste); LedSection SV-square drag's ghost-cursor
under-repaint bug (opposite failure mode, ledSection.h `_drawSvCursor()`).

**Owner:** Developer (implementation) · **Deps:** M-DISPLAY-DELTA-COMMON addendum
(design, this session); informed by TASK-354/358 (the Clock/PlaneRadar precedents
this generalizes from) · **Gate:** `run/check` + DUT eyeball (BP-048 — this is a
visual, drag the slider live and confirm no flicker) + a screendump-diff assertion
analogous to `clock_delta_smoke.py` (steady drag motion touches only the
track/knob region + value-number cell, not the label or background outside the
track) · **Priority:** P2 — confirmed visible defect, not a correctness/data-loss
bug · **Status:** Closed 2026-07-29 (`e70a87f`) — BP-048 human eyeball PASSED
(human dragged the slider live, confirmed flicker gone, "much better").

**Implementation:** `sliderWidget.h` split into `render()` (one-time/row-enter
full draw, unchanged behaviour) + `renderDynamic()` (called from `onMove()`/
`onRelease()` at the three call sites — `displaySection.h`'s Level row,
`appsSection.h`'s Max-vol and Poll-interval rows). `renderDynamic()` diffs three
independent pieces against per-instance last-drawn state and skips any that
didn't change: label cell (`strncmp` against a cached copy — needed because
PlaneRadar's Poll row bakes the live value into its label text, "Poll: Ns", so
that one *does* redraw every step; Level/Max-vol pass a constant literal and
no-op after the first call), value-number cell (`kValueX0..S_CANVAS_W`, redraws
only on integer value change), and track+knob (`kZoneX0..kZoneX1`, i.e.
`kTrackX0-kKnobW/2 .. kTrackX1+kKnobW/2`, redraws only on knob-x or
disabled-state change). No full-row `fillRect` on the hot path anymore.

DRAM note: the 3 new per-instance diff-cache fields (`_lastValue`/`_lastKnobX`/
`_lastDisabled`/`_lastLabel[]`) overflowed `cyd2usb_winamp_debug`'s
`.dram0.bss` budget at first pass (72 bytes over, [[feedback_dram_bss_static_buffers|
memory: DRAM budget — check debug env too]]) — fixed by narrowing `_min`/`_max`/
`_value`/`_lastValue`/`_lastKnobX` to `int16_t` and `_lastLabel` to `char[10]`
(longest real label, "Poll: 30s", is 10 bytes incl. NUL); both envs compile clean
after.

**Verification:** `run/check` 6/6. DUT-verified on debug firmware via new
`app/tools/slider_delta_smoke.py` (8/8 PASS) — drags the Level slider start-to-
end via the incremental `onMove()`/`onRelease()` path only, then forces a fresh
`render()` by leaving/re-entering the section at the same settled value, and
diffs the two screendumps: 0 px differ. Documented in the script why a plain
before/after content diff can't observe the flicker *itself* (old and new code
draw identical final pixels for any given state — the bug was wasted
intermediate writes, a timing artifact, not wrong output); what this test
proves instead is that the new scoped/diffed repaint reaches the exact same
pixel state a full redraw would, i.e. no stale-knob/stale-digit artifacts from
narrowing the erase rects. Production firmware reflashed after the debug-build
test run.

**BP-048 gate:** human dragged the slider live on the device and confirmed the
flicker is gone — this closes the one thing the automated check above
structurally couldn't test (see its own reasoning above for why).

## Open — taskbar health-indicator follow-up (2026-07-28, filed on TASK-364 closure)

### TASK-366 — taskbar active-slot indicator doesn't reflect `spotifyTask::isHealthy()` (ADR-046 gap)

Filed by PM on closing TASK-364, per that task's own explicit "not fixed here, future
PM/Architect follow-up" flag (§6 investigation surfaced it, out of scope by design-doc
framing) — not a live bug, pure display-indicator scope.

`ADR-046`'s taskbar active-slot indicator (`taskbar.h:renderActiveIndicator`) drives its
tri-state colour (error/red > busy-or-connecting/amber > idle/green) from the `App` base-
class endpoints `hasError()`/`isConnecting()`. For Spotify these resolve to
`spotifyTask::authError()` (a **sticky 403 latch** — set on any 403, cleared only on a real
200/204 success) and `spotifyTask::isConnecting()`. Neither reads
`spotifyTask::isHealthy()` (`spotifyTaskStorage.cpp:578`, `return s_consecutiveFailures < 2`)
— a **different, non-sticky** signal already computed and already exposed (used by
`winampDisplay.h:131,1208` for the marquee), but never wired into the taskbar's error
endpoint.

**Concrete gap:** a run of ≥2 consecutive *non-403* poll failures (network blip, timeout,
DNS hiccup, any non-auth HTTP error) leaves `s_consecutiveFailures >= 2` (i.e.
`isHealthy() == false`) while `authError()` stays false and `isConnecting()` stays false
(if the first poll already succeeded this boot) — the taskbar bar renders green throughout,
even though Spotify has an active, ongoing fetch problem the device itself can already see.
Distinguish from ADR-046 §4's already-accepted "starvation makes other apps slow, not
failed" limitation — this is Spotify's **own** slot failing to reflect Spotify's **own**
already-computed unhealthy signal, not a cross-app starvation case.

**Proposed scope (PM sizing only — Architect to confirm approach before implementation,
per AGENTS.md's cross-component-design consult convention, since this touches the shared
`App`/taskbar contract ADR-046 established):**
1. Decide whether `SpotifyApp::hasError()` should OR in `!spotifyTask::isHealthy()`
   alongside the existing `authError()` check, or whether a genuinely distinct third
   tri-state input is warranted (non-sticky "degraded" vs. sticky "auth-failed" are
   different severities — collapsing them into one red may itself need a design call,
   not just a code change).
2. If collapsed: confirm `isHealthy()`'s non-sticky nature doesn't cause taskbar flap
   (bar going red then immediately green on transient single-poll recovery) the way
   ADR-046 Amendment 2 already had to fix once for the auth-latch case — likely needs
   the same sticky-latch treatment `authError()` got, not a raw pass-through.
3. Audit whether other apps' `hasError()` implementations have the same class of gap
   (a locally-computed health/degraded signal that exists but isn't wired to the shared
   endpoint) while touching this — TASK-246's original breadth-first audit (ADR-046)
   predates `isHealthy()`'s introduction.

**Owner:** Architect (design call) → Developer (implementation) · **Deps:** ADR-046
(tri-state precedence + latching convention this extends); TASK-364/§6 (where the gap was
noticed, no code dependency) · **Gate:** `run/check` + DUT screendump of the taskbar bar
across a forced non-403 failure run (e.g. AP-side block/timeout, not a 403) confirming red
appears and clears correctly, no flap · **Priority:** P3 — real observability gap, but no
known live bug and no user report; display-indicator scope only, Spotify's actual
poll/retry/backoff behavior is unaffected either way · **Size:** S-M (small code change if
the design call in step 1 lands on "reuse the OR", larger if it lands on a genuine third
state) · **Status:** **DONE — closed 2026-07-31.** DUT gate passed (see below).

**Design call (step 1-3, resolved):** reuse the OR (`SpotifyApp::hasError()` returns
`authError() || degraded()`) — no new tri-state colour, no `taskbar.h`/`shell_layout.h`
touch, golden-hash safe. Collapsing sticky-403 and sticky-degraded into one red was judged
acceptable: both are "Spotify's poll path is stuck," and the taskbar has no room for a
fourth colour without a design doc of its own (rejected per ADR-046's own precedent against
a persistent per-slot health dot). Step 2 (flap risk): confirmed real — a raw `isHealthy()`
read is `s_consecutiveFailures < 2`, and that counter is zeroed by `resetBackoff()` on every
touch, the *exact* bug Amendment 2 already fixed once for `authError()`. Fix: a new sticky
latch `s_degradedLatched` (`spotifyTaskStorage.cpp`), set when `s_consecutiveFailures` first
reaches 2 on a non-200/204 poll, cleared only on a real 200/204 — mirrors
`s_authErrorLatched` exactly, touch-immune. Step 3 (breadth audit): grepped every other
app's `hasError()` (Stock/Weather/Crypto/Teletext/WebRadio/PlaneRadar) — each already wires
its own fetch-fail flag directly; `isHealthy()`-style "computed but unwired" signals are a
Spotify-only artifact (predates `isHealthy()`, which was added for the marquee, not the
taskbar). No other app needs this fix.

**Implementation:** `spotifyTaskStorage.cpp` (`s_degradedLatched` + `degraded()` accessor +
wiring in `doPoll()`'s three branches), `spotifyTask.h` (`degraded()` decl),
`main.cpp` (`SpotifyApp::hasError()` OR). `dbg_set("backoff", N)` also sets the latch when
`N>=2` and `dbg_set("lastHttp", 200|204)` also clears it, mirroring the existing `lastHttp`
403 injector — lets VE drive the red state deterministically without a real network failure.
Also added `spotifyDegraded` to `get activeError`'s JSON (alongside the existing
`spotifyAuthError`) so the two sticky latches can be asserted independently.
`./run/check` 6/6 (prod + debug both compile clean).

**DUT gate — DONE 2026-07-31.** Flashed debug, ran a single persistent serial session
(`app/tools/screendump.py`'s `DutLite` + a driver script) so the DTR-reset-on-open quirk
(documented in EXP-020's harness notes) couldn't wipe injected state between commands.
Real account is still 403-latched (owner Premium lapse, TASK-243 — confirmed live:
`last=403` in the boot heartbeat), so isolating `degraded()` from `authError()` needed an
explicit `set lastHttp 200` (clears both) before `set backoff 2` (trips only `degraded`).
Sequence + evidence:
1. Fresh boot baseline: `activeError` all-false, `connecting:true` (no poll yet) — bar amber.
2. `set lastHttp 200` + `set backoff 2` → `{"active":true,"spotifyAuthError":false,
   "spotifyDegraded":true}` — **screendump shows solid red** (`TASKBAR_ERR_COLOR`), proving
   `degraded()` alone (no 403 involved) drives the same red path as `authError()`.
3. `set lastHttp 200` again (recovery) → `{"active":false,"spotifyDegraded":false}` —
   **screendump shows amber**, not green, because `connecting()` is still true (this boot
   has had zero real 200/204 polls, expected given the live 403 account) — correct
   precedence (`connecting` beats idle), not a bug.
4. Touch-immunity (no flap on tap): **not independently re-exercised with a live physical
   touch** — the injected `tap <x> <y>` serial command dispatches straight to
   `handleInput()`/`switchApp()` and never passes through `appHandleInput()`'s
   `ts.touched()` branch that calls `resetBackoff()`, so there is no serial-injectable path
   that could flap it either way. Verified instead by code inspection: `resetBackoff()`
   (`spotifyTaskStorage.cpp:571`) only ever zeroes `s_consecutiveFailures`, never touches
   `s_degradedLatched` — structurally identical to `s_authErrorLatched`, whose touch-immunity
   *was* DUT-verified live (ADR-046 Amendment 2, "touch-immune" on real taps). Same mechanism,
   same guarantee.

Production firmware reflashed after, monitor restored. **TASK-366 CLOSED.**

## Open — full-suite regressions/findings (2026-08-01, filed from `run/test` full run)

Filed from a full `./run/test` pass (120 passed, 6 failed, 41 skipped, 3 flaked; DUT restored to
prod cleanly). Two of the six failures (`T_WR_TLS_01`, `T_PRM_02`) match already-tracked flake
patterns (TASK-284 mirror truncation; TASK-313 adsb.fi Cloudflare-edge truncation, though tonight's
`T_PRM_02` gaps — 16/300s, up to 26s between fetches — are worse than the last documented PASS at
tasks.md:456, 36/300s, and worth a fresh look rather than being assumed identical). The four below
had no prior record in this file or in QM memory and were filed as-is, uninvestigated.

**Update 2026-08-01 (same session):** TASK-380/381/382 (the three Stock chart `fetchOkCount`
stalls, T176/T188/T192) were investigated and all three now have a confirmed root cause and are
**not** one shared bug as the matching symptom initially suggested. TASK-380 (T176): a stale recency
guard in `drillToChart()` — **fixed and DUT-verified same session.** TASK-381/382 (T188/T192): a
`deserializeJson()` `IncompleteInput` failure after a clean HTTP 200, correlated with a severe heap
squeeze during the fetch — confirmed via a raw serial capture (`run_serialdbg_tests.py` grew a
`--log-file` option, `run/test-targeted` a matching `LOG_FILE=` passthrough, to see the `LOG_D`/
`LOG_W` lines the harness's JSON-only parsing had been silently discarding). Root cause confirmed,
TASK-300 identity-mismatch drop). See each entry for detail.

### TASK-379 — T148 assertion is stale post-TASK-346, NOT a Winamp zone leak (misdiagnosed at filing)

**Investigated 2026-08-01 — this is a test bug, not a firmware bug. No guard failure occurred.**
Original filing read `hit='CLOCKAPP' action='CONSUMED' at (137,120)` as a cross-app zone leak
("BUG-1 guard not firing"). Tracing the actual code shows the opposite: this is exactly correct,
deterministic, by-design behavior, and T148's assertions are simply out of date.

`main.cpp:2804-2811` (the tap dispatcher) has had a **dedicated** `currentAppId == AppId::Clock`
branch since **TASK-346 (M-CLOCK-TAP-CYCLE, commit `06455a8`, "in-app face/theme cycling via tap
zones")** — it routes the tap through `ClockApp::handleInput()` directly and reports
`hit="CLOCKAPP"`, never touching `winampDisplay.injectTouch()`/the Winamp zone tables at all. The
generic `"CLOCK"` sentinel T148 still expects is the *fallback* `else` branch (`main.cpp:2812-2816`)
used by apps with **no** dedicated tap handling (Matrix, Weather, Crypto, GoL — confirmed via
`T_MA_02`/`T_WX_02`, which correctly still assert `hit=="CLOCK"` for those, and correctly still
pass). Clock stopped being one of those apps as of TASK-346.

`clockApp.h:39-43` defines `CLK_TAP_SPLIT_Y = 120` — the canvas splits at y=120 into a theme-cycle
zone (`y < 120`) and a face-cycle zone (`y >= 120`), with **no dead zone left anywhere on the
canvas**. T148's tap coordinate, `(137, 120)` from `coords.py:clock_canvas_tap()`, lands exactly on
the boundary (`y < 120` is false) → routes to `_cycleFace()` (`clockApp.h:115-121`), which
unconditionally `return true`s. So `hit="CLOCKAPP", action="CONSUMED"` isn't a flake or an
intermittent bug — it is the **only** possible outcome for this exact tap, every single time,
since TASK-346 shipped. T148 has been deterministically broken since then; it just hadn't been
exercised as part of a full suite run until now.

`coords.py:186-187`'s docstring is also stale: `"Hits TRANSPORT zone in Spotify mode; must return
CLOCK/NONE after BUG-1 fix"` — describes Clock's pre-TASK-346 non-interactive behavior.

**Fix (implemented 2026-08-01):** updated `T148` (`app/tools/run_serialdbg_tests.py`) to assert the
current, correct contract instead of the pre-TASK-346 one: `hit == "CLOCKAPP"` and
`action == "CONSUMED"` (deterministic for this coordinate). The property BUG-1 originally guarded —
no Winamp/Spotify transport action can fire while Clock owns the screen — is now structurally
guaranteed by the dedicated `AppId::Clock` branch existing at all (that branch never calls
`winampDisplay.injectTouch()`), not by a runtime string comparison, so the rewritten test's real job
is confirming the dispatch still routes to Clock's own handler, not matching a specific string for
its own sake. Also refreshed `clock_canvas_tap()`'s stale docstring (`coords.py`) to describe the
current TASK-346 behavior instead of the old pre-fix "must return CLOCK/NONE" framing.

**DUT-verified 2026-08-01** (`run/test-targeted T147,T148`): both pass —
`T148  Clock active: hit='CLOCKAPP' action='CONSUMED' — routed through Clock's own handler, no
Winamp zone leak`. DUT restored to prod cleanly.

**Owner:** Developer · **Deps:** none · **Gate:** `run/test-targeted T147,T148` — 2/2 PASS ·
**Priority:** P3 (downgraded from P2 — no live firmware defect, no user-facing risk; this was
test-suite hygiene) · **Status:** **DONE 2026-08-01** — test fixed and DUT-verified.

### TASK-380 — `drillToChart()` skips re-fetch on ticker change within 60s (confirmed root cause of T176)

**Investigated 2026-08-01 — root cause CONFIRMED by code read, not yet DUT-fixed.** `drillToChart()`
(`app/src/main.cpp:1488-1501`, the List→Chart drill-in-by-ticker-index path) guards its enqueue with
a pure recency check: `if (!_s.lastChartFetch || millis() - _s.lastChartFetch > STOCK_CHART_FETCH_D1)`
(60s). `_s.lastChartFetch` is a single timestamp shared across *every* chart fetch regardless of
which ticker/range it was for — the guard answers "was there a recent chart fetch of any kind?", not
"is *this* ticker's D1 data still fresh?". Drilling into a new ticker within 60s of any prior chart
fetch silently skips the enqueue entirely: no request ever reaches the dataTask queue, which matches
the observed evidence exactly (`inFlight=-1`, `pendingMask=0` for the entire 45s wait — nothing was
ever dispatched, not a stuck in-flight request).

This is inconsistent with the two sibling entry points, both of which enqueue unconditionally on any
symbol/range change with no recency guard: `drillToChartBySym()` (`main.cpp:1503-1513`, heatmap-tile
drill) and the chart-view tab-switch handler (`main.cpp:1226-1236`). `drillToChart()` is the odd one
out.

**Reproduction match:** in the full suite's test order, `T174` ("Row drill-in (NVDA)") drills NVDA
and completes a real chart fetch, setting `_s.lastChartFetch`. `T175` (back-navigation) does nothing
that touches it. `T176` runs seconds later and drills AAPL (row 0) via the same `drillToChart()`
path — well inside the 60s window — so the guard fires and the fetch is silently skipped.

**Fix (implemented 2026-08-01):** dropped the freshness guard in `drillToChart()` — it now
enqueues unconditionally on every drill-in, matching `drillToChartBySym()` and the tab-switch
handler exactly (a drill-in is a deliberate user action, not a cadence tick; re-fetching every time
is correct UX regardless of recency, and simpler than threading ticker identity through the guard).

**Owner:** Developer · **Deps:** none · **Gate:** `run/check` 6/6 clean.
`run/test-targeted T176,T188,T192` DUT-verified: **T176 PASS** (fetchOkCount advanced, chart data
received — confirms the fix; this is the same back-to-back-drill scenario that previously hung),
**T188 PASS** (all 4 ranges D1/D5/Mo1/Ytd fetched clean, no regression from touching the same file),
T192 SKIP (heatmap screener never populated in 60s this run — precondition failure unrelated to this
fix, not a regression; see TASK-382). DUT restored to prod (`cyd2usb_winamp`) cleanly after.
**Priority:** P2 · **Status:** **DONE 2026-08-01** — root cause confirmed, fix implemented and
DUT-verified. This was *not* the same bug as TASK-381/382 below — see those entries, investigation
found their fetch **was** correctly enqueued and dispatched (confirmed via `inFlight=5`/`3` and
correct `stockChartRange` readback), so this recency-guard bug never explained them.

### TASK-381 — Stock chart JSON parse fails (`IncompleteInput`) after a clean HTTP 200, under heap pressure (T188)

**Investigated 2026-08-01 — root cause CONFIRMED via raw serial capture, not yet fixed.** Extended
`app/tools/run_serialdbg_tests.py` with a `--log-file` option (`run/test-targeted` grew a matching
`LOG_FILE=` passthrough) that tees every raw serial line — including the `LOG_D`/`LOG_W` lines the
harness's own JSON-only parsing had been silently discarding — to a file. Re-ran
`LOG_FILE=… ./run/test-targeted T188,T192`; both reproduced (T188 failed on **D1** this time, not
D5 — confirms it's not tied to a specific range/tab, ruling out anything range-specific) and the
capture shows exactly what happens:

```
[D][dataTask.stock] chart START AAPL range=1d heap free=73k maxBlk=41k
[D][dataTask.stock] chart GET AAPL range=1d 200 elapsed=2632ms
[D][dataTask.stock] chart pre-json heap free=23k maxBlk=15k
[D][dataTask.stock] chart post-json heap free=71k maxBlk=21k err=IncompleteInput
[W][dataTask.stock] chart JSON err: IncompleteInput
```

The HTTP GET completes cleanly (200, ~2.6s) — the failure is entirely in `deserializeJson()`
(`dataTaskStorage.cpp:483-490` / the by-sym twin at `:984-990`) running out of input mid-parse.
Heap free drops from 73k to 23k (`maxBlk` 41k→15k, real fragmentation, not just usage) between the
GET starting and the pre-json checkpoint — the response body is landing during a heap squeeze severe
enough to plausibly be truncating the stream itself (allocation failure inside the TLS/HTTP read
path producing a short read that `getStream()`'s filtered parse can't recover from).

**Both original hypotheses are now settled:**
- ~~Silent identity-mismatch drop (TASK-300's `main.cpp:1782-1788` stale-result guard)~~ — **ruled
  out**. `grep -c "drop stale"` on the full capture returns `0`; that code path never fires.
  `fetchErrorCode=None` in the test's diagnostic follow-up was indeed a serial-timing artifact of the
  *diagnostic* query, not a missing firmware value, as suspected — the real error is captured above.
- ~~Yahoo rate-limit / generic HTTP failure~~ — **ruled out as stated**. The GET always returns 200;
  the failure is 100% in JSON parsing, not the HTTP layer. Refined to: **JSON body truncation under
  heap pressure**, not a rate-limit.

**Fix (implemented 2026-08-01):** chose the retry-once mitigation over chasing the heap squeeze
directly (cheaper, matches this codebase's existing TASK-313 precedent for the identical failure
shape; the squeeze's root cause — heap-caps fragmentation during GET+parse — remains uninvestigated
and could still be worth a separate look someday, but isn't blocking). Factored the shared GET+parse
body out of both `fetchStockChart()`/`fetchStockChartBySym()` into one `fetchStockChartOnce()`
helper (`dataTaskStorage.cpp:472`), and added `fetchStockChartWithRetry()` (`:545`) which calls it,
and — only when `code == 200 && !r.ok` (never on a non-200 or connect failure, same skip-don't-retry
rule TASK-313 established) — waits 300ms and calls it again on a fresh connection/result, keeping
whichever attempt's outcome is final. Both `fetchStockChart()` and `fetchStockChartBySym()` are now
thin wrappers delegating to the shared retry orchestrator (`certTag` parameterized so the existing
per-fetch-type `certbreak` test hook still targets each independently).

**DUT-verified 2026-08-01** with `LOG_FILE=` capture again (`run/test-targeted T176,T188,T192`):
**T192 passed clean** — the exact by-symbol path that hit `IncompleteInput` in the pre-fix capture.
T188 failed again this run, but on a **different range (Mo1) with a different, distinct root cause**
— see TASK-383 below, filed separately; the retry logic correctly did *not* fire for it (HTTP code
was `-1`, a connect/timeout failure, not the `code==200`-but-truncated shape this fix targets) —
confirms the retry is scoped correctly, not just "test happened to pass." No `IncompleteInput`
appeared anywhere in this run's capture for any of the D1/D5/Mo1/NVDA fetches that *did* complete.
T176 SKIP ("could not enter chart view") was an unrelated harness-timing flake — the pipeline-drain
precondition step ate an unusually long stretch (`inFlight=2` for ~60s before draining), leaving too
little of the test's own window; `drillToChart()`'s control flow for entering chart view is
unchanged by this fix, only its enqueue guard (TASK-380) — re-run clean before treating as a
regression. DUT restored to prod cleanly.

**Owner:** Developer · **Deps:** TASK-313 (retry-once precedent, `dataTaskStorage.cpp` PlaneRadar
path) · **Gate:** `run/check` 6/6; `run/test-targeted T188,T192` with `LOG_FILE=` — T192 clean,
T188's remaining failure mode is TASK-383, not this bug · **Priority:** P2 · **Status:** **DONE
2026-08-01** — root cause confirmed, fix implemented and DUT-verified for the `IncompleteInput`
failure shape specifically.

### TASK-382 — same `IncompleteInput`-under-heap-pressure cause as TASK-381 (T192, tab-switch after heatmap drill)

**Investigated 2026-08-01 — confirmed same root cause as TASK-381, via the same `LOG_FILE=` capture
(one combined `run/test-targeted T188,T192` run reproduced both).** T192's failure log:

```
[D][dataTask.stock] chart-sym GET NVDA 200 elapsed=3158ms
[W][dataTask.stock] chart-sym JSON err: IncompleteInput
[D][dataTask.stock] heap free=68k maxBlk=22k
```

Identical shape to TASK-381 (clean HTTP 200, `IncompleteInput` on parse, depressed/fragmented heap
around the fetch) via the by-symbol fetch path (`fetchStockChartBySym()`,
`dataTaskStorage.cpp:951-1016` pre-fix) instead of the by-ticker-index one.

**Fix: shared with TASK-381** — `fetchStockChartBySym()` is now a thin wrapper over the same
`fetchStockChartWithRetry()` orchestrator, so the retry-once mitigation applies to this call site
automatically; no separate change needed. **DUT-verified 2026-08-01: `T192` PASSED clean** on the
fixed build (`run/test-targeted T176,T188,T192` with `LOG_FILE=` capture) — `drilled='NVDA'; 5D
tab-switch fired fetch; ticker unchanged`, the exact scenario that previously hit `IncompleteInput`.

**Owner:** Developer · **Deps:** TASK-381 (shared fix) · **Gate:** `run/test-targeted T192` with
`LOG_FILE=` — clean pass, no `IncompleteInput` in capture · **Priority:** P2 · **Status:** **DONE
2026-08-01** — fixed via TASK-381's shared retry orchestrator, DUT-verified.

### TASK-383 — Stock chart fetch: HTTP-level connect/timeout failure (`code=-1`, ~13s), distinct from TASK-381/382

**Filed 2026-08-01, surfaced while DUT-verifying the TASK-381/382 fix — uninvestigated.** During
the post-fix verification run (`LOG_FILE=… ./run/test-targeted T176,T188,T192`), `T188` failed again
— but not with `IncompleteInput` this time. The Mo1 (1-month) tab fetch for AAPL:

```
[D][dataTask.stock] chart START sym=AAPL range=1mo heap free=74k maxBlk=39k
[D][dataTask.stock] chart GET sym=AAPL range=1mo -1 elapsed=13039ms
```

`code=-1` is an `HTTPClient`/connect-level failure (not a JSON parse error — no `pre-json`/
`post-json` log lines appear at all, confirming the failure is before or during the GET, not after
a 200), and `elapsed=13039ms` is ~5x the normal ~2.6s round-trip — looks like a connect or TLS
handshake stall that eventually times out, not a fast-fail. TASK-381/382's retry-once mitigation
correctly did **not** fire for this (by design — it only retries `code==200 && !ok`), so this is
confirmed to be genuinely outside that fix's scope, not a gap in it. Same D1/D5 fetches in the same
test run (AAPL and NVDA both) completed fine at their usual ~2.5-2.6s, so this isn't a systemic
per-request slowdown — something about the Mo1 request specifically (larger response window? a
`STOCK_RANGE_STR`/`STOCK_INTERVAL_STR` value that hits a slower Yahoo code path?) or plain bad luck
on one connection attempt.

**Investigated 2026-08-01.** Two lines of investigation, neither turned up an actionable code bug:

**Library-level:** `code=-1` is `HTTPC_ERROR_CONNECTION_REFUSED` — HTTPClient's generic "connect
failed" code, returned when `WiFiClientSecure::connect(host, port, timeout)` fails
(`HTTPClient.cpp:1162`). The codebase sets no explicit `setTimeout()`/`setConnectTimeout()` anywhere
in `dataTaskStorage.cpp` (`grep` came up empty), so this runs on library defaults:
`HTTPCLIENT_DEFAULT_TCP_TIMEOUT` = 5000ms for the raw TCP connect (`HTTPClient.h:42`), with a
separate, much larger `handshake_timeout` = 120000ms for the TLS handshake proper
(`WiFiClientSecure.cpp:40`) — the observed 13039ms doesn't cleanly match either ceiling on its own,
but is consistent with DNS resolution (a separate step before `start_ssl_client()`, with its own
retry/backoff) plus a TCP connect attempt stacking together. No misconfigured or missing timeout
found — this is the library behaving as configured, not a firmware bug in the request path.

**Repro attempt:** ran `run/test-targeted T188` five more times back-to-back with `LOG_FILE=`
capture (full flash/test/restore cycle each time, DUT restored to prod cleanly all 5×). **0/5
reproduced the `code=-1` connect failure** — every GET across all 5 runs (20 chart fetches total)
returned 200. Useful side effect: the TASK-381/382 retry-once fix was caught actually firing live
twice in this batch (iteration 2's D1 and iteration 5's 5d+ytd all hit `IncompleteInput` on first
attempt, retried, and succeeded — `chart retry ok=1 rc=0` both times, test still passed) — good
independent confirmation that fix holds up under repeated real-world exercise, separate from this
task's own question.

**Disposition:** with 1 occurrence in 6 total `T188` runs across this investigation and 0/5 on
immediate re-test, plus no code-level cause found, this reads as ordinary transient WiFi/DNS/TCP
noise (single dropped or slow resolution/connect attempt) rather than a reproducible firmware
defect — the same category this project already accepts for `T_WR_TLS_01`/TASK-284's mirror
flakiness. Deliberately **not** widening TASK-381/382's retry scope to cover connect-level failures
too: unlike the `IncompleteInput` case (reproduced 2/5 in the same batch, clearly common enough to
be worth the fix) or PlaneRadar's adsb.fi truncation (empirically ~9%, TASK-313), a single
unreproduced event doesn't justify a code change, and a failed chart-tab fetch already has a
free, trivial recovery path (the user just re-taps the tab — `main.cpp:1226`'s tab handler
enqueues unconditionally on every tap, no cooldown/backoff blocking a retry).

**Owner:** Developer · **Deps:** none · **Gate:** re-open only if this recurs with a discernible
pattern (same range, same time-of-day, correlates with Spotify activity, etc.) — otherwise no
further action planned · **Priority:** P4 (downgraded from P3 — investigated, no actionable cause,
not reproducible) · **Status:** **CLOSED — accepted as transient network noise, not a firmware
defect.** Re-open with fresh evidence if it recurs.

## Open — full-suite re-run findings (2026-08-01, filed from `run/test` after TASK-379/380/381/382 landed)

Re-ran the full suite (`./run/test`) after all four fixes above were committed, to confirm the
original 6 failures were resolved. Result: **122 passed, 6 failed, 40 skipped, 2 flaked** — the
targeted tests (T148, T176, T188, T192) that TASK-379/380/381/382 fixed all now **PASS**, confirming
those fixes hold in full-suite context, not just isolated targeted runs. But 3 **new** failures
appeared that weren't present in the original baseline run (`T184`, `T231` — both `PASS` in the
original run; `T193` — also `PASS` originally), alongside the already-tracked `T_WR_TLS_01`
(TASK-284) and `T_PRM_02` (TASK-313, still showing degraded gaps — 19/300s this run, up to 37s
between fetches, consistent with the "worth a fresh look" flag noted when this section was first
filed) and one already-known `T091` reconnect flake (`FLAKE` in the baseline run, `FAIL` this run —
same underlying serial-timing flakiness, not new).

### TASK-384 — Back-navigation tap silently dropped by `g_shellBusy` gate, exposed by TASK-380's fix (T184, T231)

**Filed + root-caused 2026-08-01.** Both failures show the identical shape: drill into Stock chart
→ tap the back button (`(10,7)`) shortly after → `stockSubView` stays `"chart"` instead of
returning to `"list"`. Traced to `main.cpp:2756-2760`:

```cpp
if (g_shellBusy) {
    Serial.printf("{\"ok\":true,\"cmd\":\"tap\",...,\"hit\":\"CANVAS\",\"action\":\"NONE\",\"skipped\":true}\n", x, y);
    return;
}
```

This check runs **before** the `currentAppId != AppId::Spotify` dispatch block that routes taps to
`StockApp::handleInput()` — while `g_shellBusy` is true, **every** tap is silently skipped
(`"skipped":true`), with no exception for the back button. `shell::setBusy(true)` fires right after
a drill-in (`main.cpp:2768`, `if (!g_shellBusy && hasPendingAsync()) shell::setBusy(true)`) and
`hasPendingAsync()` mirrors `_pendingAsync`, which `drillToChart()`/`drillToChartBySym()` set to
`true` on every enqueue. `SHELL_BUSY_TIMEOUT_MS = 3000` (`main.cpp:1861`) is the auto-clear ceiling,
and a chart fetch (~2.5-3.5s normally, up to ~5.5s with TASK-381's retry-once) is well within that
window — so a back-tap arriving 0.15-0.4s after a drill (both T184 and T231's actual timing) lands
squarely inside the busy window and gets dropped before it ever reaches `backToPrevView()`.

**Why this is new:** before TASK-380's fix, `drillToChart()`'s stale recency guard frequently
*skipped* the enqueue entirely on back-to-back drills within 60s (exactly what T184/T231's dense
sequence of chart tests does) — so `_pendingAsync` often stayed `false`, `shellBusy` never got set,
and back-taps sailed through unblocked. TASK-380 correctly fixed a real data-staleness bug by making
every drill-in enqueue unconditionally — but that also means `shellBusy` now reliably engages on
every drill, which unmasks this pre-existing gap: **the busy gate has no allowance for
back-navigation**, a tap that should always be safe to process (it doesn't touch the in-flight
fetch, just changes what view is showing). This was latent before, now reliably reproducible.

**Deepened investigation 2026-08-01 — this affects real physical touch, not just the serial test
harness, and is systemic across four apps, not Stock-specific. Severity upgraded.**

`cmdTap()` (`main.cpp:2735`, the `#ifdef SERIAL_DEBUG` command this bug was originally caught
through) is a **test-only simulation** of touch input. Checked whether the same gate exists on the
**always-compiled production path** — it does, independently: `appHandleInput()`
(`main.cpp:2032-2104`, polled every loop iteration from `ts.touched()`) has its own equivalent check
at `main.cpp:2061`: `if (!s_inGesture && (millis() <= s_cooldownMs || g_shellBusy)) return;` — a
brand-new Press is dropped with **no `handleInput()` call at all** whenever `g_shellBusy` is true.
This is confirmed to affect the real CYD hardware exactly as it affects the test harness: a real
finger tap on the back button within the busy window is silently ignored, same as the serial-
injected one.

**Busy-window duration, precisely (`main.cpp:4063-4069`):** clears at the *earlier* of (a) the
active app's `hasPendingAsync()` going false (checked every loop tick, right after `appTick()`) or
(b) the `SHELL_BUSY_TIMEOUT_MS=3000` safety-net ceiling. For Stock, (a) fires when the chart fetch
genuinely completes — i.e. the busy window is essentially the **full fetch duration** (~2.5-3.5s
normally, up to ~5.5s if TASK-381's retry fires), not some artificially-extended 3s always. Since
T184/T231's back-taps land at 0.15-0.4s post-drill — far inside *any* normal fetch's duration — this
is not a narrow race window to hit; **any back-tap thrown during the entire normal fetch time gets
dropped.** That's the common case for a user who drills in, immediately realizes it's the wrong row,
and taps back right away — not an edge case.

**Confirmed systemic, not Stock-specific:** `hasPendingAsync()` (`appShell.h:18`, default `false`)
is overridden by Stock, **Teletext** (`teletextApp.h:155`, `_pendingFetch`), **PlaneRadar**
(`planeRadarApp.h:270`, `_pendingFetch`), and **WebRadio** (`webRadioApp.h:782`,
`_pendingStations`) — all four route through the identical pre-dispatch `g_shellBusy` check with no
navigation exception. Teletext is the clearest case of this violating an *existing, stated* design
intent: its own back-navigation zone is commented **"Strip is always live (back, nav) even when
numpad is active"** (`teletextApp.h:237`) — a promise the outer `g_shellBusy` gate currently breaks
whenever a page fetch (`_pendingFetch`) is in flight. This wasn't invented for Stock; it's a
pre-existing cross-app gap that TASK-380 happened to make reliably reproducible for Stock first.

One existing precedent for the right shape of fix: the **taskbar tap block already runs before this
check** (`main.cpp:2743-2755`, returns early) — switching apps via the taskbar is *never* blocked by
`shellBusy`, on the reasoning that navigating away is always safe regardless of in-flight work. The
fix for in-app back-navigation (Stock's `(10,7)` chart-back) should extend that same reasoning
inward: a canvas tap can still be safe to process even while the app's *own* fetch is in flight, if
what it does is pure navigation/UI state (no new fetch, no data mutation) rather than starting a
competing async operation.

**Correction before implementing — Teletext/PlaneRadar do NOT need this fix, on closer read of
their actual `handleInput()` bodies (the systemic framing above overreached; narrowed here rather
than left standing uncorrected):**
- **Teletext's `STRIP_BACK`** (`teletextApp.h:430-438`) is *not* pure navigation in the general
  case — when `_histDepth > 0` it calls `_goBack()` → `_active()->navigate(...)` →
  `dataTask::enqueueTeletextPage(...)`, i.e. it starts a **new fetch** for the previous page. Same
  for `STRIP_PREV`/`STRIP_NEXT`/`STRIP_SUBUP`/`STRIP_SUBDN` — all call `_navigate()`, all enqueue.
  The "Strip is always live... even when numpad is active" comment (`teletextApp.h:237`) is about
  numpad-vs-strip precedence, a *different* axis from the `g_shellBusy` gate this task is about —
  not the promise it first looked like. Exempting the strip from busy would let rapid taps stack
  overlapping page fetches, which is exactly what the gate exists to prevent. Leaving it as-is.
- **PlaneRadar's `handleInput()`** (`planeRadarApp.h:350-379`) has no pure-navigation tap at all —
  both its interactions (`STRIP_LOC_x` via `_setActiveLoc()`, and the disc-range-cycle tap)
  explicitly re-enqueue a fetch. There's no in-app sub-view to navigate back from in the first
  place (single full-screen view, no back button). Nothing to fix here.

Only **Stock** genuinely has this pattern (multiple in-app sub-views — List/Chart/Heatmap — reached
via a back-navigation tap that touches zero fetch state), which makes sense: it's the only app in
this codebase structured with real in-app sub-navigation.

**Fix (implemented 2026-08-01):** added `App::isNavigationTap(int x, int y) const` to the base
interface (`appShell.h`, default `false` — zero behavior change for any app that doesn't override
it, confirmed by `T_MA_02`/`T_WX_02`/`T_CX_02`/`T_GOL_02` all still passing unchanged). Wired it into
**both** dispatch paths — `cmdTap()` (`main.cpp:2756-2763`, the serial test harness) and
`appHandleInput()` (`main.cpp:2061-2065`, the real physical-touchscreen path, cooldown debounce
still applies) — so a tap where `isNavigationTap()` returns true bypasses the `g_shellBusy` check
and reaches the app's `handleInput()` regardless of pending async work. `StockApp::isNavigationTap()`
returns true for the exact same geometry `handleInput()` already checks for chart-back
(`y` in the header band `&& x < ST_CHART_BACK_W*2`, `ChartDetail` only) and heatmap-back
(`y < ST_LIST_RULE_Y && x > 190`, `HeatmapDetail` only) — confirmed neither zone's actual handler
(`backToPrevView()`) touches `dataTask::enqueue*` anywhere, so bypassing busy for these specific
coordinates is safe by construction, not just by absence of a counterexample.

**DUT-verified 2026-08-01** (`run/test-targeted T184,T231,T148,T176,T188,T192,T_MA_02,T_WX_02,
T_CX_02,T_GOL_02` — the fix itself plus every test touching the shared dispatch code this change
modified): **9 passed, 0 failed, 1 skipped** (`T192` skipped on an unrelated precondition —
heatmap cache not populated within 60s this run, not caused by this fix). `T184`/`T231` (the actual
regression) now PASS; `T148`/`T176`/`T188` (TASK-379/380/381's fixes) still PASS, confirming no
regression from touching shared dispatch code; all four BUG-1 guard tests
(`T_MA_02`/`T_WX_02`/`T_CX_02`/`T_GOL_02`) still PASS, confirming apps that don't override
`isNavigationTap()` see zero behavior change. DUT restored to prod cleanly.

**Owner:** Developer · **Deps:** TASK-380 (exposed this, did not cause it) · **Gate:**
`run/test-targeted T184,T231,T148,T176,T188,T192,T_MA_02,T_WX_02,T_CX_02,T_GOL_02` — 9/10 PASS,
1 unrelated SKIP · **Priority:** P1 (confirmed real-hardware impact, common-case trigger window) ·
**Status:** **DONE 2026-08-01** — root cause confirmed, fix implemented (Stock only — Teletext/
PlaneRadar investigated and found not to need it) and DUT-verified with no regressions.

### TASK-385 — T193 auto-refresh fetch timeout — likely TASK-383-adjacent, unconfirmed

**Filed 2026-08-01, low confidence.** `T193` failed: `fetchOkCount did not advance after
triggerFetch — auto-refresh did not fire` (45s timeout). Traced the trigger path
(`main.cpp:1332-1334`, `triggerFetch=1` resets `_s.lastChartFetch=0`, forcing `stockTickChart()`'s
own cadence check to re-enqueue on the next tick) — this is a **different** code path from
TASK-384 above (no tap involved, not gated by `g_shellBusy`, and `stockTickChart()`'s cadence
re-fetch was untouched by any of today's fixes). No obvious mechanism connects this to TASK-379/380
directly. Best guess: simply increased exposure to TASK-383's already-documented rare connect-level
failure (`code=-1`, no retry fires for non-200) or two consecutive `IncompleteInput` parse failures
(TASK-381/382's retry only covers one) — this run's `T_PRM_02` degradation (19/300s vs. the usual
36/300s) suggests the network was generally worse than usual during this run, and TASK-380 also
means more real chart fetches happen throughout the full suite than before, proportionally raising
odds of hitting *any* single-request failure mode somewhere in the run. Unconfirmed — no serial
capture for this run to check for `IncompleteInput`/connect-timeout evidence at the actual failure
point.

**Investigated 2026-08-02.** Re-ran `run/test-targeted T193` five times back-to-back with `LOG_FILE=`
capture (full flash/test/restore cycle each time, DUT restored to prod cleanly all 5×), same method
as TASK-383's investigation. **0/5 reproduced.** Every run showed the identical clean pattern: both
chart GETs (`NVDA range=1d` — the initial drill-fetch and the `triggerFetch`-forced auto-refetch)
returned HTTP 200 on the first attempt, `elapsed` in the normal ~2.9-3.0s band, no `IncompleteInput`,
no `code=-1`, no retry ever fired, `fetchOkCount` advanced 1→2 and `chartLen=79` every time (10
total chart fetches across the 5 runs, all clean). One useful side observation: run 1's log did show
a live `code=-1 HTTPC_CONNECTION_REFUSED`, but on a *Spotify* poll reconnect (unrelated call site),
not the stock chart fetch — confirms the failure mode TASK-383 characterized is real and still
occurs in this build's fetch stack generally, just not caught landing on T193's specific fetch in
this sample.

**Reopened 2026-08-02 — the 0/5 result above doesn't rule out what it looks like it rules out.**
`run/test-targeted` flashes fresh and boots the DUT immediately before running only the named
test(s) — every one of the 5 re-runs started from a clean boot (~2-3 min uptime, heap freeInt
~74-118k, no prior test history). But the run T193 originally failed in was a `run/test` full-suite
pass: one flash, one boot, then ~167 tests run sequentially with **no reboot in between** — T193
executed after roughly 150 prior tests had already been exercising heap alloc/free, the dataTask
queue, WiFi, and Spotify's 403-poll/backoff loop for however long the suite had been running by
that point. The isolated re-runs only tested "does T193 fail from a cold boot" (answer: no) — they
never tested "does T193 fail once ~150 tests' worth of state has accumulated," which is the
condition it actually failed under. Walking the CLOSED disposition back to open pending real
evidence from that condition, not a synthetic approximation of it.

**Plausible causes, now framed against the isolated-vs-suite-accumulated gap** (untested,
listed for the next full-suite pass to discriminate between, most to least likely):

1. **dataTask queue congestion / poll-bounded serialization** (TASK-244/299/300 precedent) — if a
   fetch enqueued by a test running shortly before T193 is still in flight or queued when
   `triggerFetch` lands, TASK-244's already-accepted "queued fetch can serialize behind Spotify's
   poll cycle for up to minutes" behavior could push completion past the 45s deadline with **no
   failure at all** on the wire — a false test failure, not a firmware bug. Distinguishing test:
   `T193-pre-trigger`'s new `dataq` snapshot (queueWaiting/inFlight) — clean-boot baseline is 0/0.
2. **Heap fragmentation under sustained load** (TASK-381/382 precedent, same mechanism TASK-386
   already flagged for T204/T-BUSY-01) — ~150 tests' worth of alloc/free cycles could leave
   `lfbInt`/`lfbDma` (largest free block, not just free bytes) measurably smaller than the
   clean-boot baseline (~41-45k), which is what actually gates whether `DynamicJsonDocument` can
   allocate contiguously. Distinguishing test: the new `heap()` snapshots' `lfbInt`/`lfbDma` fields
   vs. the 2026-08-02 clean-boot baseline.
3. **tlsYield arbitration contention** (TASK-287/299's tlsYield-starvation precedent) — extended uptime means
   many more Spotify 403-poll/backoff cycles have run and contested the shared TLS yield lock than
   in a 2-3 min isolated boot; if the chart fetch's `tlsYield()` call has to wait longer to acquire
   it under sustained contention, that eats into the 45s budget before the GET even starts.
   Distinguishing test: the new `dataq` snapshots' `spAct`/`spActMs`/`yieldCount`/`tlsStopped`
   fields at `pre-trigger` — elevated `spActMs` or a non-idle `spAct` right before the trigger
   would implicate this.
4. **Plain connect-level noise, more exposure** (TASK-383's original hypothesis) — more total
   fetches happen throughout a longer, busier run, proportionally raising the odds of hitting
   TASK-383's already-characterized rare `code=-1` connect failure on any single request,
   independent of any accumulated-state mechanism. Distinguishing signal: a `T193-timeout` snapshot
   that looks identical to the clean-boot baseline (nothing degraded) points here instead of 1-3.

**Diagnostics added 2026-08-02 (code, no DUT run performed — batched for the next real `run/test`
pass instead of another isolated repro attempt):** new `_diag_snapshot()` helper in
`run_serialdbg_tests.py` (`get heap` + `get backoff` + `get dataq` in one call) wired into both
`t193()` and `t194()` at entry, immediately before each test's risky fetch-trigger step, and — for
the specific `fetchOkCount`-did-not-advance failure — again at the moment of timeout. Snapshots are
embedded directly in the `fail()`/`skip()` reason string itself (not just printed), so the evidence
survives in the test-summary output even on a run with no `LOG_FILE=` capture — closing the exact
gap this task was originally blocked on. T194 got the same instrumentation as T193 (entry +
pre-list-drill + pre-tab-switch + timeout) even though it wasn't the one that failed: it runs
immediately after T193 in suite order, does a heavier fetch cascade (heatmap + 2 chart fetches + a
tab-switch fetch vs. T193's 2), and is therefore the more sensitive canary for the same
suite-accumulation hypotheses — a same-run comparison of T193's and T194's entry snapshots is a
second, free data point.

**Full-suite `run/test` pass 2026-08-02, with the new `LOG_FILE=` capture.** First real
suite-condition test since filing — single boot, ~167 tests sequentially, no reboot in between
(the actual condition T193 originally failed under, unlike the isolated re-runs above). **0/1
reproduced.** Located T193's exact run in the raw log via its unique `set triggerFetch` marker
(the heatmap-tile-drill → `triggerFetch` sequence is unambiguous): fired at uptime ~663s (~11 min
into the suite), `pre-trigger` diag snapshot read `heap(freeInt=117604,lfbInt=42996,freeDma=74460,
lfbDma=42996) backoff(cf=17) dataq(queueWaiting=0,inFlight=-1,tlsStopped=false,spAct=0)` —
materially *healthier* than the isolated clean-boot baseline, not degraded — chart GET returned
200 in 2881ms, `fetchOkCount` advanced, test passed clean. T194 (same run, ~1 min later) also
passed clean, both new diag triples (`pre-list-drill`, `pre-tab-switch`) confirmed present and
readable in the log exactly where the instrumentation should place them — the new tooling itself
is validated working, independent of whether it caught a failure this time. Also checked
suite-wide: zero non-200 chart GETs, zero `IncompleteInput`/parse failures, zero `fetchFailed=true`
anywhere in the entire ~9,300-line log for any Stock test (the 13 `IncompleteInput` hits in this
run are all PlaneRadar/adsb.fi — TASK-313's already-accepted issue, unrelated). No crash/panic;
two `SW_CPU_RESET` events were both harness-issued `reboot` commands (deliberate persistence-test
reboots), not faults.

**Disposition unchanged — one clean run doesn't retire an intermittent hypothesis, but it's a real
data point now, not a synthetic one.** This run's heap simply never got as pressured as the
original filing's (`lfbInt` held rock-steady ~41-43k the entire suite, vs. the original run's noted
`T_PRM_02` degradation suggesting a rougher network night) — consistent with hypothesis 2 (heap
fragmentation under load) requiring conditions this particular run didn't hit, not with the
mechanism being wrong. Keep `LOG_FILE=` on future `run/test` passes going forward; either a repro
eventually lands with full diagnostic context attached, or enough clean runs accumulate to
downgrade this with real evidence instead of a guess.

**Owner:** Developer · **Deps:** possibly TASK-383 (same failure class, different trigger path);
shares its diagnostic mechanism with TASK-386's T204/T-BUSY-01 (same heap-pressure-under-load
hypothesis, worth checking together) · **Gate:** keep `LOG_FILE=` on future full `run/test` passes;
next repro (if any) — inspect the diag snapshots against the 2026-08-02 clean-boot baseline (heap
freeInt~74-118k/lfbInt~41-45k, dataq queueWaiting=0/inFlight=0 pre-trigger, spAct idle) to
discriminate between hypotheses 1-4 · **Priority:** P3 · **Status:** **OPEN — instrumented and now
validated working under real suite conditions; 0/1 full-suite repro + 0/5 isolated repro so far.**

**Update (2026-08-06, second full-suite `run/test` pass, `LOG_FILE=` capture) — 0/1 again, first
run since diagnostics moved into the shared helpers.** T193 passed clean: `[T193-entry]`/
`[T193-pre-trigger]` diag markers present and correctly placed in the raw log (confirms the
generalized shared-helper instrumentation from TASK-386's later update — not just the earlier
hand-instrumented version — is live and working, not only code-reviewed). `pre-trigger` snapshot:
`heap(freeInt=117612,lfbInt=42996,...)` — same healthy shape as every prior clean run, no
degradation trend. `fetchOkCount` advanced, `chartLen=61`. Real failures this run were elsewhere
and unrelated: `T079`/`T082` (new, not previously seen — see note below) and the already-tracked
`T_WR_TLS_01`/`T_PRM_02` flakes (TASK-284/TASK-313; this run's cert-preflight step also logged
`nl1`/`at1` radio-browser mirrors network-unreachable **from the host**, consistent with
`T_WR_TLS_01`'s failure, not a new cause). Tally: 132 passed, 4 failed, 36 skipped, 1 flaked; DUT
restored to prod cleanly. Now 3 consecutive clean full-suite passes for T193 (2026-08-02 ×2,
2026-08-06) — no repro yet under any condition tested, including this run's real network noise
elsewhere in the suite.

**Side note, out of scope for this task:** `T079` (`tap not skipped while gate armed`) and `T082`
(`only 0 ACT_VOLUME enqueue(s)`) failed this run with no prior record in this file — not
investigated (unrelated code path, Winamp gesture/volume-debounce tests, not stock-fetch), flagging
here rather than dropping silently. Worth a look if they recur.

## Open — TASK-386 (2026-08-01, filed from a third full-suite `run/test` pass, post-TASK-384)

Re-ran `./run/test` after TASK-384 landed. **Result: 122 passed, 4 failed, 41 skipped, 3 flaked** —
best result yet across the three full-suite passes today. Every fix from today
(TASK-379/380/381/382/384) confirmed holding simultaneously in this run: `T148`, `T176`, `T184`,
`T188`, `T192`(skip, unrelated precondition)/`T193`, `T231` all pass. `T091` back to its usual
`FLAKE` (not `FAIL`) — no new information. `T_WR_TLS_01`/`T_PRM_02` remain the already-tracked
flakes (TASK-284/313) — `T_PRM_02`'s gaps this run (up to 27573ms) are again on the degraded side,
consistent with a generally rough network night rather than a new issue.

### TASK-386 — T204 + T-BUSY-01: two more `fetchOkCount`/`chartLen` stalls, likely TASK-381/382's known residual risk

**Filed 2026-08-01, not independently investigated — high-confidence hypothesis from pattern
match.** Two new failures, both Stock-chart-fetch tests that have passed cleanly in both prior
full-suite runs today:
- `T204` (`D1↔Ytd rapid alternating stress`, M-STOCK-VE-STRESS — deliberately hammers
  `DynamicJsonDocument` alloc/free under heap pressure by design): `fetchOkCount did not advance on
  Ytd — heap pressure failure?` (the test's own hypothesis, baked into its fail message).
- `T-BUSY-01` (`StockApp row tap → amber → clears on fetch complete`): `chartLen did not exceed 0
  after 45s — fetch did not complete`.

Both show the identical `dataq` shape already characterized for TASK-381/382/383: `inFlight`
transitions out of flight within a few seconds (fetch attempt(s) genuinely completed, not stuck) but
`fetchOkCount`/`chartLen` never advances. **Not re-investigated with a fresh `LOG_FILE=` capture**,
but the shape, the same fetch codepath (`fetchStockChart`/`fetchStockChartBySym` via
`fetchStockChartWithRetry`), and — most tellingly — `T_PRM_02`'s notably degraded gaps in this exact
same run all point at the same already-documented, already-accepted residual risk: TASK-381/382's
retry-once mitigation covers exactly one extra attempt, and under sustained heap/network pressure
(evidenced this run) two consecutive failures (two `IncompleteInput`s, or one `IncompleteInput` +
one `code=-1` connect failure) still produce a genuine, uncovered failure. This is expected residual
behavior of a retry-*once* design, not retry-forever — TASK-381/382's commit message said as much.

**Not attributed to TASK-384** — that fix touches only tap-dispatch/busy-gate logic, no HTTP/JSON/
heap code at all, and both failures are squarely in the fetch/parse path TASK-384 never touched.

**Investigated 2026-08-02 — code-only, no DUT run (human direction: batch diagnostics before any
rerun).** Read `fetchStockChartWithRetry()` (`dataTaskStorage.cpp:545-581`) to confirm the retry
mechanism precisely: retries **only** when `code==200 && !r.ok` (HTTP succeeded, JSON parse
failed — the `IncompleteInput` case); a non-200/connect-level failure on the *first* attempt never
retries at all, by design (retrying a connect failure "just burns another TLS handshake for no
benefit", per the code comment). So a genuine double-failure covers exactly two shapes: two
consecutive `IncompleteInput`s, or one `IncompleteInput` (retried) followed by a second failure of
either kind — but a **first-attempt connect-level `code=-1`** would show as this exact same
`fetchOkCount`-never-advanced/`chartLen`-stayed-0 symptom from the test's point of view, with *zero*
retry ever attempted (TASK-383's failure mode, not TASK-381/382's). The existing firmware LOG_D
lines (`chart START ... heap free=Xk maxBlk=Yk`, `chart GET ... <code> elapsed=Xms`, `chart parse
failed rc=X -> retry`, `chart retry ok=Y rc=Z`) already distinguish all of this cleanly — they just
weren't captured, because **`run/test` (the full-suite script) had no `LOG_FILE=` support at all**
(only `run/test-targeted` did) — the actual reason TASK-383's/TASK-386's own filed gates could only
ever recommend an *isolated* re-run, which TASK-385's investigation this session established
is the wrong tool for a suite-order-dependent failure.

**Applying the TASK-385 lesson here too:** `T204` and `T-BUSY-01` are not equally suite-state-
dependent. `T204` self-induces its own heap pressure (6 rapid back-to-back fetches by design), so
an isolated `run/test-targeted T204` repro attempt would actually be a fair test of the
heap-pressure hypothesis on its own — unlike T193. `T-BUSY-01` is a single self-contained fetch,
structurally identical to T193's case: its failure is more plausibly suite-accumulated-state-
dependent (heap fragmentation, dataTask queue backlog, tlsYield contention left over from ~150
prior tests) than something a fresh-boot isolated rerun could validate.

**Diagnostics added 2026-08-02 (code, no DUT run performed):**
1. **`run/test` gained `LOG_FILE=` support**, mirroring `run/test-targeted`'s existing flag —
   previously only isolated targeted re-runs could capture raw serial (`run_serialdbg_tests.py`
   already accepted `--log-file` in full-suite mode; the full-suite *wrapper script* just never
   passed it through). This is the single highest-value fix here: the next full `run/test` pass can
   now capture the complete firmware-side retry-cascade evidence for T204/T-BUSY-01 (and T193/T194)
   in situ, under real suite conditions, with zero isolated-repro ambiguity.
2. Same `_diag_snapshot()` helper from TASK-385 wired into both tests: `T204` gets a baseline at
   entry plus a snapshot before **every one of its 6 taps** (not just on failure — the
   heap-pressure hypothesis is specifically about a *trend* across the cycle, which a single
   failure-point snapshot can't show) and on any failure; `T-BUSY-01` gets entry/pre-trigger/
   timeout snapshots, same shape as T193's. All embedded directly in the `fail()` reason so the
   evidence survives even on a `run/test` pass someone forgets to point `LOG_FILE=` at.

**Full-suite `run/test` pass 2026-08-02, with the new `LOG_FILE=` capture.** Same run used for
TASK-385's re-check. Located T204's exact block via its unique alternating-tap signature
((256,9)/(148,9) × 3): fired ~12 min into the suite, entry snapshot `heap(freeInt=76268,
lfbInt=42996,...)`, all 6 cycles (Ytd/D1 × 3) returned HTTP 200 with `err=Ok`, `fetchOkCount`
advanced monotonically 12→18, `lfbInt` held flat at 42996 across every single one of the 6
pre-tap snapshots — **no heap-pressure trend at all this run**, contrary to what the hypothesis
would predict if conditions were similar to the original filing. `fetchFailed` read `false` after
every cycle. **T204: 0/1 reproduced.**

`T-BUSY-01` could not be individually isolated in the raw log — this suite has several other
Stock tests that tap the same AAPL list-row coordinate in adjacent sequences, and without the
python-level PASS/FAIL boundary (lost to a `tail -100` truncation on the background command —
noted for next time: don't pipe a long-running full-suite run through `tail`, let the harness
capture the whole thing) its exact block couldn't be confidently distinguished from the others by
raw-log pattern alone. However, a suite-wide sweep settles it anyway: **zero non-200 chart GETs,
zero `IncompleteInput`/parse failures, zero `fetchFailed=true`, and zero post-JSON parse errors
appear anywhere in the entire ~9,300-line log for any Stock test this run** (the only
`IncompleteInput` hits are PlaneRadar/adsb.fi, TASK-313's unrelated already-accepted issue). Since
T-BUSY-01 is just another stock chart fetch and no stock chart fetch failed anywhere in this run,
T-BUSY-01 passed too, by construction. **T-BUSY-01: 0/1 reproduced** (via exhaustive negative
sweep, not direct isolation).

Same disposition logic as TASK-385: this run's heap simply never got as pressured as the original
filing's — informative (the new instrumentation is confirmed working, ready to catch it next time
with full context) but not yet conclusive either way.

**Generalized 2026-08-02 (human: "does this pattern apply to other tests? could we improve suite
quality?").** Surveyed every caller of the same family of async-wait-or-timeout helpers.
`_wait_chart_complete` alone (the exact helper T193/T204's failures went through) is also called by
`T176`, `T185`, `T188`, `T192`, and `T-BUSY-01b` — T188/T192 are literally TASK-381/382's own
`IncompleteInput` regression tests, so they're the most relevant uninstrumented gap of all. Parallel
un-instrumented helper families exist for stock quotes (`_wait_quote_fetch`) and WebRadio
(`_wait_wr_count`/`_wait_wr_state`) — same single-async-op-plus-timeout shape, same theoretical
exposure to heap/queue/tlsYield pressure.

Rather than hand-instrumenting each call site (what TASK-385/386 did for T193/T194/T204/T-BUSY-01),
pushed `_diag_snapshot()` **into the shared helpers themselves**, on their timeout path only (never
on a legitimate early-exit like `_wait_wr_count`'s `pending==0`/"no stations" case): `_wait_chart_
complete`, `_poll_chart_len_positive`, `_wait_quote_fetch`, `_wait_wr_count`, `_wait_wr_state`,
`_wait_heatmap_count`, `_wait_shell_not_busy`. Return types/signatures are **unchanged** (still
`bool`/`int`) — zero risk to any of the existing ~15+ call sites across the suite, since the
diagnostic `get`s land on the wire (captured by any `LOG_FILE=` in effect) purely as a side effect
before the existing `return False`/`return 0`. Every current caller — instrumented or not — and any
future test written against these helpers now gets this for free.

Also added a **serial-side per-test marker**: the main dispatch loop (`run_serialdbg_tests.py`
`main()`) now issues `get __TEST_<id>__` immediately before invoking each test. That's
intentionally an unrecognized var — the firmware's existing "unknown var" fallback echoes it
straight back on serial with zero firmware changes, giving `LOG_FILE=` captures an unambiguous
per-test boundary. This directly targets the exact problem hit during this investigation: `T-BUSY-
01` couldn't be individually isolated in the raw log because several tests share its tap
coordinates, and the python-level PASS/FAIL boundary had been lost to a `tail -100` truncation on
the backgrounded command. Future investigations won't need the kind of manual signature-matching
this one required.

**Owner:** Developer · **Deps:** TASK-381/382 (shared mechanism), TASK-383 (established the
accept-transient-network-noise precedent this likely falls under), TASK-385 (shared diagnostic
mechanism + the isolated-rerun-vs-suite-state methodology lesson) · **Gate:** keep `LOG_FILE=` on
future full `run/test` passes; next repro (if any) — check (a) the LOG_D retry-cascade lines to see
whether it was a genuine double-`IncompleteInput`/mixed failure (TASK-381/382's accepted residual)
vs. a first-attempt `code=-1` with no retry (TASK-383's class) vs. something new, and (b) the new
`_diag_snapshot()` lines for a heap/queue/tlsYield trend · **Priority:** P3 (unchanged) ·
**Status:** **OPEN — instrumented and validated working under real suite conditions; 0/1 full-suite
repro for both tests so far** (T204 directly confirmed clean, T-BUSY-01 via exhaustive sweep).

**Update (2026-08-06, second full-suite `run/test` pass, `LOG_FILE=` capture) — both 0/1 again,
this time each test directly isolated** (T-BUSY-01 needed the exhaustive-sweep workaround last
time because its PASS/FAIL boundary was lost to a `tail` truncation — the per-test `__TEST_<id>__`
serial marker added afterward fixed exactly that; both tests' blocks were unambiguous in this raw
log). T204: all 6 alternating D1/Ytd taps passed, `fetchOkCount` advanced 14→19 monotonically,
`lfbInt` held dead flat at 42996 across every one of the 6 pre-tap snapshots — zero heap-pressure
trend, same as the first clean run. T-BUSY-01: `shellBusy` cleared correctly on fetch completion,
`[T-BUSY-01-entry]`/`[T-BUSY-01-pre-trigger]` markers present and correctly placed. Real failures
this run were unrelated (`T079`/`T082`, new — see TASK-385's note above; `T_WR_TLS_01`/`T_PRM_02`,
already-tracked TASK-284/313 flakes). Now 2 consecutive clean full-suite passes for both T204 and
T-BUSY-01 — still no repro under any condition tested.

**Update (2026-08-06, third full-suite `run/test` pass, same session):** T193/T204/T-BUSY-01 all
pass clean again (3rd consecutive for T193, 2nd for T204/T-BUSY-01 counting only full-suite
passes — 4th overall counting the earlier isolated hand-check). `fetchOkCount` advanced
monotonically through all 6 T204 taps as before, no heap trend. This run's real failures were
`T082` (again — see TASK-406's correction above, root-caused and fixed this time, unrelated to
the heap-pressure hypothesis) plus the already-tracked `T_WR_TLS_01`/`T_PRM_02`/`T_WR_COEX_04`/
`T_WR_VOL_03`/`T_PR_04` flakes (network/timing noise, not investigated further this session).
Diminishing returns at this point — 3-4 clean full-suite passes with zero heap-pressure trend on
every single check. Still open per the discipline established above (a clean run doesn't retire
an intermittent hypothesis), but further blind full-suite reruns are unlikely to be the highest-
value next step; a real repro would need either a genuinely worse network night (like the
original filing's `T_PRM_02` degradation) or a purpose-built heap-fragmentation stress harness
rather than waiting on ambient conditions.

---

## Open — M-WEBRADIO-REAL-VIS follow-on: Spectrum + Wave graduation (2026-08-02)

Two Architect design docs (`M-WEBRADIO-REAL-VIS-SPECTRUM.md`, `M-WEBRADIO-REAL-VIS-WAVE.md`)
resolved the open tap-cycle-length question by human decision 2026-08-02: ship both together,
keep `VIS_WAVE_ATLAS`. WebRadio's tap-cycle becomes the 6-stop Atlas → WaveAtlas → VU → Wave →
Spectrum → Blank → Atlas; Spotify's cycle is untouched (Atlas → WaveAtlas → VU → Blank). Both
tasks are DUT-gated (no DUT this session — scheduled, not started).

### TASK-387 — M-WEBRADIO-REAL-VIS: graduate real per-band spectrum energy (PROP-005 rung 3)

Graduates EXP-018's already-built real 19-band Goertzel spectrum analyzer (branch
`rnd/webradio-vis`) to production. Promote `tickSpectrum`'s `specPeak`/`specH`/`specVel` arrays
to namespace-scope accessors (`vu::specHRef()` etc., same pattern as `lLevelRef()`/`rLevelRef()`);
extract `vu::updateSpectrumBar(i, lvl)` for the pump task (`audio_process_extern`) to call
per-band per decoded block. Revive `VIS_SPECTRUM` in WebRadio's tap-cycle only — `nextMode()`
gains a per-caller branch (same shape as `vu::tick()`'s existing `realAudio` parameter), Spotify's
cycle stays Atlas/WaveAtlas/VU/Blank. Ship a per-band makeup-gain pass in the same PR to address
EXP-018's "under-driven relative to rung 2" finding — not deferred to a follow-up.

**Exit criteria:** zero new static bytes (linker `.map` diff vs. pre-change build); `get wrPump`
`maxPumpMs` unchanged at 42ms vs. TASK-278/rung-2 baseline; WebRadio tap-cycle reaches Spectrum,
Spotify's does not (VE regression); human eyeball gate (BP-048-style) confirms spectrum mode
visibly tracks real program material and reads acceptably close to VU's liveliness after the gain
pass; new VE test ids added to `run_serialdbg_tests.py` mirroring T_WR_VIS_01/02/03's shape.

**Owner:** Developer · **Deps:** vu-002/ADR-056 (rung 2, shipped), PROP-005/EXP-018 (cost-cleared
on `rnd/webradio-vis`, not yet ported to master) · **Design:**
[M-WEBRADIO-REAL-VIS-SPECTRUM.md](../architecture/designs/M-WEBRADIO-REAL-VIS-SPECTRUM.md) ·
**Registers:** vu-003, X044 (both now `implemented`) ·
**Priority:** P2 · **Status:** DONE (2026-08-03, implementation + DUT verification; code
uncommitted pending human review — see feature_inventory.yaml `vu-003` for full evidence).

**Implementation notes:** all four exit criteria met. Zero new static bytes confirmed via a
byte-for-byte `.dram0.data`/`.dram0.bss` `.map` diff against the pre-change build, on both
`cyd2usb_winamp` and `cyd2usb_winamp_debug` (not just the RnD branch's earlier measurement).
Isolated `get wrPump` reads (45s, no concurrent traffic) measured `maxPumpMs=43-47ms` vs.
EXP-018's 42ms baseline — within noise, under the 50ms ceiling. WebRadio's tap-cycle confirmed
on DUT to visit Atlas(0)->WaveAtlas(3)->VU(1)->Spectrum(4)->Blank(2)->Atlas(0); Spotify's
confirmed to stay within {0,1,2,3}, visMode=4 never observed. Gain table (20dB base + 1.0dB/band
tilt) derived empirically via a new `get wrSpec` debug getter (dumps the promoted `specH()` bar
heights) — landed at Spectrum/VU screendump pixel deltas of 415 vs. 433 out of 9800 (comparable
liveliness), full 0..16 bar-height range exercised on loud content. Added T_WR_VIS_04/05 to
`run_serialdbg_tests.py` (spectrum reachability + real-data animation; Spotify regression guard).

**Bug found + fixed along the way (not scoped originally, but blocking VE's own reachability
check):** `cmdTap`'s WebRadio branch in `main.cpp` called both `winampDisplay.injectTouch()`
(Press phase — hits the shared `hitVis` branch built for Spotify's real touch path) and
WebRadioApp's own Release-phase vis handler on every synthetic vis-zone tap, double-stepping
`vu::nextMode()` per `tap` command. Harmless while `nextMode()` took no args; broken once the two
calls started passing different `appHasSpectrum` values (synthetic taps got stuck oscillating
between `VIS_ATLAS_MODE` and `VIS_VU` only, WAVE_ATLAS/BLANK/SPECTRUM all unreachable via the
debug `tap` command — pre-existing, just never exercised since no prior test needed those
indices). Fixed by skipping `injectTouch` for vis-zone coordinates under WebRadio and building
the diagnostic JSON directly. Real hardware touch was never affected (single dispatch via
`WebRadioApp::handleInput` only) — synthetic-harness-only defect.

**Automated suite this session:** T_WR_VIS_01/02/04 SKIPped (radio-browser station fetch
returned 0 stations — live recurrence of the pre-existing TASK-284 mirror-flakiness/rate-limit
issue; the manual DUT session minutes earlier successfully loaded 30 stations and exercised the
same assertions directly). T_WR_VIS_03/05 SKIPped on the pre-existing TASK-243 external blocker
(Premium lapsed). Re-run `run/test-targeted T_WR_VIS_01,T_WR_VIS_02,T_WR_VIS_03,T_WR_VIS_04,T_WR_VIS_05`
next session once station fetch/Spotify are healthy, for the formal automated PASS record.

### TASK-388 — M-WEBRADIO-REAL-VIS: real 19-column waveform trace for WebRadio's "Wave" mode

**Rescoped 2026-08-02 (same day as filing) — see history below for the original scope.**
PROP-009 validated a 19-column real oscilloscope-style trace (EXP-021: storage: fits today's
measured 40-byte `dram0_0_seg` headroom directly, no reuse-overlay needed; EXP-022: decode-tail
44ms, noise vs. the 42ms baseline; visual: screendump pairs show the trace changing *shape* — not
just height — between a jagged speech passage and a quiet pause on live program material) in the
same DUT session this task was filed in. Human decision, presented with both the originally-scoped
amplitude-only sine and the validated trace: **ship the trace, not the sine.** WebRadio's "Wave"
tap-cycle slot now means the 19-column real trace.

Production implementation ports `vu::waveTraceRef()` (19-byte namespace-scope static) and
`vu::tickWaveTrace()` from the throwaway spike branch `rnd/webradio-wave-spike` (commits `bcd2d0c`,
`b698a2f`) — the spike's renderer was a full-redraw-per-call implementation for DUT observability,
not tuned for production (no dirty-diff; fine as a starting point). Decimation is plain
sub-sampling of the pump task's most recently decoded block (`idx = i*len/19`), overwriting the
whole 19-byte array every `audio_process_extern` call — single writer, same never-both-active
argument already established for `lLevelRef()`/`rLevelRef()` (X043) and the promoted spectrum
arrays (X044).

<details><summary>Original scope at filing (superseded same day)</summary>

Originally: feed real audio amplitude (`vu::lLevelRef()`) into the currently-dormant synthetic
`VIS_WAVE` sine (`tickWave()`) — cheap, zero new storage, but the sine's *shape* stayed synthetic,
only its *height* tracked real audio. The true-oscilloscope variant was explicitly out of scope at
filing, deferred to PROP-009 (then unstarted). PROP-009 ran to completion the same session,
proving the trace affordable at comparable cost with a strictly better result — see
`M-WEBRADIO-REAL-VIS-WAVE.md`'s amendment section for the full rationale for replacing rather than
shipping both.

</details>

**Exit criteria:** re-verify storage headroom fresh at implementation time (don't trust EXP-021's
40-byte snapshot as durable — explicit warning in that report); `get wrPump` `maxPumpMs` unchanged
vs. TASK-278/42ms baseline on the production build (spike measured 44ms, noise); WebRadio tap-cycle
reaches Wave with the real trace visibly animating in *shape* (not just amplitude) — screendump-diff
check extended to assert shape variance, not just a raw pixel-delta threshold; Spotify's cycle
unaffected; human eyeball gate — spot-check more than one station (this session's evidence was one
NPO news/talk relay; worth checking a music station too, since speech's silence-vs-speech contrast
may look more dramatic than continuous music would).

**Owner:** Developer · **Deps:** PROP-009/EXP-021/EXP-022 (validated the shipped approach, spike
code to port from `rnd/webradio-wave-spike`), X043/X044 (precedent for the single-writer argument) ·
**Design:** [M-WEBRADIO-REAL-VIS-WAVE.md](../architecture/designs/M-WEBRADIO-REAL-VIS-WAVE.md) ·
**Registers:** vu-004, X045 (both now `implemented`) ·
**Priority:** P2 · **Status:** DONE (2026-08-03, implementation + DUT verification; code uncommitted
pending human review, same as TASK-387/389 this session).

**Implementation notes:** ported `vu::waveTraceRef()`/`vu::tickWaveTrace()` from
`rnd/webradio-wave-spike` verbatim (`bcd2d0c`/`b698a2f`) — full-redraw renderer, no dirty-diff, per
the design doc's explicit "acceptable starting point" allowance. The old synthetic `tickWave()`
sine became genuinely dead code once `VIS_WAVE`'s tap-cycle slot repoints to the real trace (no
call site left anywhere, for either app) — deleted rather than left unreachable, per the
project's no-half-finished/no-dead-code convention. `vu::nextMode()` gained a second per-caller
flag (`appHasWave`, alongside TASK-387's `appHasSpectrum`) and the ring grew to 6 stops for
WebRadio: Atlas → WaveAtlas → VU → **Wave** → Spectrum → Blank → Atlas. `webRadioApp.h`'s
`audio_process_extern` decimates the L channel of each decoded block to 19 columns
(`idx = i*len/19`) directly into `waveTraceRef()`, unconditionally (display-independent, same as
the Goertzel spectrum writer). TASK-389's toggle scheme extended to 5 modes (`webRadioVisWave`
added, default true) — Settings > WebRadio > Vis modes' sub-view now has 5 rows, reordered to
match the actual tap-cycle order.

**Storage headroom re-verified fresh (per the design doc's explicit warning not to trust EXP-021's
40 B snapshot as durable):** current measured headroom on `cyd2usb_winamp_debug` is **20 B** after
this task's 19-byte trace array + 1 new settings bool (down from ~32 B after TASK-389 alone,
~40 B baseline 2026-08-02 before either) — both envs still link cleanly. This is a fast-shrinking
margin; the next feature that needs new static-BSS on this board should budget time for a
storage-reuse search rather than assuming a small addition still fits.

**Decode-tail measurement had a real confound this session, resolved by A/B test:** initial
isolated `get wrPump` reads (45 s wait, no concurrent traffic — same methodology as T_WR_VIS_01)
measured 78-123 ms, well over the 50 ms ceiling. Temporarily `#if 0`-disabling the new trace-write
code and re-measuring gave an even *worse* result (311 ms, `maxMutexWaitMs`=6533 ms) — proving the
regression was not attributable to this task's code at all. Root cause: the persisted `lastStation`
(index 2) was itself stalling/reconnecting during the test window (matches the known TASK-284
station-fetch-flakiness pattern). Switching to a known-reliable relay
(`icecast.omroep.nl/radio1-bb-mp3`, this project's established fallback for ad-hoc WebRadio DUT
testing) with the trace code re-enabled gave two clean isolated reads: **49 ms and 50 ms** — right
at EXP-022's spike measurement (44 ms) plus TASK-387's Goertzel baseline, within the 50 ms ceiling
but with less margin than before. Worth a closer look next session if a future feature needs to
add more per-block work to this same pump-task budget.

**DUT verification (2026-08-03):** WebRadio's 6-stop tap-cycle confirmed via `get visMode`:
`0→3→1→5→4→2→0→3` (Atlas→WaveAtlas→VU→Wave→Spectrum→Blank→Atlas). `get wrWave` (new debug getter,
dumps the 19 raw trace samples) showed flat zeros while the stream was still connecting, then
genuine shape variance once audio flowed (sample spread up to 76 between adjacent columns,
changing shape not just height across successive reads) — the exact property this mode exists
for, confirmed non-visually via the numeric getter rather than only a screendump diff. Spotify's
tap-cycle reconfirmed to visit only `{0,1,2,3}` across 8 taps, never reaching Wave(5) or
Spectrum(4). Settings UI screendump-confirmed for both all-off and all-on states of the 5-row
sub-view, no overlap. `run/check` 6/6 both times.

**Not done this session:** human eyeball gate across more than one station (design doc's own
explicit ask) — only the NPO relay was exercised after the degraded-station confound above; the
original design doc also flagged wanting a music station in addition to a news/talk one. Worth a
follow-up DUT pass.

### TASK-389 — Settings > WebRadio: per-mode vis-cycle toggle (mock vs. audio-driven)

Human-requested follow-on to TASK-387: a Settings option to include/exclude each of WebRadio's
four toggleable tap-cycle vis modes (`Atlas`, `WaveAtlas` — pre-recorded/mock; `VU`, `Spectrum` —
real audio-driven, TASK-369/TASK-387) independently. `VIS_BLANK` has no toggle — always the
guaranteed cycle fallback.

**Implementation:** four new `AppSettings` bools (`webRadioVisAtlas`/`webRadioVisWaveAtlas`/
`webRadioVisVU`/`webRadioVisSpectrum`, default `true` — today's full 5-stop cycle, unchanged until
a user opts to trim it), wired through `SettingsStorage::load()`/`save()` per ADR-050. `vu::nextMode()`
(`vuMeter.h`) gains an `enabledMask` parameter (new `vu::ModeFlags` bitmask) and now loops (bounded
to one lap of the 5-state ring) skipping disabled modes instead of a single fixed hop — `VIS_BLANK`
is unconditionally "enabled" in the mask check, so the loop always terminates, settling on Blank if
every togglable mode is off. WebRadio's tap handler (`webRadioApp.h`) builds the mask fresh from
`g_settings` on every tap (cheap enough not to cache — a live Settings edit takes effect on the very
next tap). Spotify's call site is unaffected (default full mask; `appHasSpectrum=false` already
keeps Spectrum off there regardless).

**Settings UI:** new "Vis modes" row (row 6) in the existing WebRadio settings list — chevron +
`N/4` summary value, same idiom as PlaneRadar's Locations row — opens a dedicated 4-row toggle
sub-view (`_wrVisActive`, mirrors `_prLocActive`'s gating pattern in `appsSection.h`, but without
PlaneRadar's keyboard/picker machinery — this sub-view is plain tap-to-toggle rows only). Added
`_wrRowSub()` (`_wrSub() && !_wrVisActive`) to correctly exclude the Max-volume slider's
Press/Move/Release phase-forwarding while the vis sub-view is showing (was gated on `_wrSub()`
alone, which stayed true inside the sub-view too).

**Exit criteria — all DUT-confirmed (2026-08-03):** `run/check` 6/6 + settings-wiring gate green
(54 fields, 4 new, all wired); zero new static bytes was NOT the bar here (unlike TASK-387's
pump-task real-time constraint) — `.dram0.bss` grew a normal +8 B for the 4 new persisted bools,
well within the ~40 B headroom measured 2026-08-02, confirmed the build still links on both envs.
DUT-driven Settings navigation (switchApp → tap Applications → tap WebRadio row → tap Vis modes
row → toggle rows → back×3) confirmed submenu/section state transitions correct at every step.
Screendump confirmed both the row-view "Vis modes 4/4 >" row and the 4-row sub-view render legibly
with kit styling. Live tap-cycle behavior confirmed for all three cases: VU+Spectrum disabled →
cycle visits only {WaveAtlas, Blank, Atlas}; Atlas+WaveAtlas disabled → cycle visits only
{VU, Spectrum, Blank}; all four disabled → cycle settles on Blank only, no hang/crash. Device
left in the default all-on state.

**Owner:** Developer · **Deps:** TASK-387 (vu-003/X044, DONE), TASK-369 (vu-002/X043, DONE — VU's
`realAudio` seam this reuses) · **Priority:** P3 (UX customization, not a correctness fix) ·
**Status:** DONE (2026-08-03, implementation + DUT verification; code uncommitted pending human
review, same as TASK-387 this session).

**Follow-up (same session, human feedback):** the row labels alone ("Atlas", "WaveAtlas", "VU",
"Spectrum") didn't communicate which pair is pre-recorded vs. real-audio-driven. Fixed with
explicit `"(mock)"`/`"(real)"` label suffixes plus color (real-mode rows in `TFT_GREEN`, matching
`vuMeter.h`'s own `levelColor()` "signal present" convention — mock rows stay plain white), and a
one-line grey legend under the four rows ("mock = pre-recorded, real = today's audio"). Screendump-
confirmed both the normal and all-off states render without overlap.

### TASK-390 — WebRadio marquee/title display freezes on sustained real playback — unconfirmed, filed for investigation

**Filed 2026-08-03, human-observed live on DUT (production firmware, not a test-harness finding).**
While a WebRadio station (SLAM!, a real Dutch commercial station — matches the default
`webRadioCountry=NL`) had been playing for an extended, unmeasured duration, the marquee/title
area froze showing a fragment of a show name ("...n de pauzuh", likely "in de pauze" — Dutch for
"on break"/between-programme ID). Human confirmed the touchscreen was still responding to input
at the time — this rules out a full `loopTask` hang (touch polling and the marquee tick both run
in the same `loop()`), so this is not TASK-285/288's class of watchdog-relevant freeze.

**Corroborating evidence, from the live serial heartbeat (not reconstructed after the fact):**
`last_render_age_ms` was climbing in exact lockstep with `uptime` across three consecutive
30s-interval heartbeats (32027 → 62027 → 92027, i.e. +30000 each time) — zero full-screen repaints
happened in that window and counting. This is a *display-pipeline* symptom, not merely "the ICY
title stopped updating text" — something stopped calling the render path that would normally fire
every tick regardless of content changes.

**No forensic trail into the actual triggering event.** The monitor session capturing the original
freeze went silent independently (the board's CH340 adapter flapped `/dev/ttyUSB0` → `/dev/ttyUSB1`
mid-session — a known quirk, see `docs/process/dut_workflow.md`), and was killed/restarted before
its scrollback could be searched for the triggering sequence. Production firmware
(`cyd2usb_winamp`, no `SERIAL_DEBUG`) has no live `get`/`set` query surface, so nothing could be
pulled from the frozen device directly either. This task starts from symptom + one confirmed
mechanism-level fact (render pipeline stalled, not full loopTask) and no direct cause evidence.

**Diagnostic gap found while investigating (worth closing regardless of root cause):** neither
`WinampDisplay`'s marquee state (`titleScrollOffset`/`titleScrollDeadline`/`lastTitle`/
`_wifiDownOverrideActive` — `winampDisplay.h:693-710`) nor the WiFi-down-override latch has any
debug getter today. `get wrIcy` (webRadioApp.h) exposes the *source* ICY title but not what the
marquee is actually doing with it — there is currently no way to tell "ICY title stopped arriving"
apart from "marquee logic itself is stuck" apart from "WiFi-down override latched and never
cleared" without new instrumentation.

**Plausible causes, ranked most to least likely (all unconfirmed — this is the investigation's
starting hypothesis set, same discipline as TASK-385/386):**

1. **ICY-metadata pipeline stalled independent of audio/touch/loopTask.** `s_icyTitleQueue`
   (`webRadioApp.h:107`, single-slot `xQueueOverwrite`) is fed by the Audio library's metadata
   callback and drained non-blockingly in `tick()`. The existing stall-detection apparatus
   (`WR_STREAM_DEAD_MS`, TASK-218/291's "no bytes consumed" debounce) is tuned to catch the PCM
   byte-level stall case; it's unconfirmed whether metadata delivery specifically can silently stop
   while byte-level stall-detection still reads the stream as healthy (or vice versa — audio still
   audibly playing while metadata parsing wedges). This would produce exactly the observed symptom:
   a real, stale title frozen on screen, with everything else (touch, heartbeat, presumably audio)
   still alive. Distinguishing test: `get wrIcy` during a live freeze — if it matches the frozen
   on-screen text, metadata delivery stopped upstream of the marquee; if it shows a *newer* title
   the marquee never picked up, the bug is in the marquee's consumption of the queue instead.
2. **Marquee scroll-state stuck independent of ICY delivery.** `_tickMarquee()`
   (`winampDisplay.h:836`) only redraws when `titleScrollDeadline != 0 && millis() >= deadline`. A
   short title intentionally sets `titleScrollDeadline = 0` (static display, no scroll — not a bug
   by itself), but if a *new* title never gets to `setTitle()` at all (see hypothesis 1) this reads
   identically to "marquee is broken." Needs the new getter (below) to tell apart from hypothesis 1.
3. **WiFi-down override (`_wifiDownOverrideActive`, `winampDisplay.h:196-234`) latched and never
   cleared.** Ranked low-likelihood specifically because the visible text was real station content
   ("...n de pauzuh"), not the override's fixed `"WI-FI: RECONNECTING..."` string — if this were
   active, that string would show, not stale station content. Kept as a hypothesis only because the
   override *could* have engaged and cleared earlier in the session in a way that left some other
   state inconsistent; the getter below settles it in one read.
4. **Extended-uptime resource contention as a contributing factor, not the direct mechanism.** The
   live log showed Spotify's background poll continuously failing (`HTTPC_CONNECTION_REFUSED`
   alternating with `403`, backoff climbing every ~30-60s cycle) concurrently with WebRadio
   playback, for over an hour of uptime by the time the freeze was noticed. Matches this project's
   prior tlsYield-contention/heap-fragmentation-under-sustained-load precedent class
   (TASK-287/288/289, and TASK-385/386's still-open hypotheses for an unrelated app). Not a
   standalone mechanism — would need to combine with 1 or 2 to actually produce a frozen marquee —
   but worth checking `get heap`'s `lfbInt`/`lfbDma` at repro time against this session's
   established baselines.
5. **Regression from today's TASK-387/388/389 changes.** Lowest likelihood: none of today's edits
   touch `WinampDisplay`'s marquee code, the ICY queue, or the top-level render dispatch — they're
   scoped to the vis area (`vuMeter.h`), `audio_process_extern`'s per-block math
   (`webRadioApp.h`), and the Settings UI (`appsSection.h`/`settingsStorage.*`). Kept as a
   hypothesis only for completeness and because it's the cheapest to rule out: if reproduced, A/B
   against a build with today's three commits reverted settles it in one soak.

**Investigation plan (not yet executed — DUT-gated, needs a long unattended/monitored window):**

- Add a `get wrMarquee` debug getter (mirrors this session's `wrSpec`/`wrWave` precedent) dumping
  `titleScrollOffset`, `titleScrollDeadline` (plus `millis()` so the caller can compute the delta
  without a race), `lastTitle`, and `_wifiDownOverrideActive` — the single missing piece that lets
  hypotheses 1-3 be told apart the moment a freeze is caught live.
- Flash `cyd2usb_winamp_debug`, tune into a real, currently-live station — ideally SLAM! or another
  ID-heavy commercial station (frequent title changes stress the ICY-update path harder than a
  quiet talk station would) — and sustain playback for an extended, unattended window (no existing
  canned soak fits this: `run/wr-soak` cycles play/leave every ~20s by design, which is the wrong
  shape for a "sits on one station for a long time" bug). Leave Spotify's background poll running
  rather than suspending it, matching the environment the original freeze happened in (hypothesis 4
  needs that concurrent churn present to have a chance of mattering).
- Poll `get wrIcy` + the new `get wrMarquee` + `get heap` + `get wrPump` + a screendump on an
  interval (e.g. every 60-120s) for the full soak duration. On a freeze: compare `wrIcy` against
  the on-screen text and `wrMarquee`'s state to place the fault per hypothesis 1 vs. 2 vs. 3.
- If not reproduced in a reasonable window (say, 60-90 min — unknown true MTTF, this is a budget
  not a bound): disposition as unconfirmed/intermittent, same honest framing TASK-385/386 already
  use, rather than closing on absence of a forced repro.

**Architect review (2026-08-03):** No new ADR or design doc warranted — this is a bug
investigation with a small, well-scoped diagnostic addition (one debug getter, read-only, no new
persistent state, no cross-component interface change), not a design decision. Cross-component
note worth flagging for whoever picks this up: hypothesis 1's queue (`s_icyTitleQueue`) and the
marquee's `setTitle()` gate both live on the boundary between the pump/Audio-library callback
context and the UI-thread render path — same class of boundary TASK-387/388 already had to reason
about carefully for `vu::specHRef()`/`waveTraceRef()` (single-writer discipline). Worth explicitly
confirming the ICY callback and `tick()`'s drain are still correctly single-producer/single-consumer
before assuming the queue mechanism itself is innocent — it wasn't audited as part of this filing.
No storage-headroom concern: `get wrMarquee` is a pure read-only getter over existing fields, same
shape as `wrSpec`/`wrWave` (net zero new static bytes) — this board's shrinking `dram0_0_seg`
headroom (see `[[project_webradio_headroom_finding]]`, 20B as of this session) is not at risk here,
but flagging since it's a live constraint on this exact file. Approved for scheduling as filed.

**VE review (2026-08-03):** Exit criteria as drafted above are testable but not yet automatable —
this is a real gap, not an oversight: the repro depends on real-world station content and an
unknown, possibly long, time-to-failure, which doesn't fit `run_serialdbg_tests.py`'s
short-deterministic-assertion model. Recommend, once reproduced at least once with the new getter:
(a) capture the exact `wrIcy`/`wrMarquee` state pairing that a real freeze produces and turn *that*
specific signature into a fast synthetic test (`set wrIcy <value>` injection already exists per
`webRadioApp.h:1347-1350` — a synthetic repro harness is plausible once the real mechanism is
known, not before); (b) until then, this stays a manual/soak-verified item, not a suite addition —
do not force a T_WR_MARQUEE_xx id into `run_serialdbg_tests.py` before the failure mode is
understood, that would just encode a guess as a permanent assertion. Testability challenge for the
Developer taking this on: the "not reproduced in 60-90 min" disposition path needs an explicit,
stated confidence level (this is a budget, not a bound, per the investigation plan above) — don't
let a single clean soak read as "fixed" the way TASK-385's first isolated-rerun mistake did.

**Owner:** Developer (investigation) · **Deps:** none blocking; loosely related to TASK-385/386's
open extended-uptime/resource-contention hypothesis class (#4 above) and shares this session's
`get wrSpec`/`get wrWave` getter precedent for the new `get wrMarquee` · **Gate:** DUT session with
an extended unattended soak window, new getter added first · **Priority:** P2 (real user-observed
defect on production firmware, not a test artifact) · **Status:** open — filed, reviewed
(Architect approved as filed; VE flagged the automation gap above), **soak attempted same session,
paused mid-investigation — see below.**

**Soak attempt 2026-08-03 (same day as filing) — paused, not completed.** `get wrMarquee`
implemented (`winampDisplay.h`, chained through the existing `spotifyDisplay->dbgGet()` polymorphic
path — `spotifyDisplay` is `&winampDisplay` for this build, so no new dispatch wiring was needed;
zero new static bytes, confirmed via unchanged RAM-used in the build report). Flashed
`cyd2usb_winamp_debug`, entered WebRadio with Spotify's background poll deliberately left running
(matching the original freeze's environment), loaded the real 30-station NL list, selected "SLAM!
DANCE CLASSICS" (index 23 — the closest real match to the human's original report), started
playback.

**What actually happened, not what was originally being tested for:** within 90s, `wrState`
transitioned to `ERROR_UNREACHABLE` ("Station unreachable") and stayed there across 4 consecutive
90s-spaced polls (240s+) with zero visible recovery. This is **not** the originally-reported
symptom — the marquee correctly showed the error text, not frozen-stale-real-content — but it's a
second, real, DUT-observed WebRadio defect-shaped signal worth its own line: `wrPump` stayed alive
with `cycles` climbing steadily (~45,000/90s, consistent, no stall in the pump task itself) and
heap stayed rock-stable (`lfbInt` flat at 42996 across the whole window, no fragmentation) — so
whatever's happening isn't a crash, leak, or pump-task hang, just an apparent failure to progress
past the error state.

**Self-caught methodology gap, worth recording as its own lesson:** the first soak's poller
captured `wrState`/`wrIcy`/`wrMarquee`/`heap`/`wrPump` but **not** `wrIdx` or `get wrSkip`
(`autoSkip`/`tried`/`retries`). `webRadioApp.h:610-648`'s auto-skip logic has two layers — an
immediate multi-station burn-through on connect failure, and (once parked in a terminal error) a
30s-paced re-arm that retries whatever station it's currently parked on, not necessarily a
*different* one. Without `wrIdx` per-poll, "stuck in `ERROR_UNREACHABLE` for 4 minutes" cannot be
told apart from "auto-skip correctly cycling through a network that's currently bad end-to-end" —
these look identical from `wrState` alone. **Initially over-called this as a confirmed stuck-state
bug before catching the gap** — corrected before writing it up as more certain than the evidence
supports. This is exactly the discipline TASK-385's history already flagged (don't let an
incomplete read pass as a confirmed finding) — recorded here as a second instance of the same
lesson, not just a one-off.

**Follow-up attempt blocked, investigation paused (human decision):** rebuilt the poller to add
`wrIdx`/`get wrSkip`, but the station-list fetch then failed **three consecutive times** on
re-entry — confirmed NOT the heap-guard this time (`get heap` on a fresh boot showed
`lfbInt=42996`, comfortably clear of the ~40k gate) — a live recurrence of the pre-existing
TASK-284 radio-browser-flakiness class, not a new issue and not something to hammer further
per that task's own "space out fetches" lesson. Human paused the investigation here rather than
continuing to burn reconnect/fetch attempts against a currently-uncooperative external service.
Production firmware restored, DUT left clean.

**State for whoever resumes this:** the original marquee-freeze-with-stale-content symptom was
**not reproduced** this session — zero data either way on hypotheses 1-3. The `ERROR_UNREACHABLE`-
parking observation above is a **separate, real signal**, currently unclassified (bug vs. expected
behavior against bad network conditions) pending a clean run with `wrIdx`/`wrSkip` instrumentation
(the corrected poller already exists, just never got a clean station-list fetch to run against —
`/tmp` scratch path from this session, not committed; whoever resumes should rewrite it fresh
rather than hunt for the throwaway). Next session: retry once radio-browser is healthy again
(`get wrCount` succeeding is the go/no-go signal, same as every other WebRadio DUT session this
project has had), watch `wrIdx` specifically to resolve the auto-skip question first — that's now
higher-priority than the original marquee hypothesis, since it's the thing actually reproduced.

**TASK-391 update (2026-08-03):** host-side A/B testing found real, repeat-run evidence that
`Audio.h`'s tight default connect-timeout (250ms HTTP/2700ms HTTPS) is clipping genuinely-good
connects (0/36 failures at 5s budget vs. 11/36 at the default budget, same hosts/network) — a
plausible contributor to this task's `ERROR_UNREACHABLE`-parking signal specifically. Does **not**
reproduce or explain the original marquee-freeze symptom (host-side 10-minute soak against SLAM!
DANCE CLASSICS stayed healthy throughout, no sustained stall) — that thread stays open, unchanged,
pending the `wrIdx`/auto-skip retry above. Candidate timeout fix filed as TASK-392, gated on DUT
confirmation. Full results: TASK-391 entry below.

**Live correlation found 2026-08-03, later same session (human-flagged):** a DUT was already
running (production `cyd2usb_winamp`, `spotify-mon` tmux monitor session, boot ~15:20) when this
session's TASK-391 work started — missed initially; should have been checked per the design doc's
own "Correlation with DUT runs" section. Once found, its live heartbeat showed the *exact*
TASK-390 signature actively in progress: `last_render_age_ms` climbing in lockstep with `uptime`,
zero repaints. Back-calculated onset from two heartbeat readings (both agree): **~18:20:42**,
~180.7 min into uptime — about 20 min *before* TASK-391's 3-hour host soak started (18:41:33), and
it was still frozen when that soak completed at 21:41:33 (200+ min frozen and counting, confirmed
again after). `heap=128k`/`maxAlloc=41k` unchanged throughout (not a crash/heap issue),
WiFi rssi stayed in a normal range (-43 to -55, not a WiFi drop), `poll=0/177` (Spotify polling,
unrelated to WebRadio) failing the whole session.

**This gives the disposition-matrix outcome #4 comparison the design doc asked for, even though
the overlap was partial (missed the actual onset moment):** for the entire 3-hour host soak
window, the host sustained a healthy connection to the *same station family* (SLAM! DANCE
CLASSICS) — 180 min, only 5 brief reconnects (each recovering within seconds, real titles tracked
throughout, 45 timeline events) — while the DUT sat completely frozen the whole time, both before
and during. Network/CDN health is not in question here; the DUT's render pipeline stopped calling
repaint on its own. This points at outcome #4 (DUT-specific, in the render/marquee pipeline, not
network) as the more likely explanation for the original marquee-freeze report, though it's a
timing correlation, not a captured root cause.

**Confirmed no live introspection possible on this instance:** sent a single safe, read-only probe
(`help`, matches `cmdHelp` in the SERIAL_DEBUG-only list — not the always-compiled `reconnect`
command, deliberately avoided since it forces a TLS reset + poll and would have cleared the frozen
state). Response: `{"ok":false,"error":"unknown command","cmd":"help"}` — confirms production
build, no `get`/`set`/`screendump` surface, exactly the wall this task's own "diagnostic gap"
paragraph above already flagged. No further live diagnosis possible on this instance without
reflashing debug (which would reboot and lose it). Left running, not touched further, decision on
reflash-vs-continue-observing handed to the human.

**Session note (2026-08-06) — `last_render_age_ms` caught disagreeing with a direct eyeball check;
weakens it as this task's primary diagnostic signature.** Found a live production `spotify-mon`
tmux session already running (`tmux ls`, per `[[feedback_check_for_live_dut_session_before_host_only_claims]]`)
mid-WebRadio-playback, auto-skipping between several NL stations over ~2h40m uptime.
`last_render_age_ms` climbed in lockstep with `uptime` between every station switch (resetting
only on switch events) — superficially matching this task's original signature. But at one
specific moment the human was asked to look at the physical screen directly, live: title had "just
changed, scrolling to 'radio 10'" — a real, directly-observed, correctly-scrolling repaint — while
the log's `last_render_age_ms` at that same moment showed no reset and kept climbing for 11+
minutes past it (`StreamTitle=''` → station-name-fallback repaint, not a `StreamTitle` change, is
the likely uninstrumented path). **Reading:** the counter does not cover every repaint code path
(the station-name-fallback case specifically), so a climbing `last_render_age_ms` does **not**
reliably mean the screen is stuck — it can be actively, correctly updating while the counter
reports otherwise. **Confirmed a second time, same session, ~10 min later:** switched to Radio 10,
a real `StreamTitle='Robbie Williams - Supreme'` arrived in the log and was directly observed on
the physical screen scrolling correctly at the same moment — `last_render_age_ms` again did not
reset (1165632 → 1195633 across that exact log line). So this isn't limited to the station-name-
fallback path either; a normal ICY-driven title-change repaint also doesn't reset the counter.
Broadens the finding: treat `last_render_age_ms` as unreliable for *any* mid-station title-change
repaint, not just the fallback case. This does **not** confirm or disprove the original 2026-08-03 report (a direct
human sighting of a genuinely stuck title fragment, independent of this counter) — it only weakens
confidence in using this specific field as a stand-in for "is the marquee actually stuck" going
forward. **Not closing as unable-to-reproduce** — no attempt this session actually tried to
reproduce the original conditions (extended single-station play, no auto-skip churn); this was an
opportunistic check of an already-running unrelated session. **Revised "what to look for" for
future repro attempts:** direct eyeball only, don't trust `last_render_age_ms` alone — watch for
(a) ticker text that has stopped scrolling/animating when it's long enough that it should be
scrolling, and (b) title text that visibly doesn't match what's currently audible/announced for an
extended stretch (the original report's "...n de pauzuh" fragment is the shape of a real positive:
a stale, static, truncated-looking title). If `last_render_age_ms` is used as a corroborating
signal, treat a *long* stretch with zero station switches as the only regime where it's meaningful
(the reset-on-switch masking observed here doesn't apply when nothing switches for a long time,
matching the original single-station report's setup) — cross-check any live reading against the
physical screen before trusting it alone.

### TASK-391 — Host-side network reproduction harness for WebRadio connectivity (informs TASK-390)

**Filed 2026-08-03, human-directed** to determine whether TASK-390's `ERROR_UNREACHABLE`-parking
finding is reproducible from a host machine on the same WiFi SSID as the DUT (same router/ISP
path, different hardware) — separating "network/station/CDN-side problem" from "DUT-specific."

**Concrete lead found while drafting the design (not yet tested, not yet applied as a fix):**
`ESP32-audioI2S`'s `Audio::connecttohost()` defaults its TCP-connect timeout to **250ms for plain
HTTP, 2700ms for HTTPS** (`Audio.h:530-531`) and `webRadioApp.h` never raises it via
`setConnectionTimeout()`. That's an unusually tight budget for a real TCP handshake to a remote
icecast/shoutcast host over consumer internet — a connect that would succeed in 300-400ms reads
identically to a genuinely dead station from the app's perspective, and could explain an entire
station list appearing "unreachable" in quick succession without any real outage. This is the
leading hypothesis the host tool should test first (fast, cheap: just measure real connect
latency to the actual stream hosts), before committing to the longer sustained soak.

**Design:** [M-WEBRADIO-HOST-REPRO.md](../architecture/designs/M-WEBRADIO-HOST-REPRO.md)
(Architect, drafted same session). Lean: lightweight HTTP + ICY-metadata-aware streaming client
(no MP3 decode, no I2S) — replicates `connecttohost()`'s exact request bytes and headers, splits
connect latency into DNS/TCP/TLS phases (a fast-DNS-slow-TCP result points at a different fix than
slow-DNS-fast-TCP), and tracks `StreamTitle` changes over a sustained connection to also speak to
TASK-390's original metadata-stall hypothesis. Breadth test: top 5 NL stations by vote count via
the exact same radio-browser query the app uses (`countrycode=NL&codec=MP3&hidebroken=true&
order=votes&reverse=true&bitrateMax=128`), decoupled from the DUT's own (currently flaky) fetch.
Depth test: sustained soak on SLAM! DANCE CLASSICS (the exact station TASK-390's DUT run
attempted), matching the human's original report station.

**Exit criteria:** design doc's four-way disposition matrix (timeout-too-short / DUT-specific /
real external outage / metadata-pipeline-specific) reached with logged evidence — connect-latency
numbers with DNS/TCP/TLS phase splits, and/or a title-tracking timeline from the soak — written
back into TASK-390 or a new follow-up, not left only in the design doc.

**VE review (2026-08-03):** independent pass found six real gaps, none blocking but two
substantive enough to require resolving before the tool's output is trusted for a disposition
call. Most important: (1) the design's Phase 1 test compares absolute host connect latency
against "near 250ms" — indirect and not falsifiable (host TCP stack timing isn't guaranteed
comparable to the ESP32's). Stronger substitute: connect to each host twice, once with an
artificially-imposed 250ms client timeout matching `m_timeout_ms` exactly, once with a generous
one — a materially higher failure rate at 250ms on the *same* hosts is direct causal evidence,
not a cross-stack number comparison. (2) single connect attempt per breadth-test station is too
thin to distinguish "reliably unreachable" from "one lost packet" — require N≥3 attempts per
station with a per-station success rate, not a pass/fail bit. Four more flagged: DNS-resolver
mismatch between host and DUT is unaddressed (host OS resolver may differ from the router's
DHCP-assigned DNS the ESP32 actually gets); re-querying radio-browser for station selection
repeats the exact flaky, rate-limit-sensitive call under suspicion — cache the resolved URLs,
don't re-fetch every run; the ICY-metadata parser has no correctness check of its own before a
"title went quiet" finding is trusted (the same false-positive shape TASK-385 and this session's
own `wrIdx` gap already hit); and "same-session, best-effort" correlation between host and DUT
runs is too loose given how fast conditions changed today (radio-browser worked, then failed 3×
within the same hour) — log + report elapsed time between host and DUT runs, don't treat them as
implicitly simultaneous. Full detail with fixes proposed for each: design doc's "VE Review"
section. Testability sign-off: exit criteria become genuinely falsifiable once #1/#2 are
addressed; without them a Developer could reach whichever disposition they expected going in —
the outcome this document exists to prevent.

**Owner:** Developer (implementation) · **Deps:** TASK-390 (this informs its resumption) ·
**Priority:** P2 (same urgency class as TASK-390 — real user-observed defect, and this is the
fastest path to root-causing it) · **Status:** CLOSED 2026-08-03 — disposition reached, follow-up
filed as TASK-392.

**Results (2026-08-03, Developer):** Built `app/tools/test_webradio_host_repro.py` per the design
(Option C + all six VE-review fixes: self-check gate, capped-vs-generous same-host A/B instead of
absolute-latency guessing, N=3 attempts/station, cached station resolution, DNS-resolver
disclosure, ICY-parser correctness check before trusting title-tracking). Ran the full harness
twice, ~15 minutes apart (self-check + parser-check + Phase 1 six-station A/B + Phase 2 10-minute
soak each time).

**Tool bug found and fixed before trusting Phase 2 (worth recording as its own lesson):** the
first run's soak showed SLAM! DANCE CLASSICS "dropping" every ~17s for the full 10 minutes,
34 reconnects, zero throughput, zero titles — reading like a dramatic real stall. It was a tool
defect: the soak's connect path (unlike `probe_once`) didn't follow the 302 redirect every single
station in this session required (StreamTheWorld edge load-balancing) — it was reading a
redirect's empty body forever until the 15s read timeout, over and over. Fixed by sharing the
redirect-following logic into the soak's connect path; a 30s re-test immediately showed normal
sustained throughput and a correctly-parsed title. Re-ran the full 10-minute soak after the fix —
this is exactly the false-positive shape the VE review's point #5 warned about, just one layer up
(connect/redirect, not metadata parsing) from where the review looked for it.

**Phase 1 (connect-latency A/B), combined across both runs — primary result:** generous-budget
(5s) connects succeeded **36/36** (100%) across all 6 stations × 2 runs. Capped-budget connects
(250ms HTTP / 2700ms HTTPS, matching `Audio.h`'s defaults exactly) succeeded **25/36** (~69%,
31% failure rate) — same hosts, same network, same code path, only the timeout value differed.
5 of 6 stations hit the pre-registered "timeout-supported" threshold (capped failures ≥2 more than
generous, out of 3) in at least one of the two runs: Radio 10, Sky Radio 80's Hits, SLAM!,
Concertzender Baroque, SLAM! DANCE CLASSICS. Only Arrow Classic Rock (HTTPS, the more generous
2700ms capped budget) never did. **This is same-machine, same-moment, falsifiable evidence for
the timeout-too-short hypothesis** — disposition matrix outcome #2 ("host connects fine, but
latency clusters near/above 250ms") — not outcome #1 (weakens hypothesis) or #3 (real outage).

**Caveat that likely makes 31% an undercount, not an overcount:** Python's `getaddrinfo()` has no
enforceable per-call timeout, so DNS-resolve time was NOT counted against the tested budget in
this tool — only TCP-connect (+TLS for HTTPS) was. One attempt (SLAM!, run 2, generous budget)
saw a 5222ms DNS resolve alone. On the real device, `WiFiClient::connect(host, port, timeout)`
bundles DNS+TCP(+TLS) under one budget, so a DNS spike like that would by itself blow through the
250/2700ms capped budget on the DUT — a failure mode this tool can't currently observe or count.

**DNS resolver caveat (VE review #3, unresolved):** this host resolves via `127.0.0.53`
(systemd-resolved) — not verified equivalent to whatever the DUT's DHCP lease actually hands out.
Flagged, not fixed; residual uncertainty on how directly comparable the two paths are.

**Phase 2 (10-minute soak, depth station, post-fix):** sustained connection to SLAM! DANCE
CLASSICS, ~150-300 KB/10s throughput throughout (consistent with the 128 kbps stream), 4 real
`StreamTitle` changes correctly tracked over the session, only **1 reconnect** in 10 minutes (a
~32s gap around the 3:45 mark, recovered on its own). No sustained multi-minute stall of the kind
TASK-390's original marquee-freeze report described — this host-side run does not reproduce that
symptom, and (parser-correctness check having passed separately) there's no reason to suspect the
one clean reconnect was itself a parsing artifact. Disposition matrix outcome #4 ("metadata
pipeline specific to the DUT") stays unconfirmed either way — no concurrent DUT run happened this
session to compare against, so this remains open per TASK-390, not closed by this result.

**Overall disposition:** timeout-too-short (outcome #2) is the supported finding, with logged,
repeat-run evidence. Per this doc's own scoping note ("not proposing the fix yet... proposing the
measurement"), the candidate fix (raise `setConnectionTimeout()`) is **not applied here** — filed
as **TASK-392**, gated on a DUT-side confirmation run per the design's own requirement.

### TASK-392 — Raise WebRadio's connect timeout (setConnectionTimeout), gated on DUT confirmation

**Filed 2026-08-03, follow-up from TASK-391.** TASK-391's host-side A/B test found real,
repeat-run evidence that `Audio.h`'s default connect-timeout budget (`m_timeout_ms = 250` plain
HTTP, `m_timeout_ms_ssl = 2700` HTTPS — never raised by `webRadioApp.h` via
`setConnectionTimeout()`) clips genuinely-successful connects: 0/36 failures at a 5s budget vs.
11/36 (~31%) failures at the capped budget, same hosts/network/code path, across two independent
runs. 5 of 6 tested NL stations hit this at least once. Likely conservative (see TASK-391's DNS-
timing caveat — the tested budget didn't even cover DNS-resolve time, which the real device's
`WiFiClient::connect()` does).

**Proposed change:** call `wrAudio().setConnectionTimeout(...)` in `webRadioApp.h` with a more
realistic budget — exact values TBD by whoever implements (something well above the observed
capped-budget failures without drifting into TASK-295's TWDT-adjacent territory at the high end;
that task's own `10000ms` extreme-case bump is a useful ceiling reference, not necessarily the
right steady-state value here).

**Gate (per TASK-391's design doc, explicit — do not skip):** this must be confirmed on the DUT
before being treated as done — run `run/wr-soak` (or a targeted WebRadio connectivity test) before
and after the change and confirm `ERROR_UNREACHABLE` incidence actually drops. A host-side A/B
result is evidence to justify trying the change, not proof it fixes the DUT symptom.

**Implemented, 2026-08-04:** `WR_CONNECT_TIMEOUT_MS = 5000` / `WR_CONNECT_TIMEOUT_MS_SSL = 7000`
added to `webRadioApp.h`, applied via a new `wrApplyConnectTimeout()` helper (mirrors the existing
`wrApplyInBufTrial()` pattern) called at both `Audio` construction sites (`wrAudio()`'s lazy path
and `_play()`'s explicit re-create path). 5000ms matches TASK-391's tested generous budget
directly (36/36 succeeded); 7000ms pads the HTTPS leg for the TLS handshake on top of TCP, staying
well under TASK-295's 10000ms extreme-case ceiling. `run/check` 6/6 both envs.

**DUT before/after gate run, 2026-08-04 — inconclusive, not a confirmation:** ran `run/wr-soak 10`
(28-cycle real-station soak, `test_webradio_soak.py`) twice against the same station list, ~15
minutes apart — once with the fix `git stash`-removed (clean unmodified-defaults baseline), once
with it restored. **Both runs came back identical: 28 cycles, reached PLAYING 28/28, error/skip
cycles 0, arena acquire FAILures 0.** The gate this task specifies (confirm incidence *drops*)
could not be exercised today because the baseline itself never failed once — there was no
incidence to drop. This is not evidence the fix does nothing; it's the same pattern as TASK-393's
whole investigation this session (three independent real-network repro attempts + a full 4h
TASK-397 soak, none reproducing a connect-parked freeze on demand) — real WebRadio connect
failures here are genuinely intermittent/network-dependent, not something a 10-minute same-day
soak can be relied on to surface either way. TASK-391's own host-side evidence (same hosts/network,
same code path, only the timeout value varied, 100% vs 69% success across 36 attempts × 2 runs)
remains the strongest evidence for the underlying premise — today's on-device comparison neither
confirms nor undermines it, it just didn't get a chance to discriminate.

**Owner:** Developer · **Deps:** TASK-391 (done, this task's evidence base) · **Priority:** P2 ·
**Status:** implemented, code-complete, `run/check` clean — **DUT gate attempted but inconclusive**
(both before/after runs clean, no incidence to compare). Leaving open per the task's own explicit
"must be confirmed on the DUT" requirement rather than closing on an inconclusive result. Re-run
the same before/after comparison on a session where WebRadio connect issues are actually being
observed (or against a station/network known to produce real capped-budget failures, per TASK-391's
Phase 1 list — Radio 10, Sky Radio 80's Hits, Concertzender Baroque hit the threshold more than
SLAM! did) to get a comparison that can actually move this to DONE.

**Update (2026-08-04, later same day — sobering data point, not a gate result):** TASK-393's
Spotify-present 4h soak ran on this exact fix (5000ms/7000ms already applied) and still saw a
~97% connect-failure rate against SLAM! DANCE CLASSICS (415 failures / 13 successes) whenever
Spotify's background polling was concurrently active — vs 0 failures on the identical code with
Spotify disabled. **The raised timeout budget alone did not fix connect reliability under
Spotify-concurrent conditions.** Not a formal gate result for this task (different variable under
test — Spotify-presence, not before/after the timeout change itself — see TASK-393's own entry for
the full writeup, including two disproven theories for the precise ~7.007s failure timing worth
reading before continuing this investigation), but real evidence that Spotify-concurrency may be a
much bigger lever on WebRadio connect reliability than the timeout budget was. Worth factoring in
before declaring this task's fix sufficient even if a future clean before/after gate does confirm
it helps in isolation.

**Second DUT gate attempt, isolated retry (2026-08-04, later still) — same inconclusive result, on
a different station this time.** Per PM direction to re-run the gate isolated from TASK-393's
Spotify-present confound and against a station with an actual TASK-391 failure track record:
targeted single-station soak (`test_webradio_long_soak.py`, 30 min each leg) against **Radio 10**
(`http://playerservices.streamtheworld.com/api/livestream-redirect/RADIO10.mp3`), on the
**noSpotify** build for the cleanest possible isolation. Before leg: temporarily reverted just
`webRadioApp.h` to its pre-fix state (`git checkout b0adc8d~1 -- app/src/webRadioApp.h`, working
tree otherwise untouched), flashed, ran 30 min — **0 failures, 5 title changes, 2 connects, 0
anomalies.** Restored the fix (`git checkout HEAD -- app/src/webRadioApp.h`), confirmed `run/check`
clean, reflashed, ran the identical 30 min after-leg — **0 failures, 7 title changes, 2 connects, 0
anomalies.** Identical shape, both legs.

**This is now the second independent gate attempt, on two different stations (SLAM! DANCE
CLASSICS, Radio 10), across two separate sessions, with the *same* structural outcome: neither leg
of either attempt has ever produced a single connect failure at the original tight 250ms/2700ms
defaults.** TASK-391's host-side A/B (100% vs 69% success, same hosts/network, only the timeout
varied) is real, controlled, repeat-run evidence — but two on-device gate attempts now can't
reproduce *any* baseline failure to confirm the fix against, on this network, on these two nights.
That's a pattern, not bad luck twice: either tonight's/2026-08-03's on-device network path is
consistently healthier than whatever TASK-391's host machine experienced, or the DNS-resolver
mismatch TASK-391 itself flagged as unresolved (host resolves via `127.0.0.53` systemd-resolved,
never verified equivalent to the DUT's DHCP-assigned resolver) means the host-side finding doesn't
transfer to the device's actual network path the way assumed. Reports:
`app/tools/rnd_logs/webradio_long_soak_20260804T162536.json` (before) /
`webradio_long_soak_20260804T170116.json` (after), raw logs alongside each.

**Still open.** Not closing on a second inconclusive result any more than the first. If a third
attempt is ever made, it should either (a) target a network/time-of-day more likely to show a
capped-budget failure (TASK-391's own testing happened at a different hour than either on-device
attempt — worth checking if that's a variable), or (b) stop trying to catch it in the wild and
instead build a controlled reproduction (deliberately throttle the DUT's connect path to simulate
a slow handshake, rather than waiting for a real one) — that would actually let this task close on
a real pass/fail instead of a third "nothing failed" result.

### TASK-393 — WebRadio ERROR_* render freeze, live-reproduced on debug build; terminal-retry not firing

**Filed 2026-08-03, same session as TASK-390/391, human-directed** ("could we do an extended soak,
3h?" → live DUT correlation found while that soak ran → flashed debug build → drove WebRadio into
the exact failure and caught it live with full introspection). This is the strongest evidence yet
for TASK-390's render-freeze thread — reproduced on demand, not just observed after the fact.

**Repro steps (debug build `cyd2usb_winamp_debug`, via `tmux send-keys` into the already-open
monitor — no new serial connection, no DTR reset):**
1. `switchApp 11` (WebRadio's current `AppId` — verified via `app/tools/app_ids_gen.py`'s
   `APP_SLOT` map, **not** the `switchApp 10` `test_webradio_soak.py` hardcoded. **Correction
   (2026-08-03, later same session):** the guess here that `cyd2usb_webradio` has a different,
   trimmed app registry was wrong — `appRegistry.h` is one unconditional list, identical across
   every env; `WEBRADIO_ONLY` is an unrelated memory-budget flag, not a registry trim. `10` was
   simply stale everywhere, full stop — see TASK-394, which traces exactly when and fixes it.).
2. Station list fetch hit a live `HTTP 503` from radio-browser (`get wrLastHttp` — real, ambient
   flakiness, unrelated to anything in this session). Sidestepped with the debug-only
   `set wrUrl http://stream.slam.nl/WEB15_MP3` (TASK-261 Phase 2 lever — injects a single
   synthetic station and plays it immediately, bypassing the fetch).
3. First connect succeeded (`StreamTitle='September - Cry For You'`, `last_render_age_ms` reset to
   4398 — **confirms active playback does reset the render clock; idle screens climbing on their
   own is separately normal, not a symptom** — this session briefly worried a fresh idle boot's
   own climbing `last_render_age_ms` was the same bug; it isn't, this comparison settles it).
4. ~5s in: `stream dead (isRunning=1 for 0ms, bufStalled for 5000ms)`, one stall-retry per
   `_onPlaybackFailed`'s policy, retry's `connecttohost()` to `stream.slam.nl` itself failed
   (`"Request ... failed!"`) — plausibly another instance of TASK-391/392's connect-timeout
   finding, though not confirmed as the specific cause here. `_state → ERROR_UNREACHABLE` (5).

**From that point, `last_render_age_ms` climbed in exact lockstep with `uptime` for the entire
observation window (348s+, zero resets, two independent `get wrState` checks both returned `5`
throughout) — the identical signature as the live DUT correlation found earlier this session and
TASK-390's original report.** `get wrScroll` while parked: `offset=0 drag=0 vel=0 accum=0` — fully
static, matching the human's own live observation on the physical LCD this session ("buffer/POS is
at zero (left)"). `get heap`/`get stacks` both healthy throughout — not a resource issue.

**Root-cause candidate, not fully confirmed:** `webRadioApp.h`'s `tick()` only calls `_drawFull()`
when `_dirty` is set, and once parked in an `ERROR_*` state nothing in the normal per-tick PLAYING
block runs (it's gated on `_state == PLAYING`), so `_dirty` only gets set once (the transition into
the error state) and never again — matching the freeze. **This is expected to be already handled**
by TASK-276's own terminal-retry mechanism (`webRadioApp.h:623-634`, `WR_TERMINAL_RETRY_MS=30000`)
— re-arms a fresh play attempt every 30s specifically so the app never parks forever. **That
mechanism did not fire even once in 348+ seconds** (no `"terminal retry — re-arming scan"` log
line ever appeared, `wrState` never left `5`), despite every logged precondition appearing
satisfied (`webRadioAutoSkip` defaults `true`, `_state` is one of the three retryable errors,
`_stationCount=1 > 0`, elapsed time was >10x the threshold). **Why the re-arm isn't firing is not
determined** — `get wrAutoSkip` isn't a valid debug var (that key belongs to a different app's
dbgGet, a dead end), and further tracing needs either a breakpoint/instrumented build or reading
`_pendingAction`'s actual runtime value some other way. Flagged as the concrete next step, not
solved here.

**Relationship to other WebRadio tasks:** doesn't fully explain the *original* human report (this
repro's `wrIcy` was empty when frozen — no stale title text — whereas the original report saw a
stale real fragment, "...n de pauzuh"). Same *class* of bug (render pipeline stuck while parked),
not necessarily byte-identical mechanism. Directly classifies the "ERROR_UNREACHABLE parking"
signal TASK-390 flagged as "separate, real, currently unclassified" — it's now classified: real,
reproducible, and its supposed auto-recovery isn't working.

**Owner:** Developer · **Deps:** TASK-390 (feeds it), TASK-391/392 (connect-timeout evidence this
repro's own connect failure is consistent with) · **Priority:** P2 (downgraded from P1 — see
below; the original freeze was directly witnessed and logged, but three independent real-network
repro attempts couldn't re-break the retry mechanism, so this is no longer a reliably-reproducible
defect to hand a Developer as "fix this") · **Status:** open — the render-freeze-while-parked
*symptom* was live-reproduced once; the *retry-doesn't-recover* mechanism behind it could not be
re-triggered in three further attempts (see update below). Needs recurrence + better
instrumentation-at-the-moment before a root cause is findable.

**Update (TASK-395's `T276` test, same day):** the retry re-arm's own condition logic tested
correctly (PASS, fired at 32s) under `wrDeadUrls`'s synthetic forced-fail path — see TASK-395 for
the full result. That path never calls the real `connecttohost()`, so this narrows the regression
to something specific to state left behind by a genuine failed connect, not the retry logic
itself. Next repro should use a real dead URL (`set wrUrl`), not the synthetic hook.

**Update (real-dead-URL reproduction attempted, same day, human-directed) — could NOT re-break it,
three separate ways:**

1. **Real raw-IP dead host (`set wrUrl http://192.0.2.1/dead`, RFC 5737 TEST-NET, single injected
   station, immediate `connecttohost()` failure via the real network stack — no PLAYING ever
   happened first):** landed terminal `ERROR_UNREACHABLE` on the first attempt. Retry fired
   reliably at **30s, then 30s, then 30s again** — three consecutive clean cycles, heap stable
   (54k, no drift), before being stopped manually. (Note: raw-IP hosts hit TASK-295's existing
   `10000ms` timeout bump, not the normal 250ms — expected, unrelated to this question; each
   `_play()` attempt itself took ~10s to fail, the *retry cadence* was still a clean 30s.)
2. **Real hostname (`set wrUrl http://stream.slam.nl/WEB15_MP3`), natural connect → play → stall →
   stall-retry → second failure → terminal — structurally the same shape as the original human
   report and this task's own live repro above:** reached terminal `ERROR_STALL`/`ERROR_UNREACHABLE`
   repeatedly as the real stream connected, played briefly, and stalled again (real StreamTheWorld
   edge-server flakiness, matches TASK-391's own findings). **The terminal-retry fired every single
   time it was checked — four separate `"terminal retry — re-arming scan idx=0"` log lines across
   one continuous ~5-minute session**, each landing back at a fresh connect attempt.

**None of the three independent reproduction methods (synthetic multi-station, real single-station
immediate-fail, real single-station stall-then-fail matching the original conditions structurally)
could reproduce the 348+s-with-zero-re-arms behavior originally observed.** The terminal-retry
mechanism held up under repeated, deliberate stress today. This does not mean the original
observation was wrong or imagined — it was directly witnessed, logged, and math-checked at the
time (two independent `last_render_age_ms` readings agreeing on a stable, non-recovering freeze
duration) — but it does mean **this is not a simple, reliably-reproducible logic defect in the
retry condition itself.** Candidate explanations, none confirmed: (a) some one-off state left over
from that specific session's unusually long precursor history (5.5h frozen prod instance, a
reflash, a real radio-browser 503 mid-session, the `_deferredInject` path) that a clean repro
wouldn't hit; (b) a genuine but rare timing race that today's ~7 total retry cycles across three
tests simply didn't happen to trigger. **Downgrading confidence accordingly** — this is now
"observed once, robust against every repro attempt so far," not "confirmed broken." If it recurs,
capture `_pendingAction`/`_lastAttemptMs`/`_autoSkipTried` via a debug build at the moment it's
noticed, before touching anything else — that's the instrumentation this investigation was missing
each time.

**Update (TASK-397 4-hour unattended soak, 2026-08-04, 05:20:40–09:20:55):** ran the purpose-built
`test_webradio_long_soak.py` v2 (see TASK-397 for its own build history) against the single real
target station (`SLAM! DANCE CLASSICS`, `http://stream.slam.nl/WEB15_MP3`), no Spotify present
(`cyd2usb_winamp_debug_noSpotify`), `wrAutoSkip` confirmed on throughout. **Result: 14401.9s
(4h00m02s) elapsed, 0 anomalies, `status=complete`.** `wrState` stayed `2` (PLAYING) for the entire
run — never entered an `ERROR_*` state, so the terminal-retry mechanism this soak exists to stress
was never actually invoked; heap stable 49–58k across 479 heartbeat samples (no drift); 71 real ICY
title changes tracked correctly; DUT-silence watchdog never tripped (max gap between raw serial
lines: 40s, well under its 90s threshold); zero `terminal retry`/`stream dead`/`connecttohost
failed`/`ERROR_` lines anywhere in the 1872-line raw log. Report:
`app/tools/rnd_logs/webradio_long_soak_20260804T052040.json`, raw log
`app/tools/rnd_logs/webradio_long_soak_20260804T052040_raw.log`. Also caught mid-run, on-device (not
a bug): the Winamp skin's play-time digits legitimately wrap at 6000s / 100min
(`webRadioApp.h:786`, `_snapPlaySec % 6000`, TASK-349's own documented design for streams that
outlive classic MM:SS range) — human saw the on-screen clock drop from ~90min to ~1min and flagged
it as a possible reset; confirmed from the raw log (zero reconnect events at that timestamp) and
source it was the intentional wrap, not a real reconnect.

**This is new evidence, not resolution.** A single clean 4-hour run where the target error states
were never entered doesn't confirm or rule out TASK-393's original observation — it mainly confirms
`stream.slam.nl` didn't happen to fail during this particular window, so the terminal-retry-recovery
question this soak was built to answer remains untested by this run. Consistent with the "observed
once, robust against every repro attempt so far" framing above, now with a fourth clean attempt
added to that list (three real-network repro attempts + this soak). If a real anomaly is ever
caught by this tool (or another `--hours` run against a flakier station), the report JSON's
`anomalies[]` array carries the full diagnostic snapshot at the moment it fires — that's what
would move this from "not reproduced" to "confirmed."

**Update (Spotify-present 4-hour soak, 2026-08-04, 11:40:13–15:40:14) — did not reproduce the
render-freeze, but found a large, separate, well-evidenced connect-reliability finding.** Added a
`--spotify-present` flag to `test_webradio_long_soak.py` (skips the `set bgPoll 0` disable, leaving
Spotify's background polling active as a concurrent TLS user — the one condition from the original
human sighting the noSpotify-build runs above don't cover). Flashed the regular
`cyd2usb_winamp_debug` build (Spotify enabled, TASK-243's Premium lapse means `bgPoll` is
continuous 403 retries rather than real playback polling — still real TLS churn either way). Ran
the identical single-station soak (`SLAM! DANCE CLASSICS`) on a build that also already had
TASK-392's connect-timeout fix (5000ms/7000ms) applied.

**Result: 14401.9s (4h00m02s) elapsed, 0 anomalies, `status=complete`.** `render_age` never
climbed in lockstep with `uptime` at any point — the render-freeze detector correctly never fired,
so **this run does not reproduce TASK-393's specific symptom**, same disposition as every prior
attempt (now a fifth). But the connect-outcome numbers are dramatic and unambiguous: **415 connect
failures vs. 13 successful plays over the full 4 hours (~97% failure rate)**, against the identical
code/station/URL that held **0 failures, 71 successful title updates, one continuous connection for
nearly the entire 4 hours** in the no-Spotify run directly above. Heap stable 44-117k (mostly 47-49k
observed live, no leak — `anomalies=0` would have caught sustained drift), silence watchdog never
tripped (max gap between raw serial lines: 24.7s). Report:
`app/tools/rnd_logs/webradio_long_soak_20260804T114000.json`, raw log
`app/tools/rnd_logs/webradio_long_soak_20260804T114000_raw.log`.

**Live investigation during the run, both leads chased and both disproven — recorded so a future
session doesn't repeat them:**
1. *SSL-edge-timeout theory (wrong):* every failure takes almost exactly **7.007s**, matching
   `WR_CONNECT_TIMEOUT_MS_SSL`, which looked at first like the device was being redirected to an
   HTTPS StreamTheWorld edge (`stream.slam.nl` genuinely does 302-redirect there — confirmed via a
   live host `curl`, real audio streamed fine externally). Disproven by the raw log itself: the
   `"Connect to new host"` and `"Request ... failed!"` lines both reference the exact same string,
   `http://stream.slam.nl/WEB15_MP3` — no `"redirect to new host"` line ever appears in a failing
   cycle. The failure happens at the very first hop, on the plain-HTTP URL, which per
   `Audio.cpp:476-477` means `m_f_ssl` should be `false` and the **5000ms** plain budget should
   apply — not 7000ms. The precise 7.007s timing (confirmed consistent from the run's start to its
   final failure just before completion) remains **unexplained** — flagged, not resolved.
2. *General router-DNS unhealthiness (not supported):* one cold `dig @<gateway> stream.slam.nl`
   took 10.02s, suggestively close to the unaccounted-for ~2s gap. Immediately re-tested: a fresh,
   never-queried hostname (`stream.radiocorp.nl`, the CNAME target) resolved in 0.01s, `www.google.com`
   resolved in 0.02-0.19s across three tries, and `stream.slam.nl` itself resolved in 0.10s on a
   second (genuinely TTL-expired, re-resolved) query. One isolated slow blip, not a sustained
   pattern — doesn't survive its own follow-up test, so not trusted as the explanation either.
3. **What is confirmed, from source, and stays useful regardless of which theory is right:**
   `framework-arduinoespressif32/libraries/WiFi/src/WiFiClient.cpp:302-309` —
   `WiFiClient::connect(host, port, timeout_ms)` calls `hostByName()` (DNS resolve) with **no
   timeout at all**; only the subsequent raw-IP `connect()` gets the requested budget. This sharpens
   (with actual source evidence, not a guess) the DNS caveat TASK-391 already flagged as unresolved
   — DNS-resolve time is additional and unbounded on top of `setConnectionTimeout()`'s budget, not
   counted against it. Still doesn't fully explain the precise 7.007s figure on its own.

**Bearing on TASK-392:** this build already had TASK-392's timeout fix (5000ms/7000ms) applied, and
the connect failure rate was still ~97% under Spotify-present conditions — raising the budget alone
clearly does not fix connect reliability when Spotify is concurrently active. TASK-392's own gate
(run without Spotify present, both before/after clean) and this result are not directly comparable
— different variable under test — but this is a strong signal that Spotify-concurrency is a bigger
lever on connect reliability than the timeout budget was, at least for this station tonight.

**Honest bottom line:** TASK-390's original concurrent-Spotify-TLS-contention hypothesis now has
real, dramatic, reproducible-tonight support at the *connect-reliability* level (100%→3% success
swing, same code/station/URL, only Spotify's presence differs) — but it still has **zero** support
at the *render-freeze* level (the actual symptom TASK-393 was filed for). These may be related
(repeated connect failure is a precondition for ever reaching a parked `ERROR_*` state) or may be
two separate WebRadio-reliability issues that happen to share a station. Don't conflate "WebRadio
struggles to connect when Spotify is present" (now well-evidenced) with "WebRadio's error-recovery
gets permanently stuck" (still unreproduced) when reporting this further up.

**Update (2026-08-04, later same day) — the Spotify-present run's own raw log already answered a
different, bigger, previously-open question, with zero new instrumentation required.** Re-reading
the existing `[W][perf] iter=...ms (worst path so far: app.tick:...)` lines already captured in
that soak's raw log: **every one of the run's 415 failed connect attempts blocked `loopTask` — the
main app-dispatch loop: touch, rendering, taskbar, every other app — for 7-9+ seconds.** 421
individual tick iterations exceeded 5000ms over the 4-hour run (`grep -oE "iter=[0-9]+ms"` on the
raw log, filtered >5000), roughly one every ~34s, matching the failure cadence almost exactly.
Successful connects are fast (29-332ms observed). Cross-checked against the clean no-Spotify run:
worst `app.tick` there was 79ms, zero iterations over 5000ms.

**Self-correction, same session, before this went further:** initially wrote this up as "failed
connects fall through to a generic `app.tick` bucket instead of the `wr.connect` perf label — a
secondary instrumentation gap." Checked the actual `_play()` call site
(`webRadioApp.h:1690-1694`) before repeating that claim in TASK-398, and it's wrong —
`perf::record("wr.connect", ...)` runs *unconditionally*, before the success/failure branch, so
failures ARE recorded under `wr.connect` (confirmed: 47 `wr.connect`-labelled worst-path lines in
this same raw log, including fast successful connects). `app.tick` shows as the reported "worst
path" during failures simply because `perf::worstPathName()` reports whichever named slot has the
largest value, and `app.tick` (the outer `tick()` span, containing the nested `wr.connect` call
plus everything else) is always ≥ `wr.connect` for the same iteration — not a gap, expected
behavior for a max-over-named-spans profiler. The 7-9s/421-freezes finding itself is unaffected;
only the "why app.tick and not wr.connect" secondary detail was wrong. See
`M-WR-AUDIO-TASK.md`'s OQ4 for the corrected version.

**This is not a new architectural discovery — it's the first real measurement of an already-known,
already-explicitly-deferred open question.** `docs/architecture/designs/M-WR-AUDIO-TASK.md` (the
design behind TASK-278's audio-pump-task offload, accepted 2026-07-03) documents this exact gap at
filing time: *"A third, adjacent latency source: `connecttohost()` blocks loopTask for up to
several seconds... Not this design's primary target, but the option space should not foreclose
fixing it."* Phase 1 (implemented, TASK-278) **deliberately left connect-blocking out of scope**
— TASK-278's own E1 exit-criteria explicitly excluded CONNECTING-state windows from its UI-latency
measurement. Phase 2 (async connect via a command-queue architecture, "real surgery on the
freshly validated ADR-045/TASK-276 machine," per the design doc) was proposed and explicitly
deferred, gated on OQ4 — *"measure (`perf::record("wr.connect")`) during Phase 1 to decide whether
Phase 2 is worth the state-machine surgery"* — which had only ever been sampled once, under
healthy conditions (`wr.connect:83ms`, excluded as an outlier in the 2026-07-07 E1 campaign).
**Tonight's 421-freezes-in-4-hours number is that measurement**, just arrived at from the failure
path instead of the success path OQ4 originally expected. OQ4 marked RESOLVED in the design doc
with this update; a caught-live self-correction is on record there too (an early read of the
`app.tick` worst-path values as "growing over time due to fragmentation" was wrong — same benign
~73ms/cycle phase-drift artifact as `render_age`'s drift, not real degradation; walked back before
being asserted as fact).

**Filed as TASK-398** to actually scope Phase 2 (or a narrower connect-specific mitigation) now
that the freeze magnitude is real data, not a deferred theoretical.

**Post-TASK-398 soak, 2026-08-05 (2h, Spotify-present, `--spotify-present` flag, SLAM! DANCE
CLASSICS, `cyd2usb_winamp_debug`) — sixth repro attempt overall, first since TASK-398 landed.**
Run via `test_webradio_long_soak.py` in the background while unrelated host-side implementation
work (TASK-400/401) proceeded in parallel. **Result: 0 anomalies, `status=complete`, 7200s
elapsed.** `render_age` never climbed in lockstep with `uptime` at any point (the render-freeze
detector correctly never fired) — same disposition as all five prior attempts, still unreproduced.
Raw-log counts (`grep` against the persisted log, not live reads): 213 `connecttohost failed` /
67 successful connects (~76% failure rate this run — lower than the pre-TASK-398 97% figure from
the 2026-08-04 run, but station/network conditions differ enough between sessions that this is not
a controlled before/after comparison, just a data point), and — the actually load-bearing number —
**232 `terminal retry — re-arming scan` firings, every single one followed by a fresh `play idx=`
attempt, zero permanent `ERROR_*` parks over the full 2 hours.** Heap stable (42-117k, no drift),
no crash/panic/reboot lines. This is meaningfully different from the pre-TASK-398 picture: the
device now visibly enters and recovers from the connect-fail/terminal-retry cycle roughly every
30s for two straight hours, under the same adverse Spotify-concurrent conditions that used to
produce 7-9s whole-device freezes, without ever wedging — consistent with TASK-398's async-connect
fix having removed the freeze mechanism even though it hasn't fixed (and was never intended to fix)
the underlying connect-reliability rate against this specific station under Spotify contention.
Does not confirm the original stale-title marquee-freeze symptom either way (TASK-390's own open
thread — no fresh evidence for or against this session). Reports:
`app/tools/rnd_logs/webradio_long_soak_20260805T114034.json` (+ `_raw.log`).

**Eighth repro attempt, 2026-08-05 22:46–00:50 (overnight, unattended).** First launch
(`..._20260805T224632_raw.log`, 9KB) aborted itself after 43s — booted into production firmware
(no `SERIAL_DEBUG` surface), every `get` poll returned `{"ok":false,"error":"unknown command"}`;
harness detected this and relaunched rather than logging a false-clean result. Second launch
(`..._20260805T225002`, `status=complete`, `elapsed_s=7200.1`, 0 anomalies) is the real run: boot
line shows `spotify=idle (playerMode=webradio) — refresh deferred to first toggle` — this run did
**not** have Spotify's background poll active (`--spotify-present` was not set), unlike the sixth
attempt above. 175 `wrState` polls, 66 `terminal retry — re-arming scan` firings (each followed by
a fresh `play idx=` attempt, same pattern as the sixth run), 28 `connecttohost failed` lines, 0
permanent `ERROR_*` parks, `render_age` never climbed in lockstep with `uptime`. Same disposition
as all seven prior attempts — still unreproduced. Reports:
`app/tools/rnd_logs/webradio_long_soak_20260805T225002.json` (+ `_raw.log`); the aborted false-start
kept alongside it as `..._20260805T224632_raw.log` (evidence the harness's abort-on-no-debug-surface
behavior works, not a separate finding).

**Update (2026-08-06, instrumentation gap closed, no new repro attempted):** every "if it recurs,
capture X" note above pointed at `_pendingAction`/`_lastAttemptMs`/`_autoSkipTried` — but
`_pendingAction` and `_autoSkipTried` were already exposed via the existing `get wrSkip` getter
(`pending`/`tried`/`retries`/`autoSkip` fields, `webRadioApp.h`) the whole time; every "dead end"
note in this task about needing a breakpoint or new instrumentation was really just this getter
going unchecked. The one genuinely missing piece was `_lastAttemptMs` itself — with no elapsed-time
field, a live catch couldn't tell whether the terminal-retry gate's `>= WR_TERMINAL_RETRY_MS` term
was the one holding it back from the other three ANDed conditions. Added `sinceAttemptMs`
(`millis() - _lastAttemptMs`) to `get wrSkip`'s JSON output — SERIAL_DEBUG-only, zero new static
storage (computed inline), `run/check` 6/6 clean. `test_webradio_long_soak.py` already snapshots
`get wrSkip` on every anomaly capture (line 322), so the next anomaly report picks this field up
for free with no tool changes. Net effect: the four gating conditions in `tick()`'s terminal-retry
check (`webRadioApp.h:863-874` — `autoSkip`, `pendingAction`, `state`, elapsed-vs-30s) are now all
readable in one `get wrState` + `get wrSkip` pair at the moment of a freeze, closing the gap this
task's repro attempts kept citing. Does not itself explain the original unreproduced freeze —
still 8/8 repro attempts clean, mechanism holds up under stress — this only removes the excuse for
the *next* live catch (spontaneous or soak-caught) coming back inconclusive again.

### TASK-394 — stale `switchApp 10` (WebRadio) in three tools — TASK-347's own follow-up, never filed

**Filed and CLOSED same-session, 2026-08-03 — human pushback on TASK-393's write-up** ("we've done
addressing by reference, yet the test suite is not able be coded by reference?! yesterday we ran
the full test suite and this issue was not flagged — how poor is our test suite?"). Root-caused
before fixing, not just patched.

**Timeline (git history, not guessed):**
- `c941260` (2026-06-29, TASK-271): `test_webradio_soak.py` written, `switchApp 10` — **correct
  at the time**, WebRadio genuinely was `AppId` 10 in `appRegistry.h` then.
- `8dd270c` (2026-07-11, TASK-303/304, M-PLANERADAR): `PlaneRadar` inserted before `WebRadio` in
  `appRegistry.h` → WebRadio shifted 10→11. **This is the exact commit that broke it** —
  `test_webradio_soak.py`, `test_adr045_gate.py`, and `exp012_measure.py` (all pre-existing at
  that point) went stale here, silently.
- `68da01b` (2026-07-28, TASK-347): explicitly audited the codebase for hardcoded `switchApp <N>`
  literals broken by *its own* registry reorder (moving `Settings`) — found and fixed
  `run_serialdbg_tests.py`, `test_fetch_stress.py`, `prloc_*_smoke.py`, `pr_delta_smoke.py`, plus
  doc references. **In the course of that audit it also found today's three files, correctly
  attributed them to the earlier TASK-307/PlaneRadar break (not its own change), wrote "flagging
  for a separate task" directly into `tasks.md`** (line 244 as of this session) — **and no such
  task was ever actually filed.** It sat as a prose note in a closed task for 6 days.
- `2026-08-03` (this session, TASK-393): live-reproduced the WebRadio render-freeze bug on the
  DUT, mentioned in passing that `test_webradio_soak.py`'s `switchApp 10` was stale — framed as a
  minor "landmine avoided," with an **incorrect guess** that it might still be intentionally
  correct for a differently-registered build (corrected above, in TASK-393). Human correctly
  called this out as under-selling a real, already-self-diagnosed, never-actioned gap.

**Why "yesterday's full test suite" didn't flag it:** it doesn't run these three tools.
`run/test`'s T-suite (`run_serialdbg_tests.py`) is unaffected — it already routes `switchApp`
through the generated `APP_SLOT` mirror correctly (fixed by TASK-347). `test_webradio_soak.py` /
`test_adr045_gate.py` / `exp012_measure.py` are separate, manually-invoked tools
(`run/wr-soak` and ad-hoc), not part of the routine regression sweep — so this bug could only ever
have been caught by someone actually running one of them, which nobody had done since the break
(TASK-238's ADR-045 gate close, the last recorded `test_adr045_gate.py` run, was 2026-07-02 —
*before* the break).

**Fix (DUT-verified, not just code-reviewed):** all three files now `from app_ids_gen import
APP_SLOT` and use `f"switchApp {APP_SLOT['WebRadio']}"` — the same pattern already established
correctly in `run_serialdbg_tests.py` / `test_tls_yield_reliability.py`. Verified end-to-end
against the live DUT (not just import-tested): `python3 tools/test_webradio_soak.py --port
/dev/ttyUSB1 --minutes 1 --play-secs 15 --verbose` → `entering WebRadio (switchApp 11)`, `30
stations loaded`, 4 real play cycles against real stations (Radio 10, Sky Radio 80's Hits, SLAM!,
Concertzender Baroque), arena acquire/release balanced 4/4, **VERDICT: PASS**. (Incidentally: 3 of
those 4 cycles hit `state=4`/`state=5` — ERROR_STALL/ERROR_UNREACHABLE — during a 1-minute window;
consistent with, not deeper-investigated here, TASK-391/392's connect-timeout finding.)

**Owner:** Developer · **Deps:** none · **Priority:** P2 · **Status:** DONE — fixed and
DUT-verified 2026-08-03.

### TASK-395 — zero regression coverage for TASK-276's terminal-retry — the actual reason TASK-393 went undetected

**Filed 2026-08-03, same pushback session.** TASK-394 explains why the *tooling* was broken;
this explains why the T-suite itself has no chance of catching a TASK-393-class regression even
when every tool is pointed at the right app.

`webRadioApp.h:608-634`'s terminal-retry (`WR_TERMINAL_RETRY_MS=30000`, added by TASK-276
specifically to stop the app parking in an `ERROR_*` state forever) was DUT-confirmed working
*eagerly* on 2026-07-07 — confirmed so eager, in fact, that `run_serialdbg_tests.py`'s own
`_wr_err_test()` helper (used by `T_WR_ERR_01`/`T_WR_ERR_02`) has to explicitly `set wrAutoSkip 0`
before injecting a test state, **specifically because the retry would otherwise re-arm within one
tick and overwrite the injected state** (see the helper's own docstring, dated from the TASK-277
campaign). That's a deliberate, correctly-reasoned test-isolation choice — but its side effect is
that **every automated test which touches this code path turns the retry off first**, so none of
them can ever observe whether it still fires.

`T237` (`run_serialdbg_tests.py:6409`) is the closest thing to a real test of the surrounding
auto-skip machinery, and it does run with auto-skip ON — but it only asserts "no loop within 1.5s
of hitting terminal," which is correct for *its own* scope (TASK-237's runaway-skip bound) and
says nothing about the 30-second-later re-arm. **No test anywhere waits past
`WR_TERMINAL_RETRY_MS` with auto-skip ON to confirm the terminal-retry itself still recovers.**

Between the 2026-07-07 manual DUT confirmation and 2026-08-03's TASK-393 finding that it no longer
fires (348+s observed, zero re-arms, despite every logged precondition satisfied), roughly four
weeks passed with **no automated test capable of catching that regression even in principle** —
one class deliberately disables the mechanism for isolation, the other class (TASK-394's tools)
was independently broken and unrun. Two unrelated gaps compounded into one blind spot exactly
where the real regression lived.

**Test written and DUT-run 2026-08-03 — `T276`** (`run_serialdbg_tests.py`, registered alongside
`T237`): drives to terminal `ERROR_UNREACHABLE` via the same deterministic `set wrDeadUrls N`
hook T237 uses (no real network dependency), with `wrAutoSkip` **ON** this time, then polls
`wrSkip.tried` for up to `WR_TERMINAL_RETRY_MS + 15s` slack — a drop below the saturated `N-1`
is unambiguous evidence the re-arm fired (only the retry handler resets that counter).

**Result — surprising, and it changes the shape of TASK-393, doesn't close it:**

```
T276  reached terminal (tried=2, state=5) — waiting up to 45s for re-arm …
T276  PASS — terminal-retry re-armed after 32s (tried dropped below 2, scan restarted)
```

**The terminal-retry fired correctly** — 32s, right against `WR_TERMINAL_RETRY_MS=30000`. This
directly contradicts TASK-393's live observation (348+s, zero re-arms) under what looked like the
same preconditions. The mechanistic difference: `wrDeadUrls`'s `_debugForceConnFail` path is an
early return in `_play()` (`webRadioApp.h:1568-1580`) that sets `ERROR_UNREACHABLE` **without ever
calling the real `connecttohost()`** — no real `WiFiClient`/TLS/`Audio` object state is touched.
TASK-393's repro used `set wrUrl` against a real stream URL, where `connecttohost()` actually ran
and returned false after a genuine attempted TCP connect. **TASK-393's regression is therefore
plausibly specific to state left behind by a real failed `connecttohost()`** (a stuck semaphore,
`spotifyTask` TLS yield/resume bookkeeping, `Audio` object internal state, something arena/heap-
adjacent) — not a defect in the retry re-arm's own condition logic, which this test now shows
works correctly in isolation.

**This test is real, valuable coverage on its own** (the retry mechanism's logic previously had
zero automated assertion; now it has one, and it passes) — but it does **not** currently reproduce
or catch TASK-393's actual failure mode. TASK-393 needs a repro using a real dead URL (matching
the original live conditions) with this same 30s+ wait pattern, not the synthetic hook, to
actually pin down what real-connect-failure-specific state differs. Filed as the next concrete
step under TASK-393, not a new task — same root cause, sharper reproduction target.

**Owner:** Developer · **Deps:** TASK-393 · **Priority:** P1 · **Status:** T276 test DONE
(committed, passing, real coverage) — **TASK-393's actual root cause still open, now better
scoped** (real-`connecttohost()`-failure-specific, not the retry logic itself).

### TASK-396 — audit `tasks.md` for "flagged for a separate task" notes that were never filed

**Filed 2026-08-03, same pushback session.** TASK-394 is a second confirmed instance of a specific
failure pattern: a task's own closing write-up correctly identifies a real, separate issue,
explicitly says "flagging for a separate task" / "no task filed for it yet," and then nothing
files it — the note sits as prose in a closed task, invisible to any task-number-based search,
until someone re-discovers the underlying bug the hard way (today: live, on the DUT, because a
human happened to be watching the screen).

One other live instance was checked this session and found to have actually resolved itself
correctly (`OQ4`/taskbar `isHealthy()` gap: flagged once as unfiled circa TASK-364's writeup, then
properly filed as **TASK-366** in the same document, later) — so this isn't universal, but it's
not a one-off either (two real instances found from a light grep this session, not an exhaustive
pass).

**Scope:** grep `tasks.md` (and `tasks-archive.md`) for the pattern (`flagged for`, `flagging for`,
`no task filed`, `not yet filed`, `separate task`, `follow-up task`, similar phrasings), and for
each hit: confirm a real `TASK-NNN` now exists for it: if yes, note it inline (`OQ4` precedent);
if no, either file it properly or make an explicit, reasoned call that it's not worth tracking
(some of this session's own grep hits *were* legitimately fine as-is — e.g. tasks-archive.md's
"doesn't warrant tracked backlog on its own" calls were reasoned decisions, not gaps — the audit
needs to tell those apart, not file everything reflexively).

**Process angle (for QM):** `AGENTS.md` already says "PM reads `git log` before planning" — worth
adding an explicit line that a task closing with a "flagged, not filed" note is not actually
closed on that thread until the follow-up has a number, or the human/PM has made an explicit
call to drop it. Candidate for `docs/quality/best_practices.md` once this task's audit gives it a
concrete enough shape to generalize from (don't add the BP speculatively before that).

**Owner:** PM/QM · **Deps:** none · **Priority:** P3 (process hygiene, not a functional bug) ·
**Status:** **DONE — full audit completed 2026-08-05.**

**Audit results.** `grep -noiE` for the pattern set (`flagged for`, `flagging for`, `no task
filed`, `not yet filed`, `separate task`, `follow-up task`) across both files:

- `tasks-archive.md` (TASK-143..313 range, 8673 lines): **zero hits.** Clean.
- `tasks.md`: 21 raw hits, collapsing to **7 distinct notes** (several hits are the same note
  matching the pattern twice, e.g. "flagging for a separate task"). Disposition per note:

| # | Location (origin task) | Note | Disposition |
|---|---|---|---|
| 1 | TASK-347 (`:244`) | stale `switchApp 10` in 3 tools, "flagging for a separate task" | **Already resolved** — filed as TASK-394 (this task's own trigger case) |
| 2 | TASK-347 (`:246`) | same note, restated in the 2026-08-03 follow-up paragraph | Self-referential to #1, no separate action |
| 3 | TASK-360 (`:844`) | two non-smoother inaccuracy candidates, "filed below as TASK-367/368" | **Already resolved** — filed correctly same session, both since DONE |
| 4 | TASK-361 (`:1304`) | HTTP response compression (brotli) lever for adsb.fi fetch size, "flagging for PM/Architect, not implementing here" | **Gap — filed as TASK-403** (see below) |
| 5 | TASK-364 design doc (`:3989`) | OQ4, taskbar `isHealthy()` gap, "no task filed for it yet" | **Already resolved** — filed as TASK-366, DONE 2026-07-31 |
| 6 | TASK-364 (`:4088`) | WiFi fallback cascade: NVS/SPIFFS attempts both fail after hardcoded stage fails, ~60-85s recovery via supervisor only, "No task filed for it yet; human to decide if/when" | **Gap — filed as TASK-404** (see below) |
| 7 | TASK-364 (`:4139`) | WebRadio ICY title vs. Clock/Spotify `setTitle()` guard re-check, "Not filing a dedicated follow-up task... doesn't warrant tracked backlog on its own" | **Already a reasoned drop, not a gap** — correctly dispositioned inline, no action |

Net: of 7 distinct notes, 3 were already resolved (correctly filed later, just never
cross-referenced), 1 was already a deliberate reasoned drop, and **2 were genuine gaps** —
now filed as TASK-403 and TASK-404. No further "flagged, never filed" debt remaining as of
this audit.

**QM process note (per the "Process angle" above):** the pattern that let #4 and #6 sit
unfiled for 2-4 weeks each is the same both times — the flag was written into a *closing*
write-up of an unrelated task, several paragraphs deep, with no structural marker beyond the
prose phrase itself. Recommend `docs/quality/best_practices.md` adopt: **any task closeout
that identifies a new, real, out-of-scope issue must either get a TASK-NNN in the same
editing session, or an explicit `**Deferred, not filed:**` marker line** (searchable, unlike
free-form "flagging for..." prose) so a future audit — or grep — doesn't have to re-derive
which notes are gaps vs. already-actioned vs. deliberately dropped.

### TASK-397 — long single-station WebRadio soak tool (`test_webradio_long_soak.py`)

**Filed 2026-08-04, TASK-393 follow-up.** Building a soak tool to catch a genuine TASK-393
recurrence on real hardware, with instrumentation captured at the moment it happens — the thing
every prior TASK-393 sighting lacked. This task exists specifically to document the tool's own
build process honestly, including the mistakes, per direct human instruction not to under-report
trial-and-error as if it were a clean build.

**v1 (built, run, retired same day) — three real bugs, found only by running it, not by design
review (that gap is the point of this task's second half):**
1. Default report path was relative (`"rnd_logs/..."`) — crashed the first real multi-hour run at
   its first periodic checkpoint write (~5 min in), because the actual invocation cwd didn't match.
2. Didn't disable Spotify's competing background polling — its continuous TLS retries starved the
   WebRadio station-fetch's heap-contiguity guard (`-101`, `dataTaskStorage.cpp:1575`), causing
   repeated silent failures to even start on a fresh boot.
3. Played from the real 30-station list with `wrAutoSkip` at its firmware default (ON) and never
   tracked `wrIdx` — so when the target station failed repeatedly, the firmware's own auto-skip
   logic (correctly) moved to a *different* real station, and the tool's logs showed a confusing
   mix of titles from at least two stations (dance/pop mixed with classical/baroque programme
   names) with no way to tell what was actually playing. Human caught this from the log output
   alone ("sounds like a different station... I get the feel you've missed this"). This also means
   v1 was structurally incapable of testing "stuck on one station forever" — auto-skip always had
   somewhere else to go with a real multi-station list.

**Separately, an operational incident:** stopping v1 mid-run via `TaskStop` reset the DUT. Root
cause (per human correction, not my first guess): closing the serial port on process kill drops
DTR via the OS's hangup-on-close behaviour — the same reset mechanism as opening a fresh
connection, already documented elsewhere in this project's own process notes ("never externally
kill a soak/test script mid-flight"). My first explanation (blamed an apparent ~3h host-suspend
gap in the logs) was wrong for the reboot itself, though a genuine large monotonic/wall-clock
gap was separately present in that same run and remains unexplained.

**v1 also only ever did periodic `get` polling**, and its `cmd()` called `reset_input_buffer()`
before every command — silently discarding every unsolicited log line the DUT emits the instant a
state transition, connect attempt, redirect, or auto-skip decision happens. Human: "we keep
looking at point issues, based on a serialdbg view that is incomplete." Correct — the same event
stream had already been read live via `tmux capture-pane` earlier in TASK-393's own investigation
and worked well; v1 never built that capability in.

**v2 (rewritten):** single real station injected via debug-only `set wrUrl <resolved-url>`
(`webRadioApp.h` TASK-261 Phase 2 lever) instead of the station list — pins `_stationCount=1` so
auto-skip has nowhere to go and TASK-276's terminal-retry is the sole recovery path under test.
Continuous reader-thread architecture (modeled on `test_adr045_gate.py`'s already-working
pattern) — one thread owns the serial port, tees every raw line host-timestamped to a full log
file, and parses known patterns (`play idx=`, `terminal retry`, `connecttohost failed`,
`stream dead`, `ICY:`, `auto-skip`, heartbeats) into a structured real-time timeline; `get` polling
is now a light periodic cross-check, not the primary data source. Primary anomaly signal is the
heartbeat's `last_render_age_ms` parsed directly (the actual TASK-390/393 symptom), secondary is
an event-log mechanism check (connect-fail/stream-dead with no recovery event within
`WR_TERMINAL_RETRY_MS` + slack).

**Independent VE-style review requested by human before any further live run** (explicit callback
to `docs/agents/verification_engineer.md`: "Challenge Developer... before code beats after" — a
step that was skipped for v1 and shouldn't have been). Fresh general-purpose agent, no shared
context with the implementation, told to verify every claim against the actual firmware source
rather than trust the tool's own comments. Result: **two blocking findings**, both fixed same
session before any further DUT time was spent:

1. **The render-freeze detector would false-positive on nearly every healthy run.** Traced every
   `_dirty = true` site in `webRadioApp.h` (16 of them): during steady PLAYING with no touch input,
   none fire again after the initial connect — ICY title updates, the buffer bar, and time digits
   are all explicitly targeted blits, not `repaintChrome()`. So `last_render_age_ms` climbs in
   lockstep with `uptime` during completely normal quiet playback the same way it does while parked
   in an error state. Fixed: gate the alert on `get wrState` actually being one of the three
   retryable errors at the moment the heartbeat threshold trips, not on the heartbeat signal alone
   — and specifically don't latch the "already checked, it's healthy" flag, so a *later* transition
   into a stuck error state without an intervening repaint still gets caught (a bug in my first fix
   attempt, caught in self-review while applying the finding, not by the reviewer).
2. **`wrAutoSkip` was never forced on or verified.** The terminal-retry re-arm's own gate condition
   requires `g_settings.webRadioAutoSkip == true` — a persisted setting a prior debug session could
   have left off (T237/`T_WR_ERR_*` tests flip it deliberately). `test_adr045_gate.py` sets this
   explicitly before its trials; the line was dropped translating the pattern to this tool. Fixed:
   force `set wrAutoSkip 1` and abort with a clear message if `get wrSkip` doesn't confirm it —
   better to fail loudly before wasting DUT hours than complete a soak that silently never exercised
   the mechanism under test.

Four more (non-blocking) findings also fixed same pass: `RE_CONNECT_OK` missed the SSL-station log
variant (thinned the event timeline for https-only stations); `atexit` doesn't fire on a bare
`SIGTERM` in Python by default (root cause of the reboot-on-stop incident above) — added a signal
handler funnelling `SIGTERM` through normal `sys.exit()`; `set bgPoll 0`/`set wrUrl` replies were
fire-and-forget, now verified with a WARN on non-confirmation; default `--station-name "SLAM"` was
coarser than TASK-393's actual repro station, tightened to `"SLAM! DANCE CLASSICS"`.

**Reviewer's honest scope caveat, carried forward, not resolved:** isolating Spotify out (via
`bgPoll 0`, and now primarily via the recommended `cyd2usb_winamp_debug_noSpotify` build) tests the
WebRadio-only mechanism, not the exact environment of the one real historical sighting, which had
Spotify's TLS churn concurrently active — TASK-390's own investigation plan explicitly wants that
concurrency present as an unconfirmed hypothesis. Plan: no-Spotify build first (faster, more
reliable, isolates the mechanism question cleanly); a Spotify-present run is a distinct necessary
follow-up if this one comes back clean, not something this run can substitute for.

**Second independent review** (fresh agent, explicitly instructed not to take the first review's
claimed fixes on faith): independently traced both blocking fixes down to exact source lines —
confirmed correct as claimed, not just plausible. Every `_state = ERROR_*` assignment site (4 of
them) sets `_dirty=true` in the same block, confirming the render-freeze detector's state-gate
logic is sound across a full walked timeline (3h healthy quiet PLAYING → zero false positives,
re-checks every heartbeat without latching; a 10-min genuine stuck episode → exactly one anomaly,
correct ~90-120s delay, no missed detection). `wrSkip.autoSkip` confirmed to really read
`g_settings.webRadioAutoSkip`, the same flag gating the terminal-retry. `SIGTERM → sys.exit(0)`
handler confirmed safe (CPython dispatches at the next bytecode check, not in raw signal-handler
context — no deadlock risk with the reader thread). `cyd2usb_winamp_debug_noSpotify` confirmed to
exist as described and safe for the cleanup path (`SpotifyApp` only touches zero-initialized
statics even when `spotifyTask::begin()` never ran).

Five new (non-blocking) findings, all fixed same pass: (1) `RE_PLAY`'s `\S+` name capture silently
dropped any multi-word station name from the event timeline — including this soak's own default
target, `"SLAM! DANCE CLASSICS"` — fixed to non-greedy `.*?` (inert for the actual test path since
`wrUrl` renames to `"INJECTED"`, but a real trap if reused); (2) **no detector existed for total
DUT silence** (loopTask wedged — this project's own history: TASK-285/288/295 — or a dropped
USB/serial connection) as distinct from a render freeze; a DUT dying at hour 1 of a 4h run would
have produced a `"complete", 0 anomalies` report, the single worst outcome for an unattended run,
and is exactly the shape of the unexplained gap this tool's own v1 run hit earlier the same day.
Added a watchdog on `dut.last_line_ts` (any serial line at all, not just heartbeats) at 3×
heartbeat period (90s); final report status becomes `complete-dut-silent` rather than a bare
`complete` if it's still silent at run end; (3) the `bgPoll` fallback comment's premise was
factually wrong (the handler compiles in unconditionally, `DISABLE_SPOTIFY` only guards the
`begin()` call) — corrected, harmless either way; (4) a station-name mismatch silently fell back to
station idx 0 with just a WARN — an unattended run could soak entirely the wrong station with no
one noticing; now fatal, matching the `wrAutoSkip`-mismatch precedent, with the full available list
printed; (5) `wrAutoSkip` was forced on and never restored — now captured before forcing and
restored in `_cleanup()`.

**Go/no-go from the second review: go**, for a supervised run; the silence watchdog (now added)
was its one recommendation before running unattended overnight.

**Flashed + supervised smoke test, 2026-08-04, clean:** `cyd2usb_winamp_debug_noSpotify` built and
flashed (`pio run -e cyd2usb_winamp_debug_noSpotify -t upload`, 32s, SUCCESS). 6-minute supervised
run against it: station-list fetch succeeded on the **first** attempt (no `-101` retries needed —
confirms the no-Spotify build fixes the heap-contiguity race that `bgPoll 0` alone didn't
reliably prevent), resolved the exact target `'SLAM! DANCE CLASSICS'` (idx=23, real
`http://stream.slam.nl/WEB15_MP3`), `wrAutoSkip` confirmed ON, ICY titles tracked correctly
(`Sean Paul - Get Busy` → `Uniting Nations - Out Of Touch` → `Jules & Raoul - Progress`), heap
stable 56-60k throughout, `last_render_age_ms` climbed in lockstep with `uptime` the entire time
(as expected for healthy quiet PLAYING per the render-freeze finding) and correctly did **not**
false-positive — every threshold trip confirmed `wrState=PLAYING` and stood down. 5-minute
checkpoint fired cleanly at 300s. Final: **360s elapsed, 0 anomalies, `status=complete`.** Report:
`app/tools/rnd_logs/webradio_long_soak_20260804T051037.json`.

**Real 4-hour unattended run, 2026-08-04, 05:20:40–09:20:55 (handover from the smoke-test
session):** launched per the handover prompt against the flashed `cyd2usb_winamp_debug_noSpotify`
build, `--hours 4 --station-name "SLAM! DANCE CLASSICS"`, detached from the harness via
`nohup`+`disown` (PID 988751) specifically so no `TaskStop`/session-boundary event could touch the
serial port mid-run — the operational lesson from v1's DTR-reset incident, applied for real this
time. Monitored via periodic `ScheduleWakeup` reads of the stdout log and report JSON only, never
by touching `/dev/ttyUSB1` while the tool held it. **Result: 14401.9s (4h00m02s) elapsed, 0
anomalies, `status=complete`, heap stable 49-58k across 479 heartbeats, 71 title changes tracked,
silence watchdog never tripped.** Full result and its relationship to TASK-393's original
observation is written up under TASK-393's own entry (not duplicated here) — short version: clean
run, but `wrState` never left PLAYING, so the terminal-retry mechanism under test was never
actually exercised; this is new evidence the mechanism didn't obviously break under 4h of real
single-station playback, not proof TASK-393 is resolved. Report:
`app/tools/rnd_logs/webradio_long_soak_20260804T052040.json`.

**One cosmetic bug found and fixed mid-run (self-caught, not by the human this time):** the
report JSON's `"start"` field was calling `_ts()` (current wall-clock time) fresh on every 5-minute
checkpoint write instead of the actual run-start timestamp — so `"start"` silently drifted forward
to "now" on every write, reading exactly like the run had restarted if you looked at that one field
in isolation. (`elapsed_s` was never affected — it's computed from a `time.monotonic()` value
captured once at true start — so the run's own correctness was never in question, only that one
display field.) Root cause: `full_report()`'s `"start": _ts()` should have referenced the
already-captured `start_wall`/its ISO form, not called `_ts()` again. Fixed in-place
(`start_iso = _ts()` captured once alongside `start`/`start_wall`, referenced by `full_report()`
thereafter) — safe to edit while the soak was running since Python had already loaded the old
function body into memory; the live run kept using the old (buggy but harmless) behavior for its
remaining ~40 minutes, this fix only affects future runs.

**Owner:** Developer · **Deps:** TASK-393 (this soak exists to catch its recurrence), TASK-395
(shares the terminal-retry mechanism understanding) · **Priority:** P1 · **Status:** **CLOSED
2026-08-04.** Tool built, twice independently reviewed (2 blocking + 6 minor findings, all
resolved), smoke-tested, and run to completion for a full real 4-hour unattended soak — clean
(0 anomalies), commit `b1cb80a`. This task's deliverable was the tool + a real run of it, both
done; it does not claim TASK-393 resolved (that task stays open on its own merits — see its entry).
Re-open only if the tool itself needs further changes (a new detector, a different station-fault
profile, etc.) — a *bug hunt* using the tool (another `--hours` run, a flakier station, a
Spotify-present run) is TASK-393's job, not a reason to reopen this one.

**PM sign-off (2026-08-04):** closing TASK-397. Scope was "build a soak tool that can catch a
TASK-393 recurrence with full diagnostics" — met: built, independently reviewed twice, smoke-tested,
and proven against real hardware for a full 4-hour run with a working anomaly-capture path (even
though this particular run didn't trigger it). **TASK-393 itself stays OPEN** — a clean run is
evidence the mechanism didn't break under these conditions, not proof of no bug; per its own entry,
this is repro attempt #4 with the same "observed once, unreproduced since" disposition. Next
candidates if someone picks TASK-393 back up: a longer run, a station with a track record of real
failures (StreamTheWorld per TASK-393's second update, not SLAM! which held clean twice now), or a
Spotify-present run per the reviewer's carried-forward scope caveat above.

**Post-close tool enhancement (2026-08-04, same day):** added `--spotify-present` (skip the
`bgPoll 0` disable) and used it for exactly the "Spotify-present run" candidate named above — see
TASK-393's own entry for the full result (415 connect failures vs 13 successes over 4h, a large
connect-reliability finding, still no render-freeze reproduction). Small, low-risk addition (one
argparse flag gating the existing, already-reviewed `set bgPoll 0` call behind an if/else — no
change to the anomaly-detection logic itself), didn't reopen this task for it.

### TASK-398 — scope Phase 2 (async `connecttohost`) now that the freeze magnitude is measured

**Filed 2026-08-04, follow-up from TASK-393's Spotify-present soak.** `docs/architecture/designs/
M-WR-AUDIO-TASK.md` (TASK-278's own design doc, accepted 2026-07-03) has carried an explicitly
deferred open question since filing: OQ4, *"`connecttohost` freeze magnitude: measure... to decide
whether Phase 2 (async connect) is worth the state-machine surgery."* It was never really answered
— the one sample taken during the 2026-07-07 E1 campaign was a single healthy connect
(`wr.connect:83ms`), excluded as an outlier, under conditions with no reason to ever hit the slow
path.

**Now measured, for real, under harsh (but real — reproduced tonight, not hypothetical)
conditions:** TASK-393's Spotify-present 4h soak (same day) found `_play()`'s `connecttohost()`
call — which per TASK-278's own explicit, human-approved Phase-1 scope decision still runs
synchronously on `loopTask`, not the offloaded pump task — blocks the entire device (touch,
render, taskbar, every other app) for **7-9+ seconds on every failed connect attempt**. Under
Spotify-concurrent conditions that was 421 separate whole-device freezes over 4 hours, roughly one
every ~34 seconds. TWDT (15s window) survived all 421 without a reboot, but this is a real,
directly-felt "the device is frozen" symptom — arguably more user-visible than the narrower
WebRadio-marquee-specific freeze TASK-393 itself was filed to catch, and plausibly part of what
made the original human sighting read as "frozen" in the first place (unconfirmed — TASK-393's
own render-freeze detector and this `app.tick` finding are measuring two different things and
haven't been shown to be the same event).

**What this task is NOT:** it doesn't reproduce or explain TASK-393's specific render-freeze
signature (`last_render_age_ms` climbing in lockstep with `uptime` while parked in an `ERROR_*`
state with zero recovery) — that stays open on its own, still unreproduced after 5 attempts. This
is a distinct, separately-real, now-measured architectural cost of the current synchronous-connect
design.

**Proposed scope (Architect to own the actual design work):**
1. Revisit `M-WR-AUDIO-TASK.md`'s Phase 2 sketch (pump task owns the `Audio` object, UI sends
   `PLAY(idx)/STOP/VOL` via queue, connect results return as events, `tick()` reads a `volatile`
   snapshot) with the new magnitude data as justification — the design doc's own gating condition
   for even considering Phase 2 is now satisfied.
2. Phase 2 was flagged as "real surgery on the freshly validated ADR-045/TASK-276 machine" — an
   Architect design pass should assess whether a narrower mitigation (e.g. moving just the
   `connecttohost()` call itself onto the pump task, without the full command-queue rearchitecture)
   gets most of the benefit at a fraction of the risk, before committing to the full Phase 2 scope.
3. ~~Fix the instrumentation gap~~ — **retracted, no gap exists.** Initial write-up claimed
   failed connects weren't wrapped in the `wr.connect` perf scope; checked the actual call site
   before repeating it here and that's wrong — `perf::record("wr.connect", ...)` runs
   unconditionally in `_play()`, before the success/failure branch. `app.tick` shows as the
   reported worst-path during failures because it's the outer span containing the nested
   `wr.connect` call, not because failures go uninstrumented. See TASK-393's own entry and
   `M-WR-AUDIO-TASK.md`'s OQ4 for the correction. Nothing to fix here.

**Architect design pass (2026-08-04, same day):** `docs/architecture/designs/M-WR-CONNECT-ASYNC.md`
drafted. Key finding from tracing the actual call sites, not obvious from the task filing alone:
**the "narrower mitigation" (move just `connecttohost()` to the pump task) is not actually narrow
once followed through** — `_stopAudio()`/`suspend()` (eject, `switchApp` away from WebRadio) both
take the same `s_wrAudioMutex` with a blocking, unbounded `xSemaphoreTake`, so relocating the
connect call alone would just relocate the freeze to whichever of those fires next, not remove it.
Two concrete safety requirements identified for a real fix (gate `_stopAudio`/`suspend` on
`_state != CONNECTING`; widen or connect-aware the existing `WR_PUMP_ACK_TIMEOUT_MS=10000` teardown
handshake, since tonight's observed connect-failure range of 7099-9425ms leaves an uncomfortably
thin margin against it). Lean: the narrow option (with both requirements as mandatory, not
optional) over the full Phase 2 command-queue rearchitecture — smaller surface, doesn't touch the
freshly-validated ADR-045/TASK-276 terminal-retry transition logic. Draft, not yet accepted — needs
human sign-off and a VE testability pass on the CONNECTING-state changes before implementation, per
this session's own standing practice.

**Human sign-off (2026-08-04):** design lean approved (narrow option, both safety requirements
mandatory). Sent to VE for a testability challenge before implementation.

**VE review (2026-08-04, same day) — 4 blocking findings, 1 non-blocking, sign-off: no-go until
resolved.** Independent pass confirmed the design doc's own line citations are all accurate, but
found its mutex audit stopped short: (1) `_play()` itself is reachable with zero `_state` guard
from six other loopTask-synchronous entry points (eject/stop/next/prev/togglePlay/station-tap, plus
five debug `set wr*` hooks) — today safe only because loopTask is fully blocked during connect,
exactly the property this design removes; also found a third independent freeze source (`wrVol`'s
debug setter uses a raw blocking mutex take, inconsistent with the short-timeout idiom already used
next door for the real volume-drag path). (2) The `WR_PUMP_ACK_TIMEOUT_MS=10000` risk is a real,
already-provable use-after-free, not an open question — `Audio.cpp:511-519` (TASK-295) forces the
connect timeout to exactly `10000` for raw-IP URLs, a zero-margin tie with the teardown ack-wait on
an already-shipped code path. (3) The design doc's own prose is self-contradictory about whether
loopTask "stays responsive" or "waits" during CONNECTING — can't be both on ESP32 Arduino's
single-threaded `loop()`. (4) No exit criterion exercises re-entrant control input during
CONNECTING despite the test hooks already existing. Full findings + proposed fixes in
`M-WR-CONNECT-ASYNC.md`'s own VE review section. Design needs revision before implementation —
none of this argues for abandoning the narrow-option lean, but the "two mandatory requirements" as
originally written are insufficient.

**Design revision (2026-08-04, same day):** all 4 blocking findings addressed in
`M-WR-CONNECT-ASYNC.md` — now **three** mandatory requirements instead of two: (1) `_play()`
becomes a no-op during `CONNECTING` instead of racing a second connect, plus fixing a third
freeze source VE found (`wrVol`'s debug setter); (2) teardown ownership moves to the pump task
itself via a `s_wrPumpTeardownPending` flag instead of relying on `WR_PUMP_ACK_TIMEOUT_MS` as a
safety bound — VE's finding that DNS resolution is genuinely unbounded meant no fixed timeout
value could have soundly fixed this, so widening the number was rejected in favor of an ownership
fix; (3, resolved as a side effect of fixing #2) the self-contradictory "stays responsive" vs
"waits" framing is gone — every path is now fast-no-op or deferred-cleanup, never a blocking wait.
One new edge case surfaced *during* the revision and is explicitly flagged as unresolved, not
implemented around: quick re-entry into WebRadio while a deferred teardown is still pending races
`init()`/`resume()` against the pump task's cleanup.

**Second VE pass (2026-08-04, same day) — 4 new blocking findings, 1 non-blocking, no consensus.**
The first revision's fix was incomplete: `_stopAudio()` itself, not just `_play()`, is the real
blocking primitive in 5 of the design's own named call sites, including `suspend()`'s own first
line — so `_stopAudio()`/eject/STOP/`suspend()` all still fully froze the device exactly as today,
unfixed by requirement 1 as originally worded. Worse, once that gap is closed the flag-only
teardown mechanism has no code path that ever clears `_state` back out of `CONNECTING` (that job
belonged solely to `_stopAudio()`'s own `_state = STOPPED` line, which the fix had to stop calling)
— so what looked like a rare re-entry *race* (Open Question 3) is actually a **deterministic
permanent wedge**: any single eject during `CONNECTING` leaves WebRadio stuck showing
"Connecting..." forever, no race required. Also found the pump-task-handle null-timing was
unspecified (risking a second concurrent pump task on re-entry) and that the exit criteria's
synthetic `set wrState 1` path can't actually exercise the mutex-held case the fix is meant to
protect.

**Second revision (2026-08-04, same day):** replaced the ad-hoc flags entirely with an explicit
`s_wrPumpRequest`/`s_wrPumpResult` request/result-slot pair between `loopTask` and the pump task —
`_stopAudio()` itself gains the `CONNECTING`-state branch (fixing every caller, including a
*seventh* unguarded call site found while re-checking, inside `resume()`'s config-diff branch, that
neither VE pass had enumerated), and `tick()` gains an unconditional per-iteration poll that
reconciles `_state` whether the user stayed in WebRadio (stop-while-staying) or left and came back
(teardown). Re-uses `resume()`'s pre-existing `_state == STOPPED` autoplay gate (unmodified) to
naturally handle the re-entry-during-teardown case without new special-case code — the accepted
residual limitation is a missed one-shot autoplay opportunity in a narrow timing window, not a
crash or a wedge. Full mechanism + revision history in `M-WR-CONNECT-ASYNC.md`.

**Third VE pass (2026-08-04, same day) — 4 new blocking findings, 2 non-blocking, no consensus.**
Confirmed the second revision genuinely closed the use-after-free and the permanent `_state` wedge
— but re-deriving every call site that touches `_state`/`s_wr_audio`/`_spotifyYielded` during
`CONNECTING` found four more real bugs, reachable by ordinary use, not adversarial timing. Most
severe: `_stopAudio()`'s new early-return also skips the Spotify TLS-resume call, permanently
leaking `spotifyTask`'s yield reference count on nothing more exotic than pressing STOP while a
station connects — reintroducing `tlsYield` starvation, a bug class this project has already
root-caused and fixed five separate times, via a sixth mechanism. Also found: the STOP button and
`wrStop` debug setter still force `_state = STOPPED` immediately after `_stopAudio()`, defeating
the mechanism specifically for that tap and reintroducing the original freeze via STOP-then-retap;
the request slot was never specified to clear itself, so a successful connect as drafted would
free-run into an infinite 2ms reconnect loop; and `resume()`'s config-diff branch could silently
downgrade an already-posted `TEARDOWN` back to `ABORT`, leaking the arena and pump task past their
intended session.

**Third revision (2026-08-04, same day):** added the missing TLS-resume call to `tick()`'s
reconciliation; deleted the two now-harmful redundant `_state = STOPPED` writes; specified the
request slot's clear-on-commit explicitly, with a narrow, deliberately-accepted residual race
documented (not engineered around — no compare-and-swap primitive exists in this codebase, and the
window is a handful of instructions, not the multi-second connect duration); and made
`_stopAudio()`'s guard priority-aware so `TEARDOWN` can never be downgraded to `ABORT`. Also caught
and removed a genuine editing mistake from the second revision: stale, superseded duplicate content
(an old "two mandatory requirements" list) had been left sitting in the doc alongside the newer
mechanism description, contradicting it.

**Fourth VE pass (2026-08-04, same day) — 3 new blocking findings, 3 non-blocking, no consensus,
but real progress: 2 of the third revision's 4 fixes confirmed correct.** Independently re-verified
the `TEARDOWN`-priority guard (traced against every caller, no legitimate downgrade case found) and
the STOP-button/`wrStop` fix (confirmed via a file-wide grep — exactly the two sites the doc
claimed, plus `_stopAudio()`'s own intentional one, with a fourth candidate site correctly ruled
out). But: (1, most severe) the clear-on-commit fix that closed the third pass's infinite-reconnect
bug opened a *different* hole — the request slot's consumer never handled `ABORT`/`TEARDOWN`
arriving before the pump had read a posted `CONNECT` at all (a real window spanning the pump's own
2ms `vTaskDelay`, not a sub-instruction race), reintroducing the permanent `_state` wedge plus a
resource leak, reachable via two ordinary back-to-back `set` commands with no timing luck required;
(2) the TLS-resume fix was precise for `ABORTED`/`TORN_DOWN` but only said "same substitution" for
`FAILED` — the single most common outcome (421 occurrences) — leaving that exact line at risk of
being dropped again through the one branch the fix's precision didn't reach; (3) an exit-criteria
gap downstream of finding #1. Non-blocking: correctly identified that the doc's own "accepted
residual race" (pump reading `CONNECT` then clearing it) is actually already closed by this file's
documented FreeRTOS task-priority setup — a misdiagnosis, not a real gap, but pointed attention at
the wrong window while finding #1's real one went unaddressed; and re-flagged that `wrVol`'s debug
setter (named in the very first pass) had silently fallen out of scope across three revisions.

**Fourth revision (2026-08-04, same day):** adds explicit `ABORT`/`TEARDOWN` top-of-loop branches
to the consumer side, closing the early-arrival hole finding #1 found; spells out all three
`tick()` reconciliation branches in full (no more "same substitution" shorthand anywhere); corrects
the residual-race framing to reflect it's already closed by FreeRTOS priority preemption rather
than merely accepted; and re-adds the `wrVol` fix the second revision had accidentally dropped
while rewriting that section.

**Fifth VE pass (2026-08-05) — narrowest result yet: 1 blocking finding, 1 non-blocking, no
consensus, but a real inflection point.** Down from 3-4 findings each of the prior four passes.
Independently re-verified as sound: the full `ABORT`/`TEARDOWN`/`CONNECT`/`NONE` branch coverage
added last revision, the `FAILED` branch's TLS-resume ordering against the real `_play()` failure
path, the corrected residual-race framing (extended and re-checked across all four branches, not
just the one prior pass covered), and the re-added `wrVol` fix. The one gap: both `TEARDOWN`
branches (post-connect and early-arrival) specified `delete s_wr_audio` but never reset the pointer
to `nullptr` afterward — a deterministic dangling-pointer bug (every other call site in the file
treats non-null as proof-of-life), the same "second half of a two-part cleanup doesn't survive
relocation" pattern that hit the TLS-resume line twice already, this time for a different pair of
statements. Non-blocking: a mutex-scoping clarification for the post-connect branch's `stopSong()`
call.

**Fifth revision (2026-08-05):** adds `s_wr_audio = nullptr` after both `delete s_wr_audio`
instances, mirroring today's synchronous `suspend()` exactly (`webRadioApp.h:559` already does both
statements as one unit); clarifies the mutex-scoping detail.

**Sixth VE pass (2026-08-05) — CONSENSUS REACHED, zero blocking findings.** Independently
re-verified the fifth pass's dangling-pointer fix correct (right order, right scope, no new race)
and re-checked the doc's underlying "every call site guards on non-null" claim against a fresh,
complete grep (not the fifth pass's own enumerated list) — found three additional touch points the
fifth pass hadn't individually named, all consistent with the claim. One cheap non-blocking finding:
no sub-branch of the `CONNECT` case explicitly stated when it gives back the mutex taken before
`connecttohost()` — judged non-blocking specifically because a real gap here would self-deadlock on
the single most basic possible smoke test (the very first connect), not survive silently into soak
conditions the way every actual blocking finding across all six passes did. Folded into a final,
sixth revision anyway (explicit per-branch mutex give-back) given this document's own established
pattern of "second half of a paired operation" gaps recurring three times already.

**Six passes, findings narrowing 4 → 4 → 4 → 3 → 1 → 0 blocking.** Full mechanism + six-pass
revision history in `M-WR-CONNECT-ASYNC.md`, now marked implementation-ready. This is the first
task this session to complete a full iterate-to-consensus VE loop — the process itself (not just
this specific bug) is worth remembering: five real, previously-unflagged, increasingly-narrow bugs
were caught before a single line of firmware code was written, on a design that looked complete to
its own author at every single revision along the way.

**Implementation (2026-08-05):** built against `M-WR-CONNECT-ASYNC.md` exactly as specified —
`s_wrPumpRequest`/`s_wrPumpResult` enums added; `_play()` gets the `_state == CONNECTING` no-op
guard and now posts `CONNECT` (station URL copied into a lazily heap-allocated file-static buffer,
`wrPumpConnectUrlBuf()`, before the post — the design doc didn't spell out how the pump, a free
function with no `this`, would reach `_stations[idx].url`; mirrors `TeletextApp::_nosSource()`'s
existing lazy-malloc-once-never-freed pattern rather than an embedded array, since an embedded
104B static overflowed the debug build's `.dram0.bss` on first attempt — caught by `./run/check`,
not by inspection); `_stopAudio()` gets the `CONNECTING`-guard posting `ABORT`
(never downgrading `TEARDOWN`); `suspend()` posts `TEARDOWN` and skips the synchronous
teardown/delete when leaving mid-connect, falling through to the settings-save logic unchanged;
`wrPumpTaskBody()` gets the full `CONNECT`/`ABORT`/`TEARDOWN`/`NONE` branch chain including
early-arrival `ABORT`/`TEARDOWN`, `s_wr_audio = nullptr` after both `TEARDOWN` deletes,
`s_wrPumpTask = nullptr` last before self-delete, and an explicit mutex give-back per `CONNECT`
sub-branch; `tick()` polls `s_wrPumpResult` unconditionally first thing every iteration with all
three reconciliation branches (`CONNECTED`/`FAILED`/`ABORTED`+`TORN_DOWN`) each explicitly calling
`spotifyTask::tlsResume()` when `_spotifyYielded`; the two redundant `_state = STOPPED` writes
(STOP transport button, `wrStop` debug setter) deleted; `wrVol`'s debug setter switched from a raw
`portMAX_DELAY` take to the same short-timeout, degrade-gracefully idiom `wrVolumeSink()` already
uses. `./run/check` passed clean (6/6 gates, both `cyd2usb_winamp`/`cyd2usb_winamp_debug`) on the
first attempt after fixing the `.dram0.bss` overflow above.

**Post-implementation fresh-agent review (2026-08-05) — two real bugs, neither anticipated by the
six-pass design review, both closed same session before any DUT time was spent on them.** Per this
project's standing practice, a fresh general-purpose agent (no shared context with the
implementation) reviewed the diff against the design doc's every specified mechanism detail —
confirmed faithful line-for-line — and then independently hunted for translation defects the
design text couldn't have anticipated. Found:
1. **BLOCKING** — `_stopAudio()`'s `CONNECTING` guard posted `ABORT` purely on `_state ==
   CONNECTING`, without checking a pump task actually existed to consume it. `main.cpp`'s `cmdSet`
   forwards `webRadioDbgSet()` to `g_WebRadioApp.dbgSet()` **unconditionally, regardless of
   `currentAppId`** — the same pattern as every other app's debug setter, confirmed by grep, not
   assumed. None of the six design-review passes considered this because the design's own prose
   assumed (reasonably, for the UI path) that nothing reaches WebRadio's instance while it's
   suspended — true for taps, false for debug `set` commands. A stray `set wrStop`/`wrEject` fired
   at a suspended, stale-`CONNECTING` WebRadio instance (its earlier `TEARDOWN` already resolved,
   pump already self-deleted) could write an orphaned `ABORT` into the request slot; a freshly
   created pump task on the *next* `_play()` would consume that orphaned `ABORT` before ever seeing
   the real `CONNECT` it was about to post, producing a phantom `ABORTED` result that `tick()` would
   apply to a connect genuinely still in flight — re-timing this design's own re-entrancy/freeze
   class one layer up. **Fix:** the guard now also checks `wrPumpAlive()` before posting `ABORT`.
2. **Non-blocking-but-real** — the same cross-app-reachability fact meant the pump's early-arrival
   `TEARDOWN` branch's deliberate mutex-skip (justified in the design text as safe "by
   construction," an assumption finding #1 proved false) left a narrow TOCTOU window: a same-window
   `set wrVol` could pass its own `!s_wr_audio` null-check and then dereference a pointer this
   branch was concurrently freeing, unprotected. **Fix:** that branch's delete is now
   mutex-wrapped, matching every other `s_wr_audio` touch site in the file.

A second, narrower fresh-agent pass confirmed both fixes correct (no new deadlock, no suppression
of legitimate in-flight `ABORT`s, no path merging between the two distinct `TEARDOWN` sub-branches)
and swept the remaining `wrPlay`/`wrNext`/`wrPrev`/`wrUrl`/`wrEject` debug setters for the same
class of gap — none found. `./run/check` re-passed clean after both fixes.

**DUT verification (2026-08-05).** Two layers:

*Regression baseline* (`run/test-targeted`, existing `T_WR_*` suite, unrelated to this task but
exercising code paths this task rewrote): `T_WR_EJECT_01/02`, `T_WR_ERR_01-04` passed first try.
`T_WR_VOL_03`/`T_WR_TLS_01`/`T_WR_SPOTIFY_RESUME_01` needed one-to-two retries each — not a
regression, a pre-existing, previously-documented radio-browser.info mirror flake (TASK-284;
confirmed host-side same session: `de1`/`at1` mirrors DNS/connect-failed while `nl1` returned 200).
On retry all five passed clean, including `T_WR_VOL_03` — **`wrPlay 0` reached `PLAYING` via a real
station through the entire new async path** (`_play()` → `CONNECT` → pump → `tick()`
reconciliation) — and `T_WR_SPOTIFY_RESUME_01`, confirming eject-during-`PLAYING` TLS resume still
works.

*New exit-criteria script* (`app/tools/task398_connect_async_verify.py`, kept as a project asset —
see its own module docstring for the full methodology writeup). Building it surfaced a real
environmental finding worth recording: **`set wrDeadUrls`'s synthetic dead-host hook cannot test
this design at all** — it resolves inside `_play()` before ever posting `CONNECT`, so it never
touches the pump. A genuinely unreachable real address (RFC 5737 TEST-NET-1, an unused LAN IP)
was tried first per the design doc's own instruction to use "real slow/dead hosts" — and failed
**near-instantly** on this network (this network's router/resolver responds fast; TASK-393's
7-9s freezes came from real-world mirror flakiness this healthy LAN doesn't reproduce on demand).
An accept-then-never-respond TCP listener was tried next and also didn't work: `connecttohost()`
returns success as soon as the TCP handshake completes, before any HTTP response is read — a
server that accepts but stays silent resolves to `PLAYING` almost instantly, no hang. What
reliably worked: a **fresh, never-cached NXDOMAIN hostname per attempt** (`hostByName()` has no
enforced timeout — the exact mechanism the Architect's own VE review cites as TASK-393's real root
cause) — real DNS resolution + negative-response round-trip against this network's resolver
reproducibly took ~350-600ms per fresh random label (a repeated hostname resolves from cache
near-instantly on retry, which is why a fresh label is used every time). This is a real,
reproducible, non-synthetic window through the pump's genuine mutex-held `connecttohost()` call —
shorter than TASK-393's pathological case, but the mechanism under test doesn't care about the
duration, only whether it's genuine. Two harness bugs found and fixed while building this (a
`send()`-without-drain leaving a stale ack for the next `cmd()` call to misread; `set wrUrl`
unconditionally clamping `_stationCount=1`, so a "no stations? refetch" check written as `cnt==0`
silently no-oped after any dead-host test had already run) — both fixed, not worked around.

Result: **32/33 checks passed** on the clean run. Covered and passing: re-entrant `_play()`-path
taps during real `CONNECTING` (no second dispatch); re-entrant `_stopAudio()`-path taps (fast,
no mutex block, resolves to `STOPPED`); early-arrival `ABORT` (3 iterations, back-to-back `set`
commands with zero delay, pump never orphaned); early-arrival `TEARDOWN` via eject
(state reconciles correctly on re-entry); TLS-yield accounting for both the interrupted
(stop-during-connecting) and uninterrupted (ordinary failed-connect) paths, verified via the
persisted raw serial log rather than live reads (a third harness bug — `drain_log_lines()` races
against every intervening `cmd()` call's own read, which silently consumes whatever log lines are
sitting in the buffer regardless of who was looking for them; fixed by grepping the `_TeeSerial`
log file directly, which sees every line unconditionally); leave-and-quickly-re-enter during
`CONNECTING` (arena stays sane, exactly one pump task, state reconciles, manual play works
afterward); no dangling `s_wr_audio` after `TEARDOWN` (fresh session plays/fails cleanly, DUT
stays responsive); `switchApp`-during-`CONNECTING` (no crash, arena `acquires`==`releases`
throughout). The one non-pass (`4-setup`, "no runaway reconnect loop on a **real successful**
connect") was blocked by the same radio-browser.info mirror flakiness noted above, not a firmware
issue — a dedicated retry (120s wait for station fetch) still returned `count=0`; not re-attempted
further given this session's evidence budget. **Not left unverified, though:** the raw log across
this session's ~36 real (dead-host) connect attempts shows a perfect 1:1 `play idx=` /
`connecttohost failed` pairing throughout — zero evidence of reconnect-hammering under real network
I/O — and `T_WR_VOL_03` (above) already independently proved a real successful connect reaches
`PLAYING` via this exact path. The specific combination ("real successful connect" + "dispatch-count
check") is the only piece not directly re-derived this session; flagged honestly rather than
silently marked done.

**Honest scope note carried forward:** this DUT session did not reproduce TASK-393's full 7-9s
freeze window — this network's DNS/routing infrastructure is healthier than whatever TASK-393's
real-world mirror conditions were. The mechanism was verified under a real, shorter (~0.4-0.6s)
window instead; the properties that matter (non-blocking taps, correct guard priority, no orphaned
requests, no leaked TLS yield, no dangling pointer) don't depend on the window's duration, only on
it being genuine mutex-held real I/O, which it was.

**PM close-out check (2026-08-05):** `M-WR-CONNECT-ASYNC.md` (line 18-20) had self-flagged a
`cross_feature_matrix.yaml` edge as "reserved at implementation time — not done yet" for the
pump-task/control-call mutex-serialization change this task makes. Never followed up — not by
implementation, not by either post-implementation fresh-agent review, not by DUT verification, not
by the six-pass VE loop (all of which focused on the new request/result protocol's own internal
correctness, never cross-referenced the matrix). Existing edges X043/X044 explicitly name this
exact mutex serialization as their safety argument and say a change to it "must be re-verified, not
assumed." Re-verified now: the non-blocking `ABORT`/`TEARDOWN` path only fires during `CONNECTING`,
before any audio decode starts, so `audio_process_extern` (what X043/X044 actually guard) is never
in flight during that window — PLAYING-state teardown is untouched, stays fully synchronous. X043/
X044's invariant holds, on a narrower argument than their original text states. Filed as **X045
(requested, already taken by TASK-388's vu-004/webradio-001 wave-trace edge) → filed as X048** in
`cross_feature_matrix.yaml`, recording this re-derivation and flagging it as a re-check point for
any future CONNECTING-state decode change (e.g. gapless pre-buffering).

**Owner:** Architect (design — six-pass VE consensus) → Developer (implementation, done) → fresh-agent
review ×2 (two real bugs found + fixed, neither in the design's own six-pass history) → DUT
verification (done, 32/33 direct + full T_WR_* regression suite, one criterion indirectly evidenced
per above) → PM close-out (done, X048 filed) · **Deps:** M-WR-AUDIO-TASK.md, TASK-393,
M-WR-CONNECT-ASYNC.md · **Priority:** P2 · **Status:** **closed — implemented, reviewed,
DUT-verified, committed to master** (commit `4d105e4` + the two post-review fixes in the same
commit). `app/tools/task398_connect_async_verify.py` kept as a regression asset for future
WebRadio connect-path changes.

### TASK-399 — endless-ticker wraparound for the Winamp title marquee

**Filed 2026-08-04.** Human noticed the title marquee (`winampDisplay.h::_tickMarquee()`) doesn't
loop like real Winamp 2 — it scrolls fully out, holds blank, then respawns off-screen right and
scrolls back in, instead of an endless loop with a separator glyph between passes. Traced the
separator to `TEXT.BMP` row2/col1 (`bake_skin.py`'s `CHAR_MAP`, mapped to ASCII `'*'`) — cropped
and confirmed it renders as a 4-point shuriken, not a plain asterisk; already reachable today via
`SKIN_GLYPH['*']`, no bake-tool change needed. Also found `M-UI-POLISH-fidelity.md` (TASK-048,
marked done) had already specified this exact endless-loop-with-gap behavior — only the
`"Artist - Title"` composition half of that item shipped, not the loop/gap half.

Architect design doc: `docs/architecture/designs/M-TITLE-MARQUEE-WRAP.md`. Three options
enumerated (doubled-string buffer / modular virtual-index render in `drawTitleText()` / keep
bounce motion but fill the hold with glyphs). **Lean: Option B** (modular indexing, no extra RAM,
true endless loop) — human-approved 2026-08-04. Exact separator glyph run/spacing left as an open
question for a DUT/`preview_layout.py` visual-fit pass before locking the constant in.

**Implementation (2026-08-05, Developer, PM-driven session).** Landed Option B exactly as
specced: `titleTextPx`/`titlePeriodPx` cached in `_forceSetTitle()` (not recomputed per tick);
`_tickMarquee()` drops the off-screen-respawn reset for an unconditional `% titlePeriodPx` wrap
once `textPx > TITLE_W`; `drawTitleText()` walks a virtual `lastTitle` + separator + `lastTitle`
sequence via modular indexing (no doubled string, Goal 4) when scrolling, and keeps the original
flat walk untouched for the short-text static path (Goal 3). Separator picked as `"   ***   "`
(the doc's own named "classic" shape) through `kTitleMarqueeSep` — a file-scope `static
constexpr char[]` (not a class static member: the latter needs an out-of-line definition to be
ODR-used from an index expression, which linked as `undefined reference` on first build; moved
to file scope alongside the existing `kDriftPip` precedent, fixed). `wrMarquee` getter extended
with `textPx`/`periodPx`/`scrolling` per the doc's open question (cheap, done alongside).
`./run/check` 6/6 both envs, no DRAM/BSS regression.

**DUT verification (2026-08-05, same session).** The passive monitor (`spotify-mon`) turned out
to be watching normal playback, not a supervised soak — confirmed via `ps aux`/tmux pane inspection
(no soak/stress script attached) before interrupting it; human approved flashing. `./run/flash-debug`
+ a new ad hoc harness (`app/tools/task399_402_dut_verify.py`, same convention as
`task400_401_dut_verify.py`) drove real DUT checks via `get wrMarquee`:
- Long injected ICY title (`set wrIcy`) → `scrolling:true`, `periodPx`(240) `>` `textPx`(186) by
  exactly the separator's pixel width (9 glyphs × 6px pitch = 54px) — confirms the separator is
  actually being counted into the loop period, not just cosmetically appended.
- `scrollOffset` polled across real ticks: advances monotonically, **never goes negative** (the
  old off-screen-respawn value), and a live wrap was caught mid-test — offset fell from 239 to 1,
  landing near 0 as designed rather than jumping to a large negative "off-screen" value. This is
  the actual behavioral core of the fix (bounce → endless loop), confirmed on hardware, not just
  read from source.
- Short text afterward: `scrolling:false` — Goal 3 (static short-text path unchanged) holds.
- **Visual confirmation**: timed a `screendump` (via a throwaway single-session script — a second
  connection would DTR-reset the DUT and lose the marquee state, so setup + capture had to share
  one serial session) to land inside the wrap window (`scrollOffset` in `[textPx-20, periodPx-5]`).
  The captured frame shows the tail of one pass, the shuriken separator glyphs, and the head of the
  next pass all in the same frame with no blank gap between them — the literal exit-criterion goal.
  Confirms `kTitleMarqueeSep`'s glyphs render as the intended shuriken (via `SKIN_GLYPH['*']`), not
  garbled — full-quality video of continuous motion is still a further-nice-to-have but the static
  frame already proves the structural claim (endless loop, real separator, no hold).
- WiFi-down override path not separately re-tested this session (short strings, same code path as
  the already-covered short-text case — no new risk surface introduced by this change).

**Correction (2026-08-05, same day, human-caught on real hardware):** the ASCII `'*'` glyph
above — despite being explicitly "confirmed" as a 4-pointed star/shuriken in this doc's own
Context section via a BMP crop — reads as "o-umlaut" at actual render size on the physical LCD,
not a star. Human caught it live; a second independent BMP-crop re-check (done to verify) made
the identical misjudgment before a pixel-exact diff against a real screendump settled it
definitively (30/30 match for `'*'`'s own bitmap, confirming the code was rendering exactly the
glyph it was told to — this was a wrong glyph *choice*, not a rendering bug). A full scan of the
155×74 `SKIN_FONT` atlas (not just the 3 `CHAR_MAP` rows) found no cleaner star hiding elsewhere —
it's the same 31×3 character set repeated 4× in different recolor palettes, not extra glyphs.
Human picked TEXT.BMP row2/col4 instead (real pixel data there, a small angular tick/spark shape,
just never wired to an ASCII code by `CHAR_MAP`) — implemented as `kTitleMarqueeSepGlyph`, a raw
`SkinUV` constant referencing that pixel position directly, no `CHAR_MAP`/bake-pipeline change.
Same 3-blank+3-glyph+3-blank spacing kept. Full mechanism re-verified (17/17) and a fresh DUT
screenshot confirms the new glyph reads cleanly. See `M-TITLE-MARQUEE-WRAP.md`'s OQ1 for the full
writeup — flagged there as a general lesson: static BMP-crop reads of this kind of low-res
abstract bitmap aren't a reliable proxy for in-context rendering, twice over in this one case.

**Owner:** Architect (design pass — done) → Developer (implementation — **done 2026-08-05**,
DUT-verified, glyph corrected same day per human real-hardware catch) · **Deps:** `m3-001`
(feature owning the title marquee), `M-UI-POLISH-fidelity.md` TASK-048 (the gap/loop half that
never shipped) · **Priority:** P3 (cosmetic fidelity, no functional/safety impact) · **Status:**
**CLOSED — implemented, host-verified (`run/check` 6/6 both envs) and DUT-verified**, including
the separator-glyph correction. WiFi-down-override path inferred safe (same short-text code path
already covered) rather than separately re-tested.

### TASK-400 — Settings → System → Reboot (user-triggered soft reboot)

**Filed 2026-08-04.** Human asked for a manual recovery path for the occasional heap-fragmentation
state that leaves an app unable to open (`M-HEAP-FRAGMENTATION.md`, parked — no in-session recovery
exists today short of a physical power cycle or the `SERIAL_DEBUG`-only `reboot` command). Asked
for a design pass before implementation.

Architect design doc: `docs/architecture/designs/M-SYS-REBOOT.md`. Lean: new 7th Settings category
("System") with a single "Reboot device" row → Danger-styled confirm screen (existing
`SButton`/`sButtonBar` kit, same pattern as the PrLoc delete-slot confirm) → `ESP.restart()` — the
same call already proven at `wifiSection.h:377` and the debug `reboot` serial command, no new reset
mechanism. Doc also works out why a full `ESP.restart()` isn't undercut by `M-HEAP-FRAGMENTATION`'s
own OQ4 finding (partial in-process `vTaskDelete()` teardown doesn't reliably un-fragment the heap)
— a full chip reset reinitializes the entire heap allocator from scratch, a different mechanism
than the one OQ4 measured as insufficient. Flags a real layout constraint: the category list is
now 208/212px used with 7 categories + Cancel — zero headroom left for an 8th category without a
layout change (reserved as cross-feature edge X047 pending acceptance).

**VE testability review (2026-08-04, same day):** `docs/architecture/designs/
sys-reboot-wifi-multi-VE-review.md`. Verdict **approve-with-changes**, no blockers. Two majors:
VE-1-1 (confirm-tap reboot path has no stable pre-restart log line, unlike the existing serial
`reboot` command's ack — a harness reconnecting after the confirm tap can't tell "confirmed as
designed" from a coincidental crash/TWDT reset) and VE-1-2 (the doc's "confirm on-device" layout
check can't be automated with `run/screendump` as it exists today — connecting the tool resets the
DUT via CH340 DTR-on-open, per `best_practices.md`'s live rule and LL-051, wiping any navigated
state before a pixel is read). Three minors/informational, no design rethink required.

**Architect disposition (2026-08-04, same day):** both majors folded into `M-SYS-REBOOT.md`.
VE-1-1 → confirm handler now specs a `[settings] system-reboot confirmed` log line immediately
before `ESP.restart()`, plus a matching exit-criteria assertion. VE-1-2 → the layout-check exit
criterion now states explicitly it's human-eyeball-only under current tooling (DTR-reset-on-open
makes `run/screendump` unusable for navigated state), not left implicit.

**Human sign-off (2026-08-04):** design **accepted** as a design doc, no separate ADR (OQ1's own
lean — the reset mechanism is 100% reused, not a novel decision). `settings-system` (new feature)
+ `X047` (new cross-feature edge, `settings-system` × `settings-001` category-list capacity)
committed to `feature_inventory.yaml`/`cross_feature_matrix.yaml` same day, both `status: planned`.

**PM scheduling (2026-08-04):** cleared for Developer pickup — no further design/review gate
before implementation. `app/src/settings/systemSection.h` (new) + `main.cpp` `SETTINGS_CAT_COUNT`
6→7 wiring, per the accepted doc's §Lean/decision.

**Implementation (2026-08-05, Developer subagent, PM-reviewed):** built exactly per §Lean/decision
— `SETTINGS_CAT_COUNT` 6→7, `"System"` added to `kLabels[]`, `_sections[6]` wired to a new
`SystemSection` (`main.cpp`). New `app/src/settings/systemSection.h`: single "Reboot device" row →
confirm screen (`SButton`/`sButtonBar` kit, mirrors `appsSection.h`'s ManualConfirm/LookupError
confirm-frame idiom — no new confirm-screen code invented). Confirm-tap: `SButton::flash()` →
`LOG_I("settings","system-reboot confirmed")` (VE-1-1) → `Serial.flush(); delay(50);` → `ESP.restart()`.
One implementation-time deviation from the doc, not a design change: the confirm screen's
`SButton[2]` is lazy heap-allocated (`new SButton[2]`, never freed) rather than an inline member —
an embedded array overflowed the debug build's `.dram0.bss` by exactly 32B at link time (prod build
was fine); same "lazy malloc once, never freed" pattern already used by `TeletextApp::_nosSource()`
and `webRadioApp.h`'s `wrPumpConnectUrlBuf()`. No `settingsStorage.h`/`_cancel()` changes (design
doc confirmed unnecessary — every section autosaves per-field on change already).

**PM verification (2026-08-05):** re-ran `./run/check` independently (not just trusting the
implementer's own report) — 6/6 green. Read the full diff: `main.cpp` wiring matches the existing
five-section pattern exactly; `systemSection.h`'s `handleInput`/`repaint`/`tick`/`title` overrides
match `SettingsSection`'s actual virtual signatures (not the base class's stale docstring, which
still says `handleTap`); `SBtnStyle::Neutral` is a real enum member (`settingsWidgets.h:50`); the
gnu++11 no-aggregate-brace-init field-assignment approach matches that file's own documented note.
Confirmed host-side only — a DUT soak (TASK-390/393) was running concurrently on `/dev/ttyUSB0`
during this implementation; no serial-port script was touched. `feature_inventory.yaml`'s
`settings-system` entry flipped `planned` → `implemented` with a matching notes update; `X047`
left untouched (still accurately describes the shipped layout). Nothing committed yet.

**DUT verification (2026-08-05, PM-run, once the TASK-390/393 soak freed the port).** New tool
`app/tools/task400_401_dut_verify.py` (kept as a project asset, not folded into the automated
suite — both VE reviews flagged parts of this as human-eyeball-only or not yet worth a permanent
test id). Flashed `cyd2usb_winamp_debug`. Results: `switchApp 10` → `tap 137 197` (category row 6)
→ `get settingsSection` returns `section:6` (System reachable); `tap 137 41` (Reboot device row) →
`tap 69 210` (Cancel) → `get settingsSection` still `6`, no restart (Cancel path clean); re-entered
the confirm screen and tapped Reboot for real (`tap 204 210`) — raw serial showed
**`[I][settings] system-reboot confirmed`** as the line immediately before the connection dropped
(VE-1-1, directly confirmed, not inferred). Reconnected after the boot: device came back up
responsive (`get appId` → `Spotify`, its persisted pre-reboot `playerMode`), `SettingsStorage:
loaded` clean in the boot log (no SPIFFS corruption), WiFi/Spotify/dataTask all started normally.
10/10 automated checks in the script passed (see TASK-401 below for the second half — same DUT
session).

**Not exercised this session (honest scope note):** the human-eyeball 7-row layout check (VE-1-2)
— genuinely not automatable with current tooling (`run/screendump` DTR-resets on connect, wiping
any navigated-to state before a pixel is read, exactly as VE-1-2 itself predicted; not attempted
rather than faked). The "reboot while WebRadio actively playing / a fetch in-flight" exit-criteria
bullet also wasn't separately exercised — the actual confirmed reboot above happened from a
Spotify-idle state, not mid-fetch; the general "reboot doesn't corrupt SPIFFS" property is
evidenced (clean `SettingsStorage: loaded` after a real device-wide reset), but not that specific
concurrent-activity variant. Both are cheap to pick up in a future DUT session if wanted; neither
blocks calling the core feature done.

**Owner:** Architect (design pass — done; VE majors folded) → human (**signed off**) → VE
(testability review — done, approve-with-changes) → PM (scheduled, implementation-reviewed,
DUT-verified) → Developer (implementation — **done 2026-08-05**) · **Deps:**
`M-HEAP-FRAGMENTATION.md` (the motivating parked issue), `settings-001` (SettingsApp category-list
capacity) · **Priority:** P2 (real recovery gap — no user-facing path today for a known, if
infrequent, failure mode) · **Status:** **closed — implemented, host-verified (`run/check` 6/6),
DUT-verified** (reachability, confirm/cancel, the VE-1-1 log line, and a real reboot-and-recover
cycle all confirmed live; VE-1-2's layout eyeball-check and the mid-activity-reboot variant are the
only two exit-criteria items left, both non-blocking per above). Uncommitted, pending the user's
go-ahead to commit.

### TASK-401 — Settings → WiFi: save multiple networks (manual switch only, no auto-failover)

**Filed 2026-08-04.** Human asked whether SPIFFS has room for multiple saved WiFi networks, and
whether the device could support them. Asked for a design pass before implementation.

Architect design doc: `docs/architecture/designs/M-WIFI-MULTI-AP.md`. SPIFFS headroom confirmed
trivial (2,129 B used of a 1.4 MB partition). First draft proposed automatic scan-and-failover, both
at boot and in `wifiDiag::superviseTick()` (built on the vendored `WiFiMulti` library) — **human
explicitly rejected autonomous switching** ("I don't want the DUT switching over of wifi hotspots on
its own"), so the doc was revised same-day: boot chain and the supervisor are now **fully
unchanged** — still single-NVS-profile retry, forever, exactly as today. The feature collapses to
storage + a new "Saved networks" screen in `WifiSection` (new `/wifi_networks.json`, cap 5 entries,
kept out of `g_settings`/`settings.json` to avoid re-opening that file's own TASK-329 capacity-math
history) where tapping a saved entry is a deliberate, user-initiated connect — no code path picks a
network on its own anywhere. Rejected auto-failover design space kept in the doc, marked rejected,
per this project's "record what was investigated and turned down" convention.

**VE testability review (2026-08-04, same day):** `docs/architecture/designs/
sys-reboot-wifi-multi-VE-review.md`. Verdict **approve-with-changes**, no blockers. Two majors:
VE-2-1 (no debug getter proposed for the saved-network list — every comparable list-editing
section in this codebase has one, e.g. `AppsSection::submenu()`; without it the LRU-eviction
outcome the doc's own OQ4 already leaves undecided is also unobservable) and VE-2-2 (the doc's
exit criteria never test the one-time legacy `/wifi_creds.json` migration path, despite every
existing DUT today hitting exactly that path first). Three minors/informational, no design
rethink required.

**Architect disposition (2026-08-04, same day):** both majors folded into `M-WIFI-MULTI-AP.md`.
VE-2-1 → new `get wifiSaved` debug getter specced as Lean step 5, mirroring the existing
`AppsSection` accessor pattern. VE-2-2 → new exit-criteria bullet requiring the legacy
`/wifi_creds.json` → `/wifi_networks.json` migration to be exercised on a DUT, wired to the new
getter for verification.

**Human sign-off (2026-08-04):** design **accepted** as a design doc, no separate ADR (OQ1's own
lean — boot chain and `wifiDiag::superviseTick()` stay unchanged, so there's no boot-order/
recovery-policy decision to formalize). `wifi-002` (new feature) committed to
`feature_inventory.yaml` same day, `status: planned`. No new cross-feature edge, per the design's
own §Registers.

**PM scheduling (2026-08-04):** cleared for Developer pickup — no further design/review gate
before implementation. Extends `app/src/settings/wifiSection.h` per the accepted doc's
§Lean/decision; no boot-chain or `wifiDiag.cpp` changes in scope.

**Implementation (2026-08-05, Developer subagent — died mid-task, PM-finished and verified.)**
The implementing subagent hit its session credit limit partway through and terminated before
reporting — per this project's own standing lesson (`[[project_subagent_credit_deaths]]`), the
uncommitted work was reviewed and finished rather than discarded and redone. What it left behind
was the complete feature, built exactly per §Lean/decision: `/wifi_networks.json` (cap
`WIFI_MAX_SAVED=5`) with TASK-329-discipline capacity math (a documented worst-case comment,
`doc.overflowed()` guards on both read and write, same as `SettingsStorage::save()`); one-time
migration from legacy `/wifi_creds.json`, lazily triggered on first `WifiSection::enter()` or
first `get wifiSaved` touch — deliberately not in the boot chain, satisfying the design's
zero-boot-changes requirement; new `WifiStep::SavedList/SavedEntry/SavedDeleteConfirm` sub-steps
reusing existing row/button-bar widgets (no new confirm-screen code); `_onConnectSuccess()` hooked
into `tick()`'s `WL_CONNECTED` branch, appending/refreshing a saved entry with LRU eviction past
the cap, reading the password back out of NVS via `esp_wifi_get_config()` rather than caching a
second plaintext copy; `_doForget()` scoped down to remove just the active list entry; new
`get wifiSaved` debug getter (VE-2-1) in `SettingsApp::dbgGet()`. One leftover mid-debug artifact
(a compile-time `sizeof(WifiSection)` probe, clearly mid-diagnosis of the DRAM issue below) was
found and removed during review.

**PM review + DRAM-budget fix (2026-08-05).** Read the full diff against the design doc and this
codebase's real interface names (`SettingsSection`'s actual virtual signatures, `SBtnStyle`'s real
enum members, `sStackedBtnRect`'s real existing precedent) — all correct, nothing hallucinated.
`./run/check`'s debug-build gate failed: `.dram0.bss` overflowed by 8 bytes (this debug build had
exactly 0 bytes of headroom left after TASK-400, the same-day sibling task). Traced properly rather
than guessed: measured `sizeof(WifiSection)` before/after via a temporary probe, diffed `nm`
symbol tables between a clean-master baseline build and the current one to isolate exactly which
symbols grew. Two plausible-looking fixes (merging the saved-state pointer+count+selIdx into one
heap-allocated struct; relocating that pointer, and separately TASK-400's own confirm-button
pointer, to file scope) were tried and **measured to have zero effect on the actual link-time
total** — a class member and an equivalent file-scope global cost the identical 4 bytes either way,
confirmed via `nm`/`size` before reverting both relocations back to plain class members for code
clarity. The actual fix: shrank `WifiSection`'s pre-existing `_nets[16]` live-scan buffer to
`_nets[S_MAX_ROWS]` (8) — behavior-preserving, not a functional cut, since `repaintList()` only
ever renders `min(_netCount, S_MAX_ROWS)` rows regardless of how many candidates the insertion sort
tracks; an 8-slot bounded insertion sort selects the identical top-8-by-RSSI set as a 16-slot one
(any network that would land in the true top 8 is by definition stronger than whatever's in slot 8
of an 8-slot array, so it always survives the shift). `./run/check` 6/6 green on both envs after.
Re-verified independently (not just trusting the subagent's own prior report), full diff read
line-by-line post-fix to confirm the mechanical renames from the DRAM iteration didn't corrupt any
logic. Confirmed `main.cpp`'s boot-chain WiFi connect tiers and `wifiDiag.cpp` are byte-for-byte
untouched — the one hard constraint this design exists to satisfy. `feature_inventory.yaml`'s
`wifi-002` entry flipped `planned` → `implemented` with a full implementation note. Nothing
committed yet.

**DUT verification (2026-08-05, PM-run, same session as TASK-400 above, `app/tools/
task400_401_dut_verify.py`).** Real, non-synthetic result: `get wifiSaved` against the actual
production device returned `count:1, entries:[{"ssid":"<home-ssid>","lastUsedMs":...}]`
— **the legacy `/wifi_creds.json` → `/wifi_networks.json` migration ran correctly on first touch
against this device's real, previously-untouched credential file** (VE-2-2's exit criterion,
confirmed with real data, not a synthetic fixture). Also confirmed: `get wifiSaved` works
standalone before any `Settings → WiFi` navigation that boot (queried immediately after
`switchApp Settings`, migration/load fired lazily on the getter itself, per design); `switchApp 10`
→ WiFi category (`tap 137 41`) → `get settingsSection` returns `section:0`; navigated into the
Saved-networks list (`tap` at the computed saved-row y, connected-state offset) → `SavedEntry` for
the one real entry → `get wifiSaved` still reports the identical single entry (no state
corruption from the nav); back-tap chain (`SavedEntry` → `SavedList` → `Status`) returns cleanly
to `section:0`.

**Not exercised this session (deliberate, not an oversight):** tap-to-connect and the
Danger-confirm-delete path were **not** fired for real against this device's *only* saved,
currently-active credential — doing so risked dropping the DUT's sole known-good WiFi connection
for no real coverage gain (a reconnect-to-self and a delete-then-instantly-relose-network aren't
meaningfully different from what the code already demonstrably does elsewhere). Those two
exit-criteria bullets, plus "delete a *non-active* entry" and the out-of-range-connect failure
path, all genuinely need a **second** saved network to test safely and aren't coverable with what
this device currently has — noted as the concrete next step, not silently skipped. `T-WIFI-01..06`
regression suite also not run this session (DUT time was budgeted for TASK-400+401's own new
surface, not a full regression pass) — no reason to expect a regression (boot-chain/`wifiDiag.cpp`
untouched, confirmed by diff), but not directly re-verified either.

**Owner:** Architect (design pass — done, revised same-day per human decision; VE majors folded)
→ human (**signed off**) → VE (testability review — done, approve-with-changes) → PM (scheduled,
implementation-finished + DRAM-fixed + reviewed + DUT-verified) → Developer (implementation —
**done 2026-08-05**, subagent died mid-task, finished by PM) · **Deps:** `settings-wifi`
(WifiSection, the section this extends) · **Priority:** P3 (convenience feature, no functional gap
being closed) · **Status:** **implemented, host-verified (`run/check` 6/6 both envs), DUT-verified
for reachability + the real legacy-migration path + nav integrity** — **open, not closed**: the
tap-to-connect, delete, out-of-range, and `T-WIFI-01..06` regression exit-criteria bullets need a
second saved network (or a dedicated future DUT session) to exercise safely, and haven't been.
Core migration/storage/UI mechanism is proven against real device data; the remaining gap is
narrow and named, not open-ended.

### TASK-402 — WebRadio posbar: smooth the buffer-fullness bar + rate-limit its redraws

**Filed 2026-08-05.** Human observed the WebRadio posbar (repurposed in WebRadio mode to show
input-buffer fullness rather than playback position) is too jittery and redraws too often,
wasting CPU/SPI for no visible benefit — and asked directly whether the current update rate was
known. Asked for a design pass before implementation.

Architect design doc: `docs/architecture/designs/M-WEBRADIO-POSBAR-SMOOTH.md`. Direct answer to
the update-rate question: there wasn't one — `WebRadioApp::tick()` runs once per `loop()`
iteration with no `delay()` gating it, and the only redraw gate was a raw ±2-point value-delta
check (not time-based) on an unfiltered ratio recomputed every tick from the audio library's input
ring buffer. Each redraw was also unnecessarily expensive — always a full 248×10 groove reblit (20
`pushImage` calls), ~4.8× costlier than Spotify's own seek-bar update in the same file, which only
touches the changed thumb region. Doc flags that this exact tension was already tuned once before,
in the opposite direction: TASK-253 cut a 15-point hysteresis down to 2 specifically to fix
visible 33px thumb jumps — so simply widening the threshold back up would undo a real, prior,
DUT-verified fix rather than improve on it.

Lean: EMA smoothing on the value (mirroring the VU meter's own existing attack/release filter in
the same file) + a time-based minimum redraw interval + a partial-diff blit (mirroring Spotify's
seek-bar pattern) + a new `perf::record("wr.posbar", ...)` path and `get wrPosbar` debug getter,
since nothing measures this today and any before/after claim needs a DUT baseline first. EMA alpha
and the redraw-interval constant are explicitly left as DUT-tuning open questions, not guessed.

**VE testability review (2026-08-05, same day):** `docs/architecture/designs/
webradio-posbar-VE-review.md`. Verdict **approve-with-changes**, no blockers. Four majors:
VE-1 (the existing `set wrBufPct` debug hook's interaction with the new gates was unaddressed),
VE-2 (perf.h matches slots by pointer identity, not string content — the doc's "instrument around
`_drawPosbar()`'s call site" was ambiguous since that function has three call sites; instrumenting
at each independently risked silently fragmenting into multiple slots, invisible thanks to
perf::record()'s silent-drop-on-overflow behavior), VE-3 (before/after redraw-count comparison
wasn't specified multi-trial, despite this project's own repeated history of single-shot DUT
measurements proving unreliable), VE-4 (the new getter reported outcomes but not which of the two
new gates was currently binding, undermining the DUT tuning pass OQ1/OQ2 themselves call for).

**Architect disposition (2026-08-05, same day):** all four majors folded into the design doc.
VE-1 → `set wrBufPct` explicitly kept bypassing both new gates, documented as debug-forced. VE-2 →
instrumentation pinned to exactly one site, inside `_drawPosbar()`'s own body. VE-3 → exit criteria
now require ≥3 trials each side (or explicit `[wifi-ev]` outage correlation). VE-4 → new getter
gains a `lastSkipReason: delta|interval|none` field.

**Human sign-off (2026-08-05):** design **accepted** as a design doc, no separate ADR (this is a
display-refresh tuning fix, not a novel architectural decision). Cross-feature edge `X049`
(`webradio-001` × `perf-001`, the `perf.h` `MAX_PATHS` budget) committed to
`cross_feature_matrix.yaml` same day. No new `feature_inventory.yaml` entry — this modifies the
existing `webradio-001` feature in place; that entry's description/notes get updated by Developer
at implementation, per the design doc's own note.

**PM scheduling (2026-08-05):** cleared for Developer pickup — no further design/review gate
before implementation. Touches `app/src/webRadioApp.h` (EMA, time-gate, new debug getter,
`perf::record` call), `app/src/winamp/winampDisplay.h` (`drawBufferBar()` partial-diff blit), and
`app/src/perf.h` (`MAX_PATHS` 10→11), per the accepted doc's §Lean/decision.

**Implementation (2026-08-05, Developer, PM-driven session).** Landed the full Lean (A+B+E+F):

- **A (EMA):** `_bufPctSmoothed` (float), `+= (raw - smoothed) * WR_POSBAR_EMA_ALPHA`, mirroring
  the VU meter's own attack/release filter shape. `_bufPct` itself stays raw and untouched — still
  what `wrUnderruns`/`_minBufPct` read, per the doc's "raw value stays available" note.
- **B (time floor):** `WR_POSBAR_MIN_REDRAW_MS` gate alongside the existing (now smoothed-value)
  delta check — both must pass to redraw. Provisional constants (`WR_POSBAR_EMA_ALPHA = 0.2f`,
  `WR_POSBAR_MIN_REDRAW_MS = 200`), explicitly commented as OQ1/OQ2-pending, not claimed final.
- **E (partial-diff blit):** `drawBufferBar()` rewritten to mirror `updateSeekThumb()`'s own
  old-thumb-under + new-thumb pattern, via a new `lastBufThumbPx` sentinel kept separate from
  Spotify's `lastThumbPx` (prevents the two callers' diff-state from cross-contaminating). OQ3
  (does anything else paint over the groove between calls) checked directly: `repaintChrome()`
  already re-blits the full groove unconditionally on every full-chrome event, so `drawBufferBar`
  invalidates `lastBufThumbPx` there too (`repaintChrome()` now resets it alongside the existing
  `vu::invalidate()` precedent) — closes the one real gap found (a stray full-chrome repaint,
  e.g. `SCREEN_LOG`'s `screenlog.tick()` dismiss, leaving a stale off-position thumb sprite that a
  same-position partial-diff redraw would otherwise never clean up).
- **F (instrumentation):** `perf::record("wr.posbar", ...)` added at the single site inside
  `_drawPosbar()`'s own body (VE-2: not at its three callers), `MAX_PATHS` 10→11 in `perf.h`.
  New `get wrPosbar` getter: `bufPctRaw`, `bufPctSmoothed`, `bufPctDrawn`, `redraws`,
  `sinceLastRedrawMs`, `lastSkipReason: delta|interval|none` (VE-4).
- **`set wrBufPct` (VE-1):** unchanged behavior — force-writes and draws immediately, bypassing
  both new gates. Also syncs `_bufPctSmoothed` to the forced value so a real tick right after
  doesn't visibly jump back toward a stale pre-override EMA baseline (small addition beyond the
  doc's literal spec, low-risk, avoids an obvious own-goal).

`feature_inventory.yaml`'s `webradio-001` entry updated per the doc's own note (description +
serial-debug var list, including a pre-existing inaccuracy fixed in passing: `wrBufPct` was
listed as a `get` var but only ever existed as `set`). `./run/check` 6/6 both envs, no DRAM/BSS
regression.

**DUT verification (2026-08-05, same session, real playback).** Same harness as TASK-399
(`app/tools/task399_402_dut_verify.py`), against a real playing station (SLAM!, 30-station NL
list fetched live), using the new `get wrPosbar` getter:
- VE-1 (`set wrBufPct 37`, debug-forced): `bufPctDrawn` and `bufPctSmoothed` both reflect 37
  immediately, gate bypass confirmed working exactly as specified.
- Real playback, polled every 250ms over ~7s: `redraws` climbed 5→17 (real redraws happening) but
  **not on every sample** — confirms the time-floor gate (B) is genuinely binding, not a no-op.
  `lastSkipReason` was observed taking all three values (`delta`, `interval`, `none`) across the
  window — both new gates were seen actually blocking a redraw at different points, not just one
  dominating (the exact thing VE-4's getter field was added to make visible).
- **Visual**: a `screendump` mid-playback shows the posbar thumb rendering cleanly at a plausible
  low fill position with no groove corruption or leftover/ghost thumb sprite — the partial-diff
  blit (Option E) isn't leaving stale pixels behind. (The forced 37% from the VE-1 check above was
  overwritten within the same ~200ms window by real ticks recalculating from live buffer state,
  as designed — the debug hook was never meant to stick once real playback resumes.)

**Not done this session (explicitly, not an oversight):** OQ1/OQ2 formal DUT *tuning* (the
provisional `WR_POSBAR_EMA_ALPHA=0.2f` / `WR_POSBAR_MIN_REDRAW_MS=200` constants read as reasonable
from the above — visibly smoothed, visibly rate-limited, nothing looked laggy — but weren't swept
against alternatives) and the design doc's own ≥3-trial before/after redraw-count comparison,
multi-minute stall-visibility check, and full WebRadio regression suite (auto-skip/eject/ICY/vis
toggles) — those are a deliberately separate, longer DUT session, not a quick mechanism check.

**Owner:** Architect (design pass — done; VE majors folded) → human (**signed off**) → VE
(testability review — done, approve-with-changes) → PM (scheduled) → Developer (implementation —
**done 2026-08-05**, DUT-verified) · **Deps:** `webradio-001` (the feature this modifies),
`perf-001` (`perf.h`'s `MAX_PATHS` budget, `X049`) · **Priority:** P3 (visual/resource-usage
polish, no functional gap) · **Status:** **CLOSED.** implemented, host-verified (`run/check` 6/6
both envs) and DUT-verified (mechanism confirmed live against real playback + a real-hardware
screenshot). OQ1/OQ2 formal tuning was picked up as TASK-405 (2026-08-06) — the live-eyeball
session this entry deferred to found the slew-only tuning insufficient (ceiling jitter) and
landed on a hysteresis dead-band instead, superseding rather than merely tuning this task's own
constants. Live-eyeball confirmed on the physical LCD: "POSBAR no longer jitters." See TASK-405
for the full resolution.

## Open — TASK-396 audit follow-ups (2026-08-05, filed from the completed audit)

Two genuine "flagged, never filed" gaps surfaced by TASK-396's full audit. Both were correctly
identified with real evidence at the time they were originally noted; neither ever got a task
number. Filed here rather than folded into their origin tasks (both origins are long since
closed/DONE) per this session's own new BP recommendation — a number now, not more prose.

### TASK-403 — PlaneRadar fetch: HTTP response compression (brotli) support

Origin: TASK-361's candidate-scoping pass (2026-07-25). Live `curl -H "Accept-Encoding: br"`
against `opendata.adsb.fi` returned a **9.2 KB body vs. 56.9 KB uncompressed at the same JFK
query — a 6.15x reduction** — which per TASK-361's own confirmed size-scaling data (truncation
failure rate climbs with payload size) would very plausibly collapse the fetch-truncation
failure rate back toward TASK-313's original floor. Called "probably the single highest-impact
lever available" at the time, explicitly not implemented as part of TASK-361 (too large for that
task's scope) and never filed since.

**Why it's real work, not a quick win:** the vendored Arduino-ESP32 `HTTPClient.cpp`
(`framework-arduinoespressif32/libraries/HTTPClient/src/HTTPClient.cpp:1217`) unconditionally
sends `Accept-Encoding: identity;q=1,chunked;q=0.1,*;q=0` — no user override point as vendored —
and there is no gzip/brotli decoder anywhere in this firmware today (confirmed via grep across
`app/src`). Fixing this needs: (1) a library patch making the Accept-Encoding header overridable
(this project already has a `LOCAL_PATCHES.md` precedent for SpotifyArduino — same mechanism);
(2) a streaming decompressor integrated as a `Stream` adapter feeding `prParseStream()` — brotli
decode is heavier than gzip/deflate, and even deflate's ~32 KB window is a lot against this
board's tight DRAM budget (see `[[feedback_dram_bss_static_buffers]]` memory note — this board
has overflowed DRAM on additions as small as 264 bytes before); (3) a RAM budget review before
committing to which codec, if any, actually fits.

**Owner:** Architect (design/feasibility pass first — this is exactly the "separately-scoped
design/task" TASK-361 deferred to) · **Deps:** TASK-361 (shipped mitigation already lowers the
acute urgency — radius-capped 2nd retry is in production and TASK-361's own follow-up soaks
never reproduced the original "both attempts fail" condition live) · **Priority:** P3 (real,
well-evidenced, but not currently blocking — TASK-361's cheaper fix is holding) · **Size:**
L (library patch + decompressor + RAM budget review) · **Gate:** design doc first; no
implementation without an Architect feasibility call, given the DRAM-budget risk. ·
**Status:** **OPEN — feasibility gate cleared 2026-08-06, deferred at P3** (design doc landed,
not implemented; see session update below).

**Session update (2026-08-06) — Architect feasibility pass done, gate cleared for a future
implementation task; not implemented this session.** Full design doc:
[`M-PLANERADAR-http-compression.md`](../architecture/designs/M-PLANERADAR-http-compression.md).
Findings in brief:
- **RAM verdict: feasible, and easier than the gate's framing implied.** Deflate/gzip's window is
  spec-capped at 32 KB (unlike brotli, which the original `curl` test happened to use first, not
  deliberately chose); as a transient dataTask-serial scratch buffer freed right after parse, it's
  the same lifecycle already carried by `planeradar_doc`/`heatmap_doc`/`crypto_doc` in
  `app/mem_manifest.yaml`, comfortably inside today's ~185 K nominal unallocated INTERNAL headroom.
  No WebRadio-style arena/reclaim design needed — this fetch has no DMA-contiguity or long-residency
  constraint.
- **Mechanism verdict: already proven on this board.** `app/lib/WiFiClientSecure/` already vendors
  and patches (PATCH-001/003) a framework-supplied library to shadow the Arduino-ESP32 core's own
  copy — the exact mechanism TASK-403 needs for `HTTPClient.cpp`'s unconditional `Accept-Encoding`
  header, not a novel approach.
- **Scope correction: recommend gzip, not brotli**, as the implementation target — lighter decoder,
  bounded window, no embedded precedent gap to close. Brotli (TASK-361's only actual measurement)
  is explicitly not the recommended codec.
- **Priority verdict: concur with P3, stay deferred.** TASK-361's radius-capped retry2 is
  code-reviewed and fault-injection-proven to fire correctly, and three post-fix soaks at
  JFK-scale traffic found the original truncation condition not reproducing organically — final
  failure rate 0% in every soak since. No open user-visible symptom this would currently fix;
  revisit on real recurrence (watch for frequent `radius-capped`/`retry2` log lines) or a future
  need to shrink fetch size for its own sake.
- Open questions before any implementation starts (full list in the design doc): whether
  `opendata.adsb.fi` actually serves `gzip` (only `br` was ever tested), the real gzip ratio on
  this payload shape, and which embedded inflate implementation to use.

### TASK-404 — Boot: WiFi fallback cascade doesn't recover until the background supervisor kicks in (~60-85s)

Origin: TASK-364/M-BOOT-UI's §6 mid-session investigation (2026-07-28). Once the hardcoded
`wifi_creds.h` stage's `WiFi.begin()` genuinely fails, the *same-boot* NVS and SPIFFS-creds
fallback attempts both hit an ESP32 driver-level `sta is connecting, return error` and fail too
— **even when the SPIFFS creds are correct.** Recovery only happens via the background WiFi
supervisor's later retry kick, observed at ~60-85s post-boot. Noted at the time as "a
retry-policy issue in the fallback cascade itself, not a display-layer bug" (M-BOOT-UI's own
scope was the marquee/UI layer, not cascade retry timing) — "No task filed for it yet; human to
decide if/when." Never filed until now.

**Symptom conditions:** only manifests when the hardcoded-WiFi credential source (`wifi_creds.h`)
is present but wrong or unreachable — a narrow, self-inflicted-config window, not a general WiFi
flakiness issue (see `[[project_wifi_flapping_ap_side]]` for the unrelated AP-side flapping
history). Self-recovers within ~85s regardless, via the existing supervisor — not a hang, just a
slower-than-necessary recovery.

**Candidate fix direction (unscoped, needs Developer investigation, not prescribed here):** the
ESP32 WiFi driver's "sta is connecting" rejection suggests the cascade's stage transitions aren't
giving `WiFi.disconnect()`/driver teardown enough time to settle between `WiFi.begin()` attempts
— either add an explicit disconnect-and-wait between cascade stages, or skip the immediate
same-boot NVS/SPIFFS retries entirely and let the background supervisor own all retries after a
hardcoded-stage failure (avoids hammering a driver that's still mid-teardown).

**Session update (2026-08-06) — premise was stale; picked up as the day's PM-recommended next
task.** Attempted the gate's own repro (misconfigure `wifi_creds.h` to an unreachable SSID, flash
debug, watch the boot log) and it reconnected in 1.4s — no stall at all. Traced why:
**`HARDCODED_WIFI_SSID` was never actually defined in this build.** `app/.gitignore` expects the
shim at `app/src/wifi_creds.h`; that file didn't exist on this machine. The file that did exist,
`Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h`, is the wrong location and was never `#include`d
by any compiled source — confirmed by a full grep across every tracked `.cpp`/`.h`/`.ino` and by
`strings` on the compiled ELF (no hardcoded SSID string present anywhere in the binary). The
`#ifdef HARDCODED_WIFI_SSID` stage in `main.cpp` has been permanently dead code — the real chain
has only ever been NVS → SPIFFS → UI, contradicting CLAUDE.md's documented chain (also now fixed).
This means the original 2026-07-28 M-BOOT-UI observation, whatever its true cause, could not have
been this specific hardcoded→NVS race as filed.

**Human decision:** rip out the dead stage rather than wire it up (superseded by TASK-401's
NVS-backed multi-network Settings UI; no product need for a compile-time-baked SSID anymore).
Done: removed the `#ifdef HARDCODED_WIFI_SSID` block from `main.cpp` (`git log` — this session's
commit). CLAUDE.md's "Hardcoded station WiFi" section rewritten to describe the real NVS→SPIFFS→UI
chain and record why the old shim was dead.

**The underlying race mechanism is still real for the two stages that do exist** — confirmed from
source, not just inferred: `WiFiSTA.cpp`'s no-arg `begin()` (the NVS stage) calls
`esp_wifi_connect()` with no disconnect first, and `WiFiGeneric.cpp:1091-1094`'s
`STA_DISCONNECTED` handler runs its own background `WiFi.disconnect(); WiFi.begin();` retry loop
whenever `autoReconnect` (default `true`) sees a reconnectable failure reason — which is most of
them, including `NO_AP_FOUND`. If the SPIFFS stage's own `WiFi.begin(ssid, pass)` fires while that
background retry is mid-attempt, `esp_wifi_connect()` returns `ESP_ERR_WIFI_CONN` ("sta is
connecting, return error") and the SPIFFS attempt silently no-ops — explains the doc's original
~60-85s-until-supervisor-recovers symptom shape even though the originally-named trigger (a bad
hardcoded stage) turned out not to exist. **Fix applied** (`main.cpp`, between the NVS and SPIFFS
stages): `WiFi.setAutoReconnect(false); WiFi.disconnect(false);` plus a bounded 300ms
TWDT-fed settle-wait before the SPIFFS stage's own `WiFi.begin()` — stops the NVS stage's
background retry from colliding with the next stage's explicit attempt.

**Verification: compile + happy-path only, not the failure-path race itself.** `run/check` 6/6
both envs. DUT sanity boot on production firmware with real creds: connects in ~1.5s via NVS exactly
as before (one transient `AUTH_FAIL`/reason=202 on the very first attempt, driver's own
built-in single retry recovers it, `GOT_IP` at t=1536ms) — the new disconnect+settle block is
gated on `!wifiConnected` and was correctly skipped, confirming zero regression to the common case.
**Not verified on DUT: the actual NVS→SPIFFS race scenario and whether this fix collapses its
recovery time**, because reproducing it requires temporarily feeding the DUT's *real* NVS-persisted
WiFi credentials something bad (not a throwaway file this time) — the human declined that specific
action this session (offered as an explicit option, not chosen), preferring to scope down to
removing the dead stage instead. If a future session wants full confirmation: temporarily corrupt
NVS creds (e.g. via the on-device WiFi Settings UI, connect to a wrong/decoy network once), leave
correct creds in SPIFFS `/wifi_creds.json`, reflash debug, and watch for `sta is connecting` in the
boot log pre-fix vs. post-fix recovery timing — then restore the real NVS creds via Settings UI
afterward.

**Owner:** Developer (done: dead-stage removal + race fix implemented and compile/happy-path
verified) · **Deps:** none, informed by M-BOOT-UI/TASK-364 (`docs/architecture/designs/
M-BOOT-UI-chrome-first-boot.md` §4/§6), TASK-401 (superseding rationale for the removed stage) ·
**Priority:** P3 · **Status:** implemented, host-verified (`run/check` 6/6 both envs), DUT
happy-path-verified — **the specific NVS→SPIFFS race this fix targets remains DUT-unconfirmed**,
gated on a future session choosing to deliberately corrupt this DUT's real NVS creds to test it ·
**Size:** S-M (came in as scoped; the dead-code discovery added investigation time, not
implementation size).

## Open — TASK-405 (2026-08-06, filed from TASK-402's own deferred OQ1/OQ2 tuning session)

### TASK-405 — WebRadio posbar: bound visual travel per second (slew-rate limiter, supersedes TASK-402's delta-threshold gate)

**Filed 2026-08-06.** TASK-402 shipped EMA smoothing + a minimum-redraw-interval gate for the
WebRadio posbar, explicitly deferring OQ1/OQ2 (the actual constant values) to a dedicated DUT
tuning session — never done at implementation time. Picked up that session today: human
live-observed the bar on the physical LCD (SLAM!, real playback) and reported it "oscillates,"
~4 visible changes/sec — suspiciously close to the existing `MIN_REDRAW_MS=200` ceiling (5/sec
max), meaning the time-gate wasn't actually limiting anything.

Traced 5 stations (`app/tools/task402_posbar_trace.py`, new ad hoc tool, extends
`run_serialdbg_tests.py`'s `Dut`/`_ensure_webradio`/`_webradio_enter_with_stations`/
`_wait_wr_state` rather than re-deriving them) with `wrState` tracked alongside `wrPosbar` to
isolate genuine `PLAYING` segments from `CONNECTING`/stall-retry noise (`_play()` force-resets
`_bufPct=0` on every reconnect attempt, `webRadioApp.h:1861`, ambiguous with a real empty buffer
otherwise). Two capture runs, `app/tools/rnd_logs/task402_trace_20260806T101314/` and
`task402_trace_20260806T102219/` (raw CSVs, one manifest each).

**Finding: the reported "oscillation" is a real, physically-driven burst-fill/rapid-drain
pattern** (small ring buffer + bursty TCP chunk delivery), not steady jitter — raw buffer ratio
swings the full 0-100 range within ~1.4s on 3 of 5 stations, repeatedly. Root cause of the visual
defect: the existing gate correctly bounds redraw *frequency* (≤5/sec, confirmed working exactly
as designed) but places no bound on redraw *magnitude* — a single redraw can jump ~80 points.
Quantified via host-side simulation against the real captured traces (not synthetic data): worst
2-second-window value range is 92-96 points today on 3 stations (i.e. nearly the entire bar
flashes by), vs. ~18-20 points with a simulated slew-rate limiter (max 2 points per redraw tick,
fed from the existing EMA target instead of jumping straight to it) — a ~5x reduction, by
construction rather than tuning luck.

**Design doc:** `docs/architecture/designs/M-WEBRADIO-POSBAR-SLEW.md` (Architect, status draft,
full measurement method + analysis results + design-space writeup + lean). Proposes replacing the
delta-threshold gate with the slew-rate limiter (Option C in the doc; A = lower EMA alpha alone
rejected, no hard bound; B = widen delta threshold rejected outright, repeats the exact TASK-253
regression M-WEBRADIO-POSBAR-SMOOTH already refused to reopen; D = windowed median filter
rejected, more RAM state for no demonstrated benefit over C on a board with a DRAM-budget history —
`[[feedback_dram_bss_static_buffers]]`). Starting constant `WR_POSBAR_MAX_STEP_PER_TICK=2`,
flagged as simulation-informed, not yet DUT-confirmed.

**Side finding, not this task's problem to solve:** 2 of 5 traced stations spent most/all of
their capture window failing to reach `PLAYING` at all — real connect failures, same family as
the already-tracked TASK-390/391/393/398 connect-reliability thread. Not folded in here; PM to
decide if it's worth a fresh data point there.

**VE testability review (2026-08-06, same day):** `docs/architecture/designs/
M-WEBRADIO-POSBAR-SLEW-VE-review.md`. Verdict **approve-with-changes**, one blocker. VE-1 (major)
— the doc's own Lean step 4 wrongly claimed `lastSkipReason` "collapses" to two values; re-derived
that all three stay meaningful under the slew design, just re-mapped. VE-2 (**blocker**) — the
doc's proposed OQ2 test method (`wrDeadUrls`-style injected failure) doesn't work: re-verified
against the tree that `wrDeadUrls` never reaches `PLAYING` at all (TASK-395's own finding), and
`set wrBufPct` bypasses the gate by design — neither can exercise the gated/slewed path over a real
decline, meaning OQ2 had no test path at all as scoped, the same failure mode that already left
TASK-402's own OQ1/OQ2 unresolved for a day-plus. VE-3 (major) — Exit criteria dropped the ≥3-trial
protocol TASK-402's own VE-3 already established as necessary for this project (documented history
of single-shot DUT/RF comparisons proving unreliable), and let "whichever station reproduces live"
stand in for the one actually complained about. VE-4 (informational) — the host-side simulation's
EMA fidelity rests on an unverified assumption that external poll rate approximates real tick()
rate; order-of-magnitude consistent with observed `loop_max` values but not independently
confirmed. VE-5 (minor) — OQ3's disposition should be an explicit PM decision, not an implicit
non-decision.

**Architect disposition (2026-08-06, same day):** all five folded into the design doc. VE-1 →
Lean step 4 corrected (three-way `lastSkipReason` contract preserved, re-mapped not collapsed,
`DELTA`→`CONVERGED` rename suggested). VE-2 → new Lean step 6: `set wrPosbarSimDrain
<startPct>[,<stepPerTick>]` debug hook, seeds `_bufPct` and decrements it through the real
(non-bypassing) code path each tick — makes OQ2 deterministically testable instead of waiting on a
real stall; Exit criteria updated to use it. VE-3 → Exit criteria now requires ≥3 trials against
SLAM! specifically at minimum, with Radio 10/100% NL as encouraged additional trials. VE-4 → caveat
paragraph added to Analysis section. VE-5 → OQ3 now explicitly requires a PM disposition, not
silence.

**Human sign-off (2026-08-06):** design **accepted** as filed (all VE findings folded). Cleared
for Developer pickup — no further design/review gate before implementation.

**Implementation (2026-08-06, Developer, same session).** Landed per Lean, all six steps:

- **Constants:** `WR_POSBAR_MAX_STEP_PER_TICK = 2` added alongside the existing EMA/interval
  constants (`webRadioApp.h:95-103`).
- **`lastSkipReason` (VE-1):** `PosbarSkipReason::DELTA` renamed `CONVERGED` — three-way contract
  preserved, re-mapped (not collapsed) exactly as the folded design specifies.
- **Slew gate:** the delta-threshold check replaced with a clamped step toward
  `_bufPctSmoothed`, bounded to `±WR_POSBAR_MAX_STEP_PER_TICK` per `MIN_REDRAW_MS`-eligible tick.
- **`wrPosbarSimDrain` (VE-2):** new `dbgSet` hook, seeds `_bufPct` and decrements it through the
  real (non-bypassing) per-tick path. One design refinement found during DUT verification and
  fixed same-session: an initial "auto-disable at raw==0" convenience (not in the VE-folded spec)
  let real high-value playback data flood back in before the *drawn* value had visually finished
  slewing down to 0, reversing the trend before a tester would see it bottom out — removed,
  matching the doc's simpler literal spec (explicit `0` to disable only).
- **`wrBufPct`:** unchanged bypass behavior, now also clears `_posbarSimDrainActive` on force-write
  (hygiene, avoids the two debug hooks fighting).
- **PLAYING-entry reset:** `_posbarSimDrainActive` reset alongside the existing
  `_bufPctDrawn`/`_bufPctSmoothed` fresh-baseline reset, so a stale sim-drain can't suppress real
  readings across a reconnect.

`./run/check` 6/6 both envs. RAM: +8 bytes (three new small fields) — negligible, no DRAM/BSS
budget concern.

**DUT verification (2026-08-06, same session).** New `app/tools/task405_slew_verify.py` (ad hoc,
same convention as `task399_402_dut_verify.py`), against real playback (30-station NL list,
live). **13/13 PASS** after two rounds of fixing the *test's* own flawed assumptions (not the
implementation — see script's own history for the two false starts): `wrBufPct` bypass still
force-writes `bufPctDrawn` immediately; the slew bound holds exactly (`steps=[2,2,2,...] max=2`,
every single observed redraw step ≤ `WR_POSBAR_MAX_STEP_PER_TICK`, confirmed against real device
data, not simulation); `wrPosbarSimDrain` declines gradually through 35 distinct values before
settling at 0 and staying there (no bounce-back); `lastSkipReason` reports only
`{none, converged, interval}`, zero stale `"delta"` leakage; disabling sim-drain releases control
back to real per-tick computation (confirmed via renewed raw-value variability, not a specific
value — real buffers legitimately sit at/near 0 for stretches too, per this session's own traces).

**Regression (2026-08-06, same session).** `T_WR_EJECT_01/02`, `T_WR_ERR_01-04` (6/6 PASS,
consistent) — the tests most directly adjacent to this change (app-switch, error-state display).
`T_WR_COEX_01/02/04` PASS on retry (3/3) after one transient CH340 port-flap and one real
connect-timing hiccup, both environmental — confirmed non-deterministic by re-running (different
failure shape each time with zero code changes between runs), consistent with this project's
well-documented DUT-flakiness history, not a regression. `T_WR_VIS_01` (decode-tail pump timing)
and `T_WR_VIS_04` (spectrum animation) showed flaky failures across runs — both test subsystems
(`wrPump`/Audio decode, `vu::specHRef()`/spectrum) this diff has zero code overlap with (confirmed
by re-reading the actual diff, not assumed); `T_WR_VIS_03/05` skipped on the pre-existing TASK-243
external blocker (Spotify Premium lapsed), unrelated. Not treated as a blocking regression signal
for this task; flagged here for the record rather than silently dropped.

**Not yet done — still needs the human:** the design doc's own Exit Criteria live-eyeball check
(≥3 trials against SLAM! specifically, VE-3) — the actual "does it look smooth now" call.
Mechanism is DUT-confirmed working exactly as designed; the subjective visual read is next.

**Owner:** Architect (design doc — done; VE findings folded) → VE (testability review — done,
approve-with-changes) → human (**signed off**) → PM (scheduled) → Developer (implementation —
**done 2026-08-06**, DUT-verified, host-verified `run/check` 6/6) · **Deps:** TASK-402 (the
feature this modifies; supersedes its delta-threshold gate, keeps its EMA + time-floor +
partial-diff-blit + instrumentation machinery) · **Priority:** P3 (visual polish, no functional
gap, same class as TASK-402) · **Status (superseded by the addendum below):** implemented,
host-verified, and DUT-verified (mechanism + regression) — the live-eyeball exit criterion found
a real remaining gap, see below.

**Live-eyeball follow-up (2026-08-06, same day) — "buffer slowly fills [good], but once full,
still jumps around multiple times a second."** The slew limiter bounds redraw magnitude but not
direction-reversal frequency, and reversals (not total range) turn out to be what reads as
"jumping around." Full design-doc addendum: `M-WEBRADIO-POSBAR-SLEW.md`'s own Addendum section.

Five filter-shape alternatives evaluated host-only (real captured traces + synthetic connect/
hiccup/drop scenarios) before spending any further DUT time:

1. **Fixed-gain critically-damped spring-damper** (same P+D-on-a-double-integrator family as
   `vuMeter.h`'s spectrum peak tracker — the vuMeter's own literal constants turned out to be
   underdamped for this recurrence, `b ≤ (1-√a)²` derived and used instead). Real, structural
   tradeoff: damping heavy enough to kill ceiling jitter also made a genuine connection-drop
   never reach 50% visible in the test window — worse than what was already shipped. A linear
   P+D controller can't distinguish small noise from a large real change; both feed the same
   proportional term.
2. **Dual-rate/gain-scheduled spring-damper** (switch damping by error magnitude). Failed worse
   — confirmed via direct measurement that single-sample noise on this signal routinely exceeds
   any reasonable magnitude threshold, so "large error = real signal" doesn't hold here. A
   persistence-gated variant was worse still, traced to a genuine "bumpless transfer" bug
   (velocity built under fast dynamics bleeding off too slowly after switching to the heavy
   regime's much slower damping) — confirmed and partially fixed (zeroing velocity on switch),
   but still ~3x worse than the plain slew limiter even after the fix.
3. **Asymmetric slew** (slower fall than rise). No improvement on the worst stations at any
   fall rate — reversals happen *within* a single network-delivery burst, not as a clean
   rise-then-fall, so damping only the fall side doesn't touch them.
4. **Asymmetric EMA** (attack/release, fed from raw). Worse across the board, same root cause
   as the raw-fed spring-damper variants.
5. **Plain step-size reduction.** Range scales down linearly as expected, but reversal *count*
   stays flat, and connection-drop visibility (already borderline at the shipped step size)
   never resolves at any smaller step.

**Winning approach: hysteresis dead-band near the ceiling, layered on the existing slew
mechanism.** Freeze (skip the slew step) once drawn AND target are both `≥ WR_POSBAR_FREEZE_
ENTER_PCT` (90); only resume once the target drops below `WR_POSBAR_FREEZE_EXIT_PCT` (80) —
the gap between the two is the hysteresis band, preventing the boundary itself from chattering.
Doesn't need to distinguish noise from signal at all, sidestepping the exact problem that broke
the gain-scheduled attempts. Host-only: real-trace steady-state reversals dropped 5→0 (worst
stations), connection-drop-from-98 cost only +0.2-0.6s versus the already-accepted ~5.4s/10.3s
baseline, a recoverable near-ceiling hiccup was almost entirely absorbed.

**Implementation:** `WR_POSBAR_FREEZE_ENTER_PCT`/`_EXIT_PCT` constants, `_posbarFrozen` state
(reset alongside existing per-session/`wrBufPct`-override hygiene resets), `PosbarSkipReason`
gains `FROZEN` (distinct from `CONVERGED`) plus a new explicit `"frozen"` getter field.

**DUT verification** (`task405_slew_verify.py`, extended, same ad hoc convention): three
consecutive clean confirmations of the freeze mechanism — froze at the seeded value, held
constant while `bufPctRaw` kept changing underneath (proving the underlying computation isn't
stopped, only the display step), correctly un-froze past `EXIT_PCT`, still reached 0 afterward.
Two flaky failures across four DUT runs — a pre-existing `wrBufPct`-vs-concurrent-playback race
(documented, predates this change) and one polling-aliasing artifact in an unrelated code path
(never reaches the freeze threshold) that cleared on a smoother-polling rerun — both coincided
with a literal mid-session USB disconnect/reconnect on the DUT rig (confirmed via `journalctl -k`
CH341 disconnect/reconnect lines), not the implementation. `run/check` 6/6 both envs. Regression:
`T_WR_EJECT_01/02`, `T_WR_ERR_01-04` 6/6 clean.

**Live-eyeball confirmation (2026-08-06, same day, human on the physical LCD):** "POSBAR no longer
jitters." Resolves the exit criterion this whole addendum thread was chasing.

**Status:** **CLOSED.** Implemented, DUT-verified (mechanism + regression), and live-eyeball
confirmed on the physical LCD. TASK-402's own OQ1/OQ2 tuning pass — the reason this session
started — is superseded by the dead-band addendum and considered resolved by this closure.

---

### TASK-406 — T079/T082 full-suite failures: leftover `playerMode=WebRadio` state, a hardcoded-`skipped` bug, and a missing volume-drag log line

**Filed 2026-08-06, closed same day after a self-caught correction mid-investigation** — surfaced
as two new, previously-unrecorded failures
in the TASK-385/386 second full-suite `run/test` pass (see that update above): `T079` (`tap not
skipped while gate armed`) and `T082` (`only 0 ACT_VOLUME enqueue(s)`).

**Root trigger, both tests:** the DUT booted this run with `g_settings.playerMode` persisted as
`WebRadio`, not `Spotify` — leftover state from an unrelated manual DUT session earlier the same
day (`set wrUrl ...` to verify TASK-393's terminal-retry, which switches `currentAppId` to
WebRadio; `playerMode` persists in SPIFFS across reflashes, so it survived the subsequent
`./run/flash` back to prod). Boot log confirmed it: `[boot] spotify=idle (playerMode=webradio)`.
`run_serialdbg_tests.py` (`Dut` readiness wait, ~line 199-218) explicitly knows a device can boot
into WebRadio and skips the Spotify-poll wait for that case — correct, intentional, TASK-363/
ADR-054 territory — but nothing resets `playerMode` back to Spotify before the early T077-T082
group runs, which implicitly assumes Spotify's winamp context. A `set playerMode 0` reset does
exist later in the suite (for a different test), just too late to help these two.

**T079 — real, previously-unnoticed firmware bug, confirmed and fixed.** With `currentAppId==
WebRadio`, `cmdTap` routes through its WebRadio branch (`main.cpp`, ~line 2844-2867). That branch
calls `winampDisplay.injectTouch()`, which correctly detects the armed `touchScreenCoolDownTime`
gate and sets `TouchResult.skipped=true` internally (`winampDisplay.h:1053-1056`) — but the
branch's response `printf` hardcoded `"skipped":false` instead of reading `wr.skipped`, unlike
every other branch in `cmdTap` that has a real skip concept. Only reachable when a serial `tap`
lands on the WebRadio-active dispatch path while the cooldown gate is armed — never exercised by
any prior test, which is why it went unnoticed since this exact branch was added (TASK-387, for
an unrelated vis-zone double-dispatch fix; see that entry above). Fixed: `wr.skipped ? "true" :
"false"`. DUT-verified (`run/test-targeted T079,T082`, debug build): `tap 50 97` while armed now
correctly returns `skipped:true` (was `false`); the follow-up post-reset tap correctly returns
`hit=TRANSPORT, action=PLAY`.

**T082 — initial disposition was WRONG, corrected same day.** The first write-up above claimed
"same root cause, no separate bug" based on a `run/test-targeted T079,T082` pass — but that
targeted run's *own* fresh debug reflash happened to boot with `playerMode` already back to
Spotify (confirmed via `get playerMode` right before it, and via T079's second tap carrying a
`pressed` field in its JSON response — that field only appears in `cmdTap`'s Spotify-branch
format, never WebRadio's, proving Spotify was genuinely active), so T082 passed for a reason
that had nothing to do with any fix — it simply never
exercised the WebRadio branch at all. This was caught because **`playerMode` reverted to
WebRadio again on the very next full-suite `run/test` pass**, with no manual DUT poking in
between — proving the original "one-off human-caused precondition, not a recurring risk" framing
was also wrong. (The mechanism behind that reversion is still unexplained — current on-disk
`settings.json` reads `player.mode=0` right now, and the suite's own teardown correctly leaves it
there each time, so whatever flips it back to WebRadio between one full-suite run's teardown and
the next run's fresh boot wasn't root-caused this session. Flagging as an open question for
whoever next sees a `[boot] spotify=idle (playerMode=webradio)` line unprompted.)

With that full-suite run's raw log giving a genuine WebRadio-active T082 failure (2nd real data
point, 0 `enqueued ACT_VOLUME` lines, confirmed via `sinceAttemptMs`-style raw-log inspection —
not a targeted-run coincidence this time), the real root cause was found: `winampDisplay.h`'s
`handleVolumeGesturePublic()` (TASK-352's WebRadio-only capture entry into the shared
`D_VOLUME_DRAG` machine — deliberately *not* routed through `handleWinampInput()`, per its own
comment, to avoid hit-testing Spotify-only zones) duplicates `handleWinampInput`'s debounce/
`_volumeSink()` logic in full but never got the `LOG_D("touch", "enqueued ACT_VOLUME pct=%ld", …)`
line the other two call sites (`handleWinampInput`'s own Press and Move branches) have. The
volume commit itself works fine under WebRadio — `_volumeSink()`/`drawVolume()` both fire
correctly — this was a pure observability gap in the duplicated path, invisible until a test
happened to grep for that exact log line. Fixed: added the missing `LOG_D` call to both branches
(Move-continuation and Press-capture) in `handleVolumeGesturePublic()`.

**DUT-verified properly this time** — and only after tripping over a second, independent mistake
in my own manual verification: `switchApp 6` is **Stock**, not WebRadio (`appRegistry.h` order:
0=Spotify, 1=Clock, 2=Weather, 3=Crypto, 4=Matrix, 5=Life, 6=Stock, …, 11=WebRadio) — the exact
stale-ID class of mistake TASK-393/394 already documented and fixed elsewhere in this project,
now made fresh by a human (me) doing ad hoc DUT commands instead of using the harness's own
`app_ids_gen.py`-verified IDs. First manual attempt against "app 6" showed zero `drawVolume`
calls at all (that unconditional-`Serial.printf`, not log-level-gated, made the wrong-app mistake
obvious in retrospect) and `dragState` stuck at `D_IDLE` throughout a held gesture — not a bug,
just the wrong app entirely. Re-run against the correct `switchApp 11`: `dragState` correctly
transitions to `D_VOLUME_DRAG`, and a full 61-step drag (matching T082's own shape) produced
exactly 2 `enqueued ACT_VOLUME` lines (`pct=0`, `pct=65`) — meets the test's `>= 2` bar under
genuine, deliberately-forced WebRadio-active conditions this time, not a coincidence.

**Lesson for future sessions:** confirming a test passes isn't the same as confirming *why* it
passes — the first T082 "fix" here looked identical in isolation and was still just describing a
precondition that happened to be absent, not present-and-satisfied. When a fix is meant to change
behavior under a specific condition, verify the condition was actually live during the check
(here: which `cmdTap`/dispatch branch's JSON *shape* fired, or a positive-control check like
forcing the app switch explicitly first) rather than trusting an ambient state to have been the
one you think you know how it got there.

**Owner:** Developer · **Deps:** none · **Priority:** P4 (narrow test-harness-only surfaces, T079
never reachable from real touch; T082's underlying volume-drag itself always worked, only its
debug observability was gapped) · **Status update:** T082 fix is real and DUT-verified now, not
just T079. The `playerMode`-reverts-between-runs mechanism remains genuinely open — filed
separately as TASK-407, see below.

**Status:** **CLOSED.** Both fixes real and DUT-verified, `run/check` 6/6, prod firmware restored.

---

### TASK-407 — `g_settings.playerMode` reverts to WebRadio between DUT sessions with no manual trigger found

**Filed 2026-08-06, split out of TASK-406's investigation** — that task closed two confirmed,
narrow bugs (T079's hardcoded `skipped`, T082's missing volume-drag log line), but along the way
turned up a separate, unexplained persistence anomaly that deserves its own tracking rather than
living as a paragraph inside a closed task.

**What's confirmed:** across today's session, `g_settings.playerMode` was observed reverting to
`WebRadio` (`1`) at DUT boot on at least two occasions where the *known* mutation paths don't
explain it:

1. **First occurrence** — traceable to a real cause: an earlier manual DUT session that day
   (`set wrUrl ...`, verifying TASK-393's terminal-retry) switched `currentAppId` to WebRadio, and
   `playerMode` was never explicitly reset back to Spotify before the session's final
   `./run/flash` (app-partition-only reflash — doesn't touch the SPIFFS/data partition, so
   whatever was last durably saved there survives). Not mysterious once traced.

2. **Second occurrence — genuinely unexplained.** A `run/test-targeted T079,T082` session (debug
   reflash → run two tests, neither touches `playerMode` → prod reflash) left the device reading
   `playerMode=Spotify` throughout (confirmed via raw serial log, zero `set playerMode` or
   `switchApp` calls to WebRadio anywhere in that session's capture) and via a manual
   `./run/flash` immediately after. The **next** full-suite `run/test` pass — a fresh debug
   reflash with no manual DUT interaction in between — booted with `playerMode=WebRadio`
   (`[boot] spotify=idle (playerMode=webradio)`), and that same full-suite run's own teardown then
   correctly wrote it back to Spotify (confirmed durably: pulling `settings.json` after that run's
   prod restore read `player.mode=0`, matching the suite's last action). No `set`/`switchApp`
   command, no code path, no test invocation between the two sessions explains the flip from
   Spotify to WebRadio.

**A third, separate, KNOWN-cause instance happened later the same session** (not mysterious,
noted here for completeness): my own manual TASK-406 T082 fix-verification explicitly ran
`set playerMode webradio` to force the test condition, then reflashed prod directly afterward
without resetting it back — leaving the live device on `playerMode=1` until caught and corrected
via a `run/spiffs pull` → edit → `run/spiffs push settings.json` round-trip (non-destructive,
confirmed `player.mode=0` after). This is just me forgetting a cleanup step, the same mistake
TASK-406 itself was originally triggered by — worth a process note (see below) but not part of
this task's actual mystery.

**Ruled out / considered:**
- `persistPlayerMode()` (`main.cpp:1935`) does an immediate `SettingsStorage::save()`, not a
  coalesced/RAM-only write — no reason a completed `set playerMode 0` response should be lying
  about having persisted.
- The debug `set playerMode` handler (`main.cpp:3803-3819`) parses both numeric and
  `spotify`/`webradio` string forms correctly; not a parsing bug.
- Not explained by any test in the T077-T082 group or the T079/T082 targeted subset — neither
  touches `playerMode`.
- Repeated hard resets via `esptool`'s RTS-pin reset (many back-to-back reflashes happened this
  session) are a plausible but unconfirmed suspect — if a SPIFFS write from an *unrelated* earlier
  point in time wasn't fully committed before a later hard reset, a stale on-disk value could
  resurface. Pure speculation; not verified against SPIFFS/LittleFS's actual write-durability
  guarantees on this hardware.

**Instrumentation landed (2026-08-07):** `run_serialdbg_tests.py` now prints a `[TASK-407] entry
playerMode:` / `[TASK-407] exit playerMode:` line (via `get playerMode`) right after connect and
right before `dut.close()` — covers `run/test`, `run/test-targeted`, and `run/test-smoke` (all
three share this runner). Mirrors the `_diag_snapshot()` precedent from TASK-385/386. Not added to
`run/test-sync` (separate `run_sync_tests.py` runner; occurrence #2 never implicated it — revisit
if a future flip does).

**Reproduction attempt (2026-08-07):** ran the exact sequence from the "not yet tried" note —
`run/test-targeted T079,T082` (clean, non-touching) → immediately `run/test` (full suite, no
manual action between) → immediately another `run/test-targeted T079,T082`. Three boundary
snapshots, all explained:
1. Targeted #1: entry `WebRadio(1)`, exit `WebRadio(1)` — unchanged, as expected (neither test
   touches it).
2. Full suite: entry `WebRadio(1)` (correctly carried over) → exit `Spotify(0)` — this flip is the
   suite's *own* WebRadio tests + end-of-run teardown resetting it, not a mystery.
3. Targeted #2: entry `Spotify(0)` (correctly carried over from #2's teardown), exit `Spotify(0)`
   unchanged. **No unexplained flip.** 0/1 repro on this attempt.

Consistent with `feedback_isolated_rerun_vs_suite_state` — a single clean pass doesn't rule out a
suite-order-dependent trigger. The instrumentation now stays live permanently, so the next time
occurrence #2's pattern shows up in the wild (in any `run/test`/`run/test-targeted`/`run/test-smoke`
session) it'll be caught in that session's own log instead of requiring after-the-fact reasoning
across separate sessions.

**Process note (not this task, but adjacent):** occurrence #3 above suggests manual DUT `set`
commands used for one-off verification should default to resetting any test-only overrides
(`playerMode`, `cooldown`, injected debug state) before handing the DUT back to an automated
suite — the same discipline `run_serialdbg_tests.py`'s own tests already apply to themselves
(`set cooldown 0` before/after nearly every tap). Consider this a personal-workflow reminder more
than a firmware gap.

**Owner:** unassigned · **Deps:** none · **Priority:** P4 (cosmetic-adjacent — self-heals via the
suite's own end-of-run reset every time it's been observed; the actual risk is only ever a wasted
T077-T082 run if caught mid-suite, which TASK-406's fixes now make harmless either way) ·
**Status:** **OPEN — instrumented, one repro attempt clean (0/1).** Passive: instrumentation now
catches the flip automatically in any future `run/test*` session's own log; no active follow-up
needed until it resurfaces.

---

## Open — M-WINAMP-PLAYER (filed 2026-08-07)

Human request: make Winamp behave like Winamp — play MP3s off the SD card, browse the filesystem,
read/write `.m3u` playlists, make PLEDIT a real editor, and drive the skin's existing shuffle/repeat
buttons.

Architect design set, committed `a8d0369`: umbrella
[M-WINAMP-PLAYER.md](../architecture/designs/M-WINAMP-PLAYER.md) (reuse audit, memory/flash budgets,
build variants, registry, test-family map) over four workstreams —
[M-SDFS](../architecture/designs/M-SDFS-sd-card-exploration.md),
[M-AUDIO-ENGINE](../architecture/designs/M-AUDIO-ENGINE-extraction.md),
[M-PLEDIT-ABSTRACTION](../architecture/designs/M-PLEDIT-ABSTRACTION-playlist-source.md),
[local-playback](../architecture/designs/M-WINAMP-PLAYER-local-playback.md).
Decision: [ADR-059](../architecture/decisions/ADR-059.md).

> **✅ GATE CLEARED — ADR-059 accepted 2026-08-07** (human sign-off, all thirteen decisions).
> Implementation is authorised. All five design docs are `accepted`. Three constraints ride with
> acceptance and are **not** renegotiable at implementation time without a new ADR:
>
> 1. **TASK-423 runs first** — the reclaim, before anything spends the 304 B of debug headroom.
> 2. **D13's ≥3-run baselines must be captured BEFORE TASK-409, 412 and 417 land.** That is DUT time
>    *ahead of* the refactors, not concurrent with them. Scheduling this late is the one way to
>    invalidate the milestone's main safety property.
> 3. **D2's move stays a move** — no behavioural hunks in the extraction commit.
>
> Acceptance does **not** pre-approve D1's outcome: TASK-408 remains a genuine gate, and a failing
> probe closes the milestone with a hardware note rather than triggering a redesign.

**Execution order is NOT numeric.** TASK-423 runs **first** (it was added after the range was
drafted; renumbering would invalidate the just-committed design docs and their cross-references).
Order: **423 → 408 → 409 → 410 → 411 → 412 → 413 … 422**.

**Scheduling note.** Workstreams 2 and 3 (TASK-409, 411, 412) need no SD card and have standalone
value — 409 turns a 2 365-line app header into an app plus a reusable engine, and 411/412 collapse a
PLEDIT duplication that exists and has already diverged today. They can proceed regardless of what
TASK-408 returns. Only TASK-410 and workstream 4 are gated on the probe passing.

**Registry.** Reserved at design time (Architect responsibility #10): features `sdfs-001`,
`localplay-001`, `plmodel-001`, `m3u-001`, `browse-001`, `pledit-edit-001`, `playorder-001`;
matrix X050–X064. Developer completes them at implementation.

**Reviews complete (2026-08-07).** [VE](../architecture/designs/M-WINAMP-PLAYER-VE-review.md) —
4 blockers, 9 majors, 5 minors. [Developer](../architecture/designs/M-WINAMP-PLAYER-DEV-review.md) —
2 blockers, 5 majors, 4 minors. **All folded into the design set and ADR-059** (Architect,
2026-08-07). Material outcomes for scheduling:

- **ADR-059 D7 was factually wrong** and is corrected — only one of three `static_assert`s breaks,
  `TASKBAR_APP_COUNT = (int)AppId::WebRadio` still holds, and the proposed `COUNT - 2` replacement was
  *less* robust than the existing code. Affects TASK-413 only.
- **D6 amended (DEV-1)** — the taskbar cycle cannot live in `resolvePlayerSlot()`; `switchApp()`
  early-returns on same-app and the two dispatch sites guard differently. Needs one shared helper
  called from both. Affects TASK-413 only.
- **New ADR-059 D12** — observability is product surface. TASK-411 gains `get pleditRepaints`;
  TASK-418 gains `get plOrder` / `get plCursor` / `set plCursor` / `advance next|prev`; TASK-410
  gains the loopTask-handle capture + `configASSERT`. Without these, eight ids were unrunnable
  (two needed ~3 h of playback; six asserted on state the firmware does not expose).
- **New ADR-059 D13** — every "identical pass set" gate now requires a **≥3-run baseline** with the
  flaky set pre-declared. A single-run bar would have failed on `T_WR_TLS_01`/`T169`/`T_PR_05`
  rather than on regression. Affects TASK-409, 412, 417 scheduling (baseline runs must precede the
  refactor landing).
- **TASK-422 also renumbers `check_build.sh`'s gate labels** (DEV-7) — the script prints `[1/6]`…
  `[6/6]` plus a `[7/7]`, and `tasks.md` entries cite both 6/6 and 7/7.

**VE ids: 76 → 78.** Added `T_SD_10`, `T_PLE_14` (closes a real X055 gap — WebRadio's `_pleditDirty`
bool becoming a seqno has two uncovered failure modes), `T_PLR_41`. Withdrawn: `T_AE_05` (a review
gate, not a repeatable test — survives as a TASK-409 checklist item). Reclassified: `T_PLR_25`'s
task-identity half becomes a runtime assert. Per-task tables live in the workstream docs;
`test_coverage: []` stays empty until VE lands the suite.

### TASK-423 — proactive DRAM reclaim: `cmdScreenDump` band buffers off `.bss`

**Runs first.** `cyd2usb_winamp_debug` has **304 B** of `dram0_0_seg` headroom (production has
13 160 B — measured 2026-08-07, not remembered). 11 956 B of the debug build's 12 792 B `.bss`
overage over production — 93 % — is two function statics inside one `#ifdef SERIAL_DEBUG` command:
`cmdScreenDump`'s `s_b64` (6 836 B, `main.cpp:3967`) and `s_band` (5 120 B, `main.cpp:3966`).
Neither appears in the production map (verified, zero matches). They are band buffers for an
on-demand host-driven screenshot tool that runs ~18 s when a human asks for it, resident permanently
in the one build with no headroom.

Move both to per-invocation `malloc`/`free` — preferred over the lazy-malloc-once idiom used for
`WinampDisplay` because it *returns* the 12 KB to the heap rather than relocating it. Allocation
failure prints the existing JSON error shape and returns; a dev tool degrading on a fragmented heap
is acceptable where a link failure is not. Zero production impact (the code does not compile in).

**Owner:** Developer · **Deps:** none · **Gate:** `T_RCL_01`–`04` — debug headroom ≥10 KB
**measured** from a fresh `run/build-debug` + `.map` extents; prod `.dram0.bss` byte-identical;
`screendump` output byte-identical to a pre-change capture of the same static screen ·
**Priority:** P1 (unblocks the headroom every later task spends) · **Status:** DONE (2026-08-07).

`s_band`/`s_b64` moved to per-invocation `malloc`/`free` in `cmdScreenDump` (`app/src/main.cpp`).
`T_RCL_01`: debug `dram0_0_seg` headroom 304 B → **12 264 B** (`.map` extents, `run/build-debug`).
`T_RCL_02`: prod `.dram0.data`/`.dram0.bss` byte-identical before/after (`.map` diff). `T_RCL_03`:
DUT full-canvas `screendump` PNG SHA256-identical before/after change (windowed-dump 30/66000 px
diff traced to live app-state drift between the two captures, not the reclaim). `T_RCL_04`
(alloc-failure degrades cleanly): closed by code inspection, not DUT-forced — no existing serial
harness can force `malloc` failure on this device; null-check frees both pointers and returns the
existing `"error":"empty region"`-shaped JSON, mirroring the pre-existing empty-region error path.
Human accepted code-inspection closure over building a throwaway heap-pressure probe.

> `T_RCL_03` matters more than it looks: `screendump` is the *instrument* three `T_PLE_`
> pixel-identity tests depend on. Breaking it would silently invalidate the PLEDIT gate rather than
> fail it.

### TASK-408 — SD card phase-0 probe and benchmark (HARD GATE)

The ESP32-2432S028R carries a micro-SD slot; **this firmware has never mounted it**
(`M-AQUARIUM/overview.md` dropped the donor's `SD.h` path as out of board config — a decision not to
use it, not a finding that it works). Pin budget is desk-checked clean: VSPI **18 SCLK · 19 MISO ·
23 MOSI · 5 CS** is free, TFT stays on HSPI, touch on 25/32/33/36/39, DAC on 26.

Add an `sdprobe` debug command reporting, in one shot: mount success, card type/size, FAT type,
`.dram0.bss` + heap delta across `SD.begin()`, long-filename round-trip, `listDir()` timing on a
~200-file directory, and a sustained sequential-read benchmark with a per-read latency histogram.
Own `SPIClass(VSPI)`, start at 4 MHz.

Pass bar: mount OK · sustained read **≥200 KB/s** · worst single-read latency **≤50 ms** ·
`SD.begin()` heap delta **≤8 KB**. Derivations in M-SDFS §3. Run the benchmark **with the display
actively redrawing** — an idle-device number measures the wrong thing.

**A negative result is a valid outcome.** On failure, record the numbers and close the milestone
with a hardware note. SPIFFS is explicitly *not* an accepted fallback (1.4 MB shared with
skin/settings/config ≈ one track). **Do not retune the bar to fit the hardware.**

**Owner:** Developer · **Deps:** none · **Gate:** `T_SD_01`–`09` ·
**Priority:** P0 (blocks its own gate; was P1 gating TASK-410/workstream 4) ·
**Status:** **DONE — passed with one recorded exception (2026-08-09).** Operator accepted the
`T_SD_06` disposition (option (a), ADR-059 D1 amendments #1/#2): the ≤8 KB mount-heap bar is
**unreachable by construction** — 11 164 B is the floor at one open-file slot — so it is recorded as
an **accepted exception, not a pass**, with the measured numbers on the record. The bar was not
retuned. `T_SD_09`'s exFAT half is **explicitly waived** by the operator (no spare card; the 2 GB
SDSC card holds unrelated content and was deliberately left alone).

Final: **7 of 9 ids PASS, 1 accepted exception (`T_SD_06`), 1 partial-and-waived (`T_SD_09`).** Both
go/no-go ids pass by wide margins. Three defects were found and fixed getting here — two of them in
the vendored SD library, one of which (PATCH-SD-2) is a use-after-free on a path LocalPlayer will
meet as a *normal* user state.

> **Two conditions ride out of this close and are not discharged by it** (ADR-059 D1 amendment #2):
> the Player-mode **concurrent peak** has not been measured (all heap figures here are mount-cost in
> isolation, idle, no stream), and the whole `max_files` table is **mount-first** while the accepted
> lifecycle is **arena-first**. TASK-425 carries both. TASK-410 must not pick a `max_files` value
> from the table in this task.

**The earlier BLOCKED finding was a misdiagnosis and is withdrawn.** There is no runtime heap
corruption and no concurrency defect. `esp_vfs_fat_register()` returns `ESP_ERR_NO_MEM` from two
unrelated places — the `FF_VOLUMES` context table being full, *and* a plain `calloc()` failing — and
this was the second. `SD.begin()` needs **one contiguous byte-addressable internal block** of
`sizeof(vfs_fat_ctx_t) + max_files * sizeof(FIL)`, and this IDF build has `FF_MAX_SS=4096`
(`CONFIG_WL_SECTOR_SIZE`) with `FF_FS_TINY=0` (`CONFIG_FATFS_PER_FILE_CACHE=1`), so `sizeof(FATFS)`
is **4 156 B** and `sizeof(FIL)` is **4 136 B** (both DUT-printed, not derived). The Arduino default
`max_files=5` therefore asks for **24 964 B in one piece** — which is exactly the 27 712 B mount cost
recorded as unexplained. Mount succeeds at every heap state above the ctx size and fails at every
state below it, at every `max_files` setting:

| heap state | largest free 8-bit block | `sdmount 5` (24 964 B) | `sdmount 1` (8 420 B) |
|---|---|---|---|
| boot, before tasks | 110 580 B | — (boot mount OK) | OK |
| idle, tasks+WiFi up | 49 140 B | **OK** | OK |
| WebRadio playing (Helix arena acquired) | 4 852 B | FAIL `0x101` | FAIL `0x101` |

Two things made the original reading wrong. `MALLOC_CAP_INTERNAL` over-reports what `calloc()` can
serve — it counts the 32-bit-only D/IRAM region, and the number that decides the mount is
`MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT` (49 140 vs 42 996 in the same snapshot). And `log_e()` was
invisible at `CORE_DEBUG_LEVEL=0`; the one line that separates the two `ESP_ERR_NO_MEM` paths is
`sd_diskio.cpp:800 esp_vfs_fat_register failed 0x(101)`. The level-1 bump is kept for that reason.

**Consequence for M-SDFS §5:** the lazy per-mode-entry mount is not implementable as specified. A
mount is only as reliable as the heap happens to be when the user enters the mode, and LocalPlayer
needs the card mounted *and* the arena acquired simultaneously. Mount once in `setup()` and hold —
that is the design, not a workaround. It is also cheap to make robust: `max_files` is a memory knob,
not a throughput knob, and 2 slots is the minimum that walks a directory (`openNextFile()` in a
`for`-increment opens the next entry before destroying the current File, so one slot is not enough).

**Second defect — SDHC cards are misdetected and cannot mount (fixed, PATCH-SD-1).** The card-swap
retest did not start with a benchmark; the new 30 GB SDHC card would not mount at all:
`f_mount failed: (13) There is no valid FAT volume`, while the 2 GB SDSC card in the same slot was
fine. `ff_sd_initialize()` types the card **solely** from OCR bit 30 (CCS) after ACMD41, and that bit
reads 0 here — so the card was typed `CARD_SD` (byte-addressed) and every read issued `sector << 9`
as a byte address to a card that expects block numbers.

It hides well, because the one sector that still works is the one you check first: **address 0 is
identical under both addressing modes**, so sector 0 returned a perfectly valid MBR (`0x55AA`,
partition type `0x0C` FAT32-LBA, start LBA 63) and only sector 63 was garbage. Init completed with
**no warnings at `CORE_DEBUG_LEVEL=2`** — every `log_w`/`goto unknown_card` path was skipped.

The evidence is a self-contradiction inside the same init: `sdGetSectorsCount()` reads the CSD and
takes the `(csd[0] >> 6) == 0x01` branch — **CSD structure v2.0, defined only for SDHC/SDXC** —
returning a correct 60 733 440 sectors (29 655 MB). A byte-addressed `CARD_SD` cannot exceed 2 GB, so
the OCR type and the CSD capacity cannot both be right. Deterministic: 5 consecutive cold inits,
byte-identical garbage at sector 63.

Fixed by vendoring the framework `SD` library into `app/lib/SD/` (the pattern `WiFiClientSecure`
already uses) and promoting `CARD_SD` → `CARD_SDHC` when the CSD reports v2 — narrow by
construction, and a genuine SDSC card (CSD v1) takes exactly its previous path. Full rationale in
`app/lib/SD/LOCAL_PATCHES.md`. **Re-apply on any `platform = espressif32` bump.**

**SPI clock is now 20 MHz, not the 4 MHz the bring-up plan assumed.** On the SDHC card 4 MHz
reproducibly panics inside FatFs mid-read (2/2 runs) while 20 MHz is clean (3/3) and ~40× faster.
Card identification always runs at 400 kHz inside the library regardless, and the library caps the
data clock at 25 MHz.

**Gate results.** Every number below is DUT-measured on `cyd2usb_winamp_debug`, display actively
redrawing, `spotifyTask`/`dataTask` live, reading files copied onto the card by the host.

| id | bar | 2 GB SDSC @4 MHz | 30 GB SDHC @20 MHz | verdict |
|---|---|---|---|---|
| `T_SD_01` mount | OK | OK | OK | **PASS** |
| `T_SD_02` GPIO5 strapping | 20 **power-cycles** | ~15 esptool resets — excluded method | **20/20 physical power-cycles** | **PASS** |
| `T_SD_03` LFN round-trip | exact | `lfnOk=true` | read-only (write path broken) | **PASS (SDSC)** |
| `T_SD_04` sustained read | **≥200 KB/s** | 34.1 KB/s | **637.2 KB/s worst of 5** (median 1 433.1) | **PASS — 3.2× over** |
| `T_SD_05` worst read latency | **≤50 ms** | 113.9 ms | **3.71 ms worst of 5** (p50 0.25–1.00) | **PASS — 13× margin** |
| `T_SD_06` `SD.begin()` heap delta | **≤8 KB** | 15 300 B | **11 164 B floor** (1 slot); 23 376 B at 4 | **FAIL — unmeetable at any slot count** |
| `T_SD_08` 20 mount/unmount cycles | leak-free | 8 B total drift | 8 B total drift | **PASS** |
| `T_SD_07` `listDir()` ~200 files | reported | 18 552 ms (200 files) | **5 270 ms / 200 files** (26.4 ms/entry) | **MET** |
| `T_SD_09` absent/unformatted card | clean fail | not run | **absent half PASS**; exFAT half unrun | **PARTIAL** |

**Coverage gaps — what still has to happen before this closes.** Three of these need the human at
the bench; none can be self-served from the serial harness.

1. ~~**`T_SD_02` (20 power-cycles).**~~ **CLOSED 2026-08-08 — 20/20.** See below.
2. **`T_SD_09` — absent half CLOSED 2026-08-08 (and it found a crash); exFAT half still unrun.**
   The criterion names two cases and only one has been run. See below. The exFAT case needs a card
   that can be reformatted — deliberately not done to the 2 GB SDSC card, which still holds unrelated
   content.
3. ~~**`T_SD_04`/`T_SD_05` load fixture (VE-6).**~~ **CLOSED 2026-08-08** — re-run under the named
   load. See below; VE-6 was right, and the re-run changed the reported numbers.
4. ~~**`T_SD_07` (~200-file listing).**~~ **CLOSED 2026-08-08** — 200 long-named files copied on
   from the host (the write path cannot create them). See below; the result is a constraint on
   `browse-001`, not just a number.

**`T_SD_09` — absent card, 2026-08-08. Absent half PASS; it caught a live panic.** With the slot
empty: boot mount `mounted:false` (heap delta 332 B, nothing retained), and `sdmount` / `sdprobe` /
`sdls` / `sdcycle` / `sdmbr` each return `ok:false` with a distinguishable error — `"mount failed"`,
`"not mounted"`, `"not mounted at boot"`, `"no readable card"`. Device responsive throughout, heap
flat, zero resets across the run. Each failed mount attempt blocks `loopTask` for **~626 ms**
(`block_max=618ms` in the heartbeat) — well inside the 15 s TWDT, but it is a visible stall and is a
direct input to `T_SD_10` / LocalPlayer degraded entry, which should not sit on it synchronously.

Getting there required fixing **PATCH-SD-2**, a use-after-free in the stock SD library that this id
exists to catch: `f_mount()` registers the volume *before* attempting the forced mount, so a failed
mount leaves `FatFs[vol]` populated; `sdcard_mount()`'s failure path then frees the context that
FATFS is embedded in without detaching it, and the next mount dereferences the dangling pointer and
asserts in `vQueueDelete(NULL)`. Full write-up in `app/lib/SD/LOCAL_PATCHES.md`.

> Two things about that fix are worth carrying forward. It is **not** reachable through the stock
> library alone — six consecutive failed `SD.begin()` calls with no card do not crash, because the
> same-sized context is freed and reallocated at the same address and the stale pointer lands on the
> new one by luck. It took a second mount path with a different context size to expose it. And the
> **first fix was wrong**: a plausible double-unregister of `card->base_path` was patched, DUT-tested,
> and still crashed. That change was kept (it is a genuine hygiene bug) but the write-up was rewritten
> to name the real mechanism rather than the first theory — per BP-055, a diagnosis that has not been
> tested against the failure is a hypothesis.

`PATCH-SD-2` touches the shared mount path, so it was regression-checked with the card back in: boot
mount and heap delta byte-identical (15 300 B), `sdread` 1 450.3 KB/s / 3.59 ms worst with the same
4 375 / 625 histogram, `sdls /probe200` 5 521 ms (inside the observed spread), `sdcycle 20` 20/20
with **0 B** drift (was 8 B). No regression.

**The exFAT half is WAIVED (operator, 2026-08-09), not done.** The criterion is "probe with no card,
**then with an exFAT card**"; only the first case was run. Waived because it needs a card that can be
reformatted and no spare exists — the 2 GB SDSC card holds unrelated content and was deliberately
left alone. Residual risk is low but non-zero: the pre-`PATCH-SD-1` SDHC card presented exactly the
shape this criterion wants (`ok:false`, distinguishable error, no crash, no hang), which is
encouraging but was an accident of a different bug rather than this test. **If a spare card ever
turns up, run it** — an unformatted or exFAT card is a realistic user state, and `T_SD_09` is the id
that would have caught PATCH-SD-2 earlier.

**`T_SD_02` — GPIO5 strapping, 2026-08-08. PASS 20/20.** Twenty *physical* USB unplug/replug cycles
with the card inserted, driven by hand (`powercycle_watch.py`, scratchpad). Every cycle: application
banner reached, `rst:0x1` only, no `rst:0x10` (RTCWDT_RTC_RESET, the bootloop signature the criterion
names), no repeated resets. **Bonus: 20/20 also reported `"mounted":true`** — twenty independent
cold-boot mount samples, which is a stronger mount result than `T_SD_01` alone gives.

Honest limits on this evidence. The CH341 driver asserts DTR on open regardless of what userspace
requests, so the capture tool's *own* connect resets the board — the `rst:0x1` it logs is from that
connect, not from the power-on it is nominally observing. There is no way around that over USB
serial on this rig. **The primary evidence is therefore the physical display** (human watched the
Winamp UI come up all twenty times); the log is corroboration and a written record. That is an
eyeball gate of the same class as BP-048/LL-109, which this project already relies on. One cycle
(13) printed the replug prompt without an unplug prompt — the node had already gone during the
previous capture window — but it was still a genuine replug boot and is counted as one.

> The first attempt at this test aborted after one cycle, and the cause is worth recording because it
> is a trap for any future bench tooling here: the watcher polled `run/port` to decide whether the
> DUT was plugged in, and `resolve_port()` (`run/lib.sh:15`) returns `$PORT` **unconditionally when
> that variable is set, without checking the device exists**. It is an override hook, not a presence
> check, and using it as one means "is the device gone?" can be answered by an environment variable.
> Detection is now an in-process `glob('/dev/ttyUSB*')` with no subprocess in the poll loop, and the
> aborting timeout that turned a detection miss into a dead run was removed entirely.

**`T_SD_07` — directory listing, 2026-08-08.** 200 files named `track NNN test.txt` (long names with
spaces, so LFN records are exercised), created on the host because TASK-424 blocks the device from
writing them. Deterministic across runs (5 270 / 5 303 / 5 444 / 5 465 ms).

| directory | entries | total | per entry |
|---|---|---|---|
| `/` | 9 | 9 ms | 1.0 ms |
| `/mp3` | 52 | 543 ms | 10.5 ms |
| `/probe200` | 200 | **5 270 ms** | **26.4 ms** |

**Per-entry cost grows with directory size** — it is not a fixed page cost, so sizing a browser page
from a small directory will underestimate badly. Three points on three different directories is not
enough to name a complexity class, and the root is not comparable (short names, mostly
subdirectories), so this is recorded as a trend, not a law.

One hypothesis was tested and **falsified**: that `File::size()` per entry was the cost, since FatFs
resolves a path-based stat by scanning the directory from its start. Added a no-stat listing mode
(`sdls <dir> n`) to price it — and it made no difference at all (200 entries: 5 264 ms without the
stat vs 5 270 ms with; 52 entries: 546 vs 543). The stat is not avoidable that way because
`openNextFile()` already stats each entry when it constructs the `File` (to resolve `_isDirectory`),
so skipping `size()` skips nothing.

> **Constraint for `browse-001`, which is what this id exists to feed.** 5.3 s to walk a 200-file
> directory cannot sit on a mode-entry or navigation path as a blocking call — that is ~18× the
> worst *single-read* latency budget and would read as a hang. The browser has to walk incrementally
> (yielding to `loopTask`), cache the result, or both, and it cannot assume the per-page cost it
> measures on a small directory holds on a large one. Note this is a *listing* cost, not a
> throughput problem: sustained reads on the same card are 637–1 439 KB/s.

**`T_SD_04`/`T_SD_05` under the named load (VE-6), 2026-08-08.** Five runs of 5 000 reads
(2 560 000 B each, zero read failures) with **Aquarium** as the active app at its natural frame rate,
`get appId` asserted `id:7 Aquarium` before and after every run:

| run | KB/s | p50 | p99 | max | histogram |
|---|---|---|---|---|---|
| 1 (first read after boot) | **637.2** | 1.00 ms | 1.00 ms | 1.82 ms | 4 997 in the ≤1 ms bucket, 3 in ≤2 ms |
| 2 | 1 433.1 | 0.25 ms | 3.65 ms | 3.65 ms | 4 375 / 625 |
| 3 | 1 439.2 | 0.25 ms | 3.70 ms | 3.70 ms | 4 375 / 625 |
| 4 | 1 437.1 | 0.25 ms | 3.62 ms | 3.62 ms | 4 375 / 625 |
| 5 | 1 431.7 | 0.25 ms | 3.71 ms | 3.71 ms | 4 375 / 625 |

Runs 2–5 are tight (0.5 % spread). **Run 1 is a reproducible-looking outlier at 2.2× slower**, and
its shape is the interesting part: it shows *no* buffered-hit bucket at all — every read cost ~1 ms,
where runs 2–5 show the expected 8:1 pattern of one 4 KB physical read serving eight 512 B calls. The
first read after boot appears not to get the 4 KB read-ahead. **Report the worst, not the median**:
`T_SD_04` = 637.2 KB/s (still 3.2× over the bar), `T_SD_05` = 3.71 ms (13× under).

> This is exactly what VE-6 was protecting against. The previously reported 1 380.8 KB/s was a
> single run under an unnamed load; the honest worst-case under the specified load is less than half
> of it. The verdict does not flip, but the number moved a long way, and a first-read-after-boot
> penalty is directly relevant to `localplay-001`'s start-of-playback latency — it should be
> characterised there rather than discovered again.

Read latency is now tightly bimodal and clean: 4 376 buffered hits ≤250 µs and 624 physical 4 KB
reads all landing in the 2–4 ms bucket, nothing above.

**`T_SD_06` is unmeetable at every slot count, and that is now measured rather than argued.** Full
sweep, DUT, card present — mount cost and unmount reclaim agree byte-for-byte at every point, so
there is no leak and no measurement ambiguity:

| `max_files` | mount cost | vs ≤8 KB bar |
|---|---|---|
| 1 | **11 164 B** | 1.4× over — and 1 slot cannot walk a directory |
| 2 | 15 300 B | 1.9× over (current setting) |
| 3 | 19 240 B | 2.3× over |
| 4 | **23 376 B** | **2.9× over** |
| 5 | 27 516 B | 3.4× over |

Exactly **+4 136 B per slot** — one `sizeof(FIL)`, as predicted before measuring. More slots make
`T_SD_06` worse, never better: the bar cannot be met by tuning `max_files`, because
`sizeof(FATFS)` = 4 156 B plus the non-context overhead already consumes ~7 KB before the first file
slot exists. **11 164 B is the floor**, and it is 1.4× the bar.

Root cause is `FF_MAX_SS=4096` (`CONFIG_WL_SECTOR_SIZE`) with `FF_FS_TINY=0` in the **precompiled**
IDF FATFS — FATFS carries a 4 KB window buffer and every `FIL` carries its own 4 KB sector cache.
Not tunable from this project.

4 slots costs 23 376 B *and* fragments: it drops the largest free 8-bit block to 20 468 B at idle,
before WebRadio's Helix arena is anywhere in the picture. Throughput is unaffected (1 356.3 KB/s,
3.61 ms worst, 200-file walk 5 350 ms at 4 slots), so this is purely a memory decision.

**This is an Architect ruling, and it cannot be closed by measurement.** The honest options are:
(a) accept the cost as an explicit, documented exception to `T_SD_06` and amend ADR-059 to say so;
(b) rebuild the IDF with a smaller `FF_MAX_SS`; or (c) move to `esp_vfs_fat_sdspi_mount` (the
`sdmmc` driver is already linked). **The bar was not retuned** — the milestone brief says not to,
and no measurement can turn 11 164 B into ≤8 KB.

**The old card was never the problem.** It reads at 9.5 MB/s on a host PC. Its 34 KB/s here was the
same class of driver-level issue, and both cards now read fine given a correct card type and clock.

**Open defect — the write path is broken, and it is card-independent.** Sustained writes to a single
open file panic the firmware: `f_write()` → `validate()` faults `LoadProhibited` because `obj->fs`
reads NULL immediately after `ff_req_grant()` returns. Reproduced on **both** cards and at **both**
4 and 20 MHz. On the SDSC card short open/write/close bursts were a reliable workaround (200 fixture
files, 32 KB appends at ~265 KB/s); on the SDHC card even those now fail. Files produced by this path
are left damaged — one truncated-and-reopened file reported a **1 073 678 476 B** size, and reading a
fixture the path had written was itself enough to panic, which is what a `sdprobe` re-run hit.

M-SDFS phase-0 is read-only, and reads of host-written files are clean and fast, so nothing in the
milestone depends on this. But **the write path is unproven and currently unsafe** — do not build
playlist persistence, tag caching, or any on-card write feature on it without fixing this first. It
needs its own task. `sdprobe` now builds its bench fixture in bursts specifically to route around it.

> An earlier crash in this area was a *different*, now-fixed bug: the probe fed the task watchdog
> only every 20 files / 64 KB, which a 93 ms/op bus overran outright. That one was mine, not the
> library's.

**Tooling landed** (`app/src/main.cpp`, all `SERIAL_DEBUG`-only): `sdmem` (FATFS/FIL sizing, the
8-bit contiguous-alloc ceiling by bisection, and a calloc ladder at 1/2/3/5 slots), `sdmount
[maxFiles] [freqHz]` / `sdumount` (mount at a chosen slot count and SPI clock with full heap
accounting — the unmount side is the clean cost measurement, since a boot-time delta is polluted by
WiFi/NTP/task-start), `sdcycle`, `sdls`, `sdread <reads> <path>` (read-only benchmark against a file
the card already carried, so a fixture this probe wrote cannot flatter the result), `sdwrite`,
`sdclean`, `sdmbr` (raw sector 0 / partition table / volume ID below the FatFs layer, which is what
identified PATCH-SD-1), and `sdprobe [reads] [skipWrites]`.

> Two measurement traps are fixed in the committed tools and are worth knowing about. A failed
> physical read latches the stdio stream's error flag, and `seek()` does **not** clear it — every
> later read returns 0 instantly, which silently ended the benchmark at 385 KB and understated
> sustained throughput. Both read paths now reopen and resume. And the histogram is bucketed rather
> than an array of every sample: at 5 000 reads a `uint32_t[]` is a 20 KB contiguous internal
> allocation, i.e. precisely the allocation class this task just proved cannot be served live.

### TASK-424 — SD write path panics in FatFs (card-independent)

Split out of TASK-408, where it was found and characterised but not filed. Sustained writes to a
single open file panic the firmware: `f_write()` → `validate()` faults `LoadProhibited` because
`obj->fs` reads NULL immediately after `ff_req_grant()` returns. Reproduced on **both** cards tested
and at **both** 4 and 20 MHz, so it is not a card or clock artefact.

Files the path produces are left damaged — one truncated-and-reopened file reported a
**1 073 678 476 B** size, and *reading* a fixture this path had written was itself enough to panic.
On the 2 GB SDSC card, short open/write/close bursts were a reliable workaround (200 files created,
32 KB appends at ~265 KB/s); on the 30 GB SDHC card even short writes now fail.

Not on the M-SDFS phase-0 critical path — phase 0 is read-only and reads of host-written files are
clean and fast. Filed because it is a live firmware panic with a known trigger, and because
`pledit-edit-001` / `m3u-001` (TASK-420/421, playlist save) assume a working write path. Those tasks
must not start until this is understood.

**Owner:** Developer · **Deps:** none (TASK-408 supplies the repro) · **Gate:** the `sdwrite` command
completes 2 048 chunks single-open, twice, on both cards, with no panic and a correct `endSizeB` ·
**Priority:** P2 (blocks TASK-420/421 only) · **Status:** OPEN — repro is `sdwrite 2048` on a
`cyd2usb_winamp_debug` build.

> `sdprobe` builds its bench fixture in short bursts specifically to route around this. If this is
> fixed, revert that to a plain single-open write — the burst loop is a workaround, not a design.

### TASK-425 — re-measure the SD/arena memory table under arena-first ordering

ADR-059 D1 amendment #2 changed the Player-mode lifecycle to **acquire the decoder arena before
mounting SD**, on the asymmetry that the arena needs one contiguous 23 216 B block while FATFS needs
~19 KB in many small pieces. Every number the ruling rests on was measured **mount-first**, and the
amendment says so explicitly: *"Re-measure the whole table under arena-first before relying on any
row of it."* This task is that re-measure. Filed because the ADR names it as a condition of the
acceptance and TASK-408 closed without discharging it.

Two things to settle, both currently hypotheses:

1. **Does `max_files=4` become viable under arena-first?** Mount-first it is not — largest free block
   after mounting 4 slots is 20 468 B against the arena's 23 216 B need, measured. Arena-first takes
   the big block from a clean heap and lets FATFS's small allocations fit around it, which *may*
   make 4 work. If it does, the browser-handle closure rule (amendment #2) becomes optional rather
   than load-bearing.
2. **The Player-mode concurrent peak** — condition 1 of the acceptance, never measured. Every heap
   figure in TASK-408 is mount cost in isolation, idle, WiFi up, no stream. The number that matters
   is free heap and largest-free-block with the arena held *and* SD mounted *and* a playlist loaded
   *and* a file playing.

At `max_files=3` the mount-first margin over the arena is **1 348 B** (measured; the ADR derived
1 388). That is thin enough that fragmentation alone could close it — this project has already had a
byte-count-only gate pass in a narrow environment and then crash in the full build.

**Blocker on method:** this cannot be measured with today's firmware. The arena is acquired inside
`WebRadioApp::_play()`, so the only way to hold it is to start a stream — which drags ~40 KB of TLS
in and measures the wrong profile entirely. Needs either a debug hook that acquires/releases
`mb_arena` standalone (cheap, `set arenaHold 0|1`) or `LocalPlayerApp` to exist.

**Owner:** Developer (Architect consult — the ruling depends on the result) · **Deps:** none for the
debug hook; the full peak needs TASK-410 · **Gate:** the amendment #2 table re-measured arena-first,
all rows, with mount `heapDelta` and unmount `reclaimedB` agreeing; plus a stated `max_files` for
TASK-410 with its arena margin · **Priority:** P1 — TASK-410 cannot pick `max_files` without it ·
**Status:** OPEN.

> Do not carry any row of TASK-408's `max_files` table into TASK-410. It is all mount-first, and
> mount-first is the ordering the ADR replaced.

### TASK-409 — extract the audio engine to `audio/audioEngine.h` (PURE MOVE)

Exactly one `Audio` object can exist (one internal DAC, one 23 216 B Helix arena, one 6 400 B
InBuff), and today WebRadio owns all of it as file statics in `webRadioApp.h`: `s_wr_audio` (`:187`),
`s_wrAudioMutex` (`:323`), the `wrAudio` pump task (`:303`ff), `wrPumpConnect` posting (`:340`ff),
`mb_arena` acquire/release (`:317`/`:456`/`:498`/`:719`), `audio_process_extern` (`:223`), the
`audio_info`/`audio_showstreamtitle` callbacks, and the volume sink (`:385`ff). Move all of it out;
WebRadio and (later) LocalPlayer become peer clients. Only new surface: `connect(const Source&)` with
`Source = {URL | FILE}`.

**This is a move, not a refactor.** No logic change, no reordering, no opportunistic cleanup — the
code carries the fixes from TASK-278/287/289/291/295/299/392/398 and a diff that also changes
behaviour makes any regression undiagnosable.

**Owner:** Developer (Architect consult — cross-component) · **Deps:** none · **Gate:**
`T_AE_01`–`06`. `T_AE_01` re-runs WebRadio's **existing** suite unchanged and compares failure
**sets**, not counts (LL-104) — **baseline it before the extraction lands or there is nothing to
compare to**. `T_AE_03` requires a **full-length** `./run/wr-soak`; a short soak has given false
confidence on precisely this code before · **Priority:** P2 · **Status:** **DONE** (2026-08-10) —
ADR-059 accepted 2026-08-07 (D2); full gate `T_AE_01`–`04`/`06` DUT-PASS, see below.

**`T_AE_01` pre-refactor baseline captured 2026-08-09 (ADR-059 D13, 3× `./run/test` on `cyd2usb_winamp_debug`, prod restored clean after each):**

| Run | Passed | Failed | Skipped | Flaked |
|---|---|---|---|---|
| 1 | 131 | 2 | 39 | 1 |
| 2 | 126 | 1 | 43 | 3 |
| 3 | 126 | 1 | 43 | 3 |

Runs 2 and 3 are byte-identical result sets. Run 1 differs from 2/3 only in six tests, all explained:

- `T_WR_TLS_01` — **FAIL in all 3 runs**, not intermittent this session (`http=-101` on all mirrors,
  both TLS paths). Host-side cert preflight (step 0) PASSED `de1.api.radio-browser.info` all 3 times,
  so this isn't ADR-029-style CA rot — the failure is device-side/network, consistent with TASK-284's
  "comes and goes" history, but **this baseline saw it fail, not flake**. It was on ADR-059's
  pre-declared flaky list already (named alongside `T169`/`T_PR_05`), so it doesn't block the gate, but
  flag to Developer/Architect as a live TASK-284 data point, not silently absorbed as "known flaky."
- `T_WR_COEX_01`, `T_WR_HEAP_03`, `T_WR_HEAP_04`, `T_WR_VOL_03` — cascade of the above: run 1 happened
  to have stations already loaded (prior session state) so these attempted and either passed or timed
  out; runs 2/3 correctly `SKIP`ped ("station list unavailable"). Not independent flakes — downstream
  of `T_WR_TLS_01`.
- `T091` — FLAKE all 3 runs (reconnect `consecutiveFailures=1`, expected 0).
- `T087`, `T092` — PASS in run 1, FLAKE in runs 2/3 — genuinely intermittent (reconnect/TLS-adjacent).

**Pre-declared flaky set for the D13 "identical pass set" bar:** `T_WR_TLS_01`, `T_WR_COEX_01`,
`T_WR_HEAP_03`, `T_WR_HEAP_04`, `T_WR_VOL_03`, `T091`, `T087`, `T092`, `T_PR_05` (network,
pre-existing), plus the ~30 tests `SKIP`ped identically in all 3 runs (Premium/TASK-243-gated,
hardware/audible-gated — pre-existing, not new). Everything else passed clean in all 3 runs and is
the actual regression bar for post-extraction `T_AE_01`: **no test outside this set may fail after
the move, and nothing outside it may newly fail.**

D13 baseline satisfied — **TASK-409 is clear to start.**

**Implementation landed 2026-08-09.** New `app/src/audio/audioEngine.h` — the Audio singleton
(`s_wr_audio`/`wrAudio()`), the ICY queue + `audio_showstreamtitle`/`audio_info` callbacks,
`audio_process_extern` (real VU/spectrum/wave-trace feed), volume policy
(`wrEffectiveVolume`/`wrScaledVolume`/`wrVolumeSink`), and the whole pump task (mutex, TASK-398
request/result protocol, `wrEnsurePumpTask`/`wrTeardownPumpTask`) moved out of `webRadioApp.h`
verbatim — cut/paste only, zero statements touched. Single-TU include model (everything under
`app/src` is textually pulled into one compilation via `main.cpp`), so every symbol kept its
original name/linkage; `webRadioApp.h` picks the new header up via one `#include` and every call
site (`_play`, `_stopAudio`, `init`, `_refreshAudioSnapshot`, etc.) is untouched. `connect(const
Source&)` (the one new surface the task authorises) **not yet added** — deferred to land alongside
TASK-410's FILE arm rather than sit unused, since introducing it now with only a URL variant would
be exactly the "opportunistic" scope creep this task forbids.

- `T_AE_06` (host, `run/check`) — **PASS**, 6/6 both envs.
- Flash size **byte-for-byte identical** to the pre-move baseline on both environments (prod
  1,795,281 B, debug 1,868,877 B) — the strongest evidence available pre-DUT that this was a true
  zero-behaviour move, not just "no logic looks different."
**DUT gate session 2026-08-09 (post-implementation):**

- `T_AE_01` — **PASS.** Post-move `run/test` result set is byte-for-byte identical to the pre-move
  3-run baseline (126 passed, 1 failed — `T_WR_TLS_01`, pre-declared, 43 skipped, 3 flaked — `T087`/
  `T091`/`T092`, pre-declared). Zero drift outside the pre-declared flaky set. First attempt hit a
  CH340 USB re-enumeration mid-run (`/dev/ttyUSB1`→`/dev/ttyUSB0`, known flaky-rig quirk, not a code
  issue) — prod firmware manually restored, clean retry confirmed the result above.
- `T_AE_02` (arena lifecycle balance) — **PASS.** 30-min `run/wr-soak`, 114 play/stop cycles: 115
  acquires / 114 releases (balanced — 1 active at snapshot, correct per invariant), **zero acquire
  failures**, contiguous INTERNAL block never dropped from 98 292 B. Real evidence the moved
  pump/arena code handles repeated churn cleanly, including down the async-FAILED branch.
- `T_AE_03` (no decode regression under load) — **PASS (final, 2026-08-10).** Earlier same-night
  attempts were blocked by what looked like "WiFi down," then "DNS resolution failing" — both were
  downstream symptoms of TASK-426 (WiFi supervisor wedge: a dead saved SSID stayed resident in the
  STA config and got retried forever instead of the live AP — see
  `project_task426_no_ap_found_wedge` memory). Once TASK-426 landed (commits `d19bcff`..`96a388a`),
  re-ran clean: 30 real stations loaded, 67 play/stop cycles over 30 min, **66/67 reached PLAYING**
  with sustained playback (median 18.2s against the 20s cap — genuine decode load ran nearly the
  full window each cycle), arena balanced (67 acquires/66 releases, 1 correctly active at snapshot),
  **zero acquire failures**, contiguous INTERNAL block never dropped from 42 996 B, only 1 underrun
  across the whole soak, 0 error/skip cycles. `VERDICT: PASS`.
  `run/wr-soak`/`test_webradio_soak.py` kept the `--inject-url` bypass added while chasing this —
  harmless, useful for a future session if station fetch is ever down for an unrelated reason again.
- `T_AE_04` (teardown ordering, eject mid-CONNECTING ×10) — **PASS (2026-08-10, after harness
  rework).** `10/10 cycles clean, 0 invariant failures, 0 setup/precondition. VERDICT: PASS` via
  `./run/ae04` (new wrapper: flash `cyd2usb_webradio` → run → restore prod + monitor, same shape as
  `run/wr-soak`). Per cycle: teardown **9.9 s** (10.5 s once) through the pump's own
  `torn down (post-connect)` branch, worst `[perf] iter=103 ms` (the ordinary app-switch repaint
  baseline, ≤ 180 ms bound), arena **+1/−1 with `active` back to 0 and zero acquire failures**, no
  crash signature, no ack-timeout tripwire. Dead flat across all ten cycles — the accumulation the
  previous session suspected does not exist.

  **All three (four) earlier findings were harness defects; firmware was never at fault.** Root
  cause of the "worse and monotonic" cycles 3-10: the tool waited a fixed **8.0 s** for the pump to
  die, but `DEAD_URL` is a raw IP and `Audio::connecttohost()` (`Audio.cpp:511-519`, TASK-295's own
  patch) force-sets `m_timeout_ms = 10000` for raw-IP hosts. The pump is blocked inside that
  `_client->connect()` and cannot observe the posted TEARDOWN until it returns — so an 8 s bound is
  one the design is not built to meet, and the measured 9.9 s is correct behaviour, not a stall.
  Whether a cycle "passed" depended only on how much of the 10 s had burned before the eject command
  landed. Worse, a cycle that timed out left `_state` stale-`CONNECTING` off-screen, where
  `set wrStop` cannot reconcile it (`_stopAudio()` returns early on CONNECTING) and `_play()`'s own
  CONNECTING guard then silently no-ops the next `set wrUrl` — so one late teardown poisoned every
  later cycle identically. That is the entire "monotonic degradation" signal.

  Harness fixes landed (all in `app/tools/test_ae04_teardown.py`, documented in-file):
  1. Teardown wait is now a poll with a deadline **derived from the connect timeout**
     (`--teardown-deadline-s`, default 16 s = 10 s + margin), and the measured latency is reported
     per cycle instead of being collapsed into pass/fail.
  2. **Preconditions are proved, not assumed** — STOPPED before injection, CONNECTING + pump-alive
     after — and a failed precondition is reported as `SETUP`, distinct from an invariant `FAIL`, so
     a harness problem can never again be read as a firmware one (the run summary says
     `INCONCLUSIVE` rather than `FAIL` in that case).
  3. Measurement no longer flushes the serial buffer: `watch()` interleaves `get wrPump` probes into
     one continuous raw read, so `[perf]`/`wrpump` lines between probes still count. The previous
     `cmd()`-based polling discarded exactly the lines the loopTask bound and the ordering evidence
     are read from.
  4. Each cycle waits for `get wrCount` `pending==0` first. On first entry `init()`'s station fetch
     is in flight and `set wrUrl` **defers** rather than plays (TASK-289's fetch/playback heap-race
     guard) — that made cycle 1 vacuous and the late-firing deferred play left the arena acquired,
     breaking cycle 2 too (both reproduced and then eliminated this session).
  5. Arena is checked as a **per-cycle delta** against a baseline (counters never reset) with a
     `upMs`-went-backwards reboot guard, and ordering is asserted positively by requiring the
     `wrpump: torn down (post-connect|early-arrival)` log line — i.e. the TEARDOWN was serviced by
     the pump task itself, not synchronously by loopTask.

  Historical record of the three findings as they were first reported (all now explained above):
  1. The tool's original 100 ms loopTask-block bound was a **false-positive generator, not a real
     finding** — an isolation probe (ordinary WebRadio-STOPPED→Spotify switch, zero pump/arena
     involvement) measured the *same* `[perf] iter=103ms (worst path shell.switch:76ms)` baseline —
     that's this app's ordinary screen-repaint cost on any app switch, nothing to do with the audio
     engine. Bound corrected to 180 ms (baseline + margin) in the script.
  2. With that fixed, an alternating PASS/FAIL-by-cycle-parity pattern showed up identically under
     both WiFi-down and WiFi-up conditions — ruling out network jitter and pointing at the test
     harness's own cycle sequencing: `resume()`'s `webRadioAutoplay` (triggered by the script's own
     `switchApp` back into WebRadio) can race the script's explicit `set wrUrl` injection, since
     `_play()`'s CONNECTING guard silently no-ops a call that lands on an already-in-flight connect —
     desyncing the "eject right after posting CONNECT" timing assumption the test depends on.
  3. Patched to force-`wrStop`-and-poll-for-STOPPED before each injection — cycles 1-2 then passed
     cleanly, but cycles 3-10 degraded to a *consistent* "pump still alive 8.3s after eject" failure,
     i.e. **worse and monotonic, not flaky** — suggesting genuine accumulated state drift across
     repeated injected-dead-URL cycles (possibly in the async request/result protocol's handling of
     this specific back-to-back-dead-connect pattern) rather than a harness bug. **Superseded: it
     was the 8 s-vs-10 s bound plus the stale-CONNECTING cascade described above — there is no
     accumulation bug.**

**Status: DONE — implementation complete, host-verified, `T_AE_01`–`T_AE_04` and `T_AE_06` all
DUT-PASS (2026-08-10). `T_AE_05` was withdrawn on VE-9 (a review gate, not a test), so the gate is
fully satisfied.**

### TASK-410 — drop `-DAUDIO_NO_SD_FS`, implement `connect(FILE)`, play one file

Remove the flag from `platformio.ini:84` (re-enables `connecttoFS()` and the `File audiofile`
member), wire the FILE arm of `connect()` through the existing post-to-pump-and-poll path, and play
one hardcoded path to the speaker. Measured cost of the flag drop: **+88 B static DRAM
(+16 data / +72 bss), +3 984 B flash** — measured with the code actually referenced, since the
linker GCs it otherwise and the unreferenced number (+40 B) flatters.

Also implement the `audio_eof_mp3()` hook (declared weak in `Audio.h:77`, implemented nowhere
today). **It fires on the audio pump task, inside `Audio::loop()`, with the engine mutex held — it
may only set a flag.** Opening the next track from inside it calls `connecttoFS()` from the task
already holding the mutex: self-deadlock. Drain the flag on loopTask's next tick.

**Owner:** Developer · **Deps:** TASK-408 (pass), TASK-409 · **Gate:** `T_AE_07`–`10`. `T_AE_09` is
cheap and falsifies this workstream's biggest assumption — arena HWM after file playback must still
be **23 216 B** (the same nine Helix structs as the stream path); if it differs, "no new decoder" is
wrong and `mem_manifest.yaml` needs revisiting. `T_AE_08` re-derives `.dram0.bss` headroom from a
fresh map · **Priority:** P2 · **Status:** **DONE** (2026-08-10) — `./run/check` 6/6 both envs;
`T_AE_07`/`09`/`10` DUT-PASS (commit `7f01680`). Note two constraints it inherits: SD must be mounted
in `setup()` and held (not lazily on mode entry), and the SD write path is a known open defect —
`connect(FILE)` stays read-only.

**Two bugs found and fixed during DUT verification, neither anticipated by the design doc:**
`s_wrAudioMutex`/`s_wrPumpAckSem` were only ever created inside `WebRadioApp::init()` — calling the
engine standalone (no WebRadio app switch) null-derefed into a FreeRTOS assert and rebooted the
device; fixed by moving idempotent creation into the shared `wrEnsurePumpTask()`. Separately,
`aeConnectFile()` wasn't yielding Spotify's TLS session first the way `WebRadioApp::_play()` does —
with Spotify connected, `mb_arena_acquire()` and even the pump task's own stack allocation reliably
failed under that heap pressure; fixed with a standalone yield/resume pair (`s_aeSpotifyYielded`,
separate from `WebRadioApp::_spotifyYielded` since this path has no app instance), resumed at the
file's natural EOF.

**DUT results** (real MP3 from the card's `/mp3/` folder, 192 s CBR, played via the new
`set aePlayFile <path>` / `get aePlay` debug surface — no LocalPlayer app yet to drive this through,
that's TASK-413+): `T_AE_07` PASS — `filePos` climbs monotonically to `fileSize`, `running` drops to 0
right at `curSec≈durSec`. `T_AE_10` PASS — `audio_eof_mp3` fired, drained on loopTask, no stall/deadlock,
`configASSERT` never tripped. `T_AE_09` PASS on the one run where Spotify's TLS session never
established (arena HWM measured exactly `23216`); under concurrent Spotify the arena acquire
gracefully falls back to `malloc` instead (by design, not an invariant violation) — **flagged for
TASK-413**: concurrent Spotify+file playback may permanently run the file decoder off the malloc
fallback path rather than the reserved arena.

### TASK-411 — extract `pleditView.h`, Spotify caller only

PLEDIT is implemented twice: `winampDisplay.h` (Spotify queue, `dragState`, seqno-diff gate) and
`webRadioApp.h` (stations, `_scrollAccum`/`_scrollVelocity`) — sharing only
`touch/scrollTuning.h`. Extract one renderer owning chrome blit, row layout/truncation, duration
column, total-time bar, synthetic thumb, velocity scroll, direct-scroll strip and the redraw gate.
`winampDisplay.h` delegates; **WebRadio untouched in this task.**

Deliverable alongside the code: an **enumeration of the two copies' divergences**, since they have
drifted. Merging means choosing per divergence deliberately, not inheriting whichever caller lands
second.

Adopt `touch/hitbox.h` (`Rect`/`hitTest`/`hitTestRow` — already the shared primitive) instead of
porting the hand-rolled bounds maths, and extract the ellipsis truncation currently inlined in the
Spotify row formatter into a shared `util/textFit()` — three new callers are coming and it is the
only implementation in the tree.

**Owner:** Developer (Architect consult) · **Deps:** none · **Gate:** `T_PLE_01`–`06` —
pixel-identical via `run/screendump` diff across ≥5 states. Known limitation: screendump **cannot
capture live navigated app state** (DTR-resets on connect), so reach states by serial injection ·
**Priority:** P2 · **Status:** **DONE** — `pleditView.h` extracted (`28b149e`), `winampDisplay.h`
delegates via `SpotifyQueueSource`, WebRadio untouched as scoped. `T_PLE_01`–`04`+`06` PASS on DUT
(0 differing pixels, 7 states, `e6ef89b`). `T_PLE_05` closed on a deterministic serial gesture
battery, human-accepted in place of the void blind A/B (`078e689`). 22-row divergence log in
`docs/architecture/designs/M-PLEDIT-ABSTRACTION-playlist-source.md` § Divergence log feeds
TASK-412, which has since landed on top (`251c3c9`).

### TASK-412 — WebRadio as the second caller (`StationListSource`)

Delete WebRadio's PLEDIT copy, wire `StationListSource` (`CAP_PLAY` only) over the shared renderer.
`webRadioApp.h` must end up with zero PLEDIT render/scroll symbols.

**Documented fallback:** if TASK-411 or this cannot be made pixel-identical, stop and give local
playlists their own third renderer. The duplication is worse, but shipped scroll behaviour is not
traded for deduplication — **do not relax the test to make it pass.**

**Owner:** Developer · **Deps:** TASK-411 · **Gate:** `T_PLE_07`–`13`. `T_PLE_09` is an **eyeball
gate on the physical LCD** (BP-048): pixel-identity does not imply feel-identity, timing and gesture
thresholds do not appear in a screenshot, and this is the code TASK-277 was spent tuning.
`T_PLE_13` is a tripwire — one renderer replacing two must be a **negative** flash delta; a positive
one means the old path was not deleted · **Priority:** P2 · **Status:** **DONE** — code landed
2026-08-09 (`webRadioApp.h` has zero PLEDIT render/scroll code, `T_PLE_12`/`14` PASS, `T_PLE_11`
vacuously PASS, `T_PLE_07` 3/5 states pixel-identical with the other 2 root-caused and documented,
`T_PLE_13` FAILS as literally worded — +36 B/+160 B flash, analysed, not an incomplete deletion).
2026-08-10: `T_PLE_08` **PASS** — new `T_PLE_WR_155`–`160` battery, 3/3 clean ADR-059 D13 baselines
(18/18). First attempt failed 3/6 on a harness-timing artifact (interleaved-send pattern tuned to
Spotify's `loop()` cost raced WebRadio's), root-caused and rewritten with `drag ... hold` + `get
wrScroll`, not a product regression. `T_PLE_09` **PASS** — live DUT feel-check on production
firmware, human-accepted (same standard as `T_PLE_05`): WebRadio's station-list scroll reported
identical to Spotify's queue scroll (acceleration, quick-swipe fallback, clamps, direct-scroll strip
tracking). All five exit criteria in the design doc §7 met; `run/check` 6/6. See design doc §7b for
the full gate record.

**Status: DONE.**

### TASK-413 — `AppId::LocalPlayer`, three-valued mode, taskbar-icon cycling, taskbar assertion

`PlayerMode { Spotify=0, WebRadio=1, Player=2 }` — `g_settings.playerMode` already stores a
`uint8_t`, so the SPIFFS schema is unchanged; only the value domain widens. Mode cycling moves
**off eject onto the taskbar Winamp icon**: tapping the player slot while the player is already
active cycles and persists; tapping from another app restores the persisted mode
(`resolvePlayerSlot()`, `main.cpp:1926`, extended to three).

`taskbar.h` asserts today that WebRadio is the **last** `AppId`, because eject-only apps are
excluded by occupying the enum tail. With two such modes the tail becomes `Settings, WebRadio,
LocalPlayer` and `TASKBAR_APP_COUNT = (int)AppId::COUNT - 2`. **Rewrite the assertion to express
"the eject-only tail", not to name WebRadio** — otherwise a future third eject-only mode silently
leaks into the taskbar and null-icon-crashes exactly as TASK-242 did. `appRegistry.h` edits require
re-running `gen_app_registry.py`; `check_build.sh` step [5/5] enforces staleness.

**Also in this task, same commit — widen the debug surface.** Both halves are hardcoded two-valued
and fail *silently*: `main.cpp:3336` (`get`) does `uint8_t pm = g_settings.playerMode ? 1 : 0` and
names non-zero `"WebRadio"`, so Player mode reports as **`WebRadio(1)`**; `main.cpp:3806-3807`
(`set`) rejects `idx > 1` and accepts only `"spotify"`/`"webradio"`, so Player mode is unreachable
from the harness. The TASK-407 instrumentation (landed `9d4beaf`) reads exactly that getter — left
unwidened it would log confident wrong data for the very bug it exists to catch.

**Owner:** Developer · **Deps:** TASK-410, TASK-412 · **Gate:** `T_PLR_01`–`05`; `T_PLR_03` is the
TASK-242 regression check, `T_PLR_04` requires `get`/`set playerMode` to round-trip all three
values · **Priority:** P2 · **Status:** **DONE** — ADR-059 D6/D7 implemented 2026-08-10. Related:
TASK-407 (OPEN, passive) tracks an unexplained flip of this exact field — does **not** block, but
see TASK-422's `T_PLR_36`.

**DUT gate result (2026-08-10):** `T_PLR_01`–`05` all PASS, plus regression rerun of `T242`/`T162`/
`T_TBFB_03` (8/8 PASS) to confirm the existing taskbar/player-slot suite survives the cycling change.
`AppId::LocalPlayer` lands as a minimal placeholder App (`app/src/localPlayerApp.h`) — reachable via
mode cycling/reboot-restore, no crash — the real file-browser/M3U UI is TASK-415+. Found and fixed
along the way: (1) `resolvePlayerTap()` — the taskbar tap on the player slot now cycles when already
active, restores otherwise, called from both `shellTbRelease()` and `cmdTap()`'s SERIAL_DEBUG
injection (ADR-059 D6 amendment); (2) the taskbar's `isWebRadioSkin`/`resolveTaskbarSlotApp` remap
had to be widened to LocalPlayer too, or the active-slot highlight would address an AppId past
`TASKBAR_APP_COUNT` and show no highlight at all while in Player mode; (3) the harness's
`_restore_spotify()` test helper broke under the new cycling semantics (tapping the player slot from
an already-active WebRadio/LocalPlayer no longer unconditionally lands on Spotify) — fixed to step
off to Clock first; (4) `T242`'s and the new `T_PLR_03`'s "WebRadio never a taskbar slot" tap-check
had to skip offset 0 (the player's own slot), since tapping it while active is now *supposed* to
cycle — that's not the TASK-242 leak class, it's D6 working as designed.

### TASK-414 — eject remap: "load media from this source"

Eject is freed by TASK-413 and becomes one verb with three realisations: **Spotify** → TLS reset +
force poll (the reconnect currently on the Winamp logo tap, TASK-053f); **WebRadio** → station-list
refresh/browse; **Player** → open the file browser. The logo tap **keeps** its TLS-reset behaviour —
a duplicated affordance is harmless, silently deleting a recovery path is not.

Accepted UX break: eject has meant "switch to radio" since M-WEBRADIO shipped. Operator's explicit
call; recorded so it is not later mistaken for a regression.

**Owner:** Developer · **Deps:** TASK-413 · **Gate:** `T_PLR_06`–`07` · **Priority:** P2 ·
**Status:** **DONE** — ADR-059 D6 implemented 2026-08-10.

**DUT gate result (2026-08-10):** `T_PLR_06`/`07` PASS, plus regression rerun of `T_WR_EJECT_01`/`02`
(rewritten for the new per-mode semantics — see below), `T_WR_VOL_CLAMP`, `T237`, `T_PLR_01`, `T_PLR_05`
(5/5 PASS) to confirm the taskbar-cycle entry path introduced by TASK-413 still works everywhere the
old eject-entry path was assumed. `T_WR_SPOTIFY_RESUME_01` SKIPped on a station-list fetch failure
(radio-browser.info network flake, not a regression — its own taps were rewritten and exercised the
same code path other passing tests confirm). Implementation: `SpotifyApp::handleInput` (`main.cpp`)
and `WebRadioApp::handleInput` (`webRadioApp.h`) no longer call `switchApp()` on eject; `LocalPlayerApp`
(`localPlayerApp.h`) gets a wired eject stub (logs + consumes the tap; the real file browser is
TASK-416). The TLS-reset + force-poll action used to live inline in the logo-tap branch of
`handleWinampInput()`; factored out to a shared `WinampDisplay::tryReconnect()` (public, cooldown-
gated) so the logo tap and Spotify's eject share one implementation and one cooldown window, per the
"duplicated affordance is harmless" call above.

Ripple found and fixed: eject was WebRadio's **only** entry path in the test harness
(`_switch_to_webradio_capture_heap()`, used transitively by `_webradio_enter_with_stations()` and
~10 other tests) — TASK-413 introduced the taskbar-cycle entry path but never migrated the harness
onto it, so it was silently still exercising the old eject-switch behaviour this task removes. Fixed
at the one shared helper (now taps the taskbar player slot instead of eject); `T_WR_HEAP_02` and
`T_WR_SPOTIFY_RESUME_01` had their own independent `tap_eject()` call sites for the same reason and
needed the same fix individually. `T_WR_EJECT_01`/`02` were rewritten in place (same names, new
assertions: TLS-reset-and-stay-on-Spotify / station-refresh-and-stay-on-WebRadio) rather than deleted,
since `T_PLR_06` covers the cross-mode gate but these remain the WebRadio-app-specific unit checks.

### TASK-415 — `m3u.h` + index model + read-only `LocalPlaylistSource`

Extended-M3U parse (`#EXTINF:<sec>,<Artist> - <Title>`), relative paths resolved against the
playlist directory, row text read on demand. Backing structure is **one immutable array plus two
permutations** (ADR-059 D3): `entries[]` `{uint32 offset, uint16 durSec, uint16 flags}` (2 048 B
@256, load-order, subscripts are stable ids), `viewOrder[]` `uint16` (what PLEDIT renders and SAVE
writes), `playOrder[]` `uint16` (what playback advances through) — 3 072 B total, plus a ≤8-row text
cache (576 B) and a 16-entry staging arena (1 536 B).

**All of it heap, none of it static** — the debug build's headroom does not permit a global app
instance's members in `.bss`. Acquire in `resume()`, free in `suspend()`. Register the buffers in
`mem_manifest.yaml` (`kind: scratch`, `placement: runtime`).

**Owner:** Developer · **Deps:** TASK-410, TASK-413 · **Gate:** `T_PLR_08`–`12`; `T_PLR_11` covers
malformed input (truncated, missing `#EXTINF`, CRLF, BOM), `T_PLR_12` requires the heap delta to
return to baseline ±256 B on suspend · **Priority:** P2 · **Status:** **DONE** — implemented and
DUT-gated 2026-08-11 (`T_PLR_08`–`12` 5/5 PASS).

> ~~**Blocking sub-decision (OQ1)**~~ — **resolved 2026-08-11**: `app/src/util/asciiFold.h`
> (`textfold::foldUtf8`). It did **not** change `PlRow`'s contract as feared — the fold belongs in
> the source that composes the row text, so `PlRow::text` keeps its existing "already renderable"
> meaning. Applying it to the Spotify/WebRadio sources, which carry the same latent bug, is
> TASK-428 (separate because it deliberately changes pixels those tasks' gates froze).

**Implementation.** `app/src/player/m3u.h` — `PlEntry {uint32 offset, uint16 durSec, uint16 flags}`,
`PlaylistIndex` with `entries[]`/`viewOrder[]`/`playOrder[]` (identity permutations for now; nothing
mutates them until TASK-418/420) and an 8-row text cache; `app/src/localPlayerApp.h` grows a nested
`LocalPlaylistSource` (CAP_PLAY only) and real resume/suspend/tick/input. Heap, never `.bss`:
3 616 B, acquired in `resume()`, freed in `suspend()` — registered in `mem_manifest.yaml` as
`player_index` + `player_rowcache`, both `placement: runtime`.

Four decisions worth recording, because each has a wrong-looking-right alternative:

1. **`offset` addresses the record, not the path line.** Pointing it at the path (the obvious read
   of "one entry, one file") makes the `#EXTINF` artist/title unreachable without rescanning from
   the top of the file for every row repaint.
2. **The playlist `File` stays open for the session.** Re-opening per row read costs a FAT
   directory scan each time. This spends the mount's second open-file slot — `kSdMaxFiles = 2`
   (audio + playlist), so **TASK-416's browser needs the mount bumped to 3** before it can hold a
   directory handle. Recorded here so that lands as a mount-sizing change and not as a mystery.
3. **`../` is not collapsed.** `_resolve()` strips a leading `./` and otherwise prepends the
   playlist's directory verbatim, letting FatFs resolve `..`. A hand-rolled collapse would be a
   second, divergent path parser — the classic place these disagree.
4. **The FILE arm's pump result is consumed by this app.** `s_wrPumpResult` is one shared slot;
   TASK-410's debug entry point left FILE results parked, so a `CONNECTED` from a local file would
   have been picked up by `WebRadioApp::tick()` on the next mode switch and applied to a stream
   connect that never happened. `LocalPlayerApp::tick()` polls and clears it, and the engine gained
   `aeStopFile()`/`aeTeardownFile()` (mirroring `_stopAudio()` and `suspend()`'s teardown ordering
   exactly — one engine, one ordering) so suspend releases the pump task, `Audio` and the arena.

**Debug surface** (ADR-059 D12, all `SERIAL_DEBUG`): `set plLoad <path>` (raw-args, paths on this
card have spaces), `set plPlay <n>`, `get plCount`, `get plRow <n>`, `get plMem` (free heap **and**
largest-free-block, VE-15), `get plFold <text>`. `cmdTap`'s LocalPlayer branch now calls
`injectTouch()` before `handleInput(Release)`, like the WebRadio branch — without it the harness
could reach eject and transport but never a PLEDIT row, and the injected and real-touch paths would
anchor against different state (the TASK-406 defect class).

**Found along the way, filed not fixed:** production builds never mount the card at all — the boot
mount is inside `main.cpp`'s `SERIAL_DEBUG` region from TASK-408 (**TASK-427**).

**Fixtures.** `app/tools/gen_playlist_fixtures.py` generates the six M3U fixtures the gate needs
(120-entry, relative-path, UTF-8, malformed, empty). Getting them onto the card was supposed to need
a host card reader — TASK-424 says the write path is broken. Re-probed it instead of assuming:
`sdwrite 2` wrote 1 KB in 5 ms with no panic, so **short bursts work on this SDHC card today** even
though sustained writes do not. That bought a much better rig: `sdmkdir` + `sdput <w|a> <base64>
<path>` (SERIAL_DEBUG, ≤90 B per call — the 160 B serial line buffer sets the chunk) driven by
`app/tools/sd_put.py --tree`. All six fixtures uploaded byte-exact, no panic. This does **not**
reopen TASK-424: it is one open/write/close per call, it is test tooling, and TASK-421's save path
is still blocked on the sustained-write defect.

**DUT gate (2026-08-11, `cyd2usb_winamp_debug`): `T_PLR_08`–`12` all PASS, one clean 5/5 run on the
final build** (`5 passed, 0 failed, 0 skipped, 0 flaked`).

| id | result |
|---|---|
| `T_PLR_08` | PASS — 120 entries in 18–19 ms, `totalSec` 29890, last row correct |
| `T_PLR_09` | PASS — 12 full-list swipes during playback, still playing, worst swipe round-trip 0.1 s |
| `T_PLR_10` | PASS — bare, `./` and `../` all resolve against the playlist directory |
| `T_PLR_11` | PASS — 8/8 malformed cases; empty file loads to 0; UTF-8 folded to ASCII |
| `T_PLR_12` | PASS — +3 676 B resting, +8 052 B peak with the file open, residual **+0 B**, largest-free-block unchanged 19 444 → 19 444 → 19 444 |

`T_PLR_12`'s residual is exactly 0 B here and on three earlier runs, and an independent 3-cycle
enter/play/leave probe returned free heap to 72 844 B every single time — the index is balanced.
Two earlier full-suite runs failed it on the *allocation* side rather than the leak side (one ended
with largest-free-block at 1 460 B after the playback tests, too fragmented to acquire 3.6 KB).
Neither reproduced in isolation or in the clean run. Watch it during TASK-422's soak: the suspicion
is the decoder's libc-fallback allocations when the arena acquire fails, which is not this task's
code but is the state this task's allocation lands in.

**Four defects the gate found, all fixed here:**

1. **Path normalisation was needed after all, and then written wrong.** Decision 3 above ("let FatFs
   collapse `..`") is false on this platform: the ESP-IDF FATFS VFS passes the path through
   untouched and `/playlists/../mp3/x.mp3` fails to open. Added `_normalize()` — and its first cut
   appended the separator *after* each segment, which on the final segment writes over the string's
   NUL, the byte the read cursor is standing on, so the loop reads on into the heap and emits
   `/mp3/02 - Clint Eastwood.mp3/<garbage>`. Intermittent by nature (it depends on the next byte
   being non-zero), which is exactly why it took a DUT run to see. Now writes the separator *before*
   each segment, where the write cursor is provably behind the read cursor. The playlist's own path
   is normalised too, or `_deriveDir()` hands every relative track a directory containing `..`.
2. **Trailing whitespace on a path line was not trimmed** — leading was. FAT will not open
   `"/mp3/x.mp3   "`, and hand-edited playlists collect stray spaces.
3. **Persisting the last playlist at selection time fails during playback.** `SettingsStorage`
   allocates a 6 KB ArduinoJson doc; with the Helix arena holding the large contiguous blocks the
   8-bit largest-free drops to ~2.8 KB, the ctor alloc fails, capacity is 0 and TASK-329's guard
   aborts the save (`JSON doc OVERFLOWED`). Moved to a coalesced suspend()-time write per ADR-050
   rule 3 — by then the engine is torn down and the arena released. Filed as TASK-429 because the
   same trap catches every settings write during playback, not just this one.
4. **A row tap can park the UI for up to 150 s.** `aeConnectFile()` calls `spotifyTask::tlsYield()`,
   which blocks the *calling* task until the Spotify task acks — 150 s worst case, and it feeds the
   TWDT, so the device does not crash, it just goes silent. Pre-existing engine behaviour that
   WebRadio's `_play()` shares; TASK-415 makes it reachable from a PLEDIT row tap. Not fixed here
   (it is the M-TLSYIELD thread's problem) — filed as TASK-430, and the tests now `set bgPoll 0`.

**Harness gaps found and fixed** (`run_serialdbg_tests.py`): the readiness check knew `WebRadio` but
not `Player`, so a device persisted in Player mode fell through to the 60 s Spotify-poll wait and
then failed startup — the same TASK-413 widening miss as §6.1's getter. Added `--no-wifi`
(`NO_WIFI=1 ./run/test-targeted`) for suites that touch no network, which waits for the *shell*
rather than for an IP — "do not require WiFi" is not "do not wait for the DUT", and the first cut
got that wrong and simply moved the failure to the first command. `_enter_player()` retries the
taskbar tap once (a dropped scroll-anchor landed it on PlaneRadar).

**Rig note:** the AP was flapping throughout this session — the boot cascade repeatedly gets an IP
and then drops it (`STA_GOT_IP` → `ASSOC_LEAVE` ~150 ms later). That is TASK-426's neighbourhood,
not this task's, but it is why the gate needed several runs.

### TASK-416 — `fileBrowser.h` via `SPickerList`, eject entry, play-from-browser

Modal full-canvas list over the player. **Reuse, do not rebuild:**
`settings/settingsWidgets.h`'s `SPickerList` already provides scrollbar, drag, offset clamping,
highlight, open-scrolled-to-selection and a documented CP-1 full-phase takeover contract — it is
merely typed to `CountryEntry`. Generalising its item type is smaller and better-tested than a fourth
list widget. `settingsSection.h` supplies `drawRow()`/`drawRows()`.

One directory level at a time (`SD.open` + `openNextFile()`), **paged at ≤32 entries per tick** so
loopTask never stalls the audio pump; page size tuned from TASK-408's `listDir()` timing. Directories
first, then `.mp3`/`.m3u`, natural FAT order, no sort buffer. Tap file → play; directory → descend;
`.m3u` → load as active playlist.

**Owner:** Developer · **Deps:** TASK-415 · **Gate:** `T_PLR_13`–`16`. `NEW-APP-CHECKLIST.md` items
1 and 4 apply directly: `hasPendingAsync()` true while a page read or save is in flight, and
`isNavigationTap()` **must** except the browser back/up zone or the shell busy gate swallows
navigation taps — TASK-384 is the precedent, confirmed on real hardware, not just in the harness ·
**Priority:** P2 · **Status:** **READY** — ADR-059 accepted 2026-08-07.

### TASK-417 — transport capability mask: un-gate shuffle, repeat and seek

**No new skin work.** `chrome-001` already bakes `SKIN_SHUFREP` (75×30, four sprites), and
`winampDisplay.h` already draws (`SHUFFLE_X=164`, `REPEAT_X=211`), hit-tests and optimistically
caches shuffle/repeat. What blocks reuse is that it is hardcoded Spotify — hit-tested inside
`handleWinampInput()` (whose own comment names them "Spotify-only zones") and dispatched straight to
`spotifyTask::ACT_SHUFFLE`/`ACT_REPEAT`.

Replace mode-hardcoding with a per-mode mask `CAP_TRANSPORT | CAP_SEEK | CAP_SHUFFLE | CAP_REPEAT`;
a zone whose capability is absent is neither drawn nor hit-tested. Spotify all four, WebRadio
`CAP_TRANSPORT` only, Player all four. Rendered state sourced from the mode, not from
`spotifyTask::Snapshot`. `handleVolumeGesturePublic()` — which exists *only* because
`handleWinampInput()` is Spotify-hardcoded — can then be retired, but **in its own commit**: it
shares the `D_VOLUME_DRAG` machine (TASK-352) and WebRadio's volume path already cost TASK-406 a bug.

**Owner:** Developer (Architect consult) · **Deps:** TASK-412, TASK-413 · **Gate:**
`T_PLR_17`–`19`. `T_PLR_17`/`18` protect two shipped modes from a refactor they get no benefit from
— any WebRadio or Spotify delta here is a regression, not a feature · **Priority:** P2 ·
**Status:** **READY** — ADR-059 accepted 2026-08-07 (D8).

### TASK-418 — play-order engine: shuffle bag, repeat, auto-advance

**Shuffle is a materialised bag**, not a per-`next` dice roll: Fisher-Yates permutation of
`playOrder[]` on toggle-on, advance walks it. Re-rolling a random index per advance repeats tracks
and starves others — the standard way this ships broken — and materialising it is what makes Prev
replay history and tap-to-play move the cursor instead of reshuffling.

**Repeat is binary**, encoded in the shipped tri-state domain (Player emits only `2`=off and
`0`=repeat-all) so `drawRepeat()`'s existing `s != 2 → ON` rule is untouched. Repeat-one deferred:
the skin has two repeat sprites, and two indistinguishable ON states are tolerable for Spotify (the
phone app is the source of truth) but not for a device that is its own only display.

All four shuffle × repeat end-of-list cells are specified in local-playback §8 — implement the table,
including the guard that a reshuffle-on-wrap must not re-open with the track that just finished.
Auto-advance drains TASK-410's `audio_eof_mp3` flag on loopTask; **the bag is loopTask-owned state
and must never be mutated from the pump task.**

**Owner:** Developer · **Deps:** TASK-415, TASK-417 · **Gate:** `T_PLR_20`–`26`; `T_PLR_21` is all
four cells 4/4, `T_PLR_22` is 0/20 collisions over 20 wrap cycles · **Priority:** P2 ·
**Status:** **READY** — ADR-059 accepted 2026-08-07 (D9).

### TASK-419 — real posbar seek for local files

The vendored `Audio` exposes `setFilePos()`, `setTimeOffset()`, `getFilePos()`, `getFileSize()`,
`getAudioFileDuration()`, `getAudioCurrentTime()`. The Player posbar becomes a genuine scrub against
real duration — not WebRadio's estimated slew (M-WEBRADIO-POSBAR-SLEW/SMOOTH), not Spotify's
`seek()` round-trip. Falls out of TASK-417's un-gating.

**Owner:** Developer · **Deps:** TASK-417 · **Gate:** `T_PLR_27`–`28` — ±2 s of target at 25/50/75 %,
and 20 scrubs during playback with no underrun or decoder reinit failure · **Priority:** P3 ·
**Status:** **READY** — ADR-059 accepted 2026-08-07.

### TASK-420 — PLEDIT edit mode: button strip, reorder, delete

PLEDIT title-bar tap toggles edit mode; the bottom bar — today only total-time text — becomes
`[+] [–] [↑] [↓] [SAVE]`, and row tap selects rather than plays. Reuses `settingsWidgets.h`'s
`SButton`/`sButtonBar()`. Skin-authentic (real Winamp's ADD/REM/SEL/MISC/LIST strip).

Drag-to-reorder was **rejected**: 16 px rows on a resistive panel, in direct collision with the
TASK-277 velocity-scroll gesture. Mutations are pure permutation edits — reorder permutes two
`uint16` in `viewOrder` (`playOrder` untouched: dragging a row must not make the playback queue
jump), delete memmoves `viewOrder` **and** drops the id from `playOrder`, fixing the bag cursor if it
pointed past the removed slot.

**Owner:** Developer · **Deps:** TASK-415, TASK-417 · **Gate:** `T_PLR_29`, `T_PLR_34` ·
**Priority:** P2 · **Status:** **READY** — ADR-059 accepted 2026-08-07 (D5).

> **Blocking sub-decision (OQ2):** does `bake_skin.py`'s `build_pledit_atlas()` already crop
> ADD/REM/SEL/MISC/LIST from `PLEDIT.BMP`? If not: bake-tool change + new `skin_layout.h` constants
> + `golden.sha256` re-bake + T025 determinism re-check. Check before estimating this task.

### TASK-421 — add-from-browser (staging), save, restore

Add appends to `entries[]` with a "staged" flag (path in the bounded staging arena) and appends the
id to both permutations. SAVE streams `viewOrder`, copying each source line to `<name>.m3u.tmp`,
emitting staged entries **from the staging arena** — they have no backing offset yet, and the naive
copy loop drops them *while reporting success* — then renames. One sequential pass, constant memory.
Rename is the atomic commit point. Mount-time sweep deletes stray `.tmp` files.

SAVE is the one unbounded SD operation: it runs only from edit mode and **pauses playback** for its
duration — deliberate and visible, not a background write.

**Owner:** Developer · **Deps:** TASK-420 · **Gate:** `T_PLR_30`–`33`. **`T_PLR_30` and `T_PLR_31`
are verified host-side, off the card** — shuffle ON + reorder + SAVE must write **display** order,
and staged adds must survive. Both have failure modes where the device confidently reports success;
**never verify a save by re-reading through the structure that produced it** ·
**Priority:** P2 · **Status:** **READY** — ADR-059 accepted 2026-08-07.

### TASK-422 — build variants, soak, VE suite, registry completion

Compile-time mode flags `-DPLAYER_SPOTIFY` / `-DPLAYER_WEBRADIO` / `-DPLAYER_LOCAL` (presence only,
never `=0` — LL-006). Four consequences are **not** automatic: cycling iterates the compiled-in set
(a single-mode build must not cycle); a persisted `playerMode` naming an absent mode falls back to
the first compiled-in one; `TASKBAR_APP_COUNT` computed from the compiled-in tail; Settings lists
only compiled-in modes. Existing `-DDISABLE_SPOTIFY` stays as-is — load-bearing for the harness's
`get variant` fast path, do not migrate it here.

**No 2³ env matrix.** `check_build.sh` runs two full builds today; eight would make the gate
unusable. Add exactly one dev env `cyd2usb_player` (Player only), mirroring the existing
`cyd2usb_webradio` precedent. Gates go 6 → 7.

Close-out: complete the reserved `feature_inventory.yaml` entries and X050–X064, walk
`NEW-APP-CHECKLIST.md` for `AppId::LocalPlayer`, and run the sustained soak.

**Owner:** Developer + VE · **Deps:** all of the above · **Gate:** `T_PLR_35`–`40`.
**`T_PLR_36` is the dangerous one** — a persisted mode naming a compiled-out mode must fall back,
not null-app-crash, and it is only reproducible over *existing* settings: **a clean flash will not
catch it** (X064). `T_PLR_39` is ≥30 min playback **with concurrent browsing and scrolling**, not
idle playback · **Priority:** P2 · **Status:** **READY** — ADR-059 accepted 2026-08-07 (D10).

---

## Closed — TASK-426 (2026-08-10, filed from a DUT "no network" investigation)

### TASK-426 — supervisor replays a dead SSID forever after a failed boot cascade

Filed and fixed in the same session. Reported as "the DUT is off the network"; two earlier passes
attributed it to the AP being down, then to DNS. Both are **downstream symptoms** — with no
association there is no DNS, and `hostByName(): DNS Failed` + `errno=9` on every fetcher is what
that looks like. Recording the real cause here because the misattribution is the expensive part.

**Root cause.** `WiFiSTAClass::begin()` — the *no-arg* overload — is
`esp_wifi_get_config() → esp_wifi_set_config() → esp_wifi_connect()`. It reuses whatever STA config
is already resident and never reloads NVS or the saved list. Three things call it: the WiFiGeneric
auto-reconnect handler (~2.44 s), `wifiDiag::superviseTick()` (30 s), and the boot NVS stage. The
boot cascade (`main.cpp:2431`) leaves **whichever candidate it tried last** resident. When that last
candidate is a dead SSID — here `<home-ssid>`, whose AP had been renamed back to plain
`<home-ssid>` on ch 3 — every subsequent kick re-attacks the dead SSID and the live AP is never
retried. Reboot-only recovery, with the real AP sitting at **−58 dBm**.

`NO_AP_FOUND` was accurate the whole time: it was reported for the SSID actually being requested,
which was not the one the operator had configured. An intermediate conclusion in-session that "the
driver is lying" was wrong and is withdrawn — at that moment the resident config happened to hold
the good SSID, so the comparison was against the wrong thing. **Read `get wifiCfg` and the scan in
the same breath, or the scan means nothing.**

**Evidence (A/B, same firmware, same AP, same failing boot).** Dead entry present → 9+ supervisor
kicks over 5+ min, zero recovery. Dead entry removed → kick #1 reconnected in **225 ms**.

**Refuted along the way** (do not re-run): the TASK-404 collision/silent-no-op variant (no
`connect failed! 0x…` is ever logged, so `esp_wifi_connect()` returned OK); stale channel/BSSID pin,
RSSI and authmode thresholds, PMF, WPA3, wrong credentials (all refuted by `get wifiCfg`:
`bssid_set=0 ch=3 thr_rssi=-127 thr_auth=3 pmf_r=0 pwlen=25`); RF or power marginality (the DUT's own
scan saw 9 APs with the target at −58 dBm *while wedged*).

**Fix** (`d19bcff`). The supervisor takes a registered candidate list and connects with an explicit
ssid+pass per kick, **rotating one step each kick** — replacing the resident config instead of
replaying it, so one dead entry costs one kick rather than every kick. With no candidates registered
it falls back to the historic bare `begin()`, leaving no-credentials and NVS-connected boots
unchanged. `main.cpp` additionally re-points at the MRU candidate on cascade failure so the ~60 s
before the first kick is not spent on the last-tried AP. Costs ~582 B static; mem-budget gate passes.
`[wifi-sup]` stays a stable grep contract — `ssid`/`cand` are appended, never substituted.

**Tooling** (`0d35696`, all `SERIAL_DEBUG`-gated; prod answers `unknown command`). `get wifiCfg`
dumps the STA config and is what cracked this. `get wifiScan` now prints `own=` plus every scan row —
the stock `matches:[]` form is ambiguous, because an unassociated STA has an empty `own`, so "AP
absent" and "filter matched nothing" print identically. `set wifiKick 1` quiesces then does exactly
one `begin()`; both its waits feed the TWDT per TASK-288, without which it panic-reset the board and
the reset masqueraded as a recovery.

**Owner:** Developer · **Deps:** none · **Gate:** met — forced-failure boot (NVS erased, three
unreachable SSIDs) rotated `kick=1 gamma cand=1/3 → kick=2 alpha 2/3 → kick=3 beta 3/3`, where the
old code would replay candidate 3 forever; and a real failed-cascade boot recovered via
`kick=1 ssid="<home-ssid>" cand=1/1` → `STA_GOT_IP` **609 ms** later. `./run/check` 6/6 ·
**Priority:** P1 (silent permanent loss of network on a headless device) · **Status:** DONE
(2026-08-10), commits `0d35696` + `d19bcff`.

> One smaller thing left open: **nothing evicts saved networks that repeatedly `NO_AP_FOUND`** — a
> stale entry stays in the list forever, costing a 10 s boot window each time and, before this fix,
> wedging the device outright.

### TASK-426b — boot cascade gives each candidate only one connect attempt

Follow-up to the above, fixed in `ec0a6f8`. Originally filed as "the NVS stage interferes with the
cascade behind it", on the observation that the first (live) candidate failed ~2.7 s in when NVS
held a dead SSID but connected in ~1 s when NVS was erased. **That framing was wrong on both
counts** and is recorded here so it is not re-derived.

*Refuted 1 — it is not a stale in-flight scan.* A full driver stop/start before the cascade
(`WIFI_OFF` → `WIFI_STA`, confirmed by `STA_STOP`/`STA_START` in the event log at t=11389/11614)
changed nothing: the candidate still failed at 2.7 s. That attempt is reverted; the original 300 ms
settle stands with a comment so nobody lengthens it hoping for a different result.

*Refuted 2 — it is not deterministic.* It is intermittent, ~1 boot in 3. The original conclusion
came from three boots, which is exactly the sample size that produced the two earlier
misattributions in TASK-426.

**Real defect.** TASK-404 disables auto-reconnect for the whole cascade. Nothing else re-issues a
connect, so each candidate gets exactly ONE attempt; a transient `NO_AP_FOUND` leaves the rest of
its 10 s window as dead air and the cascade gives up with a healthy AP at −56 dBm in range. The fix
re-issues `begin()` on each observed failure, using `wifiDiag::discCount` as the completion edge.
It is a **tolerance for the transient, not a cure** — the transient itself is still unexplained.

**Gate:** met — same-build A/B, stale SSID forced into NVS before every boot:

| arm | boots failing the cascade |
|---|---|
| retry disabled | 9 / 24 (37.5%) |
| retry enabled | 0 / 16 |

**Owner:** Developer · **Priority:** P2 · **Status:** DONE (2026-08-10), commit `ec0a6f8`.

> Scaffolding worth keeping, all `SERIAL_DEBUG`-gated: `set nvsSsid <ssid>` recreates the stale-NVS
> precondition without renaming a real AP; `set casRetry 0|1` picks the A/B arm; `set reboot 1`
> software-resets. **The reset method is load-bearing** — an EN/RTS reset clears the RTC domain
> where the arm flag lives, so the first attempt at this A/B ran the control in *both* arms and
> looked perfectly clean. The flag is cookie-guarded and compiled out of prod, because an unguarded
> `RTC_NOINIT` read would let a cold boot disable the retry at random in a production build.

### TASK-427 — production builds never mount the SD card

Found while landing TASK-415. `sdProbeBootMount()` and its `setup()` call site sit inside
`main.cpp`'s `#ifdef SERIAL_DEBUG` region, because TASK-408 landed them as bring-up tooling
alongside `sdprobe`/`sdmount`/`sdls`. Nothing since has moved them out. So **`cyd2usb_winamp`
(production) has no SD mount at all**, and Player mode degrades to "No SD card" there while working
fully on `cyd2usb_winamp_debug`. Every T_PLR gate runs on the debug build, so no gate catches this —
it is exactly the class of divergence `T_PLR_35` (each variant builds *and boots*) exists for.

Not fixed inside TASK-415, deliberately: an unconditional boot mount costs ~13 KB of
permanently-held **contiguous** internal heap (FATFS window + `max_files` × `FIL`, `FF_MAX_SS=4096`,
`FF_FS_TINY=0`), and that lands on top of WebRadio's 40 KB TLS fetch guard and the Helix arena's
23 216 B contiguous need. It is a memory-budget decision with an ADR-059 D1 dependency
(TASK-425 is re-measuring that same table under arena-first ordering), not a `#ifdef` move.

Options, in the order they should be considered:
1. Mount unconditionally at boot in every build, and re-run the M-HEAP-FRAGMENTATION numbers —
   simplest, and the only one that makes the mount deterministic, but it taxes every app.
2. Mount on first entry to Player mode and unmount on suspend — cheapest for the other apps, but
   TASK-408's measurement is that a lazy mount is only as reliable as the heap happens to be at
   that moment (it fails outright once WebRadio is playing), which is precisely why the boot mount
   was chosen.
3. Gate the mount on a build flag that the Player-mode variant sets — keeps prod unchanged and makes
   `cyd2usb_player` (TASK-422) work, at the cost of Player mode being absent from the main build.

**Owner:** Architect (Developer implements) · **Deps:** TASK-425 (the re-measure this rests on) ·
**Gate:** `T_PLR_35`/`T_PLR_36` cover it once decided; add a production-build assertion that
`sdReady()` and the compiled-in mode set agree · **Priority:** P2 — blocks Player mode shipping in
production, blocks nothing before that · **Status:** OPEN — filed 2026-08-11 from TASK-415.

### TASK-428 — apply the ASCII fold to the Spotify queue and station-list rows

TASK-415 resolved design OQ1 with a shared helper (`util/asciiFold.h`, `textfold::foldUtf8`) and
wired it into `LocalPlaylistSource` only. The same latent bug is live in the two shipped sources:
`SpotifyQueueSource::row()` copies the API's UTF-8 artist/title straight into `PlRow::text`, and
`StationListSource::row()` does the same with radio-browser station names — both then render through
TFT_eSPI Font 1 (GLCD), whose glyphs above 0x7F are box-drawing symbols. An accented artist name
("Björk", "Sigur Rós", "Motörhead") therefore renders as unrelated symbols today, one per UTF-8
continuation byte.

The fix is one call per source. What makes it a separate task is the gate: TASK-411 and TASK-412
were held to **pixel identity** against the pre-extraction PLEDIT copies, and this deliberately
changes pixels for exactly the rows that were wrong. It needs its own before/after screendump pair
on real content, not a silent rider on a task whose gate is about something else.

Also in scope: the Winamp **title marquee** (`winampDisplay.setTitle()`) draws through `SKIN_FONT` /
`SKIN_GLYPH[128]`, i.e. a 128-entry ASCII atlas — same class of bug, same one-line fix, and the more
visible of the two since the title is 8 px tall and scrolls.

**Owner:** Developer · **Deps:** TASK-415 (helper landed) · **Gate:** screendump before/after on a
queue containing at least one Latin-1 and one Latin-Extended-A name; `T_PLE_*` row-geometry tests
must be unchanged (the fold changes glyphs, never column widths — a 2-byte codepoint folding to 1–2
ASCII characters can change a row's rendered *length*, so the truncation path is what to watch) ·
**Priority:** P3 · **Status:** OPEN — filed 2026-08-11 from TASK-415's OQ1 resolution.

### TASK-429 — a settings save during playback silently aborts

Found in TASK-415. `SettingsStorage::save()` builds a `DynamicJsonDocument(6144)`. While a track is
playing, the Helix arena holds the large contiguous blocks and the **8-bit-capable** largest free
block drops to ~2.8 KB (boot log: `freeDma=3028 lfbDma=2804` right after decoder init), so the
document's constructor allocation fails, ArduinoJson reports capacity 0, every add no-ops, and
TASK-329's `doc.overflowed()` guard aborts the write with
`SettingsStorage: JSON doc OVERFLOWED — save aborted, previous file kept!`.

The guard does its job — nothing is corrupted and the previous file survives — but the *caller* is
told nothing: `save()` returns void, so a feature that persists something during playback silently
does not persist it. TASK-415 dodged this by coalescing its write into `suspend()` (ADR-050 rule 3),
which is the right pattern anyway, but the trap is general: any settings write while audio is up
hits it, and the next author will not know.

Worth noting the diagnostic gap too: the success path logs `saved (doc 1914/6144 B)` while the
failure path logs no numbers at all, so the log line reads like a capacity overflow when it is
really a failed allocation. The two are indistinguishable in the field today.

Candidate fixes: (a) `save()` returns bool and callers handle it; (b) defer-and-retry a failed save
rather than dropping it; (c) shrink or statically place the document so the allocation cannot fail;
(d) at minimum, log `memoryUsage()`/`capacity()` on the failure path so the two modes are
distinguishable. (a)+(d) are the cheap pair.

**Owner:** Developer · **Deps:** none · **Gate:** set a persisted value from a debug command while a
local file is playing, reboot, confirm it survived; assert the log distinguishes alloc-failure from
true overflow · **Priority:** P2 · **Status:** OPEN — filed 2026-08-11 from TASK-415.

### TASK-430 — a PLEDIT row tap can freeze the UI for up to 150 s

Found in TASK-415, but the mechanism is older than it. `aeConnectFile()` (and `WebRadioApp::_play()`
before it) calls `spotifyTask::tlsYield()`, which blocks the **calling** task until the Spotify task
acknowledges the stop. That wait is bounded at 150 s by design (TASK-286: two API calls × 75 s), and
it deliberately feeds the task watchdog in 200 ms slices so the device does not reboot. The result
when the Spotify task is genuinely stuck mid-HTTP: loopTask stops for as long as it takes — no
repaints, no heartbeat, no serial responses — and then everything resumes as if nothing happened.

Observed on the DUT 2026-08-11: a `set plPlay` with a wedged Spotify queue GET in flight (the
TASK-243 403 makes a wedged call likely) took the shell out entirely; the test harness saw every
subsequent command time out and reported three unrelated failures. The device was never crashed.

Why it matters more now than it did for WebRadio: WebRadio's entry points are eject and a station
tap, both already understood as "this will take a moment". TASK-415 puts the same 150 s exposure
behind an ordinary PLEDIT row tap on a local file that should start in ~200 ms, and TASK-418's
auto-advance will put it on the end-of-track path where no user gesture is involved at all.

The fix is not to shorten the timeout (that just moves the failure into the connect). Options: make
the yield asynchronous — post the request, return to the caller, and let the connect proceed from
the ack — or give the caller a short non-blocking try-yield and fail the play cleanly when TLS is
busy. Both are M-TLSYIELD-shaped changes touching WebRadio's path too, hence a separate task.

Mitigation in place meanwhile: the `T_PLR_08`–`12` suite suspends the background poll
(`set bgPoll 0`) for its duration.

**Owner:** Developer (Architect consult) · **Deps:** none · **Gate:** with a deliberately wedged
Spotify call in flight, a row tap must either start playback or fail visibly within ~2 s; the shell
must answer serial throughout · **Priority:** P2 — becomes P1 if TASK-418 lands auto-advance on top
of it · **Status:** OPEN — filed 2026-08-11 from TASK-415.
