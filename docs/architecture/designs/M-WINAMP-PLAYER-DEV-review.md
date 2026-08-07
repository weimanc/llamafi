# M-WINAMP-PLAYER — Developer Review (implementability)

> Reviewer: Developer
> Date: 2026-08-07
> Scope: all five design documents + ADR-059, reviewed against the actual codebase
> Design set: [M-WINAMP-PLAYER.md](M-WINAMP-PLAYER.md) · [M-SDFS](M-SDFS-sd-card-exploration.md) · [M-AUDIO-ENGINE](M-AUDIO-ENGINE-extraction.md) · [M-PLEDIT-ABSTRACTION](M-PLEDIT-ABSTRACTION-playlist-source.md) · [local-playback](M-WINAMP-PLAYER-local-playback.md)
> Status: **Pre-implementation review — 2 blockers, 5 majors, 4 minors. One design claim is wrong.**

*(Note: requested as "@designer"; that role is not in this team's roster, so this is a Developer
implementability pass — the conventional complement to the VE testability pass, matching the existing
`*-DEV-review.md` / `*-VE-review.md` pairs in this directory.)*

---

## Verdict

The design set is unusually well-grounded — budgets are measured rather than estimated, the reuse
audit names real symbols at real line numbers, and the workstream split makes three of four pieces
independently landable. I checked the load-bearing claims against the source and they hold, with the
exceptions below.

Two findings would cause the implementation to diverge from the design on first contact. One of them
is a **factual error in ADR-059 D7** that would make the change larger and less robust than necessary.

---

## Blockers

### DEV-1 — The taskbar-cycle behaviour cannot live in `resolvePlayerSlot()`, and there are **two** dispatch sites

**Problem.** Local-playback §6 and ADR-059 D6 say: "Tap the player slot while the player is already
active → **cycle** … (`resolvePlayerSlot()`, extended to three)". That cannot work as described.

`switchApp()` early-returns on same-app (`main.cpp:2014`):

```c
void switchApp(AppId next) {
  if (next == currentAppId) return;
```

So when the player slot is tapped while already in that mode, `resolvePlayerSlot()` returns the
current app and `switchApp()` silently no-ops. The cycle decision has to be made **before**
`switchApp()`, at the dispatch sites — and there are two of them, which do **not** guard identically:

- `main.cpp:2001` — production taskbar dispatch, which additionally has **its own** same-app guard at
  `:2002` (`if (target != currentAppId)`) wrapping the press-anchored commit and slot repaint;
- `main.cpp:2793` — the serial-injection drain path, which calls `switchApp(target)` unconditionally
  and relies solely on `switchApp()`'s internal early return.

So the no-op happens at two different layers depending on the path, and a cycle branch added to only
one of them changes behaviour on only one path.

TASK-279's own comment requires these two to stay in lockstep ("invoked from **BOTH** dispatch sites
so the injected path the measurement plan depends on cannot drift from production"). An
implementation that adds cycling at only one site produces a feature that works by hand on the DUT but
not under serial injection — or the reverse. That is precisely the TASK-406 defect class (a code path
that behaved differently under test than in production), and it is invisible to a build gate.

**Severity:** Blocker — silent divergence between production and the harness.

**Resolution.** Introduce a single shared helper, e.g.
`AppId resolvePlayerTap(AppId tapped, bool playerAlreadyActive)`, that owns both the restore and the
cycle decision, and call it from both sites — same pattern as `shellTbPress()`/`shellTbCommit()`
already use for tap feedback. Keep `resolvePlayerSlot()` as the pure restore case so its existing
callers are undisturbed. State the two call sites explicitly in TASK-413.

### DEV-2 — ADR-059 D7's `TASKBAR_APP_COUNT` expression is wrong, and only one of three asserts needs changing

**Problem.** D7 says the taskbar tail becomes `Settings, WebRadio, LocalPlayer` and
`TASKBAR_APP_COUNT = (int)AppId::COUNT - 2`. Checked against `taskbar.h:34-56`, there are **three**
coupled static asserts, and the design's account of what breaks is inaccurate:

| Assert | Current | With `LocalPlayer` appended | Verdict |
|---|---|---|---|
| `AppId::WebRadio == COUNT - 1` | holds | **breaks** — LocalPlayer is last | must change |
| `AppId::Settings == AppId::WebRadio - 1` | holds | **still holds** — tail order is `Settings, WebRadio, LocalPlayer` | unchanged |
| `TASKBAR_ICON_COUNT == TASKBAR_APP_COUNT` | holds | **still holds** | unchanged |

