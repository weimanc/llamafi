#pragma once
// audio/audioEngine.h — system-owned audio engine (TASK-409 / ADR-059 D2).
//
// PURE MOVE from webRadioApp.h: exactly one Audio object (one internal DAC,
// one 23 216 B Helix arena, one 6 400 B InBuff) can exist. WebRadio owned all
// of this as file statics; it and (from TASK-410) LocalPlayer become peer
// clients instead. No logic changed, no reordering, no opportunistic cleanup
// — this code carries the fixes from TASK-278/287/289/291/295/299/392/398 and
// a diff that also changes behaviour makes any regression undiagnosable.
//
// M-SRCLAYOUT Stage E (TASK-471): this header used to say "every symbol below
// keeps its internal (static) linkage exactly as it had in webRadioApp.h" —
// true only while audioEngine.h had exactly one includer (main.cpp). Now that
// webRadioApp.h/localPlayerApp.h are their own translation units and both
// reach into this engine directly by name, every symbol they touch had to
// become a real extern declaration here with its one definition in
// audioEngine.cpp — otherwise each TU would compile its own private copy of
// "the" Audio object, exactly the silent-divergence hazard M-SRCLAYOUT §5
// flagged as the reason this split was deferred past the other Stage E
// conversions. Values, names and ordering are unchanged; only linkage moved.
// Genuinely internal helpers (never named outside this engine) stay static,
// now in audioEngine.cpp instead of the header.

#include <Arduino.h>
#include <Audio.h>
#include <SD.h>  // TASK-410: connecttoFS(SD, path) — AUDIO_NO_SD_FS dropped
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include "esp_task_wdt.h"
#include <esp_heap_caps.h> // T_MB_PROBE_00: caps-split for CP1/CP2 (TASK-261 Phase 0+2)
#include <new>             // TASK-432: std::nothrow — a bare `new Audio` reset the device
#ifdef MEMBUDGET_PHASE1
#include "mem/arena/mb_arena.h"  // Phase 2: arena HWM reporting at CP2
#endif
#include "settingsStorage.h"
#include "logSink.h"
#include "perf.h"
#include "winamp/vuMeter.h"

// TASK-392: ESP32-audioI2S's own default connect budget (Audio.h: 250ms plain
// HTTP / 2700ms HTTPS) is too tight for a real handshake over consumer internet
// and was never raised here. TASK-391's host-side A/B (same hosts/network/code
// path, only the timeout varied) found 36/36 connects succeeding at a 5s budget
// vs 25/36 (~69%) at the capped default — real false-negative "unreachable"
// failures, not real outages. 5s/7s here: 5s matches the tested generous budget
// directly; 7s pads the HTTPS leg for the TLS handshake on top of TCP, staying
// well under TASK-295's 10000ms extreme-case ceiling for known-bad hosts.
static constexpr uint16_t WR_CONNECT_TIMEOUT_MS = 5000;
static constexpr uint16_t WR_CONNECT_TIMEOUT_MS_SSL = 7000;

// TASK-224: ICY StreamTitle buffer length, used consistently across the audio
// callback, the queue's element size, tick()'s receive buffer, and _icyTitle.
static constexpr size_t WR_ICY_TITLE_LEN = 104;

// TASK-224: volume ceiling (matches settingsStorage.h's webRadioMaxVolume
// "1-21" comment / ESP32-audioI2S's setVolume() range).
static constexpr uint8_t WR_VOLUME_MAX = 21;

// TASK-209 / M-WEBRADIO §HW Mod: without the SC8002B gain-reduction mod the 8-bit
// internal-DAC output overloads and clips above ~12/21, so stock hardware is
// soft-capped here. With the mod installed the full 1–21 range is usable.
static constexpr uint8_t WR_VOLUME_SOFT_CAP_STOCK = 12;

