# LOCAL_PATCHES — vendored `SpotifyDiyThingUpstream` files

This directory holds files from the upstream `witnessmenow/Spotify-Diy-Thing`
project (`Spotify-Diy-Thing/SpotifyDiyThing/`), vendored so `app/`'s own
firmware can include them via `lib_extra_dirs`. Until now nothing in this
directory carried local patches, so there was no record — this file starts
one, same convention as `app/lib/SD/LOCAL_PATCHES.md`,
`app/lib/SpotifyArduino/LOCAL_PATCHES.md`, and
`app/lib/ESP32-audioI2S/LOCAL_PATCHES.md`.

---

## PATCH-TOUCHSCREEN-1 — `tft`/`ts` etc. moved from definitions to extern declarations

**Files:** `touchScreen.h` (+ new `touchScreen.cpp`), `cheapYellowLCD.h` (+ new
`cheapYellowLCD.cpp`) · **Task:** TASK-471 (M-SRCLAYOUT Stage E) · **Added:** 2026-08-21

### Symptom

Linking `cyd2usb_winamp` (and every other env) failed with
`multiple definition of 'tft'`, then (after an intermediate fix) `multiple
definition of 'touchSetup(SpotifyArduino*)'` / `previousTrackStatus` /
`nextTrackStatus` / `handleTouched()`.

### Cause

Both headers defined real, non-`extern` globals and function bodies at file
scope — `TFT_eSPI tft = TFT_eSPI();` in `cheapYellowLCD.h`; `CYD28_TouchR ts(...)`,
`bool previousTrackStatus`/`nextTrackStatus`, `SpotifyArduino *spotify_touch`,
and the bodies of `touchSetup()`/`handleTouched()` in `touchScreen.h` (which also
had no `#pragma once` at all). This was safe for as long as this whole firmware
was Arduino/`.ino`-style single-TU — `app/src/main.cpp` was the only
translation unit that ever pulled these headers in, via `winamp/winampDisplay.h`
→ `cheapYellowLCD.h` → `touchScreen.h`.

M-SRCLAYOUT Stage E (TASK-471) converts `app/src` app classes from
all-inline headers into real `.h`/`.cpp` component pairs. The first app
conversion that also transitively includes `winampDisplay.h` — `webRadioApp.h`
→ `webRadioApp.cpp` — made this the *second* translation unit to include
`cheapYellowLCD.h`/`touchScreen.h`, and every one of those file-scope
definitions duplicated at link time.

### Fix

Same pattern already used across `app/src` for this exact problem
(`audio/audioEngine.h` split, same task): every definition moved out of the
header into one new `.cpp` per file, with the header reduced to declarations
(`extern` for data, plain prototypes for functions). `touchScreen.h` also
gained the `#pragma once` it never had, and both new `.cpp` files needed their
own `#include`s added (`<Arduino.h>`, `<WiFi.h>`, `<SpotifyArduino.h>`,
`<string.h>`) that the old single-inclusion model let them borrow silently
from whatever `main.cpp` had already included by that point in the file.

Nothing here changes behaviour: `ts`, `tft`, `previousTrackStatus`,
`nextTrackStatus`, and `spotify_touch` are still each exactly one object,
still constructed/initialised identically, just declared in the header and
defined in the new `.cpp`. Verified: `cyd2usb_winamp`, `cyd2usb_winamp_debug`,
`cyd2usb_webradio`, and `cyd2usb_player` all build clean; `.dram0.bss`/`.data`
unchanged to within a few bytes (measured via `firmware.map`, well under the
project's 256 B per-component exception threshold) on both the production and
debug builds. No DUT access from this session — build/gate-verified only.

### Note for the next platform bump

If this directory is ever re-vendored wholesale from upstream (unlike
`app/lib/SD/`, there is no re-vendoring step documented for this one today,
but if one is ever added), re-apply this patch the same way PATCH-SD-1 is
re-applied: diff the fresh upstream copy against this one and reintroduce the
`extern`/`.cpp`-split shape.
