### EXP-017 — 2026-07-29 — WebRadio real-vis: peak vs. RMS A/B (EXP-016 follow-up)
**Hypothesis**: EXP-016 flagged pure-peak detection as potentially "jumpy" vs. classic VU ballistics; is a running-RMS envelope (`sqrtf(sum-of-squares / N)`) a straightforward drop-in improvement at the same cost?

**Approach**: Added `WR_VIS_RMS` (only meaningful with `WR_VIS_ENVELOPE`) — same hook, same write target (`vu::lLevelRef()`/`rLevelRef()`), same `ATTACK`/`RELEASE` smoothing, only the per-block target computation changes: `int64_t` sum-of-squares (a full 2048-sample int16 block at full scale overflows a 32-bit accumulator: 2048 × 32768² ≈ 2.2×10¹², need int64) → one `sqrtf` per block instead of a max-scan. New scratch env `cyd2usb_winamp_envelope_rms`. Zero DRAM growth (same as EXP-016).

**Outcome — first pass looked like a regression, wasn't**: the combined screendump+`wrPump` script (`vis_diff_probe.py`) reported `maxPumpMs=272ms` — 6.5× the 42ms baseline, which would trip PROP-005's decode-tail kill gate. Re-measured with the plain `wrPump`-only script (no concurrent screendump traffic) and got **42ms**, identical to both peak and the EXP-015 no-op. Conclusion: the 272ms spike was contention from the screendump run's own retry traffic (WiFi/Serial activity competing with the pump task for CPU time) happening in the same window, not the RMS math — a testing-methodology artifact, not a real cost difference. Documented here so it isn't mistaken for a real finding on a future re-read: **don't measure `wrPump` in the same window as screendump activity** if the number needs to be trustworthy.

Visually: RMS's bars read noticeably shorter/duller than peak's at the same station and volume — expected, since RMS of typical program material sits well below its peak (a 0..1 target computed as raw peak vs. raw RMS on the same signal are not comparable in scale without a compensating gain factor). Pixel-count diff between two RMS screendumps 1.5s apart (451/9800) was in the same order of magnitude as peak's (531/9800) — both are clearly animating, but RMS's un-gained amplitude looks under-driven compared to peak's already-reasonable-looking bars.

**Conclusion**: Inconclusive on "which looks better" as implemented — RMS isn't wired with the makeup gain it would need to be a fair comparison, so this isn't a clean quality verdict either way. Cost is a non-issue: confirmed identical (42ms) to peak once measured cleanly.

**Recommendation**: Don't block graduation on this. Peak (EXP-016) already looks reasonable un-tuned and needs no calibration; ship that. If human testing later finds peak too jumpy, revisit RMS *with* a gain factor (or a peak/RMS blend, closer to real VU ballistics) as a follow-up refinement — not a prerequisite.

**Branch**: rnd/webradio-vis

**Notes**:
- Kill-gate discipline caught what looked like a real decode-tail regression; re-measuring under clean conditions before treating a spike as a verdict is why this rung's methodology (isolate `wrPump` reads from other serial/WiFi traffic) generalizes to any future measurement here.
- `cyd2usb_winamp_envelope_rms` env left in `platformio.ini` alongside the other rung-2 scratch envs.
