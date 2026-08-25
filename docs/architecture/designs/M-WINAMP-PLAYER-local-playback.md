# Design — M-WINAMP-PLAYER-local: the Winamp-Player mode

> Owner: Architect
> Status: accepted
> As-built: 2026-08-07 (ADR-059 signed off; implementation authorised)
> Date: 2026-08-07
> Parent: [M-WINAMP-PLAYER.md](M-WINAMP-PLAYER.md) (workstream 4 of 4)
> Feeds: ADR-059 D3, D5, D6, D7, D8, D9
> Tracked-as: TASK-413 … TASK-422
> Registers: `browse-001` · `m3u-001` · `pledit-edit-001` · `playorder-001` · X052 · X056 · X057 · X058 · X059 · X060 · X061 · X062
> Depends on: M-SDFS (pass), M-AUDIO-ENGINE (landed), M-PLEDIT-ABSTRACTION (landed)

---

## 1. Scope

The user-visible feature: a third player mode that plays MP3s off the SD card, browses the
filesystem, reads and writes M3U playlists, edits playlists in PLEDIT, and drives the skin's
shuffle/repeat buttons.

## 2. Playlist model — one immutable array, two permutations

A playlist must survive being large without a proportional RAM cost.

| | Option | RAM @256 | Verdict |
|---|---|---|---|
| A | Full in-RAM entry array (`path[96] + title[48] + artist[32] + dur`) | ~46 KB | rejected on budget — caps out near 32 tracks |
| B | Playlist lives only on SD; seek and scan per read | ~0 | rejected on latency — O(N) scan per repaint, and reorder rewrites the file |
| C | **RAM index + on-demand row text** | ~3 KB | **lean** |

The naive form of C — "reorder permutes the index" — is wrong the moment a shuffle order exists: a
shuffle order storing *positions* is invalidated by any reorder, and a shuffle that permutes the
index in place writes shuffled order to the card on save. The model is therefore:

| Array | Type | @256 | Mutated by | Meaning |
|---|---|---|---|---|
| `entries[]` | `{uint32 offset, uint16 durSec, uint16 flags}` | 2 048 B | load only | **immutable** load-order index; subscripts are stable entry ids |
| `viewOrder[]` | `uint16` | 512 B | reorder, delete, add | what PLEDIT renders and SAVE writes |
| `playOrder[]` | `uint16` | 512 B | shuffle, delete, add | what playback advances through |

3 072 B, plus a ≤8-row text cache (8 × 72 B = 576 B) invalidated on scroll or mutation, plus a
staging arena for not-yet-written additions (16 × 96 B = 1 536 B). **Total ≈ 5.2 KB, all
heap-allocated on playlist load and freed on suspend** — see the parent design's budget section for
why nothing here may be static.

**Shuffle never touches `viewOrder`, so it provably cannot affect what PLEDIT shows or what SAVE
writes.** That is the entire reason for the split.

Operations:

- *reorder* — permute two `uint16` in `viewOrder`. No file I/O; `playOrder` untouched (dragging a row
  must not make the playback queue jump).
- *delete* — memmove `viewOrder`, drop the id from `playOrder`, fix the bag cursor if it pointed past
  the removed slot. No file I/O.
- *add* — append to `entries[]` with a `flags` "staged" bit (path in the staging arena), append the
  id to both permutations.
- *save* — stream `viewOrder`, copying each source line to `<name>.m3u.tmp`, emitting staged entries
  inline, then rename. One sequential pass, constant memory.
- *restore* — discard all three arrays, re-parse.

## 3. M3U

Extended M3U (`#EXTINF:<sec>,<Artist> - <Title>`). One pass at load builds `entries[]`; relative
paths resolve against the playlist's directory. Row text is read on demand, not cached in RAM.

The writer must emit staged entries **from the staging arena**, not by seeking the source file —
they have no backing offset yet. A naive copy loop gets this silently wrong: it drops the added
tracks while reporting success. Verification is host-side: write from the device, pull the card,
diff against expected order. Never verify a save by re-reading through the same structure that
produced it.

## 4. File browser

Modal full-canvas list over the player, entered by eject (§6).

**Reuse, not rebuild:** `settings/settingsWidgets.h` already ships `SPickerList` — a modal list with
scrollbar, drag handling, offset clamping, highlight, open-scrolled-to-selection, and a documented
CP-1 full-phase takeover contract. `settingsSection.h` provides `drawRow()`/`drawRows()`;
`touch/hitbox.h` provides the hit-testing primitives.

**How to generalise it (DEV-3).** The coupling to `CountryEntry` is structural, not a typedef:
`#include "gen/countries.h"` at `:29`, `const CountryEntry* _items` at `:310`, and three direct field
reads — `strcasecmp(_items[i].code, code)` at `:293`, `_items[i].name` at `:356`, `_items[i].code` at
`:359`. Reuse is still right — the scrollbar, drag, clamping and takeover contract are the expensive
parts and none of them care about the item type — but **do not template it**: at 216 B of debug
headroom, instantiating the whole widget twice is not affordable. Generalise with a row-accessor
callback pair matching the widget's existing `onSelect`/`onCancel` style:

```c
void show(int16_t count,
          void (*rowText)(int16_t idx, char* out, size_t n, void* ctx),
          bool (*rowIsCurrent)(int16_t idx, void* ctx),
          void (*onSelect)(int16_t idx, void* ctx),
          void (*onCancel)(void* ctx), void* ctx);
```

