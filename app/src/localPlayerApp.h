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
#include "player/fileBrowser.h"
#include "player/m3u.h"
#include "settingsStorage.h"
#include "winamp/winampDisplay.h"

extern TFT_eSPI tft;
extern WinampDisplay winampDisplay;
extern bool sdReady();   // main.cpp — the boot mount's outcome (TASK-408)

// TASK-417 / ADR-059 D8/D9 — winampDisplay's shuffle/repeat commit seams
// (setShuffleSink()/setRepeatSink()/setSeekSink(), mirrors TASK-352's
// setVolumeSink()) for Player mode. State is instance-free, file-scope: no
// play-order bag exists yet to attach it to (TASK-418), and no persistence
// yet (also TASK-418/D9's job — this task only un-gates the zones). Repeat
// deliberately reuses the shipped tri-state domain but Player only ever
// emits 2 (off) or 0 (repeat-all) per D9's binary domain.
static bool   s_plShuffleOn   = false;
static int8_t s_plRepeatState = 2;   // 2=off, 0=repeat-all
static void playerShuffleSink(int next) { s_plShuffleOn = (next != 0); }
static void playerRepeatSink(int next)  { s_plRepeatState = (next == 2) ? 2 : 0; }
static void playerSeekSink(long ms) {
    // TASK-419 wires this to the vendored Audio's setFilePos()/
    // setTimeOffset(). Until then the zone is capability-gated and
    // hit-testable (T_PLR_19) but the seek itself is a documented no-op —
    // real duration-accurate scrubbing is that task's own gate (T_PLR_27/28).
    (void)ms;
}

class LocalPlayerApp : public App, public player::FileBrowser::Delegate {
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
        _browser.bind(this);
        // No allocation here: a compiled-in-but-never-entered mode must cost
        // nothing but flash (design §10). resume() acquires.