// The volume actually fed to audio.setVolume(): the user's configured ceiling
// (webRadioMaxVolume) clamped to the hardware-safe range — soft cap on stock,
// full range with the HW mod. Single source of truth for all production setVolume
// sites (the wrVol debug setter stays unclamped so calibration can reach the clip
// point). Free function so settingsStorage's g_settings is the only dependency.
inline uint8_t wrEffectiveVolume() {
    uint8_t hi = g_settings.webRadioHwMod ? WR_VOLUME_MAX : WR_VOLUME_SOFT_CAP_STOCK;
    return g_settings.webRadioMaxVolume > hi ? hi : g_settings.webRadioMaxVolume;
}

// TASK-352: the Winamp slider's session volume (webRadioVolumePct, 0-100)
// scales *within* the wrEffectiveVolume() ceiling — the ceiling stays the
// ceiling (TASK-209/T_WR_VOL_03 clamp semantics untouched), the slider is
// relative to it. +50 rounds instead of truncating.
inline uint8_t wrScaledVolume() {
    return (uint8_t)(((uint32_t)g_settings.webRadioVolumePct * wrEffectiveVolume() + 50) / 100);
}

// ── ICY metadata queue ───────────────────────────────────────────────────────
// Written from ESP32-audioI2S callback — runs on the wrAudio pump task (core 1,
// prio 2, TASK-278/M-WR-AUDIO-TASK); read in tick() (loopTask, core 1, prio 1).
// Depth 1 + overwrite: old unread title is replaced by the newest one.

extern QueueHandle_t s_icyTitleQueue;

// Required by ESP32-audioI2S — weak-linked extern resolved by user code.
void audio_showstreamtitle(const char *info);

// T_MB_PROBE_00 CP2 (TASK-261 Phase 0): decoder-init capture point.
// audio_info is the ESP32-audioI2S broad info callback; fires on decoder init
// ("MP3Decoder ... initialized") — AFTER InBuff calloc + Helix alloc, so this
// is the moment both big allocations have landed and heap drop is measurable.
void audio_info(const char *info);

// TASK-410 / ADR-059 D12: loopTask's handle, captured once in setup() (this
// file has no g_loopTaskHandle of its own before TASK-410 — there was no
// callback that needed to prove which task it ran on). Everything that must
// only ever run on loopTask asserts against it, below.
extern TaskHandle_t g_loopTaskHandle;

// M-AUDIO-ENGINE-extraction.md §4: audio_eof_mp3 fires on the pump task, from
// inside Audio::loop(), WITH THE ENGINE MUTEX HELD. It may therefore only set
// a flag — opening the next track here would call connecttoFS() from the task
// already holding the mutex it needs: self-deadlock. Weak-linked by
// ESP32-audioI2S (Audio.h:77); resolved here now that AUDIO_NO_SD_FS is gone.
extern volatile bool s_aeEofPending;

void audio_eof_mp3(const char *info);

// Drains the eof flag. Callable ONLY from loopTask — it is the sole context
// allowed to touch SD, the playlist model and the display (§4) — enforced,
// not just documented, per ADR-059 D12.
//
// TASK-410 scope is a single hardcoded file, so there is no next track to
// open yet; this just proves the hook fires without deadlocking (T_AE_10).
// Auto-advance is TASK-413+'s job, landing inside this same drain point.
// TASK-415: monotonic count of drained end-of-file events. LocalPlayerApp
// polls it to notice "the track finished" without owning the eof flag itself
// (the flag is engine state and must stay single-drain — two consumers racing
// to clear it is how an auto-advance silently skips a track). TASK-418's
// auto-advance hangs off the same drain point, not off a second flag.
extern uint32_t s_aeEofCount;
inline uint32_t aeEofCount() { return s_aeEofCount; }

void aeDrainEof();

// ── Audio singleton ──────────────────────────────────────────────────────────
// Internal DAC, GPIO26 (I2S_DAC_CHANNEL_LEFT_EN = SC8002B amp).
// Pointer used to defer construction until after I2S is ready.

extern Audio* s_wr_audio;

