# Overnight architecture review — running log and escalations

> Started 2026-08-16 ~02:30 by the Architect, at the human's request, to run unattended overnight.
> **The human reads this file first in the morning.** §1 is what needs their judgement; §2 is the
> state machine for resuming; §3 is the running log.
>
> Scope: review and refine the design docs produced on 2026-08-16 (nine designs, ADR-060/061,
> IFC-002/003 + three stubs). **No `app/src` code edits** — docs only.

---

## 1. ESCALATIONS — need human judgement

Nothing escalated yet. Entries appear here as `E-NN` with the decision needed and my recommendation.

| id | doc | question | my lean |
|---|---|---|---|
| **E-01** | ADR-060 | I narrowed the ADR to authorise **Stages A+B only**; C/D/E/F now need a separate ADR. This reverses a sign-off you have not given yet, in the conservative direction. Confirm? | **Accept the narrowing.** @Developer's argument is strong and matches M-SRCLAYOUT §5b's own lean: A+B already captured most of the listed benefits at near-zero risk; Stage E's distinct win is build time, which nobody here has ever complained about; and two of Stage E's costs were underweighted (wrong budget axis, and a composition-root gap four documents missed). |
| **E-05** | **scheduling** | **@PM: this whole board should lose to closing M-WINAMP-PLAYER.** That milestone is paused over work quality with 12 open entries; this board reproduces two of its three diagnosed failure modes on a compressed timescale, in the same week. Do you want the M-ARCH programme scheduled at all, or M-WINAMP-PLAYER resumed first? | **@PM is right and I do not overrule it.** I produced this board; PM is the scheduler and read it cold. Recommended next session, in order: **TASK-488 + 497 in one DUT block** → decide 455/456/471/472 on what it finds → **495 folded into 458** → **466** → **475** → **478** → then M-WINAMP-PLAYER (PM would put **TASK-424**, the SD write panic, ahead of most of this board if DUT time is scarce). |
| **E-03** | process | QM proposes a standing rule: **no ADR / design doc / IFC gates other work, or is cited as fact by another agent, until at least one independent review has run against it.** Adopt? | **Adopt.** Eight confirmed errors from nine raised, across three reviewers, in one day's output. The rule is the only one of QM's recommendations that would have prevented all of them. Cost is real — it serialises authoring behind review — which is why it is yours to decide, not mine. |
| **E-04** | `best_practices.md` | Land **BP-DOC-1** (cite symbols, not coordinates) and **BP-DOC-2** (landed work says so, with the commit) as new entries, and amend **BP-060** to widen its scope from handover prompts to any document a cold agent treats as fact? | **Yes to all three.** BP-DOC-1 has a measured baseline and a gate; BP-DOC-2 has two real precedents; the BP-060 widening replaces what would have been a redundant BP-DOC-3. Drafts are staged in `docs/quality/bp-candidates-doclife.md`. |
| **E-02** | `dataTaskStorage.cpp` | **A live divergence, not a doc issue.** `fetchWeather` resumes Spotify's TLS **after** its JSON parse; `fetchCrypto` **before** — and a comment claims they match. One is wrong, or it is deliberate and undocumented. Which timing is correct? | **Needs someone who knows the intent.** Resume-before-parse gives Spotify heap back sooner but lets it reconnect *during* a parse — on this device that is the TASK-289 shape. Resume-after is safer and slower. I lean **after** (weather's behaviour), but this is a judgement about a real runtime tradeoff. Filed TASK-495; it **gates** TASK-458. |

---

## 2. STATE — how to resume

**Reviewer chain, ONE AT A TIME, never concurrent:**

| # | Reviewer | Scope | Status |
|---|---|---|---|
| 1 | @Developer | ADR-060, M-SRCLAYOUT, M-CODEQUAL | **DONE** — 3 MAJOR accepted, all verified true |
| 2 | @VE | IFC-002, IFC-003, M-CONCURRENCY, M-TESTARCH, reserved test ids | **DONE** — 1 BLOCKER + 2 MAJOR, all verified true; IFC-002 → v2 |
| 3 | @QM | M-DOCLIFE, check-docs spec, 3 BP candidates | **DONE + INTEGRATED** (`38edadb`, `e97e7d3`, `2d1d0ac`, `728fb15`) |
| 4 | @PM | `tasks-architecture.md`, sequencing, M-ARCH split | **DONE + INTEGRATED** (`b540f4c`) — chain complete |

