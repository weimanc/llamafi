# Undeclared gating classes — the R35 ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_test_meta.py` (finding **G1**) ·
> Opened **2026-09-04** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R35, TASK-591

## What this file is

[R35](M-HARNESS2-requirements.md) requires every id whose class can block a run — RIG, HEALTH or
CORE — to carry an **explicit class declaration with a written reason**, never a default. The
reason is not a restatement of the class name. It is a sentence saying **what makes this test's
failure mean the rest of the run cannot be trusted**. It lives in the `@meta(cls=…, cls_reason=…)`
declaration on the body, or in the family's `META_OVERRIDES` — next to the code it describes, so it
cannot drift from it (LL-114: parse, don't mirror).

TASK-591 read all 49 gating bodies with that question in front of it and **could write the sentence
for 25**: 3 RIG, 3 HEALTH, and 19 of the 43 CORE ids. Those 25 are declared.

The **24 rows below are the ones where the sentence could not honestly be written.** For each, the
finding is not "nobody has got round to it" — it is that the id looks like a FEATURE test that was
seeded CORE by `_meta.seed_cls()` because its scope happened to be `shell`, `taskbar`, `boot` or
`spotify-chrome`. Each row carries the proposed demotion and its evidence.

**A row does not make the id safe.** While it sits here the id still resolves to CORE and, once
TASK-566's `--class-order` switch flips, still blocks the 167 FEATURE ids beneath it. The row makes
the fact visible and dated; it does not fix it. That is the direct reason
**[TASK-617](../project/tasks-harness2.md) must not flip the switch while this ledger is non-empty** —
24 ids would then carry a gate's authority on a class nobody affirmed.

## Why the demotions are proposed and not performed

A demotion changes what the suite blocks on. That is a change to the run's semantics, and the human
asked to see the list before it lands (ruling of 2026-09-03). So TASK-591 declares the 19 it can
defend, and files the other 24 here for a ruling. Each row resolves one of two ways, and the gate
reports either as **G2** the moment it does:

* the id takes `@meta(cls="FEATURE", cls_reason=…)` — the demotion this file proposes; or
* somebody writes a CORE reason this file could not, and the id takes `@meta(cls="CORE", …)`.

**The rules that make this a gate and not an amnesty:**

1. A row suppresses **one** finding, keyed on `(kind, id)`. No file, family or wildcard exemption
   exists, by design.
2. **A stale row is a BLOCKING failure.** When the id declares a class, G2 fails until the row is
   deleted. The list can only shrink.
3. Every row needs an owning `TASK-` id and an ISO `since` date. Missing or malformed either is a
   failure, not a skipped row.
4. **There is one exemptable kind**, `undeclared-gating-class`. G3 (a declared gating class whose
   reason is too short to be an argument) is at zero and is not exemptable — an exemption kind with
   no rows is an invitation to open one.

## The exemptable kind

| kind | the finding it suppresses |
|---|---|
| `undeclared-gating-class` | an id resolving to RIG, HEALTH or CORE with no `cls_reason` on its declaration — a class that can stop the run, applied by a default nobody affirmed |

## Ledger

Owner = the task that will resolve it. `since` = the date the row was opened.
Ordered by confidence in the proposed demotion, strongest first.

| id | kind | why it is not resolved today | owner | since |
|---|---|---|---|---|
| `T-UART-01` | undeclared-gating-class | **DEMOTE.** WP-C `C-2`: it is BROKEN — its subject is JSON garbling under Core-0 load, its only detector is a `JSONDecodeError`, and `Dut.read_json` (`app/tools/lib/dut.py:1086`) swallows that and returns the next well-formed line. `errors` can fill only on a total timeout, never on the interleave it exists to catch. A CORE id that structurally cannot fail on its subject carries a gate's authority with the gate switched off. Also drives StockApp exclusively (WP-B `B-1`), so scope should be `Stock`. | TASK-591 | 2026-09-04 |
| `T-BUSY-05` | undeclared-gating-class | **DEMOTE.** WP-C `C-1`: the guard at `app/tools/suite/serialdbg/shell.py:1923` is inverted — `if any(b is not True …)` is False exactly when all three post-switch reads are `True`, i.e. when the amber did NOT clear, so control falls through to `pass_()`. It passes precisely when the regression is present. Four `skip()` exits above it mean it usually never reaches the assertion at all. Re-promotion is arguable once C-1 is fixed and it has been run; not before. Stock-only, scope should be `Stock`. | TASK-591 | 2026-09-04 |
| `T091` | undeclared-gating-class | **DEMOTE.** Two independent grounds. (1) No premise: nothing outside T092 and T-BGPOLL-02 — both themselves proposed for demotion — depends on `reconnect` clearing `consecutiveFailures`; no FEATURE id does. (2) WP-C `C-6`: every exit routes through `flake()` and T091 IS declared in `flaky.yaml`, so its worst case is `FLAKY-PASS`, which `app/tools/suite/serialdbg/_gate.py:128` does not treat as a blocker. It is a CORE id that can never block. This row and the [R37 flake ledger](flake_class_exceptions.md) row for `T091` retire together. | TASK-591 | 2026-09-04 |
| `T-BGPOLL-03` | undeclared-gating-class | **DEMOTE.** WP-C `C-11`: the only thing it asserts is that a flag the test itself wrote is still 0 — which would hold if the tap were never sent. `_wait_shell_not_busy`'s return is discarded (`app/tools/suite/serialdbg/shell.py:3402`) and the tap's own `hit`/`action` reply is never inspected, so the "force-poll completed" half of the claim has no oracle at all. Nothing downstream rests on it either way. | TASK-591 | 2026-09-04 |
| `T-CDWN-03` | undeclared-gating-class | **DEMOTE.** WP-C `C-11`: the precondition its claim rests on is never established — nothing between the row tap (`app/tools/suite/serialdbg/shell.py:2121`) and the taskbar tap (`app/tools/suite/serialdbg/shell.py:2124`) checks `shellBusy` was true when the taskbar tap arrived, and `set triggerFetch 1` makes it likely, not certain. On a warm or failed fetch it passes without exercising the bypass. BP-074: an assertion whose precondition never occurred is inconclusive, not a pass — and an inconclusive verdict cannot gate. Stock-only, scope should be `Stock`. | TASK-591 | 2026-09-04 |
| `T133` | undeclared-gating-class | **DEMOTE, and split.** WP-B `B-2` / WP-C `C-14`: part A is a host-side source `grep` for `CurrentlyPlaying current = {}` and belongs in `app/tools/gate/`; a checkout without `lib/SpotifyArduino/` FAILs it before the DUT is touched, and under the switch that host file-existence failure NOT-RUNs all 167 FEATURE ids. Part B is a 90 s idle soak that is satisfied by any board with or without the guard — the single most expensive cell in the CORE block, proving nothing. Neither half is a shared premise. Also the R36/TASK-626 reference case for "the host's file layout". | TASK-591 | 2026-09-04 |
| `T-BUSY-01` | undeclared-gating-class | **DEMOTE.** WP-B `B-1`'s headline id. Its pass/fail is a network outcome: `_poll_chart_len_positive` is 45 s of live HTTPS to Yahoo and a timeout is a hard `fail()`, not a skip — under the switch it runs at index 14 and NOT-RUNs 167 ids on a network outage. Its own assertion is weak besides: `app/tools/suite/serialdbg/shell.py:1744-1749` downgrades the "busy went true" half to a printed note, leaving `busy == False` at rest, which cannot distinguish auto-clear from never-rose. The genuine `shellBusy` premise is already declared CORE on T-BUSY-02. Stock-only, scope should be `Stock`. | TASK-591 | 2026-09-04 |
| `T-BUSY-01b` | undeclared-gating-class | **DEMOTE.** Same family and same network dependency (two 45 s live chart fetches). Its negative outcome is a `skip()` (`app/tools/suite/serialdbg/shell.py:1803`, "warm fetch too fast"), so a genuine regression where the tap raises nothing is indistinguishable from a fast fetch and reports green — the raise half it exists to supply is unfalsifiable in practice. Three `skip()` exits. Stock-only, scope should be `Stock`. | TASK-591 | 2026-09-04 |
| `T-ERR-07` | undeclared-gating-class | **DEMOTE.** Single-app feature test: StockApp's `hasError() = _s.fetchFailed` latch, driven through `set fetchFailed`. Nothing else in the suite depends on the Stock error latch. Seeded CORE only because its module is `shell.py` and its scope fell to the catch-all. Stock-only, scope should be `Stock` (WP-B `B-1`'s seventh id). | TASK-591 | 2026-09-04 |
| `T-ERR-01` | undeclared-gating-class | **DEMOTE.** An ADR-046 feature test of the `activeError` state machine behind the red taskbar bar. WP-C rates the body SOUND and it is the good version of the injection pattern (write key `lastHttp`, read key `activeError`) — but a sound feature test is still a feature test. No other id's verdict depends on the error latch. | TASK-591 | 2026-09-04 |
| `T-ERR-02` | undeclared-gating-class | **DEMOTE.** Same family: the error is owned by the app, hidden while another app is active, restored on return. A per-app ownership rule for one indicator; nothing downstream rests on it. Also carries hardcoded slot numbers (`switchApp 1`/`switchApp 0`) with no `ok` check, WP-C `C-16`. | TASK-591 | 2026-09-04 |
| `T-ERR-04` | undeclared-gating-class | **DEMOTE, and note the order hazard.** A feature test of the boot-amber `connecting` latch. WP-B `B-7`: it writes `lastOkMs`, `backoff` and `lastHttp` and restores NONE of them — under the class-order switch it moves from index ~206 to ~39, in front of 170 ids, which is an argument against running it early, i.e. against CORE, not for it. | TASK-591 | 2026-09-04 |
| `T-ERR-05` | undeclared-gating-class | **DEMOTE.** A precise regression guard for one past defect (a touch must not clear a 403, because `authError` keys on the last HTTP status, not on `s_consecutiveFailures`). Valuable, and entirely local to the Spotify error indicator. Leaves `backoff 0` deliberately (WP-B `B-7`). | TASK-591 | 2026-09-04 |
| `T-ERR-06` | undeclared-gating-class | **DEMOTE.** Asserts offline apps never report `connecting`. WP-C: a weak negative — `connecting` defaults false, so it asserts a default was not overwritten — with hardcoded `conn(1)`/`conn(4)` and no `ok` check on the switch, so a failed switch reads the previous app's state (`C-16`). Not a premise for anything. | TASK-591 | 2026-09-04 |
| `T-BGPOLL-02` | undeclared-gating-class | **DEMOTE.** `reconnect` resetting `bgPoll` to 1 is a recovery invariant of the Spotify poll, not a premise of the run: nothing downstream needs it. WP-B `B-6` cuts the other way too — with no `finally`, a failure here leaves `bgPoll 0` for every id after it, so the id most likely to poison its successors is currently the one licensed to stop them. | TASK-591 | 2026-09-04 |
| `T_BI_01` | undeclared-gating-class | **DEMOTE.** Asserts `lastPlaylistDraw` advances on Spotify resume — a PLEDIT repaint, local to the Winamp view. No other id reads `lastPlaylistDraw`. It also skips on an empty Spotify queue, which under TASK-243's live 403 is the routine outcome, so in the current environment it is near-permanently inconclusive (BP-074). | TASK-591 | 2026-09-04 |
| `T_BI_04` | undeclared-gating-class | **DEMOTE.** WP-C `C-20`: its stated subject ("cmdTap delivers the Release phase") has no oracle — the reply is synthesised by `cmdTap` from the hit-test, so a firmware that never delivers Release still answers `TRANSPORT`/`PLAY`. What it does assert duplicates T081's, five times over, and the tap-injection premise is already declared CORE on T079. A duplicate of a premise is not a second premise. | TASK-591 | 2026-09-04 |
| `T-CDWN-01` | undeclared-gating-class | **DEMOTE.** WP-C calls it the most carefully built test in the CORE set, and it is — but its subject is SpotifyApp's VIS 300 ms cooldown, a canvas feature. The gate the suite's tap primitive actually drains is the shell's `s_cooldownMs`, a different variable (see T_TBFB_04's docstring). No FEATURE id's verdict depends on VIS cycling. Scope should be `Spotify`. | TASK-591 | 2026-09-04 |
| `T092` | undeclared-gating-class | **DEMOTE.** A latency assertion on the Spotify force poll (≤2000 ms after `reconnect`). A slow poll does not invalidate the taskbar, Clock, Stock, Player or WebRadio families. Its oracle is also fragile in a way that argues against gating: the whole assertion is a `LOG_D` line, which `app/src/logSink.h:119`'s runtime level gate can suppress if any earlier test lowered the log level, and its 2 s window is started after a drain loop that may consume 1 s. | TASK-591 | 2026-09-04 |
| `T_TBFB_01` | undeclared-gating-class | **DEMOTE.** M-TASKBAR-FEEDBACK (TASK-279) feature test: `tb-press` → `tb-commit` → `entered` marker ordering for the amber press feedback. A well-built test — ordering assertions on captured lines, no sleeps — of a visual-feedback feature. The switch LANDING, which is the shared premise, is already declared CORE on T147 and T162. Nothing depends on the marker order. | TASK-591 | 2026-09-04 |
| `T_TBFB_02` | undeclared-gating-class | **DEMOTE.** Same feature: `tb-press-cancel` on a scroll, no commit, no switch. The strongest row in its family (it asserts the negative as well as the positive) and still a feature test — the tap/scroll discrimination it overlaps is declared CORE on T162. | TASK-591 | 2026-09-04 |
| `T_TBFB_03` | undeclared-gating-class | **DEMOTE, and fix the restore first.** Feature test of the WebRadio player-mode slot redirect. WP-C `C-12`: its `finally` writes `set playerMode {r_pm.get('val', 0)}` — if the entry `get playerMode` reply was lost it silently REWRITES persisted SPIFFS state to Spotify instead of restoring it. An id that can corrupt persisted state on a lost reply is a poor candidate for running first, which is what CORE would make it. | TASK-591 | 2026-09-04 |
| `T_TBFB_04` | undeclared-gating-class | **DEMOTE.** Asserts a taskbar gesture never arms SpotifyApp's canvas cooldown and a canvas gesture still does. A feature boundary between two cooldowns, both device-observed, neither a premise: if the canvas cooldown stopped arming, no other id would be misled — the suite drives it to zero before every tap anyway. | TASK-591 | 2026-09-04 |
| `T_TBFB_05` | undeclared-gating-class | **DEMOTE.** The closest of the five to a premise — `Dut.cmd` issues `get shellCooldown` before every tap and drag — but it fails the test in the load-bearing direction: this id asserts the shell cooldown DOES arm on a release, and if it stopped arming, `Dut.cmd`'s drain would simply be a no-op and downstream taps would be unaffected. A failure here does not invalidate anything after it. | TASK-591 | 2026-09-04 |

## Retirement

This file is deleted when the last row is. A row goes when its id carries a class declaration with a
reason — `FEATURE` per the proposal above, or `CORE` with an argument this package could not make.
Until then, `check_test_meta.py` prints the count on every `run/check`, and the count can only fall.
