# Local patches to vendored SpotifyArduino

This is a vendored copy of `witnessmenow/spotify-api-arduino` (formerly
pulled by PlatformIO `lib_deps`). It is checked in under
`Spotify-Diy-Thing/lib/SpotifyArduino/` so PlatformIO compiles this copy
instead of re-downloading upstream.

## Patches applied

### 1. Public `getBearerToken()` getter — `src/SpotifyArduino.h`

Added one inline accessor in the `public:` section, just below
`lateInit()`:

```cpp
const char *getBearerToken() const { return _bearerToken; }
```

The buffer holds the pre-formatted string `"Bearer <access_token>"`
maintained by the library's auth-refresh path (see `_bearerToken` and
the assignments around `SpotifyArduino.cpp:31` and `:220` and `:300`).

### Reason

`audio-features` and `audio-analysis` are not implemented on
`SpotifyArduino`. The M1 spike fetches them via Arduino's `HTTPClient`
(or the library's own public `makeGetRequest()` plus a local header
skipper) and needs the bearer token to set `Authorization`. The token
was previously only accessible to the library itself.

### 2. Disabled `SPOTIFY_DEBUG` — `src/SpotifyArduino.h`

Commented out `#define SPOTIFY_DEBUG 1` at line 29. The debug flag
caused the library to `Serial.print()` the full
`grant_type=refresh_token&refresh_token=...&client_id=...&client_secret=...`
POST body on every auth refresh, leaking secrets to anyone watching
the serial log. With auth retrying every 5 s on failure (e.g. the
2026-04-28 boot-time TLS issue), the leak compounds quickly.

### Reason (SPOTIFY_DEBUG)

Per `docs/quality/lessons_learned.md` LL-003, vendored libraries with
auth handling must have their debug-log surface audited before first
flash. The library's own header comment says:
"Do not use this option on live-streams, it will reveal your private
tokens!" — same reasoning applies to any device whose serial console
is captured to disk or chat transcript.

### 3. `stop()` instead of `flush()` before `connect()` — `src/SpotifyArduino.cpp`

In both `makeRequestWithBody` (line 44) and `makeGetRequest` (line 113),
replaced the leading `client->flush()` with `client->stop()`. Comment
on each line cites ADR-007.

### Reason (stop-before-connect)

Per ADR-007: the library sends `HTTP/1.0`, so the server closes the
TCP/TLS session after every response. The library never called
`stop()` on the shared `WiFiClientSecure`, only `flush()`, so the
next `connect()` on Arduino-ESP32 2.0.17 could succeed against a
peer-closed session and the next write tripped mbedTLS `0x0050`
(`NET_CONN_RESET`). This was the root cause of TASK-007's `>` `<`
`p` `P` `s` `S` `+` `-` `v` `h` `H` `r` `R` `o` rows failing while
the GET poll loop continued working. `stop()` forces a fresh TLS
handshake per request — verified by clean build; DUT verification
deferred (TASK-009 verification gate).

### 4. Removed trailing `println()` health check in `makeRequestWithBody`

In `src/SpotifyArduino.cpp`, the upstream lib wrote the request as:

```c
client->println();      // end-of-headers blank line
client->print(body);
if (client->println() == 0) return -2;   // <-- removed
int statusCode = getHttpStatusCode();
```

That trailing `\r\n` is **after** the body — i.e. after Content-Length
bytes have been transmitted, after the server has received the
complete request and may have already responded and closed the
socket (HTTP/1.0 implicit `Connection: close`, 204 from player
endpoints). Writing into a closing/closed TLS socket trips mbedTLS
`0x0050 NET_CONN_RESET`, the `println()` returns 0, the lib returns
`-2`, and every PUT/POST in the spike harness logged `[FAIL]` —
even though the server had already actioned the request.

Patched (2026-05-08): removed the trailing `println()` and the `-2`
return. `makeRequestWithBody` now mirrors `makeGetRequest`: write
the request, read the response, return the HTTP status code.

### Reason (trailing-CRLF removal)

Spec-side: each affected player endpoint (`/me/player/{play,pause,
next,previous,seek,volume,shuffle,repeat}`) is documented with no
request body — Content-Length: 0 is correct, the trailing CRLF is
extraneous. Empirical: ADR-007 fixed the *first*-write 0x0050 (stale
session); this fix addresses the *last*-write 0x0050 (server already
closed). Both produce the same numeric error code, which is why
ADR-007 was thought to cover both cases.

