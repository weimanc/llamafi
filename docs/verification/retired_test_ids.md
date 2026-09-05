# Retired test ids — the register

> Owner: **@VE** · Opened **2026-09-05** by [TASK-603](../project/tasks-harness2.md)
> Procedure: [docs/process/test_id_retirement.md](../process/test_id_retirement.md)
> Machine-read by `app/tools/gate/check_no_reachable_fail.py` (the `UNOBSERVABLE` half).

## What this file is

The terminal record for every test id removed from the executable corpus. It exists because a
deleted test is a **coverage change**, and a coverage change that leaves no record is
indistinguishable from a test that was never written.

Two dispositions, defined in the procedure:

* **`deleted`** — the claim is not one the project holds. Nothing is owed. The row is permanent.
* **`UNOBSERVABLE`** — the claim is real and cannot be observed today. The row carries an owning
  task and states what would make it observable. **The body is deleted either way**: an
  `UNOBSERVABLE` record above a live green body is `H-2`'s mechanism, and R34 fails on it.

**A row here is a record of missing coverage, never coverage.** No milestone exit criterion may
read PASS on the strength of a row in this file.

The `Status` column is what `check_docs` C6 reads. It is deliberately *not* one of C6.3's binding
tokens (`impl`/`resv`/`blocked`), because none of them is true of a retired id.

---

## `deleted` — 12 ids, 2026-09-05, TASK-603

Dispositions and evidence: [M-HARNESS2-task603-disposition.md](M-HARNESS2-task603-disposition.md) §1.

| id | Status | family | why | coverage lost |
|---|---|---|---|---|
| `T136` | retired 2026-09-05 (TASK-603) — `deleted` | shell | body was one unconditional `skip("T136", "merged into T137 precondition — run T137")` | **none** — the assertion is a real `fail()` inside `T137`'s precondition |
| `T171` | retired 2026-09-05 (TASK-603) — `deleted` | Stock | body was one `skip()`, labelled `[MANUAL — pixel verification required]` | **none mechanically** — it never asserted anything. The colour-coding claim re-enters as a *new* id against ADR-064's `get sig` (TASK-638), not as a migration |
| `T179` | retired 2026-09-05 (TASK-603) — `deleted` | Stock | as `T171` | as `T171` |
| `T178` | retired 2026-09-05 (TASK-603) — `deleted` | Stock | asserted `chartLen == 0` / `fetchFailed == false`, both written by its own `set triggerFetch 1`, with no firmware transition interposed — R2's canonical self-write oracle | **none** — there was no interposed behaviour to lose |
| `T185` | retired 2026-09-05 (TASK-603) — `deleted` | Stock | cleared its own injected error before any fetch was enqueued and never re-read `fetchFailed` | **none in this construction.** The claim (an injected fetch error is cleared by a successful fetch) is real and must be re-filed as an id that does not write the field it asserts on. ~65 s off a full run |
| `T194` | retired 2026-09-05 (TASK-603) — `deleted` | Stock | `drillTo()` clears `chartSymbol` unconditionally, so its one `fail()` compared a value with itself | **none — unrepresentable by construction.** A different claim, or a firmware change, is required |
| `T_PLR_02` | retired 2026-09-05 (TASK-603) — `deleted` | LocalPlayer | three `set playerMode X` / `get playerMode == X` round trips for a claim about persistence **across reboot**, with no reboot in the body | **none.** The persistence claim is real; the real test needs `Dut.reboot_and_wait` and is a new id (TASK-615) |
| `T_WR_ERR_01` | retired 2026-09-05 (TASK-603) — `deleted` | WebRadio | `set wrState N` / `get wrState == N` through one `_state` member; `dbgSet` returns `true` for any input, so the `ok` check proved nothing either | **see the gap note below** |
| `T_WR_ERR_02` | retired 2026-09-05 (TASK-603) — `deleted` | WebRadio | as `T_WR_ERR_01` | as above |
| `T_WR_ERR_03` | retired 2026-09-05 (TASK-603) — `deleted` | WebRadio | as `T_WR_ERR_01`, and its shared teardown wrote back the value it injected (`set wrState 3` believed to be STOPPED; 3 is `ERROR_WIFI`), parking all four in an error state ahead of six ids whose oracle is `wrState == 2` | as above |
| `T_WR_ERR_04` | retired 2026-09-05 (TASK-603) — `deleted` | WebRadio | as `T_WR_ERR_01`; additionally reached WebRadio via a taskbar tap that lands on the *player* slot | as above |
| `T_PLR_25` (registry copy only) | *not retired — see note* | LocalPlayer | the duplicate body in `suite/serialdbg/player.py`'s `TESTS` was deleted; it had no variant guard and was a deterministic 60 s false red on the only env that dispatched it | **none.** The id is still `impl`: its sole executable body is `app/tools/test_playorder_player.py`, now carrying an `ALL_TESTS` declaration so C6 binds it there. This is a duplicate-body disposal, not a coverage disposal |

---

## `deleted` — 1 id, 2026-09-05, TASK-632

