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
**Status**: done (2026-05-15 — touch press-hold state machine landed via pendingReleaseAt/PRESS_HOLD_MS; TASK-034 closed 80 ms delay; DMA deferred per ADR-013; async poll done in TASK-031)
**Notes**:
- Whichever of (async poll, DMA blits, screenLog incremental redraw, touch-debounce state-machine) the ADRs greenlight.
- Touch-debounce / press-hold state-machine: 80 ms `delay()` in checkForInput becomes a millis-deadline; release re-renders the unpressed sprite. Always helpful, no ADR needed; could land in this task or fold into the next M5-follow-up commit.

### TASK-023 — M-CHROME tier 1: bake-tool extension + atlases
**Owner**: Developer
**Feature**: chrome-001 (to be registered at impl)
**Status**: done (2026-05-15 — SKIN_SHUFREP 75×30 atlas emitted (TASK-025); MONOSTER composited into MAIN_BG per ADR-014 (TASK-040); SKIN_SHUFREP in gen/skin_assets.c, constants in gen/skin_layout.h)
**Notes**:
- Extend `tools/bake_skin.py`: load `MONOSTER.BMP` (58×24) + `SHUFREP.BMP` (92×85) from the .wsz; emit `SKIN_MONOSTER` / `SKIN_SHUFREP` arrays + sprite UVs in `gen/skin_layout.h`.
- MONOSTER sprite UVs: 29×12 each — `MONO` at (0,0), `STEREO` at (29,0), and a "lit" variant pair at (0,12) / (29,12). Confirm offsets against the source BMP at bake time.
- SHUFREP sprite UVs: 28×15 each (approx) — shuffle off/on (lit) at top row, repeat off/track/all at next rows. Layout per Winamp 2.x convention; derive from `92x85` dimensions.
- Re-bake; flash budget should land at ~98.4 %.

### TASK-024 — M-CHROME tier 1: mono/stereo + kHz/kbps strip
**Owner**: Developer
**Feature**: chrome-001
**Status**: superseded by TASK-040 (2026-05-09 — the strip is now baked statically into MAIN_BG via the ADR-014 composite path; no runtime renderer)
**Notes**:
- Bake-tool `composite_static_decoration` paints `MS_MONO_OFF` at (212, 41) and `MS_STEREO_ON` at (241, 41), plus glyph-composited `kbps "192"` at (110, 43) and `kHz "44"` at (156, 43). All four are decorative now — `currently_playing_type` driven mono/stereo was descoped along with TASK-040 since Spotify doesn't expose kHz/kbps anyway.

