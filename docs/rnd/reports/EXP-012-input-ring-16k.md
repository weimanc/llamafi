# EXP-012 — Input-ring 8 K → 16 K: slow-stream underrun fix, post-arena (TASK-233 residual)

> Owner: R&D · 2026-06-29 → 2026-07-02 · **Status: CLOSED — H1 true (decoder fine at 16 K), H2 false (no underrun benefit) → input ring stays 8 K** · DUT: ESP32-2432S028R (no PSRAM, `cyd2usb_webradio`)
> Feeds: TASK-233 (no-PSRAM playback residual — slow-stream underruns) · TASK-262 (A-lite arena, promoted)
> Prior art: EXP-007 (heap spike — the "16 K input → decoder OOM" finding this re-tests) · TASK-258/EXP-009
> (footprint-lever correction) · TASK-271 (soak harness + long single-stream soak: fast streams STABLE)

---

## Question

The one standing no-PSRAM residual (TASK-233) is **slow-stream underruns**: the input ring was shrunk to 8 K
to fit memory, so a slow/jittery stream starves it. Long-soak (2026-06-29) proved a *fast* stream is rock
solid (7 min, 0 drops, 0 new underruns, buffer 95–100%), so the problem is narrow — but real for slow
stations (auto-skip currently papers over it).

**Can the input ring grow 8 K → 16 K to absorb more jitter, without bringing back the decoder OOM?**

## Hypothesis

EXP-007 found "growing the input buffer to 16 K made the decoder fail every time" — but that was measured
**before A-lite**, when the decoder allocated from the *same fragmented general heap* as the input ring
(zero-sum). TASK-262 now isolates the decoder in its own 24 K `mb_arena` (`heap_caps_malloc`, walled off), so
the input ring and decoder **no longer compete for the same contiguous block**.

