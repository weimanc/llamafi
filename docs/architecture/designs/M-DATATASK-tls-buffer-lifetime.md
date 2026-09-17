# Design — M-DATATASK: own the dataTask TLS buffer for the client's lifetime (TASK-708)

> Owner: Architect
> Status: proposed
> [VE-reviewed 2026-09-17](M-DATATASK-tls-buffer-lifetime-VE-review.md):
> READY for human sign-off on scheduling OQ1 only; F3 implementation is a
> separate, later gate not covered by this sign-off
> Date: 2026-09-17
> Feeds: TASK-708 (the lead left by TASK-697, PARKED at P2)
> Tracked-as: TASK-708
> Registers: none yet — this design does not commit a registry claim; see
> "Registers" at the foot

## Context

TASK-697 spent four DUT sessions chasing a post-reboot heap-fragmentation
symptom (~22 Stock ids fail on an affected full run, cause never conclusively
named) and was downgraded to P2 and parked by the human's stopping condition
(2026-09-14, recorded in
[task697-reboot-inject-stock.md](../../verification/regression_suite/task697-reboot-inject-stock.md)).
Its last experiment (Revision 3 / "Option 3", `93b5455a`) tested a **shared,
release-and-reacquire heap reservation**: a single 40 KB `heap_caps_malloc`
span, held from `dataTask::begin()` and briefly released/reacquired around
each of `dataTask`'s 9 TLS fetch brackets. The result: every reacquire
failed (8/8) — once released, the span never came back, because nothing
constrains where the *next* unrelated allocation lands — and holding it
otherwise starved everything else (76 `-32512` results per try against
0-20 in the control). **The one thing that moved the needle**: even in this
broken, degenerate form (the span handed away once, at boot, to the first
fetch that asked, and never meaningfully recovered), the Stock fetch under
test (`T170`) passed 8/8 against a 3/8 control. The doc's own conclusion:
*"a real fix would have to own the span for the TLS client's lifetime rather
than gamble on re-acquiring it... decided in an ADR, not a probe flag."*
That sentence is this design's brief.

**Scope correction worth stating up front.** Revision 3's own premise check
(`f636e981`) found Spotify never holds a live TLS session during the
`T_PR_04`→`T170` sequence the A/B ran (TASK-675's cert-pin rot fails every
Spotify refresh before a session forms — the same failure visible live in
this session's own monitor log at boot). **The evidence gathered so far says
nothing about dataTask's fragmentation problem in the presence of a live,
persistent Spotify TLS session** — the regime the original heap-fragmentation
investigation ([M-HEAP-FRAGMENTATION.md](M-HEAP-FRAGMENTATION.md)) was about.
It tests a *different*, narrower failure: **dataTask's own fetchers
fragmenting the heap against each other**, reboot over reboot, independent
of Spotify. This design is scoped to that narrower problem. Whether the fix
below also helps once TASK-675 is fixed and Spotify holds a real session
again is an open question (OQ2 below), not something this design claims.

## The mechanism (why churn, not contention, is the suspect here)

`dataTaskStorage.cpp:1-6`, under **ADR-029**: *"per ADR-029 each fetch
stack-allocates a `WiFiClientSecure`, calls `setCACert()`, then passes it to
`http.begin(client, url)`. No persistent TLS connection; 60 s cadence makes
setup overhead negligible."* Nine call sites do this (Weather, Crypto,
Teletext, Geocode, Stock quote/chart/heatmap/chart-by-sym, PlaneRadar) —
each one constructs a fresh `WiFiClientSecure` on the stack, which lazily
allocates its mbedTLS `in`/`out` buffers on first `connect()`
(`CONFIG_MBEDTLS_SSL_MAX_CONTENT_LEN=16384` each, ADR-057/058's own figures
— ~32 KB combined per session), uses them for one HTTP round trip, and frees
them when the object goes out of scope at the end of the function. ADR-029's
rationale (60 s cadence, setup overhead negligible) was written for the
*time* cost of this pattern; it did not evaluate the *heap-shape* cost. That
gap is what this design closes.

