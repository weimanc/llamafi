# EXP-013 — Lane C-1: ESP32-audioI2S v2.3.0 ↔ v2.0.6 decoder-footprint A/B (TASK-257)

> Owner: R&D · 2026-07-13 · DUT: ESP32-2432S028R (no PSRAM) · rig: `~/proj/webradio-bare/` (EXP-009 rig, config B +TFT)
> Optional confirmation of EXP-009's bottom-up finding. Parent: TASK-258 step 4. Cites EXP-009.

**Headline: CONFIRMED — the library version is not a lever.** Swapping ESP32-audioI2S v2.3.0 ↔ v2.0.6
(only `lib_deps` changed, fresh `.pio/libdeps`, same station/buffer/CP2 capture, 3 valid trials/arm)
moves `usable`@CP2 by ~0 — the Δ is inside single-trial jitter, and contiguity (`maxAlloc`@CP2) is
**byte-identical** across arms. EXP-009's model stands: the Helix decoder is vendored ~identically
across the v2.x line; the no-PSRAM lever is **resident footprint, not library version**.

## Method

- EXP-009 rig unchanged (config B: +TFT, internal DAC GPIO26, espressif32@6.9.0, esp32dev).
  Arm A = `esphome/ESP32-audioI2S@2.3.0` (project pin); arm B = `@2.0.6` — **one-line `lib_deps`
  change, nothing else** (see "prior blocker" below). Fresh `.pio/libdeps` per arm, verified via
  `library.json` version.
- Same station all trials: `http://ice1.somafm.com/groovesalad-128-mp3` (SomaFM HTTP 128 kbps).
- Per trial: cold boot (DTR/RTS reset) → CP1 pre-connect → `play 0` → CP2 at decoder-init
  (`MP3Decoder has been initialized`) → StreamTitle proof → 25 s settle → heap query → `stop`.
- Driver: `ab_trials.py` (scratchpad; pyserial, port auto-resolve by VID:PID).

## Results

| | CP1 free | CP2 free (3 trials) | CP2 mean | CP2 maxAlloc | path cost (CP1−CP2) |
|---|---|---|---|---|---|
| **A — v2.3.0** | 206,684–206,696 | 165,440 / 163,076 / 163,088 | 163,868 | **102,388** | 41.2–43.6 K |
| **B — v2.0.6** | 207,216–207,224 | 165,964 / 163,600 / 165,964 | 165,176 | **102,388** | 41.3–43.6 K |

- **Δ `usable`@CP2 (B−A) ≈ +1.3 K mean — not significant.** Per-trial CP2 jitter is ±2.4 K in *both*
  arms (bimodal ~165.9 K / ~163.1 K — how much stream data sits buffered at the decoder-init instant),
  and the arm distributions overlap completely.
- **`maxAlloc`@CP2 identical: 102,388 both arms, every trial** (deadblk likewise). Zero contiguity gain.
- CP1 delta (+530 B for v2.0.6) matches its smaller static image (57,280 vs 57,800 B, −520 B) —
  a static-RAM rounding error, not a heap-path difference.
- Both arms played (ICY `StreamTitle` flowed each valid trial); settle heap ~170–173 K both arms.
- Build parity: identical linked lib set both arms (SPI, WiFi, WiFiClientSecure, LittleFS, SD, SD_MMC,
  SPIFFS, FS, FFat, TFT_eSPI, ESP32-audioI2S) — no link-set confound. Flash Δ −1.1 KB. Core toolchain
  NOT swapped (the EXP-008 trap avoided per task spec).

## Prior blocker resolved

TASK-257's noted `SD_MMC.h: No such file` (v2.0.6 predates `AUDIO_NO_SD_FS`) **did not reproduce** —
from a clean `.pio` *and* from an in-place pin flip on a cached build, PlatformIO's default `chain`
LDF resolves the framework's bundled SD/SD_MMC/SPIFFS fine. No shim needed; the rig doesn't set
`AUDIO_NO_SD_FS`, so both versions pull the same SD/FS stack unconditionally. (v2.0.6 API note: ctor
is `Audio(bool, uint8_t, uint8_t)` — `I2S_DAC_CHANNEL_LEFT_EN` converts implicitly; no src change.)

## Rig/ops notes (for future rig users)

- Rig `secrets.h` had the pre-rename SSID (`yellowbrickroad` — AP renamed to `yellowbrickroad-2.4Ghz`
  2026-07-09); refreshed from `app/data/wifi_creds.json`. First arm-A batch failed on WiFi until fixed.
- SomaFM returns `403 Account already in use` on rapid reconnect after an unclean drop (hard reset
  mid-stream) — excluded one trial; fixed with 60 s inter-trial cooldown + clean `stop` before reset.
- The CH340 link re-enumerated `ttyUSB0` ↔ `ttyUSB1` twice mid-session (after playing-session hard
  resets). Driver resolves port by VID:PID per trial. Production DUT reflashed + verified after.

## Verdict

**Confirmation nicety delivered: v2.0.6 buys nothing** (~0.5 KB static, 0 contiguity, Δ@CP2 inside
noise). Keep the v2.3.0 pin. No follow-up warranted; Lane C is closed. TASK-257 → DONE.
