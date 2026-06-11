#include "logDecode.h"
#include "logHeartbeat.h"
#include "logSink.h"
#include "spotifyTask.h"
#include <esp_log.h>

SpotifyDisplay *sp_Display;

SpotifyArduino spotify(client, NULL, NULL);

bool albumArtChanged = false;

long songStartMillis;
long songDuration;
uint32_t g_lastRenderMs = 0;  // TASK-059: millis() of last snapshot-driven WinampDisplay repaint

char lastTrackUri[200];
char lastTrackContextUri[200];

// You might want to make this much smaller, so it will update responsively

// 031d: poll cadence + backoff moved into spotifyTask. The previous
// loop-side globals (delayBetweenRequests, requestDueTime,
// consecutiveSpotifyFailures, BACKOFF_MAX_MS) are gone — the task owns
// them all and the loop never gates on them anymore.

// poll-002: 100ms tick → ~3px/tick on a 280px bar at typical track length.
// Renderer is idempotent (no-op when pixel position unchanged), so a fast
// tick doesn't spam SPI writes.
unsigned long delayBetweenProgressUpdates = 100;
unsigned long progressDueTime;                   // time when request due

void spotifySetup(SpotifyDisplay *theDisplay, const char *clientId, const char *clientSecret)
{
  sp_Display = theDisplay;
  client.setCACert(spotify_server_cert);
  spotify.lateInit(clientId, clientSecret);

  lastTrackUri[0] = '\0';
  lastTrackContextUri[0] = '\0';
}

bool isSameTrack(const char *trackUri)
{

  return strcmp(lastTrackUri, trackUri) == 0;
}

void setTrackUri(const char *trackUri)
{
  strcpy(lastTrackUri, trackUri);
}

void setTrackContextUri(const char *trackContext)
{
  if (trackContext == NULL)
  {
    lastTrackContextUri[0] = '\0';
  }
  else
  {
    strcpy(lastTrackContextUri, trackContext);
  }
}

void spotifyRefreshToken(const char *refreshToken)
{
  spotify.setRefreshToken(refreshToken);

  // If you want to enable some extra debugging
  // uncomment the "#define SPOTIFY_DEBUG" in SpotifyArduino.h

  Serial.println("Refreshing Access Tokens");
  if (!spotify.refreshAccessToken())
  {
    Serial.println("Failed to get access tokens");
  }
}

void handleCurrentlyPlaying(CurrentlyPlaying currentlyPlaying)
{
  if (currentlyPlaying.trackUri != NULL)
  {
    if (!isSameTrack(currentlyPlaying.trackUri))
    {
      setTrackUri(currentlyPlaying.trackUri);
      setTrackContextUri(currentlyPlaying.contextUri);

      // We have a new Song, need to update the text
      sp_Display->printCurrentlyPlayingToScreen(currentlyPlaying);
    }

    albumArtChanged = sp_Display->processImageInfo(currentlyPlaying);

    // Re-anchor on every poll. Renderer is idempotent (poll-002), so this is
    // free when interpolation already painted the same pixel; on pause it's
    // the only thing keeping the bar accurate since updateProgressBar idles.
    sp_Display->displayTrackProgress(currentlyPlaying.progressMs, currentlyPlaying.durationMs);

    if (currentlyPlaying.isPlaying)
    {
      // If we know at what millis the song started at, we can make a good guess
      // at updating the progress bar more often than checking the API
      songStartMillis = millis() - currentlyPlaying.progressMs;
      songDuration = currentlyPlaying.durationMs;
    }
    else
    {
      // Song doesn't seem to be playing, do not update the progress
      songStartMillis = 0;
    }
  }
}

void updateProgressBar()
{
  if (songStartMillis != 0 && millis() > progressDueTime)
  {
    long songProgress = millis() - songStartMillis;
    if (songProgress > songDuration)
    {
      songProgress = songDuration;
    }
    sp_Display->displayTrackProgress(songProgress, songDuration);
    progressDueTime = millis() + delayBetweenProgressUpdates;
  }
}

