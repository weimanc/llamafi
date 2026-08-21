// audio/audioEngine.cpp — audio engine definitions, out-of-line
// (M-SRCLAYOUT Stage E / TASK-471). See audioEngine.h for the "why now" note
// on why these moved from internal (static) to external linkage.
#include "audio/audioEngine.h"
#include "spotifyTask.h"   // tlsResume()/tlsTryYield() — aeConnectFile/aeStopFile/aeDrainEof

QueueHandle_t s_icyTitleQueue = nullptr;

void audio_showstreamtitle(const char *info) {
    if (!s_icyTitleQueue || !info) return;
    char buf[WR_ICY_TITLE_LEN];
    strlcpy(buf, info, sizeof(buf));
    xQueueOverwrite(s_icyTitleQueue, buf);
}

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

TaskHandle_t g_loopTaskHandle = nullptr;

volatile bool s_aeEofPending = false;

// TASK-410: separate from WebRadioApp's _spotifyYielded — aeConnectFile() has
// no app instance to hold it. DUT finding: without yielding Spotify's TLS
// session first, its held heap fragments enough that both the arena acquire
// and the pump task's stack alloc fail on a normal boot (reproduced: arena
// acquire FAIL->libc-fallback, xTaskCreatePinnedToCore rc=-1) — same
// ~50KB-contiguous need _play() already documents below. Resumed in
// aeDrainEof(), the natural "done playing" point for this single-file scope
// (TASK-413 gets a real stop/teardown path). Not referenced outside this
// engine, so it stays file-static here rather than in the header.
static bool s_aeSpotifyYielded = false;

void audio_eof_mp3(const char *info) {
    (void)info;
    s_aeEofPending = true;
}

uint32_t s_aeEofCount = 0;

void aeDrainEof() {
    configASSERT(xTaskGetCurrentTaskHandle() == g_loopTaskHandle);
    if (!s_aeEofPending) return;
    s_aeEofPending = false;
    s_aeEofCount++;
    // TASK-418 wired auto-advance; this string kept saying otherwise and was
    // emitted 31 times on a DUT run where auto-advance demonstrably worked
    // (rows 0->1->2->3->4->0...). Corrected 2026-08-15.
    LOG_I("audioengine", "eof drained on loopTask");
    if (s_aeSpotifyYielded) {
        spotifyTask::tlsResume();
        s_aeSpotifyYielded = false;
    }
}

// ── Audio singleton ──────────────────────────────────────────────────────────
Audio* s_wr_audio = nullptr;

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

#ifdef SERIAL_DEBUG
size_t s_aeDmaFloorOverride = AE_I2S_DMA_FLOOR_BYTES;
#endif

// TASK-432: the ONLY place an Audio is constructed. Both arms (WebRadio's
// _play() and the FILE arm's aeConnectFile()) route through here, so the DMA
// floor and the allocation check cannot diverge between them.
static void aeReleaseArenaIfIdle() {
#ifdef MEMBUDGET_PHASE1
    if (!s_wr_audio && !wrPumpAlive()) {
        mb_arena_release();
        LOG_W("audioengine", "play aborted before engine bring-up — arena released");
    }
#endif
}

#ifdef SERIAL_DEBUG
bool s_aeNoArenaInject = false;
bool s_aeFailAudioInject = false;
#endif

