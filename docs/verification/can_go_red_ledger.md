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
| `T170` | RED-WITHOUT-ASSERTION | newly VISIBLE 2026-09-12: TASK-575's run refreshed 194 transcripts, and a healthy recording sweeps where a `BASELINE-NOT-PASS` one was skipped. Not a new defect — newly measurable | TASK-688 | 2026-09-12 |
| `T176` | RED-WITHOUT-ASSERTION | as `T170` — exposed by the 2026-09-12 transcript refresh, not introduced by it | TASK-688 | 2026-09-12 |
| `T188` | RED-WITHOUT-ASSERTION | as `T170` | TASK-688 | 2026-09-12 |
| `T_CLK_SIG_01` | RED-WITHOUT-ASSERTION | as `T170`; 41 replays over 5 exchanges, zero assertions on its subject. TASK-638 landed the id; the oracle is what is missing | TASK-688 | 2026-09-12 |

**6 rows** (first recording, 2026-09-09, 9 rows; `T204` removed 2026-09-14 — see below; `T077`/`T_CX_05`/`T_WR_HEAP_01`/`T_WR_HEAP_02`/`T_WX_05` fixed to assert and removed 2026-09-18, TASK-676).

**`T_WR_HEAP_02`'s numeric claim is still not falsifiable by this sweep — recorded here because
its row leaving the table would otherwise hide that (2026-09-18, TASK-676).** The id's subject
(`HEAP post-fetch free=… min=…` ≥ 30 KB) is parsed out of a raw serial LOG line, and
`poison_transcript` (app/tools/lib/canfail.py:234-238) rewrites only lines that parse as a JSON
object: PERTURB/DROP/REFUSE cannot move that number, and SILENCE can only delete the whole
exchange. What went red under poison, and what took the row out, is the id's *precondition* — a
refused `set bgPoll 0`, which contradicts the "bgPoll suspended, TLS torn down" premise the heap
sample is only meaningful under. That is a real assertion on a real claim, and it is not the
30 KB floor. Falsifying the floor needs the value to arrive as a JSON field (the `get wrHeap`
fallback already reads one, but the log line wins on every healthy path so the fallback is dead
code there) or a poison that rewrites log text. Neither is scheduled; this is the standing note
that it is owed.

**`T204` removed 2026-09-14 (TASK-697).** TASK-697 added `_diag_snapshot`'s `get dataRing` call
(app/tools/suite/serialdbg/_helpers.py) ahead of where `T204`'s recorded transcript diverges from
its old RED-WITHOUT-ASSERTION path — the poisoned replay now runs out of recorded exchanges one
command earlier and grades INCONCLUSIVE instead, per rule 2 ("the list can only shrink"; a row
whose id no longer sweeps a blocking outcome is itself a failure). Not a fix to whatever `T204`'s
120 s Ytd stall (TASK-668) or its missing assertion actually is — those are unchanged and still
real — only the recording is stale. Re-record `T204` (`RECORD_DIR=... run/test-targeted T204`) and
re-add the row with whatever outcome the fresh sweep finds.

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
