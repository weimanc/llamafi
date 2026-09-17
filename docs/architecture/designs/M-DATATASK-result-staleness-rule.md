# Design — M-DATATASK: a stated rule for a dataTask result delivered after app-switch (TASK-706)

> Owner: Architect
> Status: proposed
> [VE-reviewed 2026-09-17](M-DATATASK-result-staleness-rule-VE-review.md):
> READY for human sign-off, VE-2 firm-up applied
> Date: 2026-09-17
> Feeds: TASK-706
> Tracked-as: TASK-706
> Registers: none — a rule + a primitive test, no feature registered

## Context

TASK-706: *"A dataTask result for an app that is no longer active has no stated rule: no discard/coalesce was found in `dataTaskStorage.cpp` for a switched-away app's in-flight fetch... Write the rule (ADR-level), then the primitive test."* A full research pass (this session, read-only, no DUT) surveyed all eight `dataTask` fetch types — Weather, Crypto, Stock quote, Stock chart, Stock chart-by-symbol, PlaneRadar, Teletext, Geocode — against exactly this question. Findings, condensed (full citations in the research transcript this doc is built from):

- **No app-identity concept exists in `dataTaskStorage.cpp` at all** (`activeApp`/`currentApp`/`g_appId`/`appShell::` — zero hits). Every fetch type uses a single-slot, spinlock-protected "mailbox" (a result struct + a `New` flag), latest-write-wins, with no drain-on-switch-away and no time-of-arrival check at read time.
- **Three of eight types carry an identity field** (`StockChartResult`'s `symbol`/`rangeIdx`, `PlaneRadarResult`'s `epoch`, `GeocodeResult`'s `seq`) — but every one of them discriminates *which request* a result answers (a superseded lookup, a changed ticker, a changed location), not *how old* it is or *whether the app that asked is still on-screen*. A result for the *same* still-relevant identity, sitting in the mailbox since before an app-switch, passes every existing identity check and is displayed as if it just arrived.
- **Teletext has an unused identity field**: `TeletextState.page` exists (IFC-001 documents it) but the one consumer, `NosTeletextSource::poll()`, doesn't compare it against the page currently being viewed before accepting `result.ready`.
- **Weather, Crypto, Stock quote have no identity field and no protection at all.**
- **The existing governing invariant already on the books — `M-CONCURRENCY-task-ownership-contract.md` R6 / `IFC-002.md` I5 ("results carry identity where a stale reply could apply against changed consumer state")** — was written for a different question: *within one app*, does a newer request's result get confused with an older, superseded one. It was never extended to *across an app-switch*, and even where it's implemented (the three identity-bearing types above) it does not close TASK-706's gap, because "identity" there means "which request," not "how stale."
- **This was flagged as an open question at the feature's introduction and never resolved**: `M-MULTIAPP/app-lifecycle.md:174-176` (the original dataTask design) explicitly wrote *"(or when a cached fetch expires in the background — TBD in dataTask design)"* — a TBD that has sat unresolved since M-MULTIAPP shipped. The same doc analyzed staleness for **Spotify only** (concluded stale-proof, because `spotifyTask` polls continuously in the background regardless of foreground app) and never wrote the equivalent analysis for any of the eight one-shot-per-request fetch types this design covers.
- **Only Geocode closes the actual race by construction, and by accident**: `enqueueGeocode()` bumps `s_geoSeq` on every call, before any concurrent poll can run, so a stale result is provably rejected. This wasn't designed for the app-switch case — it was designed for the abandoned-lookup case — but it happens to also close this door, which is itself evidence for what the general fix should look like (see Lean, below).

## Why this is a time problem, not an identity problem

The existing pattern this project has for "is this result still relevant" is entirely about identity: does the result's tag match what I currently want. That pattern is necessary but not sufficient here, because the failure mode TASK-706 names is different in kind: **the result is for exactly the right thing (same symbol, same location, same page) — it just arrived a while ago, while nobody was watching, and gets displayed as if it just happened.** No amount of "does this match what I asked for" checking closes that gap, because the answer is always yes. What's missing is "and did I ask for it recently enough that showing it as current is honest" — a question about elapsed time, not about identity.

## Goals

- One rule, stated once, that every fetch type can be checked against — not eight separate ad-hoc analyses (the current state, and part of why this went unaddressed for as long as it did).
- Cheap: this is a low-severity UX-staleness issue (a price ticker or forecast reading a few tens of seconds to low-minutes old, not a crash or data corruption), so the fix should be proportionate — this design explicitly does NOT propose an app-identity/generation-counter mechanism threaded through all eight structs and their `Request`s, which would be the "complete" fix but is a much larger change for a problem whose actual cost is cosmetic.
- Must not regress the three identity checks that already exist (stockChart/planeRadar/geocode) — this is additive to them, not a replacement.

## The rule (lean)

**Every dataTask result mailbox stamps its own arrival time; every consumption site refuses a result older than a stated bound instead of accepting anything the `New`/identity check lets through.**

Concretely:
1. Add a `uint32_t arrivedMs` (or equivalent) field to each of the five currently-unprotected-by-time result structs (Weather, Crypto, Stock quote, Stock chart family, Teletext — PlaneRadar/Geocode already have a workable discriminator, see below), set to `millis()` at the point the mailbox is written (the existing `s_*Result = r;` assignment sites — one line each).
2. Each `poll*()` call, or the app-side consumer immediately after it, compares `millis() - result.arrivedMs` against a per-type staleness bound and treats a too-old result as "nothing new" (do not surface it, do not stamp `_s.lastXFetch = now` as if fresh) rather than displaying it. The bound should be a small multiple of that type's own fetch cadence (e.g. Weather's `WEATHER_FETCH_MS=60000` → a bound like 90-120s is "this is basically the answer to the request I'm about to make again anyway"; a much longer bound, e.g. multiple minutes, is the "definitely stale, from before I switched away" case this design is actually about).
3. **Teletext**: wire up the identity check that already exists but isn't consulted (`result.page` vs. the page being viewed) — this closes its case without needing the time bound at all, since it already has the right primitive; add the time bound too for consistency with the other four, but the page check is the more precise fix here and should land regardless.
4. **PlaneRadar/Geocode**: no change needed to their own identity mechanism — their gap is narrower (same-identity-but-stale, not any-staleness) and lower priority; a future revision could add the same `arrivedMs` bound to them for full consistency, but this design does not require it to close TASK-706's stated question, which is about the general absence of any rule, not about closing every fetcher's every gap in one pass.
5. **Stock chart's mismatched-symbol discard already exists and is unaffected** — this adds a time check for the same-symbol-still-stale case it doesn't cover, on top of (not instead of) the existing identity check.

