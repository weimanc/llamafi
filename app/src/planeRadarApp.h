#pragma once
// planeRadarApp.h — ADS-B plane radar (M-PLANERADAR, TASK-304).
// Layout constants transcribed verbatim from phase0-preview-ui.md Results
// (frozen 2026-07-10, human eyeball sign-off); result shape from dataTask's
// PlaneRadarResult (ADR-048). Single-header App class, matches teletextApp.h's
// shape.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <math.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "logSink.h"
#include "gen/planeradar_airports.h"
#include "planeRadarConfig.h"
#include "util/tftViewportRepair.h"

extern TFT_eSPI tft;

// ── layout constants (phase0-preview-ui.md Results, frozen) ──────────────────
static constexpr int PR_CX = 120, PR_CY = 120, PR_R = 118;   // disc: x:2..238, y:2..238
static constexpr int PR_STRIP_X = 240, PR_STRIP_W = 35;      // x:240..274
static constexpr int PR_STRIP_LABEL_X = PR_STRIP_X + 17;     // 257
static constexpr int16_t PR_SCREEN_H = 240;                  // full display height

// ══ radar style — single style surface (TASK-312, human directive 2026-07-12) ══
// Palette + grid/symbol/tag geometry live together in this one block so a
// future style pass has exactly one place to look. Layout constants above
// (disc/strip placement) and everything below this section (timing,
// projection scale, strip row Y positions) are geometry/behaviour, not
// look-and-feel — deliberately left out.

// RGB565 palette — matched 1:1 to the reference's radar_theme.h initPalette()
// (rgb565() equivalents; see preview_planeradar.py's rgb565() block, kept in
// sync by hand — the two files don't share code, see docs). Constants with
// no reference counterpart (OUTSIDE, STRIP_*, STALE, ERROR — our square-panel
// side strip has no analogue in the reference's round-display UI) are left
// as our own design calls.
static constexpr uint16_t PR_COL_FIELD          = 0x0043;  // rgb565(4,10,28)     ref kColorBackground
static constexpr uint16_t PR_COL_OUTSIDE        = 0x0000;  // black surround outside the disc (TASK-312)
static constexpr uint16_t PR_COL_RING           = 0x1324;  // rgb565(16,100,32)   ref kColorGrid
static constexpr uint16_t PR_COL_BEZEL          = 0xFFFF;  // rgb565(255,255,255) ref kColorLabel/kColorCenter
static constexpr uint16_t PR_COL_AIRCRAFT       = 0xF800;  // rgb565(255,0,0)     ref kColorAircraft
static constexpr uint16_t PR_COL_VECTOR         = 0xF81F;  // rgb565(255,0,255)   ref kColorTrackVector
static constexpr uint16_t PR_COL_TAG_CALLSIGN   = 0xFFFF;  // rgb565(255,255,255) ref kColorLabel
static constexpr uint16_t PR_COL_TAG_TYPE       = 0xFE20;  // rgb565(255,200,0)   ref kColorTagType
static constexpr uint16_t PR_COL_TAG_ALT        = 0x5E3F;  // rgb565(90,200,255)  ref kColorTagAltitude
static constexpr uint16_t PR_COL_STRIP_BG       = 0x0842;
static constexpr uint16_t PR_COL_STRIP_TEXT     = 0xA7F4;
static constexpr uint16_t PR_COL_STALE          = 0xFDA0;
static constexpr uint16_t PR_COL_ERROR          = 0xFA08;
static constexpr uint16_t PR_COL_RUNWAY         = 0x3CB5;  // rgb565(56,150,170)  ref kColorRunway
static constexpr uint16_t PR_COL_RUNWAY_LABEL   = 0x6E9C;  // rgb565(110,210,230) ref kColorRunwayLabel

// Grid ring geometry: ring index 3 of 4 is the ring the Q5 stale indicator
// recolours in _updateStripDynamic() (TASK-312: the base grid no longer
// highlights any ring — all four rings draw PR_COL_RING now; was TASK-311
// audit finding #5's shared highlight/stale-recolour pair, before the
// highlight was removed per the 2026-07-12 human style directive).
static constexpr int16_t PR_RING_COUNT     = 4;
static constexpr int16_t PR_RING_STALE_IDX = 3;

static constexpr uint8_t PR_TAG_MAX_LINES = 3;
static constexpr uint8_t PR_TAG_LINE_LEN  = 10;

// Tag layout metrics (TASK-311 audit finding #3): font is the TFT_eSPI
// built-in size-1 font (6px advance, 8px line height); 9px is the gap kept
// between the aircraft symbol centre and the tag's near edge.
static constexpr int16_t PR_TAG_CHAR_W = 6;
static constexpr int16_t PR_TAG_LINE_H = 8;
static constexpr int16_t PR_TAG_GAP    = 9;

// Aircraft symbol geometry (TASK-311 audit finding #2; names mirror the
// reference's kAircraftNoseLenPx etc.). Wing angle is a radian offset
// applied directly to the heading angle, not a degrees value.
static constexpr float   PR_AC_NOSE_LEN       = 7.0f;
static constexpr float   PR_AC_TAIL_LEN       = 4.0f;
static constexpr float   PR_AC_WING_ANGLE     = 2.5f;   // radians, offset from nose
static constexpr int16_t PR_AC_RIMDOT_DRAW_R  = 2;
static constexpr int16_t PR_AC_RIMDOT_ERASE_R = 3;
// TASK-312: PR_R-4 (was PR_R-2) so the r=3 erase circle (PR_AC_RIMDOT_ERASE_R)
// reaches at most PR_R-1 — disc containment invariant, see _repaintDisc().
static constexpr int16_t PR_AC_RIM_RADIUS     = PR_R - 4;

// TASK-309 fix 1: symbol centroids beyond PR_R - PR_SYMBOL_INSET fall back to
// a rim dot instead of a full triangle, so no vertex (plus the ±1px erase
// pad _erasePrev() applies) can cross x=PR_STRIP_X=240 into the strip.
// Mirrors the reference's kAircraftInsideRingInsetPx (nose + tail + 1px).
// TASK-312: this same inset also satisfies the PR_R-1 disc containment
// invariant by construction — max vertex reach is
// (PR_R - PR_SYMBOL_INSET) + PR_AC_NOSE_LEN + 1px erase pad = 106+7+1 = 114,
// under PR_R-1 = 117 — no change needed for the triangle path.
static constexpr int16_t PR_SYMBOL_INSET = (int16_t)(PR_AC_NOSE_LEN + PR_AC_TAIL_LEN) + 1;  // 7+4+1=12
// ══ end radar style ═══════════════════════════════════════════════════════════

// PR_KM_PER_NM, PR_NUM_PRESETS, kPrPresetKm, kPrFetchNm live in
// planeRadarConfig.h — shared with settings/appsSection.h (TASK-310 audit
// finding #6).

// D4 (v1): location (g_settings.prLat/prLon) is a compile-time default with
// no numeric-entry UI — settingsStorage.cpp's applyDefaults() owns the actual
// default value (matches the reference project's kDefaultRadarLat/Lon);
// edited only via `run/spiffs push` (TASK-305).

// Poll cadence (D2, foreground-only) is a live setting since TASK-355
// (M-PR-MOTION Item A): g_settings.prPollSec (1–30 s, default
// PR_POLL_DEFAULT_SEC = 10 s == the old fixed PR_POLL_MS = 10000), read fresh
// each tick via _pollMs() so a Settings edit applies on the next tick.
static constexpr uint32_t PR_STALE_S = 30;      // Q5 stale threshold

// ── motion smoothing (TASK-357, EXP-014 graduation: dr-damped, tau=2, depth 1) ──
// Per aircraft: dead-reckon the rendered position from the last fix along
// track+groundspeed (same vecPx derivation the speed line already uses); on
// a new fix, do NOT snap — the just-rendered dead-reckoned position (at the
// instant the new fix lands) becomes a 2-component px offset from the new
// fix, decaying exponentially with tau = 2 s. Continuity is automatic: at
// dt=0 the offset fully cancels the fix jump, so the redraw right after a
// fetch lands exactly where the last smoothing frame left off. tau is a
// constant by design (EXP-014: tau=1 leaks visible jump, tau=4 gains
// nothing) — no settings knob. Extrapolation is capped at PR_STALE_S so a
// stale plane stops moving and hands off to the existing prStaleStyle
// treatment (never fly a ghost).
static constexpr uint32_t PR_INTERP_TICK_MS = 100;      // ~10 Hz repaint cadence
static constexpr float    PR_INTERP_TAU_MS  = 2000.0f;  // EXP-014 validated
static constexpr float    PR_INTERP_SNAP_PX = 40.0f;    // bigger correction = re-appearance -> snap to 0 offset

