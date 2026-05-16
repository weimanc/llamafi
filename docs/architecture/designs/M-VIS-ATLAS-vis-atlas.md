# Design — M-VIS-ATLAS Bar-Height Atlas Visualizer

> Owner: Architect
> Status: draft (2026-05-16)
> Implements: PROP-002
> R&D sources: M-VIS-animation-improvements.md, M-VIS-video-analysis-method.md, M-VIS-spectrum-analysis.md
> Deps: M-VIS (TASK-050a–c done), skin asset pipeline (ADR-003, ADR-014)

---

## Scope

Implement PROP-002: replace (or supplement) the synthetic spectrum with a looping atlas of real bar heights extracted from the committed Winamp 2 screengrab video. Deliver authentic Winamp spectral motion — real decay rates, real spectral shape — without audio coupling or on-device DSP.

**Includes:**

- Host-side `tools/bake_vis.py`: extract bar heights from video → `gen/vis_atlas.c` + `gen/vis_atlas.h`
- **Host-side animation preview**: `tools/preview_vis.py` produces an animated GIF and/or live window — iterate on the vis without touching the DUT
- Firmware `VIS_ATLAS` playback mode in `vuMeter.h`
- Determinism check (golden SHA256)
- Mode insertion into existing tap cycle

**Out of scope:** per-track audio coupling, new video capture, changes to `bake_skin.py`, matrix display, Q2/Q3/Q4 synthetic improvements (separate commit).

---

## 1. Bake Pipeline — `tools/bake_vis.py`

### Inputs

| Input | Path | Notes |
|---|---|---|
| Screengrab video | `resource/Screencast_20260516_060344.mkv` | Committed VP9 source |
| Vis area calibration | Hardcoded from M-VIS-spectrum-analysis.md | x=24..99, y=43..58 at scale 2.5× |

The video is at ~59 fps; atlas playback is 20 Hz. The script subsamples: extract every Nth frame where `N = round(source_fps / 20)`.

### Extraction algorithm

```
for each sampled frame:
    crop to vis area (scale-corrected)
    for bar i in 0..18:
        col_x = VIS_RECT_X + i * 4 + 1       # centre pixel of 3px bar
        scan column from y=VIS_LEFT_Y down to y=VIS_LEFT_Y + VIS_H - 1
        count non-background pixels (background: dot-matrix pattern, pre-classified)
        bar_h[i] = pixel_count                # 0..16
    emit frame row
```

Background classification: any pixel whose RGB565 matches `SKIN_MAIN_BG` pattern at that (x,y). The dot-matrix alternates `0x0C61` on even `(x+y)` and `0x0000` on odd — same values baked into skin atlas by `bake_skin.py`. Threshold tolerance: ±2 per channel (handles VP9 decode rounding).

### Output format

```c
// gen/vis_atlas.h
#pragma once
#define VIS_ATLAS_FRAMES  600    // 30 s × 20 Hz
#define VIS_ATLAS_BARS    19
extern const uint8_t VIS_ATLAS[VIS_ATLAS_FRAMES][VIS_ATLAS_BARS];

// gen/vis_atlas.c
#include "vis_atlas.h"
const uint8_t VIS_ATLAS[600][19] = {
    {12, 11, 9, 8, ...},
    ...
};
```

**Encoding:** byte-per-bar (not 4-bit packed). Rationale: avoids unpack cost per tick on device; 30 s at byte-per-bar = 11.4 KB — within flash budget (see §4). Switch to 4-bit packing if headroom tightens; the format change is isolated to the bake script and the unpack macro.

### Determinism

- Input video is committed; script is deterministic given fixed ffmpeg VP9 decode.
- After first bake, commit `gen/vis_atlas.sha256`.
- CI / dev check: `sha256sum -c gen/vis_atlas.sha256`. Document that the golden hash is host-specific (ffmpeg version matters); machines with different ffmpeg must re-generate and re-commit the golden.
- Alternative if cross-machine determinism is required: bake script exports a `gen/vis_atlas_frames.png` strip (one column per frame) as the canonical representation; golden check hashes the PNG, not the C array. The C array is re-generated from the PNG at bake time — PNG encode/decode is bit-exact across platforms.

### Running

