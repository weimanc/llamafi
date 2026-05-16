# R&D Report — M-VIS Animation Improvements

> Author: R&D Engineer
> Date: 2026-05-16
> Status: draft
> Relates-to: TASK-050a/b/c, ADR-009, M-VIS-options.md, M-VIS-video-analysis-method.md, M-VIS-spectrum-analysis.md

---

## Background

M-VIS (TASK-050a/b/c) has shipped. The visualizer delivers four tap-cycling modes: VU, Spectrum, Wave, Blank. The spectrum renderer produces 19 bars × 16 levels at 20 Hz, driven entirely by a synthetic envelope (`lLvl`, `rLvl`, beat clock, and noise floor jitter). User feedback: the animation is visibly synthetic — bars move predictably and do not react to actual musical content.

Prior R&D (`M-VIS-options.md`) evaluated three options:

- **Option A** (synthetic envelope) — shipped. Correct visual idiom, no audio coupling.
- **Option B** (Spotify audio analysis) — blocked by HTTP 403 deprecation wall (ADR-009). Extended Quota Mode is the only viable path; non-deterministic.
- **Option C** (pre-baked RGB565 atlas) — rejected. Flash cost: 38.6 KB/second at 20 fps; available headroom ~60 KB or less; a loopable sequence of useful length is infeasible.

This report investigates four directions for improving the shipped animation, assessing feasibility within current resource constraints, and recommends what to pursue next.

---

## Resource envelope (post M-VIS, M-IO, M-UI-POLISH)

| Resource | Budget |
|---|---|
| Flash | ~60 KB remaining |
| RAM free heap | 80–120 KB (WiFi + TLS + ArduinoJSON + JPEGDEC compete) |
| CPU per vis tick | < 50 ms at 20 Hz (shared with Spotify poll + JPEGDEC) |
| Available inputs | `lLvl`, `rLvl` (0..1), beat phase (120 BPM), elapsed ms, `is_playing`, `track.name`, `track.duration_ms` |
| Vis geometry | 19 bars × 16 levels; 4 bits per bar height |

---

## Q1 — Compressed bar-height atlas from video analysis

### Concept

Option C was rejected for storing full RGB565 frames (76 × 16 × 2 = 2,432 bytes/frame). Bar heights are far smaller. Each frame needs only 19 × 4 bits = 9.5 bytes, which rounds to 10 bytes with alignment (or 12 if byte-per-bar rather than 4-bit packed).

The video analysis pipeline (`M-VIS-video-analysis-method.md`) has already extracted the visual geometry, colour gradient, and decay rate from real Winamp 2 screengrab video. Bar heights per frame have not yet been extracted but the pipeline supports it: per-column pixel scanning already isolates bar vs background.

### Flash cost at 20 fps

Using 10 bytes/frame (4-bit packed, two bars per byte):

| Loop length | Frames | Flash cost | % of ~60 KB headroom |
|---|---|---|---|
| 1 second | 20 | 200 B | 0.3% |
| 10 seconds | 200 | 2.0 KB | 3.3% |
| 30 seconds | 600 | 6.0 KB | 10% |
| 60 seconds | 1,200 | 12.0 KB | 20% |

Using 19 bytes/frame (byte-per-bar, no packing):

| Loop length | Frames | Flash cost | % of ~60 KB headroom |
|---|---|---|---|
| 10 seconds | 200 | 3.8 KB | 6.3% |
| 30 seconds | 600 | 11.4 KB | 19% |
| 60 seconds | 1,200 | 22.8 KB | 38% |

**Finding**: the compressed bar-height atlas is fiscally viable within flash budget. Even a 60-second byte-per-bar atlas at 38% headroom leaves margin. The rejection of Option C in `M-VIS-options.md` was correct for RGB565 frames but does not apply to height-only representations — the per-frame size drops by a factor of ~250.

### Perceptual loop threshold

A 19-bar spectrum is a relatively coarse display. Loop-repeat perception depends on the period and the distinctiveness of the sequence. General psychoacoustic / visual literature places the repeat-detection threshold for rhythmically regular loops around 2–4 seconds for attentive listeners; for a decorative background animation with no explicit rhythm cues, 8–12 seconds is plausibly below the detection threshold for casual observation. Given the numbers above, a 10-second atlas (200 frames, 2.0 KB) is well within flash budget and likely below the casual-viewing detection threshold. A 30-second atlas (6.0 KB) is very comfortable and almost certainly imperceptible as looping.

### Pipeline extension difficulty

