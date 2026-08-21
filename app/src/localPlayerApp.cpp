// localPlayerApp.cpp — LocalPlayerApp method bodies, out-of-line (M-SRCLAYOUT Stage E).
#include "localPlayerApp.h"

// TASK-418: the toggle/state booleans and the active-instance pointer stay
// file-scope, private to this TU (never referenced outside localPlayerApp.h/
// cpp) — see localPlayerApp.h's comment above the forward declarations.
static LocalPlayerApp* s_activeLocalPlayer = nullptr;
static bool   s_plShuffleOn   = false;
static int8_t s_plRepeatState = 2;   // 2=off, 0=repeat-all

void LocalPlayerApp::init() {
    _src.bind(this);
    _browser.bind(this);
    // No allocation here: a compiled-in-but-never-entered mode must cost
    // nothing but flash (design §10). resume() acquires.

    // TASK-417 / ADR-059 D8: switchApp() (main.cpp) calls init() XOR
    // resume() — never both — on an AppId's first-ever entry each boot
    // session (`if (!shell::state().launched[next]) init(); else resume()`).
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
    // TASK-418: the sinks above need a live instance to reach the bag —
    // see s_activeLocalPlayer's comment. Duplicated in resume() below,
    // same discipline as the caps/sink wiring it sits next to.
    s_activeLocalPlayer = this;
    s_plShuffleOn   = g_settings.playerShuffle;
    s_plRepeatState = (g_settings.playerRepeat == 0) ? 0 : 2;
}

void LocalPlayerApp::resume() {
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
    // TASK-418: same instance wiring as init() above.
    s_activeLocalPlayer = this;
    s_plShuffleOn   = g_settings.playerShuffle;
    s_plRepeatState = (g_settings.playerRepeat == 0) ? 0 : 2;
    // Seed the sprites from this mode's own state rather than whatever
    // repaintChrome()'s shared cache last held (D8: "rendered state
    // sourced from the mode, not from spotifyTask::Snapshot").
    winampDisplay.drawShuffle(s_plShuffleOn ? 1 : 0);
    winampDisplay.drawRepeat(s_plRepeatState);
    winampDisplay.pleditScrollToRow(0);
    strlcpy(_playlistSaved, g_settings.playerPlaylist, sizeof(_playlistSaved));
    _playlistDirty = false;
    _shuffleSaved = g_settings.playerShuffle;
    _repeatSaved  = g_settings.playerRepeat;
    _shuffleRepeatDirty = false;
    _playCursor = -1;
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

void LocalPlayerApp::suspend() {
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
    _playCursor = -1;
    // Free the index and close the playlist File — the whole point of
    // heap-allocating it is that a suspended mode costs nothing (T_PLR_12).
    _pl.free();
    // s_activeLocalPlayer is only meaningful while this instance is the
    // live mode — the sinks above no-op harmlessly if a tap somehow
    // reaches them while it's null, rather than mutating a torn-down bag.
    s_activeLocalPlayer = nullptr;

    // ADR-050 rule 3: coalesced settings write, here and nowhere else.
    // Saving at selection time looked simpler and is wrong twice over —
    // it costs a flash write per pick, and (observed on the DUT) it FAILS
    // outright while a track is playing: SettingsStorage allocates a 6 KB
    // ArduinoJson doc, the Helix arena holds the large contiguous blocks,
    // and 8-bit-capable largest-free drops to ~2.8 KB, so the ctor alloc
    // fails, capacity is 0 and the TASK-329 guard aborts the save. By
    // suspend() the engine is torn down and the arena released, so the
    // allocation succeeds. See TASK-429.
    //
    // TASK-418: shuffle/repeat ride the same coalesced write — g_settings
    // is updated live by onShuffleToggled()/onRepeatChanged() (RAM only),
    // this is the one place any of it reaches flash. One save() call for
    // both, not one each — either dirty flag can trip it.
    if (_playlistDirty || _shuffleRepeatDirty) {
        const bool changed = strcmp(g_settings.playerPlaylist, _playlistSaved) != 0
                           || g_settings.playerShuffle != _shuffleSaved
                           || g_settings.playerRepeat  != _repeatSaved;
        if (changed) SettingsStorage::save();
        strlcpy(_playlistSaved, g_settings.playerPlaylist, sizeof(_playlistSaved));
        _shuffleSaved = g_settings.playerShuffle;
        _repeatSaved  = g_settings.playerRepeat;
        _playlistDirty = _shuffleRepeatDirty = false;
    }
    SettingsStorage::tickDeferredSave(/*force=*/true);   // TASK-429 (b)
}

void LocalPlayerApp::tick() {
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
                    // TASK-450: give the engine back. A failed connect used
                    // to leave the Audio object, its 6 400 B InBuff and the
                    // pump task resident — DUT-measured 2026-08-15: lfb8 sat
                    // at 22 516 for 120 s instead of returning to its 61 428
                    // baseline, so a retry began from a worse heap than the
                    // attempt that had just failed. On a marginal build that
                    // turns one recoverable failure into a permanent one.
                    //
                    // aeTeardownFile(false) is the same call suspend() makes,
                    // and every step inside it is individually guarded
                    // (wrTeardownPumpTask() no-ops without a pump, the delete
                    // is null-checked, mb_arena_release() early-returns when
                    // unheld) — so it is safe on the paths that failed BEFORE
                    // standing anything up, e.g. the tlsTryYield timeout. It
                    // also resumes Spotify TLS via aeStopFile(), which that
                    // early-return path would otherwise leave yielded.
                    aeTeardownFile(/*connecting=*/false);
                }
            }
            _connecting = false;
            s_wrPumpResult = WrPumpResult::NONE;
            _dirty = true;
            _plSeqno++;               // the "current" row highlight changed
        }
    }

    // End of track. aeDrainEof() (audioEngine.h) already asserted this
    // runs on loopTask before incrementing s_aeEofCount — this poll is
    // itself only ever reached from tick(), which is loopTask-only, so
    // everything below (the bag, _pl, _curRow) is touched on the same
    // task the design requires (§8, ADR-059 D9: "the bag lives in
    // loopTask-owned state and must not be mutated from the pump task").
    if (_eofSeen != aeEofCount()) {
        _eofSeen = aeEofCount();
        if (_playing) {
            if (_direct) {
                // A browser-tapped file isn't part of any playlist queue
                // — nothing to advance to.
                _playing = false;
                _curRow  = -1;
                _direct  = false;
                _plSeqno++;
                _dirty = true;
                LOG_I("localplayer", "direct-play track ended");
            } else {
                _autoAdvance();
            }
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

bool LocalPlayerApp::handleInput(TouchPhase phase, int x, int y) {
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

    // Transport.
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
            _playCursor = -1;
            _direct  = false;
            _plSeqno++;
            _dirty = true;
        }
        return true;
    }
    // TASK-418: PREV/NEXT drive the play-order engine (§8) — model step
    // first, then start playback on whatever row it lands on (or do
    // nothing if the step reports "stopped": shuffle-off+repeat-off at
    // the last row, or shuffle-on+repeat-off at the end of one full
    // pass). A no-op here matches real Winamp: NEXT at the end of a
    // non-repeating list does not restart from the top.
    if ((t == 0 || t == 4) && _pl.count() > 0) {
        const AdvanceResult r = _stepOrder(t == 4 ? +1 : -1);
        if (r.moved) _startPlayback(r.row);
        return true;
    }
    return false;
}

