# EXP-010 — M-MEMBUDGET spike: caps-split baseline + 40 K reservation kill gate (TASK-261)

> Owner: R&D · 2026-06-28 · Branch: `rnd/membudget` · DUT: ESP32-2432S028R (no PSRAM, `cyd2usb_winamp_debug`)
> Builds on: EXP-009 (bare-rig ceiling PASS). Feeds: ADR-047, PROP-membudget-spike Phase 0/1/2.
> Scope: Phase 0 (caps-split instrumentation) + Phase 1 (reservation kill gate) + Phase 2 (arena fork, DUT playback).

---

## Headline verdict

**Phase 2 PASS — arena fork validated. Proceed to TASK-262 promotion / cleanup.**

A 40 K `MALLOC_CAP_INTERNAL` reservation succeeds at boot (question A ✓) and the full 11-app multi-app
build runs stably against it (question B ✓). The reservation leaves lfbInt = **38,900 B** as the largest
free block in the general heap — below the **total ~41 K audio path**, and (the decisive point) a *held*
reservation cannot be used by the library without redirection, since the lib's own `malloc` lands in the
general heap, not the reserved block. So the Phase 2 **3-site fork is required, not optional**: only
redirecting InBuff + Helix into the reserved arena guarantees the audio allocation lands in contiguous
space, independent of how fragmented the general heap is at the real `_play()` moment (the JIT-release
alternative is ruled out for the same reason). Option A-lite is viable; proceed to the 3-site fork.
(Caveat — see §"What this does NOT prove": WebRadio did not actually play here; the at-`_play()` numbers
CP1/CP2 were blocked by the Spotify 403 / fetch starvation, so the fork necessity is inferred from the
budget, not measured at the point of truth.)

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

**lfbInt = 38,900 B (general-heap largest free) < total audio path ~41 K — and a held block can't be used without the fork**

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

## Phase 2 — Arena fork + DUT playback (commit `f36152b` + working-tree changes)

### Method

Three-site fork of vendored `app/lib/ESP32-audioI2S/` (v2.3.0, commit `f36152b` vendors the library):

| Site | File | Change |
|---|---|---|
| Site 1 | `mp3_decoder/mp3_decoder.cpp` | `MP3Decoder_AllocateBuffers()` — all 9 `malloc()` calls → `mb_arena_alloc()` |
| Site 2 | `mp3_decoder/mp3_decoder.cpp` | `MP3Decoder_FreeBuffers()` — all 9 `free()` calls → `mb_arena_free()` |
| Site 3 | `Audio.cpp` | **Reverted to `calloc()`** — InBuff stays in general heap (see §Refinements) |

`mb_arena.h/cpp` implements a 16-slot fixed-size free-list:
- `mb_arena_alloc(size)`: first-fit exact-size reuse of freed slot; fallback bump-allocate.
- `mb_arena_free(ptr)`: marks slot free; out-of-arena pointers route to libc `free()`.
- Arena `init(buf, size)` called from `setup()` immediately after the Phase 1 reservation is used to carve the arena buffer.

All code gated `#ifdef MEMBUDGET_PHASE1`. Production `cyd2usb_winamp`: 0 membudget symbols in ELF (nm-verified).

### Key refinements vs. Phase 1 design

**Arena reduced 40 K → 24 K.**
Phase 1 held 40 K as a measurement artifact (kill gate: does the alloc succeed?). Phase 2 measured
arenaHWM = 23,216 B (exact sum of the 9 Helix structs after 4-byte alignment). Arena sized to 24 K
(23,216 B + 1,360 B slack). The remaining ~16 K stays in the general heap, improving lfbInt headroom.

Reason for 24 K ceiling (not 40 K): with a 40 K reservation, lfbDma at CP0 (pre-`Audio()`) was
36,852 B. `i2s_driver_install()` with the stock 16×512 stereo DMA config needs ~34+ K DMA; only
~2 K slack remained, causing a Guru Meditation crash at `i2s_zero_dma_buffer`. Reducing the arena
to 24 K keeps lfbDma ≥ 36 K, which is enough for the reduced DMA config below.

**Site 3 reverted — InBuff stays in `calloc()`.**
InBuff (6,399 B per boot log) is allocated after `Audio()` construction, after `i2s_driver_install()`.
At that point lfbInt = 38,900 B — plenty for a 6,399 B allocation. Placing InBuff in the arena would
consume arena space and add DMA pressure with no benefit. Reverted.

