# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

## Project Scope

**In scope:** `Spotify-Diy-Thing/` — Arduino/PlatformIO firmware for ESP32 CYD2USB displaying Spotify now-playing track + album art via Spotify Web API.

**Out of scope:** `cspot/` — vendored upstream of an unrelated Spotify Connect player library. Do not extend, do not depend on. If touched at all, only to track upstream pulls.

## Active Tasks

### TASK-012 — M2 skin bake tool, tier 1
**Owner**: Developer
**Feature**: m2-001 (new)
**Status**: done (2026-05-07, tier-1 user scope — title + main controls — closed via tier-2 batch)
**Blocks**: M3 (unblocked: layout + atlas + glyph UVs all present)
**Notes**:
- Tier 1 deliverables landed at Spotify-Diy-Thing@a9682be: bake tool, source `.wsz` (Winamp 2 Base-2.91), generated `gen/skin_assets.c` + `gen/skin_layout.h`. Build clean. Atlas budget ~94 KB.
- Tier-2 batch (this commit) closes the user's stated tier-1 scope ("title and main control buttons"): `SKIN_GLYPH[128]` ASCII→UV table emitted from `CHAR_MAP` in `bake_skin.py`, golden hash committed at `gen/golden.sha256` (T025 now passing), ImageMagick CLI dep documented in `CLAUDE.md`.
- Tier 3 deferred until M3 wires the renderer: time digits (NUMBERS.BMP), play/pause indicator (PLAYPAUS.BMP), seek bar (POSBAR.BMP), title bar sprites (TITLEBAR.BMP), VOLUME/BALANCE/MONOSTER/SHUFREP, eject.
- Build wiring: standalone tool, manual invocation per user pref. `python3 tools/bake_skin.py -i skins/base-2.91.wsz -o SpotifyDiyThing/gen`. Determinism: `cd SpotifyDiyThing/gen && sha256sum -c golden.sha256`.

