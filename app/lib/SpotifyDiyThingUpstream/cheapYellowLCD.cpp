// PATCH-TOUCHSCREEN-1 (M-SRCLAYOUT Stage E / TASK-471) — `tft`'s one
// definition, moved out of cheapYellowLCD.h. See
// app/lib/SpotifyDiyThingUpstream/LOCAL_PATCHES.md.
#include <Arduino.h>
#include <WiFi.h>
#include <SpotifyArduino.h>
#include <string.h>
#include "cheapYellowLCD.h"

TFT_eSPI tft = TFT_eSPI();
