# DEV Panel Review — M-PR-LOCATIONS: PlaneRadar location presets + geocode lookup

> Reviewer: Developer · Date: 2026-07-13 · Reviewed at current tree (master,
> commit range through 63e2c2e)
> Scope: implementability against the real code — dataTask fetcher-idiom fit,
> settings write-through-mirror soundness, strip render/touch geometry,
> KeyboardWidget capability, settingsStorage migration risk, effort realism.
> Verdict: **PASS-with-actions**
> Every code-fact citation below was re-checked against the tree (not taken on
> the design doc's word) — file:line refs point at what's actually there today.

---

## Code-claim verification

- `settingsStorage` migration pattern confirmed: `SettingsStorage::load()`
  always runs `applyDefaults()` first, then overlays per-key from JSON only
  where the key is present (`settingsStorage.cpp:114-127`, PlaneRadar block
  `:251-264`) — this is the right substrate for the doc's "seed prLocs[0] from
  prLat/prLon on absent key" migration; see DEV-PRL-6 for an ordering gotcha.
- `dataTaskCerts.h` alias pattern confirmed: `#define RADIO_BROWSER_ROOT_CA
  OPEN_METEO_ROOT_CA` (`dataTaskCerts.h:232`) is exactly the "radio-browser
  pattern" the doc proposes reusing for `NOMINATIM_ROOT_CA` — sound.
- `KeyboardWidget` confirmed to have exactly two modes, `Full` and
  `UpperAlpha` (`keyboardWidget.h:47-50`) — no numeric mode exists today; see
  DEV-PRL-5.
- `openHttps()` (`dataTaskStorage.cpp:159-166`) is used by exactly **one**
  existing fetcher (`fetchTeletext`, `:498`) — every other fetcher (weather,
  crypto, `fetchStockChartBySym`, PlaneRadar's own `prFetchOnce`, WebRadio's
  `fetchOneMirror`) opens TLS/HTTP manually; see DEV-PRL-9.
- No `urlEncode`/percent-encode helper exists anywhere in `app/src/` (grep
  clean) — see DEV-PRL-7.
- `Request` struct is `{ uint8_t type; uint8_t param0; uint8_t param1; char
  symbol[8]; }` (`dataTaskStorage.cpp:37`); `enqueuePlaneRadar()` and
  `enqueueWebRadioStations()` do **not** use `symbol[8]` for their string/float
  params — they snapshot into a dedicated mutex-protected static slot
  (`s_pendingPrLat/Lon/DistNm` at `:679-682`, `s_pendingCountry` at `:667-669`)
  read back by the fetcher; only `enqueueStockChartBySym` uses `symbol[8]`.
  See DEV-PRL-2.
- `PlaneRadarApp::_repaintDisc()` (`planeRadarApp.h:462-467`) already calls
  `_redrawGridStatics()` (`:439-450`), which itself draws runways when
  `g_settings.prRunwayOverlay` is set (`:449`). See DEV-PRL-3.
- `GeocodeResult` as specced carries no request-identity field, unlike
  `StockChartResult` (`dataTask.h:43-57`), which was hardened with `symbol`/
  `rangeIdx` specifically because a stale parked result from an earlier
  request landed in a later, unrelated consumer (TASK-300, comment at
  `dataTask.h:50-54`, consumer-side guard at `appsSection.h:34-36`). See
  DEV-PRL-1.

---

## Findings

### DEV-PRL-1 (major) — `GeocodeResult` reproduces the exact bug class TASK-300 already fixed for `StockChartResult`

`GeocodeResult` (design doc lines 109-114) is `{ ok, errorCode, lat, lon,
display[48] }` — no field identifying which request it answers. The geocode
fetch is a single-slot parked-result channel exactly like
`pollStockChart()`/`s_stockChartResult` (`dataTaskStorage.cpp:87-89`), and
this codebase already hit the failure mode once: a stale result from an
earlier request got popped by a later, unrelated view
(`dataTask.h:50-54`; the fix added `symbol`/`rangeIdx` to `StockChartResult`
and a matching identity check at `appsSection.h:34-36`, TASK-300). The
location editor's Lookup path is at least as prone to this: a user can enter
Country+Postcode, back out or Cancel before the fetch resolves, open a
different slot's editor, and enter a second Lookup — the first fetch's late
result is popped by `pollGeocode()` with nothing distinguishing it from the
second request's answer, silently confirming the wrong coordinates.

**Proposed action:** add a request-identity field to `GeocodeResult` (e.g. a
monotonic request counter set by `enqueueGeocode()` and echoed back, or the
country+postcode strings truncated to a comparison length) and have the
editor discard non-matching results, mirroring `appsSection.h:34-36`'s
pattern exactly. Call this out explicitly in the design doc's dataTask
section, not left implicit.

### DEV-PRL-2 (major) — `enqueueGeocode`'s analogy to "the stock-chart request path" points at the wrong plumbing; `Request.symbol[8]` cannot hold country+postcode

The design doc frames the fetcher as "same shape as the stock-chart request
path" (line 105). But `enqueueStockChartBySym` is the *one* fetcher that
threads its string param through `Request.symbol[8]`
(`dataTaskStorage.cpp:37`, dispatch at `:1335`) — 7 usable chars after NUL.
`enqueueGeocode(countryCC, postcode)` needs to carry a 2-char country code
*and* up to a 10-char postcode (per the doc's own Lookup-path spec, "Postcode
(Full mode, ≤10)", line 151) — that doesn't fit in `symbol[8]` even before
accounting for both fields. A UK full postcode with its mandatory space
(`SW1A 1AA` = 8 characters) already exceeds `symbol[8]`'s 7-char usable
capacity on its own.

The correct precedent sits one struct away in the same file:
`enqueuePlaneRadar()` and `enqueueWebRadioStations()` snapshot their params
(lat/lon/distNm; country code) into a dedicated static slot under its own
mutex (`s_pendingPrLat/Lon/DistNm` + `s_pendingPrMux`, `:679-682`;
`s_pendingCountry` + `s_pendingCountryMux`, `:667-669`) and enqueue only the
bare `FetchType` — the fetcher reads the snapshot back at dispatch time. This
is the pattern `enqueueGeocode` needs (a `s_pendingGeocode{country[3],
postcode[11]}` + mutex), not the symbol[8] one the doc's wording points at.

**Proposed action:** correct the design doc's wording to point at the
`enqueuePlaneRadar`/`enqueueWebRadioStations` pending-config-slot pattern,
not `enqueueStockChartBySym`'s `symbol[8]` — otherwise an implementer
following the doc's stated analogy hits a silent truncation bug on the first
UK postcode with a space.

### DEV-PRL-3 (major) — the strip-tap location-switch sequence is missing the app-state reset that `isConnecting()`/age/count readouts depend on

The design's proposed handler (lines 182-186) is: "`prActiveLoc = slot`,
write-through to `prLat/prLon`, `saveSettings()`, then full `_repaintDisc()` +
`_drawRunways()` + immediate `enqueuePlaneRadar()`". Two problems against the
real code:

1. **Redundant draw.** `_repaintDisc()` (`planeRadarApp.h:462-467`) already
   calls `_redrawGridStatics()` (`:439-450`), which draws runways itself when
   the overlay is on (`:449`). Calling `_drawRunways()` again after
   `_repaintDisc()` double-draws — harmless (idempotent, cheap per the code's
   own comment at `:433-434`) but shows the spec wasn't checked against what
   `_repaintDisc()` already does.
2. **Missing state reset (the real issue).** The sequence never resets
   `_result`, `_everHadResult`, `_lastGoodMs`, or `_prErr`. After a location
   switch, `_result` still holds aircraft data from the *old* location — those
   coordinates are meaningless once `_project()`'s center moves
   (`:417-423`), so nothing will be drawn (`_repaintDisc()` zeroed
   `_prevCount`), but the strip's count/age fields are driven by
   `_updateStripDynamic()` reading `_result.count` and `millis() -
   _lastGoodMs` (`:562, 566`) — both still reflect the *old* location's last
   fetch. Worse, `isConnecting()` (`:170`, the ADR-046 amber-until-first-result
   signal, same pattern the file already establishes for app entry) returns
   `!_everHadResult`, which stays `true` from the old location — so the
   taskbar/strip give no "fetching new location" indication at all, and the
   strip briefly shows a stale aircraft count/age for a place the disc is no
   longer centered on.

**Proposed action:** the tap handler should reset `_result =
dataTask::PlaneRadarResult{}`, `_everHadResult = false`, `_prErr = false`,
`_lastGoodMs = 0` before `_repaintDisc()` + `enqueuePlaneRadar()` (drop the
redundant `_drawRunways()` call), and call `_updateStripDynamic(true)`
afterward so count/age blank immediately instead of showing stale numbers
until the next poll lands. This is closer to `init()`'s reset block
(`:141-151`) than to `_setPreset()`'s (`:353-360`, which is correct to *keep*
`_result` since a range change doesn't move the projection center).

### DEV-PRL-4 (major) — "same in-section sub-view pattern as TimeSection's CityPicker" understates the state-machine size; `AppsSection` has no precedent this deep

`TimeSection`'s sub-view is a single extra state — `TimeView::{Main,
CityPicker}` (`timeSection.h:7`) — a flat list with one level of navigation.
`AppsSection` today has exactly one level of "sub" (`_sub`: -1 = app list,
else which configurable app, `appsSection.h:74`), and each app's screen is a
single flat row list handled by one `_repaintAppRows()`/`_handleAppTap()`
pair (`:102-121`, `:195-220`). The closest existing precedent for an
async, multi-state in-place edit is Stock's `StockEditPhase::{None,
Validating, Error}` (`:72-79`) — three states, one field, one fetch.

The location editor as specced needs: slot list → slot editor → coordinate-
source choice (Lookup | Manual) → **Lookup**: country entry → postcode entry
→ spinner → confirm (Save/Retry/Cancel) → **Manual**: lat entry → lon entry →
range validation → confirm, plus Delete from the slot editor. That's on the
order of 7-8 distinct view states with branching, not the 2-state CityPicker
shape the doc cites, and it needs its own state enum + view stack nested
*inside* `AppsSection`'s existing single `_sub` selector (or a new dedicated
class `AppsSection` delegates to for `AppId::PlaneRadar`). This is
implementable, but the doc's framing ("same...pattern as TimeSection's
CityPicker") will under-size the TASK breakdown if taken literally.

**Proposed action:** PM/Architect size the slot-editor sub-view as its own
state machine (rough comparable: 3-4x Stock's `StockEditPhase` in state
count and branch count), not as a CityPicker-sized addition, when breaking
this into TASKs.

### DEV-PRL-5 (minor) — Manual lat/lon entry (a first-class path per Q4, not a fallback) hits real Full-mode friction, not just a hypothetical one

`KeyboardWidget::Mode::Full` is the only mode with digits, but digits live on
a separate SYM page (`kSym[0][0]`, `keyboardWidget.h:32`) reached via the
"123" key, and while `-` is on that same SYM page (`kSym[0][2][0]`), `.` is
one page further, on the second SYM page (`kSym[1][0][5]`, reached via
"NEXT"). Typing a coordinate like `52.3676` therefore requires: switch to
digits page, type `52`, switch to the next symbol page for `.`, switch back
for `3676` — several page flips per coordinate, ×2 for lat and lon. The
design doc treats this as a maybe ("add a numeric layout to KeyboardWidget
if Full mode proves clumsy", line 158) but it demonstrably will be clumsy
for every Manual entry, day one — Manual is not a rare fallback, it's Q4's
first-class alternative input method.

**Proposed action:** size a minimal numeric `KeyboardWidget::Mode` (digits +
`-` + `.` + backspace/OK, one page, no shift/SYM navigation) into the TASK
breakdown up front rather than deferring the decision to "if it proves
clumsy" — the friction is already knowable from the key tables without a DUT
test.

### DEV-PRL-6 (minor) — migration correctness depends on parse order inside the `planeRadar` JSON block, which the design doesn't spell out

The design's migration ("seed `prLocs[0] = {"HOME", prLat, prLon}` from the
existing fields", line 92) only carries over the *user's actual saved
location* if the new `locs` key is parsed **after** `lat`/`lon` populate
`g_settings.prLat/prLon` within the same `if (doc.containsKey("planeRadar"))`
block (today's order: `lat`/`lon` at `settingsStorage.cpp:254-255`). If a
`locs`-absent-check is implemented before that point (e.g. as a guard at the
top of the block), it would seed `prLocs[0]` from `applyDefaults()`'s
Amsterdam default instead of the pre-upgrade user's real coordinates —
silently discarding their configured location on the first upgrade.

**Proposed action:** state the ordering constraint explicitly in the design
(or as a TASK acceptance test: "pre-upgrade settings.json with a
*non-default* `planeRadar.lat/lon` migrates to `prLocs[0]` holding those same
non-default values", not just any value) — T_PRL_04 as currently sketched
(line 281-282) doesn't specify a non-default source value, so it wouldn't
catch an ordering regression.

### DEV-PRL-7 (minor) — "URL-encode the postcode" is new code; no such helper exists in the firmware today

Grep across `app/src/` for `urlEncode`/percent-encoding turns up nothing —
every existing fetcher builds URLs with plain `snprintf`/string
concatenation and none currently need to encode user-entered free text into
a query string. This isn't a reuse of existing infrastructure as the doc's
one-line mention might imply; it's a new (small) utility.

**Proposed action:** no design change needed, just size it as new code in
the TASK breakdown — a minimal space-only encoder covers the stated UK case
(`SW1A 1AA` → `SW1A%201AA` or `+`), per the phase-0 probe script's own
"URL encoding: space and `+` handling" checklist item (line 227).

### DEV-PRL-8 (minor) — `prLocs[4]` heap-budget arithmetic omits struct alignment padding

"`prLocs[4]` adds 4×(6+8) = 56 B to `AppSettings`" (line 292) computes
`sizeof(PrLocation)` as `label[6] + lat(4) + lon(4) = 14` bytes. In practice
`char label[PR_LABEL_MAX+1]` (6 bytes) followed by two `float`s will pad to
4-byte alignment for the floats, making `sizeof(PrLocation)` 16 bytes on a
typical ABI, i.e. 64 B total, not 56 B. Immaterial to the "no resident
growth" conclusion (8 bytes either way is noise against the stated ~14 KB
dataTask stack margins), but worth a `sizeof()` sanity check if the number
is going to be cited again in an ADR or TASK.

**Proposed action:** none required beyond a `static_assert` or comment fix
when the struct is actually written.

### DEV-PRL-9 (minor) — `openHttps()`'s "no header hook" framing has it backwards; the codebase's dominant pattern already does what the doc treats as a fallback

The design says `openHttps()` "takes no header hook today; either add an
optional UA parameter or set it on the HTTPClient before the call (decide at
implementation, trivial)" (lines 122-123), phrased as if extending
`openHttps()` is the default plan and the manual approach is the escape
hatch. In the actual tree, `openHttps()` is used by exactly one fetcher
(`fetchTeletext`, `dataTaskStorage.cpp:498`); every other fetcher — including
PlaneRadar's own `prFetchOnce` (`:1123-1151`, the nearest sibling to this new
fetcher) and `fetchOneMirror`, which already sets a custom User-Agent between
`begin()` and `GET()` (`:911-917`) — opens TLS/HTTP manually without
`openHttps()`. The manual pattern is not a fallback here, it's the norm, and
it's what `fetchGeocode()` should copy (mirroring `prFetchOnce`'s shape)
rather than spending effort extending `openHttps()`.

**Proposed action:** no design change needed; note for the implementer that
skipping `openHttps()` entirely (manual `tls.setCACert()` + `http.begin()` +
`http.addHeader("User-Agent", ...)` + `http.GET()`, matching `prFetchOnce`)
is both simpler and more consistent with this feature's nearest sibling
fetcher than extending the one-consumer `openHttps()` helper.

---

## Verdict

**PASS-with-actions.** The provider choice, TLS-pin reuse, settings
write-through-mirror strategy, and phase-0 host-first discipline are all
sound and well-grounded in the existing code. Four majors (DEV-PRL-1..4) must
be folded into the design before TASK breakdown — none of them overturn the
design's shape, but each would produce a real bug or a mis-sized TASK if
implemented exactly as worded:

- DEV-PRL-1: `GeocodeResult` needs a request-identity guard (TASK-300 class).
- DEV-PRL-2: `enqueueGeocode`'s wiring should point at the
  `enqueuePlaneRadar` pending-slot pattern, not `symbol[8]`.
- DEV-PRL-3: strip-tap location switch needs an explicit state reset
  (`_result`/`_everHadResult`/`_lastGoodMs`/`_prErr`), not just a repaint.
- DEV-PRL-4: the slot-editor sub-view is a bigger state machine than the
  CityPicker analogy suggests — size it accordingly.

The five minors (DEV-PRL-5..9) are implementation-hygiene / effort-sizing
notes, no design rework needed.
