# TASK-697 — fetches wedge after an in-session reboot: what is established

> Owner: @VE · 2026-09-13 · board `d48afcc8eed0`, `cyd2usb_winamp_debug` (elf `fb53f2b7`).
> Status: **cause not established.** This record exists so the next attempt starts from the evidence,
> not from the theory that was refuted on the way.

## Observed in full runs (2/2)

Both full `run/test` runs on 2026-09-13 lost ~22 Stock ids (FAIL, or PASS → SKIP), plus `T182`
and `T_DTP_01/02` UNMET, all inside the boot generation started by a `[REBOOT]` id in the PlaneRadar
family. The per-id diagnostics show `dataq` with a fetch in flight since ~2 s after boot and
`tlsStopped=True`, for the rest of the generation. PlaneRadar ids in the same generation time out
(`T_PR_05`, `T_PRM_02`, `T_PRI_01`).

## Targeted sequences (`run/test-targeted`, each a cold boot, n = 1 each)

| arm | ids | R14 check | result |
|---|---|---|---|
| A | `T_PRM_01,T_PRI_01,T170,T186` | on | T170, T186 **FAIL** |
| B | same | **off** (`DUT_ARMED_CHECK=0`) | T170, T186 **FAIL** |
| C | `T170,T186` | on | PASS |
| D | `T_PRM_01,T170` | on | PASS |
| E | `T_PRI_01,T170` | on | PASS |
| — | `T_PR_04,T_PR_05,T170` | on | PASS |
| F | `T_PR_04,T_PRI_01,T170` | on | T170 **FAIL** |

Refuted along the way:
- **the boundary check** — B fails the same as A;
- **`T_PRM_01`'s reboot specifically** — F fails with `T_PR_04`'s reboot, and full run 2 failed
  although `T_PRM_01` never reached its reboot.

What the arms share: **an in-session reboot, then `T_PRI_01`, then a Stock fetch.**

## The same bodies driven directly (`lib.dut`, no runner) — PASS twice

The probe ran `T_PR_04` → `T_PRI_01` → `T170` in one session, snapshotting `get dataq`/`get appId`/
`get armed` between steps. It **passed twice**: once with 5 s idle gaps between steps, and once
with no gaps. So the sequence is necessary, not sufficient, and timing decides. The snapshot
commands themselves may shift that timing.

What the snapshots showed, both times, right after the reboot and again right after `T_PRI_01`:
`inFlight=8` (a PlaneRadar fetch), `tlsStopped=true`, `spAct=1`, and `queueWaiting` up to 2. The
state cleared within ~10 s. Spotify `backoff.consecutiveFailures=6` at the end, consistent with
TASK-675's failing token refresh at every boot.

## Hypothesis — NOT verified

A Stock fetch enqueued while the dataTask's TLS is stopped for Spotify's post-boot activity, with a
PlaneRadar fetch in flight (re-armed by `T_PRI_01`'s own `set prClearInject 1`), can strand that
in-flight slot for the rest of the boot. That is the shape of the tlsYield hand-off layers fixed
under TASK-277/287/289/293/295. The next step is instrumentation, not another run: log the
`tlsStopped` edges and `inFlight` transitions on the DUT across a failing `run/test-targeted` F, so
the stuck transition is read rather than inferred.
