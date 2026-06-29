# EXP-012 — Input-ring 8 K → 16 K: slow-stream underrun fix, post-arena (TASK-233 residual)

> Owner: R&D · 2026-06-29 · **Status: PLANNED (not yet executed)** · DUT: ESP32-2432S028R (no PSRAM, `cyd2usb_webradio`)
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

_PENDING EXECUTION._ Estimated DUT time ~30–40 min (2 flashes; baseline + trial soaks).

| Phase | Metric | 8 K (baseline) | 16 K (trial) |
|---|---|---|---|
| 0/2.1 | `lfbInt` at decoder-init | _tbd_ | _tbd_ |
| 0/2.1 | decoder alloc OK (10+ stations) | _tbd_ | _tbd_ |
| 0/2.2 | slow-station `underruns/min` | _tbd_ | _tbd_ |
| 0/2.2 | slow-station `minBufPct` | _tbd_ | _tbd_ |
| 0/2.2 | slow-station sustained `playMs` | _tbd_ | _tbd_ |
| 3 | fast-stream soak (regression) | STABLE (TASK-271) | _tbd_ |
| 3 | `lfbDma` at decoder-init | _tbd_ | _tbd_ |

## Verdict

_PENDING._