### TASK-025 — M-CHROME tier 1: shuffle / repeat indicator
**Owner**: Developer
**Feature**: chrome-001 / touch-002
**Status**: done (2026-05-15 — render + tap-toggle DUT-verified on home network; shuffle/repeat sprites visible, tap-toggle confirmed working by user)
**Notes**:
- Bake (`tools/bake_skin.py`): added `build_shufrep_atlas` packing 4 normal-state sprites (REPEAT off/on, SHUFFLE off/on) into a 75×30 atlas (4500 bytes flash). Pressed states intentionally skipped — tap feedback is implicit in the state flip.
- Lib (LOCAL_PATCHES patch #9): extended `getCurrentlyPlaying` filter + parser to surface `shuffle_state` and `repeat_state` on the existing `/me/player` poll. Added `bool shuffleState` + `RepeatOptions repeatState` to `CurrentlyPlaying`.
- Snapshot: added `bool shuffleState` + `int8_t repeatState` to `spotifyTask::Snapshot`. Defaults `false` / `2 (off)`. Written under spinlock by `onCurrentlyPlaying`.
- Renderer (`winampDisplay.h`): `drawShuffle(int)` / `drawRepeat(int)` overrides blit from SKIN_SHUFREP at canonical (164, 89) / (210, 89). Cached in `lastShuffleRendered` / `lastRepeatRendered`. Both paint in `repaintChrome` after blitMainBackground.
- Tap dispatch: `hitTestShuffle` / `hitTestRepeat` slot tests; tap toggles shuffle (off↔on) and cycles repeat (off → context → track → off, snapshot encoding 2 → 1 → 0 → 2). Optimistic UI paints the new sprite immediately; freeze window (`SHUFREP_OPTIMISTIC_HOLD_MS=2000`) gates the snap-driven redraw in `spotifyLogic.h`. ACT_SHUFFLE / ACT_REPEAT enqueued to `spotifyTask`; task body calls `s_spotify->toggleShuffle` / `setRepeatMode` then re-polls (matches NEXT/PREV/PLAY pattern; volume skips repoll because of drag-burst, shuffle/repeat are single events).
- Visual: tier 1 plan was render-only but the touch toggle came along with it because the M5 plumbing was already in place. Pressed-state sprites still deferred (would have doubled the SHUFREP atlas to 9 KB; we're at 4.5 KB now).

### TASK-046 — Decorative eject button bake
**Owner**: Developer
**Feature**: chrome-001
**Status**: done (2026-05-10 — visible in `gen/skin_preview.png`; no runtime code).
**Notes**:
- Composite `CBUTTONS.BMP (114, 0, 22, 16)` onto `MAIN_BG (136, 89)` in `tools/bake_skin.py::composite_static_decoration`. CBUTTONS was already loaded for the transport-button atlas; passed as a pre-baked source via `composite_sources.setdefault("CBUTTONS.BMP", cbut_bmp)` to avoid re-opening the zip entry.
- Static composite — eject has no Spotify equivalent (closest semantic is `transferPlayback` to a non-Spotify endpoint, not useful), so render-only.
- 0 bytes runtime cost (paints once at bake time into `SKIN_MAIN_BG`).

### TASK-039 — M-CHROME tier 2: extend SpotifyArduino parser for device.volume_percent
**Owner**: Developer
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-10 — SpotifyArduino.cpp:791-868; filter["device"]["volume_percent"] + currentlyPlaying.volumePercent field; LOCAL_PATCHES documented)
**Notes**:
- Add `device.volume_percent` to the JSON filter in `SpotifyArduino::getCurrentlyPlaying`.
- Add `int volumePercent` field to `CurrentlyPlaying` struct (default `-1` = unknown / no device).
- Mirror the existing `currentlyPlayingType` extraction pattern.
- Document in `lib/SpotifyArduino/LOCAL_PATCHES.md`.

### TASK-040 — M-CHROME tier 2: bake-time static composite onto MAIN_BG
**Owner**: Developer
**Feature**: chrome-001 / m2-001
**Status**: done (2026-05-10 — composite_static_decoration() in bake_skin.py: TITLEBAR active, BALANCE centred, kbps "192", kHz "44", MS_STEREO_ON + MS_MONO_OFF; MONOSTER dropped from runtime atlas; drawBitrateSampleRate/drawMonoStereo/redrawMetadataStrip removed)
**Notes**:
- Extend `tools/bake_skin.py` with composite mode: TITLEBAR active variant, BALANCE centered, kbps "192", kHz "44", static MS_STEREO_ON + MS_MONO_OFF.
- Drop MONOSTER.BMP from TIER3_SHEETS (after compositing). Remove SKIN_MONOSTER atlas + UV defines from gen/.
- Drop `winampDisplay::drawBitrateSampleRate()`, `drawMonoStereo()`, `redrawMetadataStrip()`, the snapshot-seq watcher block in `checkForInput`.
- Confirm visual via `--preview` eyeball before committing.

### TASK-045 — M-CHROME tier 2.5: drag-to-set volume control
**Owner**: Developer (impl), Architect (ADR-016), VE (T074 + T075)
**Feature**: chrome-001, touch-002 (extension family)
**Status**: done (2026-05-10; ADR-016 §5-§10 implemented; user-confirmed "works perfectly").
**Notes**:
- `ACT_VOLUME` added to `spotifyTask::Action` enum + dispatch case in `spotifyTaskStorage.cpp::taskBody` (no `doPoll()` after — drag-burst guard per ADR-016 §9). Calls `s_spotify->setVolume((int)req.param)` which accepts any 2xx (LOCAL_PATCHES patch #6).
- `hitTestVolume(sx, sy)` mirrors `hitTestPosbar` shape — returns `0..100` percent if inside `(originX + VOLUME_X, originY + VOLUME_Y, 68, 13)`, else `-1`.
- Drag state machine in `WinampDisplay`: `D_IDLE` ↔ `D_VOLUME_DRAG`. Transition on first hit inside the slot; transition back on the loop iteration where `ts.touched()` returns false. Drag-end commits a final `ACT_VOLUME(lastVolumeRendered)` if it diverges from `lastVolumeEnqueuedPct`.
- Debounce: ACT_VOLUME enqueued at most once per 300 ms during drag (`VOLUME_DRAG_DEBOUNCE_MS`), unconditionally on drag-end. Bounds queue depth at ~1 in practice.
- Optimistic-UI freeze (LL-015): `optimisticVolumeUntilMs = millis() + 2000` set on every drag sample. `WinampDisplay::getOptimisticVolumeUntil()` overrides the new base-class virtual on `SpotifyDisplay`. `spotifyLogic.h::updateCurrentlyPlaying` gates the snap-driven `drawVolume` dedup on `millis() >= getOptimisticVolumeUntil()`. Stops the next regular poll's stale `volumePercent` from re-anchoring the slider over the user's chosen value before Spotify commits.
- Build: cyd2usb_winamp clean. Flash 99.2 % → 99.3 % (+492 bytes used: 0 new atlas, ~492 bytes code), 9.4 KB free.
- DUT verify: captured drag samples and drag-end commits across multiple drag sessions. Sample log:
  ```
  drawVolume pct=58→61→62  →  drag-end commit pct=62
  drawVolume pct=67→...→70 →  drag-end commit pct=70
  spotify.task dequeued action=VOLUME param=71, 56, 34, 25, 38, 62, 67, 70
  ```
- T074 (drag dispatches setVolume): PASS — 8 ACT_VOLUME dispatches during drag session, all accepted by Spotify.
- T075 (optimistic-UI freeze prevents flicker): PASS — user-confirmed no snap-back during/after drag.
- ADR-016 OOS scope held: snap-to-bucket NOT implemented (linear values), pressed-state knob NOT introduced, no cross-drag.

### TASK-044 — M-CHROME tier 2.5: display-only volume knob
**Owner**: Developer (impl), Architect (ADR-016)
**Feature**: chrome-001
**Status**: done (2026-05-10; ADR-016 §1-§4 implemented; user-confirmed visual all 5 keyframe buckets + sentinel).
**Notes**:
- Bake (`tools/bake_skin.py`): added `extract_volume_knob` + `AUX_SPRITES` plumbing. Knob crop `(15, 422, 14, 11)` from BALANCE.BMP emitted as `SKIN_VOLUME_KNOB[14*11]` (308 bytes) — separate atlas, not padded into SKIN_VOLUME (saves 1.2 KB vs the wider-row alternative). Per-element review PNG `gen/composite/volume_knob.png`.
- Layout (`gen/skin_layout.h`): added `VOLUME_KNOB_W=14`, `VOLUME_KNOB_H=11`, plus `VOLUME_W=68` / `VOLUME_H=13` for the runtime to compute the knob travel range.
- Render (`winampDisplay.h::drawVolume`): after the keyframe blit, if `clamped >= 0`, blit the knob at `originX + VOLUME_X + (clamped * 54) / 100, originY + VOLUME_Y + 1`. Skipped on sentinel per ADR-016 §4.
- Knob sprite is fully filled (no cyan border pixels) — verified by per-pixel scan of the cropped 14×11 image; `blitSprite(...)` works without a colour-key path.
- Build: cyd2usb_winamp clean. Flash 99.2 % → 99.2 % (+432 bytes used: 308 atlas + ~124 code), 9.9 KB free remaining.
- Bake determinism: re-bake byte-identical; `golden.sha256` regenerated.
- DUT verify: drawVolume sequence captured at boot + 4 distinct buckets (`pct=-1 NONE`, `pct=17 KF0`, `pct=51 KF2`, `pct=65 KF3`, `pct=98 KF4`). User visually confirmed knob tracks position correctly; colour sprite changes match keyframe bucket.
- Touch control (TASK-045) intentionally NOT in scope — display-only first per ADR-016 §12.

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
**Status**: done (2026-05-09; ADR-008 amended 2026-05-09 with BI_RLE8 decision; golden.sha256 regenerated by TASK-044 bake run — sha256sum -c passes as of 2026-05-21)
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
**Owner**: Developer
**Feature**: playlist-001
**Status**: done (2026-05-15 — DUT-verified, user confirmed playlist panel visible)
**Notes**:
- ADR-017 accepted. Orientation C, `GET /me/player/queue`, Font 2, 7 rows.
- **020a**: `originY = 0` — chrome flush to top edge. Also fixed VU meter hardcoded origin → `chromeOriginX()/chromeOriginY()` getters (bug: VU was stuck at old centered position).
- **020b**: `getQueue()` added to `SpotifyArduino` (LOCAL_PATCHES pattern). `QueueSnapshot` struct + `g_queueMux` spinlock in `spotifyTask`. Poll trigger: track-change detection in `onCurrentlyPlaying` + 60 s keepalive. `queueBufferSize = 6000` (3000 was insufficient for 20 filtered queue items).
- **020c**: `drawPlaylist()` in `winampDisplay.h` — seqno-diff + 1 Hz rate gate; `fillRect` strip + 7 rows Font 2; row 0 gold highlight + white text, rows 1-6 Winamp grey-green. Seqno check and draw call in main loop under `#ifdef WINAMP_DISPLAY`.
- Scope: `user-read-playback-state` covers queue endpoint — no token regeneration needed (returned 200, not 403).
- Flash: 50.0 % (stable). RAM: +1 KB for QueueSnapshot.

### TASK-050a — M-VIS: VisMode enum + toggle dispatch + blank mode
**Owner**: Developer
**Feature**: vis-001 (new)
**Status**: done (2026-05-16 — VisMode enum + nextMode() + blitVisBackground() + hitTestVis() + mode dispatch in tick(); compile-verified)
**Blocks**: TASK-050b, TASK-050c (need mode dispatch before adding renderers)
**Notes**:
- Add `enum VisMode { VIS_VU, VIS_SPECTRUM, VIS_WAVE, VIS_BLANK };` to `vuMeter.h` namespace.
- Add file-static `VisMode s_mode = VIS_VU;` inside `vuMeter.h`.
- `nextMode()`: cycles `VIS_VU → VIS_SPECTRUM → VIS_WAVE → VIS_BLANK → VIS_VU`.
- `currentMode()`: returns `s_mode`.
- Update `tick()` signature: `void tick(int originX, int originY, const uint16_t *mainBg)` (adds `mainBg` — TASK-049 change folded in here; these two tasks should land together).
- Dispatcher in `tick()`: `switch(s_mode) { VIS_VU: tickVU(); VIS_SPECTRUM: tickSpectrum(); VIS_WAVE: tickWave(); VIS_BLANK: blitVisBackground(); }`.
- `blitVisBackground(originX, originY, mainBg)`: restores `SKIN_MAIN_BG` rows for the full vis area `(RECT_X=24, LEFT_Y=43, RECT_W=76, VIS_H=16)`.
- **Vis area constants** (add to `vuMeter.h`): `VIS_H = 16` (R&D confirmed y=43..58; **not** 13 — old formula `RIGHT_Y + RECT_H - LEFT_Y` gives VU height, not full spectrum height). Also add `SPEC_BARS=19`, `SPEC_BAR_W=3`, `SPEC_BAR_STEP=4`.
- **Touch hit-test** (`winampDisplay.h`): add `bool hitTestVis(int sx, int sy)`:
  - Bounds: `sx in [originX+RECT_X, originX+RECT_X+RECT_W)` AND `sy in [originY+LEFT_Y, originY+LEFT_Y+VIS_H)` (y=originY+43..58).
  - Confirm no overlap with existing hit-test zones (transport at y=originY+88..106; all clear).
- Wire `hitTestVis` into `checkForInput()`: on tap inside vis area → `vu::nextMode()`. No API action, no optimistic freeze.
- TASK-049 is a prerequisite for this task's `blitVisBackground`; implement together or immediately before.
- **Authoritative spec:** `docs/architecture/designs/M-VIS-visualization.md` (updated 2026-05-16).

### TASK-050b — M-VIS: spectrum analyzer view
**Owner**: Developer
**Feature**: vis-001
**Status**: done (2026-05-16 — 19 bars × 3px, VIS_ROW_COLOR gradient, grey peak dots 3px wide, decay 1/VIS_H per tick; compile-verified)
**Notes**:
- **Authoritative spec:** `docs/architecture/designs/M-VIS-visualization.md`. Summary of corrections from original 2026-05-15 notes:
  - **19 bars** (not 38): 3px wide + 1px gap = 4px step. `barX = originX + RECT_X + i * 4`.
  - **Colour by absolute row:** `VIS_ROW_COLOR[r]` where `r = pixel_y - (originY + LEFT_Y)`. NOT threshold-based green/yellow/red.
  - Per-bar draw is a row loop: `for (r = VIS_H - barH; r < VIS_H; r++) tft.drawFastHLine(barX, originY+LEFT_Y+r, 3, VIS_ROW_COLOR[r]);`
  - **Peak decay:** `specPeak[i] -= 1.0f / VIS_H;` (~0.0625f, 1 row per 50ms tick). Old `0.008f` was wrong (≈480ms/row, far too slow).
  - **Peak dot:** `tft.drawFastHLine(barX, originY+LEFT_Y+peakRow, 3, VIS_PEAK_COLOR)` — 3px wide (full bar width), colour `0x94B2`. Not `drawPixel`.
  - **Dedup arrays:** `lastBinH[19]` + `lastPeakRow[19]`.
- **Bin synthesis (19 bins):** `binLevel[i] = clamp(envelope × shape[i] × (1 + beatBoost(i)), 0, 1)`
  - `envelope = (lLvl + rLvl) * 0.5f`
  - `shape[19]`: `1.0f - (i / 18.0f) * 0.6f`
  - `beatBoost`: `(i < 4) ? beat * 0.8f : 0.0f`

### TASK-050c — M-VIS: waveform oscilloscope view
**Owner**: Developer
**Feature**: vis-001
**Status**: done (2026-05-16 — white sine wave, vertical fill between samples, midline y=originY+50, phase-advancing; compile-verified)
**Notes**:
- **Authoritative spec:** `docs/architecture/designs/M-VIS-visualization.md`. Summary of corrections from original 2026-05-15 notes:
  - **Colour:** `VIS_WAVE_COLOR = 0xFFFF` (white, VISCOLOR[18]). NOT `TFT_GREEN`. R&D measurement confirmed white.
  - **Vertical fill between samples:** Winamp draws line segments, not single pixels per column. Use `drawFastVLine` from `min(y[x-1], y[x])` to `max(y[x-1], y[x])`. Single `drawPixel` per column is not Winamp-accurate.
  - **Midline:** `VIS_CENTRE_Y = originY + LEFT_Y + (VIS_H-1)/2 = originY + 50`. R&D measured skin y=50.2 ≈ 50. Old `originY + 49` was based on wrong VIS_H=13.
- **Synthesis:** `y[x] = clamp(VIS_CENTRE_Y + roundf(lLvl * 5.0f * sinf(wavePhase + x * 2.5f * TWO_PI / 76)), originY+43, originY+58)`
- **Render per tick:**
  1. `blitVisBackground()` — clears previous frame.
  2. For each `x` in 0..75: `drawFastVLine(originX+RECT_X+x, min(y[x-1],y[x]), abs(y[x]-y[x-1])+1, VIS_WAVE_COLOR)`. For x=0 draw single pixel at y[0].
  3. Advance `wavePhase += 0.3f`.
- **Paused state:** `lLvl` decays to 0 → flat HLine at y=50. Natural, no special case.

### TASK-048 — M-UI-POLISH: artist + title in marquee strip
**Owner**: Developer
**Feature**: disp-001 (existing)
**Status**: done (2026-05-15 — winampDisplay.h:200-214; snprintf "%s - %s   " artist+title; lastTitle[264]; lastArtist change detection; 3-space gap for loop-back)
**Notes**:
- `Snapshot::artistName[128]` already populated (`spotifyTaskStorage.cpp:100-101`). Just not wired into `drawTitleText()`.
- `winampDisplay.h:173` copies only `currentlyPlaying.trackName` → `lastTitle`. Change to compose `artist + " - " + name`.
- Buffer: `lastTitle[128]` → `lastTitle[260]` (artist 128 + `" - "` 3 + title 128 + NUL).
- Compose logic: if `artistName[0] != '\0'`: `snprintf(lastTitle, sizeof(lastTitle), "%s - %s", artistName, trackName)`. Else: `strncpy(lastTitle, trackName, ...)`.
- Track change detection (`strcmp(lastTitle, ...)` on line 173): update to trigger recompose on *either* `trackName` or `artistName` change (store `lastArtist[128]` alongside `lastTitle`, check both).
- Scroll gap: after the last glyph in `drawTitleText()`, the loop-back should insert a 3-space gap (`"   "`) before restarting from the string start. Achieves the classic "endless ticker" feel. Implement by appending `"   "` to the composed string, or by adding 3×`GLYPH_W+1` px of blank before the wrap in the render loop.
- Scroll speed: `TITLE_SCROLL_STEP_MS=120` unchanged — adjust only if user requests.
- Original Winamp 2 reference: main window shows `"Artist - Title"` format (no track-number prefix; that is playlist-editor only). Falls back to `"Title"` alone when artist blank.

### TASK-049 — M-UI-POLISH: VU zero-fill from SKIN_MAIN_BG
**Owner**: Developer
**Feature**: vu-001 (existing)
**Status**: done (2026-05-16 — pushImage zero-fill pattern already implemented in vuMeter.h; mainBg param present; confirmed in code)
**Notes**:
- `vuMeter.h:121` and `vuMeter.h:127` clear the off-portion of each bar with `tft.fillRect(..., TFT_BLACK)`. This overwrites the skin's visualization-area background.
- Fix: replace with per-row `pushImage` from `SKIN_MAIN_BG` at the corresponding window-local pixel offset. Same pattern as `drawTitleText()` line 513-514.
- VU rects are fully inside the 275×116 `SKIN_MAIN_BG` atlas:
  - Left bar:  window-local `(RECT_X=24, LEFT_Y=43, RECT_W=76, RECT_H=6)`.
  - Right bar: window-local `(RECT_X=24, RIGHT_Y=50, RECT_W=76, RECT_H=6)`.
- API change: `vu::tick(int originX, int originY)` → `vu::tick(int originX, int originY, const uint16_t *mainBg)`. Pass `SKIN_MAIN_BG` from the call site in `.ino` (or `winampDisplay.h` — wherever `vu::tick` is invoked).
- In `tick()`, replace:
  ```cpp
  if (lW < RECT_W) tft.fillRect(lx + lW, ly, RECT_W - lW, RECT_H, TFT_BLACK);
  ```
  with a row-loop blitting `mainBg + (LEFT_Y + row) * SKIN_MAIN_BG_W + RECT_X + lW` for `RECT_W - lW` pixels. Same for right bar.
- No bake-tool change. No atlas change. `SKIN_MAIN_BG` already contains the correct background pixels.
- `vu::invalidate()` path: no change needed — full bar repaint already triggered by the existing `lastLW/lastRW` dedup logic.

### TASK-047a — M-LIST-v2: bake_skin.py PLEDIT extraction + atlas + preview
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15 — 5 rows × 13px, tiled title bar, split bottom bar, SKIN_PLEDIT_BG 275×58 emitted; commits 949c057..388665f)
**Blocks**: TASK-047c (renderer needs atlas + layout constants)
**Notes**:
- Extract `PLEDIT.BMP` from `skins/base-2.91.wsz`. Inspect dimensions + sprite offsets empirically (LL-016 pattern — record actual values, don't assume canonical).
- New `build_pledit_atlas(wsz)` function in `tools/bake_skin.py`:
  - Crop title bar strip `(0, 0, 275, 14)` → scale/pad to 320 px wide (prefer pad with PLEDIT body bg colour on right; fallback nearest-neighbour stretch).
  - Crop bottom bar strip `(0, bottom_y, 275, 16)` → same horizontal treatment.
  - Composite both into `SKIN_PLEDIT_BG[320 * 30]` (title at index 0, bottom bar immediately after; renderer uses offset arithmetic: `SKIN_PLEDIT_BG` at `y=116` for title, `SKIN_PLEDIT_BG + 320*14` at `y=210` for bottom bar).
  - Crop row-highlight sprite `(0, first_row_y, 260, 16)` → `SKIN_PLEDIT_ROW_HIGHLIGHT[260 * 16]`.
- Emit `SKIN_PLEDIT_BG` + `SKIN_PLEDIT_ROW_HIGHLIGHT` to `gen/skin_assets.c`.
- Emit layout constants to `gen/skin_layout.h`: `PLEDIT_Y=116`, `PLEDIT_H=124`, `PLEDIT_TITLE_H=14`, `PLEDIT_BOTTOM_H=16`, `PLEDIT_ROWS_Y=130`, `PLEDIT_ROW_H=16`, `PLEDIT_ROW_COUNT=5`, `PLEDIT_BOTTOM_Y=210`, `PLEDIT_W=320`.
- Composite PLEDIT panel into `gen/skin_preview.png` lower band (y=116..240) with 5 sample rows. Validate on-host before DUT.
- Regenerate `gen/golden.sha256`; confirm `sha256sum -c golden.sha256` passes.

### TASK-047b — M-LIST-v2: durationMs in QueueEntry + getQueue() filter
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15)
**Blocks**: TASK-047d (total time needs `durationMs`)
**Notes**:
- Add `uint32_t durationMs` to `QueueEntry` struct. Size impact: +4 bytes × 5 entries = +20 bytes RAM (negligible).
- Reduce `QUEUE_MAX` from 7 to 5 (5 rows per ADR-018). Saves `2 × (48+32+64+4) = 296 bytes` RAM.
- Extend `getQueue()` ArduinoJson filter doc in `SpotifyArduino` LOCAL_PATCHES to include `duration_ms` from both `currently_playing` and `queue[]` items.
- At snapshot-write time, mirror `Snapshot::durationMs` (already present for posbar) into `g_queueSnapshot.items[0].durationMs` — no extra API call needed for row 0.
- Document in `lib/SpotifyArduino/LOCAL_PATCHES.md` as patch #10 (or next available).

### TASK-047c — M-LIST-v2: drawPlaylist() redesign — PLEDIT chrome + row format
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15 — commit 2d90ffa; drawPlaylist() rewritten with PLEDIT chrome, 5 rows, Font 1 text, originX=22 centering)
**Notes**:
- Implemented: title bar + bottom bar via pushImage(SKIN_PLEDIT_BG), 5 rows fillRect+Font1. Text format "Artist - Track" (no duration yet — TASK-047b prereq not done). Row 0 uses PLEDIT_BG_SELECTED + PLEDIT_FG_CURRENT; rows 1-4 use PLEDIT_BG_NORMAL + PLEDIT_FG_NORMAL. Left/right gutters filled PLEDIT_BODY_BG. seqno-gated, PLAYLIST_DRAW_MIN_MS rate limit.
- Duration column deferred to TASK-047b+d.
- Hit-test update for TASK-021 (Tier 2): row y boundaries now `y=PLEDIT_ROWS_Y+row*PLEDIT_ROW_H`.

