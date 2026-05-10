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

**Update (2026-05-08):** T001–T015 all **passing** after the LOCAL_PATCHES fixes (TASK-009 close-out). Diagnosis was incomplete in April — the original `WiFiClientSecure` reuse fix (ADR-007) was necessary but not sufficient. Three further structural bugs in the vendored `SpotifyArduino` lib needed patching: (a) extraneous trailing CRLF after body, (b) `Content-Type: application/json` on bodyless requests (caused server to early-RST), (c) strict `statusCode == 204` check that rejected Spotify's actual 200 responses. Per-test status lines below carry the "failing" history; treat T001–T015 as **passing as of 2026-05-08**.

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

## Suite: poll-002 — Position interpolation (M4)

Visual e2e tests against a live DUT with Spotify playing on the same Premium account. Default `cyd2usb` env (no `-DSPIKE_MODE`). Renderer-side correctness; the spotifyLogic interpolation math is exercised implicitly via display state.

### T021 — [poll-002] Seek bar advances smoothly between polls
- **Type**: e2e (visual)
- **Feature(s)**: poll-002
- **Objective**: Verify the seek bar advances at ~10 Hz, not the prior 2 Hz step rate.
- **Preconditions**: DUT booted, WiFi up, Spotify playing a track ≥ 60 s long on a Premium device.
- **Steps**: Watch seek bar for 10 s.
- **Expected result**: Bar appears to move continuously (sub-perceptual stepping). No stutter, no backwards jump on poll boundary.
- **Status**: passing (2026-05-07, user confirmed "alright-ish, good enough"). No automated assertion — visual only.

### T022 — [poll-002] Pause freezes bar at correct position
- **Type**: e2e (visual)
- **Feature(s)**: poll-002
- **Objective**: Verify `updateProgressBar` idles when `songStartMillis == 0` and the re-anchor in `handleCurrentlyPlaying` keeps the displayed position correct.
- **Steps**: 1. Play a track. 2. Pause from another device mid-track. 3. Wait 10 s.
- **Expected result**: Bar stops at paused position; doesn't drift, doesn't jump back to 0.
- **Status**: planned-deferred (not exercised on 2026-05-07; user accepted M4 close on T021 alone).

### T023 — [poll-002] Track skip resets bar without artifacts
- **Type**: e2e (visual)
- **Feature(s)**: poll-002
- **Objective**: Verify the renderer's shrink-branch full-repaint covers track-change correctly (lastBarXWidth resets via the smaller new value).
- **Steps**: Skip to next track from another device.
- **Expected result**: Bar snaps to the new track's progress (likely near 0) within one poll. No leftover white pixels from the previous track's longer bar.
- **Status**: planned-deferred.

### T024 — [poll-002] Idempotent renderer SPI cost under 100ms tick
- **Type**: integration (instrumentation)
- **Feature(s)**: poll-002
- **Objective**: Verify the lower tick rate (500 → 100 ms) doesn't increase TFT_eSPI write traffic during steady playback (when pixel position is unchanged, redraw should no-op).
- **Steps**: Add a counter around `tft.fillRect` calls in `displayTrackProgress`, run a 60 s playback window, log calls.
- **Expected result**: Calls per second ≤ pixel-position changes per second (≈ once per 200–400 ms depending on track length). 100 ms tick should NOT produce 10 fillRects/s.
- **Status**: planned (no instrumentation in tree yet). Backlog if SPI/CPU contention surfaces.

---

## Suite: m2-001 — Skin asset bake tool

Host-side tool tests. Run on the dev machine, not the DUT.

### T025 — [m2-001] Bake produces deterministic output
- **Type**: unit (regression)
- **Feature(s)**: m2-001
- **Objective**: Verify two bake runs from the same source `.wsz` produce byte-identical `gen/skin_assets.c` and `gen/skin_layout.h`.
- **Preconditions**: Pillow + ImageMagick installed.
- **Steps**: 1. `python3 tools/bake_skin.py -i skins/base-2.91.wsz -o SpotifyDiyThing/gen`. 2. `cd SpotifyDiyThing/gen && sha256sum -c golden.sha256`.
- **Expected result**: `skin_assets.c: OK` and `skin_layout.h: OK`.
- **Status**: passing (2026-05-07). Golden hash committed at `SpotifyDiyThing/gen/golden.sha256`. CI hook deferred until CI exists.

