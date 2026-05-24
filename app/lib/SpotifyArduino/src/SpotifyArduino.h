/*
SpotifyArduino - An Arduino library to wrap the Spotify API

Copyright (c) 2020  Brian Lough.

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version 2.1 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this library; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA
*/

#ifndef SpotifyArduino_h
#define SpotifyArduino_h

// I find setting these types of flags unreliable from the Arduino IDE
// so uncomment this if its not working for you.
// NOTE: Do not use this option on live-streams, it will reveal your
// private tokens!

// LOCAL_PATCH (LL-003): disabled to stop the library from Serial.printing
// the refresh-token-grant POST body (refresh_token + client_secret) on every
// auth attempt. Re-enable only for short, controlled debug sessions on a
// non-shared device.
//#define SPOTIFY_DEBUG 1

// Comment out if you want to disable any serial output from this library (also comment out DEBUG and PRINT_JSON_PARSE)
#define SPOTIFY_SERIAL_OUTPUT 1

// Prints the JSON received to serial (only use for debugging as it will be slow)
//#define SPOTIFY_PRINT_JSON_PARSE 1

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Client.h>

#ifdef SPOTIFY_PRINT_JSON_PARSE
#include <StreamUtils.h>
#endif

#define SPOTIFY_HOST "api.spotify.com"
#define SPOTIFY_ACCOUNTS_HOST "accounts.spotify.com"

// Fingerprint for "*.spotify.com", correct as of March 14, 2024
#define SPOTIFY_FINGERPRINT "69 2B 36 29 F0 B5 FC 1B A3 57 A6 76 E6 92 EF 30 14 22 34 6A"

// Fingerprint for "*.scdn.co", correct as of March 14, 2024
#define SPOTIFY_IMAGE_SERVER_FINGERPRINT "0A 0F 59 45 2C FF 37 3C FE 37 27 AD 32 64 59 A9 5A B6 2F 30"

#define SPOTIFY_TIMEOUT 2000

#define SPOTIFY_NAME_CHAR_LENGTH 100 //Increase if artists/song/album names are being cut off
#define SPOTIFY_URI_CHAR_LENGTH 40
#define SPOTIFY_URL_CHAR_LENGTH 70

#define SPOTIFY_DEVICE_ID_CHAR_LENGTH 45
#define SPOTIFY_DEVICE_NAME_CHAR_LENGTH 80
#define SPOTIFY_DEVICE_TYPE_CHAR_LENGTH 30

// LOCAL_PATCHES (patch #8 / TASK-043 / ADR-015): query /me/player rather than
// /me/player/currently-playing. The latter does not include the `device` field
// in the actual server response (despite the OpenAPI spec saying both endpoints
// return CurrentlyPlayingContextObject). /me/player is a strict superset for
// every field this parser reads, including device.volume_percent — required by
// the M-CHROME tier 2 dynamic VOLUME slider. See LOCAL_PATCHES.md patch #8 and
// docs/quality/lessons_learned.md LL-018 for the wire-capture evidence.
#define SPOTIFY_CURRENTLY_PLAYING_ENDPOINT "/v1/me/player?additional_types=episode"

#define SPOTIFY_PLAYER_ENDPOINT "/v1/me/player"
#define SPOTIFY_DEVICES_ENDPOINT "/v1/me/player/devices"

#define SPOTIFY_PLAY_ENDPOINT "/v1/me/player/play"
#define SPOTIFY_SEARCH_ENDPOINT "/v1/search"
#define SPOTIFY_PAUSE_ENDPOINT "/v1/me/player/pause"
#define SPOTIFY_VOLUME_ENDPOINT "/v1/me/player/volume?volume_percent=%d"
#define SPOTIFY_SHUFFLE_ENDPOINT "/v1/me/player/shuffle?state=%s"
#define SPOTIFY_REPEAT_ENDPOINT "/v1/me/player/repeat?state=%s"

#define SPOTIFY_NEXT_TRACK_ENDPOINT "/v1/me/player/next"
#define SPOTIFY_PREVIOUS_TRACK_ENDPOINT "/v1/me/player/previous"

