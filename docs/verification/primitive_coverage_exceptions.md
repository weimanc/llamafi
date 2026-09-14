# Primitive operations that are not drivable today — the R-PRIM ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_primitive_coverage.py` ·
> Opened **2026-09-14** by TASK-705 · Background: TASK-697's reboot/inject/Stock
> wedge investigation (`docs/verification/regression_suite/task697-reboot-inject-stock.md`)

## What this file is

`suite/serialdbg/_meta.OPS` is a closed vocabulary of primitive operations that TASK-705's
coverage gate (`check_primitive_coverage.py`) requires each have a PRIMITIVE test — one id
declaring `@meta(ops=(that_op,))` and nothing else. Most ops in the vocabulary have one; this
ledger is for the ones that genuinely do not, because the operation cannot be driven from the
console on the firmware as it exists today. A row here is not an amnesty for "nobody got to it
yet" — that is a P1 finding this file cannot suppress.

Each row is keyed on the **op alone** (not an id): an op's drivability is a fact about the
firmware surface, not about any one test. `since` = the date the row was opened. A row whose
finding no longer occurs is itself a blocking failure — this ledger only shrinks.

## Ledger

| op | why | owner | since |
|---|---|---|---|
| `spotify_token_refresh_fail` | A live Spotify token refresh cannot be forced to fail from the console: `cmdSet.cpp`'s `certbreak` table (~707-729) arms a synthetic TLS-handshake failure for the dataTask fetchers (Weather/Crypto/Stock/Teletext/PlaneRadar/WebRadio) but deliberately excludes spotifyTask — there is no `set certbreak spotify` target. TASK-675 (the Spotify cert-pin-rot task) is today's live, uninjected instance of this exact failure mode; driving it synthetically needs a certbreak-table entry for spotifyTask, which is a firmware change, not a test. | TASK-675 | 2026-09-14 |

## How a row leaves

A firmware change adds the missing hook (here: a `certbreak spotify` arm point), a primitive test
is written against it, and the row is deleted in the same change that lands the test. The gate
fails on a row whose finding no longer occurs, so a fix that leaves the row behind is caught on the
next `run/check`.