void LocalPlayerApp::fbPlayFile(const char* path) {
    strlcpy(_lastBrowseDir, _browser.dir(), sizeof(_lastBrowseDir));
    _playPathDirect(path);
}

void LocalPlayerApp::fbLoadPlaylist(const char* path) {
    strlcpy(_lastBrowseDir, _browser.dir(), sizeof(_lastBrowseDir));
    if (!_pl.allocated() && !_pl.alloc()) { _err = true; _dirty = true; return; }
    if (_load(path)) _rememberPlaylist(path);
}

#ifdef SERIAL_DEBUG
bool LocalPlayerApp::dbgLoad(const char* path) {
    if (!_pl.allocated() && !_pl.alloc()) return false;
    const bool ok = _load(path);
    if (ok) _rememberPlaylist(path);
    return ok;
}

void LocalPlayerApp::dbgReport() const {
    // TASK-435 added fileOpen/lfb8 as a throwaway diagnostic marked "do not
    // commit"; it was committed (fea2978) and has since earned its place —
    // lfb8 is what measured TASK-442's 2932 B shortfall. Comment retired
    // TASK-422; these two fields are deliberate now, not leftovers:
    // fileOpen tells the caller whether closeIfIdle() has actually fired
    // yet (tick()-driven, not a timer — wall-clock waits alone don't
    // prove it), lfb8 is the same byte-addressable cap mb_arena.cpp's own
    // acquire log uses (BP-055), read here with no allocation of its own.
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plCount\","
                  "\"path\":\"%s\",\"count\":%u,\"loadMs\":%lu,\"totalSec\":%lu,"
                  "\"truncated\":%s,\"error\":%s,\"curRow\":%d,\"playing\":%s,"
                  "\"fileOpen\":%s,\"lfb8\":%u,"
                  "\"last\":true}\n",
                  _pl.path(), (unsigned)_pl.count(), (unsigned long)_pl.loadMs(),
                  (unsigned long)_pl.totalSec(),
                  _pl.truncated() ? "true" : "false",
                  _pl.error() ? "true" : "false",
                  _curRow, _playing ? "true" : "false",
                  _pl.fileOpen() ? "true" : "false",
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
}

