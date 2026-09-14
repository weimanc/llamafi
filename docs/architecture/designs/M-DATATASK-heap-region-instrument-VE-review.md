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

---

## Review of Revision 2 (2026-09-14)

Gate 0 ran and **FAILED: perturbing** (`task697-...md`, last section: OFF 3/8 FAIL matching the
signature exactly, ON 2/8 FAIL + 6/8 harness-exchange failures — outside the pre-registered
{3,4,5}/8 band, and the new evidence category this re-review's own §2 didn't anticipate). Architect's
Revision 2 (`Status: proposed`) responds with new evidence and a re-opened option set. Read in full;
every file:line citation it adds was checked against the raw artifacts, not taken on faith.

### 1. Evidence verification

**Span timing — mostly right, not exact.** Re-parsed all 8 `G0ON_*.log` files for
`point=N ... begin`/`... integrity=ok end` marker pairs directly: **55 pairs** (not the claimed 54),
strictly alternating begin/end (no ordering ambiguity), span **112-124 ms, mean 115.9 ms** (not the
claimed "110-124 ms"). The qualitative claim — tight, state-independent clustering, inconsistent with
a variable-cost integrity walk — holds against the corrected numbers exactly as well as the claimed
ones; this is an imprecision, not a wrong conclusion. **Byte volume**: measured 1531 bytes between one
real begin/end pair in `G0ON_1.log` — matches "roughly 1.3-1.5 KB" (at the high end, not centered, but
within the stated range). **9 registered heaps** (8 small + one 113 840 B region) confirmed exactly
against the captured dump text.

**The split-reply citations — one right, one off by a line.** `G0ON_2.log:605` is exact: that line is
`ok":true,"cmd":"get","var":"appId","id":6,"name":"Stock","last":true}`, the orphaned tail of a reply
whose head (`{"`) landed mid-dump at line 600 (`{"    largest_free_block 0 alloc_blocks 9...`) — the
phenomenon as described. `G0ON_1.log:616`, however, is **not** the corrupted line — line 616 is
`At 0x3ffaff10 len 240 free 8 allocated 4 min_free 8`, ordinary dump text. The actual corruption
(`... total_blocks 4{"ok":true,"2`, reply head landing mid-digit) is at **line 615**, one line above
the cited one; the reply's tail reappears at line 630. The phenomenon is real and independently
reproduced by direct grep — this is a one-line citation slip, not a fabricated finding.

**`app/tools/lib/dut.py:1086` — confirmed WRONG, and it's a repeat.** Line 1086 of `dut.py` is
mid-way through an unrelated `playerMode`-polling helper, not the discard-non-`{` rule. The rule
lives in `read_json()`, `dut.py:1396` (`if line.startswith("{")`, inside the method starting at
line 1389). This citation is not new to Revision 2 — it was already wrong in **this review's own
VE-3 finding** on the original draft, inherited uncorrected from that draft's Option A cost note, and
now Revision 2 repeats it again without correction. The underlying claim (non-`{` lines are discarded)
is still true; only the line number is wrong, three times running now. Flagging this as a finding in
its own right: a wrong citation that survives two revisions and one VE review unfixed is a process
gap, not a one-off typo — nothing in this project's docs pipeline currently catches a stale line
citation the way `check_docs.py`'s C5 catches a broken relative link. **Resolution**: fix all three
occurrences (this doc's VE-3, and Revision 2's evidence section) to `dut.py:1396`.

**Unverifiable-and-said-so claim, checked and confirmed correctly unverifiable.** Revision 2 states
the "integrity-walk holds a lock" reading "could not be verified against source" because no
`heap_caps.c`/`multi_heap.c`/`multi_heap_poisoning.c` exists under the installed framework package —
confirmed by an independent `find`, no such files present, only the prebuilt `libheap.a`. Correctly
labelled "reading, not verified" rather than asserted.

### 2. Challenging the Lean

**Option 1's retry is a control, not a fix candidate, and the doc should say so plainly.** Revision
2's own "reframes the fallback options" paragraph already establishes that the observed corruption is
caused by the *print's* text landing on the shared UART, not by the integrity walk (which returns a
bool and writes nothing on success). Dropping the integrity walk removes an unverified, probably
minor, share of the 116 ms and none of the interleaving — the design says this, then in Lean still
treats "(1) is cheap to try but unproven" as one of two parallel-tracked options with a chance of
closing Gate 0. It has essentially no such chance on the evidence already in the same document: the
write path that corrupted `appId`/`quoteOkCount` replies is `heap_caps_print_heap_info()` itself,
present unchanged in the option-1 rebuild. Running it is still worth doing — cheap, and it isolates
the integrity walk's own contribution as a control variable, and per the new zero-corruption rule a
second Gate-0 failure there would be confirmatory, not wasted — but Revision 2 should say plainly that
option 1's likely outcome is another Gate-0 failure via the corruption rule specifically, not the rate
band, so nobody reads a second failure as new information when it's the predicted one.