### 5. `Content-Type` only sent when body is non-empty

In `makeRequestWithBody`, the lib unconditionally sent
`Content-Type: application/json`. For Spotify's empty-body player
endpoints (next/previous/pause/seek/volume/shuffle/repeat), this
combined with `Content-Length: 0` made the server early-RST the
connection — same mbedtls 0x0050 symptom as the trailing CRLF.

Patched (2026-05-08): emit `Content-Type` only when `body[0] !=
'\0'`. `play()` may take a JSON body for context_uri/offset etc.;
the firmware doesn't currently exercise that, but if/when it does,
the header will be emitted correctly.

`Content-Length` is **kept unconditional** — Spotify returns 411
Length Required if it's missing on POST/PUT, even with an empty
body.

### 6. Accept any 2xx as success on player-control calls

The spec for `/me/player/{play,pause,next,previous,seek,volume,
shuffle,repeat}` documents response 204 No Content, but Spotify
actually returns 200 for most of them (volume returns 204; seek
returns 200; etc.). Upstream lib's `return statusCode == 204`
flagged every successful call as failure.

Patched (2026-05-08): replaced `return statusCode == 204` with
`return statusCode >= 200 && statusCode < 300` in `playerControl`,
`playerNavigate`, `seek`, and `transferPlayback`.

### Reason (status-code laxity + Content-Type/Length distinction)