void LocalPlayerApp::dbgRow(uint16_t idx) {
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

void LocalPlayerApp::dbgMem() const {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plMem\","
                  "\"allocated\":%s,\"indexBytes\":%u,\"freeHeap\":%u,"
                  "\"largestBlock\":%u,\"minFreeHeap\":%u,\"last\":true}\n",
                  _pl.allocated() ? "true" : "false",
                  (unsigned)m3u::PlaylistIndex::bytes(),
                  (unsigned)ESP.getFreeHeap(),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                  (unsigned)ESP.getMinFreeHeap());
}

bool LocalPlayerApp::dbgPlayRow(uint16_t idx) {
    if (idx >= _pl.count()) return false;
    _playRow(idx);
    return true;
}

void LocalPlayerApp::dbgPlayerVector() const {
    const uint16_t n = _pl.count();
    const uint16_t* pv = _pl.playOrder();
    const uint16_t* vv = _pl.viewOrder();
    uint32_t ph = 2166136261u, vh = 2166136261u;
    for (uint16_t i = 0; i < n; i++) {
        ph = (ph ^ (uint32_t)pv[i]) * 16777619u;
        vh = (vh ^ (uint32_t)vv[i]) * 16777619u;
    }
    Serial.printf("\"plCount\":%u,\"playHash\":%lu,\"viewHash\":%lu,"
                  "\"orderIdentical\":%d,",
                  (unsigned)n, (unsigned long)ph, (unsigned long)vh,
                  (int)(ph == vh));
}

void LocalPlayerApp::dbgOrder() const {
    // Streamed rather than built into one big local buffer — up to 256
    // entries would cost ~1.5 KB of loopTask stack for a single debug
    // dump, not worth it when Serial.print() does the same job a piece
    // at a time.
    const uint16_t n = _pl.count();
    const uint16_t* order = _pl.playOrder();
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plOrder\","
                  "\"count\":%u,\"order\":[", (unsigned)n);
    for (uint16_t i = 0; i < n; i++) {
        if (i) Serial.print(',');
        Serial.print((unsigned)order[i]);
    }
    Serial.println("],\"last\":true}");
}

void LocalPlayerApp::dbgCursor() const {
    Serial.printf("{\"ok\":true,\"cmd\":\"get\",\"var\":\"plCursor\","
                  "\"cursor\":%d,\"curRow\":%d,\"shuffle\":%s,\"repeat\":%d,"
                  "\"last\":true}\n",
                  _playCursor, _curRow, s_plShuffleOn ? "true" : "false",
                  (int)s_plRepeatState);
}

bool LocalPlayerApp::dbgSetCursor(int n) {
    const uint16_t count = _pl.count();
    if (count == 0) return false;
    if (n < 0) n = 0;
    if (n >= (int)count) n = (int)count - 1;
    _playCursor = n;
    _syncCurRowFromCursor();
    _plSeqno++;
    _dirty = true;
    return true;
}

void LocalPlayerApp::dbgAdvance(bool next, bool* moved, uint16_t* row, bool* reshuffled) {
    const AdvanceResult r = _stepOrder(next ? +1 : -1);
    *moved = r.moved;
    *row = r.row;
    *reshuffled = r.reshuffled;
}
#endif