**A missing option that attacks the interleaving directly.** Options (2)-(4) don't include the one
combination the evidence most directly points at: `heap_caps_print_heap_info()` makes on the order of
19 separate `Serial`/`printf` calls (one per dump line) across ~1.5 KB — each call is a preemption
window the console's own reply write can land inside. A **hand-rolled, single-`printf`-call, per-
region compact line** — pack just the load-bearing fields (per-heap `largest_free_block`,
`total_free_bytes`, `allocated_blocks` for the handful of 8BIT-capable heaps) into one short
JSON-safe string and emit it with one write call — keeps Option A's per-region granularity (unlike
naive aggregation, option 4 in the doc, or the "record only aggregate numbers" idea the coordinator
also raised, which is just Option B again and reopens the original (a)/(b) problem) while cutting both
the byte count (~200-300 B vs 1.5 KB) and, more importantly, the *number of preemption windows* from
~19 to 1 — the mechanism Revision 2's own evidence names as the actual writer of the corruption.
**Testability**: still needs a real Gate 0 re-run to confirm (nothing here is provable from documents
alone, same as the doc's own Option 2), and it's a real code change (a new formatter, not a toggled-
off library call) so it needs the same Developer-spike gate Option 2 is already held to — it is not
"cheap to try" in the free sense Option 1's retry is. The RAM-buffer-plus-deferred-atomic-emit idea
the coordinator also raised is weaker than this: buffering ~1.5 KB to defer the write needs a new
allocation at exactly the capture instant, which risks perturbing the very fragmentation metric under
investigation — a self-referential risk this design should avoid, not one of its stronger candidates.
A lock shared with the console's reply path is stronger (guarantees no interleaving by construction)
but is the most invasive of the three, touching code this design's own scope note says is "currently
uninvolved," and carries a priority-inversion question the doc doesn't raise.
**Resolution:** add this compact-single-write option to the Design space, and weigh it against — not
after — Option 1's retry in the Lean. Given Option 1's retry has a known-weak rationale (above), the
compact-line option is the better use of the next DUT session if a Developer spike can turn it around
quickly; Option 1's retry is worth keeping only as a fast, free control run in the same session, not
as a co-equal parallel track.

### 3. Pre-registered A/B for Option 3

**Command:** `run/test-targeted T_PR_04,T_PRI_01,T170`, `LOG_FILE=<path>`, 8 tries per arm, fresh
flash per arm — same shape as every prior baseline in this investigation, so the result is comparable
to the 4/8 (morning) and 3/8 (this evening's OFF arm) already on record.

- **Arm A (control, no reservation)**, run in the same session immediately before Arm B: expected to
  reproduce a FAIL rate in the established {3,4,5}/8 band with the exact `maxBlk=31k` + `-32512`
  signature. If it doesn't, the session is compromised (environmental drift, a different firmware
  commit, a different board) and Arm B's result is **not interpretable** regardless of what it shows —
  don't read B without A confirming the baseline first, same discipline as Gate 0 itself.
- **Arm B (reservation in place).**

**Decision rule, stated honestly for N=8:** the OFF arm has already shown natural rate variance of
{3,4}/8 across two independent runs today, without any reservation change. At this N, only a result
outside that already-observed noise floor is trustworthy:
- **Success** = Arm A reproduces {3,4,5}/8, **and** Arm B reads **0/8 FAIL**. A clean sweep is the
  only outcome distinguishable from baseline noise at N=8 with any confidence (if the true underlying
  FAIL probability were still ~40-50%, P(0/8) is under 1% — a real signal; P(1/8) or P(2/8) is not
  meaningfully rarer than what the baseline itself already produced).
- **Inconclusive** = Arm B reads 1/8 or 2/8. Do not report this as "the reservation helps" — it is
  within the noise band this project's own two same-day baselines already demonstrate, and escalating
  to a larger N (per the human open question below) is the only way to resolve it, not a smaller
  informal read.
- **Failure** = Arm A reproduces the baseline band and Arm B reads ≥3/8 with the same signature — the
  reservation as implemented does not change the outcome (wrong size, wrong placement, or consumed
  before the critical moment; a specific reservation attempt failing, not necessarily a refutation of
  reservation as an approach in general).
- **Session invalid** = Arm A does not reproduce {3,4,5}/8 — stop, don't read B, re-run.

**What a success would NOT establish:** which of (a)/(b)/(c) was happening — the mechanism stays
unnamed; that the fix generalises to X010's other triggers (different fetchers, different allocation
shapes could still hit a ceiling this reservation doesn't cover); that the reservation is *correctly
sized* rather than oversized-and-accidentally-working (a real risk against `mem_manifest.yaml`'s
tight `INTERNAL` headroom, worth a follow-up sizing pass before this becomes a permanent change); or
that it holds under other apps' concurrent RAM pressure (WebRadio's separate RAM story is untouched by
an 8-try Spotify/PlaneRadar/Stock sequence). A success closes X068's *operational cost*, not its
*root cause* — consistent with how Revision 2 itself already frames Option 3.

