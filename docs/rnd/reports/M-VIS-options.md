# R&D Report — M-VIS Visualization Area Options

> Author: R&D Engineer
> Date: 2026-05-16
> Status: final
> Relates-to: TASK-050a/b/c, ADR-002, ADR-009, M-VIS design doc

---

## Background

The vis area is 76×13 px (window-local x=24, y=43), rendered at 20 Hz via TFT_eSPI on the CYD2USB. The device is a Spotify Connect *controller* — no audio PCM is ever decoded on-device. The existing synthetic envelope engine in `vuMeter.h` produces `lLvl`, `rLvl` (0..1), beat phase (120 BPM flat), and an LFO-split stereo signal, all synthesised from `currentlyPlaying` elapsed time.

The Spotify audio-analysis endpoint (`/v1/audio-analysis/{id}`) returns HTTP 403 for this app (post-deprecation Dev Mode app; confirmed TASK-007 DUT run). ADR-009 closed this data source as unavailable. ADR-002 is superseded.

Three options are evaluated below.

---

## Option A — Synthetic Spectrum + Wave (current M-VIS spec)

**What it is**: Two new vis modes layered on top of the existing `vuMeter.h` envelope engine. Spectrum: 38 bars × 2px wide, height driven by `lLvl`/`rLvl` shaped through a static pink-noise rolloff table (`shape[i] = 1 - i/37 × 0.6`), beat transient injected into low bins. Wave: a phase-advancing sine at 20 Hz, amplitude = `lLvl × 5 px`, colour green. Both modes cycle in via a tap on the vis rect (VU → Spectrum → Wave → Blank → VU).

**Authenticity**: Medium. The bar layout, colour scheme (green/yellow/red by height), and peak-dot decay are faithful Winamp 2 reproductions. The *content* of the spectrum is not musically derived — it is a shaped noise envelope. A user looking at it and not concentrating will accept it as a vis. Anyone paying attention will notice the bars never react to beats or tonal content.

**Music reactivity**: Low-synthetic. The beat transient fires at 120 BPM regardless of track; the swell amplitude varies by elapsed time, not audio energy. Bars change shape frame-to-frame because of the noise floor jitter (`MIX_NOISE = 0.18`), which gives surface-level "alive" motion, but there is no track-content coupling at all.

**Implementation complexity**: Low. The design spec in M-VIS-visualization.md is fully detailed: bin synthesis, bar renderer, peak dot state, wave equation, background restore. Three sub-tasks (TASK-050a/b/c) cover the whole scope. No new endpoints, no new hardware, no new data. The existing `vuMeter.h` tick outputs are the only inputs. Estimated effort: 1–2 sessions for an experienced implementer.

**Flash cost**: Negligible. Static `shape[38]` rolloff table = 152 bytes; peak-dot heights `peaks[38]` = 38 bytes; mode enum + tick routing = a few hundred bytes of code. Well within the +1% flash budget constraint from the M-VIS exit criteria (1% of app0 = 25.6 KB).

**RAM cost**: ~40 bytes for the vis state struct (mode enum, phase float, peak heights). No heap allocation.

**Blockers**: None. Deps are TASK-049 (skin background restore pattern, needed for wave erase) and M6 envelope engine — both already shipped.

---

## Option B — Spotify Audio Analysis Segments

**What it is**: Pre-fetch `/v1/audio-analysis/{id}` at track start, cache the `segments[]` array in RAM. Each segment carries: `start` (seconds), `duration`, `loudness_max` (dBFS float), `pitches[12]` (chroma vector, 0..1), `timbre[12]` (MFCC-like coefficients). On each vis tick, binary-search `segments[]` by elapsed ms to find the active segment, map its fields to spectrum bins.

### Sub-question (1): Is the 403 a scope/permission issue fixable without hardware changes?

**Answer: No. The 403 is a confirmed deprecation wall, not a scope or network issue. One long-shot path exists.**

