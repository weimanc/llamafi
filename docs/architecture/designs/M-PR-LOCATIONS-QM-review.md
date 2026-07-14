# QM Panel Review — M-PR-LOCATIONS: PlaneRadar location presets + geocode lookup

> Owner: QM
> Date: 2026-07-13
> Scope: process/quality compliance review of
> [M-PR-LOCATIONS-location-presets.md](M-PR-LOCATIONS-location-presets.md)
> (commit-time draft, Q1–Q7 resolved same day). Findings labelled QM-N,
> classified blocker / major / minor, each citing the BP/LL id or process
> rule it rests on, with a one-line proposed resolution — format of
> [touch-ux-panel-QM-review.md](touch-ux-panel-QM-review.md).
> Architect dispositions; QM does not edit the design doc.

Review bar applied: BP/LL compliance (preview-first/eyeball gates, measure-
don't-guess, cert-pinning procedure, network-test restraint), repeated-lesson
risk against `lessons_learned.md`, process correctness (status/ownership
headers, bidirectional supersession), scope-discipline (deferred/grown items
parked with owner+trigger, not prose — BP-003/BP-035/BP-040 family), and — per
this review's specific brief — external-service licensing exposure (Nominatim/
OSM usage policy and ODbL attribution) for a device that geocodes against a
possibly-published GitHub repo.

