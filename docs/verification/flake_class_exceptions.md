# Gating-class flake exceptions — the R37 ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_flake_class.py` (finding **F1**) ·
> Opened **2026-09-04** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R37, TASK-623

## What this file is

`check_flake_class.py` asserts that no id whose class can block a run — RIG, HEALTH or CORE — also
carries a declaration in [`flaky.yaml`](flaky.yaml). The two mechanisms contradict each other: a
gating class exists to stop the run, and a declared flake that passes on retry resolves
`FLAKY-PASS`, which `lib/results.py` deliberately makes neither a PASS nor a FAIL. An id that is
both gates nothing.

The check landed on a corpus holding **one** such violation. This file grandfathers exactly that
one, dated and task-owned, so the check can be **blocking** for everything else from day one rather
than advisory. `check_docs` C3 is this repository's standing demonstration of what advisory does:
it has been advisory long enough for its failure count to grow without anyone acting on it.

**The rules that make this a gate and not an amnesty:**

1. A row suppresses **one** finding, keyed on `(kind, id)`. No file, family, suite or wildcard
   exemption exists, by design.
2. **A stale row is a BLOCKING failure.** When the finding stops occurring — the id is fixed and
   its `flaky.yaml` entry deleted, or it is demoted out of the gating class — F4 fails until the
   row is removed. The list can only shrink.
3. Every row needs an owning `TASK-` id and an ISO `since` date. Missing or malformed either is a
   failure, not a skipped row.
4. **There is one exemptable kind.** F2 (a flake *candidate* on a gating id) and F3 (a declaration
   for an id no registry contains) are at zero today and are not exemptable — an exemption kind
   with no rows is an invitation to open one.

## The exemptable kind

| kind | the finding it suppresses |
|---|---|
| `gating-flake` | an id resolving to RIG, HEALTH or CORE that carries a `flaky:` entry — its retry can only ever resolve `FLAKY-PASS`, so it can never set the blocker its class exists to set |

## Ledger

Owner = the task that will resolve the contradiction, not the task that opened this file.

| id | kind | why it is not resolved today | owner | since |
|---|---|---|---|---|
| `T091` | gating-flake | WP-C `C-6`: every exit in the body routes through `flake()`, and the id is declared in `flaky.yaml` (`TASK-545`, `review_by 2026-09-26`), so its best case is `FLAKY-PASS` — neither a PASS nor a FAIL. Its CORE class is **seeded** from the `spotify-chrome` scope and has never been declared, which is TASK-591's subject: declaring it CORE keeps this row, demoting it to FEATURE retires it. Either way the resolution is TASK-591's, not a second exemption. | TASK-591 | 2026-09-04 |

## Retirement

This file is deleted when the row above is. Two ways that happens, and the check reports either as
F4 the moment it does:

* **TASK-591** declares `T091`'s class. If the written reason cannot justify CORE — and a body that
  can only resolve `FLAKY-PASS` is a poor CORE candidate — it becomes FEATURE and the contradiction
  is gone.
* The underlying race is fixed (`TASK-545`, `review_by 2026-09-26`), the `flaky.yaml` entry is
  deleted, and the id becomes an ordinary CORE test. Note that the flake declaration expires on
  that date regardless: past it, `lib/results.py` turns the declaration into a FAIL, so this row
  cannot outlive September without someone re-justifying it.
