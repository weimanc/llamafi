# Design — M-DOCLIFE: keeping architecture docs alive under many agents

> Owner: Architect (proposing) — **decisions here belong to PM (process) and QM (adoption)**
> Status: proposed
> As-built: 2026-08-16
> Date: 2026-08-16
> Tracked-as: TASK-474
> Consulted: @PM (§3), @QM (§4). BP candidates in §4 are **candidates** — per AGENTS.md, QM brings
> them to the human and never self-promotes.

**The question.** The project now carries 61 ADRs, ~100 design docs, 6 IFCs, 81 features and 64
matrix entries, written and consumed by many agents with no shared memory between sessions. How do
these stay true?

---

## 1. This session is the case study

Not a hypothetical. Over roughly one working day, in one session:

| Failure | What happened |
|---|---|
| **Positional rot** | Wrote M-CODEQUAL citing `main.cpp:3484`, `:4101`, `:2976`, `:5769`. My own next commits moved every one of them. Stale **within a day of writing.** | <!-- check-docs: ignore-line -->
| **Status rot** | M-SRCLAYOUT described Stages A/B as `proposed` while they were already committed. |
| **Reference rot** | Reserved TASK-451/452; a parallel session had already taken both. Renumbered 18 references. |
| **Custody loss** | All four documents were swept into `c7686aa`, an unrelated arena fix, by another session's `git add`. The commit message describes none of them. |
| **Fact rot** | Found `cross_feature_matrix.yaml` X015 asserting `dataTask` runs on Core 0. It pins to `APP_CPU_NUM`, and never did otherwise. |
| **Count rot** | `run/check` gate count read 5 (CLAUDE.md ×2), `6/6` (ADR-059 ×2) and `[6/7]` (appRegistry.h) against an actual 7. |

Scale of the exposure: **274 of 576 `file:line` citations in the gated corpus are already broken —
48 %.** Every surviving one is a hostage to the next refactor.

> *Corrected on @QM review, 2026-08-16.* This line and its sibling in `bp-candidates-doclife.md`
> quoted **1 171** and **1 201** for the same claim — two unlabelled corpora (`docs/` vs
> `docs/` + `CLAUDE.md`), same author, same session, neither stated which. Both are now stale anyway
> (1 188 / 1 236 today). A citation-count inconsistency inside the document diagnosing citation
> inconsistency. Fixed by dropping the corpus-wide figure entirely and keeping only the gated-corpus
> ratio, which is the number any decision actually turns on.

None of this was carelessness — each document was accurate when written. **That is the point.**
Accuracy at write time is not the problem; *decay* is, and decay has no owner.

## 2. The five decay modes

| # | Mode | Detectable? | Precedent |
|---|---|---|---|
| **D1** | **Positional** — `file:line` moves | **yes, cheaply** | this session; 274 of 576 gated citations already broken |
| **D2** | **Mirrored fact** — a doc/tool copies a firmware truth | **yes** | **LL-114**, TASK-335 |
| **D3** | **Status** — landed work still marked `proposed` | **yes** | July sweep found 9 stale-`proposed` ADRs |
| **D4** | **Dangling reference** — points at a deleted thing | **yes** | `run/ceefax-ws-soak` → deleted env |
| **D5** | **Scope** — task closed with residual scope | **no — human judgement** | M-NOART closed; the base-class coupling it left is still open |

D1–D4 are mechanical. **D5 is not, and no gate will catch it** — that one needs review.

## 3. @PM — process and ownership

**PM position: doc updates belong in exit criteria, never in a follow-up task.**

The evidence is already in the tracker. M-PR-LOCATIONS shipped TASK-315..325 with **zero** matrix
entries, backfilled weeks later. `docs/agents/architect.md:20` ("Reserve registry entries at design
time") exists *because* end-of-work discipline failed once already. *(Citation corrected on @QM
review — the original said "AGENTS.md rule 10"; AGENTS.md has no numbered rules. Second instance of
the same misfiled pointer in this document set.)* A follow-up doc task is a task that competes with feature work and loses.

**PM recommendations:**

1. **Any task that moves or deletes code carries a `docs-touched:` line in its exit criteria**,
   naming the documents it invalidates. Not "update docs" — the specific files.
2. **Milestone close gets a doc-sweep gate**, alongside the existing `run/check` gate. A milestone is
   not closed while its own design doc still describes its work as proposed.
3. **Status vocabulary is closed and mandatory**: `proposed` | `accepted` | `partially landed` |
   `superseded` | `rejected`. Currently ADRs use four of these informally and design docs use
   `draft` as a sixth.
4. **Task-number reservation must be atomic.** This session collided because reservations lived only
   in an unpushed document. PM owns `tasks.md`; reservations should land there as placeholder rows
   the moment a design doc claims them — which is already the pattern used for the split-out
   M-WINAMP-PLAYER board.

## 4. @QM — audit, lessons, enforcement

**QM position: this is LL-114 generalised, and LL-114 already prescribed the fix.**

