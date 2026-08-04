# Design — moving WebRadio's `connecttohost()` off loopTask (TASK-398)

> Owner: Architect
> Status: accepted (lean) — human-approved 2026-08-04. Two VE passes same day: first found 4
> blocking findings against the original two-requirement sketch (addressed, but incompletely);
> second found the fix itself was incomplete (`_stopAudio()`, not just `_play()`, was the real
> blocking primitive; the flag-only teardown left a permanent state wedge, not just a race) — 4 new
> blocking findings. This revision replaces the ad-hoc flags with an explicit request/result-slot
> mechanism between `loopTask` and the pump task, fixing `_stopAudio()` at the primitive (which
> transitively covers `suspend()` and a seventh call site neither VE pass had enumerated) and giving
> `tick()` an unconditional per-iteration reconciliation poll. **Not yet re-reviewed — a third VE
> pass is next, not implementation.**
> Date: 2026-08-04
> Feeds: (ADR TBD — promote once VE review + implementation lands)
> Tracked-as: TASK-398
> Registers: — (no new feature id; a `cross_feature_matrix.yaml` edge for the pump-task/
> control-call interaction should be reserved at implementation time — not done yet, flagged
> rather than skipped silently)

## Context / pain points

TASK-393's Spotify-present 4h soak measured what `M-WR-AUDIO-TASK.md`'s OQ4 had left an open
question since TASK-278 was accepted (2026-07-03): `_play()`'s `connecttohost()` call
(`webRadioApp.h:1690-1694`) runs synchronously on `loopTask` — the main app-dispatch loop that also
owns touch sampling, rendering, taskbar, and every other app — and blocks it for **7-9+ seconds on
every failed connect attempt**. Under Spotify-concurrent conditions that was 421 separate
whole-device freezes over 4 hours, roughly one every ~34s. TASK-278's own Phase 1 deliberately left
this out of scope ("Phase 1 deliberately leaves connect blocking"), and sketched a Phase 2
(pump-task-owns-Audio, full command-queue) as the fix, explicitly deferred as "real surgery on the
freshly validated ADR-045/TASK-276 machine," gated on measuring the freeze magnitude first. That
measurement now exists (see TASK-393, `M-WR-AUDIO-TASK.md` OQ4).

TASK-398 asked the Architect to assess whether a **narrower** mitigation — just move the
`connecttohost()` call itself onto the existing pump task, without the full command-queue
rearchitecture — gets most of the benefit at a fraction of the risk. This doc is that assessment.
**Short answer: the narrow mitigation is real and worth doing, but it is not actually narrow once
followed through — every other control path that can fire while a connect is in flight
(`_stopAudio()`, `suspend()`/eject, skip) currently takes the same `s_wrAudioMutex` with a blocking,
unbounded `xSemaphoreTake`, so simply relocating `connecttohost()` to the pump task would just
relocate the freeze to whichever of those fires next, not eliminate it.** This was not obvious
until tracing the actual call sites — worth recording here so the next person doesn't have to
re-derive it.

## Goals

1. Eliminate (or bound to something small and predictable) the whole-device freeze during a
   WebRadio connect attempt — the actual, now-measured problem.
2. Do not silently reintroduce the same freeze via mutex contention on a different control path
   (`_stopAudio`/`suspend`/skip) that happens to fire while a connect is in flight.
3. Minimize surgery on the ADR-045/TASK-276 terminal-retry state machine, which is freshly
   validated and this session's whole investigation is *about* WebRadio reliability — breaking it
   while fixing this would be a bad trade.
4. Prefer a design that degrades safely under the worst-case conditions already observed tonight
   (near-100% connect failure, sustained for hours) rather than one that's only been reasoned about
   under the healthy case.

## Design space (options + tradeoffs)

**Option A — do nothing.** TWDT has survived 421 consecutive occurrences without a reboot; the
symptom is "annoying and looks broken," not a crash. Free, but leaves a real, now-quantified,
user-visible defect in place, and the original human sighting this whole thread traces back to
may partly *be* this (unconfirmed — TASK-393's own render-freeze detector and this finding measure
different things).

**Option B — narrow async connect (this doc's actual subject).** Move only the `connecttohost()`
call onto the pump task; `_play()` on `loopTask` becomes a fast, non-blocking "kick off" that sets
`_state = CONNECTING` and posts a request; `tick()` polls a result slot each iteration instead of
blocking on the call.

**Revised 2026-08-04 after VE's first pass — three mandatory requirements, not two (superseded
below, kept for history): a `_play()`-only re-entrancy guard, and moving delete-ownership off a
fixed timeout via a pending-teardown flag.**