### T026 — [m2-001] Generated headers compile in firmware build
- **Type**: integration
- **Feature(s)**: m2-001
- **Objective**: Verify `gen/skin_assets.c` + `gen/skin_layout.h` build cleanly under `cyd2usb` env without referenced-but-missing-symbol errors.
- **Steps**: `pio run -e cyd2usb`.
- **Expected result**: SUCCESS.
- **Status**: passing (2026-05-07 build clean post-bake). Linker may DCE unused arrays until M3 references them.

### T027 — [m2-001] Preview composite matches reference
- **Type**: visual
- **Feature(s)**: m2-001
- **Objective**: Verify sprite UVs and screen positions match Winamp 2's documented main-window layout.
- **Steps**: Run with `--preview /tmp/skin.png`. Eyeball against a reference Winamp 2 main-window screenshot.
- **Expected result**: Five transport buttons sit in their canonical positions on the main background; no overlap, no off-by-one.
- **Status**: passing (2026-05-07, eyeballed). No checked-in reference.

### T028 — [m2-001] BMP fallback path covers RLE8
- **Type**: integration
- **Feature(s)**: m2-001
- **Objective**: Verify the ImageMagick fallback triggers correctly for BMPs Pillow can't decode (specifically Winamp's `TEXT.BMP`).
- **Steps**: Bake from `skins/base-2.91.wsz` (which contains RLE8 `TEXT.BMP`). Confirm `SKIN_FONT` array is populated and non-trivial.
- **Expected result**: `SKIN_FONT[155*74]` array present, all-zero check fails (palette + glyphs decoded).
- **Status**: superseded by T071 (2026-05-09 — manual BI_RLE8 decoder is now the primary path per ADR-008 Amendment 1; ImageMagick is no longer load-bearing for any RLE8 BMP).

### T071 — [m2-001] Manual BI_RLE8 decoder produces correct pixels for delta-using streams
- **Type**: unit (host-runnable)
- **Feature(s)**: m2-001
- **Objective**: Guard against the silent-corruption regression captured in TASK-042 / LL-017. For a BMP whose RLE8 stream uses delta opcodes (`00 02 dx dy`), `_decode_bmp_rle8` must produce pixel-identical output to ffmpeg's decoder.
- **Preconditions**: Pillow installed; ffmpeg on PATH (test-time only — not a bake-time dep).
- **Steps**:
  1. Extract `BALANCE.BMP` from `skins/base-2.91.wsz` to a tempfile.
  2. Decode via `_decode_bmp_rle8(raw)` → image A.
  3. Decode via `ffmpeg -i tmp.bmp tmp.png` → image B.
  4. Pixel-compare A vs B.