### TASK-009 — TLS connection lifecycle for non-GET endpoints
**Owner**: Developer (implementation), Architect (ADR-007)
**Feature**: api-002 (new — to be registered)
**Status**: done (2026-05-08 — DUT-verified, 14/15 spike rows [OK] in one run, 15th was a Marriott-WiFi getHttpStatusCode timeout, not a lib bug. Network was NOT the scapegoat — three additional structural lib bugs were found and patched.)
**Notes**:
- ADR-007 patch (`client->stop()` before each `connect()`) addresses the *first-write* 0x0050. Necessary but insufficient.
- Three further LOCAL_PATCHES required to actually pass the spike control surface (T001–T015):
  1. Removed trailing `client->println()` after body (was a false-negative health check that fired after the server's HTTP/1.0 implicit close).
  2. Made `Content-Type: application/json` conditional on a non-empty body. With `Content-Length: 0`, sending application/json caused Spotify to early-RST the connection (same 0x0050 numeric symptom).
  3. Kept `Content-Length` unconditional (Spotify returns 411 Length Required without it on POST/PUT, even empty-body).
  4. Replaced `return statusCode == 204` with `return statusCode >= 200 && statusCode < 300`. Spec says 204 but Spotify actually returns 200 for most player endpoints.
- All four documented in `Spotify-Diy-Thing/lib/SpotifyArduino/LOCAL_PATCHES.md`.
- Earlier user-side observation ("prev and fwd controls work via DUT touch") is now explained: Spotify was always actioning the request; the lib just couldn't see success due to strict-204 + the early-RST false negatives.
**Blocks**: M5 (full-skin touch controls), TASK-002, TASK-003
**Notes**:
- Discovered during TASK-007 DUT run 2026-04-29: every `POST` (`nextTrack`, `previousTrack`) and `PUT` (`pause`, `play`, `seek`, `setVolume`, `toggleShuffle`, `setRepeatMode`) fails at TLS-send with mbedTLS `0x0050 (NET_CONN_RESET)`. `GET /v1/me/player/currently-playing` works in the same boot from the same poll loop.
- Architect 2026-05-04: confirmed root cause via `lib/SpotifyArduino/src/SpotifyArduino.cpp` inspection. Library uses HTTP/1.0 (server closes after response) but never calls `client->stop()` between requests — only `client->flush()` then `connect()`. Arduino-ESP32 2.0.17 `WiFiClientSecure::connect()` on a peer-closed socket can succeed without re-handshaking, producing `0x0050` on the next write. ADR-007 selects **option 2** (insert `client->stop()` before each `connect()` in `makeRequestWithBody` + `makeGetRequest`). Options 1 and 3 rejected — 1 thrashes heap with no upside, 3 is a disproportionate library rewrite. Option 3 retained as pre-authorised fallback if verification partial-passes.
- Verification gate (VE): re-run spike harness rows `>` `<` ` ` `p` `P` `s` `S` `+` `-` `v` `h` `H` `r` `R` `o`; all must return `[OK]`. GET poll loop must remain healthy. Rows `f` / `a` stay 403 (TASK-010, out of scope here).

### TASK-018 — On-screen log overlay (M-LOG2)
**Owner**: Developer
**Feature**: log-002 (registered at implementation)
**Status**: done (2026-05-07 — DUT verified; user confirms green log text in top + bottom strips, chrome unaffected)
**Notes**:
- Roadmap entry: M-LOG2. Spec: log is full-screen 320×240 background; Winamp chrome paints on top and clips whatever it covers. Top strip (~7 lines) shows older history; bottom strip (~7 lines) shows new lines; middle ~16 lines hidden behind chrome — they scroll through but aren't seen. Subscribed to the existing 12 KB ringbuffer (no new state).
- TFT_eSPI built-in font 1 (~6×8 px), green-on-black. Lines truncated right (no wrap).
- Behind `#define SCREEN_LOG` (or a new `cyd2usb_winamp_screenlog` env). Default off — zero overhead when not built in.
- Update gating: dirty flag set by `ringPush`; redraw at ≤4 Hz to avoid SPI thrash.
- Redraw orchestration: each tick paints log full-screen, then re-blits the chrome (bg + transport buttons + status + title slot + posbar). Time-digit / progress-thumb / title-marquee updates already self-repaint over their slot from MAIN.BMP — they don't need to know the log exists.
- Diagnostic motivation: makes state-coupling problems (TASK-019) visible at the moment they affect the UI.
- DUT integration surfaced a blast-radius correction to ADR-010: Arduino-ESP32 redefines `ESP_LOGx` to its own `log_x` macros that bypass `esp_log_writev`. Our hook was effectively starved. Fix: new `LOG_I/W/D/E(tag, fmt, ...)` macros in `logSink.h` that format → Serial + `ringPush` directly. Migrated heartbeat + `spotify.poll` call sites. Other `ESP_LOGx` sites still work (Serial only) until migrated. ADR-010 amended.

### TASK-029 — M-PERF tier 1: loop-iteration + hot-path timing
**Owner**: Developer
**Feature**: perf-001 (registered alongside this commit)
**Status**: done (2026-05-08 — DUT-verified)
**Notes**:
- New `perf.h` namespace: `record(name, ms)`, `recordLoop(ms)`, `loopMaxMs()`, `worstPathName()`, `worstPathMs()`, `stackHwmBytes()`, `reset()`. Heartbeat consumes + resets each tick.
- `.ino` wraps top-level loop paths (`screenlog::tick`, `display.input`, `spotify.poll`, `display.bar`) with `millis()` brackets and emits `LOG_W("perf", "iter=Nms ...")` when an iteration > 50 ms.
- New heartbeat fields: `stack_hwm=Nb loop_max=Nms slow=<name>:Mms`.
- DUT data captured (see TASK-031 notes): touch handler dominates at up to 4 189 ms / iteration; polling secondary at 1.5–2 s; stack hwm ≈ 2 380 bytes (comfortable).

### TASK-030 — M-PERF tier 1: SPI clock A/B
**Owner**: Developer
**Status**: done (2026-05-08 — DUT-verified: 40 MHz reduces flicker; kept)
**Notes**:
- Flipped `SPI_FREQUENCY` 55 MHz → 40 MHz in `common_cyd.build_flags`. User-confirmed flicker improvement on the static Winamp chrome. Default kept at 40 MHz.
- Bonus finding (independent of TASK-030): with `SCREEN_LOG` enabled, the 4 Hz full-screen `fillScreen` + chrome-repaint cycle causes visible tearing. Without `SCREEN_LOG`, the chrome is stable. The screenLog overlay is fine for diagnostic use; don't ship it as the default. Already addressed by it being opt-in via `-DSCREEN_LOG`. Tier-2 follow-up (incremental-redraw / dirty-line diff) tracked separately for if/when on-screen logging gets used regularly — see TASK-029 follow-up notes / TASK-033.

### TASK-031 — M-PERF tier 2: async Spotify HTTP (poll + touch)
**Owner**: Architect (ADR-012 done), Developer (impl done)
**Status**: done (2026-05-08; ADR-012 + 031a/b/c/d shipped + DUT-verified — `loop_max` 4 191 ms → 16 ms; seek-during-poll race resolved; user confirms snappy UI).
**Notes**:
- ADR: `docs/architecture/decisions/ADR-012.md`. Per LL-010 the @VE / @Developer / @QM / @PM passes are folded inline. Status: `proposed` (transition to `accepted` once human signs off, per the LL-010 promotion candidate).
- Sub-task split (PM):
  - **TASK-031a**: skeleton — `spotifyTask.h` + storage TU + task creation wired into `.ino` + queue + snapshot scaffolding. Empty action handling. ~150 LOC.
  - **TASK-031b**: move `getCurrentlyPlaying` into the task. Loop reads snapshot. ~80 LOC.
  - **TASK-031c**: move `nextTrack/previousTrack/play/pause/seek` into the task. Touch handler enqueues. ~30 LOC.
  - **TASK-031d**: remove the 1.5 s deferred-repoll guard from M5 — race is gone (LL-015 no longer applies). ~10 LOC.
- VE follow-up: T060–T065 to be written at implementation time.
- Expected `loop_max`: 4 191 ms → < 100 ms (per ADR exit criterion).

### TASK-032 — M-PERF tier 2 ADR: DMA SPI for blits
**Owner**: Architect
**Status**: closed — ADR-013 verdict **deferred** (2026-05-08). DMA gains hinge on the CPU having non-SPI work to do during a blit; in our current shape, every blit is followed by another blit on the same bus, so CPU+DMA race for one shared resource. Revisit when (a) a non-display CPU consumer runs in parallel with blits — TASK-014 album-art decode is the main candidate, (b) the chrome surface grows materially (M-CHROME tier 2), or (c) we move to a wider data path. Cheap-win bracketing handed off to TASK-038.

### TASK-038 — `startWrite`/`endWrite` bracket multi-blit chrome paths
**Owner**: Developer
**Feature**: perf-001
**Status**: done (2026-05-08, DUT-verified — chrome renders identically, no transaction-state bugs)
**Notes**:
- Bracket `repaintChrome()`, `drawTitleText()`, `drawTransportButtons()`, `drawTimeDigits()`, and `screenLog::tick`'s render loop with `tft.startWrite()` / `tft.endWrite()`. Keeps CS asserted across the sequence; eliminates per-pushImage chip-select toggle + address-window setup overhead.
- Expected: ~3–10 % chrome-redraw cost reduction based on TFT_eSPI usage notes.
- ~10 LOC. No risk surface beyond "make sure every startWrite has a matching endWrite even on error paths."
**Notes**:
- `repaintChrome` (~32 KB) takes a few ms — non-issue at current cadence.
- `screenlog::tick`'s 4 Hz full-screen blit causes the user-observed tearing when the overlay is on. If the overlay graduates from "diagnostic only" to "regular use", DMA + dirty-line diff become worth doing. Not now.

### TASK-034 — Quick-win: drop the 80 ms touch-press hold delay
**Owner**: Developer
**Status**: done (2026-05-08, DUT-verified — press feedback still visible, loop no longer blocks during the hold)
**Notes**:
- `winampDisplay::checkForInput` does `delay(80)` between drawing the pressed sprite and drawing the released sprite. Loop task can't make progress during that 80 ms. After TASK-031 ships, the synchronous API call's ~2 s contribution disappears, but `delay(80)` would still be there.
- Replace with a millis-deadline state machine: pressed-until = now + 80; on next loop iteration after pressed-until, paint released. Always-helpful, ~10 LOC.
- Could ship before or with TASK-031.

### TASK-033 — M-PERF tier 3: implementation
**Owner**: Developer
**Status**: gated on TASK-031 / TASK-032 acceptance
**Notes**:
- Whichever of (async poll, DMA blits, screenLog incremental redraw, touch-debounce state-machine) the ADRs greenlight.
- Touch-debounce / press-hold state-machine: 80 ms `delay()` in checkForInput becomes a millis-deadline; release re-renders the unpressed sprite. Always helpful, no ADR needed; could land in this task or fold into the next M5-follow-up commit.

### TASK-023 — M-CHROME tier 1: bake-tool extension + atlases
**Owner**: Developer
**Feature**: chrome-001 (to be registered at impl)
**Status**: planned (2026-05-08)
**Notes**:
- Extend `tools/bake_skin.py`: load `MONOSTER.BMP` (58×24) + `SHUFREP.BMP` (92×85) from the .wsz; emit `SKIN_MONOSTER` / `SKIN_SHUFREP` arrays + sprite UVs in `gen/skin_layout.h`.
- MONOSTER sprite UVs: 29×12 each — `MONO` at (0,0), `STEREO` at (29,0), and a "lit" variant pair at (0,12) / (29,12). Confirm offsets against the source BMP at bake time.
- SHUFREP sprite UVs: 28×15 each (approx) — shuffle off/on (lit) at top row, repeat off/track/all at next rows. Layout per Winamp 2.x convention; derive from `92x85` dimensions.
- Re-bake; flash budget should land at ~98.4 %.

### TASK-024 — M-CHROME tier 1: mono/stereo + kHz/kbps strip
**Owner**: Developer
**Feature**: chrome-001
**Status**: planned (2026-05-08)
**Notes**:
- Render the MONOSTER strip at the canonical Winamp main-window position. Mono vs stereo selected by `currently_playing_type` (`track` / `episode` / `ad` / `unknown`): tracks render `STEREO`, episodes render `MONO`, others render unlit.
- kHz and kbps: Spotify Web API doesn't expose either. Hardcoded — `44` for kHz; `320` for kbps if Premium can be assumed (see `changelog-feb-2026-migration-guide.md` — Premium is now required for Dev Mode apps), else `--`.
- Renders text via the existing `SKIN_GLYPH` font atlas so no extra font work needed.

### TASK-025 — M-CHROME tier 1: shuffle / repeat indicator
**Owner**: Developer
**Feature**: chrome-001
**Status**: planned (2026-05-08)
**Notes**:
- Drive sprite selection from `shuffle_state` (boolean) and `repeat_state` (`off` / `track` / `context`). Already in the `currentlyPlaying` payload — no extra GET.
- Tap-on-sprite to toggle is M5 follow-up territory (touch-002 extension), not in this task. Tier 1 is render-only.

### TASK-039 — M-CHROME tier 2: extend SpotifyArduino parser for device.volume_percent
**Owner**: Developer
**Feature**: api-002 (lib patch family)
**Status**: planned (2026-05-09; ADR-014 sub-task 1)
**Notes**:
- Add `device.volume_percent` to the JSON filter in `SpotifyArduino::getCurrentlyPlaying`.
- Add `int volumePercent` field to `CurrentlyPlaying` struct (default `-1` = unknown / no device).
- Mirror the existing `currentlyPlayingType` extraction pattern.
- Document in `lib/SpotifyArduino/LOCAL_PATCHES.md`.

### TASK-040 — M-CHROME tier 2: bake-time static composite onto MAIN_BG
**Owner**: Developer
**Feature**: chrome-001 / m2-001
**Status**: planned (2026-05-09; ADR-014 sub-task 2-3)
**Notes**:
- Extend `tools/bake_skin.py` with composite mode: TITLEBAR active variant, BALANCE centered, kbps "192", kHz "44", static MS_STEREO_ON + MS_MONO_OFF.
- Drop MONOSTER.BMP from TIER3_SHEETS (after compositing). Remove SKIN_MONOSTER atlas + UV defines from gen/.
- Drop `winampDisplay::drawBitrateSampleRate()`, `drawMonoStereo()`, `redrawMetadataStrip()`, the snapshot-seq watcher block in `checkForInput`.
- Confirm visual via `--preview` eyeball before committing.

### TASK-043 — Switch primary poll to `/me/player` (unblock TASK-041)
**Owner**: Developer (impl), Architect (ADR-015), VE (T073 + T070a/b re-run)
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-10; ADR-015 §1–§5 implemented; T073 + T070a + T070b all PASS).
**Notes**:
- Lib URL change in `lib/SpotifyArduino/src/SpotifyArduino.h:68` — `SPOTIFY_CURRENTLY_PLAYING_ENDPOINT` flipped from `/v1/me/player/currently-playing?additional_types=episode` to `/v1/me/player?additional_types=episode`. Documented as LOCAL_PATCHES.md patch #8.
- Diag log added during T070a debug session (`spotifyLogic.h` `[D][chrome.diag]` Serial.printf) reverted in same commit — LL-010 hygiene.
- Side-fix discovered during T070b: 204 No Content path in `spotifyTaskStorage.cpp::doPoll` did NOT bump snapshot seq nor reset `volumePercent`, so the dedup gate suppressed the NONE redraw on session-close. Fix: 204 path now writes `g_snapshot.volumePercent = -1` and bumps seq under the spinlock, leaving track fields alone. ~5 LOC.
- T073 host-side test: `tools/test_player_endpoint_superset.py`. PASS — confirmed `/me/player` is a strict superset for every firmware-consumed field; `device.volume_percent=16` returned (Web Player active, supports_volume=true).
- T070a DUT: captured drawVolume transitions `pct=10 keyframe=0` → `pct=90 keyframe=4` against host-side toggle script (`/tmp/volume_toggle.py` 10↔90 every 12s). Visual: red max-fill bar at 90%.
- T070b DUT: captured `pct=-1 keyframe=NONE` (boot) → `pct=65 keyframe=3` (first poll) → `pct=-1 keyframe=NONE` (Web Player closed, 204 path triggered the 204-handler reset). All three transitions in serial; visual confirmed.
- ADR-015 OOS scope held: no rename, no extra fields surfaced, no refactor toward `getPlayerDetails`.

