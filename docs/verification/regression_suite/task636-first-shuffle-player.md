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

## Campaign continued, 2026-09-14 01:02–02:21 — `clock`, `planeradar`, `webradio` (seed 42)

Same design: two canonical runs and one shuffled, `--scope <Family>`, one flash, board `d48afcc8eed0`.

| family | canonical 1 | canonical 2 | shuffled | comparison |
|---|---|---|---|---|
| `clock` (11) | 11 P | 11 P | 11 P | **0 differ — the canonical verdict set reproduced under shuffle** |
| `planeradar` (9) | `T_PRM_02` F | `T_PR_05`, `T_PRM_01` F | `T_PR_05`, `T_PRM_02` F | 0 flagged, but **the canonical runs disagree with each other**, so the comparison has nothing to hold |
| `webradio` (25) | `T_WR_TLS_01` F | `T_WR_TLS_01` F (+ `T_WR_EJECT_01` flaky-pass) | `T_WR_TLS_01`, **`T237`** F | **`T237` ORDER-DEPENDENT candidate** (PASS at position 16 → `TimeoutError` at position 5) |

R20's exit ("per-family shuffled runs produce the canonical verdict set") is **met for `clock` only**.
`planeradar` is non-stationary on its own before order is involved: `T_PR_05` times out and
`T_PRM_01` read `prPollSec=1 after reboot, expected 30`.

## Second `player` shuffle, seed 7, 2026-09-16 21:02 — board reflashed to `95e8ebe0`

Same selection (`--scope LocalPlayer`, 24 ids, `DUT_SHUFFLE_SEED=7 ./run/test-targeted --scope
LocalPlayer` — the wrapper only accepts the env-var form; `--shuffle-family SEED` as a CLI arg to
`run/test-targeted` is not supported and errors out before touching the DUT, board reboot handshake
notwithstanding). 22 of 24 ids moved
([artifact](../../../app/tools/.runs/run-20260916T210200-167530-33cb2e57.json)): `T_PLR_15`,
`T_PLR_12` FAIL; `T_PLR_06`, `T_PLR_24` PASS.

Compared with the two 2026-09-13 canonicals (both agree `T_PLR_12`, `T_PLR_15` FAIL): this
seed-7 shuffle reproduces the **canonical** verdict on `T_PLR_12` — the opposite of what the
seed-42 shuffle showed (`T_PLR_12` PASS at position 16 there). `T_PLR_06`, flagged
ORDER-DEPENDENT under seed 42 (PASS→FAIL), is back to PASS here, matching canonical.

**Reading: `T_PLR_12`/`T_PLR_06` are not a stable, seed-independent order-dependence — they flip
depending on which specific permutation ran.** `T_PLR_12`'s own failure text is a heap-residual
check (`heap did not return to baseline: +55364B`), which is the same shape of symptom TASK-697
is chasing (post-activity heap fragmentation, cause not yet named). The working hypothesis is that
these two ids are heap-state-dependent flake, gated by *which* ids happened to run immediately
before them rather than by "shuffled vs canonical" as a category — consistent with TASK-697's
open lead, not a separate order-dependence bug. This still leaves R20's "reproduces the canonical
verdict set" criterion **unmet for `player`**, but for a different reason than first assumed:
not a clean order-dependent test, but the same unresolved heap issue surfacing under more seeds.

## Second `webradio` shuffle, seed 7, 2026-09-16 21:07 — same board/flash as above

`DUT_SHUFFLE_SEED=7 ./run/test-targeted --scope WebRadio`, 25 ids, 23 moved
([artifact](../../../app/tools/.runs/run-20260916T210729-170639-6639fd40.json)). `T_WR_TLS_01`
FAIL (as in every run on record so far — a standing network/TLS issue, TASK-675 territory, not
order-related); `T237` **PASS**, matching canonical and the opposite of what seed 42 showed
(`T237` FAIL there). Same flip-by-permutation pattern as `player`'s `T_PLR_12`/`T_PLR_06` above,
not a stable seed-independent order-dependence.

**Two families, same shape.** `player` and `webradio` both produced an ORDER-DEPENDENT candidate
under seed 42 that reverted to the canonical verdict under seed 7. Read together with `planeradar`'s
canonical instability (three canonical runs, no two agreeing) this now looks like one thing across
all three non-`clock` families: state-dependent flake sensitive to exactly which ids ran
immediately before, surfacing differently depending on the specific permutation — not a
deterministic bug in any one test's ordering assumption. R20's exit clause needs a decision on
what to do with that reading (declare a flake class vs. treat as TASK-697's unresolved lead vs.
run enough seeds to bound it statistically) rather than more single shuffles at new seeds, which
keep reproducing the same ambiguity.

**A finding for TASK-697:** `T_PRM_02` (shuffled) reported `spotifyTask activity stamp went
306382ms stale (>120s)` under continuous PlaneRadar fetching. A spotifyTask that stops making
progress is what TASK-697's code reading predicts: `tlsYield()` can wait 150 s, and `TlsYieldGuard`
records success unconditionally. Recorded as a correlation, not a cause.

## Third canonical run, `planeradar` only, 2026-09-16 20:42 — board reflashed to `95e8ebe0`

`DUT_SHUFFLE_SEED=42 ./run/test-targeted --scope PlaneRadar` (no `--shuffle-family`, so this is a
third *canonical*-order data point, not a shuffle): `T_PR_05` FAIL, `T_PRM_02` FAIL, `T_PRM_01`
PASS ([artifact](../../../app/tools/.runs/run-20260916T204215-155994-3294ec82.json)).

Across all three canonical runs now on record: `T_PR_05` FAIL 2/3, `T_PRM_02` FAIL 2/3, `T_PRM_01`
FAIL 1/3 — no two canonical runs agree with each other on the failing set. Both `T_PR_05` and
`T_PRM_02` carry `[NETWORK][SLOW]` tags (`TimeoutError: no JSON response within 3.0s`); this reads
as fetch-latency flake independent of run order, not as evidence for or against order-dependence.
**`planeradar` cannot supply the "two agreeing canonical runs" precondition the shuffle comparison
needs, and a fourth run is unlikely to change that** — the instability is upstream of the shuffle
question. Filing this as a decision point for the human rather than spending more DUT time chasing
canonical agreement: either declare these two ids' network-timeout flake out of scope for R20's
per-family criterion (they'd need their own flake declaration / retry budget, `gate/check_flake_class.py`
territory), or accept `planeradar` as a standing exception to the exit clause.