### TASK-047d — M-LIST-v2: total time in PLEDIT bottom bar
**Owner**: Developer
**Feature**: playlist-002
**Status**: done (2026-05-15 — commit 15ab2c5; right-aligned in scrollbar track x=222, y+5 in bottom bar)
**Notes**:
- Sum `durationMs` across all `count` snapshot entries on each `drawPlaylist()` call.
- Format as `"H:MM:SS"` (hours if sum ≥ 1 h, else `"MM:SS"`).
- Determine render position from PLEDIT.BMP bottom bar inspection at TASK-047a time — record pixel offset as `PLEDIT_TOTALTIME_X` / `PLEDIT_TOTALTIME_Y` in `gen/skin_layout.h`.
- Font: TFT_eSPI Font 1 (6×8) — fits the smaller bottom bar height. Colour: white or PLEDIT text colour from inspection.
- Only re-render when seqno advances (same gate as `drawPlaylist()`).

### TASK-021 — M-LIST tier 2: tap-on-row plays that track
**Owner**: Developer
**Status**: done (2026-05-16 — winampDisplay.h:342-353; ACT_PLAY_URI dispatched on PLEDIT row tap; spotifyTaskStorage dispatches playAdvanced(uri). Caveat: playAdvanced replaces context; queue-aware skip deferred to M-LIST-v3)
**Notes**:
- Hit-test: `y >= PLEDIT_ROWS_Y && y < PLEDIT_BOTTOM_Y` → `row = (y - PLEDIT_ROWS_Y) / PLEDIT_ROW_H`. Bounds-check against `QueueSnapshot::count`.
- On tap: `enqueue(ACT_PLAY_URI, row_index)` → task reads `QueueSnapshot::items[row_index].uri` → `playAdvanced`.
- Need new `ACT_PLAY_URI` action enum. Index-in-snapshot avoids URI string in `Request` struct; race-free (task owns snapshot write side).
- Note: row y-boundaries updated by TASK-047c (PLEDIT layout shifts rows down by `PLEDIT_TITLE_H=14` px vs TASK-020 baseline).
- **DUT observation (2026-05-16)**: `playAdvanced(uri)` clears the Spotify queue and starts the selected track as a fresh session. PLEDIT immediately shows 5 identical rows of the new track; Spotify queue shows only that 1 item. This is `playAdvanced` API behaviour — it replaces the context, it does not skip ahead in the existing queue.
- **Desired behaviour**: keep the existing queue intact; "jump" to the tapped track. Implementation options: (a) if playing from a playlist/album context, use `PUT /v1/me/player/play` with `context_uri` + `offset.uri`; (b) without context, call `next` N times to skip ahead. Neither is trivially available from the current queue snapshot (which carries URIs but not the original context URI or position). Tracked for resolution in M-LIST-v3 (TASK-051a–f). See `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md`.
- **Resolution**: `s_lastTrackContextUri` is already populated by `onCurrentlyPlaying()` (`spotifyTaskStorage.cpp:77-81`) but is never read in the `ACT_PLAY_URI` handler — the wire is missing. Fix tracked in TASK-066.

### TASK-051a — M-LIST-v3: optimistic selected-row highlight
**Owner**: Developer
**Feature**: playlist-002, touch-002
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 1
**Notes**: After `ACT_PLAY_URI`, track `optimisticSelectedRow` in `WinampDisplay` (pattern: `optimisticVolumeUntilMs`). Render that row selected until seqno advances or ~8 s timeout. Reset to row 0 on track change.

### TASK-051b — M-LIST-v3: extend queue to 20 items
**Owner**: Developer
**Feature**: playlist-002
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 2
**Notes**: Raise `SPOTIFY_QUEUE_MAX_ITEMS` from 5 to 20 in `lib/SpotifyArduino/`. `QueueSnapshot` grows; heap impact must be verified (each `QueueItem` ~100 B → +1500 B).

### TASK-051c — M-LIST-v3: scrollOffset state + sliced row rendering
**Owner**: Developer
**Feature**: playlist-002
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 2
**Notes**: Add `int scrollOffset` to `WinampDisplay`. `drawPlaylist()` renders `items[scrollOffset .. scrollOffset+PLEDIT_ROW_COUNT-1]`. Row tap maps to `ACT_PLAY_URI(scrollOffset + row)`.

### TASK-051d — M-LIST-v3: swipe gesture in PLEDIT content area
**Owner**: Developer
**Feature**: playlist-002, touch-002
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-hitzones.md` Zone 1
**Notes**: Add `D_PLEDIT_SCROLL` dragState. On touch-end in content area: if `|dy| < 8px` → tap; else → increment/decrement `scrollOffset`. Requires TASK-051c.

### TASK-051e — M-LIST-v3: live scrollbar thumb (sprite blit)
**Owner**: Developer
**Feature**: playlist-002
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 3; `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md`
**Notes**: Thumb is a sprite blit, NOT a fillRect (spec corrected 2026-05-22, TASK-075 amendment). Use normal-state thumb sprite (BMP x=52, y=54, w=9, h=17) from `SKIN_ASSETS`. Blit at: `thumb_x = originX + PLEDIT_CONTENT_X + PLEDIT_CONTENT_W + 1`, `thumb_y = PLEDIT_ROWS_Y + scrollOffset * (65 - 17) / max(1, count - PLEDIT_ROW_COUNT)`. Hide when `count <= PLEDIT_ROW_COUNT`. Requires TASK-051c.

### TASK-051f — M-LIST-v3: auto-reset scrollOffset on track change
**Owner**: Developer
**Feature**: playlist-002, sync-001
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Cross-feature
**Notes**: On seqno advance, set `scrollOffset = 0`. items[0] (currently playing) always in view post-change.

### TASK-051g — M-LIST-v3: row format N. Artist - Title... M:SS
**Owner**: Developer
**Feature**: playlist-002, playlist-003
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 4
**Notes**: Replace current `"Artist - Title"` with `"N. Artist - Title   M:SS"`. N = `songsSeen + scrollOffset + i + 1`. Duration right-aligned (pixel math: `right_edge - strlen(dur)*6`). Middle truncated with `"..."` on overflow. Font 1 fixed 6px/char, 238px usable.

### TASK-051h — M-LIST-v3: songsSeen counter + 2-entry URI history
**Owner**: Developer
**Feature**: playlist-003
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md` Feature 5
**Notes**: `uint16_t songsSeen` (RAM). `char prevNextUri[40]`. `bool skipPending` (set by ACT_NEXT / ACT_PLAY_URI dispatch). Increment when `items[0].uri == prevNextUri && !skipPending`. Update `prevNextUri = items[1].uri` after each poll. Row N shows `songsSeen + scrollOffset + i + 1`.

