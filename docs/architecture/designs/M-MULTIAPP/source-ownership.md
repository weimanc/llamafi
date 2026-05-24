# M-MULTIAPP — Source Ownership and Project Restructure

> Owner: Architect
> Status: draft (2026-05-24)
> Part of: [overview.md](overview.md)
> Prerequisite for: M-MULTIAPP firmware implementation, originX=0 shift

## Problem

All code — upstream `SpotifyDiyThing` and our additions — lives in the same
flat directory. No clear boundary between what we own and what is external.
The upstream `.ino` is the entry point, meaning the application shell is
implicitly upstream's.

```
Spotify-Diy-Thing/SpotifyDiyThing/   ← everything lives here, flat
├── SpotifyDiyThing.ino               ← upstream entry point (we've modified it)
├── spotifyLogic.h                    ← upstream
├── cheapYellowLCD.h                  ← upstream
├── winampDisplay.h                   ← OURS (no directory to signal this)
├── vuMeter.h                         ← OURS
└── gen/                              ← OURS (generated assets)
```

## What "library" means in practice

Arduino/PlatformIO compiles everything together — there is no binary library
boundary. "Using SpotifyDiyThing as a library" means:

- We own the entry point (`SpotifyDiyThing.ino` is rewritten as our shell)
- We `#include` upstream headers for WiFi, Spotify API, and config
- Upstream source files are compiled in, but we do not modify them
- Our code lives in named subdirectories that signal ownership

This is a code-organisation change, not a build-system change. The output
binary is identical in structure.

## Ownership table

| File(s) | Owner | Disposition |
|---------|-------|-------------|
| `spotifyLogic.h` | upstream | include as-is, do not modify |
| `WifiManagerHandler.h` | upstream | include as-is |
| `configFile.h` | upstream | include as-is |
| `touchScreen.h`, `CYD28_TouchscreenR.*` | upstream | include as-is |
| `nfc.h`, `dnsOverride.h` | upstream | include as-is |
| `cheapYellowLCD.h` | upstream | include as-is (TFT init) |
| `spotifyDisplay.h` | upstream | **superseded** — our shell replaces this abstraction |
| `screenLog.h` | **ours** | stays flat; `#include "winampDisplay.h"` → `#include "winamp/winampDisplay.h"` in step 1 |
| `SpotifyDiyThing.ino` | **ours** | rewritten as app shell entry point |
| `appShell.h` | **ours** | new — app registry, switchApp(), tick/input dispatch |
| `winamp/winampDisplay.h` | **ours** | moved to subdirectory |
| `winamp/vuMeter.h` | **ours** | moved to subdirectory |
| `taskbar/taskbar.h` | **ours** | new |
| `gen/` | **ours** | unchanged |

## Target directory structure

**Option B chosen**: `Spotify-Diy-Thing/` is kept as close to stock upstream as
possible. Our firmware is a separate PlatformIO project at `app/` in the repo root.
`app/platformio.ini` uses `lib_extra_dirs` to include upstream source files.

```
esp_spotify/
├── Spotify-Diy-Thing/          ← upstream repo, best-effort stock
│   └── SpotifyDiyThing/
│       ├── SpotifyDiyThing.ino ← reverted to upstream (our shell is app/src/main.cpp)
│       ├── platformio.ini      ← reverted to upstream (our envs move to app/)
│       ├── cheapYellowLCD.h    ← PATCHED (M-NOART JPEGDEC guards — keep; fixes crash)
│       └── ... all other upstream files unmodified
│
└── app/                        ← our PlatformIO project (new)
    ├── platformio.ini          ← cyd2usb_winamp* envs; lib_extra_dirs → Spotify-Diy-Thing/SpotifyDiyThing
    ├── src/
    │   ├── main.cpp            ← our shell (was SpotifyDiyThing.ino)
    │   ├── appShell.h
    │   ├── winamp/
    │   │   ├── winampDisplay.h
    │   │   └── vuMeter.h
    │   ├── taskbar/
    │   │   └── taskbar.h
    │   └── screenLog.h
    ├── gen/                    ← generated assets (skin_layout.h, skin_assets.c, …)
    ├── skins/                  ← base-2.91.wsz
    └── tools/                  ← bake_skin.py, coords.py, run_serialdbg_tests.py, …
```

### Upstream patch policy

| File | Status | Rationale |
|------|--------|-----------|
| `cheapYellowLCD.h` | **patched** | M-NOART JPEGDEC guards fix a real crash; no upstream fix available |
| All other upstream files | stock | Do not modify; pull upstream updates without conflict |

Patches against upstream are tracked in `docs/architecture/designs/M-MULTIAPP/upstream-patches.md` (to be created).

## Interface boundary: SpotifyAppState

`app-lifecycle.md` already defines `SpotifyAppState` — the render-cache fields
that winampDisplay.h reads and the shell saves/restores on app switch. This is
the interface between the Spotify data layer (upstream `spotifyLogic.h`) and
our winamp renderer.