// PROP-005 rung 3 (EXP-018/TASK-387): per-band makeup gain for the real
// Goertzel spectrum below. EXP-018 measured real per-band energy as
// visibly "under-driven" vs. rung 2's broadband peak/RMS — a single-
// frequency resonance carries much less amplitude than the full-signal
// peak once real program energy is spread across the band, and the
// narrow high bands (log-spaced 80 Hz-14 kHz over a fixed-length Goertzel
// window, so every band sees the same Hz-wide analysis window) capture an
// even smaller slice of a typically pink/rolled-off real spectrum. Flat
// makeup gain (20 dB base + 1.0 dB/band tilt toward the highs) derived
// empirically against live WebRadio stations during the TASK-387 DUT
// gate — mirrors SPEC_BAND_FREQ's log spacing, same flash-resident
// constexpr, zero new DRAM.
constexpr float SPEC_BAND_GAIN[vu::SPEC_BAND_COUNT] = {
    10.000f, 11.220f, 12.589f, 14.125f, 15.849f, 17.783f, 19.953f, 22.387f,
    25.119f, 28.184f, 31.623f, 35.481f, 39.811f, 44.668f, 50.119f, 56.234f,
    63.096f, 70.795f, 79.433f,
};

// PROP-005/M-WEBRADIO-REAL-VIS: real per-block peak envelope for WebRadio's
// VIS_VU mode, plus (rung 3, TASK-387) real per-band spectrum energy for
// VIS_SPECTRUM. Fires once per decoded PCM block (interleaved L/R int16,
// pre-gain/filter/volume — Audio.cpp's sendBytes()), on the wrAudio pump
// task, before playChunk() sends the block to I2S. Writes directly into
// vu::lLevelRef()/rLevelRef() and (via vu::updateSpectrumBar()) the
// promoted specH/specVel/specPeak arrays — the same statics the synthetic
// Spotify path uses — rather than any new storage: SERIAL_DEBUG-enabled
// builds on this board have ~0 bytes of static-BSS headroom (see
// EXP-015/PROP-007). DUT-verified cost-free (maxPumpMs unchanged vs a
// no-op baseline, EXP-016; 19-band Goertzel unchanged again, EXP-018).
//
// Spectrum: one Goertzel resonator per band, recomputed fresh every block —
// no coefficient caching, matching EXP-018's honest per-block cost
// measurement. Mono mix (L+R)/2, same simplification tickSpectrum's
// synthetic mode already made via its single `envelope` value.
void audio_process_extern(int16_t* buff, uint16_t len, bool *continueI2S);

// TASK-432: the I2S DMA floor that must be clear before an Audio can be
// constructed. i2s_driver_install()'s DMA malloc failure is UNCHECKED in the
// vendored Audio ctor — it null-derefs (LoadProhibited, EXCVADDR 0x1c) and
// reboots. TASK-289 measured it failing at lfbDma 13.8 KB and succeeding at
// 30+ KB; 16 KB sits just above the known-bad point without rejecting plays
// that fragmentation alone would allow. Was a literal inside
// WebRadioApp::_play(); hoisted here so the FILE arm gets the same guard
// rather than a second copy that can drift.
static constexpr size_t AE_I2S_DMA_FLOOR_BYTES = 16 * 1024;
#ifdef SERIAL_DEBUG
// TASK-442: runtime override for the floor (`set aeDmaFloor <bytes>`, 0 =
// disable the check). The floor is a *largest-contiguous-block* test, but
// i2s_driver_install() allocates several small DMA buffers, not one 16 KB
// block — so the check may reject states the driver could actually serve.
// Deciding that needs an A/B on hardware, which needs this knob.
extern size_t s_aeDmaFloorOverride;
#define AE_DMA_FLOOR() (s_aeDmaFloorOverride)
#else
#define AE_DMA_FLOOR() (AE_I2S_DMA_FLOOR_BYTES)
#endif

