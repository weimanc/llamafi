#pragma once
// sliderWidget.h — horizontal drag slider for use inside SettingsSection.
//
// Follows the pointer-capture pattern from M-TOUCH-CAPTURE:
//   onPress()   — establishes capture if tap lands in the row hit zone.
//   onMove()    — called unconditionally while isDragging(); no re-hit-test.
//   onRelease() — commits value, releases capture.
//
// The caller (e.g. DisplaySection) is responsible for:
//   1. Calling onPress/onMove/onRelease in its handleInput() override.
//   2. Calling render() after onMove to update the visual.
//   3. Applying the committed value (ledcWrite / saveSettings) on onRelease.
//   4. Passing disabled=true when the row should be read-only (e.g. auto-brightness on).
//
// Value range is generic (min/max/step); brightness uses 1–10.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "../touch/hitbox.h"
#include "settingsSection.h"   // palette + geometry constants

extern TFT_eSPI tft;

class SliderWidget {
public:
    // ---- Setup ---------------------------------------------------------------

    void init(int minVal, int maxVal, int initialVal) {
        _min      = minVal;
        _max      = maxVal;
        _value    = constrain(initialVal, minVal, maxVal);
        _dragging = false;
    }

    int  value()      const { return _value; }
    bool isDragging() const { return _dragging; }

    // Force value without a touch gesture (e.g. on section enter to sync from storage).
    void setValue(int v) { _value = constrain(v, _min, _max); }

    // ---- Touch capture -------------------------------------------------------

    // Call on TouchPhase::Press. Returns true if the slider captured the event.
    // rowY: screen y of the top of this slider row (S_CONTENT_Y + row * S_ROW_H).
    bool onPress(int px, int py, int rowY) {
        Rect zone = { 0, (int16_t)rowY, S_CANVAS_W, S_ROW_H };
        if (!hitTest(zone, px, py)) return false;
        _dragging = true;
        _setValue(xToValue(px));
        return true;
    }

    // Call on TouchPhase::Move — only when isDragging().
    // Clamps x to the track range; y is ignored after capture.
    void onMove(int px) {
        if (!_dragging) return;
        _setValue(xToValue(px));
    }

    // Call on TouchPhase::Release — only when isDragging().
    // Returns the committed value and releases capture.
    int onRelease(int px) {
        _setValue(xToValue(px));
        _dragging = false;
        return _value;
    }

    // ---- Render --------------------------------------------------------------

    // Full row repaint at rowY.
    //   label    — row label drawn at S_COL_LABEL (e.g. "Level").
    //   disabled — greyed out when auto-brightness is active; ignores touches.
    void render(int rowY, const char* label, bool disabled = false) const {
        tft.fillRect(0, rowY, S_CANVAS_W, S_ROW_H, S_BG);

        int mid = rowY + S_ROW_H / 2;

        // Label (left)
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(disabled ? S_VALUE_OFF : S_LABEL);
        tft.drawString(label, S_COL_LABEL, mid, 2);

        // Value number (right, aligned with other setting rows)
        char buf[4];
        snprintf(buf, sizeof(buf), "%d", _value);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(disabled ? S_VALUE_OFF : S_VALUE_ON);
        tft.drawString(buf, S_COL_VALUE, mid, 2);

        tft.setTextDatum(TL_DATUM);

        // Track colours
        uint16_t cFill   = disabled ? S_VALUE_OFF : S_VALUE_ON;
        uint16_t cEmpty  = S_SEP;
        uint16_t cKnob   = disabled ? S_SEP       : S_HDR_TXT;
        uint16_t cBorder = disabled ? S_SEP       : S_VALUE_ON;

        int trackY = rowY + (S_ROW_H - kTrackH) / 2;
        int knobCx = valueToX(_value);

        // Unfilled track (full span)
        tft.fillRect(kTrackX0, trackY,
                     kTrackX1 - kTrackX0, kTrackH, cEmpty);

        // Filled track (left of knob centre)
        if (knobCx > kTrackX0)
            tft.fillRect(kTrackX0, trackY,
                         knobCx - kTrackX0, kTrackH, cFill);

        // Knob (centred on knobCx)
        int kx = knobCx - kKnobW / 2;
        int ky = rowY   + (S_ROW_H - kKnobH) / 2;
        tft.fillRect(kx, ky, kKnobW, kKnobH, cKnob);
        tft.drawRect(kx, ky, kKnobW, kKnobH, cBorder);
    }

private:
    // ---- Track geometry -------------------------------------------------------
    //
    // Layout within a 275 × 26 px row:
    //
    //  x:0        8           68              248   268    274
    //  |<-- bg -->|<-- label->|<---- track --->|<val>|<-- bg -->|
    //             "Level"     [====o----------] "7"
    //
    // Knob centre range is inset by kKnobW/2 so the knob never overflows the track.
    //   kKnobCX0 = 68 + 7 = 75   (at min value)
    //   kKnobCX1 = 248 - 7 = 241  (at max value)
    //   Span = 166 px for 9 steps (min=1..max=10) → ~18 px/step

    static constexpr int16_t kTrackX0  =  68;   // track left edge
    static constexpr int16_t kTrackX1  = 248;   // track right edge
    static constexpr int16_t kTrackH   =   6;   // track bar height (px)
    static constexpr int16_t kKnobW    =  14;   // knob width  (px)
    static constexpr int16_t kKnobH    =  20;   // knob height (px) — tall for resistive touch
    static constexpr int16_t kKnobCX0  = kTrackX0 + kKnobW / 2;   // 75
    static constexpr int16_t kKnobCX1  = kTrackX1 - kKnobW / 2;   // 241

    int  _min      = 1;
    int  _max      = 10;
    int  _value    = 7;
    bool _dragging = false;

    // Map value → knob centre x.
    int valueToX(int v) const {
        int range = _max - _min;
        if (range <= 0) return kKnobCX0;
        return kKnobCX0 + (v - _min) * (kKnobCX1 - kKnobCX0) / range;
    }

    // Map raw touch x → value (clamped to [min,max]).
    int xToValue(int px) const {
        int range = _max - _min;
        if (range <= 0) return _min;
        int cx = constrain(px, (int)kKnobCX0, (int)kKnobCX1);
        return _min + (cx - kKnobCX0) * range / (kKnobCX1 - kKnobCX0);
    }

    void _setValue(int v) { _value = constrain(v, _min, _max); }
};
