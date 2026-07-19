# Design — M-HEAP-FRAGMENTATION: Spotify's permanent TLS heap ceiling starves WebRadio's station fetch

> Owner: Architect
> Status: **parked** (2026-07-19, human decision — none of Option E's
> variants appealed; not adopting now). Root-cause investigation and
> design-space survey stand as a reference if this fragmentation issue
> reoccurs or worsens; Option E is not scheduled and the `webradio-002`/
> `X038` registry reservations below were **not** committed (parking, not
> implementing, so no registry claim). A complementary/alternative angle —
> gating `spotifyTask::begin()` on `g_settings.playerMode` so Spotify's TLS
> never connects (and never fragments the heap) on a boot where the user's
> mode is WebRadio — is being explored separately; see
> `M-SPOTIFY-BOOT-GATE.md` (or whatever the Architect names it) once filed,
> not a supersession of this doc.
> Date: 2026-07-19
> Feeds: ADR-053 (parked, not proposed for adoption)
> Tracked-as: — (parked; not scheduled)
> Registers: — (parking, not implementing — no reservation claimed)

## Context / pain points

**Symptom.** WebRadio's background station-list fetch fails with `-101`
(`app/src/dataTaskStorage.cpp:1419-1426`, TASK-289's own defensive guard):
before attempting its HTTPS fetch, `fetchWebRadioStations()` checks
`heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)` against
`WR_FETCH_MIN_TLS_BLOCK = 40 * 1024` (`dataTaskStorage.cpp:769`) and refuses
the fetch — rather than risk crashing mid-TLS-handshake — if the largest
contiguous free block is smaller. Observed on the physical DUT as "no
stations."

**Root cause, confirmed by direct measurement (this session, `get heap`).**
The moment Spotify's persistent TLS/mbedTLS session first connects, it
allocates ~30-40 KB carved out of the *middle* of what was a pristine ~73 KB
contiguous free block (`lfbInt` / largest-free-block), permanently splitting
it into two smaller pieces (~43 KB + ~30 KB). Tearing the TLS session back
down frees the bytes — total free heap recovers, e.g. 78616 → 118740 — but
the split **never re-coalesces**: the largest contiguous block stays pinned
at ~42996 bytes (~43 KB) for the rest of the session, regardless of
Spotify's connect/disconnect cycling. That is only ~2 KB above WebRadio's
40960-byte guard, so any transient concurrent allocation (the fetch's own
5 KB parse doc, socket buffers, etc.) tips the largest block under the
guard's threshold and trips the skip. Reproduced on both debug and
production builds: the production heartbeat's `maxAlloc` drops from 83 K to
41 K the instant Spotify's TLS connects, and **stays there** — this is not a
momentary dip, it is a new permanent ceiling for the remainder of the boot.

This is significant against TASK-289's own design assumption. Its guard
comment (`dataTaskStorage.cpp:764-768`) was calibrated against a *different*
population: "every observed successful fetch ran with maxBlk ≥ 47 KB;
[during] WebRadio playback concurrently holding the heap ... maxBlk sits
≤ ~38 KB." That calibration run implicitly assumed a heap that fluctuates —
clean between playback sessions, tight during them — and the surrounding
code (`webRadioApp.h:1338`, "re-tried on the next resume() when the heap is
quiet again") explicitly bakes in a "wait for a quiet window" retry
strategy. **This investigation falsifies that assumption for the general
case**: once Spotify's TLS has connected even once, there is no quiet window
above ~43 KB for the rest of the session. Retrying later doesn't help,
because the ceiling isn't a transient dip, it's a floor that never moves
back up.

**Explicitly ruled out** (confirmed by direct measurement / source-reading
this session, not guessed — recorded here so a future reader doesn't
re-litigate it):
- This session's PlaneRadar work (`_ensureMotion()`, TASK-357, a one-time
  480-byte heap allocation) — an A/B test showed it changes the largest free
  block by exactly **0 bytes** (served from a small free-list bin, never
  carved from the large top block). Not a contributor.
- PlaneRadar's fetch not yielding Spotify's TLS — false; `fetchPlaneRadar()`
  calls `spotifyTask::tlsYield()`/`tlsResume()` around its handshake
  (`dataTaskStorage.cpp:1235`/`1272`, BP-031), same pattern as Crypto/
  Weather, confirmed both in source and empirically (opening PlaneRadar was
  observed to free Spotify's ~40 KB TLS session).
- Clock's TASK-354 delta engine — allocates zero heap (`clockApp.h` has no
  `new`/`malloc`/`calloc`).
- PlaneRadar's JSON parse buffer — static `.bss` overlay
  (`MEM_planeradar_doc`), not heap, contributes no heap churn by design.

So: this is a **pre-existing structural fragmentation ceiling from
Spotify's TLS allocator behavior**, present with or without any of this
session's other work, sitting dangerously close (only ~2 KB of margin) to
WebRadio's own safety guard.

### Why the existing `tlsYield`/`tlsResume` pattern doesn't already fix this

The project has a documented, previously-effective pattern for exactly this
class of problem: `spotifyTask::tlsYield()`/`tlsResume()` (BP-031), used by
Crypto, Weather, PlaneRadar, Geocode — **and already used by WebRadio's own
station fetch** (`dataTaskStorage.cpp:1380`/`1481`). It works for those
other fetchers because their problem is *transient contention* — Spotify's
TLS session competing for heap *right now*, freed by a stop-and-resume
around the critical section. WebRadio's fetch does exactly this and the
guard still trips, because **its problem is different in kind**: not "is
Spotify's TLS session live right now" but "has Spotify's TLS session *ever*
connected this boot." The fragmentation this design is about is a
side-effect of the connect, not of the connection being held — tearing the
connection down (which `tlsYield` does, and does correctly) doesn't undo the
side-effect. This is the answer to the question this task was framed
around: **WebRadio already does what Crypto/Weather/PlaneRadar do, and it
is insufficient for this specific failure**, not a gap in applying the
existing pattern.

### Existing infrastructure surveyed (what's already invested here)

- **`app/mem_manifest.yaml` / `app/gen/mem_layout.h` / M-MEMPLAN
  (`docs/architecture/designs/M-MEMPLAN-static-overlay-planner.md`).** A
  declarative, build-time-planned overlay system for *static* `.bss`
  buffers shared by mutually-exclusive apps. It explicitly does **not**
  cover this problem: the manifest's own `headroom.INTERNAL: 60000` line
  exists precisely to carve out budget for "transient heap the planner does
  NOT place (TLS, system)" — heap-resident TLS working sets are declared
  out of scope by design (`M-MEMPLAN-static-overlay-planner.md:45-46`, `§6`
  boundary: "the fetch's mbedtls TLS is not [placeable]"). The philosophy
  (declare, budget, gate the build) doesn't extend cleanly to this problem
  because the manifest plans *placement* of buffers whose lifetime and size
  are known at build time; a TLS handshake's internal mbedTLS allocations
  are neither owned by our code nor deterministically sized/placed — there
  is nothing for the planner to *place*. The planner already treats "TLS
  heap" as an opaque, unmanaged headroom tax, which is the correct
  boundary — this design doesn't try to move that boundary.
- **`app/src/mb_arena.h`, used by `app/src/webRadioApp.h`.** A fixed-slot
  free-list arena for the *audio decoder's* heap needs (24 KB,
  `MB_ARENA_BYTES`), JIT-acquired at `_play()` and released at `suspend()`
  (`mb_arena.h:15-33`). This **is** a structurally similar problem — a large
  contended heap allocation competing with other consumers — and its
  resolution (documented in ADR-047 Amendment 1) is the closest precedent:
  the fetch (needs ~40 K TLS, transient) and the decoder (needs 24 K arena,
  during playback) are **sequential and disjoint** — they never coexist —
  so the fix was to *sequence* them (JIT-reserve the arena only at
  `_play()`, never at boot) rather than to fight for space with both live.
  §Design space Option E below is the direct extension of this exact
  reasoning to the fetch-vs-Spotify problem.
