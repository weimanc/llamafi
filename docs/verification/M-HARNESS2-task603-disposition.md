# TASK-603 — disposition of the 35 ids the Developer proposed to remove

> Owner: **Verification Engineer**
> Status: **PREPARED, NOT EXECUTED** — this document changes nothing. No test body was
> edited and no id was deleted in preparing it. **Deleting a test body is a coverage change
> and the human rules on it.**
> Written: 2026-09-04 · Host-only: no DUT, no serial port, no flash.
> Board row: [TASK-603](../project/tasks-harness2.md), Phase 1, P2 — from
> [R34/R4](M-HARNESS2-requirements.md).
> Subject: [Developer review §8](../architecture/designs/M-HARNESS2-DEV-review.md) — 19 deleted,
> 8 retired to an `UNOBSERVABLE` record, 8 kept and fixed.
> Evidence: the eight M-TESTQUAL audits under [reviews/](reviews/), re-read against the bodies as
> they stand **after TASK-584, TASK-585, TASK-591 and TASK-596 landed**. Four of §8's evidence
> lines are stale for that reason and are corrected in place below.

Per the M-TESTQUAL rubric amendment A2 and the Developer review's own convention, **no table cell
in this document opens with a bare test id**: ids sit in the second column so `check_docs`' C6 id
binder does not read this document as a status declaration. It is a proposal, not coverage.

---

## 0. How to read this, and what it is for

The Developer's §8 is the first document in the programme to say *delete* out loud, and it is
right to. Three of the 216 ids are already a single `skip()` precisely because nobody had a
procedure for removing an id, so the corpus has been growing a class of test that costs suite time,
counts toward the 213-id total, and asserts nothing. §8 is the disposal.

What it is not is an authorisation. Each row below carries four things the human needs and §8
gives for some rows and not others:

* the **id, family and audit verdict**, so the claim is graded before it is judged;
* the **disposition with its evidence line** — the specific firmware or suite line that makes the
  disposition true, not the finding key;
* **what coverage is lost, concretely.** "Nothing — the assertion was unrepresentable" is the
  honest answer for most of them and is stated as such. Where it is *not* the answer, the row says
  what goes uncovered and whether anything else covers it;
* **where I disagree with the Developer**, with the reason. There are eight, collected in §4.

### 0.1 The counts

| | Developer §8 | This review | delta |
|---|---|---|---|
| delete outright | 19 | **12** | −7 |
| retire the body to an `UNOBSERVABLE` record | 8 | **6** | −2 |
| keep and fix | 8 | **17** | +9 |
| **total** | **35** | **35** | — |

Two of the +9 are ids §8 sent to `UNOBSERVABLE` that have a working observable today
(`T078`, `T_CLK_08`); four are the residue cluster TASK-584 has just made falsifiable; one is
`T093`, whose disposition was already decided the other way by TASK-591; and two are the
`T_MA_02` cluster held together rather than split 3-and-1 (§4.3) — those two land in "keep and fix"
only under the option the human may not choose, so §4.3 states both branches.

### 0.2 What is NOT in scope here

`T_PLR_25`'s registry copy (§8 row 19) is a *duplicate-body* disposal, not a coverage disposal, and
WP-A `A-15`/WP-E `§7` already adjudicated it: two executable bodies, one id, and the standalone
wins. It is listed for completeness and needs no coverage argument. TASK-586 has no board row
because it is inside this list — the board is explicit about that — so this document is the only
place it is now tracked.

---

## 1. Delete outright

Twelve of §8.1's nineteen. The seven that move are in §2 and §4.

