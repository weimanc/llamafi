# M-TESTQUAL — test harness, framework and per-test quality review

> Owner: **Verification Engineer**
> Status: in progress
> Started: 2026-09-02
> Scope: the serialdbg-001 DUT suite (`app/tools/suite/serialdbg/`, 213 registered ids),
> its shared layer (`app/tools/lib/`), the `run/` entry points, and the host gates
> (`app/tools/gate/`).
> Companion to: [M-TESTARCH test architecture](../../architecture/designs/M-TESTARCH-test-architecture.md),
> [M-TESTARCH precedence hierarchy](../../architecture/designs/M-TESTARCH-precedence-hierarchy.md),
> [M-TOOLING](../../architecture/designs/M-TOOLING-host-tool-architecture.md).

M-TESTARCH said what the architecture **should** be. This review says what the suite
**is**, measured against it, plus the question M-TESTARCH never asked: **is each
individual test actually testing anything?**

Every file in this directory ends `-review.md`, which is a `check_docs.py` exemption
suffix — deliberate: these documents quote hundreds of test ids in table rows and must
not be read by C6 as a second, competing test registry. `test_plan.md` remains the only
place a test id is *declared*.

---

## 1. The questions this review answers

Posed by the human operator, 2026-09-02:

| # | Question | Answered in |
|---|---|---|
| Q1 | Is there one common test harness for all tests? | WP-A |
| Q2 | Is there a consistent DUT entry point? | WP-A |
| Q3 | Is result reporting consistent? | WP-A |
| Q4 | Duplicate code? | WP-A |
| Q5 | Magic variables/numbers? | WP-A |
| Q6 | Double bookkeeping — are firmware constants/defines re-declared in the suite instead of reused? | WP-A |
| Q7 | Do the test grouping and test order make sense? | WP-B |
| Q8 | Duplicate tests? | WP-B |
| Q9 | **What is the actual quality of each test? Is any test cheating — printing PASS without proving anything?** | WP-C…WP-H |

Q9 is the emphasis. It is audited per test-class hierarchy (RIG → HEALTH → CORE →
FEATURE), against the rubric in
[M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md). No verdict in this review is
allowed to be an impression: every row cites `file:line`.

---

## 2. Method and constraints

* **Static audit only.** No DUT run, no flash, no `run/test*`. The board is currently
  pinned to the `-DBOD_WATCH` debug build for TASK-557 and must not be disturbed; and a
  suite cannot be trusted to report on its own soundness anyway (M-TESTARCH §7, the
  verification paradox). Where a finding needs hardware to confirm, it is filed as
  **NEEDS-DUT** and left unconfirmed rather than asserted.
* **Evidence or it did not happen.** Every claim carries `path:line`. Counts are
  re-measured with a quoted command, never carried over from another document.
* **The rubric is fixed before the audit starts** so families are graded the same way.
* Findings do not edit the suite. This review produces documents and proposed tasks;
  fixes are separate, PM-scheduled work.

---

## 3. Work packages

One document per package — no monolith. Each is self-contained and links back here.

| WP | Document | Covers | Status |
|----|----------|--------|--------|
| A | [harness & framework](M-TESTQUAL-A-harness-review.md) | Q1–Q6: entry points, `lib/`, result layer, duplication, magic values, firmware-constant double bookkeeping | **done** — 19 findings (P1×5, P2×9, P3×5) |
| B | [taxonomy, grouping & order](M-TESTQUAL-B-taxonomy-review.md) | Q7–Q8: class/scope assignment, registry order, `_gate`/`_order`, duplicate & overlapping tests | **done** — 18 findings (P1×4, P2×9, P3×5) |
| C | [RIG / HEALTH / CORE audit](M-TESTQUAL-C-audit-core-review.md) | the 49 gating ids — audited first, because everything above them inherits their trust | **done** — 20 findings (P1×6, P2×9, P3×5) |
| D | [shell family audit](M-TESTQUAL-D-audit-shell-review.md) | `shell.py`'s 50 FEATURE ids (27 Spotify, 6 Settings, 5 Weather, 5 Crypto, 4 Life, 3 Matrix); the other 46 shell ids are WP-C's | **done** — 17 findings (P1×5, P2×8, P3×4) |
| E | [player family audit](M-TESTQUAL-E-audit-player-review.md) | `player.py` — LocalPlayer, **31** ids (26 `T_PLR_*` + 5 `T_PMT_*`; the "29" this row carried predated `T_PMT_04`) | **done** — 16 findings (P1×2, P2×9, P3×5) |
| F | [webradio family audit](M-TESTQUAL-F-audit-webradio-review.md) | `webradio.py` — 31 ids | pending |
| G | [stock family audit](M-TESTQUAL-G-audit-stock-review.md) | `stock.py` — Stock/Crypto/Weather, 40 ids | pending |
| H | [clock / teletext / planeradar audit](M-TESTQUAL-H-audit-data-apps-review.md) | the three smaller data-app families, 26 ids | pending |
| Z | [findings & proposed tasks](M-TESTQUAL-Z-findings-review.md) | consolidated, deduplicated, severity-ranked; proposed TASK rows for @PM | pending |

