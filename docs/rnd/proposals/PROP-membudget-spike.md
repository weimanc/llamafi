# PROP — M-MEMBUDGET measurement spike: can a reserved internal arena make WebRadio deterministic on the multi-app build?

> Owner: R&D / Architect · 2026-06-27 · Status: **proposed — for PM to schedule / panel to review**
> Feeds: M-MEMBUDGET (design sketch §6), ADR-045, candidate ADR-047. Couples: TASK-259 (player mode-state).
> Builds on EXP-009 (bare-rig ceiling PASS). **This runs IN-PROJECT on the multi-app build — not the bare rig.**

## The question

EXP-009 proved the hardware plays MP3 radio bare. The open question is the one EXP-009 explicitly did **not**
answer (R2/LL-086): **does WebRadio fit on *our* multi-app build** if we (a) reserve a contiguous internal
arena at boot and (b) fork the audio library to place its two big buffers in it. This spike answers it with
numbers, cheaply-first, with a hard kill gate before the expensive fork.

## Caps refinement (drives the whole feasibility) — confirmed in code

The arena needs **`MALLOC_CAP_INTERNAL` (8-bit), NOT DMA-capable**:
- The I2S DMA ring is allocated by **`i2s_driver_install()`** (`Audio.cpp:209`), `dma_buf_count=16 ×
  dma_buf_len=512` → sixteen **512-byte** DMA chunks. DMA *contiguity* demand is 512 B, trivially met even
  fragmented; the driver owns it, not our arena.
- The two big allocations we reserve for — **InBuff** (`Audio.cpp:59` `calloc`) and the **Helix decoder**
  (`mp3_decoder.cpp:1533` `__malloc_heap_psram` → `INTERNAL` on no-PSRAM) — are **plain internal RAM**.

So we reserve ~**32–40 K of the *large* internal pool**, not the scarce DMA pool. This is the single biggest
de-risk vs the design sketch's original "DMA-internal" framing — and Phase 0 verifies it before we lean on it.

## Where it runs / hygiene

- **In-project, on a branch** (`rnd/membudget` or `feature/membudget`), DUT-driven. NOT the bare rig.
- Standard serial-dbg harness (`get stacks` / `get heap`), extended with a **caps split** (INTERNAL vs DMA:
  free + largest-free-block each) so every probe distinguishes the two pools.
- **Restore production firmware to the DUT** at the end (the DUT currently carries prod; the bare rig is
  separate). Per BP-040: this PROP names its cleanup/abort disposition (see Phase gates + Task topology).
- BP-041: any new `[env:...]` or `-D` flag kept past the spike is gated in `run/check` or removed.

## Phased plan with kill-gates (cheap measurement before M-effort)

### Phase 0 — Baseline measurement + the gating instrumentation (cheap; no kill)

