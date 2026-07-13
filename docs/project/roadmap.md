# Roadmap

> Owner: Project Manager
> Purpose: Milestone-level view of planned work. Features/tasks in `feature_inventory.yaml`/`tasks.md` — roadmap groups into delivery chunks.
> Detailed implementation specs live in `docs/architecture/designs/` — roadmap milestones reference them, not embed them.

Scope per ADR-006: keep the Spotify-Diy-Thing baseline architecture; change the UI to a Winamp 2 classic skin; extend touch to drive the full skin's controls; add a synthesised VU.

---

## Completed

### M0 — Baseline hardened

First dev unit working end-to-end; secrets and NFC posture cleaned up before UI work begins.
**Status:** done
**Deps:** —

---

### M1 — API capability spike

Prove every Spotify Web API call the Winamp UI needs round-trips on this DUT before any skin work.
**Status:** done — surfaced TASK-009 (HTTPClient migration) and TASK-010 (audio-features/analysis 403 blocker)
**Deps:** M0

---

### M3 — Winamp display backend

New `winampDisplay.h` rendering baked atlas + layout on the CYD via TFT_eSPI.
**Status:** done (2026-05-07 — DUT visual verify confirmed)
**Deps:** M2

---

### M4 — Position interpolation

Smooth seek-bar / elapsed-time movement between ~1 Hz polls via local millis-based interpolation.
**Status:** done (2026-05-07)
**Deps:** M3

---

### M5 — Full-skin touch controls

Replace three-zone touch map with skin-region hit-testing wired to full Spotify API control surface.
**Status:** done (2026-05-08 — DUT-verified)
**Deps:** M1, M3, M4

---

### M6 — VU meter

Decorative two-bar VU synthesised from Spotify poll envelope; green/yellow/red grading; decays on pause.
**Status:** done (2026-05-09 — ADR-009 option (e))
**Deps:** M5

---

### M-LOG — Logging redesign

Replace ad-hoc Serial prints with esp_log tags/levels, RAM ringbuffer, `/log` pull, mbedTLS decoder, secret redactor.
**Status:** tier 1 shipped 2026-05-07 (ADR-010 + DUT-verified); tier 2/3 deferred
**Deps:** cross-cutting
**Design:** [logging-rethink.md](../architecture/designs/logging-rethink.md)

---

### M-CHROME — Remaining main-window chrome sprites

Bake and render MONOSTER, SHUFREP, title bar, volume/balance sliders from skin BMP sheets.
**Status:** tier 1 done (2026-05-10 — MONOSTER static, SHUFREP dynamic, eject decoration); tier 2 superseded by ADR-014 + TASK-035
**Deps:** M2, M3

---

### M2 — Skin asset pipeline

Host-side bake tool converting the Winamp 2 skin to RGB565 atlas + layout header.
**Status:** done (tier 2 confirmed complete 2026-05-16)
**Deps:** —
**Design:** [M2-skin-asset-pipeline.md](../architecture/designs/M2-skin-asset-pipeline.md)

---

### M-LIST — Top-align UI + playlist panel

Top-align Winamp chrome; render Spotify queue strip in freed area below using `GET /me/player/queue`.
**Status:** done (TASK-020 DUT-verified 2026-05-15; ADR-017)
**Deps:** M3, M-IO

---

### M-PERF — Profiling + targeted optimisation

Instrument loop and hot paths; measure before deciding which optimisations to ship.
**Status:** done (2026-05-08/15 — TASK-029/030/031/033/034/038; async Spotify HTTP loop_max 4191ms→16ms; SPI clock 40 MHz; startWrite/endWrite chrome brackets; touch press-hold state machine)
**Deps:** M-LOG (done), M3, M-IO
**Design:** [M-PERF-profiling.md](../architecture/designs/M-PERF-profiling.md)

---

### M-IO — Decouple display from blocking network calls

Remove cases where Spotify API calls block the super-loop long enough to freeze UI and stale state.
**Status:** done (TASK-019 async poll; TASK-052 tap resets backoff, 2026-05-16)
**Deps:** M3
**Design:** [M-IO-decouple-display-network.md](../architecture/designs/M-IO-decouple-display-network.md)

---

### M-HITZONES — Hit-zone preview PNG

Extend bake tool to emit a semi-transparent hit-zone overlay PNG for touch alignment verification.
**Status:** done (2026-05-16)
**Deps:** M2
**Design:** [M-HITZONES-hitzone-preview.md](../architecture/designs/M-HITZONES-hitzone-preview.md)

---

### M-UI-POLISH — Small UI fidelity improvements

Wire artist name into marquee (`Artist - Title`); restore skin background in VU zero-fill region.
**Status:** done (2026-05-16)
**Deps:** M3, M6
**Design:** [M-UI-POLISH-fidelity.md](../architecture/designs/M-UI-POLISH-fidelity.md)

---

### M-VIS — Visualization area

Tap-cycling visualizer replacing fixed VU: Atlas (baked from Winamp screengrab) → WaveAtlas → VU → Blank.
**Status:** done (2026-05-16/17 — TASK-050a-c + M-VIS-ATLAS TASK-052a-f; tap cycle Atlas→WaveAtlas→VU→Blank; DUT sign-off "looks great"; 52.9% flash)
**Deps:** M6, M-UI-POLISH (TASK-049)
**Design:** [M-VIS-visualization.md](../architecture/designs/M-VIS-visualization.md) · [M-VIS-ATLAS-vis-atlas.md](../architecture/designs/M-VIS-ATLAS-vis-atlas.md)

---

### M-WAVE-ATLAS — Waveform oscilloscope atlas

Extract per-column waveform Y positions from a Winamp screengrab video into a baked C atlas (`gen/wave_atlas.c`); wire as `VIS_WAVE_ATLAS` in the firmware tap-cycle (Atlas → WaveAtlas → VU → Blank). Freeze-fix applied to lead-in frames.

**Status:** done (2026-05-17 — TASK-053/055a–d; ccc1bde; DUT-verified)
**Deps:** M-VIS (tickWave firmware in tree), M-VIS-ATLAS (bake pipeline pattern)
**Design:** [M-WAVE-ATLAS-wave-atlas.md](../architecture/designs/M-WAVE-ATLAS-wave-atlas.md) · [M-WAVE-ATLAS-firmware-playback.md](../architecture/designs/M-WAVE-ATLAS-firmware-playback.md)

---

### M-LIST-v2 — Winamp PLEDIT playlist skin

Replace plain row list with proper PLEDIT skin: title bar, bottom bar, 5 rows, MM:SS durations, total time.
**Status:** done (2026-05-15 — TASK-047a-d; PLEDIT chrome with title/bottom bars, 5 rows, Font 1, MM:SS durations, total-time strip; ADR-018)
**Deps:** M-LIST, M2, M3
**Design:** [M-LIST-v2-pledit-skin.md](../architecture/designs/M-LIST-v2-pledit-skin.md)

---

### M-LOG2 — On-screen log overlay

Full-panel log terminal behind the Winamp chrome; newest 15 lines visible in PLEDIT area.
**Status:** done (TASK-018 DUT-verified 2026-05-07)
**Deps:** M-LOG (done), M3
**Design:** [M-LOG2-screen-log-overlay.md](../architecture/designs/M-LOG2-screen-log-overlay.md)

---

### M-SERIALDBG — Serial debug command expansion + touch injection

Expand `handleSerialCommands()` beyond `reconnect` with a richer debug/test command surface. Primary deliverable: `tap X Y` and `drag X1 Y1 X2 Y2 STEPS` commands that inject synthetic touch events into the same `hitTest*` / `enqueue` path as physical screen presses. Secondary deliverables: `info` (state snapshot), `status` (hit-zone dump).

All responses are JSON lines. Host scripts use `json.loads(line)` — check `ok`, `hit`, `action` fields. Drag emits the same intermediate log lines that physical drag already produces.

This unlocks regression-scriptable coverage for T052–T054, T074, T075, T048, and nine new tests (T076–T085, T089) that are impossible to write without coordinate-precise, repeatable input injection.

**Status:** done (2026-05-17/18 — TASK-056a-n + TASK-056k; tap/drag injection, get/set/info/help, IDebugExportable interface; VE suite T076–T096 22 PASS / 0 FAIL)
**Deps:** M5 (touch hit-test path in tree), M-LOG (structured serial output)
**Design:** [M-SERIALDBG-serial-debug-framework.md](../architecture/designs/M-SERIALDBG-serial-debug-framework.md) · [ADR-021](../architecture/decisions/ADR-021.md)

---

### M-SYNC — DUT–Spotify state synchronization