void LocalPlayerApp::onShuffleToggled(bool on) {
    g_settings.playerShuffle = on;
    _shuffleRepeatDirty = true;
    if (_pl.count() == 0) return;
    if (on) {
        // Toggle-ON is not a wrap — nothing "just finished" to guard
        // against re-opening on. 0xFFFF matches no real entry id
        // (PL_MAX_ENTRIES is 256).
        _pl.shuffleReset(0xFFFF);
        if (_curRow >= 0) {
            const uint16_t id = _pl.idAtView((uint16_t)_curRow);
            const int16_t pos = _pl.playPosOfId(id);
            _playCursor = (pos >= 0) ? pos : -1;
        } else {
            // Nothing playing: -1, NOT 0 — matches _load()'s own "cursor
            // unset" state and _stepOrder()'s dir>0 handling of -1 ("start
            // of order"), so the FIRST advance after this lands on
            // position 0 rather than skipping it. Landed as 0 originally
            // (T_PLR_20/21 DUT bug: a 20-track cycle came back missing
            // exactly its first entry, and all four §8 cells drifted off
            // "last row" for the same reason — get plCursor right after
            // toggle-ON with nothing playing read 0, not -1, so the
            // caller's "am I at the end" arithmetic was built on a
            // position that was never actually visited).
            _playCursor = -1;
        }
    } else {
        // Falling back to view order: the cursor's domain switches from
        // "bag position" to "view row" — the currently-playing row's
        // OWN view index is the equivalent position, not its old bag
        // slot (§8: shuffle never touches viewOrder, off-state playback
        // is plain sequential view order). Same -1-not-0 fix as above
        // when nothing is playing.
        _playCursor = (_curRow >= 0) ? _curRow : -1;
    }
}

void LocalPlayerApp::onRepeatChanged(int8_t state) {
    g_settings.playerRepeat = (uint8_t)state;
    _shuffleRepeatDirty = true;
}

void LocalPlayerApp::_rememberPlaylist(const char* path) {
    strlcpy(g_settings.playerPlaylist, path, sizeof(g_settings.playerPlaylist));
    _playlistDirty = true;
}

bool LocalPlayerApp::_load(const char* path) {
    if (!sdReady()) {
        LOG_W("localplayer", "no SD card mounted — cannot load %s", path);
        _err = true;
        _dirty = true;
        return false;
    }
    const bool ok = _pl.load(path);
    _err    = !ok;
    _curRow = -1;
    _playCursor = -1;
    _plSeqno++;
    _dirty  = true;
    // TASK-418: PlaylistIndex::load() always rebuilds playOrder as the
    // fresh identity (m3u.h) — a shuffle in effect from a previous list
    // must be re-applied to the new one, or "shuffle ON" silently reverts
    // to sequential the moment a different playlist loads. Nothing was
    // playing this list yet, so no guard id (0xFFFF, same as toggle-ON).
    if (ok && s_plShuffleOn) _pl.shuffleReset(0xFFFF);
    // A different playlist is a different list: re-anchor the scroll here
    // rather than through resetScrollOnChange(), which would also fire on
    // every current-row change.
    winampDisplay.pleditScrollToRow(0);
    return ok;
}

void LocalPlayerApp::_syncCurRowFromCursor() {
    if (_pl.count() == 0 || _playCursor < 0) { _curRow = -1; return; }
    _curRow = s_plShuffleOn ? (int)_pl.playRowAt((uint16_t)_playCursor) : _playCursor;
}

LocalPlayerApp::AdvanceResult LocalPlayerApp::_stepOrder(int dir) {
    AdvanceResult r{false, 0, false};
    const uint16_t n = _pl.count();
    if (n == 0) return r;

    if (dir > 0) {                                    // NEXT
        if (_playCursor < 0) {
            _playCursor = 0;                           // nothing was playing: start of order
        } else {
            const int next = _playCursor + 1;
            if (next < (int)n) {
                _playCursor = next;
            } else if (s_plRepeatState == 2) {          // repeat OFF: stop at the end either way
                return r;                                // shuffle off: "stop at last row"
            } else if (!s_plShuffleOn) {                // repeat ALL, shuffle off
                _playCursor = 0;                         // wrap to viewOrder[0]
            } else {                                     // repeat ALL, shuffle on
                const uint16_t justFinishedId = _pl.idAtPlayPos((uint16_t)_playCursor);
                _pl.shuffleReset(justFinishedId);         // guard: must not re-open on it
                _playCursor = 0;
                r.reshuffled = true;
            }
        }
    } else {                                          // PREV — replay history, no reroll
        if (_playCursor <= 0) return r;                 // nothing before the start
        _playCursor -= 1;
    }
    _syncCurRowFromCursor();
    r.moved = true;
    r.row = (uint16_t)_curRow;
    return r;
}

void LocalPlayerApp::_autoAdvance() {
    const AdvanceResult r = _stepOrder(+1);
    if (r.moved) {
        LOG_I("localplayer", "auto-advance -> row %u%s", (unsigned)r.row,
              r.reshuffled ? " (reshuffled)" : "");
        _startPlayback(r.row);
    } else {
        _playing = false;
        _curRow  = -1;
        _direct  = false;
        _plSeqno++;
        _dirty   = true;
        LOG_I("localplayer", "auto-advance: end of list, stopping");
    }
}

