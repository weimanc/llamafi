# M-MULTIAPP — Matrix Rain App Design

> Owner: Architect
> Status: draft
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [layout.md](layout.md)
> Source reference: `resource/5in1/5in1 cyberdeck CYD 2.8inch.txt` — `runMatrix()`

---

## Source algorithm

```cpp
void runMatrix() {
  if (modeChanged) {
    for (int i = 0; i < MAX_STREAMS; i++) {   // MAX_STREAMS = 14
      rain[i].x = i * 17 + 2;               // fixed x per stream, 17px stride
      rain[i].y = random(-400, 0);           // start above screen
      rain[i].speed = random(5, 15);         // pixels per tick (float in source)
      rain[i].length = random(15, 40);       // tail length in chars (×20px each)
    }
    modeChanged = false;
  }
  for (int i = 0; i < MAX_STREAMS; i++) {
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    char hC = random(33, 126);
    tft.drawChar(hC, rain[i].x, (int)rain[i].y, 2);          // white head
    tft.setTextColor(TFT_GREEN, TFT_BLACK);
    tft.drawChar(rain[i].lastChar, rain[i].x, (int)rain[i].y - 20, 2); // green trail
    tft.fillRect(rain[i].x, (int)rain[i].y - (rain[i].length * 20), 20, 20, TFT_BLACK); // erase tail
    rain[i].lastChar = hC;
    rain[i].y += rain[i].speed;
    if (rain[i].y > 320 + (rain[i].length * 20)) rain[i].y = -20; // wrap
  }
  delay(25);   // ~40 fps
}
```

Source struct (note `float y` and `float speed`):
```cpp
struct MatrixColumn { int x; float y; float speed; int length; char lastChar; };
```

Portrait: 240px wide, 320px tall. 14 streams at 17px stride = 14×17=238px ≈ fills 240px width.
Each glyph: font 2 ≈ 14px wide × 20px tall (TFT_eSPI proportional).

---

## Landscape adaptation

Canvas: full 275×240 (same rationale as GoL and Clock — visually distinct effect).

Streams run top→bottom in landscape exactly as in portrait. The adaptation is
minimal — only `x` stride and the `y` wrap threshold change:

| Parameter | Source (portrait) | Ours (landscape) |
|-----------|------------------|-----------------|
| Canvas height | 320 | 240 |
| Canvas width | 240 | 275 |
| Stream count | 14 | 14 (unchanged) |
| x stride | 17 px | `275/14 ≈ 20 px` → use 19 |
| `rain[i].x` init | `i * 17 + 2` | `i * 19 + 2` |
| y wrap threshold | `320 + length*20` | `240 + length*20` |
| y start range | `random(-400, 0)` | `random(-400, 0)` (unchanged) |

Everything else — white head, green trail, black erase, `float y`, `float speed`,
`random(33,126)` char, `delay(25)` → millis gate — ports verbatim.

---

## State struct correction

`app-lifecycle.md` has `int y, speed` in the Column struct. Source uses
`float y` and `float speed` — the fractional part gives smooth variable-speed
scrolling. Correct the struct:

```cpp
struct MatrixAppState {
    struct Column {
        int   x;
        float y;       // float, not int — fractional scroll position
        float speed;   // float, not int — fractional pixels per tick
        int   length;
        char  lastChar;
    } rain[14];
    bool initialised;
};
```

---

## Stream geometry verification

14 streams at stride 19, starting at x=2:
- Stream 0: x=2, stream 13: x=13×19+2=**249**
- Font 2 glyph width ≈ 14 px → rightmost glyph ends at 263
- Canvas right edge: 274. Gap: **11 px** — acceptable.

15 streams would overflow: i=14 → x=268, glyph ends at 282 > 274. 14 is correct.

`fillRect` erase width is 20 px (source). At stride 19 this means adjacent
stream erase rects overlap by 1 px. Harmless — both rects write black.

---

## appTick integration

Replace source's `delay(25)` with millis gate:

```cpp
void matrixTick(MatrixAppState &s) {
    static unsigned long lastMs = 0;
    unsigned long now = millis();
    if (now - lastMs < MATRIX_TICK_MS) return;
    lastMs = now;

    for (int i = 0; i < MATRIX_STREAMS; i++) {
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        char hC = random(33, 126);
        tft.drawChar(hC, s.rain[i].x, (int)s.rain[i].y, 2);
        tft.setTextColor(TFT_GREEN, TFT_BLACK);
        tft.drawChar(s.rain[i].lastChar, s.rain[i].x, (int)s.rain[i].y - 20, 2);
        tft.fillRect(s.rain[i].x, (int)s.rain[i].y - (s.rain[i].length * 20),
                     20, 20, TFT_BLACK);
        s.rain[i].lastChar = hC;
        s.rain[i].y += s.rain[i].speed;
        if (s.rain[i].y > MATRIX_CANVAS_H + (s.rain[i].length * 20))
            s.rain[i].y = -20.0f;
    }
}
```

`static unsigned long lastMs` retains its value across app switches. On restore,
if >25 ms have elapsed (always true), the first tick fires immediately —
streams resume mid-fall. Desired behaviour.

---

## initAppState / restoreAppState

`initAppState(Matrix)` — first launch only:
```cpp
void initMatrixState(MatrixAppState &s) {
    for (int i = 0; i < MATRIX_STREAMS; i++) {
        s.rain[i].x      = i * MATRIX_STRIDE + 2;
        s.rain[i].y      = (float)random(-400, 0);
        s.rain[i].speed  = (float)random(5, 15);
        s.rain[i].length = random(15, 40);
        s.rain[i].lastChar = ' ';
    }
    s.initialised = true;
}
```

`restoreAppState(Matrix)` — subsequent returns: no action. The `rain[]` array
in `g_appState` already holds the saved mid-fall positions. `matrixTick` resumes
on the next loop iteration.

---

## repaintApp(Matrix)

`switchApp()` calls `repaintApp(next)` after clearing the left canvas. For
Matrix there is no canonical pixel-accurate frame to reconstruct from state —
stream positions are continuous and glyphs are random. The correct repaint is:

```cpp
void repaintMatrix() {
    tft.fillRect(0, 0, MATRIX_CANVAS_W, MATRIX_CANVAS_H, TFT_BLACK);
    // Next matrixTick() call draws stream heads immediately.
}
```

The black fill is redundant (switchApp already called fillRect) but is kept
for correctness if repaintApp is ever called outside of a switchApp context.

---

## Touch input

A tap on the Matrix canvas (x < `TASKBAR_X`) reinitialises all streams:

```cpp
void matrixHandleInput(MatrixAppState &s, TouchPoint p) {
    if (p.x < TASKBAR_X) {
        initMatrixState(s);
        repaintMatrix();
    }
}
```

Reinit from tap scatters all streams back above the screen — produces a visible
"reset" effect as they fall in together. Same interaction as GoL tap-to-reseed.

---

## Constants

```cpp
#define MATRIX_STREAMS     14
#define MATRIX_STRIDE      19    // px between stream x positions
#define MATRIX_TICK_MS     25    // ~40 fps
#define MATRIX_CANVAS_W   275
#define MATRIX_CANVAS_H   240
```

---

## Open questions

None. Algorithm ports verbatim with two numeric substitutions (stride, canvas
height). Float struct types corrected. All lifecycle paths covered.

---

## Exit criteria

- **C1** — 14 streams visible; rightmost stream head does not overdraw taskbar
  (x < 275 at all times).
- **C2** — Streams wrap: a stream that exits bottom re-enters from y=-20 within
  one tick. No stream frozen off-screen.
- **C3** — App switch: GoL → Matrix → GoL — Winamp chrome pixel-correct after
  two `switchApp()` calls; no Matrix glyph residue in taskbar strip (x≥275).
- **C4** — Tap resets all streams; visible change within one tick.
- **C5** — Matrix → Spotify → Matrix: streams resume mid-fall (not restarted
  from above screen).
