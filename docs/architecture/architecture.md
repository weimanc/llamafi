# System Architecture

> Owner: Architect
> Living system specification. Reflects accepted ADRs and validated implementation only.

This document describes two states of the system:

- **Current Implementation** — the Spotify-Diy-Thing firmware as it exists today. Baseline reference.
- **Target Architecture** — the proposed extension to a Winamp 2 classic skin UI with full controller capability and a PC-side mirror. Driven by ADR-001 through ADR-005.

---

# Current Implementation (Spotify-Diy-Thing baseline)

## System Overview

Single-purpose ESP32 firmware that polls Spotify's Web API for the user's currently-playing track and renders track + album art on a 320×240 LCD. Optional NFC reader for tap-to-play.

**Scope boundary:** only `Spotify-Diy-Thing/` is in scope. The sibling `cspot/` directory is a vendored upstream of an unrelated Spotify Connect *player* implementation; it is not built, linked, or referenced from this firmware.

## Component Architecture

```
                       +---------------------+
                       |  Spotify Web API    |
                       +----------+----------+
                                  |  HTTPS (TLS via WiFiClientSecure)
                                  |
+-------------------+    +--------v---------+    +------------------+
| WiFiManager (AP)  |--->| Wifi STA + DNS   |--->| SpotifyArduino   |
|  /config + DRD    |    +------------------+    |  (lib_dep)       |
+-------------------+                            +---+----+---------+
        |                                            |    |
        | first-boot only                            |    |
        v                                            |    |
+-------------------+      +------------------+      |    |
|  NVS (wifi creds) |      | SPIFFS           |<-----+    | track JSON +
+-------------------+      |  /spotify_diy_   |           | JPEG bytes
                           |  config.json     |           v
                           |  (clientId,      |   +-------+---------+
                           |   clientSecret,  |   | spotifyLogic.h  |
                           |   refreshToken)  |   |  poll loop      |
                           +------------------+   +-------+---------+
                                                          |
+-------------------+                                     v
| PN532 (optional)  |---SPI--+                  +---------+---------+
|  nfc.h            |        |                  |  spotifyDisplay   |
+-------------------+        |                  |  (interface)      |
                             |                  +----+---------+----+
                             |                       |         |
                             v                       v         v
                       +-----+---------+    +--------+--+ +----+--------+
                       | spotifyLogic  |    | cheapYellow| | matrixDisp  |
                       |  (play URI)   |    |  LCD       | | (HUB75)     |
                       +---------------+    +-----+------+ +-------------+
                                                  |
                                                  v
                                         +--------+--------+
                                         | TFT_eSPI / SPI  |
                                         | + JPEGDEC       |
                                         | + XPT2046 touch |
                                         +-----------------+
```

## Software Stack

| Layer            | Choice                                                                |
|------------------|-----------------------------------------------------------------------|
| Toolchain        | PlatformIO (`~/.platformio/penv/bin/pio`), env `cyd2usb`              |
| Platform         | `espressif32 @ 6.9.0` (Arduino-ESP32 2.0.17) — pinned                 |
| Framework        | Arduino                                                               |
| Spotify client   | `witnessmenow/spotify-api-arduino`                                    |
| JSON             | `bblanchon/ArduinoJson @ 6.x`                                         |
| Image decode     | `bitbank2/JPEGDEC @ 1.x`                                              |
| Provisioning     | `wnatth3/WiFiManager @ 2.0.16-rc.2` + `khoih-prog/ESP_DoubleResetDetector` |
| Display (CYD)    | `bodmer/TFT_eSPI @ 2.5.x` with full `User_Setup.h` baked into build_flags |
| Display (Matrix) | `mrfaptastic/ESP32-HUB75-MatrixPanel-I2S-DMA` + `Adafruit GFX`        |
| NFC (optional)   | `witnessmenow/Seeed_Arduino_NFC` fork                                 |

## Component Interfaces