The country picker then becomes one caller of that shape rather than the shape everyone else must
conform to.

Behaviour:

- One directory level at a time via `SD.open(dir)` + `openNextFile()`, **paged**, so loopTask never
  stalls the audio pump (§7).

  **Page size corrected 2026-08-08 from TASK-408's measurement.** `T_SD_07` measured **26.4 ms per
  directory entry** (5.3 s for 200 files), with per-entry cost rising as the directory grows. The
  design's original "≤32 entries per tick" is **845 ms of blocking** — five times what the 6 400 B
  InBuff can absorb (~160 ms of 320 kbps audio). It would underrun on the first page.

  Revised policy, in three parts:

  1. **Batch ≤4 entries per tick** (~105 ms worst case, still under the InBuff window with margin).
  2. **Only the visible window is needed to paint.** The browser shows ~8 rows, so the first screen
     costs ~210 ms across two ticks — the full directory walk is *not* on the critical path for
     showing something. Paint as soon as the first window is filled, keep filling behind it.
  3. **Scrolling past the loaded region waits**, with the existing busy indicator
     (`hasPendingAsync()`), rather than blocking to pre-walk.

  Consequence to accept: FAT `openNextFile()` is sequential-only, so reaching entry N is inherently
  O(N) — a 200-file directory takes ~5 s to become fully scrollable. That is a property of the
  filesystem, not of this design. If it grates in use, the answer is a cached per-directory index on
  the card, not a bigger batch. **Do not raise the batch size to make scrolling feel faster** — that
  trades an audible underrun for a UI nicety.
- Directories first, then `.mp3`/`.m3u`, natural FAT order — no sort buffer.
- Tap file → play now. Tap directory → descend. `..` → ascend. Tap `.m3u` → load as active playlist.
- Edit-mode `[+]` → append to the current playlist (staged).

### 4.1 Browsing while a track plays is over-budget on DRAM (TASK-521, measured 2026-08-18)

§9 and §4 both assume the browser and the decoder coexist. On `cyd2usb_player` they **do not fit**,
and the shortfall is in byte-addressable DRAM, not in SD handles, FATFS locking or directory size.
Measured on the DUT, `cyd2usb_player`, real MP3 playback from `/mp3/rel.m3u`:

| moment | `free8` (`MALLOC_CAP_INTERNAL\|8BIT`) | `largest8` |
|---|---|---|
| Player entered, `_pl` loaded, browser arrays **not** claimed | 77 448 B | 73 716 B |
| same, browser arrays claimed (5 120 B) | 72 288 B | 69 620 B |
| decoder running, browser arrays **not** claimed | **5 108 B** | **3 188 B** |
| decoder running, browser arrays claimed | **284 B** | **140 B** |

Starting playback costs ~72 KB of DRAM: the 24 576 B Helix arena (HWM 23 216 B), the 8 192 B
`wrpump` stack, and ~39 KB of `Audio` object + `InBuff` + I2S DMA buffers. What is left is smaller
than what the browser needs — 5 120 B of entry arrays **plus** ~700 B for the `vfs_fat_dir_t`
(`FF_DIR` + `FILINFO` + `struct dirent`) that `vfs_fat_opendir()` allocates on every `opendir()`.

**Allocation order is not the lever.** It only decides *which* allocation fails:

- arrays not yet claimed → `FileBrowser::alloc()` fails (`alloc FAILED (5120 B) … largest=3188`);
- arrays already claimed → `opendir()` fails with `ENOMEM`, surfacing as the framework's bare
  `VFSFileImpl(): opendir(/sd/probe200) failed`.

Both were reproduced deliberately. So `open()` cannot be fixed by claiming memory earlier, and it
cannot be fixed by shrinking the arrays further either: `largest8` is 3 188 B during playback, so
the 4 096 B `_files` array cannot be served at *any* ordering, and coming down to 48 files would
truncate this card's real 53-file `/mp3` — the capability the sizing note in `fileBrowser.h` has
already refused to trade away three times.

Hypotheses eliminated by measurement, so they are not re-litigated:

- **`kSdMaxFiles` / open-handle exhaustion.** `sdslots` reports **2 of 3 slots free** during
  playback and `get plCount` reports `fileOpen:false` — the playlist file is *not* held open while a
  track plays. Mechanically it could not have been the cause either: `CONFIG_FATFS_FS_LOCK=0`, so
  `f_opendir()` has no lock table and cannot return `FR_TOO_MANY_OPEN_FILES`, and `vfs_fat_opendir()`
  never touches the context's `files[]` array. Raising `kSdMaxFiles` would have **made this worse** —
  +4 136 B of exactly the resource that is exhausted.
- **FATFS mutex contention with the audio pump (the X052 story).** `opendir()` returns in
  247–558 µs during playback, never `ETIMEDOUT`; `FF_FS_TIMEOUT` is 10 s and is never approached.
- **Something specific to a 200-entry directory.** `/`, `/mp3` and `/probe200` behave identically —
  `opendir()` resolves a path, it does not enumerate.

**The decision this needs (Architect).** Making browse-during-playback work requires reclaiming
~6 KB of DRAM from the playback working set. Candidates, with what is known about each:

