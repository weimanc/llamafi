# Design — M-AUDIO-ENGINE: extract the audio engine from WebRadio

> Owner: Architect
> Status: accepted
> As-built: 2026-08-07 (ADR-059 signed off; implementation authorised)
> Date: 2026-08-07
> Parent: [M-WINAMP-PLAYER.md](M-WINAMP-PLAYER.md) (workstream 2 of 4)
> Feeds: ADR-059 D2
> Tracked-as: TASK-409, TASK-410
> Registers: `localplay-001` · X050 · X051 · X063

**Standalone value:** partial. The extraction (TASK-409) is a behaviour-neutral refactor that stands
on its own — it turns a 2 365-line app header into an app plus a reusable engine, and it is worth
doing even if local playback never ships. It does not depend on M-SDFS. TASK-410 (the file source)
does depend on M-SDFS passing.

---

## 1. Context

There can be exactly one `Audio` object on this hardware: one internal DAC (GPIO26), one 23 216 B
Helix decoder arena, one 6 400 B InBuff. Today all of it is owned by WebRadio as file statics inside
`webRadioApp.h`:

| Thing | Current home |
|---|---|
| `s_wr_audio` (`Audio*`, lazily `new`ed) | `webRadioApp.h:187` |
| `s_wrAudioMutex` — guards every `Audio` method call | `webRadioApp.h:323` |
| `wrAudio` pump task (core 1, prio 2) | `webRadioApp.h:303`ff |
| `wrPumpConnect` request/result posting | `webRadioApp.h:340`ff |
| `mb_arena` acquire/release | `webRadioApp.h:317`, `:456`, `:498`, `:719` |
| `audio_process_extern` visualisation tap | `webRadioApp.h:223` |
| `audio_info`, `audio_showstreamtitle` callbacks | `webRadioApp.h:155`, `:166` |
| volume sink + `wrScaledVolume()` | `webRadioApp.h:385`ff |

A second consumer cannot construct its own instance, and calling into a radio app's header from a
local-file app is an uncontracted dependency. Hence extraction.

## 2. What is being reused (and therefore not rebuilt)

This is the answer to "can we reuse WebRadio's decoder / the Helix lib?" — **yes, entirely.**

| Component | Reuse |
|---|---|
| Helix MP3 decoder (`lib/ESP32-audioI2S/src/mp3_decoder/`) | **unchanged.** Local files decode through the identical path. There is no second decoder and no new codec integration. |
| `mb_arena` (`lib/ESP32-audioI2S/src/mb_arena.{h,cpp}`) | **unchanged.** It is a generic fixed-slot free-list allocator, not MP3-specific. Sizing is unchanged: the 23 216 B HWM is the measured sum of the same nine Helix structs, and a file source allocates exactly the same nine. |
| InBuff (6 400 B, `wrApplyInBufTrial`) | unchanged; the library fills it from a `File` instead of a socket. |
| pump task, mutex, request/result posting | unchanged; only the connect payload differs. |
| `audio_process_extern` vis tap | unchanged — the spectrum/wave visualisers (TASK-387/388) work for local files for free. |
| `aac_decoder`, `flac_decoder` (also vendored) | **not enabled.** The arena is sized for MP3's struct set; enabling another codec changes the HWM and invalidates `mem_manifest.yaml`. Explicit non-goal. |

Net new decode code for local playback: **none**. The only new surface is where bytes come from.

## 3. Design

```
audio/audioEngine.h
  // NOTE (DEV-4): no default member initialisers here. Under -std=gnu++11 an NSDMI makes
  // the struct a non-aggregate and every Source{URL, path} call site stops compiling.
  // This project has already paid for that once (TASK-327, SButton et al).
  // NOTE (DEV-8): `str` is BORROWED for the duration of the call only. connect() copies it
  // into the pump task's own fixed buffer (today s_wrPumpConnectUrl) before returning —
  // that ownership model exists so the posting task never outlives the caller's storage.
  // Do not let a stack pointer cross the task boundary.
  struct Source { enum Kind { URL, FILE } kind; const char* str; };
  bool connect(const Source&);      // posts to the pump task, polls result — existing shape
  void stop();  void setVolume(int);  bool isRunning();
  void acquire();                   // mb_arena + pump task bring-up
  void teardown();                  // pump task → Audio → arena, in that order
```

`connect()`'s FILE arm calls `connecttoFS(SD, path)` where the URL arm calls
`connecttohost(url)`. Everything around it — the multi-second-blocking-call-off-loopTask design
(TASK-398), the ABORT/TEARDOWN request precedence, the arena-before-task ordering (DEV-2-3), the
volume seam — is untouched.

