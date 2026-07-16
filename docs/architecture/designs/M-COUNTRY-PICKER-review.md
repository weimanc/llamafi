# Review — M-COUNTRY-PICKER (design)

> Panel: consolidated Developer + VE + QM + PM design review
> Date: 2026-07-16
> Subject: `docs/architecture/designs/M-COUNTRY-PICKER.md` (draft, 2026-07-16)
> Verdict: **PASS-with-actions** — CP-1 (BLOCKER: AppsSection phase routing /
> full-canvas takeover unspecified — the widget's core drag interaction cannot
> work at either call site as written) must be amended into D1/D3 before PM
> slices; CP-2/3/4 (MAJOR) need design-text dispositions; the rest are
> spec/consistency fixes that can ride implementation.

---

## Claim verification (adversarial pass)

| Design claim | Verified? | Evidence |
|---|---|---|
| City picker mechanics: paged rows, scrollbar thumb drag + arrow taps, tap-to-select | YES | app/src/settings/timeSection.h:156-275 — `_cityOffset` paging (:159-160), drag on Press/Move (:200-216), arrow taps on Release (:217-227), row tap select (:233-238) |
| Donor is DUT-tested | PARTIAL | T-TIME-01 steps 3-7 are **manual visual**, status "partial … steps 4-7 visual pending" (test_plan.md:2343-2359); T-CITY-DRAG-01 (test_plan.md:2433-2443) covers the drag but its assertions are also visual. "Proven" = shipped + eyeballed, not serial-asserted — see CP-8 |
| "81-entry city list" | YES | 81 entries in app/src/settings/cities.h (`kCityCount`, :135) |
| Country-code right-column idiom exists in donor | YES | timeSection.h:187-190 (`c.country` right-aligned at x=246) |
| Opens scrolled to current selection = donor mechanics | **NO** | Donor always opens at offset 0: `enter()` sets `_cityOffset = 0` (timeSection.h:17-19) and the city-row tap (:131-135) switches view without touching the offset. Highlight exists (:162-163); scroll-to-selection is **new code** — CP-6 |
| prloc LookupCountry uses `g_keyboard.show("Country", …, UpperAlpha, 2, …)` | YES | app/src/settings/appsSection.h:616-618 |
| `_prLastCountry` session memory (Q5) | YES | appsSection.h:126 (`= "NL"`), fed at :652 |
| `tap`/`drag` serial injection exists | YES | `drag` command app/src/main.cpp:2437, `cmdDrag` :2686 (queue-drain, TASK-279 lineage) |
| Flash ≈ 6 KB | YES (sane) | 249 × (8 B struct: two 4-B pointers + ~12 B avg name + 3 B code) ≈ 5.7 KB `.rodata` |
| "Same determinism gate as every bake" | PARTIAL | golden.sha256 (app/gen/golden.sha256) lists 9 files — `webradio_countries.h` is NOT in it, vis/wave atlases use their own .sha256; `run/check` has no generic staleness regen, only the registry-specific gate 5 (check_build.sh) — CP-5 |
| "pinned source list" | **NOT VERIFIABLE** | No source named anywhere in the design — CP-3 |
| "no curated subset to maintain" | **FALSE in-repo** | `app/gen/webradio_countries.h` (~60 curated entries) + `app/tools/gen_webradio_countries.py` already exist; design never mentions them — CP-2 |
| M-PR-LOCATIONS Q5 cross-ref | YES | Q5 already annotated "Revisited 2026-07-16 … shared picker drafted as M-COUNTRY-PICKER" (M-PR-LOCATIONS-location-presets.md:417-423) — coherent both directions |
| M-WEBRADIO-SETTINGS OQ2 ship-order contingency | YES | OQ2 (M-WEBRADIO-SETTINGS.md:179-184) matches this design's D3/exit-1 in both orderings; WR-12's "point at exit criterion 1, not T-CPICK-03" correction still applies on the WR side |
| ~249 ISO 3166-1 assigned codes | YES | 249 officially assigned alpha-2 codes; note uint8_t headroom is only 6 — CP-7 |

---

## Findings

### CP-1 — BLOCKER — SPickerList cannot receive Press/Move at either call site: AppsSection's Release-only gate; the full-canvas takeover pattern is unspecified

The design's entire deliverable is a draggable scroll list, and both call
sites live inside `AppsSection`, whose input path drops every non-Release
phase before any dispatch.