And `TASKBAR_APP_COUNT = (int)AppId::WebRadio` (`taskbar.h:38`) — the existing expression — **also
still holds**, because `AppId::WebRadio`'s ordinal equals the number of apps before it, which is
exactly the taskbar app count.

So the design overstates the change (one assert, not "the assertion" plus a recomputed constant) and,
worse, the replacement it proposes is **less robust than what is already there**. `COUNT - 2`
hardcodes "there are exactly two eject-only modes" — the next eject-only mode silently breaks it,
which is the very failure D7 exists to prevent.

**Severity:** Blocker (the correction changes what gets written, and the proposed form reintroduces
the bug class).

**Resolution.** Keep the count derived, not literal. The most robust expression is anchored to the
*last taskbar slot* rather than to the eject-only tail:

```c
static constexpr int TASKBAR_APP_COUNT = (int)AppId::Settings + 1;
```

This survives any number of eject-only tail modes and is already protected by the second assert
(Settings is pinned as the last taskbar slot, TASK-347). Then replace only the first assert with one
expressing the invariant D7 actually wants:

```c
static_assert((int)AppId::Settings + 1 == TASKBAR_APP_COUNT,
              "Settings must remain the last taskbar slot; every AppId after it is eject-only "
              "and must have no taskbar slot. See NEW-APP-CHECKLIST.md.");
```

ADR-059 D7 and local-playback §6 both need correcting before TASK-413 is written.

---

## Majors

### DEV-3 — `SPickerList` is more coupled to `CountryEntry` than the reuse audit implies

The umbrella §3.1 lists `SPickerList` as reusable for the file browser, calling it "generalising its
item type". Checked (`settingsWidgets.h`): the coupling is structural, not just a typedef —
`#include "gen/countries.h"` at `:29`, `const CountryEntry* _items` at `:310`, and three direct field
reads: `strcasecmp(_items[i].code, code)` at `:293`, `_items[i].name` at `:356`, `_items[i].code` at
`:359`.

Reuse is still the right call — the scrollbar, drag, offset clamping and the CP-1 takeover contract
are the expensive parts and they are item-type-agnostic. But the mechanism matters at 216 B of debug
headroom: **templating it would instantiate the whole widget twice**. Specify a non-template
generalisation instead — a row-accessor callback pair matching the widget's existing
`onSelect`/`onCancel` style:

```c
void show(int16_t count,
          void (*rowText)(int16_t idx, char* out, size_t n, void* ctx),
          bool (*rowIsCurrent)(int16_t idx, void* ctx), ...)
```

The country picker becomes one caller of that, not the shape everyone else conforms to. Worth a line
in local-playback §4 so this is not rediscovered mid-task.

### DEV-4 — Beware NSDMI + brace-init in the new structs (`-std=gnu++11`)

Confirmed the toolchain is `-std=gnu++11` (framework-arduinoespressif32 `platformio-build-esp32.py:52`).
The interface sketches (`PlRow`, `Source`, `PlaylistSource`) are all valid C++11 **as written** —
no default member initialisers, so aggregate init works.

The trap is one edit away: the moment anyone adds a default (`const char* str = nullptr;`) the struct
stops being an aggregate under C++11 and every `Source{URL, path}` call site fails to compile. This
project has already paid for that once (TASK-327, `SButton` and friends — field-by-field assignment
throughout). Add a one-line note to the interface sketches so the next author does not learn it from
a build error.

### DEV-5 — `T_PLR_25`'s task-identity check needs a real handle

VE's review asks for `configASSERT(xTaskGetCurrentTaskHandle() == g_loopTaskHandle)` on the
open-next-track path. Agreed and cheap — but there is no `g_loopTaskHandle` today. Arduino's loopTask
handle is retrievable at `setup()` time via `xTaskGetCurrentTaskHandle()`; capture it into a file
static there. Small, but it is real work that belongs in TASK-410 alongside the `audio_eof_mp3`
handler, not discovered during TASK-418.

### DEV-6 — Mount-time `.tmp` sweep needs a definition of "stale"

Local-playback §10 says the mount-time sweep deletes "stray `.tmp` files older than the current
session". The device has no RTC and FAT timestamps depend on a clock the firmware may not have set
(NTP arrives after WiFi). "Older than the current session" is not evaluable at mount time on a device
that just booted.

Simpler and deterministic: use a **single fixed temp name** (`<name>.m3u.tmp`) and delete it
unconditionally at playlist load. There can only ever be one save in flight, the original `.m3u` is
untouched until the rename, and no timestamp is consulted. Suggest amending §10.

### DEV-7 — `run/check` gate count is stated inconsistently

