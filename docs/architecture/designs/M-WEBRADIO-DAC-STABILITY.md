# Design — WebRadio internal-DAC stability (midscale silence, DMA window)

> Owner: Architect
> Status: implemented
> Note: DUT-verified 2026-09-27 (`cyd2usb_webradio` + `cyd2usb_player`, no crash, pool-neutral —
> see TASK-724). Not verified: whether the pop is actually gone (needs a listener with the
> speaker attached; not checkable from this session).
> Date: 2026-09-27
> Feeds: (ADR TBD — pending a listening check)
> Tracked-as: TASK-724
> Source: external PR weimanc/llamafi#1 (bvarbanov90), `Audio.cpp` hunks only. The rest of that PR
> (EQ panel, drive range, Settings, tests) is **out of scope** here.
> Registers: webradio-dac-001 · X071

## Context / pain points

WebRadio drives the **ESP32 built-in DAC** (GPIO26, mono) through the I2S peripheral in built-in-DAC
mode. That mode consumes **unsigned** PCM: `Audio::playSample()` adds `0x80008000` to every stereo
word (in `Audio::playSample()`), so **silence is 0x8000, not 0**. A literal-zero word is the negative rail.

The vendored `ESP32-audioI2S` fork (BP-042, frozen) inherits upstream behaviour written for external
I2S DACs, where zero *is* silence. Five places write or produce literal zeros into the DMA ring:

| # | Site (current `Audio.cpp`) | Trigger | Effect on internal DAC |
|---|---|---|---|
| 1 | `tx_desc_auto_clear = true` (l.201) | any DMA **underrun** (network/decoder stall) | driver zero-fills the descriptor → rail step → pop |
| 2 | `i2s_zero_dma_buffer` in ctor (l.245) | `Audio()` construction | ring starts at rail |
| 3 | `i2s_zero_dma_buffer` in `stopSong()` (l.2371) | stop / station change | rail step on every stop |
| 4 | `i2s_zero_dma_buffer` in `pauseResume()` (l.2396) | pause | rail step |
| 5 | `i2s_zero_dma_buffer` in `sendBytes()` error path (l.4197) | recoverable decode error | **discards queued audio** and steps to rail |

Separately, `playI2Sremains()` (l.2375) sets `m_validSamples = dma_buf_len × dma_buf_count` and then
calls `playChunk()`. `m_outBuff` holds 2048 stereo frames (`int16_t m_outBuff[2048*2]` in `Audio.h`).
Production (`MEMBUDGET_PHASE1`, 8×256) is exactly 2048 frames, so it fits with no margin. Any ring
larger than 2048 frames **reads past `m_outBuff`**. The non-`MEMBUDGET` 16×512 path (8192 frames)
already does this in upstream, but no shipping env uses it.

Symptom on the DUT class of hardware: audible pop on stall / stop / pause / station change, worst
with a small speaker at high Max-volume. (Reported by the PR author; **not reproduced here** — no
DUT run was done for this doc.)

## Goals

1. No rail-to-rail step on the internal DAC in any of sites 1–5.
2. **Zero change to the external-I2S path** (upstream behaviour retained; only `m_f_internalDAC`
   branches change).
3. No new steady-state DMA-pool cost unless the memory budget below shows it fits.
4. Keep `playI2Sremains()` memory-safe for any ring size.

## Memory budget

### What the manifest can and cannot say

`app/mem_manifest.yaml` declares `ceiling.DMA = 48000` but **registers no DMA-class buffer at all**:
every WebRadio row is `caps: INTERNAL` (decoder 23 216, inbuf 6 400, stations_doc 5 120 → 34 736 B
foreground). The I2S ring is allocated by `i2s_driver_install()` inside `Audio()`, driver-owned, so
the manifest never models it. On this no-PSRAM part `MALLOC_CAP_DMA` is the same 8-bit internal pool
the decoder arena and InBuff come from (lesson at `lessons_learned.md`, the TASK-442 entry), so the
ring competes with them for the same bytes.

Consequence: the manifest's pool-level arithmetic (290 000 − 60 000 headroom = 230 000 vs 34 736)
looks roomy and **cannot answer this question**. The binding figure is the *measured* free DMA pool
after the decoder is up, per BP-063 (diff `[membudget]` probes; do not reason from the manifest).

### Ring cost by option (16-bit stereo = 4 B/frame; the built-in DAC needs the stereo format)

