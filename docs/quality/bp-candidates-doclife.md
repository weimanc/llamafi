# BP candidates — document lifecycle under many agents

> Raised by: Architect, 2026-08-16
> **For QM to evaluate and, if adopted, carry to the human.** Per AGENTS.md, QM brings best-practice
> candidates to the human and never self-promotes — so these are staged here rather than written into
> `best_practices.md`.
> Source: [M-DOCLIFE-keeping-design-docs-alive.md](../architecture/designs/M-DOCLIFE-keeping-design-docs-alive.md)
> Next free ids at time of writing: **BP-064**, and these would derive from a new **LL-134**.

**Dispositioned by @QM, 2026-08-16 — read this first.** Two adopt, one does not. My original framing
below said *"one adoption or none"*; **@QM rejected that bundling and was right to.** QM named it a
mild instance of the exact failure `tasks-winamp-player.md` records — a persuasive bundle is the shape
to distrust by default, independent of whether it happens to be partly correct. BP-DOC-1 and BP-DOC-2
are independently strong and independently gateable; bundling them with a weaker third would have
forced either lowering the bar or blocking two good candidates to carry one.

| candidate | QM disposition |
|---|---|
| **BP-DOC-1** cite symbols, not coordinates | **ADOPT** — clears the BP-063/BP-049 bar |
| **BP-DOC-2** landed work says so, with the commit | **ADOPT, with a mandatory citation fix** (applied below) |
| **BP-DOC-3** an admitted gap beats an invented contract | **DO NOT MINT** — fold into a **BP-060 scope widening** instead (§BP-DOC-3 below) |

Two candidates are generalisations of **LL-114** — *"artifacts encode truth by copy, with
nothing but a comment binding them; the copies rot invisibly because they have no gate"* — moved up
one altitude from host tools to documents.

---

### BP-DOC-1 — Cite symbols, not coordinates

**Adopted from**: LL-134 (proposed)
**Date adopted**: — *(candidate)*
**Rule**: In any document intended to be true now — ADR, design doc, IFC, task entry, `CLAUDE.md` —
refer to code by **symbol**: `cmdGet`, `dataTaskStorage.cpp :: fetchWeather`,
`winampDisplay.h :: handleWinampInput`. Do **not** cite a bare `file.ext:NNN` coordinate as the
primary reference. A line number may follow a symbol as a convenience (`fetchWeather`,
`dataTaskStorage.cpp:248`), but the symbol must be present so the reference survives without it.
Historical records — `tasks-archive.md`, `lessons_learned.md`, `audit_log.md`, `docs/rnd/` — are
exempt: they describe the tree as it was, and their coordinates are correct as history.
**Rationale**: Measured 2026-08-16 over the **gated corpus** (223 live docs; historical records
exempt per §1 of the check-docs spec): **274 of 576 `file:line` citations — 48 % — are already
broken** — the file is gone or has fewer lines than the citation.
The mechanism was demonstrated end-to-end inside a single session: `M-CODEQUAL` was written citing
`main.cpp:3484` / `:4101` / `:2976` / `:5769`, and the *same author's next three commits* moved every <!-- check-docs: ignore-line -->
one. In the same document, every reference by symbol name survived unchanged. The asymmetry is not
about care — the line-number document was written carefully — it is that coordinates are a mirror of
a fact that moves, and symbols are the fact.
**Applies to**: All

---

### BP-DOC-2 — A document describing landed work says so, with the commit

