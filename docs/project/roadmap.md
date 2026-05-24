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

## Outstanding

### M-IO — Decouple display from blocking network calls

Remove cases where Spotify API calls block the super-loop long enough to freeze UI and stale state.
**Status:** done (TASK-019 async poll; TASK-052 tap resets backoff, 2026-05-16)
**Deps:** M3
**Design:** [M-IO-decouple-display-network.md](../architecture/designs/M-IO-decouple-display-network.md)

---

### M-UI-POLISH — Small UI fidelity improvements

Wire artist name into marquee (`Artist - Title`); restore skin background in VU zero-fill region.
**Status:** done (2026-05-16)
**Deps:** M3, M6
**Design:** [M-UI-POLISH-fidelity.md](../architecture/designs/M-UI-POLISH-fidelity.md)

---

### M-HITZONES — Hit-zone preview PNG

Extend bake tool to emit a semi-transparent hit-zone overlay PNG for touch alignment verification.
**Status:** done (2026-05-16)
**Deps:** M2
**Design:** [M-HITZONES-hitzone-preview.md](../architecture/designs/M-HITZONES-hitzone-preview.md)

---

### M-CONN — Connection health UI + TLS recovery controls

Inactive title bars on disconnect; serial `reconnect` command; Winamp logo tap → TLS reset.
**Status:** done (2026-05-22 — all exit criteria met). F1: DNS-induced consecutive=2 → repaintChrome fired SKIN_TITLEBAR_INACTIVE (render_age 60003→17251ms). F2: reconnect JSON ack, TLS reset, 10/10 polls. F3: logo tap → TLS reset + force poll logged; 2s cooldown correct; visual redraw confirmed. Also fixed TASK-073 crash (strcmp nullptr on track start).
**Deps:** M-IO (TASK-052), M-CHROME (done), M3
**Design:** [M-CONN-connection-health.md](../architecture/designs/M-CONN-connection-health.md)

---

### M-LIST-v2 — Winamp PLEDIT playlist skin

Replace plain row list with proper PLEDIT skin: title bar, bottom bar, 5 rows, MM:SS durations, total time.
**Status:** planned (2026-05-15; ADR-018)
**Deps:** M-LIST, M2, M3
**Design:** [M-LIST-v2-pledit-skin.md](../architecture/designs/M-LIST-v2-pledit-skin.md)

---

### M-VIS — Visualization area

Tap-cycling visualizer replacing fixed VU: VU → Spectrum (19 bars) → Wave (sine) → Blank.
**Status:** design updated (2026-05-16 — R&D pixel measurements incorporated; implementation pending TASK-050a/b/c)
**Deps:** M6, M-UI-POLISH (TASK-049)
**Design:** [M-VIS-visualization.md](../architecture/designs/M-VIS-visualization.md)

---

### M-LOG2 — On-screen log overlay

Full-panel log terminal behind the Winamp chrome; newest 15 lines visible in PLEDIT area.
**Status:** done (TASK-018 DUT-verified 2026-05-07); PLEDIT compat fix needed before using with M-LIST-v2
**Deps:** M-LOG (done), M3
**Design:** [M-LOG2-screen-log-overlay.md](../architecture/designs/M-LOG2-screen-log-overlay.md)

---

### M-LIST-v3 — Playlist interactivity

Selected-row highlight tracking, virtual scroll (20 items), live scrollbar thumb.
**Status:** planned (2026-05-15)
**Deps:** M-LIST-v2, TASK-021 (tap-to-play)
**Design:** [M-LIST-v3-playlist-interactivity.md](../architecture/designs/M-LIST-v3-playlist-interactivity.md)

---

### M-PERF — Profiling + targeted optimisation

Instrument loop and hot paths; measure before deciding which optimisations to ship.
**Status:** planned (added 2026-05-08)
**Deps:** M-LOG (done), M3, M-IO
**Design:** [M-PERF-profiling.md](../architecture/designs/M-PERF-profiling.md)

---

### M-SERIALDBG — Serial debug command expansion + touch injection

Expand `handleSerialCommands()` beyond `reconnect` with a richer debug/test command surface. Primary deliverable: `tap X Y` and `drag X1 Y1 X2 Y2 STEPS` commands that inject synthetic touch events into the same `hitTest*` / `enqueue` path as physical screen presses. Secondary deliverables: `info` (state snapshot), `status` (hit-zone dump).

All responses are JSON lines. Host scripts use `json.loads(line)` — check `ok`, `hit`, `action` fields. Drag emits the same intermediate log lines that physical drag already produces.

This unlocks regression-scriptable coverage for T052–T054, T074, T075, T048, and nine new tests (T076–T085, T089) that are impossible to write without coordinate-precise, repeatable input injection.

**Status:** planned (2026-05-17)
**Deps:** M5 (touch hit-test path in tree), M-LOG (structured serial output)
**Design:** [M-SERIALDBG-serial-debug-framework.md](../architecture/designs/M-SERIALDBG-serial-debug-framework.md) · [ADR-021](../architecture/decisions/ADR-021.md)

---

### M-SYNC — DUT–Spotify state synchronization

Field-level lag bounds + stale-state checks between Spotify's authoritative state and DUT chrome render. 14 tests (T097–T110, TSYNC-1 through -14). Three lag-bound tiers formalized in ADR-022.
**Status:** planned (2026-05-17); blocked on ADR-022, SERIALDBG-l/-m, TASK-058, VE harness tools
**Deps:** M-SERIALDBG, M-IO, M-LOG

---

### M-DRIFT — Operational state-drift surfacing

Runtime counterpart to M-SYNC. Two surfaces: (a) `last_render_age_ms` heartbeat field; (b) in-chrome staleness indicator when `last_poll_age_ms > N_STALE_MS`. Threshold + indicator form in ADR-023.
**Status:** planned (2026-05-17); blocked on ADR-023, TASK-059, TASK-060
**Deps:** M-SYNC (TASK-058 shared), M-CONN (overlay pattern)

---

### M7 — Polish / open questions

Resolve remaining open questions (TLS CA strategy, seek-drag, speculative poll, audio-analysis cache) once system exercised end-to-end.
**Status:** done (2026-05-16 — ADR-019 TLS CA, ADR-020 speculative poll, seek-drag visual resolved in design doc; audio-analysis already closed ADR-009)
**Deps:** M6 and all prior milestones
**Design:** [M7-open-questions.md](../architecture/designs/M7-open-questions.md)

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

**Status:** design (2026-05-22 — design doc drafted; blocked on M-MULTIAPP interactive preview tooling)
**Deps:** M-MULTIAPP (interactive preview tool, step 1)
**Blocks:** M-MULTIAPP taskbar + appshell implementation (steps 3–4)
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

**Status:** design (2026-05-22 — design docs drafted; preview tooling pass required before implementation tasks filed)
**Deps:** M3 (done), M-NOART (done), M-RESTRUCTURE (gates step 2), M-SHELL-LAYOUT (taskbar constants header, gates steps 3–4)
**Design:** [M-MULTIAPP/overview.md](../architecture/designs/M-MULTIAPP/overview.md)

---

## Out of scope (recorded for non-action)

- PC mirror / SDL host build target — superseded by ADR-006.
- Portable `core/` + `platform/` leaves layout — superseded by ADR-006.
- IFCs in `docs/architecture/interfaces/` — not introduced under ADR-006.
- HUB75 matrix display backend — dropped at M3.
- Runtime skin swap / user-supplied skins — precluded by ADR-003.
- On-device audio path / I2S microphone for real spectrum VU — ADR-002 option (c), not chosen.
