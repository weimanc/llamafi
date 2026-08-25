// PATCH-TOUCHSCREEN-1 (M-SRCLAYOUT Stage E / TASK-471) — `tft`'s one
// definition, moved out of cheapYellowLCD.h and into this file, then
// rehomed again (ADR-061 D9 step 1 / TASK-468) into
// `app/src/display/tft.cpp` — this file no longer defines it, only
// includes the header chain that (transitively) declares it, same as
// before. See app/lib/SpotifyDiyThingUpstream/LOCAL_PATCHES.md.
#include <Arduino.h>
#include <WiFi.h>
#include <SpotifyArduino.h>
#include <string.h>
#include "cheapYellowLCD.h"
