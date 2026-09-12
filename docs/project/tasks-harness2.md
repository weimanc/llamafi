# M-HARNESS2 + WP-Z — test-harness remediation programme

> Owner: **Project Manager**
> Status **2026-09-09**: **Phases 0 and 1 COMPLETE** (32 rows, all closed); **Phase 2's session is
> executed** and 4 rows remain (582, 588, 595, 597); **Phase 4: TASK-638 DONE**, 637/639 open;
> **Phase 5: TASK-671 DONE** (the runtime R34 gate is live on 193 transcripts), 641's taxonomy
> ruled accepted, 672–674 and 676 filed; Phases 3 and the rest of 5 stay behind TASK-557. Only Phase 1 was
> ever *committed* by the programme decision — 2, 4 and 5 have been worked opportunistically where
> a row was unblocked, which is why closed rows appear in phases that are not committed.
> **Where to start cold: the Totals table at the foot of this file** — it names the live rows per
> phase and which of them are blocked by what.
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
ids from delete to keep-and-fix, so the branch-A firmware work was real and needed scheduling. That
ruling was **reversed on 2026-09-06** — branch B, all four deleted, with the replacement filed
against ADR-063 D3 (`T_APPKEY_01`, blocked on TASK-637) rather than as four more hand-written
`cmdTap` branches; the row is DONE. **If you are
about to paste WP-Z §4 onto a board, those 17 ids must not come with it.**

**2. Ids.** Allocated **TASK-579 … TASK-643**, verified against every board and the archive on
2026-09-03: the highest id in use on any board was 578, and no id in this band collided with
anything. 579–619 are WP-Z's own numbering, which that document declared provisional and
renumberable — **kept rather than renumbered on purpose**, because the human ruled on TASK-616,
617 and 618 *by those ids*, and six review documents cross-reference them. 621–643 were the PM
review's `(prov.)` block and are now real. **TASK-620 was never allocated** (it was only the top of
WP-Z's reserved band). **TASK-648 was never allocated either** — the band closed at 647 and the
next filing started at 649. Allocated since: **TASK-649…660** on [tasks.md](tasks.md) (the TASK-587
escalations and the oracle-sweep rulings) and **TASK-661** here. **Next free id: TASK-682** (671–674, 676–681 filed here; 675 on tasks.md)
(662–668 filed 2026-09-07 on [tasks.md](tasks.md) from the Phase 2 hardware sessions; **TASK-669**
the same day, the board-currency gate, and **TASK-670** the LL-151 BP candidate, both also on
[tasks.md](tasks.md)).

**3. TASK-575 has a row here since 2026-09-10** — in § Rig stability, moved with the rest of the
TASK-557 chain when `tasks-architecture.md` was retired. Until then it was deliberately *not* a row
here, to avoid rebuilding the mirror deleted from `tasks.md` on 2026-09-03; with the source board
gone there is one copy again, and it is this one.

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

## Phase 1 — host-only foundation (~28.5 d) — **COMPLETE 2026-09-06, all 26 rows closed**

