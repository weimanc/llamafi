#pragma once
// webRadioApp.h — International Web Radio app (M-WEBRADIO).
// Streams MP3 from radio-browser.info via ESP32-audioI2S on internal DAC GPIO26.
// No taskbar slot of its own (eject-only tail, TASK-242) — reached via the
// taskbar player-slot cycle/restore (TASK-413). Eject means "load media from
// this source" here (station-list refresh), not "switch app" (TASK-414).

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
#include "audio/audioEngine.h"  // TASK-409: system-owned Audio engine (PURE MOVE)
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "gen/skin_layout.h"
#include "logSink.h"
#include "perf.h"
#include "spotifyTask.h"
#include "winamp/winampDisplay.h"
#include "winamp/vuMeter.h"

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

// TASK-224: ICY StreamTitle buffer length, WR_CONNECT_TIMEOUT_MS/_SSL and
// WR_VOLUME_MAX moved to audio/audioEngine.h (TASK-409).

// TASK-402 (M-WEBRADIO-POSBAR-SMOOTH): EMA alpha + time-based redraw floor
// for the posbar buffer-fullness bar. Provisional defaults, not derived from
// static analysis -- the design doc's OQ1/OQ2 call for a DUT tuning pass
// (via `get wrPosbar`, comparing raw vs. smoothed traces under real
// playback) before these are considered final.
static constexpr float         WR_POSBAR_EMA_ALPHA      = 0.2f;
static constexpr unsigned long WR_POSBAR_MIN_REDRAW_MS  = 200;
// TASK-405 (M-WEBRADIO-POSBAR-SLEW): max points the drawn value may step
// toward the smoothed target per redraw-eligible tick. Bounds worst-case
// visual travel within any 2s window to <= (2000/MIN_REDRAW_MS) * this,
// by construction -- unlike the delta-threshold gate it replaces, which
// only bounded redraw frequency, not magnitude (a single redraw could
// jump ~80 points). Simulation-informed starting value against real
// captured traces (see design doc); DUT eyeball confirmation still open.
static constexpr uint8_t       WR_POSBAR_MAX_STEP_PER_TICK = 2;
// TASK-405 (M-WEBRADIO-POSBAR-SLEW, live-eyeball follow-up): the slew limiter
// alone bounds redraw *magnitude* but not *frequency of direction reversal* --
// on real playback the raw ring-buffer ratio reverses direction multiple
// times within a single network-delivery burst (confirmed via host-only sim
// against captured DUT traces: reversal count near the ceiling was ~flat
// regardless of step size or EMA alpha, since the underlying signal itself
// keeps flipping). A hysteresis dead-band near the top absorbs this: once
// the drawn value AND the smoothed target are both >= ENTER, freeze (skip
// the slew step entirely) until the target drops below EXIT. The gap
// between the two thresholds is the hysteresis band itself -- a single
// shared threshold would just move the chatter to that one boundary.
// Host-only eval (real traces + synthetic connect/hiccup/drop scenarios)
// showed near-total elimination of steady-state ceiling jitter (5->0
// reversals per 2s window) for ~0.2-0.6s of added connection-drop-detection
// latency, negligible against the already-accepted ~5s baseline.
static constexpr uint8_t       WR_POSBAR_FREEZE_ENTER_PCT  = 90;
static constexpr uint8_t       WR_POSBAR_FREEZE_EXIT_PCT   = 80;

// TASK-209 / M-WEBRADIO §HW Mod: WR_VOLUME_SOFT_CAP_STOCK, wrEffectiveVolume(),
// wrScaledVolume(), the ICY metadata queue, audio_showstreamtitle/audio_info,
// the Audio singleton (s_wr_audio/wrAudio()), audio_process_extern (real VU +
// spectrum + wave-trace feed), and the audio pump task (mutex, request/result
// protocol, wrEnsurePumpTask/wrTeardownPumpTask) all moved to
// audio/audioEngine.h (TASK-409 / ADR-059 D2, PURE MOVE).

// ── WebRadioApp ──────────────────────────────────────────────────────────────

class WebRadioApp : public App {
public:

    // ADR-059 D4 / TASK-412: WebRadio's station list as a PlaylistSource
    // (CAP_PLAY only) for the shared PLEDIT renderer (winamp/pleditView.h).
    // Nested in WebRadioApp (not a free class like winampDisplay.h's
    // SpotifyQueueSource) so it can read the station array / current index /
    // play state directly — there's no snapshot-copy seam here the way
    // spotifyTask::QueueSnapshot gives Spotify; WebRadio's state already
    // lives on the app object, and a nested class has the same access rights
    // as any other member (C++11).
    class StationListSource : public PlaylistSource {
    public:
        void bind(WebRadioApp* app) { _app = app; }

        uint16_t count()    override { return _app ? _app->_stationCount : 0; }
        uint32_t seqno()    override { return _app ? _app->_plSeqno : 0; }
        uint8_t  caps()     override { return CAP_PLAY; }
        uint32_t totalSec() override { return 0; }  // D10: overlayText() replaces this

        // D4: station name only, no track numbering (a station list has none —
        // already source-owned per the design, unchanged from TASK-411's
        // resolution of the same row for Spotify).
        bool row(uint16_t idx, PlRow &out) override {
            if (!_app || idx >= _app->_stationCount) return false;
            const dataTask::WebRadioStation &s = _app->_stations[idx];
            strlcpy(out.text, s.name, sizeof(out.text));
            out.durationSec = 0;
            // D3: right column is the bitrate badge — fixed dim colour, only
            // when known, not the row's fg (that's Spotify's duration rule).
            if (s.bitrate > 0) {
                snprintf(out.rightText, sizeof(out.rightText), "%uk", (unsigned)s.bitrate);
                out.rightColor = 0x4208U;
            } else {
                out.rightText[0] = '\0';
                out.rightColor   = 0;
            }
            // D7: "current" = the selected station while actually playing/
            // connecting, not merely selected — matches the pre-merge
            // definition; STOPPED clears the highlight.
            out.current = (idx == _app->_currentIdx) && (_app->_state != WRPlayState::STOPPED);
            return true;
        }

        void onTap(uint16_t idx) override {
            if (_app) _app->_play((uint8_t)idx);   // D22: already resolved by the interface
        }

        // D1/D2: WebRadio's pre-merge copy gave every row the same
        // background (no distinct "current" treatment) and no left margin.
        uint16_t bgNormal()   override { return PLEDIT_BODY_BG; }
        uint16_t bgSelected() override { return PLEDIT_BODY_BG; }
        uint8_t  marginPx()   override { return 0; }

