# Design — M-QUALITY: the improvement map

> Owner: Architect
> Status: accepted
> As-built: 2026-08-16
> Purpose: one page that says what we are trying to improve, which document owns each area, what
> unlocks what, and — explicitly — what we have decided *not* to do.
> Indexes: [M-TESTARCH](M-TESTARCH-test-architecture.md) · [M-TOOLING](M-TOOLING-host-tool-architecture.md) ·
> [M-CODEQUAL](M-CODEQUAL-duplication-and-abstraction.md) + [§12–§13](M-CODEQUAL-duplication-and-abstraction.md) ·
> [M-SRCLAYOUT](M-SRCLAYOUT-main-decomposition.md) / [ADR-060](../decisions/ADR-060.md) ·
> [M-DOCLIFE](M-DOCLIFE-keeping-design-docs-alive.md)

**Why this exists.** Six documents now describe overlapping structural work, and the dependencies
between them are real but stated nowhere. Three of the six independently arrived at the same root
cause and none of them says so. This page is the join.

**Nothing in this document is new analysis.** Every claim is measured and cited to the document that
owns it. If this page and an owning document disagree, the owning document wins.

---

## 0. Priority — phase 1 is scoped to the 3-mode player

**Human direction, 2026-08-16: the short-term goal is reducing the noise blocking M-WINAMP-PLAYER.**
[M-TESTBASE phase 1](M-TESTBASE-phase1-player-gate.md) funds four items and **defers everything else
in this map**, including items argued for above. Rationale, measured: **7 of the 8 uncovered
high-risk cross-feature interactions are in the player area**, and the debug surface is siloed
per-mode so cross-mode breakage is unobservable. Read §0 before treating anything below as scheduled.

## 1. The map

| # | Area | Owner doc | State | The one-line problem |
|---|---|---|---|---|
| **A** | **Physical design / component model** | M-SRCLAYOUT, ADR-060, M-LEVELS | stages A/B landed; levels **audited 2026-08-16** | 66 headers, 8 `.cpp` — the firmware is effectively one translation unit, so no boundary can be enforced and nothing can be compiled alone |
| **B** | **Test architecture** | M-TESTARCH | reviewed 2026-08-16 | 100 % of testing is integration, on hardware, on one device — and the plan and the code do not agree on what exists |
| **B2** | **Test *logical* design (conformance matrices)** | M-TESTARCH §2 | new 2026-08-16 | the app/settings contract exists only as a human checklist; tests are hand-copied per app, so the gaps are invisible (Aquarium: zero coverage) |
| **C** | **Test synchronisation** | M-TESTARCH §3b | new 2026-08-16 | 924 hand-tuned waits; the harness polls a device that is already an event source |
| **D** | **Host tooling architecture** | M-TOOLING | proposed | ~39 000 lines of Python, never architected; the DUT library lives inside the suite that uses it |
| **E** | **Constant ownership (SSoT)** | M-CODEQUAL C5, VE-review §3 | proposed, gate red | 24 self-declared firmware mirrors, one 5-constant block copy-pasted 4× |
| **F** | **Code quality in the firmware** | M-CODEQUAL C1–C6 | proposed | one proven bug class (hand-managed acquire/release), plus readability debt |
| **G** | **Ownership + type hygiene** | M-CODEQUAL §12 C8/C9 | new 2026-08-16 | a coherent memory policy that is written down nowhere; zero `= delete` in the tree |
| **H** | **Documentation lifecycle** | M-DOCLIFE | **phase 1 landed** | design docs rot; `run/check-docs` now gates the worst of it |
| **I** | **Feature↔test traceability + VE process** | [M-TESTARCH-VE-review](M-TESTARCH-VE-review.md) | new 2026-08-16 | 51 % of features claim no tests and 54 % of the claims don't resolve; **no VE review exists for any of the 11 structural design docs** |

## 2. The dependency view — what unlocks what

```
        A  component model = translation unit
        │        (ADR-060 D0; the keystone)
        ├──────────────► B  unit/component test tiers (T1, T2)
        │                       ▲
        │                       │ needs a runner + a shim
        │                       │
        └──────────────► F/G  enforceable boundaries, RAII, ownership policy

        D  lib/dut.py extraction ──► D  runner split ──► B  id binding by family
                 │
                 └──► C  one timeout policy, correlated protocol, watch/idle
                              │
                              └──► B  T3 becomes deterministic and ~faster

        E  SSoT constants ──► D  host tools stop mirroring firmware
                          └──► B  tests stop encoding app order by hand

        H  check-docs ──► the gate mechanism every other area reuses
```

