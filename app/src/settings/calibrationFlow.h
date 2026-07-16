#pragma once
#include <Arduino.h>
#include <TFT_eSPI.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include "settingsSection.h"
#include "settingsWidgets.h"
#include "CYD28_TouchscreenR.h"

extern TFT_eSPI tft;

// ============================================================================
// TouchCalData — runtime calibration struct
// ============================================================================

struct TouchCalData {
    int16_t  xMin = CYD28_TouchR_CAL_XMIN;
    int16_t  xMax = CYD28_TouchR_CAL_XMAX;
    int16_t  yMin = CYD28_TouchR_CAL_YMIN;
    int16_t  yMax = CYD28_TouchR_CAL_YMAX;
    int16_t  rawTL[2] = {};
    int16_t  rawTR[2] = {};
    int16_t  rawBR[2] = {};
    int16_t  rawBL[2] = {};
    uint32_t ts     = 0;
    bool     valid  = false;   // false = no SPIFFS entry; use #define defaults
};

extern TouchCalData g_calData;

// ============================================================================
// TouchCalStorage — SPIFFS persistence for /cal.json
// ============================================================================

namespace TouchCalStorage {
    static constexpr const char* kFile = "/cal.json";

    inline void load() {
        g_calData = TouchCalData{};   // reset to compile-time defaults

        if (!SPIFFS.exists(kFile)) return;
        File f = SPIFFS.open(kFile, "r");
        if (!f) return;

        DynamicJsonDocument doc(1024);
        if (deserializeJson(doc, f) != DeserializationError::Ok) {
            f.close(); return;
        }
        f.close();

        if (!doc.containsKey("current")) return;
        auto cur = doc["current"];
        g_calData.xMin  = cur["xMin"] | (int)CYD28_TouchR_CAL_XMIN;
        g_calData.xMax  = cur["xMax"] | (int)CYD28_TouchR_CAL_XMAX;
        g_calData.yMin  = cur["yMin"] | (int)CYD28_TouchR_CAL_YMIN;
        g_calData.yMax  = cur["yMax"] | (int)CYD28_TouchR_CAL_YMAX;
        g_calData.ts    = cur["ts"]   | 0u;
        g_calData.valid = true;

        if (cur.containsKey("raw")) {
            auto raw = cur["raw"];
            g_calData.rawTL[0] = raw["TL"][0] | 0; g_calData.rawTL[1] = raw["TL"][1] | 0;
            g_calData.rawTR[0] = raw["TR"][0] | 0; g_calData.rawTR[1] = raw["TR"][1] | 0;
            g_calData.rawBR[0] = raw["BR"][0] | 0; g_calData.rawBR[1] = raw["BR"][1] | 0;
            g_calData.rawBL[0] = raw["BL"][0] | 0; g_calData.rawBL[1] = raw["BL"][1] | 0;
        }

        Serial.printf("TouchCalStorage: loaded xMin=%d xMax=%d yMin=%d yMax=%d\n",
                      g_calData.xMin, g_calData.xMax, g_calData.yMin, g_calData.yMax);
    }

