# M-WINAMP-PLAYER — active tasks

> Owner: Project Manager · Split out of [tasks.md](tasks.md) on 2026-08-15.
>
> **Why this file exists.** The milestone began with reviewed Architect design docs (ADR-059) and
> ended up with 30+ task entries, several reframed two or three times, and a P1 whose cause was
> found in the end by accounting rather than by any of the theories the tasks carried. Splitting it
> out is bookkeeping, not a fix — see the PM note at the foot of this file for the honest read on
> what went wrong and what it implies for the remaining work.
>
> Closed entries live in [tasks-archive.md](tasks-archive.md). The rest of the board is in
> [tasks.md](tasks.md).

---

### TASK-407 — `g_settings.playerMode` reverts to WebRadio between DUT sessions with no manual trigger found

**Filed 2026-08-06, split out of TASK-406's investigation** — that task closed two confirmed,
narrow bugs (T079's hardcoded `skipped`, T082's missing volume-drag log line), but along the way
turned up a separate, unexplained persistence anomaly that deserves its own tracking rather than
living as a paragraph inside a closed task.

**What's confirmed:** across today's session, `g_settings.playerMode` was observed reverting to
`WebRadio` (`1`) at DUT boot on at least two occasions where the *known* mutation paths don't
explain it:

1. **First occurrence** — traceable to a real cause: an earlier manual DUT session that day
   (`set wrUrl ...`, verifying TASK-393's terminal-retry) switched `currentAppId` to WebRadio, and
   `playerMode` was never explicitly reset back to Spotify before the session's final
   `./run/flash` (app-partition-only reflash — doesn't touch the SPIFFS/data partition, so
   whatever was last durably saved there survives). Not mysterious once traced.

2. **Second occurrence — genuinely unexplained.** A `run/test-targeted T079,T082` session (debug
   reflash → run two tests, neither touches `playerMode` → prod reflash) left the device reading
   `playerMode=Spotify` throughout (confirmed via raw serial log, zero `set playerMode` or
   `switchApp` calls to WebRadio anywhere in that session's capture) and via a manual
   `./run/flash` immediately after. The **next** full-suite `run/test` pass — a fresh debug
   reflash with no manual DUT interaction in between — booted with `playerMode=WebRadio`
   (`[boot] spotify=idle (playerMode=webradio)`), and that same full-suite run's own teardown then
   correctly wrote it back to Spotify (confirmed durably: pulling `settings.json` after that run's
   prod restore read `player.mode=0`, matching the suite's last action). No `set`/`switchApp`
   command, no code path, no test invocation between the two sessions explains the flip from
   Spotify to WebRadio.

**A third, separate, KNOWN-cause instance happened later the same session** (not mysterious,
noted here for completeness): my own manual TASK-406 T082 fix-verification explicitly ran
`set playerMode webradio` to force the test condition, then reflashed prod directly afterward
without resetting it back — leaving the live device on `playerMode=1` until caught and corrected
via a `run/spiffs pull` → edit → `run/spiffs push settings.json` round-trip (non-destructive,
confirmed `player.mode=0` after). This is just me forgetting a cleanup step, the same mistake
TASK-406 itself was originally triggered by — worth a process note (see below) but not part of
this task's actual mystery.

**Ruled out / considered:**
- `persistPlayerMode()` (`main.cpp:1935`) does an immediate `SettingsStorage::save()`, not a
  coalesced/RAM-only write — no reason a completed `set playerMode 0` response should be lying
  about having persisted.
- The debug `set playerMode` handler (`main.cpp:3803-3819`) parses both numeric and
  `spotify`/`webradio` string forms correctly; not a parsing bug.
- Not explained by any test in the T077-T082 group or the T079/T082 targeted subset — neither
  touches `playerMode`.
- Repeated hard resets via `esptool`'s RTS-pin reset (many back-to-back reflashes happened this
  session) are a plausible but unconfirmed suspect — if a SPIFFS write from an *unrelated* earlier
  point in time wasn't fully committed before a later hard reset, a stale on-disk value could
  resurface. Pure speculation; not verified against SPIFFS/LittleFS's actual write-durability
  guarantees on this hardware.

**Instrumentation landed (2026-08-07):** `run_serialdbg_tests.py` now prints a `[TASK-407] entry
playerMode:` / `[TASK-407] exit playerMode:` line (via `get playerMode`) right after connect and
right before `dut.close()` — covers `run/test`, `run/test-targeted`, and `run/test-smoke` (all
three share this runner). Mirrors the `_diag_snapshot()` precedent from TASK-385/386. Not added to
`run/test-sync` (separate `run_sync_tests.py` runner; occurrence #2 never implicated it — revisit
if a future flip does).

**Reproduction attempt (2026-08-07):** ran the exact sequence from the "not yet tried" note —
`run/test-targeted T079,T082` (clean, non-touching) → immediately `run/test` (full suite, no
manual action between) → immediately another `run/test-targeted T079,T082`. Three boundary
snapshots, all explained:
1. Targeted #1: entry `WebRadio(1)`, exit `WebRadio(1)` — unchanged, as expected (neither test
   touches it).
2. Full suite: entry `WebRadio(1)` (correctly carried over) → exit `Spotify(0)` — this flip is the
   suite's *own* WebRadio tests + end-of-run teardown resetting it, not a mystery.
3. Targeted #2: entry `Spotify(0)` (correctly carried over from #2's teardown), exit `Spotify(0)`
   unchanged. **No unexplained flip.** 0/1 repro on this attempt.

Consistent with `feedback_isolated_rerun_vs_suite_state` — a single clean pass doesn't rule out a
suite-order-dependent trigger. The instrumentation now stays live permanently, so the next time
occurrence #2's pattern shows up in the wild (in any `run/test`/`run/test-targeted`/`run/test-smoke`
session) it'll be caught in that session's own log instead of requiring after-the-fact reasoning
across separate sessions.

**Process note (not this task, but adjacent):** occurrence #3 above suggests manual DUT `set`
commands used for one-off verification should default to resetting any test-only overrides
(`playerMode`, `cooldown`, injected debug state) before handing the DUT back to an automated
suite — the same discipline `run_serialdbg_tests.py`'s own tests already apply to themselves
(`set cooldown 0` before/after nearly every tap). Consider this a personal-workflow reminder more
than a firmware gap.

