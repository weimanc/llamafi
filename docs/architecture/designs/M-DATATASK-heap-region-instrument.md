# Design — Heap-region instrument for TASK-697's 31k ceiling

> Owner: Architect
> Status: proposed
> Revision 2 was accepted by human sign-off 2026-09-14. @VE's final check on the symmetric-release
> spec found a capacity conflict (Spotify's persistent session + the reservation ≥ free heap); the
> human ruled a treatment change (design the Spotify-session-idle option) on 2026-09-14, changing
> Option 3's mechanism again — `Status` returns to `proposed` for fresh sign-off (see Revision 3).
> Date: 2026-09-14
> Feeds: — (no ADR yet; this designs a probe, not a fix)
> Tracked-as: TASK-697
> Registers: —

**Revision 2 2026-09-14 (after Gate 0 failure)** — the implemented instrument (`8af4a0a2`) ran its
pre-registered Gate 0 and **FAILED: perturbing**, harder than "the rate shifted." `Status` moves to
`proposed` (C4 vocabulary — a changed design needs fresh sign-off, not silent continuation under
`draft`). This revision: (1) separates measured evidence from reading, including a **directly
captured corruption mechanism** the original design didn't anticipate; (2) re-opens the option set
— dropping the integrity walk and moving the dump off dataTask are both evaluated against the new
evidence, not assumed to work; (3) adds Option 3, abandoning allocator-level observation in favour
of a reservation fix to the X010 family directly; (4) revises Gate 0/Gate 1/exit criteria.
Superseded content (the original Design space A-E, the original Lean, the original Gate 0/Gate 1)
is compressed below under "Revision 1, for history" rather than deleted, per template discipline.

## Revision 1, for history (compressed)

Distinguishing (a) region-span / (b) mid-block-survivor / (c) other for TASK-697's 31k ceiling
needs a per-region view. `heap_caps_get_info()` aggregates across all matching heaps by construction
(`esp_heap_caps.h` (framework, line 230)) and can't do this alone; `heap_caps_print_heap_info(MALLOC_CAP_8BIT)` is the
only public IDF-4.4 call that preserves per-heap boundaries, and it's a text dump, not JSON — no
`heap_caps_walk` exists in this header set (IDF 5.x only). Heap tracing is compiled out
(`CONFIG_HEAP_TRACING_OFF=y`). The lean was: keep `LOG_HEAP`'s aggregate bracket always-on, gate a
`heap_caps_print_heap_info` + `heap_caps_check_integrity_all` pair at three capture points (0:
before the PlaneRadar fetch, 1: after its result lands, 2: first `-32512` in `certSentinel`), and
require a **Gate 0** non-perturbation check (two builds — `#ifdef`-absent vs firing — 8-try FAIL
rate within one try of the un-instrumented 4/8 baseline) before trusting any content read at those
points (**Gate 1**, N=3 FAIL + 3 PASS readable captures, delta-based per @VE-2). Implemented as
designed in `8af4a0a2`: `heapRegionDump()` in `dataTaskStorage.cpp`, `get heapInfo` in `cmdGet.cpp`,
under `SERIAL_DEBUG && !HEAP_REGION_DUMP_OFF`. Full detail: `git show 8af4a0a2 -- app/src`.

## Gate 0 result, 2026-09-14 16:41-18:42 (`docs/verification/regression_suite/task697-reboot-inject-stock.md`, last section)

`run/test-targeted T_PR_04,T_PRI_01,T170`, 8 tries/arm, fresh flash per arm, OFF first.

| arm | FAIL | PASS | other |
|---|---|---|---|
| OFF (`-DHEAP_REGION_DUMP_OFF`) | 3 (signature exact: `maxBlk=31k` + 18×`-32512`) | 5 | 0 |
| ON (dump fires at points 0/1/2) | 2 | **0** | **6**: `T170` SKIP "could not switch to Stock" ×5, UNMET "no reply to `get quoteOkCount`" ×1 |

Instrumented FAIL rate (2/8) falls outside the pre-registered {3,4,5}/8 band → **perturbing per the
design's own rule. Gate 1 content not read** (57 `integrity=ok` markers recorded, uninterpreted).

## What Gate 0's failure mode tells us — evidenced vs. reading

**Evidenced (measured from the raw serial, `G0ON_1.log` through `G0ON_8.log` in the run's
`RECORD_DIR`/scratchpad):**

- **Timing.** Every `[heapreg] … begin`/`… end` marker pair was pulled and differenced across all 8
  ON logs (**55 pairs**, per @VE's independent recount — this doc's own first pass mis-tallied one).
  Span is **112-124 ms, mean 115.9 ms**, tightly clustered regardless of which
  point fired or the heap's fragmentation state at that instant. A theoretical UART-only estimate —
  `heap_caps_print_heap_info(MALLOC_CAP_8BIT)`'s ~9 registered-heap two-line blocks (confirmed 9 in
  the captured text: 8 small heaps + one 113 840 B region) plus totals, roughly 1.3-1.5 KB of text,
  at 115 200 baud (~11.5 KB/s ⇒ ~87 µs/byte) — lands at ~115-130 ms. The tight, state-independent
  clustering matches a **fixed transmission cost dominating**, not a variable-cost integrity walk
  (which should scale with live block count, and the pool is *more* fragmented, i.e. more blocks, in
  a FAIL try than a PASS try — no such spread is visible in the 112-124 ms range). Byte volume:
  1531 B measured between one real begin/end pair in `G0ON_1.log`, matching "~1.3-1.5 KB" at the
  high end, per @VE's independent check.
