# VE Review — dataTask TLS buffer lifetime (TASK-708)

> Owner: VE · Date: 2026-09-17 · Reviewed at commit (uncommitted, first draft)
> `docs/architecture/designs/M-DATATASK-tls-buffer-lifetime.md`, `Status: proposed`
> Scope: TESTABILITY review, same posture as `M-DATATASK-heap-region-instrument-VE-review.md` —
> is the design's exit criterion agent/harness-executable, does it expose the right observables,
> is F3 actually gated on OQ1 or does the document's own structure quietly commit past it.
> Documents only: no code, builds, serial port, flashing, commits, or task-board edits performed
> for this review.

Evidence read in full: the draft in full (post-correction, task-identity-check claim already fixed
by the Architect during drafting — confirmed against `spotifyTaskStorage.cpp:685-730`, which is
semaphore+queue, not task-handle comparison); `task697-reboot-inject-stock.md` (Option 3 A/B
section and "the lead this leaves"); `M-HEAP-FRAGMENTATION.md` (Option C1/D/E sections); ADR-029;
`dataTaskStorage.cpp:1-6, 477-509`; `app/mem_manifest.yaml` headroom block.

## Code-claim check

- `dataTaskStorage.cpp:1-6`'s ADR-029 citation and the "no persistent TLS connection" wording:
  verified verbatim.
- `headroom.INTERNAL: 60000` "~40 K mbedtls fetch context + margin": verified verbatim in
  `app/mem_manifest.yaml`.
- The 9-call-site count: I count `WiFiClientSecure tls;` declarations at lines 570, 633, 703, 781,
  946, 1223, 1346, 1614, 1854 — **9, confirmed**, matching the draft.
- Revision 3's "every reacquire failed (8/8)" and "76 `-32512` per try": verified against
  `task697-reboot-inject-stock.md`'s results table.

No further code-claim errors found beyond the one the Architect already caught and corrected
in-draft (task-identity check mechanism).

## VE-1 (blocker) — OQ1 is named, not designed; the document reads as gating on it while doing nothing to make it schedulable

The "Lean / recommendation" section says F3 is "gated on OQ1 first," and OQ1 itself is described
only as *"a cheap, DUT-time experiment distinguishing 'dataTask fetch churn causes the
fragmentation' from other candidate causes, run and read under the same pre-registered-rules
discipline TASK-697's prior sessions used."* That is a requirement for an experiment, not an
experiment. This project's own process (`AGENTS.md`, and TASK-697's own history — Gate 0 stopping a
perturbing instrument, the pre-registered rules stopping a 0-of-8 from being reported as success)
requires decision rules pre-registered *before* a run, not before a design doc is accepted. As
written, a human reading this design cannot actually authorize OQ1 — there is nothing to authorize
yet, only a name for a future authorization request. That's a meaningful gap for a document whose
entire recommendation rests on OQ1 resolving first.

**Resolution:** either (a) narrow this design's own scope to "diagnosis only, no F3 commitment" and
retitle/reframe the recommendation as "if OQ1 confirms X, then F3 is the lean" rather than
presenting F3 as already the lean subject to a formality, or (b) add a genuine OQ1 protocol
sketch — candidate shape: hold `TLS_RESERVE_EXPERIMENT`'s existing boot-reservation code (already
built, `dataTaskStorage.cpp:310-380`) permanently acquired (no release/reacquire dance at all, sidestepping
the mechanism Revision 3 already proved doesn't work) across N reboots, comparing Stock-id
pass rate against an unmodified control — reusing existing instrumentation rather than building
new, which is squarely in this project's stated preference (BP-59-adjacent: verify before
theorizing, reuse before rebuilding). I'd rather see (b): it costs nothing to write down now and
saves a design-doc round-trip when someone does pick this up.

## VE-2 (major) — F3's own gate gets no pre-registered decision rule either

Even once OQ1 is scheduled and confirms the hypothesis, F3 itself (the allocator hook) needs its
own accept/reject criterion before implementation — not "it worked" but a *stated* bound, the same
discipline Gate 0 applied to the heap-region instrument (tolerance {3,4,5}/8) and Revision 3's own
rules applied to the reservation experiment (engagement rate, confound bound). The draft's OQ3
("blast radius... needs its own review before acceptance") gestures at this but doesn't commit to
a concrete gate. Given this design explicitly declines to authorize implementation yet, I'm not
blocking on this — but flagging it now so whoever schedules OQ1 doesn't also have to reopen this
question from scratch: the "accept/reject F3" gate should probably be defined in the *same* sign-off
round as OQ1's protocol, not deferred to a second design-doc cycle.

**Resolution:** non-blocking. Note for whoever schedules OQ1: bring F3's accept/reject rule (not
just OQ1's) to that same sign-off conversation.

## VE-3 (minor) — F2's rejection reasoning is sound but its "strictly better than F3" framing needs one caveat

The draft says F2 is listed "only to establish that the checker-change cost is unavoidable once you
share anything, not a reason specific to F3" and implies F3 pays that same A5-rework cost. Reading
F3 again: it explicitly claims F3 does **not** need an A5/checker change ("the object's declaration
site is untouched, only where its internal buffer's bytes physically come from changes"). That's
correct as I read it, but it means the framing sentence linking F2's cost to F3 is confusing on a
close read — F3 avoids the exact cost the sentence says is "unavoidable once you share anything."
Worth a one-line fix so a future reader doesn't conclude F3 also needs the A5 rework it was
specifically designed to avoid.

**Resolution:** reword the closing sentence of F2 to say the A5-rework cost is specific to sharing
the **object's declaration** (F2), not to sharing the **backing bytes** (F3) — they are different
kinds of "sharing" and only one trips the checker.

## Resolution pass, same day

VE-1 (b) and VE-3 both applied to the draft directly rather than deferred: OQ1 now carries a
concrete protocol (permanent-acquire the existing `TLS_RESERVE_EXPERIMENT` reservation with no
release/reacquire at any bracket, N≥8 reboots, failure-set comparison, decision rule stated before
the run) reusing built instrumentation rather than proposing new code; F2's closing sentence now
correctly scopes the A5-rework cost to sharing the *declaration* (F2), not the *backing bytes*
(F3). VE-2 remains a forward note, not a blocker — it asks whoever schedules OQ1 to also bring
F3's own accept/reject rule to that conversation, which is a scheduling-time action, not something
this document can pre-register today without knowing OQ1's actual result shape.

## What I'd sign off on today

The design's load-bearing claim — "don't implement F3 yet; the hypothesis is unconfirmed" — is
sound and matches this project's burned history on this exact investigation (two refuted readings
already on record for TASK-697). With VE-1/VE-3 applied, I'd sign off on this document both as the
diagnostic/design-space record **and** as specifying OQ1 well enough that a human sign-off on
*scheduling* OQ1 (not on implementing F3 — that's a separate, later gate per VE-2) is now a
real, answerable decision rather than a placeholder.

## Verdict

**READY** for human sign-off on scheduling OQ1 only. F3 implementation itself stays gated on OQ1's
result and a separate accept/reject rule (VE-2) not yet written — this review does not recommend
signing off on F3 today, only on the diagnostic step in front of it.