**Self-review passes** (do these while a subagent runs — never touch a doc a running agent owns):

| doc | status |
|---|---|
| ADR-061 (build-variant hygiene) | not started |
| M-TOOLING | not started |
| M-DOCLIFE + check-docs spec | not started |
| IFC-002 / IFC-003 | not started |
| The five skeletons | not started |

**Resume procedure**
1. Integrate any completed subagent review — accept / amend / reject **each finding yourself**, amend
   the docs, commit. Do not accept a finding without checking it against the code.
2. Otherwise pick the next unreviewed doc and self-review, verifying every claim against source.
3. Spawn the next reviewer in the chain, one at a time.
4. Append escalations to §1, log to §3, commit each increment.

---

## 3. LOG

### 02:30 — chain started
- Spawned @Developer on ADR-060 + M-SRCLAYOUT + M-CODEQUAL.
- Brief carried three standing mandates, applied to every reviewer:
  1. **Attack the framing, not just the contents.** The `tasks-winamp-player.md` PM note records that
     on the last milestone *"three team reviews each improved the arena argument, none asked where
     the memory went"* — review reinforced a wrong frame. A review that only refines inside my
     framing is a failed review.
  2. **Verify every claim against code.** The Architect made two factual errors this session that
     only re-checking caught: a false "these headers cannot be included from a second `.cpp`" claim
     that a four-stage plan was built on, and `mb_arena` reported as 13/8 acquire/release when the
     real figure is 4/7 (the rest were declarations and `#else` no-op inlines).
  3. **Findings cite `file:symbol`, carry a severity, and end in accept / amend / reject** — so they
     can be acted on rather than admired.
- Scheduled hourly wakeup; the human's 5-hour allowance resets ~05:00.

### ~03:00 — @Developer review integrated (commit `b4ca2ff`)
Three MAJOR findings. **I verified all three against source before accepting; all three were right.**

- **F1** ADR-060 D2's composition root is not implementable as sketched — 3 of 13 apps are
  `#ifdef WINAMP_DISPLAY` and `g_apps[]` already forks. → TASK-496, Stage D definition-of-done.
- **F2** M-CODEQUAL C1 was wrong: two skeletons (buffered vs streaming), not one — *and* it hid a
  live weather/crypto `tlsResume()` divergence a guard would have silently changed. → TASK-495 (E-02).
- **F3** The memory gate measured the wrong axis: `-fno-lto` is unconditional on this toolchain and
  ADR-059 measured 88 B DRAM vs 3 984 B flash. Stage E now gates flash too.

**The review also worked as intended on framing** — it attacked the ADR's premise rather than
refining inside it (E-01), which is exactly what the M-WINAMP-PLAYER post-mortem said the last round
of reviews failed to do. It independently re-verified the `mb_arena` 4/7 figure and D5's
constructor claim; both hold.

**Cost note:** ~130 k subagent tokens for that review. At that rate the remaining three reviewers fit
comfortably in the overnight budget.

### ~03:30 — @VE review integrated (commits `55913fd`, `bd7282d`)
**1 BLOCKER + 2 MAJOR, all verified against source before accepting, all correct — and all three were
errors in contracts I wrote yesterday.**

- **BLOCKER, IFC-002 I5**: I asserted "*every* cross-context result carries a monotonic seq or epoch",
  citing IFC-001 as the house standard **while contradicting IFC-001's own table**, which records
  *"none (single consumer)"* for five of nine result types. IFC-001's rule 5 is conditional; I wrote a
  universal from it. Restated; real set is 3 of 9. `T_CC_04` discarded — it tested a false claim.
- **MAJOR, IFC-002 I4**: "pump-task callbacks may only set a flag" was **false about one of its own
  four named examples** — `audio_process_extern` runs a rectified peak scan and a 19-band Goertzel
  every decoded block. Split into I4a/I4b. `T_CC_03` discarded.
- **MAJOR, I1 enforcement**: I claimed "guaranteed by construction after TASK-458". That task is open
  and gated on TASK-495 (E-02, unresolved). Corrected to what it actually is: manual comment
  discipline — the discipline that already failed once, in TASK-222.

