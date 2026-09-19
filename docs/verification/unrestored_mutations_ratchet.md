# Unrestored device writes — the R17 ratchet

> Owner: **@Developer** · Machine-read by `app/tools/gate/check_restore_manager.py` ·
> Opened **2026-09-05** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R17, TASK-602

## What this file is

[R17](M-HARNESS2-requirements.md) requires any state a test mutates to be restored through a
mechanism that runs on **every** exit path including failure, and forbids a restore that defaults to
a literal when the saved read is missing. TASK-602 landed that mechanism —
`Dut.saved()` and `Dut.injected()` in `app/tools/lib/dut.py` — and this gate, which asserts the
mechanism is **used**.

R17 is a **ratchet** ([requirements §14](M-HARNESS2-requirements.md)), not a flag day: 197 device
writes across eight suite modules are outside a manager today, and converting them is a per-module
migration with judgement in it (what the pre-state actually was, whether the variable is readable at
all). So the gate lands **blocking against this dated, per-module, shrink-only ledger**, enforced in
both directions — a cap above the real count is headroom to reintroduce the defect and is itself a
failure.

## What the gate counts

Every `dut.cmd("set …")`, `dut.send("set …")` or `dut.set_val(…)` in `app/tools/suite/` and
`app/tools/lib/` that is **not lexically inside** a `with` block on `Dut.saved(...)` /
`Dut.injected(...)` naming that variable.

**A `try/finally` is not credited, on purpose.** That is the whole design of R17's verification: a
`finally:` restoring the wrong variable, restoring from a defaulted read (`r.get('val', 0)` —
`C-12`/`D-15`/`E-4` did this to `playerMode` four times), restoring to a guessed constant, or
restoring with an unacknowledged `dut.cmd` all match a static "a restore exists" pattern and all
still leak. Each of those four is a fixture in `gate/test_check_restore_manager.py` that this gate
flags.

Two structural exemptions, both narrow and both checkable:

* the manager's own implementation in `lib/dut.py` (`saved`, `injected`, `_restore`, `set_val`) —
  writing state back is what those functions *are*;
* `SELF_REARMING_VARS`, currently one entry: `cooldown`. `shell::state().cooldownMs` is an absolute
  `millis()` deadline the shell rewrites on **every** consumed tap
  (`app/src/appShell.cpp:272,296,305`), so there is no state to leak and nothing a restore could put
  back. An entry here needs that: a cited line of firmware that rewrites the variable
  unconditionally.

## Checks

| id | what it fails on |
|---|---|
| M1 | a module holds more unrestored writes than its row allows |
| M2 | a row is **stale** — above the real count. Lower it; the ledger only shrinks |
| M3 | a row names a module that does not exist |
| M4 | a row without an owning `TASK-` id and an ISO `since` date, or with a wildcard |
| M5 | `lib/` holds a row at all. The managers live there; an unrestored write in the shared layer reaches every caller at once |
| M6 | a `DELEGATING_MANAGERS` entry that no longer delegates to `saved`/`injected` — a stale credit granted to every call site of that helper |

**How to refresh a row after a migration:**

```sh
cd app/tools && python3 gate/check_restore_manager.py --print-counts
cd app/tools && python3 gate/check_restore_manager.py --list suite/serialdbg/clock.py
```

**Migrate with:** `with dut.saved("playerMode", set_to=2): …` for anything with a read-back, and
`with dut.injected("triggerHeatmap", 1, clear_to=0): …` for a write-only injector, where the
clearing value is mandatory and not defaulted (BP-073: an injector ships with its clearing path).
A snapshot that cannot be read raises **before** the body runs — `NoAnswer` → `UNMET`, `BadField`
→ FAIL — so there is no path on which a restore writes a guess.

## Rows