**Scope of decoupling in M-RESTRUCTURE (steps 1–5):** The structural move
and shell rewrite do not require full interface decoupling. `winampDisplay.h`
may continue to read `spotifyTask::isHealthy()`, `lastSuccessfulPollAgeMs()`,
and the existing `spotifyLogic.h` globals during this milestone. Full
decoupling — routing all data through `SpotifyAppState` — is M-MULTIAPP work.

**Known write-back case:** `songStartMillis` is *mutated* by `WinampDisplay`
on optimistic seek (not just read). This means `SpotifyAppState` cannot be a
simple read-only struct for this field. The mutation semantics must be resolved
before full decoupling; that design belongs in M-MULTIAPP app-lifecycle work,
not here.

## Entry point: our shell replaces upstream .ino

`SpotifyDiyThing.ino` becomes our file. It:

1. Calls upstream `setup()` helpers (WiFi, Spotify auth, TFT init)
2. Starts `spotifyTask` (existing FreeRTOS worker)
3. Starts `dataTask` for Weather/Crypto (per app-lifecycle.md)
4. In `loop()`: calls `appTick(currentAppId)` and `appHandleInput(currentAppId)`
   (per app-lifecycle.md dispatch design)

`spotifyDisplay.h` (the upstream display abstraction) is no longer used — our
shell is the dispatcher.

## No new HAL

`TFT_eSPI` is the display HAL. Arduino WiFi is the network HAL. PlatformIO
envs (`cyd2usb_winamp`) are the target selector. No additional layer is needed.

## Relation to origin shift

With winampDisplay.h receiving its canvas rect from the shell (`Rect(0, 0,
275, 240)` at `originX=0`), there is no global `originX` for it to read.
The static grep audit (T141 / `audit_origin.py`) becomes a one-time migration
check, not an ongoing concern.

## Relation to existing M-MULTIAPP designs

| Design doc | Status | Interaction |
|------------|--------|-------------|
| `app-lifecycle.md` | draft | defines `SpotifyAppState`, `switchApp()`, dispatch — this doc defers to it |
| `shell-layout.md` | draft | defines `gen/shell_layout.h` constants consumed by `appShell.h` |
| `taskbar.md` | draft | defines taskbar renderer — lives in `taskbar/` per this doc |
| `layout.md` | draft | defines originX=0 shift — enabled by this restructure |

## `app/platformio.ini` spec

`app/platformio.ini` builds our firmware from `app/src/`. It references upstream
headers via `lib_extra_dirs` and picks up SpotifyArduino from `app/lib/` (moved
from `Spotify-Diy-Thing/lib/` during TASK-083 step 2).

```ini
[platformio]
src_dir = src
default_envs = cyd2usb_winamp

[env]
platform = espressif32@6.9.0
board    = esp32dev
framework = arduino
; SpotifyArduino vendored in app/lib/ — LOCAL_PATCHES preserved (see LOCAL_PATCHES.md).
; Upstream headers (spotifyLogic.h, cheapYellowLCD.h, etc.) resolved via lib_extra_dirs.
lib_deps =
    khoih-prog/ESP_DoubleResetDetector@^1.3.2
    bblanchon/ArduinoJson@^6.21.3
    wnatth3/WiFiManager@^2.0.16-rc.2
    https://github.com/witnessmenow/Seeed_Arduino_NFC.git
; lib_extra_dirs entry 1: upstream flat source dir — provides all upstream .h files.
;   PlatformIO (lib_ldf_mode=deep+) compiles paired .cpp files (e.g. CYD28_TouchscreenR.cpp)
;   when their .h is #included. .ino files in this dir are NOT compiled by PlatformIO
;   (Arduino .ino compilation only applies to src_dir).
; lib_extra_dirs entry 2: upstream lib/ dir — lets PlatformIO discover external libs
;   that may remain in Spotify-Diy-Thing/lib/ post-restructure (e.g. future upstream pulls
;   that add a new lib). app/lib/ is auto-scanned as the project lib dir; no extra_dirs needed for it.
lib_extra_dirs =
    ../Spotify-Diy-Thing/SpotifyDiyThing
    ../Spotify-Diy-Thing/lib
monitor_speed = 115200
monitor_filters = esp32_exception_decoder
upload_speed = 921600
lib_ldf_mode = deep+

[common_cyd]
lib_deps =
    ${env.lib_deps}
    bodmer/TFT_eSPI@^2.5.33
build_flags =
    -DYELLOW_DISPLAY
    -DUSER_SETUP_LOADED
    -DILI9341_2_DRIVER
    -DTFT_WIDTH=240
    -DTFT_HEIGHT=320
    -DTFT_MISO=12
    -DTFT_MOSI=13
    -DTFT_SCLK=14
    -DTFT_CS=15
    -DTFT_DC=2
    -DTFT_RST=-1
    -DTFT_BL=21
    -DTFT_BACKLIGHT_ON=HIGH
    -DTFT_BACKLIGHT_OFF=LOW
    -DLOAD_GLCD
    -DSPI_FREQUENCY=40000000
    -DSPI_READ_FREQUENCY=20000000
    -DSPI_TOUCH_FREQUENCY=2500000
    -DLOAD_FONT2
    -DLOAD_FONT4
    -DLOAD_FONT6
    -DLOAD_FONT7
    -DLOAD_FONT8
    -DLOAD_GFXFF
    -DUSE_HSPI_PORT
    -DSPOTIFY_MARKET=\"IE\"

[env:cyd2usb]
board_build.partitions = ../Spotify-Diy-Thing/partitions_no_ota.csv
lib_deps =
    ${common_cyd.lib_deps}
build_flags =
    ${common_cyd.build_flags}
    -DTFT_INVERSION_ON
    -DCORE_DEBUG_LEVEL=4

[env:cyd2usb_winamp]
extends = env:cyd2usb
build_flags =
    ${env:cyd2usb.build_flags}
    -DWINAMP_DISPLAY
lib_ignore = JPEGDEC

[env:cyd2usb_winamp_screenlog]
extends = env:cyd2usb_winamp
build_flags =
    ${env:cyd2usb_winamp.build_flags}
    -DSCREEN_LOG

[env:cyd2usb_winamp_debug]
extends      = env:cyd2usb_winamp
extra_scripts = pre:scripts/inject_git_hash.py
build_flags =
    ${env:cyd2usb_winamp.build_flags}
    -DSERIAL_DEBUG
```

