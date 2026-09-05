# M-HARNESS2 + WP-Z — test-harness remediation programme

> Owner: **Project Manager**
> Status: **proposed** — Phase 0 discharged, Phase 1 committed, Phases 2–5 scheduled behind named
> entry criteria. Only Phase 1 is *committed* by the programme decision.
> Board created: 2026-09-03 (board-reset Step 5).
> **This board is the single scheduling surface for this programme.** The reasoning behind every
> row — phases, cuts, deferrals, adjudications between the four reviews — is in
> [M-HARNESS2-PM-review.md](M-HARNESS2-PM-review.md). **Do not restate it here.** A row is a
> pointer: id, priority, status, one-line title, and the finding or requirement it comes from.

**Sources.** [Requirements (@VE, 55 reqs)](../verification/M-HARNESS2-requirements.md) ·
[WP-Z findings (@VE)](../verification/reviews/M-TESTQUAL-Z-findings-review.md) ·
[Architect review](../architecture/designs/M-HARNESS2-architect-review.md) ·
[Developer review](../architecture/designs/M-HARNESS2-DEV-review.md) ·
[QM review](../quality/M-HARNESS2-QM-review.md) ·
[PM programme decision](M-HARNESS2-PM-review.md).

---

## Read this before adding a row

**1. Double-booking is the failure mode this board exists to prevent.** WP-Z proposed 41 task rows.
**15 of them were found subsumed by an M-HARNESS2 requirement** and their WP-Z rows are **dropped**
— see [PM review §2.1](M-HARNESS2-PM-review.md). Fourteen keep their id, carrying the M-HARNESS2
work under it, and appear here exactly once: TASK-584, 591, 592, 593, 596, 599, 600, 602, 603, 606,
607, 608, 609, 613. **TASK-590 is retired entirely** into TASK-624 (the `UNMET` bucket is its
general form) and has no row anywhere. **TASK-586 had no row** — it is inside TASK-603's delete list (`T_PLR_25`'s registry copy,
executed 2026-09-05). **TASK-598 has a row again**: the human's 12/6/17 ruling moved the four `_02`
ids from delete to keep-and-fix, so the branch-A firmware work is real and needs scheduling. **If you are
about to paste WP-Z §4 onto a board, those 17 ids must not come with it.**

**2. Ids.** Allocated **TASK-579 … TASK-643**, verified against every board and the archive on
2026-09-03: the highest id in use on any board was 578, and no id in this band collided with
anything. 579–619 are WP-Z's own numbering, which that document declared provisional and
renumberable — **kept rather than renumbered on purpose**, because the human ruled on TASK-616,
617 and 618 *by those ids*, and six review documents cross-reference them. 621–643 were the PM
review's `(prov.)` block and are now real. **TASK-620 was never allocated** (it was only the top of
WP-Z's reserved band). **Next free id: TASK-648.**

**3. TASK-575 is deliberately not a row here.** It lives on
[tasks-architecture.md](tasks-architecture.md) (host-side FIXED, full `run/test` pass owed) and is
named in Phase 3's entry criteria instead. Copying it here would rebuild the mirror that was
deleted from `tasks.md` on the same day this board was created. **Do not add it.**

**4. Priorities.** P1 = a wrong verdict is being produced today, or a precondition of something
that is. P2 = mechanism and foundation. P3 = hygiene and ratchets. 579–619 carry WP-Z's own
severities unchanged; 621–643 are graded by the same rule.

**5. Two conditions apply to every row and are not repeated per phase.** No gate lands advisory —
a new check lands at zero, or blocking with a dated, owned, shrink-only ledger whose stale rows are
themselves blocking failures. And no declaration ships without a mechanical check behind it.

---

## Phase 0 — decisions and the free win — **DISCHARGED for the decisions**

