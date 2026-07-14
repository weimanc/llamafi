# Design — M-PR-LOCATIONS: PlaneRadar location presets + geocode lookup

> Owner: Architect
> Status: **r2 — panel-reviewed** — proposed 2026-07-13; Q1–Q7 resolved by
> human same day (see Resolved questions); 4-reviewer panel (DEV/VE/QM/PM,
> see `M-PR-LOCATIONS-*-review.md`) unanimous PASS-with-actions 2026-07-13;
> all blockers/majors folded in 2026-07-14 (r2, this revision) — tasks filed
> TASK-315..325; supersedes the D4 (v1)
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

New on-demand fetcher. **Plumbing pattern (DEV review): the
pending-config-mux pattern** (`s_pendingCountry` / `s_pendingPrLat/Lon`,
`dataTaskStorage.cpp:667,679-682`) — NOT the stock-chart `Request.symbol[8]`
queue, whose 7-char payload can't even hold `SW1A 1AA`:
`s_pendingGeoCountry[4]` + `s_pendingGeoPostcode[12]` + seq under one
`portMUX`, drained by the dataTask loop.

```cpp
// dataTask.h
struct GeocodeResult {
    bool    ok;
    int     errorCode;    // 0 ok; HTTP status; HTTPClient negatives; -96 no-match; -100; -120 (M-CERT-ERRCODE)
    uint8_t seq;          // echo of the request sequence — see identity rule below
    float   lat, lon;
    char    display[48];  // truncated display_name for the confirm UI
};
uint8_t enqueueGeocode(const char* countryCC, const char* postcode); // returns seq
bool    pollGeocode(GeocodeResult& out);
```

- **Request identity (DEV-1, TASK-300 lesson):** every request gets a
  monotonically increasing `seq`, echoed in the result — same hardening
  `StockChartResult` got after a stale parked result landed in the wrong
  consumer. The editor stores the seq it enqueued and **ignores+discards**
  any result with a different seq (covers back-out-and-retry, cancel, and
  slot-change while a lookup is in flight — VE-PRL-5).
- **URL encoding:** UK postcodes contain a space and no `urlEncode` helper
  exists anywhere in this firmware (DEV minor) — add a minimal
  percent-encode (space + non-alnum) in the fetcher, exercised against the
  phase-0 probe's query matrix on host and re-checked on-device in
  T_PRL_01b.
- `tlsYield()` before handshake per BP-031, `openHttps()` with
  `NOMINATIM_ROOT_CA`, plus `http.setUserAgent(...)` — `openHttps()` takes
  no header hook today; either add an optional UA parameter or set it on
  the HTTPClient before the call (decide at implementation, trivial).
- Empty JSON array (`[]`, postcode not found) → `ok=false`,
  `-96 GEOCODE_NO_MATCH` (next to the stock parse band) so the edit UI can
  say "not found" vs "network error".
- Parse buffer: ~1 KB `StaticJsonDocument` **provisional — sized by the
  phase-0 probe's measured responses before freezing** (BP-001: measure,
  don't guess; QM-5).
- Attribution (QM-4): geocoding results are OSM-derived (ODbL). The
  GitHub-publish README must carry "Geocoding © OpenStreetMap
  contributors, ODbL" — add to `docs/process/github_publish_plan.md`'s
  attribution items alongside the existing license-scanner item.

Country input: two-letter ISO code via keyboard (`UpperAlpha`, maxLen 2).
A country *picker* (scroll list à la cities.h) is nicer but is pure UI
polish; v1 ships with the 2-char code, revisit in Q5.

## Settings UI — Settings → Applications → PlaneRadar

Existing rows (Range / Units / Runways / Tag rule / Stale style / grey
lat-lon row, `appsSection.h:332-357`) stay. Changes:

