# Design — M-PR-LOCATIONS: PlaneRadar location presets + geocode lookup

> Owner: Architect
> Status: draft — proposed 2026-07-13; **Q1–Q7 resolved by human same day**
> (see Resolved questions) — ready for PM breakdown; supersedes the D4 (v1)
> "compile-time default, no numeric-entry UI" location lean
> (`settingsStorage.h:106`, M-PLANERADAR design D4) and the "strip is
> display-only" phase-0 decision (`planeRadarApp.h:209`, phase0-preview-ui.md)
> Date: 2026-07-13
> Deps: M-PLANERADAR (done), dataTask, ADR-029, KeyboardWidget
> (M-SETTINGS-001), Settings AppsSection
> Feeds: likely 1 small ADR (geocode provider + pin reuse); M-CERT-ERRCODE
> (companion — new pinned host should fail loudly)

## Context

PlaneRadar's location (`g_settings.prLat/prLon`) is a compile-time default,
editable only via `run/spiffs push` — deliberate v1 scope (D4). Human
direction 2026-07-13: grow this into **named location presets**:

- A few location slots, each: `label` + `lat/lon`.
- Slots are created/edited in Settings → Applications → PlaneRadar via a
  **country + postcode** geocode lookup (no numeric lat/lon entry).
- Inside the radar app, the side strip lists the labels; tapping one jumps
  the radar to that location.