- **`spotifyTask::tlsYield()`/`tlsResume()` and BP-031.** See above — solves
  transient contention, not a permanent side-effect. TASK-287's "5 layers"
  starvation-fix history (see project memory) hardened *this* mechanism
  against races and watchdog stalls; none of those fixes touch fragmentation
  because fragmentation was never the failure mode they were chasing.
- **ADR-029 (webradio-001, cleartext-media amendment), ADR-034 (streaming
  parse over buffered `String`), ADR-045/ADR-047 (no-PSRAM WebRadio memory
  viability).** All consistent with, and none contradicted by, this design.
  ADR-047 Amendment 1 in particular already rejected a global mbedTLS
  buffer-size shrink as "too broad a blast radius for a fetch-only problem"
  — the same objection applies to any allocator-hook approach considered
  below (see Option C1).

## Goals

1. Restore reliable WebRadio station-list availability on the production
   no-PSRAM board, given that Spotify's TLS connect creates a **permanent**
   ~43 KB ceiling for the rest of the boot (not a transient dip a retry can
   wait out).
2. Prefer a fix that **sidesteps** the ceiling structurally over one that
   fights it reactively — the human's explicit ask, and consistent with
   this project's own precedent (ADR-047 Amendment 1's sequencing
   argument).
3. Don't regress Spotify's boot/connect reliability or user-visible
   latency beyond what ADR-046's "connecting" bar already tolerates.
