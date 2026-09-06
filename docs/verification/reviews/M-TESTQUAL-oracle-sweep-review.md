# M-TESTQUAL — uniform oracle sweep over every closed milestone

> Owner: **Verification Engineer**
> Status: **done** — sweep executed 2026-09-06, static only
> Commissioned by: human ruling on [LL-146](../../quality/lessons_learned.md) (`docs/quality/lessons_learned.md:9-39`)
> Method: static. No DUT, no serial port, no flash. Only `build_all_tests`/`build_all_meta`
> imported from `app/tools/`. Nothing re-scored; no milestone status edited; nothing committed.

Per the `-review.md` convention (rubric amendment A2, `M-TESTQUAL-Z-findings-review.md:12-14`), no
table below opens a cell with a bare test id. Column one carries the criterion or the document
location; ids appear in later columns only.

---

## 0. What this sweep asks

LL-146 found the same defect five times in three passes that were each looking for something else,
and named the reason it stayed invisible: nothing ever asked the question uniformly, so the class
could not be counted. This document asks it once, of every closed milestone:

> **For each stated exit criterion, what oracle does the criterion name or imply, and what oracle
> actually produced the evidence it was closed on?**

The filter is LL-146's subject-noun test — a criterion about a pixel, a colour, an interval, a
reboot, a render or a byte-exact restore, closed against an id whose oracle reads a count, a state
byte or "no crash". **It is a filter, not a verdict.** Every criterion flagged below was checked by
reading the cited id's body (or the task-board record that stands in for one) before it was flagged.

Dispositions use LL-146's proposed vocabulary — **MET / CITED / ACCEPTED / DEFERRED** — and never
`PASS`, which stays a property of a test id against its own assertion.

---

## 1. The census

| Corpus | Count | Note |
|---|---|---|
| Milestone entries in `roadmap.md` | 68 | every `### ` heading carrying a `**Status:**` line |
| — of those, reading *done* / *closed* | **55** | `roadmap.md:16` … `roadmap.md:1194` |
| — re-opened by the 2026-09-06 ruling | 1 | M-PLANERADAR (`roadmap.md:998`) |
| — reading *in progress* / *scheduled* / *partial* | 12 | M-WEBRADIO, M-WINAMP-PLAYER, M-TESTARCH, M-PR-MOTION, M-SKIN-SELECT, … — **out of scope**, flagged only where a closed milestone cites them |
| Off-roadmap milestones closed in a design doc or task board | **9 examined** | M-CLOCK-THEMES, M-CLOCK-NIXIE, M-CLOCK-VFD, M-CLOCK-FLIP, M-HOME-LOCATION, M-COUNTRY-PICKER, M-WEBRADIO-SETTINGS, M-SRCLAYOUT, M-WR-CONNECT-ASYNC |
| Design docs under `docs/architecture/designs/` | 159 | |
| — carrying an exit/acceptance-criteria section | **109 sections in 94 docs** | extracted mechanically by heading match |
| Documents in `docs/verification/regression_suite/` | **16** | all read in full |
| Registered ids in the live harness registry | 195 | `build_all_tests()` |

**Criteria and citations actually read.** 109 criteria sections were extracted and read; of these,
**61 belong to a closed milestone** and are in scope. Those 61 sections state **≈310 individual
criteria**. Against them the closing records (roadmap status lines, design-doc implementation-results
tables, regression-suite coverage tables, task-board close notes) cite **147 distinct test ids or
named runs**. Every criterion whose subject is a pixel, a colour, an interval, a render, a reboot or
a byte-exact state — **74 of the ≈310** — was individually compared against its cited oracle. The
remainder (build gates, grep assertions, "file exists", flash-budget checks) are mechanically
self-observing and were spot-checked, not exhaustively re-derived.

**Result: 10 new findings** — **7 oracle defects** and **3 overstated headers**, across 9 distinct
milestones (M-LIST-v4 appears under both severities, once in its own right and once as the set a
later milestone's regression gate cites).

---

## 2. New findings — severity A: **oracle defect**

*The criterion's subject is not observable by the cited id. The evidence is honest about what it
measured; it simply measures something else. This is H-2's class, and it needs new firmware or a new
test, not a re-word.*

### A-1 — M-SETTINGS-APP-WIRE: thirteen behavioural criteria closed on a different milestone's navigation suite

| | |
|---|---|
| Criterion | `docs/architecture/designs/M-SETTINGS-APP-WIRE.md:443-459` — **E1–E13**, all thirteen |
| Closing record | `docs/project/roadmap.md:402` — *"done (2026-06-12 — TASK-172; W1–W9 all shipped; T-SET-01..08 PASS on DUT)"* |
| Oracle actually cited | `T-SET-01` … `T-SET-08`, defined at `docs/verification/test_plan.md:2573-2725` |
| Disposition | **DEFERRED — none of E1–E13 has been observed** |

The criteria are behavioural and visual: *"Matrix color: all three values render correctly"* (E1,
`:443`), *"slow/normal/fast produce visually distinct speeds"* (E2/E3/E6, `:445-450`), *"Settings 4
→ ≈4 fish active"* (E5, `:448`), *"change ticker 1 to TSLA → StockApp shows TSLA and fetches fresh
price immediately"* (E7, `:451`), *"change to EUR → prices fetched and displayed in EUR"* (E10,
`:456`).