---

## 4. Rollup — filled as packages land

| Verdict | Count | Notes |
|---|---|---|
| SOUND | 81 | WP-C 29 (49 gating ids) + WP-D 28 (50 shell FEATURE ids) + WP-E 24 (31 player ids). |
| WEAK | 31 | WP-C 17 + WP-D 10 + WP-E 4 (`T_PLR_07`, `T_PLR_13`, `T_PLR_18`, `T_PMT_00`). |
| HOLLOW | 8 | WP-C: `T093`. WP-D: `T078`, and the four "BUG-1 guard" ids `T_MA_02`/`T_GOL_02`/`T_WX_02`/`T_CX_02`, which assert a fixed string `cmdTap` prints on a branch that calls no app handler. WP-E: `T_PLR_02` (claims reboot persistence, reads back its own write, defers the reboot to a human) and `T_PLR_03` (its "no leaked taskbar slot" assertion is arithmetically unrepresentable — `appIdx = offset % TASKBAR_APP_COUNT` cannot yield WebRadio or LocalPlayer). |
| BROKEN | 10 | WP-C: `T-BUSY-05` (inverted guard — passes on the regression), `T-UART-01` (its detector is swallowed by `read_json`). WP-D: `T136` (body is one unconditional `skip()`; archived plan row still says PASS), the four residue ids `T_MA_03`/`T_GOL_03`/`T_WX_03`/`T_CX_03` (no `fail()` anywhere in the body — the guarded regression exits as a SKIP), and `T_WX_04`/`T_CX_04` (precondition destroyed by their own predecessors). WP-E: `T_PLR_25` (no variant guard, so it is a deterministic 60 s false red on the only env that dispatches it; `run/player-gate` stays green by omitting the id from leg A). |
| _(WP-F…H pending)_ | — | 97 ids not yet audited (WP-F 31, WP-G 40, WP-H 26, per §3). |

---

## 5. Progress ledger (resume point)

This section is the handover state. A session picking this work up cold reads §3's
status column and this ledger, and nothing else.