4. Don't reopen the mbedTLS-global-blast-radius risk ADR-047 already
   flagged, and don't weaken `WR_FETCH_MIN_TLS_BLOCK`'s crash-avoidance
   purpose.
5. Stay inside `mem_manifest.yaml`'s existing `headroom.INTERNAL: 60000`
   budget — this design should not need a bigger heap allowance, only a
   better-timed use of the one already budgeted.

## Design space (options + tradeoffs)

### A — Lower or adaptively compute `WR_FETCH_MIN_TLS_BLOCK`
**Reject.** The guard's entire purpose (per its own TASK-289 comment) is to
avoid attempting a TLS handshake that is `heap_caps`-doomed to fail with
`ssl_client (-32512) SSL - Memory allocation failed` mid-handshake — exactly
the failure ADR-045's "Wall 1" describes. Lowering the threshold doesn't
touch the fragmentation; it only changes the odds of trading a clean,
debuggable `-101` skip for an occasional in-handshake allocation failure.
That is a regression of the guard's safety property, not a fix of the
underlying problem. Not structural; rejected outright.

### B — Push `tlsYield` further: full `spotifyTask` teardown (M-RECLAIM Q3-b) around the fetch
M-RECLAIM (`docs/architecture/designs/M-RECLAIM-dynamic-resident.md`)
already designed, at sketch depth, a heavier option than today's
TLS-session-only stop: `vTaskDelete()` the whole `spotifyTask`, reclaiming
its ~10 KB stack in addition to the TLS session. Today's `tlsYield` is
already the Q3-a-equivalent (TLS-only stop) — and that's confirmed
*insufficient* by this session's own measurement: total free heap fully
recovers after `client.stop()` (78616 → 118740), proving nothing is still
*resident* in the freed TLS session's footprint, yet the largest block stays
split. That means the fragmentation is not caused by anything Q3-a leaves
resident — so there's no clear mechanism by which Q3-b's *additional* 10 KB
stack reclaim would un-split the specific hole left by the earlier TLS
alloc/free. It might still help incidentally (a different resident block
disappearing could shift the allocator's placement of subsequent
allocations enough to change which hole gets used) — but nothing in the
current evidence predicts that, and Q3-b carries real, already-documented
cost: a null-safety audit across every unconditional `spotifyTask::`
accessor (LL-085 family), reconnect latency on toggle-back, and it's a
heavier, permanent architectural commitment (task delete/recreate
lifecycle) for what may be zero marginal benefit here.
**Verdict: unproven, not free — worth a one-hour DUT spike (instrument a
debug `vTaskDelete` + re-measure `lfbInt`) before committing engineering,
but not a candidate to build speculatively.** Parked as an Open Question,
not the lean.