```sh
cd Spotify-Diy-Thing/tools
python3 bake_vis.py \
    -i ../../resource/Screencast_20260516_060344.mkv \
    -o ../SpotifyDiyThing/gen \
    --duration 30                 # seconds; default 30
sha256sum -c ../SpotifyDiyThing/gen/vis_atlas.sha256
```

Dependencies: `ffmpeg` on PATH (frame extraction), `python3-pillow` (pixel classification). No new deps beyond what `bake_skin.py` already requires.

---

## 2. Host Animation Preview — `tools/preview_vis.py`

**Goal:** iterate on atlas content, frame selection, loop transition, and playback rate without touching the DUT. Output is an animated GIF that extends `skin_preview.png` with live vis animation, and optionally a live pygame window.

### Design

The preview tool composites atlas frames onto the existing skin preview base:

1. Load `gen/skin_assets.c` pixel data (or re-derive from the `.wsz` directly) to get `SKIN_MAIN_BG` and the skin sprite at 2.5× scale (320×240 display coordinate space → 800×600 preview).
2. Load `gen/vis_atlas.h` / `gen/vis_atlas.c` (parsed from the C source, or a companion `.npy` dump the bake script also emits).
3. For each frame in the atlas, draw the spectrum bars into the vis area using the same `VIS_ROW_COLOR[]` palette and geometry as the firmware renderer.
4. Assemble into an animated GIF at 20 fps (50 ms/frame) and write to `gen/skin_preview_animated.gif`.

```
gen/skin_preview.png           — existing static shot (unchanged)
gen/skin_preview_animated.gif  — NEW: animated, vis area cycling through atlas
```

The animated GIF replaces the vis area pixels; all other skin regions come from the base preview. The GIF loops indefinitely, matching on-device loop behaviour.

### Preview tool interface

```sh
# Animated GIF (default)
python3 tools/preview_vis.py \
    --atlas SpotifyDiyThing/gen/vis_atlas.npy \
    --skin  SpotifyDiyThing/gen/skin_preview.png \
    --out   SpotifyDiyThing/gen/skin_preview_animated.gif

# Live window (pygame) — real-time, interactive
python3 tools/preview_vis.py \
    --atlas SpotifyDiyThing/gen/vis_atlas.npy \
    --skin  SpotifyDiyThing/gen/skin_preview.png \
    --live

# Live window with synthetic fallback (no atlas needed — preview Q3 improvements)
python3 tools/preview_vis.py \
    --mode synthetic \
    --skin  SpotifyDiyThing/gen/skin_preview.png \
    --live
```

`--mode synthetic` runs the same AR(1)/inertia/oscillator logic as the firmware in Python so both animation strategies can be A/B compared on host before any DUT flash.

### Bake pipeline integration

`bake_vis.py` emits a companion `gen/vis_atlas.npy` (NumPy array, shape `[N_FRAMES, 19]`, uint8) alongside the C array. This is the canonical input to `preview_vis.py` — avoids parsing C source. The `.npy` is gitignored (derived artifact); the C array and SHA256 are committed.

### Dependencies

| Package | Purpose | Already needed? |
|---|---|---|
| `python3-pillow` | Image I/O, GIF assembly | Yes (bake_skin.py) |
| `numpy` | `.npy` load/store | New — lightweight |
| `pygame` | Live window | New — optional; only needed for `--live` |

`pygame` is not required for the GIF path. The `--live` flag can be gated behind an import guard with a clear error message.

### What the preview enables

- Inspect atlas content before committing (frame-by-frame via `--frame N` flag).
- Tune loop wrap point: `--loop-start F` / `--loop-end F` to select the sub-range with the smoothest wrap.
- Compare atlas vs synthetic side-by-side: run two live windows, one `--mode atlas`, one `--mode synthetic`.
- Share progress: commit `gen/skin_preview_animated.gif` to the repo for review without requiring a DUT flash.

---

## 3. Firmware — `VIS_ATLAS` Mode in `vuMeter.h`

### Data access

```cpp
#include "gen/vis_atlas.h"   // VIS_ATLAS[N_FRAMES][19], stored in flash (PROGMEM or const → .rodata)
```

On ESP32 with Arduino-ESP32 2.0.x, `const` arrays in global scope land in `.rodata` (flash-mapped). No explicit `PROGMEM` needed. Access via index is single-instruction dereference through the flash cache.

### Playback state