**VE overturned one of my own notes**, which is the review working: I had pre-labelled `T_CC_01` as
"review-shaped". VE checked — zero `tft.` hits in the three non-loopTask TUs — and ruled it a genuine
automatable grep, provided it walks one level of call-graph closure. Kept as a test.

**Net on the reserved ids: 2 of 5 discarded because the invariants they tested were factually wrong.**
That is a better outcome than 5 of 5 passing would have been.

Also: `T_CQ_03`'s grep as printed matches `TASK-320` and `111.320` — noise, not signal. Must not be
adopted as a gate unscoped. Filed TASK-497 (retrospective baseline — window is **not** closed, costs
2× DUT time), TASK-498 (`T_SRC_09`), TASK-499 (G1 has no test id at all).

**Pattern worth noting for the morning:** two reviewers, six confirmed errors, **zero rejected
findings.** Every single challenge has held up on verification. That says the docs were written faster
than they were checked — which is exactly what BP-DOC-3 (candidate) is about.

### ~04:00 — @QM review received. **NOT YET INTEGRATED — this is the resume point.**
Hit the usage checkpoint mid-verification. The review is captured below; the doc amendments are not
made. **Resume here.**

QM's dispositions: **BP-DOC-1 adopt** · **BP-DOC-2 adopt with a mandatory citation fix** ·
**BP-DOC-3 reject as a new number — fold into a BP-060 amendment instead** (it duplicates BP-060 and
BP-046, and its claimed LL-114 lineage does not hold: LL-114 is about *decay*, BP-DOC-3's precedent is
about *fabrication at write time* — a different failure class). QM also **rejected my "one adoption or
none" bundling**, and named it a mild instance of the very framing failure this chain exists to catch.
QM drafted **LL-134** and an **audit_log entry**, and recommends amending the check-docs spec to add a
**delta-only blocking mode for C1** (fail only on *newly introduced* positional citations) rather than
accepting advisory-forever.

**The first reviewer finding that does NOT fully hold — recorded because I said I would record these.**
QM's F1 calls "AGENTS.md rule 10" a *fabricated* reference. I verified: AGENTS.md indeed has **no
numbered rules** (QM is right about that), **but the rule exists** — `docs/agents/architect.md:20`,
"Reserve registry entries at design time." So it is a **misfiled citation, not an invented one**. The
fix is a corrected pointer, not a replacement citation. Severity drops from MAJOR to MINOR; QM's
conclusion that BP-DOC-2 must be fixed before promotion still stands.

Its F2 (1 171 vs 1 201 citation counts) **is** a real inconsistency — the two figures measure
different corpora (`docs/` vs `docs/` + `CLAUDE.md`) and neither was labelled. Both are also now stale:
today's figures are **1 188** and **1 236**. Fix by stating the corpus with the number, or by dropping
the corpus-wide figure and keeping only the live-doc one (274/576), which is the number that matters.

**Reviewer hit-rate is now 8 confirmed / 9 raised** across three reviewers — still the strongest
signal in this whole exercise.

### ~04:15 — QM's F5 verified. Disposition right, reasoning needs correcting.
QM says BP-DOC-3 *"substantially overlaps"* BP-060 and BP-046, so it should fold into a BP-060
amendment rather than take a new number. **I checked both. The disposition is right; the stated reason
is not, and the difference changes the amendment's wording.**

- **BP-060** is scoped to *handover prompts* — "When briefing a fresh or continuing agent, mark each
  diagnostic claim as measured / inferred / assumed." An ADR or IFC is not a handover prompt, so
  **BP-060 as written does not cover this session's failures at all.**
- **BP-046** is scoped to *design-doc claims about preview/PoC tools* — narrower still.

So it is **not** already covered, and "duplicate" overstates it. What is true — and is the stronger
argument — is that **BP-060's *rationale* is precisely this disease**: *"Delegation multiplies the cost
of an unverified assertion: a theory a single engineer would test in five minutes instead becomes
hours of plausible-looking work across several agents."* That is exactly what happened here at a
different altitude: a false duplicate-symbol claim became a four-stage plan; two overgeneralised
IFC-002 invariants became five reserved test ids, two of which had to be discarded.

**Therefore: fold into BP-060 as QM recommends, but as a genuine scope widening** — from "a handover
prompt" to "a handover prompt, or any document a cold agent will treat as fact (ADRs, design docs,
IFCs)" — not as a redundancy cleanup. Same landing place, materially different edit.

