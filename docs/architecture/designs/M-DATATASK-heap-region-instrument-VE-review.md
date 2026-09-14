# VE Review — Heap-region instrument for TASK-697's 31k ceiling

> Owner: VE · Date: 2026-09-14 · Reviewed at commit 75f741b8 (draft under review: `Status: draft`,
> `docs/architecture/designs/M-DATATASK-heap-region-instrument.md`, Date: 2026-09-14)
> Scope: TESTABILITY review, same posture as `sys-reboot-wifi-multi-VE-review.md` — is the design's
> exit criterion agent/harness-executable, does it expose the right observables, does the design risk
> perturbing the exact race it exists to read. Documents only: no code, builds, serial port, flashing,
> commits, or task-board edits performed for this review.
> Findings labelled VE-<n>, classified blocker/major/minor, each with a proposed resolution.

Evidence read in full: `task697-reboot-inject-stock.md` (all sections, incl. the CORRECTION and the
4/8-FAIL / 0/4-perturbed / 5/8-refuted results), `task575-timeout-audit-and-criterion.md` §4
(pre-registration discipline this review mirrors), the draft design in full.

## Code-claim check

The draft's central move — Option B (`heap_caps_get_info`) can't separate (a) from (b) because it's
defined to aggregate every matching heap (`esp_heap_caps.h` (framework, line 230)), so Option A's per-heap text is load-
bearing — is internally consistent given that citation. `task697-...md`'s own last section already
asks for exactly this instrument, so the draft is responsive to a prior VE ask, not inventing scope.
The 4/8 and 0/4 numbers in the draft's Context match `task697-...md` verbatim.

## VE-1 (blocker) — perturbation risk is asserted, not bounded

Goal 1 is "without changing whether the split occurs." The design's own `0/4` result is a 1 Hz console
poll perturbing the race; this design adds two synchronous, non-yielding library calls at the same
kind of sensitive instant and argues from "doesn't yield" that it's safe. That's plausible but
unmeasured — and this investigation already has one refuted plausible-looking theory (`PrMotion[24]`
eager alloc, 5/8) on record. Two specific vectors the design doesn't quantify: **stack cost** (the
print formats ~6-10 lines on dataTask's own stack, a different budget than the `.dram0.bss` the RAM
section checks) and **UART time cost** (`Serial.printf`/logSink transmission of that text at the
capture instant — the *call* doesn't yield but the sink underneath it may still spend wall-clock time
at exactly the moment that decides the outcome).

