# M-MULTIAPP — Game of Life App Design

> Owner: Architect
> Status: draft — App ABC integration pending
> Date: 2026-05-22
> Part of: [overview.md](overview.md)
> See also: [app-lifecycle.md](app-lifecycle.md), [app-interface.md](app-interface.md), [layout.md](layout.md)
> Source reference: `resource/5in1/5in1 cyberdeck CYD 2.8inch.txt` — `runLife()` / `spawnLife()`

---

## Context / pain points

Game of Life is AppId 5 in the M-MULTIAPP registry. The 5in1 reference
(`resource/5in1/5in1 cyberdeck CYD 2.8inch.txt`) contains a complete,
working GoL implementation in `runLife()` / `spawnLife()`. The algorithm
is proven — we port it, not reinvent it.

What the source implements (baseline for this doc):

- **Grid**: `uint8_t grid[GRID_W][GRID_H]` and `nextGrid[GRID_W][GRID_H]`
  as globals. Values are strictly 0 or 1.
- **Border**: Toroidal — `(x+i+GRID_W)%GRID_W`, `(y+j+GRID_H)%GRID_H`.
- **Color**: Position-based spatial gradient with global hue drift:
  `r=(x*4+hueShift)%255`, `g=(y*2+hueShift/2)%255`, `b=255-r`.
  `hueShift` incremented by 3 each generation.
- **Cell render**: `fillRect(x*5, y*5, 4, 4, color)` — 4×4 px fill in a
  5×5 cell, leaving a 1px gap between cells.
- **Diff render**: only cells that changed between `grid` and `nextGrid`
  are redrawn.
- **Init density**: `random(100) < 20` → 20% live cells.
- **Stagnation**: reset when `sameCountTimer > 120` OR `totalAlive < 5`.
- **Rate**: `delay(100)` at end of `runLife()` → 10 gen/s.
- **Live count HUD**: `drawRightString(String(totalAlive), 235, 10, 2)`
  in top-right corner each generation.

The 5in1 source targets **portrait** (240×320, `setRotation(0)`).
GRID_W=48, GRID_H=60 at 5px/cell = 240×300 (portrait).

This device is **landscape** (320×240). Our app canvas is 275×240 (full
left column, since GoL is visually distinct enough to overwrite Winamp chrome —
see `layout.md`). Portrait GRID_W maps to landscape horizontal, portrait
GRID_H maps to landscape vertical: use `GRID_W=55, GRID_H=48`
at 5px/cell = 275×240 exactly.

**The only mandatory change from source:** grid dimensions and array size.
All other algorithm logic ports verbatim or near-verbatim.

---

## Goals

1. Port the 5in1 GoL algorithm faithfully — no unnecessary reinvention.
2. Adapt grid dimensions to landscape 275×240 canvas.
3. Integrate with shell lifecycle per `app-interface.md` App ABC
   (`LifeApp : public App` — `init`, `resume`, `suspend`, `tick`, `handleInput`).
4. No network dependency. No FreeRTOS task beyond main loop.
5. State preserved across app switches (returns to same generation / hueShift).
6. Stagnation auto-resets — never freezes on screen.

---

## Grid geometry

| Constant | Source | Ours | Reason |
|----------|--------|------|--------|
| `GRID_W` | 48 | 55 | 55×5=275 = canvas width |
| `GRID_H` | 60 | 48 | 48×5=240 = canvas height |
| `CELL_PX` | 5 | 5 | unchanged |
| Cell fill | 4×4 | 4×4 | 1px gap — unchanged |

Grid arrays are **column-major** `[x][y]` following the source convention:
`grid[GRID_W][GRID_H]` = `grid[55][48]`. Inner loop is `y`, outer is `x`.

---

## LifeAppState (revised)

```cpp
struct LifeAppState {
    uint8_t  grid[55][48];      // [x][y], 0=dead 1=alive — col-major per source
    uint16_t hueShift;          // global colour drift, += 3 per generation
    int      lastCellCount;     // live-cell count from previous generation
    int      sameCountTimer;    // generations without liveCount change
    bool     initialised;
};
```