Field-level lag bounds + stale-state checks between Spotify's authoritative state and DUT chrome render. 14 tests (T097–T110, TSYNC-1 through -14). Three lag-bound tiers formalized in ADR-022.
**Status:** done (2026-05-17/18 — TASK-057/058/061; spotify_state.py + spotify_drive.py + tsync_diff.py harness; heartbeat fields last_poll_age_ms + next_poll_in_ms; VE suite 12 PASS / 0 FAIL / 3 SKIP on DUT)
**Deps:** M-SERIALDBG, M-IO, M-LOG

---

### M-DRIFT — Operational state-drift surfacing

Runtime counterpart to M-SYNC. Two surfaces: (a) `last_render_age_ms` heartbeat field; (b) in-chrome staleness indicator when `last_poll_age_ms > N_STALE_MS`. Threshold + indicator form in ADR-023.
**Status:** done (2026-05-17 — TASK-059/060; last_render_age_ms heartbeat field + g_lastRenderMs; 4×4 amber pip at (268,1) when age > N_STALE_MS=15000; ADR-023 accepted)
**Deps:** M-SYNC (TASK-058 shared), M-CONN (overlay pattern)

---

### M7 — Polish / open questions

Resolve remaining open questions (TLS CA strategy, seek-drag, speculative poll, audio-analysis cache) once system exercised end-to-end.
**Status:** done (2026-05-16 — ADR-019 TLS CA, ADR-020 speculative poll, seek-drag visual resolved in design doc; audio-analysis already closed ADR-009)
**Deps:** M6 and all prior milestones
**Design:** [M7-open-questions.md](../architecture/designs/M7-open-questions.md)

---

### M-CONN — Connection health UI + TLS recovery controls

Inactive title bars on disconnect; serial `reconnect` command; Winamp logo tap → TLS reset.
**Status:** done (2026-05-22 — all exit criteria met). F1: DNS-induced consecutive=2 → repaintChrome fired SKIN_TITLEBAR_INACTIVE (render_age 60003→17251ms). F2: reconnect JSON ack, TLS reset, 10/10 polls. F3: logo tap → TLS reset + force poll logged; 2s cooldown correct; visual redraw confirmed. Also fixed TASK-073 crash (strcmp nullptr on track start).
**Deps:** M-IO (TASK-052), M-CHROME (done), M3
**Design:** [M-CONN-connection-health.md](../architecture/designs/M-CONN-connection-health.md)

---

### M-CONN-HTTP11 — HTTP/1.1 keep-alive + dechunker

Promote the `api.spotify.com` connection to HTTP/1.1 persistent keep-alive; add a chunked-transfer dechunker so `getQueue()` responses can stream without buffering the full body.

**Status:** done (2026-05-21 — TASK-062/063; 943ccf3; DUT-verified)
**Deps:** M-IO (async Spotify task), M-CONN (connection health)
**Design:** [M-CONN-http11-keepalive.md](../architecture/designs/M-CONN-http11-keepalive.md)

---

### M-NOART — Remove album-art path and JPEG decoder

The `WinampDisplay` renderer does not use album art; the CYD panel has no space for it.
The inherited JPEG decode path (`JPEGDEC` library, `getImage()`, `processImageInfo()`) is
dead weight: it pulls in ~40 KB of JPEG decoder, makes CDN connections that clobber the
`api.spotify.com` keep-alive session, and crashes with a null `pDraw` on some track
transitions (`JPEGPutMCU22 LoadProhibited` Guru Meditation, confirmed 2026-05-20).

Work:
- Gate the entire album-art path in `cheapYellowLCD.h` behind `#ifndef WINAMP_DISPLAY`
  (or a dedicated `ALBUM_ART_ENABLED` flag).
- Remove `JPEGDEC` from `platformio.ini` `lib_deps` under `cyd2usb_winamp`.
- Drop the `processImageInfo` override workaround in `winampDisplay.h` (no longer needed
  once the path is compiled out).
- Confirm the winamp build clean-compiles without the decoder and no longer crashes on
  track change.

**Status:** done (2026-05-21 — commit 1411a3e; `lib_ignore = JPEGDEC` in winamp env, album-art path gated behind `#ifndef WINAMP_DISPLAY`, `processImageInfo` override removed)
**Deps:** M3 (winamp renderer in tree)
**Design:** [M-NOART-remove-album-art.md](../architecture/designs/M-NOART-remove-album-art.md)

---

### M-LIST-v3 — Playlist interactivity

Selected-row highlight tracking, virtual scroll (20 items), live scrollbar thumb.
**Status:** done (2026-05-23 — TASK-051a-j; optimistic highlight, 20-item queue, scrollOffset + sliced rows, swipe gesture, live thumb sprite, auto-reset on track change, row format "N. Artist - Title… M:SS", songsSeen counter, scrollbar direct drag; DUT confirmed)
**Deps:** M-LIST-v2, TASK-021 (tap-to-play)
**Design:** [M-LIST-v3-playlist-interactivity.md](../architecture/designs/M-LIST-v3-playlist-interactivity.md)

---

### M-SHELL-LAYOUT — Shell geometry single source of truth

Establish `gen/shell_layout.h` as the single authoritative definition of taskbar
geometry and style constants (TASKBAR_X, TASKBAR_W, TASKBAR_SLOT_H, indicator
colour, separator colour). The interactive preview tool (`preview_layout.py`)
emits this header on export; firmware `#include`s it; Python preview tools parse
it via a shared helper. Eliminates the drift risk between firmware and host tooling
that would otherwise arise from M-MULTIAPP's taskbar constants.

Work:
1. Add `parse_shell_layout()` helper to `bake_skin.py`.
2. Add `--export` path to `preview_layout.py` that writes `gen/shell_layout.h`.
3. Update firmware to `#include "gen/shell_layout.h"` and remove any literal taskbar constants.
4. Fix `preview_vis.py:58` to parse `gen/skin_layout.h` instead of hardcoding `WINDOW_W=275`.
5. VE: T125–T127 host-side test suite.

**Status:** done (2026-05-24 — TASK-068/069/070/071/072; coords.py originX-aware helpers, bake_skin gaps 2+3, parse_shell_layout helper, T125–T127 pass; aesthetics deferred)
**Deps:** M-MULTIAPP (interactive preview tool, step 1)
**Design:** [M-MULTIAPP/shell-layout.md](../architecture/designs/M-MULTIAPP/shell-layout.md)

---

### M-RESTRUCTURE — Project source ownership split

Decouple our winamp-app code from the upstream `SpotifyDiyThing` entrypoint.
The upstream `.ino` becomes our shell; winamp code moves into named subdirectories;
a `WinampState`/`SpotifyAppState` struct becomes the interface between the Spotify
data layer and the renderer. No behaviour change — firmware output is identical
before and after. Prerequisite for M-MULTIAPP because it makes the `originX=0`
shift a one-liner in the shell rather than a global variable to audit.

Work (per `docs/architecture/designs/M-MULTIAPP/source-ownership.md`):
1. Create `winamp/` subdir; move `winampDisplay.h`, `vuMeter.h`
2. Add `appShell.h` per app-lifecycle.md spec
3. Add `taskbar/taskbar.h` per taskbar.md spec
4. Rewrite `SpotifyDiyThing.ino` as our shell (upstream files included, not modified)
5. Apply `originX=0` shift — now a one-line rect change in the shell

Gate: `check_build.sh` passes after each step (BP-008). Firmware behaviour
verified unchanged on DUT after step 4 before proceeding to step 5.

**Status:** done (2026-05-24) — TASK-083 complete; commits d62c9f4, 709027b
**Deps:** M-NOART (done)
**Blocks:** M-MULTIAPP step 2 onward ✓ unblocked
**Design:** [M-MULTIAPP/source-ownership.md](../architecture/designs/M-MULTIAPP/source-ownership.md)

---

### M-MULTIAPP — Multi-app shell with icon taskbar

Add a persistent 45 px icon-only taskbar on the right edge (x: 275..319).
Shift the Winamp window to originX=0. Six apps: Spotify/Winamp, Clock,
Weather, Crypto, Matrix rain, Game of Life. Apps do not run concurrently —
the taskbar is an always-present input layer that triggers state-preserving
app switches. Network apps (Weather, Crypto) use a shared `dataTask` on the
same FreeRTOS pattern as `spotifyTask`.

Work sequence:
1. Preview tooling — extend `bake_skin.py` to render full 320×240 layout
   composite with taskbar variants; resolve icon style and active indicator.
2. Layout — shift `originX = 0`; constrain app canvas to x: 0..274.
3. Taskbar — `renderTaskbar()` + first-priority hit-test in `checkForInput()`.
4. App shell — `appShell.h` with `AppId` enum, state structs, `switchApp()`.
5. Non-network apps — Clock, Matrix, GoL tick + input handlers.
6. Network apps — `dataTask` + Weather + Crypto fetch/render.

