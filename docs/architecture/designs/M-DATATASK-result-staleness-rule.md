# Design — M-DATATASK: a stated rule for a dataTask result delivered after app-switch (TASK-706)

> Owner: Architect
> Status: proposed
> [VE-reviewed 2026-09-17](M-DATATASK-result-staleness-rule-VE-review.md) — READY on the v1 draft
> ([independent Opus Architect re-review, 2026-09-18](#revision-2026-09-18-after-independent-architect-review):
> **NOT READY** on that draft — severity premise wrong for PlaneRadar, no design-space section, the
> chosen mechanism has a live counterexample in Stock chart's cadence. Revised below; the lean is now
> the resume-boundary drain, not the time-bound.)
> Date: 2026-09-17, revised 2026-09-18
> Feeds: TASK-706
> Tracked-as: TASK-706
> Registers: `cross_feature_matrix.yaml` X-entry owed for the app-switch-boundary ↔ dataTask-delivery
> interaction this design names (see Exit criteria)

## Context

TASK-706: *"A dataTask result for an app that is no longer active has no stated rule: no discard/coalesce was found in `dataTaskStorage.cpp` for a switched-away app's in-flight fetch... Write the rule (ADR-level), then the primitive test."* A research pass surveyed all eight `dataTask` fetch types — Weather, Crypto, Stock quote, Stock chart, Stock chart-by-symbol, PlaneRadar, Teletext, Geocode — against exactly this question.

- **No app-identity concept exists in `dataTaskStorage.cpp` at all** (`activeApp`/`currentApp`/`g_appId`/`appShell::` — zero hits, confirmed independently across all 2559 lines). Every fetch type uses a single-slot, spinlock-protected "mailbox" (a result struct + a `New` flag), latest-write-wins, popped destructively by `poll*()`.
- **Three of eight types carry an identity field** (`StockChartResult`'s `symbol`/`rangeIdx`, `PlaneRadarResult`'s `epoch`, `GeocodeResult`'s `seq`) — but every one of them discriminates *which request* a result answers, not *how old* it is. Verified at each consumer: `app/src/stock/stockChart.cpp:126` (`strcmp` + `rangeIdx` compare, same-symbol-same-range always accepted), `app/src/apps/planeRadarApp.cpp:40` (`epoch != _locEpoch`, unchanged since only a location change bumps it), `app/src/settings/appsSection.h:1084` (`seq != _prGeoSeq`). A result for the *same* still-relevant identity, sitting in the mailbox since before an app-switch, passes every one of these and is displayed as if it just arrived.
- **Teletext has an unused identity field**: `TeletextState.page` exists but `NosTeletextSource::poll()` (`app/src/apps/teletextApp.cpp:75-95`) does `*out = result;` unconditionally — never compares `result.page` against the page currently being viewed.
- **Weather, Crypto, Stock quote have no identity field and no protection at all.**
- **`M-CONCURRENCY-task-ownership-contract.md` R6 / `IFC-002.md` I5** ("results carry identity where a stale reply could apply against changed consumer state") governs *within one app*: does a newer request's result get confused with an older, superseded one. It was never extended *across an app-switch*, and even the three implemented cases above don't close that different gap.
- **Flagged and never resolved at the feature's introduction**: `M-MULTIAPP/app-lifecycle.md:174-176` explicitly wrote *"(or when a cached fetch expires in the background — TBD in dataTask design)"*. The same doc analyzed staleness for **Spotify only** (stale-proof, continuously-polling) and never wrote the equivalent analysis for the eight one-shot-per-request types.
- **Confirmed live, not just theoretical**: `app/src/apps/weatherApp.cpp:103-104` — `if (dataTask::pollWeather(&r)) { _s.lastDataFetch = millis(); ...` — a drained result is stamped as fetched-now regardless of how long it sat unread, and `WeatherApp::resume()` (`:10-17`) only re-triggers a fetch if the configured coordinates changed, so this also **suppresses the next real fetch for a further `WEATHER_FETCH_MS` (60s)**. The staleness is self-extending, not a one-time cosmetic blip.

## Why this is a time problem, not an identity problem

The existing pattern this project has for "is this result still relevant" is entirely about identity: does the result's tag match what I currently want. That's necessary but not sufficient here: **the result is for exactly the right thing — it just arrived a while ago, while nobody was watching, and gets displayed as if it just happened.** No amount of "does this match what I asked for" checking closes that, because the answer is always yes. What's missing is "did I ask for this recently enough that showing it as current is honest" — a question about elapsed time, or equivalently, about *whether I've been away since I asked*.

## Severity — corrected from the original draft

The v1 draft characterized this uniformly as cosmetic UX staleness (a price or forecast reading tens of seconds to minutes old) and, on that premise, deferred PlaneRadar and Geocode as lower priority. **That premise is false for PlaneRadar, independently confirmed against source:**

- `app/src/apps/planeRadarApp.cpp:62`: `_lastGoodMs = now;` is stamped at **drain** time, not fetch time.
- `app/src/apps/planeRadarApp.cpp:101-104`: the on-screen age readout is `(now - _lastGoodMs) / 1000` — a result popped after sitting parked renders as **"0s old"**, an affirmative wrong freshness claim, not merely an unremarked stale number.
- The same drain instant seeds `_lastInterpMs` / `_reconcileMotion()` (`app/src/apps/planeRadarApp.cpp:69-71`), which **dead-reckons aircraft positions forward from the drain time as if it were the fix time** — a target can be interpolated several nautical miles from its actual position on a map whose entire purpose is position accuracy. This is wrong data, not a stale-looking timestamp.
- The app already carries a scar from exactly this class of bug (`app/src/apps/planeRadarApp.cpp:355`, an existing comment: *"else the next interp tick's dirty-check compares against a stale pre-switch time"*).

Geocode's own `seq` mechanism already closes its race by construction (see Context) — it stays correctly out of scope. **PlaneRadar does not get the same pass and moves into the first tranche of fixes below.** Weather/Crypto/Stock quote/Stock chart/Teletext remain genuinely cosmetic-severity (a stale display value, no downstream data corruption) — the severity claim is now scoped per-type rather than asserted uniformly.

## Design space (options + tradeoffs)

The v1 draft skipped this section — an omission in its own right against this persona's documented standard, and the reason a better option went unconsidered. Three options, compared against the same five criteria.

### A — Time-bound mailbox (v1's original lean)

Stamp `arrivedMs` at each mailbox write; each consumer discards anything older than a per-type bound (a small multiple of that type's fetch cadence).

- **Struct/storage changes**: 5 new fields (Weather/Crypto/Stock quote/Stock chart family/Teletext), a stamp at every write site.
- **New tuned constants**: one bound per fetch type, chosen against real fetch-latency data not yet gathered.
- **Precision**: approximate. "Older than N ms" is a *proxy* for "arrived since I last asked," not the fact itself.
- **Live counterexample, found on review**: `app/src/stock/stockShared.h:20`, `STOCK_CHART_FETCH_SLOW = 300000UL` (5 minutes), used for every chart range but D1 (`app/src/stock/stockChart.cpp:109-110`). A "small multiple" of that is 10-15 minutes — longer than almost any plausible switched-away window, so the bound would admit nearly everything it exists to reject. And because `app/src/stock/stockChart.cpp:111` skips re-fetching inside that same window, a stale chart popped on re-entry **stands unreplaced for up to five minutes**, the longest-lived exposure of any of the eight types — handled worst by exactly this mechanism.
- **Test surface**: needs a new injector able to fabricate an *old* `arrivedMs` without waiting for it in real time — undesigned, and a genuinely new kind of test double this codebase doesn't have yet.
- **Injector-path hazard**: any mailbox write that doesn't stamp `arrivedMs` (a default of `0`, matching every other field's convention in `dataTask.h`) reads as maximally old and gets silently discarded — including any future debug-injection write shaped like `debugInjectWebRadioResult()` (`dataTaskStorage.cpp:2552-2557`). Every writer, test paths included, has to remember the stamp.
- **Verdict: rejected.** The one fetch type whose cadence most needs this bound to work is the one whose cadence breaks it.

### B — Request-ownership drain at the resume boundary (adopted)

**An app must not accept a `dataTask` result it did not itself request since its last `resume()`. Clear the outstanding-request flag and drain the mailbox on resume, before the app's first `tick()` can pop anything.**

- **Struct/storage changes**: none. No new fields anywhere.
- **New tuned constants**: none. No bound to guess, no cadence to reconcile against.
- **Precision**: exact. "Arrived without a live request of mine" is the actual predicate this design wants, not a time-based proxy for it.
- **Test surface**: uses existing `set`/`get` debug surfaces only — inject a result, switch away, switch back, assert it is not surfaced. No new instrumentation needed; the primitive test becomes designable today (see below).
- **Already exists in this tree, working, test-covered**: `app/src/stock/stockApp.cpp:223-231` (`triggerFetch` handler, TASK-300) already does exactly this for Stock chart — zeroes the fetch-state fields *and* explicitly pops-and-discards any parked `StockChartResult`, with a comment naming the precise failure this design is about: *"the next drill-in's first tick pops the stale result."* A VE test (T178) already depends on this behavior. This is not a novel mechanism being proposed; it is an existing, working idiom that four of the eight fetch types simply never adopted.
- **Partially already implemented for Teletext**: `NosTeletextSource::onResume()` (`app/src/apps/teletextApp.cpp:62-67`) already sets `_pendingFetch = false` and forces an immediate re-fetch on resume — it clears the request flag but doesn't drain the mailbox. One line short of the rule.
- **Available hook, uniform across apps**: every app has `suspend()`/`resume()` (`app/src/stock/stockApp.h:54`, `app/src/apps/teletextApp.h:97`, `app/src/apps/planeRadarApp.h:240` — the last already an empty body waiting for exactly this), and `switchApp()` (`appShell.cpp:164-228`) already calls both around every switch. The rule can be stated once in the `App` contract and honored in one line per app.
- **Residual gap, honestly named**: does not cover a result parked while the app stays **foreground but changes sub-view** (Stock's List vs. Chart-detail — TASK-300's own original scenario). `resume()` isn't called on a sub-view change, so a drain keyed only to `resume()` doesn't fire there. This is real but narrower and already partially mitigated by `triggerFetch`'s existing drain plus the mismatched-symbol identity check (`app/src/stock/stockChart.cpp:126`) catching the case where the sub-view change also changed what's being viewed.
- **Verdict: adopted as the primary mechanism.**

### C — Generation-counter through `Request`

Thread an app-identity/generation stamp through the shared `Request` struct and every populate site; every result echoes it back; every consumer compares against the current generation.

- Would close every gap precisely, including B's residual sub-view case.
- **Cost**: touches a shared, `xQueueSend`-copied POD (`dataTaskStorage.cpp:2219-2253`) at all eight populate sites and all eight consumers — real queue-memory and code-churn cost, for a problem set that (once PlaneRadar's re-scoped severity is fixed by B) is otherwise cosmetic.
- **Better reason to decline than "expensive," found on review**: `resume()` *is* the generation edge already. A generation counter would re-derive, at a real cost, information the resume boundary already carries for free. Declining C isn't a cost/benefit trade against correctness — it's recognizing C is redundant with a boundary this design already uses.
- **Verdict: declined**, for redundancy with B, not primarily for cost. Revisit only if B's sub-view residual (Stock quote/chart while foreground) is later shown to matter enough on its own to justify the generation stamp — at that point it would be scoped to Stock alone, not all eight types.

## The rule

**Every app drains its `dataTask` mailbox and clears its outstanding-request flag in `resume()`, before its first post-resume `tick()` can read anything stale.** Concretely, for the five currently-unprotected types (Weather, Crypto, Stock quote, Teletext's page check, PlaneRadar):

1. **PlaneRadar (first tranche — this is the one with real data-correctness cost, not just cosmetic staleness)**: `PlaneRadarApp::resume()` (`app/src/apps/planeRadarApp.h:240`, currently empty) drains any parked `PlaneRadarResult` via `pollPlaneRadar()` and discards it, mirroring `app/src/stock/stockApp.cpp:223-231`'s pattern exactly. Bump `_locEpoch` on resume too (not just on an actual location change) so the epoch check alone would also catch it — belt and suspenders, since this is the correctness-bearing case.
2. **Teletext (independent, standalone, lands regardless of what else in this list ships)**: wire up the identity check that already exists but isn't consulted — `NosTeletextSource::poll()` compares `result.page` against the page currently being viewed before accepting it, matching the pattern `app/src/stock/stockChart.cpp:126` already uses for symbol/range. This is the highest-severity item in the whole list after PlaneRadar's fix: an unwired page-identity check doesn't just show stale content, it **retargets which page the app believes it's viewing** (`*out = result` at `app/src/apps/teletextApp.cpp:87` overwrites `_st.page`, which can propagate into `g_settings.teletextPage` — a spontaneous, user-visible navigation, reachable via back-navigation mid-fetch within a single session, not only across an app-switch). Two-line fix, no new field, no new test surface — should not wait on the other four.
3. **Weather/Crypto/Stock quote**: each app's `resume()` drains its own mailbox (`pollWeather()`/`pollCrypto()`/`pollStockQuote()`, discarding the result) and resets its own "last fetch" gate so the next `tick()` re-enqueues rather than treating the drained-and-discarded slot as satisfied.
4. **Stock chart**: `triggerFetch`'s existing drain (`app/src/stock/stockApp.cpp:227-232`) is the reference implementation — extend the same drain to run on ordinary `resume()`, not only on the debug-injected reset path it was written for.

## What this does NOT change

- No behavior change to Spotify (already analyzed as stale-proof by design, continuously-polling — `app-lifecycle.md`'s existing analysis stands).
- No behavior change to WebRadio's station list (a different single-consumer argument, gated by `tlsYield`/app-exclusivity in ways the other eight types aren't; out of scope).
- No change to the three existing identity checks' own logic (stockChart symbol/range, planeRadar epoch, geocode seq) — this is additive to them (PlaneRadar's epoch-bump-on-resume) or independent of them (Teletext, drain-based types).

## The primitive test

Unlike v1's time-bound mechanism (which needed an undesigned injector to fabricate an old timestamp), the drain rule is testable with existing surfaces today: inject a result for one of the covered types (the existing debug-injection pattern), switch away and back via the normal `switchApp` path, and assert the app's next `tick()` does **not** surface the injected result as fresh (it should instead show the state a real fresh fetch would produce — nothing yet, or a newly-enqueued in-flight state). For PlaneRadar specifically, additionally assert the age readout does not read "0s" for a result that predates the switch, and that `_locEpoch` changed across the resume.

## Open questions

- **OQ1 (Stock quote's resume/mode-change gating, partially resolved).** `StockApp::resume()` (`app/src/stock/stockApp.cpp:35-63`) only zeroes `_s.lastQuoteFetch` when the configured tickers changed — on an ordinary switch-away-and-back inside `STOCK_QUOTE_FETCH_MS` (60s), today's code enqueues no new fetch and pops any parked result as fresh. This is exactly the case this design's rule 3 fixes; the remaining open question is narrower than v1's framing suggested — just the settings-change permutations around it, not the whole gating path.
- **OQ2 (Stock's sub-view residual, named honestly rather than hidden).** A result parked while the user stays on StockApp but changes sub-view (List ↔ Chart-detail) isn't covered by a `resume()`-keyed drain, since `resume()` isn't called on a sub-view change. Mitigated today by `app/src/stock/stockChart.cpp:126`'s existing symbol/range check catching the case where the sub-view change also changed what's being viewed, plus `triggerFetch`'s explicit drain for the debug-reset path. If this residual is later shown to matter in practice, it's the trigger to consider Option C (§Design space) scoped to Stock alone — not to revisit the drain's design for all eight types.

**This design's recommendation: worth doing, and now cheaper than the original draft proposed.** The drain rule needs no new struct fields, no tuned constants, and reuses a pattern this codebase already trusts (TASK-300) rather than inventing one. It closes a design question open since M-MULTIAPP shipped, fixes a real data-correctness bug in PlaneRadar (not just a cosmetic one), and delivers both halves of TASK-706's own ask — the rule and a genuinely designable primitive test — in one pass.

## Exit criteria

Human sign-off on the rule (§"The rule" above) before implementation. Register a `cross_feature_matrix.yaml` X-entry for the app-switch-boundary ↔ dataTask-delivery interaction this design names (Architect's own standard: naming an identity/staleness rule spanning a shell boundary and multiple app consumers is a cross-feature edge) — Developer completes/corrects at implementation per the usual reservation split. This design proposes no DUT time and no firmware change on its own; implementation (the five `resume()` drains, the Teletext identity check, the primitive test) is separate, scheduled work once the rule itself is accepted.

## Revision, 2026-09-18, after independent Architect review

An independent second-opinion review (different model instance, same Architect persona, `docs/agents/architect.md`) verified every factual claim in the v1 draft against live source and found the diagnostic sound but the recommended mechanism wrong on three grounds: PlaneRadar's severity was mischaracterized (§Severity above), no design-space section existed so a better, cheaper, already-precedented option was never considered (§Design space, Option B), and the time-bound's own escape-hatch trigger ("a cadence too long for a sane multiplier") already had a live counterexample in Stock chart. All three are corrected above; the rule changed from a time-bound to a resume-boundary drain as a direct result. The review also correctly promoted the Teletext identity-wiring fix to a standalone, independent, highest-priority item (§"The rule" item 2) since it has real state-clobber consequences beyond staleness and needs no new mechanism. Full review on file in this session's record; not reproduced here in full to avoid the same doc-bloat BP-069 exists to prevent on task boards.