        // D10: country code in the same bottom-bar overlay slot Spotify uses
        // for total playlist time (was the old superimposed WR_BADGE).
        void overlayText(char *buf, size_t bufSize) override {
            strlcpy(buf, g_settings.webRadioCountry, bufSize);
        }

        // D13: the station list is the same list refetched, not a new one —
        // keep the scroll position across a refresh. WebRadioApp explicitly
        // re-syncs it to the current pick via winampDisplay.pleditScrollToRow()
        // on selection and on app entry instead.
        bool resetScrollOnChange() override { return false; }

    private:
        WebRadioApp* _app = nullptr;
    };

    // ── Lifecycle ──────────────────────────────────────────────────────────

    void init() override {
        _state           = WRPlayState::STOPPED;
        _stationCount    = 0;
        _currentIdx      = g_settings.webRadioLastStation;
        _pendingStations = false;
        _stationSource.bind(this);   // TASK-412 / ADR-059 D4
        // ADR-050 rule 3 (M-WEBRADIO-SETTINGS): lastStation-at-load baseline for
        // the coalesced suspend()-save — no flash write when nothing changed.
        _lastStationSaved = g_settings.webRadioLastStation;
        _lastStationDirty = false;
        // TASK-352: same idiom for the volume-slider session pct.
        s_wrVolPctSaved   = g_settings.webRadioVolumePct;
        s_wrVolPctDirty   = false;
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
            s_wr_audio->setVolume(wrScaledVolume());  // TASK-352: ceiling + session pct
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
        _pleditSync();   // TASK-412: init() runs alone on first launch (no resume() call)

        // TASK-417 / ADR-059 D8: same reason as the TASK-412 comment just
        // above — switchApp() calls init() XOR resume(), never both, on
        // WebRadio's first-ever entry each boot session. Wiring caps/sinks
        // only in resume() (as first written) left the WinampDisplay
        // defaults (all four caps, Spotify's sinks) live for that first
        // session — the exact bug T_PLR_18 caught (playerCaps=15 instead of
        // CAP_TRANSPORT). Duplicated rather than factored, to keep this
        // diff small and match this file's existing style at line 235.
        winampDisplay.setPlayerCaps(CAP_TRANSPORT);
        winampDisplay.setShuffleSink(nullptr);
        winampDisplay.setRepeatSink(nullptr);
        winampDisplay.setSeekSink(nullptr);

        // _dirty=true; tick() handles first paint — init() must return fast
        // (called synchronously from cmdTap context; _drawFull here risks WDT).
    }

    void resume() override {
        _dirty = true;
        _pleditSync();   // TASK-412: PLEDIT scroll state is shared with SpotifyApp now
        // Defer paint to tick() — resume() can also run from cmdTap context.

        // TASK-352: wire the shared volume-drag machine's commit seam to
        // WebRadio for the duration of this session; SpotifyApp::resume()
        // restores the default (ACT_VOLUME) seam on eject-back.
        winampDisplay.setVolumeSink(wrVolumeSink);

        // TASK-417 / ADR-059 D8: WebRadio advertises CAP_TRANSPORT only —
        // no shuffle, repeat or seek zone. This is a refactor for WebRadio,
        // not a feature (T_PLR_18): its own handleInput() never hit-tested
        // those zones, but repaintChrome() drew the sprites anyway from
        // whatever the shared cache last held (dead icons). Gating the draw
        // on this mask (winampDisplay.h) fixes that. Sinks reset for
        // hygiene even though the mask means they're unreachable here.
        winampDisplay.setPlayerCaps(CAP_TRANSPORT);
        winampDisplay.setShuffleSink(nullptr);
        winampDisplay.setRepeatSink(nullptr);
        winampDisplay.setSeekSink(nullptr);

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
            _plSeqno++;   // TASK-412 / T_PLE_14: list identity changed (now empty, pending refetch)
            winampDisplay.pleditScrollToRow(0);
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
        // set wrEject can fire mid-gesture. TASK-412: PLEDIT drag state now
        // lives in the shared PleditView (winampDisplay._plView), reset below
        // along with the shared D_VOLUME_DRAG machine (TASK-352 precedent) —
        // must not leave either stuck across an eject mid-drag.
        winampDisplay.resetDragState();

        _stopAudio();
#ifdef MEMBUDGET_PHASE1
        if (_state == WRPlayState::CONNECTING) {
            // TASK-398: a connect is in flight on the pump task — the
            // _stopAudio() call above already posted ABORT (or left an
            // already-posted TEARDOWN alone; TEARDOWN always wins, never
            // downgraded). Leaving WebRadio entirely is always at least as
            // strong an intent as stopping, so overwrite unconditionally to
            // TEARDOWN and let the pump task own the delete/arena-release
            // itself — calling wrTeardownPumpTask() or deleting s_wr_audio
            // here would block loopTask for the connect's full remaining
            // duration, the exact freeze this design exists to remove.
            // Execution falls through to the settings-save logic below
            // unchanged — that's cheap, RAM-only, and doesn't touch
            // WebRadio audio state.
            s_wrPumpRequest = WrPumpRequest::TEARDOWN;
        } else {
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
        }
#endif

        // ADR-050 rule 3 (M-WEBRADIO-SETTINGS D3): coalesced lastStation +
        // (TASK-352) volumePct persistence — both write g_settings in RAM and
        // mark their own dirty flag; one SettingsStorage::save() here per
        // session iff either actually changed since load, so a session that
        // touches both doesn't cost two flash writes. Auto-skip/drag churn
        // costs zero flash writes otherwise, and eject also funnels through
        // suspend() so it is covered.
        bool needSave = false;
        if (_lastStationDirty) {
            if (g_settings.webRadioLastStation != _lastStationSaved) needSave = true;
            _lastStationDirty = false;
        }
        if (s_wrVolPctDirty) {
            if (g_settings.webRadioVolumePct != s_wrVolPctSaved) needSave = true;
            s_wrVolPctDirty = false;
        }
        if (needSave) {
            SettingsStorage::save();
            _lastStationSaved = g_settings.webRadioLastStation;
            s_wrVolPctSaved   = g_settings.webRadioVolumePct;
        }
    }