Confirmed in TASK-007 (DUT run 2026-04-29) and closed in TASK-010: both `/v1/audio-features/{id}` and `/v1/audio-analysis/{id}` return HTTP 403. This is not a missing OAuth scope — the endpoint requires no scope beyond `user-read-currently-playing`, which the app already holds. It is an app-tier deprecation enforced by Spotify at the policy level: apps created after approximately late 2024 have no access regardless of scope. App `db2ff394...` was created 2026-04-26, well inside the deprecation window. The TLS connection reaches Spotify cleanly (confirmed: GETs succeed on other endpoints from the same session); the 403 is a deliberate policy response. The only software-only remediation is:

- Apply for Spotify Extended Quota Mode. This restores access to the deprecated endpoints for approved apps. Process: fill the quota request form at developer.spotify.com. Timeline: Spotify's documentation states "a few weeks"; in practice hobbyist submissions are often rejected or sit for months. No guarantees for personal/hobbyist projects. If granted, no firmware change is needed — the existing `makeGetRequest` path in the vendored `SpotifyArduino` can reach the endpoint (confirmed TASK-007: GETs do reach Spotify and return authoritative responses; the 403 is a policy response, not a network or TLS failure).

- Create a new Spotify app registered before the deprecation cutoff. This is not possible for an app created today; the date is baked in at registration.

- Use a proxy or serverless relay that holds a pre-deprecation app's credentials, forwards the analysis fetch, and returns it to the device. This adds an external dependency, a hosting cost, and a credential-management burden — inappropriate for a hobbyist device.

**Verdict**: Extended Quota application is the only viable no-hardware path. It is non-deterministic in timeline and outcome. Do not gate any milestone on it.

### Sub-question (2): What data fields are useful for spectrum synthesis?

If access were granted, the useful fields per segment are:

| Field | Use |
|-------|-----|
| `loudness_max` | Overall bar amplitude for the frame window |
| `pitches[12]` | 12-bin chroma spectrum (C through B); maps cleanly to left third of a 38-bin display with interpolation |
| `timbre[0]` | Loudness redundant with `loudness_max` but useful as a second check |
| `timbre[1]` | Brightness (spectral centroid proxy): high values → tilt energy to upper bins |
| `timbre[2]` | Flatness: high values → flatten shape, low → peaked |
| `beat timestamps` | `beats[].start` gives per-track beat times — replaces the synthetic 120 BPM clock entirely |

`pitches[12]` is the biggest win: it gives real tonal content per segment, enabling bars to react to chord changes. `timbre[1..2]` lets the spectral shape tilt and flatten in a musically meaningful way. The remaining timbre coefficients (3–11) are higher-order and less perceptually meaningful for a 76×13 display.

### Sub-question (3): Memory cost for a 3-minute track

Full parse (loudness_max + pitches[12] + timbre[12] + start + duration), 1200 typical segments for a 3-minute track:
- Per segment: (1 + 12 + 12 + 1 + 1) × 4 bytes = 108 bytes
- Full cache: ~129.6 KB RAM — **not feasible**. Typical free heap at runtime (WiFi + TLS + ArduinoJSON + JPEGDEC) is 80–120 KB; this would exhaust it.

Slim parse (loudness_max + beat-useful timbre[0..2] + start only, 5 floats per segment):
- Per segment: 5 × 4 = 20 bytes
- Slim cache: ~24.0 KB RAM — **feasible** if the heap allows it, but competes with ArduinoJSON's parse buffer (~8–16 KB for a large analysis JSON) and JPEGDEC's decode buffer. Two caveats: (a) the analysis JSON itself is 30–80 KB on the wire; parsing it with `DynamicJsonDocument` requires the JSON string in RAM simultaneously with the output structure, putting peak allocation at ~50–100 KB over baseline; (b) long tracks (5+ min) can have 2000+ segments, pushing the slim cache toward 40 KB.

Beat-only cache (start timestamps only, 4 bytes each, ~600 beats in 3 min):
- 2.4 KB RAM — trivially feasible.

**Practical verdict**: Even the slim variant requires solving a significant JSON parsing problem on a heap-constrained device. The analysis JSON is never small enough to parse with a fixed ArduinoJSON `StaticJsonDocument`; it would require streaming parse with custom extraction, which is a non-trivial implementation.

