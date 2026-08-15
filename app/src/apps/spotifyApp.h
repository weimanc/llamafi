#pragma once
// apps/spotifyApp.h — SpotifyApp, moved verbatim out of main.cpp (M-SRCLAYOUT).
// Pure move: no logic change, no reordering.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "winamp/winampDisplay.h"
#include "spotifyTask.h"

class SpotifyApp : public App {
public:
  void init() override {
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
  void resume() override {
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
  void suspend() override {
    winampDisplay.resetDragState();
  }
  // spotifyTask action queue is exclusively user-initiated (play/pause/next/prev/
  // volume/shuffle/repeat/seek) — hasPendingActions() true means a user tap is
  // still in flight. cmdTap also enqueues via injectTouch(), so this path covers
  // both production touches (via handleInput) and injected taps.
  bool hasPendingAsync() const override {
    return spotifyTask::hasPendingActions();
  }
  // TASK-245 / ADR-046: red taskbar bar on a persistent 403 (authorization
  // refused — e.g. owner-account Premium lapsed). Self-clears on the next
  // successful poll (see spotifyTask::authError()).
  // TASK-366: OR'd with degraded() (>=2 consecutive non-403 failures — network/
  // timeout/DNS) so a sustained non-auth poll problem also shows red, not just
  // 403s. Both are sticky latches owned by spotifyTask; this endpoint just ORs.
  bool hasError() const override {
    return spotifyTask::authError() || spotifyTask::degraded();
  }
  // TASK-245 amendment / ADR-046: amber "connecting" bar at boot until the first
  // poll resolves (then green on success, red on persistent 403).
  bool isConnecting() const override {
    return spotifyTask::connecting();
  }
  void tick() override {
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
  bool handleInput(TouchPhase phase, int x, int y) override {
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
};
