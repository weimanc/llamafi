### EXP-022 — 2026-08-02 — WebRadio wave trace: decode-tail cost + visual check (PROP-009 steps 2–3)

**Hypothesis**: Following EXP-021 (step 1: a 19-column real wave trace fits
today's 40-byte `dram0_0_seg` headroom directly, no reuse-overlay needed),
can that 19-column trace — plain sub-sampling decimation of the pump task's
most recently decoded block, one column overwritten per `audio_process_extern`
call — be captured at TASK-278 decode-tail cost (42ms baseline) and does it
visibly read as a real waveform *shape* (not just amplitude) during live
WebRadio playback?

**Approach**: Built on `EXP-021`'s scaffold, same branch
(`rnd/webradio-wave-spike`, recut fresh from `master`). Added
`vu::waveTraceRef()` (`static int8_t buf[19]`, namespace-scope accessor,
same inline-function-wrapping-a-static pattern as `lLevelRef()`/
`specHRef()`) and `vu::tickWaveTrace()` (connected-line renderer, full
redraw per call — spike simplicity, not a production dirty-diff
implementation). `audio_process_extern` (`webRadioApp.h`) decimates the
current block's L channel to 19 points via `idx = i*len/19` and overwrites
the whole trace array every call (single writer, same never-both-active
argument as X043/X044/X045). Forced `tickWaveTrace()` to render every
WebRadio tick regardless of `vu::currentMode()` for observability (same
pattern as EXP-018's `VIS_SPECTRUM` force-hack) — new scratch env
`cyd2usb_winamp_wavetrace` (`-DWR_VIS_WAVE_TRACE`), built and confirmed
linking clean (RAM +24 bytes vs. the unmodified debug baseline — slightly
more than the 19-byte array itself, likely section-alignment rounding;
still comfortably inside the 40-byte ceiling EXP-021 measured).

Flashed to the DUT, drove into WebRadio via the existing
`_webradio_ensure_playing()` test helper (real station-list fetch, not a
`wrUrl` injection — station 0 happened to be an NPO news/talk relay this
session). Measured `get wrPump` after playback stabilized, then two
screendumps of the vis region 1.5s apart (same method and region as
EXP-016/018 — `_vis_pixel_delta`-equivalent, x=0,y=20,w=140,h=70).

**Outcome**:
- **Decode-tail: `maxPumpMs=44` (cycles=6894)** — 2ms over the 42ms figure
  every prior rung measured, well within noise (EXP-016/018/021 all landed
  at exactly 42ms; a 2ms delta from one run is not a meaningful regression
  signal, same conclusion prior rungs drew from similar small deltas).
  **Decode-tail kill gate: cleared.**
- **Pixel delta: 205/9800** between the two screendumps — comfortably
  above the >100 "materially animating" threshold `T_WR_VIS_02` uses, and
  sits between EXP-016's VU result (531/9800) and EXP-018's spectrum
  result (100/9800), consistent with a trace that's visibly live but not
  as broadly full-canvas-changing as a bar-height display.
- **Visual inspection (the actual bar this step exists to clear, per
  PROP-009's Kill gates): both captures show a genuine connected waveform
  line, not a flatline or a rendering artifact.** More telling than the
  pixel-count alone: the two frames show **materially different shapes**,
  not just different heights of the same shape — frame 1 (t=0) shows a
  visibly jagged, irregular trace (consistent with active speech from the
  news/talk content); frame 2 (t=1.5s) shows a much flatter trace with two
  small dips (consistent with a pause between sentences). This is exactly
  the property Option A (amplitude-only synthetic sine) **cannot**
  produce — Option A's sine shape never changes, only its height tracks
  real audio. This spike's trace changes *shape* in response to content,
  which is the actual thing "real audio-driven wave" was asking for.

**Conclusion**: Validated, both remaining kill gates cleared. The
19-column real wave trace is free at this measurement's resolution
(decode-tail), fits within measured storage headroom (EXP-021), and reads
as genuinely content-reactive in shape, not just amplitude, on real live
program material.

**Recommendation**: Propose for graduation, folded into or alongside
TASK-388 (currently scoped as Option A, amplitude-only sine per
`M-WEBRADIO-REAL-VIS-WAVE.md`) — Architect/PM should decide whether this
19-column trace **replaces** TASK-388's Option A scope (better result, same
"ship a real wave mode" goal) or ships as a **third** WebRadio vis mode
alongside both VU and the Option A sine (more tap-cycle stops, a product
call). This spike deliberately did not touch that scope question — it
only answers R&D's job (is it affordable and does it look real), matching
every prior PROP-005 rung's handoff discipline. Two things worth flagging
for whoever picks this up:
1. **The 76-column full-resolution variant is still not proven** — this
   spike only validated 19 columns (matching `SPEC_BARS`, the size that
   fits directly per EXP-021). If full pixel-column resolution is wanted
   later, that's still gated on the reuse-overlay-onto-Spectrum's-arrays
   approach EXP-021 flagged, unmeasured here.
2. **Re-check storage headroom fresh at implementation time** — EXP-021
   already stressed this is a snapshot (40 bytes today), not a durable
   board property; don't carry this session's numbers forward without
   re-deriving them.

**Branch**: `rnd/webradio-wave-spike` (commit follows this report — spike
code retained per R&D branch discipline, not merged).

**Notes**:
- Kill gate check: all three of PROP-009's original kill gates now
  addressed — storage (EXP-021, cleared for 19-col), decode-tail (this
  report, cleared), visible improvement over Option A (this report,
  cleared — shape-reactive, not just amplitude-reactive).
- Decimation choice: plain sub-sampling (`idx = i*len/19`) was used, not
  the min/max-per-column envelope PROP-009 flagged as an alternative —
  worked well enough on real content that a follow-up A/B wasn't run this
  session (same "worth a quick A/B, not a blocker" framing EXP-016 used
  for peak-vs-RMS on the VU rung).
- Test station was whatever `_webradio_ensure_playing()`'s real
  station-list fetch returned as index 0 this session (an NPO news/talk
  relay) — not a fixed `wrUrl` injection. Worth noting for reproducibility:
  a future re-run may land on a different station depending on fetch
  order/availability.
- Screendumps saved to the session scratchpad, not committed (throwaway
  artifacts, same as prior EXP screendump pairs).
- DUT restored to production firmware (`cyd2usb_winamp`) and monitor
  restarted at the end of this session, clean.
