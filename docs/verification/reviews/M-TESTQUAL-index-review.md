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
| B | [taxonomy, grouping & order](M-TESTQUAL-B-taxonomy-review.md) | Q7–Q8: class/scope assignment, registry order, `_gate`/`_order`, duplicate & overlapping tests | in progress |
| C | [RIG / HEALTH / CORE audit](M-TESTQUAL-C-audit-core-review.md) | the 49 gating ids — audited first, because everything above them inherits their trust | pending |
| D | [shell family audit](M-TESTQUAL-D-audit-shell-review.md) | `shell.py` (3 528 lines, scopes shell/taskbar/boot/spotify-chrome/Spotify/Settings/Life/Matrix) | pending |
| E | [player family audit](M-TESTQUAL-E-audit-player-review.md) | `player.py` — LocalPlayer, 29 ids | pending |
| F | [webradio family audit](M-TESTQUAL-F-audit-webradio-review.md) | `webradio.py` — 31 ids | pending |
| G | [stock family audit](M-TESTQUAL-G-audit-stock-review.md) | `stock.py` — Stock/Crypto/Weather, 40 ids | pending |
| H | [clock / teletext / planeradar audit](M-TESTQUAL-H-audit-data-apps-review.md) | the three smaller data-app families, 26 ids | pending |
| Z | [findings & proposed tasks](M-TESTQUAL-Z-findings-review.md) | consolidated, deduplicated, severity-ranked; proposed TASK rows for @PM | pending |

---

## 4. Rollup — filled as packages land

| Verdict | Count | Notes |
|---|---|---|
| _(pending)_ | — | — |

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