- The grey read-only `%.3f,%.3f` row is replaced by a **Locations** row
  showing the active slot's label; tapping it opens a **location sub-view**
  (in-section sub-view mechanism like TimeSection's CityPicker,
  `timeSection.h:12` — but note the honest sizing (DEV-4): CityPicker is a
  2-state flat list, while this editor is an explicit ~8-state machine
  (slot list → editor → source fork → lookup: country → postcode →
  pending → confirm / manual: lat → lon → confirm, plus delete). Give it
  its own state enum from the start; do not grow it out of boolean flags.
  The closest existing precedent is Stock's 3-state `StockEditPhase`, and
  this is ~3x that — sized M, and the reason manual entry is split into
  its own task (TASK-322)).
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
  highlight: **frozen 2026-07-14 at the TASK-316 eyeball gate — variant
  (a) inverse box** (filled `PR_COL_STRIP_TEXT` rect, field-coloured
  label); labels at y68/94/120/146. TASK-317's editor frames passed the
  same gate as rendered (stacked-button fork, slot-0 delete disabled,
  40 px confirm buttons) — and spawned TASK-328/327 (shared Settings
  widget kit + style-enforcement pass) so the editor's button idiom
  becomes THE Settings idiom instead of a fifth hand-roll.
- **Touch**: `handleTouch` currently returns `STRIP_NONE` for `x >= 240`
  (display-only). New behaviour: hit-test the label rows; tap →
  `_setActiveLoc(slot)`. Taps elsewhere in the strip stay inert.
- **`_setActiveLoc(uint8_t slot)` — the single switch primitive (DEV-3 +
  QM-1).** One shared helper, called by exactly two sites: the strip tap
  and the `set prloc active <i>` debug command — never two inline copies
  of the sequence (the BP-047/LL-110 duplication shape). It does, in
  order:
  1. Guard: `slot == prActiveLoc` or empty slot → no-op (no flicker).
  2. Copy `prLocs[slot]` → `prLat/prLon` write-through mirror,
     `prActiveLoc = slot`, `saveSettings()`.
  3. **Reset the result/staleness state** — `_result`, `_everHadResult`,
     `_lastGoodMs`, `_prErr` — so the strip doesn't show the old
     location's aircraft count/age and the ADR-046 amber "connecting"
     indicator fires for the new location (DEV-3: as previously drafted,
     none of these reset).
  4. Bump the **location epoch** (below), `_repaintDisc()` — which already
     redraws runways internally (`planeRadarApp.h:449`); the earlier
     draft's separate `_drawRunways()` call was redundant — then
     `enqueuePlaneRadar()` for the new centre.
- **Stale in-flight result (VE-PRL-6, TASK-308/309 lineage):** a fetch for
  the *old* location may already be in flight at switch time.
  `enqueuePlaneRadar()` gains an epoch byte echoed in `PlaneRadarResult`;
  the app's poll discards any result whose epoch predates the current one
  (same identity rule as the geocode `seq`). Without this, old-location
  aircraft render on the new-location grid up to one full fetch cycle
  after a switch.
- Label length 5 is the hard bound: 34 usable px / 6 px-per-char font-1
  glyph advance (strip W35 minus the x=240 border line).
- One-location degenerate case: single row, tap is a no-op (no flicker
  repaint on same-slot tap — guard `slot == prActiveLoc`).

Preview-first per BP-048: extend `app/tools/preview_planeradar.py` with the
label rows + active highlight and eyeball-gate the strip layout (marker
relocation, pitch, highlight style) before firmware code.

## Host-side left shift — preview, prototype, query derisk

Everything decidable on the host gets decided on the host before firmware
code exists (BP-048 lineage; same phase-0 discipline as M-PLANERADAR).

### Strip layout — preview tool first

Extend `app/tools/preview_planeradar.py`: slot label rows at the agreed
pitch, active-slot highlight variants (inverse box vs colour), N^ marker
deleted, empty-slot rendering, degenerate single-slot case. Eyeball-gate
the layout (BP-048: init must paint; human eyeball approves) before any
`planeRadarApp.h` edit. The preview is also where the highlight-style
choice (deferred from Q-review) actually gets made.

### Editor flow — preview/prototype

