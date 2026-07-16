# Review — M-HOME-LOCATION: one device home location

> Reviewers: consolidated panel (Developer + VE + QM + PM)
> Date: 2026-07-16
> Design under review: `M-HOME-LOCATION.md` (draft, 2026-07-16)
> Verdict: **PASS-with-actions** (0 BLOCKER / 5 MAJOR / 5 MINOR / 2 NIT)

## Verification baseline

Every load-bearing claim was checked against the working tree (2026-07-16,
master @ 34dbdfd):

- `settingsStorage.cpp:314-318` — prLat/prLon derived from the ACTIVE slot on
  every load: exact. Invariants at `:305-313`, migration branch `:292-299`,
  Amsterdam defaults `52.3676f/4.9041f` at `:84-85` (copied into slot 0 at
  `:94-96`, repeated as load fallbacks at `:266-267`): all as cited.
- `timeSection.h:241-252` `_selectCity()` today writes `city/tzName/posixTz/
  lat/lon` + `configTzTime` + `saveSettings()` — and **nothing reads
  `g_settings.lat/lon`** anywhere in the tree (repo grep: only the picker
  writes, only load/save touch). §1's "consumed by nothing today" is exact.
- `appsSection.h`: slot save is `_prSaveCoords()` at `:808` (mirror refresh
  iff active, `:813-818`); `_prDeleteSlot()` at `:632` (active-delete falls
  back to slot 0, `:638-643`; slot 0 not deletable, `:633`).
- `planeRadarApp.h:269-295` `_setActiveLoc()` — writes prLat/prLon + persists,
  never touches `lat/lon`: already compliant with D2's "no home interaction".
- `main.cpp:3369-3398` `set prloc active` (mirrors prLat/prLon both branches);
  `main.cpp:3401-3430` `set prloc <i> <label> <lat> <lon>` (see H-3).
