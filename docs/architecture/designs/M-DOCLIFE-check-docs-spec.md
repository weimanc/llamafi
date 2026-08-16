# Spec — `run/check-docs`: a staleness gate for architecture documents

> Owner: Architect (spec) — **Developer implements**
> Status: **proposed** — 2026-08-16
> Date: 2026-08-16
> Parent: [M-DOCLIFE-keeping-design-docs-alive.md](M-DOCLIFE-keeping-design-docs-alive.md) §4
> Tracked-as: TASK-475
> Registers: — (tooling; no `feature_inventory.yaml` id, no new cross-feature seam)

Implements the mechanically-detectable half of M-DOCLIFE (decay modes D1–D4). **D5 — a task closed
with residual scope — is deliberately out of scope: no gate detects it, and implying otherwise gives
false assurance.**

**Every baseline below was measured on 2026-08-16 against the tree at `77a9568`.** The counts are the
point of this spec: the checks have wildly different day-one failure counts, and that dictates the
rollout, not preference.

> **Re-measured 2026-08-16 at `efab524`, before implementation (amendments A1–A3).** A pre-execution
> pass re-took every baseline. Two defects would have reached the implementer: **C2's resolution set
> was missing `tasks-architecture.md`** (138 false failures against a spec that says it "now reads 0"),
> and **C1-`delta` — a phase-1 *blocking* check — never defined what it diffs against.** C4's baseline
> was also unreliable: scoped, it is worse than the corpus-wide number quoted for it. Corrections are
> marked **[A1]**, **[A2]**, **[A3]** inline. Drift in the other counts is ordinary decay and changes
> nothing: C1 274/576 → **280/599**, C3 8 → **9**, corpus 292/223 → **233 gated + 69 exempt + CLAUDE.md**,
> C5 **0** (holds).
>
> **A second pass by @Architect then falsified three of these amendments' own numbers** and found
> eleven further defects. Corrections are folded in below and marked **[A-rev]**; the two that matter
> most are that **C4's 91 is struck entirely** (the count depends on a matching rule the spec never
> states — it ranges 100–218 across plausible readings) and that **C1-`delta` blocking in phase 1
> contradicts OQ1**, since nothing invokes `check-docs` until phase 3. Closed in §7.

---

## 1. Corpus and exemptions

292 `.md` files under `docs/`, plus `CLAUDE.md`. **223 are gated ("live"); 69 are exempt.**
*(Re-measured at `efab524`, **corrected after @Architect review**: **302 `.md` under `docs/` = 233
gated + 69 exempt**, and **`CLAUDE.md` is gated**, giving **234 gated** in total. The earlier
"234 / 68" was self-consistent and wrong — it counted `CLAUDE.md` inside the 302. The corpus grows;
the exemption rule is what must stay stable, not the count.)*

**`CLAUDE.md` is in the gated corpus.** Stated explicitly because it is load-bearing and was
previously left to inference: C1 reads **279/598** without it and **280/599** with it, so an
implementer who excludes it cannot reproduce any baseline in this spec.

**Exempt, and why** — this is the most important design decision in the spec. Without it the gate is
unusable and gets disabled on day one:

| Exemption | Reason |
|---|---|
| `tasks-archive.md` | A historical record. Its 132 broken citations describe the tree **as it was** and are *correct as history*. "Fixing" them would falsify the archive. |
| `lessons_learned.md`, `audit_log.md` | Same — a lesson records what was true when learned. |
| `docs/rnd/**` | Experiment reports are dated snapshots, not living specification. |
| `*-review.md` | A review is a point-in-time opinion on a document, not a document. |

**Rule:** a file is gated if it is intended to be *true now*. Historical records are exempt by nature,
not by convenience — and any new exemption needs that justification, or the gate erodes.

> **[A-rev] Exemptions govern which files are SCANNED, never which files are RESOLUTION SOURCES.**
> Stated because the natural misreading is expensive: `tasks-archive.md` is exempt from scanning, but
> **356 `TASK-` ids resolve only there**, so a resolver that honours the exemption produces **1261
> false failures** — measured — in a check scheduled to block at phase 2. The same applies to
> `lessons_learned.md` and `*-review.md`: never scanned, always readable.

