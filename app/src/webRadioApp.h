#pragma once
// webRadioApp.h — International Web Radio app (M-WEBRADIO).
// Streams MP3 from radio-browser.info via ESP32-audioI2S on internal DAC GPIO26.
// Entered via Winamp eject button; exits back to Spotify via the same button.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <Audio.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include "esp_task_wdt.h"
#include <esp_heap_caps.h> // T_MB_PROBE_00: caps-split for CP1/CP2 (TASK-261 Phase 0+2)
#ifdef MEMBUDGET_PHASE1
#include "mb_arena.h"  // Phase 2: arena HWM reporting at CP2
#endif
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "gen/skin_layout.h"
#include "logSink.h"
#include "perf.h"
#include "spotifyTask.h"
#include "touch/scrollTuning.h"   // TASK-277: shared gesture tuning with winampDisplay
#include "winamp/winampDisplay.h"

extern TFT_eSPI         tft;
extern WinampDisplay    winampDisplay;

// ── Play state ───────────────────────────────────────────────────────────────

enum class WRPlayState : uint8_t {
    STOPPED           = 0,
    CONNECTING        = 1,
    PLAYING           = 2,
    ERROR_WIFI        = 3,
    ERROR_STALL       = 4,
    ERROR_UNREACHABLE = 5,
    ERROR_BLOCKED     = 6,  // HTTP 403/451 — geo-blocked or DMCA-blocked station
};

// TASK-218: a stream that ends/drops mid-playback otherwise leaves _state stuck
// at PLAYING with Spotify's TLS held yielded forever. isRunning() can blip false
// during a transient underrun, so we require it to stay false this long before
// declaring the stream dead and resuming Spotify TLS. Conservative (favours a
// few seconds of silence over a false-positive kill of healthy playback).
// *** DUT-VERIFY: isRunning() transient semantics during normal underrun are
// unconfirmed on hardware — tune this against real behaviour (TASK-218). ***
// TASK-291: isRunning() alone is not sufficient — a peer that FIN-closes the
// socket (station server restart/reload) leaves ESP32-audioI2S's m_f_running
// stuck true indefinitely, so the isRunning()-based check above never arms.
// DUT-confirmed (2026-07-08, local FIN-close repro): the input buffer does NOT
// drain to empty in this state — the lib treats it as "slow stream" and pauses
// decode, so inBufferFilled() freezes at whatever level it held at the moment
// of the close (observed frozen at a nonzero %, not 0) and never changes again.
// The liveness signal is therefore "no bytes consumed" (an unchanged fill level),
// not "empty" — on a healthy stream inBufferFilled() is continuously read down
// and refilled at a byte-level cadence, so an exact-same reading for a full
// WR_STREAM_DEAD_MS window doesn't happen by chance. Reuses the same debounce
// window as the isRunning() check.
static constexpr uint32_t WR_STREAM_DEAD_MS = 5000;

// TASK-234 (ADR-045): a station that holds PLAYING this long is "settled" — past
// the decode-alloc-failure window (WR_STREAM_DEAD_MS) by a comfortable margin — so
// the auto-skip scan counter resets and a *later* death starts a fresh hunt rather
// than counting against the original scan's bound.
static constexpr uint32_t WR_SETTLED_MS = 12000;
static constexpr uint32_t WR_SKIP_PACE_MS = 2000;  // TASK-273: min gap between auto retry/skip attempts
static constexpr uint32_t WR_TERMINAL_RETRY_MS = 30000;  // TASK-276: backoff before re-arming a parked scan

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

// ── ICY metadata queue ───────────────────────────────────────────────────────
// Written from ESP32-audioI2S callback — runs on the wrAudio pump task (core 1,
// prio 2, TASK-278/M-WR-AUDIO-TASK); read in tick() (loopTask, core 1, prio 1).
// Depth 1 + overwrite: old unread title is replaced by the newest one.

static QueueHandle_t s_icyTitleQueue = nullptr;

// Required by ESP32-audioI2S — weak-linked extern resolved by user code.
// Defined with external linkage; safe since webRadioApp.h is included only from main.cpp.
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

// ── Audio singleton ──────────────────────────────────────────────────────────
// Internal DAC, GPIO26 (I2S_DAC_CHANNEL_LEFT_EN = SC8002B amp).
// Pointer used to defer construction until after I2S is ready.

static Audio* s_wr_audio = nullptr;

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

static Audio& wrAudio() {
    if (!s_wr_audio) {
        s_wr_audio = new Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);
        wrApplyInBufTrial(s_wr_audio);
    }
    return *s_wr_audio;
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
        if (s_wrPumpStopReq) {
            LOG_I("wrpump", "ack");
            xSemaphoreGive(s_wrPumpAckSem);
            LOG_I("wrpump", "deleted");
            vTaskDelete(NULL);
        }

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

        s_wrPumpCycles++;
        vTaskDelay(WR_PUMP_CADENCE_TICKS);
    }
}

