# TASK-566 — order diff and pre-switch baseline

**TASK-566** · Owner: @Developer · Date: 2026-09-02 · **§1 re-derived 2026-09-04 (TASK-591)**
Design: [M-TESTARCH precedence hierarchy](../../architecture/designs/M-TESTARCH-precedence-hierarchy.md)
§4.1 / §6 R3 / EC-G9 · **The order switch is HELD and was NOT flipped.**

Everything below is regenerable — no number here is hand-maintained:

```
cd app/tools && python3 suite/serialdbg/runner.py --order-diff [--full]
cd app/tools && python3 -m lib.baseline <runner log> …
```

---

## 1. The order diff — what the switch would change

Computed on the default selection (210 ids) with **zero DUT time**, which is the whole
argument for landing the classification inert first (§6 R3).

| | 2026-09-02 (CORE=43) | 2026-09-04 (CORE=23) | **2026-09-06 (CORE=18)** |
|---|---|---|---|
| ids in the default selection | 210 | 210 | **193** |
| ids that change position | 210 — all of them | 202 | **185** |
| ids whose position is preserved | 0 | 8 | **8** |
| inverted pairs | 6505 | 3497 (−46 %) | **2444** (−62 % from 2026-09-02) |
| inverted pairs touching an edge candidate | 1350 | 1084 (−20 %) | **689** (−49 %) |

**Why the second column exists.** TASK-591 declared the gating classes R35 requires and, on
the human's ruling of 2026-09-04, demoted 20 CORE ids to FEATURE — every one of them a
`_meta.seed_cls()` default nobody had affirmed. That is a change to what the switch would do,
so §1 was re-derived rather than left to describe a corpus that no longer exists.

The shape is the same and it is milder. `shell.py`'s CORE ids still sit at the tail of the
registry and class order still moves them to the head; there were **23** of them after TASK-591,
so every id ahead of them shifted by exactly **+23** instead of +43.

**Re-derived again 2026-09-06 (TASK-626 + TASK-598).** TASK-626's rulings demoted five more
(`T-BUSY-01`, `T-BUSY-01b`, `T-BUSY-05`, `T-CDWN-03`, `T_X07_01`) and split one (`T-CDWN-04`,
FEATURE); TASK-598 deleted four (`T_MA_02`, `T_GOL_02`, `T_WX_02`, `T_CX_02`). **CORE is 18**, so
the shift is **+18**; the registry is 196 ids and the default selection 193 (RIG stripped). The
third column of the table above is the re-run of the same command, not a hand-edit. The direction
has been one-way all programme: **43 → 23 → 18**, and inverted pairs 6505 → 3497 → 2444.

§1's stop criterion — *"if demoting the network-dependent CORE ids leaves CORE with too few members
to gate anything meaningful, cancel the class-order switch outright and close TASK-566 as
WONTFIX"* — is now a live question rather than a hypothetical, and belongs to the human with
TASK-617. The 18 that remain are not a residue: they include `T079` (tap injection), `T-BUSY-02`
(the `shellBusy` primitive on both edges), `T-CDWN-02` (the `cmdTap` gate), `T147`/`T148` (app
switch and tap dispatch) and `T_BI_02`/`T_BI_03` (boot-input) — the premises the rest of the corpus
is written on top of. **@VE's reading is
that the criterion is not triggered**, but it is stated here rather than assumed, because the
count has fallen by 58 % since the criterion was written.

What is new is the preserved set. **Eight ids no longer move at all** — `T-BGPOLL-02`,
`T-BGPOLL-03` and `T-ERR-01/02/04/05/06/07`. They are demoted ids that already sat at the
very end of the registry and, as FEATURE, stay there. One of the eight matters
disproportionately: **`T-ERR-04` was the baseline's own worst unrestored-state hazard**
(WP-B `B-7` — it writes `lastOkMs`, `backoff` and `lastHttp` and restores none of them, and
the switch would have moved it from index ~206 to ~39, in front of 170 ids). Its demotion
removes that migration entirely; it now stays at index ~206 where its leakage reaches almost
nothing.

Class census under the switch (ascending — this *is* the execution order):

| Class | Count (was) | Note |
|---|---|---|
| RIG | 0 (0) | no registry id is class RIG — the three RIG ids are stripped from the default selection (`app/tools/suite/serialdbg/runner.py:231`), so this line is structural, not an artefact (WP-C `C-3`) |
| HEALTH | 0 (0) | `T_DH_01..03` live in a separate registry (§4.5) and run in the gate phase |
| CORE | **18** (43) | 23 after TASK-591 (19 declared + 4 ledgered); TASK-626 declared those 4 FEATURE and demoted `T_X07_01` on 2026-09-06, so all 18 are declared and the R35 ledger is deleted |
| **APP** | **0** (0) | **no id is classified APP today** — see §4 |
| FEATURE | **175** (167) | everything else, including the 25 demoted ids and `T-CDWN-04`; 196 registry ids total on 2026-09-06 (18 CORE + 3 RIG + 175) |

## 2. The 0→1-edge enumeration — @VE §18.6(c), delivered as a precondition

