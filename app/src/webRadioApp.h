#pragma once
// webRadioApp.h — International Web Radio app (M-WEBRADIO).
// Streams MP3 from radio-browser.info via ESP32-audioI2S on internal DAC GPIO26.
// Entered via Winamp eject button; exits back to Spotify via the same button.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <Audio.h>
#include <freertos/queue.h>
#include "esp_task_wdt.h"
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

// TASK-224: ICY StreamTitle buffer length, used consistently across the audio
// callback, the queue's element size, tick()'s receive buffer, and _icyTitle.
static constexpr size_t WR_ICY_TITLE_LEN = 104;

// TASK-224: volume ceiling (matches settingsStorage.h's webRadioMaxVolume
// "1-21" comment / ESP32-audioI2S's setVolume() range).
static constexpr uint8_t WR_VOLUME_MAX = 21;

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

// ICY StreamTitle line (between Winamp title and VU):
static constexpr int WR_ICY_X = TITLE_X;
static constexpr int WR_ICY_Y = 36;
static constexpr int WR_ICY_W = TITLE_W;
static constexpr int WR_ICY_H = 6;

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
        if (s_wr_audio) s_wr_audio->setVolume(g_settings.webRadioMaxVolume);

        // TASK-208: heap watermark — app launch baseline
        _heapInitFree = ESP.getFreeHeap();
        _heapInitMin  = ESP.getMinFreeHeap();
        LOG_I("webradio", "HEAP init free=%u min=%u",
              (unsigned)_heapInitFree, (unsigned)_heapInitMin);

        // Kick off station list fetch
        LOG_I("webradio", "HEAP pre-fetch free=%u min=%u",
              (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap());
        dataTask::enqueueWebRadioStations(g_settings.webRadioCountry);
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
        // Poll ICY metadata from audio callback queue
        {
            char buf[WR_ICY_TITLE_LEN];
            if (s_icyTitleQueue && xQueueReceive(s_icyTitleQueue, buf, 0) == pdTRUE) {
                strlcpy(_icyTitle, buf, sizeof(_icyTitle));
                _drawIcyLine();
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
                // TASK-220: drive the POSBAR buffer-health bar from real buffer
                // occupancy. Repaint only when it moves a meaningful amount
                // (hysteresis) so we don't trigger a full chrome repaint every tick.
                uint32_t filled = s_wr_audio->inBufferFilled();
                uint32_t freeB  = s_wr_audio->inBufferFree();
                uint32_t total  = filled + freeB;
                _bufPct = total ? (uint8_t)((uint32_t)filled * 100u / total) : 0;
                int delta = (int)_bufPct - (int)_bufPctDrawn;
                if (delta < 0) delta = -delta;
                if (delta >= 15) {
                    _bufPctDrawn = _bufPct;
                    _dirty = true;
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
                } else if (now - _lastRunningMs >= WR_STREAM_DEAD_MS) {
                    LOG_W("webradio",
                          "stream dead (isRunning=0 for %lums) — stop + resume Spotify TLS",
                          (unsigned long)(now - _lastRunningMs));
                    _stopAudio();                       // resumes the yielded Spotify TLS
                    _state = WRPlayState::ERROR_STALL;  // _stopAudio() set STOPPED; show stall
                    _dirty = true;
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
        // T_WR_VOL_01–03 (TASK-209): runtime volume setter for calibration
        if (strcmp(var, "wrVol") == 0) {
            int v = atoi(val);
            if (v >= 0 && v <= (int)WR_VOLUME_MAX) {
                wrAudio().setVolume((uint8_t)v);
                LOG_I("webradio", "vol set=%d", v);
            }
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
        // Resume Spotify TLS if we yielded it for playback
        if (_spotifyYielded) {
            spotifyTask::tlsResume();
            _spotifyYielded = false;
        }
    }

    void _play(uint8_t idx) {
        if (idx >= _stationCount) return;
        _stopAudio();  // stops current + resumes TLS if it was yielded

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

        // Yield Spotify TLS for the duration of playback.
        // Both new Audio() and connecttohost() need ~50 KB contiguous heap;
        // Spotify's active TLS session fragments the heap enough to fail.
        // TLS stays yielded while playing; _stopAudio() resumes it.
        spotifyTask::tlsYield();
        _spotifyYielded = true;
        esp_task_wdt_reset();

        if (!s_wr_audio)
            s_wr_audio = new Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);

        wrAudio().setVolume(g_settings.webRadioMaxVolume);
        // TASK-208: heap watermark at connecttohost (audio buffer alloc point).
        // maxAlloc = largest contiguous block — the figure that actually governs
        // whether the MP3 decoder / TLS buffers can be allocated (TASK-233).
        LOG_I("webradio", "HEAP pre-connect free=%u min=%u maxAlloc=%u",
              (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap(),
              (unsigned)ESP.getMaxAllocHeap());
        if (wrAudio().connecttohost(_stations[idx].url)) {
            _state = WRPlayState::PLAYING;
            _lastRunningMs = millis();  // TASK-218: seed grace window for stream-death detection
            _bufPctDrawn   = 0;         // TASK-220: force a buffer-bar repaint on first fill
            // _spotifyYielded stays true; TLS resumes in _stopAudio()
        } else {
            _state = WRPlayState::ERROR_UNREACHABLE;
            LOG_W("webradio", "connecttohost failed idx=%u", idx);
            // resume TLS now — we won't be streaming
            spotifyTask::tlsResume();
            _spotifyYielded = false;
        }
        _dirty = true;
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
        _drawTitleZone();
        _drawIcyLine();
        _drawCountryBadge();
        _drawPledit();
    }

    void _drawPosbar() {
        // POSBAR used as buffer-health bar. Background already drawn by repaintChrome.
        // Overdraw with green fill proportional to buffer percentage.
        if (_bufPct > 0) {
            int fillW = (int)((uint32_t)_bufPct * POSBAR_W / 100);
            if (fillW > POSBAR_W) fillW = POSBAR_W;
            tft.fillRect(POSBAR_X, POSBAR_Y, fillW, POSBAR_H, 0x07E0U);
        }
    }

    void _drawTitleZone() {
        tft.fillRect(TITLE_X, TITLE_Y, TITLE_W, TITLE_H, TFT_BLACK);
        tft.setTextColor(0x07E0U, TFT_BLACK);
        if (_pendingStations) {
            tft.drawString("Loading...", TITLE_X, TITLE_Y, 1);
        } else if (_stationCount > 0 && _currentIdx < _stationCount) {
            switch (_state) {
                case WRPlayState::CONNECTING:
                    tft.drawString("Connecting...", TITLE_X, TITLE_Y, 1); break;
                case WRPlayState::ERROR_UNREACHABLE:
                    tft.drawString("Station unreachable", TITLE_X, TITLE_Y, 1); break;
                case WRPlayState::ERROR_STALL:
                    tft.drawString("Stream stalled", TITLE_X, TITLE_Y, 1); break;
                case WRPlayState::ERROR_WIFI:
                    tft.drawString("WiFi lost", TITLE_X, TITLE_Y, 1); break;
                case WRPlayState::ERROR_BLOCKED:
                    tft.drawString("Station blocked", TITLE_X, TITLE_Y, 1); break;
                default:
                    tft.drawString(_stations[_currentIdx].name, TITLE_X, TITLE_Y, 1); break;
            }
        } else {
            tft.drawString("No stations", TITLE_X, TITLE_Y, 1);
        }
    }

    void _drawIcyLine() {
        tft.fillRect(WR_ICY_X, WR_ICY_Y, WR_ICY_W, WR_ICY_H, TFT_BLACK);
        if (_icyTitle[0]) {
            tft.setTextColor(TFT_WHITE, TFT_BLACK);
            tft.drawString(_icyTitle, WR_ICY_X, WR_ICY_Y, 1);
        }
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
