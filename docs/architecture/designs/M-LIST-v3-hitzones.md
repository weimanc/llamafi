# Design — M-LIST-v3 PLEDIT Hit-zone Redesign

> Owner: Architect
> Status: planned (2026-05-22)
> Tracked-as: TASK-051d (swipe gesture), TASK-051i (scrollbar strip drag), TASK-051j (hitzones PNG + human review)
> Deps: M-LIST-v3 Feature 2 (scrollOffset), M-HITZONES tooling (TASK-054, done)

---

## Context

M-LIST-v3 adds swipe-to-scroll and scrollbar-strip drag to the PLEDIT content area. The existing hit-zone model (5 discrete tap zones, rows 0–4) must be extended to handle:

1. Tap-vs-swipe disambiguation in the content area
2. A new scrollbar-strip drag zone (right 19px of PLEDIT)
3. bake_skin.py zone registry update → regenerated `skin_hitzones.png`
4. Human visual review before implementation

---

## Absolute coordinates (originX = 22 for 320px screen)

| Landmark | Absolute x | Absolute y | w | h |
|----------|-----------|-----------|---|---|
| Content area (all rows) | 34 | 136 | 244 | 65 |
| Row 0 | 34 | 136 | 244 | 13 |
| Row 1 | 34 | 149 | 244 | 13 |
| Row 2 | 34 | 162 | 244 | 13 |
| Row 3 | 34 | 175 | 244 | 13 |
| Row 4 | 34 | 188 | 244 | 13 |
| Scrollbar strip | 278 | 136 | 19 | 65 |
| Bottom bar (full) | 22 | 201 | 275 | 38 |

Note: `originX` is runtime-computed as `(screenWidth - WINDOW_W) / 2`. All zone checks use `originX` not the hardcoded 22 — that value is correct for the 320px CYD but must not be hard-coded.

---

## Zone 1 — Content area: tap-vs-swipe disambiguation

### Current behaviour
Five separate tap zones (rows 0–4), each fires `ACT_PLAY_URI(row)` on any touch.

### New behaviour
The content area becomes a **gesture zone**. Touch events are classified on release:

```
touch start → record (startX, startY, startMs)
touch ongoing → track (currentX, currentY)
touch end:
    dy = currentY - startY
    if |dy| < SWIPE_THRESHOLD  →  tap  →  row = (startY - PLEDIT_ROWS_Y) / PLEDIT_ROW_H
                                           ACT_PLAY_URI(scrollOffset + row)
    elif dy < 0                →  swipe UP   →  scrollOffset = min(scrollOffset+1, count-PLEDIT_ROW_COUNT)
    else                       →  swipe DOWN →  scrollOffset = max(scrollOffset-1, 0)
```

**`SWIPE_THRESHOLD = 8px`** — half a row height (13px ÷ 2, rounded up). Rejects accidental finger drift on a tap; catches any deliberate upward or downward swipe.

The existing `dragState` infrastructure handles the ongoing tracking. Add `D_PLEDIT_SCROLL` state alongside `D_VOLUME_DRAG`.

### Why not separate swipe and tap zones?
The content area is 65px tall — splitting it into a scroll strip and a tap strip wastes half the tap targets. Gesture classification on release is the standard mobile pattern and matches Winamp 5.x + Audacious behaviour.

---

## Zone 2 — Scrollbar strip: direct scroll drag

Right 19px column of the PLEDIT frame (`SKIN_PLEDIT_RIGHT_SIDE`, x=278..296, y=136..200).

Touch anywhere in this strip → direct scroll:

```
on touch in scrollbar strip:
    dragState = D_PLEDIT_SCROLL_DIRECT
    // map Y continuously to scrollOffset
    rel_y     = clamp(currentY - PLEDIT_ROWS_Y, 0, track_h - 1)
    scrollOffset = rel_y * (count - PLEDIT_ROW_COUNT) / max(1, track_h - thumb_h)
    scrollOffset = clamp(scrollOffset, 0, count - PLEDIT_ROW_COUNT)
```

Redraws thumb on each sample (same cadence as volume knob drag). No tap action fires from this zone.

---

## Zone 3 — Scroll arrows (deferred)

The bottom bar right section contains scroll-up / scroll-down arrow buttons (visible in `SKIN_PLEDIT_BG` composite). Their exact pixel positions within the 150×38px right section have not been measured. Wiring these up is deferred — swipe and direct drag (Zones 1 & 2) are sufficient for launch.

---

## bake_skin.py zone registry update (TASK-051j)

Replace the five individual row entries with the redesigned zone set:

```python
# Old (remove):
pledit rows 0-4 | PLEDIT_CONTENT_X, PLEDIT_ROWS_Y + i*ROW_H, PLEDIT_CONTENT_W, PLEDIT_ROW_H | ROW0..ROW4

# New (add):
| Zone ID              | Rect                                              | Label          |
|----------------------|---------------------------------------------------|----------------|
| pledit_content       | (34, 136, 244, 65)                                | SWIPE/TAP      |
| pledit_row_0..4      | (34, 136+i*13, 244, 13)  [sub-labels, no fill]    | R0..R4         |
| pledit_scrollbar     | (278, 136, 19, 65)                                | SCROLL DRAG    |
```

Sub-row labels drawn without magenta fill (informational only — the gesture zone covers all rows as one unit).

---

## Human review checkpoint (TASK-051j)

Before any firmware code is written:

1. Run `bake_skin.py` → regenerates `gen/skin_hitzones.png` with new zones.
2. Human inspects: do `SWIPE/TAP` and `SCROLL DRAG` zones cover the right pixels? Do sub-row labels align with the visible row dividers?
3. Sign-off → proceed to TASK-051b–e firmware implementation.

This is the same gate used for M-LIST-v2 (TASK-047a).

---

## dragState additions

```cpp
enum DragState {
  D_IDLE,
  D_VOLUME_DRAG,          // existing
  D_PLEDIT_SCROLL,        // new — swipe in content area (Zone 1)
  D_PLEDIT_SCROLL_DIRECT, // new — drag in scrollbar strip (Zone 2)
};
```

`startY` already tracked for volume drag-start. Reuse for PLEDIT swipe start.

---

## Exit criteria

- Tap on a row (vertical movement < 8px) fires `ACT_PLAY_URI` for the correct `scrollOffset + row`.
- Swipe up/down (≥ 8px) increments/decrements `scrollOffset` by 1; content redraws.
- Drag in scrollbar strip maps Y continuously to `scrollOffset`; thumb tracks finger.
- `skin_hitzones.png` shows `SWIPE/TAP` over content area and `SCROLL DRAG` over right strip.
- Human sign-off on hitzones PNG before firmware implementation.
- No regression in existing tap-to-play (T115/T116) — verify with `SWIPE_THRESHOLD` at 8px.
