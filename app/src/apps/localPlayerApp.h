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
//
// Self-contained per D0/SF.11 (M-SRCLAYOUT Stage E / TASK-471) — method
// bodies live in localPlayerApp.cpp.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <SD.h>
#include <esp_heap_caps.h>
#include <SpotifyArduino.h>   // winamp/winampDisplay.h's CheapYellowDisplay base needs this in scope

#include "appShell.h"
#include "audio/audioEngine.h"
#include "gen/shell_layout.h"
#include "logSink.h"
#include "player/fileBrowser.h"
#include "player/m3u.h"
#include "settingsStorage.h"
#include "winamp/winampDisplay.h"

#include "display/tft.h"
extern WinampDisplay winampDisplay;
extern bool sdReady();   // sd/sdMount.cpp — the boot mount's outcome (TASK-408)

// TASK-417 / ADR-059 D8/D9 — winampDisplay's shuffle/repeat commit seams
// (setShuffleSink()/setRepeatSink()/setSeekSink(), mirrors TASK-352's
// setVolumeSink()) for Player mode. Repeat deliberately reuses the shipped
// tri-state domain but Player only ever emits 2 (off) or 0 (repeat-all) per
// D9's binary domain.
//
// TASK-418: the toggle/state booleans stay file-scope (s_plShuffleOn/
// s_plRepeatState — cheap to read from anywhere, e.g. LocalPlaylistSource's
// row rendering has no app-instance handle), but the shuffle BAG lives on
// the app's PlaylistIndex, so the sink can no longer be fully instance-free
// the way TASK-417 left it ("no play-order bag exists yet to attach it to").
// s_activeLocalPlayer is set in init()/resume() and cleared in suspend() —
// same "only meaningful while this mode is live" contract sdReady() and
// friends already use elsewhere in this file. All of these stay file-static
// (never referenced outside this file), now living in localPlayerApp.cpp.
class LocalPlayerApp;
static void playerShuffleSink(int next);
static void playerRepeatSink(int next);
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
        PlSrcKind kind() const override { return PlSrcKind::LocalPlaylist; }   // P2
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

    void init() override;
    void resume() override;

    // TASK-429 (b): the deferred-save retry in loop() cannot succeed while this
    // app is foreground — the arena and decoder hold the contiguous heap for the
    // whole session, not just while a track plays, so lfb8 stays ~5.6 KB even
    // when idle (DUT-measured: 6 retries in 45 s, all refused, lfb8 unchanged).
    // suspend() is where the engine is torn down and the memory comes back, so
    // it is the first moment the write can land — which is precisely ADR-050
    // rule 3's "coalesce the write into suspend()", applied to a write the user
    // made earlier and that would otherwise be lost.
    void suspend() override;
    void tick() override;

    bool hasError() const override { return _err; }
    // The connect runs on the pump task, not on a dataTask fetch — but the
    // taskbar's connecting indicator is the honest signal for it, same as
    // WebRadio's.
    bool isConnecting() const override { return _connecting; }

    // TASK-416 / NEW-APP-CHECKLIST item 1: true while a browser page read is
    // in flight — self-clears when the walk finishes (fileBrowser.h's tick()
    // flips its own state, this just observes it).
    bool hasPendingAsync() const override { return _browser.pending(); }

    // TASK-518 (P4): LocalPlayer has TWO independent in-flight operations:
    //   1. _browser.pending() — a file-browser page walk (fileBrowser.h:188,
    //      _state == State::Walking, flipped by the browser's own tick()).
    //      Backs hasPendingAsync().
    //   2. _connecting — a track open on the audio pump task. Set in _play()
    //      /_playIndex() (:898, :943), cleared when the open resolves (:340)
    //      and on every teardown/stop path (:253, :520, and aeStopFile at
    //      :879/:929), so a failed open clears it too.
    // isConnecting() IS reusable here (the other of the two apps where it is):
    // _connecting is transient-operation semantics — an open with a start and
    // an end — not a never-had-data latch. ORed, not used alone, because it
    // says nothing about a browser walk.
    bool hasInFlightOp() const override { return _browser.pending() || _connecting; }

    // TASK-416 / NEW-APP-CHECKLIST item 4, TASK-384 precedent: except the
    // browser's own back/up zone from the shell busy gate, or a tap there
    // while a page walk is in flight is silently dropped — confirmed on real
    // hardware to feel broken in a way the harness alone would not catch.
    bool isNavigationTap(int x, int y) const override {
        return _browser.active() && _browser.isBackZone(x, y);
    }

    // ── Input ──────────────────────────────────────────────────────────────

    bool handleInput(TouchPhase phase, int x, int y) override;

    // ── player::FileBrowser::Delegate ─────────────────────────────────────
    // The browser resolves the tap to a full path and tells us what kind of
    // file it was; playback/loading policy stays here, not in fileBrowser.h.

    void fbPlayFile(const char* path) override;
    void fbLoadPlaylist(const char* path) override;

