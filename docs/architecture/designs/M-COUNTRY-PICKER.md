# Design — M-COUNTRY-PICKER: shared country picker (SPickerList + ISO table)

> Owner: Architect
> Status: **accepted** (r2 2026-07-16 — panel-reviewed PASS-with-actions
> [1 BLOCKER CP-1 phase-routing/takeover + 3 MAJOR CP-2/3/4, all folded into
> D1/D2/D3], human sign-off; review: `M-COUNTRY-PICKER-review.md`. Notable:
> CP-2 found a dead in-repo country bake this design now deletes; CP-10's
> BP-047 ID collision in best_practices.md is a pre-existing QM defect,
> handed to QM)
> Date: 2026-07-16
> Feeds: —
> Tracked-as: — (PM to slice; natural sequencing: with/after M-WEBRADIO-SETTINGS)
> Registers: — (no new feature id or matrix edge — settings-internal UI widget;
> updates `settings-widgets-001` files/notes at implementation)
> Prior art: timeSection city picker (scroll mechanics donor, DUT-tested),
> TASK-328 widget kit, ADR-008 bake pattern, M-PR-LOCATIONS Q5,
> M-WEBRADIO-SETTINGS OQ2

## 1. Context / pain points

Two Settings surfaces take an ISO 3166-1 alpha-2 country and both currently use
a 2-char `UpperAlpha` keyboard: the prloc editor's Lookup step (M-PR-LOCATIONS
Q5 deferred a picker as "pure UI polish") and the WebRadio Country row
(M-WEBRADIO-SETTINGS OQ2 accepts free text where an invalid code just fetches
an empty station list). Two consumers was the stated extraction threshold —
both hit it now. Free-typed codes have real failure modes: `UK` vs `GB`,
`NE`(Niger) vs `NL`, and an empty-list "error" whose cause is invisible.

## 2. Goals

1. One picker both call sites share; keyboard path retired at both.
2. Complete ISO coverage (any country radio-browser/Nominatim accepts), baked
   and deterministic — no runtime fetch, no curated subset to maintain.
3. Kit-fidelity (TASK-327 direction): the list mechanics become a reusable
   widget, not a third hand-roll.

Non-goals: type-ahead search; flags/locale names (English names, one table);
touching the city picker's shipped behaviour (migration is optional follow-up).

## 3. Design

### D1 — Widget shape: `SPickerList` (generic) + country adapter

