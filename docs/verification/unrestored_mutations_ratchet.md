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
| `suite/serialdbg/shell.py` | 36 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/player.py` | 34 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/planeradar.py` | 24 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/clock.py` | 12 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/teletext.py` | 3 | TASK-602 | 2026-09-05 |
| `suite/serialdbg/_helpers.py` | 2 | TASK-602 | 2026-09-05 |

**Total: 197** on the day the gate was written. `lib/dut.py` is at **zero** and has no row, and
cannot acquire one (M5).

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