Goal: fill the design sketch's `(e)` rows and confirm the caps refinement, on the unmodified multi-app build.
**Gating note (VE B1):** the existing harness exposes only single-pool `ESP.getFreeHeap`/`getMaxAllocHeap` —
there is **no caps-split probe today**. The caps-split probe is **net-new instrumentation and is a hard
prerequisite for Phase 1** (Phase 1's "contiguous" gate is not measurable without `largest_free_block(INTERNAL)`).
So Phase 0's first deliverable is that probe, verified before any later phase (test `T_MB_PROBE_00`).
- Add a `get heap` handler emitting caps-split `freeInt / lfbInt / freeDma / lfbDma`, and emit them at boot
  milestones: **post-WiFi**, **post-`spotifyTask` create**, **post-`dataTask` create**, **steady idle**, **CP1**
  (`webRadioApp.h:621` `_play()` entry — already instrumented), a new **CP2** at decoder-init (`audio_info`
  hook), and **at `connecttohost` re-entry after ≥3 auto-skips** (Developer suggestion 3 — the fragmentation
  that bites the allocator shows up *after* skips, not at first `_play()`).
- Capture at each: `free(INTERNAL)`, `largest_free_block(INTERNAL)`, `free(DMA)`, `largest_free_block(DMA)`.
- **Deliverables:** (1) the real resident short-list (WiFi/TLS cost, per-task deltas) → fills M-MEMBUDGET §1/§5;
  (2) **confirms the audio path's big allocations are INTERNAL** (caps refinement); (3) the actual
  `largest_free_block(INTERNAL)` at CP1 — i.e. how badly fragmented we are at the moment of truth.

### Phase 1 — Reservation feasibility (KILL GATE; still cheap: ~1 boot alloc + a soak)

Goal: can we even reserve the arena, and does the system survive losing it.
- At boot (before app objects fragment the heap), `heap_caps_malloc(ARENA_BYTES, MALLOC_CAP_INTERNAL |
  MALLOC_CAP_8BIT)`, hold forever. `ARENA_BYTES` from Phase 0 (≈ InBuff + decoder peak + slack; start ~40 K).
- Measure: reservation **succeeds + is contiguous**; the **full app set still boots and runs** (switch through
  all ~10 apps, soak, no OOM); the driver's 512-B DMA chunks still alloc at a (stubbed) play.
- **GATE:**
  - reservation succeeds **AND** system runs with it gone → **proceed to Phase 2.**
  - reservation fails (internal pool too fragmented even at boot) **OR** the app set won't run 40 K short →
    **STOP. Option A-lite is dead.** Record against ADR-045 (stands), M-MEMBUDGET verdict = "reservation
    infeasible," product decision defaults to **Option B**. No fork effort spent. (Cheap terminal kill.)

### Phase 2 — The 3-site library fork (M-effort; only if Phase 1 passes)

Goal: deterministic placement + the real viability number on the multi-app build.
- Vendor ESP32-audioI2S into `lib/` (BP-042 already freezes us on v2.3.0 → low maintenance cost). Patch
  **THREE** sites (panel-corrected), PATCH-marked, to draw from a **fixed-slot free-list allocator** (NOT a
  bump arena — see below) over the Phase-1 reservation:
  - decoder *alloc* macro `__malloc_heap_psram` (`mp3_decoder.cpp:1533`) — covers all 9 Helix buffers;
  - decoder *free* `MP3Decoder_FreeBuffers()` (`mp3_decoder.cpp:1578+`) — MUST be intercepted too (else arena
    pointers reach libc `free()` → heap corruption);
  - InBuff `calloc`/free (`Audio.cpp:59`).
  **Why free-list not bump:** the decoder is freed + re-allocated inside `setDefaults()` on every
  `connecttohost()` (`Audio.cpp:436`) — i.e. every auto-skip (default ON). `stopSong()` does not free, so
  there is no bump-reset anchor; a bump allocator walks off the end after a few skips. The 9 decoder buffers
  are fixed-size/identical each session → a trivial fixed-slot pool handles the churn.
- Instrument arena high-water; confirm decoder + InBuff **land in the arena** (general-heap CP2 no longer
  drops by ~31 K).
- **Phase 2a — auto-skip churn test (the actual failure mode; Developer suggestion 2):** before the hold run,
  force ≥ 3–4 auto-skips via the existing `wrDeadUrls` debug hook (`webRadioApp.h:551`) and confirm the
  free-list allocator survives the decoder free/re-alloc cycling (arena does not exhaust). The plain hold run
  would PASS on a clean first station and never exercise this — it must be tested explicitly.
- **Viability run:** WebRadio reaches PLAYING and **holds ≥ 60 s on the multi-app build**, ≥ 3 cold-boot
  trials × the fixed SomaFM HTTP station set. **Network-flake carve-out (VE N2):** an entry is excluded from
  the hold denominator if no decoder-init line (`audio_info` "MP3Decoder ... initialized") appears within
  **N = WR_STREAM_DEAD_MS (≈ 5 s)** of `connecttohost` — that log token is the objective "decode started"
  signal; pin both so the denominator is reproducible.
- **GATE:** holds ≥ 60 s on ≥ 90 % of cold-boot entries → **PASS** → evidence base for **ADR-047** ("reserved
  internal arena + 3-site fork makes WebRadio deterministic on the multi-app no-PSRAM board"). Partial (plays
  but underruns) → recordable partial per the EXP-008 two-threshold split, not a clean pass.

### Phase 3 — Overlay financing (CONDITIONAL; only if Phase-1 always-held 40 K is too tight — OQ3)

Goal: recover the 40 K for the other apps when WebRadio is *not* active, via the mode-overlay.
- Couple with **TASK-259** (player mode-state) + **Q3** (`spotifyTask` teardown on toggle-to-WebRadio): the
  arena RAM is borrowed back from what Spotify mode would have used.
- Measure **Spotify reconnect/re-auth latency** on toggle-in (token refresh + TLS handshake); confirm
  acceptable behind ADR-046's "connecting" bar.
- Needs TASK-255's null-safety audit of unconditional `spotifyTask::` accessors as a prereq.

## Metrics & instrumentation (shared)

`get heap` extended: `freeInt / lfbInt / freeDma / lfbDma` (caps split). CP1 + new CP2 emits. Arena high-water
counter. All reuse the existing serial-dbg framework + a standalone pyserial driver (not the `Dut` class —
its `.elf` hash check would mismatch a branch build; VE N1 carry-over).

## Risks / threats

- **(R1) Reservation infeasible** — internal pool fragmented even at boot. Phase 1 tests directly; cheap to
  find out. (The caps refinement makes this *less* likely — internal pool ≫ DMA pool.)
- **(R2) Bare ≠ multi-app (LL-086)** — the entire reason Phase 2 runs on the multi-app build, not bare. The
  PASS number is the in-project one, stated with the fragmentation-tax caveat.
- **(R3) Bump allocator can't free out-of-order** — a mid-session codec switch (MP3→AAC) would break it.
  Mitigated by the MP3-only station filter; TLSF free-list is the named fallback.
- **(R4) Spotify reconnect latency** (Phase 3) unacceptable → mode-overlay financing is off the table; fall
  back to always-held 40 K (only viable if Phase 1 showed it fits).
- **(R5) Hygiene/teardown** — vendored lib + arena must not linger half-wired on trunk; branch-only until
  PASS + ADR-047. Named cleanup task below (BP-040). Restore prod fw to DUT after.

## Decision

Phase-1 PASS → Phase-2 PASS = **ADR-047** + reframes the product decision to **Option A-lite is real**
(reliable WebRadio on the multi-app build, no second firmware). Any phase fail = **Option B stands**,
ADR-045 unchanged, recorded — cheaply, before the fork on a Phase-1 kill.

## Task topology (PM — to file when directed)

- **TASK-261** — M-MEMBUDGET spike (P1), phased with the gates above; **EXP-010** record; branch
  `rnd/membudget`. **Cleanup id: TASK-262** (revert vendored lib + arena + flags + any env if merged before a
  fail — BP-040/041). Phase 3 **couples the M-PLAYER-STATE pair (TASK-259 + TASK-260)**. Phase 2 is gated
  behind a Phase-1 PASS. **PM gate (QM B2):** file TASK-262 in the *same change* as TASK-261 (the BP-040
  cleanup-id-before-scheduling rule, mirroring TASK-255→256).
- **BP-041 disposition (QM N2):** the reserved arena is **unconditional / always-on** on a PASS — it is NOT a
  new `-D` build variant, so no `run/check` gate is owed. If any `-D` flag (e.g. `ARENA_BYTES`) is introduced
  and kept, it enters `run/check` in the same change or is removed.
- **BP-042 check (QM N3) — TASK-261 DoD:** before Phase 2 vendors the lib, verify the **project**
  `platformio.ini` audio-dep pin carries the why-not-newer note inline (EXP-009 added it only to the throwaway
  rig; the "low-maintenance because frozen" claim must rest on the project pin, not the rig's).
- TASK-259 may proceed in parallel (it is a standalone UX/state change), but Phase 3 depends on it.

## Out of scope

The shipping decision itself (Architect ADR-047 + a product call), dynamic-dataTask (Q2 — deferred unless
Phase 0/1 shows a ~10 K shortfall), UI for the mode toggle beyond what TASK-259 covers.
