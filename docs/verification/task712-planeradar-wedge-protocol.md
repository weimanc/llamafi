# TASK-712 — investigation protocol: `dataTask` wedge under forced PlaneRadar parse-fail

> Owner: @VE · Filed 2026-09-18, from a TASK-706 DUT session
> Scope: TESTABILITY/diagnosis protocol, pre-registered before any run — same discipline TASK-697's
> Gate 0 and Option 3 A/B used, after that programme's own hard lesson about open-ended DUT chases.
> This document proposes steps; it does not authorize running them. Human sign-off needed before
> DUT time is spent, same as every DUT-costing step in this programme.

## What's already known (host+DUT evidence, no further reads needed to establish this)

- `set prForceParseFail 3` then `set triggerPlaneRadarFetch 1` while PlaneRadar is the active app
  (confirmed via `get appId`, no switch away) consumes all 3 forced-failure credits (observed:
  `prForceParseFail` 3→0 within ~20s of firing) but `fetchPlaneRadar()` **never returns**:
  `get dataq`'s `inFlight` field (`s_dbgInFlight`, `dataTaskStorage.cpp:2088/2115` — set to the
  request type at dispatch, reset to `-1` only when the dispatched function returns) stayed at `8`
  (`DATA_FETCH_PLANERADAR`) continuously for 300s+ across a single unbroken console session (no
  reconnect, so no DTR reset could have masked recovery).
- `dataq`'s `spAct`/`spActMs` (spotifyTask's own activity marker, `taskActivity()`/`spotifyTask.h`'s
  loop-position comment: `1 = yield-spin`) froze at `1` and a **constant** `spActMs` for the same
  300s+ window. `spotifyTask::tlsResume()` is the literal last statement of `fetchPlaneRadar()`
  (`dataTaskStorage.cpp`, end of the function) — a frozen yield-spin corroborates, independently of
  the `inFlight` field, that the function is stuck somewhere between its `tlsYield()` call (which
  DID complete — `tlsStopped=True`, `yieldCount=1` observed) and its final `tlsResume()` call.
- The console/`get` command path stayed fully responsive throughout (every diagnostic poll returned
  `ok:true` promptly) — this rules out a FreeRTOS critical-section/spinlock deadlock or a core-wide
  freeze, both of which would also stall the console-handling task. Whatever is stuck is scoped to
  `dataTask` specifically.
- `dataTask` is confirmed (prior session finding, TASK-697) **not** TWDT-subscribed — an indefinite
  block or a non-yielding loop inside it would never trip the watchdog and would hang silently
  forever, exactly matching the observed symptom, with no crash/reboot to signal it.
- A full static trace of `fetchPlaneRadar()`'s all-forced path (all three `prFetchOnce()` calls
  taking the `if (forced) {...; return 200;}` early-return, which never touches `WiFiClientSecure`/
  `HTTPClient` at all) found no `vTaskDelay`, mutex, or semaphore wait longer than the two bounded
  `300ms` retry delays. **Nothing in the read source explains a 300s+ hang on this path.** Either
  something outside this function is involved, or the static reading missed something a live trace
  would catch immediately.

## Hypotheses, ranked by how cheaply each can be tested

1. **A logging/print call is blocking on a full UART TX buffer.** `LOG_D`/`LOG_W` (`logSink.h:141`)
   route through a synchronous `Serial.write()` (`logSink.h:133`) with no buffering layer of their
   own. `fetchPlaneRadar()`'s all-forced path still emits several `LOG_D` lines (the per-attempt
   `GET %d elapsed=...`/`retry ok=%d...`/`retry2 ok=%d...`/`ok=%d errorCode=%d...` lines) plus two
   `LOG_HEAP` calls. **Weakened by**: the diagnostic session polled the console every 20s throughout
   the hang, which would read bytes off the wire regardless of whether the harness's parser used
   them — genuinely relieving any full-buffer condition — yet the hang never cleared. Not ruled out
   entirely (a burst larger than the on-chip UART driver's own ring buffer, arriving faster than the
   polls could drain it, is still conceivable), but this hypothesis alone doesn't fit the persistence
   through repeated later reads.
2. **A genuine indefinite wait/block inside the traced function that a static read missed** — e.g. a
   library call inside `LOG_HEAP`'s macro body (defined locally in `dataTaskStorage.cpp:30`, not
   re-read in full during this session's trace) that isn't as cheap as it looks, or an interaction
   with `TLS_RESERVE_EXPERIMENT`/`HEAP_REGION_DUMP_ON`-gated code that this build didn't have
   compiled in but whose surrounding logic still has an untraced side effect. Needs the actual macro
   body re-read, and ideally a live instruction-pointer-level signal (a log line per statement, not
   per function) rather than another static pass.
3. **Something outside `fetchPlaneRadar()` entirely** — e.g. dataTask's own dispatch loop
   (`taskBody()`) has logic around the `switch` statement (before/after the `s_dbgInFlight` writes)
   that can itself stall for this specific request type, not inside the function under suspicion at
   all. Not read in this session; the trace stopped at `fetchPlaneRadar()`'s own body.