**Revised again 2026-08-04 after VE's second pass — that revision didn't actually work.** The
second pass traced the fix through to `_stopAudio()` (the real blocking primitive in 5+ of the
named call sites, including `suspend()`'s own first line) and to what happens on WebRadio re-entry,
and found the flag-only mechanism traded a use-after-free for a *deterministic permanent wedge*
(any single eject during `CONNECTING` leaves `_state` stuck there forever, since nothing but
`_stopAudio()`'s own `_state = STOPPED` line — which the fix had to stop calling — ever clears it).
**This revision replaces the flag-based sketch with the request/result-slot mechanism the doc's own
opening paragraph always gestured at ("`tick()` polls a result slot") but never actually specified**
— second-pass non-blocking finding #6 called this out directly, and closing it turns out to be what
actually fixes findings #1-#5 together, not a separate nice-to-have.

**The mechanism, specified properly this time:**

Two new file-static, `volatile`-qualified values (single-word, same atomicity precedent this file
already relies on for `s_wrPumpTask`/`s_wrPumpStopReq` — no new mutex):
- `s_wrPumpRequest : { NONE, CONNECT, ABORT, TEARDOWN }` — written by `loopTask`, read/cleared by
  the pump task.
- `s_wrPumpResult : { NONE, CONNECTED, FAILED, ABORTED, TORN_DOWN }` — written by the pump task once
  its blocking call returns, read/cleared by `tick()`'s poll.

**Producer side (`loopTask`, all fast, none of these block):**
- `_play()`: unchanged guard from the first revision — no-op if `_state == CONNECTING` already.
  Otherwise sets `_state = CONNECTING`, posts `s_wrPumpRequest = CONNECT` (station URL already
  reachable via existing station-list state, no separate payload needed), returns.
- `_stopAudio()` **(the actual fix for VE findings #1 and #2, fixed once, at the primitive, not at
  each of its 6 call sites individually)**: gains a branch at the top — `if (_state ==
  WRPlayState::CONNECTING) { s_wrPumpRequest = ABORT; return; }` — skipping the mutex take and
  `stopSong()` call entirely (nothing is playing yet at the codec level; there's nothing to stop).
  Every existing behavior for every *other* state (`PLAYING`, `ERROR_*`, etc.) is unchanged — this
  narrowly targets the one state where blocking is unsafe. Because every caller VE traced (eject,
  STOP, `_togglePlay()`'s stop branch, `dbgSet`'s `wrEject`/`wrStop`, **and** a seventh call site —
  found while re-checking this revision, not caught by either VE pass — `resume()`'s config-change
  branch, `webRadioApp.h:502`, `if (_state != WRPlayState::STOPPED) _stopAudio();`) all go through
  this one shared function, fixing it once fixes all of them, including `suspend()`'s own call
  (finding #2) and this newly-found seventh site, without needing to touch each call site
  separately.
- `suspend()`: the `#ifdef MEMBUDGET_PHASE1` teardown block gains the same check — if `_state ==
  CONNECTING` when `suspend()` runs (the preceding `_stopAudio()` call already posted `ABORT` per
  the point above; this overwrites that with the stronger `TEARDOWN` request, since leaving the app
  entirely implies more than just stopping), skip `wrTeardownPumpTask()` and the direct
  `delete s_wr_audio` **entirely** for this call — post `s_wrPumpRequest = TEARDOWN` instead and
  return. Every other `suspend()` state (nothing in flight) keeps today's exact synchronous
  teardown — this only changes behavior for the specific unsafe case.

**Consumer side (the pump task, `wrPumpTaskBody`):** at the top of each cycle, if
`s_wrPumpRequest == CONNECT` and no connect is currently in flight, take the mutex and call
`connecttohost()` — this is the multi-second blocking call, now fully isolated to this task, never
touching `loopTask`. Once it returns (success or fail), check whether `s_wrPumpRequest` has since
changed to `ABORT` or `TEARDOWN` (set concurrently by `loopTask` while the connect was outstanding):
- **`TEARDOWN`**: if the connect had actually succeeded, call `stopSong()` to clean up; delete
  `s_wr_audio`, release the arena (`mb_arena_release()`) — moving this ownership to the pump task,
  exactly as the first revision intended, just triggered by a request enum instead of a bare flag;
  set `s_wrPumpResult = TORN_DOWN`; **null `s_wrPumpTask` last, immediately before
  `vTaskDelete(NULL)`** (VE second-pass finding #4's exact fix) so `wrEnsurePumpTask()`'s existing
  `if (s_wrPumpTask) return;` guard continues to see "pump still here, don't spawn a second one"
  for the entire window between the connect returning and the pump's actual self-deletion.
- **`ABORT`**: if the connect had succeeded, call `stopSong()` (the user asked to stop); set
  `s_wrPumpResult = ABORTED`; the pump task itself is **not** torn down (it persists across a stop,
  matching today's existing behavior/comment) — only the in-flight connect's outcome is discarded.
- **neither** (normal path): set `s_wrPumpResult = CONNECTED` or `FAILED` per the real outcome.

**`tick()` (runs every iteration while WebRadio is the current app — this is the fix for what was
VE's finding #3, generalized rather than patched):** polls `s_wrPumpResult` each iteration,
non-blocking. `CONNECTED` → today's existing PLAYING-transition logic runs exactly as it does today
(seed timers, etc.), reading the result instead of a live return value; `FAILED` → today's existing
`ERROR_UNREACHABLE` + `_onPlaybackFailed()` logic, same substitution; `ABORTED` or `TORN_DOWN` →
`_state = WRPlayState::STOPPED`. Each branch clears `s_wrPumpResult = NONE` after handling it. This
single poll, running unconditionally at the top of `tick()`, closes the wedge VE's second pass
found without any special-case logic in `resume()`: **`resume()`'s existing autoplay guard already
requires `_state == WRPlayState::STOPPED` before calling `_play()` again**
(`webRadioApp.h:526-528`, unchanged by this design) — so if the user re-enters WebRadio while an
`ABORT`/`TEARDOWN` is still resolving in the background, `_state` is still `CONNECTING` at that
exact moment and autoplay simply doesn't fire on *that* particular `resume()` call (a real,
accepted, narrowly-scoped limitation — a missed one-shot autoplay in a rare timing window, not a
crash and not a permanent wedge: `tick()` reconciles `_state` to `STOPPED` on its very first
iteration after re-entry, since `tick()` only runs once WebRadio is the current app again, and
after that a manual station tap or the next legitimate autoplay opportunity works normally). No new
state, no special resume()-only check, no risk of a second concurrent pump task (per the
`s_wrPumpTask`-null-timing fix above) — reusing the exact same STOPPED-gate `resume()` already has
today for an unrelated reason turns out to be sufficient once `_state` is reconciled correctly.

1. **`_play()` must be a no-op whenever `_state == CONNECTING` already** (VE finding #1). Today
   re-entry is impossible by accident — `loopTask` is fully blocked inside `connecttohost()` for
   the whole attempt, so nothing else can call `_play()` in the meantime. Removing that blocking is
   exactly what exposes six untraced call sites that could otherwise race a second connect onto the
   same `s_wr_audio`/mutex: `handleInput()`'s eject/STOP/PREV/NEXT/`_togglePlay()`/PLEDIT
   station-tap, and `dbgSet`'s `wrEject`/`wrPlay`/`wrStop`/`wrNext`/`wrPrev`/`wrUrl` hooks. Fix:
   `_play()` checks `_state == CONNECTING` first and returns immediately (log only) if so — a
   tap/command that arrives mid-connect is silently ignored, not queued, not blocked. Same pass:
   `dbgSet`'s `wrVol` handler (a third, independent freeze source VE found, using a raw
   `xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY)`) switches to the same short-timeout,
   graceful-degrade idiom `wrVolumeSink()` already uses for the real touch-drag path two hundred
   lines away — no reason for the debug setter to be less safe than the production gesture path it
   mirrors.
2. **Teardown must never delete `s_wr_audio` while the pump might still be touching it — and a
   fixed timeout cannot guarantee that, so this is an ownership fix, not a bigger number.** VE
   traced `WR_PUMP_ACK_TIMEOUT_MS = 10000`'s "thin margin" to an actual use-after-free: the
   existing ack-wait is a tripwire (logs and proceeds to delete `s_wr_audio` even on timeout), and
   `Audio.cpp:511-519` (TASK-295) forces the connect timeout to exactly `10000` for raw-IP stream
   URLs — a zero-margin tie with the teardown wait on an already-shipped path, before any DNS
   overhead on top. **Widening the number doesn't actually fix this**, because DNS resolution
   itself (`WiFiClient::connect()` → `hostByName()`, confirmed earlier this session,
   `framework-arduinoespressif32/libraries/WiFi/src/WiFiClient.cpp:302-309`) has **no timeout at
   all** — there is no fixed value that's guaranteed to exceed every real worst case, only ones
   that make the failure rarer. The actual fix has to change *who* is responsible for the
   deletion: **`suspend()` no longer deletes `s_wr_audio` itself when `_state == CONNECTING` at
   teardown time.** Instead it sets a `s_wrPumpTeardownPending` flag and returns immediately
   (`loopTask` stays fast — this is the whole point). The pump task, at the top of its next cycle
   *after* its blocking `connecttohost()` call finally returns (however long that takes — it is no
   longer `loopTask`'s problem once this fix lands, and the pump task is not TWDT-subscribed per
   `M-WR-AUDIO-TASK.md`'s own "Facts that bound the design" section, so a slow-but-eventually-
   returning connect can't crash the device from here either), checks the pending-teardown flag,
   discards whatever the connect result was, and performs the actual `delete s_wr_audio` /
   `mb_arena_release()` itself before self-deleting — the same "ack-then-self-delete, holding no
   locks" discipline the pump already uses for a normal stop request, just triggered by a flag
   instead of assumed to have already happened. Deletion ownership moves to whichever task
   actually knows it's safe, instead of `loopTask` guessing based on a timer.

With the request/result mechanism handled, Option B eliminates the `loopTask` freeze in every case
traced across both VE passes: a control tap during CONNECTING silently no-ops (`_play()`'s guard);
a stop-while-staying posts `ABORT` and reconciles via `tick()`'s next iteration; leaving WebRadio
posts `TEARDOWN` and returns immediately, with cleanup ownership genuinely moved to the pump task,
not raced against it. There is no remaining code path where `loopTask` blocks waiting for the pump
— every path is fast (no-op), posts a request and returns (connect/abort/teardown), or reconciles a
already-available result (`tick()`'s poll) — never a wait, and never an unreconciled stale state,
because `resume()`'s existing `_state == STOPPED` autoplay gate (unchanged, already in the code
today) naturally defers any new `_play()` until `tick()` has caught up.

**Option C — full Phase 2 (as sketched in `M-WR-AUDIO-TASK.md`).** Pump task owns the `Audio`
object entirely; all control calls (`PLAY`/`STOP`/`VOL`) go through a queue; results come back as
events; `tick()` never touches `Audio` directly. The revised Option B above has converged on
something structurally similar in shape (a request/result pair instead of direct calls) but scoped
narrowly to the connect operation specifically, leaving `setVolume`/other fast control calls as
direct blocking calls exactly as today — Option C's real remaining advantage is generality (any
future slow operation gets the same treatment for free) at the cost of "real surgery on the freshly
validated ADR-045/TASK-276 machine" per the original design doc's own words — `_onPlaybackFailed`,
the terminal-retry re-arm, and every debug getter/setter that reads `_state`/`_pendingAction`
synchronously would need to become event-driven. Larger surface for something to break, on a state
machine that's had real, hard-won validation this session (TASK-395's T276 test, the two
independent VE reviews of TASK-397's soak tool that specifically traced this state machine).

## Lean / decision

**Option B, narrow async connect via the request/result mechanism above, with every requirement
identified across both VE passes treated as mandatory.** It gets the actual measured problem
(loopTask freezing 421 times over 4 hours) to zero remaining blocking-wait cases, closes the
use-after-free VE's first pass found, and closes the permanent-wedge VE's second pass found in the
first pass's own fix — without touching the terminal-retry/auto-skip state machine's actual
transition logic: `tick()` still drives `_onPlaybackFailed`/retry pacing off `_state` and
`_lastAttemptMs` exactly as today, just reading a polled result instead of a live return value.
Option C is not rejected, just not justified yet — revisit if the hand-built request/result pair
above turns out to need generalizing to more than just connect (e.g. if a future change needs the
same treatment for another slow operation), at which point adopting the queue for real stops being
more work than maintaining several hand-built versions of the same idea.

**Human-approved 2026-08-04.** Sent to VE for a testability challenge on the state-machine boundary
before implementation, per this project's own standing practice (VE review before code, not after,
per TASK-397's precedent this session).

**Revision history:**
- **First VE pass** (see VE review section above): 4 blocking findings against the original
  two-requirement sketch (bare `_state`-guard on `_play()`, timeout-widening for teardown).
- **First revision**: fixed the letter of those 4 findings (added the `_play()` guard, replaced
  the timeout with a pending-teardown flag) but didn't re-derive the call graph after the fix.
- **Second VE pass** (see VE review section above): found the first revision's fix incomplete —
  `_stopAudio()` itself (not just `_play()`) is the real blocking primitive in most of the named
  call sites including `suspend()`'s own first line, and the flag-only teardown mechanism left
  `_state` permanently stuck at `CONNECTING` after any eject during a connect, since nothing else
  in the file ever clears it. 4 new blocking findings, 1 non-blocking (the mechanism for how the
  pump task learns to connect was never specified at all).
- **This revision**: replaces the ad-hoc flags with the request/result-slot mechanism (see "The
  mechanism, specified properly this time" above) — fixes `_stopAudio()` at the primitive (which
  transitively fixes `suspend()`'s call, plus a seventh call site inside `resume()`'s config-diff
  branch neither VE pass enumerated), and gives `tick()` an explicit, unconditional poll that
  reconciles `_state` on every iteration rather than relying on any one caller to do it. **Not yet
  re-reviewed — a third VE pass is the next step, not implementation.**

## VE review

Independent pass against the actual source, not a rubber stamp. All four line citations in the
"Design space" section check out exactly as written: `webRadioApp.h:1520` is the blocking
`xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY)` inside `_stopAudio()`; `:559` is `suspend()`'s
`delete s_wr_audio` (after `wrTeardownPumpTask()` at `:551`); `WR_PUMP_ACK_TIMEOUT_MS` is defined at
`:302` as `10000`; `connecttohost()` is called at `:1692`, bracketed by the mutex take/give at
`:1691`/`:1693` — the doc's `1690-1694` range is accurate. Good baseline; the problems are in what
the doc's mutex audit *didn't* trace, not in what it cited.

Five findings, four blocking. The narrow shape of Option B is still the right call — nothing here
argues for Option C — but the doc's own two "mandatory requirements" are not sufficient as written,
and in one case (#2) understate a crash-class risk as an open question.

1. **BLOCKING — the call-site audit stops at `_stopAudio()`/`suspend()`; `_play()` re-entrancy
   during `CONNECTING` is untraced, and it has real, already-wired entry points.** The doc frames
   the fix as gating "`_stopAudio()`/`suspend()` (eject, `switchApp` away from WebRadio)" — but
   `_play()` itself is invoked, with zero `_state` guard today, from six other loopTask-synchronous
   sites: `handleInput()`'s eject (`webRadioApp.h:958`, via `_stopAudio()`), STOP transport
   (`:969`), PREV/NEXT (`:966`, `_prevStation()`/`_nextStation()` → `_play()`), `_togglePlay()`
   (`:1747-1754`), PLEDIT station-tap (`_gestureEnd()`, `:1865`) — and `dbgSet()`'s `wrEject`
   (`:1213`), `wrPlay` (`:1219`), `wrStop` (`:1224`), `wrNext` (`:1230`), `wrPrev` (`:1231`), and
   `wrUrl` (`:1272`). Today none of these can race a connect, because loopTask is fully blocked
   inside `connecttohost()` for the entire attempt — that's precisely the safety-by-blocking Option
   B removes. Once `_play()` returns fast and loopTask is free during `CONNECTING`, a user mashing
   NEXT, tapping a different station, or a test harness firing `set wrNext` (these are the actual
   serial hooks the VE suite already uses) can call `_play()` a second time while the first request
   is still outstanding on the pump task. The doc never says what should happen: silently ignore the
   second call, or queue/supersede it? Getting this wrong risks two overlapping connect requests
   racing on the same `s_wr_audio` / mutex. **Fix: make this an explicit, mandatory third
   requirement** — e.g. "`_play()` is a no-op (log and return, `_state` unchanged) whenever called
   with `_state == CONNECTING` already in flight" — and state it as a hard precondition, not
   something left to infer from the "you cannot stop/skip/eject out of an in-flight connect" prose.
   Separately, note `dbgSet`'s `wrVol` handler (`:1357`) uses a raw
   `xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY)` — a *third*, independent freeze source distinct
   from `_stopAudio()`/`_play()` entirely, and inconsistent with the sanctioned pattern the file
   already uses two hundred lines away: `wrVolumeSink()` (`:328-338`, the real touch-drag volume
   path) deliberately uses the short `WR_PUMP_READ_TIMEOUT_TICKS` take with its own comment
   explaining why ("a drag must never block the UI task behind a busy pump — skip the step"). The
   debug `wrVol` setter should follow its own neighboring idiom, not the blocking one.

2. **BLOCKING — the `WR_PUMP_ACK_TIMEOUT_MS` risk is a real, already-provable use-after-free, not
   the "worth widening" open question OQ2 files it as.** `wrTeardownPumpTask()` (`:407-415`) is a
   *tripwire*, not a hard block: on ack timeout it logs an error and proceeds anyway
   (`s_wrPumpTask = nullptr`), without the pump task actually being dead — the pump only checks
   `s_wrPumpStopReq` "at the top of the cycle, holding no locks" (`:353`), i.e. it can't even see
   the stop request until its current mutex-held cycle (the in-flight `connecttohost()`) returns.
   `suspend()` then unconditionally deletes `s_wr_audio` (`:559`) and releases the arena — if the
   pump is still inside `connecttohost()` at that point, this is a use-after-free the moment the
   pump's blocked call eventually returns and touches the freed object / gives the freed mutex.
   The doc treats the 10000ms-vs-9425ms margin as merely "thin." It's worse than thin for a real,
   already-shipped code path: `Audio.cpp:511-519` (TASK-295) unconditionally overrides
   `m_timeout_ms_ssl` to exactly `10000` whenever the resolved host is a raw IP address —
   clobbering whatever `wrApplyConnectTimeout()` (`webRadioApp.h:257-258`,
   `WR_CONNECT_TIMEOUT_MS_SSL = 7000`) set moments earlier. For a raw-IP stream URL, the
   underlying connect call's own timeout is *exactly* `WR_PUMP_ACK_TIMEOUT_MS` — a zero-margin tie,
   before adding any DNS/TCP/TLS overhead sitting on top of that internal `select()` timeout, which
   makes the teardown ack-wait losing the race the *likely* outcome for that path, not an edge
   case. This is a crash, not a UX papercut, and it's reachable today's own code, not a
   hypothetical future change. **This must be promoted from OQ2 to a mandatory pre-implementation
   requirement**: either (a) widen `WR_PUMP_ACK_TIMEOUT_MS` past every connect path's real worst
   case including the raw-IP 10000ms tie, with margin, or (b) make the teardown path refuse to
   delete `s_wr_audio`/release the arena on an ack timeout when `_state == CONNECTING` at teardown
   time — park the delete and retry, or extend the wait — rather than proceeding past a
   known-still-live pointer. Pick one before implementation; don't ship with the tripwire's current
   "log and proceed anyway" behavior unchanged.

3. **BLOCKING — the doc's own description of what happens to WebRadio's own controls during
   `CONNECTING` is self-contradictory, and the two readings have very different implementations.**
   Same paragraph: "`loopTask` stays responsive for everything else meanwhile: touch, render, other
   apps" and "you wait for it to resolve (same worst-case ~7-9s)". These can't both be true if the
   wait happens synchronously inside a call made from loopTask — the ESP32 Arduino `loop()` is
   single-threaded; there is no separate scheduler tick keeping render/touch/other-apps alive while
   any one call in that loop blocks (this is exactly the mechanism of today's bug). Concretely: does
   pressing NEXT while `CONNECTING` (a) silently no-op, which is consistent with "loopTask stays
   responsive," or (b) block until the connect resolves, which — despite the doc's phrasing — would
   re-freeze the *entire device* (render, touch, taskbar, every other app run from the same
   loopTask), not just "WebRadio's own buttons"? Given finding #1's fix (make `_play()` a no-op
   during `CONNECTING`), (a) is both correct and consistent with the doc's overall design intent —
   but the doc needs to say this explicitly and drop the "you wait for it to resolve" framing for
   WebRadio's own controls, reserving genuine waiting for the one path that legitimately still does
   it: `switchApp`-away via `wrTeardownPumpTask()`'s ack-wait (bounded, per finding #2 once fixed).

4. **BLOCKING (exit-criteria gap, downstream of #1/#3) — no exit criterion tests re-entrant control
   input during `CONNECTING`, despite the test hooks already existing.** The exit criteria's
   `switchApp`-during-`CONNECTING` bullet is good but narrow — it doesn't cover the six other
   `_play()`/`_stopAudio()` entry points from finding #1, which is exactly where a silent regression
   would hide (a Developer could pass the switchApp check and still ship a NEXT-button race). This
   is cheap to close: `set wrState 1` (`dbgSet`, `:1204`) already forces `CONNECTING` synthetically,
   and `set wrNext`/`wrPrev`/`wrStop`/`wrPlay`/`wrEject` (`:1213-1231`) already exist as serial test
   hooks — no new instrumentation needed. **Add an explicit exit criterion**: force `CONNECTING`
   (synthetically or via a real slow/dead host), fire each of eject/stop/next/prev/play/station-tap
   via both `cmdTap` and the `set wr*` debug commands, and confirm via `[W][perf] app.tick` that
   none produces a multi-second spike, and via `get arenaStats`/`get wrPump` that nothing corrupts
   afterward.

**Non-blocking:**

5. The stated `WR_PUMP_ACK_TIMEOUT_MS` margin arithmetic doesn't check out: "10000ms covers
   [7099-9425ms] with only a ~600ms-1900ms margin" — `10000-9425=575ms` (~600, checks out) but
   `10000-7099=2901ms`, not ~1900ms. Doesn't change the conclusion (finding #2 shows the margin can
   be exactly zero on a real path regardless of this arithmetic), but fix the number before anyone
   cites "1900ms" as a real figure.

6. Informational, not required: `webRadioApp.h:866`'s existing `isConnecting()` hook (already wired
   to the taskbar's amber active-indicator, `main.cpp:1878-1893`) could cheaply surface "still
   connecting" feedback when a WebRadio-own control tap is silently ignored per finding #1/#3's
   fix — addresses OQ1's fairness question with a UI affordance rather than leaving a tap that does
   nothing unexplained. Worth a look during implementation; not a gate.

**Testability sign-off:** with #1-#4 addressed — a mandatory `_play()`-re-entrancy rule, a mandatory
(not open-question) fix for the teardown/use-after-free race, an unambiguous ignore-vs-wait
specification for WebRadio's own controls, and an exit criterion that actually exercises those
controls during `CONNECTING` — this design is falsifiable and a Developer would know what "done"
looks like. As currently written, a Developer implementing literally what's on the page would
satisfy the two named "mandatory requirements," pass the stated exit criteria, and still ship a
build with a live use-after-free (finding #2) and a live re-entrancy race (finding #1) that this
session's own soak methodology is fully capable of catching — if the tests were pointed at it, which
right now they aren't (finding #4). That gap is exactly the kind this project's standing
pre-implementation VE practice exists to catch before code, not after a second incident report.

### Second pass (2026-08-04)

Independent re-verification against the current source (`app/src/webRadioApp.h`, 1961 lines as of
this pass; line numbers re-derived, not trusted from either prior pass). This is not a rubber stamp
of "were the first pass's four findings addressed" — it re-derives the `_play()`/`_stopAudio()`
call-site graph from scratch and re-traces the requirement-2 mechanism against the actual
`suspend()`/`wrPumpTaskBody()`/`wrEnsurePumpTask()` code. Conclusion up front: **the revision's core
idea (deferred deletion ownership) is right, but as specified it does not achieve what the doc
claims, for a reason neither prior version of the doc traces — `_stopAudio()` itself, not just
`_play()` and not just the `delete s_wr_audio` step, needs to change, and nothing in the design
writes to `_state` from the deferred-teardown path, which wedges the app rather than just racing
it.** Five findings, four blocking.

1. **BLOCKING — requirement 1's guard doesn't close the call sites the doc itself enumerates as
   needing closure, because most of them never call `_play()` at all.** Re-derived the call graph
   independently: `_prevStation()` (`:1756-1760`), `_nextStation()` (`:1762-1766`), the PLEDIT
   station-tap (`:983`), `_togglePlay()`'s *start-playing* branch (`:1750-1751`), and `dbgSet`'s
   `wrPlay`/`wrNext`/`wrPrev`/`wrUrl` (`:1219-1223`, `:1230-1231`, `:1272`) all do route through
   `_play()` and are genuinely fixed by requirement 1's guard. But five of the doc's own named call
   sites do **not** go through `_play()` — they call `_stopAudio()` directly: the eject handler
   (`:957-958`), the STOP transport button (`:968-970`), `_togglePlay()`'s *stop* branch when
   `_state == PLAYING || _state == CONNECTING` (`:1747-1749` — this one is even more pointed, since
   the code explicitly names `CONNECTING` in its own condition and routes it into the unguarded
   call), and `dbgSet`'s `wrEject` (`:1213-1214`)/`wrStop` (`:1224-1225`). `_stopAudio()` itself
   (`:1516-1523`) has **zero `_state` check** — `if (s_wr_audio) { xSemaphoreTake(s_wrAudioMutex,
   portMAX_DELAY); s_wr_audio->stopSong(); xSemaphoreGive(...); }` unconditionally. While the pump
   task is mid-`connecttohost()` it holds exactly this mutex (per finding #2's own already-proven
   unbounded-duration argument — DNS resolution has no timeout), so pressing eject, STOP, or
   PLAY/PAUSE-to-stop during `CONNECTING` still fully freezes `loopTask` — and therefore the whole
   device — for the entire remaining connect duration, identically to today. Requirement 1 as
   literally written ("`_play()` checks `_state == CONNECTING`... and returns immediately if so")
   only ever prevents a *second* connect from racing the first; it does nothing for the *stop* path,
   which is the more commonly-pressed button during a stuck connect (a user waiting on a frozen
   "Connecting..." screen reaches for eject or STOP, not NEXT). **Fix: `_stopAudio()` needs its own
   guard/degrade path** — either skip the `stopSong()` call entirely when `_state == CONNECTING`
   (nothing is playing yet, so there's nothing to stop at the codec level) and let the
   pending-teardown/no-op machinery handle it, or take the mutex with the same short-timeout,
   degrade-gracefully idiom `wrVolumeSink()`/the fixed `wrVol` handler already use. Either way this
   is a **fourth** mandatory requirement, not a detail implied by requirement 1.

2. **BLOCKING — `suspend()`'s own first line is the unconditional, unguarded `_stopAudio()` call
   finding #1 above describes; requirement 2 only ever touches the *later* half of `suspend()`.**
   Traced `suspend()` (`:532-584`) top to bottom: `_stopAudio()` runs unconditionally at `:545`,
   *before* the `#ifdef MEMBUDGET_PHASE1` block (`:546-561`) that requirement 2's deferred-teardown
   flag is meant to modify. Every `switchApp`-away from WebRadio — not just eject, any target app —
   goes through this exact `suspend()`. So even granting requirement 2's fix works exactly as
   described for the `delete s_wr_audio` step, `suspend()` still blocks on `_stopAudio()`'s call at
   `:545` first, for the same unbounded duration, before it would ever reach the code that sets
   `s_wrPumpTeardownPending`. The doc's own "Design space" summary — *"leaving WebRadio during
   CONNECTING returns immediately and defers cleanup to the pump task itself rather than either
   blocking `loopTask` or racing a delete against it. There is no remaining case where `loopTask`
   blocks waiting for the pump"* — is false as specified, and it's exactly the one path (`switchApp`
   away during a real `CONNECTING`) the doc's own exit criteria singles out for a dedicated check
   (last bullet). This is the same root cause as finding #1, viewed from the exit path rather than
   the tap path — worth stating as its own item because it's the specific mechanism requirement 2
   claims to have fixed and evidently hasn't, once `_stopAudio()`'s current unconditional placement
   in `suspend()` is accounted for.

3. **BLOCKING — Open Question #3 is not a legitimate open question; it understates a bug that fires
   deterministically, not just under a race, and the doc's own re-entry framing actually undersells
   how bad it is.** Fixing findings #1/#2 (skip/degrade `_stopAudio()` during `CONNECTING`) requires
   *not* running `_stopAudio()`'s `_state = WRPlayState::STOPPED` line (`:1524`) — that line is
   currently the *only* code in the entire file that ever clears `WRPlayState::CONNECTING` outside of
   a successful/failed `connecttohost()` return. `_state` is a `WebRadioApp` **instance member**;
   `wrPumpTaskBody()` (`:349-382`) is a free function with no reference to the instance — it can only
   touch file-static globals (`s_wr_audio`, `s_wrPumpTeardownPending`, etc.), never `_state`. Neither
   `resume()` (`:474-530`, the function that actually runs on WebRadio re-entry — confirmed `init()`
   runs exactly once per app lifetime, gated by `g_appLaunched[]` in `switchApp()`,
   `main.cpp:2013-2019`) nor `tick()`'s dispatch polls any "deferred teardown finished" signal to
   close this loop, and `tick()` doesn't even run while WebRadio is suspended (appShell only ticks
   `currentAppId`), so nothing observes completion until the user is already back in WebRadio. Net
   effect, once requirement 1/2 are patched to stop blocking: **any single eject during `CONNECTING`
   leaves `_state` stuck at `CONNECTING` forever** — not contingent on racing a quick re-entry, the
   doc's own framing ("if the user... re-enters WebRadio quickly, before the pump task's blocked call
   returns"). Whether the user waits 30 seconds or 30 minutes before coming back makes no difference;
   there is no code path that ever clears it. On every future entry: `resume()`'s autoplay guard
   (`_state == STOPPED` at `:527`) never fires; `_play()`'s new requirement-1 guard permanently no-ops
   PREV/NEXT/PLEDIT-tap because `_state == CONNECTING` never stops being true; `_drawTitleZone()`
   (`:1799`) shows "Connecting..." forever; the taskbar's `isConnecting()` amber indicator (`:866`,
   wired at `main.cpp:1878-1893`) stays lit forever. WebRadio is permanently wedged until the device
   reboots. **This is a fifth mandatory requirement** (or a rework of the flag mechanism so it stores
   enough for `tick()`/`resume()` to reconcile `_state` once the deferred teardown lands — e.g. a
   second static, `s_wrPumpTeardownDone`, that `resume()` checks first and uses to reset `_state =
   STOPPED` before running the rest of its logic) — not an open question to resolve "before
   implementation is underway" at leisure. As specified, requirement 2 trades a use-after-free for a
   deterministic permanent-wedge — a smaller class of bug, but not an acceptable one, and not what
   "flagged, not solved" should mean for something this reachable (one eject, no race required).

4. **BLOCKING (bookkeeping gap, currently masked by finding #3, would reopen once #3 is fixed) —
   `s_wrPumpTask` handle timing during the deferred window is unspecified, and the two obvious
   implementations each have a problem.** Asked to check directly: does `wrEnsurePumpTask()`'s guard
   (`if (s_wrPumpTask) return;`, `:388`) hold up against a fresh `_play()` on re-entry racing the old,
   still-live pump task? Today `wrTeardownPumpTask()` nulls `s_wrPumpTask` (`:414`) only *after* its
   (bounded, synchronous) ack-wait — i.e., only once the pump is provably gone. The deferred path the
   revision proposes has no equivalent moment: if `suspend()` nulls `s_wrPumpTask` early (to mirror
   today's bookkeeping) while the *old* pump task is still blocked inside `connecttohost()`, a fresh
   `_play()` on re-entry would see `s_wrPumpTask == nullptr` and call `wrEnsurePumpTask()`, which
   would create a **second**, concurrent pump task via `xTaskCreatePinnedToCore` (`:393-395`) while
   the first is still alive and about to independently touch `s_wr_audio` per its own deferred-delete
   logic — two tasks touching the same `Audio*`/mutex is a real corruption/crash risk. If instead the
   handle is left stale until the old pump nulls itself right before `vTaskDelete(NULL)`, the guard
   holds correctly. The doc specifies neither. **Currently this exact scenario cannot fire** — finding
   #3 means `_state` never leaves `CONNECTING` after an eject-during-connect, so `_play()`'s guard
   permanently blocks the very `_play()` call that would reach `wrEnsurePumpTask()` — but that's an
   accident of a different bug masking this one, not evidence of soundness. Fixing #1-#3 without also
   specifying `s_wrPumpTask`'s timing reopens this hole immediately. **Fix: state explicitly that
   `s_wrPumpTask` stays non-null until the pump task itself nulls it (a plain, 32-bit-aligned pointer
   write — no torn read on Xtensa) immediately before `vTaskDelete(NULL)`**, so `wrEnsurePumpTask()`'s
   existing guard continues to see "pump still there" for the entire deferred window, not just the
   normal-teardown window it currently covers.

5. **BLOCKING (exit-criteria gap, downstream of #1-#3) — the re-entrant-input exit criterion can't
   actually exercise findings #1/#2 as worded, and no exit criterion covers requirement 2's own new
   mechanism (the re-entry race) at all.** The exit criteria bullet allows forcing `CONNECTING`
   "synthetically (`set wrState 1`) or via a real slow/dead host" — but `set wrState 1` (`:1204-1210`)
   only overwrites the `_state` field; it does **not** put the pump task inside a real
   `connecttohost()` call, so `s_wrAudioMutex` is free the whole time. Run against the synthetic
   path, `_stopAudio()`'s blocking take at `:1520` would succeed immediately (mutex uncontended) —
   the test would pass while finding #1's real bug (mutex genuinely held, multi-second block) goes
   completely unexercised. The bullet needs to make the real-host path mandatory for this specific
   check, not an equally-weighted alternative to the synthetic one. Separately: every exit-criterion
   bullet in the doc tests either "tap during CONNECTING" (requirement 1's surface) or "leave once
   during CONNECTING, confirm no crash" (the switchApp bullet, requirement 2's *delete* surface) —
   none of them test *leaving WebRadio during CONNECTING, then re-entering before the deferred
   teardown completes*, which is finding #3/OQ3's exact scenario and requirement 2's own newly-added
   mechanism. **Add an explicit exit criterion**: force `CONNECTING` against a real slow/dead host,
   eject to Spotify, immediately eject back to WebRadio (fastest two-tap timing achievable, well
   before a multi-second connect could have returned), and confirm: (a) no crash/corruption
   (`get arenaStats`/`get wrPump`), (b) `_state` is NOT permanently stuck at `CONNECTING` once the
   deferred teardown actually completes (poll `get wrState` for some bounded time after re-entry), and
   (c) no double pump task exists (`get wrPump` cycle counters climbing from exactly one source, not
   two racing writers).

**Non-blocking:**

6. Informational: the doc's Option B framing — "move only the `connecttohost()` call onto the pump
   task" — never actually specifies the mechanism by which the pump task learns to call
   `connecttohost()` at all. `wrPumpTaskBody()`'s existing loop (`:349-382`) only ever calls
   `s_wr_audio->loop()`; there's no request flag, no URL handoff, no result slot in the code today.
   This is reasonable to leave for implementation (the doc is explicit that it isn't implementation-
   ready), but the next revision should say a sentence about the intended shape (a
   `s_wrPumpConnectPending`-style request/result pair, presumably) so a Developer isn't left
   reconstructing the load-bearing half of "Option B" from scratch, and so this second-pass review
   isn't the only place the gap is written down.

**Testability sign-off (second pass):** consensus **not** reached — go/no-go is **no-go**, four
blocking findings. The revision correctly fixed the two most legible problems the first pass raised
(a `_play()`-only re-entrancy guard, and moving delete-ownership off a fixed timeout) but did not
re-trace the call graph or the state-machine consequences far enough: `_stopAudio()` is the actual
blocking primitive in three of the six-plus-one call sites and in `suspend()` itself, and nothing in
the revision touches it. Requirement 2's flag mechanism, followed through to what happens on the very
next re-entry, wedges `_state` permanently rather than merely racing it — worse than the "not yet
resolved" framing OQ3 gave it, since no race is even required to reach the wedge. None of this is
visible from the doc's own reasoning because the doc never re-derived the call graph from source
after drafting the fix, the same gap that produced the first pass's finding #1 in the first place.
Concretely falsifiable next step: fix `_stopAudio()` (finding #1), audit its one remaining unconverted
call site inside `suspend()` (finding #2), give the deferred path a way to reconcile `_state` on
`resume()` (finding #3), pin down `s_wrPumpTask`'s null-timing in prose (finding #4), and extend the
exit criteria to actually exercise the mutex-held case and the re-entry race (finding #5) — then this
is ready for a third pass, not for implementation as currently written.

## Open questions

1. **Is "control taps silently no-op during CONNECTING" actually a UX regression, or a wash?**
   Currently, mid-connect, the *entire device* is frozen — you can't press anything, anywhere, so
   there's no real "responsive but ignored" experience to compare against today. This is arguably a
   strict improvement over the status quo, not a new limitation — worth confirming this framing
   holds up rather than assuming it during implementation. VE's non-blocking finding #6 (surfacing
   `isConnecting()`, already wired to the taskbar's amber indicator, as feedback when a tap is
   ignored) is a cheap way to make the no-op legible instead of a silent nothing.
2. ~~Is `WR_PUMP_ACK_TIMEOUT_MS = 10000` the right bound?~~ — **superseded by the requirement-2
   revision above.** The fix no longer relies on picking a big-enough number (VE's finding #2
   showed no fixed number is soundly sufficient, since DNS resolution is unbounded); teardown
   ownership moves to the pump task instead. `WR_PUMP_ACK_TIMEOUT_MS` still exists for the
   *original* "pump genuinely stuck, not just mid-connect" case the ack semaphore already guarded
   against — that tripwire's behavior on a real stuck task (not a merely-slow connect) is
   unchanged by this design and out of scope here.
3. ~~Quick re-entry into WebRadio while a deferred teardown is still pending~~ — **resolved by the
   request/result mechanism, not a remaining open question.** VE's second pass correctly identified
   this as the same underlying gap as its finding #3 (nothing reconciled `_state` on re-entry) —
   fixed the same way: `tick()`'s unconditional poll sets `_state = STOPPED` once `s_wrPumpResult ==
   TORN_DOWN` lands, and `resume()`'s pre-existing `_state == STOPPED` autoplay gate
   (`webRadioApp.h:526-528`, not modified by this design) means a re-entry that races an unresolved
   teardown simply doesn't autoplay on *that* specific `resume()` call — `_state` is still
   `CONNECTING` at that instant, so the gate correctly holds off, and `tick()` catches up on its
   next iteration once WebRadio is current again. No second pump task risk either, since
   `s_wrPumpTask` stays non-null (blocking `wrEnsurePumpTask()`) for the entire window until the old
   pump nulls it immediately before self-deleting. Accepted residual limitation, not a bug: a user
   who leaves and instantly returns during this narrow window may need to manually tap a station
   once, since the one-shot autoplay opportunity was missed — covered by the new exit criterion
   below, which should confirm this is the *only* consequence (no crash, no stuck state, no double
   pump task), not something worse.
4. **Does the ICY/title/marquee code path (`_drawTitleZone()`, already flagged in
   `M-WEBRADIO-DIAG-SURFACING.md` for a retry-countdown addition) need any change under Option B?**
   Likely not — `_state == CONNECTING` already drives the "Connecting..." marquee text today; a
   polled-result model doesn't change what `tick()` does with `_state` once it's set, just how the
   transition into PLAYING/ERROR_* gets triggered.
5. **Should this land before or after `M-WEBRADIO-DIAG-SURFACING`'s Tier 1 (retry countdown)?**
   That design flagged its own interaction with TASK-393's freeze mechanism (periodic `_dirty`
   while parked). The two are touching adjacent but different code (this doc: the CONNECTING
   transition itself; that doc: the parked-in-`ERROR_*` marquee) — probably independent and
   order-agnostic, but worth a second look once both are closer to implementation.

## Exit criteria

- ~~VE testability review of the CONNECTING-state changes~~ — **two passes done, 2026-08-04.**
  First pass: 4 blocking findings against the original two-requirement sketch, addressed same day.
  Second pass: found that fix incomplete (`_stopAudio()` was the real blocking primitive in most
  named call sites; the flag-only teardown left a permanent wedge, not just a race) — 4 new
  blocking findings, addressed in this revision via the request/result-slot mechanism. **This
  revision has NOT yet had a third VE pass** — treat as addressed-but-unverified, not closed, until
  that happens.
- **Re-entrant control input during CONNECTING, using existing test hooks — split by expected
  outcome, since the two categories of tap now behave differently under the fixed design (this is
  a correction from the previous version of this criterion, which incorrectly expected `_state` to
  stay `CONNECTING` for every tap type):** force `CONNECTING` against a **real** slow/dead host —
  `set wrState 1` alone does *not* exercise this (it never takes the mutex, so it can't catch a
  regression in the `_stopAudio()`/`suspend()` fix specifically; the synthetic path is fine for
  isolating `_play()`'s own no-op guard but must not be the only path tested for the mutex-related
  requirements). Then, against the real in-flight connect:
  - **PREV/NEXT/PLEDIT-tap/`wrPlay`/`wrNext`/`wrPrev`/`wrUrl`** (route through `_play()`'s guard):
    confirm `_state` is unchanged (still `CONNECTING`), `[W][perf] app.tick` shows no multi-second
    spike, and the original in-flight connect resolves normally once it completes.
  - **eject/STOP/`_togglePlay()`'s stop branch/`wrEject`/`wrStop`** (route through the fixed
    `_stopAudio()`): confirm `[W][perf] app.tick` shows no multi-second spike (the actual regression
    finding #1/#2 would reintroduce if unfixed), `s_wrPumpRequest` becomes `ABORT`, and — polling
    `get wrState` for a bounded time afterward — `_state` transitions to `STOPPED` once the
    in-flight connect actually resolves (not immediately, and not stuck forever).
  - Either way: `get arenaStats`/`get wrPump` show nothing corrupted afterward.
- **New — leave-and-quickly-re-enter during CONNECTING (VE second-pass finding #5's own proposed
  test, for the mechanism that finding #3 showed was actually broken):** force `CONNECTING` against
  a real slow/dead host, eject to Spotify, then immediately eject back to WebRadio (fastest
  achievable two-tap timing, well before the connect could plausibly have returned). Confirm: (a) no
  crash or corruption (`get arenaStats`/`get wrPump`); (b) `_state` is **not** permanently stuck at
  `CONNECTING` — polling `get wrState` for a bounded time after re-entry should show it reach
  `STOPPED` once the deferred teardown actually completes; (c) exactly one pump task exists
  throughout (`get wrPump`'s cycle counters climbing from a single source, not two racing writers);
  (d) autoplay may or may not fire on this specific re-entry (the accepted residual limitation from
  Open Question 3) but a manual station tap afterward works normally either way.
- DUT proof under the *same* conditions that surfaced the problem: re-run TASK-393's
  `--spotify-present` soak (or a shorter targeted version) against the same station and confirm the
  `[W][perf] app.tick` worst-path no longer shows multi-second values during connect failures —
  `wr.connect` (or its pump-task equivalent) should still show the real connect duration, `app.tick`
  should stay flat regardless of connect outcome.
- Confirm `switchApp`-away-from-WebRadio during a real CONNECTING state (not just a healthy one)
  doesn't crash or corrupt the arena — this is the one path Option B still allows to block, and the
  one place a mistake here would be a crash, not just a UX papercut.
- TASK-395-style regression coverage for the terminal-retry mechanism re-run after this lands, to
  confirm the retry cadence/state transitions are unchanged from `tick()`'s perspective.