### C — Reserve/pre-allocate a dedicated block for WebRadio's own fetch
Two sub-variants surfaced by the "reserve a block up front" framing, evaluated separately because they mean different things:

**C1 — a real dedicated arena the TLS handshake allocates *into*** (mirroring
`mb_arena`'s free-list-arena pattern, but for mbedTLS's own internal
buffers instead of the audio decoder's). This is the only version of
"reserve a block" that would actually work mechanically, because merely
holding an unused block elsewhere doesn't change where mbedTLS's `calloc`
calls land (see C2). But `mb_arena`'s trick — patching the 3 call sites in
the vendored `ESP32-audioI2S`/Helix decoder — isn't available here: mbedTLS
allocates via `mbedtls_platform_set_calloc_free`, a **process-global** hook,
not a per-`WiFiClientSecure`-instance one. Redirecting it would affect
*every* TLS consumer (Spotify's own connections included), not just
WebRadio's fetch, unless additionally gated by a task-identity check inside
the hook (only divert when running on `dataTask` during the fetch window).
That's plausible in principle — the fetch and Spotify's TLS are already
temporally exclusive via `tlsYield` — but it is a nontrivial change to how
this firmware's mbedTLS integration works, on a toolchain (Arduino-ESP32
2.0.17) this project has been deliberately conservative about pinning
(the ESP32-audioI2S v2.3.0 pin/BP-042 is the closest analogue). ADR-047
Amendment 1 already rejected a *much smaller* mbedTLS-adjacent change
(shrinking `MBEDTLS_SSL_IN/OUT_CONTENT_LEN`) specifically because mbedTLS
config has global blast radius — the same objection applies here, more
severely, to hooking the allocator itself. **Verdict: mechanically the
"real" version of this idea, but high complexity and toolchain risk for a
problem this design can solve without touching mbedTLS at all (see Option
E). Flag as a longer-horizon R&D candidate if Option E ever proves
insufficient — not now.**

**C2 — reserve address space early so Spotify's later allocation is
"pushed out" of the block WebRadio needs.** This doesn't work with a
general-purpose allocator: holding a same-sized block *elsewhere* doesn't
constrain where an unrelated future allocation (Spotify's TLS session)
lands — the allocator places it wherever fits by its own policy, and the
specific 73 KB region that got split in the measured data isn't something
this scheme can steer around without already knowing the allocator's exact
placement decisions in advance. **Reject — unsound, doesn't address the
actual mechanism.**

### D — Something structural at the allocator/heap-region level
Researched, not assumed. ESP-IDF's heap component (`multi_heap`, TLSF-based)
**does** coalesce adjacent free blocks automatically on `free()` — that's
standard TLSF behavior. The fact that this *isn't* happening here (the
split survives a full `client.stop()` that recovers all the bytes) is
itself informative: it means the freed TLS allocation's neighbor isn't
simply "one adjacent free block" that a coalesce would merge — something
about IDF's segregated free-list bucketing, or the exact interleaving of
other small allocations around that address range, is leaving a durable
split. ESP-IDF's heap allocator has **no compaction/moving GC** — nothing
on this platform can relocate a live-or-freed allocation to defragment,
short of freeing literally everything on both sides of the hole. There is
no supported ESP-IDF flag or heap-caps API to opt into stronger coalescing
for this class of pattern. **Verdict: not a lever we have.** This also
explains *why* Option B (Q3-b) is unproven rather than confidently
rejected — deleting more resident state changes what's "on both sides of
the hole," which is the only kind of change that could plausibly move it,
but there's no principled way to predict the effect without measuring.

### E — Sequence the fetch to happen before the fragmentation can exist (LEAN)
Direct extension of ADR-047 Amendment 1's own reasoning ("the two big needs
are sequential and disjoint ... sequence so they never compete for the same
contiguous block") to this problem. Two parts:

1. **Cache-first UX.** Persist the station list to SPIFFS on every
   successful fetch (same mechanism already used for `wifi_creds.json` /
   `spotify_diy_config.json` / `settings.json`). Load the cached list
   immediately at WebRadio app entry — no network wait, no heap dependency
   — so the user always sees *a* list (possibly slightly stale) rather than
   "no stations." This alone fixes the user-visible symptom for the common
   case (a device that has ever successfully fetched once).
2. **Deterministic pristine-heap boot fetch.** Spotify's TLS session first
   forms shortly after `spotifyTask::begin()` (`main.cpp:2372`); before that
   call the heap is boot-fresh and has never been touched by the
   carve-and-split pattern this design is about. Move `dataTask::begin()`
   ahead of `spotifyTask::begin()` (it already sits only 11 lines later,
   `main.cpp:2383`, and depends only on WiFi being up, which it already is
   by that point in `setup()`) and insert a **bounded, one-shot** WebRadio
   station-list fetch (existing `enqueueWebRadioStations()` +
   `fetchWebRadioStations()` machinery, unchanged) between them, gated by a
   timeout (e.g. 8 s) so an offline or slow boot can't hang. This guarantees
   the session's single largest, most important fetch runs in the one
   heap window that's provably clean, deterministically — not
   probabilistically racing Spotify's own task-start timing.
3. **Rare mid-session re-fetch (country change / manual refresh) is
   unchanged** — still goes through today's `tlsYield`-protected path and
   `WR_FETCH_MIN_TLS_BLOCK` guard, best-effort as today. This is now a rare,
   explicit user action rather than the routine "every WebRadio entry"
   path, so an occasional skip here is a much smaller problem than "no
   stations, ever." (If DUT data later shows this path matters enough,
   Option B's Q3-b spike is the next lever to pull — deferred, not
   abandoned.)