// Idempotent — the pump persists across _play() churn within a session, so
// repeated calls after the first are no-ops. Call only AFTER mb_arena_acquire()
// [DEV-2-3].
static void wrEnsurePumpTask() {
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

// ── Display constants (mirrors preview_webradio.py zone map) ─────────────────

// TASK-254: the ICY StreamTitle is now folded into the title marquee (no separate
// line), so the old WR_ICY_X/Y/W/H zone constants were removed.

// Country badge (top-right, over the bitrate-legend area):
static constexpr int WR_BADGE_X = 241;
static constexpr int WR_BADGE_Y = 10;
static constexpr int WR_BADGE_W = 32;
static constexpr int WR_BADGE_H = 13;

// ── WebRadioApp ──────────────────────────────────────────────────────────────

class WebRadioApp : public App {
public:

    // ── Lifecycle ──────────────────────────────────────────────────────────

    void init() override {
        _state           = WRPlayState::STOPPED;
        _stationCount    = 0;
        _currentIdx      = g_settings.webRadioLastStation;
        _scrollOffset    = 0;
        _pendingStations = false;
        // ADR-050 rule 3 (M-WEBRADIO-SETTINGS): lastStation-at-load baseline for
        // the coalesced suspend()-save — no flash write when nothing changed.
        _lastStationSaved = g_settings.webRadioLastStation;
        _lastStationDirty = false;
        _dirty           = true;
        _icyTitle[0]     = '\0';
        _bufPct          = 0;
        _lastHeapLogMs   = 0;

        if (!s_icyTitleQueue)
            s_icyTitleQueue = xQueueCreate(1, sizeof(char) * WR_ICY_TITLE_LEN);
        // TASK-278: created once, ever — reused across every suspend()/_play()
        // cycle for the lifetime of the app (init() runs only on first entry).
        if (!s_wrAudioMutex) s_wrAudioMutex = xSemaphoreCreateMutex();
        if (!s_wrPumpAckSem) s_wrPumpAckSem = xSemaphoreCreateBinary();

        // Defer Audio creation to _play() — Audio(internalDAC) constructor
        // runs i2s_driver_install which can exceed 5s and trigger WDT when
        // init() is called synchronously from cmdTap (serial context).
        if (s_wr_audio) {  // TASK-209: HW-mod clamp — defensive; s_wr_audio is
                           // always null on first init() (see comment above)
            xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
            s_wr_audio->setVolume(wrEffectiveVolume());
            xSemaphoreGive(s_wrAudioMutex);
        }

        // TASK-208: heap watermark — app launch baseline
        _heapInitFree = ESP.getFreeHeap();
        _heapInitMin  = ESP.getMinFreeHeap();
        LOG_I("webradio", "HEAP init free=%u min=%u",
              (unsigned)_heapInitFree, (unsigned)_heapInitMin);

        // Kick off station list fetch
        LOG_I("webradio", "HEAP pre-fetch free=%u min=%u",
              (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap());
        _enqueueStationFetch();

        // _dirty=true; tick() handles first paint — init() must return fast
        // (called synchronously from cmdTap context; _drawFull here risks WDT).
    }

    void resume() override {
        _dirty = true;
        // Defer paint to tick() — resume() can also run from cmdTap context.

        // M-WEBRADIO-SETTINGS D3: pull-on-resume config diff (StockApp
        // ticker-diff precedent). A Settings edit of country or bitrate cap
        // voids the station-list identity: abort any in-flight fetch (WR-1 —
        // its result may still park; tick()'s identity check discards it),
        // stop the stream defensively (WR-7: every real app-switch path runs
        // suspend() -> _stopAudio() first, so this is belt-and-braces), clear
        // the list/indices and refetch. The WR-2 lastStation reset already
        // happened at edit time in appsSection (rides the section's save);
        // this branch is also the safety net for serial `set` edits. Autoplay
        // below cannot fire across the change: _stationCount is 0 until the
        // fresh list lands, and by then the check has passed.
        if (_cfgCountry[0] != '\0' &&
            (strcmp(_cfgCountry, g_settings.webRadioCountry) != 0 ||
             _cfgCap != g_settings.webRadioBitrateCap)) {
            LOG_I("webradio", "config changed %s/%u -> %s/%u — refetching stations",
                  _cfgCountry, (unsigned)_cfgCap,
                  g_settings.webRadioCountry,
                  (unsigned)g_settings.webRadioBitrateCap);
            if (_pendingStations) dataTask::abortWebRadioFetch();
            if (_state != WRPlayState::STOPPED) _stopAudio();
            _currentIdx   = 0;
            _stationCount = 0;
            _scrollOffset = 0;
            // The WR-2 edit-time reset already persisted lastStation=0 (UI
            // path) — refresh the suspend()-save baseline so the coalesced
            // save doesn't redundantly rewrite an unchanged value.
            _lastStationSaved = g_settings.webRadioLastStation;
            _lastStationDirty = false;
            _enqueueStationFetch();
        }

        // TASK-289: second-chance station fetch. The list was fetched exactly
        // once (init(), first entry); if that fetch failed — network blip,
        // TASK-284 mirror truncation, or the -101 heap guard tripping while a
        // debug wrUrl playback held the heap — the session showed "No stations"
        // forever. Re-enqueue on re-entry: the heap is quiet here (suspend()
        // freed the audio stack), and _stationCount==0 means the autoplay below
        // can't fire, so this cannot recreate the fetch/playback race the
        // guard exists for.
        if (_stationCount == 0 && !_pendingStations) {
            _enqueueStationFetch();
        }

        if (g_settings.webRadioAutoplay && _stationCount > 0 &&
            _state == WRPlayState::STOPPED) {
            _play(_currentIdx);
        }
    }

    void suspend() override {
        // TASK-277 [DEV-1-4]: cancel any live gesture (precedent:
        // SpotifyApp::suspend() → resetDragState()) — serial switchApp /
        // set wrEject can fire mid-gesture.
        _wrs            = WRS_IDLE;
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;
        _pleditDirty    = false;

        _stopAudio();
#ifdef MEMBUDGET_PHASE1
        // TASK-278: tear down the pump task BEFORE the Audio object — the
        // enforced ack-then-self-delete handshake guarantees the pump is gone
        // (or the timeout tripwire has fired) before anything below touches
        // s_wr_audio again.
        wrTeardownPumpTask();
        // TASK-267: release the JIT arena when leaving WebRadio so the next entry's
        // station fetch has full heap. Destroy the Audio object FIRST — its decoder
        // buffers live in the arena, so they must be freed (via ~Audio → mb_arena_free,
        // while the arena is still valid) before we free the backing block. Safe even
        // if ~Audio doesn't free them: release frees the whole block and nothing
        // references the arena afterwards (Audio is gone; a fresh one is built on
        // re-entry). Gated to MEMBUDGET_PHASE1 so production behaviour is unchanged.
        if (s_wr_audio) { delete s_wr_audio; s_wr_audio = nullptr; }
        mb_arena_release();
#endif

        // ADR-050 rule 3 (M-WEBRADIO-SETTINGS D3): coalesced lastStation
        // persistence — _play() writes g_settings in RAM and marks dirty;
        // one SettingsStorage::save() here per session iff the value actually
        // changed since load. Auto-skip churn costs zero flash writes, and
        // eject also funnels through suspend() so it is covered.
        if (_lastStationDirty) {
            if (g_settings.webRadioLastStation != _lastStationSaved) {
                SettingsStorage::save();
                _lastStationSaved = g_settings.webRadioLastStation;
            }
            _lastStationDirty = false;
        }
    }

    void tick() override {
        // TASK-252: scroll the LED-font title marquee (long station names).
        winampDisplay.tickMarquee();

        // TASK-277: velocity-scroll integrator — placed here, BEFORE the
        // terminal-retry / pending-action dispatch below, so those blocks'
        // early returns cannot stall a live gesture [DEV-1-3]. dt-integrated
        // (M-LIST-v4 OQ1): robust to variable loop cadence.
        {
            const unsigned long now = millis();
            const float dt = (_lastScrollMs == 0) ? 0.0f
                                                  : (now - _lastScrollMs) * 0.001f;
            _lastScrollMs = now;
            _tickScroll(dt);
        }
        // Scroll steps repaint the row region only — not a _dirty full repaint
        // (§Gesture spec). A pending full repaint covers it anyway.
        if (_pleditDirty) {
            _pleditDirty = false;
            if (!_dirty) _drawPledit();
        }

        // TASK-234 (ADR-045): process a deferred retry / auto-skip from a prior
        // tick's playback failure. Done here (not inline at the failure site) so
        // the connecttohost() blocking call never recurses — one attempt per tick.
        // TASK-273: paced, not every tick. An instant connect-fail (network blip:
        // EHOSTUNREACH/DNS-fail during a WiFi doze/reassoc window) used to burn the
        // ENTIRE station list into terminal ERROR in <1 s — 16 attempts in one blip.
        // ≥2 s between attempts lets a full-list walk (~32 s) outlive short outages
        // and land on a live station once the network returns.
        // TASK-276: retry-from-terminal. When the auto-skip scan exhausts the list
        // during a network outage, the player used to park in ERROR_* until the
        // user re-played — observed live 2026-07-02 (two ~30 s parks during a
        // link-flap storm, operator had to tap PREV to recover). While the app is
        // active, auto-skip is ON, and we're parked in a retryable error, re-arm a
        // fresh paced scan every WR_TERMINAL_RETRY_MS. ERROR_BLOCKED is excluded
        // (station-specific 403/451 — retrying won't change a geo-block).
        if (g_settings.webRadioAutoSkip && _pendingAction == ACT_NONE &&
            (_state == WRPlayState::ERROR_WIFI ||
             _state == WRPlayState::ERROR_STALL ||
             _state == WRPlayState::ERROR_UNREACHABLE) &&
            _stationCount > 0 &&
            (uint32_t)(millis() - _lastAttemptMs) >= WR_TERMINAL_RETRY_MS) {
            LOG_I("webradio", "terminal retry — re-arming scan idx=%u", _currentIdx);
            _autoSkipTried = 0;
            _stallRetries  = 0;
            _play(_currentIdx, /*userInitiated=*/false);
            return;
        }

        if (_pendingAction != ACT_NONE &&
            (uint32_t)(millis() - _lastAttemptMs) >= WR_SKIP_PACE_MS) {
            uint8_t act = _pendingAction;
            _pendingAction = ACT_NONE;
            if (act == ACT_RETRY_SAME) {
                _play(_currentIdx, /*userInitiated=*/false);
            } else {  // ACT_SKIP_NEXT
                _stallRetries = 0;  // fresh station gets its own retry budget
                uint8_t n = (_currentIdx + 1 >= _stationCount) ? 0 : _currentIdx + 1;
                _play(n, /*userInitiated=*/false);
            }
            return;  // let the next tick handle the outcome / paint
        }

        // Poll ICY metadata from audio callback queue
        {
            char buf[WR_ICY_TITLE_LEN];
            if (s_icyTitleQueue && xQueueReceive(s_icyTitleQueue, buf, 0) == pdTRUE) {
                strlcpy(_icyTitle, buf, sizeof(_icyTitle));
                _drawTitleZone();  // TASK-254: ICY now folds into the title marquee
                LOG_D("webradio", "ICY: %s", _icyTitle);
            }
        }

        // Poll station list from dataTask
        if (_pendingStations) {
            dataTask::WebRadioStationsResult result;
            if (dataTask::pollWebRadioStations(&result)) {
                // WR-1 (M-WEBRADIO-SETTINGS D3): result identity. A stale
                // in-flight/parked fetch from before a config change can pop
                // AFTER resume()'s diff cleared the list and re-enqueued —
                // the TASK-300 parked-result class. Compare BOTH request-param
                // echoes against the snapshot latched at enqueue; on mismatch
                // discard and keep polling for the current request's result
                // (_pendingStations stays true — do NOT install, do NOT set
                // _stationCount).
                if (strcmp(result.countryCode, _cfgCountry) != 0 ||
                    result.bitrateCap != _cfgCap) {
                    LOG_W("webradio",
                          "stale station result discarded (%s/%u, want %s/%u)",
                          result.countryCode, (unsigned)result.bitrateCap,
                          _cfgCountry, (unsigned)_cfgCap);
                    return;
                }
                _pendingStations = false;
                // TASK-208: heap watermark — post-fetch (TLS torn down)
                _heapFetchFree = ESP.getFreeHeap();
                _heapFetchMin  = ESP.getMinFreeHeap();
                LOG_I("webradio", "HEAP post-fetch free=%u min=%u",
                      (unsigned)_heapFetchFree, (unsigned)_heapFetchMin);
                if (_deferredInject) {
                    // TASK-289: a wrUrl inject is waiting on this result. The
                    // injected station (slot 0) must survive, so drop the
                    // payload regardless of outcome (usually -102/aborted
                    // anyway) and start the deferred playback now that the
                    // fetch's TLS is torn down and the heap is ours. The
                    // _last* observability fields are still recorded below.
                    _deferredInject = false;
                    LOG_I("webradio", "deferred wrUrl play (fetch resolved http=%d)",
                          result.lastHttpCode);
                    _play(0);
                } else if (result.ok && result.count > 0) {
                    _stationCount = result.count;
                    memcpy(_stations, result.stations,
                           result.count * sizeof(dataTask::WebRadioStation));
                    if (_currentIdx >= _stationCount) _currentIdx = 0;
                    LOG_I("webradio", "stations loaded count=%u country=%s",
                          _stationCount, result.countryCode);
                } else {
                    LOG_W("webradio", "station fetch failed ok=%d http=%d jsonErr=%s",
                          result.ok, result.lastHttpCode, result.jsonErr);
                }
                // Record regardless of outcome — T_WR_TLS_01 needs the http code,
                // ok flag and TLS path on both success and failure (a successful
                // fetch still has to confirm http=200 and which path fired). result
                // carries the right values for both outcomes (ok=true/jsonErr=""
                // on success), so the accessor stays consistent either way.
                _lastOk          = result.ok;
                _lastHttpCode    = result.lastHttpCode;
                _lastTlsInsecure = result.tlsInsecure;
                strlcpy(_lastJsonErr, result.jsonErr, sizeof(_lastJsonErr));
                _dirty = true;
            }
        }

        // TASK-278: Audio::loop() now runs on the dedicated wrAudio pump task
        // (core 1, prio 2) — no longer pumped from tick(). loopTask's only
        // remaining touch is the timeout-take snapshot read below.

        if (_state == WRPlayState::PLAYING) {
            uint32_t now = millis();

            // TASK-208: periodic heap watermark every 30 s during playback
            if (now - _lastHeapLogMs >= 30000u) {
                _lastHeapLogMs = now;
                LOG_I("webradio", "HEAP play free=%u min=%u",
                      (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap());
            }

            if (s_wr_audio) {
                // TASK-278: per-tick read, short timeout-take — degrades to the
                // last snapshot on a miss (pump may be inside an in-loop()
                // reconnect/redirect/playlist connect) rather than blocking
                // loopTask [DEV-2-1].
                _refreshAudioSnapshot();

                // TASK-220/253: drive the POSBAR buffer bar from real buffer occupancy.
                // drawBufferBar() is a cheap targeted blit (groove + thumb), NOT a full
                // chrome repaint, so update it directly on small moves for a smooth thumb
                // (was a 15-pt hysteresis → _dirty full repaint, which made the thumb jump
                // ~33 px at a time). A tiny 2-pt threshold just skips no-op repaints.
                uint32_t filled = _snapFilled;
                uint32_t freeB  = _snapFreeB;
                uint32_t total  = filled + freeB;
                _bufPct = total ? (uint8_t)((uint32_t)filled * 100u / total) : 0;
#ifdef MEMBUDGET_PHASE1
                // TASK-263: objective halved-DMA underrun metric — edge-count input
                // buffer empties + track low-water while PLAYING.
                if (_state == WRPlayState::PLAYING) {
                    if (_bufPct < _minBufPct) _minBufPct = _bufPct;
                    bool empty = (filled == 0);
                    if (empty && !_wasEmpty) {
                        _underrunCount++;
                        _lastUnderrunMs = now;
                        // TASK-266: the connect-time buffer-fill transient (isPlayable()
                        // gates stream start on a single m_maxBlockSize, so the input
                        // buffer runs dry again almost immediately at T<5s, before the
                        // network catches up) reads as underruns=1 every session — not a
                        // real playback gap. _settled only latches true after the station
                        // has survived WR_SETTLED_MS, which is well past that window, so
                        // gating on it here gives the "recurrent underruns" signal the
                        // task asked for: ==0 once the connect transient is excluded.
                        if (_settled) _recurrentUnderrunCount++;
                    }
                    _wasEmpty = empty;
                }
#endif
                int delta = (int)_bufPct - (int)_bufPctDrawn;
                if (delta < 0) delta = -delta;
                if (delta >= 2) {
                    _bufPctDrawn = _bufPct;
                    _drawPosbar();   // targeted POSBAR blit only — no full repaint
                }

                // TASK-218 (guarded): a stream that ends or drops mid-playback
                // otherwise leaves _state at PLAYING with Spotify TLS held yielded
                // forever (silent Spotify starvation). Debounced: isRunning() must
                // stay false for WR_STREAM_DEAD_MS before we act, so a transient
                // underrun doesn't kill healthy playback. _lastRunningMs is seeded
                // at PLAYING entry, so the initial buffer fill sits inside the grace
                // window. *** isRunning() transient semantics unverified on DUT. ***
                if (_snapRunning) {
                    _lastRunningMs = now;
                    // TASK-234: once a station has held long enough to be past the
                    // decode-failure window, reset the auto-skip scan so a later
                    // death starts a fresh hunt instead of hitting the old bound.
                    if (!_settled && now - _playingSinceMs >= WR_SETTLED_MS) {
                        _settled       = true;
                        _autoSkipTried = 0;
                        _stallRetries  = 0;
                    }
                }
                // TASK-291: independent liveness signal, tracked regardless of
                // _snapRunning — a FIN-closed peer leaves isRunning() stuck true
                // forever, AND (DUT-confirmed) inBufferFilled() does not drain to
                // empty either — it freezes at whatever level it held at the FIN,
                // because the lib pauses decode ("slow stream") instead of
                // draining. So "no bytes consumed" (an unchanged reading), not
                // "empty", is the signal. Same debounce window/grace-seeding as
                // the isRunning() check above.
                if (filled != _lastSeenFilled) {
                    _lastSeenFilled  = filled;
                    _lastBufChangeMs = now;
                }

                bool deadByRunning = !_snapRunning && (now - _lastRunningMs   >= WR_STREAM_DEAD_MS);
                bool deadByStall   =                   now - _lastBufChangeMs >= WR_STREAM_DEAD_MS;
                if (deadByRunning || deadByStall) {
                    LOG_W("webradio",
                          "stream dead (isRunning=%d for %lums, bufStalled for %lums) — "
                          "stop + resume Spotify TLS",
                          (int)_snapRunning, (unsigned long)(now - _lastRunningMs),
                          (unsigned long)(now - _lastBufChangeMs));
                    _stopAudio();                       // resumes the yielded Spotify TLS
                    _state = WRPlayState::ERROR_STALL;  // _stopAudio() set STOPPED; show stall
                    _dirty = true;
                    _onPlaybackFailed(/*connectFail=*/false);  // TASK-234: retry / auto-skip
                }
            }
        }

        if (_dirty) {
            // WDT: _drawFull (repaintChrome) can be slow; reset before painting.
            esp_task_wdt_reset();
            _drawFull();
            _dirty = false;
        }
    }

    bool hasPendingAsync() const override { return _pendingStations; }

    // TASK-314 / ADR-046: amber active-slot indicator while establishing a
    // station connection (no audio yet) — mirrors SpotifyApp/PlaneRadarApp's
    // isConnecting() pattern, reusing _state rather than adding new tracking.
    bool isConnecting() const override { return _state == WRPlayState::CONNECTING; }
    // Red active-slot indicator on a sustained stream failure (dead host,
    // stall past the auto-skip/retry budget, WiFi loss, geo/DMCA block).
    // Self-clears the instant _play() lands PLAYING again (userInitiated
    // retry/skip, or the terminal-retry re-arm in tick()) — same sticky/
    // self-clearing contract as SpotifyApp::hasError()/StockApp::hasError().
    bool hasError() const override {
        return _state == WRPlayState::ERROR_WIFI ||
               _state == WRPlayState::ERROR_STALL ||
               _state == WRPlayState::ERROR_UNREACHABLE ||
               _state == WRPlayState::ERROR_BLOCKED;
    }

    // ── Input ──────────────────────────────────────────────────────────────

    bool handleInput(TouchPhase phase, int x, int y) override {
        // TASK-277 (M-WR-PLEDIT-SCROLL): captured gesture — while a drag is
        // live, Move updates it and Release is consumed by drag-end BEFORE any
        // eject/transport hit-test [DEV-1-1 blocker]. Mirrors the donor
        // machine's phase structure (winampDisplay.h release-first/captured).
        if (_wrs != WRS_IDLE) {
            if (phase == TouchPhase::Release) return _gestureEnd();
            if (_wrs == WRS_SCROLL) _dragCurrentY = y;
            else                    _updateScrollDirect(y);
            return true;
        }

        // TASK-277: Press in the PLEDIT bands anchors a gesture. Press
        // anywhere else is not consumed (eject/transport act on Release, as
        // today).
        if (phase == TouchPhase::Press) {
            const int rowsY1 = PLEDIT_ROWS_Y + PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
            if (y >= PLEDIT_ROWS_Y && y < rowsY1) {
                if (x >= PLEDIT_CONTENT_X + PLEDIT_CONTENT_W && x < PLEDIT_W) {
                    _wrs = WRS_SCROLL_DIRECT;         // scrollbar column
                    _updateScrollDirect(y);
                    return true;
                }
                if (x >= PLEDIT_CONTENT_X &&
                    x < PLEDIT_CONTENT_X + PLEDIT_CONTENT_W && _stationCount > 0) {
                    _wrs                   = WRS_SCROLL;
                    _dragStartY            = y;
                    _dragCurrentY          = y;
                    _dragStartRow          = (y - PLEDIT_ROWS_Y) / PLEDIT_ROW_H;
                    _dragStartMs           = millis();
                    _dragStartScrollOffset = _scrollOffset;
                    return true;
                }
            }
            return false;
        }

        if (phase != TouchPhase::Release) return false;

        // No-anchor Release [VE-1-2]: no prior Press (exactly how cmdTap
        // drives the T_WR_* tap surface) — today's tap-at-(x,y) path,
        // unchanged from here down.

        // Eject → back to Spotify
        if (winampDisplay.hitTestEject(x, y)) {
            _stopAudio();
            persistPlayerMode((uint8_t)PlayerMode::Spotify);   // TASK-260
            switchApp(AppId::Spotify);
            return true;
        }

        // Transport buttons (PREV/PLAY/PAUSE/STOP/NEXT) via public hit-test
        int t = winampDisplay.hitTestTransportPublic(x, y);
        if (t == 0) { _prevStation(); return true; }
        if (t == 1 || t == 2) { _togglePlay(); return true; }
        if (t == 3) {
            _stopAudio();
            _state = WRPlayState::STOPPED;
            _dirty = true;
            return true;
        }
        if (t == 4) { _nextStation(); return true; }

        // PLEDIT rows → tap to select + play
        if (_stationCount > 0 &&
            x >= PLEDIT_CONTENT_X && x < PLEDIT_CONTENT_X + PLEDIT_CONTENT_W &&
            y >= PLEDIT_ROWS_Y    && y < PLEDIT_ROWS_Y + PLEDIT_ROW_COUNT * PLEDIT_ROW_H) {
            int row = (y - PLEDIT_ROWS_Y) / PLEDIT_ROW_H;
            int idx = _scrollOffset + row;
            if (idx >= 0 && idx < (int)_stationCount) {
                _play((uint8_t)idx);
                return true;
            }
        }

        return false;
    }

#ifdef SERIAL_DEBUG
    // TASK-277 [VE-1-5]: cmdTick drives the ACTIVE app's integrator — this is
    // the WebRadio entry point (private _tickScroll + repaint marker intact).
    void tickScrollDebug(float dt) { _tickScroll(dt); }
#endif

    // ── Serial debug surface (BP-036) ──────────────────────────────────────

    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "wrState") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrState\",\"state\":%d,\"last\":true", (int)_state);
            return true;
        }
        if (strcmp(var, "wrCount") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrCount\",\"count\":%u,\"pending\":%u,\"last\":true",
                     (unsigned)_stationCount, (unsigned)_pendingStations);
            return true;
        }
        // Debug: dump one loaded station by index — "get wrStation <idx>". Pair
        // with wrCount to walk the whole list from a host script when the
        // physical display can't be inspected directly.
        if (strncmp(var, "wrStation", 9) == 0) {
            int idx = -1;
            sscanf(var + 9, "%d", &idx);
            if (idx < 0 || idx >= (int)_stationCount) {
                snprintf(buf, len,
                         "\"var\":\"wrStation\",\"error\":\"idx out of range\","
                         "\"count\":%u,\"last\":true", (unsigned)_stationCount);
                return true;
            }
            snprintf(buf, len,
                     "\"var\":\"wrStation\",\"idx\":%d,\"name\":\"%s\","
                     "\"bitrate\":%u,\"url\":\"%s\",\"last\":true",
                     idx, _stations[idx].name, (unsigned)_stations[idx].bitrate,
                     _stations[idx].url);
            return true;
        }
        if (strcmp(var, "wrIdx") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrIdx\",\"idx\":%u,\"last\":true", (unsigned)_currentIdx);
            return true;
        }
        // TASK-277: gesture observability — field set VE-signed (BP-024, see
        // design doc §VE dbg-surface sign-off). offset/drag exact; vel/accum
        // tolerance-banded only [VE-1-4].
        if (strcmp(var, "wrScroll") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrScroll\",\"offset\":%d,\"drag\":%d,\"vel\":%.4f,"
                     "\"accum\":%.4f,\"speedK\":%.4f,\"last\":true",
                     _scrollOffset, (int)_wrs, (double)_scrollVelocity,
                     (double)_scrollAccum, (double)_scrollSpeedK);
            return true;
        }
        if (strcmp(var, "wrIcy") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrIcy\",\"title\":\"%s\",\"last\":true", _icyTitle);
            return true;
        }
        // TASK-209: report the configured ceiling, the HW-mod flag, and the
        // hardware-clamped value actually fed to setVolume() (T_WR_VOL_03).
        if (strcmp(var, "wrEffectiveVol") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrEffectiveVol\",\"maxVol\":%u,\"hwMod\":%s,"
                     "\"eff\":%u,\"last\":true",
                     (unsigned)g_settings.webRadioMaxVolume,
                     g_settings.webRadioHwMod ? "true" : "false",
                     (unsigned)wrEffectiveVolume());
            return true;
        }
        // T_WR_EJECT_01 surface — reports that eject is wired
        if (strcmp(var, "wrEject") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrEject\",\"wired\":true,\"last\":true");
            return true;
        }
        if (strcmp(var, "wrLastHttp") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrLastHttp\",\"http\":%d,\"ok\":%d,\"count\":%u,"
                     "\"jsonErr\":\"%s\",\"tlsInsecure\":%d,\"last\":true",
                     _lastHttpCode, (int)_lastOk, (unsigned)_stationCount, _lastJsonErr,
                     (int)_lastTlsInsecure);
            return true;
        }
        // TASK-234: auto-skip scan state — lets VE assert the bound (one list pass)
        // and the settled-reset without a logic analyser.
        if (strcmp(var, "wrSkip") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrSkip\",\"autoSkip\":%d,\"tried\":%u,\"retries\":%u,"
                     "\"settled\":%d,\"pending\":%u,\"last\":true",
                     (int)g_settings.webRadioAutoSkip, (unsigned)_autoSkipTried,
                     (unsigned)_stallRetries, (int)_settled, (unsigned)_pendingAction);
            return true;
        }
        // TASK-255 (M-WEBRADIO-NOPSRAM, V0): PLAYING-hold duration in ms (0 when not
        // PLAYING) — the ≥60 s decision-gate signal T_WR_PLAY_SUSTAIN needs
        // (wrSkip.settled only proves WR_SETTLED_MS=12 s; _playingSinceMs was private).
        if (strcmp(var, "wrPlaying") == 0) {
            uint32_t ms = (_state == WRPlayState::PLAYING && _playingSinceMs)
                          ? (uint32_t)(millis() - _playingSinceMs) : 0u;
            snprintf(buf, len, "\"var\":\"wrPlaying\",\"ms\":%u,\"playing\":%d,\"last\":true",
                     (unsigned)ms, (int)(_state == WRPlayState::PLAYING));
            return true;
        }
        // T_WR_HEAP_01/02: heap snapshots queryable without relying on log capture
        if (strcmp(var, "wrHeap") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrHeap\","
                     "\"initFree\":%u,\"initMin\":%u,"
                     "\"fetchFree\":%u,\"fetchMin\":%u,\"last\":true",
                     (unsigned)_heapInitFree, (unsigned)_heapInitMin,
                     (unsigned)_heapFetchFree, (unsigned)_heapFetchMin);
            return true;
        }
