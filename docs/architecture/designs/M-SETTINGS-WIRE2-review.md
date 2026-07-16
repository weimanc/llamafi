# Review — M-SETTINGS-WIRE2: Global settings wiring gaps

> Reviewers: consolidated panel (Developer + VE + QM + PM)
> Date: 2026-07-16
> Design under review: `M-SETTINGS-WIRE2-global-settings-wiring.md` (draft, 2026-07-16)
> Verdict: **PASS-with-actions** (0 BLOCKER / 4 MAJOR / 5 MINOR / 2 NIT)

## Verification baseline

Every file:line claim in the design was checked against the working tree
(2026-07-16, master @ 34dbdfd). The core claims are **accurate**:

- `main.cpp:2265` `configTime(0, 0, …)` — exact. `main.cpp:2119`
  `SettingsStorage::load()` — exact. Boot order for G5 is correct as designed:
  load (2119) → `analogReadResolution(12)` (2123) → `ledcSetup(0,…)` (2124) →
  `ledcAttachPin` (2125) → the dispLevel block (2126-2129) that
  `g_backlight.applyMode()` replaces. An auto-mode `analogRead` inside
  `applyMode()` is safe at that point (ADC1/GPIO34, resolution already set,
  channel attached).
- `main.cpp:2044` `g_ledFlow.tick()` inside `appTick()` — exact, and
  `appTick(currentAppId)` runs unconditionally every `loop()` iteration
  (`main.cpp:3526`), so a sibling `g_backlight.tick()` ticks in all apps
  including Settings.
- `dataTask.h:217` `enqueuePlaneRadar(float, float, float, uint8_t)` — exact.
- `dataTaskStorage.cpp:119-123` `WEATHER_URL` with
  `latitude=51.75&longitude=-0.47…&timezone=Europe/London` — as claimed
  (design cites :121, the latitude line; fine). Dropping `&timezone=` is safe:
  the parser consumes only `current.temperature_2m/relative_humidity_2m/
  wind_speed_10m` (`dataTaskStorage.cpp:220-222`).
- `displaySection.h:24-42` — the LDR sample→map→`ledcWrite` loop is exactly
  those lines. `settingsStorage.cpp:159-160` `|200`/`|3800` vs
  `applyDefaults()` 0/120 (`settingsStorage.cpp:22-23`) — exact; the
  divergence the design orders aligned is real.
- `clockApp.h:148` and `:352` — both hardcoded-DMY date lines, exact.
  `aquariumApp.h:933` `"%02d:%02d"` — exact. `main.cpp:1080-1090` StockApp
  resume ticker-diff — exact.
- `applyDefaults()` seeds `posixTz="UTC0"`, `city=""`, `lat=lon=0.0`
  (`settingsStorage.cpp:11-15`) — G1's no-behaviour-change claim and G4's
  empty-city-sentinel rationale check out. The 5 s NTP wait
  (`main.cpp:2266-2271`) compares raw epoch — TZ-independent as claimed.
- No missed render surface: a repo-wide sweep for `strftime`/`tm_hour` finds
  only clockApp, the weather TIME tile, aquarium, and LedFlow's clock-hue
  tick (not a formatted display). G2's surface list is complete.

Findings below are ordered by severity.

---

## W-1 — MAJOR (VE) — T-SETW-01/02 are not executable as written

**Evidence**: Nothing saves `settings.json` at boot. `SettingsStorage::load()`
(`settingsStorage.cpp:126`) only reads; `save()` is invoked from Settings-UI
edits (`settings/settingsSection.h:191`) and from `SettingsApp::_cancel()`
(`main.cpp:930-934`). Therefore:

- **T-SETW-01** (push non-default file → reboot → pull → diff): the pulled
  file is byte-identical to the pushed file whether or not `load()` parsed a
  single key. It proves SPIFFS round-trips bytes, not that load/save are
  symmetric.
- **T-SETW-02** (`spiffs rm settings.json` → reboot → pull): there is no file
  to pull — the device never re-creates it.

**Disposition**: insert a forced load→RAM→save leg between reboot and pull.
Cheapest existing path: scripted `switchApp 6` → tap Cancel — `_cancel()`
writes the entry-time snapshot (= the loaded values) to flash
(`main.cpp:930-934`). Cleaner: specify a `set settingsSave` (or `save`)
SERIAL_DEBUG command in §4 alongside `injectLdr`. Either way the test spec
must name the mechanism.

