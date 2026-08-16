# Design — M-TESTBASE phase 1: a base test framework, scoped to the 3-mode player

> Owner: Architect + VE
> Status: **proposed** — 2026-08-16
> Goal (human, 2026-08-16): *reduce the noise that is making M-WINAMP-PLAYER unimplementable.*
> Parent: [M-TESTARCH](M-TESTARCH-test-architecture.md) · [M-QUALITY map](M-QUALITY-improvement-map.md) ·
> [VE review](M-TESTARCH-VE-review.md)
> Serves: [M-WINAMP-PLAYER](M-WINAMP-PLAYER-local-playback.md) — Spotify / WebRadio / LocalPlayer

**This document deliberately drops most of the quality programme.** M-QUALITY maps nine areas; this
plan funds four items and explicitly defers the rest. The selection criterion is single and strict:
**does it reduce the noise in the 3-mode player, now?** Everything that does not, waits — including
work this same author argued for two documents ago.

---

## 1. The whack-a-mole is not diffuse. It is located.

Measured against `cross_feature_matrix.yaml` (65 interactions):

| Measure | Value |
|---|---|
| Interactions involving the player surface | **26 of 65 (40 %)** — for one of thirteen apps |
| High-risk interactions with **zero** test coverage | 8 |
| …**of those, in the player area** | **7 of 8** |

