#pragma once
#include <Arduino.h>
#include <TFT_eSPI.h>
#include "../util/mathUtil.h"
#include "settingsSection.h"
#include "settingsWidgets.h"

// LedMode is defined in settingsStorage.h (already included via settingsSection.h).

extern TFT_eSPI tft;

// ============================================================================
// LED hardware constants
// ============================================================================

#define LED_R_PIN   4
#define LED_G_PIN  16
#define LED_B_PIN  17
#define LED_R_CH    1    // ledc channels (ch0 = TFT_BL, reserved)
#define LED_G_CH    2
#define LED_B_CH    3

// Common-anode: duty 0 = full ON (cathode at GND), 255 = OFF. Invert here.
#define LED_WRITE(ch, duty)  ledcWrite((ch), 255u - (uint8_t)(duty))

// ============================================================================
// LedFlow — background LED animator (ticked from main loop)
// ============================================================================

class LedFlow {
public:
    void applyMode() { _apply(); }

    void pause()  { _paused = true; }
    void resume() { _paused = false; _apply(); }

    void tick() {
        if (_paused) return;
        switch (g_settings.ledMode) {
            case LedMode::Pulse: _tickPulse(); break;
            case LedMode::Clock: _tickClock(); break;
            default: break;
        }
    }

private:
    bool    _paused    = false;
    float   _phase     = 0.0f;
    uint8_t _lastHour  = 255;

    void _apply() {
        switch (g_settings.ledMode) {
            case LedMode::Off:
                LED_WRITE(LED_R_CH, 0);
                LED_WRITE(LED_G_CH, 0);
                LED_WRITE(LED_B_CH, 0);
                break;
            case LedMode::Static:
            case LedMode::Pulse:
            case LedMode::Clock:
                _writeLed(g_settings.ledHue, g_settings.ledSat, g_settings.ledVal);
                break;
        }
    }

    void _tickPulse() {
        _phase += 0.05f;
        if (_phase > 6.28318f) _phase -= 6.28318f;
        float env = (lut_sin(_phase) + 1.0f) * 0.5f;
        uint8_t val = (uint8_t)(g_settings.ledVal * env);
        _writeLed(g_settings.ledHue, g_settings.ledSat, val);
    }

    void _tickClock() {
        struct tm t;
        if (!getLocalTime(&t)) return;
        if ((uint8_t)t.tm_hour == _lastHour) return;
        _lastHour = (uint8_t)t.tm_hour;
        uint8_t hue = (uint8_t)((t.tm_hour * 256) / 24);
        _writeLed(hue, 255, 255);
    }

    void _writeLed(uint8_t h, uint8_t s, uint8_t v) {
        RGB8 c = hsvToRgb(h, s, v);
        LED_WRITE(LED_R_CH, c.r);
#if NFC_ENABLED
        (void)c.g;
#else
        LED_WRITE(LED_G_CH, c.g);
#endif
        LED_WRITE(LED_B_CH, c.b);
    }
};

extern LedFlow g_ledFlow;

// ============================================================================
// LedSection — Settings section for LED configuration
// ============================================================================

enum class LedView : uint8_t { List, Picker };

class LedSection : public SettingsSection {
public:
    // ---- SettingsSection contract -------------------------------------------

    const char* title() const override { return "LED"; }

    void enter() override {
        _view       = LedView::List;
        _mode       = g_settings.ledMode;
        _hue        = g_settings.ledHue;
        _sat        = g_settings.ledSat;
        _val        = g_settings.ledVal;
        _svDragging = false;
        _hueDragging= false;
        _dirty      = false;
        g_ledFlow.pause();
        repaint();
    }

    void leave() override {
        g_ledFlow.resume();
    }

    SectionResult tick() override { return SectionResult::Continue; }   // LedFlow drives animation; picker live-previews on drag

    void repaint() override {
        drawHeader();
        clearContent();
        if (_view == LedView::List) _repaintList();
        else                        _repaintPicker();
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (_view == LedView::List) return _handleList(phase, x, y);
        else                        return _handlePicker(phase, x, y);
    }

private:
    // ---- View state ----------------------------------------------------------
    LedView _view        = LedView::List;

    // Working copies — not committed until Save
    LedMode _mode        = LedMode::Off;
    uint8_t _hue         = 85;
    uint8_t _sat         = 255;
    uint8_t _val         = 200;

    bool    _svDragging  = false;
    bool    _hueDragging = false;
    bool    _dirty       = false;

    // ---- Picker geometry (absolute canvas coords) ----------------------------
    // OFF/ON/SAVE are kit buttons (TASK-327; were a hand-rolled 20px bar at
    // y=28). S_BTN_H=40 pushed the SV square down from y=61 to y=78; the
    // bottom edge stays at 229.
    static constexpr int16_t kBarY  = 32;    // button bar top y
    static constexpr int16_t kPickY = 78;    // SV square + hue strip top y
    static constexpr int16_t kPickH = 151;