- **The actual corruption mechanism, captured directly.** `G0ON_1.log:615` and `G0ON_2.log:605`
  each show a `get appId` JSON reply **split by the heap dump's own concurrent output**:
  ```
      largest_free_block 0 alloc_blocks 42 free_blocks 0 total_blocks 4{"ok":true,"2
    ...(heap-dump lines continue)...
  cmd":"get","var":"appId","id":6,"name":"Stock","last":true}
  ```
  `total_blocks 42` is cut mid-digit, the reply's `{"ok":true,"` lands inside it, and `cmd":"get"…`
  reappears as an orphaned line with no leading `{` several lines later. This is **byte-level
  interleaving on the shared UART TX from two FreeRTOS tasks writing concurrently** (dataTask's
  `heapRegionDump()` mid-print; loopTask/console answering `get appId` at the same instant) — not a
  delayed-but-intact reply. `app/tools/lib/dut.py:1396` (`read_json()`, `if line.startswith("{")`)
  discards any line that doesn't start with
  `{`; a reply broken this way produces no valid line at all, which is exactly "could not switch to
  Stock" (the harness's `_appid_is` polls for a matching `get appId` reply and times out) and "no
  reply to `get quoteOkCount`" (same failure shape on a different key). Confirmed present in at
  least 2 of the 8 ON logs by direct inspection; not exhaustively checked against all 6 broken
  tries, but the two checked account for 2 of the 5 SKIPs plus the general shape matches all 6.

**Reading, not verified:** the design's Gate-0-failure fallback text speculated
`heap_caps_check_integrity_all()` "takes each heap's lock while it walks every block… stalls every
allocating task." **This could not be verified against source** — this PlatformIO framework ships
only `libheap.a` (prebuilt archive); no `heap_caps.c`/`multi_heap.c`/`multi_heap_poisoning.c` exists
anywhere under `~/.platformio/packages/framework-arduinoespressif32` (checked by `find`), so there is
no IDF 4.4 source to cite a lock-hold claim against. **It may also be the wrong mechanism to chase**:
the directly-observed corruption is explained by `Serial`/`printf` output interleaving, which
`heap_caps_print_heap_info()` alone (no integrity check at all) is equally capable of causing — it
does the actual writing to the shared UART; `heap_caps_check_integrity_all()` returns a bool and
writes nothing on success. The span data's state-independence further suggests the walk's own cost
(lock or not) is a minority contributor next to the print's transmission time. **This reframes the
fallback options below: dropping the integrity check trims some of the ~115.9 ms, but does not by
itself address the interleaving, because the interleaving's cause is the print, not the check.**

## Options