    inline void save(const TouchCalData& d) {
        DynamicJsonDocument doc(1024);

        // Push current → history[0], shift existing, keep factory anchor
        JsonArray hist = doc.createNestedArray("history");
        // Factory anchor (always first in history)
        {
            auto h0 = hist.createNestedObject();
            h0["xMin"] = CYD28_TouchR_CAL_XMIN;
            h0["xMax"] = CYD28_TouchR_CAL_XMAX;
            h0["yMin"] = CYD28_TouchR_CAL_YMIN;
            h0["yMax"] = CYD28_TouchR_CAL_YMAX;
            h0["ts"]   = 0;
            h0["src"]  = "factory";
        }
        // Read existing history entries (up to 2 non-factory) to carry forward
        if (SPIFFS.exists(kFile)) {
            File fr = SPIFFS.open(kFile, "r");
            if (fr) {
                DynamicJsonDocument old(1024);
                if (deserializeJson(old, fr) == DeserializationError::Ok &&
                    old.containsKey("history")) {
                    int added = 0;
                    for (JsonObjectConst h : old["history"].as<JsonArrayConst>()) {
                        if (added >= 2) break;
                        const char* src = h["src"] | "";
                        if (strcmp(src, "factory") == 0) continue;
                        auto hN = hist.createNestedObject();
                        hN["xMin"] = h["xMin"] | 0;
                        hN["xMax"] = h["xMax"] | 0;
                        hN["yMin"] = h["yMin"] | 0;
                        hN["yMax"] = h["yMax"] | 0;
                        hN["ts"]   = h["ts"]   | 0u;
                        added++;
                    }
                }
                fr.close();
            }
        }

        // Current calibration
        auto cur = doc.createNestedObject("current");
        cur["xMin"] = d.xMin;
        cur["xMax"] = d.xMax;
        cur["yMin"] = d.yMin;
        cur["yMax"] = d.yMax;
        cur["ts"]   = d.ts;
        auto raw = cur.createNestedObject("raw");
        auto tl = raw.createNestedArray("TL"); tl.add(d.rawTL[0]); tl.add(d.rawTL[1]);
        auto tr = raw.createNestedArray("TR"); tr.add(d.rawTR[0]); tr.add(d.rawTR[1]);
        auto br = raw.createNestedArray("BR"); br.add(d.rawBR[0]); br.add(d.rawBR[1]);
        auto bl = raw.createNestedArray("BL"); bl.add(d.rawBL[0]); bl.add(d.rawBL[1]);

        File f = SPIFFS.open(kFile, "w");
        if (!f) { Serial.println("TouchCalStorage: write failed"); return; }
        serializeJson(doc, f);
        f.close();
        Serial.println("TouchCalStorage: saved");
    }
}

// ============================================================================
// CalibrationFlow constants
// ============================================================================

#define CAL_HEADER_H        28
#define CAL_CONTENT_Y       28
#define CAL_INSET_X         20
#define CAL_INSET_Y         48    // CAL_HEADER_H + 20 px margin
#define CAL_CROSSHAIR_ARM   24
#define CAL_Z_THRESHOLD    400

#define CAL_BG_COLOR         0x2104
#define CAL_SEP_COLOR        0x4208
#define CAL_HEADER_COLOR     0xFFFF
#define CAL_SECTION_COLOR    0xFFE0
#define CAL_VALUE_COLOR      0x07FF
#define CAL_DIM_COLOR        0x7BEF
#define CAL_CROSSHAIR_ACTIVE 0x07E0
#define CAL_CROSSHAIR_DONE   0x4208
#define CAL_MARKER_OK        0x07E0
#define CAL_MARKER_NEAR      0xFFE0
#define CAL_MARKER_FAR       0xF800
#define CAL_BTN_COLOR        0x07E0
#define CAL_ERROR_COLOR      0xF800

// Corner screen targets
static const int16_t kCalTX[4] = { CAL_INSET_X, 274 - CAL_INSET_X,
                                    274 - CAL_INSET_X, CAL_INSET_X };
static const int16_t kCalTY[4] = { CAL_INSET_Y, CAL_INSET_Y,
                                    239 - 20, 239 - 20 };

// ============================================================================
// CalibrationFlow
// ============================================================================

enum class CalStep : uint8_t { Idle, TL, TR, BotR, BL, Review, Saving };

class CalibrationFlow : public SettingsSection {
public:
    // SettingsSection contract
    const char* title() const override {
        static const char* kTitles[] = {
            "Touch Calibration",    // Idle
            "Tap top-left",         // TL
            "Tap top-right",        // TR
            "Tap bottom-right",     // BR
            "Tap bottom-left",      // BL
            "Review calibration",   // Review
            "Saving...",            // Saving
        };
        return kTitles[(int)_step];
    }

    void enter() override {
        _step        = CalStep::Idle;
        _tapsDone    = 0;
        _sanityFailed = false;
        _rawSumX = _rawSumY = 0;
        _rawCount = 0;
        _loadHistory();
        repaint();
    }

    void leave() override {
        _step = CalStep::Idle;
    }

    SectionResult tick() override {
        if (_step == CalStep::Saving) {
            TouchCalStorage::save(_pending);
            g_calData   = _pending;
            g_calData.valid = true;
            _justSaved  = true;   // SettingsApp reads this to call ts.setCalibration()
            _step       = CalStep::Idle;
            repaint();
        }
        return SectionResult::Continue;
    }

    // True while the cal section owns the screen (Idle through Saving).
    bool stepping() const {
        return _step >= CalStep::TL && _step <= CalStep::BL;
    }

