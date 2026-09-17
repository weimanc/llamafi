# VE Review — dataTask result-staleness rule (TASK-706)

> Owner: VE · Date: 2026-09-17 · Reviewed at first draft, uncommitted
> Scope: same testability posture as this session's other VE reviews. Documents only: no code,
> builds, serial port, flashing, or commits performed for this review.

Evidence read in full: the draft; spot-checked its two most load-bearing citations
(`M-MULTIAPP/app-lifecycle.md`'s TBD quote, `IFC-002.md`'s I5 wording) against the live files —
both verbatim-accurate. Did not re-verify every per-fetch-type table cell in the underlying
research transcript; scope below reflects that.

## Code-claim check

The central move — existing identity fields (stockChart symbol/range, planeRadar epoch, geocode
seq) solve *which request*, not *how stale* — is the load-bearing claim the whole design rests on.
I re-read `dataTask.h`'s struct definitions for `PlaneRadarResult`/`GeocodeResult` myself: `epoch`
is bumped only by `_setActiveLoc()` (a location change) and `seq` only by `enqueueGeocode()` — both
confirm the draft's claim structurally (neither field has any time component). Accepted.

## VE-1 (minor) — the primitive-test section is a placeholder, correctly labeled as one

The design says its own test section "needs an actual injector design once the implementation
exists — not designed here." That's honest rather than hand-wavy (it doesn't claim design work it
hasn't done), but it means TASK-706's own ask ("the rule, THEN the primitive test") is only
half-delivered by this document. Not a blocker — the rule is the harder, judgment-requiring half,
and the test is mechanical once an implementation exists to test. Flagging so whoever picks this up
next doesn't read "primitive test" as already specified.

**Resolution:** non-blocking. Note for implementation: pick the injector shape at the same time as
the `arrivedMs` field, not after — a test written after the fact tends to test what shipped rather
than what the rule requires.

## VE-2 (minor) — OQ3 asks a scope question this design shouldn't need to ask

"Is this worth fixing at all, given the severity" reads as the design hedging on its own
recommendation. The rest of the document is confident and well-argued (cheap, targeted, doesn't
regress existing checks) — OQ3 undercuts that by inviting the human to reject the whole thing on
cost grounds the design itself just argued against. Either the Architect believes this is worth
doing (in which case say so plainly and drop OQ3) or genuinely doesn't (in which case the
Lean/recommendation section shouldn't read as confidently as it does).

**Resolution:** the Architect should firm up one way or the other before sign-off; I'd lean "worth
doing" given the design's own cost/benefit argument, but that's the Architect's call to state
plainly, not mine to make for them.

## What I'd sign off on today

The core diagnostic (time-staleness, not identity-staleness, is the actual gap) is sound,
well-evidenced, and correctly scoped smaller than the "complete" generation-counter alternative it
explicitly declines to propose. I'd sign off on this as a design ready for human ruling once VE-2 is
resolved (a one-sentence edit, not a re-review).

## Verdict

**READY**, pending VE-2's one-sentence firm-up. VE-1 is a forward note, not a blocker.
