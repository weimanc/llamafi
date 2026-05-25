# Design — Velocity-Scroll PLEDIT (M-LIST-v4)

> Owner: Architect
> Status: draft — VE feedback incorporated (2026-05-25)
> Feeds: ADR-030
> Tracked-as: TASK-TBD (PM to assign)
> Deps: M-LIST-v3 (implemented), M-TOUCH-CAPTURE / TASK-101 (implemented)
> VE review: `docs/verification/regression_suite/velocity-scroll-ve-review.md`

---

## Context / pain points

The current PLEDIT content-area gesture (M-LIST-v3 / TASK-051d) is **commit-on-release**:

1. Press → anchor recorded, list frozen
2. Move → `_dragCurrentY` updated silently, no visual change
3. Release → `dy` computed → teleport by `max(1, abs(dy)/ROW_H)` rows OR play row (tap)

Observed failure modes:
- **No live feedback** — the list is inert during the entire gesture
- **Coarse jumps** — 65 px travel / 13 px row = max 5 rows per swipe; 20-item queue needs 3+ swipes
- **Fragile tap discrimination** — two-axis check (TASK-078 point 1) fires on short fast swipes

---

## Goals

1. Live visual feedback — list moves in real time during drag
2. Velocity model — finger offset from anchor determines scroll *speed*, not *distance*; holding still at nonzero offset scrolls continuously
3. Simplified tap discrimination — dead-zone only, no elapsed-time heuristic
4. Integer `scrollOffset` preserved — no sub-row pixel rendering required
5. Test harness can drive and observe all scroll behavior deterministically
6. Architecture ready for Phase 2 fling/momentum without structural rework

---

## Design space

### Option A — drag-follows-position ("iOS list")

`scrollOffset` tracks `_dragStartScrollOffset + dy / ROW_H` in real time. Sub-row granularity
requires float `scrollOffset` or pixel-level vertical clipping in `drawPlaylist()`. On a 65 px
viewport, 13 px of drag = exactly one row — coarse without sub-row rendering.

**Tradeoffs**: Familiar mobile pattern. Sub-row rendering adds significant complexity to
`drawPlaylist()`. Coarseness on this viewport is the same problem relocated.

### Option B — velocity joystick (user request) ← chosen

`dy = _dragCurrentY - _dragStartY` maps to scroll speed (rows/s). Holding still at a nonzero
offset scrolls continuously. Release stops. Dead zone (|dy| < DEAD_ZONE_PX) provides tap region.

**Tradeoffs**: Unusual for a list (more common in map/3D panning). Matches explicit user intent.
Works with integer `scrollOffset`. No sub-row rendering. Phase-2-ready accumulator.

### Option C — hybrid: position-follow + momentum on release

Standard iOS scroll: position-locked during drag, momentum after release. Most complexity.
Deferred to Phase 3 pending evaluation of Phase 2 fling.

---

## Lean / decision

**Option B now; fling as Phase 2; Option C deferred.**

---

## Velocity model

```
dy        = _dragCurrentY - _dragStartY       // signed px; positive = finger below anchor
effective = max(0, abs(dy) - DEAD_ZONE_PX)   // strip dead zone
speed     = effective * _scrollSpeedK         // rows/second (using mutable member, see §Constants)
direction = (dy <= 0) ? -1 : +1              // dy < 0 → scroll up (offset decreases)
velocity  = direction * speed                 // rows/second, signed
```

`dy < 0` (finger above anchor) → scroll up → `scrollOffset` decreases.
`dy > 0` (finger below anchor) → scroll down → `scrollOffset` increases.

---

## Constants

| Constant | Default | Rationale |
|---|---|---|
| `SCROLL_DEAD_ZONE_PX` | `8` | Half a row; prevents jitter on firm press |
| `SCROLL_SPEED_K_DEFAULT` | `0.088f` | 5 rows/s at 57 px effective travel |

`SCROLL_DEAD_ZONE_PX` is `static constexpr int` (no runtime calibration needed).

`_scrollSpeedK` is a **non-const `float` member** initialised to `SCROLL_SPEED_K_DEFAULT`.
It is settable via `dbgSet("speedK", "...")` to allow in-session DUT calibration without
reflash. This resolves VE-C6.

---

## Tick integration — `tickScroll(float dt)`

VE-C1: `tickScroll` accepts an **explicit `dt` parameter** so the test harness can inject
synthetic time steps. The app tick passes real elapsed time; `cmdTick` passes a fixed dt.