The existing `M-VIS-video-analysis-method.md` Step 4 method scans horizontal rows to find bar vs background pixels. Extracting bar heights requires a vertical scan per bar column per frame — a straightforward extension:

1. For each frame, for each of the 19 bars, scan the bar's column in the vis area from top to bottom; count non-background pixels. This is the bar height in skin pixels (0–16).
2. Emit as a C array: `const uint8_t VIS_ATLAS[N_FRAMES][19]` (byte-per-bar) or 4-bit packed.

The pipeline already handles frame extraction (`ffmpeg`), vis area calibration, and background pixel classification. Estimated extension: one additional Python function (~40 lines), producing a ready-to-embed C array. Determinism: input is a committed video file; output is deterministic given fixed ffmpeg decode. SHA256 golden check is straightforward.

### Multiple clips by energy tier

Multiple short atlases could be stored and selected by current energy level (`lLvl`):

- Clip A: "high energy" (loud, fast-moving bars) — activated when `lLvl > 0.65`
- Clip B: "medium energy" — activated when `0.35 < lLvl <= 0.65`
- Clip C: "quiet" — activated when `lLvl <= 0.35`

With 10-second clips at 2.0 KB each (4-bit packed), three clips = 6.0 KB total — comfortably within budget. Switching clips on an energy threshold creates a crude but real coupling between the animation and playback intensity. Transitions between clips need a brief cross-fade or cut-on-boundary strategy to avoid jarring jumps.

### Device-side rendering cost

Current `tickSpectrum` per-tick cost: 19 bar height computations (floating-point multiply, shape lookup, clamp, peak tracking), then 19 × up-to-16 drawFastHLine calls. The floating-point synthesis contributes a small fraction of the total; the dominant cost is the SPI pixel writes.

With an atlas: per-tick cost is a single array index (frame counter mod N_FRAMES), no float arithmetic, same SPI writes. CPU cost decreases slightly; the rendering pipeline (blitVisBackground + drawFastHLine per bar row) is unchanged. No regression risk.

### Q1 verdict

**Feasible and attractive.** A 10–30 second bar-height atlas from real Winamp vis footage fits easily within flash budget, requires modest pipeline extension, and delivers authentic-looking Winamp motion at zero ongoing CPU cost. Music coupling is weak (same loop every track) but the atlas content is derived from real audio — bar motion has natural spectral shape, decay rate, and attack behaviour by construction. This is a fundamentally different and superior approach to the Option C rejection: storing heights rather than pixels makes the representation ~250× smaller.

---

## Q2 — Statistical / parametric model derived from video

### Concept

Rather than storing raw frames, analyse real Winamp vis footage to extract statistical properties of bar motion, then build a compact parametric generator that approximates those statistics. The generator runs on-device, producing synthetic bars with the statistical fingerprint of real Winamp output.

### Properties measurable from existing footage

From `M-VIS-spectrum-analysis.md` and `M-VIS-video-analysis-method.md`, the following can be extracted:

- **Per-bar amplitude distribution**: mean and variance of bar height per column over the recording, derivable from the same vertical scan proposed in Q1.
- **Inter-bar correlation**: adjacent bars tend to move together (spectral correlation in audio). Pearson correlation matrix of bar heights across frames — or simply a smoothing kernel applied to heights.
- **Decay rate**: measured at ~3–4 skin px/frame at 60 Hz. At 20 Hz (our tick rate) this is ~10–13 px/frame, meaning peak dots fall ~0.6–0.8 of the vis height per second. The current implementation already models this (`specPeak[i] -= 1.0f / VIS_H` per tick, equivalent to 16 ticks to full decay = 0.8 s).
- **Attack vs decay asymmetry**: visual inspection confirms Winamp bars rise fast (one frame to target) and decay slowly (peak dot visible for many frames). The current implementation uses `ATTACK = 0.45f`, `RELEASE = 0.10f` — this asymmetry is already modelled.
- **Beat transient shape**: sharp rise followed by exponential-like decay over ~100–200 ms. The current `BEAT_DECAY_MS = 80` captures this shape roughly but fires at a fixed synthetic BPM.

### Simplest model capturing "alive" feel

The minimum viable parametric model is an **AR(1) process per bar** with shared spectral shape and inter-bar smoothing:

```
h[i][t] = alpha * h[i][t-1] + (1 - alpha) * (target[t] * shape[i] + noise[i][t])
```

