# Design — Heap-region instrument for TASK-697's 31k ceiling

> Owner: Architect
> Status: proposed
> Date: 2026-09-14
> Feeds: — (no ADR yet; this designs a probe, not a fix)
> Tracked-as: TASK-697
> Registers: —

**Revision 2026-09-14 (after @VE review, `M-DATATASK-heap-region-instrument-VE-review.md`,
ACCEPT WITH CHANGES):** folded in VE-1 (Gate 0, non-perturbation, required not asserted; stack/WDT
cost stated), VE-2 (capture point 0, before/after-per-region delta replaces the single-dump table),
VE-3 (parser: out of scope, named if ever needed), VE-4 (integrity-check framing narrowed; dataTask's
TWDT subscription confirmed absent), VE-5 (T089 enforcement named as a one-time manual test, not an
automated gate). Status stays `draft` — VE's verdict is "not yet ready to implement," which this
revision addresses but does not itself re-review. No change to Design space's option set or Lean's
conclusion (VE endorsed both); trimmed prose elsewhere to hold the line-budget.

## Context / pain points

TASK-697 (`docs/verification/regression_suite/task697-reboot-inject-stock.md`) narrowed to a
heap-fragmentation defect, now X068 in `cross_feature_matrix.yaml` (same failure class as X010:
TLS OOM at `maxAlloc` below a handshake's contiguous need, new trigger). Rate measured at 4/8 FAIL,
exact on `maxBlk`: FAIL tries land at **31k** after PlaneRadar's in-flight-fetch result is consumed
following an injection; PASS tries land at 33-43k. One code-derived candidate (the lazily allocated
`PrMotion[24]` table) is refuted (A/B: eager allocation still 5/8 FAIL). The open question is no
longer "which allocation" but **what kind of ceiling 31k is**:

- **(a) region span** — ESP32 internal RAM is several disjoint heaps (`soc_memory_regions[]`,
  `heap_memory_layout.h` (framework, line 49)); 31k could be what's left of *one* region after DRAM/IRAM/BSS claims
  it, other regions still holding more but not the one the fetch's buffers land in;
- **(b) mid-block survivor** — a large free span split by one small allocation that outlives the
  fetch's own buffers; candidate 1 was this shape and is refuted, but not the only such shape;
- **(c) something else** — a live allocation whose size happens to occupy the split point,
  corruption, or slow growth this small a sample can't see.

A probe run adding `get heap`/`get dataq` every second reproduced 0/4 — the probe itself perturbs
the timing that decides the outcome. The next evidence must be captured **from inside firmware, at
the moment of interest**, not polled from the host.

## Goals

1. Distinguish (a)/(b)/(c) from a same-try before/after capture at the 31k/33k+ split, **without
   changing whether the split occurs** — and *demonstrate* that, not assert it (VE-1).
2. Stay within IDF 4.4/Arduino-ESP32 2.0.17's actual public heap API (verified below).
3. Add no capture on any path that also builds without `SERIAL_DEBUG` (T089); additive-only on
   IFC-007.

## What the framework actually offers (verified against installed headers)

Headers: `~/.platformio/packages/framework-arduinoespressif32/tools/sdk/esp32/include/heap/include/`.
sdkconfig: `.../tools/sdk/esp32/sdkconfig` (all four QSPI variants agree on the lines below).

| Claim | Verified | Citation |
|---|---|---|
| `heap_caps_get_info(multi_heap_info_t*, caps)` returns one **aggregate** struct across *all* heaps sharing `caps` | yes | `esp_heap_caps.h` (framework, line 230); struct `multi_heap.h` (framework, line 169-177) |
| `heap_caps_print_heap_info(caps)` prints a two-line summary **per matching heap**, then a total — unlike `_get_info`, it doesn't merge | yes | `esp_heap_caps.h` (framework, line 233-243) doc comment |
| A public per-region **iterator returning structured data** (`heap_caps_walk` or equiv.) | **absent** in this IDF 4.4 header set (IDF 5.x addition) | grepped `esp_heap_caps.h`, `esp_heap_caps_init.h`, `heap_memory_layout.h`, `multi_heap.h` — no match |
| `heap_caps_check_integrity_all(bool print_errors)` | yes | `esp_heap_caps.h` (framework, line 257) |
| `heap_caps_dump(caps)`/`heap_caps_dump_all()` — full per-block dump | yes, not used further (Option A suffices) | `esp_heap_caps.h` (framework, line 367),377` |
| `soc_memory_regions[]`/`soc_memory_region_count` — static, compile-time region table | yes, labels addresses only, no runtime fragmentation data | `heap_memory_layout.h` (framework, line 49-50) |
| `CONFIG_HEAP_TRACING` | **off** — compiled to no-ops in the prebuilt library; needs a full IDF rebuild, out of scope | `sdkconfig:1192`; `esp_heap_trace.h` (framework, line 24-26) |
| `CONFIG_HEAP_POISONING` | **`LIGHT` on** (not off as assumed) — canary word per block, **no backtraces** | `sdkconfig:1189-1191` |

**Prior art**: `get heapHist` (`cmdGet.cpp` ~line 500) already uses these same aggregate calls
around a synthetic allocation sweep — answers a different question, not reused, but its shape (a
one-shot JSON snapshot on a console verb) is `get heapInfo`'s template below.

**Conclusion**: `heap_caps_get_info()` (one merged struct) and `heap_caps_print_heap_info()` (text,
one block per heap) are the two per-region views this build offers. Nothing gives a per-block
address/size list without `heap_caps_dump()`'s raw text or a rebuild for tracing.

## Design space

**(A) `heap_caps_print_heap_info(MALLOC_CAP_8BIT)` text dump.** Only call that preserves per-region
boundaries — load-bearing for (a) vs (b). Cost: 0 B new `.dram0.bss` (walks existing structures);
flash negligible (already linked via `heapHist`). Output large (one two-line block per matching
heap, ~4-6 on this chip after WiFi/LWIP claims) and unstructured — must go to `LOG_D`/raw serial,
not the JSON reply channel (`app/tools/lib/dut.py:1396` (`read_json`) discards non-`{` lines). No allocation, no yield.

**(B) `heap_caps_get_info()` JSON per capability class (INTERNAL, 8BIT, DMA), `LOG_HEAP`-shaped,
plus on-demand `get heapInfo`.** Cheap, parses cleanly, fits IFC-007 I3 — but aggregates by
definition (`esp_heap_caps.h` (framework, line 230)), so **cannot** separate (a) from (b) alone. `get heapInfo`'s
console cost: one `strcmp` branch + one `Serial.printf`, same shape as `get heap`/`get heapHist`.

**(C) Heap tracing.** Would answer (b) vs (c) directly (named allocations) but is **not feasible**:
`CONFIG_HEAP_TRACING_OFF=y` is baked into this framework's prebuilt `libheap.a`; the header itself
warns tracing calls are no-ops without the config bit. Ruled out — a library rebuild is out of this
doc's scope and disproportionate to the question.

**(D) `heap_caps_check_integrity_all(true)` at the capture points, as a supplement only.** Answers a
narrower question — is a block corrupted — not "too small for the handshake." With
`HEAP_POISONING_LIGHT` on, this is a real (if partial) corruption check: a clean result rules out
only (c)'s corruption sub-case, says nothing about (a) vs (b). Framed this way (not "for free" — see
VE-4), it's cheap to add alongside (A)/(B), silent on success so no steady-state log cost.

**(E) Cross-reference `soc_memory_regions[]` to label heaps by name/type.** Interpretation-time only,
layered on Option A's output when read (by a human — see Parser scope below); no new firmware state.

## Lean

**(A) + (B) together, (D) alongside, (E) at read-time.** (B) alone cannot tell (a) from (b) by
construction; (A) alone is expensive to read across 8+ regions and only earns its keep at the exact
moment under test, not as a steady-state log line. So: keep `LOG_HEAP` (Option B's shape, the
existing idiom, `dataTaskStorage.cpp:30-33`) always-on, and add (A)+(D) gated to fire **only** at the
three capture points below — bounded output, not every fetch. (C) is out: no rebuild.

**Decision rule — before/after delta, same heap, per @VE-2** (a single post-fetch dump can't tell
(a)/(b) from "already small"; the ~45k figure in X068/Context is the *aggregate* bracket, which by
(B)'s own aggregation argument can't stand for any one region):

| Observed, point 0 → point 1, same heap (identified by which heap's numbers moved) | Verdict |
|---|---|
| Already ≈31k at point 0 (no drop across the fetch) | not (a)/(b) as framed — pre-existing ceiling; escalate as (c) |
| Drops from ~45k range to 31k, and at point 1 `largest_free_block` ≈ `total_free_bytes` | **(a)** region span |
| Same drop, but `largest_free_block` well below `total_free_bytes` at point 1, `allocated_blocks` up vs point 0 | **(b)** mid-block survivor |
| `heap_caps_check_integrity_all` fails at point 1 or point 2 | **(c)** corruption — stop, file separately |
| No single heap's delta explains the aggregate drop | **(c)** unexplained — escalate per exit criterion 2 |

## Non-perturbation — Gate 0 (required, per VE-1; blocks reading Gate 1's content)

**Cost that must be bounded, not merely argued not-to-yield:**
- **Stack**: dataTask's own stack is `kStackBytes = 14 * 1024` (`dataTaskStorage.cpp:168`, the
  non-`WEBRADIO_ONLY` build — the one this instrument targets). `heap_caps_print_heap_info`'s
  formatting (~4-6 heap blocks × two lines) and `Serial.printf`/logSink call frames add stack depth
  on top of `fetchPlaneRadar`'s/`certSentinel`'s existing frames — not measured here (would need a
  build + `get stacks`, out of scope for a documents-only draft); Gate 0 is the check that catches
  an overrun or a race-shifting delay empirically, in place of a hand-estimate.
- **Time/WDT**: the calls themselves don't yield, but the logSink/UART transmission underneath
  `LOG_D` may still spend wall-clock time at the capture instant (VE-1). Separately: **dataTask is
  not TWDT-subscribed** — only `loopTask` and the CPU0 idle task call `esp_task_wdt_add`
  (`app/src/boot/boot.cpp:236-237`); grepped the tree for `esp_task_wdt_add`/`_subscribe`, no other
  call site. So a slow `heap_caps_check_integrity_all` walk over a fragmented pool (VE-4: it walks
  every block, slower exactly when the pool under test is fragmented) risks delaying dataTask's own
  fetch loop, not a watchdog trip.

**Protocol**: two builds, not a runtime toggle — a compile-time `#ifdef` with the calls **entirely
absent** in one binary vs **firing unconditionally** in the other (a `set`-gated runtime toggle
would still execute the calls and only suppress the print, which doesn't test the thing being
tested). Baseline: re-confirm or re-run the existing `T_PR_04,T_PRI_01,T170` 4/8, 8 tries, fresh
flash, `#ifdef`-absent build. Then the same command, 8 tries, fresh flash, instrumented build with
all three points firing unconditionally.

- FAIL try = `T170` fails AND `maxBlk=31k` at point 1 AND ≥1 `-32512` after it. PASS try = `T170`
  passes AND `maxBlk`≥33k at point 1 AND no `-32512`. Anything else: record, don't force a bucket.
- Instrumented FAIL rate ∈ {3,4,5}/8 (within one try of baseline) → non-perturbing, proceed.
- Instrumented FAIL rate ∈ {0,1,2,6,7,8}/8 → **perturbing. Stop.** Don't read content. Fallback
  (named now, not invented after a failed gate): move the print off dataTask onto a lower-priority
  task via a lock-free ring, or accept a documented "cannot observe non-invasively" verdict.
- At N=8/arm this has essentially no power to distinguish 4/8 from 3/8 or 5/8 — the tolerance band
  is one try wide on purpose. It catches gross perturbation (the 1 Hz-poll kind), not zero cost.

**Gate 1 (content read, only after Gate 0 passes)**: collect readable captures until 3 FAIL-side +
3 PASS-side are gathered or 8 tries exhausted (captures, not tries — an unreadable/ambiguous dump
doesn't count). N=3+3 per @VE, distinct from Gate 0's N=8 (rate-comparison needs power against the
7.1% flake background; content-reading a capture does not). Apply the delta table above per FAIL
try, comparing point 0 against point 1 for the same heap.

## Capture points

All under `SERIAL_DEBUG` only (T089).

0. **`app/src/dataTaskStorage.cpp`, `fetchPlaneRadar()`**, at the existing pre-fetch `LOG_HEAP` line
   (~1421, before `prFetchOnce`) — same gated pair, the same-try "before" half of the delta (VE-2).
1. **Same function**, after the existing post-fetch `LOG_HEAP` (~1537, after `s_planeRadarResult = r`
   is published, before `tlsResume()`) — the "after" half; the exact "result lands" moment.
2. **`certSentinel()`** (line 273), the shared wrapper every dataTask fetcher's `http.GET()` routes
   through (5 call sites) — gated pair on the branch returning the SSL OOM sentinel; unconditional
   trigger, no threshold to tune (-32512 *is* the failure, not a proxy).
3. **`get heapInfo`** in `cmdGet.cpp` (~line 530, alongside `get heap`/`get heapHist`) — Option B's
   per-class JSON, on demand, for bracketing a *sequence* between console commands. Not how the race
   is caught (that's points 0-2); this is for confirming steady state before/after.

All log via the existing `LOG_D`/`LOG_W` sink, reaching `RECORD_DIR`'s replay transcript and raw
serial the same way today's `LOG_HEAP` lines do.

**IFC-007**: `get heapInfo` is additive (I1), one JSON line (I3), not app-scoped (I5 inapplicable,
same class as `get heap`). `gate/check_get_keys.py`'s TASK-600 fix covers `cmdGet.cpp`-resident
`strcmp` keys, so the new key needs no gate change — confirm the new branch matches that shape.

**Parser (VE-3), explicitly out of scope**: point 0-2's text dumps are read by a human once per
gate-1 run, not machine-parsed — this design's exit criterion only needs a name for the mechanism,
not a shipped tool. If gate 1 needs more than one or two manual reads (PM's call once measured, not
pre-filed speculatively), a parser belongs in `app/tools/probe/` (one-shot host probe, per
`CLAUDE.md`), never `lib/` (would imply suite dependence) or an untagged `spike/` (the SPIKE gate
deletes it on archive). It would need its own negative test (BP-068): feed it a malformed/truncated
dump, assert "could not parse," never a silently-wrong region label.

**T089 enforcement (VE-5)**: `test_plan.md` T089 is a real test but a **one-time manual run**
(`strings firmware.elf | grep -c SERIAL_DEBUG`, "passed 2026-05-17") — grepped `smoke_test.sh` and
`gate/*.py` for `SERIAL_DEBUG`; no automated re-check exists in `run/check`'s 11 gates or its 49
host scripts today. This design adds no new symbol outside `#ifdef SERIAL_DEBUG`, same convention
every other console key already relies on, but the backstop is written discipline, not a gate.

## Open questions — resolved by @VE review; recorded for traceability

1. Sample size: **N=8 for Gate 0** (rate comparison, matches the existing baseline's power), **N=3
   FAIL + 3 PASS readable captures for Gate 1** (content reading, not a rate).
2. Both sides, every Gate-1 run: PASS-side captures are required (the delta table's FAIL-vs-PASS
   comparison depends on them).
3. Non-perturbation protocol: promoted to Gate 0, required before Gate 1's content is trusted;
   two separate builds (`#ifdef`-absent vs firing), not a runtime toggle.
4. Trigger: **unconditional** at all three points (agreed with the draft's own recommendation) — a
   firmware-baked threshold embeds a guess about the FAIL/PASS boundary that Gate 1 might move.

No open question for the human: this stays a probe (no fix proposed), within existing
SERIAL_DEBUG/IFC-007/T089 practice, and RAM cost is documented below pending re-derivation.

**RAM**: debug `.dram0.bss` headroom recorded at 7040 B as of the TASK-697 ring commit — re-derive
fresh from the debug `.map` before landing (per the standing project lesson that this number moves).
This design adds 0 B of new static state (no new globals; print/check/get-info calls use existing
library state and caller-stack scratch) — only flash for `get heapInfo` and the two gated points,
expected negligible against a RAM budget, but the re-derivation is still owed since it's the actual
gate, not this design's estimate.

## Exit criteria

1. All four capture points land, compiling clean under `SERIAL_DEBUG`, zero new symbols in the
   non-`SERIAL_DEBUG` build per the T089 convention above (no automated gate exists to check this;
   a manual `strings`/`grep -c` re-run is the closeout evidence until one does), `.dram0.bss`
   headroom re-derived and positive.
2. **Gate 0 passes** (instrumented FAIL rate within one try of the current 4/8 baseline) — required
   before Gate 1's content is read at all. A Gate 0 failure is itself a closeout: "cannot observe
   non-invasively with this instrument" is a valid, documented exit, not a blocker to escalate
   silently past.
3. **Gate 1** produces, for at least one FAIL-side and one PASS-side readable capture, a verdict of
   (a), (b), or (c) per the delta table — or a stated reason the instrument's output does not
   resolve it. Either outcome closes this design's job; a fix, if any, is a separate task.