| # | id | family | audit verdict | evidence line | coverage lost |
|---|---|---|---|---|---|
| 1 | `T136` | shell | **BROKEN** (WP-D `D-4`) | `app/tools/suite/serialdbg/shell.py:843-846` is the whole body: one unconditional `skip("T136", "merged into T137 precondition — run T137")`. Registered at `:3421` and dispatched every run. | **None.** The assertion moved into `T137`'s precondition, where it is a real `fail()` (`app/tools/suite/serialdbg/shell.py:863`). See §4.7 — the deletion has a documentation half that must land with it. |
| 2 | `T171` | Stock | **HOLLOW** (WP-G `G-16`) | `app/tools/suite/serialdbg/stock.py:155-158`: one `skip()`, labelled `[MANUAL — pixel verification required]`. | **None mechanically** — it never asserted anything. The *claim* (positive changePct rows green, negative red) is real and unobserved; it is not lost by the deletion because it was never held. It re-enters as a new id against ADR-064's `get sig`, not as a migration. |
| 3 | `T179` | Stock | **HOLLOW** (WP-G `G-16`) | `app/tools/suite/serialdbg/stock.py:411-414`: same shape. | As row 2. |
| 4 | `T178` | Stock | **HOLLOW** (WP-G) | Asserts `chartLen == 0` and `fetchFailed == false`, both written by its own `set triggerFetch 1` (`app/src/stock/stockApp.cpp:222-233`) with no firmware transition interposed. R2's canonical self-write oracle. | **None.** There is no interposed behaviour to lose. Note it is one of the twenty adjudicated `EDGE` rows in `_order.EDGE_ADJUDICATION`; deleting it removes a row from that enumeration and `test_class_order.py` will stay green because `unadjudicated()` shrinks. |
| 5 | `T185` | Stock | **HOLLOW** (WP-G) | Clears its own injected error with `set triggerFetch 1` before any fetch is enqueued (`app/src/stock/stockApp.cpp:325-327,338`) and never re-reads `fetchFailed`. | **None in this construction.** The claim ("an injected fetch error is cleared by a successful fetch") is real and must be re-filed as a new id that does not write the field it asserts on. ~65 s comes off a full run. |
| 6 | `T194` | Stock | **BROKEN** (WP-G `G-6`) | `drillTo()` assigns `chartSymbol[0] = '\0'` unconditionally (`app/src/stock/stockChart.cpp:75`), so the subsequent list drill produces an index-keyed ticker whether or not `backToPrevView()` cleared it. Its one `fail()` (`app/tools/suite/serialdbg/stock.py:1434`) compares a value with itself. | **None — unrepresentable by construction.** No body can hold this claim while `drillTo()` clears unconditionally; a different claim, or a firmware change, is required. |
| 7 | `T_PLR_02` | LocalPlayer | **HOLLOW** (WP-E) | Three rounds of `set playerMode X` / `get playerMode == X` for a claim about persistence **across reboot**, with no reboot in the body (`app/tools/suite/serialdbg/player.py:70-80`). | **None.** The persistence claim is real; the real test needs `Dut.reboot_and_wait` (`H-17`) and is a new id. **See §4.6 — `T_CLK_08` is the identical defect and §8 gives it a different disposition.** |
| 8 | `T_WR_ERR_01` | WebRadio | **HOLLOW** (WP-F `F-3`) | `set wrState N` / `get wrState == N` round trip through one `_state` member; `dbgSet` returns `true` for any input (`app/src/apps/webRadioApp.cpp:716-720`), so the `ok` check proves nothing either. | **None.** The named subject (a banner, an empty POSBAR) appears only in the pass string and has no oracle. |
| 9 | `T_WR_ERR_02` | WebRadio | **HOLLOW** (WP-F `F-3`) | As row 8. | As row 8. |
| 10 | `T_WR_ERR_03` | WebRadio | **BROKEN** (WP-F `F-1`) | Its "restore" re-writes the value it injected: the shared teardown writes `set wrState 3` believing it is STOPPED, and 3 is `ERROR_WIFI` (`app/src/apps/webRadioApp.h:36-44`; `app/tools/suite/serialdbg/webradio.py:511-513`). | **None.** It is also actively harmful: all four exit parked in an error state ahead of six ids whose oracle is `wrState == 2`. **See §4.5 — deleting these four closes TASK-583's subject and must do so explicitly.** |
| 11 | `T_WR_ERR_04` | WebRadio | **HOLLOW** (WP-F `F-3`) | As row 8; additionally reaches WebRadio only via `_switch_to(dut,"WebRadio")`, which taps slot 11 → `appIdx = 11 % 11 = 0`, the *player* slot (`E-11`). | As row 8. |
| 12 | `T_PLR_25`, the **registry copy** | LocalPlayer | **BROKEN** (registry copy) / **SOUND** (standalone) | Two executable bodies, one id (`app/tools/suite/serialdbg/player.py:1526` vs `test_playorder_player.py`); the registry copy has no variant guard and is a deterministic 60 s false red on the only env that dispatches it (`E-2`), and `run/player-gate` stays green only by omitting the id from leg A's list (`run/player-gate:84-87`). | **None** — the standalone body holds the claim and the gate's pass set already assumes it. Port the two things the registry copy does better first (WP-E §7 names them). 60 s off a full run. |

**Effect if all twelve go:** 213 → 201 registered ids (−5.6 %), and roughly 2½ minutes off a full
run (`T_PLR_25` 60 s, `T185` 65 s, the four `T_WR_ERR_*` and their teardown).

---

## 2. Retire the body, keep the claim as an `UNOBSERVABLE` record

Six of §8.2's eight. The two that move are `T078` (§4.1) and `T_CLK_08` (§4.6); `T093` moves too
(§4.2), and one id arrives here from §8.1 (`T_GOL_03`/`T_WX_03`/`T_CX_03`/`T172`'s *pixel* half,
§4.4) — that arrival is a half-claim, not a whole id, so it is counted in §4.4 and not here.

R4's mechanism is the point, and §8.2 states the load-bearing half correctly: **the body goes.** An
`UNOBSERVABLE` record with a live green body still prints green, which is exactly how `H-2` booked
five M-CLOCK-STYLES exit criteria as PASS.

