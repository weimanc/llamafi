# R&D Report — M-WAVE-ATLAS Waveform Fidelity Options

> Owner: R&D
> Date: 2026-05-17
> Status: draft
> Relates-to: M-WAVE-ATLAS-wave-atlas.md, M-VIS-waveform-analysis.md

---

## Background

The wave atlas bake pipeline (`bake_wave.py`) is shipped. The extracted waveform is visually functional but shows two distinct blocky artefacts:

1. **Vertical quantization** — vis height is 16 px. Wave-y positions are integers 0..15. A smooth audio waveform, when snapped to the nearest row, looks like a staircase — especially on sections with moderate slope.
2. **Staircase on steep slopes** — where consecutive columns differ by 3+ rows, the vertical fill (correct Winamp rendering) creates a visible block-step pattern that reads as "quantized block wave" rather than a smooth analogue oscilloscope trace.

Both artefacts are bake-time problems: the atlas encodes integer row positions, so the ESP32 faithfully reproduces what's in the data. Improving fidelity means improving the data, not the renderer — all options below are host-side unless noted.

---

## Option A — Spatial smoothing (host-only, zero firmware cost)

**What it does:** Apply a low-pass filter along the x-axis (column direction) to wave-y values within each frame before emitting the atlas. A 3–5 tap box or Gaussian kernel rounds off sharp column-to-column transitions.

**Implementation:** One `scipy.ndimage.uniform_filter1d` (or manual convolution) call per frame in `bake_wave.py`:

```python
from scipy.ndimage import uniform_filter1d
wave_smooth = uniform_filter1d(wave_row.astype(float), size=3, mode='nearest')
wave[frame] = np.clip(np.round(wave_smooth), 0, VIS_H - 1).astype(np.uint8)
```

Kernel width 3 is conservative (one-neighbour blend); width 5 noticably softens transitions. Apply before boost/dc-offset so boost still reaches full rail.

**Effect:** Reduces inter-column jumps. Slope sections look smoother. Does not reduce the 16-level vertical quantization — individual rows are still integers.

**Cost:** Zero on firmware. Negligible at bake time (~0.5 ms per frame). New `--spatial-smooth N` flag in `bake_wave.py`.

**Risk:** Over-smoothing loses the "sharp transient" character of the source audio. Kernel width 3–5 is safe; avoid >7.

**Verdict:** Low-hanging fruit. Implement first. Complements all other options.

---

## Option B — Temporal smoothing (host-only, zero firmware cost)

**What it does:** Filter wave-y values along the time axis (per column, across frames). An exponentially-weighted moving average (EWM) or box filter damps frame-to-frame jitter — the "shimmer" where a column flickers between two adjacent rows.

**Implementation:** Apply after per-frame extraction, across the full atlas array:

```python
from scipy.ndimage import uniform_filter1d
# axis=0 is the time axis
atlas_smooth = uniform_filter1d(atlas.astype(float), size=3, axis=0, mode='wrap')
atlas = np.clip(np.round(atlas_smooth), 0, VIS_H - 1).astype(np.uint8)
```

`mode='wrap'` treats the atlas as a loop — avoids edge discontinuity at frame 0 and frame N-1.

**Effect:** Reduces temporal noise / shimmer on near-horizontal sections. Slightly slows the apparent speed of fast transients.

**Cost:** Zero on firmware. Negligible at bake time. New `--temporal-smooth N` flag.

**Risk:** Smears fast transients across frames. At kernel=3 the smear is ±1 frame (50 ms at 20 Hz) — perceptually negligible. At kernel=5 (±2 frames, 100 ms) fast peaks may appear sluggish.

**Verdict:** Orthogonal to A — combine both. Temporal=3 is safe as a default.

---

## Option C — Sub-pixel / temporal dithering (host-only, zero firmware cost)

**What it does:** Retain the fractional part of wave-y during extraction (currently discarded by `round()`). Where the true position is, say, 7.4, alternate the quantized row between 7 and 8 across consecutive frames weighted by the fraction. At 20 fps the eye temporally blends adjacent frames and perceives a position between two rows.

**Implementation outline:**

1. In `extract_wave_row`, accumulate fractional positions per column (store as float32 array) instead of immediately rounding.
2. After all frames are extracted, apply the dither: for each column, for each frame, compute `frac = wave_float[t, col] - floor(wave_float[t, col])`. Assign row `floor` with probability `(1 - frac)` and row `ceil` with probability `frac` — use a deterministic pattern (e.g. threshold against a 1D Bayer sequence along the time axis) rather than random noise, for stability.
3. Emit integer atlas as usual.