**Every exit criterion below was met and is mechanically re-checkable.** The stop criterion did not
fire: all three summary parsers were retired by TASK-608, and `run/check` holds at **43.5 s warm**
(cold ~100 s, rebuild-dominated, and the script says so) against its 90 s budget.

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
| TASK-587 | P1 | **DONE 2026-09-06**; its 3 escalations **RULED 2026-09-06** | M-CLOCK-STYLES criteria re-recorded DEFERRED, not PASS — [H-2](../verification/reviews/M-TESTQUAL-Z-findings-review.md). Rulings: clock **not blocked**, criteria stay DEFERRED (no work scheduled); **M-PLANERADAR RE-OPENED**, TASK-649..652; heatmap claim downgraded, TASK-653 — [tasks.md](tasks.md) |
| TASK-598 | P2 | **DONE 2026-09-06** — branch B: all four **deleted**, [registered](../verification/retired_test_ids.md); replacement `T_APPKEY_01` filed `blocked` on TASK-637 (ADR-063 D3) | the four `_02` ids (`T_MA_02`, `T_GOL_02`, `T_WX_02`, `T_CX_02`) share one fate — [D-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-591 | P1 | **DONE 2026-09-04** — **CORE 43 -> 23**; 25 gating declared + 20 demoted, 4 ledgered. Ledger emptied and deleted by TASK-626 2026-09-06; **CORE 18, all declared, G1/G2/G3 blocking at zero with no ledger** | every gating class declared with a written reason — [R35](../verification/M-HARNESS2-requirements.md) |
| TASK-626 | P1 | **DONE 2026-09-06** — 8 rulings executed, **15 findings -> 3** ([ledger](../verification/gating_offline_exceptions.md)); **TASK-617 criterion still NOT met**: `T-CDWN-02`'s arming residue | a gating class may not need the network or the host file layout — [R36](../verification/M-HARNESS2-requirements.md) |
| TASK-596 | P2 | **DONE 2026-09-04** — accessor + ratchet gate; 25 of 171 sites migrated … | one typed accessor; no oracle or restore satisfied by a default — [R18](../verification/M-HARNESS2-requirements.md). `Dut.get_int/str/bool/float/val` + `set_val` raise `BadField` (-> FAIL) or `NoAnswer` (-> `UNMET`); `gate/check_defaulted_reads.py` blocking on a dated shrink-only ledger |
| TASK-585 | P1 | **DONE 2026-09-04** — `stock.py` + the stock helpers at zero defaults | the Stock fetch oracle's sentinel is an unconditional pass across nine ids — [G-2](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |
| TASK-602 | P2 | **DONE 2026-09-05** — `Dut.saved`/`Dut.injected`; gate blocking on a [197-write ledger](../verification/unrestored_mutations_ratchet.md) | restore via a context manager; gate on *use of the manager*, not static matching — [R17](../verification/M-HARNESS2-requirements.md). Four `finally`-shaped leaks are fixtures the gate flags |
| TASK-627 | P2 | **DONE 2026-09-05** — `── SKIP by scope (N) ──`, most-skipped scope first | print the per-scope SKIP count in the run summary — [QM §7](../quality/M-HARNESS2-QM-review.md). Fed by the same installed meta provider as the artifact, so it needed 608's typed data … |
| TASK-611 | P3 | **DONE 2026-09-05** — 5 checks; 3 at zero, 6 on a [dated ledger](../verification/plan_integrity_exceptions.md) | plan integrity: id collisions, stale rows, duplicate-body detection — [R46](../verification/M-HARNESS2-requirements.md). Re-measured: `A-15` now **0**, `F-2` is **4** not 3 (`T242`), 6 duplicate declarations fixed |
| TASK-628 | P2 | **DONE 2026-09-06** — `lib/replay.py`; 40-arm negative suite blocking at zero in `run/check`; **191 of 195 ids recordable**, measured | replay engine in `lib/`: stub transport, keyed store, virtual clock, plus its negative test — [R10](../verification/M-HARNESS2-requirements.md). A miss is `INCONCLUSIVE` in the data, never a verdict; transcripts ELF-stamped |
| TASK-629 | P3 | **DONE 2026-09-05** — both scripts print their budget line; measured warm after TASK-602/611/626: `run/check` **39.5 s** of 90, `run/check-docs` **1.0 s** of 15 (cold `run/check` 94.1 s, rebuild-dominated, and says so) | host-gate wall-clock budget, measured and printed by the scripts — [Dev D6](../architecture/designs/M-HARNESS2-DEV-review.md) |
| TASK-630 | P3 | **DONE 2026-09-06** — `run/new-test`; 34-arm negative suite blocking at zero | scaffold the record — [Dev D4](../architecture/designs/M-HARNESS2-DEV-review.md). Generates module/scope/cls-seed/effect, the registry line, the plan entry and a gate-clean body; REFUSES the oracle and a gating `cls_reason` (its stub is under the 80-char floor, so it reds `run/check` until written) |
| TASK-631 | P3 | **DONE 2026-09-06** — artifact schema **1.1**, `results[].exchanges`; measured **3.0-3.8 µs/exchange**, ~0.12 s per full run, 0 B on a green artifact | a FAIL carries the last 20 command/reply pairs — [Dev D3](../architecture/designs/M-HARNESS2-DEV-review.md). Artifact only, never the summary text; FAIL **and** UNMET; redacted |
| TASK-632 | P2 | **DONE 2026-09-05** — C3 **deleted**, `T_DOC_08` retired | dispose of the advisory documentation check — [QM §3.1](../quality/M-HARNESS2-QM-review.md). All 58 findings measured as correct prose; disposition in [M-DOCLIFE §C3](../architecture/designs/M-DOCLIFE-check-docs-spec.md) |
| TASK-647 | P2 | **DONE 2026-09-05** — blocking, opening [ledger](../verification/rowlen_exceptions.md) **18 rows, measured**; corpus 103 -> 168 rows across 4 boards | promote ROWLEN to blocking, and discover the board corpus instead of enumerating it — `tasks-harness2.md` was never scanned. [M-ROWGATE §8](../architecture/designs/M-ROWGATE-task-board-length-check.md) |
| TASK-644 | P3 | **DONE 2026-09-06** | all five specification gaps ruled in the documents that own them — [ADR-066](../architecture/decisions/ADR-066.md) D2a/D4a, [IFC-008](../architecture/interfaces/IFC-008.md) I8/I9 + D-COMP/D-SNAP/D-VER, [R28/R21](../verification/M-HARNESS2-requirements.md) corrected. Four of five confirm as-built; **D2a narrows TASK-636** |
| TASK-645 | P3 | **DONE 2026-09-06** — artifact schema **1.2**; T_ART_16/17 blocking | the premise now identifies what it ran against: harness = a content hash over `app/tools/**/*.py` + `run/*` (git is provenance only); board = the efuse MAC via a new `get boardId` key, port demoted to `transport`. **`get boardId` DUT-VERIFIED 2026-09-07**, both arms (session review §0) |
| TASK-646 | P2 | **DONE 2026-09-06** — on `lib/results` + the artifact; `check_private_results.py` blocking, [1-row ledger](../verification/private_results_exceptions.md) | `run/test-sync`'s 20 ids had no machine interface — [A-6](../verification/reviews/M-TESTQUAL-A-harness-review.md). They now get the flake retry, `NOT-RUN`/`UNMET` and the artifact. The private `Dut` stays: TASK-599 |

---

## Phase 2 — the 80-minute session (board) — **SESSION EXECUTED 2026-09-07; 3 rows remain**

**Status 2026-09-07.** The session ran twice — A (`d3a3600`) and B (`f66a4d2`) — and is recorded in
[M-TESTQUAL-phase2-session-review.md](../verification/reviews/M-TESTQUAL-phase2-session-review.md).
**Exit criteria: met.** All three clusters ruled (WebRadio and Stock CONFIRMED **and fixed**,
PlaneRadar REFUTED); both isolated-vs-in-suite splits measured, plus two more (`E #2` refuted,
`D #6` confirmed); the CORE skip census taken (**17 of 18** reach a verdict, against 18 not WP-Z's
43). **36 of 58** NEEDS-DUT items settled. **The stop criterion did not fire** — it required all
three refuted; two were confirmed. So group STA stays foundation, **Phase 3 is not cancelled** but
shrinks by roughly a third, and the Phase 5 corpus retrofit is not cut.
**What the session cost, and the lesson:** ~90 minutes of board time went into D-1/D-2 — TASK-633's
conversion had never been executed against a board and both its headline mechanisms were dead, and
the ELF guard had been inert since 2026-08-17 while every artefact said otherwise. A gate that greps
for a call is not a gate that runs it (TASK-661).
**Still open here: TASK-582, TASK-588, TASK-597, TASK-589, TASK-595** — none blocked by the session
any more; 588/597 wait on nothing but hands. **589 landed 2026-09-07 (PARTIAL — uncommitted)**, so
Phase 4's render half is no longer waiting on an instrument.

**Entry: TASK-618 — RULED 2026-09-03. SATISFIED 2026-09-06 by TASK-633.** The entry points now
verify and refuse (ADR-067): they read the board's build identity and exit 3 (`elf-mismatch`, RIG) if
it is not what the run needs. **The restore is gone from all fourteen scripts**, so a board pinned to
a debug build (TASK-557) no longer blocks this phase, and `DUT_NO_RESTORE=1` — the dated interim
exception owned by TASK-618 — has met its retirement condition and is **@PM's row to retire** (a
stale row is itself a blocking failure, ADR-067 D3).
**The standing hazard is unchanged (ADR-067 D5):** never kill a `run/flash*` or soak script
mid-flight. It no longer races a restore, but it still races a flash or an in-flight measurement.
**What changed for the operator:** the board keeps whatever build the last flash put there, including
after a run. Flash what you need first, with `run/flash-debug` / `run/flash-player` /
`run/flash-webradio`; the entry point will tell you loudly if you got it wrong.
**Exit:** each of the three armed-injector clusters confirmed or refuted with a dated record; both
isolated-vs-in-suite splits measured; the CORE skip census taken; the three cluster fixes landed.
**Stop criterion — the one most wanted on the record:** if the session **refutes all three
clusters**, group STA drops from foundation to hygiene, **Phase 3 is cancelled**, and the Phase 5
corpus retrofit is cut to delta-scoped rules only.