bool aeEnsureAudio() {
    if (s_wr_audio) return true;

    size_t lfbDma = heap_caps_get_largest_free_block(MALLOC_CAP_DMA);
    if (AE_DMA_FLOOR() && lfbDma < AE_DMA_FLOOR()) {
        LOG_E("audioengine", "DMA pool too low for I2S init: lfbDma=%u — abort play",
              (unsigned)lfbDma);
        aeReleaseArenaIfIdle();
        return false;
    }

    // TASK-432: nothrow + check. Every other allocation on this path is
    // already checked (mb_arena_acquire() falls back to libc, the Helix
    // sub-allocations fail cleanly to "play FAILED"); this one was the lone
    // bare `new`.
    // TASK-432: the injection suppresses the allocation and then falls through
    // to the SAME failure handling below — it does not return early. An
    // injector that short-circuits past the rollback tests a path that does not
    // exist in production: the first cut did exactly that, skipped
    // aeReleaseArenaIfIdle(), and produced a FAIL that looked like a firmware
    // defect (LL-127, one level deeper — the fault must enter through the real
    // door).
    Audio* a = nullptr;
#ifdef SERIAL_DEBUG
    if (s_aeFailAudioInject) {
        LOG_E("audioengine", "Audio alloc failure INJECTED (set aeFailAudio 1)");
    } else
#endif
    {
        a = new (std::nothrow) Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);
    }
    if (!a) {
        LOG_E("audioengine", "Audio alloc failed: lfbInt=%u freeInt=%u — abort play",
              (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
              (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        aeReleaseArenaIfIdle();
        return false;
    }

    s_wr_audio = a;
    wrApplyInBufTrial(s_wr_audio);      // EXP-012: before connecttohost (InBuff not yet alloc'd)
    wrApplyConnectTimeout(s_wr_audio);  // TASK-392
    return true;
}

// ── Audio pump task (TASK-278 / M-WR-AUDIO-TASK, Phase 1) ────────────────────
SemaphoreHandle_t s_wrAudioMutex  = nullptr;  // guards every Audio method call
SemaphoreHandle_t s_wrPumpAckSem  = nullptr;  // teardown handshake
TaskHandle_t      s_wrPumpTask    = nullptr;
static volatile bool s_wrPumpStopReq = false;

volatile WrConnectKind s_wrPumpConnectKind = WrConnectKind::URL;

volatile WrPumpRequest s_wrPumpRequest = WrPumpRequest::NONE;  // written by loopTask, read/cleared by the pump task
volatile WrPumpResult  s_wrPumpResult  = WrPumpResult::NONE;   // written by the pump task, read/cleared by tick()'s poll

// Connect target for a posted CONNECT request. s_wrPumpConnectUrl itself is
// not referenced outside this engine, so it stays file-static here; the
// accessor is called from WebRadioApp::_play() too, so it needs external
// linkage.
static char* s_wrPumpConnectUrl = nullptr;
char* wrPumpConnectUrlBuf() {
    if (!s_wrPumpConnectUrl) s_wrPumpConnectUrl = new char[WR_PUMP_CONNECT_URL_LEN];
    return s_wrPumpConnectUrl;
}

volatile uint32_t s_wrPumpCycles         = 0;
volatile uint32_t s_wrPumpMaxPumpMs      = 0;
volatile uint32_t s_wrPumpMaxMutexWaitMs = 0;

bool wrPumpAlive() { return s_wrPumpTask != nullptr; }

// ── TASK-352: Winamp volume-slider seam ───────────────────────────────────────
bool    s_wrVolPctDirty = false;
uint8_t s_wrVolPctSaved = 100;

void wrVolumeSink(int pct) {
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

size_t wrPumpStackSizeBytes() {
    return (size_t)WR_PUMP_STACK_WORDS * sizeof(StackType_t);
}
size_t wrPumpStackHighWaterBytes() {
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
void wrEnsurePumpTask() {
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
void wrTeardownPumpTask() {
    if (!s_wrPumpTask) return;
    s_wrPumpStopReq = true;
    if (xSemaphoreTake(s_wrPumpAckSem, pdMS_TO_TICKS(WR_PUMP_ACK_TIMEOUT_MS)) != pdTRUE) {
        LOG_E("wrpump", "teardown ack timeout after %ums — pump may be stuck in Audio::loop()",
              (unsigned)WR_PUMP_ACK_TIMEOUT_MS);
    }
    s_wrPumpTask = nullptr;
}

bool aeConnectFile(const char* path) {
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
    // TASK-443 option (a)/(e) EXPERIMENT TOGGLE — `set aeNoArena 1`, debug only.
    // Not the ruling: the ruling would delete this acquire outright. This lets the
    // decisive measurement (does a full local play succeed with the decoder on the
    // libc path?) run on hardware before the ruling is accepted, instead of after.
    // Default keeps today's behaviour exactly.
#ifdef SERIAL_DEBUG
    if (!s_aeNoArenaInject)
#endif
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

void aeStopFile(bool connecting) {
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

void aeTeardownFile(bool connecting) {
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
