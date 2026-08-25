#pragma once
// webRadioApp.h — International Web Radio app (M-WEBRADIO).
// Streams MP3 from radio-browser.info via ESP32-audioI2S on internal DAC GPIO26.
// No taskbar slot of its own (eject-only tail, TASK-242) — reached via the
// taskbar player-slot cycle/restore (TASK-413). Eject means "load media from
// this source" here (station-list refresh), not "switch app" (TASK-414).
// Self-contained per D0/SF.11 (M-SRCLAYOUT Stage E / TASK-471) — method
// bodies live in webRadioApp.cpp.

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

#include "display/tft.h"
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
        PlSrcKind kind() const override { return PlSrcKind::StationList; }   // P2
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

    void init() override;
    void resume() override;
    void suspend() override;
    void tick() override;

    bool hasPendingAsync() const override { return _pendingStations; }

    // TASK-314 / ADR-046: amber active-slot indicator while establishing a
    // station connection (no audio yet) — mirrors SpotifyApp/PlaneRadarApp's
    // isConnecting() pattern, reusing _state rather than adding new tracking.
    bool isConnecting() const override { return _state == WRPlayState::CONNECTING; }

    // TASK-518 (P4): WebRadio has TWO independent in-flight operations, so
    // neither existing predicate alone is the answer:
    //   1. _pendingStations — the radio-browser station-list fetch. Set at
    //      _fetchStations() (:1313, :1539), cleared in tick() when
    //      pollWebRadioStations() delivers (:568) and by abort on suspend/
    //      eject (:295, :887, :1704). Backs hasPendingAsync().
    //   2. _state == WRPlayState::CONNECTING — the stream connect, which runs
    //      on the wrPump task, not on dataTask, so no queue term can see it.
    //      Set in _play() (:1662), left on the first PLAYING/ERROR_* tick.
    // isConnecting() IS reusable here, and this is one of only two apps where
    // it is: it is transient-operation semantics (a state-machine state with
    // an entry and an exit), not a never-had-data latch. It is ORed, not used
    // alone, because it says nothing about the list fetch.
    bool hasInFlightOp() const override {
        return _pendingStations || _state == WRPlayState::CONNECTING;
    }
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

    bool handleInput(TouchPhase phase, int x, int y) override;

#ifdef SERIAL_DEBUG
    // TASK-277 [VE-1-5]: cmdTick drives the ACTIVE app's integrator. TASK-412:
    // the integrator is the shared PleditView now — this just forwards, kept
    // as its own entry point since main.cpp's cmdTick branches on which app
    // is active before calling either this or winampDisplay.tickScroll()
    // directly.
    void tickScrollDebug(float dt) { winampDisplay.tickScroll(dt); }
#endif

    // ── Serial debug surface (BP-036) ──────────────────────────────────────

    bool dbgGet(const char* var, char* buf, int len) const;
    bool dbgSet(const char* var, const char* val);

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
    void _enqueueStationFetch();

    // TASK-412: force a PLEDIT repaint and re-sync the shared view's scroll
    // window to the current pick on app entry. Needed because the PLEDIT
    // scroll offset is now shared state (one PleditView instance, both
    // callers) — without this, WebRadio would inherit whatever scroll
    // position Spotify's queue was left at, or vice versa. Mirrors
    // SpotifyApp::resume()'s invalidatePlaylist() call, plus the explicit
    // keep-visible clamp the pre-merge PLEDIT copy applied inline.
    void _pleditSync();

    // ── Audio control ──────────────────────────────────────────────────────

    // TASK-278: per-tick read — short timeout-take, degrade to the last
    // snapshot on miss rather than blocking loopTask behind a pump that may
    // be inside an in-loop() reconnect/redirect/playlist connect [DEV-2-1].
    void _refreshAudioSnapshot();

    // resumeTls=false is for _play()'s stop-then-replay path ONLY: a
    // tlsResume() followed within one scheduler quantum by a fresh tlsYield()
    // from the same task deadlocks the handshake — spotifyTask's 20 ms-sampled
    // service wait never observes the transient count==0, so it stays in the
    // old batch and never re-gives the ack the new yield is waiting on
    // (DUT-reproduced 2026-07-07 via NEXT-while-playing: loopTask parked the
    // full 150 s ceiling, serial dead). Keeping the yield held across the
    // stop removes the bounce entirely; _play() skips its re-yield when
    // _spotifyYielded is still true.
    void _stopAudio(bool resumeTls = true);

    // userInitiated=true (user picked this station) resets the auto-skip scan;
    // the auto-skip/retry dispatch passes false so the scan bound is preserved.
    void _play(uint8_t idx, bool userInitiated = true);

    // TASK-234 (ADR-045): decide what to do after a station fails to play. A stall
    // (decode/stream death) retries the same station once — the no-PSRAM decoder
    // failure is fragmentation-dependent, so a retry often lands — then advances.
    // A connect failure skips straight on (re-dialling a dead host rarely helps).
    // Advancing is bounded to one pass over the list so a fully-dead list can't
    // loop forever; the action is deferred to the next tick (no recursion).
    void _onPlaybackFailed(bool connectFail);

    void _togglePlay();
    void _prevStation();
    void _nextStation();

    // ── Display ────────────────────────────────────────────────────────────

    // Full repaint: Winamp skin background then WebRadio overlays.
    void _drawFull();
    void _drawPosbar();
    void _drawTitleZone();

    // TASK-412: PLEDIT gesture handling (_gestureEnd/_tickScroll/
    // _updateScrollDirect) and rendering (_drawPledit) are gone — both now
    // live once, shared, in winamp/pleditView.h (PleditView), reached via
    // StationListSource and the winampDisplay.pledit*()/drawPlaylistFor()
    // entry points used above.
};