Evidence:

- The settings shell forwards **all** phases to the active section
  (main.cpp:877, no filter) — that is why the donor works: `TimeSection::
  handleInput` routes Press/Move/Release into `_handlePickerInput(phase,…)`
  itself (timeSection.h:42-48).
- `AppsSection::handleInput` self-gates: `if (phase != TouchPhase::Release)
  return …;` at appsSection.h:81, **before** back-tap and all row dispatch.
  The only thing that pierces it is the keyboard capture branch at :77-80
  (`if (_prLocActive && g_keyboard.active()) { g_keyboard.handleInput(…) }`).
  A picker dropped in via D3 as written gets Release-only input: thumb drag
  (Press at timeSection.h:200, Move at :206) never fires. Same trap the WR
  review already named for the volume slider (WR-3) — this design repeats it
  without addressing it, for both of its call sites.
- The takeover pattern is likewise unspecified: `repaint()` must early-return
  while the picker owns the canvas (the keyboard-step guard at appsSection.h:
  32-33 is the precedent), `title()` needs a picker-mode string ("Select
  country" — donor precedent timeSection.h:12-14), and back-tap ownership is
  ambiguous: if the picker captures like `g_keyboard` does, the section's
  `isBackTap` check at :82 is never reached, so "cancel-via-back" (D1) needs
  the picker to own a back/cancel zone (KeyboardWidget's cancel-zone
  precedent) — or the section must check back before forwarding. The design
  says none of this.

Disposition (amend D1/D3 before slicing): specify the integration as the
`g_keyboard` precedent — a global `g_picker` (or section-held instance) with
`active()`, captured in `handleInput` **before** the Release gate, with the
repaint guard, title string, and an explicit back/cancel owner. State that
`TimeSection` needs no change (it already routes phases) — that keeps the
"donor untouched" claim honest while admitting AppsSection is restructured.
See also the PM note: this is the same AppsSection phase-forwarding work
WR-3 demands for the slider — one task, two consumers.

### CP-2 — MAJOR — an existing curated country bake (`webradio_countries.h` + `gen_webradio_countries.py`) is unaccounted for; the design's "no curated subset to maintain" is currently false in-repo

Evidence:

- `app/gen/webradio_countries.h` (~60 entries, `kWebRadioCountries`,
  `WebRadioCountry {code, displayName}`) and `app/tools/
  gen_webradio_countries.py` shipped with TASK-213 (e6c02ed).
- The tool is exactly the anti-pattern D2 rejects: codes curated from
  cities.h, **network fetch at gen time** (radio-browser `countrycodes`,
  gen_webradio_countries.py:125-129 via urllib), output not in golden.sha256
  — non-deterministic and ungated.
- The table is currently dead weight: `#include "gen/webradio_countries.h"`
  at webRadioApp.h:20, but `kWebRadioCountries` is referenced nowhere in
  app/src (grep-verified). Zero flash cost today (linker GC), real
  confusion/maintenance cost: after this design lands there would be two
  country tables and two gen tools with overlapping purpose and no statement
  of which is canonical.

Disposition: D2 must dispose of the predecessor explicitly — supersede and
delete (`gen_webradio_countries.py`, `webradio_countries.h`, the dead include
at webRadioApp.h:20) in the same slice, or justify coexistence. Cite it as
prior art too: it is the in-repo proof of why "baked, network-free, gated"
is the right call.

### CP-3 — MAJOR — the ISO source is not actually pinned: no provenance, no committed input file — T-CPICK-05's determinism claim is unverifiable as written

Evidence: D2 says "(`app/tools/gen_countries.py`, pinned source list)" and
nothing more. No upstream named, no file location, no format. The repo's
determinism pattern is ADR-008 #9/#10: **commit the source verbatim with
provenance recorded**, making the bake network-free and byte-reproducible
(skin `.wsz` precedent; `app/tools/fixtures/planeradar/` is the fixtures
precedent for data bakes). BP-002 additionally requires a companion script
with the canonical invocation. Without a committed source, "re-run
byte-identical" either tests nothing (list embedded in the tool — then say
so) or is false (fetched at gen time — the gen_webradio_countries.py
failure mode, CP-2).

