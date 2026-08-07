# Design — M-WINAMP-PLAYER (umbrella): local media playback for the Winamp player slot

> Owner: Architect
> Status: draft
> Date: 2026-08-07 (restructured from a single doc into umbrella + 4 workstreams, same date)
> Feeds: ADR-059 (proposed)
> Tracked-as: TASK-408 … TASK-422 (proposed)
> Registers: see §7

---

## 1. Ask

Make Winamp behave like Winamp: play MP3s off the SD card, browse the filesystem, read and write
`.m3u` playlists, make PLEDIT an actual editor (reorder / add / delete / save / restore), and drive
the skin's existing shuffle and repeat buttons.

## 2. Document map

This started as one document and was too big to schedule, review or partially land. It is now an
umbrella over four workstreams. **Three of the four have standalone value and do not depend on the
SD card existing** — they can be scheduled and judged on their own merits.

| # | Document | Tasks | Depends on | Standalone value |
|---|---|---|---|---|
| 1 | [M-SDFS — SD card exploration](M-SDFS-sd-card-exploration.md) | 408 | — | **yes** — answers a hardware question the project has never answered |
| 2 | [M-AUDIO-ENGINE — engine extraction](M-AUDIO-ENGINE-extraction.md) | 409, 410 | 410 needs #1 | **yes** for 409 — behaviour-neutral refactor of a 2 365-line app header |
| 3 | [M-PLEDIT-ABSTRACTION — playlist source](M-PLEDIT-ABSTRACTION-playlist-source.md) | 411, 412 | — | **high** — collapses a duplication that exists and has already diverged today |
| 4 | [M-WINAMP-PLAYER-local — the Player mode](M-WINAMP-PLAYER-local-playback.md) | 413–422 | #1, #2, #3 | no — this is the feature |

```
   #1 SD probe ──────┐
                     ├──▶ #4 Player mode (browser, m3u, playorder, edit)
   #2 audio engine ──┤
   #3 PLEDIT ────────┘
   (#2, #3 land without #1; #1 gates only #4 and TASK-410)
```

Cross-cutting analysis that applies to all four — reuse, memory, flash, build variants, registry —
lives here and is not repeated in the children.

## 3. Code reuse audit

The PLEDIT duplication was the first thing found; it is not the only one. This section is the
deliberate sweep.

### 3.1 Reused wholesale — no new code

| Component | Where | Reuse |
|---|---|---|
| **Helix MP3 decoder** | `lib/ESP32-audioI2S/src/mp3_decoder/` | **unchanged.** Local files decode through the identical path. **There is no second decoder and no new codec work.** |
| **`mb_arena`** | `lib/ESP32-audioI2S/src/mb_arena.{h,cpp}` | **unchanged, and sizing is unchanged.** It is a generic fixed-slot free-list allocator, not MP3-specific; a file source allocates the same nine Helix structs, so the 23 216 B HWM in `mem_manifest.yaml` still holds. |
| InBuff (6 400 B) | `Audio.cpp`, `wrApplyInBufTrial()` | unchanged — the library fills it from a `File` instead of a socket |
| Pump task, mutex, request/result posting | `webRadioApp.h` → `audio/audioEngine.h` | moved, not rewritten (workstream 2) |
| `audio_process_extern` vis tap | `webRadioApp.h:223` | unchanged — the spectrum and wave visualisers (TASK-387/388) work for local files **for free** |
| `touch/hitbox.h` | `Rect`, `hitTest`, `hitTestRow`, `hitTestCol` | already the shared hit-testing primitive |
| `touch/scrollTuning.h` | TASK-277 tuning constants | already shared by both PLEDIT copies |
| `settings/settingsWidgets.h` | `SButton` + `sButtonBar()` | the PLEDIT edit strip's buttons |
| `settings/settingsWidgets.h` | **`SPickerList`** | the file browser. Already has scrollbar, drag, offset clamping, highlight, open-scrolled-to-selection and a documented CP-1 full-phase takeover contract. Generalising its item type beats writing a fourth list widget. |
| `settings/settingsSection.h` | `drawRow()`, `drawRows()`, `S_MAX_ROWS` | browser row rendering |
| `appRegistry.h` | rows are already comment-out-able by design | build variants (§6) |

Not reused, deliberately: `aac_decoder` and `flac_decoder` are vendored but stay disabled — the arena
is sized for MP3's struct set, and enabling another codec changes the HWM and invalidates the
manifest.

### 3.2 Duplication found