LL-114's root cause reads: *"host tools encode firmware truth by copy, with nothing but a comment
binding them; the copies rot invisibly because they have no gate — they're only exercised when a
human reaches for them, which is exactly when they must not lie."*

Replace "host tools" with "design docs" and it is the same lesson at a different altitude. LL-114's
answer was **parse, don't mirror**. The documentation equivalent:

> **BP candidate — cite symbols, not coordinates.** In any document, refer to `cmdGet` or
> `dataTaskStorage.cpp :: fetchWeather`, not `main.cpp:3484`. Symbol names survive refactors; line <!-- check-docs: ignore-line -->
> numbers do not. This session proved both halves in one day: every symbol reference in M-CODEQUAL
> survived Stages A/B; every line number broke.

> **BP candidate — a document describing landed work says so, with the commit hash.** "Status:
> partially landed (`78caa95`), unreviewed" is checkable. "Status: proposed" on landed work is a
> silent lie that a cold agent will act on.

> **BP candidate — an admitted gap beats an invented contract.** IFC-004/005/006 are stubs that say
> what they must cover and that they are not implementable. A confidently-written contract for an
> interface nobody read is worse than a marked hole.

**QM recommendation: make D1–D4 a gate, because unenforced rules do not survive many agents.**

This is the same finding as IFC-002's enforcement table: of nine concurrency invariants, only the one
with a `configASSERT` stopped recurring. Conventions decay; checks do not.

Proposed `run/check-docs` — all greps, seconds to run:

| Check | Catches | Cost |
|---|---|---|
| every `file.ext:NNN` cites an existing file with ≥ NNN lines | D1 | trivial |
| every `TASK-NNN` / `ADR-NNN` / `IFC-NNN` / `X0NN` referenced exists | D4 | trivial |
| every env named in `docs/` exists in `app/platformio.ini` | D4 | ADR-061 D7 already specifies this |
| every `**Status**:` uses the closed vocabulary | D3 | trivial |
| no ADR sits in `proposed` beyond N days without a note | D3 | needs a date field |
| relative doc links resolve | D4 | trivial |

Deliberately **not** in scope: D5. No gate detects "this task closed with work left over." That stays
a QM retrospective question, and pretending otherwise would give false assurance.

## 5. The multi-agent point

Everything above holds for one careful human. What changes with many agents is **the cost of a wrong
document.**

A human reading `main.cpp:3484` and finding something else notices and adapts. **An agent takes it as <!-- check-docs: ignore-line -->
fact**, and may edit on that basis — this session began with me asserting a duplicate-symbol linkage
barrier that did not exist, and designing around it, until it was checked. Docs are the only shared
memory between agent sessions; a stale doc is not a stale doc, it is **an instruction**.

Two consequences:

- **Every document needs a cold-open header** — status, what landed, what is unverified — because
  every agent arrives with no context. M-SRCLAYOUT §5a is the shape: commits, real numbers, and the
  deviations stated rather than left to be discovered.
- **Write what was *checked*, not what was *believed*.** Several statements in this session's docs
  are wrong-and-corrected in place, with the correction visible. That is the correct form: a future
  agent needs to know the claim was tested, and a struck-through claim stops it being re-derived.

## 6. Recommendation

| # | Action | Owner | Status |
|---|---|---|---|
| 1 | `run/check-docs` implementing the §4 table | Developer, spec by Architect | **DONE** — see TASK-475/508 |
| 2 | `docs-touched:` in exit criteria for code-moving tasks | PM | **DONE 2026-08-27** — [BP-070](../../quality/best_practices.md#bp-070) |
| 3 | Closed status vocabulary, applied across ADRs and designs | PM + Architect | **DONE** — TASK-508, 189 headers, 0 non-conforming |
| 4 | Three BP candidates in §4 → human | **QM** | open |
| 5 | Task-number reservations land in `tasks.md` immediately | PM | **DONE 2026-08-27** — [BP-071](../../quality/best_practices.md#bp-071) |
| 6 | Doc-staleness sweep as a milestone-close gate | PM + QM | open |

**Do 1 and 4 first.** The gate makes D1–D4 self-correcting from then on, and the BPs change what gets
written next — both compound. 2/3/5/6 are process changes that need PM's scheduling judgement and the
human's assent.

## 7. Open questions

- **OQ1** — is `run/check-docs` part of `run/check` (blocking, ~seconds) or separate? Lean: separate
  and advisory first, promoted to blocking once the existing 1 171 citations are cleaned, or it fails
  on day one and gets disabled.
- **OQ2** — do we mass-convert existing `file:line` citations to symbols, or only enforce
  going forward? Lean: enforce forward, convert opportunistically. A 1 171-citation sweep is its own
  milestone and would itself go stale mid-flight.
- **OQ3** — should design docs expire? An ADR is permanent by nature (a decision record). A design doc
  is a snapshot of thinking. Marking superseded design docs would stop cold agents mining dead
  designs — this session read M-NOART (status `draft`, 2026-05-20) and had to work out from source
  that half of it had shipped.
