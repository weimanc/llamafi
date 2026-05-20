# Design — Album-art path removal (M-NOART)

> Owner: Architect
> Status: draft
> Date: 2026-05-20
> Feeds: (leave blank — no ADR needed; change is structural, not cross-cutting)
> Tracked-as: TASK-062

## Context / pain points

The `WinampDisplay` renderer (`winampDisplay.h`) subclasses `CheapYellowDisplay`
(`cheapYellowLCD.h`) and inherits its album-art path unchanged. That path:

1. **~40 KB dead weight** — `JPEGDEC` (bitbank2) is linked into every Winamp build.
   The CYD panel has no space for album art in the Winamp layout; the code is
   never reachable.
2. **Keep-alive clobber** — `displayImageUsingFile()` opens a TLS connection to
   Spotify's CDN image server (`i.scdn.co`), swapping the active certificate
   (`spotify_image_server_cert`). This tears down the `api.spotify.com` HTTP/1.1
   keep-alive session established by PROP-004 / INV-A Step 3.
3. **Guru Meditation crash** — `JPEGPutMCU22 LoadProhibited` observed on DUT
   2026-05-20 during track transitions. Root cause: `processImageInfo` triggers on
   track change, `displayImageUsingFile` calls `getImage`, JPEGDEC's MCU decode
   dereferences a null `pDraw` on a partial or empty response.

**Current workaround** (`winampDisplay.h:57–59`): `WinampDisplay` overrides
`processImageInfo` to unconditionally return `false`, preventing the fetch.
This blocks the crash but does not remove the compiled-in JPEG decoder, the
CDN TLS swap, or the SPIFFS write path that also allocates heap.

**Constraint:** `processImageInfo`, `displayImage`, and `clearImage` are pure
virtual in `SpotifyDisplay` (`spotifyDisplay.h:20–22`). Removing their
implementations from `CheapYellowDisplay` makes the class abstract and breaks
the build. Any gating strategy must preserve at least a stub.

## Goals

- `cyd2usb_winamp` build: JPEGDEC not compiled, not linked; no CDN album-art
  connections; no SPIFFS album-art writes.
- No regression to `cyd` / `cyd2usb` non-Winamp builds — full art path unchanged.
- `winampDisplay.h` workaround (`processImageInfo` override) removed — superseded
  by the compile-time guard.
- DUT survives 5+ min of active playback without a Guru Meditation error.

## Design space (options + tradeoffs)

### Gap 1 — Virtual method contract under compile-time gating

`processImageInfo` and `displayImage` are pure virtual in `SpotifyDisplay`.
Wrapping their entire bodies in `#ifndef WINAMP_DISPLAY` leaves no override →
`CheapYellowDisplay` becomes abstract → instantiation fails.

**Option A — Guard method bodies; keep signatures.**

When `WINAMP_DISPLAY` is defined, `processImageInfo` returns `false` and
`displayImage` returns `0` via a trivial `#else` branch inside the existing
method definitions. The signatures remain, satisfying the pure-virtual contract.
The JPEG-using private implementation methods (`displayImageUsingFile`,
`drawImagefromFile`) are wrapped and omit entirely via `#ifndef`.

Tradeoffs: no base-class change; pure-virtual contract preserved for future
backends; guard is local to `cheapYellowLCD.h`; minimal diff.

**Option B — Change `SpotifyDisplay` to provide default no-op implementations.**

Convert `processImageInfo` and `displayImage` from pure virtual to virtual with
body `{ return false; }` / `{ return 0; }`. Then `CheapYellowDisplay` can omit
its overrides entirely when `WINAMP_DISPLAY` is defined.

Tradeoffs: cleaner per-env compile output; but changes the base class contract,
meaning future backends silently compile without providing these methods. The
pure-virtual nature is a useful safety net (forces intentional implementation).

**Lean: Option A.** Guard bodies, keep signatures. No base-class change; future
backends remain required to implement the methods intentionally.