| module | cap | owner | since |
|---|---|---|---|
| `suite/serialdbg/webradio.py` | 46 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/stock.py` | 40 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/shell.py` | 22 | TASK-615 | 2026-09-18 |
| `suite/serialdbg/player.py` | 32 | TASK-695 | 2026-09-13 |
| `suite/serialdbg/planeradar.py` | 25 | TASK-706 | 2026-09-18 |
| `suite/serialdbg/clock.py` | 12 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/teletext.py` | 1 | TASK-695 | 2026-09-13 |
| `suite/serialdbg/_helpers.py` | 2 | TASK-602 | 2026-09-05 |

**Total: 197** on the day the gate was written; **181** as of TASK-695 (2026-09-13) — B-taxonomy
review sites (`teletext.py` T270, `shell.py` T149/T150/T153/T154/T-BGPOLL-02/T-ERR-04/T-ERR-05,
`player.py` T_PLR_21/T_PLR_22/T_PLR_24 plus the `_bgpoll_backstop` timeout fix) moved to `saved()`/
`injected()`. `lib/dut.py` is at **zero** and has no row, and cannot acquire one (M5).

**What the remaining 197 cost.** Not uniform, and not blind. The cheap majority are a single
`set`/restore pair where the variable is in `gen_get_keys.py`'s generated list, so `saved(…,
set_to=…)` is a mechanical two-line change. The expensive minority are the write-only flags —
`bgPoll`, `wrDeadUrls`, `triggerHeatmap`, `prInjectAircraft`, `stockMode` (WP-B `B-5`) — where
`injected()` forces the author to write down a clearing value the firmware may not actually honour;
those three of them are the subject of TASK-579/580/581 and **should not be converted ahead of the
Phase 2 session that measures them**, because a clearing value nobody has observed working is a
second guess wearing a manager's clothes.

`_bgpoll_suspended` was converted as the worked example (`suite/serialdbg/_helpers.py`), and its
conversion is not cosmetic: it restored `bgPoll` to a literal `1` with an unacknowledged `cmd`, so a
caller that found it at 0 had its state rewritten and a refused restore read as a successful one. It
reads `bgPoll` back in the field `enabled`, not `val` (`app/src/spotifyTaskStorage.cpp:923`) — which
is the kind of fact a guessed restore never has to get right.

## Runtime findings (TASK-673)

**A second, machine-read section — one ledger, two ratchets.** The table above is a per-MODULE cap;
`check_restore_manager.py`'s runtime arm (`app/tools/gate/check_restore_manager.py:` see the module
docstring's "THE RUNTIME ARM" heading) asks a different, EXECUTED question that a static line count
cannot: on a poisoned replay of a recorded transcript that reaches a FAIL/UNMET verdict, was a
variable the body mutated ever set back afterward — attempted at all, whether or not the attempt hit
the transcript? A var with no later `set VAR` anywhere on that path is `NO_RESTORE_ATTEMPTED`,
R17's `C-15` shape observed rather than inferred. That cannot be expressed as a per-module count (one
unmanaged mutation site is usually shared by dozens of ids in the same module, so counting by id
would multiply one defect into dozens of rows for no information gain), so this section keys by
**variable** instead: one row per var the arm has observed leaking on at least one real FAIL/UNMET
replay, with one example id/path as evidence and the same discipline as the table above — dated,
owned, shrink-only, a stale row (the var no longer leaks) is itself a blocking failure.

`SELF_REARMING_VARS` (`cooldown`) is excluded here for the same cited reason as the static scan.
An id with no recorded transcript contributes nothing (a census line, not a finding — TASK-643 owns
growing the recorded set). A `set VAR` that WAS attempted after the mutation but never ACKED — it
either missed the transcript, or the device explicitly REFUSED it (`{"ok":false,...}`) — is not a
finding either: `RESTORE_ATTEMPTED_UNRECORDED`, printed by `--verbose`, never ledgered. See the
module docstring's "THE TRAP THIS AVOIDS" paragraph for why counting either as a leak would be
measuring the recording, not the suite.

**A LOWER BOUND, not a closed count.** "Any later `set VAR`, anywhere" credits a second, unrelated
mutation of the same var as if it were a restore — a body that mutates a var three times and never
actually restores it clears this arm on the second `set` alone. Measured in the corpus: `wrDeadUrls`,
`prPollSec`, `wrStop`, `wrAutoSkip`, `wrHwMod`, `wrMaxVol`, `wrPlay` and `spotifyWedge` all have
repeated same-var `set`s inside one id. `T_WR_VOL_CLAMP`'s were checked by hand — its `finally:`
genuinely restores the stock default `wrMaxVol 10` — but that was verified by reading the body, not by
this arm, and the arm would clear a real repeat-mutation leak of the same shape identically. Closing
this needs a VALUE-aware comparison (the eventual state against the pre-mutation snapshot), not
attempted here; see `lib/canfail.py`'s `_restore_leaks()` docstring.

**Opened 2026-09-19, corrected same day, 14 rows, from the live corpus (196 recorded ids).** All 14 are
pre-existing R17 defects the static ratchet above already prices in at the module level (`player.py`,
`webradio.py`, `stock.py`, `planeradar.py`, `clock.py`, `shell.py` cover every var below) — this table
is the first EXECUTED confirmation that each one is reachable on a real FAIL/UNMET path, not a
hypothetical one.

Five vars considered in earlier drafts of this table are NOT here, for two DIFFERENT reasons, both
found and corrected before this table shipped:

  * `lastHttp`, `lastOkMs`, `shellBusy` — each is `with dut.injected(...)`-managed and its restore
    fires promptly on `with`-exit, BEFORE a later `fail()` elsewhere in the body records the verdict.
    The first draft of this arm compared strictly "before the verdict" against "after it" and misread
    that ordering as a leak (`T-CDWN-02`'s shape; see `lib/canfail.py`'s `_restore_leaks()` docstring).
  * `bgPoll`, `songDuration` — a SECOND, SEPARATE defect, caught at review: the witness recorded
    "the command hit the transcript" as `ok`, when the actual question is "did the device ACK it".
    Both vars' example rows were driven by a REFUSE poison on the MUTATING `set` itself
    (`T-BUSY-01b`'s `dut.saved(...)`-managed `bgPoll`, `T085`'s raw-but-explicitly-restored
    `songDuration`) — REFUSE hits the transcript (no miss) but answers `{"ok":false,...}`, so
    `set_val`/the body's own `if not r.get("ok")` check aborts before anything is mutated OR restored.
    `_replied_ok()` (`lib/canfail.py`) now reads the actual reply instead of "did the lookup succeed".

**Not every row below is fixed by writing a set-back, and nobody should try** (added at review,
2026-09-19). The rows are what the arm measures — a `set` with nothing setting it back on a real
FAIL/UNMET path — and that is the same definition the per-module table above uses, deliberately.
But the vars fall into three kinds and the remedy differs:

  * **latched state**, where a set-back is exactly right: `clockStyle` (`T_CLK_03`
    (app/tools/suite/serialdbg/clock.py:39-53) sets `flip` and every `fail()` returns without
    putting the style back), `plCursor`, `playerMode`, `stockMode`, `prRange`, `backoff`.
  * **armed injectors**, where the remedy is a CLEAR, not a restore, and where leaving one armed
    is the shape that "wedged a family each for a whole run" in R14's record: `prInjectAircraft`,
    `prClearInject`, `triggerHeatmap`.
  * **one-shot actions with no field to put back**: `triggerFetch` is the clearest — the firmware
    handler (app/src/stock/stockApp.cpp:243-252) stores no `triggerFetch` flag at all; it zeroes
    `lastQuoteFetch`, `lastChartFetch`, `chartLen` and `fetchFailed` and discards a parked chart
    result. The residue is what it CLEARED, and no `set triggerFetch` value restores that. Closing
    such a row means re-establishing the cleared state or demoting the var the way
    `SELF_REARMING_VARS` demotes `cooldown` — with a cited firmware line, per that list's own rule.

Refresh with `python3 gate/check_restore_manager.py --print-runtime-rows` (from `app/tools`).

| var | example | owner | since |
|---|---|---|---|
| `backoff` | `T084` (perturb/at @3 `set backoff 5`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `clockStyle` | `T_CLK_03` (perturb/at @1 `set clockStyle flip`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `fetchErrCount` | `T-CDWN-04` (perturb/at @15 `set fetchErrCount 0`, verdict UNMET) | TASK-673 | 2026-09-19 |
| `fetchErrorCode` | `T186` (perturb/at @10 `set fetchErrorCode 0`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `fetchFailed` | `T186` (perturb/at @10 `set fetchFailed 0`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `plCursor` | `T_PLR_22` (perturb/at @21 `set plCursor -1`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `plLoad` | `T_PLR_08` (perturb/at @19 `set plLoad /playlists/gate100.m3u`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `playerMode` | `T-BUSY-03` (perturb/at @6 `set playerMode spotify`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `prClearInject` | `T_PR_03` (perturb/at @12 `set prClearInject 1`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `prInjectAircraft` | `T_PRI_01` (perturb/at @10 `set prInjectAircraft ...`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `prRange` | `T_PR_03` (perturb/at @12 `set prRange 5`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `stockMode` | `T-BUSY-01b` (drop/at @3 `set stockMode 0`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `triggerFetch` | `T-BUSY-01b` (drop/at @10 `set triggerFetch 1`, verdict FAIL) | TASK-673 | 2026-09-19 |
| `triggerHeatmap` | `T196` (perturb/at @4 `set triggerHeatmap 1`, verdict FAIL) | TASK-673 | 2026-09-19 |