The seven: `X052` (SD × LocalPlayer, two tasks on the filesystem), `X054` (pleditView absorbed
`drawPlaylist()` wholesale), `X055` (WebRadio's independently-evolved PLEDIT copy), `X057` + `X064`
(taskbar asserts WebRadio is the **last** `AppId`), `X061` (capability mask rewrites the Spotify-only
zone hardcoding), `X062` (**shuffle permutes `playOrder[]`; `viewOrder[]` — what PLEDIT renders and
what SAVE writes — is never touched**).

**That is the shape of whack-a-mole, written down in the project's own artifacts before anyone asked.**
Every one is a *shared-state or dependency* coupling between two modes. Fix mode A, break mode B, with
no test that can observe the break — because no test covers any of them.

Churn agrees: `main.cpp` 164 commits, `webRadioApp.h` 57, `winampDisplay.h` 31, and **30 of ~93
player-area commits carry a fix/revert/regress marker in the subject line.**

**Conclusion: the noise is not general technical debt. It is seven specific untested couplings in the
one subsystem being actively built.** That is a far smaller problem than the quality programme, and
it is addressable now.

## 2. Why the instrumentation cannot see it

Thirty player-related debug keys exist: `wrState`, `wrPlaying`, `wrIdx`, `wrPump`, `wrEject`,
`wrHeap`, `plCount`, `plOrder`, `plCursor`, `plMem`, `playerMode`, `aePlay`, `arenaStats` …

**They are organised by implementation silo, not by contract.** `wr*` answers questions about
WebRadio; `pl*` about the playlist model; `aePlay` about the audio engine. To ask *"is the player slot
in a consistent state?"* — the only question that matters at a mode transition — you must issue eight
commands, correlate them by hand, and know which subset applies to the current mode.

**A cross-mode bug is invisible to a per-mode observation.** X061, X062 and X055 are precisely
cross-mode, and precisely unobservable. This is what "serial dbg designed for testing" means in
practice: the debug surface should expose the **contract that spans the modes**, not mirror the
modules that implement them.

## 3. Sequencing call: test signal before main.cpp decomposition

The intuition that `main.cpp` is fuel is correct — 164 commits, highest-churn file in the tree. But
the ordering matters, and it goes the other way round from the obvious:

**Decomposing `main.cpp` is measured by the regression suite. The regression suite is the thing that
is noisy. You cannot use a broken instrument to verify the repair of the workbench.**

This is not hypothetical. ADR-059 D13 requires ≥3 pre-declared baseline runs for behaviour-neutrality,
and **that baseline was never taken for the two M-SRCLAYOUT stages that already landed** — TASK-488
had to close by comparing compiled binaries instead. Continue decomposition on today's suite and that
repeats.

**Fix the instrument first.** M-SRCLAYOUT is right, is already in flight, and should continue — but
after phase 1, with a suite whose failures mean something.

## 4. Phase 1 — four items, in order

### P1 — `lib/dut.py`, scoped hard *(the enabler; everything else needs it)*

Extract `Dut` out of the 10 229-line suite. **Scope discipline: this is not TASK-480.** Do not split
the test bodies. Extract only:

- `Dut`, `_TeeSerial`, `SetupFailure`, the boot/ready cascade
- **`resolve_port()`** delegating to `run/port` — kills 19 hardcoded `/dev/ttyUSB0` defaults
- **one timeout policy** replacing 672 literals: a default, a slow-op override, nothing else
- promote the private names the 16 importers already reach for (`_switch_to`, `_restore_spotify`)

Host-verifiable. No DUT time. Migrate the 16 importers a few per commit.

### P2 — `get player`: one aggregated state vector *(the instrumentation that adds value)*

A single key answering the whole player-slot contract in one line, identical shape in all three modes:

```
mode · caps mask · engine state · arena held · source bound
· playOrder len+hash · viewOrder len+hash · pending flags · last error
```

Everything in it **already exists** in the firmware, scattered across eight keys. This is aggregation,
not new state — the cheapest item here, and the one that makes the next item possible. `viewOrder`'s
hash alongside `playOrder`'s is what makes **X062 observable at all**.

Design rule, per M-TESTARCH §4 I1: **additive-only, VE-gated field set.** Extend, never rename.

### P3 — the mode-transition matrix *(the base framework, testing the core feature)*

Three modes ⇒ **9 transitions** (including mode→same-mode). Seven invariants, each derived from an
uncovered high-risk interaction rather than invented:

| id | Invariant at a transition | From |
|---|---|---|
| `M1` | previous mode's audio engine fully torn down | X052, `T_AE_04` |
| `M2` | arena released or transferred; no leak across the transition | X052, TASK-425/442 |
| `M3` | UI zones match the new mode's capability mask | **X061** |
| `M4` | `playOrder` / `viewOrder` consistent; **SAVE writes what is displayed** | **X062** |
| `M5` | the correct playlist source is bound to PLEDIT | **X054, X055** |
| `M6` | taskbar slot + `AppId` tail assumption still hold | **X057, X064** |
| `M7` | `playerMode` survives reboot | settings `S5` |

**63 cells, generated from the mode list — never typed.** One parameterised body per invariant, seven
bodies total, replacing what would otherwise be dozens of hand-written per-mode tests that would
again cover some pairs and not others.

This is the anti-whack-a-mole mechanism, and it is mechanical: **a fix to one mode that breaks another
fails a named cell in the same run**, instead of surfacing three days later as a user-visible
regression in a mode nobody re-checked.

Expect it to land **red**. That is the correct first result — seven of these couplings have never been
tested.

### P4 — `get idle`: one quiescence predicate *(kills the settling sleeps)*

The firmware already tracks `g_shellBusy`, `App::hasPendingAsync()`, `App::isConnecting()` and the
dataTask queue depth. **None is aggregated.** One key that ANDs them turns *"sleep 0.3 and hope"* into
*"block until quiet, fail at deadline"*.

Mode transitions are exactly where this bites: a transition involves teardown, allocation, a repaint
and possibly a reconnect, and **no test can currently ask whether it finished** — so every one is
followed by a guessed sleep. 252 sleeps exist tree-wide; the transition tests would need none.

One new key, no protocol change, no async lines. **If P4 alone removes a meaningful share of the 252
sleeps, the wider synchronisation work (correlation IDs, `watch`) has an evidence base. If it does
not, that is worth learning for one day's work.**

## 5. Explicitly deferred — and this is the point of the document

| Deferred | Why it does not serve phase 1 |
|---|---|
| **TASK-480 runner split** | large, and it is the *regression suite* — high risk, and it does not make one player bug visible. **P1 is the part of it that pays now** |
| TASK-481 directory move / taxonomy | churns every doc path; zero signal improvement |
| T1 host unit tier + Arduino shim | genuinely valuable, needs D0, and `m3u.h` (2 commits, quiet) is not where the noise is |
| Correlation IDs / `watch` subscribe | phase 2. Gated on P4 producing evidence |
| C1 fetch consolidation, C3 table dispatch, C5 geometry, C6 palette | quality debt, not player noise |
| Conformance matrix for all 13 apps | the *pattern* is proven by P3 on the 3 modes first. Generalise after |
| `main.cpp` decomposition | continue **after** phase 1 — see §3 |

**Aquarium's zero conformance coverage, the 41 features with no `test_ids`, the 176 non-resolving ids
— all real, all deferred.** They are not what is making the player unimplementable.

## 6. Order, cost, and what "done" means

| # | Item | DUT time | Verifiable by |
|---|---|---|---|
| P1 | `lib/dut.py` + port + timeout policy | none | imports resolve; suite runs unchanged |
| P2 | `get player` aggregate key | minutes | key returns in all 3 modes |
| P4 | `get idle` predicate | minutes | replaces settling sleeps in a sample, no new failures |
| P3 | 9 × 7 transition matrix | one run | **lands red; every red cell names a real coupling** |

P1 first (everything needs it). P2 and P4 are independent and can go in either order. P3 needs both.

**Exit criteria — measurable, not vibes:**

1. `lib/dut.py` exists; 16 importers migrated; **zero** hardcoded `/dev/ttyUSB0`; one timeout policy.
2. `get player` returns the full vector in all three modes.
3. The 63-cell matrix runs, and **every failing cell maps to a named `X0NN` interaction** — no
   unexplained reds.
4. The seven uncovered high-risk interactions have reserved ids in `test_plan.md` (VE), whether or
   not the cells pass yet.
5. **A mode fix that breaks another mode fails in the same run.** That is the whole objective;
   everything else here is instrumentation for it.

**What phase 1 does not promise:** it does not clean up the test suite, does not build a unit tier,
and does not reduce the 209 test bodies. It makes the 3-mode player observable and its couplings
testable. That is the smallest thing that stops the tail-chasing, and it should be finished before
anything else in M-QUALITY is funded.
