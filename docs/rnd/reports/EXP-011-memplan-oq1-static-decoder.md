# EXP-011 — M-MEMPLAN OQ1: static-always decoder region viability (TASK-268)

> Owner: R&D · 2026-06-28 · Branch: `rnd/memplan` · DUT: ESP32-2432S028R (no PSRAM, `cyd2usb_webradio`)
> Feeds: M-MEMPLAN §10 (OQ1 resolution), TASK-268 Phase 1 deliverable.
> Prior art: TASK-265 (fetch-vs-arena, boot reservation) · TASK-267 (JIT fix, PASS)

---

## Question

M-MEMPLAN OQ1: can the Helix decoder arena be a **static BSS region** (always present from boot, pool
permanently smaller) instead of the current **runtime-JIT heap alloc** (`mb_arena_acquire()` at `_play()`)?

A static region eliminates the JIT alloc/release lifecycle and makes the decoder's location
build-time-deterministic (the goal of M-MEMPLAN). The cost is that the decoder's ~23 K permanently occupies
BSS, competing with the station-fetch TLS (~40 K) that runs before `_play()`.

---

## Method

### Baseline (Trial B, no static decoder)

Build: `cyd2usb_webradio` (`MEMBUDGET_PHASE1` + `DISABLE_SPOTIFY`) with `rnd/memplan` Phase 1 changes
(mem_manifest.yaml, gen_mem_layout.py, mem_layout.h included in main.cpp — but the static overlay arrays
optimized away as unused). Arena: JIT at `_play()` (TASK-267 current behaviour).

### OQ1 variant (Trial S, MEMPLAN_STATIC_DECODER)

Added `MEMPLAN_STATIC_DECODER` build flag to `cyd2usb_webradio`. Changes in `mb_arena.cpp`:
- `static uint8_t s_static_decoder_buf[23216] __attribute__((aligned(4)))` in BSS (exact Helix HWM)
- `mb_arena_init_static()` called from `main.cpp::setup()` before WiFi / any fetch
- `mb_arena_acquire()` returns true immediately (no heap alloc); `mb_arena_release()` resets slot table only

Decoder arena: backed by BSS array from boot; no JIT acquire; present during station fetch.

---

## Results

### Trial B — baseline (JIT arena, no static decoder)

| Measurement | Value |
|---|---|
| DUT idle: heap | 107 K |
| DUT idle: maxAlloc | 57 K |
| At WebRadio entry: freeInt | 110,184 B |
| At WebRadio entry: maxAlloc | 59,380 B |
| At fetch time (dataTask pre-SSL): maxBlk | **57 K** |
| Fetch result (mirror de1) | code=-11 (TCP timeout — mirror unreachable) |
| Fetch result (mirror all) | **code=200, count=16** |
| wrCount after fetch | **16** (PASS) |

JIT arena baseline: fetch succeeds. maxBlk=57K > 40K TLS. Consistent with TASK-267 (lfbInt=61K at _play() after fetch).

**Note:** `gen/mem_layout.h` static overlay arrays (40,616 B declared) were **optimized away** by the
compiler — confirmed via `nm` on the ELF (no `s_overlay_*` symbols present). Zero BSS impact in Phase 1.
This is the correct Phase 1 behaviour: the header is declarative, not instantiated until Phase 2 wires it.

### Trial S — OQ1 static decoder (23,216 B BSS, present during fetch)

| Measurement | Value |
|---|---|
| DUT idle: heap | **85 K** (−22 K from baseline) |
| DUT idle: maxAlloc | **37 K** (−20 K from baseline) |
| At WebRadio entry: freeInt | 87,352 B |
| At WebRadio entry: maxAlloc | 38,900 B |
| At fetch time (dataTask pre-SSL): maxBlk | **37 K** |
| SSL error | **`MBEDTLS_ERR_SSL_ALLOC_FAILED (-32512)`** — both mirrors |
| Fetch result (mirror de1) | code=-1, elapsed=162 ms (TCP OK, SSL fail) |
| Fetch result (mirror all) | code=-1, elapsed=92 ms (TCP OK, SSL fail) |
| wrCount after fetch | **0** (FAIL) |

Static decoder: fetch fails. maxBlk=37K < ~40K mbedtls SSL context. Identical failure mode to TASK-265
(boot-held 24K heap arena → maxBlk=35K → -32512), confirming the same root cause: static DRAM reduces
the contiguous heap available to the TLS context alloc.

---

## Linker note

`s_static_decoder_buf[24 * 1024]` (24,576 B) causes BSS overflow by **1016 B** — the linker refuses the
binary. Sized down to exact HWM (23,216 B) to fit; overflow avoided by 344 B. This confirms there is
virtually no BSS margin for a static decoder region of any practical size on this build.

---

## Verdict

**OQ1: decoder must stay runtime-JIT. Static-always placement is not viable.**

| | Baseline (JIT) | OQ1 (static BSS) |
|---|---|---|
| maxBlk at fetch | 57 K | 37 K |
| SSL result | OK | -32512 |
| wrCount | 16 | 0 |

The 23 K BSS array reduces maxAlloc from 57 K to 37 K — below the ~40 K mbedtls needs. The fetch starves
identically to TASK-265. The TASK-267 JIT fix (acquire at `_play()`, after fetch TLS frees) is the only
viable path.

**Manifest treatment (M-MEMPLAN §10):** decoder entry stays `kind: scratch` but the planner should NOT
emit a static region for it. In Phase 2, the manifest entry documents the decoder's known size (23,216 B)
and the headroom it contributes to (already accounted in `headroom.INTERNAL = 60000`). A `placement:
runtime` annotation or note makes this explicit.

---

## Links

TASK-265 (fetch-vs-boot-arena, same failure) · TASK-267 (JIT fix, PASS) · M-MEMPLAN §10 (OQ1 slot)
· EXP-010 (Phase 2 arena fork + playback validation) · `rnd/memplan` branch
