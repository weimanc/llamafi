# Design — M-WAVE-ATLAS Firmware Playback Mode

> Owner: Architect
> Status: draft (2026-05-17)
> Resolves: OQ-2 from M-WAVE-ATLAS-wave-atlas.md
> Deps: M-WAVE-ATLAS (bake pipeline + atlas shipped), M-VIS-ATLAS (firmware pattern)

---

## Scope

Wire the committed `WAVE_ATLAS` into the ESP32 firmware as a new `VIS_WAVE_ATLAS` vis mode.
The bake pipeline and atlas data (`gen/wave_atlas.c`, `gen/wave_atlas.h`) are already shipped —
this design covers only the firmware changes needed to play them back on the display.

**Includes:**

- `tickWaveAtlas()` renderer in `vuMeter.h`
- `VIS_WAVE_ATLAS` entry in `VisMode` enum and `nextMode()` tap cycle
- Frame-rate gating (20 Hz) via `waveAtlasFrameRef()`
- Flash budget verification

**Out of scope:** fidelity improvements (spatial/temporal smoothing, sub-pixel dithering —
see `M-WAVE-ATLAS-fidelity-options.md`), firmware OQ-3 loop-wrap cross-fade, changes to
bake pipeline or preview tools.

---

## 1. Firmware Changes — `vuMeter.h`

### 1.1 Include the atlas

```cpp
#include "gen/wave_atlas.h"   // WAVE_ATLAS[WAVE_ATLAS_FRAMES][WAVE_ATLAS_COLS], uint8_t
```

On Arduino-ESP32 2.0.x, `const` arrays in global scope land in `.rodata` (flash-mapped).
No explicit `PROGMEM` needed. Index access is single-instruction dereference through the
flash cache — same pattern as `vis_atlas.h`.

### 1.2 Mode enum and state

```cpp
// Before: VIS_VU, VIS_SPECTRUM, VIS_ATLAS_MODE, VIS_WAVE, VIS_BLANK
// After:
enum VisMode { VIS_VU, VIS_SPECTRUM, VIS_ATLAS_MODE, VIS_WAVE, VIS_WAVE_ATLAS, VIS_BLANK };

inline uint16_t &waveAtlasFrameRef() { static uint16_t f = 0; return f; }
```

### 1.3 Tap cycle

**Decision: `VIS_WAVE_ATLAS` replaces `VIS_WAVE` in the tap cycle.** The synthetic sine
(`tickWave`) is superseded by the real Winamp waveform — same precedent as `VIS_ATLAS_MODE`
superseding `VIS_SPECTRUM`. `tickWave` stays in the codebase but is removed from `nextMode()`.

New cycle: **Atlas → WaveAtlas → VU → Blank → Atlas**

```cpp
inline void nextMode() {
  VisMode &m = s_modeRef();
  switch (m) {
    case VIS_ATLAS_MODE:  m = VIS_WAVE_ATLAS; break;
    case VIS_WAVE_ATLAS:  m = VIS_VU;         break;
    case VIS_VU:          m = VIS_BLANK;      break;
    case VIS_BLANK:       m = VIS_ATLAS_MODE; break;
    default:              m = VIS_ATLAS_MODE; break;
  }
}
```

### 1.4 `tickWaveAtlas()` renderer

Mirrors `tickWave()` geometry and `blitVisBackground()` pattern. Key difference from the
synthetic renderer: `prevY` is initialised from `row[0]`, **not** `centreY`. The synthetic
renderer always starts at centre because it computes `y[0]` from a continuous sine; the
atlas renderer must start at the actual atlas value — otherwise the first column always
draws a vertical span from centre to `row[0]`, producing a left-edge artefact identical
to the bug fixed in `preview_wave.py`.

```cpp
inline void tickWaveAtlas(int originX, int originY, const uint16_t *mainBg) {
  uint16_t &frame = waveAtlasFrameRef();
  static uint32_t lastMs = 0;

  const uint32_t now = millis();
  if (now - lastMs >= 50) {           // 1000 / 20 fps = 50 ms
    lastMs = now;
    frame = (frame + 1) % WAVE_ATLAS_FRAMES;
  }

  blitVisBackground(originX, originY, mainBg);

  const uint8_t *row = WAVE_ATLAS[frame];
  const int yBase = originY + LEFT_Y + 1;   // +1: same alignment tweak as preview_wave.py
  const int yMin  = yBase;
  const int yMax  = yBase + VIS_H - 1;

  int prevY = yBase + row[0];         // ← NOT centreY
  prevY = constrain(prevY, yMin, yMax);

  tft.startWrite();
  for (int x = 0; x < RECT_W; x++) {
    int y = yBase + (int)row[x];
    y = constrain(y, yMin, yMax);

    const int yTop = min(y, prevY);
    const int yBot = max(y, prevY);
    tft.drawFastVLine(originX + RECT_X + x, yTop, yBot - yTop + 1, VIS_WAVE_COLOR);
    prevY = y;
  }
  tft.endWrite();
}
```

