# VE Review — M-WEBRADIO-POSBAR-SLEW

> Owner: VE · Date: 2026-08-06 · Reviewed at commit 3ce7812 (design doc itself uncommitted,
> Status: draft)
> Scope: TESTABILITY review, same convention as `webradio-posbar-VE-review.md` (TASK-402).
> Doc: `docs/architecture/designs/M-WEBRADIO-POSBAR-SLEW.md`
> Every code claim was independently re-verified against the tree, not taken on the design doc's
> word. Findings labelled VE-n, classified blocker / major / minor, each with a proposed
> resolution. Architect disposition to follow.

---

## Code-claim verification

Verified true in tree (independent re-check):

- Gated redraw block (`webRadioApp.h:990-1009`) matches the doc's description exactly: `deltaOk`
  (`≥2` on the smoothed-rounded value) AND `intervalOk` (`≥WR_POSBAR_MIN_REDRAW_MS` elapsed) both
  gate the draw; `_posbarLastSkipReason` records `DELTA` or `INTERVAL` on skip, `NONE` on a
  successful redraw (`webRadioApp.h:1005,1008-1009`) — confirming "none" today means "we drew,"
  not "no reason," a distinction the design doc's own step 4 gets wrong (see VE-1).
- `_bufPctDrawn` is `uint8_t` (`webRadioApp.h:1691`), `_bufPctSmoothed` is `float`
  (`webRadioApp.h:1695`) — the design's slew step (integer clamp toward a rounded target) needs no
  new field type, confirmed. `perf.h`'s `MAX_PATHS` stays at 11 (TASK-402's own bump) — no new
  instrumentation site is added by this design, confirmed by re-reading the Lean section against
  `_drawPosbar()`'s current single call to `perf::record("wr.posbar", ...)`.
- `_play()`'s force-reset of `_bufPct=0` on every reconnect attempt is real
  (`webRadioApp.h:1861`, inside the CONNECTING-transition branch, not gated on `_state==PLAYING`)
  — confirms the design's stated reason for needing `wrState`-aware filtering in the trace tool.
  **Separately confirmed the doc did NOT claim**, and should not have implied by omission: this is
  distinct from the *PLAYING-entry* reset at `webRadioApp.h:740-741`
  (`_bufPctDrawn=0; _bufPctSmoothed=0.0f`), which fires exactly once per successful
  `CONNECTED→PLAYING` transition, not on every tick and not on the mid-stream near-zero dips the
  traces show during a real burst-drain (those are genuine ring-buffer reads, not state resets) —
  re-verified by reading the surrounding `WrPumpResult::CONNECTED` branch directly, not assumed
  from the doc's framing. This distinction matters for VE-2 below.
- `set wrBufPct` (`webRadioApp.h:1627-1634`) still force-writes `_bufPct`/`_bufPctSmoothed`/
  `_bufPctDrawn` and calls `_drawPosbar()` immediately, unconditionally bypassing both gates —
  matches the design's step 5 claim exactly.
- `wrDeadUrls`'s `_debugForceConnFail` path is an early return in `_play()` that sets
  `ERROR_UNREACHABLE` **without ever calling the real `connecttohost()` and without ever reaching
  `PLAYING`** — this is not a fresh finding, it's TASK-395's own documented conclusion
  (`tasks.md`'s TASK-395 entry, re-verified against current `webRadioApp.h` rather than trusted
  from the task log alone). The design doc's own Exit Criteria cites `wrDeadUrls` as one option for
  testing OQ2 — this claim does not hold up under re-verification (see VE-2, blocker).