**Adopted from**: LL-134 (proposed)
**Date adopted**: — *(candidate)*
**Rule**: The moment work described by a design doc or ADR lands, its status changes to
`partially landed` or `accepted` **and names the commit(s)**, with an as-built section recording what
actually shipped and — explicitly — **how it deviated from the document**. Architecture documents use
a closed status vocabulary: `proposed` | `accepted` | `partially landed` | `superseded` | `rejected`.
`draft` is retired. Status is updated in the same commit as the work, never as a follow-up.
**Rationale**: Two failure shapes, both observed. (1) `M-NOART` sat at `draft` from 2026-05-20 while
half of it shipped under TASK-062; a later session had to re-derive from source which half — and
concluded wrongly at first that `cheapYellowLCD.h` was droppable, when it still owns the global `tft`
object and `WinampDisplay`'s base class. (2) The July 2026 ADR sweep found **nine** ADRs stuck at
`proposed` after being implemented, requiring a nine-way disposition pass with code evidence.
Follow-up status tasks do not get done: M-PR-LOCATIONS shipped TASK-315..325 with zero matrix entries
and was backfilled weeks later — which is why `docs/agents/architect.md:20` ("Reserve registry entries
at design time") exists at all. *(Citation corrected on @QM review: the original said "AGENTS.md rule
10". `AGENTS.md` has no numbered rules — the rule is real but lives in `architect.md`. A misfiled
pointer, not an invented one, inside the document arguing for accurate references.)* A stale `proposed` is
not a cosmetic defect — a cold agent reads it as "not yet built" and may rebuild it.
**Applies to**: All

---

### BP-DOC-3 — **withdrawn as a new entry; re-proposed as a BP-060 scope widening**

**@QM disposition, 2026-08-16: do not mint a new number.** I accept it. But the *reason* matters,
because it changes the edit:

QM argued BP-DOC-3 "substantially overlaps" **BP-060** and **BP-046**. I checked both, and it does not.
**BP-060 is scoped to handover prompts** — *"When briefing a fresh or continuing agent, mark each
diagnostic claim as measured / inferred / assumed."* An ADR or an IFC is not a handover prompt.
**BP-046** is narrower still: design-doc claims about preview/PoC tools. Neither reaches this
session's failures, so "duplicate" overstates it.

What *is* true, and is the better argument, is that **BP-060's rationale is precisely this disease**:

> *"Delegation multiplies the cost of an unverified assertion: a theory a single engineer would test
> in five minutes instead becomes hours of plausible-looking work across several agents."*

That is exactly what happened here, one altitude up. A false duplicate-symbol claim became a
four-stage plan. Two overgeneralised IFC-002 invariants became five reserved test ids, two of which
had to be discarded once someone checked.

**Proposed amendment to BP-060** — widen the scope clause, leave the rule's substance intact:

> **Rule (amended):** When briefing a fresh or continuing agent, **or writing any document a cold
> agent will treat as fact — an ADR, a design doc, an interface contract —** mark each diagnostic
> claim with how it was established: **measured** (with the evidence), **inferred from X**, or
> **assumed**. Where a document would need to state something not actually verified, say so and
> reserve the space (`STUB`, "blocked on TASK-NNN") rather than filling the gap with a plausible
> construction. …*(remainder unchanged)*

**New evidence to append to BP-060's rationale**: the 2026-08-16 architecture pass. Nine design docs,
two ADRs and three IFCs in one day; three independent reviewers raised nine findings and **eight were
confirmed**, including an IFC invariant that was false about one of its own named examples and another
that asserted a universal while citing a source whose own table contradicted it. The mitigation that
worked was already in use in the same session — `IFC-004/005/006` are reserved stubs saying "not yet
contracted, blocked on TASK-NNN", and nobody can implement the wrong thing against them.