The display layer is the only intentional abstraction in the codebase: `spotifyDisplay.h` defines the contract; concrete implementations are `cheapYellowLCD.h` (TFT_eSPI) and `matrixDisplay.h` (HUB75). Build-time `-DYELLOW_DISPLAY` / `-DMATRIX_DISPLAY` selects one.

`SpotifyArduino` is consumed directly — no wrapper.

## Data Flows

1. **Boot.** `setup()` mounts SPIFFS → `fetchConfigFile()` reads JSON into `clientId` / `clientSecret` / `refreshToken` globals → WiFiManager `autoConnect` (or captive portal if NVS empty / DRD fired) → `spotifySetup()` configures `SpotifyArduino` with creds → `spotifyRefreshToken()` exchanges refresh for access token.
2. **Steady state.** `loop()` calls `getCurrentlyPlaying` every N seconds. On track change: download JPEG → `JPEGDEC` decode → render via active `spotifyDisplay`. On 204: render idle screen.
3. **Touch.** `handleTouched()` polls XPT2046 each loop iteration; left/right thirds map to prev/next via `SpotifyArduino::previousTrack/nextTrack`.
4. **NFC (optional).** Tag scan reads URI string → `SpotifyArduino::playAdvanced` (or similar). If `writeContextToNfc` is set, currently-playing context is written back to the tag.

## Cross-cutting concerns

- **Auth bootstrap.** Spotify's redirect-URI policy (Apr 2025+) only accepts HTTPS or loopback HTTP. The device's LAN IP cannot be registered. Refresh tokens must be obtained off-device via `get_refresh_token.py` and baked into SPIFFS. The on-device `refreshToken.h` flow remains in source but is no longer reachable through dashboard-approved redirect URIs.
- **Persistence split.** Wifi creds live in NVS (managed by WiFiManager). Spotify creds live in SPIFFS. Each is preserved across firmware-only or SPIFFS-only flashes; only `pio run -t erase` wipes both.

---

# Target Architecture (esp_spotify Winamp extension)

> Per ADR-006: keep the Spotify-Diy-Thing baseline architecture. Change the UI; leave everything else.

## System Overview

The baseline firmware, with its display layer replaced by a Winamp 2 classic skin renderer and its touch layer extended to cover the full skin's controls. The device remains a Spotify Connect *controller* (no audio path on device): track metadata and playback position come from the Spotify Web API; control intents (play/pause, prev, next, seek, shuffle, repeat, volume) are sent back via the same API. A VU meter is rendered for visual fidelity to the Winamp aesthetic; it is synthesised from cached `audio-analysis` data, beat-aligned to the playing track (ADR-002).

There is **no PC mirror** and **no portable `core/` layer**. UI iteration happens on the DUT.

## Component Architecture

The baseline diagram (above) still applies. Changes are localised:

```
                       +---------------------+
                       |  Spotify Web API    |
                       +----------+----------+
                                  |  HTTPS
+-------------------+    +--------v---------+    +---------------------+
| WiFiManager (AP)  |--->| Wifi STA + DNS   |--->| SpotifyArduino      |
|  /config + DRD    |    +------------------+    |  (extended to cover |
+-------------------+                            |   seek, shuffle,    |
        |                                        |   repeat, volume,   |
        | first-boot only                        |   audio-analysis —  |
        v                                        |   see Open Qs)      |
+-------------------+      +------------------+  +---+----+------------+
|  NVS (wifi creds) |      | SPIFFS           |<-----+    |
+-------------------+      |  /spotify_diy_   |           |  track JSON
                           |  config.json     |           |  + analysis
                           |  + audio-analysis|           v
                           |  cache           |   +-------+---------+
                           +------------------+   | spotifyLogic.h  |
                                                  |  poll loop      |
                                                  |  + position     |
                                                  |    interpolation|
                                                  |  + VU module    |
+-------------------+                              +-------+---------+
| XPT2046 touch     |---SPI---+                            |
|  touchScreen.h    |         |                            v
|  (skin-region     |         |                   +--------+--------+
|   hit-testing)    |         +------------------>|  spotifyDisplay |
+-------------------+                             |  (interface)    |
                                                  +--------+--------+
                                                           |
                                                           v
                                                  +--------+--------+
                                                  | winampSkinLCD.h |
                                                  |  (TFT_eSPI +    |
                                                  |   baked atlas)  |
                                                  +-----------------+
```