This is deliberately **PlaneRadar-scoped**. A shared "device home location"
(weather's hardcoded coords, time-zone city, webradio country) is a separate
future discussion; nothing here should preclude slot 0 later being aliased
as the device home, but we don't design that now.

## Geocode provider decision (probed live, 2026-07-13)

Candidates tested against NL + UK postcodes (the two formats we care about
first):

| Input | open-meteo geocoding | Nominatim | zippopotam.us |
|---|---|---|---|
| UK full (`SW1A 1AA`) | ✗ | ✓ street-level | ✗ (outward only) |
| UK outward (`M1`, `EH1`) | ✗ | ✗ | ✓ |
| NL full (`2513AA`) | ✗ | ✓ street-level | ✗ |
| NL PC4 (`2513`) | ✓ city centroid | ✗ | ✓ |

**Pick: Nominatim, input rule "full postcode".** One consistent UX rule
across countries, street-level precision (right for 5 km range rings), and
graceful structured fallback (`city=` / free-text) if a postcode misses.
open-meteo's geocoder is effectively blind to UK postcodes; zippopotam is a
hobby-run single point of failure covering the formats Nominatim doesn't
need.

Endpoint (structured search, one result, no address breakdown):

```
https://nominatim.openstreetmap.org/search?country={CC}&postalcode={ZIP}&format=jsonv2&limit=1
```

Operational facts, verified:

- **TLS**: chain is `leaf ← YR1 ← ISRG Root YR ←(cross-sign)← ISRG Root X1`.
  Verified OK against the exact `OPEN_METEO_ROOT_CA` PEM already in
  `dataTaskCerts.h` — **no new root cert**, add a `NOMINATIM_ROOT_CA` alias
  (radio-browser pattern). MUST-comment the cross-sign dependency: if OSM
  drops the cross-signed `Root YR` from its served chain, verification
  against X1 alone breaks (-9984 / M-CERT-ERRCODE's -120); remediation is a
  two-root bundle, coingecko TASK-298 pattern.
- **Usage policy**: custom `User-Agent` is mandatory (default UA gets
  403'd) — `http.setUserAgent(...)` with a project-identifying string; max
  1 req/s. Lookups are one-shot on explicit user action in Settings, so
  policy compliance is structural. No API key (matters for GitHub publish).
- Response with `limit=1` is one small JSON array object (~0.5 KB);
  `lat`/`lon` arrive as **strings**, `display_name` gives human-readable
  confirmation text for the edit UI.

## Settings storage

```cpp
// settingsStorage.h
static constexpr uint8_t PR_NUM_LOCS  = 4;   // Q1 resolved: 4
static constexpr uint8_t PR_LABEL_MAX = 5;   // chars, excl. NUL — strip-width bound; Q2 resolved: 5

struct PrLocation {
    char  label[PR_LABEL_MAX + 1];  // "" = empty slot
    float lat, lon;
};

// in AppSettings, PlaneRadar block:
PrLocation prLocs[PR_NUM_LOCS];
uint8_t    prActiveLoc;             // index into prLocs; slot 0 always defined
```

Migration: on load, if `prLocs` absent from settings.json (pre-upgrade file),
seed `prLocs[0] = { "HOME", prLat, prLon }` from the existing fields and
`prActiveLoc = 0`. Keep `prLat/prLon` as the *written-through mirror* of the
active slot rather than deleting them — every existing consumer
(`planeRadarApp.h:341,418-419`, `appsSection.h:348`, `run/spiffs push`
dev-edit workflow, m-planeradar-dut.md tests) keeps working unmodified, and
a location switch is then just "copy slot → prLat/prLon → save + repaint".
Cheap, and avoids touching the projection math call sites.

Label charset: A–Z 0–9 (KeyboardWidget `UpperAlpha` mode, maxLen 5 — same
mechanism as the stock-ticker editor, `appsSection.h:191`).

## Geocode fetch — dataTask one-shot

New on-demand fetcher, same shape as the stock-chart request path:

```cpp
// dataTask.h
struct GeocodeResult {
    bool  ok;
    int   errorCode;        // 0 ok; HTTP status; HTTPClient negatives; -100; -120 (M-CERT-ERRCODE)
    float lat, lon;
    char  display[48];      // truncated display_name for the confirm UI
};
void enqueueGeocode(const char* countryCC, const char* postcode);
bool pollGeocode(GeocodeResult& out);
```

- URL-encode the postcode (UK ones contain a space).
- `tlsYield()` before handshake per BP-031, `openHttps()` with
  `NOMINATIM_ROOT_CA`, plus `http.setUserAgent(...)` — note `openHttps()`
  takes no header hook today; either add an optional UA parameter or set it
  on the HTTPClient before the call (decide at implementation, trivial).
- Empty JSON array (`[]`, postcode not found) → `ok=false` with a dedicated
  small code (propose `-96 GEOCODE_NO_MATCH`, next to the stock parse band)
  so the edit UI can say "not found" vs "network error".
- Parse buffer: fixed ~1 KB `StaticJsonDocument` — response is bounded by
  `limit=1`.

Country input: two-letter ISO code via keyboard (`UpperAlpha`, maxLen 2).
A country *picker* (scroll list à la cities.h) is nicer but is pure UI
polish; v1 ships with the 2-char code, revisit in Q5.

## Settings UI — Settings → Applications → PlaneRadar

Existing rows (Range / Units / Runways / Tag rule / Stale style / grey
lat-lon row, `appsSection.h:332-357`) stay. Changes:

- The grey read-only `%.3f,%.3f` row is replaced by a **Locations** row
  showing the active slot's label; tapping it opens a **location sub-view**
  (same in-section sub-view pattern as TimeSection's CityPicker,
  `timeSection.h:12`).
- Location sub-view: 4 slot rows (`label  lat,lon` or `— empty —`) + active
  marker. Tap a slot → slot editor.
- Slot editor flow (keyboard-driven, one field at a time, mirroring the
  WiFi-password and stock-ticker flows):
  1. Label (UpperAlpha, ≤5) — prefilled when editing an existing slot.
  2. Coordinate source choice (Q4 resolved): **Lookup** (default) or
     **Manual**.
  3. Lookup path: Country (UpperAlpha, ≤2, prefilled from previous entry) →
     Postcode (Full mode, ≤10) → `enqueueGeocode`; spinner row while
     pending (M-DATATASK-PROGRESS pattern); on result show `display_name` +
     coords with **Save** / **Retry** / **Cancel**. On failure the decoded
     error (`httpErr()` / `-96 GEOCODE_NO_MATCH`) shows with the same
     Retry/Cancel — Cancel keeps prior coords.
  4. Manual path: lat then lon via keyboard (numeric entry — digits,
     `-`, `.`; add a numeric layout to KeyboardWidget if Full mode proves
     clumsy), validated to −90..90 / −180..180, then the same Save /
     Cancel confirm. First-class alternative to lookup, not just a
     failure fallback: covers offline setup and locations OSM's postcode
     data doesn't know.
  - **Delete** action on the editor screen for a non-empty slot (clears
    label → slot empty). Deleting the active slot falls back to slot 0;
    slot 0 itself is not deletable (always-defined invariant, keeps
    `prActiveLoc` trivially valid).
- Saving a slot does NOT switch to it; switching is the radar-side gesture
  only (Q6 resolved: sub-view tap = edit, single-purpose).

## Radar app — strip becomes the location switcher

Strip geometry today (`planeRadarApp.h:113-116`): RANGE y5, COUNT y43,
`N^` marker y120, AGE y193, ERR y213 — free band ≈ y55..185.

- **Remove** the static `N^` bezel marker entirely (Q3 resolved: "adds no
  value" — north-up is implicit in a fixed-orientation radar). Frees the
  whole y55..185 band contiguously; one less static to repaint.
- Render up to 4 label rows (font 1, MC_DATUM at `PR_STRIP_LABEL_X`,
  ~26 px pitch) in the freed band; empty slots render nothing. Active slot
  highlighted (inverse box or `PR_COL_STRIP_TEXT` vs dimmed — preview
  decides).
- **Touch**: `handleTouch` currently returns `STRIP_NONE` for `x >= 240`
  (display-only). New behaviour: hit-test the label rows; tap →
  `prActiveLoc = slot`, write-through to `prLat/prLon`, `saveSettings()`,
  then full `_repaintDisc()` + `_drawRunways()` + immediate
  `enqueuePlaneRadar()` (same sequence as resume — projection centre moved,
  every static is stale). Taps elsewhere in the strip stay inert.
- Label length 5 is the hard bound: 34 usable px / 6 px-per-char font-1
  glyph advance (strip W35 minus the x=240 border line).
- One-location degenerate case: single row, tap is a no-op (no flicker
  repaint on same-slot tap — guard `slot == prActiveLoc`).

Preview-first per BP-048: extend `app/tools/preview_planeradar.py` with the
label rows + active highlight and eyeball-gate the strip layout (marker
relocation, pitch, highlight style) before firmware code.

## Verification sketch (VE to own)

- T_PRL_01: slot editor round-trip on DUT — create slot via geocode (live
  Nominatim, [NETWORK] tag), save, reboot, slot persists.
- T_PRL_02: strip tap switches location — disc repaints, runways re-project,
  fetch re-enqueues at new centre (assert via `get dataq` / LOG_D URL).
- T_PRL_03: geocode failure paths — bad postcode → -96 "not found" UI; UA
  missing is not testable without code change (policy, not behaviour).
- T_PRL_04: migration — pre-upgrade settings.json (no prLocs key) → slot 0
  seeded from prLat/prLon, active 0.
- T_PRL_05: same-slot tap no-op; delete-active falls back to slot 0.
- T_PRL_06: manual lat/lon entry round-trip — out-of-range values
  (91, -200) rejected at the editor, valid pair persists and projects.
- Nominatim host added to the run/test step-0 cert preflight roster.

## Heap / budget note

No resident growth: `GeocodeResult` + parse doc live only during the
one-shot fetch on the dataTask stack (bounded ~1 KB, well under the 14 KB
stack's measured margins); `prLocs[4]` adds 4×(6+8) = 56 B to `AppSettings`.
No new task, no new persistent TLS session.

## Resolved questions (human review 2026-07-13)

- **Q1 — slot count: 4.** Readable ~26 px pitch in the freed band.
- **Q2 — label length: 5 chars** (font-1 width bound; UpperAlpha keyboard).
- **Q3 — `N^` marker: remove entirely** ("adds no value") — not relocated.
  North-up is implicit; drop the draw call at `planeRadarApp.h:481`.
- **Q4 — failure UX: Retry/Cancel, plus manual lat/lon entry as a
  first-class alternative input method** to the country+postcode lookup
  (editor offers Lookup | Manual at the coordinate-source step) — not
  merely a failure fallback. Covers offline setup and OSM postcode gaps.
- **Q5 — country input: 2-char ISO code via the existing KeyboardWidget.**
  No country picker.
- **Q6 — switching: radar-strip only in v1.** Settings sub-view tap =
  edit, single-purpose.
- **Q7 — shared home location: record only.** Radar-scoped milestone;
  slot 0 remains the natural alias target for a future device-wide
  localization widget, nothing designed now.
