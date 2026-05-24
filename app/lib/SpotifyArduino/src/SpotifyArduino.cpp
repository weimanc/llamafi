/*
SpotifyArduino - An Arduino library to wrap the Spotify API

Copyright (c) 2021  Brian Lough.

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

#include "SpotifyArduino.h"

// LOCAL_PATCHES: capture errno on connect failure (TASK-018 follow-up).
#include <errno.h>
#include <string.h>

SpotifyArduino::SpotifyArduino(Client &client)
{
    this->client = &client;
}

SpotifyArduino::SpotifyArduino(Client &client, char *bearerToken)
{
    this->client = &client;
    sprintf(this->_bearerToken, "Bearer %s", bearerToken);
}

SpotifyArduino::SpotifyArduino(Client &client, const char *clientId, const char *clientSecret, const char *refreshToken)
{
    this->client = &client;
    this->_clientId = clientId;
    this->_clientSecret = clientSecret;
    setRefreshToken(refreshToken);
}

int SpotifyArduino::makeRequestWithBody(const char *type, const char *command, const char *authorization, const char *body, const char *contentType, const char *host)
{
    // INV-A Step 3: HTTP/1.1 keep-alive. Reconnect only when host changes or
    // connection dropped. Retry once on stale keep-alive write failure.
    client->setTimeout(SPOTIFY_TIMEOUT);

    for (int attempt = 0; attempt < 2; attempt++)
    {
        bool hostMatches = (strcmp(_connectedHost, host) == 0);
        if (!client->connected() || !hostMatches)
        {
            client->stop();
            _connectedHost[0] = '\0';
            delay(200);  // give lwIP time to release fd before next connect()
            if (!client->connect(host, portNumber))
            {
                int e = errno;
                Serial.printf("[lib] %s connect %s:%d failed errno=%d (%s)\n",
                              type, host, portNumber, e, strerror(e));
                return -1;
            }
            strncpy(_connectedHost, host, sizeof(_connectedHost) - 1);
            _connectedHost[sizeof(_connectedHost) - 1] = '\0';
        }

#ifdef SPOTIFY_DEBUG
        Serial.println(host);
#endif

        yield();

        client->print(type);
        client->print(command);
        client->println(F(" HTTP/1.1"));

        client->print(F("Host: "));
        client->println(host);

        client->println(F("Accept: application/json"));

        // LOCAL_PATCHES (2026-05-08): Content-Type / Content-Length are only
        // emitted when there's an actual body. Spotify's empty-body player
        // endpoints (next/previous/pause/seek/volume/shuffle/repeat) reject
        // (or silently close) requests that declare Content-Type: application
        // /json with Content-Length: 0 — which is the upstream lib's default
        // shape for those calls.
        bool hasBody = (body != NULL && body[0] != '\0');
        if (hasBody)
        {
            client->print(F("Content-Type: "));
            client->println(contentType);
        }

        if (authorization != NULL)
        {
            client->print(F("Authorization: "));
            client->println(authorization);
        }

        client->println(F("Connection: keep-alive"));
        client->println(F("Cache-Control: no-cache"));

        // LOCAL_PATCHES (2026-05-08): Content-Length required even for empty
        // bodies (411 otherwise). Content-Type stays gated on hasBody.
        client->print(F("Content-Length: "));
        client->println(strlen(body));

        // Detect stale keep-alive on the blank line (end of headers).
        if (client->println() == 0)
        {
#ifdef SPOTIFY_SERIAL_OUTPUT
            Serial.printf("[lib] %s header write fail, retrying\n", type);
#endif
            client->stop();
            _connectedHost[0] = '\0';
            delay(200);
            continue;
        }

        if (hasBody)
        {
            if (client->print(body) == 0)
            {
#ifdef SPOTIFY_SERIAL_OUTPUT
                Serial.printf("[lib] %s body write fail, retrying\n", type);
#endif
                client->stop();
                _connectedHost[0] = '\0';
                delay(200);
                continue;
            }
        }

        int statusCode = getHttpStatusCode();
        Serial.printf("[lib] %s%s -> %d\n", type, command, statusCode);
        return statusCode;
    }

#ifdef SPOTIFY_SERIAL_OUTPUT
    Serial.printf("[lib] %s%s failed after retry\n", type, command);
#endif
    return -1;
}

int SpotifyArduino::makePutRequest(const char *command, const char *authorization, const char *body, const char *contentType, const char *host)
{
    return makeRequestWithBody("PUT ", command, authorization, body, contentType);
}

int SpotifyArduino::makePostRequest(const char *command, const char *authorization, const char *body, const char *contentType, const char *host)
{
    return makeRequestWithBody("POST ", command, authorization, body, contentType, host);
}

int SpotifyArduino::makeGetRequest(const char *command, const char *authorization, const char *accept, const char *host)
{
    // INV-A Step 3: HTTP/1.1 keep-alive. Reconnect only when host changes or
    // connection dropped. Retry once on stale keep-alive write failure.
    client->setTimeout(SPOTIFY_TIMEOUT);

    for (int attempt = 0; attempt < 2; attempt++)
    {
        bool hostMatches = (strcmp(_connectedHost, host) == 0);
        if (!client->connected() || !hostMatches)
        {
            client->stop();
            _connectedHost[0] = '\0';
            delay(200);  // give lwIP time to release fd before next connect()
            if (!client->connect(host, portNumber))
            {
                int e = errno;
                Serial.printf("[lib] GET connect %s:%d failed errno=%d (%s)\n",
                              host, portNumber, e, strerror(e));
                return -1;
            }
            strncpy(_connectedHost, host, sizeof(_connectedHost) - 1);
            _connectedHost[sizeof(_connectedHost) - 1] = '\0';
        }

        yield();

        client->print(F("GET "));
        client->print(command);
        client->println(F(" HTTP/1.1"));

        client->print(F("Host: "));
        client->println(host);

        if (accept != NULL)
        {
            client->print(F("Accept: "));
            client->println(accept);
        }

        if (authorization != NULL)
        {
            client->print(F("Authorization: "));
            client->println(authorization);
        }

        client->println(F("Connection: keep-alive"));
        client->println(F("Cache-Control: no-cache"));

        if (client->println() != 0)
        {
            return getHttpStatusCode();
        }

        // Blank-line write failed — stale keep-alive connection.
#ifdef SPOTIFY_SERIAL_OUTPUT
        Serial.println(F("[lib] GET write fail, retrying"));
#endif
        client->stop();
        _connectedHost[0] = '\0';
        delay(200);
    }

#ifdef SPOTIFY_SERIAL_OUTPUT
    Serial.println(F("[lib] GET failed after retry"));
#endif
    return -1;
}

void SpotifyArduino::setRefreshToken(const char *refreshToken)
{
    int newRefreshTokenLen = strlen(refreshToken);
    if (_refreshToken == NULL || strlen(_refreshToken) < newRefreshTokenLen)
    {
        delete _refreshToken;
        _refreshToken = new char[newRefreshTokenLen + 1]();
    }

    strncpy(_refreshToken, refreshToken, newRefreshTokenLen + 1);
}

bool SpotifyArduino::refreshAccessToken()
{
    char body[300];
    sprintf(body, refreshAccessTokensBody, _refreshToken, _clientId, _clientSecret);

#ifdef SPOTIFY_DEBUG
    Serial.println(body);
    printStack();
#endif

    int statusCode = makePostRequest(SPOTIFY_TOKEN_ENDPOINT, NULL, body, "application/x-www-form-urlencoded", SPOTIFY_ACCOUNTS_HOST);
    HeaderInfo hdr = { -1, false };
    if (statusCode > 0)
    {
        hdr = skipHeaders();
    }
    unsigned long now = millis();

#ifdef SPOTIFY_DEBUG
    Serial.print("status Code");
    Serial.println(statusCode);
#endif

    bool refreshed = false;
    if (statusCode == 200)
    {
        StaticJsonDocument<48> filter;
        filter["access_token"] = true;
        filter["token_type"] = true;
        filter["expires_in"] = true;

        DynamicJsonDocument doc(512);

        char *bodyBuf = (hdr.contentLength > 0) ? (char *)malloc(hdr.contentLength + 1) : NULL;
        if (!bodyBuf)
        {
            _chunkedResponse = true;  // force close — can't parse without body length
        }
        else
        {
            client->setTimeout(3000);
            size_t bodyLen = client->readBytes(bodyBuf, (size_t)hdr.contentLength);
            client->setTimeout(SPOTIFY_TIMEOUT);
            bodyBuf[bodyLen] = '\0';

#ifndef SPOTIFY_PRINT_JSON_PARSE
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#else
            Serial.write((const uint8_t *)bodyBuf, bodyLen);
            Serial.println();
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#endif
            free(bodyBuf);
            if (!error)
            {
#ifdef SPOTIFY_DEBUG
                Serial.println(F("No JSON error, dealing with response"));
#endif
                const char *accessToken = doc["access_token"].as<const char *>();
                if (accessToken != NULL && (SPOTIFY_ACCESS_TOKEN_LENGTH >= strlen(accessToken)))
                {
                    sprintf(this->_bearerToken, "Bearer %s", accessToken);
                    int tokenTtl = doc["expires_in"];             // Usually 3600 (1 hour)
                    tokenTimeToLiveMs = (tokenTtl * 1000) - 2000; // The 2000 is just to force the token expiry to check if its very close
                    timeTokenRefreshed = now;
                    refreshed = true;
                }
                else
                {
#ifdef SPOTIFY_SERIAL_OUTPUT
                    Serial.print(F("Problem with access_token (too long or null): "));
                    Serial.println(accessToken);
#endif
                }
            }
            else
            {
#ifdef SPOTIFY_SERIAL_OUTPUT
                Serial.print(F("deserializeJson() failed with code "));
                Serial.println(error.c_str());
#endif
            }
        }
    }
    else
    {
        parseError(hdr.contentLength);
    }

    closeClient();
    return refreshed;
}

bool SpotifyArduino::checkAndRefreshAccessToken()
{
    unsigned long timeSinceLastRefresh = millis() - timeTokenRefreshed;
    if (timeSinceLastRefresh >= tokenTimeToLiveMs)
    {
#ifdef SPOTIFY_SERIAL_OUTPUT
        Serial.println("Refresh of the Access token is due, doing that now.");
#endif
        return refreshAccessToken();
    }

    // Token is still valid
    return true;
}

const char *SpotifyArduino::requestAccessTokens(const char *code, const char *redirectUrl)
{

    char body[500];
    sprintf(body, requestAccessTokensBody, code, redirectUrl, _clientId, _clientSecret);

#ifdef SPOTIFY_DEBUG
    Serial.println(body);
#endif

    int statusCode = makePostRequest(SPOTIFY_TOKEN_ENDPOINT, NULL, body, "application/x-www-form-urlencoded", SPOTIFY_ACCOUNTS_HOST);
    HeaderInfo hdr = { -1, false };
    if (statusCode > 0)
    {
        hdr = skipHeaders();
    }
    unsigned long now = millis();

#ifdef SPOTIFY_DEBUG
    Serial.print("status Code");
    Serial.println(statusCode);
#endif

    if (statusCode == 200)
    {
        DynamicJsonDocument doc(1000);

        char *bodyBuf = (hdr.contentLength > 0) ? (char *)malloc(hdr.contentLength + 1) : NULL;
        if (!bodyBuf)
        {
            _chunkedResponse = true;
        }
        else
        {
            client->setTimeout(3000);
            size_t bodyLen = client->readBytes(bodyBuf, (size_t)hdr.contentLength);
            client->setTimeout(SPOTIFY_TIMEOUT);
            bodyBuf[bodyLen] = '\0';

#ifndef SPOTIFY_PRINT_JSON_PARSE
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen);
#else
            Serial.write((const uint8_t *)bodyBuf, bodyLen);
            Serial.println();
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen);
#endif
            free(bodyBuf);
            if (!error)
            {
                sprintf(this->_bearerToken, "Bearer %s", doc["access_token"].as<const char *>());
                setRefreshToken(doc["refresh_token"].as<const char *>());
                int tokenTtl = doc["expires_in"];             // Usually 3600 (1 hour)
                tokenTimeToLiveMs = (tokenTtl * 1000) - 2000; // The 2000 is just to force the token expiry to check if its very close
                timeTokenRefreshed = now;
            }
            else
            {
#ifdef SPOTIFY_SERIAL_OUTPUT
                Serial.print(F("deserializeJson() failed with code "));
                Serial.println(error.c_str());
#endif
            }
        }
    }
    else
    {
        parseError(hdr.contentLength);
    }

    closeClient();
    return _refreshToken;
}

bool SpotifyArduino::play(const char *deviceId)
{
    char command[100] = SPOTIFY_PLAY_ENDPOINT;
    return playerControl(command, deviceId);
}

bool SpotifyArduino::playAdvanced(char *body, const char *deviceId)
{
    char command[100] = SPOTIFY_PLAY_ENDPOINT;
    return playerControl(command, deviceId, body);
}

bool SpotifyArduino::pause(const char *deviceId)
{
    char command[100] = SPOTIFY_PAUSE_ENDPOINT;
    return playerControl(command, deviceId);
}

bool SpotifyArduino::setVolume(int volume, const char *deviceId)
{
    char command[125];
    sprintf(command, SPOTIFY_VOLUME_ENDPOINT, volume);
    return playerControl(command, deviceId);
}

bool SpotifyArduino::toggleShuffle(bool shuffle, const char *deviceId)
{
    char command[125];
    char shuffleState[10];
    if (shuffle)
    {
        strcpy(shuffleState, "true");
    }
    else
    {
        strcpy(shuffleState, "false");
    }
    sprintf(command, SPOTIFY_SHUFFLE_ENDPOINT, shuffleState);
    return playerControl(command, deviceId);
}

bool SpotifyArduino::setRepeatMode(RepeatOptions repeat, const char *deviceId)
{
    char command[125];
    char repeatState[10];
    switch (repeat)
    {
    case repeat_track:
        strcpy(repeatState, "track");
        break;
    case repeat_context:
        strcpy(repeatState, "context");
        break;
    case repeat_off:
        strcpy(repeatState, "off");
        break;
    }

    sprintf(command, SPOTIFY_REPEAT_ENDPOINT, repeatState);
    return playerControl(command, deviceId);
}

bool SpotifyArduino::playerControl(char *command, const char *deviceId, const char *body)
{
    if (deviceId[0] != 0)
    {
        char *questionMarkPointer;
        questionMarkPointer = strchr(command, '?');
        char deviceIdBuff[50];
        if (questionMarkPointer == NULL)
        {
            sprintf(deviceIdBuff, "?device_id=%s", deviceId);
        }
        else
        {
            // params already started
            sprintf(deviceIdBuff, "&device_id=%s", deviceId);
        }
        strcat(command, deviceIdBuff);
    }

#ifdef SPOTIFY_DEBUG
    Serial.println(command);
    Serial.println(body);
#endif

    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }
    int statusCode = makePutRequest(command, _bearerToken, body);

    closeClient();
    // LOCAL_PATCHES (2026-05-08): spec says 204 but Spotify actually
    // returns 200 for the /me/player/* control endpoints. Accept any 2xx.
    return statusCode >= 200 && statusCode < 300;
}

bool SpotifyArduino::playerNavigate(char *command, const char *deviceId)
{
    if (deviceId[0] != 0)
    {
        char deviceIdBuff[50];
        sprintf(deviceIdBuff, "?device_id=%s", deviceId);
        strcat(command, deviceIdBuff);
    }

#ifdef SPOTIFY_DEBUG
    Serial.println(command);
#endif

    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }
    int statusCode = makePostRequest(command, _bearerToken);

    closeClient();
    // LOCAL_PATCHES (2026-05-08): spec says 204 but Spotify actually
    // returns 200 for the /me/player/* control endpoints. Accept any 2xx.
    return statusCode >= 200 && statusCode < 300;
}

bool SpotifyArduino::nextTrack(const char *deviceId)
{
    char command[100] = SPOTIFY_NEXT_TRACK_ENDPOINT;
    return playerNavigate(command, deviceId);
}

bool SpotifyArduino::previousTrack(const char *deviceId)
{
    char command[100] = SPOTIFY_PREVIOUS_TRACK_ENDPOINT;
    return playerNavigate(command, deviceId);
}
bool SpotifyArduino::seek(int position, const char *deviceId)
{
    char command[100] = SPOTIFY_SEEK_ENDPOINT;
    char tempBuff[100];
    sprintf(tempBuff, "?position_ms=%d", position);
    strcat(command, tempBuff);
    if (deviceId[0] != 0)
    {
        sprintf(tempBuff, "?device_id=%s", deviceId);
        strcat(command, tempBuff);
    }

#ifdef SPOTIFY_DEBUG
    Serial.println(command);
    printStack();
#endif

    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }
    int statusCode = makePutRequest(command, _bearerToken);
    closeClient();
    // LOCAL_PATCHES (2026-05-08): spec says 204 but Spotify returns 200
    // for these /me/player/* control endpoints. Accept any 2xx.
    return statusCode >= 200 && statusCode < 300;
}

bool SpotifyArduino::transferPlayback(const char *deviceId, bool play)
{
    char body[100];
    sprintf(body, "{\"device_ids\":[\"%s\"],\"play\":\"%s\"}", deviceId, (play ? "true" : "false"));

#ifdef SPOTIFY_DEBUG
    Serial.println(SPOTIFY_PLAYER_ENDPOINT);
    Serial.println(body);
    printStack();
#endif

    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }
    int statusCode = makePutRequest(SPOTIFY_PLAYER_ENDPOINT, _bearerToken, body);
    closeClient();
    // LOCAL_PATCHES (2026-05-08): spec says 204 but Spotify returns 200
    // for these /me/player/* control endpoints. Accept any 2xx.
    return statusCode >= 200 && statusCode < 300;
}

// LOCAL_PATCHES (TASK-020b / ADR-017): fetch /v1/me/player/queue.
// Parses currently_playing (item[0]) + up to SPOTIFY_QUEUE_MAX_ITEMS-1 queue
// items. Skips episodes (type != "track"). const char* fields in QueueData
// are ArduinoJson-owned — copy them inside the callback before returning.
int SpotifyArduino::getQueue(processQueue queueCallback)
{
    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }
    int statusCode = makeGetRequest(SPOTIFY_QUEUE_ENDPOINT, _bearerToken);
    HeaderInfo hdr = { -1, false };
    if (statusCode > 0)
    {
        hdr = skipHeaders();
    }

    if (statusCode == 200)
    {
        // LOCAL_PATCHES (TASK-047b): bumped from 256 to 320 to accommodate
        // duration_ms field in both currently_playing and queue items.
        StaticJsonDocument<320> filter;
        filter["currently_playing"]["name"]               = true;
        filter["currently_playing"]["uri"]                = true;
        filter["currently_playing"]["type"]               = true;
        filter["currently_playing"]["duration_ms"]        = true;
        filter["currently_playing"]["artists"][0]["name"] = true;
        JsonArray qf = filter.createNestedArray("queue");
        JsonObject qfi = qf.createNestedObject();
        qfi["name"]               = true;
        qfi["uri"]                = true;
        qfi["type"]               = true;
        qfi["duration_ms"]        = true;
        qfi["artists"][0]["name"] = true;

        DynamicJsonDocument doc(queueBufferSize);

        // INV-A: raw queue response is ~40–60 KB (up to ~20 full Spotify track
        // objects in the queue array). 32 KB was insufficient; 64 KB covers it.
        const size_t bodyBufSize = 65536;
        char *bodyBuf = (char *)malloc(bodyBufSize);
        if (!bodyBuf)
        {
            _chunkedResponse = true;  // force stop: unread body would corrupt stream
            closeClient();
            return statusCode;
        }
        size_t bodyLen = 0;
        // 3 s per-byte timeout: TLS records on ESP32 arrive < 1 s apart under
        // normal conditions; 3 s is safe headroom without the 20 s stall.
        client->setTimeout(3000);
        if (hdr.chunked)
        {
            // TASK-065: dechunker — strip HTTP/1.1 chunked framing (HEX\r\n DATA \r\n)
            // before passing to deserializeJson. Spotify sends chunked for /queue
            // under HTTP/1.1 keep-alive (Content-Length not present).
            char szLine[16];
            while (bodyLen < bodyBufSize - 1)
            {
                int n = client->readBytesUntil('\n', szLine, sizeof(szLine) - 1);
                if (n > 0 && szLine[n - 1] == '\r') n--;
                szLine[n] = '\0';
                unsigned long chunkSz = strtoul(szLine, nullptr, 16);
                if (chunkSz == 0) break;  // terminal chunk
                size_t space = bodyBufSize - 1 - bodyLen;
                size_t toRead = (chunkSz < space) ? (size_t)chunkSz : space;
                bodyLen += client->readBytes(bodyBuf + bodyLen, toRead);
                client->readBytesUntil('\n', szLine, sizeof(szLine) - 1);  // discard trailing CRLF
                if (toRead < chunkSz) break;  // buffer full
            }
        }
        else
        {
            size_t readLen = (hdr.contentLength > 0 && (size_t)hdr.contentLength < bodyBufSize - 1)
                             ? (size_t)hdr.contentLength
                             : bodyBufSize - 1;
            bodyLen = client->readBytes(bodyBuf, readLen);
        }
        client->setTimeout(SPOTIFY_TIMEOUT);
        bodyBuf[bodyLen] = '\0';

#ifndef SPOTIFY_PRINT_JSON_PARSE
        DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#else
        Serial.write((const uint8_t *)bodyBuf, bodyLen);
        Serial.println();
        DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#endif
        free(bodyBuf);
        if (!error)
        {
            QueueData qd;
            memset(&qd, 0, sizeof(qd));
            qd.count = 0;

            // Slot 0 — currently_playing
            JsonObject cp = doc["currently_playing"];
            if (!cp.isNull())
            {
                const char *cpType = cp["type"] | "";
                if (strcmp(cpType, "track") == 0)
                {
                    qd.items[0].name       = cp["name"]              | "";
                    qd.items[0].uri        = cp["uri"]               | "";
                    qd.items[0].artistName = cp["artists"][0]["name"] | "";
                    qd.items[0].durationMs = cp["duration_ms"].as<long>();
                    qd.count = 1;
                }
            }

            // Slots 1..SPOTIFY_QUEUE_MAX_ITEMS-1 — queue[]
            JsonArray queue = doc["queue"];
            if (!queue.isNull())
            {
                for (JsonObject item : queue)
                {
                    if (qd.count >= SPOTIFY_QUEUE_MAX_ITEMS) break;
                    const char *itemType = item["type"] | "";
                    if (strcmp(itemType, "track") != 0) continue;
                    qd.items[qd.count].name       = item["name"]              | "";
                    qd.items[qd.count].uri        = item["uri"]               | "";
                    qd.items[qd.count].artistName = item["artists"][0]["name"] | "";
                    qd.items[qd.count].durationMs = item["duration_ms"].as<long>();
                    qd.count++;
                }
            }

            queueCallback(qd);
        }
        else
        {
#ifdef SPOTIFY_SERIAL_OUTPUT
            Serial.print(F("[spotify] getQueue JSON err: "));
            Serial.println(error.c_str());
#endif
        }
        closeClient();
    }
    return statusCode;
}

int SpotifyArduino::getCurrentlyPlaying(processCurrentlyPlaying currentlyPlayingCallback, const char *market)
{
    char command[75] = SPOTIFY_CURRENTLY_PLAYING_ENDPOINT;
    if (market[0] != 0)
    {
        char marketBuff[15];
        sprintf(marketBuff, "&market=%s", market);
        strcat(command, marketBuff);
    }

#ifdef SPOTIFY_DEBUG
    Serial.println(command);
    printStack();
#endif

    // Get from https://arduinojson.org/v6/assistant/
    const size_t bufferSize = currentlyPlayingBufferSize;

    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }
    int statusCode = makeGetRequest(command, _bearerToken);
#ifdef SPOTIFY_DEBUG
    Serial.print("Status Code: ");
    Serial.println(statusCode);
    printStack();
#endif
    HeaderInfo hdr = { -1, false };
    if (statusCode > 0)
    {
        hdr = skipHeaders();
    }

    if (statusCode == 200)
    {
        // LOCAL_PATCHES: zero-init so trackUri/trackName etc. are null when
        // currentlyPlayingType==other skips both track and episode fill blocks.
        CurrentlyPlaying current = {};

        //Apply Json Filter: https://arduinojson.org/v6/example/filter/
        StaticJsonDocument<464> filter;
        filter["is_playing"] = true;
        filter["currently_playing_type"] = true;
        filter["progress_ms"] = true;
        filter["context"]["uri"] = true;
        // LOCAL_PATCHES (TASK-039): surface device.volume_percent so the
        // chrome can drive the VOLUME slider without a second endpoint.
        filter["device"]["volume_percent"] = true;
        // LOCAL_PATCHES patch #9: surface shuffle/repeat state too.
        filter["shuffle_state"] = true;
        filter["repeat_state"] = true;

        JsonObject filter_item = filter.createNestedObject("item");
        filter_item["duration_ms"] = true;
        filter_item["name"] = true;
        filter_item["uri"] = true;

        JsonObject filter_item_artists_0 = filter_item["artists"].createNestedObject();
        filter_item_artists_0["name"] = true;
        filter_item_artists_0["uri"] = true;

        JsonObject filter_item_album = filter_item.createNestedObject("album");
        filter_item_album["name"] = true;
        filter_item_album["uri"] = true;

        JsonObject filter_item_album_images_0 = filter_item_album["images"].createNestedObject();
        filter_item_album_images_0["height"] = true;
        filter_item_album_images_0["width"] = true;
        filter_item_album_images_0["url"] = true;

        // Podcast filters
        JsonObject filter_item_show = filter_item.createNestedObject("show");
        filter_item_show["name"] = true;
        filter_item_show["uri"] = true;

        JsonObject filter_item_images_0 = filter_item["images"].createNestedObject();
        filter_item_images_0["height"] = true;
        filter_item_images_0["width"] = true;
        filter_item_images_0["url"] = true;

        // Allocate DynamicJsonDocument
        DynamicJsonDocument doc(bufferSize);

        char *bodyBuf = (hdr.contentLength > 0) ? (char *)malloc(hdr.contentLength + 1) : NULL;
        if (!bodyBuf)
        {
            _chunkedResponse = true;
            statusCode = -1;
        }
        else
        {
            client->setTimeout(3000);
            size_t bodyLen = client->readBytes(bodyBuf, (size_t)hdr.contentLength);
            client->setTimeout(SPOTIFY_TIMEOUT);
            bodyBuf[bodyLen] = '\0';

#ifndef SPOTIFY_PRINT_JSON_PARSE
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#else
            Serial.write((const uint8_t *)bodyBuf, bodyLen);
            Serial.println();
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#endif
        if (!error)
        {
#ifdef SPOTIFY_DEBUG
            serializeJsonPretty(doc, Serial);
#endif
            JsonObject item = doc["item"];

            const char *currently_playing_type = doc["currently_playing_type"];

            current.isPlaying = doc["is_playing"].as<bool>();

            current.progressMs = doc["progress_ms"].as<long>();
            current.durationMs = item["duration_ms"].as<long>();

            // LOCAL_PATCHES (TASK-039): device.volume_percent → -1 if
            // device or field is missing/null.
            if (!doc["device"].isNull() && !doc["device"]["volume_percent"].isNull()) {
                current.volumePercent = doc["device"]["volume_percent"].as<int>();
            } else {
                current.volumePercent = -1;
            }

            // LOCAL_PATCHES patch #9: shuffle + repeat. Mirrors getPlayerDetails
            // parsing. Defaults: shuffle=false, repeat=off when fields missing.
            current.shuffleState = doc["shuffle_state"].as<bool>();
            const char *repeat_raw = doc["repeat_state"];
            if (repeat_raw != NULL && strncmp(repeat_raw, "track", 5) == 0) {
                current.repeatState = repeat_track;
            } else if (repeat_raw != NULL && strncmp(repeat_raw, "context", 7) == 0) {
                current.repeatState = repeat_context;
            } else {
                current.repeatState = repeat_off;
            }

            // context may be null
            if (!doc["context"].isNull())
            {
                current.contextUri = doc["context"]["uri"].as<const char *>();
            }
            else
            {
                current.contextUri = NULL;
            }

            // Check currently playing type
            // LOCAL_PATCHES: guard against null (field absent mid-stream on track start)
            if (currently_playing_type == NULL)
            {
                current.currentlyPlayingType = other;
            }
            else if (strcmp(currently_playing_type, "track") == 0)
            {
                current.currentlyPlayingType = track;
            }
            else if (strcmp(currently_playing_type, "episode") == 0)
            {
                current.currentlyPlayingType = episode;
            }
            else
            {
                current.currentlyPlayingType = other;
            }

            // If it's a song/track
            if (current.currentlyPlayingType == track)
            {
                int numArtists = item["artists"].size();
                if (numArtists > SPOTIFY_MAX_NUM_ARTISTS)
                {
                    numArtists = SPOTIFY_MAX_NUM_ARTISTS;
                }
                current.numArtists = numArtists;

                for (int i = 0; i < current.numArtists; i++)
                {
                    current.artists[i].artistName = item["artists"][i]["name"].as<const char *>();
                    current.artists[i].artistUri = item["artists"][i]["uri"].as<const char *>();
                }

                current.albumName = item["album"]["name"].as<const char *>();
                current.albumUri = item["album"]["uri"].as<const char *>();

                JsonArray images = item["album"]["images"];

                // Images are returned in order of width, so last should be smallest.
                int numImages = images.size();
                int startingIndex = 0;
                if (numImages > SPOTIFY_NUM_ALBUM_IMAGES)
                {
                    startingIndex = numImages - SPOTIFY_NUM_ALBUM_IMAGES;
                    current.numImages = SPOTIFY_NUM_ALBUM_IMAGES;
                }
                else
                {
                    current.numImages = numImages;
                }
#ifdef SPOTIFY_DEBUG
                Serial.print(F("Num Images: "));
                Serial.println(current.numImages);
                Serial.println(numImages);
#endif

                for (int i = 0; i < current.numImages; i++)
                {
                    int adjustedIndex = startingIndex + i;
                    current.albumImages[i].height = images[adjustedIndex]["height"].as<int>();
                    current.albumImages[i].width = images[adjustedIndex]["width"].as<int>();
                    current.albumImages[i].url = images[adjustedIndex]["url"].as<const char *>();
                }

                current.trackName = item["name"].as<const char *>();
                current.trackUri = item["uri"].as<const char *>();
            }
            else if (current.currentlyPlayingType == episode) // Podcast
            {
                current.numArtists = 1;

                // Save Podcast as the "track"
                current.trackName = item["name"].as<const char *>();
                current.trackUri = item["uri"].as<const char *>();

                // Save Show name as the "artist"
                current.artists[0].artistName = item["show"]["name"].as<const char *>();
                current.artists[0].artistUri = item["show"]["uri"].as<const char *>();

                // Leave "album" name blank
                char blank[1] = "";
                current.albumName = blank;
                current.albumUri = blank;

                // Save the episode images as the "album art"
                JsonArray images = item["images"];
                // Images are returned in order of width, so last should be smallest.
                int numImages = images.size();
                int startingIndex = 0;
                if (numImages > SPOTIFY_NUM_ALBUM_IMAGES)
                {
                    startingIndex = numImages - SPOTIFY_NUM_ALBUM_IMAGES;
                    current.numImages = SPOTIFY_NUM_ALBUM_IMAGES;
                }
                else
                {
                    current.numImages = numImages;
                }
#ifdef SPOTIFY_DEBUG
                Serial.print(F("Num Images: "));
                Serial.println(current.numImages);
                Serial.println(numImages);
#endif

                for (int i = 0; i < current.numImages; i++)
                {
                    int adjustedIndex = startingIndex + i;
                    current.albumImages[i].height = images[adjustedIndex]["height"].as<int>();
                    current.albumImages[i].width = images[adjustedIndex]["width"].as<int>();
                    current.albumImages[i].url = images[adjustedIndex]["url"].as<const char *>();
                }
            }

            currentlyPlayingCallback(current);
        }
        else
        {
#ifdef SPOTIFY_SERIAL_OUTPUT
            Serial.print(F("deserializeJson() failed with code "));
            Serial.println(error.c_str());
#endif
            statusCode = -1;
        }
            free(bodyBuf);
        }
    }

    closeClient();
    return statusCode;
}

int SpotifyArduino::getPlayerDetails(processPlayerDetails playerDetailsCallback, const char *market)
{
    char command[100] = SPOTIFY_PLAYER_ENDPOINT;
    if (market[0] != 0)
    {
        char marketBuff[30];
        sprintf(marketBuff, "?market=%s", market);
        strcat(command, marketBuff);
    }

#ifdef SPOTIFY_DEBUG
    Serial.println(command);
    printStack();
#endif

    // Get from https://arduinojson.org/v6/assistant/
    const size_t bufferSize = playerDetailsBufferSize;
    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }

    int statusCode = makeGetRequest(command, _bearerToken);
#ifdef SPOTIFY_DEBUG
    Serial.print("Status Code: ");
    Serial.println(statusCode);
#endif
    HeaderInfo hdr = { -1, false };
    if (statusCode > 0)
    {
        hdr = skipHeaders();
    }

    if (statusCode == 200)
    {

        StaticJsonDocument<192> filter;
        JsonObject filter_device = filter.createNestedObject("device");
        filter_device["id"] = true;
        filter_device["name"] = true;
        filter_device["type"] = true;
        filter_device["is_active"] = true;
        filter_device["is_private_session"] = true;
        filter_device["is_restricted"] = true;
        filter_device["volume_percent"] = true;
        filter["progress_ms"] = true;
        filter["is_playing"] = true;
        filter["shuffle_state"] = true;
        filter["repeat_state"] = true;

        // Allocate DynamicJsonDocument
        DynamicJsonDocument doc(bufferSize);

        char *bodyBuf = (hdr.contentLength > 0) ? (char *)malloc(hdr.contentLength + 1) : NULL;
        if (!bodyBuf)
        {
            _chunkedResponse = true;
            statusCode = -1;
        }
        else
        {
            client->setTimeout(3000);
            size_t bodyLen = client->readBytes(bodyBuf, (size_t)hdr.contentLength);
            client->setTimeout(SPOTIFY_TIMEOUT);
            bodyBuf[bodyLen] = '\0';

#ifndef SPOTIFY_PRINT_JSON_PARSE
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#else
            Serial.write((const uint8_t *)bodyBuf, bodyLen);
            Serial.println();
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen, DeserializationOption::Filter(filter));
#endif
            if (!error)
            {
                PlayerDetails playerDetails;

                JsonObject device = doc["device"];
                playerDetails.device.id = device["id"].as<const char *>();
                playerDetails.device.name = device["name"].as<const char *>();
                playerDetails.device.type = device["type"].as<const char *>();

                playerDetails.device.isActive = device["is_active"].as<bool>();
                playerDetails.device.isPrivateSession = device["is_private_session"].as<bool>();
                playerDetails.device.isRestricted = device["is_restricted"].as<bool>();
                playerDetails.device.volumePercent = device["volume_percent"].as<int>();

                playerDetails.progressMs = doc["progress_ms"].as<long>();
                playerDetails.isPlaying = doc["is_playing"].as<bool>();

                playerDetails.shuffleState = doc["shuffle_state"].as<bool>();

                const char *repeat_state = doc["repeat_state"];

                if (strncmp(repeat_state, "track", 5) == 0)
                {
                    playerDetails.repeateState = repeat_track;
                }
                else if (strncmp(repeat_state, "context", 7) == 0)
                {
                    playerDetails.repeateState = repeat_context;
                }
                else
                {
                    playerDetails.repeateState = repeat_off;
                }

                playerDetailsCallback(playerDetails);
            }
            else
            {
#ifdef SPOTIFY_SERIAL_OUTPUT
                Serial.print(F("deserializeJson() failed with code "));
                Serial.println(error.c_str());
#endif
                statusCode = -1;
            }
            free(bodyBuf);
        }
    }

    closeClient();
    return statusCode;
}

int SpotifyArduino::getDevices(processDevices devicesCallback)
{

#ifdef SPOTIFY_DEBUG
    Serial.println(SPOTIFY_DEVICES_ENDPOINT);
    printStack();
#endif

    // Get from https://arduinojson.org/v6/assistant/
    const size_t bufferSize = getDevicesBufferSize;
    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }

    int statusCode = makeGetRequest(SPOTIFY_DEVICES_ENDPOINT, _bearerToken);
#ifdef SPOTIFY_DEBUG
    Serial.print("Status Code: ");
    Serial.println(statusCode);
#endif
    HeaderInfo hdr = { -1, false };
    if (statusCode > 0)
    {
        hdr = skipHeaders();
    }

    if (statusCode == 200)
    {

        // Allocate DynamicJsonDocument
        DynamicJsonDocument doc(bufferSize);

        char *bodyBuf = (hdr.contentLength > 0) ? (char *)malloc(hdr.contentLength + 1) : NULL;
        if (!bodyBuf)
        {
            _chunkedResponse = true;
            statusCode = -1;
        }
        else
        {
            client->setTimeout(3000);
            size_t bodyLen = client->readBytes(bodyBuf, (size_t)hdr.contentLength);
            client->setTimeout(SPOTIFY_TIMEOUT);
            bodyBuf[bodyLen] = '\0';

#ifndef SPOTIFY_PRINT_JSON_PARSE
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen);
#else
            Serial.write((const uint8_t *)bodyBuf, bodyLen);
            Serial.println();
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen);
#endif
            if (!error)
            {
                uint8_t totalDevices = doc["devices"].size();

                SpotifyDevice spotifyDevice;
                for (int i = 0; i < totalDevices; i++)
                {
                    JsonObject device = doc["devices"][i];
                    spotifyDevice.id = device["id"].as<const char *>();
                    spotifyDevice.name = device["name"].as<const char *>();
                    spotifyDevice.type = device["type"].as<const char *>();

                    spotifyDevice.isActive = device["is_active"].as<bool>();
                    spotifyDevice.isPrivateSession = device["is_private_session"].as<bool>();
                    spotifyDevice.isRestricted = device["is_restricted"].as<bool>();
                    spotifyDevice.volumePercent = device["volume_percent"].as<int>();

                    if (!devicesCallback(spotifyDevice, i, totalDevices))
                    {
                        break;
                    }
                }
            }
            else
            {
#ifdef SPOTIFY_SERIAL_OUTPUT
                Serial.print(F("deserializeJson() failed with code "));
                Serial.println(error.c_str());
#endif
                statusCode = -1;
            }
            free(bodyBuf);
        }
    }

    closeClient();
    return statusCode;
}

int SpotifyArduino::searchForSong(String query, int limit, processSearch searchCallback, SearchResult results[])
{

#ifdef SPOTIFY_DEBUG
    Serial.println(SPOTIFY_SEARCH_ENDPOINT);
    printStack();
#endif

    // Get from https://arduinojson.org/v6/assistant/
    const size_t bufferSize = searchDetailsBufferSize;
    if (autoTokenRefresh)
    {
        checkAndRefreshAccessToken();
    }

    int statusCode = makeGetRequest((SPOTIFY_SEARCH_ENDPOINT + query + "&limit=" + limit).c_str(), _bearerToken);
#ifdef SPOTIFY_DEBUG
    Serial.print("Status Code: ");
    Serial.println(statusCode);
#endif
    HeaderInfo hdr = { -1, false };
    if (statusCode > 0)
    {
        hdr = skipHeaders();
    }

    if (statusCode == 200)
    {

        // Allocate DynamicJsonDocument
        DynamicJsonDocument doc(bufferSize);

        char *bodyBuf = (hdr.contentLength > 0) ? (char *)malloc(hdr.contentLength + 1) : NULL;
        if (!bodyBuf)
        {
            _chunkedResponse = true;
            statusCode = -1;
        }
        else
        {
            client->setTimeout(3000);
            size_t bodyLen = client->readBytes(bodyBuf, (size_t)hdr.contentLength);
            client->setTimeout(SPOTIFY_TIMEOUT);
            bodyBuf[bodyLen] = '\0';

#ifndef SPOTIFY_PRINT_JSON_PARSE
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen);
#else
            Serial.write((const uint8_t *)bodyBuf, bodyLen);
            Serial.println();
            DeserializationError error = deserializeJson(doc, bodyBuf, bodyLen);
#endif
            if (!error)
            {
                uint8_t totalResults = doc["tracks"]["items"].size();

                Serial.print("Total Results: ");
                Serial.println(totalResults);

                SearchResult searchResult;
                for (int i = 0; i < totalResults; i++)
                {
                    JsonObject result = doc["tracks"]["items"][i];
                    searchResult.trackUri = result["uri"].as<const char *>();
                    searchResult.trackName = result["name"].as<const char *>();
                    searchResult.albumUri = result["album"]["uri"].as<const char *>();
                    searchResult.albumName = result["album"]["name"].as<const char *>();

                    uint8_t totalArtists = result["artists"].size();
                    searchResult.numArtists = totalArtists;

                    SpotifyArtist artist;
                    for (int j = 0; j < totalArtists; j++)
                    {
                        JsonObject artistResult = result["artists"][j];
                        artist.artistName = artistResult["name"].as<const char *>();
                        artist.artistUri = artistResult["uri"].as<const char *>();
                        searchResult.artists[j] = artist;
                    }

                    uint8_t totalImages = result["album"]["images"].size();
                    searchResult.numImages = totalImages;

                    SpotifyImage image;
                    for (int j = 0; j < totalImages; j++)
                    {
                        JsonObject imageResult = result["album"]["images"][j];
                        image.height = imageResult["height"].as<int>();
                        image.width = imageResult["width"].as<int>();
                        image.url = imageResult["url"].as<const char *>();
                        searchResult.albumImages[j] = image;
                    }

                    results[i] = searchResult;

                    if (i >= limit || !searchCallback(searchResult, i, totalResults))
                    {
                        break;
                    }
                }
            }
            else
            {
#ifdef SPOTIFY_SERIAL_OUTPUT
                Serial.print(F("deserializeJson() failed with code "));
                Serial.println(error.c_str());
#endif
                statusCode = -1;
            }
            free(bodyBuf);
        }
    }

    closeClient();
    return statusCode;
}

int SpotifyArduino::commonGetImage(char *imageUrl)
{
#ifdef SPOTIFY_DEBUG
    Serial.print(F("Parsing image URL: "));
    Serial.println(imageUrl);
#endif

    uint8_t lengthOfString = strlen(imageUrl);

    // We are going to just assume https, that's all I've
    // seen and I can't imagine a company will go back
    // to http

    if (strncmp(imageUrl, "https://", 8) != 0)
    {
#ifdef SPOTIFY_SERIAL_OUTPUT
        Serial.print(F("Url not in expected format: "));
        Serial.println(imageUrl);
        Serial.println("(expected it to start with \"https://\")");
#endif
        return false;
    }

    uint8_t protocolLength = 8;

    char *pathStart = strchr(imageUrl + protocolLength, '/');
    uint8_t pathIndex = pathStart - imageUrl;
    uint8_t pathLength = lengthOfString - pathIndex;
    char path[pathLength + 1];
    strncpy(path, pathStart, pathLength);
    path[pathLength] = '\0';

    uint8_t hostLength = pathIndex - protocolLength;
    char host[hostLength + 1];
    strncpy(host, imageUrl + protocolLength, hostLength);
    host[hostLength] = '\0';

#ifdef SPOTIFY_DEBUG

    Serial.print(F("host: "));
    Serial.println(host);

    Serial.print(F("len:host:"));
    Serial.println(hostLength);

    Serial.print(F("path: "));
    Serial.println(path);

    Serial.print(F("len:path: "));
    Serial.println(strlen(path));
#endif

    int statusCode = makeGetRequest(path, NULL, "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8", host);
#ifdef SPOTIFY_DEBUG
    Serial.print(F("statusCode: "));
    Serial.println(statusCode);
#endif
    if (statusCode == 200)
    {
        // INV-A Step 3: skipHeaders() reads all headers line-by-line, returning
        // Content-Length. Body starts immediately after; caller reads it directly.
        HeaderInfo info = skipHeaders();
        return info.contentLength;
    }

    // Failed
    return -1;
}

bool SpotifyArduino::getImage(char *imageUrl, Stream *file)
{
    int totalLength = commonGetImage(imageUrl);

#ifdef SPOTIFY_DEBUG
    Serial.print(F("file length: "));
    Serial.println(totalLength);
#endif
    if (totalLength > 0)
    {
        // Headers already consumed by commonGetImage's skipHeaders() call.
        int remaining = totalLength;
        // This section of code is inspired but the "Web_Jpg"
        // example of TJpg_Decoder
        // https://github.com/Bodmer/TJpg_Decoder
        // -----------
        uint8_t buff[128] = {0};
        while (client->connected() && (remaining > 0 || remaining == -1))
        {
            // Get available data size
            size_t size = client->available();

            if (size)
            {
                // Read up to 128 bytes
                int c = client->readBytes(buff, ((size > sizeof(buff)) ? sizeof(buff) : size));

                // Write it to file
                file->write(buff, c);

                // Calculate remaining bytes
                if (remaining > 0)
                {
                    remaining -= c;
                }
            }
            yield();
        }
// ---------
#ifdef SPOTIFY_DEBUG
        Serial.println(F("Finished getting image"));
#endif
    }

    closeClient();

    return (totalLength > 0); //Probably could be improved!
}

bool SpotifyArduino::getImage(char *imageUrl, uint8_t **image, int *imageLength)
{
    int totalLength = commonGetImage(imageUrl);

#ifdef SPOTIFY_DEBUG
    Serial.print(F("file length: "));
    Serial.println(totalLength);
#endif
    if (totalLength > 0)
    {
        // Headers already consumed by commonGetImage's skipHeaders() call.
        uint8_t *imgPtr = (uint8_t *)malloc(totalLength);
        *image = imgPtr;
        *imageLength = totalLength;
        int remaining = totalLength;
        int amountRead = 0;

#ifdef SPOTIFY_DEBUG
        Serial.println(F("Fetching Image"));
#endif

        // This section of code is inspired but the "Web_Jpg"
        // example of TJpg_Decoder
        // https://github.com/Bodmer/TJpg_Decoder
        // -----------
        uint8_t buff[128] = {0};
        while (client->connected() && (remaining > 0 || remaining == -1))
        {
            // Get available data size
            size_t size = client->available();

            if (size)
            {
                // Read up to 128 bytes
                int c = client->readBytes(buff, ((size > sizeof(buff)) ? sizeof(buff) : size));

                // Write it to file
                memcpy((uint8_t *)imgPtr + amountRead, (uint8_t *)buff, c);

                // Calculate remaining bytes
                if (remaining > 0)
                {
                    amountRead += c;
                    remaining -= c;
                }
            }
            yield();
        }
// ---------
#ifdef SPOTIFY_DEBUG
        Serial.println(F("Finished getting image"));
#endif
    }

    closeClient();

    return (totalLength > 0); //Probably could be improved!
}

int SpotifyArduino::getContentLength()
{

    if (client->find("Content-Length:"))
    {
        int contentLength = client->parseInt();
#ifdef SPOTIFY_DEBUG
        Serial.print(F("Content-Length: "));
        Serial.println(contentLength);
#endif
        return contentLength;
    }

    return -1;
}

SpotifyArduino::HeaderInfo SpotifyArduino::skipHeaders()
{
    // INV-A Step 3: line-by-line parse to extract Content-Length and detect
    // Transfer-Encoding: chunked. Clears _chunkedResponse on entry so the
    // flag always reflects the current response.
    _chunkedResponse = false;
    HeaderInfo info = { -1, false };

    char lineBuf[192];
    while (true)
    {
        int n = client->readBytesUntil('\n', lineBuf, sizeof(lineBuf) - 1);
        if (n > 0 && lineBuf[n - 1] == '\r') n--;
        lineBuf[n] = '\0';
        if (n == 0) break;  // blank line = end of headers

        if (strncasecmp(lineBuf, "Content-Length:", 15) == 0)
        {
            const char *p = lineBuf + 15;
            while (*p == ' ') p++;
            info.contentLength = atoi(p);
        }
        else if (strncasecmp(lineBuf, "Transfer-Encoding:", 18) == 0)
        {
            const char *p = lineBuf + 18;
            while (*p == ' ') p++;
            if (strncasecmp(p, "chunked", 7) == 0)
                info.chunked = true;
        }
    }

    _chunkedResponse = info.chunked;
    return info;
}

int SpotifyArduino::getHttpStatusCode()
{
    char status[32] = {0};
    client->readBytesUntil('\r', status, sizeof(status));
    client->read();  // consume the '\n' completing the CRLF; stream now at first header line
#ifdef SPOTIFY_DEBUG
    Serial.print(F("Status: "));
    Serial.println(status);
#endif

    char *token;
    token = strtok(status, " "); // https://www.tutorialspoint.com/c_standard_library/c_function_strtok.htm

#ifdef SPOTIFY_DEBUG
    Serial.print(F("HTTP Version: "));
    Serial.println(token);
#endif

    if (token != NULL && (strcmp(token, "HTTP/1.0") == 0 || strcmp(token, "HTTP/1.1") == 0))
    {
        token = strtok(NULL, " ");
        if (token != NULL)
        {
#ifdef SPOTIFY_DEBUG
            Serial.print(F("Status Code: "));
            Serial.println(token);
#endif
            return atoi(token);
        }
    }

    // LOCAL_PATCHES: surface what we actually got so case (b) of the -1
    // sink (status-line parse) is debuggable. status[] holds the raw read
    // up to '\r' or readBytesUntil timeout. Connection state + bytes left
    // give context.
    Serial.printf("[lib] status-line parse fail: read='%s' connected=%d avail=%d\n",
                  status, (int)client->connected(), (int)client->available());
    return -1;
}

void SpotifyArduino::parseError(int contentLength)
{
#ifdef SPOTIFY_SERIAL_OUTPUT
    if (contentLength <= 0)
    {
        // No known body length — can't stream-parse under keep-alive.
        Serial.println(F("[lib] parseError: no content-length"));
        _chunkedResponse = true;  // force closeClient() to stop()
        return;
    }
    char *bodyBuf = (char *)malloc(contentLength + 1);
    if (!bodyBuf)
    {
        _chunkedResponse = true;
        return;
    }
    client->setTimeout(3000);
    size_t n = client->readBytes(bodyBuf, (size_t)contentLength);
    client->setTimeout(SPOTIFY_TIMEOUT);
    bodyBuf[n] = '\0';

    DynamicJsonDocument doc(1000);
    DeserializationError error = deserializeJson(doc, bodyBuf, n);
    free(bodyBuf);
    if (!error)
    {
        Serial.print(F("getAuthToken error"));
        serializeJson(doc, Serial);
    }
    else
    {
        Serial.print(F("Could not parse error"));
    }
#endif
}

void SpotifyArduino::lateInit(const char *clientId, const char *clientSecret, const char *refreshToken)
{
    this->_clientId = clientId;
    this->_clientSecret = clientSecret;
    setRefreshToken(refreshToken);
}

void SpotifyArduino::drainBody()
{
    // INV-A Step 1: consume remaining response bytes so the server's HTTP/1.0
    // FIN arrives cleanly. Connected() then accurately returns false, allowing
    // the conditional reconnect in Step 2 to open a fresh (non-zombie) socket.
    unsigned long deadline = millis() + SPOTIFY_TIMEOUT;
    while (client->connected() && millis() < deadline)
    {
        while (client->available())
            client->read();
        delay(1);
    }
}

void SpotifyArduino::closeClient()
{
    // INV-A Step 3: chunked responses can't be drained without dechunking —
    // force-close and accept one reconnect on the next request.
    if (_chunkedResponse)
    {
        _chunkedResponse = false;
        client->stop();
        delay(200);
        _connectedHost[0] = '\0';
#ifdef SPOTIFY_DEBUG
        Serial.println(F("closeClient: chunked, stopped"));
#endif
        return;
    }

    // Keep-alive success path: drain any remaining bytes (response headers
    // for control endpoints; trailing bytes for JSON endpoints that read
    // body via readBytes). Do NOT stop() — leave TLS session alive.
    while (client->available())
        client->read();

#ifdef SPOTIFY_DEBUG
    Serial.println(F("closeClient: keep-alive, drained"));
#endif
}

#ifdef SPOTIFY_DEBUG
void SpotifyArduino::printStack()
{
    char stack;
    Serial.print(F("stack size "));
    Serial.println(stack_start - &stack);
}
#endif