    void tick() override {
        // TASK-398 (M-WR-CONNECT-ASYNC): reconcile the pump task's async
        // connect outcome. Runs unconditionally, first thing every tick, so
        // a stale CONNECTING never survives past this call — this single
        // poll is what lets _play()'s CONNECTING no-op guard and
        // resume()'s existing `_state == STOPPED` autoplay gate both work
        // correctly without any special-case logic of their own.
        {
            WrPumpResult result = s_wrPumpResult;
            if (result == WrPumpResult::CONNECTED) {
                // Re-derived from _play()'s old post-connect success path —
                // today's existing PLAYING-transition logic, unchanged, just
                // reading a polled result instead of a live return value.
                _state = WRPlayState::PLAYING;
                _lastRunningMs   = millis();  // TASK-218: seed grace window for stream-death detection
                _lastBufChangeMs = _lastRunningMs;  // TASK-291: seed grace window for the buffer-stall signal
                _lastSeenFilled  = 0;
                _playingSinceMs  = _lastRunningMs;  // TASK-234: settled-timer start
                _settled        = false;
                _bufPctDrawn    = 0;         // TASK-220: force a buffer-bar repaint on first fill
                _bufPctSmoothed = 0.0f;      // TASK-402: fresh EMA baseline per PLAYING session
                _posbarSimDrainActive = false; // TASK-405: a stale sim-drain must not suppress
                                                // real buffer readings on a fresh session
                _posbarFrozen   = false;     // TASK-405: fresh session, fresh dead-band state
#ifdef MEMBUDGET_PHASE1
                _underrunCount          = 0; // TASK-263: fresh underrun count per PLAYING session
                _recurrentUnderrunCount = 0; // TASK-266: fresh per PLAYING session too
                _minBufPct      = 100;
                _wasEmpty       = false;
#endif
                // _spotifyYielded stays true — TLS resumes in _stopAudio().
                _dirty = true;
                s_wrPumpResult = WrPumpResult::NONE;
            } else if (result == WrPumpResult::FAILED) {
                // Re-derived directly from _play()'s old failure path, in
                // full — the resume call sits between the other two
                // statements and is not optional: FAILED is the single most
                // common outcome (421 occurrences/4h per TASK-393), so
                // dropping it here leaks Spotify's TLS yield for the rest of
                // the boot (tlsYield starvation — a bug class this project
                // has already root-caused and fixed five times before).
                _state = WRPlayState::ERROR_UNREACHABLE;
                LOG_W("webradio", "connecttohost failed idx=%u", _currentIdx);
                if (_spotifyYielded) {
                    spotifyTask::tlsResume();
                    _spotifyYielded = false;
                }
                _onPlaybackFailed(/*connectFail=*/true);  // TASK-234: skip a dead host
                _dirty = true;
                s_wrPumpResult = WrPumpResult::NONE;
            } else if (result == WrPumpResult::ABORTED || result == WrPumpResult::TORN_DOWN) {
                // Same TLS-resume obligation as FAILED above — a STOP/eject
                // during CONNECTING must not leak the yield either.
                _state = WRPlayState::STOPPED;
                if (_spotifyYielded) {
                    spotifyTask::tlsResume();
                    _spotifyYielded = false;
                }
                _dirty = true;
                s_wrPumpResult = WrPumpResult::NONE;
            }
        }

        // TASK-252: scroll the LED-font title marquee (long station names).
        winampDisplay.tickMarquee();

        // TASK-350: reuse the Spotify synthetic visualizer — decoupled seam
        // (vu::tick() no longer reaches into spotifyTask state itself), fed
        // WebRadio's own playing/elapsed. elapsedMs rides the item-2 (TASK-349)
        // read block's _snapPlaySec — one take, both consumers, per TASK-278
        // discipline; up to one tick (50ms) stale here is fine, the envelope's
        // beat oscillators don't need sub-second phase accuracy. Mode state
        // (vu::currentMode()) is global, so it carries across the eject
        // toggle for free.
        // PROP-005/M-WEBRADIO-REAL-VIS: realAudio=true unconditionally — this
        // app's audio_process_extern hook above keeps lLevelRef()/rLevelRef()
        // fresh with the real per-block peak envelope whenever WebRadio is
        // playing, so vu::tick() should always trust it here (VIS_VU only;
        // other modes are unaffected — see vuMeter.h).
        vu::tick(winampDisplay.chromeOriginX(), winampDisplay.chromeOriginY(), SKIN_MAIN_BG,
                 /*playing=*/_state == WRPlayState::PLAYING,
                 /*elapsedMs=*/(long)_snapPlaySec * 1000L,
                 /*realAudio=*/true);

        // TASK-277: velocity-scroll integrator — placed here, BEFORE the
        // terminal-retry / pending-action dispatch below, so those blocks'
        // early returns cannot stall a live gesture [DEV-1-3]. dt-integrated
        // (M-LIST-v4 OQ1): robust to variable loop cadence.
        {
            const unsigned long now = millis();
            const float dt = (_lastScrollMs == 0) ? 0.0f
                                                  : (now - _lastScrollMs) * 0.001f;
            _lastScrollMs = now;
            winampDisplay.tickScroll(dt);
        }
        // TASK-412: PLEDIT now owns its own seqno/scroll redraw gate
        // (pleditView.h) — call unconditionally every tick, same as
        // SpotifyApp::tick()'s winampDisplay.drawPlaylist(). Must run here,
        // not folded into the _dirty branch below, so a scroll step or a
        // _pleditSync() invalidate still repaints this tick even when
        // nothing else changed.
        winampDisplay.drawPlaylistFor(_stationSource);

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
                    _plSeqno++;   // TASK-412 / T_PLE_14: list identity changed
                    winampDisplay.pleditScrollToRow((int)_currentIdx);
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
                if (_posbarSimDrainActive) {
                    // TASK-405 (VE-2): `set wrPosbarSimDrain` override — decrement at the
                    // same cadence as the redraw gate (slow enough to be a meaningful
                    // "real decline", not an instant jump); feeds the exact same
                    // EMA/slew path below, unlike `wrBufPct`'s direct-draw bypass.
                    // Deliberately does NOT auto-disable at raw==0 — an earlier version
                    // did, and it let real (high) buffer data flood back in as soon as
                    // raw hit empty, while the slewed *drawn* value was still several
                    // ticks away from visually catching down to 0, reversing the trend
                    // before a tester could see it bottom out. Sits at 0 until
                    // `set wrPosbarSimDrain 0` explicitly disables it, matching the
                    // design doc's own spec.
                    if (now - _posbarSimDrainLastMs >= WR_POSBAR_MIN_REDRAW_MS) {
                        _posbarSimDrainLastMs = now;
                        _bufPct = (_bufPct > _posbarSimDrainStep)
                                  ? (uint8_t)(_bufPct - _posbarSimDrainStep) : 0;
                    }
                } else {
                    _bufPct = total ? (uint8_t)((uint32_t)filled * 100u / total) : 0;
                }
                // TASK-402: EMA the raw ratio before it drives the gate/draw — the raw
                // byte-level ring-buffer ratio is naturally noisy (M-WEBRADIO-POSBAR-
                // SMOOTH.md), same value-domain-filter technique as the VU meter's own
                // attack/release smoothing (webRadioApp.h tick(), around line 227).
                _bufPctSmoothed += ((float)_bufPct - _bufPctSmoothed) * WR_POSBAR_EMA_ALPHA;
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
                // TASK-405 (M-WEBRADIO-POSBAR-SLEW): time-gate, then slew the drawn
                // value toward the smoothed target by at most WR_POSBAR_MAX_STEP_PER_TICK
                // points — bounds worst-case 2-second-window travel by construction
                // (the old delta-threshold gate bounded redraw *frequency* only; a
                // single redraw could still jump ~80 points, which is what read as
                // "oscillating" on the physical LCD — see design doc's Analysis).
                // `lastSkipReason` (`get wrPosbar`) stays three-way and meaningful
                // (VE-1): INTERVAL = time-gate blocked; CONVERGED = eligible but
                // already at target, nothing to step; NONE = we stepped/redrew.
                uint8_t smoothedRounded = (uint8_t)(_bufPctSmoothed + 0.5f);
                bool intervalOk = (now - _lastPosbarRedrawMs) >= WR_POSBAR_MIN_REDRAW_MS;
                if (intervalOk) {
                    _lastPosbarRedrawMs = now;
                    // TASK-405 (live-eyeball follow-up): hysteresis dead-band near the
                    // ceiling. Un-freeze first (based on the incoming target, before this
                    // tick's own step) so a genuine decline starts escaping the same tick
                    // it crosses EXIT, not one tick late.
                    if (_posbarFrozen && smoothedRounded < WR_POSBAR_FREEZE_EXIT_PCT) {
                        _posbarFrozen = false;
                    }
                    if (_posbarFrozen) {
                        _posbarLastSkipReason = PosbarSkipReason::FROZEN;
                    } else {
                        int diff = (int)smoothedRounded - (int)_bufPctDrawn;
                        if (diff > (int)WR_POSBAR_MAX_STEP_PER_TICK) diff = WR_POSBAR_MAX_STEP_PER_TICK;
                        else if (diff < -(int)WR_POSBAR_MAX_STEP_PER_TICK) diff = -(int)WR_POSBAR_MAX_STEP_PER_TICK;
                        if (diff != 0) {
                            _bufPctDrawn = (uint8_t)((int)_bufPctDrawn + diff);
                            _posbarRedrawCount++;
                            _posbarLastSkipReason = PosbarSkipReason::NONE;
                            _drawPosbar();   // targeted POSBAR blit only — no full repaint
                        } else {
                            _posbarLastSkipReason = PosbarSkipReason::CONVERGED;
                        }
                        if (_bufPctDrawn >= WR_POSBAR_FREEZE_ENTER_PCT
                            && smoothedRounded >= WR_POSBAR_FREEZE_ENTER_PCT) {
                            _posbarFrozen = true;
                        }
                    }
                } else {
                    _posbarLastSkipReason = PosbarSkipReason::INTERVAL;
                }

                // TASK-349: main-window time digits — same read block as the
                // buffer gauge above (one take, all values out, per TASK-278
                // discipline). Wrap at 6000s (99:59 the raw drawTimeDigits()
                // clamp would otherwise pin at) — radio streams outlive the
                // classic 4-digit MM:SS range. Freeze-on-rebuffer falls out
                // for free: the lib's own counter stalls with decode.
                winampDisplay.updateTimeDigits((int)(_snapPlaySec % 6000));

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
        // TASK-352: volume slider — public capture entry into the shared
        // D_VOLUME_DRAG machine (winampDisplay). Checked first: on Press it
        // only consumes touches inside the slider (returns false otherwise,
        // falling through unchanged below); once captured it consumes every
        // Move/Release regardless of x/y, same priority pattern as the PLEDIT
        // gesture capture right below — geometry is disjoint (slider sits in
        // the main-window band, PLEDIT rows start at y=136+) so the two
        // captures can never compete for the same touch.
        if (winampDisplay.handleVolumeGesturePublic(phase, x, y)) return true;

        // TASK-412 (ADR-059 D4): PLEDIT press/move/release now dispatch
        // through the shared PleditView (winamp/pleditView.h) via
        // StationListSource — captured gesture first (Move updates it,
        // Release is consumed by drag-end BEFORE any eject/transport
        // hit-test [DEV-1-1 blocker], same priority the donor machine used).
        if (winampDisplay.pleditDragging()) {
            if (phase == TouchPhase::Release) {
                const PlReleaseResult r = winampDisplay.pleditRelease(_stationSource);
                if (r.cooldownMs) winampDisplay.armTouchCooldown(r.cooldownMs);  // D17
                return true;
            }
            winampDisplay.pleditMove(y);
            return true;
        }

        // TASK-277 / D17: Press in the PLEDIT bands anchors a gesture — gated
        // by the shared cooldown now (WebRadio's pre-merge copy had no
        // cooldown at all; adopting Spotify's closes that gap). Press
        // anywhere else is not consumed (eject/transport act on Release, as
        // today).
        if (phase == TouchPhase::Press) {
            if (winampDisplay.touchCoolingDown()) return false;
            if (winampDisplay.pleditPress(x, y)) return true;
            return false;
        }

        if (phase != TouchPhase::Release) return false;

        // No-anchor Release [VE-1-2]: no prior Press (exactly how cmdTap
        // drives the T_WR_* tap surface) — today's tap-at-(x,y) path,
        // unchanged from here down.

        // TASK-350: tap the vis area to cycle mode — M-VIS parity with the
        // Spotify path (the hit zone geometry already lives in vuMeter.h).
        // Mode state is a global (vu::s_modeRef()), so this affects both apps.
        // TASK-387/388: appHasSpectrum/appHasWave=true — WebRadio's cycle
        // gains real-data Spectrum and Wave stops (Atlas -> WaveAtlas -> VU
        // -> Wave -> Spectrum -> Blank -> Atlas); Spotify's own call site
        // (winampDisplay.h) is untouched.
        // TASK-389: mask built fresh from g_settings each tap (Settings >
        // WebRadio > Vis modes) — cheap enough not to cache, and a live
        // Settings edit takes effect on the very next tap this way.
        if (x >= vu::RECT_X && x < vu::RECT_X + vu::RECT_W &&
            y >= vu::LEFT_Y && y < vu::LEFT_Y + vu::VIS_H) {
            uint8_t mask = 0;
            if (g_settings.webRadioVisAtlas)     mask |= vu::MF_ATLAS;
            if (g_settings.webRadioVisWaveAtlas) mask |= vu::MF_WAVE_ATLAS;
            if (g_settings.webRadioVisVU)        mask |= vu::MF_VU;
            if (g_settings.webRadioVisSpectrum)  mask |= vu::MF_SPECTRUM;
            if (g_settings.webRadioVisWave)      mask |= vu::MF_WAVE;
            vu::nextMode(/*appHasSpectrum=*/true, mask, /*appHasWave=*/true);
            return true;
        }

        // TASK-414 / ADR-059 D6: eject is freed from "switch back to Spotify"
        // (the taskbar player-slot cycle from TASK-413 owns app switching
        // now) and becomes "load media from this source" — a station-list
        // refresh/browse, staying on WebRadio. Mirrors resume()'s
        // config-change refetch (abort any in-flight fetch first, WR-1),
        // but does NOT stop playback or reset the current station — a
        // refresh is not a teardown.
        if (winampDisplay.hitTestEject(x, y)) {
            if (millis() >= _ejectCooldownMs) {
                if (_pendingStations) dataTask::abortWebRadioFetch();
                _enqueueStationFetch();
                _ejectCooldownMs = millis() + EJECT_COOLDOWN_MS;
                LOG_I("webradio", "eject tap → station list refresh");
            }
            return true;
        }

        // Transport buttons (PREV/PLAY/PAUSE/STOP/NEXT) via public hit-test
        int t = winampDisplay.hitTestTransportPublic(x, y);
        if (t == 0) { _prevStation(); return true; }
        if (t == 1 || t == 2) { _togglePlay(); return true; }
        if (t == 3) {
            // TASK-398: no redundant _state = STOPPED here — _stopAudio()
            // already sets it in every state except CONNECTING, and forcing
            // it there would overwrite the pending-ABORT CONNECTING state
            // before the pump has actually processed it, defeating _play()'s
            // re-entrancy guard on the very next tap. tick()'s poll is the
            // sole owner of this transition now, for every caller.
            _stopAudio();
            _dirty = true;
            return true;
        }
        if (t == 4) { _nextStation(); return true; }

        // TASK-412 / D21: pre-merge WebRadio had a SECOND, unanchored
        // PLEDIT-row tap-at-(x,y) path here for cmdTap, which drives a bare
        // Release with no prior Press against WebRadioApp's OWN gesture
        // state. That's no longer a gap: cmdTap's WebRadio branch
        // (main.cpp's cmdTap) calls winampDisplay.injectTouch() BEFORE this
        // handleInput(Release,...) — injectTouch() runs handleWinampInput()'s
        // Press phase, which (PLEDIT coordinates fall through every
        // Spotify-only zone) still reaches the shared PleditView's press().
        // Both the real-touch path (via the pleditDragging() branch above)
        // and cmdTap now anchor and release through the SAME view instance,
        // so the fallback would only ever double-dispatch a tap already
        // handled above. Deleted rather than kept dead.

        return false;
    }

#ifdef SERIAL_DEBUG
    // TASK-277 [VE-1-5]: cmdTick drives the ACTIVE app's integrator. TASK-412:
    // the integrator is the shared PleditView now — this just forwards, kept
    // as its own entry point since main.cpp's cmdTick branches on which app
    // is active before calling either this or winampDisplay.tickScroll()
    // directly.
    void tickScrollDebug(float dt) { winampDisplay.tickScroll(dt); }
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
            // TASK-412: served from the shared PleditView now — the JSON
            // shape and field meanings are unchanged (D14: "drag" values
            // still line up with the old WRS_IDLE/WRS_SCROLL/WRS_SCROLL_DIRECT
            // 0/1/2, since PleditView::DragMode uses the same ordinal values).
            snprintf(buf, len,
                     "\"var\":\"wrScroll\",\"offset\":%d,\"drag\":%d,\"vel\":%.4f,"
                     "\"accum\":%.4f,\"speedK\":%.4f,\"last\":true",
                     winampDisplay.pleditScrollOffset(), (int)winampDisplay.pleditDragMode(),
                     (double)winampDisplay.pleditScrollVelocity(),
                     (double)winampDisplay.pleditScrollAccum(),
                     (double)winampDisplay.pleditSpeedK());
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
        // TASK-352: T_WRUI_04 surface — session pct + the ceiling-scaled value
        // actually fed to setVolume().
        if (strcmp(var, "wrVolPct") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrVolPct\",\"pct\":%u,\"scaled\":%u,\"last\":true",
                     (unsigned)g_settings.webRadioVolumePct, (unsigned)wrScaledVolume());
            return true;
        }
        // TASK-349: T_WRUI_02 surface — raw seconds + the wrapped/displayed value.
        if (strcmp(var, "wrPlaySec") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrPlaySec\",\"sec\":%u,\"wrapped\":%u,\"last\":true",
                     (unsigned)_snapPlaySec, (unsigned)(_snapPlaySec % 6000));
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
        // TASK-393: sinceAttemptMs added — the one gating input the terminal-retry
        // check (tick(), WR_TERMINAL_RETRY_MS) didn't already expose here. autoSkip/
        // pending/state (get wrState) cover the other three ANDed conditions; this
        // closes the diagnostic gap the task's own writeup flagged ("_pendingAction's
        // actual runtime value" was already visible as `pending` above — the missing
        // read was always the elapsed-time term, not _pendingAction).
        if (strcmp(var, "wrSkip") == 0) {
            snprintf(buf, len,
                     "\"var\":\"wrSkip\",\"autoSkip\":%d,\"tried\":%u,\"retries\":%u,"
                     "\"settled\":%d,\"pending\":%u,\"sinceAttemptMs\":%u,\"last\":true",
                     (int)g_settings.webRadioAutoSkip, (unsigned)_autoSkipTried,
                     (unsigned)_stallRetries, (int)_settled, (unsigned)_pendingAction,
                     (unsigned)(millis() - _lastAttemptMs));
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
        // TASK-402 (M-WEBRADIO-POSBAR-SMOOTH, VE-4) + TASK-405 (M-WEBRADIO-POSBAR-SLEW,
        // VE-1): observability for the EMA + time-gate + slew redraw path — raw vs.
        // smoothed value, redraw count, last interval, and which of the two gates most
        // recently blocked a redraw / whether the value had already converged (needed
        // for the OQ1/OQ2 DUT tuning pass, not just whether one was skipped).
        if (strcmp(var, "wrPosbar") == 0) {
            long sinceLastMs = _lastPosbarRedrawMs
                              ? (long)(millis() - _lastPosbarRedrawMs) : -1;
            const char *skipReason =
                (_posbarLastSkipReason == PosbarSkipReason::CONVERGED) ? "converged" :
                (_posbarLastSkipReason == PosbarSkipReason::INTERVAL)  ? "interval" :
                (_posbarLastSkipReason == PosbarSkipReason::FROZEN)    ? "frozen" : "none";
            snprintf(buf, len,
                     "\"var\":\"wrPosbar\",\"bufPctRaw\":%u,\"bufPctSmoothed\":%d,"
                     "\"bufPctDrawn\":%u,\"redraws\":%u,\"sinceLastRedrawMs\":%ld,"
                     "\"lastSkipReason\":\"%s\",\"frozen\":%s,\"last\":true",
                     (unsigned)_bufPct, (int)(_bufPctSmoothed + 0.5f),
                     (unsigned)_bufPctDrawn, (unsigned)_posbarRedrawCount, sinceLastMs,
                     skipReason, _posbarFrozen ? "true" : "false");
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
        // TASK-387: real per-band spectrum observability — dump vu::specHRef()
        // (0..VIS_H bar heights, rounded) as a JSON array. Used for the DUT
        // gain-tuning pass (M-WEBRADIO-REAL-VIS-SPECTRUM.md) and by VE's
        // spectrum-liveliness regression test, same role `get wrPump` plays
        // for decode-tail: a precise numeric readout instead of pixel-diffing
        // a screendump.
        if (strcmp(var, "wrSpec") == 0) {
            float *specH = vu::specHRef();
            int n = snprintf(buf, len, "\"var\":\"wrSpec\",\"bars\":[");
            for (int i = 0; i < vu::SPEC_BARS && n < len; i++) {
                n += snprintf(buf + n, len - n, "%s%d", i ? "," : "",
                              (int)(specH[i] + 0.5f));
            }
            if (n < len) n += snprintf(buf + n, len - n, "],\"last\":true");
            return true;
        }
        // TASK-388: real waveform trace observability — dump vu::waveTraceRef()
        // (19 raw int8_t samples) as a JSON array. Same role wrSpec plays for
        // TASK-387's DUT verification.
        if (strcmp(var, "wrWave") == 0) {
            int8_t *trace = vu::waveTraceRef();
            int n = snprintf(buf, len, "\"var\":\"wrWave\",\"samples\":[");
            for (int i = 0; i < vu::SPEC_BARS && n < len; i++) {
                n += snprintf(buf + n, len - n, "%s%d", i ? "," : "", (int)trace[i]);
            }
            if (n < len) n += snprintf(buf + n, len - n, "],\"last\":true");
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
            // TASK-398: no redundant _state = STOPPED — see the STOP
            // transport button's comment above the same fix.
            _stopAudio();
            _dirty = true;
            return true;
        }
        if (strcmp(var, "wrNext") == 0) { _nextStation(); return true; }
        if (strcmp(var, "wrPrev") == 0) { _prevStation(); return true; }
        // TASK-277: WebRadio-local speed calibration (mirrors winampDisplay's
        // `set speedK` under the WebRadio dbg surface; shared default comes
        // from scrollTuning.h). TASK-412: same PleditView instance now, so
        // this and `set speedK` tune the identical value — documented
        // consequence of one shared renderer, not a bug.
        if (strcmp(var, "wrSpeedK") == 0) {
            float k = (float)atof(val);
            if (k > 0.0f && k <= 10.0f) winampDisplay.pleditSetSpeedK(k);
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
            _plSeqno++;   // TASK-412 / T_PLE_14: list identity changed
            winampDisplay.pleditScrollToRow(0);
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
                _plSeqno++;   // TASK-412 / T_PLE_14: list identity changed (now empty)
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
            _plSeqno++;   // TASK-412 / T_PLE_14: list identity changed
            winampDisplay.pleditScrollToRow(0);
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
                // one (that would create an Audio with no pump task, no mutex
                // discipline, no arena). Clamp-store-only: nothing to apply until
                // a real _play() session exists. TASK-432 made this structural:
                // the lazy-constructing wrAudio() accessor is gone, and
                // aeEnsureAudio() is only ever called from the two _play arms.
                LOG_I("webradio", "vol set=%d — no active session, not applied", v);
                return true;
            }
            // TASK-398: short-timeout, degrade-gracefully take — matches
            // wrVolumeSink()'s idiom (a drag/debug-set must never block
            // loopTask behind a busy pump), instead of the raw portMAX_DELAY
            // take this debug setter used to have, a third independent
            // freeze source distinct from _play()/_stopAudio().
            if (xSemaphoreTake(s_wrAudioMutex, WR_PUMP_READ_TIMEOUT_TICKS) == pdTRUE) {
                s_wr_audio->setVolume((uint8_t)v);
                xSemaphoreGive(s_wrAudioMutex);
                LOG_I("webradio", "vol set=%d", v);
            } else {
                LOG_I("webradio", "vol set=%d — pump busy, skipped", v);
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
        // TASK-402 (VE-1): force-writes and draws immediately, bypassing both the
        // EMA (A) and the redraw-interval floor (B) — same as before this task,
        // does NOT exercise the smoothing/rate-limit path itself. Also syncs
        // _bufPctSmoothed so a real tick() right after this hook doesn't EMA-lag
        // back toward a stale pre-override baseline.
        if (strcmp(var, "wrBufPct") == 0) {
            int p = atoi(val);
            if (p < 0) p = 0;
            if (p > 100) p = 100;
            _bufPct         = (uint8_t)p;
            _bufPctSmoothed = (float)p;
            _bufPctDrawn    = (uint8_t)p;
            _posbarSimDrainActive = false;  // TASK-405: an immediate override cancels
                                             // any in-progress simulated drain
            _posbarFrozen         = false;  // TASK-405: an immediate override isn't
                                             // subject to the dead-band either
            _drawPosbar();
            return true;
        }
        // TASK-405 (M-WEBRADIO-POSBAR-SLEW, VE-2): deterministic synthetic buffer-drain
        // injection. Unlike wrBufPct (forces + draws immediately, bypassing both gates),
        // this seeds _bufPct and lets the real per-tick EMA/slew/redraw-gate path (only
        // active while PLAYING) consume it exactly as it would a real declining buffer —
        // needed because neither wrDeadUrls (never reaches PLAYING, TASK-395) nor wrBufPct
        // (bypasses the gate) can exercise OQ2 (does a real depleting trend still show up
        // in time through the gated/slewed path) deterministically.
        // Usage: set wrPosbarSimDrain <startPct>[,<stepPerTick>]  (stepPerTick default 1,
        // decremented once per WR_POSBAR_MIN_REDRAW_MS). `set wrPosbarSimDrain 0` disables.
        if (strcmp(var, "wrPosbarSimDrain") == 0) {
            int startPct = 0, step = 1;
            sscanf(val, "%d,%d", &startPct, &step);
            if (startPct <= 0) {
                _posbarSimDrainActive = false;
                return true;
            }
            if (startPct > 100) startPct = 100;
            if (step < 1) step = 1;
            if (step > 100) step = 100;
            _posbarSimDrainActive = true;
            _posbarSimDrainStep   = (uint8_t)step;
            _posbarSimDrainLastMs = millis();
            _bufPct = (uint8_t)startPct;   // seed — next real tick's EMA picks this up
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
    // TASK-412 / ADR-059 D4: PLEDIT gesture + scroll state (formerly _wrs /
    // _dragStart* / _scrollAccum / _scrollVelocity / _scrollSpeedK /
    // _pleditDirty) now lives once, shared, in winampDisplay's PleditView —
    // reached through the winampDisplay.pledit*() entry points and
    // StationListSource below. _plSeqno is StationListSource's seqno()
    // (T_PLE_14): bumped on every station-list identity change.
    StationListSource _stationSource;
    uint32_t          _plSeqno      = 0;
    unsigned long     _lastScrollMs = 0;   // dt tracking for winampDisplay.tickScroll()
    bool        _pendingStations = false;
    // TASK-414: eject → station-list refresh cooldown (2 s), same window as
    // the Winamp logo tap's TLS-reset debounce (winampDisplay.h) — prevents
    // rapid re-taps from stacking dataTask enqueues.
    unsigned long _ejectCooldownMs = 0;
    static constexpr unsigned long EJECT_COOLDOWN_MS = 2000;
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
    // TASK-402: EMA-filtered value feeds the redraw gate + the actual draw;
    // _bufPct above stays raw (wrUnderruns/_minBufPct still read the raw
    // value per the design doc's "raw value stays available" note).
    float       _bufPctSmoothed        = 0.0f;
    unsigned long _lastPosbarRedrawMs  = 0;
    uint32_t    _posbarRedrawCount     = 0;
    // TASK-405: CONVERGED replaces the old DELTA meaning -- under the slew
    // limiter there's no jump-trigger width to fall short of, only "already
    // equals the rounded smoothed target, nothing to step" (VE-1). FROZEN
    // (live-eyeball follow-up): the near-ceiling hysteresis dead-band is
    // actively holding -- distinct from CONVERGED (which means the value
    // isn't frozen, it's just genuinely caught up to the target).
    enum class PosbarSkipReason : uint8_t { NONE = 0, CONVERGED, INTERVAL, FROZEN };
    PosbarSkipReason _posbarLastSkipReason = PosbarSkipReason::NONE;
    // TASK-405 (live-eyeball follow-up): near-ceiling hysteresis dead-band
    // state -- see WR_POSBAR_FREEZE_ENTER_PCT/EXIT_PCT's own comment.
    bool        _posbarFrozen          = false;
    // TASK-405 (M-WEBRADIO-POSBAR-SLEW, VE-2): deterministic synthetic
    // buffer-drain injection via `set wrPosbarSimDrain` -- feeds the same
    // raw input the EMA/slew logic already consumes each real tick (unlike
    // `wrBufPct`, does not call _drawPosbar() directly), so OQ2 (does a
    // real depleting trend still show up in time through the gated/slewed
    // path) is testable on purpose instead of waiting on a real stall.
    bool        _posbarSimDrainActive  = false;
    uint8_t     _posbarSimDrainStep    = 1;
    unsigned long _posbarSimDrainLastMs = 0;
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
    uint32_t    _snapPlaySec    = 0;   // TASK-349: getAudioCurrentTime(), same read block

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

    // TASK-412: force a PLEDIT repaint and re-sync the shared view's scroll
    // window to the current pick on app entry. Needed because the PLEDIT
    // scroll offset is now shared state (one PleditView instance, both
    // callers) — without this, WebRadio would inherit whatever scroll
    // position Spotify's queue was left at, or vice versa. Mirrors
    // SpotifyApp::resume()'s invalidatePlaylist() call, plus the explicit
    // keep-visible clamp the pre-merge PLEDIT copy applied inline.
    void _pleditSync() {
        winampDisplay.invalidatePlaylist();
        winampDisplay.pleditScrollToRow((int)_currentIdx);
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
            _snapPlaySec = s_wr_audio->getAudioCurrentTime();  // TASK-349
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
        // TASK-398: a connect is in flight on the pump task. Nothing is
        // playing yet at the codec level — there's nothing to stop — and
        // taking the mutex here would block loopTask for the connect's full
        // remaining duration, exactly the freeze this design exists to
        // remove. Post ABORT and let the pump/tick() reconcile _state once
        // it resolves. Never downgrade an already-posted TEARDOWN (e.g.
        // resume()'s config-diff branch calling _stopAudio() while an
        // earlier suspend()'s TEARDOWN is still pending) — TEARDOWN must
        // always win, or the arena/Audio release it guards would be silently
        // cancelled.
        //
        // wrPumpAlive() guard: dbgSet's wrEject/wrStop/wrPlay (like every
        // other app's debug setters — see main.cpp's unconditional
        // cmdSet -> webRadioDbgSet forwarding) reach this instance
        // regardless of currentAppId, including while WebRadio is
        // suspended. _state can be stale CONNECTING off-screen (nothing
        // reconciles it until tick() runs again on re-entry) even after an
        // earlier TEARDOWN has already fully resolved and self-deleted the
        // pump. Without this check, a stray off-screen call here would post
        // an orphaned ABORT into a slot with no live reader — a freshly
        // created pump task on the next _play() would then consume that
        // stale ABORT before ever seeing the real CONNECT it's about to
        // post, producing a phantom ABORTED result that tick() applies to a
        // connect that's genuinely still in flight (re-timing this design's
        // own re-entrancy/freeze bugs one layer up).
        if (_state == WRPlayState::CONNECTING) {
            if (wrPumpAlive() && s_wrPumpRequest != WrPumpRequest::TEARDOWN)
                s_wrPumpRequest = WrPumpRequest::ABORT;
            return;
        }
        // TASK-278: control call — blocking take (§Locking model). Pump task
        // persists across this stop (only suspend() tears it down).
        if (s_wr_audio) {
            xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
            s_wr_audio->stopSong();
            xSemaphoreGive(s_wrAudioMutex);
        }
        _state = WRPlayState::STOPPED;
        _pendingAction = ACT_NONE;  // TASK-234: a stop/eject cancels any deferred retry/skip
        // TASK-349: stopSong() doesn't reset the lib's internal play-time counter
        // (only the next connecttohost() does) — force the digits to 0:00 here so
        // a stopped stream doesn't leave the last-played position on screen.
        _snapPlaySec = 0;
        winampDisplay.updateTimeDigits(0);
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
        // TASK-398: a connect is already in flight on the pump task —
        // _stopAudio()'s guard and tick()'s poll own reconciling it. A
        // second _play() here would race a second connecttohost() against
        // the first over the same s_wr_audio/mutex.
        if (_state == WRPlayState::CONNECTING) return;
        // Keep the TLS yield held across the stop (see _stopAudio comment —
        // resume-then-reyield within one quantum deadlocks the handshake).
        _stopAudio(/*resumeTls=*/false);

        // TASK-277 [QM-1-3 — single rule]: a play starting while a gesture is
        // live (auto-skip is tick-driven, so this CAN coincide with a finger
        // down) cancels the gesture FIRST, then the keep-visible clamp below
        // runs. Offset stays consistent with list state; next Press re-anchors.
        // TASK-412: the gesture lives in the shared PleditView now.
        winampDisplay.pleditResetDrag();

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
        // TASK-349: station change — the lib's play-time counter only resets
        // once connecttohost() below succeeds; zero the displayed digits now
        // so a skip doesn't leave the previous station's elapsed time up.
        _snapPlaySec = 0;
        winampDisplay.updateTimeDigits(0);

        // D13: scroll PLEDIT to keep the current station visible — the
        // source doesn't reset scroll on its own (StationListSource is "the
        // same list refetched"), so the app re-syncs it explicitly on every
        // selection. markDirty() covers the case where idx was already
        // visible but the current-row highlight still needs to move.
        winampDisplay.pleditScrollToRow((int)_currentIdx);
        winampDisplay.pleditMarkDirty();

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
        // TASK-289's I2S DMA floor and TASK-432's checked allocation now both
        // live in aeEnsureAudio(), so this arm and the FILE arm cannot drift
        // apart — the DMA floor used to be a literal here and absent there,
        // which is half of why TASK-432 could reset the device from a plain
        // `set plPlay`. The degrade path below is unchanged.
        if (!aeEnsureAudio()) {
            _state = WRPlayState::ERROR_UNREACHABLE;
            spotifyTask::tlsResume();
            _spotifyYielded = false;
            _onPlaybackFailed(/*connectFail=*/true);
            _dirty = true;
            return;
        }
        // TASK-278: lazily create the pump task — AFTER mb_arena_acquire() above
        // [DEV-2-3], idempotent across churn within a session (persists until
        // suspend()).
        wrEnsurePumpTask();

        // TASK-278: control calls — blocking take (§Locking model).
        xSemaphoreTake(s_wrAudioMutex, portMAX_DELAY);
        s_wr_audio->setVolume(wrScaledVolume());  // TASK-209 ceiling + TASK-352 session pct
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
        // TASK-398 / OQ4: connecttohost() itself is the multi-second blocking
        // call (TASK-393: 7-9+s per failed attempt, 421 whole-device freezes
        // in one 4h soak) — hand it to the pump task instead of running it
        // here on loopTask. _state stays CONNECTING; tick()'s poll of
        // s_wrPumpResult reconciles PLAYING/ERROR_UNREACHABLE once the
        // pump's attempt resolves. The URL is copied into the shared buffer
        // BEFORE the request post, so the pump — which only reads it after
        // observing CONNECT — never sees a partial/stale value.
        strlcpy(wrPumpConnectUrlBuf(), _stations[idx].url, WR_PUMP_CONNECT_URL_LEN);
        // TASK-410: explicit URL kind — s_wrPumpConnectKind is state shared with
        // aeConnectFile()'s FILE arm, so a stream play after a file play must
        // reset it back, same write-before-post ordering as the buffer above.
        s_wrPumpConnectKind = WrConnectKind::URL;
        s_wrPumpRequest = WrPumpRequest::CONNECT;
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
        // TASK-352: repaintChrome() just redrew whatever pct was last cached
        // (possibly Spotify's, from before the eject) — seed the slider with
        // WebRadio's own persisted session volume.
        winampDisplay.drawVolume((int)g_settings.webRadioVolumePct);
        _drawPosbar();
        _drawTitleZone();   // TASK-254: title now carries the ICY StreamTitle inline
        // TASK-412: PLEDIT is no longer drawn here — tick() calls
        // winampDisplay.drawPlaylistFor(_stationSource) unconditionally every
        // loop, same as SpotifyApp::tick(), and the shared view's own seqno/
        // scroll gate decides whether that's a repaint or a no-op.
    }

    void _drawPosbar() {
        // TASK-253: buffer-health gradient bar. The shared renderer owns the POSBAR
        // groove sprite, so it restores the groove (handling a shrinking buffer) and
        // draws the amber→green health-tinted gradient stretched to _bufPctDrawn.
        // TASK-402: draws the gated/smoothed value (_bufPctDrawn), not raw _bufPct —
        // single instrumentation site (VE-2): this is the only place `wr.posbar` is
        // recorded, so tick()'s gated redraw, _drawFull(), and dbgSet's debug-forced
        // call all funnel through one perf path instead of fragmenting into three.
        unsigned long _t = millis();
        winampDisplay.drawBufferBar(_bufPctDrawn);
        perf::record("wr.posbar", millis() - _t);
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

    // TASK-412: PLEDIT gesture handling (_gestureEnd/_tickScroll/
    // _updateScrollDirect) and rendering (_drawPledit) are gone — both now
    // live once, shared, in winamp/pleditView.h (PleditView), reached via
    // StationListSource and the winampDisplay.pledit*()/drawPlaylistFor()
    // entry points used above.
};
