#pragma once
// display/tft.h — the global TFT_eSPI object, rehomed (ADR-061 D9 step 1 /
// TASK-468). Level-0/1 component under ADR-060 D2a: declares one thing,
// pulls in nothing above it.
//
// Before this: `TFT_eSPI tft = TFT_eSPI();` was defined in the vendored
// `app/lib/SpotifyDiyThingUpstream/cheapYellowLCD.cpp` (see that
// directory's LOCAL_PATCHES.md, PATCH-TOUCHSCREEN-1), an upstream
// compatibility header nobody in this codebase owns, and every one of the
// ~28 files that call `tft.` re-declared its own local, hand-written
// extern for `tft` rather than including a shared declaration. This is
// that shared declaration; `tft.cpp` carries the single definition.
// `cheapYellowLCD.h`/`.cpp` now include this header instead of
// declaring/defining `tft` themselves (D9 step 1 note: the file coupling
// from `WinampDisplay : public CheapYellowDisplay` was NOT resolved here —
// that was D9 step 3 / TASK-469, since done: `WinampDisplay` now inherits
// `SpotifyDisplay` directly. `cheapYellowLCD.h`/`.cpp` themselves are the
// last piece, deleted in D9 step 4 / TASK-470).
//
// ADR-061 D9: "Step 1 is worth doing regardless of whether the chain
// completes. A single owned display/tft component is strictly better
// than a global defined in vendored upstream compat code."

#include <TFT_eSPI.h>

extern TFT_eSPI tft;