| task | pri | status | title |
|---|---|---|---|
| TASK-633 | P1 | **DONE 2026-09-06** — 14 entry points + `lib.sh`; gate blocking at zero; 27-arm negative suite | verify-and-refuse, **exit 3** (`elf-mismatch`, RIG); restore DELETED from all 14 — [R51](../verification/M-HARNESS2-requirements.md). **`DUT_NO_RESTORE=1` RETIRED 2026-09-07 (@PM)**, never implemented in code. **As-built defects: TASK-661 (fixed), TASK-666 (open)** |
| TASK-661 | P1 | **DONE 2026-09-07** — hardware-verified | ADR-067 as-built: wrong cwd, a port open fighting the monitor, and an ELF guard inert since 2026-08-17. Fixed; the gate now EXECUTES the mechanism — [ADR-067](../architecture/decisions/ADR-067.md), [D-1/D-2](../verification/reviews/M-TESTQUAL-phase2-session-review.md) |
| TASK-634 | P1 | **DONE 2026-09-07** — two sessions (`d3a3600`, `f66a4d2`); **36 of 58** NEEDS-DUT items settled | run the 80-minute session and file its dated records — [WP-Z §5](../verification/reviews/M-TESTQUAL-Z-findings-review.md). **Stop criterion NOT triggered** — 2 confirmed, 1 refuted; Phase 3 stands, shrunk |
| TASK-579 | P1 | **DONE 2026-09-07** (`f66a4d2`) — forced connect-fail **45 → 1**, `wrState=5` → **0**, 4 downstream ids newly PASS | the WebRadio forced-connect-fail injector nothing clears — [F-4](../verification/reviews/M-TESTQUAL-Z-findings-review.md). Fixed in the harness: `_wr_deadurls_custody` via `Dut.injected` (BP-073); session review §B.3 |
| TASK-580 | P1 | **DONE 2026-09-07** (`f66a4d2`) — "could not normalize to list view" **6 SKIPs → 0**, `T203` control holds | the heatmap injector wedges the sub-view and the block behind it — [G-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). One-line firmware fix: `backToPrevView()` tested `== HeatmapDetail`, one of two detail views; `!= List` covers both (§B.2) |
| TASK-581 | P1 | **CLOSED 2026-09-07 — REFUTED on hardware**, not fixed | the aircraft injector freezes the radar for the rest of the boot — [H-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). All eight ids PASS; `H-5`'s companion claim (`T_PR_05` a permanent SKIP) is **STALE** — it passes — [§1.3](../verification/reviews/M-TESTQUAL-phase2-session-review.md) |
| TASK-582 | P1 | **OPEN — unblocked 2026-09-07** (TASK-634 done) | an inverted guard that passes exactly on the regression — [C-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). Its id `T-BUSY-05` was demoted out of CORE by TASK-626, so it no longer gates the run — the inverted guard itself is still unfixed |
| TASK-583 | P1 | **CLOSED 2026-09-05, subject deleted** — not fixed, GONE | the error-suite teardown writes the wrong state — [F-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). TASK-603 deleted `_wr_err_test` with the only four bodies that called it (`T_WR_ERR_01`-`04`) … [retired_test_ids.md](../verification/retired_test_ids.md) |
| TASK-588 | P1 | **OPEN — unblocked** (TASK-624 DONE 2026-09-04) | a skipped health check announced as a health PASS — [C-4](../verification/reviews/M-TESTQUAL-Z-findings-review.md). `unmet()` is the verdict it needed and it now exists |
| TASK-597 | P2 | **OPEN — unblocked** (TASK-624 DONE 2026-09-04) | the player gate's health machinery cannot fire — [E-13](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-595 | P2 | **OPEN — unblocked 2026-09-07** (TASK-579 done); **scope grew** | sweep the flake registry against its call sites, both directions — [C-7](../verification/reviews/M-TESTQUAL-Z-findings-review.md). Hardware confirmed `T092`/`T_PLR_07` and found a **third**: `T_WR_EJECT_01` FAILs `UNDECLARED flake`. Also owns the 4 `no_reachable_fail` rows (`T084`/`T087`/`T091`/`T092`) |
| TASK-589 | P1 | **DONE 2026-09-07** (`69984ed`) | repair `run/screendump`, broken at import — [A-1](../verification/reviews/M-TESTQUAL-Z-findings-review.md). Portal branch DROPPED not restored; 3 dependants wrapped; `--colorprobe` 25/25 + 4/4 swatch on DUT; gated by `check_screendump_instrument.py` |

