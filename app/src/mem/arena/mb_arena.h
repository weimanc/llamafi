// mb_arena.h — TASK-261 Phase 2: fixed-slot free-list arena allocator
// Over the Phase 1 MALLOC_CAP_INTERNAL reservation (s_mb_arena, 40 K).
// Called by 2 patched sites, BOTH in mp3_decoder.cpp (PATCH-MEMBUDGET-1/2).
// TASK-445: this line used to say "the 3 patched sites in Audio.cpp +
// mp3_decoder.cpp", which was wrong on the count and the file list and sent
// readers looking for an arena call site in Audio.cpp that does not exist.
// PATCH-MEMBUDGET-3 (InBuff) was REVERTED — InBuff is plain calloc, and its
// 6 400 B coming from the general heap is load-bearing in every memory
// measurement from TASK-425 on. PATCH-MEMBUDGET-4 does live in Audio.cpp but
// is a halved-DMA config change that never touches this allocator.
// See app/lib/ESP32-audioI2S/LOCAL_PATCHES.md for the full patch record.
// All public symbols are no-ops (inline wrappers for standard heap) when
// MEMBUDGET_PHASE1 is not defined. Production (cyd2usb_winamp) DEFINES
// MEMBUDGET_PHASE1 (platformio.ini, TASK-262 promotion 2026-06-29) — the
// arena is live there, not a no-op.

#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef MEMBUDGET_PHASE1

// TASK-267: JIT lifecycle. mb_arena_acquire() reserves a contiguous
// MALLOC_CAP_INTERNAL block of MB_ARENA_BYTES and inits the free-list over it;
// mb_arena_release() frees it. Called from WebRadioApp::_play() (acquire) and
// ::suspend() (release) — NOT at boot, so the station-fetch TLS (~40 K) is not
// starved (TASK-265 / ADR-047 Amendment 1). Acquire is idempotent. On a failed
// acquire the arena stays inactive and mb_arena_alloc falls back to libc malloc
// (best-effort playback, never a crash). Sized to the Helix HWM (23,216 B) + slack.
//
// MEMPLAN_STATIC_DECODER (OQ1 experiment, rnd/memplan branch only):
// arena is a static BSS array present from boot — acquire/release are no-ops.
// Call mb_arena_init_static() in setup() before any fetch to activate.
// Measures whether static-always decoder competes with fetch TLS.
static const size_t MB_ARENA_BYTES = 24 * 1024;
bool   mb_arena_acquire(void);
void   mb_arena_release(void);
#ifdef MEMPLAN_STATIC_DECODER
void   mb_arena_init_static(void);  // called from setup() to wire static BSS block
#endif
bool   mb_arena_active(void);

// Initialise the arena over an already-allocated block (used internally by
// mb_arena_acquire()).
void   mb_arena_init(void* buf, size_t size);

// Alloc / free called by the 3 patched sites.
// Falls back to malloc/free if arena is not initialised (safety net).
void*  mb_arena_alloc(size_t size);
void   mb_arena_free(void* ptr);

// High-water mark (bytes) for monitoring.
size_t mb_arena_hwm(void);
// TASK-444: frees refused because the pointer belonged to an already-released
// arena generation. Non-zero means someone is freeing decoder memory after the
// arena went away — a real defect, and the counter is the observable for it.
uint32_t mb_arena_stale_free_total(void);

// TASK-292: lifetime acquire/release/fail totals, never reset across the
// arena's JIT lifecycle. Serial `[membudget]` lines get dropped at harness
// command boundaries (reset_input_buffer), so leak detection must read these
// device-side totals (`get arenaStats`) instead of counting wire lines.
// Invariant: acquires - releases == (mb_arena_active() ? 1 : 0).
uint32_t mb_arena_acquire_total(void);
uint32_t mb_arena_release_total(void);
uint32_t mb_arena_acquire_fail_total(void);

#else  // !MEMBUDGET_PHASE1 — production: transparent wrappers, zero overhead

static inline bool   mb_arena_acquire(void)    { return false; }
static inline void   mb_arena_release(void)     {}
static inline bool   mb_arena_active(void)      { return false; }
static inline void   mb_arena_init(void*, size_t) {}
static inline void*  mb_arena_alloc(size_t sz) { return malloc(sz); }
static inline void   mb_arena_free(void* p)    { free(p); }
static inline size_t mb_arena_hwm(void)        { return 0; }
static inline uint32_t mb_arena_stale_free_total(void)    { return 0; }
static inline uint32_t mb_arena_acquire_total(void)      { return 0; }
static inline uint32_t mb_arena_release_total(void)      { return 0; }
static inline uint32_t mb_arena_acquire_fail_total(void) { return 0; }

#endif // MEMBUDGET_PHASE1
