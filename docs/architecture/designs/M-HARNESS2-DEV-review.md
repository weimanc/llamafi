# M-HARNESS2 — Developer review

> Owner: **Developer**
> Status: review — advisory, binding on nothing
> Written: 2026-09-03
> Reviews: [M-HARNESS2 requirements](../../verification/M-HARNESS2-requirements.md) (@VE, 55 reqs,
> 37 MUST / 18 SHOULD) **as amended by** the
> [Architect review](M-HARNESS2-architect-review.md) (12 amendments, R3(a) rejected, R5 re-specified
> as GRAM readback)
> Against: `app/tools/lib/`, `app/tools/suite/serialdbg/` (15 modules, ~11 900 lines),
> `app/tools/gate/`, `run/*`, `app/src/debug/serialConsole/` (3 684 lines) ·
> [WP-Z §4](../../verification/reviews/M-TESTQUAL-Z-findings-review.md) (41 proposed tasks) ·
> [best_practices.md](../../quality/best_practices.md)
> Method: static only. No DUT, no serial port, no flash — the board is pinned to `-DBOD_WATCH`
> (TASK-557). Nothing under `app/tools/` was imported; every count below is a grep or arithmetic,
> and the command is given.

---

## 0. Overall verdict

**I would sign up to build about a third of this, and I would refuse the rest as scoped.** The
mechanism half — the result artifact, the typed verdict, the class declarations, the import guards,
the typed accessors — is ~61 engineer-days of work I believe in, most of it host-only and therefore
buildable *today* against a pinned board; the corpus half is ~57 more days that the document prices
at zero by calling it "a ratchet", and a ratchet is not an estimate, it is a way of not giving one.
The total as written is **~154 engineer-days — roughly seven months of one engineer** — against a
project whose largest completed milestone was a fraction of that, and roughly 30 of those days are
already committed on WP-Z's own 41-task board, so scheduling both documents double-books a month.

What I would cut, in order: **R44** (threshold citations — a >1 000-site ratchet with no completion
condition, which is `check_docs` C3's exact shape and will be scrolled past within a quarter),
**R26** (device push — concur with the Architect's DEFER), **R8** (injection parity — unmeasured
benefit on a 0-byte static pool), **R53's budget table** (numbers with no derivation, enforced by
"reporting"), and **AC11's ≤ 25 sleeps** (a round number in a document whose discipline is that
every number is measured — the Architect flagged it and he is right). And I would add one thing the
document does not have: **a sanctioned way to delete a test id.** Nineteen of the 216 should be
deleted rather than migrated, and three of them are already bodies consisting of a single `skip()`
precisely because nobody had a procedure for removing an id. That deletion is the cheapest
acceptance-criterion movement in the whole programme and it costs one day.

The document's central claim is right and I am not arguing with it. Test quality is a property of
the observable; `A-8`, `G-3` and `B-5` are firmware defects wearing test-failure clothes; and the
Architect's re-seat of R3 onto the shell plus his GRAM-readback re-specification of R5 make both
buildable where they were not. My objections are about who pays and whether the declarations can be
lied to.

---

## 1. Is it implementable as written?

### 1.1 Method

Every row is graded on two axes, because the document consistently conflates them:

* **Mechanism** — the gate, the schema, the `lib/` change, the firmware key. Written once.
* **Retrofit** — applying it to the 213 registered ids, the 19 files that open a port, the 253
  sleeps. This is where the document says "ratchet" and stops counting.

Scale words: **already true**, **S** (< ½ day), **M** (1–3 days), **L** (> 3 days), **BLOCKED**.
Day figures are engineer-days for one person who knows this codebase; they exclude DUT wall-clock,
which is counted separately in §1.4. Estimates are anchored to a measured quantity in the tree — the
number of call sites, the number of ids, the size of the file — not to a feeling.

### 1.2 The 37 MUSTs