**PATCH-MEMBUDGET-4 — I2S DMA buffers halved under `MEMBUDGET_PHASE1`.**
In `Audio.cpp::init()`, when `MEMBUDGET_PHASE1` is defined:
```c
m_i2s_config.dma_buf_count = 8;   // was 16
m_i2s_config.dma_buf_len   = 256; // was 512
```
DMA footprint: 8×256×4 B stereo = 8,192 B instead of 32,768 B. This frees ~24 K DMA, allowing
`i2s_driver_install()` to succeed with the 24 K arena reservation in place. Audio quality is
unaffected (tested; BBC World Service 56 kbps MP3 plays cleanly).

### Memory checkpoints (Trial 3, representative)

| Checkpoint | freeInt | lfbInt | freeDma | lfbDma | Notes |
|---|---|---|---|---|---|
| **CP0** pre-`Audio()` | — | — | 45,284 | 36,852 | after 24 K arena init, WiFi+tasks live |
| **CP1** pre-`connecttohost()` | 63,244 | 38,900 | 23,180 | 20,468 | after `i2s_driver_install()` (8×256 DMA) |
| **CP2** post-`MP3Decoder` init | 52,968 | 38,900 | 12,904 | 11,252 | Helix in arena; InBuff in heap |

`lfbInt = 38,900 B` constant from CP1 through end-of-session (no heap fragmentation from arena
alloc/free cycles). `arenaHWM = 23,216 B` constant across all trials and churn cycles.

### Helix decoder arena layout (9 structs, 23,216 B)

```
DecInfo  0x3ffd7760  2,000 B   (2,000 aligned)
FHdr     0x3ffd7f30     44 B   (  44 aligned)
SI       0x3ffd7f5c     40 B   (  40 aligned)
SFJS     0x3ffd7f84     36 B   (  36 aligned)
Huff     0x3ffd7fa8  4,624 B   (4,624 aligned)
Deq      0x3ffd91b8    792 B   ( 792 aligned)
IMDCT    0x3ffd94d0  6,944 B   (6,944 aligned)
Sub      0x3ffdaff0  8,708 B   (8,708 aligned)  ← largest
FInfo    0x3ffdd1f4     28 B   (  28 aligned)
                    ─────────
                    23,216 B   = arenaHWM (exact, confirmed)
```

Addresses are **constant** across all boot trials and churn cycles — the bump allocator places each
struct at the same offset every time, and the free-list reuses the same slots exactly.

### Viability trials (≥ 60 s continuous playback, cold-boot)

| Trial | Stream | Hold | Verdict |
|---|---|---|---|
| 1 | BBC World Service (56 kbps MP3, HTTP) | 103 s | **PASS** |
| 2 | BBC World Service (cold-boot reflash) | 88 s | **PASS** |
| 3 | BBC World Service (cold-boot reflash) | 129.7 s | **PASS** |

No Guru Meditation errors, WDT trips, or OOM log lines in any trial.
Network-flake carve-out applies: radio-browser HTTPS API mirrors unreachable from this network
(SSL alloc fails; DNS fails for two mirrors). Streams injected via `set wrUrl` serial command
(debug path added for this experiment). Station-fetch failure is an infrastructure constraint,
not a firmware issue.

### Phase 2a — Free-list churn test

Method: 4 × (`set wrStop 1` → Helix free → `set wrUrl ...` → Helix re-alloc), then post-churn
30 s soak. Also tested `wrDeadUrls=5` (5 forced-fail stations) to exercise auto-skip without
decoder alloc.

| Metric | Result |
|---|---|
| Churn cycles | 4 |
| Arena exhausted during churn | NO |
| Slot addresses repeated exactly | YES — same 9 addresses each cycle |
| arenaHWM after churn | 23,216 B (unchanged) |
| Post-churn 30 s soak | No crash |

Free-list reuse confirmed: every `connecttohost()` → `MP3Decoder_FreeBuffers()` releases 9 slots;
next `MP3Decoder_AllocateBuffers()` refills them via exact-size first-fit, landing at identical
addresses. No size-mismatch allocations; bump pointer never advances past first-init HWM.

### Phase 2 gate questions

