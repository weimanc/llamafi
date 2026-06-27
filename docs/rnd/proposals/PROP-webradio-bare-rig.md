# PROP — WebRadio bare-rig: measure the no-PSRAM ceiling bottom-up

> Owner: R&D / Architect · 2026-06-27 · Status: **plan / proposed — panel review before execution**
> Pivot from TASK-255 Lane A (top-down strip). Feeds TASK-241 / ADR-045 / EXP-008.

## Why pivot (top-down → bottom-up)

EXP-008 established our 11-app build leaves ~21 K usable at `_play()` and a stack-trim to ~24 K **still**
fails the decoder (model refinement: nominal `usable ≥ demand` is necessary-not-sufficient). Stripping our
project down to headless is a confirmed **~25–30 `#ifdef`-site M-effort grind for a coin-flip**. The
**existence proof** (EXP-008 Part 2: ESP32-audioI2S runs no-PSRAM internet radio in its own examples) says
the *bare* footprint works. So measure the ceiling **bottom-up**: build the bare example on **our actual
hardware** and see (a) whether the decoder allocates and (b) the bare `usable` number. This is cheaper,
cleaner (no cascade), and a true control — and it also gives a clean home for the Lane C-1 library A/B that
was confounded inside our build.

## What it answers

1. **Does the no-PSRAM CYD play MP3 radio at all** (decoder allocates), bare? → settles "hardware vs our
   footprint" definitively.
2. **The bare `usable` ceiling** → the budget any in-project variant must fit under (the target for a future
   headless build, if pursued).
3. **(Bonus) clean Lane C-1**: v2.3.0 vs v2.0.6 decoder footprint, A/B in a minimal project with no SD_MMC /
   build-config confound.

## The bare rig — design

A **separate minimal PlatformIO project** (R&D, not our firmware) — `rnd/webradio-bare/` (gitignored from the
main tree, or a sibling repo) so it never touches the shipping build:
- **Base:** ESP32-audioI2S `examples/Simple_WiFi_Radio` (the canonical radio example), **stripped of the
  TFT** — no display (the display is part of the footprint under test; bare = absolute ceiling).
- **Hardware match (critical):** our CYD — **internal DAC, `Audio(/*internalDAC=*/true, I2S_DAC_CHANNEL_LEFT_EN)`
  on GPIO26**, ESP32 (no PSRAM). Board env `esp32dev`/equivalent on **`platform = espressif32@6.9.0`** to match
  our toolchain (GCC 8.x) — so the result is comparable to our build and avoids the v3.x/GCC-14 issue.
- **WiFi:** baked from our project's `Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h`
  (`HARDCODED_WIFI_SSID/PASS`) into a local `secrets.h` — **no user setup** (per instruction; the creds file
  is gitignored, stays out of the R&D project's VCS too).
- **Stations:** a few known **HTTP, ≤128 kbps** MP3 streams (no-PSRAM-friendly; reuse a couple from our
  radio-browser set or the example's list).
- **Serial-dbg rig (bare minimum):** a `loop()` serial reader exposing exactly what the measurement needs:
  - `heap` → prints `free / minfree / maxAlloc` (matches our `get stacks` fields) + computed `usable = free −
    maxAlloc`.
  - `play <n>` → `audio.connecttohost(stations[n])`; logs `HEAP pre-connect free=.. maxAlloc=..` right before
    connect (matching our instrumentation point) and the decoder result.
  - `stop`.
  - `audio_info()` callback → log `MP3Decoder ...` lines so the decoder PASS/FAIL is captured.
  This mirrors our harness's drive model so the same Python driver pattern reads it (no full `Dut` ready-wait
  needed — it's a bare board with no Spotify poll).

## Measurement protocol & decision gate

1. Flash bare rig to the CYD. `heap` at boot (expect ~250–290 K free — vast vs our 107 K).
2. `play 0`; capture `HEAP pre-connect` + decoder result; compute `usable` at `_play()`.
3. **Gate:**
   - **Decoder allocates + holds ≥ 60 s** → **hardware confirmed capable; bare `usable` = the ceiling.** Then
     `usable_bare − 22.7 K` is the headroom a future in-project variant must preserve → quantifies the headless
     target precisely (turns the "coin-flip" into a budget).
   - **Decoder fails even bare** → the no-PSRAM CYD genuinely cannot run this decoder → **ADR-045 stands
     definitively**, and any in-project effort is pointless. (Strong, cheap kill.)
4. **Lane C-1 (optional, same rig):** swap lib v2.3.0 ↔ v2.0.6, re-measure `usable` at decoder-init — clean A/B.

## Risks / threats

- **(R1) Toolchain/board parity:** must use `espressif32@6.9.0` + internal-DAC so the bare number is comparable
  to ours; a different core would confound. Pinned explicitly.
- **(R2) "Bare proves bare":** a bare PASS proves the *hardware/library* works, **not** that our app fits — it
  sets the budget, it does not by itself make our build viable. Frame the claim narrowly (same discipline as
  EXP-008 N1).
- **(R3) Project location / hygiene:** must live outside the shipping build & VCS (no nested git, no stray env
  in `run/check`); creds never committed.
- **(R4) Station availability:** pin known-good HTTP MP3 URLs (not live radio-browser discovery) for
  reproducibility.

## Relationship to existing work

Does **not** modify the shipping firmware or `rnd/webradio-nopsram` (that branch keeps the EXP-008 strip WIP).
Feeds **EXP-009** (new report) and the TASK-241 / ADR-045 verdict. If bare PASSes, it converts the headless
question from "coin-flip" to "fit under `usable_bare` budget"; if bare FAILs, it definitively closes the
milestone (ADR-045 stands).

## Out of scope

Display, touch, the full app shell, any shipping-variant work — all downstream of a bare PASS + a separate
product decision.