What's new vs. baseline:

- **`winampSkinLCD.h`** — new concrete `spotifyDisplay` implementation. Renders the Winamp 2 classic skin against TFT_eSPI using a baked atlas + layout table (ADR-003). Replaces `cheapYellowLCD.h` for this project.
- **Skin-region hit-testing in `touchScreen.h`** — replaces the three-zone (prev / dead / next) mapping with per-button rects from the same baked layout table. Issues calls into the Spotify client for play/pause, prev, next, seek, shuffle, repeat, volume.
- **Position interpolation in `spotifyLogic.h`** — between ~1 Hz polls, the displayed position is computed as `progress_ms_at_last_poll + (millis() - last_poll_millis)`. On each poll, the API value is treated as truth; if the gap exceeds ~500 ms, snap rather than glide. Local seeks update both fields directly. (Survives from ADR-005; not its own ADR.)
- **VU module** — one new file, fed by an `audio-analysis` cache. Fetched once per track change and held in RAM (and optionally mirrored to SPIFFS for restart persistence; see Open Questions). Fallback chain per ADR-002: `audio-analysis` → `audio-features` → `off`.
- **Optimistic UI** — touch handlers flip the locally tracked play/pause / shuffle / repeat / volume / position immediately for visual feedback, then fire the API call. The next poll reconciles. (Survives from ADR-004; an implementation pattern, not a separate component.)

What's removed:

- **`matrixDisplay.h`** (HUB75 backend) — out of scope for the Winamp skin, not carried forward.

What's unchanged from baseline:

- Toolchain (`espressif32@6.9.0`, env `cyd2usb`, PlatformIO).
- Super-loop in `loop()`. No FreeRTOS task split.
- `SpotifyArduino` consumed directly. No `SpotifyTransport` wrapper.
- WiFiManager provisioning, NVS for WiFi creds, SPIFFS for Spotify creds.
- `get_refresh_token.py` host-side OAuth bootstrap.
- `spotifyDisplay.h` as the display seam.

## Software Stack

Identical to baseline (PlatformIO + Arduino-ESP32 + TFT_eSPI + JPEGDEC + WiFiManager + SpotifyArduino + ArduinoJson). No new libraries are mandated by the architecture; the `audio-analysis` fetch may use either an extension to `SpotifyArduino` or a small helper built on the existing `WiFiClientSecure` (Open Question).

Skin asset pipeline (per ADR-003): a host-side build-time tool emits `gen/skin_assets.c` (sprite atlas, RGB565) and `gen/skin_layout.h` (button rects, VU rect, text rects, slider tracks, 9-slice metadata) from the Winamp 2 classic skin. Run as a PlatformIO pre-build step or as a separate `make` target. No runtime parser on the device.

## Component Interfaces

`spotifyDisplay.h` is reused as-is and is the only architectural interface in scope. New display capabilities (VU rect render, slider state, button highlight) are added as methods on this interface; both `cheapYellowLCD.h` (if kept for fallback) and `winampSkinLCD.h` either implement them or stub them.

No IFCs are drafted in `interfaces/`. `Surface` / `Input` / `SpotifyTransport` / `Clock` / `Storage` from the superseded ADR-001 are not introduced.

## Data Flow

