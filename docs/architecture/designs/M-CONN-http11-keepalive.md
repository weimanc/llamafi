# Design — HTTP/1.1 Keep-Alive for SpotifyArduino

> Owner: Architect
> Status: draft
> Date: 2026-05-19
> Feeds: (leave blank — no ADR yet)
> Tracked-as: (leave blank)

## Context / pain points

ADR-007 (`docs/architecture/decisions/ADR-007.md`) fixed zombie-socket write failures by inserting `client->stop()` before every request. This traded one bug for two: every request pays a full TLS handshake (~4–5 s), and the unconditional `stop()`+`connect()` cycle races against lwIP's fd-release on espressif32@6.9.0, producing a recurring `stale connect fd=49` zombie.

INV-A (`docs/rnd/investigations/INV-A-tls-connection-lifecycle.md`) Steps 1+2 (implemented 2026-05-18) reduced zombie-fd frequency but did not eliminate it. With HTTP/1.0 forcing a server-close after every response, the reconnect cycle still fires every ~5–6 s, and the lwIP fd-release race wins occasionally (~2 hits per 10 min). The only reliable fix is Step 3: switch to HTTP/1.1 keep-alive so `stop()`+`connect()` is called only when the server actually closes the connection (keep-alive timeout typically 60–90 s).

Four implementation gaps were not addressed in the INV-A Step 3 outline and must be resolved here:

1. `skipHeaders()` must return `Content-Length` and detect `Transfer-Encoding: chunked`.
2. Seven `deserializeJson(*client)` call sites rely on connection-close to signal EOF; keep-alive makes the stream never close, hanging the parser.
3. No mechanism for `skipHeaders()` to signal chunked back to `closeClient()`.
4. `makeRequestWithBody()` can POST to `accounts.spotify.com` (token refresh) — a different host than `api.spotify.com`; the conditional-reconnect must key on host, not just `connected()`.

## Goals

- Eliminate `stale connect fd=N` entirely over a 30+ min run.
- `block_max` < 500 ms per poll cycle (no per-request TLS handshake).
- `poll=S/N` > 95% over 30 min.
- No regression on PUT/POST control endpoints or token-refresh flow.
- Keep the change contained to the vendored `lib/SpotifyArduino/` — no caller changes.

## Design space (options + tradeoffs)

### Gap 1 — `skipHeaders()` API redesign

**Current state:** `client->find("\r\n\r\n")` — single destructive scan; discards all header bytes including `Content-Length` and `Transfer-Encoding`.

**Option A — Return a struct; parse line-by-line.**

New signature:
```
struct HeaderInfo {
    int  contentLength;   // -1 if absent
    bool chunked;         // true if Transfer-Encoding: chunked
};
HeaderInfo skipHeaders();
```

Implementation: read one line at a time with `client->readBytesUntil('\n', buf, sizeof(buf))` until an empty CRLF line is seen. Match `Content-Length:` and `Transfer-Encoding: chunked` on each line.

Tradeoffs: small stack buffer (~128 B) per call; handles any number of headers; returns both fields in one pass; callers must be updated to use `HeaderInfo` but the change is mechanical. Line-by-line is the only correct approach for HTTP/1.1 where header order is not guaranteed.

**Option B — Two-pass: find("\r\n\r\n"), then backtrack via `peek()`.**

`client->find()` is destructive and non-rewindable on `WiFiClientSecure`. Backtracking is not possible. This option is not viable.

**Option C — Call `getContentLength()` before `skipHeaders()`.**

`getContentLength()` (line 1385) already uses `client->find("Content-Length:")` — also destructive. Calling it before `find("\r\n\r\n")` would consume some header bytes and corrupt the stream for the second call. Not viable.

**Lean: Option A.** Line-by-line `readBytesUntil` is the only correct approach. The `HeaderInfo` struct is lightweight and expresses both outputs cleanly.

---

### Gap 2 — `deserializeJson(*client)` call sites (streaming EOF problem)

Six call sites pass `*client` (or a `ReadLoggingStream` wrapping it) directly to ArduinoJson. The parser reads until the stream signals EOF. Under HTTP/1.0, connection-close is that signal. Under keep-alive, the stream never closes, so the parser blocks until `SPOTIFY_TIMEOUT` fires — typically hanging the poll task for the full timeout duration.

**Option A — Buffer-then-parse for all sites.**

Read exactly `contentLength` bytes into a heap buffer; pass the buffer to `deserializeJson`. Already done for `getQueue()` (line 583–604). Extend the pattern to all sites.

