# Roadmap

> Owner: Project Manager
> Purpose: Milestone-level view of planned work. Features/tasks in `feature_inventory.yaml`/`tasks.md` — roadmap groups into delivery chunks.

Scope per ADR-006: keep the Spotify-Diy-Thing baseline architecture; change the UI to a Winamp 2 classic skin; extend touch to drive the full skin's controls; add a synthesised VU. Super-loop, `SpotifyArduino`, SPIFFS/NVS/WiFiManager all unchanged.

---

## M0 — Baseline hardened (done / housekeeping)

**Status:** in_progress
**Scope:** First dev unit working end-to-end; secrets and NFC posture cleaned up before UI work begins.

| Feature / Task | Status |
|----------------|--------|
| TASK-001 first bring-up | done |
| TASK-004 NFC posture decision (gate or remove) | done (2026-04-28) |
| TASK-005 secret hygiene (`.gitignore`, `.example` template) | done (2026-04-28) |
| TASK-006 refresh-token rotation (leak response) | paused (Spotify account access issue) |
| TASK-008 NTP sync at boot (time-001) | done (2026-04-28) |

### Still to do
- TASK-006: resume when user has Spotify account access back. **DUT confirmed (2026-04-28) that the leaked refresh token is now `invalid_grant — Refresh token revoked`** by Spotify's leak scanner, so rotation is the only remaining gate to running M1 spike tests. Verifying TASK-004 (no `NFC Bad`) and a fresh `[time] synced` line ride along on the same flash cycle.

---

## M1 — API capability spike (de-risk)

**Status:** done (2026-04-29) — with two new blockers surfaced for downstream milestones (TASK-009, TASK-010)
**Scope:** Prove every Spotify Web API call the Winamp UI will need round-trips on this DUT + this account, *before* any skin work. Throwaway code: trivial trigger surface (serial command per call, or three crude touch zones), baseline `cheapYellowLCD.h` UI untouched. Output is a written go/no-go per row + a decision on `SpotifyArduino` extension strategy. Spike code can be deleted or absorbed into M4/M5.

| Capability | Endpoint | In `SpotifyArduino`? | Risk |
|------------|----------|----------------------|------|
| Play / pause | `PUT /v1/me/player/{play,pause}` | no | low |
| Seek | `PUT /v1/me/player/seek` | yes (unwired) | low |
| Shuffle toggle | `PUT /v1/me/player/shuffle` | no | low |
| Repeat toggle | `PUT /v1/me/player/repeat` | no | low |
| Volume | `PUT /v1/me/player/volume` | no | medium — Free-tier returns 403; needs Premium + active device |
| `audio-features` | `GET /v1/audio-features/{id}` | no | low — small JSON |
| `audio-analysis` | `GET /v1/audio-analysis/{id}` | no | **high** — 30–80 KB JSON, heap + ArduinoJson sizing, may force streaming parse or a non-`SpotifyArduino` fetch path |

| Deliverable | Feature ID |
|-------------|------------|
| Spike harness (serial commands or 3-zone touch) firing each call | api-001 |
| Per-row pass/fail recorded in `tasks.md` | api-001 |
| Decision: extend `SpotifyArduino` / fork / write helpers | api-001 (closes Open Q) |
| Heap headroom note for `audio-analysis` parse | api-001 (informs M5 cache sizing) |

### Exit criteria — outcome

- ✅ Each row marked pass or fail with the failing-row mitigation written down. See `tasks.md:TASK-007` per-row table and `test_plan.md:T001-T020`.
- ✅ `SpotifyArduino` strategy decided: vendoring + tiny-patch is **not** sufficient. The library reuses one `WiFiClientSecure` across heterogeneous request types and breaks at TLS-send for non-GET. Recommendation (subject to architect ADR): migrate affected endpoints to Arduino-ESP32 `HTTPClient`. Tracked as **TASK-009 / api-002**.
- ⚠ M5 is **not** unblocked: the spike found that the entire control surface (play/pause/seek/volume/shuffle/repeat/next/previous) cannot be driven from this firmware until TASK-009 lands.
- ⚠ M6 has **lost its data source**: `audio-features` and `audio-analysis` return HTTP 403 from Spotify for new Developer apps as of late 2024. ADR-002's primary path is invalidated. Tracked as **TASK-010 / vu-001 rethink**.