| Config | Ring bytes | Δ vs prod | Frames | Play-through @44.1 kHz |
|---|---|---|---|---|
| 8 × 256 (**production**) | 8 192 | — | 2 048 | 46 ms |
| 8 × 320 | 10 240 | +2 048 | 2 560 | 58 ms |
| 12 × 256 | 12 288 | +4 096 | 3 072 | 70 ms |
| **8 × 512 (PR #1)** | **16 384** | **+8 192** | 4 096 | 93 ms |
| 16 × 512 (stock, disabled) | 32 768 | +24 576 | 8 192 | 186 ms |

### Measured headroom (existing records, not re-measured today)

| Checkpoint | freeDma | lfbDma | Source |
|---|---|---|---|
| CP2 post-decoder-init, **WebRadio** (8×256 ring) | **5 100** | 4 852 | `tasks-archive.md:18562` |
| CP2 post-decoder-init, **Player** (8×256 ring) | **2 416** | 2 292 | `tasks-archive.md:18197` |
| CP2, first arena spike (older build) | 12 904 | 11 252 | EXP-010 |
| CP1 pre-decoder, after ring install | 23 180 | 20 468 | EXP-010 |
| Idle, post-boot (no audio) | 75 960 | 73 716 | live monitor 2026-09-27 |

The two CP2 rows are the ones that matter: the ring is installed at CP1, **then** the 24 576 B
arena, the InBuff and the Helix structs are taken from the same pool.

### Verdict per option

| Option | CP2 freeDma after | Fits? |
|---|---|---|
| Production 8×256 | 5 100 (WebRadio) / 2 416 (Player) | baseline |
| 8×320 (+2 048) | ~3 052 / **~368** | WebRadio yes but thin; **Player marginal** |
| 12×256 (+4 096) | ~1 004 / **−1 680** | WebRadio near-zero; **Player no** |
| **8×512 (+8 192)** | **−3 092 / −5 776** | **No.** Something fails at or after decoder init |

The PR's comment claims a 16 K window "leaves about 20K allocation headroom". That matches the
**CP1** row (lfbDma ≈ 20 K) and not CP2. I believe the PR measured before the decoder arena and
InBuff were taken, but that is my inference; the PR body does not say where it sampled.

Additional floor: TASK-429 shows a ~6 KB `DynamicJsonDocument` allocation already fails at
`lfbDma ≈ 2.8 KB` during playback, and ADR-057 records crashes at `lfbDma = 8180` on the Teletext
path. Playback already sits below both. Spending more of the pool there is the wrong direction.

## Design space

### Option A — Midscale-silence fixes only (no ring change)  ← lean

Take the five-site fix, gated on `m_f_internalDAC`:

- `tx_desc_auto_clear = !internalDAC`.
- Ctor / `stopSong()` / `pauseResume()`: internal DAC gets `playI2Sremains()` (filtered-zero →
  0x8000 midscale) instead of `i2s_zero_dma_buffer`; external I2S keeps the zero-fill.
- `sendBytes()` error path: internal DAC keeps the queued audio.
- `playI2Sremains()`: fill in chunks bounded by `m_outBuff` (memory-safe for any ring).

DMA cost: **0 B**. Fixes sites 1–5 and the latent overrun.
Cost/risk:
- With auto-clear off, an underrun **replays the stale ring** (≈46 ms of old audio, looping) rather
  than popping. That is a buzz/stutter instead of a click. Quieter, not silent. With Max-volume 0 it
  is true silence.
- `playI2Sremains()` blocks for a full ring drain (≈46 ms at 8×256) inside `stopSong()` /
  `pauseResume()`. Confirm which task calls them (pump task vs UI) before accepting.
- Constructor: the driver zeroes the ring at `i2s_driver_install()` before the prime, so a short
  rail transient at construction may remain. Option A shrinks it; it does not prove it gone.

### Option B — Option A + 8×512 ring (PR #1 as submitted)

Adds 8 192 B and a 93 ms underrun-absorbing window. **Rejected on budget**: −3 092 B at WebRadio CP2
by the numbers above; Player is worse. Would need ≥ 8.2 KB freed elsewhere first.

### Option C — Option A + a modest ring growth (8×320 or 12×256)

Buys 12–24 ms of extra stall tolerance for 2–4 KB. Only defensible if WebRadio *and* Player still
clear a floor after the change. Player at 8×320 leaves ~368 B, which I would not accept. Candidate
only for a **WebRadio-only** ring size, which needs a per-app `Audio` config (today the ring is
compile-time). Needs a real underrun case to justify the bytes: EXP-010 saw only one startup
transient underrun at 8×256 and none in ≥120 s sustained playback at 128 kbps. **No evidence today
that a bigger ring is needed once the pop is fixed.**

### Option D — Free DMA-pool bytes first, then revisit B/C

Candidate donors: `webradio_stations_doc` (5 120 B, manifest notes it never coexists with the
decoder; TASK-289), InBuff sizing (EXP-012: 16 K gave no benefit, 8 K stays), the 1 536 B staging
arena not registered for Player. None is small work. **Not proposed now.**

### Not evaluated: mono ring

The built-in DAC path might allow a single-channel I2S format, halving ring bytes. I have **not
verified** this in the vendored driver/IDF version; listed only as a question.

## Lean / decision

**Option A.** It removes the pop at zero pool cost and fixes the latent overrun. Do **not** take the
8×512 ring; the budget does not close, and there is no measured underrun that justifies the bytes.
Revisit ring size only after Option A is DUT-verified and a real stall case is recorded.

## DUT verification (2026-09-27, post-implementation)

Fresh `[membudget] CP2-decoder-init` captures on this HEAD, both against the live board
(ESP32-2432S028R, `/dev/ttyUSB0`):

| Env | Action | freeDma | lfbDma | Result |
|---|---|---|---|---|
| `cyd2usb_webradio` | play station 0 (Radio 10) | 4820 | 2292 | OK, played |
| `cyd2usb_webradio` | reconnect after 1 startup underrun | 4548 | 1652 | OK, no crash |
| `cyd2usb_webradio` | station change (play idx 1) | 4604 | 2292 | OK, played |
| `cyd2usb_player` | 6+ track auto-advance cycles (tone1..5.mp3) | 4112 (steady) | 3956 (steady) | OK, no crash, no drift |

All four are **at or above** the archived pre-change figures (WebRadio ~5100/4852 B, Player
~2416 B) — no regression, confirms Option A is pool-neutral as designed. The Player figure is
notably better than the stale archived row (2416 → ~4100 B); re-derived fresh per Open Question 1,
which is now closed.

Exercised without incident: station play, forced reconnect after an underrun (`get wrUnderruns`:
underruns=1, recurrentUnderruns=0 — the known startup transient, not new), `set wrStop`,
station-to-station switch, LocalPlayer EOF-triggered auto-advance across 6+ tracks (each one a
`stopSong()`/decoder-reinit cycle), and clean app-switch teardown from both WebRadio and
LocalPlayer (arena released, pump deleted, no heap leak across the whole session).

**Not verified — cannot be, from this session:** whether the pop is actually gone. That needs a
person listening with the speaker connected. Everything checkable by log/heap inspection (crash,
leak, pool cost, decode-error resilience) passed.

`pauseResume()` (site 4) was **not exercised** — confirmed by grep that nothing in `app/src/`
calls it (matches `CLAUDE.md`'s note that touch has no play/pause wired). The fix there is
defensively correct but currently unreachable dead code, same as upstream's own path.

## Open questions

1. ~~Fresh CP2 numbers~~ — **closed above.**
2. Which task calls `stopSong()` / `pauseResume()` — is a ~46 ms blocking fill acceptable there?
   (Not measured directly; no stall/lag was observed on stop/track-advance during this session.)
3. Is the constructor-time rail transient audible on the CYD amp? (Needs a listener; open.)
4. Should the manifest register the I2S ring as a `caps: DMA` row so this class of question is
   answerable from the manifest? (Separate task; the current gap is why this doc needs measurements.)
5. Upstream contribution: the PR is from an external contributor. PM to decide how to credit/merge
   (cherry-pick of the `Audio.cpp` hunks vs. re-implement), given PR #1 also carries unrelated scope.

## Exit criteria

- [x] `Audio.cpp` change confined to `m_f_internalDAC` branches; external-I2S code path byte-identical.
- [x] `run/check` green; host build of `cyd2usb_webradio` and `cyd2usb_winamp_debug` green.
- [x] `[membudget] CP2-decoder-init freeDma` on WebRadio and Player **unchanged** vs pre-change
      (Option A must be pool-neutral; any delta is a defect). Verified 2026-09-27, see table above.
- [ ] DUT: WebRadio play → stop → station change → pause/resume with no audible pop (**listening
      check** — needs a person with the speaker; play/stop/station-change exercised with no crash,
      the audible part is unverified), plus a forced-stall run to characterise the stale-ring replay
      (a startup-transient underrun occurred naturally and recovered cleanly; a deliberate mid-stream
      stall was not forced).
- [x] `playI2Sremains()` bounds verified for 8×256 (unchanged behaviour, exercised repeatedly on
      DUT with no crash). A larger scratch-env ring was **not** built/tested — reasoned from the
      arithmetic (`m_outBuff` capacity vs. ring frame count), not DUT-confirmed.
- [x] PATCH note added to the vendored `ESP32-audioI2S` patch record (`PATCH-DAC-1`).
