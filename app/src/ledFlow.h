#pragma once
#include <Arduino.h>
#include "util/mathUtil.h"
#include "settingsStorage.h"

// ledFlow.h — background LED animator (ticked from main loop).
//
// Moved verbatim out of settings/ledSection.h (M-SETTINGS-WIRE2 G5 / review
// W-4): LedFlow is the runtime OWNER of the LED settings, and ADR-050 rule 2
// requires owners to live outside app/src/settings/ — the settings-wiring
// gate (check_settings_wiring.py) counts consumers by file location, so the
// owner living inside settings/ made the gate's own exemplar fail. Pure move,
// zero behaviour change; ledSection.h includes this header.

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
