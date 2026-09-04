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

- **The board is pinned to the debug build** while TASK-557 is open. Human ruling, 2026-09-03: the
  pin forbids **restoring production**; rebuilding and flashing *the same debug env* is fine
  provided `-DBOD_WATCH` survives. `run/test` and `run/test-targeted` restore production from an
  EXIT trap, so they cannot be run as-is — `DUT_NO_RESTORE=1` is a dated interim exception, retired
  when TASK-633 converts the entry points to verify-and-refuse.
- **PlatformIO is not on PATH.** Use `~/.platformio/penv/bin/pio` (alias `pio` if you want).
- **Board:** ESP32-2432S028R "Cheap Yellow Display", **two-USB variant** — production target is `cyd2usb_winamp`; requires `-DTFT_INVERSION_ON` (inherited from `cyd2usb` base). The plain `cyd` env produces inverted colors on this hardware.
- **Serial port:** `/dev/ttyUSB0`, CH340 (USB VID:PID `1A86:7523`).
- **Platform pin:** `platformio.ini` pins `platform = espressif32@6.9.0` (Arduino-ESP32 2.0.17). The repo's original unpinned line broke against current PlatformIO because the bundled WiFi lib in newer cores expects `Network.h`, which the install didn't ship. Don't bump above 6.9.x without checking the WiFi/Network split. **A bump also drops PATCH-SD-1** — the
framework `SD` library is vendored into `app/lib/SD/` and patched so SDHC cards are typed correctly
(without it a 32 GB card fails to mount with "no valid FAT volume"). Re-copy and re-apply per
`app/lib/SD/LOCAL_PATCHES.md`. **And PATCH-TLS-1** — `app/lib/WiFiClientSecure/` is vendored too, and
patched so `stop()` releases its socket with `lwip_close()` rather than the VFS `close()`; without it
`stop()` on lwIP socket 0 closes VFS fd 0, which is whatever file the firmware opened first
(TASK-424). See `app/lib/WiFiClientSecure/LOCAL_PATCHES.md`.

### Run scripts (use these — do not issue raw pio/tmux commands)

All build, flash, monitor, and test operations have named scripts in `run/`. Always use these instead of raw `pio` or `tmux` commands — the scripts handle port resolution, monitor lifecycle, and DUT safety automatically.

```sh
./run/lib.sh                   # shared helpers sourced by all run/* scripts — not executed directly
./run/port                    # resolve + print CH340 serial port
./run/build                   # compile production firmware
./run/build-debug             # compile debug firmware
./run/setup                   # first-time setup wizard (WiFi + Spotify credentials)
./run/flash                   # flash production (kills + restores monitor)
./run/flash-debug             # flash debug firmware (monitor stays down for test harness)
./run/flash-player             # flash cyd2usb_player variant (TASK-427/431); monitor not restarted
./run/flash-webradio           # flash cyd2usb_webradio (-DDISABLE_SPOTIFY -DWEBRADIO_ONLY); monitor not restarted
./run/flash-fs                 # upload SPIFFS — full format/rewrite (destructive; use run/spiffs push instead)
./run/spiffs ls               # list files on device
./run/spiffs pull [file]      # extract all → app/data/spiffs-dump/, or single file → stdout
./run/spiffs push [file]      # write single file or merge app/data/ (non-destructive, no format)
./run/spiffs rm <file>        # remove single file from device
./run/monitor-start           # start tmux serial monitor
./run/monitor-stop            # kill monitor (idempotent)
./run/monitor-read [N]        # dump last N lines (default 200)
./run/dut-health              # PRE-FLIGHT ONLY: HEALTH class T_DH_01-03 — is this board fit
                               #   to test now? exit 0/4. ~15 s typical, up to ~60 s on a
                               #   degraded boot (its own port open RESETS the board, so the
                               #   boot is part of the price). Needs debug firmware already
                               #   flashed; it does not flash. NEVER as a post-mortem: the
                               #   reset destroys the wedge you were diagnosing (TASK-426) —
                               #   read run/monitor-read FIRST. (TASK-565, M-TESTARCH §5 E4)
./run/test                    # full DUT validation loop (BP-020, trap-guarded)
./run/test-targeted T1,T2     # targeted loop for a specific feature
./run/test-targeted --scope X # targeted loop by SCOPE — an app name, one of
                              # shell|boot|taskbar|spotify-chrome|rig, or the PATH of
                              # the file you changed (TASK-570)
./run/test-smoke              # smoke preset < 2 min
./run/test-sync               # sync/drift/playlist suite T097-T116 (requires DUT)
./run/browser-player           # directory-browse + real playback test on cyd2usb_player (TASK-416/T_PLR_13)
./run/playorder-player         # auto-advance playback across 5 tracks on cyd2usb_player (TASK-418/T_PLR_25)
./run/player-gate              # M-TESTBASE phase-1 player gate, two-leg ordered regression run (TASK-519)
./run/wr-gate [trials]         # ADR-045 MVP exit-criterion gate for M-WEBRADIO close (TASK-238)
./run/pr-fetch-soak [min]      # PlaneRadar fetch-failure-rate soak by payload size (TASK-361)
./run/stress [min]            # multi-app fetch stress/soak (TASK-248; flash debug → soak → restore prod)
./run/wr-soak [min]           # WebRadio playback + A-lite arena-churn soak (TASK-271; flash webradio build → soak → restore prod)
./run/ae04 [cycles]           # T_AE_04 audio-engine teardown ordering, eject mid-CONNECTING (TASK-409; flash webradio build → test → restore prod)
./run/task488 [ids]           # T_488_04-11 refactor verification (TASK-488; DUT_TREE=<worktree> flashes another checkout for an A/B)
./run/pr-soak [min]           # PlaneRadar + Spotify coexistence soak (TASK-307; flash debug → soak → restore prod)
./run/audit-origin [--grep-only] # origin-relative render/hit-test audit (TASK-082/251)
./run/screendump               # pull an exact DUT screenshot via SERIAL_DEBUG (requires debug firmware)
./run/check                   # 11-gate build check (check_build.sh)
./run/check-docs               # documentation staleness gate (TASK-475, M-DOCLIFE phase 1)
./run/check-datatask-certs     # dataTask TLS chain preflight, offline chain-build verify (ADR-029)
./run/check-teletext-api       # NOS Teletekst API stability canary
./run/bake-skin               # bake Winamp skin assets
./run/bake-airports            # bake OurAirports runway DB for M-PLANERADAR (ADR-049)
./run/bake-icons               # bake app/icons/taskbar/*.png -> app/gen/taskbar_icons.{cpp,h}
```