| # | id | family | audit verdict | evidence line | coverage lost |
|---|---|---|---|---|---|
| 13 | `T_CLK_02` | Clock | **HOLLOW** (WP-H `H-3`) | A visual clock claim whose only oracle is a settings byte read back through the command that wrote it. | **None mechanically** — it asserted a value the harness wrote. The visual claim is real, is currently unobservable, and the ledger row is what stops it being re-counted as coverage. Owning task: ADR-064's `get sig` (TASK-638). |
| 14 | `T_CLK_09` | Clock | **HOLLOW** (WP-H `H-3`) | As row 13. | As row 13. |
| 15 | `T_CLK_13` | Clock | **HOLLOW** (WP-H) | Claims the flip **tick gate** (`app/src/apps/clockApp.cpp:31-33`, `gate = anyFlip ? 30 : 1000`); nothing in the body observes an interval, a frame count or `_anyFlipActive()` — there is no `dbgGet` for any of them, and the body says so in a comment (`app/tools/suite/serialdbg/clock.py:211-212`). | **None mechanically.** WP-H names the cheap fix — a `frames`/`gateMs` field on `get clockStyle` — which would make this SOUND without touching the body's shape. That makes the ledger row's owning task a *firmware* row, and a cheap one; it should not be filed behind `get sig`. |
| 16 | `T_CLK_14` | Clock | **HOLLOW** (WP-H `H-3`) | As row 13. | As row 13. |
| 17 | `T_WR_VOL_03` | WebRadio | **HOLLOW** (WP-F `F-7`) | Claims a volume behaviour and reads no volume — its only oracle is `wrState == 2` — and its `set wrVol 21` after `set wrStop 1` hits the no-live-session branch (`app/src/apps/webRadioApp.cpp:1104-1116`), so it may never have injected the value it exists to see overridden. | **None.** The observable (`webRadioMaxVolume` readback) is a four-line `dbgGet` case; the ledger row names that task. Note it is also one of `flaky.yaml`'s declared-but-never-calling-`flake()` mismatches (`C-7`) and one of the ids `F-4`'s `set wrDeadUrls` leak lands on — three findings on one id, and the retirement resolves only this one. |
| 18 | `T_PLR_03` | LocalPlayer | **HOLLOW** (WP-E `E-8`) | The "no leaked taskbar slot" assertion is arithmetically unrepresentable at the two chosen offsets: `appIdx = (tbScrollOffset() + slot) % TASKBAR_APP_COUNT` (`app/src/debug/serialConsole/cmdTouch.cpp:31`; the production path is `app/src/appShell.cpp:105`) cannot yield WebRadio or LocalPlayer. | **Disputed direction, agreed outcome.** §8.3 keeps this one and says "choose offsets that *could* select an eject-only app and it becomes a real test". That is right in principle and false in arithmetic: **no** offset can, because the modulus is the taskbar cycle length that *excludes* the eject-only apps (TASK-242). The claim is unrepresentable at every offset, not at two of them, so it belongs here and not in §3. |

---

## 3. Keep and fix

§8.3's eight, plus the nine that move here. Named so §1 is not read as "delete everything the audit
criticised" — this is now the largest of the three buckets, which is the right shape for a suite the
audits graded 54 % sound.