### 4. Answers to Revision 2's open questions

**For @VE:**
1. **No, the zero-corruption rule as written is not sufficient — extend its scope, don't just keep
   it.** It currently only catches corruption that happens to surface as a recognisable SKIP/UNMET
   message. A `set` reply corrupted the same way might not fail visibly at all — a truncated-but-
   still-JSON-shaped ack could be silently accepted (false green, worse than a visible failure) or
   misread as belonging to the wrong command. Extend the rule to require a byte-level scan (grep for
   an orphaned `{`/`}` fragment or any raw-serial line not matching a known emitted shape) across
   **all 8 ON-arm tries**, covering every console round trip in the sequence (`set prRange`,
   `set prClearInject`, both `set prInjectAircraft`, and every trailing `get`), not just the two
   FAIL-shaped tries inspected this time.
2. **Yes, a documents-only "not viable without a firmware redirection" is an acceptable close for
   this design's exit criterion** — same posture as Gate 0's own "cannot observe non-invasively" being
   named as a valid exit in Revision 1, and consistent with this project's practice of a written,
   accounted-for stop over silent abandonment. Condition: the close must name the compact-single-write
   option (above) and Option 2's sub-approaches explicitly as the named follow-up, handed to Developer
   as a scoped spike — not dropped quietly, since (unlike the `probe/` parser in the first review) this
   is not speculative tooling ahead of need, it's already-measured need.
3. **0/8 on the reservation arm**, matched against a same-session control reproducing {3,4,5}/8 — see
   §3. 1-2/8 is INCONCLUSIVE, not accepted as success, at N=8.

**For the human**, both of Revision 2's own items stand (Option 3's RAM-budget scoping timing; a
DUT-time budget for the investigation) — VE has no authority over either. Adding one: today's Gate 0
already cost a full 16-try, two-fresh-flash session and produced a new harness-corruption finding
rather than an answer; Option 3's A/B and a compact-line retry (if pursued) will each cost at least
one more 8-try session. Is the human's intended parallelism ("Option 3 in parallel with Option 1's
retry") two DUT sessions run back-to-back on one board, or genuinely concurrent on two boards — and is
there a stopping condition (this project's own precedent: TASK-393 was downgraded P1→P2 after three
failed repro attempts; TASK-697 is now at a comparable count of inconclusive instrumentation attempts)
if neither closes within a stated number of further sessions.

### Verdict

**ACCEPT WITH CHANGES.** Revision 2's discipline is good where it matters most — it applied its own
pre-registered Gate 0 rule correctly against a result that didn't go its way (2/8 outside the band,
stop, don't read content), and it separates evidenced claims from unverified readings honestly (the
lock-hold theory explicitly marked unverifiable, and correctly so per the independent `find` check
above). No blocker. Required before the next DUT session:

1. Fix the `dut.py:1086` citation (→ `:1396`) everywhere it appears, including retroactively in this
   review's own VE-3 finding on the original draft.
2. Correct `G0ON_1.log:616` → `:615`, and re-state the span statistics as 55 pairs / 112-124 ms
   (or caveat the existing numbers as approximate — but don't leave them stated as exact when a direct
   recount differs).
3. Add the compact-single-write per-region option to the Design space and weigh it against Option 1's
   retry in the Lean — Option 1's retry should be reframed as a free control run with a known-likely
   outcome, not a co-equal parallel track with a real chance of closing Gate 0.
4. Fold this section's extended zero-corruption rule (all commands, all 8 ON-arm tries) and Option
   3's A/B decision rule into the design doc itself, same as Revision 1's findings were folded.

None of this blocks Option 3's A/B from proceeding as scoped in §3, and none of it invalidates
Revision 2's central, well-evidenced conclusion — the interleaving is real, directly observed, and
correctly identified as the print's own doing, not the integrity check's.

---

## Re-check of the Option 3 spec (2026-09-14)

Human signed off Revision 2 (reservation first, experiment-only, last session — not a clean 0/8 →
P2). Architect added "Option 3 experiment specification" (`Status: accepted`). Checked against this
review's own §3 A/B before implementation. Documents only.

### 1. Architect's three flagged items