| id | Status | family | why | coverage lost |
|---|---|---|---|---|
| `T_DOC_08` | retired 2026-09-05 (TASK-632) — `deleted` | host gate (`check_docs`) | its subject was check **C3** (`cyd2usb*` build-env names in docs vs `app/platformio.ini`), and C3 itself was deleted rather than promoted. C3 stood advisory for two months at 58-60 findings; measured, **all 58 are correct prose in living documents** — 21 in ADR-061, the decision that *deleted* `cyd2usb`; 10 in C3's own specification quoting its own failure list; the rest archives, closed designs, and `CLAUDE.md`'s note on why the env is excluded from the build matrix. A check whose only honest fix is to falsify the record cannot be cleared honestly (QM's rot rule (c)) | **none.** The residual signal was measured separately: env names in an actionable context (`-e X`, `*ENV*=X`) number 19 corpus-wide, 2 unresolved, both in an archive and a closed design. `pio run -e <missing>` fails on the next command; the sub-signal never needed a gate. The number `T_DOC_08` is not reused |

### The one genuine coverage gap: the WebRadio error path

Deleting the four `T_WR_ERR_*` bodies removes nothing that was being asserted — but it does leave
the WebRadio **error-path** claim with no id at all, and that is a real gap, not an accounting one.

* **`TASK-583`'s subject is closed by this deletion.** Its subject was "the error-suite teardown
  writes the wrong state" (`F-1`), and that teardown was `_wr_err_test`, shared by exactly these
  four bodies and deleted with them. You cannot fix a teardown shared only by four tautologies you
  are deleting. Closed explicitly, with that reason, on the board — not orphaned.
* **The replacement id is `T_WR_ERR_05`, and it is `blocked`.** It must drive a real error path
  through the dead-URL injector rather than round-tripping an enum, and it cannot be written until
  **TASK-579** lands (`set wrDeadUrls` is the injector nothing clears — `F-4`, the defect eleven
  downstream WebRadio ids already run behind). Its `test_plan.md` row records what is uncovered in
  the meantime: **no id asserts that any WebRadio error state produces its banner, or that
  `ERROR_*` empties the POSBAR.** That is uncovered from 2026-09-05 until TASK-579 and then
  TASK-583's successor land.

---

## `UNOBSERVABLE` — 6 ids, 2026-09-05, TASK-603

Dispositions and evidence: [M-HARNESS2-task603-disposition.md](M-HARNESS2-task603-disposition.md) §2 and §4.8.

Every row: the body is **deleted**, the claim is **carried**, and no milestone criterion resting on
it may read PASS.

| id | Status | family | the claim, which is real | why it cannot be observed today | what would make it observable | owner |
|---|---|---|---|---|---|---|
| `T_CLK_02` | UNOBSERVABLE since 2026-09-05 (TASK-638) | Clock | the clock renders in the digital style by default | its only oracle was a settings byte read back through the command that wrote it | ADR-064's `get sig` render signature | TASK-638 |
| `T_CLK_09` | UNOBSERVABLE since 2026-09-05 (TASK-638) | Clock | the style survives an app-switch round trip | as `T_CLK_02` | as `T_CLK_02` | TASK-638 |
| `T_CLK_14` | UNOBSERVABLE since 2026-09-05 (TASK-638) | Clock | `get clockStyle`'s reply shape (`val` int, `name` str, `last` true) reflects the rendered style | as `T_CLK_02` — the shape is the harness's own echo | as `T_CLK_02` | TASK-638 |
| `T_CLK_13` | UNOBSERVABLE since 2026-09-05 (TASK-615) | Clock | the Flip style's tick gate runs at 30 ms while animating and 1000 ms stable | nothing observes an interval, a frame count or `_anyFlipActive()`; there is no `dbgGet` for any of them, and the deleted body said so in a comment | **a firmware change, not `get sig`**: add `frames`/`gateMs` fields to `get clockStyle`. Cheap; deliberately not filed behind the Clock family rewrite | TASK-615 |
| `T_WR_VOL_03` | UNOBSERVABLE since 2026-09-05 (TASK-615) | WebRadio | normal `_play()` applies `g_settings.webRadioMaxVolume` as the ceiling, not 21 | the body read no volume at all — its only oracle was `wrState == 2` — and its `set wrVol 21` after `set wrStop 1` hit the no-live-session branch, so it may never have injected the value it existed to see overridden | a `webRadioMaxVolume` readback: a four-line `dbgGet` case | TASK-615 |
| `T_PLR_03` | UNOBSERVABLE since 2026-09-05 (TASK-614) | LocalPlayer | no taskbar slot ever selects an eject-only app (WebRadio, LocalPlayer) | **arithmetically unrepresentable at every offset**, not at the two chosen: `appIdx = (tbScrollOffset() + slot) % TASKBAR_APP_COUNT`, and `TASKBAR_APP_COUNT` is the taskbar cycle length that *excludes* the eject-only apps by construction (TASK-242) | something that makes an eject-only app reachable from a taskbar index — which may be nothing. **The owning task's job is to decide that**, and if the answer is "nothing", to convert this row to `deleted` | TASK-614 |

### Note on `T_CLK_08`, and on the four residue ids

Two ids the Developer's §8 sent to `UNOBSERVABLE` are **not** here, deliberately:

* **`T_CLK_08`** has a working observable today — report `SettingsStorage::save()`'s return the way
  `set fmt24h` already does — so it is keep-and-fix, not a ledger row. Bundling it with the visual
  five would price a four-line firmware change as a blocked-on-ADR-064 deferral. Fixed under
  TASK-603; see §3 of the disposition.
* **`T_GOL_03` / `T_WX_03` / `T_CX_03` / `T172` / `T_MA_03`** keep their ids and their bodies. Only
  the **pixel half** of their claim is unobservable: `lastPlaylistDraw` is a repaint clock and
  cannot see a stale pixel. That half is recorded here as a half-claim rather than as six more ids,
  because the falsifiable half — *the shell still repaints after leaving app X* — is live, is
  reachable since TASK-584, and discriminates five different `tick()`/`pause()` paths.

| claim | Status | owner |
|---|---|---|
| canvas **pixel** residue after leaving Matrix / Life / Weather / Crypto / Stock (the half of `T_MA_03`, `T_GOL_03`, `T_WX_03`, `T_CX_03`, `T172` that a repaint clock cannot see) | UNOBSERVABLE since 2026-09-05 (TASK-638) | TASK-638 |
