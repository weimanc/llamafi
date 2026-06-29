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
#include "esp_heap_caps.h"  // TASK-267: heap_caps_malloc/free + largest-free-block

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
#ifdef SERIAL_DEBUG
    Serial.printf("[membudget] arena init base=%p cap=%u\n", buf, (unsigned)size);
#endif
}

// TASK-267 / ADR-047 Amendment 1: the arena block is owned here and acquired at
// _play() (not boot), so the station-fetch TLS is not starved. heap_caps_free on
// release. The Helix decoder is freed (via mb_arena_free) before release happens
// (WebRadioApp::suspend() deletes the Audio object first), so no dangling slots.
static void* s_owned = nullptr;

#ifdef MEMPLAN_STATIC_DECODER
// OQ1 experiment (rnd/memplan branch): 24 K static BSS region, always present.
// This makes the region equivalent to a linker-placed static array — it subtracts
// from the heap pool at boot and competes with fetch TLS during station fetch.
// mb_arena_init_static() wires it; acquire/release are no-ops.
// Sized to exact Helix HWM (23,216 B) — smaller than MB_ARENA_BYTES (24 K) to fit linker DRAM.
static uint8_t s_static_decoder_buf[23216] __attribute__((aligned(4)));

void mb_arena_init_static(void) {
    Serial.printf("[membudget] OQ1 static decoder init: buf=%p size=%u lfbInt=%u freeInt=%u\n",
        (void*)s_static_decoder_buf, (unsigned)sizeof(s_static_decoder_buf),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    mb_arena_init(s_static_decoder_buf, sizeof(s_static_decoder_buf));
    s_owned = s_static_decoder_buf;  // mark as active so active() returns true
}

bool mb_arena_acquire(void) {
    // static path: arena already init'd at boot; no heap alloc; no-op here
    Serial.printf("[membudget] OQ1 static acquire (no-op) lfbInt=%u\n",
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));
    return s_owned != nullptr;
}

void mb_arena_release(void) {
    // static path: cannot free BSS; only reset slot table so decoder re-allocates clean
    s_bump = 0; s_hwm = 0; s_nslots = 0;
    memset(s_slots, 0, sizeof(s_slots));
    Serial.println("[membudget] OQ1 static arena reset (BSS block retained)");
}

#else  // normal JIT path

bool mb_arena_acquire(void) {
    if (s_owned) return true;  // idempotent — already held this session
    size_t lfb = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
    s_owned = heap_caps_malloc(MB_ARENA_BYTES, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
#ifdef SERIAL_DEBUG
    Serial.printf("[membudget] TASK-267 arena acquire=%uB lfbBefore=%u %s\n",
        (unsigned)MB_ARENA_BYTES, (unsigned)lfb, s_owned ? "OK" : "FAIL→libc-fallback");
#else
    (void)lfb;
#endif
    if (!s_owned) return false;  // mb_arena_alloc falls back to libc (best-effort)
    mb_arena_init(s_owned, MB_ARENA_BYTES);
    return true;
}

void mb_arena_release(void) {
    if (!s_owned) return;
    heap_caps_free(s_owned);
    s_owned = nullptr;
    s_base = nullptr; s_cap = 0; s_bump = 0; s_hwm = 0; s_nslots = 0;
    memset(s_slots, 0, sizeof(s_slots));
#ifdef SERIAL_DEBUG
    Serial.println("[membudget] TASK-267 arena released");
#endif
}

#endif  // MEMPLAN_STATIC_DECODER

bool mb_arena_active(void) { return s_base != nullptr; }

void* mb_arena_alloc(size_t size) {
    if (!s_base) {
        // Arena not initialised — fallback (should never happen in correct usage)
        log_e("[mb_arena] alloc called before init, falling back to malloc");
        return malloc(size);
    }

    // Align to 4 bytes (ESP32 requirement for safe dereference of any type)
    size = (size + 3u) & ~3u;

#ifdef SERIAL_DEBUG
    // Log first alloc to confirm arena is live (debug-only diagnostic)
    if (s_nslots == 0 && s_bump == 0) {
        Serial.printf("[mbdbg] arena FIRST alloc: base=%p cap=%u req=%u\n",
                      s_base, (unsigned)s_cap, (unsigned)size);
    }
#endif

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