Extract the city picker's proven mechanics — paged rows, right-edge scrollbar
with thumb drag + arrow taps, tap-to-select — into `settingsWidgets.h` as
`SPickerList`: full-canvas list over `(label, value)` rows with
`onSelect(idx, ctx)` / cancel-via-back, opens scrolled to the current
selection (highlighted row — **CP-6: opens-at-selection is NEW code, not
donor behaviour; the donor always opens at offset 0**; offsets are `int16_t`
in the generic widget, CP-7 — the donor's `uint8_t` clears 249 with only 6 to
spare, and a kit widget doesn't inherit that cliff). The country picker is
`SPickerList` over the
baked table; rows render "Netherlands NL" (name left, code right — the
city picker's existing country-code column idiom).

**Phase routing + canvas takeover (CP-1, r2 — BLOCKER fix).** The thumb drag
cannot work at either call site as drafted: `AppsSection::handleInput()`
drops all non-Release phases (`appsSection.h:81`); the donor only works
because TimeSection routes Press/Move itself. SPickerList integrates via the
**g_keyboard-capture precedent** (`appsSection.h:77-80` input capture +
`:32-33` repaint early-return): an active picker owns ALL touch phases and
the full canvas; the host section never paints under it; cancel is the
picker's own zone, checked before the host's header back-tap. This is the
**same phase-forwarding plumbing M-WEBRADIO-SETTINGS WR-3 needs for its
volume slider — one shared mechanism, two consumers, build once.** Serial
observability (CP-8): the picker exposes scroll offset + highlighted index
via a `get` var so T-CPICK assertions aren't coordinate-guesswork against a
scroll-state-dependent list.

Considered and rejected: a dedicated `CountryPicker` copying the mechanics —
second copy of scroll code the day after TASK-327 deleted the button
hand-rolls (BP-047 shape). The city picker itself migrates onto `SPickerList`
only as an optional TASK-327-style follow-up — its DUT-tested surface is not
put at risk by this design.

### D2 — Data: baked full ISO 3166-1 table

Host tool (`app/tools/gen_countries.py`) → checked-in `app/gen/countries.h`:
~249 `{ name, code }` entries, alphabetical by English short name. Flash cost
≈ 6 KB `.rodata` — trivial at current usage. Same determinism gate as every
bake (`golden.sha256`, re-run byte-identical, `run/check` staleness).

Provenance (CP-3 — "pinned" must be checkable, ADR-008 #9 pattern): the
source list is a **committed input file** (`app/tools/data/iso3166.csv` or
equivalent) with its origin + retrieval date in the file header; the gen tool
is **network-free** — it reads only the committed file. Determinism is then a
property of the repo, not of an upstream URL.

Supersede-and-delete (CP-2 — found in review): the repo already carries a
**dead** curated country bake — `app/gen/webradio_countries.h` +
`app/tools/gen_webradio_countries.py` (network-fetch at gen time, not in
golden.sha256; `kWebRadioCountries` is included by `webRadioApp.h:20` but
referenced nowhere). This design **replaces and deletes both files** (and the
include) — one country table in the tree, not two.

~249 rows through a paged scrollbar is coarse but workable (thumb drag is
proportional — one drag lands within a page or two; 81-entry city list already
proves the mechanics). If DUT feel demands it, a v2 A–Z index rail is the
escape hatch — explicitly deferred.

### D3 — Call-site integration

- **WebRadio Country row** (M-WEBRADIO-SETTINGS D2): tap opens the picker
  instead of the keyboard; select → `webRadioCountry` + `saveSettings()` +
  the D3 resume-diff contract fires as designed. OQ2's "invalid code →
  empty list" failure mode becomes unrepresentable.
- **prloc Lookup country step** (appsSection `LookupCountry`): picker replaces
  `g_keyboard.show("Country", ...)`; select feeds `_prPendingCountry` and
  advances to the Postcode keyboard step unchanged. `_prLastCountry`
  session-memory (Q5) becomes the picker's initial position.
- Serialdbg: rows are ordinary tap targets (`tap`/`drag` injection already
  covers lists), but picker taps are scroll-state-dependent — tests use the
  CP-8 observable, not blind coordinates. Add a **generic `set pick <value>`
  injection on the active SPickerList** (selects by value as if tapped —
  the kbText idiom), NOT just a WebRadio-row `set country`: retiring the
  prloc country keyboard breaks `prloc_editor_smoke.py` (drives that step via
  `set kbOk`, :127/:188 — T_PRL_01a's evidence) and the T_PRL suite with it
  (CP-4). Migrating that harness + the affected T_PRL steps onto `set pick`
  is **in this design's regression scope and budget**, same pass as the
  WR-4 coordinate re-derivation.

## 4. Verification sketch (VE to own)

- T-CPICK-01 — picker opens scrolled to current selection, highlighted.
- T-CPICK-02 — scrollbar thumb drag + arrows page correctly at 249 entries
  (donor tests T-TIME-0x cover 81; re-run bounds at the larger N).
- T-CPICK-03 — select at both call sites round-trips (webRadioCountry
  persisted; prloc flow advances with the picked code).
- T-CPICK-04 — back-tap cancels without mutating state.
- T-CPICK-05 — bake determinism: `gen_countries.py` re-run byte-identical.
- Regression: T-TIME city-picker suite untouched (no donor changes in v1);
  T-WRSET-03 (country change propagation) re-run on the picker path.

## 5. Exit criteria

1. Both call sites use the picker; the 2-char country keyboard path is gone.
2. Full ISO table baked + determinism-gated; `run/check` green.
3. `settings-widgets-001` inventory entry updated (SPickerList + countries.h);
   M-PR-LOCATIONS Q5 and M-WEBRADIO-SETTINGS OQ2 annotated resolved-by-this.
4. T-CPICK-01..05 pass on DUT.

## 6. Open questions

- **OQ1**: A–Z index rail if 249-row scroll feels bad on DUT — deferred, eyeball
  gate (BP-048) decides.
- **OQ2**: station-count-aware ordering for WebRadio (radio-browser countries
  endpoint) — rejected for v1 (runtime fetch vs baked determinism); revisit
  only if users actually struggle to find countries with stations.