where `shape[i]` is the pink-noise rolloff (already in `tickSpectrum`), `alpha` is the per-bar inertia coefficient (~0.6–0.8), and `noise[i][t]` is a small per-bar perturbation. Inter-bar correlation is imposed by spatially smoothing `noise[i][t]` with a 3-tap kernel before applying it.

This is structurally similar to what Option A already does (lLvl → shape → noise → bar height). The difference would be:

1. Replacing uniform random noise with correlated per-bar noise (a 3-float kernel applied to an array of 19 random values per tick).
2. Adding an inertia term so bars don't jump to target in one tick — they converge over 2–3 ticks, producing natural overshoot at beat transients.

### Parameter size

A full parametric model for 19 bars:

| Parameter | Size |
|---|---|
| Spectral shape `shape[19]` | 19 × 4 = 76 bytes (float) or 19 bytes (uint8 scaled) |
| Inertia coefficient `alpha[19]` | Same — 19 bytes |
| Noise kernel (3 taps, shared) | 12 bytes |
| Beat transient shape (5-point envelope) | 20 bytes |
| Total | ~70–130 bytes |

Well within the 200-byte target. If shape and alpha are encoded as uint8 (0–255 scaled to 0.0–1.0), the table is ~60 bytes.

### CPU cost per tick at 20 Hz on ESP32

ESP32 has an FPU; single-precision float operations are hardware-accelerated. Per-tick operations for 19 bars with the AR(1) model:

- 19 random() calls (fast; ~50 ns each on ESP32)
- 3-tap spatial convolution: 19 × 3 multiplies + adds = 57 float ops
- 19 AR(1) updates: 19 × 2 float ops
- 19 bar height computations: same as current

Total: ~100–150 float operations vs current ~40. At the ESP32 FPU rate (~200 MFLOPS single-precision), this adds ~0.5–1 µs per tick. Negligible. The bottleneck remains SPI writes.

### Would it look better than current Option A?

The primary visual complaint is that bars evolve together (no inter-bar variation) and jump predictably with the beat clock. The AR(1) model with per-bar correlated noise would add:

- Independent slow drift per bar (each bar has its own state, not just a scaled copy of `envelope`)
- Natural settle time after beat transients (inertia)
- Spatial variation: adjacent bars correlated but not identical

This would look meaningfully more organic. However, it is still entirely synthetic — the motion is not derived from actual audio content. An attentive listener would still notice no coupling to musical events (chord changes, drops, verses).

### Q2 verdict

**Moderate improvement, small cost.** A parametric AR(1) model with inter-bar correlation adds ~60–130 bytes of flash (parameter tables) and negligible CPU overhead. It is the simplest route to less robotic-looking motion without requiring video analysis or external data. Implementation is an extension to `tickSpectrum` in `vuMeter.h`, requiring no new files or infrastructure. The improvement is real but bounded: it addresses the "bars all move together" symptom, not the "no musical coupling" root cause.

---

## Q3 — Improved synthetic algorithms (no video dependency)

Evaluating five candidate improvements to the current Option A synthetic engine:

### 3a — Perlin / fractal noise instead of uniform noise

**What**: Replace `random(0, 1000) / 1000.0f * MIX_NOISE` with value noise or a simple 1D Perlin-like function that evolves slowly over time. Each call returns a value that changes smoothly rather than jumping to a new random value each tick.

**Flash cost**: A minimal value noise implementation (two-point linear interpolation between random seeds, advancing phase at ~0.05 Hz) = ~100–200 bytes of code. No data tables needed.

**RAM cost**: 2 float seeds per bar = 19 × 2 × 4 = 152 bytes, or 2 global floats if the same noise is applied to all bars. Negligible.

**CPU cost**: 1 lerp per bar per tick vs 1 random() call. On ESP32, linear interpolation in float is slightly faster than `random()`. No regression.

**Visual impact**: **Medium**. Uniform noise produces visible jitter — bar heights flicker frame-to-frame with visible period of ~50 ms. Slowly-evolving noise produces gentle drift that reads as organic. The difference is more noticeable on close inspection than at a glance. The "all bars move together" problem is not addressed — the noise is applied as a global scalar to the envelope before per-bar shape scaling.

### 3b — Multiple BPM oscillators

**What**: Replace the single 120 BPM beat clock with two overlapping oscillators, e.g., one at 96 BPM and one at 148 BPM (ratio ~1:1.54, close to 2:3). The combined output has irregular beat timing that does not obviously repeat within 10–15 seconds.