**(1) Drop the integrity walk; print only (`heap_caps_print_heap_info` alone).** Removes whatever
share of the ~115.9 ms and whatever share of task-stall risk the lock-hold reading (unverified) would
have contributed. **Does not address the observed interleaving** — the print itself is the writer
that corrupted the `appId` reply in both captured cases, and it's still ~1.3-1.5 KB of text on the
same UART TX either way. Distinguishes (a)/(b)/(c) exactly as before if it can be made
non-perturbing; loses (c)'s corruption sub-case (no integrity check to catch it). **Per @VE's
review (§2, "Challenging the Lean"): this option's likely outcome is another Gate-0 failure via the
new zero-corruption rule specifically, not the rate band** — the write path that corrupted
`appId`/`quoteOkCount` is `heap_caps_print_heap_info()` itself, present unchanged here. Agreed: this
is the correct reading of the evidence already in this doc. Still worth running — cheap, isolates
the integrity walk's own contribution as a control variable, and a second failure would be
confirmatory, not wasted — but re-ranked below from a co-equal track to a **free control run**.

**(2) Move the dump off dataTask.** The design's own pre-named fallback (a lower-priority task via a
lock-free ring). Per this design's own earlier verification, **`heap_caps_print_heap_info()` is the
only public per-region source in IDF 4.4 — there is no struct-returning per-heap snapshot call to
move instead.** So "moving the work off dataTask" can relocate *which task* calls
`heap_caps_print_heap_info()` and *when* (e.g., deferred a few hundred ms until console traffic is
believed quiet), but the print still ends up on the same physical UART either way — moving the
*caller* does not move the *wire*. It would reduce dataTask's own stack/priority exposure (a real,
separate cost from the interleaving) and could reduce interleaving *odds* if scheduled to avoid
windows where a console reply is likely in flight, but cannot *guarantee* avoidance without either
(a) a shared lock between the console's reply path and the dump's print path (a firmware change,
console internals currently uninvolved in this design), or (b) redirecting the dump's text to a
separate channel entirely (a second UART, or intercepting libc's `stdout`/`printf` sink to a RAM
buffer for the call's duration) — both are real code changes needing a Developer prototype, not
decidable from documents alone. **Flagged as a follow-up spike, not chosen here without evidence
that it closes Gate 0.**

**(3) Abandon allocator-level observation; address the X010 family directly.** Reserve or
pre-allocate a contiguous block sized for a TLS handshake's need (the existing `LOG_HEAP` comment at
`dataTaskStorage.cpp:29` puts this at "~50-70 k contiguous") before PlaneRadar's injection path can
fragment the pool around it, or otherwise guarantee one handshake-sized span survives — the X010
precedent (`heatmapPause()`/`heatmapResume()`, `cross_feature_matrix.yaml` X010) is a *release*
strategy for the same failure class; this would be a *reservation* strategy. **Evidence**: @VE's
pre-registered A/B, adopted verbatim — see "Adopted: Option 3 A/B" below (references
`M-DATATASK-heap-region-instrument-VE-review.md` §3 rather than restating it, so the two documents
cannot drift). **What a success would tell us**: the mechanism is addressable without naming it — a
practical close to X068/TASK-697's operational cost (the ~22-Stock-id full-run loss) even without
resolving (a)/(b)/(c). **What it would *not* tell us**: which of (a)/(b)/(c) was actually happening,
whether the fix generalises to X010's other triggers, whether the reservation is correctly sized
rather than oversized-and-accidentally-working, or whether it holds under other apps' concurrent RAM
pressure (VE §3, "What a success would NOT establish"). **Scope note**: a permanent reservation of
~40-50 KB is a real RAM-budget decision against `app/mem_manifest.yaml`'s `INTERNAL` ceiling
(290 000 B) and headroom (60 000 B, "~40 K mbedtls fetch context + margin") — this is bigger than a
probe and needs its own design/ADR if chosen, not a sub-bullet here. Named as an option, not designed.

**(4) Narrow the capability mask to reduce dump volume.** Considered and set aside: the captured
dumps show 9 registered heaps under `MALLOC_CAP_8BIT` already (8 small ones plus one 113 840 B
region) — this reflects the SoC's physical DRAM/IRAM-alias layout (`soc_memory_regions[]`,
`heap_memory_layout.h` (framework, line 49)), not an over-broad capability request. A narrower mask (e.g.
`MALLOC_CAP_INTERNAL` alone) would likely return most of the same heaps, since `8BIT` is already
close to `INTERNAL` on this chip. Not evaluated further — low expected payoff for the volume it
would cut.