Tradeoffs: requires `malloc(contentLength)` per call. Spotify API JSON payloads for these endpoints: `refreshAccessToken` ~512 B, `requestAccessTokens` ~1 KB, `getCurrentlyPlaying` ~2–4 KB, `getPlayerDetails` ~1 KB, `getAvailableDevices` ~1 KB, `searchForSong` variable. All comfortably within ESP32 heap (free ~218 KB at idle). Allocation failure must return early. Heap fragmentation risk is low given sizes and call frequency (these are infrequent relative to GETs). This approach is robust and uniform.

**Option B — Bounded stream wrapper.**

Wrap `*client` in a custom `BoundedStream` that returns EOF after `contentLength` bytes. Pass the wrapper to `deserializeJson` — no heap allocation needed for the body buffer itself.

Tradeoffs: requires a new class (`BoundedStream : public Stream`); more code surface. The Arduino `Stream` API on ESP32 does not have a clean, documented way to "peek ahead" without consuming; implementing correctly requires care. The gain over Option A (avoiding one `malloc` per call) is marginal given call frequency. If `contentLength` is -1 (absent), the wrapper cannot operate — fallback required.

**Option C — Chunked-aware streaming.**

Parse chunked encoding inline, dechunk on the fly into a stream adapter. Complexity is high; ArduinoJson has no built-in dechunking. Overkill for the observed payload sizes.

**Lean: Option A (buffer-then-parse) for all sites.** Uniform with the existing `getQueue()` pattern. `contentLength` from `HeaderInfo` drives the `readBytes` call. Allocation failure returns -1 immediately. If `contentLength == -1` (no header), fall back to connection-close mode (see Gap 3 below).

---

### Gap 3 — Chunked encoding signaling from `skipHeaders()` to `closeClient()`

With HTTP/1.1, Spotify may respond with `Transfer-Encoding: chunked` (no `Content-Length`). The INV-A outline says "fall back to connection-close for that response" but provides no mechanism.

**Option A — `bool` member flag `_chunkedResponse`.**

`skipHeaders()` sets `this->_chunkedResponse = headerInfo.chunked`. `closeClient()` reads it: if `_chunkedResponse`, call `client->stop()` (force-close, accept reconnect cost for that cycle) and clear the flag. On the next request the connection is gone; `makeGetRequest`/`makeRequestWithBody` reconnect normally.

Tradeoffs: adds one byte of state to the object; simple and self-contained; no call-site changes. Risk: if a caller returns early (error path) without calling `closeClient()`, the flag persists across calls. Mitigate: clear `_chunkedResponse` at the top of `skipHeaders()` on every invocation.

**Option B — Return a `ResponseMode` enum from `skipHeaders()` and thread it through every caller to `closeClient()`.**

Callers already have many code paths (early returns on parse failure, error status, etc.). Adding an extra parameter to every `closeClient()` call multiplies touch points and error-path risk significantly.

**Option C — Always stop on chunked at `skipHeaders()` time.**

If `chunked` is detected, `skipHeaders()` itself calls `client->stop()`. Downstream `deserializeJson` falls back to connection-close (stream closes immediately and signals EOF). `closeClient()` finds `!connected()`, still calls `stop()` (no-op), and moves on.

Tradeoffs: couples `skipHeaders()` to connection lifecycle — violates separation of concerns. Also prevents any future dechunking implementation.

**Lean: Option A (member flag `_chunkedResponse`).** One member, cleared on entry to `skipHeaders()`, checked in `closeClient()`. Minimal coupling. Chunked path pays one extra reconnect but chunked responses are expected to be rare.

---

### Gap 4 — Multi-host reconnect keying

`makeGetRequest` talks to `api.spotify.com`. `makeRequestWithBody` can talk to either `api.spotify.com` (player controls) or `accounts.spotify.com` (token refresh via `refreshAccessToken` and `requestAccessTokens`). The host is passed as a parameter (`const char *host`).

**Option A — Store `_connectedHost[64]` as a member; compare on each request.**

At reconnect time: if `client->connected()` AND `strcmp(_connectedHost, host) == 0`, reuse. Otherwise `stop()` + `connect(host, ...)` + update `_connectedHost`. Clear `_connectedHost` (set to `""`) whenever `client->stop()` is called.

Pseudo-interface:
```
// in makeGetRequest / makeRequestWithBody:
bool hostMatches = (strcmp(_connectedHost, host) == 0);
if (!client->connected() || !hostMatches) {
    client->stop();
    if (!client->connect(host, portNumber)) { return -1; }
    strncpy(_connectedHost, host, sizeof(_connectedHost)-1);
}
```

Tradeoffs: 64 B of object state; correct for all existing callers; `accounts.spotify.com` calls always reconnect (different host), which is appropriate — token refresh is rare (once per hour). No caller changes needed.

**Option B — Dedicate a separate `WiFiClientSecure` for `accounts.spotify.com`.**