**Entry:** none. **Owner:** human, @QM, @Architect. **Stop criterion:** none — cheapest action on
the programme.
**Exit:** TASK-616/617/618 ruled; LL-127 and LL-140 promoted or explicitly dismissed; the five ADRs
exist as documents, even if only as filed questions.
**Status: DISCHARGED 2026-09-04.** The three decision rows were RULED 2026-09-03; the five remaining
rulings were taken 2026-09-04 and written up as ADR-063 … ADR-067 (TASK-622), and TASK-619 and
TASK-621 are closed. Every exit criterion is met.

| task | pri | status | title |
|---|---|---|---|
| TASK-616 | P1 | **RULED 2026-09-03** | M-WEBRADIO close **stands**; the skip-rate criterion goes DEFERRED, re-run behind the board's release with ≥3 stations and a recorded build hash — [PM §5(a)](M-HARNESS2-PM-review.md) |
| TASK-617 | P1 | **RULED 2026-09-03** | class-order switch does **not** flip yet; exit criteria are the declaration + offline gates (TASK-591, TASK-626), **not** the shuffle campaign — [PM §5(b)](M-HARNESS2-PM-review.md) |
| TASK-618 | P1 | **RULED 2026-09-03** | verify-and-refuse sanctioned; `DUT_NO_RESTORE=1` permitted only as a dated interim exception retired by the conversion — [PM §5(c)](M-HARNESS2-PM-review.md) |
| TASK-619 | P3 | **DONE 2026-09-04** | `effect` **kept** — R14/R17/R19 are its consumers; `app/gen/mem_layout.py` (zero importers) survives only if TASK-606's no-mirror gate consumes it within one milestone, else it **and** its `run/check` step are deleted; `A-7` folds into ADR-066/IFC-008 — [WP-Z §4.4](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-621 | P1 | **DONE 2026-09-04** (`9358e5f`) — BP-073, BP-074 | promote LL-127 and LL-140, or dismiss each with a reason — [QM §6.3](../quality/M-HARNESS2-QM-review.md) |
| TASK-622 | P2 | **DONE 2026-09-04** — ADR-063, ADR-064, ADR-065, ADR-066, ADR-067 (+ IFC-007, IFC-008, IFC-003 v2 pending) | file the five ADRs as documents (App debug surface, render mechanism, console as interface, result artifact, DUT firmware lifecycle) — [Arch §9](../architecture/designs/M-HARNESS2-architect-review.md) |

---

## Phase 1 — host-only foundation (~28.5 d) — **COMMITTED, buildable today**

**Entry: none.** Every row is host-only: no board, no ADR, no graded finding, unaffected by the
TASK-557 pin.
**Exit — all counts, none arguable:** ids with no reachable `fail()` or a body that is one
unconditional `skip()` = **0**; CORE ids with a declared class and written reason = **43 of 43**;
gating-class ids whose precondition needs the network or the host file layout = **0**; consumers
parsing the human summary text = **0**; modules opening a serial port at import = **0**; every run
emits a schema-versioned artifact and every gate reads a typed verdict; `run/check` **≤ 90 s** and
`run/check-docs` **≤ 15 s**, measured and printed by the scripts.
**Stop criterion:** if after the four irreducible days (typed verdict, artifact, deletions) the
artifact cannot retire all three summary parsers, or `run/check` cannot be held under 90 s with the
new gates in it — **stop and re-scope the whole programme.**

