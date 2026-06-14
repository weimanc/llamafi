#pragma once
// webRadioApp.h — International Web Radio app (M-WEBRADIO).
// Streams MP3 from radio-browser.info via ESP32-audioI2S on internal DAC GPIO26.
// Entered via Winamp eject button; exits back to Spotify via the same button.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <Audio.h>
#include <freertos/queue.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "gen/skin_layout.h"
#include "gen/webradio_countries.h"
#include "logSink.h"
#include "winamp/winampDisplay.h"

extern TFT_eSPI         tft;
extern WinampDisplay    winampDisplay;

// ── Play state ───────────────────────────────────────────────────────────────

enum class WRPlayState : uint8_t {
    STOPPED          = 0,
    CONNECTING       = 1,
    PLAYING          = 2,
    ERROR_WIFI       = 3,
    ERROR_STALL      = 4,
    ERROR_UNREACHABLE = 5,
};

// ── ICY metadata queue ───────────────────────────────────────────────────────
// Written from ESP32-audioI2S callback (Core 0/audio task); read in tick() (Core 1).
// Depth 1 + overwrite: old unread title is replaced by the newest one.

static QueueHandle_t s_icyTitleQueue = nullptr;

// Required by ESP32-audioI2S — weak-linked extern resolved by user code.
// Defined with external linkage; safe since webRadioApp.h is included only from main.cpp.
void audio_showstreamtitle(const char *info) {
    if (!s_icyTitleQueue || !info) return;
    char buf[104];
    strlcpy(buf, info, sizeof(buf));
    xQueueOverwrite(s_icyTitleQueue, buf);
}

// ── Audio singleton ──────────────────────────────────────────────────────────
// Internal DAC, GPIO26 (I2S_DAC_CHANNEL_LEFT_EN = SC8002B amp).
// Pointer used to defer construction until after I2S is ready.

static Audio* s_wr_audio = nullptr;

static Audio& wrAudio() {
    if (!s_wr_audio) {
        s_wr_audio = new Audio(/*internalDAC=*/true, /*channel=*/I2S_DAC_CHANNEL_LEFT_EN);
    }
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

        if (!s_icyTitleQueue)
            s_icyTitleQueue = xQueueCreate(1, sizeof(char) * 104);

        wrAudio().setVolume(g_settings.webRadioMaxVolume);

        // Kick off station list fetch
        dataTask::enqueueWebRadioStations(g_settings.webRadioCountry);
        _pendingStations = true;

        _drawFull();
    }

    void resume() override {
        _dirty = true;
        _drawFull();

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
            char buf[104];
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
                if (result.ok && result.count > 0) {
                    _stationCount = result.count;
                    memcpy(_stations, result.stations,
                           result.count * sizeof(dataTask::WebRadioStation));
                    if (_currentIdx >= _stationCount) _currentIdx = 0;
                    LOG_I("webradio", "stations loaded count=%u country=%s",
                          _stationCount, result.countryCode);
                } else {
                    LOG_W("webradio", "station fetch failed ok=%d http=%d",
                          result.ok, result.lastHttpCode);
                }
                _dirty = true;
            }
        }

        // Audio loop — keeps I2S DMA buffer filled from HTTP stream
        if (s_wr_audio) s_wr_audio->loop();

        if (_dirty) {
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
                     "\"var\":\"wrCount\",\"count\":%u,\"last\":true", (unsigned)_stationCount);
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
        return false;
    }

    bool dbgSet(const char* var, const char* val) {
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
    char        _icyTitle[104]   = {};
    dataTask::WebRadioStation _stations[100];

    // ── Audio control ──────────────────────────────────────────────────────

    void _stopAudio() {
        if (s_wr_audio) s_wr_audio->stopSong();
        _state = WRPlayState::STOPPED;
    }

    void _play(uint8_t idx) {
        if (idx >= _stationCount) return;
        _stopAudio();

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

        wrAudio().setVolume(g_settings.webRadioMaxVolume);
        if (wrAudio().connecttohost(_stations[idx].url)) {
            _state = WRPlayState::PLAYING;
        } else {
            _state = WRPlayState::ERROR_UNREACHABLE;
            LOG_W("webradio", "connecttohost failed idx=%u", idx);
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
                    tft.drawString("ERROR: host unreachable", TITLE_X, TITLE_Y, 1); break;
                case WRPlayState::ERROR_STALL:
                    tft.drawString("ERROR: stream stalled", TITLE_X, TITLE_Y, 1); break;
                case WRPlayState::ERROR_WIFI:
                    tft.drawString("ERROR: WiFi lost", TITLE_X, TITLE_Y, 1); break;
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
        // Title bar
        tft.fillRect(0, PLEDIT_Y, PLEDIT_W, PLEDIT_TITLE_H, (uint16_t)PLEDIT_BODY_BG);
        {
            char header[64];
            if (_pendingStations) {
                snprintf(header, sizeof(header), "Loading stations...");
            } else {
                snprintf(header, sizeof(header), "%u stations \xe2\x80\x94 %s",
                         (unsigned)_stationCount, g_settings.webRadioCountry);
            }
            tft.setTextColor((uint16_t)PLEDIT_FG_NORMAL, (uint16_t)PLEDIT_BODY_BG);
            tft.drawString(header, PLEDIT_CONTENT_X, PLEDIT_Y + 4, 1);
        }

        // Station rows
        for (int row = 0; row < PLEDIT_ROW_COUNT; row++) {
            int    idx  = _scrollOffset + row;
            int    rowY = PLEDIT_ROWS_Y + row * PLEDIT_ROW_H;
            bool   isCur = (idx == (int)_currentIdx) &&
                           (_state != WRPlayState::STOPPED);
            uint16_t fg  = isCur ? (uint16_t)0xFFFFU
                                 : (uint16_t)PLEDIT_FG_NORMAL;
            uint16_t bg  = (uint16_t)PLEDIT_BODY_BG;
            tft.fillRect(0, rowY, PLEDIT_W, PLEDIT_ROW_H, bg);
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

        // Bottom bar
        tft.fillRect(0, PLEDIT_BOTTOM_Y, PLEDIT_W, PLEDIT_BOTTOM_H,
                     (uint16_t)PLEDIT_BODY_BG);
    }
};