| # | id | family | audit verdict | evidence line | the fix |
|---|---|---|---|---|---|
| 19 | `T-BUSY-05` | shell/Stock | **BROKEN** (WP-C `C-1`) | The guard at `app/tools/suite/serialdbg/shell.py:2034` is inverted (WP-C cited `:1836`, TASK-591's ledger `:1961`; the line has drifted twice and the citation should be re-derived, not copied): `if any(b is not True for b in results)` is `False` exactly when all three post-switch reads are `True` — i.e. when the amber did **not** clear — so control falls through to `pass_()`. It passes precisely when the regression is present. | One predicate. Then **re-run**: the cell has been green on an untested path for its whole life, so nobody knows the answer either way. Already carried as one of TASK-591's four ledgered gating-class rows (**DEMOTE**, owner TASK-634) — it is a *seeded* CORE today, `cls_declared=False`. |
| 20 | `T-UART-01` | shell | **BROKEN** (WP-C `C-2`) | JSON garbling is detectable only via `JSONDecodeError`, which `lib/dut.py:1086-1090` swallows before returning the next well-formed line; the `ValueError` in its `except` is unreachable. | Fixable **only** by R25's correlated replies. It is the one id whose value is unlocked by that work and should be cited as R25's justification. Already demoted out of CORE with a written reason (TASK-591). |
| 21 | `T_WX_04` | Weather | **BROKEN** (WP-B `B-3`/WP-D `D-3`) | Dead by **position**, not construction: `T_WX_01/02/03` all switch to Weather at indices 158-160, so `weatherReady` is already `True` at 161 and the body takes its "already true" `skip()` every full run (`app/tools/suite/serialdbg/shell.py:1420-1424`). The field exists (`app/src/debug/serialConsole/cmdGet.cpp:422-425`) and the oracle is real. | An order adjudication or a `set weatherReady 0` reset. Owned by TASK-594. Neither id is in `EDGE_ADJUDICATION`, which is `B-4`'s point. |
| 22 | `T_CX_04` | Crypto | **BROKEN** (WP-B `B-3`) | Same shape at indices 163-166 (`app/tools/suite/serialdbg/shell.py:1535-1539`). | As row 21. |
| 23 | `T182` | Stock | **BROKEN** (WP-D `D-2`, WP-G) | Was: no *reachable* `fail()` on its subject — both taskbar failures its cross-feature claim is about exited via `skip()`, and the one `fail()` that guarded the arrival read (`if not r_app.get("ok")`) was unreachable, since `name` had already been read off that reply. | **Done — TASK-584.** Both taskbar exits are now `fail()`; the unreachable guard is replaced by `_restore_from_stock`'s real return-leg assertion; the two setup preconditions are `unmet()`. Keep: it is the family's only taskbar cross-feature test and the only place in the file that computes a slot from the generated registry instead of typing it. |
| 24 | `T_MA_03` | Matrix | **BROKEN** (WP-D `D-2`) | Was: no reachable `fail()`; the residue regression exited via `skip()` with a *false* excuse ("Spotify not rendering (not playing?)"). | **Done — TASK-584**, and the excuse is disproven in the code: `SpotifyApp::resume()` calls `invalidatePlaylist()` unconditionally (`app/src/apps/spotifyApp.cpp:27`) and `PleditView::draw()` stamps `_lastDrawMs` before it reads the queue count (`app/src/winamp/pleditView.h:139-156`). §8.3 additionally proposes re-aiming it at an ink-count signature under ADR-064 — agreed, as an *addition*; the repaint-clock half is now a real assertion and should not be dropped when the signature lands. |
| 25 | `T_GOL_03` | Life | **BROKEN** (WP-D `D-2`) | §8.1 row 7. **Evidence line stale — see §4.4.** | Kept, TASK-584 applied. Pixel half ledgered `UNOBSERVABLE`. |
| 26 | `T_WX_03` | Weather | **BROKEN** (WP-D `D-2`) | §8.1 row 8. **Stale — §4.4.** | As row 25. |
| 27 | `T_CX_03` | Crypto | **BROKEN** (WP-D `D-2`) | §8.1 row 9. **Stale — §4.4.** | As row 25. |
| 28 | `T172` | Stock | **BROKEN** (WP-D `D-2`, WP-G) | §8.1 row 10, "whose failure path is also a `skip()`". **Stale twice — §4.4:** it had two reachable `fail()`s before TASK-584 and now has three. | As row 25; it is additionally the only Stock↔Spotify transit test in the family. |
| 29 | `T078` | shell | **HOLLOW** (WP-D `D-5`) | §8.2 says "the marker it needs does not exist". **It does** — see §4.1. | Reuse `_tc_drag_collect(dut, cmd, ["enqueued ACT_VOLUME"])` and `fail()` if the list is non-empty, with the positive control §4.1 requires. |
| 30 | `T_CLK_08` | Clock | **HOLLOW** (WP-H `H-3`) | §8.2 groups it with five visual claims. WP-H's own §1 says otherwise — see §4.6. | Report `SettingsStorage::save()`'s return the way `set fmt24h` already does (`app/src/debug/serialConsole/cmdSet.cpp:634-638`), or reboot-and-read via `Dut.reboot_and_wait`. |
| 31 | `T093` | shell/rig | **HOLLOW** (WP-C) | §8.2 proposes "demote out of CORE + move to an interactive-only registry". Both halves are already decided the other way — see §4.2. | Fix the body (two `input()` prompts are its only oracles) and give the RIG class an executable entry point (`C-3`: no `run/` script passes `--interactive`). |
| 32 | `T_MA_02` | Matrix | **HOLLOW** (WP-D `D-1`) | The claimed regression is unrepresentable on the path the test drives — see §4.3, where all four `_02` ids are held together. | Branch A: give the four small apps a real `cmdTap` branch calling `handleInput()`. Branch B: delete all four. **Not** keep-one-delete-three. |
| 33 | `T_GOL_02` | Life | **HOLLOW** (WP-D `D-1`) | §4.3. | As row 32. |
| 34 | `T_WX_02` | Weather | **HOLLOW** (WP-D `D-1`) | §4.3. | As row 32. |
| 35 | `T_CX_02` | Crypto | **HOLLOW** (WP-D `D-1`) | §4.3. | As row 32. |

---

## 4. Where I disagree with the Developer, and why

Eight. I have read these bodies more recently than he has, and four of §8's evidence lines were
written before TASK-584, TASK-585, TASK-591 and TASK-596 landed. Each disagreement names the check
that settles it.

### 4.1 `T078` — the marker §8.2 says does not exist, exists

§8.2: *"The claim is right; the marker it needs does not exist and the body defers to a human via
`print()`."* The second clause is true. The first is wrong.

`LOG_D("touch", "enqueued ACT_VOLUME pct=%ld", …)` is emitted at **`app/src/winamp/winampDisplay.cpp:496`
and `:510`**. `app/tools/suite/serialdbg/shell.py:221` already greps `"enqueued ACT_VOLUME"` inside
`T082`, and `app/tools/suite/serialdbg/shell.py:2413-2415` collects it through `_tc_drag_collect(...,
["enqueued ACT_VOLUME", "drag-end commit"])` inside `T151`. WP-D `D-5` says this in terms — *"the
marker it needs is emitted, greppable, and already collected by two other ids in the same
module"* — and names the one-line fix.

**Disposition: keep and fix, not `UNOBSERVABLE`.** Ledgering it would book a permanent hole against
a claim that is one line from being tested, and an `UNOBSERVABLE` ledger whose rows are fixable is
the ledger that stops being read.

**One caveat the fix must carry.** `T078` is a *negative* log assertion, and WP-E `E-6` is that four
such assertions in the player family treat a `_wait_for_log` timeout as a pass on a suppressible
`LOG_D` channel, so "no commit" and "no logging" are the same result. The fix must therefore pair
the negative with a positive control in the same body — assert the marker **does** appear for a
non-zero drag — or it inherits `E-6` while resolving `D-5`.

### 4.2 `T093` — both halves of §8.2's disposition were decided the other way, on 2026-09-04

§8.2 proposes: retire the body to `UNOBSERVABLE`, **demote it out of CORE**, and move it to an
interactive-only registry.

`build_all_meta()` today reports `cls='RIG'`, `cls_declared=True`, with this written reason from
TASK-591: *"WP-C rates the body HOLLOW (both oracles are `input()` prompts) — that is a body defect
to fix, not a reason to move the claim out of RIG."* So the demotion is moot (it is not CORE and
has not been since TASK-591) and the relocation is the decision TASK-591 explicitly declined.