static constexpr float PR_MI_PER_KM      = 0.621371f;
static constexpr float PR_KM_PER_DEG_LON = 111.320f;
static constexpr float PR_KM_PER_DEG_LAT = 110.574f;

// Strip dynamic-field row Y positions (TASK-310 audit finding #5).
// AGE/ERR moved to the strip bottom (2026-07-18, Q1 amendment 4->7 slots):
// AGE fills 211..225, ERR fills 226..240 — flush against PR_SCREEN_H=240,
// freeing the y57..211 band for seven slot rows.
static constexpr int16_t PR_STRIP_ROW_RANGE_Y = 5;
static constexpr int16_t PR_STRIP_ROW_COUNT_Y = 43;
static constexpr int16_t PR_STRIP_ROW_AGE_Y   = 211;
static constexpr int16_t PR_STRIP_ROW_ERR_Y   = 226;

// Location-slot strip rows (M-PR-LOCATIONS/TASK-316, frozen at the
// 2026-07-14 eyeball gate; transcribed from preview_planeradar.py's
// PR_PREVIEW_SLOT_Y0/PITCH). Named per-row so hit-test/render code and VE
// tests reference geometry, not magic numbers (settings-nav coordinate-drift
// lesson). Q1 amendment (2026-07-18): 4 slots @ 26 px -> 7 slots @ 22 px,
// occupying the COUNT-row-to-AGE-row band exactly (hit zones [57,211)).
static constexpr int16_t PR_STRIP_ROW_LOC0_Y = 68;
static constexpr int16_t PR_STRIP_ROW_LOC1_Y = 90;
static constexpr int16_t PR_STRIP_ROW_LOC2_Y = 112;
static constexpr int16_t PR_STRIP_ROW_LOC3_Y = 134;
static constexpr int16_t PR_STRIP_ROW_LOC4_Y = 156;
static constexpr int16_t PR_STRIP_ROW_LOC5_Y = 178;
static constexpr int16_t PR_STRIP_ROW_LOC6_Y = 200;
static constexpr int16_t PR_STRIP_ROW_LOC_Y[PR_NUM_LOCS] = {
    PR_STRIP_ROW_LOC0_Y, PR_STRIP_ROW_LOC1_Y, PR_STRIP_ROW_LOC2_Y, PR_STRIP_ROW_LOC3_Y,
    PR_STRIP_ROW_LOC4_Y, PR_STRIP_ROW_LOC5_Y, PR_STRIP_ROW_LOC6_Y
};
// Half the 22 px pitch: hit-test zones tile [57,211) with no gaps/overlap.
static constexpr int16_t PR_STRIP_LOC_HIT_HALF = 11;

// One aircraft's on-screen geometry from the last render — kept so the next
// update can erase exactly what it drew (static-grid-once + symbol/tag
// erase-redraw, per the design doc's platform-infrastructure table: no
// full-frame sprite exists on this board).
struct PrRendered {
    bool    shown      = false;
    bool    rimDot     = false;
    int16_t x = 0, y = 0;
    int16_t tipX = 0, tipY = 0, lX = 0, lY = 0, rX = 0, rY = 0;
    bool    hasVector  = false;
    int16_t vecX = 0, vecY = 0;
    bool    hasTag     = false;
    int16_t tagX = 0, tagY = 0, tagW = 0, tagH = 0;
};

// Per-aircraft dr-damped(tau=2) smoothing state (TASK-357, EXP-014
// graduation), depth 1 — last fix + one 2-component px offset, no history
// arrays. Indexed like _result.aircraft[]/_prev[] between fetches; rebuilt
// by _reconcileMotion() whenever a fresh fetch lands, matching old-to-new by
// callsign (hashed — see _csHash()) so the offset (and therefore on-screen
// continuity) survives across the fetch event.
//
// Deliberately compact: the debug build (extra log/screenlog buffers) has
// only tens of bytes of static DRAM headroom on this no-PSRAM board, and
// this struct is x24 (dataTask::PR_MAX_AIRCRAFT). Fixed lat/lon is cached as
// the already-projected screen px (fixPxX/Y) rather than kept as float
// degrees — valid because every path that could change the projection scale
// (_setPreset/_setActiveLoc, via _repaintDisc()) zeroes _motionCount first,
// so a surviving fix is always still on the current scale. The offset is
// Q4 fixed-point (offXq/offYq = px * 16) — PR_INTERP_SNAP_PX bounds its
// range far under int16, and 1/16 px resolution is well past what's visible.
struct PrMotion {
    uint32_t csHash  = 0;             // identity key across fetches (0 = no callsign)
    int16_t  fixPxX = 0, fixPxY = 0;  // projected position at the fix, current scale
    int16_t  trackDeg = 0, gsKnots = 0;
    uint32_t fixMs    = 0;            // millis() at the fix — dead-reckon + decay epoch
    int16_t  offXq = 0, offYq = 0;    // Q4 fixed-point px offset, decays toward 0 from fixMs
};

class PlaneRadarApp : public App {
public:
    // TASK-312: init()-only state resets, then falls through into resume() —
    // that's the single full-paint path for both the first-ever entry and
    // every later resume(). Lines resume() already re-does on its own
    // (_applyRangeSetting(), _lastFetch seeding via _requestFetch(),
    // _prevCount via _repaintDisc()) are NOT duplicated here.
    void init() override {
        _pendingFetch   = false;
        _everHadResult  = false;
        _prErr          = false;
        _injected       = false;
        _lastHttp       = 0;
        _result         = dataTask::PlaneRadarResult{};
        _lastGoodMs     = 0;
        _lastAgeDrawSec = -1;
        _lastAction[0]  = '\0';
        resume();
    }

    void resume() override {
        // Bug found 2026-07-11 (TASK-308 fix 2): range is the one g_settings.pr*
        // field that was cached (_presetIdx) and only re-applied in init(), not
        // resume() — see _applyRangeSetting(). Mirrors AquariumApp::resume()'s
        // _applyAquariumSettings() pattern.
        // TASK-312: this is also the app's one full-paint entry point — init()
        // (above) seeds init-only state, then falls through into this same
        // routine, so no partial-grid draw path exists on first entry.
        _applyRangeSetting();
        _drawGridOnce();   // _repaintDisc() inside resets _prevCount — nothing on-screen to erase yet
        if (!_injected) _requestFetch(_forceNow());
    }

    void suspend() override {}

    // ADR-046: amber until the first result ever resolves; red while the last
    // fetch failed (cleared on next success) — same pattern as TeletextApp.
    bool isConnecting() const override { return !_everHadResult; }
    bool hasError()     const override { return _prErr; }
    bool hasPendingAsync() const override { return _pendingFetch; }

