# Design — M-HOME-LOCATION: one device home location (X030 resolution)

> Owner: Architect
> Status: draft
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
  (writes `prLocs[0].lat/lon` + refreshes the mirror + save). Label stays
  `"HOME"` — city names don't fit PR_LABEL_MAX=5, and the label is the
  *slot's* name, not the place's.
- **prloc HOME-slot editor** (postcode geocode / manual): **refines coords
  only** — tz and `city` name untouched. Postcode precision inside the same
  city is the intended use; the editor is the precision tool, the city picker
  is the region tool.
- Divergence guard (cheap, non-blocking): if a HOME-slot edit lands >500 km
  from the current city coords, the confirm screen renders one hint line
  "timezone follows Time & Location" — informs, never blocks. (The user may
  genuinely be moving; the next city pick re-converges tz and coords.)
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
Then derive the mirror. Fresh device: home = Amsterdam compile default —
weather's previous hardcoded-Luton behaviour is superseded (see §6).

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
occur). If G4 ships first anyway, this design's migration converts it with no
rework: the caller's coordinate source changes from `g_settings.lat/lon`
(raw) to `g_settings.lat/lon` (mirror) — same field, new derivation. Weather
tile naming: show `city` when set, else the HOME label.

## 7. Open questions

- **OQ1**: should a >500 km HOME-slot edit *offer* a matching city re-pick
  (deep-link to the city picker) instead of just hinting? v1 hints only.
- **OQ2**: seed `webRadioCountry` from the picked city's country when the user
  never customised it (detect: value still the "NL" compile default)? Human
  call at M-WEBRADIO-SETTINGS or here; zero code risk either way.
- **OQ3**: weather tile label for a postcode-refined home — `city` name may be
  a neighbouring city (picker granularity). Cosmetic; v1 accepts.

## 8. Verification sketch (VE to own)

`T-HOME` family (DUT):

- T-HOME-01 — city pick → prLocs[0] coords + mirror updated + persisted; radar
  HOME slot renders new coords; weather refetch fires with them (rides G4's
  URL LOG_D hook).
- T-HOME-02 — HOME slot postcode refine → mirror + weather follow; tz and
  `city` name unchanged.
- T-HOME-03 — radar strip switch to slot 1 → weather coords UNMOVED (home ≠
  active slot).
- T-HOME-04 — migration: settings.json with city set + compile-default
  prLocs[0] → boot seeds slot 0 from city; any user-edited prLocs[0] survives
  an identical boot untouched.
- T-HOME-05 — divergence hint: geocode HOME >500 km from city → hint line
  renders on confirm; ≤500 km → absent.
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
