# M-MEMBUDGET — No-PSRAM RAM budget + WebRadio coexistence design space

> Owner: Architect · Status: **SKETCH / design-space (not an ADR yet)** · 2026-06-27
> Feeds: ADR-045 (no-PSRAM playback), TASK-258/EXP-009 (bottom-up ceiling), TASK-259 (player mode-state).
> Purpose: build a first **memory budget** for the no-PSRAM CYD so we can evaluate whether WebRadio can be
> made *deterministically* reliable on the multi-app build (the "Option A-lite" reserved-arena approach)
> instead of either a full headless strip (Option A) or accepting best-effort (Option B).

## Why this doc

EXP-009 settled the hardware question: the no-PSRAM CYD **can** play MP3 radio (both bare and with the full
TFT). The wall is not silicon, not the display — it is **resident footprint + heap contiguity**: at WebRadio
`_play()` our 11-app build has ~60 K free but cannot land the ~41 K audio path because no *contiguous
DMA-capable* span survives the fragmentation of a long-running multi-app heap.

This is a classic fixed-RAM-ceiling, no-MMU problem. The toolkit is well-named:
- **memory budget** (a.k.a. worst-case memory usage) — enumerate every consumer, sum vs the ceiling;
- **memory overlay** — let mutually-exclusive working sets share the same physical RAM (linker overlays / C
  `union`);
- **region / arena allocation** — reserve a contiguous block for a privileged client, lend it cooperatively
  (the OS analog is Linux **CMA**).

The WebRadio idea (reserve ~40 K DMA-capable contiguous RAM; let mutually-exclusive apps borrow it only if
they can free it on demand) is the convergence of all three. This doc inventories the budget and frames the
design space; it does **not** commit an approach — that needs a measurement spike (see §6).

## 1. Memory inventory (corrected)

Total internal SRAM ≈ **320 K** usable heap pool (after ~57.5 K static, per EXP-009). `(m)` = measured
(code constant / EXP-007/009); `(e)` = estimate to be confirmed by the spike.

| Component | Size | Cap required | Contiguous? | Lifetime | Freeable at runtime? |
|---|---|---|---|---|---|
| WiFi / LWIP / mbedTLS system | tens of KB (e) | internal | partial | resident (system) | no |
| **Spotify task stack** | **10 K** (m) | internal | yes | resident from boot | **only by not creating / tearing down the task** — see Q3 |
| **dataTask stack** | **11 K** (webradio_only) / **14 K** (full) (m) | internal | yes | resident from boot | **only by not creating / tearing down** — see Q2 |
| TFT_eSPI | **~0** framebuffer (m), direct-draw | — | — | resident lib, no backbuffer | n/a |
| Per-fetch JSON docs (weather/crypto/stock/teletext) | 1–5 K (m: `WR_DOC_CAP=5120`, `2048`, `1536`…) | any | yes | **transient** (alloc in fetch, freed after) | **yes — already short-lived** |
| Heatmap doc | 2.56 K (m), file-scope `static` | any | yes | **resident** (could be made transient) | not as written — see Q4 |
| WR station table | 30 × `sizeof(WebRadioStation)` (m) | any | yes | resident in dataTask | no (small) |
| Aquarium sprite | `AQ_W×AQ_STRIP_H×1B` (m, 8-bit) | any | yes | per-app-entry | yes — on app exit |
| Marquee sprite (`main.cpp:1584`) | `sprW×8×?` (m, small) | any | yes | transient | yes |
| ~~Album-art JPEG decode~~ | **REMOVED** | — | — | — | — |
| **WebRadio audio path** (only when active) | **~41 K** (m): InBuff ~8 K + Helix 22.7 K + conn | **INTERNAL contiguous** (InBuff+decoder) — see caps note | **yes — the wall** | dynamic (play→stop) | yes |
| └ I2S DMA ring | ~8 K (m: `16×512`) | **DMA-capable** but **512-B chunks** (driver-owned) | per-buffer 512 B only | dynamic | yes |

### Caps refinement (confirmed in code — drives feasibility)

The ~40 K we'd reserve needs only **`MALLOC_CAP_INTERNAL` (8-bit), NOT DMA-capable.** The I2S DMA ring is
allocated by `i2s_driver_install()` (`Audio.cpp:209`, `dma_buf_count=16 × dma_buf_len=512`) as sixteen 512-B
DMA chunks — trivially satisfiable even fragmented, and driver-owned. The two big allocations we redirect
(InBuff `calloc` `Audio.cpp:59`; Helix decoder `__malloc_heap_psram` → `INTERNAL` on no-PSRAM) are plain
internal RAM. **So we reserve from the large internal pool, not the scarce DMA pool** — materially easier than
this sketch's first framing. Verified by PROP-membudget-spike Phase 0.

