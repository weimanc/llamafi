// PATCH-TOUCHSCREEN-1 (M-SRCLAYOUT Stage E / TASK-471) — definitions moved out
// of touchScreen.h, which is now declarations-only. See
// app/lib/SpotifyDiyThingUpstream/LOCAL_PATCHES.md.
#include "touchScreen.h"

bool previousTrackStatus = false;
bool nextTrackStatus = false;

CYD28_TouchR ts(CYD28_DISPLAY_HOR_RES_MAX, CYD28_DISPLAY_VER_RES_MAX);

SpotifyArduino *spotify_touch;

void touchSetup(SpotifyArduino *spotifyObj) {
//  mySpi.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
//  ts.begin(mySpi);
  ts.begin();
  ts.setRotation(1);
  spotify_touch = spotifyObj;
}

bool handleTouched() {
  previousTrackStatus = false;
  nextTrackStatus = false;
  //if (ts.tirqTouched() && ts.touched()) {
  if (ts.touched()) {
    CYD28_TS_Point p = ts.getPointScaled();
    Serial.print("Pressure = ");
    Serial.print(p.z);
    Serial.print(", x = ");
    Serial.print(p.x);
    Serial.print(", y = ");
    Serial.print(p.y);
    delay(30);
    Serial.println();
    if (p.x < 120) {
      previousTrackStatus = true;
      //spotify_touch->previousTrack();
      return true;
    } else if (p.x > 200) {
      nextTrackStatus = true;
      //spotify_touch->nextTrack();
      return true;
    }
  }

  return false;

}
