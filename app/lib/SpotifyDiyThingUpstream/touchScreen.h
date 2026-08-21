// PATCH-TOUCHSCREEN-1 (M-SRCLAYOUT Stage E / TASK-471, app/lib/SpotifyDiyThingUpstream/LOCAL_PATCHES.md):
// this file used to define `ts`/previousTrackStatus/nextTrackStatus/spotify_touch
// and the two function bodies directly, with no #pragma once — safe only while
// cheapYellowLCD.h (its sole includer) was itself only ever included from one
// translation unit. Now that app/src component conversions put cheapYellowLCD.h
// (via winamp/winampDisplay.h) into more than one .cpp, every definition below
// had to move to touchScreen.cpp with this header holding only declarations.
#pragma once

//#include <XPT2046_Touchscreen.h>
#include "CYD28_TouchscreenR.h"
#include <SPI.h>
#include <SpotifyArduino.h>

//#define XPT2046_IRQ 36
//#define XPT2046_MOSI 32
//#define XPT2046_MISO 39
//#define XPT2046_CLK 25
//#define XPT2046_CS 33

#define CYD28_DISPLAY_HOR_RES_MAX 320
#define CYD28_DISPLAY_VER_RES_MAX 240

extern bool previousTrackStatus;
extern bool nextTrackStatus;

//SPIClass mySpi = SPIClass(HSPI);
//
//XPT2046_Touchscreen ts(XPT2046_CS, XPT2046_IRQ);  // Param 2 - Touch IRQ Pin - interrupt enabled polling
extern CYD28_TouchR ts;

extern SpotifyArduino *spotify_touch;

void touchSetup(SpotifyArduino *spotifyObj);
bool handleTouched();
