#pragma once
// PATCH-SPOTIFYLOGIC-1 (M-SRCLAYOUT Stage E / TASK-471,
// app/lib/SpotifyDiyThingUpstream/LOCAL_PATCHES.md): this file used to define
// `spotify`/songStartMillis/lastTrackUri/etc. and every function body
// directly, with no #pragma once — safe only while main.cpp was this
// header's sole includer. Declarations only now; definitions live in
// spotifyLogic.cpp, needed once app/src component conversions (apps/
// spotifyApp.h) include this header from a second translation unit.

#include <WiFiClientSecure.h>
#include <SpotifyArduino.h>
#include "spotifyDisplay.h"
#include "logDecode.h"
#include "logHeartbeat.h"
#include "logSink.h"
#include "spotifyTask.h"
#include <esp_log.h>

extern WiFiClientSecure client;   // defined once, in app/src/main.cpp

extern SpotifyArduino spotify;

// Track duration + interpolation anchor. WinampDisplay (winamp/
// winampDisplay.h) already carries its own `extern` for these three and for
// songDuration/g_lastRenderMs — declared again here so this header is the
// single source of truth for anyone else that wants them (apps/spotifyApp.h).
extern long     songStartMillis;
extern long     songDuration;
extern uint32_t g_lastRenderMs;   // TASK-059: millis() of last snapshot-driven WinampDisplay repaint

extern char lastTrackUri[200];
extern char lastTrackContextUri[200];

void spotifySetup(SpotifyDisplay *theDisplay, const char *clientId, const char *clientSecret);
void spotifyRefreshToken(const char *refreshToken);

// poll-002: 100ms tick → ~3px/tick on a 280px bar at typical track length.
// Renderer is idempotent (no-op when pixel position unchanged), so a fast
// tick doesn't spam SPI writes.
void updateProgressBar();
void updateCurrentlyPlaying(boolean forceUpdate);
