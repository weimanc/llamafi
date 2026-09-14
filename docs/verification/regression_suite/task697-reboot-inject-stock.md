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
| F | `T_PR_04,T_PRI_01,T170` | on | T170 **FAIL**, then PASS on a second run (with `LOG_FILE`) — **1 of 2** |

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

## Caught with raw serial, 2026-09-14 02:40 — the strongest evidence so far

With the event ring flashed (`d5b1a521`), `LOG_FILE=… ./run/test-targeted T_PR_04,T_PRI_01,T170` was
looped. Tries 1–2 PASSed; **try 3 FAILed `T170`**. The ring was not captured: `T170`'s failure
path does not call `_diag_snapshot`, and its own late `get fetchFailed` was refused `inactiveApp` by
TASK-637's guard, which is why it reports `'?'`. The raw serial log (`c697_serial_3.log`, 624 lines)
does show the mechanism:

- After the reboot, Spotify's backoff is reset (`backoff: consecutive=1 next=10000ms`). The
  spotifyTask then runs **back-to-back failing cycles**. Every poll or queue GET first attempts a
  token refresh that fails `-9984` (`accounts.spotify.com`, the TASK-675 pin rot), then
  `GET write fail, retrying` ×2 with `(-80)`. That is ~4 s per cycle (`spotify.queue status=-1
  elapsed=4263ms`, `block_max=4332ms`), and the cycles are separated only by the backoff.
- The Stock quote fetch does not start until the **very end** of `T170`'s 65 s window:
  `[spotify.tls] tls yield — client stopped` → `[dataTask.stock] spark GET -1 elapsed=107ms` →
  `tls yield — resumed`. It waited ~60 s for spotifyTask to reach its yield checkpoint, and then
  its own GET failed immediately.

**Reading, not proof:** TASK-697 is dataTask's TLS yield starved by a spotifyTask kept
permanently busy by TASK-675's failing token refresh. A reboot resets the backoff, so the failing
cycles come fastest exactly in the generation after an in-session reboot. That explains the reboot
dependence, the timing dependence, and why long sessions (backoff grown to 60 s) did not show it.
The deciding experiment is an A/B with TASK-675 fixed (a valid pin), or with Spotify polling held
off (`bgPoll 0`) across the same sequence. TASK-675 is **DEFERRED by the human**, and that deferral
now has a measured cost: this wedge, ~22 Stock ids in an affected full run.

Two harness findings on the way: `T170`'s failure path collects no `_diag_snapshot` (so no ring),
and its failure diagnostics read Stock keys after leaving Stock, which TASK-637's guard now refuses.

## CORRECTION, 2026-09-14 11:50 — the TLS-starvation reading above is WRONG

The mechanism recorded in the previous section was read from one log, and the lines that
contradict it were in the same log; I did not look for them. The heap lines were there.

**What the raw serial actually shows, in both failing captures** (`c697_serial_3.log` 02:40, and
`t705b_serial.log` 11:50, run inside TASK-705's combined selection):

1. `T_PRI_01` runs `set prRange 25` (a settings save), then `set prClearInject 1`, then two
   `set prInjectAircraft …` **while a real PlaneRadar fetch issued at switch-in is still in flight**.
2. That fetch's `GET 200` lands, and the next heap line reads **`maxBlk=31k`**. It was 45–47k
   before. It stays at 31k for the rest of the boot generation.
3. Every TLS handshake after that fails at once with **`-32512 SSL - Memory allocation failed`**:
   PlaneRadar's, Spotify's (`after -1: rc=-32512`) and Stock's (`spark GET -1 elapsed=104ms`,
   straight after an immediate `tls yield — client stopped`). Stock retries every 60 s, so
   `T170`'s 65 s window sees one or two failed attempts and no success.

The Stock fetch was **not** starved of the TLS yield: the yield acked at once, both times. The
"~60 s wait" in the previous section was Stock's 60 s retry cadence after a `-32512`, misread.
Spotify's failing `-9984` refreshes (TASK-675) are real but coincidental to this failure.

Passing tries in the same loop kept `maxBlk` at 33k or above at the Stock fetch (`c697_serial_1/2`).

**Reading, still not proof:** interleaving PlaneRadar's injected-aircraft allocations with an
in-flight real fetch's result processing, possibly with the settings save, fragments internal
heap so the largest free block falls below a TLS handshake's contiguous need. That matches the
sequence exactly in both captures, and the timing dependence: the injection has to land before
the in-flight fetch returns. It is the X010 family (TLS OOM), with a new trigger.

**What this changes:** TASK-697 is a heap-fragmentation defect around PlaneRadar injection, not a
TLS-yield hand-off defect. TASK-700 (`TlsYieldGuard`) and TASK-675 remain real but are not its
cause. The next evidence to collect is the largest free block across `T_PRI_01`'s steps
(`get heap` between each command), and the PlaneRadar allocation that survives the result.