---

## Rig stability and the M-TESTARCH remainder — rows moved from `tasks-architecture.md` (retired 2026-09-10)

That board was a stopgap by its own header ("when every remaining entry here is closed, fold what's
left into `tasks-archive.md` and delete this file"). It was retired on 2026-09-10 with 18 live rows
left, not zero: the 13 below are harness and rig work and belong beside the phases they block —
**TASK-557 is Phase 3's entry condition** — and the other five (462, 484, 486, 549, 568) went to
[tasks.md § inherited](tasks.md). Its 94 closed rows and every prose section are in
[tasks-archive.md § tasks-architecture.md — retired](tasks-archive.md#tasks-architecturemd--retired-2026-09-10-verbatim-snapshot).
TASK-557's 20 680-character measurement record moved to
[EXP-025](../rnd/reports/EXP-025-rig-instability-record-task557.md) and its row is now the pointer
BP-069 always asked for. Rows other than 557 moved **verbatim**; the ROWLEN and board-currency
ledger entries that name them were re-keyed to this file in the same commit, not cleared.

| task | pri | status | title |
|---|---|---|---|
| TASK-557 | **P2** | **ROOT CAUSE 2026-09-12 — rig wiring, not the board** | Sag + USB drop reproduce only for DUT1 `d4:8a…` on its ORIGINAL cable/port (2×2, 4/4 consistent): [EXP-039](../rnd/reports/EXP-039-board-cable-interaction.md). Cable/hub null test discharged. Open: replace that cable, re-verify 0/3. **Owner:** @RnD |
| TASK-575 | **P2** | **FIXED 2026-09-02 — host-tested; DUT regression pass PENDING** | `_TeeSerial` (`app/tools/lib/dut.py`) wraps the serial object but defines no `__setattr__`, so every `self.ser.timeout = …` in the readiness path sets a **shadow attribute on the wrapper** and never reaches pyserial. Read timeouts have silently been whatever the constructor passed, for as long as the tee has existed. TASK-564's own deadline loops are monotonic-clock based and so are correct regardless, which is why this surfaced by inspection rather than as a failure — but every other caller that sets a timeout is affected. Fixed by a `__setattr__` that forwards to the wrapped object, with `_OWN_ATTRS` naming the wrapper's own state explicitly (`run_id`/`boot_count` have no leading underscore, so an underscore rule would have pushed the generation counter onto pyserial). 14 cases in `test_boot_gate.py`. **The fix tightens real timeouts across the whole harness** — 14 post-wrap sites in `dut.py`/`shell.py` that meant 0.3–1.0 s were silently getting the constructor's value, and `test_fetch_stress.py`'s `write_timeout` was never armed at all. Correctness is unaffected (deadline loops are monotonic-clock based) but reads now give up sooner, so **a full `run/test` pass is owed once the board is repaired** (TASK-557). **Owner:** @Developer · **Deps:** none. |
| TASK-576 | P3 | **OPEN — filed 2026-09-02** | **A stale monitor log was mistaken for a dead board, twice in one session, and the misdiagnosis stopped two scheduled tasks.** The `by-id` symlink moved `ttyUSB0`→`ttyUSB1`; `pio device monitor` kept the old fd, so `run/monitor-read` returned a frozen boot banner ending at `[bootphase] 3 wifi`, and the monitor's own reopen attempts each asserted DTR and reset the board — which is what produced the "re-enumerating every ~1.5 s" reading. With the port free: **0 re-enumerations in 45 s**, and the board had in fact been up 9 h 26 m (`disc=0`, `rssi -49`). `run/monitor-read` **did** print its `stale/deleted tty` WARN (TASK-558) and both the agent and the orchestrator read past it. **Correction 2026-09-02: "re-resolve by VID:PID" was a wrong fix candidate — `resolve_port()` already returns the `by-id` path (ADR-062 R1) and `monitor-start` already passes it.** The stale thing is never the *name*, it is the **open fd**: a re-enumeration destroys the tty, and an fd opened before it does not follow, while the `by-id` path is recreated and would open fine. `run/lib.sh`'s ADR-062 comment over-claims here ("the path handed out at script start stays valid for the device's entire session … nothing downstream needs to re-resolve anything") — true of the path, false of a long-lived fd, which is why the monitor is the only exposed consumer (everything else reopens per operation). **Reopen-on-stale is DEAD — measured 2026-09-02 and it does not work.** A reopen asserts DTR again, so it resets the board again, which drops again at t=1.47 s: probe result `open-1` boot banner → hangup 1.47 s → `reopen-2` **boot banner again** → hangup 1.47 s. Every open resets, every reset drops, so the harness can never hold a session while the drop persists — and that loop is almost certainly what the "re-enumerating every ~1.5 s" observation actually was (`pio device monitor` reopening). No fd-layer or naming-layer fix exists; the drop itself has to stop. Two candidate paths, in cost order: **(a) physical** — different cable / powered hub / the other USB socket, the cheapest null test and TASK-557's own named experiment; **(b) firmware inrush mitigation** at the exact moment measured — back off TFT backlight and/or set a lower `WiFi.setTxPower()` immediately before `WiFi.begin()`, since the drop is timed to `[bootphase] 3 wifi`. Flashing still works (`run/flash*` succeeded repeatedly today), so (b) is testable without solving (a) first. Per TASK-557's measurement the reopen must distinguish two cases, and `[bootreason]` (TASK-572) + the generation counter (TASK-564) are the discriminator: a reset **we** caused reports `1 POWERON` and is benign bookkeeping, whereas `4 PANIC` / `5-6 WDT` / `9 BROWNOUT` — or any generation increment the harness did not ask for — is a finding that must reach the HEALTH/triage path and never be silently absorbed. Caveat to settle first: a real supply glitch may also report `POWERON`, so the rule needs `Dut._port_open_time` (recorded since TASK-557, still unread) as a second input. **Owner:** @Developer · **Deps:** none · Host-only. |
| TASK-577 | P3 | **OPEN — filed 2026-09-02, TASK-424 follow-up** | Revert `sdprobe`'s short-burst bench-fixture loop to a plain single-open write, and consider the same for `sd_put.py`'s 90 B chunking. Both are workarounds for TASK-424's write defect, which was root-caused and fixed on 2026-09-01 (PATCH-TLS-1) — TASK-424's own record asks for the revert once that landed, and calls the burst loop "a workaround, not a design". Keep `sd_put.py`'s per-call size verification regardless: that is TASK-548's dropped-ack guard, unrelated to TASK-424. **Not started because it cannot be verified**: the gate is a DUT write run, and the harness cannot hold a port session while TASK-557's inrush drop persists. Do not land it blind — the whole point is removing a guard. **Owner:** @Developer · **Deps:** TASK-557. |
| TASK-578 | P2 | **OPEN — filed 2026-09-02** | Decide what to do about the brownout ISR now that TASK-557 has measured the sag. `bodWatch` (debug env, `-DBOD_WATCH`) proves the ESP32 rides through the WiFi-init transient once ESP-IDF's brownout interrupt is cleared — 0 disconnects/120 s vs 77 — but that trades a clean reset for undefined behaviour on any deeper sag, and risks corruption if flash or SD is mid-write. **Do not promote to production by default.** Options: (a) fix the supply and leave the ISR alone; (b) keep the clear as a debug-only rig affordance; (c) promote with a bounded window (clear only across WiFi init, re-arm after). Wants an @Architect ruling and, ideally, the GPIO35/ADC1_CH7 divider so the sag depth is known rather than bracketed by an 8-level comparator. **Owner:** @Architect · **Deps:** TASK-557. |
| TASK-677 | **P2** | **DONE 2026-09-10** (`ddfa0d9`) — host-tested; first live window owed to P1 | `rigwatch`: host+DUT fault correlation (kernel USB events, harness stamps, timestamped tee, `rig:` artifact section, `run/rig-timeline`); `run/local.env`-gated. [PROP-011 §5 P0](../rnd/proposals/PROP-011-rig-ground-truth.md). |
| TASK-679 | P4 | **OPEN — candidate, filed 2026-09-10; premise weakened 2026-09-11** | Back off the `NO_AP_FOUND` reconnect retry. X-P1c found 0 trips in 121 provoked retries ([EXP-026](../rnd/reports/EXP-026-p1c-scanloop-trips.md)), so this is a robustness candidate, not a rig fix. **Owner:** @Developer · **Deps:** TASK-678. |
| TASK-678 | **P2** | **DONE 2026-09-11 (`c4291bf`..`4033090`)** — DUT-verified incl. F-6 descent+quiet step-up via synthetic faults | BOD ISR, scanLoop, UART probes, flag split, F-6. [EXP-026](../rnd/reports/EXP-026-p1c-scanloop-trips.md), [EXP-032](../rnd/reports/EXP-032-f6-descent-dut.md), [EXP-033](../rnd/reports/EXP-033-f6-staircase-echo.md). **Owner:** @Developer |
| TASK-680 | P2 | **DONE 2026-09-11 (`501e1aa`)** — DUT-verified, POWERON boot | Saved-network cascade race: candidate i-1's auto-reconnect retry blocked candidate i's `esp_wifi_connect()` (TASK-404's race, recurring between cascade candidates). Teardown before each candidate + RAM/FLASH storage bracket. Candidate 2 now reaches STA_GOT_IP at t=22166ms (was: 0 events/10s). |
| TASK-681 | P4 | **DONE 2026-09-11 (`39246e0`)** — DUT-verified, SW reboot | `[boot] git=` banner named a stale commit on incremental builds (`-DGIT_REV` isn't SCons-tracked). Now written to `gen_build/git_rev.h` (gitignored, not golden.sha256-gated) and `#include`d — a real dependency edge. DUT: banner `git=39246e0` == `git rev-parse --short HEAD`. |
| TASK-564 | **P2** | **DONE 2026-09-01 — host-tested; DUT verification PARTIAL** | `_wait_for_ready()` gates on `[bootphase] 6 ready` with seven per-phase deadlines, each derived from a firmware constant or measured boots (phase 4 = 90 s vs the cascade's 75.3 s bound); every readiness-path `SetupFailure` carries `last-phase=`/`gen=`; `_TeeSerial` counts `[bootphase] 0` into a global `<run-id>.<n>` tag. **Live on hardware only: boot-signature detection, the counter firing, run-id increment across sessions.** Reaching phase 6 and the phase-timeout path are host-test-only — the session read a **stale monitor log** and wrongly concluded the board was dead (see TASK-576); the board was healthy throughout. Detail: roadmap ▶ M-TESTARCH. |
| TASK-566 | P3 | **PARTIAL DONE 2026-09-02 — inert landing + order diff + baseline; ORDER SWITCH STILL HELD** | **Landed, inert:** `_order.py` (class order, diff, 0->1-edge scanner + adjudication), `_gate.py` (class-ordered dispatch, HEALTH gate phase, CORE blocking), the `NOT-RUN` bucket + opt-in exit 4 in `lib/results.py` (@VE §18.4 - shared default untouched), `DUT_HEALTH=gate|warn|skip`, `lib/baseline.py`, and EC-G8's inversion test (`test_class_order.py`, blocking in `run/check`). **EC-G7 is green:** all four exit-4 consumers taught it - `run/player-gate` (rc-4 leg, DUT_HEALTH refusal per @VE §18.2, 3 new `--selftest` cases), `run/test`, `run/test-targeted`, `run/test-sync`. **`--class-order` defaults OFF**; with it off behaviour is unchanged, and the inert arm of EC-G8 asserts that. **Order diff** (`runner.py --order-diff`): 210 ids, **all 210 move**, 6505 inverted pairs - `shell.py`'s 43 CORE ids jump from the registry tail to the head, everything else +43; 20 edge candidates adjudicated 2 EDGE / 3 ORDER-SENSITIVE / 2 VACUITY / 13 DISMISSED, with **`T178` newly identified as the highest-risk cell** (asserts chartLen==0 at rest; two Stock-fetching CORE ids move in front of it). **New finding: `run/player-gate` is order-blind for this switch** - both legs are 100% FEATURE, 0 moved, 0 inversions - so `run/test`'s default selection is the only valid A/B instrument. **Baseline:** 3 x `run/test`; **flake exposure 15/210 (7.1%) non-stationary across the first two runs alone**, each run crossing 4 boot generations. Artefact: [testarch-order-baseline-task566.md](../verification/regression_suite/testarch-order-baseline-task566.md). **STILL HELD - the switch itself.** @VE §18.6 (a) interleaved A/B at one commit and (b) flake candidates adjudicated before run 1 (now **five**: `T169`, `T_PR_05`, `T_WR_TLS_01` + newly-surfaced `T_PLR_07`, `T092`) are **unmet**; (c) the 0->1-edge enumeration is now **delivered**. TASK-557 unresolved. **Owner:** @Developer · **Deps:** met (565/570/571/573). |
| TASK-567 | P3 | **DEFERRED — after TASK-566 has a baseline; 74 sites split out to TASK-574** | Adjudicate the remaining **187** `skip()` sites (172 precondition / 4 n-a / 11 residual) into a closed vocabulary incl. `precondition-not-establishable-in-suite-order` (without it this regresses TASK-553). ~~Start with the 74 "other"~~ — **the 74 masked FAILs are now TASK-574, P2, scheduled at #3** (@PM ruling 2026-09-01: they are false greens today and have no dependency on 566's baseline, so deferring them behind 566 was mis-sequencing). What is left here genuinely does need the class ordering to adjudicate, and correctly stays deferred. [Design](../architecture/designs/M-TESTARCH-precedence-hierarchy.md) §4.3. **Owner:** @VE · **Deps:** TASK-566 baseline. |
| **TASK-573** | **P1** | **OPEN — filed 2026-09-01 by @PM from the adversarial review** | **Live gate defect, verified, independent of all M-TESTARCH work.** `run/player-gate:118` parses `\(PASS\|FAIL\|SKIP\|FLAKE\)`; `lib/results.py:127` writes `FLAKY-PASS`. `FLAKE` ≠ `FLAKY`, so the alternation fails, the whole line is dropped, the id scores **MISSING**, and the gate reports **REGRESS**. `T_PMT_04` is both a declared flake (`docs/verification/flaky.yaml:130`) and a baseline PASS cell (`player-gate-baseline.md`) — so a declared flake that passes on its own **mandated** retry makes the gate report a firmware regression that did not happen. ~10 lines. Fix the parser to accept `FLAKY-PASS` and score it against the baseline as its own bucket (it is **not** a PASS — `results.py`'s header says so explicitly); a baseline cell of PASS met by `FLAKY-PASS` is not a regression but must not be silently laundered into a pass either. **Add a unit test** over `_parse_runner_log` covering all five statuses — this defect is exactly the class `test_serial_classify.py` was written to prevent for TASK-556. **Owner:** @Developer · **Deps:** none · **Blocks:** TASK-566 (it produces 566's baseline). |
| **TASK-574** | **P2** | **OPEN — filed 2026-09-01, split out of TASK-567 at @PM ruling** | The **74 masked-FAIL `skip()` sites** — assertions that *failed* and were recorded as non-results (e.g. `"drill-in did not fire"`). These are **false greens today**. @VE filed this on their own authority during review and the filing is upheld: it has **no dependency on TASK-566's baseline**, so it does not belong behind the deferred TASK-567. Convert each to a real FAIL or a real, named precondition skip; a site that cannot be adjudicated without the class ordering stays in TASK-567 and is listed by id. Expect this to turn some currently-green cells red — that is the point, and the `player-gate-baseline.md` cells it moves must be re-baselined in the same change with the reason recorded. **Owner:** @VE · **Deps:** none. |
| TASK-569 | P4 | **OPEN — filed 2026-09-01** | `T_DH_04` heap/stack floors, **advisory, not a HEALTH member** until real floors exist: `app/mem_manifest.yaml` is a static overlay budget, no runtime heap or stack figure, and heap is untrustworthy before ~150 s settle. [Design](../architecture/designs/M-TESTARCH-precedence-hierarchy.md) §3.1. **Owner:** @VE. |

---

## Phase 3 — order and state hygiene, and the switch question (board)

**Entry:** Phase 1 complete; Phase 2 complete **and its stop criterion not triggered**; **TASK-557
closed or explicitly signed off by the human**. TASK-575's owed full `run/test` pass (§ Rig stability above) belongs to this entry too.
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
| TASK-635 | P2 | BLOCKED — **phase entry (TASK-557)**; its row predecessor TASK-608 is DONE | armed device state enumerable; boundary check attributes the leak to the arming test — [R14](../verification/M-HARNESS2-requirements.md) |
| TASK-592 | P2 | BLOCKED — **phase entry (TASK-557)**; its row predecessor TASK-602 is DONE | add the readiness-skip and unrestored-set scanners to the edge enumeration — [B-4](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-636 | P2 | BLOCKED — **phase entry (TASK-557)**; predecessor TASK-624 is DONE | per-family shuffle and the `ORDER-DEPENDENT` outcome — [R20/R21](../verification/M-HARNESS2-requirements.md). **Narrowed by TASK-644 / ADR-066 D2a:** emit it from the shuffle job as a comparison over the two runs' artifacts, keyed by id. **MUST NOT** add an 8th `Verdict` member |
| TASK-594 | P2 | BLOCKED — TASK-636 | two ids whose own predecessors destroy their precondition — [B-3](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-604 | P2 | BLOCKED — phase entry | six ids drive a different app than their record says — [E-5](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-605 | P2 | BLOCKED — **phase entry (TASK-557)**; its row predecessor TASK-634 is DONE | two ids reach their app only because of what ran before them — [E-11](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |

---

## Phase 4 — the observability contract (firmware; per-app, never a sweep)

**Entry: MET for the ADRs, 2026-09-04.** ADR A is **ADR-063** (`App` gains `dbgGet`/`dbgSet`;
identity and progress move to the shell) and ADR B is **ADR-064** (GRAM readback, **on demand only**;
a periodic or render-path signature is a violation of the decision, not a future option). Still
required: `.dram0.bss` headroom
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
| TASK-638 | P2 | **DONE 2026-09-09** (`983cd54`; DUT: `T_DH_05` 25/25, `T_CLK_SIG_01` ink 7463 / 63 colours; `.dram0.bss` +8 B, headroom 7 976 B) | `get sig` over panel readback with ink/entropy metrics, `set now [freeze]`, readback liveness in HEALTH — [R5](../verification/M-HARNESS2-requirements.md), [ADR-064](../architecture/decisions/ADR-064.md) |
| TASK-593 | P2 | BLOCKED — TASK-637 | per-app result and entry-state observables, one app per commit, capped per app — [R3](../verification/M-HARNESS2-requirements.md) |
| TASK-639 | P3 | OPEN — unblocked 2026-09-09 (TASK-638 DONE) | the clock family is rewritten, not migrated — ledger five claims, re-file as new ids — [Dev §8.2](../architecture/designs/M-HARNESS2-DEV-review.md) |

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
| TASK-607 | P3 | BLOCKED — **phase entry (Phase 3, hence TASK-557)**; its row predecessor TASK-608 is DONE | one wait helper, one app-entry helper, one timeout policy with users — [R22/R24](../verification/M-HARNESS2-requirements.md) |
| TASK-640 | P3 | BLOCKED — TASK-607 | classify all synchronisation sleeps, publish the three counts, then set the floor — [R23](../verification/M-HARNESS2-requirements.md) |
| TASK-606 | P3 | BLOCKED — phase entry | mirror-equality gate, pairs generated wherever the symbol is already generated — [R42](../verification/M-HARNESS2-requirements.md) |
| TASK-613 | P3 | BLOCKED — TASK-606 | a numeric bound in an assertion **you touch** cites its origin — delta-scoped only — [R44](../verification/M-HARNESS2-requirements.md) |
| TASK-599 | P2 | BLOCKED — **phase entry (Phase 3, hence TASK-557)**; its row predecessor TASK-609 is DONE | one session layer; migrate the four bypassing harnesses — [R47](../verification/M-HARNESS2-requirements.md) |
| TASK-641 | P3 | **PARTIAL 2026-09-08** (`9f70a6e`, design + spike); execution BLOCKED on **phase entry (TASK-557)**; **RULED accepted 2026-09-09** | read-key set (transcript-first, static `APPROX` fallback); author declares key ROLE and oracle SHAPE — [R1](../verification/M-HARNESS2-requirements.md), [taxonomy](../architecture/designs/M-HARNESS2-falsifier-taxonomy.md) |
| TASK-642 | P3 | BLOCKED — TASK-641; **design filed 2026-09-08** | falsifier: replay half derived from declared shapes, physical half with an enforced expiry — [R9](../verification/M-HARNESS2-requirements.md), [taxonomy §7](../architecture/designs/M-HARNESS2-falsifier-taxonomy.md) |
| TASK-643 | P3 | BLOCKED — TASK-642; **design filed 2026-09-08** | driver runs the expected-verdict matrix (baseline + one arm per key); POLL shape = freeze + time dilation, **measured on T_MA_03**; a miss is inconclusive and names its constraint — [R10](../verification/M-HARNESS2-requirements.md), [taxonomy §4–5](../architecture/designs/M-HARNESS2-falsifier-taxonomy.md) |
| TASK-601 | P2 | BLOCKED — TASK-599 | the TLS preflight runs from every entry point, not one — [A-5](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-610 | P3 | OPEN — unblocked | collapse 26 ids to about 11 behaviours — [B-16](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-612 | P3 | BLOCKED — phase entry | scope resolution for the 55 % of the tree it cannot reach — [B-9](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-614 | P3 | OPEN — unblocked; **scope grew** | registry and tooling honesty — [B-13](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |
| TASK-615 | P3 | OPEN — unblocked; **scope grew** | small correctness debts with named fixes — [H-17](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |
| TASK-671 | P2 | **DONE 2026-09-09** (`c444071`, `0399324`; 193 transcripts, 9-row ledger; `run/check` 63.1 s warm, the sweep is 22 s of it) | R34 at runtime: `check_can_go_red.py` executes each recorded body against its poisoned transcript; reds graded assertion/contract/accident/policy — [design](../architecture/designs/M-HARNESS2-runtime-gates.md) |
| TASK-672 | P3 | OPEN — needs TASK-671's first recording; shares TASK-641's read-key instrument | R18 runtime arm: PASS under `DROP@k` on a field the body read = an oracle satisfied by a default — [design §4](../architecture/designs/M-HARNESS2-runtime-gates.md) |
| TASK-673 | P3 | OPEN — needs TASK-671's first recording | R17 runtime arm: on every poisoned FAIL/UNMET path, an unacked or missing set-back is a leak on that path (`C-15`'s shape, host-side) — [design §4](../architecture/designs/M-HARNESS2-runtime-gates.md) |
| TASK-674 | P3 | OPEN — needs TASK-671's first recording | R36 runtime arm: the healthy transcript's command set is the exact gating key set; check it, not a closure guess — [design §4](../architecture/designs/M-HARNESS2-runtime-gates.md) |
| TASK-676 | P3 | OPEN — filed 2026-09-09 from the first recording | six bodies whose only red is a crash arm (`T077`, `T_CX_05`, `T_CX_07`, `T_WR_HEAP_01/02`, `T_WX_05`): they break on a bad reply and never assert on it — read typed, `fail()` on the subject — [ledger](../verification/can_go_red_ledger.md) |

---

## Totals

**Recounted mechanically 2026-09-08.** The previous table read 61 rows and predated TASK-644/645/
646/647 and TASK-661; every count below is derived from the tables above, not carried forward.

| phase | rows | closed | live | days | state |
|---|---|---|---|---|---|
| 0 — decisions | 6 | 6 | 0 | ~1 | **DISCHARGED 2026-09-04** |
| 1 — host-only foundation | 26 | 26 | 0 | ~28.5 | **COMPLETE 2026-09-06** — every exit criterion met; `run/check` 43.5 s warm of 90, `run/check-docs` 1.1 s of 15 |
| 2 — the 80-minute session | 12 | 7 | 5 | ~6 | **session executed 2026-09-07**; stop criterion did not fire. Live: 582, 588, 597, 595, 589 |
| 3 — order and state hygiene | 6 | 0 | 6 | ~7.5 | blocked at phase level on **TASK-557**; shrunk by H-1's refutation |
| 4 — observability contract | 4 | 1 | 3 | ~10 | ADR-063/064 taken; **638 DONE 2026-09-09**; 637 and 639 open |
| rig stability + M-TESTARCH remainder (moved in 2026-09-10) | 16 | 2 | 14 | — | 557 gates Phase 3; 564/566/567 are the order-switch chain; 573/574 gate defects; 677/678 PROP-011; **680/681 DONE 2026-09-11** |
| 5 — ratchets | 17 | 1 | 16 | ~30 | blocked on Phase 3. **610, 614, 615, 672–674 are unblocked** — they do not inherit the phase entry; 671 landed |
| **total** | **88** | **44** | **44** | **~83** | Phases 0–1 done; only Phase 1 was ever *committed* |

**The three phases still ahead are not equally blocked.** Phase 2's five live rows and Phase 4's
TASK-637 and Phase 5's TASK-610/614/615 need **nothing but hands**. Everything else waits on
TASK-557 (Phase 3, and Phase 5 through it). TASK-589 — Phase 4's render half — was repaired and
hardware-verified on 2026-09-07 and no longer holds anything back.

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
