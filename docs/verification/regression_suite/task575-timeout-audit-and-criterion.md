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

## 6. Result — two runs, 2026-09-12, same commit (`a22a0c6`), board `d48afcc8eed0`

| | run 1 | run 2 |
|---|---|---|
| summary | 139 passed, 18 failed, 34 skipped, 1 flaky-pass, 2 unmet | 143 passed, 19 failed, 30 skipped, 0 flaky-pass, 2 unmet |
| non-PASS ids | 20 | 21 |

**Deterministic — failed in BOTH runs (16):** `T078`, `T087`, `T092`, `T172`, `T182`, `T_CX_03`,
`T_DTP_01`(U), `T_DTP_02`(U), `T_GOL_03`, `T_MA_03`, `T_PLR_06`, `T_PLR_12`, `T_PLR_13`, `T_PLR_24`,
`T_WR_TLS_01`, `T_WX_03`.

**Environmental — one run only (9):** run 1 `T_PLR_14`, `T_PLR_17`, `T_PR_05`, `T_WR_HEAP_01`;
run 2 `T_CLK_11`, `T_PLR_15`, `T_PLR_16`, `T_PRM_01`, `T_WR_EJECT_01`. Four of these are
`TimeoutError: no JSON response`, and none repeats — which is what "environmental until shown
otherwise" (LL-104) is for.

### The verdict: §4's FAIL branch fired. **The criterion is NOT met.**

Two clauses fail, and both are recorded as they read rather than as would be convenient:

1. **`T_PLR_13` fails in both runs with `TimeoutError: no JSON response within 8.0s`** — the exact
   signature §4 names as FAIL. It is deterministic, not environmental.
2. **Six deterministic failures have no prior account**: the `lastPlaylistDraw` cluster (`T172`,
   `T182`, `T_CX_03`, `T_GOL_03`, `T_MA_03`, `T_WX_03`). They are **not** covered by TASK-243:
   each message argues the opposite in its own text — *"an idle/empty/403 Spotify still advances
   this clock — a stalled clock is the residue regression, not an idle account"*. Plus `T_PLR_12`
   (heap −6068 B), `T_PLR_24` (`curRow=-1`), `T_DTP_01`/`02` (UNMET, Stock fetch — not a Spotify
   account issue), none of which any open row names.

Accounted for, and correctly: `T078` → TASK-662 (open, "a real input regression"); `T087`/`T092` →
declared in `flaky.yaml`; `T_WR_EJECT_01` → TASK-667, closed by TASK-595's declaration.

### What this does NOT establish

**It does not show that TASK-575 caused any of it**, and §2's audit predicts it did not:

- `TimeoutError: no JSON response within Ns` is raised by `dut.cmd`'s own **monotonic deadline**,
  not by `ser.timeout`. Per §2 the unmasked assignments only raise sampling density inside
  unchanged windows, so an expired 8 s command deadline means the device did not answer in 8 s.
- The `lastPlaylistDraw` cluster has a firmware root cause named in its own failure text.

But that is an argument again — the same kind §2 was written to stop accepting. **The decisive test
is an A/B**: disable `_TeeSerial.__setattr__` (restoring pre-fix behaviour) and re-run the
deterministic set. If `T_PLR_13` still fails, TASK-575 is exonerated by measurement rather than by
reasoning. That A/B is owed and is not done here.

### Two findings this run produced on its own

- **`T087` and `T092` reproduced in BOTH runs.** Policy already makes a reproduced flake a FAIL, and
  the suite reported them correctly. But an id that fails deterministically across two runs is not
  flaky — it is broken, and its `flaky.yaml` declaration is now the wrong description. Direct
  follow-on to TASK-595's sweep.
- **`T_PLR_17` (run 1 only) failed on a mis-correlated reply**: it sent `set cooldown 0` and read
  back `{'cmd': 'get', 'error': 'unknown var', 'var': '__TEST_T_PLR_17__'}`. The sentinel name looks
  like a test-scaffold artifact reaching a live run. Not a timeout; a correlation defect.

### By-product, as planned

`RECORD_DIR` was set on both runs: **194 transcripts refreshed**, which is what `check_can_go_red`'s
`BASELINE-NOT-PASS` notes were asking for.

## 7. Follow-up, 2026-09-13 — "how come we didn't see it before?"

**We did. Three times.** The artifacts prove it, and §6's phrase "no prior account" was accurate
about the task board and misleading about the evidence — corrected here.