## W-2 — MAJOR (QM/design) — §6 misstates the existing verification landscape; T-SETW-11/12 duplicate planned tests

**Evidence**: §6 claims "the audit found gaps no existing test family
(T-SET/T-TIME/T-DISP/T-APPS) was *shaped* to catch: those suites verify the
Settings UI …, not that the persisted value *does* anything." The test plan
contradicts this:

- **T-TIME-02** (`test_plan.md:2366`) — "12h mode: AM/PM label visible,
  digits 1-12 … Clock app … hour 1-12, AM/PM label in top-right of time
  cell". Status: planned. This is exactly G2.
- **T-TIME-03** (`test_plan.md:2388`) — "Clock app date display matches"
  after cycling dateFmt. Status: planned. Exactly G3.
- **T-TIME-04** (`test_plan.md:2404`) — "`configTzTime()` re-applied on boot
  (time-settings C6)". Status: partial, the decisive visual steps pending.
  Exactly G1.
- **T-DISP-02/04** cover the G5 behaviours (auto dimming, boot persistence).

The defect class is therefore **"specified-but-never-executed (mostly
manual-visual) tests"**, not "no test was shaped to catch this" — a different
QM lesson with a different fix (execution discipline / automation of visual
assertions, which §6d's `get clockRender` correctly starts). The G1-G3 gaps
also violate pre-existing acceptance criteria (time-settings C1/C3/C5/C6
cited by those tests), which the design nowhere acknowledges.

Secondary conflict: T-TIME-02 specifies AM/PM "in top-right of the time
cell"; the design's G2 table says "drawn small next to the minute block".
Pick one; VE owns reconciling the assertion.

**Disposition**: rewrite §6's opening claim; have T-SETW-11/12 supersede or
absorb T-TIME-02/03 (and T-SETW-10 vs T-TIME-04) explicitly rather than
duplicating IDs over the same behaviour; reconcile the AM/PM placement spec.

## W-3 — MAJOR (QM/PM) — G4's fallback design is contradicted by M-HOME-LOCATION; no forward pointer

**Evidence**: `M-HOME-LOCATION.md` (same date, draft) §5: at implementation
Developer updates "X032 (weather fallback story superseded — always-defined
home replaces the empty-city sentinel), and WIRE2 §4-G4 (drop
`WX_DEFAULT_LAT/LON`)". §6: "the G4-only pieces that die are the
`WX_DEFAULT_LAT/LON` compile constants and the empty-city sentinel"; X035
(`cross_feature_matrix.yaml:669`) repeats it. WIRE2 §4-G4 specifies both
pieces, EC3 bakes in "empty-city fallback preserves today's behaviour", and
the doc's only pointer forward is OQ1's stale "note for M-PR-LOCATIONS
follow-up" — M-HOME-LOCATION is never mentioned. Fresh-device behaviour also
diverges: WIRE2 keeps hardcoded 51.75,-0.47; M-HOME-LOCATION moves the
default to the Amsterdam HOME slot.

Not a design error in isolation — G4's enqueue/resume-diff machinery survives
unchanged either way — but as written, PM slicing WIRE2 alone produces
known-throwaway work (sentinel + constants + the T-SETW-13 empty-city leg).