---

## M2 — Skin asset pipeline (host-side)

**Status:** in_progress (tier 1 done 2026-05-07 — bake tool + main bg + transport buttons + raw font atlas; tier 2 covers glyph UV table, time digits, sliders alongside M3 wiring)
**Scope:** Build-time bake tool (per ADR-003) that converts the Winamp 2 classic skin to `gen/skin_assets.c` (RGB565 atlas) + `gen/skin_layout.h` (button rects, VU rect, text rects, slider tracks, 9-slice metadata). No firmware change yet — output is verified by inspection and by rendering the atlas in a throwaway preview. Independent of M1 (host-only); can run in parallel.

| Deliverable | Status |
|-------------|--------|
| Skin bake tool (host-side, Python or similar) | planned |
| `gen/skin_assets.c`, `gen/skin_layout.h` checked-in artefacts | planned |
| PlatformIO pre-build hook (or `make` target) wiring | planned |

### Exit criteria
- Atlas + layout regenerate deterministically from the source skin.
- Atlas size known → confirms RGB565 against flash budget (closes one Open Question).

---

## M3 — Winamp display backend

**Status:** done (2026-05-07 — DUT visual verify confirmed all 8 chrome+touch items)
**Scope:** New `winampDisplay.h` (subclass of CheapYellowDisplay, reusing JPEG/SPIFFS/touch plumbing) renders the baked atlas + layout against TFT_eSPI on the CYD. `cheapYellowLCD.h` stays as the default; `cyd2usb_winamp` env selects. HUB75 / `matrixDisplay.h` dropped from project scope per ADR-006.

| Deliverable | Feature ID |
|-------------|------------|
| `winampSkinLCD.h` static layout (no live data yet) | disp-002 (new) |
| Wire `spotifyLogic.h` to drive the new backend with currently-playing data | disp-002 |
| Drop HUB75 env from `platformio.ini` | — |

### Exit criteria
- Device boots, shows the Winamp chrome with track title, artist, album art in the right slots.
- Seek bar and elapsed-time field render (display-only, not yet interactive).
- Visual parity check against a reference Winamp screenshot.

---

## M4 — Position interpolation

**Status:** done (2026-05-07)
**Scope:** Smooth seek-bar / elapsed-time movement between ~1 Hz polls. Few lines in `spotifyLogic.h` per ADR-006: stash `progress_ms` + `millis()` on each poll, derive displayed position each frame, snap on poll if gap > 500 ms. Local seeks update both fields directly.

| Deliverable | Feature ID |
|-------------|------------|
| Position interpolation in poll loop | poll-002 (new) |

### Exit criteria
- Seek bar advances visibly smoothly during playback.
- After a poll, no visible stutter or backwards jump under normal jitter.
- 500 ms snap threshold validated against measured network jitter (closes one Open Question).

---

## M5 — Full-skin touch controls

**Status:** done (2026-05-08 — DUT-verified; transport buttons + posbar seek live, optimistic-UI interpolator freeze in place)
**Scope:** Replace the three-zone (prev / dead / next) mapping in `touchScreen.h` with skin-region hit-testing driven by `gen/skin_layout.h`. Wire each button to the corresponding `SpotifyArduino` call. Optimistic UI per ADR-006: flip local state immediately, fire API call, let next poll reconcile.