```cpp
// dt: elapsed seconds for this tick. 0 or >0.2 → no-op (stall guard).
void tickScroll(float dt) {
    if (dragState != D_PLEDIT_SCROLL) {
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;
        return;
    }
    if (dt <= 0.0f || dt > 0.2f) return;

    const int dy = _dragCurrentY - _dragStartY;
    const float effective = max(0.0f, (float)abs(dy) - (float)SCROLL_DEAD_ZONE_PX);
    const float speed = effective * _scrollSpeedK;
    _scrollVelocity = (dy <= 0 ? -1.0f : 1.0f) * speed;   // stored for dbgGet

    _scrollAccum += _scrollVelocity * dt;
    const int steps = (int)_scrollAccum;
    if (steps != 0) {
        _scrollAccum -= (float)steps;
        const int maxOffset = max(0, (int)lastCount - PLEDIT_ROW_COUNT);
        scrollOffset = max(0, min(maxOffset, scrollOffset + steps));
        _pleditScrollDirty = true;
    }
}
```

**Call site (app tick):**
```cpp
// In SpotifyApp::tick() or equivalent:
static unsigned long lastScrollMs = 0;
unsigned long now = millis();
float dt = (lastScrollMs == 0) ? 0.0f : (now - lastScrollMs) / 1000.0f;
lastScrollMs = now;
display->tickScroll(dt);
```

`tickScroll` is safe to call unconditionally every frame — no-ops when not in D_PLEDIT_SCROLL.

---

## Release logic

On `D_PLEDIT_SCROLL` Release:

```
dy = _dragCurrentY - _dragStartY
if abs(dy) < SCROLL_DEAD_ZONE_PX:
    → tap: play scrollOffset + _dragStartRow
    touchScreenCoolDownTime = millis() + 300
else:
    → scroll end: no row played
    touchScreenCoolDownTime = millis() + 150
_scrollAccum    = 0.0f
_scrollVelocity = 0.0f
dragState = D_IDLE
```

The TASK-078 point 1 two-axis tap check (`elapsed + dy`) is superseded. Dead zone is the
sole discriminator. `_dragStartMs` becomes unused — see §`_dragStartMs` removal below.

---

## Snapshot mid-gesture cancellation (VE-C3)

When `drawPlaylist()` detects a seqno change while `dragState == D_PLEDIT_SCROLL`, cancel
the gesture to prevent the tick from re-scrolling from the reset `scrollOffset = 0`:

```cpp
// In drawPlaylist(), seqno-change branch:
if (seqnoChanged) {
    scrollOffset = 0;
    if (dragState == D_PLEDIT_SCROLL) {
        dragState       = D_IDLE;
        _scrollAccum    = 0.0f;
        _scrollVelocity = 0.0f;
    }
    // ... rest of seqno handling (optimisticSelectedRow reset, etc.)
}
```

**Invariant**: `scrollOffset` is always consistent with the current snapshot seqno. A
mid-gesture seqno change resets both and cancels the gesture cleanly. The user's next
Press re-anchors on the new list.

---

## Serial debug observability (VE-C1, VE-C2)

### `dbgGet` additions

```cpp
if (strcmp(var, "scrollAccum") == 0) {
    snprintf(buf, len, "\"var\":\"scrollAccum\",\"val\":%.4f,\"last\":true",
             _scrollAccum);
    return true;
}
if (strcmp(var, "scrollVelocity") == 0) {
    snprintf(buf, len, "\"var\":\"scrollVelocity\",\"val\":%.4f,\"last\":true",
             _scrollVelocity);
    return true;
}
```

### `dbgSet` addition

```cpp
if (strcmp(var, "speedK") == 0) {
    _scrollSpeedK = (val && *val) ? strtof(val, nullptr) : SCROLL_SPEED_K_DEFAULT;
    return true;
}
```

### `cmdTick` serial command

New serial command, only compiled under `SERIAL_DEBUG`:

```
tick [n] [dtMs]
```

- `n` — number of synthetic tick steps (default 1)
- `dtMs` — simulated milliseconds per step (default 20)
- Calls `display->tickScroll(dtMs / 1000.0f)` n times
- Emits JSON after all steps: `{"cmd":"tick","steps":n,"dtMs":dtMs,"scrollOffset":<val>}`

This allows the harness to drive deterministic scroll advancement:
```python
# Advance 25 ticks of 20ms = 500ms equivalent at held dy=30px
send("tick 25 20")
assert get("scrollOffset") > 0
assert float(get("scrollVelocity")) == approx(1.93, rel=0.05)  # (30-8)*0.088
```

---

## `_dragStartMs` removal (VE-C4)

`_dragStartMs` was introduced in TASK-078 point 1 for elapsed-time tap discrimination.
The velocity model supersedes it. **Removal preconditions** (both required before delete):

1. `grep -r "_dragStartMs\|elapsed.*150\|150.*elapsed" app/ docs/verification/` returns no
   test assertions against the elapsed-time arm.