Code and doc claims were independently spot-checked on the tree at review
time: `planeRadarApp.h` line refs (109 `prLat/prLon`, 209 `STRIP_NONE`, 341/
418-419 fetch+project call sites, 22-23/113-116 strip geometry constants) all
verified accurate; `settingsStorage.h:106`'s D4-era comment and
`M-PLANERADAR-plane-radar-app.md:152-158`'s D4 text both confirmed as the
doc claims; `phase0-preview-ui.md`'s frozen strip layout (incl. the `N^`
bezel marker at `strip_x+17, y=120`, closed as part of OQ4) confirmed as the
"strip is display-only" / N^-marker source the design proposes to overturn.
No committed script or evidence file exists anywhere in the tree for the
2026-07-13 Nominatim probes (grepped `app/tools/`, no `nominatim` hit) — the
design doc itself is honest about this ("the 2026-07-13 live probes …
were ad-hoc"), which is the trigger for QM-2 below.

---

## What it gets right

- **BP-048 applied correctly, twice.** Both the strip-layout change (N^
  removal, label rows, active highlight) and the new editor sub-view are
  explicitly routed through `preview_planeradar.py` / the preview tool
  before any firmware edit, with an eyeball gate named for the layout
  question specifically deferred from Q-review (highlight style). This is
  the load-bearing lesson from LL-109/BP-048 (PlaneRadar's own paint bug)
  applied prospectively to the next PlaneRadar change — good instance of a
  team actually using its own most recent lesson.
- **BP-031 applied correctly.** `tlsYield()`/`tlsResume()` and `openHttps()`
  with a named root-CA alias are called out explicitly for the new fetcher,
  matching the established fetchWeather/fetchCrypto/fetchStockChart shape —
  no "small fetch, skip it" hand-wave (the exact thing BP-031 exists to
  forbid).
- **LL-107 lesson honoured, not repeated.** `GeocodeResult` carries a
  dedicated `bool ok` field distinct from the raw `errorCode`, avoiding the
  exact 0-means-both-"ok"-and-"never-fetched" collision that broke
  `prLastHttp`-based tests in LL-107. This is a deliberate improvement over
  PlaneRadar's own existing `PlaneRadarResult.errorCode` pattern one struct
  over, in the same design doc's own dependency chain — worth naming so it
  isn't accidentally "fixed" back to the broken shape at implementation time.
- **BP-034 applied correctly.** `set geocode <lat> <lon> [display]` / `set
  geocode err <code>` gives every editor-flow test a synthetic path,
  keeping the live-network case down to one tagged `[NETWORK]` test
  (T_PRL_01) — exactly the "blocked-with-a-fallback" shape BP-034 asks for,
  not "blocked, no coverage."
- **Network-test restraint honoured.** The geocode probe cadence is
  explicitly "manual/on-demand only — do NOT wire into run/test," citing the
  same restraint as the adsb.fi ≥60 s probe rule. Consistent with house
  practice on external-service courtesy.
- **BP-024 (VE debug-spec-first) is structurally satisfied** — `get prloc` /
  `set prloc` / `set geocode` are designed in alongside the feature, not
  proposed as a follow-up.

---

## Findings

### QM-1 (major) — Active-slot switch has no named shared helper; same duplication shape BP-047 was written to stop

The design specifies the switch side-effect sequence (`prActiveLoc = slot`,
write-through to `prLat/prLon`, `saveSettings()`, `_repaintDisc()` +
`_drawRunways()` + `enqueuePlaneRadar()`) once, in prose, under "Touch." It
then separately specifies `set prloc active <i>` as "programmatic switch, so
switch-side effects (repaint, re-project, re-fetch) are testable
independently of strip tap hit-testing" — i.e. a **second call site** that
must run the identical sequence. Nothing in the doc names a shared
`_setActiveLoc()`-style helper (the pattern `_setPreset()`/
`_applyRangeSetting()` already established in this same file per TASK-310).
This is the precise shape LL-110/BP-047 was adopted from two days ago: the
range-repaint fix landed in `handleInput()` but not `dbgSet("prRange")`,
diverged within 24 hours, and was only caught by a duplication-hunting
audit. BP-047's rule is explicit: "Before committing a fix, ... either (a)
extract the shared helper ... or (b) apply the fix to every sibling, or (c)
name the unfixed siblings ... out-of-scope." A design that *creates* two
call sites for one side-effect sequence should meet the same bar prospectively.

**Resolution:** name a single `_setActiveLoc(slot)` helper in the design
(mirroring `_setPreset()`) that both the strip touch handler and
`dbgSet("prloc active")` call; state it explicitly so the implementer cannot
independently re-derive the sequence twice.

### QM-2 (major) — "Chain verified OK" / "no new root cert" claim has no committed strict-verify evidence

The design states the Nominatim chain "Verified OK against the exact
`OPEN_METEO_ROOT_CA` PEM already in `dataTaskCerts.h`" and uses this to
justify skipping a new pinned root. BP-039's bar for accepting *any*
cert-chain claim is a host-side **strict offline verify**
(`openssl s_client ... -CAfile <root-only.pem> -verify_return_error`, or
`run/check-datatask-certs`) — explicitly *not* an issuer string or
`-showcerts` chain-depth read, because that weaker check is exactly what
produced the false TASK-214 "missing intermediate" root-cause (LL-083,
BP-039's own origin incident). The design doc itself says the 2026-07-13
probes "were ad-hoc; formalize into a repeatable probe script" — i.e. it
concedes no reproducible evidence exists yet — and no such script or output
is committed anywhere in the tree (checked: no `nominatim` hit under
`app/tools/`). Per LL-092 ("a script whose output is cited in a committed
report must be committed with the report") and BP-046 ("a design doc's
'confirms X' claim must be checked against the tool's source/evidence, not
just its screenshot"), a "verified OK" line resting on an unrecorded ad-hoc
check is exactly the shape those two lessons exist to catch — here, before
implementation rather than after.

**Resolution:** before the pin-reuse decision is treated as closed, run
(and commit, per LL-092) either `run/check-datatask-certs` against
Nominatim's live chain or the equivalent one-off `-verify_return_error`
command, and cite its output — not the issuer-read description currently in
the doc. This is squarely the "geocode query — derisk on host" section's
own promised follow-up; it should gate the pin-reuse claim, not just the
buffer-size claim.

### QM-3 (major) — Supersession recorded in one direction only; house convention requires a forward-pointer at the source

House convention for superseding a prior decision is to mark the
**superseded document itself** ("Status: superseded by ADR-NNN"), not only
the new document that claims the supersession — e.g. `ADR-005.md:3`,
`ADR-002.md:3`, `ADR-004.md:3`, `ADR-021.md:3` (Decision 3), `ADR-014.md:156`
(§3), and `M-PLANERADAR-plane-radar-app.md:106` itself (marks its own D4
predecessor lean "superseded by the Phase-0 revision below" in-doc). M-PR-
LOCATIONS's header claims to supersede two things — `M-PLANERADAR`'s D4
("compile-time default, no numeric-entry UI," `settingsStorage.h:106` /
`M-PLANERADAR-plane-radar-app.md:152-158`) and `phase0-preview-ui.md`'s
frozen strip layout (the `N^` bezel marker closed as part of OQ4,
`phase0-preview-ui.md:~248`) — but **neither superseded document has been
touched**: D4's text and phase0-preview-ui.md's "frozen … transcription-
ready" layout constants still read as current, undisturbed decisions. A
reader who opens `M-PLANERADAR-plane-radar-app.md` (its `Status:` line
literally says "implementation may proceed") has no signal that D4 is
stale.

**Resolution:** at acceptance, add a one-line forward-pointer to both
superseded locations: D4's paragraph in `M-PLANERADAR-plane-radar-app.md`
("superseded 2026-07-13 by M-PR-LOCATIONS — see
M-PR-LOCATIONS-location-presets.md") and a matching note next to
`phase0-preview-ui.md`'s frozen `N^` marker line. Same commit that lands the
M-PR-LOCATIONS acceptance, per the LL-045-family "doc and lean diverge,
nobody reconciles" risk this project has paid for before (touch-ux-panel
QM-1-2).

### QM-4 (minor) — Nominatim/OSM attribution requirement (ODbL) is unaddressed

Nominatim's usage policy (which the design already engages with for the
User-Agent and 1 req/s requirements) also requires visible attribution —
"© OpenStreetMap contributors" — for any application that displays results
derived from OSM data; this is a standing condition of using the public
Nominatim endpoint at all, independent of API-key status. The design's
"No API key (matters for GitHub publish)" line shows licensing-for-publish
is already a live concern for this feature, but attribution is not
mentioned anywhere — not in the geocode-provider decision, not in the
editor-flow UI spec (which shows `display_name` + coords on the confirm
screen, a natural place for a one-line credit), and not as an open question.
This sits alongside the project's own unresolved OurAirports/ODbL exposure
from M-PLANERADAR (also unaddressed there — a pre-existing gap this review
does not fault M-PR-LOCATIONS for creating, but which a second OSM-derived
data source makes more visible).

**Resolution:** add a one-line attribution requirement to the design
(smallest viable form: a static "Data © OpenStreetMap contributors" caption
on the geocode confirm screen, or a device-wide credits/about screen if one
already exists) before this ships to a repo the project intends to publish.
Flag the same gap for OurAirports/M-PLANERADAR to PM as a linked but
separate cleanup item — do not fold both into this task's scope.

### QM-5 (minor) — Parse-buffer size (~1 KB) is committed ahead of its own measurement gate, and the "measure, don't guess" citation is wrong

The "Geocode fetch" section commits to "Parse buffer: fixed ~1 KB
`StaticJsonDocument`" as a design decision, sourced only from prose ("response
… is one small JSON array object (~0.5 KB)"). The doc's own later "Geocode
query — derisk on host" section lists "measure real response sizes … to
validate the ~1 KB parse-buffer budget (measure, don't guess — LL-104
spirit)" as *future* phase-0 work — i.e. the value is adopted into the spec
before the measurement that is supposed to validate it has run, the same
sequencing gap LL-089 ("design outrunning the gate") and BP-001 ("verify
derived values before adopting into specs," from LL-020 — the RGB565/M-VIS
incident) exist to catch. Separately, the citation itself is off: LL-104 is
about matching failure *sets* across reruns to distinguish deterministic
from environmental causes, not about measuring real payload sizes before
adopting a derived buffer constant — the applicable lesson is BP-001/LL-020.
Low physical risk here (1 KB against a ~0.5 KB measured-by-eye response is a
comfortable margin, and `limit=1` bounds it structurally), so kept minor —
but the citation should point at the rule it's actually invoking.

**Resolution:** either run the response-size measurement before freezing the
buffer constant, or explicitly label ~1 KB as "estimate, to be confirmed by
the phase-0 probe" (touch-ux precedent: QM-3-3's "tag as estimate" fix).
Correct the citation to BP-001/LL-020.

### QM-6 (minor) — New pinned root reuse not routed through ADR-029's rotation table (pre-existing gap, worth closing here)

BP-030 requires: "Add the host to the ADR-029 rotation table with a
quarterly check date" whenever a pinned root CA is added or reused. The
design names only "Nominatim host added to the run/test step-0 cert
preflight roster" (the LL-103 script-attachment fix) — a different artefact
from ADR-029's own Host/Leaf-issuer/Root-CA table (`ADR-029.md:~98-99`),
which is not mentioned. This is not a new failure mode introduced by this
design — `adsb.fi`/`PLANERADAR_ROOT_CA` (added for M-PLANERADAR) is already
missing from that same table, so the gap predates M-PR-LOCATIONS — but a
design doc that explicitly reuses a pinned root and cites BP-030-adjacent
reasoning (the cross-sign MUST-comment) is a natural place to close both
omissions in one pass rather than add a third.

**Resolution:** when the companion ADR (doc's own "Feeds: likely 1 small
ADR") is written, add both `nominatim.openstreetmap.org` and the
pre-existing `adsb.fi` row to ADR-029's rotation table.

### QM-7 (minor) — Q4's scope growth (manual entry as a first-class path) isn't flagged for PM sizing at breakdown

Q4 was resolved same-day by the human to add manual lat/lon entry as "a
first-class alternative input method … not merely a failure fallback" —
a legitimate, explicitly human-approved decision, not unilateral scope
creep by the Architect. But it roughly doubles the editor-flow's
implementation surface (a second complete input path, new numeric
KeyboardWidget layout work explicitly deferred as "decide at
implementation," new −90..90/−180..180 validation, a new test T_PRL_06) and
the design's only handoff instruction is the single line "ready for PM
breakdown into tasks" — the same for every other resolved question,
undifferentiated. This project has no formal task-sizing/costing
convention to violate (checked: no effort/size tags anywhere in
`roadmap.md`), so this is not a compliance breach — but per the BP-003/
BP-035 family ("a caveat with no owner is not tracked"), a scope delta this
size deserves one explicit sentence at handoff so PM's task breakdown
doesn't under-size the editor-flow work.

**Resolution:** PM breakdown should split Lookup-path and Manual-path work
into separately estimated tasks rather than one "slot editor" task; note
this explicitly when M-PR-LOCATIONS moves from roadmap "proposed" to task
breakdown.

---

## Verdict

**PASS-with-actions.** No blockers — nothing here prevents PM breakdown from
starting, and several disciplines the team has recently paid for (BP-048
preview-first, BP-031 tlsYield, LL-107's ok-vs-errorCode fix, BP-034
injection fallback, network-test restraint) are applied correctly and
proactively in this doc. The majors (QM-1, QM-2, QM-3) should be closed
before implementation of the switch-logic and geocode-fetcher code lands —
QM-1 and QM-2 are both instances of lessons adopted in this project within
the last 48–72 hours (BP-047 2026-07-12, BP-046/BP-039 2026-06-20/07-11)
recurring immediately in the very next design; QM-3 is a direct process gap
the review brief asked to check for and found. The minors (QM-4–QM-7) should
be dispositioned (fixed, deferred-with-task, or explicitly waived) at
acceptance, not silently dropped.

| Finding | Severity | Rests on |
|---|---|---|
| QM-1 | major | BP-047 / LL-110 |
| QM-2 | major | BP-039 / LL-092 / BP-046 / LL-083 |
| QM-3 | major | House supersession convention (ADR-005/002/004/021/014 pattern) |
| QM-4 | minor | Nominatim usage policy / ODbL — licensing, not a BP/LL |
| QM-5 | minor | BP-001 / LL-020 (mis-cited in doc as LL-104) |
| QM-6 | minor | BP-030 |
| QM-7 | minor | BP-003 / BP-035 family (scope-delta-with-no-owner) |
