# Plan integrity — the R46 ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_plan_integrity.py` ·
> Opened **2026-09-05** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R46, TASK-611

## What this file is

[R46](M-HARNESS2-requirements.md) requires a test id to bind to **exactly one body and one
declaration**. `check_plan_integrity.py` measures five ways that breaks, and this ledger holds the
findings that cannot be resolved by editing a document — because resolving them means **renaming a
live test id**, which changes what the suite runs and is @VE's call, not a gate's.

**Every row here suppresses one finding, keyed on `(kind, id)`.** No file, family or wildcard
exemption exists. A row whose finding no longer occurs is a **blocking failure** — the list can only
shrink.

## Re-measurement, 2026-09-05 (TASK-611)

WP-Z's figures were re-measured before this gate was written, and three of them have moved:

| finding | WP-Z said | measured 2026-09-05 |
|---|---|---|
| `A-15` — ids with two executable bodies | 2 (`T_PLR_13`, `T_PLR_25`) | **0.** TASK-603 deleted `T_PLR_25`'s registry copy and the standalone bodies won both adjudications. `P1` is at zero and blocking there |
| `F-2`/`G-11` — registry ids colliding with unrelated plan headings | 3 (`T237`, `T276`, `T231`) | **4.** `T242` is the same shape and was not in the finding: plan `test_plan.md:4240` is "Settings Cancel restores Stock ticker", the body at `app/tools/suite/serialdbg/shell.py:2969` is a taskbar-scroll test |
| `G-12`/`H-13` — six stale plan rows | 6 | **partly fixed, partly reclassified.** The four Stock rows named there were resolved by TASK-603's retirements, and `P4` (a retired id whose plan entry does not say so) reads **0**. The two Teletext rows remain and are `P5` rows below |
| ids with two `###` declarations | not counted | **6, all fixed in this task, none ledgered.** `test_plan.md`'s `serialdbg-audit-001` section re-declared nine ids as `### T176 fix — …` work items, and C6 read a status out of both entries. Retitled to `### Fix for T176 — …`; the id keeps exactly one declaration and the work item keeps its text |

## The checks

| id | what it fails on | count today |
|---|---|---|
| P1 | `two-bodies` — one id, two executable functions | 0 |
| P2 | `two-declarations` — one id, two live `###` plan entries | 0 |
| P3 | `collision` — the plan entry and the body share no content word | 3 |
| P5 | `manual-but-executable` — the plan says `[MANUAL]`/`[Blocked…]`, a body is registered | 3 |
| P4 | `stale-retirement` — a retired id whose plan entry still reads as coverage | 0 |

P3's threshold is **zero shared content words**, not a ratio. Measured over the 79 ids that have
exactly one live plan entry and a body title, the distribution is: 3 ids at 0, 3 at 1, and 73 at 2
or more. All three zeros are real collisions. Of the three ones, `T231` is also a real collision —
and it is caught by P5 instead, on a fact rather than a word count. That is why both checks exist.

## Ledger

Owner = the task that will resolve the row. All six need an **id rename**, which changes what
`run/test` selects and what every coverage claim citing the id means, so they are @VE's to schedule:
they sit under **TASK-614** (registry and tooling honesty), the open row that already carries this
class of debt.

| id | kind | why it is not resolved today | owner | since |
|---|---|---|---|---|
| `T237` | collision | The id was minted from TASK-237 and `test_plan.md:4197` already used `T237` for "[app-settings-wire-001] Crypto currency change". The body (`app/tools/suite/serialdbg/webradio.py:772`) is the ADR-045 auto-skip terminal bound. Renaming the body's id is the fix; it is a live WebRadio id and the rename touches the registry, the plan and `flaky.yaml`. | TASK-614 | 2026-09-05 |
| `T242` | collision | Same shape, **not in `F-2`** — found by this gate. `test_plan.md:4240` is "Settings Cancel restores Stock ticker"; the body (`app/tools/suite/serialdbg/shell.py:2969`) is "Taskbar excludes WebRadio, full scroll cycle". | TASK-614 | 2026-09-05 |
| `T276` | collision | Same shape. `test_plan.md:4546` is an `M-WEBRADIO-PREVIEW` **host-tool** check (skin base layer from `gen/skin_preview.png`); the body (`app/tools/suite/serialdbg/webradio.py:873`) is the TASK-395/393 terminal-retry re-arm. The two are not even the same kind of test — one runs on the host, one on the board. | TASK-614 | 2026-09-05 |
| `T231` | manual-but-executable | `F-2`'s third collision, caught here rather than by P3 because both titles contain the word "settings". `test_plan.md:4118` is "[app-settings-wire-001] Aquarium speed slow/fast visually distinct **[MANUAL]**"; the body (`app/tools/suite/serialdbg/stock.py:675`) is the Stock mode launch view. A `[MANUAL]` entry with a registered body cannot both be true. | TASK-614 | 2026-09-05 |
| `T270` | manual-but-executable | `G-12`/`H-13`'s first Teletext row. `test_plan.md:4468` still reads `[Blocked: G1, G2]` while `app/tools/suite/serialdbg/teletext.py:215` registers and runs a body. Whether the row's blockers were cleared or the body tests something narrower than the row claims is a question for the Teletext family, not a document edit. | TASK-614 | 2026-09-05 |
| `T271` | manual-but-executable | `G-12`/`H-13`'s second. `test_plan.md:4477` reads `[Blocked: G2]`, `app/tools/suite/serialdbg/teletext.py:216` registers a body. Same question. | TASK-614 | 2026-09-05 |

## How a row leaves

Either the id is renamed so the plan entry and the body describe the same test, or the plan entry is
corrected so it does — and the row is **deleted in the same change**. The gate fails on a row whose
finding no longer occurs, so a fix that leaves the row behind is caught on the next `run/check`.
