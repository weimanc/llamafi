#pragma once
#include "settingsSection.h"
#include "sliderWidget.h"
#include "../settingsStorage.h"

#define LDR_PIN          34
#define TFT_LEDC_CHANNEL  0

class DisplaySection : public SettingsSection {
public:
    const char* title() const override { return "Display"; }

    void enter() override {
        _slider.init(1, 10, g_settings.dispLevel);
        _ldrRaw       = (int16_t)analogRead(LDR_PIN);
        _ldrUpdateMs  = millis();
        _lastAutoLevel = -1;
        repaint();
    }

    void tick() override {
        if (millis() - _ldrUpdateMs >= 500) {
            _ldrUpdateMs = millis();
            int16_t fresh = (int16_t)analogRead(LDR_PIN);
            if (abs(fresh - _ldrRaw) > 20) {
                _ldrRaw = fresh;
                _repaintLdrRows();
            }
        }
        if (g_settings.dispAuto) {
            int16_t raw = constrain(_ldrRaw, g_settings.ldrLow, g_settings.ldrHigh);
            int level = map(raw, g_settings.ldrLow, g_settings.ldrHigh, 1, 10);
            if (abs(level - _lastAutoLevel) >= 1) {
                _lastAutoLevel = level;
                _applyBrightness(level);
            }
        }
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
                _slider.onPress(x, y, levelRowY);
            } else if (phase == TouchPhase::Move && _slider.isDragging()) {
                _slider.onMove(x);
                _slider.render(levelRowY, "Level", false);
                _applyBrightness(_slider.value());
            } else if (phase == TouchPhase::Release && _slider.isDragging()) {
                g_settings.dispLevel = (uint8_t)_slider.onRelease(x);
                _applyBrightness(g_settings.dispLevel);
                saveSettings();
                _slider.render(levelRowY, "Level", false);
                return SectionResult::Continue;
            }
        }

        if (phase == TouchPhase::Release) {
            int row = tapToRow(y);
            if (row == 0) {
                g_settings.dispAuto = !g_settings.dispAuto;
                saveSettings();
                if (!g_settings.dispAuto) _applyBrightness(g_settings.dispLevel);
                repaint();
            }
        }

        return SectionResult::Continue;
    }

private:
    SliderWidget  _slider;
    int16_t       _ldrRaw        = 0;
    unsigned long _ldrUpdateMs   = 0;
    int           _lastAutoLevel = -1;

    void _applyBrightness(int level) {
        ledcWrite(TFT_LEDC_CHANNEL, (uint32_t)map(constrain(level, 1, 10), 1, 10, 25, 255));
    }

    void _repaintLdrRows() {
        char bufLive[8], bufLow[8], bufHigh[8];
        snprintf(bufLive, sizeof(bufLive), "%d", (int)_ldrRaw);
        snprintf(bufLow,  sizeof(bufLow),  "%d", (int)g_settings.ldrLow);
        snprintf(bufHigh, sizeof(bufHigh), "%d", (int)g_settings.ldrHigh);
        tft.fillRect(0, S_CONTENT_Y + 2 * S_ROW_H, S_CANVAS_W, 3 * S_ROW_H, S_BG);
        drawRow(S_CONTENT_Y + 2 * S_ROW_H, { "LDR",      bufLive, S_LABEL, S_VALUE     });
        drawRow(S_CONTENT_Y + 3 * S_ROW_H, { "LDR Low",  bufLow,  S_LABEL, S_VALUE_OFF });
        drawRow(S_CONTENT_Y + 4 * S_ROW_H, { "LDR High", bufHigh, S_LABEL, S_VALUE_OFF });
    }
};