    static constexpr int16_t kSvX   =   8;
    static constexpr int16_t kSvW   = 168;
    static constexpr int16_t kHueX  = 184;
    static constexpr int16_t kHueW  =  24;

    SButton _pickBtns[3];   // OFF / ON / SAVE

    // ---- List view -----------------------------------------------------------

    void _repaintList() {
        bool colourActive = (_mode == LedMode::Static || _mode == LedMode::Pulse);

        const char* modeStr = "Off";
        if      (_mode == LedMode::Static) modeStr = "Static";
        else if (_mode == LedMode::Pulse)  modeStr = "Pulse";
        else if (_mode == LedMode::Clock)  modeStr = "Clock";

        // Row 0: Mode
        int y0 = S_CONTENT_Y;
        drawRow(y0, { "Mode", modeStr, S_LABEL, S_VALUE });

        // Row 1: Colour — greyed when Off or Clock
        int y1 = y0 + S_ROW_H;
        if (colourActive) {
            // Draw label, chevron, and colour swatch
            drawRow(y1, { "Colour", ">", S_LABEL, S_CHEVRON });
            _drawColourSwatch(y1);
        } else {
            drawRow(y1, { "Colour", "-", S_LABEL, S_VALUE_OFF });
        }
    }

    void _drawColourSwatch(int rowY) const {
        uint16_t col = hsvToRgb565(_hue, _sat, _val);
        tft.fillRect(S_COL_VALUE - 30, rowY + (S_ROW_H - 10) / 2, 16, 10, col);
    }

    SectionResult _handleList(TouchPhase phase, int x, int y) {
        if (phase != TouchPhase::Release) return SectionResult::Continue;
        if (isBackTap(x, y)) return SectionResult::GoBack;

        int row = tapToRow(y);
        if (row == 0) {
            // Cycle mode: Off → Static → Pulse → Clock → Off
            _mode = static_cast<LedMode>((static_cast<uint8_t>(_mode) + 1u) % 4u);
            g_settings.ledMode = _mode;
            saveSettings();
            _applyLed();
            clearContent();
            _repaintList();
        } else if (row == 1 && (_mode == LedMode::Static || _mode == LedMode::Pulse)) {
            _view  = LedView::Picker;
            _dirty = false;
            clearContent();
            _repaintPicker();
        }
        return SectionResult::Continue;
    }

    // ---- Picker view ---------------------------------------------------------

    void _repaintPicker() {
        _drawPickerButtons();
        _drawSvSquare();
        _drawHueStrip();
        _drawSvCursor();
        _drawHueCursor();
    }

    void _drawPickerButtons() {
        tft.fillRect(0, kBarY, S_CANVAS_W, S_BTN_H, S_BG);

        // Active state renders as Primary (green), inactive as Neutral —
        // same palette as the old hand-rolled bar, now via the kit.
        _pickBtns[0].label = "OFF";
        _pickBtns[0].style = (_mode == LedMode::Off) ? SBtnStyle::Primary
                                                     : SBtnStyle::Neutral;
        _pickBtns[1].label = "ON";
        _pickBtns[1].style = (_mode != LedMode::Off) ? SBtnStyle::Primary
                                                     : SBtnStyle::Neutral;
        _pickBtns[2].label = "SAVE";
        _pickBtns[2].style = _dirty ? SBtnStyle::Primary : SBtnStyle::Neutral;
        sButtonBar(_pickBtns, 3, kBarY);
        for (auto& b : _pickBtns) b.draw();
    }

    void _drawSvSquare() const {
        uint16_t buf[kSvW];
        for (int row = 0; row < kPickH; row++) {
            uint8_t v = (uint8_t)(255u - (uint32_t)row * 255u / (kPickH - 1));
            for (int col = 0; col < kSvW; col++) {
                uint8_t s = (uint8_t)((uint32_t)col * 255u / (kSvW - 1));
                buf[col] = hsvToRgb565(_hue, s, v);
            }
            tft.pushImage(kSvX, kPickY + row, kSvW, 1, buf);
        }
    }

    void _drawHueStrip() const {
        for (int row = 0; row < kPickH; row++) {
            uint8_t hue = (uint8_t)((uint32_t)row * 255u / (kPickH - 1));
            tft.fillRect(kHueX, kPickY + row, kHueW, 1, hsvToRgb565(hue, 255, 255));
        }
    }

    void _drawSvCursor() const {
        int cx = kSvX + (int)((uint32_t)_sat * (kSvW - 1) / 255u);
        int cy = kPickY + (int)((uint32_t)(255u - _val) * (kPickH - 1) / 255u);
        uint16_t col = (_val > 128) ? (uint16_t)0xFFFF : (uint16_t)0x0000;
        // 8×8 hollow square cursor (2px border)
        tft.drawRect(cx - 4, cy - 4, 8, 8, col);
        tft.drawRect(cx - 3, cy - 3, 6, 6, col);
    }

