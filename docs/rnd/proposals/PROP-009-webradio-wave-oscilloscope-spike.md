# PROP-009 — True oscilloscope waveform trace from the WebRadio audio stream

> Owner: R&D Engineer
> Status: **VALIDATED 2026-08-02, for the 19-column variant — all three
> kill gates cleared (EXP-021 storage, EXP-022 decode-tail + visual).
> Recommended for graduation.** The 76-column full-resolution variant
> remains unproven — see EXP-022's Recommendation.
> Branch: `rnd/webradio-wave-spike` (recut fresh from current `master`
> 2026-08-02 — the originally-declared `rnd/webradio-vis` was ~100 commits
> stale, predating M-CEEFAX's implement-then-cut arc and everything since;
> see EXP-021 for why a fresh recut was judged safer than rebasing for a
> storage question that specifically depends on current-master's static
> footprint. Per AGENTS.md, R&D never merges to main directly.)
> Origin: `M-WEBRADIO-REAL-VIS-WAVE.md` (Architect design, Option B) — filed
> because that design explicitly declined to make a production Lean for a
> true waveform trace without a cheap-kill-first spike first

## Premise

`M-WEBRADIO-REAL-VIS-WAVE.md` distinguishes two different things "real
audio-driven wave" could mean: (A) real amplitude scaling a still-synthetic
sine (cheap, same mechanism as the already-shipped VU envelope — that
half is a small production design, not R&D) and (B) an actual oscilloscope
trace of real decoded sample values. This proposal is (B) only.

Unlike PROP-005's rungs 2–3 (real VU envelope, real spectrum bands), a
waveform trace has no existing same-shaped storage to reuse: rung 2 reused
`lLevelRef()`/`rLevelRef()`, rung 3 reused `tickSpectrum`'s own five arrays.
There is no dormant per-column sample buffer sitting around to swap into.
EXP-018 found that on this board's `SERIAL_DEBUG`-enabled link *as of
2026-07-29/30*, even one new 4-byte static pointer, alone, overflowed. **That
specific number is stale** — EXP-021 (2026-08-02, this proposal's step 1)
re-measured on current `master` and found **exactly 40 bytes** of headroom
today, almost certainly because M-CEEFAX shipped and was then fully cut in
the interim, net-freeing static state. 40 bytes does not fit a full 76-byte
(1-byte-per-pixel-column) trace, but does fit a coarser 19-column trace
(matching `SPEC_BARS`) directly, no reuse-overlay needed. See EXP-021 for
the exact bisection and the explicit warning that this number is a snapshot,
not a stable property of the board — it must be re-checked immediately
before any production implementation, not trusted as durable.

## Question to answer

Can a real per-tick waveform trace (one representative sample value per
horizontal pixel column, 76 columns) be captured from the WebRadio decode
path and handed to the UI thread — within the same zero-static-BSS-headroom
constraint every prior rung had to solve, and without regressing the
TASK-278 decode-tail budget (still 42 ms across every rung measured so
far) — at a quality that reads as an actual waveform (not just louder/
quieter) rather than the amplitude-only fake sine Option A already covers
cheaply?

## Suggested ladder (cheap-kill-first, LL-087 — same discipline PROP-005 used)

1. ~~Storage-reuse spike~~ **DONE 2026-08-02 (EXP-021).** Direct
   measurement (bisected new-static size against current `master`'s
   `cyd2usb_winamp_debug` link) beat the originally-planned reuse-overlay
   approach to the answer: current headroom is exactly 40 bytes, not zero.
   Verdict per candidate:
   - **A 19-column coarse trace (1 byte/column, matching `SPEC_BARS`) fits
     directly today — 19 B, no reuse-overlay needed at all.** This is the
     cheapest path forward and doesn't require promoting `tickSpectrum`'s
     arrays or coupling Wave's storage to Spectrum's (TASK-387) landing
     first.
   - A full 76-column, 1-byte-per-pixel trace does **not** fit directly
     (76 B > 40 B). Two remaining options if full resolution is wanted:
     reuse-overlay onto `tickSpectrum`'s promoted arrays (original plan
     (a)/(b) below, now only needed for this higher-fidelity variant), or
     a packing scheme (~2 samples/byte, ~38 B for 76 columns — cost of
     packing/unpacking on the pump task not yet measured, a candidate for
     step 2's cost check if this variant is wanted).
   - Original reuse candidates, still valid for the 76-column variant only:
     (a) `tickSpectrum`'s now-promoted `specPeak`/`specH`/`specVel`
     namespace-scope arrays (`vu::specHRef()` etc., from EXP-018/rung 3,
     not yet on `master` — TASK-387 lands them) — valid only if Wave and
     Spectrum modes are mutually exclusive at any given tick, which they
     are (`VisMode` is a single active enum value); (b) riding `SPEC_BARS`'
     19-wide granularity visually blown up — this is now just the direct
     19-byte-new-static path above, made moot as a *reuse* question since
     it fits as new storage on its own.
2. ~~Decimation + cost measurement~~ **DONE 2026-08-02 (EXP-022).** Plain
   sub-sampling (`idx = i*len/19`), not the min/max-envelope alternative —
   worked well enough on real content that the A/B wasn't run this
   session (same "worth a quick A/B, not a blocker" framing EXP-016 used
   for peak-vs-RMS). `maxPumpMs=44` vs. the 42ms baseline every prior rung
   measured — within noise, not a regression.
3. ~~Visual check~~ **DONE 2026-08-02 (EXP-022).** Two screendumps 1.5s
   apart during live playback (an NPO news/talk station) showed 205/9800
   changed pixels **and**, more importantly, materially different *shapes*
   between frames (jagged during speech, flat during a pause) — the
   specific property Option A's amplitude-only sine cannot produce.

## Kill gates

- ~~No storage-reuse angle fits without a new static~~ **Cleared for the
  19-column variant** (EXP-021: 19 B fits directly within the 40 B
  measured headroom). Still a live gate for the 76-column variant only,
  if that's the one pursued — re-check headroom fresh at implementation
  time regardless (EXP-021's number is a snapshot, not durable).
- ~~Decode-tail p95 regresses vs. the TASK-278/42ms baseline~~ **Cleared**
  (EXP-022: 44ms, within noise).
- ~~Visible improvement over Option A's amplitude-only sine is marginal~~
  **Cleared** (EXP-022: shape-reactive to real content, not just
  amplitude-reactive — the actual bar Option A doesn't clear).

## Deliverables

EXP reports under `docs/rnd/reports/`: `EXP-021` (storage), `EXP-022`
(decode-tail + visual). **Graduation recommended** — see EXP-022's
Recommendation for the open scope question (replace TASK-388's Option A,
or ship as a third mode alongside it) that Architect/PM should resolve;
production integration is NOT part of this activity, matching every prior
PROP-005 rung's handoff discipline.

## DUT dependency (resolved 2026-08-02)

Correction to this proposal's original framing: step 1 (storage) needed
**no live device at all** — a host cross-compile/link reproduces
`dram0_0_seg`'s exact link behavior. Steps 2–3 did need the DUT and both
ran this session (EXP-022) — decode-tail measured, visual check performed
against live WebRadio playback. Nothing further blocked on hardware for
the 19-column variant; the 76-column variant remains unexplored.