**Owner:** unassigned · **Deps:** none · **Priority:** P4 (cosmetic-adjacent — self-heals via the
suite's own end-of-run reset every time it's been observed; the actual risk is only ever a wasted
T077-T082 run if caught mid-suite, which TASK-406's fixes now make harmless either way) ·
**Status:** **OPEN — instrumented, one repro attempt clean (0/1).** Passive: instrumentation now
catches the flip automatically in any future `run/test*` session's own log; no active follow-up
needed until it resurfaces.

---

## Open — M-WINAMP-PLAYER (filed 2026-08-07)

Human request: make Winamp behave like Winamp — play MP3s off the SD card, browse the filesystem,
read/write `.m3u` playlists, make PLEDIT a real editor, and drive the skin's existing shuffle/repeat
buttons.

Architect design set, committed `a8d0369`: umbrella
[M-WINAMP-PLAYER.md](../architecture/designs/M-WINAMP-PLAYER.md) (reuse audit, memory/flash budgets,
build variants, registry, test-family map) over four workstreams —
[M-SDFS](../architecture/designs/M-SDFS-sd-card-exploration.md),
[M-AUDIO-ENGINE](../architecture/designs/M-AUDIO-ENGINE-extraction.md),
[M-PLEDIT-ABSTRACTION](../architecture/designs/M-PLEDIT-ABSTRACTION-playlist-source.md),
[local-playback](../architecture/designs/M-WINAMP-PLAYER-local-playback.md).
Decision: [ADR-059](../architecture/decisions/ADR-059.md).

> **✅ GATE CLEARED — ADR-059 accepted 2026-08-07** (human sign-off, all thirteen decisions).
> Implementation is authorised. All five design docs are `accepted`. Three constraints ride with
> acceptance and are **not** renegotiable at implementation time without a new ADR:
>
> 1. **TASK-423 runs first** — the reclaim, before anything spends the 304 B of debug headroom.
> 2. **D13's ≥3-run baselines must be captured BEFORE TASK-409, 412 and 417 land.** That is DUT time
>    *ahead of* the refactors, not concurrent with them. Scheduling this late is the one way to
>    invalidate the milestone's main safety property.
> 3. **D2's move stays a move** — no behavioural hunks in the extraction commit.
>
> Acceptance does **not** pre-approve D1's outcome: TASK-408 remains a genuine gate, and a failing
> probe closes the milestone with a hardware note rather than triggering a redesign.

**Execution order is NOT numeric.** TASK-423 runs **first** (it was added after the range was
drafted; renumbering would invalidate the just-committed design docs and their cross-references).
Order: **423 → 408 → 409 → 410 → 411 → 412 → 413 … 422**.

**Scheduling note.** Workstreams 2 and 3 (TASK-409, 411, 412) need no SD card and have standalone
value — 409 turns a 2 365-line app header into an app plus a reusable engine, and 411/412 collapse a
PLEDIT duplication that exists and has already diverged today. They can proceed regardless of what
TASK-408 returns. Only TASK-410 and workstream 4 are gated on the probe passing.

**Registry.** Reserved at design time (Architect responsibility #10): features `sdfs-001`,
`localplay-001`, `plmodel-001`, `m3u-001`, `browse-001`, `pledit-edit-001`, `playorder-001`;
matrix X050–X064. Developer completes them at implementation.

**Reviews complete (2026-08-07).** [VE](../architecture/designs/M-WINAMP-PLAYER-VE-review.md) —
4 blockers, 9 majors, 5 minors. [Developer](../architecture/designs/M-WINAMP-PLAYER-DEV-review.md) —
2 blockers, 5 majors, 4 minors. **All folded into the design set and ADR-059** (Architect,
2026-08-07). Material outcomes for scheduling:

- **ADR-059 D7 was factually wrong** and is corrected — only one of three `static_assert`s breaks,
  `TASKBAR_APP_COUNT = (int)AppId::WebRadio` still holds, and the proposed `COUNT - 2` replacement was
  *less* robust than the existing code. Affects TASK-413 only.
- **D6 amended (DEV-1)** — the taskbar cycle cannot live in `resolvePlayerSlot()`; `switchApp()`
  early-returns on same-app and the two dispatch sites guard differently. Needs one shared helper
  called from both. Affects TASK-413 only.
- **New ADR-059 D12** — observability is product surface. TASK-411 gains `get pleditRepaints`;
  TASK-418 gains `get plOrder` / `get plCursor` / `set plCursor` / `advance next|prev`; TASK-410
  gains the loopTask-handle capture + `configASSERT`. Without these, eight ids were unrunnable
  (two needed ~3 h of playback; six asserted on state the firmware does not expose).
- **New ADR-059 D13** — every "identical pass set" gate now requires a **≥3-run baseline** with the
  flaky set pre-declared. A single-run bar would have failed on `T_WR_TLS_01`/`T169`/`T_PR_05`
  rather than on regression. Affects TASK-409, 412, 417 scheduling (baseline runs must precede the
  refactor landing).
- **TASK-422 also renumbers `check_build.sh`'s gate labels** (DEV-7) — the script prints `[1/6]`…
  `[6/6]` plus a `[7/7]`, and `tasks.md` entries cite both 6/6 and 7/7.

**VE ids: 76 → 78.** Added `T_SD_10`, `T_PLE_14` (closes a real X055 gap — WebRadio's `_pleditDirty`
bool becoming a seqno has two uncovered failure modes), `T_PLR_41`. Withdrawn: `T_AE_05` (a review
gate, not a repeatable test — survives as a TASK-409 checklist item). Reclassified: `T_PLR_25`'s
task-identity half becomes a runtime assert. Per-task tables live in the workstream docs;
`test_coverage: []` stays empty until VE lands the suite.

### TASK-424 — SD write path panics in FatFs (card-independent)

Split out of TASK-408, where it was found and characterised but not filed. Sustained writes to a
single open file panic the firmware: `f_write()` → `validate()` faults `LoadProhibited` because
`obj->fs` reads NULL immediately after `ff_req_grant()` returns. Reproduced on **both** cards tested
and at **both** 4 and 20 MHz, so it is not a card or clock artefact.

Files the path produces are left damaged — one truncated-and-reopened file reported a
**1 073 678 476 B** size, and *reading* a fixture this path had written was itself enough to panic.
On the 2 GB SDSC card, short open/write/close bursts were a reliable workaround (200 files created,
32 KB appends at ~265 KB/s); on the 30 GB SDHC card even short writes now fail.

Not on the M-SDFS phase-0 critical path — phase 0 is read-only and reads of host-written files are
clean and fast. Filed because it is a live firmware panic with a known trigger, and because
`pledit-edit-001` / `m3u-001` (TASK-420/421, playlist save) assume a working write path. Those tasks
must not start until this is understood.

**Owner:** Developer · **Deps:** none (TASK-408 supplies the repro) · **Gate:** the `sdwrite` command
completes 2 048 chunks single-open, twice, on both cards, with no panic and a correct `endSizeB` ·
**Priority:** P2 (blocks TASK-420/421 only) · **Status:** OPEN — **re-characterised 2026-08-15 with a
measured mechanism; the model in the paragraphs above is wrong in two ways.** No fix yet.

#### TASK-424 re-characterisation (2026-08-15, `cyd2usb_winamp_debug`, 32 GB SDHC)

**Reproduced deterministically**: `sdwrite 2048` panicked on both consecutive attempts.

**Fault resolved with `addr2line` against the real ELF** (the inline decoder is untrustworthy on this
project — TASK-432):

```
0x40168974: validate     ff.c:3465
0x40169bce: f_write      ff.c:3852
0x4016bb45: vfs_fat_write vfs_fat.c:379
0x4014544e: esp_vfs_write vfs.c:431
EXCVADDR: 0x00000001
```

`EXCVADDR = 0x1` with the fault inside `validate()` means the `FFOBJID*` **is** `0x1` — the FIL is
corrupt, not merely unmounted.

**Correction 1 — it is not "sustained writes".** Chunk count is not monotonic and not the variable:

| chunks | outcome |
|---|---|
| 64 | PANIC |
| 256 | OK, 131 072 B, 1 143 kB/s |
| 512 | OK, 262 144 B, 1 213 kB/s |
| 1024 | short write at chunk 22, then OK-with-loss |
| 2048 | PANIC |

**Correction 2 — the dominant failure is silent data loss, not the panic.** `f.write()` returns **0**
(not a partial count) at a varying chunk — 22 and 49 in two runs — and the loop's own `endSizeB` is
*smaller still* than the bytes it accepted: 49 chunks accepted (25 088 B) but 23 552 B on the card.
So writes the caller was told succeeded were never flushed. A playlist-save built on this path
(TASK-420/421) would silently truncate.

**The decisive negative: `sd_diskio` never logs an error.** `CORE_DEBUG_LEVEL=1` is on, so a media
failure would appear. Nothing does — **FatFs fails before touching the card**. That is exactly what
`validate()` returning `FR_INVALID_OBJECT` looks like, and it is the same function that faults when
the pointer is garbage instead of null. **One mechanism explains both symptoms: the FIL is
invalidated mid-write.** Heap integrity checks (`sdwrite N 32`) pass right up to the fault, so it is
not general heap corruption.

**Also confirmed**: the damaged-directory-entry symptom persists across sessions — a fresh open
reported `startSizeB=1073628004` (~1 GB), the same class as the 1 073 678 476 B in the original
filing.

**Next step for whoever fixes it** — and it is now a narrow question, not a hunt: instrument
`fp->obj.fs` and `fs->id` per chunk (a debug build already has `ff.h` and `ffconf.h` included for
exactly this, `main.cpp:89-92`) and find who invalidates them. `fs->id` changes on every `f_mount`,
so a concurrent remount is the leading candidate — `SD.begin()`/`SD.end()` live at `main.cpp:3195`,
`:5060`, `:5095`, `:5099`, and `main.cpp:92` already refers to a "deferred live-mount corruption"
investigation that was never completed.

**Fixture safety, checked after the runs**: `/playlists/short5.m3u` still loads 5 entries and
`/playlists` still lists 7 files, so the T_PLR fixtures survived. `sdwrite` only touches
`/probebench.bin`, but the FS damage this path produces makes that worth re-checking after any
future run.

> `sdprobe` builds its bench fixture in short bursts specifically to route around this. If this is
> fixed, revert that to a plain single-open write — the burst loop is a workaround, not a design.

### TASK-452 — retire the arena from the FILE path (successor to the withdrawn TASK-443)

**Scope, deliberately small.** `aeConnectFile()` stops calling `mb_arena_acquire()`; the decoder
allocates through `mb_arena_alloc()`'s libc fallback. WebRadio's URL path is unchanged. The gate is
the connect kind, not the build variant.

**What this is NOT.** It is not what makes Player mode work — TASK-447/448 did that, and
`cyd2usb_player` plays a 5-track playlist today **with the arena acquired** (`hwm=23216` inside its
24 576 B). It does not rescue the Spotify-enabled build either: measured 2026-08-15, skipping the
arena there produces zero tracks, failing 700 B later at `SubbandInfo_t` instead. Anyone reading
this as a fix for a playback problem has the wrong task.

**Why do it at all — two reasons that survived the withdrawal:**
1. **Contiguity.** The arena converts the decoder's nine allocations (largest 8 708 B) into one
   24 576 B contiguous demand. Measured: nine holes' worth of room exists at idle
   (`n8708=7 n4096=15 n1024=48`) and the nine real allocations succeed un-arena'd, leaving ~41 KB.
   The arena manufactures a requirement the FILE path does not have.
2. **It shrinks TASK-444's blast radius.** Two arms with different provenance sharing one `Audio`
   is what makes the free-after-release corruption reachable; removing the arena from one arm does
   not fix it, but it stops the FILE path contributing arena-provenance pointers.

**Three things must land with it — each was found by review of the withdrawn task and none is
optional:**
- `aeTeardownFile()`'s **unconditional** `mb_arena_release()` must go. An arm that never acquires
  must never release; the deferred-CONNECTING teardown path can otherwise yank a live WebRadio arena.
- `aeReleaseArenaIfIdle()` must gate on **ownership, not idleness**. Its guard is
  `!s_wr_audio && !wrPumpAlive()`, which post-change can only ever release someone else's arena.
- **libc accounting first** (`libcCount`/`libcBytes`/`libcMax` in `get arenaStats`), before the
  `mb_arena_alloc` `log_e` is quieted. `mb_arena_hwm()` reads 0 once the FILE path is un-arena'd, so
  without it the decoder's footprint becomes unmeasurable and that `log_e` is the only provenance
  signal left.

**Retired objection, recorded so it is not re-raised:** both reviews flagged per-EOF decoder churn as
the main risk. Measured on the healthy control — `lfb8` flat at 5 620 across **32 track starts / 31
EOF cycles**, no monotone decline. It does not fragment in practice.

**Owner:** Architect (ruling) + Developer · **Deps:** TASK-444 (decide together — this changes when
its corruption path is reachable) · **Gate:** `T_AE_11` (5-track, `Δacquires == 0`) and `T_AE_13`
(mixed Player+WebRadio session, `Δacquires == 1` exactly) from `test_plan.md`; `T_AE_13` needs a
working station fetch, currently blocked by TASK-438 on this rig · **Priority:** P3 — nothing is
broken by not doing it · **Status:** OPEN — filed 2026-08-15, replacing the withdrawn TASK-443.

### TASK-444 — `mb_arena_free()` can call libc `free()` on a pointer inside an already-freed arena

Found by the @VE review of TASK-443 (since withdrawn — successor TASK-452); verified in source,
not yet observed on hardware.

`mb_arena_free()` decides arena-vs-libc by pointer range against the **current** `s_base`
(`mb_arena.cpp:190-196`):

```c
if (!s_base || p < s_base || p >= s_base + s_cap) { free(ptr); return; }
```

`mb_arena_release()` sets `s_base = nullptr` immediately after `heap_caps_free(s_owned)`
(`:125-131`). So any buffer allocated **from** the arena and freed **after** a release fails the
range test, takes the libc branch, and calls `free()` on a pointer interior to a block that
`heap_caps_free()` has already returned to the allocator. That is heap corruption, and it surfaces
later and elsewhere — the worst possible failure signature to diagnose.

**Reachability.** Latent today, because both arms allocate from the arena and teardown order has so
far kept frees ahead of releases. **TASK-452 would make it newly reachable**: the FILE and URL
arms will differ in provenance while still sharing one `Audio` object and one pump, so a FILE play
entered while WebRadio's engine is up decodes out of a live arena, and whichever teardown runs first
decides whether those buffers outlive their arena. The reverse direction is safe (libc-provenance
buffers freed with an arena active fall out of range and go to libc correctly).

**Nothing covers this.** Every existing driver is single-arm: `test_ae04_teardown.py`,
`task398_connect_async_verify.py` and `test_webradio_soak.py` are URL-only;
`test_playorder_player.py` and `test_fbrowser_player.py` are FILE-only. TASK-452's `T_AE_15` is the
first test that would alternate them.

**Candidate fixes** (Architect's call, not settled here): (a) make `mb_arena_free()` fail loudly
rather than silently libc-free an unrecognised pointer that *was* in range at alloc time — the arena
already has the diagnostic (`mb_arena.cpp:207` logs "in arena range but not in slot table"); (b)
refuse to release while any slot is still `in_use`; (c) generation-count the arena so a stale-
provenance free is detectable rather than inferable.

**Owner:** Architect (fix choice) + Developer · **Deps:** none to file; interacts with TASK-452 (decide the two together) ·
**Gate:** `T_AE_15` Part B green, including zero "in arena range but not in slot table" lines ·
**Priority:** P2 today, **P1 the moment TASK-452 lands** · **Status:** OPEN — filed
2026-08-15 from the VE review.

### TASK-445 — `mb_arena.h`'s header comment misdescribes which sites call the arena

Found while explaining the arena's origins (2026-08-15). `app/lib/ESP32-audioI2S/src/mb_arena.h:3`
says:

```
// Called by the 3 patched sites in Audio.cpp + mp3_decoder.cpp.
```

Wrong on both the count and the file list. Verified by grepping every `mb_arena_alloc` /
`mb_arena_free` call site in the vendored library:

| patch | location | status | calls the arena? |
|---|---|---|---|
| `PATCH-MEMBUDGET-1` | `mp3_decoder.cpp:1534` — `#define __malloc_heap_psram(size) mb_arena_alloc(size)`, covering all 9 Helix allocs | live | **yes** |
| `PATCH-MEMBUDGET-2` | `mp3_decoder.cpp:1599` — the 9 matching `mb_arena_free()` calls | live | **yes** |
| `PATCH-MEMBUDGET-3` | InBuff | **REVERTED** (`Audio.cpp:15` — "40 K arena exhausted") | no; it is plain `calloc` (`Audio.cpp:62`) |
| `PATCH-MEMBUDGET-4` | `Audio.cpp:187-195` — halved I2S DMA config under `MEMBUDGET_PHASE1` | live | **no** — a config change, not an allocation |

So it is **two** arena call sites, both in `mp3_decoder.cpp`, and **`Audio.cpp` contains no arena
call site at all**. The surviving Audio.cpp patch is unrelated to the allocator.

**Why this is worth a task rather than a silent edit.** The sentence is the first thing a reader
meets in the arena's own header, and it is the sentence that decides where they go looking. It
implies Audio.cpp participates in arena allocation, which is exactly the wrong mental model for
TASK-452 (retire the arena from the FILE path) and for TASK-444 (an arena-provenance buffer
freed after a release). Someone reasoning about provenance from this comment would look for a call
site in Audio.cpp that does not exist, or assume InBuff is arena-backed when it is not — and InBuff
being 6 400 B of plain heap is load-bearing in every one of the memory measurements in TASK-425,
TASK-442 and TASK-443.

**Fix:** correct the sentence to name the two live sites and their file, and note that
`PATCH-MEMBUDGET-4` is a DMA-config patch with no allocator involvement. While there, the same
header's `mb_arena.h:17-20` says acquire is "Called from `WebRadioApp::_play()` (acquire) and
::suspend() (release)" — accurate today, and it becomes the *whole* truth only if TASK-443's ruling
lands, so amend it in that change rather than now.

**Owner:** Developer · **Deps:** none · **Gate:** the comment matches a fresh grep of
`mb_arena_alloc|mb_arena_free` call sites · **Priority:** P3 — comment-only, no behaviour ·
**Status:** **DONE 2026-08-15** — corrected to "2 patched sites, BOTH in mp3_decoder.cpp", with the
reverted PATCH-MEMBUDGET-3 and the non-allocator PATCH-MEMBUDGET-4 both named so the next reader is
not sent hunting an Audio.cpp call site that does not exist. Gate met by construction (no DUT
needed): the comment now states what the grep returns.

### TASK-446 — MP3 only: make the unreachable codecs actually unreachable

**Human decision, 2026-08-15: this firmware supports MP3 and nothing else.** That is already true in
practice at both entry points; this task makes it true in the build, and turns a silent
impossible-path into an explicit refusal.

**Where it is already true.** The file browser lists `.mp3`/`.m3u` only (`fileBrowser.h:17`), and the
station query pins `codec=MP3` (`dataTaskStorage.cpp:1004`).

**Where it is not.** `aac_decoder/`, `flac_decoder/` and `mp3_decoder/` all compile unconditionally —
there is **no** codec-exclusion lever in the vendored fork (`Audio.h` carries only `AUDIO_NO_SD_FS`),
so `Audio.cpp`'s dispatch (`:3768-3787`, `:4146-4147`) can still select AAC/M4A/FLAC at runtime.
Reaching them is a memory disaster rather than a clean failure: AAC allocates
`PSInfoSBR_t` 50 788 + `PSInfoBase_t` 27 364 + 1 408 ≈ **79 KB** in four blocks, on a board whose
largest free 8-bit block is ~26 KB. It also allocates through **upstream's**
`heap_caps_malloc_prefer` — the arena patch covers `mp3_decoder.cpp` only — so none of the
`MEMBUDGET_PHASE1` accounting or guards apply to it.

**The reachable path to that disaster, and the real reason for this task.** The `codec=MP3` filter is
on **radio-browser metadata, not on the stream**. A station whose metadata is wrong, or a `.pls`/`.m3u`
redirect that resolves to an AAC stream, hands `Audio` a non-MP3 bitstream and the codec dispatch
does the rest. `set wrUrl <url>` bypasses the station list entirely. Today that ends in a 79 KB
allocation attempt on a heap that cannot serve it — the failure mode TASK-432 spent a day making
survivable for the MP3 path, arriving through a door nobody has guarded.

**Scope — narrowed by the human, 2026-08-15: "leave the flash".** Item 1 below is **OUT OF SCOPE**.
Do not chase the build-exclusion or the flash saving; flash sits at 69.1 % with ~811 KB free and the
lever would cost a new patch to a fork with no `LOCAL_PATCHES.md`. **The task is item 2 only: refuse
non-MP3 explicitly.** The dead decoders stay compiled in and unreachable.

1. ~~Stop compiling `aac_decoder/` and `flac_decoder/`~~ — **dropped** (see above). For the record,
   had it been pursued: `lib_ignore` is whole-library and `build_src_filter` does not apply to
   `app/lib/`, so a `library.json` srcFilter on the vendored fork was the likely lever.
2. Make the dispatch refuse explicitly: a non-MP3 codec must surface as a clean `play FAILED` /
   `ERROR_*` with a named reason, not fall through to an allocation that cannot succeed.
3. Keep the metadata filter as-is — it is still worth having, it is just not a guarantee.

**Expected win, stated honestly.** Mostly **not** memory: the AAC/FLAC buffers are allocated lazily
at decoder init, so an unreached decoder costs no DRAM today — the win there is removing a
catastrophic path, not reclaiming bytes. Flash: the decoder tables are `.rodata`, so a real but
unmeasured saving; **flash is not currently tight** (prod at 69.1 %, ~811 KB free), so this is not
urgent on space grounds. The genuine value is correctness and one less unguarded route into the
allocator.

**Not measured, deliberately:** the exact flash/`.rodata` saving, because the exclusion mechanism
does not exist yet and quoting a number before the lever exists would be a guess.

**Owner:** Developer · **Deps:** none · **Gate:** MP3
playback unaffected on both arms (WebRadio station + local file); a deliberately AAC stream injected
via `set wrUrl` produces a named refusal and a live device, not an allocation failure; `./run/check`
7/7 · **Priority:** P2 · **Status:** **IMPLEMENTED 2026-08-15, DUT GATE OWED.**

`initializeDecoder()` now refuses any codec that is not MP3 (PATCH-MP3ONLY-1), returning false into a
caller that already handles it — so it degrades like any other shortfall rather than attempting ~79 KB
in four blocks through upstream's allocator, outside every `MEMBUDGET_PHASE1` guard. All three envs
build; `./run/check` 7/7.

**Not verified on hardware, and the status says so rather than the prose only (BP-061).** The DUT went
off the USB bus mid-session — no `/dev/ttyUSB*`, no CH340 in `lsusb` — before either half of the gate
could run. Owed when it returns: (a) MP3 still plays a 5-track playlist, (b) an AAC stream injected via
`set wrUrl` produces the named refusal. Half (b) additionally needs a reachable AAC stream, which this
AP cannot currently supply (TASK-438).

#### TASK-443 — DUT measurement, 2026-08-15: the arena is NOT the blocker at today's baseline

Conditions, recorded per LL-132: `cyd2usb_player` (`SD_BOOT_MOUNT`, `DISABLE_SPOTIFY`,
`MEMBUDGET_PHASE1`), 150 s post-reset settle, holiday AP (RSSI -47…-54, boot cascade fails over every
saved SSID before the supervisor connects), SD mounted with `/playlists/short5.m3u` loaded. All
figures are `MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT` — the cap the arena allocates with (BP-055).

**Measurement 1 — the heap is not "one big block and dust", and the nine decoder allocations fit on
their own.** New `get heapHist` probe (allocates until failure per size class, then frees; then calls
the REAL `MP3Decoder_AllocateBuffers()` with the arena inactive — real sizes, real allocator path, no
hardcoded table):

```
free8=32032 lfb8=27636   n8708=3  n4096=6  n1024=28
helixOk=true -> free8=8660 lfb8=6900     (then fully restored)
```

So option (e)'s premise holds: three holes ≥ 8 708 B exist, and the decoder's nine real allocations
succeed un-arena'd from an idle heap, leaving ~8.7 KB.

**Measurement 2 — but a real play still fails with the arena skipped.** New `set aeNoArena 1` toggle
(debug-only; the ruling would delete the acquire outright), then `set plPlay 0`:

```
arenaStats: acquires:0        <- the arena genuinely was not taken
play row 0 -> Audio + pump created -> "buffers freed, free Heap: 43884"
MP3Decoder_AllocateBuffers(): not enough memory to allocate mp3decoder buffers
play FAILED row 0             <- clean degrade, no reset (TASK-432 holding)
plCount.lfb8 after the attempt: 8180
```

**The arithmetic, and it is not close.** Engine bring-up (Audio + I2S DMA + the 6 400 B InBuff) takes
`lfb8` from 27 636 to ~8 180 — call it ~23 KB. The decoder then needs another 23 216 B. Total ≈ 47 KB
against **free8 = 32 032**. The shortfall is **~15 KB**, and no arrangement of the arena closes it:
option (a) removes a contiguity requirement that is real but not the binding constraint, and option
(e) redistributes the same bytes.

**What this does to the ruling.** Both (a) and (e) are downstream of a fact neither addresses: on
this rig, at this baseline, the variant is ~15 KB short of what one playback session costs. TASK-427
played 3+ minutes on this exact variant — and TASK-442 measured today's idle baseline as ~26 KB below
that era's. **26 KB > 15 KB**, which means the baseline swing alone accounts for the difference. The
environment question, previously filed as a side issue, **is the issue**.

**This does not make the ruling wrong.** (a) remains correct on its own terms — the arena converts a
tolerant demand into an intolerant one, measurement 1 confirms the tolerant shape is real, and
TASK-444's corruption path is unaffected by any of this. It means (a) is **necessary but not
sufficient**, and that accepting it today would produce a variant that still cannot play, which is
exactly the outcome to avoid claiming otherwise about.

**Next experiment, and it is cheap.** Find the ~26 KB. It is not Spotify (compiled out on this
variant). The candidates are the WiFi/lwIP working set left by a boot cascade that fails over every
saved network before the supervisor connects, `dataTask`'s 14 336 B stack, and TASK-433's 3 072 B of
resident browser arrays. The discriminating run is the same probe on the **home** network, where
TASK-427's number was taken — and, if that is not available, a boot with WiFi never brought up at
all, comparing `free8` at `post-init-idle`.

**Firmware added for this measurement** (both debug-only, both to be kept — they are the instruments
this decision needs): `get heapHist` and `set aeNoArena 0|1`.

### TASK-419 — real posbar seek for local files

The vendored `Audio` exposes `setFilePos()`, `setTimeOffset()`, `getFilePos()`, `getFileSize()`,
`getAudioFileDuration()`, `getAudioCurrentTime()`. The Player posbar becomes a genuine scrub against
real duration — not WebRadio's estimated slew (M-WEBRADIO-POSBAR-SLEW/SMOOTH), not Spotify's
`seek()` round-trip. Falls out of TASK-417's un-gating.

**Owner:** Developer · **Deps:** TASK-417 · **Gate:** `T_PLR_27`–`28` — ±2 s of target at 25/50/75 %,
and 20 scrubs during playback with no underrun or decoder reinit failure · **Priority:** P3 ·
**Status:** **READY** — ADR-059 accepted 2026-08-07.

### TASK-420 — PLEDIT edit mode: button strip, reorder, delete

PLEDIT title-bar tap toggles edit mode; the bottom bar — today only total-time text — becomes
`[+] [–] [↑] [↓] [SAVE]`, and row tap selects rather than plays. Reuses `settingsWidgets.h`'s
`SButton`/`sButtonBar()`. Skin-authentic (real Winamp's ADD/REM/SEL/MISC/LIST strip).

Drag-to-reorder was **rejected**: 16 px rows on a resistive panel, in direct collision with the
TASK-277 velocity-scroll gesture. Mutations are pure permutation edits — reorder permutes two
`uint16` in `viewOrder` (`playOrder` untouched: dragging a row must not make the playback queue
jump), delete memmoves `viewOrder` **and** drops the id from `playOrder`, fixing the bag cursor if it
pointed past the removed slot.

**Owner:** Developer · **Deps:** TASK-415, TASK-417 · **Gate:** `T_PLR_29`, `T_PLR_34` ·
**Priority:** P2 · **Status:** **BLOCKED** (was READY; re-marked 2026-08-14 by PM) — behind
**TASK-424** (SD write path panics in FatFs, card-independent). Delete and reorder are edits to a
playlist that has to be written back; TASK-424's own text names TASK-420/421 as the only things it
blocks, so READY was a board error, not a design change. ADR-059 (D5) is still accepted and the
design is unaffected — this is purely a sequencing correction.

> **Blocking sub-decision (OQ2):** does `bake_skin.py`'s `build_pledit_atlas()` already crop
> ADD/REM/SEL/MISC/LIST from `PLEDIT.BMP`? If not: bake-tool change + new `skin_layout.h` constants
> + `golden.sha256` re-bake + T025 determinism re-check. Check before estimating this task.

### TASK-421 — add-from-browser (staging), save, restore

Add appends to `entries[]` with a "staged" flag (path in the bounded staging arena) and appends the
id to both permutations. SAVE streams `viewOrder`, copying each source line to `<name>.m3u.tmp`,
emitting staged entries **from the staging arena** — they have no backing offset yet, and the naive
copy loop drops them *while reporting success* — then renames. One sequential pass, constant memory.
Rename is the atomic commit point. Mount-time sweep deletes stray `.tmp` files.

SAVE is the one unbounded SD operation: it runs only from edit mode and **pauses playback** for its
duration — deliberate and visible, not a background write.

**Owner:** Developer · **Deps:** TASK-420 · **Gate:** `T_PLR_30`–`33`. **`T_PLR_30` and `T_PLR_31`
are verified host-side, off the card** — shuffle ON + reorder + SAVE must write **display** order,
and staged adds must survive. Both have failure modes where the device confidently reports success;
**never verify a save by re-reading through the structure that produced it** ·
**Priority:** P2 · **Status:** **BLOCKED** (was READY; re-marked 2026-08-14 by PM) — behind
**TASK-424** for the same reason as TASK-420: save/restore is a write path. ADR-059 unaffected.

### TASK-422 — build variants, soak, VE suite, registry completion

Compile-time mode flags `-DPLAYER_SPOTIFY` / `-DPLAYER_WEBRADIO` / `-DPLAYER_LOCAL` (presence only,
never `=0` — LL-006). Four consequences are **not** automatic: cycling iterates the compiled-in set
(a single-mode build must not cycle); a persisted `playerMode` naming an absent mode falls back to
the first compiled-in one; `TASKBAR_APP_COUNT` computed from the compiled-in tail; Settings lists
only compiled-in modes. Existing `-DDISABLE_SPOTIFY` stays as-is — load-bearing for the harness's
`get variant` fast path, do not migrate it here.

**No 2³ env matrix.** `check_build.sh` runs two full builds today; eight would make the gate
unusable. Add exactly one dev env `cyd2usb_player` (Player only), mirroring the existing
`cyd2usb_webradio` precedent. Gates go 6 → 7.

**`cyd2usb_player` already exists** (landed in TASK-427, 2026-08-11 — Architect ruling TASK-431 option
a required it ahead of this task's own schedule). `app/platformio.ini`: extends
`cyd2usb_winamp_debug`, adds `-DDISABLE_SPOTIFY`. DUT-verified: boots, mounts SD, arena acquires, MP3
plays. This task's remaining scope here is narrower than originally scoped: just the
`check_build.sh` 6→7 gate addition — the env itself, and its build+boot+playback verification, are
done. **One loose end for this task:** as landed, `cyd2usb_player` is flag-for-flag identical to
`cyd2usb_webradio` (both are `cyd2usb_winamp_debug` + `-DDISABLE_SPOTIFY`) — it is a distinct name and
binary but not yet a distinct *configuration*. This task's `-DPLAYER_LOCAL` / `-DPLAYER_WEBRADIO`
work is what makes them actually differ; until then, do not read a `cyd2usb_player` result as
evidence about a Player-only compiled mode set.

Close-out: complete the reserved `feature_inventory.yaml` entries and X050–X064, walk
`NEW-APP-CHECKLIST.md` for `AppId::LocalPlayer`, and run the sustained soak.

### TASK-422 parts A + B (2026-08-14) — implemented by subagent, reviewed and independently verified

**Part A — compile-time mode flags.** Presence-only `-DPLAYER_SPOTIFY` / `-DPLAYER_WEBRADIO` /
`-DPLAYER_LOCAL` (never `=0`, LL-006), with a backfill: an env defining none of the three gets all
three, so every existing env is unchanged. The ordered set `kPlayerModes[]` in `settingsStorage.h`
is the single source of truth — cycling (`playerModeNext`), the persisted-mode fallback
(`playerModeResolve`) and the Settings row all read it, and no consumer re-derives membership with
its own `#ifdef`. It lives in the header rather than `main.cpp` because `settingsStorage.cpp` is a
separate TU and needs the same set for the load-time clamp.

Consequences wired: cycling iterates the set (`main.cpp resolvePlayerTap`, was `% 3`); a persisted
mode naming an absent one resolves to the first compiled-in mode (one widened clamp in
`SettingsStorage::load()`, not a second divergent one); `appIdForPlayerMode()` resolves before
mapping, so an injected absent mode cannot select an app that was never instantiated; the Settings
"Applications → Winamp → Mode" row (`appsSection.h`) lists and cycles only compiled-in modes and
early-returns on a single-mode build (no save, no repaint).

**Part B — `check_build.sh` 6 → 7.** `cyd2usb_player` added as gate 3, labels renumbered, and the
warn-only settings-wiring gate now prints `[warn] … (not counted)` instead of a `[7/7]` sitting next
to a `[6/6]` total. `run/check`'s "5-gate" header (already stale before this) corrected.

**Verification — done by the orchestrator, not taken on report.**
- Full diff reviewed line by line.
- `./run/check` re-run independently: **7 passed, 0 failed**.
- **Set construction proved with a stronger probe than the subagent's**: temporary `static_assert`s
  on the set *contents and order*, not just its size — `-DPLAYER_LOCAL` alone yields
  `kPlayerModeCount == 1 && kPlayerModes[0] == Player`; no flags yields `count == 3`,
  `[0] == Spotify` (the fallback), `[2] == Player` (cycle order). Both compiled clean.
- **Negative control run** (LL-127): flipping one assertion to a deliberately wrong value produced
  the expected compile error, proving the probe could fail. Probes and scratch envs removed;
  `app/platformio.ini` is byte-identical to its committed state.

**Two claims in this task's own text were checked rather than implemented on faith:**
- *"`TASKBAR_APP_COUNT` computed from the compiled-in tail"* — **does not hold, no work done.**
  `TASKBAR_APP_COUNT` is already anchored to `AppId::Settings + 1` (TASK-413 fixed exactly this), and
  `gen_app_registry.py`'s `EJECT_ONLY_TAIL = ["WebRadio", "LocalPlayer"]` puts both player apps after
  Settings, so neither owns a taskbar slot and compiling a mode out cannot change the count.
- *"Settings lists only compiled-in modes"* — **holds, implemented** (`appsSection.h`).

**Scope NOT taken, stated so it is not mistaken for done:** the flags gate mode *reachability* only.
They do not drop app objects, headers or `appRegistry.h` rows, so a single-mode build is not smaller.
ADR-059 D10 also asks for that; it would move `AppId` values and disturb the taskbar/registry
static_asserts, and is left for its own task.

**Design tension for the Architect — do NOT resolve it by editing `platformio.ini` casually.** This
task's text says the added dev env should be "Player only", i.e. `cyd2usb_player` should carry
`-DPLAYER_LOCAL`. It deliberately does not, because that env is currently the *playback test vehicle
for the whole milestone*: `T_PLR_01`/`T_PLR_02` cycle all three modes on it and were run green on it
today. Adding `-DPLAYER_LOCAL` would make those two tests unrunnable there. Either the flag goes on a
new fourth env, or those tests move — an Architect call, not a config tweak.

**Gates `T_PLR_35`–`40` remain owed.** `T_PLR_36` (persisted mode naming a compiled-out mode must
fall back, only reproducible over *existing* settings — X064) cannot run at all until some env
actually defines the flags: today none does, so the fallback path is implemented but unexercised in
every shipping configuration. `T_PLR_39` (≥30 min playback with concurrent browsing) is blocked by
**TASK-442** — that variant cannot start playback.

### TASK-422 part C — `NEW-APP-CHECKLIST.md` walk for `AppId::LocalPlayer` (2026-08-14)

Walked all eight sections against the code. **5 pass, 1 documented deviation, 1 gap, 1 owed.**

| # | Checklist item | Result |
|---|---|---|
| 1 | `hasPendingAsync()` override | PASS — `localPlayerApp.h:383`, returns `_browser.pending()` |
| 2 | `tlsYield()`/`tlsResume()` bracketing | N/A — LocalPlayer makes no HTTPS calls. The engine yields on its behalf: `aeConnectFile()` takes a **bounded** `tlsTryYield()` (TASK-430). Recorded rather than ticked, because the obligation is met by delegation, not by absence |
| 3 | `dbgGet`/`dbgSet` standard interface | **DEVIATION — see below** |
| 4 | `cmdTap` busy propagation | PASS — `main.cpp:3272` checks `hasPendingAsync()` on the LocalPlayer branch |
| 5 | `cross_feature_matrix.yaml` entries | **GAP** — X050–X064 all exist and are substantive, but **every one has `test_coverage: []`**, including three marked `risk: high`. This is the QM audit's third dimension failing on the newest milestone |
| 6 | Taskbar visibility + icon | PASS — taskbar-hidden by design, shares the player slot; `taskbar.h:29/65/80` carry the invariant and the static_asserts |
| 7 | `init()` vs `resume()` first paint (BP-048) | **OWED** — both exist (`:134`/`:163`), but "init produces the COMPLETE first paint" is a pixel claim that greps cannot settle. Needs a screendump on `cyd2usb_player` |
| 8 | `AppSettings` field wiring | PASS — `./run/check` step 7/7 reports every field wired |

**Item 3, the deviation.** `WebRadioApp` and `PlaneRadarApp` implement
`bool dbgGet(const char* var, char* buf, int len) const`; `LocalPlayerApp` instead exposes bespoke
methods (`dbgReport`, `dbgMem`, `dbgRow`, `dbgFbState`, `dbgOrder`, `dbgCursor`, `dbgLoad`,
`dbgPlayRow`) dispatched directly from `main.cpp:3837-3856` and `:4136-4150`. It works and the
harness uses it heavily. It is recorded as a deviation rather than ticked or silently fixed:
converting it is a refactor with no behavioural gain, and the next author needs to know the two
shapes coexist.

**Found while walking item 3, unrelated to the checklist:** `localPlayerApp.h:543` reads
"TASK-435 temporary diagnostic (**not part of the fix, do not commit**)" — and it was committed, in
`fea2978`. The code itself has since proved its worth: its `lfb8` field is what measured TASK-442's
2 932 B shortfall today, and `fileOpen` is what proves `closeIfIdle()` actually fired. **Resolution:
keep the code, retire the comment** — it now tells a reader to delete the most useful diagnostic on
the player path. Flagged here rather than fixed in the same breath only because a subagent is
holding `app/src` for TASK-422 part A.

**Owner:** Developer + VE · **Deps:** all of the above · **Gate:** `T_PLR_35`–`40`.
**`T_PLR_36` is the dangerous one** — a persisted mode naming a compiled-out mode must fall back,
not null-app-crash, and it is only reproducible over *existing* settings: **a clean flash will not
catch it** (X064). `T_PLR_39` is ≥30 min playback **with concurrent browsing and scrolling**, not
idle playback · **Priority:** P2 · **Status:** **PARTIAL — parts A, B, C done 2026-08-14; part D
(soak) BLOCKED.** Not DONE, deliberately: see the resolution note below for exactly what is and is
not verified. ADR-059 accepted 2026-08-07 (D10).

---

## Closed — TASK-426 (2026-08-10, filed from a DUT "no network" investigation)

### TASK-428 — apply the ASCII fold to the Spotify queue and station-list rows

TASK-415 resolved design OQ1 with a shared helper (`util/asciiFold.h`, `textfold::foldUtf8`) and
wired it into `LocalPlaylistSource` only. The same latent bug is live in the two shipped sources:
`SpotifyQueueSource::row()` copies the API's UTF-8 artist/title straight into `PlRow::text`, and
`StationListSource::row()` does the same with radio-browser station names — both then render through
TFT_eSPI Font 1 (GLCD), whose glyphs above 0x7F are box-drawing symbols. An accented artist name
("Björk", "Sigur Rós", "Motörhead") therefore renders as unrelated symbols today, one per UTF-8
continuation byte.

The fix is one call per source. What makes it a separate task is the gate: TASK-411 and TASK-412
were held to **pixel identity** against the pre-extraction PLEDIT copies, and this deliberately
changes pixels for exactly the rows that were wrong. It needs its own before/after screendump pair
on real content, not a silent rider on a task whose gate is about something else.

Also in scope: the Winamp **title marquee** (`winampDisplay.setTitle()`) draws through `SKIN_FONT` /
`SKIN_GLYPH[128]`, i.e. a 128-entry ASCII atlas — same class of bug, same one-line fix, and the more
visible of the two since the title is 8 px tall and scrolls.

**Owner:** Developer · **Deps:** TASK-415 (helper landed) · **Gate:** screendump before/after on a
queue containing at least one Latin-1 and one Latin-Extended-A name; `T_PLE_*` row-geometry tests
must be unchanged (the fold changes glyphs, never column widths — a 2-byte codepoint folding to 1–2
ASCII characters can change a row's rendered *length*, so the truncation path is what to watch) ·
**Priority:** P3 · **Status:** OPEN — filed 2026-08-11 from TASK-415's OQ1 resolution.

### TASK-429 — a settings save during playback silently aborts

Found in TASK-415. `SettingsStorage::save()` builds a `DynamicJsonDocument(6144)`. While a track is
playing, the Helix arena holds the large contiguous blocks and the **8-bit-capable** largest free
block drops to ~2.8 KB (boot log: `freeDma=3028 lfbDma=2804` right after decoder init), so the
document's constructor allocation fails, ArduinoJson reports capacity 0, every add no-ops, and
TASK-329's `doc.overflowed()` guard aborts the write with
`SettingsStorage: JSON doc OVERFLOWED — save aborted, previous file kept!`.

The guard does its job — nothing is corrupted and the previous file survives — but the *caller* is
told nothing: `save()` returns void, so a feature that persists something during playback silently
does not persist it. TASK-415 dodged this by coalescing its write into `suspend()` (ADR-050 rule 3),
which is the right pattern anyway, but the trap is general: any settings write while audio is up
hits it, and the next author will not know.

Worth noting the diagnostic gap too: the success path logs `saved (doc 1914/6144 B)` while the
failure path logs no numbers at all, so the log line reads like a capacity overflow when it is
really a failed allocation. The two are indistinguishable in the field today.

Candidate fixes: (a) `save()` returns bool and callers handle it; (b) defer-and-retry a failed save
rather than dropping it; (c) shrink or statically place the document so the allocation cannot fail;
(d) at minimum, log `memoryUsage()`/`capacity()` on the failure path so the two modes are
distinguishable. (a)+(d) are the cheap pair.

**Owner:** Developer · **Deps:** none · **Gate:** set a persisted value from a debug command while a
local file is playing, reboot, confirm it survived; assert the log distinguishes alloc-failure from
true overflow · **Priority:** P2 · **Status:** **DONE 2026-08-15** — both halves of the gate pass;
fixes (a), (b) and (d) all landed, plus a follow-up the same day: an intentional reboot beat the
deferred retry (the heap is still held at reboot time), so all three restart paths now tear the
engine down before flushing — see TASK-451's `T_PRM_01` section, which is where that gap was found. The status said OPEN until 2026-08-15 because it was written when
half the gate still failed and was not revisited when fix (b) closed it — caught by generating the
placeholder table in `tasks.md`, which is a use for that table nobody intended. See below.

#### TASK-429 gate result (2026-08-15, `cyd2usb_player`, during real playback)

**Half 2 — "the log distinguishes alloc failure from true overflow": PASS.** Captured live while a
track was playing (`playing:true`, `curRow:2`, `lfb8:5620`):

```
>>> set fmt24h 0
SettingsStorage: save aborted — doc ALLOC FAILED (capacity 0, wanted 6144 B;
  lfb8=5620 freeInt=48828). Audio arena up? Coalesce the write into suspend()
  (ADR-050 rule 3). Previous file kept.
```

`settingsSaveCount` → `count:1 failAlloc:1`; a forced `set settingsSave 1` while still playing gave
`failAlloc:2` with `count` still 1. The overflow branch is code-separate with its own counter but is
not triggerable without a schema change, so it is unproven by observation.

**Half 1 — "set a value during playback, reboot, confirm it survived": now PASS (2026-08-15, after
fix (b) landed).** Full chain on `cyd2usb_player`:

```
set fmt24h 0 during playback -> save aborted — ALLOC FAILED (lfb8=5364) … Deferred; will retry
switchApp away from Player   -> SettingsStorage: deferred save landed (TASK-429)
                                SettingsStorage: saved (doc 1929/6144 B)
counters: count 1->2, failAlloc 1, pending true -> false
after reboot, ./run/spiffs pull settings.json -> "fmt24h": false     <- the value survived
```

Verified through the SPIFFS file rather than the write path that produced it.

**The retry alone was not enough, and the measurement is why.** A first implementation retried every
10 s from `loop()` and never landed: the engine holds the contiguous heap for the whole Player
session, not just while a track plays, so `lfb8` stayed ~5.6 KB even idle — six retries in 45 s, all
refused. The write can only land when the engine is torn down, so `suspend()` now force-flushes it.
That is ADR-050 rule 3's "coalesce the write into suspend()" applied to a write **the user made
earlier**, which is the case the rule never covered. Also quieted the repeat: the first abort of an
episode reports in full, retries are silent (six identical ERROR-shaped lines in 45 s otherwise).

**Superseded — the original FAIL, kept for the record:** Verified independently of the write path via `./run/spiffs pull settings.json` → `fmt24h`
still `true` after a reboot. Only fixes (a) and (d) landed; **nothing defers or retries the write**,
so the value set during playback is still lost. The gate as written cannot pass until (b)
(defer-and-retry) is implemented — which is now the remaining work on this task, and the idle-control
first (`set fmt24h 1` → `saved (doc 1907/6144 B)`, `count` 0→1) proves the mechanism is sound when
the heap allows.

**New defect found by the gate, fixed in the same commit:** `save()` returns bool (fix (a)) but
**both debug call sites discarded it** — `set settingsSave` printed `"saved":true` unconditionally
and `set fmt24h` printed `"ok":true`, both while the save had just aborted with `failAlloc`.
Any harness asserting on those replies would false-PASS. Both now report the real result
(`"saved":false`), which is exactly what fix (a) existed for and was not wired to.


---

## PM note — what went wrong on this milestone (2026-08-15)

Recorded here rather than in a retrospective nobody re-reads, because the remaining tasks in this
file inherit it.

**The design was not the problem.** ADR-059's decisions (D2 the shared engine, D6/D7 the three-way
mode, D10 the build variants) all survived contact with the hardware. Nothing in this milestone was
lost to a design that turned out wrong.

**Three things went wrong, all downstream of design:**

1. **A measurement without conditions became a premise.** TASK-427 recorded "MP3 plays" and a heap
   figure, with nothing about the environment. Three later task write-ups reasoned from it as a
   property of the commit. It did not reproduce on its own commit four days later. → BP-062.
2. **A P1 was closed against a proxy path.** TASK-432 was gated on a shared code path because the
   real one could not be tested; the real one later exposed two defects in the shipped fix. → BP-061.
3. **A plausible mechanism became the frame, and review reinforced it.** The arena's contiguity
   asymmetry was real, measured, and not the binding constraint. An Architect ruling, three team
   reviews and five filed tasks were spent inside that frame while the cause — a boot TLS session on
   a build with Spotify compiled out — sat in every capture taken during the investigation. → BP-063.

**What this implies for the tasks below.** TASK-443 is the clearest casualty: it has been reframed
three times, its central hypothesis is falsified, and it now carries more review than conclusion. It
should be **re-issued or withdrawn by the Architect**, not incrementally patched again. TASK-444,
TASK-445 and TASK-424 are independent of it and stand on their own evidence.

**What went right, and is worth keeping:** every fix in this milestone was gated on hardware before
being called done; the failure paths now degrade visibly rather than resetting or hanging; and the
three subagent reviews each caught a real error in the orchestrator's brief. The verification
discipline held. The framing discipline did not.

---

## PM note — what went wrong on this milestone (2026-08-15)

Recorded here rather than in a retrospective nobody re-reads, because the remaining tasks in this
file inherit it.

**The design was not the problem.** ADR-059's decisions (D2 the shared engine, D6/D7 the three-way
mode, D10 the build variants) all survived contact with the hardware. Nothing in this milestone was
lost to a design that turned out wrong.

**Three things went wrong, all downstream of design:**

1. **A measurement without conditions became a premise.** TASK-427 recorded "MP3 plays" and a heap
   figure, with nothing about the environment. Three later task write-ups reasoned from it as a
   property of the commit. It did not reproduce on its own commit four days later. → BP-062.
2. **A P1 was closed against a proxy path.** TASK-432 was gated on a shared code path because the
   real one could not be tested; the real one later exposed two defects in the shipped fix. → BP-061.
3. **A plausible mechanism became the frame, and review reinforced it.** The arena's contiguity
   asymmetry was real, measured, and not the binding constraint. An Architect ruling, three team
   reviews and five filed tasks were spent inside that frame while the cause — a boot TLS session on
   a build with Spotify compiled out — sat in every capture taken during the investigation. → BP-063.

**What this implies for the tasks below.** TASK-443 is the clearest casualty: it has been reframed
three times, its central hypothesis is falsified, and it now carries more review than conclusion. It
should be **re-issued or withdrawn by the Architect**, not incrementally patched again. TASK-444,
TASK-445 and TASK-424 are independent of it and stand on their own evidence.

**What went right, and is worth keeping:** every fix in this milestone was gated on hardware before
being called done; the failure paths now degrade visibly rather than resetting or hanging; and the
three subagent reviews each caught a real error in the orchestrator's brief. The verification
discipline held. The framing discipline did not.