    // Scaled touch input — Idle and Review button taps.
    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return SectionResult::Continue;

        if (_step == CalStep::Idle) {
            // Back tap
            if (isBackTap(x, y)) return SectionResult::GoBack;
            // Start tap (x > 220, y < CAL_HEADER_H)
            if (y < CAL_HEADER_H && x > 220) {
                _step     = CalStep::TL;
                _tapsDone = 0;
                _rawSumX  = _rawSumY = 0;
                _rawCount = 0;
                repaint();
            }
            return SectionResult::Continue;
        }

        if (_step == CalStep::Review) {
            if (isBackTap(x, y)) {
                _step = CalStep::Idle;
                repaint();
                return SectionResult::Continue;
            }
            // Accept is SBtnStyle::Disabled while _sanityFailed, so hit()
            // already refuses it — no separate guard needed.
            if (_calBtns[0].hit(x, y)) {
                _calBtns[0].flash();
                _step = CalStep::Saving;
                return SectionResult::Continue;
            }
            if (_calBtns[1].hit(x, y)) {
                _calBtns[1].flash();
                _step     = CalStep::TL;
                _tapsDone = 0;
                _rawSumX  = _rawSumY = 0;
                _rawCount = 0;
                repaint();
                return SectionResult::Continue;
            }
            if (_calBtns[2].hit(x, y)) {
                _calBtns[2].flash();
                _step = CalStep::Idle;
                repaint();
                return SectionResult::Continue;
            }
        }

        // During STEP_* — allow back-tap to cancel to Idle
        if (stepping() && isBackTap(x, y)) {
            _step     = CalStep::Idle;
            _tapsDone = 0;
            repaint();
            return SectionResult::Continue;
        }

        return SectionResult::Continue;
    }

    // Raw XPT2046 input — called by SettingsApp::tick() when stepping().
    // Accumulates samples while pressed; latches averaged values on Release.
    bool handleInputRaw(TouchPhase phase, int16_t rawX, int16_t rawY) {
        if (phase == TouchPhase::Press) {
            _rawSumX += rawX;
            _rawSumY += rawY;
            _rawCount++;
            return false;
        }
        if (phase == TouchPhase::Release && _rawCount > 0) {
            int cornerIdx = (int)_step - (int)CalStep::TL;
            _rawX[cornerIdx] = (int16_t)(_rawSumX / _rawCount);
            _rawY[cornerIdx] = (int16_t)(_rawSumY / _rawCount);
            _rawSumX = _rawSumY = 0;
            _rawCount = 0;
            _tapsDone++;

            // Advance step
            CalStep next = (CalStep)((uint8_t)_step + 1);
            if (next == CalStep::Review) {
                _sanityFailed = !_computeCalibration();
            }
            _step = next;
            repaint();
            return true;
        }
        return false;
    }

    void repaint() override {
        if (_step == CalStep::Idle) {
            _repaintIdle();
        } else if (_step == CalStep::Review || _step == CalStep::Saving) {
            _repaintReview();
        } else {
            drawHeader();
            _repaintStep();
        }
    }

    // External accessor so SettingsApp can call ts.setCalibration() after Saving completes.
    bool justSaved() const { return _justSaved; }
    void clearJustSaved()  { _justSaved = false; }

