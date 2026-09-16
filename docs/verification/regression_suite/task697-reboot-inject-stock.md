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

## 2026-09-14 afternoon — rate measured; the first allocation candidate REFUTED

**Baseline, log-only, 8 tries** (`run/test-targeted T_PR_04,T_PRI_01,T170` with `LOG_FILE`, no extra
commands, `efe86b6f`-era firmware plus the event ring): **4 of 8 FAIL.** The correlation is exact: all
4 FAILs show `maxBlk=31k` and 18 × `-32512`; all 4 PASSes stay ≥ 33k with no `-32512`. The console
sequence is identical in all 8 (both injections precede the in-flight fetch's `GET 200`). Only the
`maxBlk` after that result differs: 31k in FAILs; 33k, 37k, 39k and 43k in PASSes. So the outcome
depends on placement, not command order.

**A heap-probe run** (the same commands plus `get heap`/`get dataq` every second, 4 attempts)
reproduced **0 of 4** (min `maxBlk` 35k). The probe perturbs the timing, and it omits `get prInterp`.

**Candidate 1 — PlaneRadar's lazily allocated, never-freed motion table** (`new PrMotion[24]`,
~480 B, `planeRadarApp.cpp` `_ensureMotion()`), first allocated at the first injection while the
in-flight fetch's TLS buffers were live. **A/B: allocated eagerly in `init()`, before the first
fetch, then the same 8-try loop: 5 of 8 FAIL**, with the same signature. **Refuted.** The change
was reverted and never committed.

**What is left:** the drop to 31k is placement-dependent and happens when that fetch's result is
processed. An allocation-level instrument is needed now, not another candidate guessed from code:
per-region free-block stats (`heap_caps_print_heap_info(MALLOC_CAP_8BIT)` is available on IDF 4.4)
immediately before and after the PlaneRadar result lands, in a FAIL and in a PASS.
The internal heap on this chip is several disjoint regions, so a 31k ceiling may be one region's
remaining span rather than a mid-block survivor.

## Gate 0 (pre-registered, M-DATATASK-heap-region-instrument), 2026-09-14 16:41–18:42 — FAILED: perturbing

Same commit (`8af4a0a2`), board `d48afcc8eed0`, `run/test-targeted T_PR_04,T_PRI_01,T170` with
`LOG_FILE`, 8 tries per arm, a fresh flash per arm, the OFF arm first.

| arm | build | FAIL | PASS | other |
|---|---|---|---|---|
| OFF | `PLATFORMIO_BUILD_FLAGS=-DHEAP_REGION_DUMP_OFF` (dump absent) | **3** (4, 5, 8) | 5 | 0 |
| ON | default (dump fires at points 0, 1 and 2) | **2** (3, 4) | 0 | **6**: `T170` SKIP "could not switch to Stock" ×5, UNMET "no reply to `get quoteOkCount` within 3.0s" ×1 |

The OFF arm reproduces the baseline and the signature exactly: every FAIL is `maxBlk=31k` with 18 ×
`-32512`, and every PASS stays ≥ 33k with none. The rate is 3/8, consistent with this morning's 4/8.

**Verdict, applying the pre-registered rule:** the instrumented FAIL rate is 2/8, outside {3,4,5}/8,
so the instrument **perturbs. Stop. The dump contents are not read.** Beyond the rate, the ON arm
broke the harness's own console exchanges (a switch not confirmed, a reply lost) in 6 of 8 tries,
which the OFF arm never did. That is gross perturbation, the kind Gate 0 exists to catch. All 57
`integrity=ok` markers are recorded and not interpreted.

**Unverified reading of the mechanism**, for the redesign only: `heap_caps_check_integrity_all()`
takes each heap's lock while it walks every block. That stalls every allocating task, the loop
task that answers the console included, for the length of the walk. `heap_caps_print_heap_info()`
is small by comparison. The design's pre-named fallbacks: move the dump off dataTask onto a
lower-priority task via a lock-free ring, or accept "cannot observe non-invasively". A third option
the gate result suggests: drop the integrity walk (Option D) and re-run Gate 0 with the print only.

## Option 3 A/B (pre-registered), 2026-09-16 18:49–20:48 — Arm B INVALID and CONFOUNDED; TASK-697 → P2

One commit (`a93535d5`), board `d48afcc8eed0`, `run/test-targeted T_PR_04,T_PRI_01,T170`, 8 tries per
arm, fresh flash per arm, control first. Arm A = `-DHEAP_REGION_DUMP_OFF`; Arm B adds
`-DTLS_RESERVE_EXPERIMENT` (40 KB reserved in `dataTask::begin()`, released around each fetcher's
TLS work, re-acquired right after each session teardown).

| | Arm A (control) | Arm B (reservation) |
|---|---|---|
| `T170` FAIL | **3 / 8** — in the {3,4,5} band, control valid | **0 / 8** |
| `[tlsres] point1` | n/a | **RELEASED in 8/8** |
| re-acquire | n/a | **FAIL 33/33** (no `ok`, no `held`) |
| Spotify failure elapsed (median of 32/33 samples) | **4076 ms** | **748 ms** |
| `-32512` per try | 0–20 | **76** |
| Spotify successes | 0 | 0 (hard invalidator not triggered) |

**Verdict under the pre-registered rules — both failure conditions fired:**

1. **INVALID (engagement).** @VE's rule: engaged = the block HELD at capture point 1; ≥3/8
   non-engaged invalidates the arm. It read RELEASED in 8 of 8, because **every re-acquire failed**:
   once the reservation is released for the first fetch, no 40 KB contiguous span exists to take
   back. Arm B therefore tested "a 40 KB block held from boot until the first fetch", not the
   specified treatment.
2. **CONFOUNDED (timing shape).** Spotify's failures went from ~4.1 s (`-9984`, a real round trip)
   to ~0.75 s, with 76 `-32512` per try against 0–20 in the control. Arm B starved every other
   allocation, exactly the behavioural confound the rule was written to catch.

**Per the human's stopping condition (2026-09-14): not a clear 0/8 → TASK-697 is downgraded to P2
and parked.**

### The lead this leaves, for whoever picks it up

`T170` passed **8 of 8** in Arm B against a valid **3 of 8** control. Even in its degenerate form —
one contiguous 40 KB span guaranteed at boot and handed to the first fetch that asks — the Stock
fetch never hit the wedge. That is consistent with the whole failure being about *one contiguous
span existing when a handshake needs it*, and it is the first treatment that moved the number at
all. It is not a fix: it made everything else fail faster and more often, and the arm is invalid on
its own terms. A real fix would have to own the span for the TLS client's lifetime rather than
gamble on re-acquiring it — a pooled/preallocated mbedTLS buffer, sized from
`app/mem_manifest.yaml`, decided in an ADR, not a probe flag. Filed as TASK-708.
