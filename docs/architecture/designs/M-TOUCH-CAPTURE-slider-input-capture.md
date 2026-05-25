# Design — Slider Input Capture (M-TOUCH-CAPTURE)

> Owner: Architect
> Status: approved (2026-05-25)
> Tracked-as: TASK-101 (implementation), TASK-102 (VE test suite)
> Deps: touch-002 (skin-region touch, implemented)

---

## Problem

All four interactive slider elements in `WinampDisplay` re-run their hitbox check on
every `Move` event. If the user's finger drifts outside the narrow hitbox mid-gesture,
the sample is silently dropped — or worse, routed to a different handler. The affected
sliders:

| Slider | DragState today | Hitbox (h) | Axis |
|---|---|---|---|
| POSBAR (seek) | none | 10 px tall | X |
| VOLUME | `D_VOLUME_DRAG` | 13 px tall | X |
| PLEDIT scrollbar strip | `D_PLEDIT_SCROLL_DIRECT` | 19 px wide | Y |
| PLEDIT content swipe | `D_PLEDIT_SCROLL` | 244 px wide | Y |

Standard fix: **pointer capture** — the first `Press` in a hitbox establishes ownership;
subsequent `Move` and `Release` events route directly to the owning handler, bypassing
all hit-testing.

---

## Design

### 1. DragState enum — add one value

```cpp
enum DragState {
    D_IDLE = 0,
    D_VOLUME_DRAG,
    D_POSBAR_DRAG,           // ← new
    D_PLEDIT_SCROLL,
    D_PLEDIT_SCROLL_DIRECT,
};
```

### 2. Two-phase dispatch in `handleWinampInput` (Press/Move path)

**Phase 1 — captured gesture (dragState ≠ D_IDLE): no hit-test.**

```cpp
if (dragState != D_IDLE) {
    switch (dragState) {
        case D_VOLUME_DRAG:
            { long pct = volumeFromX(x); drawVolume((int)pct); debounceVolumeEnqueue(pct); }
            break;
        case D_POSBAR_DRAG:
            { updateSeekThumb(posbarFromX(x)); }   // visual only — commit on Release
            break;
        case D_PLEDIT_SCROLL_DIRECT:
            { updateScrollDirect(y); }
            break;
        case D_PLEDIT_SCROLL:
            { _dragCurrentY = y; }
            break;
        default: break;
    }
    _tickMarquee();
    return true;
}
```

**Phase 2 — D_IDLE only: run hit-tests to start a new gesture** (existing tree, unchanged
logic, just moved after the Phase 1 guard).

### 3. Clamped-coordinate helpers (private)

Replace the hit-test functions for captured moves. Each helper clamps the relevant axis
to the slider range; the irrelevant axis is ignored.

```cpp
// Horizontal sliders — clamp x, ignore y.
long volumeFromX(int sx) const {
    const int x0 = originX + VOLUME_X;
    const int cx = max(x0, min(x0 + VOLUME_W - 1, sx));
    return ((long)(cx - x0) * 100) / (VOLUME_W - 1);   // 0..100
}

long posbarFromX(int sx) const {
    if (songDuration <= 0) return 0;
    const int x0 = originX + POSBAR_X;
    const int cx = max(x0, min(x0 + (int)POSBAR_BG.w - 1, sx));
    return ((long)(cx - x0) * songDuration) / POSBAR_BG.w;   // 0..songDuration ms
}
```

`updateScrollDirect(y)` — existing logic extracted to a private helper (already called
from two places; no logic change).

### 4. POSBAR: visual-update on Move, commit on Release

Add member `long _posbarDragCurrentMs = 0;` — caches the last drag position so Release
commits the correct seek position regardless of what x-coordinate the Release event
carries (matches `lastVolumeRendered` pattern for VOLUME).

During `D_POSBAR_DRAG` Move:
```cpp
_posbarDragCurrentMs = posbarFromX(x);
updateSeekThumb(_posbarDragCurrentMs);
songStartMillis = millis() - _posbarDragCurrentMs;  // optimistic digits
// no ACT_SEEK enqueued
```

