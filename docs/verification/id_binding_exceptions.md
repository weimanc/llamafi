# Id-binding exceptions — the C6 ledger

> Owner: **@VE** · Machine-read by `app/tools/check_docs.py` (check **C6**) · Opened **2026-08-18**
> Umbrella sweep task: **TASK-510** (apply the P0 convention repo-wide)

## What this file is

`run/check-docs` gate **C6** asserts that the executable test registries and the VE-owned plan
describe the same set of tests (M-TESTARCH §6). It landed on a corpus that already held **49**
violations. This file grandfathers exactly those 49, dated and task-owned, so that C6 can be
**blocking** for everything else from day one.

**The rules that make this a gate and not an amnesty:**

1. A row here suppresses **one** finding, keyed on `(kind, id)`. Nothing is suppressed wholesale —
   no file, directory, family or wildcard exemption exists, by design.
2. **A stale row is a BLOCKING failure.** When an id here is registered properly, C6 fails with
   `stale exception … delete this row` until the row is removed. The list can only shrink.
3. **`mismatch` is not an exemptable kind.** A row of kind `mismatch` is rejected by the parser as
   an error. A doc row marked `impl` whose id has no body is the exact defect C6 exists to catch
   (LL-140: "covered" read as "green"); an exemption for it would be an exemption from the point.
4. Every row needs an owning `TASK-` id and an ISO `since` date. Missing either is a failure.

## The two exemptable kinds

| kind | the finding it suppresses |
|---|---|
| `orphan` | an id in an executable registry with **no entry** anywhere in `docs/verification/` — it runs, and the plan has never heard of it |
| `undeclared` | an id **with** a doc entry, none of which declares a status (no `Status`/`Result`/`Outcome` column cell, no `**Status**:` field) |

## Ledger

Owner = the task that created the test and can write its plan row, not the sweep task.