**Effect:** Perceived resolution increases from 16 to ~30+ effective levels on smooth sections. Most impactful for the gradual arc of a sine wave where the "staircase" is most visible.

**Cost:** Zero on firmware — atlas format unchanged (uint8 0..15). Moderate bake-time complexity: requires two-pass extraction (float first, dither second). New `--dither` flag.

**Risk:** Dithering introduces temporal noise that can look like a flickering waveform on sections where the source moves slowly. A Bayer/ordered dither (not random) minimises this. Should be applied AFTER spatial smoothing (A) so the fractional positions are themselves smooth.

**Verdict:** Highest fidelity gain per firmware-complexity cost (zero). More implementation work than A/B. Worth a dedicated R&D branch to validate visually before committing.

---

## Option D — 2-pixel-wide wave line (trivial firmware change)

**What it does:** In `tickWave()` (firmware), draw the wave at both `(x, y)` and `(x, y-1)` — doubling the line weight. Alternatively, draw the vertical fill span as 2 px wide by adding a `drawFastVLine` at `originX + RECT_X + x + 1`.

**Effect:** A thicker line makes 1-row staircase steps visually smaller relative to line weight — classic trick in analogue oscilloscope CRT rendering where the beam has finite width. Does not actually reduce quantization but makes it less objectionable.

**Cost on ESP32:** ~76 extra `putpixel`/`drawFastVLine` calls per frame (trivial). No atlas change needed — this is a pure renderer change.

**Risk:** Reduces effective vertical resolution from 16 to 15 usable rows (the doubled line eats 1 px of headroom). At VIS_H=16 this is acceptable. The vis area is 76×16 px — a 2 px line is 12.5% of height, which is within Winamp's original oscilloscope aesthetic.

**Verdict:** Cheapest firmware change for a visible quality improvement. Can be combined with any host-side option. Propose as part of wave atlas firmware mode task.

---

## Option E — Frame interpolation on the ESP32

**What it does:** If the display updates faster than 20 fps, linearly interpolate wave-y between the current and next atlas frame. For each column: `y = round(lerp(atlas[frame][col], atlas[frame+1][col], t))` where `t = elapsed / frame_period`.

**Effect:** Smooths temporal motion — transitions between frames appear as continuous movement rather than discrete jumps. Most impactful when the source audio has fast transients that produce large inter-frame jumps.

**Cost on ESP32:** 76 multiplies + 76 adds per render tick. Requires reading two atlas frames per tick (cache-friendly if frames are contiguous). Negligible CPU cost; no RAM cost beyond the two frame pointers.

**Risk:** Interpolating between integer positions can produce rounding artefacts (the lerp result snaps between two quantized rows). Combining with Option C (sub-pixel dithering in atlas) mitigates this. Loop wrap (frame N-1 → frame 0) needs handling: clamp or wrap-around lerp.

**Verdict:** Better suited to fast-content waveforms. For typical pop music the 20 Hz atlas already appears smooth. Implement after other options are validated; only worth it if inter-frame jumps remain visible post-A/B/C.

---

## Interaction Matrix

| | A (spatial) | B (temporal) | C (dither) | D (2px line) | E (lerp) |
|---|---|---|---|---|---|
| **A (spatial)** | — | complement | prerequisite for C | independent | independent |
| **B (temporal)** | complement | — | complement | independent | complement |
| **C (dither)** | needs A first | complement | — | independent | complement |
| **D (2px line)** | independent | independent | independent | — | independent |
| **E (lerp)** | independent | complement | complement | independent | — |

Recommended sequence: **A → B → C** on host (each improves on the previous). **D** in firmware alongside wave atlas playback mode. **E** only if needed after A–C.

---

## Recommended Next Steps

1. **Prototype A + B** in `bake_wave.py` on a short-lived branch. Regenerate `wave_zoom.gif` and compare visually. Both are low-risk and reversible (new CLI flags, no format change).
2. If A + B are satisfying: ship as defaults in `bake_wave.py`. Document chosen kernel widths.
3. If staircase quantization remains objectionable after A + B: prototype C (sub-pixel dithering). Requires more careful visual validation — evaluate on `wave_zoom.gif` at 6× scale.
4. **D** (2px line) can be proposed to PM as part of the wave atlas firmware mode task — negligible cost, visible improvement.
5. **E** (frame interpolation): defer; re-evaluate after A–D are on device.

If A + B + C are validated and worth productionising, raise PROP-003 for PM intake.
