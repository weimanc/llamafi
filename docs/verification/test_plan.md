# Test Plan

> Owner: Verification Engineer

From `feature_inventory.yaml` + `cross_feature_matrix.yaml`. Hierarchy: suite→feature→test. Each feature needs ≥1 test. Each matrix interaction needs ≥1 cross-feature test.

---

## Suite: api-001 — Spotify Web API capability spike (M1)

Manual e2e tests run against the spike harness (`-DSPIKE_MODE`, env `cyd2usb_spike`) on the DUT, with a Spotify client (phone app or other) actively playing on the same Premium account. Each test = one serial command key. Pass = expected effect observed both on the controlling Spotify client and in the harness's serial log.

Common preconditions for all tests below:
- DUT flashed with `cyd2usb_spike` env, booted, WiFi up, refresh token valid.
- Spotify Premium account, currently playing on at least one device (phone) so a transfer/control target exists.
- Serial monitor attached at 115200; `?` returned the help table on connect.

**M1 exit verdict (2026-04-29):** the entire control surface (T001–T015) is **failing** for the same root cause — `WiFiClientSecure` reuse breaks non-GET requests at TLS-send. T016/T017/T018 are blocked by Spotify's late-2024 deprecation of audio-features/audio-analysis for new Developer apps (HTTP 403 returned). Per-test detail below; cross-cutting follow-ups TASK-009 (TLS lifecycle) and TASK-010 (VU rethink).

### T001 — [api-001] nextTrack
- **Type**: e2e
- **Objective**: Verify `SpotifyArduino::nextTrack()` advances the current track.
- **Steps**: 1. Note current track. 2. Send `>`. 3. Wait one Spotify poll (~5 s).
- **Expected result**: Serial log `[OK ] > nextTrack`. Spotify client advances to next track within ~1 s.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T002 — [api-001] previousTrack
- **Type**: e2e
- **Objective**: Verify `previousTrack()`.
- **Steps**: Send `<`.
- **Expected result**: `[OK ] < previousTrack` and Spotify client jumps back.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T003 — [api-001] play (force)
- **Type**: e2e
- **Objective**: Verify `play()` resumes paused playback.
- **Preconditions**: Playback paused.
- **Steps**: Send `p`.
- **Expected result**: `[OK ] p play`. Track resumes.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T004 — [api-001] pause (force)
- **Type**: e2e
- **Objective**: Verify `pause()` pauses active playback.
- **Preconditions**: Playback running.
- **Steps**: Send `P`.
- **Expected result**: `[OK ] P pause`. Track pauses.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T005 — [api-001] toggle play/pause
- **Type**: e2e
- **Objective**: Verify the spike's local `s_assumedPlaying` toggle dispatches to the right call.
- **Steps**: Send space twice. Confirm first action matches assumed state, second flips.
- **Expected result**: Two `[OK ]` lines, alternating play/pause; client state matches.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T006 — [api-001] seek 30s
- **Type**: e2e
- **Objective**: Verify `seek(30000)`.
- **Steps**: Send `s`.
- **Expected result**: `[OK ] s seek 30000`. Spotify client position jumps to ~0:30.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T007 — [api-001] seek 0
- **Type**: e2e
- **Steps**: Send `S`.
- **Expected result**: `[OK ] S seek 0`. Position resets to track start.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T008 — [api-001] setVolume +10
- **Type**: e2e
- **Objective**: Verify `setVolume()` raises volume by 10 from local mirror baseline (50 → 60).
- **Steps**: Send `+`.
- **Expected result**: `[OK ] + setVolume +10`, then `(vol=60)`. Spotify client volume slider rises.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T009 — [api-001] setVolume −10
- **Type**: e2e
- **Steps**: Send `-`.
- **Expected result**: `[OK ] - setVolume -10`. Volume falls.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T010 — [api-001] setVolume 50 (reset)
- **Type**: e2e
- **Steps**: Send `v`.
- **Expected result**: `[OK ] v setVolume 50`. Slider snaps to 50%.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T011 — [api-001] shuffle on
- **Type**: e2e
- **Steps**: Send `h`.
- **Expected result**: `[OK ] h shuffle on`. Shuffle indicator on Spotify client lights.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T012 — [api-001] shuffle off
- **Type**: e2e
- **Steps**: Send `H`.
- **Expected result**: `[OK ] H shuffle off`. Indicator unlights.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T013 — [api-001] repeat track
- **Type**: e2e
- **Steps**: Send `r`.
- **Expected result**: `[OK ] r repeat track`. Client shows repeat-one.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T014 — [api-001] repeat context
- **Type**: e2e
- **Steps**: Send `R`.
- **Expected result**: `[OK ] R repeat context`. Client shows repeat-all.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T015 — [api-001] repeat off
- **Type**: e2e
- **Steps**: Send `o`.
- **Expected result**: `[OK ] o repeat off`. Repeat off on client.
- **Status**: failing — blocked on TASK-009 (TLS-send `0x0050` on every non-GET; library client-reuse bug)

