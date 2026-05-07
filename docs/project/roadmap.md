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

**Status:** **blocked on TASK-009** (TLS connection lifecycle — non-GET endpoints fail until fixed)
**Scope:** Replace the three-zone (prev / dead / next) mapping in `touchScreen.h` with skin-region hit-testing driven by `gen/skin_layout.h`. Wire each button to the corresponding `SpotifyArduino` call. Optimistic UI per ADR-006: flip local state immediately, fire API call, let next poll reconcile.

| Control | API surface | Status |
|---------|-------------|--------|
| Play / pause | needs new (extend SpotifyArduino or helper) | planned |
| Prev / Next | existing `previousTrack` / `nextTrack` | planned |
| Seek (drag, debounce-on-release) | `seek` (exists, unwired) | planned |
| Shuffle toggle | needs new | planned |
| Repeat toggle | needs new | planned |
| Volume | needs new | planned |

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

**Status:** **blocked on TASK-010** (ADR-002 invalidated — `audio-features` and `audio-analysis` return HTTP 403 for new Developer apps; primary data source unavailable)
**Scope:** Originally per ADR-002. Now requires a superseding ADR before any work — see TASK-010 candidate options ((a) drop, (b) synthesise from poll data, (c) Spotify Extended Quota Mode, (d) on-device microphone).

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