Disposition: name the source in D2 — e.g. a checked-in
`app/tools/fixtures/iso3166.csv` (or a table embedded in gen_countries.py)
with recorded provenance (which upstream, which revision/date), tool
network-free by construction. T-CPICK-05 then verifies something real.

### CP-4 — MAJOR — retiring the prloc country keyboard breaks the existing prloc harness and T_PRL suite; §4's regression scope omits it

Evidence:

- `app/tools/prloc_editor_smoke.py` (T_PRL_01a's cited evidence, 14/14
  PASS 2026-07-15) drives the country step via keyboard injection: `set
  kbOk` submits the prefilled "NL" at :127 and again at :188; F1/F2 legs
  assert "Lookup -> Country keyboard, UpperAlpha maxLen=2" (:124-131). Exit
  criterion 1 deletes that path — the smoke harness and every T_PRL step
  that traverses LookupCountry break by design.
- The proposed `set country <CC>` direct-set is scoped "on the WebRadio row"
  only (D3) — nothing drives the prloc picker step cheaply.
- Driving via `tap` instead is scroll-position-dependent (row coordinates
  depend on the opened offset, which depends on `_prLastCountry` session
  state) — the WR-4 coordinate-drift concern compounds here: this is not a
  row-height shift but a whole flow-shape change.
- §4's regression line covers T-TIME (untouched donor) and T-WRSET-03 but
  says nothing about the prloc suite/harness.

Disposition: extend the serialdbg bullet — either generalize `set country
<CC>` to whichever picker context is active (submit-equivalent, mirroring
`set kbText`+`kbOk`), or add a picker-level inject; add to §4: rework
prloc_editor_smoke.py F1/F2 and re-run the T_PRL family, and re-derive any
tap-driven country-step coordinates.

### CP-5 — MINOR — "same determinism gate as every bake" overstates what run/check does; BP-002 companion script not mentioned

golden.sha256 covers 9 files (skin, shell, taskbar, mem_layout, airports) —
not webradio_countries.h, not the vis/wave atlases (own .sha256 files); and
`run/check` has no generic staleness regen — only the registry-specific
regen-and-diff (check_build.sh gate 5). Disposition: reword D2 to the
concrete mechanism: add `countries.h` to `app/gen/golden.sha256` (gate 3
then catches drift/hand-edits), optionally a gate-5-style regen diff if
staleness matters (it barely does — the source is static, ADR-008 #2
posture), and commit the BP-002 companion invocation script.

### CP-6 — MINOR — "opens scrolled to current selection" is presented as donor-proven mechanics but is new code

Donor opens at offset 0 always (timeSection.h:17-19; picker entry :131-135
never sets the offset). The idx→offset clamp (`min(idx, N - kPickerRows)`,
plus the no-selection case for an unset `webRadioCountry`) is new arithmetic
with edge cases at both ends. T-CPICK-01 already covers it — good — but D1
should stop implying it rides for free, and the empty/unset-selection
opening position should be specified (top of list?).

### CP-7 — MINOR — uint8_t offset arithmetic: safe at 249, but 6 below the ceiling for a *generic* kit widget