**Dropped envs** (not our target hardware; stay in `Spotify-Diy-Thing/platformio.ini`
for upstream use): `[env:cyd]`, `[env:cyd2usb_spike]`, `[env:trinity]`.

**`partitions_no_ota.csv`**: referenced via relative path `../Spotify-Diy-Thing/`.
The file is upstream-owned; no need to copy it. Adjust the path if it moves.

**`lib/SpotifyArduino/`**: PlatformIO auto-discovers `app/lib/` as the project
lib directory — no `lib_extra_dirs` entry needed for it.

**Implementation note**: validate `lib_extra_dirs` during TASK-083 step 1 by
confirming `CYD28_TouchscreenR.cpp` compiles (needs the upstream flat dir) and
`SpotifyArduino` resolves (needs `app/lib/`). If upstream's lib dir introduces
conflicts, drop the second `lib_extra_dirs` entry and rely solely on `app/lib/`.

## Migration sequence

1. Create `winamp/` subdirectory; move `winampDisplay.h`, `vuMeter.h`.
   Update `screenLog.h` include: `"winampDisplay.h"` → `"winamp/winampDisplay.h"`.
   Gate: `check_build.sh` passes.

2. Add `appShell.h` stub (per app-lifecycle.md spec — dispatch wired, app bodies
   stubbed). Gate: `check_build.sh` passes.

3. Add `taskbar/taskbar.h` stub (per taskbar.md spec — render + hit-test stubs).
   Gate: `check_build.sh` passes.

4. Rewrite `SpotifyDiyThing.ino` as our shell; upstream files included unchanged.
   Gate: `check_build.sh` passes **and** `audit_origin.py --grep-only` exits 0
   (shell must not introduce bare absolute X literals) **and** DUT smoke test:
   - Boot with a playing track — Winamp chrome renders correctly
   - Touch NEXT/PREV — track advances
   - Touch PLAY/PAUSE — playback toggles
   - No crash on track change

5. Apply `originX=0` (layout.md) — one-line rect change in shell.
   Gate: `audit_origin.py` (full run, T141–T146) exits 0. This is the TASK-082
   exit gate and the entry condition for TASK-081 DUT regression.

Steps 1–4 have no firmware behaviour change. Step 5 is the first observable
change on hardware.

## Exit criteria

- `check_build.sh` exits 0 after each step
- `SpotifyDiyThing.ino` contains only shell dispatch — no upstream business logic
- `screenLog.h` updated to use `"winamp/winampDisplay.h"` path
- Upstream files in the flat directory are unmodified (verifiable via `git diff`
  against the upstream ref — do not modify `spotifyLogic.h`, `cheapYellowLCD.h` etc.)
- Step 4 DUT smoke test passes (boot render, NEXT/PREV, PLAY/PAUSE, no crash)
- `audit_origin.py --grep-only` exits 0 after step 4 and after step 5
- `audit_origin.py` (full, T141–T146) exits 0 after step 5

**Out of scope for this milestone (M-MULTIAPP work):**
- Full decoupling of `winampDisplay.h` from `spotifyLogic.h` globals
- `songStartMillis` write-back design in `SpotifyAppState`
- `spotifyTask::` direct calls removal from `winampDisplay.h`
- `saveAppState`/`restoreAppState` field mapping
- `repaintApp()` / `dataTask` implementation