#ifdef SERIAL_DEBUG
    // ── Debug surface (ADR-059 D12: shipped with the feature) ──────────────
    // `set plLoad <path>` is the only way to choose a playlist until the
    // browser lands, and `get plCount` / `get plRow` / `get plMem` are the
    // observables T_PLR_08–12 assert on.
    bool dbgLoad(const char* path);
    void dbgReport() const;
    void dbgRow(uint16_t idx);
    // T_PLR_12 (VE-15): largest-free-block alongside free heap — a clean
    // free-heap figure hides fragmentation, which is the real risk here.
    void dbgMem() const;
    bool dbgPlayRow(uint16_t idx);
    // TASK-416 (ADR-059 D12): drives the browser from the harness — T_PLR_13-16
    // need to open big/nested/empty directories and select rows deterministically,
    // not just via injected taps.
    bool dbgFbOpen(const char* path)   { return _browser.open(path); }
    bool dbgFbSelect(int16_t idx)      { return _browser.dbgSelect(idx); }
    bool dbgFbCancel()                 { return _browser.dbgCancel(); }
    void dbgFbState() const            { _browser.dbgReport(); }
    // TASK-521: which failure mode the last open() hit — the harness needs to
    // tell "not on the card" from "no byte-addressable heap left".
    player::FileBrowser::OpenErr dbgFbLastError() const { return _browser.lastError(); }

    // TASK-418 / ADR-059 D12 — the play-order engine's own observability,
    // "product surface, not test scaffolding". `advance` steps the SAME
    // _stepOrder() real playback uses, WITHOUT calling _startPlayback() —
    // T_PLR_20-24 exercise the whole shuffle bag, all four end-of-list
    // cells and prev-history in seconds instead of the ~3h of real playback
    // the design originally specified (VE-1).
    // P2 (M-TESTBASE): the playlist half of `get player`. Emits FRAGMENT JSON —
    // no braces, no "last" — because cmdGet's `get player` composes it into one
    // line. Order-sensitive FNV-1a over the u16 sequence, so a permutation is
    // detectable without dumping up to 256 entries on every poll.
    void dbgPlayerVector() const;

    void dbgOrder() const;
    void dbgCursor() const;
    // Sets the cursor directly in whichever domain is active (view row when
    // shuffle is off, bag position when shuffle is on) — same field `advance`
    // and real playback share. Does NOT touch _curRow's "is this the row
    // that's actually playing" meaning beyond re-deriving it for display;
    // does NOT call aeConnectFile (D12: "without decoding audio").
    bool dbgSetCursor(int n);
    // `next`=true for NEXT, false for PREV. Model-only step (see _stepOrder).
    void dbgAdvance(bool next, bool* moved, uint16_t* row, bool* reshuffled);
#endif

    // TASK-418 / ADR-059 D9 — public because the file-scope sinks (free
    // functions, not members — that's the signature winampDisplay's
    // setShuffleSink()/setRepeatSink() expect) call these on the active
    // instance via s_activeLocalPlayer.
    void onShuffleToggled(bool on);
    void onRepeatChanged(int8_t state);

