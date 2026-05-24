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
upstream ref:    <fill in: git rev-parse HEAD on the upstream clone at pull time>
```

## Patch table

| File (relative to `Spotify-Diy-Thing/`) | Patch ID | Description | Rationale |
|------------------------------------------|----------|-------------|-----------|
| `SpotifyDiyThing/cheapYellowLCD.h` | PATCH-001 | M-NOART: gate JPEGDEC album-art path behind `#ifndef WINAMP_DISPLAY` | JPEGDEC causes `JPEGPutMCU22 LoadProhibited` crash during track playback under `cyd2usb_winamp` build. No upstream fix available. Crash confirmed on DUT 2026-05-20. |

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