→ **H1:** at 16 K input, the decoder still allocates reliably (EXP-007's zero-sum is obsolete).
→ **H2:** 16 K input measurably reduces slow-stream underruns (`underruns/min` ↓, `minBufPct` ↑).

**Falsifiable:** if the decoder OOMs again at 16 K, the zero-sum still holds → abort; input ring stays 8 K.

## The knob (one line, in our code — not the vendored lib)

In `app/src/webRadioApp.h::_play()`, after `new Audio(...)` and **before** `connecttohost()`:
```cpp
#ifdef WR_INBUF_16K
    wrAudio().setBufsize(16384, 0);   // EXP-012: 8K→16K input ring
#endif
```
InBuff is allocated inside `connecttohost` (`initInBuff()`), which runs in `_play()` — **after** the station
fetch — so this does NOT touch the fetch-TLS path (confirm `initInBuff()` timing in Phase 1). Behind
`-DWR_INBUF_16K` so baseline↔trial is a single build flag and rollback is trivial.

Current input ring: `Audio.h: m_buffSizeRAM = 1600 * 5` (8000 B), INTERNAL/general heap, NOT in the arena.

## Method — 4 phases, all on `cyd2usb_webradio` (no 403 starvation; arena identical to production)

**Phase 0 — Baseline (8 K), establish "before":**
1. Probe pass: play a station, capture `[membudget]` CP1/CP2 → `freeInt / lfbInt / freeDma / lfbDma` at
   decoder-init. This is the headroom the input ring has to grow into.
2. **Slow-station hunt** (gating prerequisite): extend the churn soak to log per-station `underruns` +
   `minBufPct` + sustained `playMs`; pick 1–2 stations that genuinely underrun. *No slow station → nothing to
   measure; record and stop.*
3. Baseline soak the slow station (auto-skip OFF, ~5 min): `underruns/min`, `minBufPct`, sustained `playMs`.

**Phase 1 — Build the 16 K trial:** add the `setBufsize` + `-DWR_INBUF_16K` env. Confirm `initInBuff()` runs
post-fetch. `run/check` 6/6.

**Phase 2 — Re-measure at 16 K (the two questions):**
1. **Decoder still allocates?** (EXP-007 re-test) — play 10+ stations; require **0** `MP3Decoder_AllocateBuffers:
   not enough memory` and **0** arena acquire-FAILs. Capture new `freeInt/lfbInt` at decoder-init.
2. **Underruns drop?** — soak the *same* slow station; compare `underruns/min`, `minBufPct`, sustained `playMs`.

**Phase 3 — Regression + DMA check:**
- Re-run the 7-min fast-stream soak → still stable, no decoder fail.
- Watch `lfbDma`: did the bigger input ring shift the bottleneck to the 8 K I2S DMA ring? (informs a follow-on
  DMA experiment.)

## Decision criteria

| Outcome | Action |
|---|---|
| Decoder OOM returns at 16 K | **ABORT** — zero-sum still holds; input ring capped at 8 K. Close EXP-012. |
| Decoder fine **+** slow-stream underruns measurably drop, no fast regression | **PROMOTE** — keep `setBufsize(16384)`, drop the flag, file a TASK (ships via `MEMBUDGET_PHASE1`). |
| Decoder fine, underruns **unchanged** | Bottleneck is the **DMA ring**, not input → pivot to a DMA-ring experiment; revert input change. |
| 16 K marginal (intermittent OOM) | Try **12 K** (`1600×7.5`); fallback ladder 16 K → 12 K → 8 K. |

## Instrumentation (already exists — no new firmware)

- `[membudget]` CP1/CP2: `freeInt/lfbInt/freeDma/lfbDma` at decoder-init.
- `get wrUnderruns`: `underruns / minBufPct / bufPct / playMs`.
- `app/tools/test_webradio_soak.py` (per-station churn metrics) + the long single-stream soak script.

## Risks & rollback

- **Decoder re-fragmentation** (the thing under test) — caught Phase 2.1; revert.
- **Production parity:** the change ships via `MEMBUDGET_PHASE1`, so smoke the production build (boots clean,
  no OOM, fast-stream stable) before promoting.
- **DMA pool:** the input ring is INTERNAL, but on ESP32 INTERNAL/DMA overlap — watch `lfbDma` doesn't collapse
  the I2S ring path.
- **Rollback:** drop `-DWR_INBUF_16K` / remove one line (TASK-256 revert lineage).

## Results

### Phase 0 — DONE 2026-06-29 (16 stations surveyed, arena held, auto-skip OFF)

**Decoder-init headroom (CP2, after arena 24 K + current 8 K InBuff allocated):**

| Metric | min | max | Reading |
|---|---|---|---|
| `freeInt` | 43,344 | 52,800 | total free INTERNAL |
| **`lfbInt`** | **38,900** | **38,900** | **largest contiguous INTERNAL block — the room the input ring grows into** |
| `freeDma` | 3,344 | 12,800 | total free DMA |
| `lfbDma` | 2,292 | 10,740 | I2S DMA ring headroom — **tight** |

**→ INTERNAL headroom is ample.** `lfbInt` = **38,900 B** at decoder-init *with* the current 8 K InBuff
already allocated. Growing the input ring +8 K (→16 K) consumes 8 K more general heap, leaving ~31 K contiguous
— and the decoder is in its own 24 K arena, so it is untouched. **H1 strongly supported: there is clear room
for a 16 K input ring.** (At InBuff-alloc time the block is even larger, ~47 K, so the 16 K alloc itself fits
trivially.)

**→ DMA is the genuinely tight pool** (`lfbDma` 2.3–10.7 K) — confirms the input ring (INTERNAL) is the right
lever and the I2S DMA ring (8 K) has little room to grow (separate question, likely NO budget).

**Slow-station shortlist (the `buf%` low-water at end of an 18 s hold is the discriminator — `minBufPct` is
startup-dominated so it reads 0 for all):**

| Station | sustained | end `buf%` | Read |
|---|---|---|---|
| **st10** | 2.0 s | 0% | died fast — genuinely slow/dead |
| **st7** | 16 s | **22%** | playing but buffer chronically draining → underrun-prone |
| **st5** | 16 s | **23%** | same |
| **st3** | 16 s | **32%** | borderline |
| st0/1/9/11/13/15 … | 16 s | 90–100% | healthy/fast (buffer full) |
| st6 | — | dead | never reached PLAYING |

**EXP-012 baseline targets = st5, st7 (chronic ~22% buffer), st10 (2 s death).** These are real slow streams
to measure the 16 K ring against.

**Phase 0 verdict: GO.** Both prerequisites met — (a) ~38.9 K INTERNAL headroom to grow the ring into, (b)
slow stations exist to measure. Proceed to Phase 1/2 (build 16 K trial, re-test decoder-alloc + slow-station
underruns).

### Phase 1 — DONE 2026-07-02

Knob built as planned: `wrApplyInBufTrial()` in `webRadioApp.h` (both `new Audio` sites — the object is
deleted on suspend, so the trial must re-apply per construction), behind `-DWR_INBUF_16K` via a new
experiment-only env `cyd2usb_webradio_16k` (extends `cyd2usb_webradio`). `initInBuff()` timing confirmed:
InBuff is calloc'd inside `connecttohost()` → `setDefaults()`, after the station fetch. `run/check` 6/6.
Ground truth on DUT: `inputBufferSize: 14783` (= 16384 − 1600 reserve − 1) vs baseline `6399`.

Measurement harness: `app/tools/exp012_measure.py` (survey all stations for H1 + long-hold slow-station
soak for H2; matches stations across runs by URL — **indices are NOT stable across refetches**, which
invalidated the Phase 0 st5/st7/st10 shortlist and forced a same-day 8 K control run instead of comparing
against the 3-day-old Phase 0 table).

### Phase 2 — 16 K run DONE 2026-07-02 (16 stations, auto-skip OFF, 18 s survey + 120 s slow hold)

- **H1 (decoder still allocates): PASS on substance** — 8/16 stations reached playback (the other 8 were
  dead streams this fetch, station-side); **0 decoder OOM, 0 arena acquire-FAIL** across all 8. The 24 K
  arena walls the decoder off exactly as hypothesized; EXP-007's zero-sum is obsolete.
- `lfbInt` at decoder-init = **38,900 constant** — identical to the 8 K baseline. The 16 K ring carves
  from a *different* free region than the big contiguous block, so INTERNAL contiguity is untouched.
- **`lfbDma` at decoder-init: 948–3,316** (vs 2,292–10,740 at 8 K, Phase 0) — the ring is DMA-capable
  RAM, so the +8 K comes out of the DMA pool: pre-connect `lfbDma` drops 20.5 K → 4.6 K once the ring
  exists. Safe mid-session (I2S DMA ring installs once at first `Audio` construction with ~36 K free),
  but this is the Phase 3 suspend→re-enter watch item.
- Slow-station hold (st7 = `soulradio02.live-streams.nl`): **122.8 s sustained, 1 underrun (0.5/min)**,
  end buf 9 %.
- Caveat: `bufPct` is a fraction of the ring size (14,784 vs 6,400 B), so percentages are not comparable
  across builds — compare byte runway and underruns/min instead.

### Phase 2 — same-day 8 K control DONE 2026-07-02 (identical procedure, ring 6399 confirmed)

Same 16-URL station list in the same order as the 16 K run (verified by URL — both runs same query result),
~40 min apart. 11/16 reached playback (vs 8/16 at 16 K — stations flap minute-to-minute, availability is
station-side noise, not ring-related). 0 decoder OOM / 0 arena FAIL, H1 gate PASS.

**The head-to-head (same-day, same stations):**

| Metric | 8 K (control) | 16 K (trial) |
|---|---|---|
| ring size on wire (`inputBufferSize`) | 6,399 | 14,783 |
| decoder OOM / arena FAIL | 0 / 0 (11 stations) | 0 / 0 (8 stations) |
| `lfbInt` at decoder-init | **38,900** (constant) | **38,900** (constant) |
| `lfbDma` at decoder-init | 1,396–9,716 | 948–3,316 |
| pre-connect `lfbDma` after ring alloc | ~20 K | ~4.6 K (**ring eats the DMA-capable pool**) |
| 120 s slow-station hold, sustained | 121–122 s (st0, st8) | 122.8 s (st7) |
| 120 s slow-station hold, underruns | **1/session (0.5/min)** | **1/session (0.5/min)** |
| steady-state underruns | ~0 (the 1 is a startup artifact — every station on both builds logs exactly ur=1 per PLAYING session) | ~0 (same) |

Unexplained-but-secondary: steady-state buffer *fill in bytes* did not scale with ring size (16 K often held
*fewer* bytes than 8 K on the same station). The lib's `f_stream` start threshold is `maxFrameSize`-based,
not ring-relative, and the two passes were 40 min apart — fill level is dominated by server pacing, so no
clean attribution. Underruns/min is the honest H2 metric, and it is identical.

### Phase 3 — not run (moot)

No promotion → no regression pass needed. The `lfbDma` observation above is the recorded flag: a 16 K ring
allocates from DMA-capable RAM and would leave <5 K DMA headroom for the suspend→re-enter path where the I2S
DMA ring must re-install. Any future revisit must clear that wall first.

## Verdict — CLOSED 2026-07-02: H1 TRUE, H2 FALSE → **do not promote; input ring stays 8 K**

- **H1 confirmed:** the decoder allocates reliably at a 16 K input ring — EXP-007's "16 K input → decoder
  OOM every time" zero-sum is **obsolete post-arena** (TASK-262). The ring *can* grow if a real need appears.
  That knowledge is the experiment's lasting value.
- **H2 falsified:** underruns did not drop (identical 0.5/min, both = one startup artifact per session;
  steady-state ≈ 0 on both builds). Today's "slow" stations (chronic low buffer) played 120 s clean on 8 K.
  The TASK-233 slow-stream underrun residual did not reproduce as a chronic condition; auto-skip remains the
  right handling for genuinely dying streams.
- **Costs of 16 K with no benefit:** −8 K general heap while playing, DMA-capable headroom collapses
  20 K → 4.6 K.
- Per the decision matrix (decoder fine + underruns unchanged): input ring is not the bottleneck. A DMA-ring
  experiment remains *possible* future work but has no motivating symptom while steady-state underruns are ~0.
- **Disposition of the knob:** `-DWR_INBUF_16K` + `wrApplyInBufTrial()` + env `cyd2usb_webradio_16k` stay in
  the tree, default-off (zero cost in production builds; re-arms this experiment in minutes). Harness:
  `app/tools/exp012_measure.py`.