1. `wrpump` stack 8 192 B → measured high-water use **3 280 B**, i.e. 4 912 B spare. The largest
   single reclaim available, and the one with real risk: it needs a soak, not an inspection.
2. Arena cap 24 576 B vs measured HWM 23 216 B → ~1 360 B, safe but not sufficient alone.
3. `Audio`/`InBuff`/I2S DMA sizing → trades directly against underrun margin (§4's batch policy is
   already sized off that same window).
4. Redesign the browser to hold a window rather than a full-directory cache — §4 explicitly rejected
   re-walking per repaint on cost grounds, so this is a re-opening of that decision, not a tweak.

Until one of those lands, `open()` fails **honestly**: it records why (`nomem` / `notfound` /
`allocfail` / `nosd` / `notdir` / `ioerr`), logs `errno`, `free8` and `largest8`, and reports the
reason through `set fbOpen` and `get fbState`. Both replies are emitted from a stack buffer via
`Serial.write()`, not `Serial.printf()` — `Print::printf()` `malloc()`s whenever the formatted line
exceeds its 64 B stack buffer and silently returns 0 when that fails, which is why the first
investigation saw `get fbState`, `get heap` and `get plCount` return *nothing at all* under
`free8=284` and read it as a dead console.

## 5. PLEDIT edit mode

| | Option | Verdict |
|---|---|---|
| i | Long-press row → floating action menu | long-press has no precedent here; competes with drag arming; cramped over a 65 px band |
| ii | **Edit mode + bottom button strip** | **lean** |
| iii | Drag-to-reorder with long-press arm | rejected: 16 px rows on a resistive panel, in direct collision with the TASK-277 velocity-scroll gesture |

