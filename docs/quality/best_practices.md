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

### BP-006 — Visual sign-off for range-dependent renderers must cover zero, max, and one intermediate state

**Adopted from**: LL-025  
**Date adopted**: 2026-05-23  
**Rule**: Any renderer whose output depends on a runtime value (scroll offset, volume, position) must be sign-off tested at three states — minimum (0), maximum, and one mid-range value — before the implementing task is closed. PM records user sign-off using the user's exact words, not a paraphrase.  
**Rationale**: "Correct at rest" does not validate range-dependent code paths. A bug in the scrollbar thumb X offset was missed because sign-off was given only at the resting/zero state; the visual defect only appeared during scrolling. Additionally, PM paraphrasing "moves to the right" as "Y position wrong" misfiled the axis, wasting a full audit cycle and multiple flash iterations. Exact-quote policy eliminates the paraphrase error class.  
**Applies to**: VE (define test cases covering min/max/mid before task closes), PM (record user sign-off verbatim, never paraphrase visual bug descriptions), Developer (do not close range-dependent renderer tasks without VE sign-off on all three states)

---

### BP-007 — Reference image consumed → paired visual validation item required

**Adopted from**: LL-026  
**Date adopted**: 2026-05-23  
**Rule**: Any element whose position, size, or colour is derived from a reference image must have a paired VE or audit item that validates rendered output against that image before the task is closed. The validation item is filed at the same time the reference image is first cited in the design.  
**Rationale**: Reference images contain the ground-truth pixel data needed to verify placement. When validation is skipped, implementation values are guessed and the human is forced to iterate through flash-observe cycles to converge on the correct pixel offset. This is expensive and degrading. Concrete incident: `resource/winamp_reference_cropped.png` was available from project start and examined by R&D (TASK-075), but no VE item was filed for thumb X placement; 5+ flash cycles with human pixel feedback were required to arrive at `PLEDIT_THUMB_X_INSET = 4`. A single image measurement would have produced the correct value immediately.  
**Applies to**: R&D Engineer (flag reference images as requiring paired validation when cited in reports), Architect (do not finalise a design that cites a reference image without a linked VE validation item), VE (own the validation item; measure from the image, do not accept "looks right"), PM (reject task close if reference image was cited and no validation item exists)

---

### BP-008 — Run check_build.sh before and after every structural change

**Adopted from**: restructure pre-gate (2026-05-24)
**Date adopted**: 2026-05-24
**Rule**: Run `./check_build.sh` from the project root before starting any structural change (file moves, `#include` edits, entry-point rewrites) and again after completing it. Do not commit a structural change that fails the script.
**Rationale**: The DUT-based test suite requires physical hardware and cannot catch compile errors during a refactor. `check_build.sh` is the only automated gate that runs on the local machine without a board. When it was first run, it immediately surfaced a pre-existing compile error (`PLEDIT_THUMB_X_INSET` undefined) that had gone undetected because no build check existed. Without this gate, `#include` breakage, missing constants, and symbol errors accumulate silently until someone next flashes the board.
**Applies to**: Developer (run before/after every structural change), PM (do not close restructure tasks without confirming check_build.sh exit 0 on the final state)

### BP-009 — Structural refactors must include a grep-for-old-paths step and tool-script smoke test

**Adopted from**: LL-029
**Date adopted**: 2026-05-24
**Rule**: Any task that moves a file or directory must include an explicit sub-step: `grep -rn "OldPath" movedDir/` before the task is closed. For Python tool scripts, confirm `python3 -c "import module"` from the new location. For shell scripts, confirm `--help` (or a dry-run invocation) completes without `No such file or directory` errors.
**Rationale**: Path strings inside scripts are structural coupling to the file's old directory context. A file move that does not update internal path strings is an incomplete migration — equivalent to leaving a broken `#include`. The class of breakage is silent until the first consumer runs: no compile error, no git warning, no `check_build.sh` failure. M-RESTRUCTURE moved six scripts with stale path strings; the T102 harness crash on 2026-05-24 was the first consumer to hit it. A one-command grep would have caught all six in under 10 seconds.
**Applies to**: Developer (add grep + smoke-test step to every restructure task), PM (reject restructure task `done` without grep confirmation or smoke-test evidence), Architect (include the grep step in any source-ownership migration design doc)

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