The slot-editor sub-view (slot list, Lookup|Manual fork, confirm screen)
is new Settings UI; prototype the screen flow in the preview tool (static
frames are enough — the point is layout + wording + tap-target sizes, not
interaction) before committing to `appsSection.h` geometry.

### Geocode query — derisk on host, phase-0 style

The 2026-07-13 live probes (provider matrix, cross-sign chain verify)
were ad-hoc; formalize into a repeatable probe script + short phase-0
report (`M-PR-LOCATIONS/phase0-geocode-probe.md`, pattern of
`M-PLANERADAR/phase0-api-probe.md`) covering:

- **Query matrix re-run**: NL full/PC4, UK full/outward, DE, at least one
  postcode-with-space case — assert the "full postcode" rule holds and
  document per-country quirks.
- **URL encoding**: space and `+` handling in `postalcode=`.
- **Response contract**: `lat`/`lon` are JSON *strings*; `[]` on no match;
  measure real response sizes with `limit=1&addressdetails=0` to validate
  the ~1 KB parse-buffer budget (measure, don't guess — LL-104 spirit).
- **HTTP/1.0 compat**: `openHttps()` forces `useHTTP10(true)`; confirm
  Nominatim answers HTTP/1.0 sanely (no chunked-only behaviour, no
  redirect to a different host that would dodge the pin).
- **UA policy**: confirm default-UA 403 and chosen project UA acceptance,
  so the firmware string is known-good before first device test.
- **Rate behaviour**: single probes ≥1 s apart; note any 429/`Retry-After`
  observed so the editor's Retry wording can be honest.
- **Cert-chain evidence (QM-2 — evidentiary bar):** the "verifies against
  the already-pinned ISRG Root X1" claim above rests on ad-hoc 2026-07-13
  probes; the probe script re-runs the strict verify (the
  `check-datatask-certs` method, BP-039 — verify, don't read issuer
  strings) and the report commits the output. Same task adds
  `nominatim.openstreetmap.org` to `run/check-datatask-certs`'s ENDPOINTS
  roster (VE-PRL-12) — the claim is **provisional until that lands**.

Probe cadence: manual/on-demand only — do NOT wire into run/test (external
service, 1 req/s policy; same restraint as the ≥60 s adsb.fi probe rule).
Exit gate: probe report reviewed before the fetcher task (TASK-320) starts.
Sequencing (VE-PRL-11): the fetcher also depends on M-CERT-ERRCODE's
minimal `-120` sentinel slice (TASK-318, pulled forward per PM review) so
the new pinned call site is born with correct cert-failure surfacing
instead of retrofitting it in the later audit.

## Verification — design for testing (M-SERIALDBG)

Testability is designed in, not bolted on. New serial-debug surface
(debug build, `handleSerialCommands` conventions):

- `get prloc` — dump all slots (`i label lat lon`), active index, and the
  last geocode result/error code. The diagnostic surface for every T_PRL
  test (same role `get wrStation` / `get dataq` play elsewhere).
- `set prloc <i> <label> <lat> <lon>` — write a slot directly, bypassing
  the editor. Test setup in one line; also the T_PRL_04 migration test's
  teardown tool.
- `set prloc active <i>` — programmatic switch, so switch-side effects
  (repaint, re-project, re-fetch) are testable independently of strip
  tap hit-testing.
- `set kbText <string>` + `set kbOk` / `set kbCancel` — **prerequisite
  primitive (VE-PRL-1, blocker):** inject text into the active
  `KeyboardWidget` buffer and commit/cancel it. No serial path into the
  keyboard exists today — the stock-ticker editor tests (T232/233/246/247)
  have been non-executable for exactly this reason, and this design has
  three keyboard fields per editor pass. Landing the hook unblocks those
  stock tests too. Filed as its own task (TASK-325) ahead of the editor
  work.
- `set geocode <lat> <lon> [display]` / `set geocode err <code>` — stub
  the next `pollGeocode()` result. **Isolation mechanism (VE-PRL-2,
  blocker), specified structurally like `prInjectAircraft`:** the injected
  result parks in a dedicated slot that `pollGeocode()` checks *before*
  the real result slot; while one is parked, `enqueueGeocode()` is a no-op
  (no real fetch can race the stub — the TASK-276 bug shape was precisely
  a real fetch overwriting injected state); the parked result is consumed
  on first poll and carries whatever `seq` the consumer's pending request
  has, so it passes the identity check. Editor-flow tests (T_PRL_01a/03
  UI legs) thus run without live Nominatim: keeps [NETWORK]-tagged tests
  to the single genuine end-to-end case (T_PR_05 flake lesson — network
  tests are the ones that rot).
- Strip taps: drive via the existing M-SERIALDBG touch injection; slot-row
  hitbox Y-constants live next to the other `PR_STRIP_ROW_*` constants so
  tests reference named geometry, not magic numbers (settings-nav
  coordinate-drift lesson: tests break loudly, not silently, if row
  order/pitch changes).
- Geocode fetch observable in `get dataq` like every other dataTask
  fetcher (queue state, last error), so "editor spinner stuck" has a
  diagnosis path.

## Verification sketch (VE to own)

- T_PRL_01a: slot editor round-trip, **stubbed** — full keyboard flow via
  `set kbText`, result via `set geocode`; save, reboot, slot persists. The
  primary gate: no network dependence (VE-PRL-3 split — don't bundle novel
  parse/persist logic with live-service risk in one test).
- T_PRL_01b: thin live smoke, [NETWORK] tag — one real Nominatim lookup
  including a space-containing postcode (on-device URL-encoding check,
  VE-PRL-9). SKIP on network trouble is acceptable; 01a is the gate.
- T_PRL_02: strip tap switches location — disc repaints, runways re-project,
  fetch re-enqueues at new centre (assert via `get dataq` / LOG_D URL), and
  strip count/age reset (no stale old-location values — DEV-3).
- T_PRL_03: geocode failure paths — `set geocode err` → decoded error +
  Retry; bad postcode → -96 "not found" UI; UA missing is not testable
  without code change (policy, not behaviour).
- T_PRL_04: migration — pre-upgrade settings.json (no prLocs key) → slot 0
  seeded from prLat/prLon, active 0.
- T_PRL_05: same-slot tap no-op; delete-active falls back to slot 0.
- T_PRL_06: manual lat/lon entry round-trip — out-of-range values
  (91, -200) rejected at the editor, valid pair persists and projects.
- T_PRL_07: persistence layers (VE-PRL-4) — slots survive `run/flash`
  (firmware reflash); documented-destroyed by `run/flash-fs` (same class
  as cal.json/settings.json wipe — expected, but asserted so the behaviour
  is recorded, not folklore).
- T_PRL_08: late result after cancel (VE-PRL-5) — cancel mid-lookup, then
  deliver stubbed result with the stale seq → editor ignores it, no state
  change.
- T_PRL_09: switch discards in-flight old-location fetch (VE-PRL-6) —
  switch while a fetch is pending; old-epoch result must not render.
- T_PRL_10: slot-0 delete is refused (VE-PRL-10).
- T_PRL_11: geocode during Spotify-active (VE-PRL-7) — lookup with the
  Spotify TLS session live; BP-031 yield honoured, no tlsYield starvation
  regression (this exact seam has 5 prior fix layers).
- Label uniqueness (VE-PRL-8), decided: **duplicates allowed** — the slot
  index is the identity, labels are display-only text. Documented here so
  the editor doesn't grow a uniqueness check nobody specified.
- Nominatim host added to the run/test step-0 cert preflight roster.

## Heap / budget note

No resident growth: `GeocodeResult` + parse doc live only during the
one-shot fetch on the dataTask stack (bounded ~1 KB, well under the 14 KB
stack's measured margins); `prLocs[4]` adds 64 B to `AppSettings`
(`label[6]` pads to 8 for float alignment → 16 B/slot × 4; DEV minor
corrected the earlier 56 B figure). No new task, no new persistent TLS
session.

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
