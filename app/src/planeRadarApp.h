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

extern TFT_eSPI tft;

// ── layout constants (phase0-preview-ui.md Results, frozen) ──────────────────
static constexpr int PR_CX = 120, PR_CY = 120, PR_R = 118;   // disc: x:2..238, y:2..238
static constexpr int PR_STRIP_X = 240, PR_STRIP_W = 35;      // x:240..274
static constexpr int PR_STRIP_LABEL_X = PR_STRIP_X + 17;     // 257

// RGB565 palette (radar_theme.h equivalents — see preview_planeradar.py's
// rgb565() block; values here are that same (r,g,b) set packed to RGB565).
static constexpr uint16_t PR_COL_FIELD      = 0x0006;
static constexpr uint16_t PR_COL_RING       = 0x0304;
static constexpr uint16_t PR_COL_RING_HI    = 0x0466;
static constexpr uint16_t PR_COL_BEZEL      = 0xFFFF;
static constexpr uint16_t PR_COL_AIRCRAFT   = 0xF904;
static constexpr uint16_t PR_COL_VECTOR     = 0xF81F;
static constexpr uint16_t PR_COL_TAG        = 0xCE59;
static constexpr uint16_t PR_COL_STRIP_BG   = 0x0842;
static constexpr uint16_t PR_COL_STRIP_TEXT = 0xA7F4;
static constexpr uint16_t PR_COL_STALE      = 0xFDA0;
static constexpr uint16_t PR_COL_ERROR      = 0xFA08;
static constexpr uint16_t PR_COL_RUNWAY = 0x0514;

static constexpr float    PR_KM_PER_NM    = 1.852f;
static constexpr uint8_t  PR_NUM_PRESETS  = 4;
static constexpr uint16_t kPrPresetKm[PR_NUM_PRESETS] = {5, 10, 15, 25};
// Fetch radius (NM) per preset — reference's fetchRadiusKm() margin factor
// (preset_km * 4/3 * 118/107), converted NM, per phase0-api-probe.md. Wider
// than the display range (outer_km = preset*4/3) so traffic doesn't pop in
// right at the ring edge.
static constexpr float kPrFetchNm[PR_NUM_PRESETS] = {4.0f, 7.9f, 11.9f, 19.9f};

// D4 (v1): location (g_settings.prLat/prLon) is a compile-time default with
// no numeric-entry UI — settingsStorage.cpp's applyDefaults() owns the actual
// default value (matches the reference project's kDefaultRadarLat/Lon);
// edited only via `run/spiffs push` (TASK-305).

static constexpr uint32_t PR_POLL_MS = 10000;  // D2 cadence, foreground-only
static constexpr uint32_t PR_STALE_S = 30;      // Q5 stale threshold

static constexpr uint8_t PR_TAG_MAX_LINES = 3;
static constexpr uint8_t PR_TAG_LINE_LEN  = 10;

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

class PlaneRadarApp : public App {
public:
    void init() override {
        _presetIdx     = (g_settings.prRangeIdx < PR_NUM_PRESETS) ? g_settings.prRangeIdx : 1;
        _pendingFetch  = false;
        _everHadResult = false;
        _prErr         = false;
        _injected      = false;
        _lastHttp      = 0;
        _result        = dataTask::PlaneRadarResult{};
        _prevCount     = 0;
        _lastFetch     = _forceNow();
        _lastGoodMs    = 0;
        _lastAgeDrawSec = -1;
        _lastAction[0] = '\0';
    }

    void resume() override {
        // Bug found 2026-07-11: every other g_settings.pr* field (units, runway
        // toggle, tag rule, stale style) is read live at point-of-use, so a
        // Settings-app change takes effect on the very next poll/redraw. Range
        // is the one exception — it's cached into _presetIdx, and only init()
        // was refreshing that cache, never resume(). Changing the range preset
        // via Settings > Applications (necessarily done while this app is
        // suspended) silently had no live effect until the next reboot, even
        // though g_settings.prRangeIdx itself was correctly updated and
        // persisted. Mirrors AquariumApp::resume()'s _applyAquariumSettings()
        // pattern — re-apply cached settings on every resume(), not just init().
        _presetIdx = (g_settings.prRangeIdx < PR_NUM_PRESETS) ? g_settings.prRangeIdx : 1;
        _drawGridOnce();
        _prevCount = 0;   // fresh grid paint — nothing on-screen to erase yet
        _lastFetch = _forceNow();
        if (!_injected) {
            dataTask::enqueuePlaneRadar(g_settings.prLat, g_settings.prLon, kPrFetchNm[_presetIdx]);
            _pendingFetch = true;
        }
    }

