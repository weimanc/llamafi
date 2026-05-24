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
| `SpotifyDiyThing.ino` | **ours** | rewritten as app shell entry point |
| `appShell.h` | **ours** | new — app registry, switchApp(), tick/input dispatch |
| `winamp/winampDisplay.h` | **ours** | moved to subdirectory |
| `winamp/vuMeter.h` | **ours** | moved to subdirectory |
| `taskbar/taskbar.h` | **ours** | new |
| `gen/` | **ours** | unchanged |

## Target directory structure

```
Spotify-Diy-Thing/SpotifyDiyThing/
├── SpotifyDiyThing.ino    ← our shell (replaces upstream entrypoint)
├── appShell.h             ← app registry, switchApp(), dispatch
│
├── winamp/                ← our winamp app
│   ├── winampDisplay.h
│   └── vuMeter.h
│
├── taskbar/               ← taskbar renderer + hit-test
│   └── taskbar.h
│
├── gen/                   ← generated (skin_layout.h, shell_layout.h, assets)
│
│   — upstream files below, unmodified —
├── spotifyLogic.h
├── WifiManagerHandler.h
├── configFile.h
├── touchScreen.h
├── CYD28_TouchscreenR.h
├── CYD28_TouchscreenR.cpp
├── nfc.h
├── dnsOverride.h
└── cheapYellowLCD.h
```

## Interface boundary: SpotifyAppState

`app-lifecycle.md` already defines `SpotifyAppState` — the render-cache fields
that winampDisplay.h reads and the shell saves/restores on app switch. This is
the interface between the Spotify data layer (upstream `spotifyLogic.h`) and
our winamp renderer.

The restructure makes this explicit: winampDisplay.h reads **only** from
`SpotifyAppState` (no direct globals from spotifyLogic.h). The shell populates
the struct from the spotifyTask snapshot and passes it in.

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

## Migration sequence

1. Create `winamp/` subdirectory; move `winampDisplay.h`, `vuMeter.h`
2. Add `appShell.h` (per app-lifecycle.md spec)
3. Add `taskbar/taskbar.h` (per taskbar.md spec)
4. Rewrite `SpotifyDiyThing.ino` as our shell
5. Apply originX=0 shift (layout.md) — now a one-line change in shell rect
6. Run `audit_origin.py` (TASK-082) as migration check

Steps 1–4 have no firmware behaviour change. Step 5 is the first observable
change on hardware.

## Exit criteria

- `winampDisplay.h` has no direct reads from `spotifyLogic.h` globals; all
  data comes through `SpotifyAppState`
- `SpotifyDiyThing.ino` contains no upstream code — only shell dispatch
- Upstream files in the flat directory are unmodified (verifiable via git diff
  against the upstream ref)
- Firmware builds and behaves identically to pre-restructure (no regressions)
- `audit_origin.py --grep-only` exits 0 post-restructure