PLEDIT title-bar tap toggles edit mode. In edit mode the bottom bar — today only total-time text —
becomes `[+] [–] [↑] [↓] [SAVE]`, and row tap selects rather than plays. Skin-authentic (real
Winamp's ADD/REM/SEL/MISC/LIST strip), no new gesture vocabulary, and it reuses
`settingsWidgets.h`'s `SButton` / `sButtonBar()`.

**OQ** — does `bake_skin.py`'s `build_pledit_atlas()` already crop ADD/REM/SEL/MISC/LIST from
`PLEDIT.BMP`? If not: bake-tool change, new `skin_layout.h` constants, `golden.sha256` re-bake, T025
determinism re-check.

## 6. Mode topology and control remap

`PlayerMode { Spotify=0, WebRadio=1, Player=2 }` — `g_settings.playerMode` already stores a `uint8_t`,
so the SPIFFS schema is unchanged; only the value domain widens.

**Mode cycling moves off eject onto the taskbar Winamp icon.** Tap the player slot from another app →
restore the persisted mode. Tap it while the player is already active → cycle Spotify → WebRadio →
Player → Spotify, and persist. This gives the taskbar's active-slot tap a second meaning it has for no
other app — a deliberate asymmetry that belongs in the taskbar contract.

**Where that logic lives (corrected 2026-08-07, DEV-1).** *Not* in `resolvePlayerSlot()`, as this
design originally said. `switchApp()` early-returns on same-app (`app/src/main.cpp`, `switchApp`), so a tap on the
already-active slot resolves to the current app and silently no-ops — and the two dispatch sites guard
differently:

| Site | Path | Same-app guard |
|---|---|---|
| `app/src/main.cpp` (`shellTbRelease`) | production taskbar dispatch | **its own** `if (target != currentAppId)` guard, *plus* `switchApp()`'s |
| `app/src/debug/serialConsole/cmdTouch.h` (`cmdTap`) | serial-injection drain | `switchApp()`'s internal return only |

A cycle branch added to one site only makes the feature behave differently under the harness than in
production — the TASK-406 defect class, invisible to every build gate. Introduce one shared helper,
`resolvePlayerTap(AppId tapped, bool playerAlreadyActive)`, owning both decisions and called from
**both** sites — the same discipline TASK-279 imposes on `shellTbPress()`/`shellTbCommit()`.
`resolvePlayerSlot()` stays as the pure restore case so its existing callers are undisturbed.

**Eject becomes "load media from this source":**

| Mode | Eject |
|---|---|
| Spotify | TLS reset + force poll (the reconnect currently on the Winamp logo tap, TASK-053f) |
| WebRadio | station-list refresh / browse |
| Player | open the file browser |

The Winamp logo tap keeps its TLS-reset behaviour — duplicating an affordance is harmless, silently
deleting a recovery path is not.

**Taskbar invariant (corrected 2026-08-07, DEV-2).** This design originally claimed the tail change
forces `TASKBAR_APP_COUNT = (int)AppId::COUNT - 2` and a rewrite of "the assertion". Checked against
`taskbar.h:34-56`, that is wrong on three counts — and the proposed replacement was worse than the
existing code, because `COUNT - 2` hardcodes "exactly two eject-only modes" and the third one breaks
it silently, which is the failure this invariant exists to prevent.

| Assert / constant | With `LocalPlayer` appended |
|---|---|
| `AppId::WebRadio == COUNT - 1` | **breaks** — the only one that does |
| `AppId::Settings == AppId::WebRadio - 1` | still holds (tail is `Settings, WebRadio, LocalPlayer`) |
| `TASKBAR_ICON_COUNT == TASKBAR_APP_COUNT` | still holds |
| `TASKBAR_APP_COUNT = (int)AppId::WebRadio` | still holds — the ordinal *is* the taskbar app count |

Change exactly one thing, and keep the count derived rather than literal by anchoring it to the **last
taskbar slot** instead of the eject-only tail:

```c
static constexpr int TASKBAR_APP_COUNT = (int)AppId::Settings + 1;

static_assert((int)AppId::Settings + 1 == TASKBAR_APP_COUNT,
              "Settings must remain the last taskbar slot; every AppId after it is eject-only "
              "and must have no taskbar slot. See NEW-APP-CHECKLIST.md.");
```

This survives any number of eject-only tail modes. The Settings-pinning assert (TASK-347) and the
icon-count assert (TASK-242) are untouched and keep doing their jobs.

Cycling must **skip compiled-out modes** (parent design's build-variant section).

### 6.1 The debug surface is hardcoded two-valued — widen it in the same task

Both halves of the `playerMode` serial surface assume the field is a boolean, and neither fails
loudly when it stops being one:

| Site | Code | Behaviour at `playerMode = 2` |
|---|---|---|
| `get` — `app/src/debug/serialConsole/cmdGet.h` (`cmdGet`) | `uint8_t pm = g_settings.playerMode ? 1 : 0;` then `name = pm ? "WebRadio" : "Spotify"` | **reports Player mode as `WebRadio(1)`** — silently wrong, no error |
| `set` — `app/src/debug/serialConsole/cmdSet.h` (`cmdSet`) | `idx < 0 \|\| idx > 1` → reject; strings only `"spotify"` / `"webradio"` | `set playerMode 2` is rejected as a bad value — Player mode is unreachable from the harness |

This is not cosmetic. The TASK-407 instrumentation landed 2026-08-07 (`run_serialdbg_tests.py`,
entry/exit `get playerMode` snapshots in every `run/test*` session) reads exactly this getter. Once
Player mode exists, that instrumentation will log `WebRadio(1)` for a device sitting in Player mode —
actively misleading for the very bug it was added to catch, and misleading in a way that looks like
data rather than an error.

**TASK-413 widens both** — getter emits the true `uint8_t` with a three-way name mapping, setter
accepts `0..2` and `"player"` — and does it in the same commit as the enum change, not as a
follow-up. VE should treat "`get playerMode` round-trips all three values" as a gate on that task.

## 7. Transport capabilities — un-gating shuffle, repeat, seek

The skin work is already done. `chrome-001` bakes `SKIN_SHUFREP` (75×30, four sprites:
`SR_SHUFFLE_ON/OFF`, `SR_REPEAT_ON/OFF`); `winampDisplay.h` already draws them (`drawShuffle()`,
`drawRepeat()` at `SHUFFLE_X=164`, `REPEAT_X=211`), hit-tests them, and caches them with a 2 s
optimistic hold. Nothing needs baking, cropping or drawing.

What blocks reuse is that it is hardcoded Spotify — hit-tested inside `handleWinampInput()` and
dispatched straight to `spotifyTask::ACT_SHUFFLE` / `ACT_REPEAT`. Replace mode-hardcoding with a
per-mode capability mask:

| Mode | `CAP_TRANSPORT` | `CAP_SEEK` | `CAP_SHUFFLE` | `CAP_REPEAT` |
|---|---|---|---|---|
| Spotify | ✓ | ✓ (API round-trip) | ✓ | ✓ tri-state, server-owned |
| WebRadio | ✓ (play/stop) | ✗ | ✗ | ✗ |
| Player | ✓ | ✓ **real** | ✓ | ✓ binary |

`handleWinampInput()` consults the mask; a zone whose capability is absent is neither drawn nor
hit-tested. WebRadio advertises only `CAP_TRANSPORT`, so its behaviour is unchanged — this is a
refactor for it, and any delta is a regression.

**Seek becomes real for local files.** The vendored `Audio` exposes `setFilePos()`, `setTimeOffset()`,
`getFilePos()`, `getFileSize()`, `getAudioFileDuration()`, `getAudioCurrentTime()`. The posbar is a
genuine scrub against real duration — not WebRadio's estimated slew (M-WEBRADIO-POSBAR-SLEW/SMOOTH),
not Spotify's `seek()` round-trip.

The rendered state must be sourced from the mode too: `drawShuffle`/`drawRepeat` read
`lastShuffleRendered`/`lastRepeatRendered` fed from `spotifyTask::Snapshot`. Same seam shape as
`PlaylistSource` — the mode supplies state, the renderer stays common.

## 8. Play-order engine

Only `LocalPlaylistSource` needs this. Spotify's shuffle/repeat live server-side; WebRadio has no
ordered list.

**Repeat is binary in v1.** The skin carries two repeat sprites and Winamp 2.x's repeat is a binary
"repeat playlist" toggle. Encoding reuses the shipped tri-state domain so the render helper is
untouched: Player emits only `2` (off) and `0` (repeat-all), and `drawRepeat()`'s existing
`s != 2 → ON` rule already renders both. Repeat-one is deferred — Spotify already has two
indistinguishable ON states, excusable there because the phone app is the source of truth,
unacceptable on a device that is its own only display. Adding it means a synthetic "1" glyph over
the ON sprite (Winamp 5's solution; ~10 lines, no re-bake).

**Shuffle is a materialised bag, not a dice roll.** Fisher-Yates permutation of `playOrder[]` on
toggle-on; advance walks it. Re-rolling a random index per `next` repeats tracks and starves others —
the standard way this ships broken.

End-of-playlist, all four cells:

| | repeat off | repeat all |
|---|---|---|
| **shuffle off** | stop at last row | wrap to `viewOrder[0]` |
| **shuffle on** | play each track once, then stop | reshuffle and continue |

The reshuffle on wrap must not re-open with the track that just finished — a one-line guard (swap
`playOrder[0]` with a random other slot on collision), and the classic annoyance if omitted.

Falling out of the cursor model, to be honoured rather than reinvented:

- **Prev under shuffle** walks *back* along `playOrder`, replaying history. It does not roll a new
  random. This is why the order is materialised rather than generated lazily.
- **Tap-to-play under shuffle** moves the bag cursor to that entry's position in `playOrder` (O(N)
  scan, trivial at 256) and continues. It does not reshuffle.
- **Edits under shuffle** — see §2.

**Auto-advance** hangs off `audio_eof_mp3()`, which fires on the audio pump task under the engine
mutex and may only set a flag — see [M-AUDIO-ENGINE](M-AUDIO-ENGINE-extraction.md) §4. The bag lives
in loopTask-owned state and must not be mutated from the pump task.

**Persistence:** `player.shuffle` / `player.repeat` in `g_settings`, Player-scoped. Spotify's stay
server-owned and are never written there.

## 9. Concurrency

Two tasks touch the filesystem: **loopTask** (browser paging, playlist rows, save) and the **audio
pump** (`Audio::loop()` refilling from `audiofile`). ESP-IDF's FATFS VFS serialises per volume — safe
but *blocking*: a bulk directory read on loopTask can stall the pump into an underrun.

1. Bulk loopTask SD I/O is chunked (≤32 dir entries, one row batch per tick).
2. Playlist **save** is the one unbounded operation. It runs only from edit mode and **pauses
   playback** for its duration — a deliberate, visible modal action, not a background write.
3. The engine mutex protects `Audio` method calls, **not** the filesystem. Do not widen it.
4. `LocalPlayerApp::hasPendingAsync()` is true while a browser page or save is in flight, and
   `isNavigationTap()` excepts the browser's back/up zone — otherwise the shell busy gate swallows
   navigation taps (TASK-384 precedent, confirmed on real hardware).

## 10. Lifecycle — init / resume / suspend / teardown

`WebRadioApp::suspend()` is the precedent and is fully specified; LocalPlayer mirrors its shape.
**Ordering matters and is not negotiable** — pump task before `Audio` before arena, mirroring
TASK-278's teardown and DEV-2-3's acquire ordering.

**`init()`** (first entry only) — allocate nothing. Register the source with `pleditView`. All buffers
are acquired in `resume()`, so a compiled-in-but-never-entered mode costs nothing but flash.

**`resume()`** — **order revised 2026-08-09 (ADR-059 D1 amendment #2): arena BEFORE mount.**
1. `mb_arena_acquire()` — **first**, from the least-fragmented heap state. The arena needs 23 216 B
   **contiguous**; FATFS needs ~19 KB in many small pieces, which tolerate fragmentation. Mounting
   first leaves only ~1.4 KB of largest-free-block margin over the arena at `max_files=3` and none at
   all at 4. Failure → degraded (`hasError()`), do **not** mount — a clean early failure beats a
   successful mount followed by a play that mysteriously never starts.
   *In Player mode the arena is mode-scoped, not play-scoped* — held for the whole session, released
   in `suspend()`. A deliberate departure from WebRadio's JIT-per-play discipline, justified because
   Player needs it for essentially the entire session and pre-committing makes acquisition
   deterministic.
2. `sdfs::mount()` — lazy, VSPI, 4 MHz, **`max_files=3`** (audio + browser directory handle + the
   entry `openNextFile()` returns; save is also 3). Failure → degraded, release the arena, bail.
3. Allocate the playlist model (§2, ≈5.2 KB heap). Failure → degraded, unmount, release, bail.
3. Restore last playlist + shuffle/repeat from `g_settings`; rebuild `playOrder`.
4. Seed `winampDisplay`'s volume/shuffle/repeat caches from Player state — they may hold Spotify's or
   WebRadio's values from before the switch (the precedent this exists for is `app/src/apps/spotifyApp.h` (`SpotifyApp::resume`)).
5. Repaint.

**`suspend()`** — in this order:
1. Cancel live gestures: reset scroll accumulators, `winampDisplay.resetDragState()` (shared state —
   a mid-drag mode switch must not leave `D_VOLUME_DRAG` stuck; TASK-352 precedent).
2. Close the browser if open; discard its page state.
3. **If a save is in flight, finish it** — an interrupted save leaves a stray `.tmp` and possibly a
   half-written playlist. Save is bounded and rare; completing it is correct. Rename is the atomic
   commit point.
4. `audioEngine::stop()` → pump-task teardown → `Audio` delete → `mb_arena_release()`, delegated to
   the engine and using the same request-posting discipline as WebRadio's `CONNECTING` case (never
   block loopTask on an in-flight connect — TASK-398).
5. Close any open `File`; free the playlist model.
6. `sdfs::unmount()`.
7. Persist mode/shuffle/repeat with the unchanged-value skip (flash wear).

**Unclean paths.** Reboot or power loss mid-save leaves `<name>.m3u.tmp` on the card. The original
`.m3u` is untouched until the rename, so the playlist is never lost — only unsaved edits are.

*Sweep policy (corrected 2026-08-07, DEV-6).* The original "delete stray `.tmp` files older than the
current session" is not evaluable: this device has no RTC, and NTP arrives after WiFi — at mount time
there is no trustworthy clock to compare FAT timestamps against. Use a **single fixed temp name**
(`<name>.m3u.tmp`) and delete it unconditionally at playlist load. Only one save can ever be in
flight, so there is nothing to disambiguate and no timestamp is consulted.

**Invariant to assert in the debug build:** on suspend completion, `mb_arena_active() == false`, no
`File` handle open, SD unmounted, playlist pointers null. Same shape as the existing arena
acquire/release balance invariant.

## 11. Open questions

- ~~**OQ1** — text encoding~~ — **RESOLVED 2026-08-11 (TASK-415)**. `app/src/util/asciiFold.h`,
  `textfold::foldUtf8(in, out, n)`: one pass, no allocation, ASCII passes through; Latin-1
  Supplement and Latin Extended-A fold to their base letters (`é`→`e`, `Æ`→`AE`, `ß`→`ss`,
  `ł`→`l`); typographic punctuation substitutes (curly quotes, en/em dash, `…`→`...`, NBSP);
  everything else — CJK, emoji, malformed or truncated UTF-8 — becomes one `?` **per codepoint**,
  and control characters become spaces so a row can never smuggle a line break into the renderer.
  Truncation is substitution-safe: a replacement that does not fit whole is not written at all.
  Verified on the DUT through `get plFold <text>`, which is the shipped helper, not a copy of it.

  Two decisions inside the resolution worth keeping: (a) the fold happens in the **source**, when
  the row text is composed, not in the renderer — `PlRow::text` is defined as already-renderable,
  so the contract change the open question warned about turned out to be no change at all;
  (b) `LocalPlaylistSource` uses it, and **`SpotifyQueueSource` and `StationListSource` do not yet**.
  The latent bug is real there (an accented artist name renders as two GLCD symbols today), but
  retro-fitting it changes shipped pixels and would have to answer to TASK-411/412's pixel-identity
  gate — a separate change with its own before/after, not a rider on this one. Tracked as TASK-428.
- **OQ2** — PLEDIT button sprites (§5).
- **OQ3** — playlist location and naming: `/playlists/*.m3u`, or alongside the media? Default name,
  auto-restore-last behaviour.
- **OQ4** — ID3 depth: does the index cache `#EXTINF` metadata (avoiding an ID3 read per row) or
  always read tags? M-SDFS's numbers settle it.
- **OQ5** — eject muscle memory: eject has meant "switch to radio" since M-WEBRADIO shipped. The
  remap is the operator's explicit call; recorded so it is not later mistaken for a regression.
- **OQ6** — TASK-407 (`g_settings.playerMode` reverting between DUT sessions with no manual trigger
  found) is **open**, and §6 widens that exact field's domain. Close 407 first, or accept debugging a
  three-valued version of an unexplained bug.

## 12. Test & validation

Ids reserved in the `T_PLR_` family, grouped by task. VE owns the suite and may renumber; the
*properties* are the design's contribution.

> **Revised 2026-08-07 after [VE review](M-WINAMP-PLAYER-VE-review.md).** Changes folded in below:
> `T_PLR_25` is **reclassified to a runtime assert** (ADR-059 D12) — strictly stronger than a probe,
> because it holds on every execution; `T_PLR_21`/`22` become reachable via the TASK-418 debug surface
> instead of hours of playback (VE-1); `T_PLR_17`/`18` inherit the ≥3-run baseline protocol (D13);
> `T_PLR_30` gains a precondition (VE-10); `T_PLR_36` names its flash script (VE-11); `T_PLR_39`
> becomes injection-driven (VE-12); `T_PLR_41` added for the card-removal path (VE-13).
>
> **Debug surface these depend on** (product surface, shipped with the feature — ADR-059 D12):
> `get plOrder` · `get plCursor` · `set plCursor <n>` · `advance next|prev` (steps the order engine
> **without decoding audio**), all delivered by TASK-418.

### TASK-413 — `AppId::LocalPlayer`, three-way mode, taskbar cycle

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_01` | Taskbar tap cycles the mode | DUT serial — tap active player slot ×4 | Spotify → WebRadio → Player → Spotify → WebRadio |
| `T_PLR_02` | Mode persists across reboot | DUT — set each mode, reboot | restored 3/3 |
| `T_PLR_03` | Taskbar has no leaked slot | DUT serial + eyeball — `get taskbar` | exactly `TASKBAR_APP_COUNT` slots; neither WebRadio nor LocalPlayer present (TASK-242 regression) |
| `T_PLR_04` | **`get`/`set playerMode` round-trip all three values** | DUT serial | `set playerMode player` → `get` returns `Player(2)`; all three names and all three numerics accepted; §6.1 |
| `T_PLR_05` | Tap from another app restores, not cycles | DUT serial — switch away, tap player slot | lands on the persisted mode, unchanged |

### TASK-414 — eject remap

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_06` | Eject is per-mode | DUT serial — eject in each mode | Spotify → TLS reset + force poll; WebRadio → station refresh; Player → browser opens |
| `T_PLR_07` | Logo tap still resets TLS | DUT serial | unchanged from TASK-053f behaviour |

### TASK-415 — M3U + index model

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_08` | ≥100-track M3U loads | DUT serial — `get plCount` | count correct; load time recorded |
| `T_PLR_09` | Scroll end to end during playback | DUT — scroll full list while a track plays | no audible underrun, no dropped frames |
| `T_PLR_10` | Relative paths resolve | DUT — playlist referencing `./sub/x.mp3` | resolves against the playlist's directory |
| `T_PLR_11` | Malformed M3U degrades | DUT — truncated file, missing `#EXTINF`, CRLF, BOM | loads what it can; no crash; unreadable rows render the placeholder |
| `T_PLR_12` | Index memory is bounded and freed | DUT serial — heap before load / after load / after suspend, quiesced; report **largest-free-block alongside free-heap** (fragmentation is the real risk per M-HEAP-FRAGMENTATION, and a clean free-heap figure hides it — VE-15). **All three samples must come from ONE boot** | ≤5.2 KB delta; returns to baseline ±256 B on suspend — **within-run deltas only** |

> **VE correction, 2026-08-15 — `T_PLR_12`: cross-run absolute `lfb` comparisons are struck.**
> The id's own criteria (≤5.2 KB delta, ±256 B on suspend) are **within-run** and stand unchanged —
> `run_serialdbg_tests.py::t_plr_12` takes baseline / loaded / post-suspend on a single boot. What
> must never be carried forward is an absolute largest-free-block figure compared against a number
> from a **different run or date**: at a fixed commit the idle baseline moved ~26 KB between
> 2026-08-11 and 2026-08-15 (`lfbInt` 69 620 → 42 996, TASK-427 vs TASK-442), and BP-055 already
> records that this 32-bit metric over-reports. The historical
> "largest-free-block unchanged 19 444 → 19 444 → 19 444" note is a within-run triple and is fine;
> treating 19 444 as an *expected value* for a future run is not. Also note BP: no heap number is
> trustworthy before ~150 s of settle (TASK-425).

### TASK-416 — file browser

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_13` | Paging never stalls audio | DUT — browse a ~200-file directory during playback | no underrun; no single tick > the M-SDFS latency bar |
| `T_PLR_14` | Navigation taps survive the busy gate | DUT serial — tap back/up while a page read is in flight | tap honoured (`isNavigationTap`); TASK-384 regression |
| `T_PLR_15` | Busy indicator reflects real work | DUT serial — `hasPendingAsync()` during a page read | true from enqueue to completion, self-clears |
| `T_PLR_16` | Deep/edge paths | DUT — nested dirs, empty dir, 8.3 and long names, non-audio files | descend/ascend correct; non-audio filtered; no crash |

### TASK-417 — capability mask

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
> **Corrected 2026-08-17 (P0).** These two rows were assigned the other way round and disagreed with
> the implementation: `app/tools/run_serialdbg_tests.py:5958` is Spotify, `:6019` is WebRadio. **The
> spec was changed to match the code, not the reverse** — the runner's numbering is already baked into
> five closed quality artifacts (`docs/quality/lessons_learned.md:2132`, `:2153`;
> `docs/quality/best_practices.md:597`, `:627`; `docs/quality/audit_log.md:1764`) and a passed gate
> (`docs/project/tasks-archive.md:16689`). Renaming the code would falsify all of them.

| `T_PLR_17` | **Spotify unchanged** | DUT serial — repeat cycle + optimistic hold | 2→1→0→2 preserved; `SHUFREP_OPTIMISTIC_HOLD_MS` behaviour identical |
| `T_PLR_18` | **WebRadio unchanged** | DUT serial — hit-test sweep across the whole main window | no shuffle/repeat/seek zone drawn or hit-tested; identical `lastTouchResult` region map to baseline |
| `T_PLR_19` | Player advertises all four | DUT serial | shuffle, repeat, seek, transport all drawn and hit-testable |

### TASK-418 — play-order engine

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_20` | Shuffle bag visits each track once | DUT serial — 20-track playlist, `advance next` ×20, `get plOrder` | 20 distinct ids, no repeat within the cycle |
| `T_PLR_21` | All four end-of-list cells | DUT serial — `set plCursor <last>` then `advance next`, per combination | matches §8's table exactly, 4/4. **No real-time playback** — VE-1 |
| `T_PLR_22` | Reshuffle does not re-open with the last track | DUT serial — 20 forced wraps via `set plCursor <last>` + `advance next` | 0/20 collisions. Was ~3 h of playback as originally written (VE-1) |
| `T_PLR_23` | Prev replays history | DUT serial — `advance next` ×5, `advance prev` ×5, diff against `get plOrder` | exact reverse sequence, no new randoms |
| `T_PLR_24` | Tap-to-play moves the cursor | DUT serial — tap a row under shuffle, read `get plCursor`, then `advance next` | cursor moves to that entry's bag position; `get plOrder` unchanged (no reshuffle) |
| `T_PLR_25` | Auto-advance works end to end | DUT — play 5 **short** files to completion (the one real-playback case, proving `audio_eof_mp3` drives the same path the debug surface drives) | advances 5/5; no WDT |
| ~~`T_PLR_25b`~~ | ~~no `connecttoFS` from the pump task~~ | **reclassified to a runtime assert** (ADR-059 D12): `configASSERT(xTaskGetCurrentTaskHandle() == g_loopTaskHandle)` on the open-next-track path | panics in *every* debug run, not probed once |
| `T_PLR_26` | Shuffle/repeat persist | DUT — set, reboot | restored; Spotify's values never written to settings |

### TASK-419 — real seek

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_27` | Posbar scrubs against real duration | DUT — drag to 25/50/75 % | `getAudioCurrentTime()` within ±2 s of target 3/3 |
| `T_PLR_28` | Seek during playback does not underrun | DUT — 20 scrubs during playback | no underrun, no decoder reinit failure |

### TASK-420/421 — edit mode, save, restore

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_29` | Reorder/delete/add mutate only RAM | DUT serial — mutate, then read the card | file on card unchanged until SAVE |
| `T_PLR_30` | **Shuffle ON + reorder + SAVE writes display order** | **host** — pull the card, diff. **Precondition: N ≥ 20 and assert `get plOrder` != `viewOrder` before saving** — Fisher-Yates can return identity on a short list, and the test would pass proving nothing (VE-10) | file matches `viewOrder`, **not** `playOrder`. The destructive failure §2 exists to prevent |
| `T_PLR_31` | Staged adds survive SAVE | host — add from browser, save, pull the card | added tracks present, in position — the failure mode that reports success while dropping them |
| `T_PLR_32` | SAVE is atomic | DUT — reboot mid-save (deliberate), remount | original `.m3u` intact; stray `.tmp` swept at mount |
| `T_PLR_33` | Restore discards edits | DUT serial — mutate, restore, compare | matches the on-card file |
| `T_PLR_34` | Delete repairs both permutations | DUT serial — delete under shuffle, then next | no dangling id; cursor valid; playback continues |

### TASK-422 — variants, soak, close-out

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_PLR_35` | Each variant builds and boots | host + DUT — prod (all three) and `cyd2usb_player` | both build; both boot to a valid mode |
| `T_PLR_36` | **Persisted mode naming an absent mode falls back** | DUT — set Player, then **`run/flash` (app-partition only, SPIFFS survives)** a variant without it, boot. **Never `run/flash-fs`** — it formats SPIFFS, wipes the persisted mode and makes the test vacuously pass (VE-11) | falls back to the first compiled-in mode; **no null-app crash**. Only reproducible over *existing* settings — a clean flash will not catch it (X064) |
| `T_PLR_37` | Single-mode build does not cycle | DUT serial — tap active slot on `cyd2usb_player` | no-op, no crash |
| `T_PLR_38` | Suspend leaves nothing behind | DUT serial — 20 mode switches in/out of Player | §10 invariant clean each time: arena inactive, no `File` open, SD unmounted, pointers null |
| `T_PLR_39` | Sustained soak | DUT — ≥30 min playback with concurrent browsing and scrolling, **driven from the injection queue** (`tap`/`tick`/`release`) so it is repeatable and re-runnable after later changes, not a human poking the screen (VE-12) | no underrun, no heap decline, no WDT |
| `T_PLR_40` | Checklist walked | host — `NEW-APP-CHECKLIST.md` | every item recorded for `AppId::LocalPlayer` |
| `T_PLR_41` | **Card removed mid-playback degrades** | DUT — physically remove the card during playback (VE-13) | no WDT, no crash; `hasError()` true; taskbar indicator red; Player mode still exitable |

**Validation notes.** `T_PLR_30`, `T_PLR_31` and `T_PLR_36` are the three that would ship broken
while looking fine, and all three are verified **off the device** — from the card or from a variant
reflash — because each has a failure mode where the device confidently reports success.
`T_PLR_17`/`T_PLR_18` protect two shipped modes from a refactor they get no benefit from.
`T_PLR_09`, `T_PLR_13` and `T_PLR_39` all attack the same risk (loopTask SD I/O starving the audio
pump) at increasing durations; a pass on the short one is not a pass on the long one.

## 13. Exit criteria

1. A ≥100-track M3U loads, scrolls end to end without an audible underrun.
2. Reorder / delete / add / save / restore round-trip correctly — verified host-side from the card.
3. All four shuffle × repeat end-of-playlist cells (§8) exercised; a full shuffle cycle over a
   ≥20-track playlist visits every track exactly once; Prev under shuffle replays history.
4. **Shuffle ON + reorder + SAVE writes display order, not shuffled order** — the destructive failure
   §2 exists to prevent.
5. WebRadio and Spotify show no behavioural change from the capability-mask refactor: WebRadio still
   renders and hit-tests no shuffle/repeat/seek zone; Spotify's 2→1→0→2 repeat cycle and optimistic
   hold are unchanged.
6. Three-way mode cycle via the taskbar icon persists across reboot; eject performs the correct
   per-mode action in all three modes.
7. Taskbar contains exactly `TASKBAR_APP_COUNT` slots with no eject-only mode leaked (TASK-242
   regression check).
8. Suspend invariant (§10) asserted clean after 20 mode switches in and out of Player.
9. ≥30 min local-playback soak **with concurrent browsing and scrolling** — no underrun, no heap
   decline, no WDT.
10. `NEW-APP-CHECKLIST.md` walked for `AppId::LocalPlayer` — every item, recorded.