On `Release` with `dragState == D_POSBAR_DRAG`:

```cpp
if (dragState == D_POSBAR_DRAG) {
    spotifyTask::enqueue(spotifyTask::ACT_SEEK, (int32_t)_posbarDragCurrentMs);
    songStartMillis = millis() - _posbarDragCurrentMs;
    touchScreenCoolDownTime = millis() + 200;
    dragState = D_IDLE;
}
```

**Rationale:** ACT_SEEK is a one-shot HTTP call; issuing it on every 10 ms Move sample
would saturate the Spotify queue. Single commit on Release matches desktop Winamp and
produces one network call per scrub gesture. Caching `_posbarDragCurrentMs` instead of
using `posbarFromX(release_x)` is required because `injectRelease(0,0)` passes x=0,
which would clamp to leftmost and seek to 0 ms (VE-CH1).

### 5. POSBAR Press entry

On initial Press in the POSBAR hitbox (`hitTestPosbar(x,y) >= 0`):

```cpp
dragState = D_POSBAR_DRAG;
updateSeekThumb(posbarFromX(x));   // paint immediately on press
songStartMillis = millis() - posbarFromX(x);   // optimistic UI
// no enqueue yet
consumed = true;
```

Note: `songStartMillis = 0` (pause/stop sentinel) must not be set here — the track
continues playing while the user scrubs.

### 6. `dbgGet` additions

`dragState` string table — add `D_POSBAR_DRAG` arm:
```cpp
: dragState == D_POSBAR_DRAG ? "D_POSBAR_DRAG"
```

`posbarDragMs` — new variable, returns `_posbarDragCurrentMs` (VE-CH2):
```cpp
if (strcmp(var, "posbarDragMs") == 0) {
    snprintf(buf, len, "\"var\":\"posbarDragMs\",\"ms\":%ld,\"last\":true",
             _posbarDragCurrentMs);
    return true;
}
```

### 7. `injectTouch` / `injectRelease` (SERIAL_DEBUG)

`injectTouch` already re-runs hit-tests to populate `lastTouchResult` after calling
`handleWinampInput`. The POSBAR block in the existing `else if (seekMs >= 0)` arm
already covers this — no new code needed there.

`injectRelease` calls `handleWinampInput(Release, 0, 0)`. With capture, `D_POSBAR_DRAG`
Release commits via `posbarFromX(0)` — which clamps to `x=POSBAR_X` (leftmost position,
seek to 0 ms). Injection tests that need a specific release position must issue a Move to
set the position, then Release. Document this in the VE acceptance criteria.

---

## Absolute geometry reference

| Slider | originX+ | y range (screen) | axis |
|---|---|---|---|
| POSBAR | x: 16..263 (248 px) | y: 72..81 (10 px) | X |
| VOLUME | x: 107..174 (68 px) | y: 57..69 (13 px) | X |
| PLEDIT scrollbar | x: 278..296 (19 px) | y: 136..200 (65 px) | Y |
| PLEDIT content | x: 34..277 (244 px) | y: 136..200 (65 px) | Y |

All x values relative to `originX = 0` on the 320 px CYD.

---

## What does NOT change

- `hitTestVolume(x,y)` remains for Press entry detection (y check still needed to
  distinguish volume from posbar on initial touch).
- `hitTestPosbar(x,y)` remains for Press entry.
- All existing DragState values and Release handling for VOLUME / PLEDIT_SCROLL /
  PLEDIT_SCROLL_DIRECT are preserved.
- The `VOLUME_DRAG_DEBOUNCE_MS` debounce gate is preserved.
- No changes to the `App` interface, `appShell.h`, or `main.cpp`.

---

## Files changed

- `app/src/winamp/winampDisplay.h` — sole change site.

---

## Exit criteria (for VE)

See TASK-102.
