#pragma once
// webRadioApp.h — International Web Radio app (M-WEBRADIO).
// Streams MP3 from radio-browser.info via ESP32-audioI2S on internal DAC GPIO26.
// Entered via Winamp eject button; exits back to Spotify via the same button.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <Audio.h>
#include <freertos/queue.h>
#include "esp_task_wdt.h"
#include <esp_heap_caps.h> // T_MB_PROBE_00: caps-split for CP1/CP2 (TASK-261 Phase 0+2)
#ifdef MEMBUDGET_PHASE1
#include "mb_arena.h"  // Phase 2: arena HWM reporting at CP2
#endif
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "gen/skin_layout.h"
#include "gen/webradio_countries.h"
#include "logSink.h"
#include "spotifyTask.h"
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
static constexpr uint32_t WR_STREAM_DEAD_MS = 5000;

// TASK-234 (ADR-045): a station that holds PLAYING this long is "settled" — past
// the decode-alloc-failure window (WR_STREAM_DEAD_MS) by a comfortable margin — so
// the auto-skip scan counter resets and a *later* death starts a fresh hunt rather
// than counting against the original scan's bound.
static constexpr uint32_t WR_SETTLED_MS = 12000;

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
// Written from ESP32-audioI2S callback (Core 0/audio task); read in tick() (Core 1).
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
    // CP2: emit caps-split on decoder-init line (the gate metric for Phase 1).
#ifdef MEMBUDGET_PHASE1
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

