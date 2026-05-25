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

Replace source's `delay(25)` with millis gate. `_lastTickMs` is a member variable
(not a static local) so it is visible in the class interface and can be reset in
`init()` if needed.

```cpp
void MatrixApp::matrixTick() {
    unsigned long now = millis();
    if (now - _lastTickMs < MATRIX_TICK_MS) return;
    _lastTickMs = now;

    for (int i = 0; i < MATRIX_STREAMS; i++) {
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        char hC = random(33, 126);
        tft.drawChar(hC, _s.rain[i].x, (int)_s.rain[i].y, 2);
        tft.setTextColor(TFT_GREEN, TFT_BLACK);
        tft.drawChar(_s.rain[i].lastChar, _s.rain[i].x, (int)_s.rain[i].y - 20, 2);
        tft.fillRect(_s.rain[i].x, (int)_s.rain[i].y - (_s.rain[i].length * 20),
                     20, 20, TFT_BLACK);
        _s.rain[i].lastChar = hC;
        _s.rain[i].y += _s.rain[i].speed;
        if (_s.rain[i].y > MATRIX_CANVAS_H + (_s.rain[i].length * 20))
            _s.rain[i].y = -20.0f;
    }
    tft.setTextColor(TFT_WHITE, TFT_BLACK);   // reset — producer rule (ADR-027)
}
```

`_lastTickMs` retains its value across app switches. On resume,
if >25 ms have elapsed (always true), the first tick fires immediately —
streams resume mid-fall. Desired behaviour.

---

## App ABC integration

Under the live `appShell.h` ABC, Matrix is a `MatrixApp : public App` class.
The free functions above become private methods; state is held as members.

```cpp
class MatrixApp : public App {
public:
    void init() override {
        initMatrixState();
        repaintMatrix();
    }
    void resume() override {
        // rain[] positions persist — no state restore needed.
        // Clear canvas so any residue from the previous app is gone.
        repaintMatrix();
    }
    void suspend() override {}   // no drag state; no-op

    void tick() override { matrixTick(); }

    // Press on the app canvas reinitialises all streams.
    // Returns true (consumed) to trigger the inter-gesture cooldown.
    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase == TouchPhase::Press) {
            initMatrixState();
            repaintMatrix();
            return true;
        }
        return false;
    }

private:
    MatrixAppState _s;
    unsigned long  _lastTickMs = 0;

    void initMatrixState();   // seeds rain[] — see below
    void matrixTick();        // per-frame update — see above
    void repaintMatrix();     // canvas clear — see below
};
```

`x < TASKBAR_X` is guaranteed by the shell before `handleInput` is called
(layering rule 2 from app-interface.md) — no extra guard needed inside the method.

---

## initMatrixState / repaintMatrix

`MatrixApp::init()` — first launch; also called on tap-reinit:
```cpp
void MatrixApp::initMatrixState() {
    for (int i = 0; i < MATRIX_STREAMS; i++) {
        _s.rain[i].x       = i * MATRIX_STRIDE + 2;
        _s.rain[i].y       = (float)random(-400, 0);
        _s.rain[i].speed   = (float)random(5, 15);
        _s.rain[i].length  = random(15, 40);
        _s.rain[i].lastChar = ' ';
    }
    _s.initialised = true;
}
```

`MatrixApp::resume()` — subsequent returns: `rain[]` already holds mid-fall
positions; only a canvas clear is needed. `matrixTick` resumes on the next
loop iteration.

```cpp
void MatrixApp::repaintMatrix() {
    tft.fillRect(0, 0, MATRIX_CANVAS_W, MATRIX_CANVAS_H, TFT_BLACK);
    // Next matrixTick() call draws stream heads immediately.
}
```

The black fill duplicates what `switchApp()` already does, but is kept so
`repaintMatrix()` is correct if called outside a switch context (e.g. tap-reinit).

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

## ADR-028 forward note

`matrixTick()` uses `tft.setTextColor()` / `tft.drawChar()` / `tft.fillRect()`
directly. ADR-028 (Canvas abstraction) is currently **proposed/blocked**. When it
activates, migrate these calls to `canvas.drawChar()` / `canvas.fillRect()` and
remove `tft.setTextColor()` entirely — the stateless Canvas API has no text-color
register to leak. No interface change to `MatrixApp` is required; only the
private method bodies change.

---

## Open questions

None. Algorithm ports verbatim with two numeric substitutions (stride, canvas
height). Float struct types corrected. All lifecycle paths covered under App ABC.

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
