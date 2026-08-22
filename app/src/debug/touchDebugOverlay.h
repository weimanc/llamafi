// app/src/debug/touchDebugOverlay.h
// Compile-time touch debug overlay (TOUCH_DEBUG_OVERLAY build flag).
// Stamps the last scaled touch position on screen after every Press/Move event.
// Overdraw only -- no erase. See touch-calibration.md section Touch debug overlay.
//
// M-SRCLAYOUT Stage E / TASK-471: declaration only — method bodies moved
// out-of-line into touchDebugOverlay.cpp, self-contained per SF.11.
#pragma once
#ifdef TOUCH_DEBUG_OVERLAY

#include <TFT_eSPI.h>
extern TFT_eSPI tft;

enum class DbgCursorStyle : uint8_t { Diamond, Crosshair };

class TouchDebugOverlay {
public:
    bool           enabled = true;
    DbgCursorStyle style   = DbgCursorStyle::Diamond;

    // Stamp cursor at scaled screen coords (x, y). Overdraw -- no erase.
    // Called from touch dispatch after the event reaches the active app.
    void onTouch(int x, int y);

private:
    void drawDiamond(int x, int y);
    void drawCrosshair(int x, int y);
};

extern TouchDebugOverlay g_touchDebug;   // defined in touchDebugOverlay.cpp

#endif // TOUCH_DEBUG_OVERLAY