### TASK-051i — M-LIST-v3: scrollbar strip direct drag (Zone 2)
**Owner**: Developer
**Feature**: playlist-002, touch-002
**Status**: planned
**Design**: `docs/architecture/designs/M-LIST-v3-hitzones.md` Zone 2
**Notes**: Touch in x=278..296, y=136..200 → `D_PLEDIT_SCROLL_DIRECT`. Continuous Y-to-scrollOffset mapping during drag; thumb redraws each sample. No tap action from this zone. Requires TASK-051c, TASK-051e.

### TASK-051j — M-LIST-v3: hitzones PNG update + human review gate
**Owner**: Developer + human sign-off
**Feature**: playlist-002, touch-002
**Status**: done (2026-05-23 — human sign-off given)
**Design**: `docs/architecture/designs/M-LIST-v3-hitzones.md`
**Notes**: TASK-054 (done) already built `render_hitzones()` and the single-source-of-truth zone registry pattern. Remaining work: edit the `pledit_rows` block in `render_hitzones()` (bake_skin.py:1086–1090) — replace `ROW0..ROW4` entries with `pledit_content` (SWIPE/TAP, 34,136,244,65), sub-row labels R0–R4 (no magenta fill, informational only), `pledit_scrollbar` (SCROLL DRAG, 278,136,19,65), `pledit_scroll_up` (UP BTN, 275,201,22,7), and `pledit_scroll_down` (DOWN BTN, 275,208,22,10). Re-run bake_skin.py to regenerate `gen/skin_hitzones.png`. Human eyeball sign-off before any firmware implementation of TASK-051b–i begins. This is the human review gate for M-LIST-v3. Scroll arrow coords measured in TASK-075 (see `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md`).

### TASK-022 — M-LIST option B: portrait rotation
**Owner**: Developer
**Status**: cancelled (2026-05-15 — ADR-017 chose option C; portrait rotation not needed)

### TASK-019 — Decouple display from blocking network calls (M-IO)
**Owner**: Architect (ADR-011), then Developer
**Feature**: io-001 (registered with tier-1 implementation)
**Status**: done (2026-05-22 — tier-2 delivered by TASK-031; closing)
**Notes**:
- Symptoms: slow first sync after boot; occasional hangs (clock + progress thumb stop); LCD shows previous track many seconds after Spotify advanced; heartbeat 56 s gaps observed during TLS retries.
- Tier 1 (ADR-011, 2026-05-07): exponential backoff on consecutive Spotify-poll failures (5 s → 10 → 20 → 40 → 60 s cap, reset on success or touch). Heartbeat now emits `block_max=Nms`.
- Tier 2 (TASK-031, 2026-05-08): all HTTP moved off the main task into `spotifyTask` (FreeRTOS worker). `loop_max` 4 191 ms → 16 ms. Exit criterion (heartbeat gap < 5 s p95) met. No further work needed.

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
**Status**: shipped + fully verified (Spotify-Diy-Thing@7f1009c, 2026-05-07). DUT-verified for boot trace + ESP_LOGI capture; T036 + T037 verified 2026-05-22 on non-isolated network (DUT 192.168.1.126).
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
**Status**: closed — deferred (M-NOART, TASK-062, shipped 2026-05-21 — album-art path removed; DISABLE_ALBUM_ART is now permanent policy, not a workaround. Hang is moot.)
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

### TASK-052a — M-VIS-ATLAS: bake_vis.py — bar-height extraction pipeline
**Owner**: Developer
**Feature**: vis-002 (new)
**Status**: done (2026-05-16 — 412 frames, 7.6 KB, wrap L1=18 ✓, sha256 golden committed)
**Blocks**: TASK-052b, TASK-052c, TASK-052d
**Notes**:
- New `tools/bake_vis.py` (sibling to `bake_skin.py`). Inputs: one or more committed `.webm` screengrab videos; output: `gen/vis_atlas.c` + `gen/vis_atlas.h` + `gen/vis_atlas.npy` + `gen/vis_atlas.sha256`.
- Auto-calibrate vis area per M-VIS-video-analysis-method.md (blue border detection).
- Subsample source at 20 Hz; extract bar heights (0..16) per bar per frame via background pixel classification.
- Emit `uint8_t VIS_ATLAS[N_FRAMES][19]` byte-per-bar C array and companion NumPy `.npy`.
- Report wrap-jump distance (L1 between frame[0] and frame[-1]) to console.
- SHA256 golden: `sha256sum -c gen/vis_atlas.sha256` must pass on same machine.
- See `docs/architecture/designs/M-VIS-ATLAS-vis-atlas.md` §1.

### TASK-052b — M-VIS-ATLAS: preview_vis.py — animated GIF output
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — gen/skin_preview_animated.gif, 182 frames, correct 1:1 device-pixel coords, boost+trim applied)
**Deps**: TASK-052a (needs vis_atlas.npy)
**Notes**:
- `tools/preview_vis.py` reads `gen/vis_atlas.npy` + `gen/skin_preview.png`; composites atlas frames into vis area at 1:1 device pixels (skin_preview.png is 320×240, chrome at x=0,y=0); writes animated GIF at 20 fps.
- Vis coords mirror firmware exactly: skin chrome at (0,0) in preview, vis at x=RECT_X=24, y=LEFT_Y+1=44.
- `--boost 1.5` (default): scales bar heights so peaks reach ceiling (row 0 = red).
- `--trim-quiet` (default on, thresh=4, keep=2): collapses runs of all-green frames to 2 highest-energy frames per run.
- `--boost` and `--trim-quiet` are preview-only tuning knobs; `bake_vis.py` applies the same transforms to the committed C array (see TASK-052a notes below).

### TASK-052c — M-VIS-ATLAS: preview_vis.py — live pygame window + synthetic mode
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — --live pygame window + --mode synthetic implemented; --loop-start/--loop-end sub-range tuning)
**Deps**: TASK-052b
**Notes**:
- `--live` flag opens pygame window at 20 Hz real-time.
- `--mode synthetic` runs firmware AR(1)/inertia/oscillator logic in Python for A/B comparison vs atlas.
- `--loop-start F` / `--loop-end F` to select atlas sub-range for wrap-point tuning.

### TASK-052d — M-VIS-ATLAS: firmware VIS_ATLAS mode in vuMeter.h
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — DUT verified; Atlas default mode; tap cycle Atlas→Wave→VU→Blank→Atlas)
**Deps**: TASK-052a (needs gen/vis_atlas.h)
**Notes**:
- `VIS_ATLAS_MODE` in `VisMode` enum (renamed from VIS_ATLAS to avoid clash with global array symbol).
- `tickAtlas()`: index `VIS_ATLAS[frame][i]` directly (.rodata); freeze frame counter on `!playing` but always blit (fix: early return on !playing left vis area showing stale Spectrum frame).
- No peak dots in atlas mode (footage encodes Winamp peak behaviour by construction).
- VIS_SPECTRUM removed from tap cycle — superseded by atlas. New cycle: **Atlas → Wave → VU → Blank → Atlas**. Default boot mode: Atlas.

### TASK-052e — M-VIS-ATLAS: flash headroom verification
**Owner**: Developer
**Feature**: vis-002
**Status**: done (2026-05-16 — Flash 52.4%; baked atlas 3.4 KB after trim+boost, well within 12 KB budget ✓)
**Deps**: TASK-052d
**Notes**:
- `pio run -e cyd2usb_winamp`: Flash 52.4% (1,374,121 / 2,621,440 bytes). Healthy.
- Atlas after trim+boost: 182 frames × 19 bytes = 3,458 bytes in .rodata. Original raw: 412 frames × 19 = 7,828 bytes.
- `bake_vis.py` applies `--boost 1.5` and `--trim-quiet thresh=4 keep=2` before emitting the C array; same parameters as preview_vis.py — DUT and preview match.

### TASK-052f — M-VIS-ATLAS: VE regression — existing vis modes unchanged
**Owner**: VE
**Feature**: vis-002
**Status**: done (2026-05-17 — DUT visual sign-off by user)
**Deps**: TASK-052d
**Notes**:
- DUT flash `cyd2usb_winamp`. Tapped through Atlas → WaveAtlas → VU → Blank → Atlas on device.
- Confirmed: Atlas 19 bars animate at 20 Hz, gravity peak dots visible and correct. User: "looks great".
- WaveAtlas mode added since task was written (TASK-055a–b); cycle is now Atlas → WaveAtlas → VU → Blank → Atlas.
- VU bars intact; Blank clean skin bg.
- Spectrum mode no longer in cycle — removed intentionally.
- Flash delta confirmed within budget (TASK-052e, TASK-055c).

### TASK-065 — BUG: PLEDIT empty after HTTP/1.1 keep-alive (getQueue chunked bail-out)
**Owner**: Developer
**Feature**: playlist-002, conn-002
**Status**: done (2026-05-21 — inner repo commit `62d1792` on rnd/poll-lag, cherry-picked to main as `ab3864e`)
**Git ref**: rnd/poll-lag (observed 2026-05-20 post-M-NOART flash)
**Notes**:

#### Symptom
PLEDIT rows are empty (no track names) even when Spotify shows an active queue.
`get queue` serial command returns `count=0` after a normal boot + track playing.

#### Root cause
`getQueue()` (`lib/SpotifyArduino/src/SpotifyArduino.cpp:625–630`) bails out silently
when the response carries `Transfer-Encoding: chunked`:

```cpp
if (hdr.chunked) {
    closeClient();
    return statusCode;  // 200 returned; onQueue never called
}
```

Under HTTP/1.0 (pre-INV-A Step 3) Spotify returned `Content-Length` for the queue
endpoint — `hdr.chunked` was false and the parse path ran. After the HTTP/1.1
keep-alive switch (INV-A Step 3, 2026-05-20), Spotify responds with
`Transfer-Encoding: chunked`. The bail-out fires every time, `onQueue` is never
invoked, `g_queueSnapshot.count` stays 0, `drawPlaylist()` renders 5 empty rows.

`doFetchQueue()` sets `s_queueRefreshNeeded = false` regardless of outcome, so
subsequent fetches only happen on track-change or the 60 s keepalive — each also
hits the chunked path and produces the same silent zero.

Note: the INV-A Step 3 design notes (`INV-A-tls-connection-lifecycle.md`, §Step 3
implementation notes, item 7) explicitly called out the chunked risk and specified
"fall back to connection-close for that response". This was not implemented — the
bail-out was carried over from the pre-Step-3 code unchanged.

#### Why verification did not catch this
- T102 (TSYNC-6 — queue strip shifts on track-change) ran **2026-05-18**, two days
  before INV-A Step 3 landed (**2026-05-20**). T102 passed under HTTP/1.0; no
  re-run was scheduled after Step 3.
- The Step 3 DUT verification run (5 min, idle, all 204s) checked connection
  metrics only (fd warnings, block_max, poll ratio, heap). The success criteria
  did not include a `get queue` assertion or a PLEDIT visual check. A PLEDIT
  content check was not in the Step 3 exit criteria document.