**(a) Every dataTask fetcher's bracket — verified directly, not taken on the doc's word.**
`app/src/dataTaskStorage.cpp`: `fetchWeather` (478), `fetchCrypto` (518), `fetchStockQuote` (576),
`fetchStockChartWithRetry` (732, Stock chart), `fetchTeletext` (811), `fetchHeatmapQuote` (1073,
Stock heatmap), `fetchGeocode` (1643), `fetchWebRadioStations` (1713) — **8 of 9** use the RAII
`spotifyTask::TlsYieldGuard tlsGuard;` (`app/src/spotifyTask.h:206`, constructor calls `tlsYield()`,
destructor calls `tlsResume()`). **`fetchPlaneRadar` (1493-1604) is the one exception**: manual
`spotifyTask::tlsYield()` at 1493 and `spotifyTask::tlsResume()` at 1604, no RAII guard — and this is
the *only* fetcher the design's draft actually confirmed ("BP-031"), which makes it the
least-representative example available, not a representative spot-check. Coverage is complete — all
9 fetchers bracket their TLS work one way or the other, no fetcher fetches with Spotify's TLS still
live and no reservation-release hook — but the mechanical wiring is **not** uniform: the 8 RAII
fetchers need the reserve call inserted on the line right after `TlsYieldGuard tlsGuard;` and the
re-acquire call inserted right before the guard's scope closes (nothing in `TlsYieldGuard` itself
should change — it's used elsewhere in the tree beyond these 9 fetchers, e.g. the audio engine's
file-play path per its own move-constructor comment, and baking reserve/release into the guard's
ctor/dtor would reach those unrelated call sites too); `fetchPlaneRadar` needs its own manual
insertion at both existing call sites, no guard scope to hook into. No early return sits between
`fetchPlaneRadar`'s `tlsYield()`/`tlsResume()` pair (checked — the function runs straight through),
so a manual release/re-acquire pair there is as safe as the RAII fetchers' automatic one, just written
by hand. **Resolution:** Developer instruction — treat this as 9 call sites needing 9 pairs of manual
insertions (2 lines each), not "wire the shared function into the bracket" as if the bracket were one
uniform thing; list both patterns explicitly in the implementation notes so `fetchPlaneRadar` isn't
mis-handled as if it had a guard.

**(b) Reservation-never-engaged severity — the design mis-cites this as an adopted VE rule; it isn't
yet. Deciding it now, as asked.** Checked this review's own §3 (this doc's "Re-view of Revision 2"
section): it defines Arm-level success/inconclusive/failure/session-invalid entirely on the *FAIL
rate*, and says nothing about a per-try engagement-failure exclusion. The design's "@VE's rule: ...
exclude it from the 8-try count" is **not something VE said before now** — it is presented as adopted
verbatim alongside things that genuinely are (the Gate 0 band, the A/B command/arms), and that
juxtaposition is itself a finding: one rule in the "adopted from VE" material was not, in fact, from
VE. **Ruling, pre-registered now:**
- A try where the `LOG_D` engagement markers show the reservation was never acquired at boot, or was
  released but not successfully re-acquired before the measured fetch, is **excluded from that arm's
  count** (recorded, not forced into PASS/FAIL) — agreed with the design's proposal on the individual-
  try question.
- **New condition the design doesn't have:** if **3 or more of Arm B's 8 tries** are excluded this
  way, the arm is **invalid, not merely smaller** — re-run Arm B in full (fresh flash) before reading
  it. Reasoning: this review's own success bar (§3) is 0/8 specifically *because* N=8 has power only
  for a clean sweep (P(0/8) under 1% against the ~40-50% baseline rate; P(0/5) is 3-5%, a materially
  weaker claim). A same-session ruling of "the reservation succeeded" built on an eroded N would not
  meet the bar the human's own "clear 0/8, not a partial win" ruling asked for. Given this is TASK-697's
  **last session**, a silently-shrunk N producing an apparent 0/5 or 0/6 must not be reported as the
  clear 0/8 the ruling requires — either re-run within the same session to recover N=8 evaluable tries,
  or report to the human as "engagement was unreliable, no valid A/B result obtained," not as a success.

**(c) Unverified TLSF-style placement reasoning — sufficient to spend the session on, with one
correction.** The design's own framing ("best-fit-style allocator... marked unverified, a reasoning
step") is honest about not being able to cite source (confirmed again: no `.c` sources ship). One
correction worth folding in: ESP-IDF's heap component (public knowledge, not verifiable from this
framework's shipped sources either) is TLSF-based — a segregated-fit allocator that picks a block from
the smallest non-empty size class that still fits the request, which is a **good-fit** approximation,
not literal best-fit, and does not guarantee the *single largest* free span is where a 40 KB-plus
request lands if other free blocks also clear the size-class threshold. This weakens the *causal*
story ("TLSF will prefer our released span specifically") without weakening the *experiment*: this
review's own §3 already states a success would not establish which of (a)/(b)/(c) was happening, and
that stands regardless of which allocator-placement story is right — the A/B's FAIL-rate comparison is
mechanism-agnostic by design. **Sufficient to spend the session on**, provided the design doesn't
upgrade "should preferentially place" to a confirmed mechanism if the A/B succeeds — a success shows
the reservation changes the outcome, not that it does so via the TLSF story specifically. Add one line
noting TLSF good-fit (not best-fit) as the actual allocator family, so a future reader doesn't cite
the unverified reasoning as settled.