private:
    // RAM-only; the flash write is coalesced into suspend(). See the comment there.
    void _rememberPlaylist(const char* path);

    bool _load(const char* path);

    // playOrder position (shuffle on) or view row (shuffle off) -> _curRow,
    // the VIEW row PLEDIT highlights as "current". Kept as a separate step
    // from _playCursor's own mutation so `set plCursor`/`advance` (D12: no
    // audio) and real playback update the highlight identically.
    void _syncCurRowFromCursor();

    // ── TASK-418 / ADR-059 D9 — the play-order engine ───────────────────────
    // Result of one step. Model-only: never touches the audio engine. Real
    // playback (auto-advance, transport PREV/NEXT) calls _stepOrder() then
    // _startPlayback()s the row it returns; the debug `advance` command
    // (D12) calls _stepOrder() alone.
    struct AdvanceResult {
        bool     moved;        // false = end of list, nothing to play
        uint16_t row;           // valid VIEW row iff moved
        bool     reshuffled;    // a wrap-triggered reshuffle happened
    };

    // dir > 0 = NEXT, dir < 0 = PREV. Implements design §8's table exactly:
    //
    //              | repeat off              | repeat all
    //   shuffle off| stop at last row        | wrap to viewOrder[0]
    //   shuffle on | play each once, stop    | reshuffle and continue
    //
    // PREV never rerolls — it walks _playCursor backward through whatever
    // playOrder already holds (history), which is the whole reason the bag
    // is materialised rather than generated lazily (§8).
    AdvanceResult _stepOrder(int dir);

    // Auto-advance (ADR-059 D9/D12) — hangs off tick()'s aeEofCount() poll,
    // which only ever runs on loopTask (tick() is loopTask-only), same task
    // aeDrainEof() itself asserts against. The bag is loopTask-owned state
    // and is never touched from the audio pump task — audio_eof_mp3() only
    // ever sets a flag (audioEngine.h).
    void _autoAdvance();

    // Connects the engine to a playlist row. Does NOT touch _playCursor —
    // callers that mean "the user picked this row" (tap-to-play, PLAY button)
    // set the cursor themselves first (_playRow, below); callers driven by
    // the order engine (_autoAdvance, PREV/NEXT) already moved it via
    // _stepOrder() before calling this.
    void _startPlayback(uint16_t idx);

    // Manual pick — tap-to-play or the PLAY button on a stopped list. Moves
    // the play-order cursor to match the picked row (§8: "tap-to-play under
    // shuffle moves the bag cursor to that entry's position ... does not
    // reshuffle") and THEN starts playback.
    void _playRow(uint16_t idx);

    // TASK-416: playing a file tapped straight out of the browser, not
    // through the loaded playlist's index — _curRow stays -1 (no playlist row
    // "is" this track; PLEDIT correctly shows no current-row highlight) and
    // _direct + _directPath carry what the title bar needs instead. Not part
    // of any playlist queue, so the play-order cursor is cleared, not moved
    // (auto-advance on a direct-played file's eof stops rather than stepping
    // a cursor that no longer means anything — see tick()'s _direct branch).
    void _playPathDirect(const char* path);

    void _drawFull();
    void _drawTitle();

    m3u::PlaylistIndex     _pl;
    LocalPlaylistSource    _src;
    player::FileBrowser    _browser;
    bool          _browserWasActive = false;
    char          _lastBrowseDir[m3u::PL_PATH_MAX] = {0};
    bool          _direct     = false;   // playing a browser-tapped file, not a playlist row
    char          _directPath[m3u::PL_PATH_MAX] = {0};
    uint32_t      _plSeqno    = 1;    // never 0 — the view's gate starts at 0
    int           _curRow     = -1;
    // TASK-418 / ADR-059 D9: position in the ACTIVE order domain — the view
    // row when shuffle is off, the bag position (index into _pl.playOrder())
    // when shuffle is on. -1 = nothing playing. _curRow is always re-derived
    // from this (_syncCurRowFromCursor()); the reverse is never true.
    int           _playCursor = -1;
    bool          _playing    = false;
    bool          _connecting = false;
    bool          _err        = false;
    bool          _dirty      = true;
    unsigned long _lastScrollMs = 0;
    uint32_t      _eofSeen    = 0;
    bool          _playlistDirty = false;
    char          _playlistSaved[64] = {0};
    // TASK-418: shuffle/repeat's half of the same coalesced-write discipline
    // as the playlist path above (ADR-050 rule 3, suspend()-only flash write).
    bool          _shuffleRepeatDirty = false;
    bool          _shuffleSaved = false;
    uint8_t       _repeatSaved  = 2;
};