// TASK-432: the ONLY place an Audio is constructed. Both arms (WebRadio's
// _play() and the FILE arm's aeConnectFile()) route through here, so the DMA
// floor and the allocation check cannot diverge between them.
//
// Returns false instead of crashing on either failure mode — the bare `new`
// this replaces threw `bad_alloc` out of aeConnectFile(), which nothing
// catches: abort() -> std::terminate() -> device reset, reproduced on the
// ordinary `set plPlay` path on cyd2usb_player. A memory shortfall must
// degrade to a visible "play FAILED", never to a reset.
//
// Callers own their own rollback (TLS yield, play state); this function
// leaves no partial engine behind when it fails.
// TASK-432 (follow-up, 2026-08-14): give the arena back when a play attempt
// dies before an engine exists.
//
// The first cut of TASK-432 deliberately left the arena held on the failure
// path, reasoning that mb_arena_acquire() is not ref-counted and a release
// could yank it from a live WebRadio session. That reasoning was wrong, and
// the gate's own "is the engine still usable?" check caught it on the DUT:
//
//   arena acquire=24576B lfbBefore=28660 OK     <- arena taken
//   Audio alloc failure INJECTED — abort play    <- guard fires, arena kept
//   DMA pool too low for I2S init: lfbDma=4084   <- next play, 24 KB missing
//
// One failed play poisoned every later play until mode exit — strictly worse
// than the reset it replaced, for a user who would just tap play again.
//
// The feared case cannot occur: a live WebRadio session implies s_wr_audio is
// non-null, and then aeEnsureAudio() returns early and never reaches here. So
// "no Audio object AND no pump task" is a sufficient test for "nobody is using
// the arena", whoever acquired it.
#ifdef SERIAL_DEBUG
// TASK-443: skip the arena acquire on the FILE path (`set aeNoArena 1`).
extern bool s_aeNoArenaInject;
// TASK-432 gate: force the guard to fail. The defect's natural trigger is a
// transient heap window (first play after a flash, before the ~150 s settle of
// TASK-425), which is exactly the kind of condition a regression test cannot
// schedule — "did not reproduce" would prove nothing. Set this and the degrade
// path runs deterministically. Debug builds only; `set aeFailAudio 0|1`.
extern bool s_aeFailAudioInject;
#endif

bool aeEnsureAudio();

// ── Audio pump task (TASK-278 / M-WR-AUDIO-TASK, Phase 1) ────────────────────
// Moves Audio::loop() (decode + HTTP stream fill) off loopTask onto a
// dedicated core-1, priority-2 task, so a slow paint can no longer starve the
// pump and a decode/refill spike can no longer stall touch sampling (E0
// decode-loaded baseline: 141 ms max-iteration spike, worst path app.tick —
// see docs/architecture/designs/M-WR-AUDIO-TASK.md). Phase 1 locking model:
// one non-recursive mutex guards every Audio method call.
//   - Control calls (connecttohost/stopSong/setVolume, from _play/_stopAudio/
//     wrVol): blocking take — correct, since there's nothing to pump until
//     the call returns [DEV-2-1].
//   - Per-tick reads (inBufferFilled/Free, isRunning): short timeout-take,
//     degrade to the last snapshot on miss — never block loopTask behind a
//     pump that may be inside an in-loop() reconnect/redirect/playlist
//     connect (Audio.cpp:2450-2452/3587/5255).
// Lifecycle: created lazily at first _play() (AFTER mb_arena_acquire() —
// the 8 KB task stack must not fragment the block the arena needs
// [DEV-2-3]); persists across _play() churn within a session; torn down in
// suspend() via an enforced ack-then-self-delete handshake [QM-2-1/DEV-2-6]
// before the Audio object + arena are released.

extern SemaphoreHandle_t s_wrAudioMutex;  // guards every Audio method call
extern SemaphoreHandle_t s_wrPumpAckSem;  // teardown handshake
extern TaskHandle_t      s_wrPumpTask;

