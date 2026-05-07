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
- Build wiring: standalone tool, manual invocation per user pref. `python3 tools/bake_skin.py -i skins/winamp2_base.wsz -o SpotifyDiyThing/gen`. Determinism: `cd SpotifyDiyThing/gen && sha256sum -c golden.sha256`.

### TASK-009 — TLS connection lifecycle for non-GET endpoints
**Owner**: Developer (implementation), Architect (ADR-007)
**Feature**: api-002 (new — to be registered)
**Status**: in_progress (ADR-007 proposed 2026-05-04 — awaiting human sign-off → Developer implements)
**Blocks**: M5 (full-skin touch controls), TASK-002, TASK-003
**Notes**:
- Discovered during TASK-007 DUT run 2026-04-29: every `POST` (`nextTrack`, `previousTrack`) and `PUT` (`pause`, `play`, `seek`, `setVolume`, `toggleShuffle`, `setRepeatMode`) fails at TLS-send with mbedTLS `0x0050 (NET_CONN_RESET)`. `GET /v1/me/player/currently-playing` works in the same boot from the same poll loop.
- Architect 2026-05-04: confirmed root cause via `lib/SpotifyArduino/src/SpotifyArduino.cpp` inspection. Library uses HTTP/1.0 (server closes after response) but never calls `client->stop()` between requests — only `client->flush()` then `connect()`. Arduino-ESP32 2.0.17 `WiFiClientSecure::connect()` on a peer-closed socket can succeed without re-handshaking, producing `0x0050` on the next write. ADR-007 selects **option 2** (insert `client->stop()` before each `connect()` in `makeRequestWithBody` + `makeGetRequest`). Options 1 and 3 rejected — 1 thrashes heap with no upside, 3 is a disproportionate library rewrite. Option 3 retained as pre-authorised fallback if verification partial-passes.
- Verification gate (VE): re-run spike harness rows `>` `<` ` ` `p` `P` `s` `S` `+` `-` `v` `h` `H` `r` `R` `o`; all must return `[OK]`. GET poll loop must remain healthy. Rows `f` / `a` stay 403 (TASK-010, out of scope here).

### TASK-018 — On-screen log overlay (M-LOG2)
**Owner**: Developer (will need brief Architect input on screen-real-estate trade-off vs M3 chrome)
**Feature**: log-002 (to be registered at first implementation commit)
**Status**: planned (2026-05-07)
**Notes**:
- Roadmap entry: M-LOG2. Spec: render last ~7 ringbuffer lines to the bottom 62 px strip of the CYD using TFT_eSPI font 1, green-on-black. Newest at bottom, scrolls up. Subscribed to the existing 12 KB ring (no new state).
- Behind `#define SCREEN_LOG` (or a new `cyd2usb_winamp_screenlog` env). Default off — zero overhead when not built in.
- Update gating: dirty flag set by `ringPush`; redraw at ≤4 Hz to avoid SPI thrash.
- Truncate long lines (no wrap). Bottom strip dimensions: 320×62 → ~7 lines × 53 chars at font 1.
- Diagnostic motivation: makes state-coupling problems (TASK-019) visible at the moment they affect the UI.
- Open: should the overlay also paint over the Winamp window when something is critically wrong (e.g. during a long block), or stay strictly in the margin? Defer until in code.

### TASK-019 — Decouple display from blocking network calls (M-IO)
**Owner**: Architect (ADR), then Developer
**Feature**: io-001 (to be registered when an ADR lands)
**Status**: open (2026-05-07 — observed during M3 DUT verify)
**Notes**:
- Symptoms: slow first sync after boot; occasional hangs (clock + progress thumb stop); LCD shows previous track many seconds after Spotify advanced; heartbeat 56 s gaps observed during TLS retries.
- Diagnostic plan: enable TASK-018 (on-screen log) once shipped; let user observe blocking events live. Cross-reference with `/log?n=` ringbuffer dumps once a non-AP-isolated network is available.
- Likely contributors to investigate (none confirmed yet): TLS retry storms on captive-portal networks, 5 s `delayBetweenRequests` being too long for short tracks, synchronous `getCurrentlyPlaying` blocking the renderer for the full TLS+HTTP duration.
- Likely fixes (TBD ADR): aggressive timeouts; move HTTP off the main task; speculative re-poll on track-change indication.
- Exit criteria: heartbeat gap distribution < 5 s p95 across normal play.

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
**Owner**: Architect (decision), Developer (next)
**Feature**: vu-001 (planned)
**Status**: design-complete (ADR-009 accepted 2026-05-07; awaiting implementation)
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

- **TASK-002** — Touchscreen seek/scrub. Currently `touchScreen.h:46-53` only maps left/right thirds to prev/next; middle is dead, seek bar is display-only. Wire `SpotifyArduino::seek()` to taps inside the bar geometry. Owner: Developer.
- **TASK-003** — Play/pause + volume on touch. No control surface for either today. Layout decision needed first. Owner: Architect → Developer.
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
