# Design — M-CERT-ERRCODE: Dedicated error code for TLS certificate failures

> Owner: Architect
> Status: scheduled — proposed 2026-07-13, no ADR needed (extends ADR-029's error
> surface; no new decision class). Minimal slice shipped as TASK-318
> (M-PR-LOCATIONS); remainder broken down 2026-07-18 as TASK-341..344
> (tasks.md) — this doc is the implementation spec for those tasks.
> Date: 2026-07-13
> Deps: ADR-029 (root-CA pinning), TASK-223 (openHttps helper), M-CONN
> (heartbeat `last=` surface)

## Context / pain point

When mbedTLS rejects a peer certificate, the handshake aborts with
`MBEDTLS_ERR_X509_CERT_VERIFY_FAILED` (`-0x2700` = `-9984`). That code never
reaches the app layer: Arduino's `HTTPClient` collapses any pre-connect
failure into `-1 HTTPC_ERROR_CONNECTION_REFUSED`. At the `errorCode` surface
(dataTask result structs, app error rows, heartbeat `last=`), **pin rot is
indistinguishable from a plain dead host.**

Today the only place `-9984` is visible is the serial log via
`tlsErr()` (`logDecode.h:25`) — i.e. you must be watching the monitor at the
moment of failure. Both coingecko root flips (2026-06-12 GTS→ISRG,
2026-07-08 ISRG→GTS, TASK-298) were diagnosed that way, at DUT-session cost.

This matters more now: the pin roster is growing (planeradar/adsb.fi added
2026-07; a Nominatim geocode pin is proposed by M-PR-LOCATIONS), and the
Nominatim chain carries a known future-rot mechanism — it reaches our pinned
ISRG Root X1 only via the cross-signed `ISRG Root YR` intermediate that
openstreetmap.org currently serves. When that cross-sign is dropped, we want
the failure to name itself on screen.

Existing mitigations and their gaps:

- Host-side cert preflight (`run/test` step 0, warn-only) — catches rot
  before a test session, but not in normal device operation, and only for
  hosts the preflight probes.
- `tlsErr()` log decode — post-hoc, serial-only.

## Goal

A cert-verify failure anywhere in the dataTask fetch path surfaces as its own
`errorCode` sentinel — on the app error row, in `get dataq`, and in the
heartbeat — with zero per-fetcher boilerplate.

## Design

### Sentinel value

`-120 CERT_VERIFY_FAILED`.

Why not adjacent to `-100`: the internal code space is already crowded below
-90 — `-100` (begin-failed), `-91..-95` (stock parse phases), and PlaneRadar's
`-90-err.code()` open-ended JSON-parse range (`dataTask.h:142`), which can
reach -101 and below for large ArduinoJson error codes. `-120` starts a new
reserved band; document `-120..-129` as "TLS-layer sentinels" in the
`dataTask.h` errorCode convention comment so future TLS-adjacent codes
(e.g. a hypothetical handshake-timeout sentinel) land next to it instead of
colliding.

### Detection point — `openHttps()` (single hook)

`WiFiClientSecure::lastError(buf, len)` returns the underlying mbedTLS error
int after a failed connect. Hook it in the one shared place
(`dataTaskStorage.cpp:159`):

```cpp
static int openHttps(WiFiClientSecure& tls, HTTPClient& http, const char* url,
                     const char* rootCA, bool insecure) {
    if (insecure) tls.setInsecure();
    else          tls.setCACert(rootCA);
    http.useHTTP10(true);
    if (!http.begin(tls, url)) return OPENHTTPS_BEGIN_FAILED;
    int code = http.GET();
    if (code < 0) {
        char ebuf[64];
        if (tls.lastError(ebuf, sizeof(ebuf)) == -0x2700 /* X509_CERT_VERIFY_FAILED */)
            return CERT_VERIFY_FAILED;   // -120; caller still http.end()s (begin succeeded)
    }
    return code;
}
```

Note the containment: `-120` is only substituted for an already-negative
GET() result, so the OPENHTTPS_BEGIN_FAILED / post-begin-cleanup distinction
(the reason `OPENHTTPS_BEGIN_FAILED` is `INT_MIN`, see comment at
`dataTaskStorage.cpp:147-156`) is untouched.

### Fetchers not on the helper — audit + migrate