**Disposition: keep and fix.** The claim — the greyed titlebar is the operator's only out-of-band
signal that the board is in backoff — is what RIG *means*; a class whose members are ledgered
`UNOBSERVABLE` because they need a human is a class that has been defined out of existence. The
real defect is `C-3`: **no `run/` script passes `--interactive`**, so the RIG class has no
executable coverage in any shipped entry point and `T093` has never been runnable from a script.
Fix that (R40) and fix the body; do not ledger the claim.

### 4.3 The four `_02` ids must share a disposition — 3-delete-1-keep is the one outcome `D-1` forbids

§8.1 rows 4-6 delete `T_GOL_02`, `T_WX_02` and `T_CX_02` as *"three verbatim copies of `T_MA_02`
with one app name changed"*, and §8.3 keeps `T_MA_02` as *"the surviving representative"*.

They are verbatim copies — that part is exact. But WP-D `D-1`'s finding is not duplication, it is
that the assertion is a **tautology on the test's own precondition**: `hit == "CLOCK"` comes from
`cmdTap`'s terminal `else` (`app/src/debug/serialConsole/cmdTouch.cpp:141-144`), which calls no app
handler and no `injectTouch()`, on a branch selected by `currentAppId` — the value `_switch_to`
verified by `get appId` on the line before. The claimed regression, *"Winamp zones leak into a small
app"*, is **unrepresentable on that path**. That is a property of the assertion, not of the number
of copies, so the surviving copy is exactly as hollow as the three deleted ones. `D-1`'s own
recommendation ends: *"Do not leave a green row asserting a printf."*

**Disposition: one fate for all four.**
* **Branch A (recommended)** — give the four small apps a real `cmdTap` branch that calls
  `handleInput()` and reports `CONSUMED`/`NONE`, the shape `T148` is SOUND on
  (`app/src/debug/serialConsole/cmdTouch.cpp:134-140`). All four become real; coverage rises.
* **Branch B** — delete all four and record in `test_plan.md` that the small apps have no canvas
  interaction to test. Coverage lost: **none** (there was none), and the plan stops claiming it.

This choice must be made **here**. The board deliberately has no TASK-598 row — it is inside this
list — so if TASK-603 executes as §8 wrote it, Branch A is silently foreclosed and one tautology
survives as a green cell.

### 4.4 The residue cluster — §8.1's evidence line is stale, and the four ids are not one id

§8.1 rows 7-10 delete `T_GOL_03`, `T_WX_03`, `T_CX_03` and `T172` as copies of `T_MA_03`, on the
evidence *"none with a reachable `fail()`, all excusing the regression they exist to catch"*.

