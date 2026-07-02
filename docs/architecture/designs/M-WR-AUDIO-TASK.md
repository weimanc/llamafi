# Design — WebRadio audio decode off loopTask (dedicated pump task)

> Owner: Architect
> Status: draft
> Date: 2026-07-02
> Feeds: (ADR TBD — promote the lean once Phase-1 DUT numbers land)
> Tracked-as: TASK-278

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
  playback window and dataTask is idle after the station fetch — the only busy core-1 task
  while PLAYING is loopTask itself.
- **Playback is strictly foreground.** `switchApp()` calls `suspend()` on the outgoing app
  (main.cpp:1828); `WebRadioApp::suspend()` stops audio, and (MEMBUDGET_PHASE1 — now the
  production env, platformio.ini cyd2usb_winamp) **deletes the Audio object and releases
  the JIT arena** (TASK-267/ADR-047 Amd 1). Eject does the same via `_stopAudio()` +
  `switchApp(Spotify)`. No background-playback requirement exists — the pump task's
  lifecycle can bind to the app being active.
- **v2.3.0 has no built-in audio task** (upstream added one in 3.x; we are frozen on the
  2.3.0 fork carrying PATCH-MEMBUDGET-1..4). Any task model is ours to build — but the
  project already has two proven command-queue task patterns to copy (`spotifyTask`,
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
paint can no longer starve the pump, and the pump's per-call work (one header parse / one
socket read / one decode chunk) is short, so UI preemption is bounded and frequent rather
than long and rare — exactly the latency shape we want.

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
  core 0 — the exact contention ESP32-audioI2S's own guidance warns about (WiFi bursts
  starving decode). Our WiFi is busy *while streaming* by definition.
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
every `Audio` method. Pump: take → `loop()` → give (short hold). UI/tick side: take around
`connecttohost`, `stopSong`, `setVolume`, and the per-tick read cluster
(`inBufferFilled/Free`, `isRunning`). `connecttohost` holds the mutex for seconds — the pump
simply blocks meanwhile, which is correct: there is nothing to pump until connect returns.
The WR state machine, TLS yield/resume pairing, retry/skip pacing, and every dbg surface
keep their exact current shape and call sites. **This is the minimal-regression cut.**

**Phase 2 (separate, optional, gated on Phase-1 numbers) — ownership + command queue:** the
pump task *owns* the Audio object; UI sends `PLAY(idx)/STOP/VOL` via queue (the
spotifyTask/dataTask pattern); connect results come back as events; tick() reads a
`volatile` snapshot (bufPct, lastRunningMs, connect outcome) instead of calling Audio. This
kills the `connecttohost` UI freeze too — but it makes `_play()` asynchronous, which
restructures `_onPlaybackFailed`/CONNECTING semantics — real surgery on the freshly
validated ADR-045/TASK-276 machine. Do not bundle it with Phase 1. Measure the freeze first
(`perf::record("wr.connect", …)` around the call).

### Cross-cutting details (per the lean, Phase 1)

- **Task lifecycle:** create the pump task lazily at first `_play()` (alongside the JIT
  arena acquire); it blocks on the mutex/delay cycle and self-idles (skips `loop()`) when
  `!s_wr_audio || !isRunning()`. Destroy it in `suspend()` **with a handshake**: set a stop
  flag → pump acknowledges (semaphore) at the top of its cycle, *outside* `Audio::loop()` →
  then `vTaskDelete` → then `stopSong()` → `delete s_wr_audio` → `mb_arena_release()`.
  **Invariant: the Audio object is never destroyed, and the arena never released, while the
  pump could be inside a Audio method.** Eject and taskbar-switch both route through
  `suspend()`, so one teardown path covers all exits. Per-station churn (auto-skip) does
  NOT churn the task — it persists across `_play()` calls within a session.
