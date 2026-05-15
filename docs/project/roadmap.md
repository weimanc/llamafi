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

**Status:** done (TASK-020 DUT-verified 2026-05-15; M-LIST-v2 PLEDIT skin in progress per ADR-018).

**Scope:** Top-align the Winamp chrome and render a Spotify queue strip in the freed area below.

**Decisions locked (ADR-017):**

| Decision | Choice |
|---|---|
| Orientation | **C — landscape, `originY = 0`** (TASK-022 cancelled) |
| Playlist area | 320 × 124 px at y=116..240 |
| Data source | `GET /me/player/queue` (Tier 1; see `ADR-017-api-candidates.md`) |
| Row 0 | Currently-playing track (yellow-gold highlight) |
| Rows 1-6 | Queue items (Winamp grey-green) |
| Font | TFT_eSPI Font 2 (12×16 px) — 7 rows |
| Tap-to-play | Tier 2 (TASK-021, deferred) |

**Sub-tasks (all done):**

| Deliverable | Owner | Status |
|---|---|---|
| TASK-020a: `originY = 0` layout shift | Developer | done |
| TASK-020b: `QueueSnapshot` + `getQueue()` + poll logic | Developer | done |
| TASK-020c: `drawPlaylist()` renderer + seqno-diff hook | Developer | done |
| TASK-021: tap-on-row → play that track | Developer | deferred (tier 2) |
| TASK-022: portrait rotation (option B) | — | **cancelled** |

### Exit criteria (met 2026-05-15)
- ✅ Winamp chrome paints flush with the top edge.
- ✅ Playlist strip shows currently-playing in row 0, queue rows 1-6 below, updated ≤5 s.
- ✅ 60 s keepalive re-fetches queue without track change.
- ✅ Flash budget delta ≤ +3 % on `cyd2usb_winamp`.

---

## M-LIST-v2 — Winamp PLEDIT playlist skin

**Status:** planned (2026-05-15 — whiteboard done, ADR-018 accepted).

**Scope:** Replace the plain-black row list from TASK-020 with a proper Winamp Playlist Editor (`PLEDIT.BMP`) skin. Option C hybrid: baked title bar (14 px) + bottom bar (16 px) + `SKIN_PLEDIT_ROW_HIGHLIGHT` sprite; 5 track rows with `MM:SS` duration right-aligned; total playlist time in bottom bar.

**Decisions locked (ADR-018):**

| Decision | Choice |
|---|---|
| Fitting strategy | **Option C — PLEDIT title bar + bottom bar baked; 5 track rows** |
| Row count | **5** (authenticity over count) |
| Duration format | **`MM:SS` right-aligned** per row, original Winamp style |
| Scrollbar | Static decoration (Tier 1); live position deferred Tier 2 |
| Total time | Sum `durationMs`, rendered in PLEDIT bottom bar time slot |

**Sub-tasks:**

| Deliverable | Owner | Tier | Status |
|---|---|---|---|
| TASK-047a: `bake_skin.py` PLEDIT extraction + atlas + preview | Developer | 1 | planned |
| TASK-047b: `durationMs` in `QueueEntry` + `getQueue()` filter | Developer | 1 | planned |
| TASK-047c: `drawPlaylist()` redesign — PLEDIT chrome + row format | Developer | 1 | planned |
| TASK-047d: total time in PLEDIT bottom bar | Developer | 1 | planned |
| TASK-021: tap-on-row → play that track | Developer | 2 | deferred |
| TASK-047e: scrollbar live position | Developer | 2 | deferred |

**Cross-cuts:** depends on TASK-020 (done), `m2-001` bake pipeline, `m3-001` renderer. Adds feature `playlist-002`.

### Exit criteria
- `gen/skin_preview.png` shows PLEDIT title bar + 5 rows + bottom bar below main chrome.
- DUT: PLEDIT title bar at `y=116`, bottom bar at `y=224`.
- DUT: row 0 `► Artist - Title   MM:SS` with PLEDIT highlight bg.
- DUT: rows 1-4 PLEDIT green text, right-aligned `MM:SS`, black bg.
- DUT: total time in bottom bar time slot.
- Flash delta ≤ +2 % on `cyd2usb_winamp`.
- `sha256sum -c golden.sha256` passes after re-bake.
- No regression in main chrome.

---

## M-LIST-v3 — Playlist interactivity: selected-row tracking + virtual scroll

**Status:** planned (2026-05-15).

**Scope:** Three tightly coupled playlist features that together make the PLEDIT strip behave like the real Winamp playlist editor.

### Feature 1 — Selected-row highlight tracks the current song

**Problem:** Row 0 is permanently highlighted (gold). After `TASK-021` tap-to-play, the user sees instant `PUT /play` 204 but the highlight stays at row 0 until the next queue poll (~5 s). The delay breaks the cause-and-effect expectation.