---

### Gap 2 — File-scope JPEG globals and callbacks in `cheapYellowLCD.h`

Lines 12–66 are file-scope: the `#include <JPEGDEC.h>`, `JPEGDEC jpeg`,
`const char *ALBUM_ART`, and four JPEG I/O callbacks (`myOpen`, `myClose`,
`myRead`, `mySeek`) plus `JPEGDraw` and `myfile`. These must be C-linkage
functions passed as function pointers to `JPEGDEC::open()` — they cannot be
moved inside the class.

**Option A — Wrap the entire block in `#ifndef WINAMP_DISPLAY` / `#endif`.**

Single guard, lines 12–66. When `WINAMP_DISPLAY` is set, the include is skipped,
globals are not declared, callbacks are not emitted. No linker reference to JPEGDEC.

Tradeoffs: straightforward; requires the private methods that reference these
globals to also be guarded (Gap 3).

**Option B — Move globals and callbacks inside the class.**

Not viable: JPEGDEC's API requires raw C function pointers; member function
pointers have incompatible calling conventions. No change possible here.

**Lean: Option A.** Single `#ifndef WINAMP_DISPLAY` block. Minimal and correct.

---

### Gap 3 — Private JPEG implementation methods in `CheapYellowDisplay`

`displayImageUsingFile()` (lines 250–289) and `drawImagefromFile()` (lines 291–306)
reference `JPEGDEC jpeg`, `ALBUM_ART`, and the callbacks from Gap 2. They are
private and not virtual — no abstract-class constraint applies.

**Option A — Wrap entire private methods in `#ifndef WINAMP_DISPLAY`.**

Both methods compile out completely when `WINAMP_DISPLAY` is defined. The
guarded `displayImage()` public stub (Gap 1) never calls them.

Tradeoffs: zero dead code in Winamp build; private methods fully absent.

**Option B — Guard method bodies only (keep signatures, empty when WINAMP_DISPLAY).**

Signatures remain; bodies are empty under `WINAMP_DISPLAY`. No meaningful
difference at link time for private non-virtual methods, but leaves placeholder
noise in the build.

**Lean: Option A.** Private non-virtual methods can be fully excised. Cleaner.

---

### Gap 4 — JPEGDEC in `platformio.ini`

`bitbank2/JPEGDEC@^1.2.8` is declared in `[env]` (the common base section),
so all environments — including all Winamp envs — inherit it. The inheritance
chain is:

```
[env] → [common_cyd] → [env:cyd2usb] → [env:cyd2usb_winamp]
                                      → [env:cyd2usb_winamp_screenlog]
                                      → [env:cyd2usb_winamp_debug]
```

With `lib_ldf_mode = deep+` PlatformIO may resolve the library even if the
`#include` is inside `#ifndef`, depending on whether its scanner respects
preprocessor guards.

**Option A — Remove from `[env]`; re-add to `[env:cyd]` and `[env:cyd2usb]` explicitly.**

Breaks the `extends` inheritance chain: `cyd2usb_winamp` extends `cyd2usb`,
so JPEGDEC would still reach winamp via cyd2usb. Avoiding that requires either
overriding `lib_deps` completely in the winamp env (breaking the clean `extends`)
or not adding JPEGDEC to `cyd2usb` at all — but then the non-Winamp `cyd2usb`
env also loses art. Not viable without significant restructuring.

**Option B — Keep in `[env]` base; add `lib_ignore = JPEGDEC` to `[env:cyd2usb_winamp]`.**

PlatformIO's `lib_ignore` prevents the library from being resolved/linked for
that env. Screenlog and debug envs extend winamp and inherit the ignore.
Compile-time guard (Gap 2) is the primary defense; `lib_ignore` is belt-and-
suspenders to suppress the library resolve step under `lib_ldf_mode = deep+`.
The `extends` chain is untouched.