1. **Boot.** Same as baseline: SPIFFS mount → `fetchConfigFile()` → WiFiManager → `spotifySetup()` → `spotifyRefreshToken()`.
2. **Steady state.** `loop()` polls `getCurrentlyPlaying` via `spotifyTask` (FreeRTOS task, TASK-031) at a 5 s base cadence with exponential backoff. On track change: fetch album JPEG, decode, hand off to the active `spotifyDisplay`. Between polls, the seek bar and elapsed-time field advance via local millis-based interpolation (ADR-005).
3. **Touch.** `checkForInput()` polls XPT2046 each loop iteration; the touch coordinate is hit-tested against the baked button layout. Each button enqueues an action into `spotifyTask` (ADR-012). The local UI state is flipped immediately for visual feedback (ADR-004); the next poll reconciles. After `ACT_NEXT` / `ACT_PREV`, a 750 ms deferred speculative poll fires automatically (ADR-020).
4. **VU.** `vu::tick()` runs at 20 Hz. Drives a synthetic stereo envelope from `progressMs` + `is_playing` (ADR-009 option e — `audio-analysis` not available). Beat transient synthesised from a flat 120 BPM clock with per-track phase offset.
5. **NFC (optional).** Unchanged from baseline; gate with `NFC_ENABLED` (TASK-004 still open).

## Migration from baseline (delta)

- Add `winampSkinLCD.h` implementing `spotifyDisplay`; build `-DWINAMP_DISPLAY` (or rename the existing `-DYELLOW_DISPLAY` flag space).
- Add the host-side skin bake tool and the generated `gen/skin_assets.c` / `gen/skin_layout.h`.
- Extend `touchScreen.h` to consume the layout table and fire all controller intents.
- Add a synthetic VU module driven by `currentlyPlaying` envelope (ADR-009 option e — `audio-analysis` not available).
- Add position interpolation in the existing poll loop.
- Drop `matrixDisplay.h` and its build env from scope.
- Everything else: keep.

---

# Open Questions

Cross-cutting questions across both states. Items marked **(baseline)** apply to current firmware; **(target)** apply to the Winamp extension; unmarked apply to both.

- **(target)** `SpotifyArduino` extension strategy — the library covers `getCurrentlyPlaying`, `previousTrack`, `nextTrack`, and exposes (unwired) `seek`. It does not cover `audio-analysis`, `audio-features`, shuffle/repeat toggles, or volume. Options: extend the library upstream, fork, or add small helpers using the existing `WiFiClientSecure`. No PC mirror means no portability constraint on this choice.
- **(target)** WiFi + TLS root CA strategy for `accounts.spotify.com` and `api.spotify.com` — **closed ADR-019** (2026-05-16): keep two hardcoded DigiCert Global Root CA G2 PEMs; no change needed; cert expires 2038.
- **(target)** `audio-analysis` cache size and eviction — closed. M6 went synthetic (ADR-009 option e); no analysis fetch.
- **(target)** `audio-analysis` cache miss UX — closed. Same as above.
- **(target)** Skin atlas pixel format — closed. RGB565 confirmed; flash budget resolved via ADR-014 + TASK-035.
- **(target)** Seek-bar drag UX — **closed M7** (2026-05-16): snap posbar to finger during drag, freeze interpolation, fire seek on release. Impl in `touchScreen.h` / `spotifyDisplay`.
- **(target)** Position snap threshold — 500 ms is the starting value (survives ADR-005); tune once real network jitter is measured.
- **(target)** Spotify rate-limiting headroom — **closed ADR-020** (2026-05-16): speculative 750 ms post-poll after `ACT_NEXT`/`ACT_PREV` only; not for other actions.
- **(baseline / target)** Touch UX gesture model on a 320×240 panel given more controls (play/pause, volume, seek, shuffle, repeat). See TASK-002, TASK-003.
- **(baseline)** NFC: keep, gate behind a build flag, or remove? See TASK-004. **(target)** carries the same question; if dropped, NFC code is removed in the migration.
- **(baseline)** Secret hygiene: `data/spotify_diy_config.json` must be gitignored once this directory becomes a git repo. See TASK-005.
