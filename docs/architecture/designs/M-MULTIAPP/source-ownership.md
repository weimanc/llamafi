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
