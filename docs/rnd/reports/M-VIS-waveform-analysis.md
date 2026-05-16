# R&D — Winamp Vis Waveform (Oscilloscope) Analysis

> Author: R&D Engineer
> Date: 2026-05-16
> Status: final
> Subject: Pixel-accurate measurements of the time-based waveform (oscilloscope) vis mode extracted from a Winamp screencast

---

## Input

| Item | Value |
|---|---|
| Video | `resource/Screencast_20260516_061832.webm` |
| Resolution | 706×308 |
| Codec | VP9, ~59 fps |
| Skin | `Spotify-Diy-Thing/skins/base-2.91.wsz` |
| Note | Recording begins with waveform paused (flat line visible) — ideal for thickness measurement |

---

## Method

Same pipeline as `M-VIS-video-analysis-method.md` (spectrum analyzer). Blue border pixels in MAIN.BMP anchor the vis area; scale derived from vis-to-skin dimension ratios.

---

## Results

### Scale and window origin

| Property | Value |
|---|---|
| Scale | **2.5×** (same Winamp window as spectrum recording) |
| Window origin (frame px) | (1, 7) |

Derivation:
- Left blue border line at frame x=56 → skin x=22 → `win_x = 56 − 22×2.5 = 1`
- Bottom blue border line at frame y=157 → skin y=60 → `win_y = 157 − 60×2.5 = 7`

### Vis area

Same physical region as spectrum vis (waveform and spectrum share the vis window):

| Property | Skin px | Frame px |
|---|---|---|
| Vis rect | x=23..102, y=42..59 (80×18) | x=58..256, y=112..154 (199×43) |
| Active content | x=24..99, y=43..58 (76×16) | x=61..249, y=114..152 (189×39) |
| Center y (silence) | y=50.5 | y≈133 |

### Waveform line

| Property | Value |
|---|---|
| Color | VISCOLOR[18] = (255, 255, 255) = white |
| Secondary color | VISCOLOR[19] = (214, 214, 222) — appears on steeper segments (possible compression artefact or secondary rendering pass) |
| Base thickness (skin) | **1 skin px** |
| Base thickness (frame) | ~2 frame px (mode across all columns) |
| Max thickness (frame) | 7 frame px (steep slope columns — Winamp fills vertically between consecutive samples) |

Line thickness distribution across 198 vis columns:

| Frame px | Skin px equiv | Column count | Notes |
|---|---|---|---|
| 1 | 0.4 | 54 | sub-pixel rendering / compression |
| 2 | 0.8 | 72 | flat/near-horizontal sections — **mode** |
| 4 | 1.6 | 48 | moderate slope |
| 6 | 2.4 | 6 | steep |
| 7 | 2.8 | 5 | steepest visible segments |

**Conclusion:** the waveform is drawn as a 1-skin-px-thick line. Winamp fills vertically between consecutive sample positions, so the apparent thickness grows with slope. The horizontal/flat section (paused/silence) renders as 2 frame px ≈ 1 skin px at 2.5× scale.

### Silence / paused position

The paused waveform line centre sits at frame y≈132–133, corresponding to:

```
skin y = (132.5 − 7) / 2.5 = 50.2 ≈ 50
```

This is the mid-point of the vis height (skin y=42..59, centre=50.5). Winamp maps amplitude=0 to the vertical centre.

---

## Key differences from spectrum mode

| Property | Spectrum (M-VIS-video-analysis-method.md) | Waveform (this report) |
|---|---|---|
| Background | Alternating dot-matrix: (24,24,41) / (0,0,0) | **Same alternating dot-matrix** |
| Active elements | 19 vertical bars, VISCOLOR[2..17] | 1-px line, VISCOLOR[18] |
| Peak indicator | VISCOLOR[23] peak dot | None |
| Vertical meaning | Frequency amplitude (bottom=0) | Sample amplitude (centre=0) |

---

## Pitfalls

1. **Background pattern present.** Waveform mode uses the same alternating dot-matrix (24,24,41) / (0,0,0) as spectrum mode — confirmed visually in frame crop. However, VP9 compression shifts the O-pixel values enough to fool a tight colour threshold on a single row scan. Use the blue border lines and vis-to-skin dimension ratio for scale (both methods converge on 2.5×).
2. **Line not flat when paused.** The paused waveform shows the last audio buffer, which is not necessarily silence. Use the brightest/most-populated horizontal band to estimate the centre, not a literal flat line.
3. **Two colours observed.** VISCOLOR[18] and [19] both appear in the waveform region. The distinction may be a Winamp rendering detail (two-pass draw) or VP9 compression. Treat [18] as the primary wave colour.
