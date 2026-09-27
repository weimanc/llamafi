# LOCAL_PATCHES — ESP32-audioI2S (vendored fork)

> Created 2026-08-15 (TASK-449). This fork has carried local patches since TASK-261 Phase 2
> (`f36152b`) with **no patch record at all** — unlike `app/lib/SD/` and `app/lib/SpotifyArduino/`,
> which have had one for exactly this reason. A platform or library bump would have silently dropped
> every entry below. Written while adding PATCH-INBUFF-1, because adding a fifth undocumented patch
> to an undocumented fork was not defensible.

**Upstream:** ESP32-audioI2S **v2.3.0**, vendored into `app/lib/ESP32-audioI2S/`.

**Licence: GPL-3.0** (see `LICENSE` beside this file — the verbatim text from the esphome fork's
`2.3.0` tag, checked 2026-09-26 against upstream's `LICENSE` and the GNU text; identical). Upstream
schreibfaul1/ESP32-audioI2S is GPL-3.0 at every tag checked (2.0.3, 2.0.6, 3.0.0). **This copy is
modified** — the patches below are the modification record GPL-3.0 §5(a) asks for. The decoders'
provenance was validated 2026-09-26 and is **not clean**:
- **`mp3_decoder` and `aac_decoder` are RealNetworks Helix code** (shared entry points with upstream
  libhelix, e.g. `MP3FindSyncWord`/`MP3Decode`; the AAC decoder carries Helix's SBR tables) with the
  Helix licence block and author credits **stripped** (0 hits for "RealNetworks" or "Jon Recker" in
  either file **as vendored** — restored 2026-09-26: the verbatim Helix licence block and credits are back at
  the top of both `.cpp` files (short pointers in the `.h`), and `licenses/` holds RPSL 1.0, RCSL 1.0 and
  Helix's own notice, copied from libhelix). Helix DNA is licensed **RPSL 1.0 or RCSL 1.0**, verbatim in
  `ultraembedded/libhelix-mp3`'s `LICENSE.txt`. The FSF lists the RPSL as **GPL-incompatible**
  (derivatives must stay RPSL; litigation venue clause). So this GPL-3.0 library ships RPSL-derived
  code under a GPL label: upstream's problem, but ours the moment we distribute a binary.
- **`flac_decoder` is Nayuki's Simple FLAC implementation, MIT** ("License: MIT" on the project page).
  MIT is GPL-compatible, but requires the copyright and licence notice to travel with it; this copy
  has only a "from nayuki.io" comment. The exact copyright line was not seen and is not invented here.
Open as TASK-722.

**DO NOT BUMP TO v3.x.** It allocates ~704 KB at boot and crashes instantly on a no-PSRAM CYD
(EXP-008 / EXP-009 / BP-042). The registry entry was removed so the local copy is picked up.

---

## PATCH-MEMBUDGET-1 — Helix decoder allocations routed to the arena
**File:** `src/mp3_decoder/mp3_decoder.cpp:1577` · **Task:** TASK-261 Phase 2 · **Status:** live

`#define __malloc_heap_psram(size) mb_arena_alloc(size)` under `MEMBUDGET_PHASE1`, redirecting all
nine `MP3Decoder_AllocateBuffers()` allocations (total 23 216 B, largest `SubbandInfo_t` at 8 708 B)
into the reserved arena. Upstream's definition (`heap_caps_malloc_prefer`) is kept for the
non-`MEMBUDGET_PHASE1` build.

## PATCH-MEMBUDGET-2 — matching frees
**File:** `src/mp3_decoder/mp3_decoder.cpp:1642` · **Task:** TASK-261 Phase 2 · **Status:** live

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

## PATCH-DAC-1 — built-in DAC gets midpoint silence, never literal zero
**File:** `src/Audio.cpp` (ctor, `stopSong()`, `playI2Sremains()`, `pauseResume()`, `sendBytes()`) ·
**Task:** TASK-724 · **Design:** `docs/architecture/designs/M-WEBRADIO-DAC-STABILITY.md` (Option A) ·
**Status:** live

Upstream was written for external I2S DACs, where a literal-zero PCM word is silence. The ESP32
built-in DAC consumes **unsigned** PCM (`playSample()` adds `0x80008000`), so silence there is the
midpoint `0x8000` — a literal zero is the negative rail, heard as a pop. Five upstream sites wrote or
produced literal zero into the DMA ring: `tx_desc_auto_clear` (any underrun), the ctor's initial
`i2s_zero_dma_buffer()`, `stopSong()`, `pauseResume()`, and `sendBytes()`'s recoverable-decode-error
path. All five are now gated on `m_f_internalDAC`: the built-in-DAC branch calls `playI2Sremains()`
(midpoint-primed via the normal sample path) or, for the decode-error case, simply leaves the queued
audio alone; the external-I2S branch is byte-identical to upstream.

`playI2Sremains()` also gained a bound: it filled `m_validSamples = dma_buf_len * dma_buf_count` in
one pass, which exceeds the `m_outBuff` capacity (2048 stereo frames) for any DMA config larger than
production's 8×256 — latent since PATCH-MEMBUDGET-4, never triggered because no shipping env used a
bigger ring. Now fills in `m_outBuff`-sized chunks, safe for any configured ring size.

**Zero DMA-pool cost** — no `dma_buf_len`/`dma_buf_count` change. A PR (external, weimanc/llamafi#1)
proposed also widening the ring to 8×512; the design doc's memory budget found that does not fit
(measured free-DMA at decoder-init: ~5.1 KB WebRadio / ~2.4 KB Player, both go negative at +8 KB) and
it was not taken.

**Side effect, not hidden:** with `tx_desc_auto_clear` off, a genuine underrun on the built-in DAC now
replays the last primed content (≈46 ms at 8×256) instead of stepping to the rail — quieter (a buzz/
stutter) rather than a click, but not literal silence unless volume is 0. Not yet DUT-verified for
audible correctness (see the design doc's exit criteria).

---

## The other local file in this tree (relocated 2026-08-26, TASK-476)

`mb_arena.{h,cpp}` used to live here as `src/mb_arena.{h,cpp}` — **not a patch, an addition** — a
project-authored fixed-slot allocator (TASK-261 Phase 2 / TASK-267 / ADR-047), not present upstream.
It has moved to `app/src/mem/arena/mb_arena.{h,cpp}`, since it's project-owned code with no upstream
counterpart and doesn't need to live inside the vendored fork. PATCH-MEMBUDGET-1/2 above still target
it — `mp3_decoder.cpp` now reaches it via `#include "mem/arena/mb_arena.h"`, resolved through the
`-Isrc` include path already granted to library sources (confirmed via `pio run -t compiledb` before
the move; TASK-476). See TASK-452/444 for its open design questions (TASK-443 was withdrawn
2026-08-15).
