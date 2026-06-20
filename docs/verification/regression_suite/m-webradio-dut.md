# M-WEBRADIO DUT VE Suite

> Owner: Verification Engineer
> Milestone: M-WEBRADIO (TASK-207, TASK-208, TASK-209, TASK-214)
> Status: open — awaiting DUT run
> DUT: ESP32-2432S028R CYD2USB, firmware cyd2usb_winamp_debug
> Exit criteria: TASK-207 pass criteria, TASK-208 pass criteria, TASK-209 pass criteria, TASK-214 pass criteria

---

## Test inventory

| ID                  | Description                                                              | Method              | Result                   |
|---------------------|---------------------------------------------------------------------------|---------------------|--------------------------|
| T_WR_TLS_01         | Station fetch succeeds; `wrLastHttp` reports http=200 and which TLS path fired | serial          | open — awaiting DUT run  |
| T_WR_SPOTIFY_RESUME_01 | Spotify resumes normally after eject back out of WebRadio playback   | serial + visual      | open — awaiting DUT run  |
| T_WR_COEX_01  | Audio plays and VU meter animates while station connected                 | serial + audible    | open — awaiting DUT run  |
| T_WR_COEX_02  | Injected tap fires while audio playing — wrIdx changes on prev/next      | serial              | open — awaiting DUT run  |
| T_WR_COEX_03  | No audio dropout correlated with touch events over ≥ 2 min              | audible + serial    | open — awaiting DUT run  |
| T_WR_COEX_04  | Touch response unaffected by audio playback — tap latency normal         | serial              | open — awaiting DUT run  |
| T_WR_HEAP_01  | minFreeHeap at app launch (baseline) recorded                            | serial log          | open — awaiting DUT run  |
| T_WR_HEAP_02  | minFreeHeap at post-fetch (TLS torn down) ≥ 30 KB                       | serial log          | open — awaiting DUT run  |
| T_WR_HEAP_03  | minFreeHeap during sustained audio decode ≥ 40 KB                       | serial log          | open — awaiting DUT run  |
| T_WR_HEAP_04  | No heap panic / stack overflow over 5-minute playback run                | serial log          | open — awaiting DUT run  |
| T_WR_VOL_01   | Volumes 1–10 produce clean output; clipping level identified             | audible             | open — awaiting DUT run  |
| T_WR_VOL_02   | kMaxVolumeStock determined = (clip − 2); matches design estimate ≈ 10 ±2 | audible             | open — awaiting DUT run  |
| T_WR_VOL_03   | Normal play uses g_settings.webRadioMaxVolume as ceiling (not 21)        | serial              | open — awaiting DUT run  |

---

## Notes

