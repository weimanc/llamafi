#pragma once
// display/tft.h — the global TFT_eSPI object, rehomed (ADR-061 D9 step 1 /
// TASK-468). Level-0/1 component under ADR-060 D2a: declares one thing,
// pulls in nothing above it.
//
// Before this: `TFT_eSPI tft = TFT_eSPI();` was defined in the vendored
// `app/lib/SpotifyDiyThingUpstream/cheapYellowLCD.cpp` (see PATCH-TOUCHSCREEN-1
// in that directory's LOCAL_PATCHES.md — the file itself is gone as of
// TASK-470 below, but the patch record explains the history), an upstream
// compatibility header nobody in this codebase owned, and every one of the
// ~28 files that call `tft.` re-declared its own local, hand-written
// extern for `tft` rather than including a shared declaration. This is
// that shared declaration; `tft.cpp` carries the single definition.
// D9's full chain, now closed: step 1 (TASK-468) rehomed `tft` here; step 3
// (TASK-469) flattened `WinampDisplay : public CheapYellowDisplay` onto
// `WinampDisplay : public SpotifyDisplay` directly; step 4 (TASK-470)
// deleted `cheapYellowLCD.h`/`.cpp` entirely, since nothing depended on the
// class any more.
//
// ADR-061 D9: "Step 1 is worth doing regardless of whether the chain
// completes. A single owned display/tft component is strictly better
// than a global defined in vendored upstream compat code."

#include <TFT_eSPI.h>

extern TFT_eSPI tft;