**Approach:**
- After `ACT_PLAY_URI param=N` is dispatched, `winampDisplay` tracks an `optimisticSelectedRow` index (similar to `optimisticVolumeUntilMs`). `drawPlaylist()` renders that row as selected instead of row 0 until the queue snapshot's seqno advances (confirming Spotify updated the queue) or a timeout expires (~8 s).
- On track change (seqno advances), derive selected row from the new `items[0]` URI matching the previously enqueued URI — or just reset to row 0 (items[0] = currently playing, always correct post-poll).

### Feature 2 — Virtual scroll: queue > 5 items

**Problem:** `SPOTIFY_QUEUE_MAX_ITEMS = 5` caps the queue. Expanding to 10–20 items requires a scroll offset to stay within the 5 visible rows.

**Approach:**
- Extend `SPOTIFY_QUEUE_MAX_ITEMS` (patched in `lib/SpotifyArduino/`) to e.g. 20. `QueueSnapshot` grows accordingly.
- Add `scrollOffset` (int, 0-based) to `WinampDisplay`. `drawPlaylist()` renders `items[scrollOffset .. scrollOffset + PLEDIT_ROW_COUNT - 1]`.
- Touch: row tap maps to `scrollOffset + row` for `ACT_PLAY_URI`.
- Scroll gesture (swipe in PLEDIT content area) increments/decrements `scrollOffset`. Simple up/down drag detection (reuse `dragState` pattern).

### Feature 3 — Live scrollbar thumb

**Problem:** TASK-047e deferred the scrollbar to a static decoration.

**Approach:**
- Scrollbar thumb position = `scrollOffset / (count - PLEDIT_ROW_COUNT)` × scrollbar track height.
- On each `drawPlaylist()` redraw, blit the thumb sprite at the computed Y within the scrollbar track (right-side PLEDIT chrome).
- Depends on Feature 2 (scroll offset exists only once virtual scroll lands).

### Cross-feature: auto-scroll to current track on track change

**Problem:** After the queue scrolls, the currently-playing track (items[0]) may be above the scroll window. A track change should snap the view back to include it.

**Approach:**
- On `seqno` advance (track changed), reset `scrollOffset = 0` so items[0] (current track) is always in view.
- If the user had scrolled, the snap is intentional and expected (same behaviour as real Winamp).

**Sub-tasks (to be fleshed out by PM when scheduled):**

| Task | Scope |
|---|---|
| TASK-051a | `optimisticSelectedRow` in `winampDisplay.h`; drawPlaylist uses it for highlight |
| TASK-051b | Extend `SPOTIFY_QUEUE_MAX_ITEMS` to 20; grow `QueueSnapshot`; verify RAM budget |
| TASK-051c | `scrollOffset` in `WinampDisplay`; drawPlaylist slices items[offset..offset+5] |
| TASK-051d | Swipe gesture in PLEDIT content area drives scrollOffset |
| TASK-051e | Live scrollbar thumb (depends on TASK-051c) |
| TASK-051f | Auto-scroll-to-current on seqno advance (reset scrollOffset = 0) |

**Cross-cuts:** extends `TASK-021` (tap-to-play row index must add `scrollOffset`); extends `TASK-047c/d` (drawPlaylist); touches `lib/SpotifyArduino` (queue size constant). Adds feature `playlist-003`.

### Exit criteria
- Selected row highlight follows the playing track within one poll after track change; optimistic highlight appears immediately on tap.
- With queue > 5 items, swipe up/down scrolls the visible window; all rows reachable.
- Scrollbar thumb position matches scroll position.
- Track change (external or via tap) snaps view to show currently-playing in row 0.
- No regression in tap-to-play (TASK-021) or PLEDIT chrome (TASK-047).

---

## M-VIS — Visualization area: spectrum + waveform + toggle

**Status:** planned (2026-05-15 — whiteboard done; mono spectrum chosen per Winamp 2 main-window convention).

**Scope:** Replace the fixed synthetic VU meter with a proper Winamp-style visualization section. Tap on the vis area cycles through four modes: **VU → Spectrum → Wave → Blank → VU**. VU mode is the existing M6 implementation (kept). Spectrum and wave are new synthesized renderers operating within the confirmed vis area `(x=24, y=43, w=76, h=13 px)`.

No new API calls. All views derive from the existing synthetic envelope engine (`lLvl`, `rLvl`, beat phase, LFO) already in `vuMeter.h`.

**Vis area geometry (confirmed):**
```
window-local: x=24, y=43, w=76, h=13
VU left bar:  y=43..48  (6px)
gap row:      y=49       from SKIN_MAIN_BG
VU right bar: y=50..55  (6px)
wave midline: y=49 (centre)
```

**Mode cycle:** tap vis area → `vu::nextMode()` → `VIS_VU → VIS_SPECTRUM → VIS_WAVE → VIS_BLANK → VIS_VU`

**Decisions locked:**

| Decision | Choice |
|---|---|
| Spectrum layout | Mono, 38 bars × 2px wide, full 76px (matches Winamp 2 main-window default) |
| Spectrum colours | Green 0–50 % height, yellow 50–80 %, red 80–100 % (Winamp classic palette) |
| Peak dots | 1×1 px per bin, rises instantly, falls ~1 px / 100 ms |
| Wave colour | `TFT_GREEN` (Winamp oscilloscope default) |
| Wave cycles | 2.5 per 76 px width (dense, matches Winamp feel) |
| Wave amplitude | `lLvl × 5 px` (±5 from centre; collapses to flat line when paused) |
| Background restore | All modes: blit `SKIN_MAIN_BG` rows for vis area before draw (same pattern as TASK-049) |
| Data source | Synthetic only — existing envelope engine, no new API |

