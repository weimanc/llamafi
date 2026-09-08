# Can-go-red ledger — R34's runtime exception list

> Owner: **@VE** · Machine-read by `app/tools/gate/check_can_go_red.py` · Opened **2026-09-08**
> Opening task: **TASK-671** · Mechanism: `app/tools/lib/canfail.py` · Static sibling:
> [`no_reachable_fail_ledger.md`](no_reachable_fail_ledger.md)

## What this file is

`check_can_go_red.py` runs every registered id that has a recorded transcript
(`app/tools/suite/serialdbg/transcripts/<id>.json`) against that transcript **poisoned at every
position with four poisons**, through the real `Dut` and the runner's real dispatch arms, and asks
one question: **did the body ever record an assertion-grade FAIL?** An id whose answer is no lands
here, or the gate is red.

The two blocking outcomes, defined in `lib/canfail.py`:

| outcome | meaning |
|---|---|
| `NEVER-RED` | every poison at every position left the body green (PASS/SKIP) or UNMET |
| `RED-WITHOUT-ASSERTION` | red was observed, but only through the **contract** arm (`BadField`: the typed accessor rejected the reply shape), a **crash** arm (`TimeoutError`/`Exception`) or the **flake** policy failing closed — never through the body's own `fail()` on its subject |

Why contract reds do not count, measured not predicted: every body with one typed read goes red
under the DROP poison through `BadField`, whatever its own logic does. Counting that would clear
`C-1`'s inverted guard on the strength of a `get_int` it never looks at.

`INCONCLUSIVE` and `BASELINE-NOT-PASS` are **not** findings about the body — they say the recording
is stale or unhealthy for it — and are printed with a re-record instruction, never ledgered.
`UNRECORDED` is a census count; the recorded set is TASK-641/642/643's ratchet.

**The rules that make this a gate and not an amnesty** (the standing form):

1. A row suppresses **one** id. No wildcard.
2. **The list can only shrink.** A row whose id now sweeps `RED` is a blocking failure
   (`stale ledger row … delete this row`).
3. Every row names the `outcome` the sweep actually finds (a row naming the wrong one is a
   failure), an owning `TASK-` id, and an ISO `since` date.
4. **A row whose owning task is archived is a blocking failure.**

## Ledger

| id | outcome | why it is not fixed today | owner | since |
|---|---|---|---|---|

**0 rows.** The transcript directory was empty when this gate landed — a TASK-557 observation
window (uptime ~24 h) was live and recording costs a reset — so the gate reads zero **by absence**,
and prints exactly that. The mechanism is proven by `gate/test_check_can_go_red.py`, which records
synthetic bodies through the real recorder and sweeps them, including a mutation arm.

## What the first recording is expected to put here

The static ledger's eight rows will not all reappear: `T093`/`T094`/`T095` are registry `None`s
the sweep cannot see either (they stay `UNRECORDED`), and `T084`/`T087`/`T091`/`T092` are predicted
`RED-WITHOUT-ASSERTION` (policy) — their `flake()` exits fail closed as UNDECLARED, which the static gate cannot
count as a `fail()` and this gate correctly refuses to count as an assertion. New rows are
expected from the shapes only execution can see: `T-BUSY-05`'s inverted guard (TASK-582) is the
named candidate for `NEVER-RED`. Write the prediction down before recording; compare after.