- `get queue` returning `count=0` on first fetch looks identical to a valid empty
  queue at idle (no track playing). The idle verification run never exercised the
  active-playback queue path.

#### Fix
Implement a dechunker in `getQueue()`: read raw socket bytes into `bodyBuf`,
strip chunk-size framing (`HEX\r\n…DATA…\r\n`, terminated by `0\r\n\r\n`) before
passing to `deserializeJson`. ~20-line loop; isolated to the `getQueue` body-read
path. Removes the bail-out; handles multi-chunk responses correctly.
Alternative (simpler but incurs a reconnect): add `Connection: close` override for
the queue request only, forcing the server to send Content-Length.

#### VE gap (regression coverage) — **closed 2026-05-21**
T114 PASS (DUT 2026-05-21, inner `main` `ab3864e`): `get queue` count=4, row[0] non-empty.
T102 re-run PASS (DUT 2026-05-21): queue row[0] shifted 5832ms ≤ 8500ms under HTTP/1.1
keep-alive + dechunker. Harness: `run_sync_tests.py` T114 added (inner repo `6c6bbe6`);
`read_json()` timing bug fixed; T102 settle-wait added. Results recorded in test_plan.md.

---

### TASK-066 — BUG: tap-to-play clears Spotify queue (context_uri not wired in ACT_PLAY_URI)
**Owner**: Developer
**Feature**: playlist-001 (bug fix)
**Status**: done (2026-05-22 — inner `main` `7a97088`)
**Blocks**: TASK-067 (VE gate)
**Notes**:

#### Symptom (DUT 2026-05-16, re-confirmed 2026-05-22)
Tapping a PLEDIT row clears the Spotify queue. After the tap, PLEDIT shows 5 identical rows of the tapped track; Spotify app shows only 1 item. First reported at TASK-021 close-out.

#### Root cause
`ACT_PLAY_URI` handler (`spotifyTaskStorage.cpp:330-331`) constructs:
```cpp
snprintf(body, sizeof(body), "{\"uris\":[\"%s\"]}", uri);
s_spotify->playAdvanced(body);
```
`{"uris":["..."]}` starts a new ad-hoc single-track session, replacing the existing playlist/album context. `s_lastTrackContextUri` (`spotifyTaskStorage.cpp:46`) is populated on every poll (`onCurrentlyPlaying` lines 77-81) but **never read** in the handler — the wire is missing.

Spotify then fills the 4 upcoming queue slots with the same track URI (its behaviour for a single-URI session), causing `qd.count=5` with identical items → 5 duplicate PLEDIT rows.

#### Fix (spotifyTaskStorage.cpp)
In the `ACT_PLAY_URI` case, check `s_lastTrackContextUri[0]`:
- Non-empty (playlist/album context): use `{"context_uri":"<ctx>","offset":{"uri":"<track>"}}`
- Empty (ad-hoc/radio — no context): fall back to existing `{"uris":["<uri>"]}` behaviour

Pattern already established by `nfc.h:174`.

#### Deliverables
1. `spotifyTaskStorage.cpp` — `ACT_PLAY_URI` handler wires `s_lastTrackContextUri`.
2. `dbg_get("snapshot")` serial output — add `contextUri` field (reads `s_lastTrackContextUri` directly) so VE can verify preconditions for T115/T116 without a host-side Spotify API call.
3. Update TASK-021 notes (done — reference to this task already added).

#### Exit criterion
T115 passes on DUT (playlist context: queue preserved, no duplicate rows).
T116 passes on DUT (ad-hoc/radio: fallback fires, no crash).

---

### TASK-067 — VE: write + execute T115/T116 — tap-to-play regression suite
**Owner**: VE
**Status**: done (2026-05-22 — T115 PASS, T116 PASS; inner `main` `1a9d531`)
**Deps**: TASK-066 done (inner `main` `7a97088`)
**Notes**:
- Write T115 (playlist context — queue preserved) and T116 (ad-hoc fallback — no crash) in `docs/verification/test_plan.md` (stubs already added at planned status).
- Execute both on DUT with TASK-066 firmware.
- Update `playlist-001` `test_ids` in `feature_inventory.yaml` to `[T115, T116]` on first pass.
- Report pass/fail status back to PM. PM to prompt QM for retrospective on TASK-021/TASK-066 lifecycle.

---

### TASK-064 — Merge rnd/poll-lag planning docs to master (outer repo)
**Owner**: PM
**Status**: done (2026-05-21 — `e9f9203`, `eb70315`, `943ccf3` cherry-picked to outer master; M-NOART design doc, TASK-065 filing, task status updates all on master)
**Git ref**: rnd/poll-lag outer repo — commits `f1b8fb0` (M-NOART roadmap + PROP-004 resolved), `a71753e` (INV-A step3 design doc)
**Notes**:
- PM/Arch/VE artifacts cherry-picked to outer master: M-NOART design doc (`e9f9203`),
  TASK-065 filing (`eb70315`), task status backfills (`f5bdaf6`, `3da873d`, `f918351`),
  ADR acceptances (`3da873d`), T114+T102 results (`cff4aaf`, `66b89d4`).
- R&D investigation docs (INV-A, INV-B, EXP-001/002, PROP-003/004) remain on
  `rnd/poll-lag` per convention.
- `docs/project/tasks.md` on master reflects all done-status updates for TASK-062/063/065
  via the above cherry-picks. Divergence between branches is expected (tasks.md notes
  were updated on master via cherry-picks of later commits).

### TASK-062 — M-NOART: remove album-art path and JPEG decoder
**Owner**: Developer
**Feature**: noart-001 (new)
**Status**: done (2026-05-21 — inner repo commit `dcfbad0` on rnd/poll-lag, cherry-picked to main as `1411a3e`)
**Git ref**: rnd/poll-lag (roadmap item added f1b8fb0)
**Notes**:
- Gate for promoting the INV-A keep-alive fix to main.
- JPEG crash (`JPEGPutMCU22 LoadProhibited`) observed on DUT 2026-05-20 during track
  playback; triggered by the inherited album-art decode path in `CheapYellowDisplay`.
- Work: gate the album-art path in `cheapYellowLCD.h` behind `#ifndef WINAMP_DISPLAY`
  (or a dedicated `ALBUM_ART_ENABLED` flag); remove `JPEGDEC` from `lib_deps` under
  `cyd2usb_winamp` in `platformio.ini`; drop the `processImageInfo` override workaround
  in `winampDisplay.h` (superseded by the compile-time guard).
- Exit criterion: `cyd2usb_winamp` build clean without `JPEGDEC`; DUT survives 5+ min
  of active track playback without a Guru Meditation Error.
- Design: `docs/project/roadmap.md` M-NOART.

### TASK-063 — Promote rnd/poll-lag keep-alive fix to main
**Owner**: Developer
**Feature**: conn-002 (new)
**Status**: done (2026-05-21 — cherry-picked `66e71de`, `49d9b71`, `8542f91`, `4f0da82`, `dcfbad0`, `62d1792` → main `d7b261b`–`ab3864e`)
**Git ref**: rnd/poll-lag — inner repo commit `4f0da82` (keep-alive) + `49d9b71`, `66e71de` (tools)
**Notes**:
- Cherry-pick or merge `4f0da82` to `main`, replacing the `processImageInfo` workaround
  in `winampDisplay.h` with the proper M-NOART `#ifdef` guard from TASK-062.
- Also promote `tools/poll_latency_mock.py` (`66e71de`) and `tools/command_latency.py`
  (`49d9b71`) — low-risk R&D tooling, independent of the JPEG issue.
- The INV-B timeout bump/revert pair (`e174b04` + `bae05bb`) is net-zero; do not promote.
- Source investigation: INV-A (`docs/rnd/investigations/INV-A-tls-connection-lifecycle.md`),
  design: `docs/architecture/designs/M-CONN-http11-keepalive.md`.
- Verified: poll=55/55 100%, block_max 216–442ms typical, zero stale fd warnings (idle).
  One stale fd=49 sighting during active playback at 1:05 — acceptable, rare.

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

### TASK-052 — M-IO: any tap resets backoff + force-polls Spotify
**Owner**: Developer
**Feature**: io-001
**Status**: done (2026-05-16 — winampDisplay.h:233-366; resetBackoff() at top of every touched() block; dead-zone path enqueues ACT_FORCE_POLL with 1 s deadZoneForcePollAt cooldown)
**Notes**:
- **Problem**: during a backoff run (consecutive failures → 10/20/40/60 s waits), the screen feels dead even when the network recovers. User has no escape except waiting for the next cadence poll.
- **Fix**: every tap — whether on an active control or a dead zone (inactive PLEDIT rows, PLEDIT title/bottom bar, black areas) — resets `s_consecutiveFailures = 0` and enqueues `ACT_FORCE_POLL`. This matches ADR-011's stated intent ("touch resets backoff") and extends it to all touch events, not just transport buttons.
- **Backoff reset on dispatch** (not just on poll success): zero `s_consecutiveFailures` the moment any touch-driven action is enqueued. `nextWaitMs()` will return `kPollPeriodMs` (5 s) immediately — the task unblocks from its long `xQueueReceive` wait at queue-receive time (action already in queue, wait irrelevant) and issues the poll.
- **1 s force-poll cooldown**: track `lastForcePollMs` in `winampDisplay.h`. Any tap that would otherwise fall through all hit-tests (dead zone) sends `ACT_FORCE_POLL` only if `millis() - lastForcePollMs > 1000`. Active-control taps (transport, seek, volume, PLEDIT row) already enqueue their own action + trigger `doPoll()` post-action — they don't need the dead-zone path, but they do reset `s_consecutiveFailures` via a new `spotifyTask::resetBackoff()` call.
- **Implementation surface**:
  1. `spotifyTask.h` / `spotifyTaskStorage.cpp`: expose `void resetBackoff()` (sets `s_consecutiveFailures = 0`).
  2. `winampDisplay.h::update()`: at top of the `ts.touched()` block (before any hit-test), call `spotifyTask::resetBackoff()`. At the end of the else-fall-through (no hit matched), if cooldown elapsed enqueue `ACT_FORCE_POLL` and update `lastForcePollMs`.
- **No UI feedback needed** — backoff recovery is transparent; the next successful poll updates the display normally.
- **Cooldown rationale**: 1 s prevents a held-finger from hammering the queue with repeated `ACT_FORCE_POLL` when already draining. Separate from `touchScreenCoolDownTime` (which gates all touch recognition).



To be triaged with the team.

### TASK-054 — M-HITZONES: hit-zone preview PNG from bake_skin.py
**Owner**: Developer
**Feature**: m2-001 (bake pipeline extension)
**Status**: done (2026-05-16 — bake_skin.py:1034-1097; render_hitzones() overlays all zones as semi-transparent magenta rects + labels; emits gen/skin_hitzones.png; excluded from golden.sha256)
**Notes**:
- Extend `tools/bake_skin.py`: after `render_full_preview()` runs, call a new `render_hitzones(canvas, out_path)` that overlays all registered touch zones as semi-transparent magenta rects with white labels.
- Zone registry: Python list of `(label, x, y, w, h)` tuples using the same constant values that are emitted to `skin_layout.h` (single source of truth — define once, use in both the emitter and the renderer).
- Rendering: `ImageDraw.Draw(overlay)` filled magenta rects at alpha=100 (40 %); `Image.alpha_composite` over the preview canvas; `ImageDraw.textbbox` / `ImageDraw.text` for labels centred in each rect. PIL `ImageFont.load_default()` — no external font dep.
- Zones to cover (minimum set): PREV, PLAY, PAUSE, STOP, NEXT, SEEK (posbar), VOL (volume slider), SHUF, RPT, VIS, LOGO/RECONNECT, PLEDIT ROW0–ROW4.
- Output: `gen/skin_hitzones.png` — written unconditionally alongside `skin_preview.png`.
- Exclude `skin_hitzones.png` from `gen/golden.sha256` (derived artefact, not a firmware input).
- ~50 LOC. No new Python deps.