**Flash cost**: ~20–40 bytes of code. Two `beatPhase` computations, two decay envelopes, mixed at a fixed ratio.

**RAM cost**: 0 (two additional `long` values for phase counters, stackable).

**CPU cost**: 2 modulo operations per tick instead of 1. Negligible.

**Visual impact**: **Medium-High**. The current 500ms flat-period beat clock is the most detectable synthetic artifact. Irregular beat timing removes the most obvious regularity. A user who taps along to the beat will find no consistent period. Combined with any of the other improvements, this is disproportionately high value for very low cost.

**Risk**: If the actual track's BPM happens to align with one of the two oscillators, the synthetic beat may occasionally coincide with the real beat — which looks good. If it's far off both, it looks no worse than the current 120 BPM misalignment. No regression possible.

### 3c — Per-bar momentum / inertia

**What**: Bars don't jump to target height — each bar has a velocity term. Target height is a spring-like attractor; bars overshoot and settle.

```
vel[i] = 0.7 * vel[i] + 0.3 * (target_h[i] - h[i])
h[i] += vel[i]
```

The spring constant (0.3) and damping (0.7) control overshoot and settle time. Tuned for a slight overshoot on beat transients with 2–3 tick settle.

**Flash cost**: ~80 bytes of code. Replaces the current direct bar height assignment in `tickSpectrum`.

**RAM cost**: 19 float velocity values = 76 bytes. Modest; does not threaten heap.

**CPU cost**: 19 × 2 float multiply-adds per tick. Negligible on FPU.

**Visual impact**: **High**. Overshoot and settle is the most visible organic characteristic of physical visualizers. Current bars jump from one height to another with a step function — clearly digital. With inertia, bars bob through their targets and settle naturally, especially on beat transients. This is the single change with the largest perceptual improvement relative to implementation cost. The "alive" feel cited as missing by users is largely produced by this kind of physical simulation.

**Interaction with peak decay**: the existing `specPeak` tracking records the bar's maximum height; inertia doesn't change the peak's identity (still the max the bar reached), only the approach. Compatible without modification.

### 3d — Stereo spread with phase offset

**What**: The left half of the spectrum (bars 0–8) is driven primarily by `lLvl`; the right half (bars 10–18) primarily by `rLvl`, with a slight phase offset between the two sides. Currently the LFO split partially achieves this: `lLvl` and `rLvl` diverge by ±15% based on a 700ms LFO.

**What's missing**: the phase of the LFO split means the left and right sides of the spectrum peak at different moments — a correct observation. But bars are still all driven from the same monophonic `envelope = (lLvl + rLvl) * 0.5`. Extending this: map bar i to a blend `lerp(lLvl, rLvl, i/18.0)` so bars 0–18 continuously sweep from left to right channel. Add a fixed 2–4 tick phase offset so the right side of the spectrum reacts slightly later than the left.

**Flash cost**: ~50 bytes of code. Replace `envelope` with a per-bar lerp in `tickSpectrum`.

**RAM cost**: 0.

**CPU cost**: 19 lerp operations. Negligible.

**Visual impact**: **Low-Medium**. The stereo information in `lLvl` vs `rLvl` is already a synthetic signal (LFO, not real audio), so the spread remains artificial. However, the visual effect of the two sides moving slightly independently and with a phase delay reads as more complex and less uniform. Combined with inertia (3c), the spectrum looks considerably less like a single bar scaled 19 times.

### 3e — Spectral tilt modulation

**What**: Slowly shift where the energy peaks in the spectrum (low vs mid vs high) over time, driven by an LFO at 0.05–0.1 Hz (~10–20 second period). The existing `shape[i] = 1 - i/18 * 0.6` is a fixed pink-noise rolloff (always peaks at bar 0). Modulating the tilt makes the energy centre of mass drift slowly across the bar array:

```
tilt_offset = sin(elapsed / 12000.0) * 4.0    // ±4 bars over ~12 s period
shape[i] = 1 - clamp(i - tilt_offset, 0, 18) / 18.0 * 0.6
```

**Flash cost**: ~40 bytes of code. One `sinf()` call per tick (shared with existing swell calculation).

**RAM cost**: 0.

**CPU cost**: One `sinf()` per tick (same as existing swell `sinf`). Negligible.

**Visual impact**: **Medium**. The static pink-noise rolloff means bars 0–3 are always the tallest. Over a typical track, this reads as predictable. Slow tilt variation creates the impression that different frequency regions are active at different moments — mimicking the real behaviour of a spectrum analyzer responding to music with varying spectral content (verse vs chorus, quiet vs loud sections). The effect is slow enough not to call attention to itself.

