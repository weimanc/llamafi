# Design — moving WebRadio's `connecttohost()` off loopTask (TASK-398)

> Owner: Architect
> Status: accepted (lean) — human-approved 2026-08-04. VE's first pass (same day) found 4 blocking
> findings; all four addressed same day in a revision to the "Design space"/"Lean" sections below
> (now three mandatory requirements, not two). **Revision has not yet had a second VE pass — not
> implementation-ready until that happens.** One new open question (re-entry racing a deferred
> teardown) surfaced during the revision itself and is explicitly unresolved, not implemented
> around.
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

**Revised 2026-08-04 after VE review — three mandatory requirements, not two, and #2 rewritten
after the original "widen the timeout" idea turned out not to be soundly fixable at all:**

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

With all three handled, Option B eliminates the `loopTask` freeze in every case traced so far: a
control tap during CONNECTING silently no-ops instead of blocking anything; leaving WebRadio during
CONNECTING returns immediately and defers cleanup to the pump task itself rather than either
blocking `loopTask` or racing a delete against it. There is no remaining case where `loopTask`
blocks waiting for the pump — every path is now either fast (no-op) or deferred (pending-teardown
flag), never a wait.

**Option C — full Phase 2 (as sketched in `M-WR-AUDIO-TASK.md`).** Pump task owns the `Audio`
object entirely; all control calls (`PLAY`/`STOP`/`VOL`) go through a queue; results come back as
events; `tick()` never touches `Audio` directly. This naturally handles cancellation/supersession
(a stale connect result for a station the user already skipped past just gets dropped when it
arrives) as a structural property of the queue, not a bolted-on flag — the real advantage over the
revised Option B, whose silent-no-op (requirement 1) and deferred-teardown-with-a-pending-flag
(requirement 2) are two separate, hand-built mechanisms doing a smaller version of the same job.
Cost: "real surgery on the freshly validated ADR-045/TASK-276 machine" per the original design
doc's own words — `_onPlaybackFailed`, the terminal-retry re-arm, and every debug getter/setter
that reads `_state`/`_pendingAction` synchronously would need to become event-driven. Much larger
surface for something to break, on a state machine that's had real, hard-won validation this
session (TASK-395's T276 test, the two independent VE reviews of TASK-397's soak tool that
specifically traced this state machine).

## Lean / decision

**Option B, narrow async connect, with all three safety requirements above treated as mandatory,
not optional.** It gets the actual measured problem (loopTask freezing 421 times over 4 hours) down
to zero remaining blocking-wait cases — every path is now either a fast no-op (a control tap during
CONNECTING) or a deferred cleanup (leaving WebRadio during CONNECTING) — without touching the
terminal-retry/auto-skip state machine's actual transition logic: `_play()` still runs to
completion synchronously from the pump task's own perspective, `tick()` still drives
`_onPlaybackFailed`/retry pacing off `_state` and `_lastAttemptMs` exactly as today, just reading a
polled result instead of a live return value. Option C is not rejected, just not justified yet —
revisit if the silent-no-op UX (requirement 1) or the deferred-teardown mechanism (requirement 2)
turn out to need more real state than a flag once implementation is underway, at which point the
hand-built version may cost more than just adopting the queue.

**One new edge case surfaced while revising requirement 2, not yet resolved — see Open Questions:**
if the user leaves WebRadio during CONNECTING (deferred teardown pending) and re-enters WebRadio
quickly, before the pump task's blocked `connecttohost()` call returns and completes the deferred
cleanup, `init()`/`resume()` would be racing the still-pending teardown for ownership of
`s_wr_audio`. Not covered by any of the three requirements above as currently scoped.

**Human-approved 2026-08-04.** Sent to VE for a testability challenge on the state-machine boundary
before implementation, per this project's own standing practice (VE review before code, not after,
per TASK-397's precedent this session). VE findings recorded below.

**Revised 2026-08-04, same day, after VE's first pass (4 blocking findings) — see VE review section
above for the original findings and the "Revised" callouts inline above for how each was addressed.
This revision has not yet been re-reviewed by VE — flagged in Open Questions, not silently treated
as resolved.**

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
3. **NEW, surfaced during this revision, not yet resolved — quick re-entry into WebRadio while a
   deferred teardown (requirement 2) is still pending.** If the user leaves WebRadio during
   CONNECTING (setting `s_wrPumpTeardownPending`) and switches back into WebRadio before the pump
   task's blocked call returns and completes that deferred cleanup, `init()`/`resume()` would race
   the pending teardown for ownership of `s_wr_audio`. Needs a concrete answer before implementation
   — candidates: (a) `resume()` checks the pending-teardown flag and treats WebRadio as still
   mid-shutdown, showing a brief "closing…"-style state until the pump's deferred cleanup finishes,
   then proceeds with a normal fresh `init()`; (b) block re-entry into WebRadio entirely (via
   `switchApp`'s own gating) while a teardown is pending, same rough shape as how CONNECTING itself
   blocks control taps. Not designed yet — flagged, not solved, per this doc's own standing
   practice of not silently treating an open edge case as handled.
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

- ~~VE testability review of the CONNECTING-state changes~~ — **first pass done, 2026-08-04, 4
  blocking findings, see VE review section above.** Addressed same day in the "Design space" /
  "Lean" revisions above (three mandatory requirements instead of two, self-contradiction resolved
  by eliminating the "wait" case entirely, new open question #3 for the re-entry race surfaced
  during the revision itself). **This revision has NOT yet had a second VE pass** — treat as
  addressed-but-unverified, not closed, until that happens.
- **New, from VE finding #4 — re-entrant control input during CONNECTING, using existing test
  hooks, no new instrumentation needed:** force `CONNECTING` (`set wrState 1`, or a real slow/dead
  host), then fire each of eject/stop/next/prev/play/station-tap via both `cmdTap` and the
  `set wr*` debug commands (`wrEject`/`wrStop`/`wrNext`/`wrPrev`/`wrPlay`/`wrUrl`), and confirm: (a)
  `_state` is unchanged by each (still `CONNECTING`, not disturbed by the ignored tap), (b)
  `[W][perf] app.tick` shows no multi-second spike from any of them, (c) `get arenaStats`/
  `get wrPump` show nothing corrupted afterward, and (d) the original in-flight connect still
  resolves normally (to PLAYING or an `ERROR_*` state) once its own attempt completes, undisturbed
  by the ignored taps.
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