**Why this wins over B/C/D:** it uses *zero* new mechanism — no allocator
hook, no arena, no mbedTLS surgery, no task-lifecycle risk. It's built
entirely out of infrastructure that already exists and is already trusted
(`dataTask`, `enqueueWebRadioStations`, SPIFFS persistence, `tlsYield` for
the residual rare path). Its only cost is boot-order coupling and a bounded
one-time latency addition to Spotify's connect — a cost class this project
has already decided is acceptable (ADR-046's "connecting" bar exists for
exactly this kind of latency, and boot already pays several seconds for
NTP+HTTPS-date sync ahead of this same code path). It is the only option
that doesn't ask "how do we get more out of a heap that's already broken" —
it removes the precondition (Spotify-has-already-connected) that breaks the
heap in the first place, for the one fetch that matters most.

## Lean / decision

**Adopt Option E.** Concretely: (1) SPIFFS-cache the station list on every
successful fetch, serve the cache immediately on WebRadio entry regardless
of fetch state; (2) reorder boot so a bounded, one-shot WebRadio
station-list prefetch runs after WiFi/`dataTask::begin()` but *before*
`spotifyTask::begin()`, refreshing the cache while the heap is still
boot-fresh; (3) leave the existing mid-session re-fetch path (`tlsYield` +
`WR_FETCH_MIN_TLS_BLOCK` guard) exactly as-is as the best-effort fallback
for the now-rare case of an explicit user-triggered re-fetch mid-session.

Explicitly **not** adopted now: Option A (rejected — undermines a safety
guard for no structural benefit), Option C2 (rejected — unsound mechanism),
Option D (not available on this platform). Option B (Q3-b) and Option C1
(dedicated mbedTLS arena) are **parked, not rejected** — real candidates if
DUT evidence after shipping Option E shows the residual mid-session
re-fetch path fails often enough to matter; both carry cost/risk that isn't
justified by the evidence in hand today.

## Open questions

- **OQ1 (boot latency bound).** What's the right timeout for the one-shot
  prefetch, and what's the actual measured added boot-to-Spotify-connect
  latency on a typical (not worst-case) network? Needs a DUT measurement,
  not a paper estimate; the "connecting" bar can absorb some of this but
  shouldn't be asked to absorb an unbounded amount.