This is deliberately NOT a generation-counter/app-identity mechanism threaded through `Request`. That would be the more "complete" architectural answer (and would also close PlaneRadar/Geocode's residual same-identity race precisely), but it is a bigger, more invasive change to a shared struct eight call sites populate, for a problem whose actual severity is cosmetic staleness, not correctness. If a future finding shows the time-bound approach is insufficient (e.g., a fetch type whose staleness bound can't be sanely chosen because its cadence itself is unbounded or user-configurable in a way that defeats a fixed multiplier), that is the trigger to revisit toward the heavier mechanism — not something to build preemptively.

## What this does NOT change

- No behavior change to Spotify (already analyzed as stale-proof by design, continuously-polling, out of scope — `app-lifecycle.md`'s existing analysis stands).
- No behavior change to WebRadio's station list (recorded in IFC-001 as "none (single consumer)" — a different single-consumer argument than the one this design is correcting; WebRadio's station fetch is itself gated by `tlsYield`/app-exclusivity in ways the other eight types aren't, and re-examining it is out of this design's scope).
- No change to the three existing identity checks' own logic (stockChart symbol/range, planeRadar epoch, geocode seq) — additive only.

## The primitive test

TASK-706 asks for "the rule, then the primitive test" — per this session's TASK-705 precedent (primitive-operation coverage, `M-HARNESS2` gate), this should be a single-op test asserting the RULE itself, not a full end-to-end app-switch scenario (which would need real timing and is a DUT-scheduling question for whoever implements this). Candidate shape: an id that (a) triggers a fetch for one of the five newly-covered types, (b) uses the existing debug-injection surface (`armedInjectors.h`'s pattern, or a new `dbgSet` hook if none fits) to fast-forward or fabricate an `arrivedMs` value older than the staleness bound without waiting for it in real time, (c) asserts the consumer does NOT surface it as fresh. This needs an actual injector design once the implementation exists — not designed here, flagged as the next step once this rule is accepted.

## Open questions

- **OQ1 (bound tuning).** The exact staleness-bound multiplier per fetch type (this design suggests "a small multiple of the fetch cadence" but doesn't pin exact numbers) is an implementation detail best decided against real fetch-latency data, not guessed here.
- **OQ2 (Stock quote's more convoluted resume/mode-change gating).** The research pass flagged `StockApp`'s `_s.lastQuoteFetch`-zeroing permutations (settings changes, sub-view re-entry) as not fully traced — whoever implements this rule for Stock quote should re-verify the same-tick re-enqueue-then-poll race the other four types were confirmed to have, since it wasn't conclusively confirmed for this one.
**This design's recommendation: worth doing.** The lean fix is a handful of one-line stamps plus a per-consumer comparison — cheap relative to closing a design question that has sat open since M-MULTIAPP shipped and that every new fetch type since has had no pattern to follow. The severity is cosmetic (a stale reading shown as current, never a crash or corruption), and that is exactly why the lean rule — not the heavier generation-counter mechanism — is the right size for it, not a reason to skip it.

## Exit criteria

Human sign-off on the lean rule (§"The rule" above) before implementation. This design proposes no DUT time and no firmware change on its own — it is the rule and its rationale; implementation (the `arrivedMs` fields, the consumer-side checks, the Teletext wiring, the primitive test's injector) is separate, scheduled work once the rule itself is accepted.
