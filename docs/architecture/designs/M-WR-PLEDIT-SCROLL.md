# Design — WebRadio PLEDIT drag/velocity scroll (M-WR-PLEDIT-SCROLL)

> Owner: Architect
> Status: draft
> Date: 2026-07-02
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
4. **Zero change** to the DUT-validated Spotify gesture path (VE T155–T161 must stay green
   without re-validation being load-bearing).
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
  `lastScrollMs` (per M-LIST-v4 open-question #1 resolution). dt-integration makes the
  velocity model robust to the degraded loop cadence while audio decodes on loopTask
  (each iteration integrates real elapsed time); if M-WR-AUDIO-TASK lands, cadence just
  improves. Steps mark a row-region-only repaint (not `_dirty` full repaint).
- **Auto-follow interplay:** `_play()` keep-visible clamp runs *after* a tap (desired) and
  on auto-skip. Rule: auto-follow never fires mid-gesture — guard the `_play()` clamp with
  `state == WRS_IDLE` skip is unnecessary since `_play` from auto-skip can't coincide with
  a finger down on rows... it can (auto-skip is tick-driven). Guard: if a gesture is
  active, cancel it (`WRS_IDLE`, zero accumulators) before the clamp — mirrors M-LIST-v4's
  seqno-cancel invariant (offset consistent with list state, next Press re-anchors).
- **Transport/eject precedence:** unchanged — those hit-tests run before the PLEDIT region
  check in `handleInput`, and Press/Move now returning `true` for PLEDIT gestures must not
  swallow transport taps (transport stays Release-based in WebRadio; hit-tests ordered
  before the region check as today).

## Serial debug / VE surface

1. **Fix drag injection routing (prerequisite for VE):** `drainInjectionQueue`
   (`main.cpp:2289-2334`) hardwires non-taskbar samples to
   `winampDisplay.handleWinampInput`. Change to
   `g_apps[(int)currentAppId]->handleInput(phase, x, y)` — production-faithful dispatch;
   Spotify behaviour identical (`SpotifyApp::handleInput` → `handleWinampInput`,
   `main.cpp:254-261`), and existing Spotify drag tests remain valid. `_injectingDrag`
   suppression stays as-is.
2. **`dbgGet` additions (WebRadio):** `wrScroll` →
   `{"var":"wrScroll","offset":N,"drag":0|1|2,"vel":x.xxxx,"accum":x.xxxx,"last":true}`.
3. **`dbgSet speedK`** already reaches `winampDisplay`; the shared-header constant plus a
   WebRadio-local `_scrollSpeedK` member mirrors the same dbgSet name under the WebRadio
   dbg surface (`wrSpeedK`) for independent calibration.
4. **`tick n dtMs`** (`cmdTick`) must drive the *current app's* scroll tick, not only
   `winampDisplay.tickScroll` — route through app when WebRadio active (small dispatch in
   `cmdTick`).

---

## Open questions

1. **Positional vs velocity for 30 rows** — velocity chosen for parity, but if DUT feel is
   poor at WebRadio's row redraw cost, the positional taskbar model
   (`TB_SCROLL_DEAD_ZONE_PX` + 1:1 steps) is the fallback; decision point at first DUT
   session, `wrSpeedK` tunable without reflash either way.
2. **Row repaint budget while PLAYING** — 5–8 ms per scroll step on top of audio servicing
   in the same loop; acceptable on paper, needs one measurement (perf path
   `display.input` / `app.tick` in heartbeat) before tuning.
3. **Thumb-only fast path** — `_drawPledit()` redraws frame + rows every step; a
   `drawScrollThumbOnly` analogue for WebRadio is an optimisation, decide after (2).
4. **At-limit release defect** (M-LIST-v4 §Known limitation VE-C5) — inherited by the copy.
   Accept for parity or fix in both? Default: accept, document.

## Exit criteria (DUT-verifiable)

- Drag in WebRadio PLEDIT rows scrolls the station list live; holding at offset scrolls
  continuously; Release stops. No station starts playing from a scroll gesture.
- Tap (within dead zone + `PLEDIT_TAP_MS`) plays exactly the tapped row.
- Scrollbar column drag jumps the list positionally (parity with Spotify direct-drag).
- Auto-skip firing mid-gesture cancels the gesture cleanly; next Press re-anchors.
- `drag x1 y1 x2 y2 steps` via serialdbg exercises the WebRadio path when WebRadio is the
  active app; `get wrScroll` reflects offset/drag-state/velocity deterministically with
  `tick n dtMs`.
- Spotify regression gate: T155–T161 pass unchanged; `./run/check` green.
- Constants single-sourced: grep shows `SCROLL_DEAD_ZONE_PX`/`SCROLL_SPEED_K_DEFAULT`/
  `PLEDIT_TAP_PX`/`PLEDIT_TAP_MS` defined once (shared header), consumed by both sites.