The cited ids are the **settings-navigation** suite from a *different* milestone — every one is
headed `[settings-001, TASK-141]` and belongs to M-SETTINGS-STUB. Their oracles are
`get settingsSection`, `get settingsAppSubmenu`, `get appId` and `g_previousAppId`
(`test_plan.md:2573`, `:2590`, `:2608`, `:2663`, `:2684`, `:2705`). Not one reads `matrixColor`,
`lifeTickMs`, `aquariumFish`, a ticker symbol or a currency. A build in which **no per-app setting
is wired at all** passes all eight.

This milestone's own suite exists and was written the same day: `app-settings-wire-001`, 27 ids
`T222`–`T248`, specified in full at
`docs/verification/regression_suite/app-settings-wire-001.md:602-628` and registered at
`docs/verification/test_plan.md:4027-4110`. **Every one of the 27 rows reads `planned`** — none has
ever been run. The suite doc itself names five Developer deliverables as
*"pre-implementation blockers"* gating them (`app-settings-wire-001.md:641-647`); the roadmap's own
close line predates any record of those blockers clearing.

**What would settle it.** Run `T222`, `T223`, `T225`, `T226`, `T228`, `T233`, `T236`, `T237` — the
SERIALDBG half, which asserts the actual fields — once their `dbgGet` blockers are confirmed
present. The MANUAL half (`T224`, `T227`, `T229`–`T231`, `T239`, `T240`) is colour and motion, i.e.
ADR-064 `get sig` territory or a named human ACCEPTED, not a PASS.

**This is the largest single finding in the sweep**: thirteen criteria, zero observed, closed on a
suite belonging to another milestone.

---

### A-2 — M-TELETEXT: closed with its own suite unrun; 21 of 24 ids are not in the harness

| | |
|---|---|
| Criterion | `docs/architecture/designs/M-TELETEXT.md:280` — *"All touch zones (fast-text bar, right strip, row links) pass DUT tap tests"* (and `:279`, `:281`) |
| Closing record | `docs/project/roadmap.md:832` — *"done … VE suite T249 ready-to-run, T272 PASS"* |
| Oracle actually cited | `T272` only, `docs/verification/test_plan.md:4490` |
| Disposition | **DEFERRED** |

`T272`'s objective is *"TLS heap contention — `fetchTeletext` concurrent with `spotifyTask`"*
(`test_plan.md:4490`). It observes heap and TLS behaviour. It touches no tap zone, no grid, no
mosaic glyph.

The touch-zone criterion's real ids are `T254`–`T260` and `T268`–`T271`
(`test_plan.md:4310-4515`); their statuses are `planned`, several also `[Blocked: G2]`. `T249`–`T251`
read `ready to run` — written, never executed. **The status line's own words are the tell**: a suite
that is "ready-to-run" is a suite that has not run, and it was quoted as evidence of a close.

Confirmed against the live registry: of `T249`–`T272`, only `T270`, `T271`, `T272` exist in
`build_all_tests()` today. **Twenty-one of the twenty-four ids this milestone registered are not in
the harness at all**, fifteen weeks after the close.

**What would settle it.** Implement and run `T254`–`T260` (the four fast-text buttons, the two
right-strip zones, the inactive-zone negative) plus `T259`/`T260` for row links. The render criteria
`T265`/`T266` are `[MANUAL]` and need `get sig` or an explicit ACCEPTED.

---

### A-3 — M-WAVE-ATLAS: a pixel-identity criterion cites a task from an unrelated milestone

| | |
|---|---|
| Criterion | `docs/architecture/designs/M-WAVE-ATLAS-firmware-playback.md:211` — *"Atlas, VU, Blank modes: pixel output unchanged from pre-053 baseline (VE TASK-053d)"* |
| Closing record | `docs/project/roadmap.md:144` — *"done (2026-05-17 — TASK-053/055a–d; ccc1bde; DUT-verified)"* |
| Oracle actually cited | `TASK-053d`, `docs/project/tasks-archive.md:2645` |
| Disposition | **DEFERRED — the citation does not resolve to this milestone** |

`TASK-053d` in the archive is **"M-CONN: `spotifyTask::resetTls()`"** (`tasks-archive.md:2645`) — a
TLS-reset implementation task in a different milestone, with no vis, no atlas and no pixel content.
The M-WAVE-ATLAS task family is `TASK-055a`–`d` (`tasks-archive.md:2579-2617`), and all four are
**Developer** tasks: enum + `nextMode()`, `tickWaveAtlas()`, flash-budget verify, and the frozen
lead-in fix. **No VE task for this milestone exists.** The pixel-unchanged criterion is therefore
closed against no evidence whatsoever, behind a citation that reads as though it were.

The neighbouring criteria in the same section are equally visual — *"white waveform animating at 20
fps"* (`:208`), *"no left-edge spike artefact"* (`:209`), *"no right-edge artefact"* (`:210`) — and
share the same (absent) evidence.

**What would settle it.** ADR-064's `get sig` differential over the vis region in each of the three
untouched modes, `sig(before) == sig(after)`, quiescent at both ends — the exact shape M-PLANERADAR
criterion 1 was re-opened onto. Failing that, the citation should be corrected to name what actually
happened, which appears to be nothing.

