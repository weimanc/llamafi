# PROP-002 — 2026-05-16 — Bar-height atlas from real Winamp vis footage

> Owner: R&D

---

**Origin**: `docs/rnd/reports/M-VIS-animation-improvements.md` (Q1), informed by `M-VIS-video-analysis-method.md`, `M-VIS-spectrum-analysis.md`

**Summary**: Replace (or supplement) the current synthetic spectrum animation with a looping atlas of real bar heights captured from a Winamp 2 screengrab video. The atlas is extracted from existing footage via a pipeline extension, stored as a compact C array in flash, and played back at 20 Hz on-device. Result: authentic Winamp spectral motion — real decay rates, real spectral shape, real attack/sustain behaviour — without requiring Spotify audio analysis access or on-device audio decoding.

**Prototype evidence**: No code prototype; this proposal is based on a feasibility study. Key findings:

- The earlier Option C rejection (full RGB565 frames, 2,432 bytes/frame) does not apply to height-only representation. At 19 bars × 4 bits = 10 bytes/frame, a 30-second atlas costs **6.0 KB flash** (4-bit packed) vs 77.2 KB for RGB565 — a 250× reduction.
- The existing video analysis pipeline (`M-VIS-video-analysis-method.md`) already performs the hard work: frame extraction, vis-area calibration, background pixel classification. Extracting bar heights requires one additional vertical-scan pass (~40 lines of Python).
- Current flash headroom is ~60 KB (post M-VIS / M-IO / M-UI-POLISH). A 30-second atlas consumes ~10% of that; three energy-tier clips (quiet / medium / loud) at 10 seconds each consume ~10 KB total.
- Device-side rendering is unchanged: the existing bar renderer (`drawFastHLine` per row, `blitVisBackground`) accepts heights directly. A new `VIS_ATLAS` mode indexes the array by frame counter and calls the same renderer.
- The screengrab video (`resource/Screencast_20260516_060344.webm`, 689×316, VP9 ~59 fps) is already committed and was used for the spectrum analysis. It is the capture source.

**Suggested scope**:

_In scope:_
- Extend `tools/bake_vis.py` (new sibling to `bake_skin.py`) to extract bar heights from the committed screengrab video and emit `gen/vis_atlas.c` + `gen/vis_atlas.h` containing `VIS_ATLAS[N_FRAMES][SPEC_BARS]`.
- Add a determinism check: re-running the script on the same input video produces byte-identical output; SHA256 golden hash committed alongside.
- Add a new `VIS_ATLAS` vis mode to `vuMeter.h` that cycles in via the existing tap sequence (VU → Spectrum → Wave → **Atlas** → Blank → VU, or replaces Spectrum).
- Playback: advance frame counter at 20 Hz; pause on `!is_playing`; loop.
- Optional (scope decision for Architect/Developer): multiple energy-tier clips selected by `lLvl` threshold.

_Out of scope:_
- Per-track music coupling — the atlas loops identically regardless of what is playing. This is a known limitation accepted at R&D stage; it is not worse than the current synthetic engine, and the motion is derived from real audio by construction.
- New screengrab capture — use only the committed video. If additional clips are wanted, that is a separate capture task.
- Changes to `bake_skin.py` — the vis bake is a separate script with a different input domain (video frames vs static skin zip).

**Risks / unknowns**:

1. **Committed video quality**: the spectrum in `Screencast_20260516_060344.webm` may not contain sufficient bar-height variation across its duration (e.g., quiet passage, single genre). If the extracted sequence is monotonous, the loop will still feel synthetic. Mitigation: inspect the extracted atlas visually before committing; capture additional footage if needed.
2. **Flash headroom**: the 60 KB estimate predates any additional features that may have landed. Architect should verify current `firmware.elf` size before committing to atlas size. If headroom is tighter than expected, limit to a single 10-second clip (2.0 KB).
3. **Determinism on different ffmpeg versions**: ffmpeg VP9 decode may produce slightly different pixel values across versions, causing SHA256 mismatch on other machines. The golden hash check should be documented as host-specific or use a committed PNG strip as the canonical source instead of decoding the video at check time.
4. **Loop transition artefact**: a looping atlas may have a visible jump at the wrap point if the last frame's bar heights differ significantly from the first frame. Mitigation: cross-fade or select a wrap point where heights are near the sequence mean.
5. **Mode naming / UX**: inserting a new tap-cycle mode changes the existing VU → Spectrum → Wave → Blank sequence. Architect should decide whether Atlas replaces Spectrum or is inserted as an additional mode.

**Recommended next step**: Hand to Architect for feasibility review of (a) bake pipeline integration and determinism strategy, (b) flash headroom confirmation, (c) mode insertion decision. PM to schedule after Architect sign-off.

**Branch**: `rnd/vis-atlas` (no code exists yet — this proposal precedes implementation)
