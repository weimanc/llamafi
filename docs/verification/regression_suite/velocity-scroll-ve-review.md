# VE Review — M-LIST-v4 Velocity-Scroll PLEDIT Design

> Reviewer: Verification Engineer
> Design doc: `docs/architecture/designs/M-LIST-v4-velocity-scroll.md`
> ADR: `docs/architecture/decisions/ADR-030.md`
> Date: 2026-05-25
> Verdict: **Conditional approval — 2 blockers + 2 must-fix before implementation**

---

## Summary

The velocity-joystick model is sound and testable in principle. Two blockers must be resolved
before Developer starts: the test harness cannot drive time-dependent scroll advancement
without a tick injection mechanism, and key intermediate state is invisible to the harness.
Two must-fix items complete the picture. One advisory is included for DUT calibration
convenience.

---

## Challenge 1 — `tickScroll()` is not harness-drivable [BLOCKER]

**Design says**: `tickScroll()` is called from `SpotifyApp::tick()` each frame. It reads
`millis()` to compute `dt`. Scroll advancement is proportional to real elapsed time.

**Problem**: The existing serial debug test harness (`run_serialdbg_tests.py`) drives
`injectTouch` / `injectRelease` and reads `dbgGet` variables. It has no way to advance the
app tick or inject a simulated `dt`. Without tick injection:

- A test cannot assert "after holding the finger at dy=30 for 500 ms, scrollOffset advanced
  by ~N rows" without sleeping for real wall-clock time — making the harness slow, flaky on
  loaded hardware, and non-deterministic.
- Any acceptance test for the velocity model degrades to "did scrollOffset change at all"
  rather than "did it change by the correct amount in the correct time".

**Fix required**: Add a `cmdTick` serial command that calls `tickScroll()` N times with a
synthetic dt:

```
tick [n] [dtMs]
```

- `n` — number of tick steps to inject (default 1)
- `dtMs` — simulated milliseconds per step (default 20, i.e. 50 Hz equivalent)

`tickScroll()` should accept an optional `float dt` parameter (defaulting to real `millis()`
delta), or expose a `_mockDt` path gated on `SERIAL_DEBUG`. Either approach unblocks
deterministic harness tests.

Alternative: expose `tickScroll(float dt)` with explicit dt; the app tick calls
`tickScroll((millis() - _lastScrollTickMs) / 1000.0f)` and resets `_lastScrollTickMs`.
`cmdTick` calls `tickScroll(dtMs / 1000.0f)` directly. This is the cleaner design.

---

## Challenge 2 — `_scrollAccum` and velocity not observable [BLOCKER]

**Problem**: Tests that assert "scrollOffset advanced by exactly N after M ticks" need to
observe the fractional accumulator between scroll steps. Without `dbgGet("scrollAccum")`,
a test can only see `scrollOffset` change in integer steps — making it impossible to verify
that accumulation is happening at the correct rate before a row boundary is crossed.