---

### A-4 — M-VIS-ATLAS: "pixel-identical" closed on a human eyeball, unrecorded

| | |
|---|---|
| Criterion | `docs/architecture/designs/M-VIS-ATLAS-vis-atlas.md:311` — *"VU / Wave / Blank modes: **pixel-identical** output to pre-ATLAS baseline on DUT (VE TASK-052f)"* |
| Closing record | `docs/project/roadmap.md:134` — *"done … DUT sign-off 'looks great'"* |
| Oracle actually cited | `TASK-052f`, `docs/project/tasks-archive.md:2257-2266` |
| Disposition | **ACCEPTED-shaped, but never recorded as such — currently reads as met** |

`TASK-052f`'s recorded evidence, in full: *"DUT visual sign-off by user"*, *"Tapped through Atlas →
WaveAtlas → VU → Blank → Atlas on device"*, *"User: 'looks great'"*, *"VU bars intact; Blank clean
skin bg"* (`tasks-archive.md:2259-2265`). No capture was kept, no pixel was compared to a baseline,
and no baseline was recorded to compare against.

**This is M-CLOCK-THEMES' exact shape** (LL-146 case 4) at a different milestone and six weeks
earlier: a criterion whose own word is *pixel-identical*, closed on a person looking at the screen
and being satisfied. The difference is that M-CLOCK-THEMES has since been re-recorded as ACCEPTED by
human ruling; this one still reads as met.

**What would settle it.** Same mechanism as A-3. Or a ruling: the evidence stated exactly (an
informal, unrepeatable, un-captured 2026-05-17 visual check), recorded as **ACCEPTED** with accepter
and date, not left as a satisfied criterion.

---

### A-5 — M-LIST-v4: the board says "all 7 tests passing"; the plan says 5 of 7 never ran

| | |
|---|---|
| Criteria | `docs/architecture/designs/M-LIST-v4-velocity-scroll.md:379-389` — eleven items |
| Closing record | `docs/project/roadmap.md:532` and `docs/project/tasks-archive.md:142-149` — *"suite written and executed … **All 7 tests passing**"* |
| Oracle actually cited | `T155`–`T161`, `docs/verification/test_plan.md:1540-1676` |
| Disposition | **DEFERRED for four criteria; one criterion is unsatisfiable as written** |

The recorded statuses of the seven cited ids:

| Cited id's plan entry | Recorded status | Criterion it carries |
|---|---|---|
| `test_plan.md:1557` | PASS-bearing (dead-zone tap) | *"Finger within dead zone at Release → tap plays the row"* (`:381`) |
| `test_plan.md:1575` | `written (2026-05-25)` | *"Finger outside dead zone at Release → no track play"* (`:382`) |
| `test_plan.md:1591` | `written (2026-05-25)` | speed-scaling / `get scrollVelocity` (`:384`, `:385`) |
| `test_plan.md:1609` | `written (2026-05-25)` | `cmdTick` deterministic advance (`:385`) |
| `test_plan.md:1628` | `written (2026-05-25)` | accumulator reset on Release |
| `test_plan.md:1646` | `written (2026-05-25)` | *"`tickScroll(dt)` is a no-op when dragState ≠ D_PLEDIT_SCROLL"* (`:383`) |
| `test_plan.md:1675` | **`planned`**, `[manual]`, no automation | *"Seqno change mid-drag → gesture cancelled … dragState D_IDLE"* (`:387`) |

`written` is a status meaning the body exists; it is not a verdict. `planned` is not even that.
Confirmed against the live registry: `T161` **is not in `build_all_tests()` at all** — there is no
mechanism by which the seqno-cancellation criterion could ever have been observed.

Separately, one criterion is **unsatisfiable as written**: *"DUT evidence: 5 firm-press taps register
as taps (validates 8 px dead zone before `_dragStartMs` removal)"* (`:388`). The design's own
status correction says the removal never happened and the elapsed-time arm is still load-bearing in
shipped firmware (`M-LIST-v4-velocity-scroll.md:266-273`), and the as-built dead zone is **1 px, not
8** (`docs/verification/test_plan.md:1530`). The criterion refers to a state of the code that does
not exist.

**What would settle it.** Run `T156`–`T160` to a verdict — they are in the harness and need only a
≥10-item Spotify queue (blocked-external on TASK-243, the same blocker M-WR-PLEDIT-SCROLL's gate
row names). `T161` needs a body before it needs a run. The dead-zone criterion needs rewriting to
the shipped design or dropping.

---

### A-6 — M-DATATASK-PROGRESS: the atoms the milestone delivered are never asserted

| | |
|---|---|
| Criteria | `docs/project/roadmap.md:368-380` — Phase 1 `stockQuoteProgress`; Phase 2 `weatherFetchPhase`, `cryptoFetchPhase`, `stockChartProgress` |
| Closing record | `docs/project/roadmap.md:382` — *"done (2026-06-12 — TASK-173/174; commit 95d6a93; T170/T_WX_05/T_CX_05 PASS on DUT)"* |
| Oracles actually cited | `T170` (`test_plan.md` stock suite; body `app/tools/suite/serialdbg/stock.py:150-185`), `T_WX_05`, `T_CX_05` |
| Disposition | **CITED for Phase 1 (partially); DEFERRED for Phase 2** |