- **OQ2 (dataTask reorder side effects).** Moving `dataTask::begin()` ahead
  of `spotifyTask::begin()` should be inert for the other four dataTask
  fetchers (Weather/Crypto/Stock/Teletext/PlaneRadar/Geocode are all
  Spotify-independent), but Developer should re-check against
  M-RECLAIM's Q2 sequencing notes (`M-RECLAIM-dynamic-resident.md` §Q2),
  which also touches `dataTask`'s boot lifecycle, before implementing.
- **OQ3 (cache staleness policy).** Is "always attempt a fresh boot-time
  fetch, silently fall back to the SPIFFS cache on failure/timeout" enough,
  or does the cache need an explicit max-age / manual-invalidate path?
  Leans toward the simpler policy — radio-browser's list changes slowly —
  but worth a explicit decision rather than an implicit one.
- **OQ4 (is Option B worth a cheap spike anyway).** A DUT A/B measuring
  `lfbInt` before/after a debug-triggered full `spotifyTask` teardown
  (Q3-b) is roughly an hour of work and would retire the "unproven" status
  in §Design space Option B either way. Worth doing opportunistically even
  though it's not gating Option E.
- **OQ5 (manifest headroom).** Confirm the boot-time-prefetch's demand
  (~40 K TLS + `WR_DOC_CAP` 5 K) still fits `mem_manifest.yaml`'s
  `headroom.INTERNAL: 60000` line — expected yes, since it's the same
  demand already budgeted for the existing runtime-placement fetch path,
  just moved earlier in time rather than enlarged; Developer to confirm at
  implementation.

## Exit criteria

- **DUT, ≥5 cold boots:** WebRadio station list has `count > 0` with no
  `-101` skip logged, sampled well into the session (after Spotify's TLS
  has provably connected/fragmented at least once) — proving the cache +
  boot-fetch path bypasses the ceiling rather than getting lucky.
- **DUT, ≥3 cold boots:** `lfbInt` captured immediately before
  `spotifyTask::begin()` is called, confirming it clears
  `WR_FETCH_MIN_TLS_BLOCK` with the same margin as the historical "clean
  fetch" population the guard's threshold was calibrated against
  (comment at `dataTaskStorage.cpp:764-768`: observed successful fetches
  ran with `maxBlk ≥ 47 KB`).
- **Regression check:** full serialdbg suite green on `cyd2usb_winamp`;
  boot-to-first-`currently-playing` latency delta measured and recorded
  (informational — only a hard gate if it becomes user-visible beyond
  ADR-046's existing "connecting" bar tolerance).
- `./run/check` 5-gate green; `mem_manifest.yaml`'s build-time budget
  assertion still passes unchanged (OQ5).

## Registers

**Parked 2026-07-19 — not claimed.** The reservation below was drafted at
design time per the usual `Registers:` protocol, but this design was parked
before reaching implementation, so it was **not** committed to
`feature_inventory.yaml`/`cross_feature_matrix.yaml` — `webradio-002` and
`X038` do not exist in the registry. Left here as a record of what *would*
be reserved if Option E is ever picked back up, not as a claim in effect.

Would-be new feature: **webradio-002** — "WebRadio station-list boot-time
prefetch + persistent SPIFFS cache" — pointer to this design doc. Distinct
from `webradio-001` (the existing dataTask-triggered-on-app-entry fetch,
which this design would extend rather than replace — the mid-session
re-fetch path would stay `webradio-001`'s as-is).

Would-be new cross-feature edge: **X038** — `webradio-002` × `poll-001`
(Spotify's currently-playing poll loop / `spotifyTask` boot start) —
`dependency`, `risk: medium` (boot-order coupling; `spotifyTask::begin()`
would be deferred until the bounded one-shot prefetch completes or times
out, changing Spotify's connect latency on every cold boot). Not added to
`cross_feature_matrix.yaml`.