#ifdef MEMBUDGET_PHASE1
        // TASK-263: halved-DMA (PATCH-MEMBUDGET-4) underrun metric. underruns =
        // input-buffer-empty events while PLAYING (objective proxy for audible gaps;
        // with the 8K DMA ring an empty input buffer becomes a gap far faster than
        // with the stock 32K). minBufPct = session low-water. Reset on each PLAYING
        // entry. Operator should still confirm by ear; this is the quantified gate.
        // TASK-266: recurrentUnderruns excludes the connect-time initial-fill
        // transient (edges before the station has _settled past WR_SETTLED_MS) —
        // this is the field to gate a clean pass/fail on; `underruns` is kept as
        // the raw total for back-compat with existing tooling (test_webradio_soak.py,
        // exp012_measure.py) which already treats underruns=1/session as expected.
        if (strcmp(var, "wrUnderruns") == 0) {
            uint32_t playMs = (_state == WRPlayState::PLAYING && _playingSinceMs)
                              ? (uint32_t)(millis() - _playingSinceMs) : 0u;
            snprintf(buf, len,
                     "\"var\":\"wrUnderruns\",\"underruns\":%u,\"recurrentUnderruns\":%u,"
                     "\"minBufPct\":%u,\"bufPct\":%u,\"playMs\":%u,\"last\":true",
                     (unsigned)_underrunCount, (unsigned)_recurrentUnderrunCount,
                     (unsigned)_minBufPct, (unsigned)_bufPct, (unsigned)playMs);
            return true;
        }
        // TASK-292: device-side arena lifecycle totals. The wr-soak balance gate
        // used to count [membudget] serial lines, which the harness's own
        // reset_input_buffer() drops at command boundaries → false-FAILs.
        // These counters live in mb_arena and never reset, so start/end deltas
        // are loss-proof. Invariant: acquires - releases == active. upMs lets
        // the harness detect a mid-soak reboot (counters reset → deltas lie).
        if (strcmp(var, "arenaStats") == 0) {
            snprintf(buf, len,
                     "\"var\":\"arenaStats\",\"acquires\":%u,\"releases\":%u,"
                     "\"fails\":%u,\"active\":%d,\"hwm\":%u,\"upMs\":%u,\"last\":true",
                     (unsigned)mb_arena_acquire_total(),
                     (unsigned)mb_arena_release_total(),
                     (unsigned)mb_arena_acquire_fail_total(),
                     (int)mb_arena_active(), (unsigned)mb_arena_hwm(),
                     (unsigned)millis());
            return true;
        }