**Reviewer hit-rate: 8 confirmed / 9 raised, plus one finding whose disposition survives but whose
reasoning did not.** Both QM findings I checked (F1, F5) were directionally right and imprecise in the
same way — which is itself worth noting, since QM was the reviewer auditing precision.

### ~04:45 — @QM integrated (`38edadb`, `e97e7d3`, `2d1d0ac`, `728fb15`)
Applied: bundling withdrawn; BP-DOC-2's citation retargeted; BP-DOC-3 withdrawn as a number and
re-proposed as a **BP-060 scope widening**; corpus-count figures dropped in favour of the gated ratio;
**C1 gains a `delta` blocking mode** so it gates new debt from phase 1 instead of sitting advisory
forever. LL-134 and an audit-log entry staged for QM to land (E-04).

**New finding, mine, found while applying the fixes: both QM-found errors recurred at a second site.**
`AGENTS.md rule 10` was also in M-DOCLIFE §3; the stale count was also in its D1 table row. **A fix
applied at the first hit was not a fix.** Folded into LL-134: when a documentation error is found,
grep the corpus before calling it fixed.

**Also corrected my own framing**, on QM's prompting: I had claimed all three candidates generalise
LL-114. They do not. LL-114 is about *decay*; BP-DOC-3's precedent is *fabrication at write time*.
Filing a fabrication lesson under a decay lesson misfiles it for whoever searches next — QM's
sharpest point of the night, and the reason LL-134 exists as its own entry.

### ~05:15 — @PM integrated (`b540f4c`). **REVIEWER CHAIN COMPLETE.**
The last reviewer read the one artefact nobody had checked — the board itself — and its central
finding is about **altitude, not detail** (E-05). Accepted without argument: I produced the board, PM
is the scheduler, and PM read it cold.

Applied: the PM verdict now sits at the **top** of `tasks-architecture.md`; the inflated "47 tasks"
figure corrected to **~10–12 actually actionable**; **TASK-458 marked GATED** — its row said OPEN
while the same file's prose said "gates TASK-458", which would have walked a scheduler into a wall;
455/456/471/472 demoted **P2 → P3** (a five-deep chain whose step 1 has no owner should not outrank
independently actionable work); TASK-497 folded into TASK-488's DUT block; TASK-487 folded into 493.

---

## FINAL TALLY — reviewer chain, 2026-08-16

| Reviewer | Raised | Confirmed | Notes |
|---|---:|---:|---|
| @Developer | 3 | 3 | all MAJOR; one reversed the ADR's own scope |
| @VE | 3 | 3 | 1 BLOCKER; 2 of 5 reserved test ids discarded as testing false claims |
| @QM | 4 | 3 + 1 narrowed | found the 7th error in the doc nobody else was scoped to read |
| @PM | 6 | 6 | the only altitude finding; corrected a live table/prose contradiction |
| **Total** | **16** | **15** | **one finding narrowed, none rejected** |

**Fifteen of sixteen findings held.** Not one reviewer was wrong about the substance of what they
challenged. That is not a sign the reviews were lenient — it is the measurement that matters here:
**same-day architecture output, unreviewed, currently carries a defect rate high enough that shipping
any of it without an independent pass is unsafe.** I am the case study, and E-03 is the fix.

Every error clustered in one authoring shape: **an absolute claim written from a partial or
conditional source.** IFC-002 I5 (universal from a conditional), IFC-002 I4 (universal false about its
own example), the duplicate-symbol claim, the misfiled citation, "every fetch runs the same
sequence", "47 tasks". Same mistake, six times, by one author in one day.

---

## 4. STANDING CONSTRAINTS for this work

- **No `app/src` edits.** Three refactor commits (`a044f5d`, `78caa95`, `b36f184`) already landed
  unreviewed and un-DUT-verified; TASK-488 gates the rest. Adding more unreviewed code overnight
  would compound exactly the problem the human paused M-WINAMP-PLAYER over.
- **Docs only, committed incrementally** so any single bad increment is revertible.
- **Record disagreements, don't smooth them.** If a reviewer and I disagree and neither is clearly
  right, that is an escalation, not something to average out.
- **Task ids 453–494 are filed.** Next free is **495**.
- Reviewer findings that turn out to be *wrong* get recorded as such, with the evidence — a reviewer
  being mistaken is data about the review process, not something to quietly drop.
