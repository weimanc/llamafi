# Gating classes that need the outside world — the R36 ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_gating_offline.py` ·
> Opened **2026-09-05** by [TASK-626](../project/tasks-harness2.md) ·
> Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R36

## What this file is

[R36](M-HARNESS2-requirements.md) requires a RIG, HEALTH or CORE test's precondition to be
**satisfiable offline on a healthy board**. The cost of breaking it is not a lost test, it is a lost
run: a CORE id that FAILs on a 45 s live HTTPS timeout runs at index 14 under TASK-566's class order
and NOT-RUNs the 167 FEATURE ids below it. A network outage must not be able to declare the firmware
untestable.

`check_gating_offline.py` measures it. This ledger holds the ids that break it today, **because
fixing one changes what the suite blocks on** — either the id leaves the CORE class, or its
precondition is injected so it no longer needs a live fetch. TASK-591's twenty demotions were put to
the human for exactly that reason and approved as a set; these are the same kind of decision and
have not been taken.

> **This gate reading zero is an exit criterion of [TASK-617](../project/tasks-harness2.md).** It
> read **8 ids / 15 findings** when this file was opened. After the human's 2026-09-06 ruling
> it read **2 ids / 3 findings**. The criterion is still **NOT MET** — one row remains
> (`T_BI_03`) — but it is **no longer a decision**: a row records the dependence, it does not
> remove it, and this one now needs a suite change, not a ruling.
>
> **Update 2026-09-07 (@PM, TASK-634's session).** One of the three findings is no longer a
> decision: `T_BI_03`'s open question was answered YES on hardware, so it is now a small suite
> change, not a ruling.
>
> **Update 2026-09-13 (TASK-617).** The two `T-CDWN-02` rows are gone. `set shellBusy 1`
> (`armedInjectors.h`'s `shellBusy` entry, M-HARNESS2 R14) raises `shell::state().busy` through
> the exact field and `busySetMs` stamp a real enqueue uses, with no app fetch anywhere in the
> id's precondition — the ADR-063-shaped injection this file always said would clear them. The
> suite change: `T-CDWN-02` arms via `dut.injected("shellBusy", 1, clear_to="0")` instead of
> `set triggerFetch 1` + a Stock activation, and no longer touches StockApp at all. `check_gating_
> offline.py` now reads **1 id / 1 finding** (`T_BI_03` only).

## What the gate looks at

For each gating id it walks the body and every same-package helper it reaches, and reports four
kinds. The closure walk is the point — every id below reaches its dependence through a helper
(`_wait_chart_complete`, `_poll_chart_len_positive`, `_stock_ok_count`, `wait_for_queue`), so a grep
over the body sees none of them. That is how seven CORE ids became network-dependent with nobody
writing it down.

| kind | exemptable | at opening | today |
|---|---|---|---|
| `network-key` | yes | 4 | 1 |
| `network-helper` | yes | 4 | 1 |
| `network-app` | yes | 7 | 1 |
| `host-file-layout` | **no** | **0** | **0** |

`host-file-layout` is **not exemptable and is blocking at zero.** It was `B-2`'s shape — a CORE id
that was a host-side `grep` of `lib/SpotifyArduino/`, so a checkout missing a directory would
NOT-RUN the FEATURE suite on a fact about the checkout. TASK-591 demoted that id (`T133`) and the
count has been zero since; an exemption kind with no rows is an invitation to open one, so the gate
refuses a row of this kind outright.

## Re-measurement, 2026-09-05

TASK-591 named seven ids. The gate finds **eight**:

* the seven are all confirmed — `T-BUSY-01`, `T-BUSY-01b`, `T-BUSY-05`, `T-CDWN-02`, `T-CDWN-03`
  (live Yahoo), `T-BUSY-03` (Weather/Crypto activation fetch), `T_BI_03` (live Spotify queue ≥ 2);
* **`T_X07_01` is new.** Its whole subject is rapid Weather↔Crypto switching under dataTask
  contention, so its premise *is* two activation fetches. It was never on any R36 list. Nothing in
  the static reads TASK-591 did could have caught it, because it names no fetch key: it taps taskbar
  slots.

The host-file-layout case named in the board row is confirmed gone: `T133`'s demotion removed it and
the check reads zero.

## The ruling, 2026-09-06 (TASK-626, executed)

The human took the eight decisions as a set. What landed, and what each cost:

| id | ruling | landed as | rows left |
|---|---|---|---|
| `T-BUSY-01` | **DEMOTE** | `@meta(cls="FEATURE", cls_reason=…)` on the body. Its `shellBusy` premise is already declared CORE on `T-BUSY-02`, which asserts both edges with a hard `fail()` on each and needs no network | 0 |
| `T-BUSY-01b` | **DEMOTE** | as above; it was the weakest of the four — its negative outcome is a `skip()`, so a real regression and a fast fetch are indistinguishable | 0 |
| `T-BUSY-05` | **DEMOTE** | as above. WP-C `C-1`'s inverted guard means it passes exactly when the regression is present; a test that cannot report its own failure cannot license stopping the run | 0 |
| `T-CDWN-03` | **DEMOTE** | as above. Its bypass precondition is never established (BP-074), and its falsifiable half duplicates `T_BI_02`/`T147` | 0 |
| `T-CDWN-02` | **SPLIT** | the 60 s live-Yahoo half is now **`T-CDWN-04`**, a FEATURE id. `T-CDWN-02` keeps the `cmdTap` gate assertion, the CORE class, and — new — a real `fail()`, guarded by the `shellBusy` reading skip-adjudication row 101 named as the precondition of converting it | **2 — see below** |
| `T-BUSY-03` | **RE-POINT** | Weather and Crypto dropped; the list is Clock/Matrix/Life/Aquarium. Zero coverage lost, and that is a fact about `cmdTouch.cpp`, not a judgement — see the verification note below | 0 |
| `T_BI_03` | **DEFER** to TASK-634 | unchanged. `set queue N` may already satisfy `wait_for_queue(min_count=2)`, which would clear the row with no class change; that needs a DUT to confirm | 1 |
| `T_X07_01` | **DEMOTE** | `@meta(cls="FEATURE", …)`. Its activation fetches are its subject, so injecting the precondition would delete the claim; demoted rather than opening an exceptions precedent | 0 |

**8 ids / 15 findings → 2 ids / 3 findings.**

### Why `T-BUSY-03`'s re-point costs nothing — verified, not assumed

The claim was that four of its six apps are passive and carry the same claim. Checked against
firmware rather than against the earlier analysis, and it is **stronger** than claimed:
`app/src/debug/serialConsole/cmdTouch.cpp` dispatches an injected canvas tap on `currentAppId`, and
**Weather, Crypto, Matrix, Life and Aquarium all fall through the same terminal `else`**
(`hit=CLOCK`, `app/src/debug/serialConsole/cmdTouch.cpp:141-144`) — no app handler, no
`hasPendingAsync()` check, so no `setBusy` call is reachable on that branch at all. Clock is the one
with a branch of its own (`CLOCKAPP`, `:133-140`), whose comment states the same thing: *"no async, so no setBusy
propagation"*. So the two apps removed were driving a **duplicate of the Matrix/Life/Aquarium code
path plus a network dependency**, and the four retained apps drive every path the six drove. The
`cls_reason` names Clock, Matrix, Life and Aquarium as the families the claim protects; it now
matches the body.

### Why `T-CDWN-02` had two rows for so long, and how they were cleared (TASK-617, 2026-09-13)

The disposition expected this ledger to shrink to `T_BI_03` alone. It did not for a while, and the
two residual rows were reported rather than argued around.

The primary assertion needs the busy gate to be **armed**, and the only way to arm it in StockApp was
`set triggerFetch 1` (a local write that zeroes cache timestamps) followed by a drill tap (a local
enqueue on the dataTask). **Neither waited on Yahoo** — `shellBusy` rises at enqueue, and the verdict
resolves on the shell's own reply — but the checker could not see that: `triggerFetch` is in
`NETWORK_KEYS` because it *arms* a live fetch, and `Stock` is in `NETWORK_APPS`. The finding was a
true statement about the static proxy and a false one about the run, and that was worth having
written down exactly once rather than smoothed away.

Two things were **not** done, deliberately, and still were not done in the fix:

* **the id was not re-pointed at Spotify.** A `PLAY` tap raises `shellBusy` the same way
  (`T-BUSY-02` does exactly this) and `Spotify` is not in `NETWORK_APPS` — so the gate would read
  zero. But SpotifyApp's pending async *is* a Web API poll; the id would be no more offline-
  satisfiable, only invisible to the checker. That is gaming the gate, not meeting R36.
* **`triggerFetch` was not removed from `NETWORK_KEYS`.** It arms a live fetch for the several other
  ids that then wait on the result, and weakening the key for all of them to clear one id is the
  same trade in a different direction.

What actually cleared these two rows is the **injection** this file always said would: `set shellBusy
1` (`app/src/debug/armedInjectors.h`'s `shellBusy` entry, M-HARNESS2 R14) writes
`shell::state().busy = true` through the exact same `shell::setBusy()` call and `busySetMs` stamp a
real enqueue uses — no app fetch, real or forced, anywhere in the path. It needed exactly one new bit
of firmware state (`ShellState::busyForced`, TASK-635 §2.2 clause 3): a *forced* busy has no real
`hasPendingAsync()` behind it, so `main.cpp`'s loop()'s primary auto-clear (`!hasPendingAsync() ->
setBusy(false)`) would otherwise clear it on the very next tick; `busyForced` makes loop() skip that
one check for a forced busy while leaving the `SHELL_BUSY_TIMEOUT_MS` safety net and `set shellBusy
0`/`set injclear` untouched. `T-CDWN-02` now arms via `dut.injected("shellBusy", 1, clear_to="0")`
and no longer switches to Stock or reads any Stock state at all — the id's scope moved from `Stock`
to `shell` accordingly, since the gate it asserts (`cmdTouch.cpp:47`) reads `shell::state().busy`
before any app-specific dispatch runs.

## Ledger

Owner = **TASK-617**, the held class-order-switch decision, because that is where the demote-or-inject
ruling belongs: it is the decision these rows are a precondition of, and taking them one at a time
would decide it by attrition. `since` = the date the row was opened.

| id | kind | why it is not resolved today | owner | since |
|---|---|---|---|---|
| `T_BI_03` | network-helper | `wait_for_queue(min_count=2)` needs a live Spotify queue, which TASK-243's permanent 403 prevents. **Question ANSWERED on hardware 2026-09-07 (TASK-634 session A §1.5): `set queue N` DOES satisfy `wait_for_queue(min_count=2)` — YES, and with no class change.** So this row no longer needs a ruling; it needs the small suite change that points the helper at the injection, after which the row is deleted. It is the one row here that is a work item, not a decision. | TASK-617 | 2026-09-05 |

## How a row leaves

The id is demoted out of the gating class with a written reason, or its precondition is injected so
the assertion holds with no external service reachable — and the row is deleted in the same change.
The gate fails on a row whose finding no longer occurs, so a fix that leaves the row behind is caught
on the next `run/check`.
