# Experiment — Wave Atlas Fidelity Options

> Owner: R&D
> Date: 2026-05-17
> Report: [M-WAVE-ATLAS-fidelity-options.md](../../reports/M-WAVE-ATLAS-fidelity-options.md)

Prototype outputs from visual evaluation of options A, B, C (spatial smoothing, temporal
smoothing, sub-pixel dithering) applied to the wave atlas bake pipeline.

All variants baked from `resource/Screencast_20260516_061832.webm` with `--dc-offset 3 --boost 2.0`.

## Assets

| File | Variant | Bake flags |
|------|---------|------------|
| `zoom_baseline.gif` | Baseline | _(none)_ |
| `zoom_A_spatial3.gif` | A | `--spatial-smooth 3` |
| `zoom_AB_spatial3_temporal3.gif` | A + B | `--spatial-smooth 3 --temporal-smooth 3` |
| `zoom_ABC_dither.gif` | A + B + C | `--spatial-smooth 3 --temporal-smooth 3 --dither` |
| `compare_frame60.png` | All 4, frame 60 | — |
| `compare_multiframe.png` | All 4, frames 20/60/100/160 | — |
| `zoom_AC_spatial3_dither.gif` | A + C | `--spatial-smooth 3 --dither` |
| `compare_AC_multiframe.png` | Baseline / A / AC, frames 20/60/100/160 | — |
| `zoom_AE_spatial3_errdiff.gif` | A + error diffusion (integer extract) | `--spatial-smooth 3 --error-diffusion` |
| `compare_AE_multiframe.png` | A / A+ED (integer extract), frames 20/60/100/160 | — |
| `zoom_AE_float_spatial3_errdiff.gif` | A + error diffusion (float extract) | `--spatial-smooth 3 --error-diffusion` + float extraction |
| `compare_float_extract.png` | A / A+ED integer / A+ED float, frames 20/60/100/160 | — |

All zoom GIFs are 6× nearest-neighbour upscales of the 76×16 px vis area, 224 frames @ 20 fps.

## Observations

- **A alone** is the clearest win: staircase eliminated, dynamic range preserved (0..14).
- **AB** produces the smoothest arc shapes but temporal kernel=3 pulls peaks inward (range 2..11),
  losing ~25% of the boosted excursion. Kernel=2 may be a better compromise.
- **ABC** adds sub-pixel shimmer on near-flat sections; effect is subtle in stills, visible in
  the animated GIF on plateau sections.
