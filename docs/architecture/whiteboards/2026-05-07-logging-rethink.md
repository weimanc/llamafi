# Whiteboard — Logging rethink

> Owner: Architect (whiteboard, not a decision yet — feeds an ADR)
> Date: 2026-05-07
> Trigger: User during M3 DUT verification — "improve logging"

## Pain points observed this session

- **Boot trace is lost** if the serial monitor attaches after boot completes. Today's verify cycle nearly lost the "winamp display setup" confirmation line. No on-device buffer to replay.
- **No levels, no tags.** Mix of free-form `Serial.println` (ours), ad-hoc `SPOTIFY_DEBUG` macros (vendored lib), and Arduino-ESP32 system errors (`[E][ssl_client.cpp:37] _handle_error()`). Cannot filter; cannot grep coherently.
- **Secret hygiene is fragile.** `configFile.h` still prints the parsed JSON to Serial — refresh token + client secret are emitted on every boot. LL-002/LL-003 flagged this; the fix landed in the vendored lib (SPOTIFY_DEBUG off) but not in our own code. Logs from this very session contain live secrets.
- **mbedTLS error codes are opaque.** `(0x0050)`, `(0x004C)`, `(-9984)` mean nothing without a lookup. Each shows up bare; we re-derive their meaning every time.
- **State-machine transitions are invisible.** Poll loop, TLS lifecycle, display state, DRD trigger — no structured trace. We see effects (a 403, a hang) without the precondition that produced them.
- **Hangs are silent.** TASK-014 (album-art fetch hang): `Removing existing image` then nothing. No progress log inside `displayImageUsingFile` to localise the freeze.
- **No remote sink.** Cannot capture logs while the DUT is off-tether, in a captive-portal session, or running unattended overnight.
- **No counters.** Poll success/failure, HTTP codes seen, TLS retries — would diagnose intermittent issues that single-line errors don't capture.

## Goals (what "good logging" looks like here)

1. Levelled (ERROR / WARN / INFO / DEBUG / VERBOSE), per-tag (`wifi`, `spotify`, `tls`, `display`, `nfc`, `time`, `cfg`).
2. Runtime-filterable without recompile (set per-tag level via menuconfig sketch-side or a serial command).
3. Boot trace recoverable post-hoc — not lost just because monitor attached late.
4. Secret-safe by construction: redacting helpers, single-source secret accessor, no raw config dump.
5. Decoded errors: TLS / HTTP / mbedtls codes printed with their string meaning.
6. State-machine trace points at poll-loop transitions, display-state changes, DRD triggers, captive-portal entry.
7. Remote sink optional (UDP syslog or similar) for headless capture.
8. Counters/heartbeat: every N seconds dump a one-line status (display mode, wifi RSSI, free heap, poll counters, last HTTP code).

## Design space

### Transport / framework

- **A — Adopt ESP-IDF `esp_log`.** Already in the build; tag + level macros (`ESP_LOGI(TAG, ...)`); per-tag runtime level via `esp_log_level_set`. Output goes through a single `esp_log_set_vprintf` hook we own. Hook can fan out to Serial, an in-RAM ringbuffer, and (optionally) UDP. **Cost**: migrate existing `Serial.println` call sites. **Reward**: leverage what's there; ESP-IDF system errors (mbedtls, lwip, wifi) already come through this pipe — they'll get our formatting too.

- **B — Custom macro layer over Serial.** Hand-rolled `LOG_INFO("tag", ...)`. Pure Arduino feel; no IDF coupling. **Cost**: duplicates work. **Reward**: full control of format. **Verdict**: not worth it when (A) is free.

- **C — Hybrid.** New code uses (A); old `Serial.println` stays until touched. **Cost**: two systems for a while. **Reward**: incremental, no big-bang migration. **Verdict**: probably how (A) lands in practice anyway.

→ **Lean: A, with C-style migration ordering.**

### Buffering

- **B1 — In-RAM ringbuffer** behind the `esp_log` hook, ~8–16 KB. Last N log lines retrievable on demand. Survives missed serial monitor attaches. Cleared on reboot.
- **B2 — SPIFFS-backed ringbuffer.** Survives reboot. Wear concerns; small SPIFFS partition. Useful for crash forensics; overkill for "I missed boot."
- **B3 — Both, layered.** RAM ring is the default; on `panic`/`abort` flush to SPIFFS.

→ **Tier 1: B1 only.** SPIFFS layer is post-MVP.

