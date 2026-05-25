# VE Review — M-TOUCH-CAPTURE Slider Input Capture Design

> Reviewer: Verification Engineer
> Design doc: `docs/architecture/designs/M-TOUCH-CAPTURE-slider-input-capture.md`
> Date: 2026-05-25
> Verdict: **Conditional approval — one design correction required before implementation**

---

## Summary

The design is sound. The two-phase dispatch structure is correct and testable. One
design defect must be fixed before Developer starts: the POSBAR Release handler reads
`posbarFromX(release_x)` where `release_x = 0` (from `injectRelease(0,0)`), which
clamps to the leftmost position and emits a wrong seek. The fix is a one-liner: cache
the last position during Move (same pattern as `lastVolumeRendered` for VOLUME).

---

## Challenge 1 — POSBAR Release commits wrong position via injectRelease [BLOCKER]

**Design says (§4):**
```cpp
const long seekMs = posbarFromX(x);   // x from Release event
```

**Problem:** `injectRelease()` calls `handleWinampInput(Release, 0, 0)`. With
`D_POSBAR_DRAG` active, `posbarFromX(0)` clamps to `x = originX + POSBAR_X` → seeks to
0 ms regardless of where the drag ended. Physical touch Release also delivers the last
known position, but hardware reliability on the CYD is inconsistent — the last Release
coordinate may not match the final Move coordinate.

**Fix:** Follow the `lastVolumeRendered` pattern exactly.

```cpp
// Add member:
long _posbarDragCurrentMs = 0;

// During D_POSBAR_DRAG Move (Phase 1):
_posbarDragCurrentMs = posbarFromX(x);
updateSeekThumb(_posbarDragCurrentMs);

// During Release D_POSBAR_DRAG:
spotifyTask::enqueue(spotifyTask::ACT_SEEK, (int32_t)_posbarDragCurrentMs);
songStartMillis = millis() - _posbarDragCurrentMs;
```

`injectRelease(0,0)` now commits the last cached position correctly.

**Precedent:** `D_VOLUME_DRAG` Release commits `lastVolumeRendered`, not a coordinate.
`D_PLEDIT_SCROLL` Release commits `_dragCurrentY`. This design must be consistent.

---

## Challenge 2 — POSBAR drag position not observable via serial debug [MUST-FIX]

There is no `dbgGet` variable for POSBAR drag position. Without it, T149 (commit
correct seek on Release) cannot assert the committed value from the harness — the only
signal is a `{"cmd":"drag",...}` JSON that does not include the seek target.

**Fix:** Add `dbgGet("posbarDragMs")` that returns `_posbarDragCurrentMs`:

```cpp
if (strcmp(var, "posbarDragMs") == 0) {
    snprintf(buf, len, "\"var\":\"posbarDragMs\",\"ms\":%ld", _posbarDragCurrentMs);
    return true;
}
```

Alternatively, emit a log line `[D][touch] posbar drag-end seek=%ld ms` on Release and
let the test harness parse serial output. Either approach unblocks T149.

---

## Challenge 3 — `dragState` string table update noted, no issue

`dbgGet("dragState")` must include the `D_POSBAR_DRAG` arm — design §6 calls this out.
Verify in implementation.

---

## Challenge 4 — Capture exclusivity: design is silent on concurrent-state edge case

If a Move arrives while `dragState != D_IDLE` and the raw (x,y) falls inside a
*different* slider's hitbox, Phase 1 must still route to the captured handler. The
design's Phase 1 guard (`if (dragState != D_IDLE) { switch ... return; }`) handles this
correctly — the Phase 2 hit-test tree never runs. T153 verifies this explicitly.

No design change needed; included in test acceptance criteria.

---

## Testability verdict per slider

| Slider | Capture testable? | Commit-value testable? | Observability gap? |
|---|---|---|---|
| POSBAR | Yes (cmdDrag crosses hitbox) | Yes after fix §C1 | `posbarDragMs` dbgGet needed |
| VOLUME | Yes (cmdDrag crosses hitbox) | Yes (lastVolumeRendered visible) | None |
| PLEDIT scrollbar | Yes (cmdDrag drifts into content area) | Yes (scrollOffset via `get scrollOffset`) | None |
| PLEDIT content | Yes (cmdDrag drifts outside content) | Yes (`get dragState` + scrollOffset) | None |

---

## Acceptance criteria (TASK-102 test IDs: T149–T154)

See test_plan.md §suite touch-capture-001.

---

## Sign-off condition

Fix Challenge 1 (cache pattern) and Challenge 2 (observability) in the design doc and
implementation before first commit. All other points are non-blocking or covered by the
test suite.