`nextGrid` is **not** in the state struct — it is scratch used during
`stepGeneration()`. Declare it as a file-scope static in `appShell.cpp`
(or `golApp.cpp`), matching the source's global pattern:

```cpp
static uint8_t s_nextGrid[55][48];   // scratch buffer, not persisted
```

State struct size: 55×48=2640 bytes + 8 bytes = **2648 bytes**.
Total named-struct cost for all 6 apps remains ~3.8 KB.

Note: `app-lifecycle.md` had `grid[48][55]` (row-major) and `prevLiveCount`
— those were errors introduced before reading the source. Correct both here:
`grid[55][48]` col-major, `lastCellCount` (source naming).

---

## spawnLife() port

```cpp
void spawnLife(LifeAppState &s) {
    // Source shows a "GENERATING SEED..." splash — omit or adapt for shell context.
    // In shell: clear is already done by switchApp(); no extra fill needed.
    for (int x = 0; x < 55; x++)
        for (int y = 0; y < 48; y++)
            s.grid[x][y] = (random(100) < 20) ? 1 : 0;  // 20% density, per source
    s.sameCountTimer = 0;
    s.hueShift = 0;   // reset on reseed — clean colour restart each generation
}
```

---

## stepGeneration() port

Verbatim algorithm from source, adapted for GRID_W=55, GRID_H=48:

```cpp
void stepGeneration(LifeAppState &s) {
    int totalAlive = 0;
    for (int x = 0; x < 55; x++) {
        for (int y = 0; y < 48; y++) {
            int n = 0;
            for (int dx = -1; dx <= 1; dx++)
                for (int dy = -1; dy <= 1; dy++) {
                    if (dx == 0 && dy == 0) continue;
                    if (s.grid[(x+dx+55)%55][(y+dy+48)%48] > 0) n++;
                }
            if (s.grid[x][y] > 0)
                s_nextGrid[x][y] = (n == 2 || n == 3) ? 1 : 0;
            else
                s_nextGrid[x][y] = (n == 3) ? 1 : 0;
            if (s_nextGrid[x][y] > 0) totalAlive++;
        }
    }
    // Diff render — only changed cells
    for (int x = 0; x < 55; x++) {
        for (int y = 0; y < 48; y++) {
            if (s.grid[x][y] != s_nextGrid[x][y]) {
                if (s_nextGrid[x][y] > 0) {
                    uint8_t r = (x * 4 + s.hueShift) % 255;
                    uint8_t g = (y * 2 + s.hueShift / 2) % 255;
                    tft.fillRect(x*5, y*5, 4, 4, tft.color565(r, g, 255-r));
                } else {
                    tft.fillRect(x*5, y*5, 4, 4, TFT_BLACK);
                }
            }
            s.grid[x][y] = s_nextGrid[x][y];
        }
    }
    // Live-count HUD (top-right of GoL canvas — adjust x for landscape)
    tft.fillRect(215, 0, 55, 15, TFT_BLACK);
    tft.setTextColor(0x07FF);
    tft.drawRightString(String(totalAlive), 270, 2, 2);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);   // reset — producer rule (ADR-027)

    // Stagnation
    if (totalAlive == s.lastCellCount) s.sameCountTimer++;
    else                               s.sameCountTimer = 0;
    s.lastCellCount = totalAlive;
    s.hueShift += 3;

    if (totalAlive < 5 || s.sameCountTimer > 120) {
        spawnLife(s);
        resume();   // full redraw after reseed (replaces repaintApp(AppId::Life))
    }
}
```

The source's `delay(1500)` before respawn is blocking and incompatible with
the shell's non-blocking tick model. Dropped — immediate respawn.

---

## App ABC integration

Under the live `appShell.h` ABC, GoL is a `LifeApp : public App` class.
Free functions become private methods; `_s`, `_lastTickMs`, and `s_nextGrid`
(scratch buffer) are owned by the class.