`T_WX_05`'s assertion is *"`weatherReady` becomes true within 30 s"*; `T_CX_05`'s is
*"`cryptoReady=true` within 30 s"*. Neither reads `weatherFetchPhase` or `cryptoFetchPhase` — the
two atoms Phase 2 exists to add. A grep of the whole suite tree finds `weatherFetchPhase` read at
exactly one site (`app/tools/suite/serialdbg/shell.py:1645`), in a different test, and
`cryptoFetchPhase` at none.

`T170` is the closest to real coverage and still does not assert: its body reads
`stockQuoteProgress` every poll iteration (`stock.py:163`) but only ever **uses** it on the failure
branches (`stock.py:173`, `stock.py:177-182`), to enrich an error message. A run reaches PASS
purely via `quoteOkCount` advancing (`stock.py:160-162`). **A `T170` PASS is precisely the outcome
in which the progress atom's value was never checked.**

**What would settle it.** One cheap assertion per atom: drive a fetch, assert the atom leaves `-1`,
takes a value in its documented domain (0–7 for tickers, 0/1/2 for chart phases), and returns to
`-1`. That is the claim the milestone actually makes.

---

### A-7 — M-SETTINGS-STUB: "6/6" over an eight-id range, and the two missing ids are the pixel ones

| | |
|---|---|
| Criteria | `docs/architecture/designs/M-MULTIAPP/settings.md:573ff` (C3, C4 among them) |
| Closing record | `docs/project/roadmap.md:472` — *"done … `T-SET-01..08` **6/6 PASS**; DUT-141d visual all pass"* |
| Oracles actually cited | `T-SET-01`–`T-SET-08`, `docs/verification/test_plan.md:2573-2725` |
| Disposition | **DEFERRED for the two visual criteria** |

The arithmetic is the tell: *6/6* is quoted over a range of *eight* ids. The two that are not in the
six are exactly the two visual ones:

- `test_plan.md:2630` — *"Content panel renders within x:0..274, y:28..239 for all sections"*;
  status `planned (manual visual — pending DUT-141d walkthrough)` (`test_plan.md:2643`).
- `test_plan.md:2646` — *"App-switch residue: Spotify→Settings→Spotify leaves **no settings
  pixels**"*; status `planned (manual visual — pending DUT-141d walkthrough)`
  (`test_plan.md:2661`).

Both are **pending the DUT-141d walkthrough** — the same walkthrough the status line asserts *"all
pass"*. The header cites as complete the observation the two ids say is still owed. Neither id is in
`build_all_tests()`.

The residue criterion is the identical claim M-CLOCK-STYLES C8 was re-recorded DEFERRED for
(`docs/verification/regression_suite/m-clock-styles.md` § Exit criteria coverage, C8) — settled by
the same `sig(before) == sig(after)` differential.

**What would settle it.** ADR-064 `get sig` over the canvas either side of the round trip for the
residue claim, and an `inkCount == 0` assertion outside the content-panel rect for the bounds claim
— both structural, neither needing a golden.

---

## 3. New findings — severity B: **overstated header**

*The body is honest and usually candid to the point of naming its own gap. The summary line collapses
that candour into a green token. This is LL-146's root cause (b) and it is fixed by a re-word plus,
where an observation is genuinely owed, an owner and a date — not by new firmware.*

### B-1 — M-WR-PLEDIT-SCROLL: "exit criteria 13/13" over a results table containing a SKIP

| | |
|---|---|
| Criterion | `docs/architecture/designs/M-WR-PLEDIT-SCROLL.md:253-255` — *"Spotify regression gate: T155–T161 pass unchanged (**mandatory**)"* |
| Closing record | `docs/project/roadmap.md:930` — *"**DONE 2026-07-07** … exit criteria **13/13**"* |
| Oracle actually cited | the results table at `M-WR-PLEDIT-SCROLL.md:323-336`, row `:332` |
| Disposition | **ACCEPTED (human, 2026-07-07) — recorded in the design doc, not in the header** |

The design doc's own row is exemplary and says the opposite of the header:

> *"T162-T166 5/5 PASS; **T155-T160 SKIP — precondition needs a ≥10-item Spotify queue,
> blocked-external by TASK-243** … Harness registry has no `T161` — the design's range overshoots by
> one."* (`M-WR-PLEDIT-SCROLL.md:332`)

That row is a SKIP, not a pass, and the disposition was properly ratified —
*"Dispositions ratified (human, 2026-07-07): the T155-T160 blocked-external SKIP … are final.
Standing item: re-run T155-T160 when TASK-243 resolves"* (`M-WR-PLEDIT-SCROLL.md:358-360`). The
milestone is legitimately closed. **Only the roadmap's `13/13` is wrong**, and it is wrong in exactly
LL-146's way: an ACCEPTED rendered as a count of passes.

A second point compounds it, and it is the one worth acting on. The criterion names `T155–T161` as a
*mandatory* regression gate — but per **A-5**, `T157`–`T160` have never been run to a verdict in
their own milestone and `T161` has no body. **The gate cites a set that was never green to begin
with**, so even a TASK-243 re-run would not restore a baseline that does not exist. The design doc
half-noticed this ("the design's range overshoots by one") without noticing the larger half.

