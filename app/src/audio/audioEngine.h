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
// Single-TU inclusion model (Arduino/.ino-style — everything under app/src is
// textually included once from main.cpp), so every symbol below keeps its
// original name and internal (static) linkage exactly as it had in
// webRadioApp.h; callers elsewhere in the same TU are unaffected by the move.

#include <Arduino.h>
#include <Audio.h>
#include <SD.h>  // TASK-410: connecttoFS(SD, path) — AUDIO_NO_SD_FS dropped
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include "esp_task_wdt.h"
#include <esp_heap_caps.h> // T_MB_PROBE_00: caps-split for CP1/CP2 (TASK-261 Phase 0+2)
#include <new>             // TASK-432: std::nothrow — a bare `new Audio` reset the device
#ifdef MEMBUDGET_PHASE1
#include "mb_arena.h"  // Phase 2: arena HWM reporting at CP2
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
static inline uint8_t wrEffectiveVolume() {
    uint8_t hi = g_settings.webRadioHwMod ? WR_VOLUME_MAX : WR_VOLUME_SOFT_CAP_STOCK;
    return g_settings.webRadioMaxVolume > hi ? hi : g_settings.webRadioMaxVolume;
}

// TASK-352: the Winamp slider's session volume (webRadioVolumePct, 0-100)
// scales *within* the wrEffectiveVolume() ceiling — the ceiling stays the
// ceiling (TASK-209/T_WR_VOL_03 clamp semantics untouched), the slider is
// relative to it. +50 rounds instead of truncating.
static inline uint8_t wrScaledVolume() {
    return (uint8_t)(((uint32_t)g_settings.webRadioVolumePct * wrEffectiveVolume() + 50) / 100);
}

// ── ICY metadata queue ───────────────────────────────────────────────────────
// Written from ESP32-audioI2S callback — runs on the wrAudio pump task (core 1,
// prio 2, TASK-278/M-WR-AUDIO-TASK); read in tick() (loopTask, core 1, prio 1).
// Depth 1 + overwrite: old unread title is replaced by the newest one.

static QueueHandle_t s_icyTitleQueue = nullptr;

// Required by ESP32-audioI2S — weak-linked extern resolved by user code.
// Defined with external linkage; safe since audioEngine.h is included only from main.cpp.
void audio_showstreamtitle(const char *info) {
    if (!s_icyTitleQueue || !info) return;
    char buf[WR_ICY_TITLE_LEN];
    strlcpy(buf, info, sizeof(buf));
    xQueueOverwrite(s_icyTitleQueue, buf);
}

