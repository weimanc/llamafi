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

## PATCH-SPOTIFYLOGIC-1 — `spotify`/`songStartMillis`/etc. moved from definitions to extern declarations

**Files:** `spotifyLogic.h` (+ new `spotifyLogic.cpp`) · **Task:** TASK-471 (M-SRCLAYOUT Stage E) ·
**Added:** 2026-08-21

### Symptom

Linking failed with `multiple definition of 'spotify_server_cert'` /
`'spotify_image_server_cert'` (from `app/lib/SpotifyArduino/src/SpotifyArduinoCert.h`,
see PATCH-CERT-1 in that library's own patch record) once `spotifyLogic.h` was made
declarations-only and its new `spotifyLogic.cpp` included it.

### Cause

Same class of problem as PATCH-TOUCHSCREEN-1 above: `spotifyLogic.h` defined a real
`SpotifyArduino spotify(client, NULL, NULL);` instance, several other globals
(`songStartMillis`, `songDuration`, `g_lastRenderMs`, `lastTrackUri`,
`lastTrackContextUri`, plus a few genuinely private ones), and every function body
(`spotifySetup`, `spotifyRefreshToken`, `updateProgressBar`, `updateCurrentlyPlaying`,
and three helpers only ever called from within this file), all at file scope with no
`#pragma once`. Safe only while `app/src/main.cpp` was its sole includer.
`apps/spotifyApp.h`'s Stage E conversion needed these symbols directly (rather than
picking them up silently via main.cpp's include order, the exact SF.11 gap Stage E
exists to close), making `apps/spotifyApp.cpp` a second includer.

### Fix

Same shape as PATCH-TOUCHSCREEN-1: real `extern` declarations (functions kept
declaration-only) in the header, one definition each in the new `spotifyLogic.cpp`.
The three helper functions genuinely private to this file (`isSameTrack`, `setTrackUri`,
`setTrackContextUri`) and `handleCurrentlyPlaying` (dead code — confirmed uncalled
anywhere in the tree; `updateCurrentlyPlaying` duplicates its logic against the
`spotifyTask::Snapshot` API instead) stay `static` in the .cpp, not declared in the
header at all — nothing outside this file ever named them.

Also needed: `app/src` on the include path for library compilation units. `spotifyLogic.h`
`#include`s three `app/src` headers (`logDecode.h`, `logHeartbeat.h`, `logSink.h`) plus
`spotifyTask.h` — quoted-includes that resolved for free while this header was only ever
textually pasted into `main.cpp.o` (which gets `src_dir` on its own include path), but not
for a `.cpp` living under `app/lib/`. Added `-Isrc` to `platformio.ini`'s shared
`build_flags` (`[common_cyd]`) rather than duplicating `app/src` paths by hand in this one
library.

Verified on five envs: `cyd2usb_winamp`, `_debug`, `_webradio`, `_player`, and
`_winamp_debug_noSpotify` all build clean. `.dram0.bss`/`.data` byte-identical on both
`cyd2usb_winamp` and `cyd2usb_winamp_debug` (measured via `firmware.map`). No behaviour
change: same objects, same construction order, just declared in the header and defined
once in the .cpp. No DUT access from this session — build/gate-verified only.

### Note for the next platform bump

If this directory is ever re-vendored wholesale from upstream (unlike
`app/lib/SD/`, there is no re-vendoring step documented for this one today,
but if one is ever added), re-apply this patch the same way PATCH-SD-1 is
re-applied: diff the fresh upstream copy against this one and reintroduce the
`extern`/`.cpp`-split shape.

### Follow-up — TASK-468 (ADR-061 D9 step 1, 2026-08-25)

`tft`'s definition moved again, out of `cheapYellowLCD.cpp` and into the new
owned component `app/src/display/tft.{h,cpp}`. `cheapYellowLCD.h` now
`#include`s `display/tft.h` instead of declaring its own `extern TFT_eSPI
tft;`; `cheapYellowLCD.cpp` no longer defines `tft` at all — it keeps its
other includes only. If this directory is ever re-vendored, the extern in
`cheapYellowLCD.h` should be re-pointed at `display/tft.h` rather than
reintroduced locally.

### Follow-up — TASK-470 (ADR-061 D9 step 4, 2026-08-25): `cheapYellowLCD.h`/`.cpp` deleted

The two files this patch record's PATCH-TOUCHSCREEN-1 section above is
partly about no longer exist. TASK-469 (D9 step 3, same day) flattened
`WinampDisplay : public CheapYellowDisplay` onto `WinampDisplay : public
SpotifyDisplay` directly, absorbing the small amount of `CheapYellowDisplay`
behaviour it actually used; nothing in `app/src` depended on the class
after that. `main.cpp`'s `#elif defined YELLOW_DISPLAY` display-selection
branch (the only thing that ever `#include`d `cheapYellowLCD.h` or
instantiated `CheapYellowDisplay`) is deleted too — plain-CYD was already a
"no longer supported target" per ADR-061 D9's consequences, and no env
defines `YELLOW_DISPLAY` for *that* purpose (see below).

**`touchScreen.h`/`.cpp` are unaffected and stay** — they were always their
own file pair (see PATCH-TOUCHSCREEN-1 above), only ever transitively
`#include`d *through* `cheapYellowLCD.h`. `winamp/winampDisplay.h` now
`#include`s `touchScreen.h` directly (TASK-469), so the touch subsystem
declarations reach every includer exactly as before — one hop shorter.

**`-DYELLOW_DISPLAY` the build flag is NOT retired** — do not read this
follow-up as license to strip it from `[common_cyd]` in `platformio.ini`.
It is still unconditionally defined for every CYD env and gates a real,
independent, live feature: `boot.cpp`'s GPIO0 `forceRefreshToken` check
(`#if defined YELLOW_DISPLAY`, not an `#elif` of the display-selection
chain). That coupling — one macro, two unrelated meanings (display class
selection in `main.cpp`; a boot-time button gate in `boot.cpp`) — predates
this task and was flagged, not fixed, here; a future cleanup could give the
boot-time gate its own flag if the overload is ever confusing enough to be
worth the churn.