### Challenge resolved: album-art JPEG is a phantom (Q1 — CLOSED)

Confirmed in code: `cheapYellowLCD.h:9` wraps the JPEG include, the `JPEGDEC jpeg;` object, and
`displayImageUsingFile()` in `#ifndef WINAMP_DISPLAY`. Production defines `-DWINAMP_DISPLAY`
(`platformio.ini:67`) **and** `lib_ignore = JPEGDEC` (line 76). **Net: zero RAM, zero flash for album
art/JPEG in the shipped firmware.** Removed from the budget. (The album-art removal milestone
`M-NOART-remove-album-art.md` already drove this.)

## 2. App × mode cross — what is resident vs reclaimable

The inventory's important shape: **most app memory is transient or app-scoped** (JSON docs, sprites — freed
on app switch). The genuinely *resident, hard-to-free* consumers are a short list.

### 2a. Component × app matrix (roster from `appRegistry.h` — 11 apps)

Shared-resident across **every** app (never varies, omitted from the grid): **TFT_eSPI display** (incl. the
shared **title marquee** — a direct-draw scrolling-text primitive, **0 RAM**, shared by Spotify + WebRadio per
TASK-252/254, *not* a sprite), **app shell/registry**, **WiFi/LWIP/TLS stack**. The grid shows only the
**variable** components — the ones that decide the budget:

| Variable component | Spotify | Clock | Weather | Crypto | Matrix | Life | Settings | Stock | Aquarium | Teletext | WebRadio |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **spotifyTask** 10 K + TLS | ● | — | — | — | — | — | — | — | — | — | — |
| **dataTask** 11–14 K | — | — | ● | ● | — | — | — | ● | — | ● | ◐¹ |
| **WR audio arena** ~40 K int | — | — | — | — | — | — | — | — | — | — | ● |
| heatmap static doc 2.5 K | — | — | — | — | — | — | — | ● | — | — | — |
| JSON fetch doc *(transient)* | — | — | ○ | ○ | — | — | — | ○ | — | ○ | ○ |
| sprite/canvas *(transient)* | — | — | — | — | — | — | — | ○² | ○³ | — | — |

● = resident while app active · ◐ = needed transiently · ○ = transient (alloc/free with the app) · — = none
¹ WebRadio uses dataTask **only to fetch its station list**, then never again — needed briefly, not during play.
² Stock/heatmap narrow-tile rotated label (`main.cpp:1584`) — `createSprite`→`deleteSprite` on the spot.
³ Aquarium strip canvas (`aquariumApp.h`) — created on entry, freed on exit.
(Correction vs the first draft: there is **no "Spotify marquee sprite"** — the scrolling title is the shared
0-RAM direct-draw marquee above; the only real `TFT_eSprite`s belong to Stock/heatmap and Aquarium.)

### 2b. Resident short-list + reclaim

The genuinely *resident, hard-to-free* consumers (everything else is overlay-friendly — comes and goes with
the active app):

| Resident block | Size | Used by | Reclaim mechanism | Reclaim when WebRadio active |
|---|---|---|---|---|
| WiFi/LWIP/TLS system | tens of K | all networked | none (system) | — |
| Spotify task (stack + TLS working set) | 10 K + TLS | **1 app** (Spotify) | tear the task down (Q3) — best candidate | **~10 K + TLS** |
| dataTask (stack) | 11–14 K | 5 apps (fetchers) | create-on-data-app / destroy-on-leave (Q2) — churn risk | **~11–14 K** (after station fetch) |
| Heatmap static doc | 2.5 K | 1 app (Stock) | make transient like the other fetchers (Q4) — trivial | **2.5 K** |

### 2c. The overlay arithmetic (finances the arena — OQ3 / Phase 3)

Sum the mutually-exclusive resident blocks reclaimable **when WebRadio is the active mode**:

```
spotifyTask stack + TLS       ~10 K + TLS working set   (Q3 — single app, high value)
dataTask (post-station-fetch)   11–14 K                 (Q2 — needs fetch-then-teardown sequencing)
heatmap static doc               2.5 K                  (Q4 — trivial)
──────────────────────────────────────────────────────
reclaimable in WebRadio mode  ≈ 24–27 K + TLS
```

So the 40 K arena is **not pure dead weight**: the overlay hands ~24–27 K (+ the TLS working set) back exactly
when WebRadio needs it. **Net steady-state cost to the other apps ≈ ~15 K, not 40 K** — which sharpens Phase 1's
gate from "tolerate losing 40 K" to "tolerate ~15 K net" (PROP-membudget-spike §Phase 1). The budget question
reduces to: can the system tolerate ~15 K net, and does a boot-reserved 40 K *internal* arena guarantee the
~41 K audio path (InBuff + decoder internal; I2S ring driver-owned — see §1 caps refinement).