**Status:** done (2026-05-25 — all 6 apps wired, DUT-verified, VE test suites written)
- TASK-087: taskbar + app-shell + Clock — DUT verified 2026-05-24
- TASK-090: App ABC, SpotifyApp + ClockApp, B1–B4 fixed, T_BI_01–04 passing — 2026-05-25
- TASK-092: ADR-027 TFT shared-state hotfix — 2026-05-25
- TASK-093: MatrixApp — DUT verified 2026-05-25
- TASK-094: LifeApp — DUT verified 2026-05-25
- TASK-095/096: WeatherApp + CryptoApp + dataTask + full-canvas fix — DUT verified 2026-05-25
- TASK-097–100: VE suites T_MA/T_GOL/T_WX/T_CX/T_X07 (18 automated + 9 manual-planned) — 2026-05-25
**Deps:** M3 (done), M-NOART (done), M-RESTRUCTURE (gates step 2), M-SHELL-LAYOUT (taskbar constants header, gates steps 3–4)
**Design:** [M-MULTIAPP/overview.md](../architecture/designs/M-MULTIAPP/overview.md)

---

### M-APP-REGISTRY — Single-source app registry

X-macro table (`appRegistry.h`) as the single canonical definition of app order, taskbar icons, and configurability. Six previously-scattered sites (appShell, taskbar, main, appsSection, Python test harness) are now derived from one file via `gen_app_registry.py`. ADR-041.

**Status:** done (2026-06-06 — 801f378)
**Deps:** M-MULTIAPP (AppId enum, taskbar, dispatch table in tree)
**Design:** [M-APP-REGISTRY.md](../architecture/designs/M-APP-REGISTRY.md)

---

### M-STOCK-POC — StockApp list, chart, and heatmap

Standalone stock market viewer app: ticker list (8 symbols, price + change%), chart detail (line graph, 4 range tabs), and heatmap treemap view (market sectors, colour-coded by change%). TLS via ADR-029. Integrated into multi-app shell.

**Status:** done (2026-05-29 — TASK-109 `27bd86b`; TASK-119 heatmap `cf98180`; VE suites T170–T221; TASK-138 TLS yield reliability 3/3 PASS)
**Design:** `docs/architecture/designs/M-MULTIAPP/stock.md` · `stock-list.md` · `stock-chart.md` · ADR-036/037

---

### M-TOUCH-UX — Touch UX layer (hitbox, debounce, busy indicator)

Formal touch event pipeline: `Rect` hitbox primitive, debounce activation gate (cool-down), shell-busy amber indicator, `hasPendingAsync()` ABC contract. Three implementation phases: foundation, shell infrastructure, app integration.

**Status:** done (2026-05-31 — TASK-114–118; phases 1–3 shipped; VE T-BUSY/T-CDWN pass; retrospective LL-044/045)
**Design:** `docs/architecture/designs/M-TOUCH-UX.md` · ADR-035

---

## Outstanding

### M-DATATASK-PROGRESS — Live dataTask progress indicators for long-running fetches

Add volatile per-step progress atoms to dataTask functions that run multi-step HTTP
sequences on Core 0. Expose via global serialdbg `get` commands so tests (and operators)
can observe in-progress state on Core 1 without waiting for a committed result.

Phase 1: `fetchStockQuote()` — `stockQuoteProgress` (int8_t, -1=idle, 0–7=ticker index).
Turns T170 timeout failures from "quoteOkCount did not advance" into "stuck on ticker N (SYM)".

Phase 2: extended to `fetchWeather()`, `fetchCrypto()`, `fetchStockChart()`, `fetchStockChartBySym()` — `weatherFetchPhase`, `cryptoFetchPhase`, `stockChartProgress` (0=TLS, 1=GET, 2=parse, -1=idle).

No timeout introduced — diagnostic only. No queue restructuring — orthogonal to any
future per-ticker queue-split refactor.

**Status:** done (2026-06-12 — TASK-173/174; commit 95d6a93; T170/T_WX_05/T_CX_05 PASS on DUT)  
**Design:** [M-DATATASK-PROGRESS.md](../architecture/designs/M-DATATASK-PROGRESS.md)  
**Owner:** Developer  
**Priority:** P2  
**Cross-feature:** X015 (dataTask Core 0 ↔ serialdbg Core 1 observability)

---

### M-SETTINGS-APP-WIRE — Wire per-app settings to app behaviour

Connect the five per-app setting groups stored in `g_settings` to the apps that own
them. Currently the Settings UI saves preferences (Matrix color/speed, Life speed/colors,
Aquarium fish/speed, Stock tickers/default view, Crypto coins/currency) but every app
ignores `g_settings` and uses hardcoded defaults.

Scope: Matrix, Life, Aquarium, Stock — pull-on-resume model. Crypto deferred (coin
symbol→CoinGeckoId mapping + dynamic URL required; separate milestone M-SETTINGS-CRYPTO).
Stock also requires a `configureStockTickers()` path to `dataTaskStorage.cpp` so the
network layer fetches the user-configured symbols.

**Status:** done (2026-06-12 — TASK-172; W1–W9 all shipped; T-SET-01..08 PASS on DUT)  
**Design:** [M-SETTINGS-APP-WIRE.md](../architecture/designs/M-SETTINGS-APP-WIRE.md)  
**ADR:** [ADR-043](../architecture/decisions/ADR-043.md) (accepted)  
**Deps:** M-SETTINGS-001 (done)

---

### M-CLOCK-STYLES — Clock style variants + MM position fix

Fix the blinking-colon MM spacing jump and add three new clock face styles
(Flip, Nixie Tube, VFD) selectable at runtime via Settings > Applications > Clock.

Work:
0. **Concept phase** — `preview_clock.py` host-side pygame renderer; iterate all
   four styles interactively (colours, glow, segment geometry, flip timing) before
   any firmware is written; record approved constants in design doc. Human sign-off
   required before Phase 3 begins.
1. **Bug fix** ✓ done (77de8d6) — split digit rendering: HH at MR_DATUM x=129, MM at ML_DATUM x=145, colon drawn/erased at MC_DATUM x=137. MM no longer jumps on blink toggle.
2. **`ClockStyle` enum + storage** — add `enum class ClockStyle : uint8_t` and
   `ClockStyle clockStyle` to `AppSettings`; default `Digital`; persist via `settings.json`.
3. **`ClockApp` style dispatch** — replace the flat `drawTime()` with a virtual-style
   dispatch on `g_settings.clockStyle`; each renderer (`drawDigital`, `drawFlip`,
   `drawNixie`, `drawVFD`) lives in a self-contained private method block.
4. **Sub-second tick** — change tick gate from 1 000 ms to 100 ms while a flip
   animation is in-flight; otherwise 1 000 ms (no regression for non-Flip styles).
5. **Flip renderer** — per-digit `FlipState` struct; 5-frame split-card animation;
   Phase 0 approved palette.
6. **Nixie renderer** — per-digit oval "tube" chrome; outer/inner glow layers;
   Phase 0 approved colours.
7. **VFD renderer** — 7-segment primitives (H-bar + V-bar); active / inactive
   segment colours; Phase 0 approved geometry.
8. **Settings wiring** — `appRegistry.h`: Clock `configurable=1`; re-run
   `gen_app_registry.py`; add `_repaintClock` / `_cycleClock` to `appsSection.h`.
9. **VE suite** — T_CLK_01–14 (style cycle, blink stability, flip animation,
   Nixie/VFD bounds, settings persistence, app-switch style preservation).

**Status:** done (2026-06-13 — TASK-193 + T_CLK_01–14 14/14 PASS); visual DUT review deferred (C1/C4/C5/C6/C8)  
**Design:** [M-CLOCK-STYLES.md](../architecture/designs/M-CLOCK-STYLES.md)  
**Deps:** M-SETTINGS-001 (done), M-APP-REGISTRY (done)

---

### M-SETTINGS-STUB — Settings app navigation shell

Implement the `SettingsApp` navigation skeleton: category list (6 entries with chevron rows),
header bar with `< back`, 3-level back logic (appSubmenu → section → previous app via
`g_previousAppId`), stub placeholder for each section. No live section implementations.
Applications section supports 2-level drill (app list → per-app stub rows).

Full per-section implementations (WiFi flow, display, LED, touch-cal, time, Application
sub-menus with SPIFFS persistence) are **not** in scope here — each will be a separate
milestone once the stub is verified.

**Status:** done (2026-06-05 — TASK-141/142; check_build.sh 4/4; T-SET-01..08 6/6 PASS; DUT-141d visual all pass)
- TASK-141: SettingsApp class, constants, g_previousAppId tracking, SERIAL_DEBUG get settingsSection/settingsAppSubmenu
- TASK-142: VE suite T-SET-01..08 written + executed; also fixed cmdTap bug (non-Spotify apps beyond Stock not dispatched to handleInput)
**Design:** [M-MULTIAPP/settings.md](../architecture/designs/M-MULTIAPP/settings.md)
**Deps:** M-MULTIAPP (done), M-TASKBAR-SCROLL (done)

