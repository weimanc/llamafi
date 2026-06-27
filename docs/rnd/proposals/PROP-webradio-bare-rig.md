# PROP — WebRadio bare-rig: measure the no-PSRAM ceiling bottom-up

> Owner: R&D / Architect · 2026-06-27 · Status: **rev2 — panel-reviewed (R1: 2 PROCEED, 3 NEEDS-CHANGES, all "fold specifics → PROCEED"); this rev folds the blocking items**
> Pivot from TASK-255 Lane A (top-down strip). Feeds TASK-241 / ADR-045 / EXP-009.

## Why pivot (top-down → bottom-up)

EXP-008: our 11-app build leaves ~21 K usable at `_play()` (decoder FAIL); a stack-trim to ~24 K **still**
fails (nominal `usable ≥ demand` is **necessary-not-sufficient** — the input buffer + fragmentation alloc
*after* the measurement point). Stripping our project to headless is a confirmed **~25–30 `#ifdef`-site
M-effort grind for a coin-flip**. The existence proof (EXP-008 Part 2: ESP32-audioI2S runs no-PSRAM radio
in its own examples) says the *bare* footprint works. So measure the ceiling **bottom-up**: build the bare
example on **our actual hardware** as a true control. Cheaper, confound-free, decisive either way, and a
clean home for the Lane C-1 library A/B.

## What it answers

1. **Does the no-PSRAM CYD play MP3 radio at all** (decoder allocates + holds), bare? → settles
   "hardware vs our footprint" definitively.
2. **The realistic budget** any in-project variant must fit under (the **+TFT** config — see below).
3. **(Bonus) clean Lane C-1**: v2.3.0 vs v2.0.6 decoder footprint, A/B with no SD_MMC/build-config confound.

## The bare rig — design

A **separate minimal PlatformIO project living OUTSIDE this repo** — `../webradio-bare/` (a sibling of the
repo root, e.g. `~/proj/webradio-bare/`), **never under `app/`, never in `app/platformio.ini` or
`run/check`** (QM B1 / PM BL-1 / Developer). It has **no nested `.git`** (LL-007) — it's a throwaway rig.
- **Base:** ESP32-audioI2S `examples/Simple_WiFi_Radio`, adapted.
- **Hardware match (Developer-verified):** **remove the example's `setPinout(BCLK,LRC,DOUT)`** (external I2S,
  GPIO25/26/27) and construct **`Audio(/*internalDAC=*/true, I2S_DAC_CHANNEL_LEFT_EN)`** (GPIO26 = SC8002B amp;
  **leave GPIO25 untouched** — reserved for CYD touch; LEFT-only, not BOTH). `setVolume(~8)` (stock clip
  ceiling, TASK-209 — courtesy to the operator; irrelevant to the heap gate). Board `esp32dev`, **`platform =
  espressif32@6.9.0`** (toolchain parity; avoids v3.x 704 KB boot-alloc + GCC-14). **Stock partitions** (our
  custom CSV exists only because the 11-app build overflowed — irrelevant here).
- **Pinned-dep note** in the rig's `platformio.ini`: "ESP32-audioI2S — do NOT bump to v3.x (704 KB boot alloc
  bricks no-PSRAM); v2.0.6 last no-PSRAM line" (QM N1).
- **WiFi:** baked from `Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h` (`HARDCODED_WIFI_SSID/PASS`) into a
  **gitignored local `secrets.h`** — no user setup. **No creds in any committed file, report, or pasted log**
  (LL-002/003); audit the serial capture for creds echo before pasting.
- **Stations:** **2–3 pinned literal HTTP ≤128 kbps MP3 URLs** (reuse ones seen PLAYING on our DUT, so a FAIL
  is unambiguously heap, not a dead host) — not live discovery (R4 / VE N2 / Developer).
- **Serial-dbg rig (~40 lines):** `loop()` line-reader: `heap` (free/min/maxAlloc), `play <n>`, `stop`, +
  the `audio_info()` callback logging the `MP3Decoder ...` lines. **Log the audio-lib version at boot** (self-
  labels the C-1 arm). **Driven by a ~30-line standalone pyserial driver — NOT our `Dut` class** (it checks
  the `.elf` hash against our build and would mismatch; VE N1 / Developer).

## Measurement — the critical correction (R&D B1 / VE B1)