    void _drawHueCursor() const {
        int cy = kPickY + (int)((uint32_t)_hue * (kPickH - 1) / 255u);
        tft.fillRect(kHueX, cy - 1, kHueW, 3, 0xFFFF);
    }

    void _svFromTouch(int px, int py) {
        int cx = constrain(px, (int)kSvX, (int)(kSvX + kSvW - 1));
        int cy = constrain(py, (int)kPickY, (int)(kPickY + kPickH - 1));
        _sat = (uint8_t)((uint32_t)(cx - kSvX) * 255u / (kSvW - 1));
        _val = (uint8_t)(255u - (uint32_t)(cy - kPickY) * 255u / (kPickH - 1));
    }

    void _hueFromTouch(int py) {
        int cy = constrain(py, (int)kPickY, (int)(kPickY + kPickH - 1));
        _hue = (uint8_t)((uint32_t)(cy - kPickY) * 255u / (kPickH - 1));
    }

    void _applyLed() const {
        if (_mode == LedMode::Off) {
            LED_WRITE(LED_R_CH, 0);
            LED_WRITE(LED_G_CH, 0);
            LED_WRITE(LED_B_CH, 0);
            return;
        }
        RGB8 c = hsvToRgb(_hue, _sat, _val);
        LED_WRITE(LED_R_CH, c.r);
#if NFC_ENABLED
        (void)c.g;
#else
        LED_WRITE(LED_G_CH, c.g);
#endif
        LED_WRITE(LED_B_CH, c.b);
    }

    SectionResult _handlePicker(TouchPhase phase, int x, int y) {
        // SV square pointer capture
        if (_svDragging) {
            if (phase == TouchPhase::Move || phase == TouchPhase::Release) {
                _svFromTouch(x, y);
                _drawSvCursor();
                _applyLed();
                if (phase == TouchPhase::Release) { _svDragging = false; _dirty = true; }
            }
            return SectionResult::Continue;
        }

        // Hue strip pointer capture
        if (_hueDragging) {
            if (phase == TouchPhase::Move || phase == TouchPhase::Release) {
                _hueFromTouch(y);
                _drawHueStrip();
                _drawHueCursor();
                _drawSvSquare();
                _drawSvCursor();
                _applyLed();
                if (phase == TouchPhase::Release) { _hueDragging = false; _dirty = true; }
            }
            return SectionResult::Continue;
        }

        // Fresh press — hit-test for drag capture
        if (phase == TouchPhase::Press) {
            Rect svRect  = { kSvX,  kPickY, kSvW,  kPickH };
            Rect hueRect = { kHueX, kPickY, kHueW, kPickH };
            if (hitTest(svRect, x, y)) {
                _svDragging = true;
                _svFromTouch(x, y);
                _drawSvCursor();
                _applyLed();
            } else if (hitTest(hueRect, x, y)) {
                _hueDragging = true;
                _hueFromTouch(y);
                _drawHueStrip();
                _drawHueCursor();
                _drawSvSquare();
                _drawSvCursor();
                _applyLed();
            }
            return SectionResult::Continue;
        }

        if (phase != TouchPhase::Release) return SectionResult::Continue;

        // Release — back zone or button bar
        if (isBackTap(x, y)) {
            // Discard working copy
            _hue  = g_settings.ledHue;
            _sat  = g_settings.ledSat;
            _val  = g_settings.ledVal;
            _mode = g_settings.ledMode;
            _applyLed();
            _view = LedView::List;
            clearContent();
            _repaintList();
            return SectionResult::Continue;
        }

        if (_pickBtns[0].hit(x, y)) {
            // OFF — no flash: the active-state repaint is the feedback
            _mode = LedMode::Off;
            g_settings.ledMode = _mode;
            _applyLed();
            _dirty = true;
            _drawPickerButtons();
        } else if (_pickBtns[1].hit(x, y)) {
            // ON — restore Static if coming from Off
            if (_mode == LedMode::Off) _mode = LedMode::Static;
            g_settings.ledMode = _mode;
            _applyLed();
            _dirty = true;
            _drawPickerButtons();
        } else if (_pickBtns[2].hit(x, y)) {
            // SAVE — kit flash replaces the old hand-rolled 100 ms invert
            _pickBtns[2].flash();
            g_settings.ledHue  = _hue;
            g_settings.ledSat  = _sat;
            g_settings.ledVal  = _val;
            g_settings.ledMode = _mode;
            saveSettings();
            _dirty = false;
            _drawPickerButtons();
        }

        return SectionResult::Continue;
    }
};
