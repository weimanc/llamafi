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

## System Overview

Extends the baseline into a Spotify Connect *controller* (no audio path on device) presenting a Winamp 2 classic skin UI on the same CYD hardware. Controls exposed via touch: play/pause, previous, next, seek, shuffle, repeat, volume. Track metadata and playback position read from the Spotify Web API. A VU meter is rendered for visual fidelity to the Winamp aesthetic; it is synthesised from cached `audio-analysis` data, beat-aligned to the playing track (ADR-002).

A PC-side mirror of the UI is a first-class build target alongside the device firmware (ADR-001).

## Component Architecture

Layered architecture per ADR-001: a portable `core/` plus per-target `platform/` leaves.

**Core (portable):**

- `PlayerState` — single canonical model (see Data Flows below). Fields: track metadata (id, title, artist, album, duration_ms), `position_ms`, `last_poll_clock_ms`, `is_playing`, `shuffle`, `repeat`, `volume_pct`, VU ring buffer (stereo), `vu.source`, `conn`, `last_error`. Concurrency rules per ADR-005.
- `Poller` — periodic `GET /me/player` reads → `PlayerState` updates.
- `Interpolator` — advances `position_ms` between polls against `Clock`; resyncs on poll with a 500 ms snap threshold (ADR-005).
- `VuSynth` — drives the stereo VU ring buffer from cached `audio-analysis` for the current track; falls back to `audio-features` or `off` when analysis is unavailable (ADR-002).
- `IntentHandler` — translates UI intents into Spotify commands; applies optimistic local mutations and reconciles on the next poll (ADR-004).
- `Renderer` — pure function over `PlayerState` + baked skin layout, emitting draw commands against `Surface`.

**Platform leaves (per target):**