    void tick() override {
        unsigned long now = millis();

        if (!_injected && !_pendingFetch && (now - _lastFetch >= _pollMs())) {
            _requestFetch(now);
        }

        if (!_injected) {
            dataTask::PlaneRadarResult result;
            if (dataTask::pollPlaneRadar(&result)) {
                if (result.epoch != _locEpoch) {
                    // VE-PRL-6: a fetch started for the OLD location landed after
                    // _setActiveLoc() already moved on — discard rather than
                    // render aircraft against the new centre. _pendingFetch is
                    // deliberately left alone: it now tracks the NEW-epoch
                    // fetch _setActiveLoc() already enqueued.
                    LOG_D("planeradar", "stale epoch result=%u current=%u — discarded",
                          (unsigned)result.epoch, (unsigned)_locEpoch);
                } else {
                    _pendingFetch = false;
                    _lastHttp     = result.errorCode;
                    if (result.ok) {
                        _result        = result;
                        _everHadResult = true;
                        _prErr         = false;
                        _lastGoodMs    = now;
                        _reconcileMotion(now);   // TASK-357: match to old motion by callsign before drawing
                        _render(now);
                        _lastInterpMs  = now;
                    } else {
                        _prErr = true;   // stale display kept; strip shows the error code
                    }
                    _updateStripDynamic(true);
                }
            }
        }

        // TASK-357/358: ~10 Hz smoothing repaint between fetches. Dead-reckon +
        // damped-offset positions evolve every ms, but a redraw only costs
        // anything for aircraft whose pixel position actually crossed a pixel
        // between the last interp tick and now (_motionPx() is a pure
        // function of stored state + time, so evaluating it at both instants
        // IS the dirty check — no extra "last drawn px" bookkeeping needed).
        // TASK-358: per-aircraft, not whole-scene — only the dirty aircraft's
        // own footprint gets erased/redrawn/repaired, fixing the visible
        // tearing the prior whole-scene _render() call caused here.
        if (_everHadResult && now - _lastInterpMs >= PR_INTERP_TICK_MS) {
            unsigned long prevInterpMs = _lastInterpMs;
            _lastInterpMs = now;
            for (uint8_t i = 0; i < _motionCount; i++) {
                int16_t x0, y0, x1, y1;
                _motionPx(i, prevInterpMs, &x0, &y0);
                _motionPx(i, now,          &x1, &y1);
                if (x0 != x1 || y0 != y1) _redrawOneAircraft(i, now);
            }
        }

        // Age readout ticks once a second even without a new fetch.
        long ageS = _everHadResult ? (long)((now - _lastGoodMs) / 1000) : 0;
        if (ageS != _lastAgeDrawSec) {
            _lastAgeDrawSec = ageS;
            _updateStripDynamic(false);
        }
    }

    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return false;
        if (x >= PR_STRIP_X) {
            // M-PR-LOCATIONS/TASK-323: supersedes the phase0 "strip is
            // display-only" default — hit-test the 4 location-slot rows
            // (half-pitch zones, no gaps/overlap); everything else in the
            // strip (RANGE/COUNT/AGE/ERR rows) stays inert, as before.
            for (uint8_t i = 0; i < PR_NUM_LOCS; i++) {
                int16_t rowY = PR_STRIP_ROW_LOC_Y[i];
                if (y < rowY - PR_STRIP_LOC_HIT_HALF || y >= rowY + PR_STRIP_LOC_HIT_HALF) continue;
                if (g_settings.prLocs[i].label[0] == '\0') break;   // empty slot: inert
                char act[16]; snprintf(act, sizeof(act), "STRIP_LOC_%u", (unsigned)i);
                strlcpy(_lastAction, act, sizeof(_lastAction));
                _setActiveLoc(i);   // guards same-slot tap internally (no-op, no flicker)
                return true;
            }
            strlcpy(_lastAction, "STRIP_NONE", sizeof(_lastAction));
            return false;
        }
        // TASK-308 fix 5 / TASK-309 fix 2: _project()'s scale depends on
        // _presetIdx, so a range change shifts every airport/aircraft pixel
        // position — _setPreset() repaints the disc at the new scale (else the
        // old-scale runway overlay ghosts) and re-renders _result immediately
        // (else the disc sits empty of aircraft until the next poll — or,
        // under _injected, forever).
        _setPreset((uint8_t)((_presetIdx + 1) % PR_NUM_PRESETS));
        strlcpy(_lastAction, "DISC_RANGE", sizeof(_lastAction));
        if (!_injected) _requestFetch(millis());
        return true;
    }

    // M-PR-LOCATIONS: the single switch primitive (DEV-3/QM-1, BP-047/LL-110
    // — one shared sequence, never two inline copies). Exactly two call
    // sites: the strip tap above and `set prloc active <i>` in main.cpp.
    // Public so main.cpp can reach it on the file-scope g_PlaneRadarApp
    // instance, same access pattern as planeRadarDbgGet/planeRadarDbgSet.
    void _setActiveLoc(uint8_t slot) {
        if (slot >= PR_NUM_LOCS) return;                           // out of range: no-op
        if (slot == g_settings.prActiveLoc) return;                // (a) same slot: no-op, no flicker
        if (g_settings.prLocs[slot].label[0] == '\0') return;      // (a) empty slot: no-op

        // (b) copy slot -> write-through mirror, persist.
        g_settings.prLat       = g_settings.prLocs[slot].lat;
        g_settings.prLon       = g_settings.prLocs[slot].lon;
        g_settings.prActiveLoc = slot;
        SettingsStorage::save();

        // (c) DEV-3: strip must not show the old location's count/age, and
        // the ADR-046 amber "connecting" state must fire again for the new fetch.
        _result        = dataTask::PlaneRadarResult{};
        _everHadResult = false;
        _lastGoodMs    = 0;
        _prErr         = false;

        // (d) epoch bump (VE-PRL-6) before re-enqueuing, so the new fetch
        // carries the new epoch; _repaintDisc() already redraws runways via
        // _redrawGridStatics() — no separate _drawRunways() call.
        _locEpoch++;
        _repaintDisc();
        _drawLocSlots();
        _updateStripDynamic(true);   // reflect the (c) reset immediately, not stale digits
        if (!_injected) _requestFetch(_forceNow());
    }

    // ── VE debug surface (NEW-APP-CHECKLIST §3) ──────────────────────────────
    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "prAircraftCount") == 0) {
            snprintf(buf, len, "\"var\":\"prAircraftCount\",\"val\":%u,\"last\":true",
                     (unsigned)_result.count);
            return true;
        }
        if (strcmp(var, "prLastHttp") == 0) {
            snprintf(buf, len, "\"var\":\"prLastHttp\",\"val\":%d,\"last\":true", _lastHttp);
            return true;
        }
        if (strcmp(var, "prRange") == 0) {
            snprintf(buf, len, "\"var\":\"prRange\",\"val\":%u,\"last\":true",
                     (unsigned)kPrPresetKm[_presetIdx]);
            return true;
        }
        if (strcmp(var, "prLastAction") == 0) {
            snprintf(buf, len, "\"var\":\"prLastAction\",\"val\":\"%s\",\"last\":true", _lastAction);
            return true;
        }
        if (strcmp(var, "prPollSec") == 0) {   // TASK-355: T_PRM_01/02 observable
            snprintf(buf, len, "\"var\":\"prPollSec\",\"val\":%u,\"last\":true",
                     (unsigned)g_settings.prPollSec);
            return true;
        }
        if (strcmp(var, "prInterp") == 0) {
            // TASK-357: T_PRI_01 observable — motion-slot 0 (the first
            // tracked aircraft; VE drives this with a single prInjectAircraft
            // record for a controlled, deterministic read). offsetPx is the
            // decaying continuity correction's current magnitude (0 once
            // settled or for a just-appeared aircraft); fixAgeMs is how long
            // ago that slot's dead-reckon fix landed.
            bool have = _motionCount > 0;
            float offsetPx = 0.0f;
            unsigned long fixAgeMs = 0;
            if (have) {
                const PrMotion& m = _motion[0];
                fixAgeMs = millis() - m.fixMs;
                // Bug found in DUT verification (2026-07-19): reporting the raw
                // stored offXq/offYq (fixed at the fix instant) read as a flat
                // 13px for 2.5s straight instead of decaying — the stored value
                // never decays on its own, only _motionPx()'s evaluation of it
                // does. Apply the same tau=2s decay here so this observable
                // matches what's actually on screen.
                float decay = expf(-(float)fixAgeMs / PR_INTERP_TAU_MS);
                offsetPx = _distPx((float)m.offXq / 16.0f * decay, (float)m.offYq / 16.0f * decay);
            }
            snprintf(buf, len,
                     "\"var\":\"prInterp\",\"have\":%s,\"offsetPx\":%.2f,\"fixAgeMs\":%u,"
                     "\"tracked\":%u,\"last\":true",
                     have ? "true" : "false", (double)offsetPx, (unsigned)fixAgeMs,
                     (unsigned)_motionCount);
            return true;
        }
        return false;
    }

    bool dbgSet(const char* var, const char* val) {
        if (strcmp(var, "triggerPlaneRadarFetch") == 0 && strcmp(val, "1") == 0) {
            _lastFetch    = _forceNow();
            _pendingFetch = false;   // allow tick() to enqueue even if a prior fetch is pending
            return true;
        }
        if (strcmp(var, "prRange") == 0) {
            // TASK-309 fix 3: shares _setPreset() with handleInput()'s range tap
            // (was missing the disc repaint here, reproducing the stale-scale
            // runway-overlay overlap via the debug path). No fetch enqueue —
            // VE injection isolation preserved.
            int km = atoi(val);
            for (uint8_t i = 0; i < PR_NUM_PRESETS; i++)
                if (kPrPresetKm[i] == km) { _setPreset(i); break; }
            return true;
        }
        if (strcmp(var, "prPollSec") == 0) {
            // TASK-355: clamp to the slider range (mirrors load()'s
            // out-of-range guard) and persist — T_PRM_01 asserts the value
            // survives a reboot. No fetch enqueue / no _lastFetch touch: the
            // tick gate reads the value live on its next pass.
            int s = atoi(val);
            if (s < PR_POLL_MIN_SEC) s = PR_POLL_MIN_SEC;
            if (s > PR_POLL_MAX_SEC) s = PR_POLL_MAX_SEC;
            g_settings.prPollSec = (uint8_t)s;
            SettingsStorage::save();
            return true;
        }
        if (strcmp(var, "prClearInject") == 0 && strcmp(val, "1") == 0) {
            _injected     = false;
            _lastFetch    = _forceNow();
            _pendingFetch = false;
            return true;
        }
        if (strcmp(var, "prInjectAircraft") == 0) {
            // TASK-276 pattern: synthetic aircraft for VE render tests, isolated
            // from auto-refresh — tick() skips real fetch/poll while _injected.
            // Format: "" clears to zero aircraft; otherwise ';'-separated
            // records "callsign,type,lat,lon,distNm,noseDeg,trackDeg,gsKnots,altFt".
            _injected     = true;
            _pendingFetch = false;
            dataTask::PlaneRadarResult r;
            r.ok = true;
            char tmp[512];
            strlcpy(tmp, val, sizeof(tmp));
            char* saveptr = nullptr;
            char* rec = strtok_r(tmp, ";", &saveptr);
            while (rec && r.count < dataTask::PR_MAX_AIRCRAFT) {
                char callsign[16] = {}, type[8] = {};
                float lat = 0, lon = 0, dist = 0;
                int   nose = 0, trk = 0, gs = 0;
                long  alt = 0;
                int n = sscanf(rec, "%15[^,],%7[^,],%f,%f,%f,%d,%d,%d,%ld",
                               callsign, type, &lat, &lon, &dist, &nose, &trk, &gs, &alt);
                if (n == 9) {
                    dataTask::PrAircraft ac{};
                    strlcpy(ac.callsign, callsign, sizeof(ac.callsign));
                    strlcpy(ac.type, type, sizeof(ac.type));
                    ac.lat = lat; ac.lon = lon; ac.distNm = dist;
                    ac.noseDeg = (int16_t)nose; ac.trackDeg = (int16_t)trk;
                    ac.gsKnots = (int16_t)gs;   ac.altFt   = (int32_t)alt;
                    r.aircraft[r.count++] = ac;
                }
                rec = strtok_r(nullptr, ";", &saveptr);
            }
            _result        = r;
            _everHadResult = true;
            _prErr         = false;
            _lastHttp      = 0;
            _lastGoodMs    = millis();
            // TASK-357: reconcile before render — two successive injections
            // with a repeated callsign exercise the dr-damped continuity path
            // exactly like a real fetch pair, which is how T_PRI_01 drives it.
            _reconcileMotion(_lastGoodMs);
            _render(_lastGoodMs);
            _lastInterpMs  = _lastGoodMs;
            _updateStripDynamic(true);
            return true;
        }
        return false;
    }

