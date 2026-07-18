# PROP-005 — Real visualization from the WebRadio audio stream

> Owner: R&D Engineer
> Status: registered 2026-07-18 (human-commissioned; PM tracks as TASK-351)
> Branch: `rnd/webradio-vis` (per AGENTS.md — R&D never merges to main directly)
> Companion: M-WEBRADIO-WINAMP-UI item 4 (design doc has the production seam)

## Premise

ADR-009 made the visualizer synthetic because the Spotify path never touches
audio on-device. WebRadio broke that premise: real PCM is decoded locally by
the audioI2S pump task. TASK-350 (mock-vis reuse) deliberately refactors
`vu::tick()` to take caller-supplied level inputs — that seam is where real
data would plug in. This proposal explores whether real levels are affordable.

## Question to answer

Can we derive audio levels from the WebRadio decode path — within the
no-PSRAM heap budget, the pump task's decode-tail timing (TASK-278: tail
spikes were fought down to 50 ms/0 spikes; we must not regress that), and
without touching the Spotify path — at a quality visibly better than the
ADR-009 synthetic envelope?

## Suggested ladder (cheap-kill-first, LL-087)

1. **Tap point spike:** find where PCM is cheapest to observe (audioI2S has
   process/callback hooks — verify which exist in our vendored fork before
   building anything). Measure the cost of just *touching* every sample
   block (pass-through, no math) on the pump task. If decode tail regresses
   measurably → kill or move the math off-task.
2. **Envelope only:** per-block peak/RMS → L/R levels into the vu:: seam via
   a lock-free snapshot (single-writer pump, single-reader UI — same pattern
   as the ICY title queue). This alone replaces the fake envelope with a real
   one for VU + atlas gating; likely the best value/cost point.
3. **Bands (only if 2 is cheap):** fixed-point 4–8 band energy (Goertzel or
   IIR band-pass — NOT a full FFT until proven necessary) to drive the
   spectrum-style modes. Prior art in-repo: `docs/rnd/reports/
   M-VIS-spectrum-analysis.md` and siblings from the M-VIS research round.

## Kill gates

- Decode-tail p95 regresses vs the TASK-278 baseline → stop, report.
- Envelope math needs a heap allocation on the pump task → redesign or stop
  (arena/stack only; TASK-295's unchecked-malloc lesson applies).
- Visible improvement over synthetic is marginal on the 76×16 vis area →
  report honestly; the synthetic envelope is already good decoration.

## Deliverables

EXP report under `docs/rnd/reports/` (numbers: decode-tail deltas, CPU/heap
cost per rung); if validated, a graduation proposal for PM — production
integration is NOT part of this activity.
