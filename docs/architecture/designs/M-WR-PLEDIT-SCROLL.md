# Design — WebRadio PLEDIT drag/velocity scroll (M-WR-PLEDIT-SCROLL)

> Owner: Architect
> Status: accepted — human-approved 2026-07-03 (panel: VE/DEV/QM approve-with-changes ×3, dispositions applied)
> Date: 2026-07-02 (dispositions applied 2026-07-03)
> Feeds: ADR-TBD (lean below to be promoted after review)
> Tracked-as: TASK-277
> Deps: M-LIST-v4 / ADR-030 (the gesture model being reused), M-WEBRADIO (done)
> Sibling: M-WR-AUDIO-TASK (decode off loopTask — affects scroll tick cadence, not this design's correctness)

---

## Context / pain points

WebRadio's PLEDIT is tap-to-play only. `WebRadioApp::handleInput`
(`app/src/webRadioApp.h:390-426`) begins with `if (phase != TouchPhase::Release) return false;`
— Press and Move are discarded. Consequences observed on DUT (operator report 2026-07-02):

- **A swipe is a misclick.** Any drag gesture is silently reinterpreted on finger-lift as a
  tap on whichever row the finger ends over → wrong station starts playing.
- **No user-driven scrolling exists.** `_scrollOffset` moves only by auto-follow in `_play()`
  (`webRadioApp.h:727-732`, keep-current-visible). With `WR_MAX_STATIONS = 30` and
  `PLEDIT_ROW_COUNT = 5` visible rows, 25 of 30 stations are reachable only by repeatedly
  playing NEXT/PREV — each of which *starts playback* of every intermediate station.
- **Experience gap vs Spotify.** Spotify's PLEDIT in the same chrome has the full M-LIST-v4
  velocity-joystick machine (ADR-030, accepted; DUT-validated VE T155–T161). Users see one
  widget with two behaviours.

The plumbing already exists: `appHandleInput` (`main.cpp:1860-1931`) delivers
Press/Move/Release to `WebRadioApp::handleInput` exactly as it does for Spotify. Only the
app-side gesture logic is missing. Chrome is already shared (`drawPleditFrame`, scrollbar
thumb); input logic is not.

### What is generic vs Spotify-coupled in the existing machine

Audit of `winampDisplay.h:302-553` (`handleWinampInput`, `tickScroll`, `updateScrollDirect`):

| Generic (reusable as-is) | Spotify-coupled (does not transfer) |
|---|---|
| `D_PLEDIT_SCROLL` press-anchor state (`_dragStartY/_dragCurrentY/_dragStartRow/_dragStartMs/_dragStartScrollOffset`) | Release-tap action: `spotifyTask::enqueue(ACT_PLAY_URI, idx)` + `optimisticSelectedRow` + `_skipPending` + `_lastInputWasAsync` |
| `tickScroll(float dt)` velocity integrator (~20 lines, `winampDisplay.h:532-553`) | Clamp source `lastCount` (Spotify queue snapshot; seqno-cancel in `drawPlaylist()`) |
| Tap discrimination: `PLEDIT_TAP_PX`(6) + `PLEDIT_TAP_MS`(250) + quick-swipe min-1-row fallback | `drawScrollThumbOnly()` targeted repaint (Spotify's renderer path) |
| Scrollbar direct-drag mapping math (`updateScrollDirect`, `winampDisplay.h:693-707`) | `touchScreenCoolDownTime` interplay with transport/volume/posbar hit-tests |
| Tuning constants `SCROLL_DEAD_ZONE_PX`(1), `SCROLL_SPEED_K_DEFAULT`(0.1667), `_scrollSpeedK` dbgSet | Origin offsets (`originX/originY`) for the movable Spotify window |

Roughly half the machine is generic math/state (~70 lines); the other half is Spotify action
dispatch and renderer calls. WebRadio's row-tap semantics are also structurally different:
synchronous local `_play(idx)` vs Spotify's async enqueue + optimistic highlight.

---

## Goals

1. Drag in the WebRadio PLEDIT content area scrolls the station list live — same
   velocity-joystick feel as Spotify (ADR-030 semantics, same constants).
2. Tap still plays the row — with the same dead-zone + elapsed-time discrimination as
   Spotify, killing the swipe-plays-wrong-station failure mode.
3. Scrollbar column direct-drag works (parity with `D_PLEDIT_SCROLL_DIRECT`).
4. **Zero change to the Spotify *gesture logic*** (`winampDisplay.h` machine untouched).
   The injection-path reroute (§Serial debug #1) sits under every T155–T161 drag test, so
   the T155–T161 re-run is a **mandatory gate, not a formality** [QM-1-1].
5. Harness-drivable: injected drags must exercise the WebRadio path; scroll state observable
   via `dbgGet`.
6. Auto-follow (`_play()` keep-visible) coexists with user scrolling without fighting.

Non-goals: fling momentum (Phase 2 of ADR-030, still deferred); scroll in other list apps
(none exist — Stock/Teletext have their own paging models).

---

## Design space

### Option A — extract a shared gesture component (`app/src/touch/listScroll.h`)

Pull the generic column of the table above into a `ListScrollGesture` struct
(press/move/release + `tick(dt)` + direct-drag mapping; callbacks or return-codes for
"offset changed" and "tap on row N"). Both `winampDisplay` and `WebRadioApp` instantiate it.

- **RAM/flash:** ~30 B state per instance; flash neutral-to-negative (dedup).
- **Regression risk: the killer.** Spotify's shipped machine must be refactored onto the
  component. T155–T161 (+ the TASK-078/ADR-030 correction subtleties: elapsed-time arm,
  quick-swipe min-delta, at-limit release defect) were validated against the *current*
  byte layout of that logic. Extraction forces full VE re-run and re-tuning risk for a
  feature with exactly two consumers.
- **Tap semantics still diverge** (async enqueue vs sync `_play`), so the component ends up
  callback-parameterised — the shared core shrinks to the ~45 lines of integrator + tap math.

### Option B — route WebRadio input through `winampDisplay`'s existing machine

`WebRadioApp::handleInput` forwards PLEDIT-region input to a new
`winampDisplay.handlePleditInput(phase, x, y, dataSource)` where the data source abstracts
row count / scroll offset / tap action.

- **State collision:** `scrollOffset`, `lastCount`, `lastVisibleRows`, `_pleditScrollDirty`
  inside `winampDisplay` are *Spotify's list state* (seqno-cancelled by `drawPlaylist()`).
  WebRadio has its own `_scrollOffset`/`_stationCount`. Sharing the machine means either
  swapping state on app switch (fragile) or indirecting every access through the data
  source — i.e. Option A's refactor, but leaving the result inside the already-large
  `winampDisplay` god-object and *still* touching the validated path.
- **Mode conditionals** would leak into the Release handler (enqueue vs `_play`). Worst of
  both worlds. Rejected on inspection.

### Option C — self-contained gesture in `webRadioApp.h`, pattern-copied, constants shared ← lean

Replicate the ADR-030 gesture *pattern* inside `WebRadioApp` (~80 lines): a private
3-state enum (`WRS_IDLE / WRS_SCROLL / WRS_SCROLL_DIRECT`), press-anchor members, a
`_tickScroll(dt)` integrator identical in form to `winampDisplay.h:532-553` but clamping
against `_stationCount`, Release tap-vs-scroll using the same discrimination, and the
`updateScrollDirect` mapping for the scrollbar column. Tuning constants
(`SCROLL_DEAD_ZONE_PX`, `SCROLL_SPEED_K_DEFAULT`, `PLEDIT_TAP_PX`, `PLEDIT_TAP_MS`) move to
a small shared header (e.g. `app/src/touch/scrollTuning.h`) consumed by both files so
calibration stays single-source; `winampDisplay` includes it with zero behavioural change
(same values, now named once).

- **Regression risk to Spotify: none.** `winampDisplay.h` gesture logic untouched (only the
  constants' definition site moves — compile-time identical values).
- **Duplication cost:** ~45 lines of integrator/discrimination math duplicated. Bounded and
  visible; both sites reference ADR-030. Promotion path: if a *third* scrolling list ever
  appears, execute Option A then (three consumers justify the extraction + re-validation).
- **Fits the app model:** WebRadio already owns its tick (`tick()` calls
  `winampDisplay.tickMarquee()` the same way — precedent for app-owned per-frame work).
- **Repaint cost:** scroll steps trigger `_drawPledit()` row redraw (5× fillRect + Font-1
  text ≈ 5–8 ms, same budget as Spotify's `drawPlaylist()` — acceptable per M-LIST-v4 §Open
  questions #3). Thumb-only fast path optional later.

---

## Lean / decision

**Option C.** Self-contained velocity-scroll gesture inside `WebRadioApp`, semantics and
constants identical to ADR-030, constants hoisted to a shared tuning header. Option A is
the documented promotion path on a third consumer; Option B rejected (state collision).

Rationale: the DUT-validated Spotify path (T155–T161) is untouchable for a UX-parity
feature; the honestly-shareable core is only ~45 lines once Spotify-coupled action code is
excluded; and WebRadio's synchronous `_play` tap semantics differ enough that a shared
component degenerates into callback plumbing. Consistency of *feel* is preserved by sharing
the model and the tuning values, not the code.

---

## Gesture spec (deltas from ADR-030 only)

- **Regions** (raw screen coords — WebRadio window is not movable, no origin offsets):
  - Content rows: `x ∈ [PLEDIT_CONTENT_X, PLEDIT_CONTENT_X+PLEDIT_CONTENT_W)`,
    `y ∈ [PLEDIT_ROWS_Y, PLEDIT_ROWS_Y + 5·PLEDIT_ROW_H)` → `WRS_SCROLL` on Press.
  - Scrollbar column: `x ∈ [PLEDIT_CONTENT_X+PLEDIT_CONTENT_W, PLEDIT_W)` same y-band →
    `WRS_SCROLL_DIRECT`, positional mapping as `updateScrollDirect` with
    `maxOffset = max(0, _stationCount - PLEDIT_ROW_COUNT)`.
- **Release tap** (`|dy| < PLEDIT_TAP_PX && elapsed < PLEDIT_TAP_MS`): `_play(_scrollOffset
  at press + row)` — clamp `idx < _stationCount` (rows past end are dead, as today).
  Quick-swipe fallback (min 1 row from start offset) retained verbatim.
- **Tick:** `_tickScroll(dt)` called from `WebRadioApp::tick()` with member-tracked
  `lastScrollMs` (per M-LIST-v4 open-question #1 resolution) — placed **at the top of
  `tick()`, alongside `tickMarquee()`, before the terminal-retry / pending-action dispatch
  block**, so the early `return`s at `webRadioApp.h:248/262` cannot stall a live gesture
  [DEV-1-3]. dt-integration makes the velocity model robust to the degraded loop cadence
  while audio decodes on loopTask (each iteration integrates real elapsed time); if
  M-WR-AUDIO-TASK lands, cadence just improves. Steps mark a row-region-only repaint (not
  `_dirty` full repaint).
- **Auto-follow interplay [QM-1-3 — single rule]:** if `_play()` runs while a gesture is
  active (auto-skip is tick-driven, so this CAN coincide with a finger down), the gesture
  is cancelled first — `WRS_IDLE`, accumulators zeroed — then the keep-visible clamp runs.
  Mirrors M-LIST-v4's seqno-cancel invariant: offset stays consistent with list state; the
  next Press re-anchors.
- **Release capture [DEV-1-1 blocker — replaces the draft's "hit-tests unchanged" bullet]:**
  while `WRS_SCROLL`/`WRS_SCROLL_DIRECT` is active, **Release is consumed by drag-end
  before any eject/transport hit-test** — mirroring the donor machine's captured-gesture
  phase structure (`winampDisplay.h:304-366` release-first, `:370-401` captured
  Press/Move). Otherwise a drag released over eject fires `_stopAudio()` +
  `switchApp(Spotify)`. Eject/transport precedence applies only from `WRS_IDLE`.
- **No-anchor Release [VE-1-2]:** a Release arriving in `WRS_IDLE` (no prior Press —
  exactly how `cmdTap` drives the whole T_WR_* tap surface today) behaves as today's
  tap-at-(x,y) path: eject/transport hit-tests, then PLEDIT row tap. The T_WR_* suite
  passes unchanged (exit criterion below).
- **`suspend()` cancels the gesture [DEV-1-4]:** zero the WRS state + accumulators in
  `suspend()` (precedent: `SpotifyApp::suspend()` → `resetDragState()`, `main.cpp:211-213`);
  serial `switchApp`/`set wrEject` can fire mid-gesture.

## Serial debug / VE surface

1. **Fix drag injection routing (prerequisite for VE) [VE-1-1 blocker + DEV-1-2]:**
   `drainInjectionQueue` (`main.cpp:2289-2334`) hardwires non-taskbar samples to
   `winampDisplay.handleWinampInput` — **and the release sentinel is a separate branch
   hardwired to `handleWinampInput(Release, 0, 0)`** (`main.cpp:2300-2302`). The reroute
   covers **all three phases**: samples dispatch to
   `g_apps[(int)currentAppId]->handleInput(phase, x, y)`, and the release step dispatches
   to the same target **carrying the last sample's coordinates, not (0,0)** — otherwise an
   injected WebRadio drag delivers Press/Move to the new machine and Release to Spotify's,
   and the gesture never ends. Two behaviour deltas, stated for the record: (i) injected
   Releases now pass `SpotifyApp::handleInput`'s eject intercept (`main.cpp:256-260`) —
   last-sample coords make that hit-test evaluate real data; (ii) injected canvas drags now
   reach every app's handler (Stock/Settings/Teletext previously never saw injected
   Press/Move) [VE-1-6] — regression sweep: T155–T161 re-run (the Spotify gate) plus one
   smoke drag per non-player app. Lands as **its own commit** with the T155–T161 +
   T162–T166 sweep, before any of the trio's features [DEV-X-2]. `_injectingDrag`
   suppression stays as-is.
2. **Held-gesture primitive [VE-1-3]:** `cmdDrag` always appends a release sentinel, so
   "auto-skip fires mid-gesture" is not agent-executable. Add `drag x1 y1 x2 y2 steps hold`
   (suppress the sentinel; gesture stays anchored) + a bare `release` command (enqueue the
   release step at last-sample coords). The mid-gesture-cancel exit criterion is asserted
   with `drag … hold` → wait for auto-skip pace → `get wrScroll` shows `drag:0`.
3. **`dbgGet` additions (WebRadio):** `wrScroll` →
   `{"var":"wrScroll","offset":N,"drag":0|1|2,"vel":x.xxxx,"accum":x.xxxx,"last":true}`.
4. **`dbgSet speedK`** already reaches `winampDisplay`; the shared-header constant plus a
   WebRadio-local `_scrollSpeedK` member mirrors the same dbgSet name under the WebRadio
   dbg surface (`wrSpeedK`) for independent calibration.
5. **`tick n dtMs`** (`cmdTick`) must drive the *current app's* scroll tick, not only
   `winampDisplay.tickScroll` — route through app when WebRadio active (small dispatch in
   `cmdTick`). **The reply JSON's `scrollOffset` field is read from
   `winampDisplay.dbgGet` (`main.cpp:2521-2523`) and stays Spotify-only — WebRadio tests
   assert via `get wrScroll` exclusively** [VE-1-5].
6. **VE signs off this dbg surface before implementation (BP-024)** [QM-1-4] — gate
   recorded in the exit criteria.

---

## Open questions

1. **Positional vs velocity for 30 rows** — velocity chosen for parity, but if DUT feel is
   poor at WebRadio's row redraw cost, the positional taskbar model
   (`TB_SCROLL_DEAD_ZONE_PX` + 1:1 steps) is the fallback; decision point at first DUT
   session, `wrSpeedK` tunable without reflash either way. **Feel tuning is scheduled
   after TASK-278 lands (or explicitly re-tuned) — the loop cadence it tunes against is
   about to change** [DEV-X-1].
2. **Row repaint budget while PLAYING** — the per-step cost to measure is **`_drawPledit()`
   whole**: the row loop (5× fillRect + Font-1 text ≈ 5–8 ms, estimate) *plus*
   `drawPleditFrame()` (border tiles + thumb) which it re-runs every call [DEV-1-5].
   Measure via perf path before tuning; a rows+thumb-only step repaint is the fix if the
   frame share is material.
3. **Thumb-only fast path** — `drawScrollThumbOnly` analogue for WebRadio; decide after (2)
   (absorbs the DEV-1-5 frame delta if needed).
4. **At-limit release defect** (M-LIST-v4 §Known limitation VE-C5) — inherited by the copy.
   Default: accept for parity. **On acceptance, the second site is recorded in the
   M-LIST-v4 VE-C5 known-limitation note (owner: VE, at implementation-task close)** — a
   deferred defect needs a named artefact, not prose [QM-1-5].

## Exit criteria (DUT-verifiable)

- Drag in WebRadio PLEDIT rows scrolls the station list live; holding at offset scrolls
  continuously; Release stops. No station starts playing from a scroll gesture — including
  a drag released over eject/transport (Release-capture rule) [DEV-1-1].
- Tap (within dead zone + `PLEDIT_TAP_MS`) plays exactly the tapped row.
- Scrollbar column drag jumps the list positionally (parity with Spotify direct-drag).
- Auto-skip firing mid-gesture cancels the gesture cleanly (asserted via `drag … hold` +
  `get wrScroll` [VE-1-3]); next Press re-anchors.
- `drag x1 y1 x2 y2 steps` via serialdbg exercises the WebRadio path end-to-end (Press
  through Release) when WebRadio is the active app; `get wrScroll` reflects
  offset/drag-state/velocity under `tick n dtMs` **within the T157–T161-precedent
  tolerance bands** (real-tick integration runs concurrently with synthetic ticks — exact
  step counts are not assertable) [VE-1-4].
- Spotify regression gate: T155–T161 pass unchanged (mandatory — the injection reroute
  sits under them [QM-1-1]); one smoke drag per non-player app [VE-1-6]; `./run/check`
  green.
- **T_WR_* tap suite passes unchanged** (no-anchor Release fallback) [VE-1-2].
- VE has signed off the dbg surface (BP-024) before implementation starts [QM-1-4].
- Constants single-sourced: grep shows `SCROLL_DEAD_ZONE_PX`/`SCROLL_SPEED_K_DEFAULT`/
  `PLEDIT_TAP_PX`/`PLEDIT_TAP_MS` defined once (shared header — standalone, includes
  neither consumer; `webRadioApp.h` already includes `winampDisplay.h` [DEV-1-6]),
  consumed by both sites.

---

## Panel dispositions (2026-07-03)

VE / DEV / QM returned **approve-with-changes**; every blocker/major applied in place above.
Reviews: [touch-ux-panel-VE-review.md](touch-ux-panel-VE-review.md) ·
[touch-ux-panel-DEV-review.md](touch-ux-panel-DEV-review.md) ·
[touch-ux-panel-QM-review.md](touch-ux-panel-QM-review.md).

- **VE-1-1 (blocker) + DEV-1-2** (release sentinel hardwired to Spotify at (0,0)) →
  §Serial debug #1: three-phase reroute, Release carries last-sample coords, deltas stated.
- **DEV-1-1 (blocker)** (drag released over eject fires eject) → §Gesture spec
  Release-capture rule; eject/transport precedence only from `WRS_IDLE`.
- **VE-1-2** (anchor-less `cmdTap` Releases) → no-anchor fallback rule + T_WR_* exit gate.
- **VE-1-3** (mid-gesture cancel not agent-executable) → `drag … hold` + `release`
  primitives, §Serial debug #2.
- **QM-1-1** (Goal 4 self-contradiction) → Goal 4 reworded: T155–T161 re-run is a
  mandatory gate.
- **VE-1-4** ("deterministically" overclaims) → tolerance-banded exit criterion.
- **VE-1-5** (`cmdTick` reply reads Spotify state) → reply field documented Spotify-only;
  WebRadio asserts via `get wrScroll`.
- **VE-1-6** (reroute changes dispatch for all apps) → delta stated in #1 + per-app smoke.
- **DEV-1-3/1-4/1-5/1-6** (tick placement / suspend cancel / repaint-cost scope / header
  shape) → folded into §Gesture spec and OQ2.
- **QM-1-3** (rejected reasoning left inline) → auto-follow bullet rewritten as single rule.
- **QM-1-4** (BP-024 dbg-surface sign-off) → gate added (#6 + exit criteria).
- **QM-1-5** (VE-C5 parked as prose) → OQ4 names the artefact + owner.
- **QM-1-2** (roadmap blurb says "extract/reuse", lean is pattern-copy) → roadmap blurb
  reconciled in the disposition commit; TASK-277 body likewise.
- **DEV-X-2** (reroute is harness-wide) → #1: lands as its own commit + sweep, first.
