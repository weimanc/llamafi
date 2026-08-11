#pragma once
// localPlayerApp.h — AppId::LocalPlayer, the SD-backed third player mode.
//
// TASK-413 wired the mode into the shell (enum, taskbar cycle, taskbar
// assertion, debug surface); TASK-414 wired its eject verb; TASK-415 (this
// file's current scope) gives it its first real content: an M3U playlist read
// off the SD card, rendered through the one shared PLEDIT renderer, with
// tap-to-play against the system audio engine's FILE arm.
//
// What is deliberately NOT here yet, so the seams stay honest:
//   * the modal file browser and "eject = open browser"     — TASK-416
//   * shuffle/repeat/seek zones (the capability mask)       — TASK-417
//   * the play-order engine and auto-advance                — TASK-418
//   * PLEDIT edit mode, save/restore (CAP_REORDER etc.)     — TASK-420/421
// The source below therefore advertises CAP_PLAY only, and the renderer hides
// every control it does not advertise (ADR-059 D4).
//
// Concurrency: everything here runs on loopTask. The playlist File handle and
// the audio decoder's own handle are the two slots the boot mount is sized for
// (main.cpp's kSdMaxFiles = 2) — the browser's third handle is TASK-416's
// problem, together with the mount-size bump it needs.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <SD.h>
#include <esp_heap_caps.h>

#include "appShell.h"
#include "audio/audioEngine.h"
#include "gen/shell_layout.h"
#include "logSink.h"
#include "player/m3u.h"
#include "settingsStorage.h"
#include "winamp/winampDisplay.h"

extern TFT_eSPI tft;
extern WinampDisplay winampDisplay;
extern bool sdReady();   // main.cpp — the boot mount's outcome (TASK-408)

class LocalPlayerApp : public App {
public:
    // ── The playlist as a PlaylistSource (ADR-059 D4) ──────────────────────
    // Nested, like WebRadio's StationListSource and for the same reason: the
    // state it renders lives on the app object, and there is no snapshot-copy
    // seam (the Spotify path's QueueSnapshot) to read instead.
    class LocalPlaylistSource : public PlaylistSource {
    public:
        void bind(LocalPlayerApp* app) { _app = app; }

        uint16_t count()    override { return _app ? _app->_pl.count() : 0; }
        uint32_t seqno()    override { return _app ? _app->_plSeqno : 0; }
        uint32_t totalSec() override { return _app ? _app->_pl.totalSec() : 0; }
        // CAP_PLAY only until TASK-420 lands edit mode. The renderer hides the
        // controls it isn't told about rather than trusting a default-false
        // mutator, so this is the whole gate on editing being reachable.
        uint8_t  caps()     override { return CAP_PLAY; }

        bool row(uint16_t idx, PlRow& out) override {
            if (!_app || idx >= _app->_pl.count()) return false;
            _app->_pl.rowText(idx, out.text, sizeof(out.text));
            out.durationSec = _app->_pl.durationAt(idx);
            out.current     = (_app->_curRow >= 0 && idx == (uint16_t)_app->_curRow);
            // Same right-column contract as the Spotify queue: the row's own
            // "M:SS" in the row's fg colour. An M3U without #EXTINF has no
            // duration at all — an empty right column, not a bogus "0:00".
            if (out.durationSec > 0) {
                snprintf(out.rightText, sizeof(out.rightText), "%lu:%02lu",
                         (unsigned long)(out.durationSec / 60),
                         (unsigned long)(out.durationSec % 60));
            } else {
                out.rightText[0] = '\0';
            }
            out.rightColor = 0;
            return true;
        }

        // Total playlist time in the bottom bar, Spotify's format (D10). Zero
        // when no entry carried an #EXTINF duration — "0:00" is the honest
        // answer there: the durations are genuinely unknown, and reading 256
        // ID3 headers to synthesise them is TASK-419's problem, not a repaint's.
        void overlayText(char* buf, size_t bufSize) override {
            const uint32_t total = totalSec();
            const uint32_t h = total / 3600, m = (total % 3600) / 60, s = total % 60;
            if (h > 0) snprintf(buf, bufSize, "%lu:%02lu:%02lu",
                                (unsigned long)h, (unsigned long)m, (unsigned long)s);
            else       snprintf(buf, bufSize, "%lu:%02lu",
                                (unsigned long)m, (unsigned long)s);
        }

        void onTap(uint16_t idx) override { if (_app) _app->_playRow(idx); }

        // D13: unlike Spotify's queue (a new list every poll), this list only
        // changes when the user loads a different playlist — and the seqno also
        // advances on a current-row change, which must not throw the user's
        // scroll position away. load() re-anchors the scroll explicitly.
        bool resetScrollOnChange() override { return false; }

