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

// Initialise the arena over an already-allocated block.
// Must be called from main.cpp after mb_arena_reserve() succeeds.
void   mb_arena_init(void* buf, size_t size);

// Alloc / free called by the 3 patched sites.
// Falls back to malloc/free if arena is not initialised (safety net).
void*  mb_arena_alloc(size_t size);
void   mb_arena_free(void* ptr);

// High-water mark (bytes) for monitoring.
size_t mb_arena_hwm(void);

#else  // !MEMBUDGET_PHASE1 — production: transparent wrappers, zero overhead

static inline void   mb_arena_init(void*, size_t) {}
static inline void*  mb_arena_alloc(size_t sz) { return malloc(sz); }
static inline void   mb_arena_free(void* p)    { free(p); }
static inline size_t mb_arena_hwm(void)        { return 0; }

#endif // MEMBUDGET_PHASE1