Every one of those ~9 sites repeats the same carve-then-free cycle,
independently, dozens of times over a session. TASK-289's own guard
comment and M-HEAP-FRAGMENTATION's measurement already established that
ESP-IDF's `multi_heap` allocator does not reliably re-coalesce a freed
~32-40 KB block back into its neighbor — the split can outlive the free.
Repeating that cycle nine ways, reboot after reboot, is a second and
independent source of the same class of damage M-HEAP-FRAGMENTATION found
from Spotify's *single* persistent-connect carve — this one self-inflicted
by dataTask's own fetch pattern, not by contention with Spotify. TASK-697's
Stock-specific symptom (a fetch that used to pass losing its contiguous
block after enough reboots/fetches) is consistent with this mechanism
without yet being proven to be caused by it — no DUT time has been spent
isolating churn from contention (see OQ1).

## Prior art this design builds on, not repeats

[M-HEAP-FRAGMENTATION.md](M-HEAP-FRAGMENTATION.md) (2026-07-19, rejected —
parked, not adopted for its own problem) already surveyed "reserve a
dedicated buffer" in depth as **Option C1** (a real mbedTLS allocator arena)
and rejected adopting it *then*, for two reasons:

1. mbedTLS allocates via `mbedtls_platform_set_calloc_free`, a
   **process-global** hook — redirecting it affects every TLS consumer
   (Spotify included) unless additionally gated by a task-identity check.
2. ADR-047 Amendment 1 already rejected a *smaller* mbedTLS-adjacent change
   (shrinking `MBEDTLS_SSL_IN/OUT_CONTENT_LEN`) specifically because mbedTLS
   config has global blast radius on this pinned toolchain
   (Arduino-ESP32 2.0.17).

Its verdict: *"mechanically the 'real' version of this idea, but high
complexity and toolchain risk for a problem [Option E, sequencing] can
solve without touching mbedTLS at all... flag as a longer-horizon R&D
candidate if Option E ever proves insufficient — not now."*

**What's different this time:** Option C1 was evaluated for
*Spotify-vs-WebRadio contention*, where the task-identity gate has to
distinguish two independently-scheduled tasks racing for the same heap.
Here the population needing the persistent buffer is **dataTask's own nine
call sites, which already execute serially on one task** (`dataTaskStorage.cpp`'s
own model — one FreeRTOS task, one fetch at a time). A task-identity gate
for "is this dataTask" is a much smaller, cheaper claim than "is this the
specific fetch dataTask happens to be running right now vs. a completely
independent task" — the hard part of C1's original objection was ever
knowing to divert *only* the intended caller, and a single-task, serial
caller population is close to the easy case, not the hard one. It does not
remove objection #2 (ADR-047's global-blast-radius precedent) — that risk is
real regardless of which caller population is diverted, and is this design's
main open cost (OQ3).

## mem_manifest.yaml already budgets for this

`app/mem_manifest.yaml`'s `headroom.INTERNAL: 60000` is annotated *"~40 K
mbedtls fetch context + margin"* — the ~32-40 KB this design would make
persistent is **already reserved headroom, not new budget**. This design
does not need a ceiling increase; it needs that already-anticipated
transient allocation to stop being alloc'd-and-freed nine different ways
and become one thing that is allocated once and reused.

## Goals

- Eliminate the alloc/free churn from dataTask's own 9 TLS fetch call sites
  as a source of cumulative heap fragmentation, without touching Spotify's
  own TLS lifecycle or WebRadio's (already-solved via Option E) contention.
- Stay inside the already-declared 60 000 B `headroom.INTERNAL` budget — no
  ceiling change.
- Preserve `gate/check_app_conformance.py`'s A5 check, which attributes an
  HTTPS session-open site to an app by finding the enclosing function of a
  `WiFiClientSecure` *declaration* (`dataTaskStorage.cpp:477-487`) — any
  design that collapses all 9 declarations into one shared site breaks A5's
  per-app attribution and needs its own conformance-checker change, which
  is real added scope, not incidental.
- No new DUT session required to *design* this — TASK-697 stays parked;
  implementation and validation are separate, later decisions (see
  "Registers" and OQ1).

## Design space (options + tradeoffs)