#endif
        // TASK-278 (VE-2-2): pump task observability — alive flag, cycle count,
        // per-session max pump/mutex-wait times, stack headroom.
        if (strcmp(var, "wrPump") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrPump\",\"alive\":%d,\"cycles\":%u,"
                     "\"maxPumpMs\":%u,\"maxMutexWaitMs\":%u,\"stackHwm\":%u,\"last\":true",
                     (int)wrPumpAlive(), (unsigned)s_wrPumpCycles,
                     (unsigned)s_wrPumpMaxPumpMs, (unsigned)s_wrPumpMaxMutexWaitMs,
                     (unsigned)wrPumpStackHighWaterBytes());
            return true;
        }
        return false;
    }

    bool dbgSet(const char* var, const char* val) {
        // T_WR_ERR_01–04: force playState for synthetic error injection (TASK-212)
        if (strcmp(var, "wrState") == 0) {
            int s = atoi(val);
            if (s >= 0 && s <= (int)WRPlayState::ERROR_BLOCKED) {
                _state = (WRPlayState)s;
                _dirty = true;
            }
            return true;
        }
        // T_WR_EJECT_02: serial-inject eject action
        if (strcmp(var, "wrEject") == 0) {
            _stopAudio();
            persistPlayerMode((uint8_t)PlayerMode::Spotify);   // TASK-260
            switchApp(AppId::Spotify);
            return true;
        }
        if (strcmp(var, "wrPlay") == 0) {
            int idx = atoi(val);
            if (idx >= 0 && idx < (int)_stationCount) _play((uint8_t)idx);
            return true;
        }
        if (strcmp(var, "wrStop") == 0) {
            _stopAudio();
            _state = WRPlayState::STOPPED;
            _dirty = true;
            return true;
        }
        if (strcmp(var, "wrNext") == 0) { _nextStation(); return true; }
        if (strcmp(var, "wrPrev") == 0) { _prevStation(); return true; }
        // TASK-277: WebRadio-local speed calibration (mirrors winampDisplay's
        // `set speedK` under the WebRadio dbg surface; shared default comes
        // from scrollTuning.h).
        if (strcmp(var, "wrSpeedK") == 0) {
            float k = (float)atof(val);
            if (k > 0.0f && k <= 10.0f) _scrollSpeedK = k;
            return true;
        }
        // TASK-237: synthesize N unreachable stations + arm forced connect-fail, so
        // the auto-skip terminal bound (skip ≤ N-1, land terminal, never loop) is
        // deterministically testable without a real dead stream. `0` disables and
        // clears the synthetic list. Debug-only.
        // TASK-261 Phase 2 debug: inject a direct stream URL as a synthetic single
        // station and start playback immediately. Bypasses radio-browser API fetch
        // so arena allocation can be tested when the API is unreachable. Debug-only.
        // Usage: set wrUrl http://IP:PORT/mount
        if (strcmp(var, "wrUrl") == 0) {
            if (!val || !val[0]) return true;
            strlcpy(_stations[0].name, "INJECTED", sizeof(_stations[0].name));
            strlcpy(_stations[0].url, val, sizeof(_stations[0].url));
            _stations[0].bitrate = 0;
            _stationCount = 1;
            _currentIdx   = 0;
            _debugForceConnFail = false;
            _pendingAction = ACT_NONE;
            _autoSkipTried = 0;
            _stallRetries  = 0;
            _dirty = true;
            if (_pendingStations) {
                // TASK-289: the init()/resume() station fetch is still in
                // flight. Playing now makes both sides race for the heap and
                // the LOSER breaks either way: the fetch's TLS handshake dies
                // -32512, or — worse — Audio's I2S DMA alloc fails and the
                // unchecked vendored ctor null-derefs (observed LoadProhibited
                // reboot). Signal the fetch to wrap up at its next checkpoint
                // and let tick() start playback once the result lands.
                dataTask::abortWebRadioFetch();
                _deferredInject = true;
                LOG_I("webradio", "wrUrl deferred until station fetch resolves");
            } else {
                _play(0);
            }
            return true;
        }
        if (strcmp(var, "wrDeadUrls") == 0) {
            int n = atoi(val);
            if (n <= 0) {
                _debugForceConnFail = false;
                _stationCount = 0;
                _currentIdx = 0;
                _pendingAction = ACT_NONE;
                _autoSkipTried = 0;
                _stallRetries  = 0;
                return true;
            }
            if (n > dataTask::WR_MAX_STATIONS) n = dataTask::WR_MAX_STATIONS;
            for (int i = 0; i < n; i++) {
                snprintf(_stations[i].name, sizeof(_stations[i].name), "DEAD-%d", i);
                strlcpy(_stations[i].url, "http://127.0.0.1:1/dead",
                        sizeof(_stations[i].url));
                _stations[i].bitrate = 0;
            }
            _stationCount       = (uint8_t)n;
            _currentIdx         = 0;
            _pendingAction      = ACT_NONE;
            _autoSkipTried      = 0;
            _stallRetries       = 0;
            _debugForceConnFail = true;
            _dirty = true;
            return true;
        }
        // T-WRSET-01 (M-WEBRADIO-SETTINGS D3, WR-1): fault-injection hook —
        // directly parks a synthetic WebRadioStationsResult for tick()'s next
        // poll, bypassing the real dataTask fetch queue. Timing a genuinely
        // stale network result to land after a country/cap edit isn't
        // reproducible on demand; this simulates the same race by forcing a
        // result whose echo (countryCode/bitrateCap) is caller-controlled —
        // the test deliberately mismatches it against _cfgCountry/_cfgCap so
        // tick()'s identity check (line ~520) discards it. Forces
        // _pendingStations=true so tick() actually polls (the discard branch
        // does NOT clear it — get wrCount's "pending" stays 1, "count" stays
        // unchanged, proving the stale result never installed).
        // Usage: set wrInjectResult <country>[,<cap>]  (cap defaults to 255 —
        // not a real bitrateCap value: 0/64/96/128/192 — if omitted).
        if (strcmp(var, "wrInjectResult") == 0) {
            char country[4] = {};
            int  cap        = 255;
            sscanf(val, "%3[^,],%d", country, &cap);
            if (!country[0]) return true;   // malformed — no-op, still handled
            dataTask::WebRadioStationsResult r;
            r.ok           = true;
            r.lastHttpCode = 200;
            r.count        = 1;
            strlcpy(r.countryCode, country, sizeof(r.countryCode));
            r.bitrateCap   = (uint8_t)cap;
            strlcpy(r.stations[0].name, "INJECTED_STALE", sizeof(r.stations[0].name));
            strlcpy(r.stations[0].url, "http://198.51.100.1:1/stale",
                    sizeof(r.stations[0].url));
            r.stations[0].bitrate = 0;
            _pendingStations = true;
            dataTask::debugInjectWebRadioResult(r);
            LOG_I("webradio", "wrInjectResult parked %s/%u (cfg %s/%u)",
                  country, (unsigned)cap, _cfgCountry, (unsigned)_cfgCap);
            return true;
        }
        // TASK-237: drive the auto-skip setting (no on-device UI exists) so both
        // ON (skip past dead stations) and OFF (park on first stall) are testable.
        if (strcmp(var, "wrAutoSkip") == 0) {
            g_settings.webRadioAutoSkip = val && strcmp(val, "0") != 0;
            return true;
        }
        // T_WR_VOL_01–02 (TASK-209): runtime volume setter for *subjective* clip-point
        // calibration — intentionally UNCLAMPED so a human can drive past the soft cap
        // to find the clipping level. Production playback uses wrEffectiveVolume().
        if (strcmp(var, "wrVol") == 0) {
            int v = atoi(val);
            if (v < 0 || v > (int)WR_VOLUME_MAX) return true;
            if (!s_wr_audio) {
                // DEV-2-4: no live Audio session — wrVol must NOT lazily construct
                // one via wrAudio() (that would create an Audio with no pump task,
                // no mutex discipline, no arena). Clamp-store-only: nothing to
                // apply until a real _play() session exists.
                LOG_I("webradio", "vol set=%d — no active session, not applied", v);
                return true;
            }
            xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
            s_wr_audio->setVolume((uint8_t)v);
            xSemaphoreGive(s_wrAudioMutex);
            LOG_I("webradio", "vol set=%d", v);
            return true;
        }
        // TASK-254: inject an ICY StreamTitle (single token — cmdSet splits on
        // space) so the combined "STATION - SONG" marquee is checkable on DUT
        // without real playback. `set wrIcy -` clears it.
        if (strcmp(var, "wrIcy") == 0) {
            strlcpy(_icyTitle, (val && val[0] == '-' && !val[1]) ? "" : (val ? val : ""),
                    sizeof(_icyTitle));
            _drawTitleZone();
            return true;
        }
        // TASK-253: drive the buffer bar without real playback so the thumb
        // position is visually checkable on DUT.
        if (strcmp(var, "wrBufPct") == 0) {
            int p = atoi(val);
            if (p < 0) p = 0;
            if (p > 100) p = 100;
            _bufPct = (uint8_t)p;
            _drawPosbar();
            return true;
        }
        // TASK-209: drive the HW-mod flag + configured ceiling so the clamp logic
        // (wrEffectiveVolume / T_WR_VOL_03) is verifiable on DUT without a speaker.
        if (strcmp(var, "wrHwMod") == 0) {
            g_settings.webRadioHwMod = val && strcmp(val, "0") != 0;
            return true;
        }
        if (strcmp(var, "wrMaxVol") == 0) {
            int v = atoi(val);
            if (v >= 0 && v <= (int)WR_VOLUME_MAX) g_settings.webRadioMaxVolume = (uint8_t)v;
            return true;
        }
        return false;
    }