| id | 09-06 | 09-09 | 09-12 run 1 | 09-12 run 2 |
|---|---|---|---|---|
| `T172`, `T_CX_03`, `T_GOL_03`, `T_MA_03`, `T_WX_03` | FAIL | FAIL | FAIL | FAIL |
| `T182` | UNMET | UNMET | FAIL | FAIL |
| `T_PLR_12`, `T_PLR_13` | FAIL | FAIL | FAIL | FAIL |
| `T_PLR_24` | **PASS** | **FAIL** | FAIL | FAIL |

All four runs: same board `d48afcc8eed0`, same env, same entry point.

**Why they became visible when they did.** Until 2026-09-04 all six of the `lastPlaylistDraw` ids
spent this exact regression on `skip()`, excused as *"Spotify not rendering — not playing?"*. A skip
is a statement about the configuration, so the suite was green. **TASK-584 (`d95a13c`) converted all
six to `fail()`** after disproving that excuse in firmware — `SpotifyApp::resume()` calls
`invalidatePlaylist()` with no queue or Premium predicate, and `PleditView::draw()` stamps
`_lastDrawMs` before it reads `src.count()`, so an empty queue stamps the clock exactly like a full
one. They failed on the very next full run, 09-06. The conversion worked exactly as designed.

**Why nobody acted.** The verdicts were written to `.runs/` on 09-06 and 09-09 and read by nobody.
That is not an attention failure, it is a missing consumer: **the only thing in the tree that ever
reads an artifact back is `run/player-gate`**, and it compares against a hand-kept markdown baseline
rather than against the previous run. Nothing diffs two artifacts. So six deterministic failures —
one of them a P1-shaped firmware defect — sat in the run history for six days while the programme
that built the artifact worked on other rows. Filed as **TASK-689**, and it is the most valuable
thing this run produced.

**`T_PLR_24` is a genuine regression** with a three-day window: PASS on 09-06, FAIL on 09-09 and
every run since. That is a bisect range, not a mystery.

**What this does to §6's verdict: nothing.** The criterion still reads FAIL, and TASK-575 is still
unproven either way — but the balance of evidence moved. Every one of these failures predates the
09-12 runs and was already present on 09-06, four days after the `_TeeSerial` fix landed and two
days after the conversion that made them reportable. The artifact history begins 2026-09-05, so
**no pre-fix full run exists to serve as a control** — which is precisely why the
`__setattr__`-disabled A/B remains the only way to settle attribution, and why it is still owed.

## 8. The A/B, 2026-09-13 — **TASK-575 is EXONERATED by measurement**

The attribution question §6 and §7 both left open, settled the only way it could be: by disabling the
fix and re-running.

**Design.** Both arms use the *same* selection (`run/test-targeted`, one id list), because a
targeted run cold-boots and cannot reproduce a full-suite order — the comparison is between arms,
not against the full-suite verdict. Same firmware (flashed once, before either arm), same board
`d48afcc8eed0`, same entry state (`playerMode=WebRadio` on both).

- **Arm T (treatment)** — the code as shipped: `__setattr__` forwards to pyserial.
- **Arm C (control)** — pre-fix behaviour restored: `__setattr__` always lands on the wrapper, so no
  assignment reaches pyserial and every read uses the constructor's 3.0 s. Verified before the run:
  `t.timeout = 0.5` left `t._ser.timeout == 3.0`.

Ids chosen because each failure mode involves a bounded wait — the only class the fix could touch.

| id | arm T (fix ON) | arm C (fix OFF) |
|---|---|---|
| `T_PLR_06` | **PASS** | **PASS** |
| `T_PLR_12` | FAIL — heap −4324 B | FAIL — heap −53312 B |
| `T_PLR_13` | FAIL — walk still pending after 15.4 s | FAIL — `TimeoutError: no JSON response within 3.0s` |
| `T_PLR_24` | FAIL — `curRow=-1` | FAIL — `curRow=-1` |
| `T172` | FAIL — `lastPlaylistDraw` | FAIL — `lastPlaylistDraw` |
| `T_MA_03` | FAIL — `lastPlaylistDraw` | FAIL — `lastPlaylistDraw` |
| **totals** | 1 passed, 5 failed | 1 passed, 5 failed |

**The verdict set is identical with the fix and without it.** Disabling TASK-575 makes nothing pass.

**The decisive detail is in arm C.** `TimeoutError: no JSON response within 3.0s` — the exact
signature §4 named as the TASK-575 FAIL condition — appears in the arm where the fix is **disabled**
and reads use the old, looser 3.0 s. A timeout that reproduces with the fix off cannot be caused by
the fix. §2's prediction ("the owed run should produce no new failures attributable to TASK-575")
is confirmed by measurement rather than by reasoning, which is what §2 said it needed.

