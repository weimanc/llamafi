# Design — M-VIS Visualization Area

> Owner: Architect
> Status: updated (2026-05-16) — R&D pixel measurements incorporated; supersedes planned-2026-05-15 version
> Tracked-as: TASK-050a–c
> Deps: M6 (VU mode + envelope engine), TASK-049 (SKIN_MAIN_BG restore pattern)
> R&D sources: M-VIS-spectrum-analysis.md, M-VIS-waveform-analysis.md (both 2026-05-16, final)

## Scope

Replace fixed synthetic VU meter with tap-cycling visualizer in the vis area. Tap cycles:
**VU → Spectrum → Wave → Blank → VU**. No new API calls — all views derive from existing synthetic envelope engine (`lLvl`, `rLvl`, beat phase, LFO) in `vuMeter.h`.

---

## Vis area geometry

R&D pixel measurements from `M-VIS-spectrum-analysis.md` (scale 2.5×, confirmed by both reports):

```
MAIN.BMP full vis rect:  x=23..102 (80px), y=42..59 (18px)  — incl. 1px blue border
Active vis area:         x=24..99  (76px), y=43..58 (16px)  — spectrum + wave + VU use this
  VIS_RECT_X  = 24    (RECT_X in vuMeter.h)
  VIS_LEFT_Y  = 43    (LEFT_Y in vuMeter.h)
  VIS_RECT_W  = 76    (RECT_W)
  VIS_H       = 16    ← CORRECTED from 13; spans y=43..58 (confirmed R&D)

VU left bar:  y=43..48 (6px, RECT_H=6)
gap row:      y=49      from SKIN_MAIN_BG
VU right bar: y=50..55 (6px)
Spectrum:     full 16 rows y=43..58
Wave midline: y=50  (centre of 16-row area; R&D measured skin y=50.2 ≈ 50)
```

**Note for TASK-049:** `blitVisBackground()` region must use `VIS_H=16`, not 13.
**Note for TASK-050a:** `VIS_H` constant and hit-test bounds must use 16.

---

## Colour palette — VISCOLOR.TXT

Pixel-accurate RGB565 values measured from `M-VIS-spectrum-analysis.md`. Emit as:
```cpp
static constexpr uint16_t VIS_ROW_COLOR[16] = {
    0xE903, // row  0  y=43  red (highest amplitude)
    0xCD02, // row  1  y=44
    0xD6B0, // row  2  y=45
    0xD6CC, // row  3  y=46
    0xD6E0, // row  4  y=47
    0xC6F1, // row  5  y=48
    0xDEA3, // row  6  y=49
    0xD6C4, // row  7  y=50
    0xBDC5, // row  8  y=51
    0x94C4, // row  9  y=52
    0x2982, // row 10  y=53
    0x32C2, // row 11  y=54
    0x3962, // row 12  y=55
    0x3141, // row 13  y=56
    0x2920, // row 14  y=57
    0x1901, // row 15  y=58  dark green (lowest amplitude)
};
static constexpr uint16_t VIS_WAVE_COLOR = 0xFFFF;  // VISCOLOR[18] — white
static constexpr uint16_t VIS_PEAK_COLOR = 0x94B2;  // VISCOLOR[23] — grey
```

**Colour assignment rule (spectrum):** each pixel's colour is by its **absolute row position in the vis area**, not by bar height fraction. Row index `r = pixel_y - VIS_LEFT_Y` → `VIS_ROW_COLOR[r]`. Row 0 = topmost pixel (highest amplitude = red); row 15 = bottommost (low amplitude = dark green).

---

## Mode specs

### VU mode (unchanged)
Two 6-pixel bars (L/R), existing `tickVU()`. Not touched by this milestone except:
- `blitVisBackground()` now passes `VIS_H=16` for the background restore region (covers rows the spectrum/wave use, which includes the gap row at y=49).

---

### Spectrum mode (TASK-050b)

**R&D source:** `M-VIS-spectrum-analysis.md` — pixel-accurate bar geometry confirmed.

#### Bar geometry

