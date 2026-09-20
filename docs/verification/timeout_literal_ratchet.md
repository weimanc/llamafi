# Numeric `timeout=` literals — the R24 ratchet

> Owner: **@Developer** · Machine-read by `app/tools/gate/check_timeout_literals.py` ·
> Opened **2026-09-20** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R24, TASK-607

## What this file is

[R24](M-HARNESS2-requirements.md) (`docs/verification/M-HARNESS2-requirements.md:471-477`) asks for a single transport timeout policy in `lib/` with a
default and a slow-operation override, and asks that test bodies stop carrying numeric transport
timeouts. `app/tools/lib/dut.py` declared that policy (`TIMEOUT`, `TIMEOUT_SLOW`) as part of
M-TESTBASE P1 with **zero users** (`A-11`): 715 numeric `timeout=` literals lived in
`app/tools/suite/`, 446 of them exactly `TIMEOUT`'s default (`3.0`) and 20 exactly `TIMEOUT_SLOW`'s
(`10.0`).

TASK-607 migrated those two exact, unambiguous populations onto the policy names — a mechanical
keyword-position substitution, `timeout=3.0` -> `timeout=TIMEOUT` and `timeout=10.0` ->
`timeout=TIMEOUT_SLOW`, verified to change no call site's effective value under the (unchanged)
defaults. That leaves **249** literals that mean something call-site-specific — `2.0`, `5.0`, `8.0`,
`15.0`, and a handful of others — which R24's own ruling forbids folding into new policy constants:
"a policy with six constants is a rename of the problem, not a fix."

R24 is a **ratchet** ([requirements §14](M-HARNESS2-requirements.md)), not a flag day — 249 remaining
literals is not zero, and turning each into either `TIMEOUT`/`TIMEOUT_SLOW` (if a future audit finds
it was really the default/slow value in disguise) or a named, justified module-level constant is a
per-site judgement call, not a mechanical sweep. So the gate lands **blocking against this dated,
per-module, shrink-only ledger**, enforced in both directions exactly like
`unrestored_mutations_ratchet.md`'s: a cap above the real count is headroom to reintroduce the
defect and is itself a failure.

## What the gate counts

Every occurrence of the text `timeout=` immediately followed by a numeric literal (optionally
signed-free, with or without a decimal point — matches `timeout=2`, `timeout=2.0`, `timeout=15`,
...) in a `.py` file under `app/tools/suite/`. `timeout=TIMEOUT`, `timeout=TIMEOUT_SLOW`, and
`timeout=some_variable` do not match — those are already policy users, which is the point. Only
`app/tools/suite/` is in scope, per R24's own verification clause ("count of numeric `timeout=`
literals in `suite/`"); `app/tools/lib/` (where the policy itself lives, and where a slow-path
constant might legitimately be spelled as a literal inside the policy module) is out of scope for
this ratchet, mirroring how `unrestored_mutations_ratchet.md`'s M5 keeps `lib/` at zero-and-unledgered
rather than folding it into the same table — the two layers have different rules and shouldn't share
a row shape. (`app/tools/lib/dut.py` itself has no bare numeric `timeout=` literals to count either
way.)

## Checks

| id | what it fails on |
|---|---|
| T1 | a module holds more numeric `timeout=` literals than its row allows |
| T2 | a row is **stale** — above the real count. Lower it; the ledger only shrinks |
| T3 | a row names a module that does not exist under `app/tools/suite/` |
| T4 | a row without an owning `TASK-` id and an ISO `since` date, or with a wildcard |

**How to refresh a row after a migration:**

```sh
cd app/tools && python3 gate/check_timeout_literals.py --print-counts
cd app/tools && python3 gate/check_timeout_literals.py --list suite/serialdbg/stock.py
```

## Rows

Counted 2026-09-20 with `grep -roE 'timeout=[0-9]+\.?[0-9]*' app/tools/suite/*.py app/tools/suite/serialdbg/*.py | wc -l`
(249 total) after TASK-607's mechanical migration of the `3.0`/`10.0` populations.

| module | cap | owner | since |
|---|---|---|---|
| `suite/serialdbg/shell.py` | 76 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/player.py` | 73 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/webradio.py` | 54 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/stock.py` | 15 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/teletext.py` | 14 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/_helpers.py` | 7 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/runner.py` | 5 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/health.py` | 2 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/planeradar.py` | 2 | TASK-607 | 2026-09-20 |
| `suite/serialdbg/clock.py` | 1 | TASK-607 | 2026-09-20 |

**Total: 249** on the day the gate was written (down from 715 pre-migration; 466 literals — the
`3.0` and `10.0` populations — moved onto `TIMEOUT`/`TIMEOUT_SLOW`). What is left is not
undifferentiated debt: `2.0`/`5.0`/`8.0`/`15.0`/`20.0`/`30.0`/`180.0`/etc. are values a human picked
for a specific wait (a short poll interval, a long fetch, a soak-scale delay) and folding them into
the two-constant policy would be the "rename of the problem" R24 explicitly rules out. Shrinking a
row means looking at each remaining literal and deciding, per site: is it actually `TIMEOUT` or
`TIMEOUT_SLOW` in disguise (audit and reclassify), or does it deserve a named module-level constant
with a comment saying why (e.g. `_FETCH_TIMEOUT = 8.0  # NPO's slower mirror, TASK-XXX`) — a call
site spelled `timeout=_FETCH_TIMEOUT` is no longer a bare numeric literal at that line, so it drops
out of this gate's count once the constant is introduced. A ledger row that reaches 0 with no
remaining literals in that module can be deleted entirely, same as
`unrestored_mutations_ratchet.md`'s rule.