4. **Not reproducible via the console path used to discover it** — i.e., an artifact of how the
   diagnostic script issued commands (two separate `dut.cmd()` round-trips to arm then fire, rather
   than the test's own `dut.injected()`/single-body pattern) rather than a property of the firmware
   alone. Lowest-probability given `T_PR_08`'s own PASS run showed the SAME unconsumed-credits
   signature using the harness's real code path, not just the ad-hoc script — but that run's window
   was too short (2-2.5s away) to have caught the hang in progress either way, so this isn't
   actually ruled out yet, only unconfirmed.

## Proposed protocol, in cost order

**Gate 0 (host-only, zero DUT cost, do this first).** Before spending any DUT time: read
`LOG_HEAP`'s full macro body (`dataTaskStorage.cpp:30`, not fully re-read this session) and
`taskBody()`'s dispatch loop end-to-end (only the `switch` cases were read this session, not the
loop's own before/after logic) — either could resolve hypothesis 2 or 3 for free. If either read
finds a plausible blocking call, that becomes the primary suspect for Step 1's instrumentation
rather than a blind sweep.

**Step 1 (minimal DUT cost — one reproduction, full raw capture).** Reproduce with
`LOG_FILE=<path> ./run/test-targeted <ids>` (the existing raw-serial-capture mechanism,
`run/test-targeted:12`) capturing every line during a repro of the exact arm+fire sequence, staying
on PlaneRadar (no switch, matching the diagnostic that reproduced it, not `T_PR_08`'s own
switch-away shape — reproduce the KNOWN-bad case first, not a guess at a different one). The last
`LOG_D`/`LOG_HEAP` line printed before the stream goes silent for `fetchPlaneRadar` names, by
elimination, either the exact statement that never returns, or confirms the function got further
than static reading suggested (which would itself be informative — reopen the static trace at that
point rather than guess further). **Pre-registered decision rule**: whichever of the function's
existing log call sites is the last one seen is the next thing to add fine-grained instrumentation
around, in a follow-up step — not a proxy for "found it," since a print completing doesn't prove the
statement immediately after it also completed.

**Step 2 (if Step 1 is inconclusive — needs new instrumentation, own sign-off).** Add temporary,
`SERIAL_DEBUG`-gated log lines between every statement in the suspect region identified by Step 1
(a "print a breadcrumb after every line" pass, removed before any production-adjacent build) and
reproduce once more. This is genuinely new code, even if temporary — bring it back for a design
sign-off before landing it, matching this programme's rule that no DUT-costing instrument ships
without review (TASK-697's Gate 0 precedent: an instrument itself can perturb the exact thing it's
measuring, so even a "just add prints" step needs to state what it might disturb before running it).

## What this protocol does NOT propose

- No new debug hook shaped like `TLS_RESERVE_EXPERIMENT`/`HEAP_REGION_DUMP_ON` — those were built
  for a different, still-parked investigation (TASK-697) and reusing them here would conflate two
  separate open questions on one board.
- No fix attempt before the hang is actually located. TASK-706's resume()-drain code is a plausible
  but unconfirmed suspect (it's new, and it does call `pollPlaneRadar()` from a different task
  context than `fetchPlaneRadar()` normally runs in) — Step 1's capture should also note whether
  `PlaneRadarApp::resume()`'s own drain-and-epoch-bump log context appears anywhere near the hang,
  but this document does not assume TASK-706 caused it. The wedge may be entirely pre-existing and
  merely newly-exercised by `T_PR_08`'s introduction of this exact `prForceParseFail=3` +
  `triggerPlaneRadarFetch` combination in a test for the first time.

## Cost and stop condition

Each reproduction costs one TASK-557 observation window (a wedge requires a reflash to clear — no
lesser recovery exists, confirmed: the console stayed responsive but `dataTask` itself never
recovered on its own across 180s+ of observation) plus the DUT time for the repro itself (~1-2
minutes to arm/fire/observe/confirm-stuck). **Cap: 2 reproduction attempts (Gate 0's host read plus
Step 1, then Step 1 repeated once if the first capture is ambiguous) before stopping and reporting
back for a scope decision** — matching TASK-697's own precedent of a human-set stopping condition
declared before a session starts, not discovered mid-chase. This is a P1 finding (it can wedge a
running board via a legitimate VE test hook, not an edge-case misuse), but "P1" is not itself
license for an open-ended DUT session; the severity argues for prioritizing when it's investigated,
not for how much DUT time gets spent per sitting.

## Exit criteria

Either: the hang's exact location is identified (Step 1 or 2 succeeds) and a fix can be scoped as
its own task, separate from this diagnostic; or both attempts are inconclusive and TASK-712 is
parked (matching TASK-697's own disposition) with everything gathered here plus the two attempts'
findings recorded, rather than continuing past the 2-attempt cap.