// TASK-398 (M-WR-CONNECT-ASYNC): request/result-slot protocol that moves
// connecttohost() itself off loopTask. Single-word volatiles, same
// atomicity/no-mutex-needed precedent as s_wrPumpTask/s_wrPumpStopReq above —
// see the design doc's "residual race" analysis (WR_PUMP_PRIORITY above
// loopTask, both pinned to APP_CPU_NUM, no blocking call between a branch's
// read and its clear, so the window is zero-width by construction, not a
// race needing CAS). Used only when a connect is actually in flight — the
// s_wrPumpStopReq/ack-sem handshake above still owns every other teardown.
enum class WrPumpRequest : uint8_t { NONE, CONNECT, ABORT, TEARDOWN };
enum class WrPumpResult  : uint8_t { NONE, CONNECTED, FAILED, ABORTED, TORN_DOWN };

// TASK-410: which connecttoXXX() the CONNECT branch below dials. Same ordering
// argument as s_wrPumpConnectUrl — written by the poster (loopTask) strictly
// before the CONNECT post, read by the pump only after observing that post.
enum class WrConnectKind : uint8_t { URL, FILE };
extern volatile WrConnectKind s_wrPumpConnectKind;

extern volatile WrPumpRequest s_wrPumpRequest;  // written by loopTask, read/cleared by the pump task
extern volatile WrPumpResult  s_wrPumpResult;   // written by the pump task, read/cleared by tick()'s poll
// Connect target for a posted CONNECT request — written by _play() (loopTask)
// strictly before the s_wrPumpRequest post that hands it off, read by the
// pump's CONNECT branch only after observing that post; same ordering
// argument as the enums above, no separate mutex needed. Sized to match
// dataTask::WebRadioStation::url (dataTask.h).
// Lazy heap-allocated on first _play(), never freed — an embedded 104B
// static array overflows the debug build's .dram0.bss at link time, same
// "lazy malloc once, never freed" rule the project already uses elsewhere
// for large static buffers (project memory feedback_dram_bss_static_buffers;
// TeletextApp's _nosSource() is the precedent this mirrors).
static constexpr size_t WR_PUMP_CONNECT_URL_LEN = 104;
char* wrPumpConnectUrlBuf();

constexpr UBaseType_t WR_PUMP_STACK_WORDS      = (8 * 1024) / sizeof(StackType_t);
constexpr UBaseType_t WR_PUMP_PRIORITY         = 2;  // above loopTask (prio 1) — DMA deadline
constexpr TickType_t  WR_PUMP_CADENCE_TICKS    = pdMS_TO_TICKS(2);   // OQ1: tune on DUT
constexpr TickType_t  WR_PUMP_READ_TIMEOUT_TICKS = pdMS_TO_TICKS(50); // per-tick reads
// Teardown ack-wait bound. *** DUT-VERIFY (E3): must exceed the measured
// worst-case Audio::loop() hold (redirect/reconnect/playlist connect paths,
// DEV-2-1) — this starting value is a placeholder, not yet DUT-measured. ***
constexpr uint32_t WR_PUMP_ACK_TIMEOUT_MS = 10000;

// Pump observability (BP-036, VE-2-2) — single-producer (pump task) volatiles,
// read by dbgGet("wrPump") / "get stacks" on the loop task. Same accepted
// pattern as spotifyTask's volatile counters (no torn 32-bit reads on Xtensa).
extern volatile uint32_t s_wrPumpCycles;
extern volatile uint32_t s_wrPumpMaxPumpMs;
extern volatile uint32_t s_wrPumpMaxMutexWaitMs;

bool wrPumpAlive();

// ── TASK-352: Winamp volume-slider seam ───────────────────────────────────────
// webRadioVolumePct coalesced-save state (ADR-050 rule 3, lastStation idiom —
// mirrors _lastStationDirty/_lastStationSaved on WebRadioApp, kept as file
// statics here rather than instance members because the sink below is a free
// function: it is wired into WinampDisplay via a plain function pointer, no
// `this`, same reason s_wr_audio/s_wrAudioMutex above are file statics.
extern bool    s_wrVolPctDirty;
extern uint8_t s_wrVolPctSaved;

