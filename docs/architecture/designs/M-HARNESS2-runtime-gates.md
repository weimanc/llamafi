# M-HARNESS2 — the four static gates, and the runtime truth each one approximates

> Owner: **@Architect**
> Status: accepted
> Decided 2026-09-08 (TASK-671). Built: R34's runtime half (`gate/check_can_go_red.py`,
> `lib/canfail.py`, commit `c444071`). Filed: TASK-672/673/674 (the other three arms)
> Sources: [requirements](../../verification/M-HARNESS2-requirements.md) R34/R18/R17/R36 ·
> [DEV review §4](M-HARNESS2-DEV-review.md) · `lib/replay.py` (TASK-628)

## 1. The problem, stated once

Four `run/check` gates decide a **runtime** property of a test body by reading its **text**:

| gate | requirement | the text it reads | the runtime fact it stands in for |
|---|---|---|---|
| `check_no_reachable_fail.py` | R34 | a `fail()` reachable through the call graph | the body can record a FAIL |
| `check_defaulted_reads.py` | R18 | `.get(<field>, <literal>)` on a reply-tainted name | an oracle or restore is satisfied when the field is absent |
| `check_restore_manager.py` | R17 | the mutation is lexically inside `with dut.saved()/injected()` | what the body set is set back, on every exit path |
| `check_gating_offline.py` | R36 | a closure walk against hand-kept `NETWORK_KEYS/HELPERS/APPS` | a gating body's precondition needs the outside world |

Each is a **necessary-condition check** written as if it were sufficient. Each one's docstring is
honest about a piece of that (R34's refuses dominance analysis; R18's says why it is a taint walk;
R17's says why it does not look for `finally`; R36's says why it walks the closure). None of them
can be made sufficient by widening the analysis, because "this guard can be true", "this default is
consumed by a comparison", "this restore runs on the fail path", "this helper is actually called"
are questions about **execution paths through 196 bodies with helper indirection**. A static
answer to those is program analysis, and a wrong one errs in the direction that matters: it
**clears** a body that has the defect. TASK-661 recorded the same lesson one layer down — *a gate
that greps for a call is not a gate that runs it* — after fourteen entry points passed a text
check with a dead mechanism behind the string.

## 2. The decision

