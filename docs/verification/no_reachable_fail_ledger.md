# No-reachable-`fail()` ledger — R34's shrink-only exception list

> Owner: **@VE** · Machine-read by `app/tools/gate/check_no_reachable_fail.py` · Opened **2026-09-05**
> Opening task: **TASK-603** · Procedure: [test_id_retirement.md](../process/test_id_retirement.md)

## What this file is

`check_no_reachable_fail.py` (R34) asserts that every id in `build_all_tests()` can actually produce
a **FAIL**. Blocking-at-zero was not available on day one — the first run measured **8** findings —
so the gate lands **blocking with this ledger**, in the same form as
[`defaulted_reads_ratchet.md`](defaulted_reads_ratchet.md) and
[`id_binding_exceptions.md`](id_binding_exceptions.md). (R35's own ledger,
`gating_class_declarations.md`, was the same form and is **gone** — TASK-626 emptied it on
2026-09-06 and it was deleted per its own retirement rule.)

**The rules that make this a gate and not an amnesty:**

1. A row suppresses **one** id. No file, family, module or wildcard exemption exists, by design.
2. **The list can only shrink.** A row whose finding no longer occurs is a **blocking failure**
   (`stale ledger row … delete this row`), so a fix forces the row out.
3. Every row needs a `shape` (1–4), an owning `TASK-` id, and an ISO `since` date. Missing any is a
   failure.
4. **A row whose owning task is archived is a blocking failure.** Without this a row outlives its
   owner and the gate reads zero forever — the `C3` shape the PM review cut ~60 days of ratchets to
   avoid re-creating.

The four shapes are defined in the gate's module docstring. Briefly: **1** no `fail()` anywhere in
the reachable source; **2** the body is one unconditional `skip()`; **3** a guard that cannot be
true; **4** the only `fail()` is behind a helper that swallows its own read error and returns a
bool — the shape `check_defaulted_reads.py` structurally cannot see.

## Ledger

| id | shape | why it is not fixed today | owner | since |
|---|---|---|---|---|
| `T087` | 1 | as `T084`: the `errors` list is collected honestly and then spent on `flake()`. Four real region assertions, none of which can go red | TASK-595 | 2026-09-05 |
| `T091` | 1 | as `T084`. WP-C `C-6` states the consequence in the id's own declaration: *"its best case is `FLAKY-PASS` — neither a PASS nor a FAIL — and `_gate.py` can never see it set the blocker"* | TASK-595 | 2026-09-05 |
| `T092` | 1 | as `T084`; a latency bound whose over-budget branch is `flake()`, so the bound is unenforced | TASK-595 | 2026-09-05 |
| `T-BUSY-01b` | 1 | every non-pass exit is `skip()`. Since TASK-624 the right verdict for "the window the test needs was not observable" is `unmet()`, which blocks; the conversion is a named, small fix and belongs with the rest of them | TASK-615 | 2026-09-05 |
| `T093` | 1 | the registry entry is `None` (`shell.py`'s `TESTS`) — the interactive ids are dispatched specially in `main()`, so **the gate cannot see a body through the registry at all**. The body does have reachable `fail()`s. This is `B-13`'s registry-honesty defect showing up from a second direction, and it compounds `C-3`: no `run/` script passes `--interactive`, so these three have never been runnable from a shipped entry point | TASK-614 | 2026-09-05 |
| `T094` | 1 | as `T093` | TASK-614 | 2026-09-05 |
| `T095` | 1 | as `T093` | TASK-614 | 2026-09-05 |

**8 rows.** Re-count with `python3 app/tools/gate/check_no_reachable_fail.py` — the gate prints the
census, generated, never transcribed here.

## What the opening measurement changed about the plan

The TASK-603 disposition (§5.4) predicted this ledger would open holding the **shape-4** ids — "the
twelve remaining `_appid_is` / `_switch_to` / `_restore_spotify` guards that gate a sole `fail()`"
— plus `T093`. **Measured, shape 4 is zero and shape 3 is zero.** Eight ids do carry a
helper-guarded `fail()` (`T169`, `T172`, `T173`, `T182`, `T231`, `T_GOL_01`, `T_MA_01`, `T_PR_04`),
but in every one of them it is *one of several* `fail()`s, not the only one — TASK-584 and TASK-596
had already converted the sole-`fail()` cases to typed call-site reads. The clause stays in the gate
and is exercised by its negative test and by the mutation arm: a clause that reads zero today is
what stops the shape coming back, and it is the one shape no other gate in the tree can see.

What the ledger holds instead was not predicted at all: **five ids whose every exit is `flake()` or
`skip()`**, which no audit had counted as a no-reachable-`fail()` finding, and the three interactive
ids the registry hides behind a `None`.
