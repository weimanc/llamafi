#pragma once
#include <Arduino.h>
#include "settingsStorage.h"

// backlightFlow.h — global backlight controller (M-SETTINGS-WIRE2 G5).
//
// Runtime OWNER of dispAuto/dispLevel/ldrLow/ldrHigh (ADR-050): before this,
// the LDR sample→map→ledcWrite loop lived in DisplaySection::tick() and ran
// ONLY while Settings→Display was the active view — auto-brightness froze at
// the last duty on leaving the screen, and boot applied manual dispLevel even
// with dispAuto=true. Constants and mapping transcribed from the old
// displaySection.h:24-42 loop. LedFlow sibling: applyMode() at boot/toggle,
// tick() from the main loop, pause()/resume() so the Display section's manual
// slider preview doesn't fight the controller.

#define LDR_PIN          34   // ADC1 — no WiFi/ADC2 conflict
#define TFT_LEDC_CHANNEL  0

class BacklightFlow {
public:
    // Boot + mode-toggle applier. Auto: one immediate sample → mapped duty.
    // Manual: dispLevel duty. Safe from setup() once analogReadResolution +
    // ledcSetup/ledcAttachPin have run (main.cpp:2123-2125).
    void applyMode() {
        if (_autoValid()) {
            _ldrRaw = _sample();
            _ldrUpdateMs = millis();
            int duty = _mapDuty(_ldrRaw);
            _lastAutoDuty = duty;
            ledcWrite(TFT_LEDC_CHANNEL, (uint32_t)duty);
        } else {
            applyManual(g_settings.dispLevel);
        }
    }

    // 500 ms LDR cadence, ±20 ADC hysteresis, ≥3-duty-step write filter —
    // verbatim from the old DisplaySection loop. No-op in manual mode or
    // while paused (section slider preview owns the backlight then).
    void tick() {
        if (_paused || !_autoValid()) return;
        unsigned long now = millis();
        if (now - _ldrUpdateMs < 500) return;
        _ldrUpdateMs = now;
        int16_t fresh = _sample();
        if (abs(fresh - _ldrRaw) > 20) _ldrRaw = fresh;
        int duty = _mapDuty(_ldrRaw);
        if (abs(duty - _lastAutoDuty) >= 3) {
            _lastAutoDuty = duty;
            ledcWrite(TFT_LEDC_CHANNEL, (uint32_t)duty);
        }
    }

    void pause()  { _paused = true; }
    void resume() { _paused = false; applyMode(); }

    // Section live-preview path (manual slider drag) — direct duty, no save.
    void applyManual(int level) {
        int duty = (int)map(constrain(level, 1, 10), 1, 10, 25, 255);
        _lastAutoDuty = duty;   // "last written duty" — keeps `get duty` truthful in manual mode
        ledcWrite(TFT_LEDC_CHANNEL, (uint32_t)duty);
    }

    int16_t ldrRaw() {
        // Keep the Display section's live LDR row fresh even in manual mode
        // (tick() only samples when auto) — cheap, called at repaint cadence.
        if (_paused || !_autoValid()) _ldrRaw = _sample();
        return _ldrRaw;
    }

#ifdef SERIAL_DEBUG
    // T-SETW-14: sticky ADC override — the harness can't darken the room.
    // -1 clears. While set, every sample path returns the injected value.
    void injectLdr(int16_t raw) { _inject = raw; }
    int  currentDuty() const    { return _lastAutoDuty; }
    bool injected() const       { return _inject >= 0; }
#endif

private:
    bool          _paused       = false;
    int16_t       _ldrRaw       = 0;
    unsigned long _ldrUpdateMs  = 0;
    int           _lastAutoDuty = -1;
#ifdef SERIAL_DEBUG
    int16_t       _inject       = -1;
#endif

    bool _autoValid() const {
        return g_settings.dispAuto && g_settings.ldrHigh > g_settings.ldrLow;
    }

    int16_t _sample() {
#ifdef SERIAL_DEBUG
        if (_inject >= 0) return _inject;
#endif
        return (int16_t)analogRead(LDR_PIN);
    }

    int _mapDuty(int16_t raw) const {
        int16_t c = constrain(raw, g_settings.ldrLow, g_settings.ldrHigh);
        return (int)map(c, g_settings.ldrLow, g_settings.ldrHigh, 255, 25);
    }
};

extern BacklightFlow g_backlight;