**Stale on both clauses, and one of them was wrong when written.**

* *The excuse* is confirmed disproven, and the disproof is now compiled into the failure strings:
  `SpotifyApp::resume()` calls `winampDisplay.invalidatePlaylist()` unconditionally
  (`app/src/apps/spotifyApp.cpp:27`); `PleditView::invalidate()` zeroes `_lastDrawMs` and sets
  `_scrollDirty` (`app/src/winamp/pleditView.h:175-179`), so the next `draw()` clears both
  early-return gates and stamps `_lastDrawMs = now` at `:143` — **before** it reads `src.count()`
  at `:156`; and `SpotifyApp::tick()` calls `drawPlaylist()` unconditionally
  (`app/src/apps/spotifyApp.cpp:67`). An empty, idle or 403-latched Spotify advances the clock exactly like a
  playing one.
* *"No reachable `fail()`"* is false as of TASK-584 for all four, and was **already false for
  `T172`** when §8 was written: `fail("T172", "could not switch to Stock")` and
  `fail("T172", "Stock->Spotify switch-back failed")` were both reachable. `T182`, which §8.3 also
  describes as having no reachable `fail()`, likewise had `fail("T182", "could not switch to
  Stock")`. WP-Z `D-2`'s summary sentence — *"six ids can PASS or SKIP and never FAIL"* — is
  therefore wrong for two of its six. The finding's substance stands; its count does not.

**On the merits.** The oracle is identical across the four, which is what makes them look like
copies. The *subject* is not: each id leaves a **different app**, and `lastPlaylistDraw` stops
advancing if the departed app wedged the shell's tick or left the TFT bus in a state
`_plView.draw()` blocks on. Four ids therefore discriminate four `tick()`/`pause()` paths —
`MatrixApp`, `LifeApp`, `WeatherApp`, `CryptoApp` — plus, for `T172`, the Stock↔Spotify transit,
which is the only one of the five that goes through `switchApp` rather than a taskbar tap.

**Disposition: split the claim, keep the ids.**
* Keep all five ids for the falsifiable half — *"the shell still repaints after leaving app X"* —
  which TASK-584 has just made reachable and which the proof harness exercises for each of them.
* Ledger the **pixel** half `UNOBSERVABLE` against ADR-064's `get sig`: `lastPlaylistDraw` cannot
  see a stale pixel, so "canvas residue" is not what these ids measure and the plan should stop
  saying it is.

If the human wants the count down anyway, the fallback is delete three and keep `T_MA_03` + `T172`
— but the survivors must then be **re-titled**, because a title claiming canvas residue against a
repaint-clock oracle is how `H-2` happened.

### 4.5 Deleting the four `T_WR_ERR_*` closes TASK-583's subject — make that explicit

I agree with §8.1 rows 11-14. The sequencing needs saying out loud: **TASK-583** (Phase 2, `F-1`,
*"the error-suite teardown writes the wrong state"*) is BLOCKED on TASK-634, and its subject is
precisely these four bodies' shared teardown. Executing this list in Phase 1 deletes TASK-583's
subject before Phase 2 opens. That is probably the right answer — you cannot fix a teardown shared
by four tautologies you are deleting — but it must be an **explicit close with a reason**, not an
orphaned row discovered later.