Two client objects: `_apiClient` (`api.spotify.com`) and `_authClient` (`accounts.spotify.com`). Each has its own keep-alive connection.

Tradeoffs: doubles TLS context memory (~20–30 KB each on ESP32). The auth client is used at most once per hour; keeping it alive wastes memory. Unnecessary complexity.

**Option C — Always reconnect in `makeRequestWithBody` (current behaviour for auth calls).**

Token-refresh calls are infrequent (once/hour) and go to a different host. Accept the one-time TLS cost for auth, apply keep-alive only to `makeGetRequest`.

Tradeoffs: simpler — no host tracking needed. But player control PUT/POST calls (`play`, `pause`, `next`, `skip`) also go through `makeRequestWithBody` to `api.spotify.com`. If keep-alive is not applied there, each control action still pays a full handshake. Unacceptable for user-facing latency.

**Lean: Option A (member `_connectedHost`).** Correct for both hosts; minimal overhead; enables keep-alive on control endpoints as well.

---

### Retry on stale keep-alive

With HTTP/1.1, the server may close a keep-alive connection between requests (idle timeout). A write to a stale connection returns 0 or fails silently (or triggers mbedTLS error). Detection point: `client->println() == 0` (already checked in `makeGetRequest` line 184).

Design: on write failure in `makeGetRequest`/`makeRequestWithBody`, call `client->stop()`, clear `_connectedHost`, reconnect once, and retry the write. If the retry also fails, return -1 to the caller. One retry — not a loop.

## Lean / decision

Summary of all decisions:

| Gap | Decision |
|-----|----------|
| `skipHeaders()` signature | `HeaderInfo skipHeaders()` — line-by-line, returns `{contentLength, chunked}` |
| `deserializeJson` sites | Buffer-then-parse (Option A) using `contentLength` from `HeaderInfo`; `malloc` + `readBytes(contentLength)` |
| Chunked signaling | `bool _chunkedResponse` member flag; cleared in `skipHeaders()`, checked in `closeClient()` |
| Multi-host reconnect | `char _connectedHost[64]` member; conditional reconnect compares host + `connected()` |
| Stale keep-alive retry | Single retry on write failure inside `makeGetRequest`/`makeRequestWithBody` |
| `closeClient()` on success | Drain `available()` bytes; do NOT `stop()`; leave connection alive for next request |
| `closeClient()` on chunked | `stop()` + `delay(200)` (same as current path); sets `_connectedHost = ""` |

`getContentLength()` (line 1385) becomes dead code once `skipHeaders()` subsumes it. Leave in place but note it is superseded; a later cleanup ADR can remove it.

`drainBody()` (line 1489) remains for the chunked / connection-close path inside `closeClient()`. No change to its logic.

## Open questions

1. **Spotify chunked frequency in practice.** If `api.spotify.com` reliably responds with `Content-Length` under HTTP/1.1, the chunked path is never exercised. Verify in a short DUT run before declaring the chunked fallback complete.

2. **`getImageFromUrl()` / album art (winamp build — resolved).** `WinampDisplay` inherits `processImageInfo` from `CheapYellowDisplay`, which calls `getImage()` → CDN fetch on a different host, clobbering the keep-alive connection. Resolution: override `processImageInfo` in `WinampDisplay` to return `false` immediately (no-op). Album art is not used in the winamp renderer; the inheritance is incidental. This eliminates the CDN client conflict entirely for the target build. The `cyd`/`matrix` builds are unaffected (they do not use HTTP/1.1 keep-alive today).

3. **`parseError()` (line 1464)** also calls `deserializeJson(doc, *client)` under `SPOTIFY_SERIAL_OUTPUT`. This is a debug-only path; it reads until connection-close. Under keep-alive it hangs until timeout. Since `SPOTIFY_SERIAL_OUTPUT` is disabled on the production build (per LL-003), this is acceptable for now — flag for cleanup.

4. **Keep-alive timeout value.** Spotify's servers advertise `Keep-Alive: timeout=N` in their response. Parsing this and using it to proactively reconnect before server-side close would avoid the "write to stale" path entirely. Nice-to-have; the single-retry fallback already handles the stale case adequately.

## Exit criteria

- `stale connect fd=N` warnings: zero over 30+ min DUT run.
- `block_max` < 500 ms per poll cycle (no per-request TLS handshake visible in log).
- `poll=S/N` > 95% over 30 min.
- All PUT/POST rows from the ADR-007 verification matrix return 2xx.
- Token-refresh flow (`refreshAccessToken` to `accounts.spotify.com`) succeeds after a 1-hour soak.
- `getQueue()` continues to parse correctly (no regression from `HeaderInfo` integration).
- No heap allocation failure logged over a 30-min run (heap stays > 50 KB free).
