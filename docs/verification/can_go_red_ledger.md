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
| `T-BUSY-01b` | RED-WITHOUT-ASSERTION | every non-pass exit is `skip()`; red only via contract/accident. Since TASK-624 the right verdict is `unmet()` — same row as the static ledger | TASK-615 | 2026-09-09 |
| `T091` | RED-WITHOUT-ASSERTION | as `T084`, red only via contract/accident | TASK-595 | 2026-09-09 |
| `T077` | RED-WITHOUT-ASSERTION | red only through a crash arm (accident 7): raw `cmd()` reads, no `fail()` reached under any poison | TASK-676 | 2026-09-09 |
| `T_CX_05` | RED-WITHOUT-ASSERTION | accident-only (40): the body breaks on a bad reply, never asserts on it | TASK-676 | 2026-09-09 |
| `T_WR_HEAP_01` | RED-WITHOUT-ASSERTION | accident-only (52) | TASK-676 | 2026-09-09 |
| `T_WR_HEAP_02` | RED-WITHOUT-ASSERTION | accident-only (49) | TASK-676 | 2026-09-09 |
| `T_WX_05` | RED-WITHOUT-ASSERTION | accident-only (60) | TASK-676 | 2026-09-09 |
| `T170` | RED-WITHOUT-ASSERTION | newly VISIBLE 2026-09-12: TASK-575's run refreshed 194 transcripts, and a healthy recording sweeps where a `BASELINE-NOT-PASS` one was skipped. Not a new defect — newly measurable | TASK-688 | 2026-09-12 |
| `T176` | RED-WITHOUT-ASSERTION | as `T170` — exposed by the 2026-09-12 transcript refresh, not introduced by it | TASK-688 | 2026-09-12 |
| `T188` | RED-WITHOUT-ASSERTION | as `T170` | TASK-688 | 2026-09-12 |
| `T204` | RED-WITHOUT-ASSERTION | as `T170`; `T204`'s 120 s Ytd stall is separately TASK-668 | TASK-688 | 2026-09-12 |
| `T_CLK_SIG_01` | RED-WITHOUT-ASSERTION | as `T170`; 41 replays over 5 exchanges, zero assertions on its subject. TASK-638 landed the id; the oracle is what is missing | TASK-688 | 2026-09-12 |

**9 rows** (first recording, 2026-09-09).

**Opening state, 2026-09-08 (0 rows):** The transcript directory was empty when this gate landed — a TASK-557 observation
window (uptime ~24 h) was live and recording costs a reset — so the gate reads zero **by absence**,
and prints exactly that. The mechanism is proven by `gate/test_check_can_go_red.py`, which records
synthetic bodies through the real recorder and sweeps them, including a mutation arm.

## The first recording, measured 2026-09-09 — against the prediction below

193 transcripts, sweep 22 s warm. **RED 110 · RED-WITHOUT-ASSERTION 9 · NEVER-RED 0 · BASELINE-NOT-PASS 63 · INCONCLUSIVE 11 · UNRECORDED 3.** Predicted right: `T084`/`T091` (policy/contract only), `T093`–`T095` unrecorded. Predicted wrong: **`T-BUSY-05` is RED** — `perturb get shellBusy` reaches its own `fail()` ("shellBusy not false after switchApp"), so the C-1 inverted guard *can* go red; whatever C-1 found is not "cannot fail". `T087`/`T092` were recorded as FLAKE/FAIL runs, so they are BASELINE-NOT-PASS until re-recorded healthy. New and unpredicted: six **accident-only** bodies (TASK-676). The 63 BASELINE-NOT-PASS are the run's own 24 FAILs + 39 SKIPs (Spotify-dependent ids under TASK-243, Stock fetches, WebRadio TLS); the 11 INCONCLUSIVE are polled oracles whose recording ended by deadline, not by event — re-record when healthy. One witness defect was found and fixed by this recording: the first pass graded 0 assertions because suite modules import `fail` by name (fixture `byname` in the negative suite now).

## What the first recording was expected to put here (written 2026-09-08, before the run)

The static ledger's eight rows will not all reappear: `T093`/`T094`/`T095` are registry `None`s
the sweep cannot see either (they stay `UNRECORDED`), and `T084`/`T087`/`T091`/`T092` are predicted
`RED-WITHOUT-ASSERTION` (policy) — their `flake()` exits fail closed as UNDECLARED, which the static gate cannot
count as a `fail()` and this gate correctly refuses to count as an assertion. New rows are
expected from the shapes only execution can see: `T-BUSY-05`'s inverted guard (TASK-582) is the
named candidate for `NEVER-RED`. Write the prediction down before recording; compare after.