#define SPOTIFY_SEEK_ENDPOINT "/v1/me/player/seek"
// LOCAL_PATCHES (TASK-020b / ADR-017): queue endpoint for M-LIST playlist panel.
#define SPOTIFY_QUEUE_ENDPOINT "/v1/me/player/queue"
// LOCAL_PATCHES (TASK-047b): reduced from 7 to 5; TASK-051b: raised to 20 for scroll.
#define SPOTIFY_QUEUE_MAX_ITEMS 20

#define SPOTIFY_TOKEN_ENDPOINT "/api/token"

#define SPOTIFY_NUM_ALBUM_IMAGES 3 // Max spotify returns is 3, but the third one is probably too big for an ESP

#define SPOTIFY_MAX_NUM_ARTISTS 5

#define SPOTIFY_ACCESS_TOKEN_LENGTH 309

enum RepeatOptions
{
  repeat_track,
  repeat_context,
  repeat_off
};

enum SpotifyPlayingType
{
  track,
  episode,
  other
};

struct SpotifyImage
{
  int height;
  int width;
  const char *url;
};

struct SpotifyDevice
{
  const char *id;
  const char *name;
  const char *type;
  bool isActive;
  bool isRestricted;
  bool isPrivateSession;
  int volumePercent;
};

struct PlayerDetails
{
  SpotifyDevice device;

  long progressMs;
  bool isPlaying;
  RepeatOptions repeateState;
  bool shuffleState;
};

struct SpotifyArtist
{
  const char *artistName;
  const char *artistUri;
};

struct SearchResult
{
  const char *albumName;
  const char *albumUri;
  const char *trackName;
  const char *trackUri;
  SpotifyArtist artists[SPOTIFY_MAX_NUM_ARTISTS];
  SpotifyImage albumImages[SPOTIFY_NUM_ALBUM_IMAGES];
  int numArtists;
  int numImages;
};

struct CurrentlyPlaying
{
  SpotifyArtist artists[SPOTIFY_MAX_NUM_ARTISTS];
  int numArtists;
  const char *albumName;
  const char *albumUri;
  const char *trackName;
  const char *trackUri;
  SpotifyImage albumImages[SPOTIFY_NUM_ALBUM_IMAGES];
  int numImages;
  bool isPlaying;
  long progressMs;
  long durationMs;
  const char *contextUri;
  SpotifyPlayingType currentlyPlayingType;
  // LOCAL_PATCHES (TASK-039): device volume from the same response. -1 if
  // no active device or field missing. 0..100 otherwise.
  int volumePercent;
  // LOCAL_PATCHES patch #9 (M-CHROME chrome-001 final): surface shuffle +
  // repeat from the same /me/player response so the renderer can drive the
  // SHUFREP indicators without a second endpoint.
  bool shuffleState;
  RepeatOptions repeatState;
};

typedef void (*processCurrentlyPlaying)(CurrentlyPlaying currentlyPlaying);
typedef void (*processPlayerDetails)(PlayerDetails playerDetails);
typedef bool (*processDevices)(SpotifyDevice device, int index, int numDevices);
typedef bool (*processSearch)(SearchResult result, int index, int numResults);

// LOCAL_PATCHES (TASK-020b / ADR-017): queue snapshot for M-LIST playlist panel.
// [0] = currently_playing, [1..SPOTIFY_QUEUE_MAX_ITEMS-1] = next-up queue.
// const char* pointers are valid only inside the processQueue callback — copy them.
struct QueueItem {
  const char *name;
  const char *artistName;
  const char *uri;
  long        durationMs;  // LOCAL_PATCHES (TASK-047b)
};
struct QueueData {
  QueueItem items[SPOTIFY_QUEUE_MAX_ITEMS];
  uint8_t   count;  // valid items in items[] (0 if nothing playing)
};
typedef void (*processQueue)(QueueData &data);

class SpotifyArduino
{
public:
  SpotifyArduino(Client &client);
  SpotifyArduino(Client &client, char *bearerToken);
  SpotifyArduino(Client &client, const char *clientId, const char *clientSecret, const char *refreshToken = "");