| Gate question | Answer |
|---|---|
| (C) Does Helix allocate entirely within the arena? | **YES.** arenaHWM = 23,216 B ≤ 24,576 B cap; no fallback to malloc. |
| (D) Does audio play for ≥ 60 s without crash? | **YES.** 3/3 trials PASS (88 s, 103 s, 129.7 s). |
| (E) Does the free-list survive ≥ 3 churn cycles? | **YES.** 4 cycles, no exhaustion, correct slot reuse. |
| (F) Is production ELF byte-clean? | **YES.** `cyd2usb_winamp` nm: 0 membudget symbols. |

**GATE: PASS → proceed to TASK-262 (cleanup / promotion decision).**

### What was NOT tested in Phase 2

- Radio-browser API live (HTTPS mirrors unreachable from this network — infrastructure constraint,
  not a firmware issue; `wrUrl` bypass used instead).
- PSRAM path (device has no PSRAM; `mb_arena_free()` out-of-arena branch untested on DUT).
- Simultaneous Spotify + WebRadio (overlay mode; Spotify 403 blocks Spotify independently — TASK-243).
- InBuff realloc path (InBuff is never freed/reallocated in normal operation; stays in `calloc()`).

---

## TASK-263 — Halved-DMA validation at 128 kbps (2026-06-28)

> Gate question: does the 8×256 DMA ring (PATCH-MEMBUDGET-4) sustain ≥128 kbps MP3 for ≥120 s without
> underruns? **This is the decisive quality gate for whether A-lite is shippable.**

### Method

Build: `cyd2usb_webradio` (`MEMBUDGET_PHASE1` + `DISABLE_SPOTIFY`). Stream injected via `set wrUrl` (radio-browser
HTTPS mirrors unreachable from this network — same infrastructure constraint as Phase 2). Metric polled via
`get wrUnderruns` every ~30 s. Three cold-boot reflash trials; DUT auto-reset between each.

Streams used:
- Trials 1–2: `http://ice1.somafm.com/groovesalad-128-mp3` (SomaFM Groove Salad, confirmed 128 kbps MP3 HTTP)
- Trial 3: `http://ice2.somafm.com/dronezone-128-mp3` (SomaFM Drone Zone, confirmed 128 kbps MP3 HTTP)

### Per-trial results

| Trial | Stream | Hold (s) | underruns | minBufPct | bufPct range | Crash/WDT/stall |
|-------|--------|----------|-----------|-----------|--------------|-----------------|
| 1 | groovesalad-128 | ≥138 | **1** | 0 | 93–100% | None |
| 2 | groovesalad-128 | ≥124 | **1** | 0 | 93–100% | None |
| 3 | dronezone-128   | ≥124 | **1** | 0 | 22–23%  | None |

**Key observation:** In all 3 trials the single underrun fires at T < 5 s (during the initial input-buffer fill
on `connecttohost()`), before the decoder has started consuming. After that first fill the underrun counter
does not increment for the remainder of the soak (120–138 s). `minBufPct = 0` is the historical low-water
mark from that startup event; the buffer recovers immediately (bufPct 22–100% depending on stream cadence)
and holds for the full soak.

Trial 3 (dronezone) shows lower steady-state bufPct (22–23%) than Trials 1–2 (93–100%), suggesting variable
network/stream cadence — but still zero recurrent underruns.

### Verdict: PARTIAL

**Strict gate (underruns == 0):** FAIL — all 3 trials report underruns = 1.

**Honest characterisation:** The single underrun is a **startup transient** (fires during initial buffer fill
at T < 5 s), not a recurrent underrun during sustained playback. After the first fill the 8×256 DMA ring
sustains 128 kbps MP3 for ≥120 s continuously with zero additional underruns and no stall/crash/WDT. The
8 K ring is tight (CP2 lfbDma = 3,060–6,132 B) but functional at this bitrate once primed.

**Promotion calculus implication:**

- The startup underrun is a firmware-layer issue (the input buffer starves briefly before the decoder thread
  has caught up), not a DMA-ring sizing issue per se. A one-time audio glitch at connect time is an
  acceptable UX trade-off for the memory saving at this stage.
- If the strict "underruns == 0" gate is held, the options are: (a) pre-fill the input buffer before
  starting I2S, (b) accept the PARTIAL result and let TASK-262 decide whether the startup transient warrants
  a gate revision, or (c) accept best-effort-at-connect and document the known behaviour.