### F1 — Per-fetcher persistent `static WiFiClientSecure` (reject — budget)
Change each of the 9 call sites' `WiFiClientSecure tls;` from stack-local to
`static`, so each fetcher's own client (and its lazily-allocated mbedTLS
buffers) persists across calls instead of being freed each time. Simplest
possible change — one keyword per site — and satisfies A5 unchanged (still
declared per-function). **Rejected on arithmetic alone**: 9 independently
static ~32-40 KB buffers, all resident simultaneously for the rest of the
boot, is 288-360 KB against a 290 000 B *total* INTERNAL ceiling. Even
though only one fetch runs at a time, `static` storage does not know that —
every one of the 9 buffers stays allocated whether or not its fetcher has
ever run again. Non-starter.

### F2 — One shared, module-scope persistent `WiFiClientSecure` (reject — breaks A5)
Hoist a single `static WiFiClientSecure` into `dataTaskStorage.cpp`, used by
every one of the 9 call sites in turn (safe because dataTask fetches are
already serial). Fits the budget (one ~32-40 KB buffer, matching the
already-declared headroom). **Rejected as specified**: A5's checker
attributes a TLS bracket to an app by finding the *enclosing function* of
the `WiFiClientSecure` declaration (`dataTaskStorage.cpp:477-487`'s own
comment explains this was deliberately kept per-call-site for exactly this
reason). A single shared declaration collapses all 9 attributions into
whichever function happens to declare the shared object, which is silent
data loss in the conformance matrix, not a cosmetic issue — `check_app_conformance.py`
would need a second attribution mechanism (e.g. an explicit tag argument
per call, checked structurally instead of by declaration site). This is
real, scoped work, not a blocker in principle — but it is **specific to
sharing the object's declaration** (F2's shape), not to sharing the bytes
underneath it. F3 below shares only the backing storage, keeps each call
site's own `WiFiClientSecure tls;` declaration exactly as ADR-029/A5
require, and does not trip this checker at all — F2 is listed to show why
"just share the object" fails, not because F3 pays the same cost.

### F3 — Single shared mbedTLS arena via a task-identity-gated allocator hook (LEAN)
Revisit M-HEAP-FRAGMENTATION's Option C1, narrowed to dataTask's own
population: install a `mbedtls_platform_set_calloc_free` hook that, when called from
dataTask's own task context (`xTaskGetCurrentTaskHandle()` compared against
`dataTask`'s own stored handle — `dataTask.h`'s `g_taskHandle` equivalent;
**correction**: `tlsYield`/`tlsResume` (BP-031) do NOT use a task-identity
check — they coordinate via a semaphore + request-queue handshake
(`spotifyTaskStorage.cpp:685-730`), a different mechanism entirely, so this
design cannot borrow their pattern and must specify its own gate), serves
allocation requests from one persistent, pre-sized ~40 KB pool
instead of the general heap; every other caller (Spotify's own TLS,
anything outside dataTask) falls through to the real `calloc`/`free`
unchanged. Each of the 9 call sites keeps its own stack-local
`WiFiClientSecure` exactly as ADR-029 and A5 require — **the object's
declaration site is untouched, only where its internal buffer's bytes
physically come from changes**. Because the pool is a fixed, never-freed
address range, every fetch's mbedTLS buffer lands in the *same* bytes every
time — there is nothing left to carve-and-not-recoalesce, because nothing
is ever freed back to the general allocator in the first place.

**Why this wins over F1/F2:** it is the only option that is both
budget-feasible (one pool, sized from the already-declared headroom, not
per-fetcher) and A5-compatible (no change to declaration sites, no checker
rework). Its cost is exactly M-HEAP-FRAGMENTATION's original C1 objection —
a process-global mbedTLS hook — but paid against a much better-defined,
single-task, always-serial caller population than C1's original
Spotify-vs-WebRadio framing, which is what makes revisiting it now
defensible rather than repeating a decision already made.