**What would settle it.** Re-word the roadmap line to `12/13 + 1 ACCEPTED (T155-T160 SKIP,
blocked-external TASK-243)`; and land A-5 first, since this gate is downstream of it.

---

### B-2 — M-TOUCH-CAPTURE: an honest SKIP with no owner, no date, and no re-run in fifteen weeks

| | |
|---|---|
| Criterion | scrollbar-capture leg; the design defers its criteria wholesale — `docs/architecture/designs/M-TOUCH-CAPTURE-slider-input-capture.md:204-206` says only *"See TASK-102"* |
| Closing record | `docs/project/roadmap.md:520` — *"done … `T149/T150/T151/T153/T154` PASS; `T152` **SKIP [CONDITIONAL]** queue < 6"* |
| Oracle actually cited | `T152`, `docs/verification/test_plan.md:1462-1481` |
| Disposition | **DEFERRED — outstanding observation, unowned** |

The header is candid; the task rows are candid three times over (`tasks-archive.md:56`, `:70`,
`:83`, `:87` — *"T152 is the only pending item"*). Nothing here is hidden. What is missing is
LL-146 rule 4's other half: **the SKIP names a re-run condition — *"Re-run when Spotify queue has ≥
6 tracks loaded"* (`test_plan.md:1480`) — and that re-run is recorded nowhere as having happened, has
no owner and no due date.** This is the heatmap review's shape (LL-146 case 3), one severity milder
because the SKIP is environmental rather than harness breakage, so it does at least fall under a
"conditional" limb.

The criterion it carries is real: `T152` is the only id covering scrollbar-strip capture drifting
into the content area, and `T149`–`T151`/`T153`/`T154` cover the POSBAR and VOLUME sliders, not that
path.

**What would settle it.** `T152` is in `build_all_tests()` and needs only a ≥6-item queue —
`set queue N` (the debug injection recorded in project memory) seeds exactly that snapshot without a
Premium account. One targeted run, or an explicit ACCEPTED with an accepter and a date.

---

### B-3 — M-SETTINGS-001: four deferred observations under a "done" header

| | |
|---|---|
| Criteria | six section implementations plus the new-items batch, `docs/project/roadmap.md:480-499` |
| Closing record | `docs/project/roadmap.md:484` — *"done (2026-06-06/07 — fd93679, c07c903)"* |
| Oracles actually cited | the bullet list at `roadmap.md:485-497` |
| Disposition | **partly MET, partly DEFERRED — the bullets say so; the header does not** |

The body under the header carries four self-declared gaps in five lines:

- *"Cal back-tap cancel: `T-CAL-BTAP-01/06` PASS; **T-02..05 deferred** (require physical corner taps)"* (`roadmap.md:489`)
- *"Cal history display: implemented; **visual DUT check deferred**"* (`roadmap.md:490`)
- *"KeyboardWidget ACT_CANCEL: implemented; **BLOCKED-PHASE2 for full VE**"* (`roadmap.md:491`)
- *"TouchDebugOverlay: implemented; **visual DUT check deferred**"* (`roadmap.md:492`)

Plus four open polish tasks named in the same entry, two of which (`TASK-152`/`TASK-154`) are
literally *"visual confirm"* (`roadmap.md:497`).

This is the mildest finding in the sweep and it is included for completeness rather than alarm: the
record is honest at the bullet level and the reader who scrolls sees everything. But the **status
token is `done` with no qualifier**, and LL-146 rule 3 is that a header may not be stronger than its
weakest cell. Four deferred observations and two open visual-confirm tasks make `done` the wrong
token; `done; 4 observations DEFERRED` is the right one.

**What would settle it.** A header re-word. No new evidence is needed to make the record accurate —
only to make the criteria met, which is a separate and lower-priority question.

---

## 4. Calibration — does this method rediscover the five known cases?

The sweep was run as if the five were unknown: extract every criteria section, resolve the closing
record, resolve the cited id's body, apply the subject-noun filter, read before flagging. The five
were then compared against what the method produced.

| Known case | Rediscovered? | By what step, and what the method saw |
|---|---|---|
| M-CLOCK-STYLES (LL-146 case 1) | **Yes — A-class** | Criteria section `M-CLOCK-STYLES.md:626-633` is five pixel/interval claims; the coverage table `regression_suite/m-clock-styles.md` § Exit criteria coverage names the oracle for each as "`set clockStyle <x>` accepted, readback matches". Subject *tube position* vs oracle *settings byte* — flagged on the first pass, before reading the 2026-09-06 annotations |
| M-PLANERADAR (case 2) | **Yes — A-class for 1/6, B-class for 3/4** | `M-PLANERADAR-plane-radar-app.md:324`/`:330` say *render*; `regression_suite/m-planeradar-dut.md` test inventory gives `prAircraftCount` as the oracle for both. Criterion 3's cited id is a SKIP row in the same table; criterion 4's soak is disclaimed in the doc's own VE design notes. The severity split the method produced matches the human ruling's split exactly |
| Heatmap reliability review (case 3) | **Yes — but by a different limb** | The subject-noun filter does *not* fire here (no oracle is blind to its subject — this is the point LL-146 makes about it being a different failure mode). It was caught by the second filter this sweep applies: **resolve every cited id to a verdict**. `T217` resolves to SKIP-on-harness-bug with a re-run that resolves to nothing (`regression_suite/heatmap-reliability-ve-review.md` § T217). Same limb that caught A-2 and A-5 |
| M-CLOCK-THEMES (case 4) | **Yes — A-class** | Caught deliberately by the design-doc arm: the milestone has no regression-suite document, so only `M-CLOCK-THEMES.md:127-128` states the criterion (*"DUT-verified via `screendump` … actual on-device colour"*), and the close record is a human eyeballing eight captures. **A-4 (M-VIS-ATLAS) is the same shape found by the same step**, which is the calibration working |
| M-PR-LOCATIONS (case 5) | **Yes — B-class** | `regression_suite/m-pr-locations-dut.md` test inventory, `T_PRL_07` row: the reflash leg's oracle is the literal string *"implicit (many reflashes this milestone, always correct)"*, and `T_PRL_01b` is a PASS cell whose own note says one leg was not run. The method flags "an oracle that is a recollection" under the same read-the-cited-body step |

