# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.



### TASK-078 — Design: PLEDIT content-area drag UX improvements
**Owner**: Architect (whiteboard), then Developer
**Feature**: playlist-002, touch-002
**Status**: open (2026-05-23) — points 1 and 3 remain; point 2 resolved by TASK-101
**Blocked by**: nothing — T149/T150/T151/T153/T154 PASS (2026-06-05); capture verified
**Notes**: Current Zone 1 swipe is functional but unsatisfying. Three discussion points:

1. **Click vs gesture discrimination**: Current threshold (|dy| < 4px → tap, ≥4px →
   scroll) is crude. A proper discriminator would consider gesture velocity and/or
   total travel time: short fast → tap; slow long → scroll. Avoids mis-fires when
   the user intends a firm tap but moves slightly.
   Requires `_dragStartMs` timestamp added at `D_PLEDIT_SCROLL` Press entry
   (one-liner). Capture now verified (T149–T154 PASS), so dy/elapsed_ms is accurate.

2. ~~**Full-screen gesture capture**~~ — **RESOLVED by TASK-101** (M-TOUCH-CAPTURE
   DragState-first dispatch covers all four sliders including PLEDIT content swipe).
   No separate implementation needed here.

3. **Acceleration / momentum**: A single swipe increments scrollOffset by ±1
   regardless of gesture speed or length. A fast or long swipe should scroll 2–3
   rows. Simple model: `delta = max(1, abs(dy) / ROW_H)` — proportional to travel in
   row-heights. Cap at PLEDIT_ROW_COUNT to avoid jumping past all visible rows.
   Capture now verified (T149–T154 PASS); `abs(dy)` accurately measures full gesture travel.

---

> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
