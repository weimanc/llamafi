#pragma once
#include <stdint.h>

struct Rect { int16_t x, y, w, h; };

// Returns true if (px, py) is inside r (exclusive right/bottom edge).
inline bool hitTest(const Rect& r, int px, int py) {
    return px >= r.x && px < r.x + r.w
        && py >= r.y && py < r.y + r.h;
}

// Returns 0-based row index for py, or -1 if outside r vertically.
inline int hitTestRow(const Rect& r, int rowH, int py) {
    if (py < r.y || py >= r.y + r.h) return -1;
    return (py - r.y) / rowH;
}

// Returns 0-based column index for px, or -1 if outside r horizontally.
inline int hitTestCol(const Rect& r, int colW, int px) {
    if (px < r.x || px >= r.x + r.w) return -1;
    return (px - r.x) / colW;
}
