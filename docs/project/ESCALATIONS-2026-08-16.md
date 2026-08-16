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
| — | — | — | — |

---

## 2. STATE — how to resume

**Reviewer chain, ONE AT A TIME, never concurrent:**

| # | Reviewer | Scope | Status |
|---|---|---|---|
| 1 | @Developer | ADR-060, M-SRCLAYOUT, M-CODEQUAL | **RUNNING** (spawned ~02:30) |
| 2 | @VE | IFC-002, IFC-003, M-CONCURRENCY, M-TESTARCH, reserved test ids | not started |
| 3 | @QM | M-DOCLIFE, check-docs spec, 3 BP candidates | not started |
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