| task | pri | status | title |
|---|---|---|---|
| TASK-609 | P3 | **DONE 2026-09-04** (`8927b16`) | six `__main__` guards + import-in-subprocess gate with a stubbed transport — [R48](../verification/M-HARNESS2-requirements.md) |
| TASK-600 | P2 | **DONE 2026-09-04** (`8927b16`) — 43→111 keys | generated key list sees `.cpp` bodies; count compared full-tree in `run/check` — [R7](../verification/M-HARNESS2-requirements.md) |
| TASK-623 | P3 | **DONE 2026-09-04** (`8927b16`) — blocking, 1-row ledger | cross-check the flake registry against declared gating classes — [R37](../verification/M-HARNESS2-requirements.md) |
| TASK-624 | P1 | **DONE 2026-09-04** | closed verdict enum incl. `UNMET`; typed gating; `UNMET` blocks; inversion selftest arm — [R28/R31/R38](../verification/M-HARNESS2-requirements.md). **Build to ADR-066/IFC-008**: `UNMET` exits **1**, owns no code of its own, and is distinct from `NOT-RUN` |
| TASK-608 | P3 | **DONE 2026-09-05** — artifact v1.0 landed; **3 of 3 summary parsers retired**, acceptance count gated at zero | schema-versioned run artifact carrying the run's premise; retire all three summary parsers — [R29/R30](../verification/M-HARNESS2-requirements.md) … |
| TASK-584 | P1 | **DONE 2026-09-04** — 6/6 now `fail()` on their subject; 32-scenario host proof | six residue callers convert the regression to a skip — make them fail — [D-2](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |
| TASK-603 | P2 | **DONE 2026-09-05** — executed at 12/6/17; **213 -> 195 ids**; R34 gate blocking on an 8-row ledger | delete 12 ids, retire 6 bodies to `UNOBSERVABLE`, no-reachable-fail gate — [R34/R4](../verification/M-HARNESS2-requirements.md). Disposition: [M-HARNESS2-task603-disposition.md](../verification/M-HARNESS2-task603-disposition.md) … |
| TASK-625 | P3 | **DONE 2026-09-05** — landed FIRST, ahead of TASK-603, per disposition §4.7 | write the id-retirement procedure into `docs/process/` — [Dev D7](../architecture/designs/M-HARNESS2-DEV-review.md). [test_id_retirement.md](../process/test_id_retirement.md); worked example is `T136`'s stale archive `Status: pass`, which no C6 sub-check can see |
| TASK-587 | P1 | OPEN — unblocked; **scope shrank to 5 - 2 = 3** | five M-CLOCK-STYLES exit criteria re-recorded DEFERRED, not PASS — [H-2](../verification/reviews/M-TESTQUAL-Z-findings-review.md). TASK-603 already re-recorded **C3** and **C4** DEFERRED, because both rested on ids it retired UNOBSERVABLE … |
| TASK-598 | P2 | OPEN — **re-opened by TASK-603** | the four `_02` ids (`T_MA_02`, `T_GOL_02`, `T_WX_02`, `T_CX_02`) share one fate — [D-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). The 12/6/17 ruling puts all four in **keep-and-fix**, i.e … |
| TASK-591 | P1 | **DONE 2026-09-04** — **CORE 43 -> 23**; 25 gating declared + 20 demoted, 4 [ledgered](../verification/gating_class_declarations.md) pending TASK-634 | every gating class declared with a written reason; `check_test_meta.py` G1/G2/G3 blocking — [R35](../verification/M-HARNESS2-requirements.md). **TASK-617 exit criterion NOT met while the ledger holds rows** |
| TASK-626 | P1 | **GATE DONE 2026-09-05 — the 8 demotions need a human ruling**; host-layout 0, unexemptable; 7 named ids + `T_X07_01` [ledgered](../verification/gating_offline_exceptions.md) | a gating class may not need the network or the host file layout — [R36](../verification/M-HARNESS2-requirements.md). **A TASK-617 exit criterion, NOT met** — the gate reads 8 |
| TASK-596 | P2 | **DONE 2026-09-04** — accessor + ratchet gate; 25 of 171 sites migrated … | one typed accessor; no oracle or restore satisfied by a default — [R18](../verification/M-HARNESS2-requirements.md). `Dut.get_int/str/bool/float/val` + `set_val` raise `BadField` (-> FAIL) or `NoAnswer` (-> `UNMET`); `gate/check_defaulted_reads.py` blocking on a dated shrink-only ledger |
| TASK-585 | P1 | **DONE 2026-09-04** — `stock.py` + the stock helpers at zero defaults | the Stock fetch oracle's sentinel is an unconditional pass across nine ids — [G-2](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |
| TASK-602 | P2 | **DONE 2026-09-05** — `Dut.saved`/`Dut.injected`; gate blocking on a [197-write ledger](../verification/unrestored_mutations_ratchet.md) | restore via a context manager; gate on *use of the manager*, not static matching — [R17](../verification/M-HARNESS2-requirements.md). Four `finally`-shaped leaks are fixtures the gate flags |
| TASK-627 | P2 | **DONE 2026-09-05** — `── SKIP by scope (N) ──`, most-skipped scope first | print the per-scope SKIP count in the run summary — [QM §7](../quality/M-HARNESS2-QM-review.md). Fed by the same installed meta provider as the artifact, so it needed 608's typed data … |
| TASK-611 | P3 | **DONE 2026-09-05** — 5 checks; 3 at zero, 6 on a [dated ledger](../verification/plan_integrity_exceptions.md) | plan integrity: id collisions, stale rows, duplicate-body detection — [R46](../verification/M-HARNESS2-requirements.md). Re-measured: `A-15` now **0**, `F-2` is **4** not 3 (`T242`), 6 duplicate declarations fixed |
| TASK-628 | P2 | BLOCKED — TASK-609 | replay engine in `lib/`: stub transport, keyed store, virtual clock, plus its negative test — [R10](../verification/M-HARNESS2-requirements.md) |
| TASK-629 | P3 | **DONE 2026-09-05** — both scripts print their budget line; measured warm after TASK-602/611/626: `run/check` **39.5 s** of 90, `run/check-docs` **1.0 s** of 15 (cold `run/check` 94.1 s, rebuild-dominated, and says so) | host-gate wall-clock budget, measured and printed by the scripts — [Dev D6](../architecture/designs/M-HARNESS2-DEV-review.md) |
| TASK-630 | P3 | OPEN — TASK-624 done | scaffold the record — emit the generated fields, leave the author the two that need thought — [Dev D4](../architecture/designs/M-HARNESS2-DEV-review.md) |
| TASK-631 | P3 | BLOCKED — TASK-628 | a FAIL carries the last 20 command/reply pairs — [Dev D3](../architecture/designs/M-HARNESS2-DEV-review.md) |
| TASK-632 | P2 | **DONE 2026-09-05** — C3 **deleted**, `T_DOC_08` retired | dispose of the advisory documentation check — [QM §3.1](../quality/M-HARNESS2-QM-review.md). All 58 findings measured as correct prose; disposition in [M-DOCLIFE §C3](../architecture/designs/M-DOCLIFE-check-docs-spec.md) |
| TASK-647 | P2 | **DONE 2026-09-05** — blocking, opening [ledger](../verification/rowlen_exceptions.md) **18 rows, measured**; corpus 103 -> 168 rows across 4 boards | promote ROWLEN to blocking, and discover the board corpus instead of enumerating it — `tasks-harness2.md` was never scanned. [M-ROWGATE §8](../architecture/designs/M-ROWGATE-task-board-length-check.md) |
| TASK-644 | P3 | OPEN — @Architect | reconcile the specification gaps TASK-624 and TASK-608 surfaced: `ORDER-DEPENDENT` in R28 vs ADR-066 D2's 7-member enum; "attributable" undefined in D4; IFC-008's cross-leg composition rule; whether the artifact copying `cls`/`scope`/`effect` per row is a mirror (LL-114) or a snapshot … [TASK-608 report](../verification/M-HARNESS2-requirements.md) |
| TASK-645 | P3 | OPEN | the artifact's premise cannot identify what it ran against: "harness version" (R30) has no source in the tree, "the board" (ADR-066 D3) has no identity surviving a USB re-enumeration, and `run/dut-health` exits before `print_results` so emits none — against R29's "every run MUST" |
| TASK-646 | P2 | OPEN | `run/test-sync`'s 20 ids have no machine interface at all — `run_sync_tests.py` keeps a private pre-TASK-520 results layer with no flake policy, no `NOT-RUN`, no `UNMET` and now no artifact — [A-6](../verification/reviews/M-TESTQUAL-A-harness-review.md) |

---

## Phase 2 — the 80-minute session (board)

**Entry: TASK-618 — RULED 2026-09-03, so this phase is unblocked in principle.** It is *satisfied*
when TASK-633 lands; until then the sanctioned dated interim exception (`DUT_NO_RESTORE=1`, owned by
TASK-618) is the permitted path. **Killing a script mid-flight is not a workaround** — it races the
trap-guarded restore and can boot-loop the board.
**Exit:** each of the three armed-injector clusters confirmed or refuted with a dated record; both
isolated-vs-in-suite splits measured; the CORE skip census taken; the three cluster fixes landed.
**Stop criterion — the one most wanted on the record:** if the session **refutes all three
clusters**, group STA drops from foundation to hygiene, **Phase 3 is cancelled**, and the Phase 5
corpus retrofit is cut to delta-scoped rules only.

| task | pri | status | title |
|---|---|---|---|
| TASK-633 | P1 | OPEN — ADR-067 | DUT entry points verify-and-refuse, refusal is **exit 3** (`elf-mismatch`, RIG); delete the restore trap — it is shared across 15 `run/*` scripts, not two; update `CLAUDE.md` — [R51](../verification/M-HARNESS2-requirements.md) |
| TASK-634 | P1 | BLOCKED — TASK-633 | run the 80-minute session and file its dated records — [WP-Z §5](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-579 | P1 | BLOCKED — TASK-634 | the WebRadio forced-connect-fail injector nothing clears — [F-4](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-580 | P1 | BLOCKED — TASK-634 | the heatmap injector wedges the sub-view and the block behind it — [G-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-581 | P1 | BLOCKED — TASK-634 | the aircraft injector freezes the radar for the rest of the boot — [H-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-582 | P1 | BLOCKED — TASK-634 | an inverted guard that passes exactly on the regression — [C-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-583 | P1 | **CLOSED 2026-09-05, subject deleted** — not fixed, GONE | the error-suite teardown writes the wrong state — [F-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). TASK-603 deleted `_wr_err_test` with the only four bodies that called it (`T_WR_ERR_01`-`04`) … [retired_test_ids.md](../verification/retired_test_ids.md) |
| TASK-588 | P1 | BLOCKED — TASK-624 | a skipped health check announced as a health PASS — [C-4](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-597 | P2 | BLOCKED — TASK-624 | the player gate's health machinery cannot fire — [E-13](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-595 | P2 | BLOCKED — TASK-579 | sweep the flake registry against its call sites, both directions — [C-7](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-589 | P1 | OPEN | repair the `run/screendump` instrument, broken at import — [A-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). Prerequisite of Phase 4 |

---

## Phase 3 — order and state hygiene, and the switch question (board)

**Entry:** Phase 1 complete; Phase 2 complete **and its stop criterion not triggered**; **TASK-557
closed or explicitly signed off by the human**. TASK-575's owed full `run/test` pass (on
[tasks-architecture.md](tasks-architecture.md), not duplicated here) belongs to this entry too.
**Blocked at phase level by TASK-557** — every row below inherits it.
**Exit:** armed device state enumerable and asserted at every test boundary, with the failure
landing on the test that armed it; per-family shuffled runs produce the canonical verdict set;
TASK-617's exit criteria met and the switch decision re-put to the human with evidence.
**Stop criterion:** if demoting the seven network-dependent CORE ids plus the host-file-grep id
leaves CORE with too few members to gate anything meaningful — **cancel the class-order switch
outright and close TASK-566 as WONTFIX.** A gating class that gates nothing is worse than none,
because it carries a gate's authority.

| task | pri | status | title |
|---|---|---|---|
| TASK-635 | P2 | BLOCKED — TASK-608 | armed device state enumerable; boundary check attributes the leak to the arming test — [R14](../verification/M-HARNESS2-requirements.md) |
| TASK-592 | P2 | BLOCKED — TASK-602 | add the readiness-skip and unrestored-set scanners to the edge enumeration — [B-4](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-636 | P2 | BLOCKED — TASK-624 | per-family shuffle capability and the order-dependent verdict value — [R20/R21](../verification/M-HARNESS2-requirements.md) |
| TASK-594 | P2 | BLOCKED — TASK-636 | two ids whose own predecessors destroy their precondition — [B-3](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-604 | P2 | BLOCKED — phase entry | six ids drive a different app than their record says — [E-5](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-605 | P2 | BLOCKED — TASK-634 | two ids reach their app only because of what ran before them — [E-11](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |

---

## Phase 4 — the observability contract (firmware; per-app, never a sweep)

**Entry: MET for the ADRs, 2026-09-04.** ADR A is **ADR-063** (`App` gains `dbgGet`/`dbgSet`;
identity and progress move to the shell) and ADR B is **ADR-064** (GRAM readback, **on demand only**;
a periodic or render-path signature is a violation of the decision, not a future option). Still
required: `run/screendump` repaired (TASK-589); `.dram0.bss` headroom
**re-derived fresh** from `run/build-debug` and the `.map` immediately before each commit, never
remembered. **Permitted while the board is pinned** — the human confirmed on 2026-09-03 that the
TASK-557 pin forbids restoring *production*, not reflashing the same debug env, provided
`-DBOD_WATCH` survives every commit and no flash happens inside a measurement window.
**Exit:** the shell-side identity guard and tick/repaint counters landed; a signature command with
ink and distinct-colour metrics exists, preconditioned on a live readback channel in the HEALTH
class; every visual claim has a mechanism or is carried as a dated `UNOBSERVABLE` record with an
owning task; no milestone exit criterion rests on an `UNOBSERVABLE` id and carries a PASS.
**Stop criterion:** if a freshly derived `.dram0.bss` headroom reads under ~1 KB — **stop after the
shell half** and ledger the per-app clauses. This pool has measured 0 B, 40 B, 304 B and 9 920 B
inside three months; the shell half is ~60 B, the per-app half is not worth a link failure.

| task | pri | status | title |
|---|---|---|---|
| TASK-637 | P2 | OPEN — ADR-063 taken | shell-side identity guard + tick/repaint counters — fixes the class for all thirteen apps — [Arch §1.2](../architecture/designs/M-HARNESS2-architect-review.md) |
| TASK-638 | P2 | BLOCKED — TASK-589 (ADR-064 taken) | render signature over panel readback, ink/entropy metrics, time freeze, readback liveness check — [R5](../verification/M-HARNESS2-requirements.md) |
| TASK-593 | P2 | BLOCKED — TASK-637 | per-app result and entry-state observables, one app per commit, capped per app — [R3](../verification/M-HARNESS2-requirements.md) |
| TASK-639 | P3 | BLOCKED — TASK-638 | the clock family is rewritten, not migrated — ledger five claims, re-file as new ids — [Dev §8.2](../architecture/designs/M-HARNESS2-DEV-review.md) |

---

## Phase 5 — the ratchets (open-ended, delta-scoped)

**Entry:** Phases 1 and 3. **Blocked at phase level by Phase 3, hence by TASK-557.**
**Exit:** each ratchet count is printed by the thing developers already run, and has fallen across
two consecutive milestones.
**Stop criterion:** any ratchet whose count is unchanged across two consecutive milestones is
**cut, not carried.** That is C3's lesson applied in advance, and the only defence against a rule
that reads the same number in a year.
**Deliberately not sequenced past its entry criteria** — a ratchet with a date is a sweep wearing a
ratchet's clothes.

| task | pri | status | title |
|---|---|---|---|
| TASK-607 | P3 | BLOCKED — TASK-608 | one wait helper, one app-entry helper, one timeout policy with users — [R22/R24](../verification/M-HARNESS2-requirements.md) |
| TASK-640 | P3 | BLOCKED — TASK-607 | classify all synchronisation sleeps, publish the three counts, then set the floor — [R23](../verification/M-HARNESS2-requirements.md) |
| TASK-606 | P3 | BLOCKED — phase entry | mirror-equality gate, pairs generated wherever the symbol is already generated — [R42](../verification/M-HARNESS2-requirements.md) |
| TASK-613 | P3 | BLOCKED — TASK-606 | a numeric bound in an assertion **you touch** cites its origin — delta-scoped only — [R44](../verification/M-HARNESS2-requirements.md) |
| TASK-599 | P2 | BLOCKED — TASK-609 | one session layer; migrate the four bypassing harnesses — [R47](../verification/M-HARNESS2-requirements.md) |
| TASK-641 | P3 | BLOCKED — TASK-628 | generate the read-key set; the author declares a claim class from a closed enum — [R1](../verification/M-HARNESS2-requirements.md) |
| TASK-642 | P3 | BLOCKED — TASK-641 | two-field falsifier: executable replay, and physical with an enforced expiry — [R9](../verification/M-HARNESS2-requirements.md) |
| TASK-643 | P3 | BLOCKED — TASK-642 | mutation driver with the control arm; a transcript miss is inconclusive, never a confirmation — [R10](../verification/M-HARNESS2-requirements.md) |
| TASK-601 | P2 | BLOCKED — TASK-599 | the TLS preflight runs from every entry point, not one — [A-5](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-610 | P3 | OPEN — unblocked | collapse 26 ids to about 11 behaviours — [B-16](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-612 | P3 | BLOCKED — phase entry | scope resolution for the 55 % of the tree it cannot reach — [B-9](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-614 | P3 | OPEN — unblocked; **scope grew** | registry and tooling honesty — [B-13](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |
| TASK-615 | P3 | OPEN — unblocked; **scope grew** | small correctness debts with named fixes — [H-17](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |

---

## Totals

| phase | rows | days | committed |
|---|---|---|---|
| 0 — decisions | 6 (all closed) | ~1 | yes — **discharged 2026-09-04** |
| 1 — host-only foundation | 21 | ~28.5 | **yes** |
| 2 — the 80-minute session | 11 | ~6 | no — scheduled |
| 3 — order and state hygiene | 6 | ~7.5 | no — blocked on TASK-557 |
| 4 — observability contract | 4 | ~10 | no — ADR-063/064 taken; TASK-637 open, TASK-638 gated on TASK-589 |
| 5 — ratchets | 13 | ~28.5 | no — blocked on Phase 3 |
| **total** | **61** | **~81** | **only Phase 1** |

**~60 engineer-days were cut outright and are not on this board** — R44's retrofit, R8, R26, R53's
budget table, R11's quarterly campaign, the three-consecutive-shuffled-runs criterion, R1's prose
oracle reason, R16 as an authored declaration, and the rubric re-audit as an acceptance criterion.
Each cut is priced and justified in [PM review §4.1](M-HARNESS2-PM-review.md). **Do not re-file one
without reading why it was cut** — several were cut because they had no completion condition, and
re-filing them restores that defect.

**Phase 1, day 1** — the row set that needs no board, no ADR and no decision: **TASK-609**
(six import guards + the import-in-subprocess gate), **TASK-600** (the generated-key-list glob fix)
and **TASK-623** (the flake-registry cross-check). One day, host-only. TASK-609 closes the defect
that reset the board during the audit that found it.
