#pragma once
// planeRadarApp.h — ADS-B plane radar (M-PLANERADAR, TASK-304).
// Layout constants transcribed verbatim from phase0-preview-ui.md Results
// (frozen 2026-07-10, human eyeball sign-off); result shape from dataTask's
// PlaneRadarResult (ADR-048). Self-contained per D0/SF.11 (M-SRCLAYOUT Stage
// E / TASK-471) — method bodies live in planeRadarApp.cpp.

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

#include "display/tft.h"

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
// TASK-378: beyond-effective-horizon annulus shade (see _drawHorizonShade()).
// Native RGB565 midpoint between PR_COL_FIELD (0,2,3 in 5/6/5-bit units) and
// PR_COL_OUTSIDE (0,0,0) — G=1 (half of field's 2), B=2 (half of field's 3,
// rounded up). Computed directly from the two real constants, not derived
// through the lossy 0-255-input rgb565() helper used elsewhere in this file
// (that round trip is fine at the 4-28 magnitudes those constants use, but
// field/outside are already this close together that going through it here
// just re-derives the same handful of representable values less directly).
// Earlier candidates iterated blind against host-rendered PNG mockups,
// which turned out not to be a reliable judge of near-black RGB565 contrast
// at all (see TASK-367/378 session history) — this one was picked by human
// eyeball directly on the DUT instead, still worth a final on-device check
// after this change.
static constexpr uint16_t PR_COL_HORIZON        = 0x0022;  // native (0,1,2) — halfway FIELD(0,2,3)<->OUTSIDE(0,0,0)
// TASK-378 (human directive): a distinct warning shade for the OTHER reason
// the disc's coverage can fall short of the preset radius — TASK-361's
// radius-capped retry2 (the fetch itself asked a smaller question this
// cycle, after two straight parse failures), not the nearest-24 cap. Mirrors
// PR_COL_FIELD's (4,10,28) with R/B swapped — same magnitude, warm instead
// of cool, so it reads as a different hue rather than a different shade of
// the same one (hue differences are more perceptible than luminance-only
// steps at this end of the RGB565 range — see PR_COL_HORIZON's own
// candidate-selection history). Also a candidate, needs the same DUT eyeball
// confirmation before it locks.
static constexpr uint16_t PR_COL_HORIZON_WARN   = 0x1840;  // rgb565(24,10,4) candidate
// TASK-378: float-equality tolerance for "did this fetch use a smaller
// radius than the preset nominally covers" — the normal-path value is the
// same float round-tripped through enqueuePlaneRadar()/PlaneRadarResult, so
// it should compare exact, but this guards against any accumulated fp
// drift rather than relying on that.
static constexpr float    PR_RADIUS_CAP_EPS_NM  = 0.01f;
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
    void init() override;
    void resume() override;
    void suspend() override {}

    // ADR-046: amber until the first result ever resolves; red while the last
    // fetch failed (cleared on next success) — same pattern as TeletextApp.
    bool isConnecting() const override { return !_everHadResult; }
    bool hasError()     const override { return _prErr; }
    bool hasPendingAsync() const override { return _pendingFetch; }

    // TASK-518 (P4): in-flight = _pendingFetch — set in _requestFetch()
    // (planeRadarApp.h:669) and cleared in tick() on every delivery branch,
    // including the parse-error retry (:291, :519, :528) and the centre-moved
    // discard (:479). Transient and self-clearing on failure as well as
    // success, so hasPendingAsync() is already the answer; the App default
    // forwards to it and this override just records the reasoning at the site.
    //
    // isConnecting() NOT reusable: !_everHadResult is a never-had-data latch,
    // set true on the first good roster and only re-armed by an explicit
    // location change (:400). A PlaneRadar showing a stale roster with no
    // fetch outstanding is idle.
    bool hasInFlightOp() const override { return _pendingFetch; }

    void tick() override;
    bool handleInput(TouchPhase phase, int x, int y) override;

    // M-PR-LOCATIONS: the single switch primitive (DEV-3/QM-1, BP-047/LL-110
    // — one shared sequence, never two inline copies). Exactly two call
    // sites: the strip tap above and `set prloc active <i>` in main.cpp.
    // Public so main.cpp can reach it on the file-scope g_PlaneRadarApp
    // instance, same access pattern as planeRadarDbgGet/planeRadarDbgSet.
    void _setActiveLoc(uint8_t slot);

    // ── VE debug surface (NEW-APP-CHECKLIST §3) ──────────────────────────────
    bool dbgGet(const char* var, char* buf, int len) const;
    bool dbgSet(const char* var, const char* val);