**Honest limits.** One run per arm, not three. `T_PLR_13` is unstable in *mode* though not in
verdict — three different failure texts across four runs (`TimeoutError` at 8.0 s, walk-pending at
15.4 s, `TimeoutError` at 3.0 s), so it is deterministic in that it always fails and non-deterministic
in how. `T_PLR_12`'s byte delta swings −4324 / −6068 / −53312, so that id's *measurement* is noisy
even though its verdict is not. Neither undermines the arm comparison; both are reasons the ids
belong to TASK-686 rather than here.

**Consequence for TASK-575.** The fix is not the cause of any failure in the deterministic set. §4's
criterion still reads FAIL — correctly, because it was written to gate on "are there unexplained
deterministic failures?", and there are — but those failures are now **attributed elsewhere**
(TASK-685, TASK-686) and predate the fix's visibility window. The `run/test` pass TASK-575 owed has
been executed and its one open question answered. **What blocks Phase 3 is no longer TASK-575's fix;
it is whether the programme accepts entry with TASK-685/686 open.** That is a scheduling decision,
not a measurement, and it belongs to @PM.

The control-arm edit was reverted immediately after the run and verified: `t.timeout = 0.5` again
reaches pyserial. Nothing from arm C is committed.

## 9. The criterion RE-RUN, 2026-09-13 (§4 applied a second time)

§6's runs predated TASK-685 and TASK-692. Both landed, so the criterion was re-run at one commit
(`c7894ef`), two full runs, same board. `RECORD_DIR` deliberately NOT set: the 194 transcripts were
refreshed on 09-12 and `check_can_go_red` is green against them, so re-recording would churn all 194
and raise fresh ledger work unrelated to the question these runs exist to answer.

| | run 1 | run 2 |
|---|---|---|
| summary | 150 passed, 13 failed, 28 skipped, 2 unmet | 151 passed, 12 failed, 28 skipped, 2 unmet |
| non-PASS | 15 | 14 |

**Deterministic (both runs): 8** — was 16 in §6.

`T078` · `T087` · `T_DTP_01`(U) · `T_DTP_02`(U) · `T_PLR_06` · `T_PLR_15` · `T_PLR_24` · `T_WR_TLS_01`

**Non-stationary: 13 ids** (7 run-1-only, 6 run-2-only) of ~193 = **6.7 %**, which corroborates
TASK-566's independently measured 7.1 % rather than resting on it.

The fixes are visible in the delta against 09-12: **11 newly passing**, including all six
`lastPlaylistDraw` ids (TASK-685) and `T_PLR_13` (TASK-692).

### §4 clause by clause

**Clause 1 — "no failing id whose mode is a read that gave up": MET.** No `TimeoutError` anywhere in
the deterministic set. This is the clause that carried TASK-575's own signature, and in §6 it was
failed by `T_PLR_13`. It is now clean, which is the second independent confirmation — after §8's
A/B — that the `_TeeSerial` fix broke nothing.

**Clause 2 — "every failing id accounted for": NOT MET, by two ids.**

| id | account |
|---|---|
| `T078` | TASK-662 ✓ |
| `T087` | declared in `flaky.yaml` ✓ |
| `T_DTP_01`/`02`, `T_PLR_24` | TASK-686 ✓ |
| `T_PLR_06` | TASK-691 ✓ |
| **`T_PLR_15`** | **none** — no open row names it |
| **`T_WR_TLS_01`** | **none** — it is a `candidates:` entry, and §4 says *declaration* |

### Verdict: still FAIL, and deliberately not laundered

Two ids short. Filing rows for them **now** would make clause 2 read MET, and that is exactly what
this record must not do: §4 says *a pre-existing open row*, and satisfying a criterion by filing
paperwork against it after seeing the result is the shape LL-146 exists to prevent. They are filed
as **TASK-693** because they are real deterministic failures that need owners — **not** to close
this clause, which stays failed for this run.

### What it means

The criterion's PURPOSE — did TASK-575's fix break anything? — is answered twice over: clause 1 is
clean and §8's A/B showed an identical verdict set with the fix disabled. What remains is a
pre-existing backlog that has nothing to do with `_TeeSerial`, now down from a cluster to **two
unaccounted ids**.

Phase 3 entry therefore remains a scheduling judgement rather than a measurement — but a far
narrower one than on 09-12: two named ids instead of an unexplained cluster, with the
TASK-575-specific signature measured absent.