### 1.5 Dispatch in `tick()`

```cpp
case VIS_WAVE_ATLAS: tickWaveAtlas(originX, originY, mainBg); break;
```

Frame counter advances inside `tickWaveAtlas()` regardless of `playing` state — the
waveform loops continuously. If a freeze-on-pause behaviour is wanted later, gate the
`frame++` on `playing` (same pattern as `tickAtlas()`); not required for v1.

---

## 2. Coordinate Notes

| Constant | Value | Notes |
|---|---|---|
| `RECT_X` | 24 | Skin-relative x of vis area left edge |
| `LEFT_Y` | 43 | Skin-relative y of vis area top edge |
| `yBase` | `originY + LEFT_Y + 1` | +1 visual alignment (matches `preview_wave.py VIS_Y = 44`) |
| `RECT_W` | 76 | Vis width in skin pixels (= `WAVE_ATLAS_COLS`) |
| `VIS_H` | 16 | Vis height in skin pixels |
| `VIS_WAVE_COLOR` | `0xFFFF` | White; VISCOLOR[18] in Winamp's colour table |
| Atlas encoding | `0` = top row, `15` = bottom row | 0-indexed; centre = 8 |

`yBase = originY + LEFT_Y + 1` rather than `originY + LEFT_Y` — the +1 corrects a
half-pixel visual offset observed during host preview development (`preview_wave.py`,
same tweak as `preview_vis.py`).

---

## 3. Flash Budget

| Asset | Size |
|---|---|
| `vis_atlas.c` (already shipped) | 3,458 B |
| `wave_atlas.c` (224 × 76 B) | 17,024 B |
| Combined delta | **~20 KB** |

Established headroom from M-VIS-ATLAS: ~60 KB. Combined atlas cost ~20 KB leaves ~40 KB
remaining. No packing required.

Verify after build:

```sh
cd Spotify-Diy-Thing
~/.platformio/penv/bin/pio run -e cyd2usb_winamp
# Check .pio/build/cyd2usb_winamp/firmware.elf map or pio's flash usage summary
```

---

## 4. Loop Wrap (OQ-3)

The atlas is 224 frames. Frame 223 → frame 0 L1 distance is 106 (mean ~1.4 rows per
column). At 20 fps this is a ~50 ms transition — perceptually similar to a normal
inter-frame jump in active music content. No mitigation in v1.

If the wrap is visible on DUT: select a sub-range in `bake_wave.py` where
`frame[end] ≈ frame[0]` (both near mean position) using `--frame-start / --frame-end`
flags (to be added to `bake_wave.py`). Cross-fade is not implemented in firmware.

---

## 5. Files Changed

| File | Change |
|---|---|
| `SpotifyDiyThing/vuMeter.h` | Add `VIS_WAVE_ATLAS` to enum; add `waveAtlasFrameRef()`; add `tickWaveAtlas()`; update `nextMode()`; add dispatch in `tick()` |
| `SpotifyDiyThing/SpotifyDiyThing.ino` | `#include "gen/wave_atlas.h"` if not pulled in via vuMeter |

`gen/wave_atlas.c`, `gen/wave_atlas.h` — already committed. `bake_wave.py`, `preview_wave.py` — unchanged.

---

## 6. Sub-tasks

| Task | Scope | Owner |
|---|---|---|
| TASK-053a | Firmware: `VIS_WAVE_ATLAS` enum + `waveAtlasFrameRef()` + `nextMode()` update | Developer |
| TASK-053b | Firmware: `tickWaveAtlas()` in `vuMeter.h` + dispatch in `tick()` | Developer |
| TASK-053c | Flash budget check: measure `.elf` after TASK-053b; confirm ≤ 40 KB remaining headroom | Developer |
| TASK-053d | VE: visual regression — Atlas / VU / Blank modes pixel-identical to pre-053 baseline; WaveAtlas displays correctly on DUT | VE |

Recommended order: TASK-053a → TASK-053b (can be one commit) → TASK-053c → TASK-053d.

---

## 7. Exit Criteria

- Device builds with `cyd2usb_winamp` env without error; flash usage ≤ previous + 17 KB.
- Tapping vis area cycles: Atlas → **WaveAtlas** → VU → Blank → Atlas.
- WaveAtlas mode displays white waveform animating at 20 fps in the 76×16 vis area.
- No left-edge spike artefact (prevY initialised from `row[0]`).
- No right-edge artefact (propagate-left fallback already baked into atlas data).
- Atlas, VU, Blank modes: pixel output unchanged from pre-053 baseline (VE TASK-053d).
- Synthetic `tickWave()` remains in codebase; removed from tap cycle.