private:
    struct HistEntry {
        int16_t  xMin, xMax, yMin, yMax;
        uint32_t ts;
        bool     factory;
    };
    HistEntry _hist[3];
    uint8_t   _histCount = 0;

    void _loadHistory() {
        _histCount = 0;
        if (!SPIFFS.exists(TouchCalStorage::kFile)) return;
        File f = SPIFFS.open(TouchCalStorage::kFile, "r");
        if (!f) return;
        DynamicJsonDocument doc(1024);
        if (deserializeJson(doc, f) != DeserializationError::Ok) { f.close(); return; }
        f.close();
        if (!doc.containsKey("history")) return;
        for (JsonObjectConst h : doc["history"].as<JsonArrayConst>()) {
            if (_histCount >= 3) break;
            HistEntry& e = _hist[_histCount++];
            e.xMin    = h["xMin"] | 0;
            e.xMax    = h["xMax"] | 0;
            e.yMin    = h["yMin"] | 0;
            e.yMax    = h["yMax"] | 0;
            e.ts      = h["ts"]   | 0u;
            const char* src = h["src"] | "";
            e.factory = (strcmp(src, "factory") == 0);
        }
    }

    CalStep   _step         = CalStep::Idle;
    uint8_t   _tapsDone     = 0;
    bool      _sanityFailed = false;
    bool      _justSaved    = false;

    SButton   _calBtns[3];   // Accept / Retry / Cancel (Review screen)

    int16_t   _rawX[4] = {};
    int16_t   _rawY[4] = {};

    int32_t   _rawSumX = 0;
    int32_t   _rawSumY = 0;
    int16_t   _rawCount = 0;

    TouchCalData _pending;

    // ---- Compute calibration from 4 corner taps --------------------------------

    bool _computeCalibration() {
        // Average left/right/top/bottom raw values
        int32_t rxL = ((int32_t)_rawX[0] + _rawX[3]) / 2;   // TL + BL
        int32_t rxR = ((int32_t)_rawX[1] + _rawX[2]) / 2;   // TR + BR
        int32_t ryT = ((int32_t)_rawY[0] + _rawY[1]) / 2;   // TL + TR
        int32_t ryB = ((int32_t)_rawY[2] + _rawY[3]) / 2;   // BR + BL (note: BR=2, BL=3)

        int32_t screenW = 275 - 2 * CAL_INSET_X;   // = 235
        int32_t screenH = 239 - CAL_INSET_Y - 20;  // = 171

        if (screenW == 0 || screenH == 0) return false;

        float xSlope = (float)(rxR - rxL) / screenW;
        float ySlope = (float)(ryB - ryT) / screenH;

        // Extrapolate to the full 320×240 physical screen, matching sizeX_px/sizeY_px in
        // CYD28_TouchR (ts is constructed with CYD28_DISPLAY_HOR_RES_MAX=320, _VER_=240).
        // Left corner is at x=CAL_INSET_X=20  → extend 20px left  to x=0.
        // Right corner is at x=254           → extend 65px right to x=319  (319-254=65).
        // Top corner is at y=CAL_INSET_Y=48  → extend 48px up    to y=0.
        // Bottom corner is at y=219          → extend 20px down  to y=239.
        static const int16_t kRightExtend = 319 - (S_CANVAS_W - 1 - CAL_INSET_X); // = 65
        _pending.xMin = (int16_t)(rxL - CAL_INSET_X * xSlope);
        _pending.xMax = (int16_t)(rxR + kRightExtend  * xSlope);
        _pending.yMin = (int16_t)(ryT - CAL_INSET_Y   * ySlope);
        _pending.yMax = (int16_t)(ryB + (CAL_INSET_Y - CAL_HEADER_H) * ySlope);

        // Sanity checks
        if (_pending.xMax - _pending.xMin < 1000) return false;
        if (_pending.yMax - _pending.yMin < 1000) return false;
        if (_pending.xMin < 0 || _pending.xMax > 4095) return false;
        if (_pending.yMin < 0 || _pending.yMax > 4095) return false;

        // Store raw corners
        _pending.rawTL[0] = _rawX[0]; _pending.rawTL[1] = _rawY[0];
        _pending.rawTR[0] = _rawX[1]; _pending.rawTR[1] = _rawY[1];
        _pending.rawBR[0] = _rawX[2]; _pending.rawBR[1] = _rawY[2];
        _pending.rawBL[0] = _rawX[3]; _pending.rawBL[1] = _rawY[3];

        struct tm t;
        _pending.ts    = getLocalTime(&t) ? (uint32_t)mktime(&t) : 0u;
        _pending.valid = true;
        return true;
    }

    // ---- Rendering -------------------------------------------------------------

    void _repaintIdle() {
        // Custom header: "< back" left, "Start" right — no centre title
        tft.fillRect(0, 0, S_CANVAS_W, CAL_HEADER_H, CAL_BG_COLOR);
        tft.setTextColor(CAL_HEADER_COLOR);
        tft.setTextDatum(ML_DATUM);
        tft.drawString("< back", 4, CAL_HEADER_H / 2, 2);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(CAL_BTN_COLOR);
        tft.drawString("Start", S_CANVAS_W - 4, CAL_HEADER_H / 2, 2);
        tft.drawFastHLine(0, CAL_HEADER_H - 1, S_CANVAS_W, CAL_SEP_COLOR);
        tft.setTextDatum(TL_DATUM);

        tft.fillRect(0, CAL_CONTENT_Y, S_CANVAS_W, S_CANVAS_H - CAL_CONTENT_Y, CAL_BG_COLOR);

        int y = CAL_CONTENT_Y + 6;
        char buf[48];

        tft.setTextColor(CAL_SECTION_COLOR);
        tft.drawString("Current cal", 8, y, 2); y += 20;

        tft.setTextColor(CAL_VALUE_COLOR);
        snprintf(buf, sizeof(buf), "xMin %4d   xMax %4d", g_calData.xMin, g_calData.xMax);
        tft.drawString(buf, 8, y, 2); y += 16;
        snprintf(buf, sizeof(buf), "yMin %4d   yMax %4d", g_calData.yMin, g_calData.yMax);
        tft.drawString(buf, 8, y, 2); y += 16;

        tft.setTextColor(CAL_DIM_COLOR);
        const char* src = g_calData.valid ? "SPIFFS" : "factory default";
        snprintf(buf, sizeof(buf), "Source: %s", src);
        tft.drawString(buf, 8, y, 2); y += 20;

        tft.drawFastHLine(8, y, 259, CAL_SEP_COLOR); y += 8;

        tft.setTextColor(CAL_SECTION_COLOR);
        tft.drawString("Tap Start to calibrate", 8, y, 2); y += 20;

        // History entries
        if (_histCount > 0) {
            tft.drawFastHLine(8, y, 259, CAL_SEP_COLOR); y += 6;
            tft.setTextColor(CAL_SECTION_COLOR);
            tft.drawString("History", 8, y, 2); y += 18;
            for (uint8_t i = 0; i < _histCount; i++) {
                const HistEntry& e = _hist[i];
                char line[48];
                if (e.factory) {
                    snprintf(line, sizeof(line), "[%d] factory  %d/%d/%d/%d",
                             i + 1, e.xMin, e.xMax, e.yMin, e.yMax);
                } else {
                    struct tm t;
                    time_t ts = (time_t)e.ts;
                    localtime_r(&ts, &t);
                    snprintf(line, sizeof(line), "[%d] %02d-%02d  %d/%d/%d/%d",
                             i + 1, t.tm_mon + 1, t.tm_mday,
                             e.xMin, e.xMax, e.yMin, e.yMax);
                }
                tft.setTextColor(CAL_DIM_COLOR);
                tft.drawString(line, 8, y, 1); y += 14;
                if (y > 230) break;
            }
        }
    }

    void _repaintStep() {
        int cornerIdx = (int)_step - (int)CalStep::TL;
        tft.fillRect(0, CAL_CONTENT_Y, S_CANVAS_W, S_CANVAS_H - CAL_CONTENT_Y, CAL_BG_COLOR);

        // Completed corners: grey crosshair + tap marker
        for (int i = 0; i < cornerIdx; i++) {
            _drawCrosshair(kCalTX[i], kCalTY[i], CAL_CROSSHAIR_DONE);
            _drawTapMarker(i);
        }
        // Active corner: green crosshair
        _drawCrosshair(kCalTX[cornerIdx], kCalTY[cornerIdx], CAL_CROSSHAIR_ACTIVE);
    }

    void _repaintReview() {
        const char* hdr = _sanityFailed ? "Bad reading" : "Review calibration";
        tft.fillRect(0, 0, S_CANVAS_W, S_CANVAS_H, CAL_BG_COLOR);
        tft.setTextColor(CAL_HEADER_COLOR);
        tft.setTextDatum(ML_DATUM);
        tft.drawString("< back", 4, CAL_HEADER_H / 2, 2);
        tft.setTextDatum(MR_DATUM);
        tft.drawString(hdr, S_CANVAS_W - 4, CAL_HEADER_H / 2, 2);
        tft.drawFastHLine(0, CAL_HEADER_H - 1, S_CANVAS_W, CAL_SEP_COLOR);
        tft.setTextDatum(TL_DATUM);

        for (int i = 0; i < 4; i++) _drawTapMarker(i);

        if (_sanityFailed) {
            tft.setTextColor(CAL_ERROR_COLOR);
            tft.drawString("Span too small - tap Retry", 8, 150, 2);
        } else {
            char buf[48];
            int y = 120;
            tft.setTextColor(CAL_SECTION_COLOR);
            tft.drawString("New:", 8, y, 2);
            tft.setTextColor(CAL_VALUE_COLOR);
            snprintf(buf, sizeof(buf), "xMin %4d  xMax %4d", _pending.xMin, _pending.xMax);
            tft.drawString(buf, 48, y, 2); y += 16;
            snprintf(buf, sizeof(buf), "yMin %4d  yMax %4d", _pending.yMin, _pending.yMax);
            tft.drawString(buf, 48, y, 2); y += 16;

            tft.setTextColor(CAL_DIM_COLOR);
            snprintf(buf, sizeof(buf), "d xMin%+d  xMax%+d",
                     (int)_pending.xMin - g_calData.xMin,
                     (int)_pending.xMax - g_calData.xMax);
            tft.drawString(buf, 48, y, 2); y += 16;
            snprintf(buf, sizeof(buf), "  yMin%+d  yMax%+d",
                     (int)_pending.yMin - g_calData.yMin,
                     (int)_pending.yMax - g_calData.yMax);
            tft.drawString(buf, 48, y, 2);
        }

        tft.drawFastHLine(0, S_BTN_BAR_Y - 6, S_CANVAS_W, CAL_SEP_COLOR);

        // Kit buttons on the standard bar (TASK-327; were hand-rolled 26px
        // outline boxes at y=210). CAL_BG_COLOR == S_BG, so the Disabled
        // style's background fill matches this screen.
        _calBtns[0].label = "Accept";
        _calBtns[0].style = _sanityFailed ? SBtnStyle::Disabled : SBtnStyle::Primary;
        _calBtns[1].label = "Retry";  _calBtns[1].style = SBtnStyle::Neutral;
        _calBtns[2].label = "Cancel"; _calBtns[2].style = SBtnStyle::Neutral;
        sButtonBar(_calBtns, 3);
        for (auto& b : _calBtns) b.draw();
    }

    void _drawCrosshair(int x, int y, uint16_t color) const {
        tft.drawFastHLine(x - CAL_CROSSHAIR_ARM, y, CAL_CROSSHAIR_ARM * 2, color);
        tft.drawFastVLine(x, y - CAL_CROSSHAIR_ARM, CAL_CROSSHAIR_ARM * 2, color);
        tft.fillRect(x - 2, y - 2, 4, 4, color);
    }

    void _drawTapMarker(int i) const {
        if (i >= _tapsDone) return;
        int ex = kCalTX[i], ey = kCalTY[i];
        // Replicate convertRawXY (rotation=1): (raw - min) * sizeXY_px / range.
        // sizeX_px=320, sizeY_px=240 — must match CYD28_TouchR constructor args.
        int32_t xRange = (int32_t)g_calData.xMax - g_calData.xMin;
        int32_t yRange = (int32_t)g_calData.yMax - g_calData.yMin;
        int ax = (xRange > 0) ? (int)(((int32_t)(_rawX[i] - g_calData.xMin) * 320) / xRange) : 0;
        int ay = (yRange > 0) ? (int)(((int32_t)(_rawY[i] - g_calData.yMin) * 240) / yRange) : 0;
        ax = constrain(ax, 0, 274);
        ay = constrain(ay, 0, 239);

        int dist = (int)sqrtf((float)((ax-ex)*(ax-ex) + (ay-ey)*(ay-ey)));
        uint16_t markerColor = (dist <= 4) ? (uint16_t)CAL_MARKER_OK
                             : (dist <= 8) ? (uint16_t)CAL_MARKER_NEAR
                             :               (uint16_t)CAL_MARKER_FAR;

        tft.fillCircle(ex, ey, 4, CAL_CROSSHAIR_DONE);
        if (ax != ex || ay != ey)
            tft.drawLine(ex, ey, ax, ay, markerColor);
        tft.fillCircle(ax, ay, 4, markerColor);

        char buf[16];
        snprintf(buf, sizeof(buf), "%d/%d", _rawX[i], _rawY[i]);
        tft.setTextColor(CAL_DIM_COLOR);
        tft.drawString(buf, constrain(ax - 12, 0, 210), ay + 6, 1);
    }
};