Computed velocity is also needed: a test checking speed-scaling correctness ("at dy=30,
velocity ≈ 1.9 rows/s") cannot be written without seeing the intermediate computation.

**Fix required**: Add two `dbgGet` variables:

```cpp
if (strcmp(var, "scrollAccum") == 0) {
    snprintf(buf, len, "\"var\":\"scrollAccum\",\"val\":%.4f,\"last\":true", _scrollAccum);
    return true;
}
if (strcmp(var, "scrollVelocity") == 0) {
    // _scrollVelocity must be stored as a member after each tickScroll() call
    snprintf(buf, len, "\"var\":\"scrollVelocity\",\"val\":%.4f,\"last\":true", _scrollVelocity);
    return true;
}
```

`_scrollVelocity` must be stored as a member (the design lists it but marks it
"informational, not strictly needed" — for VE observability it is needed).

---

## Challenge 3 — Queue snapshot update mid-gesture is unhandled [MUST-FIX]

**Design is silent on**: what happens when a new queue snapshot arrives (seqno advances,
`drawPlaylist()` resets `scrollOffset = 0`) while `dragState == D_PLEDIT_SCROLL` is active.

Current `drawPlaylist()` resets `scrollOffset = 0` on seqno change (M-LIST-v3 / TASK-051f).
With the velocity model, `tickScroll()` will then continue advancing `scrollOffset` from 0
based on the stale `_dragStartY` anchor. The visual result is a snap-to-top followed by
immediate re-scroll — jarring and confusing.

**Fix required**: When `drawPlaylist()` detects a seqno change while `dragState ==
D_PLEDIT_SCROLL`, cancel the gesture:

```cpp
if (seqnoChanged) {
    scrollOffset = 0;
    if (dragState == D_PLEDIT_SCROLL) {
        dragState    = D_IDLE;
        _scrollAccum = 0.0f;
    }
    // ... rest of seqno handling
}
```

This is one line to add to `drawPlaylist()`'s seqno branch. The user's finger is likely
still on the screen; the next touch event re-enters D_PLEDIT_SCROLL with a fresh anchor.
Document this cancellation as an explicit invariant in the design doc.

---

## Challenge 4 — `_dragStartMs` removal: regression confirmation needed [MUST-FIX]

**Design says**: "`_dragStartMs` becomes dead code; remove in implementation."

**Problem**: TASK-078 point 1 (two-axis tap check) was introduced because abs(dy) < 4 alone
was too tight and caused missed taps on a firm press with slight drift. That behavior is now
replaced by a dead zone of 8 px. Before removing `_dragStartMs` and the elapsed-time check,
VE needs to confirm:

1. No passing tests in the existing suite assert the elapsed-time arm (`elapsed < 150 &&
   abs(dy) < 16`) specifically. A grep for `_dragStartMs` in test harness scripts and
   test_plan.md should be clean.

2. The 8 px dead zone is sufficient in practice — it must be verified on DUT. A user who
   presses firmly and drifts 9 px before releasing should not accidentally scroll. At 13 px/row,
   8 px is 62% of a row; this seems reasonable, but DUT evidence is required before the
   elapsed-time safety net is removed.

**Required action**: Developer confirms no test references `_dragStartMs` timing behavior.
One DUT trial (5 firm taps with natural press-lift drift) confirms 8 px dead zone is
sufficient before the elapsed-time arm is removed. Document result in implementation notes.

---

## Challenge 5 — Release-at-limit behavior: document explicitly [ADVISORY]

When `scrollOffset` is at 0 or `maxOffset` and the user has been scrolling against the
limit, `|dy|` at Release will be ≥ DEAD_ZONE_PX — so no tap fires. This is correct
behavior (they were scrolling, not tapping) but will feel wrong if the user pressed near
the top of the list, the list didn't move (already at 0), and they expected a tap.

This edge case is not a design defect — the correct fix is: if `scrollOffset` never
advanced from 0 during the gesture (i.e., the limit was hit immediately), the Release
should still be treated as a tap if `|dy| < some_threshold`. But this is complex to
implement correctly and is out of scope for M-LIST-v4.

**Required action**: Document this as a known limitation in the design doc with a note
that it is deferred. No implementation change needed now.

---

## Challenge 6 — SCROLL_SPEED_K: make settable via dbgSet [ADVISORY]

`SCROLL_SPEED_K` as a `static constexpr float` requires a reflash to tune. Given that
this constant needs DUT calibration (the design explicitly acknowledges it as a first
estimate), a `dbgSet("speedK", "0.100")` override would allow in-session tuning without
reflash — significantly speeding up calibration.

Pattern: expose as a `float _scrollSpeedK = SCROLL_SPEED_K_DEFAULT` member; `dbgSet`
updates it; `tickScroll()` reads the member. Default value is the constexpr.

**Required action**: Recommended but not blocking. PM may choose to defer to post-M-LIST-v4
cleanup if calibration can be done with reflash during development.

---

## Testability verdict per design element

| Element | Harness-testable? | Gap |
|---|---|---|
| Dead zone tap discrimination | Yes (injectTouch + Release; assert ACT_PLAY_URI) | None after C2 |
| Velocity scaling (speed ∝ dy) | Blocked until C1 + C2 resolved | cmdTick + scrollVelocity dbgGet |
| Continuous scroll (finger held still) | Blocked until C1 resolved | cmdTick needed |
| Integer step advancement | Blocked until C2 resolved | scrollAccum dbgGet needed |
| D_IDLE after Release | Yes (get dragState) | None |
| Seqno cancels mid-gesture | Blocked until C3 implemented | drawPlaylist seqno branch |
| No tap on out-of-dead-zone Release | Yes (injectTouch + Release + assert no ACT_PLAY_URI) | None |

---

## Sign-off condition

Fix C1 (tick injection mechanism) and C2 (scrollAccum + scrollVelocity observability) in
the design before Developer begins. Fix C3 (snapshot mid-gesture) in implementation.
Confirm C4 (_dragStartMs) before removal. C5 is documentation only. C6 is advisory.

Proposed acceptance test IDs: T155–T161 (to be written against the revised design).
