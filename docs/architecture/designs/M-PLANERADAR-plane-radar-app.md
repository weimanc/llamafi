# Design — M-PLANERADAR: ADS-B Plane Radar app

> Owner: Architect
> Status: draft — designer-review PASS 2026-07-10 (4 rounds, incl. independent re-execution of the phase-0 harness); human sign-off pending
> Date: 2026-07-10
> Feeds: (ADR TBD on acceptance)
> Tracked-as: (TASK TBD — PM to schedule)

## Context / pain points

Reference project: `~/proj/esp/ESP32-Plane-Radar` ([MatixYo/ESP32-Plane-Radar](https://github.com/MatixYo/ESP32-Plane-Radar)).
Standalone firmware for an **ESP32-C3 Super Mini + 1.28″ round GC9A01 (240×240)**:
sonar-style circular radar showing live aircraft around a configured lat/lon,
data from the free **adsb.fi** REST API (`https://opendata.adsb.fi/api/v3/lat/…/lon/…/dist/…`),
polled every 3–5 s. Optional major-airport runway overlay from an embedded
OurAirports-derived database. WiFiManager captive portal for setup; NVS for
location/units/range persistence; BOOT button cycles range presets.

Question posed: can this be ported as an app on our multi-app CYD platform, and
what carries over vs. gets rewritten?

### Reference project profile (assessed 2026-07-10)

| Aspect | Reference | Notes |
|---|---|---|
| MCU | ESP32-C3 (single-core RISC-V, 4 MB) | Weaker than our CYD's dual-core ESP32 |
| Display | GC9A01 round 240×240, LovyanGFX | Full-frame redraw each update |
| Code size | ~2.4 kLOC logic + ~140 KB generated airport DB source | `src/data/large_airports_data.cpp` |
| Fetch | Blocking `HTTPClient` **on the main loop**, with a `setPollFn()` callback hack to keep WiFiManager alive during the blocking GET | `src/services/adsb_client.cpp` |
| TLS | `WiFiClientSecure::setInsecure()` | Violates our ADR-029 |
| Parse | Whole body into Arduino `String`, then one `JsonDocument` | Two full copies of the payload on heap |
| Aircraft store | Fixed `Aircraft s_aircraft[kMaxAircraft]` array | Good — matches our fixed-capacity pattern |
| Input | Single BOOT button (tap = range preset, hold = factory reset) | We have touch |
| Config | WiFiManager portal + NVS (lat/lon, mi/km, runway toggle) | We have Settings app + SPIFFS settings.json |
| Assets | VLW smooth font (10.7 KB), airport/runway DB baked by `scripts/build_large_airports.py` | Bake pipeline concept matches our `run/bake-*` pattern |

## Goals

1. `AppId::PlaneRadar` taskbar app: circular radar, aircraft symbols + heading
   vectors + callsign/type/alt tags, range presets cycled by tap, optional runway
   overlay — visual parity with the reference where our display allows.
2. All network I/O via `dataTask` (never on loopTask), TLS pinned per ADR-029.
3. Location/units/runway config via existing Settings app + SPIFFS persistence.
4. No heap regression that threatens the Spotify TLS session or the WebRadio
   A-lite arena (no-PSRAM board — the binding constraint on everything).

## Fit assessment — verdict

**Feasible, good fit.** The app is the same shape as Weather/Stock/Teletext:
periodic HTTPS fetch → fixed-size result struct → canvas render. Nothing in it
needs PSRAM, a second display, or continuous audio-grade throughput. The two
things that made the reference project awkward on a C3 (blocking fetch on the
UI loop, captive-portal setup) are exactly what our platform already solved
(dataTask + Settings/SPIFFS). **CYD + its ESP32 stays the base hardware — no
new hardware needed.** The round 240×240 radar maps onto our 275×240 full-screen
app canvas (240×240 radar disc + 35 px side strip for range label / status /
fetch-error code).

### What ports over (concepts + math, mostly rewritten in our idioms)

- Radar geometry: equirectangular lat/lon→screen projection, range presets
  (5/10/15/25 km), ring/crosshair grid, bearing-only rim dots for out-of-ring
  aircraft, center-facing tag placement (`radar_display.cpp`, `radar_range.cpp`).
- ADS-B field handling: heading fallback chain (`true_heading`→`mag_heading`→
  `track`→`dir`), ground filtering, callsign/hex fallback, altitude tag format
  (`adsb_client.cpp` lines 98–198) — port as-is into the dataTask fetcher.
- Runway overlay + `build_large_airports.py` bake script — adopt as a
  `run/bake-airports` host-side generator per our bake pattern (golden.sha256
  determinism check like M2).

### What gets replaced by platform infrastructure

| Reference | Ours |
|---|---|
| Blocking HTTP on main loop + `setPollFn` hack | `dataTask` `enqueuePlaneRadar()` / `pollPlaneRadar()` (spinlock, fixed struct) |
| `setInsecure()` | ADR-029 root-CA pin in `dataTaskCerts.h` + `run/check-datatask-certs` + cert preflight (run/test step 0) |
| WiFiManager captive portal | Shell WiFi (wifi_creds chain) — delete entirely |
| NVS config | `settingsStorage` SPIFFS json (lat/lon, units, runways, range preset) |
| BOOT button | Touch: tap radar = cycle range; Settings > Applications for the rest |
| LovyanGFX full-frame redraw | TFT_eSPI direct draw: static grid painted once on resume, erase/redraw only aircraft symbols + tags each update (no full-frame 240×240 sprite — 115 KB @16bpp does not exist on this board) |
| VLW smooth font | Existing baked fonts |

## Design space (options + tradeoffs)

### D1 — Fetch/parse strategy (the real risk)

Busy airspace (fetch radius ≈ preset × 4/3 × 118/107 per the reference's
`fetchRadiusKm()`, ~7–37 km across presets) returns dozens of
aircraft with full v3 field sets — payloads of tens of KB. The reference holds
**two** copies (String + JsonDocument) on heap; on our board, next to the
~50 KB Spotify TLS session, that is the same class of contention that produced
the tlsYield saga.

- **(a) Reference approach (String + JsonDocument)** — simplest port; worst
  peak heap; rejected.
- **(b) Stream-parse with ArduinoJson deserialization filter** — parse straight
  off the socket stream, filter to the 15 fields we use, cap at
  `PR_MAX_AIRCRAFT` (~24) fixed-size records (~40 B each → ~1 KB result
  struct; see phase0-parse-heap for the concrete layout). Peak heap = TLS
  session + filter working set only. **Lean as originally written — see the
  Phase-0 revision below for the measured correction (chunked variant).**
- **(c) Reduce fetch radius / server-side cap** — `dist` is already the only
  server-side knob; keep it coupled to the range preset as the reference does
  (helps, but is not sufficient alone).

Lean *(original — superseded by the Phase-0 revision below)*: (b) + (c),
bracketed by `tlsYield()`/`tlsResume()` like every other dataTask fetcher
(BP-031), with Stock-style negative error codes for HTTP/parse/truncation
failures — the yield bracket, radius coupling, and error-code surface all
carry into the revision unchanged; only the parse mechanism changed.

**Phase-0 revision (2026-07-10, measured):** (b) as stated — one filtered
document for the whole response — is falsified: it scales ~410 B/aircraft and
hit 29.4 KB on a real 71-aircraft morning capture. The executed lean is
**(b′) chunked per-object filtered parse** (one aircraft at a time through the
filter into a reused ~4 KB doc): peak parse heap ~4 KB fixed, independent of
traffic. Numbers + mechanism in phase0-parse-heap Results.

### D2 — Poll cadence + lifecycle

Reference polls every 3–5 s forever. On our platform: fetch **only while
foreground** (`suspend()` stops the cycle, `resume()` repaints grid + enqueues),
default **10 s** cadence (aircraft move ~1.2 km/10 s at 250 kn — one ring
pixel-ish at 10 km preset; smoothness can come later from dead-reckoning between
polls using track+gs, an optional M4-style interpolation follow-up). 10 s also
respects adsb.fi's public 1 req/s courtesy limit with a wide margin and keeps
TLS churn low next to Spotify polling.

### D3 — Airport/runway DB

~140 KB of source ≈ ~40–60 KB of flash-resident data, global coverage. Flash is
at ~62 % — it fits, but most of it is dead weight for a stationary device.
Options: (a) embed global list as-is; (b) bake filtered by bounding box around
the configured home location (device is stationary; regenerate when location
changes — but location is runtime-configurable, so bake-time filtering fights
the Settings flow); (c) global data on **SPIFFS** loaded into a small RAM cache
for the active range. Lean: **(a) trimmed** — bake with a generous continental
bounding box (build flag), runway overlay behind a Settings toggle, and defer
(c) until flash pressure says otherwise. Open question OQ2.

### D4 — Location entry

Settings app has toggles/choices but no numeric lat/lon entry UI today.
Options: (a) SPIFFS settings.json only (edit via `run/spiffs push`) for v1;
(b) build a numeric entry widget in Settings. Lean: **(a) for v1** — this is a
dev-bench device with an established SPIFFS config workflow; (b) is a separate
Settings-app milestone if ever wanted. Default location compile-time constant
like the reference's `kDefaultRadarLat/Lon`.

## Phase 0 — host-first exploration (teletext pattern, before any firmware)

Precedent: **M-TELETEXT** was fully de-risked on-host before a line of firmware
existed — API reverse-engineered, control codes decoded, and
`preview_teletext.py` iterated the entire canvas layout with live navigation;
firmware implementation then started with the parse policy and layout already
frozen. Same play here. **R2 (API availability/rate limiting) and R1's
parse-heap term are fully explorable off-DUT.** R1's other term — coexistence
with the live Spotify TLS session — stays DUT-side by design (exit criterion
4's 30-min soak); phase 0 bounds the parse contribution so that soak tests one
variable, not two.

Detailed sub-design docs (one per workstream):
[phase0-api-probe](M-PLANERADAR/phase0-api-probe.md) ·
[phase0-parse-heap](M-PLANERADAR/phase0-parse-heap.md) ·
[phase0-preview-ui](M-PLANERADAR/phase0-preview-ui.md) ·
[phase0-airport-db](M-PLANERADAR/phase0-airport-db.md)

1. **API probe (R2, feeds D1/D2)** — host script (venv, `requests`) polling
   live adsb.fi v3 across the range presets and representative airspaces:
   configured home location, a Schiphol-adjacent worst case (busy TMA), and a
   rural control. Record per-response payload bytes, aircraft counts, and a
   field census (how often `true_heading`/`mag_heading`/`track`/`dir`/`t`/
   `flight` are actually present — validates the fallback chain). Run a
   multi-hour cadence soak to characterise rate limiting, error modes, and
   TASK-284-style truncation behaviour before we commit to the 10 s cadence.
2. **Fixture capture** — check representative responses (busy / sparse / empty
   / malformed-truncated) into a fixtures dir. These serve the preview tool
   now and become the VE synthetic-injection corpus (`dbgSet`) later — one
   artefact, two consumers.
3. **Heap bound with real numbers (R1/D1)** — ArduinoJson is header-only and
   compiles on host: prototype the option-(b) filtered stream parse against
   the captured worst-case fixtures, measure filter working set, and validate
   the ≤ `PR_MAX_AIRCRAFT` truncation policy (which aircraft to keep when the
   feed exceeds the cap — nearest-first needs distance computed during parse).
   Output: measured peak-heap figure for D1(b) vs D1(a), settling the lean
   with data instead of estimate.
4. **UI PoC** — `app/tools/preview_planeradar.py` on `preview_common.py`
   (M-PREVIEW-FRAMEWORK): full 275×240 canvas + taskbar at 1×/2×/3× zoom,
   replaying fixtures with optional live polling. Iterate OQ4 (side strip vs
   on-disc bezel), tag-placement collision handling, range-preset feel, and
   runway-overlay density — all the judgement calls that are expensive on a
   flash-cycle loop and free in pygame.
5. **Airport DB trial bake (D3/R3, answers OQ2)** — run
   `build_large_airports.py` variants on host (global vs continental bounding
   boxes), measure generated array sizes → real flash delta before deciding.
6. **Cert chain probe (OQ1)** — `openssl s_client` against
   `opendata.adsb.fi:443`, decide single-root vs bundle per ADR-029 before the
   `dataTaskCerts.h` entry is written.

**Phase-0 exit:** D1/D3 leans confirmed with measured numbers, fixtures +
preview tool committed, OQ1/OQ2/OQ4 closed. Only then does firmware work start
— at which point it is transcription, not exploration.

## Platform optimizations to apply (the checklist the reference lacks)

1. **dataTask fetcher** — new `FetchType`, fixed `PlaneRadarResult` struct,
   `pollPlaneRadar()` spinlock copy-out; no String on loopTask (ADR-029 family).
2. **tlsYield/tlsResume** around the fetch (BP-031; NEW-APP-CHECKLIST §2).
3. **Root-CA pin** for `opendata.adsb.fi` + `run/check-datatask-certs` row +
   cert preflight coverage. Verify the served chain first (LE vs multi-root —
   CoinGecko/Yahoo both turned out to need two-root bundles).
4. **`hasPendingAsync()` + cmdTap busy propagation** (checklist §1/§4) — tap
   cycles range and re-enqueues a fetch, so this applies from day one.
5. **`dbgGet`/`dbgSet`** — `prAircraftCount`, `prLastHttp`, `prRange`,
   injectable synthetic aircraft list for VE render tests without live traffic
   (pattern: TASK-276 injected-state lesson — isolate from auto-refresh).
6. **Error-code surface** — Stock-style `-9x` codes rendered in the side
   strip. Must include a distinct code for HTTP 429 with skip-don't-retry
   backoff: the phase-0 limit probe measured ~33 % 429s at the nominal
   1 req/s courtesy limit (zero at the 10 s ship cadence, but the code path
   must exist).
7. **Bake pipeline** — `run/bake-airports` + golden.sha256 determinism gate.
8. **Suspend/resume fetch gating** — no background polling (Weather precedent).
9. **Taskbar icon** — bake `planeradar.png`/`_active.png`; `static_assert`
   catches omission (checklist §6).
10. **Preview tool** — `app/tools/preview_planeradar.py` on `preview_common.py`
    with canned adsb.fi JSON fixtures, so layout iterates host-side.
11. **`cross_feature_matrix.yaml` entries** (NEW-APP-CHECKLIST §5) — one per
    cross-cutting feature the app touches (touch-004, tls-yield,
    app-interface-001, …), added when the firmware feature lands.

## Requirements summary

- CYD 275×240 canvas; radar disc 240×240; touch tap = range cycle.
- adsb.fi v3 fetch via dataTask, pinned TLS, 10 s foreground-only cadence,
  ≤ ~24 aircraft, filtered stream parse.
- Config: lat/lon + units + runway toggle + range persist via settingsStorage.
- No regression on: heap floor during Spotify playback, WebRadio arena churn,
  taskbar scroll cycle (new visible app shifts slot count — re-run taskbar suite;
  LL-085 class).

## Challenges / risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Payload heap spike vs Spotify TLS coexistence | D1 lean (filtered stream parse, fixed structs); soak with `run/stress`-style multi-app fetch test |
| R2 | adsb.fi availability / rate limiting (free, best-effort; mirror-truncation behaviour like TASK-284 unknown) | Error codes + stale-data age indicator (M-DRIFT pattern); no retry storm — single in-flight fetch |
| R3 | Flash growth (airport DB + new app + icon) | D3 trimmed bake; watch `run/check` size output |
| R4 | Render cost of 714-line reference renderer done naively (full repaint) | Static-grid-once + symbol erase/redraw; 10 s cadence makes per-update cost trivial |
| R5 | Taskbar slot-count shift (11th visible app) | NEW-APP-CHECKLIST §6 + taskbar full-cycle VE test |
| R6 | cert chain rot on a hobbyist API host | preflight (warn-only) already runs as run/test step 0 |

## Open questions

- **OQ1**: adsb.fi actual root CA chain + stability — verify live chain before
  pinning (single root or bundle?).
- **OQ2**: airport DB bounding box vs global embed — measure real flash delta
  from a trial bake first.
- **OQ3**: dead-reckoning interpolation between polls (M4 pattern) — v1 or
  follow-up? (Lean: follow-up milestone, keep v1 static between polls.)
- **OQ4**: show the device's own location label / N-S-E-W bezel letters in the
  35 px side strip vs on-disc as reference does — preview-tool question.

## Exit criteria (draft — VE to challenge)

1. Live aircraft render within one poll of app entry, DUT on bench WiFi.
2. Range tap cycles 5→10→15→25 km, persists across reboot.
3. Fetch error → side-strip error code, app stays responsive, recovers on next poll.
4. 30-min foreground soak alongside Spotify playback: zero reboots, heap floor
   within agreed budget of pre-app baseline.
5. Taskbar full-cycle scroll test passes with the new slot.
6. Synthetic-injection render test (dbgSet aircraft list) passes without network.