**(5) Compact, single-write per-region line** (@VE's missing option, folded in). Instead of
`heap_caps_print_heap_info()`'s ~19 separate `Serial`/`printf` calls (one per dump line, ~1.5 KB),
pack only the load-bearing fields — per-heap `largest_free_block`, `total_free_bytes`,
`allocated_blocks` for the handful of 8BIT-capable heaps — into one short JSON-safe string and emit
it with a single write call. Cuts both byte count (~200-300 B vs ~1.5 KB) and, more importantly, the
*number* of separate UART write calls the console's reply write can land inside.

*Where the per-region numbers come from, verified against this build:* there is **no route that
avoids calling into `heap_caps_print_heap_info()`'s own machinery**. Capability masks (`MALLOC_CAP_*`)
select by capability class, not by physical region — the whole reason `heap_caps_get_info()` can't
separate (a) from (b) is that multiple disjoint regions share a capability class and are aggregated
together; there is no cap combination that isolates one region. `multi_heap_get_info(handle)` is
public and per-heap, but needs a `multi_heap_handle_t`, and **no public function returns the list of
registered heap handles** for iteration. Checked the non-public-symbol route directly: `nm` against
this build's `libheap.a`
(`~/.platformio/packages/framework-arduinoespressif32/tools/sdk/esp32/lib/libheap.a`) shows the one
per-heap iterator, `find_containing_heap`, as a **local symbol (`t`, not `T`)** — not exported, so it
cannot be `extern`-linked from firmware code outside its own translation unit. No other exported
symbol enumerates registered heaps. **The non-public-symbol route is unavailable, not merely risky.**

That leaves one route: capture `heap_caps_print_heap_info()`'s *own* text output — still internally
~19 calls, still walking the same data — into a buffer, parse the fields back out, and emit the
compact line once. This needs a `stdout`/UART redirection around the call (an `esp_vfs` swap or
equivalent) so those ~19 internal writes land off the wire instead of on it; not verified feasible
from documents alone, same Developer-spike gate as Option 2's redirection sub-approach.
**Refinement over @VE's framing**: VE separately flagged a "RAM-buffer-plus-deferred-atomic-emit"
idea as weaker than this option, on the grounds that buffering ~1.5 KB needs a fresh allocation at
the capture instant, self-referentially perturbing the fragmentation metric under investigation. On
inspection **that risk applies to option 5 too** — there is no way to get the per-region numbers
without capturing the print's own output, so option 5 *is* that buffering approach, not an
alternative to it. The self-referential risk is avoidable, but only by using a **static,
compile-time-reserved scratch buffer** (fixed `.dram0.bss` allocation sized to ~1.5-2 KB, costed once
against the design's RAM budget, never `malloc`'d at capture time) rather than a runtime heap
allocation — a scoping detail for whoever prototypes this, not yet a resolved design. With that
refinement, option 5 still needs the redirection mechanism (unverified) but avoids the
self-referential concern VE raised, which applies to a naive implementation but not a static-buffer
one.

## Lean

**Re-ranked per @VE's review, agreed.** Option 1's retry has a known-likely outcome (a second
Gate-0 failure via the corruption rule, not new information) — it is downgraded from a co-equal
track to a **free control run**, done in the same session as whichever primary option proceeds,
because it's cheap and isolates the integrity walk's own contribution regardless of outcome.
**Option 5 (compact single-write), refined with a static scratch buffer, is the stronger next
allocator-level attempt** — it attacks the evidenced mechanism (the *number* and *size* of writes
onto the shared UART) directly, where option 1 does not. It is not free: it needs a Developer
spike for the `stdout`/UART redirection before it can be claimed to close Gate 0, same gate option 2
was already held to. **Given TASK-697's already-measured cost and that this is now the second
inconclusive instrumented DUT session, the proportionate move is: run option 1 as a free control in
the same session as option 3's A/B (which needs no firmware change beyond the reservation itself),
and treat option 5 as a scoped follow-up spike, not committed to this session.** This does not
disagree with VE's ranking — it sequences it: option 5 costs Developer time before it costs DUT
time, so it does not compete with option 3's A/B for the same session.

## Adopted: revised Gate 0 (option 1's re-try only — verbatim from VE review §2/§4.1)

Same {3,4,5}/8 FAIL-rate band. **Adopting @VE's extension verbatim, not paraphrased** (review §4,
answer 1): the zero-corruption rule is **not** limited to tries that surface a recognisable
SKIP/UNMET — it requires a byte-level scan (an orphaned `{`/`}` fragment, or any raw-serial line not
matching a known emitted shape) across **all 8 ON-arm tries**, covering **every console round trip**
in the sequence (`set prRange`, `set prClearInject`, both `set prInjectAircraft`, and every trailing
`get`) — not just the two FAIL-shaped tries this session's own citation check happened to inspect. A
`set` reply corrupted the same way but still JSON-shaped would be a false green if the scan is
narrower than this. Builds: `#ifdef`-absent (OFF) vs. print-only, no integrity check (ON),
`-DHEAP_REGION_DUMP_OFF` retained as the OFF flag name. 8 tries/arm, fresh flash/arm.