The design says gates go "6 → 7" (umbrella §6). `check_build.sh` currently prints `[1/6]`…`[6/6]` plus
a `[7/7]` warn-only settings-wiring gate — so the existing numbering is already inconsistent in the
script itself, and several task entries in `tasks.md` cite "`run/check` 7/7" while others cite 6/6.
Adding an env makes this worse. Not a design defect, but TASK-422 should renumber the script's gate
labels in one pass rather than adding an eighth confusingly-numbered one.

---

## Minors

- **DEV-8** — M-AUDIO-ENGINE §3's `Source` uses `const char* str` for both URL and path. Fine, but the
  pump task's connect target is currently a fixed `char` buffer (`s_wrPumpConnectUrl`) precisely so
  the posting task does not outlive the caller's storage. Keep that ownership model — a bare
  `const char*` in the struct invites passing a stack pointer across the task boundary.
- **DEV-9** — Local-playback §2 sizes `entries[]` at 8 B/entry with `uint16 flags`, but only one flag
  bit ("staged") is specified. If nothing else claims those bits, `uint8` + explicit pad documents the
  intent better and leaves an obvious place for the next flag.
- **DEV-10** — The umbrella's reuse audit flags "ellipsis truncation — exactly one implementation".
  Confirmed: one match in the tree, inside `winampDisplay.h`. Extracting it in TASK-411 is right;
  note that its current form is entangled with the number-prefix and duration-column width maths
  (M-LIST-v3 §Feature 4), so `textFit()` should take a pixel budget, not a column spec.
- **DEV-11** — `browse-001` says "natural FAT order (no sort buffer)". Worth stating in the user-facing
  docs too: on a card written by drag-and-drop this is effectively arbitrary, which reads as a bug to
  anyone expecting alphabetical. Cheap mitigation if it grates: sort only the visible page.

---

## Confirmed-correct claims (spot-checked against source)

Recording these so a later audit does not re-litigate them:

| Claim | Verified |
|---|---|
| VSPI 18/19/23/5 free; TFT on HSPI 12/13/14/15/2; touch 25/32/33/36/39; DAC 26; LED 4/16/17; LDR 34; BL 21 | ✅ `platformio.ini`, `CYD28_TouchscreenR.h:36-40`, `ledFlow.h:19-21`, `backlightFlow.h:16` |
| `-DAUDIO_NO_SD_FS` is set in production and gates `connecttoFS()` | ✅ `platformio.ini:84`, `Audio.h:24/177-180` |
| `audio_eof_mp3` declared weak, implemented nowhere | ✅ `Audio.h:77`; no definition in tree |
| File seek API exists (`setFilePos`, `setTimeOffset`, `getAudioFileDuration`, `getAudioCurrentTime`) | ✅ `Audio.h:184-207` |
| SHUFREP atlas + draw + hit-test already ship | ✅ `skin_layout.h:97-99/145-151`, `winampDisplay.h:319-336/965-977` |
| `drawRepeat()` uses `s != 2 → ON`, so a binary Player encoding needs no render change | ✅ `winampDisplay.h:332` |
| PLEDIT implemented twice, sharing only `scrollTuning.h` | ✅ `winampDisplay.h` vs `webRadioApp.h`; `grep` confirms two users |
| `handleVolumeGesturePublic()` exists because `handleWinampInput()` is Spotify-hardcoded | ✅ `winampDisplay.h:600-612` (comment states it) |
| `get`/`set playerMode` are hardcoded two-valued | ✅ `main.cpp:3336`, `:3806-3807` |
| `mb_arena` is a generic allocator, not MP3-specific | ✅ `mb_arena.h` — fixed-slot free-list, no codec types |
| Helix MP3 / AAC / FLAC decoders all vendored; only MP3 in use | ✅ `lib/ESP32-audioI2S/src/{mp3,aac,flac}_decoder/` |
| Debug headroom 304 B, prod 13 160 B; SD/FS costs 88 B + 3 984 B | ✅ reproduced from `.map` extents |

---

## Handoff

**To Architect:** DEV-1 and DEV-2 need design edits before TASK-413 is written — D7's constant is
wrong and its replacement is less robust than the current code. DEV-3, DEV-4 and DEV-6 are
clarifications that prevent rediscovery mid-task.

**To PM:** neither blocker affects TASK-423, TASK-408, TASK-409 or TASK-411 — the critical path is
undisturbed. Both land on TASK-413, which is already gated behind TASK-410 and TASK-412, so there is
time. DEV-5 adds a small piece of work to TASK-410.

**To VE:** DEV-5 confirms your VE-2(3) ask is implementable but not free; the loopTask handle has to
be captured first. Your VE-1 debug surface and my DEV-1 shared-helper ask should land together — both
are about making the injected path and the production path provably the same code.