static Audio& wrAudio() {
    if (!s_wr_audio)
        s_wr_audio = new Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);
    return *s_wr_audio;
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
        _dirty           = true;
        _icyTitle[0]     = '\0';
        _bufPct          = 0;
        _lastHeapLogMs   = 0;

        if (!s_icyTitleQueue)
            s_icyTitleQueue = xQueueCreate(1, sizeof(char) * WR_ICY_TITLE_LEN);

        // Defer Audio creation to _play() — Audio(internalDAC) constructor
        // runs i2s_driver_install which can exceed 5s and trigger WDT when
        // init() is called synchronously from cmdTap (serial context).
        if (s_wr_audio) s_wr_audio->setVolume(wrEffectiveVolume());  // TASK-209: HW-mod clamp

        // TASK-208: heap watermark — app launch baseline
        _heapInitFree = ESP.getFreeHeap();
        _heapInitMin  = ESP.getMinFreeHeap();
        LOG_I("webradio", "HEAP init free=%u min=%u",
              (unsigned)_heapInitFree, (unsigned)_heapInitMin);

        // Kick off station list fetch
        LOG_I("webradio", "HEAP pre-fetch free=%u min=%u",
              (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap());
        dataTask::enqueueWebRadioStations(g_settings.webRadioCountry,
                                          g_settings.webRadioBitrateCap);
        _pendingStations = true;

        // _dirty=true; tick() handles first paint — init() must return fast
        // (called synchronously from cmdTap context; _drawFull here risks WDT).
    }

    void resume() override {
        _dirty = true;
        // Defer paint to tick() — resume() can also run from cmdTap context.

        if (g_settings.webRadioAutoplay && _stationCount > 0 &&
            _state == WRPlayState::STOPPED) {
            _play(_currentIdx);
        }
    }

    void suspend() override {
        _stopAudio();
    }

    void tick() override {
        // TASK-252: scroll the LED-font title marquee (long station names).
        winampDisplay.tickMarquee();

        // TASK-234 (ADR-045): process a deferred retry / auto-skip from a prior
        // tick's playback failure. Done here (not inline at the failure site) so
        // the connecttohost() blocking call never recurses — one attempt per tick.
        if (_pendingAction != ACT_NONE) {
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
                _pendingStations = false;
                // TASK-208: heap watermark — post-fetch (TLS torn down)
                _heapFetchFree = ESP.getFreeHeap();
                _heapFetchMin  = ESP.getMinFreeHeap();
                LOG_I("webradio", "HEAP post-fetch free=%u min=%u",
                      (unsigned)_heapFetchFree, (unsigned)_heapFetchMin);
                if (result.ok && result.count > 0) {
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

        // Audio loop — keeps I2S DMA buffer filled from HTTP stream
        if (s_wr_audio) s_wr_audio->loop();

        if (_state == WRPlayState::PLAYING) {
            uint32_t now = millis();

            // TASK-208: periodic heap watermark every 30 s during playback
            if (now - _lastHeapLogMs >= 30000u) {
                _lastHeapLogMs = now;
                LOG_I("webradio", "HEAP play free=%u min=%u",
                      (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap());
            }

            if (s_wr_audio) {
                // TASK-220/253: drive the POSBAR buffer bar from real buffer occupancy.
                // drawBufferBar() is a cheap targeted blit (groove + thumb), NOT a full
                // chrome repaint, so update it directly on small moves for a smooth thumb
                // (was a 15-pt hysteresis → _dirty full repaint, which made the thumb jump
                // ~33 px at a time). A tiny 2-pt threshold just skips no-op repaints.
                uint32_t filled = s_wr_audio->inBufferFilled();
                uint32_t freeB  = s_wr_audio->inBufferFree();
                uint32_t total  = filled + freeB;
                _bufPct = total ? (uint8_t)((uint32_t)filled * 100u / total) : 0;
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
                if (s_wr_audio->isRunning()) {
                    _lastRunningMs = now;
                    // TASK-234: once a station has held long enough to be past the
                    // decode-failure window, reset the auto-skip scan so a later
                    // death starts a fresh hunt instead of hitting the old bound.
                    if (!_settled && now - _playingSinceMs >= WR_SETTLED_MS) {
                        _settled       = true;
                        _autoSkipTried = 0;
                        _stallRetries  = 0;
                    }
                } else if (now - _lastRunningMs >= WR_STREAM_DEAD_MS) {
                    LOG_W("webradio",
                          "stream dead (isRunning=0 for %lums) — stop + resume Spotify TLS",
                          (unsigned long)(now - _lastRunningMs));
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

    // ── Input ──────────────────────────────────────────────────────────────

    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return false;

        // Eject → back to Spotify
        if (winampDisplay.hitTestEject(x, y)) {
            _stopAudio();
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
        if (strcmp(var, "wrIdx") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrIdx\",\"idx\":%u,\"last\":true", (unsigned)_currentIdx);
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
        // TASK-237: synthesize N unreachable stations + arm forced connect-fail, so
        // the auto-skip terminal bound (skip ≤ N-1, land terminal, never loop) is
        // deterministically testable without a real dead stream. `0` disables and
        // clears the synthetic list. Debug-only.
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
            if (v >= 0 && v <= (int)WR_VOLUME_MAX) {
                wrAudio().setVolume((uint8_t)v);
                LOG_I("webradio", "vol set=%d", v);
            }
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
    bool        _pendingStations = false;
    bool        _dirty           = false;
    uint8_t     _bufPct          = 0;
    uint8_t     _bufPctDrawn     = 0;       // TASK-220: last buffer % painted (hysteresis)
    uint32_t    _lastRunningMs   = 0;       // TASK-218: last tick isRunning() was true
    // TASK-234 (ADR-045): auto-skip-on-stall. Bounded retry-once-then-advance so a
    // no-PSRAM decode failure (TASK-233) tunes past dead stations instead of parking.
    uint32_t    _playingSinceMs  = 0;       // millis() when current PLAYING began
    uint8_t     _autoSkipTried   = 0;       // stations advanced in the current failure scan
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

    // ── Audio control ──────────────────────────────────────────────────────

    void _stopAudio() {
        if (s_wr_audio) s_wr_audio->stopSong();
        _state = WRPlayState::STOPPED;
        _pendingAction = ACT_NONE;  // TASK-234: a stop/eject cancels any deferred retry/skip
        // Resume Spotify TLS if we yielded it for playback
        if (_spotifyYielded) {
            spotifyTask::tlsResume();
            _spotifyYielded = false;
        }
    }

    // userInitiated=true (user picked this station) resets the auto-skip scan;
    // the auto-skip/retry dispatch passes false so the scan bound is preserved.
    void _play(uint8_t idx, bool userInitiated = true) {
        if (idx >= _stationCount) return;
        _stopAudio();  // stops current + resumes TLS if it was yielded

        if (userInitiated) { _autoSkipTried = 0; _stallRetries = 0; }
        _currentIdx = idx;
        g_settings.webRadioLastStation = idx;
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
            _onPlaybackFailed(/*connectFail=*/true);
            _dirty = true;
            return;
        }

        // Yield Spotify TLS for the duration of playback.
        // Both new Audio() and connecttohost() need ~50 KB contiguous heap;
        // Spotify's active TLS session fragments the heap enough to fail.
        // TLS stays yielded while playing; _stopAudio() resumes it.
        spotifyTask::tlsYield();
        _spotifyYielded = true;
        esp_task_wdt_reset();

        if (!s_wr_audio)
            s_wr_audio = new Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);

        wrAudio().setVolume(wrEffectiveVolume());  // TASK-209: HW-mod clamp
        // TASK-208 / TASK-261 CP1: heap watermark at connecttohost (audio buffer alloc point).
        // Extended with caps-split (T_MB_PROBE_00) for Phase 0: freeInt/lfbInt distinguish
        // INTERNAL pool contiguity from total free. Also tagged with auto-skip count so
        // post-skip fragmentation is visible vs first-play (Developer suggestion 3).
        LOG_I("webradio", "HEAP pre-connect free=%u min=%u maxAlloc=%u",
              (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap(),
              (unsigned)ESP.getMaxAllocHeap());
#ifdef MEMBUDGET_PHASE1
        Serial.printf("[membudget] CP1-pre-connect skip=%u freeInt=%u lfbInt=%u freeDma=%u lfbDma=%u\n",
              (unsigned)_autoSkipTried,
              (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
              (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
              (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
              (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
#endif
        if (wrAudio().connecttohost(_stations[idx].url)) {
            _state = WRPlayState::PLAYING;
            _lastRunningMs  = millis();  // TASK-218: seed grace window for stream-death detection
            _playingSinceMs = _lastRunningMs;  // TASK-234: settled-timer start
            _settled        = false;
            _bufPctDrawn    = 0;         // TASK-220: force a buffer-bar repaint on first fill
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
            t = "No stations";
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

    void _drawPledit() {
        // TASK-225: reuse the real Winamp PLEDIT sprite chrome (frame border,
        // scrollbar thumb, bottom bar) instead of the old flat fillRect panel,
        // so WebRadio's station list matches Spotify's playlist in the same skin.
        // The skin title bar carries no text by design (§PLEDIT title bar — the
        // active country is surfaced via Settings, not an overlay), so the old
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