## 2. The five checks, with measured baselines

> **Every count in this document is per-occurrence, not per-unique-id** — @Architect review,
> 2026-08-16. This was never stated and the checks silently disagreed: C1's baseline is
> per-occurrence, C2's original "39" was per-unique-id, and §3's output contract
> (`file:line: <what> -> <why>`) can only be per-occurrence. An implementer building to §3 would have
> measured C2 as 138 and assumed their code was broken. **C2's corrected baseline is 138 occurrences
> across 40 unique ids** with the old hardcoded list, **0** with [A1]'s glob.

| id | Check | Baseline (live docs) | Verdict |
|---|---|---|---|
| **C1** | every `file.ext:NNN` resolves to an existing file with ≥ NNN lines | 274/576 → **280 failures / 599 citations** (47 %) | advisory (full) · **blocking (`delta`)** |
| **C2** | every `TASK-`/`ADR-`/`IFC-`/`X0NN` id referenced exists | 22 → **0** with **[A1]**'s glob (**138 occurrences / 40 ids** without) | blocking — precondition met |
| **C3** | every env named in docs exists in `app/platformio.ini` | 8 → **9 failures** (`cyd2usb` joined them, ADR-061 D8) | blocking after ADR-061 D8 |
| **C4** | `Status:` uses the closed vocabulary | ~~67~~ ~~91~~ → **order 100–200, rule undefined** — see **[A3]** | advisory; phase 4 needs its own migration task |
| **C5** | relative `.md` links resolve | **0 failures** (re-confirmed at `efab524`) | **blocking immediately** |

### C1 — positional citations
Regex `([\w./-]+\.(h|cpp|py|ini|sh|yaml|json|md)):(\d+)`, resolved against `.`, `app/`, `app/src/`,
`app/tools/`, `docs/`. Fails if no candidate file exists, or the file has fewer than NNN lines.

Worst live offenders: `M-BOOT-UI.md` (32), `M-SPOTIFY-BOOT-GATE.md` (24), `tasks-winamp-player.md`
(15), `M-TASKBAR-FEEDBACK.md` (12), `test_plan.md` (10).

