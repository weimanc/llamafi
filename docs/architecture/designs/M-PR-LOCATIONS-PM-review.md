# PM Review — M-PR-LOCATIONS: PlaneRadar location presets + geocode lookup

> Reviewer: Project Manager
> Date: 2026-07-13
> Verdict: **PASS-with-actions**

## Summary

The design is decomposable into clean, small-to-medium tasks with
legible dependency edges. Q1–Q7 are already resolved, the geocode
provider decision is probed and evidenced (not guessed), and the
host-first discipline (preview tool, probe script) is already baked
into the design rather than left for the PM to invent. No external
blocker: Nominatim is unauthenticated OSM infra, unrelated to the
Spotify/TASK-243 Premium blocker that has stalled other lanes. Current
`tasks.md` WIP is light — of the 9 nominally "open" entries, TASK-314
and TASK-257 are already closed in substance per recent commits/memory
and awaiting archival, TASK-255/256/262/270 are a paused R&D-adjacent
memory-budget thread, and TASK-239/241/284 are WebRadio-side. None
compete for the same files this milestone touches
(`settingsStorage.h`, `dataTask.h`/`dataTaskStorage.cpp`,
`appsSection.h`, `planeRadarApp.h`, `preview_planeradar.py`). Capacity
is available.

Verdict is PASS-with-actions, not clean PASS, because of four
sequencing/scope calls the design leaves open that materially change
task shape (below) — none are design defects, they're PM-breakdown
judgement calls the Architect correctly deferred.

## Findings

### 1. M-CERT-ERRCODE companion — pull the minimal hook forward, don't gate on the whole milestone

Design says "companion, not blocking." Literally true, but the geocode
fetcher (TASK-320 below) is a **new** `setCACert()` call site. If it
ships before M-CERT-ERRCODE's `openHttps()` hook lands, it's another
entry on the "audit ~8 call sites" list from that design's own
migration task — pure rework. If the hook lands first, the fetcher is
born reporting `-120` correctly and the audit for the *other* 7 sites
proceeds fully independently on its own track.

**Action:** extract the minimal slice of M-CERT-ERRCODE (the
`openHttps()` `lastError()` check, the `-120` sentinel constant, the
`httpErr()` decode case, the band comment) into its own small task
that lands before the geocode fetcher. The rest of M-CERT-ERRCODE
(hand-rolled-fetcher audit, host build-time preflight hook, offline
expiry check, `--propose-fix`, T_CERT_ERR_01 full DUT verification,
Q1 heartbeat latch) stays that milestone's own task list, tracked and
scheduled independently — it is not on M-PR-LOCATIONS' critical path
and should not block this milestone's DONE state.

### 2. Manual lat/lon entry — separate task, not bundled into the Lookup editor

