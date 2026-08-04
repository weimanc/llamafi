# Design — moving WebRadio's `connecttohost()` off loopTask (TASK-398)

> Owner: Architect
> Status: draft
> Date: 2026-08-04
> Feeds: —
> Tracked-as: TASK-398
> Registers: —

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

**Draft lean, not an accepted decision — needs human sign-off, and should go to VE for a
testability challenge on the state-machine boundary before any implementation, per this project's
own standing practice (VE review before code, not after, per TASK-397's precedent this session).**

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

- VE testability review of the CONNECTING-state changes specifically (the `_stopAudio`/`suspend`
  gating, and the pump-task result-polling handoff) before implementation — per this session's own
  standing practice, not a formality.
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