## 3. Open questions raised against the inventory

> **Design for Q2/Q3/Q4 is now worked out in
> [M-RECLAIM-dynamic-resident](M-RECLAIM-dynamic-resident.md)** (mechanism: lifecycle-scope the three resident
> consumers via the existing `App::init/resume/suspend` hooks; Q3 split into a light TLS-drop vs full
> task-delete; Q4 owned by Stock app-lifetime to preserve its anti-fragmentation rationale). The summaries
> below are retained as the originating rationale.

### Q2 — dataTask: not the OS; can it be dynamic?

**Fact:** dataTask is *our* FreeRTOS task (`dataTaskStorage.cpp:992` `xTaskCreatePinnedToCore`), not part of
esp-idf/FreeRTOS. 11–14 K resident stack. It services all data-fetching apps (weather, crypto, stock,
teletext, heatmap, **and WebRadio station fetch**).

**Make it dynamic (create on entering a data app, delete on leaving)?**
- **Pro:** reclaims 11–14 K when no data app is active.
- **Con (important):** WebRadio *itself* uses dataTask to fetch its station list. So WebRadio mode needs
  dataTask at least transiently → can't simply assume "WebRadio mode ⇒ dataTask gone." Sequencing: fetch
  stations (dataTask up) → tear dataTask down → reserve/own the arena → play. Doable but adds a state
  machine and a window where both coexist.
- **Con:** task create/destroy churn re-introduces fragmentation (the stack is a 11–14 K contiguous alloc;
  repeatedly allocating/freeing it fights the very contiguity we are trying to protect). Mitigate with a
  **static stack buffer** (`xTaskCreateStatic`) so the stack memory is fixed and merely "parked," not
  malloc/free'd.
- **Verdict (sketch):** promising but **second-order** to the arena reservation. Recommend: keep dataTask
  resident for v1; revisit dynamic-dataTask only if the budget spike shows we are short by ~10 K.

### Q3 — Spotify task stack: pros/cons of dynamic

**Fact:** `spotifyTaskStorage.cpp:460`, 10 K stack, created unconditionally at boot, holds the Spotify Web
API HTTPS/TLS working set.

