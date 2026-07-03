# DEV Panel Review — Touch-UX design trio (TASK-277 / TASK-278 / TASK-279)

> Owner: Developer · Date: 2026-07-03 · Reviewed at commit a1cf11c (all three docs Status: draft)
> Scope: IMPLEMENTABILITY + CODE-REALITY review per the M-WIFI-DIAG panel precedent (that doc §7-8).
> Docs: 1 = M-WR-PLEDIT-SCROLL.md · 2 = M-WR-AUDIO-TASK.md · 3 = M-TASKBAR-FEEDBACK.md
> Every code claim was re-verified against the tree independently of the VE review
> (touch-ux-panel-VE-review.md); testability findings there are not repeated — cross-referenced
> where the same code fact drives both. Findings: DEV-<doc>-<n>, blocker / major / minor, one-line
> resolution each. Architect dispositions.

---

## Code-claim verification (additional to VE's table; all checked in tree)

- I concur with the VE review's verification table (line refs for `handleInput`, `tickScroll`,
  `updateScrollDirect`, constants, `drainInjectionQueue`, `cmdTick`, switch anatomy, cooldown
  dispatch order, `cmdTap` divergence — all accurate).
- Doc 1 extras verified: the gesture-state members WebRadio needs already exist and fit
  (`_scrollOffset` is `int`, `_stationCount`/`_currentIdx` `uint8_t`, `webRadioApp.h:661-698`);
  `WR_MAX_STATIONS = 30` (`dataTask.h:66`); `PLEDIT_ROW_COUNT = 5`, rows band y136..201
  (`gen/skin_layout.h:164-175`); quick-swipe min-1-row fallback exists verbatim
  (`winampDisplay.h:333-341`); `dbgSet speedK` exists (`winampDisplay.h:1020-1023`);
  `originX/originY` are 0 for the shell chrome (`winampDisplay.h:51-52`) so raw-coords claim holds.
- Doc 2 extras verified: vendored fork is v2.3.0 (`app/lib/ESP32-audioI2S/library.json`); **no**
  internal locking anywhere in `Audio.cpp` (no semaphore/critical-section hits — claim confirmed);
  PATCH-MEMBUDGET-4 halves the DMA ring under `MEMBUDGET_PHASE1` (`Audio.cpp:187-196`) and
  `MEMBUDGET_PHASE1` **is** in the production env (`app/platformio.ini:63-76`, TASK-262) — the
  design is right; note the `Audio.cpp:192` comment still says "experiment-only", which is stale
  (DEV-2-7). `connecttohost()` blocks (DNS + TCP + request write, `Audio.cpp:391+`) and — key —
  is also called **from inside `Audio::loop()`** (DEV-2-1). ICY producer comment cited at
  `webRadioApp.h:80` ✓; `audio_info` → `LOG_I` at `:98-101` ✓.
- Doc 3 extras verified: taskbar geometry 45 px × 6 slots × 40 px (`gen/shell_layout.h:7-9`),
  icons baked 24×24 (`gen/taskbar_icons.h:7`); `TASKBAR_BUSY_COLOR`/`TASKBAR_ERR_COLOR` are
  firmware-only `#define`s in `taskbar.h:13-19` (golden-hash rule matches ADR-046 precedent);
  `renderActiveIndicator` precedence error > busy|connecting > idle (`taskbar.h:46-49`);
  `switchApp`'s final `renderTaskbar` at `main.cpp:1856-1857` does overwrite a transient amber.
- Perf reality (feeds DEV-3-5 / VE-2-3): production `perf::record` sites are exactly 5 —
  `spotify.poll` (`main.cpp:250`), `display.bar` (`:252`), `display.input` (`:2916`), `app.tick`
  (`:2920`), `vu.tick` (`vuMeter.h:428`) — plus `screenlog.tick` under SCREEN_LOG only (`:2907`).
  `MAX_PATHS = 8`, overflow silently drops (`perf.h:28, 50-52`).

---

## Doc 1 — M-WR-PLEDIT-SCROLL (TASK-277)

