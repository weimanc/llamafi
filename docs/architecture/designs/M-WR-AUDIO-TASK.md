# Design — WebRadio audio decode off loopTask (dedicated pump task)

> Owner: Architect
> Status: accepted — human-approved 2026-07-03 (panel: VE/DEV/QM approve-with-changes ×3, dispositions applied)
> Date: 2026-07-02 (dispositions applied 2026-07-03)
> Feeds: (ADR TBD — promote the lean once Phase-1 DUT numbers land)
> Tracked-as: TASK-278
> Deps: M-WEBRADIO (done), M-WEBRADIO-NOPSRAM (A-lite arena — the heap ceiling in Goal 4) [QM-2-6]

## Context / pain points

`WebRadioApp::tick()` calls `s_wr_audio->loop()` (webRadioApp.h:310) on the Arduino
**loopTask** — the same task that samples touch (`appHandleInput`), runs the serial/logsink/
heartbeat plumbing, and paints. `Audio::loop()` (ESP32-audioI2S v2.3.0, vendored fork under
`app/lib/ESP32-audioI2S`, frozen per BP-042) is the whole playback engine: it parses the HTTP
response header, pulls the socket into `InBuff`, runs the Helix MP3 decode, and feeds I2S.
The contention is **two-way**:

1. **Decode starves UI** — while PLAYING, every loop iteration carries decode work; touch
   sampling and paint cadence degrade shell-wide (operator report 2026-07-02: taskbar and
   PLEDIT feel sluggish during playback).
2. **UI starves decode** — a slow paint (`_drawFull` → `repaintChrome`) or any long loop
   path blocks `loop()` servicing; the input buffer drains and I2S underruns. This is
   *worse* since PATCH-MEMBUDGET-4 halved the I2S DMA ring (production since TASK-262):
   less DMA slack means the pump must be serviced more often, not less. The TASK-263
   metrics (`_underrunCount` / `_minBufPct`, `get wrUnderruns`) exist precisely because of
   this sensitivity.

A third, adjacent latency source: `connecttohost()` blocks loopTask for up to several
seconds (DNS + TCP + header) on every play/skip — the UI freezes during CONNECTING. Not
this design's primary target, but the option space should not foreclose fixing it.

**Facts that bound the design** (verified in tree, 2026-07-02):

- **Core topology:** loopTask (prio 1), `spotifyTask` (prio 1, `APP_CPU_NUM` = core 1,
  spotifyTaskStorage.cpp:38-40) and `dataTask` (prio 1, core 1, dataTaskStorage.cpp:100-105)
  all live on **core 1**. Core 0 runs WiFi/lwIP + the TWDT-subscribed CPU0 idle task
  (main.cpp `setup()`: TWDT 15 s, loopTask + CPU0 idle subscribed).
- **During playback core 1 has headroom:** Spotify TLS is yielded (`tlsYield`) for the whole
  playback window; dataTask is idle after the station fetch *(inference — suspended apps
  enqueue no fetches; E0/E1 confirm)* [QM-2-3] — the only busy core-1 task while PLAYING is
  loopTask itself.
- **Playback is strictly foreground.** `switchApp()` calls `suspend()` on the outgoing app
  (main.cpp:1828); `WebRadioApp::suspend()` stops audio, and (MEMBUDGET_PHASE1 — now the
  production env, platformio.ini cyd2usb_winamp) **deletes the Audio object and releases
  the JIT arena** (TASK-267/ADR-047 Amd 1). Eject does the same via `_stopAudio()` +
  `switchApp(Spotify)`. No background-playback requirement exists — the pump task's
  lifecycle can bind to the app being active.
- **v2.3.0 has no built-in audio task** (citation: `grep -r xTaskCreate
  app/lib/ESP32-audioI2S/src/` → no hits [QM-2-4]; upstream added one in 3.x; we are frozen
  on the 2.3.0 fork carrying PATCH-MEMBUDGET-1..4). Any task model is ours to build — but
  the project already has two proven command-queue task patterns to copy (`spotifyTask`,
  `dataTask`).
- **No internal locking** in Audio v2.3.0. `loop()`, `connecttohost()`, `stopSong()`,
  `setVolume()`, `inBufferFilled/Free()`, `isRunning()` all touch shared state
  (`m_f_running`, `InBuff`, client) unguarded.
- **Cross-task plumbing already exists** for two of the read paths: ICY titles arrive via
  `s_icyTitleQueue` (`xQueueOverwrite` from the `audio_showstreamtitle` callback — i.e. from
  whatever task runs `loop()`), and the decoder's arena allocations are task-agnostic
  (`mb_arena_alloc` from the patched sites).
