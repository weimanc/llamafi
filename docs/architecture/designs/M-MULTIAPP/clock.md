# M-MULTIAPP — Clock App Design

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md)
> Source reference: `resource/5in1/5in1 cyberdeck CYD 2.8inch.txt` — `runClock()`

---

## Source algorithm

```cpp
void runClock() {
  if (modeChanged) {
    tft.drawRoundRect(5, 5, 230, 95, 10, 0xF81F);    // time box
    tft.drawRoundRect(5, 105, 230, 55, 10, 0x07FF);   // seconds bar box
    tft.drawRoundRect(5, 165, 230, 150, 10, 0xFFE0);  // date box
    modeChanged = false;
  }
  // Updates once per second (lsec guard)
  // Time: drawString(HH:MM, 120, 50, 6) — blinking colon on odd seconds
  // Seconds bar: 60 × 2px-wide rainbow-coloured rects, elapsed filled
  // Date: drawString(day-name, 120, 200, 4) + drawString(Mon DD YYYY, 120, 240, 4)
  // RSSI bars: bottom-right
}
```

Portrait layout (240×320 source):

| Element | y range | height |
|---------|---------|--------|
| Time box (HH:MM, font 6) | 5..100 | 95 px |
| Seconds bar (60 × 2px rects) | 105..160 | 55 px |
| Date box (day + date) | 165..315 | 150 px |

Total: ~310 px of 320 portrait height. Mostly vertical stacking.

---

## Landscape adaptation

Canvas: full 275×240 (same rationale as GoL — visually distinct, no Winamp chrome needed).

Portrait's vertical stack maps awkwardly to landscape (portrait height 320 > landscape height 240). Rearrange into two columns:

```
x=0        x=140     x=275
+----------+---------+  y=0
| HH:MM    | Day     |
|  (big)   | Date    |  y=120
+----------+---------+
| [seconds rainbow bar — full width] |  y=120..155
+------------------------------------+  y=155
|        (padding / empty)          |  y=155..240
+------------------------------------+
```

| Element | Position | Size |
|---------|----------|------|
| Time (font 6) | centred x=0..140, y=40 | fits in ~80×60 |
| Day name (font 4) | centred x=140..275, y=30 | |
| Date string (font 2) | centred x=140..275, y=70 | |
| Seconds bar | x=0..274, y=120..155 | 275×35 px |
| Rounded rect borders | adapt to new positions | |

Exact pixel positions are calibration targets (exit criterion C2). The source
`drawRoundRect` framing, blinking colon, and rainbow seconds-bar logic port
verbatim — only the coordinates change.

RSSI bars: omit or move to bottom-right of canvas (x≈250, y≈220). Low priority.

---

## State

```cpp
struct ClockAppState {
    // stateless — time via getLocalTime(), seconds bar redrawn each tick
    // modeChanged equivalent: initialised flag triggers border repaint
    bool initialised;
};
```

No data to save/restore beyond `initialised`. `getLocalTime()` always reflects
current time, so restoring clock state is just a full repaint.

---

## appTick integration

Update once per second (source uses `lsec` guard). In shell:

```cpp
void clockTick() {
    struct tm ti;
    if (!getLocalTime(&ti)) return;
    static int lsec = -1;
    if (ti.tm_sec == lsec) return;
    lsec = ti.tm_sec;
    repaintClock(ti);   // redraws time, seconds bar, date
}
```

`repaintClock()` implements the source's per-second update block verbatim
(time string, blinking colon, rainbow bar, date) with adapted coordinates.

On `initAppState(Clock)`: draw border boxes, call `repaintClock()` immediately.

---

## Open questions

1. **Two-column vs. three-row layout** — two-column proposed above. Confirm
   visually in preview before finalising coordinates.
2. **RSSI bars** — include or omit? Source shows them; they require `WiFi.RSSI()`
   which is already available in this project.