#ifdef SERIAL_DEBUG
    // TASK-635 (M-HARNESS2 R14): `get armed` predicate — reads the existing
    // _injected flag, adds no new state.
    bool dbgArmedInjected() const { return _injected; }
#endif

private:
    uint8_t       _presetIdx      = 1;
    bool          _pendingFetch   = false;
    bool          _everHadResult  = false;
    bool          _prErr          = false;
    bool          _injected       = false;
    int           _lastHttp       = 0;
    unsigned long _lastFetch      = 0;
    // TASK-377: real millis() at the GET enqueue, always — unlike _lastFetch,
    // never backdated by _forceNow() (that backdate is deliberate for the
    // poll-interval gate above, but would make a just-landed fix look up to
    // a full _pollMs() stale if used as its age reference). _reconcileMotion()
    // stamps fixMs from this, not drain time (TASK-367: drain time let
    // 6-21s of fetch/retry transport variance masquerade as dead-reckon lead).
    unsigned long _fetchIssuedMs  = 0;
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

    // TASK-378: effective-coverage horizon — active only when the roster is
    // actually capped (_result.count == PR_MAX_AIRCRAFT), since below cap
    // every detected aircraft is shown and there's no hidden horizon.
    // Recomputed in _reconcileMotion() (same pass already scanning
    // _result.aircraft[], no extra loop).
    bool          _horizonActive = false;
    float         _horizonNm     = 0.0f;
    // TASK-378: radius-capped-retry2 indicator — active when this cycle's
    // landed result queried a smaller radius than the preset nominally
    // covers (TASK-361's degraded-fetch mitigation). Set where `result`
    // lands in tick(), not in _reconcileMotion() — this is about the FETCH,
    // not the aircraft positions. Takes precedence over _horizonActive when
    // both would apply (see _drawHorizonShade()) — a radius-capped fetch
    // already queried a smaller area, so "we don't know" is the more urgent
    // signal than "roster's genuinely full."
    bool          _radiusCapActive = false;
    float         _radiusCapNm     = 0.0f;

    // Lazily heap-allocate _motion on first use; returns false (leaving
    // _motion null) on the OOM edge case, which callers treat the same as
    // "nothing tracked yet" — _render()'s `i < _motionCount` guard already
    // falls back to raw fix positions, so a failed allocation just means no
    // smoothing rather than a crash.
    bool _ensureMotion();

    // TASK-355: live poll interval — read fresh from settings so an edit
    // applies on the next tick (no resume-diff). load() guarantees 1–30.
    static uint32_t _pollMs() { return (uint32_t)g_settings.prPollSec * 1000UL; }

    unsigned long _forceNow() const { return millis() - _pollMs(); }

    // Re-seed _presetIdx from g_settings.prRangeIdx (init()/resume() — TASK-310
    // dedup of the clamp expression whose divergence caused TASK-308 fix 2).
    void _applyRangeSetting();

    // Common enqueue+bookkeeping triple, was ×3 in resume()/tick()/handleInput()
    // (TASK-310). Callers gate on !_injected themselves — VE injection tests
    // rely on real fetches never firing while injected.
    void _requestFetch(unsigned long ts);

    // Switch range preset: persist, repaint the disc at the new scale, and
    // re-render the still-valid _result immediately (TASK-309 fixes 2+3) —
    // _repaintDisc() zeroes _prevCount before _render() runs, so _render()
    // doesn't try to erase symbols at the old scale. Shared by handleInput()'s
    // range tap and dbgSet("prRange"); callers add their own fetch-enqueue
    // and _lastAction bookkeeping on top (dbgSet deliberately does not enqueue
    // a fetch — VE injection isolation).
    void _setPreset(uint8_t idx);

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
    void _clipToDisc(float x0, float y0, float* ex, float* ey) const;

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
    void _project(float lat, float lon, int16_t* px, int16_t* py) const;

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
    void _motionPx(uint8_t i, unsigned long now, int16_t* px, int16_t* py) const;

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
    void _reconcileMotion(unsigned long now);

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
    //
    // TASK-378: `shade` gates the beyond-horizon annulus fill. Default true
    // for the two real callers of this whole-static-layer path (_repaintDisc()
    // and _render()'s once-per-fetch repair — both cheap contexts for two
    // full-radius fillCircle() calls). _redrawOneAircraft()'s ~10Hz
    // per-aircraft withViewportRepair() call passes false explicitly:
    // withViewportRepair only clips PIXEL WRITES, not the shape-iteration
    // CPU cost (see tftViewportRepair.h) — two full fillCircle(PR_R) calls
    // in that hot path would cost real CPU every dirty-aircraft tick for a
    // repaint that's 99% clipped away. Known accepted limitation (same shape
    // as _redrawOneAircraft()'s tag-reposition one below): an aircraft erase
    // that chews into the shaded annulus during interp-tick smoothing won't
    // have that patch repaired until the next real _render() — self-corrects
    // at the next fetch landing, same cadence the horizon value itself
    // changes at anyway.
    void _redrawGridStatics(bool shade = true);

    // TASK-378: SINGLE SOURCE OF TRUTH for the beyond-horizon shade —
    // precedence rule (radius-cap warn > nearest-24 neutral > none) and the
    // NM->px conversion live ONLY here. Every consumer (_drawHorizonShade()'s
    // full-disc fill, _repairHorizonShadeBox()'s per-footprint patch,
    // _bgColorAt()'s text-background lookup) calls through this instead of
    // re-deriving the rule — found duplicated across the first two during a
    // human code-review request (2026-08-01), which is exactly the
    // divergence-risk shape BP-047 warns about. Returns false (radiusPx
    // untouched) if neither condition is active or the horizon is at/past
    // the disc's own edge (nothing to shade either way).
    bool _activeShade(uint16_t& col, float& radiusPx) const;

    // TASK-378: the background colour at a single point — PR_COL_FIELD
    // inside the active horizon (or when there isn't one), the shade colour
    // beyond it. Use this anywhere a background/erase colour is needed on
    // the disc, instead of hardcoding PR_COL_FIELD — found two call sites
    // that had (_drawRunways()'s ICAO label, _drawTagLines()'s tag text),
    // both invisible to every other TASK-378 fix since text rendering's
    // setTextColor(fg,bg) erase-behind-glyph never went through
    // _drawHorizonShade()/_repairHorizonShadeBox() at all.
    uint16_t _bgColorAt(int16_t x, int16_t y) const;

    // Fill the annulus beyond the effective coverage horizon — outer
    // fillCircle first, then an inner fillCircle back to PR_COL_FIELD,
    // leaving the ring band between them. MUST be idempotent/self-
    // correcting, not additive-only: this runs once per landed fetch
    // regardless of whether a shade was active last time, so the "no active
    // shade" branch explicitly re-fills the full disc with PR_COL_FIELD —
    // bug found by human DUT eyeball (2026-08-01): an early version just
    // `return`ed there, leaving a stale shade stuck on screen after the
    // underlying condition cleared.
    void _drawHorizonShade();

    // Cheap per-footprint repair for the ~10Hz interp-tick path
    // (_redrawOneAircraft()'s withViewportRepair scope) — _eraseFootprint()
    // already filled the erased box with PR_COL_FIELD; if the box actually
    // sits beyond the active horizon, that fill was wrong and needs
    // overpainting with the shade colour, or a moving aircraft visibly
    // "wipes clean" a hole in the shaded annulus as it crosses through (bug
    // found by human DUT eyeball, 2026-08-01 — the interp-tick path
    // deliberately skips _drawHorizonShade()'s full-disc redraw for
    // performance, see _redrawGridStatics()'s comment, but that left this
    // hole unrepaired). Approximates by the box's CENTRE distance from the
    // disc centre — a box straddling the boundary line gets entirely one
    // colour, not pixel-exact, but self-corrects at the next full _render()
    // (once per fetch) regardless, and stays O(box area) instead of
    // O(disc area).
    void _repairHorizonShadeBox(int16_t bx, int16_t by, int16_t bw, int16_t bh);

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
    void _repaintDisc();
    void _drawGridOnce();

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
    void _drawRunways();

    // One strip row: erase-then-draw at a fixed Y, MC_DATUM text 7px below the
    // erase rect's top (was ×4 copies in _updateStripDynamic(), TASK-310).
    // Bug found 2026-07-11: MC_DATUM (center-anchored) numeric text whose
    // width shrinks between draws (e.g. aircraft count "12ac" -> "3ac", age
    // "12s" -> "9s") leaves stray old digits outside the new, narrower
    // string's bounds — setTextColor(fg,bg)'s opaque erase only covers the
    // NEW string's bounding box, not the OLD one's. Explicit fillRect erase
    // first, matching the pattern already used by WeatherApp's value fields —
    // not opaque-text alone.
    void _stripField(int16_t rowY, const char* text, uint16_t color);

    // Location-slot label rows (M-PR-LOCATIONS/TASK-316 frozen layout,
    // variant (a) inverse box — preview_planeradar.py's _location_slots()).
    // Static per location-set: called from _drawGridOnce() and again after
    // every _setActiveLoc() switch (the active row moves). Empty slots draw
    // nothing; the fillRect below still erases the row so a slot that was
    // just deleted (Settings, while this app is suspended) doesn't leave a
    // stale label behind on the next resume()'s repaint.
    void _drawLocSlots();

    // Repaints the strip's dynamic fields. includeRangeAndCount also refreshes
    // the range digits + aircraft count (poll result or preset change);
    // otherwise only the once-a-second age readout (+ ring-colour stale shift).
    void _updateStripDynamic(bool includeRangeAndCount);

    // Draw one aircraft's symbol (rim-dot or triangle) + speed vector at
    // (x,y), populating `rd` with the drawn geometry for the next erase. Pure
    // drawing — does NOT place a tag; callers own tag placement (TASK-358:
    // extracted from _render()'s per-aircraft loop body so both _render()'s
    // full-occlusion path and _redrawOneAircraft()'s rigid-reposition path
    // call the identical symbol/vector drawing code).
    void _drawAircraftBody(const dataTask::PrAircraft& a, int16_t x, int16_t y, PrRendered& rd);

    // Erase previous frame's symbols/tags, draw the current _result, remember
    // the new geometry in _prev[] for next erase. TASK-357: `now` positions
    // every aircraft via _motionPx() (dead-reckon + damped offset) rather
    // than the raw fix. TASK-358: this whole-scene path is now reserved for
    // real fetch-landing/injection/preset-switch events (tick()'s ~10 Hz
    // interp tick calls the per-aircraft _redrawOneAircraft() instead) — kept
    // verbatim in shape (full erase, full grid repaint, full occlusion
    // recompute) since that's correct here, just refactored to share
    // _eraseFootprint()/_drawAircraftBody() with the new path.
    void _render(unsigned long now);

    // Erase one previously-drawn aircraft's footprint (rim-dot circle, or
    // triangle bbox + vector line + tag rect) and report the union bounding
    // box of every pixel just touched, via the (bx,by,bw,bh) out-params —
    // TASK-358: extracted from the old _erasePrev() loop body so both
    // _erasePrev() (whole-scene, ignores the bbox) and _redrawOneAircraft()
    // (per-aircraft, uses the bbox to scope grid-static repair) share the
    // identical erase logic. bw/bh are 0 if nothing was drawn (p.shown false).
    void _eraseFootprint(const PrRendered& p, int16_t& bx, int16_t& by, int16_t& bw, int16_t& bh);

    void _erasePrev();

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
    void _redrawOneAircraft(uint8_t i, unsigned long now);

    // Build the tag's text lines (callsign/type/altitude) + per-line colours
    // — pure formatting, no drawing or placement. Returns the line count.
    // TASK-358: extracted from _placeTag() so _redrawOneAircraft()'s rigid-
    // reposition path can reuse the identical formatting without touching
    // _placeTag()'s occlusion-avoidance logic.
    static uint8_t _buildTagLines(const dataTask::PrAircraft& a,
                                   char lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN],
                                   uint16_t lineColors[PR_TAG_MAX_LINES]);

    // Draw pre-built tag lines at (tx,ty) — pure drawing, no placement/
    // occlusion logic. TASK-358: extracted from _placeTag()'s trailing draw
    // loop so _redrawOneAircraft() can reuse it verbatim.
    void _drawTagLines(const char lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN],
                        const uint16_t lineColors[PR_TAG_MAX_LINES], uint8_t nLines,
                        int16_t tx, int16_t ty);

    // Q2 tag placement: centre-side, rule (c) default — ±10/±20 px vertical
    // nudge on overlap, drop tag (keep symbol) if all four candidates collide.
    // TASK-312: in-disc containment (all four box corners within PR_R-1) is a
    // hard constraint layered over every rule, including (a) — human style
    // directive 2026-07-12, overrides the phase0 doc. TASK-358: line
    // building/drawing now delegate to _buildTagLines()/_drawTagLines(); the
    // occlusion-avoidance logic below (occ[]/overlaps/nudge ladder) is
    // unchanged.
    void _placeTag(const dataTask::PrAircraft& a, int16_t x, int16_t y, PrRendered& rd,
                   PrRendered* occ, uint8_t& occCount);
};