**Implementation complexity**: High. Requires: (1) Extended Quota access (unblocked only by Spotify policy); (2) a streaming JSON parser for large payloads or a custom HTTP body reader that extracts fields without materialising the full document; (3) a binary search index into the segment array; (4) careful heap management to avoid collision with JPEGDEC during album art decode (track change fires both simultaneously). Estimated effort: 3–6 sessions minimum after unblock.

**Flash cost**: Code-only overhead; no large flash arrays. Probably 2–5 KB of code. Within budget.

**Blockers**: Extended Quota Mode approval — **not on the critical path and non-deterministic**. The entire option is blocked until this clears.

---

## Option C — Pre-baked Animation Atlas

**What it is**: Capture real Winamp 2 vis frames (76×13 px, RGB565) from a desktop Winamp 2 instance playing actual music, bake as a looping sprite sheet stored in flash. On the device, cycle through frames at 20 Hz. Optionally gate frame selection on `lLvl` / beat phase to add minimal reactivity (e.g., scrub forward in the loop on beat transients).

### Sub-question (1): Flash cost for useful loop length at 20fps

Each frame: 76 × 13 × 2 bytes = 1,976 bytes.

| Loop length | Frames | Flash cost | % of 81.9 KB headroom |
|-------------|--------|-----------|------------------------|
| 1 second    | 20     | 38.6 KB   | 47%                    |
| 2 seconds   | 40     | 77.2 KB   | 94%                    |
| 2.1 seconds | 42     | 81.0 KB   | ~99%                   |

