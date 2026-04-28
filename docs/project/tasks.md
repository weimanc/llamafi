# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

## Project Scope

**In scope:** `Spotify-Diy-Thing/` — Arduino/PlatformIO firmware for ESP32 CYD2USB displaying Spotify now-playing track + album art via Spotify Web API.

**Out of scope:** `cspot/` — vendored upstream of an unrelated Spotify Connect player library. Do not extend, do not depend on. If touched at all, only to track upstream pulls.

## Active Tasks

### TASK-008 — NTP sync at boot (time-001)
**Owner**: Developer
**Feature**: time-001
**Status**: in_progress (code landed + builds clean, awaiting DUT verification)
**Git ref**: (commit pending in Spotify-Diy-Thing)
**Notes**:
- Root cause for the 2026-04-28 DUT TLS failure (`status Code-1`, `_handle_error 0x0050`). ESP32 has no RTC and the firmware never called `configTime()`, so mbedTLS rejected Spotify's certs whose `notBefore` is in the future.
- `setup()` now calls `configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com")` immediately after WiFi-up, then waits up to 5 s for `time(nullptr) > 1700000000` (2023-11-14). Non-fatal on timeout — logs `[time] WARN ...` and proceeds so the failure mode stays distinguishable.
- Spike harness `i` command extended: also prints epoch + ISO-8601 UTC + `sane=0|1` so T019/T020 verify the fix.
- Both `cyd2usb` and `cyd2usb_spike` envs build clean.
- DUT verification when reachable: flash `cyd2usb_spike`, watch for `[time] synced epoch=...` in boot log, send `i` and confirm UTC > 2025-12-08, observe whether `spotifyRefreshToken` now succeeds (decides whether time-001 alone fixes the TLS failure or whether TASK-006 rotation is also needed).
- Cross-feature interaction recorded: `cross_feature_matrix.yaml:X001` (time-001 → auth-001, dependency, risk: high).

### TASK-007 — M1 API capability spike harness
**Owner**: Developer
**Feature**: api-001
**Status**: in_progress (code drafted, awaiting DUT run)
**Git ref**: (commit pending)
**Notes**:
- Spike harness implemented under `-DSPIKE_MODE` build flag (env `cyd2usb_spike`). Both spike and default envs compile clean.
- SpotifyArduino vendored to `Spotify-Diy-Thing/lib/SpotifyArduino/` with a 3-line `getBearerToken()` patch. See `LOCAL_PATCHES.md`.
- DUT required to run. Procedure: build/flash `cyd2usb_spike`, start playback from a Spotify client, send command keys via serial, fill the per-row table below.
- Pair with TASK-006 (refresh-token rotation) on the same DUT trip.

#### Per-row results (fill during DUT run)

| Key | Action | Result | Notes |
|-----|--------|--------|-------|
| `>` | nextTrack | | |
| `<` | previousTrack | | |
| ` ` | toggle play/pause | | |
| `p` | play | | |
| `P` | pause | | |
| `s` | seek 30000 | | |
| `S` | seek 0 | | |
| `+` | setVolume +10 | | |
| `-` | setVolume -10 | | |
| `v` | setVolume 50 | | |
| `h` | shuffle on | | |
| `H` | shuffle off | | |
| `r` | repeat track | | |
| `R` | repeat context | | |
| `o` | repeat off | | |
| `f` | audio-features | code= clen= heap_delta= | |
| `a` | audio-analysis (16K filter) | code= clen= heap_delta= beats= segments= | |
| `A` | audio-analysis (32K filter) | code= clen= heap_delta= beats= segments= | only if `a` failed |

#### Decisions to record at exit
- SpotifyArduino extension strategy (extend / fork-and-keep-vendored / replace). Closes one Open Question in `architecture.md`.
- Working `audio-analysis` doc size; feeds vu-001 cache sizing in M6.

## Blocked Tasks

### TASK-006 — Rotate leaked refresh token + client secret
**Owner**: Developer
**Status**: blocked
**Blocked by**: DUT not on hand (need physical device for `uploadfs` step)
**Notes**:
- Refresh token from initial bring-up was pasted into a shared chat transcript.
- Rotation procedure: Spotify dashboard → rotate client secret → re-run `get_refresh_token.py` on host → edit `Spotify-Diy-Thing/data/spotify_diy_config.json` → `pio run -e cyd2usb -t uploadfs --upload-port /dev/ttyUSB0` → reset device → confirm polling.
- Resume when DUT is reachable again.

## Completed Tasks

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