**The extraction is a pure move.** No logic change, no reordering, no "while we're here" cleanup.
That code carries the fixes from TASK-278, 287, 289, 291, 295, 299, 392 and 398; a refactor that
also changes behaviour makes any regression undiagnosable.

## 4. Auto-advance hook (TASK-410 onward)

`audio_eof_mp3(const char*)` is declared `__attribute__((weak))` in `Audio.h:77` and implemented
nowhere in this firmware. It is the end-of-file signal local playback needs.

**It fires on the audio pump task, from inside `Audio::loop()`, with the engine mutex held.** It may
therefore only set a flag. Opening the next track from inside it calls `connecttoFS()` from the task
that already holds the mutex — self-deadlock. The flag is drained on loopTask's next tick, which is
also the only context allowed to touch SD, the playlist model and the display.

This is the same post-a-request discipline the `wrPumpConnect` path already uses. Reuse it; do not
invent a second mechanism.

**Enforced, not just documented (ADR-059 D12).** TASK-410 also captures the loopTask handle in
`setup()` (`xTaskGetCurrentTaskHandle()` into a file static — there is no `g_loopTaskHandle` today,
DEV-5) and asserts on it at the head of the open-next-track path:

```c
configASSERT(xTaskGetCurrentTaskHandle() == g_loopTaskHandle);
```

This replaces a reserved test id with a runtime assert, which is strictly stronger: it holds on every
debug execution rather than on the one run where someone remembered to probe for it.

## 5. Build cost

Dropping `-DAUDIO_NO_SD_FS` (required for the FILE arm) costs a measured **88 B of static DRAM and
~4 KB of flash** — see [M-SDFS](M-SDFS-sd-card-exploration.md) §4 for the method and the full table.

## 6. Verification obligation

Behaviour-neutrality is the whole contract, so it is verified rather than argued:

1. `./run/check` 6/6 on both envs.
2. **A `./run/wr-soak` of ≥30 min** (VE-7 — the previous wording, "at or above the duration that
   caught the DMA-gate regression", was not a number anywhere, so it would have been read as whatever
   was convenient). Short soaks have given false confidence on precisely this code before; a clean
   2-minute run is not evidence.
3. WebRadio play / skip / stop / eject / error-retry paths exercised, including the stall-retry and
   FIN-killed-stream paths (TASK-291/295).
4. `get dataq` and the arena counters (`mb_arena_acquire_total` / `release_total` /
   `acquire_fail_total`) balanced before and after — the invariant
   `acquires - releases == (active ? 1 : 0)` must hold.

## 7. Open questions

- **OQ1** — does the engine own the `audio_*` callbacks, or forward them to the active client?
  Forwarding is cleaner but adds an indirection on the pump task's hot path. Lean: engine owns them
  and exposes a client pointer, matching how `audio_process_extern` already resolves.
- **OQ2** — retire `handleVolumeGesturePublic()`? It exists only because `handleWinampInput()` is
  Spotify-hardcoded, which the parent design's capability mask fixes. Retire it in its own commit,
  never as a side effect: it shares the `D_VOLUME_DRAG` state machine (TASK-352) and WebRadio's
  volume-drag path already cost TASK-406 a missing-log-line bug.

## 8. Test & validation

Ids reserved in the `T_AE_` family. The governing property is **behaviour-neutrality**, which is
tested by re-running WebRadio's existing suite unchanged — not by writing new tests for the engine.
New ids cover only what the extraction itself can break.