**A 2-second loop exhausts nearly all remaining flash headroom** (81.9 KB free as of ADR-009's 96.8% figure; M-IO and M-UI-POLISH shipped since then and will have consumed some of this). A 1-second loop is the absolute maximum that fits with any margin. A 1-second vis loop at 20 fps is perceptually unsatisfying — looping artefacts become noticeable at anything under ~3–4 seconds.

Note: the 96.8% figure dates from before M-IO and M-UI-POLISH completed (both landed 2026-05-16). Actual current headroom is likely smaller — possibly under 60 KB. An atlas of any useful length may already be impossible without further partition changes.

### Sub-question (2): Integration with bake_skin.py pipeline

The existing `bake_skin.py` pipeline extracts static sprite regions from a `.wsz` zip, converts them to RGB565 LE C arrays via Pillow + ImageMagick fallback, and emits `skin_assets.c` + `skin_layout.h`. Extension would require:

1. A separate Python script (or a new `bake_vis.py`) that runs a headless or pre-recorded Winamp 2 instance and captures the 76×13 vis rect at 50ms intervals.
2. The capture frames are converted to RGB565, concatenated into a single array `VIS_ANIM[N_FRAMES][76*13]`, emitted to `gen/skin_assets.c`.
3. `skin_layout.h` gains `VIS_N_FRAMES` and optionally frame metadata (beat-sync point indices).

Headless Winamp 2 capture on Linux is not straightforward — Winamp 2 is a Windows application. Options: Wine + xvfb frame capture, or pre-record on a Windows machine and commit the raw frames. Either way this is host-tooling work that is architecturally separate from `bake_skin.py` (different input domain: live video capture vs. static image extraction from a zip). It could be a sibling script but would not reuse `bake_skin.py`'s internals meaningfully.

The determinism requirement (golden SHA256 check) becomes harder: frame capture is inherently non-deterministic unless input frames are committed as a canonical source (e.g., a PNG strip of 20 frames that the bake script converts, with the PNG itself committed).

### Sub-question (3): Amplitude/beat modulation

With a static atlas, the only reactivity hooks are:

- **Playback gate**: freeze on frame 0 (or last frame) when `!isPlaying`. Already done by the envelope engine.
- **Beat phase scrub**: on beat transient, jump to a beat-sync frame (if the atlas has annotated beat-peak frames). Between beats, advance linearly. This gives a loose "pulsing" that correlates with the synthetic 120 BPM clock — but the pulse is at fixed BPM regardless of track. Not musically accurate.
- **Amplitude scale**: if the atlas was captured with real audio, the encoded brightness already reflects real audio amplitude. Tinting/dimming per `lLvl` is possible but requires pixel-by-pixel multiply, which at 76×13 = 988 pixels is feasible (< 1ms) but adds a per-frame tinting loop.

**Authenticity**: High for the frames themselves — they are real Winamp vis output. Low for the music coupling — the loop repeats identically regardless of what track is playing.

**Music reactivity**: Very low. Worse than Option A in one sense: Option A's spectrum at least changes amplitude plausibly with the beat clock; Option C's atlas plays the same loop for every track regardless of energy or content.

**Implementation complexity**: Medium-high for the capture/bake side; low for the device rendering side (`pushImage` with a frame counter). Total effort: 2–4 sessions. Blocked on Windows/Wine capture tooling setup.

**Flash cost**: Unacceptable at current headroom. Even a 1-second (20-frame) atlas costs 38.6 KB and leaves ~40 KB or less — dangerously thin margin before linker errors. A genuinely loopable 3-second atlas exceeds the entire remaining flash budget by 40%.

---

## Comparison Table

| Criterion | Option A (Synthetic) | Option B (Audio Analysis) | Option C (Baked Atlas) |
|-----------|---------------------|--------------------------|------------------------|
| Authenticity | Medium — correct visual idiom, synthetic data | High — real per-segment tonal/loudness data | High for frames; low for coupling |
| Music reactivity | Low-synthetic — beat at 120 BPM flat, no tonal info | High — per-segment loudness, chroma, beat timestamps | Very low — same loop every track |
| Implementation complexity | Low — fully specced, no new deps | High — blocked, streaming JSON, heap management | Medium-high — capture tooling; device side easy |
| Flash cost | ~200 bytes code + 190 bytes data | ~2–5 KB code | 38.6 KB (1s) to 77.2 KB (2s) — unacceptable |
| RAM cost | ~40 bytes | 9.4 KB (beat-only) to 24 KB (slim) | 3.9 KB (double-buffer 2 frames) |
| Blockers | None | Confirmed deprecation wall (TASK-010); Extended Quota the only path — non-deterministic, hobbyist rejection risk | Flash headroom; Windows capture tooling |

---

## Recommendation

**Implement Option A first.** It is the only option with no blockers, fits within the flash budget constraint, and delivers the correct Winamp 2 visual idiom. The three sub-tasks (TASK-050a/b/c) are already specced in the M-VIS design doc. Shipping Option A unblocks M-VIS and provides a complete user-facing feature: three vis modes (Spectrum, Wave, Blank) cycling on tap, on top of the existing VU mode.

The fact that the spectrum is not music-locked is an honest limitation already accepted project-wide (ADR-009: "this is decoration, not visualisation"). Option A's Spectrum mode is no less honest than the existing VU bars; it is simply a different visual.

**Spike Option B in parallel, non-blocking.** The Extended Quota Mode application should be submitted as a one-time low-effort action (ADR-009 already noted this bias). If granted weeks or months later, the envelope engine's input module can be upgraded to consume `loudness_max` and beat timestamps from the segment cache without touching the renderer — the architecture already anticipates this swap. The streaming JSON parsing problem should be spiked separately to determine whether it is feasible on this heap before committing to it. Do not schedule Option B as a milestone task until: (a) quota is granted, and (b) a heap-budget spike confirms the slim cache fits alongside JPEGDEC's allocation.

**Drop Option C.** The flash cost makes it infeasible at current headroom unless the partition table is restructured again. Even a 1-second loop consumes 47% of remaining headroom, leaving insufficient margin for future features. More fundamentally, a looped atlas is musically decoupled from the track — worse than Option A on the only axis (reactivity) that justifies the complexity and flash spend. The bake pipeline integration is a non-trivial new tooling investment for a strictly inferior result. Option C is not worth revisiting unless the project acquires substantially more flash headroom and resolves the music coupling problem (which would require either audio analysis access or on-device audio, both of which are blocked separately).