- **T_WR_TLS_01 / TASK-214 context**: the original diagnosis ("radio-browser.info omits the R13 intermediate, mbedtls can't build the chain") is now disputed by a host-side re-check (2026-06-20, `./run/check-datatask-certs`) — `de1.api.radio-browser.info` (mirror[0], tried first) currently presents a complete, verifying chain (leaf → R13 → ISRG Root X1) from at least one network vantage point. The fix was re-scoped from unconditional `setInsecure()` to try-`setCACert()`-first-then-fallback (see `dataTaskStorage.cpp::fetchOneMirror()`). **This test's job is to observe which path actually fires on real hardware** — `tlsInsecure:0` in `wrLastHttp` means the strict path succeeded (no ADR-029 exception needed for that run); `tlsInsecure:1` means it fell back. Either outcome can be a genuine PASS for *station loading*; record which one happened, it's the data point the Architect needs to decide whether ADR-029 needs an amendment at all.
- **T_WR_SPOTIFY_RESUME_01 context**: `dafa4a4` added `spotifyTask::tlsYield()`/`tlsResume()` around WebRadio playback (frees ~50 KB so `connecttohost()`'s contiguous alloc doesn't compete with Spotify's fragmenting heap). This is a new coexistence path with no prior coverage — confirm Spotify actually comes back to life (track info repaints, transport controls respond) after a play→eject cycle, not just that the device doesn't crash.
- **T_WR_COEX_03** requires human operator with 8 Ω speaker on SPEAK header — serial alone cannot confirm absence of audible glitch.
- **T_WR_COEX_02**: use `tap <x> <y>` to inject touch events; PREV zone x<120, NEXT zone x>200 in CYD coordinate space at any y in touch area (~y=100–230).
- **T_WR_HEAP_01–04**: heap values appear in `./run/monitor-read` output as `LOG_I("webradio", "HEAP ...")` lines logged at: app launch, pre-fetch, post-fetch (TLS torn down), first `connecttohost()`, and every 30 s during playback.
- **`set wrVol <n>`** is a raw calibration bypass — it calls `wrAudio().setVolume(n)` directly, intentionally bypassing `webRadioMaxVolume`. Use this for TASK-209 sweep. **Do not** confuse with normal operation where `_play()` applies the `webRadioMaxVolume` cap.
- **T_WR_VOL_03**: normal `_play()` path uses `wrAudio().setVolume(g_settings.webRadioMaxVolume)` — verify by issuing `set wrStop 1`, then `set wrPlay 0`, then `set wrVol 21`, then `set wrStop 1`, `set wrPlay 0` again — the re-play should reset volume to maxVolume (default 10), not 21.
- GPIO25 (XPT2046 SPI SCK) and GPIO26 (I2S-DAC) are independent buses; electrical risk is low but PCB routing is unverified for this board revision.
- **TASK-208 pass criteria are stale as written** — they assume TLS spike (~50–70 KB) and audio decode (~40–60 KB) are non-overlapping. `dafa4a4` changed that: `spotifyTask::tlsYield()` now holds Spotify's TLS session yielded for the *entire* playback duration, not just during the station-list fetch. Treat T_WR_HEAP_03/04 thresholds as provisional until re-validated against this 3-way interaction (radio decode + held-yielded Spotify state + station doc); if `minFreeHeap` comes in lower than 40 KB but still positive, that's new information, not necessarily a regression — record the actual number before deciding pass/fail.

---

## Preconditions (common)

- `./run/flash-debug` complete, firmware `cyd2usb_winamp_debug`.
- 8 Ω speaker connected to SPEAK header (required for T_WR_COEX_03, T_WR_VOL_01/02).
- Device on WiFi, monitor running (`./run/monitor-start`).
- Station list loaded: `get wrCount` returns `count >= 1`.

---

## T_WR_TLS_01 — Station fetch succeeds; record which TLS path fired

- **Type**: DUT serial
- **Task**: TASK-214
- **Preconditions**: `./run/flash-debug` complete, device on WiFi, monitor running. Does **not** require station list pre-loaded — this test is what confirms that.
- **Steps**:
  1. `tap 136 89` — switch to WebRadio (triggers the station-list fetch if list is stale/empty).
  2. Poll `get wrCount` until `count >= 1` or ~10 s elapse (mirror fallback + insecure retry can take a few seconds across 3 mirrors).
  3. `get wrLastHttp` — record `http`, `ok`, `count`, `jsonErr`, `tlsInsecure`.
- **Expected**: `http:200`, `ok:1`, `count>=1`. `tlsInsecure` can legitimately be `0` (strict `setCACert()` path succeeded) or `1` (fell back) — **record which one**, don't treat either as fail by itself.
- **Fail**: `count=0` after all 3 mirrors exhausted on both TLS paths — note `jsonErr` and `http` for further diagnosis; re-run `./run/check-datatask-certs` from the dev host at the same time to compare host-side chain state against what the DUT saw.
- **Follow-up for Architect**: if this comes back `tlsInsecure:0` consistently across repeated runs, the `setInsecure()` fallback in `fetchOneMirror()` is dead code for now and ADR-029 doesn't need an amendment — file that finding back to TASK-214 either way.

---

## T_WR_SPOTIFY_RESUME_01 — Spotify resumes after eject out of WebRadio

- **Type**: DUT serial + visual
- **Task**: TASK-214 (regression introduced by the `tlsYield()`/`tlsResume()` change in `dafa4a4`)
- **Preconditions**: Spotify actively playing a track before switching to WebRadio.
- **Steps**:
  1. Note current Spotify track via `get touchResult` or on-screen title.
  2. `tap 136 89` — switch to WebRadio.
  3. Select and play any station (`set wrPlay 0` or tap a PLEDIT row); confirm `get wrState` = `state:2` (PLAYING).
  4. `tap 136 89` again — eject back to Spotify.
  5. Confirm Spotify's display repaints with current track info (not stale/frozen).
  6. Tap a transport button (e.g. next track) and confirm Spotify responds normally.
- **Expected**: Spotify polling/playback resumes with no visible delay or stuck state; transport controls work immediately after eject.
- **Fail**: Spotify display frozen, transport unresponsive, or a crash/reboot on eject — indicates `spotifyTask::tlsResume()` did not actually restore a usable session.

---

## T_WR_COEX_01 — Audio plays, VU meter animates

- **Type**: DUT serial + audible
- **Task**: TASK-207
- **Steps**:
  1. `tap 136 89` — switch to WebRadio.
  2. Wait for `get wrState` to return `state:2` (PLAYING).
  3. Confirm audible audio from speaker.
  4. `get wrState` — assert `state:2` sustained.
- **Expected**: `state:2` confirmed; audio audible.

---

## T_WR_COEX_02 — Injected tap fires while audio playing

- **Type**: DUT serial
- **Task**: TASK-207
- **Steps**:
  1. Confirm `get wrState` = `state:2` (PLAYING).
  2. Record current `get wrIdx`.
  3. Send `tap 240 160` (NEXT zone).
  4. Assert `get wrIdx` incremented (or wrapped).
  5. Repeat with `tap 60 160` (PREV zone).
  6. Assert `get wrIdx` decremented.
- **Expected**: Station index changes on each tap; serial confirms touch registered.

---

## T_WR_COEX_03 — No audio dropout over ≥ 2 min with concurrent touch

- **Type**: DUT audible + serial
- **Task**: TASK-207
- **Steps**:
  1. Confirm playing (`get wrState` = 2).
  2. Every ~10 s, send `tap 240 160` or `tap 60 160` — total ≥ 12 taps over 2 min.
  3. Confirm no ERROR state (`get wrState` stays 2 throughout).
  4. Listen for audio glitches, stutters, or dropouts correlated with taps.
- **Expected**: `wrState` = 2 throughout. No audible dropout on tap events.

---

## T_WR_COEX_04 — Touch latency normal during playback

- **Type**: DUT serial
- **Task**: TASK-207
- **Steps**:
  1. While playing, send `tap 240 160` and time the serial response (approximate).
  2. Assert response arrives promptly (< 500 ms subjective estimate from CLI).
  3. Confirm `get wrIdx` matches expectation.
- **Expected**: Serial tap response and station change happen without perceptible lag.

---

## T_WR_HEAP_01 — App-launch heap baseline

- **Type**: DUT serial log
- **Task**: TASK-208
- **Steps**:
  1. `tap 136 89` — switch to WebRadio app.
  2. `./run/monitor-read 100` immediately.
  3. Find `HEAP init free=...` and `HEAP pre-fetch free=...` log lines.
  4. Record `free` and `min` values.
- **Expected**: `min` ≥ 30 KB at launch baseline. Log lines present.

---

## T_WR_HEAP_02 — Post-fetch heap (TLS spike recovery)

- **Type**: DUT serial log
- **Task**: TASK-208
- **Steps**:
  1. Wait for `get wrCount` ≥ 1 (station list loaded).
  2. `./run/monitor-read 200`.
  3. Find `HEAP post-fetch free=...` log line.
  4. Record `min` value.
- **Pass**: `min` ≥ 30 KB.
- **Fail action**: heap too low → reduce `MAX_STATIONS` or tune ArduinoJson filter.

---

## T_WR_HEAP_03 — Audio decode heap watermark

- **Type**: DUT serial log
- **Task**: TASK-208
- **Steps**:
  1. Start a station (`set wrPlay 0`).
  2. Wait 30 s; `./run/monitor-read 200`.
  3. Find `HEAP play free=...` log lines.
  4. Record `min` across all 30-s logs over 5 min.
- **Pass**: `min` ≥ 40 KB at every sample.
- **Fail action**: reduce audio ring buffer or investigate Audio library alloc.

---

## T_WR_HEAP_04 — No panic over 5-minute run

- **Type**: DUT serial log
- **Task**: TASK-208
- **Steps**:
  1. Play for 5 min.
  2. `./run/monitor-read 500`.
  3. Grep for `panic`, `abort`, `stack overflow`, `Guru Meditation`.
- **Pass**: none of those strings present.

---

## T_WR_VOL_01 — Volume sweep, clipping level identification

- **Type**: DUT audible
- **Task**: TASK-209
- **Steps**:
  1. Start station (`set wrPlay 0`).
  2. `set wrVol 1`, listen 5 s. Repeat for 2, 3, ..., 21.
  3. Note the first level N at which distortion/clipping is audible.
- **Expected**: Levels 1–(N−1) produce clean output.

---

## T_WR_VOL_02 — kMaxVolumeStock determination

- **Type**: DUT audible
- **Task**: TASK-209
- **Steps**:
  1. Take N from T_WR_VOL_01.
  2. `kMaxVolumeStock = N − 2` (headroom).
  3. Assert `kMaxVolumeStock` is in range 8–12.
  4. Record value for firmware constant update.
- **Expected**: kMaxVolumeStock ≈ 10 ± 2. If outside range, note and escalate.

---

## T_WR_VOL_03 — Normal play applies webRadioMaxVolume cap

- **Type**: DUT serial
- **Task**: TASK-209
- **Steps**:
  1. `set wrStop 1` — stop audio.
  2. `set wrVol 21` — force volume high via calibration bypass.
  3. `set wrPlay 0` — start new play; `_play()` calls `wrAudio().setVolume(g_settings.webRadioMaxVolume)`.
  4. Confirm LOG_I "vol" line shows volume reset to default (10), not 21.
  5. Confirm audio plays without clipping at the default level.
- **Expected**: After `set wrPlay 0`, effective volume is `webRadioMaxVolume` (10), not the injected 21.

---

## Exit criteria coverage

| Criterion                                              | Task      | Test(s)               | Status                  |
|--------------------------------------------------------|-----------|-----------------------|-------------------------|
| Station list loads on real hardware; TLS path recorded | TASK-214  | T_WR_TLS_01           | open — awaiting DUT run |
| Spotify resumes cleanly after WebRadio TLS yield        | TASK-214  | T_WR_SPOTIFY_RESUME_01| open — awaiting DUT run |
| No audio dropout correlated with touch events          | TASK-207  | T_WR_COEX_03          | open — awaiting DUT run |
| Touch fires correctly during audio playback            | TASK-207  | T_WR_COEX_02, 04      | open — awaiting DUT run |
| ≥ 2 min continuous playback + touch without failure    | TASK-207  | T_WR_COEX_01–04       | open — awaiting DUT run |
| TLS phase minFreeHeap ≥ 30 KB                         | TASK-208  | T_WR_HEAP_02          | open — awaiting DUT run |
| Audio decode phase minFreeHeap ≥ 40 KB (provisional, see TASK-208 note above) | TASK-208  | T_WR_HEAP_03          | open — awaiting DUT run |
| No heap panic / stack overflow over 5-min run          | TASK-208  | T_WR_HEAP_04          | open — awaiting DUT run |
| kMaxVolumeStock determined; matches ≈ 10 ±2            | TASK-209  | T_WR_VOL_01, 02       | open — awaiting DUT run |
| Normal play applies webRadioMaxVolume cap              | TASK-209  | T_WR_VOL_03           | open — awaiting DUT run |

---

## How to run

```sh
# Prerequisites
./run/flash-debug
./run/monitor-start
./run/check-datatask-certs   # host-side cross-check — run alongside T_WR_TLS_01

# TASK-214 — TLS path + Spotify coexistence (run first; gates everything below)
tap 136 89          # switch to WebRadio, triggers station fetch
get wrCount         # poll until count >= 1
get wrLastHttp      # record http / ok / count / jsonErr / tlsInsecure
tap 136 89          # eject back to Spotify
# confirm Spotify display + transport responsive (T_WR_SPOTIFY_RESUME_01)

# TASK-207 — Touch + audio coexistence
tap 136 89          # switch to WebRadio
get wrState         # assert state:2 (PLAYING)
tap 240 160         # NEXT
tap 60 160          # PREV
# repeat taps every ~10 s for ≥ 2 min while listening

# TASK-208 — Heap watermark
./run/monitor-read 500   # check HEAP log lines after 5 min play

# TASK-209 — Volume calibration
set wrVol 1              # start sweep
# ... step to 21, note first clip level N
# kMaxVolumeStock = N - 2

./run/test-targeted T_WR_TLS_01,T_WR_SPOTIFY_RESUME_01,T_WR_COEX_01,T_WR_COEX_02,T_WR_COEX_03,T_WR_COEX_04,T_WR_HEAP_01,T_WR_HEAP_02,T_WR_HEAP_03,T_WR_HEAP_04,T_WR_VOL_01,T_WR_VOL_02,T_WR_VOL_03
```
