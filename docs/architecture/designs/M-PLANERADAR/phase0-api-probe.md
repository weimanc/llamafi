# Design — M-PLANERADAR Phase 0: adsb.fi API probe + cert chain

> Owner: Architect
> Status: draft — designer-review PASS 2026-07-10; execution partially complete (see Results)
> Date: 2026-07-10
> Parent: [M-PLANERADAR-plane-radar-app.md](../M-PLANERADAR-plane-radar-app.md)
> Closes: R2 (API availability/rate limiting), OQ1 (cert chain); feeds D1 (parse), D2 (cadence)

## Context / pain points

Everything downstream — parse strategy, heap budget, poll cadence, error-code
taxonomy — depends on facts about adsb.fi we currently only have from the
reference project: `https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}`
(dist in **nautical miles**, per `adsb_client.cpp`), public courtesy limit
**1 req/s** (per the `kAdsbFetchIntervalMs` comment in the reference's
`config.h`), JSON body with an `ac` array. Payload size in busy airspace is the single number that decides
D1; API failure modes decide the error-code surface; the served TLS chain
decides the `dataTaskCerts.h` entry. All measurable from the host, none need
the DUT.

Precedent for the risk: TASK-284 (radio-browser mirror truncation that came
and went, degraded under repeated fetches). We assume nothing about adsb.fi's
behaviour under sustained polling until measured.

## Goals

1. Payload-size and aircraft-count distributions per range preset per airspace
   density class.
2. Field census: presence rates of every field the app reads
   (`lat`, `lon`, `dst`, `dir`, `true_heading`, `mag_heading`, `track`, `gs`,
   `tas`, `ias`, `alt_baro`, `alt_geom`, `flight`, `hex`, `t`) — validates the
   reference's fallback chains against reality. `dst`/`dir` (server-computed
   distance NM / bearing) are of special interest: if reliably present they
   let the truncation policy sort on `dst` with no client-side math.
3. Availability/rate-limit taxonomy under sustained polling at the cadence we
   intend to ship (10 s), plus a bounded characterisation of the 1 req/s limit.
4. Fixture corpus for the parse trial (phase0-parse-heap) and preview tool
   (phase0-preview-ui), later the VE injection corpus.
5. TLS chain recorded; root-pin decision made (OQ1).

## Design space (options + tradeoffs)

- **Ad-hoc curl/jq session** — fastest to start, leaves nothing behind;
  rejected: results must be reproducible and the fetch function is reused by
  the preview tool and the fixtures must be regenerable.
- **One multi-mode probe tool** (survey/soak/census/capture/limit-probe) —
  slightly more upfront work, single source of truth for the URL/radius
  formula, JSONL logs re-analysable. **Lean.**
- Soak cadence: 10 s = the cadence we intend to ship (D2) — measure the thing
  we will run, not an artificial fast poll that would trip the courtesy limit.

## Design

### Tool

`app/tools/pr_adsb_probe.py` — project venv (`~/proj/esp/venv`), `requests`.
Modes:

- `--survey` — one fetch per (site × preset), print summary table.
- `--soak --hours N --interval 10` — sustained polling, JSONL log per response:
  timestamp, HTTP code, latency ms, body bytes, `ac` count, parse ok/fail,
  truncation flag (body ends mid-JSON — the TASK-284 signature).
- `--census` — accumulate field-presence counts across N fetches.
- `--capture <name>` — save raw body to
  `app/tools/fixtures/planeradar/<name>.json` (pretty-printed copy alongside
  for review).
- `--limit-probe` — **bounded** burst: ramp to 1 req/s for ≤ 60 s, record the
  response-code transition (429? 5xx? silent truncation?), then stop. One run,
  not repeated — we characterise the limit, we don't lean on it.

### Probe matrix

| Site | Lat/Lon | Why |
|---|---|---|
| Home (Amsterdam area — reference default 52.3676, 4.9041) | config default | The location the device will actually run at |
| Schiphol TMA (52.3086, 4.7639) | worst case | Busiest airspace within reach — upper-bounds payload |
| Rural NL/DE (52.8, 6.9) | sparse control | Lower bound; empty-`ac` handling |

× fetch radii for the four presets. Fetch radius follows the reference's
`radar_range.cpp::fetchRadiusKm()`: outer_km × (screen_r_px / kGridOuterRadius)
= (preset × 4/3) × (118/107) ≈ preset × 1.47 — i.e. **7.4 / 14.7 / 22.1 /
36.8 km** → 4.0 / 7.9 / 11.9 / 19.9 NM. (Earlier draft omitted the ×118/107
screen-edge scale and understated the worst case by ~21 % in fetch area —
review finding, corrected.)

### Soak plan

≥ 6 h at 10 s interval on the home site (2 160 requests), one run; repeat once
at a different time of day (evening air-traffic peak). A small stdlib-only
analysis script over the JSONL produces: success rate, latency percentiles,
size percentiles (p50/p95/max), error-code histogram, truncation count.

### Fixture set (minimum)

| Fixture | Content |
|---|---|
| `busy_33km.json` | Schiphol site, 25 km preset — worst-case size/count |
| `home_13km.json` | Home site, default preset — the typical frame |
| `sparse.json` | Rural site — few aircraft |
| `empty.json` | Response with empty/absent `ac` |
| `ground_mix.json` | Contains `alt_baro:"ground"` entries (filter test) |
| `truncated.json` | Synthetic: `busy_33km` cut mid-object (error-path test) |
| `nofields.json` | Synthetic: aircraft missing heading/speed/callsign fields (fallback test) |

