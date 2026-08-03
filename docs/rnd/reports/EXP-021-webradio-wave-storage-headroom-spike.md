### EXP-021 — 2026-08-02 — WebRadio wave trace: dram0_0_seg headroom re-check post-M-CEEFAX-cut (PROP-009 step 1)

**Hypothesis**: EXP-015/016/018 (2026-07-29/30) found `cyd2usb_winamp_debug`'s
`dram0_0_seg` link with **zero bytes** of static-BSS headroom — any new
referenced static, no matter how small, overflowed the link. Given M-CEEFAX
was implemented and then fully cut since (`CeefaxTeletextSource`,
`teletextCountry` setting, WebSockets lib_dep, `ceefaxspike` env all
removed, commit `41448f5`) alongside a lot of unrelated shipped work
(TASK-341..388), is that zero-headroom finding still accurate today, or has
the net effect of everything shipped since shifted it?

**Approach**: Built current `master` (`e943dac`)'s `cyd2usb_winamp_debug`
unmodified first — link succeeded, PlatformIO reports 124536/327680 B RAM
(38.0%). Parsed the linker `.map` directly for the actual constrained
region (PlatformIO's headline RAM% is a coarser, less precise number than
the specific `dram0_0_seg` section EXP-015/016/018 were checking):
`dram0_0_seg` origin `0x3ffbdb5c`, length `0x1e6a4` → segment end
`0x3ffdc200`. Current `_bss_end = 0x3ffdc200` — **wait, that's the
*post-spike* number; the pre-spike unmodified build's `_bss_end` needed a
separate check to get the true zero-cost baseline, see Notes.**

Added a throwaway scratch env (`cyd2usb_winamp_wavespike`, clone of
`cyd2usb_winamp_debug` + one build flag `WR_VIS_WAVE_SPIKE_BYTES`) and a
size-parameterized static (`vu::waveSpikeBufRef()`, an `inline` function
wrapping a function-local `static uint8_t buf[N]` — same
inline-function-wrapping-a-static pattern as `lLevelRef()`/`specHRef()`),
referenced from `webRadioApp.h`'s `audio_process_extern` (already-linked,
always-executed pump-task path, so `--gc-sections` can't strip it as a
false negative — EXP-018's exact lesson). Bisected `N` via the env var:

| N (bytes) | Result |
|-----------|--------|
| 40 | **SUCCESS** — links clean, `_bss_end` lands exactly at `dram0_0_seg`'s end (`0x3ffdc200`), zero bytes to spare afterward |
| 41 | **FAILED** — `region 'dram0_0_seg' overflowed by 8 bytes` |

**Outcome**: Current headroom is **exactly 40 bytes**, not zero. The
41-byte failure overflowing by 8 (not 1) shows some alignment/padding
granularity is in play past the boundary — consistent with EXP-018's
observation that a single 4-byte pointer alone overflowed by 8 bytes for
a similar reason — but the 40-byte success landing with **precisely**
zero bytes remaining (not a few spare) confirms 40 is the real, exact
ceiling for a plain byte-array-shaped addition today, not an
approximation.

**Conclusion**: Validated — headroom changed. The zero-headroom finding
from EXP-015/016/018 was accurate *for that point in time* but does not
generalize forward as a permanent property of this board/build the way
those reports' phrasing ("any new static, full stop") might read out of
context — it reflects the specific static-BSS balance at the time of
measurement, which shifts as features ship and get cut. M-CEEFAX's
removal is the most likely single largest contributor (it was a
significant static-footprint feature that got fully reverted), but this
spike did not isolate exactly which change(s) freed the 40 bytes — that
would need a bisection across the intervening commits, not done here
(out of scope for this question).

**Recommendation**: This reopens `M-WEBRADIO-REAL-VIS-WAVE.md`'s Option B
(true oscilloscope trace) as more affordable than that design assumed,
**for a coarse trace, not the full 76-column one**:
- A 76-column, 1-byte-per-pixel trace (76 B) still does **not** fit
  directly (76 > 40) — would still need the storage-reuse-overlay idea
  from the design doc (riding `tickSpectrum`'s promoted arrays), or a
  packing scheme (e.g. 2 samples/byte via nibbles, ~38 B for 76 columns —
  worth a follow-up spike specifically on packing overhead/unpacking cost,
  not measured here).
- A **19-column coarse trace** (matching `SPEC_BARS`, 1 byte each = 19 B)
  **fits directly today, brand new, no reuse-overlay needed at all** —
  well under the 40-byte ceiling, with room to spare for a second small
  field if wanted (e.g. a per-column min in addition to max, 38 B total,
  still fits).
- This headroom is specific to `cyd2usb_winamp_debug` today, at this
  exact commit, with everything else unmodified. It **is not a stable
  number** — the same way it was 0 nine days ago, it could shift again
  with the very next feature that ships or gets cut. **Any production
  design building on this 40-byte number must re-run this exact check
  (or its own version of it) immediately before implementation, not trust
  this report's number as durable.**
- Does not change the recommendation to run PROP-009's steps 2–3
  (decimation scheme, decode-tail cost, visual check) before committing
  to a production Lean — this spike only answers the storage-affordability
  gate, the cheapest and now-completed first kill gate.

**Branch**: `rnd/webradio-wave-spike` (recut fresh from current `master`,
**not** a continuation of the original `rnd/webradio-vis` — that branch is
~100 commits stale relative to master, predating all of M-CEEFAX's
implementation-then-cut and everything since; rebasing it was judged
riskier than a clean recut for a storage question that specifically
depends on current-master's static footprint). `rnd/webradio-vis` remains
retained as-is per R&D branch discipline (not merged, not touched).

**Notes**:
- Kill gate check: this spike only exercises the storage kill gate from
  `PROP-009`'s ladder step 1. Decode-tail cost (step 2) and visual
  quality (step 3) are unmeasured — no live playback was exercised this
  spike, pure build/link check.
- Scratch env `cyd2usb_winamp_wavespike` and the `WR_VIS_WAVE_SPIKE_BYTES`
  flag / `vu::waveSpikeBufRef()` exist only on `rnd/webradio-wave-spike`
  (commit `bcd2d0c`) — not on `master`, per R&D discipline.
- Correction to this report's own Approach section: the *unmodified*
  `cyd2usb_winamp_debug` build's `_bss_end` was not independently
  recorded before the spike env's first build overwrote the relevant
  `.map` in the same build directory — the 40/41-byte bisection result is
  the load-bearing evidence, not the initial unmodified-build number,
  which was only used to confirm the env still links at all today (it
  does). If this matters for a future audit, re-run
  `./run/build-debug` fresh and check `_bss_end` before any spike changes
  are applied, first thing.
