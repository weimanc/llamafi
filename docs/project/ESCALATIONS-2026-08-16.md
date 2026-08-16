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
| **E-02** | `dataTaskStorage.cpp` | **A live divergence, not a doc issue.** `fetchWeather` resumes Spotify's TLS **after** its JSON parse; `fetchCrypto` **before** — and a comment claims they match. One is wrong, or it is deliberate and undocumented. Which timing is correct? | **Needs someone who knows the intent.** Resume-before-parse gives Spotify heap back sooner but lets it reconnect *during* a parse — on this device that is the TASK-289 shape. Resume-after is safer and slower. I lean **after** (weather's behaviour), but this is a judgement about a real runtime tradeoff. Filed TASK-495; it **gates** TASK-458. |

---

## 2. STATE — how to resume

**Reviewer chain, ONE AT A TIME, never concurrent:**

| # | Reviewer | Scope | Status |
|---|---|---|---|
| 1 | @Developer | ADR-060, M-SRCLAYOUT, M-CODEQUAL | **DONE** — 3 MAJOR accepted, all verified true |
| 2 | @VE | IFC-002, IFC-003, M-CONCURRENCY, M-TESTARCH, reserved test ids | **DONE** — 1 BLOCKER + 2 MAJOR, all verified true; IFC-002 → v2 |
| 3 | @QM | M-DOCLIFE, check-docs spec, 3 BP candidates | **RUNNING** |
| 4 | @PM | `tasks-architecture.md`, sequencing, M-ARCH split | not started |

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