### 2. Spotify contention — Arm B is confounded as specified; this is a rule, not advice

Checked the mechanism against `TlsYieldGuard`'s actual semantics (`spotifyTask.h:206-`): `tlsYield()`
**stops** Spotify's own TLS activity for the guard's lifetime; `tlsResume()` **resumes** it. So while
any dataTask fetcher holds its bracket, Spotify is already paused by the pre-existing BP-031
mechanism — the reservation's release (during that same window) cannot be grabbed by a concurrently-
running Spotify handshake, because Spotify isn't running one then. The exposure is the *inverse*
window: between dataTask fetches, when no fetcher's bracket is open, Spotify has resumed and the 40 KB
reservation is held by default (per the "when acquired... before the dataTask loop... every fetcher
and injection can run" framing, it's the *resting* state, released only transiently). Spotify's own
client is admitted to need ~50 KB contiguous and was already observed failing `-32512` in FAIL tries
at baseline; the coordinator's measured `freeInt` figures (≈105 k with no TLS session, ≈55 k with one)
mean a persistent 40 KB hold leaves Spotify roughly **≈15 k** when it already has a session live —
well under its own need, and worse than baseline. **This confirms the coordinator's concern is real,
not hypothetical: Arm B, as specified, changes Spotify's own success rate, not just PlaneRadar's/
Stock's fragmentation exposure — it is testing "reservation + a squeezed Spotify," not "reservation"
in isolation.**

This **does invalidate Arm B as a clean isolated treatment** for the question "does protecting one
handshake-sized span fix the X010-family ceiling" — a rate change could be produced by the reservation
working as intended, by Spotify backing off more (quieting the concurrent workload that fragments the
heap in the first place, an artifact not a fix), or both, and the design as specified cannot tell them
apart.

Given constraints (last session, experiment-only, no `mem_manifest.yaml` change, Spotify's own code
explicitly out of scope), extending the release bracket into `spotifyTask` itself is too large a
change for this session, and reserving later/smaller re-opens exactly the timing-precision problem
this design has already failed once (Gate 0) to solve non-invasively. The coordinator's third option —
a pre-registered secondary observable — is the only one that fits the session's own constraints (zero
firmware change: `-32512` already appears in existing log lines per Revision 2's own evidence
section). **Pre-registered as a rule:**

- For every evaluable try in both arms, count occurrences of `rc=-32512` attributable to **Spotify's**
  own client (the `after -1: rc=-32512` shape already named in this document's evidence section,
  distinct from PlaneRadar's/Stock's own `-32512` lines) in that try's raw serial log.
- Compute each arm's mean Spotify-`-32512`-count-per-try.
- **Decision consequence, stated as a rule:**
  - Arm B reads 0/8 FAIL **and** its Spotify-`-32512` rate is not meaningfully higher than Arm A's
    (no more than roughly double Arm A's per-try mean, and not present in every Arm B try where Arm A
    had none) → **clean success**, reportable to the human as the clear 0/8 the ruling asked for.
  - Arm B reads 0/8 FAIL **but** its Spotify-`-32512` rate is meaningfully higher (roughly doubled, or
    present in every Arm B try against none in Arm A) → **confounded, not a clean success.** Report to
    the human explicitly as "0/8 on T170, but confounded by increased Spotify TLS failure" — do **not**
    let this silently satisfy the "clear 0/8" ruling, since the ruling's downstream consequence (a real
    sizing decision/ADR) assumes the mechanism is protecting the fetch path, not degrading Spotify's.
  - Arm B's Spotify-`-32512` rate increases **and** T170's FAIL rate does not read a clean 0/8 →
    report as a reason **against** pursuing a larger reservation, not merely "inconclusive" — the
    experiment would then show the approach costs Spotify without fixing Stock.

### 3. Other threats to validity; readiness

No other threat rises to blocking. Two worth naming: the reservation's release is a general release
into the free pool, not a targeted hand-off to the fetcher that triggered it — a different concurrent
allocator could claim it, which is a pre-existing property of any pool-based reservation and not
specific to this design's flaws, just worth knowing before reading a "success" as proof the *intended*
fetcher got the span. And Arm A/B's fresh-flash-per-arm protocol means the two arms still run at
different points on the same board's boot/flash history, same as every prior A/B in this
investigation — an accepted, already-standard limitation here, not a new one.