        // TASK-417 / ADR-059 D8: switchApp() (main.cpp) calls init() XOR
        // resume() — never both — on an AppId's first-ever entry each boot
        // session (`if (!g_appLaunched[next]) init(); else resume();`).
        // Wiring caps/sinks only in resume() (as first written) left the
        // WinampDisplay defaults (all four caps, Spotify's sinks) live for
        // Player's first-ever session each boot — caps happened to read
        // correct by coincidence (Player wants all four too) but the sinks
        // did not: a first-session shuffle/repeat tap would have dispatched
        // to spotifyTask::ACT_SHUFFLE/ACT_REPEAT instead of this file's own
        // sinks. Same wiring as resume(), duplicated rather than factored,
        // to keep this diff small.
        winampDisplay.setPlayerCaps(CAP_TRANSPORT | CAP_SEEK | CAP_SHUFFLE | CAP_REPEAT);
        winampDisplay.setShuffleSink(&playerShuffleSink);
        winampDisplay.setRepeatSink(&playerRepeatSink);
        winampDisplay.setSeekSink(&playerSeekSink);
    }

    void resume() override {
        // TASK-417 / ADR-059 D8: Player advertises all four capabilities.
        // Wire the shuffle/repeat/seek commit seams to this file's
        // instance-free state (above) so the shared dispatch path (used by
        // SERIAL_DEBUG's injectTouch() as a side channel regardless of
        // which app is active) never leaks a spotifyTask::ACT_SHUFFLE/
        // ACT_REPEAT/ACT_SEEK enqueue while Player is the active app.
        winampDisplay.setPlayerCaps(CAP_TRANSPORT | CAP_SEEK | CAP_SHUFFLE | CAP_REPEAT);
        winampDisplay.setShuffleSink(&playerShuffleSink);
        winampDisplay.setRepeatSink(&playerRepeatSink);
        winampDisplay.setSeekSink(&playerSeekSink);
        // Seed the sprites from this mode's own state rather than whatever
        // repaintChrome()'s shared cache last held (D8: "rendered state
        // sourced from the mode, not from spotifyTask::Snapshot").
        winampDisplay.drawShuffle(s_plShuffleOn ? 1 : 0);
        winampDisplay.drawRepeat(s_plRepeatState);
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
        // TASK-433 revision: an earlier version of this fix eagerly claimed
        // the browser's arrays here on every resume(), on the theory that
        // grabbing them as early as possible beats later fragmentation.
        // Measured cost on the DUT: it claims the block on the FIRST-EVER
        // Player-mode entry of the whole boot session, which starves the
        // m3u playlist index (`_pl`, above) for the REST of the session —
        // `[m3u] index alloc FAILED` went 0 -> 15 in a full-suite run,
        // failing T_PLR_11/12 (T_PLR_12's ±256 B residual budget is a hard
        // acceptance line, not a suggestion). Reverted: the browser now
        // stays lazily allocated at first `open()` (eject tap or `set
        // fbOpen`), same as before this task, so a Player-mode session that
        // never opens the browser costs the m3u index nothing extra. It
        // still never frees once opened — see suspend() below.
    }

    void suspend() override {
        // Cancel live gestures — the PLEDIT drag and the shared volume-drag
        // machine are global state; a mode switch mid-drag must not leave
        // either armed (TASK-352 / TASK-277 precedent).
        winampDisplay.resetDragState();
        // TASK-433: do NOT free the browser's 5 120 B here (was: _browser.free(),
        // same discipline as _pl below). Measured cause of the suite-state-
        // dependent fbOpen failure: suspend()/resume() fires around every mode
        // switch, so free-then-realloc asks for a 4 096 B contiguous block
        // against whatever the heap looks like at that moment — `largestBlock`
        // was measured as low as 756 B after a realistic test sequence, well
        // under the ask, while total free heap still read a healthy 50 016 B
        // (BP-055). Allocate once (resume(), below) and hold for the rest of
        // the boot session instead — the arrays are cheap (5 120 B) and the
        // alternative is an alloc that can fail at any mode switch for the
        // life of the session. Still fully closes the open directory handle
        // and hides the picker (_closeDir()/_picker.hide() inside free()'s
        // sibling _cancel-shaped cleanup — see open()/handleInput()), just
        // keeps the two heap arrays resident. Cost: 5 120 B permanently taken
        // from the shared internal-8-bit pool from the first Player-mode
        // entry onward — see the TASK-433 writeup in tasks.md for the margin
        // this leaves WebRadio's 24 576 B arena grab.
        _browser.cancel();
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
        // TASK-416: continue any in-flight directory walk (≤FB_BATCH entries
        // — see fileBrowser.h). Cheap no-op when the browser isn't Walking.
        _browser.tick();
        // The browser owns the whole canvas while active (CP-1, same contract
        // as g_countryPicker) — force a full repaint the tick after it
        // closes, since its SPickerList painted over the player screen.
        const bool browserActive = _browser.active();
        if (_browserWasActive && !browserActive) {
            _dirty = true;
            winampDisplay.invalidatePlaylist();
        }
        _browserWasActive = browserActive;

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
                _direct  = false;
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

        // TASK-416: the browser is modal and owns the canvas — its own
        // repaint/updateCount() calls are its rendering, not this one's.
        if (browserActive) return;

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

    // TASK-416 / NEW-APP-CHECKLIST item 1: true while a browser page read is
    // in flight — self-clears when the walk finishes (fileBrowser.h's tick()
    // flips its own state, this just observes it).
    bool hasPendingAsync() const override { return _browser.pending(); }

    // TASK-416 / NEW-APP-CHECKLIST item 4, TASK-384 precedent: except the
    // browser's own back/up zone from the shell busy gate, or a tap there
    // while a page walk is in flight is silently dropped — confirmed on real
    // hardware to feel broken in a way the harness alone would not catch.
    bool isNavigationTap(int x, int y) const override {
        return _browser.active() && _browser.isBackZone(x, y);
    }

    // ── Input ──────────────────────────────────────────────────────────────

    bool handleInput(TouchPhase phase, int x, int y) override {
        // TASK-416: the browser is modal (CP-1, same contract as
        // g_countryPicker) — it owns every touch phase while active, ahead of
        // PLEDIT/eject/transport, exactly like AppsSection forwards to
        // g_countryPicker before its own tap logic.
        if (_browser.active()) {
            _browser.handleInput(phase, x, y);
            return true;
        }

        // NOTE: no handleVolumeGesturePublic() call. The shared volume-drag
        // machine commits through a sink that still defaults to Spotify's
        // ACT_VOLUME, so wiring it here would send Spotify volume commands
        // from Player mode. Volume stays deliberately out of scope here —
        // TASK-417's task statement says handleVolumeGesturePublic() is
        // retirable but explicitly "in its own commit" (it shares the
        // D_VOLUME_DRAG machine with TASK-352, and WebRadio's volume path
        // already cost TASK-406 a real bug). Shuffle/repeat/seek are NOT
        // part of that machine — TASK-417 wires them below via
        // winampDisplay's capability-gated hit-tests + this file's own sinks.

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
            // TASK-417 / ADR-059 D8: shuffle/repeat/seek, dispatched on
            // Press to match Spotify's own immediate-feedback timing
            // (handleWinampInput() dispatches these on Press too). Deliberately
            // NOT duplicated in the Release branch below — SERIAL_DEBUG's
            // cmdTap drives Player taps via injectTouch() (a Press against
            // the shared handleWinampInput(), capability-gated + sunk to
            // this file's sinks — see resume()) followed by a real Release
            // against this handler; dispatching here-only means each tap
            // fires exactly once regardless of which path drove it.
            const uint8_t caps = winampDisplay.playerCaps();
            if ((caps & CAP_SHUFFLE) && winampDisplay.hitTestShufflePublic(x, y)) {
                int next = (winampDisplay.getLastShuffleRendered() == 1) ? 0 : 1;
                winampDisplay.drawShuffle(next);
                playerShuffleSink(next);
                winampDisplay.armTouchCooldown(250);
                return true;
            }
            if ((caps & CAP_REPEAT) && winampDisplay.hitTestRepeatPublic(x, y)) {
                // D9: binary domain — only 2 (off) / 0 (repeat-all) are
                // meaningful for Player, unlike Spotify's tri-state cycle.
                int next = (winampDisplay.getLastRepeatRendered() == 2) ? 0 : 2;
                winampDisplay.drawRepeat(next);
                playerRepeatSink(next);
                winampDisplay.armTouchCooldown(250);
                return true;
            }
            if ((caps & CAP_SEEK) && winampDisplay.hitTestPosbarZonePublic(x, y)) {
                // TASK-419 wires the real scrub against the playing file's
                // actual duration; this only proves the zone is reachable
                // (T_PLR_19) instead of falling through to the dead zone.
                playerSeekSink(0);
                return true;
            }
            return false;
        }
        if (phase != TouchPhase::Release) return false;

        // TASK-414/416 / ADR-059 D6: eject means "load media from this
        // source" — for Player that is the file browser. Starts from the
        // loaded playlist's directory if there is one (a browse session
        // after loading a playlist should land where that playlist lives,
        // not at the card root), else the last-browsed directory, else root.
        if (winampDisplay.hitTestEject(x, y)) {
            const char* startDir = _pl.count() > 0 ? _pl.dir()
                                  : (_lastBrowseDir[0] ? _lastBrowseDir : "/");
            LOG_I("localplayer", "eject tap -> file browser: %s", startDir);
            if (!_browser.open(startDir)) {
                _err = true;
                _dirty = true;
            }
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
                _direct  = false;
                _plSeqno++;
                _dirty = true;
            }
            return true;
        }
        return false;
    }

    // ── player::FileBrowser::Delegate ─────────────────────────────────────
    // The browser resolves the tap to a full path and tells us what kind of
    // file it was; playback/loading policy stays here, not in fileBrowser.h.

    void fbPlayFile(const char* path) override {
        strlcpy(_lastBrowseDir, _browser.dir(), sizeof(_lastBrowseDir));
        _playPathDirect(path);
    }

    void fbLoadPlaylist(const char* path) override {
        strlcpy(_lastBrowseDir, _browser.dir(), sizeof(_lastBrowseDir));
        if (!_pl.allocated() && !_pl.alloc()) { _err = true; _dirty = true; return; }
        if (_load(path)) _rememberPlaylist(path);
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
    // TASK-416 (ADR-059 D12): drives the browser from the harness — T_PLR_13-16
    // need to open big/nested/empty directories and select rows deterministically,
    // not just via injected taps.
    bool dbgFbOpen(const char* path)   { return _browser.open(path); }
    bool dbgFbSelect(int16_t idx)      { return _browser.dbgSelect(idx); }
    bool dbgFbCancel()                 { return _browser.dbgCancel(); }
    void dbgFbState() const            { _browser.dbgReport(); }
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
        _direct     = false;   // a playlist row, not a browser-direct file
        _connecting = true;
        _playing    = false;
        _err        = false;
        _plSeqno++;
        _dirty      = true;
    }

    // TASK-416: playing a file tapped straight out of the browser, not
    // through the loaded playlist's index — _curRow stays -1 (no playlist row
    // "is" this track; PLEDIT correctly shows no current-row highlight) and
    // _direct + _directPath carry what the title bar needs instead.
    void _playPathDirect(const char* path) {
        if (_playing || _connecting) aeStopFile(_connecting);
        LOG_I("localplayer", "play (direct): %s", path);
        if (!aeConnectFile(path)) { _err = true; _dirty = true; return; }
        strlcpy(_directPath, path, sizeof(_directPath));
        _direct     = true;
        _curRow     = -1;
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
        if (_direct) {
            const char* slash = strrchr(_directPath, '/');
            snprintf(buf, sizeof(buf), "%s%s", _connecting ? "Opening: " : "",
                     slash ? slash + 1 : _directPath);
        } else if (_err && _pl.count() == 0) {
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

    m3u::PlaylistIndex     _pl;
    LocalPlaylistSource    _src;
    player::FileBrowser    _browser;
    bool          _browserWasActive = false;
    char          _lastBrowseDir[m3u::PL_PATH_MAX] = {0};
    bool          _direct     = false;   // playing a browser-tapped file, not a playlist row
    char          _directPath[m3u::PL_PATH_MAX] = {0};
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