- **The WR state machine is load-bearing and freshly validated** (ADR-045 gate 10/10,
  TASK-275; TASK-273 pacing; TASK-276 terminal retry, DUT-validated 2026-07-02). Semantics
  changes to `_play`/`_onPlaybackFailed`/stream-death (TASK-218) carry real regression risk.

## Goals

1. Touch/UI latency while PLAYING comparable to not playing: `hb` `loopMax` during playback
   within ~1.5× of the STOPPED baseline (exact number set after the Phase-0 baseline run).
2. No underrun regression: `wrUnderruns` / `minBufPct` over `./run/wr-soak 30` no worse than
   baseline — ideally *better*, since paints stop blocking the pump.
3. State-machine semantics preserved: TASK-218 stream-death debounce, ADR-045 auto-skip
   bound, TASK-273 pacing, TASK-276 terminal retry, TLS yield/resume pairing, and all
   `wr*` dbg surfaces behave identically.
4. Heap/stack budget fits the no-PSRAM A-lite world: pump-task stack is transient (exists
   only while WebRadio is active) and small (~8 KB target, HWM-measured); no new resident
   footprint in other apps.
5. No TWDT interaction: pump task never starves the TWDT-subscribed CPU0 idle task and
   never needs its own subscription.

## Design space (options + tradeoffs)

### (a) Dedicated pump task, core 1, priority 2 — recommended