Second, the replacement §8 proposes (*"one new id that drives a real error path through the dead-URL
injector"*) is blocked on **TASK-579**: `set wrDeadUrls` is the injector nothing clears
(`F-4`), which is the defect eleven downstream WebRadio ids are already running behind. The new id
cannot be written until TASK-579 lands, so the four deletions leave the WebRadio error-path claim
genuinely uncovered for at least one phase. That is a real coverage gap and the first in this
document; it should be recorded as such rather than absorbed.

### 4.6 `T_CLK_08` and `T_PLR_02` are the same defect and §8 gives them opposite dispositions

Both are persistence claims whose body performs no reboot and reads the value back through the
command that wrote it. §8.1 row 17 **deletes** `T_PLR_02` and re-files it against
`Dut.reboot_and_wait`. §8.2 sends `T_CLK_08` to `UNOBSERVABLE` bundled with five *visual* clock
claims that need ADR-064's `get sig`.

`T_CLK_08` does not need `get sig`. WP-H's own §1 says so: *"reporting `SettingsStorage::save()`'s
return the way `set fmt24h` already does (`app/src/debug/serialConsole/cmdSet.cpp:634-638`) … would convert `T_CLK_13` and
`T_CLK_08` from HOLLOW to SOUND **without touching either body's shape**."* And the same
`Dut.reboot_and_wait` route §8 prescribes for `T_PLR_02` is open to it — `T_PR_04` and `T_PRM_01`
already do exactly that and are the corpus's only two genuine persistence tests.

**Disposition: keep and fix `T_CLK_08`** (row 30). Bundling it with the visual five mis-prices a
four-line firmware change as a blocked-on-ADR-064 ledger row, and — worse — parks it behind the
Clock family rewrite (TASK-639), which is where cheap fixes go to wait for expensive ones.
For the same reason, row 15 flags `T_CLK_13`'s ledger row as owned by a *firmware* task, not by
`get sig`.

### 4.7 The retirement procedure lands after the retirements it governs

TASK-625 — *"write the id-retirement procedure into `docs/process/`"* — is BLOCKED on TASK-603.
That ordering is backwards for at least `T136`, whose deletion has a documentation half that will
be got wrong without a procedure: its only `test_plan` declaration lives in
`test_plan-archive.md:1453` and still reads `Status: pass (2026-05-24 re-run post-fix)`;
`check_docs` scans the archive like any other file under `docs/verification/`
(`gate/check_docs.py:650`), so C6.1 resolves `T136` **through that stale row today**. Delete the
registry entry without touching the archive and C6 stays green while the corpus asserts a pass for
a test that no longer exists — the identical shape to `D-4`, one layer down.

**Recommendation:** land TASK-625 first, or concurrently, and make the archive correction plus the
`id_binding_exceptions.md` row part of each deletion's definition of done. This is cheap and it is
the difference between a retirement and a disappearance.

### 4.8 `T_PLR_03` — right instinct, wrong arithmetic

§8.3 keeps it: *"Choose offsets that could select an eject-only app and it becomes a real test."*
No offset can. `appIdx = (tbScrollOffset() + slot) % TASKBAR_APP_COUNT` (`app/src/debug/serialConsole/cmdTouch.cpp:31`,
mirrored at `app/src/appShell.cpp:105`), and `TASKBAR_APP_COUNT = (int)AppId::Settings + 1`
(`app/src/shell/taskbar.h:45`) is the taskbar cycle length that **excludes** the eject-only WebRadio and
LocalPlayer (TASK-242). The residue class is empty for every offset, not for the two chosen. WP-E
`E-8` says "arithmetically unrepresentable" without qualification.

**Disposition: `UNOBSERVABLE`** (row 18), owned by whatever makes an eject-only app reachable from
a taskbar index — which may be nothing, in which case the record says the claim is unrepresentable
by design and stops costing a test slot.

---

## 5. The no-reachable-`fail()` gate (R34) — specification only

**Not built.** This section is what makes TASK-603 executable once the human rules on §1-§4;
it is written so that the gate can be implemented without re-deriving any of it.

### 5.1 What it asserts

For every id in `build_all_tests()`, exactly one of:

1. the body has **at least one reachable `fail()`**, in the sense of §5.2; or
2. the id has a row in the `UNOBSERVABLE` ledger, dated, owned by a task that is not archived, and
   **its body has been deleted** (an `UNOBSERVABLE` id with a live body is a gate failure, not a
   ledger row — that is `H-2`'s mechanism and the gate exists to make it unrepresentable); or
3. the id has a row in the gate's own dated, shrink-only exception ledger.

And, as a second clause with its own count: **no body is one unconditional `skip()`** — the `T136`
/`T171`/`T179` shape. This is decidable without §5.2's analysis (a body whose only statement other
than `print()` is a `skip()` call) and is worth counting separately because it is the shape the
corpus has been growing for want of a deletion procedure.

Phase 1's exit criterion states both as one number: *"ids with no reachable `fail()` or a body that
is one unconditional `skip()` = **0**"*.

### 5.2 The shape of body it must catch

An AST walk over `_meta._reachable_source(fn)` — the existing transitive helper walk, six deep,
already used by `_order.edge_shape()` and `check_test_meta.py`, so the traversal is not new work.
Within that source, a `fail()` call is **reachable** unless it is dominated by a condition that is
statically constant. Four shapes must be caught, and the fourth is the one that makes the gate
worth building:

1. **No `fail()` anywhere in the reachable source.** The base case: `T_MA_03`, `T_GOL_03`,
   `T_WX_03`, `T_CX_03` before TASK-584. Trivially decidable.
2. **One unconditional `skip()` and nothing else.** `T136`, `T171`, `T179`.
3. **A `fail()` whose guard cannot be true**, given a value already established earlier in the same
   body. `T182`'s `if not r_app.get("ok"): fail(...)`, sitting three lines below a successful read
   of `r_app["name"]` off the same reply, is the corpus's instance. Full dominance analysis is not
   required and should not be attempted: the decidable subset is *a guard on a field of a reply
   dict whose truthiness was already required upstream in the same function*, which is a local
   pattern match, and anything outside it is left to review.
4. **A `fail()` guarded only by a helper that swallows its own read error and returns a `bool`.**
   This is the shape TASK-596's ratchet deliberately **cannot** see, and it must be stated
   explicitly because a gate that misses it will report zero while the defect is present. The
   canonical instance is in the tree today:

   ```python
   def _appid_is(dut, app_name, timeout=5.0) -> bool:
       try:
           return dut.get_str("appId", field="name", timeout=timeout) == app_name
       except DeviceReadError:
           return False
   ```

   `check_defaulted_reads.py` counts `.get(<key>, <literal>)` on a reply. There is no literal here
   and no `.get`: the default has moved into an `except` arm, and the two outcomes the typed
   accessor exists to separate — *the device said another app* and *the device said nothing* — are
   re-merged into one `False`. Every caller then spends that `False` on one verdict.

   The gate must therefore flag, as a body-level finding rather than a call-site one: **a function
   annotated `-> bool` (or returning only booleans) that catches `DeviceReadError`, `NoAnswer`,
   `BadField`, `TimeoutError` or bare `Exception` and returns a constant in the handler**, together
   with the ids whose only `fail()` is guarded by a call to it. Note that `_appid_is` itself is
   *legitimate* — its docstring says so, and TASK-596 consolidated four hand-rolled copies into it
   deliberately — so the finding is not "delete the helper". It is "this id's only `fail()` cannot
   distinguish a silent device from a wrong answer, so it must either read typed at the call site
   (which is what TASK-584 did for `T_MA_03`, `T_GOL_03`, `T_WX_03`, `T_CX_03` and `T182`) or
   carry a ledger row saying why not".

   **Consequence for the ledger's opening count:** this clause is what makes it non-zero. The
   twelve remaining `_appid_is` / `_switch_to` / `_restore_spotify` guards that gate a sole `fail()`
   are the ledger's initial population, not a reason to weaken the clause.

### 5.3 The negative test (BP-068)

Four arms, mirroring §5.2, each a synthetic body the gate is run against in-process:

* a body with a reachable `fail()` → **not flagged** (the control arm; without it the gate could
  pass by flagging everything);
* a body with no `fail()` → flagged, shape 1;
* a body that is one `skip()` → flagged, shape 2;
* a body whose only `fail()` is guarded by a `-> bool` helper with an exception-swallowing handler →
  flagged, shape 4.

Plus one **mutation arm** over the live corpus, in the shape `test_class_order.py` already uses for
TASK-553: revert one known-good id's `fail()` to a `skip()` in a copy of the source and assert the
gate's count rises by exactly one. A gate that cannot detect the regression it was written for is
`T-BUSY-05` with a different subject. TASK-584's own proof harness
(`app/tools/spike/task584_residue_verdicts.py`) demonstrates the mutation arm working on this exact
defect and can be read as the pattern.

### 5.4 The opening ledger

Blocking-at-zero is not available on day one, so the gate lands **blocking with a dated,
owned, shrink-only ledger whose stale rows are themselves blocking failures** — the board's
standing condition, and the form `check_defaulted_reads.py` and `gating_class_declarations.md`
already take.

The opening ledger holds, and holds nothing else:

| holds | why it is not zero on day one | owner |
|---|---|---|
| the ids in §2 and §4.4's ledgered half, until their bodies are deleted | R4's records are written before the bodies go; between those two commits the ids are live and unfalsifiable by design | TASK-603 execution |
| the shape-4 ids from §5.2 | the `_appid_is`-class guards TASK-596's ratchet cannot see; each needs a call-site decision, not a sweep | TASK-596 follow-on |
| `T093` | RIG, and its oracles are a human's eyes until `C-3` gives the class an executable entry point | TASK-589 / R40 |
| **nothing else** | every other id in the corpus either has a reachable `fail()` today or is in §1's delete list | — |

Two properties the ledger must have, both of which the programme has already paid for once:

* **Shrink-only, enforced.** A row may be removed; a row may not be added without the gate failing.
  This is what stops the ledger becoming the thing the gate measures.
* **Stale rows are blocking failures.** A row whose owning task is archived (the `SPIKE` check's
  rule, `check_docs.py:317-350`) fails the gate. Without this, a ledger row outlives its owner and
  the gate reads zero forever — which is the `C3` shape the PM review cut ~60 days of ratchets to
  avoid re-creating.

**Expected opening count:** to be measured by the gate's first run, not guessed here. The
programme's discipline is that every number is measured, and this document has no way to count
shape 3 and shape 4 without writing the walk.

---

## 6. What this document does not decide

* **Whether to delete anything.** The human rules. Nothing here has been executed.
* **`T171`/`T179`'s and the clock family's re-entry as new ids.** They are new ids against ADR-064,
  not migrations, and belong to TASK-638/TASK-639.
* **The plan-side corrections.** Each deletion needs its `test_plan.md` / `test_plan-archive.md` row
  and its `id_binding_exceptions.md` entry; §4.7 argues TASK-625 should define that first.
* **`T_PLR_25`'s two ported improvements.** WP-E §7 names them; porting them is part of executing
  §1 row 12, not part of deciding it.
