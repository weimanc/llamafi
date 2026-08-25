#pragma once
// apps/spotifyApp.h — SpotifyApp component (M-SRCLAYOUT Stage E / TASK-471).
// Self-contained per D0/SF.11 — method bodies live in spotifyApp.cpp.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <SpotifyArduino.h>   // winamp/winampDisplay.h's WinampDisplay needs this in scope (CurrentlyPlaying, SpotifyArduino*)
#include "appShell.h"
#include "winamp/winampDisplay.h"
#include "spotifyTask.h"
#include "spotifyLogic.h"   // songStartMillis, lastTrackUri/ContextUri, updateCurrentlyPlaying/ProgressBar
#include "perf.h"
#include "logSink.h"

#include "display/tft.h"
extern WinampDisplay winampDisplay;

class SpotifyApp : public App {
public:
  void init() override;
  void resume() override;
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
  // TASK-518 (P4): in-flight = spotifyTask::hasPendingActions(), i.e.
  // s_actionPending — set when enqueue() accepts a non-POLL action, cleared
  // when the action queue drains (spotifyTaskStorage.cpp:796 / :413). That is
  // exactly "a user-initiated operation is still running", and it self-clears
  // on both the success and the failure path because the clear is the queue
  // drain, not the HTTP result.
  //
  // isConnecting() was NOT reusable: it is spotifyTask::connecting() ==
  // (s_lastSuccessfulPollMs == 0), a never-had-data latch that only falls on
  // the FIRST 200/204. Under TASK-243 (owner Premium lapsed, sustained 403 —
  // still live on this rig) it never falls, so ORing it here would make the
  // device report never-quiet forever in Spotify mode.
  //
  // The background cadence POLL is deliberately excluded: it is not an
  // operation the caller asked for, and including it would leave a poll-every-
  // few-seconds app permanently non-idle. A poll actually in flight is still
  // visible to `get idle` through the dataq/spAct terms.
  bool hasInFlightOp() const override {
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
  void tick() override;
  bool handleInput(TouchPhase phase, int x, int y) override;
};