*(This is QM's call to carry to the human as a BP-060 edit, not mine to land.)*

---

## Note for QM

~~These are worth considering as one adoption or none.~~ **Withdrawn — see the disposition table at
the top.** QM rejected the bundling and I accept it: BP-DOC-1 and BP-DOC-2 stand on their own evidence
and their own gates (C1 and C4 respectively), and BP-DOC-3's lesson lands better as a BP-060 widening
than as a third number.

One correction to my own framing while withdrawing it: I claimed all three generalise LL-114. **They
do not.** LL-114's shape is *decay* — a fact true when written, rotting because nothing re-checks it.
BP-DOC-3's precedent is **fabrication at write time**: the duplicate-symbol claim was never true. QM
caught this, and it matters for retrieval — filing a fabrication lesson under a decay lesson misfiles
it for whoever searches next.

The supporting evidence would be a single lessons-learned entry, LL-134, covering the 2026-08-16
session in which all three failure modes occurred within one working day — including custody loss
(four architecture documents swept into an unrelated commit by a parallel session) and an id
collision (TASK-451/452 reserved in a document while another session was already using them). Both
are multi-agent failure modes with no single-agent equivalent, and neither is addressed by the three
rules above — they belong to PM's process recommendations in M-DOCLIFE §3.

---

## Staged for QM to land — LL-134 and an audit-log entry

Drafted by @QM on review, 2026-08-16. **QM owns `lessons_learned.md` and `audit_log.md`; these are
staged here, not landed.** Architect corrections are marked inline — two of QM's supporting claims
needed narrowing, and one new fact emerged after the draft was written.

### LL-134 (draft)

**Context**: A one-day architecture pass produced nine design docs, two ADRs and three IFCs. A
three-reviewer chain (Developer → VE → QM) raised nine findings; **eight were confirmed**, none
rejected outright. The errors sat inside contracts written the same day, including an IFC invariant
false about one of its own named examples.

**Observation**: **Two failure classes co-occurred and must not be merged into one lesson.**
*(This is QM's central insight and the reason this is a new entry rather than an LL-114 amendment.)*

1. **Decay** — a fact true when written, rotting because nothing re-checks it. LL-114's shape:
   positional citations, stale status, dangling ids.
2. **Fabrication** — a claim written as fact, never checked, false from the moment of writing: the
   duplicate-symbol-linkage claim; IFC-002's two overgeneralised invariants; a misfiled `AGENTS.md
   rule 10` citation.

Neither was caught by the author. Both were caught by external review.

> **Architect correction 1.** QM called the `AGENTS.md rule 10` citation *fabricated*. Verified: the
> rule is real (`docs/agents/architect.md:20`) but AGENTS.md has no numbered rules — a **misfiled
> pointer, not an invented one.** Weaker than QM framed it, and it belongs in the *decay* class more
> than the fabrication one.
>
> **Architect correction 2.** QM's supporting claim that the fabrication lesson "duplicates BP-060 /
> BP-046" does not hold — BP-060 is scoped to handover prompts, BP-046 to preview-tool claims;
> neither reaches an ADR or IFC. The disposition (widen BP-060) survives; the reason changes from
> *redundancy* to *right home, wrong scope*.
>
> **New fact, found while applying the fixes.** **Both** QM-found errors recurred elsewhere in the
> same doc set — `rule 10` also in M-DOCLIFE §3, the stale count also in its D1 table row. A fix
> applied at the first hit was not a fix. Any rule this becomes should say: *when a documentation
> error is found, grep the corpus for it before calling it fixed.*

**Root cause**: There is no required step between "written" and "committed as authoritative for other
agents." Self-review is optional and demonstrably insufficient — the author who wrote the
citation-rot warning miscited a rule and quoted two different corpus counts for one claim in the same
session. Output speed and verification are in tension; verification loses by default.

**Suggested improvement**:
(a) **No ADR / design doc / IFC gates other work, or is cited as fact by another agent, until at
least one independent review has run against it.** *(This is the load-bearing recommendation —
escalated as E-03.)*
(b) Decay gets the mechanical treatment: BP-DOC-1 + `run/check-docs` C1–C5, with C1 in `delta` mode.
(c) Fabrication folds into a **BP-060 scope widening**, not a new number.
(d) **Track reviewer hit-rate** (confirmed / raised) across future passes as a leading indicator — a
sustained near-100 % rate says the authoring pace needs a brake, not that review should be trusted
less.

**Status**: draft — pending human sign-off.

### audit_log.md entry (draft)

**Triggered by**: QM review, overnight reviewer chain (`ESCALATIONS-2026-08-16.md`).
**Areas checked**: documentation currency, scoped to the 2026-08-16 architecture output — not a full
sweep.

**Findings**: eight confirmed errors from nine raised across three independent reviewers, zero
rejected. QM's own pass found the seventh in the one document nobody else was scoped to read
(`bp-candidates-doclife.md`) — a coverage gap in the chain, not a one-off miss. Two errors recurred at
a second site after being fixed at the first.

**Actions**: Architect — corrections applied (`38edadb`, `e97e7d3`, `2d1d0ac`). QM — BP-DOC-1 and
BP-DOC-2 staged for sign-off; BP-DOC-3 folded into a BP-060 amendment; LL-134 drafted. PM — consider
(a) above as standing process, and track reviewer hit-rate.

**Resolution**: open — pending human review.