**Readiness: READY WITH CHANGES**, all documents-only and small:
1. Fold §1(a)'s two-pattern instruction (8 RAII insertions vs. `fetchPlaneRadar`'s manual pair) into
   the spec so Developer doesn't treat the bracket as uniform.
2. Fold §1(b)'s ruling in verbatim (exclude individual non-engaged tries; ≥3/8 excluded invalidates
   and requires a re-run, not a smaller-N read) and correct the misattribution — this rule is new as
   of this section, not something VE had already adopted.
3. Add §1(c)'s one-line TLSF/good-fit correction to the placement-reasoning note.
4. Add §2's Spotify-`-32512` secondary observable and its three-way decision rule to the spec verbatim
   — this is the one required change with teeth: without it, a confounded 0/8 reads identically to a
   clean one, and the human's ruling explicitly turns on "a clear 0/8," not any 0/8.

None of these block starting implementation of the reservation itself — they're checks to run and
rules to apply when Arm B's data comes back, not redesigns of the reservation mechanism.

---

## Final check — symmetric release (2026-09-14)

### Persistent session — confirmed, exactly as the coordinator predicted

Read `app/src/spotifyTaskStorage.cpp` directly. `doPoll()` (252-320) calls `client.stop()` **only**
on `status == -1` (line 314, inside the failure branch); on `status == 200` or `204` (success) the
client is left open — no `stop()` call anywhere on that path. `doFetchQueue()` (239-247) is the same
shape: `client.stop()` only when `status < 0` (247). Confirms `cross_feature_matrix.yaml` X010's
claim: Spotify's `WiFiClientSecure` session persists across successful polls. There are exactly five
places this file calls `client.stop()`: init (355), `resetTls` (365), `doPoll`'s `-1` branch (314),
`doFetchQueue`'s failure branch (247), and the `tlsYield()`-ack path inside `taskBody` (377, the same
event every dataTask fetcher's bracket already triggers). **Every other moment — every successful
poll or queue fetch — the client stays open, holding its own ~40 KB session.**

Symmetric release's re-acquire, placed unconditionally right after `getCurrentlyPlaying`/`getQueue`
returns, does not correspond to any of these five stop events on the success path — it is not
re-acquiring when the client is stopped, it is attempting a fresh 40 KB contiguous malloc **while**
Spotify's own ~40 KB session is still live, against a measured `freeInt` of only ≈55 KB with a session
up. That is a malloc asking for ~73% of *all* free memory in one contiguous span, immediately after
the coordinator's own measured squeeze — likely to fail outright on most successful-poll cycles, not
merely "usually fail" as a probabilistic hedge. **The re-acquire point must be one of the five actual
stop events, not the call's return.** Of those five, only one is already visible to dataTask's
reservation logic without new plumbing into `spotifyTaskStorage.cpp`'s internals: the `tlsYield()`-ack
at line 377 — which is the *same* event the original per-fetcher bracket already keys off of when
another dataTask fetcher requests the yield.

### The two goals conflict on this heap — stated plainly, as asked

Tying re-acquire to a genuine stop event (rather than the call boundary) doesn't rescue the design —
it sharpens the conflict instead of resolving it. If re-acquire only fires on an actual `client.stop()`
event, the reservation is **un-held for the entire duration of every successful Spotify poll cycle** —
which per this investigation's own evidence is precisely the state the boot is normally in when
`T_PRI_01`'s injection race lands (a failure storm is the exception, not the trigger condition). If
instead re-acquire fires unconditionally at the call boundary (as currently specified), it mostly just
**fails** during that same state, for the arithmetic reason above — same practical non-engagement,
reached by a failed malloc instead of a deliberate skip. **Neither placement lets the reservation stay
reliably held through Spotify's ordinary, successful operating state**, because the conflict is
capacity, not code placement: Spotify's persistent session (~40 KB) plus the reservation (40 KB) is
≥80 KB against a total free pool that is only ≈55-105 KB depending on whether a session is up. No
choice of call site changes that sum. **This is the finding the coordinator asked to check for: the
two goals conflict on this heap, and no placement of the release/re-acquire calls resolves it — only
either shrinking one side (a smaller reservation, which re-opens the problem VE-4/the earlier re-check
already named: too small to protect dataTask's own fetchers) or accepting the confound (the original,
non-symmetric design, monitored via the `-32512` secondary observable already pre-registered) avoids
it.**