Not every fetcher goes through `openHttps()` (e.g. `fetchWeather()` at
`dataTaskStorage.cpp:176` hand-rolls begin/GET; `fetchOneMirror()` for
radio-browser has its own path). Implementation task includes an audit pass:
migrate hand-rolled fetchers onto `openHttps()` where the divergence was
historical accident, or add the same two-line `lastError()` check where the
custom path is deliberate (radio-browser's per-mirror skip logic). The
milestone is DONE only when **every `setCACert()` call site** in
`dataTaskStorage.cpp` reports `-120` on verify failure.

Out of scope: `spotifyTask` (separate task, own cert handling and error
surface) and the WebRadio *audio stream* path inside the audioI2S library
(station-list fetch IS in scope — it's a dataTask fetcher).

### Decode + display

- `logDecode.h` `httpErr()`: add `case -120: return "-120 CERT_VERIFY_FAILED";`
  next to the `-100` sentinel. Apps that render `errorCode` numerically get
  the distinct number for free; apps using `httpErr()` get the name.
- `dataTask.h:139` convention comment: document the `-120..-129` band.
- `dataTaskCerts.h` header comment: note that remediation for a `-120` is the
  ADR-029 rotation-table procedure (update PEM + reflash).

No new UI. The value of this milestone is that the *existing* surfaces
(app error rows, `get dataq`, heartbeat `last=`) become diagnostic.

## Host-side: build-time validity check + guided rotation (added 2026-07-13)

Human ask: run cert validity tests at build time, and "update if needed"
before ESP32 compilation. Split into three pieces with different answers:

### 1. Validity test — exists, reuse it

`run/check-datatask-certs` already is the validity test: strict offline
single-root chain verify per endpoint, PEMs parsed from `dataTaskCerts.h`
(can't drift from firmware), PASS/FAIL/ERROR with network-vs-chain
distinction. Changes here are only roster upkeep (M-PR-LOCATIONS adds
`nominatim.openstreetmap.org`).

### 2. Build-time hook — warn-only preflight, not a gate

Add the preflight to `run/build` / `run/build-debug` (and it's inherited by
`run/flash*` which call build), **warn-only**, mirroring the run/test step-0
pattern:

- FAIL prints a loud banner naming the endpoint(s) but does not block the
  compile — a rotted pin is a runtime property of one endpoint, not a build
  defect, and post-sentinel it degrades to a visible `-120` on device.
- ERROR (network unreachable) prints one line and moves on — builds must
  stay possible offline. `CERT_PREFLIGHT=0` env knob skips entirely (CI /
  air-gapped).
- Latency guard: the 8-endpoint probe costs a few seconds; acceptable
  against a multi-minute PIO compile. Keep TIMEOUT_S at 10 and run probes
  concurrently if it ever annoys.

Additionally a **fully offline expiry check** (new, cheap, deterministic):
parse each pinned PEM's `notAfter` locally and warn when within 180 days.
This one CAN run unconditionally — no network, no flake. Current roots all
expire 2035–2038, so it's silent for years; it exists to catch a
short-lived root/intermediate accidentally pinned in a future rotation
(the TASK-109c intermediate-pin mistake would have tripped it, expiry 2030).

### 3. "Update if needed" — propose, never apply

Explicit non-goal: **no automatic PEM replacement.** Rationale:

- Auto-accepting whatever root the live server presents is trust-on-first-
  use; it converts ADR-029's human trust decision into "trust anything once,
  forever" and lets a build-time MITM bake itself into firmware.
- Single probes are unreliable evidence: coingecko's Cloudflare edge
  load-balances between ISRG and GTS chains (flipped twice, TASK-298). An
  auto-updater observing one chain would have "corrected" the two-root
  bundle back to a single pin and reintroduced the exact breakage the
  bundle fixed. Deciding pin-vs-bundle needs multi-observation judgement
  (cf. PLANERADAR_ROOT_CA's two-independent-day rule).

Instead, extend the checker with `--propose-fix`: on FAIL it fetches the
served chain, identifies the root (or notes the chain terminates in a root
we don't have), and writes a report to `scratch/` containing the candidate
root's subject/issuer/fingerprint/notAfter, the ready-to-paste PEM block,
and a reminder of the two open judgement calls: (a) verify the fingerprint
against the CA's published root (CCADB/Mozilla store), (b) decide
replace-vs-bundle based on whether the old root still appears on repeat
probes. Human reviews, edits `dataTaskCerts.h`, re-runs the checker to
green, commits — same approval flow as TASK-298, minus the legwork.

## Verification sketch (VE to own)

- **T_CERT_ERR_01 (DUT):** debug-build serial command (`set certbreak <app>`)
  swaps in a syntactically-valid wrong root CA for the next fetch of that
  app; expect the app's error row and `get dataq` to show `-120`, and the
  fetch to recover on the following cycle once the override auto-clears.
  Follows the TASK-276-style injected-state pattern; needs the same
  autoSkip/retry isolation care LL-noted there.
- **Host sanity:** none needed beyond existing cert preflight — this is a
  device-side surfacing change, not a reachability change.
- Regression guard: `run/check` gate 5 unaffected; no golden changes.
- **T_CERT_HOST_01:** `--propose-fix` against a deliberately-wrong pinned
  root (checker run with a doctored copy of dataTaskCerts.h, not the real
  one) produces a report naming the actual served root.
- **T_CERT_HOST_02:** offline expiry check trips on a PEM with
  `notAfter` < 180 days (synthetic cert), silent on the shipped roster.

## Effort / risk

Small-to-medium (grew with the host-side section). Device side: one helper
edit, one decode case, an audit of ~8 `setCACert()` call sites, one debug
command, one DUT test. Host side: build-script hook (warn-only + env knob),
offline expiry parse, `--propose-fix` report mode. Risk: `lastError()` semantics across
the Arduino-ESP32 2.0.17 ssl_client (does a *connection-refused-before-TLS*
leave a stale prior error in the mbedtls ctx?). Mitigate: check that
`lastError()` is only consulted when GET() failed **and** the error is
exactly `-0x2700`; a stale-but-different code falls through to the raw
HTTPClient code as today. Verify stale-error behaviour on DUT as part of
T_CERT_ERR_01 (break cert, recover, then unplug-host fail → must show -1/-11,
not a lingering -120).

## Open questions

- **Q1** — Should the heartbeat additionally latch a "last cert failure
  (host, timestamp)" line, given rot can be transient under Cloudflare
  multi-chain load-balancing (coingecko pattern)? Lean: yes, one static
  slot, but only if free — not worth new heartbeat plumbing on its own.
