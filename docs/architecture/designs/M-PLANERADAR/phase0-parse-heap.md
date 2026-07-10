# Design — M-PLANERADAR Phase 0: host parse trial + heap bound

> Owner: Architect
> Status: draft — designer-review PASS 2026-07-10; executed (see Results)
> Date: 2026-07-10
> Parent: [M-PLANERADAR-plane-radar-app.md](../M-PLANERADAR-plane-radar-app.md)
> Closes: R1 parse-heap term (coexistence term → parent exit criterion 4) — settles D1 lean with measured numbers
> Depends: phase0-api-probe (fixtures, worst-case payload)

## Context / pain points

The reference project holds the ADS-B response **twice** on heap: the full
body in an Arduino `String`, then a complete `JsonDocument`. On our board that
peak lands next to the ~50 KB Spotify TLS session — the exact contention class
behind the tlsYield saga (five fixed layers; we are not adding a sixth).
Parent-doc D1 lean is a filtered stream parse into fixed-size records, but the
lean is currently an estimate. This trial replaces the estimate with a number.

**Version parity matters:** the device firmware pins **ArduinoJson 6.21.3**
(`platformio.ini` `bblanchon/ArduinoJson@^6.21.3`); the reference project uses
v7. The v6 API differs (`DynamicJsonDocument(capacity)`, capacity is
caller-chosen, filter via `DeserializationOption::Filter`). The trial must run
against **6.21.3** — a v7 measurement would be a number about the wrong
library.

## Goals

1. Measured peak heap for:
   - **D1(a)** reference approach — String body + full document parse;
   - **D1(b)** filtered stream parse — no body buffer, filter document +
     fixed output records only.
   Both against the worst-case fixture (`busy_33km.json`).
2. Filter-document capacity: find the minimum `DynamicJsonDocument` capacity
   that parses the worst case without `NoMemory`, with margin policy.
3. Truncation policy validated: when the feed exceeds `PR_MAX_AIRCRAFT`, which
   aircraft are kept, and does the policy behave against real data.
4. A go/no-go statement for D1(b) feeding the parent doc and eventual ADR.

## Design

*(Format note: the primary design space for fetch/parse — D1 (a)/(b)/(c) with
tradeoffs and lean — is enumerated in the parent doc; this trial executes the
comparison. The one design space local to this doc is the truncation policy
below, with its lean marked inline.)*

### Harness

`app/tools/host/pr_parse_trial/` — single C++17 `main.cpp` + `Makefile`
(g++, no PlatformIO). ArduinoJson is header-only: vendor the single-header
`ArduinoJson-v6.21.3.h` into the trial dir (pinned copy, sha256 noted in the
Makefile comment) rather than symlink into `.pio` (keeps the trial buildable
on a clean checkout).

Arduino-API shims: ArduinoJson itself is platform-clean; the D1(a) leg needs a
minimal `String` stand-in — use `std::string` and note that Arduino `String`
realloc behaviour on-device is *worse* (fragmentation), so the host number is
a lower bound for (a).

### Instrumentation

Two complementary measurements (review finding: a custom allocator alone
**cannot** answer Goals 1–2 — v6's `BasicJsonDocument` grabs its pool **once**
at the requested capacity, so an allocator hook only sees the pool grab, never
how much of it the parse used):

- **Actual usage**: `doc.memoryUsage()` after each successful parse — the v6
  API for bytes consumed inside the pool. This is the "measured peak heap"
  number for Goal 1 (legA additionally adds the body-buffer size).
- **Minimum viable capacity** (Goal 2): binary-search the constructor capacity
  for the smallest value that parses the worst-case fixture without
  `NoMemory`.
- **v6 custom allocator** (`BasicJsonDocument<TrackingAllocator>`): retained
  only to verify the single-pool-grab assumption holds (alloc count == 1 per
  parse) and to account total heap traffic.
- Stream input: a `Reader` class over the fixture file that yields bytes in
  512-byte chunks (mimics `WiFiClientSecure` reads) so the parse is a true
  incremental-stream parse, not a memory-buffer parse.
- Report: per-leg table — capacity requested, `memoryUsage()`, result
  (ok / NoMemory / TooDeep), aircraft parsed, aircraft kept.

### Filter document (D1(b))

```cpp
StaticJsonDocument<512> filter;
// definitive 15-field set — MUST match phase0-api-probe Goal 2's census list:
// lat, lon, dst, dir, true_heading, mag_heading, track, gs, tas, ias,
// alt_baro, alt_geom, flight, hex, t
for (const char* k : {...}) filter["ac"][0][k] = true;
```

`tas`/`ias` are included so the reference's `pickGroundSpeed()` gs→tas→ias
fallback (ported as-is per the parent doc) still works on-device; `dst` is the
server-computed distance (NM) used as the truncation sort key. Everything else
never allocates.

**Post-execution note:** the `filter["ac"][0][k]` whole-response shape shown
above is the leg-B mechanism, which Results falsified. The winning (b′)
per-object parse uses the same 15 fields but a **flat** filter
(`filter[k] = true`, no `ac[0]` wrapper) applied to one aircraft object at a
time — transcribe that shape into the firmware, not this snippet.

### Output record (drives the result-struct size in the firmware design)

```cpp
struct PrAircraft {           // packed target ~40 B
    float   lat, lon;         // 8
    float   distNm;           // 4  server 'dst' — truncation sort key
    int16_t noseDeg, trackDeg;// 4  (0.1° not needed; whole degrees)
    int16_t gsKnots;          // 2
    int32_t altFt;            // 4  (INT32_MIN = "GND", INT32_MAX = unknown)
    char    callsign[9];      // 9
    char    type[5];          // 5
    // + pad → 40 B
};
static constexpr uint8_t PR_MAX_AIRCRAFT = 24;   // 24 × 40 B ≈ 1 KB result payload
```

