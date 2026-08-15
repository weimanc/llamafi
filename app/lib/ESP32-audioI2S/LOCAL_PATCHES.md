# LOCAL_PATCHES — ESP32-audioI2S (vendored fork)

> Created 2026-08-15 (TASK-449). This fork has carried local patches since TASK-261 Phase 2
> (`f36152b`) with **no patch record at all** — unlike `app/lib/SD/` and `app/lib/SpotifyArduino/`,
> which have had one for exactly this reason. A platform or library bump would have silently dropped
> every entry below. Written while adding PATCH-INBUFF-1, because adding a fifth undocumented patch
> to an undocumented fork was not defensible.

**Upstream:** ESP32-audioI2S **v2.3.0**, vendored into `app/lib/ESP32-audioI2S/`.

**DO NOT BUMP TO v3.x.** It allocates ~704 KB at boot and crashes instantly on a no-PSRAM CYD
(EXP-008 / EXP-009 / BP-042). The registry entry was removed so the local copy is picked up.

---

## PATCH-MEMBUDGET-1 — Helix decoder allocations routed to the arena
**File:** `src/mp3_decoder/mp3_decoder.cpp:1534` · **Task:** TASK-261 Phase 2 · **Status:** live

`#define __malloc_heap_psram(size) mb_arena_alloc(size)` under `MEMBUDGET_PHASE1`, redirecting all
nine `MP3Decoder_AllocateBuffers()` allocations (total 23 216 B, largest `SubbandInfo_t` at 8 708 B)
into the reserved arena. Upstream's definition (`heap_caps_malloc_prefer`) is kept for the
non-`MEMBUDGET_PHASE1` build.

## PATCH-MEMBUDGET-2 — matching frees
**File:** `src/mp3_decoder/mp3_decoder.cpp:1599` · **Task:** TASK-261 Phase 2 · **Status:** live

The nine `mb_arena_free()` calls pairing Site 1. `mb_arena_free()` has an in-range guard, so
out-of-arena pointers fall through to libc `free()`.

## PATCH-MEMBUDGET-3 — InBuff into the arena
**Status: REVERTED.** See `src/Audio.cpp:15`. A 40 K arena was exhausted by it; InBuff stays on plain
`calloc` (`Audio.cpp:62`). Recorded because its absence is load-bearing in every memory measurement
from TASK-425 onward — InBuff's 6 400 B comes from the general heap, not the arena.

## PATCH-MEMBUDGET-4 — halved I2S DMA config
**File:** `src/Audio.cpp:187-195` · **Task:** TASK-261 Phase 2 · **Status:** live

Under `MEMBUDGET_PHASE1`, 8×256 instead of 16×512. **Not** an allocator patch — no arena involvement.
Note (TASK-443): the reason for it was arena pressure on the WebRadio path; it has never been
re-measured for the FILE path.

## PATCH-INBUFF-1 — a failed InBuff allocation must refuse the connect
**Files:** `src/Audio.cpp` `initInBuff()` + `connecttoFS()` · **Task:** TASK-449 · **Status:** live

Upstream's `initInBuff()` calls `InBuff.init()`, logs **only** `if (size > 0)`, propagates nothing
and returns `void`. When the 6 400 B `calloc` fails, `connecttoFS()` still succeeded, the decoder
initialised, `m_f_running` was set and the UI rendered `playing:true` — with no ring buffer, so no
byte ever moved. DUT-observed 2026-08-15 on `cyd2usb_winamp_debug`: 122 s on a 3 s track, pump
spinning at ~525 cycles/s with `maxPumpMs=0`, and **not one error line**.

Patch adds an `else { log_e(...) }` naming the failure with the live `lfb8`, and an
`if(!InBuff.isInitialized()) return false;` guard immediately after `setDefaults()` in
`connecttoFS()`, so a shortfall degrades to `play FAILED` (TASK-432's invariant) instead of hanging.

**Known gap, deliberately not patched here:** `connecttohost()` has the same exposure and is NOT
guarded — the WebRadio path was not the one under test, and changing its timing has cost a real
defect before (TASK-406). Do it with a WebRadio soak, not blind.

## PATCH-MP3ONLY-1 — refuse any codec that is not MP3
**File:** `src/Audio.cpp` `initializeDecoder()` · **Task:** TASK-446 · **Status:** live

Human decision 2026-08-15: this firmware supports MP3 only. Both sources already enforce it
(browser lists `.mp3`/`.m3u`; station query pins `codec=MP3`), but the station filter reads
radio-browser *metadata*, not the stream — a mislabelled station or a `.pls` redirect can still
present AAC. Reaching the AAC path asks ~79 KB in four blocks through **upstream's**
`heap_caps_malloc_prefer`, outside `mb_arena` and therefore outside every `MEMBUDGET_PHASE1` guard.
The guard returns false, which the caller already handles, so it degrades like any other shortfall.

**Deliberately NOT done** (human: "leave the flash"): the AAC/FLAC decoders are still compiled in.
Flash sits at 69.1 % with ~811 KB free, and excluding them would have meant a `library.json`
srcFilter — a further patch for no functional gain. They are unreachable, not absent.

---

## The other local file in this tree

`src/mb_arena.{h,cpp}` is **not a patch, it is an addition** — a project-authored fixed-slot
allocator (TASK-261 Phase 2 / TASK-267 / ADR-047), not present upstream. It is the target of
PATCH-MEMBUDGET-1/2. See TASK-452/444 for its open design questions (TASK-443 was withdrawn 2026-08-15).
