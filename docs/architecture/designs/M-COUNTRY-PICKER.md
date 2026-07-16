# Design — M-COUNTRY-PICKER: shared country picker (SPickerList + ISO table)

> Owner: Architect
> Status: draft
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
selection (highlighted row). The country picker is `SPickerList` over the
baked table; rows render "Netherlands NL" (name left, code right — the
city picker's existing country-code column idiom).

Considered and rejected: a dedicated `CountryPicker` copying the mechanics —
second copy of scroll code the day after TASK-327 deleted the button
hand-rolls (BP-047 shape). The city picker itself migrates onto `SPickerList`
only as an optional TASK-327-style follow-up — its DUT-tested surface is not
put at risk by this design.

### D2 — Data: baked full ISO 3166-1 table

Host tool (`app/tools/gen_countries.py`, pinned source list) → checked-in
`app/gen/countries.h`: ~249 `{ name, code }` entries, alphabetical by English
short name. Flash cost ≈ 6 KB `.rodata` — trivial at current usage. Same
determinism gate as every bake (`golden.sha256`, re-run byte-identical,
`run/check` staleness).

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
  covers lists); add `set country <CC>` direct-set on the WebRadio row for
  cheap VE setup, mirroring existing settings `set` vars.

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
