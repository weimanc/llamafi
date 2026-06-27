# EXP-008 — WebRadio no-PSRAM: Spotify-disable Step-1 + headless-footprint survey (TASK-255)

> Owner: R&D · 2026-06-27 · DUT: ESP32-2432S028R (no PSRAM) · branch `rnd/webradio-nopsram`
> Feeds TASK-255 / TASK-241 / ADR-045. Design: `docs/architecture/designs/M-WEBRADIO-SPOTIFY-DISABLE.md`.

**Conclusion up front:** the Spotify-disable variant **failed its Step-1 kill gate, but it tested the
wrong build** (full 11-app shell). A Lane-B survey shows **no-PSRAM ESP32 internet radio is a solved,
common configuration** — the hardware is capable and our *footprint* is the wall. Next: Lane A
(headless WebRadio-only build) is the true ceiling test. Two Lane-C inputs surfaced: **library version**
and **AAC**.

## Part 1 — Step-1 measurement (`cyd2usb_webradio`, full multi-app disabled build)

Method: `-DDISABLE_SPOTIFY` skips `spotifyTask::begin()` (sole guard); V0 variant-aware harness; capture
`usable = free − maxAlloc` at WebRadio `_play()` entry (the decoder-alloc moment).

| Point | free | maxAlloc | usable | decoder |
|---|---|---|---|---|
| Boot | 107,652 | 59,380 | — | — |
| `_play()` entry | **59,976** | **38,900** | **21,076** | **FAIL** — `MP3Decoder_AllocateBuffers(): not enough memory` (needs ~22,700; short ~1.6 KB) |

- **The ~10 KB `spotifyTask` reclaim is visible at boot (107 K) but does NOT survive to `_play()`.**
  Play-entry `usable` converges to ~21 K ≈ EXP-007's 20.6 K failing baseline — one task is noise vs the
  shell + 10 other apps + the audio path.
- **The 38,900 caps-restricted dead-block is unchanged** on the disabled build (R&D relayout concern
  resolved — no shift). `usable = free − maxAlloc` is the right metric; the real decoder failure confirms
  the number.
- **Verdict: Step-1 FAIL on the full build — but it is not the ceiling test.** Default build proven
  byte-unchanged (V1: `.text`/`.iram`/`.dram` identical; `.rodata` differs only by the 2-byte build
  timestamp).

## Part 2 — Lane B survey: how no-PSRAM ESP32 radio is actually done

**Existence proof (local, authoritative):** ESP32-audioI2S ships `examples/Simple_WiFi_Radio` — a TFT
display **+** MP3 internet radio on a plain ESP32, **no PSRAM**, the default 8 KB RAM buffer
(`m_buffSizeRAM = 1600*5`), no `setBufsize`. A display and radio coexist on bare silicon; the only
difference from us is **one app vs eleven + the multi-app shell**.

**Library version is a prime suspect (Lane-C input #1).** We ship **v2.3.0** (esphome fork). Field
reports:
- **v2.0.6 is the last version that officially supports no-PSRAM.** **PLSousa's patched fork of v2.0.6**
  (9 patches for GCC-14 + stability) is the recommended no-PSRAM library today.
- **v3.x unconditionally allocates a ~704 KB audio buffer at boot → instant crash on no-PSRAM.** We are
  *not* on v3.x (we boot fine and fail only at decoder-alloc), so v2.3.0 sits between — works at boot but
  is not the no-PSRAM-tuned line. **Worth A/B-testing v2.0.6/PLSousa vs our v2.3.0** for decoder
  footprint + no-PSRAM buffer handling.

**Footprint comparison confirms the diagnosis.** A working no-PSRAM radio reports **~163 KB free after
MP3 decoder init** (of ~231 KB internal RAM). We have **~60 K at `_play()` (21 K usable)**. Same decoder,
same silicon — the ~100 KB gap is *our resident footprint*, not the hardware.

**Codecs (Lane-C input #2):** MP3 and **AAC** are both validated on no-PSRAM; WAV works; FLAC/M4A
untested. AAC's decoder memory profile vs Helix MP3's ~22.7 KB is worth measuring — could cut the
*demand* side.

## Recommendation

1. **Lane A (primary):** build a headless WebRadio-only variant (strip the registry to WebRadio +
   Settings, boot straight in) and re-take the Step-1 measurement — the true ceiling. The existence proof
   predicts ample headroom (bare ≈ 163 K free). If it clears 22.7 KB → startup fixed; then `setBufsize`
   a bigger RAM buffer (NOT PSRAM-gated) and re-measure for the underrun fix.
2. **Lane C-1:** A/B the audio library — our v2.3.0 vs v2.0.6 / PLSousa no-PSRAM fork — for decoder
   footprint.
3. **Lane C-2:** measure AAC decoder demand vs MP3; consider AAC-station filtering.
4. **ADR-045:** do not overturn yet — but its "NO-GO" is now known to be a *full-multi-app-footprint*
   result, not a hardware limit. The bare build settles it either way.

## Sources
- [ESP32-audioI2S #785 — mp3 decoder cannot allocate memory](https://github.com/schreibfaul1/ESP32-audioI2S/issues/785)
- [ESP32-audioI2S Discussion #1262 — no-PSRAM solution (PLSousa fork of v2.0.6; v3.x 704 KB boot alloc)](https://github.com/schreibfaul1/ESP32-audioI2S/discussions/1262)
- [ESP32-audioI2S #126 — not enough memory to allocate mp3decoder buffers](https://github.com/schreibfaul1/ESP32-audioI2S/issues/126)
- Local: `app/.pio/libdeps/cyd2usb_winamp/ESP32-audioI2S/examples/Simple_WiFi_Radio/Simple_WiFi_Radio.ino`; `src/Audio.cpp:38` (`setBufsize`); `src/Audio.h:145-146` (buffer defaults)