  // Auth Methods
  void setRefreshToken(const char *refreshToken);
  bool refreshAccessToken();
  bool checkAndRefreshAccessToken();
  const char *requestAccessTokens(const char *code, const char *redirectUrl);

  // Generic Request Methods
  int makeGetRequest(const char *command, const char *authorization, const char *accept = "application/json", const char *host = SPOTIFY_HOST);
  int makeRequestWithBody(const char *type, const char *command, const char *authorization, const char *body = "", const char *contentType = "application/json", const char *host = SPOTIFY_HOST);
  int makePostRequest(const char *command, const char *authorization, const char *body = "", const char *contentType = "application/json", const char *host = SPOTIFY_HOST);
  int makePutRequest(const char *command, const char *authorization, const char *body = "", const char *contentType = "application/json", const char *host = SPOTIFY_HOST);

  // User methods
  int getCurrentlyPlaying(processCurrentlyPlaying currentlyPlayingCallback, const char *market = "");
  // LOCAL_PATCHES (TASK-020b / ADR-017): fetch /v1/me/player/queue.
  int getQueue(processQueue queueCallback);
  int getPlayerDetails(processPlayerDetails playerDetailsCallback, const char *market = "");
  int getDevices(processDevices devicesCallback);
  bool play(const char *deviceId = "");
  bool playAdvanced(char *body, const char *deviceId = "");
  bool pause(const char *deviceId = "");
  bool setVolume(int volume, const char *deviceId = "");
  bool toggleShuffle(bool shuffle, const char *deviceId = "");
  bool setRepeatMode(RepeatOptions repeat, const char *deviceId = "");
  bool nextTrack(const char *deviceId = "");
  bool previousTrack(const char *deviceId = "");
  bool playerControl(char *command, const char *deviceId = "", const char *body = "");
  bool playerNavigate(char *command, const char *deviceId = "");
  bool seek(int position, const char *deviceId = "");
  bool transferPlayback(const char *deviceId, bool play = false);

  //Search
  int searchForSong(String query, int limit, processSearch searchCallback, SearchResult results[]);

  // Image methods
  bool getImage(char *imageUrl, Stream *file);
  bool getImage(char *imageUrl, uint8_t **image, int *imageLength);

  int portNumber = 443;
  int currentlyPlayingBufferSize = 3000;
  int queueBufferSize = 10240;  // TASK-051b: bumped from 6000 for 20 filtered items
  int playerDetailsBufferSize = 2000;
  int getDevicesBufferSize = 3000;
  int searchDetailsBufferSize = 3000;
  bool autoTokenRefresh = true;
  Client *client;
  void lateInit(const char *clientId, const char *clientSecret, const char *refreshToken = "");

  // Local patch (LOCAL_PATCHES.md): expose the formatted "Bearer <token>" string
  // so the M1 spike can drive endpoints not covered by this library
  // (audio-features, audio-analysis) via the public makeGetRequest() / client.
  const char *getBearerToken() const { return _bearerToken; }

#ifdef SPOTIFY_DEBUG
  char *stack_start;
#endif

private:
  char _bearerToken[SPOTIFY_ACCESS_TOKEN_LENGTH + 10]; //10 extra is for "bearer " at the start
  char *_refreshToken;
  const char *_clientId;
  const char *_clientSecret;
  unsigned int timeTokenRefreshed;
  unsigned int tokenTimeToLiveMs;
  int commonGetImage(char *imageUrl);
  int getContentLength();
  int getHttpStatusCode();
  struct HeaderInfo { int contentLength; bool chunked; };
  HeaderInfo skipHeaders();
  void drainBody();
  void closeClient();
  void parseError(int contentLength = -1);
  bool _chunkedResponse = false;
  char _connectedHost[64] = {};
  const char *requestAccessTokensBody =
      R"(grant_type=authorization_code&code=%s&redirect_uri=%s&client_id=%s&client_secret=%s)";
  const char *refreshAccessTokensBody =
      R"(grant_type=refresh_token&refresh_token=%s&client_id=%s&client_secret=%s)";
#ifdef SPOTIFY_DEBUG
  void printStack();
#endif
};

#endif