**Do not widen the static analysis. Execute instead.** Where a recorded transcript exists for an
id, run the real body through the real `Dut` and the runner's real dispatch arms
(`lib/dispatch.py`) against that transcript **poisoned**, and read the property off what the body
actually did. The static gates stay, as **authoring-time linters**: cheap, fixture-free, and they
catch the shape the moment it is typed. The runtime gate is **ground truth where a transcript
exists**. Where the two disagree, the disagreement is a finding about one of the *gates* and is
printed as such (`check_can_go_red.py`'s CONTRADICTION note).

Three properties of this design are load-bearing and each was tested, not asserted:

1. **Soundness is one-directional and stated.** An assertion FAIL *observed* under poison is the
   body going red — not a prediction. "Never red" is *not observed under 8 poison/extent
   combinations × N positions*, and is ledgered as such. The gate can be conservative (flag a body
   that some other perturbation would have reddened); it cannot clear a body that cannot fail,
   because clearance requires an exhibited FAIL.
2. **Not every red is an assertion.** Building the negative suite measured that *every* body with
   one typed read goes red under the DROP poison via `BadField` — the accessor rejecting the reply
   shape — whatever the body's own logic does. Counting that would have cleared `C-1`'s inverted
   guard on the strength of a `get_int` it never looks at. So reds are graded off the dispatch
   `Arm` and the `fail()` caller: **ASSERTION** (a suite `fail()` on a device reply) is the only
   grade that earns `RED`; **CONTRACT** (`BadField`), **ACCIDENT** (`TimeoutError`/`Exception`) and
   **POLICY** (`flake()` failing closed) are `RED-WITHOUT-ASSERTION`, blocking with a ledger row.
   This is also why the static ledger's `T084`/`T087`/`T091`/`T092` rows and the hardware
   observation "`T_WR_EJECT_01` FAILs `UNDECLARED flake`" are *both* right: the cell is red, the
   body asserted nothing.
3. **The ELF stamp is irrelevant to this question, and the reason is written down.** `lib/replay.py`
   refuses a stale transcript because for **falsification** (R9/R10) the recording stands in for
   what the *firmware* would say. R34 asks about the **body**: is there a reply sequence under which
   it records FAIL? A sequence the firmware once produced, mutated, is a reply sequence. What must
   hold instead is that the recording is a **healthy path for this body** — the unmutated replay
   PASSes with no transcript miss — and that is decided by running it, not by hashing the source.
   A body that changed to ask something new misses and is `INCONCLUSIVE(re-record)`, never a
   finding. Results produced under the waiver carry `is_confirmation == False` and are never
   counted by `confirmations()`; they are counted as observed verdicts, which is what they are.

## 3. What is built (TASK-671, `c444071`)

`lib/canfail.sweep(tid, body, transcript)` → `Sweep` with one of `RED`, `RED-WITHOUT-ASSERTION`,
`NEVER-RED`, `BASELINE-NOT-PASS`, `INCONCLUSIVE`. Poisons `PERTURB`/`DROP`/`REFUSE`/`SILENCE`, each
`AT` one position and `ONWARD` from it (the `AT` extent exists because a later read may have to
stay healthy for the `fail()` to be reached — fixture `pair` in the suite). Search stops at the
first assertion red. `gate/check_can_go_red.py` is blocking on a dated shrink-only ledger
([`can_go_red_ledger.md`](../../verification/can_go_red_ledger.md)); a row must name the outcome the
sweep actually finds. `test_check_can_go_red.py` records eight synthetic shapes through the real
recorder and includes two mutation arms: poisons disabled → `RED` must vanish; fail-witness blinded
→ the flake-only body is wrongly `RED`. The runner grew `--record DIR` (`RECORD_DIR=` through
`run/test` and `run/test-targeted`).

**Today the transcript directory is empty** and the gate prints *zero BY ABSENCE*: a TASK-557
observation window (uptime ~24 h) was live and recording resets the board. The first recording is
a deliberate act — end the window on purpose and record that you did (dut_workflow §5a).

## 4. The other three, and how each falls out of the same sweep

The sweep already produces, for free, the two things the other three gates cannot see: **every
command the body actually issued** (the transcript's key set on the healthy path) and **every
FAIL/UNMET exit path** (the poisoned runs). Each arm below is a read over those, not a new engine.

| gate | static blind spot | runtime arm | row |
|---|---|---|---|
| `check_defaulted_reads.py` (R18) | a default that is not a `.get` literal — `or 0`, `try/except` returning a constant (R34's shape 4), a helper that swallows; and it counts defaults on fields nobody compares | `DROP@k` leaves the reply with framing only. **PASS under DROP@k, where the body read a field of exchange k**, means the oracle was satisfied by a default. "Read a field" needs the reply dicts to record key access — the same instrument TASK-641's read-key set needs, so build it once | **TASK-672** (after 641's key tracking, or builds it) |
| `check_restore_manager.py` (R17) | cannot see a restore on the **fail** path (`C-15`), cannot see a `with` whose restore was refused, cannot see a restore of the wrong variable at runtime | on every poisoned run that ends FAIL/UNMET, diff the `set X` commands the body issued after the verdict against the ones before it; a `set` with no acked set-back is a leak **on that path**. The sweep is the only host-side way to *generate* fail paths | **TASK-673** |
| `check_gating_offline.py` (R36) | the lists are hand-kept — a new key or app is invisible until listed; the closure over-approximates (a reachable helper is not a called one) | the healthy transcript's command set **is** the exact key set on the gating path; check it against `NETWORK_KEYS` with no closure guess, and read app switches off the `tap` commands rather than `NETWORK_APPS` | **TASK-674** |

Each arm keeps its static sibling. The static gate is what catches the shape while it is being
typed, with no fixture; the runtime arm is what says whether the shape *did* anything.

## 5. What this does not claim

- It does not grade the assertion (R2/R9). A tautology (`set X 5; get X == 5`) is `RED` here.
  The falsifier taxonomy (TASK-641/642/643) owns that, and the poison sweep is a substrate for it,
  not a substitute.
- It does not say the firmware would still produce the recorded replies (R10). That is the
  ELF-stamped falsification job, which keeps its refusal.
- The recorded set is a **ratchet**, not a gate at zero: a host gate cannot demand a board session.
  `UNRECORDED` is a census line. The ratchet's owner is TASK-643, as `lib/replay.py` already states.
- A finite poison set. `NEVER-RED` means *not under these*; a body that only reddens on one specific
  wrong value is flagged and belongs in the ledger with that said. Adding a poison is a one-function
  change and the negative suite says what it must not break.

## 6. Recording protocol for the first session

1. `./run/monitor-read` — if a TASK-557 window is live, decide to end it and write that down.
2. Flash the debug env (`./run/flash-debug`); the entry point will refuse an `elf-mismatch`.
3. `RECORD_DIR=app/tools/suite/serialdbg/transcripts ./run/test` — one `<id>.json` per id, redacted.
4. `python3 app/tools/gate/check_can_go_red.py --verbose` — compare against the prediction already
   written at the foot of the ledger (`T084/087/091/092` → `RED-WITHOUT-ASSERTION` (policy);
   `T-BUSY-05` → `NEVER-RED`). A prediction written before the run is the only kind that counts.
5. Ledger every blocking outcome with its true token and an owner; commit the transcripts.