- `task399_402_dut_verify.py:184-187`'s existing `lastSkipReason` assertion is
  `reasons.issubset({"delta","interval","none"})` — a **subset** check, so it would not fail if
  `"delta"` stops appearing. Confirmed this specific existing test is not a hard blocker for VE-1's
  finding, but its own intent (docstring: "takes at least one recognized value... across the
  window") assumed all three could plausibly appear — worth a note, not a blocker.

---

## Findings

### VE-1 (major) — the design's own step 4 misdescribes what happens to `lastSkipReason`, and the imprecise version loses observability the whole design depends on

The Lean section's step 4 says the three-value `lastSkipReason` contract "collapses ... to
effectively `interval|none`." Re-deriving the slew logic directly: on every `MIN_REDRAW_MS`-
eligible tick there are still exactly two outcomes — the drawn value is already equal to the
rounded smoothed target (nothing to step, a direct re-mapping of today's `DELTA` skip: "value
hasn't moved enough to matter"), or it isn't (step and redraw, `NONE`) — plus the existing
time-gate skip (`INTERVAL`). **All three values remain independently meaningful under the slew
design; nothing needs to collapse.** The doc's own OQ1 (final constant tuning) and OQ2 (stall-
visibility) both need exactly this three-way signal to work — an OQ1 tuning pass can't otherwise
tell "the bar isn't moving because it's already caught up to a flat buffer" apart from "the bar
isn't moving because the time-gate is holding it back," which is the same class of ambiguity
TASK-402's own VE-4 finding already fixed once for the delta/interval case. **Resolution:** drop
the "collapses" language; keep three-way semantics, renaming `DELTA` to something accurate for its
new meaning (e.g. `CONVERGED`) if the name is felt to be misleading post-change — a naming choice,
not a functional change. Low-risk to fix (rename + one clarified comment), but must be fixed before
implementation, not left to Developer's own reading of an already-wrong doc sentence.

### VE-2 (blocker) — no existing debug hook can actually exercise OQ2 (stall-visibility through the *gated* path) deterministically; the doc's own proposed method doesn't work

Exit Criteria's OQ2 check proposes "a real stall, or `wrDeadUrls`-style injected failure with the
buffer left to drain naturally beforehand." Re-verified against the tree (see Code-claim
verification): `wrDeadUrls` never reaches `PLAYING` at all, so there is no real ring buffer to
drain and no path through the gated-redraw block being tested — this option is not available as
written, not a matter of using it carefully. The other existing hook, `set wrBufPct`, **explicitly
bypasses both gates** (design's own step 5, re-confirmed above) — using it to synthesize a decline
would test the debug-forced path, not the slewed/gated one, and would tell you nothing about
whether OQ2 actually holds. **This means OQ2 as currently scoped has no deterministic test path at
all — only "wait for a real stall to happen live," which is exactly the failure mode that already
left TASK-402's own OQ1/OQ2 unresolved for a full day-plus (filed 2026-08-05, still open when this
design doc's own predecessor session started 2026-08-06).** Recommend blocking implementation on
adding a narrow debug hook — e.g. a `set wrPosbarSimDrain <startPct>[,<stepPerTick>]` that seeds
`_bufPct` to a starting value and then decrements it by a small fixed amount each real tick
**through the normal, non-bypassing code path** (i.e. it feeds the raw input the EMA/slew logic
consumes, it does not `_drawPosbar()` directly) — mirrors `wrDeadUrls`'s own "deterministic
synthetic injection for testability" precedent, applied to the one exit criterion that currently
has no way to be met on purpose. Classified **blocker**, not major: without this, OQ2 is not
"harder to verify," it is **not verifiable at all** as scoped, and this design's own stated Goal
("do not hide a genuine depleting-buffer trend indefinitely") has no test behind it.

### VE-3 (major) — Exit Criteria doesn't require the multi-trial protocol this exact project has already been burned by skipping twice

M-WEBRADIO-POSBAR-SMOOTH's own VE-3 (TASK-402) required ≥3 trials for its live-eyeball exit
criterion specifically because of two prior documented single-shot DUT/RF comparison failures
(`touch-ux-panel-VE-review.md` VE-2-1, `M-HEAP-FRAGMENTATION.md` OQ4) — and TASK-402 **never
actually ran that multi-trial protocol either** (its own tasks.md entry lists it as still-open,
which is the entire reason this design doc exists). This design's Exit Criteria repeats the same
"live human eyeball" language but drops the trial count and the "same station, comparable
conditions" framing entirely. Given this project's traced data already shows highly
station-dependent behavior (worst-case 2s-window range ranged 15-96 points across five stations in
the same session), a single eyeball pass on whichever station happens to be reachable that day
risks the same non-resolution TASK-402 hit. **Resolution:** require ≥3 trials, explicitly against
the originally-reported station (SLAM!) at minimum — not "whichever reproduces live" as currently
worded, which lets the easiest station stand in for the one actually complained about.

### VE-4 (minor, informational) — the host-side simulation's fidelity rests on an unverified assumption about real on-device tick rate

The Analysis section's simulation applies the EMA update once per *captured sample* (external
serial-poll rate, measured at ~20-90ms/sample) to approximate the real per-`tick()` EMA update
rate. This is a reasonable proxy — order-of-magnitude consistent with `loop_max` values seen in
this project's own heartbeat logs (24-85ms under WebRadio + Spotify-idle load) — but was never
independently confirmed against a real on-device tick counter, and EMA behavior is sensitive to
this (a materially faster real tick rate would mean the real device's smoothing is lighter, in
wall-clock terms, than the simulation assumes, since more EMA updates happen between each 200ms
redraw-gate check). Not a blocker — the simulation's qualitative conclusion (today's gate bounds
frequency, not magnitude; a slew limiter fixes that) doesn't depend on the exact tick rate, and the
DUT verification step in Exit Criteria will catch a fidelity gap if one exists. Flagged so it isn't
silently assumed exact in a later write-up.

### VE-5 (minor) — OQ3's "no action item created here" is the right call but should be an explicit PM decision, not an implicit non-decision

Reasonable scope boundary (this design shouldn't absorb TASK-390/391/393/398's connect-reliability
thread). Only flagging so it's a recorded PM disposition ("noted, no new task, folded as a data
point into the existing thread" or similar) rather than something that quietly falls off both
task's radar — same discipline TASK-396's own audit was filed to catch project-wide.

---

## Verdict

**Approve-with-changes.** One blocker (VE-2 — OQ2 has no test path as scoped, needs a debug hook
before implementation can meaningfully claim to meet its own Goal), three majors (VE-1 correcting
a wrong claim in the doc itself, VE-3 requiring the multi-trial protocol this project has already
paid for the lesson on twice), one informational minor (VE-4), one process minor (VE-5). Nothing
here challenges the core Lean decision (Option C, the slew limiter) — the simulation evidence for
it is sound and independently re-checked. The gaps are all in exit-criteria testability, the same
category TASK-402's own VE review caught and folded before implementation; recommend the same
treatment here before this goes to human sign-off.
