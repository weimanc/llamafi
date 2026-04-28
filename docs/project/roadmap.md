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
| TASK-008 NTP sync at boot (time-001) | in_progress (code landed, awaiting DUT verify) |

### Still to do
- TASK-008 DUT verification: confirm `[time] synced` line appears and that `spotifyRefreshToken` succeeds. If TLS still fails after time fix, root-cause shifts back to TASK-006 (rotation) or library-level TLS quirks.
- TASK-006: resume when user has Spotify account access back. Verifying TASK-004 (no `NFC Bad`) rides along on the same flash cycle.

---

## M1 — API capability spike (de-risk)

**Status:** in_progress (code drafted 2026-04-28, awaiting DUT run — TASK-007)
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

### Exit criteria
- Each row marked pass or fail with the failing-row mitigation written down.
- `SpotifyArduino` strategy chosen and recorded as a short ADR or as a note in `architecture.md` Open Questions.
- M4 and M5 unblocked of the "does the endpoint even work" question.

### Blockers
- DUT required. Spike code can be drafted host-side now and run on the next DUT trip alongside TASK-006.

---

## M2 — Skin asset pipeline (host-side)

**Status:** planned
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

**Status:** planned
**Scope:** New `winampSkinLCD.h` implementing `spotifyDisplay.h`, rendering the baked atlas + layout against TFT_eSPI on the CYD. `cheapYellowLCD.h` stays for fallback; build flag selects. HUB75 / `matrixDisplay.h` dropped from project scope.

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

**Status:** planned
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

**Status:** planned
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

**Status:** planned
**Scope:** New VU module per ADR-002. Fetches `audio-analysis` for the current track on track change, caches in RAM (LRU, N TBD), drives an attack/release envelope with beat transients. Fallback chain: `audio-analysis` → `audio-features` → `off`.

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