---

### M-SETTINGS-001 — Settings section implementations + new-items

All 6 live settings section implementations (WiFi, Time & Location, Touch Calibration, Display, LED, Applications) plus a second feature batch: cancel button with snapshot-restore, CalibrationFlow back-tap cancel and history display, KeyboardWidget cancel button, TouchDebugOverlay, DisplaySection Serial.printf guard.

**Status:** done (2026-06-06/07 — fd93679, c07c903)
- WiFi, Time, Touch Cal, Display, LED, Apps sections: implemented; DUT-verified (2026-06-06)
- Cancel button + snapshot-restore: 7/7 serial tests PASS (2026-06-07)
- Cal back-tap cancel: T-CAL-BTAP-01/06 PASS; T-02..05 deferred (require physical corner taps)
- Cal history display: implemented; visual DUT check deferred
- KeyboardWidget ACT_CANCEL: implemented; BLOCKED-PHASE2 for full VE
- TouchDebugOverlay: implemented; visual DUT check deferred
- DisplaySection map() bug fixed: guard `ldrHigh > ldrLow` (c07c903)
- Design-vs-impl audit: 6/6 features strong-match spec (2026-06-07)
- Open polish: TASK-150 (backlight LEDC), TASK-152/154 (visual confirm), TASK-153 (scrollbar drag), TASK-155 (KB highlight)
**Design:** [M-MULTIAPP/settings.md](../architecture/designs/M-MULTIAPP/settings.md) and sibling design docs
**VE suite:** [settings-001-new-items.md](../verification/regression_suite/settings-001-new-items.md)
**Deps:** M-SETTINGS-STUB (done)

---

### M-SETTINGS-WIFI-P2 — WiFi section Phase 2: on-device connect + remove WiFiManager

Replace the WiFiManager + DoubleResetDetector boot flow with a native NVS/SPIFFS reconnect
sequence and an on-device connect UI in WifiSection (Keyboard → Connecting → Result states).
WiFiManager and DoubleResetDetector libs removed from build.

**Status:** done — build PASS + DUT verified 2026-06-11 (TASK-168). T-WIFI-P2-01..06 all passing.
- Boot sequence: NVS reconnect → SPIFFS wifi_creds.json → open WiFi settings
- WifiSection: Keyboard/Connecting/Result states + PATCH-004 (spotifyDisplay.h, cheapYellowLCD.h)
- WifiManagerHandler.h retired; PATCH-003 superseded
**Deps:** M-SETTINGS-001 (done), M-SETUP-WIZARD (done)

---

### M-TOUCH-CAPTURE — Slider input capture

Pointer capture for all four interactive sliders (POSBAR, VOLUME, PLEDIT scrollbar strip,
PLEDIT content swipe). Mid-gesture drift outside a hitbox no longer drops events or mis-routes
to another handler. POSBAR commits seek on Release from a cached position (not release coords).

**Status:** done (2026-06-05 — TASK-101 `b253eb8`; VE T149/T150/T151/T153/T154 PASS; T152 SKIP [CONDITIONAL] queue < 6)
**Design:** [M-TOUCH-CAPTURE-slider-input-capture.md](../architecture/designs/M-TOUCH-CAPTURE-slider-input-capture.md)

---

### M-LIST-v4 — Velocity-scroll PLEDIT

Replace the commit-on-release PLEDIT swipe gesture with a velocity-joystick model: finger
offset from the press anchor maps to scroll speed (rows/s). Holding the finger still at a
nonzero offset scrolls continuously. Dead-zone-only tap discrimination. Integer `scrollOffset`
preserved. Architecture pre-wired for Phase 2 fling momentum.

**Status:** done (2026-05-25 — TASK-103 `abf4722`; VE T155–T161 TASK-104 `aaf8009`)
**ADR:** ADR-030 (accepted 2026-05-25)
**Design:** [M-LIST-v4-velocity-scroll.md](../architecture/designs/M-LIST-v4-velocity-scroll.md)
**VE review:** [velocity-scroll-ve-review.md](../verification/regression_suite/velocity-scroll-ve-review.md)

---

### M-TASKBAR-SCROLL — Scrolling taskbar (wrap-around, N > 6 apps)

The taskbar currently renders exactly 6 apps in 6 fixed slots. Settings (AppId 6) and
Stock (AppId 7) are already designed; further apps may follow. This milestone extends the
taskbar to support an arbitrary number of registered apps by making the 6 visible slots a
scrollable view over the full app list, with wrap-around.

Scroll model: finger swipe up/down on the taskbar strip scrolls the visible window.
Tap discrimination reuses the PLEDIT dead-zone pattern (`SCROLL_DEAD_ZONE_PX`).
Velocity/inertia is **not** needed for a ≤12-item list — steps are driven directly from
finger displacement. Wrap-around is free via modulo: `(scrollOffset + i) % totalApps`.
A 2 px scroll-position indicator column (deferred to impl) shows current position.

Work:
1. Add `_tbScrollOffset`, `_tbDragStartY`, `_tbScrollAccum` to `WinampDisplay` private section.
2. Add `D_TASKBAR_SCROLL` to `DragState` enum.
3. Update `checkForInput()` taskbar first-pass: Press → `D_TASKBAR_SCROLL`; Move → step accumulation; Up → tap-vs-scroll (3× dead zone threshold), with wrap-around modulo on scroll.
4. Update `renderTaskbar()` signature to `(tft, activeApp, scrollOffset, totalApps)`; inner loop `appIdx = (scrollOffset + i) % totalApps`.
5. Wire `_tbScrollOffset` into all `renderTaskbar()` call sites.
6. VE: T162–T168 (tap-vs-scroll discrimination, scrollOffset increment/decrement, wrap-around, active indicator follows appIdx).

Stub registration of Settings (AppId 6) and Stock (AppId 7) is included in TASK-105a,
bringing `AppId::COUNT` to 8 immediately so the scroll is visually exercisable on DUT
without waiting for full app implementations.

**Status:** done (2026-05-26 — TASK-105 `d205ad0`; VE T162–T166 PASS, TASK-106 `ee43831`)
**Design:** [M-MULTIAPP/taskbar.md §Scroll model](../architecture/designs/M-MULTIAPP/taskbar.md)
**Deps:** M-MULTIAPP (done), M-TOUCH-CAPTURE (done)

---

### M-AQUARIUM — ASCII Aquarium app

Port ASCII Aquarium into the multi-app shell as a full-canvas (275×240) animated demoscene: fish, bubbles, seaweed, food flakes. Dynamic heap-sized sprite; full-height canvas (sand strip removed); hybrid strip renderer halves heap cost (33 KB vs 66 KB).

**Status:** done (2026-05-26/29 — 276bbba, 2e8c705, 4d61760; DUT-verified)
**Deps:** M-MULTIAPP (app shell in tree)
**Design:** [M-AQUARIUM/overview.md](../architecture/designs/M-AQUARIUM/overview.md) · [M-AQUARIUM/fullheight.md](../architecture/designs/M-AQUARIUM/fullheight.md) · [M-AQUARIUM/hybrid-strip.md](../architecture/designs/M-AQUARIUM/hybrid-strip.md)

---

### M-AQUARIUM-DEMOSCENE — Aquarium demoscene optimisations

Apply classic "never store what you can compute" and "cache only the minimum repeating
unit" techniques to `AquariumApp`. Motivated by the RAM audit (2026-05-28) which found
the app contributing ~24 KB to `.bss` via arrays that are either over-cached, tiled
beyond their natural period, or reconstructible from data already available at draw time.

Work (all changes local to `aquariumApp.h`):
1. **Gradient x-tile** — replace `_gradientBandCache[275×36]` (19,800 B) with
   `_gradTile[36][32]` (2,304 B). The Bayer dither pattern repeats every 32 px in x;
   render each row by tiling the 32-pixel strip via a 550 B stack buffer. Alternatively,
   evaluate scanline-only render (zero cache) on DUT — 8-bit palette quantisation may
   make dithering visually redundant. **Supersedes ADR-033 heap migration.**
2. **Mirror fish on the fly** — drop `_fishMirroredLeft[12][28]` (336 B); apply
   `_mirrorBracket()` inline during draw using the existing right-string in reverse.
3. **Glyph offsets → per-char widths** — replace `_fishGlyphOffsetRight/Left[12][28]`
   (1,344 B) with `_fishCharWidthRight/Left[12][28]` (672 B); accumulate x position
   incrementally during draw.
4. **Seaweed root arrays → inline + flash** — `_seaweedBaseX` and `_seaweedAmp` are
   two-line formulas of `i`; compute inline. `_seaweedHeightNoise` → `static const`
   table in flash (`.rodata`). Drop `_seaweedCached` flag.
5. **Seaweed phase hoisting** — hoist the time-constant sin phase component per root
   out of `_swayPoint`; eliminates ~1,200 redundant float ops/frame (CPU only).
