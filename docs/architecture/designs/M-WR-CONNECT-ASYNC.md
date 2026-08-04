# Design — moving WebRadio's `connecttohost()` off loopTask (TASK-398)

> Owner: Architect
> Status: accepted (lean) — human-approved 2026-08-04; VE review complete same day, **4 blocking
> findings, no-go until resolved** (see VE review section below). Narrow-option lean itself stands;
> the doc's stated "mandatory requirements" need revision before implementation.
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
blocking on the call. Two real safety requirements fall out of tracing the existing code, not
optional extras:

- **`_stopAudio()` / `suspend()` (eject, `switchApp` away from WebRadio) must not blocking-take
  `s_wrAudioMutex` while a connect may be in flight.** Currently they do
  (`xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY)`, `webRadioApp.h:1520`), which would block
  `loopTask` for the same 7-9s waiting for the pump to finish its connect — moving the freeze, not
  removing it. Fix: gate these paths on `_state != CONNECTING`, i.e. accept that you cannot
  stop/skip/eject *out of* an in-flight connect attempt — you wait for it to resolve (same
  worst-case ~7-9s, but `loopTask` stays responsive for everything else meanwhile: touch, render,
  other apps, `switchApp` to a *different* app is the one path that still needs to wait, see next
  point). This is a real, honest UX limitation, not free — but it replaces "everything is frozen"
  with "WebRadio's own eject/skip buttons don't respond for up to ~7-9s," which is a real reduction
  even if not a full fix.
- **`suspend()` deletes the `Audio` object** (`webRadioApp.h:559`, `MEMBUDGET_PHASE1`) **after**
  `wrTeardownPumpTask()`'s ack-or-timeout handshake (`WR_PUMP_ACK_TIMEOUT_MS = 10000`,
  `webRadioApp.h:302`). If the pump is mid-`connecttohost()` when `suspend()` fires (user switches
  to a different app while WebRadio is CONNECTING), deleting `s_wr_audio` out from under the pump's
  blocked call is a use-after-free. The existing teardown handshake already has *some* tolerance
  for this ("pump may be stuck in `Audio::loop()`" is an anticipated log line), but 10s is close
  enough to the observed 7-9425ms range that it's not a comfortable margin — worth widening or
  making connect-aware (e.g. skip the ack-timeout log/path entirely and just wait out the known
  bound when `_state == CONNECTING` at teardown time, since in that specific case "stuck" isn't an
  anomaly, it's the expected worst case).

With both handled, Option B eliminates the `loopTask` freeze for the common case (nothing else
touches WebRadio while it's connecting) and bounds the worst case (switching away from WebRadio
mid-connect) to a wait, not a crash — down from "the whole device is unusable" to "leaving
WebRadio takes up to ~7-9s if you catch it mid-connect," which is a real, meaningful improvement
without adopting the full command-queue model.

**Option C — full Phase 2 (as sketched in `M-WR-AUDIO-TASK.md`).** Pump task owns the `Audio`
object entirely; all control calls (`PLAY`/`STOP`/`VOL`) go through a queue; results come back as
events; `tick()` never touches `Audio` directly. This naturally handles cancellation/supersession
(a stale connect result for a station the user already skipped past just gets dropped when it
arrives) without the "wait it out" compromise Option B needs — the real advantage over B. Cost:
"real surgery on the freshly validated ADR-045/TASK-276 machine" per the original design doc's own
words — `_onPlaybackFailed`, the terminal-retry re-arm, and every debug getter/setter that reads
`_state`/`_pendingAction` synchronously would need to become event-driven. Much larger surface for
something to break, on a state machine that's had real, hard-won validation this session (TASK-395's
T276 test, the two independent VE reviews of TASK-397's soak tool that specifically traced this
state machine).

## Lean / decision

**Option B, narrow async connect, with both safety requirements above treated as mandatory, not
optional.** It gets the actual measured problem (loopTask freezing 421 times over 4 hours) down to
a much smaller and more honest one (WebRadio's own controls, and only `switchApp`-away specifically,
wait up to the connect's worst-case duration in the rare case they race with an in-flight connect)
without touching the terminal-retry/auto-skip state machine's actual transition logic — `_play()`
still runs to completion synchronously from the pump task's perspective, `tick()` still drives
`_onPlaybackFailed`/retry pacing off `_state` and `_lastAttemptMs` exactly as today, just reading a
polled result instead of a live return value. Option C is not rejected, just not justified yet —
revisit if Option B's "wait it out" compromise turns out to matter in practice (e.g. if users
frequently switch away from WebRadio while it's failing to connect and find that annoying).

**Human-approved 2026-08-04.** Sent to VE for a testability challenge on the state-machine boundary
before implementation, per this project's own standing practice (VE review before code, not after,
per TASK-397's precedent this session). VE findings recorded below once returned.

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

1. **Is "you can't cancel out of a CONNECTING state" actually a UX regression, or a wash?**
   Currently, mid-connect, the *entire device* is frozen — you can't press anything, anywhere, so
   there's no real "cancel" experience to preserve today. Option B's compromise (WebRadio's own
   controls specifically don't respond during CONNECTING, but the rest of the device does) is
   arguably a strict improvement over the status quo, not a new limitation — worth confirming this
   framing holds up rather than assuming it during implementation.
2. **Is `WR_PUMP_ACK_TIMEOUT_MS = 10000` the right bound once `suspend()` can legitimately wait out
   a real in-flight connect (not just a stuck `Audio::loop()`)?** Tonight's observed range was
   7099-9425ms; 10000ms covers it with only a ~600ms-1900ms margin against the worst tonight
   actually produced. Should this widen, or should `suspend()` treat "waiting for a known
   CONNECTING state" differently (no error log, since it's expected) from "actually stuck"?
3. **Does the ICY/title/marquee code path (`_drawTitleZone()`, already flagged in
   `M-WEBRADIO-DIAG-SURFACING.md` for a retry-countdown addition) need any change under Option B?**
   Likely not — `_state == CONNECTING` already drives the "Connecting..." marquee text today; a
   polled-result model doesn't change what `tick()` does with `_state` once it's set, just how the
   transition into PLAYING/ERROR_* gets triggered.
4. **Should this land before or after `M-WEBRADIO-DIAG-SURFACING`'s Tier 1 (retry countdown)?**
   That design flagged its own interaction with TASK-393's freeze mechanism (periodic `_dirty`
   while parked). The two are touching adjacent but different code (this doc: the CONNECTING
   transition itself; that doc: the parked-in-`ERROR_*` marquee) — probably independent and
   order-agnostic, but worth a second look once both are closer to implementation.

## Exit criteria

- ~~VE testability review of the CONNECTING-state changes~~ — **done, 2026-08-04, see VE review
  section above.** 4 blocking findings; not yet resolved. The three items below still apply once
  implementation happens, but implementation itself is blocked on addressing those findings first
  (in particular: the `_play()`-re-entrancy rule from finding #1, the mandatory teardown fix from
  finding #2, and finding #4's own added exit criterion for re-entrant control input during
  CONNECTING).
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
