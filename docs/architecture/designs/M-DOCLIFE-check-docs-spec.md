# Spec — `run/check-docs`: a staleness gate for architecture documents

> Owner: Architect (spec) — **Developer implements**
> Status: **proposed** — 2026-08-16
> Date: 2026-08-16
> Parent: [M-DOCLIFE-keeping-design-docs-alive.md](M-DOCLIFE-keeping-design-docs-alive.md) §4
> Tracked-as: TASK-475

Implements the mechanically-detectable half of M-DOCLIFE (decay modes D1–D4). **D5 — a task closed
with residual scope — is deliberately out of scope: no gate detects it, and implying otherwise gives
false assurance.**

**Every baseline below was measured on 2026-08-16 against the tree at `77a9568`.** The counts are the
point of this spec: the checks have wildly different day-one failure counts, and that dictates the
rollout, not preference.

---

## 1. Corpus and exemptions

292 `.md` files under `docs/`, plus `CLAUDE.md`. **223 are gated ("live"); 69 are exempt.**

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

## 2. The five checks, with measured baselines

| id | Check | Baseline (live docs) | Verdict |
|---|---|---|---|
| **C1** | every `file.ext:NNN` resolves to an existing file with ≥ NNN lines | **274 failures** / 576 citations (48 %) | advisory |
| **C2** | every `TASK-`/`ADR-`/`IFC-`/`X0NN` id referenced exists | **22 failures** — *all* of them this session's unfiled reservations (453–474) | blocking after PM files |
| **C3** | every env named in docs exists in `app/platformio.ini` | **8 failures** | blocking after ADR-061 D8 |
| **C4** | `Status:` uses the closed vocabulary | 67 raw hits — **needs scoping, see §3** | advisory until scoped |
| **C5** | relative `.md` links resolve | **0 failures** | **blocking immediately** |

### C1 — positional citations
Regex `([\w./-]+\.(h|cpp|py|ini|sh|yaml|json|md)):(\d+)`, resolved against `.`, `app/`, `app/src/`,
`app/tools/`, `docs/`. Fails if no candidate file exists, or the file has fewer than NNN lines.

Worst live offenders: `M-BOOT-UI.md` (32), `M-SPOTIFY-BOOT-GATE.md` (24), `tasks-winamp-player.md`
(15), `M-TASKBAR-FEEDBACK.md` (12), `test_plan.md` (10).

**Line-overrun is the cheap half and worth keeping even though it under-detects.** A citation whose
file shrank below the line number is *certainly* wrong; one that still has enough lines may point at
unrelated code. C1 catches the certain cases; the BP in §5 is what prevents the rest.

### C2 — identifier existence
`TASK-NNN` resolved against `tasks.md` + `tasks-archive.md` + `tasks-winamp-player.md`; `ADR-NNN`,
`IFC-NNN` against their directories; `X0NN` against `cross_feature_matrix.yaml`.

**All 22 current failures are TASK-453…474 — reservations made in design docs this session and never
filed in `tasks.md`.** That is exactly the gap M-DOCLIFE §3 recommendation 5 addresses, and the check
found it without being told. ADR and IFC references are already clean (0 failures).

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

### C4 — status vocabulary
**Must be scoped to `docs/architecture/decisions/`, `designs/` and `interfaces/` only.** Applied
corpus-wide it produces 67 hits that are almost all legitimate: `roadmap.md` uses `done`/`partial`,
test docs use `pass`/`passing`, `quality_manager.md` uses `open`. Those are different vocabularies for
different artifacts, not errors.

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
| 1 | C5, **C1-`delta`** | C1-full, C2, C3, C4 | none — ship immediately (§4a) |
| 2 | + C2 | C1-full, C3, C4 | ~~PM files TASK-453…474~~ **DONE** — filed 2026-08-16, C2 now reads 0 |
| 3 | + C3 | C1-full, C4 | ADR-061 D8 lands |
| 4 | + C4 | C1-full | C4 scoped per §2; `draft` folded in |
| 5 | + C1-full | — | the 274 backlog cleared — **optional; may never happen** |

### 4a. C1 gets a delta-only blocking mode — @QM amendment, 2026-08-16

**Accepted.** The spec below argues C1 stays advisory forever. QM's objection: *that gives up more
than necessary, and the spec's own "conventions decay, checks do not" argument applies to itself.*

**Add a third mode.** Alongside `off` and `advisory`, C1 gains **`delta`**: fail only on positional
citations **newly introduced in the diff** of changed `.md` lines. Existing debt is invisible to it.

That flips C1 from a permanently-ignored warning into a live gate **immediately**, with no cleanup
precondition — and it is what actually operationalises BP-DOC-1, which is otherwise a convention with
nothing behind it. The 274-citation backlog then decays opportunistically instead of needing a
milestone.

Revised rollout: **C1 goes `delta`-blocking in phase 1**, alongside C5. Full-corpus C1 stays advisory,
and phase 5 becomes optional rather than aspirational.

**C1's full-corpus mode likely stays advisory permanently, and the spec says so on purpose.** 274 failures across ~40
documents is a milestone of its own, it would go stale mid-flight, and a gate that fails on day one
gets switched off. The BP in §5 is the real fix: stop creating new positional citations. C1's job is
to make the existing debt *visible and non-growing*, not to force a sweep.

## 5. Relationship to the BP candidates

The gate and the practice do different jobs and neither substitutes:

- **C1 detects** broken coordinates after the fact.
- **BP-DOC-1 prevents** them being written — cite symbols, not coordinates.

This session proved both halves inside a day: every symbol reference in M-CODEQUAL survived Stages
A/B; every line number broke. See `docs/quality/bp-candidates-doclife.md`.

## 6. Non-goals

- **D5 (residual scope)** — not detectable; stays a QM retrospective question.
- **Semantic accuracy** — no gate can tell that `cmdGet` is described *wrongly*, only that it exists.
  C3 found six dead envs; it could not have found X015's false Core-0 claim, which needed a human to
  ask.
- **Rewriting history** — the exemptions in §1 are load-bearing.

## 7. Open questions

- **OQ1** — part of `run/check` or standalone? Lean: **standalone `run/check-docs`**, called by
  `run/check` only once phase 3 is reached. Adding a failing gate to the pre-commit path is how gates
  get disabled.
- **OQ2** — should C1 resolve symbols too (`file :: symbol`), verifying the symbol still exists in
  that file? That would make BP-DOC-1's preferred form *checkable* rather than merely encouraged.
  Attractive; needs a cheap symbol index. Defer to a follow-up.