| When | Event |
|---|---|
| 2026-09-02 | Review chartered; index + rubric written; WP-A dispatched. |
| 2026-09-02 | WP-A landed and QC'd (three claims re-verified independently by the orchestrator: D6 `PR_FETCH_TYPE`, `lib/dut.TIMEOUT`'s zero users, the closed hardcoded-port finding). Headline: one real harness plus 13 standalone DUT harnesses; nine firmware-fact mirrors registered; `gen_get_keys.py` enumerates 43 of 71+ `get` keys, so `run/task488`'s "every key resolves" covers ~60 %. |
| 2026-09-02 | **Incident:** the WP-A agent bulk-imported `app/tools/*.py` to find broken imports; six modules open the serial port and run their suite at import time, which reset the board and injected taps. Firmware untouched (still the `-DBOD_WATCH` debug build; log confirms `build=Sep 2 2026-22:42`, uptime 00:43 at 23:39). Filed as WP-A finding A-12; the rubric §5 now bans importing anything under `app/tools/`. Any TASK-557 window open this evening is contaminated. |
| 2026-09-02 | WP-B dispatched. |
| 2026-09-03 | WP-B landed and QC'd (declared-vs-seeded counts re-measured independently: 6 `cls`, 57 `scope`, 3 `effect` declared of 216 records — exact match). Headline: the taxonomy is 97 % inference, including all 43 CORE ids the order switch would let block the other 167; six order-dependence clusters, three invisible to the TASK-566 edge enumeration; 26 ids collapse to ~11 distinct assertions. Rubric amendment A2 records the C6 table-binding trap WP-B hit. |
| 2026-09-03 | WP-C dispatched (RIG/HEALTH/CORE, 49 ids). |
| 2026-09-03 | WP-C died at the first tool call — the orchestrating session hit its 5-hour usage limit (~03:00, reset 03:40). No document produced, nothing partial to salvage. Re-dispatched unchanged at 04:07. |
| 2026-09-03 | WP-C landed. Headline: 29 SOUND / 17 WEAK / 1 HOLLOW / 2 BROKEN. Two BROKEN CORE ids — `T-BUSY-05`'s guard is inverted so it passes exactly when the amber fails to clear, and `T-UART-01` cannot observe JSON garbling at all because `Dut.read_json` discards a malformed line and returns the next one. Three structural gate findings: the RIG class has no executable coverage in any `run/` entry point (nothing passes `--interactive`); 31 of 43 CORE ids fail their preconditions as SKIPs, which `_gate.py:128` does not treat as blocking, so the CORE block almost never fires; and a SKIPped HEALTH check is announced as `[health] PASS`. `./run/check-docs` re-run with and without the new document: C6 identical (224 bound, 41 orphan, 0 unexcepted) — rubric A2 held. |
| 2026-09-03 | WP-D dispatched (`shell.py`'s 50 FEATURE ids). |
| 2026-09-03 | WP-D landed. Headline: 28 SOUND / 10 WEAK / 5 HOLLOW / 7 BROKEN — the worst per-test result so far, and the failure mode has inverted. Where the gating classes' problem was *a failure that does not block*, the FEATURE class's problem is *a test that does not run*: S7 is the dominant smell (23 of 50 rows) and 14 ids produce no verdict at all in a normal run. Two four-id clusters carry most of it — the small apps' "BUG-1 guard" rows assert a fixed literal `cmdTap` prints on a branch that calls no app handler (`cmdTouch.cpp:141-144`), and their "canvas residue" rows contain **no `fail()` at all**, so the regression they guard exits as a SKIP. Also: three ids grep for log markers (`ACT_SEEK`, `seek commit`) the firmware has never emitted, `posbarDragMs` turns out to be the live drag-tracking value rather than the committed seek, and a new state-leakage cluster (`songDuration`, C7) was added to WP-B §5.2. On TASK-243: the Spotify scope never asserted playback in the first place — every oracle in all 27 bodies is a hit-test region, a gesture-state value or a trace count — but 12 of the 27 are now permanent SKIPs for want of a non-empty queue, and five plan entries still promise enqueue markers their bodies never implemented. `./run/check-docs` run once before handover: C6 identical again (224 bound, 41 orphan, 0 unexcepted), 6 passed / 0 failed — A2 held a second time.
| 2026-09-03 | WP-E dispatched (`player.py`, the LocalPlayer family). |
| 2026-09-03 | WP-E landed. Corpus re-measured at **31 ids, not the 29 this index carried** (the row predated `T_PMT_04`); §3 corrected. Headline: 24 SOUND / 4 WEAK / 2 HOLLOW / 1 BROKEN — the best-graded family so far (77 % SOUND vs WP-C's 59 % and WP-D's 56 %), and the cause is upstream of the tests: ADR-059 D12 designed the play-order engine's observables first (`get plOrder`, `get plCursor`, `advance`'s `moved`/`row`/`reshuffled`), and the seven ids built on them assert exact permutations and exact triples rather than proxies. It is also the first family with **zero dead markers** — every log string and `get` key resolves in `app/src/`. Against that: only **3 of 31 ids have any audio-side oracle at all** although this is the one family with a physical one, and the family's real-playback coverage lives outside the registry. `T_PLR_25` is BROKEN — no variant guard, so it is a deterministic 60 s false red in every `run/test`, and the gate is green only because leg A's list omits it. Two HOLLOW rows assert unfalsifiable things (`T_PLR_02` reads back its own write for a reboot claim it defers to a human; `T_PLR_03`'s leak assertion is excluded by `appIdx = offset % TASKBAR_APP_COUNT`). New failure mode for the running series: WP-C's was *a failure that does not block*, WP-D's *a test that does not run*, WP-E's is **a test that leaves the board changed** — S14 on 17 of 31 rows, two of the leaked quantities persisted and one a 16 KB arena allocation, which is how TASK-553 became a false regression (new cluster `C8` for WP-B §5.2). Also: all three flaky.yaml declarations/call sites in this family are mismatched in both directions; four negative assertions sit on a suppressible `LOG_D` channel; and `run/player-gate`'s exit-4 HEALTH machinery is unreachable because the gate never passes `--class-order`. The package additionally answers WP-A **A-15** (§7, both duplicate bodies read and compared — the standalone body wins both) and audits the gate's `sed` parser behind **A-7** (§8). `./run/check-docs` run once before handover: C6 identical again (224 bound, 41 orphan, 0 unexcepted), 6 passed / 0 failed — A2 held a third time. |