2. DUT evidence: 5 firm-press taps on PLEDIT rows with natural press-lift drift. All 5 must
   register as taps (ACT_PLAY_URI enqueued), not scroll-end events. This validates the 8 px
   dead zone as sufficient without the elapsed-time safety net.

If evidence is not satisfactory, increase `SCROLL_DEAD_ZONE_PX` (e.g. to 12) before removing.
Document result in implementation notes.

---

## Known limitation — Release at scroll limit (VE-C5)

When `scrollOffset` is at 0 or `maxOffset` and the user presses and holds with a dy outside
the dead zone (list won't move because it's at the limit), Release will not fire a tap even
if the intent was a tap. The gesture was classified as a scroll attempt on Press entry; the
limit was hit before any rows advanced.

This is a known defect deferred to a future iteration. The correct fix (check whether
`scrollOffset` actually moved during the gesture) requires additional state. It is not
included in M-LIST-v4.

**Workaround**: users tapping at-limit rows should press near the centre of the row (short
natural drift stays in the dead zone).

---

## Phase 2 — fling momentum (not in scope, design notes)

On Release with `|dy| >= DEAD_ZONE_PX`, record and decay:
```cpp
_flingVelocity = _scrollVelocity;   // rows/s from last tickScroll
dragState = D_IDLE;
```

In `tickScroll()` D_IDLE branch:
```cpp
if (abs(_flingVelocity) > FLING_CUTOFF) {
    _flingVelocity *= (1.0f - FLING_RESISTANCE);
    _scrollAccum   += _flingVelocity * dt;
    // advance scrollOffset from _scrollAccum; hard stop at limits
}
```

Estimated: `FLING_RESISTANCE = 0.05f/frame`, `FLING_CUTOFF = 0.1f rows/s`.
Phase 2 adds only `_flingVelocity` + the D_IDLE branch. No structural change.

---

## Data model changes

New private members in `WinampDisplay`:

```cpp
float _scrollVelocity   = 0.0f;              // rows/s; stored after each tick (VE-C2)
float _scrollAccum      = 0.0f;              // fractional row accumulator
float _scrollSpeedK     = SCROLL_SPEED_K_DEFAULT;  // mutable for dbgSet (VE-C6)
static constexpr int   SCROLL_DEAD_ZONE_PX      = 8;
static constexpr float SCROLL_SPEED_K_DEFAULT   = 0.088f;
// Phase 2: float _flingVelocity = 0.0f;
```

Remove after DUT validation (VE-C4):
- `unsigned long _dragStartMs`

No change to `scrollOffset` type (stays `int`).

---

## Files changed

- `app/src/winamp/winampDisplay.h` — new members, `tickScroll(float dt)`, Release logic,
  snapshot-cancel in `drawPlaylist()`, `dbgGet`/`dbgSet` additions
- `app/src/appShell.h` (or SpotifyApp tick site) — compute real dt, call `display->tickScroll(dt)`
- `app/src/main.cpp` (or serial debug handler) — `cmdTick` command under `SERIAL_DEBUG`

---

## Open questions

1. **tickScroll call site** — confirm which method in `appShell.h`/`SpotifyApp` is the frame
   tick entry point. `lastScrollMs` tracking can live there or inside `tickScroll` as a member
   (member is cleaner; avoids call-site boilerplate).

2. **Re-anchor on repeated Press** — if user lifts mid-scroll and re-presses, new Press lands
   in D_IDLE (scroll stopped via Release reset), re-anchoring cleanly. No special handling needed.

3. **drawPlaylist() performance** — 5 rows of fillRect + Font-1 text ≈ 5–8 ms/frame at 40 MHz
   SPI. At 50 Hz tick ≤ 40% SPI occupancy while scrolling. Acceptable on dual-core ESP32.

---

## Exit criteria

- Finger drag in PLEDIT content area → playlist scrolls live (no commit-on-release)
- Holding finger still at nonzero offset → continuous scroll at constant rate; Release stops it
- Finger within dead zone at Release → tap plays the row (ACT_PLAY_URI)
- Finger outside dead zone at Release → no track play
- `tickScroll(dt)` is a no-op when dragState ≠ D_PLEDIT_SCROLL
- `get scrollAccum` and `get scrollVelocity` return values via serial debug harness
- `cmdTick n dtMs` advances scrollOffset deterministically (harness-testable speed scaling)
- `set speedK <val>` updates scroll speed without reflash
- Seqno change mid-drag → gesture cancelled, scrollOffset reset to 0, dragState D_IDLE
- DUT evidence: 5 firm-press taps register as taps (validates 8 px dead zone before `_dragStartMs` removal)
- No regression: PLEDIT chrome, scrollbar thumb (TASK-051e), D_PLEDIT_SCROLL_DIRECT, slider capture (TASK-101)