private:
    uint8_t       _presetIdx      = 1;
    bool          _pendingFetch   = false;
    bool          _everHadResult  = false;
    bool          _prErr          = false;
    bool          _injected       = false;
    int           _lastHttp       = 0;
    unsigned long _lastFetch      = 0;
    unsigned long _lastGoodMs     = 0;
    long          _lastAgeDrawSec = -1;
    char          _lastAction[16] = {};
    uint8_t       _locEpoch       = 0;   // VE-PRL-6: bumped by _setActiveLoc(), echoed via enqueuePlaneRadar()

    dataTask::PlaneRadarResult _result;
    PrRendered _prev[dataTask::PR_MAX_AIRCRAFT];
    uint8_t    _prevCount = 0;

    // TASK-357: motion smoothing. _motion[i] tracks _result.aircraft[i]
    // between fetches; _reconcileMotion() rebuilds it (matched by callsign)
    // each time a new fetch lands. _lastInterpMs paces the ~10 Hz repaint
    // tick independent of the (much slower) fetch cadence.
    //
    // Heap-allocated (via _ensureMotion(), lazily on first reconcile), NOT a
    // static x24 array: the debug build (SERIAL_DEBUG's membudget probes +
    // TOUCH_DEBUG_OVERLAY) has only tens of bytes of .bss/.data headroom left
    // on this no-PSRAM board — a static array here overflowed dram0_0_seg by
    // hundreds of bytes even after shrinking PrMotion to its current 20-byte
    // fixed-point form. 480 B total is a one-time allocation, held for the
    // app's lifetime (never freed/reallocated), so it does not contend with
    // the large-contiguous-block concerns M-AQUARIUM's sprite-heap-arbitration
    // exists for (that mechanism is for apps holding/releasing large pools —
    // not applicable at this size).
    PrMotion*     _motion        = nullptr;
    uint8_t       _motionCount   = 0;
    unsigned long _lastInterpMs  = 0;

    // Lazily heap-allocate _motion on first use; returns false (leaving
    // _motion null) on the OOM edge case, which callers treat the same as
    // "nothing tracked yet" — _render()'s `i < _motionCount` guard already
    // falls back to raw fix positions, so a failed allocation just means no
    // smoothing rather than a crash.
    bool _ensureMotion() {
        if (_motion) return true;
        _motion = new PrMotion[dataTask::PR_MAX_AIRCRAFT];
        return _motion != nullptr;
    }

    // TASK-355: live poll interval — read fresh from settings so an edit
    // applies on the next tick (no resume-diff). load() guarantees 1–30.
    static uint32_t _pollMs() { return (uint32_t)g_settings.prPollSec * 1000UL; }

    unsigned long _forceNow() const { return millis() - _pollMs(); }

    // Re-seed _presetIdx from g_settings.prRangeIdx (init()/resume() — TASK-310
    // dedup of the clamp expression whose divergence caused TASK-308 fix 2).
    void _applyRangeSetting() {
        _presetIdx = (g_settings.prRangeIdx < PR_NUM_PRESETS) ? g_settings.prRangeIdx : 1;
    }

    // Common enqueue+bookkeeping triple, was ×3 in resume()/tick()/handleInput()
    // (TASK-310). Callers gate on !_injected themselves — VE injection tests
    // rely on real fetches never firing while injected.
    void _requestFetch(unsigned long ts) {
        dataTask::enqueuePlaneRadar(g_settings.prLat, g_settings.prLon, kPrFetchNm[_presetIdx], _locEpoch);
        _lastFetch    = ts;
        _pendingFetch = true;
    }

    // Switch range preset: persist, repaint the disc at the new scale, and
    // re-render the still-valid _result immediately (TASK-309 fixes 2+3) —
    // _repaintDisc() zeroes _prevCount before _render() runs, so _render()
    // doesn't try to erase symbols at the old scale. Shared by handleInput()'s
    // range tap and dbgSet("prRange"); callers add their own fetch-enqueue
    // and _lastAction bookkeeping on top (dbgSet deliberately does not enqueue
    // a fetch — VE injection isolation).
    void _setPreset(uint8_t idx) {
        _presetIdx = idx;
        g_settings.prRangeIdx = idx;   // persists across reboot
        SettingsStorage::save();
        _repaintDisc();   // TASK-357: also zeroes _motionCount — new scale, no continuity claim
        unsigned long now = millis();
        _reconcileMotion(now);
        _render(now);
        _lastInterpMs = now;   // else the next interp tick's dirty-check compares against a stale pre-switch time
        _updateStripDynamic(true);
    }

    float _outerKm() const { return (float)kPrPresetKm[_presetIdx] * PR_FETCH_RING3_TO_OUTER; }

    // Disc px per km at the active preset — used by _project() and the
    // aircraft track-vector length in _render().
    float _pxPerKm() const { return (float)PR_R / _outerKm(); }

    // Compass bearing (degrees) -> math angle (radians) for a north-up screen:
    // the -90 rotates 0deg(north)/90deg(east) compass convention onto the
    // atan2-style 0rad(+x)/90deg(+y) screen convention cosf/sinf expect.
    static float _degToRad(float bearingDeg) {
        return (bearingDeg - 90.0f) * (float)M_PI / 180.0f;
    }

    // Pixel distance from the disc centre. Every call site (aircraft inside-
    // ring test, runway in-range gate, vector-clip threshold ×2) is a single
    // sqrtf() > PR_R comparison — de-duped from ×4 inline copies (TASK-310).
    static float _distPx(float dx, float dy) { return sqrtf(dx * dx + dy * dy); }

    // Binary-search clip of a segment endpoint onto radius PR_R-1, given a
    // start point (x0,y0) known to be inside the disc — a refinement of the
    // reference's linear t-=0.05 scan, not "parity" with it (this is NOT the
    // same algorithm). Extracted from _render()'s track-vector clip
    // (TASK-312) so _drawRunways()'s one-endpoint-out-of-disc case can share
    // it rather than duplicate the loop.
    void _clipToDisc(float x0, float y0, float* ex, float* ey) const {
        float ex0 = *ex, ey0 = *ey;
        float lo = 0.0f, hi = 1.0f;
        for (int iter = 0; iter < 12; iter++) {
            float mid = (lo + hi) / 2;
            float mx = x0 + (ex0 - x0) * mid, my = y0 + (ey0 - y0) * mid;
            float mdx = mx - PR_CX, mdy = my - PR_CY;
            if (_distPx(mdx, mdy) > (float)(PR_R - 1)) hi = mid; else lo = mid;
        }
        *ex = x0 + (ex0 - x0) * lo; *ey = y0 + (ey0 - y0) * lo;
    }

    // True if a w×h box anchored at top-left (tlx, tly) has all four corners
    // within radius PR_R-1 of the disc centre — the TASK-312 containment
    // invariant, shared by tag placement (_placeTag) and the runway ICAO
    // label (_drawRunways).
    static bool _boxInDisc(int16_t tlx, int16_t tly, int16_t w, int16_t h) {
        int16_t xs[2] = { tlx, (int16_t)(tlx + w) };
        int16_t ys[2] = { tly, (int16_t)(tly + h) };
        for (int16_t bx : xs)
            for (int16_t by : ys)
                if (_distPx((float)(bx - PR_CX), (float)(by - PR_CY)) > (float)(PR_R - 1)) return false;
        return true;
    }

    // Equirectangular lat/lon → disc px (north = up). Matches
    // preview_planeradar.py's Radar.project() exactly. Deliberate divergence
    // from the reference: cos(lat)-corrected per-axis (PR_KM_PER_DEG_LON
    // scaled by cosf(lat)) rather than the reference's flat 111.0 km/deg for
    // both axes — kept because our disc spans locations where the correction
    // is visible, not a bug to reconcile.
    void _project(float lat, float lon, int16_t* px, int16_t* py) const {
        float dxKm = (lon - g_settings.prLon) * PR_KM_PER_DEG_LON * cosf(g_settings.prLat * (float)M_PI / 180.0f);
        float dyKm = (lat - g_settings.prLat) * PR_KM_PER_DEG_LAT;
        float s    = _pxPerKm();
        *px = (int16_t)lroundf(PR_CX + dxKm * s);
        *py = (int16_t)lroundf(PR_CY - dyKm * s);
    }

    // FNV-1a over the callsign — cross-fetch identity key. Collisions
    // between two simultaneously-visible aircraft are astronomically
    // unlikely at ~20 aircraft/32 bits, and even a collision only costs one
    // mismatched (but PR_INTERP_SNAP_PX-bounded) frame, never a crash.
    static uint32_t _csHash(const char* s) {
        uint32_t h = 2166136261u;
        for (; *s; s++) { h ^= (uint8_t)*s; h *= 16777619u; }
        return h;
    }

    // TASK-357: dr-damped(tau=2) rendered position for _motion[i] at time
    // `now` — dead-reckon the last fix along track+groundspeed (same
    // kmMin -> px derivation _render()'s speed line already uses), then add
    // the decaying continuity offset on top. Caller must have i < _motionCount
    // (true for every _result-indexed caller post-reconcile).
    void _motionPx(uint8_t i, unsigned long now, int16_t* px, int16_t* py) const {
        const PrMotion& m = _motion[i];
        float dtSec = (float)(now - m.fixMs) / 1000.0f;   // unsigned subtraction wraps sanely across millis() rollover
        if (dtSec < 0.0f) dtSec = 0.0f;
        if (dtSec > (float)PR_STALE_S) dtSec = (float)PR_STALE_S;   // cap extrapolation — stale hands off to prStaleStyle
        float speedPxPerSec = (float)m.gsKnots * PR_KM_PER_NM / 3600.0f * _pxPerKm();
        float tr = _degToRad((float)m.trackDeg);
        float predX = (float)m.fixPxX + speedPxPerSec * dtSec * cosf(tr);
        float predY = (float)m.fixPxY + speedPxPerSec * dtSec * sinf(tr);
        float decay = expf(-dtSec * 1000.0f / PR_INTERP_TAU_MS);
        *px = (int16_t)lroundf(predX + (float)m.offXq / 16.0f * decay);
        *py = (int16_t)lroundf(predY + (float)m.offYq / 16.0f * decay);
    }

    // Rebuild _motion[] from the just-landed _result (identity by callsign —
    // depth 1, no history arrays). For a matched aircraft, the new offset is
    // exactly the delta between where we were CURRENTLY rendering it (dead-
    // reckoned + decayed from the OLD fix, evaluated at `now`) and the new
    // fix's raw position — so the very next _render() call draws it right
    // where the smoother left off (continuity, no teleport) and then decays
    // toward the new fix over tau=2s. Unmatched (new) aircraft get offset 0:
    // no continuity claim for a plane that just appeared. A correction bigger
    // than PR_INTERP_SNAP_PX is treated as a re-appearance (stale timeout,
    // location switch collision, etc.) and snapped to 0 rather than dragged
    // across the disc. Callers (fetch landing / injection) must have already
    // assigned the new _result before calling — old-generation continuity is
    // read from _motion[], which is only overwritten at the end here.
    void _reconcileMotion(unsigned long now) {
        if (!_ensureMotion()) { _motionCount = 0; return; }   // OOM edge case: render falls back to raw fix positions
        PrMotion next[dataTask::PR_MAX_AIRCRAFT];
        for (uint8_t i = 0; i < _result.count; i++) {
            const dataTask::PrAircraft& a = _result.aircraft[i];
            PrMotion m{};
            m.csHash   = a.callsign[0] ? _csHash(a.callsign) : 0;
            m.trackDeg = a.trackDeg;
            m.gsKnots  = a.gsKnots;
            _project(a.lat, a.lon, &m.fixPxX, &m.fixPxY);

            int8_t oldIdx = -1;
            if (m.csHash) {
                for (uint8_t j = 0; j < _motionCount; j++) {
                    if (_motion[j].csHash == m.csHash) { oldIdx = (int8_t)j; break; }
                }
            }

            if (oldIdx >= 0) {
                int16_t predX, predY;
                _motionPx((uint8_t)oldIdx, now, &predX, &predY);
                float ox = (float)(predX - m.fixPxX), oy = (float)(predY - m.fixPxY);
                if (_distPx(ox, oy) > PR_INTERP_SNAP_PX) { ox = 0.0f; oy = 0.0f; }
                m.offXq = (int16_t)lroundf(ox * 16.0f);
                m.offYq = (int16_t)lroundf(oy * 16.0f);
            }
            m.fixMs = now;
            next[i] = m;
        }
        memcpy(_motion, next, sizeof(PrMotion) * _result.count);
        _motionCount = _result.count;
    }

    // Rings + crosshair + bezel + runway overlay — the disc's static layer.
    // Called once on resume() AND after every _erasePrev() in _render() (bug
    // found 2026-07-11: _erasePrev()'s per-aircraft bounding-box erase paints
    // PR_COL_FIELD over whatever static pixels happen to fall inside it —
    // rings, crosshair lines, runway centerlines/labels — with no repair.
    // Only ring PR_RING_STALE_IDX had any repair (redrawn every second by
    // _updateStripDynamic()'s stale-age readout), so after enough traffic
    // crossed the disc the other rings + crosshair + runways visibly eroded
    // away, leaving what looked like "only 1 ring." Redrawing these thin
    // outlines is cheap — safe to repeat every ~10s poll, not just once.
    // TASK-312: all four rings draw the same PR_COL_RING now — no per-ring
    // colour variation in the base grid (the highlight was removed; the Q5
    // stale indicator still recolours ring PR_RING_STALE_IDX, but as a
    // status signal drawn in _updateStripDynamic(), not base-grid decoration).
    void _redrawGridStatics() {
        for (int i = 1; i <= PR_RING_COUNT; i++) {
            int rr = PR_R * i / PR_RING_COUNT;
            tft.drawCircle(PR_CX, PR_CY, rr, PR_COL_RING);
        }
        tft.drawFastHLine(PR_CX - PR_R, PR_CY, PR_R * 2, PR_COL_RING);
        tft.drawFastVLine(PR_CX, PR_CY - PR_R, PR_R * 2, PR_COL_RING);
        tft.fillRect(PR_CX - 1, PR_CY - 1, 3, 3, PR_COL_BEZEL);

        // Runway overlay (Q4, density=all — every in-range airport labeled).
        if (g_settings.prRunwayOverlay) _drawRunways();
    }

    // Black surround + field-colour disc + statics redraw + stale-aircraft-
    // position reset — was duplicated in handleInput()'s range tap and
    // _drawGridOnce() (TASK-310). TASK-312: field colour is now confined to
    // the disc itself (a filled circle of radius PR_R) rather than filling
    // the whole square area — everything outside the outer ring is
    // PR_COL_OUTSIDE (black). This paint is the ONLY place PR_COL_OUTSIDE is
    // drawn; every dynamic pixel afterwards (symbol/rim-dot/vector/tag draws
    // and erases) must stay inside the disc so the black surround is never
    // damaged — see the PR_R-1 containment invariant on the rim-dot, vector,
    // tag and runway code below.
    void _repaintDisc() {
        tft.fillRect(0, 0, PR_STRIP_X, PR_SCREEN_H, PR_COL_OUTSIDE);
        tft.fillCircle(PR_CX, PR_CY, PR_R, PR_COL_FIELD);
        _redrawGridStatics();
        _prevCount   = 0;   // prior aircraft pixel positions are stale after a repaint/rescale
        _motionCount = 0;   // TASK-357: and so is any dead-reckon/offset continuity built on them
    }

    void _drawGridOnce() {
        _repaintDisc();

        tft.fillRect(PR_STRIP_X, 0, PR_STRIP_W, PR_SCREEN_H, PR_COL_STRIP_BG);
        tft.drawFastVLine(PR_STRIP_X, 0, PR_SCREEN_H, PR_COL_RING);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(PR_COL_STRIP_TEXT, PR_COL_STRIP_BG);
        // Unit suffix: fixed for the duration of this resume() (settings changes
        // apply from the next resume — the app is necessarily suspended while
        // the user is in the Settings app to change it).
        tft.drawString(g_settings.prUnits ? "mi" : "km", PR_STRIP_LABEL_X, 22, 1);
        tft.setTextDatum(TL_DATUM);

        _drawLocSlots();   // Q3: N^ marker removed outright — slots take the freed band
        _updateStripDynamic(true);
    }

    // Q4 (density=all): centerlines + ICAO label for every in-range airport
    // from the ADR-049 V-europe baked DB (app/gen/planeradar_airports.{c,h},
    // TASK-306). Static — drawn once alongside the rest of the grid in
    // resume(); airports don't move, only the projection centre could (a
    // settings location change, which forces a fresh resume() anyway).
    // Outside the baked region this loop simply finds nothing in range —
    // graceful-absent per ADR-049, not a special case to handle. Gated on the
    // airport CENTRE only (> PR_R skips the whole airport, an optimisation),
    // but TASK-312 now clips/skips each runway SEGMENT and the ICAO label
    // against the PR_R-1 disc containment invariant individually (human
    // directive 2026-07-12 — supersedes the frozen phase0 doc's "drawn
    // unclipped, a runway can visibly cross the ring edge").
    void _drawRunways() {
        tft.setTextDatum(MC_DATUM);
        for (uint16_t i = 0; i < PR_AIRPORT_COUNT; i++) {
            const PrAirportRec& ap = kPrAirports[i];
            int16_t ax, ay;
            _project(ap.lat, ap.lon, &ax, &ay);
            int16_t dx = (int16_t)(ax - PR_CX), dy = (int16_t)(ay - PR_CY);
            if (_distPx((float)dx, (float)dy) > PR_R) continue;
            for (uint16_t r = 0; r < ap.rwCount; r++) {
                const PrRunwayRec& rw = kPrRunways[ap.rwOffset + r];
                int16_t lx, ly, hx, hy;
                _project(rw.leLat, rw.leLon, &lx, &ly);
                _project(rw.heLat, rw.heLon, &hx, &hy);
                bool lIn = _distPx((float)(lx - PR_CX), (float)(ly - PR_CY)) <= (float)(PR_R - 1);
                bool hIn = _distPx((float)(hx - PR_CX), (float)(hy - PR_CY)) <= (float)(PR_R - 1);
                if (!lIn && !hIn) continue;   // both endpoints outside: skip the line
                float flx = lx, fly = ly, fhx = hx, fhy = hy;
                if (lIn && !hIn)      _clipToDisc(flx, fly, &fhx, &fhy);
                else if (!lIn && hIn) _clipToDisc(fhx, fhy, &flx, &fly);
                tft.drawLine((int16_t)lroundf(flx), (int16_t)lroundf(fly),
                             (int16_t)lroundf(fhx), (int16_t)lroundf(fhy), PR_COL_RUNWAY);
            }
            // ICAO label box: MC_DATUM-centred at (ax, ay-9), width 4 chars.
            // Skip entirely (rather than clip text) if any corner would exit
            // the disc — a partially-drawn label reads worse than none.
            int16_t lw = (int16_t)(4 * PR_TAG_CHAR_W), lh = PR_TAG_LINE_H;
            int16_t ltlx = (int16_t)(ax - lw / 2), ltly = (int16_t)((ay - 9) - lh / 2);
            if (_boxInDisc(ltlx, ltly, lw, lh)) {
                char icao[5]; strlcpy(icao, ap.icao, sizeof(icao));
                tft.setTextColor(PR_COL_RUNWAY_LABEL, PR_COL_FIELD);
                tft.drawString(icao, ax, (int16_t)(ay - 9), 1);
            }
        }
        tft.setTextDatum(TL_DATUM);
    }

    // One strip row: erase-then-draw at a fixed Y, MC_DATUM text 7px below the
    // erase rect's top (was ×4 copies in _updateStripDynamic(), TASK-310).
    // Bug found 2026-07-11: MC_DATUM (center-anchored) numeric text whose
    // width shrinks between draws (e.g. aircraft count "12ac" -> "3ac", age
    // "12s" -> "9s") leaves stray old digits outside the new, narrower
    // string's bounds — setTextColor(fg,bg)'s opaque erase only covers the
    // NEW string's bounding box, not the OLD one's. Explicit fillRect erase
    // first, matching the pattern already used by WeatherApp's value fields —
    // not opaque-text alone.
    void _stripField(int16_t rowY, const char* text, uint16_t color) {
        tft.fillRect(PR_STRIP_X + 1, rowY, PR_STRIP_W - 2, 14, PR_COL_STRIP_BG);
        tft.setTextColor(color, PR_COL_STRIP_BG);
        tft.drawString(text, PR_STRIP_LABEL_X, rowY + 7, 1);
    }

    // Location-slot label rows (M-PR-LOCATIONS/TASK-316 frozen layout,
    // variant (a) inverse box — preview_planeradar.py's _location_slots()).
    // Static per location-set: called from _drawGridOnce() and again after
    // every _setActiveLoc() switch (the active row moves). Empty slots draw
    // nothing; the fillRect below still erases the row so a slot that was
    // just deleted (Settings, while this app is suspended) doesn't leave a
    // stale label behind on the next resume()'s repaint.
    void _drawLocSlots() {
        tft.setTextDatum(MC_DATUM);
        for (uint8_t i = 0; i < PR_NUM_LOCS; i++) {
            int16_t y      = PR_STRIP_ROW_LOC_Y[i];
            bool    active = (i == g_settings.prActiveLoc);
            // Erase + (active row only) inverse-box highlight in one fill.
            // 34 px usable width = strip W35 minus the x=PR_STRIP_X border line.
            uint16_t boxColor = active ? PR_COL_STRIP_TEXT : PR_COL_STRIP_BG;
            tft.fillRect(PR_STRIP_X + 1, (int16_t)(y - 5), PR_STRIP_W - 1, 10, boxColor);
            const char* label = g_settings.prLocs[i].label;
            if (label[0] == '\0') continue;   // empty slot: nothing drawn
            tft.setTextColor(active ? PR_COL_STRIP_BG : PR_COL_STRIP_TEXT, boxColor);
            tft.drawString(label, PR_STRIP_LABEL_X, y, 1);
        }
        tft.setTextDatum(TL_DATUM);
    }

    // Repaints the strip's dynamic fields. includeRangeAndCount also refreshes
    // the range digits + aircraft count (poll result or preset change);
    // otherwise only the once-a-second age readout (+ ring-colour stale shift).
    void _updateStripDynamic(bool includeRangeAndCount) {
        tft.setTextDatum(MC_DATUM);
        if (includeRangeAndCount) {
            unsigned rangeVal = g_settings.prUnits
                ? (unsigned)lroundf(kPrPresetKm[_presetIdx] * PR_MI_PER_KM)
                : (unsigned)kPrPresetKm[_presetIdx];
            char rbuf[4]; snprintf(rbuf, sizeof(rbuf), "%u", rangeVal);
            _stripField(PR_STRIP_ROW_RANGE_Y, rbuf, PR_COL_STRIP_TEXT);

            char ac[8]; snprintf(ac, sizeof(ac), "%uac", (unsigned)_result.count);
            _stripField(PR_STRIP_ROW_COUNT_Y, ac, PR_COL_STRIP_TEXT);
        }

        long ageS  = _everHadResult ? (long)((millis() - _lastGoodMs) / 1000) : 0;
        bool stale = ageS > (long)PR_STALE_S;
        char age[8]; snprintf(age, sizeof(age), "%lds", ageS);
        _stripField(PR_STRIP_ROW_AGE_Y, age, stale ? PR_COL_STALE : PR_COL_STRIP_TEXT);
        // Q5: ring-colour shift is the strip age-text's ADDITION, not a
        // replacement — the numeric fallback above is always shown regardless
        // of style (per the frozen doc). Text/Dim (never prototyped, Q5
        // caveat) skip the ring recolour and fall back to the same numeric-only
        // behaviour until a dimming-sweep visual is designed and eyeballed.
        bool ringShift = stale && (g_settings.prStaleStyle == PrStaleStyle::Ring);
        tft.drawCircle(PR_CX, PR_CY, PR_R * PR_RING_STALE_IDX / PR_RING_COUNT, ringShift ? PR_COL_STALE : PR_COL_RING);

        char err[12] = "";
        if (_prErr) snprintf(err, sizeof(err), "E%d", _lastHttp);
        _stripField(PR_STRIP_ROW_ERR_Y, err, PR_COL_ERROR);   // always clears the slot; text only when _prErr
        tft.setTextDatum(TL_DATUM);
    }

    // Draw one aircraft's symbol (rim-dot or triangle) + speed vector at
    // (x,y), populating `rd` with the drawn geometry for the next erase. Pure
    // drawing — does NOT place a tag; callers own tag placement (TASK-358:
    // extracted from _render()'s per-aircraft loop body so both _render()'s
    // full-occlusion path and _redrawOneAircraft()'s rigid-reposition path
    // call the identical symbol/vector drawing code).
    void _drawAircraftBody(const dataTask::PrAircraft& a, int16_t x, int16_t y, PrRendered& rd) {
        rd = PrRendered{};
        rd.shown = true;
        rd.x = x; rd.y = y;

        int16_t dx = (int16_t)(x - PR_CX), dy = (int16_t)(y - PR_CY);
        float distPx = _distPx((float)dx, (float)dy);

        // TASK-309 fix 1: rim-dot fallback triggers PR_SYMBOL_INSET px before
        // the ring edge (not just past it) so no triangle vertex can reach
        // the strip at x=PR_STRIP_X.
        if (distPx > PR_R - PR_SYMBOL_INSET) {
            rd.rimDot = true;
            float ang = atan2f((float)dy, (float)dx);
            rd.x = (int16_t)lroundf(PR_CX + PR_AC_RIM_RADIUS * cosf(ang));
            rd.y = (int16_t)lroundf(PR_CY + PR_AC_RIM_RADIUS * sinf(ang));
            tft.fillCircle(rd.x, rd.y, PR_AC_RIMDOT_DRAW_R, PR_COL_AIRCRAFT);
            return;
        }

        float nose = _degToRad((float)a.noseDeg);
        rd.tipX = (int16_t)lroundf(x + PR_AC_NOSE_LEN * cosf(nose));
        rd.tipY = (int16_t)lroundf(y + PR_AC_NOSE_LEN * sinf(nose));
        rd.lX   = (int16_t)lroundf(x + PR_AC_TAIL_LEN * cosf(nose + PR_AC_WING_ANGLE));
        rd.lY   = (int16_t)lroundf(y + PR_AC_TAIL_LEN * sinf(nose + PR_AC_WING_ANGLE));
        rd.rX   = (int16_t)lroundf(x + PR_AC_TAIL_LEN * cosf(nose - PR_AC_WING_ANGLE));
        rd.rY   = (int16_t)lroundf(y + PR_AC_TAIL_LEN * sinf(nose - PR_AC_WING_ANGLE));
        // TASK-312: triangle vertices already satisfy the PR_R-1 disc
        // containment invariant by construction (see PR_SYMBOL_INSET) — no
        // clip needed here.
        tft.fillTriangle(rd.tipX, rd.tipY, rd.lX, rd.lY, rd.rX, rd.rY, PR_COL_AIRCRAFT);

        if (a.gsKnots > 0) {
            // Deliberate divergence from the reference: this is the true
            // 1-minute ground distance at the active zoom (gsKnots -> km/min
            // -> px via _pxPerKm()), not the reference's fixed screen length
            // — vector length shrinks/grows with the range preset here.
            float kmMin = a.gsKnots * PR_KM_PER_NM / 60.0f;
            float vecPx = kmMin * _pxPerKm();
            float tr    = _degToRad((float)a.trackDeg);
            float ex = x + vecPx * cosf(tr), ey = y + vecPx * sinf(tr);
            float ddx = ex - PR_CX, ddy = ey - PR_CY;
            // TASK-312: clip threshold is PR_R-1 (was PR_R) — disc
            // containment invariant, so the drawn+erased line never reaches
            // the outer ring pixel. _clipToDisc() is the extracted
            // binary-search clip, shared with _drawRunways().
            if (_distPx(ddx, ddy) > (float)(PR_R - 1)) {
                _clipToDisc((float)x, (float)y, &ex, &ey);
            }
            rd.hasVector = true;
            rd.vecX = (int16_t)lroundf(ex); rd.vecY = (int16_t)lroundf(ey);
            tft.drawLine(x, y, rd.vecX, rd.vecY, PR_COL_VECTOR);
        }
    }

    // Erase previous frame's symbols/tags, draw the current _result, remember
    // the new geometry in _prev[] for next erase. TASK-357: `now` positions
    // every aircraft via _motionPx() (dead-reckon + damped offset) rather
    // than the raw fix. TASK-358: this whole-scene path is now reserved for
    // real fetch-landing/injection/preset-switch events (tick()'s ~10 Hz
    // interp tick calls the per-aircraft _redrawOneAircraft() instead) — kept
    // verbatim in shape (full erase, full grid repaint, full occlusion
    // recompute) since that's correct here, just refactored to share
    // _eraseFootprint()/_drawAircraftBody() with the new path.
    void _render(unsigned long now) {
        _erasePrev();
        _redrawGridStatics();   // repair any grid pixels the erase above chewed into

        PrRendered next[dataTask::PR_MAX_AIRCRAFT];
        uint8_t    nextCount = 0;
        PrRendered occ[dataTask::PR_MAX_AIRCRAFT];
        uint8_t    occCount  = 0;

        for (uint8_t i = 0; i < _result.count; i++) {
            const dataTask::PrAircraft& a = _result.aircraft[i];
            int16_t x, y;
            if (i < _motionCount) {
                _motionPx(i, now, &x, &y);
            } else {
                _project(a.lat, a.lon, &x, &y);   // defensive: should not happen post-reconcile
            }

            PrRendered rd;
            _drawAircraftBody(a, x, y, rd);
            if (!rd.rimDot) _placeTag(a, x, y, rd, occ, occCount);
            next[nextCount++] = rd;
        }

        memcpy(_prev, next, sizeof(PrRendered) * nextCount);
        _prevCount = nextCount;
    }

    // Erase one previously-drawn aircraft's footprint (rim-dot circle, or
    // triangle bbox + vector line + tag rect) and report the union bounding
    // box of every pixel just touched, via the (bx,by,bw,bh) out-params —
    // TASK-358: extracted from the old _erasePrev() loop body so both
    // _erasePrev() (whole-scene, ignores the bbox) and _redrawOneAircraft()
    // (per-aircraft, uses the bbox to scope grid-static repair) share the
    // identical erase logic. bw/bh are 0 if nothing was drawn (p.shown false).
    void _eraseFootprint(const PrRendered& p, int16_t& bx, int16_t& by, int16_t& bw, int16_t& bh) {
        bx = by = bw = bh = 0;
        if (!p.shown) return;
        if (p.rimDot) {
            tft.fillCircle(p.x, p.y, PR_AC_RIMDOT_ERASE_R, PR_COL_FIELD);
            bx = (int16_t)(p.x - PR_AC_RIMDOT_ERASE_R);
            by = (int16_t)(p.y - PR_AC_RIMDOT_ERASE_R);
            bw = (int16_t)(PR_AC_RIMDOT_ERASE_R * 2 + 1);   // inclusive: covers p.x-R..p.x+R
            bh = (int16_t)(PR_AC_RIMDOT_ERASE_R * 2 + 1);
            return;   // rim-dot aircraft never carry a vector or a tag
        }
        // minX/maxX/minY/maxY track an INCLUSIVE pixel extent throughout —
        // final bw/bh below add the +1 to convert to a width/height, same
        // convention fillRect()'s own (maxX-minX+1) call already used.
        int16_t minX = (int16_t)(min(min(p.tipX, p.lX), p.rX) - 1);
        int16_t maxX = (int16_t)(max(max(p.tipX, p.lX), p.rX) + 1);
        int16_t minY = (int16_t)(min(min(p.tipY, p.lY), p.rY) - 1);
        int16_t maxY = (int16_t)(max(max(p.tipY, p.lY), p.rY) + 1);
        tft.fillRect(minX, minY, (int16_t)(maxX - minX + 1), (int16_t)(maxY - minY + 1), PR_COL_FIELD);
        if (p.hasVector) {
            tft.drawLine(p.x, p.y, p.vecX, p.vecY, PR_COL_FIELD);
            minX = min(minX, (int16_t)min(p.x, p.vecX));
            maxX = max(maxX, (int16_t)max(p.x, p.vecX));
            minY = min(minY, (int16_t)min(p.y, p.vecY));
            maxY = max(maxY, (int16_t)max(p.y, p.vecY));
        }
        if (p.hasTag) {
            tft.fillRect(p.tagX, p.tagY, p.tagW, p.tagH, PR_COL_FIELD);
            minX = min(minX, p.tagX);
            maxX = max(maxX, (int16_t)(p.tagX + p.tagW - 1));
            minY = min(minY, p.tagY);
            maxY = max(maxY, (int16_t)(p.tagY + p.tagH - 1));
        }
        bx = minX; by = minY; bw = (int16_t)(maxX - minX + 1); bh = (int16_t)(maxY - minY + 1);
    }

    void _erasePrev() {
        for (uint8_t i = 0; i < _prevCount; i++) {
            int16_t bx, by, bw, bh;
            _eraseFootprint(_prev[i], bx, by, bw, bh);   // whole-scene path: bbox unused, _redrawGridStatics() repairs the full disc after
        }
    }

    // TASK-358: per-aircraft dirty-rect repaint for the ~10 Hz smoothing
    // tick. Erases only aircraft `i`'s old footprint (_prev[i]), repairs grid
    // statics scoped to that footprint's bounding box (ADR-052's
    // withViewportRepair(), instead of the whole 240px disc), redraws the
    // symbol/vector at the new dead-reckoned position, and rigidly
    // repositions its tag by the same (dx,dy) the symbol moved — no full
    // occlusion recompute, which stays reserved for _render()'s real
    // fetch-landing/injection/preset-switch path.
    //
    // Known accepted limitation: rigid tag repositioning between real fetches
    // can't detect a NEW overlap a full occlusion pass would have avoided —
    // self-corrects at the next fetch/injection landing (which calls
    // _render()). Not a regression versus pre-TASK-357 behaviour: tags didn't
    // exist mid-smoothing before TASK-357 introduced the interp tick at all.
    void _redrawOneAircraft(uint8_t i, unsigned long now) {
        if (i >= _result.count || i >= _prevCount) return;   // defensive: invariant should hold post-reconcile
        const dataTask::PrAircraft& a = _result.aircraft[i];
        PrRendered old = _prev[i];

        int16_t x, y;
        _motionPx(i, now, &x, &y);

        int16_t bx, by, bw, bh;
        _eraseFootprint(old, bx, by, bw, bh);
        if (bw > 0 && bh > 0) {
            withViewportRepair(tft, bx, by, bw, bh, [&] { _redrawGridStatics(); });
        }

        PrRendered rd;
        _drawAircraftBody(a, x, y, rd);

        // Tag: rigid reposition by the symbol's (dx,dy), no occlusion
        // recompute. Rim-dot aircraft never carry a tag (old.rimDot check);
        // any old/new rim-dot-state mismatch or off-disc landing drops the
        // tag for this tick rather than carrying it over, per the accepted
        // limitation above.
        if (old.hasTag && !old.rimDot && !rd.rimDot) {
            int16_t dx = (int16_t)(x - old.x), dy = (int16_t)(y - old.y);
            int16_t newTagX = (int16_t)(old.tagX + dx), newTagY = (int16_t)(old.tagY + dy);
            if (_boxInDisc(newTagX, newTagY, old.tagW, old.tagH)) {
                char     lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN] = {};
                uint16_t lineColors[PR_TAG_MAX_LINES] = {};
                uint8_t  nLines = _buildTagLines(a, lines, lineColors);
                _drawTagLines(lines, lineColors, nLines, newTagX, newTagY);
                rd.hasTag = true;
                rd.tagX = newTagX; rd.tagY = newTagY; rd.tagW = old.tagW; rd.tagH = old.tagH;
            }
        }

        _prev[i] = rd;
    }

    // Build the tag's text lines (callsign/type/altitude) + per-line colours
    // — pure formatting, no drawing or placement. Returns the line count.
    // TASK-358: extracted from _placeTag() so _redrawOneAircraft()'s rigid-
    // reposition path can reuse the identical formatting without touching
    // _placeTag()'s occlusion-avoidance logic.
    static uint8_t _buildTagLines(const dataTask::PrAircraft& a,
                                   char lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN],
                                   uint16_t lineColors[PR_TAG_MAX_LINES]) {
        uint8_t nLines = 0;
        const char* cs = a.callsign[0] ? a.callsign : "?";
        strlcpy(lines[nLines], cs, PR_TAG_LINE_LEN);
        lineColors[nLines++] = PR_COL_TAG_CALLSIGN;
        if (a.type[0]) {
            strlcpy(lines[nLines], a.type, PR_TAG_LINE_LEN);
            lineColors[nLines++] = PR_COL_TAG_TYPE;
        }
        if (a.altFt == INT32_MIN) {
            strlcpy(lines[nLines], "GND", PR_TAG_LINE_LEN);
            lineColors[nLines++] = PR_COL_TAG_ALT;
        } else if (a.altFt != INT32_MAX) {
            snprintf(lines[nLines], PR_TAG_LINE_LEN, "%ldft", (long)a.altFt);
            lineColors[nLines++] = PR_COL_TAG_ALT;
        }
        return nLines;
    }

    // Draw pre-built tag lines at (tx,ty) — pure drawing, no placement/
    // occlusion logic. TASK-358: extracted from _placeTag()'s trailing draw
    // loop so _redrawOneAircraft() can reuse it verbatim.
    void _drawTagLines(const char lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN],
                        const uint16_t lineColors[PR_TAG_MAX_LINES], uint8_t nLines,
                        int16_t tx, int16_t ty) {
        tft.setTextDatum(TL_DATUM);
        for (uint8_t i = 0; i < nLines; i++) {
            tft.setTextColor(lineColors[i], PR_COL_FIELD);
            tft.drawString(lines[i], tx, (int16_t)(ty + i * PR_TAG_LINE_H), 1);
        }
    }

    // Q2 tag placement: centre-side, rule (c) default — ±10/±20 px vertical
    // nudge on overlap, drop tag (keep symbol) if all four candidates collide.
    // TASK-312: in-disc containment (all four box corners within PR_R-1) is a
    // hard constraint layered over every rule, including (a) — human style
    // directive 2026-07-12, overrides the phase0 doc. TASK-358: line
    // building/drawing now delegate to _buildTagLines()/_drawTagLines(); the
    // occlusion-avoidance logic below (occ[]/overlaps/nudge ladder) is
    // unchanged.
    void _placeTag(const dataTask::PrAircraft& a, int16_t x, int16_t y, PrRendered& rd,
                   PrRendered* occ, uint8_t& occCount) {
        char     lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN] = {};
        uint16_t lineColors[PR_TAG_MAX_LINES] = {};
        uint8_t  nLines = _buildTagLines(a, lines, lineColors);

        int16_t w = 0;
        for (uint8_t i = 0; i < nLines; i++) {
            int16_t l = (int16_t)(strlen(lines[i]) * PR_TAG_CHAR_W);
            if (l > w) w = l;
        }
        int16_t h  = (int16_t)(nLines * PR_TAG_LINE_H);
        int16_t tx = (x < PR_CX) ? (int16_t)(x + PR_TAG_GAP) : (int16_t)(x - PR_TAG_GAP - w);
        int16_t ty = (int16_t)(y - h / 2);

        auto overlaps = [&](int16_t rx, int16_t ry) {
            for (uint8_t i = 0; i < occCount; i++) {
                const PrRendered& o = occ[i];
                if (!(rx + w < o.tagX || rx > o.tagX + o.tagW ||
                      ry + h < o.tagY || ry > o.tagY + o.tagH))
                    return true;
            }
            return false;
        };

        // Q2 (settings-configurable, default C): (a) reference — always place,
        // never nudge/drop, but still subject to the TASK-312 in-disc
        // containment invariant below. (b) + nudge, place at the un-nudged
        // position if all four candidates still collide (never drops) —
        // unless even the un-nudged box is out-of-disc, in which case it
        // drops like (c). (c) same nudge ladder, DROP the tag (keep the
        // symbol) if all four still collide, or if no candidate fits inside
        // the disc.
        int16_t bestY = ty;
        bool placed;
        if (g_settings.prTagRule == PrTagRule::A) {
            placed = _boxInDisc(tx, ty, w, h);
        } else {
            placed = _boxInDisc(tx, ty, w, h) && !overlaps(tx, ty);
            if (!placed) {
                static const int16_t kNudges[4] = {10, -10, 20, -20};
                for (int16_t n : kNudges) {
                    int16_t ny = (int16_t)(ty + n);
                    if (_boxInDisc(tx, ny, w, h) && !overlaps(tx, ny)) { bestY = ny; placed = true; break; }
                }
                // (b): place anyway, un-nudged — only if that box is in-disc.
                if (!placed && g_settings.prTagRule == PrTagRule::B && _boxInDisc(tx, ty, w, h))
                    placed = true;
            }
        }
        if (!placed) return;   // (c), or no in-disc candidate under any rule: drop tag, keep symbol

        rd.hasTag = true;
        rd.tagX = tx; rd.tagY = bestY; rd.tagW = w; rd.tagH = h;

        occ[occCount].tagX = tx; occ[occCount].tagY = bestY;
        occ[occCount].tagW = w;  occ[occCount].tagH = h;
        occCount++;

        _drawTagLines(lines, lineColors, nLines, tx, bestY);
    }
};
