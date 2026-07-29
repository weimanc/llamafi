#pragma once
#include "settingsSection.h"
#include "sliderWidget.h"
#include "../settingsStorage.h"
#include "../backlightFlow.h"

// DisplaySection — pure EDITOR since M-SETTINGS-WIRE2 G5 (ADR-050 rule 2):
// the LDR sample→map→ledcWrite loop moved to BacklightFlow (g_backlight),
// which owns the backlight in every app and at boot. This section renders
// rows, edits values, and borrows the backlight only through the owner's
// pause()/applyManual()/resume() handshake (the g_ledFlow idiom). No direct
// analogRead/ledcWrite here.

class DisplaySection : public SettingsSection {
public:
    const char* title() const override { return "Display"; }

    void enter() override {
        _slider.init(1, 10, g_settings.dispLevel);
        _shownLdr    = g_backlight.ldrRaw();
        _repaintMs   = millis();
        repaint();
    }

    SectionResult tick() override {
        // Repaint cadence only — the owner samples; we just display its value.
        if (millis() - _repaintMs >= 500) {
            _repaintMs = millis();
            int16_t fresh = g_backlight.ldrRaw();
            if (abs(fresh - _shownLdr) > 20) {
                _shownLdr = fresh;
                _repaintLdrRows();
            }
        }
        return SectionResult::Continue;
    }

    void repaint() override {
        drawHeader();
        clearContent();
        bool autoOn = g_settings.dispAuto;
        drawRow(S_CONTENT_Y + 0 * S_ROW_H, {
            "Auto", autoOn ? "On" : "Off", S_LABEL,
            autoOn ? S_VALUE_ON : S_VALUE_OFF
        });
        _slider.render(S_CONTENT_Y + 1 * S_ROW_H, "Level", g_settings.dispAuto);
        _repaintLdrRows();
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (phase == TouchPhase::Release && isBackTap(x, y))
            return SectionResult::GoBack;

        if (!g_settings.dispAuto) {
            const int levelRowY = S_CONTENT_Y + 1 * S_ROW_H;
            if (phase == TouchPhase::Press) {
                if (_slider.onPress(x, y, levelRowY))
                    g_backlight.pause();   // borrow the backlight for live preview
            } else if (phase == TouchPhase::Move && _slider.isDragging()) {
                _slider.onMove(x);
                _slider.renderDynamic(levelRowY, "Level", false);
                g_backlight.applyManual(_slider.value());
            } else if (phase == TouchPhase::Release && _slider.isDragging()) {
                g_settings.dispLevel = (uint8_t)_slider.onRelease(x);
                saveSettings();
                g_backlight.resume();      // owner re-applies from committed settings
                _slider.renderDynamic(levelRowY, "Level", false);
                return SectionResult::Continue;
            }
        }

        if (phase == TouchPhase::Release) {
            int row = tapToRow(y);
            if (row == 0) {
                g_settings.dispAuto = !g_settings.dispAuto;
                saveSettings();
                g_backlight.applyMode();
                repaint();
            }
            // Cal rows: tap to capture the owner's current LDR reading.
            // Cal:bright (ldrLow) = expected low ADC in bright room.
            // Cal:dark   (ldrHigh) = expected high ADC in dark room.
            const int calY = S_CONTENT_Y + 3 * S_ROW_H + S_ROW_HDR_H;
            if (y >= calY && y < calY + S_ROW_H) {
                g_settings.ldrLow = _shownLdr;
                saveSettings();
                g_backlight.applyMode();
                _repaintLdrRows();
            } else if (y >= calY + S_ROW_H && y < calY + 2 * S_ROW_H) {
                // Only store if reading is above the bright calibration — prevents
                // accidentally wiping cal by tapping in ambient (ldrRaw ≈ 0).
                if (_shownLdr > g_settings.ldrLow + 10) {
                    g_settings.ldrHigh = _shownLdr;
                    saveSettings();
                    g_backlight.applyMode();
                    _repaintLdrRows();
                }
            }
        }

        return SectionResult::Continue;
    }

private:
    SliderWidget  _slider;
    int16_t       _shownLdr   = 0;
    unsigned long _repaintMs  = 0;

    void _repaintLdrRows() {
        char bufLive[8], bufLow[8], bufHigh[8];
        snprintf(bufLive, sizeof(bufLive), "%d", (int)_shownLdr);
        snprintf(bufLow,  sizeof(bufLow),  "%d", (int)g_settings.ldrLow);
        snprintf(bufHigh, sizeof(bufHigh), "%d", (int)g_settings.ldrHigh);
        // ldr_live(26) + subhdr(22) + dark(26) + bright(26) = 100px
        tft.fillRect(0, S_CONTENT_Y + 2 * S_ROW_H, S_CANVAS_W, 3 * S_ROW_H + S_ROW_HDR_H, S_BG);
        drawRow(S_CONTENT_Y + 2 * S_ROW_H, { "LDR", bufLive, S_LABEL, S_VALUE });
        int subY = S_CONTENT_Y + 3 * S_ROW_H;
        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(S_SUBHDR);
        tft.drawString("Calibration", S_COL_LABEL, subY + 4, 2);
        tft.drawFastHLine(S_COL_LABEL, subY + S_ROW_HDR_H - 1, S_CANVAS_W - S_COL_LABEL, S_SEP);
        int calY = subY + S_ROW_HDR_H;
        drawRow(calY,           { "Cal: bright", bufLow,  S_LABEL, S_VALUE });
        drawRow(calY + S_ROW_H, { "Cal: dark",   bufHigh, S_LABEL, S_VALUE });
    }
};