The single `HEAP pre-connect` point is what **misled Step-1**: it fires *before* `connecttohost()`, and the
8 KB input buffer + decoder buffers alloc *inside* it. Capture **three** points, free/min/maxAlloc at each,
**plus the caps dead-block** `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)` (re-probed per build — R&D B4):
- **CP1 — pre-connect:** right before `connecttohost()` (matches our `webRadioApp.h:621` instrument, for
  apples-to-apples vs our 21 K).
- **CP2 — at decoder-init:** in `audio_info()` on the `"MP3Decoder ... initialized"` (or first-frame) line —
  **after** input-buffer + decoder buffers. **This is the gate metric** (the real "can it run" number).
- **CP3 — post-decoder low-water:** `minFreeHeap` after settle.
- **Comparability:** the bare-vs-project comparison must be **instant-matched** (CP1↔CP1, CP2↔CP2). Our
  project currently emits only CP1 → **add a CP2 emit to `webRadioApp.h`** (the `audio_info` hook already
  exists) so the comparison is real, not pre-vs-post (VE B2).

## Two configs — ceiling vs budget (R&D B2)

Stripping the TFT answers a *different* question than the budget. Run **both**:
- **(A) no-TFT** = absolute hardware ceiling → **the KILL test**.
- **(B) +TFT** (our CYD TFT_eSPI driver/framebuffer) = the **realistic budget anchor**, comparable to our
  21 K (our product always carries the framebuffer). Only (B)'s number is a valid in-project budget.

## Decision gate

1. Boot `heap` (parity check: expect ~250–290 K free for the no-PSRAM single-bank layout; if wildly off, the
   rig isn't a valid control — PM BL-2). **Positive control:** confirm the *unmodified* example (with TFT)
   plays first, so a FAIL is attributable to footprint, not the port (R&D N1).
2. `play 0`; **≥ 3 cold-boot trials per pinned station**; record CP1/CP2/CP3 + dead-block; report `usable`
   (= free − dead-block) at **CP2** as min/median across trials (fragmentation is run-to-run); **network-flake
   entries** (no `audio_info` decode line within N s) excluded from the ≥ 60 s-hold denominator (T169 carve-out).
3. **Gate (on config B, +TFT):**
   - **Decoder allocates + holds ≥ 60 s** → **hardware capable; `usable_bare(B)` = the ceiling.** Budget for
     an in-project variant = **`usable_bare(B) − runtime-decoder-demand`, stated as a *bounded* claim with the
     fragmentation-tax caveat** (NOT a clean `− 22.7 K`: 22.7 K is nominal; our path-dependent heap pays a
     fragmentation tax the pristine bare heap doesn't — R&D B3 / QM N2).
   - **Decoder fails even bare (config A *and* B)** → no-PSRAM CYD genuinely can't run this decoder →
     **ADR-045 stands DEFINITIVELY**, milestone closes, strip (TASK-255) abandoned. (Cheap, terminal kill —
     valid only because the positive control + parity check rule out a port artifact.)
4. **Lane C-1 (re-homed):** same project/station/buffer/CP2 capture, swap **only** `lib_deps` v2.3.0 ↔ v2.0.6
   → fresh `.pio/libdeps` → reflash; signal = Δ `usable`@CP2, ≥ 3 trials/arm. Don't swap the core too (that's a
   second variable — EXP-008 trap).

## Risks / threats

- **(R1) Parity:** `espressif32@6.9.0` + internal-DAC + CP-matched instrument, *verified* (PM BL-2) — else the
  number can't be cited against our 21 K.
- **(R2) Bare proves bare:** a PASS proves *hardware/library* works + sets the budget — **not** that our app
  fits (EXP-008 N1 / LL-086). EXP-009 states `usable_bare` as a budget/ceiling, never "WebRadio is viable."
- **(R3) Hygiene:** outside the tree, no nested `.git`, creds never committed/logged, never in `run/check`.
- **(R4) Fragmentation:** bare heap is near-pristine; the budget under-counts our fragmentation tax — stated.

## Task topology (PM — to file when directed)

**TASK-258** (bare rig, P1, active now, → **EXP-009**); **park TASK-255** (`parked-pending-TASK-258` — keep the
branch's V0 harness/`get wrPlaying`/EXP-008 datapoint, reusable on a bare PASS); **re-home TASK-257** (Lane C-1)
as TASK-258 step 4; TASK-256/TASK-241 unchanged. Does NOT touch `rnd/webradio-nopsram` (EXP-008 WIP frozen).

## Out of scope

Display polish, touch, the app shell, any shipping-variant work — all downstream of a bare PASS + a separate
product decision. (Creep guard: do NOT grow the rig toward "our app in miniature.")