### Remote sink

- **R1 — UDP syslog (RFC 5424-ish).** Cheap, async, lossy (UDP). Receiver = `nc -ul 514` on dev host. Skipped automatically in offline modes.
- **R2 — TCP log shipper.** Reliable but blocks on slow links; bad for real-time.
- **R3 — HTTP/HTTPS endpoint.** Heavyweight; cost per line.
- **R4 — In-firmware HTTP fetch endpoint** (the device serves `/log` over its existing web server). Pull, not push. No always-on UDP listener needed on host.

→ **Tier 1: R4 (pull).** It's a few lines on top of the WiFiManager web server we already run. **Tier 2: R1 (push)** when we want continuous capture — but it can wait until there's a use case.

### Secret hygiene

- One-way redactor at the boundary: `redactSecret(token) -> "AQ…IY (len=131)"`. Banned: printing the parsed config JSON. Lint-style review (humans) plus a CI grep when CI exists.
- Vendored-lib audit: `SPOTIFY_DEBUG` already off (LL-002 follow-up); confirm no Bearer token gets `printf`-ed in error paths.

### Decoded errors

- mbedTLS: short table covering the codes we've actually hit (0x0050, 0x004C, 0x4C, -9984, -76, -80). Lookup macro at the log site:
  `LOG_TLS_ERR(rc) -> "0x0050 NET_CONN_RESET"`. Anything not in the table prints as raw hex.
- HTTP: pair status code with endpoint + Spotify error body's `error.message` if we can cheaply parse it.

### State-machine traces

- Poll-loop tags: `spotify.poll.begin`, `spotify.poll.ok`, `spotify.poll.4xx`, `spotify.poll.tls_err`, `spotify.poll.skip`.
- Display-state tags: `display.skin.show`, `display.title.set`, `display.bar.tick`, `display.button.press`.
- Lifecycle tags: `wifi.connect.{begin,ok,fail}`, `time.sync.{ntp,httpsdate,buildepoch,fail}`, `drd.{normal,double_reset}`, `cfg.load.{ok,missing,parse_fail}`.

Each transition is one INFO line; per-tick polling stays at DEBUG so it doesn't drown the channel.

### Heartbeat

- Once every 30 s at INFO: `hb display=winamp wifi=RSSI(-58) heap=128k poll=ok(204):42 last=200`.
- Single line, machine-greppable, key=value pairs.

## What this doesn't try to be

- Not a metrics system (no Prometheus, no OTel). Counters are dumped as text in heartbeat lines, not exported.
- Not crash forensics. SPIFFS-backed and panic-handler are post-MVP — separate ADR if/when we need them.
- Not silent. We deliberately keep INFO chatty enough that "the box is alive and doing X" is obvious from a tail; quiet logs are anti-debugging.

## Tiering for the roadmap

**Tier 1 (close the worst pain):**
1. `esp_log` adoption + tag taxonomy. New code only; existing `Serial.println` left in place.
2. RAM ringbuffer + `/log` HTTP endpoint to retrieve last N lines.
3. Secret redactor; remove the `configFile.h` JSON dump and any other call sites that print tokens.
4. mbedTLS / HTTP code decoder.
5. Heartbeat line every 30 s.

**Tier 2 (when the use case shows up):**
6. UDP syslog push for continuous capture.
7. Migrate noisy legacy `Serial.println` sites to `esp_log`.
8. State-machine tags wired into the poll loop, display, time/wifi lifecycles, DRD path.

**Tier 3 (if/when crash forensics matter):**
9. SPIFFS-backed ringbuffer + panic-handler flush.
10. Per-tag runtime control via serial command or web UI.

## Open questions for the ADR

- Tag taxonomy: short tokens vs. namespaced (`wifi.connect` vs. `WIFI`). Lean: short namespaced, lower-case.
- Default level per tag at boot: INFO baseline, DEBUG for `display` and `spotify` while M3/M5 are active, WARN for vendored libs that we can't easily silence.
- Ringbuffer size vs. heap pressure: 8 KB rings ~80 lines @100 chars; 16 KB if heap allows.
- Where the redactor lives: a small `secret.h` next to `configFile.h`, or a single helper inside `serialPrint.h` so it's hard to bypass.

## Hand-off

This whiteboard becomes ADR-010 (proposed) when the open questions above resolve. PM: please add a tier-1 task entry to the roadmap; Developer/Architect can then take it as work.