6. **Fish struct packing** — narrow `type` (int→uint8_t), `speed` (float→uint8_t),
   `visualWidth` (int→uint8_t); reorder fields to eliminate padding. ~192 B across pool.

Expected `.bss` reduction: **~18.7 KB**. Combined with M-AQUARIUM-OPT pool right-sizing,
total aquarium `.bss` drops from ~24 KB to ~2.6 KB. No heap lifecycle changes needed.

**Status:** done (2026-05-28/29 — TASK-132–137; P1–P5 + CPU-opt VE ADR-038 accepted)
- P1 gradient x-tile: `f839a61` (~17.5 KB .bss freed)
- P2 seaweed inline + phase hoisting: `78462b9`
- P3 fish glyph subsystem: `e975f03`
- P4 fish struct packing: `59d6b8e`
- P5 pool right-sizing: `4d61760`
- ADR-033 (gradient heap migration) superseded by P1.
**Design:** [M-AQUARIUM/demoscene-opt.md](../architecture/designs/M-AQUARIUM/demoscene-opt.md)
**Deps:** M-AQUARIUM (done)

---

### M-AQUARIUM-OPT — Aquarium static-RAM reduction

Reduce `AquariumApp`'s contribution to `.bss` by ~22 KB and improve heap headroom for TLS
handshakes when the aquarium is active or suspended.

Identified in RAM audit 2026-05-28: `AquariumApp` is the single largest static-RAM consumer
in the firmware outside of system libraries, driven by two issues:
(a) `_gradientBandCache[275×36]` (19.3 KB) lives permanently in `.bss` even when the app is
suspended; and (b) pool arrays `_fishPool[48]` and `_bubbles[50]` are oversized relative to the
active count constants (`AQ_FISH_COUNT=16`, `AQ_BUBBLE_COUNT=10`), wasting ~3 KB in `.bss`.

Work:
1. **Heap-migrate gradient cache** (ADR-033): replace `uint16_t _gradientBandCache[…]` member
   array with a `uint16_t* _gradientBandCache = nullptr` pointer. Allocate on `init()`/`resume()`
   alongside the sprite; free on `suspend()`. Cache-invalid flag `_gradientBandCached` becomes
   the null check. Net: 19.3 KB leaves `.bss`; on suspend, that heap is available for mbedTLS.
2. **Right-size pool arrays**: reduce `AQ_FISH_POOL_MAX` from 48 → 16 (`AQ_FISH_COUNT`) and
   `AQ_BUBBLE_POOL_MAX` from 50 → 10 (`AQ_BUBBLE_COUNT`). The upstream over-allocated these
   for a settings-UI that was dropped (ADR-031). Net: ~3 KB leaves `.bss`.
3. **Update `overview.md`** Open Question #2 as resolved.
4. **VE**: verify fish count, bubble count, and gradient render on DUT after changes.

Expected outcome: `.bss` reduced by ~22 KB; heap headroom when aquarium is suspended increases
from ~100 KB to ~122 KB, giving mbedTLS single-handshake peaks (~40 KB) comfortable margin.
ADR-032 heap arbitration (SSL yield protocol) is independent and may proceed in parallel.

**Status:** superseded by M-AQUARIUM-DEMOSCENE — P1 (gradient x-tile) and P5 (pool right-sizing) delivered the same .bss reductions without heap lifecycle complexity. ADR-033 status: superseded.
**ADR:** ADR-033 (superseded)
**Design:** [M-AQUARIUM/memory-opt.md](../architecture/designs/M-AQUARIUM/memory-opt.md)
**Deps:** M-AQUARIUM (done — aquariumApp.h in tree)

---

### M-DATATASK-STREAM-PARSE — Replace buffered HTTP parse with streaming across all dataTask fetchers

All four fetch functions in `dataTaskStorage.cpp` (weather, crypto, stock quote, stock chart) call `http.getString()` before passing to `deserializeJson`. This allocates the full response body as a heap `String` before the ArduinoJson doc — peak heap pressure is `String + DynamicJsonDocument` simultaneously. On a fragmented heap, the String allocation fails or truncates, and ArduinoJson returns a parse error → `fetchFailed=1 / errorCode=-99`. Observed on DUT during rapid StockApp range-tab cycling.

Fix:
1. Replace `deserializeJson(doc, http.getString())` with `deserializeJson(doc, http.getStream())` in all four fetchers. Eliminates the intermediate String; only the doc arena is needed.
2. Update `CHART_BUDGET_B` in `test_yahoo_finance_api.py` from 8192 to 16384 to match the firmware's `DynamicJsonDocument(16384)` for chart fetches. Add cross-reference comment citing the firmware source line.
3. Add a capacity safety-factor note (≥ 1.5×) to the host budget check explaining why raw payload bytes ≠ doc capacity.

