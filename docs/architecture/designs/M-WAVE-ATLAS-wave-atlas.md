# Design — M-WAVE-ATLAS Oscilloscope Waveform Atlas

> Owner: Architect
> Status: draft (2026-05-17)
> R&D sources: M-VIS-waveform-analysis.md
> Deps: M-VIS-ATLAS (bake pipeline pattern), M-VIS (TASK-050c — tickWave firmware, done)

---

## Scope

Extend the bake pipeline to extract an oscilloscope waveform atlas from the committed Winamp 2 screengrab video and produce an animated host-side preview. The firmware `tickWave()` already ships a synthetic sine wave; this atlas provides a drop-in replacement with real Winamp waveform motion, parallel to how `vis_atlas` replaced the synthetic spectrum.

**Includes:**

- Host-side `tools/bake_wave.py`: extract per-column wave-y positions from video → `gen/wave_atlas.c` + `gen/wave_atlas.h`
- Host-side `tools/preview_wave.py`: animated GIF preview at 1:1 device pixels + 6× zoom crop
- Determinism check (golden SHA256)
- Calibration parameters documented here (dc-offset, boost, fallback propagation)

**Out of scope:** fidelity improvements (spatial/temporal smoothing, sub-pixel dithering — see R&D report `M-WAVE-ATLAS-fidelity-options.md`), firmware atlas playback mode (separate task), changes to `bake_skin.py`, `bake_vis.py`, or `preview_vis.py`.

---

## 1. Source Video

| Property | Value |
|---|---|
| File | `resource/Screencast_20260516_061832.webm` |
| Codec | VP9, 706×308, ~59 fps |
| Content | Winamp 2 in oscilloscope mode, white waveform on dot-matrix background |
| Scale / window | 2.5× scale, same Winamp window as spectrum video |

Same calibration constants as `bake_vis.py` apply (see §2).

---

## 2. Vis Area Calibration

The oscilloscope vis area occupies the same 76×16 skin-pixel region as the spectrum vis:

| Constant | Skin px | Frame px (at 2.5×, win_x=1, win_y=13) |
|---|---|---|
| x1 | 24 | 61 |
| y1 | 43 | 121 |
| x2 | 99 | 250 |
| y2 | 58 | 160 |

### DC-offset correction

The oscilloscope centre line in the committed video sits approximately 3 skin pixels above the geometric centre of the vis area (y1=43, centre=50). Root cause: the Winamp window y-origin in the oscilloscope recording differs slightly from the spectrum recording.

Correction applied post-extraction via `--dc-offset 3`: adds +3 to every `wave_y` value, shifting the detected waveform down 3 skin rows. After correction, atlas mean ≈ 7.6 vs centre = 8. This parameter is video-specific — a re-capture at a different window position requires re-measurement.

### Boost

Raw extraction at 1× produces a low-excursion waveform (values clustering in rows 4–11). `--boost 2.0` amplifies deviation from centre:

```
wave_y_out = clamp(round(centre + (wave_y - centre) * boost), 0, VIS_H-1)
```

At boost=2.0 the atlas spans rows 0..15 (full rail), giving a visually active waveform. Boost is applied after dc-offset.

### Full bake invocation

```sh
cd Spotify-Diy-Thing
python3 tools/bake_wave.py \
    -i ../resource/Screencast_20260516_061832.webm \
    -o SpotifyDiyThing/gen \
    --dc-offset 3 \
    --boost 2.0
cd SpotifyDiyThing/gen && sha256sum -c wave_atlas.sha256
```

---

## 3. Extraction Algorithm

```
for each sampled frame (every Nth frame, N = round(59/20) → 20 Hz):
    px = decode frame as RGB
    for col_skin in 0..75:
        col_frame = x1 + round(col_skin * 2.5)
        scan column top→bottom in vis rect
        find pixels where R,G,B > 200  (VP9 rounding on white: tolerance ±55 from 255)
        if found:
            among white pixels, take the one farthest from centre_frame
            wave_y[col] = round((peak_frame_row - y1) / scale), clamped 0..15
        else:
            if col > 0: wave_y[col] = wave_y[col-1]   # propagate left
            else:        wave_y[col] = VIS_H // 2       # centre fallback
```

**Farthest-from-centre selection:** Winamp fills vertically between consecutive samples, so a steeply-sloped column has multiple white pixels. Selecting the pixel farthest from centre recovers the sample's peak excursion rather than the fill midpoint.

**Propagate-left fallback:** Winamp's oscilloscope does not draw a waveform pixel in the rightmost skin column (col 75) — the waveform ends ~1 skin pixel short of the vis right edge. Without this fallback, the centre-snap (8) would produce a 4-pixel artefact in the last column every frame. Propagating from col 74 eliminates the artefact.

---

## 4. Output Format

