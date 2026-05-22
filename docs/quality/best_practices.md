# Best Practices

> Owner: Quality Manager

Entries promoted from `lessons_learned.md` on explicit human approval. All agents read+apply. QM owns file, invalidates outdated practices.

### BP-001 — Verify derived values before adopting into specs

**Adopted from**: LL-020  
**Date adopted**: 2026-05-16  
**Rule**: Any R&D report value that is *computed* from measurements (format conversions, scale factors, timing calculations) must include the derivation formula or a one-line verification command; the Architect runs that command before adopting the value into a design doc.  
**Rationale**: Measured and computed values can coexist in the same table and look equally authoritative. Computed values can silently be wrong — 16/16 RGB565 colour values in M-VIS were incorrect due to a misapplied conversion formula, caught only on DUT visual inspection. A 30-second Python check at spec time would have prevented the bug.  
**Applies to**: R&D Engineer (label columns as measured vs derived; include formula), Architect (do not adopt a derived value without running the verification)

---

### BP-002 — Commit a canonical bake script alongside generated artifacts

**Adopted from**: LL-021  
**Date adopted**: 2026-05-17  
**Rule**: For every bake tool that produces committed generated artifacts, commit a companion shell script containing the exact invocation. The script is the canonical recipe; update it in the same commit as any regenerated artifact.  
**Rationale**: Bake flags (boost, smoothing, offsets, frame trimming) are invisible inside the generated C/header files and are not consulted from commit messages before re-running a tool. A shell script is a file — it gets read, diffed, and updated as part of normal workflow.  
**Applies to**: Developer, R&D Engineer

---

### BP-003 — File a separate bug task for every known regression at close time

**Adopted from**: LL-022  
**Date adopted**: 2026-05-22  
**Rule**: A task with a documented functional regression in its notes must not be closed as `done`. File a separate bug task at close time — owner, status `planned`, reference to parent task — before marking the parent done.  
**Rationale**: Prose caveats in task notes have no owner and no deadline. They are not surfaced by any dashboard or review step. A known, identified fix can sit unresolved for days and return to the user as a re-reported bug. A task entry creates pressure and traceability. Concrete incident: TASK-021 closed `done` with a 5-line fix named in the notes; bug returned to user 6 days later.  
**Applies to**: Developer (file the bug task before closing), PM (reject `done` status if a regression caveat has no associated bug task)

---

### BP-004 — Mirror every physical-touch branch in `injectTouch()` in the same commit

**Adopted from**: LL-023  
**Date adopted**: 2026-05-22  
**Rule**: Any new action branch added to `checkForInput()` (physical touch path) must be mirrored in `injectTouch()` in the same commit. Both methods carry a co-location comment enforcing this invariant.  
**Rationale**: `injectTouch()` is the VE harness's only path for injecting touch events. A branch absent from `injectTouch()` silently falls to DEADZONE — the harness dispatches `ACT_FORCE_POLL` and reports no error, so tests can appear to pass while the action under test never fires. Divergence is invisible without a running test. Concrete incident: PLEDIT tap branch missing from `injectTouch()` for 7 days; T115's first run exposed it via `'hit':'DEADZONE'`.  
**Applies to**: Developer

---

### BP-005 — `test_ids: []` on an implemented feature requires a VE task before `done`

**Adopted from**: LL-024  
**Date adopted**: 2026-05-22  
**Rule**: An `implemented` feature in `feature_inventory.yaml` with `test_ids: []` must have a corresponding VE task in `tasks.md` (status at least `planned`) before the feature is declared `done` at the roadmap level. PM files the VE task at feature close; VE populates `test_ids` when tests pass.  
**Rationale**: `test_ids: []` is a visible signal in the YAML but creates no work item and no deadline. VE audit notes recorded only as YAML prose age silently — no owner, no trigger to act. A tasks.md entry gives the gap a deadline and an owner. Concrete incident: `playlist-001` test gap open 7 days with only a YAML annotation; tests found an additional infra bug (`injectTouch` divergence) when finally written.  
**Applies to**: PM (file VE task at feature close), VE (own and close the task), Developer (do not ship features expecting `test_ids` to be filled in "later")

---

## Entry Format

```
### BP-001 — [Title]
**Adopted from**: LL-XXX
**Date adopted**: YYYY-MM-DD
**Rule**: The actionable guidance (one clear sentence where possible)
**Rationale**: Why this matters
**Applies to**: Developer | VE | PM | QM | All
```