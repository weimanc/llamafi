// app/src/debug/touchDebugOverlay.cpp — method bodies + the instance, out-of-line
// (M-SRCLAYOUT Stage E / TASK-471). Body compiles only under TOUCH_DEBUG_OVERLAY;
// the .cpp itself is always compiled, same convention as the other debug
// console components.
#include "debug/touchDebugOverlay.h"

#ifdef TOUCH_DEBUG_OVERLAY

TouchDebugOverlay g_touchDebug;

void TouchDebugOverlay::onTouch(int x, int y) {
    if (!enabled) return;
    if (style == DbgCursorStyle::Diamond) drawDiamond(x, y);
    else                                  drawCrosshair(x, y);
}

void TouchDebugOverlay::drawDiamond(int x, int y) {
    tft.drawPixel(x,     y,     0xF800);   // centre
    tft.drawPixel(x,     y - 1, 0xF800);   // N
    tft.drawPixel(x,     y + 1, 0xF800);   // S
    tft.drawPixel(x - 1, y,     0xF800);   // W
    tft.drawPixel(x + 1, y,     0xF800);   // E
}

void TouchDebugOverlay::drawCrosshair(int x, int y) {
    tft.drawFastHLine(0, y, 275, 0x4208);   // horizontal -- x:0..274
    tft.drawFastVLine(x, 0, 240, 0x4208);   // vertical   -- y:0..239
}

#endif // TOUCH_DEBUG_OVERLAY