## Adopted: Option 3 pre-registered A/B (verbatim from VE review §3)

Command, arms, decision rule (success = Arm A reproduces {3,4,5}/8 **and** Arm B reads 0/8;
inconclusive = Arm B reads 1-2/8, not reported as success at N=8; failure = Arm A reproduces the
band and Arm B reads ≥3/8 with the same signature; session invalid if Arm A does not reproduce the
band — stop, don't read B), and what a success would/would not establish: **as specified in
`M-DATATASK-heap-region-instrument-VE-review.md`, "Review of Revision 2" §3, adopted without
change.** Restated here only to the extent needed to sequence it (below); the review is the source
of truth for the rule set, so a future edit to one does not silently diverge from the other.

## Revised Gate 1 / exit criteria

Unchanged in shape from Revision 1 (N=3 FAIL + 3 PASS readable captures, same-heap before/after
delta table) **conditional on the adopted Gate 0 passing both the rate band and the zero-corruption
rule** (now scoped to all commands, all 8 ON-arm tries, per the adoption above). Per @VE's answer to
this doc's open question 2 (review §4.1, answer 2): a documents-only "not viable without a firmware
redirection" **is** an acceptable close for this design's exit criterion, **conditioned on naming
option 5 (and option 2's sub-approaches) explicitly as the named follow-up, handed to Developer as a
scoped spike** — not dropped quietly, since this is measured need, not speculative tooling ahead of
it. Either a Gate-1 mechanism verdict, or a Gate-0-failure-plus-Option-3-A/B-result (per its own
decision rule above), closes this design's job; a production fix, if Option 3 is pursued past the
A/B, is a separate task/ADR per its scope note.

## Capture points

0/1/2 as implemented in `8af4a0a2` (`fetchPlaneRadar()` pre/post, `certSentinel()` first `-32512`),
`get heapInfo` in `cmdGet.cpp`. If option 1 is re-gated and passes, no code change to the capture
sites — only `HEAP_REGION_DUMP_OFF`'s companion (the integrity-check call) is dropped from the ON
build for the re-run. Option 5, if spiked, replaces `heapRegionDump()`'s body at the same three
sites with the redirect-capture-and-compact-emit sequence — same call sites, different
implementation. Option 3 needs no capture points at all (no observation, a reservation guarantee)
and no code change to this file's capture sites.

## Sequencing and human decisions

Session sequencing is fixed by the design above: option 1's control run costs nothing beyond a
build flag and rides in the same DUT session as whichever primary option is chosen; option 5 needs a
Developer spike (code, not DUT time) before it can occupy a session at all; option 3's A/B is ready
to run as soon as a reservation is implemented. **Proposed order**: (i) implement Option 3's
reservation (small, scoped change, no diagnostic-instrument risk); (ii) one DUT session running
Option 3's Arm A + Arm B back-to-back, with Option 1's control folded into the same session if a
rebuild is cheap enough to include it; (iii) only if Option 3 is inconclusive or fails, spike Option
5 and gate it in a later session. This is a proposal, not a decision — three items below are the
human's to set, not this design's:

1. **Option 3's reservation scope.** Size/placement are a real `app/mem_manifest.yaml` budget
   decision against the `INTERNAL` ceiling/headroom — not this design's to set.
   **HUMAN RULING, 2026-09-14**: reservation first — Option 3's pre-registered A/B, with print-only
   Option 1 folded in as a free control **only if the rebuild is cheap**. Scope is
   **EXPERIMENT-ONLY**: debug build, behind a compile-time flag, **no `mem_manifest.yaml` change**.
   A real sizing decision/ADR is only warranted if the A/B succeeds.
2. **Sequencing.** One board — sessions are necessarily sequential.
   **HUMAN RULING, 2026-09-14**: proposed order confirmed as stated above — Option 3's reservation
   implemented, one session running Arm A then Arm B (+ Option 1's control if cheap), Option 5 held.
3. **A DUT-time budget / stopping condition for TASK-697.**
   **HUMAN RULING, 2026-09-14**: **this is TASK-697's last session.** If the reservation A/B is not
   a clear 0/8 success (per the adopted decision rule above — 1-2/8 is INCONCLUSIVE, not a partial
   win), **TASK-697 is downgraded to P2 and parked**, same disposition as the `TASK-393` precedent.
4. **Spotify capacity conflict (@VE's final check on symmetric release).** Holding a 40 KB
   reservation *and* Spotify's own persistent session simultaneously can exceed free heap regardless
   of placement — not a tuning problem, a capacity one.
   **HUMAN RULING, 2026-09-14**: design the Spotify-session-idle option now (Spotify stops its TLS
   client when idle instead of holding a session between polls), A/B'd on the TASK-697 sequence,
   poll-latency cost measured. Ruling 3 (last session; not clear → P2) still stands. **See "Revision
   3 — premise check" below: this ruling's premise does not hold for the failing scenario as
   observed** — reported before further design, per the coordinator's instruction.

## Revision 3 — premise check against evidence, before designing the Spotify-session option

@VE's capacity-conflict finding assumes Spotify holds a persistent TLS session between polls
("Spotify's own client is admitted to need ~50 KB contiguous... a persistent 40 KB hold leaves
Spotify roughly ≈15 k when it already has a session live"). @VE separately found `client.stop()`
fires on `doPoll()`'s and `doFetchQueue()`'s own failure paths (`spotifyTaskStorage.cpp` ~314, ~247).
TASK-675 (deferred) means Spotify's token refresh fails `-9984` at every boot — so the premise
("a session live") needed checking against the actual failing runs, not assumed from the general
case. Checked directly: for every try, all `[D][spotify.poll]`/`[D][spotify.queue]` lines in the
window from `T_PR_04`'s reboot to `T170`'s completion, specifically whether any poll or queue call
ever returned `200`/`204` (a real success, `spotify.poll] ok`/`"204 no track"`) — the only way a
session stays open past one cycle, since every non-success branch calls `client.stop()`.

| try | verdict (L697) | any Spotify 200/204 in the window? |
|---|---|---|
| 1 | FAIL | **no** |
| 4 | FAIL | **no** |
| 5 | FAIL | **no** |
| 8 | FAIL | **no** |
| 2 | PASS | **no** |
| 3 | PASS | **no** |
| 6 | PASS | **no** |
| 7 | PASS | **no** |

Zero occurrences of `spotify.poll] ok`/`"204 no track"` across all 8 `L697_*.log` tries — confirmed
by direct grep (`grep -c`), not sampling. Every poll fails `-1` (`HTTPC_CONNECTION_REFUSED` while the
pool is intact, `-32512` once it's fragmented), and every failure branch calls `client.stop()`
(`spotifyTaskStorage.cpp:314`/`:247`, confirmed present on every failing GET in the logs). Re-checked
against all 8 `G0OFF_*.log` tries (Gate 0's un-instrumented control arm, same sequence, different
session) — **also zero** successes. **16 of 16 tries checked show no live Spotify session at any
point in the `T_PR_04`→`T170` window.**

**Finding (i): the capacity conflict does not apply to the failing scenario as observed.** Spotify
never successfully holds a session in this window in any of the 16 tries checked — TASK-675's
`-9984` failure means every attempted refresh fails before a session could be established, regardless
of heap state. The 40 KB-reservation-plus-persistent-Spotify-session capacity conflict @VE found is
real in general (and would matter once TASK-675 is fixed), but it is not present in the sequence this
A/B actually runs. **This reopens the original, non-symmetric reservation (dataTask-only, Spotify not
touched) as a clean treatment for this specific scenario** — there is no persistent Spotify session
for a dataTask-favouring hold to squeeze.

**Finding (ii): "close Spotify's session when idle" would change nothing in the failing scenario.**
The session is already closed — every poll's failure path already calls `client.stop()`, in every
try checked. An idle-close mechanism has no session to close in this window; it cannot move `T170`'s
FAIL rate one way or the other here, because the state it changes (persistent session → closed when
idle) is not the state this scenario is ever in.

**Consequence for this design**: designing the Spotify-session-idle mechanism per the human's ruling
would build a treatment aimed at a condition this specific A/B does not exercise. The
`Option 3 experiment specification` below is therefore **reverted to the dataTask-only reservation**
(Revision 2's original scope, before the symmetric-release fix) rather than extended to Spotify's
client — consistent with finding (i). This is put to the coordinator/human before proceeding further,
per instruction; if TASK-675 is ever fixed (or Spotify's polling is otherwise made to succeed), the
capacity conflict and the idle-close mechanism both become live questions again, but not for this
session's A/B.

## Option 3 experiment specification

Named, not designed, until now. This is the mechanism the Developer builds against; EXPERIMENT-ONLY
per the ruling above — no `mem_manifest.yaml` entry, debug build only.

- **Flag**: `-DTLS_RESERVE_EXPERIMENT`, debug env only, same `PLATFORMIO_BUILD_FLAGS` mechanism as
  Gate 0's `-DHEAP_REGION_DUMP_OFF` (opposite polarity: absent = today's behaviour, present = the
  reservation compiles in).
- **Size: 40 KB.** Derived from the evidence on record, not the `LOG_HEAP` comment's "~50-70 k"
  alone: the FAIL/PASS boundary sits at `maxBlk`=31k (FAIL, every time) vs. ≥33k (PASS, observed
  33/37/39/43k) — a real handshake has been observed to *succeed* at 33k, well under the comment's
  conservative 50-70k. 40 KB clears the empirical 33k floor with margin, without reaching for the
  unverified upper estimate, and matches `mem_manifest.yaml`'s own existing "~40 K mbedtls fetch
  context + margin" headroom note — reusing a number this project already treats as the right order
  of magnitude for one TLS context, not inventing a new one.
- **When acquired**: `dataTask::begin()` (`dataTaskStorage.cpp`, right after `xQueueCreate`
  succeeds, before `xTaskCreatePinnedToCore`) — before the dataTask loop, and therefore every
  fetcher and every console-driven injection, can run at all. Nothing that could fragment the pool
  has executed yet at this point in boot.
- **Release/re-acquire choke point — corrected per @VE's re-check.** `spotifyTask::tlsYield()` /
  `tlsResume()` are **not** a single choke point to hook inside of: verified by grep that they have
  callers beyond the 9 dataTask fetchers — `app/src/audio/audioEngine.cpp` (`aeConnectFile`/
  `aeStopFile`/`aeDrainEof`, WebRadio local-file playback, line ~437 `TlsYieldGuard g(...)`) and
  `app/src/apps/webRadioApp.cpp` (its own `TlsYieldGuard _tlsGuard`, WebRadio-vs-Spotify TLS
  coexistence). Baking the reserve/release into `tlsYield()`/`tlsResume()` (or into `TlsYieldGuard`'s
  ctor/dtor) would silently reach those unrelated call sites too. **Instead**: a shared helper
  function implements the reserve/release logic once, called explicitly at each of 9 dataTask call
  sites, using two patterns (per @VE's direct verification, not assumed uniform):
  - **8 RAII fetchers** — `fetchWeather` (478), `fetchCrypto` (518), `fetchStockQuote` (576),
    `fetchStockChartWithRetry` (732), `fetchTeletext` (811), `fetchHeatmapQuote` (1073),
    `fetchGeocode` (1643), `fetchWebRadioStations` (1713), each declaring
    `spotifyTask::TlsYieldGuard tlsGuard;` — insert the release call on the line right after
    `tlsGuard`'s declaration, and the re-acquire call right before the guard's scope closes (the
    function's return points), not inside `TlsYieldGuard` itself.
  - **`fetchPlaneRadar`, the one manual pair** (no RAII guard): release right after
    `spotifyTask::tlsYield();` (`dataTaskStorage.cpp:1493`), re-acquire right before
    `spotifyTask::tlsResume();` (`:1604`). No early return sits between the two (checked), so a
    hand-written pair is as safe as the RAII fetchers' automatic one.
- **Spotify's own client — NOT covered, reverted per Revision 3's premise check.** The symmetric-
  release fix below (§ Spotify confound fix) is superseded: 16/16 checked tries show Spotify never
  holds a live session in the `T_PR_04`→`T170` window this A/B runs (TASK-675's `-9984` fails every
  refresh attempt before a session forms), so there is nothing for a dataTask-favouring hold to
  squeeze *in this scenario*, and no reservation-side mechanism is needed on Spotify's call sites for
  this experiment. Only the 9 dataTask call sites above are wired.
- **Re-acquire failure**: log once (`LOG_W`), continue. Never block a task's own loop waiting for
  the reservation to come back — a failed re-acquire degrades that one try back to today's
  unprotected behaviour, it must not wedge dataTask's fetch queue or spotifyTask's poll cadence.
- **Why the released span should get claimed by the handshake — reasoning, marked unverified,
  corrected per @VE (good-fit, not best-fit)**: ESP-IDF's heap component is TLSF-based — a
  segregated-fit allocator that picks from the smallest non-empty size class that still fits the
  request (a *good-fit* approximation), not literal best-fit, and does not guarantee the single
  largest free span is where a 40 KB+ request lands if other size-class-eligible blocks exist. This
  weakens the causal story without weakening the A/B: a success shows the reservation changes the
  outcome, not that it does so via this specific placement mechanism. Not verified against source (no
  `.c` sources ship in this framework, per the earlier `find` check).
- **Instrumentation and non-engagement, adopted from @VE's re-check by reference (not previously
  adopted — corrected mis-citation)**: one `LOG_D` line per release and per re-acquire (`ok`,
  timestamp). Per `M-DATATASK-heap-region-instrument-VE-review.md`, "Re-check of the Option 3 spec"
  §1(b): a try whose log shows the reservation was never acquired at boot, or released but not
  successfully re-acquired before the measured fetch, is excluded from that arm's count (recorded,
  not forced into PASS/FAIL). **New condition**: if **3 or more of Arm B's 8 tries** are excluded
  this way, the arm is **invalid, not merely smaller** — re-run Arm B in full (fresh flash) before
  reading it; a silently-shrunk N must not be reported as the clear 0/8 the human's ruling requires.

### Spotify confound fix — SUPERSEDED by Revision 3's premise check, kept for history

Designed to fix a capacity conflict (a persistent 40 KB hold squeezing a live Spotify session) by
extending the release/re-acquire bracket to Spotify's own two call sites in `spotifyTaskStorage.cpp`
(`doPoll()` before `s_spotify->getCurrentlyPlaying(...)` ~253, `doFetchQueue()` before
`s_spotify->getQueue(...)` ~239), chosen over holding-only-while-idle (inverts protection during the
injection window) and a smaller reservation (re-opens Gate 0's timing-precision problem). **Not
needed for this A/B**: Revision 3 found Spotify never holds a live session in the failing sequence at
all (TASK-675), so there is no squeeze to fix here. Retained as a design if TASK-675 is ever fixed and
Spotify's polling starts succeeding during this sequence — not wired for the current experiment.

**@VE's Spotify-`-32512`-per-try count is kept anyway, as a cheap sanity check, not a confound fix**:
count `after -1: rc=-32512` occurrences per try in both arms. Expected near-zero in both arms per
Revision 3's finding (no live session means little exposure either way); a non-trivial count in
either arm would itself be worth a second look, since it would mean this scenario's Spotify behaviour
changed between when Revision 3's evidence was gathered and when the A/B runs.

## Arm build commands

Same mechanism as Gate 0, `PLATFORMIO_BUILD_FLAGS`, Arm A run first per the adopted decision rule
(§"Adopted: Option 3 pre-registered A/B" — don't read B if A doesn't reproduce {3,4,5}/8):

```sh
# Arm A (control, no reservation) — run first
PLATFORMIO_BUILD_FLAGS= ./run/flash-debug
LOG_FILE=<path> ./run/test-targeted T_PR_04,T_PRI_01,T170   # x8, fresh flash

# Arm B (reservation in place) — only after Arm A reproduces {3,4,5}/8
PLATFORMIO_BUILD_FLAGS=-DTLS_RESERVE_EXPERIMENT ./run/flash-debug
LOG_FILE=<path> ./run/test-targeted T_PR_04,T_PRI_01,T170   # x8, fresh flash
```