```cpp
class LifeApp : public App {
public:
    void init() override { spawnLife(_s); resume(); }

    void resume() override {
        tft.fillRect(0, 0, GOL_GRID_W * GOL_CELL_PX, GOL_GRID_H * GOL_CELL_PX, TFT_BLACK);
        repaintLife(_s);
    }

    void suspend() override {}   // no gesture state; no-op

    void tick() override { golTick(); }

    // Press on the GoL canvas reseeds all cells.
    // x < TASKBAR_X is guaranteed by the shell (layering rule 2, app-interface.md).
    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase == TouchPhase::Press) {
            spawnLife(_s);
            resume();
            return true;
        }
        return false;
    }

private:
    LifeAppState  _s;
    unsigned long _lastTickMs = 0;   // replaces static unsigned long lastMs

    static uint8_t s_nextGrid[GOL_GRID_W][GOL_GRID_H];   // scratch; not persisted

    void spawnLife(LifeAppState &s);
    void stepGeneration(LifeAppState &s);
    void repaintLife(LifeAppState &s);
    void golTick();
};
```

`millis()`-gated tick, per source's `delay(100)` pattern:

```cpp
void LifeApp::golTick() {
    unsigned long now = millis();
    if (now - _lastTickMs < GOL_TICK_MS) return;
    _lastTickMs = now;
    stepGeneration(_s);
}
```

The source used `delay(100)` at the end of `runLife()`. The `millis()` gate
keeps other shell work (taskbar input, etc.) unblocked.

---

## repaintLife()

Full repaint from state — called by `resume()` and after reseed:

```cpp
void LifeApp::repaintLife(LifeAppState &s) {
    tft.fillRect(0, 0, 275, 240, TFT_BLACK);
    for (int x = 0; x < 55; x++) {
        for (int y = 0; y < 48; y++) {
            if (s.grid[x][y] > 0) {
                uint8_t r = (x * 4 + s.hueShift) % 255;
                uint8_t g = (y * 2 + s.hueShift / 2) % 255;
                tft.fillRect(x*5, y*5, 4, 4, tft.color565(r, g, 255-r));
            }
        }
    }
}
```

---

## Touch input

Source cycles app mode on any touch. In the shell, taskbar taps are consumed
by the shell before reaching `LifeApp::handleInput()` (layering rule 2). A
GoL-canvas `Press` triggers reseed and returns `true` (consumed). `Move` and
`Release` return `false`.

---

## Constants

```cpp
#define GOL_GRID_W        55
#define GOL_GRID_H        48
#define GOL_CELL_PX        5   // cell stride
#define GOL_CELL_FILL      4   // fill size (1px gap — from source)
#define GOL_TICK_MS      100
#define GOL_STAGNATION   120   // sameCountTimer threshold — from source
#define GOL_MIN_ALIVE      5   // totalAlive < this → reseed — from source
#define GOL_INIT_DENSITY  20   // random(100) < N → alive — from source
```

---

## Open questions

~~1. **Live-count HUD position**~~ **CLOSED.** `drawRightString` at x=270, y=2. Confirmed.

~~2. **"GENERATING SEED…" splash**~~ **CLOSED.** No text overlay on reseed.
Shell clear + immediate `resume()` is sufficient.

~~3. **hueShift reset on reseed**~~ **CLOSED.** Reset `hueShift = 0` in
`spawnLife()`. Clean colour restart on each reseed.

---

## Exit criteria

- **C1** — Glider traverses toroidal boundary and re-enters correctly.
- **C2** — Full repaint renders within x:0..274, y:0..239; no pixel outside.
- **C3** — Stagnation fires within 13 s on a forced still-life.
- **C4** — `totalAlive < 5` path triggers reseed (all-dead board).
- **C5** — Spotify → GoL → Spotify: Winamp chrome pixel-correct after two
  `switchApp()` calls; no GoL residue.
- **C6** — Tap on GoL canvas reseeds within one tick.
- **C7** — Diff render: only changed cells pushed to TFT (confirm with a
  logic analyser or SPI byte count comparison vs. full repaint).
