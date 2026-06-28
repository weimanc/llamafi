// mb_arena.cpp — TASK-261 Phase 2 fixed-slot free-list arena allocator
//
// Backs the 3 patched audio-library sites (mp3 decoder alloc/free, InBuff).
// Builds only under MEMBUDGET_PHASE1; the header provides inline stubs otherwise.
//
// Design: fixed-slot table over a contiguous external buffer.
// - Up to MB_ARENA_MAX_SLOTS slots (10 in practice: 9 Helix + 1 InBuff).
// - alloc(size): search free slots with exact size match first (reuse path, O(n));
//   if not found, bump-allocate a new slot from the tail.
// - free(ptr): mark slot free; safety-check ptr is inside the arena range.
// - No reset-on-all-free needed: InBuff persists across connecttohost(), so
//   there is always at least one live slot after the first _play() call.
// - Pointer-in-range guard: arena_free() calls libc free() for out-of-arena
//   pointers (handles the PSRAM path, if ever active, transparently).

#include "mb_arena.h"

#ifdef MEMBUDGET_PHASE1

#include <Arduino.h>  // log_e

#define MB_ARENA_MAX_SLOTS 16

struct MbSlot {
    uint8_t* ptr;
    size_t   size;
    bool     in_use;
};

static uint8_t*  s_base    = nullptr;
static size_t    s_cap     = 0;
static size_t    s_bump    = 0;   // next free byte offset from s_base
static size_t    s_hwm     = 0;   // high-water mark (max bytes ever used)
static MbSlot    s_slots[MB_ARENA_MAX_SLOTS] = {};
static int       s_nslots  = 0;

void mb_arena_init(void* buf, size_t size) {
    s_base   = (uint8_t*)buf;
    s_cap    = size;
    s_bump   = 0;
    s_hwm    = 0;
    s_nslots = 0;
    memset(s_slots, 0, sizeof(s_slots));
    Serial.printf("[membudget] arena init base=%p cap=%u\n", buf, (unsigned)size);
}

void* mb_arena_alloc(size_t size) {
    if (!s_base) {
        // Arena not initialised — fallback (should never happen in correct usage)
        log_e("[mb_arena] alloc called before init, falling back to malloc");
        return malloc(size);
    }

    // Align to 4 bytes (ESP32 requirement for safe dereference of any type)
    size = (size + 3u) & ~3u;

    // Log first alloc to confirm arena is live (removed after Phase 2 validation)
    if (s_nslots == 0 && s_bump == 0) {
        Serial.printf("[mbdbg] arena FIRST alloc: base=%p cap=%u req=%u\n",
                      s_base, (unsigned)s_cap, (unsigned)size);
    }

    // First-fit: reuse a free slot with the exact size
    for (int i = 0; i < s_nslots; i++) {
        if (!s_slots[i].in_use && s_slots[i].size == size) {
            s_slots[i].in_use = true;
            return s_slots[i].ptr;
        }
    }

    // Bump-allocate a new slot
    if (s_bump + size > s_cap) {
        log_e("[mb_arena] arena exhausted: bump=%u size=%u cap=%u",
              (unsigned)s_bump, (unsigned)size, (unsigned)s_cap);
        return malloc(size);  // fallback — must not happen if sized correctly
    }
    if (s_nslots >= MB_ARENA_MAX_SLOTS) {
        log_e("[mb_arena] slot table full (%d slots)", s_nslots);
        return malloc(size);
    }

    uint8_t* p        = s_base + s_bump;
    s_bump           += size;
    if (s_bump > s_hwm) s_hwm = s_bump;

    s_slots[s_nslots].ptr    = p;
    s_slots[s_nslots].size   = size;
    s_slots[s_nslots].in_use = true;
    s_nslots++;

    return p;
}

void mb_arena_free(void* ptr) {
    if (!ptr) return;

    uint8_t* p = (uint8_t*)ptr;

    // Out-of-arena pointer: libc free (handles PSRAM path / pre-init pointers)
    if (!s_base || p < s_base || p >= s_base + s_cap) {
        free(ptr);
        return;
    }

    // Find the slot and mark free
    for (int i = 0; i < s_nslots; i++) {
        if (s_slots[i].ptr == p) {
            s_slots[i].in_use = false;
            return;
        }
    }

    // In-range pointer but not in slot table — shouldn't happen; log and ignore
    log_e("[mb_arena] free: ptr %p in arena range but not in slot table", ptr);
}

size_t mb_arena_hwm(void) { return s_hwm; }

#endif // MEMBUDGET_PHASE1