| # | Req | Mechanism | Retrofit | Days | Anchor for the number |
|---|---|---|---|---|---|
| 1 | R1 vocabulary rule | M | L | **8** | the `reads:` extraction can reuse `_meta.py:178` `_reachable_source()` (it already walks helper transitivity, 6 deep); the 213 `reads:`/`oracle_reason` declarations at ~2 min each are 6 d |
| 2 | R2 no self-write oracle | S | M | **2.5** | same source-walk; ~30 sites match the `set X`…`get X` shape and most are on my delete list |
| 3 | R3 app admission | BLOCKED on ADR-A | L | **7** | Architect's shell half ~1.5 d; per-app result+entry-state across 13 apps in `app/src/**/*App.cpp` at ~0.3 d each = 4 d; conformance rows in `check_app_conformance.py` (554 lines, already enumerates `APP_ORDER`) ~1 d |
| 4 | R4 UNOBSERVABLE ledger | S | M | **2.5** | the ledger is `id_binding_exceptions.md`'s shape, already parsed at `check_docs.py:_parse_ledger`; ~1 d to write today's records |
| 5 | R5 render signature | BLOCKED on ADR-B | L | **6** | `get sig` reuses `cmdMisc.cpp:66-131`'s band loop (~2 d incl. TWDT feed); `set now` ~0.5 d; `colorprobe` HEALTH row ~0.5 d; rewriting the Clock family is 3 d and produces **new ids, not migrations** |
| 6 | R6 observable ships with feature | S | — | **0.5** | a `NEW-APP-CHECKLIST.md` §3 edit; enforcement is R3's rows |
| 7 | R9 declared falsifier | S | L | **8.5** | the presence gate is a `check_test_meta.py` clause (215 lines, the pattern exists); 213 honest falsifiers at ~15 min each is 8 d and is the single largest line item in the document |
| 8 | R10 transcript mutation | L | L | **8** | see §4 — engine 3 d, keyed recorder 1 d, divergence handling 2 d, driver + negative test 1.5 d; plus board time to record |
| 9 | R12 live-channel negative | M | new-only | **2** | static detection of "the only `fail()` is timeout-guarded" is heuristic over ~262 `skip()` and the `_wait_for_log` sites; budget the exemption ledger |
| 10 | R14 armed-state enumeration | M | S | **3** | firmware bitmask is ~8 B and half a day, but there is **no generated injector list to bitmask over** — `gen_get_keys.py` covers `get` only, so the generator is the real cost |
| 11 | R16 effect declared and verified | M | M | **3.5** | boundary check needs settings-hash + reboot + entry-app observation (~1.5 d); 213 confirmations at ~1 min each is 0.5 d, plus the `persisting` firmware key |
| 12 | R17 restore as context manager | M | L | **8** | `_bgpoll_suspended` exists and is used at 20 of 41 sites; the other 21 plus every `set` in ~100 bodies is 6 d. See §7 — I dispute the *gate* here, not the requirement |
| 13 | R18 no defaulted read | S | M | **3** | one typed accessor in `lib/dut.py`; the gate is a one-line regex; **98 sites** match `.get("key", <literal>)` in `suite/serialdbg/` |
| 14 | R20 shuffled order | S | scheduled | **1** | `_order.py` (339 lines) already computes and diffs orders; the flag is half a day. The cost is board time, not code |
| 15 | R22 wait is a failure bound | M | new-only | **3** | needs one `wait_until()` in `_helpers.py` (WP-Z's TASK-607) plus a heuristic gate over bounded loops |
| 16 | R23 no bare sleep | S | L | **9** | ratchet gate is trivial; **253 sleeps** is 8 d *if the observables exist*, and for several families they do not — which makes this partly BLOCKED on R3/R5 |
| 17 | R25 correlated replies | M | M | **2** | in the Architect's additive form: `console.cpp` (230 lines) parses `get#7`, `lib/dut.py:1122` opts in, call sites ratchet. As the VE's flag-day it is 5 d+ |
| 18 | R28 verdict vocabulary | S | L | **5.5** | the enum is half a day; splitting **262 `skip()` sites** into SKIP vs UNMET is per-site judgement — 5 d, and see §7 for the migration order |
| 19 | R29 artifact is the interface | M | S | **2** | `results.py` is 312 lines with one print loop at `:269-271`; three consumers to move |
| 20 | R30 the run's premise | M | — | **1.5** | build identity already read by `run/player-gate`; `dut.py:1050-1065` has the env-verify machinery to hang the ELF hash on |
| 21 | R31 typed verdict | S | M | **1.5** | `_gate.py:129`'s `startswith("FAIL")` is one line, but every `RESULTS.get(...)` consumer moves with it |
| 22 | R33 one results layer | S | L | **3** | `run_sync_tests.py`'s private copy plus the four `SerialDut` clones; 19 files call `serial.Serial(` |
| 23 | R34 no unfalsifiable coverage | M | S | **2** | an AST walk for "no reachable `fail()`" is decidable on these bodies; the coverage figure comes from C6's binding data, already built |
| 24 | R35 declared gating class | S | M | **1.75** | the gate clause is 2 h; the 43 CORE reason strings are 1.5 d and **are the audit** |
| 25 | R36 gating class offline | M | M | **2** | classifying a body as network-touching is heuristic; demoting the 7 Stock CORE ids and `T133` is the other day |
| 26 | R37 no flake in a gating class | S | — | **0.25** | cross-product of `flaky.yaml` and the meta census; both already parsed |
| 27 | R38 UNMET blocks | S | — | **1** | `_gate.py:120-134` plus the inversion selftest's new arm; depends on R28 |
| 28 | R40 every class dispatchable | S | S | **1.5** | the gate is trivial; making the RIG class reachable from a `run/` script is the real half (`C-3`) |
| 29 | R42 no mirrored facts | M | M | **4** | the nine-mirror register plus parsers; several parse sources exist (`app_ids_gen`, `preview_common.py`) and are unused |
| 30 | R46 ids exist once | M | M | **2** | `check_docs.py` C6 already keys by id (`:659-676`); duplicate-body detection is new, the six collisions are the other day |
| 31 | R47 one session layer | S | L | **4.5** | the gate is an hour; **19 files** and four whole `SerialDut` harnesses is 4 d and is not a ratchet you finish in the background |
| 32 | R48 no import-time board access | S | S | **1.5** | six `__main__` guards; the subprocess-import gate with a stubbed `serial` is a day. **Highest ratio in the document** |
| 33 | R49 typed rig-vs-device exit | M | M | **2** | `results.py:161`'s `HEALTH_FAIL_EXIT` exists; the message-selection half touches four entry points and their selftests |
| 34 | R50 fitness before, never after | already true (S) | — | **0.5** | `run/dut-health` already warns; add the selftest |
| 35 | R51 pinned build | BLOCKED on TASK-618 | S | **1.5** | the Architect's verify-and-refuse form: read build identity, exit 4, delete the trap in two scripts |
| 36 | R53 per-class budget | S | — | **0.5** | falls out of R30's artifact. The *table* I reject as a MUST — see §7 |
| 37 | R54 slow tests declare why | S | M | **1.5** | elapsed ranking is free from R30; the declarations are a day; the duplicate-precondition half is by review |

**MUST subtotal: ~117.5 days** — **61 mechanism, 56.5 retrofit.**

### 1.3 The 18 SHOULDs

Shorter, because they are the part that will not get built (§5).

| # | Req | Days | Note |
|---|---|---|---|
| 38 | R7 versioned console | **1** | the generator-completeness half is a one-word glob fix (`*.h` → `*.[hc]*`, WP-Z TASK-600) and the Architect is right to promote it to MUST |
| 39 | R8 injection parity | **3** | firmware on a pool measured at 0 B in July; benefit unmeasured by the VE's own admission |
| 40 | R11 hardware falsification campaign | **1** + board | the mechanism is a record format; the campaign is calendar |
| 41 | R13 never-failed report | **0.5** | free once R30 exists |
| 42 | R15 injector cleared on resume | **1** | 13 apps, one line each — but see the Architect's amendment, which I agree with |
| 43 | R19 session-level snapshot | **2** | interacts with `run/test` step 0b/5b, which currently erases the evidence |
| 44 | R21 ORDER-DEPENDENT outcome | **0.5** | one verdict value once R28 lands |
| 45 | R24 one timeout policy | **3** | **727** numeric `timeout=` literals; mostly mechanical, all of it boring |
| 46 | R26 device push | **4** | DEFER — concur with the Architect |
| 47 | R27 ack means handled | **1** | the `"skipped"`-flag half is nearly free and worth doing first, as the VE says |
| 48 | R32 structured reasons | **1.5** | schema plus a grouping report |
| 49 | R39 real HEALTH checks | **3** | five checks, each negative-tested, all inside the 60 s budget; plus the Architect's `colorprobe` row |
| 50 | R41 generated APP class | **4** | 12 hand-copied ids across four families |
| 51 | R43 derive once | **1** | folded into R42's pairs |
| 52 | R44 cited thresholds | **6** | > 1 000 literals. This is the one I would cut outright |
| 53 | R45 generated code has a consumer | **0.5** | the Architect took the decision; it is now an edit |
| 54 | R52 declared fixtures | **3** | the declaration format is undecided, which is honest and also means it is not estimable to better than ±50 % |
| 55 | R55 endurance outside the gate | **0.5** | the entry points are already separate; this is documentation |

**SHOULD subtotal: ~36.5 days.**

### 1.4 Total, and what it does not include

**~154 engineer-days ≈ 31 working weeks ≈ 7 months of one engineer.**

Split: **61 d** new mechanism · **56.5 d** retrofit of the existing corpus · **~19 d** firmware
(R3, R5, R14, R25, R26, R27, `set now`) · **~17 d** SHOULDs that are neither.

Not included, and each is real:

* **Board time.** R20's AC13 alone is three shuffled full runs at up to 60 min each, plus
  diagnosis. R11's campaign is one class per session, quarterly. R10 needs a recording pass over
  every replayable id. Call it **10–15 board-hours** on a rig that is one board, serialised, and
  currently pinned.
* **The ADRs.** Five, per the Architect's §9. Two of them (A and B) gate 13 days of the table above.
* **Re-derivation.** Every firmware item must land against a freshly derived `.map` (ADR-060 D8,
  and the project's own recorded lesson that `dram0_0_seg` headroom is a moving target). That is
  ~20 min per firmware commit, and the OBS contract is 13 commits by the Architect's own landing
  rule.

### 1.5 Reconciliation with WP-Z's 41 tasks

This matters because the two documents will otherwise be scheduled as if they were disjoint. They
are not. Mapping the ones that are the same work:

| WP-Z task | M-HARNESS2 requirement | Days double-counted |
|---|---|---|
| TASK-584, TASK-590 | R28 / R34 | ~4 |
| TASK-591 | R35 | ~1.75 |
| TASK-592 | R20 | ~1 |
| TASK-593 | R3 (firmware half) | ~3 |
| TASK-596, TASK-602 | R17 / R18 | ~5 |
| TASK-599 | R47 | ~4.5 |
| TASK-600 | R7 | ~1 |
| TASK-603 | R34 + my delete list | ~1 |
| TASK-606 | R42 | ~4 |
| TASK-607 | R23 / R24 | ~3 |
| TASK-608 | R29 | ~2 |
| TASK-609 | R48 | ~1.5 |
| TASK-613 | R44 | ~6 |

**~38 days of the 154 are already on WP-Z's board.** Net new M-HARNESS2 work is therefore
~116 days, and the two documents must be scheduled as one programme or a month gets paid twice.
That is a @PM item, and it is the most useful number in this section.

---

## 2. The per-test authoring burden

### 2.1 What a new test costs after this lands

Writing a test in this suite today is: pick an id, write a 20–60 line body against `dut.cmd`, add
it to the family's `TESTS` dict, add a `test_plan.md` row (C6 blocks without it). Call it **1–3
hours** including the DUT cycle to see it go green and then go red.

Added by M-HARNESS2, per test:

| Declaration | Honest cost | Cost if you are in a hurry | Can it be filled with a plausible lie? |
|---|---|---|---|
| R9 `falsifier` | 10–20 min (you must actually try the perturbation) | 30 s | **Yes, trivially.** "mutate `get chartLen`" is unverifiable prose at declaration time |
| R16 `effect` | 2 min | 0 s — accept the seed | **Yes, two ways**: accept the seeded `mutating` (209 of 213 records do exactly this today), or over-declare `resetting`, which R16 explicitly permits and never fails |
| R35 `cls` + reason | 5 min | 1 min | **Yes.** "shell test" satisfies "a written reason" |
| R28 verdict vocabulary | ~0 | ~0 | **No.** A closed enum with a gate is not defeatable |
| R1 `reads:` + `oracle_reason` | 15 min | 2 min | `reads:` no (mechanically checkable); `oracle_reason` **yes** — it is free text and it is the document's own weakest link, said so in §4 |
| R17 restore | 5 min | 0 — omit it | Detectable, but the gate is the weak part (§7) |
| R30/R32 reason codes | 3 min | 0 | Partly |

**Total honest addition: ~40–50 minutes on a 1–3 hour job — a 30–50 % tax.** Total hurried
addition: about four minutes of typing that passes every gate. That gap is the whole problem.

### 2.2 Which of these I would actually enforce mechanically, and how

I will enforce four things and I will not pretend to enforce the rest.

**R28's vocabulary — enforce absolutely.** One module owns the enum, `fail`/`skip`/`unmet` are the
only writers, and a gate asserts no suite writes a verdict string. Nothing here can be lied to, it
costs the author nothing, and it fixes a live defect (`_gate.py:129` is a `startswith` on a string
that a `FLAKY-PASS` and an `UNMET` both defeat). This is the model for what a good declaration
looks like: *the author does not declare anything, the type system does.*

**R1's `reads:` — generate it, do not declare it.** The VE proposes the author declares `reads:` and
a gate compares it against a parse of the body. But the parse is the ground truth and the
declaration adds nothing except a place to be wrong; `_meta.py:178`'s `_reachable_source()` already
does the transitive walk this needs. **Amendment: `reads:` is generated into the record, and the
author declares a `claim_class` from a closed enum (`time | order | render | fetch | state |
identity`).** Then the vocabulary rule becomes mechanical for the common cases — a `claim_class:
time` whose generated `reads:` contains no timestamp key is a gate failure, no human judgement
required — and `oracle_reason` shrinks to the residue. That converts the document's weakest MUST
into a mostly-mechanical one at no extra authoring cost.

**R16's `effect` — close the over-declaration hole.** As written, "a declaration stronger than the
behaviour is allowed and reported, never failed" means `effect: resetting` on every test satisfies
the gate forever and R14/R17/R19 all key off a field that has become a constant. **Amendment: after
three runs in which a test's observed effect is stable and weaker than its declaration, the
declaration fails.** The artifact (R30) already has the observations; this is a report over three
archived runs, not new machinery, and it is the only version of R16 that cannot be defeated by
typing one word.

**R9's `falsifier` — make it executable or make it expire.** A prose falsifier is a lie surface, and
this project has already solved this exact problem once: `flaky.yaml` requires `owner`, `task` and
`review_by`, and `results.py:193-196` turns an expired declaration into a FAIL. Reuse it verbatim.
**Amendment: two fields, not one.** `falsifier_replay: {key, mutation, expect: FAIL}` — executable,
checked every run by R10's job, no human judgement. `falsifier_physical: {action, owner, task,
executed_on, review_by}` — and an unexecuted or expired physical falsifier is a **gate failure**,
exactly as an expired flake declaration is. Without the expiry, R11 being a SHOULD means every
physical falsifier is written once and never executed, and AC4 reads 100 % declared / 0 % confirmed
forever.

**R35's `cls` reason — I would not enforce the reason, I would cap the class.** No gate can tell a
considered reason from "shell test". What *can* be enforced is R36 (a CORE precondition must be
satisfiable offline) and a **budget on the CORE set**: 43 ids today, and raising the count requires
a row in a design doc, not a decorator. A class whose membership is capped and whose preconditions
are mechanically checked does not need its prose to be honest.

### 2.3 The scaffold is not optional

If the declarations must be typed by hand, they will be typed badly. **`run/new-test <scope> <id>`
should emit the record with `reads:`, `effect` and `scope` pre-filled from the body and the seed,
leaving the author only the two fields that require thought (`claim_class`, `falsifier_replay`).**
That is half a day of work and it is the difference between a 5-minute tax and a 45-minute one. It
is not in the requirements document. It is item D4 in §6.

---

## 3. Migration of the existing 216

### 3.1 Is host-only first the right first increment?

**Mostly yes, and for a better reason than the document gives.** The VE's first reason — "it is the
only increment available, because the board is pinned" — is an argument from a temporary
circumstance, and TASK-618 could dissolve it next week. The durable reason is the fourth one:
**the schema is verifiable without the thing it verifies.** Everything else in the document is a
test of tests; the artifact is not, and its negative tests can be written the way `gate/`'s already
are (BP-068).

Three changes I would make to the increment as scoped.

**Take R28's *migration* out of it.** The verdict *vocabulary* is host-only and cheap. Splitting 262
`skip()` sites into SKIP and UNMET is 5 days of per-site judgement, and doing it in increment 1
means the increment lands as a mass reclassification of green cells to non-green with no board
available to confirm any of them. **Land the enum and the `UNMET` value; reclassify only the 31 CORE
skip sites (`C-5`), which is bounded at 43 ids and is the set that actually changes what a gate
does.** The other 231 default to SKIP and become a ratchet.

**Put R48 in it.** Six `__main__` guards plus the subprocess-import gate is 1.5 days, it is host-only,
and it is the precondition for R10 (the Architect noticed this; the §14 migration table does not).
More immediately: those six modules reset the board at import, and they will do it again to the next
person who greps the tooling. It belongs in the first increment on cost-benefit alone.

**Put the deletions in it.** Nineteen ids removed is the cheapest movement on the acceptance table
(AC5 goes to 0, the 213-id denominator becomes honest, and ~8 minutes come off a 60-minute run). It
requires no board, and doing it *before* the retrofit means 19 fewer ids to write falsifiers,
effects and `reads:` for — which is ~2 days saved on R9/R16/R1 alone.

### 3.2 The realistic path for the other ~195

Not a sweep, and not the mode table's four categories either. Family by family, in this order,
because the order is dictated by which families block the class-order switch and which are cheap:

1. **The gating set first (43 CORE + HEALTH + RIG).** Bounded, and it is the exit criterion for
   TASK-617. R35 reasons, R36 offline check, R28's UNMET, R37's flake cross-check. ~4 days.
2. **LocalPlayer next**, because it is 77 % SOUND and has real observables (`get player`,
   `get plOrder`). It is the family where the declarations will be true, so it calibrates the
   authoring cost honestly before the hard families set the expectation. ~3 days for 31 bodies.
3. **Stock and shell** — the two big files (1 495 and 3 528 lines, 86 and 80 `skip()` sites). These
   are where the retrofit money goes. ~10 days.
4. **WebRadio, PlaneRadar, Teletext.** ~5 days.
5. **Clock last, and only after ADR-B.** Retrofitting declarations onto 14 ids that will be deleted
   or rewritten by R5 is pure waste. Clock is not a migration, it is a rewrite, and pretending
   otherwise puts 14 ids' worth of false progress on the ratchet.

The mode table's `new-only` category is the one I trust least. `new-only` means "the rule applies to
tests written or touched from adoption", and in a suite where a family module is 3 528 lines, "touched"
is ambiguous enough that it will resolve to "the function I edited" and never propagate. If a rule is
new-only, the gate must be diff-aware and must say so; otherwise it is aspiration.

### 3.3 What must be deleted rather than migrated

Full list and reasoning in §8. Summary: of the 14 BROKEN and 21 HOLLOW ids, **19 should be deleted
outright**, **8 should have their bodies deleted and their claims carried as R4 `UNOBSERVABLE`
records**, and **8 should be kept and fixed**. That is 27 bodies removed from a 213-id registry.

The principle I am applying, and I would like it written into the requirements: **a test that cannot
be made to fail for the right reason is worth less than nothing, because it consumes a suite slot,
inflates a coverage denominator, and occupies the attention of everyone who reads the registry
looking for the test that covers a behaviour.** Four of the deletions are literally the same body
with one app name changed, asserting one string literal produced by one line of firmware
(`cmdTouch.cpp:141-144`). Migrating four copies of that — four falsifiers, four effect declarations,
four `reads:` records — is 40 minutes spent making a duplicate look rigorous.

---

## 4. Host-side transcript mutation (R10)

**Verdict: the idea is right, the "always on, every id" scope is wrong, and the mechanism as
specified has a hole big enough to make the job report success vacuously — which is the exact
failure (`F-15`) it exists to prevent.**

### 4.1 Does it work for tests that branch on earlier replies?

Not as a transcript. A recorded transcript is an ordered list of replies; these bodies are not
straight-line. `clock.py:160-171` is typical:

```
if not _switch_to_clock(dut):        # branches on a reply
    fail(tid, ...); return
dut.cmd("set clockStyle vfd")
r = dut.cmd("get appId")
if r.get("id") != 1: fail(...)
```

Mutate `get appId`'s `id` and the body takes a different path — fine, that is the point. But mutate
anything read *earlier*, or mutate a field in a family whose helpers branch (`_switch_to`,
`_wait_chart_complete`, `_tb_set_offset`, `_stock_ok_count`), and the body issues a command the
transcript does not have a reply for. Three consequences the requirement does not address:

1. **The store must be keyed, not positional** — `(command string, nth occurrence) → reply`. That is
   buildable; `Dut.cmd` (`lib/dut.py:1120-1136`) is the one choke point and a recording wrapper is
   ~50 lines. But `send()`/`read_json()` are also called directly in the suite, and
   `drain_log_lines` reads unsolicited lines with no command at all — those need a second, unkeyed
   channel.
2. **A transcript miss is not a falsification.** If the replay raises "no recorded reply for
   `get chartSymbol` #3" and the harness records that as a FAIL, the mutation job reports the test
   as falsifiable when what actually happened is that the recording was incomplete. **Every id whose
   mutation run ends in a transcript miss must be reported as `INCONCLUSIVE`, never as a
   confirmation**, and the count of inconclusive ids must be in the summary. Without that clause R10
   is a machine for generating a 100 % AC4 figure that means nothing.
3. **Mutation proves that *some* field matters, not that the *right* one does.** `set X 5; get X == 5`
   is perfectly falsifiable — the VE says so in §5's "honest boundary" and is right — so a green
   mutation result on a HOLLOW id is the expected outcome, not a bug. **Amendment (R10a): the job
   must run a control arm.** Mutate the key the falsifier names → expect FAIL. Mutate a key the test
   reads but should not depend on → expect PASS. An id that fails under *both* is reading its input
   too broadly and is reported. That second arm is what makes the mechanism say something about
   vocabulary rather than only about reachability, and it costs one more replay per id.

### 4.2 What fraction of the 216 is replayable at all?

Measured, by family (`grep -c` over `app/tools/suite/serialdbg/`):

| Family | Bodies | Log-draining sites | Sleeps | Replayable in principle |
|---|---|---|---|---|
| clock | 14 | 0 | 20 | high |
| teletext | 8 | 0 | 7 | high |
| planeradar | 9 | 0 | 13 | high |
| stock | ~30 | 0 | 78 | high, but 86 `skip()` exits make most mutations no-ops |
| webradio | 28 | 7 | 28 | medium |
| player | 31 | 10 | 24 | medium |
| shell | 51 | 12 | 67 | medium |
| health | 3 | 4 | 2 | low |

Log-draining bodies (~33 sites) need the unkeyed second channel and a virtual clock. Interactive
ids (`T093` and `T095` both call `input()`) are not replayable at all. Ids whose oracle *is* elapsed
time are not replayable once `time.sleep` is stubbed — and it must be stubbed, because 253 sleeps is
~100 s of pure sleeping per pass and the job runs ≥ 2 passes per id.

**My estimate: ~150–165 of 213 are mechanically replayable (70–77 %), and ~120 of those produce a
mutation result that means anything** — the rest exit through a `skip()` before reaching the mutated
field. AC4's "≥ 90 % host-replayable confirmed" is therefore not reachable against the current
corpus; it becomes reachable only after R28's skip reclassification and the deletions, and the
requirement should say so instead of asserting a number.

### 4.3 Is the recording infrastructure there, and what does it cost?

**It is not there at all.** There is no transcript, no fixture format, no stub transport in `lib/`.
The precedent the requirement cites — `run/player-gate --selftest` and the `gate/` negative suites —
is a stubbed *serial line*, not a recorded session, and it is per-test hand-written. And 19 files
call `serial.Serial(` directly, four of them whole `SerialDut` clones, so **nothing bypassing
`lib/dut.py` is recordable until R47 lands.** That ordering constraint is not in §14 either.

Cost, as an implementer:

| Piece | Days |
|---|---|
| `lib/replay.py` — stub transport, keyed store, virtual clock, `TranscriptMiss` | 3 |
| recording wrapper on `Dut.cmd`/`send`/`read_json`/`drain_log_lines`, behind an env flag | 1 |
| `runner.py --mutate` driver, per-id, with the control arm | 1.5 |
| negative test: break the mutator, assert it reports zero falsifications | 0.5 |
| the recording pass itself | ~2 board-hours, blocked while the board is pinned |
| **total** | **~6 d + board time** |

Plus a maintenance cost the document does not mention: **transcripts rot.** Any firmware change to a
reply shape invalidates them, and the job then goes red for a reason that has nothing to do with the
tests. Mitigation: stamp each transcript with R30's ELF hash and treat a stale transcript as
`INCONCLUSIVE` with a re-record instruction, never as a failure. Otherwise the first firmware commit
after this lands turns the mutation job into noise, and noise on a gate is how C3 got where it is.

### 4.4 Verdict

**AMEND.** Accept the engine and the always-on host-only job. Reject "every id with a replayable
falsifier" as a day-one scope — make the *recorded set* the ratchet, start with the ~35 ids of the
LocalPlayer and Clock families, and require: keyed transcripts, `INCONCLUSIVE` for transcript
misses, the control arm (R10a), and ELF-stamped transcripts. Engine in `lib/`, driver in
`runner.py --mutate` — I agree with the Architect's placement but **not with his reason**: he argues
a gate may not import `suite/`, and `gate/check_test_meta.py:49` already does exactly that as a
blocking gate in `run/check`. The real reason to put the driver in the runner is that it needs the
runner's selection, ordering and reporting, not that `gate/` is forbidden from importing upward.

---

## 5. What will rot

I have watched this project's gates. `run/check` has 11 and its whole value is that a developer
actually runs it. `check_docs` has 6, and **C3 has been advisory with a standing failure count for
months** — while `check_docs.py:528` contains, in its own source, the sentence "advisory failures
are scrolled past, which is the exact mechanism by which 'covered' and 'green' got conflated". The
file knows. The gate is still advisory.

Six things will be quietly abandoned within two quarters:

| What | Why it rots | What would make it stick |
|---|---|---|
| **R44** threshold citations | > 1 000 sites, ratchet with no completion condition, and the VE grades it a SHOULD in the same breath as admitting it can never be retrofitted. This is C3 with a different subject | Cut it. Or scope it to *assertion thresholds in the 43 gating ids* — bounded, ~40 literals, finishable in a day |
| **R1's `oracle_reason`** | Free prose, "by review", and the review is the same person who wrote the test | The `claim_class` enum in §2.2. Enum + generated `reads:` covers the mechanical majority; only then is the residue small enough that a human reads it |
| **R23 / AC11's ≤ 25 sleeps** | 253 today, an undecided target, and several removals are blocked on observables that do not exist. It will stall around 200 and stay there | Derive the target: classify all 253 mechanically (post-tap settle → R27's `skipped` flag; pre-`get` settle → `wait_until`; physical → keep and cite), publish the counts, then set the number to the physical count. Until then the ratchet has no floor and a ratchet with no floor is a slogan |
| **R11's quarterly campaign** | The VE says out loud it is the first thing dropped under time pressure, and grades it SHOULD *for that reason* — which guarantees the outcome | The expiry mechanism from §2.2: an unexecuted `falsifier_physical` past its `review_by` is a gate failure. `flaky.yaml` proves this works in this repo |
| **R20 / AC13's three shuffled runs** | ~3 board-hours on a one-board rig, competing with actual development | Per-family shuffle inside the family's own budget, run automatically whenever that family's file changes. A 5-minute shuffle that runs 30 times beats a 3-hour one that runs once |
| **R52 fixture declarations** | The format is explicitly undecided, so it starts as prose in a docstring | Decide the format or drop the requirement; an undesigned declaration is a comment |

The general rule I would put in the document, since it is the one thing my experience here says
loudest: **do not land an advisory gate.** Land it blocking with a dated exception ledger that can
only shrink — C6's pattern, which reads 0 unexcepted today and works. An advisory gate with a
standing failure count is worse than no gate, because it manufactures the impression of coverage
while training everyone to scroll past a red line. C3 is the proof and it is in this repo.

Second rule: **the ratchet count must be printed by the thing developers already run**, not stored
in a doc. If the sleep count and the mirror count are lines in `run/check`'s output, they move. If
they are rows in `M-HARNESS2-requirements.md` §13, they will read 253 and 9 in a year.

---

## 6. What is missing that I would need

Six developer-experience requirements the document does not have. I would not start without D1, D3
and D6.

**D1 — a test must be runnable without a board. MUST.** Today the cheapest way to see whether a body
is syntactically alive is a port open, which resets the DUT (~15 s good boot, up to ~60 s degraded).
Once R10's replay engine exists, `runner.py --replay <id>` costs milliseconds and needs no hardware.
That single affordance changes the economics of every other requirement in the document — it is how
an author iterates on a falsifier declaration without spending board time — and the VE proposes the
engine for verification purposes only, never noticing it is also the development loop.

**D2 — the artifact records whether a verdict came from an isolated run or a full session. MUST.**
This project has a recorded lesson that an isolated `run/test-targeted` rerun cannot prove a
suite-order bug is gone, because it always cold-boots. R30's premise fields include the entry point
but not this distinction, and the three armed-injector clusters (`F-4`, `G-1`, `H-1`) are exactly
the class of defect that an unlabelled isolated PASS hides. One field.

**D3 — a FAIL carries the last N commands and replies. MUST.** Mode P (TASK-571) already attaches
health, phase and generation to every FAIL. The missing half is the transcript: today, diagnosing a
failed id means re-running it on the board, which cold-boots and often does not reproduce. Once
R10's recorder exists (§4.3), a ring buffer of the last 20 command/reply pairs in the FAIL record is
nearly free and is the largest single reduction in board time in this whole programme. It is not in
the document.

**D4 — the record is scaffolded, not typed.** See §2.3. `run/new-test` emitting `reads:`, `effect`
and `scope` pre-filled. Half a day. Without it, R9/R16/R35 are a 45-minute tax per test and authors
will write "mutate the reply" 213 times.

**D5 — every gate and every host job runs with no board, and `run/check` proves it.** R48 gets most
of the way; the requirement should be stated positively, because the current state is that a pinned
board blocks all test work, which is why WP-Z's 80-minute session and this entire review had to be
static.

**D6 — a host-gate wall-clock budget. MUST.** The Architect raised this as omission 4 and I am
seconding it as a requirement, not a note. The document budgets DUT seconds to the second (§12) and
proposes roughly **fifteen new host gates** while saying nothing about the gate a developer runs
before every commit. `run/check` is 11 gates today. **≤ 90 s for `run/check`, ≤ 15 s for
`check-docs`, measured and reported by the scripts themselves.** A gate suite that takes four
minutes is a gate suite people stop running, and then all fifteen of the new ones are worth nothing.

**D7 — there must be a sanctioned way to delete a test id.** This is the omission I care about most,
because its absence is *visible in the corpus*: three registered ids whose entire body is one
`skip()` (`T136`, `T171`, `T179`), and `T136`'s archived plan entry still reads `Status: pass` for a
test that has not executed an assertion since May. Someone did the right analysis, could not delete
the id, and left a stub. The procedure is small — remove the registry entry, remove or strike the
`test_plan.md` row, add a dated retirement row to the ledger C6 already parses, regenerate the
coverage figure — and without it R34's "an id that cannot produce a verdict is not coverage" has no
disposal path and will be satisfied by writing skip-only bodies with a comment.

**D8 — a gate failure names the file, the line and the fix.** Fifteen new gates whose output is a
count and a rule number is fifteen new reasons to add an exemption row rather than fix the defect.
`check_docs`'s failure lines (`rel:lineno: <what> -> <why>`) are the house standard; hold the new
ones to it.

---

## 7. Disputed requirements

Verdicts on the 16 rows I engage with substantively. The remaining 39 I accept, several with the
comments in §7.2. Where the Architect already amended a requirement, my verdict is on **his amended
form**, and where I disagree with him I say so.

| Req | Verdict | Objection (one sentence) | Amendment I would accept |
|---|---|---|---|
| R1 | **AMEND** | The author declaring `reads:` adds a place to be wrong to a fact the gate must parse anyway, and `oracle_reason` is free prose reviewed by the person who wrote it. | Generate `reads:` from `_reachable_source()`; the author declares a `claim_class` from a closed enum (`time｜order｜render｜fetch｜state｜identity`) and the gate cross-checks it against the generated key set. |
| R3(a) | **REJECT** | Concur with the Architect: thirteen app-authored identity keys can each be wrong in the way the test is trying to detect. | His console-level refusal guard plus one generated conformance row. |
| R3(b–d) | **AMEND** | The Architect's re-seat is right, but the admission rule must not switch on before the shell half lands or thirteen apps go red for a reason no test author can fix. | Land the shell half first; the per-app admission rule activates per app, as that app's keys land, with the `UNOBSERVABLE` ledger carrying the interval. |
| R5 | **AMEND** | Accepting the GRAM-readback re-specification, it is still a MUST that cannot be met until ADR-B is taken and `set now` exists, and the Clock ids it "fixes" are new ids, not migrations. | Grade R5 MUST-on-adoption-of-ADR-B; state explicitly that the Clock family is rewritten, not migrated; add read duration to `get sig`'s reply so a degrading MISO shows up as a trend before it shows up as a false FAIL. |
| R6 | **AMEND** | Concur with the Architect: a MUST enforced by "a review item" fails the document's own §1 standard. | His R6a MUST / R6b SHOULD split. |
| R8 | **DEFER** | Firmware on a static pool measured at 0 B in July, for a benefit the requirement itself says is unmeasured. | Defer until an incident search names one multi-hour soak bug this surface would have converted to a fast test. |
| R9 | **AMEND** | A single prose `falsifier` field is a lie surface, and the document has a proven anti-lie mechanism ten metres away in `flaky.yaml`. | Split into executable `falsifier_replay` (key, mutation, expected verdict — checked every run) and `falsifier_physical` (action, owner, task, `executed_on`, `review_by` — expiry is a gate failure, exactly as `results.py:193` treats an expired flake). |
| R10 | **AMEND** | "Every id with a replayable falsifier" is not reachable against a corpus where a transcript miss is indistinguishable from a falsification. | Keyed transcripts; `INCONCLUSIVE` for a transcript miss, never a confirmation; the R10a control arm; ELF-stamped transcripts; the recorded set is the ratchet, starting at LocalPlayer + Clock. |
| R16 | **AMEND** | "A declaration stronger than the behaviour is allowed and never failed" means `effect: resetting` everywhere passes forever, and R14/R17/R19 then key off a constant. | Fail a declaration that has been stably stronger than the observed effect across three archived runs; the artifact already holds the observations. |
| R17 | **AMEND** | A static "every `set` has a matching restore on every exit path" gate over 11 900 lines with six-deep helper transitivity will be mostly false positives, and a gate people mute is worse than none. | Gate on *use of the context manager* — mechanical, unfoolable, already the in-tree pattern at 20 of 41 sites — plus R14's boundary check to catch what static analysis misses. |
| R20 | **AMEND** | Concur with the Architect, and add: three consecutive full shuffled runs is ~3 board-hours that will happen once. | Capability MUST, campaign SHOULD; per-family shuffle triggered by a change to that family's file, cross-FEATURE only after family-level runs come back clean. |
| R22 | **AMEND** | The elapsed-reporting half needs a shared `wait_until()` that does not exist, so the requirement silently contains WP-Z TASK-607. | Name `wait_until()` in `_helpers.py` as the prerequisite and land it first; the gate follows it. |
| R23 | **AMEND** | AC11's ≤ 25 is a round number in a document whose stated discipline is that every number is measured, and some removals are blocked on observables that do not exist. | Classify all 253 sleeps mechanically first (post-tap settle, pre-`get` settle, physical), publish the three counts, then set the target to the physical count. |
| R24 | **AMEND** | 727 literals is a separate mechanical sweep from R23's semantic one and will be scheduled as one job and finished as neither. | Fold the *counting* into R23's census and schedule the sweep as its own bounded task; the overwhelming majority are exactly the default and are a `sed`. |
| R28 | **AMEND** | The vocabulary is right; the migration of 262 `skip()` sites into SKIP vs UNMET is 5 days of per-site judgement and is not host-only-cheap. | Land the enum and `UNMET` in increment 1; reclassify only the 31 CORE skip sites there; the remaining 231 default to SKIP and become a ratchet. |
| R42 | **AMEND** | The `(suite symbol, firmware symbol)` pair register is itself a hand-maintained mirror — the failure mode it exists to prevent. | Generate the pairs wherever the firmware symbol is already in `app/gen/`; cap the hand-written list and require a reason per hand-written pair. |
| R53 | **REJECT** | A MUST that is "reported, not failed" is not a MUST, and the table's numbers are undeclared as derived — the APP ≤ 6 min row in particular, against a rig where one cold app switch measured 2.06 s busy→idle. | Concur with the Architect: fold the per-class elapsed measurement into R30 as a MUST, keep the budget table as a SHOULD-grade target, derive or drop the APP row. Add: FEATURE ≤ 45 min is unreachable until the deletions and duplicate-precondition collapses land, so the table is a post-condition of the programme, not a requirement on it. |
| R54 | **AMEND** | The second clause ("no second id may pay a precondition a first has already paid") is a review item by the document's own admission and is sometimes wrong — independence is occasionally worth a duplicate wait. | Mechanise it as a per-run report of repeated command prefixes across ids (free once R10's recorder exists) and drop the MUST on the human half. |
| R44 | **DEFER** | > 1 000 literals with no completion condition; this is `check_docs` C3's exact shape and will read the same number in a year. | Defer; or re-scope to the ~40 assertion thresholds inside the 43 gating ids, which is finishable in a day and covers the bounds that can actually block a run. |
| R26 | **DEFER** | Concur with the Architect. | Defer to a joint ADR with R25; do not build before the correlated-reply ratchet is complete. |

**Counts, over 56 rows (55 requirements, with R3 split as the Architect split it):
ACCEPT 35 · AMEND 16 · REJECT 2 · DEFER 3.**

### 7.1 Where I disagree with the Architect

Three places.

**On R10's placement, the reason is wrong even though the conclusion is right.** He argues a gate may
not import `suite/` because "nothing depends on `gate/`. A gate is a leaf." But
`gate/check_test_meta.py:49` imports `suite.serialdbg` today, as a **blocking** gate in `run/check`
— the M-TOOLING rule says nothing may depend *on* `gate/`, not that `gate/` may not depend on
anything. If we are going to cite the dependency rule at a new mechanism, we should first say
whether the existing blocking gate violates it. My own reason for putting the driver in
`runner.py --mutate` is simply that it needs selection, ordering and reporting, all of which live
there.

**On R51, verify-and-refuse is right and it is not free.** He calls it "smaller than the flag". It is
smaller in concept and larger in diff: `run/test` and `run/test-targeted` currently own a
trap-guarded flash lifecycle, and removing it means every caller who relied on the restore learns
about it the hard way — including the documented workflows in `CLAUDE.md`. Budget 1.5 days and a
`CLAUDE.md` update, not an afternoon, and land it with the recorded hazard restated: never kill a
`run/flash*` or soak script mid-flight.

**On R5's affordability, the flash number is right and the *time* number is the one to watch.** His
readback arithmetic (~69 ms for a 120×60 region) is per signature. A Clock family that samples three
times across an animation window, across 14 ids, plus a `colorprobe` liveness check per session, is
tens of signatures per run. That is still small — but the requirement should carry a per-id
signature budget the way §12 carries a per-class one, or the family that is 7 % SOUND becomes the
family that is 6 minutes long.

### 7.2 Accepted with comment

* **R48** — I agree with the Architect that this is the strongest requirement in the document, and I
  will go further: it is the only one I would land unilaterally, today, with no ADR and no
  discussion. Six `__main__` guards.
* **R4** — the requirement that licenses my delete list. `UNOBSERVABLE` is what lets us remove a body
  without losing the claim, which is the thing that has been missing (D7).
* **R14** — cheapest firmware ask in the document, but note it depends on a **generated injector
  list** that does not exist: `gen_get_keys.py` enumerates `get` keys only (and, per `A-3`, only 43
  of 71+ of those). Budget the `set`-side generator, not just the bitmask.
* **R18** — the 98 measured `.get("key", <literal>)` sites make this the most mechanically
  satisfying requirement here: one accessor, one regex gate, a countable ratchet, and `G-2` is a
  live wrong-verdict across nine ids.
* **R29/R30/R31/R33** — accept without reservation. This is the increment I would build first and
  the only part of the document that pays for itself in the first month.
* **R36** — "a network outage must not be able to declare the firmware untestable" is the right
  sentence and it is also the exit criterion for TASK-617; I would not let the class-order switch
  flip without it.
* **R46** — accept, and note the mechanism is nearly free: `check_docs.py`'s C6 already keys entries
  by id at `:659-676`.

---

## 8. Delete, do not migrate

Of the 35 ids the M-TESTQUAL audits graded BROKEN (14) or HOLLOW (21), **27 bodies should be
removed**: 19 deleted outright, 8 retired to an R4 `UNOBSERVABLE` record. Eight are worth fixing.

Every row is the audit's own finding — I have re-read the cited evidence and am proposing the
disposal, which is the part the audits deliberately left open. Ids are written in the body of each
row rather than in a leading table cell so that `check_docs`' id binder does not treat this review
as a declaration.

### 8.1 Delete outright (19)

1. **T136** — body is one unconditional `skip()`; the assertion already lives in T137's
   precondition. Delete the registry entry and correct `test_plan-archive.md:1453`, which still
   reads `Status: pass` for a body that has not executed an assertion since May. (`D-4`)
2. **T171** and 3. **T179** — bodies are one `skip()` each, honestly labelled `[MANUAL — pixel
   verification required]`, counted in the 213-id total and in `--scope Stock`'s 30. If ADR-B lands,
   these come back as *new* ids against `get sig`; they are not migrations. (`G-16`)
4. **T_GOL_02**, 5. **T_WX_02**, 6. **T_CX_02** — three verbatim copies of T_MA_02 with one app name
   changed, all asserting one string literal produced by one firmware line
   (`cmdTouch.cpp:141-144`), on a branch the test's own precondition selected. Keep T_MA_02, delete
   the three copies. (`D` §HOLLOW rows)
7. **T_GOL_03**, 8. **T_WX_03**, 9. **T_CX_03** — three copies of T_MA_03's "Spotify repaints after
   switch-back" claim, none with a reachable `fail()`, all excusing the regression they exist to
   catch as "Spotify not rendering (not playing?)" — an excuse WP-D disproved
   (`SpotifyApp::resume()` calls `invalidatePlaylist()` regardless). Keep T_MA_03 and re-aim it at
   an ink-count signature under R5. (`D-2`)
10. **T172** — the fifth copy of the same residue claim, in the Stock family, wrongly scoped, whose
    failure path is also a `skip()`. Covered by the one surviving copy. (`G`, `D-2`)
11. **T_WR_ERR_01**, 12. **T_WR_ERR_02**, 13. **T_WR_ERR_03**, 14. **T_WR_ERR_04** — four
    `set wrState N` / `get wrState == N` tautologies sharing a teardown that writes `ERROR_WIFI`
    believing it is `STOPPED`, parking the app in an error state ahead of six ids whose oracle is
    `wrState == 2`. Delete all four and file one new id that drives a real error path through the
    dead-URL injector and reads the resulting state. (`F-1`)
15. **T178** — asserts `chartLen == 0` and `fetchFailed == false`, both of which its own
    `set triggerFetch 1` wrote (`stockApp.cpp:225-226`), with no firmware transition interposed.
    This is R2's canonical violation and there is nothing to migrate. (`G`)
16. **T185** — clears its own error with `set triggerFetch 1` before any fetch is enqueued, and
    never re-reads `fetchFailed`. The claim is unrepresentable in this construction. Re-file as a
    new id that never writes the field it asserts on. (`G`)
17. **T_PLR_02** — three rounds of `set playerMode X` / `get playerMode == X` for a claim about
    persistence *across reboot*, with no reboot. The real test needs `Dut.reboot_and_wait` (`H-17`)
    and is a new id. (`E`)
18. **T194** — the claimed behaviour is unobservable by construction: `drillTo()` assigns
    `chartSymbol[0] = '\0'` unconditionally (`stockChart.cpp:75`), so the subsequent list drill
    produces an index-keyed ticker whether or not `backToPrevView()` cleared it. Its one `fail()`
    compares a value with itself. Nothing can fix this id short of a different claim. (`G`)
19. The **registry copy of T_PLR_25** — a deterministic 60 s false red on the only env that
    dispatches it, while the standalone body owns the id and the player gate's pass set already
    assumes so. Delete the registry entry, port the two things the copy does better, keep the
    standalone. (`E-2`, already WP-Z TASK-586)

**Effect on the numbers**: 19 ids off a 213-id registry (−8.9 %), AC5 moves to 0 for the skip-only
half, and roughly 8 minutes come off a full run (T_PLR_25's 60 s, T185's 65 s wait, the four
`T_WR_ERR_*` and their teardown, T178's fetch cycle, six duplicate app-switch round trips).

### 8.2 Delete the body, keep the claim as `UNOBSERVABLE` (8)

These claims are real and the observable does not exist. R4 is precisely the mechanism for them, and
the important half is that **the body goes** — an `UNOBSERVABLE` record with a live green body still
prints green, which is exactly how `H-2` booked five milestone criteria.

* **T078** — "a zero-delta drag does not commit `ACT_VOLUME`". The claim is right; the marker it
  needs does not exist and the body defers to a human via `print()`. Ledger it, name the missing log
  marker, delete the body.
* **T_CLK_02**, **T_CLK_08**, **T_CLK_09**, **T_CLK_13**, **T_CLK_14** — five visual clock claims
  whose oracle is a settings byte. These are the family at 7 % SOUND and they are the reason ADR-B
  exists. Ledger all five against the `get sig` task; delete the bodies; re-file as new ids when the
  mechanism lands. Migrating them first would put five falsifier declarations on the ratchet for
  bodies that are about to be rewritten.
* **T_WR_VOL_03** — asserts `wrState == 2` for a claim about a volume cap, with the pass detail
  stating the reasoning instead of asserting it. The observable (`webRadioMaxVolume` readback) is a
  four-line `dbgGet` case; ledger it against that task.
* **T093** — a CORE id whose only machine assertion is that `set backoff 5` returned `ok`, with two
  `input()` prompts for the rest. Two disposals in one: **demote it out of CORE** (it cannot satisfy
  R36 and it cannot run unattended) and move it to an interactive-only registry. A CORE id that
  requires a human at the board is a veto held by nobody.

### 8.3 Keep and fix (8)

Named so the list above is not read as "delete everything the audit criticised".

* **T-BUSY-05** — an inverted guard; one predicate. Fix, then re-run: the cell has been green on an
  untested path for its whole life.
* **T-UART-01** — cannot observe garbling because `read_json` swallows the malformed line. Fixable
  **only** by R25; it is the one id whose value is unlocked by the correlated-reply work, and it
  should be cited as R25's justification.
* **T_WX_04** and **T_CX_04** — dead by position, not by construction; their oracles are real and
  their fields exist. Fixed by an order adjudication or a `set weatherReady 0` reset.
* **T182** — no reachable `fail()`, but it is the Stock family's only taskbar cross-feature test and
  the only place in the file that computes a slot from the generated registry instead of typing it.
  Rewrite the three `skip()` exits as `fail()`; do not delete.
* **T_MA_02** and **T_MA_03** — the surviving representatives of the two duplicate clusters above.
* **T_PLR_03** — the leak assertion cannot fail because of the modulo arithmetic at the two chosen
  offsets. Choose offsets that *could* select an eject-only app and it becomes a real test.

---

## 9. What I would build first, in two weeks

Ten working days, one engineer, **no DUT** — because the board is pinned and because everything
below is deliberately host-only, which means TASK-618 is not a blocker for any of it. Each day names
its deliverable and its check.

**Day 1 — the free wins.**
`__main__` guards on the six modules that run their suite at import, plus the import-in-subprocess
gate with a stubbed `serial` (R48). The one-word glob fix in `gen_get_keys.py` so it sees `.cpp`
bodies (R7, WP-Z TASK-600) — expect the key count to jump from 43 toward 71+ and expect new unknowns
in `run/task488`. The flake-registry × gating-class cross-check (R37). *Check*: `run/check` green,
AC16 = 0.

**Days 2–3 — the verdict type (R28 core, R31, R38).**
One module owns the verdict enum; `PASS｜FAIL｜SKIP｜UNMET｜NOT-RUN｜FLAKY-PASS｜ORDER-DEPENDENT`.
`RESULTS` holds typed values, not formatted strings. `_gate.py:129`'s `startswith("FAIL")` becomes a
type test, and `UNMET` blocks exactly as `FAIL` does. Extend the inversion selftest with an `UNMET`
arm that asserts the **absence** of any other verdict among the blocked ids, not merely the presence
of `NOT-RUN`. *Check*: negative suite, in the `gate/` pattern (BP-068).

**Days 4–5 — the artifact (R29, R30, R53's measurement half).**
Schema-versioned JSON sidecar: per id — id, cls, scope, effect, verdict, reason, start/end, elapsed,
boot generation, falsification status; per run — firmware ELF hash and build id, harness version,
entry point, flake-registry hash, downgraded gates, per-class elapsed, and D2's isolated-vs-session
flag. Move all three summary parsers onto it, starting with `run/player-gate`'s `sed`. *Check*:
schema negative test; `grep` for summary parsers reads 0 (AC10); TASK-573's defect class is retired.

**Day 6 — the deletions (R34, R4, D7).**
AST gate for "no reachable `fail()`". Delete the 19 ids of §8.1; retire the 8 bodies of §8.2 into an
`UNOBSERVABLE` ledger in `id_binding_exceptions.md`'s shape; correct `test_plan-archive.md`'s stale
`Status: pass`; regenerate the coverage figure from C6's binding data. Write the deletion procedure
into `docs/process/` — that is D7 and it is thirty lines. *Check*: AC5 = 0; the id total is honest.

**Day 7 — the CORE audit (R35, R36).**
Write the 43 CORE reason strings; gate on an undeclared gating class; demote the seven single-app
Stock CORE ids whose precondition is a live HTTPS fetch, plus `T133`'s host-file grep, out of CORE.
This is WP-Z TASK-591 and it is the exit criterion for TASK-617. *Check*: AC8 = 43/43; no CORE id
needs the network.

**Day 8 — effect, honestly (R16, R14's host half).**
`persisting` added to the enum; the 213 declarations confirmed rather than seeded; the boundary
check computes observed effect from the artifact (settings hash, entry app, reboot marker) and fails
a declaration weaker than the behaviour — plus §2.2's three-run rule against over-declaration. The
firmware `get armed` key is left as a stub the harness tolerates, so none of this waits on a board.
*Check*: AC9 = 213/213 with 0 weaker-than-observed.

**Day 9 — typed reads (R18).**
`Dut.get_int` / `get_str` distinguishing "the device answered X" from "the device did not answer";
the gate forbidding `.get(<key>, <literal>)`; convert the nine Stock ids behind `_stock_ok_count`
first, because `G-2` is a live unconditional pass. *Check*: 98 sites become the ratchet count and it
starts falling.

**Day 10 — replay, one id end to end (R10's recorder half).**
`lib/replay.py`: stub transport, keyed `(command, nth)` store, virtual clock, `TranscriptMiss`.
Recording wrapper on `Dut.cmd` behind an env flag. One replayed id, no board — a hand-written
transcript for a pure cmd/reply body is enough to prove the engine. The negative test lands the same
day: break the mutator, assert it reports **zero** falsifications rather than passing vacuously.
*Check*: `runner.py --replay <id>` runs in milliseconds with no serial port, which is also D1.

### What I deliberately do not do in the two weeks

No firmware — the board is pinned and every firmware item needs a freshly derived `.map`. No R23,
R42 or R44 sweeps — those are the ratchets and starting them early produces motion, not progress.
No R25, no R5, no R3: all three are gated on ADRs that have not been taken, and starting them before
the decision is how a rejected design gets defended.

### What is true at the end of day 10

Four of the sixteen acceptance criteria met without touching a board — AC5 = 0, AC8 = 43/43,
AC10 = 0, AC16 = 0 — a typed result artifact every consumer reads, 27 fewer bodies in a registry
that now counts honestly, and a replay loop that lets the next 140 days of retrofit happen without
queuing for the DUT. That last one is the reason day 10 is where it is: everything after it is
cheaper because of it.

If the answer to "may we spend two weeks" is "no", the irreducible core is **days 1, 2–3 and 6** —
four days that delete a class of false verdict, retire 27 bodies that assert nothing, and make the
gate block on a type instead of a string prefix. I would not build anything else in this document
before those.