**Resolution:** promote open question 3's two-step protocol from optional to required, with a stated
tolerance — folded into §2 (gate 0) below. If gate 0 fails, Goal 1 is not met and the instrument needs
revising (candidate fallback: move the print off dataTask onto a lower-priority task via a lock-free
ring — name this now as the fallback, don't invent it after a failed gate).

## VE-2 (major) — no same-try pre-fetch baseline; a single post-fetch dump can't separate (a)/(b) from "already small"

The decision-rule table reads the FAIL-side dump alone against a threshold. But (a) and (b) are both
consistent with that same single dump if the region was already near 31k **before** the fetch started
— the "~45k before" figure the draft's Context and `cross_feature_matrix.yaml` X068 cite comes from
the *aggregate* `LOG_HEAP` bracket, which by the draft's own aggregation argument cannot represent any
one region. Without a per-region "before" capture in the *same try*, a clean-looking (a) reading could
just mean the region was always that size.

**Resolution:** add capture point 0 — the same gated pair, at the existing pre-fetch `LOG_HEAP` line
(`~1421`, before `prFetchOnce`). No new mechanism, one more call site. Turns the table into a same-try
before/after per-region delta, not a single snapshot.

## VE-3 (major) — no named parser for the text dump

`heap_caps_print_heap_info()` output is unstructured, routed to `LOG_D`/raw serial because
`app/tools/lib/dut.py:1396` (`read_json`) discards non-`{` lines — the draft says so but names no scraper, implicitly assuming a
human eyeballs it once per run. That's fine for this design's own scope (a diagnostic close-out, not a
shipped tool) but should be said, not left implicit. If a parser is later written (worth it once past
the first hand-read, since RECORD_DIR already captures the transcript), it belongs in
`app/tools/probe/` (one-shot host probe against a live/recorded artifact — `CLAUDE.md`'s stated
purpose), not `lib/` (would wrongly imply other suites depend on it) or `spike/` unless explicitly
TASK-697-tagged (the SPIKE gate deletes it once TASK-697 archives). It would need its own negative
test per BP-068 (feed it a malformed/mid-reboot-truncated dump, assert "could not parse," never a
silently-wrong region label).

**Resolution:** add one paragraph naming this, explicitly out of this design's exit criteria (a human
reading is sufficient to close TASK-697's diagnostic question).

## VE-4 (minor) — integrity-check framing and dataTask WDT exposure

`CONFIG_HEAP_POISONING_LIGHT` catches out-of-bounds writes, not "block too small for the handshake" —
a clean integrity result rules out (c)'s corruption sub-case only, says nothing about (a) vs (b). The
decision-rule table already gets this right; the prose elsewhere ("answers the corruption sub-
question... for free") reads slightly stronger than that. Separately: `heap_caps_check_integrity_all`
walks every block in every matching heap, and walks a *fragmented* pool more slowly than a healthy
one — exactly the state under test, stacked on top of VE-1's already-unquantified cost, on dataTask,
at the worst-case moment for a watchdog trip if dataTask is TWDT-subscribed (this project has a
recorded history of TWDT-adjacent failures; the draft doesn't say either way).

**Resolution:** confirm dataTask's TWDT subscription before landing (one line); if subscribed, feed
the watchdog around the gated pair or move it earlier.

## VE-5 (minor) — T089 exclusion claimed, enforcement mechanism uncited

"Zero symbols in production" is a stronger, more specific claim than "compiles clean under an
`#ifdef` guard" (a stray unguarded reference could still compile). The design should name which
existing gate (if any) verifies symbol-level absence on the production ELF, or say plainly that T089
is currently a written convention with no automated backstop.

**Resolution:** one line citing the gate, or the absence of one.

## Answers to the design's open questions

1. **Sample size — not 8.** 8 was right for *comparing a rate* (candidate-1's A/B) against this
   project's measured 7.1% flake background. Reading a capture's *content* is different: propose
   **N=3 FAIL-side + 3 PASS-side readable captures** (captures, not tries — an unreadable/ambiguous
   dump doesn't count and the loop continues), with VE-1's non-perturbation check run first at N=8 to
   match the existing baseline.
2. **Both sides, every run.** PASS-side captures are required — VE-2's same-try delta and the
   decision table's cross-try PASS-vs-FAIL comparison both depend on them.
3. **Confirm the two-step protocol, with a stated tolerance** — promoted to blocker-resolution under
   VE-1; see gate 0 below. Implement "silent" as a compile-time `#ifdef` producing two binaries (calls
   entirely absent vs. firing), not a runtime `set` toggle that still executes the calls and only
   suppresses the print — that wouldn't test the thing being tested.
4. **Unconditional**, agree with the design's own recommendation: a firmware-baked threshold embeds a
   guess about the FAIL/PASS boundary that a rebuild would be needed to correct if VE-2's added
   baseline moves it. Volume stays bounded regardless (at most 3 capture points per try).

## §2 — Pre-registered experiment (TASK-575 §4 discipline: fixed before any run)

**Gate 0 — non-perturbation (must PASS before gate 1 is read).** Baseline: re-confirm the existing
4/8 baseline is current (same firmware lineage, no intervening dataTask/PlaneRadar/certSentinel
changes) or re-run it fresh: `LOG_FILE=<path> ./run/test-targeted T_PR_04,T_PRI_01,T170`, 8 tries,
fresh flash, `#ifdef`-absent debug build. Then: same command, 8 tries, fresh flash, the instrumented
build with all three gated points (0, 1/result-lands, 2/certSentinel) firing unconditionally.

FAIL try = `T170` fails AND `maxBlk=31k` at point 1 AND ≥1 `-32512` after it. PASS try = `T170`
passes AND `maxBlk`≥33k at point 1 AND no `-32512`. Anything else is neither — record it, don't force
a bucket, don't count it toward either rate.

- Instrumented FAIL rate ∈ {3,4,5}/8 (within one try of baseline) → **non-perturbing, proceed to
  gate 1.**
- Instrumented FAIL rate ∈ {0,1,2,6,7,8}/8 → **perturbing. Stop.** Don't read gate-1 content — a
  shifted rate means a different or absent race. Escalate per VE-1 (move the print off dataTask, or
  accept a documented "cannot observe non-invasively" verdict).
- Honest statistics: at N=8/arm this has essentially no power to distinguish 4/8 from 3/8 or 5/8 —
  that's why the tolerance band is one try wide. It catches a gross perturbation (the kind the 1 Hz
  poll produced) but does not certify zero cost. State this in the writeup.

**Gate 1 — content read (only after gate 0 passes).** From the instrumented run, collect readable
captures until 3 FAIL-side + 3 PASS-side are gathered or 8 tries are exhausted. For each FAIL try,
compare capture point 0 against point 1 **for the same heap** (identified by which heap's numbers
actually moved), then apply:

| Observed (point 0 → point 1, same heap) | Verdict |
|---|---|
| Already ≈31k at point 0 (no drop across the fetch) | not (a)/(b) as framed — pre-existing ceiling; escalate as (c)/other |
| Drops from ~45k range to 31k, and at point 1 `largest_free_block` ≈ `total_free_bytes` | **(a)** region span |
| Same drop, but `largest_free_block` well below `total_free_bytes` at point 1, `allocated_blocks` up vs point 0 | **(b)** mid-block survivor |
| `heap_caps_check_integrity_all` fails at point 1 or point 2 | **(c)** corruption — stop, file separately |
| No single heap's delta explains the aggregate drop | **(c)** unexplained — escalate per the design's own exit criterion 2 |

**What this run cannot establish:** that (a)/(b) is the only mechanism across all X010-family
triggers; a slow cross-try leak (every try is a cold boot, so this shape is invisible to an N=8
capture set); non-perturbation to better than ~±1 try. A verdict of (a) or (b) closes this design's
stated exit criterion (name the mechanism), not TASK-697's fix — a fix stays explicitly out of scope.

## Coverage bookkeeping

`get heapInfo` needs a `test_plan.md` entry (every additive console key gets one). Proposed, marked
`planned` only — not written into `test_plan.md` by this review (HARD CONSTRAINTS; VE persona rule:
test hole found → record as planned, flag PM, no silent skip, no out-of-turn edit before the design
lands):

```
### T_DTH_01 — [M-DATATASK-heap-region-instrument] get heapInfo contract
- Type: unit · Feature(s): data-task-001 · Interaction: X068
- Objective: `get heapInfo` returns one JSON line per capability class (INTERNAL, 8BIT, DMA) matching
  heap_caps_get_info()'s fields; absent from a non-SERIAL_DEBUG build (T089).
- Steps: `get heapInfo`; parse as JSON
- Expected: well-formed single-line JSON, three class keys, allocated_blocks+free_blocks==total_blocks
- Status: planned
```

`cross_feature_matrix.yaml` X068's `test_coverage` should gain `T_DTH_01` once written, and its "may
be reachable without the debug injector" clause revisited once gate 1 names a mechanism —
Developer/PM's call, not VE's to edit here. PM should file a follow-up task for the `probe/` parser
(VE-3) **only if** gate 1's hand-read pass proves more than one or two manual reads are needed — don't
pre-file speculative tooling ahead of measured need. VE-1/VE-2/VE-4/VE-5 need no task: they're design-
doc edits for Architect to fold, same as the sys-reboot-wifi precedent's same-day disposition.

## Verdict

| Finding | Class | Blocking? |
|---|---|---|
| VE-1 perturbation unbounded | blocker | yes — fold gate 0 into exit criteria |
| VE-2 no pre-fetch same-try baseline | major | yes — add capture point 0 |
| VE-3 no named parser location/scope | major | yes — one paragraph |
| VE-4 integrity-check framing + WDT | minor | fold in, not blocking |
| VE-5 T089 enforcement uncited | minor | fold in, not blocking |

**ACCEPT WITH CHANGES.** The design's instinct (Option A+B split, a decision-rule table inside the
design doc itself, naming what a single dump can't resolve) is sound and unusually testability-aware
for a first draft. VE-1 and VE-2 are the two changes that actually gate whether the eventual reading
can be trusted — both fold into existing sections (Lean/decision-rule/exit-criteria), no redesign.
**Not yet ready to implement**; ready once VE-1 (gate 0) and VE-2 (capture point 0) are folded in.
VE-3/4/5 can land at implementation time without blocking.

**Escalate to human:** none. Stays within the design's stated scope (probe, not fix) and existing
SERIAL_DEBUG/IFC-007/T089 practice; VE-1's fallback is named as contingency only, not proposed as new
scope now.

---

## Re-review 2026-09-14

Re-read `M-DATATASK-heap-region-instrument.md` after Architect's "Revision 2026-09-14 (after @VE
review)" note. Checked each finding against the revised text, and checked the revision's Gate 0/Gate 1
mechanics against this review's §2 word-for-word (not just "does it exist") — a mismatch between the
two documents would itself be a finding, per the coordinator's ask.

- **VE-1 — RESOLVED.** "Non-perturbation — Gate 0" is now a required section, not an open question.
  Tolerance band matches §2 exactly: FAIL rate ∈ {3,4,5}/8 → proceed, ∈ {0,1,2,6,7,8}/8 → stop, same
  boundary values, same "one try wide, essentially no power below that" honesty. Two-build protocol
  (`#ifdef`-absent vs firing, not a runtime toggle) matches. Stack cost is *named and bounded by
  method* (Gate 0 catches an overrun/delay empirically) rather than pre-measured — the design is
  explicit it can't measure stack depth in a documents-only draft, which is consistent with this
  review's own HARD CONSTRAINTS; deferring to an empirical gate rather than a hand-estimate was the
  resolution asked for, not a numeric bound. WDT concern is closed with a checked claim, not an
  assertion: dataTask is confirmed **not** TWDT-subscribed (`boot.cpp:236-237`, only `loopTask`/idle
  task call `esp_task_wdt_add`, grepped for other call sites, none found) — so VE-4's WDT-trip risk
  is moot, not just mitigated.
- **VE-2 — RESOLVED.** Capture point 0 added at the existing pre-fetch `LOG_HEAP` line (~1421),
  same gated pair as points 1/2. The delta table in the revision's Lean section is **identical** to
  this review's §2 table — same five rows, same conditions, same verdicts, same wording down to "not
  (a)/(b) as framed" and "escalate per exit criterion 2." No drift between the two documents.
- **VE-3 — RESOLVED.** Parser explicitly out of scope, `app/tools/probe/` named as the eventual home,
  BP-068 negative-test obligation stated, SPIKE-gate consequence noted, and correctly gated on "if
  gate 1 needs more than one or two manual reads (PM's call once measured, not pre-filed
  speculatively)" — matches this review's own instruction not to pre-file ahead of measured need.
- **VE-4 — RESOLVED.** Integrity-check reframed ("not for free" — rules out only the corruption
  sub-case, says nothing about (a)/(b)). WDT exposure checked and found moot (see VE-1 above) rather
  than merely fed-around.
- **VE-5 — RESOLVED.** T089 enforcement investigated, not just cited: `test_plan.md` T089 is a
  one-time manual `strings`/`grep -c` run ("passed 2026-05-17"), confirmed absent from `run/check`'s
  gates and `smoke_test.sh`'s 49 host scripts by grep. This is the honest answer this review asked
  for ("cite the gate, or say none exists") — it says none exists, plainly.

No mismatch found between the two documents on any load-bearing number (Gate 0 tolerance band, N=8
vs N=3+3, capture-point numbering, the delta table). Nothing outstanding.

**Final verdict: ACCEPT.**

**On `> Status:`**: not moving it. This review's ACCEPT clears VE's own hold, but per this project's
own precedent (`sys-reboot-wifi-multi-VE-review.md`: both docs stayed `Status: draft` — "awaiting
human sign-off next" — even after VE approved and Architect folded every change same day), flipping
`Status: draft` → `accepted` (C4 closed vocabulary) is a human/Architect action, not something VE's
own approval performs. Recommend the human make that call now that both required findings are folded
and this re-review reads no open item against VE; until then it correctly stays `draft`.
