# Design — M-WEBRADIO-POSBAR-SMOOTH: smooth + rate-limit the WebRadio buffer-fullness bar

> Owner: Architect
> Status: draft
> Date: 2026-08-05
> Feeds: ADR-NNN (TBD — human to decide once the DUT-measured numbers below
> exist; leaning toward "no ADR needed," this is a display-refresh tuning
> fix, not an architectural decision, but flagging rather than deciding)
> Tracked-as: — (not yet scheduled; PM to file a task if accepted — TASK-402
> is the next free number as of this writing)
> Registers: — (modifies the existing `webradio-001` feature, no new
> feature id). Candidate cross-feature edge X049 (`webradio-001` ×
> `perf-001`, the `perf.h` `MAX_PATHS` budget) — **not yet committed**,
> draft status, same reserve-on-acceptance convention as prior designs this
> session.

## Context / pain points

Asked: the WebRadio posbar (repurposed, in WebRadio mode, to show input
buffer fullness rather than playback position) is too jittery and updates
too often, costing CPU/SPI for no visible benefit. Also asked directly:
do we know the current update rate? Answering from the actual code, not
assumption.

### The value: unfiltered, recomputed every tick

`_bufPct` (`webRadioApp.h:1634`) is a **raw, unfiltered ratio**, recomputed
fresh on every `PLAYING`-branch `tick()`:

```cpp
uint32_t filled = _snapFilled;
uint32_t freeB  = _snapFreeB;
uint32_t total  = filled + freeB;
_bufPct = total ? (uint8_t)((uint32_t)filled * 100u / total) : 0;
```
(`webRadioApp.h:950-953`)

`_snapFilled`/`_snapFreeB` come from `_refreshAudioSnapshot()`
(`webRadioApp.h:1694-1704`), which reads `Audio::inBufferFilled()`/
`inBufferFree()` — the **MP3 input ring buffer** inside the vendored
ESP32-audioI2S library (not `mb_arena`, not the ICY buffer, not a decode/DMA
output buffer) — through a mutex with a bounded 50ms timeout-take, falling
back to the last snapshot on a miss rather than blocking. The underlying
buffer itself is filled/drained by the `wrAudio` pump task's `Audio::loop()`
call every `WR_PUMP_CADENCE_TICKS` (2ms, `webRadioApp.h:327`) — so the true
source value can itself change every 2ms, before `tick()` even samples it.

**No smoothing exists on this value anywhere.** Contrast: the same file's
VU meter does have exactly this kind of filter for a different signal —
`lLvl += (targetL - lLvl) * (ATTACK-or-RELEASE)` (`webRadioApp.h:227-228`)
— proven, already-working precedent for value-domain smoothing in this
exact codebase, just never applied to `_bufPct`.

### The redraw gate: value-delta only, no time component — this is the actual "no known update rate" answer

```cpp
int delta = (int)_bufPct - (int)_bufPctDrawn;
if (delta < 0) delta = -delta;
if (delta >= 2) {
    _bufPctDrawn = _bufPct;
    _drawPosbar();
}
```
(`webRadioApp.h:976-981`)

`tick()` itself runs once per `loop()` iteration (`main.cpp:4127-4128`),
and `loop()` has **no `delay()` call anywhere in its body** — confirmed by
reading the full function, not assumed. So there is no fixed frame rate to
report: the redraw gate is purely "did the raw value move ≥2 points since
the last **drawn** value," evaluated at whatever rate the ambient `loop()`
happens to run. If the raw ratio is noisy around a 2-point boundary — which
a byte-level ring-buffer fill ratio naturally will be — this can redraw on
consecutive loop iterations. **This is the concrete, code-level answer to
"do we know the update rate": no, because nothing bounds it by time, only
by an unfiltered value's motion.** No existing telemetry measures the
actual resulting rate either (see below) — the honest answer is "unbounded
by design, unmeasured in practice."

### Per-redraw cost is also higher than it needs to be

`drawBufferBar()` is not a partial/diff redraw — it always repaints the
**entire** 248×10 groove plus the thumb, unconditionally, regardless of how
small the delta that triggered it was:

