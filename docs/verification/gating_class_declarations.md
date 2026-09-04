# Undeclared gating classes — the R35 ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_test_meta.py` (finding **G1**) ·
> Opened **2026-09-04** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R35, TASK-591

## What this file is

[R35](M-HARNESS2-requirements.md) requires every id whose class can block a run — RIG, HEALTH or
CORE — to carry an **explicit class declaration with a written reason**, never a default. The
reason is not a restatement of the class name. It is a sentence saying **what makes this test's
failure mean the rest of the run cannot be trusted**. It lives in the `@meta(cls=…, cls_reason=…)`
declaration on the body, or in the family's `META_OVERRIDES` — next to the code it describes, so it
cannot drift from it (LL-114: parse, don't mirror).

TASK-591 read all 49 gating bodies with that question in front of it. It **could write the sentence
for 25** — 3 RIG, 3 HEALTH and 19 of the 43 CORE ids — and could not write it for the other 24, each
of which looked like a FEATURE test that `_meta.seed_cls()` had made CORE because its scope happened
to be `shell`, `taskbar`, `boot` or `spotify-chrome`. Those 24 were filed here as proposed demotions
with their evidence.

**On 2026-09-04 the human approved 20 of the 24.** Those ids now carry
`@meta(cls="FEATURE", cls_reason=…)` — a demotion is a declaration too, and each one says why its
failure is *local*. Their rows are gone from the table below; `check_test_meta.py`'s **G2** would
have failed on any that were left. The CORE class went **43 → 23**.

The **4 rows that remain** are the ones a static read cannot settle. They stay CORE and stay here
until the Phase 2 DUT session produces the measurement each needs:

| id | what the session has to answer |
|---|---|
| `T-BUSY-05` | WP-C `C-1`'s inverted guard means we have no evidence either way about the path it guards. Does `shellBusy` actually clear on `switchApp` while a fetch is in flight, once the guard is corrected? |
| `T-CDWN-03` | WP-C NEEDS-DUT #3. Is `shellBusy` ever genuinely true when the taskbar tap lands? If it rarely is, the id has passed vacuously for its whole life and the demotion is clear-cut; if it usually is, it is not. |
| `T-BUSY-01` | WP-B `N-B2`. Is the live-fetch failure rate high enough to make B-1 a live P1 rather than a theoretical one? The answer sets whether the fix is a demotion or an injected precondition (R36). |
| `T-BUSY-01b` | The same question for the warm-fetch path, whose negative outcome is a `skip()` — a genuine regression and a fast fetch are indistinguishable today. |

**A row does not make the id safe.** While it sits here the id still resolves to CORE and, once
TASK-566's `--class-order` switch flips, still blocks the FEATURE ids beneath it. The row makes the
fact visible and dated; it does not fix it. That is the direct reason
**[TASK-617](../project/tasks-harness2.md) must not flip the switch while this ledger is non-empty** —
4 ids would then carry a gate's authority on a class nobody has affirmed.

## How a row leaves

Each remaining row resolves one of two ways, and the gate reports either as **G2** the moment it
does:

* the id takes `@meta(cls="FEATURE", cls_reason=…)` — the demotion this file proposes; or
* the session's measurement supports a CORE reason, and the id takes `@meta(cls="CORE", …)`.

**The rules that make this a gate and not an amnesty:**

1. A row suppresses **one** finding, keyed on `(kind, id)`. No file, family or wildcard exemption
   exists, by design.
2. **A stale row is a BLOCKING failure.** When the id declares a class, G2 fails until the row is
   deleted. The list can only shrink.
3. Every row needs an owning `TASK-` id and an ISO `since` date. Missing or malformed either is a
   failure, not a skipped row.
4. **There is one exemptable kind**, `undeclared-gating-class`. G3 (a declared gating class whose
   reason is too short to be an argument) is at zero and is not exemptable — an exemption kind with
   no rows is an invitation to open one.

## The exemptable kind

| kind | the finding it suppresses |
|---|---|
| `undeclared-gating-class` | an id resolving to RIG, HEALTH or CORE with no `cls_reason` on its declaration — a class that can stop the run, applied by a default nobody affirmed |

## Ledger

Owner = the task that will resolve it — **TASK-634**, the Phase 2 DUT session, for all four:
each needs a measurement, not another static read. `since` = the date the row was opened.

| id | kind | why it is not resolved today | owner | since |
|---|---|---|---|---|
| `T-BUSY-05` | undeclared-gating-class | **DEMOTE.** WP-C `C-1`: the guard at `app/tools/suite/serialdbg/shell.py:1961` is inverted — `if any(b is not True …)` is False exactly when all three post-switch reads are `True`, i.e. when the amber did NOT clear, so control falls through to `pass_()`. It passes precisely when the regression is present. Four `skip()` exits above it mean it usually never reaches the assertion at all. Re-promotion is arguable once C-1 is fixed and it has been run; not before. Stock-only, scope should be `Stock`. | TASK-634 | 2026-09-04 |
| `T-CDWN-03` | undeclared-gating-class | **DEMOTE.** WP-C `C-11`: the precondition its claim rests on is never established — nothing between the row tap (`app/tools/suite/serialdbg/shell.py:2167`) and the taskbar tap (`app/tools/suite/serialdbg/shell.py:2169`) checks `shellBusy` was true when the taskbar tap arrived, and `set triggerFetch 1` makes it likely, not certain. On a warm or failed fetch it passes without exercising the bypass. BP-074: an assertion whose precondition never occurred is inconclusive, not a pass — and an inconclusive verdict cannot gate. Stock-only, scope should be `Stock`. | TASK-634 | 2026-09-04 |
| `T-BUSY-01` | undeclared-gating-class | **DEMOTE.** WP-B `B-1`'s headline id. Its pass/fail is a network outcome: `_poll_chart_len_positive` is 45 s of live HTTPS to Yahoo and a timeout is a hard `fail()`, not a skip — under the switch it runs at index 14 and NOT-RUNs 167 ids on a network outage. Its own assertion is weak besides: `app/tools/suite/serialdbg/shell.py:1782-1787` downgrades the "busy went true" half to a printed note, leaving `busy == False` at rest, which cannot distinguish auto-clear from never-rose. The genuine `shellBusy` premise is already declared CORE on T-BUSY-02. Stock-only, scope should be `Stock`. | TASK-634 | 2026-09-04 |
| `T-BUSY-01b` | undeclared-gating-class | **DEMOTE.** Same family and same network dependency (two 45 s live chart fetches). Its negative outcome is a `skip()` (`app/tools/suite/serialdbg/shell.py:1841`, "warm fetch too fast"), so a genuine regression where the tap raises nothing is indistinguishable from a fast fetch and reports green — the raise half it exists to supply is unfalsifiable in practice. Three `skip()` exits. Stock-only, scope should be `Stock`. | TASK-634 | 2026-09-04 |

## Retirement

This file is deleted when the last row is. A row goes when its id carries a class declaration with a
reason — `FEATURE` per the proposal above, or `CORE` with an argument this package could not make.
Until then, `check_test_meta.py` prints the count on every `run/check`, and the count can only fall.