| Property | Value |
|---|---|
| Bars | **19** |
| Bar width | **3 px** |
| Gap width | **1 px** |
| Bar unit | 4 px (bar + gap) |
| Total span | 19 × 4 = 76 px |
| Bar X for bar i | `originX + VIS_RECT_X + i * 4` |
| fillRect width | **3** |

#### Bin synthesis (19 bins, mono)

```
binLevel[i] = clamp(envelope × shape[i] × (1 + beatBoost(i)), 0.0, 1.0)

envelope = (lLvl + rLvl) * 0.5f
shape[19]  — constexpr float, pink-noise rolloff: shape[i] = 1.0f - (i / 18.0f) * 0.6f
beatBoost  — applied to low-freq bins only (i < 4): beat * 0.8f, else 0.0f
```

#### Render per tick

1. Restore `SKIN_MAIN_BG` for full vis area: `blitVisBackground()`.
2. For each bar `i` in 0..18:
   - `barH = (int)(binLevel[i] * VIS_H)` — pixel height.
   - `barX = originX + VIS_RECT_X + i * 4`
   - `barY_top = originY + VIS_LEFT_Y + (VIS_H - barH)`
   - For each filled pixel row `r` from `(VIS_H - barH)` to `VIS_H-1`:
     - Colour = `VIS_ROW_COLOR[r]`
   - Draw: `tft.fillRect(barX, barY_top, 3, barH, VIS_ROW_COLOR[VIS_H - barH])` is **wrong** — the bar spans multiple colours. Use a row loop:
     ```cpp
     for (int r = VIS_H - barH; r < VIS_H; r++) {
         tft.drawFastHLine(barX, originY + VIS_LEFT_Y + r, 3, VIS_ROW_COLOR[r]);
     }
     ```
   - Dedup: `lastBinH[19]` — skip loop if `barH == lastBinH[i]` (and peak unchanged).

3. **Peak dots:**
   - File-static `float specPeak[19] = {0}`.
   - Each tick: `if (binLevel[i] > specPeak[i]) specPeak[i] = binLevel[i];`
   - Decay: `specPeak[i] -= (1.0f / VIS_H);`  → 1 row per tick (at 20 Hz = 50 ms/row, matches R&D ~50 ms/row).
   - Clamp: `if (specPeak[i] < 0) specPeak[i] = 0;`
   - Peak row: `peakRow = (int)((1.0f - specPeak[i]) * VIS_H)`. Clamp to [0, VIS_H-1].
   - Draw: `tft.drawFastHLine(barX, originY + VIS_LEFT_Y + peakRow, 3, VIS_PEAK_COLOR);` — **3px wide** (full bar width), **1px tall**.
   - Dedup: `lastPeakRow[19]`.

#### Dedup arrays

```cpp
static int8_t lastBinH[19]    = {-1};
static int8_t lastPeakRow[19] = {-1};
```

---

### Wave mode (TASK-050c)

**R&D source:** `M-VIS-waveform-analysis.md` — midline, colour, vertical fill confirmed.

#### Synthesis

```
y[x] = clamp(
    VIS_CENTRE_Y + roundf(lLvl * 5.0f * sinf(wavePhase + x * WAVE_CYCLES * TWO_PI / VIS_RECT_W)),
    originY + VIS_LEFT_Y,
    originY + VIS_LEFT_Y + VIS_H - 1
)

VIS_CENTRE_Y = originY + VIS_LEFT_Y + (VIS_H - 1) / 2  =  originY + 50   (R&D: skin y=50.2 ≈ 50)
VIS_RECT_W   = 76
WAVE_CYCLES  = 2.5f
wavePhase    advances +0.3f per tick (20 Hz)
```

#### Render per tick — vertical fill (Winamp-accurate)

Winamp draws the waveform as connected line segments by filling vertically between consecutive sample positions. Single `drawPixel` per column is **not** correct.

```
1. Restore SKIN_MAIN_BG for full vis area: blitVisBackground().
2. For x in 0..75:
     screenX = originX + VIS_RECT_X + x
     y0 = y[x]
     y1 = (x == 0) ? y[0] : y[x-1]   // fill from previous sample
     yTop = min(y0, y1)
     yBot = max(y0, y1)
     tft.drawFastVLine(screenX, yTop, yBot - yTop + 1, VIS_WAVE_COLOR)  // 0xFFFF white
3. Advance wavePhase += 0.3f.
```

