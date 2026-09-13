# TASK-636 — the first per-family shuffle: `player`, seed 42

> Owner: @VE · 2026-09-13 · board `d48afcc8eed0`, `cyd2usb_winamp_debug` flashed at `efe86b6f`.
> Instrument: `runner.py --shuffle-family` / `lib.artifact --order-dependence` (TASK-636, `8b4ac9d`).

## Runs

Same selection (`--scope LocalPlayer`, 24 ids), same firmware, run back to back. 22 of the 24 ids
moved within the family in the shuffled run.

| run | artifact | result | non-PASS |
|---|---|---|---|
| canonical 1 | `run-20260913T182343-1776924-2d50e92d` | 18 P / 4 F / 2 S | `T_PLR_10` (timeout + `bgPollOff` leak), `T_PLR_12`, `T_PLR_15`, `T_PLR_24` |
| canonical 2 | `run-20260913T183111-1782836-d252c209` | 20 P / 2 F / 2 S | `T_PLR_12`, `T_PLR_15` |
| shuffled, seed 42 | `run-20260913T183832-1797620-0887b556` | 18 P / 3 F / 2 S / 1 flaky-pass | `T_PLR_06`, `T_PLR_15`, `T_PLR_24` (timeout + `bgPollOff` leak) |

## The comparison

`python3 -m lib.artifact <shuffled> --order-dependence <canon1> <canon2>`:

| id | canonical (both agree) | shuffled | reading |
|---|---|---|---|
| `T_PLR_12` | FAIL, position 9 | **PASS**, position 16 | Consistent with TASK-686's in-suite-only failure. The heap residue depends on what ran before |
| `T_PLR_06` | PASS, position 3 | **FAIL**, position 5 | `no TLS-reset log line within 8 s`. TASK-691 already questions what this id asserts |
| `T_PLR_07` | PASS | FLAKY-PASS | **Not order dependence.** It is a declared flake that passed on retry, and the report should not label it — TASK-699 |

`T_PLR_24` and `T_PLR_10` were correctly **not** flagged, because the two canonical runs disagree
on them. That is the flake guard working.

**TASK-699, resolved 2026-09-13.** `order_dependence()` now treats PASS and FLAKY-PASS as the same
outcome for this comparison (`lib/results.py`'s `FLAKY-PASS` is only ever written when a mandated
retry itself returns PASS), so `T_PLR_07`'s row above is no longer labelled `ORDER-DEPENDENT`. It is
still reported — under `DIFFERS (flake-involved)` — rather than silently dropped, because a retry
firing in the shuffled run and not the canonical ones is itself a fact worth a human's attention, just
not proof of order dependence on its own. `T_PLR_12`/`T_PLR_06` above are unaffected: neither verdict
pair involves the flake-retry mechanism, so both keep the bare `ORDER-DEPENDENT` label.

## What this does not establish

One shuffled run at ~7 % non-stationary exposure. `T_PLR_12` and `T_PLR_06` are **candidates**,
not findings. R20's exit criterion ("per-family shuffled runs produce the canonical verdict set")
is **not met** for `player`. The capability exists and has been exercised, and the campaign that
would settle these ids is scheduled work.

## By-product

`T_PLR_24` timed out and leaked `bgPoll 0` again (TASK-635's boundary check caught it). TASK-695's
backstop (`c8234382`) lands after this run and is what should stop it.