Q4 resolved manual entry as first-class (not merely a fallback), but
it carries its own open implementation question the design explicitly
punts ("add a numeric layout to KeyboardWidget if Full mode proves
clumsy — decide at implementation"). Bundling it into the same task as
the Lookup-path editor means a UI-widget risk can block shipping the
primary (and probably more-used) Lookup flow.

**Action:** split into two tasks — Lookup-path editor first (ships +
DUT-validates the storage/fetcher/UI spine), Manual-path entry second
(extends the same sub-view, isolated risk on the keyboard-widget
question). This also gives T_PRL_06 (manual entry test) a natural
task home instead of being tacked onto the Lookup editor's test pass.

### 3. Serial-debug hooks — bundle into the tasks that own the state, not a standalone task

The design's serialdbg section reads as one block, but the hooks
don't share a dependency: `get prloc` / `set prloc <i>` / `set prloc
active <i>` need only `PrLocation` storage (no UI, no fetcher); `set
geocode <lat> <lon> [display]` / `set geocode err <code>` need only
`GeocodeResult` (no UI). Making this one downstream task means VE
can't start test-writing against real hooks until UI lands, and it
recreates a "stub hooks bolted on after" pattern the design elsewhere
argues against ("testability designed in, not bolted on").

**Action:** fold `get/set prloc*` into the storage task, fold `set
geocode*` into the fetcher task. Strip-tap hitbox constants
(`PR_STRIP_ROW_*`) are just an implementation detail of the strip task
and reuse the existing M-SERIALDBG touch-injection infra already
built — no new task needed for that leg.

### 4. DUT-session realism — bundle validation, don't reflash per task

Task-per-task DUT need (below) totals 6 of 10 tasks touching the
device. Flashing/validating each independently is unrealistic churn.

**Action:** target 2–3 DUT sessions total: (1) storage + migration +
fetcher + their bundled serialdbg hooks, smoke-tested together; (2)
Lookup editor + Manual editor + strip switcher, exercised together
since they're UI-adjacent and share a settings-nav path; (3) the
consolidated VE gate (T_PRL_01–06 + preflight roster). This mirrors
how M-PLANERADAR's TASK-307..313 gated in phases rather than per-file.

### Other notes (no action needed, recorded for completeness)

- Country-picker UI is correctly out of v1 (Q5) — no task filed for it,
  confirmed nothing in the breakdown below implies one.
- `prLat/prLon` write-through-mirror keeps every existing consumer
  (`planeRadarApp.h`, `appsSection.h`, `run/spiffs push`, the existing
  `m-planeradar-dut.md` suite) compiling and passing unmodified — the
  storage task's regression check should include a pass of the
  *existing* PlaneRadar DUT suite, not only the new T_PRL_04, to catch
  an accidental mirror-sync break.
- Nominatim's `[NETWORK]`-tag test discipline (stub-first, one genuine
  e2e case) already follows the TASK-284/LL-104 lesson — good, no
  action.
- Probe cadence restraint (manual/on-demand, not wired into
  `run/test`) matches the adsb.fi ≥60s precedent — good, no action.

### Descope candidates for v1

- **New KeyboardWidget numeric layout** — don't pre-build. Prototype
  Manual entry with the existing Full-mode alpha keyboard first
  (digits/`-`/`.` are already on it per the design's own hedge); only
  add a dedicated numeric layout if that prototype proves clumsy.
  Keeps TASK-322 (below) small unless proven otherwise.
- **Full M-CERT-ERRCODE** (host build hook, `--propose-fix`, 8-site
  audit, heartbeat latch) — already addressed in Finding 1, restated
  here as a scope line: none of it belongs in this milestone's task
  list.
- Nothing in the PlaneRadar-specific scope itself looks cuttable —
  it's already tightly bounded (4 slots, one provider, radar-only
  switching, no shared home-location plumbing per Q7).

## Proposed task breakdown

Numbering continues from `tasks.md`'s current highest id (TASK-314).
All titles/descriptions are proposed only — `tasks.md` is not edited
by this review.

| ID | Title | Deps | Size | DUT |
|----|-------|------|------|-----|
| TASK-315 | Phase-0: geocode probe script + report (query matrix, URL-encoding, response contract, HTTP/1.0 compat, UA policy, rate behaviour) | — | S | n |
| TASK-316 | Phase-0: preview tool — radar strip layout (label rows, active highlight, N^ removal, empty-slot, degenerate single-slot), eyeball-gated | — | S | n |
| TASK-317 | Phase-0: preview tool — slot-editor screen-flow prototype (slot list, Lookup\|Manual fork, confirm screen; static frames) | — | S | n |
| TASK-318 | M-CERT-ERRCODE minimal slice: `-120 CERT_VERIFY_FAILED` sentinel in `openHttps()` + `httpErr()` decode + band doc (pulled forward as this milestone's prerequisite; rest of M-CERT-ERRCODE stays its own milestone) | — | S | n* |
| TASK-319 | Settings storage: `PrLocation[4]` + `prActiveLoc` + migration seed from `prLat`/`prLon`; bundled serialdbg `get prloc` / `set prloc <i>` / `set prloc active <i>` | — | S/M | y |
| TASK-320 | dataTask geocode fetcher: `enqueueGeocode`/`pollGeocode`, `NOMINATIM_ROOT_CA` roster entry, UA header, URL-encoding, `-96 GEOCODE_NO_MATCH`; bundled serialdbg `set geocode ...` stub | TASK-315, TASK-318 | M | y |
| TASK-321 | Settings UI: Locations sub-view + slot editor, Lookup path (label → country → postcode → spinner → confirm/save/retry/cancel → delete) | TASK-316, TASK-317, TASK-319, TASK-320 | M | y |
| TASK-322 | Settings UI: Manual lat/lon entry path (coordinate-source fork, numeric entry, −90..90/−180..180 validation) | TASK-321 | S | y |
| TASK-323 | Radar strip switcher: remove `N^`, render label rows + active highlight, touch hit-test → switch (write-through, save, repaint/re-project/re-fetch), same-slot no-op guard, `PR_STRIP_ROW_*` constants | TASK-316, TASK-319 | M | y |
| TASK-324 | VE suite: T_PRL_01–06 + Nominatim added to `run/test` cert preflight roster | TASK-320, TASK-321, TASK-322, TASK-323 | M | y |

\* TASK-318 itself needs no dedicated DUT session; it's exercised for
real by TASK-320/321's live-Nominatim legs (T_PRL_01/03) and by
M-CERT-ERRCODE's own T_CERT_ERR_01 later — no double verification
needed here.

Recommended DUT-session grouping (Finding 4): session A = {319, 320,
324's storage/fetcher legs}; session B = {321, 322, 323}; session C =
final consolidated 324 gate. Two-to-three sessions, not six.

## Sequencing diagram (informal)

```
315 ─┐
316 ─┼─┐
317 ─┤ │
318 ─┼─┼──> 320 ──> 321 ──> 322
     │ └──> 323 <───────────┘ (writes same PrLocation storage as 319)
319 ─┴────> 320, 321, 323
                        \
                         └──> 324 (final gate, needs 320/321/322/323 all)
```

## Open questions for human/Architect before scheduling

- Confirm TASK-318's placement — pulling a slice of a sibling milestone
  forward as a hard prerequisite of this one is a cross-milestone
  dependency `tasks.md` doesn't currently have a notation for; PM
  suggests filing it under M-PR-LOCATIONS' task list with a one-line
  cross-reference to M-CERT-ERRCODE rather than duplicating it there,
  but wants sign-off before either roadmap entry is touched.
- Confirm the TASK-321/322 split is acceptable given Q4 already
  resolved manual entry as "first-class" — splitting the task is a
  delivery-sequencing choice, not a re-litigation of that scope
  decision; v1 still ships both before the milestone is DONE.