### TASK-409 — engine extraction (pure move)

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_AE_01` | No WebRadio behavioural change | DUT — existing `m-webradio-dut.md` suite + `T_WR_*` / `T_WRUI_*` families, unchanged. **Baseline = ≥3 full runs before the extraction lands**, flaky set pre-declared from them (ADR-059 D13 / VE-3) | **no test that passed in all 3 baselines fails after**, and no new failure outside the pre-declared flaky set. A single-run "identical pass set" bar fails on known flake — `T_WR_TLS_01`, `T169`, `T_PR_05` — not on regression |
| `T_AE_02` | Arena lifecycle balanced | DUT serial — `get wrArena` before/after 20 play/stop cycles | `acquires - releases == (active ? 1 : 0)` holds throughout; `acquire_fail_total` unchanged |
| `T_AE_03` | No decode regression under load | DUT — `./run/wr-soak` | **≥30 min** (VE-7: "the duration that caught the DMA-gate regression" was never a figure anywhere, so an implementer would pick something convenient — the exact failure this bar exists to prevent). Zero underruns, no heap decline, no WDT |
| `T_AE_04` | Teardown ordering preserved | DUT — eject mid-`CONNECTING`, ×10 | pump task torn down before `Audio` before arena; no loopTask block > 100 ms (TASK-398's whole point) |
| `T_AE_06` | Build gates green | host — `./run/check` | 6/6 both envs |

### TASK-410 — file source (`connect(FILE)`)

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_AE_07` | A local MP3 plays | DUT — hardcoded path, audible | plays to completion, no underrun |
| `T_AE_08` | `AUDIO_NO_SD_FS` removal is budget-bounded | host — `run/build-debug` + `.map` extents | `dram0_0_seg` headroom re-derived and recorded; ≥10 KB after TASK-423's reclaim |
| `T_AE_09` | Arena HWM unchanged by the file path | DUT serial — **fresh boot, file playback only, no stream connect**, then `get wrArena` HWM (VE-8: `mb_arena_hwm()` is a session high-water mark — any earlier stream playback contaminates it and the assertion becomes vacuous) | **23 216 B** — same nine Helix structs as the stream path. If it differs, the codec assumption in §2 is wrong |
| `T_AE_10` | `audio_eof_mp3` fires and does not deadlock | DUT — play a short file to its end, ×10; "stall" measured via `perf::record()` on the loopTask tick (VE-2: unmeasured "no stall" degrades to "it didn't crash") | callback observed 10/10; **max loopTask tick gap < 100 ms**, matching `T_AE_04`'s bound; flag drained on loopTask, not acted on in-callback |

> **VE status annotation, 2026-08-15 (TASK-443, withdrawn — successor TASK-452).** Rationale and replacement criteria are in
> `docs/verification/test_plan.md`, suite **M-AUDIO-ENGINE** ("Corrections to existing ids"); this is
> the pointer, not a rewrite of the ids above.
>
> - **`T_AE_09` — BLOCKED.** If the ruling (retire the arena from the FILE path) is accepted, the
>   criterion `mb_arena_hwm() == 23 216` is falsified *by construction*: `s_hwm` is written only by
>   the bump allocator (`mb_arena.cpp:180`), which the libc fallback never reaches, so the metric
>   reads **0** on every FILE session. **0 is an absent instrument, not a pass — do not report this
>   id green on `hwm == 0`.** Its **PASS of 2026-08-10 (commit `7f01680`) stands as taken**, on the
>   arena'd path; it does not carry over. Replacement criterion, blocked on libc-fallback accounting
>   landing in `get arenaStats`: `Δ libcBytes == 23 216 × tracks` and `libcMax == 8 708`
>   (`SubbandInfo_t.vbuf`, `mp3_decoder.h:176`).
> - **`T_AE_10` — criteria unchanged, weight increased.** End-of-file is exactly where `Audio` frees
>   the nine Helix buffers (`Audio.cpp:3053`) and the next `connecttoFS` reallocates them
>   (`:3769`), so post-ruling this id is the smallest instance of the fragmentation experiment, not
>   only a deadlock check. **Its ×10 repetition merges into `T_AE_12`** (repeat-all ×10 over a
>   5-track playlist = 50 cycles) — run the repetition once, at the deeper depth.
> - **`T_AE_07` — criteria stand, evidence stale.** Its 2026-08-10 PASS predates both TASK-432's fix
>   and the ruling; re-run alongside `T_AE_11`.

**Validation notes.** `T_AE_01` is the load-bearing test and it is *deliberately not new work* — the
value is that the existing suite runs untouched. Baseline it **before** the extraction lands, or
there is nothing to compare against.

`T_AE_05` ("the diff is a move") was **removed from the test set** on VE-9: it is a review gate with
no repeatable procedure, and counting it as a test inflates coverage with something that cannot be
re-run. It survives as a **review checklist item on TASK-409** — `git diff -M --stat` should show
≥95 % rename similarity on the moved block, and no hunk should change behaviour. `T_AE_09` is cheap and falsifies the single biggest assumption
in this workstream (that a file source allocates the same decoder set as a stream source).

## 9. Exit criteria

1. `webRadioApp.h` contains no `Audio`, `mb_arena` or pump-task symbol; all of it lives in
   `audio/audioEngine.h`.
2. The move commit's diff is reviewable as a move — no behavioural hunks.
3. §6 items 1–4 all green.
4. `connect(FILE)` plays one hardcoded path to the speaker (TASK-410), gated on M-SDFS passing.