The Option C analysis is code-accurate: the generic/Spotify-coupled split of
`winampDisplay.h:302-553` is honest, Option B's state-collision rejection matches the real
member layout (`scrollOffset`/`lastCount` are Spotify's, seqno-cancelled in `drawPlaylist()`),
and WebRadio owns everything the copied machine needs. One spec error would ship a wrong
behaviour if implemented verbatim:

### DEV-1-1 (blocker) — Release-during-gesture is NOT captured; the spec's "hit-tests ordered before the region check as today" ships an eject/transport misfire

The gesture spec asserts transport/eject precedence "unchanged — those hit-tests run before the
PLEDIT region check in `handleInput`". Today that is safe because Press/Move are discarded
(`webRadioApp.h:390-391`); once Press anchors a gesture, a real-finger drag that starts in the
rows and ends with the finger over a hit zone delivers Release at that point — and
`WebRadioApp::handleInput` runs eject/transport hit-tests first (`webRadioApp.h:394-411`), so a
scroll gesture can end in `_stopAudio()` + `switchApp(Spotify)` (eject) or a station change
(PREV/NEXT). The donor machine avoids exactly this with its captured-gesture phase: on Release
it services drag-end **before** any hit-test and returns (`winampDisplay.h:304-366`), and on
Press/Move it routes captured gestures before hit-tests (`:370-401`). The copy must copy that
structure, not just the integrator. (VE-1-1 hits the same code fact from the injection side;
this is the production-path half.)
**Resolution:** amend the gesture spec: while `WRS_SCROLL`/`WRS_SCROLL_DIRECT` is active,
Release is consumed by drag-end before eject/transport hit-tests (mirror `winampDisplay.h`
phase structure); eject/transport precedence applies only from `WRS_IDLE`.

### DEV-1-2 (major) — the injection-reroute prerequisite is under-specified on the Release step and changes dispatch for every app

The doc's fix #1 reroutes non-taskbar **samples** (`main.cpp:2322-2327`) but the release
sentinel is a separate branch hardwired to `handleWinampInput(Release, 0, 0)` (`main.cpp:2301`)
— with zero coords (see VE-1-1 for the test-side consequence). Additionally, routing through
`g_apps[(int)currentAppId]->handleInput` makes the "Spotify behaviour identical" claim only
*nearly* true: `SpotifyApp::handleInput` adds the eject intercept before `handleWinampInput`
(`main.cpp:256-260`), so an injected Release must carry last-sample coords (not (0,0)) or the
eject hit-test evaluates garbage; and injected canvas drags now reach Stock/Settings/Teletext
handlers that never saw Press/Move injection before (VE-1-6).
**Resolution:** spec the reroute as: all three phases dispatch to the active app, Release
carries the last sample's coordinates; state the eject-intercept delta explicitly in the doc.

### DEV-1-3 (minor) — `_tickScroll` placement vs `tick()` early returns

`WebRadioApp::tick()` returns early on terminal-retry re-arm and pending-action dispatch
(`webRadioApp.h:248, 262`); a `_tickScroll` placed with the other per-frame work stalls one
tick when those fire mid-gesture (and the gesture-cancel rule fires `_play()` in the same
tick).
**Resolution:** call `_tickScroll(dt)` at the top of `tick()` (with `tickMarquee`), before the
retry/skip dispatch block.

### DEV-1-4 (minor) — `suspend()` must cancel the gesture

Serial `switchApp`/`set wrEject` can fire mid-gesture; `SpotifyApp::suspend()` has the
precedent (`resetDragState()`, `main.cpp:211-213`) but `WebRadioApp::suspend()`
(`webRadioApp.h:204-217`) has no gesture state to clear today and the design adds some.
**Resolution:** zero the WRS state + accumulators in `suspend()`.

### DEV-1-5 (minor) — step-repaint cost quote omits the frame

"5× fillRect + Font-1 text ≈ 5-8 ms" describes the row loop, but `_drawPledit()` also re-runs
`drawPleditFrame()` (border tiles + scrollbar thumb, `webRadioApp.h:936`) every call — the
per-step number OQ2 will measure is _drawPledit as-is, not rows-only.
**Resolution:** either measure `_drawPledit()` whole in OQ2 (and let OQ3's thumb-only fast
path absorb the delta) or spec a rows+thumb-only step repaint from the start.

### DEV-1-6 (minor) — shared tuning header: watch the include shape

The four constants are currently `private: static constexpr` members of `WinampDisplay`
(`winampDisplay.h:621-624`); hoisting to `app/src/touch/scrollTuning.h` is compile-identical
as claimed, but the header must be standalone (no includes of either consumer —
`webRadioApp.h` already includes `winampDisplay.h`) and `_scrollSpeedK`'s member init keeps
reading the shared `SCROLL_SPEED_K_DEFAULT`.
**Resolution:** constants-only header, both consumers include it; grep exit-criterion already
covers single-sourcing.

**Doc 1 verdict: approve-with-changes** — DEV-1-1 must be folded into the gesture spec before
implementation; everything else is the right shape and the machine fits the app's real state.

---

## Doc 2 — M-WR-AUDIO-TASK (TASK-278)

Core topology, lifecycle binding to `suspend()`, the JIT-arena teardown order, and the
no-internal-locking claim all check out. Option (a) over (b)/(c) is well-argued and the
Phase-1/Phase-2 severance is the correct protection for the freshly validated ADR-045/TASK-276
machine. Two majors are about premises the code contradicts:

### DEV-2-1 (major) — "the pump's per-call work is short" is false on three real paths: `Audio::loop()` calls `connecttohost()` internally

`loop()` re-enters the blocking connect path on: playlist-format resolution
(`connecttohost(parsePlaylist_M3U/PLS/ASX())`, `Audio.cpp:2450-2452` — .pls/.m3u station URLs
exist in radio-browser data), HTTP 3xx redirect during header parse (`Audio.cpp:3587` — the
header is parsed in `loop()`, *after* `_play()`'s connect returned true and set PLAYING), and
lost-stream reconnect (`lostStreamDetection` → `connecttohost(m_lastHost)`, `Audio.cpp:5255`).
On any of these the pump holds the Phase-1 mutex through a multi-second DNS+TCP window: the
tick-side read cluster, `_stopAudio()` (eject/STOP), and the suspend handshake all block
loopTask for that window — the UI freeze returns exactly on redirects and stream drops, and
teardown latency is bounded by worst-case `loop()`, not by "one decode chunk". No deadlock
(lock ordering is acyclic; FreeRTOS mutex priority inheritance covers the inversion), but the
design's latency-shape rationale for prio 2 does not hold on these paths.
**Resolution:** amend the locking model: tick-side reads use `xSemaphoreTake` with 0/short
timeout falling back to the last snapshot; document the stop/suspend worst-case bound and add
it to the E-criteria (measure a forced redirect + a stream-kill); optionally note the fork
patch (suppress in-`loop()` reconnect) as the Phase-2-adjacent fix — BP-042 freeze makes the
documented bound the Phase-1 cut.

### DEV-2-2 (major) — E3's regression evidence exercises zero pump/mutex code: `wrDeadUrls` short-circuits before any Audio call

`_debugForceConnFail` returns from `_play()` **before** `tlsYield`, arena acquire, Audio
construction, or `connecttohost` (`webRadioApp.h:741-747`). The `set wrDeadUrls 3` auto-skip
bound and TASK-276 terminal-retry re-runs in E3 therefore validate pacing/state-machine
semantics but touch none of the new task/mutex/lifecycle code; only the ADR-045 instrumented
gate re-run (real streams) does. The pump-vs-TASK-218 interaction (in-library
`lostStreamDetection` reconnect racing the debounce, DEV-2-1's third path) is untested by
anything listed.
**Resolution:** add a real-stream death case to E3 — `set wrUrl http://host:port/mount`
against a local source, kill it mid-play (TASK-261 pattern), assert debounce → `_stopAudio` →
retry under the mutex; keep wrDeadUrls for the pacing half. (VE-2-6 covers the RF-environment
half of E3.)

### DEV-2-3 (minor) — pump-task create order vs the arena window

"Create lazily at first `_play()` (alongside the JIT arena acquire)": an 8 KB contiguous
stack allocated *before* `mb_arena_acquire()` bites into the same lfbInt window E4 checks
(`≥ 24 K` at CP1).
**Resolution:** fix the order in the doc — arena acquire first, then task create — and note
the task stack in the CP1 budget line.

### DEV-2-4 (minor) — `set wrVol` lazily constructs Audio outside the guarded lifecycle

`wrAudio()` news up the object on first use (`webRadioApp.h:132-138`) and the `wrVol` setter
calls it (`:616-623`) — under the pump design that creates an Audio with no task, no mutex
discipline, and no arena.
**Resolution:** make `wrVol` no-op (or clamp-store) when `!s_wr_audio`; all creation goes
through `_play()`.

### DEV-2-5 (minor) — OQ2 is answerable from the tree today: logSink is safe

The ring append is guarded by `portENTER_CRITICAL_SAFE(&g_mux)` (`logSink.h:33-67`) — a
spinlock, correct for a prio-2 core-1 writer preempting loopTask mid-append.
**Resolution:** close OQ2 with that citation; the residual risk is Serial line interleaving,
which VE-2-7's torn-line grep covers.

### DEV-2-6 (minor) — suspend-handshake ack point is ambiguous as worded

"Pump acknowledges at the top of its cycle, outside `Audio::loop()`" permits ack-then-retake:
the pump could ack and re-enter the mutex/loop before loopTask runs `vTaskDelete`.
**Resolution:** spec it as ack-then-park (pump gives the ack semaphore while holding no locks,
then blocks forever on a kill event; delete happens against a parked task).

### DEV-2-7 (minor) — stale fork comment contradicts the (correct) design claim

`Audio.cpp:192` still says PATCH-MEMBUDGET-4 is "experiment-only — production keeps 16/512";
`MEMBUDGET_PHASE1` has been in the production env since TASK-262 (`platformio.ini:63-76`).
**Resolution:** fix the comment when the file is next touched; the design doc needs no change.

### DEV-2-8 (minor) — cross-task `perf::record` has a registration race, not just torn reads

Slot claim is a non-atomic two-field write (`perf.h:40-49`) racing loopTask registrations and
heartbeat's `perf::reset()`; OQ3 names torn reads only. Diagnostic-grade, but worth naming.
**Resolution:** fold into OQ3: accept as diagnostic noise or gate `wr.pump` behind
SERIAL_DEBUG; adopt VE-2-3's `MAX_PATHS` bump regardless (see cross-doc below).

**Doc 2 verdict: approve-with-changes** — Option (a) stands; the Phase-1 locking model text
must absorb DEV-2-1 (timeout reads + measured teardown bound) and E3 must absorb DEV-2-2
before implementation.

---

## Doc 3 — M-TASKBAR-FEEDBACK (TASK-279)

The cooldown correction is verified against the real dispatch order and is worth keeping on
the record; the F-c + L-a + L-d lean matches the code's constraints. The two majors are API/
anchoring gaps the implementation hits on day one:

### DEV-3-1 (major) — "cancel highlight on scroll-start" has no shell-visible signal today

`_tbIsScrolling` is private (`winampDisplay.h:631`) and `tbGestureContinue()` returns true
only when the offset actually steps ≥1 slot (`winampDisplay.h:73-88`) — dead-zone-exceeded
with sub-slot travel produces no observable event, so the highlight lingers through the start
of every slow scroll and the F-a restore trigger (1) cannot be implemented as specced.
**Resolution:** add a `tbIsScrolling()` accessor (or make `tbGestureContinue` return an enum
{none, scrollStarted, stepped}); one-line change, but it belongs in the design's interface
list.

### DEV-3-2 (major) — highlighted slot and committed slot can differ: press-y vs release-y anchoring

F-a computes the highlight from press y (`slot = y / TASKBAR_SLOT_H`), but the tap commit
resolves from `s_lastTouchY` at release (`tbGestureEnd(s_lastTouchY, …)`, `main.cpp:1915`,
`winampDisplay.h:97`). Within the 3 px dead zone the finger can cross a slot boundary —
highlight slot A, switch to slot B, on a resistive panel that jitters by design. Latent
production quirk today; the highlight makes it user-visible.
**Resolution:** resolve the tap from the press-anchored slot (capture it in `tbGesturePress`)
— fixes the latent quirk and guarantees highlight == commit; note it touches T162-T166's
assumptions (VE owns the re-check).

### DEV-3-3 (minor) — pressed-slot repaint must reproduce the full slot body

The "parameterised single-slot variant of the renderTaskbar loop body" must include the
separator line (`taskbar.h:72-73`), and — when the pressed slot is the active slot — the 3 px
indicator with ADR-046 precedence (error > busy|connecting > idle), or pressing the active
slot visibly eats the indicator for the press duration.
**Resolution:** name the indicator + separator in the F-a paint spec; the restore paint is the
same helper.

### DEV-3-4 (minor) — icon bake constrains the "brightened bg" treatment

Icons are opaque 24×24 RGB565 baked over `TASKBAR_BG` (`gen/taskbar_icons.h`); re-blitting one
onto a brightened slot leaves a dark icon-sized square inside the highlight. OQ1 already defers
the visual pick but doesn't name this constraint.
**Resolution:** add the bake constraint to OQ1 — edge-bar/white-frame treatments are free;
full-slot tint needs re-baked pressed icons (golden-hash impact: none, icons are a separate
gen artifact, but bake step required).

### DEV-3-5 (minor) — perf path count is wrong (5 production, not 6); combined trio hits MAX_PATHS

`screenlog.tick` is SCREEN_LOG-gated (`main.cpp:2906-2908`); production paths are 5, so
`shell.switch` alone is fine — but with doc 2's `wr.pump` + `wr.connect` the trio lands at 8
production = `MAX_PATHS` exactly and 9 under SCREEN_LOG, where `perf::record` drops silently
(`perf.h:50-52`).
**Resolution:** correct the count in L-d; adopt VE-2-3's `MAX_PATHS` bump (10) in whichever
task lands first — concur with VE-2-3, this is the same finding from the code side.

### DEV-3-6 (minor) — press feedback has two production call sites; hoist one helper

`tbGesturePress` is called from `appHandleInput` (`main.cpp:1880`) *and* `drainInjectionQueue`
(`:2315-2316`); the F-a paint + log must live in one shell helper used by both or the injected
path (which the measurement plan depends on) drifts — concur with VE-3-1, which specs the
helper; flagging here because the amber commit paint (F-b) has the same two-site shape on the
release side (`main.cpp:1917` and `:2294-2296`).
**Resolution:** as VE-3-1, and extend the same helper rule to the F-b commit paint.

**Doc 3 verdict: approve-with-changes** — the lean survives; DEV-3-1/3-2 are small code
changes but must be in the design's interface spec, not discovered mid-implementation.

---

## Cross-doc sequencing (implementation order)

- **DEV-X-1 (major) — shared-baseline ordering.** Doc 3's measurement matrix row "WebRadio
  PLAYING" and doc 2's E0 measure the same quantity (`hb` loopMax + drain rate under decode
  load) and both docs demand baseline-before-change. Land order that avoids double work and
  confounds: (1) doc 3's L-d instrumentation + doc 2's E0 in **one DUT session** (shared
  baseline tables, cross-filed in both docs); (2) TASK-278 Phase 1; (3) TASK-277 — its
  `wrSpeedK`/feel tuning (doc 1 OQ1/OQ2) must be scheduled **after** 278 lands, or explicitly
  re-tuned, since the loop cadence it tunes against is about to change; (4) doc 3's feedback
  blits any time (independent). VE-3-2's re-baseline rule is the enforcement mechanism —
  concur.
  **Resolution:** PM encodes this order in tasks.md; doc 1 notes "tune after TASK-278" in OQ1.
- **DEV-X-2 (note, no action)** — doc 1's drainInjectionQueue reroute (its fix #1) is a
  harness-wide change that docs 2 and 3 both lean on for evidence (drag-drain rate in E1,
  taskbar drag-taps in the matrix); it should land as its own commit with the T155-T161 +
  T162-T166 sweep, before any of the three features, so injection-path regressions are
  attributable.
- SPI-bus worry checked and dismissed: decode feeds I2S DMA, not the TFT SPI bus — a prio-2
  pump preempting a scroll repaint stretches its wall-clock but there is no bus-level
  contention between doc 1's step repaints and doc 2's pump.

---

## Verdict summary

| Doc | Verdict | Blockers | Majors |
|---|---|---|---|
| 1 — M-WR-PLEDIT-SCROLL | **approve-with-changes** | DEV-1-1 | DEV-1-2 |
| 2 — M-WR-AUDIO-TASK | **approve-with-changes** | — | DEV-2-1, DEV-2-2 |
| 3 — M-TASKBAR-FEEDBACK | **approve-with-changes** | — | DEV-3-1, DEV-3-2 (+ DEV-X-1 cross-doc) |