**Colour:** `VIS_WAVE_COLOR = 0xFFFF` (white, VISCOLOR[18]).  
**Paused/silence:** `lLvl` decays to 0 → flat line at y=50 drawn as single-pixel HLine. Natural, no special case.

---

### Blank mode

Restore `SKIN_MAIN_BG` rows for full vis area (16 rows), then idle. No draw calls each tick.

---

## Background restore

`blitVisBackground(originX, originY, mainBg)` — restores `SKIN_MAIN_BG` pixels for region:
```
window-local: x=VIS_RECT_X=24, y=VIS_LEFT_Y=43, w=VIS_RECT_W=76, h=VIS_H=16
```

Same pushImage-from-atlas pattern as TASK-049. Shared by spectrum, wave, and blank modes.

The dot-matrix background (even (x+y): `0x0C61` ≈ (24,24,41); odd: black) is pre-baked into `SKIN_MAIN_BG` from MAIN.BMP — no runtime generation needed.

---

## Constants summary (add to vuMeter.h)

```cpp
static constexpr int VIS_H       = 16;   // active height, y=43..58
static constexpr int SPEC_BARS   = 19;   // 19 bars × (3px + 1px gap) = 76px
static constexpr int SPEC_BAR_W  = 3;
static constexpr int SPEC_BAR_STEP = 4;  // bar + gap
```

---

## Sub-tasks

| Task | Scope |
|---|---|
| TASK-050a | `VisMode` enum + `nextMode()` + vis hit-test + touch dispatch + blank mode. **Use VIS_H=16.** |
| TASK-050b | Spectrum: 19 bars × 3px+1px-gap, `VIS_ROW_COLOR[]` gradient by absolute row, peak dots 3px wide grey, decay 1/VIS_H per tick |
| TASK-050c | Wave: phase-advancing sine, vertical-fill between samples, **white** (0xFFFF), midline y=50 |

---

## Corrections to prior TASK-050a/b/c specs (tasks.md)

The following items in the 2026-05-15 task notes are superseded by R&D data. Developer must use this doc as authoritative:

| Task | Old (wrong) | Correct |
|---|---|---|
| 050a | `VIS_H = RIGHT_Y + RECT_H - LEFT_Y = 13` | `VIS_H = 16` (y=43..58) |
| 050a | hit-test note says `y=originY+43..56` | `y=originY+43..58` |
| 050b | 38 bins, `i * 2` (2px wide) | 19 bars, `i * 4` step, 3px wide |
| 050b | green/yellow/red threshold colouring | `VIS_ROW_COLOR[r]` by absolute row |
| 050b | `specPeak[i] -= 0.008f` | `specPeak[i] -= 1.0f / VIS_H` (~0.0625f) |
| 050b | peak dot: `drawPixel` (1px) | `drawFastHLine(..., 3, VIS_PEAK_COLOR)` |
| 050b | `lastBinH[38]`, `lastPeakY[38]` | `lastBinH[19]`, `lastPeakRow[19]` |
| 050c | `TFT_GREEN` | `VIS_WAVE_COLOR = 0xFFFF` (white) |
| 050c | single `drawPixel` per column | `drawFastVLine` from y[x-1] to y[x] |
| 050c | `VIS_CENTRE_Y = originY + 49` | `originY + 50` (VIS_H=16: 43+7=50) |

---

## Exit criteria

- Tapping vis area cycles VU → Spectrum → Wave → Blank → VU on DUT.
- Spectrum: 19 bars, 3px wide, 1px gap. Per-row gradient red (top, row 0) → dark green (bottom, row 15). Peak dots 3px wide, grey (0x94B2), decay ~1 row per 50 ms.
- Wave: connected line (vertical fill between samples), amplitude tracks `lLvl`, flat white line at y=50 when paused, white pixels (0xFFFF).
- Blank: vis area shows skin background dot-matrix only.
- VU mode unchanged (regression check).
- Flash delta ≤ +1% on `cyd2usb_winamp`.
