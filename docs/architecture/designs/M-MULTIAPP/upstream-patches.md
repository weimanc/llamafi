# M-RESTRUCTURE — Upstream Patch Registry

> Owner: Developer  
> Status: active  
> Part of: [source-ownership.md](source-ownership.md)

Tracks every intentional deviation from upstream
[witnessmenow/Spotify-Diy-Thing](https://github.com/witnessmenow/Spotify-Diy-Thing)
in `Spotify-Diy-Thing/`. One row per patched file. All other files in that
directory must be stock — verifiable by `git diff <upstream-ref>`.

## Upstream reference

Pin this to the upstream commit that was current when Option B was adopted
(2026-05-24). Update on each upstream pull.

```
upstream remote: https://github.com/witnessmenow/Spotify-Diy-Thing.git
upstream ref:    6eb95ffd546482423c88f647a527b89de633059d  (origin/main as of 2026-05-24)
```

## Patch table

| File (relative to `Spotify-Diy-Thing/`) | Patch ID | Description | Rationale |
|------------------------------------------|----------|-------------|-----------|
| `SpotifyDiyThing/cheapYellowLCD.h` | PATCH-001 | M-NOART: gate JPEGDEC album-art path behind `#ifndef WINAMP_DISPLAY` | JPEGDEC causes `JPEGPutMCU22 LoadProhibited` crash during track playback under `cyd2usb_winamp` build. No upstream fix available. Crash confirmed on DUT 2026-05-20. |
| `SpotifyDiyThing/CYD28_TouchscreenR.h` | PATCH-002 | Add `setCalibration()` public method + private `_cal*` members for runtime touch calibration override | Upstream bakes `CYD28_TouchR_CAL_*` constants into `convertRawXY()`; no runtime override path. Required by M-MULTIAPP Settings touch calibration flow. |
| `SpotifyDiyThing/CYD28_TouchscreenR.cpp` | PATCH-002 | Replace `CYD28_TouchR_CAL_*` macro references in `convertRawXY()` with `_cal*` member variables | Same as above — C++ side of the patch. |

## PATCH-001 detail

**File**: `Spotify-Diy-Thing/SpotifyDiyThing/cheapYellowLCD.h`  
**Upstream status**: no equivalent guard; upstream always compiles the JPEG path.  
**Our change**: wrap the `displayImageUsingFile` implementation and the
`JPEGDEC`-dependent declarations with `#ifndef WINAMP_DISPLAY ... #endif`.
When `WINAMP_DISPLAY` is defined (our `cyd2usb_winamp*` envs), the JPEG decode
path is compiled out entirely. The `lib_ignore = JPEGDEC` in `app/platformio.ini`
removes the `JPEGDEC` lib_dep from those envs.  
**Introduced**: commit `1411a3e` (cherry-pick from `rnd/poll-lag`, 2026-05-21)  
**Design ref**: `docs/project/roadmap.md` M-NOART; TASK-062.

## PATCH-002 detail

**Files**: `Spotify-Diy-Thing/SpotifyDiyThing/CYD28_TouchscreenR.h` and `.cpp`  
**Upstream status**: `convertRawXY()` references `CYD28_TouchR_CAL_*` `#define` constants
directly — no runtime override path exists.  
**Our change** (`.h`): add `setCalibration(int16_t xMin, int16_t xMax, int16_t yMin, int16_t yMax)`
public method; add private `_calXMin/_calXMax/_calYMin/_calYMax` members initialised to the
compile-time `#define` defaults (backward-compatible — calling code that never calls
`setCalibration()` sees identical behaviour).  
**Our change** (`.cpp`): replace the four `CYD28_TouchR_CAL_*` references in `convertRawXY()`
with the corresponding `_cal*` member variables.  
**Prerequisite for**: M-MULTIAPP Settings → Touch Calibration section (`CalibrationFlow`).
Must be applied before any cal implementation work begins.  
**Design ref**: [touch-calibration.md §Integration prerequisite — PATCH-002](touch-calibration.md).  
**Status**: **not yet applied** — pending implementation of touch calibration section.

---

## Policy

- Keep this file current whenever upstream is pulled.
- A patch is retired when upstream ships an equivalent fix; retire by removing
  the row and reverting the file to stock.
- New patches require an entry here before merging. If a patch grows beyond a
  few guarded lines, consider a side-by-side patch file under
  `docs/architecture/designs/M-MULTIAPP/patches/` instead of an inline guard.
- `lib/SpotifyArduino/` (our LOCAL_PATCHES family) is **not tracked here** —
  it lives in `app/lib/` after the restructure and is fully owned by us.
  See `app/lib/SpotifyArduino/LOCAL_PATCHES.md`.