- `cities.h`: `CityEntry` carries ISO 3166-1 alpha-2 `country` (D3's hook is
  real); 81 entries (§1's count exact); Amsterdam city entry is
  `52.3667/4.9000` — **distinct** from the `52.3676/4.9041` compile default,
  so a city-pick of Amsterdam is distinguishable from the untouched default
  (good for D4).
- X030 note ("resolution DRAFTED — M-HOME-LOCATION … X035 reserved") and
  X035 text match the design; M-PR-LOCATIONS Q7 is annotated
  ("M-HOME-LOCATION drafts the slot-0 home alias", design lines 421-426).
  T_PRL_02/04/05 and T-TIME-01 exist in `test_plan.md`.
- Float round-trip for D4 (checked empirically): the real device dump
  `app/data/spiffs-dump/settings.json` serializes floats at ~9-10 significant
  digits (`"lat": 51.50830078`); host check confirms every plausible
  serialization of `52.3676f`/`4.9041f` ("52.3676", "52.36759949",
  "52.3675995") parses back to the bit-identical float. D4's equality test is
  sound in practice (see H-7 for the residual hardening ask).

The core architecture (D1b: home = slot 0, `lat`/`lon` repurposed as its
load-derived mirror, zero schema change) verifies clean against the code. The
findings are about **unstated writer obligations for the second mirror**, a
reference-coordinate hole in the divergence hint, and test executability.

---

## H-1 — MAJOR (Dev) — Two mirrors, one word "mirror": the dual-refresh obligation is never stated and X035 conflates them

**Evidence**: After this design there are two distinct mirrors:
`prLat`/`prLon` = mirror of the ACTIVE slot (`settingsStorage.cpp:317-318`,
X026), and `lat`/`lon` = mirror of SLOT 0 (new). D2 says the city picker
"writes `prLocs[0].lat/lon` + refreshes **the mirror** + save" — singular,
ambiguous. X035 obligation (a) makes it worse: the city picker "must refresh
the mirror + save **exactly like every writer in X026's list**" — X026's
mirror is `prLat/prLon`, not the home mirror.

Concrete failure this permits: `prActiveLoc == 0` is the default
(`settingsStorage.cpp:102`) and the common case. A city pick that updates
`prLocs[0]` + `lat/lon` but not `prLat/prLon` leaves the radar centred on
stale coordinates with no error — the exact silent-stale failure X026's own
text warns about. Symmetrically, a writer that refreshes only `prLat/prLon`
leaves weather stale.

**Disposition**: add a writer×mirror matrix to D2 (or §4): for every writer
of `prLocs[i]` — city picker, `_prSaveCoords`, `_prDeleteSlot`,
`_setActiveLoc`, `set prloc …`, `load()` — state which of the two mirrors it
refreshes and under what condition (`lat/lon` iff i==0; `prLat/prLon` iff
i==prActiveLoc; `_setActiveLoc` refreshes `prLat/prLon` only, never
`lat/lon`). Amend X035 (a) to say "both mirrors where applicable" instead of
pointing at X026's single-mirror rule.

## H-2 — MAJOR (Dev) — Slot-0 edit while slot 0 is NOT the active slot: home-mirror refresh is not specified

**Evidence**: `_prSaveCoords()` (`appsSection.h:808-823`) refreshes
`prLat/prLon` only when `_prEditSlot == prActiveLoc` (`:813`). Under the new
rule, editing slot 0 while the radar is parked on, say, slot 2 must STILL
refresh `lat/lon` (weather follows home, not the active slot) — otherwise
weather serves stale home coords until the next reboot re-derives the mirror.
The design says the HOME editor "refines coords only" (D2) and T-HOME-02
asserts "mirror + weather follow", but no text states the unconditional
home-mirror write for the not-active case; the §4 table row ("refines coords
only") reads as if `_prSaveCoords` needs no change beyond the hint line.

**Disposition**: one explicit sentence in D2: "`_prSaveCoords` on slot 0
refreshes `lat/lon` **unconditionally** (and `prLat/prLon` additionally iff
slot 0 is active)". Same for `_prDeleteSlot`: no `lat/lon` write needed
(slot 0 is never deleted, its coords don't move on a fallback — verified
`appsSection.h:638-643` only re-points the active mirror) — worth stating so
an implementer doesn't add one "for symmetry".

## H-3 — MAJOR (Dev/QM) — The serial slot writer refreshes NO mirror today; X026's writer accounting (which EC5 claims to close) is already wrong

**Evidence**: `set prloc <i> <label> <lat> <lon>` (`main.cpp:3422-3426`)
writes the slot and saves — with **no** `prLat/prLon` refresh even when
`idx == prActiveLoc` (contrast the `active` sub-form at `:3392-3394`, which
does). Yet X026 lists this path among the writers that "must refresh the
mirror" as if compliant, and this design's exit criterion 5 asserts "the
mirror's writer set is enumerated in X026 and closed". It isn't: editing the
active slot over serial leaves the radar on stale coords until
reboot/switch (latent today; T_PRL tests evidently never edit the active
slot's coords in place). Under this design the same path gains a second
unmet obligation (slot-0 edit → `lat/lon`).

**Disposition**: the design (or its implementation task) must name this
pre-existing gap and fix both obligations in the serial writer; QM to correct
X026's implied compliance claim in the same change. Cheap: route the serial
edit through the same helper H-1's matrix produces.

## H-4 — MAJOR (Dev/Arch) — The >500 km hint's reference point ("current city coords") ceases to exist once lat/lon are repurposed

**Evidence**: D2's divergence guard compares a HOME edit against "the current
city coords". But under D1b, `g_settings.lat/lon` ARE the slot-0 mirror —
after the first post-upgrade save, the stored `time.lat/lon` are overwritten
with home coords (`save()` writes `t["lat"] = g_settings.lat`,
`settingsStorage.cpp:336-337`); the city's own coordinates survive nowhere in
settings.json. The design never says where the comparison's city coords come
from. The only source left is a `kCities[]` lookup by `g_settings.city` name
(81-entry linear scan — fine), which also defines the two edge cases the
design is silent on: `city == ""` (never picked → no reference → hint must be
specified as skipped) and a city name absent from the table (can't happen via
the picker, can via a pushed file).

**Disposition**: specify "reference = kCities lookup by `city` name; hint
skipped when city unset/unknown" in D2, and note that the divergence check is
name-driven, not field-driven. (This also feeds OQ1's deep-link: the lookup
is the same.)

## H-5 — MAJOR (VE) — T-HOME-01/02/04's "mirror" legs have no observation surface; T-HOME-04's persistence leg hits the W-1 no-save-at-boot gap; weather legs are hard-gated on G4

**Evidence**:

- No `get` var exposes `g_settings.lat/lon` (home mirror). The full `cmdGet`
  surface (`main.cpp:2763-3110`) has nothing location-shaped except
  `get prloc` (`:3078-3093`), which dumps slots + active at `%.6f` — adequate
  for observing the SLOT side of T-HOME-01/02/04, but the tests' distinctive
  new assertions ("mirror updated", "weather coords UNMOVED") assert the
  mirror, which is unreadable from the harness.
- D4 migration mutates RAM only; nothing saves settings.json at boot (same
  finding as WIRE2 review W-1). So T-HOME-04's "boot seeds slot 0" cannot be
  observed via `spiffs pull` without a forced save, and "persisted" in
  T-HOME-01 needs the same mechanism (scripted Settings-cancel per W-1, or
  the `save` debug command W-1 proposed — this design should reference
  whichever WIRE2 adopts, not re-derive it).
- T-HOME-01..03's weather assertions "ride G4's URL LOG_D hook" — G4 is
  unimplemented (WEATHER_URL still hardcoded, `dataTaskStorage.cpp:121`). If
  home-location is sliced before G4, three of five tests lose their weather
  leg entirely.

**Disposition**: §8 names its debug surface: extend `get prloc` with
`"home":{"lat":…,"lon":…}` (or add `get home`) and reference the W-1
forced-save mechanism; §6/§8 state the hard test dependency "T-HOME weather
legs require G4 landed" so PM sequences accordingly (see H-10).

## H-6 — MINOR (VE) — T-HOME-05: no distance helper exists, and the hint has no assertable surface

**Evidence**: there is no haversine (or any geo-distance helper) in the tree;
the only km-scale geo math is planeRadarApp's inline equirectangular
projection constants (`planeRadarApp.h:491-492`), private to the disc
painter. The confirm-screen hint needs its own computation (equirectangular
is fine at a 500 km threshold; say so, so nobody imports a heavier
haversine). And "hint line renders" is pixel-visual — house style asserts
text via debug vars (`get clockRender` precedent, WIRE2 §6d). Without a hook
(e.g. divergence-km or hint-active in a `dbgGet`), T-HOME-05 is
eyeball-only.

**Disposition**: name the computation (equirectangular, cosf-scaled, in
appsSection) and add a debug observable (`get prloc` gains `"divKm"` on the
confirm screen, or the hint state string) — or explicitly mark T-HOME-05
[MANUAL-VISUAL].

## H-7 — MINOR (Dev) — D4's float-equality heuristic: verified safe, but harden it — the "compile default" already exists as three uncoordinated literals

**Evidence**: equality survives the JSON round trip (see baseline: device
serialization at ~9-10 sig digits round-trips `52.3676f`/`4.9041f`
bit-exactly; even the 6-digit text does). Residual risks: (a) the Amsterdam
constants are bare literals in three places already — `applyDefaults()`
(`settingsStorage.cpp:84-85`), the load fallbacks (`:266-267`), and the
comment-only claim "matches planeRadarApp.h's PR_DEFAULT_LAT/LON" (no such
symbol exists — `planeRadarApp.h:100` is a comment); D4 adds a fourth
comparison site. One drifted literal breaks the heuristic silently in the
"never migrates" direction. (b) a crafted/corrupt file with `city` set but
`time.lat/lon` missing parses as 0,0 (`:148-149`) — D4 as written would seed
home to the Gulf of Guinea.

**Disposition**: introduce a named `PR_DEFAULT_LAT/LON` constant used by all
four sites (fixes the stale comment too); compare with a small epsilon
(~1e-4) as cheap insurance; guard D4 with "city set ∧ city found in kCities"
or "lat/lon nonzero" so a truncated time block can't seed 0,0.

## H-8 — MINOR (QM) — §6's "no rework" claim for G4-first understates; WIRE2 remains un-amended (W-3 still open)

**Evidence**: §6 says "If G4 ships first anyway, this design's migration
converts it with no rework". The enqueue/resume-diff machinery survives, true
— but G4-first ships `WX_DEFAULT_LAT/LON`, the empty-city sentinel branch,
and T-SETW-13's empty-city leg, all of which §5 then deletes. That is
throwaway code + a throwaway test leg — precisely what WIRE2 review W-3
called out. Cross-doc state: WIRE2 §4-G4/EC3 still specify the sentinel with
no forward pointer to M-HOME-LOCATION (W-3's disposition not yet applied);
X030's note and M-PR-LOCATIONS Q7 are, by contrast, correctly annotated.

**Disposition**: soften §6 to "no rework of the enqueue/resume-diff; the
fallback branch and its test leg are discarded" — that is the honest cost PM
weighs when sequencing; QM tracks the W-3 WIRE2 amendment as still owed.

## H-9 — MINOR (QM/UX) — City name vs refined coords can diverge durably; the tile label will then name the wrong place

**Evidence**: §6 "show `city` when set, else the HOME label" + D2's
refine-only editor means a user with city=Tokyo (kept for tz) and a HOME
refined to Amsterdam sees a weather tile titled "Tokyo" with Amsterdam
weather — the exact confusion §1 opens with, now relocated into the label.
The 500 km hint is a single transient line at edit time; the D4 migration
path can create the same divergence with no hint at all (user-edited slot 0 +
old city name, migration correctly preserves the slot). OQ3 acknowledges only
the neighbouring-city case.

**Disposition**: widen OQ3 to the large-divergence case, with a cheap v1
option recorded: title the tile with the HOME label instead of `city` when
the same >500 km predicate holds (reuses H-4/H-6's computation). Human call;
acceptable to ship v1 as designed if explicitly accepted.

## H-10 — MINOR (PM) — Dependency direction is safe, but only one way; state it, and size the slice

**Evidence**: §6's "implement G4 against this design" is safe in the
not-accepted direction — WIRE2 G4 is self-contained (own fallback story, own
tests) and loses nothing if M-HOME-LOCATION is rejected. The unstated hazard
is the reverse: this design's observable value (weather follows home) and
three of its five tests presuppose G4's `enqueueWeather` + LOG_D hook. If PM
slices home-location first, it lands as pure plumbing with no user-visible
effect and a half-executable test family.

**Disposition**: add one line to §6: "hard ordering: G4 (or at minimum its
enqueueWeather + URL log) lands before or with this work". Sizing for the
slice as reviewed: load-order change + D4 (S), dual-mirror writer updates
incl. the H-3 serial fix (S), hint UI + distance + debug hooks (S-M) —
overall **M**, one task or two (mechanics / hint+hooks) if the hint is
deferred behind OQ1.

## H-11 — NIT — X026 names a function that doesn't exist; line drift

`_prSaveGeocode()` in X026 (and this review's briefing) is actually
`_prSaveCoords()` (`appsSection.h:808`, active-check `:813`); `_prDeleteSlot`
is `:632` not `:625`. Substance unaffected. Fix names/lines when X026 is
updated at implementation (§5 already schedules an X026 touch).

## H-12 — NIT — Small wording tightenings

- §1 table: "mirror `prLat/prLon`" for the prLocs row is correct today but
  becomes ambiguous the moment §4 creates the second mirror — after H-1's
  matrix lands, name them ("active mirror" / "home mirror") consistently in
  §1/§4/X035.
- D4 "weather's previous hardcoded-Luton behaviour is superseded" — WIRE2
  never shipped; today's behaviour is a compile-time URL, not a designed
  fallback. Say "WIRE2 G4's planned WX_DEFAULT fallback" to avoid implying a
  runtime behaviour change on already-shipped code.

---

## Verdict

**PASS-with-actions.**

D1b is the right shape and everything it leans on verifies against the code:
slot 0's always-defined invariant, the proven mirror derivation, the
migration ordering constraint, the cities.h country hook, the Q7/X030
annotations — all real and correctly cited. The D4 float-equality heuristic,
the panel's biggest a-priori worry, was verified safe against actual device
serialization. No finding invalidates the architecture.

Required before PM slices (the five MAJORs):

1. **H-1** — writer×mirror matrix; disambiguate "the mirror" in D2/X035.
2. **H-2** — unconditional home-mirror refresh on slot-0 edits, stated.
3. **H-3** — serial slot writer's missing mirror refresh named and fixed;
   X026 accounting corrected.
4. **H-4** — divergence hint's reference coords defined (kCities-by-name;
   empty-city skip).
5. **H-5** — home-mirror debug observable + forced-save mechanism named;
   G4 test dependency stated.

MINORs (H-6..H-10) are one-to-three-sentence spec additions best folded into
the same revision; NITs at implementer's discretion.