| Control | API surface | Status |
|---------|-------------|--------|
| Play / pause | `play` / `pause` (lib already had — patched 2026-05-08) | done |
| Prev / Next | `previousTrack` / `nextTrack` | done |
| Seek (tap-to-position) | `seek` | done |
| Stop | maps to `pause` (no native Spotify stop) | done |
| Shuffle toggle | not on main-window chrome — deferred | not yet |
| Repeat toggle | not on main-window chrome — deferred | not yet |
| Volume | not on main-window chrome — deferred | not yet |
| Seek-drag with debounce-on-release | tap-only for tier 1; drag deferred | not yet |

| Deliverable | Feature ID |
|-------------|------------|
| Skin-region hit-testing | touch-002 (new) |
| Production wiring of API calls proven in M1 | api-001 |
| Optimistic-UI pattern across all controls | touch-002 |

### Exit criteria
- Every visible Winamp control responds to touch within one render frame visually.
- Spotify state reconciles within one poll on success; UI snaps back on API failure.
- TASK-002 and TASK-003 closed.

---

## M6 — VU meter

**Status:** done (2026-05-09 — ADR-009 option (e) shipped; decorative envelope synthesised from `currentlyPlaying` + flat 120 BPM beat clock + LFO stereo split. No real audio data — Web API doesn't surface it.)
**Scope (final):** ADR-009 option (e). Two horizontal bars rendered into the canonical Winamp visualization rect at window-coords (24,43,76,6)/(24,50,76,6); green/yellow/red colour grading by level; 20 Hz tick; decays to zero on `is_playing=false`. Decoration only — explicitly not music-locked.

| Deliverable | Feature ID |
|-------------|------------|
| `audio-analysis` + `audio-features` fetch path | api-001 (proven in M1) |
| In-RAM LRU cache (size N) | vu-001 (new) |
| Envelope synthesis + beat transients | vu-001 |
| Renderer hook for stereo VU rect | vu-001 |

### Exit criteria
- VU bounces visibly in time with playback for tracks with analysis.
- Graceful fallback verified for tracks without analysis (`features`) and without either (`off`).
- Cache size N picked given remaining flash/RAM after M3 atlas (closes one Open Question).
- Cache-miss UX on track change accepted (closes one Open Question).

---

## M-LOG2 — On-screen log overlay (debug HUD)

**Status:** planned (added 2026-05-07; complements M-LOG tier-1 ringbuffer).
**Scope:** Use the **whole 320×240 panel** as a log terminal; the Winamp chrome paints on top and naturally clips whatever it covers. Top strip (y 0–62) shows older lines, bottom strip (y 178–240) shows newer lines, the middle band is hidden behind the Winamp window. Diagnostic aid for state-coupling investigations: lets the user see live what the firmware is doing without a tethered monitor or `/log` HTTP pull.
**Why:** Symptoms during M3 verify (slow first sync, occasional hangs, stale track shown after Spotify advanced) are all manifestations of the super-loop blocking inside network calls — heartbeat data already showed 56 s gaps. The on-screen overlay makes those gaps and their causes visible at the same moment they're affecting the UI.
**Design sketch:**
- New `screenLog.h` renderer; subscribed to the existing 12 KB ringbuffer (no new state).
- Layering: log is the bottom layer (full-screen, ~30 lines × 53 chars at TFT_eSPI font 1, ~6×8 px). Winamp chrome is the top layer and overlays the middle band; what it covers is hidden, what it doesn't is visible.
- Visible budget: top strip ~7 lines (oldest visible), bottom strip ~7 lines (newest), middle ~16 lines hidden behind chrome — they scroll through but aren't seen.
- Newest line at the bottom of the screen; older lines scroll up; oldest line eventually scrolls off the top.
- Default colors: green-on-black (terminal aesthetic, on-brand for Winamp). No anti-aliasing — direct `tft.drawString`.
- Lines truncated on the right (no wrapping).
- Redraw orchestration: dirty flag set by `ringPush`; redraw at most ~4 Hz from the main loop to avoid SPI thrash. Each redraw paints the log over the full screen, then re-blits the Winamp chrome (background + transport buttons + status indicator + title slot + posbar). Time-digit / progress-thumb / title-marquee updates are unchanged — they self-repaint over their slot from `MAIN.BMP` and don't need to know the log exists.
- Behind `#define SCREEN_LOG` (or a `cyd2usb_winamp_screenlog` env that adds the flag) so it can be disabled cleanly. Default off — production-build aesthetic.
**Cross-cuts:** depends on log-001 (ringbuffer); informs disp-001 / m3-001 (the chrome is now the "top layer", not the only layer).
**Tracked as:** TASK-018.

### Exit criteria
- With `-DSCREEN_LOG` set, the panel shows log lines top + bottom, with the Winamp chrome overlaid in the middle. New entries appear at the bottom and scroll up.
- Without the flag, no overhead — `screenLog::tick()` and the renderer are compiled out; chrome paints directly to a black background as today.
- Default off — `cyd2usb_winamp` env unchanged.

---

## M-IO — Decouple display from blocking network calls

**Status:** planned (added 2026-05-07; observed during M3 verify).
**Scope:** Investigate and remove the cases where a Spotify API call blocks the super-loop long enough to freeze time/slider/touch and let track state go stale.
**Symptoms (2026-05-07 M3 DUT verify):**
- Slow first sync after boot.
- Occasional hangs — clock + progress thumb stop advancing.
- LCD shows previous track for many seconds after Spotify has moved on.
- Heartbeat data captured 56 s gaps between consecutive ticks during TLS retries.
**Likely contributors (to be confirmed via on-screen log + `/log` traces):**
- HTTP retry storms when TLS handshake fails on captive-portal-style networks.
- 5 s `delayBetweenRequests` is too long when a track is short.
- Synchronous `getCurrentlyPlaying` blocks the renderer for the full TLS+HTTP duration.
**Tracked as:** TASK-019.

### Exit criteria
- TBD — likely an ADR proposing async IO, a worker task, or aggressive timeouts.
- Heartbeat gap distribution stays under 5 s p95 across normal play.

---

## M-LOG — Logging redesign (cross-cutting, parallel)

**Status:** tier 1 shipped 2026-05-07 (ADR-010 + amendments + DUT-verified). Whiteboard 2026-05-07.
**Scope:** Replace ad-hoc `Serial.println` + vendored `SPOTIFY_DEBUG` with `esp_log` tags+levels, RAM ringbuffer + `/log` pull endpoint, mbedTLS/HTTP code decoder, redactor for secret-bearing fields, 30 s heartbeat. Tier 2 adds UDP syslog and state-machine trace points; tier 3 adds SPIFFS-backed buffer + panic flush.
**Why:** DUT verification this session nearly lost the boot trace; mbedTLS error codes are opaque; refresh tokens are still printed by `configFile.h`; hangs (TASK-014) leave no progress trail. Whiteboard: `docs/architecture/whiteboards/2026-05-07-logging-rethink.md`.
**Cross-cuts:** every existing milestone — adopt incrementally, not as a single migration.
**Tracked as:** TASK-016.

### Exit criteria
- ADR-010 accepted; tier-1 items shipped (esp_log adoption surface, ringbuffer + `/log`, secret redactor, mbedTLS decoder, heartbeat).
- Configuration JSON dump removed from boot path (LL-002 / LL-003 follow-up closed in code, not just in vendored lib).

---

## M-PERF — Profiling + targeted optimisation

**Status:** planned (added 2026-05-08; triggered by user-reported "LCD flicker + sluggish controls" during M5 use).

**Scope:** Two distinct symptoms — separate, instrument, then optimise where the data points.

- **LCD/backlight flicker.** Likely candidates: aggressive SPI clock (`SPI_FREQUENCY=55000000`), mid-blit tear during big repaints, power dip under combined WiFi-TX + display + JPEG decode load. `TFT_BL` is static HIGH, not PWM — backlight itself shouldn't flicker, panel content can.
- **Sluggish controls.** Already partially diagnosed via M-IO `block_max_ms` heartbeat: synchronous Spotify polls blocking the loop for ~600–2000 ms. Touch isn't sampled while a poll is in flight.

The objective is to verify those hypotheses with measurements before deciding which optimisations to ship — many of them are non-trivial (async poll, DMA SPI), and we want signal before scope.

### Tier 1 — Instrumentation (no architecture change)

| Deliverable | Owner | Notes |
|---|---|---|
| Loop-iteration timer; `LOG_W` when an iteration > 50 ms | Developer | adds `loop_max_ms` to heartbeat; identifies which iterations are slow |
| `micros()` pairs around hot paths (`getCurrentlyPlaying`, `screenlog::tick`, `repaintChrome`, `displayTrackProgress`, `checkForInput`) | Developer | per-path max since last heartbeat; surfaced as `path_max=<name>:Nms` field |
| Stack high-water mark in heartbeat (`uxTaskGetStackHighWaterMark`) | Developer | tells us whether we're near stack overflow |
| 40 MHz vs 55 MHz SPI A/B (just a build flag flip) | Developer | 30-second test; rules in/out signal-integrity flicker |

Total ~60 LOC + one build-flag flip. No DUT-iteration churn beyond a single flash for the instrumentation.

### Tier 2 — Decisions (gated on tier-1 data)

| Deliverable | Owner | Notes |
|---|---|---|
| ADR: async Spotify poll (FreeRTOS task on APP_CPU, snapshot slot read by main loop) | Architect | M-IO tier 2 promotion. Biggest expected win. Skip if tier-1 data shows polling isn't the bottleneck. |
| ADR: DMA SPI for big blits (`tft.initDMA`, `tft.pushImageDMA`) | Architect | Modest win on `repaintChrome` + `screenLog::tick` full-screen paths. Skip if tier-1 shows blits aren't dominant. |
| ADR: screenLog incremental redraw (diff-against-previous, repaint only changed lines) | Architect | Saves ~90% of SPI traffic when only the newest line is new. Justifies itself only if SCREEN_LOG is on by default. |

### Tier 3 — Implementation (gated on tier-2 ADRs being accepted)

| Deliverable | Owner |
|---|---|
| Async Spotify poll task | Developer |
| DMA-converted blit paths | Developer |
| screenLog incremental redraw | Developer |
| Touch debounce / press-hold state-machine (replaces 80 ms `delay()` in `checkForInput`) | Developer |

The 80 ms touch-press `delay()` is a known stall — it's there for visual press-feedback. Replace with a millis-tracked release-on-timer. Small but always-helpful.

**Cross-cuts:** depends on `log-001` (heartbeat field plumbing). Touches `poll-001` (potential async restructure), `m3-001` (DMA blit candidates), `log-002` (redraw efficiency). Adds new feature `perf-001`.

**Tracked as:** TASK-029 (tier 1 instrumentation), TASK-030 (tier-1 SPI clock A/B test), TASK-031 (tier-2 ADR — async poll), TASK-032 (tier-2 ADR — DMA blits), TASK-033 (tier-3 impl, gated).

### Exit criteria

- Tier 1 lands and DUT data is captured for a representative session (≥5 min play, includes at least one network blip).
- An honest diagnosis: which paths actually exceed 50 ms, what `loop_max_ms` looks like during touch / during pause, whether the SPI A/B made the flicker measurably better.
- Tier-2 ADRs only written for paths the data justifies. No optimisation without measurement.

---

## M-CHROME — Bake the rest of the Winamp main-window sprites

**Status:** planned (added 2026-05-08).

**Scope:** Bring the remaining main-window chrome elements out of the `.wsz` and onto the panel. Some have an API source we can drive (volume / shuffle / repeat / mono-vs-stereo); the rest are pure static decoration that just makes the chrome look complete. Cross-checked against the local Spotify Web API snapshot (`resource/web-api/`) — Spotify exposes `device.volume_percent`, `shuffle_state`, `repeat_state`, `currently_playing_type` directly on `/me/player/currently-playing`, so all of those are free. **Bitrate and sample rate are NOT in any Web API schema** — Spotify deliberately doesn't surface stream quality. They get rendered as hardcoded static values (44 kHz, 320 kbps assuming Premium, "stereo" for tracks / "mono" for episodes per `currently_playing_type`).

**Tier 1 (fits in current flash budget — ~28 KB free, ~18 KB needed):**

| Element | Source BMP | Bytes | Driven by | Static / dynamic |
|---|---|---|---|---|
| Mono/stereo + kHz/kbps strip | MONOSTER.BMP | 2 784 | `currently_playing_type` | mostly static (kHz=44, kbps=320 hardcoded; mono/stereo derived) |
| Shuffle / repeat indicator | SHUFREP.BMP | 15 640 | `shuffle_state`, `repeat_state` | fully dynamic |

**Tier 2 (gated on flash-budget work — currently won't fit):**

| Element | Source BMP | Bytes | Driven by | Notes |
|---|---|---|---|---|
| Title bar | TITLEBAR.BMP | 59 856 | static | decoration; could subset to one variant (~10 KB) before baking to fit |
| Volume slider | VOLUME.BMP | 58 888 | `device.volume_percent` | 28 frames; could subset to ~8 keyframes (~17 KB) |
| Balance slider | BALANCE.BMP | 58 888 | none | pure decoration; "always centred" or skip entirely |

The tier-2 sheets are dominated by frame-strip variants (28 volume positions, 28 balance positions, 3-state title bar). Subsetting at bake time would let one or two of them fit; baking all three at full resolution requires a real flash-budget conversation (lighter atlas format, partition resize, or compressing the existing atlases).

**Sub-tasks:**

| Deliverable | Owner | Tier |
|---|---|---|
| Extend `tools/bake_skin.py` to optionally include MONOSTER + SHUFREP atlases + sprite UVs | Developer | 1 |
| Render the mono/stereo + kHz/kbps strip in `winampDisplay.h` (driven by `currently_playing_type`) | Developer | 1 |
| Render shuffle/repeat indicator state from `shuffle_state` / `repeat_state` (touch tier 2 separate) | Developer | 1 |
| ADR or short note on flash-budget approach for tier 2 (subset / partition / compress) | Architect | 2-gate |
| Bake + render title bar (static) | Developer | 2 |
| Bake + render volume slider driven by `device.volume_percent` | Developer | 2 |
| Decide whether balance ships at all | Architect | 2-gate |

**Cross-cuts:** depends on `m2-001` (bake tool), `m3-001` (renderer), `poll-001` (already polls `currently_playing`). Adds new feature `chrome-001`. Touches the planned but unimplemented volume / shuffle / repeat slots from M5 — TASK-003's volume sub-task closes here.

**Tracked as:** TASK-023 (bake-tool extension + tier-1 atlases), TASK-024 (mono/stereo + kHz/kbps strip), TASK-025 (shuffle/repeat indicator), TASK-026 (tier-2 ADR), TASK-027 (titlebar bake+render), TASK-028 (volume slider bake+render).

### Exit criteria

- Tier 1: MONOSTER + SHUFREP visible on the chrome; both reflect Spotify's reported state within one poll. ✅ MONOSTER baked statically (TASK-040, ADR-014); SHUFREP rendered dynamically with tap-toggle (TASK-025, 2026-05-10).
- Tier 2: gated on the flash-budget ADR — superseded by ADR-014 + TASK-035 (drop OTA app1). ✅
- Eject decorative composite landed alongside tier 1 (TASK-046, 2026-05-10).
- No regression in the existing chrome (transport, posbar, time digits, title marquee). ✅
- Flash budget for tier 1 stays under 99 % on `cyd2usb_winamp`. ⚠ Hit 99.7% during TASK-025, which trip-tested TASK-035; current binary at 49.9 % of the new 2.56 MB app0.

---

## M-LIST — Top-align Winamp UI + add playlist panel

**Status:** planned (added 2026-05-08).

**Scope:** Stop centering the Winamp main window on the panel. Top-align it instead, then use the freed-up area below to render a Spotify playlist / queue / next-up list. Two orientation options on the table:

| Option | Panel rotation | UI rotation | Playlist area | Notes |
|---|---|---|---|---|
| **C (default lean)** | landscape (no change, 320×240) | none | **320 × 124 px** below UI | one-line change to `originY`; no bake-time rotation; touch coordinates unchanged. Largest playlist canvas. |
| **B (portrait)** | `setRotation(0)`/`2` (240×320) | 90° at bake time | 240 × 45 px below UI | needs rotated atlas, layout-constant swap, touch x/y swap, screenLog flip. Phone-like ergonomics; ~3× less playlist area than C. |

Pick on aesthetic/ergonomic grounds. C if "as much playlist as possible" wins; B if "device held vertically like a phone" wins.

**Why now:** M5 closed the control surface. The current centered chrome wastes ~50 % of the panel as black margin. A playlist is the natural use of that real-estate, fits the Winamp aesthetic (Winamp had a separate playlist window), and gives the user up-next visibility that maps directly to a planned UX (tap a row to play that track).

**Sub-tasks:**

| Deliverable | Owner | Tier |
|---|---|---|
| Architect decision: option B vs C (one ADR) | Architect | gate |
| Top-align: shift `originY` to 0 in `winampDisplay.h::displaySetup` | Developer | tier 1 |
| Reposition the screenLog overlay layout to wrap around the new chrome position | Developer | tier 1 |
| Spotify Web API surface for the queue: `GET /me/player/queue` (already in `resource/web-api/player-endpoints.yaml`) | Developer | tier 1 |
| Playlist renderer: scrolling N-row list with current-track highlight, font 1 or 2, rendered into the freed strip | Developer | tier 1 |
| Tap-on-row → play-that-track (`spotify.playAdvanced` with the track URI as `context_uri`) | Developer | tier 2 |
| If option B chosen: bake-time atlas rotation + layout-constant swap + touch coord swap + screenLog flip | Developer | tier-B-only |

**Cross-cuts:** depends on `m3-001`, `touch-002`, `log-002`. Touches `disp-001`. Adds new feature `playlist-001`.

**Tracked as:** TASK-020 (architect decision + tier-1 wire-up), TASK-021 (tap-to-play), TASK-022 (option-B rotation if chosen).

### Exit criteria
- Winamp chrome paints flush with the top edge.
- Playlist strip below the chrome shows the current Spotify queue (≥3 rows, current track first or highlighted), updated on each poll cycle.
- ScreenLog overlay still functional (zero overhead when off; renders cleanly around the new chrome position when on).
- No flash regression > 1 % on `cyd2usb_winamp`.

---

## M7 — Polish / open questions

**Status:** planned
**Scope:** Clean up remaining Open Questions in `architecture.md` once the system is exercised end-to-end. Tuning, not new features.

| Item | Source |
|------|--------|
| TLS root CA strategy (pin vs trust-store) | Open Q |
| Seek-drag visual treatment during drag | Open Q |
| Speculative one-shot poll ~250 ms after intent (rate-limit headroom) | Open Q |
| `audio-analysis` SPIFFS-mirror vs RAM-only | Open Q |

### Exit criteria
- Each Open Question either resolved (with an ADR if it changed direction) or explicitly deferred with a written rationale.

---

## Out of scope (recorded for non-action)

- PC mirror / SDL host build target — superseded by ADR-006.
- Portable `core/` + `platform/` leaves layout — superseded by ADR-006.
- IFCs in `docs/architecture/interfaces/` — not introduced under ADR-006.
- HUB75 matrix display backend — dropped at M3.
- Runtime skin swap / user-supplied skins — precluded by ADR-003.
- On-device audio path / I2S microphone for real spectrum VU — ADR-002 option (c), not chosen.