R3's mechanism, not an anecdote: `mb_arena_acquire()` early-returns on `if (s_owned) return
true;` *before* incrementing, so **any** test asserting an acquire edge is order-fragile by
construction — not just `T_PMT_04`. The scanner over-reports on purpose; the adjudication
lives in `app/tools/suite/serialdbg/_order.py:EDGE_ADJUDICATION` and
`test_class_order.py` fails if any candidate is missing from it, so the enumeration cannot
silently rot.

**20 candidates → 2 EDGE, 3 ORDER-SENSITIVE, 2 VACUITY, 13 DISMISSED.**

The four verdicts are split by *direction*, because direction decides whether the switch can
hide a defect or merely manufacture a red cell:

* **EDGE** (false red, or a false green once spoilt) — `T_PMT_04`, `T178`.
  `T_PMT_04` is the TASK-553 reference case and already carries a precondition SKIP.
  **`T178` is the highest-risk cell in the reorder** and was not previously identified: it
  asserts `chartLen == 0` *at rest* immediately after drill-in, so a predecessor's in-flight
  fetch spoils it (measured — `chartLen=33` on the 2026-07-10 full-suite run, mitigated by
  TASK-300's `_drain_data_pipeline`). Under class order `T-BUSY-01` and `T-CDWN-02`, which
  both drive Stock chart fetches, move from ~100 ids *after* it to ~90 ids *before* it.
* **ORDER-SENSITIVE** (silent non-result) — `T-BUSY-01`, `T165`, `T173`.
  **`T165`'s row is wrong** and TASK-591 confirmed it from the body: `_tb_precondition`
  *drives* `tbScrollOffset` to 0 and returns False if it cannot, so the `skip()` the
  adjudication cites is unreachable in registry order. WP-C `C-19` proposes re-verdicting it
  `DISMISSED` alongside `T163`/`T164`; that edit belongs to whoever owns C-19, and is noted
  here because an inaccurate row in a stated precondition of the switch matters.
* **VACUITY** (false green, the easiest to miss) — `T193`, `T196`.
* **DISMISSED** (establishes its own precondition) — the remaining 13.

## 3. The baseline — what it rests on, and its flake exposure

**Instrument:** `./run/test` (the full 210-id default selection) on `cyd2usb_winamp_debug`.

**Not `run/player-gate`, and this is a finding.** The gate is **order-blind for this switch**:
both legs are 100 % FEATURE ids, so the diff over leg A's 28-id list reports *0 moved, 0
inverted pairs* — "the switch is a no-op for this selection". A player-gate baseline, at any
run count, cannot serve as the A/B reference for the order switch. `run/test`'s default
selection must.

Per-run totals (210 ids each):

| Run | Passed | Failed | Skipped | Flaky-pass | Boot generations |
|---|---|---|---|---|---|
| 1 | 141 | 15 | 54 | 0 | `gen=3.1` → `3.4` |
| 2 | 142 | 18 | 49 | 1 | `gen=4.1` → `4.4` |

**Flake exposure is the headline, not the totals: 15 of 210 ids (7.1 %) did not give the same
answer in both runs** — `T-BUSY-01`, `T-BUSY-01b`, `T-SET-02`, `T-SET-03`, `T091`, `T092`,
`T272`, `T_CLK_11`, `T_PLR_07`, `T_PLR_08`, `T_PLR_20`, `T_PLR_21`, `T_PLR_22`, `T_PRM_01`,
`T_PR_05`. `T-BUSY-01` is one of §2's adjudicated order-sensitive cells, which is
corroboration rather than coincidence.

Each run additionally crossed **four boot generations** — the board rebooted three times
mid-suite — which is TASK-557's unresolved instability showing up inside the measurement.

**Two flake candidates are undeclared and surfaced as FAILs** (`T_PLR_07`, `T092`, both
`UNDECLARED flake` records), on top of the three already in `flaky.yaml`'s `candidates:`
(`T169`, `T_PR_05`, `T_WR_TLS_01`). @VE §18.6(b) requires these to be promoted or dismissed
**before run 1 of the A/B**, and explicitly not adjudicated from results — so they are listed
here, not judged here.

**Rig note, learned the expensive way:** back-to-back `run/test` invocations do not work on
this board. Each run's trap reflashes *production*, production boot-loops this hardware, and
the CH340 then vanishes before the next run's step-2 flash (`Could not open … the port
doesn't exist`). `./run/flash-debug` between runs is mandatory. `run/test` also reported
**rc=0** for that aborted run — the same trap-swallows-the-failure defect `run/player-gate`
fixed under BP-068 — which is worth its own task.

## 4. What this says about the switch

Not "it is safe". The diff says the blast radius is **near-total** — 202 of 210 ids move, and
the 8 that do not are all demoted tail ids (§1) — the edge enumeration names **2 cells that
can invert** and 5 more that can go quiet, and the baseline says **7.1 % of the suite is
already non-stationary before anything is reordered**. A 3-run
sequential baseline cannot separate a reorder effect from that noise floor, which is exactly
why @VE §18.6(a) requires an **interleaved A/B at one commit**.

Also recorded, because a reviewer will ask: **the APP class has no members**, so §4's rule-5
drop and EC-G8's APP arm are today asserting a property of an empty set. That is not a defect
— the arm exists so per-app blocking cannot silently come back — but nobody should read a
green APP arm as evidence about real APP-class tests.
