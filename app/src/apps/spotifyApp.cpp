// apps/spotifyApp.cpp — SpotifyApp method bodies, out-of-line (M-SRCLAYOUT Stage E).
#include "apps/spotifyApp.h"

void SpotifyApp::init() {
  // TASK-417 / ADR-059 D8: switchApp() calls init() XOR resume(), never
  // both, on an AppId's first-ever entry each boot session — and Spotify
  // is ALWAYS a first-ever entry (main.cpp inits it directly at boot,
  // never through switchApp()/resume()). This happened to be harmless for
  // Spotify specifically (WinampDisplay's field defaults already match
  // Spotify's own caps/sinks — see winampDisplay.h), but relying on that
  // coincidence rather than setting it explicitly is exactly the gap that
  // bit WebRadio and Player (T_PLR_18's caught bug). Set it here too so
  // it's not accidental.
  winampDisplay.setPlayerCaps(CAP_TRANSPORT | CAP_SEEK | CAP_SHUFFLE | CAP_REPEAT);
  winampDisplay.setShuffleSink(nullptr);
  winampDisplay.setRepeatSink(nullptr);
  winampDisplay.setSeekSink(nullptr);
  winampDisplay.showDefaultScreen();
}

void SpotifyApp::resume() {
  // TASK-417 / ADR-059 D8: set caps BEFORE repaintChrome() below — it's
  // the very first paint of this resume() and must not draw shuffle/
  // repeat gated by whatever mode was active before this switch.
  winampDisplay.setPlayerCaps(CAP_TRANSPORT | CAP_SEEK | CAP_SHUFFLE | CAP_REPEAT);
  winampDisplay.repaintChrome();
  winampDisplay.invalidatePlaylist();
  // TASK-352: restore the default volume-commit seam (WebRadio may have
  // wired its own on the way out) and seed the slider from the current
  // snapshot rather than whatever pct repaintChrome() just redrew from
  // its lastVolumeRendered cache (could be WebRadio's, from before eject).
  winampDisplay.setVolumeSink(nullptr);
  // TASK-417: same reasoning for shuffle/repeat — restore the default
  // (spotifyTask ACT_SHUFFLE/ACT_REPEAT) commit seam and re-seed the
  // sprites from the live snapshot rather than repaintChrome()'s cache,
  // which could hold Player's locally-toggled state from before the
  // switch.
  winampDisplay.setShuffleSink(nullptr);
  winampDisplay.setRepeatSink(nullptr);
  winampDisplay.setSeekSink(nullptr);
  spotifyTask::Snapshot snap;
  spotifyTask::copySnapshot(&snap);
  winampDisplay.drawVolume(snap.volumePercent);
  winampDisplay.drawShuffle(snap.shuffleState ? 1 : 0);
  winampDisplay.drawRepeat((int)snap.repeatState);
}

void SpotifyApp::tick() {
  {
    static unsigned long _lastScrollMs = 0;
    unsigned long now = millis();
    float dt = (_lastScrollMs == 0) ? 0.0f : (now - _lastScrollMs) * 0.001f;
    _lastScrollMs = now;
    winampDisplay.tickScroll(dt);
  }
  {
    // TASK-350: vu::tick() no longer reads spotifyTask state internally —
    // read the snapshot here at the Spotify call site, byte-identical to
    // the old inline behaviour.
    spotifyTask::Snapshot snap;
    spotifyTask::copySnapshot(&snap);
    const bool playing = snap.valid && snap.isPlaying && songStartMillis != 0;
    const long elapsed = playing ? (long)(millis() - (unsigned long)songStartMillis) : 0L;
    vu::tick(winampDisplay.chromeOriginX(), winampDisplay.chromeOriginY(), SKIN_MAIN_BG,
             playing, elapsed);
  }
  winampDisplay.drawPlaylist();
#ifdef NFC_ENABLED
  if (writeContextToNfc) {
    nfcLoop(lastTrackUri, lastTrackContextUri);
  } else {
    nfcLoop(lastTrackUri);
  }
#endif
  { unsigned long _t = millis(); updateCurrentlyPlaying(false);
    perf::record("spotify.poll", millis() - _t); }
  { unsigned long _t = millis(); updateProgressBar();
    perf::record("display.bar", millis() - _t); }
}

bool SpotifyApp::handleInput(TouchPhase phase, int x, int y) {
  // TASK-414 / ADR-059 D6: eject is freed from "switch to WebRadio" (the
  // taskbar player-slot cycle from TASK-413 owns app switching now) and
  // becomes "load media from this source" — same TLS-reset + force-poll
  // reconnect as the Winamp logo tap (TASK-053f), via the shared
  // tryReconnect() (winampDisplay.h) so both affordances share one
  // cooldown. Duplicating the affordance is harmless; silently deleting a
  // recovery path is not, so the logo tap keeps its own behaviour
  // unchanged.
  if (phase == TouchPhase::Release && winampDisplay.hitTestEject(x, y)) {
      if (winampDisplay.tryReconnect()) {
        LOG_I("touch", "eject tap → TLS reset + force poll");
      }
      return true;
  }
  return winampDisplay.handleWinampInput(phase, x, y);
}