`xTaskCreatePinnedToCore(pumpBody, "wrAudio", 8K, …, /*prio*/2, …, APP_CPU_NUM)`. The task
loops: take mutex → `audio->loop()` → release → `vTaskDelay(pdMS_TO_TICKS(2))` (cadence
tuned on DUT against the halved DMA ring). Priority 2 preempts loopTask (prio 1): a slow
paint can no longer starve the pump. The pump's *typical* per-call work (one header parse /
one socket read / one decode chunk) is short, so UI preemption is normally bounded and
frequent rather than long and rare. **Exception [DEV-2-1]: `Audio::loop()` re-enters the
blocking `connecttohost()` path internally on three real paths** — playlist-format
resolution (`connecttohost(parsePlaylist_M3U/PLS/ASX())`, `Audio.cpp:2450-2452`; .pls/.m3u
station URLs exist in radio-browser data), HTTP 3xx redirect during header parse
(`Audio.cpp:3587` — headers parse in `loop()`, *after* `_play()`'s connect returned), and
lost-stream reconnect (`Audio.cpp:5255`). On those paths the pump holds the mutex through a
multi-second DNS+TCP window; the locking model below absorbs this (timeout-take reads), and
the stop/suspend worst-case bound is measured, not assumed.

- **Underrun risk:** lowest of the options. Decode is decoupled from paint stalls *and*
  keeps its distance from WiFi/lwIP bursts (which live on core 0). Stream bytes arrive via
  the core-0 tcpip task regardless of where `loop()` runs, so moving the pump does not slow
  ingress. During playback core 1 is otherwise quiet (TLS yielded, dataTask idle — see
  Context), so the two-tasks-one-core oversubscription concern is theoretical for this
  specific window.
- **Locking:** single (non-recursive) mutex serialises `loop()` against UI-side control
  calls (see §Locking model below).
- **TWDT:** core-1 idle is not TWDT-subscribed; the pump's `vTaskDelay` yields every cycle
  anyway. loopTask keeps its existing resets. No new subscription.
- **Consistency:** matches the house pattern — every project task is core-1-pinned prio 1;
  this is the first prio-2 task, justified by the DMA deadline (it is the only task with a
  hard real-time consumer).

### (b) Dedicated pump task, core 0

Same task, `PRO_CPU_NUM`. Superficially attractive ("keep core 1 clean for UI"), but:

- **Underrun risk is higher, not lower:** the pump then competes with WiFi/lwIP/TLS work on
  core 0 — WiFi bursts starving decode is the community-reported contention pattern for
  this library (uncited folklore; the structural argument stands on its own [QM-2-4]). Our
  WiFi is busy *while streaming* by definition.
- **TWDT exposure:** CPU0 idle is TWDT-subscribed (15 s). A prio-2 pump that misbehaves
  (e.g. a blocking read path) starves CPU0 idle → watchdog. Option (a) cannot trip this.
- **dataTask precedent cuts against it:** the 15 s TWDT extension exists because core-0
  starvation already bit us once (setup() comment).

Kept as the *measured fallback*: if the (a) soak shows UI-induced underruns persist (i.e.
prio 2 on core 1 is not enough), try core 0 before anything heavier.

### (c) Status quo + budgeted servicing (do-less option)

Keep `loop()` on loopTask but service it N× per tick and/or cap paint work between pumps
(e.g. pump before and after `_drawFull`).

- **Cost:** trivial. No locking, no lifecycle, no task.
- **Why it loses:** it addresses neither direction of the contention. Decode work still
  rides the loop (UI stays sluggish — the operator's actual complaint), and a single 100 ms
  `repaintChrome` still drains the halved DMA ring regardless of how many pump calls
  surround it. It also couples pump cadence to loop cadence, which the serial/logsink/
  heartbeat plumbing already jitters.
- Retained only as the fallback if (a) hits an unforeseen library-reentrancy wall on DUT.

### Locking model (applies to a/b)

**Phase 1 — mutex, synchronous control (recommended now):** one `SemaphoreHandle_t` guards
every `Audio` method. Pump: take → `loop()` → give (hold is short on the typical path, but
can span seconds on the DEV-2-1 in-`loop()` connect paths). UI/tick side, two disciplines
[DEV-2-1]:

- **Control calls** (`connecttohost`, `stopSong`, `setVolume` from `_play`/`_stopAudio`):
  blocking take, as drafted. `connecttohost` from `_play()` holds the mutex for seconds —
  the pump simply blocks meanwhile, which is correct: there is nothing to pump until
  connect returns.
- **Per-tick reads** (`inBufferFilled/Free`, `isRunning`): `xSemaphoreTake` with a short
  timeout (≤50 ms; start at 0 and tune on DUT). On timeout, degrade gracefully — skip the
  POSBAR update and reuse the last snapshot; never block loopTask behind a pump that is
  inside an in-`loop()` reconnect/redirect. Same rule for the TASK-263 underrun sampling.

The stop/eject/suspend worst-case is bounded by worst-case `Audio::loop()`, not by one
decode chunk — that bound is **measured** in E3 (forced redirect + stream-kill cases), and
a fork patch suppressing the in-`loop()` reconnect is the named Phase-2-adjacent fallback
if the measured bound is unacceptable (BP-042 keeps it out of Phase 1). The WR state
machine, TLS yield/resume pairing, retry/skip pacing, and every dbg surface keep their
exact current shape and call sites. **This is the minimal-regression cut.**

**Phase 2 (separate, optional, gated on Phase-1 numbers) — ownership + command queue:** the
pump task *owns* the Audio object; UI sends `PLAY(idx)/STOP/VOL` via queue (the
spotifyTask/dataTask pattern); connect results come back as events; tick() reads a
`volatile` snapshot (bufPct, lastRunningMs, connect outcome) instead of calling Audio. This
kills the `connecttohost` UI freeze too — but it makes `_play()` asynchronous, which
restructures `_onPlaybackFailed`/CONNECTING semantics — real surgery on the freshly
validated ADR-045/TASK-276 machine. Do not bundle it with Phase 1. Measure the freeze first
(`perf::record("wr.connect", …)` around the call).

### Cross-cutting details (per the lean, Phase 1)

- **Task lifecycle:** create the pump task lazily at first `_play()` — **order: arena
  acquire first, then task create** (an 8 KB contiguous stack allocated before
  `mb_arena_acquire()` bites into the same lfbInt window E4 checks) [DEV-2-3]; it blocks on
  the mutex/delay cycle and self-idles (skips `loop()`) when `!s_wr_audio || !isRunning()`.
  **Teardown is an enforced sequence, not an invariant sentence** [QM-2-1 + DEV-2-6]:
  `suspend()` sets the stop flag → the pump, at the top of its cycle **holding no locks**,
  gives the ack semaphore and then **immediately self-deletes** (`vTaskDelete(NULL)` is its
  next and last statement — it never re-enters the mutex or `Audio::loop()` after acking;
  ack-then-park-forever is the acceptable alternative, ack-then-keep-cycling is not) →
  `suspend()`, having taken the ack, proceeds: `stopSong()` → `delete s_wr_audio` →
  `mb_arena_release()`. The owner task never `vTaskDelete`s a possibly-inside-Audio pump.
  The ack take in `suspend()` uses a timeout bounded by the E3-measured worst-case
  `Audio::loop()` (DEV-2-1) + margin, with a LOG_E on timeout as the tripwire. Eject and
  taskbar-switch both route through `suspend()`, so one teardown path covers all exits.
  Per-station churn (auto-skip) does NOT churn the task — it persists across `_play()`
  calls within a session.
- **`set wrVol` lazy-construction hole [DEV-2-4]:** `wrAudio()` news up the Audio object on
  first use and the `wrVol` setter calls it — under this design that would create an Audio
  with no task, no mutex discipline, no arena. `wrVol` becomes clamp-store-only when
  `!s_wr_audio`; all Audio construction goes through `_play()`.
- **Stack/heap:** 8 KB stack, transient (freed on suspend with the task). No TLS on this
  path (streams are HTTP-only per ADR-029 amendment; HTTPS connect attempts fail allocation
  long before deep stack use). Measure `uxTaskGetStackHighWaterMark` on the soak; trim to
  HWM + 2 KB (the TASK-240 rule). Budget check: 8 KB transient sits inside the window the
  Spotify teardown overlay (TASK-264/M-RECLAIM) freed for playback — verify with
  `get heap` at CP1 that `lfbInt ≥ 24 K` still holds for the arena acquire.
- **POSBAR/ICY/metrics reads:** ICY queue unchanged (its producer just moves task — the
  queue was built for a cross-task producer; note the `webRadioApp.h:80` comment "Core
  0/audio task" is stale-then-true: false today, true-ish after this design — **correct the
  comment to the actual producer task in the implementation** [QM-2-5]). POSBAR reads
  (`inBufferFilled/Free`) and `isRunning()` use the tick-side timeout-take (§Locking model)
  — sub-microsecond reads when the mutex is free; skipped, not blocked-on, when it is not.
  TASK-263 underrun edge-counting stays in tick() Phase 1 (same fidelity it has today);
  moving it into the pump (fresher view) is a Phase-2 nicety.
- **Callbacks:** `audio_showstreamtitle` (→ `xQueueOverwrite`, ISR-safe pattern, fine) and
  `audio_info` (→ `LOG_I`) now fire from the pump task. **OQ2 resolved from the tree
  [DEV-2-5]:** the logSink ring append is guarded by `portENTER_CRITICAL_SAFE(&g_mux)`
  (`logSink.h:33-67`) — a spinlock, correct for a prio-2 core-1 writer preempting loopTask
  mid-append. Residual risk is Serial *line interleaving* (not ring corruption): the soak
  procedure greps for torn/interleaved lines with the pump alive; if found, `audio_info`
  drops to a queue like ICY (mandatory fallback) [VE-2-7].
- **perf instrumentation:** add `perf::record("wr.pump", …)` and
  `perf::record("wr.connect", …)`. **Slot budget [VE-2-3, binds all three touch-UX
  designs]:** production sites today are exactly 5 (`spotify.poll`, `display.bar`,
  `display.input`, `app.tick`, `vu.tick`) + `screenlog.tick` under SCREEN_LOG; this design
  adds `wr.pump` + `wr.connect`, M-TASKBAR-FEEDBACK adds `shell.switch` → 8 production =
  `MAX_PATHS` exactly, 9 under SCREEN_LOG, and `perf::record` **drops silently** on
  overflow (`perf.h:51`). **`MAX_PATHS` goes 8 → 10 in whichever of the trio lands first**;
  this table is the single source for the budget. Cross-task slot writes: registration is
  a non-atomic two-field claim racing `perf::reset()` [DEV-2-8] — accepted as
  diagnostic-grade noise (OQ3), or gate `wr.pump` behind SERIAL_DEBUG.
- **Pump observability (BP-036) [VE-2-2]:** the pump gets a first-class dbg surface —
  `get wrPump` → `{"alive":0|1,"cycles":N,"maxPumpMs":N,"maxMutexWaitMs":N,"stackHwm":N,
  "last":true}`; the pump is added to `get stacks`; task create / ack / self-delete each
  log one stable-prefix line (`[wrpump] created|ack|deleted`), so E3/E4 teardown checks are
  grep-able without a logic analyser.

## Lean / decision

**Option (a) — dedicated pump task, core 1, priority 2, Phase-1 mutex model.** Create at
first `_play()`, destroy with handshake in `suspend()`. Cadence `vTaskDelay(2 ms)` initial,
tuned on DUT. Phase 2 (command-queue ownership, async connect) is explicitly deferred and
separately gated.

Core placement is **not** judged an open two-way tie: (b)'s theoretical benefit (a clean
core 1) is smallest exactly when it matters (core 1 is quiet during playback — TLS yielded,
dataTask idle) while its risks (WiFi contention on the streaming path, TWDT on CPU0 idle)
are structural. (b) stays as the measured fallback with a concrete trigger: underruns on
the (a) soak exceeding baseline.

## Open questions

- **OQ1 — pump cadence vs halved DMA:** is 2 ms tight enough (or overkill) against
  PATCH-MEMBUDGET-4's ring at 128–192 kbps? Tune with `wrUnderruns`/`minBufPct` on DUT;
  consider pumping until `InBuff` free-space stops shrinking rather than once per wake.
- **OQ2 — logSink third-writer safety: RESOLVED** [DEV-2-5] — ring append is spinlock-safe
  (`portENTER_CRITICAL_SAFE(&g_mux)`, `logSink.h:33-67`). Residual: torn Serial lines —
  soak grep, queue fallback if found (§Callbacks) [VE-2-7].
- **OQ3 — perf slot cross-task writes:** torn reads *and* a non-atomic registration race
  vs `perf::reset()` [DEV-2-8] — accept as diagnostic-grade noise, or gate `wr.pump`
  behind SERIAL_DEBUG only.
- **OQ4 — `connecttohost` freeze magnitude:** measure (`perf::record("wr.connect")`) during
  Phase 1 to decide whether Phase 2 (async connect) is worth the state-machine surgery.
  The DEV-2-1 in-`loop()` connect paths (redirect/reconnect/playlist) count toward the same
  decision.
- **OQ5 — `isRunning()` transient semantics** (TASK-218's standing DUT-verify note): the
  mutex changes nothing here, but the Phase-0 baseline run is a chance to finally
  characterise it.

## Exit criteria (all on DUT, debug build unless noted)

- **E0 (baseline, before any change) — SHARED SESSION** [QM-2-2 + VE-2-1 + VE-3-2 +
  DEV-X-1]: one DUT session on current master records this design's baseline **and**
  M-TASKBAR-FEEDBACK's measurement matrix (the "WebRadio PLAYING" row is the same
  quantity). Contents: STOPPED vs PLAYING `hb` `loopMax`/worst-path (per-hb-window series,
  not one number), `wrUnderruns`/`minBufPct` over a defined window length (reused verbatim
  in E2), N≥5 injected-gesture drain-rate samples per state, **with `get wifi`/`[wifi-ev]`
  captured throughout — outage windows are attributed per M-WIFI-DIAG §3.4 and excluded/
  annotated before anything is scored**. This session runs before either TASK-278 or
  TASK-279 implementation merges; if TASK-278 lands first anyway, doc 3's starved-state
  "before" row is unmeasurable forever. E0 also confirms (or refutes) the premise that
  `display.input` is inflated during playback [VE-2-4] — if refuted, E1 drops that clause.
- **E1 (UI latency):** with radio PLAYING, **median of per-hb-window `loopMax`** ≤ 1.5× the
  STOPPED baseline median over a same-length window; hb windows overlapping CONNECTING
  state (`wrState` correlation) are excluded — Phase 1 deliberately leaves connect blocking
  [VE-2-5]. `display.input` clause conditional on E0 [VE-2-4]. Cross-check with a serialdbg
  `drag` injection: steps drain at ≥ the idle-state per-loop cadence.
- **E2 (no underrun regression):** `./run/wr-soak 30` — compared to E0 as **per-10-min
  rates over same-length windows** (not raw counts across unequal durations), with
  `[wifi-ev]`-attributed outage windows excluded [VE-2-1]. `minBufPct` ≥ baseline − 5 pts.
  Expectation is improvement (paints no longer block pump).
- **E3 (state-machine regression guard):** ADR-045 instrumented gate re-run (TASK-275
  procedure) 10/10, **run under the `[wifi-ev]` correlation — link-attributed failures
  trigger re-run per M-WIFI-DIAG §3.4, not FAIL** [VE-2-6]; `set wrDeadUrls 3` auto-skip
  bound + TASK-276 terminal-retry cadence reproduce (pacing/state-machine half only —
  `_debugForceConnFail` short-circuits before any Audio call, `webRadioApp.h:741-747`);
  **plus a real-stream death case [DEV-2-2]: `set wrUrl http://host:port/mount` against a
  local source, kill it mid-play (TASK-261 pattern), assert TASK-218 debounce →
  `_stopAudio` → retry executes under the mutex with the pump alive** — this is the only
  case that exercises the new task/mutex code against stream death, including the
  in-`loop()` reconnect path (DEV-2-1); measure the redirect/reconnect mutex-hold bound
  here (`maxMutexWaitMs`). Eject and taskbar-switch teardown clean: `[wrpump]
  ack`/`deleted` lines present and ordered before arena release, no crash, TLS resumed,
  `get heap` recovers to pre-entry level.
- **E4 (budget):** pump stack HWM headroom ≥ 2 KB (read via `get wrPump`/`get stacks`
  [VE-2-2]); CP1 `lfbInt ≥ 24 K` still holds at arena acquire **with the pump stack
  allocated after the arena** [DEV-2-3]; no TWDT trip across the soak.
- **E5 (build gates):** `./run/check` 5/5; production env behaviour identical when WebRadio
  is never entered (task exists only after first `_play()`).

---

## Panel dispositions (2026-07-03)

VE / DEV / QM returned **approve-with-changes**; every blocker/major applied in place above.
Reviews: [touch-ux-panel-VE-review.md](touch-ux-panel-VE-review.md) ·
[touch-ux-panel-DEV-review.md](touch-ux-panel-DEV-review.md) ·
[touch-ux-panel-QM-review.md](touch-ux-panel-QM-review.md).

- **DEV-2-1 (major)** (`Audio::loop()` calls `connecttohost()` internally on three paths;
  "per-call work is short" was false) → §(a) exception noted; §Locking model split into
  control-calls (blocking take) vs per-tick reads (timeout-take ≤50 ms, degrade to last
  snapshot); worst-case bound measured in E3; fork patch named as Phase-2-adjacent fallback.
- **QM-2-1 (major) + DEV-2-6** (teardown invariant was prose; ack-then-`vTaskDelete` left a
  re-entry window) → §Task lifecycle: enforced sequence — ack while holding no locks, then
  immediate self-delete (or terminal park); owner never deletes a possibly-inside-Audio
  pump; ack timeout + LOG_E tripwire.
- **DEV-2-2 (major)** (`wrDeadUrls` exercises zero pump/mutex code) → E3 real-stream kill
  case (wrUrl + host-side kill, TASK-261 pattern); wrDeadUrls kept for the pacing half.
- **QM-2-2 (major) + VE-2-1 + VE-3-2 + DEV-X-1** (shared baseline, windowing, ordering) →
  E0 rewritten as the shared session; same-length windows / per-10-min rates; `[wifi-ev]`
  attribution; land order pinned in roadmap: shared E0 → TASK-278 → TASK-277 → TASK-279
  blits.
- **VE-2-2 (major)** (pump invisible to harness) → §Pump observability: `get wrPump`,
  `get stacks` entry, `[wrpump]` lifecycle lines.
- **VE-2-3 (major, cross-doc)** (perf slots hit `MAX_PATHS=8`, silent drop) → §perf
  instrumentation: slot-budget table, `MAX_PATHS` 8→10 in whichever task lands first.
- **VE-2-4/2-5/2-6** (E1 premise/statistic, E3 environment) → folded into E0/E1/E3.
- **VE-2-7 + DEV-2-5** (logSink third writer) → OQ2 resolved (spinlock cited); torn-line
  soak grep with mandatory queue fallback.
- **DEV-2-3/2-4/2-8** (create order vs arena; `wrVol` lazy-construct hole; perf
  registration race) → §Task lifecycle order; `wrVol` clamp-store rule; OQ3.
- **QM-2-3/2-4/2-5/2-6** (inference labelling; uncited claims; stale ICY comment; missing
  Deps header) → applied in place.
- **DEV-2-7** (stale `Audio.cpp:192` "experiment-only" comment) → no doc change; fix
  when the file is next touched (recorded here so it isn't lost).

## E0 attempts (2026-07-03)

Two full 4-state sessions run (`app/tools/e0_baseline.py`, debug build, 10-min windows, N=5
taps/state). **Both link-dead — no scoreable E0 yet** (VE-2-1 attribution rule applied):

- Run 1: WiFi down from t≈150 s (BEACON_TIMEOUT → NO_AP_FOUND storm → parked, disc=29); all
  windows captured an unloaded loop (no TLS traffic, `last=-1`). WebRadio PLAYING never entered
  (station fetch impossible).
- Run 2: WiFi pre-flight PASSED (status 3, rssi −49), then the identical storm at t≈147 s:
  reason=200 → 2.42 s-cadence 201 storm (disc 30→99) → reason=39 → **parked dead, zero further
  reconnect attempts 40+ min** — filed as **TASK-283** (link supervisor gap). PLAYING never
  entered.

**Salvaged (network-idle rows, reproduced across 3 runs):** quiet-loop `loop_max` median 23 ms
(max 29–76); injected taskbar tap: drain ≈100 ms, tap-to-switch-committed median 83.6–97.9 ms
(N=5/state, spread <3 ms).

## E0 resolution (2026-07-03) — root cause was the AP, not the firmware

The link failures were the **router**, not the design: JNAP read showed the MX5600's 2.4 GHz on
`channel: 0` (auto-select); its channel-optimisation sweeps took the radio off-air 5–40 s every
1–2 min, host-confirmed by an independent 2nd radio (`resource/wifi-monitor/`). Pinning 2.4 GHz
to a fixed channel fixed it (host availability 87 % → 99 %+); residual host-confirmed blips
persist ~1 per 8–10 min even pinned (low-rate AP defect). TASK-283 link supervisor (all builds)
recovers wedged links; the TASK-282 promiscuous beacon watcher must NOT be left armed during a
run (it breaks STA reconnect — Heisenberg artifact, SERIAL_DEBUG-only).

**The PLAYING row also needs the `cyd2usb_webradio` (DISABLE_SPOTIFY) build.** On the prod build
the owner-account Spotify 403 (TASK-243) starves the shared dataTask TLS via `tlsYield`
(memory: tlsyield-starvation): the radio-browser station fetch returns `count=0/http=0` while the
*host* reaches the same API at HTTP 200 — proven by direct A/B (prod `count=0` → webradio build
`count=16`) minutes apart on the same DUT/network. No stations ⇒ PLAY parks in STOPPED.

### Decode-loaded baseline (E0 wr_playing, cyd2usb_webradio, 10-min continuous PLAYING)

`wr_state 2→2`, `playMs` 20 s→103 s (decode continuous). `--taps 0`; N=5 tap rows deferred to
the multi-app build (see M-TASKBAR-FEEDBACK).

| metric | idle baseline | **WebRadio PLAYING (decode on loopTask)** |
|---|---|---|
| `loop_max` median | 23 ms | **24 ms** |
| `loop_max` max (per-hb) | 23–36 ms | **141 ms** |
| >50 ms iterations / 10 min | 0 | **6** |
| worst path | app.tick | **app.tick** (calls `s_wr_audio->loop()`) |
| series | flat 23 | `25,27,28,25,23…76…23,141,27,24,25` |

**Finding — the case for this milestone.** Decode barely moves the *median* iteration (23→24 ms)
but blows the *tail*: 141 ms max, 6 spikes/10 min, worst path `app.tick` (the `Audio::loop()`
call site). This is the touch-drop mechanism precisely: playback is smooth most iterations, then a
decode/refill spike stalls one iteration to 76–141 ms and a touch sample landing in that window is
lost. The problem is **tail latency, not average load** — moving `Audio::loop()` to its own task
(this design) targets exactly the tail. E1's ≤1.5×-median bar (23→24 ms = 1.04×) would PASS on the
median alone and is therefore the **wrong statistic**; the real regression signal is the
>50 ms-iteration count and the per-hb max. **Amend E1 to gate on tail (max / >50 ms count), not
median** [supersedes the median framing].

**Caveats (annotated, non-invalidating).** (a) 57 in-window `[wifi-ev]`: residual router blips
churned the window, so some of the 6 spikes may be WiFi-reconnect stalls, not decode — a calm
10-min window is not obtainable on this AP (blips every ~8–10 min), so decode-tail and reconnect-
tail cannot be fully separated here; the tail-stall signature is nonetheless real and the
mechanism (app.tick worst-path) is decode-attributed. (b) Station idx 0 was a *slow stream*
(`minBufPct 0`, 1 underrun/window) — a marginal upstream, so **underruns here are not a clean
device baseline**; TASK-278 E2 must pick a fast station (or `./run/wr-soak` which already does).
`display.input` premise (VE-2-4): worst path stayed `app.tick`, never `display.input`, under
decode → **VE-2-4 refuted, E1 may drop the display.input clause.**

---

## Exit-criteria results (2026-07-07) — Phase 1 E1-E5 campaign

All on DUT, `cyd2usb_winamp_debug` (E2 on `cyd2usb_webradio` per `run/wr-soak`), firmware
`39e6c08` + the TASK-290 boot fix. Note this build is HARSHER than E0's PLAYING row
(Spotify enabled and 403-churning throughout — `last=403` heartbeats — vs E0's
Spotify-disabled build); the numbers held anyway.

### E1 (UI latency, tail-gated per the 2026-07-03 amendment) — **PASS**

10-min windows, same session, 0 in-window `[wifi-ev]` in all three states (calm windows —
the channel pin + a quiet AP phase finally delivered what E0 never got):

| state | median | max (per-hb) | >50 ms iters / 10 min | worst path |
|---|---|---|---|---|
| idle_clock | 23 ms | 153 ms¹ | 1¹ | app.tick |
| wr_stopped | 23 ms | **23 ms (flat)** | 0 | app.tick |
| wr_playing (pump) | 24 ms | **50 ms²** | **0²** | app.tick ≤24 ms / wr.pump 22-23 ms³ |
| *E0 wr_playing (loopTask decode)* | *24 ms* | ***141 ms*** | ***6*** | *app.tick (Audio::loop)* |

¹ hb[0] only, immediately post-boot (token-refresh window); all 19 later windows flat 23-24.
² hb[0] (213 ms, slow-path `wr.connect:83ms`) excluded per VE-2-5 — Phase 1 deliberately
leaves connect blocking; series decays 50→23 as the session settles.
³ `wr.pump` is the pump task's own perf slot (OQ3 cross-task write), not a loopTask stall.

**The design's target quantity — the decode tail on loopTask — is gone**: 141→50 ms max,
6→0 iterations >50 ms. Tap cross-check: 5/5 gestures delivered in every state; PLAYING drain
median 128.8 ms vs 113.5 idle (~1.14×), entered 112.7 ms vs 97.9 — no drops.

### E2 (underrun regression, `wr-soak 30`) — **PASS** (harness verdict FAIL attributed, see below)

Two full 30-min soaks (88 + 92 cycles, 20 s/station, 16 real stations): **0 arena acquire
failures**, lfb min 51188/55284 (never near the 24576 floor), **lfb ended above its start in
both runs** (61428→63476), max **1 underrun per session** across all 180 sessions, sustained
playback median 16.1 s of the ~16 s effective cap, no crash/TWDT. E0's underrun row was
declared dirty (slow station); today's rate — at most a handful of single-underrun sessions
per 30 min on fast stations — is comfortably "no regression, expectation improvement".

**Harness verdict disposition:** both soaks printed `VERDICT: FAIL` solely on the
acquire/release balance clause (81/77, then 90/89). The verbose per-cycle trace (run 2) shows
the counter diff is only ever 0 or exactly 1, flipping once mid-run and never growing — a
single `arena released` serial line lost at a command boundary (the harness's own
`reset_input_buffer()` discards in-flight lines). A real leak accumulates and permanently
steps lfb down 24 K per occurrence; lfb ending above start refutes it mathematically. Filed
as a verifier defect (TASK-292); does not gate E2.

### E3 (state-machine regression guard) — **PASS**, one pre-existing gap filed

- ADR-045 instrumented gate: **10/10 PASS**, skips=0 every trial, ttfp 0.1 s, hold ≥60 s,
  discΔ=0 (16 real stations, live mirrors).
- `wrDeadUrls 3` bound: skips 1/3, 2/3, park terminal, never loops — PASS. TASK-276
  terminal-retry re-armed after the 30 s backoff — PASS.
- Real-stream death (local host streamer, FIN-killed mid-play, DEV-2-2): the pump/mutex
  machinery held through 90 s of starved-stream churn — pump alive, no crash, no deadlock —
  and the measured DEV-2-1 mutex-hold bound is **maxMutexWaitMs 258-312 ms** (maxPumpMs
  39-48 ms), far under the 10 s teardown ack bound. **OQ5 answered, negatively**: the vendored
  lib keeps `isRunning()==true` indefinitely on a FIN-closed socket ("slow stream" forever),
  so TASK-218's predicate never arms — a pre-existing app-level detection gap, not a
  pump/mutex regression (filed **TASK-291** with a bufPct-based secondary-predicate
  direction).
- Teardown (eject after the death case, i.e. worst-state teardown): `[wrpump] ack` →
  `deleted` → `arena released` strictly ordered, TLS resumed, pump gone (`alive:0`), heap
  recovered to pre-entry. PASS.

### E4 (budget) — **PASS**

Pump stack HWM headroom **4624 B** ≥ 2 KB bar (8 K stack, ~3.5 K peak use). Arena acquire
`lfbBefore=61428` ≥ 24 K with the pump stack allocated after the arena [DEV-2-3]; held ≥51 K
across both soaks (180 acquires, 0 FAILs). No TWDT trip anywhere in the campaign (2×30-min
soaks + all E1/E3 sessions).

### E5 (build gates) — **PASS**

`./run/check` 6/6 throughout. Production build behaviour unchanged when WebRadio is never
entered (task created only at first `_play()`); prod firmware reflashed and heartbeat-verified
after every DUT stage.

**Phase 1 exit criteria: met.** Campaign incidentals fixed/filed along the way: TASK-290
(boot SPIFFS-path persist re-begin deauth → 0.0.0.0 boots — fixed), TASK-291 (FIN-close
stream-death detection gap — open, P2), TASK-292 (wr-soak balance counter false-FAIL —
open, P3).

**Dispositions ratified (human, 2026-07-07):** the E2 PASS-with-disposition (harness
false-FAIL, TASK-292) and the E3 scoped pass (TASK-291 carries the FIN-close detection gap)
are final. LL-097 from this campaign adopted as BP-044.
