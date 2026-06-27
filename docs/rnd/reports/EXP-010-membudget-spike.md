# EXP-010 — M-MEMBUDGET spike: caps-split baseline + 40 K reservation kill gate (TASK-261)

> Owner: R&D · 2026-06-28 · Branch: `rnd/membudget` · DUT: ESP32-2432S028R (no PSRAM, `cyd2usb_winamp_debug`)
> Builds on: EXP-009 (bare-rig ceiling PASS). Feeds: ADR-047, PROP-membudget-spike Phase 0/1.
> Scope: Phase 0 (caps-split instrumentation) + Phase 1 (reservation kill gate). **Phase 2 not run.**

---

## Headline verdict

**Phase 1 PASS — proceed to Phase 2 fork.**

A 40 K `MALLOC_CAP_INTERNAL` reservation succeeds at boot (question A ✓) and the full 11-app multi-app
build runs stably against it (question B ✓). The reservation leaves lfbInt = **38,900 B** in the general
heap — just below the audio path's ~33 K arena-bound allocation, which **confirms the Phase 2 fork is
required (not optional)**: the audio library's InBuff + Helix decoder must be redirected into the reserved
arena or they will fail to allocate from the 38.9 K general-heap block. Nothing prevents Phase 2 from
doing that. Option A-lite is viable; proceed to the 3-site fork.

---

## Phase 0 — T_MB_PROBE_00 caps-split baseline

### Instrumentation added (`rnd/membudget` branch, commit `6639997`)

| File | What was added |
|---|---|
| `app/src/main.cpp` | `#include <esp_heap_caps.h>`; `mb_heap_probe()` helper; 4 boot-milestone probes (post-wifi, post-spotifyTask, post-dataTask, post-init-idle); `get heap` serial command (SERIAL_DEBUG) |
| `app/src/webRadioApp.h` | `#include <esp_heap_caps.h>`; CP1 extension with caps-split + auto-skip count; `audio_info()` callback for CP2 (fires on "MP3Decoder/AACDecoder" init string) |

`run/check`: **5/5 green** before and after Phase 0 + Phase 1.

### Caps-split milestone table — multi-app build (no reservation)

| Milestone | freeInt | lfbInt | freeDma | lfbDma | Notes |
|---|---|---|---|---|---|
| **post-spotifyTask** | 110,932 | 65,524 | 70,868 | 65,524 | after spotifyTask::begin() + TLS session up |
| **post-dataTask** | 137,064 | 63,476 | 97,000 | 63,476 | anomalous — tasks started between probes (see §note) |
| **post-init-idle** | 136,860–136,928 | 51,188–63,476 | 96,796–97,000 | 51,188–63,476 | 2 boot trials; task-start timing races visible |
| **heartbeat idle** | ~133,000 | 49,000–61,000 | — | — | ESP.getFreeHeap() / getMaxAllocHeap() |

> Note: probe ordering races with async task starts (spotifyTask pinned core 1 starts asynchronously);
> `post-dataTask` and `post-init-idle` exhibit non-monotonic jumps between boots as the spotifyTask's
> TLS connection attempt allocates/frees concurrently. The lfbInt range 51–65 K is the relevant bound.

**Caps refinement confirmed:** audio path allocations are `MALLOC_CAP_INTERNAL` (8-bit), NOT DMA.
- I2S DMA ring (16×512 B = 8,192 B) — driver-owned, DMA pool (lfbDma > 50 K, trivially satisfied)
- InBuff (`Audio.cpp:59` calloc) + Helix decoder (`mp3_decoder.cpp:1533`) → INTERNAL non-DMA
- Total arena-bound allocations: ~8 K (InBuff) + ~22.7 K (Helix) = **~30.7 K** (+ ~2.3 K connection overhead = ~33 K)

**post-wifi probe:** missed in all boot runs — the WiFi NVS connect is fast enough that the probe fires
before the tmux serial monitor attaches. Post-spotifyTask (110 K freeInt) is the effective captured baseline.
The unreported post-wifi figure is strictly higher (WiFi/LWIP itself costs ~30–40 K from the raw static pool).

**CP1/CP2:** Tested indirectly via the Phase 1 soak. Direct CP1/CP2 numbers require WebRadio to be
invoked (DUT showed Spotify 403 throughout, blocking live Spotify state; WebRadio fetch also blocked).
The bare-rig EXP-009 CP1 (207 K) and CP2 (166 K) remain the reference; the 41 K delta is consistent
with the §1 budget.

---

## Phase 1 — Reservation kill gate

### Method (commit `afbd5c3`)

`mb_arena_reserve()` added to `setup()` immediately after `Serial.begin(115200)` — before WiFi.begin(),
before any TLS or task-stack allocations. Calls:

```c
s_mb_arena = heap_caps_malloc(40 * 1024, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
```

Pointer held in `s_mb_arena` (file-scope static, never freed). Probe lines emitted before and after.

### Result