| Finding | Status | Disposition |
|---|---|---|
| **PLEDIT renderer × 2** — `winampDisplay.h` (Spotify queue) and `webRadioApp.h` (stations) share only `scrollTuning.h`; everything else is restated | already identified | workstream 3 |
| **Scroll/velocity machinery × 3 families** — `winampDisplay.h`'s `dragState`, `webRadioApp.h`'s `_scrollAccum`/`_scrollVelocity`, `SPickerList::_sbDragging`. Only tuning constants are shared. The file browser would be a **fourth** | new | mitigated by reusing `SPickerList` (workstream 4 §4) rather than adding a fourth. Full unification of all three is **out of scope** — flag to PM as a candidate, not a prerequisite |
| **Ellipsis truncation — exactly one implementation**, inline in `winampDisplay.h`'s Spotify row formatter | new | three new callers need it (browser rows, local PLEDIT rows, ID3 titles). Extract `util/textFit()` during workstream 3, before the copies exist |
| **UTF-8 → renderable ASCII — nothing anywhere.** The Spotify path has the latent bug today; M3U/ID3 makes it acute | new | one shared helper serves both. Blocks row rendering — see workstream 4 OQ1 |
| **Hand-rolled row bounds maths** in both PLEDIT copies, predating `hitbox.h` | new | adopt `hitbox.h` during extraction rather than porting the arithmetic twice |
| **`handleVolumeGesturePublic()`** — a narrow public entry into one gesture, existing *only* because `handleWinampInput()` is Spotify-hardcoded | new | the capability mask (workstream 4 §7) removes the reason it exists. Retire it in its own commit — it shares `D_VOLUME_DRAG` state (TASK-352) and WebRadio's volume path already cost TASK-406 a bug |
| 13 `fetch*()` functions in `dataTaskStorage.cpp` with similar fetch/parse shape | pre-existing | **out of scope** — local playback makes no network calls. Noted so the sweep is honest, not to expand the milestone |

## 4. Memory budget

### 4.1 Current footprint — measured 2026-08-07, not remembered

| | prod `cyd2usb_winamp` | debug `cyd2usb_winamp_debug` |
|---|---|---|
| `.dram0.data` | 32 848 | 32 912 |
| `.dram0.bss` | 78 568 | 91 360 |
| `dram0_0_seg` capacity | 124 580 | 124 580 |
| **static headroom** | **13 160 B** | **304 B** |
| `.iram0.text` | 86 043 (cap 131 072) | 86 083 |
| `firmware.bin` | 1 799 840 | 1 797 920 |

**The debug build has 304 bytes of headroom.** That is the binding constraint on this entire
milestone, and it is not a remembered number — re-derive it before each phase
(`run/build-debug`, then the `dram0_0_seg` / `.dram0.bss` / `.dram0.data` map extents).

### 4.2 Measured cost of enabling SD/FS

Method: rebuild `cyd2usb_winamp_debug` with `-UAUDIO_NO_SD_FS`, plus a probe translation unit that
actually references `SD.begin()`, `openNextFile()`, `read()` and `connecttoFS()` — without it the
linker garbage-collects most of the cost and the number flatters.

| | `.dram0.data` | `.dram0.bss` | headroom | flash |
|---|---|---|---|---|
| debug baseline | 32 912 | 91 360 | 304 B | 1 797 920 |
| `-UAUDIO_NO_SD_FS`, unreferenced | +0 | +40 | 264 B | +3 904 |
| **`-UAUDIO_NO_SD_FS`, wired** | **+16** | **+72** | **216 B** | **+3 984** |

SD/FS itself is cheap: **88 B static DRAM, ~4 KB flash.** It lands on 304 B of headroom.

### 4.3 What that forces

**Every byte of Player state must be heap, not static.** A `LocalPlayerApp` global instance puts its
members in `.bss`; at 216 B remaining that is not available. The accepted pattern in this project is
lazy `malloc` once, never freed (the `WinampDisplay` precedent) — here it is better than that,
because Player state has a natural lifetime: acquired in `resume()`, freed in `suspend()`.

Projected runtime (heap) additions, to be registered in `mem_manifest.yaml`:

| Buffer | Size | kind / placement | Notes |
|---|---|---|---|
| `plmodel_entries` | 2 048 B @256 | scratch / runtime | immutable load-order index |
| `plmodel_view` | 512 B @256 | scratch / runtime | display permutation |
| `plmodel_play` | 512 B @256 | scratch / runtime | playback permutation |
| `plmodel_rowcache` | 576 B | scratch / runtime | ≤8 visible rows |
| `plmodel_staging` | 1 536 B | scratch / runtime | 16 pending adds |
| `sdfs_fatfs` | **unmeasured** | scratch / runtime | FATFS work area at `SD.begin()`; M-SDFS pass bar is ≤8 KB |
| `browser_page` | ≤32 × ~80 B ≈ 2 560 B | scratch / runtime | one directory page |

≈ **7.7 KB of heap plus the FATFS area**, all Player-scoped and freed on suspend.

The compensating structural win: **local playback opens no TLS.** The ~40 KB mbedtls context that
forces `webradio_decoder` and `webradio_inbuf` to stay `placement: runtime` is simply absent in this
mode. Player is the *cheapest* of the three player modes at runtime, not the most expensive.

### 4.4 Reclaim — proactive, scheduled first (operator decision, 2026-08-07)

Taken ahead of the milestone rather than reactively when a phase fails to link. A phase that fails
to link mid-implementation costs a debugging session and blocks the phase; the reclaim below costs
one task and is independently correct.

**Where the debug overage actually is.** Debug `.dram0.bss` exceeds production by 12 792 B. A map
symbol dump attributes **11 956 B of that — 93 % — to two function statics in one debug-only
command**:

| Symbol | Size | Home |
|---|---|---|
| `cmdScreenDump::s_b64` | 6 836 B | `main.cpp:3967` |
| `cmdScreenDump::s_band` | 5 120 B | `main.cpp:3966` |

Both live inside the `#ifdef SERIAL_DEBUG` block, and neither appears in the production map
(verified: zero matches). They are the band buffers for `screendump`, an on-demand host-driven
screenshot tool that runs for ~18 s when a human asks for it — 12 KB of permanently-resident DRAM
serving an occasional dev command, in the exact build that has 304 B of headroom.

**TASK-423 — move them off `.bss`.** Allocate on entry to `cmdScreenDump()` and free on exit. The
command is manual, occasional and not latency-critical, so per-invocation `malloc`/`free` is
preferable to the lazy-malloc-once pattern used for `WinampDisplay` — it returns the 12 KB to the
heap instead of merely relocating it. Allocation failure prints the existing JSON error shape and
returns; a dev tool degrading on a fragmented heap is acceptable where a link failure is not.

Expected result: debug headroom **304 B → ≈12.2 KB**, with zero production impact (the code does not
compile into production) and zero behavioural change to the tool beyond a possible allocation-failure
path. This is measured before and after, not assumed.

Remaining levers, if ever needed after that:

1. The build variants of §6 — a development env with one mode compiled out.
2. `logsink::g_lines` (12 384 B) — the largest single `.bss` object, present in **both** builds.
   Load-bearing for the test harness; resize only with VE agreement.
3. TASK-400/401 precedent: shrink an oversized static whose extra capacity is dead weight
   (`WifiSection::_nets[]` went 16→8, behaviour-preserving). Candidates from the same dump:
   `renderTaskbarSlot`'s 2 592 B static, `g_sinLUT` 2 048 B (a boot-computed table that could be a
   `const` in flash).
4. `CORE_DEBUG_LEVEL` is already 0 on debug — that lever is spent (TASK-370).

## 5. Flash budget

`app0` is 0x280000 = **2 621 440 B**. Current prod `firmware.bin` is 1 799 840 B — **68.7 % used,
821 600 B free.**

| Item | Estimate | Basis |
|---|---|---|
| SD/FS enable | **+3 984 B** | measured (§4.2) |
| `audio/audioEngine.h` extraction | ~0 | pure move |
| `pleditView.h` extraction | **negative** — one renderer replaces two | measured after TASK-412 |
| File browser | ~4–6 KB | `SPickerList` generalisation + browser logic |
| M3U parse/write | ~3 KB | |
| Play-order engine | ~1 KB | Fisher-Yates + cursor logic |
| Edit mode UI | ~3 KB | reuses `sButtonBar()` |
| PLEDIT button sprites, **if** a re-bake is needed | ~2 KB rodata | conditional on workstream 4 OQ2 |

**Projected total ≈ +15–20 KB, against 821 KB free.** Flash is not a constraint for this milestone.
It was in the past (TASK-035 hit the app0 wall and is why `partitions_no_ota.csv` exists), so the
number is stated rather than assumed.

## 6. Build variants — enabling and disabling the three player modes

Requested, and it doubles as the §4.4 reclaim lever.