Spec is wrong; the server is the source of truth. DUT-confirmed:
14 of 15 spike-harness rows return [OK] post-patch on a single run
(the 15th hit a Marriott-WiFi flake — getHttpStatusCode timeout,
not a lib bug). User-reported pre-patch behaviour ("prev and fwd
controls work") is now explained: Spotify always actioned the
request, the lib just couldn't see success because of the strict
204 check + the early-RST false-negatives.

### 7. Surface `device.volume_percent` in `getCurrentlyPlaying`

In `src/SpotifyArduino.cpp` `getCurrentlyPlaying`:
- Added `filter["device"]["volume_percent"] = true;` to the JSON filter.
- Added parse: `current.volumePercent = doc["device"]["volume_percent"].as<int>();` (or `-1` if `device`/field is null).

In `src/SpotifyArduino.h`:
- Added `int volumePercent;` field to `CurrentlyPlaying` struct.

### Reason (volume_percent)

Per ADR-014, M-CHROME tier 2 makes the VOLUME slider dynamic. The
upstream lib's `currentlyPlaying` filter doesn't include the `device`
object — but the `/me/player/currently-playing` response does have it
when an active device is reporting. Surfacing one extra int avoids a
second `/me/player` (PlayerDetails) round-trip per poll.

`-1` sentinel signals "no active device or field missing"; the chrome
renderer treats that as the lowest-volume keyframe (or skip the slider
entirely — implementation choice in TASK-041).

### 8. `getCurrentlyPlaying` URL changed to `/me/player`

In `src/SpotifyArduino.h`, `SPOTIFY_CURRENTLY_PLAYING_ENDPOINT` was
changed from
`/v1/me/player/currently-playing?additional_types=episode` to
`/v1/me/player?additional_types=episode`.

No parser change. The function name `getCurrentlyPlaying` is now
slightly misleading (it queries the player-state endpoint, not the
named "currently playing" endpoint), but rename is deferred per
ADR-015 OOS list.

### Reason (URL change)

Patch #7 (TASK-039) added `device.volume_percent` to the filter for
`getCurrentlyPlaying`. T070a/T070b verification on 2026-05-10 found
the parser correctly falls through to `volumePercent = -1` on every
poll, regardless of which Spotify Connect device is active. Wire
capture against a working session showed why:
`/me/player/currently-playing` does **not** include the `device`
field at all in the actual response. The OpenAPI spec
(`resource/web-api/official-open-api.yaml:4701, 4967-4985`) declares
the response shape as `CurrentlyPlayingContextObject` (which
includes `device`); the server returns a subset.

`/me/player` is a strict superset: same `is_playing`, `progress_ms`,
`currently_playing_type`, `context.uri`, `item.*`, plus the
additional `device`, `repeat_state`, `shuffle_state`, `smart_shuffle`
that this parser ignores via filter. Side-by-side wire capture
documented in ADR-015's evidence section.

Second concrete instance of the LL-013 spec-vs-server divergence
pattern (first was the M1-spike "spec says 204, server returns
200"). Captured as LL-018 — strongest promotion candidate in the
LL set.

### 9. Surface `shuffle_state` + `repeat_state` in `getCurrentlyPlaying`

In `src/SpotifyArduino.cpp` `getCurrentlyPlaying`:
- Added `filter["shuffle_state"] = true;` and `filter["repeat_state"] = true;`
  to the JSON filter.
- Added parse mirroring `getPlayerDetails`: `current.shuffleState = doc["shuffle_state"].as<bool>();`
  and a `repeat_state` string → `RepeatOptions` (track / context / off) decode.

In `src/SpotifyArduino.h`:
- Added `bool shuffleState;` and `RepeatOptions repeatState;` fields to the
  `CurrentlyPlaying` struct.

### Reason (shuffle/repeat surfacing)

M-CHROME chrome-001 final renders the SHUFREP indicators and dispatches
shuffle / repeat toggles from touch. The upstream lib's
`getCurrentlyPlaying` filter already had room for these fields (the
`/me/player` response we already query includes them per ADR-015), but
they were only parsed by the unused `getPlayerDetails` path. Surfacing
them on the same poll avoids a second round-trip per cycle.

### 10. `getQueue` — surface `duration_ms` per item; `SPOTIFY_QUEUE_MAX_ITEMS` set to 20

In `src/SpotifyArduino.h`:
- Added `long durationMs` to `QueueItem` struct.
- `SPOTIFY_QUEUE_MAX_ITEMS` is `20` (capacity for up to 20 queue items including currently-playing).

In `src/SpotifyArduino.cpp` `getQueue`:
- Added `filter["currently_playing"]["duration_ms"] = true` and `qfi["duration_ms"] = true`
  to the JSON filter document (size bumped 256 → 320).
- Added `qd.items[i].durationMs = item["duration_ms"].as<long>()` parse for both
  currently_playing slot and queue[] items.

### Reason (duration_ms in queue)

TASK-047b (M-LIST-v2). `drawPlaylist()` needs track duration to format `"MM:SS"` duration
columns and to compute total playlist time (TASK-047d). The `getQueue` endpoint already
returns `duration_ms` in each item's track object — it was simply not included in the filter
or parsed. No extra API round-trip required.

Note: an earlier version of this patch reduced `SPOTIFY_QUEUE_MAX_ITEMS` to 5 to match
`PLEDIT_ROW_COUNT`. That reduction was reversed when `app/lib/` was created (TASK-083);
`cmdGetQueue` in `spotifyTaskStorage.cpp` now uses `QUEUE_MAX` (= `SPOTIFY_QUEUE_MAX_ITEMS`)
as its serialize cap so the snapshot and serial protocol agree (TASK-086).

### 11. Null guard before `strcmp(currently_playing_type, ...)` — `src/SpotifyArduino.cpp`

In `src/SpotifyArduino.cpp` `getCurrentlyPlaying` (~line 893):

```cpp
if (currently_playing_type == NULL)
{
    current.currentlyPlayingType = other;
}
else if (strcmp(currently_playing_type, "track") == 0)
```

### Reason (currently_playing_type null guard)

`doc["currently_playing_type"]` returns `nullptr` when the field is absent from the
response (observed on the first poll when a track starts mid-stream). The unguarded
`strcmp(nullptr, "track")` caused a `LoadProhibited` Guru Meditation crash at
`SpotifyArduino.cpp:894`. The existing `repeat_raw` handling (patch #9) already used
null guards — this patch brings `currently_playing_type` in line with the same pattern.

Filed as a crash on DUT 2026-05-22 during M-CONN validation. Fixed same session.

---

### Strategy decision (open)

Per ADR-006 / `architecture.md` Open Questions, the M1 exit decides
whether to:

1. Keep this vendored fork as the project's library going forward and
   add the missing endpoints here as proper methods.
2. Push the patch (and any new methods) upstream to
   `witnessmenow/spotify-api-arduino`.
3. Drop the library entirely and replace with a thinner client.

Until that decision is recorded, treat this fork as tactical.