### T016 — [api-001] audio-features
- **Type**: integration
- **Objective**: Verify raw `GET /v1/audio-features/{id}` round-trips, parses, and stays under heap budget.
- **Preconditions**: A track has been picked up by the existing poll loop (`lastTrackUri` populated). Otherwise the spike skips with `[SKIP] f`.
- **Steps**: Send `f`.
- **Expected result**: `[GET]  audio-features <id> code=200 clen=<~700-1000> heap=<a>-><b> dE=<small>` plus reasonable energy/valence/danceability/tempo/loudness values. `dE` (heap delta) under ~3 KB.
- **Status**: **failing — endpoint deprecated.** 2026-04-29: `[ERR]  audio-features 6kicsnoSgwTPWYPlxTDB2t code=403 clen=-1`. Spotify returns HTTP 403 for new Developer apps as of late 2024; the request reaches Spotify and is rejected at the API layer (not TLS — TLS round-trip succeeded). Blocked on TASK-010.

### T017 — [api-001] audio-analysis 16K filtered parse
- **Type**: integration
- **Objective**: Verify `GET /v1/audio-analysis/{id}` round-trips and a 16 KB `DynamicJsonDocument` with a beats-and-segments filter parses successfully on this DUT.
- **Preconditions**: As T016. Track must be one Spotify provides analysis for (most catalogue tracks).
- **Steps**: Send `a`.
- **Expected result**: `[GET]  audio-analysis <id> code=200 clen=<~30-80 KB> doc=16384 beats=<N>0 segments=<N>00 heap=<a>-><b> dE=<≤16K>`.
- **Status**: **failing — endpoint deprecated.** 2026-04-29: `[ERR]  audio-analysis 6kicsnoSgwTPWYPlxTDB2t code=403 clen=-1`. Same root cause as T016. Blocked on TASK-010.

### T018 — [api-001] audio-analysis 32K filtered parse (fallback)
- **Type**: integration
- **Objective**: Confirm 32 KB doc size succeeds when 16K fails.
- **Steps**: Send `A`.
- **Expected result**: As T017 with `doc=32768`. Either success or a recorded structural reason it cannot fit (informs decision to stream-parse or drop fields).
- **Status**: **moot — endpoint deprecated.** Doc-size fallback is irrelevant when Spotify returns 403 unconditionally for this app. Blocked on TASK-010.

### T019 — [api-001, time-001] info / heap / clock baseline
- **Type**: unit
- **Feature(s)**: api-001, time-001
- **Objective**: Sanity baseline for heap-delta interpretation (T016/T017) and verification that time-001's NTP sync produced a valid clock.
- **Steps**: Send `i` immediately after boot, then again after running T001–T015, then again after T016/T017.
- **Expected result**: Two `[INFO]` lines per `i`. Heap deltas bounded, audio-analysis dominant. Time line shows `sane=1` and `utc=` ISO-8601 timestamp past 2025-12-08 (the current Spotify cert's `notBefore`). If `sane=0`, time-001 failed and T020 will already have flagged it.
- **Status**: time portion **passing** (2026-04-28 and again 2026-04-29: `sane=1`, current UTC timestamps each boot). Heap-delta portion **moot** — depends on T016/T017/T018 producing heap data, but those endpoints return 403 from Spotify; no heap data to baseline against.

### T020 — [time-001] NTP sync at boot
- **Type**: integration
- **Feature(s)**: time-001
- **Interaction**: X001 (time-001 → auth-001 dependency)
- **Objective**: Verify the SNTP block in `setup()` produces a sane system clock before the first TLS handshake.
- **Preconditions**: WiFi up, AP allows outbound UDP/123 to at least one of `pool.ntp.org` / `time.google.com` / `time.cloudflare.com`.
- **Steps**: 1. Flash `cyd2usb_spike`. 2. Capture serial log from boot.
- **Expected result**: Log line `[time] synced epoch=<n> in <ms>ms` with `n > 1700000000`, before any `Refreshing Access Tokens` line. Following `spotifyRefreshToken` succeeds (no `Status Code: -2`). Total NTP wait under 5 s.
- **Negative case**: If UDP/123 blocked, expect `[time] WARN: NTP sync failed after 5000ms, proceeding with epoch=<small>` at +5 s. Firmware still boots (non-fatal); subsequent TLS still fails as before. Documents environment for follow-up.
- **Status**: **passing** (positive case, 2026-04-28). Boot log: `[time] synced epoch=1777404307 in 3400ms`. Subsequent `Refreshing Access Tokens` reached Spotify (HTTP 400 returned, not a TLS-layer failure) — confirming time-001 alone closed the TLS-validation issue. Negative case not exercised (no captive-AP environment available); kept as `planned-deferred`.

---

## Entry Format

```
### T001 — [Feature ID] [Test Name]
- **Type**: unit | integration | e2e | cross-feature
- **Feature(s)**: F001[, F002]
- **Interaction**: X001 (if cross-feature; omit otherwise)
- **Objective**: What this test verifies
- **Preconditions**: Starting state required
- **Steps**: Numbered sequence of actions
- **Expected result**: Observable, verifiable outcome
- **Status**: planned | written | passing | failing
```