Tradeoffs: JPEGDEC still listed in common `lib_deps` (downloaded once for the
whole project), but not resolved or linked for winamp envs. Cosmetically the
common section still references a lib the Winamp build doesn't use; this is
acceptable given the inheritance constraint.

**Lean: Option B.** `lib_ignore = JPEGDEC` in `[env:cyd2usb_winamp]` is the
least invasive change. Screenlog/debug envs inherit it for free.

---

### Gap 5 — `winampDisplay.h` `processImageInfo` override (INV-A Step 3 workaround)

Lines 57–59 of `winampDisplay.h`:
```cpp
// INV-A Step 3: block CDN album-art fetches that would clobber the
// HTTP/1.1 keep-alive on api.spotify.com
bool processImageInfo(CurrentlyPlaying /*currentlyPlaying*/) override { return false; }
```

Once the compile-time guard in Gap 1 is in place, `CheapYellowDisplay::processImageInfo`
returns `false` under `WINAMP_DISPLAY`. The workaround override in WinampDisplay
becomes redundant — both return `false` under the same build flag.

**Decision:** Remove lines 57–59 from `winampDisplay.h`. Update the comment on line 3
("inherits the JPEG/SPIFFS/album-art plumbing") to reflect that the plumbing
is now compiled out, not inherited.

---

## Lean / decision

| Gap | Chosen option | Key reason |
|-----|--------------|------------|
| Virtual method contract | A — guard bodies, keep signatures | No base-class change; pure-virtual safety preserved |
| File-scope JPEG globals/callbacks | A — `#ifndef WINAMP_DISPLAY` block (lines 12–66) | Only viable option; callbacks must be C-linkage |
| Private JPEG methods | A — wrap entire methods in `#ifndef` | Private non-virtual; can fully excise |
| JPEGDEC in platformio.ini | B — `lib_ignore` in winamp env | `extends` chain prevents clean removal from common |
| winampDisplay.h workaround | Remove — superseded by Gap 1 guard | Redundant once compile-time guard is in place |

## Open questions

1. **`clearImage()` call sites** — `clearImage()` uses `imageWidth`/`imageHeight`
   set by `processImageInfo`. When WINAMP_DISPLAY is set and `processImageInfo`
   is a no-op, these retain their `displaySetup` defaults (150×150). Verify no
   call site in `SpotifyDiyThing.ino` calls `clearImage()` after expecting
   `processImageInfo` to have resized them. (Expected: safe — Winamp renderer
   never renders a 150×150 art rect, and `clearImage` is only called from
   the art refresh path, which returns early when `processImageInfo` returns false.)

2. **`lib_ldf_mode = deep+` behaviour** — Confirm that `lib_ignore = JPEGDEC`
   is sufficient to prevent PlatformIO from resolving JPEGDEC even when it
   appears in the common `lib_deps`. If the library is still resolved despite
   the ignore, Option A (restructure lib_deps) must be revisited.

3. **Firmware size delta** — Measure linked binary size before and after for
   `cyd2usb_winamp`. Expect ~40 KB reduction. Document in TASK-062 notes.

## Exit criteria

- `pio run -e cyd2usb_winamp` compiles and links without any JPEGDEC symbol.
  Zero warnings referencing JPEGDEC, `JPEGPutMCU22`, or `pDraw`.
- `pio run -e cyd` and `pio run -e cyd2usb` compile without changes; both
  retain full album-art path and JPEGDEC linkage.
- `winampDisplay.h` contains no `processImageInfo` override.
- `cheapYellowLCD.h` contains no JPEG include, globals, or callbacks when
  `WINAMP_DISPLAY` is defined (verified by inspecting preprocessed output).
- DUT running `cyd2usb_winamp` firmware survives 5+ min of active playback
  without a Guru Meditation error.
- Serial log for `cyd2usb_winamp` shows no CDN connection attempts to
  `i.scdn.co` during normal playback.