### TASK-055a — M-WAVE-ATLAS: VIS_WAVE_ATLAS enum + nextMode() update
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Git ref**: 49ff9a9
**Notes**:
- Added `VIS_WAVE_ATLAS` to `VisMode` enum in `vuMeter.h`.
- Added `waveAtlasFrameRef()` inline state accessor.
- Updated `nextMode()` cycle: Atlas → WaveAtlas → VU → Blank → Atlas. `VIS_WAVE` removed from cycle (stays in codebase).
- Included `gen/wave_atlas.h`.

### TASK-055b — M-WAVE-ATLAS: tickWaveAtlas() + dispatch in tick()
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Git ref**: 49ff9a9
**Notes**:
- `tickWaveAtlas()`: 20 Hz frame advance (continuous, not gated on playing); `blitVisBackground()` + white vertical fill between consecutive atlas samples.
- `prevY` seeded from `row[0]`, not `centreY` — prevents left-edge spike artefact.
- Dispatch wired in `tick()`: `case VIS_WAVE_ATLAS: tickWaveAtlas(...)`.

### TASK-055c — M-WAVE-ATLAS: flash budget verify
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Notes**:
- Build: 52.9 % flash (1,387,237 / 2,621,440 B). Headroom ~47 %. Well within the ≤ previous+17 KB exit criterion.

### TASK-055d — M-WAVE-ATLAS: fix frozen lead-in frames + canonical bake script
**Owner**: Developer
**Feature**: wave-001
**Status**: done (2026-05-17)
**Git ref**: a071b89
**Notes**:
- Root cause: frames 0–29 byte-identical (source video static before music starts) → 1.5 s visual freeze per loop at 20 Hz.
- Fix: added `--frame-start` / `--frame-end` to `bake_wave.py`; rebaked with `--frame-start 30`. 224 → 194 frames.
- All AE flags restored: `--boost 2.0 --spatial-smooth 3 --error-diffusion --dc-offset 3`.
- `tools/bake_wave.sh`: canonical invocation per BP-002. Future rebakes use this script.

### TASK-053a — M-CONN: bake SKIN_TITLEBAR_INACTIVE sprite
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16)
**Notes**:
- Cropped TITLEBAR.BMP at (27,14,302,28) → 275×14 `SKIN_TITLEBAR_INACTIVE`.
- Added `LOGO_X/Y/W/H` layout constants to `skin_layout.h`.
- Regenerated `gen/golden.sha256`.

### TASK-053b — M-CONN: spotifyTask::isHealthy() + resetTls()
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16)
**Notes**:
- `isHealthy()`: returns `s_consecutiveFailures < 2`.
- `resetTls()`: sets volatile `s_resetTlsPending = true` + zeroes failures. Task body calls `client.stop()` on its own stack before next poll (avoids cross-task mbedTLS races).

### TASK-053c — M-CONN: inactive title bar overlay in repaintChrome()
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16; DUT-verified 2026-05-22)
**Notes**:
- `repaintChrome()` blits `SKIN_TITLEBAR_INACTIVE` over position (originX, originY) when `!isHealthy()`.
- Active bar (already in MAIN_BG) shows on recovery without extra code.
- Health-change trigger: `drawPlaylist()` (called every loop) detects `isHealthy() != lastHealthy` and calls `repaintChrome()` immediately.
- DUT 2026-05-22: DNS override pointed `api.spotify.com → 192.0.2.1`. consecutive=1 → consecutive=2. After consecutive=2, `last_render_age_ms` dropped 60003→17251 confirming `repaintChrome()` fired. PASS (active→inactive direction).

### TASK-053d — M-CONN: spotifyTask::resetTls()
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16 — merged into TASK-053b)

### TASK-053e — M-CONN: serial `reconnect` command
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16; DUT-verified 2026-05-22)
**Notes**:
- `handleSerialCommands()` in `SpotifyDiyThing.ino` loop — line-buffered; dispatches `resetTls()` + `enqueue(ACT_FORCE_POLL)` on "reconnect".
- DUT 2026-05-22: sent "reconnect" via serial. Response: `{"ok":true,"cmd":"reconnect"}`. Log: `[I][spotify.tls] hard reset — stopping client`. Polls resumed immediately; 10/10 at 1:06 uptime. PASS.

### TASK-053f — M-CONN: Winamp logo tap → TLS reset
**Owner**: Developer
**Feature**: conn-001
**Status**: done (2026-05-16; DUT-verified 2026-05-22)
**Notes**:
- `hitTestLogo()` at `LOGO_X/Y/W/H` (250,100,25,16 window-local); 2 s cooldown `logoTapCooldownMs`.
- Calls `resetTls()` + `enqueue(ACT_FORCE_POLL)` + `repaintChrome()` for immediate visual feedback.
- DUT 2026-05-22 (3 taps): `[I][touch] logo tap → TLS reset + force poll` logged twice; 2nd tap hit 2s cooldown → `dead zone tap` (correct). TLS hard reset fired, polls recovered 200 OK. Visual redraw confirmed by user. PASS.