- `Surface` — pixel/sprite blit primitives. DUT: TFT_eSPI on the CYD's 320×240 ILI9341 (per baseline). PC mirror: SDL2 (or equivalent) at native skin resolution.
- `Input` — emits `Intent` values. DUT: XPT2046 resistive touch (per baseline). PC mirror: mouse mapped to touch coordinates.
- `SpotifyTransport` — HTTPS request/response, OAuth refresh. DUT: on-device TLS (continuing the baseline's `WiFiClientSecure` + `SpotifyArduino` foundation, or replacing it — TBD). PC mirror: real HTTPS, or a mock transport replaying canned JSON fixtures.
- `Clock` — monotonic milliseconds.
- `Storage` — persistent key/value for OAuth refresh token and per-track `audio-analysis` cache. DUT: SPIFFS (continuing baseline). PC mirror: local file.

Dependency direction: `core/` depends only on the abstract leaf interfaces. Leaves do not call each other.

## Software Stack

Inherits the baseline's Arduino + PlatformIO + TFT_eSPI + SPIFFS toolchain on the DUT side. Build targets: `make pc` and `pio run -e cyd2usb` (or equivalent) compile the same `core/` sources against different `platform/` implementations.

Skin asset pipeline (proposed under ADR-003): a host-side build-time tool emits `gen/skin_assets.c` (sprite atlas, RGB565 to match TFT_eSPI's native format) and `gen/skin_layout.h` (button rects, VU rect, text rects, 9-slice metadata) from the Winamp 2 classic skin. No runtime parser on the device.

The baseline's `SpotifyArduino` library covers `getCurrentlyPlaying`, `previousTrack`, `nextTrack`, and exposes (unwired) `seek`. It does not cover `audio-analysis` or `audio-features` endpoints, nor shuffle/repeat toggles. Decision pending: extend `SpotifyArduino`, fork it, or write a thinner client purpose-built for the controller.

## Component Interfaces

The baseline's `spotifyDisplay.h` interface is superseded by the new `Surface` leaf in the target architecture; the HUB75 matrix backend (`matrixDisplay.h`) is out of scope for the Winamp skin and not carried forward.

IFCs to be drafted (in `interfaces/`): `Surface`, `Input`, `SpotifyTransport`, `Clock`, `Storage`, plus the Spotify Web API client contract used by `Poller` and `IntentHandler`.

## Data Flows

```
Spotify Web API ──poll──► Poller ──► PlayerState ◄── Interpolator ◄── Clock
                                          │
                              VuSynth ────┤  (audio-analysis cache, ADR-002)
                                          │
Touch / Mouse ──► Input ──► Intent ──► IntentHandler ──► Spotify Web API
                                          │                    │
                                          └──optimistic────────┘  (ADR-004)
                                          │
                                          ▼
                                       Renderer ──► Surface (CYD LCD | SDL)
```

Tasking sketch (final cadences subject to DUT validation):

| Task         | Period   | Job                                                  |
|--------------|----------|------------------------------------------------------|
| Poller       | 1000 ms  | `GET /me/player` → `PlayerState`                     |
| Interpolator | 50 ms    | advance `position_ms` from `Clock`                   |
| VuSynth      | 50 ms    | drive VU buffer from cached `audio-analysis`         |
| Renderer     | 33 ms    | dirty-rect blit                                      |
| Input        | 20 ms    | poll XPT2046 / mouse, emit intents                   |
| IntentHandler| event    | optimistic mutation + API call                       |

## Migration from baseline

- Keeps: `WiFiManager` provisioning, NVS+SPIFFS persistence split, `get_refresh_token.py` host-side OAuth bootstrap, CYD board (env `cyd2usb`).
- Replaces: single-display abstraction → `Surface` leaf; coarse three-zone touch → full skin-region hit-testing in `Input`; direct `SpotifyArduino` use → `SpotifyTransport` leaf wrapping it (or successor).
- Drops from scope: HUB75 matrix display backend, NFC tap-to-play (decision pending — see Open Questions).
- Adds: `core/` portable layer, PC mirror build target, baked skin atlas, VU synthesis from `audio-analysis`.

---

# Open Questions

Cross-cutting questions across both states. Items marked **(baseline)** apply to current firmware; **(target)** apply to the Winamp extension; unmarked apply to both.

- **(target)** Spotify-Diy-Thing fork URL — the baseline uses `witnessmenow/spotify-api-arduino`. For the target, do we extend that library to cover `audio-analysis`, `audio-features`, shuffle/repeat, and seek-debouncing — or build a thinner replacement client?
- **(target)** WiFi + TLS root CA strategy for `accounts.spotify.com` and `api.spotify.com` — pin or trust-store?
- **(target)** `audio-analysis` cache size and eviction — per-track JSON ~30–80 KB; LRU keyed by track id, sized to N most-recent. Need a value for N given remaining flash after baseline + skin atlas.
- **(target)** `audio-analysis` cache miss UX — momentary VU "off" on track change while analysis is fetched; acceptable, or worth a placeholder envelope?
- **(target)** Skin atlas pixel format — RGB565 is the proposed default to match TFT_eSPI; confirm against flash budget once atlas size is known.
- **(target)** Tasking model on DUT — Arduino `loop()` super-loop (continuing baseline) vs migrate to FreeRTOS tasks. Affects render pacing and poll/render decoupling.
- **(target)** Seek-bar drag UX — debounce-on-release is decided (ADR-004); open is the visual treatment of position during drag (snap to finger immediately, freeze interpolator until release).
- **(target)** Position snap threshold — 500 ms is the starting value (ADR-005); tune once real network jitter is measured.
- **(target)** Spotify rate-limiting headroom — how aggressively the speculative-poll refinement (ADR-004 option c) can be used without bumping the ~180 req/min ceiling.
- **(baseline / target)** Touch UX gesture model on a 320×240 panel given more controls (play/pause, volume, seek, shuffle, repeat). See TASK-002, TASK-003.
- **(baseline)** NFC: keep, gate behind a build flag, or remove? See TASK-004. **(target)** carries the same question; if dropped, NFC code is removed in the migration.
- **(baseline)** Secret hygiene: `data/spotify_diy_config.json` must be gitignored once this directory becomes a git repo. See TASK-005.