- **Stack/heap:** 8 KB stack, transient (freed on suspend with the task). No TLS on this
  path (streams are HTTP-only per ADR-029 amendment; HTTPS connect attempts fail allocation
  long before deep stack use). Measure `uxTaskGetStackHighWaterMark` on the soak; trim to
  HWM + 2 KB (the TASK-240 rule). Budget check: 8 KB transient sits inside the window the
  Spotify teardown overlay (TASK-264/M-RECLAIM) freed for playback — verify with
  `get heap` at CP1 that `lfbInt ≥ 24 K` still holds for the arena acquire.
- **POSBAR/ICY/metrics reads:** ICY queue unchanged (its producer just moves task — it was
  written for exactly this, webRadioApp.h:80). POSBAR reads (`inBufferFilled/Free`) and
  `isRunning()` move inside the tick-side mutex hold — sub-microsecond reads, no contention
  concern. TASK-263 underrun edge-counting stays in tick() Phase 1 (sampling at tick cadence
  under the mutex is the same fidelity it has today); moving it into the pump (fresher view)
  is a Phase-2 nicety.
- **Callbacks:** `audio_showstreamtitle` (→ `xQueueOverwrite`, ISR-safe pattern, fine) and
  `audio_info` (→ `LOG_I`) now fire from the pump task. `LOG_*` is already used cross-task
  (dataTask, spotifyTask) — assumed safe; verify logSink's ring lock covers a third writer
  (open question OQ2).
- **perf instrumentation:** add `perf::record("wr.pump", …)` from the pump so the hb line
  attributes pump cost; `perf` slot updates are monotonic-max uint32 writes — cross-task
  benign for a diagnostic (OQ3 notes the (unlikely) torn-read caveat).

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
- **OQ2 — logSink third-writer safety:** confirm the ring/lock handles a prio-2 writer
  (`audio_info` → `LOG_I`) preempting loopTask mid-append. If not, drop `audio_info` to a
  queue like ICY.
- **OQ3 — perf slot cross-task writes:** accept torn-read risk on a diagnostic, or gate
  `wr.pump` recording behind SERIAL_DEBUG only.
- **OQ4 — `connecttohost` freeze magnitude:** measure (`perf::record("wr.connect")`) during
  Phase 1 to decide whether Phase 2 (async connect) is worth the state-machine surgery.
- **OQ5 — `isRunning()` transient semantics** (TASK-218's standing DUT-verify note): the
  mutex changes nothing here, but the Phase-0 baseline run is a chance to finally
  characterise it.

## Exit criteria (all on DUT, debug build unless noted)

- **E0 (baseline, before any change):** record STOPPED vs PLAYING `hb` `loopMax`/worst-path
  and a 10-min `wrUnderruns`/`minBufPct` window on current master. All later criteria are
  relative to this.
- **E1 (UI latency):** with radio PLAYING, `loopMax` ≤ 1.5× the STOPPED baseline over a
  10-min window, and `display.input` no longer inflated vs idle. Cross-check with a
  serialdbg `drag` injection: steps drain at ≥ the idle-state per-loop cadence.
- **E2 (no underrun regression):** `./run/wr-soak 30` — `wrUnderruns` ≤ E0 baseline + 1,
  `minBufPct` ≥ baseline − 5 pts. Expectation is improvement (paints no longer block pump).
- **E3 (state-machine regression guard):** ADR-045 instrumented gate re-run (TASK-275
  procedure) 10/10; `set wrDeadUrls 3` auto-skip bound + TASK-276 terminal-retry cadence
  reproduce; eject and taskbar-switch teardown clean (no crash, TLS resumed, arena
  released — `get heap` recovers to pre-entry level).
- **E4 (budget):** pump-task stack HWM headroom ≥ 2 KB; CP1 `lfbInt ≥ 24 K` still holds at
  arena acquire; no TWDT trip across the soak.
- **E5 (build gates):** `./run/check` 5/5; production env behaviour identical when WebRadio
  is never entered (task exists only after first `_play()`).