### TASK-035 — Drop OTA `app1` partition (reclaim 1.25 MB flash)
**Owner**: Developer
**Status**: done (2026-05-10 — tripped the wall during TASK-025 bring-up; firmware.bin overflowed the 1.28 MB app0 partition by ~2.6 KB and bootlooped silently with `rst:0x3 (SW_RESET)` and zero app output. No exception, no panic — the loader's image-hash check fails when the trailing bytes spill into app1 territory, and re-resets immediately.)
**Notes**:
- Custom partition table at `Spotify-Diy-Thing/partitions_no_ota.csv`. Drops `app1`; `app0` grows from 0x140000 → 0x280000 (2.56 MB). NVS / otadata / SPIFFS / coredump untouched, so existing user data + wifi creds + spotify creds survive across the layout change.
- `[env:cyd2usb]` (and the cyd2usb-derived envs) sets `board_build.partitions = partitions_no_ota.csv`. The legacy `cyd` env keeps the default Arduino-ESP32 partitions (uses much less flash; OTA optionality preserved there for now).
- Cost: lose OTA capability on `cyd2usb*` envs. Acceptable — this project flashes over USB.
- Diagnostic note: when this fires the next time, the symptom is *boot loop with no application Serial output*. PlatformIO's "Flash 99.7%" report compares against the partition size, not the actual on-disk binary size (which is ~3 KB larger after the loader-checksum padding). If the binary grows past ~99.6%, double-check `ls -la .pio/build/<env>/firmware.bin` against the app0 size in `partitions.bin` before assuming a code bug.

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

### TASK-056a — M-SERIALDBG: platformio.ini debug env + inject_git_hash.py
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- New `[env:cyd2usb_winamp_debug]` extending `cyd2usb_winamp` with `-DSERIAL_DEBUG`.
- New `scripts/inject_git_hash.py` pre-script — injects `GIT_REV` define (git short hash + dirty marker).
- Both `cyd2usb_winamp` and `cyd2usb_winamp_debug` build clean post-change. `GIT_REV` + `SERIAL_DEBUG` confirmed present on debug env via `pio run -v`; absent on production env.

### TASK-056b — M-SERIALDBG: boot version line
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- Unconditional `[boot] git=<hash> elf=<8hex> build=<date> <time>` via `esp_ota_get_app_description()`.
- Ships in both `cyd2usb_winamp` and debug env. `GIT_REV` token guarded; "n/a" in production.
- Implemented in `setup()` lines 169–188 (landed alongside TASK-056c).

### TASK-056c — M-SERIALDBG: table-driven dispatcher + drainInjectionQueue
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- 4-field `SerialCmd kCmds[]` table; `handleSerialCommands()` dispatcher; 64-byte line buffer with WARN+reset on overflow.
- `drainInjectionQueue()` call at top of `loop()` (TASK-056e fills the implementation).
- Coordinated with TASK-056j (reconnect JSON format change).

### TASK-056j — M-SERIALDBG: reconnect command → JSON response
**Owner**: Developer
**Feature**: serialdbg-001, conn-001
**Status**: done (2026-05-17)
**Notes**:
- `cmdReconnect` emits `{"ok":true,"cmd":"reconnect"}` (landed alongside TASK-056c).
- T090–T094 conn-001 test suite exists as regression guard. tmux/grep scripts audited — no old `[reconnect]` prefix references found.

### TASK-056n — M-SERIALDBG: IDebugExportable interface + SpotifyDisplay no-ops
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- New file `SpotifyDiyThing/debugExportable.h`: `IDebugExportable` with `dbgGet`/`dbgSet` pure virtuals, compiled under `SERIAL_DEBUG`.
- `SpotifyDisplay` gains default no-op overrides + `injectTouch`/`injectRelease` virtual no-ops under `SERIAL_DEBUG`.

### TASK-056d — M-SERIALDBG: WinampDisplay::injectTouch + injectRelease + lastTouchResult
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- Virtual `injectTouch(sx, sy)` + `injectRelease()` on `SpotifyDisplay` base; `WinampDisplay` overrides both.
- Cooldown-aware gate: if `millis() <= touchScreenCoolDownTime`, sets `lastTouchResult.skipped=true`, returns without dispatch.
- `bool _injectingDrag` member (WinampDisplay, SERIAL_DEBUG) suppresses checkForInput() drag-end branch during injection.
- `lastTouchResult` 6-field struct: region (TRANSPORT/POSBAR/VOLUME/SHUFFLE/REPEAT/VIS/LOGO/DEADZONE/NONE), transportPressed, action, seekMs, volumePct, skipped.
- Implemented co-located with TASK-056g in `winampDisplay.h`.

### TASK-056e — M-SERIALDBG: cmdTap, cmdDrag, injection ring buffer
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `cmdTap`: sscanf x/y, call `injectTouch+injectRelease` via virtual dispatch, emit region-specific JSON from `lastTouchResult`.
- `cmdDrag`: fill 64-slot `s_injectQueue` ring buffer (steps+1 move samples + 1 release sentinel); sets `_injectingDrag=true`; JSON emitted by `drainInjectionQueue()` on release step. No `delay()` in loop task.
- `drainInjectionQueue()` pops one step per `loop()` iter; per-sample `LOG_D("serial", "inject sample %d/%d sx=%d sy=%d", ...)` for T096.

### TASK-056f — M-SERIALDBG: spotifyTask::dbg_get / dbg_set
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `spotifyTask::dbg_get`: handles "backoff" (consecutiveFailures + nextWaitMs), "heap" (getFreeHeap), "snapshot" (multi-part split protocol), "queue" (5-row split protocol — TASK-056m).
- `spotifyTask::dbg_set`: handles "backoff" (sets consecutiveFailures).
- `spotifyTask::dbg_getFailureCount()`: thin getter for cmdInfo.
- `s_consecutiveFailures` → `volatile unsigned int` (matches `s_resetTlsPending` pattern).
- Implemented in `spotifyTaskStorage.cpp`.

### TASK-056g — M-SERIALDBG: WinampDisplay::dbgGet / dbgSet overrides
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `dbgGet`: handles "cooldown" (remainingMs), "dragState" (name), "optimisticVolume" (remainingMs), "songDuration" (ms).
- `dbgSet`: handles "cooldown" (resets to 0; val ignored).
- Implemented in `winampDisplay.h` alongside TASK-056d.

### TASK-056h — M-SERIALDBG: cmdGet / cmdSet dumb dispatchers
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- Dispatch to `spotifyDisplay->dbgGet/dbgSet` then `spotifyTask::dbg_get/dbg_set`. Frozen — never changes as fields grow.
- Multi-part: owner emits Serial.printf lines directly, returns true with buf[0]='\0'; cmdGet skips wrapper print.
- Implemented in `SpotifyDiyThing.ino`.

### TASK-056i — M-SERIALDBG: cmdInfo + cmdHelp
**Owner**: Developer
**Feature**: serialdbg-001
**Status**: done (2026-05-17)
**Notes**:
- `cmdInfo`: single JSON line (git/elf/build/heap/isPlaying/progressMs/durationMs/volumePct/shuffle/repeat/consecutiveFailures).
- `cmdHelp`: single JSON line iterating `kCmds[]` — table is SSOT. ADR-021 one-JSON-object-per-newline invariant preserved.
- Implemented in `SpotifyDiyThing.ino`.

### TASK-056l — M-SERIALDBG: extend get snapshot with lastPollAgeMs / currentTrackUri / deviceActive
**Owner**: Developer
**Feature**: serialdbg-001, sync-001
**Status**: done (2026-05-17)
**Notes**:
- Added `bool deviceActive` to `Snapshot`; populated at both write sites in `spotifyTaskStorage.cpp`.
- `spotifyTask::dbg_get("snapshot")`: added `lastPollAgeMs`, `deviceActive`, `currentTrackUri` in both single-line and split paths.
- Prereq for TASK-057 VE harness (T097, T099, T102, T103, T105, T107, T108).

### TASK-056m — M-SERIALDBG: get queue command (QueueSnapshot rows)
**Owner**: Developer
**Feature**: serialdbg-001, sync-001
**Status**: done (2026-05-17)
**Notes**:
- Replaced stub with real `QueueSnapshot` serialization via `copyQueueSnapshot`. Up to 5 rows, one JSON line each, split protocol with `"part":N,"last":bool`.
- No cmdGet change. Prereq for T102.

### TASK-056k — M-SERIALDBG: VE execute serialdbg-001 suite on DUT
**Owner**: VE
**Feature**: serialdbg-001
**Status**: done (2026-05-18)
**Blocked by**: TASK-056a through TASK-056i (core impl), TASK-056l (for T095)
**Notes**:
- T076–T085, T096 + T089: **pass 2026-05-17** (DUT ee65beb+, harness
  `Spotify-Diy-Thing/tools/run_serialdbg_tests.py`). 11 PASS / 0 FAIL / 0 SKIP.
- Firmware fixes landed during DUT bring-up (same day, separate commit):
  (1) `drainInjectionQueue` skips logging on release sentinel (T096 off-by-one);
  (2) `dbgSet("cooldown", ms)` accepts arming value, not reset-only (T079
  previously untestable via serial — see design doc B1 closure);
  (3) `injectTouch` emits `enqueued ACT_VOLUME pct=N` LOG_D so T082 can count
  synchronous enqueues instead of async `spotify.task` dequeues;
  (4) `dbgSet("songDuration", val)` accessor (T085 — previously required
  waiting many minutes for Spotify to drop the player session after closing
  all clients).
- Harness logic fixes: T076 now tests 8 contiguous-row boundary cases (not 10
  non-contiguous outside-left cases); T079 arms via `set cooldown 500`;
  T082 counts the new enqueue trace line; T085 forces songDuration=0.
- **T086–T088 automated (2026-05-17)**: harness functions `t086`, `t087`, `t088` added;
  registered in ALL_TESTS. Coordinate corrections vs test plan:
  - POSBAR bottom inside boundary: y=81 (not y=82 — POSBAR_BG.h=10, py1=82 is exclusive).
  - LOGO second-tap within cooldown returns DEADZONE/FORCE_POLL (not LOGO — firmware
    falls to else branch when `millis() < logoTapCooldownMs`).
  - TLS reset log pattern: `"hard reset"` / `"stopping client"` ([I][spotify.tls]).
- **T095 interactive (2026-05-17)**: harness function `t095(dut, interactive)` added;
  activated by `--interactive` flag; SKIPs without flag. Prompts operator for each of
  3 zones (PREV/POSBAR-mid/VOLUME-mid), captures dequeue log for physical tap, confirms
  Spotify effect. Run: `python3 run_serialdbg_tests.py --interactive --tests T095`.
- T089 (production symbol check) **pass** — verified again 2026-05-17 after
  the four firmware fixes (0 SERIAL_DEBUG in `cyd2usb_winamp` ELF).
- **T086–T088 + T095 DUT run (2026-05-17)**: all pass. T086 POSBAR+VOLUME boundary
  16/16; T087 LOGO tap 3/3; T088 DEADZONE 11/11; T095 3/3 region+action pairs.
  Physical touch jitter ~12% (resistive CYD2USB); T095 pass threshold revised to ±15%.
- **T090–T092 DUT run (2026-05-17)**: T090/T091 PASS, T092 harness timing fix needed
  (LOGO tap cooldown shorter than expected; T092 revised to send two rapid FORCE_POLLs).
  T090–T092 re-run: PASS after fix.
- **Status**: **done** (2026-05-18). serialdbg-001 suite complete: T076–T096 all
  executed on DUT. 22 PASS / 0 FAIL / 0 SKIP (T089/T090/T091/T092 counted separately;
  T095 requires `--interactive` flag; T093–T094 reserved for conn-001 manual step).

---

### TASK-057 — M-SYNC: VE harness tools (spotify_state.py, spotify_drive.py, tsync_diff.py)
**Owner**: VE
**Feature**: sync-001
**Status**: done (2026-05-17)
**Notes**:
- `tools/spotify_state.py`: refresh-token-aware `/me/player` wrapper; emits structured JSON matching firmware Snapshot field names. Exit 0=ok, 1=error, 2=204.
- `tools/spotify_drive.py`: Connect API control — pause, play, next, prev, seek, setVolume, setShuffle, toggleShuffle, setRepeat, transfer. Stdlib only.
- `tools/tsync_diff.py`: `get snapshot` over serial (split-protocol) + `/me/player` over HTTPS; diffs isPlaying/progressMs/durationMs/volumePct/shuffleState/repeatState/trackUri; prints `[OK]` or `[DRIFT] field dut=<v> spotify=<v>`. `--count N --interval S` for repeated runs. Exit 1 on any drift. Anchor for T110.
- All three: stdlib only (no deps beyond pyserial for tsync_diff). Syntax verified.

### TASK-058 — log-001: heartbeat fields last_poll_age_ms + next_poll_in_ms
**Owner**: Developer
**Feature**: log-001, sync-001, drift-001
**Status**: done (2026-05-17)
**Notes**:
- Added `s_lastSuccessfulPollMs` (set on 200/204) and `s_lastPollFinishedMs` (set after every `doPoll()`) task-private statics in `spotifyTaskStorage.cpp`.
- Exposed `spotifyTask::lastSuccessfulPollAgeMs()` and `spotifyTask::nextPollInMs()` loop-task-safe getters.
- Appended `last_poll_age_ms=%lu next_poll_in_ms=%lu` to heartbeat `LOG_I` in `logHeartbeat.h`.
- Both `cyd2usb_winamp` and `cyd2usb_winamp_debug` build clean.

### TASK-059 — drift-001: last_render_age_ms heartbeat field + g_lastRenderMs
**Owner**: Developer
**Feature**: drift-001
**Status**: done (2026-05-17)
**Notes**:
- Defined `uint32_t g_lastRenderMs = 0` in `spotifyLogic.h`; extern'd in `winampDisplay.h` and `logHeartbeat.h`.
- Set at end of `updateCurrentlyPlaying()` seq-change path (`spotifyLogic.h`) and at end of `repaintChrome()` (`winampDisplay.h`).
- Appended `last_render_age_ms=%lu` to heartbeat. Both envs build clean.

### TASK-060 — drift-001: chrome staleness indicator in repaintChrome()
**Owner**: Developer
**Feature**: drift-001
**Status**: done (2026-05-17)
**Notes**:
- `N_STALE_MS = 15000` compile-time constant in `winampDisplay.h` (3× base poll cadence per ADR-023).
- 4×4 amber pip (`0xFD00`) baked inline (16 × uint16_t); no atlas change.
- Blit at `originX+268, originY+1`, layered after conn-001 inactive-titlebar in `repaintChrome()` — both indicators visible simultaneously.
- Check uses `spotifyTask::lastSuccessfulPollAgeMs()` (TASK-058 getter).
- Both envs build clean.

### TASK-061 — M-SYNC/M-DRIFT: VE execute sync-001 + drift-001 suite on DUT (T097–T111)
**Owner**: VE
**Feature**: sync-001, drift-001
**Status**: done (2026-05-18)
**Notes**:
- Harness: `Spotify-Diy-Thing/tools/run_sync_tests.py` (new file, 2026-05-18).
- DUT: ESP32-2432S028R, env `cyd2usb_winamp_debug`, serial `/dev/ttyUSB0`, AT&T cellular tether.
- Results (2026-05-18): **12 PASS / 0 FAIL / 3 SKIP** (T097–T102, T104–T111 pass;
  T100/T101 skip — Firefox Web Player ignores shuffle/repeat API commands, re-run with
  mobile/speaker; T103 skip — requires two active Spotify Connect devices).
- Cellular environment: AT&T NAT closes stale TLS connections (~30% poll fail rate);
  harness uses `force_fresh_poll()` + `reconnect_after=5.0` in `poll_until()`; lag bounds
  raised to 8500ms (from spec 5500ms) for forced-poll path (5s sleep + 2s TLS+HTTP + 1.5s overhead).
- Key behavioral findings documented in test_plan.md:
  - `set backoff N` sets policy only, not running poll timer; harness uses `get backoff` for
    policy check rather than racing the heartbeat (T105, T109).
  - CH341 kernel DTR assertion always reboots DUT on serial port open; tsync_diff.py
    redesigned to pause Spotify before subprocess + proper `_wait_for_ready()` on reopen (T110).
  - T111 `last_render_age_ms` ≤ 8000ms (spec ≤500ms inapplicable — DUT renders on poll
    update ~5s cadence, not continuously).

---

- **TASK-002** — Touchscreen seek/scrub. ✅ closed 2026-05-08 by M5 (tap-to-seek shipped; drag-with-debounce deferred to a follow-up if/when it's wanted).
- **TASK-003** — Play/pause + volume on touch. Play/pause closed 2026-05-08 by M5. Volume deferred — not on the main-window chrome we render today; needs VOLUME.BMP baked + a slot reserved.
- **TASK-004** — Decide NFC support posture. Reader not connected on dev unit; boot logs `NFC Bad` harmlessly. Either wire a PN532 and validate, or set `NFC_ENABLED 0` to silence. Owner: PM (decision).

---

### TASK-068 — M-SHELL-LAYOUT: coords.py — originX-aware tap/drag helpers

**Owner**: Developer
**Feature**: shell-layout-001
**Status**: todo
**Blocked by**: ADR-025 proposed (human sign-off required before start)
**Notes**:
- New file `Spotify-Diy-Thing/tools/coords.py`.
- Parses `gen/skin_layout.h` via regex (strip inline comments); derives `ORIGIN_X = (320 - WINDOW_W) // 2`.
- Exposes named helpers: `vol_drag_x()`, `tap_button(name)`, `tap_logo()`, `pledit_tap(row)`. See `shell-layout.md` Gap 1 for full skeleton.
- Audit `gen/skin_layout.h` first: confirm `CB_*_W`, `CB_*_H`, `VOLUME_FRAME_W`, `PLEDIT_CONTENT_X`, `PLEDIT_TITLE_H`, `PLEDIT_ROW_H` are all emitted; add missing `#define`s to `bake_skin.py` emit block if not.
- Update `run_serialdbg_tests.py`: replace all hardcoded `tap`/`drag` coordinate literals with `coords.py` calls. Coordinate reference comment at top of file (lines 19–25) documents screen coords with `originX=22`; replace with `coords.py` imports.
- Update `run_sync_tests.py`: same. Replace `_PLEDIT_ORIGIN_X = 22` and all hardcoded tap/drag literals. `_pledit_tap_xy()` should delegate to `coords.pledit_tap()`.
- Verify: run T076–T088, T095–T096, T104, T106, T111, T115–T116 on DUT with `originX=22` (current firmware) — all must still pass. This is the regression gate before M-MULTIAPP shifts `originX` to 0.

### TASK-069 — M-SHELL-LAYOUT: bake_skin.py tooling fixes (gaps 2 + 3)

**Owner**: Developer
**Feature**: shell-layout-001
**Status**: todo
**Blocked by**: ADR-025 proposed
**Notes**:
- **Gap 2**: `render_hitzones()` (~line 1047) — rebuild zone list from existing dicts. Transport: iterate `CBUTTON_POSITIONS`. Other zones: read from `POSBAR_LAYOUT`, `VOLUME_LAYOUT`, `SHUFREP_LAYOUT`. See `shell-layout.md` Gap 2 for fixed pattern.
- **Gap 3**: `preview_vis.py:58` — replace `WINDOW_W = 275` hardcode with parse of `gen/skin_layout.h` using the new `parse_skin_layout()` helper (same pattern as `parse_shell_layout()`; can share implementation).
- Verify: `bake_skin.py` run produces identical `skin_hitzones.png` to pre-fix (values unchanged — only code structure changes). `sha256sum -c golden.sha256` must pass.

### TASK-070 — M-SHELL-LAYOUT: parse_shell_layout() helper + preview_layout.py

**Owner**: Developer
**Feature**: preview-tooling-001, shell-layout-001
**Status**: todo
**Blocked by**: ADR-025 proposed
**Notes**:
- Add `parse_shell_layout(path)` to `bake_skin.py`. Must strip inline comments (`//` suffix) from all values before returning. Handles int (`275`), hex (`0x07E0`), char (`'A'`), flag (`1`). T128 verifies.
- New script `Spotify-Diy-Thing/tools/preview_layout.py`. See `interactive-preview.md` for full spec:
  - `--interactive` flag opens pygame window at `--scale N` (default 2).
  - Renders 320×240 PIL composite: Winamp chrome left, taskbar strip right.
  - Icon glyphs: Winamp TEXT.BMP 5×6 bitmap font. Chars S/C/W/$/M/G. UV table in `interactive-preview.md`.
  - Keyboard controls: `b` (bg colour), `i` (indicator style), `s` (separators), `c` (indicator colour), `[`/`]` (active slot), `+`/`-` (scale), `p` (print params), `e` (export), `q` (quit).
  - `e` key writes `gen/shell_layout.h` using the schema in `shell-layout.md`. Geometry constants (`TASKBAR_X` etc.) are fixed; aesthetic constants are filled from current session state.
- Run the interactive session, approve a configuration, press `e` to commit `gen/shell_layout.h`.

### TASK-071 — M-SHELL-LAYOUT: gen/shell_layout.h in golden.sha256

**Owner**: Developer
**Feature**: shell-layout-001
**Status**: todo
**Blocked by**: TASK-070 (gen/shell_layout.h must exist first)
**Notes**:
- After TASK-070 produces `gen/shell_layout.h`, add its hash to `golden.sha256`.
- Run `sha256sum -c golden.sha256` to confirm clean. T132 verifies.

### TASK-072 — M-SHELL-LAYOUT: VE execute T125–T132

**Owner**: VE
**Feature**: shell-layout-001, preview-tooling-001
**Status**: todo
**Blocked by**: TASK-068, TASK-069, TASK-070, TASK-071
**Notes**:
- T125: `gen/shell_layout.h` present, all 11 `TASKBAR_*` defines present.
- T126: `TASKBAR_X + TASKBAR_W == 320`; `TASKBAR_SLOT_H * TASKBAR_SLOT_COUNT == 240`.
- T127: semantic grep — no bare `>= 275` or `/ 40` in `appShell.h` (note: `appShell.h` does not exist yet; T127 gates M-MULTIAPP taskbar implementation, not this task).
- T128: `parse_shell_layout()` strips comments, handles all value types.
- T129: `_Static_assert` in `appShell.h` (gates M-MULTIAPP, not this task).
- T131: manual pygame window check — scale, glyphs, all keyboard controls, `e` export.
- T132: no TBD in `taskbar.md`; `golden.sha256` passes.
- Report pass/fail to PM. PM prompts QM for retrospective.

### TASK-073 — BUG: `strcmp(nullptr)` crash in `getCurrentlyPlaying` on track start
**Owner**: Developer
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-22 — LOCAL_PATCHES patch #11; null guard added; DUT-verified no crash on first 200 OK poll with active playback)
**Notes**:

#### Symptom
`LoadProhibited` Guru Meditation on boot when Spotify is actively playing. Crash at
`SpotifyArduino.cpp:894` inside `strcmp`. Only hit on the first poll that returns 200 (track
playing) immediately after a 204-only sequence; does not crash on subsequent 200 polls.

#### Root cause
`doc["currently_playing_type"]` returns `nullptr` when the JSON field is absent (observed
during the initial track-start transition). Line 894: `strcmp(currently_playing_type, "track")`
called with null first arg → `LoadProhibited`.

The existing `repeat_raw` block (patch #9) already pattern-matches with a null guard;
`currently_playing_type` was missing the same guard.

#### Fix (`lib/SpotifyArduino/src/SpotifyArduino.cpp:893`)
```cpp
if (currently_playing_type == NULL) {
    current.currentlyPlayingType = other;
} else if (strcmp(currently_playing_type, "track") == 0) {
```

LOCAL_PATCHES.md patch #11. DUT confirmed no crash on 2026-05-22 reflash with active playback.

### TASK-074 — BUG: `LoadProhibited` crash in `onCurrentlyPlaying` — uninitialized `CurrentlyPlaying` struct
**Owner**: Developer
**Feature**: api-002 (lib patch family)
**Status**: done (2026-05-22 — `CurrentlyPlaying current = {}` zero-init patch; DUT-verified 48 polls / 5 min no crash; T133 added)
**Notes**:

#### Symptom
`LoadProhibited` Guru Meditation, EXCVADDR=`0x0000000c`, crashing in `strcmp` inside
`spotifyTask::onCurrentlyPlaying` at `spotifyTaskStorage.cpp:72`. Reproducible within 2–3 polls
of a fresh boot once `s_lastTrackUri` was non-empty. Distinct from TASK-073 (which fixed a
`nullptr` crash on `currently_playing_type`).

#### Root cause
`CurrentlyPlaying current;` at `SpotifyArduino.cpp:783` is uninitialized. When
`currently_playing_type == "other"`, neither the `track` nor the `episode` fill block executes,
leaving `current.trackUri` as stack garbage (`0x0000000c`). The null guard in
`onCurrentlyPlaying` (`cp.trackUri == NULL`) only catches exact zero — `0x0000000c` passes
through, and `strcmp` crashes on the second poll when `s_lastTrackUri` is non-empty.

#### Fix (`lib/SpotifyArduino/src/SpotifyArduino.cpp:783`)
```cpp
CurrentlyPlaying current = {};   // LOCAL_PATCHES: zero-init
```

LOCAL_PATCHES comment added. T133 in `run_serialdbg_tests.py` guards the fix with a static grep
+ 90 s runtime soak.

---

### TASK-075 — RnD: measure PLEDIT scroll-arrow + thumb sprite positions in PLEDIT.BMP
**Owner**: R&D
**Feature**: playlist-002, touch-002
**Status**: done — amended 2026-05-22
**Blocks**: TASK-051j (hitzones PNG visual validation), TASK-051i (scrollbar strip drag firmware), TASK-051e (thumb sprite blit)
**Git ref**: master (spec update in PLEDIT-BMP-spec.md)
**Notes**:

#### Findings (2026-05-22)

Scroll arrows are in the **bottom bar right section** of PLEDIT.BMP (BMP x=254..274, y=72..88),
at the rightmost edge of the 150px right section (atlas x=253..274, screen x=275..296).

**Sprite coordinates in PLEDIT.BMP:**

| Element | BMP x | BMP y | w | h |
|---------|-------|-------|---|---|
| UP▲ button (normal) | 254..274 | 72..78 | 21 | 7 |
| DOWN▼ button (normal) | 254..274 | 79..88 | 21 | 10 |
| UP glyph pixels | 261..268 | 74..77 | 8 | 4 |
| DOWN glyph pixels | 261..268 | 80..83 | 8 | 4 |

No pressed-state sprites. Glyph color: `(106,106,122)` = `0x6B4F`.

**Screen hitzones (originX=22, PLEDIT_BOTTOM_Y=201):**

| Zone | x | y | w | h |
|------|---|---|---|---|
| Scroll-UP tap | 275 | 201 | 22 | 7 |
| Scroll-DOWN tap | 275 | 208 | 22 | 10 |

Note: buttons are small (7–10px tall). Expand to 19px each if touch precision is insufficient:
UP=y201..219, DOWN=y220..238.

**Standalone zones**: YES — each tap scrolls 1 item. Complement Zone 2 (direct strip drag).

Full spec in `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md` §"Scroll arrow buttons".

#### Amendment (2026-05-22) — scrollbar thumb sprite found

Initial findings incorrectly concluded the thumb was absent and synthesised. Pixel colour analysis against a reference screenshot confirmed golden thumb colours match BMP x=52..70 exclusively. Human-verified by extracting and inspecting the sprites.

**Thumb sprite coordinates in PLEDIT.BMP:**

| Element | BMP x | BMP y | w | h |
|---------|-------|-------|---|---|
| Thumb — normal state | 52 | 54 | 9 | 17 |
| Thumb — alt state | 62 | 54 | 8 | 16 |

Spec corrected in `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md` §"Scrollbar thumb". TASK-051e updated to use sprite blit instead of `fillRect`.

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