// winampDisplay's volume-drag seam target (setVolumeSink()). Applies the
// pct-scaled volume via the sanctioned short-timeout control-call idiom — a
// drag must never block the UI task behind a busy pump (skip the step; the
// debounced next commit lands it, same degrade-gracefully rule as every
// other per-tick pump touchpoint). No live session yet (DEV-2-4 precedent,
// same as the wrVol debug setter): clamp-store only, nothing to apply.
void wrVolumeSink(int pct);

size_t wrPumpStackSizeBytes();
size_t wrPumpStackHighWaterBytes();

// Idempotent — the pump persists across _play() churn within a session, so
// repeated calls after the first are no-ops. Call only AFTER mb_arena_acquire()
// [DEV-2-3].
void wrEnsurePumpTask();

// Enforced teardown sequence [QM-2-1/DEV-2-6]: signal stop, wait (bounded) for
// the pump's ack — given while it holds no locks — then reap the handle. A
// timed-out ack is a tripwire (LOG_E), not a hard block: best-effort teardown
// proceeds so the app never gets stuck unusable (matches this codebase's
// "never crash, degrade" philosophy elsewhere in WebRadio).
void wrTeardownPumpTask();

// ── TASK-410: local-file source ──────────────────────────────────────────────
// Minimal entry point — the engine bring-up subset of WebRadioApp::_play()
// (arena acquire, Audio construction, pump task, mutex-guarded volume set,
// post-CONNECT-and-poll) with none of WebRadio's station-list/WRPlayState
// machinery, since there is no LocalPlayer app yet (TASK-413+). The caller
// owns preconditions (SD mounted, path exists); connecttoFS() failing surfaces
// as WrPumpResult::FAILED exactly like a dead stream URL — same poll path.
// TASK-430: local-file play must not block loopTask behind tlsYield()'s
// 150 s ceiling — a PLEDIT row tap (and TASK-418's auto-advance) needs to
// start or fail visibly within ~2 s. tlsTryYield()'s budget leaves headroom
// inside that gate; on timeout the play fails cleanly (no arena/Audio/pump
// stood up, ref count already rolled back by tlsTryYield()) rather than
// stalling the shell. WebRadio's station path is a deliberate exception —
// left on the blocking tlsYield() (see TASK-430's write-up in tasks.md):
// its entry points (eject, station tap) are already understood as "this
// will take a moment", and TASK-406 already cost a real bug changing that
// path's timing assumptions.
constexpr uint32_t AE_CONNECT_FILE_TLS_TRYYIELD_MS = 1500;

bool aeConnectFile(const char* path);

// TASK-415: stop the FILE arm without tearing the engine down — the transport
// STOP button and "the user tapped another row" path. Deliberately the same
// shape as WebRadioApp::_stopAudio()'s non-CONNECTING branch (control call
// under the engine mutex, pump task left alive), because the two arms share
// one Audio object and one pump: a divergent stop here would be a second,
// subtly different teardown ordering for the same hardware.
//
// `connecting` is the caller's own "a CONNECT is still in flight" state — the
// engine does not track WRPlayState. In that case nothing is playing at the
// codec level yet, and taking the mutex would block loopTask for the connect's
// full remaining duration (TASK-398's freeze), so post ABORT and let the
// caller's result poll reconcile. TEARDOWN is never downgraded.
void aeStopFile(bool connecting);

// TASK-415: full release of the engine for the FILE arm — pump task, then the
// Audio object, then the arena, in that order (TASK-278's teardown ordering;
// the decoder buffers live IN the arena, so ~Audio must run while the arena is
// still valid). Mirrors WebRadioApp::suspend()'s teardown block for the same
// reason aeStopFile() mirrors _stopAudio(): one engine, one ordering.
//
// `connecting`: hand the teardown to the pump task instead of blocking
// loopTask on the in-flight connect (TASK-398).
void aeTeardownFile(bool connecting);