**Presence flags, never `=0`** (LL-006, already enforced in `platformio.ini`'s own comments):
`-DPLAYER_SPOTIFY`, `-DPLAYER_WEBRADIO`, `-DPLAYER_LOCAL`. Absence compiles the mode out entirely —
its `AppId` row is commented out of `appRegistry.h` (which is already designed for this: *"Comment
out a row to disable that app at build time"*), its app object is not instantiated, its header is not
included.

Consequences to handle explicitly, none of which are automatic:

1. **Mode cycling must skip absent modes.** `resolvePlayerSlot()` and the taskbar cycle iterate the
   compiled-in set, not a hardcoded 0→1→2. A single-mode build must not cycle at all.
2. **Persisted `playerMode` may name an absent mode** after a variant reflash. Load must fall back to
   the first compiled-in mode rather than resolving to a null app — this is a boot-crash class bug.
3. **`TASKBAR_APP_COUNT` is computed from the compiled-in tail**, not a literal. Workstream 4 §6
   already rewrites that assertion; it must be expressed in terms of the enum, not a constant.
4. **Settings → Applications → Player** shows only compiled-in modes.
5. The existing `-DDISABLE_SPOTIFY` (a negative flag, used by `cyd2usb_webradio` and
   `cyd2usb_winamp_debug_noSpotify`) stays as-is. Do not migrate it in this milestone — it is load-
   bearing for the test harness's `get variant` fast path.

**Do not build a 2³ env matrix.** `check_build.sh` runs two full builds today (gates 1 and 2 of 6/7);
eight would make the gate unusable. Add exactly **one** development env —
`cyd2usb_player` (Player only, Spotify and WebRadio compiled out) — used for headroom during
development and for isolating Player bugs from the other two modes, mirroring how `cyd2usb_webradio`
already exists for exactly that purpose. Production keeps all three modes. Gate count goes 6 → 7,
not 6 → 13.

## 7. Registry reservations

Reserved at design time per `architect.md` responsibility #10. Developer completes them at
implementation; VE attaches test ids. Both files validated as parseable YAML on write.

### `feature_inventory.yaml` — 7 features, all `status: reserved`

| id | Name | Workstream |
|---|---|---|
| `sdfs-001` | SD card filesystem (VSPI mount + probe) | 1 |
| `localplay-001` | Local MP3 playback + system-owned audio engine | 2 |
| `plmodel-001` | Shared playlist model + single PLEDIT renderer | 3 |
| `m3u-001` | Extended-M3U parse and write | 4 |
| `browse-001` | On-device SD file browser | 4 |
| `pledit-edit-001` | PLEDIT edit mode — reorder, add, delete, save, restore | 4 |
| `playorder-001` | Shuffle / repeat engine + capability-driven transport zones | 4 |

### `cross_feature_matrix.yaml` — X050–X064

| id | Edge | Risk | Ws |
|---|---|---|---|
| X050 | `localplay-001` ↔ `webradio-001` — one `Audio` object, two clients | high | 2 |
| X051 | `localplay-001` ↔ `memplan-001` — `AUDIO_NO_SD_FS` drop vs `.dram0.bss` | high | 2 |
| X052 | `sdfs-001` ↔ `localplay-001` — loopTask vs pump task on a serialised FATFS | high | 4 |
| X053 | `sdfs-001` ↔ `memplan-001` — VSPI pin budget, GPIO5 strapping, lazy mount | medium | 1 |
| X054 | `plmodel-001` ↔ `playlist-002` — renderer absorbs `drawPlaylist()` | high | 3 |
| X055 | `plmodel-001` ↔ `webradio-001` — WebRadio's diverged copy deleted | high | 3 |
| X056 | `player-state-001` ↔ `taskbar-icons-001` — active-slot tap cycles the mode | medium | 4 |
| X057 | `player-state-001` ↔ `app-registry-001` — eject-only tail assertion | high | 4 |
| X058 | `browse-001` ↔ `touch-004` — busy gate vs navigation taps | medium | 4 |
| X059 | `pledit-edit-001` ↔ `m3u-001` — staged entries in the save path | medium | 4 |
| X060 | `playorder-001` ↔ `chrome-001` — SHUFREP sprites reused verbatim | low | 4 |
| X061 | `playorder-001` ↔ `webradio-001` — capability mask must be behaviour-neutral | high | 4 |
| X062 | `playorder-001` ↔ `plmodel-001` — shuffle must not reach `viewOrder`/SAVE | high | 4 |
| X063 | `playorder-001` ↔ `localplay-001` — `audio_eof_mp3` fires under the mutex | high | 4 |
| X064 | `player-state-001` ↔ `app-registry-001` — compile-time mode variants (§6) | high | 4 |

Gap noted: this milestone reserves 7 features and 14 edges before writing a line of code, which is
the intended discipline. The backstop it replaces — close-out registration — has demonstrably failed
before (M-PR-LOCATIONS shipped TASK-315..325 with zero matrix entries).

## 8. Test & validation

Every task in this milestone has a named validation table in its workstream document. The Architect
specifies *what must be proven and by what method*; **VE owns the suite, may renumber, and should
challenge any of these on testability before they are finalised** (inter-agent protocol). Ids are
reserved, not written — `test_coverage: []` stays empty in the registry until VE lands them.

| Family | Workstream | Ids | Table |
|---|---|---|---|
| `T_RCL_` | 0 — reclaim | 01–04 | below |
| `T_SD_` | 1 — SD exploration | 01–09 | [M-SDFS §7](M-SDFS-sd-card-exploration.md) |
| `T_AE_` | 2 — audio engine | 01–10 | [M-AUDIO-ENGINE §8](M-AUDIO-ENGINE-extraction.md) |
| `T_PLE_` | 3 — PLEDIT abstraction | 01–13 | [M-PLEDIT-ABSTRACTION §6](M-PLEDIT-ABSTRACTION-playlist-source.md) |
| `T_PLR_` | 4 — Player mode | 01–40 | [local-playback §12](M-WINAMP-PLAYER-local-playback.md) |

All five prefixes were confirmed unused before reservation. Naming follows the established
`T_XXX_NN` convention (`T_WR_`, `T_PR_`, `T_PRL_`, `T_CLK_`, …); the numeric `TNNN` space is at T282
and is not extended here.

### TASK-423 — proactive DRAM reclaim (§4.4)

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_RCL_01` | Debug headroom recovered | **host** — `run/build-debug`, `dram0_0_seg` vs `.dram0.data`+`.dram0.bss` extents | **≥10 KB** (from 304 B); number recorded, not asserted |
| `T_RCL_02` | Production untouched | host — prod `.map` diff | byte-identical `.dram0.bss`; `s_band`/`s_b64` still absent (they never compiled in) |
| `T_RCL_03` | `screendump` still works | DUT — full-canvas dump, then a windowed dump | byte-identical PNG to a pre-change capture of the same static screen |
| `T_RCL_04` | Allocation failure degrades cleanly | DUT — invoke under deliberate heap pressure | existing JSON error shape, no crash, no partial-band garbage on the wire |

`T_RCL_03` matters more than it looks: `screendump` is the instrument three `T_PLE_` pixel-identity
tests depend on. Breaking it would silently invalidate the PLEDIT gate rather than fail it.

### Cross-cutting validation properties

Four themes run across the tables; they are the reason the milestone is testable at all:

1. **Behaviour-neutral refactors are proven by re-running the existing suite unchanged**
   (`T_AE_01`, `T_PLE_08`, `T_PLR_17`, `T_PLR_18`) — not by new tests. Baseline **before** the
   refactor lands, and compare failure *sets*, not counts (LL-104).
2. **Anything the device could report success on while being wrong is verified off-device**
   (`T_PLR_30`, `T_PLR_31`, `T_PLR_36`, `T_RCL_02`) — from the card, from a variant reflash, or from
   the map file.
3. **Feel is not pixels.** `T_PLE_05`/`T_PLE_09` are eyeball gates on real hardware (BP-048); no
   serial assertion substitutes for them.
4. **Duration is a variable, not a formality.** `T_PLR_09` → `T_PLR_13` → `T_PLR_39` attack the same
   loopTask-starves-the-audio-pump risk at rising durations, and `T_AE_03` requires a full-length
   soak specifically because a short one has given false confidence on that code before.

## 9. Phasing

Numbers are proposed; PM may renumber when filing. Execution order is the table order — note
TASK-423 runs **first** despite its number (it was added after the range was drafted).

Every row's gate is a named test id (§8 and the workstream tables) — no task closes on judgement.

| Task | Ws | Scope | Gate (test ids) |
|---|---|---|---|
| **423** | **0** | **Proactive DRAM reclaim: `cmdScreenDump` band buffers off `.bss` (§4.4)** | **`T_RCL_01`–`04`** |
| 408 | 1 | SD probe + benchmark | `T_SD_01`–`09` — **hard gate for #4 and 410** |
| 409 | 2 | `audio/audioEngine.h` extraction (pure move) | `T_AE_01`–`06` (incl. **full-length** wr-soak) |
| 410 | 2 | Drop `AUDIO_NO_SD_FS`; `connect(FILE)`; play one hardcoded path | `T_AE_07`–`10` |
| 411 | 3 | `pleditView.h` extraction, Spotify caller only | `T_PLE_01`–`06` |
| 412 | 3 | WebRadio → `StationListSource` | `T_PLE_07`–`13` (incl. LCD eyeball) |
| 413 | 4 | `AppId::LocalPlayer`, three-way mode, taskbar cycle, assertion rewrite, debug-surface widening (§6.1) | `T_PLR_01`–`05` |
| 414 | 4 | Eject remap (all three modes) | `T_PLR_06`–`07` |
| 415 | 4 | `m3u.h` + index model + read-only `LocalPlaylistSource` | `T_PLR_08`–`12` |
| 416 | 4 | `fileBrowser.h` (via `SPickerList`) + eject entry + play-from-browser | `T_PLR_13`–`16` |
| 417 | 4 | Transport capability mask; un-gate shuffle/repeat/seek | `T_PLR_17`–`19` |
| 418 | 4 | Play-order engine: shuffle bag, repeat, `audio_eof_mp3` auto-advance | `T_PLR_20`–`26` |
| 419 | 4 | Real posbar seek for local files | `T_PLR_27`–`28` |
| 420 | 4 | Edit mode: button strip, reorder, delete | `T_PLR_29`, `34` |
| 421 | 4 | Add-from-browser (staging), save, restore | `T_PLR_30`–`33` |
| 422 | 4 | Build variants (§6) + soak + VE suite + registry completion | `T_PLR_35`–`40` |

417–419 sit **before** edit mode deliberately: they exercise the play-order and capability seams while
the playlist is still read-only, so a failure there is diagnosed without edit-mode mutation as a
confounder.

## 10. Open questions owned at this level

- **OQ-A — RESOLVED 2026-08-07 (operator: proactive).** The reclaim is scheduled ahead of the
  milestone as TASK-423 and runs first. Target and method in §4.4.
- **OQ-B** — do workstreams 2 and 3 get scheduled independently of the SD outcome? Both have
  standalone value and neither needs the card. Recommended: yes — they de-risk #4 and improve the
  codebase whatever #1 returns.
- **OQ-C — TASK-407 disposition (revised 2026-08-07 after reading the task).** TASK-407 is **open,
  P4, filed but not investigated**: `g_settings.playerMode` was seen reverting to WebRadio at boot on
  three occasions, of which two are traced to human process error (a manual DUT session and a
  forgotten `set playerMode` cleanup) and **one is genuinely unexplained** — a full-suite run booted
  `playerMode=webradio` with no `set`/`switchApp` anywhere in the preceding session's capture. It
  self-heals via the suite's own end-of-run reset every time it has been observed; the leading
  unverified suspect is an esptool RTS hard reset racing an uncommitted SPIFFS write.

  **Revised recommendation: do not block this milestone on it.** Widening the domain from two values
  to three does not obviously make a spontaneous flip worse. What *does* change the stakes is §6:
  once modes are compile-time optional, a spontaneously-flipped `playerMode` naming a compiled-out
  mode resolves to a null app and crashes at boot. That makes D10's fallback load-bearing rather than
  defensive — so it is tested, not merely written (X064).

  **Superseded 2026-08-07 — the diagnostic landed independently.** `run_serialdbg_tests.py` now
  prints `[TASK-407] entry/exit playerMode:` around every run (covers `run/test`,
  `run/test-targeted`, `run/test-smoke` — all three share that runner; `run/test-sync` has a separate
  runner and was deliberately left out). One reproduction attempt of occurrence #2's exact sequence
  came back clean, 0/1, correctly noted as non-conclusive per
  `feedback_isolated_rerun_vs_suite_state`. TASK-407 is now **OPEN — instrumented, passive**: it
  catches the flip in-session if it recurs, with no active follow-up. Nothing here blocks this
  milestone.

  **One consequence carried forward:** that instrumentation reads `get playerMode`, whose getter is
  hardcoded two-valued (`main.cpp:3336`) and will report Player mode as `WebRadio(1)`. See
  [local-playback §6.1](M-WINAMP-PLAYER-local-playback.md) — TASK-413 must widen the getter and
  setter in the same commit as the enum, or the TASK-407 trap starts producing confident wrong data.
