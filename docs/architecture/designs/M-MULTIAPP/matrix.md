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

## appTick integration

Replace source's `delay(25)` with millis gate:

```cpp
void matrixTick(MatrixAppState &s) {
    static unsigned long lastMs = 0;
    unsigned long now = millis();
    if (now - lastMs < 25) return;   // ~40 fps
    lastMs = now;
    // source's per-stream loop here, with landscape x/y constants
}
```

On `initAppState(Matrix)`: run the `modeChanged` init block (set x positions,
randomise y/speed/length). Set `s.initialised = true`.

On `restoreAppState(Matrix)`: restore `rain[]` array and continue from saved
position — streams resume mid-fall from where they were. This looks natural.
Full repaint not needed — next tick redraws.

---

## No open questions

Algorithm ports nearly verbatim. Two mechanical changes: x stride 17→19,
y wrap 320→240. Float types in struct. No design decisions required.