**Tear it down when not in Spotify mode (the natural partner of TASK-259's mode-state)?**
- **Pro:** reclaims 10 K stack **+ the TLS session memory** — the single biggest clean win on the resident
  short-list, and it lands *exactly* when WebRadio mode is active (mutually exclusive by TASK-259).
- **Pro:** aligns with the existing `-DDISABLE_SPOTIFY` experiment (TASK-255) which already proved skipping
  `spotifyTask::begin()` is a single clean guard with null-safe accessors.
- **Con:** re-entering Spotify mode pays a **reconnect/re-auth latency** (token refresh + TLS handshake) on
  every toggle — UX cost. Mitigate: keep the refresh token cached (already persisted); accept a "connecting"
  spinner on toggle-in (ADR-046's dormant-stub bar is already that affordance).
- **Con:** null-safety audit of every unconditional `spotifyTask::` accessor (already enumerated in
  TASK-255's handoff) is a prerequisite so the torn-down state doesn't crash callers.
- **Verdict (sketch):** **the highest-value reclaim**, and it falls out naturally from TASK-259 (mode toggle
  ⇒ tear down the other mode's heavy resources). Strong candidate for v1 of the coexistence design.

### Q4 — Heatmap static doc (2.56 K)

Minor: `s_heatmapDoc(2560)` is file-scope `static` (resident). Could be a transient local like the other
fetchers. Small; list for cleanup, not a budget mover.

## 4. The design space for WebRadio coexistence

Three mechanisms, increasing determinism:

1. **Reserve + JIT-release (no library change).** Hold a ~40 K DMA-internal contiguous block from boot;
   free it the instant before `connecttohost()` so the library's own mallocs land in the guaranteed hole.
   Fragile (timing/placement not guaranteed), but zero fork.
2. **Reserve + library fork (deterministic).** Vendor ESP32-audioI2S; redirect its **two** big allocation
   sites into a fixed-pool allocator over the reserved arena:
   - decoder: the single macro `__malloc_heap_psram` (`mp3_decoder.cpp:1533`) funnels **all 9** Helix
     buffers — one redirect places the whole 22.7 K;
   - input ring: the `calloc(m_buffSize…)` at `Audio.cpp:52/59` — one redirect.
   The dozens of other `malloc()`s are small transient strings → leave on the general heap. **Fork surface ≈
   2 sites.** Maintenance cost is unusually low because **BP-042 already freezes us on v2.3.0** (v3.x bricks
   no-PSRAM), so we were never tracking upstream. Allocator: a **reset-on-stop bump arena** likely suffices
   (decoder allocates-once-per-session / frees-on-stop, and our station filter is MP3-only so no out-of-order
   codec-switch frees); keep a small TLSF-style free-list as the fallback.
3. **Overlay via mode-state (TASK-259) + Q3 teardown.** Make Spotify and WebRadio mutually-exclusive modes;
   on toggle-to-WebRadio, tear down the Spotify task (Q3) and reset borrow-arena (Q2 transient scratch),
   then own the reserved arena. This is the *overlay* that makes the reservation affordable — the arena's RAM
   is "borrowed back" from whatever Spotify mode would have used.

**Recommended sketch:** combine **(2) + (3)** — deterministic placement via the 2-site fork, financed by the
mode-overlay so the ~40 K reservation is not pure dead weight. (1) is the fallback if forking is rejected.

## 5. Budget arithmetic (provisional — to confirm by spike)

```
pool (heap)                         ≈ 320 K (m)
− WiFi/LWIP/TLS system              ≈  ?? K (e)   ← spike must measure
− dataTask stack (resident, v1)         11–14 K (m)
− resident app/static (heatmap, tables) ≈   ?? K (e)
────────────────────────────────────────────────
= free with Spotify mode torn down  ≈  ?? K
reserve DMA-internal arena              40 K  ← must succeed at boot, contiguous
= remaining general heap            ≈  ?? K   ← MUST still run the other ~10 apps
```

The two numbers the spike must produce: **(A)** does a `heap_caps_malloc(40K, MALLOC_CAP_DMA |
MALLOC_CAP_INTERNAL)` succeed at boot and stay contiguous, and **(B)** does the system still run the full app
set with that 40 K removed (with Spotify torn down when in WebRadio mode).

## 6. What must be measured — the spike plan

Full phased plan with kill-gates: **[PROP-membudget-spike](../../rnd/proposals/PROP-membudget-spike.md)**
(runs in-project on the multi-app build, DUT, branch `rnd/membudget`; → EXP-010 / candidate ADR-047). Summary:

| Phase | What | Gate |
|---|---|---|
| **0 — Baseline** (cheap) | caps-split heap probes at boot milestones + CP1/new-CP2; fill the `(e)` rows; confirm audio path is INTERNAL not DMA | none — measurement only |
| **1 — Reservation** (KILL GATE, cheap) | boot-reserve ~40 K `MALLOC_CAP_INTERNAL`; confirm contiguous + full app set still runs 40 K short | fail → **Option A-lite dead, Option B stands, ADR-045 unchanged** — *before* any fork |
| **2 — 2-site fork** (M-effort) | vendor lib, redirect decoder macro + InBuff calloc into a reset-on-stop bump arena; WebRadio holds ≥ 60 s **on multi-app build**, ≥ 3 trials | pass ≥ 90 % → **ADR-047 candidate** |
| **3 — Overlay** (conditional) | only if always-held 40 K too tight (OQ3): TASK-259 mode-state + Q3 `spotifyTask` teardown finances the arena; measure Spotify reconnect latency | — |

The design lever: **measure cheaply, kill cheaply.** Phase 1 settles feasibility with ~one boot alloc + a soak,
so we never sink the Phase-2 fork effort into a reservation that can't exist. A Phase-1+2 PASS reframes the
product decision from "Option B by default" to "Option A-lite is real."

## 7. Open questions / deferred decisions

- **OQ1:** exact arena size — 40 K is the audio-path estimate; the spike refines it (decoder peak + InBuff +
  DMA ring + alignment slack).
- **OQ2:** allocator type — bump-reset-on-stop vs TLSF free-list (depends on whether any mid-session
  out-of-order free occurs; MP3-only filter likely lets bump win).
- **OQ3:** is the 40 K reservation *always* held (simplest, costs the other apps 40 K permanently) or
  borrow-lent via Q2/Q3 overlay (recovers it when WebRadio is off, more code)? Decide after the spike shows
  whether the always-held case still fits.
- **OQ4:** persistence of player mode-state (TASK-259) — RAM-only vs `settings`-persisted across reboot.
- **OQ5:** AppId topology — does WebRadio stop being its own `AppId` (becoming a mode of the player slot)?
  Interacts with the taskbar-excludes-WebRadio invariant (LL-085 / TASK-242). Resolve jointly with TASK-259.

## 8. Links

EXP-009 (`docs/rnd/reports/EXP-009-webradio-bare-rig.md`) · ADR-045 (no-PSRAM playback) · TASK-258 (ceiling)
· TASK-259 (player mode-state — the mutual-exclusion this design leans on) · TASK-255 (parked
`-DDISABLE_SPOTIFY` strip — its null-safety audit feeds Q3) · BP-042 (the v2.3.0 pin that makes the fork
cheap to own).