void updateCurrentlyPlaying(boolean forceUpdate)
{
  // 031b: poll happens on the spotifyTask. This function is now a
  // snapshot reader: read the latest snapshot, render only when the
  // sequence counter advances. forceUpdate enqueues a FORCE_POLL.
  if (forceUpdate) {
    spotifyTask::enqueue(spotifyTask::ACT_FORCE_POLL);
  }

  static uint32_t lastRenderedSeq = 0;
  spotifyTask::Snapshot snap;
  spotifyTask::copySnapshot(&snap);
  if (!snap.valid || snap.seq == lastRenderedSeq) return;
  lastRenderedSeq = snap.seq;

  // TASK-041 / ADR-014 A1.1 — VOLUME slider. Cache lives on the display
  // (private member); we dedup here to skip the SPI traffic when the
  // value hasn't changed. Crucially this runs BEFORE the empty-track
  // and isSameTrack early-returns below — volume can change while the
  // track stays the same (or while no track is loaded yet).
  //
  // TASK-045 / ADR-016 §10 — gate on the display's optimistic-volume
  // window. While dragging or for ~2 s after, the user's chosen value
  // is authoritative; suppressing this avoids the slider snapping back
  // to a stale snap.volumePercent before Spotify commits the drag.
  if (millis() >= sp_Display->getOptimisticVolumeUntil() &&
      snap.volumePercent != sp_Display->getLastVolumeRendered()) {
    sp_Display->drawVolume(snap.volumePercent);
  }

  // chrome-001 final — shuffle / repeat. Same dedup + optimistic-freeze
  // shape as VOLUME. Runs before the empty-track early-return because
  // shuffle/repeat are independent of which track (or whether any) is
  // playing.
  if (millis() >= sp_Display->getOptimisticShufRepUntil()) {
    int8_t snapShuffle = snap.shuffleState ? 1 : 0;
    if (snapShuffle != sp_Display->getLastShuffleRendered()) {
      sp_Display->drawShuffle(snapShuffle);
    }
    if (snap.repeatState != sp_Display->getLastRepeatRendered()) {
      sp_Display->drawRepeat((int)snap.repeatState);
    }
  }

  if (snap.trackUri[0] == '\0') {
    // 204 path — no track. Make sure the lastTrackUri tracking resets too,
    // so a subsequent track shows up as "changed".
    if (lastTrackUri[0] != '\0') {
      lastTrackUri[0] = '\0';
      lastTrackContextUri[0] = '\0';
    }
    return;
  }

  // Reconstruct minimal CurrentlyPlaying for the existing display API.
  // const char* fields point at the stable snapshot buffers (we hold a
  // local copy; the task is allowed to mutate g_snapshot under the lock
  // but that doesn't disturb our local).
  CurrentlyPlaying cp = {};
  cp.trackName  = snap.trackName;
  cp.albumName  = snap.albumName;
  cp.trackUri   = snap.trackUri;
  cp.numArtists = (snap.artistName[0] != '\0') ? 1 : 0;
  if (cp.numArtists > 0) cp.artists[0].artistName = snap.artistName;
  cp.isPlaying  = snap.isPlaying;
  cp.progressMs = snap.progressMs;
  cp.durationMs = snap.durationMs;

  if (!isSameTrack(snap.trackUri)) {
    setTrackUri(snap.trackUri);
    setTrackContextUri(nullptr);  // contextUri not currently in snapshot
    sp_Display->printCurrentlyPlayingToScreen(cp);
  }
  // Re-anchor visual progress on every poll so the bar+digits snap to
  // server-truth even when the user hasn't touched anything. The M4
  // interpolator (updateProgressBar) takes over between polls.
  sp_Display->displayTrackProgress(snap.progressMs, snap.durationMs);
  g_lastRenderMs = millis();  // TASK-059: mark snapshot-driven repaint time
}
