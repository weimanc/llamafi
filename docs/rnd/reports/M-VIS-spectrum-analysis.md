# R&D — Winamp Vis Spectrum Analyzer Analysis

> Author: R&D Engineer
> Date: 2026-05-16
> Status: final
> Subject: Pixel-accurate measurements of the spectrum analyzer vis mode extracted from a Winamp screencast

---

## Input

| Item | Value |
|---|---|
| Video | `resource/Screencast_20260516_060344.webm` |
| Resolution | 689×316 |
| Codec | VP9, ~59 fps |
| Skin | `Spotify-Diy-Thing/skins/base-2.91.wsz` |
| Method | `M-VIS-video-analysis-method.md` |

---

## Results

### Scale and window origin

| Property | Value |
|---|---|
| Scale | **2.5×** |
| Window origin (frame px) | (~1.5, ~9.5) |

Derivation:
- Dot-matrix period = 5 frame px → scale = 5/2 = 2.5×
- Left blue border line at frame x≈56 → skin x=22 → `win_x ≈ 1.5`
- Bottom blue border line at frame y≈157 → skin y=60 → `win_y ≈ 9.5`

### Vis area

| Property | Skin px | Frame px |
|---|---|---|
| Vis rect (incl. border) | x=23..102, y=42..59 (80×18) | x=59..256, y=114..157 (198×44) |
| Active spectrum area | x=24..99, y=43..58 (76×16) | x=61..249, y=116..155 (189×40) |

### Bar geometry

| Property | Skin px |
|---|---|
| Bar width | 3 px |
| Gap width | 1 px |
| Bar unit (bar + gap) | 4 px |
| Total bars | 19 (76 px / 4 px per bar) |
| Active width | 76 px (x=24..99) |

### Colour gradient

16 levels, top-to-bottom = VISCOLOR[2..17]. Row 0 = top (highest amplitude), row 15 = bottom (lowest). Pixel colour assigned by absolute row position in vis, not by bar height fraction.

| Row | Skin y | VISCOLOR | RGB888 | RGB565 |
|---|---|---|---|---|
| 0 | 43 | [2] | (239, 49, 16) | 0xE903 |
| 1 | 44 | [3] | (206, 41, 16) | 0xCD02 |
| 2 | 45 | [4] | (214, 90,  0) | 0xD6B0 |
| 3 | 46 | [5] | (214,102,  0) | 0xD6CC |
| 4 | 47 | [6] | (214,115,  0) | 0xD6E0 |
| 5 | 48 | [7] | (198,123,  8) | 0xC6F1 |
| 6 | 49 | [8] | (222,165, 24) | 0xDEA3 |
| 7 | 50 | [9] | (214,181, 33) | 0xD6C4 |
| 8 | 51 | [10] | (189,222, 41) | 0xBDC5 |
| 9 | 52 | [11] | (148,222, 33) | 0x94C4 |
| 10 | 53 | [12] | (41, 206, 16) | 0x2982 |
| 11 | 54 | [13] | (50, 190, 16) | 0x32C2 |
| 12 | 55 | [14] | (57, 181, 16) | 0x3962 |
| 13 | 56 | [15] | (49, 156,  8) | 0x3141 |
| 14 | 57 | [16] | (41, 148,  0) | 0x2920 |
| 15 | 58 | [17] | (24, 132,  8) | 0x1901 |

### Peak dot

| Property | Value |
|---|---|
| Colour | VISCOLOR[23] = (150,150,150) = 0x94B2 |
| Width | 3 skin px (full bar width) |
| Height | 1 skin px |
| Position | Top of bar (same row as bar's topmost pixel) |
| Rise | Instant (jumps to bar top each frame) |
| Decay rate | ~3–4 skin px/frame at 60 Hz (~50 ms/row) |

Measured: ~8 frame pixels drop in 200 ms at 59 fps → 8/2.5 ≈ 3.2 skin px/frame.

### Background

Alternating dot-matrix, same as all vis modes:
- Even positions (skin x+y even): (24, 24, 41)
- Odd positions (skin x+y odd): (0, 0, 0)