    private:
        LocalPlayerApp* _app = nullptr;
    };

    // ── Lifecycle ──────────────────────────────────────────────────────────

    void init() override {
        _src.bind(this);
        // No allocation here: a compiled-in-but-never-entered mode must cost
        // nothing but flash (design §10). resume() acquires.
    }

    void resume() override {
        winampDisplay.pleditScrollToRow(0);
        strlcpy(_playlistSaved, g_settings.playerPlaylist, sizeof(_playlistSaved));
        _playlistDirty = false;
        _eofSeen = aeEofCount();   // a previous session's eof is not ours
        if (!_pl.allocated() && !_pl.alloc()) {
            _err = true;                      // degraded; tick() paints the reason
            _dirty = true;
            return;
        }
        _err = false;
        // Restore the last playlist. Nothing can *choose* one until the browser
        // lands (TASK-416), so the persisted path is either what a previous
        // session loaded or the debug surface's `set plLoad`.
        if (g_settings.playerPlaylist[0]) _load(g_settings.playerPlaylist);
        _dirty = true;
    }

    void suspend() override {
        // Cancel live gestures — the PLEDIT drag and the shared volume-drag
        // machine are global state; a mode switch mid-drag must not leave
        // either armed (TASK-352 / TASK-277 precedent).
        winampDisplay.resetDragState();
        // Stop and fully release the engine: pump task, Audio, arena. Leaving
        // the arena held would silently starve WebRadio's next station fetch
        // and Spotify's TLS of contiguous heap.
        if (_playing || _connecting) aeTeardownFile(_connecting);
        _playing = _connecting = false;
        _curRow = -1;
        // Free the index and close the playlist File — the whole point of
        // heap-allocating it is that a suspended mode costs nothing (T_PLR_12).
        _pl.free();

        // ADR-050 rule 3: coalesced settings write, here and nowhere else.
        // Saving at selection time looked simpler and is wrong twice over —
        // it costs a flash write per pick, and (observed on the DUT) it FAILS
        // outright while a track is playing: SettingsStorage allocates a 6 KB
        // ArduinoJson doc, the Helix arena holds the large contiguous blocks,
        // and 8-bit-capable largest-free drops to ~2.8 KB, so the ctor alloc
        // fails, capacity is 0 and the TASK-329 guard aborts the save. By
        // suspend() the engine is torn down and the arena released, so the
        // allocation succeeds. See TASK-429.
        if (_playlistDirty) {
            if (strcmp(g_settings.playerPlaylist, _playlistSaved) != 0) SettingsStorage::save();
            strlcpy(_playlistSaved, g_settings.playerPlaylist, sizeof(_playlistSaved));
            _playlistDirty = false;
        }
    }

    void tick() override {
        // Reconcile the pump task's async connect outcome. This app polls it
        // itself rather than leaving it parked: s_wrPumpResult is a single
        // shared slot, and a FILE-arm result left unconsumed would be picked
        // up by WebRadioApp::tick() on the next mode switch and applied to a
        // stream connect that never happened.
        {
            const WrPumpResult r = s_wrPumpResult;
            if (r != WrPumpResult::NONE) {
                if (r == WrPumpResult::CONNECTED) {
                    _playing = true;
                    LOG_I("localplayer", "playing row %d", _curRow);
                } else {
                    _playing = false;
                    if (r == WrPumpResult::FAILED) {
                        _err = true;
                        LOG_W("localplayer", "play FAILED row %d", _curRow);
                    }
                }
                _connecting = false;
                s_wrPumpResult = WrPumpResult::NONE;
                _dirty = true;
                _plSeqno++;               // the "current" row highlight changed
            }
        }

        // End of track. Auto-advance is TASK-418; for now the row simply stops
        // being current, so the display doesn't claim to be playing something
        // that finished minutes ago.
        if (_eofSeen != aeEofCount()) {
            _eofSeen = aeEofCount();
            if (_playing) {
                _playing = false;
                _curRow  = -1;
                _plSeqno++;
                _dirty = true;
                LOG_I("localplayer", "track ended (auto-advance is TASK-418)");
            }
        }

        // Velocity-scroll integrator, dt-integrated (M-LIST-v4 OQ1), before any
        // early return below can stall a live gesture.
        {
            const unsigned long now = millis();
            const float dt = (_lastScrollMs == 0) ? 0.0f : (now - _lastScrollMs) * 0.001f;
            _lastScrollMs = now;
            winampDisplay.tickScroll(dt);
        }

        // Drop the playlist File once a read burst has ended. See
        // PlaylistIndex::closeIfIdle() — an open handle costs ~4.4 KB of newlib
        // stdio buffer, more than the whole index, and a static list needs none
        // of it. 1.5 s spans the gap between repaints during a velocity scroll
        // (which repaints continuously) without holding the handle while the
        // user just looks at the screen.
        _pl.closeIfIdle(1500);

        if (_dirty) {
            _dirty = false;
            _drawFull();
        }
        // Unconditional, like SpotifyApp/WebRadioApp: the shared view owns its
        // own seqno/scroll redraw gate and decides whether this is a repaint.
        winampDisplay.drawPlaylistFor(_src);
    }