```cpp
// in vuMeter.h, file-static within the vis tick function
static uint16_t atlasFrame = 0;
static uint32_t atlasLastMs = 0;
```

### Tick logic

```cpp
void tickAtlas(uint32_t nowMs, bool is_playing) {
    if (!is_playing) return;   // freeze frame; hold last heights

    if (nowMs - atlasLastMs >= 50) {   // 50 ms = 20 Hz
        atlasLastMs = nowMs;
        atlasFrame = (atlasFrame + 1) % VIS_ATLAS_FRAMES;
    }

    blitVisBackground();

    for (int i = 0; i < SPEC_BARS; i++) {
        uint8_t barH = VIS_ATLAS[atlasFrame][i];   // 0..16
        int barX = originX + VIS_RECT_X + i * SPEC_BAR_STEP;
        for (int r = VIS_H - barH; r < VIS_H; r++) {
            tft.drawFastHLine(barX, originY + VIS_LEFT_Y + r, SPEC_BAR_W, VIS_ROW_COLOR[r]);
        }
    }
}
```

Peak dots are **not** rendered in atlas mode. Real Winamp vis footage already encodes the peak-dot decay by construction; synthesising a second layer of peak dots on top would double-count.

### Loop wrap transition

The wrap from frame `VIS_ATLAS_FRAMES - 1` back to frame 0 may produce a visible jump if the final frame differs significantly from the first. Mitigation:

1. During bake, the script reports the L1 distance between frame 0 and the final frame. If distance > threshold (e.g., sum of absolute bar-height differences > 30), it logs a warning: "Wrap jump may be visible — consider `--loop-end N` to select a lower-distance wrap point."
2. If a smooth wrap is needed, select a sub-range in the atlas where frame[end] ≈ frame[0] (both near the sequence's mean heights). The `preview_vis.py --loop-start / --loop-end` flags support this workflow.
3. Cross-fade is **not** implemented in firmware (no float lerp per bar × 16 ticks = 304 extra float ops at the wrap; not worth it for a decorative vis).

### Mode insertion into tap cycle

**Decision (shipped): Spectrum removed; Atlas is the primary bar-height mode and default boot mode.**

New sequence: **Atlas → Wave → VU → Blank → Atlas**

Rationale:
- Atlas supersedes Spectrum — real Winamp footage with authentic decay, boosted and trimmed for visual impact.
- Synthetic Spectrum retained in codebase (`tickSpectrum`, `VIS_SPECTRUM` enum value) but removed from the tap cycle; can be re-inserted if needed.
- Atlas is the default boot mode (`s_modeRef()` initialises to `VIS_ATLAS_MODE`).

```cpp
enum VisMode { VIS_VU, VIS_SPECTRUM, VIS_ATLAS_MODE, VIS_WAVE, VIS_BLANK };
// Tap cycle: VIS_ATLAS_MODE → VIS_WAVE → VIS_VU → VIS_BLANK → VIS_ATLAS_MODE
```

### Multiple energy tiers (optional — deferred)

PROP-002 names three energy-tier clips as optional scope. Architecture decision: **defer to a follow-on PROP.** Reasons:

1. A single 30-second atlas must ship and validate first (flash cost, loop quality, user perception).
2. Energy-tier switching requires a cross-fade or cut strategy at tier boundaries — non-trivial UX and implementation.
3. The synthetic VU envelope (`lLvl`) is already a derived signal, not real audio analysis; using it to gate atlas tiers adds coupling complexity without real musical coupling.
4. If the atlas loop is imperceptible (as expected at 30 s), energy tiers are not needed to avoid the looping artefact.

---

## 4. Flash Budget

From PROP-002: ~60 KB headroom post M-VIS / M-IO / M-UI-POLISH.

| Encoding | Duration | Size | % of 60 KB |
|---|---|---|---|
| Byte-per-bar | 10 s (200 frames × 19 B) | 3.8 KB | 6.3% |
| Byte-per-bar | 30 s (600 frames × 19 B) | 11.4 KB | 19% |
| 4-bit packed | 30 s (600 frames × 10 B) | 6.0 KB | 10% |

**Shipped: 9.1 s atlas (182 frames × 19 B = 3,458 bytes).** Raw 412-frame / 30 s extraction is post-processed by `bake_vis.py` before emit: quiet runs trimmed (thresh=4, keep=2 highest-energy frames per run) then heights scaled 1.5× (clamped to VIS_H=16). This reduces size from 7.8 KB to 3.4 KB while improving visual quality (peaks reach ceiling, quiet dead-air removed).

**Verified:** `pio run -e cyd2usb_winamp` → Flash 52.4% (1,374,121 / 2,621,440 bytes). Atlas in .rodata = 3,458 bytes, well within 12 KB budget.

---

## 5. Component Interfaces

No new architectural interfaces. All changes are localised to:

| File | Change |
|---|---|
| `tools/bake_vis.py` | New script (sibling to `bake_skin.py`) |
| `tools/preview_vis.py` | New script |
| `gen/vis_atlas.c` | Generated, committed |
| `gen/vis_atlas.h` | Generated, committed |
| `gen/vis_atlas.sha256` | Generated, committed |
| `gen/skin_preview_animated.gif` | Generated, committed (optional — may be large; consider gitignoring) |
| `SpotifyDiyThing/vuMeter.h` | Add `VIS_ATLAS` mode, `tickAtlas()`, update `VisMode` enum and `nextMode()` |

`spotifyDisplay.h` is unchanged. `winampSkinLCD.h` calls `vu::tick()` which dispatches internally by mode — no interface change.

---

## 6. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Atlas content too monotonous (single-genre footage) | `preview_vis.py` shows content before DUT flash; capture additional video if needed (separate task) |
| Flash tighter than 60 KB estimate | Measure actual headroom from .elf before committing atlas size; fall back to 4-bit packing or 10 s clip |
| ffmpeg version non-determinism | Offer PNG-strip golden as alternative; document host-specific SHA256 |
| Visible wrap jump | bake_vis.py reports wrap distance; preview_vis.py `--loop-end` flag lets you select a cleaner wrap without re-extraction |
| Mode tap sequence change (UX regression) | Spectrum removed from cycle (superseded). New 4-mode cycle: Atlas→Wave→VU→Blank. Atlas is boot default. |

---

## 7. Sub-tasks

| Task | Scope | Owner |
|---|---|---|
| TASK-052a | `tools/bake_vis.py`: frame extraction, bar-height scan, C + npy emit, SHA256 golden | Developer |
| TASK-052b | `tools/preview_vis.py`: animated GIF output | Developer |
| TASK-052c | `tools/preview_vis.py`: `--live` pygame window + `--mode synthetic` A/B mode | Developer |
| TASK-052d | Firmware: `VIS_ATLAS` mode + `tickAtlas()` in `vuMeter.h`, update `VisMode` enum + `nextMode()` | Developer |
| TASK-052e | Flash headroom check: measure `.elf` map after TASK-052d, confirm atlas size fits, document result | Developer |
| TASK-052f | VE: visual regression — confirm existing VU / Spectrum / Wave / Blank modes unchanged on DUT | VE |

Recommended implementation order: TASK-052a → TASK-052b → TASK-052c (host-side validates the atlas before any firmware work) → TASK-052d → TASK-052e → TASK-052f.

---

## 8. Exit Criteria

- `python3 tools/bake_vis.py` runs to completion; `sha256sum -c gen/vis_atlas.sha256` passes on the build machine.
- `python3 tools/preview_vis.py --atlas gen/vis_atlas.npy --skin gen/skin_preview.png --out gen/skin_preview_animated.gif` produces a valid animated GIF showing the skin with the atlas vis playing in the vis area.
- `--live` flag opens a pygame window with the vis animating in real time (both `--mode atlas` and `--mode synthetic`).
- On DUT: device boots into Atlas mode. Tapping vis area cycles Atlas → Wave → VU → Blank → Atlas.
- Atlas mode displays 19 bars, same geometry and colour table (`VIS_ROW_COLOR`) as Spectrum.
- Atlas always blits current frame; frame counter freezes on `!is_playing` (does not return early).
- Atlas loops cleanly; no visible crash or memory fault at wrap (L1 wrap distance = 23 ✓).
- Flash delta for `vis_atlas.c` ≤ 12 KB; actual 3.4 KB ✓ (post trim+boost, confirmed from build).
- VU / Wave / Blank modes: pixel-identical output to pre-ATLAS baseline on DUT (VE TASK-052f).
- Spectrum removed from tap cycle (superseded); implementation retained in codebase.