**Result: 5 of 5 rediscovered.** One (the heatmap review) is *not* caught by LL-146's subject-noun
heuristic and needs the second filter — which is itself a useful confirmation that the heuristic
alone would have a blind spot, exactly as LL-146 predicts when it observes the five are "not one
failure mode".

**What the calibration also shows about the sweep's sensitivity.** The two filters that actually
produced findings are:

1. *subject-noun mismatch* — A-1, A-3, A-4, A-6, A-7 (and cases 1, 2, 4);
2. *cited id does not resolve to a verdict* — A-2, A-5, B-1, B-2 (and case 3).

A third filter fired once and is worth naming because nothing in LL-146 anticipated it:
**3. *the citation does not resolve to the right document at all*** — A-3, where `TASK-053d` is a
task in another milestone. Nothing mechanical would have caught that; `run/check-docs` C6 binds test
ids in tables, not task ids in prose.

---

## 5. Checked and found sound

A sweep that reports only hits cannot be trusted to have looked. This is the full list of closed
milestones examined and **not** flagged, with the depth of the check stated honestly per row.

**Depth key.** **[O]** = criteria read *and* every cited oracle resolved to a body or a recorded
run. **[M]** = criteria read; they are mechanically self-observing (build succeeds, grep is clean,
file exists, hash matches, flash delta measured) so the oracle is the criterion. **[N]** = criteria
read; the milestone states no criteria that survive the subject-noun filter — nothing to mismatch.

### 5.1 Sound with the check fully resolved [O]

| Milestone (roadmap line) | Why it is sound |
|---|---|
| M-TASKBAR-FEEDBACK (`roadmap.md:981`) | **The model close in this repo.** Its results table (`M-TASKBAR-FEEDBACK.md:383-392`) puts each criterion beside the id that observed it, and where an oracle could not exist it says so and escalates: D1 (`:443-450`) states *"'Visibly highlights' cannot be asserted over serial"*, names the compensating evidence, and records **"RATIFIED (human, 2026-07-07)"** with the date. That is LL-146's ACCEPTED, three months before LL-146 |
| M-WR-AUDIO-TASK (`roadmap.md:955`) | E1–E5 each carry a measured number and a named window (`M-WR-AUDIO-TASK.md:429-517`); E2's harness FAIL is attributed to a verifier defect (TASK-292) *and* ratified rather than quietly re-scored; E3 is a **scoped** pass with the residual gap filed as TASK-291. The E0 baseline's own two failed attempts are kept in the doc (`:361-377`) rather than deleted |
| M-HOME-LOCATION (off-roadmap; `M-HOME-LOCATION.md:225-234`) | `T-HOME-01`…`06` all resolve to dated PASS entries with the observation quoted (`test_plan.md:4979-5030`). T-HOME-04's migration legs were run against three crafted fixtures with the exact booted values recorded; T-HOME-05 records a `divKm:1437` read and the deliberate Cancel. The one gap (manual-path divergence hint) is dispositioned in writing as an accepted v1 limitation |
| M-WEBRADIO-SETTINGS (off-roadmap) | `T-WRSET-01`…`06` resolve to dated verdicts; `T-WRSET-03` (`test_plan.md:4938`) records a transient empty read, attributes it to the TASK-284 rate-limit pattern, waits, re-reads, and states both observations. Attribution is argued, not asserted |
| M-PR-LOCATIONS, non-flagged legs (`roadmap.md:1143`) | `T_PRL_07`'s flash-fs leg is a byte-exact `cmp` of an esptool backup and restore; `T_PRL_02/03/05/09` observe the fields their claims are about. (The two weak cells are LL-146 case 5, already ruled.) |
| M-SRCLAYOUT (off-roadmap; `M-SRCLAYOUT-main-decomposition.md:704-730`) | Stage D names the 27-id battery it ran, why those ids (they hit the relocated members), the one skip and its external cause — and then explicitly refuses to overclaim: *"`T_SRC_05`/`T_SRC_06` and D9's ≥3-run baseline **remain owed** — this battery is targeted evidence, not a behaviour-neutrality baseline, and it should not be recorded as one"* (`:729-730`). That sentence is the whole of LL-146 rule 3, written unprompted |
| M-STOCK-VE-STRESS (`roadmap.md:679`) | The criterion *is* a counter assertion (`T204`, 3-cycle alternating stress with counter drain); subject and oracle are the same object |
| M-DATATASK-STREAM-PARSE (`roadmap.md:663`) | Closed on `T186`–`T188` plus a recorded reversal (weather/crypto reverted to `getString()` because HTTPClient on espressif32@6.9.0 cannot dechunk via `getStream()`); the negative result is in the status line, not hidden |
| M-CONN (`roadmap.md:210`) | Each of the five criteria (`M-CONN-connection-health.md:42-46`) has a matching observation in the status line with the actual numbers — F1 quotes `render_age 60003→17251 ms`, F2 quotes 10/10 polls, F3 the cooldown behaviour |
| M-TESTBASE phase-1 player gate (`regression_suite/player-gate-baseline.md`) | Pass set is **pre-declared** and machine-read, `SKIP` is a *declared* skip whose FAIL is still a regression (`:2`), and the 2026-08-31 `T_PMT_04` divergence is appended without rewriting the baseline row — *"rewriting a past measurement destroys the only thing a baseline is for"* |
| M-TESTARCH order baseline (`regression_suite/testarch-order-baseline-task566.md`) | Reports 7.1 % non-stationarity as the headline over the totals, names two undeclared flake candidates without adjudicating them, and states outright that `run/player-gate` is order-blind for this switch. It refuses to conclude "safe" |