### Q3 summary table

| Candidate | Flash (bytes) | RAM (bytes) | CPU | Visual impact vs Option A |
|---|---|---|---|---|
| 3a — Perlin/fractal noise | ~150 code | ~40 | Neutral | Medium |
| 3b — Multiple BPM oscillators | ~40 code | ~0 | Negligible | Medium-High |
| 3c — Per-bar inertia | ~80 code | 76 (static array) | Negligible | **High** |
| 3d — Stereo spread | ~50 code | 0 | Negligible | Low-Medium |
| 3e — Spectral tilt modulation | ~40 code | 0 | Negligible | Medium |

All five are combinable. Combined flash cost: ~360 bytes code + 76 bytes data = ~440 bytes. Under 1 KB total. RAM: 76 bytes (velocity array). Neither threatens the resource envelope.

---

## Q4 — BPM / energy hint from available Spotify metadata

The `currently-playing` endpoint is accessible and returns `item.duration_ms`, `item.name`, `item.artists[].name`, `item.album.name`. Audio features (BPM, energy, danceability) are 403-blocked (ADR-009).

### Candidates evaluated

**Genre lookup from artist name (hardcoded table)**

A `const char*` lookup table mapping well-known artist names to energy tier (low/high) could be stored in flash. A 50-entry table with average 15-character artist names + 1 enum byte = ~800 bytes flash. Coverage would be sparse and obviously wrong for any artist not in the table. Maintenance burden is high (table stales immediately). **Verdict: not worth it**. The classification errors would be jarring (a classical artist the table doesn't know gets treated as high-energy), and the improvement in animation quality for the hits is marginal.

**`duration_ms` as energy proxy**

The hypothesis: shorter tracks tend to be more energetic (pop singles, club edits). The data does not support this strongly. Classical pieces are long but low-energy; metal songs are often under 3 minutes but high-energy; jazz ballads vary widely. Duration has essentially no predictive power for energy on a per-track basis. **Verdict: not useful**.

**Track name keyword scan**

Keywords that might indicate low energy: "acoustic", "piano", "instrumental", "lullaby", "ambient", "slow", "ballad". Keywords for high energy: "remix", "dance", "club", "edit", "extended", "live", "feat.". A scan for these strings in `track.name` is ~10–20 case-insensitive `strstr` calls per track change (not per tick) — negligible cost. Flash: ~300 bytes for the keyword strings.

Coverage: low. Most track names don't contain these keywords. For the subset of tracks that do contain them, the signal is moderately reliable (an "acoustic version" is genuinely lower energy than the original; a "club remix" is genuinely higher energy). **Verdict: worthwhile as a low-cost additive signal**, but should not be the sole driver of BPM or energy. Weight it as a secondary hint.

Suggested implementation: on track change, scan `track.name` for energy keywords; set a 3-tier energy hint (LOW/MID/HIGH, default MID). Use to modulate `MIX_BEAT` (high energy → stronger beat transient) and BPM oscillator frequency (high energy → shift oscillators up 10–15 BPM; low → shift down).

**Better fixed BPM**

The current 120 BPM flat clock is a reasonable pop-genre median. Analysis of global streaming data suggests 120 BPM is close to the median BPM for popular music. However:

- 96 BPM is a common hip-hop / R&B / soul BPM.
- 128 BPM is the house/electronic standard.
- Using two oscillators at ~100 and ~152 BPM (3:2 ratio) gives beats at roughly 50, 75, 100, 125, 150, 200 ms intervals — covering a wide range with two periods.

**Verdict**: switching from one 120 BPM clock to two oscillators at ~100 and ~152 BPM (as proposed in 3b) is better than any fixed single BPM. The change requires no metadata. Combined with keyword-triggered energy hints for `MIX_BEAT` scaling, the result is a coarse but real improvement.

**Summary for Q4**: the only viable metadata signal is track-name keyword scanning for energy tier. All other metadata proxies (duration, artist name table) have insufficient predictive power to justify the implementation. The keyword scan is cheap (~300 bytes flash, O(n) per track change) and provides a meaningful signal for a relevant subset of tracks.

---

## Recommendation table

Ranked by (authenticity gain) / (implementation cost + resource cost):

| Option | Authenticity gain | Implementation cost | Resource cost | Recommended? |
|---|---|---|---|---|
| **3c — Per-bar inertia** | High | Low (80 bytes code, extend tickSpectrum) | 76 bytes RAM | **Yes, first** |
| **3b — Multiple BPM oscillators** | Medium-High | Very low (40 bytes code) | 0 | **Yes, with 3c** |
| **3e — Spectral tilt modulation** | Medium | Very low (40 bytes code) | 0 | **Yes, bundle with above** |
| **Q1 — Bar-height atlas** | High (authentic motion) | Medium (pipeline extension + 10–30 KB flash) | 10–30 KB flash | Yes, after Q3 bundle ships |
| **3a — Perlin noise** | Medium | Low (150 bytes code) | ~40 bytes RAM | Optional, bundle with Q3 |
| **3d — Stereo spread** | Low-Medium | Low (50 bytes code) | 0 | Optional, bundle with Q3 |
| **Q4 — Keyword energy hint** | Low-Medium | Low (300 bytes flash, O(n) per track) | 0 | Optional additive, bundle |
| **Q2 — AR(1) parametric model** | Medium | Low-Medium (130 bytes tables + rework) | ~150 bytes RAM | Subsumed by 3c + 3d |
| **Option B — audio analysis** | Very high | High + blocked (ADR-009) | Heap budget risk | No — blocked |

---

## Conclusions

### Immediate recommendation: Q3 synthetic improvements bundle

Implement 3b + 3c + 3e as a single commit to `vuMeter.h`:

- **3c (inertia)**: add a `static float vel[SPEC_BARS]` velocity array; replace the direct bar height assignment with a spring-damper update. This is the largest single improvement in perceptual quality. Estimated implementation: ~30 minutes.
- **3b (multiple oscillators)**: add a second `beatPhase` at a different period (e.g., `BEAT_PERIOD_B_MS = 392` for ~152 BPM); blend the two transients at a fixed ratio (0.6 / 0.4). No new state needed beyond a second period constant. Estimated implementation: ~10 minutes.
- **3e (spectral tilt)**: add a slow `sinf(elapsed / 14000.0)` term that shifts the rolloff shape's peak by ±3 bars over ~14 s. Shares the existing `sinf` from the swell calculation. Estimated implementation: ~10 minutes.

Combined flash: ~160 bytes code + 76 bytes data. Combined RAM: 76 bytes static array. Well within all resource constraints. No new files, no infrastructure change, no pipeline work.

### Secondary recommendation: Q1 bar-height atlas

After the Q3 bundle ships, implement the bar-height atlas as a follow-on feature:

1. Extend the video analysis pipeline (`M-VIS-video-analysis-method.md`) to emit `VIS_ATLAS[N_FRAMES][19]` from the existing screencast video. Aim for a 30-second atlas (600 frames, 6.0 KB at 4-bit packed or 11.4 KB byte-per-bar).
2. Add a new `VIS_ATLAS_PLAYBACK` mode to `vuMeter.h` that indexes into the atlas at the current frame counter, applying a simple energy-gated playback rate (pause on `!is_playing`; advance at 1 fps equivalent when very quiet; normal rate when playing).
3. Optionally add a second energy-tier clip to the atlas if flash permits after measuring the actual pipeline output size.

This delivers authentic Winamp motion — bar shapes, decay rates, and spectral behaviour derived from real audio — without requiring Spotify audio analysis access. The improvement over Q3 is real: even with perfect synthetic parameters, a parametric model cannot reproduce the specific temporal texture of actual music. An atlas from real footage captures that texture by construction.

### Do not pursue now

- **Q2 (AR(1) parametric model)**: the gains are subsumed by Q3's inertia and correlation improvements. Not worth separate implementation.
- **Q4 keyword scanning**: implement only as part of a broader metadata enrichment pass if other use cases (e.g., display formatting) also benefit. Not worth the complexity for vis animation alone.
- **Option B**: blocked. No change since ADR-009.

### Should a PROP be written?

Yes — one PROP is warranted, scoped to the Q1 bar-height atlas. The Q3 synthetic improvements are small enough (sub-200 bytes, no infrastructure change, single-file edit) that they can be implemented directly as a maintenance commit without PM scheduling. The atlas work involves pipeline changes, a new data asset committed to the repo, and a new vis mode — appropriate scope for a PROP to let PM schedule and prioritise against other open work.

Proposed PROP title: `PROP-002 — Bar-height atlas from real Winamp vis footage`. Architect review of the pipeline extension (determinism, golden hash, bake tooling integration) should happen before PM schedules it, per inter-agent protocol.