**Status**: done (4c3cb05/f57f6d0/c4ab771 — stock quote+chart on getStream(); weather/crypto reverted to getString() — chunked encoding, no Content-Length, HTTPClient on espressif32@6.9.0 can't dechunk via getStream(); ADR-034 amended; T186–T188 PASS; budget constants superseded by filter-before-parse approach)
**ADR**: ADR-034 (accepted)
**Triggered by**: QM audit LL-040 (2026-05-29)
**Deps**: M-MULTIAPP (dataTask in tree)

---

### M-STOCK-VE-STRESS — Redesign T186: per-range fetch verification with counter assertion

T186 fires 32 taps to stress-test StockApp rapid range switching, but dataTask queue depth is 4. All taps beyond the first four are silently dropped — only D1/D5 fetches ran; Mo1/Ytd (the larger ranges most likely to exhaust heap) were never exercised. The test reported PASS with unmeasured coverage.

Fix:
1. Drive each range individually: tap → wait for `lastChartFetch` counter to advance → confirm no `fetchFailed` → repeat for all four ranges. This guarantees each range executes at least once.
2. Add a focused rapid-switch phase (D1↔Ytd alternating, 4–6 cycles with queue-drain waits) to test the back-to-back allocation pattern under real pressure.
3. Add a `Dut` class docstring noting the serial stream is not thread-safe; document fire-and-forget + drain-phase as the canonical pattern for async log capture (avoids the ACK-theft failure mode from T186 iteration 2).

**Status**: done (T204 added — 3-cycle D1↔Ytd alternating stress, counter-drain pattern; all 3 steps complete: T188 per-range sequential, T204 rapid-switch stress, Dut thread-safety docstring)
**Triggered by**: QM audit LL-041 / LL-042 (2026-05-29)
**Deps**: M-DATATASK-STREAM-PARSE (fix the bug first, then verify the fix holds under stress)

---

### M-AQUARIUM-CRAB — Aquarium crab creature

Add a single red ASCII crab to the aquarium that lives on the bottom of the canvas,
walks left and right, and pinches nearby fish or food flakes with the nearest claw.

Crab glyphs:

```
Walk A:    v(._.)v      Walk B:    ^(._.)^
Pinch R:   v(._.)>      Pinch L:   <(._.)v
Cute:      v(^.^)v      Sleep:     v(-.-) z
```

Behaviour:
- **Walk** — moves sideways at ~12 px/s; reverses at canvas edges and seaweed roots.
- **Pinch** — triggered when a fish or food flake enters `CRAB_PINCH_RANGE_PX = 45 px` horizontally within the bottom 80 px zone; extends the correct claw toward the target for 600 ms.
- **Cute** — rare random emote during quiet periods.
- **Sleep** — triggered after 20 s of no nearby targets; auto-wakes on target detection or after 5 s.

Work (all changes in `app/src/aquarium/aquariumApp.h`):
1. Add `Crab` struct + `CRAB_*` constants.
2. Implement `initCrab()`, `updateCrab(dt)`, `drawCrab()`.
3. Wire into `init()`, `tick()`, and `renderFrame()`.
4. Build + DUT verify.

**Status**: done (2026-05-28 — TASK-111 `1d77e96`; DUT verified; CRAB-FIX-001–014 applied)
**Design**: [M-AQUARIUM/crab.md](../architecture/designs/M-AQUARIUM/crab.md)
**Deps**: M-AQUARIUM (done — `aquariumApp.h` in tree)

---

### M-SKIN-SELECT — Configurable bake-time skin

Allow users to build firmware with any Winamp 2.x skin, not only the default
`base-2.91.wsz`. The Winamp base skin is not redistributable; users must supply
their own `.wsz` file. The bake tool already accepts any conformant Winamp 2.x
skin via `-i`; this milestone exposes that as a proper user-facing workflow.

Work:
1. **`run/bake-skin`** — already accepts `$1` as optional skin path (done,
   2026-06-07). Default falls back to `app/skins/base-2.91.wsz` with a clear
   error and link to <https://skins.webamp.org> if the file is absent.
2. **Build flag** — add `WINAMP_SKIN_WSZ` (or similar) to `platformio.ini`
   `extra_scripts` pre-build hook so `pio run` auto-bakes when the flag points
   at a non-default skin. (Optional; manual `./run/bake-skin skin.wsz` is
   sufficient for now.)
3. **README** — document the skin workflow: download a `.wsz`, place it under
   `app/skins/`, run `./run/bake-skin`, then flash.
4. **`golden.sha256`** — note that the checksum is skin-specific; users baking
   a different skin should regenerate it with
   `cd app/gen && sha256sum skin_assets.c skin_layout.h > golden.sha256`.

**Status**: partial — `run/bake-skin` argument + missing-file guard done. Steps 2–4 outstanding.  
**Deps**: none  
**Note**: runtime skin swap remains out of scope (ADR-003).

---

### M-SETUP-WIZARD — `run/setup` first-time credential wizard

Single terminal wizard replacing the manual `wifi_creds.h` edit and bare `get_refresh_token.py` invocation. Writes `app/data/wifi_creds.json` (SPIFFS) and `app/data/spotify_diy_config.json`; handles OAuth inline; offers `./run/spiffs push` at the end. PATCH-003 in `WifiManagerHandler.h` reads `/wifi_creds.json` from SPIFFS before falling through to the captive portal (`WiFi.persistent(false)` guards NVS — TASK-167).

**Status**: done (2026-06-11 — commit 463ba0b; TASK-167 fix flashed same session; T-SETUP-07/08/09/10 passing on DUT; E1–E7 verified)
**Deps**: tooling-002 (run/spiffs)
**Design:** [M-SETUP-WIZARD.md](../architecture/designs/M-SETUP-WIZARD.md)

---

### M-TASKBAR-ICONS — Baked RGB565 icon sprites for taskbar

Replace the single ASCII-character glyphs (`S`, `C`, `W`, `$`, …) in `taskbar.h` with proper per-app icon sprites baked at host time into `app/gen/taskbar_icons.c` + `taskbar_icons.h`.

**Slot dimensions:** 45×40 px (1 px separator at bottom → 39 px drawable height). Practical icon size: **32×32 px** (≈6-7 px horizontal padding each side, ≈3-4 px vertical).

**Asset pipeline** (mirrors `vis_atlas` / `wave_atlas` pattern):
1. Source PNGs: `app/icons/taskbar/<app_name>.png` (20×20, RGBA).  
   One file per entry in `appRegistry.h`: `spotify`, `clock`, `weather`, `crypto`, `matrix`, `life`, `settings`, `stock`, `aquarium`.
2. Bake script: `app/tools/gen_taskbar_icons.py` → `app/gen/taskbar_icons.c` + `taskbar_icons.h`.  
   Outputs one `uint16_t[400]` RGB565 array per app, plus a lookup table indexed by `AppId`.
3. `taskbar.h` — replace `tft.drawChar()` call with `tft.pushImage()` using the baked array.

**Icon sourcing (human step first):**  
Candidate source: [Material Symbols](https://fonts.google.com/icons) or [Simple Icons](https://simpleicons.org/) (SVG/PNG, no-attribution licences). Place candidate PNGs in `app/icons/taskbar/` for @Architect review before bake script is written. See TASK-170.

**Status:** done (2026-06-12 — TASK-170/171; icons sourced + baked; `taskbar.h` updated to `pushImage()`; DUT flashed and verified)  
- 9 inactive (B&W) + 9 active (coloured) icons, all 24×24 baked RGB565  
- `run/bake-icons` + `app/tools/gen_taskbar_icons.py`; `golden.sha256` updated  
**Deps:** M-MULTIAPP (done)  

---

### M-TELETEXT — NOS Teletekst live reader app

10th app in the multiapp shell. Fetches live teletext pages from NOS
(`teletekst-data.nos.nl`) and renders them on the 275×240 app canvas.

**Proof of concept (2026-06-13):** fully validated on-host before any firmware
was written — a deliberate practice from lessons learned.

- NOS API reverse-engineered: `https://teletekst-data.nos.nl/page/{N}`,
  ISO-8859-1, 1000-byte 25×40 grid in a `<pre>` block, no JSON.
- Teletext control codes decoded: text mode (0x01–0x07) vs mosaic graphics mode
  (0x10–0x17); mosaic 2×3 pixel patterns rendered as `fillRect` blocks.
- Navigation metadata parsed: prev/next page, prev/next subpage, 4 fast-text
  coloured button targets + labels from row 24.
- Preview tool: `app/tools/preview_teletext.py` — live NOS fetch, full 320×240
  canvas with taskbar, 1×/2×/3× zoom, keyboard + mouse navigation.
- Resource impact assessed: ~1.1 KB per fetch (smallest in the project); fits
  into existing `dataTask` HTTPS pattern; ~4 KB persistent SRAM.

**Canvas layout** (ADR-044):

```
┌──────────────────────────────────────────────┬──────┬─────────┐
│  40 cols × 6 px  ×  25 rows × 8 px          │nav   │ taskbar │
│  240 × 200 px teletext grid                  │strip │  45 px  │
│                                              │35 px │         │
├──────────────────────────────────────────────┤      │         │
│  40 px fast-text bar (red/grn/yel/cyn btns)  │      │         │
└──────────────────────────────────────────────┴──────┴─────────┘
```

**Navigation model:**
- **Fast-text bar** (bottom 40 px): 4 coloured buttons — section shortcuts.
- **Right-strip** (35 × 200 px): subpage ▲, current page number, prev ◄ / next ►
  page, subpage ▼. Arrows via `fillTriangle()`.
- **Inline row links**: tap a news-index row → scan cols 35–39 for 3-digit page
  ref → navigate. 10-entry history ring enables back navigation.

**Settings** (Settings → Applications → Teletext):
- **Start page**: News 101 / Sport 601 / Weather 702 / Football 800
- **Refresh**: 30 s / 60 s / 120 s
- **Country**: NL (NOS) — label only until multi-country R&D spike completes

**Open items before firmware:**
1. Finalise right-strip layout + inline links in `preview_teletext.py`.
2. Confirm root CA for `teletekst-data.nos.nl` via `openssl s_client`.
3. Source `teletext.png` + `teletext_active.png` icons (24×24) for taskbar bake.
4. R&D spike: which other active teletext services share the NOS wire format?
   Candidates: ORF (AT), ARD (DE), SVT (SE), RAI (IT), YLE (FI).

**Status:** done (2026-06-13/14 — TASK-177–191; firmware implemented, icons baked, VE suite T249 ready-to-run, T272 PASS; ADR-044 accepted; 3 bugs fixed during T272: tlsYield gap, early-boot no-enqueue, null-byte parser)  
**Deps:** M-MULTIAPP (done), M-TASKBAR-ICONS (done)  
**Design:** [M-TELETEXT.md](../architecture/designs/M-TELETEXT.md)  
**ADR:** ADR-044 (accepted 2026-06-13)

---

### M-WEBRADIO — International Web Radio App

11th app in the multiapp shell. Browse and play internet radio stations from
**radio-browser.info**, categorised by country. The Winamp main-unit UI is
reused with adapted semantics: station name in the title marquee, stream buffer
health in the seek bar, prev/next mapped to station navigation. Toggle between
Spotify and web radio via the existing taskbar.

**High-level requirements:**
- **UI**: Winamp skin reused; controls remapped to radio semantics.
- **Toggle**: eject button (screen pos 136, 89) — no taskbar slot; Winamp icon stays.
- **Settings**: country/region selector (Settings → Applications → Web Radio).
- **Playlist**: scrollable station list fetched by country (radio-browser.info);
  sorted by popularity; capped at 100 entries.
- **UX controls**: play/stop, prev/next station, station name marquee, ICY
  now-playing metadata in title area.

**R&D pre-requisites (EXP-005 spike — all done):**
1. **radio-browser.info API** — confirmed; TLS: server omits R13 intermediate from the
   handshake, so pinned-CA `setCACert()` can't build the chain — uses `setInsecure()`
   instead (TASK-214, deviates from ADR-029, pending amendment).
2. **CYD audio path** — GPIO26 internal DAC → SC8002B; GPIO25 reserved (touch).
3. **ESP32-audioI2S library** — 55.6% flash at build (gate cleared TASK-199).
4. **ICY metadata** — `StreamTitle` confirmed via NPO Radio 2 probe (TASK-200).

**Status:** in progress — firmware complete (TASK-213 signed off 2026-06-14); eject + error injection VE done (TASK-211/212, 8/14 tests PASS); TASK-214 fix re-scoped 2026-06-20 (try setCACert() first, setInsecure() fallback only on verify failure — host re-check disputes the original "intermediate omitted" diagnosis for at least one mirror, see TASK-217) — still not DUT-verified. T_WR_TLS_01 + T_WR_SPOTIFY_RESUME_01 authored (TASK-216) and ready for the next DUT session, which now also resolves TASK-207/208/209 (TASK-208 thresholds provisional, TASK-215)  
**Deps:** M-MULTIAPP (done), M-TASKBAR-ICONS (done), EXP-005 (done)  
**Design:** [M-WEBRADIO.md](../architecture/designs/M-WEBRADIO.md)  
**R&D:** [EXP-005](../rnd/reports/EXP-005-webradio-spike.md)

---

### M-WEBRADIO-NOPSRAM — No-PSRAM playback viability via Spotify-disabled build

Build-time experiment to settle the open M-WEBRADIO milestone-blocker (stable MP3
playback on the no-PSRAM CYD). Hypothesis: not creating `spotifyTask` frees its
**~10 KB stack** (resident for life — `tlsYield` does *not* reclaim it) **and**
removes the ~50 KB TLS session's heap fragmentation, enlarging the contiguous
DMA-capable block the MP3 decoder needs — the actual wall per EXP-007/TASK-233. A
bigger reclaim than TASK-239/240's ~11 KB, which already gave TASK-241 a provisional
pass. **Bonus:** a Spotify-disabled build needs no auth, so it **sidesteps the
TASK-243 Premium blocker** that has stalled the TASK-241 viability test.

**Approach (see design doc):** a `cyd2usb_webradio` PlatformIO env with
`-DDISABLE_SPOTIFY` that guards `spotifyTask::begin()` and no-ops `tlsYield`/
`tlsResume`; the Spotify app UI stays as a dormant stub (no `AppId::Spotify` surgery).
Measure `get heap`/`get stacks` delta vs the multi-app build, then re-run the TASK-241
input-buffer experiment under the reclaimed budget.

**Decision gate:** PASS (stable ≥ 60 s playback + underruns drop) → supersede ADR-045's
"stable no-PSRAM playback = NO-GO" and consider a shipped WebRadio-focused variant;
FAIL → the 38.9 KB caps-restricted block is the hard wall, ADR-045 stands.

**Status:** proposed — Architect 2026-06-26; PM to schedule (R&D-flavoured, runs on a branch per AGENTS.md).  
**Deps:** M-WEBRADIO; feeds TASK-241 / TASK-233 / ADR-045; unblocks around TASK-243.  
**Design:** [M-WEBRADIO-SPOTIFY-DISABLE.md](../architecture/designs/M-WEBRADIO-SPOTIFY-DISABLE.md)

---

### M-PREVIEW-FRAMEWORK — Common preview tool framework

Extract shared geometry constants, taskbar rendering, app-registry integration,
GIF writer, and pygame window management from the six `app/tools/preview_*.py`
tools into `app/tools/preview_common.py`.

Work:
1. Write `preview_common.py` (constants, `draw_taskbar_pil`, `draw_taskbar_pygame`,
   `load_icon_pil`, `load_icon_pygame`, `write_gif`, `PreviewWindow`).
2. Port each of the six tools to import from `preview_common`:
   `preview_layout.py`, `preview_clock.py`, `preview_vis.py`, `preview_wave.py`,
   `preview_heatmap.py`, `preview_teletext.py`.
3. Verify each tool still launches and renders correctly (manual smoke test per tool).

**Status:** done
**Design:** [M-PREVIEW-FRAMEWORK.md](../architecture/designs/M-PREVIEW-FRAMEWORK.md)
**Deps:** M-APP-REGISTRY (done — app_ids_gen.py is canonical source), M-TASKBAR-ICONS (done — PNG icons exist)
**Note:** TASK-192 (retroactive). Verify caught one bug: `pygame.K_Q` does not exist; fixed to `pg.K_q` in `PreviewWindow.handle_event`. Design doc exit-criteria pixel for separator is off by one (spec says y=39, actual y=40); implementation follows reference, not the spec typo.

---

### M-WR-PLEDIT-SCROLL — WebRadio PLEDIT drag/velocity scroll

WebRadio's PLEDIT is tap-to-play only: `WebRadioApp::handleInput` reacts to `Release`
alone, so a swipe is silently interpreted as a tap on whichever row the finger lifts
over — no drag scroll exists (`_scrollOffset` moves only by auto-follow of the current
station). Spotify's PLEDIT has the full M-LIST-v4 velocity-scroll gesture machine in
`winampDisplay.h` (ADR-030). This milestone gives WebRadio the same scroll UX. Design
lean (panel-reviewed): **pattern-copy** the ADR-030 gesture into `WebRadioApp` with
tuning constants hoisted to a shared header — extraction rejected for two consumers
(promotion path documented at a third scrolling list).

**Status:** **DONE 2026-07-07** — reroute (`c5fd6e5`) + feature landed; exit criteria
13/13, T_WR 17/18 (sole fail external TASK-284), taskbar suite 5/5 through the reroute.
Campaign finds: TASK-293 (stop-then-replay tlsYield deadlock, P1, fixed), T_WR_ERR_x
harness isolation defect (fixed). T155-T160 gate SKIPped blocked-external (TASK-243) —
disposition pending human. Feel tuning (OQ1) deferred to a human DUT session
(`wrSpeedK` runtime-tunable). Design panel-reviewed 2026-07-03 — approved (human).
**Land order (panel-pinned):** shared E0 baseline session (done) → TASK-278 (done) →
**TASK-277 (done)** → TASK-279 blits (done 2026-07-07).
**Design:** [M-WR-PLEDIT-SCROLL.md](../architecture/designs/M-WR-PLEDIT-SCROLL.md)
**Deps:** M-LIST-v4 (done — the gesture model being copied), M-WEBRADIO (done)
**Tracked-as:** TASK-277

---

### M-WR-AUDIO-TASK — WebRadio audio decode off loopTask

`s_wr_audio->loop()` (ESP32-audioI2S decode + HTTP stream fill) runs inside
`WebRadioApp::tick()` on the Arduino loopTask (core 1) — the same task that samples
touch and drives all UI. During playback every loop iteration carries decode work,
degrading touch latency shell-wide (taskbar included). This milestone moves audio
servicing to a dedicated FreeRTOS task with explicit core placement, lifecycle
(start/stop on play/eject), and locking around the shared Audio object. Design lean
(panel-reviewed): pump task on core 1 prio 2, Phase-1 mutex with timeout-take UI reads,
ack-then-self-delete teardown.

**Status:** **DONE 2026-07-07 — Phase 1 landed (`39e6c08`) + E1-E5 exit criteria all PASS**
(decode tail on loopTask eliminated: 141→50 ms max, 6→0 iters >50 ms per 10-min PLAYING
window; results table in the design doc). Follow-ups from the campaign: TASK-291 (FIN-close
stream-death detection gap, pre-existing), TASK-292 (soak balance-counter false-FAIL).
Design panel-reviewed 2026-07-03 (VE/DEV/QM approve-with-changes ×3, dispositions
applied) — approved 2026-07-03 (human)
**Land order (panel-pinned):** shared E0 baseline session (done) → **TASK-278 (done)** →
TASK-277 (done) → TASK-279 blits (done 2026-07-07).
**Design:** [M-WR-AUDIO-TASK.md](../architecture/designs/M-WR-AUDIO-TASK.md)
**Deps:** M-WEBRADIO (done), M-WEBRADIO-NOPSRAM (A-lite arena — heap ceiling constraint)
**Tracked-as:** TASK-278

---

### M-TASKBAR-FEEDBACK — Taskbar tap feedback + switch latency

Taskbar app switching feels sluggish and gives no confirmation a tap landed: the
switch fires only on finger release (`tbGestureEnd`), there is no pressed-slot visual
state, and `switchApp` does a full init/resume + repaint before anything changes on
screen. (Design review: cooldowns do NOT gate taskbar taps — taskbar zone dispatches
before the gate; the real tap-loss mechanism is sampled-touch loss during long loop
iterations, owned by M-WR-AUDIO-TASK.) This milestone adds immediate press feedback
and instruments `switchApp` per-phase before any speed work. Design lean
(panel-reviewed): pressed-slot highlight + tap-commit amber via shared shellTb* helpers,
press-anchored slot commit, switch stays on-release.

**Status:** **DONE 2026-07-07** — feedback blits + instrumentation landed (`d13817d`);
taskbar suite + T_TBFB_01–04 **10/10 PASS** on DUT; before/after latency tables in the
design doc (press-to-first-pixel ~14 ms same-iteration vs first pixel only after the
post-release switch before; switch cost itself unchanged; wipe=27 ms constant recorded
as the L-b candidate, deferred as designed). Dispositions D1–D3 human-ratified
2026-07-07 (1dc4f9a, c8808cf; LL-101 → BP-045). Follow-ups all closed: TASK-280
(DONE 2026-07-08), TASK-281 (DONE), TASK-294 (shellCooldown hook + T_TBFB_05,
DONE 2026-07-08). Design approved 2026-07-03 (human).
**Land order (panel-pinned):** shared E0 baseline session (done) → TASK-278 (done) →
TASK-277 (done) → **TASK-279 feedback blits (done)** — sequence complete.
**Design:** [M-TASKBAR-FEEDBACK.md](../architecture/designs/M-TASKBAR-FEEDBACK.md)
**Deps:** M-TASKBAR-SCROLL (done — gesture layer being amended), M-TOUCH-UX (done)
**Tracked-as:** TASK-279 · Follow-ups filed from panel: TASK-280 (injection/production
dispatch alignment, done), TASK-281 (QM housekeeping, done)

---

### M-PLANERADAR — ADS-B plane radar app

New taskbar app: circular sonar-style radar of live aircraft around a configured
lat/lon, data from the free adsb.fi REST API, with range presets (5/10/15/25 km),
heading vectors, callsign/type/altitude tags, and an optional major-airport runway
overlay. Ported by concept from the `ESP32-Plane-Radar` reference project
(ESP32-C3 + round GC9A01) — radar math, ADS-B field handling, and the airport-DB
bake script carry over; fetch/TLS/config/render are rewritten on platform
infrastructure (dataTask fixed-struct fetcher, ADR-029 cert pin, tlsYield
bracket, settingsStorage, static-grid + symbol-redraw rendering — no full-frame
sprite on the no-PSRAM board). Key risks: ADS-B payload heap spike next to the
Spotify TLS session (mitigated by filtered stream-parse + fixed ~24-aircraft cap),
flash growth from the airport DB (trimmed bake), taskbar slot-count shift
(NEW-APP-CHECKLIST §6). **Host-first phase 0** (M-TELETEXT pattern): API probe,
fixture capture, host-compiled ArduinoJson parse trial, `preview_planeradar.py`
UI PoC, and airport-DB trial bake settle the API risk and the parse-heap term
of the heap risk off-DUT before firmware starts (TLS-coexistence soak stays
DUT-side).

**Status:** DONE 2026-07-11 — TASK-301..307 all closed (`./run/check` 6/6 PASS
throughout): dataTask ADS-B fetcher (ADR-048), PlaneRadarApp render + taskbar
registration, Settings integration (range/units/runway toggle/tag rule/stale
style all persisted, no longer compile-time-only), the airport-DB bake
(`run/bake-airports`, ADR-049 V-europe — baked 240 airports/355 runways,
matching the phase-0 measurement exactly; runway overlay renders real data),
and DUT validation (TASK-307): all 6 exit criteria run, 5 PASS + 1 SKIP
(network-dependent, not a gap — see `docs/verification/regression_suite/
m-planeradar-dut.md`). 30-min Spotify-coexistence soak: heap floor delta
4,952 B, within budget and matching ADR-048's ~4 KB parse estimate almost
exactly, zero reboots.
**Deps:** M-MULTIAPP (done), M-APP-REGISTRY (done), dataTask (done), ADR-029,
ADR-048 (accepted), ADR-049 (accepted).
**Design:** [M-PLANERADAR-plane-radar-app.md](../architecture/designs/M-PLANERADAR-plane-radar-app.md)
**Tracked-as:** TASK-301 (2nd cert observation, done) ·
TASK-302 (taskbar icon assets, done) · TASK-303 (dataTask fetcher, done) ·
TASK-304 (app render + registration, done) · TASK-305 (Settings integration,
done) · TASK-306 (airport-DB bake adoption, done) · TASK-307 (DUT
validation, done)

---

### M-ICON-PIXELART — Native pixel-art icon authoring at taskbar slot resolution

Follow-up to M-TASKBAR-ICONS, opened while redesigning the PlaneRadar taskbar
icon (see TASK-302/M-PLANERADAR): `gen_taskbar_icons.py` unconditionally
LANCZOS-resizes any source PNG down to `TASKBAR_ICON_W`x`_H` (24x24), which
caused repeated, hard-to-diagnose confusion when iterating on a
programmatically-generated icon (scaling a shape and its canvas together is
invisible post-bake; double-resampling through an intermediate canvas size
overshot the intended fill ratio unpredictably). Human direction: reduce/
remove reliance on scaling source art down to the taskbar's fixed budget —
author icons as pixel art directly at the real slot resolution instead.

Also surfaced mid-session: the 24x24 icon budget itself is self-imposed, not
a hardware limit — it sits inside a 45x40 slot, using only 53%/60% of the
available width/height. Whether to grow `TASKBAR_ICON_W`/`_H` to use more of
that space is logically prior to the authoring-workflow question (status quo
/ native-resolution for hand-authored icons only / uniform native-resolution
for all taskbar icons including imported art), which only matters once the
target size is settled. No lean forced on either question — needs a human
decision given real tradeoffs on each side.

**Status:** proposed — design doc drafted, awaiting human decision on
options before an ADR is written
**Deps:** M-TASKBAR-ICONS (done), M-PLANERADAR (done)
**Design:** [M-ICON-PIXELART-native-icon-authoring.md](../architecture/designs/M-ICON-PIXELART-native-icon-authoring.md)

---

### M-CERT-ERRCODE — Dedicated error code for TLS cert failures

An mbedTLS certificate-verify failure (-9984 X509_CERT_VERIFY_FAILED) is
invisible at the `errorCode` surface: Arduino HTTPClient collapses it into a
generic `-1 CONNECTION_REFUSED`, so pin rot on any dataTask host looks like a
dead server unless someone is watching the serial monitor (`tlsErr()` decode
is log-only). Both coingecko root flips (TASK-298) were diagnosed that way.
With the pin roster growing (adsb.fi; proposed Nominatim, whose chain relies
on a droppable cross-sign), cert rot should name itself on the existing
surfaces: hook `WiFiClientSecure::lastError()` in the shared `openHttps()`
helper, map `-0x2700` to a new `-120 CERT_VERIFY_FAILED` sentinel (reserved
band -120..-129), decode it in `httpErr()`, and audit the hand-rolled
fetchers onto the same check. Host side (added same day): hook the existing
`run/check-datatask-certs` validity test into `run/build*` warn-only (env
knob to skip offline), add a deterministic offline expiry check on the
pinned PEMs, and a `--propose-fix` mode that drafts the replacement PEM +
fingerprint report for human approval — explicitly **no** auto-update of
pins (TOFU risk; single probes lie under Cloudflare multi-chain
load-balancing, see TASK-298). Companion to M-PR-LOCATIONS.

**Status:** proposed — design doc drafted 2026-07-13
**Deps:** ADR-029, TASK-223 (openHttps)
**Design:** [M-CERT-ERRCODE-cert-error-sentinel.md](../architecture/designs/M-CERT-ERRCODE-cert-error-sentinel.md)

---

### M-PR-LOCATIONS — PlaneRadar location presets + geocode lookup

Supersedes the D4 (v1) compile-time-location lean and the "strip is
display-only" phase-0 decision. Four named location slots
(`label ≤5 chars + lat/lon`), managed in Settings → Applications →
PlaneRadar via a country + full-postcode geocode lookup (Nominatim
structured search — provider matrix probed live 2026-07-13: open-meteo's
geocoder is blind to UK postcodes; Nominatim is street-level for both NL and
UK full postcodes and needs **no new root cert**, its chain verifies against
the already-pinned ISRG Root X1 via a cross-sign to be flagged in
`dataTaskCerts.h`). Slot editor: keyboard-driven label/country/postcode entry,
one-shot dataTask geocode fetch, save/retry/cancel + delete. In the radar app
the side strip lists the slot labels and a tap jumps the radar (repaint disc,
re-project runways, immediate re-fetch); `prLat/prLon` stay as the
written-through mirror of the active slot so all existing consumers and the
spiffs-push dev path keep working. Preview-first for the strip layout per
BP-048.

**Status:** proposed — design doc drafted 2026-07-13; Q1–Q7 resolved by
human same day (4 slots · 5-char labels · N^ marker removed outright ·
manual lat/lon entry as first-class alternative to lookup · 2-char country
entry · radar-only switching · home-alias recorded only). Ready for PM
breakdown into tasks
**Deps:** M-PLANERADAR (done), dataTask, ADR-029, KeyboardWidget,
M-CERT-ERRCODE (companion, not blocking)
**Design:** [M-PR-LOCATIONS-location-presets.md](../architecture/designs/M-PR-LOCATIONS-location-presets.md)

---

## Out of scope (recorded for non-action)

- PC mirror / SDL host build target — superseded by ADR-006.
- Portable `core/` + `platform/` leaves layout — superseded by ADR-006.
- IFCs in `docs/architecture/interfaces/` — not introduced under ADR-006.
- HUB75 matrix display backend — dropped at M3.
- Runtime skin swap / user-supplied skins — precluded by ADR-003.
- On-device audio path / I2S microphone for real spectrum VU — ADR-002 option (c), not chosen.