    bool hasError() const override { return _err; }
    // The connect runs on the pump task, not on a dataTask fetch — but the
    // taskbar's connecting indicator is the honest signal for it, same as
    // WebRadio's.
    bool isConnecting() const override { return _connecting; }

    // ── Input ──────────────────────────────────────────────────────────────

    bool handleInput(TouchPhase phase, int x, int y) override {
        // NOTE: no handleVolumeGesturePublic() call. The shared volume-drag
        // machine commits through a sink that still defaults to Spotify's
        // ACT_VOLUME, so wiring it here would send Spotify volume commands
        // from Player mode. Volume (and shuffle/repeat/seek) become real for
        // this mode in TASK-417's capability mask, with a Player sink.

        // Captured PLEDIT gesture wins over every hit-test — Release must end
        // the drag before eject/transport get a look (the DEV-1-1 ordering).
        if (winampDisplay.pleditDragging()) {
            if (phase == TouchPhase::Release) {
                const PlReleaseResult r = winampDisplay.pleditRelease(_src);
                if (r.cooldownMs) winampDisplay.armTouchCooldown(r.cooldownMs);
                return true;
            }
            winampDisplay.pleditMove(y);
            return true;
        }

        if (phase == TouchPhase::Press) {
            if (winampDisplay.touchCoolingDown()) return false;
            if (winampDisplay.pleditPress(x, y)) return true;
            return false;
        }
        if (phase != TouchPhase::Release) return false;

        // TASK-414 / ADR-059 D6: eject means "load media from this source" —
        // for Player that is the file browser. Still a stub (TASK-416), but a
        // reload of the persisted playlist is a strictly better placeholder
        // than a log line: it is the same verb, just without the picker.
        if (winampDisplay.hitTestEject(x, y)) {
            LOG_I("localplayer", "eject tap → file browser (stub, TASK-416): reloading %s",
                  g_settings.playerPlaylist[0] ? g_settings.playerPlaylist : "(none)");
            if (g_settings.playerPlaylist[0]) _load(g_settings.playerPlaylist);
            return true;
        }

        // Transport. PREV/NEXT are the play-order engine's (TASK-418) and are
        // inert here rather than fake — a "next" that jumps to viewOrder[i+1]
        // would have to be un-taught the moment the shuffle bag exists.
        const int t = winampDisplay.hitTestTransportPublic(x, y);
        if (t == 1) {                                  // PLAY
            if (!_playing && _pl.count() > 0) _playRow(_curRow >= 0 ? (uint16_t)_curRow : 0);
            return true;
        }
        if (t == 2 || t == 3) {                        // PAUSE / STOP
            if (_playing || _connecting) {
                aeStopFile(_connecting);
                _playing = _connecting = false;
                _curRow  = -1;
                _plSeqno++;
                _dirty = true;
            }
            return true;
        }
        return false;
    }

#ifdef SERIAL_DEBUG
    // ── Debug surface (ADR-059 D12: shipped with the feature) ──────────────
    // `set plLoad <path>` is the only way to choose a playlist until the
    // browser lands, and `get plCount` / `get plRow` / `get plMem` are the
    // observables T_PLR_08–12 assert on.
    bool dbgLoad(const char* path) {
        if (!_pl.allocated() && !_pl.alloc()) return false;
        const bool ok = _load(path);
        if (ok) _rememberPlaylist(path);
        return ok;
    }
    void dbgReport() const {
        Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plCount\","
                      "\"path\":\"%s\",\"count\":%u,\"loadMs\":%lu,\"totalSec\":%lu,"
                      "\"truncated\":%s,\"error\":%s,\"curRow\":%d,\"playing\":%s,"
                      "\"last\":true}\n",
                      _pl.path(), (unsigned)_pl.count(), (unsigned long)_pl.loadMs(),
                      (unsigned long)_pl.totalSec(),
                      _pl.truncated() ? "true" : "false",
                      _pl.error() ? "true" : "false",
                      _curRow, _playing ? "true" : "false");
    }
    void dbgRow(uint16_t idx) {
        if (idx >= _pl.count()) {
            Serial.printf("{\"ok\":false,\"cmd\":\"get\",\"var\":\"plRow\","
                          "\"idx\":%u,\"error\":\"out of range\",\"count\":%u}\n",
                          (unsigned)idx, (unsigned)_pl.count());
            return;
        }
        char text[64], path[m3u::PL_PATH_MAX];
        _pl.rowText(idx, text, sizeof(text));
        if (!_pl.pathAt(idx, path, sizeof(path))) strlcpy(path, "", sizeof(path));
        Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plRow\",\"idx\":%u,"
                      "\"id\":%u,\"text\":\"%s\",\"durSec\":%u,\"path\":\"%s\",\"last\":true}\n",
                      (unsigned)idx, (unsigned)_pl.idAt(idx), text,
                      (unsigned)_pl.durationAt(idx), path);
    }
    // T_PLR_12 (VE-15): largest-free-block alongside free heap — a clean
    // free-heap figure hides fragmentation, which is the real risk here.
    void dbgMem() const {
        Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plMem\","
                      "\"allocated\":%s,\"indexBytes\":%u,\"freeHeap\":%u,"
                      "\"largestBlock\":%u,\"minFreeHeap\":%u,\"last\":true}\n",
                      _pl.allocated() ? "true" : "false",
                      (unsigned)m3u::PlaylistIndex::bytes(),
                      (unsigned)ESP.getFreeHeap(),
                      (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                      (unsigned)ESP.getMinFreeHeap());
    }
    bool dbgPlayRow(uint16_t idx) {
        if (idx >= _pl.count()) return false;
        _playRow(idx);
        return true;
    }