```cpp
void drawBufferBar(uint8_t pct) {
    ...
    blitSprite(..., SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_BG);       // full 248x10 groove
    blitSprite(..., SKIN_POSBAR, SKIN_POSBAR_W, POSBAR_THUMB_N);  // 29x10 thumb
}
```
(`winampDisplay.h:170-184`), via `blitSprite()`'s one-`pushImage`-per-row
loop (`winampDisplay.h:871-876`) — **20 `pushImage()` calls, ~2,770px** per
redraw. Contrast **Spotify's own real seek bar in the same file**
(`updateSeekThumb()`, `winampDisplay.h:306-322`), which only blits the
old-thumb-position "under" sprite plus the new thumb — **12 calls, ~580px**.
The WebRadio bar is structurally ~4.8× more expensive per redraw than the
mechanism already sitting right next to it in the same file, for no reason
tied to the buffer-fullness use case specifically — it's simply never been
converted to the partial-diff pattern Spotify's bar already uses.

### History — this exact tension has been tuned once before, in the opposite direction

- **TASK-220** (`tasks-archive.md:4668-4707`): introduced a **15-point**
  hysteresis, gated behind a full-chrome repaint.
- **TASK-253** (`tasks-archive.md:6105-6117`): replaced the full-chrome
  gate with today's targeted `_drawPosbar()` blit and **cut the hysteresis
  from 15 points to 2**, explicitly framed as a "smoothness fix" — the
  15-point version produced visible ~33px thumb jumps, which the 2-point
  version fixed by updating more often, in smaller increments.

**This means today's "too many updates" complaint and TASK-253's own
"too jumpy" complaint are the same tension, pulling in opposite
directions on the same one-dimensional knob** (the value-delta threshold).
Simply widening the threshold back up (undoing TASK-253) would reduce
update count but reintroduce the large visible jumps that fix was written
to remove — not a free win, a regression of already-shipped, DUT-verified
work. Any new fix needs a second axis (value smoothing and/or a genuine
time-based cap) rather than re-tuning the one knob TASK-253 already tuned
once.

### Nothing measures this today — no perf path, no redraw-count getter

`perf::record()` has exactly 10 named paths in use, against
`MAX_PATHS = 10` (`perf.h:28-34`) — **zero free slots today**. WebRadio's
posbar redraw cost is folded entirely into the generic `"app.tick"` slot
(`main.cpp:4127-4128`), which wraps the whole `WebRadioApp::tick()` call —
there's no way to isolate the posbar's own contribution to loop time from
existing telemetry. There is also no debug getter for a redraw count, last
redraw timestamp, or effective rate — `get wrUnderruns` exposes the
*current* `_bufPct` and session-low `_minBufPct` (`webRadioApp.h:1322-1331`)
but nothing about how often it's being redrawn. Any claim about "the
current update rate" or "the fix reduced updates by N%" needs new
instrumentation before it can be measured on a DUT, not just asserted.

## Goals