**Three keystones, and they are independent of each other** — which is the useful finding, because it
means all three can start now:

1. **A (component = TU).** Doc-only change to ADR-060. Unlocks B's entire host tier and F/G's
   enforceability. Highest leverage, lowest cost, currently unstated.
2. **D's `lib/dut.py` extraction.** Unlocks the runner split, the synchronisation work, and the
   timeout policy. Everything in D and C queues behind it.
3. **H's `check-docs`.** Already landed. It is the *mechanism* — E's SSoT rule, B's id binding and
   D's spike-retirement rule are all "add a check to the gate that already exists".

## 3. The three-way convergence nobody wrote down

A, B and D each diagnosed a different symptom of **one cause: no physical design, so code lands
wherever the helpers already are.**

| Symptom | Where |
|---|---|
| `main.cpp` grew to a monolith | M-SRCLAYOUT §3 (A) |
| `run_serialdbg_tests.py` grew to 10 229 lines | M-TOOLING F1 (D) |
| Nothing can be unit-tested | M-TESTARCH §3 / review C7 (B) |

M-TOOLING already spots two of the three — *"the exact gravity well M-SRCLAYOUT §3 describes,
reproduced in the other tree."* The third is the same well again: **a test tier is impossible for
exactly the reason the monolith is possible.** ADR-060 D0 should say this, because it changes what D0
is *for* — not tidiness, but making three separate classes of work possible at all.

## 4. Cross-cutting: the gate is the deliverable, not the cleanup

Every area here has a history of being fixed and then rotting. The pattern that has actually held is
the one `appRegistry.h` uses: **a single source, consumed by codegen, staleness-gated in `run/check`.**

| Area | Its gate | Status |
|---|---|---|
| E | `T_CQ_03` — `grep -rnE '\b(275\|320)\b'` clean | written, **red (123 hits)** |
| B | id binding: every registry id ↔ one doc row | **proposed** (M-TESTARCH §6) |
| B | flake policy: undeclared `flake()` = FAIL | **proposed** (M-TESTARCH §7) |
| D | spike retirement: archived task ⇒ spike deleted | **proposed** (M-TOOLING §4) |
| F | `T_CQ_01` — no yield/resume imbalance | written, unrun |
| H | `check-docs` C5 + C1-delta | **landed and green** |

**Rule of thumb for this whole programme: land the gate red, with a dated exception list, rather than
landing the cleanup ungated.** Precedent in-repo — TASK-475's gate rejected its own spec, and that was
the correct first result. An exception list that shrinks is a gate; a cleanup with no gate is a
half-life.

## 5. Explicitly not doing

Recorded so they are not re-proposed. Each was measured, not assumed.

| Not doing | Why | Source |
|---|---|---|
| Convert 66 headers to `.h`/`.cpp` pairs | very large diff, low reward on its own; the fix is D0 stating the rule for *new* components | M-CODEQUAL §12 |
| Replace 1 116 C-style casts with `static_cast` | sampled: all idiomatic embedded numeric conversion; catches nothing | M-CODEQUAL §13 |
| Chase a "77 `new` vs 19 `delete`" leak | real counts are 5 and 5; the gap was the English word *new* in comments | M-CODEQUAL §13 |
| Abstract `weatherApp`/`cryptoApp`'s shared shape | two instances, ~30 lines of shared control flow, different render bodies | VE-review §3 |
| Refactor `webRadioApp::tick()` (399 lines) | worst by raw measure; carries 9 tasks' interleaved fixes; no forcing reason | M-CODEQUAL §8 |
| Name the `clockApp` hex literals | nixie glyph bitmap data — naming them is worse | M-CODEQUAL §8 |
| Adopt a C++ test framework (Unity/GTest) | generalise the in-tree `test_check_docs.py` pattern instead | M-TESTARCH §3 |
| Build T2 mock infrastructure now | no components to mock until D0 | M-TESTARCH §3 |

**And a standing caution**, now with four independent confirmations: *in this codebase a grep-derived
count is a hypothesis, not a finding.* M-CODEQUAL §3's counting note should be promoted to
`best_practices.md` — it has prevented four bad findings and would have prevented three published ones.

## 6. Priority

Set by **[M-TESTBASE phase 1](M-TESTBASE-phase1-player-gate.md)** — see §0. Phase 1 funds four items
against area **B2/C/D** only, scoped to the 3-mode player, and defers every other area in this map.

The three keystones in §2 remain the right *structural* order for whatever is funded after it:
component-as-translation-unit (A, doc-only), the `lib/dut.py` extraction (D — phase 1 P1 is exactly
this), and reusing `check-docs` as the gate mechanism (H).