Donor types: `uint8_t _cityOffset` / `_sbDragAnchorOffset` (timeSection.h:
53-56), `kCityCount` uint8_t. At N=249: maxOff = 243, max idx = 248, and all
mixed expressions (`_cityOffset + kPickerRows < kCityCount` :224, drag delta
:210-213, thumb math :268-272) promote to int — no overflow. But SPickerList
is sold as generic; 255 is one grown table away. Disposition: spec the
widget's count/offset as `uint16_t` (or `int16_t`), or `static_assert(N <=
250)` at the adapter.

### CP-8 — MINOR — T-CPICK-01/02 have no serial observable for scroll position or highlight; split eyeball vs automatable legs (WR-9 posture)

No `dbgGet` exposes a picker offset/visible window (grep: nothing for
`cityOffset` in main.cpp; T-TIME-01 steps 3-7 and T-CITY-DRAG-01 are
"Visual"). `drag` injection exists (main.cpp:2437) so the *stimulus* is
automatable; the *assertion* is not, unless: (a) add a `get pickerOff`-style
var (cheap, matches `get settingsSection` precedent), or (b) assert
indirectly — drag to bottom, tap last visible row, verify the persisted
value is the table's last entry ("Zimbabwe ZW") via spiffs pull / `get`.
T-CPICK-01's "highlighted" half is eyeball (BP-048 posture) either way.
Disposition: VE to pick (a) or (b) per test and mark [MANUAL] halves
explicitly. Also note: at N=249, thumb track ≈168 px vs 243 offsets → ~1.45
rows/px; D2's "one drag lands within a page or two" assumes ~4 px finger
precision on a resistive panel — fine as a claim for the OQ1 eyeball gate to
adjudicate, not as fact.

### CP-9 — MINOR — donor drag coverage is T-CITY-DRAG-01, not "T-TIME-0x"

T-CPICK-02 cites "donor tests T-TIME-0x cover 81"; the T-TIME family
(test_plan.md:2343-2416) covers select/persist/format — the scrollbar
drag/paging test is T-CITY-DRAG-01 (test_plan.md:2433, TASK-153). Fix the
citation; the regression line "T-TIME city-picker suite untouched" should
name T-CITY-DRAG-01 too.

### CP-10 — NIT — "BP-047 shape" cite is ambiguous: best_practices.md carries TWO adopted BP-047 entries

docs/quality/best_practices.md has BP-047 "fix in duplicated logic extracts
the shared helper" (LL-110, adopted 2026-07-12) at :17 AND BP-047 "verify
shared kit code at a real call site" (LL-112, adopted 2026-07-16) at :499 —
an ID collision introduced by the latest adoption (34dbdfd). The design
means the LL-110 one. Not this design's defect — flag to QM to renumber
(the LL-112 entry should presumably be BP-049) and then fix the cite.

### CP-11 — NIT — gnu++11 construction + kit-contract placement for SPickerList

(a) If SPickerList carries NSDMI fields it must be constructed by field
assignment, not brace-init (settingsWidgets.h:57-63, LL-112), and per the
LL-112-derived BP the extraction task itself must include a real call-site
instantiation. (b) settingsWidgets.h's stated model is "no global state, no
callbacks — the section's tap handler owns what a hit means" (:51-55);
SPickerList as designed has `onSelect(idx, ctx)` callbacks and full-canvas
capture, which is the **KeyboardWidget** model (own header, `g_keyboard`
global), not the kit value-type model. Either home is fine — but pick one
explicitly (own `pickerWidget.h` beside keyboardWidget.h is the cleaner
precedent) and keep the kit header's contract comment truthful.

### CP-12 — NIT — D3 cites M-WEBRADIO-SETTINGS D3 "fires as designed", but that contract has a pending BLOCKER amendment

The WR review's WR-1 requires result-identity + abort added to the WR D3
resume-diff before slicing. This design's WebRadio bullet should say "the D3
resume-diff contract (as amended per WR-1) fires" so neither doc fossilizes
the unamended contract.

---

## PM notes (dependency ordering / sizing)

- **Not fully independent.** The AppsSection pre-Release phase-forwarding /
  full-canvas capture work (CP-1) is the same plumbing WR-3 requires for the
  volume slider. Slice it as ONE shared task with two consumers; whichever
  of M-COUNTRY-PICKER / M-WEBRADIO-SETTINGS lands first carries it. Do not
  build two capture mechanisms.
- The bake half (gen_countries.py + countries.h + golden/BP-002 wiring) IS
  independently schedulable and small — half a day including CP-2's deletion
  of the predecessor tool.
- The widget half is medium: extraction + capture pattern + two call-site
  integrations + prloc harness rework (CP-4) — the harness rework is the
  hidden line item, budget it explicitly.
- Ship-order contingency with M-WEBRADIO-SETTINGS (OQ2) is coherent in both
  directions; if picker ships first, T-WRSET country legs drive the picker
  per the WR review's PM note — no circular dependency.

## Verdict

**PASS-with-actions.** The extraction direction (SPickerList over a second
hand-roll), the full-ISO-baked-table decision, the call-site choices, and
the Q5/OQ2 cross-doc bookkeeping are sound and verified against the code.
But the design ships its core interaction without confronting AppsSection's
Release-only input gate or specifying the canvas-takeover contract (CP-1 —
BLOCKER, amend D1/D3 with the g_keyboard-precedent capture spec and share
the task with WR-3), ignores the in-repo predecessor country bake it
implicitly deprecates (CP-2), claims determinism without naming a pinned
source (CP-3), and retires a keyboard path that the existing prloc test
harness drives through (CP-4). Remaining findings are spec hygiene and test
observability that can ride implementation.