> **[A-rev] Line ranges.** `file.h:46-53` (as in `CLAUDE.md`'s touch-zone note) matches the regex as
> `46` and silently discards the range. Specified: **a `NNN-MMM` citation checks the HIGHER bound**,
> since that is the one a shrinking file breaks first. Not declaring this leaves each implementer to
> pick, and the two choices disagree on real citations in the corpus.

**Line-overrun is the cheap half and worth keeping even though it under-detects.** A citation whose
file shrank below the line number is *certainly* wrong; one that still has enough lines may point at
unrelated code. C1 catches the certain cases; the BP in §5 is what prevents the rest.

### C2 — identifier existence
**[A1 — corrected 2026-08-16.]** `TASK-NNN` resolves against **every `docs/project/tasks*.md`**,
discovered by glob — today `tasks.md`, `tasks-archive.md`, `tasks-winamp-player.md` and
`tasks-architecture.md`. `ADR-NNN`, `IFC-NNN` against their directories; `X0NN` against
`cross_feature_matrix.yaml`.

> **Why this changed.** The original list was written before `tasks-architecture.md` was split out of
> `tasks.md`, and hardcoded the three files that existed that morning. Measured at `efab524`: **138
> failing occurrences across 40 unique ids** against the hardcoded list — TASK-454, 456, 460–464,
> 467–472, 474 and the rest of the M-ARCH range — versus **0** once the split board is included.
> *(An earlier pass reported "39 ids"; @Architect re-measurement makes it 40 / 138.)* Every one is a false positive, in
> a check the rollout puts *blocking* at phase 2. **Glob, do not enumerate**: the board was split once
> and will be split again, and a hardcoded list turns the next split into a repo-wide gate failure.

~~**All 22 current failures are TASK-453…474**~~ — **resolved.** Those were reservations made in
design docs and not yet filed; PM filed them the same day, and they now live in
`tasks-architecture.md`. **C2 reads 0 at `efab524` with [A1]'s glob** — which is the whole point of
[A1]: the check went from "22 real failures" to "0 real, 138 false" purely because the board moved
house, and the check must follow the board rather than the board remembering the check. That is
exactly the gap M-DOCLIFE §3 recommendation 5 addresses, and the check found it without being told.
ADR and IFC references are already clean (0 failures).

### C3 — build-environment names
Already specified as ADR-061 D7 check 1; folded in here rather than built twice.

Current failures: `cyd2usb_spike`, `cyd2usb_winamp_bands`, `cyd2usb_winamp_debug_ceefaxspike`,
`cyd2usb_winamp_debug_vistap`, `cyd2usb_winamp_envelope`, `cyd2usb_winamp_envelope_rms`,
`cyd2usb_winamp_vistap2`, plus `cyd2usb_base` (a name ADR-061 D8 *proposes* but has not created).

**Note this found six dead envs that a manual sweep earlier in the same session missed** — the
manual pass caught only `ceefaxspike`. Mechanical beats attentive.

*Implementation note:* ADR-061 D7 check 3 requires prose to name **which** `platformio.ini`, since two
projects here share env names. C3 should resolve against `app/platformio.ini` and report an
unqualified reference as a warning, not an error.

> **[A-rev] What counts as "an env named in docs" — the check was unimplementable without this.**
> "Every env named in docs" has no detection rule, and the choice of rule moves the count: a naive
> token match yields 11 unique bad names, and this spec's 9 is only recoverable by silently dropping
> `cyd` (14 hits) and `trinity` (8 hits) — **both real envs of `Spotify-Diy-Thing/platformio.ini`**,
> i.e. the exact cross-project ambiguity the note above raises and does not resolve. Specified:
> **C3 gates identifiers matching `cyd2usb[A-Za-z0-9_]*` against `app/platformio.ini`, and nothing
> else.** Bare `cyd` and `trinity` belong to the other project, are out of C3's scope entirely, and
> are covered by the unqualified-reference warning rather than by the error path.

### C4 — status vocabulary
**Must be scoped to `docs/architecture/decisions/`, `designs/` and `interfaces/` only.** Applied
corpus-wide it produces 67 hits that are almost all legitimate: `roadmap.md` uses `done`/`partial`,
test docs use `pass`/`passing`, `quality_manager.md` uses `open`. Those are different vocabularies for
different artifacts, not errors.

> **[A3 — baseline corrected, 2026-08-16.] C4 has no usable baseline and the migration is not a
> rename.** Measured at `efab524` against the closed vocabulary, scoped exactly as this section
> requires: **91 failures** — *more* than the 67 corpus-wide hits quoted above as the reason to scope
> it. The "67" was a raw grep, never re-taken after scoping, so the number in this spec argued for a
> conclusion it does not support.
>
> Live statuses in the scoped set include `done`, `planned`, `implemented`, `resolved`, `updated`,
> `draft`, and prose forms like `feeds ADR-010 (accepted)`. Folding `draft` into `proposed` — the only
> migration this spec describes — addresses a small fraction of them.
>
> **The 91 is struck too — @Architect review, same day.** C4's count is dominated by a matching rule
> this spec never states, and across eight plausible readings (exact vs prefix; header-only vs all
> lines; `*-review.md` in or out) it measures **100–218**. 91 is outside every one of them: it came
> from one unstated reading. **No C4 number may be quoted until the rule exists** — the honest
> statement is "order 100–200, rule undefined". [A3]'s conclusion is unaffected and stands: it is a
> content migration, not a rename, and it was never 67.
>
> **Consequence for the rollout:** phase 4's precondition is a content migration across ~100–200
> document headers, not a scoping tweak. It needs its own task plus three Architect rulings, which are
> now TASK-508's first deliverable, not TASK-475's problem: (a) how landed work is spelled — the only
> doc using `partially landed` today is `M-SRCLAYOUT-main-decomposition.md:4`; (b) whether C4 matches
> on **prefix** or **exact**, which is worth ~100 failures on its own; (c) whether `Status:` is read
> header-only or anywhere in the file. **C4 stays advisory until that task lands.**

Closed vocabulary for architecture documents:
`proposed` | `accepted` | `partially landed` | `superseded` | `rejected`

`draft` is currently used by design docs and should be **folded into `proposed`** — M-NOART sat at
`draft` for three months while half of it shipped, which is precisely the ambiguity to remove.

### C5 — link integrity
Relative `.md` links, anchors stripped. **Zero failures today, so this one goes blocking on day one**
and stays cheap forever.

## 3. Output contract

Match `check_build.sh`: `[n/N]` progress lines, `PASS`/`FAIL` per check, a `=== Results: n passed,
m failed ===` tail, exit 0 only if no **blocking** check failed. Advisory checks print
`[warn]` and never affect exit status — the same shape the existing settings-wiring gate already
uses, so the convention exists.

Every failure prints `file:line: <what> -> <why>` so it is directly actionable.

## 4. Rollout — driven by the baselines, not by preference

| Phase | Blocking | Advisory | Precondition |
|---|---|---|---|
| 1 | C5, **C1-`delta`** | C1-full, C2, C3, C4 | none — ship immediately (§4a); **`run/check` invokes it from here**, per the closed OQ1 |
| 2 | + C2 | C1-full, C3, C4 | ~~PM files TASK-453…474~~ **DONE** — filed 2026-08-16, C2 now reads 0 |
| 3 | + C3 | C1-full, C4 | ADR-061 D8 lands |
| 4 | + C4 | C1-full | **[A3]** TASK-508 lands: the ~100–200-header migration **and** the matching rule that fixes the count — *not* merely "scoped per §2" |
| 5 | + C1-full | — | the **280**-citation backlog cleared — **optional; may never happen** |

### 4a. C1 gets a delta-only blocking mode — @QM amendment, 2026-08-16

**Accepted.** The spec below argues C1 stays advisory forever. QM's objection: *that gives up more
than necessary, and the spec's own "conventions decay, checks do not" argument applies to itself.*

**Add a third mode.** Alongside `off` and `advisory`, C1 gains **`delta`**: fail only on positional
citations **newly introduced in the diff** of changed `.md` lines. Existing debt is invisible to it.

> **[A2 — "the diff" defined, 2026-08-16.]** The original text never said what `delta` diffs against,
> and it is the only new mechanism the rollout puts blocking on day one. Specified:
>
> - **Default: the working tree against `HEAD`** — `git diff HEAD -- '*.md'` plus untracked `.md`
>   files in the gated corpus, treating every line of a new file as added. This gates *what you are
>   about to commit*, which matches how `run/check` is used and how this repo works: commits land
>   directly on master with no feature branches, so there is no branch point to diff from.
> - **Override: `CHECK_DOCS_BASE=<rev|range>`** for any other question — `CHECK_DOCS_BASE=HEAD~1` to
>   audit the last commit, or a range for a CI run over a push.
> - **Only added lines count** (`+` lines in unified diff). A citation that merely moved, or that sits
>   in an untouched line of a touched file, is existing debt and stays invisible — otherwise editing
>   one line of `M-BOOT-UI.md` inherits its 32 pre-existing failures and the mode is unusable.
> - **Exemptions apply first**: a `.md` under §1's exempt set is skipped even when it is in the diff,
>   so appending to `lessons_learned.md` never trips the gate.
>
> Implementation note: resolve added citations with the same resolver as C1-full — one code path, two
> input sets — so the two modes cannot disagree about whether a citation is broken.
>
> **[A-rev] Two holes in the above, both already exercised by this repo:**
>
> - **A document split is not new debt.** "Every line of a new file counts as added" contradicts this
>   mode's own rationale: `tasks-winamp-player.md` (15 C1 failures) and `tasks-architecture.md` were
>   both created by splitting an existing file, and under phase 1 the blocking gate would have fired
>   on relocated debt. Use `git diff -M -C` so renames and copies are detected, and skip any added
>   line that exists **verbatim at the base rev** anywhere in the corpus. This repo splits boards —
>   that is what caused [A1] — so this is a certainty, not a hypothetical.
> - **The default base is blind immediately after a commit.** `git diff HEAD` is empty once you have
>   committed, so "run it before committing" is a convention with nothing behind it — the precise
>   thing §4 says does not survive. Until a pre-commit hook exists, `run/check` invoking
>   `check-docs` (see the closed OQ1) is what gives it teeth; `CHECK_DOCS_BASE=HEAD~1` audits the
>   commit just made, and CI should use the push range.

That flips C1 from a permanently-ignored warning into a live gate **immediately**, with no cleanup
precondition — and it is what actually operationalises BP-DOC-1, which is otherwise a convention with
nothing behind it. The **280**-citation backlog then decays opportunistically instead of needing a
milestone.

Revised rollout: **C1 goes `delta`-blocking in phase 1**, alongside C5. Full-corpus C1 stays advisory,
and phase 5 becomes optional rather than aspirational.

**C1's full-corpus mode likely stays advisory permanently, and the spec says so on purpose.** **280** failures across **60**
documents is a milestone of its own, it would go stale mid-flight, and a gate that fails on day one
gets switched off. The BP in §5 is the real fix: stop creating new positional citations. C1's job is
to make the existing debt *visible and non-growing*, not to force a sweep.

## 5. Relationship to the BP candidates

The gate and the practice do different jobs and neither substitutes:

- **C1 detects** broken coordinates after the fact.
- **BP-DOC-1 prevents** them being written — cite symbols, not coordinates.

This session proved both halves inside a day: every symbol reference in M-CODEQUAL survived Stages
A/B; every line number broke. See `docs/quality/bp-candidates-doclife.md`.

## 5a. Exit criteria — TASK-475

Added [A-rev]: `architect.md` requires a design doc handed to an implementer to carry these, and this
one had none. A spec without exit criteria is thrown, not handed off.

| # | Criterion |
|---|---|
| E1 | `run/check-docs` exists, follows `check_build.sh`'s output contract (§3), exits non-zero **only** on a blocking check |
| E2 | Corpus resolution matches §1 exactly: 233 gated under `docs/` + `CLAUDE.md`; 69 exempt; exemptions scope scanning only, never resolution |
| E3 | C5 and C1-`delta` are blocking and both read **0** on a clean tree at the commit under test |
| E4 | C1-full reports **280 / 599**, C2 **0**, C3 **9** — an implementer who cannot reproduce these has found either a bug or a further spec defect, and must say which |
| E5 | C4 runs advisory and prints its count without a pass/fail claim, pending TASK-508's matching rule |
| E6 | `CHECK_DOCS_BASE` override works for a rev and for a range; a document split produces **0** C1-`delta` failures (regression test for the [A-rev] carve-out) |
| E7 | `run/check` invokes it from phase 1 (closed OQ1) and stays 11/11 + this gate |

## 6. Non-goals

- **D5 (residual scope)** — not detectable; stays a QM retrospective question.
- **Semantic accuracy** — no gate can tell that `cmdGet` is described *wrongly*, only that it exists.
  C3 found six dead envs; it could not have found X015's false Core-0 claim, which needed a human to
  ask.
- **Rewriting history** — the exemptions in §1 are load-bearing.

## 7. Open questions

- ~~**OQ1**~~ — **CLOSED [A-rev], and it was not an open question but a contradiction.** §4 puts
  C1-`delta` blocking in phase 1 "ship immediately", while OQ1's lean deferred wiring it into
  `run/check` to phase 3 — so for two phases the blocking gate would have had **no invoker**, which is
  the "switched off" failure mode reached by a different road. Resolution: **standalone
  `run/check-docs`, wired into `run/check` from phase 1**, with only the checks that read **0 today**
  blocking (C5, C1-`delta`). The original worry — never add a *failing* gate to the pre-commit path —
  is satisfied by the baselines, not by deferral. C1-full, C2, C3, C4 print `[warn]` and cannot fail
  the build until their own phase.
- **OQ2** — should C1 resolve symbols too (`file :: symbol`), verifying the symbol still exists in
  that file? That would make BP-DOC-1's preferred form *checkable* rather than merely encouraged.
  Attractive; needs a cheap symbol index. Defer to a follow-up.