private:

    // ── State ──────────────────────────────────────────────────────────────

    WRPlayState _state          = WRPlayState::STOPPED;
    uint8_t     _stationCount   = 0;
    uint8_t     _currentIdx     = 0;
    int         _scrollOffset   = 0;
    // TASK-277 (M-WR-PLEDIT-SCROLL): velocity-scroll gesture state — pattern
    // copy of the ADR-030 machine (winampDisplay.h), clamped to _stationCount.
    // Tuning constants come from touch/scrollTuning.h (shared, single-source).
    enum WrScrollState : uint8_t { WRS_IDLE = 0, WRS_SCROLL = 1, WRS_SCROLL_DIRECT = 2 };
    WrScrollState _wrs            = WRS_IDLE;
    int         _dragStartY       = 0;
    int         _dragCurrentY     = 0;
    int         _dragStartRow     = -1;
    unsigned long _dragStartMs    = 0;
    int         _dragStartScrollOffset = 0;
    float       _scrollVelocity   = 0.0f;
    float       _scrollAccum      = 0.0f;
    float       _scrollSpeedK     = SCROLL_SPEED_K_DEFAULT;
    unsigned long _lastScrollMs   = 0;     // dt tracking for _tickScroll (M-LIST-v4 OQ1)
    bool        _pleditDirty      = false; // row-region-only repaint marker (not _dirty)
    bool        _pendingStations = false;
    // M-WEBRADIO-SETTINGS D3: config snapshot latched at every station-list
    // enqueue (_enqueueStationFetch()). resume() diffs it against g_settings
    // to detect Settings edits; tick()'s WR-1 identity check compares the
    // result's param echoes against it before installing. Empty/0 until the
    // first init() fetch so the first-entry path is unaffected.
    char        _cfgCountry[4]   = {};
    uint8_t     _cfgCap          = 0;
    // ADR-050 rule 3: coalesced lastStation persistence (see suspend()).
    bool        _lastStationDirty = false;
    uint8_t     _lastStationSaved = 0;
    // TASK-289: a wrUrl inject arrived while the station fetch was in flight —
    // tick() starts _play(0) when the (aborted) fetch result lands, so playback
    // never allocates concurrently with the fetch's TLS session.
    bool        _deferredInject  = false;
    bool        _dirty           = false;
    uint8_t     _bufPct          = 0;
    uint8_t     _bufPctDrawn     = 0;       // TASK-220: last buffer % painted (hysteresis)