**A consequence worth naming**: per this document's own §1(b) rule (exclude an unengaged try; ≥3/8
excluded invalidates the arm and forces a re-run), a reservation that structurally fails to re-acquire
through most of Spotify's normal polling will very likely **exclude most or all of Arm B's tries on
its own**, before the FAIL-rate question is even reached — i.e., the ≥3/8 circuit-breaker this review
already specified is likely to fire almost every time this spec is run as written, not as an edge
case. Spending the *last* session on a mechanism whose own instrumentation is likely to invalidate
itself is a real cost worth surfacing before Developer implements five new call sites in
`spotifyTaskStorage.cpp` (outside the file this design otherwise touches).

### Engagement observable — tightened per the coordinator's instruction

This document's earlier engagement rule (§1(b)) only required the log to show acquire/release
*events happened somewhere in the try*. That is not sufficient — a try can show a clean release at
boot and a successful re-acquire ten seconds later and still have been **un-held at the exact
PlaneRadar result/injection window that matters**. **Tightened requirement**: the reservation's live
state (`HELD` / `RELEASED`) must be logged **at capture point 1 itself** (`heapRegionDump(1, ...)`,
`dataTaskStorage.cpp:1602`, the existing post-result `maxBlk` reading) — piggybacked onto that
existing line, not reconstructed after the fact from separate acquire/release timestamps elsewhere in
the transcript. "Engaged," for the purpose of the exclusion rule, means **the point-1 line itself
reports `HELD`** — a try showing `RELEASED` at point 1 is excluded from the count regardless of what
the acquire/release log shows before or after it.

### Verdict: **NOT READY**

Not a documents-level nitpick — a structural conflict, stated per the coordinator's own framing. Before
Developer implements the symmetric-release expansion (which also, per the coordinator's opening line,
grows the diff beyond what the human signed off — five new call sites in a file the original ruling
didn't scope):

1. Take this conflict back to the human before implementing. The choice is theirs, not Architect's or
   VE's: (a) drop symmetric release, run the **original** dataTask-only reservation, and accept Arm B
   tests "reservation + a possibly-squeezed Spotify" — report the pre-registered `-32512` secondary
   observable honestly per this document's existing three-way rule, rather than trying to engineer the
   confound away; or (b) treat this finding itself — no code-only placement can hold 40 KB against
   PlaneRadar's window without squeezing Spotify's persistent ~40 KB session on a heap this tight — as
   satisfying the spirit of the human's own stopping condition (a mechanism that cannot be made to work
   cleanly is not distinguishable from "not a clear win") and downgrade now, saving the last session.
2. If the human chooses (a): drop the `doPoll`/`doFetchQueue` release/re-acquire additions entirely,
   keep the original per-fetcher-only bracket, and keep the `-32512` observable as the confound
   detector it was already specified to be.
3. Either way: fold in the tightened engagement observable above (state logged at capture point 1,
   not inferred from separate events) before Arm B is run at all — this applies regardless of which
   fix path is chosen.

Not rejecting Option 3 wholesale — the reservation-around-dataTask-fetchers mechanism itself is
unaffected by this finding, and its own A/B (§3 of the prior re-check) remains valid. What's not ready
is the symmetric-release *expansion* specifically, and it should not proceed to implementation without
the human seeing this conflict first, per the coordinator's own note that it already expands signed-off
scope.

---

## Re-check after the premise check (2026-09-14)

### Premise verified independently — confirmed true

Grepped all 16 raw logs directly (`L697_1-8.log`, `G0OFF_1-8.log`, the scratchpad copies), not taking
Revision 3's table on faith: `grep -oE 'status=-?[0-9]+'` across all 16 files returns **only
`status=-1`, 64 occurrences, zero `status=200` or `status=204`**; a second, independent pattern
(`[spotify.poll] (ok|204)`, the exact text `doPoll()` logs only on a real success) also returns
**zero matches across all 16 files**. Both checks agree with Revision 3's table exactly: no Spotify
poll or queue call succeeds anywhere in the `T_PR_04`→`T170` window, in any of the 16 tries checked.
Since every non-success branch in `spotifyTaskStorage.cpp` calls `client.stop()` (confirmed in the
prior check: `doPoll` line 314, `doFetchQueue` line 247), zero successes means zero surviving sessions
— **the capacity-conflict finding from the previous check does not apply to this specific A/B's
sequence, confirmed independently, not just accepted on the design doc's word.** The design's reversion
to the dataTask-only reservation is sound on this evidence.

### The confound detector needed redefining — the coordinator's concern is correct