**Selecting tests by what you changed** (TASK-570, [M-TESTARCH](docs/architecture/designs/M-TESTARCH-precedence-hierarchy.md) §13.4).
You do not need to read `test_plan.md` or grep the suite for an id list. Every
test carries a `scope`, so the file you edited resolves to its ids in one command:

```sh
./run/test-targeted --scope app/src/apps/localPlayerApp.cpp   # -> LocalPlayer -> 29 ids
./run/test-targeted --scope LocalPlayer                       # the same set, named directly
./run/test-targeted --scope taskbar                           # a non-app scope
SCOPE=Stock ./run/test-targeted T169,T170                     # both -> intersection
```

Scope names are **case-sensitive**: `Spotify` is the app, `spotify-chrome` is the
shell's Spotify plumbing, and `spotify` is not a scope at all. `--class`/`--upto`
were cut at review and deliberately do not exist (design §20).

Full reference: `docs/process/project_run_scripts.md`. Rationale and failure modes: `docs/process/dut_workflow.md`.

Port is resolved automatically by VID:PID. Override: `PORT=/dev/ttyUSB1 ./run/flash`.

Other envs (don't use on this board): `cyd` (single-USB CYD, inversion off), `trinity` (HUB75 matrix). These live in `Spotify-Diy-Thing/platformio.ini` (the separate upstream project) — not `app/platformio.ini`, which has no `cyd`/`trinity` envs. Env selects display via `-DYELLOW_DISPLAY` vs `-DMATRIX_DISPLAY`. The `cyd*` envs bake the full TFT_eSPI `User_Setup.h` into `build_flags` — the library's bundled User_Setup is ignored.

`platformio.ini` keeps `lib_ldf_mode = deep+` because `Seeed_Arduino_NFC` needs conditional includes resolved.

### Build check (run before/after structural changes)

```sh
./run/check   # 11 gates: full env matrix (cyd2usb_winamp, cyd2usb_winamp_debug, cyd2usb_player,
              # cyd2usb_winamp_screenlog, cyd2usb_webradio, cyd2usb_winamp_debug_noSpotify —
              # every buildable env in app/platformio.ini; [env:cyd2usb] excluded — demoted to
              # non-building [cyd2usb_base] per ADR-061 D8/TASK-467, that base section itself
              # later deleted per ADR-061 D9/TASK-470 once cheapYellowLCD.h had no dependents
              # left; cyd2usb_webradio_16k retired per TASK-531, EXP-012 closed with a negative
              # verdict), golden.sha256,
              # smoke, app-registry staleness, mem_layout staleness+budget, check-docs
              # documentation gate (+ one warn-only settings-wiring gate, not counted)
```

The **counted gate total is 11 and does not move when a host check is added** — every host-side
gate on this project lives inside gate 8, `app/tools/smoke_test.sh`, which now runs **17 host
scripts** — 7 checkers and 10 negative suites, five of the checkers paired with their own suite
(BP-068). The three added by M-HARNESS2 Phase 1, each with its negative suite:

| check | asserts | landed |
|---|---|---|
| `gate/check_import_safety.py` | no module under `app/tools/` opens a port, resolves one, hangs or resets the board **at import** — six DUT scripts used to run their whole suite at module level (TASK-609/R48) | at zero |
| `gate/check_get_keys.py` | `gen/gen_get_keys.py` reads every `dbgGet` body in the tree; its glob and its definition regex between them saw 43 of 111 keys (TASK-600/R7) | at zero |
| `gate/check_flake_class.py` | no RIG/HEALTH/CORE id carries a `flaky.yaml` declaration — a gating id whose retry resolves `FLAKY-PASS` can never set the blocker its class exists to set (TASK-623/R37) | blocking, one dated ledger row (`docs/verification/flake_class_exceptions.md`) |

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
python3 app/tools/preview/preview_layout.py ...
```

Installed packages: `Pillow`, `numpy`, `pygame`, `pyserial`.

### Serial monitor via tmux

Use `./run/monitor-start`, `./run/monitor-stop`, `./run/monitor-read`. The monitor holds the port exclusively — all `run/flash*` and `run/test*` scripts kill it automatically before using the port and restart it afterward.

`Ctrl-C` inside the pane kills the whole session (it's the only process); recreate with `tmux new-session` after upload.

### Runtime configuration

Two persistence layers, both survive reflashing the firmware partition:

- **Wifi creds** — written by `WiFi.begin()` into ESP32 NVS (separate partition) on intentional user connect via the on-device WiFi settings UI (`wifiSection.h`). Also readable from SPIFFS `/wifi_creds.json` (written by `./run/setup`).
- **Spotify creds + refresh token** — JSON at `/spotify_diy_config.json` on SPIFFS. Schema (see `configFile.h`):
  ```json
  { "refreshToken": "...", "clientId": "...", "clientSecret": "..." }
  ```
  Keys are `clientId`/`clientSecret`, lowercase 'd'.

Three ways to populate the config:

1. **`./run/setup` wizard (primary path).** Interactive wizard handles WiFi credentials and Spotify OAuth, writes `app/data/wifi_creds.json` and `app/data/spotify_diy_config.json`, and offers `./run/spiffs push` at the end. See `README.md` step 4.

2. **Pre-baked SPIFFS files (preferred for dev boards / scripted re-auth).** Put a fully-filled `app/data/spotify_diy_config.json` and/or `app/data/wifi_creds.json` and run `./run/spiffs push`. Bypasses the portal entirely.

3. **On-device WiFi settings UI (interactive fallback).** If no credentials are found at boot, the device opens the WiFi Settings screen automatically. Use the on-screen keyboard to enter SSID and password. No captive portal or external phone required.

After SPIFFS has client ID + secret but no refresh token, the device enters "Refresh Token Mode" and serves a small auth-helper page on its LAN IP (`refreshToken.h`).

### Spotify redirect-URI policy (important)

As of Apr 2025 (all apps by Nov 2025), Spotify only accepts redirect URIs that are HTTPS, **except** loopback HTTP: `http://127.0.0.1:PORT/...` or `http://[::1]:PORT/...`. `localhost` and LAN IPs (`http://192.168.x.x/...`) are rejected at dashboard save time. The device's built-in flow uses its LAN IP, so it cannot complete the dashboard side anymore.

Workaround used here: `get_refresh_token.py` (repo root) runs the Authorization Code flow on the host using `http://127.0.0.1:8888/callback/` (must be added to the Spotify app's Redirect URIs), prints the refresh token. Bake that into `app/data/spotify_diy_config.json` and run `./run/spiffs push spotify_diy_config.json`.

### WiFi boot fallback chain

Priority: NVS (saved by prior user connect) → SPIFFS `/wifi_creds.json` (written by `./run/setup`) → WiFi settings UI on device. Each level falls through to the next on timeout or missing file. Between the NVS and SPIFFS attempts, `main.cpp` explicitly disables auto-reconnect and disconnects with a short settle-wait before the SPIFFS stage's own `WiFi.begin()` — without it, a failed NVS attempt's background auto-retry can collide with the SPIFFS attempt's `esp_wifi_connect()` call (driver returns `ESP_ERR_WIFI_CONN`, "sta is connecting", silently no-opping the SPIFFS attempt) — see TASK-404.

There used to be a hardcoded `HARDCODED_WIFI_SSID`/`HARDCODED_WIFI_PASS` stage ahead of NVS, fed by a `wifi_creds.h` shim. Removed 2026-08-06 (TASK-404): the shim was never actually wired into the build — `app/.gitignore` expected it at `app/src/wifi_creds.h`, but no such file existed, and `main.cpp` had no `__include`/`#include` mechanism to pull it in regardless — so `HARDCODED_WIFI_SSID` was never defined and the whole stage was permanently dead code. Confirmed via a full source grep and `strings` on the compiled ELF (no hardcoded SSID string present).


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
- `matrixDisplay.h` was deleted (TASK-467/ADR-061 D8) — no env defined `MATRIX_DISPLAY`, so it was unreachable. `cheapYellowLCD.h` was deleted too (TASK-470/ADR-061 D9 step 4) — `WinampDisplay` now derives directly from `SpotifyDisplay` (`app/src/winamp/winampDisplay.{h,cpp}`); the global `tft` object lives in `app/src/display/tft.{h,cpp}`, not here.
- `nfc.h` — optional PN532 NFC reader; tags carry Spotify URIs/URLs that get played on swipe. Set `NFC_ENABLED 0` in the `.ino` to disable. `writeContextToNfc` toggles writing the currently-playing context back to a tag (off for albums that auto-flow into related songs).
- `touchScreen.h` / `CYD28_TouchscreenR.{h,cpp}` — CYD touch input (rotated coordinates).
- `configFile.h` — SPIFFS-backed persisted config.
- `WifiManagerHandler.h`, `refreshToken.h` — first-run setup flow described above.

`GitHubPages/` hosts the ESPWebTools browser flasher (Chrome/Edge) — a build artifact deployment target, not part of firmware.

**Host tooling** (`app/tools/`, per [M-TOOLING-host-tool-architecture.md](docs/architecture/designs/M-TOOLING-host-tool-architecture.md)):
- `lib/` — shared layer: `dut.py` (DUT session: port resolve, open, send, expect), `flaky.py`/`results.py` (suite reporting).
- `gate/` — host gates `run/check`/`run/check-docs` invoke: the five `check_*.py` scripts + their `test_check_*.py` tests. Leaves — nothing else depends on `gate/`.
- `gen/` — codegen writing into `app/gen/`, staleness-gated (`gen_app_registry.py`, `gen_mem_layout.py`, …).
- `bake/` — asset bakes writing into `app/gen/`, `golden.sha256`-gated (`bake_skin.py`, `bake_nixie.py`, …).
- `preview/` — host-only renderers (parse `gen/*.h`, never mirror it — LL-114). `preview_common.py` (the shared parser these import) stays flat in `app/tools/`, not inside `preview/`.
- `probe/` — one-shot host probes against live external services.
- `suite/` — DUT test suites. `serialdbg/` (TASK-480, DONE): the former 10 005-line `run_serialdbg_tests.py` monolith split into one module per app family — `clock.py`, `teletext.py`, `planeradar.py`, `stock.py`, `webradio.py`, `player.py`, `shell.py` (the catch-all for taskbar/app-switch and the small single-screen apps) — plus `_helpers.py` for anything used by 2+ families. `runner.py` is the CLI entry point `run/test`/`run/test-targeted`/`run/player-gate` invoke; `__init__.py`'s `build_all_tests()` assembles the combined registry from each family's own `TESTS` dict, and `build_all_meta()` the matching `(cls, scope, effect)` record — seeded from the module/id-prefix by `serialdbg/_meta.py`, overridden by `@meta(...)` declarations, gated by `gate/check_test_meta.py` (TASK-570).
- `spike/` — one-off, task-scoped tools; `run/check-docs`'s `SPIKE` check (blocking) fails any `spike/task<NNN>_*` whose task is archived.

Levels depend downward only: a suite may use `lib/`; `lib/` never imports a suite; `preview/`/`bake/` never import from `suite/`.