#ifdef MEMBUDGET_PHASE1
    uint32_t    _underrunCount   = 0;       // TASK-263: input-buffer-empty events while PLAYING
    uint32_t    _recurrentUnderrunCount = 0; // TASK-266: same, but excludes the connect-time
                                              // initial-fill transient (only counts edges once
                                              // _settled) — the clean "recurrent underruns" signal
    uint8_t     _minBufPct       = 100;     // TASK-263: session low-water buffer %
    bool        _wasEmpty        = false;   // TASK-263: edge-detect for underrun count
    uint32_t    _lastUnderrunMs  = 0;       // TASK-263: millis() of last underrun
#endif
    uint32_t    _lastRunningMs   = 0;       // TASK-218: last tick isRunning() was true
    uint32_t    _lastBufChangeMs = 0;       // TASK-291: last tick inBufferFilled() differed from the previous reading
    uint32_t    _lastSeenFilled  = 0;       // TASK-291: previous tick's inBufferFilled() reading, for the above
    // TASK-234 (ADR-045): auto-skip-on-stall. Bounded retry-once-then-advance so a
    // no-PSRAM decode failure (TASK-233) tunes past dead stations instead of parking.
    uint32_t    _playingSinceMs  = 0;       // millis() when current PLAYING began
    uint8_t     _autoSkipTried   = 0;       // stations advanced in the current failure scan
    uint32_t    _lastAttemptMs   = 0;       // TASK-273: last _play() attempt (paces auto retry/skip)
    uint8_t     _stallRetries    = 0;       // stalls on the current station (retry once, then skip)
    bool        _settled         = false;   // current station survived WR_SETTLED_MS
    bool        _debugForceConnFail = false; // TASK-237: debug `set wrDeadUrls` — every _play() fails the connect deterministically (no network) so the auto-skip terminal bound is testable
    enum : uint8_t { ACT_NONE = 0, ACT_RETRY_SAME, ACT_SKIP_NEXT } _pendingAction = ACT_NONE;
    int         _lastHttpCode    = 0;
    bool        _lastOk          = false;
    bool        _spotifyYielded  = false;
    bool        _lastTlsInsecure = false;  // T_WR_TLS_01 — which path the last fetch used
    char        _lastJsonErr[24] = {};
    char        _icyTitle[WR_ICY_TITLE_LEN] = {};
    uint32_t    _lastHeapLogMs   = 0;
    dataTask::WebRadioStation _stations[dataTask::WR_MAX_STATIONS];
    // Heap snapshots for serial debug surface (set in init() and after fetch)
    uint32_t    _heapInitFree   = 0;
    uint32_t    _heapInitMin    = 0;
    uint32_t    _heapFetchFree  = 0;
    uint32_t    _heapFetchMin   = 0;
    // TASK-278: per-tick timeout-take snapshot of the pump-owned Audio object.
    // Degrades to these last-known values on a mutex-take miss (§Locking model).
    uint32_t    _snapFilled     = 0;
    uint32_t    _snapFreeB      = 0;
    bool        _snapRunning    = false;

    // M-WEBRADIO-SETTINGS D3: single enqueue funnel — latches the config
    // snapshot at the moment of request so tick()'s WR-1 identity check and
    // resume()'s diff always compare against what was actually asked for.
    // Every station-list enqueue MUST go through here.
    void _enqueueStationFetch() {
        strlcpy(_cfgCountry, g_settings.webRadioCountry, sizeof(_cfgCountry));
        _cfgCap = g_settings.webRadioBitrateCap;
        dataTask::enqueueWebRadioStations(g_settings.webRadioCountry,
                                          g_settings.webRadioBitrateCap);
        _pendingStations = true;
    }

    // ── Audio control ──────────────────────────────────────────────────────

    // TASK-278: per-tick read — short timeout-take, degrade to the last
    // snapshot on miss rather than blocking loopTask behind a pump that may
    // be inside an in-loop() reconnect/redirect/playlist connect [DEV-2-1].
    void _refreshAudioSnapshot() {
        if (!s_wr_audio) { _snapFilled = 0; _snapFreeB = 0; _snapRunning = false; return; }
        if (xSemaphoreTake(s_wrAudioMutex, WR_PUMP_READ_TIMEOUT_TICKS) == pdTRUE) {
            _snapFilled  = s_wr_audio->inBufferFilled();
            _snapFreeB   = s_wr_audio->inBufferFree();
            _snapRunning = s_wr_audio->isRunning();
            xSemaphoreGive(s_wrAudioMutex);
        }
        // else: mutex busy — reuse the last snapshot (already in the members).
    }

    // resumeTls=false is for _play()'s stop-then-replay path ONLY: a
    // tlsResume() followed within one scheduler quantum by a fresh tlsYield()
    // from the same task deadlocks the handshake — spotifyTask's 20 ms-sampled
    // service wait never observes the transient count==0, so it stays in the
    // old batch and never re-gives the ack the new yield is waiting on
    // (DUT-reproduced 2026-07-07 via NEXT-while-playing: loopTask parked the
    // full 150 s ceiling, serial dead). Keeping the yield held across the
    // stop removes the bounce entirely; _play() skips its re-yield when
    // _spotifyYielded is still true.
    void _stopAudio(bool resumeTls = true) {
        // TASK-278: control call — blocking take (§Locking model). Pump task
        // persists across this stop (only suspend() tears it down).
        if (s_wr_audio) {
            xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
            s_wr_audio->stopSong();
            xSemaphoreGive(s_wrAudioMutex);
        }
        _state = WRPlayState::STOPPED;
        _pendingAction = ACT_NONE;  // TASK-234: a stop/eject cancels any deferred retry/skip
        // Resume Spotify TLS if we yielded it for playback
        if (_spotifyYielded && resumeTls) {
            spotifyTask::tlsResume();
            _spotifyYielded = false;
        }
    }

    // userInitiated=true (user picked this station) resets the auto-skip scan;
    // the auto-skip/retry dispatch passes false so the scan bound is preserved.
    void _play(uint8_t idx, bool userInitiated = true) {
        if (idx >= _stationCount) return;
        // Keep the TLS yield held across the stop (see _stopAudio comment —
        // resume-then-reyield within one quantum deadlocks the handshake).
        _stopAudio(/*resumeTls=*/false);

        // TASK-277 [QM-1-3 — single rule]: a play starting while a gesture is
        // live (auto-skip is tick-driven, so this CAN coincide with a finger
        // down) cancels the gesture FIRST, then the keep-visible clamp below
        // runs. Offset stays consistent with list state; next Press re-anchors.
        _wrs            = WRS_IDLE;
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;

        if (userInitiated) { _autoSkipTried = 0; _stallRetries = 0; }
        _lastAttemptMs = millis();   // TASK-273: stamp every attempt (paces auto retry/skip)
        _currentIdx = idx;
        // RAM-only write + dirty mark; persisted coalesced in suspend()
        // (ADR-050 rule 3, M-WEBRADIO-SETTINGS D3) so auto-skip churn costs
        // zero flash writes.
        g_settings.webRadioLastStation = idx;
        _lastStationDirty = true;
        _icyTitle[0] = '\0';
        _bufPct      = 0;
        _state       = WRPlayState::CONNECTING;
        _dirty       = true;

        // Scroll PLEDIT to keep current station visible
        if ((int)_currentIdx < _scrollOffset)
            _scrollOffset = (int)_currentIdx;
        if ((int)_currentIdx >= _scrollOffset + PLEDIT_ROW_COUNT)
            _scrollOffset = (int)_currentIdx - PLEDIT_ROW_COUNT + 1;
        if (_scrollOffset < 0) _scrollOffset = 0;

        LOG_I("webradio", "play idx=%u name=%s url=%s",
              idx, _stations[idx].name, _stations[idx].url);

        // TASK-237: deterministic dead-host injection. Treat the connect as failed
        // without touching the network/audio path (so the auto-skip terminal bound
        // is testable without a real dead stream). Placed AFTER the userInitiated
        // _autoSkipTried/_stallRetries reset above so skip-counting is exercised.
        if (_debugForceConnFail) {
            _state = WRPlayState::ERROR_UNREACHABLE;
            LOG_W("webradio", "play idx=%u — forced connect-fail (debug wrDeadUrls)", idx);
            // The held-across-stop yield (see _stopAudio) must not leak on
            // this early return — no stream is coming.
            if (_spotifyYielded) {
                spotifyTask::tlsResume();
                _spotifyYielded = false;
            }
            _onPlaybackFailed(/*connectFail=*/true);
            _dirty = true;
            return;
        }

        // TASK-289: playback is about to carve up the heap (arena + decoder +
        // I2S) — a still-pending station fetch would only burn a doomed TLS
        // handshake against it (-32512). Tell dataTask to abandon; the fetch
        // is re-tried on the next resume() when the heap is quiet again.
        // tick()'s poll still consumes the abandoned result (http=-102).
        if (_pendingStations) dataTask::abortWebRadioFetch();

        // Yield Spotify TLS for the duration of playback.
        // Both new Audio() and connecttohost() need ~50 KB contiguous heap;
        // Spotify's active TLS session fragments the heap enough to fail.
        // TLS stays yielded while playing; _stopAudio() resumes it. Skipped
        // when the yield is still held from the previous session (stop-then-
        // replay path — see _stopAudio deadlock comment).
        if (!_spotifyYielded) {
            spotifyTask::tlsYield();
            _spotifyYielded = true;
        }
        esp_task_wdt_reset();

#ifdef MEMBUDGET_PHASE1
        // TASK-267 / ADR-047 Amd 1: acquire the arena HERE (JIT, after the overlay
        // freed Spotify + before the decoder allocs), NOT at boot — so the station
        // fetch ran with full heap. Ships in production (TASK-262 promotion); the
        // [membudget] probes around it are debug-only.
#ifdef SERIAL_DEBUG
        Serial.printf("[membudget] TASK-267 _play pre-acquire lfbInt=%u freeInt=%u\n",
            (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
            (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
#endif
        bool arenaOk = mb_arena_acquire();   // idempotent; on FAIL → libc fallback
        (void)arenaOk;
#ifdef SERIAL_DEBUG
        if (!s_wr_audio) {
            Serial.printf("[membudget] CP0-pre-audio-init freeDma=%u lfbDma=%u\n",
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
        }
#endif
#endif
        if (!s_wr_audio) {
            // TASK-289: I2S DMA-buffer floor. i2s_driver_install()'s DMA malloc
            // failure is UNCHECKED in the vendored Audio ctor — it null-derefs
            // (LoadProhibited, EXCVADDR 0x1c) and reboots the device. Observed
            // failing at lfbDma 13.8 KB (concurrent TLS held the pool) and
            // succeeding at 30+ KB; 16 KB sits just above the known-bad point
            // without rejecting plays that fragmentation alone would allow.
            // Degrade to the same path as a failed connect instead of crashing.
            size_t lfbDma = heap_caps_get_largest_free_block(MALLOC_CAP_DMA);
            if (lfbDma < 16 * 1024) {
                LOG_E("webradio", "DMA pool too low for I2S init: lfbDma=%u — abort play",
                      (unsigned)lfbDma);
                _state = WRPlayState::ERROR_UNREACHABLE;
                spotifyTask::tlsResume();
                _spotifyYielded = false;
                _onPlaybackFailed(/*connectFail=*/true);
                _dirty = true;
                return;
            }
            s_wr_audio = new Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);
            wrApplyInBufTrial(s_wr_audio);   // EXP-012: before connecttohost (InBuff not yet alloc'd)
        }
        // TASK-278: lazily create the pump task — AFTER mb_arena_acquire() above
        // [DEV-2-3], idempotent across churn within a session (persists until
        // suspend()).
        wrEnsurePumpTask();

        // TASK-278: control calls — blocking take (§Locking model).
        xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
        wrAudio().setVolume(wrEffectiveVolume());  // TASK-209: HW-mod clamp
        xSemaphoreGive(s_wrAudioMutex);
        // TASK-208 / TASK-261 CP1: heap watermark at connecttohost (audio buffer alloc point).
        // Extended with caps-split (T_MB_PROBE_00) for Phase 0: freeInt/lfbInt distinguish
        // INTERNAL pool contiguity from total free. Also tagged with auto-skip count so
        // post-skip fragmentation is visible vs first-play (Developer suggestion 3).
        LOG_I("webradio", "HEAP pre-connect free=%u min=%u maxAlloc=%u",
              (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap(),
              (unsigned)ESP.getMaxAllocHeap());
#if defined(MEMBUDGET_PHASE1) && defined(SERIAL_DEBUG)
        Serial.printf("[membudget] CP1-pre-connect skip=%u freeInt=%u lfbInt=%u freeDma=%u lfbDma=%u\n",
              (unsigned)_autoSkipTried,
              (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
              (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
              (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
              (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
#endif
        // TASK-278 / OQ4: control call (blocking take) + wr.connect timing —
        // Audio::loop() also re-enters this internally on redirect/reconnect/
        // playlist paths (DEV-2-1), which is why the pump's own mutex hold can
        // span seconds; this call site measures the _play()-side connect only.
        unsigned long _tConnect = millis();
        xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
        bool connectOk = wrAudio().connecttohost(_stations[idx].url);
        xSemaphoreGive(s_wrAudioMutex);
        perf::record("wr.connect", millis() - _tConnect);
        if (connectOk) {
            _state = WRPlayState::PLAYING;
            _lastRunningMs   = millis();  // TASK-218: seed grace window for stream-death detection
            _lastBufChangeMs = _lastRunningMs;  // TASK-291: seed grace window for the buffer-stall signal
            _lastSeenFilled  = 0;
            _playingSinceMs  = _lastRunningMs;  // TASK-234: settled-timer start
            _settled        = false;
            _bufPctDrawn    = 0;         // TASK-220: force a buffer-bar repaint on first fill
#ifdef MEMBUDGET_PHASE1
            _underrunCount          = 0; // TASK-263: fresh underrun count per PLAYING session
            _recurrentUnderrunCount = 0; // TASK-266: fresh per PLAYING session too
            _minBufPct      = 100;
            _wasEmpty       = false;
#endif
            // _spotifyYielded stays true; TLS resumes in _stopAudio()
        } else {
            _state = WRPlayState::ERROR_UNREACHABLE;
            LOG_W("webradio", "connecttohost failed idx=%u", idx);
            // resume TLS now — we won't be streaming
            spotifyTask::tlsResume();
            _spotifyYielded = false;
            _onPlaybackFailed(/*connectFail=*/true);  // TASK-234: skip a dead host
        }
        _dirty = true;
    }

    // TASK-234 (ADR-045): decide what to do after a station fails to play. A stall
    // (decode/stream death) retries the same station once — the no-PSRAM decoder
    // failure is fragmentation-dependent, so a retry often lands — then advances.
    // A connect failure skips straight on (re-dialling a dead host rarely helps).
    // Advancing is bounded to one pass over the list so a fully-dead list can't
    // loop forever; the action is deferred to the next tick (no recursion).
    void _onPlaybackFailed(bool connectFail) {
        if (!connectFail && _stallRetries == 0) {
            _stallRetries  = 1;
            _pendingAction = ACT_RETRY_SAME;
            LOG_I("webradio", "stall idx=%u — retrying once", _currentIdx);
            return;
        }
        if (g_settings.webRadioAutoSkip && _stationCount > 1 &&
            _autoSkipTried + 1 < _stationCount) {
            _autoSkipTried++;
            _pendingAction = ACT_SKIP_NEXT;
            LOG_I("webradio", "auto-skip %u/%u from idx=%u",
                  _autoSkipTried, _stationCount, _currentIdx);
        } else {
            _pendingAction = ACT_NONE;  // terminal — leave the error state on screen
            if (g_settings.webRadioAutoSkip)
                LOG_W("webradio", "auto-skip exhausted — no playable station");
        }
    }

    void _togglePlay() {
        if (_state == WRPlayState::PLAYING || _state == WRPlayState::CONNECTING) {
            _stopAudio();
        } else if (_stationCount > 0) {
            _play(_currentIdx);
        }
        _dirty = true;
    }

    void _prevStation() {
        if (_stationCount == 0) return;
        uint8_t next = (_currentIdx == 0) ? _stationCount - 1 : _currentIdx - 1;
        _play(next);
    }

    void _nextStation() {
        if (_stationCount == 0) return;
        uint8_t next = (_currentIdx + 1 >= _stationCount) ? 0 : _currentIdx + 1;
        _play(next);
    }

    // ── Display ────────────────────────────────────────────────────────────

    // Full repaint: Winamp skin background then WebRadio overlays.
    void _drawFull() {
        winampDisplay.repaintChrome();
        _drawPosbar();
        _drawTitleZone();   // TASK-254: title now carries the ICY StreamTitle inline
        _drawCountryBadge();
        _drawPledit();
    }

    void _drawPosbar() {
        // TASK-253: buffer-health gradient bar. The shared renderer owns the POSBAR
        // groove sprite, so it restores the groove (handling a shrinking buffer) and
        // draws the amber→green health-tinted gradient stretched to _bufPct.
        winampDisplay.drawBufferBar(_bufPct);
    }

    void _drawTitleZone() {
        // TASK-252: reuse the shared Winamp LED-font marquee (consistent with
        // Spotify's title, scrolls long names) instead of the plain GFX font.
        // setTitle() redraws only on change; tick() drives the scroll.
        char buf[48 + WR_ICY_TITLE_LEN];
        const char* t;
        if (_pendingStations) {
            t = "Loading...";
        } else if (_stationCount > 0 && _currentIdx < _stationCount) {
            switch (_state) {
                case WRPlayState::CONNECTING:        t = "Connecting..."; break;
                case WRPlayState::ERROR_UNREACHABLE: t = "Station unreachable"; break;
                case WRPlayState::ERROR_STALL:       t = "Stream stalled"; break;
                case WRPlayState::ERROR_WIFI:        t = "WiFi lost"; break;
                case WRPlayState::ERROR_BLOCKED:     t = "Station blocked"; break;
                default:
                    // TASK-254: combined Spotify-style marquee — fold the ICY
                    // StreamTitle into the title ("STATION - SONG   ") so it
                    // scrolls in the one LED line instead of a separate row that
                    // collided with the baked kbps/kHz badge.
                    if (_icyTitle[0]) {
                        snprintf(buf, sizeof(buf), "%s - %s   ",
                                 _stations[_currentIdx].name, _icyTitle);
                        t = buf;
                    } else {
                        t = _stations[_currentIdx].name;
                    }
                    break;
            }
        } else {
            // TASK-362: an empty list was previously always "No stations" —
            // indistinguishable from a heap-guard skip, a truncated fetch, a
            // real HTTP error, or a fetch that hasn't happened yet. Surface
            // _lastHttpCode (already captured from the fetch result, just
            // never read back here) so the failure reason is visible instead
            // of silently blank. Codes per dataTaskStorage.cpp's
            // fetchWebRadioStations(): 200 = fetched fine but genuinely
            // empty (e.g. bitrateCap filtered everything); -100 = JSON parse
            // error / truncated body (TASK-284); -101 = heap-guard skip
            // (largest free block below WR_FETCH_MIN_TLS_BLOCK,
            // M-HEAP-FRAGMENTATION); -102 = abandoned for playback
            // (TASK-289); anything else = a raw HTTP/HTTPClient code.
            switch (_lastHttpCode) {
                case 0:    t = "No stations"; break;   // never fetched yet
                case 200:  t = "No stations for country"; break;
                case -100: t = "No stations - fetch truncated"; break;
                case -101: t = "No stations - heap fragmented"; break;
                case -102: t = "No stations - cancelled"; break;
                default:
                    snprintf(buf, sizeof(buf), "No stations - error %d", _lastHttpCode);
                    t = buf;
                    break;
            }
        }
        winampDisplay.setTitle(t);
    }

    void _drawCountryBadge() {
        tft.fillRect(WR_BADGE_X, WR_BADGE_Y, WR_BADGE_W, WR_BADGE_H,
                     (uint16_t)PLEDIT_BODY_BG);
        tft.setTextColor(TFT_WHITE, (uint16_t)PLEDIT_BODY_BG);
        tft.drawCentreString(g_settings.webRadioCountry,
                             WR_BADGE_X + WR_BADGE_W / 2, WR_BADGE_Y + 2, 1);
    }

    // ── TASK-277: gesture helpers (ADR-030 pattern copy) ───────────────────

    // Release while a gesture is captured. Tap/scroll discrimination identical
    // to the donor (winampDisplay.h drag-end): dead zone + elapsed time, with
    // the quick-swipe min-1-row fallback verbatim.
    bool _gestureEnd() {
        if (_wrs == WRS_SCROLL_DIRECT) {
            _wrs = WRS_IDLE;
            return true;
        }
        const int dy = _dragCurrentY - _dragStartY;
        const unsigned long elapsed = (unsigned long)(millis() - _dragStartMs);
        const bool isTap = abs(dy) < PLEDIT_TAP_PX && elapsed < PLEDIT_TAP_MS;
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;
        _wrs = WRS_IDLE;
        if (isTap) {
            const int idx = _dragStartScrollOffset + _dragStartRow;
            if (_dragStartRow >= 0 && idx >= 0 && idx < (int)_stationCount)
                _play((uint8_t)idx);
        } else if (elapsed < PLEDIT_TAP_MS) {
            // Quick swipe: integrator accumulated ~0 rows (brief dt); apply a
            // guaranteed min-1-row delta from the press-time offset.
            const int delta  = max(1, abs(dy) / PLEDIT_ROW_H);
            const int dir    = (dy <= 0) ? 1 : -1;
            const int maxOff = max(0, (int)_stationCount - PLEDIT_ROW_COUNT);
            _scrollOffset = max(0, min(maxOff, _dragStartScrollOffset + dir * delta));
            _pleditDirty  = true;
        }
        // Slow drag: velocity model already applied rows during ticks.
        return true;
    }

    // Velocity integrator — form-identical to winampDisplay::tickScroll but
    // clamping against _stationCount. Inherits the donor's at-limit release
    // defect (M-LIST-v4 VE-C5) — accepted for parity, recorded there (OQ4).
    void _tickScroll(float dt) {
        if (_wrs != WRS_SCROLL) {
            _scrollAccum    = 0.0f;
            _scrollVelocity = 0.0f;
            return;
        }
        if (dt <= 0.0f || dt > 0.2f) return;
        const int dy = _dragCurrentY - _dragStartY;
        const float effective = max(0.0f, (float)abs(dy) - (float)SCROLL_DEAD_ZONE_PX);
        _scrollVelocity = (dy <= 0 ? 1.0f : -1.0f) * (effective * _scrollSpeedK);
        _scrollAccum += _scrollVelocity * dt;
        const int steps = (int)_scrollAccum;
        if (steps != 0) {
            _scrollAccum -= (float)steps;
            const int maxOffset = max(0, (int)_stationCount - PLEDIT_ROW_COUNT);
            const int no = max(0, min(maxOffset, _scrollOffset + steps));
            if (no != _scrollOffset) {
                _scrollOffset = no;
                _pleditDirty  = true;
            }
        }
    }

    // Scrollbar-column positional mapping — donor's updateScrollDirect math,
    // WebRadio window is not movable so no origin offsets.
    void _updateScrollDirect(int sy) {
        const int maxOffset = max(0, (int)_stationCount - PLEDIT_ROW_COUNT);
        if (maxOffset <= 0) return;
        constexpr int track_h = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;
        constexpr int travel  = track_h - SKIN_PLEDIT_THUMB_H;
        const int relY = sy - PLEDIT_ROWS_Y;
        const int no = max(0, min(maxOffset, relY * maxOffset / travel));
        if (no != _scrollOffset) {
            _scrollOffset = no;
            _pleditDirty  = true;
        }
    }

    void _drawPledit() {
        // TASK-225: reuse the real Winamp PLEDIT sprite chrome (frame border,
        // scrollbar thumb, bottom bar) instead of the old flat fillRect panel,
        // so WebRadio's station list matches Spotify's playlist in the same skin.
        // The skin title bar carries no text by design (§PLEDIT title bar — the
        // active country is edited and surfaced via Settings > Applications >
        // WebRadio (M-WEBRADIO-SETTINGS), not an overlay), so the old
        // "N stations — country" header is dropped here too.
        winampDisplay.drawPleditFrame(_scrollOffset, (int)_stationCount);

        // Station rows — fill the CONTENT area only; the side frame tiles drawn
        // by drawPleditFrame() must not be painted over.
        for (int row = 0; row < PLEDIT_ROW_COUNT; row++) {
            int    idx  = _scrollOffset + row;
            int    rowY = PLEDIT_ROWS_Y + row * PLEDIT_ROW_H;
            bool   isCur = (idx == (int)_currentIdx) &&
                           (_state != WRPlayState::STOPPED);
            uint16_t fg  = isCur ? (uint16_t)0xFFFFU
                                 : (uint16_t)PLEDIT_FG_NORMAL;
            uint16_t bg  = (uint16_t)PLEDIT_BODY_BG;
            tft.fillRect(PLEDIT_CONTENT_X, rowY, PLEDIT_CONTENT_W, PLEDIT_ROW_H, bg);
            if (idx >= 0 && idx < (int)_stationCount) {
                tft.setTextColor(fg, bg);
                tft.drawString(_stations[idx].name, PLEDIT_CONTENT_X, rowY + 2, 1);
                if (_stations[idx].bitrate > 0) {
                    char br[8];
                    snprintf(br, sizeof(br), "%uk", (unsigned)_stations[idx].bitrate);
                    tft.setTextColor(0x4208U, bg);
                    tft.drawRightString(br,
                        PLEDIT_CONTENT_X + PLEDIT_CONTENT_W, rowY + 2, 1);
                }
            }
        }
    }
};
