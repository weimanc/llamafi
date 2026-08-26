// planeRadarApp.cpp — PlaneRadarApp method bodies, out-of-line (M-SRCLAYOUT Stage E).
#include "apps/planeRadarApp.h"

void PlaneRadarApp::init() {
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

void PlaneRadarApp::resume() {
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

void PlaneRadarApp::tick() {
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
                // TASK-367 measurement, left in place: fetch round-trip
                // from _requestFetch()'s true issue instant (_fetchIssuedMs
                // — unlike _lastFetch, never _forceNow()-backdated, so this
                // stays accurate for re-verifying TASK-377's effect) to this
                // drain.
                LOG_D("planeradar", "fetch rtt=%lums ok=%d errorCode=%d",
                      now - _fetchIssuedMs, (int)result.ok, (int)result.errorCode);
                if (result.ok) {
                    _result        = result;
                    _everHadResult = true;
                    _prErr         = false;
                    _lastGoodMs    = now;
                    // TASK-378: this cycle's fetch asked a smaller radius
                    // than the preset nominally covers (TASK-361's
                    // radius-capped retry2) — must be set before
                    // _render() (which draws the shade) runs below.
                    _radiusCapActive = result.fetchedRadiusNm < kPrFetchNm[_presetIdx] - PR_RADIUS_CAP_EPS_NM;
                    _radiusCapNm     = result.fetchedRadiusNm;
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

bool PlaneRadarApp::handleInput(TouchPhase phase, int x, int y) {
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

void PlaneRadarApp::_setActiveLoc(uint8_t slot) {
    if (slot >= PR_NUM_LOCS) return;                           // out of range: no-op
    if (slot == g_settings.prActiveLoc) return;                // (a) same slot: no-op, no flicker
    if (g_settings.prLocs[slot].label[0] == '\0') return;      // (a) empty slot: no-op

    // (b) copy slot -> write-through mirror, persist. TASK-473 (G3):
    // routed through the matrix's own helper (settingsStorage.h) instead of
    // an inline copy, so this is no longer a second, undocumented writer.
    SettingsStorage::prActiveLocChanged(slot);
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

bool PlaneRadarApp::dbgGet(const char* var, char* buf, int len) const {
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
    if (strcmp(var, "prForceParseFail") == 0) {
        snprintf(buf, len, "\"var\":\"prForceParseFail\",\"val\":%d,\"last\":true",
                 dataTask::debugPeekForcedParseFailCount());
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

bool PlaneRadarApp::dbgSet(const char* var, const char* val) {
    if (strcmp(var, "triggerPlaneRadarFetch") == 0 && strcmp(val, "1") == 0) {
        _lastFetch    = _forceNow();
        _pendingFetch = false;   // allow tick() to enqueue even if a prior fetch is pending
        return true;
    }
    // TASK-361 VE test hook: force the next N prFetchOnce() attempts
    // (fetch/retry/retry2) to report a synthetic parse failure, so the
    // radius-capped 2nd retry can be exercised on demand rather than
    // waiting on real Cloudflare edge conditions — confirmed 2026-07-26
    // these don't reliably reproduce "both attempts fail" day to day.
    // n=2 forces attempts 1-2, letting retry2 hit the real network;
    // n=3 forces the full cascade to give up too. Combine with
    // `triggerPlaneRadarFetch 1` to fire immediately.
    if (strcmp(var, "prForceParseFail") == 0) {
        dataTask::debugForcePlaneRadarParseFail(atoi(val));
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
        // TASK-377: injection bypasses _requestFetch() entirely, so
        // _fetchIssuedMs would otherwise be left stale/zero from before
        // (or from a real fetch) — _reconcileMotion() now stamps fixMs
        // from it, so it must read "just landed" here same as a real fetch.
        _fetchIssuedMs = _lastGoodMs;
        // TASK-378: injection isn't a degraded fetch — clear any warning
        // shade left over from real traffic before the injection started.
        _radiusCapActive = false;
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

bool PlaneRadarApp::_ensureMotion() {
    if (_motion) return true;
    _motion = new PrMotion[dataTask::PR_MAX_AIRCRAFT];
    return _motion != nullptr;
}

void PlaneRadarApp::_applyRangeSetting() {
    _presetIdx = (g_settings.prRangeIdx < PR_NUM_PRESETS) ? g_settings.prRangeIdx : 1;
}

void PlaneRadarApp::_requestFetch(unsigned long ts) {
    dataTask::enqueuePlaneRadar(g_settings.prLat, g_settings.prLon, kPrFetchNm[_presetIdx], _locEpoch);
    _lastFetch     = ts;
    _fetchIssuedMs = millis();   // TASK-377: true issue instant, ts may be _forceNow()-backdated
    _pendingFetch  = true;
}

void PlaneRadarApp::_setPreset(uint8_t idx) {
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

void PlaneRadarApp::_clipToDisc(float x0, float y0, float* ex, float* ey) const {
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

void PlaneRadarApp::_project(float lat, float lon, int16_t* px, int16_t* py) const {
    float dxKm = (lon - g_settings.prLon) * PR_KM_PER_DEG_LON * cosf(g_settings.prLat * (float)M_PI / 180.0f);
    float dyKm = (lat - g_settings.prLat) * PR_KM_PER_DEG_LAT;
    float s    = _pxPerKm();
    *px = (int16_t)lroundf(PR_CX + dxKm * s);
    *py = (int16_t)lroundf(PR_CY - dyKm * s);
}

void PlaneRadarApp::_motionPx(uint8_t i, unsigned long now, int16_t* px, int16_t* py) const {
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

void PlaneRadarApp::_reconcileMotion(unsigned long now) {
    if (!_ensureMotion()) { _motionCount = 0; return; }   // OOM edge case: render falls back to raw fix positions
    PrMotion next[dataTask::PR_MAX_AIRCRAFT];
    // TASK-378: track the farthest-kept aircraft's distance in the same
    // pass — only meaningful (roster actually truncated, not just "every
    // detected aircraft happens to be this far out") when the roster is
    // at the PR_MAX_AIRCRAFT cap.
    float horizonNm = 0.0f;
    for (uint8_t i = 0; i < _result.count; i++) {
        const dataTask::PrAircraft& a = _result.aircraft[i];
        if (a.distNm > horizonNm) horizonNm = a.distNm;
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
        // TASK-377: stamp from the GET's issue instant, not `now` (this
        // reconcile's call time, which for the drain path is however long
        // the fetch+retries took to land) — the aircraft's true position
        // is that recent as of when we asked, not as of when the answer
        // happened to finish arriving.
        m.fixMs = _fetchIssuedMs;
        next[i] = m;
    }
    memcpy(_motion, next, sizeof(PrMotion) * _result.count);
    _motionCount = _result.count;
    _horizonActive = (_result.count == dataTask::PR_MAX_AIRCRAFT);
    _horizonNm     = horizonNm;
}

void PlaneRadarApp::_redrawGridStatics(bool shade) {
    if (shade) _drawHorizonShade();
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

bool PlaneRadarApp::_activeShade(uint16_t& col, float& radiusPx) const {
    float radiusNm;
    if (_radiusCapActive)      { radiusNm = _radiusCapNm; col = PR_COL_HORIZON_WARN; }
    else if (_horizonActive)   { radiusNm = _horizonNm;   col = PR_COL_HORIZON; }
    else return false;
    radiusPx = radiusNm * PR_KM_PER_NM * _pxPerKm();
    return radiusPx < (float)PR_R;
}

uint16_t PlaneRadarApp::_bgColorAt(int16_t x, int16_t y) const {
    uint16_t col; float radiusPx;
    if (!_activeShade(col, radiusPx)) return PR_COL_FIELD;
    float dx = (float)x - (float)PR_CX, dy = (float)y - (float)PR_CY;
    return (_distPx(dx, dy) > radiusPx) ? col : PR_COL_FIELD;
}

void PlaneRadarApp::_drawHorizonShade() {
    uint16_t col; float radiusPx;
    if (!_activeShade(col, radiusPx)) { tft.fillCircle(PR_CX, PR_CY, PR_R, PR_COL_FIELD); return; }
    tft.fillCircle(PR_CX, PR_CY, PR_R, col);
    tft.fillCircle(PR_CX, PR_CY, (int16_t)radiusPx, PR_COL_FIELD);
}

void PlaneRadarApp::_repairHorizonShadeBox(int16_t bx, int16_t by, int16_t bw, int16_t bh) {
    uint16_t col; float radiusPx;
    if (!_activeShade(col, radiusPx)) return;   // no active shade — _eraseFootprint's PR_COL_FIELD fill already correct
    float cdx = (float)bx + (float)bw / 2.0f - (float)PR_CX;
    float cdy = (float)by + (float)bh / 2.0f - (float)PR_CY;
    if (_distPx(cdx, cdy) > radiusPx) tft.fillRect(bx, by, bw, bh, col);
}

void PlaneRadarApp::_repaintDisc() {
    tft.fillRect(0, 0, PR_STRIP_X, PR_SCREEN_H, PR_COL_OUTSIDE);
    tft.fillCircle(PR_CX, PR_CY, PR_R, PR_COL_FIELD);
    _redrawGridStatics();
    _prevCount   = 0;   // prior aircraft pixel positions are stale after a repaint/rescale
    _motionCount = 0;   // TASK-357: and so is any dead-reckon/offset continuity built on them
}

void PlaneRadarApp::_drawGridOnce() {
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

void PlaneRadarApp::_drawRunways() {
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
            tft.setTextColor(PR_COL_RUNWAY_LABEL, _bgColorAt(ax, (int16_t)(ay - 9)));
            tft.drawString(icao, ax, (int16_t)(ay - 9), 1);
        }
    }
    tft.setTextDatum(TL_DATUM);
}

void PlaneRadarApp::_stripField(int16_t rowY, const char* text, uint16_t color) {
    tft.fillRect(PR_STRIP_X + 1, rowY, PR_STRIP_W - 2, 14, PR_COL_STRIP_BG);
    tft.setTextColor(color, PR_COL_STRIP_BG);
    tft.drawString(text, PR_STRIP_LABEL_X, rowY + 7, 1);
}

void PlaneRadarApp::_drawLocSlots() {
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

void PlaneRadarApp::_updateStripDynamic(bool includeRangeAndCount) {
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

void PlaneRadarApp::_drawAircraftBody(const dataTask::PrAircraft& a, int16_t x, int16_t y, PrRendered& rd) {
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

void PlaneRadarApp::_render(unsigned long now) {
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

void PlaneRadarApp::_eraseFootprint(const PrRendered& p, int16_t& bx, int16_t& by, int16_t& bw, int16_t& bh) {
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

void PlaneRadarApp::_erasePrev() {
    for (uint8_t i = 0; i < _prevCount; i++) {
        int16_t bx, by, bw, bh;
        _eraseFootprint(_prev[i], bx, by, bw, bh);   // whole-scene path: bbox unused, _redrawGridStatics() repairs the full disc after
    }
}

void PlaneRadarApp::_redrawOneAircraft(uint8_t i, unsigned long now) {
    if (i >= _result.count || i >= _prevCount) return;   // defensive: invariant should hold post-reconcile
    const dataTask::PrAircraft& a = _result.aircraft[i];
    PrRendered old = _prev[i];

    int16_t x, y;
    _motionPx(i, now, &x, &y);

    int16_t bx, by, bw, bh;
    _eraseFootprint(old, bx, by, bw, bh);
    if (bw > 0 && bh > 0) {
        withViewportRepair(tft, bx, by, bw, bh, [&] {
            // TASK-378: shade-colour repair BEFORE the ring/runway
            // redraw below, so those thin lines land on top of the
            // corrected background rather than being overpainted by it.
            _repairHorizonShadeBox(bx, by, bw, bh);
            _redrawGridStatics(/*shade=*/false);
        });
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

uint8_t PlaneRadarApp::_buildTagLines(const dataTask::PrAircraft& a,
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

void PlaneRadarApp::_drawTagLines(const char lines[PR_TAG_MAX_LINES][PR_TAG_LINE_LEN],
                    const uint16_t lineColors[PR_TAG_MAX_LINES], uint8_t nLines,
                    int16_t tx, int16_t ty) {
    tft.setTextDatum(TL_DATUM);
    for (uint8_t i = 0; i < nLines; i++) {
        int16_t ly = (int16_t)(ty + i * PR_TAG_LINE_H);
        tft.setTextColor(lineColors[i], _bgColorAt(tx, ly));
        tft.drawString(lines[i], tx, ly, 1);
    }
}

void PlaneRadarApp::_placeTag(const dataTask::PrAircraft& a, int16_t x, int16_t y, PrRendered& rd,
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