Exact layout is a firmware-design decision; the trial validates that this
capacity class (~1 KB fixed) holds the kept set.

### Design space — truncation policy when cap exceeded (options + tradeoffs)

Options:

- **(i) first-N as served** — trivial; server order is unspecified → arbitrary
  drops, possibly the nearest aircraft. Rejected.
- **(ii) nearest-first, replace-farthest during parse** — keep a fixed array;
  sort key = server-computed `dst` (100 % present per the field census in
  phase0-api-probe Results), falling back to
  client equirectangular range only if `dst` is ever absent; if full, replace
  the current farthest kept entry when the new one is nearer. O(N·cap) worst
  case, N ≤ ~200, cap 24 — trivial CPU. **Lean.**
- **(iii) two-pass** — parse all, sort, take N: needs the full set in memory,
  defeats the point. Rejected.

Trial validates (ii) against an oracle: Python reference implementation over
the same fixture must select the identical set.

### What this trial does NOT measure

Device-side TLS buffer costs, mbedTLS fragmentation interaction, and real
`WiFiClientSecure` chunking cadence — those stay DUT-side (the parent doc's
30-min coexistence soak, exit criterion 4). The trial bounds the *parse* term
only; that is the term D1 varies on.

## Open questions

- v6 filter + stream parse keeps the *filtered-out* branches unbuffered, but
  ArduinoJson still tokenises through them — confirm no hidden allocation
  spike on long skipped arrays. The instrument for this is the gap between
  the binary-searched minimum viable capacity and post-parse
  `memoryUsage()` (transient working set = min capacity − settled usage);
  the allocator trace cannot see intra-pool behaviour.
- Is whole-degree heading precision acceptable at 240 px disc? (Renderer
  question; 1° ≈ sub-pixel at that radius, expected yes — preview tool
  confirms visually.)

## Exit criteria

1. Table: D1(a) vs D1(b) peak heap bytes on `busy_33km.json`, plus
   `home_13km.json` for the typical case.
2. Minimum viable filter-doc capacity + chosen margin (e.g. min × 1.5) stated.
3. Truncation policy (ii) matches the Python oracle on busy + synthetic
   fixtures (including `nofields.json` — missing-field records rank sanely).
4. Parse of `truncated.json` fails *cleanly* (error return, no partial-record
   garbage) — feeds the firmware error-code design.
5. Go/no-go statement for D1(b) with the measured number vs the parent doc's
   heap-budget expectation, written into Results and mirrored to the parent.

## Results

> Executed 2026-07-10 (podman `gcc:13` container — host has no C++ toolchain;
> vendored `ArduinoJson-v6.21.3.h` sha256 `488c9fa0…`). Worst-case fixture =
> morning-wave Schiphol capture: **34 921 B body, 71 aircraft** (27 airborne
> with lat/lon).

### Peak-heap table (busy_33km, cap 24)

| Leg | Approach | Peak | Notes |
|---|---|---|---|
| A | reference: buffered body + full parse | **121.2 KB** (35 KB body + 86 KB `memoryUsage`; pool grab 209 KB) | not viable on device, ever |
| B | filtered whole-response doc (original D1(b)) | **29.4 KB** `memoryUsage` (min viable capacity 29 353 B) | scales ~410 B/aircraft — collides with the ~50 KB TLS session on a busy day |
| C | **chunked per-object filtered parse, reused doc** | **597 B** peak per object (4 KB doc cap) | count-independent; typical objects 230–600 B |

### Lean revision (feeds the parent doc + eventual ADR)

**D1(b) as originally specced is falsified for busy airspace; the lean is now
D1(b′): leg C** — scan the stream to the `ac` array, `deserializeJson` one
aircraft object at a time through the 15-field filter into a reused ~4 KB
`DynamicJsonDocument`, fill a `PrAircraft` record, repeat. Peak parse heap
~4 KB fixed + 1 KB result records, regardless of traffic. **Go** for the
firmware fetcher on these numbers.

### Other exit criteria

- Truncation policy (ii): `KEPT` set == Python oracle on `busy_33km` (24/24)
  and `nofields` — nearest-first by server `dst` validated (criterion 3 ✅).
- `truncated.json`: legs B and C both fail cleanly with `IncompleteInput`,
  no partial-record garbage (criterion 4 ✅); leg C additionally reports the
  object index where the stream died.
- Filter-doc (leg B) minimum capacity: 29 353 B on the worst case — recorded
  for completeness, moot under the (b′) lean (criterion 2 ✅ by supersession).
- Single-pool-grab assumption confirmed: `allocs=1` for legs B/C (leg A shows
  `allocs=2` from the capacity-doubling sweep).
- `home_13km` typical case — re-captured **daytime** (10 605 B wire /
  10 557 B committed compact fixture — the trial input, 23 records,
  2 airborne with lat/lon; matches the soak's p50 9.4 KB) after review round 3
  flagged the original night capture as unrepresentative: leg A
  **36.6 KB** peak total, leg B **9.0 KB** (min capacity 9 033 B), leg C
  **597 B** — the same ordering and the same count-independence at typical
  traffic (criterion 1 ✅ for both fixtures). Oracle OK. `empty`/`ground_mix`/
  `nofields` all behave (0 kept for ground-only input; hex/`dir` fallbacks
  fill field-poor records sanely).

Residual open item: none blocking — OQ on skipped-array transient resolved by
observation (leg C per-object usage never exceeded 597 B even while the parser
tokenised through 71 objects' unfiltered fields).
