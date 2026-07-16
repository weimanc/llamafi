# Design — M-HOME-LOCATION: one device home location (X030 resolution)

> Owner: Architect
> Status: **accepted** (r2 2026-07-16 — panel-reviewed PASS-with-actions
> [0 BLOCKER / 5 MAJOR, all folded: H-1 writer×mirror matrix, H-2 unconditional
> slot-0 home refresh, H-3 pre-existing serial-writer mirror bug named+owned,
> H-4 kCities-by-name hint reference, H-5 debug surface + G4 hard ordering],
> human sign-off; review: `M-HOME-LOCATION-review.md`. Terminology: "active
> mirror" = prLat/prLon, "home mirror" = lat/lon — "the mirror" unqualified is
> banned per H-1/H-12)
> Date: 2026-07-16
> Feeds: — (resolves matrix X030; may crystallise a 1-paragraph ADR at acceptance)
> Tracked-as: — (PM to slice after review; sequence WITH or immediately after
> M-SETTINGS-WIRE2 G4 — see §6 coordination note)
> Registers: home-location-001 · X035 (reserved 2026-07-16)
> Prior art: M-PR-LOCATIONS ("nothing here should preclude slot 0 later being
> aliased as the device home"), M-SETTINGS-WIRE2 G4 (weather consumes city
> coords), X030 (three-store overlap), ADR-050 (ownership)

## 1. Context / pain points

Three independent location stores live in one settings.json (X030):

| Store | Written by | Consumed by | Granularity |
|---|---|---|---|
| `lat`/`lon` (+`city`, tz fields) | Time & Location city picker | tz applied live; coords consumed by **nothing today** — weather starts reading them when WIRE2 G4 lands | city (~cities.h, 81 entries) |
| `prLocs[4]` + `prActiveLoc` (mirror `prLat/prLon`) | prloc slot editor (postcode geocode / manual), strip switcher | PlaneRadar | postcode-precise |
| `webRadioCountry` | serial today; M-WEBRADIO-SETTINGS row | radio-browser station filter | country |

They can silently disagree. Pre-G4 that is invisible; post-G4 a user with
city=Tokyo and radar HOME=Amsterdam gets Tokyo weather next to Amsterdam
aircraft with no hint. M-PR-LOCATIONS deliberately deferred unification;
WIRE2 OQ1 punts it here.

## 2. Goals

1. One answer to "where does this device live", shared by weather and the
   radar's HOME slot, editable from either surface, coherent across reboot.
2. PlaneRadar's multi-location presets stay a radar-scoped *feature* —
   switching the radar to a WORK slot must not drag the weather along.
3. No settings.json schema change and no new fields; migration is load-logic
   only.
4. Radio country stays a content preference (you may live in Tokyo and listen
   to NL radio) — out of the home concept, with a documented convenience hook.

## 3. Design space

### D1 — What IS the home?

- **(a) New `homeLat/homeLon` fields**, all stores sync to it. New schema, new
  mirror invariants, three writers to retrofit. Most moving parts for the same
  observable result. Rejected.
- **(b) Home = `prLocs[0]`** (the always-defined HOME slot), with the existing
  Time-&-Location `lat`/`lon` fields **re-purposed as its write-through
  mirror** — exactly the proven `prLat/prLon` ↔ active-slot pattern
  (settingsStorage.cpp:314-318), derived on every load. Weather (G4) reads the
  mirror; the radar reads slot 0 like any slot. Zero schema change; slot 0's
  "always defined" invariant (X025) already guarantees weather always has
  coordinates. **Lean.**
- **(c) Copy-actions only** ("use city here" buttons, stores stay divergent).
  Cheapest, but keeps three truths and pushes reconciliation onto the user
  forever. Rejected as the primary mechanism (kept as UI garnish where free).

### D2 — Writer semantics (two editors, one value, different jobs)

- **City picker** (Time & Location): sets tz + `city` name + **home coords**
  (writes `prLocs[0].lat/lon` + BOTH mirrors where applicable, see matrix +
  save). Label stays `"HOME"` — city names don't fit PR_LABEL_MAX=5, and the
  label is the *slot's* name, not the place's.
- **prloc HOME-slot editor** (postcode geocode / manual): **refines coords
  only** — tz and `city` name untouched. Postcode precision inside the same
  city is the intended use; the editor is the precision tool, the city picker
  is the region tool. **A slot-0 edit refreshes the home mirror
  unconditionally — even when slot 0 is NOT the active radar slot** (H-2;
  today's `_prSaveCoords` refreshes `prLat/prLon` only iff active, so this is
  a code change, not just wording).

**Writer×mirror matrix (H-1, r2 — normative).** After this design there are
TWO mirrors and "the mirror" unqualified is banned: the **active mirror**
`prLat/prLon` (= `prLocs[prActiveLoc]`, X026) and the **home mirror**
`lat/lon` (= `prLocs[0]`, new). Every `prLocs` writer:

