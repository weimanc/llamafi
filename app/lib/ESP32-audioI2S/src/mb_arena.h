// mb_arena.h — TASK-261 Phase 2: fixed-slot free-list arena allocator
// Over the Phase 1 MALLOC_CAP_INTERNAL reservation (s_mb_arena, 40 K).
// Called by the 3 patched sites in Audio.cpp + mp3_decoder.cpp.
// All public symbols are no-ops (inline wrappers for standard heap) when
// MEMBUDGET_PHASE1 is not defined — production (cyd2usb_winamp) is byte-clean.

#pragma once
#include <stddef.h>
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
static const size_t MB_ARENA_BYTES = 24 * 1024;
bool   mb_arena_acquire(void);
void   mb_arena_release(void);
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

#else  // !MEMBUDGET_PHASE1 — production: transparent wrappers, zero overhead

static inline bool   mb_arena_acquire(void)    { return false; }
static inline void   mb_arena_release(void)     {}
static inline bool   mb_arena_active(void)      { return false; }
static inline void   mb_arena_init(void*, size_t) {}
static inline void*  mb_arena_alloc(size_t sz) { return malloc(sz); }
static inline void   mb_arena_free(void* p)    { free(p); }
static inline size_t mb_arena_hwm(void)        { return 0; }

#endif // MEMBUDGET_PHASE1