```c
// gen/wave_atlas.h
#pragma once
#include <stdint.h>

#define WAVE_ATLAS_FRAMES  224     // ~11 s × 20 Hz
#define WAVE_ATLAS_COLS    76      // one entry per skin pixel column

extern const uint8_t WAVE_ATLAS[WAVE_ATLAS_FRAMES][WAVE_ATLAS_COLS];
```

**Encoding:** byte-per-column. Values 0..15, where 0 = top of vis area, 15 = bottom. Centre = 8 (maps to skin y = 50).

**Size:** 224 × 76 = 17,024 bytes (16.6 KB). Within the ~60 KB flash headroom established in M-VIS-ATLAS. If headroom tightens, halve the FPS or trim to 10 s.

**Determinism:** SHA256 of `wave_atlas.c` committed as `gen/wave_atlas.sha256`. Hash is host/ffmpeg-version specific — re-generate on a new machine rather than copying. `gen/wave_atlas.npy` is gitignored (derived).

---

## 5. Host Preview — `tools/preview_wave.py`

Renders atlas frames into `skin_preview.png` vis area and writes two GIFs:

| Output | Size | Description |
|---|---|---|
| `gen/skin_preview_wave.gif` | ~190 KB | Full 320×240 skin, vis area animated |
| `gen/wave_zoom.gif` | ~155 KB | Vis area only (76×16), 6× nearest-neighbour upscale |

```sh
python3 tools/preview_wave.py \
    --atlas SpotifyDiyThing/gen/wave_atlas.npy \
    --skin  SpotifyDiyThing/gen/skin_preview.png \
    --out   SpotifyDiyThing/gen/skin_preview_wave.gif
```

**Render logic** (mirrors `tickWave()` in `vuMeter.h`):

```python
prev_y = VIS_Y + (VIS_H - 1) // 2   # centre
for x in 0..75:
    y = VIS_Y + wave_row[x]
    draw vertical span from min(y, prev_y) to max(y, prev_y) in white
    prev_y = y
```

The zoom GIF is the primary review artefact — at 1:1 the vis area is 76×16 px and detail is invisible without magnification.

---

## 6. Coordinate Conventions

| Constant | Value | Notes |
|---|---|---|
| `VIS_X` | 24 | Skin-relative, no `originX` shift in preview |
| `VIS_Y` | 44 | `LEFT_Y + 1` — same +1 visual alignment tweak as `preview_vis.py` |
| `RECT_W` | 76 | Vis width in skin pixels |
| `VIS_H` | 16 | Vis height in skin pixels |
| `VIS_WAVE_COLOR` | `(255,255,255)` | VISCOLOR[18]; firmware `0xFFFF` |
| Centre row | 7 (0-indexed) | `(VIS_H-1)//2`; absolute y = 51 in preview |

Wave-y = 0 is the **top** of the vis area (maximum positive amplitude); wave-y = 15 is the **bottom**. This matches Winamp's oscilloscope coordinate system.

---

## 7. Files Changed

| File | Status | Notes |
|---|---|---|
| `tools/bake_wave.py` | New | Extraction script |
| `tools/preview_wave.py` | New | GIF preview script |
| `SpotifyDiyThing/gen/wave_atlas.c` | Generated, committed | 224 frames × 76 cols |
| `SpotifyDiyThing/gen/wave_atlas.h` | Generated, committed | — |
| `SpotifyDiyThing/gen/wave_atlas.sha256` | Generated, committed | Golden check |
| `SpotifyDiyThing/gen/skin_preview_wave.gif` | Generated, committed | Full-skin preview |
| `SpotifyDiyThing/gen/wave_zoom.gif` | Generated, committed | 6× zoom review |
| `.gitignore` | Updated | `vis_atlas.npy`, `wave_atlas.npy` gitignored |

`bake_skin.py`, `bake_vis.py`, `preview_vis.py`, `vuMeter.h` — unchanged.

---

## 8. Open Questions

| # | Question | Owner |
|---|---|---|
| OQ-1 | Fidelity: spatial/temporal smoothing and sub-pixel dithering options evaluated but not yet implemented — see `M-WAVE-ATLAS-fidelity-options.md`. If a PROP is raised, Architect reviews before scheduling. | R&D → Architect |
| OQ-2 | ~~Firmware: `tickWave()` currently plays a synthetic sine. A `VIS_WAVE_ATLAS` mode (parallel to `VIS_ATLAS_MODE` for the spectrum) would substitute atlas playback. Not yet tasked.~~ **Resolved** — design doc `M-WAVE-ATLAS-firmware-playback.md` covers `VIS_WAVE_ATLAS`, `tickWaveAtlas()`, tap cycle update, and sub-tasks TASK-053a–d. | Architect |
| OQ-3 | Loop wrap: L1 distance frame[0]↔frame[-1] = 106, flagged as potentially visible. No user complaint yet — monitor on DUT when atlas playback is wired in. | Developer |