| Writer | home mirror (`lat/lon`) | active mirror (`prLat/prLon`) |
|---|---|---|
| `SettingsStorage::load()` | derive from slot 0, every load | derive from active slot, every load (existing) |
| City picker `_selectCity` | always (writes slot 0) | **iff `prActiveLoc == 0`** — the default case; skipping this leaves the radar silently stale (H-1) |
| `_prSaveCoords` (slot editor) | iff edited slot == 0, **unconditionally** (H-2) | iff edited slot == active (existing) |
| `_prDeleteSlot` | never — slot 0 undeletable, its coords don't move (H-2 note: do NOT add one "for symmetry") | on active-delete fallback (existing) |
| `_setActiveLoc` (strip/serial) | **never** — switching must not move home | always (existing) |
| `set prloc <i> <label> <lat> <lon>` | iff i==0 | iff i==active — **PRE-EXISTING BUG (H-3): this writer refreshes NO mirror today (`main.cpp:3422-3426`), violating X026's accounting. Fix both obligations here.** |

Implementation routes all writers through one shared helper so the matrix
lives in exactly one place (the BP-047 no-duplication shape).

- Divergence guard (cheap, non-blocking): if a HOME-slot edit lands >500 km
  from the city's coordinates, the confirm screen renders one hint line
  "timezone follows Time & Location" — informs, never blocks. **Reference
  coords (H-4): a `kCities[]` lookup by `g_settings.city` name** — after this
  design `lat/lon` ARE the home mirror, so the city's own coords survive
  nowhere in settings.json; the check is name-driven. Hint **skipped** when
  `city` is unset or not found in the table (pushed-file case). Distance:
  equirectangular with cosf latitude scale (H-6 — adequate at a 500 km
  threshold; no haversine import), computed in appsSection, exposed as a
  `divKm` field on the confirm-screen debug surface.
- Radar strip switching (`_setActiveLoc`) and non-zero slot edits: **no home
  interaction whatsoever.** Home is slot 0, not the active slot.

### D3 — webRadioCountry

Stays independent (goal 4). Recorded hook: `cities.h` already carries ISO
alpha-2 per city, so a "follow home" convenience (seed the radio country on
city pick when the user never customised it) is a one-line lookup *if ever
wanted* — OQ2, not v1. M-WEBRADIO-SETTINGS' country row is the manual path.

### D4 — Migration (load-logic only)

`prLocs[0]` is always defined, so home exists on every device already. One
upgrade rule in `SettingsStorage::load()`, after the existing prLocs
invariants: **if `city` is set but `prLocs[0]` is still the untouched compile
default** (label `"HOME"` ∧ coords == the Amsterdam constants), seed
`prLocs[0]` from the city coords — a user who only ever picked a city gets
weather + radar HOME where they said they live. Every other combination keeps
`prLocs[0]` as-is (a user-edited HOME is more precise than any city entry).
Then derive both mirrors. Fresh device: home = Amsterdam compile default —
WIRE2 G4's *planned* WX_DEFAULT fallback is superseded (H-12: today's shipped
behaviour is a compile-time URL, not a designed fallback).

Hardening (H-7 — float equality itself is verified safe against real device
serialization, ~9-10 sig digits round-trip bit-exactly): (a) introduce a named
`PR_DEFAULT_LAT/LON` constant — the symbol the comments already cite **does
not exist**; the Amsterdam values are three uncoordinated literals today
(`applyDefaults` :84-85, load fallbacks :266-267, comment claim) and D4 adds a
fourth comparison site — one constant, four users; (b) compare with epsilon
~1e-4 as cheap insurance; (c) guard the seed with "city found in `kCities`"
(or lat/lon nonzero) so a truncated time block (city set, coords missing →
parsed 0,0) cannot seed home to the Gulf of Guinea. City-pick of Amsterdam
itself is distinguishable from the untouched default (kCities has
52.3667/4.9000 vs compile 52.3676/4.9041 — verified).

## 4. Lean / decision — summary

| Item | Decision |
|---|---|
| Home identity | `prLocs[0]`; Time-&-Location `lat`/`lon` become its load-derived write-through mirror |
| Weather source | the mirror (G4's `enqueueWeather(lat, lon)` unchanged; only the caller's source and fallback story simplify) |
| City picker | writes tz + name + home coords (becomes a prLocs[0] writer — X026 writer list grows by one) |
| HOME slot editor | refines coords only; >500 km hint line |
| Radar active slot | radar-local, never touches home |
| webRadioCountry | independent; cities.h country hook recorded (OQ2) |
| Migration | D4 single seeding rule; no schema change |

## 5. Registry (Registers: line, reserved with this design)

