# M-HARNESS2 + WP-Z — test-harness remediation programme

> Owner: **Project Manager**
> Status **2026-09-07**: **Phases 0 and 1 COMPLETE** (32 rows, all closed); **Phase 2's session is
> executed** and 5 rows remain; Phases 3–5 scheduled behind named entry criteria. Only Phase 1 was
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
escalations and the oracle-sweep rulings) and **TASK-661** here. **Next free id: TASK-669**
(662–668 filed 2026-09-07 on [tasks.md](tasks.md) from the Phase 2 hardware sessions).

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
any more; 588/597 wait on nothing but hands, 589 is Phase 4's prerequisite.

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
| TASK-607 | P3 | BLOCKED — **phase entry (Phase 3, hence TASK-557)**; its row predecessor TASK-608 is DONE | one wait helper, one app-entry helper, one timeout policy with users — [R22/R24](../verification/M-HARNESS2-requirements.md) |
| TASK-640 | P3 | BLOCKED — TASK-607 | classify all synchronisation sleeps, publish the three counts, then set the floor — [R23](../verification/M-HARNESS2-requirements.md) |
| TASK-606 | P3 | BLOCKED — phase entry | mirror-equality gate, pairs generated wherever the symbol is already generated — [R42](../verification/M-HARNESS2-requirements.md) |
| TASK-613 | P3 | BLOCKED — TASK-606 | a numeric bound in an assertion **you touch** cites its origin — delta-scoped only — [R44](../verification/M-HARNESS2-requirements.md) |
| TASK-599 | P2 | BLOCKED — **phase entry (Phase 3, hence TASK-557)**; its row predecessor TASK-609 is DONE | one session layer; migrate the four bypassing harnesses — [R47](../verification/M-HARNESS2-requirements.md) |
| TASK-641 | P3 | BLOCKED — **phase entry (Phase 3, hence TASK-557)**; its row predecessor TASK-628 is DONE | generate the read-key set; the author declares a claim class from a closed enum — [R1](../verification/M-HARNESS2-requirements.md) |
| TASK-642 | P3 | BLOCKED — TASK-641 | two-field falsifier: executable replay, and physical with an enforced expiry — [R9](../verification/M-HARNESS2-requirements.md) |
| TASK-643 | P3 | BLOCKED — TASK-642 | mutation driver with the control arm; a transcript miss is inconclusive, never a confirmation — [R10](../verification/M-HARNESS2-requirements.md) |
| TASK-601 | P2 | BLOCKED — TASK-599 | the TLS preflight runs from every entry point, not one — [A-5](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-610 | P3 | OPEN — unblocked | collapse 26 ids to about 11 behaviours — [B-16](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-612 | P3 | BLOCKED — phase entry | scope resolution for the 55 % of the tree it cannot reach — [B-9](../verification/reviews/M-TESTQUAL-Z-findings-review.md) |
| TASK-614 | P3 | OPEN — unblocked; **scope grew** | registry and tooling honesty — [B-13](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |
| TASK-615 | P3 | OPEN — unblocked; **scope grew** | small correctness debts with named fixes — [H-17](../verification/reviews/M-TESTQUAL-Z-findings-review.md) … |

---

## Totals

**Recounted mechanically 2026-09-07.** The previous table read 61 rows and predated TASK-644/645/
646/647 and TASK-661; every count below is derived from the tables above, not carried forward.

| phase | rows | closed | live | days | state |
|---|---|---|---|---|---|
| 0 — decisions | 6 | 6 | 0 | ~1 | **DISCHARGED 2026-09-04** |
| 1 — host-only foundation | 26 | 26 | 0 | ~28.5 | **COMPLETE 2026-09-06** — every exit criterion met; `run/check` 43.5 s warm of 90, `run/check-docs` 1.1 s of 15 |
| 2 — the 80-minute session | 12 | 7 | 5 | ~6 | **session executed 2026-09-07**; stop criterion did not fire. Live: 582, 588, 597, 595, 589 |
| 3 — order and state hygiene | 6 | 0 | 6 | ~7.5 | blocked at phase level on **TASK-557**; shrunk by H-1's refutation |
| 4 — observability contract | 4 | 0 | 4 | ~10 | ADR-063/064 taken; **TASK-637 is the only unblocked row**, 638 gated on 589 |
| 5 — ratchets | 13 | 0 | 13 | ~28.5 | blocked on Phase 3. **610, 614, 615 are unblocked** — they do not inherit the phase entry |
| **total** | **67** | **39** | **28** | **~81** | Phases 0–1 done; only Phase 1 was ever *committed* |

**The three phases still ahead are not equally blocked.** Phase 2's five live rows and Phase 4's
TASK-637 and Phase 5's TASK-610/614/615 need **nothing but hands**. Everything else waits on
TASK-557 (Phase 3, and Phase 5 through it) or on TASK-589 (Phase 4's render half).

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