void LocalPlayerApp::_startPlayback(uint16_t idx) {
    if (idx >= _pl.count()) return;
    char path[m3u::PL_PATH_MAX];
    if (!_pl.pathAt(idx, path, sizeof(path))) {
        LOG_W("localplayer", "row %u has no readable path", (unsigned)idx);
        _err = true;
        return;
    }
    // Tapping/advancing to a new row while one plays: stop first, so the
    // engine isn't asked to connect on top of a live decode.
    // TASK-518: clear the flags with the stop, matching the eject path
    // (:519-520). aeStopFile() takes the OLD _connecting, so the clear has
    // to follow it. Without this, the `!aeConnectFile()` early return below
    // leaves _connecting latched true from the attempt we just tore down —
    // a stuck amber taskbar indicator before, and now a `get idle` that
    // never goes quiet again.
    if (_playing || _connecting) aeStopFile(_connecting);
    _playing = _connecting = false;
    // TASK-435: drop the playlist's file handle BEFORE the arena is asked
    // for its 24 576 B contiguous block. pathAt() above went through
    // _readRecord() -> _ensureOpen() (m3u.h:467), which reopens the FIL if
    // closeIfIdle() had dropped it — and newlib gives that handle a ~4.4 KB
    // stdio buffer (FATFS reports st_blksize 4096). Without this line the
    // reopen and the arena ask are forced to be resident at the same
    // instant on *every* play call, which on cyd2usb_player is the
    // difference between acquiring and not: DUT-measured lfb8 26 612 B
    // immediately before the call, 22 516 B inside it at the acquire,
    // against a 24 576 B need. That is why waiting for the idle-close
    // before calling play never helped — play reopens it itself. The path
    // is already resolved into `path` by this point, so the handle has no
    // remaining reader; the next row read reopens it transparently.
    _pl.closeIfIdle(0);
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

void LocalPlayerApp::_playRow(uint16_t idx) {
    if (idx >= _pl.count()) return;
    if (s_plShuffleOn) {
        const uint16_t id = _pl.idAtView(idx);
        const int16_t pos = _pl.playPosOfId(id);
        _playCursor = (pos >= 0) ? pos : (int)idx;   // pos always found; belt+suspenders
    } else {
        _playCursor = (int)idx;
    }
    _startPlayback(idx);
}

void LocalPlayerApp::_playPathDirect(const char* path) {
    if (_playing || _connecting) aeStopFile(_connecting);
    _playing = _connecting = false;   // TASK-518 — see _startPlayback()
    // TASK-435: same reason as _startPlayback() — this path does not call
    // pathAt(), so it never reopens the handle itself, but the playlist's
    // ~4.4 KB handle can still be open from PLEDIT scrolling before the
    // user browsed to this file. Drop it before the arena's 24 576 B ask
    // rather than leaving the outcome to how recently the list was
    // scrolled.
    _pl.closeIfIdle(0);
    LOG_I("localplayer", "play (direct): %s", path);
    if (!aeConnectFile(path)) { _err = true; _dirty = true; return; }
    strlcpy(_directPath, path, sizeof(_directPath));
    _direct     = true;
    _curRow     = -1;
    _playCursor = -1;
    _connecting = true;
    _playing    = false;
    _err        = false;
    _plSeqno++;
    _dirty      = true;
}

void LocalPlayerApp::_drawFull() {
    // repaintChrome() redraws the volume slider from whatever pct was last
    // cached — possibly Spotify's or WebRadio's, from before the switch.
    // WebRadio re-seeds it here with its own persisted value; Player has no
    // volume of its own until TASK-417 gives the mode a volume sink, so it
    // deliberately inherits rather than inventing a third stored value.
    winampDisplay.repaintChrome();
    _drawTitle();
}

void LocalPlayerApp::_drawTitle() {
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

// TASK-418 / ADR-059 D9 — defined here, after LocalPlayerApp, so the sinks
// can reach the bag through s_activeLocalPlayer (forward-declared above the
// class; the pointer itself is set in init()/resume(), cleared in suspend()).
static void playerShuffleSink(int next) {
    const bool on = (next != 0);
    s_plShuffleOn = on;
    if (s_activeLocalPlayer) s_activeLocalPlayer->onShuffleToggled(on);
}
static void playerRepeatSink(int next) {
    const int8_t st = (next == 2) ? 2 : 0;   // D9: binary domain, only 2/0 meaningful
    s_plRepeatState = st;
    if (s_activeLocalPlayer) s_activeLocalPlayer->onRepeatChanged(st);
}
