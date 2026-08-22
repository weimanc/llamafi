#pragma once
// boot/boot.h — declares setup(), the Arduino boot sequence (M-SRCLAYOUT
// Stage E, TASK-471). Body lives in boot.cpp as its own translation unit.
//
// PURE MOVE. Stage C (TASK-455) moved setup()'s body out of main.cpp
// verbatim into this file as an inline-in-header block; Stage E gives it a
// real .cpp instead — not one line of the body itself is edited (see
// boot.cpp's header comment for the exact contract and how it was verified:
// byte-identical .map dram0_0_seg size, TASK-488's precedent, LL-137).
//
// setup() keeps its exact name and signature. The Arduino/ESP-IDF runtime
// only needs a globally-linked, non-static `void setup()` reachable at link
// time — it does not need to be textually present in main.cpp — so this
// declaration exists purely for discoverability/documentation. Nothing
// currently calls setup() by declaration (the runtime finds it by symbol),
// so main.cpp no longer #includes this header; it is kept anyway as the
// obvious place to look for "where does setup() live".

void setup();
