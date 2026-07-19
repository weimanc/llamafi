#pragma once
#include <TFT_eSPI.h>

// ADR-052 / M-DISPLAY-DELTA-COMMON.md (TASK-358): the single generalized
// piece from the display-repair survey — a stateless wrapper over TFT_eSPI's
// setViewport()/resetViewport(). Everything else in that survey (Clock's
// discrete-slot delta engine, VU meter's column diff, WebRadio's region
// repaint, Weather/Digital's field-gated erase, Game of Life's cell diff) was
// judged NOT to share code with this or each other — see the design doc.
// First (and so far only) consumer: app/src/planeRadarApp.h's per-aircraft
// dirty-rect repaint.
//
// Clip every subsequent draw call to [x,y,w,h] (absolute screen coords,
// vpDatum=false — no origin shift), run `repairFn` — typically an app's
// EXISTING whole-static-layer redraw function, called verbatim — then
// always restore the full-screen viewport before returning.
//
// Invariants (confirmed by reading TFT_eSPI.cpp's setViewport()):
//  - out-of-bounds/degenerate boxes are handled internally (_vpOoB inhibits
//    all drawing; no pre-clamping needed, no crash on a bad box)
//  - the viewport is a single non-stacking global — repairFn must NOT itself
//    call setViewport/resetViewport (no reentrancy)
//  - clips PIXEL WRITES only, not the CPU cost of repairFn's shape-iteration
//    loop (see ADR-052 consequences: not a goal here)
template <typename Fn>
inline void withViewportRepair(TFT_eSPI& tft, int32_t x, int32_t y,
                                int32_t w, int32_t h, Fn&& repairFn) {
    tft.setViewport(x, y, w, h, false);
    repairFn();
    tft.resetViewport();
}
