# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@docs/agents/AGENTS.md

## Workspace layout

This directory contains two **independent, unrelated** upstream projects (each its own git repo):

- `cspot/` — [feelfreelinux/cspot](https://github.com/feelfreelinux/cspot). C++ Spotify Connect player library targeting ESP32 and desktop (CLI). Uses CMake / esp-idf.
- `Spotify-Diy-Thing/` — [witnessmenow/Spotify-Diy-Thing](https://github.com/witnessmenow/Spotify-Diy-Thing). Arduino/PlatformIO ESP32 project that displays the currently-playing track via the Spotify Web API on a "Cheap Yellow Display" or HUB75 matrix panel. Does **not** depend on cspot.

Treat each subdirectory as a separate project. Don't cross-reference code between them.

---

## cspot/

C++ Spotify Connect implementation. Library code lives in `cspot/cspot/` (with bundled `bell` audio framework as a submodule under `cspot/cspot/bell`). Two build targets under `cspot/targets/`:

- `cli/` — desktop player (Linux/macOS/Windows), built with CMake. Used for development/testing.
- `esp32/` — ESP32 firmware, built with esp-idf.

Submodules are required: clone with `--recursive` or run `git submodule update --init --recursive` after pulling.

### Build — CLI (Linux)

```sh
cd cspot/targets/cli
mkdir -p build && cd build
cmake .. -DUSE_ALSA=ON          # or -DUSE_PORTAUDIO=ON on macOS
make
./cspotcli                       # ZeroConf-advertises by default
```

Optional CMake flags: `-DBELL_EXTERNAL_MBEDTLS=<mbedtls_build>/cmake` and `-DMBEDTLS_RELEASE=<name>` for a local mbedtls build instead of system-wide.

Linux deps: `libavahi-compat-libdnssd-dev`, `libasound2-dev`, mbedtls, protoc, Python `protobuf` + `grpcio-tools` (nanopb codegen).

A Nix `flake.nix` is provided at the cspot root for a reproducible dev shell.

### Build — ESP32

```sh
# After sourcing esp-idf's export.sh
pip3 install protobuf grpcio-tools     # into esp-idf's venv
cd cspot/targets/esp32
idf.py set-target esp32                # once per checkout
idf.py menuconfig                      # set wifi + CSPOT Configuration
idf.py build flash monitor
```

### Architecture

`cspot` is a **library**: the embedding program supplies an `AudioSink` (see `cspot/cspot/include/AudioSink.h`) that consumes 16-bit / 44.1 kHz stereo PCM and optionally implements `volumeChanged()` for hardware volume. Auth-blob caching is also the embedder's job (see `targets/cli/main.cpp` and its `authBlob.json` for reference).

Connection flow (key files in `cspot/cspot/src/`):

1. `ApResolve.cpp` fetches an access point from `apresolve.spotify.com`.
2. `PlainConnection.cpp` opens a TCP connection; `ShannonConnection.cpp` (+ `Shannon.cpp`, `AuthChallenges.cpp`) upgrades it to the encrypted Shannon stream.
3. `Session.cpp` / `MercurySession.cpp` handle the Mercury pub/sub protocol on top.
4. `SpircHandler.cpp` implements Spotify Connect control (play/pause/next/volume) via Mercury.
5. `TrackQueue.cpp` / `TrackReference.cpp` / `TrackPlayer.cpp` resolve tracks, fetch encrypted audio (`CDNAudioFile.cpp`), decrypt and decode (Vorbis via `bell`), and feed PCM into the user-supplied `AudioSink`.
6. `LoginBlob.cpp` handles ZeroConf-style local auth + credential persistence.

Wire formats are nanopb-generated from `cspot/cspot/protobuf/*.proto` at configure time.

Audio sinks live in the `bell` submodule under `cspot/cspot/bell/src/sinks/{unix,esp}/`. Add a new sink by subclassing `AudioSink` and implementing `feedPCMFrames`.

---

## Spotify-Diy-Thing/

Arduino sketch (`SpotifyDiyThing/SpotifyDiyThing.ino`) that polls the Spotify Web API over HTTPS and renders the currently-playing track + album art. **Not** related to cspot — it does not act as a Spotify Connect endpoint.

### This machine's setup

- **PlatformIO is not on PATH.** Use `~/.platformio/penv/bin/pio` (alias `pio` if you want).
- **Board:** ESP32-2432S028R "Cheap Yellow Display", **two-USB variant** — production target is `cyd2usb_winamp`; requires `-DTFT_INVERSION_ON` (inherited from `cyd2usb` base). The plain `cyd` env produces inverted colors on this hardware.
- **Serial port:** `/dev/ttyUSB0`, CH340 (USB VID:PID `1A86:7523`).
- **Platform pin:** `platformio.ini` pins `platform = espressif32@6.9.0` (Arduino-ESP32 2.0.17). The repo's original unpinned line broke against current PlatformIO because the bundled WiFi lib in newer cores expects `Network.h`, which the install didn't ship. Don't bump above 6.9.x without checking the WiFi/Network split.

### Run scripts (use these — do not issue raw pio/tmux commands)

All build, flash, monitor, and test operations have named scripts in `run/`. Always use these instead of raw `pio` or `tmux` commands — the scripts handle port resolution, monitor lifecycle, and DUT safety automatically.

```sh
./run/port                    # resolve + print CH340 serial port
./run/build                   # compile production firmware
./run/build-debug             # compile debug firmware
./run/flash                   # flash production (kills + restores monitor)
./run/flash-debug             # flash debug firmware (monitor stays down for test harness)
./run/flash-fs                # upload SPIFFS only
./run/monitor-start           # start tmux serial monitor
./run/monitor-stop            # kill monitor (idempotent)
./run/monitor-read [N]        # dump last N lines (default 200)
./run/test                    # full DUT validation loop (BP-020, trap-guarded)
./run/test-targeted T1,T2     # targeted loop for a specific feature
./run/test-smoke              # smoke preset < 2 min
./run/test-sync               # sync/drift/playlist suite T097-T116 (requires DUT)
./run/check                   # 5-gate build check (check_build.sh)
./run/bake-skin               # bake Winamp skin assets
```

Full reference: `docs/process/project_run_scripts.md`. Rationale and failure modes: `docs/process/dut_workflow.md`.

Port is resolved automatically by VID:PID. Override: `PORT=/dev/ttyUSB1 ./run/flash`.

Other envs in `platformio.ini` (don't use on this board): `cyd` (single-USB CYD, inversion off), `trinity` (HUB75 matrix). Env selects display via `-DYELLOW_DISPLAY` vs `-DMATRIX_DISPLAY`. The `cyd*` envs bake the full TFT_eSPI `User_Setup.h` into `build_flags` — the library's bundled User_Setup is ignored.

`platformio.ini` keeps `lib_ldf_mode = deep+` because `Seeed_Arduino_NFC` needs conditional includes resolved.

### Build check (run before/after structural changes)

```sh
./run/check   # 5 gates: cyd2usb_winamp, cyd2usb_winamp_debug, golden.sha256, smoke, app registry
```

Exit 0 = all pass. Minimum safety gate before committing structural changes (see BP-008).

### Skin asset bake (M2)

Host-side bake of `skins/base-2.91.wsz` → `app/gen/skin_assets.c` + `skin_layout.h`. Run on demand (not a PIO pre-build hook):

```sh
./run/bake-skin
# determinism check (T025): re-bake should be byte-identical to committed gen/
cd app/gen && sha256sum -c golden.sha256
```

Deps: `python3-pillow` and **ImageMagick CLI** (`magick` on PATH). Pillow's `BI_RLE8` BMP decoder fails on Winamp's `TEXT.BMP`; the tool shells out to `magick` as a fallback. Without ImageMagick the font atlas step raises. See ADR-008.

### Python venv

**Project venv:** `~/proj/esp/venv` (this machine) — used for all host-side Python tools, invoked automatically by `run/` scripts. Override with `VENV_PY=/path/to/python3`. Direct invocation when needed:

```sh
python3 app/tools/preview_layout.py ...
```

Installed packages: `Pillow`, `numpy`, `pygame`, `pyserial`.

### Serial monitor via tmux

Use `./run/monitor-start`, `./run/monitor-stop`, `./run/monitor-read`. The monitor holds the port exclusively — all `run/flash*` and `run/test*` scripts kill it automatically before using the port and restart it afterward.

`Ctrl-C` inside the pane kills the whole session (it's the only process); recreate with `tmux new-session` after upload.

### Runtime configuration

Two persistence layers, both survive reflashing the firmware partition:

- **Wifi creds** — written by WiFiManager into ESP32 NVS (separate partition).
- **Spotify creds + refresh token** — JSON at `/spotify_diy_config.json` on SPIFFS. Schema (see `configFile.h`):
  ```json
  { "refreshToken": "...", "clientId": "...", "clientSecret": "..." }
  ```
  Keys are `clientId`/`clientSecret`, lowercase 'd'. The WiFiManager param labels (`WM_CLIENT_ID_LABEL = "clientID"` etc., `WifiManagerHandler.h:9`) differ but are only used as form-field IDs.

Two ways to populate the config:

1. **Captive portal (interactive).** First boot or double-press reset within ~10s (`DoubleResetDetector`, `DRD_TIMEOUT=10`, SPIFFS-backed via `ESP_DRD_USE_SPIFFS=true`). Phone joins SSID `SpotifyDIY` / pw `thing123`. **Must use the "Configure WiFi" page**, not "Info" — only the configure page exposes the Client ID / Secret / Refresh Token text fields. If you save from the wifi-only page, those fields are written as empty strings and the OAuth URL renders with `client_id=` blank.

2. **Pre-baked SPIFFS image (preferred when reflashing dev boards).** Put a fully-filled `Spotify-Diy-Thing/data/spotify_diy_config.json` (also accessible as `app/data/spotify_diy_config.json` via symlink) and run `pio run -e cyd2usb_winamp -t uploadfs` from `app/`. Bypasses the portal entirely — wifi must still be configured separately the first time, but creds + refresh token are already there.

After SPIFFS has client ID + secret but no refresh token, the device enters "Refresh Token Mode" and serves a small auth-helper page on its LAN IP (`refreshToken.h`).

### Spotify redirect-URI policy (important)

As of Apr 2025 (all apps by Nov 2025), Spotify only accepts redirect URIs that are HTTPS, **except** loopback HTTP: `http://127.0.0.1:PORT/...` or `http://[::1]:PORT/...`. `localhost` and LAN IPs (`http://192.168.x.x/...`) are rejected at dashboard save time. The device's built-in flow uses its LAN IP, so it cannot complete the dashboard side anymore.

Workaround used here: `get_refresh_token.py` (repo root) runs the Authorization Code flow on the host using `http://127.0.0.1:8888/callback/` (must be added to the Spotify app's Redirect URIs), prints the refresh token. Bake that into `Spotify-Diy-Thing/data/spotify_diy_config.json` and run `uploadfs` from `app/`.

### Hardcoded station WiFi (bypass captive portal)

`Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h` (gitignored) opt-in shim. If present, `WifiManagerHandler.h` sees it via `__has_include` and short-circuits to `WiFi.begin(SSID, PASS)` before falling back to the portal. Format:

```c
#define HARDCODED_WIFI_SSID "..."
#define HARDCODED_WIFI_PASS "..."
```

Reflash app to apply (creds compile in). On connect timeout (30s) it falls through to the normal WiFiManager portal flow.


### Touch input (CYD)

`touchScreen.h:46-53` only recognizes two zones, hardcoded:
- `x < 120` → previous track
- `x > 200` → next track
- `120 ≤ x ≤ 200` is dead — the seek bar in the UI is **display-only**.

No play/pause, volume, or seek/scrub. `SpotifyArduino::seek()` exists but is not wired up.

### NFC

PN532 detection runs unconditionally in `setup()` (`NFC_ENABLED` in the .ino). On hardware without the reader wired up, expect `Didn't find PN53x board` / `NFC reader - not working!!!` / `NFC Bad` in the boot log — non-fatal, the device continues normally. Set `NFC_ENABLED 0` to skip the probe.

### Code layout

**Our firmware** (`app/src/`):
- `main.cpp` — app shell entry point (was `SpotifyDiyThing.ino`).
- `winamp/winampDisplay.h`, `winamp/vuMeter.h` — Winamp skin renderer.
- `appShell.h` — app registry, `switchApp()`, tick/input dispatch (M-MULTIAPP stub).
- `taskbar/taskbar.h` — taskbar renderer stub (M-MULTIAPP).
- `screenLog.h` — full-screen log overlay (SCREEN_LOG env).
- `spotifyTask.h` / `spotifyTaskStorage.cpp` — async Spotify HTTP FreeRTOS task.
- `logSink.h` / `logSinkStorage.cpp`, `logHeartbeat.h`, `logDecode.h`, `logServer.h` — logging stack.
- `perf.h`, `secret.h`, `serialPrint.h` — utilities.

**Upstream files** (`Spotify-Diy-Thing/SpotifyDiyThing/`, included via `lib_extra_dirs`):
- `spotifyLogic.h` — Spotify API call + state-machine logic.
- `spotifyDisplay.h` — display abstraction (superseded by app shell; kept for upstream compat).
- `cheapYellowLCD.h` / `matrixDisplay.h` — concrete display backends (cheapYellowLCD.h has PATCH-001).
- `nfc.h` — optional PN532 NFC reader; tags carry Spotify URIs/URLs that get played on swipe. Set `NFC_ENABLED 0` in the `.ino` to disable. `writeContextToNfc` toggles writing the currently-playing context back to a tag (off for albums that auto-flow into related songs).
- `touchScreen.h` / `CYD28_TouchscreenR.{h,cpp}` — CYD touch input (rotated coordinates).
- `configFile.h` — SPIFFS-backed persisted config.
- `WifiManagerHandler.h`, `refreshToken.h` — first-run setup flow described above.

`GitHubPages/` hosts the ESPWebTools browser flasher (Chrome/Edge) — a build artifact deployment target, not part of firmware.
