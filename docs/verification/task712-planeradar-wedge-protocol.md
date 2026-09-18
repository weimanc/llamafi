# TASK-712 — resolved by re-analysis: NOT a wedge (was: investigation protocol)

> Owner: @VE · Filed 2026-09-18 from a TASK-706 DUT session as a suspected board-wedging P1.
> **Downgraded 2026-09-18, same day, before any DUT time was spent on the protocol below.** An
> independent Opus/Architect review (requested before sign-off) found the premise "`fetchPlaneRadar()`
> never returns" was never actually established by the evidence cited for it, and named the exact
> already-captured field (`inFlightMs`) that decides the question. Re-deriving that field's raw
> values from the original diagnostic's own transcript refutes the wedge. Full trail below, kept
> rather than deleted — this is as much a record of a self-caught false alarm as of what actually
> happened, and the "how" is worth keeping for the next false-wedge-looking symptom.

## What the review found, that changed the read

Original claim: `get dataq`'s `inFlight` field stayed at `8` (`DATA_FETCH_PLANERADAR`) for 300s+,
therefore `fetchPlaneRadar()` never returned. The review (full text on file, this session) pointed
out that `inFlight` alone can't distinguish "one call stuck the whole time" from "a fast sequence of
separate calls, each one also PlaneRadar" — and that the field that *does* distinguish them,
`inFlightMs` (`s_dbgInFlightMs`, stamped with `millis()` **once, at each dispatch's start**,
`dataTaskStorage.cpp:2088`), was in the original diagnostic's own output the whole time and never
checked for exactly this.

Re-derived from the original transcript (10 samples, 20s apart, `inFlightMs` at each):

```
t=  20s  inFlightMs=134885  delta_wall=20s  delta_val= 8746ms  ratio=0.44
t=  40s  inFlightMs=155815  delta_wall=20s  delta_val=20930ms  ratio=1.05
t=  60s  inFlightMs=185260  delta_wall=20s  delta_val=29445ms  ratio=1.47
t=  80s  inFlightMs=205755  delta_wall=20s  delta_val=20495ms  ratio=1.02
t= 100s  inFlightMs=225973  delta_wall=20s  delta_val=20218ms  ratio=1.01
t= 120s  inFlightMs=246511  delta_wall=20s  delta_val=20538ms  ratio=1.03
t= 140s  inFlightMs=267535  delta_wall=20s  delta_val=21024ms  ratio=1.05
t= 160s  inFlightMs=283953  delta_wall=20s  delta_val=16418ms  ratio=0.82
t= 180s  inFlightMs=304555  delta_wall=20s  delta_val=20602ms  ratio=1.03
```

`inFlightMs` **advances at essentially wall-clock rate**, ratio ≈1.0 throughout. A value that is
written once and never touched again while a call is genuinely stuck cannot do this — it would sit
at its original value (~126139) for the whole window, with only the live `ms` clock advancing
around it. The only way `inFlightMs` itself climbs in step with real time is if `s_dbgInFlightMs`
is being **re-written**, i.e. a **new dispatch is starting**, repeatedly, roughly every 8-30
seconds.

**And `taskBody()`'s dispatch loop is strictly serial**: `xQueueReceive` → set
`inFlight`/`inFlightMs` → run the dispatched function to completion → clear `inFlight` → loop back
to `xQueueReceive` (`dataTaskStorage.cpp:2082-2118`, confirmed by this session's own re-read and
independently by the review). There is no concurrency here — a *new* dispatch's `s_dbgInFlightMs`
write is only reachable after the *previous* dispatched function has already returned. So the
advancing timestamp doesn't just make "one stuck call" unlikely, it makes it **mechanically
impossible** given what was actually observed: every one of those ten samples caught a different,
freshly-started PlaneRadar dispatch, each of which had already let its predecessor finish.

## What this actually is

Not a wedge. `fetchPlaneRadar()` returns normally, repeatedly, roughly every 8-30 seconds, for the
whole observation window — i.e., PlaneRadar's ordinary fetch cadence continuing to run, sampled at
a point where every real network attempt happens to be genuinely slow (no code anywhere in
`dataTaskStorage.cpp` sets a TLS/connect/handshake timeout — grep confirms zero
`setTimeout`/`setConnectTimeout`/`setHandshakeTimeout` calls; the vendored `WiFiClientSecure`'s
default is 120s per handshake, `app/lib/WiFiClientSecure/src/WiFiClientSecure.cpp:40` — the review's
finding, not re-verified line-for-line in this pass but consistent with everything observed).

**What's still genuinely unexplained, and worth its own look, at much lower priority than a P1
wedge**: `prLastHttp` never changed from `0` across the entire 180s+ window despite this reading
implying several real fetches completed and published results in that time. Either the app-side
consumer isn't updating that field the way assumed, or the fetches are completing with some code
path that doesn't touch `prLastHttp`, or (least likely, but not excluded) each one really is
failing/timing out in a way that never reaches the publish statement — which would reopen a
narrower version of the original question. Not chased further here; if this matters, it's a fresh,
correctly-scoped investigation, not a resurrection of "the wedge."

## TASK-706's own status is unaffected by this correction

TASK-706's `T_PR_08` PASS was independently already marked inconclusive (see `tasks.md`), for an
unrelated and still-valid reason: that test's own away-window (2-2.5s) is far too short for even a
single real dispatch to complete, forced or otherwise, so it couldn't have observed a drain either
way. That conclusion doesn't depend on anything about the wedge and stands as filed.

## Lesson for next time (the part worth keeping past this one task)

`inFlight`-style "what's currently running" fields answer "is something running", not "is it the
*same* something" — that second question needs a field that's stamped at a specific instant and
never touched again, checked for whether it's still that same stamp. This project already has a
sharper instrument for exactly this class of question — `get dataRing` (TASK-697, sequence of
dispatch/finish/yield edges with timestamps,
`app/src/debug/serialConsole/cmdGet.cpp:208-224`) — which would have shown the
repeated dispatch-then-finish pattern directly instead of requiring this after-the-fact arithmetic
on a snapshot field. Reach for `get dataRing` before `get dataq` alone the next time a "stuck at
value X" reading needs to be told apart from "value X keeps recurring."