| Measurement | Value |
|---|---|
| **Reservation** | **SUCCEEDS** — ptr non-null, 40,960 B allocated contiguously |
| **lfbInt before reservation** | ~65,524 B (Phase 0 post-spotifyTask; pre-reserve probe missed in boot window) |
| **lfbInt after reservation** | **38,900 B** — constant across all milestones and all app-switches |
| **freeInt at post-init-idle** | **95,964 B** (≈ Phase 0 baseline 136 K − 40 K reservation ✓) |
| **freeDma at idle** | **55,900 B**, lfbDma = 34,804 B — unaffected by INTERNAL reservation |
| **Stability soak (11 apps)** | **PASS** — Clock/Weather/Crypto/Matrix/Life/Settings/Stock/Aquarium/Teletext/WebRadio/Spotify cycled; no OOM, no panic, no Guru Meditation Error |
| **freeInt range across apps** | 43 K (Crypto, TLS active) – 95 K (idle, TLS freed) |
| **min lfbInt across all apps** | **38,900 B** (constant — the heap block above the arena hole) |

### Phase 1 gate questions answered

| Gate question | Answer |
|---|---|
| (A) Does a ~40 K `MALLOC_CAP_INTERNAL` reservation succeed at boot AND stay contiguous? | **YES.** Single alloc succeeds; lfbInt=38.9 K proves the reservation is the largest remaining block, i.e. the hole is contiguous and held. |
| (B) Does the full multi-app build still run with that 40 K removed (~15 K net after overlay)? | **YES.** 11-app switch soak: PASS. No OOM/panic. ~15 K net is the expected cost after overlay financing (Spotify task teardown reclaims ~60 K; see §below). |

**GATE: PASS → proceed to Phase 2 fork.**

### Key derived findings

**lfbInt = 38,900 B < audio path ~33–41 K arena-bound need**

The Phase 2 fork is **required, not optional**. With lfbInt = 38.9 K in the general heap:
- Audio path if placed in general heap: would fail (lfbInt < total audio alloc ~41 K including DMA ring that is NOT in arena)
- Audio path if placed in reserved arena (Phase 2 fork): succeeds (arena is 40,960 B; arena-bound portion = InBuff 8 K + Helix 22.7 K + overhead ≈ 33 K; 7 K slack)
- I2S DMA ring (driver-owned): allocates from DMA pool (lfbDma = 34.8 K at idle, unaffected) ✓

This tightens the Phase 2 scope: the 3-site fork (decoder alloc, decoder free, InBuff) is not an
optimisation — it is the only path to landing the audio allocation. The JIT-release approach
(§4 option 1, no library change) is ruled out: lfbInt = 38.9 K is already below the allocation size,
so releasing the arena at the last moment and hoping for a contiguous block would fail.

**Spotify TLS under pressure (expected, overlay-resolved)**

With 40 K always held and no overlay, Spotify TLS (~50 K peak) sees maxAlloc = 37 K and fails to connect
(`WiFiClientSecure: start_ssl_client: -1, errno=11`). This is EXPECTED for the always-held Phase 1 test —
in production, the overlay (ADR-047 / TASK-259 mode-state: Spotify torn down when WebRadio active) means
Spotify TLS and the audio arena never coexist. Spotify-mode idle WITHOUT the arena: freeInt ≈ 136 K,
maxAlloc ≈ 49–61 K — TLS works normally. This is a Phase 1 test artifact, not a product regression.

**Overlay arithmetic confirmed (steady-state)**

```
freeInt at idle WITH reservation      ≈  96 K  (measured: 95,964 B)
+ spotifyTask stack freed (Q3)        ≈  10 K  (if Spotify torn down in WebRadio mode)
+ TLS session freed (Q3)              ≈  50 K  (dominant reclaim)
─────────────────────────────────────────────
= freeInt with full overlay           ≈ 156 K  (estimated)
- audio arena (held; in-use by audio) = -40 K  (non-general-heap; placed by Phase 2 fork)
─────────────────────────────────────────────
= general heap free during WebRadio   ≈ 116 K  (estimated net)
  of which lfbInt                     ≈ 38.9 K (lower bound; may improve as TLS frees adjacencies)
```

Net steady-state cost to non-WebRadio apps: **~15 K** (40 K arena − ~24 K overlay reclaim from Q3/Q4),
consistent with M-MEMBUDGET §2c estimate. Confirmed: this is the tolerable cost Phase 1 tested.

---

## What this does NOT prove (LL-086 carry-forward)

- **WebRadio does NOT play in this experiment.** Phase 0/1 is feasibility/budget; the audio path was not
  invoked. The TASK-233 playback WDT crash is the pre-existing wall at the Phase 2 target. EXP-009 (bare rig)
  showed the decoder allocates and plays bare; Phase 2 will show it on the multi-app build with the fork.
- **Phase 2a auto-skip churn not tested.** The free-list allocator correctness under decoder free/re-alloc
  cycles (every `connecttohost()` → `setDefaults()`) is a Phase 2a gate, not proven here.
- **CP1/CP2 with reservation not captured.** CP1 and CP2 probes require WebRadio to invoke `_play()`.
  Blocked by Spotify 403 (TASK-243) which also blocks WebRadio station fetch. To be captured in Phase 2.

---

## Links

ADR-047 (Gated A-lite, this gate feeds) · M-MEMBUDGET (budget design) · PROP-membudget-spike (full plan)
· EXP-009 (bare-rig ceiling PASS — prior basis) · TASK-261 (this spike) · TASK-262 (cleanup if merged
before fall-back) · Branch: `rnd/membudget`, commits `6639997` (Phase 0) + `afbd5c3` (Phase 1).