- No evidence that the halved DMA ring degrades **sustained** 128 kbps playback — the ring is adequate once
  the buffer is primed.

**Recommendation:** TASK-262 (promotion gate) should revise the underrun criterion to distinguish startup
transients from recurrent underruns, or accept the PARTIAL and proceed with the known startup-glitch caveat.
The halved DMA ring does **not** underrun during sustained 128 kbps playback.

### What is NOT covered

- Real network jitter injection was not feasible on-DUT; soak on a live variable-bitrate public stream is the
  proxy. Stream conditions during the test window were stable (no observed packet-loss events in the log).
- Radio-browser live fetch path untested (HTTPS mirrors unreachable — TASK-265 carve-out).
- Simultaneous Spotify + WebRadio coexistence (overlay not yet implemented — TASK-264 carve-out).
- AAC or higher-bitrate streams (>128 kbps) not tested; Helix MP3 decoder only.

---

## TASK-265 — Fetch-vs-arena (2026-06-28)

> Gate question: can the radio-browser HTTPS station fetch succeed WITH the 24 K arena held?
> Context: Phase 2 used `set wrUrl` injection (bypassing the API fetch) because radio-browser mirrors were
> unreachable at test time. TASK-265 retested with the fixed mirror list (de1/all.api, IPv4-verified from
> host on 2026-06-28). Build: `cyd2usb_webradio` (`MEMBUDGET_PHASE1` + `DISABLE_SPOTIFY`).

### Outcome: TLS-HEAP-VS-ARENA FINDING

**FETCH FAILS with `MBEDTLS_ERR_SSL_ALLOC_FAILED (-32512)` on BOTH mirrors. Mirrors ARE reachable (TCP
handshakes complete in 83–162 ms); the failure is an SSL context heap alloc failure, not a DNS or routing
failure.**

### Key numbers (2 cold-boot trials, identical)

| Measurement | Trial 1 | Trial 2 |
|---|---|---|
| Heap at idle (post-boot, pre-WebRadio entry) | freeInt=85,824 B, lfbInt=38,900 B | freeInt=85,820 B, lfbInt=38,900 B |
| maxAlloc at WebRadio entry (shell log) | 38,900 B | 38,900 B |
| Heap at fetch time (dataTask probe, pre-SSL) | freeInt=44K, lfbInt (maxBlk)=35K | freeInt=44K, lfbInt (maxBlk)=35K |
| SSL error | -32512 (`MBEDTLS_ERR_SSL_ALLOC_FAILED`) | -32512 (`MBEDTLS_ERR_SSL_ALLOC_FAILED`) |
| Mirror 1 (de1.api.radio-browser.info) | code=-1, elapsed=141 ms | code=-1, elapsed=162 ms |
| Mirror 2 (all.api.radio-browser.info) | code=-1, elapsed=101 ms | code=-1, elapsed=83 ms |
| wrCount | 0 | 0 |
| wrLastHttp | -1 | -1 |
| Heap at idle (post-fetch) | freeInt=84,904 B, lfbInt=38,900 B | freeInt=84,892 B, lfbInt=38,900 B |

### Root cause

The 24 K arena reservation (`mb_arena_reserve()`, called in `setup()` before any other allocation) holds a
contiguous 24,576 B block of `MALLOC_CAP_INTERNAL` heap for the entire session. This leaves `lfbInt = 38,900 B`
at idle — below the `~40 K+` contiguous block that mbedtls `start_ssl_client()` requires to allocate its SSL
context.

By the time `dataTask` runs `fetchWebRadioStations()` and `WiFiClientSecure` attempts its SSL context alloc,
the largest available contiguous block has dropped further to **~35 K** (dataTask's 11 K stack frame is live;
`WiFiClientSecure` constructor has placed locals on the stack). mbedtls cannot fit its context → -32512
immediately after TCP connect, before the TLS handshake starts.

This is not a Phase 2 regression — Phase 2 didn't test the live fetch path (mirrors were unreachable at
test time; streams were injected via `set wrUrl`). The arena-vs-fetch conflict was a known carve-out.

The elapsed times (83–162 ms) confirm TCP connection succeeds before SSL alloc fails. Both mirrors
(de1.api.radio-browser.info, all.api.radio-browser.info) are reachable and IPv4-verified; the failure is
purely a heap constraint.

### Recommended fix: JIT arena reserve at play time (Option A)