**Aesthetics spec:**

*Spectrum:* 38 vertical bars × 2px, bottom-up fill, green→yellow→red by height. Static `shape[38]` pink-noise rolloff table (`1 - i/37 × 0.6`). Beat transient injected into low bins only (i < 8). Peak dot per bar decays at 1 px/100 ms.

*Wave:* `y[x] = centre + round(lLvl × 5 × sin(φ + x × 2.5 × 2π / 76))`. Phase `φ` advances `+0.3 rad` per tick (20 Hz). Restore SKIN_MAIN_BG before each frame; draw single green pixels.

*Blank:* restore SKIN_MAIN_BG to vis area, then idle (no per-tick work).

**Sub-tasks:**

| Task | Scope | Status |
|---|---|---|
| TASK-050a | `VisMode` enum + `nextMode()` + vis hit-test + touch dispatch + blank mode | planned |
| TASK-050b | Spectrum analyzer: bin synthesis, bar render, peak dots | planned |
| TASK-050c | Waveform oscilloscope: phase-advancing sine, single-pixel line | planned |

**Cross-cuts:** extends `vuMeter.h` (adds sig to `tick()`); touches `winampDisplay.h::checkForInput()`; depends on TASK-049 (SKIN_MAIN_BG background restore pattern already established). Adds feature `vis-001`.

### Exit criteria
- Tapping vis area cycles VU → Spectrum → Wave → Blank → VU on DUT.
- Spectrum: 38 bars visible, colour grades green→yellow→red by height, peak dots visible and decaying.
- Wave: smooth sine oscillation, amplitude tracks playback level, flat line when paused.
- Blank: vis area shows skin background texture only.
- VU mode: unchanged from M6 (regression check).
- No regression in touch controls (transport, posbar, volume, shufrep) — vis hit-test must not overlap existing zones.
- Flash delta ≤ +1 % on `cyd2usb_winamp` (`shape[]` table + peak state ≈ < 300 bytes).

---

## M-UI-POLISH — Small UI fidelity improvements

**Status:** planned (2026-05-15 — whiteboard done).

**Scope:** Two focused fidelity fixes that close gaps between the current render and original Winamp 2 behaviour. No new API calls, no bake-tool changes, no new atlas data.

### Item 1 — Artist + title in marquee strip (TASK-048)

**Gap:** title strip currently shows track `name` only. `Snapshot::artistName` is already populated — just not wired.

**Original Winamp 2 format (main window):** `"Artist - Title"` — no track-number prefix (that is playlist-editor only). Fall back to `"Title"` alone when artist is blank.

**Changes:**
- `lastTitle[128]` → `lastTitle[260]` (artist 128 + `" - "` 3 + title 128 + NUL 1).
- Compose `artist + " - " + name` on track change; detect change on either field.
- Scroll gap: insert `"   "` (3 spaces) between end of string and loop-back start, producing the classic endless-ticker feel original Winamp had.
- Scroll speed (`TITLE_SCROLL_STEP_MS=120`) stays unchanged unless user prefers faster.

**Change surface:** ~10 LOC in `winampDisplay.h`. No bake or firmware arch change.

### Item 2 — VU zero-fill from SKIN_MAIN_BG (TASK-049)

**Gap:** `vuMeter.h::tick()` clears the "off" portion of each bar with `fillRect(TFT_BLACK)`, overwriting the skin's visualization-area background texture.

**Fix:** Mirror the pattern `drawTitleText()` already uses — blit the corresponding `SKIN_MAIN_BG` rows into the zero-fill region. VU rects `(x=24, LEFT_Y=43, RIGHT_Y=50, w=76, h=6)` are fully within the `275×116` `SKIN_MAIN_BG` atlas.

**Changes:**
- Add `const uint16_t *mainBg` parameter to `vu::tick()`.
- Replace `fillRect(TFT_BLACK)` with per-row `pushImage` from `SKIN_MAIN_BG` at the zero-fill offset.
- Update `vu::tick(originX, originY, SKIN_MAIN_BG)` call site in `.ino`.

**Change surface:** ~15 LOC in `vuMeter.h` + 1 LOC call site. No bake or atlas change.

### Sub-tasks

| Task | Item | Status |
|---|---|---|
| TASK-048 | Artist + title in marquee strip | planned |
| TASK-049 | VU zero-fill from SKIN_MAIN_BG | planned |

### Exit criteria
- DUT: title strip shows `"Artist - Title"`, scrolling continuously with a gap spacer between end and loop-start.
- DUT: title strip shows `"Title"` only when artist field is blank.
- DUT: VU bars restore skin background texture in the zero-fill region (no solid black border visible around bars during playback).
- No regression in title scroll timing, VU animation cadence, or chrome repaint.

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