### F4 — Do nothing; leave TASK-697 parked (status quo)
Always available. Costs ~22 Stock ids on an affected full run
(`tasks-harness2.md`'s own figure) and leaves the Phase-3 shuffle exception
(2026-09-17 ruling) open-ended rather than closable. No new risk.

## Lean / recommendation

**F3, gated on OQ1 first.** This design does not recommend starting
implementation immediately: F3's payoff (fixing dataTask's own churn)
is currently a *hypothesis* about TASK-697's cause, not a confirmed one
— no DUT session has isolated "dataTask fetches against each other" from
"something else" as the actual driver of the Stock-id regression, and
Revision 3's own evidence, read narrowly, only shows that a degenerate,
broken reservation helped one id while breaking several others. Spending
an mbedTLS-global-hook's worth of implementation risk (real, per ADR-047's
precedent) on an unconfirmed hypothesis would repeat the shape of mistake
Revision 3 already made once (see `task697-reboot-inject-stock.md`'s "two
of my published readings that the evidence later refuted").

## Open questions

- **OQ1 (confirm the hypothesis before building F3).** VE review (2026-09-17,
  [sibling review](M-DATATASK-tls-buffer-lifetime-VE-review.md), VE-1) found
  this named but not designed. Candidate protocol, reusing existing
  instrumentation rather than building anything new:
  `TLS_RESERVE_EXPERIMENT`'s boot-time reservation
  (`dataTaskStorage.cpp:310-380`, already built for Revision 3) held
  **permanently acquired for the whole run — no release/reacquire at any
  bracket** (sidestepping the exact mechanism Revision 3 already proved
  fails: reacquire-after-release was 8/8 RELEASED). This isolates dataTask's
  own churn cleanly: if the fragmentation is caused by dataTask's 9 sites
  repeatedly carving and freeing their own mbedTLS buffers, a single
  never-freed span should behave like F3's arena in miniature (same bytes
  reused implicitly, because nothing else can carve into the reserved span)
  and the Stock-id regression should clear; if it doesn't clear, churn is
  not the (or not the whole) mechanism and F3 is not worth building.
  Decision rule to pre-register before running: N reboots (N ≥ 8, matching
  Revision 3's own sample size) of the affected Stock-id sequence, permanent-reserve
  arm vs. unmodified control, compared as **failure sets**, not counts
  (per this programme's own working rule) — pre-register what counts as
  "cleared" (e.g. control's specific FAILs absent in ≥ 7/8 permanent-reserve
  runs) before the first run, not after. **Still new DUT time against a
  PARKED task and needs the human's sign-off to schedule — this design
  proposes the protocol, it does not authorize running it.**
- **OQ2 (interaction with a live Spotify session, once TASK-675 is fixed).**
  This design's evidence base (Revision 3) ran with no live Spotify TLS
  session. F3's task-identity gate is written to leave Spotify's own
  allocations untouched, so it should not need re-evaluation once TASK-675
  is fixed — but that is a claim to verify, not assume, once a real session
  exists again to test against.
- **OQ3 (blast radius of the allocator hook).** ADR-047 Amendment 1's
  objection to touching mbedTLS config was about *this exact toolchain's*
  conservatism (Arduino-ESP32 2.0.17, mirroring the ESP32-audioI2S v2.3.0
  pin/BP-042 precedent). A runtime hook is a smaller footprint than a
  compile-time config change, but it is still new surface in code this
  project has otherwise avoided touching. Needs its own review before
  acceptance, independent of OQ1's empirical question.
- **OQ4 (A5/A6 checker impact).** F3 as specified changes *where bytes come
  from*, not *which function declares the object* — confirm
  `check_app_conformance.py`'s A5 scan (an AST/text check on declaration
  sites, not a runtime trace) is genuinely unaffected before relying on
  that claim in review.

## Exit criteria

Not an implementation plan — this design's own exit criterion is a human
decision on whether to schedule OQ1's confirming experiment (new DUT time,
against a task the human parked) before any code lands. If OQ1 is not
scheduled, this design stays `proposed` and TASK-708 stays open with no
change to TASK-697's P2/parked status.

## Registers

None. No `feature_inventory.yaml` or `cross_feature_matrix.yaml` entries are
claimed — this is a proposal awaiting the OQ1 scheduling decision, not
committed work.