**Disposition**: add a coordination note to §4-G4 and EC3 ("fallback branch
conditional on M-HOME-LOCATION disposition"); PM sequences the
M-HOME-LOCATION accept/reject decision before slicing G4, or slices G4
explicitly against it (its §6 already permits either order).

## W-4 — MAJOR (VE/QM) — the §6c static gate is born red on its own exemplar pattern

**Evidence**: the gate asserts every `AppSettings` field appears in "≥1
consumer file outside `app/src/settings/` + `settingsStorage.*`". But
`class LedFlow` — the design's model "owner outside settings/" — is
physically defined in `app/src/settings/ledSection.h:30`, and a repo grep
confirms **zero** references to `ledMode`/`ledHue`/`ledSat`/`ledVal` outside
`settings/` + `settingsStorage.*` (main.cpp only defines/ticks the
`g_ledFlow` object, `main.cpp:986/:2044/:2136`, without naming the fields).
So the four LED fields — the design's own example of *correct* wiring (§1) —
fail the gate on day one. ADR-050's ownership table has the same blind spot
("Global flow object … `g_ledFlow`" listed as an owner outside settings/).

**Disposition**: either (a) move LedFlow to `app/src/ledFlow.h` as part of G5
(it becomes the literal sibling of `backlightFlow.h`, and rule 2 of ADR-050
is then true by file layout), or (b) extend the §6c allowlist with the LED
fields plus a documented-debt note. (a) is small and makes the gate honest;
recommend (a).

## W-5 — MINOR (Dev) — `enqueueWeather()` silently drops TASK-250 coalescing unless specified

**Evidence**: weather today goes through the generic `enqueue()` which dedups
via `s_pendingMask` (`dataTaskStorage.cpp:1515-1525`); the
`enqueuePlaneRadar` pattern the design copies does **not** coalesce
(`dataTaskStorage.cpp:1685-1696`, no mask check). Two call sites must migrate
(`main.cpp:390` init, `main.cpp:466` stale-poll tick) plus the new
resume-diff refetch — three enqueue paths that can stack in the depth-4 queue
where today at most one weather request is ever pending. TASK-250's rationale
(queue starvation behind slow fetchers) applies.

**Disposition**: one sentence in §4-G4: `enqueueWeather()` keeps the
`DATA_FETCH_WEATHER` pendingMask bit (coalescing is safe here — the config
slot always holds the latest coords, so a coalesced request fetches the
newest location).

## W-6 — MINOR (Dev) — 12h rendering spec is incomplete at the boundaries and ignores the Digital erase model

**Evidence**: the helper comment specifies "12h maps 0→12, 13→1 …" — midnight
covered, but noon (12 stays 12) and the AM/PM boundary (00:xx = AM, 12:xx =
PM) are implied, not stated; `clockAmPm()`'s contract needs them explicit or
the six call sites can diverge (the exact drift G2 exists to kill). Second:
Digital's hour is erased by overpaint — `drawString` with bg colour,
MR_DATUM anchored at x=129 (`clockApp.h:113-117`). With the specified
no-leading-zero `%d`, the 12:59→1:00 transition renders a narrower string and
leaves stale pixels of the old "1" to the left; likewise the AM/PM glyph area
when toggling back to 24h mid-session. Needs an explicit erase rect (or
keeping a fixed-width space-padded hour).

**Disposition**: state both boundary mappings in the `timeFmt.h` contract;
add an erase note to the Digital row of the §4-G2 table; extend
T-SETW-11 with a midnight/noon assertion (achievable without waiting for
noon: pick a `posixTz` whose offset makes the DUT's local hour 0 or 12).

## W-7 — MINOR (VE) — several T-SETW tests rely on debug hooks the design never specifies

**Evidence**: the serial `set` surface is special-cased vars only
(`cmdSet`, `main.cpp:3112`; per-app `dbgSet` routing) — there is **no**
setter for `fmt24h`, `dateFmt`, `city`, `lat`, `lon` today, yet T-SETW-11/12
say "`set` fmt24h=false" / "cycle dateFmt" and T-SETW-13 says "`set`
city/lat/lon (new debug var or pushed file)" — only G4 flags the hook as new.
`get duty` (T-SETW-14) has no declared owner (BacklightFlow `dbgGet`?
global?). T-SETW-10's "Clock app shows UTC+9" needs the `get clockRender`
hook, which §6d ties only to G2/G3. And T-SETW-15 re-runs T-DISP — but
T-DISP-02/03 are marked **blocked** in the plan (LDR reads 0 on DUT,
`test_plan.md:2288`); the design's `injectLdr` incidentally unblocks their
logic, which is worth claiming explicitly.

**Disposition**: add a consolidated "new debug hooks" list to §4/§6: settings
setters (or scripted Settings-UI taps — house style supports both, cf.
T-CITY-DRAG-01), `get duty` on BacklightFlow, `get clockRender` as a G1+G2/G3
shared hook, and a T-SETW-15 note re-dispositioning T-DISP-02/03 via
`injectLdr`.

## W-8 — MINOR (VE) — T-SETW-01's value generation and diff are underspecified

**Evidence**: "script-derived from `settingsStorage.cpp`'s save() key set"
yields key *names*, but non-default *values* need the enum string domains
(`kDateFmtStr` … `kPrStaleStyleStr`, `settingsStorage.cpp:107-115`) — an
arbitrary string silently falls back to the enum default in `strToEnum`
(`settingsStorage.cpp:117-122`), which would make a bad test value
indistinguishable from a wiring bug. Floats won't survive a textual diff:
pushed `"4.9041"` loads as float and re-serializes with ArduinoJson's own
float→text conversion (not byte-identical). `webRadioMaxVolume`'s default is
hwMod-conditional (`settingsStorage.cpp:259`), so "non-default" must be
chosen against both branches. The migration guard `ldrHigh==0 → 120`
(`settingsStorage.cpp:321-322`) makes `ldrHigh=0` an invalid probe value.

**Disposition**: specify a typed comparator (numeric with float tolerance
~1e-4, booleans, enum-by-table) and derive value domains from the enum
string tables, with `ldrHigh=0` and similar migration-rewritten values
excluded from the probe set.

## W-9 — MINOR (QM/PM) — exit criteria are partially stale and ADR-050 obligations have no home

**Evidence**: EC6 requires "candidate ADR-050 submitted for human sign-off" —
already satisfied (ADR-050 accepted 2026-07-16 per its header and this
design's own OQ4). Meanwhile two obligations the accepted ADR creates are in
no G-gap and no exit criterion: (a) the `NEW-APP-CHECKLIST.md` "owner
declared?" item (§3 says "once accepted" — it is accepted); (b) the
`webRadioLastStation` coalesce-on-suspend/eject owner (ADR-050 Decision 3
names the exact mechanism; WIRE2 §8 OQ4 points at the ADR and stops).

**Disposition**: PM refreshes EC6 to "checklist item landed" and either adds
a G6 (webRadioLastStation coalescing — S-size, webRadioApp `suspend()`/eject
path) or files it as a separate TASK referenced from this design, so the
accepted ADR doesn't have an unowned decision.

## W-10 — NIT — line-number drift and one imprecise phrasing (substance all correct)

- `timeSection.h:241` (configTzTime) → now `:247-248`; `timeSection.h:239-240`
  (lat/lon writes) → now `:245-246` (`_selectCity()` starts at :241; drift
  from the TASK-327/328 widget-kit edits).
- `main.cpp:444` (weather strftime) → now `:443`.
- `ledSection.h:117/122` (pause/resume) → now `:118/123`.
- "`%02d` on `tm_hour`, all 4 styles": literal only for Digital
  (`clockApp.h:113`); Flip/Nixie/VFD digit-split `tm_hour/10, %10`
  (`:183-186`, `:266-269`, `:310-313`) — equivalent hardcoded 24h, so the
  claim's substance holds.
- §4-G2 table places the Flip/Nixie date line at `:352`; `:352` is VFD-only.
  Flip and Nixie share `_drawDate()` at `:148` (comment "all non-VFD styles",
  `clockApp.h:140`) with the `/` separator — the `fmtDate(…, '-')` call
  belongs to VFD alone, and Flip/Nixie come for free with the Digital change.

**Disposition**: refresh citations at implementation; fix the G2 table row.

## W-11 — NIT — two small citation inaccuracies in adjacent docs

- §6c cites the "cert-preflight precedent" for a warn-only `run/check` step;
  the cert preflight actually runs as `run/test` step 0. The precedent is
  fine, the script it lives in is not `run/check` — matters only because
  `run/check`'s 5-gate contract (BP-008) is what CI muscle-memory expects.
- ADR-050 says the audit walked "all 45 `AppSettings` fields"; the struct has
  47 top-level fields (`settingsStorage.h:49-132`, incl. `prLocs`/
  `prActiveLoc`). Worth aligning before the §6c gate hard-codes a count.

---

## Verdict

**PASS-with-actions.**

The five gap diagnoses are real and were verified against the code with only
trivial line drift; the per-gap mechanisms (boot `configTzTime`, shared
formatting helpers, snapshot-at-enqueue, BacklightFlow) reuse proven house
patterns, comply with ADR-050, and the boot-order/ADC/tick-placement details
all check out. No finding invalidates the architecture.

Required before PM slices tasks (the four MAJORs):

1. **W-1** — make T-SETW-01/02 actually exercise load→save (forced-save
   step or debug hook).
2. **W-2** — correct §6's coverage claim; reconcile T-SETW-10/11/12 with
   the pre-existing T-TIME-02/03/04 and the AM/PM placement spec.
3. **W-3** — G4 fallback coordination note + PM sequencing against
   M-HOME-LOCATION.
4. **W-4** — resolve the LedFlow-in-settings/ contradiction so the §6c gate
   isn't born red (recommend moving LedFlow out with G5).

MINORs (W-5..W-9) are one-liner spec additions best folded into the same
revision; NITs at implementer's discretion.