### TASK-042 — Manual BI_RLE8 decoder in bake_skin.py (silent-corruption fix)
**Owner**: Developer (impl), Architect (ADR-008 amendment), VE (regression)
**Feature**: m2-001
**Status**: done (2026-05-09; in-tree, not yet committed pending @VE regen of golden.sha256 and @Architect amend of ADR-008)
**Notes**:
- BALANCE.BMP composite was rendering as a 2-px thin strip surrounded by cyan. Diagnosis: Pillow 11.3.0's `BmpRleDecoder` mishandles the **delta opcode** (`00 02 dx dy`) in BI_RLE8 streams. base-2.91.wsz's BALANCE.BMP uses delta(9, 0) at the start of nearly every row (419 deltas across 433 rows) to encode a 9-pixel transparent left border compactly. PIL's decoder ignores the dx — pixel data lands at x=0..37 instead of x=9..46 — and produces silent garbage for ~56 % of pixels (16,588 of 29,444).
- ImageMagick fails outright on the same file (`unable to runlength decode image @ error/bmp.c/ReadBMPImage/1147`), so the existing magick fallback path (ADR-008 decision #8) does not catch this.
- ffmpeg decodes correctly. A 30-LOC manual BI_RLE8 decoder (`_decode_bmp_rle8` in `tools/bake_skin.py`) is byte-identical to ffmpeg.
- Fix: manual decoder is now the **primary** path for any BMP with `compression=1` (8 bpp RLE). Magick fallback retained for unrelated edge cases. PIL kept for non-RLE BMPs.
- Side effects: SKIN_MAIN_BG[] bytes change (now contains the real green balance bar, kbps/kHz text under proper decode, etc.). `gen/golden.sha256` is stale until VE regenerates.
- Process miss: this fix went in without TASK ID, ADR amendment, or VE regression. Captured in audit_log 2026-05-09 entry, lessons-learned LL-017.

### TASK-041 — M-CHROME tier 2: dynamic VOLUME slider
**Owner**: Developer
**Feature**: chrome-001
**Status**: done (2026-05-10; impl at b8f37d3..8075176; verification end-to-end via TASK-043 — see below).

**Implementation spec**: ADR-014 Amendment 1 §A1.1–A1.7 is authoritative. Original ADR-014 §3 wording is superseded — do not implement against §3 directly.

**Issues raised in 2026-05-10 Architect review and how each is closed**:

| # | Issue (from review) | Severity | Closed by |
|---|---|---|---|
| 1 | "Snapshot-seq watcher inside `checkForInput`" referenced by §3 was deleted in TASK-040 — drift between ADR and code. | medium | §A1.1 — render trigger moves to `spotifyLogic.h::updateCurrentlyPlaying`. |
| 2 | `updateCurrentlyPlaying`'s existing `isSameTrack` gate would suppress volume-only changes (volume can shift without a track change). | high | §A1.1 — `static int8_t lastVolumeRendered = -2;` value-cache, checked **before** the `isSameTrack` early-return. |
| 3 | Sentinel render unspecified — original ADR punted between "lowest keyframe", "skip", or "neutral", each wrong. | medium | §A1.2 — bake a dedicated 6th KEYFRAME_NONE (greyed empty track). Decision committed, not deferred. |
| 4 | VOLUME.BMP frame layout assumed canonical without inspection (LL-016 family — same shape as BALANCE.BMP's non-canonical-stride trap). | medium | §A1.3 — empirically inspected via `_decode_bmp_rle8` (uncompressed BMP, fell through to PIL); confirmed canonical 28×15-stride. Frames locked: 0, 7, 14, 20, 27. |
| 5 | "`spotifyTask::onCurrentlyPlaying`" wording in §3 — no such callback exists. | low | §A1.4 — corrected to "snapshot-write block of the poll-success branch in the task body". |
| 6 | On-screen position (107, 57) collision risk vs the now-baked TITLEBAR / kbps-text / BALANCE composite. | log-only | §A1.5 — verified non-colliding (3 px gap to BALANCE x=177; 8 px gap above kbps text at y=43-49). No change needed. |
| 7 | Atlas-surface accounting needs to include sentinel keyframe. | low | §A1.2 — 6 × 68×13 × 2 = 10,608 bytes. Fits in 18 KB flash headroom. |
| 8 | T070 acceptance was vague — no concrete pass criteria for VE. | medium | §A1.6 — split into T070a (real-volume render path) + T070b (sentinel transition). Both planned in `test_plan.md`. Both required before TASK-041 closes. |

**Internal commit ordering** per §A1.7: (1) bake atlas (5 source-frame keyframes + synthesised KEYFRAME_NONE), (2) snapshot field, (3) `drawVolume` renderer, (4) wire-in to `updateCurrentlyPlaying` + `repaintChrome`. Each step compiles cleanly on its own; steps 1–3 are dead code until step 4 — intentional, eases review.

### TASK-026 — M-CHROME tier-2 flash-budget ADR
**Owner**: Architect
**Status**: superseded by ADR-014 (2026-05-09 — composite-static reframe sidesteps the flash-budget question entirely; only VOLUME needs new atlas surface and at 5 keyframes it fits in the 18 KB headroom)
**Notes**:
- TITLEBAR/VOLUME/BALANCE atlases at full resolution = +178 KB, no fit. Decision: subset at bake time (one titlebar variant, ~8 volume keyframes, drop balance) vs partition resize vs lighter pixel format (palette-8) vs compress on flash + decompress at boot.
- ADR should land before TASK-027 / TASK-028 start.

### TASK-027 — M-CHROME tier 2: title bar render
**Owner**: Developer
**Status**: superseded by TASK-040 (2026-05-09 — title bar is now baked into MAIN_BG via the static-composite pass)

### TASK-028 — M-CHROME tier 2: volume slider + (maybe) balance
**Owner**: Developer
**Status**: superseded by TASK-040 (balance) + TASK-041 (volume) per ADR-014

### TASK-020 — M-LIST tier 1: top-align UI + playlist panel
**Owner**: Architect (orientation decision), Developer (impl)
**Feature**: playlist-001 (to be registered when impl starts)
**Status**: planned (2026-05-08)
**Notes**:
- Roadmap entry: M-LIST. Two orientations on the table:
  - **C (default lean)**: keep landscape; just shift `originY` from 62 to 0 in winampDisplay::displaySetup. Frees 320×124 below the chrome. One-line code change.
  - **B (portrait)**: `setRotation(0)`/`2` panel + 90° atlas rotation at bake time + layout-constant swap + touch coord swap + screenLog flip. Frees only 240×45 (3× less). Phone-like ergonomics.
- ADR needed before code: which orientation, where the playlist sits (below vs flanking), font choice (1 or 2), row count, current-track highlight style.
- Spotify Web API: `GET /me/player/queue` already snapshotted in `resource/web-api/player-endpoints.yaml`. Returns currently_playing + queue array.
- Cross-cuts: m3-001 (chrome positioning), touch-002 (taps below chrome region), log-002 (overlay layout).

### TASK-021 — M-LIST tier 2: tap-on-row plays that track
**Owner**: Developer
**Status**: planned (2026-05-08)
**Notes**:
- Touch hit-test on playlist rows; on tap, call `playAdvanced(body, deviceId)` with the row's track URI. Relies on TASK-020 layout being final.

### TASK-022 — M-LIST option B: portrait rotation
**Owner**: Developer
**Status**: planned (2026-05-08; only fires if TASK-020 ADR picks option B)
**Notes**:
- Bake tool extension: `--rotate 90` flag that 90°-rotates every BMP at bake time and rewrites the layout header's coords. Cheaper than runtime rotation.
- Touch coordinate swap (CYD28_TouchR setRotation or app-level x/y swap).
- ScreenLog overlay layout constants flip (PANEL_W ↔ PANEL_H, line-y math).

### TASK-019 — Decouple display from blocking network calls (M-IO)
**Owner**: Architect (ADR-011), then Developer
**Feature**: io-001 (registered with tier-1 implementation)
**Status**: tier-1 implementation shipped (2026-05-07; ADR-011 accepted)
**Notes**:
- Symptoms: slow first sync after boot; occasional hangs (clock + progress thumb stop); LCD shows previous track many seconds after Spotify advanced; heartbeat 56 s gaps observed during TLS retries.
- Diagnostic plan: enable TASK-018 (on-screen log) once shipped; let user observe blocking events live. Cross-reference with `/log?n=` ringbuffer dumps once a non-AP-isolated network is available.
- Likely contributors to investigate (none confirmed yet): TLS retry storms on captive-portal networks, 5 s `delayBetweenRequests` being too long for short tracks, synchronous `getCurrentlyPlaying` blocking the renderer for the full TLS+HTTP duration.
- Likely fixes (TBD ADR): aggressive timeouts; move HTTP off the main task; speculative re-poll on track-change indication.
- Exit criteria: heartbeat gap distribution < 5 s p95 across normal play.
- Tier 1 (ADR-011, 2026-05-07): exponential backoff on consecutive Spotify-poll failures (5 s → 10 → 20 → 40 → 60 s cap, reset on success or touch). Heartbeat now emits `block_max=Nms` — longest synchronous getCurrentlyPlaying since last tick. Touch-driven force-update also resets backoff so user input always escapes the back-off floor.
- Tier 2 (deferred): async IO / FreeRTOS worker task. Exit criteria for tier-1 sufficiency: with the on-screen overlay enabled during a Marriott-WiFi failure burst, the loop visibly keeps updating (heartbeat ticks within ±5 s of cadence). If `block_max` routinely exceeds 2.5 s and UI still hangs, escalate.

### TASK-016 — Logging redesign tier 1 (M-LOG, parent)
**Owner**: Developer (implementation), Architect (ADR-010 + amendments done), VE (T036–T040)
**Feature**: log-001 (registered at first implementation commit)
**Status**: tier-1 shipped (2026-05-07 — all five sub-tasks landed and DUT-verified except `/log` HTTP test which is gated on a non-AP-isolated network)
**Estimate**: ~half a day total across sub-tasks
**Notes**:
- Whiteboard: `docs/architecture/whiteboards/2026-05-07-logging-rethink.md`. ADR + amendments: `docs/architecture/decisions/ADR-010.md`. Review: `docs/architecture/decisions/ADR-010-review.md`.
- Split into independently-shippable sub-tasks (per @PM during review):

#### TASK-016b — Secret redactor + remove configFile.h JSON dump (security fix, ship first)
**Status**: shipped (Spotify-Diy-Thing@442b030, 2026-05-07). DUT-verified — three distinct redacted values render correctly (8-slot rotating pool needed; single-buffer aliased all printf args to the last value). Closes LL-002/LL-003 in-tree.
- New `secret.h` with `redact(s) -> "AQ…IY (len=131)"`. nullptr-safe, "" returns a non-empty marker.
- Remove the configFile.h JSON dump that prints refresh token + client secret on every boot.
- Commit message leads with security-fix framing for audit grep.

#### TASK-016a — esp_log hook + 12 KB ringbuffer + permanent post-connect HTTP server + /log
**Status**: shipped (Spotify-Diy-Thing@7f1009c, 2026-05-07). DUT-verified for boot trace + ESP_LOGI capture; `/log` HTTP test deferred (AP isolation on this network).
- `esp_log_set_vprintf` fans to Serial + ringbuffer. Line-oriented, drop-oldest, `portENTER_CRITICAL_SAFE` (works in ISR context too). 256-char line cap; one-time WARN tag=`log` on first truncation.
- Stand up a permanent HTTP server bound to `WiFi.localIP()` (not 0.0.0.0; not the WiFiManager portal one — that shuts down post-onboarding).
- `GET /log?n=N` plain text, last N lines. `GET /log?clear=1` empties. No auth — LAN-only is documented invariant.
- Default levels: INFO baseline; DEBUG for `display`, `spotify`, `time`; WARN for vendored tags (`HTTPClient`, `WiFiClient`, `ssl_client`, `mbedtls`).

#### TASK-016c — mbedTLS / HTTP decoder macros
**Status**: shipped (with TASK-016d in the same commit, 2026-05-07). DUT-verified — `[spotify.poll] fail http=HTTP -1` line shows decoder + ESP_LOGW path live.
- `LOG_TLS_ERR(rc)`: 0x0050, 0x004C, -9984, -76, -80 (more as discovered). `LOG_HTTP_ERR(code)`: 401, 403, 429, 5xx.
- Unknown codes pass through as raw hex / int — never silently dropped.

#### TASK-016d — 30 s heartbeat tick
**Status**: shipped, DUT-verified 2026-05-07. Heartbeat fires; counters track poll attempts/successes/last code. Long blocking calls (TLS retries) push the next tick out, which is the intended visibility — heartbeat surfaces opaque blocking. Required `-DCORE_DEBUG_LEVEL=3` to be effective.
- Super-loop `millis()` gate. Tag `hb`. Key=value pairs: `display=…`, `wifi=rssi(…)`, `heap=…k`, `poll=ok(204):N/last=…`, `uptime=HH:MM:SS`, `build=<epoch> <sha>`.
- Counters reset on reboot.

#### TASK-016e — `tools/audit_log_hygiene.sh`
**Status**: shipped with 016b (2026-05-07). Currently clean across the sketch. Run from `Spotify-Diy-Thing/`: `tools/audit_log_hygiene.sh`.
- Greps for banned patterns: `Bearer `, `client_secret=`, `Serial.print*` of names matching `*token*` / `*secret*` / `*refresh*`. Exit 1 on hit. Wire into review checklist; CI when CI exists.

**Migration policy**: incremental — new code uses `ESP_LOGx`; existing `Serial.println` stays until touched. Secret-leaking sites are fixed in tier 1 regardless.

**Follow-ups (post tier 1)**:
- After M3 + M5 close, lift `display` and `spotify` defaults from DEBUG to INFO. **Tracked as a checkpoint, not a task — Architect to revisit at each milestone close.**
- Promotion candidate (QM, awaiting human approval): "ADRs require @VE testability + @Developer implementability passes before transitioning to `accepted`."
- Out of scope for tier 1 (future TASK-017 if raised): UDP syslog push, state-machine trace points beyond natural call-site adoption, SPIFFS-backed buffer + panic flush, runtime per-tag control via web UI.

### TASK-015 — M3 Winamp display backend
**Owner**: Developer
**Feature**: m3-001 (new)
**Status**: done (2026-05-07 — DUT visual verify complete; all 8 items confirmed: bg, buttons, status indicator, time digits, title, marquee, progress thumb, touch press feedback)
**Notes**:
- Tier 1 (Spotify-Diy-Thing@e8f52b7): `winampDisplay.h` scaffold. Subclasses `CheapYellowDisplay`; reuses JPEG/SPIFFS/touch plumbing. New `cyd2usb_winamp` PIO env. Static bg + transport buttons + ASCII title.
- Tier 2 (Spotify-Diy-Thing@e4871e8): `bake_skin.py` now bakes NUMBERS/POSBAR/PLAYPAUS atlases + UVs. `winampDisplay.h` uses POSBAR sprite for bar+thumb, PLAYPAUS for status indicator, marquee scroll on title overflow, pressed-button feedback in `checkForInput`.
- Build: cyd2usb_winamp flash 88.6 → 96.6 % (atlas + render now linked); default cyd2usb env unchanged at 88.6 %. **Tight headroom — TITLEBAR/VOLUME/BALANCE atlases would push past 100 %; deliberately deferred.**
- `.ino` reorders `#if defined WINAMP_DISPLAY` ahead of `YELLOW_DISPLAY` because `cyd2usb_winamp` inherits `common_cyd`'s `-DYELLOW_DISPLAY`. Confirmed via section-GC nm dump.
- Verification gate (T033–T035): DUT flash, eyeball bg+buttons, title (long string for marquee), progress bar advance, press feedback. Pending next DUT session.
- Follow-ups: NUMBERS sprite use (time digits — currently DCE'd, no caller); seek/scrub on POSBAR touch; eject/shuffle/repeat/volume controls; 2× scaling (needs software upscaler).

### TASK-014 — Album art (i.scdn.co) fetch hang
**Owner**: Developer (investigation), Architect (if it leads to a TLS-stack choice)
**Feature**: poll-001 (regression surface)
**Status**: open (2026-05-07 — back-filled from audit)
**Notes**:
- Symptom (2026-05-06 Marriott captive portal session, post MAC pre-auth): DUT fetches Spotify currently-playing JSON cleanly, then hangs after logging `Removing existing image` in `cheapYellowLCD::displayImageUsingFile`. Subsequent watchdog/UI freeze; serial output from the poll loop also stops.
- Workaround in tree: `#define DISABLE_ALBUM_ART 1` in `.ino` skips the entire image fetch+decode path. Set in commit f84b112 to unblock M4 verification.
- Hypotheses to rule in/out: (a) JPEGDEC streaming hits an OOM under the new TFT_eSPI build; (b) i.scdn.co's CDN behind the captive portal returns a redirect/304 the lib doesn't handle; (c) the same WiFiClientSecure-reuse bug as TASK-009 but on the image-server cert path; (d) SPIFFS write-blocking on a fragmented FS.
- Diagnostic next step: capture serial with timing across the `getImage` call to localise the hang. May overlap with TASK-009 fix verification.

### TASK-010 — VU data-source rethink (ADR-002 invalidated)
**Owner**: Architect (decision), Developer (impl)
**Feature**: vu-001 (implemented)
**Status**: done (ADR-009 accepted 2026-05-07; M6 implementation shipped 2026-05-09 — Spotify-Diy-Thing@049c088 — synthetic envelope + 120 BPM beat clock + LFO stereo split + green/yellow/red colour grading)
**Blocks**: M6 (VU meter)
**Notes**:
- Discovered during TASK-007 DUT run 2026-04-29: both `/v1/audio-features/{id}` and `/v1/audio-analysis/{id}` return **HTTP 403** for the dev account's client app. Spotify deprecated these endpoints for new Developer apps as of late 2024 (announced via the Web API change-log). The app `db2ff394...` was created during TASK-001 (post-deprecation), so it has no access.
- ADR-002 ("VU meter sourced from Spotify `audio-analysis`, beat-synchronised") is therefore not implementable on this account.
- Options for a new ADR:
  - (a) Drop VU entirely. Skin renders the VU rect as static art.
  - (b) Synthesise a coarse VU from `currentlyPlaying` data only — track tempo (if Spotify still exposes it on the now-playing endpoint), elapsed-position, and a hand-tuned envelope. Not music-locked but might "look alive."
  - (c) Apply for Spotify "Extended Quota Mode" (manual approval, weeks, uncertain outcome). Restores audio-features/analysis access.
  - (d) On-device I2S microphone (ADR-002 option c, previously rejected). Real audio data, hardware addition, room-noise contamination.
- Recommend (b) for first cut — cheap, ships, doesn't block M2/M3/M5. Keep (c) on a second track as an upgrade path.
- 2026-05-07: ADR-009 accepted with **option (e) — synthesise from `currentlyPlaying` only** (option (a)'s premise also dead since `audio-features` is in the same deprecation). Implementation tier-1 will ship a 20 Hz envelope + flat-120 BPM beat clock + LFO stereo split. Extended-quota application kept as a parallel, non-blocking track. Feature `vu-001` description to be re-worded by Developer at implementation start.

## Blocked Tasks

_None._

## Completed Tasks

### TASK-013 — Hostile-network development shims (back-filled)
**Owner**: Developer
**Feature**: dev-001 (new)
**Status**: done (2026-05-06, code in tree; back-filled to PM tracker 2026-05-07)
**Git ref**: Spotify-Diy-Thing@bf5d5ca
**Notes**:
- Implemented across the 2026-05-05/06 session while debugging DUT on AT&T tethered hotspot then Marriott guest captive portal. Three orthogonal shims: hardcoded WiFi creds, SPIFFS-driven DNS override, HTTPS-Date time bootstrap with build-epoch fallback. All gated by file presence or compile flag — production captive-portal path unchanged.
- **Process gap (back-fill reason):** committed without a corresponding tasks.md entry, feature_inventory entry, or VE notification at the time. Caught by 2026-05-07 self-audit.
- No regression test. Manual verification was the field debug itself. VE backlog: smoke test for dnsOverride loads + answers from SPIFFS JSON; build-epoch fallback path coverage.

### TASK-011 — M4 position interpolation polish
**Owner**: Developer
**Feature**: poll-002
**Status**: done (2026-05-07, DUT visually verified — "alright-ish, good enough")
**Git ref**: Spotify-Diy-Thing@f84b112
**Notes**:
- Pre-existing interpolation in `spotifyLogic.h` (`songStartMillis = millis() - progressMs`) was already correct; this task closed the rendering-side gaps.
- Idempotent `displayTrackProgress` in `cheapYellowLCD.h` caches last `barXWidth`, no-ops on identical pixel position. Track-change / seek-back handled via shrink-branch full repaint.
- `delayBetweenProgressUpdates` 500ms → 100ms. Safe because of idempotency.
- `displayTrackProgress` direct call retained in `handleCurrentlyPlaying` for pause-state correctness (`updateProgressBar` idles when not playing).
- Album art rendering gated behind `DISABLE_ALBUM_ART` in `.ino` — orthogonal i.scdn.co fetch hang, not part of this task.
- Closes ADR-006 M4 minimal scope. Local-seek field updates remain unwired pending TASK-009 (M5).

### TASK-007 — M1 API capability spike harness
**Owner**: Developer
**Feature**: api-001
**Status**: done (2026-04-29, DUT verified — with two new follow-ups, see below)
**Git ref**: Spotify-Diy-Thing@6066cab + (rotation/cleanups commit pending)

**Per-row results (DUT run 2026-04-29 after TASK-006 rotation + time-001):**

| Key | Action | Result | Detail |
|-----|--------|--------|--------|
| `>` | nextTrack | **FAIL** | Library returned false. Root cause: mbedTLS `0x0050` on `client->println()` send. POST never reached Spotify. |
| `<` | previousTrack | not run | Same path as `>`; would fail identically. |
| ` ` | toggle | not run | Dispatches to play/pause; same PUT path failure. |
| `p` | play | not run | PUT path; same failure. |
| `P` | pause | **FAIL** | mbedTLS `0x0050` on send. PUT never reached Spotify. |
| `s` | seek 30000 | not run | PUT path; same failure. |
| `S` | seek 0 | not run | PUT path; same failure. |
| `+` `-` `v` | setVolume | not run | PUT path; same failure. |
| `h` `H` | shuffle | not run | PUT path; same failure. |
| `r` `R` `o` | repeat | not run | PUT path; same failure. |
| `f` | audio-features | **HTTP 403** from Spotify | `code=403 clen=-1`. Endpoint deprecated for new Developer apps as of late 2024. Connection-level: TLS round-trip succeeded; the library reached Spotify and got an authoritative 403. |
| `a` | audio-analysis (16K) | **HTTP 403** from Spotify | Same deprecation. |
| `A` | audio-analysis (32K) | not run | Same deprecation; doc-size fallback irrelevant. |
| `i` | info / heap / clock | **OK** | `heap=218808 track=7fUr8EpRc0AC4MCPMVPIgI playing(assumed)=1 vol(local)=50` and `time epoch=1777445587 utc=2026-04-29T06:53:07Z sane=1`. T019 + T020 passing. |

GET `/v1/me/player/currently-playing` runs every 5 s in the background poll loop and **succeeds repeatedly** (`Successfully got currently playing`), confirming auth is healthy and the library's GET path works.

**Decisions recorded at exit:**

1. **SpotifyArduino extension strategy — closed.** Vendoring + `getBearerToken()` patch is *not* sufficient. The library's reuse of a single `WiFiClientSecure` across heterogeneous request types (GET + POST + PUT) breaks at TLS-send level for non-GET on Arduino-ESP32 2.0.17. A fresh client per non-GET (or migration to Arduino's `HTTPClient`, which manages connection lifecycle internally) is required for production wiring. Worth a new ADR before M5.

2. **`audio-analysis` doc size — moot.** Endpoint returns 403 for this app, so cache sizing is unanswerable from this spike. ADR-002's primary VU data source is unavailable; M6 needs a new strategy. Worth a new ADR superseding ADR-002.

**Follow-ups opened:**
- **TASK-009** — TLS connection lifecycle: pick a fix (per-request fresh client / `HTTPClient` migration) and verify all PUT/POST endpoints recover. Blocking M5.
- **TASK-010** — VU data source rethink: ADR-002 invalidated. Decide between (a) drop VU, (b) synthesised-from-poll-data VU (e.g. fake envelope from `currentlyPlaying.tempo` if exposed), (c) apply for Spotify Extended Quota Mode, (d) on-device microphone (ADR-002 option c, previously not chosen). Blocking M6.

### TASK-006 — Rotate leaked refresh token + client secret
**Owner**: Developer
**Status**: done (2026-04-29)
**Git ref**: Spotify-Diy-Thing config (data/spotify_diy_config.json, gitignored) + (commit pending for example file move)
**Notes**:
- Spotify auto-revoked the leaked refresh token between bring-up (2026-04-26) and this run (`invalid_grant — Refresh token revoked` returned 2026-04-28). Their leak-scanner caught it from the chat transcript. LL-002.
- Rotation completed 2026-04-29: dashboard secret rotated, `get_refresh_token.py` produced a new refresh token via loopback flow, both written to `data/spotify_diy_config.json`, `uploadfs` flashed. Boot now shows `Successfully got currently playing` repeatedly.
- Concurrent fixes during rotation:
  - `SPOTIFY_DEBUG` disabled in vendored `lib/SpotifyArduino/src/SpotifyArduino.h` so the new credentials don't bleed onto serial like the old ones did. LL-003 action item.
  - `data/spotify_diy_config.example.json` moved to `Spotify-Diy-Thing/spotify_diy_config.example.json` (project root) — its 32-char path tripped SPIFFS's filename-length limit and broke `uploadfs`. The example file was never meant to be on-device anyway.
- TASK-004 NFC verification rode along: no `NFC Bad` line in this boot's log. NFC silenced as intended.

### TASK-008 — NTP sync at boot (time-001)
**Owner**: Developer
**Feature**: time-001
**Status**: done (2026-04-28, DUT verified)
**Git ref**: Spotify-Diy-Thing@c0c4950, esp_spotify@5e94a9f
**Notes**:
- Root cause for the 2026-04-28 DUT TLS failure (`status Code-1`, `_handle_error 0x0050`). ESP32 has no RTC and the firmware never called `configTime()`, so mbedTLS rejected Spotify's certs whose `notBefore` is in the future.
- `setup()` now calls `configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com")` immediately after WiFi-up, then waits up to 5 s for `time(nullptr) > 1700000000` (2023-11-14). Non-fatal on timeout — logs `[time] WARN ...` and proceeds so the failure mode stays distinguishable.
- Spike harness `i` command extended: also prints epoch + ISO-8601 UTC + `sane=0|1` so T019/T020 verify the fix.
- Both `cyd2usb` and `cyd2usb_spike` envs build clean.
- DUT verification 2026-04-28: `[time] synced epoch=1777404307 in 3400ms`. `i` returned `[INFO] time epoch=1777404345 utc=2026-04-28T19:25:45Z sane=1`. Subsequent `Refreshing Access Tokens` returned **HTTP 400 `invalid_grant — Refresh token revoked`** from Spotify — confirms time-001 alone closed the TLS-validation issue; remaining failure is purely credentials. The trailing `0x0050` log is the library re-using a closed client after the 400 (cosmetic).
- Cross-feature interaction recorded: `cross_feature_matrix.yaml:X001` (time-001 → auth-001, dependency, risk: high).
- Conclusion: time-001 done. The "TLS issue" suspicion is closed; further work blocked on TASK-006 (rotation) only — the leaked refresh token has been auto-revoked by Spotify's leak scanner, exactly the failure TASK-006 anticipated.

### TASK-004 — NFC posture: disabled on this dev unit
**Owner**: PM (decision) → Developer (change)
**Status**: done (2026-04-28)
**Notes**:
- PN532 not wired on this dev unit; boot was logging harmless `NFC Bad`.
- Commented out `#define NFC_ENABLED 1` in `Spotify-Diy-Thing/SpotifyDiyThing/SpotifyDiyThing.ino:28`. Code uses `#ifdef NFC_ENABLED` (4 sites), so commenting — not setting to `0` — is what disables it. Comment block records the intent and the gotcha.
- `nfc.h` source kept; re-enable by uncommenting if a reader is wired later.
- Verification deferred until DUT is reachable (TASK-006-style).

### TASK-005 — Secret hygiene (gitignore + example template)
**Owner**: Developer
**Status**: done (2026-04-28)
**Notes**:
- Added `data/spotify_diy_config.json` to `Spotify-Diy-Thing/.gitignore` (file-specific, not whole `data/`).
- Added `Spotify-Diy-Thing/data/spotify_diy_config.example.json` with REPLACE_ME placeholders as the trackable template.
- Verified with `git check-ignore`: real config ignored, example trackable. Real secret was never committed (pre-existing untracked state).

### TASK-001 — Bring up first dev unit (CYD2USB)
**Owner**: Developer
**Feature**: deploy-001
**Status**: done
**Git ref**: working tree (Spotify-Diy-Thing untracked)
**Notes**:
- Pinned `platform = espressif32@6.9.0` in `Spotify-Diy-Thing/platformio.ini` — repo's unpinned line broke against current PlatformIO (`Network.h` missing in newer Arduino-ESP32 cores).
- Built + flashed `cyd2usb` env (TFT_INVERSION_ON) over `/dev/ttyUSB0`.
- Spotify dashboard's new redirect-URI policy (loopback HTTP only) breaks the on-device OAuth flow. Worked around with off-device `get_refresh_token.py` (loopback `127.0.0.1:8888`), then baked refresh token + client creds into SPIFFS via `data/spotify_diy_config.json` + `pio run -t uploadfs`.
- Wifi configured via WiFiManager captive portal. Device polling Spotify Web API; renders track on next playback.
- Deployment procedure documented in `docs/first_time_run_deploy.md`.

## Backlog (initial PM assessment)

To be triaged with the team.

### TASK-035 — Drop OTA `app1` partition (reclaim 1.25 MB flash)
**Owner**: Architect → Developer
**Status**: parked (2026-05-08; revisit if M-CHROME tier 2 hits the flash wall)
**Notes**:
- Default Arduino-ESP32 partition CSV reserves a second 1.25 MB `app1` slot for OTA. We never call OTA. Single-line custom `partitions.csv` reclaims it. Would push `cyd2usb_winamp`'s effective ceiling from 1 280 KB to 2 560 KB.
- Cost: lose OTA capability. Acceptable for this project. Revert is just removing the custom CSV.
- Not needed today (97.8 % of 1 280 KB used; 28 KB free). Keep parked until M-CHROME tier 2 (TITLEBAR + VOLUME + BALANCE = +178 KB) actually needs it.

### TASK-036 — Compress skin atlas (palette-8 with runtime LUT or PNG-on-flash)
**Owner**: Architect (ADR), Developer (impl)
**Status**: parked (2026-05-08; alternative path if TASK-035 isn't enough)
**Notes**:
- Current atlas is raw RGB565 = 2 B/px. ~96 KB total. Most of those pixels are duplicates (chrome, button frames). A palette-8 + 256-entry RGB565 LUT cuts the bake to ~½ size at the cost of an indirection in `blitSprite`.
- PNG-on-flash + decompress at boot is heavier (~50 KB extra code for libpng), uses heap. Probably not worth it on this board.
- Bake-tool change + `winampDisplay.h` `blitSprite` change. ~100 LOC + ADR.

### TASK-037 — Strip unused TFT_eSPI font sets
**Owner**: Developer
**Status**: parked (2026-05-08; small win, easy)
**Notes**:
- `common_cyd.build_flags` enables `LOAD_FONT2/4/6/7/8/GLCD/GFXFF`. We only render via the baked Winamp glyph atlas (custom path, doesn't touch TFT_eSPI fonts) and via `screenLog` font 1 GLCD. Drop everything except `LOAD_GLCD`.
- Saves a few KB rodata. Verify no regression in screenLog or any legacy `cheapYellowLCD` text fallback.

- **TASK-002** — Touchscreen seek/scrub. ✅ closed 2026-05-08 by M5 (tap-to-seek shipped; drag-with-debounce deferred to a follow-up if/when it's wanted).
- **TASK-003** — Play/pause + volume on touch. Play/pause closed 2026-05-08 by M5. Volume deferred — not on the main-window chrome we render today; needs VOLUME.BMP baked + a slot reserved.
- **TASK-004** — Decide NFC support posture. Reader not connected on dev unit; boot logs `NFC Bad` harmlessly. Either wire a PN532 and validate, or set `NFC_ENABLED 0` to silence. Owner: PM (decision).

---

## Entry Format

```
### TASK-001 — [Title]
**Owner**: Developer | VE | QM | PM
**Feature**: F001 (if applicable)
**Status**: todo | in_progress | blocked | done
**Git ref**: branch name or commit SHA
**Blocked by**: (if applicable)
**Notes**:
```