    void suspend() override {}

    // ADR-046: amber until the first result ever resolves; red while the last
    // fetch failed (cleared on next success) — same pattern as TeletextApp.
    bool isConnecting() const override { return !_everHadResult; }
    bool hasError()     const override { return _prErr; }
    bool hasPendingAsync() const override { return _pendingFetch; }

    void tick() override {
        unsigned long now = millis();

        if (!_injected && !_pendingFetch && (now - _lastFetch >= PR_POLL_MS)) {
            dataTask::enqueuePlaneRadar(g_settings.prLat, g_settings.prLon, kPrFetchNm[_presetIdx]);
            _lastFetch    = now;
            _pendingFetch = true;
        }

        if (!_injected) {
            dataTask::PlaneRadarResult result;
            if (dataTask::pollPlaneRadar(&result)) {
                _pendingFetch = false;
                _lastHttp     = result.errorCode;
                if (result.ok) {
                    _result        = result;
                    _everHadResult = true;
                    _prErr         = false;
                    _lastGoodMs    = now;
                    _render();
                } else {
                    _prErr = true;   // stale display kept; strip shows the error code
                }
                _updateStripDynamic(true);
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
            strlcpy(_lastAction, "STRIP_NONE", sizeof(_lastAction));
            return false;   // strip is display-only (phase0-preview-ui.md)
        }
        _presetIdx = (uint8_t)((_presetIdx + 1) % PR_NUM_PRESETS);
        g_settings.prRangeIdx = _presetIdx;   // persists across reboot (exit criterion 2)
        SettingsStorage::save();
        strlcpy(_lastAction, "DISC_RANGE", sizeof(_lastAction));
        // Bug found 2026-07-11: _project()'s scale is PR_R / _outerKm(), which
        // changes with _presetIdx — every airport (and aircraft) pixel position
        // shifts on a range change. Rings/crosshair/bezel are fixed pixel
        // geometry (unaffected), but the runway overlay was left at its OLD
        // scale until the next poll's _render() drew the NEW scale on top
        // without erasing the old one first — old+new runway lines/labels
        // visibly overlapping. Full field repaint here is the same fix as a
        // fresh resume(), scoped to just the disc (strip is handled by
        // _updateStripDynamic() below).
        tft.fillRect(0, 0, PR_STRIP_X, 240, PR_COL_FIELD);
        _redrawGridStatics();
        _prevCount = 0;   // old aircraft pixel positions are stale after a rescale
        _updateStripDynamic(true);
        if (!_injected) {
            dataTask::enqueuePlaneRadar(g_settings.prLat, g_settings.prLon, kPrFetchNm[_presetIdx]);
            _lastFetch    = millis();
            _pendingFetch = true;
        }
        return true;
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
        return false;
    }

    bool dbgSet(const char* var, const char* val) {
        if (strcmp(var, "triggerPlaneRadarFetch") == 0 && strcmp(val, "1") == 0) {
            _lastFetch    = _forceNow();
            _pendingFetch = false;   // allow tick() to enqueue even if a prior fetch is pending
            return true;
        }
        if (strcmp(var, "prRange") == 0) {
            int km = atoi(val);
            for (uint8_t i = 0; i < PR_NUM_PRESETS; i++)
                if (kPrPresetKm[i] == km) {
                    _presetIdx = i;
                    g_settings.prRangeIdx = i;
                    SettingsStorage::save();
                    _updateStripDynamic(true);
                    break;
                }
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
            _render();
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

    dataTask::PlaneRadarResult _result;
    PrRendered _prev[dataTask::PR_MAX_AIRCRAFT];
    uint8_t    _prevCount = 0;

    unsigned long _forceNow() const { return millis() - PR_POLL_MS; }

    float _outerKm() const { return (float)kPrPresetKm[_presetIdx] * 4.0f / 3.0f; }

    // Equirectangular lat/lon → disc px (north = up). Matches
    // preview_planeradar.py's Radar.project() exactly.
    void _project(float lat, float lon, int16_t* px, int16_t* py) const {
        float dxKm = (lon - g_settings.prLon) * 111.320f * cosf(g_settings.prLat * (float)M_PI / 180.0f);
        float dyKm = (lat - g_settings.prLat) * 110.574f;
        float s    = (float)PR_R / _outerKm();
        *px = (int16_t)lroundf(PR_CX + dxKm * s);
        *py = (int16_t)lroundf(PR_CY - dyKm * s);
    }

    // Rings + crosshair + bezel + runway overlay — the disc's static layer.
    // Called once on resume() AND after every _erasePrev() in _render() (bug
    // found 2026-07-11: _erasePrev()'s per-aircraft bounding-box erase paints
    // PR_COL_FIELD over whatever static pixels happen to fall inside it —
    // rings, crosshair lines, runway centerlines/labels — with no repair.
    // Only ring 3 had any repair (redrawn every second by
    // _updateStripDynamic()'s stale-age readout), so after enough traffic
    // crossed the disc the other 3 rings + crosshair + runways visibly eroded
    // away, leaving what looked like "only 1 ring." Redrawing these thin
    // outlines is cheap — safe to repeat every ~10s poll, not just once.
    void _redrawGridStatics() {
        for (int i = 1; i <= 4; i++) {
            int rr = PR_R * i / 4;
            tft.drawCircle(PR_CX, PR_CY, rr, (i == 3) ? PR_COL_RING_HI : PR_COL_RING);
        }
        tft.drawFastHLine(PR_CX - PR_R, PR_CY, PR_R * 2, PR_COL_RING);
        tft.drawFastVLine(PR_CX, PR_CY - PR_R, PR_R * 2, PR_COL_RING);
        tft.fillRect(PR_CX - 1, PR_CY - 1, 3, 3, PR_COL_BEZEL);

        // Runway overlay (Q4, density=all — every in-range airport labeled).
        if (g_settings.prRunwayOverlay) _drawRunways();
    }

    void _drawGridOnce() {
        tft.fillRect(0, 0, PR_STRIP_X, 240, PR_COL_FIELD);
        _redrawGridStatics();

        tft.fillRect(PR_STRIP_X, 0, PR_STRIP_W, 240, PR_COL_STRIP_BG);
        tft.drawFastVLine(PR_STRIP_X, 0, 240, PR_COL_RING);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(PR_COL_STRIP_TEXT, PR_COL_STRIP_BG);
        // Unit suffix: fixed for the duration of this resume() (settings changes
        // apply from the next resume — the app is necessarily suspended while
        // the user is in the Settings app to change it).
        tft.drawString(g_settings.prUnits ? "mi" : "km", PR_STRIP_LABEL_X, 22, 1);
        tft.setTextColor(PR_COL_BEZEL, PR_COL_STRIP_BG);
        tft.drawString("N^", PR_STRIP_LABEL_X, 120, 1);  // static bezel marker
        tft.setTextDatum(TL_DATUM);

        _updateStripDynamic(true);
    }

    // Q4 (density=all): centerlines + ICAO label for every in-range airport
    // from the ADR-049 V-europe baked DB (app/gen/planeradar_airports.{c,h},
    // TASK-306). Static — drawn once alongside the rest of the grid in
    // resume(); airports don't move, only the projection centre could (a
    // settings location change, which forces a fresh resume() anyway).
    // Outside the baked region this loop simply finds nothing in range —
    // graceful-absent per ADR-049, not a special case to handle.
    void _drawRunways() {
        tft.setTextDatum(MC_DATUM);
        for (uint16_t i = 0; i < PR_AIRPORT_COUNT; i++) {
            const PrAirportRec& ap = kPrAirports[i];
            int16_t ax, ay;
            _project(ap.lat, ap.lon, &ax, &ay);
            int16_t dx = (int16_t)(ax - PR_CX), dy = (int16_t)(ay - PR_CY);
            if (sqrtf((float)dx * dx + (float)dy * dy) > PR_R) continue;
            for (uint16_t r = 0; r < ap.rwCount; r++) {
                const PrRunwayRec& rw = kPrRunways[ap.rwOffset + r];
                int16_t lx, ly, hx, hy;
                _project(rw.leLat, rw.leLon, &lx, &ly);
                _project(rw.heLat, rw.heLon, &hx, &hy);
                tft.drawLine(lx, ly, hx, hy, PR_COL_RUNWAY);
            }
            char icao[5]; strlcpy(icao, ap.icao, sizeof(icao));
            tft.setTextColor(PR_COL_RUNWAY, PR_COL_FIELD);
            tft.drawString(icao, ax, (int16_t)(ay - 9), 1);
        }
        tft.setTextDatum(TL_DATUM);
    }

    // Repaints the strip's dynamic fields. includeRangeAndCount also refreshes
    // the range digits + aircraft count (poll result or preset change);
    // otherwise only the once-a-second age readout (+ ring-colour stale shift).
    void _updateStripDynamic(bool includeRangeAndCount) {
        tft.setTextDatum(MC_DATUM);
        // Bug found 2026-07-11: MC_DATUM (center-anchored) numeric text whose
        // width shrinks between draws (e.g. aircraft count "12ac" -> "3ac",
        // age "12s" -> "9s") leaves stray old digits outside the new, narrower
        // string's bounds — setTextColor(fg,bg)'s opaque erase only covers the
        // NEW string's bounding box, not the OLD one's. Explicit fillRect erase
        // first, matching the pattern already used for the error slot below
        // (and WeatherApp's value fields) — not opaque-text alone.
        if (includeRangeAndCount) {
            tft.fillRect(PR_STRIP_X + 1, 5, PR_STRIP_W - 2, 14, PR_COL_STRIP_BG);
            tft.setTextColor(PR_COL_STRIP_TEXT, PR_COL_STRIP_BG);
            unsigned rangeVal = g_settings.prUnits
                ? (unsigned)lroundf(kPrPresetKm[_presetIdx] * 0.621371f)
                : (unsigned)kPrPresetKm[_presetIdx];
            char rbuf[4]; snprintf(rbuf, sizeof(rbuf), "%u", rangeVal);
            tft.drawString(rbuf, PR_STRIP_LABEL_X, 12, 1);

            tft.fillRect(PR_STRIP_X + 1, 43, PR_STRIP_W - 2, 14, PR_COL_STRIP_BG);
            tft.setTextColor(PR_COL_TAG, PR_COL_STRIP_BG);
            char ac[8]; snprintf(ac, sizeof(ac), "%uac", (unsigned)_result.count);
            tft.drawString(ac, PR_STRIP_LABEL_X, 50, 1);
        }

        long ageS  = _everHadResult ? (long)((millis() - _lastGoodMs) / 1000) : 0;
        bool stale = ageS > (long)PR_STALE_S;
        tft.fillRect(PR_STRIP_X + 1, 193, PR_STRIP_W - 2, 14, PR_COL_STRIP_BG);
        tft.setTextColor(stale ? PR_COL_STALE : PR_COL_TAG, PR_COL_STRIP_BG);
        char age[8]; snprintf(age, sizeof(age), "%lds", ageS);
        tft.drawString(age, PR_STRIP_LABEL_X, 200, 1);
        // Q5: ring-colour shift is the strip age-text's ADDITION, not a
        // replacement — the numeric fallback above is always shown regardless
        // of style (per the frozen doc). Text/Dim (never prototyped, Q5
        // caveat) skip the ring recolour and fall back to the same numeric-only
        // behaviour until a dimming-sweep visual is designed and eyeballed.
        bool ringShift = stale && (g_settings.prStaleStyle == PrStaleStyle::Ring);
        tft.drawCircle(PR_CX, PR_CY, PR_R * 3 / 4, ringShift ? PR_COL_STALE : PR_COL_RING_HI);

        tft.fillRect(PR_STRIP_X + 1, 213, PR_STRIP_W - 2, 14, PR_COL_STRIP_BG);  // clear error slot
        if (_prErr) {
            char err[12]; snprintf(err, sizeof(err), "E%d", _lastHttp);
            tft.setTextColor(PR_COL_ERROR, PR_COL_STRIP_BG);
            tft.drawString(err, PR_STRIP_LABEL_X, 220, 1);
        }
        tft.setTextDatum(TL_DATUM);
    }

    // Erase previous frame's symbols/tags, draw the current _result, remember
    // the new geometry in _prev[] for next erase.
    void _render() {
        _erasePrev();
        _redrawGridStatics();   // repair any grid pixels the erase above chewed into

        PrRendered next[dataTask::PR_MAX_AIRCRAFT];
        uint8_t    nextCount = 0;
        PrRendered occ[dataTask::PR_MAX_AIRCRAFT];
        uint8_t    occCount  = 0;

        for (uint8_t i = 0; i < _result.count; i++) {
            const dataTask::PrAircraft& a = _result.aircraft[i];
            int16_t x, y;
            _project(a.lat, a.lon, &x, &y);
            int16_t dx = (int16_t)(x - PR_CX), dy = (int16_t)(y - PR_CY);
            float distPx = sqrtf((float)dx * dx + (float)dy * dy);

            PrRendered rd{};
            rd.shown = true;
            rd.x = x; rd.y = y;

            if (distPx > PR_R) {
                rd.rimDot = true;
                float ang = atan2f((float)dy, (float)dx);
                rd.x = (int16_t)lroundf(PR_CX + (PR_R - 2) * cosf(ang));
                rd.y = (int16_t)lroundf(PR_CY + (PR_R - 2) * sinf(ang));
                tft.fillCircle(rd.x, rd.y, 2, PR_COL_AIRCRAFT);
                next[nextCount++] = rd;
                continue;
            }

            float nose = (float)(a.noseDeg - 90) * (float)M_PI / 180.0f;
            rd.tipX = (int16_t)lroundf(x + 7 * cosf(nose));
            rd.tipY = (int16_t)lroundf(y + 7 * sinf(nose));
            rd.lX   = (int16_t)lroundf(x + 4 * cosf(nose + 2.5f));
            rd.lY   = (int16_t)lroundf(y + 4 * sinf(nose + 2.5f));
            rd.rX   = (int16_t)lroundf(x + 4 * cosf(nose - 2.5f));
            rd.rY   = (int16_t)lroundf(y + 4 * sinf(nose - 2.5f));
            tft.fillTriangle(rd.tipX, rd.tipY, rd.lX, rd.lY, rd.rX, rd.rY, PR_COL_AIRCRAFT);

            if (a.gsKnots > 0) {
                float kmMin = a.gsKnots * PR_KM_PER_NM / 60.0f;
                float vecPx = kmMin * ((float)PR_R / _outerKm());
                float tr    = (float)(a.trackDeg - 90) * (float)M_PI / 180.0f;
                float ex = x + vecPx * cosf(tr), ey = y + vecPx * sinf(tr);
                float ddx = ex - PR_CX, ddy = ey - PR_CY;
                if (sqrtf(ddx * ddx + ddy * ddy) > PR_R) {
                    // Binary-clip the endpoint back onto the ring (reference parity).
                    float lo = 0.0f, hi = 1.0f;
                    for (int iter = 0; iter < 12; iter++) {
                        float mid = (lo + hi) / 2;
                        float mx = x + (ex - x) * mid, my = y + (ey - y) * mid;
                        float mdx = mx - PR_CX, mdy = my - PR_CY;
                        if (sqrtf(mdx * mdx + mdy * mdy) > PR_R) hi = mid; else lo = mid;
                    }
                    ex = x + (ex - x) * lo; ey = y + (ey - y) * lo;
                }
                rd.hasVector = true;
                rd.vecX = (int16_t)lroundf(ex); rd.vecY = (int16_t)lroundf(ey);
                tft.drawLine(x, y, rd.vecX, rd.vecY, PR_COL_VECTOR);
            }

            _placeTag(a, x, y, rd, occ, occCount);
            next[nextCount++] = rd;
        }

        memcpy(_prev, next, sizeof(PrRendered) * nextCount);
        _prevCount = nextCount;
    }

    void _erasePrev() {
        for (uint8_t i = 0; i < _prevCount; i++) {
            const PrRendered& p = _prev[i];
            if (!p.shown) continue;
            if (p.rimDot) {
                tft.fillCircle(p.x, p.y, 3, PR_COL_FIELD);
                continue;
            }
            int16_t minX = (int16_t)(min(min(p.tipX, p.lX), p.rX) - 1);
            int16_t maxX = (int16_t)(max(max(p.tipX, p.lX), p.rX) + 1);
            int16_t minY = (int16_t)(min(min(p.tipY, p.lY), p.rY) - 1);
            int16_t maxY = (int16_t)(max(max(p.tipY, p.lY), p.rY) + 1);
            tft.fillRect(minX, minY, (int16_t)(maxX - minX + 1), (int16_t)(maxY - minY + 1), PR_COL_FIELD);
            if (p.hasVector)
                tft.drawLine(p.x, p.y, p.vecX, p.vecY, PR_COL_FIELD);
            if (p.hasTag)
                tft.fillRect(p.tagX, p.tagY, p.tagW, p.tagH, PR_COL_FIELD);
        }
    }

    // Q2 tag placement: centre-side, rule (c) default — ±10/±20 px vertical
    // nudge on overlap, drop tag (keep symbol) if all four candidates collide.
    void _placeTag(const dataTask::PrAircraft& a, int16_t x, int16_t y, PrRendered& rd,
                   PrRendered* occ, uint8_t& occCount) {
        char lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN] = {};
        uint8_t nLines = 0;
        const char* cs = a.callsign[0] ? a.callsign : "?";
        strlcpy(lines[nLines++], cs, PR_TAG_LINE_LEN);
        if (a.type[0]) strlcpy(lines[nLines++], a.type, PR_TAG_LINE_LEN);
        if (a.altFt == INT32_MIN)      strlcpy(lines[nLines++], "GND", PR_TAG_LINE_LEN);
        else if (a.altFt != INT32_MAX) snprintf(lines[nLines++], PR_TAG_LINE_LEN, "%ldft", (long)a.altFt);

        int16_t w = 0;
        for (uint8_t i = 0; i < nLines; i++) {
            int16_t l = (int16_t)(strlen(lines[i]) * 6);
            if (l > w) w = l;
        }
        int16_t h  = (int16_t)(nLines * 8);
        int16_t tx = (x < PR_CX) ? (int16_t)(x + 9) : (int16_t)(x - 9 - w);
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
        // never nudge/drop. (b) + nudge, place at the un-nudged position if all
        // four candidates still collide (never drops). (c) same nudge ladder,
        // DROP the tag (keep the symbol) if all four still collide.
        int16_t bestY = ty;
        bool placed = true;
        if (g_settings.prTagRule != PrTagRule::A) {
            placed = !overlaps(tx, ty);
            if (!placed) {
                static const int16_t kNudges[4] = {10, -10, 20, -20};
                for (int16_t n : kNudges) {
                    if (!overlaps(tx, (int16_t)(ty + n))) { bestY = (int16_t)(ty + n); placed = true; break; }
                }
                if (!placed && g_settings.prTagRule == PrTagRule::B) placed = true;  // (b): place anyway, un-nudged
            }
        }
        if (!placed) return;   // (c): drop tag, keep symbol

        rd.hasTag = true;
        rd.tagX = tx; rd.tagY = bestY; rd.tagW = w; rd.tagH = h;

        occ[occCount].tagX = tx; occ[occCount].tagY = bestY;
        occ[occCount].tagW = w;  occ[occCount].tagH = h;
        occCount++;

        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(PR_COL_TAG, PR_COL_FIELD);
        for (uint8_t i = 0; i < nLines; i++)
            tft.drawString(lines[i], tx, (int16_t)(bestY + i * 8), 1);
    }
};