Synthetic fixtures are derived from captured ones by a documented edit, noted
in a `fixtures/planeradar/README.md` manifest (source, date, edit applied).

### Cert chain probe (OQ1)

```sh
openssl s_client -connect opendata.adsb.fi:443 -servername opendata.adsb.fi -showcerts </dev/null
```

Record the full served chain in this doc's Results section. Decision per
ADR-029: pin the **root**; if the host sits behind a multi-CA CDN
(the CoinGecko/Yahoo lesson — both needed two-root bundles), bundle every
observed root. Re-run the probe on a second day before deciding — single
observation of a CDN chain is not enough (TASK-298 lesson).

## Open questions

- Does adsb.fi vary payload shape across its `/v3/` vs legacy endpoints? (Only
  if v3 shows problems — otherwise out of scope.)
- Does the API honour `Accept-Encoding: gzip`, and does device-side HTTPClient
  benefit? Record content-encoding in the survey; decision belongs to the
  firmware fetcher design, not phase 0.

## Exit criteria

1. Survey table: (3 sites × 4 presets) → body bytes, `ac` count. Worst case
   identified and captured as `busy_33km.json`.
2. Field-census table over ≥ 100 aircraft records; fallback chains confirmed
   or corrected in the parent doc.
3. Two soak runs logged; success rate, size/latency percentiles, error
   taxonomy written into Results. Truncation behaviour: observed or ruled
   not-observed.
4. `--limit-probe` result recorded (what the API does at/over 1 req/s).
5. Fixture corpus (≥ 7 files) + manifest committed.
6. Cert chain recorded from two observations on different days; pin decision
   (single root vs bundle) written and ready for `dataTaskCerts.h`.

## Results

> Execution started 2026-07-10 (night). Partial — soak + daytime worst-case
> capture still running; doc moves to `implemented` when all exit criteria hold.

### Survey (2026-07-10 ~01:55 CEST — night, low traffic; NOT worst case)

All 12 site×preset cells returned HTTP 200, 87–235 ms. Max observed:
schiphol/25 km → 3 090 B, 7 aircraft. Empty responses are 101 B on the wire
(`ac:[]` + metadata; the committed `empty.json` fixture is 88 B because
fixtures are re-serialized compact — see the manifest's byte-size note). Top-level keys: `ac, msg, now, total, ctime, ptime`. **Caveat:**
run predates the ×118/107 radius fix (radii ~10 % short); nighttime numbers
are indicative only — daytime peak comes from the hunt-max run.

### Field census (123 aircraft records, 29 fetches, schiphol, night)

- 100 %: `hex, lat, lon, dst, dir, alt_baro` (+ `type, category, nic, rc,
  seen*, sil*, mlat, tisb, messages, rssi` — unused by us)
- `flight` 94.3 % (hex fallback needed), `gs`/`track` 76.4 %,
  `r`/`t` 55.3 %, `true_heading`/`mag_heading`/`tas`/`ias`/`alt_geom` 31.7 %
- `alt_baro` is **mixed-type**: str `"ground"` (84/123) or int ft (39/123)
- **`dst` (NM) + `dir` are server-computed and 100 % present** → truncation
  policy sorts on `dst`; client-side range math only as a guard
  (phase0-parse-heap policy (ii) updated accordingly)
- Heading fallback chain validated: `true_heading` alone would miss ~68 % of
  records; `track` covers most; `dir` covers all as last resort

### Rate limit (bounded 60 s probe @ 1 req/s, rural site)

**HTTP 429 on 20/60 requests (~33 %)** interleaved with 200s — the effective
limit is stricter than the nominal 1 req/s (or shared/burst-windowed).
Clean 429 status, empty body, no ban afterward. Consequences: 10 s cadence has
wide margin (soak will confirm 0×429); firmware needs a distinct 429 error
code + skip-don't-retry backoff.

### TLS chain (observation 1 of 2, 2026-07-10)

`adsb.fi` leaf ← **Google Trust Services WE1** ← **GTS Root R4**
(← cross-sign: GlobalSign Root CA). Same CA family as the CoinGecko TASK-298
lesson; GTS Root R4 PEM already exists in `dataTaskCerts.h`'s CoinGecko
bundle. Pin lean: GTS roots bundle (R4 + likely R1), decision after the
second-day observation per exit criterion 6.

### Fixtures

7 committed (`busy_33km, home_13km, sparse, empty, ground_mix, truncated,
nofields`) + manifest. `busy_33km` is being continuously upgraded by a 7 h
`--hunt-max` run through the morning Schiphol wave; synthetic derivatives to
be re-derived after it settles. `home_13km` re-captured **daytime at the
corrected 7.9 NM radius** (10 605 B, 23 records — matches soak p50) after
review round 3 flagged the night capture as unrepresentative of the typical
frame.

### Soak checkpoint (4.3 h of 6 h, home site, 10 s cadence, corrected radius)

**1 542 / 1 542 HTTP 200 — zero 429, zero transport errors, zero truncations.**
Body bytes p50 9 416, max 18 547 (43 aircraft) as the morning wave built.
Latency p50 140 ms, max 716 ms. The 10 s cadence is comfortably inside the
rate limit (contrast the 1 req/s probe's 33 % 429 rate).

### Daytime worst case (hunt-max through the morning Schiphol wave)

`busy_33km.json` upgraded to **34 921 B / 71 aircraft** (25 km preset,
19.9 NM). This is the payload class the parse trial ran against.

### Still pending

Soak completion + evening-peak repeat, second cert observation (different
day), synthetic fixture re-derivation from the final busy capture.