#endif

private:
    // RAM-only; the flash write is coalesced into suspend(). See the comment there.
    void _rememberPlaylist(const char* path) {
        strlcpy(g_settings.playerPlaylist, path, sizeof(g_settings.playerPlaylist));
        _playlistDirty = true;
    }

    bool _load(const char* path) {
        if (!sdReady()) {
            LOG_W("localplayer", "no SD card mounted — cannot load %s", path);
            _err = true;
            _dirty = true;
            return false;
        }
        const bool ok = _pl.load(path);
        _err    = !ok;
        _curRow = -1;
        _plSeqno++;
        _dirty  = true;
        // A different playlist is a different list: re-anchor the scroll here
        // rather than through resetScrollOnChange(), which would also fire on
        // every current-row change.
        winampDisplay.pleditScrollToRow(0);
        return ok;
    }

    void _playRow(uint16_t idx) {
        if (idx >= _pl.count()) return;
        char path[m3u::PL_PATH_MAX];
        if (!_pl.pathAt(idx, path, sizeof(path))) {
            LOG_W("localplayer", "row %u has no readable path", (unsigned)idx);
            _err = true;
            return;
        }
        // Tapping a new row while one plays: stop first, so the engine isn't
        // asked to connect on top of a live decode.
        if (_playing || _connecting) aeStopFile(_connecting);
        LOG_I("localplayer", "play row %u: %s", (unsigned)idx, path);
        if (!aeConnectFile(path)) { _err = true; return; }
        _curRow     = (int)idx;
        _connecting = true;
        _playing    = false;
        _err        = false;
        _plSeqno++;
        _dirty      = true;
    }

    void _drawFull() {
        // repaintChrome() redraws the volume slider from whatever pct was last
        // cached — possibly Spotify's or WebRadio's, from before the switch.
        // WebRadio re-seeds it here with its own persisted value; Player has no
        // volume of its own until TASK-417 gives the mode a volume sink, so it
        // deliberately inherits rather than inventing a third stored value.
        winampDisplay.repaintChrome();
        _drawTitle();
    }

    void _drawTitle() {
        char buf[64];
        if (_err && _pl.count() == 0) {
            snprintf(buf, sizeof(buf), "%s", sdReady() ? "No playlist" : "No SD card");
        } else if (_pl.count() == 0) {
            snprintf(buf, sizeof(buf), "No playlist");
        } else if (_curRow >= 0) {
            char text[64];
            _pl.rowText((uint16_t)_curRow, text, sizeof(text));
            snprintf(buf, sizeof(buf), "%s%s", _connecting ? "Opening: " : "", text);
        } else {
            const char* slash = strrchr(_pl.path(), '/');
            snprintf(buf, sizeof(buf), "%s (%u)", slash ? slash + 1 : _pl.path(),
                     (unsigned)_pl.count());
        }
        winampDisplay.setTitle(buf);
    }

    m3u::PlaylistIndex  _pl;
    LocalPlaylistSource _src;
    uint32_t      _plSeqno    = 1;    // never 0 — the view's gate starts at 0
    int           _curRow     = -1;
    bool          _playing    = false;
    bool          _connecting = false;
    bool          _err        = false;
    bool          _dirty      = true;
    unsigned long _lastScrollMs = 0;
    uint32_t      _eofSeen    = 0;
    bool          _playlistDirty = false;
    char          _playlistSaved[64] = {0};
};