- **Expected result**: Zero mismatches. (Pillow's own decode would mismatch ~16,588 of 29,444 pixels — the test should NOT trust PIL.)
- **Status**: planned. Owner: VE.

### T072 — [m2-001] Bake regression — BALANCE composite contains green bar pixels
- **Type**: integration (host-runnable)
- **Feature(s)**: m2-001
- **Objective**: Catch any future regression where SKIN_MAIN_BG[] loses the green balance-bar pixels (e.g. via Pillow upgrade silently re-asserting itself, or a refactor that breaks the manual-decoder dispatch).
- **Steps**:
  1. Run bake.
  2. Open `gen/composite/balance_bar_frame0.png`.
  3. Assert at least one pixel in the (0..38, 3..7) sub-rect has G ≥ 100 and R < 60 (the canonical Winamp green bar colour family `(30,105,22)` → `(40,153,28)`).
- **Expected result**: Assertion passes. The PIL-broken state would have all-cyan pixels in that sub-rect (G=198 but R=0, fails on R<60... wait, cyan IS R=0 G=198, which would falsely pass the G≥100 threshold). **Refine**: require BOTH G ≥ 100 AND B ≤ 80 — cyan has B=255, so cyan fails. Green pixels have B≈10–30, pass.
- **Status**: planned. Owner: VE.

---

## Suite: dev-001 — Hostile-network shims

DUT-side tests for the development infrastructure. Not part of the production verification suite — manual gate when the relevant network condition is reachable.

### T029 — [dev-001] hardcoded WiFi shim short-circuits portal
- **Type**: e2e
- **Steps**: Place `wifi_creds.h` with a valid SSID/PASS in the sketch dir, flash, observe boot log.
- **Expected result**: `Connecting to hardcoded SSID <name>` line; no `*wm:StartAP` portal entry. On bad creds, fallback to portal after ~30 s.
- **Status**: passing (2026-05-05/06 field debug).

### T030 — [dev-001] DNS override loads + answers from SPIFFS
- **Type**: e2e
- **Steps**: Populate `data/host_overrides.json` with at least one host, `pio run -t uploadfs`, reboot. Observe DUT boot log for `[dns] loaded ...` lines and `[dns] override server up on <ip>:53`.
- **Expected result**: Each host listed; subsequent `[dns] <host> -> <ip>` lines on first resolution. NXDOMAIN for unknown hosts.
- **Status**: passing (2026-05-05).

### T031 — [dev-001] Build-epoch fallback sets clock when network bootstrap fails
- **Type**: e2e
- **Steps**: Boot DUT on a network that blocks both UDP/123 (NTP) and HTTP/80 to `1.1.1.1` (HTTP-Date target).
- **Expected result**: Log line `[time] WARN: NTP+HTTPS-Date failed, falling back to build epoch=<n>` with `n > 1700000000`. Subsequent TLS attempts pass cert `notBefore` check (or fail for an unrelated reason).
- **Status**: passing (2026-05-06 Marriott captive portal pre-auth; epoch=1778045098 set).

---

## Suite: m3-001 — Winamp display backend (M3 scaffold)

DUT-side visual + integration tests. Scaffold lands compile-clean; runtime verification pending the next DUT session.

### T032 — [m3-001] cyd2usb_winamp env builds clean
- **Type**: integration (host build)
- **Feature(s)**: m3-001
- **Objective**: `pio run -e cyd2usb_winamp` succeeds; both `cyd2usb` and `cyd2usb_winamp` link without redefinition errors after the `#pragma once` on `cheapYellowLCD.h`.
- **Steps**: `pio run -e cyd2usb && pio run -e cyd2usb_winamp`.
- **Expected result**: Both SUCCESS; flash usage ≤90 %.
- **Status**: passing (2026-05-07; both envs SUCCESS, flash 88.6 %).

### T033 — [m3-001] Default screen renders skin chrome
- **Type**: visual (DUT)
- **Feature(s)**: m3-001
- **Objective**: After flash on `cyd2usb_winamp`, `showDefaultScreen` paints the 275×116 main background centered on the 320×240 panel, with the five transport buttons in their normal-state positions.
- **Preconditions**: WiFi connected, Spotify creds present, no track playing.
- **Steps**: Boot DUT, observe screen.
- **Expected result**: Skin background visible; PREV/PLAY/PAUSE/STOP/NEXT sprites at canonical x-coords (16/39/62/85/108) on row y=88 in window-local coords; black margin around the window.
- **Status**: passing (2026-05-07 DUT verify, user confirmed).

### T034 — [m3-001] Title text glyphs render legibly
- **Type**: visual (DUT)
- **Feature(s)**: m3-001
- **Objective**: `printCurrentlyPlayingToScreen` writes the track name into the TITLE slot using `SKIN_GLYPH` glyphs; lower-case folds to upper; truncates at slot edge.
- **Steps**: Play a track with a known short ASCII title; observe.
- **Expected result**: Title visible inside (TITLE_X, TITLE_Y, TITLE_W, TITLE_H) area; no overflow into surrounding chrome; slot is repainted from background between title changes.
- **Status**: passing (2026-05-07 DUT verify; marquee scroll also confirmed working on overflow).

### T035 — [m3-001] Progress bar advances inside POSBAR slot
- **Type**: visual (DUT)
- **Feature(s)**: m3-001, poll-002
- **Objective**: `displayTrackProgress` fills a green bar inside `(BAR_X=16, BAR_Y=72, BAR_W=248, BAR_H=10)` in window-local coords, advancing smoothly via the M4 100 ms tick.
- **Steps**: Play a track; observe seek bar over ~30 s.
- **Expected result**: No flicker, no stale fill on track change/seek; advance visible at ~10 Hz.
- **Status**: passing (2026-05-07 DUT verify, user confirmed).

---

## Suite: log-001 — Logging tier 1 (ringbuffer + redactor + decoder + heartbeat)

Back-filled 2026-05-08 per ADR-010-review.md and the 2026-05-08 audit. DUT verification has been ad-hoc; these rows formalize what was tested.

### T036 — [log-001] Ringbuffer wrap, line ordering, /log endpoint
- **Type**: integration (host)
- **Objective**: Inject ≥200 log lines via `LOG_I("test", ...)`; assert `/log?n=80` returns the last 80 in order; assert wrap doesn't tear lines (every line null-terminated).
- **Steps**: Call from a one-shot Sketch in a non-AP-isolated network. `curl http://<dut-ip>/log?n=80`.
- **Expected**: 80 lines returned, oldest → newest, no truncated UTF-8 sequences.
- **Status**: planned (deferred — `/log` HTTP test gated on network without AP client isolation).

### T037 — [log-001] /log?clear=1 empties the ring
- **Type**: integration (host)
- **Steps**: `curl http://<dut-ip>/log?clear=1` then `curl /log`.
- **Expected**: First returns `ok\n`. Second returns 0 lines until next push.
- **Status**: planned (same network gate as T036).

### T038 — [log-001] Secret redactor — boundary cases
- **Type**: unit (host-runnable if `secret.h` is decoupled)
- **Objective**: `redact()` returns shape `XX…YY (len=N)` for n>4; `<short len=N>` for 1≤n≤4; `<empty>` for ""; `<null>` for nullptr; pool of 8 keeps multi-call printf args distinct.
- **Steps**: Invoke from a sketch test fixture; print 9 redacts in one printf and verify slot 0 was overwritten.
- **Expected**: First 8 printf args distinct, 9th is the same as the 1st (rotating).
- **Status**: passing (2026-05-07 DUT verify of "config loaded: clientId=db…e0 (len=32) clientSecret=b9…63 (len=32) refreshToken=AQ…IY (len=131)" — three distinct values rendered correctly).

### T039 — [log-001] mbedtls / HTTP decoder table coverage
- **Type**: unit (host-runnable)
- **Objective**: `tlsErr()` returns documented strings for known codes (0x0050, 0x004C, -76, -80, -9984, -29312, -29184, -30592, -32256). `httpErr()` covers 200/204/30x/40x/50x. Unknown codes fall through with raw hex.
- **Steps**: Call each code, assert string match.
- **Expected**: Per-table strings; unknown formatted as `%d (0x%04X) ?` / `HTTP %d`.
- **Status**: passing (2026-05-07 DUT — `[W][spotify.tls] after -1: rc=-29312 (-0x7280) SSL_CONN_EOF` observed live).

### T040 — [log-001] Heartbeat cadence and field shape
- **Type**: e2e (DUT)
- **Objective**: Monitor for 5 minutes; assert ≥9 lines tagged `hb` arrive; spacing is 30 ± 5 s under normal play; key=value parses cleanly; `block_max=Nms` field present (added by io-001).
- **Steps**: Let DUT run idle for 5 minutes with a track playing, capture serial.
- **Expected**: ≥9 hb lines; cadence stretching only during known blocking calls (TLS retries).
- **Status**: passing (2026-05-08 — 4 heartbeats captured at 30/39/30/62 s spacing; `block_max=Nms` field present).

---

## Suite: io-001 — Loop responsiveness (M-IO tier 1)

Back-filled 2026-05-08 per ADR-011 / 2026-05-08 audit.

### T046 — [io-001] Backoff math on consecutive failures
- **Type**: e2e (DUT)
- **Objective**: After N consecutive failures, next-poll interval is 5 s × min(2^N, 12) capped at 60 s.
- **Steps**: Provoke failures (DNS-mangle / disconnect upstream); observe `[D][spotify.poll] backoff: consecutive=N next=Mms` log lines.
- **Expected**: 5 → 10 → 20 → 40 → 60 → 60 → 60 …
- **Status**: passing (observed during Marriott-WiFi failure bursts; cadence visibly stretches).

### T047 — [io-001] Reset on poll success
- **Type**: e2e (DUT)
- **Objective**: After a backed-off interval, next successful poll resets `consecutiveSpotifyFailures = 0`; subsequent interval returns to base 5 s.
- **Steps**: Trigger a failure burst, restore network, observe.
- **Expected**: First success after recovery resets; next interval is 5 s.
- **Status**: passing (eyeballed).

### T048 — [io-001] Touch resets backoff
- **Type**: e2e (DUT)
- **Objective**: User-initiated touch (prev/next/play/pause/seek) clears `consecutiveSpotifyFailures` so the next poll is immediate (or after the touch-002 1.5 s defer), not after the back-off interval.
- **Steps**: Provoke a 60 s back-off; tap a transport button mid-window.
- **Expected**: Next poll fires within ~1.5 s of the tap, not at the next back-off boundary.
- **Status**: passing (touch-002 also verified concurrently).

### T049 — [io-001] block_max_ms heartbeat field
- **Type**: e2e (DUT)
- **Objective**: Heartbeat emits `block_max=Nms`; under healthy network N stays <2500; during a Marriott TLS-retry burst N rises toward 2000-ish (one SPOTIFY_TIMEOUT) and resets each emit.
- **Steps**: Capture serial; grep `block_max=`.
- **Expected**: Per-emit reset; values consistent with observed network state.
- **Status**: passing (2026-05-08 — `block_max=2644ms` observed during a burst).

---

## Suite: log-002 — On-screen log overlay (M-LOG2)

Back-filled 2026-05-08.

### T050 — [log-002] SCREEN_LOG default-off has zero overhead
- **Type**: visual + flash-budget (DUT)
- **Steps**: Build `cyd2usb_winamp` (no `-DSCREEN_LOG`); flash; observe.
- **Expected**: Default chrome only; flash usage matches pre-overlay baseline (97.6 %); no log text on screen.
- **Status**: passing.

### T051 — [log-002] SCREEN_LOG renders ringbuffer in top + bottom strips
- **Type**: visual (DUT)
- **Steps**: Build `cyd2usb_winamp_screenlog`; flash; let logs flow.
- **Expected**: Green log text top strip (~7 lines, oldest) and bottom strip (~7 lines, newest); chrome unaffected; new entries appear at bottom.
- **Status**: passing (2026-05-07 DUT verify).

---

## Suite: touch-002 — Skin-region touch (M5)

Back-filled 2026-05-08.

### T052 — [touch-002] Each transport button acts on Spotify
- **Type**: e2e (DUT)
- **Objective**: Tap each of the 5 transport sprites; Spotify's playback state changes accordingly.
- **Steps**: Have a track playing on Spotify; tap PREV / PLAY / PAUSE / STOP / NEXT in turn.
- **Expected**: Track skips, plays, pauses, pauses (STOP→pause), skips. Each tap also briefly draws the pressed sprite.
- **Status**: passing (2026-05-08 user confirmed: "all buttons work").

### T053 — [touch-002] Posbar tap seeks
- **Type**: e2e (DUT)
- **Objective**: Tap on the posbar groove; thumb snaps to tap position; Spotify follows.
- **Expected**: Visual: thumb at tap location within one frame. Spotify: progressMs ≈ tap-mapped value within one poll.
- **Status**: passing (2026-05-08 user confirmed).

### T054 — [touch-002] Optimistic-UI freeze on pause/stop/prev/next
- **Type**: visual (DUT)
- **Objective**: After pause/stop/prev/next touch, the M4 interpolator must freeze (no further bar / time-digit advance) until the next poll re-anchors.
- **Steps**: Tap PAUSE; observe bar + time digits.
- **Expected**: Bar + time freeze on the press, stay frozen for ~1.5 s, then jump to true paused position once Spotify confirms.
- **Status**: passing (2026-05-08 — user reported original drift, fix shipped, confirmed working).

---

## Suite: chrome-001 — Main-window decoration (M-CHROME tiers 1+2)

Tests for the Winamp main-window static + dynamic chrome elements. Tier-1 (kbps/kHz strip, MS indicator) + tier-2 static composite (TITLEBAR, BALANCE, kbps/kHz baked, MS_STEREO_ON/MS_MONO_OFF) are visual-only and not currently ticketed here — captured by T027's preview eyeball at bake time. Tier-2 dynamic VOLUME (TASK-041) is testable as below.

### T070a — [chrome-001] Volume snapshot reaches DUT chrome within one poll
- **Type**: e2e (DUT)
- **Feature(s)**: chrome-001 (also exercises api-002 lib-patch surface from TASK-039)
- **Objective**: Confirm a remote `setVolume` call propagates through the next currently-playing poll into a redrawn VOLUME slider on the DUT.
- **Preconditions**: DUT booted, Spotify Connect active device reporting `device.volume_percent`. TASK-041 implementation in tree.
- **Steps**:
  1. Note current volume via `[D][chrome] drawVolume pct=NN keyframe=K` log line on boot.
  2. From host: `curl -X PUT -H "Authorization: Bearer $TOKEN" "https://api.spotify.com/v1/me/player/volume?volume_percent=NN"` with NN in a different keyframe bucket than current. (Or use the existing spike-harness `v` row.)
  3. Observe DUT serial within 5 s for a fresh `drawVolume pct=NN keyframe=K` line.
  4. Visual: VOLUME slider on the DUT now shows the new keyframe.
- **Expected result**: New log line within ≤ 5 s after the API call. Chrome reflects the new keyframe visually. No redraw thrash on subsequent polls when volume hasn't changed (cache-gating works).
- **Status**: passing (2026-05-10 — DUT captured drawVolume bucket transitions `pct=10 keyframe=0` → `pct=90 keyframe=4` against host-side toggle script `/tmp/volume_toggle.py`. Visual: red max-fill bar at 90% confirmed by user. Some poll attempts hit the recurring DUT network-flake ceiling — not a TASK-041 regression).

### T073 — [api-002] `/me/player` is a strict superset of `/me/player/currently-playing` for fields the firmware reads
- **Type**: integration (host-side, no DUT)
- **Feature(s)**: api-002 (lib patch family); supports TASK-043 / ADR-015
- **Objective**: Catch any future Spotify-side change that would make `/me/player` start returning *less* data than `/me/player/currently-playing` for any field the firmware consumes (`is_playing`, `progress_ms`, `currently_playing_type`, `context.uri`, `item.uri`, `item.duration_ms`, `item.name`, `item.artists[0].name`, `device.volume_percent`).
- **Preconditions**: Valid creds in `Spotify-Diy-Thing/data/spotify_diy_config.json`; an active Spotify Connect device playing a track during the test window; Python 3 + `urllib`.
- **Steps**:
  1. Refresh access token from creds.
  2. Within ~200 ms, fetch both `/v1/me/player/currently-playing?additional_types=episode` and `/v1/me/player?additional_types=episode` with the same bearer token.
  3. For each field the firmware reads (list above), assert: present in `/me/player` response with the same value as in `/currently-playing` (drift on `progress_ms` allowed up to 1 s).
  4. Assert `device.volume_percent` exists on `/me/player`.
- **Expected result**: All assertions pass. If any fail, ADR-015 must be re-evaluated and TASK-043 may need to roll back.
- **Status**: passing (2026-05-10 — first run against Web Player Firefox active device, all six firmware-consumed fields matched between endpoints, `device.volume_percent=16` present on `/me/player`).

### T070b — [chrome-001] Sentinel keyframe shows when no active device
- **Type**: e2e (DUT)
- **Feature(s)**: chrome-001
- **Objective**: Confirm KEYFRAME_NONE renders when `device.volume_percent` is unavailable (no active Spotify Connect device, or `device` field absent from the response). Confirm the transition to a real keyframe once a device becomes active.
- **Preconditions**: DUT booted with a fresh Spotify session that has NO active device (close all Spotify clients). TASK-041 implementation in tree.
- **Steps**:
  1. Boot DUT; observe boot log + screen.
  2. Verify `[D][chrome] drawVolume pct=-1 keyframe=NONE` log line and KEYFRAME_NONE (greyed empty track) on screen.
  3. From a phone or desktop Spotify client: start playback (transfer to that device).
  4. Observe DUT serial within ≤ 5 s for a `drawVolume pct=NN keyframe=K` line with `K != NONE`.
  5. Visual: VOLUME slot transitions from empty-grey to the matching real keyframe.
- **Expected result**: KEYFRAME_NONE on boot. Clean transition to a real keyframe on first poll after a device becomes active. No flicker or partial-paint artefacts.
- **Status**: passing (2026-05-10 — full bidirectional cycle captured: `pct=-1 keyframe=NONE` (boot) → `pct=65 keyframe=3` (Web Player active, orange bar) → `pct=-1 keyframe=NONE` (Web Player closed, 204 fired, 204-handler in TASK-043 reset volume to -1, dedup gate fired, NONE rendered). User visually confirmed both transitions. Caveat: pause-without-close keeps the device active, so volume stays at last value — that's correct behaviour, not a regression).

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