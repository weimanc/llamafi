# BP candidates — document lifecycle under many agents

> Raised by: Architect, 2026-08-16
> **For QM to evaluate and, if adopted, carry to the human.** Per AGENTS.md, QM brings best-practice
> candidates to the human and never self-promotes — so these are staged here rather than written into
> `best_practices.md`.
> Source: [M-DOCLIFE-keeping-design-docs-alive.md](../architecture/designs/M-DOCLIFE-keeping-design-docs-alive.md)
> Next free ids at time of writing: **BP-064**, and these would derive from a new **LL-134**.

Three candidates. All three are generalisations of **LL-114** — *"artifacts encode truth by copy, with
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
**Rationale**: Measured 2026-08-16: **1 201 `file:line` citations across the corpus; 274 of the 576 in
live documents (48 %) are already broken** — the file is gone or has fewer lines than the citation.
The mechanism was demonstrated end-to-end inside a single session: `M-CODEQUAL` was written citing
`main.cpp:3484` / `:4101` / `:2976` / `:5769`, and the *same author's next three commits* moved every
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
and was backfilled weeks later, which is why AGENTS.md rule 10 exists at all. A stale `proposed` is
not a cosmetic defect — a cold agent reads it as "not yet built" and may rebuild it.
**Applies to**: All

---

### BP-DOC-3 — An admitted gap beats an invented contract

**Adopted from**: LL-134 (proposed)
**Date adopted**: — *(candidate)*
**Rule**: When a document would need to state something not actually verified — an interface not
read, a mechanism not measured, a dependency not traced — say so explicitly and reserve the space:
mark it `STUB`, state what it must cover, and state that it is not implementable. Do not fill the gap
with a plausible construction. Where a claim *was* checked, say what was checked; where a claim is
later falsified, correct it **in place, visibly**, rather than quietly deleting it.
**Rationale**: The failure this prevents was demonstrated at the start of the same session: an
assertion that certain headers "physically cannot be included from a second `.cpp` — duplicate-symbol
link errors" was written confidently, was **false**, and a staging plan was built on top of it before
anyone checked. `dataTask.h` has 32 declarations and zero definitions, and is already included from
two `.cpp` files. Under many agents the cost is asymmetric: a human who reads a wrong claim tends to
notice and adapt; **an agent takes it as fact and designs against it**, because documents are the only
shared memory between sessions. The mitigation is cheap — `IFC-004/005/006` are reserved stubs that
each say "not yet contracted, blocked on TASK-NNN", and no one can implement the wrong thing against
them.
**Applies to**: All

---

## Note for QM

These are worth considering as **one adoption or none**. They are three faces of a single lesson:
a document is a mirror of a fact, and every mirror needs either a gate or a discipline that stops it
drifting. BP-DOC-1 has a gate coming (`run/check-docs` C1, spec'd in
[M-DOCLIFE-check-docs-spec.md](../architecture/designs/M-DOCLIFE-check-docs-spec.md)); BP-DOC-2 has a
partial one (C4); **BP-DOC-3 can never have one**, which is exactly why it needs to be a practice.

The supporting evidence would be a single lessons-learned entry, LL-134, covering the 2026-08-16
session in which all three failure modes occurred within one working day — including custody loss
(four architecture documents swept into an unrelated commit by a parallel session) and an id
collision (TASK-451/452 reserved in a document while another session was already using them). Both
are multi-agent failure modes with no single-agent equivalent, and neither is addressed by the three
rules above — they belong to PM's process recommendations in M-DOCLIFE §3.