- `feature_inventory.yaml` → **`home-location-001`** reserved.
- `cross_feature_matrix.yaml` → **X035** `home-location-001 ↔ pr-locations-001 /
  weather-001 / settings-001`: home=slot-0 semantics, the city-picker-as-
  slot-0-writer obligation (mirror refresh + save — the X026 rule), the
  radar-active-slot isolation, and the D4 migration ordering (must run after
  X025's prLocs invariants). Risk medium.
- At implementation Developer also: updates **X026** (writer list gains the
  city picker), **X030** (resolved-by pointer), **X032** (weather fallback
  story superseded — always-defined home replaces the empty-city sentinel),
  and WIRE2 §4-G4 (drop `WX_DEFAULT_LAT/LON`).

## 6. Coordination with M-SETTINGS-WIRE2 G4

G4 (weather coords) should be implemented **against this design** if both are
accepted: `enqueueWeather()` and the resume-diff stay exactly as designed; the
G4-only pieces that die are the `WX_DEFAULT_LAT/LON` compile constants and the
empty-city sentinel (slot 0 is always defined — the fallback case cannot
occur). If G4 ships first anyway (H-8 honest-cost wording): **no rework of the
enqueue/resume-diff machinery**, but the fallback branch, WX_DEFAULT constants,
and T-SETW-13's empty-city test leg ship and are then discarded — that
throwaway is the cost PM weighs when sequencing. **Hard ordering the other
way (H-10): G4 (or at minimum `enqueueWeather` + the URL LOG_D hook) lands
before or with this work** — otherwise home-location lands as pure plumbing
with no user-visible effect and three of five T-HOME tests lose their weather
leg. Weather tile naming: show `city` when set, else the HOME label.

## 7. Open questions

- **OQ1**: should a >500 km HOME-slot edit *offer* a matching city re-pick
  (deep-link to the city picker) instead of just hinting? v1 hints only.
- **OQ2**: seed `webRadioCountry` from the picked city's country when the user
  never customised it (detect: value still the "NL" compile default)? Human
  call at M-WEBRADIO-SETTINGS or here; zero code risk either way.
- **OQ3** (widened per H-9): weather tile label vs actual home coords can
  diverge durably, not just by picker granularity — city=Tokyo kept for tz +
  HOME refined to Amsterdam titles Amsterdam weather "Tokyo"; the D4 migration
  can create the same silently (user-edited slot 0 + old city name). Cheap v1
  option recorded: title with the HOME label instead of `city` when the same
  >500 km predicate holds (reuses the H-4/H-6 lookup+distance). Human call;
  shipping v1 as designed is acceptable if explicitly accepted.

## 8. Verification sketch (VE to own)

`T-HOME` family (DUT). **Observation surface (H-5): `get prloc` gains a
`"home":{"lat":…,"lon":…}` object** (the home mirror is otherwise unreadable
from the harness); persistence legs use WIRE2's `set settingsSave` forced-save
hook (nothing saves at boot — same W-1 gap; reference that mechanism, don't
re-derive). **Weather legs hard-require G4 landed** (H-5/H-10).

- T-HOME-01 — city pick → prLocs[0] coords + BOTH mirrors updated (`get prloc`
  home + active fields) + persisted via `set settingsSave` → pull; radar HOME
  slot renders new coords; weather refetch fires with them (G4 URL LOG_D).
- T-HOME-02 — HOME slot postcode refine **while a non-zero slot is active**
  (the H-2 case) → home mirror + weather follow; active mirror unmoved; tz and
  `city` name unchanged.
- T-HOME-03 — radar strip switch to slot 1 → weather coords UNMOVED (home ≠
  active slot).
- T-HOME-04 — migration: settings.json with city set + compile-default
  prLocs[0] → boot seeds slot 0 from city (`set settingsSave` → pull to
  observe); any user-edited prLocs[0] survives an identical boot untouched;
  corrupt-file leg: city set + missing time coords must NOT seed 0,0 (H-7c).
- T-HOME-05 — divergence hint: geocode HOME >500 km from city → `divKm` debug
  field present + hint asserted via the confirm-screen debug surface (H-6);
  ≤500 km → absent; city unset → skipped.
- T-HOME-06 (H-3) — `set prloc <i> …` on the ACTIVE slot refreshes the active
  mirror, and on slot 0 refreshes the home mirror (the pre-existing serial
  writer bug, fixed via the shared helper).
- Regression: T_PRL_02/04/05 (slot mechanics), T-TIME-01 (city pick), T-SETW
  weather legs.

## 9. Exit criteria

1. City pick and HOME-slot edit both move weather and radar-HOME coherently;
   radar preset switching never moves weather (T-HOME-01..03).
2. D4 migration proven both directions (seed + preserve, T-HOME-04).
3. No settings.json schema change (spiffs pull diff shows only values).
4. X026/X030/X032/X035 updated; `home-location-001` inventory completed;
   WIRE2 §4-G4 amended (WX_DEFAULT gone).
5. ADR check: every touched field still has its named owner (ADR-050) —
   the mirror's writer set is enumerated in X026 and closed.