### 5.2 Sound because the criteria are mechanically self-observing [M]

M2 skin asset pipeline (`roadmap.md:81`) · M-HITZONES (`:116`) · M-PREVIEW-FRAMEWORK (`:912`) ·
M-APP-REGISTRY (`:342`) · M-SHELL-LAYOUT (`:274`) · M-RESTRUCTURE (`:300`) · M-NOART (`:243`, the
link/grep/preprocessor legs) · M-SERIALDBG (`:176`, command-response legs) · M-SETUP-WIZARD (`:747`,
E1–E7 are file-content and guard-behaviour assertions) · M-COUNTRY-PICKER (off-roadmap; bake
determinism + `run/check`) · M-ROWGATE · M-LEVELS · M-MEMPLAN · M-DOCLIFE (`M-DOCLIFE-check-docs-spec.md:385-397`,
whose E1/E3/E4/E6 are unusually strong — each names the *negative* control that stops a `return 0`
stub passing) · M-TOOLING.

For these the criterion and the oracle are the same artifact: `sha256sum -c golden.sha256` either
matches or does not; a grep returns hits or none; a build links or fails. There is no subject to be
blind to.

### 5.3 Sound in the sense that nothing survives the filter [N]

M0 · M1 · M4 · M-CHROME · M-LIST · M-PERF · M-IO · M-LOG2 · M-SYNC · M-DRIFT · M7 ·
M-CONN-HTTP11 · M-LIST-v3 · M-MULTIAPP · M-TOUCH-UX · M-SETTINGS-WIFI-P2 · M-TASKBAR-SCROLL ·
M-AQUARIUM · M-AQUARIUM-DEMOSCENE · M-AQUARIUM-CRAB · M-TASKBAR-ICONS · M-ICON-PIXELART ·
M-SETTINGS-STYLE · M-CLOCK-NIXIE · M-CLOCK-VFD · M-CLOCK-FLIP · M-WR-CONNECT-ASYNC.

**Two honest caveats on this group.** First, several of these *do* carry visual criteria that were
closed on DUT eyeballs — M3 (`roadmap.md:32`, *"DUT visual verify confirmed"*), M5, M-VIS,
M-UI-POLISH (`M-UI-POLISH-fidelity.md:38-41`, three DUT render claims), M-LIST-v2
(`M-LIST-v2-pledit-skin.md:38-41`, four DUT claims including two exact y-coordinates). They are not
flagged individually **not because they are better evidenced than A-4, but because they are the same
finding repeated**: the project had no pixel oracle before ADR-064, so every 2026-05 render claim
rests on a person looking at the screen. Flagging fifteen instances of one systemic condition would
bury the seven that are specific and actionable. **If the human wants that class counted rather than
characterised, it is roughly 15 further criteria across 5 milestones, all of the A-4 shape, all
settled by the same `get sig` mechanism.**

Second, M-ICON-PIXELART and M-CLOCK-NIXIE/VFD/FLIP were checked shallowly — their criteria are
decision-and-record shaped (*"Human picks A/B/C; Architect records the decision as an ADR"*,
`M-ICON-PIXELART-native-icon-authoring.md:206-207`) rather than measurement shaped, so the filter
had nothing to bite on. That is an absence of evidence of a defect, not evidence of its absence.

---

## 6. Coverage gaps

### 6.1 Closed milestones with no regression-suite document

LL-146's structural point is that a milestone closed **without** a suite document is *less* likely to
have been checked, not more — M-CLOCK-THEMES was caught only because someone happened to read a
design doc's exit criteria. The sweep covered those deliberately. The count:

| | Count |
|---|---|
| Milestones reading done/closed in `roadmap.md` | 55 |
| — with **any** document in `docs/verification/regression_suite/` | **6** |
| — of those 6, documents that are *results* rather than pre-implementation design reviews | **4** |
| — **with no regression-suite document at all** | **49** |

The six, and what each actually is:

