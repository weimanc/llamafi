#ifndef SPIKE_MODE_H
#define SPIKE_MODE_H

// M1 spike harness (api-001). Throwaway code: enabled only when -DSPIKE_MODE.
// Reads single-character commands from Serial, fires one Spotify Web API call
// per command, logs [OK]/[FAIL]/[GET]/[ERR] results so a per-row pass/fail
// table can be filled in tasks.md. See docs/verification/test_plan.md.

#include <Arduino.h>
#include <SpotifyArduino.h>
#include <time.h>
#include "spikeRawHttp.h"

// From spotifyLogic.h — track URI captured by the existing poll loop.
extern char lastTrackUri[200];

namespace spike {

static SpotifyArduino *s_spotify = nullptr;
static bool s_assumedPlaying = true;   // toggled by space; explicit p/P also update
static int  s_volume = 50;             // local mirror; +/- adjust by 10

// ---- helpers --------------------------------------------------------------

inline bool extractTrackId(char *out, size_t outLen) {
  // lastTrackUri is "spotify:track:<22-char-id>"; copy id portion.
  const char *prefix = "spotify:track:";
  size_t plen = strlen(prefix);
  if (strncmp(lastTrackUri, prefix, plen) != 0) return false;
  strncpy(out, lastTrackUri + plen, outLen - 1);
  out[outLen - 1] = '\0';
  return out[0] != '\0';
}

inline void logBool(char key, const char *action, bool ok) {
  Serial.printf("[%s]  %c %s\n", ok ? "OK " : "FAIL", key, action);
}

inline void printHelp() {
  Serial.println(F("\n=== spike harness commands (api-001) ==="));
  Serial.println(F("  ?       help"));
  Serial.println(F("  i       info: heap, last track id, assumed playing"));
  Serial.println(F("  >       next track"));
  Serial.println(F("  <       previous track"));
  Serial.println(F("  space   toggle play/pause (assumed state)"));
  Serial.println(F("  p / P   force play / force pause"));
  Serial.println(F("  s       seek to 30s"));
  Serial.println(F("  S       seek to 0"));
  Serial.println(F("  + / -   volume +10 / -10 (clamped 0-100)"));
  Serial.println(F("  v       set volume to 50"));
  Serial.println(F("  h / H   shuffle on / off"));
  Serial.println(F("  r       repeat: track"));
  Serial.println(F("  R       repeat: context"));
  Serial.println(F("  o       repeat: off"));
  Serial.println(F("  f       audio-features for last-known track"));
  Serial.println(F("  a       audio-analysis for last-known track (16K filter)"));
  Serial.println(F("  A       audio-analysis (32K filter, fallback)"));
  Serial.println(F("=========================================\n"));
}

inline void printInfo() {
  char id[40] = "(none)";
  extractTrackId(id, sizeof(id));
  Serial.printf("[INFO] heap=%u track=%s playing(assumed)=%d vol(local)=%d\n",
                ESP.getFreeHeap(), id, (int)s_assumedPlaying, s_volume);

  // time-001: surface system clock so T019/T020 can verify NTP sync.
  time_t now = time(nullptr);
  char buf[32] = "(unset)";
  struct tm tmUtc;
  if (gmtime_r(&now, &tmUtc) != nullptr) {
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tmUtc);
  }
  Serial.printf("[INFO] time epoch=%ld utc=%s sane=%d\n",
                (long)now, buf, now >= 1700000000L ? 1 : 0);
}

// ---- dispatch -------------------------------------------------------------

inline void dispatch(char key) {
  if (!s_spotify) return;
  char id[40];

  switch (key) {
    case '?': printHelp(); break;
    case 'i': printInfo(); break;

    case '>': logBool(key, "nextTrack",     s_spotify->nextTrack());     break;
    case '<': logBool(key, "previousTrack", s_spotify->previousTrack()); break;

    case ' ':
      if (s_assumedPlaying) {
        bool ok = s_spotify->pause();
        logBool(key, "pause (toggle)", ok);
        if (ok) s_assumedPlaying = false;
      } else {
        bool ok = s_spotify->play();
        logBool(key, "play (toggle)", ok);
        if (ok) s_assumedPlaying = true;
      }
      break;
    case 'p': {
      bool ok = s_spotify->play();
      logBool(key, "play", ok);
      if (ok) s_assumedPlaying = true;
      break;
    }
    case 'P': {
      bool ok = s_spotify->pause();
      logBool(key, "pause", ok);
      if (ok) s_assumedPlaying = false;
      break;
    }

    case 's': logBool(key, "seek 30000", s_spotify->seek(30000)); break;
    case 'S': logBool(key, "seek 0",     s_spotify->seek(0));     break;

    case '+':
      s_volume = min(100, s_volume + 10);
      logBool(key, "setVolume +10", s_spotify->setVolume(s_volume));
      Serial.printf("       (vol=%d)\n", s_volume);
      break;
    case '-':
      s_volume = max(0, s_volume - 10);
      logBool(key, "setVolume -10", s_spotify->setVolume(s_volume));
      Serial.printf("       (vol=%d)\n", s_volume);
      break;
    case 'v':
      s_volume = 50;
      logBool(key, "setVolume 50", s_spotify->setVolume(50));
      break;

    case 'h': logBool(key, "shuffle on",  s_spotify->toggleShuffle(true));  break;
    case 'H': logBool(key, "shuffle off", s_spotify->toggleShuffle(false)); break;

    case 'r': logBool(key, "repeat track",   s_spotify->setRepeatMode(repeat_track));   break;
    case 'R': logBool(key, "repeat context", s_spotify->setRepeatMode(repeat_context)); break;
    case 'o': logBool(key, "repeat off",     s_spotify->setRepeatMode(repeat_off));     break;

    case 'f':
      if (!extractTrackId(id, sizeof(id))) {
        Serial.println(F("[SKIP] f: no track URI yet (start playback first)"));
        break;
      }
      audioFeatures(s_spotify, id);
      break;
    case 'a':
      if (!extractTrackId(id, sizeof(id))) {
        Serial.println(F("[SKIP] a: no track URI yet (start playback first)"));
        break;
      }
      audioAnalysis(s_spotify, id, 16384);
      break;
    case 'A':
      if (!extractTrackId(id, sizeof(id))) {
        Serial.println(F("[SKIP] A: no track URI yet (start playback first)"));
        break;
      }
      audioAnalysis(s_spotify, id, 32768);
      break;

    case '\r':
    case '\n':
      break;  // ignore line endings

    default:
      Serial.printf("[?]    unknown key '%c' (0x%02x); send '?' for help\n", key, key);
      break;
  }
}

// ---- public api -----------------------------------------------------------

inline void setup(SpotifyArduino *spotifyObj) {
  s_spotify = spotifyObj;
  Serial.println(F("\n[spike] M1 API capability spike enabled (api-001)"));
  printHelp();
}

inline void loop() {
  while (Serial.available() > 0) {
    int c = Serial.read();
    if (c < 0) break;
    dispatch((char)c);
  }
}

}  // namespace spike

#endif  // SPIKE_MODE_H