1. Answer "why is it jittery" and "why so many updates" with a real fix,
   not a re-tune of the single knob (`webRadioApp.h:978`'s delta threshold)
   TASK-253 already tuned once in the opposite direction.
2. Add genuine smoothing to the **value** (not just the redraw gate) so a
   naturally noisy byte-level ring-buffer ratio doesn't read as visual
   jitter — precedent already exists in this file (VU meter's EMA).
3. Bound the redraw rate by **time**, not just by value movement — a hard
   ceiling on worst-case SPI/CPU cost regardless of how noisy the
   underlying value is.
4. Don't reintroduce TASK-253's large-jump problem — whatever ships must
   still read as a smoothly-moving thumb, not a bar that visibly steps.
5. Reduce the **per-redraw** cost independently of rate, mirroring the
   partial-diff pattern Spotify's own seek bar already uses in this file —
   a redraw that happens less often should also cost less each time it
   does happen.
6. Make the result measurable — add the instrumentation this design needs
   to actually validate its own before/after claim on a DUT, since none
   exists today.

## Design space (options + tradeoffs)

### A — Value-domain smoothing (EMA on `_bufPct` before threshold comparison)

Apply an exponential moving average to the raw ratio before it's compared
against `_bufPctDrawn`, mirroring the VU meter's existing
attack/release-style filter (`webRadioApp.h:227-228`) — same technique,
same file, already proven. This directly targets *jitter* (the value
itself reads smoother) but by itself doesn't bound *redraw count* — a
smoothed-but-still-continuously-moving value could still cross the ≥2pt
gate every tick if it's drifting steadily rather than oscillating.
**Necessary but not sufficient alone.**

### B — Time-based minimum redraw interval

Add a `millis()`-gated minimum interval between `_drawPosbar()` calls
(e.g., "no more than once per N ms"), independent of the value-delta
check — both conditions must be satisfied (value moved enough, *and*
enough time has passed) before redrawing. This directly bounds worst-case
SPI/CPU cost regardless of how the underlying value behaves — the actual
"unnecessary use of resources" complaint. By itself, without A, a coarser
time gate sampling a still-noisy raw value could still occasionally redraw
a visually "jumpy" reading if the sample happens to land on a noise spike.
**Necessary but not sufficient alone — pairs naturally with A.**

### C — Adopt A + B together (LEAN)

Smooth the value (A) so what's being compared/drawn is a stable trend, not
raw byte-level noise, **and** cap redraw frequency by time (B) so there's a
hard ceiling independent of value behavior. These solve different halves
of the complaint — A addresses *jitter* (visual noise in the value), B
addresses *update frequency* (resource cost) — and composing them avoids
the trap of re-tuning the single value-delta knob TASK-253 already spent
its own tuning pass on. Both are small, additive changes to existing code
(`tick()`'s PLAYING branch and the redraw-gate check) — no new subsystem.

### D — Widen the value-delta threshold back toward TASK-253's original 15 points

**Reject as the primary fix.** This is literally undoing TASK-253's own
DUT-verified change, which fixed a real, previously-shipped visual defect
(33px thumb jumps). It would reduce redraw count, but at the direct cost
of reintroducing the jumpiness the last person to touch this code
specifically fixed. Not free, and not new — just going backwards on an
axis this project has already spent effort tuning once.

### E — Convert `drawBufferBar()` to a partial-diff blit (LEAN, orthogonal to A/B/C)

Mirror `updateSeekThumb()`'s own pattern in the same file
(`winampDisplay.h:306-322`): blit only the old-thumb-position "under"
sprite plus the new thumb, instead of unconditionally repainting the full
248×10 groove every call. This doesn't change *how often* redraws happen —
it changes *what one redraw costs* (measured today at ~20 `pushImage`
calls / ~2,770px; Spotify's equivalent bar does the same job in ~12 calls /
~580px). Independent, additive win regardless of what A/B/C land on —
whatever the new redraw rate ends up being, each redraw becomes cheaper.
One real question this raises (see Open Questions): the groove sprite is
currently re-blitted every call specifically to "restore" it
(`winampDisplay.h:172-174` comment) — need to confirm nothing else paints
over the groove between buffer-bar redraws in WebRadio mode before
dropping that restore-every-call behavior.

### F — Add instrumentation before shipping any behavior change

Add a dedicated `perf::record("wr.posbar", ...)` path around
`_drawPosbar()`'s call site, and a debug getter (e.g. `get wrPosbar` →
`{redraws, lastIntervalMs, bufPctRaw, bufPctSmoothed}`) exposing the raw
vs. smoothed value and actual redraw cadence. **Prerequisite for any
credible before/after claim**, not optional polish — today literally
nothing measures this, so "the fix reduced updates by N%" is currently an
unfalsifiable claim on this codebase. Adding the perf path requires
bumping `MAX_PATHS` from 10 to 11 (`perf.h:28-34`) — the file's own comment
already marks this as the correct, deliberate way to add a path once the
budget is full, not a workaround.

## Lean / decision

**Adopt C (A+B) + E + F.** Concretely:

1. **F first (measure before changing behavior):** add
   `perf::record("wr.posbar", ...)` around `_drawPosbar()`'s call site
   (bump `MAX_PATHS` 10→11 in `perf.h`), and a `get wrPosbar` debug getter
   reporting redraw count, last-redraw interval, raw `_bufPct`, and (once
   it exists) the smoothed value. Capture a DUT baseline of today's actual
   redraw rate and per-call cost before changing anything — turns "too
   jittery, too many updates" from a subjective complaint into a measured
   starting point.
2. **A:** add an EMA filter on `_bufPct` (same shape as the VU meter's
   attack/release filter, `webRadioApp.h:227-228`) — smoothed value feeds
   the redraw-gate comparison and the actual draw, raw value stays
   available via the new getter for comparison/debugging.
3. **B:** add a `millis()`-gated minimum redraw interval alongside the
   existing value-delta check — both must be satisfied to redraw.
4. **E:** convert `drawBufferBar()` to a partial-diff blit (old-thumb-region
   + new-thumb, skip the full-groove re-blit unless something else is
   confirmed to paint over it between calls — see Open Questions).

Not adopted: Option D (regresses TASK-253's own fix for no independent
benefit).

## Open questions

- **OQ1 (EMA alpha value).** Not derivable from static analysis — needs a
  DUT tuning pass using the new `get wrPosbar` getter (per F) to compare
  raw vs. smoothed traces under real playback and pick a constant that
  reads as smooth without lagging real buffer-health changes a user should
  actually notice (e.g., a stall approaching should still be visible in
  time to matter).
- **OQ2 (minimum redraw interval value).** Same — needs DUT measurement of
  the actual current redraw rate (via F's baseline capture) before picking
  a number. A guess without that baseline risks either not helping (too
  short) or feeling laggy (too long); this design deliberately doesn't
  pre-commit to a constant.
- **OQ3 (does dropping the full-groove re-blit in Option E ever regress a
  visual case).** The groove is re-blitted every call today specifically
  described as "restoring" it (`winampDisplay.h:172-174`) — need to confirm
  nothing else (marquee scroll, ICY title redraw, VU tick, an injected
  tap) ever paints over the POSBAR region between two buffer-bar redraws
  in WebRadio mode specifically, before it's safe to stop unconditionally
  restoring the groove on every call. Developer to check at implementation,
  not assumed clean here.
- **OQ4 (perf-path budget).** `MAX_PATHS` bump 10→11 is per the file's own
  documented pattern, low risk, but is itself a small cross-cutting change
  (every existing named path's slot index is unaffected, but the constant
  is shared budget) — flagged as the candidate `X049` edge below rather
  than silently bundled in.

## Exit criteria

- DUT baseline (pre-change, per F): `get wrPosbar` captures redraw count
  and interval distribution over a fixed real-playback window (e.g. 5 min),
  establishing the actual "how often does this redraw today" number this
  design doc could not determine from source alone.
- DUT post-change: same window, same station/conditions — redraw count
  measurably lower, with the smoothed value's visual motion still reading
  as continuous (no TASK-253-style visible jumps) — a human eyeball check
  DUT-side, not just the getter's numbers.
- DUT: a real stall/underrun approaching zero buffer is still visibly
  reflected on the bar in time to be useful — the smoothing/rate-limit
  must not hide a real depleting-buffer trend behind lag (ties to OQ1/OQ2).
- Regression: existing WebRadio DUT suite (auto-skip, eject, ICY marquee,
  vis-mode toggles) unaffected — this design touches only `_bufPct`'s
  computation/redraw path, not playback/state logic.
- `./run/check` 5-gate green.
- `perf::record("wr.posbar", ...)` present and non-dropped (`MAX_PATHS`
  bumped, confirmed via the existing overflow-is-silent-drop behavior not
  triggering — i.e. the new path actually shows up in perf output).

## Registers

**Not yet committed** (draft status — reserve-on-acceptance convention,
same as this session's other designs). If accepted:

No new feature id — this modifies the existing `webradio-001` feature's
posbar behavior in place; `webradio-001`'s `feature_inventory.yaml` entry
should have its description/notes updated at implementation to reflect the
smoothing + rate-limit + partial-diff-blit behavior (Developer's job at
implementation, per this project's file-ownership convention).

Candidate cross-feature edge: **X049** — `webradio-001` × `perf-001`
(`perf.h`'s `MAX_PATHS` budget) — `dependency`, `risk: low`. Description:
adding the `wr.posbar` perf path (§Lean step 1) requires bumping
`MAX_PATHS` from 10 to 11 — the shared budget constant every other named
perf path also depends on. Anyone adding another perf path after this one
should read this edge and `perf.h:28-34`'s own comment first.
`test_coverage: []` — VE to attach once a test id exists.