// T_MB_PROBE_00 CP2 (TASK-261 Phase 0): decoder-init capture point.
// audio_info is the ESP32-audioI2S broad info callback; fires on decoder init
// ("MP3Decoder ... initialized") — AFTER InBuff calloc + Helix alloc, so this
// is the moment both big allocations have landed and heap drop is measurable.
void audio_info(const char *info) {
    if (!info) return;
    // Surface all audio_info lines through LOG so they appear in the monitor.
    LOG_I("webradio", "audio_info: %s", info);
#if defined(MEMBUDGET_PHASE1) && defined(SERIAL_DEBUG)
    // CP2: emit caps-split on decoder-init line (the gate metric for Phase 1).
    if (strstr(info, "MP3Decoder") || strstr(info, "AACDecoder")) {
        Serial.printf("[membudget] CP2-decoder-init freeInt=%u lfbInt=%u freeDma=%u lfbDma=%u arenaHWM=%u\n",
            (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
            (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
            (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
            (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA),
            (unsigned)mb_arena_hwm());
    }
#endif
}

// TASK-410 / ADR-059 D12: loopTask's handle, captured once in setup() (this
// file has no g_loopTaskHandle of its own before TASK-410 — there was no
// callback that needed to prove which task it ran on). Everything that must
// only ever run on loopTask asserts against it, below.
static TaskHandle_t g_loopTaskHandle = nullptr;

// M-AUDIO-ENGINE-extraction.md §4: audio_eof_mp3 fires on the pump task, from
// inside Audio::loop(), WITH THE ENGINE MUTEX HELD. It may therefore only set
// a flag — opening the next track here would call connecttoFS() from the task
// already holding the mutex it needs: self-deadlock. Weak-linked by
// ESP32-audioI2S (Audio.h:77); resolved here now that AUDIO_NO_SD_FS is gone.
static volatile bool s_aeEofPending = false;

// TASK-410: separate from WebRadioApp's _spotifyYielded — aeConnectFile() has
// no app instance to hold it. DUT finding: without yielding Spotify's TLS
// session first, its held heap fragments enough that both the arena acquire
// and the pump task's stack alloc fail on a normal boot (reproduced: arena
// acquire FAIL->libc-fallback, xTaskCreatePinnedToCore rc=-1) — same
// ~50KB-contiguous need _play() already documents below. Resumed in
// aeDrainEof(), the natural "done playing" point for this single-file scope
// (TASK-413 gets a real stop/teardown path).
static bool s_aeSpotifyYielded = false;

void audio_eof_mp3(const char *info) {
    (void)info;
    s_aeEofPending = true;
}

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
static uint32_t s_aeEofCount = 0;
static inline uint32_t aeEofCount() { return s_aeEofCount; }

static void aeDrainEof() {
    configASSERT(xTaskGetCurrentTaskHandle() == g_loopTaskHandle);
    if (!s_aeEofPending) return;
    s_aeEofPending = false;
    s_aeEofCount++;
    LOG_I("audioengine", "eof drained on loopTask (no auto-advance wired yet)");
    if (s_aeSpotifyYielded) {
        spotifyTask::tlsResume();
        s_aeSpotifyYielded = false;
    }
}

// ── Audio singleton ──────────────────────────────────────────────────────────
// Internal DAC, GPIO26 (I2S_DAC_CHANNEL_LEFT_EN = SC8002B amp).
// Pointer used to defer construction until after I2S is ready.

static Audio* s_wr_audio = nullptr;

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
void audio_process_extern(int16_t* buff, uint16_t len, bool *continueI2S) {
    int32_t peakL = 0, peakR = 0;
    for (uint16_t i = 0; i < len; ++i) {
        int32_t l = buff[i * 2];
        int32_t r = buff[i * 2 + 1];
        if (l < 0) l = -l;
        if (r < 0) r = -r;
        if (l > peakL) peakL = l;
        if (r > peakR) peakR = r;
    }
    float targetL = peakL / 32768.0f;
    float targetR = peakR / 32768.0f;
    float &lLvl = vu::lLevelRef();
    float &rLvl = vu::rLevelRef();

    if (len > 0 && s_wr_audio) {
        const float fs = (float)s_wr_audio->getSampleRate();
        const float n  = (float)len;
        for (int b = 0; b < vu::SPEC_BAND_COUNT; ++b) {
            const float f = vu::SPEC_BAND_FREQ[b];
            const float k = 0.5f + (n * f / fs);
            const float w = 6.28318530718f * k / n; // 2*pi*k/n
            const float coeff = 2.0f * cosf(w);
            float s1 = 0.0f, s2 = 0.0f;
            for (uint16_t i = 0; i < len; ++i) {
                float mono = (buff[i * 2] + buff[i * 2 + 1]) * (0.5f / 32768.0f);
                float s0 = mono + coeff * s1 - s2;
                s2 = s1;
                s1 = s0;
            }
            float power = s1 * s1 + s2 * s2 - coeff * s1 * s2;
            if (power < 0.0f) power = 0.0f;
            float mag = (sqrtf(power) / n) * SPEC_BAND_GAIN[b];
            vu::updateSpectrumBar(b, mag);
        }
    }

    lLvl += (targetL - lLvl) * ((targetL > lLvl) ? vu::ATTACK : vu::RELEASE);
    rLvl += (targetR - rLvl) * ((targetR > rLvl) ? vu::ATTACK : vu::RELEASE);

    // TASK-388 (EXP-021/022, PROP-009): 19-column real trace, plain
    // sub-sampling of the L channel across this decoded block — replaces
    // the whole trace every call, single writer, same never-both-active
    // argument as X043/X044.
    if (len >= vu::SPEC_BARS) {
        int8_t *trace = vu::waveTraceRef();
        for (int i = 0; i < vu::SPEC_BARS; ++i) {
            uint16_t idx = (uint16_t)(((uint32_t)i * len) / vu::SPEC_BARS);
            trace[i] = (int8_t)(buff[idx * 2] >> 8);
        }
    }
    *continueI2S = true;
}

// EXP-012: trial 16K input ring (default 8K = 1600*5). Must run after new Audio()
// and before connecttohost() — InBuff is lazily allocated inside connecttohost's
// setDefaults()/initInBuff(), so this only sets the size, no realloc.
static inline void wrApplyInBufTrial(Audio* a) {
#ifdef WR_INBUF_16K
    a->setBufsize(16384, 0);
#else
    (void)a;
#endif
}

// TASK-392: raise connecttohost()'s TCP(+TLS) connect budget above the library's
// tight defaults — see WR_CONNECT_TIMEOUT_MS/_SSL above for the evidence.
static inline void wrApplyConnectTimeout(Audio* a) {
    a->setConnectionTimeout(WR_CONNECT_TIMEOUT_MS, WR_CONNECT_TIMEOUT_MS_SSL);
}

// TASK-432: the I2S DMA floor that must be clear before an Audio can be
// constructed. i2s_driver_install()'s DMA malloc failure is UNCHECKED in the
// vendored Audio ctor — it null-derefs (LoadProhibited, EXCVADDR 0x1c) and
// reboots. TASK-289 measured it failing at lfbDma 13.8 KB and succeeding at
// 30+ KB; 16 KB sits just above the known-bad point without rejecting plays
// that fragmentation alone would allow. Was a literal inside
// WebRadioApp::_play(); hoisted here so the FILE arm gets the same guard
// rather than a second copy that can drift.
static constexpr size_t AE_I2S_DMA_FLOOR_BYTES = 16 * 1024;

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
#ifdef SERIAL_DEBUG
// TASK-432 gate: force the guard to fail. The defect's natural trigger is a
// transient heap window (first play after a flash, before the ~150 s settle of
// TASK-425), which is exactly the kind of condition a regression test cannot
// schedule — "did not reproduce" would prove nothing. Set this and the degrade
// path runs deterministically. Debug builds only; `set aeFailAudio 0|1`.
static bool s_aeFailAudioInject = false;
#endif

static bool aeEnsureAudio() {
    if (s_wr_audio) return true;

#ifdef SERIAL_DEBUG
    if (s_aeFailAudioInject) {
        LOG_E("audioengine", "Audio alloc failure INJECTED (set aeFailAudio 1) — abort play");
        return false;
    }
#endif

    size_t lfbDma = heap_caps_get_largest_free_block(MALLOC_CAP_DMA);
    if (lfbDma < AE_I2S_DMA_FLOOR_BYTES) {
        LOG_E("audioengine", "DMA pool too low for I2S init: lfbDma=%u — abort play",
              (unsigned)lfbDma);
        return false;
    }

    // TASK-432: nothrow + check. Every other allocation on this path is
    // already checked (mb_arena_acquire() falls back to libc, the Helix
    // sub-allocations fail cleanly to "play FAILED"); this one was the lone
    // bare `new`.
    Audio* a = new (std::nothrow) Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);
    if (!a) {
        LOG_E("audioengine", "Audio alloc failed: lfbInt=%u freeInt=%u — abort play",
              (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
              (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        return false;
    }

    s_wr_audio = a;
    wrApplyInBufTrial(s_wr_audio);      // EXP-012: before connecttohost (InBuff not yet alloc'd)
    wrApplyConnectTimeout(s_wr_audio);  // TASK-392
    return true;
}

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

static SemaphoreHandle_t s_wrAudioMutex  = nullptr;  // guards every Audio method call
static SemaphoreHandle_t s_wrPumpAckSem  = nullptr;  // teardown handshake
static TaskHandle_t      s_wrPumpTask    = nullptr;
static volatile bool     s_wrPumpStopReq = false;

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
static volatile WrConnectKind s_wrPumpConnectKind = WrConnectKind::URL;

static volatile WrPumpRequest s_wrPumpRequest = WrPumpRequest::NONE;  // written by loopTask, read/cleared by the pump task
static volatile WrPumpResult  s_wrPumpResult  = WrPumpResult::NONE;   // written by the pump task, read/cleared by tick()'s poll
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
static char* s_wrPumpConnectUrl = nullptr;
static char* wrPumpConnectUrlBuf() {
    if (!s_wrPumpConnectUrl) s_wrPumpConnectUrl = new char[WR_PUMP_CONNECT_URL_LEN];
    return s_wrPumpConnectUrl;
}

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
static volatile uint32_t s_wrPumpCycles         = 0;
static volatile uint32_t s_wrPumpMaxPumpMs      = 0;
static volatile uint32_t s_wrPumpMaxMutexWaitMs = 0;

static bool wrPumpAlive() { return s_wrPumpTask != nullptr; }

// ── TASK-352: Winamp volume-slider seam ───────────────────────────────────────
// webRadioVolumePct coalesced-save state (ADR-050 rule 3, lastStation idiom —
// mirrors _lastStationDirty/_lastStationSaved on WebRadioApp, kept as file
// statics here rather than instance members because the sink below is a free
// function: it is wired into WinampDisplay via a plain function pointer, no
// `this`, same reason s_wr_audio/s_wrAudioMutex above are file statics.
static bool    s_wrVolPctDirty = false;
static uint8_t s_wrVolPctSaved = 100;

// winampDisplay's volume-drag seam target (setVolumeSink()). Applies the
// pct-scaled volume via the sanctioned short-timeout control-call idiom — a
// drag must never block the UI task behind a busy pump (skip the step; the
// debounced next commit lands it, same degrade-gracefully rule as every
// other per-tick pump touchpoint). No live session yet (DEV-2-4 precedent,
// same as the wrVol debug setter): clamp-store only, nothing to apply.
static void wrVolumeSink(int pct) {
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    g_settings.webRadioVolumePct = (uint8_t)pct;
    s_wrVolPctDirty = true;
    if (!s_wr_audio) return;
    if (xSemaphoreTake(s_wrAudioMutex, WR_PUMP_READ_TIMEOUT_TICKS) == pdTRUE) {
        s_wr_audio->setVolume(wrScaledVolume());
        xSemaphoreGive(s_wrAudioMutex);
    }
}

static size_t wrPumpStackSizeBytes() {
    return (size_t)WR_PUMP_STACK_WORDS * sizeof(StackType_t);
}
static size_t wrPumpStackHighWaterBytes() {
    return s_wrPumpTask
           ? (size_t)uxTaskGetStackHighWaterMark(s_wrPumpTask) * sizeof(StackType_t)
           : 0;
}

static void wrPumpTaskBody(void*) {
    LOG_I("wrpump", "created stack=%uB prio=%u core=%d",
          (unsigned)wrPumpStackSizeBytes(), (unsigned)WR_PUMP_PRIORITY, (int)APP_CPU_NUM);
    for (;;) {
        // Checked at the top of the cycle, holding no locks — the enforced
        // teardown sequence [QM-2-1/DEV-2-6]: ack, then immediately
        // self-delete. Never re-enters the mutex/Audio::loop() after acking.
        // Only fires for suspend()'s synchronous teardown path (nothing in
        // flight — see wrTeardownPumpTask()). TASK-398's CONNECTING-time
        // teardown goes through s_wrPumpRequest == TEARDOWN below instead,
        // since this stop-req path has no way to reconcile _state back on
        // loopTask (it's a free function — no `this`).
        if (s_wrPumpStopReq) {
            LOG_I("wrpump", "ack");
            xSemaphoreGive(s_wrPumpAckSem);
            LOG_I("wrpump", "deleted");
            vTaskDelete(NULL);
        }

        // TASK-398 (M-WR-CONNECT-ASYNC): request/result-slot protocol.
        // connecttohost() — the multi-second blocking call, OQ4/TASK-393 —
        // is fully isolated to this task here, never touching loopTask. Each
        // branch below REPLACES that cycle's normal pump servicing, it does
        // not run in addition to it.
        WrPumpRequest req = s_wrPumpRequest;
        if (req == WrPumpRequest::CONNECT) {
            // Commit point: clear now. Zero-width per the priority-preemption
            // argument above — loopTask (strictly lower priority) cannot
            // interleave with this read/clear pair, so anything posted
            // DURING the connect below is a genuinely later write, correctly
            // observed by the re-check after connecttohost() returns.
            s_wrPumpRequest = WrPumpRequest::NONE;

            xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
            unsigned long tConnect = millis();
            // TASK-410: FILE arm reads s_wrPumpConnectUrl as an SD path instead
            // of a stream URL — same buffer, same write-before-post ordering,
            // just a different connecttoXXX() call.
            bool connectOk = (s_wrPumpConnectKind == WrConnectKind::FILE)
                ? s_wr_audio->connecttoFS(SD, s_wrPumpConnectUrl)
                : s_wr_audio->connecttohost(s_wrPumpConnectUrl);
            perf::record("wr.connect", millis() - tConnect);

            WrPumpRequest after = s_wrPumpRequest;  // may have changed DURING the connect
            if (after == WrPumpRequest::TEARDOWN) {
                if (connectOk) s_wr_audio->stopSong();  // still under the mutex above
                delete s_wr_audio;
                s_wr_audio = nullptr;
                xSemaphoreGive(s_wrAudioMutex);
                mb_arena_release();
                s_wrPumpRequest = WrPumpRequest::NONE;
                s_wrPumpResult  = WrPumpResult::TORN_DOWN;
                LOG_I("wrpump", "torn down (post-connect)");
                s_wrPumpTask = nullptr;  // null last, right before self-delete —
                                          // wrEnsurePumpTask()'s guard must keep
                                          // seeing "pump still here" until now
                vTaskDelete(NULL);
            } else if (after == WrPumpRequest::ABORT) {
                if (connectOk) s_wr_audio->stopSong();
                xSemaphoreGive(s_wrAudioMutex);
                s_wrPumpRequest = WrPumpRequest::NONE;
                s_wrPumpResult  = WrPumpResult::ABORTED;
            } else {  // NONE — nothing else was requested while the connect was outstanding
                xSemaphoreGive(s_wrAudioMutex);
                s_wrPumpResult = connectOk ? WrPumpResult::CONNECTED : WrPumpResult::FAILED;
            }
        } else if (req == WrPumpRequest::ABORT) {
            // Arrived before any connect started this cycle (the pump's own
            // vTaskDelay below, not a sub-instruction race) — nothing to
            // stop, no mutex needed.
            s_wrPumpRequest = WrPumpRequest::NONE;
            s_wrPumpResult  = WrPumpResult::ABORTED;
        } else if (req == WrPumpRequest::TEARDOWN) {
            // Same early-arrival case, stronger intent — mirrors the
            // post-connect TEARDOWN branch's terminal sequence exactly, just
            // skipping stopSong() (nothing was ever dispatched this cycle).
            // The delete itself still takes the mutex, unlike an earlier
            // version of this branch: whichever caller posted TEARDOWN did
            // so via suspend(), which only runs while WebRadio is the
            // current app — but dbgSet's wrVol (like every other app's
            // debug setters) reaches s_wr_audio regardless of currentAppId,
            // including while WebRadio is suspended, and does its own
            // null-check-then-separate-take outside any single critical
            // section. Without the mutex here, a same-window `set wrVol`
            // could pass wrVol's `!s_wr_audio` check and then dereference a
            // pointer this branch is concurrently freeing.
            s_wrPumpRequest = WrPumpRequest::NONE;
            xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
            delete s_wr_audio;
            s_wr_audio = nullptr;
            xSemaphoreGive(s_wrAudioMutex);
            mb_arena_release();
            s_wrPumpResult = WrPumpResult::TORN_DOWN;
            LOG_I("wrpump", "torn down (early-arrival)");
            s_wrPumpTask = nullptr;
            vTaskDelete(NULL);
        } else {
            // NONE — genuinely nothing requested: today's existing
            // steady-state servicing, unconditionally.
            uint32_t tWait = millis();
            xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
            uint32_t waitMs = millis() - tWait;
            if (waitMs > s_wrPumpMaxMutexWaitMs) s_wrPumpMaxMutexWaitMs = waitMs;

            uint32_t tPump = millis();
            if (s_wr_audio) s_wr_audio->loop();  // no-ops fast internally when !m_f_running
            uint32_t pumpMs = millis() - tPump;
            if (pumpMs > s_wrPumpMaxPumpMs) s_wrPumpMaxPumpMs = pumpMs;
#ifdef SERIAL_DEBUG
            // OQ3: cross-task perf-slot write (non-atomic registration race vs
            // perf::reset()) — accepted as diagnostic-grade noise, SERIAL_DEBUG-only.
            perf::record("wr.pump", pumpMs);
#endif
            xSemaphoreGive(s_wrAudioMutex);
        }

        s_wrPumpCycles++;
        vTaskDelay(WR_PUMP_CADENCE_TICKS);
    }
}

// Idempotent — the pump persists across _play() churn within a session, so
// repeated calls after the first are no-ops. Call only AFTER mb_arena_acquire()
// [DEV-2-3].
static void wrEnsurePumpTask() {
    // TASK-410: created here, not left to WebRadioApp::init() — a second
    // caller (aeConnectFile(), no WebRadioApp involved) must be able to bring
    // the engine up standalone. WebRadioApp's own init() still does the same
    // idempotent check; the null-guard makes creating it twice harmless.
    if (!s_wrAudioMutex) s_wrAudioMutex = xSemaphoreCreateMutex();
    if (!s_wrPumpAckSem) s_wrPumpAckSem = xSemaphoreCreateBinary();
    if (s_wrPumpTask) return;
    s_wrPumpStopReq         = false;
    s_wrPumpCycles          = 0;
    s_wrPumpMaxPumpMs       = 0;
    s_wrPumpMaxMutexWaitMs  = 0;
    BaseType_t rc = xTaskCreatePinnedToCore(
        &wrPumpTaskBody, "wrAudio", WR_PUMP_STACK_WORDS,
        nullptr, WR_PUMP_PRIORITY, &s_wrPumpTask, APP_CPU_NUM);
    if (rc != pdPASS) {
        LOG_E("wrpump", "xTaskCreatePinnedToCore failed rc=%d", (int)rc);
        s_wrPumpTask = nullptr;
    }
}

// Enforced teardown sequence [QM-2-1/DEV-2-6]: signal stop, wait (bounded) for
// the pump's ack — given while it holds no locks — then reap the handle. A
// timed-out ack is a tripwire (LOG_E), not a hard block: best-effort teardown
// proceeds so the app never gets stuck unusable (matches this codebase's
// "never crash, degrade" philosophy elsewhere in WebRadio).
static void wrTeardownPumpTask() {
    if (!s_wrPumpTask) return;
    s_wrPumpStopReq = true;
    if (xSemaphoreTake(s_wrPumpAckSem, pdMS_TO_TICKS(WR_PUMP_ACK_TIMEOUT_MS)) != pdTRUE) {
        LOG_E("wrpump", "teardown ack timeout after %ums — pump may be stuck in Audio::loop()",
              (unsigned)WR_PUMP_ACK_TIMEOUT_MS);
    }
    s_wrPumpTask = nullptr;
}

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

static bool aeConnectFile(const char* path) {
    if (!path || !*path) return false;
    if (!s_aeSpotifyYielded) {
        if (!spotifyTask::tlsTryYield(AE_CONNECT_FILE_TLS_TRYYIELD_MS)) {
            LOG_W("audioengine", "aeConnectFile: tls try-yield timed out after %ums — play FAILED, not blocking",
                  (unsigned)AE_CONNECT_FILE_TLS_TRYYIELD_MS);
            return false;
        }
        s_aeSpotifyYielded = true;
    }
#ifdef MEMBUDGET_PHASE1
    mb_arena_acquire();  // idempotent; on FAIL -> libc fallback, same as _play()
#endif
    // TASK-432: was a bare `new Audio(...)`. On the first `set plPlay` after a
    // flash — before the heap settles (TASK-425: lfb8 is not stable until
    // ~150 s post-reset) — that allocation failed, threw bad_alloc through a
    // path with no handler, and reset the device. Now it degrades to the same
    // `play FAILED` the caller already renders for a dead path.
    if (!aeEnsureAudio()) {
        // Roll back what THIS call took. The pump task was not created and no
        // Audio exists, so the TLS yield is the only thing outstanding.
        //
        // The arena is deliberately NOT released here: mb_arena_acquire() is
        // not ref-counted, so a release would yank the arena out from under a
        // live WebRadio session that acquired it first (our acquire above
        // would have been a no-op in that case). This mirrors WebRadio's own
        // DMA-floor abort, which also leaves it held; aeTeardownFile() on
        // mode exit is what releases it.
        if (s_aeSpotifyYielded) {
            spotifyTask::tlsResume();
            s_aeSpotifyYielded = false;
        }
        return false;
    }
    wrEnsurePumpTask();  // idempotent; must run AFTER mb_arena_acquire() [DEV-2-3]

    xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
    s_wr_audio->setVolume(wrScaledVolume());
    xSemaphoreGive(s_wrAudioMutex);

    strlcpy(wrPumpConnectUrlBuf(), path, WR_PUMP_CONNECT_URL_LEN);
    s_wrPumpConnectKind = WrConnectKind::FILE;
    s_wrPumpRequest = WrPumpRequest::CONNECT;
    return true;
}

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
static void aeStopFile(bool connecting) {
    if (connecting) {
        if (wrPumpAlive() && s_wrPumpRequest != WrPumpRequest::TEARDOWN)
            s_wrPumpRequest = WrPumpRequest::ABORT;
        return;
    }
    if (s_wr_audio) {
        xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
        s_wr_audio->stopSong();
        xSemaphoreGive(s_wrAudioMutex);
    }
    if (s_aeSpotifyYielded) {
        spotifyTask::tlsResume();
        s_aeSpotifyYielded = false;
    }
}

// TASK-415: full release of the engine for the FILE arm — pump task, then the
// Audio object, then the arena, in that order (TASK-278's teardown ordering;
// the decoder buffers live IN the arena, so ~Audio must run while the arena is
// still valid). Mirrors WebRadioApp::suspend()'s teardown block for the same
// reason aeStopFile() mirrors _stopAudio(): one engine, one ordering.
//
// `connecting`: hand the teardown to the pump task instead of blocking
// loopTask on the in-flight connect (TASK-398).
static void aeTeardownFile(bool connecting) {
    aeStopFile(connecting);
    if (connecting) {
        if (wrPumpAlive()) s_wrPumpRequest = WrPumpRequest::TEARDOWN;
        return;
    }
#ifdef MEMBUDGET_PHASE1
    wrTeardownPumpTask();
    if (s_wr_audio) { delete s_wr_audio; s_wr_audio = nullptr; }
    mb_arena_release();
#endif
}
