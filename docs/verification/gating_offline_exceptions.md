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
> reads **8 ids / 15 findings** today. The criterion is **NOT MET**, and no row in this file makes
> it met: a row records the dependence, it does not remove it.

## What the gate looks at

For each gating id it walks the body and every same-package helper it reaches, and reports four
kinds. The closure walk is the point — every id below reaches its dependence through a helper
(`_wait_chart_complete`, `_poll_chart_len_positive`, `_stock_ok_count`, `wait_for_queue`), so a grep
over the body sees none of them. That is how seven CORE ids became network-dependent with nobody
writing it down.

| kind | exemptable | count today |
|---|---|---|
| `network-key` | yes | 4 |
| `network-helper` | yes | 4 |
| `network-app` | yes | 7 |
| `host-file-layout` | **no** | **0** |

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

## What each id needs — and why none of it is landed

Three of the eight carry a **declared** CORE class with a written reason (TASK-591) that already
names R36 as owed; the other four are the ledgered undeclared ids in
[gating_class_declarations.md](gating_class_declarations.md), owned by TASK-634's DUT session.
**Every one of the eight needs the same decision from a human**: demote it out of CORE, or inject
its precondition so the assertion survives an outage.

| id | class today | the dependence | the two options |
|---|---|---|---|
| `T-BUSY-01` | CORE, **undeclared** | 45 s live Yahoo chart fetch, hard `fail()` on timeout | Demote (proposed in the R35 ledger; its `shellBusy` premise is already declared CORE on `T-BUSY-02`), or split the fetch half off |
| `T-BUSY-01b` | CORE, **undeclared** | two live chart fetches | As above; its negative outcome is a `skip()`, so it is the weakest of the four |
| `T-BUSY-05` | CORE, **undeclared** | `set triggerFetch 1` + Stock activation | Demote (R35 ledger proposes it), or inject |
| `T-CDWN-03` | CORE, **undeclared** | `set triggerFetch 1` + Stock activation | Demote (R35 ledger proposes it), or inject |
| `T-CDWN-02` | CORE, **declared** | a 60 s secondary assertion that is a live Yahoo fetch. The declaration says so and calls it owed to this task | Keep CORE and **make the secondary assertion non-gating**, or inject the fetch. The primary assertion — the `cmdTap` busy gate returning `skipped:true` — needs no network at all and is the half that earns the class |
| `T-BUSY-03` | CORE, **declared** | activates Weather and Crypto, both of which fetch on activation | Keep CORE and drop the two fetching apps from its six (Clock/Matrix/Life/Aquarium are passive and carry the same claim), or inject |
| `T_BI_03` | CORE, **declared** | `wait_for_queue(min_count=2)` — a live Spotify queue, which under TASK-243's permanent 403 it does not get | Inject the queue (`set queue N` already exists and is the documented injection for exactly this) or demote |
| `T_X07_01` | CORE, seeded | rapid Weather↔Crypto switching; its premise is the activation fetches | **Undecided and unlisted before today.** Its claim (dataTask stability under app churn) may not be representable offline at all |

`T_BI_03`'s option is the interesting one: `set queue N` seeds the Spotify queue snapshot and is
already used to unblock PLEDIT-row tests without an account. If it satisfies `wait_for_queue`, that
id leaves this ledger for free and without a class change — which would make it the only one of the
eight that is not a human decision.

## Ledger

Owner = **TASK-617**, the held class-order-switch decision, because that is where the demote-or-inject
ruling belongs: it is the decision these rows are a precondition of, and taking them one at a time
would decide it by attrition. `since` = the date the row was opened.

| id | kind | why it is not resolved today | owner | since |
|---|---|---|---|---|
| `T-BUSY-01` | network-helper | Reaches `_poll_chart_len_positive()` — 45 s of live HTTPS to Yahoo, and a timeout is a hard `fail()`, not a skip. Demote-or-inject is a human ruling (R35 ledger proposes DEMOTE). | TASK-617 | 2026-09-05 |
| `T-BUSY-01` | network-app | Activates Stock via `_switch_to_stock()`, whose `init()` issues the chart fetch. | TASK-617 | 2026-09-05 |
| `T-BUSY-01b` | network-key | `set triggerFetch 1` enqueues a live fetch on the dataTask. | TASK-617 | 2026-09-05 |
| `T-BUSY-01b` | network-helper | Reaches `_stock_ok_count()`/`_wait_chart_complete()` — two live chart fetches, and the negative outcome is a `skip()`, so a real regression and a fast fetch are indistinguishable. | TASK-617 | 2026-09-05 |
| `T-BUSY-01b` | network-app | Activates Stock. | TASK-617 | 2026-09-05 |
| `T-BUSY-03` | network-app | Activates Weather and Crypto, both of which fetch on first activation — the id's own body says so (`_FETCH_APPS`). The claim is about passive apps and four of its six are passive; dropping the two fetching apps is a coverage change, hence a ruling. | TASK-617 | 2026-09-05 |
| `T-BUSY-05` | network-key | `set triggerFetch 1`. | TASK-617 | 2026-09-05 |
| `T-BUSY-05` | network-app | Activates Stock. | TASK-617 | 2026-09-05 |
| `T-CDWN-02` | network-key | `get fetchOkCount`/`get fetchErrCount` and `set triggerFetch 1` — the 60 s secondary assertion its own `cls_reason` flags as owed to R36. | TASK-617 | 2026-09-05 |
| `T-CDWN-02` | network-helper | Reaches `_stock_ok_count()`. | TASK-617 | 2026-09-05 |
| `T-CDWN-02` | network-app | Activates Stock. | TASK-617 | 2026-09-05 |
| `T-CDWN-03` | network-key | `set triggerFetch 1`. | TASK-617 | 2026-09-05 |
| `T-CDWN-03` | network-app | Activates Stock. | TASK-617 | 2026-09-05 |
| `T_BI_03` | network-helper | `wait_for_queue(min_count=2)` needs a live Spotify queue, which TASK-243's permanent 403 prevents. The `set queue N` injection may remove this row without a class change — that is the one row here that might not need a ruling, and it needs a DUT to confirm. | TASK-617 | 2026-09-05 |
| `T_X07_01` | network-app | Rapid Weather↔Crypto switching; the activation fetches ARE its subject. **Found by this gate, on no prior R36 list.** | TASK-617 | 2026-09-05 |

## How a row leaves

The id is demoted out of the gating class with a written reason, or its precondition is injected so
the assertion holds with no external service reachable — and the row is deleted in the same change.
The gate fails on a row whose finding no longer occurs, so a fix that leaves the row behind is caught
on the next `run/check`.
