# EXP-007 — WebRadio no-PSRAM heap measurement spike (TASK-235)

> Owner: Developer/R&D · 2026-06-24 · DUT: ESP32-2432S028R (no PSRAM) · debug firmware + serial probes

Resolves TASK-235 (ADR-045 move 2): measure the exact decode-failure point so we can choose
between "free more RAM" (TASK-233 direction a) and PSRAM-gating (direction d). **Conclusion is
a qualified NO-GO on stable playback, with one cheap startup-margin win worth taking.**

## Numbers measured

**Helix MP3 decoder demand** (host `sizeof`, exact, padding-accurate — see `scratchpad/helix_sizes.c`):

| Buffer | Bytes |
|---|---|
| MP3DecInfo | 2000 |
| HuffmanInfo | 4624 |
| DequantInfo | 792 |
| IMDCTInfo | 6944 |
| **SubbandInfo (largest)** | **8708** |
| ScaleFactorJS / FrameHeader / SideInfo / MP3FrameInfo | 148 |
| **TOTAL (9 allocs)** | **23 216 (22.7 KB)** |

**Runtime heap at the decode-alloc moment** (firmware `dprobe` + library `audio_info` logs):

| Input buffer | free at decode | `maxAlloc` | decoder result |
|---|---|---|---|
| 8 000 B (lib default, ~6.4 KB usable) | ~67 KB | **38 900** | succeeds (intermittent) |
| 16 000 B (×2, `setBufsize`, ~14.4 KB usable) | ~59.5 KB | **38 900** | **fails every time** |

## The key finding — a caps-restricted dead block + a zero-sum squeeze

`maxAlloc` is pinned at **38 900 in both cases** — growing the input buffer by 8 KB did *not*
shrink it, and the 22.7 KB decoder alloc did *not* shrink it either. So **neither the audio input
buffer nor the MP3 decoder can allocate from that 38.9 KB block** — it's a caps-restricted region
(`MALLOC_CAP_*` mismatch) that `ESP.getMaxAllocHeap()` counts but audio allocations can't use.

Effective audio heap is therefore `free − 38 900`:
- 8 KB buffer → 67 − 38.9 = **28.1 KB** usable; decoder needs 22.7 → **~5 KB margin** → usually
  succeeds, occasionally fails on fragmentation (explains the intermittency exactly).
- 16 KB buffer → 59.5 − 38.9 = **20.6 KB** < 22.7 → **always fails**.

The input buffer and the decoder are **zero-sum over ~28 KB of usable internal RAM**, and the
decoder alone eats 22.7 KB. **You cannot enlarge the input buffer (the lever for stream stability /
underrun tolerance) without starving the decoder** — measured, not theorised.

## Two distinct failure modes (previously conflated)

1. **Decoder-alloc failure** (TASK-233 original framing): happens at the ~5 KB margin; intermittent.
   Sensitive to total usable heap → *addressable* by freeing a few KB.
2. **Input-buffer underrun** ("slow stream, dropouts are possible" flood): the ~6.4 KB usable input
   ring can't ride out network jitter, so slower stations decode fine then starve and die. This is
   the *dominant* death mode for slow stations and is **not addressable** — the only fix (a bigger
   buffer) breaks mode 1.

## Go / No-Go

- **NO-GO on general stable playback via "free more RAM."** The usable RAM ceiling (~28 KB) barely
  fits the decoder; there is no room to also fund a jitter-tolerant input buffer. Slow streams will
  always underrun. PSRAM is the only real fix and this board has none.
- **GO on a small, bounded startup-margin reclaim** (cheap, safe, worth it): free `s_webRadioDoc`
  (5 KB static `DynamicJsonDocument`) after the station fill, and any other reclaimable *internal*
  RAM, to roughly double the decoder's ~5 KB margin → fewer mode-1 failures → more stations reach
  PLAYING on the first try. Does **nothing** for mode 2. Scope it to startup reliability only; do
  not attempt to grow the input buffer. → fold into TASK-233.
- **NO-GO on PSRAM-gating / hiding the app.** WebRadio *does* work for fast, reliable streams; with
  auto-skip (TASK-234) the device tunes to one. Hiding the feature would throw that away.

**Net:** WebRadio on no-PSRAM is a **best-effort feature, ceiling-bound** — exactly ADR-045's
framing. Auto-skip (shipped) is the right UX; a 5 KB startup reclaim is the only worthwhile
memory work. Do not invest further in memory surgery; revisit only on a PSRAM-equipped target.
