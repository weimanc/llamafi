# Gating-class flake exceptions — the R37 ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_flake_class.py` (findings **F1**, **F7**) ·
> Opened **2026-09-04**, reopened **2026-09-12** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md)
> R37, TASK-623; extended by TASK-595's C-7 both-directions sweep

## What this file is

`check_flake_class.py` asserts that no id whose class can block a run — RIG, HEALTH or CORE — also
carries a declaration in [`flaky.yaml`](flaky.yaml) (**F1**), and, since TASK-595, that every real
`flake()` call site in the suite names a declared id (**F7**). Both are the same underlying
contradiction from two directions: a gating class exists to stop the run, and a flake claim that
can resolve `FLAKY-PASS` (declared) or that silently becomes `FAIL: UNDECLARED flake` (undeclared,
bookkeeping instead of the real symptom) both mean the id is not doing what its class promises.

This file previously held exactly one row (`T091`, **F1**) and was deleted 2026-09-04 when TASK-591
retired it by demoting `T091`'s class to FEATURE — see git history for that version. It is reopened
now holding a **different** row, opened by the same TASK-595 sweep that closed the other three F1/F6
findings outright rather than exempting them (see `flaky.yaml`'s own retirement comments for
`T_PLR_17`/`T_PMT_04`/`T_WR_COEX_01`, and the new declarations for `T092`/`T_PLR_07`/`T_WR_EJECT_01`).

**The rules that make this a gate and not an amnesty (unchanged from 2026-09-04):**

1. A row suppresses **one** finding, keyed on `(kind, id)`. No file, family, suite or wildcard
   exemption exists, by design.
2. **A stale row is a BLOCKING failure.** When the finding stops occurring the row must go with it.
   The list can only shrink.
3. Every row needs an owning `TASK-` id and an ISO `since` date. Missing or malformed either is a
   failure, not a skipped row.
4. **Two exemptable kinds today**, both below. F2 (a flake *candidate* on a gating id), F3 (a
   declaration for an id no registry contains), F6 (a declared flake with no call site) and F8 (an
   expired entry) are all at zero and are **not** exemptable — an exemption kind with no rows is an
   invitation to open one.

## The exemptable kinds

| kind | the finding it suppresses |
|---|---|
| `gating-flake` | an id resolving to RIG, HEALTH or CORE that carries a `flaky:` entry — its retry can only ever resolve `FLAKY-PASS`, so it can never set the blocker its class exists to set |
| `undeclared-flake-call` | a real `flake()` call site for an id resolving to RIG, HEALTH or CORE, where the id genuinely cannot be **either** declared (it would immediately become a `gating-flake` F1) **nor** trivially converted to a plain `fail()` without a decision this sweep could not make host-only |

## Ledger

Owner = the task that will resolve the contradiction, not (necessarily) the task that opened the row.

| id | kind | why it is not resolved today | owner | since |
|---|---|---|---|---|
| `T084` | undeclared-flake-call | CORE by its own `cls_reason` (`shell.py`): "the only id that tests the `set X` -> `get X` round trip ITSELF" — around thirty other ids inject state through that mechanism and assert on the read-back, so T084 is the premise test for all of them, not a candidate for casual demotion the way `T091`/`T092` were (nothing depended on *them* specifically). Its four failure paths call `flake()` and are undeclared (**F7**) — but simply declaring it would immediately trip **F1** (a gating-class id carrying a `flaky:` entry), the identical contradiction TASK-591 resolved for `T091` by demoting it. `T-CDWN-02` is the closest precedent (same shell-poll/reconnect-race family, same CORE-vs-flake question) and TASK-626 resolved it by **converting** the `flake()` calls to `fail()`/`unmet()` while keeping CORE — but doing the same for T084 needs a DUT run to confirm the round-trip genuinely never races in practice (this rig's live TASK-243 403 already degrades the poll path the "KNOWN INTERMITTENT" comment blames), which a host-only registry sweep cannot produce. Two options stay open, neither closed by this ledger: (a) convert T084's four `flake()` calls to `fail()` per the T-CDWN-02 precedent, keeping CORE — needs hardware verification; (b) demote T084 to FEATURE like `T091`/`T092`, then declare it — but its own `cls_reason` argues this loses real coverage for the ~30 dependent ids, unlike `T091` where nothing depended on it. | TASK-595 | 2026-09-12 |

## Retirement

This row is deleted the moment either option above is actually taken and verified on hardware:

* **Option (a).** T084's `flake()` calls become `fail()`/`unmet()` (T-CDWN-02's pattern), a DUT run
  confirms the set/get round trip does not spuriously race under a live TASK-243 403, and T084 stays
  CORE with no `flaky.yaml` entry. **F7** goes quiet on its own — no declaration, no undeclared call.
* **Option (b).** T084 is demoted to FEATURE with a written `cls_reason` (TASK-591's pattern) and
  then declared in `flaky.yaml` with owner/task/`review_by`. **F7** goes quiet because the id is no
  longer undeclared; **F1** stays quiet because the class is no longer gating.

Either way the resolution needs a DUT session this host-only sweep did not have, so the row stays
until one runs.
