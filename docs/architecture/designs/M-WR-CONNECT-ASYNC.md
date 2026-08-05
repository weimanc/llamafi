# Design — moving WebRadio's `connecttohost()` off loopTask (TASK-398)

> Owner: Architect
> Status: accepted (lean) — human-approved 2026-08-04. Four VE passes same day, iterating to
> consensus per explicit human direction. First: 4 blocking findings against the original
> two-requirement sketch. Second: the fix was incomplete (`_stopAudio()`, not just `_play()`, was
> the real blocking primitive; a flag-only teardown left a permanent state wedge) — fixed via an
> explicit request/result-slot mechanism. Third: confirmed the use-after-free and permanent-wedge
> bugs were genuinely closed, but found 4 more gaps — most severely, a dropped Spotify TLS-resume
> call reintroducing `tlsYield` starvation (a bug class fixed five times before this session) on
> ordinary STOP/eject use. Fourth: confirmed 2 of the third revision's 4 fixes held up exactly as
> specified, but found the other 2 each had a residual gap of their own — a different
> early-arrival hole reintroducing the same permanent wedge, and the TLS-resume fix's "same
> substitution" shorthand leaving the `FAILED` branch (the single most common outcome) unguaranteed.
> This revision closes the early-arrival hole with explicit `ABORT`/`TEARDOWN` branches, spells out
> every `tick()` reconciliation branch in full rather than by cross-reference, corrects a
> misdiagnosed "residual race" (already closed by this file's own task-priority setup), and
> re-adds a `wrVol` fix the second revision had accidentally dropped. Fifth pass (2026-08-05): the
> narrowest result yet — 1 blocking finding (both `TEARDOWN` branches deleted `s_wr_audio` without
> nulling the pointer afterward, a deterministic dangling-pointer bug every other call site in the
> file would trip on), 1 related non-blocking; everything else re-verified sound. This revision
> adds the missing `s_wr_audio = nullptr` (mirroring `suspend()`'s own existing two-statement
> cleanup exactly) and clarifies a mutex-scoping detail. **Not yet re-reviewed — a sixth VE pass is
> next, not implementation.**
> Date: 2026-08-04 (last revised 2026-08-05)
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
- `_stopAudio()` **(the shared primitive fix — still correct in shape, but its guard's write must
  respect request priority, per VE third-pass finding #4)**: gains a branch at the top —
  `if (_state == WRPlayState::CONNECTING) { if (s_wrPumpRequest != TEARDOWN) s_wrPumpRequest =
  ABORT; return; }` — skipping the mutex take and `stopSong()` call entirely (nothing is playing
  yet at the codec level; there's nothing to stop), and **never downgrading an already-posted
  `TEARDOWN` back to `ABORT`** (third-pass finding #4: without this check, `resume()`'s config-diff
  branch calling `_stopAudio()` while a `TEARDOWN` from an earlier `suspend()` is still pending
  would silently cancel the arena/`Audio` release, leaking both past the session that was supposed
  to end them — `TEARDOWN` must always win over `ABORT` once posted). Every existing behavior for
  every *other* state (`PLAYING`, `ERROR_*`, etc.) is unchanged. Because every caller VE traced
  across all three passes (eject, STOP, `_togglePlay()`'s stop branch, `dbgSet`'s
  `wrEject`/`wrStop`, `resume()`'s config-change branch at `webRadioApp.h:502`) all go through this
  one shared function, fixing the guard once fixes the *mutex-blocking* half of the problem for all
  of them — but **not the whole problem for two of them**, see the STOP-button fix below (third-pass
  finding #2) and the TLS-resume fix in the `tick()` section (third-pass finding #1) — both are
  real gaps this primitive-level fix alone does not close.
- **STOP transport button (`webRadioApp.h:968-972`) and `dbgSet`'s `wrStop`
  (`:1224-1228`) — VE third-pass finding #2, a real gap the `_stopAudio()` fix above does not
  cover.** Both call `_stopAudio()` and then unconditionally force `_state =
  WRPlayState::STOPPED` immediately afterward — harmless today (`_stopAudio()` already sets that
  same value unconditionally at the end of its normal path), but once `_stopAudio()` skips that
  line specifically for `CONNECTING` (the fix above), these two call sites' own redundant
  assignment overwrites `_state` back to `STOPPED` *immediately*, before the pump has actually
  processed the posted `ABORT` — defeating `_play()`'s own re-entrancy guard for any subsequent tap
  (which reads `_state`, not the request slot) and reintroducing the exact blocking freeze this
  design exists to remove, reachable via ordinary STOP-then-retap or STOP-then-eject. **Fix: delete
  the redundant `_state = WRPlayState::STOPPED` line at both sites** — it was already dead code in
  every other state (`_stopAudio()` sets it), and now actively harmful in the one state where
  `_stopAudio()` deliberately doesn't. `tick()`'s reconciliation (below) becomes the sole owner of
  this transition, consistently, for every caller. **Confirmed by VE's fourth pass via a file-wide
  grep for every `_state = WRPlayState::STOPPED`/`_state = STOPPED` write**: exactly these two plus
  `_stopAudio()`'s own line — a fourth candidate site (the stream-death detector) was independently
  checked and confirmed to run only under `_state == PLAYING`, never reachable during `CONNECTING`,
  so it needs no change.
- **`dbgSet`'s `wrVol` handler (`webRadioApp.h:1346-1361`) — flagged by VE's first pass as a third,
  independent freeze source, and re-flagged by the fourth pass after this doc's second revision
  accidentally dropped it while rewriting this section.** Uses a raw, unbounded
  `xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY)`, inconsistent with the short-timeout,
  degrade-gracefully idiom `wrVolumeSink()` (`webRadioApp.h:328-338`) already uses for the real
  touch-drag volume path two hundred lines away. Not touched by the request/result mechanism above
  (volume changes don't need to survive a `CONNECTING` window the way connect/stop/teardown do) —
  **explicitly in scope for this revision, fixed the same way `wrVolumeSink()` already is**: switch
  to the short `WR_PUMP_READ_TIMEOUT_TICKS` take with the same graceful-degrade-on-timeout behavior,
  no reason for the debug setter to be less safe than the production gesture path it mirrors.
- `suspend()`: the `#ifdef MEMBUDGET_PHASE1` teardown block gains the same check — if `_state ==
  CONNECTING` when `suspend()` runs (the preceding `_stopAudio()` call already posted `ABORT` or
  left an existing `TEARDOWN` alone per the priority-respecting guard above; this line then
  overwrites to `TEARDOWN` unconditionally, since leaving the app entirely is always at least as
  strong an intent as stopping), skip `wrTeardownPumpTask()` and the direct `delete s_wr_audio`
  **only** — post `s_wrPumpRequest = TEARDOWN` instead. **Disambiguating non-blocking finding #5:**
  this skips only the audio-teardown steps inside the `#ifdef MEMBUDGET_PHASE1` block; execution
  falls through normally to the rest of `suspend()`'s body afterward (the coalesced
  `_lastStationDirty`/`s_wrVolPctDirty` settings-save logic) — that logic is cheap, RAM-only, and
  doesn't touch WebRadio audio state, so there's no reason to skip it and doing so would silently
  drop a pending settings write. Every other `suspend()` state (nothing in flight) keeps today's
  exact synchronous teardown — this only changes behavior for the specific unsafe case.

**Consumer side (the pump task, `wrPumpTaskBody`) — VE fourth-pass finding #1's fix included: the
first version of this section only ever handled `s_wrPumpRequest == CONNECT` at the top-of-loop
check, with no branch for `ABORT`/`TEARDOWN` arriving before the pump ever reads the request at
all (a real, ordinarily-reachable window — the pump's own `vTaskDelay(WR_PUMP_CADENCE_TICKS)`
between cycles, not a sub-instruction race) — reintroducing the second pass's permanent-`_state`-
wedge, plus a resource leak on the `TEARDOWN` case, via a hole this doc's own clear-on-commit fix
had newly opened one revision ago.** At the top of each cycle, `wrPumpTaskBody()` branches on
`s_wrPumpRequest` (an `if`/`else if` chain — the branch below *replaces* that cycle's normal pump
servicing, it does not run in addition to it, per non-blocking finding #5):
- **`== CONNECT`**: clear `s_wrPumpRequest = NONE` (the commit point — see below for why this
  specific clear is now provably race-free, unlike the fourth-pass finding it might look similar
  to), take the mutex, call `connecttohost()` — the multi-second blocking call, now fully isolated
  to this task, never touching `loopTask`. Once it returns (success or fail), re-check
  `s_wrPumpRequest`'s **current** value (correctly reflecting anything `loopTask` posted *during*
  the connect, since the earlier clear only touched the value at the commit instant):
  - **`TEARDOWN`**: if the connect had actually succeeded, call `stopSong()` to clean up **(still
    under the mutex the pump already holds from the `connecttohost()` call above — not a separate
    take)**; delete `s_wr_audio` **and set `s_wr_audio = nullptr` immediately after — VE fifth-pass
    finding #1: every other call site that touches `s_wr_audio` (`_play()`'s guard, `wrAudio()`'s
    inline guard, `_stopAudio()`'s guard, `wrVolumeSink()`/`wrVol`, the pump's own steady-state
    `loop()` check) treats a non-null pointer as proof the object is live; leaving it dangling
    after `delete` — as an earlier version of this section did — crashes or corrupts on the very
    next touch (a subsequent `_play()`, a bare re-eject, or a freshly-created pump task's first
    cycle), the identical "load-bearing second half of a two-part cleanup doesn't survive
    relocation" failure mode the TLS-resume line hit twice already. Mirrors today's synchronous
    `suspend()` exactly (`webRadioApp.h:559`: `if (s_wr_audio) { delete s_wr_audio; s_wr_audio =
    nullptr; }`) — both statements, not just the first.**; release the arena
    (`mb_arena_release()`); set `s_wrPumpResult = TORN_DOWN`; **null `s_wrPumpTask` last,
    immediately before `vTaskDelete(NULL)`** (VE second-pass finding #4's exact fix) so
    `wrEnsurePumpTask()`'s existing `if (s_wrPumpTask) return;` guard continues to see "pump still
    here" for the entire window until the pump's actual self-deletion.
  - **`ABORT`**: if the connect had succeeded, call `stopSong()` (the user asked to stop); set
    `s_wrPumpResult = ABORTED`; the pump task itself is **not** torn down (persists across a stop,
    matching today's existing behavior) — only the in-flight connect's outcome is discarded.
  - **`NONE`** (nothing else was requested while the connect was outstanding): set
    `s_wrPumpResult = CONNECTED` or `FAILED` per the real outcome.
- **`== ABORT`** (arrived before any connect started this cycle — nothing to stop, no mutex needed):
  clear `s_wrPumpRequest = NONE`, set `s_wrPumpResult = ABORTED` directly.
- **`== TEARDOWN`** (same early-arrival case, stronger intent): clear `s_wrPumpRequest = NONE`,
  delete `s_wr_audio` **and set `s_wr_audio = nullptr`** (same fix as the post-connect branch
  above — this early-arrival path was written to explicitly mirror it, so it inherited the same
  gap and gets the same fix), release the arena, set `s_wrPumpResult = TORN_DOWN`, null
  `s_wrPumpTask` last, self-delete — the identical terminal sequence as the post-connect
  `TEARDOWN` case above, just skipping `stopSong()` since nothing was ever dispatched this cycle
  (and skipping the mutex take entirely too, for the same reason). (`TEARDOWN` is only ever
  posted alongside `suspend()` actually running, per the producer-side spec above — so by
  construction the user has already left WebRadio whenever this branch fires, consistent with
  `tick()`'s reconciliation-on-return story below, not a new case that story doesn't cover.)
- **else** (`NONE` — genuinely nothing requested): today's existing steady-state behavior,
  unconditionally — take the mutex, call `s_wr_audio->loop()`, give the mutex (a documented fast
  no-op when nothing is running).

**On the clear-on-commit step specifically, corrected framing (non-blocking finding #4 from the
fourth pass):** the previous revision described a "razor-thin, accepted residual race" between the
pump reading `CONNECT` and clearing it to `NONE`, reached for a compare-and-swap justification for
not closing it. VE's fourth pass traced this file's own documented scheduling facts —
`WR_PUMP_PRIORITY = 2`, explicitly "above `loopTask` (prio 1)" (`webRadioApp.h:296`), both pinned
to `APP_CPU_NUM` — and found that under standard FreeRTOS priority-based preemption, with no
blocking call between the read and the clear, `loopTask` (strictly lower priority) cannot actually
interleave with that specific pair at all: the window is not narrow, it's already zero-width by
construction. **The real gap was never that window — it was the missing `ABORT`/`TEARDOWN`
top-of-loop branches this revision adds above (fourth-pass finding #1).** No compare-and-swap
primitive is needed anywhere in this design; the file's own existing priority setup already
provides the guarantee the previous revision thought it had to accept a compromise to live
without.

**`tick()` (runs every iteration while WebRadio is the current app):** polls `s_wrPumpResult` each
iteration, non-blocking, one of four branches — **each spelled out completely below, not by
shorthand, per VE fourth-pass finding #2: the third pass's TLS-resume fix was precise for two
branches and imprecise for a third, and the imprecise one is the single most common outcome this
whole design exists to fix (421 ordinary connect failures per the Context section), so "same
substitution" is not an acceptable specification for a safety-critical line a third time.**
- `CONNECTED` → today's existing PLAYING-transition logic runs exactly as it does today (seed
  timers, `_playingSinceMs`, `_settled = false`, etc.), reading the result instead of a live return
  value. Nothing to resume — TLS stays yielded for the PLAYING session, unchanged from today.
- `FAILED` → re-derived directly from the current synchronous failure path this branch replaces
  (`webRadioApp.h:1710-1717`), in full, not by naming two of its four statements: `_state =
  WRPlayState::ERROR_UNREACHABLE;` then **`if (_spotifyYielded) { spotifyTask::tlsResume();
  _spotifyYielded = false; }`** then `_onPlaybackFailed(/*connectFail=*/true);`. The resume call
  sits between the other two in the original code and is not optional or implied — it is the fix
  for the single most common code path in this entire design.
- `ABORTED` or `TORN_DOWN` → `_state = WRPlayState::STOPPED;` then **`if (_spotifyYielded) {
  spotifyTask::tlsResume(); _spotifyYielded = false; }`** (identical call, spelled out here too
  rather than cross-referenced, so no branch in this list is ever the "implied" one again).

`_play()` unconditionally yields Spotify's TLS session before ever reaching the connect call
(`webRadioApp.h:1613-1616`), so `_spotifyYielded == true` for the entire `CONNECTING` window by
construction; `_stopAudio()`'s normal (non-`CONNECTING`) path already resumes it near the end of
its body, but the new early-return added above skips straight past that resume for every caller —
meaning every one of `FAILED`/`ABORTED`/`TORN_DOWN`, not just the two the third pass's fix
originally named, must resume TLS explicitly or permanently leak Spotify's TLS yield reference
count (`spotifyTaskStorage.cpp`'s `s_tlsYieldReqCount`, TASK-287) — reintroducing `tlsYield`
starvation, a bug class this project has already root-caused and fixed five separate times
(`project_tlsyield_starvation.md`), via a sixth, previously-unconsidered mechanism, on nothing more
exotic than an ordinary failed connect or a STOP tap. Each branch clears `s_wrPumpResult = NONE`
after handling it. This single poll, running unconditionally at the top of `tick()`, closes the wedge
VE's second pass found without any special-case logic in `resume()`: **`resume()`'s existing
autoplay guard already requires `_state == WRPlayState::STOPPED` before calling `_play()` again**
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
- **Second revision**: replaced the ad-hoc flags with the request/result-slot mechanism — fixed
  `_stopAudio()` at the primitive (which transitively fixed `suspend()`'s call, plus a seventh call
  site inside `resume()`'s config-diff branch neither VE pass had enumerated), and gave `tick()` an
  explicit, unconditional poll that reconciles `_state` on every iteration rather than relying on
  any one caller to do it.
- **Third VE pass** (see VE review section above): confirmed the second revision correctly closed
  the use-after-free and the permanent `_state` wedge, but found four new gaps in the mechanism's
  own completeness — most severely, `_stopAudio()`'s new early-return silently dropped the Spotify
  TLS-resume call, reintroducing `tlsYield` starvation (a bug class fixed five times before this
  session) on ordinary STOP/eject use, not a race. Also found: the STOP button and `wrStop` debug
  setter still force `_state = STOPPED` immediately after calling `_stopAudio()`, defeating the
  whole mechanism for that specific tap; the request slot was never specified to clear itself,
  meaning a successful connect as originally drafted would free-run into an infinite 2ms reconnect
  loop; and `resume()`'s config-diff branch could silently downgrade an already-posted `TEARDOWN`
  back to `ABORT`, leaking the arena and pump task past their intended session. 4 blocking findings,
  2 non-blocking.
- **Third revision**: added the missing TLS-resume call to `tick()`'s `ABORTED`/`TORN_DOWN`
  reconciliation; deleted the two redundant, now-harmful `_state = STOPPED` writes at the STOP
  button and `wrStop`; specified the request-slot's clear-on-commit (with a "narrow residual race"
  documented as accepted rather than engineered around); made `_stopAudio()`'s guard respect
  request priority (`TEARDOWN` always wins over `ABORT`, never downgraded).
- **Fourth VE pass** (see VE review section above): confirmed two of the third revision's four
  fixes hold up exactly as specified (the `TEARDOWN`-priority guard; the STOP-button/`wrStop` fix,
  checked via a file-wide grep). But found the other two each had a real gap: the clear-on-commit
  fix, in closing the third pass's infinite-reconnect-loop bug, opened a *different*,
  ordinarily-reachable hole — the request slot's consumer never handled `ABORT`/`TEARDOWN` arriving
  *before* the pump had read a posted `CONNECT` at all, reintroducing the permanent `_state` wedge
  plus a resource leak, reachable via two ordinary back-to-back `set` commands, not adversarial
  timing. And the TLS-resume fix was precise for `ABORTED`/`TORN_DOWN` but only said "same
  substitution" for `FAILED` — the single most common outcome (421 occurrences per the Context
  section) — leaving the exact TLS-resume line the fix was about at risk of being dropped again
  through the one branch its own precision didn't reach. 3 blocking findings, 3 non-blocking
  (including confirming the doc's own "accepted residual race" was misdiagnosed — FreeRTOS
  priority preemption on this file's documented task priorities already closes that specific
  window; the real gap was the missing branches, not that race).
- **Fourth revision**: added explicit `ABORT`/`TEARDOWN` top-of-loop branches to the consumer side
  (not just the `CONNECT` branch), closing the early-arrival hole; spelled out all three `tick()`
  reconciliation branches in full rather than by cross-reference, so the TLS-resume line is
  explicit everywhere it's needed; corrected the "residual race" framing to reflect that it's
  already closed by this file's own priority setup rather than merely accepted; re-added the
  `wrVol` debug-setter fix that the second revision had accidentally dropped when it rewrote this
  section (VE's first pass had flagged it; three revisions passed before the fourth pass caught the
  drop).
- **Fifth VE pass** (see VE review section above): the narrowest result yet — 1 blocking finding, 1
  related non-blocking, down from 3-4 each of the prior four passes. Confirmed independently sound:
  the full `ABORT`/`TEARDOWN`/`CONNECT`/`NONE` branch coverage, the `FAILED` branch's TLS-resume
  ordering against the real source, the corrected residual-race framing (extended to all four
  branches, not just the one previously checked), and the re-added `wrVol` fix. The one gap: both
  `TEARDOWN` branches (post-connect and early-arrival) specified `delete s_wr_audio` but never
  `s_wr_audio = nullptr` afterward — a deterministic dangling-pointer bug, not a race, since every
  other call site treats a non-null pointer as proof the object is live. The exact "second half of
  a two-part cleanup doesn't survive relocation" failure mode the TLS-resume line hit twice already,
  recurring a third time for a different pair of statements. Non-blocking: the post-connect
  `TEARDOWN` branch's `stopSong()` call wasn't explicitly marked as still running under the mutex
  already held from the `connecttohost()` call.
- **This revision**: adds `s_wr_audio = nullptr` immediately after both `delete s_wr_audio`
  instances (mirroring today's synchronous `suspend()` at `webRadioApp.h:559` exactly — both
  statements, not just the first), and clarifies the post-connect `TEARDOWN` branch's `stopSong()`
  call runs under the mutex already held, not a separate take. **Not yet re-reviewed — a sixth VE
  pass is next, not implementation.** Given the fifth pass's own assessment that this is a narrow,
  mechanical, well-precedented fix, the sixth pass can reasonably be scoped narrowly to confirming
  just this fix rather than re-auditing the whole mechanism from scratch again — though it remains
  an independent reviewer's call whether a broader check is still warranted, not a constraint
  imposed here.

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

### Third pass (2026-08-04)

Independent re-verification against the current source (`app/src/webRadioApp.h`, 1961 lines — same
length the second pass reported, confirming no implementation has landed since; line numbers
re-derived from scratch, not trusted from either prior pass or the doc's own citations). This pass
does not re-litigate whether the request/result-slot *idea* is sound — it is, and it is the right
shape — it traces the mechanism as specified against every call site that touches `_state`,
`s_wr_audio`, or `_spotifyYielded` during a `CONNECTING` window, the same way the first two passes
traced `_stopAudio()`/`suspend()`. Conclusion up front: **the revision correctly closes the two bugs
the first two passes found (the use-after-free and the permanent `_state` wedge), but introduces two
new bugs of its own, both reachable through ordinary use, not just adversarial timing — one of them
(TLS-yield starvation) is a bug class this project has already root-caused and fixed five separate
times (see `project_tlsyield_starvation.md`), and this design reintroduces it via a different
mechanism than any of those five.** Four findings, four blocking.

1. **BLOCKING — `_stopAudio()`'s new `CONNECTING` early-return skips the Spotify TLS-resume side
   effect, reintroducing tlsYield starvation (a bug class this project has fixed five times already,
   via a sixth, new mechanism).** `_stopAudio()` (`:1516-1536`) today unconditionally resumes
   Spotify's yielded TLS session near its end: `if (_spotifyYielded && resumeTls) {
   spotifyTask::tlsResume(); _spotifyYielded = false; }` (`:1532-1535`). The design's fix adds an
   early `return` at the top of `_stopAudio()` when `_state == CONNECTING` — which necessarily skips
   this block along with everything else past it (`_pendingAction` reset, play-time zeroing). By the
   time `_state == CONNECTING` is reachable at all, `_spotifyYielded` is already `true`: `_play()`
   sets `_state = CONNECTING` at `:1564`, then unconditionally yields Spotify's TLS at `:1613-1616`
   ("Yield Spotify TLS for the duration of playback... both `new Audio()` and `connecttohost()` need
   ~50 KB contiguous heap") *before* ever reaching the connect call itself — so the entire `CONNECTING`
   window has `_spotifyYielded == true` by construction. Every call site that reaches `_stopAudio()`
   while `_state == CONNECTING` — eject (`:957-958`), the STOP transport button (`:968-969`),
   `_togglePlay()`'s stop branch (`:1747-1749`, which literally names `CONNECTING` in its own
   condition), `wrEject` (`:1213-1214`), `wrStop` (`:1224-1225`), and `suspend()`'s own first line
   (`:545`) — now returns without ever calling `spotifyTask::tlsResume()`. Traced `tlsYield()`/
   `tlsResume()` in `spotifyTaskStorage.cpp` (`:646-701`): `s_tlsYieldReqCount` is a real reference
   count (TASK-287), incremented once per `tlsYield()` and decremented once per matching
   `tlsResume()`; Spotify's own service loop stays stopped (`s_tlsStopped`) until the count returns to
   zero. A dropped `tlsResume()` here isn't cosmetic — it's a permanently leaked yield: the count never
   returns to zero from this session, and nothing else in the design's new machinery calls
   `tlsResume()` on this path either. The pump task (`wrPumpTaskBody`, a free function per second-pass
   finding #3's own already-established reasoning) has no access to `_spotifyYielded` — an instance
   member (`:1460`) — so it cannot correctly decide whether to call it even if the doc's ABORT/TEARDOWN
   branches wanted it to (and as specified, they don't mention it at all). `tick()`'s new poll *is* a
   member function and could reach `_spotifyYielded`, but the doc's spec for its `ABORTED`/`TORN_DOWN`
   branches ("`_state = WRPlayState::STOPPED`") says nothing about TLS. Net effect: pressing STOP,
   eject, or PLAY/PAUSE-to-stop during an ordinary in-flight connect attempt — not a rare race, the
   single most natural thing a user does when a "Connecting..." screen sits there for several
   seconds — silently and permanently starves Spotify's TLS session for the rest of the boot. **Fix:**
   the doc must specify where the resume happens now that `_stopAudio()` can no longer do it
   unconditionally — the natural owner is `tick()`'s new poll, which has instance access: its
   `ABORTED`/`TORN_DOWN` branches need `if (_spotifyYielded) { spotifyTask::tlsResume(); _spotifyYielded
   = false; }` added explicitly, stated as part of the mechanism, not left to be inferred.

2. **BLOCKING — the STOP transport button (`:968-972`) and the `wrStop` debug setter
   (`:1224-1228`) unconditionally force `_state = WRPlayState::STOPPED` immediately after calling
   `_stopAudio()`, which the design doesn't touch and which defeats the entire async mechanism for
   this specific tap.** Both are, today, harmless redundancy — `_stopAudio()` itself already
   unconditionally sets `_state = STOPPED` at `:1524` in every case, so the caller's own assignment is
   a no-op. The design's fix makes `_stopAudio()` skip that line specifically when `_state ==
   CONNECTING` (finding #1's early return) — but does not touch these two call sites, so they still
   force `_state = STOPPED` immediately, synchronously, regardless of whether the pump has actually
   processed the `ABORT` yet. Concretely: user taps a station (CONNECTING), immediately presses STOP —
   `_stopAudio()` posts `ABORT` and returns; the STOP handler's very next line then overwrites
   `_state` to `STOPPED` right away, before the pump's `connecttohost()` has returned. Two
   consequences, both reachable with nothing but ordinary fast button-mashing: (a) it directly
   contradicts the exit criteria's own stated expectation for this exact tap ("`_state` transitions to
   `STOPPED` once the in-flight connect actually resolves (**not immediately**, and not stuck
   forever)") — so a Developer who actually runs that check would catch this at test time, but the
   *design* itself doesn't specify the fix, so it would have to be rediscovered there rather than
   fixed here; (b) worse, it defeats `_play()`'s own requirement-1 re-entrancy guard for *any*
   subsequent action, because that guard reads `_state`, not the request slot: with `_state` now
   `STOPPED`, a station tap immediately after pressing STOP sails past `_play()`'s guard, reaches
   `_play()`'s own `_stopAudio(/*resumeTls=*/false)` call at `:1544` — which, since `_state` again
   reads `STOPPED` (not `CONNECTING`) at that exact call, takes the *original*, unguarded, blocking
   `xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY)` path (`:1520`) — and the pump task is still
   genuinely inside the first `connecttohost()` call, still holding that mutex. This reintroduces the
   full multi-second `loopTask` freeze the entire design exists to eliminate — reachable via
   STOP-then-retap, not a contrived race. The same false signal also reaches `suspend()`: if the user
   instead ejects right after pressing STOP, `suspend()`'s `_stopAudio()` call at `:545` likewise
   reads `_state == STOPPED` and takes the same blocking path, freezing `loopTask` during exactly the
   one path (`switchApp`-away during `CONNECTING`) both prior passes and this doc's own exit criteria
   treat as the single most important case to verify doesn't block. **Fix:** requirement to fix
   `_stopAudio()`'s call sites individually after all, for these two specifically — either delete the
   redundant `_state = WRPlayState::STOPPED` lines at `:970`/`:1226` (let `tick()`'s reconciliation own
   the transition, matching finding #1's fix) or make them conditional (`if (_state !=
   WRPlayState::CONNECTING) _state = WRPlayState::STOPPED;`). The doc's claim that fixing
   `_stopAudio()` "at the primitive... fixes all of them, including `suspend()`'s own call... without
   needing to touch each call site separately" is false for these two, because they do something to
   `_state` beyond just calling `_stopAudio()`.

3. **BLOCKING — the consumer-side mechanism never specifies clearing `s_wrPumpRequest` back to
   `NONE`, and the pump task's own loop structure makes "no connect currently in flight" trivially
   true every time the check is reached — as literally specified, a successful connect free-runs into
   an infinite reconnect loop.** The mechanism's opening declaration promises `s_wrPumpRequest` is
   "written by `loopTask`, read/**cleared** by the pump task," but the detailed "Consumer side"
   walkthrough that actually describes the algorithm never says when that clearing happens. Traced the
   implied control flow against `wrPumpTaskBody()`'s existing structure (`:349-382`, a single-threaded
   `for(;;)` loop): the doc's check is "at the top of each cycle, if `s_wrPumpRequest == CONNECT` **and
   no connect is currently in flight**, take the mutex and call `connecttohost()`." But "no connect
   currently in flight" isn't a variable the doc defines anywhere — and because the task is
   single-threaded, it's *always* true at that exact check point: if a connect genuinely were in
   flight, the task would be blocked inside `connecttohost()`, not back at the top of the loop to be
   asked the question. So the qualifier is a no-op as specified. Absent an explicit reset of
   `s_wrPumpRequest` to `NONE` somewhere in the consumer-side steps (e.g. immediately upon consuming a
   `CONNECT`, before or after issuing the call), `s_wrPumpRequest` stays `CONNECT` forever after the
   first successful play — and the very next pump cycle (`WR_PUMP_CADENCE_TICKS` = 2 ms later, `:297`)
   re-evaluates the same top-of-loop check, sees `CONNECT` again, and calls `connecttohost()` a second
   time — tearing down the connection it just established and reconnecting, then doing it again 2 ms
   later, indefinitely, hammering `s_wrAudioMutex` the entire time (during which every per-tick
   snapshot read and volume-drag take degrades to a stale value on every single attempt, since the
   mutex is now perpetually busy). This is not a rare interleaving — it is the deterministic outcome
   of implementing the "Consumer side" section exactly as written, on literally the first successful
   connect. **Fix:** state explicitly, as part of the consumer-side steps (not just the file-static's
   declaration comment), that the pump clears `s_wrPumpRequest = NONE` at the moment it commits to
   starting a connect (before calling `connecttohost()`, so a same-instant `ABORT`/`TEARDOWN` write
   from `loopTask` isn't lost — see finding #4 for the related ordering concern) — and confirm that is
   the *only* mechanism relied upon to stop the branch from re-firing, since no other "in-flight"
   tracking variable exists in the design.

4. **BLOCKING — `resume()`'s config-diff branch (`:494-512`, the doc's own "seventh call site") can
   downgrade an already-posted `TEARDOWN` back to `ABORT`, silently skipping the arena/Audio release
   the prior `suspend()` had already committed to, and leaking the pump task past the session that was
   supposed to end it.** Re-traced the specific sequence the doc's own revision highlights as its
   headline fix (fixing `_stopAudio()` "at the primitive... transitively covers... this newly-found
   seventh site"): user starts a connect, ejects away (`suspend()` sees `_state == CONNECTING`, posts
   `s_wrPumpRequest = TEARDOWN`, returns fast per the doc's `suspend()` requirement) — `_state` is left
   at `CONNECTING` (nothing in the design writes to it until `tick()`'s poll reconciles a landed
   result, and `tick()` doesn't run while WebRadio is suspended, per second-pass finding #3's
   already-established reasoning, unchanged by this revision). If the user then edits WebRadio's
   country or bitrate cap in Settings (entirely plausible within the several-second-to-unbounded
   window a real connect/DNS attempt can take per finding #2 of the first pass) and re-enters WebRadio
   before the deferred teardown has actually landed, `resume()` runs with `_cfgCountry`/`_cfgCap` now
   differing from `g_settings` — its diff branch fires `if (_state != WRPlayState::STOPPED)
   _stopAudio();` (`:502`) because `_state` is still `CONNECTING` (`!= STOPPED`). `_stopAudio()`'s new
   guard (finding #1's fix) unconditionally posts `s_wrPumpRequest = ABORT` whenever `_state ==
   CONNECTING` — with no check of what's already queued — **overwriting the still-pending `TEARDOWN`
   with a weaker `ABORT`.** If the pump hasn't yet consumed the request (a real possibility across a
   Settings-navigation-length window), it resolves the connect, sees `ABORT` instead of `TEARDOWN`, and
   per the doc's own ABORT branch ("the pump task itself is **not** torn down... only the in-flight
   connect's outcome is discarded") does *not* delete `s_wr_audio`, does *not* release the arena via
   `mb_arena_release()`, and does *not* self-terminate. This directly contradicts the original
   `suspend()` call's own intent (`suspend()`'s comment at `:552-557`: "release the JIT arena when
   leaving WebRadio so the next entry's station fetch has full heap") and the entire memory-budget
   motivation `MEMBUDGET_PHASE1`/`mb_arena_*` exists for — the arena and pump task silently outlive the
   session that was supposed to end them, for as long as this exact interleaving takes to next occur
   (which self-corrects only by accident, on the next unrelated `suspend()` that happens to *not* race
   a pending teardown). **Fix:** the shared `_stopAudio()` guard must not downgrade a request that's
   already stronger than `ABORT` — e.g. `if (s_wrPumpRequest != s_wrPumpRequest_TEARDOWN) s_wrPumpRequest
   = ABORT;` (or equivalent ordering: `TEARDOWN > ABORT > CONNECT`, never move down the ordering via
   `_stopAudio()`'s blind write). This is a distinct bug from second-pass finding #4 (the `s_wrPumpTask`
   null-timing question, which this revision's "pump nulls itself immediately before
   `vTaskDelete(NULL)`" answer does correctly close) — it's a request-priority-ordering gap the
   request/result model itself introduces and that finding never had reason to consider.

**Non-blocking:**

5. `suspend()`'s new `CONNECTING` branch is specified as "skip `wrTeardownPumpTask()` and the direct
   `delete s_wr_audio` **entirely** for this call — post `s_wrPumpRequest = TEARDOWN` instead and
   return." It's ambiguous whether "return" exits `suspend()` entirely or just the `#ifdef
   MEMBUDGET_PHASE1` block (`:546-561`) — if the former, it also skips the coalesced
   `_lastStationDirty`/`s_wrVolPctDirty` settings-save logic that follows at `:563-583`, silently
   dropping a pending `lastStation`/`webRadioVolumePct` write for that session whenever eject happens
   to land during a real `CONNECTING` race. Nothing about the "loopTask stays fast" motivation requires
   skipping the settings save specifically (it's a cheap RAM-only flag check, not a blocking call) — a
   sentence disambiguating the control flow before implementation would prevent this from being decided
   by accident.

6. Confirmed, for completeness, that `_play()`'s own early-return branches that set `_state` directly
   without going through the pump — `_debugForceConnFail` (`:1586-1598`) and the DMA-pool-too-low guard
   (`:1647-1657`) — both run *before* the point in `_play()` where a request would be posted (both are
   synchronous pre-flight checks on `loopTask`, unaffected by moving the actual `connecttohost()` call
   off it). No new risk here; noted so the next reviewer doesn't have to re-derive it, matching the
   documentation style of second-pass finding #6.

**Testability sign-off (third pass):** consensus **not** reached — go/no-go is **no-go**, four
blocking findings. The revision's central idea (an explicit request/result-slot pair, deletion
ownership moved to the pump, an unconditional `tick()` reconciliation poll) is the right shape and
correctly closes both bugs the first two passes found — the use-after-free and the permanent `_state`
wedge are genuinely gone. But the doc still stops its own call-site audit one layer too shallow, the
same failure mode both prior passes independently hit: it traces `_stopAudio()` and `suspend()` as
*callers of the mechanism* but not as *code with side effects beyond the mechanism* — the STOP
button/`wrStop` (finding #2) do something to `_state` besides calling `_stopAudio()`, and
`_stopAudio()` itself does something besides guarding the mutex (the TLS resume, finding #1) that its
new early-return silently drops. Findings #3 and #4 are gaps in the *new* machinery specifically —
the request-slot's own lifecycle (clearing) and priority ordering (`TEARDOWN` vs `ABORT`) were never
fully specified even though this revision's whole stated purpose was to specify the mechanism
"properly this time." Finding #1 is the most severe: it reintroduces a bug class (`tlsYield`
starvation) this project has already root-caused and fixed five times over multiple sessions, via a
sixth, previously-undocumented mechanism, and it's reachable by nothing more exotic than pressing
STOP while a station connects — not a race, not a timing window, just normal use. None of the four
findings require reopening the core design decision (Option B is still correct, the request/result
shape is still correct) — they are call-site and protocol-completeness gaps of the same character
both prior passes found, which suggests the actual process gap is that the doc's revisions keep
patching the specific bug the last VE pass named without re-running the full call-site/side-effect
audit against the newest version of the mechanism. Concretely falsifiable next step: add the missing
`tlsResume()` call to `tick()`'s `ABORTED`/`TORN_DOWN` branches (finding #1), fix the two call sites
that write `_state` directly instead of going through the guarded primitive (finding #2), specify
`s_wrPumpRequest`'s clearing point (finding #3), and give the shared `_stopAudio()` guard a
priority-preserving write instead of a blind one (finding #4) — then this needs a fourth pass, not
implementation, since three consecutive passes each finding real, previously-unflagged bugs in the
same document is itself a signal this mechanism has more surface area than a single VE pass reliably
covers in one sitting.

### Fourth pass (2026-08-04)

Independent re-verification against the current source (`app/src/webRadioApp.h`, still 1961 lines —
confirms no implementation has landed since the third pass; `app/src/spotifyTaskStorage.cpp`, 887
lines, for the TLS-yield ref-counting specifically; line numbers re-derived from scratch, not trusted
from any prior pass or the doc's own citations). This pass does not re-litigate whether the
request/result-slot idea is sound — three passes have now converged on "yes" — it re-derives, from the
actual source, whether *this specific revision's* four fixes (TLS-resume in `tick()`, deleting the two
redundant `_state` writes, the clear-on-commit spec, the `TEARDOWN`-priority guard) actually close what
they claim to close, and specifically hunts for defects that could only exist in *this* revision's new
text, per the brief. Conclusion up front: **the STOP-button/`wrStop` fix and the `TEARDOWN`-priority
fix both check out exactly as specified — confirmed independently, not just re-trusted. But the other
two claimed fixes each have a real gap: the clear-on-commit fix, in the course of correctly closing the
third pass's infinite-reconnect-loop bug, opens a new and structurally different hole in the same
mechanism — a real, sizeable window (not the "handful of instructions" one the doc explicitly accepts)
in which a `CONNECT` request can be silently overwritten before the pump ever consumes it, with nothing
in the mechanism ever processing the overwrite — reintroducing the second pass's permanent-`_state`-
wedge bug plus a resource leak, via a mechanism that could not have existed before this revision
specified the clearing point. And the TLS-resume fix, while correct for the two branches it explicitly
names, is specified with a precision gap for a third branch it doesn't — the same bug class the third
pass's own most-severe finding was about, recurring through the branch that fix didn't touch.** Three
findings, all three blocking.

1. **BLOCKING (most severe this pass) — the request slot's consumption model has exactly two entry
   points (top-of-loop `== CONNECT` check; post-connect-return check), and neither one ever processes
   an `ABORT`/`TEARDOWN` that overwrites a `CONNECT` before the pump has read it — reintroducing the
   second pass's permanent `_state` wedge, plus (when the overwritten value is `TEARDOWN`) a full
   resource leak, via a window this revision's own clear-on-commit fix newly opens.** Traced
   `wrPumpTaskBody()`'s actual loop (`webRadioApp.h:349-382`) against the mechanism as specified: the
   loop currently does `if (s_wrPumpStopReq) {...}`, then unconditionally `xSemaphoreTake` (blocking)
   + `s_wr_audio->loop()` + `xSemaphoreGive`, then `vTaskDelay(WR_PUMP_CADENCE_TICKS)` (`:297`,
   `pdMS_TO_TICKS(2)` — a real, **blocking** delay, during which the pump task is not merely
   "mid-instruction" but fully descheduled). The design's consumer-side steps require inserting a
   `CONNECT`-branch at the top of this loop and a second check after `connecttohost()` returns — but
   describe **no third path** for the case where `s_wrPumpRequest` is `ABORT` or `TEARDOWN` at the
   top-of-loop check (i.e., neither `== CONNECT` — so the connect-branch doesn't fire — nor
   "post-connect," since no connect was ever started this cycle). Concretely: `_play()` sets `_state =
   CONNECTING` and posts `CONNECT` (per the design, replacing today's `:1690-1694` blocking call); if,
   before the pump's *next* scheduled iteration reads that value — a real window, since the pump may be
   sitting inside its own 2 ms `vTaskDelay` or otherwise not yet back at the top of its loop, not a
   sub-instruction race — a second, ordinary loopTask action reaches `_stopAudio()`'s new `CONNECTING`
   guard (eject, STOP, `_togglePlay()`'s stop branch, `wrEject`, `wrStop`, or `suspend()`'s own call),
   it posts `ABORT` (or `TEARDOWN`, via `suspend()`'s subsequent unconditional upgrade) — **silently
   overwriting the still-unread `CONNECT`**. When the pump *does* next reach the top-of-loop check, it
   sees `s_wrPumpRequest != CONNECT` — the branch that would call `connecttohost()` never fires, so the
   *only other* place the design ever inspects the request slot ("once the connect returns") is never
   reached either, because no connect ever started. `s_wrPumpResult` is never written; `tick()`'s poll
   sees `NONE` forever; `_state` stays `CONNECTING` permanently — the exact bug the second pass named
   and this whole mechanism exists to prevent, resurrected through a path that could not have existed
   before *this* revision specified where the request gets consumed. Worse than the wedge alone: if the
   overwritten value was `TEARDOWN` (i.e., the user ejected), `s_wr_audio` is never deleted, the arena
   is never released via `mb_arena_release()`, and the pump task never reaches its self-`vTaskDelete`
   — precisely the leak `suspend()`'s own comment at `:552-557` exists to prevent, and the same class of
   leak the third pass's finding #4 fixed for a different code path. **This is reachable by ordinary
   use, not adversarial timing**: two loopTask actions issued back-to-back with no yield in between —
   concretely, `set wrPlay N` immediately followed by `set wrStop` or `set wrEject` in a single serial
   script, exactly the kind of two-command burst the doc's own proposed exit criteria plans to fire (see
   finding #3) — land within nanoseconds of each other on the same task, comfortably inside the pump's
   2 ms cadence gap, with no scheduling luck required at all. A human physically double-tapping this
   fast is implausible, but this codebase's own serial test-hook surface (the exact mechanism the doc
   cites as evidence of reachability for findings #1 and #4 in the first pass) makes it trivial to hit
   every time. **The doc's own "accepted, narrow residual race"** (pump reading `CONNECT` then clearing
   it to `NONE`, "a handful of instructions wide... measured in microseconds") **is a different, smaller
   window than this one, and does not cover it** — that race is about a same-instant clobber during the
   pump's own uninterruptible read-then-clear sequence (see non-blocking finding #4 below for why that
   specific window is likely fully closed by this file's own priority setup, not just narrow); this
   finding is about the much larger window *before* the pump has read the request at all, which the
   doc's residual-race paragraph never considers and which has a categorically worse outcome (permanent
   wedge + leak, not "one input dropped, connect resolves normally"). **Fix, one of:** (a) give the
   pump's top-of-loop check a second branch — `else if (s_wrPumpRequest == ABORT || s_wrPumpRequest ==
   TEARDOWN)`, resolving it immediately (no connect to abort, so this reduces to "set the terminal
   result / do the teardown steps / clear the request") without ever attempting `connecttohost()`; or
   (b) have `_stopAudio()`'s guard distinguish "request still reads `CONNECT`" (nothing has been
   dispatched yet — safe to just clear `s_wrPumpRequest` straight to `NONE` and reconcile `_state`
   directly from `loopTask`, no pump involvement needed since nothing was ever kicked off) from "request
   already cleared, connect presumably in flight" (post `ABORT`/`TEARDOWN` as today). Either closes the
   gap; the doc currently specifies neither, and the mechanism is incomplete without one of them.

2. **BLOCKING — `tick()`'s `FAILED` branch is specified with materially less precision than its
   `ABORTED`/`TORN_DOWN` sibling, and the imprecise reading drops the same TLS-resume call the third
   pass's own most severe finding was about — reachable by nothing more than an ordinary failed
   connect, the single most common outcome this whole design was written to handle better.** The
   `ABORTED`/`TORN_DOWN` branch is specified by literally quoting the code to add: `if (_spotifyYielded)
   { spotifyTask::tlsResume(); _spotifyYielded = false; }`. The `FAILED` branch, immediately
   above it in the same paragraph, is specified only as *"today's existing `ERROR_UNREACHABLE` +
   `_onPlaybackFailed()` logic, same substitution"* — naming two elements of the current code by name,
   neither of which is the TLS-resume call. Re-read the current `_play()` failure path this branch is
   meant to relocate (`webRadioApp.h:1710-1717`): `_state = WRPlayState::ERROR_UNREACHABLE;` /
   `LOG_W(...)` / **`spotifyTask::tlsResume(); _spotifyYielded = false;`** / `_onPlaybackFailed(...)` —
   the resume call sits *between* the two elements the doc names, and the doc's shorthand never
   explicitly says it's included. Under the async design this whole block necessarily moves off
   `_play()` (which no longer sees `connectOk` at all — the pump does, and the pump is a free function
   with no access to `_spotifyYielded`, the same reasoning the doc itself already applies to justify why
   `tick()`, not the pump, must own the `ABORTED`/`TORN_DOWN` resume) — so `tick()`'s `FAILED` branch is
   the *only* place this call can go, and "same substitution" is the entire specification for whether it
   goes there. Given this project's exact demonstrated failure mode on this precise question three times
   running (a TLS-resume call quietly not making it into a relocated/guarded code path), and given that
   ordinary connect failures are not an edge case here — they're the measured, headline problem this doc
   exists to fix (421 occurrences over 4 hours per the Context section) — a Developer who reads "same
   substitution" as "move the *named* elements, `ERROR_UNREACHABLE` and `_onPlaybackFailed()`" and
   leaves the resume call behind would ship a build where **every ordinary failed connect** permanently
   leaks the yield: `_play()`'s own `if (!_spotifyYielded) tlsYield()` guard (`:1613`) prevents it from
   incrementing `s_tlsYieldReqCount` a second time once already `true`, so nothing else in the design
   ever decrements it back to zero — Spotify's TLS starves for the rest of the boot after the *first*
   bad connect, not a rare interruption case. Verified `spotifyTaskStorage.cpp`'s `tlsResume()`
   (`:694-702`) is a plain ref-count decrement guarded by a spinlock, safe to call from any task context
   including `loopTask` inside `tick()` — no mechanical reason this can't work, only a specification gap.
   **Fix:** spell out the `FAILED` branch's transplanted block explicitly and completely, the same way
   `ABORTED`/`TORN_DOWN`'s fix is spelled out — don't rely on "same substitution" to carry a
   safety-critical line across a relocation by implication, precisely because this project has now
   demonstrated three separate times that the implication doesn't reliably survive.

3. **BLOCKING (exit-criteria gap, downstream of finding #1) — no exit criterion can catch finding #1
   as currently worded, because the one bullet closest to it deliberately avoids the exact timing that
   triggers it.** The "re-entrant control input during CONNECTING" bullet requires forcing `CONNECTING`
   "against a **real** slow/dead host" *before* firing the interrupting eject/stop/etc. tap — which
   guarantees the pump has had seconds, not milliseconds, to have already consumed `CONNECT` and be
   blocked inside `connecttohost()` by the time the interrupting request lands. That is precisely the
   case the mechanism already handles correctly (post-connect-return branch). It cannot exercise finding
   #1's failure mode, which requires the interrupting request to land *before* the pump's first
   top-of-loop read since `CONNECT` was posted. No other bullet fires two control actions back-to-back
   with no host-response delay between them either. **Add an explicit criterion:** fire `set wrPlay N`
   immediately followed (no delay, same script) by `set wrStop` / `set wrEject` / a different `set
   wrPlay M`, repeated several times in a tight loop against both a fast-responding and a slow/dead
   host, and confirm every time that `_state` reaches a terminal value within a bounded window (never
   parks at `CONNECTING`) and that `get wrPump`/`get arenaStats` never show an orphaned pump task cycle
   count that stops climbing or a JIT arena that was never released.

**Non-blocking:**

4. Re-derived the doc's own "accepted, narrow residual race" (pump reads `CONNECT`, then clears it to
   `NONE` — a same-instant `ABORT`/`TEARDOWN` write could in principle clobber the clear) against this
   file's own stated scheduling facts: `WR_PUMP_PRIORITY = 2` is explicitly documented as "above
   loopTask (prio 1)" (`:296`), and the pump is `xTaskCreatePinnedToCore`'d onto `APP_CPU_NUM`
   (`:393-395`) — the same core Arduino's `loopTask` runs on by default, which the file's own "above
   loopTask" comment already assumes. Under standard FreeRTOS priority-based preemption, a strictly
   lower-priority ready task cannot run while a higher-priority task is running and has not blocked or
   yielded — and there is no blocking call between "read `CONNECT`" and "write `NONE`" in the specified
   sequence. That means `loopTask` cannot actually interleave with the pump's read-then-clear pair at
   all under this file's own priority setup; the window the doc explicitly "accepts" (and reaches for a
   compare-and-swap justification to explain why it isn't engineered around) appears to be fully closed
   by the scheduler already, not merely narrow. This doesn't make the design less safe — if anything the
   opposite — but it means the doc's risk narrative is pointed at the wrong window: precise about a gap
   that's arguably zero-width, silent about the real one (finding #1, which *is* reachable, because it
   spans the pump's genuine `vTaskDelay` block where it has actually yielded the CPU). Worth correcting
   so a future reader doesn't spend effort hardening the described window while the actual gap goes
   unaddressed.

5. `wrPumpTaskBody()`'s existing structure (`:349-382`) unconditionally takes the mutex and calls
   `s_wr_audio->loop()` every single cycle; the design doesn't say whether the new `CONNECT` branch
   *replaces* that cycle's normal pump call or runs in addition to it. Low risk either way — `loop()`
   is a documented fast no-op when nothing is running (`:369`'s own comment) — but worth a sentence of
   explicit control flow (an `if`/`else if`, not two unconditional steps run back-to-back) so a
   Developer isn't left inferring it, matching this pass's brief question about whether the real loop
   structure is compatible with the mechanism as prose.

6. `dbgSet`'s `wrVol` handler (`webRadioApp.h:1346-1361`, unchanged since the first pass's own finding
   #1 named it) still takes `s_wrAudioMutex` with a raw, unbounded `xSemaphoreTake(...,
   portMAX_DELAY)` — a freeze source independent of every mechanism this design (and the three
   revisions since) has touched, and still inconsistent with the short-timeout, degrade-gracefully
   idiom `wrVolumeSink()` uses two hundred lines away for the same mutex. Never adopted as a mandatory
   requirement in any revision since the first pass flagged it as a "third, independent freeze source."
   Out of this design's stated narrow scope (it only claims to move `connecttohost()`), but it remains
   live in the source and reachable via the same `set` surface this doc's own exit criteria rely on —
   flagging again since three revisions have now passed without picking it up either way (fix it, or
   explicitly declare it out of scope with a reason).

**Testability sign-off (fourth pass):** consensus **not** reached — go/no-go is **no-go**, three
blocking findings. The design's core shape is unchanged from the third pass's assessment and still
correct — nothing here reopens Option B vs Option C. Two of this revision's four claimed fixes hold up
under independent re-verification exactly as specified: the `TEARDOWN`-priority guard
(`s_wrPumpRequest != TEARDOWN ? ABORT`) was traced against every caller from scratch and correctly
prevents every downgrade path the third pass found, with no caller that legitimately needs to reverse
it; the STOP-button/`wrStop` redundant-`_state`-write fix was checked with a file-wide grep for every
`_state = WRPlayState::STOPPED`/`_state = STOPPED` write (`:970`, `:1226`, `:1524` — exactly three,
matching the doc's claim of exactly two redundant sites plus `_stopAudio()`'s own intentional one), and
a fourth candidate site (`:846`, inside the stream-death detector) was independently confirmed to run
only under `_state == PLAYING` (gated at `:743`), never `CONNECTING`, so it is correctly *not* a third
redundant site needing the same fix. But the other two claimed fixes each have a real gap, and both are
severe enough on their own to block: finding #1 is a structural hole in the clear-on-commit mechanism
this exact revision introduced — a real, ordinarily-reachable window (not the doc's own explicitly
accepted micro-race) that reintroduces the second pass's permanent wedge plus a resource leak; finding
#2 is the same TLS-yield-starvation bug class as the third pass's headline finding, recurring through
the one reconciliation branch (`FAILED`) that fix's precision didn't reach, reachable by an ordinary
failed connect rather than a stop/eject interruption. Four consecutive passes each finding a genuine,
previously-unflagged defect — three of them in variations on the exact same TLS-yield/state-wedge
failure modes — is itself now a strong signal about where this mechanism's actual hazard surface lives:
not in the high-level shape (request/result slots, deferred teardown, priority ordering), which every
pass has endorsed, but in the precise mechanics of *when* the request slot is read versus written, and
in whether "same as today, just relocated" specifications carry every line of the original block along
with them. Concretely falsifiable next step: give the pump's top-of-loop check (or `_stopAudio()`'s
guard) a way to resolve `ABORT`/`TEARDOWN` when no connect was ever dispatched (finding #1), spell out
`tick()`'s `FAILED` branch as explicitly as its `ABORTED`/`TORN_DOWN` sibling, including the TLS-resume
line by name (finding #2), and extend the exit criteria with a back-to-back-command test that doesn't
give the host a chance to respond before the second command lands (finding #3) — then this is ready for
a fifth pass.

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

- ~~VE testability review of the CONNECTING-state changes~~ — **five passes done, 2026-08-04/05.**
  First: 4 blocking findings against the original two-requirement sketch. Second: found that fix
  incomplete (`_stopAudio()` was the real blocking primitive in most named call sites; the
  flag-only teardown left a permanent wedge) — 4 new blocking findings, addressed via the
  request/result-slot mechanism. Third: confirmed the use-after-free and permanent wedge were
  genuinely fixed, but found 4 more gaps (dropped TLS-resume; two redundant `_state` writes; an
  unspecified request-clear causing an infinite reconnect loop; a `TEARDOWN`-downgrade leak).
  Fourth: confirmed 2 of those 4 fixes held up exactly as specified, found the other 2 each had a
  residual gap (a different early-arrival hole reintroducing the same permanent wedge; the
  TLS-resume fix's shorthand leaving the `FAILED` branch un-guaranteed) — both addressed. Fifth: the
  narrowest result yet, 1 blocking finding (both `TEARDOWN` branches deleted `s_wr_audio` without
  nulling it, a deterministic dangling-pointer bug), 1 non-blocking — addressed in this revision.
  **Not yet had a sixth VE pass** — treat as addressed-but-unverified, not closed, until that
  happens.
- **New — `s_wr_audio` doesn't dangle after a `TEARDOWN` (VE fifth-pass finding #1):** force a
  `TEARDOWN` (eject during `CONNECTING`, real host, either early-arrival or post-connect-return
  timing), let it resolve, then confirm on the *next* WebRadio entry that a fresh `Audio` object is
  created cleanly (`get wrPump`/`get arenaStats` show a new session starting from a clean state, not
  a crash/reboot on the first `_play()`, autoplay, or bare re-eject after the teardown completed).
  Repeat for both `TEARDOWN` branches (early-arrival and post-connect-return) since they're
  separate code paths that both needed the same fix.
- **New — early-arrival ABORT/TEARDOWN, no connect ever dispatched (VE fourth-pass finding #1):**
  fire `set wrPlay N` immediately followed, in the same script with no delay, by `set wrStop` /
  `set wrEject` / a different `set wrPlay M` — repeated several times in a tight loop against both a
  fast-responding and a slow/dead host. Confirm every time: `_state` reaches a terminal value within
  a bounded window (never parks at `CONNECTING`); `get wrPump`'s cycle counter keeps climbing (no
  orphaned pump task); `get arenaStats` never shows the arena stuck allocated past a session that
  should have released it. This specifically exercises the window the "re-entrant control input"
  criterion below cannot reach (that one deliberately uses a slow host, giving the pump time to
  have already consumed `CONNECT` before the interrupting tap lands).
- **Spotify TLS-yield accounting survives BOTH a stop/eject during CONNECTING (VE third-pass
  finding #1) AND an ordinary failed connect with no interruption at all (VE fourth-pass finding
  #2 — the `FAILED` branch specifically, since that's the single most common outcome and the one
  the third revision's "same substitution" shorthand left unguaranteed):** force `CONNECTING`
  against a real slow/dead host with Spotify's `bgPoll` active (the `--spotify-present` soak build,
  not the isolated noSpotify build, so a real yield/resume imbalance is actually observable), press
  STOP/eject during the connect, then confirm — once the abort/teardown resolves — that Spotify's
  polling actually resumes (`get heap`/heartbeat's `poll=` counters advancing again, not stuck at
  `0/0`; cross-reference `spotifyTaskStorage.cpp`'s yield-count surface if one exists, or a fresh
  `get`/log line added for this check) rather than staying silently yielded for the rest of the
  boot. **Separately, and just as important:** repeat the same check with zero interruption — let a
  real connect attempt fail on its own (a genuinely dead host, no STOP/eject tap at all) and confirm
  Spotify's polling resumes afterward too, since the `FAILED` branch is a structurally different
  code path from `ABORTED`/`TORN_DOWN` and both need independent confirmation. These are the two
  findings across all four passes reachable by nothing more than ordinary use, not a timing race —
  each deserves its own dedicated, repeated check (multiple cycles in one soak), not a single
  pass/fail sample.
- **New — no runaway reconnect loop (VE third-pass finding #3):** force a real, eventually-
  succeeding `CONNECTING` (not a permanently-dead host), and confirm via the raw serial log that
  `connecttohost()`/`"Connect to new host"` fires exactly once per successful connect, not
  repeatedly at the pump's ~2ms cadence — the failure mode as originally drafted (before this
  revision's clear-on-commit fix) would have been silent at a casual glance (the station *does*
  play) while hammering `s_wrAudioMutex` continuously underneath, so this needs an explicit log-line
  count, not just "does audio come out."
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

### Fifth pass (2026-08-05)

Independent re-verification against the actual current source (`app/src/webRadioApp.h`, confirmed
still 1961 lines — no implementation has landed since the fourth pass; `app/src/spotifyTaskStorage.cpp`,
confirmed still 887 lines, re-checked for the `s_tlsYieldReqCount`/`tlsResume()` ref-counting claims
specifically — both check out exactly as the fourth pass described, `tlsResume()` at `:694-702` is a
plain critical-section-guarded decrement, last-caller-to-zero clears `s_tlsStopped`). Line numbers
re-derived from scratch, not trusted from any prior pass or the doc's own citations, per every prior
pass's own standing warning. This pass does not re-litigate whether the request/result-slot idea is
sound — four passes have now converged on "yes," and nothing found here disturbs that. It re-traces
the specific mechanics this revision changed (the `ABORT`/`TEARDOWN` top-of-loop branches, the fully
spelled-out `tick()` triad, the corrected residual-race framing, the re-added `wrVol` fix) against the
real `wrPumpTaskBody()`/`_stopAudio()`/`_play()`/`wrAudio()`/`suspend()` code, and specifically hunts,
per the brief, for defects reachable only through this revision's newly-written text. Conclusion up
front: **the `ABORT`/`TEARDOWN` top-of-loop chain genuinely covers all four values of
`s_wrPumpRequest`, the fully-spelled-out `tick()` branches correctly reproduce `_play()`'s real
failure-path ordering, the residual-race correction is accurate and (newly re-checked here) extends
cleanly to all three request-bearing branches, and the re-added `wrVol` fix textually matches
`wrVolumeSink()`'s real, current idiom exactly. But the two `TEARDOWN` branches — the post-connect one
carried over from earlier revisions and the early-arrival one freshly written this revision to mirror
it — both specify `delete s_wr_audio` without ever resetting the pointer to `nullptr` afterward. That
omission is a real, deterministic (not timing-dependent) dangling-pointer bug: every other call site in
this file that touches `s_wr_audio` — `_play()`'s own `if (!s_wr_audio) { new Audio(...) }` guard,
`wrAudio()`'s identical inline guard, `_stopAudio()`'s `if (s_wr_audio)` guard, `wrVolumeSink()`/`wrVol`'s
`if (!s_wr_audio) return;` checks, the pump's own steady-state `if (s_wr_audio) s_wr_audio->loop()` —
treats a non-null `s_wr_audio` as proof a live object exists, and none of them re-verify that. Once a
`TEARDOWN` completes without the reset, every one of those checks is wrong for the rest of the session,
guaranteed, not probabilistically.** One finding, blocking, plus a smaller related non-blocking
specification gap in the same branches.

1. **BLOCKING — both `TEARDOWN` branches (`s_wrPumpRequest == TEARDOWN`, early-arrival and
   post-connect-return alike) specify `delete s_wr_audio` but never `s_wr_audio = nullptr` afterward,
   leaving a permanently dangling pointer that every other `s_wr_audio` null-check in the file will
   read as "still valid" — a deterministic use-after-free on the very next touch, not a race.** Checked
   both bullets word for word: the post-connect-return case (Consumer-side, `== CONNECT` →
   `TEARDOWN`-after-resolve) reads "delete `s_wr_audio`, release the arena (`mb_arena_release()`); set
   `s_wrPumpResult = TORN_DOWN`; **null `s_wrPumpTask` last**, immediately before `vTaskDelete(NULL)`" —
   nulling is explicitly called out for `s_wrPumpTask`, in the same sentence, and just as explicitly
   never mentioned for `s_wr_audio`. The early-arrival case (`== TEARDOWN` at top-of-loop, this
   revision's new text) reads "clear `s_wrPumpRequest = NONE`, delete `s_wr_audio`, release the arena,
   set `s_wrPumpResult = TORN_DOWN`, null `s_wrPumpTask` last, self-delete — **the identical terminal
   sequence as the post-connect `TEARDOWN` case above**" — so the gap is inherited by explicit design
   intent to mirror, not independently reintroduced. Compared this against the one case in the actual
   source that already implements a synchronous version of this exact teardown — today's
   `suspend()` (`webRadioApp.h:559`): `if (s_wr_audio) { delete s_wr_audio; s_wr_audio = nullptr; }` —
   delete and null happen together, as a single unit, in the one line of existing code this design's
   `TEARDOWN` branches are meant to relocate. The design's own text drops half of that pair while
   moving it, the same failure mode (a load-bearing line silently not surviving a relocation) the third
   and fourth passes already caught twice for the TLS-resume call — recurring here in the pointer
   lifecycle instead of the TLS ref-count. Traced every downstream consumer of `s_wr_audio` to confirm
   the consequence is real, not hypothetical:
   - `_play()`'s own guard (`webRadioApp.h:1639-1661`): `if (!s_wr_audio) { ... size_t lfbDma = ...; if
     (lfbDma < 16*1024) { ...abort...; } s_wr_audio = new Audio(...); wrApplyInBufTrial(...);
     wrApplyConnectTimeout(...); }` — with `s_wr_audio` left non-null (dangling) by a prior `TEARDOWN`,
     this entire block is skipped: no fresh `Audio` object, no DMA-floor guard, no
     `wrApplyConnectTimeout()`. Execution falls straight through to `wrEnsurePumpTask()` (:1665, creates
     a *new* pump task, correctly, since `s_wrPumpTask` — unlike `s_wr_audio` — genuinely was nulled)
     and then `wrAudio().setVolume(...)` at :1668-1669.
   - `wrAudio()` (`:261-268`) has its own, textually identical inline guard (`if (!s_wr_audio) { new
     Audio(...); ... }` then `return *s_wr_audio;`) — belt-and-braces against exactly this kind of
     caller bug in the *original* single-task code, but equally fooled by a dangling non-null pointer:
     it returns `*s_wr_audio`, a reference to already-freed heap memory, and `_play()`'s very next line
     immediately calls `.setVolume(...)` on it. This is the first guaranteed crash/heap-corruption
     point — reached on quite literally the next `_play()` call (autoplay or a manual station tap)
     after any `TEARDOWN` that actually completes, no adversarial timing needed.
   - Even without ever tapping a station again: a bare re-suspend is enough. `_stopAudio()`
     (`:1516-1523`)'s normal (non-`CONNECTING`) path — reached once `_state` has been reconciled to
     `STOPPED` by `tick()`, e.g. the user re-enters WebRadio and immediately ejects again without
     touching anything — does `if (s_wr_audio) { xSemaphoreTake(...); s_wr_audio->stopSong(); ... }`,
     calling a virtual/member function through the same dangling pointer. Reachable via nothing but
     eject-during-slow-connect → wait for resolution → re-enter WebRadio → eject again, no station tap
     at all.
   - If a *fresh* pump task does get created (via `wrEnsurePumpTask()` above, since `s_wrPumpTask` was
     correctly nulled) before either of the above fires, its own steady-state branch (`:369`, `if
     (s_wr_audio) s_wr_audio->loop();`) hits the identical dangling pointer on its very first cycle,
     2 ms after creation — a second, independent crash site for the same root cause, on the pump task
     this time instead of `loopTask`.

   **This is not merely a hypothetical the exit criteria might happen to graze — the existing "leave-
   and-quickly-re-enter during `CONNECTING`" exit criterion (VE second-pass finding #5, still on the
   list above) explicitly directs a tester to confirm "a manual station tap afterward works normally
   either way" once the deferred teardown resolves. A Developer who actually runs that check on real
   hardware would hit this crash and be forced to debug it live — but that is exactly the outcome
   this project's own standing pre-implementation VE practice exists to avoid: finding it here, from
   the design text, is cheaper than finding it from a device that just aborted mid-soak.** **Fix:**
   both `TEARDOWN` branches need an explicit `s_wr_audio = nullptr;` immediately after `delete
   s_wr_audio;`, matching today's `suspend()` idiom at `:559` exactly — stated as its own step, not left
   for a Developer to infer from "delete `s_wr_audio`" the way `_play()`'s own `_debugForceConnFail`
   early return and the DMA-guard early return both already correctly pair `delete`-adjacent state
   resets with the deletion itself elsewhere in this same file.

   **A smaller, related gap surfaced while tracing this — non-blocking, but worth closing at the same
   time since it's the same code path:** neither `TEARDOWN` branch's "call `stopSong()` to clean up"
   step (post-connect-return case only — the early-arrival case correctly skips it, "nothing was ever
   dispatched this cycle") restates that this call needs `s_wrAudioMutex`, the way the doc is explicit
   about the mutex bracketing `connecttohost()` a few lines earlier in the same bullet. Every other
   `s_wr_audio` method call in the file — `_stopAudio()`'s `stopSong()`, `wrVolumeSink()`'s
   `setVolume()`, the pump's own steady-state `loop()` — is mutex-wrapped; an unwrapped `stopSong()`
   here would be calling into the `Audio` object without exclusion against a concurrent
   `wrVolumeSink()`/`wrVol` call from `loopTask` (both of which *do* still take the mutex, per the
   `wrVol` fix re-added this revision) — a real but narrower race than finding #1 above, closed by
   simply wrapping this specific `stopSong()` call the same way every other one in the file already is.
   Once finding #1's `s_wr_audio = nullptr` fix lands, this residual gap is the only place left where
   `s_wr_audio`'s mutex discipline isn't fully self-consistent within the new mechanism.

**Confirmed sound, re-checked from the real source rather than re-trusted from the doc's own
citations or any prior pass's line numbers:**
- The `if`/`else if` chain the consumer-side spec implies (`== CONNECT`, `== ABORT`, `== TEARDOWN`, else
  `NONE`) does cover all four values `s_wrPumpRequest` can hold, traced against `wrPumpTaskBody()`'s
  real structure (`webRadioApp.h:349-382`): top-of-loop stop-request check, then (per the design) the
  new branch, then `vTaskDelay(WR_PUMP_CADENCE_TICKS)` — `WR_PUMP_CADENCE_TICKS = pdMS_TO_TICKS(2)`
  (`:297`) is a genuine blocking/yielding call, confirming the fourth pass's characterization of where
  the real early-arrival window lives (the pump's own sleep, not a sub-instruction race). The
  early-arrival `TEARDOWN` branch's own question — does it need the mutex at all, given nothing was
  ever connecting — checks out as "no" for the reason the fourth pass's residual-race note already
  established for a different step: whichever task ever posts `TEARDOWN` (via `suspend()`) has, by
  construction, already caused WebRadio to stop being `currentApp`, so nothing on `loopTask` reaches
  `s_wr_audio` again until `resume()` — the pump is the sole remaining actor.
- `tick()`'s `FAILED` branch, re-derived against the real failure path it replaces
  (`webRadioApp.h:1710-1717`: `_state = WRPlayState::ERROR_UNREACHABLE;` / `LOG_W(...)` /
  `spotifyTask::tlsResume(); _spotifyYielded = false;` / `_onPlaybackFailed(true);`), correctly
  preserves the resume call and its position in the sequence. One cosmetic note: the design wraps it in
  `if (_spotifyYielded) { ... }`, whereas the real source at `:1713-1715` calls `tlsResume()`
  unconditionally at that point — but `_play()`'s own `if (!_spotifyYielded) { tlsYield(); ... }` guard
  at `:1613` guarantees `_spotifyYielded == true` for the entire `CONNECTING` window by construction
  (the same invariant the third pass's finding #1 already established), so the added `if` is a
  no-op-but-harmless defensive wrap, not a behavior change or a new gap — mentioning only so the next
  reviewer doesn't have to re-derive whether the discrepancy matters (it doesn't).
- The corrected "residual race" framing (`WR_PUMP_PRIORITY = 2`, `webRadioApp.h:296`, explicitly "above
  loopTask (prio 1)", both `xTaskCreatePinnedToCore`'d onto `APP_CPU_NUM`, `:393-395`) is accurate, and
  — re-checked per the brief's specific question — extends cleanly to all three request-bearing
  branches (`CONNECT`'s clear-on-commit, and this revision's new `ABORT`/`TEARDOWN` early-arrival
  clears), not just the `CONNECT` case the fourth pass verified: none of the three has a blocking or
  yielding call between the implicit "read via branch selection" and the "clear to `NONE`" write, so
  the same zero-width argument applies uniformly. Interrupts, not just tasks, can technically preempt
  the pump mid-branch on Xtensa — but no ISR in this codebase writes `s_wrPumpRequest` (every producer
  is a normal task-context function: `_play()`, `_stopAudio()`, `suspend()`), so an ISR landing in the
  window has nothing to race even if it occurs.
- The re-added `wrVol` fix (`webRadioApp.h:1346-1361` today, raw `xSemaphoreTake(s_wrAudioMutex,
  portMAX_DELAY)`) is specified completely and correctly against `wrVolumeSink()`'s real, current idiom
  (`:328-338`, `WR_PUMP_READ_TIMEOUT_TICKS` take with a silent-skip-on-timeout give-up) — textually
  accurate, nothing dropped this time. Whether that idiom itself remains fully safe now that
  `s_wr_audio` can be genuinely mutated from a second task (the pump, via the `TEARDOWN` branches) is
  exactly finding #1's non-blocking sub-point above, not a flaw in the re-added fix's own correctness
  against its stated target.

**Testability sign-off (fifth pass):** consensus **not** reached — go/no-go is **no-go**, one blocking
finding. This is a narrower result than any of the four prior passes (1 blocking vs. 3-4 each) and,
unlike most of those, does not touch the request/result protocol's own state machine, the TLS-yield
accounting, or the `_state` re-entrancy guards at all — every mechanism component those four passes
individually hardened (the `_play()`/`_stopAudio()` guard, the `TEARDOWN`-priority ordering, the
clear-on-commit protocol, the `ABORT`/`TEARDOWN` early-arrival branches themselves, the TLS-resume
triad) is independently re-confirmed sound here, on its own terms, against the real source. The one
gap that remains is adjacent to all of that machinery rather than inside it: the two `TEARDOWN`
branches correctly *decide* to release `s_wr_audio`'s memory but never finish the release by resetting
the pointer that every other line in the file treats as the sole liveness signal for that memory —
structurally the same class of defect (a well-established idiom's second half silently not surviving
relocation into the new asynchronous machinery) that has now shown up three times across five
revisions of this document in three different guises: the TLS-resume call (third and fourth passes),
the `wrVol` fix itself briefly falling out of scope (noted in the revision history), and now the
pointer-reset half of `delete s_wr_audio`. That recurrence is itself worth naming as a process
observation for whoever implements this: every "delete X" / "relocate Y" instruction in this design
should be re-read against the *exact* multi-statement idiom it's replacing in the current source
(`webRadioApp.h:559` in this case) before being marked complete, not summarized to the single verb that
carries the primary intent. **Concretely falsifiable next step:** add `s_wr_audio = nullptr;`
immediately after both `delete s_wr_audio` instances (Consumer-side `TEARDOWN`-after-`CONNECT` branch
and the early-arrival `TEARDOWN` branch), and wrap the post-connect `TEARDOWN` branch's `stopSong()`
call in the same mutex take/give every other `s_wr_audio` method call in the file already uses — both
are one-line, mechanical fixes with a clear real-source precedent to copy from, not a redesign. Given
the narrowing trend (4 → 4 → 3 → 1 blocking finding across the last four passes) and that this finding
is a single, precisely-scoped, easily-fixed omission rather than a structural gap in the mechanism
itself, a sixth pass focused specifically on confirming this one fix (plus a final holistic pass over
the whole document once it lands) seems like a reasonable, near-final step rather than a sign this
process needs to keep expanding in scope.