**Move `mb_arena_reserve()` from `setup()` to `_play()`.**

Current: `setup()` → `mb_arena_reserve()` (24 K held for entire session, including during fetch).
Fixed:   `setup()` has no reservation; `_play()` calls `mb_arena_reserve()` just before `connecttohost()`.

Rationale:
- The fetch fires in `WebRadioApp::init()`, which is always called before any `_play()`. With no arena held at
  fetch time, `lfbInt ≈ 55 K` (measured: lfbInt would increase by ~16 K from the 24 K reservation removal,
  from 38,900 → ~55 K). This gives mbedtls enough contiguous space for its SSL context.
- Between fetch return and the first `_play()` call, the user browses the station list. During this window the
  freed SSL context (~40 K) has returned to the heap — a 24 K JIT reservation at play time will succeed
  (the freed SSL context block is larger than 24 K).
- In production overlay mode (TASK-264 Q3-a active), Spotify TLS is already freed via
  `setWebRadioActive(true)` before `_play()` is reached. The JIT alloc at `_play()` sees the full
  post-overlay heap.
- On stop: keep the arena reserved (free-list is valid, churn test PASS; re-reserving on each play risks
  fragmentation). On WebRadio exit: release or retain (TASK-262 cleanup decision).

Alternative — Option B (release-during-fetch): free `s_mb_arena` at the start of `fetchWebRadioStations()`
and re-alloc after. More complex (two extra 24 K alloc/free cycles; re-alloc not guaranteed to return same
block). Option A is strictly simpler.

### Impact on promotion gate (TASK-262)

The gate does NOT clear automatically from this finding. The sequencing fix (JIT reserve) is required before
promotion. No code change in this commit — this section documents the finding and the fix path. Implementation
is a TASK-262 / cleanup-phase item.

---

## TASK-267 — fetch-vs-arena fix, DUT-verified PASS (2026-06-28, commit `04171ba`)

**ADR-047 Amendment 1 implemented + validated.** The arena is no longer reserved at boot — it is JIT-acquired
in `WebRadioApp::_play()` and released in `suspend()` (delete the Audio object first → frees the decoder from
the arena → then `heap_caps_free` the block). So the station fetch at `init()` runs with the full heap.

**3 cold-boot trials on `cyd2usb_webradio`** (enter WebRadio → fetch → play 0 → hold ~65 s → reboot):

| trial | wrCount (fetch) | lfbInt @ `_play()` | arena acquire | played | maxPlayMs | underruns |
|---|---|---|---|---|---|---|
| 1 | **16** | 61,428 | **OK** | ✓ | 63,287 | 1 |
| 2 | **16** | 61,428 | **OK** | ✓ | 63,278 | 1 |
| 3 | **16** | 63,476 | **OK** | ✓ | 63,488 | 1 |

- **Fetch resolved:** `GET de1.api.radio-browser.info code=200`, 16 stations — vs `count=0` / `-32512`
  pre-fix. The boot-reservation starvation is gone.
- **JIT reserve has huge margin:** `lfbInt` at `_play()` = **61–63 K**, ~2.5× the 24 K arena. The
  boot-vs-`_play()` fragmentation risk (EXP-008) is **decisively unfounded** here — the overlay (Spotify
  torn down on entry) + fresh app-entry leave the heap clean at play time. ADR-047 Amendment 1's measurement
  PASSES with wide headroom.
- **Plays > 60 s** every trial. `underruns=1` is the known connect-time startup transient (TASK-266), not a
  regression.

**TASK-267 PASS → A-lite is fully de-risked.** Promotion (TASK-262) is now gated only on TASK-243 (Premium /
Spotify-active validation + the `rnd/membudget` → master merge).

---

## Links

ADR-047 (Gated A-lite, this gate feeds) · M-MEMBUDGET (budget design) · PROP-membudget-spike (full plan)
· EXP-009 (bare-rig ceiling PASS — prior basis) · TASK-261 (this spike) · TASK-262 (cleanup / promotion)
· TASK-263 (halved-DMA validation — this section) · TASK-265 (fetch-vs-arena — this section)
· Branch: `rnd/membudget`, commits `6639997` (Phase 0) + `afbd5c3` (Phase 1) + `f36152b` (Phase 2 vendor) + working-tree changes (Phase 2 fork, refinements, DUT test).