| id | kind | why it is not bound today | owner | since |
|---|---|---|---|---|
| `T_FLK_01` | orphan | flaky-set policy gate, host-side; the whole family landed after the last plan sweep and appears **nowhere in `docs/` at all** | TASK-520 | 2026-08-18 |
| `T_FLK_02` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_03` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_04` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_05` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_06` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_07` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_08` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_09` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_10` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_11` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_12` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_13` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_14` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_15` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_16` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_17` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_18` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_19` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_20` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_21` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_FLK_22` | orphan | as `T_FLK_01` | TASK-520 | 2026-08-18 |
| `T_PLE_WR_155` | orphan | WebRadio PLEDIT battery mirroring `T155`–`T160`; specified and result-of-record in the Architect-owned M-PLEDIT-ABSTRACTION design, never registered in the plan | TASK-411 | 2026-08-18 |
| `T_PLE_WR_156` | orphan | as `T_PLE_WR_155` | TASK-411 | 2026-08-18 |
| `T_PLE_WR_157` | orphan | as `T_PLE_WR_155` | TASK-411 | 2026-08-18 |
| `T_PLE_WR_158` | orphan | as `T_PLE_WR_155` | TASK-411 | 2026-08-18 |
| `T_PLE_WR_159` | orphan | as `T_PLE_WR_155` | TASK-411 | 2026-08-18 |
| `T_PLE_WR_160` | orphan | as `T_PLE_WR_155` | TASK-411 | 2026-08-18 |
| `T_PRI_01` | orphan | dr-damped motion-smoothing continuity; graduated from EXP-014 straight into the runner, plan row skipped | TASK-357 | 2026-08-18 |
| `T_PRM_01` | orphan | `prPollSec` round-trip; specified in M-PR-MOTION, plan row skipped | TASK-355 | 2026-08-18 |
| `T_PRM_02` | orphan | as `T_PRM_01` | TASK-355 | 2026-08-18 |
| `T_TBFB_01` | orphan | taskbar tap-feedback battery; specified in M-TASKBAR-FEEDBACK, plan row skipped | TASK-279 | 2026-08-18 |
| `T_TBFB_02` | orphan | as `T_TBFB_01` | TASK-279 | 2026-08-18 |
| `T_TBFB_03` | orphan | as `T_TBFB_01` | TASK-279 | 2026-08-18 |
| `T_TBFB_04` | orphan | as `T_TBFB_01` | TASK-279 | 2026-08-18 |
| `T_TBFB_05` | orphan | shell-level post-gesture cooldown; same family, different owning task | TASK-294 | 2026-08-18 |
| `T_WR_VIS_01` | orphan | real-VU battery (`vu-002` / X043); specified in M-WEBRADIO-REAL-VIS, plan row skipped | TASK-369 | 2026-08-18 |
| `T_WR_VIS_02` | orphan | as `T_WR_VIS_01` | TASK-369 | 2026-08-18 |
| `T_WR_VIS_03` | orphan | as `T_WR_VIS_01` | TASK-369 | 2026-08-18 |
| `T_WR_VIS_04` | orphan | spectrum battery (`vu-003` / X044); specified in M-WEBRADIO-REAL-VIS-SPECTRUM, plan row skipped | TASK-387 | 2026-08-18 |
| `T_WR_VIS_05` | orphan | as `T_WR_VIS_04` | TASK-387 | 2026-08-18 |
| `T113` | undeclared | archived plan entry with no `**Status**:` field. `test_plan-archive.md` is a historical record but is **not** in `check_docs.EXEMPT_BASENAMES`, so C6 scans it — see the finding note below | TASK-060 | 2026-08-18 |
| `T_CC_01` | undeclared | M-ARCH reserved family; the disposition table carries a VE verdict column, not a status column | TASK-473 | 2026-08-18 |
| `T_CC_02` | undeclared | as `T_CC_01` | TASK-473 | 2026-08-18 |
| `T_CC_03` | undeclared | as `T_CC_01` (VE verdict: DISCARD — the row should go, not gain a status) | TASK-473 | 2026-08-18 |
| `T_CC_04` | undeclared | as `T_CC_03` | TASK-473 | 2026-08-18 |
| `T_CC_05` | undeclared | as `T_CC_01` | TASK-473 | 2026-08-18 |
| `T_CQ_01` | undeclared | M-ARCH reserved family; registered as a prose range heading (`T_CQ_01`–`T_CQ_06`), which binds only the first id and declares no status | TASK-458 | 2026-08-18 |
| `T_SRC_01` | undeclared | as `T_CQ_01`; `T_SRC_01` is the ≥3-run behaviour-neutrality baseline, which has no status because it was never taken | TASK-488 | 2026-08-18 |

**49 rows.** Re-count with `python3 app/tools/check_docs.py --no-git` — the C6 summary prints
`N on the ledger`, generated, never transcribed here.

## Findings recorded while building the ledger, not fixed here

- **The orphan set is not random.** Every one of the 41 orphans is *specified* — in an
  Architect-owned design document, or (for `T_FLK_*`) in a task entry. What is missing in all 41
  cases is the VE-owned plan row. This is a one-directional leak: design → code, with the plan
  bypassed. That is the M-TESTARCH §6 claim, confirmed at the mechanism.
- **`T_FLK_01`–`22` appear nowhere under `docs/` at all**, not merely outside `docs/verification/`.
  They are the newest family in the tree. Drift is live, not historical.
- **Range headings bind one id, silently.** `### \`T_CQ_01\`–\`T_CQ_06\`` registers `T_CQ_01` and
  loses five ids. `T_CC_`, `T_SRC_` and `T_CQ_` are all written this way. Expanding these into rows
  is plan work, deliberately not done here — a gate must not be closed by the hand it grades.
- **`test_plan-archive.md` is scanned but is a historical record.** Adding it to
  `EXEMPT_BASENAMES` would silence `T113` correctly, but would also drop it from C1/C5's scanned
  corpus, which is a scope change to three other checks. Left alone; `T113` is on the ledger with
  the reason stated.