The previously pre-registered detector (count `-32512` occurrences per try) would misfire exactly as
the coordinator describes: Spotify fails in *every* try in *both* arms regardless of the reservation
(TASK-675 guarantees that) — the only thing the reservation can plausibly change is *which* failure
Spotify hits first (a slow `-9984` cert-chain failure after a real network round trip, or a fast
`-32512` allocation failure before any network I/O happens at all) and *how long that cycle takes*, not
*whether* Spotify succeeds. Counting `-32512` would grade a pure error-code relabelling as "confounded"
even when nothing about Spotify's actual behaviour — its outcome, its resource footprint after the
attempt — changed at all. **Redefined rule, replacing the `-32512`-count detector:**

- **(b) Success count — the hard invalidator.** Expected 0 in both arms, every try (per the premise
  check above). **Any try in either arm showing a real `200`/`204`** (the same text-match used above)
  **invalidates that arm's run outright** — it means the premise this reversion rests on (TASK-675
  fails every refresh, no session ever forms) has stopped holding, the capacity conflict from the
  prior check becomes live again, and the run must stop and be reported to the human before reading
  any FAIL-rate result. This is not a statistical judgement call — one success is sufficient, because
  it falsifies the premise the whole reversion depends on.
- **(c) Elapsed-time shape — the real confound detector.** A `-9984` failure is a completed network
  round trip (measured in this evidence chain at ~4.2-4.3 s per queue attempt, e.g. `status=-1
  elapsed=4239-4262ms` in `L697_1.log`); a `-32512` failure is an allocation failure that can occur
  before any socket I/O, near-instant. **Per try, per arm**: compute each Spotify poll/queue attempt's
  `elapsed=` value from the log and classify it slow-shape (≈4 s+, a real attempt that reached the
  network) or fast-shape (a few hundred ms or less, consistent with failing before I/O). **A
  systematic shift in which shape dominates between Arm A and Arm B — not the error-code text itself —
  is the confound**: if Arm B's attempts turn fast-shape where Arm A's matching attempts were
  slow-shape, Spotify's cycle duration through the window changed, and cycle-duration is exactly the
  variable this investigation's own CORRECTION section already showed to be load-bearing for whether
  the injection race lands where it does. Use a qualitative, order-of-magnitude threshold (seconds vs.
  sub-second), not a percentage cutoff — the same honesty-at-small-N discipline already applied to
  Gate 0's rate band elsewhere in this review.
- **(a) Attempt count — informational, not a standalone invalidator.** Count poll+queue GETs per try
  in each arm and report it alongside (c); a faster failure cycle can fit more attempts in the same
  window even with no confound at all, so attempt count alone proves nothing — it corroborates (c)
  when both move together (more attempts *and* a fast-shape shift is stronger evidence than either
  alone) and should not be read in isolation.

**Consequence, stated as a rule**: Arm B reads a **clean success** only if it hits 0/8 FAIL on `T170`
(this document's original §3 rule), **no success appears in either arm** (rule (b)), **and** no
systematic fast-shape shift appears in Arm B relative to Arm A (rule (c), qualitative). A fast-shape
shift with an otherwise-clean 0/8 is **confounded, not clean** — report both numbers to the human, do
not silently pass it as the ruling's "clear 0/8."

### Restated for this design — engagement observable and the invalidation rule

Unchanged from the prior check, restated because the design reverted to the dataTask-only mechanism
these apply to directly: the reservation's live state must be logged as `HELD`/`RELEASED` **at capture
point 1 itself** (`heapRegionDump(1, ...)`, `dataTaskStorage.cpp:1602`), not reconstructed from
separate acquire/release timestamps — "engaged" means the point-1 line reports `HELD`. A try whose
point-1 line reports `RELEASED` is excluded from that arm's count (recorded, not forced into
PASS/FAIL); if **3 or more of Arm B's 8 tries** are excluded this way, the arm is **invalid, not
merely smaller**, and must be re-run in full before being read — a silently-shrunk N must not stand in
for the clear 0/8 the human's ruling requires.

### Verdict: **READY WITH CHANGES**

Premise holds under independent check — no objection to reverting to the dataTask-only reservation.
Required before Arm B is run:
1. Fold the redefined three-part confound rule (§ above: success-count hard invalidator, elapsed-time-
   shape as the real detector, attempt-count as corroborating context only) into the design doc,
   replacing the raw `-32512`-count rule verbatim.
2. Keep the point-1 `HELD`/`RELEASED` engagement observable and the ≥3/8 invalidation rule as specified
   — both restated above, unaffected by this premise check.
3. **For the human**: nothing new to decide beyond what Revision 2's ruling already covered — the
   premise check resolves the symmetric-release question without reopening scope, since the reversion
   stays inside the originally-signed-off dataTask-only mechanism. Flag one contingency for the
   record, not a decision needed now: if a success ever appears in either arm (rule (b)), that
   re-opens the capacity-conflict finding from the prior check and the symmetric-release question
   comes back — the human does not need to decide this in advance, only know the run will stop and
   escalate if it happens rather than pushing through.
