# TASK-575 — the unmasked timeouts, audited; and what the owed `run/test` pass must show

> Owner: @VE · written 2026-09-12, **before** the run · subject: TASK-575's `_TeeSerial.__setattr__`
> fix (host-tested 2026-09-02), whose full `run/test` pass is **Phase 3's last entry clause**
> ([tasks-harness2.md](../../project/tasks-harness2.md)).
> Sibling precedent: [testarch-order-baseline-task566.md](testarch-order-baseline-task566.md).

## 1. Why this is not "just a run"

`_TeeSerial` wrapped the serial object and defined no `__setattr__`, so every `self.ser.timeout = …`
set a shadow attribute on the wrapper and never reached pyserial. Reads used the constructor's
value — **3.0 s** — for as long as the tee existed. The fix forwards the assignment, so those sites
now take effect: **0.3 s, 0.5 s and 1.0 s, a 3×–10× tightening**, at sites inside `lib/dut.py` and
`shell.py` — the session layer every test uses.

A tightening is a behaviour change. The row's defence is that the loops are monotonic-clock based
and therefore unaffected; that is an argument, not evidence, and it had never been checked
site-by-site. This document checks it, so the run is a confirmation with a prediction rather than a
run-and-hope.

## 2. The audit — every site that actually tightened

Restores to `orig_timeout` are excluded: they put back what was there. The constructor assignment
(`lib/dut.py:711`) is excluded too — it sets the value the others were being measured against.

| site | function | new | loop shape | tolerates an empty read? |
|---|---|---|---|---|
| `lib/dut.py:863` | `_wait_for_ready` | 0.5 s | per-phase monotonic deadlines | yes — `_wait_for_bootphase_6`: `if not line: continue` |
| `lib/dut.py:912` | `_wait_for_ready` (shell probe) | 1.0 s | `while monotonic() < probe_deadline` | yes — loops until the marker or the deadline |
| `lib/dut.py:952` | `_wait_for_ready` (→ phase 6) | 1.0 s | per-phase monotonic deadlines | yes — same gate as `:863` |
| `lib/dut.py:986` | `_wait_for_ready` (`--no-wifi`) | 1.0 s | nested monotonic deadlines | yes — loops until the marker or the deadline |
| `suite/serialdbg/shell.py:857` | `t133` | 0.5 s | `while monotonic() < deadline` (90 s) | yes — non-matching lines fall through |
| `suite/serialdbg/shell.py:3272` | `_tbfb_drag_capture` | 0.3 s | `while monotonic() < deadline` | yes — explicit `if not line: continue` |

**Result: six sites, zero of them single-read.** Every one sits inside a loop bounded by
`time.monotonic()` whose exit condition is a *marker* or the deadline, never the return of one
blocking read. So a shorter per-read timeout cannot shorten any wait — it raises the **sampling
density** inside an unchanged window.

For two of them the change is a strict improvement rather than a risk:

- `t133` watches 90 s for `Guru Meditation Error`. At 3.0 s per read it could take ~30 samples; at
  0.5 s, ~180. It is now six times more likely to *catch* the crash it exists to catch.
- The shell probe at `:912` had a 3.0 s read inside a `_SHELL_PROBE_DEADLINE_S` window, so it could
  manage barely one attempt. It now gets several.

**The prediction this supports:** the owed run should produce **no new failures attributable to
TASK-575**. If it does, the failing id's read path is a site this table missed, and the table is
wrong — which is a finding about this audit, not only about the suite.

## 3. What the run cannot be asked to show

A full `run/test` **cannot be green today**, for three reasons that predate TASK-575 and are all
documented:

- **TASK-243** — the owner account's Premium lapsed, so Spotify returns a permanent 403. Live
  playback-state verdicts are unobtainable; UI, nav and app-switch ids are unaffected.
- **TASK-675** — the pinned root rotted (`accounts.spotify.com`/`i.scdn.co` moved to Certainly ←
  Starfield Root G2). Every boot's token refresh fails `-9984` and `run/check-datatask-certs` reads
  FAIL on those two hosts. DEFERRED by the human; expected, not a regression.
- **Flake exposure** — TASK-566 measured **15 of 210 ids (7.1 %) non-stationary across the first two
  runs alone**, each run crossing four boot generations.

So "the owed full `run/test` pass" is **not** "exit 0". Defining it as that would either block Phase 3
forever or invite someone to wave the failures through, and LL-146 exists because of the second one.

## 4. The acceptance criterion, fixed before the run

> **PASS** = across two `run/test` runs at the same commit, the union of failing ids contains no id
> whose failure is attributable to a read timing out, **and** every failing id is accounted for by
> one of: TASK-243, TASK-675, a `flaky.yaml` declaration, or a pre-existing open row naming it.
>
> **FAIL** = any failing id whose failure mode is a read that gave up — the signature TASK-575 could
> produce — or any failing id with no prior account.

Two runs, not one, because at 7.1 % flake exposure a single run's failure set is noise. **Compare
failure SETS, not counts** (LL-104): an id failing in both runs is deterministic; an id failing in
one is environmental until shown otherwise. Three runs is better and is what TASK-566 used; two is
the floor.

`RECORD_DIR=app/tools/suite/serialdbg/transcripts` is set on the runs. `check_can_go_red` is
currently emitting a long list of `BASELINE-NOT-PASS` notes, each asking for exactly this — so the
recording refresh is a by-product of a run that has to happen anyway. Decided before the run rather
than wished for afterwards.

## 5. Out of scope, and separately owed

`test_fetch_stress.py:216` sets `write_timeout = 3.0`, which was **never armed** before the fix and
now is. That is a new exception path rather than a shorter wait, so §2's deadline-loop argument does
not cover it — and it lives in `run/stress`, not `run/test`, so the owed run does not exercise it at
all. Recorded here because nothing else records it.

## 6. Result

**NOT YET RUN.** Fill with both runs' failure sets, their intersection, and the §4 verdict.