| Suite document | Milestone | Results, or review? |
|---|---|---|
| `regression_suite/m-clock-styles.md` | M-CLOCK-STYLES | results (now fully re-recorded DEFERRED) |
| `regression_suite/m-pr-locations-dut.md` | M-PR-LOCATIONS | results |
| `regression_suite/app-settings-wire-001.md` | M-SETTINGS-APP-WIRE | **specification only — all 27 rows `planned`** (see A-1) |
| `regression_suite/settings-001-new-items.md` | M-SETTINGS-001 | results (partial; see B-3) |
| `regression_suite/touch-capture-ve-review.md` | M-TOUCH-CAPTURE | **pre-implementation design review — contains no results** |
| `regression_suite/velocity-scroll-ve-review.md` | M-LIST-v4 | **pre-implementation design review — contains no results** |

So of 55 closed milestones, **four** have a document recording what was actually observed, and one of
those four (M-SETTINGS-APP-WIRE) records that nothing was. The remaining nine suite documents in the
directory belong to milestones that are *not* closed (M-WEBRADIO ×3, M-WINAMP-PLAYER, M-TESTARCH ×2,
M-TESTBASE) or to a sub-feature review (the heatmap review, `README.md`).

**The correlation LL-146 predicted holds, and it is strong.** Six of the seven A-class findings are
in milestones with no results document (A-2 …A-7); the seventh, A-1, is in a milestone whose
"suite document" is an unexecuted specification. **No A-class finding was made in a milestone that
has a real results document** — those produced only B-3, the mildest finding in the sweep. Writing
down what was observed appears to be the single strongest predictor of having observed it.

### 6.2 Classes of close this sweep did not examine

Stated so the next reader knows the boundary rather than inheriting a false sense of completeness.

1. **The pre-ADR-064 visual-claim class, counted only in aggregate.** ~15 further criteria across M3,
   M5, M-VIS, M-UI-POLISH and M-LIST-v2 are A-4's shape and are characterised in §5.3 rather than
   itemised. This is a deliberate reporting choice, not a gap in the looking — but if the project
   wants the acceptance list LL-146 rule 5 calls for to be *complete*, these belong on it.
2. **In-progress milestones.** M-WEBRADIO is the sharpest instance and is out of scope only on a
   technicality: `roadmap.md:839` reads *"in progress"*, while `regression_suite/m-webradio-dut.md`'s
   exit-criteria coverage table still reads **"open — awaiting DUT run"** on nine of ten rows, and
   two audible criteria are DEFERRED for want of a speaker. If that milestone is ever closed, its
   coverage table is where the close must be argued — not the `wr-gate` result.
3. **ADR acceptance records.** ADRs frequently carry acceptance conditions in prose
   (ADR-045's MVP exit criterion, ADR-052's sign-off lockstep). Those were not swept; only design-doc
   and roadmap criteria were.
4. **Cross-feature matrix edges.** `cross_feature_matrix.yaml` X-ids are cited as evidence in several
   closes (X026/X030/X032/X035 in M-HOME-LOCATION criterion 4). Whether an X-edge's own verification
   is real was not checked.
5. **The task boards' own close notes**, except where a milestone's roadmap line pointed into them
   (A-3, A-4, A-5 all did). `tasks-archive.md` is ~19 800 lines and was searched, not read.

### 6.3 Is the sweep complete?

**For the question as posed — every closed milestone's stated exit criteria against its cited
oracles — yes, with the §6.2 boundary stated.** All 55 closed roadmap milestones and 9 off-roadmap
closes were examined; all 61 in-scope criteria sections were read; all 74 criteria that survive the
subject-noun filter were individually compared against their cited oracle; the five known cases were
independently rediscovered.

**Whether the *class* is now countable — not yet, and this is the important qualifier.** The
acceptance list LL-146 rule 5 asks for cannot be generated from this document, because the record
still has no machine-readable relation between a criterion and the oracle that closed it. This sweep
is a snapshot produced by reading, and it will be stale the next time a milestone closes. What it
buys is a **starting inventory**: 10 findings here, plus the 5 known cases, plus ~15 aggregate
pre-ADR-064 visual criteria — call it **30 criteria the project is knowingly or unknowingly
carrying**. Keeping that number honest needs the closing-ritual checklist LL-146's BP candidate
proposes (§Mechanisation: *"the cheapest first step is not a gate but a checklist line"*), not a
second sweep.

**The one thing that would make a fourth accident unlikely** is narrower than a gate and cheaper than
either: a rule that a milestone may not close while any id it cites has a `test_plan.md` status of
`written`, `planned`, `ready to run` or `SKIP` without a named owner and date. That single check,
applied mechanically to the citation list, would have caught A-1, A-2, A-5, B-1, B-2 and LL-146's
case 3 — six of the fifteen — with no judgement required and no new firmware.

---

## 7. Disposition

**Nothing in this document is a ruling.** No milestone status was edited, no cell re-scored, no task
filed. Every finding is stated as *what the evidence on file does and does not settle*, in LL-146's
vocabulary, for the human to rule on as the last five were.

**Escalated to:** @PM (roadmap status lines A-1…A-7, B-1…B-3) and @VE (the coverage tables and the
outstanding observations named in A-2, A-5, B-2).

**Owner of this document:** @VE. **Date:** 2026-09-06.
