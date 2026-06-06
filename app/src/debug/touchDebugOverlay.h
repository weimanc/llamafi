// app/src/debug/touchDebugOverlay.h
// Compile-time touch debug overlay (TOUCH_DEBUG_OVERLAY build flag).
// Stamps the last scaled touch position on screen after every Press/Move event.
// Overdraw only -- no erase. See touch-calibration.md section Touch debug overlay.
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
    void onTouch(int x, int y) {
        if (!enabled) return;
        if (style == DbgCursorStyle::Diamond) drawDiamond(x, y);
        else                                  drawCrosshair(x, y);
    }

private:
    void drawDiamond(int x, int y) {
        tft.drawPixel(x,     y,     0xF800);   // centre
        tft.drawPixel(x,     y - 1, 0xF800);   // N
        tft.drawPixel(x,     y + 1, 0xF800);   // S
        tft.drawPixel(x - 1, y,     0xF800);   // W
        tft.drawPixel(x + 1, y,     0xF800);   // E
    }

    void drawCrosshair(int x, int y) {
        tft.drawFastHLine(0, y, 275, 0x4208);   // horizontal -- x:0..274
        tft.drawFastVLine(x, 0, 240, 0x4208);   // vertical   -- y:0..239
    }
};

extern TouchDebugOverlay g_touchDebug;   // defined in main.cpp inside same guard

#endif // TOUCH_DEBUG_OVERLAY
