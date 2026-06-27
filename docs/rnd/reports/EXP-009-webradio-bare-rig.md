# EXP-009 — WebRadio bare-rig: no-PSRAM ceiling, bottom-up (TASK-258)

> Owner: R&D · 2026-06-27 · DUT: ESP32-2432S028R (no PSRAM) · rig: `~/proj/webradio-bare/` (throwaway, out-of-tree)
> Panel-approved PROP rev2 (unanimous). Feeds TASK-241 / ADR-045. Cites EXP-007 (20.6 K), EXP-008 (21 K/24 K).

**Headline: the no-PSRAM CYD hardware CAN play MP3 radio.** Bare (no display, no app shell, internal DAC
GPIO26, ESP32-audioI2S v2.3.0, espressif32@6.9.0 — full parity with our build) the decoder allocates and the
stream holds. **ADR-045's "stable no-PSRAM playback = NO-GO" is a *footprint* limit, not a hardware/silicon
limit.**

## Config A (no-TFT) — PASS

| Capture point | free | maxAlloc / deadblk(8-bit) |
|---|---|---|
| boot (pre-wifi) | 257,700 | 110,580 |
| boot (post-wifi) | 207,308 | 110,580 |
| **CP1 pre-connect** | 207,300 | 110,580 |
| **CP2 decoder-init** | **166,056** | 102,388 |
| settle (~45 s) | ~170,000 | 102,388 |

- `connecttohost=1`; `MP3Decoder has been initialized, free Heap: 166056`; ICY `StreamTitle` flowed and
  **changed across a track** (held ≥ ~45 s, stable heap) → **plays.** (Positive control: a wrong first
  station — `0n-80s.radionetz.de` — returned `connecttohost=0` = a clean network miss, not a heap fault;
  excluded. SomaFM HTTP played first try.)
- **Audio path cost ≈ 41 K** (CP1 207,300 → CP2 166,056): input buffer 8 K + Helix MP3 ~22.7 K + connection.

## Model correction (vs EXP-007/008)

The **"38,900 dead block" is NOT a fixed quantity** — it was the *largest free block at our fragmented
11-app state*. Bare, `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)` = **110,580** (→ 102,388 after the
decoder). So the prior `usable = free − maxAlloc` framing was a misread. The real constraint is **total free
heap at connect + contiguity for the ~41 K audio path**:

| Build | free @ connect | result |
|---|---|---|
| EXP-008 our 11-app (stack-trimmed) | ~63 K | decoder FAIL |
| **EXP-009 bare** | **207 K** | **decoder OK, plays** |

The threshold sits between ~63 K and 207 K. Our build fails because its ~**147 K resident footprint** (app
objects, dataTask stack+structs, system/WiFi/TLS) leaves only ~60 K — too tight for the ~41 K path + the
headroom the allocator needs to avoid fragmentation failure.

## Static-RAM anchor

Bare firmware static = **57,500 B** (17.5 % of 327,680) → ~270 K heap pool. Our 11-app build's resident
footprint is the entire gap.

## Next: Config B (+TFT) — budget anchor

Pending: add the CYD TFT_eSPI driver/framebuffer (our `User_Setup` build_flags + `tft.init()`) and re-measure
CP1/CP2. Only config-B's number is a valid in-project budget (our product always carries the display). Then
`usable_bare(B) − the ~41 K audio path` = the headroom a stripped in-project variant must preserve, stated as
a bounded claim (our path-dependent heap pays a fragmentation tax the pristine bare heap doesn't).

## Rig config (for reproducibility — rig is throwaway)

`platform = espressif32@6.9.0`, `board = esp32dev`, `lib_deps = esphome/ESP32-audioI2S@2.3.0`,
`Audio(true, I2S_DAC_CHANNEL_LEFT_EN)` (GPIO26; GPIO25 untouched), `setVolume(8)`, SomaFM HTTP 128 kbps
streams, ~40-line serial rig (`heap`/`play`/`stop` + `audio_info` CP2 capture). WiFi baked from project
`wifi_creds.h` into gitignored `secrets.h` (no creds committed/logged).

## Verdict

**Config A PASS → hardware capable; ADR-045's NO-GO is footprint-bound, not silicon-bound.** This re-frames
TASK-255 from "coin-flip, is it even possible" to a quantified budget problem ("get our resident footprint
down so ~≥ the bare threshold of free heap survives to `_play()`"). Config B will pin the budget number.
