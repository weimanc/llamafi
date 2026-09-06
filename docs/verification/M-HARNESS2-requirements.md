# M-HARNESS2 — requirements for a test harness with a sound foundation

> Owner: **Verification Engineer**
> Status: proposed
> Written: 2026-09-03
> Parent: [M-TESTQUAL index](reviews/M-TESTQUAL-index-review.md) ·
> [WP-Z consolidated findings](reviews/M-TESTQUAL-Z-findings-review.md)
> Builds on: [M-TESTARCH test architecture](../architecture/designs/M-TESTARCH-test-architecture.md),
> [M-TESTARCH precedence hierarchy](../architecture/designs/M-TESTARCH-precedence-hierarchy.md),
> [M-TESTBASE phase 1](../architecture/designs/M-TESTBASE-phase1-player-gate.md),
> [M-TOOLING](../architecture/designs/M-TOOLING-host-tool-architecture.md)
> Method: static only. No DUT, no serial port, no flash — the board is pinned to the `-DBOD_WATCH`
> debug build for TASK-557. Counts below were re-measured on the working tree; commands are given.

This is a **requirements** document. It says what must be true of a test harness for this project;
it does not say how to build one, and it does not schedule anything. Someone else owns the design.

Two things it is deliberately not. It is **not a restatement of the 130 M-TESTQUAL findings** — those
are defects with named fixes, and fixing all 130 would leave the mechanism that produced them intact.
And it is **not a rewrite proposal**: every requirement below carries a migration mode, and the ones
that cannot be reached incrementally are named as such in §14 rather than smuggled in as requirements.

---

## 1. How to read this

Each requirement is one row of prose with four parts:

* **Statement** — one sentence, MUST or SHOULD.
* **Rationale** — traceable to an M-TESTQUAL finding key (`A-7`, `C-5`, `F-4`, theme `T3` …, all in
  [WP-Z](reviews/M-TESTQUAL-Z-findings-review.md)) or to a named project constraint.
* **Verification** — how we check the *harness* meets it. Every one is mechanical or a counted
  measurement; "by review" appears three times and each is flagged as a weakness.
* **Priority** — **MUST** (the foundation is unsound without it) or **SHOULD** (materially better).

The split is **37 MUST / 18 SHOULD** across 55 requirements. Where a requirement was tempting to grade
MUST and is not, the reason is stated in place — a document where everything is a MUST has not made
a decision.

Requirement ids `R1`…`R55` are stable and grouped; the group letters are mnemonic only and carry no
ordering. Ids are never renumbered — a superseded requirement is struck and kept.

**On evidence.** Every count in this document was measured, not carried over. The three used most:

```sh
grep -rho "time\.sleep(" app/tools/suite/serialdbg/ | wc -l          # 253
grep -rho "skip("        app/tools/suite/serialdbg/ | wc -l          # 262
grep -rho "timeout=[0-9]" app/tools/suite app/tools/lib | wc -l      # 727
```

and the taxonomy census, via the one import the constraints allow
(`suite.serialdbg.build_all_meta`): **213 registry ids**, `cls` declared on **6**, `scope` on **57**,
`effect` on **3**, and **0 of the 43 CORE ids declared** — all seeded by `_meta.py` defaults.

---

## 2. Assumptions

These are load-bearing. If one is false, the requirements resting on it need re-deriving.

| # | Assumption | If it is wrong |
|---|---|---|
| A1 | The serial debug console (`app/src/debug/serialConsole/`, `SERIAL_DEBUG`-only) remains the **only** test API for anything on the device. | The observability contract (§4) is the wrong shape; a second channel changes it. |
| A2 | There is **one** DUT and it is serialised. A second board is costed but not bought (M-TESTARCH §10 OQ-D / TASK-550, with TASK-552 as its two known blockers). | The cost budget (§12) relaxes by roughly 2×; nothing else changes. |
| A3 | No host C++ toolchain exists on this machine (`gcc-c++` absent, no `sudo`), so the T1 host-unit tier stays blocked (M-TESTARCH §10 OQ-A). | A large share of FEATURE assertions leave the DUT entirely and §12's budget stops being the binding constraint. |
| A4 | The debug build is the memory-constrained one, and its `.dram0.bss` headroom is a moving target that must be re-derived per change, never remembered. | Firmware-side requirements (§4, §6, §7) get cheaper, not more expensive. |
| A5 | Spotify returns 403 for the owner account indefinitely (TASK-243), so no live-playback oracle is available on this rig. | Twelve permanently-skipped Spotify ids become runnable; the SKIP semantics in §8 still apply. |
| A6 | The board stays pinned to a non-production build for the life of TASK-557 and possibly beyond. | §11's build-pinning requirements become optional rather than blocking. |
| A7 | `lib/dut.py`, `lib/results.py`'s `NOT-RUN` bucket, `get idle`, `get player` and class-ordered dispatch **already exist and work**. This document builds on them and re-proposes none of them. | Several requirements below become new work rather than tightening. |

---

## 3. Non-goals

Named so a reviewer can attack the boundary rather than guess at it.

1. **Not a rewrite.** 213 registered ids and the standalone harnesses stay. §14 states which
   requirements are ratchets over the existing corpus and which apply only to new tests.
2. **Not a fix list.** The 130 findings are individually cheap and separately schedulable; this
   document targets the six mechanisms behind them, and explicitly leaves the 26 rows WP-Z classes as
   ordinary defects to hygiene work.
3. **Not a second tier vocabulary.** Tier (`T0`–`T4`), class (RIG→FEATURE) and firmware level
   (`L0`–`L4`) are settled. Nothing here renames them.
4. **Not a T1/T2 host-unit programme.** Blocked on A3, and correctly deferred by M-TESTARCH §8.
5. **Not ground truth for audio or pixels by external instrument.** There is no microphone and no
   I2S tap. §4 answers those claims with device-side signatures and `run/screendump`, or refuses them.
6. **Not a change to production firmware behaviour.** Every firmware obligation below lands inside
   `SERIAL_DEBUG` (M-TESTARCH §4 I3).
7. **Not a replacement for `test_plan.md`.** It stays the only place a test id is declared, and C6
   stays the binding gate.
8. **Not the two escalated decisions.** Whether the M-WEBRADIO close stands, and whether the
   class-order switch may flip, are WP-Z §4.4 decisions for @PM/@Architect and a human. This document
   states what would have to be true for the switch to be safe (§9), not whether to flip it.

---

## 4. Group OBS — the observability contract

**The argument.** WP-Z's theme `T3` is the only finding in the review with a controlled experiment
behind it: six families, one VE, one harness, one period, SOUND rates from 77 % (LocalPlayer) to 7 %
(Clock). What varied was what the firmware gave each family to read. Where the observable was
designed before the test — ADR-059 D12's `get plOrder`/`get plCursor`/`advance`, TASK-112's
`quoteOkCount` — the tests are exact. Where it was not, the test reached for the nearest debug
injector and asserted its own input (`G-7`, `H-3`, `F-3`), or wrote *"verify manually"* into the pass
string (`D-5`). **Test quality is therefore not primarily a property of the test.** It is a property
of the surface, and a harness that does not make that a precondition will regenerate the 21 HOLLOW
ids in the next app.

So the contract below is stated as an **admission rule**, not as advice: an app earns the right to
have FEATURE tests counted as coverage by publishing observables, and an app that cannot publish them
does not get quiet green rows — it gets an explicit, dated, owned record that the claim is
unobservable.

**R1 — the vocabulary rule. MUST.** A test's oracle MUST read a value in the same vocabulary as the
claim it makes: a claim about elapsed time reads a device-side timestamp or counter; a claim about
ordering reads a device-computed order; a claim about rendered output reads a render-path signature
or a screendump; a claim about a fetch reads a fetch counter or error code, not a view flag.
*Rationale*: theme `T2` — twenty-one HOLLOW ids and a large share of the 64 WEAK ones are a
vocabulary mismatch, and `H-2` books five milestone exit criteria PASS against oracles that read a
settings byte. *Verification*: a host gate parses each registered body for the `get` keys and log
markers it reads, and compares them against a `reads:` field the record declares; a body that reads a
key its record does not declare fails the gate. The vocabulary match itself is a review judgement
recorded in the record's `oracle_reason` — **this is one of the three by-review items and is the
weakest link in the group**; the gate makes the judgement visible and dated, it does not make it.
*Priority*: MUST.

**R2 — no oracle may be satisfied by the harness's own write. MUST.** A test MUST NOT assert a value
that its own `set` command wrote, unless a firmware write to that value is provably interposed
between the write and the read; a `set <key>` and a `get <key>` on the same key inside one body with
no device-side transition between them is a defect, not a test.
*Rationale*: `G-7`, `H-3`, `F-3`, `E-8`, `H-7` — the single most common HOLLOW shape.
*Verification*: a host gate scans each body's command sequence for the `set X` … `get X` pattern with
no intervening command and fails unless the record carries an `interposed:` justification.
*Priority*: MUST.

**R3 — the app admission contract. MUST.** Before any FEATURE test for an app may be counted as
coverage, that app MUST publish, through its `dbgGet` surface: (a) an **identity** observable proving
the app is the active one, readable only when it is (not a global); (b) a **progress** observable
written exclusively by the app's own tick/render path, monotonic or changing, so that "it is running"
is distinguishable from "it exists"; (c) a **result** observable distinguishing success, failure and
never-attempted, with the failure carrying a code; and (d) an **entry-state** observable naming the
app's own sub-view or mode, gettable as well as settable.
*Rationale*: theme `T3` plus its four named gaps — `A-8` (every Clock oracle is a global readable
from any app, so a `switchApp` that stopped switching would fail no clock id), `H-6` (a boot-scoped
latch used as a per-visit oracle), `G-3` (`get fetchErrorCode` does not exist, so five diagnostics
have printed `None` for months), `B-5` (`stockMode` is settable and not gettable, so its restore
cannot be written at all).
*Verification*: extend `gate/check_app_conformance.py`'s row set — it already enumerates apps from
`APP_ORDER` and types no app name — with four rows, one per clause, over the key list from
`gen/gen_get_keys.py`. Day one is red for several apps; that is the correct first result and the same
shape as every other gate in this programme.
*Priority*: MUST.

**R4 — an app that cannot satisfy R3 is recorded, not exempted. MUST.** Where a claim has no
observable, the harness MUST carry it as an explicit `UNOBSERVABLE` record — id, claim, the missing
observable, an owning task and a date — and any milestone exit criterion resting on that claim MUST
be recorded DEFERRED, never PASS.
*Rationale*: `H-2` is the review's only finding that misstates a **shipped** result: five
M-CLOCK-STYLES criteria booked PASS against oracles that cannot see them, and a clock face rendering
as a solid black rectangle passes all fourteen ids and all five criteria.
*Verification*: `check_docs`'s C6 machinery already binds ids to declarations; add a `regression_suite`
rule that an exit criterion citing an id whose record is `UNOBSERVABLE` cannot carry a PASS. The
ledger shape is `docs/verification/id_binding_exceptions.md` — dated, task-owned, no wildcards, and a
stale row is itself a blocking failure.
*Priority*: MUST.

**R5 — the hard case, stated concretely: rendered output. MUST.** A claim about what is on the screen
MUST be verified by one of exactly two mechanisms — a **device-computed signature** over the buffer
the app drew from (a hash, a non-background pixel count, or a per-region checksum, exposed as a
`dbgGet` key), or a **host-side screendump** — and a claim that can use neither is `UNOBSERVABLE`
under R4 and may not be booked.
*Rationale*: `H-2` and `G-16`. The precedent for the cheap half already exists and shipped: M-TESTBASE
P2's `get player` returns FNV-1a hashes over the play/view order so a permutation is detectable
without dumping 256 entries. The same construction over a drawn region makes "the face rendered as a
black rectangle" a **failing** signature, because a constant region hashes to a constant, and makes
"the flip animation ran" observable as a signature that changes across the animation window. The
other half needs `run/screendump`, which has been hard-broken at import since TASK-555 (`A-1`) — so
this requirement's first cost is a repair, not a feature.
*Verification*: for each id whose claim is visual, the record names its mechanism; a gate asserts the
set of visual-claim ids with neither mechanism is exactly the `UNOBSERVABLE` set. For Clock
specifically, the acceptance number is in §13: Clock's SOUND rate must exceed 50 %, from 7 %.
*Priority*: MUST — this is the requirement that decides whether the worst family in the review is
fixable at all, and answering it with "manual verification" is what produced `G-16`'s two ids whose
entire body is one `skip()`.

**R6 — an observable is a deliverable of the feature. MUST.** A behaviour whose acceptance criterion
cannot be read through the owning component's own debug surface MUST NOT be declared done; the
observable ships with the feature, in the same task, not as later test work.
*Rationale*: theme `T3`'s cheapest recurrence-stopper, and `H-5`'s mirror image — `set
prForceParseFail` was built by TASK-361 as a deterministic fault injector and has **no consumer
anywhere**, while the id it exists for has been a permanent SKIP since 2026-07-11 and its docstring
still says no such hook exists. Observables built without a test, and tests written without an
observable, are the same defect from two ends.
*Verification*: the rule lands in `docs/architecture/designs/NEW-APP-CHECKLIST.md` §3 (which already
requires a minimum VE hook, item at `:92`) and is enforced by R3's conformance rows for apps. For
non-app features it is a review item — the second of the three by-review items, and honestly weaker
than the app half.
*Priority*: MUST.

**R7 — the console is a versioned contract. SHOULD.** The `get`/`set` surface SHOULD be treated as a
published interface: additive-only, field renames prohibited, and the key list generated rather than
mirrored.
*Rationale*: M-TESTARCH §4 I1/I2, and `A-3` — `gen/gen_get_keys.py` globs headers only, so 10
`dbgGet()` bodies that moved to `.cpp` under M-SRCLAYOUT are invisible and it enumerates 43 of 71+
keys, which is why `run/task488`'s "every key resolves" check covers about 60 %.
*Verification*: the generator's key count is compared against a full-tree scan in `run/check`; a
divergence fails. SHOULD rather than MUST because BP-024's "extend, don't rename" convention has held
with zero recorded violations (M-TESTARCH §10 OQ-C closed it on that evidence), so the gate is
insurance rather than a repair.
*Priority*: SHOULD.

**R8 — injection surface parity. SHOULD.** For every failure mode a test needs to reach, there SHOULD
be a deterministic injector, and it SHOULD be discoverable rather than invented per task.
*Rationale*: M-TESTARCH §4's stated gap ("there is no injection/fault surface to match the observation
surface"), priced at **+8 bytes `.dram0.bss`** for the minimal allocation-failure mode
(EXP-024, PROP-010 rung 2). `H-5` shows what the undiscoverable version costs.
*Verification*: the injector list is generated from the firmware the same way `get` keys are, and
every injector with no consumer is reported. SHOULD, not MUST: the *cost* side is measured, the
*benefit* side is still asserted — no incident search has yet found a multi-hour-soak bug this surface
would have converted into a fast deterministic test.
*Priority*: SHOULD.

---

## 5. Group FAL — falsifiability

**The choice, and why it is this one.** Four mechanisms were candidates: a "this test has never
failed in N runs" report; subsystem fault injection; per-test negative controls; and mutation.
**The requirement below picks a declared per-test falsifier, enforced always-on by host-side
transcript mutation and periodically on hardware.** The other three are rejected on evidence, not
taste:

* **"Never failed in N runs" is post-hoc and cannot discriminate.** It would flag a correct test of a
  stable feature exactly as loudly as a tautology. All 14 BROKEN and most of the 21 HOLLOW ids have
  never failed and — `C-1`'s inverted guard aside — never can; a report that cannot tell those apart
  from `T_DH_01`-shaped health checks that also never fail produces a list nobody can act on.
  Retained as a **SHOULD** (R13) because it is nearly free and it *is* a prior.
* **Subsystem fault injection does not reach the dominant defect.** Dropping a TLS handshake or
  failing an allocation cannot make `set X 5; get X == 5` fail. The dominant HOLLOW shape is an oracle
  reading the harness's own write, and it is immune to every fault the device can be made to suffer.
* **Full mutation testing of the firmware is not affordable.** One DUT, 30–90 minutes a run
  (M-TESTARCH §10 OQ-D), no host compile (A3). Mutating the firmware and re-running the suite per
  mutant is arithmetically out of reach on this rig, and pretending otherwise would put an
  unschedulable requirement in a requirements document.

The chosen mechanism is the only one whose enforcement is written **at authoring time**, which is the
moment the author knows what the test is for. That is the same argument WP-Z makes for declaring
`cls`: *"writing the reason strings is the audit"* — `B-1` and `B-2` would both have been caught by
someone trying to write a justification for a live-HTTPS-fetch CORE test.

**Its honest boundary, stated up front.** Falsifiability is necessary and **not sufficient**. A
tautology is perfectly falsifiable — mutate the transport and `get X == 5` fails — so this group
proves a test can fail, and §4's vocabulary rule is what proves it fails *for the right reason*.
Anyone reading R9 as a replacement for R1 has read it wrong.

**R9 — every test declares a falsifier. MUST.** Every registered id MUST carry, in its record, a
`falsifier`: a named perturbation — a mutated field in the device's reply, an injector, a fixture
removal, a deliberately wrong coordinate — that is asserted to make the test FAIL, together with
which of the two enforcement paths (R10 or R11) executes it.
*Rationale*: 21 HOLLOW + 14 BROKEN ids, and the pattern that a test's inability to fail was never
discoverable from anything but a line-by-line human read of all 216 bodies.
*Verification*: a T0 gate — the `gate/check_test_meta.py` pattern, which already asserts records are
well-formed — fails on any registered id with no `falsifier`. Landable family by family, and the
count of undeclared ids is the migration ratchet.
*Priority*: MUST.

**R10 — host-side transcript mutation, always on. MUST.** The harness MUST support recording a
test's full command/reply transcript and replaying it against the same body with one oracle field
mutated, and the suite MUST include a host-only, no-DUT job asserting that every id with a
replayable falsifier FAILs under mutation.
*Rationale*: `A-12` proves the corpus cannot even be imported safely today (six modules run their
suite at import and reset the board), so any always-on mechanism has to be host-side and stubbed. The
precedent is in-tree and works: the stubbed-serial pattern behind `run/player-gate --selftest` and
the negative suites in `gate/` (BP-068), which mutation-verified C6 with 14 deliberate breaks.
*Verification*: the job itself is negative-tested — deliberately break the mutator and assert it
reports zero falsifications rather than passing vacuously. That is the exact failure `F-15` records
in the suite (`T_WR_VIS_02`'s "control" is a `print(...)` warning) and it must not be repeated in the
mechanism that exists to catch it.
*Priority*: MUST.

**R11 — a scheduled hardware falsification campaign for physical falsifiers. SHOULD.** Falsifiers
that cannot be replayed on the host — pull the SD card, force a connect failure, remove a fixture —
SHOULD be executed on hardware on a schedule (before a milestone close, and at least once per
quarter), one class per session, inside §12's budget.
*Rationale*: `E-6` (four negative assertions where a `_wait_for_log` timeout is the pass, on a
suppressible `LOG_D` channel, so "no leak" and "no logging" are the same result) and `F-20` (the
ADR-045 criterion's skip term had zero variance in the gate run that closed the milestone, because
every trial played station 0). Both are unfalsifiable-in-practice and neither is host-replayable.
*Verification*: the campaign emits a dated per-id falsification record; the acceptance number in §13
is the share of ids with a **confirmed** falsification. SHOULD rather than MUST because it spends the
scarcest resource on the rig and a MUST would make it the first thing dropped under time pressure —
which would be worse than scheduling it honestly.
*Priority*: SHOULD.

**R12 — a negative assertion must be distinguishable from a dead channel. MUST.** A test whose pass
condition is the **absence** of an event MUST first prove the channel is live within the same run —
by observing a positive instance of the same marker, or by asserting the log level that carries it.
*Rationale*: `E-6` — 32 s per run spent proving nothing, on a channel `logSink.h` can suppress; and
`F-15`, where a failed read returns `None` and a board that stopped answering `get visMode` passes six
times.
*Verification*: a gate flags bodies whose only `fail()` is guarded by a timeout or a `!=` against a
value a failed read can produce; each must carry a liveness precondition or an exemption row.
*Priority*: MUST.

**R13 — report tests that have never failed. SHOULD.** The harness SHOULD keep a per-id verdict
history and report ids that have not produced a FAIL in the last N recorded runs, alongside their
falsification status.
*Rationale*: it is nearly free once R28's result artifact exists, and it is a genuine prior — but on
its own it cannot discriminate (see above), which is exactly why it is a SHOULD and not the group's
mechanism.
*Verification*: the report exists and is emitted from the archived result artifacts; no gate.
*Priority*: SHOULD.

---

## 6. Group STA — state hygiene

**The argument.** Three debug injectors — `set wrDeadUrls` (`F-4`), `set triggerHeatmap` (`G-1`),
`set prInjectAircraft` (`H-1`) — arm a flag that nothing clears: not `init()`, not `resume()`, not an
app switch, not a fresh fetch. Three families, three subsystems, three firmware authors, one shape;
WP-H went looking for the third deliberately and found it in one pass. Their cost is not theoretical:
`wrState=5` is the exact state `set wrDeadUrls` assigns, and it is the symptom two `flaky.yaml`
entries have blamed on radio-browser.info churn for about a year. Every one of the three is invisible
to a targeted re-run, because a targeted re-run cold-boots.

The harness's own discipline is the other half. 262 `skip()` sites, seven different defaults for
`r.get("val", …)` — six of them values a comparison can pass on (`A-14`) — and restores that
*rewrite* persisted state instead of restoring it (`C-12`). The data-app corpus writes `settings.json`
roughly fifty times per run, to real flash, and restores the user's clock face only by luck (`H-10`).

The requirements below are ordered so that the cheapest one — R14 — subsumes injectors nobody has
written yet, which is the property the three one-line suite fixes do not have.

**R14 — armed device state is enumerable, and the harness asserts it empty at every boundary. MUST.**
The firmware MUST expose a single observable enumerating every debug injection currently armed, and
the harness MUST read it at every test boundary and FAIL the *preceding* test if it is non-empty and
undeclared.
*Rationale*: `F-4`, `G-1`, `H-1` — the only three findings producing wrong verdicts today, and the
only requirement in this document that catches the fourth instance before an audit does. Attribution
is the point: the failure lands on the test that armed it, not on the eleven downstream ids that
inherited it, which is what made these three unattributable for a year.
*Verification*: a host-only inversion test in the `gate/` negative-suite pattern — stub a non-empty
injection reply and assert the arming test FAILs and the successor does not.
*Priority*: MUST.

**R15 — a debug injector is a within-visit instrument. SHOULD.** Every firmware injection flag SHOULD be
cleared by the owning app's `resume()` as well as its `init()`, so an app switch is a recovery path
for the whole class.
*Rationale*: WP-Z theme `T1`'s cheapest recurrence-stopper — three one-line firmware edits against
three one-line suite fixes that fix only the three known cases.
*Verification*: a conformance row over `APP_ORDER` asserting each app's `resume()` clears the
injection flags its `dbgSet` can set; and R14 catches whatever the static rule misses.
*Priority*: SHOULD — deliberately not MUST, and the reason is R14: once armed state is enumerable and
asserted at every boundary, a leaked injector is a named failure on the test that armed it whether or
not the firmware clears it. R15 makes the class *recoverable* rather than merely *detectable*, which
is materially better and is not the foundation.

**R16 — every test declares its effect, and the declaration is true. MUST.** Each record MUST carry a
declared `effect` — read-only, mutating, persisting (writes flash) or resetting (reboots) — declared,
not seeded from a default, and the harness MUST verify it against what the test actually did.
*Rationale*: `B-14` measured `effect` declared on **3 of 216** records; re-measured for this document
via `build_all_meta()`: 3 declared, 209 seeded `mutating`, 4 `read-only`, 3 `resetting`. WP-B filed it
P3 and was right *at the time*, because its only specified consumer (mode D descent admissibility) was
CUT — the field was correct, complete, gated and consumed by nothing. **This document is that
consumer.** R14, R17 and R19 all key off it, and a field nothing verifies is a field that will be
wrong the first time it matters. Note the new value: `persisting` does not exist today, and `H-10`'s
fifty flash writes per run are the reason it must.
*Verification*: the boundary check (R14) computes the actual effect — injections armed, settings hash
changed, reboot observed, entry app changed — and fails a test whose declaration is weaker than its
behaviour. A declaration *stronger* than the behaviour is allowed and reported, never failed.
*Priority*: MUST.

**R17 — restore is a context manager, not a convention. MUST.** Any state a test mutates MUST be
restored through a mechanism that runs on **every** exit path including failure, and a restore MUST
NOT default to a literal when the saved read is missing.
*Rationale*: `F-9` (four of thirty WebRadio bodies restore anything, three use `finally`), `E-15`
(17 of 31 player rows leak), `C-12`/`D-15`/`E-4` (seven restores default to a value that silently
rewrites persisted state — `r.get('val', 0)` for `playerMode` four times), `C-15` (a restore on the
pass path only, so every failure leaves an arbitrary app). The in-tree pattern exists and is used at
20 of 41 sites: `_bgpoll_suspended`.
*Verification*: a gate flags any `set` in a body or reachable helper with no matching restore on all
exit paths — which is also WP-B's `B-4` proposal (b), and would make a fourth injector cluster fail
`test_class_order.py` instead of waiting for an audit.
*Priority*: MUST.

**R18 — a saved value that could not be read is a skipped restore, never a guessed one. MUST.** A
harness accessor MUST distinguish "the device answered X" from "the device did not answer", and no
oracle or restore may be satisfied by a default.
*Rationale*: `A-14` (seven defaulting patterns, six passable), `G-2` (`_stock_ok_count` returns `-1`
on a bad read and `_wait_chart_complete(-1)` then returns `True` on its first poll — one raced serial
reply turns the family's central fetch oracle into an unconditional pass across nine ids), `F-15`.
*Verification*: one shared typed accessor in `lib/`; a gate asserting no `r.get(<key>, <literal>)` in
a suite body. The gate is mechanical and the count today is the ratchet.
*Priority*: MUST.

**R19 — persistent state is snapshotted and restored by the harness, not by the tests. SHOULD.** The
harness SHOULD snapshot device-persisted state at session start and restore it at session end, and any
test declaring `effect: persisting` SHOULD be reported in the run summary.
*Rationale*: `H-10` — fifty real flash writes per run, the user's clock face and radar range restored
only because a later test happens to write a different value; and `B-5`, where the restore is not
merely missing but *unwritable*, because `stockMode` is settable and not gettable.
*Verification*: a session-level settings hash printed at start and end; a difference with no
`persisting` declaration fails the run. Note this interacts with `run/test`'s existing step 0b/5b
snapshot, which currently *erases* the evidence of what the suite left behind.
*Priority*: SHOULD — R16's `persisting` declaration plus R17's restores are the foundation; a
session-level snapshot is a safety net over them, and it costs a real interaction with the existing
snapshot step that a MUST would force to be resolved before anything else could land.

**R20 — order independence is asserted, not argued. MUST.** The harness MUST be able to run a class's
ids in a shuffled order and MUST report any verdict that differs from the canonical order's.
*Rationale*: `B-4` — the 0→1-edge enumeration delivered as the class-order switch's precondition
under-reports three demonstrated order-dependence shapes, all three in the direction that grants a
false all-clear, and it cannot see clusters `C9`/`C10`/`C11` at all. A static scanner over 213 bodies
will always be an approximation; an actual shuffled run is evidence. This is also §13's strongest
acceptance number.
*Verification*: the shuffle mode exists and is exercised; three consecutive shuffled runs producing
the canonical verdict set is the acceptance criterion, not a claim in a document.
*Priority*: MUST — but see §14: it is the most DUT-expensive requirement here and is scheduled, not
continuous.

**R21 — order dependence, once found, is recorded as a first-class outcome. SHOULD.** A verdict that
differs under shuffle SHOULD be reported as `ORDER-DEPENDENT`, naming both orders, rather than as a
flake.
*Rationale*: `C-7`/`E-3`/`F-8` — every flake declaration examined across three families is mismatched
with its call sites in both directions, and `F-4` spent a year filed as network churn. A flake
declaration is where order dependence goes to be forgotten.
*Verification*: the outcome exists in the result schema (§8) and the shuffle job emits it.
*Priority*: SHOULD.

---

## 7. Group SYN — synchronisation

**The argument.** M-TESTARCH §3b's diagnosis is that the harness polls a device that is already an
event source, and that the event-driven pattern was proven in the harness's own constructor
(`_wait_for_ready()`) and never made available to a single test body. Re-measured for this document:
**253 `time.sleep(` sites** in `suite/serialdbg/`, **727 numeric `timeout=` literals** across the
suite and `lib/`, against `lib/dut.py:47-48`'s declared single timeout policy which `A-11` measured at
**zero users**. The scars are on the record — `DUT_WIFI_WAIT` then `DUT_WIFI_WAIT_2` (a harness
constant hand-tuned against a firmware constant, twice, TASK-434); `T_AE_04` "INCONCLUSIVE" for a
session because an 8 s harness wait raced a 10 s firmware connect timeout.

M-TESTBASE already funded and landed the cheap end: `get idle` with `hasInFlightOp()`, whose measured
result was *correctness, not speed* — 2.06 s busy→idle on a cold app switch against sub-50 ms warm,
where a fixed `sleep(2.5)` pays the worst case every time and is still a guess on a bad day. These
requirements build on that, and do not re-propose it.

**R22 — a wait is a failure bound, not a sampling budget. MUST.** Every wait MUST terminate on an
observed condition and MUST report the actual elapsed time on both the pass and the fail path; a test
MUST NOT pass merely because a window expired.
*Rationale*: M-TESTARCH §3b.4, and its reductio — a test that a fast network can defeat is sampling a
window it does not control. A 2 s poll interval inside a 30 s bound also reports latency at ±2 s
granularity, which is why one id could never detect a 2× fetch-latency regression.
*Verification*: a gate flags any bounded loop whose expiry path leads to `pass_()`; each must be an
exemption with a reason.
*Priority*: MUST.

**R23 — a bare sleep is not a synchronisation primitive. MUST.** New tests MUST NOT use a sleep to
wait for a device-side transition; the admissible waits are a quiescence predicate, a subscription, a
correlated reply, or a **physical** wait whose duration cites a firmware constant by name.
*Rationale*: 253 sleeps against 2 named sleep constants; `H-9`, where `set cooldown 0` is the wrong
variable at all three Teletext call sites — the calls are inert and what actually clears the gate is a
`time.sleep(0.35)` nobody documented as the mechanism.
*Verification*: a ratchet gate — the sleep count may not increase, and every sleep in a touched file
must carry a citation. §13 sets the target number.
*Priority*: MUST.

**R24 — one timeout policy, with users. SHOULD.** The transport timeout SHOULD be a single policy in
`lib/` with a default and a slow-operation override, and test bodies SHOULD NOT carry numeric transport
timeouts.
*Rationale*: `A-11` — 823 numeric literals, 459 of them exactly the default, against a declared policy
with zero users; M-TESTBASE P1 funded this and it has not been consumed.
*Verification*: count of numeric `timeout=` literals in `suite/`, ratcheted to zero.
*Priority*: SHOULD — 727 literals of which the overwhelming majority are exactly the default is
maintenance debt, not unsoundness: no verdict in the review is wrong because of it. R22's failure-bound
rule is the part that changes what a wait *means*, and that is the MUST.

**R25 — replies are correlated, not positional. MUST.** Every command MUST carry a sequence id and
every reply MUST echo it, and the harness MUST fail on a mismatch rather than consume the next
well-formed line.
*Rationale*: `C-18` — `get cooldown` and `get shellCooldown` answer with the same field name and
`Dut.cmd` correlates nothing, so a one-reply desync is undetectable, while `Dut.cmd` itself issues
`get shellCooldown` before every tap and drag; `C-2` — `T-UART-01` cannot observe JSON garbling at all
because the shared reader swallows the malformed line and returns the next one, making its `except`
branch unreachable. Positional matching is also what makes pushed event lines unsafe to add, so R26
depends on this.
*Verification*: a stubbed-serial test that injects a desynchronised reply and asserts a named failure,
not a timeout. This is a breaking wire-format change — see §14.
*Priority*: MUST.

**R26 — the device can be asked to tell, not only polled. SHOULD.** For the small set of observables
that existing condition loops target, the device SHOULD emit a line on change, so a bound becomes a
real failure bound with an exact elapsed time.
*Rationale*: M-TESTARCH §3b.3 item 4, with its own scope discipline: build it for the ~10 keys the
loops actually target, derived mechanically from the loops, not guessed. SHOULD because it is firmware
work on the memory-constrained build (A4), it depends on R25, and `get idle`'s measured outcome
suggests the remaining win is correctness on a handful of keys rather than a broad speedup.
*Verification*: the key list is derived from the loops by a script, not typed; each converted loop
reports an exact elapsed time.
*Priority*: SHOULD.

**R27 — an acknowledgement means handled, not received. SHOULD.** Input injection SHOULD acknowledge
after dispatch is complete, and the reply SHOULD carry whether the input was swallowed by a gate.
*Rationale*: M-TESTARCH §3b.3 item 2, and `H-8` — the tap reply's `"skipped"` flag is discarded at
every tap site in the data-app corpus, so a tap swallowed by the busy gate or the 300 ms debounce
passes on its predecessor's residue.
*Verification*: the harness reads the flag at every tap site (a gate can assert the call sites do not
discard it) and the settle sleeps that follow taps are removed as the ratchet in R23.
*Priority*: SHOULD — the `"skipped"` half is nearly free and should land first; changing ack
semantics is the firmware half and is not urgent once the flag is read.

---

## 8. Group RES — result semantics

**The argument.** The per-id summary line (`app/tools/lib/results.py:271`) is a machine interface
with no specification. `run/player-gate` parses it with a `sed` regex; a missing token there already
produced a **false REGRESS verdict** (TASK-573); a second producer emits the same shape by
coincidence; and `E-14` records the gate's parser seeing a `FLAKY-PASS` id twice because declared
flakes are printed again under their own heading in the same `  <id>: <status>` shape
(`app/tools/lib/results.py:279`). Meanwhile the bucket meanings are not stated anywhere a consumer can read, and the
one that matters most — a precondition that did not hold — is spelled `SKIP`, which is green.

**R28 — the buckets are defined, closed, and mean exactly this. MUST.**

| Verdict | Means | May a gate treat it as green? |
|---|---|---|
| `PASS` | the oracle ran and the assertion held | yes |
| `FAIL` | the oracle ran and the assertion did not hold — a statement about the firmware | no |
| `SKIP` | **not applicable to this configuration**: names a configuration predicate (build variant, absent fixture, disabled feature) that is true independently of the run's health | yes, and it must be counted and shown |
| `UNMET` | the test's premise could not be established — the precondition failed | **no; it is not a result about the firmware and never green** |
| `NOT-RUN` | never dispatched, blocked by a lower-class failure; carries `blocked-by` | no |
| `FLAKY-PASS` | a pre-declared flake that passed on retry; both attempts reported | no — never counted as a pass, never satisfies a declared pass set |
| `ORDER-DEPENDENT` | R21's shuffle outcome | no |

*Rationale*: `C-5` — 31 of the 43 CORE ids have a `skip()` exit and each one is a CORE precondition
that did not hold, which is exactly the condition the class exists to stop the run on; 262 `skip()`
sites suite-wide; `D-2`, where six residue ids convert the regression itself into a `skip()` and can
therefore PASS or SKIP but never FAIL. `UNMET` is the one new value, and it is the whole point of the
table: *a test that cannot run is not "not applicable", it is an unestablished premise.*
*Verification*: the vocabulary is enumerated in one module; a gate asserts no suite writes a verdict
string outside it. `NOT-RUN` and `FLAKY-PASS` already exist (TASK-566, and the flake policy) and are
not re-proposed.
*Priority*: MUST.

**R29 — the machine-readable artifact is the interface; the printed summary is not. MUST.** Every run
MUST emit a schema-versioned JSON artifact, and every consumer — gates, comparators, dashboards,
another session's analysis — MUST read that artifact and MUST NOT parse the human summary.
*Rationale*: `A-7` and TASK-573's false REGRESS; `E-14`'s double-parse; `A-6`, where
`run_sync_tests.py` carries a private pre-TASK-520 copy of the whole results layer with no flake
policy, no `FLAKY-PASS`, no `NOT-RUN` and no exit 4.
*Verification*: `grep` for consumers parsing the summary — the acceptance number is zero (three
today); the artifact carries a schema version and its own negative test.
*Priority*: MUST.

**R30 — the artifact carries the run's premise. MUST.** Each record MUST carry at minimum: id, class,
scope, effect, verdict, reason, start/end timestamps, elapsed, boot generation, the falsification
status (R9), and per run: the firmware ELF hash and build id, the harness version, the entry point,
the flake registry hash, and any downgraded gate.
*Rationale*: `F-19` — `run/wr-gate` cannot say what firmware it measured, no ELF hash and no build
check, unlike `run/player-gate`; M-TESTARCH precedence §5 E5's "every run states its own premise",
which that document calls the highest-ratio item it contains; and the generation rule that an
observation made before a boot was observed is tagged `gen=?` and is never comparable.
*Verification*: schema test; and a gate asserting no milestone exit criterion cites a run whose
artifact lacks a build identity.
*Priority*: MUST.

**R31 — a verdict is a typed value, and gating reads the type. MUST.** Gating, comparison and
reporting decisions MUST read a typed verdict, never a formatted string or its prefix.
*Rationale*: `app/tools/suite/serialdbg/_gate.py:129` — `RESULTS.get(tid,"").startswith("FAIL")` is
the entire blocking rule, so the class hierarchy's central promise is delivered by a string-prefix
test that the common failure mode does not match.
*Verification*: the inversion selftest (M-TESTARCH precedence EC-G8) extended with an `UNMET` arm.
*Priority*: MUST.

**R32 — reasons are structured. SHOULD.** A non-PASS verdict SHOULD carry a machine-readable reason
code plus prose, so failures can be grouped across runs without regex.
*Rationale*: `G-10` — three failure messages attribute an upstream timeout to a named firmware fix
("guard fix may not have landed") while the discriminating value is read by the helper and dropped.
*Verification*: reason codes enumerated in the schema; a report groups a run's failures by code.
*Priority*: SHOULD.

**R33 — one results layer, no private copies. MUST.** Every entry point that produces test verdicts
MUST use the shared results layer.
*Rationale*: `A-6`, `F-12` (a soak filed as a test with no verdict line and no non-zero exit on any
anomaly path — DUT silence, render freeze and an unexpected boot marker all just increment a counter),
`A-4` (four independent `SerialDut` classes bypassing `lib/dut.py`).
*Verification*: count of modules defining their own `RESULTS`/`pass_`/`fail`, ratcheted to zero.
*Priority*: MUST.

**R34 — a test that cannot produce a verdict is not coverage. MUST.** An id whose body cannot reach
any assertion MUST NOT be counted in a coverage figure, and coverage counts MUST be generated from
the binding rather than maintained by hand.
*Rationale*: `D-4` and `G-16` — three registered ids whose entire body is one unconditional `skip()`,
one of them still recorded `Status: pass` in the archived plan, all three counted in the id total;
M-TESTARCH §6's generated-coverage rule.
*Verification*: a gate detects bodies with no reachable `fail()`; the coverage figure is generated by
`check_docs` C6's binding data.
*Priority*: MUST.

---

## 9. Group GAT — gating and classes

**The argument.** Today's gate blocks on a `FAIL` prefix and nothing else, and the CORE class — 43
ids — is 100 % undeclared: re-measured for this document, `cls` is declared on 6 of 213 records and
**not once on a CORE id**. WP-B's line is the accurate one: a `cls` value has never been wrong here
because no `cls` value has ever been written down. That is harmless while the class-order switch is
held and decisive the moment it flips, because seven of those 43 are single-app Stock tests whose
precondition is a live HTTPS fetch and one of them FAILs rather than skips — from index 14, that
failure would NOT-RUN all 167 FEATURE ids.

**R35 — a class is declared for every gating id, never defaulted. MUST.** Every RIG, HEALTH and CORE
id MUST carry an explicit class declaration with a written reason; FEATURE remains the safe default
for everything else.
*Rationale*: `B-15` (filed P3, argued P1 by WP-Z, and the argument is right: it converts every other
CORE finding from "a weak test" into "a weak test with a veto"); the mechanism already exists as
M-TESTARCH precedence EC-G6 and is unmet.
*Verification*: `gate/check_test_meta.py` fails on an undeclared gating class. Writing the 43 reason
strings *is* the audit.
*Priority*: MUST.

**R36 — a gating class may not depend on the outside world or the host's file layout. MUST.** A RIG,
HEALTH or CORE test's precondition MUST be satisfiable offline on a healthy board.
*Rationale*: `B-1` (seven CORE ids need a live HTTPS fetch; one FAILs if a chart length does not
exceed zero in 45 s) and `B-2` (a CORE id that is a host-side source grep plus a 90 s vacuous soak, so
a checkout missing a library directory would NOT-RUN the FEATURE suite on a host file-existence
failure). A network outage must not be able to declare the firmware untestable.
*Verification*: a gate over the declared class and the body's command set; the exceptions are listed
and dated.
*Priority*: MUST.

**R37 — a gating class test may not carry a flake declaration. MUST.** An id whose class can block
MUST NOT be declared flaky; if it is unreliable it is either fixed or demoted out of the gating class.
*Rationale*: `C-6` — a CORE id whose every exit is `flake()`, so a declared flake that passes on retry
becomes `FLAKY-PASS`, which is neither PASS nor FAIL and can never set the blocker.
*Verification*: a gate cross-checks the flake registry against the declared classes.
*Priority*: MUST.

**R38 — a failed precondition in a gating class blocks. MUST.** An `UNMET` verdict in RIG, HEALTH or
CORE MUST block the classes above it exactly as a FAIL does, and MUST be visible in the summary and
the artifact.
*Rationale*: `C-5`; and `C-4`, where a skipped HEALTH check is announced as `[health] PASS` with a
sentence asserting the thing that did not run, while the triage layer calls the same run degraded in
the same output.
*Verification*: the inversion selftest's `UNMET` arm asserts the **absence** of any other verdict
among the blocked ids, not merely the presence of `NOT-RUN` — a weaker form passes a runner that
emits both.
*Priority*: MUST.

**R39 — the HEALTH class must be able to fail for the reasons the rig actually fails. SHOULD.** The
health checks SHOULD cover, at minimum: shell correctness, network identity that is actually compared
against the expected network, filesystem presence, tap-path dispatch and the ability of the data path
to dispatch at all.
*Rationale*: `C-10` — no health check performs off-board I/O, reads the filesystem, exercises the tap
path or samples supply, so a wiped SPIFFS, a broken tap dispatch and a silently non-dispatching data
task all pass, and the ~150 tap-driven ids then report rig failures as firmware defects; `C-9` — the
network check never compares the SSID against anything, so a board on a neighbour's AP is certified as
knowing which network it is on; `C-8` — the shell check validates only compile-time or trivially
non-zero fields.
*Verification*: each new check is negative-tested against a stubbed serial; the health run stays
inside its budget (§12).
*Priority*: SHOULD — the gating *machinery* (R35–R38, R40) is what must be sound; which checks the
HEALTH class contains is a coverage question, and one this document should not settle by listing five
of them. It becomes a MUST for any check whose absence has already caused a misattribution — the
tap-path one has.

**R40 — every gating class has executable coverage from a shipped entry point. MUST.** No class may
exist whose tests cannot be dispatched by any `run/` script.
*Rationale*: `C-3` — the RIG class has no executable coverage in any shipped entry point, because
nothing passes the flag its ids require, so the injection-vs-physical calibration id that licenses
every synthetic tap in the other 210 ids has never been runnable from a script.
*Verification*: a gate enumerates classes from the registry and asserts each is reachable from at
least one entry point.
*Priority*: MUST.

**R41 — the APP class is generated, never hand-copied per app. SHOULD.** Conformance rows SHOULD be
generated over `APP_ORDER`, and hand-written per-app copies of a conformance row SHOULD fail a gate.
*Rationale*: `B-12` — the APP class is empty because its three conformance rows were hand-copied per
app as FEATURE, 12 ids across four families plus two more copies; M-TESTARCH §2.3's whole argument,
with `check_settings_wiring.py` as the working precedent at one-item scale. SHOULD rather than MUST
because the existing hand-copies are correct today and the cost is a real migration; it is the
group's biggest structural win and its least urgent.
*Verification*: `gate/check_app_conformance.py` extended; a gate asserts no app name is typed in a
conformance body.
*Priority*: SHOULD.

---

## 10. Group SSOT — one source for every fact

**The argument.** The suite re-declares firmware constants, enum values, app slots, layout
coordinates and generated-header values in at least nine registered places, and in every case a
generator, a parser or a generated Python module already exists that it could import instead. The
sharpest: a **generated** teletext layout header whose y-values are mirrored by hand in six places,
in a module that imports the parser and never uses it (`H-12`). Every mirrored value is correct
today (`A-8` is refuted as a live defect and confirmed as a latent one), so the cost is entirely
future and entirely silent — and worse than "the suite fails": the firmware clamps the coordinates
the Stock suite mirrors, so a drifted value never *misses*, it selects a different row, which only
the six ids that read their selection back can see (`G-8`).

**R42 — no firmware fact is mirrored. MUST.** Constants, enum values, app slots, layout coordinates
and key names MUST be parsed from the firmware or from `app/gen/`, never re-declared in the suite.
*Rationale*: `A-9`, `A-10`, `C-13`, `D-6`, `F-16`, `H-12`, `H-19`, `A-8`; LL-114's parse-don't-mirror
rule, which the register grew *after*.
*Verification*: `A-18`'s proposal — a host gate holding the `(suite symbol, firmware symbol)` pairs
and asserting equality at gate time, seeded with the nine-mirror register. It converts every future
mirror from a silent drift into a build failure.
*Priority*: MUST.

**R43 — a derived value is derived once. SHOULD.** A formula that exists in the firmware SHOULD NOT be
re-implemented in the harness.
*Rationale*: `D-6` — the Settings tap geometry hand-mirrors four firmware constants **and**
re-implements a row-height formula in Python, using a count that lives in `app/gen/`, so drift lands
every Settings tap on the neighbouring row; `D-16` and `C-13` are the same shape.
*Verification*: covered by R42's gate; the pairs include derived expressions, not only literals.
*Priority*: SHOULD — it is a strictly harder case of R42 (a formula cannot always be compared by
equality at gate time), and R42's registered pairs already catch the instances that exist.

**R44 — every threshold cites its origin. SHOULD.** A numeric bound in an assertion SHOULD cite either
a parsed firmware constant or a dated measurement with its method.
*Rationale*: `F-18`, `G-15`, `H-18` — over a thousand numeric literals with three citing a firmware
constant; a no-loop window equal to exactly one skip-pace interval, so a slow runaway passes it; a
4096-byte leak bound on a code path that allocates nothing. The counter-example in the same review is
instructive: the two best-graded network ids both carry a derivation.
*Verification*: a gate requires a citation comment or a parsed symbol for numeric literals in
assertion positions in touched files; ratcheted, not retrofitted in one pass.
*Priority*: SHOULD — honestly graded down: over a thousand literals cannot be cited retroactively, a
ratchet that never completes is not a MUST, and the specific bounds that mattered are already named
as individual defects.

**R45 — generated infrastructure has a consumer or is deleted. SHOULD.** A generated module or key
list with no importer SHOULD be wired in or removed.
*Rationale*: `A-17` — a memory-layout module generated expressly "for the test suite" with zero
importers repo-wide, a layout module with zero suite importers, and a coordinate parser imported and
unused in two modules. Dead generated code is a mirror waiting to be written by someone who does not
know the real thing exists.
*Verification*: an importer census in `run/check`; SHOULD because deletion is a judgement about future
intent, and WP-Z routed the same question to @Architect as a standing decision.
*Priority*: SHOULD.

**R46 — ids exist once. MUST.** A test id MUST bind to exactly one body and one declaration.
*Rationale*: `A-15` (two registry ids with two executable bodies, different oracles, different
reporting), `F-2`/`G-11` (three registry ids colliding with unrelated plan headings, so the plan's
bound entries point at bodies that do not implement them and any coverage claim citing them is
ambiguous), `B-13` (a test declared in the plan with one body, no registry entry, escaping the binding
gate in both directions).
*Verification*: `check_docs` C6 extended to detect duplicate bodies and heading collisions; the
existing exception ledger is the migration path.
*Priority*: MUST.

---

## 11. Group RIG — one session layer, and a board that is allowed to stay pinned

**The argument.** `lib/dut.py` is good work — port resolution, the DRD reset-gap guard, boot-phase
deadlines — and `A-4` finds four independent `SerialDut` classes bypassing it entirely, three of them
behind documented `run/` entry points, with no reset-gap stamp, no debug-firmware verify, no cooldown
drain and no setup-failure contract. Measured for this document: **17 files** call `serial.Serial(`
directly. And the rig-vs-firmware exit contract — the thing that stops "the cable is bad" being
reported as "the firmware has 200 bugs" — is honoured by four files (`A-2`).

The pinning requirement is not hypothetical. WP-Z's DUT session, which would settle 32 of the 58
open items including all three armed-injector confirmations, **cannot be run at all** today: the two
entry points restore `ENV_PROD` from an unconditional EXIT trap, and `run/lib.sh:16` makes that
variable deliberately non-overridable, against TASK-557's standing instruction not to restore
production.

**R47 — one DUT session layer. MUST.** All DUT access MUST go through the shared session layer; no
tool may construct its own serial session.
*Rationale*: `A-4`, `A-2`, and the 17 direct-`serial.Serial` files measured above.
*Verification*: a gate forbidding `serial.Serial(` outside `lib/`; ratcheted with a dated exception
list.
*Priority*: MUST.

**R48 — importing a module MUST NOT touch the board. MUST.** No module under `app/tools/` may open a
port, reset the device or run a suite at import time.
*Rationale*: `A-12` — six DUT scripts execute their whole suite at import, which reset the board and
injected taps during this very review, contaminating a TASK-557 observation window; and it blocks any
import-level lint over the tooling, including several gates this document proposes.
*Verification*: a host gate imports every module in a subprocess with a stubbed `serial` and asserts
no port open; six files are the known ratchet, and the fix is a `__main__` guard each.
*Priority*: MUST.

**R49 — the rig-vs-device distinction is carried by the exit code and the message, and neither is
typed per call site. MUST.** A rig failure, a device-unfit failure and a firmware failure MUST be
distinguishable from the exit code alone, and the explanatory sentence MUST be selected by the failure
class rather than written at the raising site.
*Rationale*: `A-2`; M-TESTARCH precedence §4's 3-vs-4 split — *"3 means the host could not address a
board; 4 means the board is not a valid subject"* — and EC-G1/EC-G7, of which the consumer half is
what makes exit 4 safe to ship at all.
*Verification*: EC-G7's enumerated consumers each have a selftest case for the new exit; a gate
asserts no call site types the sentence.
*Priority*: MUST.

**R50 — board fitness is established before results are believed, and never after. MUST.** A run MUST
establish fitness through the HEALTH class before dispatching CORE and above, and a post-mortem fitness
check MUST NOT be offered as a diagnosis of a wedged board.
*Rationale*: M-TESTARCH precedence §5 E4 — opening the port asserts DTR and resets the ESP32, and per
TASK-426 a reset is precisely what clears the dead-SSID wedge, so running the fitness tool after
forming a theory destroys the state it was invoked to diagnose and manufactures a wrong conclusion
with a tool's authority behind it; `E-13`, where a release gate's health machinery cannot fire because
the runner is invoked without the flag that would run it.
*Verification*: the tool prints its reset warning before its verdict on every run, unconditionally
(EC-G4); the gate's health phase has a selftest.
*Priority*: MUST.

**R51 — the harness runs against a pinned build and never silently restores another. MUST.** Every
DUT entry point MUST support running without restoring production firmware, MUST record which
firmware it ran against, and MUST refuse to run rather than silently reflash when the requested build
and the board's build disagree.
*Rationale*: the TASK-557 pin, and the blocker above — a trap that fires on success, on failure and
on interrupt, against a standing instruction not to restore production. Also `F-19`: a gate that
cannot say what firmware it measured cannot support a milestone claim.
*Resolution (ADR-067, landed TASK-633 2026-09-06)*: **not** an opt-out. The restore is deleted from
all fourteen entry points; each declares the build it needs, reads the board, and refuses with exit 3
(`elf-mismatch`, RIG). `DUT_NO_RESTORE=1` was the dated interim only, and its retirement condition is
met. Killing a script mid-flight remains wrong (ADR-067 D5) — it now races a flash or a measurement
rather than a restore.
*Priority*: MUST.
*Verification*: `gate/check_entrypoint_lifecycle.py`, blocking at zero, with its 20-arm negative
suite; the ELF hash appears in the result artifact (R30).

**R52 — preconditions are declared, checked once, and shared. SHOULD.** Fixtures (SD contents,
credentials, queue state, station lists) SHOULD be declared per test, verified once per session, and
reported as `SKIP` with a named predicate when absent — not rediscovered by each body.
*Rationale*: `E-1` — the player family's fixture oracle discards the load reply and returns only a
count, so it cannot distinguish a missing fixture from a broken load or an unresumed mode, and eight
ids skip on it; `E-16`, where a fixture-missing skip is unreachable because the report it reads prints
success unconditionally; `D-13`/`E-12`/`F-17`, where duplicate preconditions cost a full extra run
each.
*Verification*: the session prints a fixture inventory; a gate asserts each declared fixture has one
checker. SHOULD because the declaration format is a design decision this document should not make.
*Priority*: SHOULD.

---

## 12. Group COST — the budget, and what may be slow

**The argument.** Hardware time is the scarcest resource on this project: one board, serialised,
30–90 minutes a full run, and a review whose most valuable single action — one 80-minute session —
has been blocked for procedural reasons. A budget is therefore a requirement, not a nicety, and the
"what may be slow" rule is what stops the budget being met by deleting coverage.

**R53 — a wall-clock budget per class, enforced and reported. MUST.**

| Class | Budget | Note |
|---|---|---|
| RIG | ≤ 15 s | host-side plus the port open |
| HEALTH | ≤ 60 s **including the boot its own port open causes** | a "20 s" figure that excludes the boot it causes is not acceptable; a degraded boot has been measured at 46 s to console |
| CORE | ≤ 8 min | 43 ids today |
| APP | ≤ 6 min | generated conformance, 13 apps |
| FEATURE | ≤ 45 min | the remainder |
| **full ordered run** | **≤ 60 min** | the number a developer will actually pay before a merge |

*Rationale*: M-TESTARCH §10 OQ-D's serialisation ceiling; `B-18`'s observation that the class-ordered
switch is a large cost improvement for a CORE failure (~40 minutes to ~6) and that the argument was
never made; and §7's ~100 s of pure sleeping per run before counting condition-loop overshoot.
*Verification*: per-class elapsed is in the result artifact (R30); a run that exceeds a class budget
reports it. Reported, not failed — a hard failure on wall-clock would make a slow network day look
like a defect, which is the mistake this document spends §7 correcting.
*Priority*: MUST.

**R54 — a slow test must be slow for a physical reason, and must be the only one paying it. MUST.**
An id exceeding 60 s MUST declare why, and the reason MUST be that its subject *is* a duration (a
soak, a drift, a leak, an endurance window) or that it pays an irreducible physical wait; a second id
MUST NOT pay the same precondition wait a first has already paid.
*Rationale*: `D-13` and `F-17` (two id pairs that are the same test with a weaker bound, each costing
a full second precondition run), `E-12` (an id whose only assertion is a strict subset of another's,
at the cost of a second full 200-entry browser walk), `E-6` (32 s a run spent on negative assertions
that cannot fail), `B-16` (26 ids collapsing to about 11 behaviours).
*Verification*: the artifact's elapsed times are ranked per run; ids over the threshold without a
declaration are reported. The duplicate-precondition half is a review item — the third and last of
the three by-review items in this document.
*Priority*: MUST.

**R55 — endurance work is outside the budget and outside the merge gate. SHOULD.** Soaks and
endurance runs SHOULD be scheduled on demand or before a milestone close, and SHOULD NOT be counted
against or dispatched inside the ordered run.
*Rationale*: M-TESTARCH §2b's T4 tier; and the practical lesson that short soaks give false
confidence — a ported fix recurred later at a higher reading, so an endurance claim needs
several-minute-plus windows that cannot live inside a 60-minute budget.
*Verification*: the entry points are separate and the artifact records which one produced a run.
*Priority*: SHOULD.

---

## 13. Acceptance criteria for the harness itself

A requirements document that cannot say how we would know it worked is a wish list. Every criterion
below has a **measured before** taken from the review or re-measured for this document, and a target.
None is "reviewed and found good".

| # | Criterion | Before | Target | How measured |
|---|---|---|---|---|
| AC1 | Share of registered ids that assert what they claim, by the M-TESTQUAL rubric | 54 % (117/216) | **≥ 85 %** on a re-audit of a 40-id random sample, and **no family below 50 %** | rubric re-audit, same method, sample drawn before the audit starts |
| AC2 | The worst family's SOUND rate | Clock 7 % (1/14) | **> 50 %**, or every unsatisfied clock claim carried as `UNOBSERVABLE` with an owning task | family re-audit |
| AC3 | Registered ids with a declared falsifier | 0 | **100 %** | gate count |
| AC4 | Ids whose declared falsifier has been **confirmed** to make them fail | 0 | **≥ 90 %** host-replayable, 100 % of the remainder scheduled with a date | mutation job + campaign records |
| AC5 | Ids with no reachable `fail()`, or a body that is one unconditional `skip()` | ≥ 17 known (6 residue + 3 skip-only + 8 predicted) | **0** | gate |
| AC6 | Test-boundary hygiene violations in a full run (armed injection, unrestored app, changed persisted state, all undeclared) | ≥ 3 known armed injectors, ~50 flash writes | **0** | boundary check, from the run artifact |
| AC7 | Gating-class ids exiting on a failed precondition as a green verdict | 31 of 43 CORE ids can | **0** — all are `UNMET` | gate + inversion selftest |
| AC8 | CORE ids with a declared class and a written reason | 0 of 43 | **43 of 43** | census via `build_all_meta()` |
| AC9 | Records with a declared `effect` | 3 of 213 | **213 of 213**, and 0 declarations weaker than observed behaviour | census + boundary check |
| AC10 | Consumers parsing the human summary text | 3 | **0** | grep over `run/` and `app/tools/` |
| AC11 | Bare synchronisation sleeps in the suite | 253 | **≤ 25**, each citing a firmware constant | count, ratcheted |
| AC12 | Registered mirrored firmware facts with no gate | 9 registered, gate absent | **0 ungated**; gate exists and is blocking | mirror gate |
| AC13 | Verdict differences across three consecutive within-class shuffled runs | never attempted | **0 differences** | shuffle runs, artifacts diffed |
| AC14 | Full ordered run wall-clock | 30–90 min | **≤ 60 min**, with per-class elapsed reported | artifact |
| AC15 | Milestone exit criteria citing an id whose oracle cannot observe the criterion | ≥ 5 (`H-2`) + 1 (`F-20`) | **0** | `regression_suite` gate |
| AC16 | Modules opening a serial port at import | 6 | **0** | import-in-subprocess gate |

**AC13 is the one to defend hardest.** Every other criterion is a count over declarations, and
declarations can be written to satisfy a gate. A shuffled run is the only criterion here that the
harness cannot talk its way past: it either produces the same verdicts or it does not, and the three
armed-injector clusters would have failed it on the first attempt, a year ago.

**What none of these prove.** They are all statements about the *suite*. None says the firmware is
correct, and a re-audit at 85 % SOUND still means one id in seven is weaker than it claims. The
review's own caution applies unchanged: a SOUND verdict is a statement about the oracle, not about the
firmware.

---

## 14. Migration — what is incremental, what is not

**The rule this section exists to honour:** a requirement that cannot be met incrementally is not a
requirement, it is a rewrite. Three of the 55 cannot, and they are named.

**Modes.** *Ratchet* — a count that may not increase and is driven down; *new-only* — applies to
tests written or touched from adoption; *flag-day* — cannot be landed partially; *gate-first* — the
mechanism lands red with a dated exception ledger that shrinks, the pattern C6 already uses.

| Mode | Requirements | Notes |
|---|---|---|
| gate-first | R1, R2, R3, R4, R5, R9, R16, R35, R36, R37, R42, R46, R54 | land the gate with today's violations on a dated ledger; a stale row is itself a failure |
| ratchet | R17, R18, R23, R24, R33, R44, R47, R48, R45 | the count is the migration plan; each is measured in §13 |
| new-only | R6, R12, R22, R52 | retrofitting is the ledger's job, not the rule's |
| additive | R10, R13, R14, R19, R21, R26, R27, R30, R32, R34, R39, R41, R51, R53, R55, R15, R43 | nothing existing breaks; consumers opt in |
| **flag-day** | **R25** (correlated replies — a wire-format change touching every importer), **R28/R31** (the verdict type and the `UNMET` bucket, which change what a gate does), **R29** (the artifact becomes the interface, at which point summary parsers must already be gone) | each needs one landing, and R25 should land **with** a session-layer change rather than after it |
| scheduled | R11, R20 | DUT-expensive by nature; they are calendar items, not continuous gates |

**The first increment: the record schema and the result artifact — host-only, zero DUT time.**
Concretely, R28's verdict vocabulary and typed value, R29's JSON artifact with R30's premise fields,
R31's gating on the type, and the record fields R9/R16/R35 declare — plus the three consumers moved
off the summary text.

Four reasons it is first, in order of weight:

1. **It is the only increment available.** The board is pinned to the `-DBOD_WATCH` build (A6) and
   the two entry points cannot run without violating that pin, so *any* first increment that needs
   hardware is blocked on a decision nobody has taken yet. This one needs none.
2. **Everything else needs a place to declare and a place to report.** The falsifier (R9), the effect
   (R16), the class (R35), the boundary result (R14), the shuffle outcome (R21) and the falsification
   status (R13) are all fields; without the schema each would invent its own.
3. **It removes a known live defect.** A missing token in an unspecified summary line already produced
   a false REGRESS verdict (TASK-573), and a second consumer sees flaky ids twice.
4. **It is verifiable without the thing it verifies** — the verification paradox in M-TESTARCH §9
   applies to the suite, not to a host-side schema with its own negative tests.

**Second increment**, when a hardware window opens: R14's armed-state enumeration plus the boundary
assertion. It is one firmware key and one harness hook, it attributes the three known injector
clusters to the tests that armed them, and it catches the fourth before an audit does.

**What must not be done in one pass.** R42's mirror retirement, R23's sleep removal and R44's
threshold citations are each a thousand-site problem. They are ratchets, and the ratchet is the
deliverable — not a sweep.

---

## 15. Traceability

Every requirement to its origin. Finding keys resolve in
[WP-Z §2](reviews/M-TESTQUAL-Z-findings-review.md); theme keys in WP-Z §3.

| Req | Origin |
|---|---|
| R1 | theme `T2`; `H-2`, `D-5`, `D-7`, `D-8` |
| R2 | `G-7`, `H-3`, `F-3`, `E-8`, `H-7`, `D-1` |
| R3 | theme `T3`; `A-8`, `H-6`, `G-3`, `B-5` |
| R4 | `H-2`; C6 ledger precedent |
| R5 | `H-2`, `G-16`, `A-1`; M-TESTBASE P2 hash precedent |
| R6 | theme `T3`; `H-5`, `G-3`; NEW-APP-CHECKLIST §3 |
| R7 | M-TESTARCH §4 I1/I2; `A-3` |
| R8 | M-TESTARCH §4; `H-5`; EXP-024 pricing |
| R9 | 21 HOLLOW + 14 BROKEN; `B-15`'s "writing the reason is the audit" |
| R10 | `A-12`; BP-068 negative-suite precedent |
| R11 | `E-6`, `F-20` |
| R12 | `E-6`, `F-15` |
| R13 | derived; no finding — declared as a prior, not evidence |
| R14 | `F-4`, `G-1`, `H-1` (theme `T1`) |
| R15 | theme `T1` recurrence-stopper |
| R16 | `B-14`; `H-10` (the `persisting` value) |
| R17 | `F-9`, `E-15`, `C-12`, `C-15`, `B-6`, `B-7` |
| R18 | `A-14`, `G-2`, `F-15` |
| R19 | `H-10`, `B-5` |
| R20 | `B-4`; clusters `C7`–`C11` |
| R21 | `C-7`, `E-3`, `F-8`, `G-14` |
| R22 | M-TESTARCH §3b.1/§3b.4 |
| R23 | 253 sleeps measured; `H-9` |
| R24 | `A-11`; M-TESTBASE P1 |
| R25 | `C-18`, `C-2`; M-TESTARCH §3b.3 item 1 |
| R26 | M-TESTARCH §3b.3 item 4 |
| R27 | M-TESTARCH §3b.3 item 2; `H-8` |
| R28 | `C-5`, `D-2`; 262 skip sites |
| R29 | `A-7`, `A-6`, `E-14`; TASK-573 |
| R30 | `F-19`; M-TESTARCH precedence §5 E5, §3.1 generation rule |
| R31 | `app/tools/suite/serialdbg/_gate.py:129` |
| R32 | `G-10` |
| R33 | `A-6`, `F-12`, `A-4` |
| R34 | `D-4`, `G-16`; M-TESTARCH §6 |
| R35 | `B-15`; EC-G6 |
| R36 | `B-1`, `B-2` |
| R37 | `C-6` |
| R38 | `C-5`, `C-4`; EC-G8 |
| R39 | `C-8`, `C-9`, `C-10` |
| R40 | `C-3` |
| R41 | `B-12`; M-TESTARCH §2.3 |
| R42 | `A-18` + the nine-mirror register; LL-114 |
| R43 | `D-6`, `D-16`, `C-13` |
| R44 | `F-18`, `G-15`, `H-18` |
| R45 | `A-17` |
| R46 | `A-15`, `F-2`, `G-11`, `B-13` |
| R47 | `A-4`, `A-2` |
| R48 | `A-12` |
| R49 | `A-2`; M-TESTARCH precedence §4 |
| R50 | M-TESTARCH precedence §5 E4; `E-13`; TASK-426 |
| R51 | TASK-557 pin; `run/lib.sh:16`; `F-19` |
| R52 | `E-1`, `E-16`, `D-13`, `E-12`, `F-17` |
| R53 | M-TESTARCH §10 OQ-D; `B-18` |
| R54 | `D-13`, `F-17`, `E-12`, `E-6`, `B-16` |
| R55 | M-TESTARCH §2b (T4) |

---

## 16. Where this builds on what exists — and what it does not re-propose

Named explicitly so a reader does not read a funded, landed item as new work.

| Already exists | Requirements that build on it |
|---|---|
| `lib/dut.py` — port resolution, DRD reset gap, boot deadlines, the setup-failure contract (M-TESTBASE P1) | R47, R48, R49 tighten adoption; none re-proposes the layer |
| `get player` — the aggregated player vector with FNV order hashes (M-TESTBASE P2) | R5 reuses the hash construction for render signatures |
| `get idle` / `hasInFlightOp()` (M-TESTBASE P4, TASK-518) | R22, R23 consume it; R26 extends past it |
| The `NOT-RUN` bucket, class-ordered dispatch, exit 4 (TASK-566, M-TESTARCH precedence) | R28 adds one value; R31/R38 fix what gating reads |
| The flake policy — pre-declared, retried once, own bucket | R21, R37 constrain where it may be used |
| `check_docs` C6 id binding + the exception ledger (TASK-521) | R4, R34, R46 extend it; the ledger pattern is reused four times |
| `check_app_conformance.py`, `check_settings_wiring.py` — generation from `APP_ORDER` / the settings struct | R3, R15, R41 add rows; nothing invents a second mechanism |
| `check_test_meta.py` — record well-formedness | R9, R16, R35 give it things to assert are *true*, not merely present |
| `run/player-gate` — a gate with its own tests and a declared pass set | R29's artifact replaces its `sed` parser; the pass-set idea is kept |

**Explicitly deferred by M-TESTBASE and left deferred here:** the T1 host tier and the Arduino shim,
T2 mock infrastructure, the runner split beyond what has landed, the directory move, and the
generalised conformance matrix over all 13 apps. R41 is the only one this document touches, and it is
a SHOULD.

---

## 17. Open questions

1. **Who owns the observability contract?** R3 and R6 place an obligation on firmware work that VE
   cannot schedule. The natural home is `NEW-APP-CHECKLIST.md` (Architect-owned) with the gate in
   `gate/` (VE-owned), but the admission rule — *no FEATURE test counted until the contract is met* —
   is a policy decision for @PM.
2. **What is the render-signature's real cost?** R5 asserts a hash over a drawn region is cheap
   because the order-hash precedent was free. That precedent hashed a 256-entry `uint16_t` array, not
   a framebuffer region, and the debug build is the constrained one (A4). This needs pricing before
   R5 is promised, exactly as the fault surface was priced.
3. **Does `UNMET` need a fifth exit code?** R28 adds a verdict; R38 makes it block. Whether a run
   whose CORE preconditions could not be established should exit 1, 4, or something new is a
   consumer-contract question with the enumerated consumers behind it.
4. **How is a falsifier declared for a physical fault?** R9 requires the declaration; R11 executes it
   on a schedule. The declaration syntax for "remove the SD card" is a design decision, and a bad one
   would make R9 unwritable for exactly the tests that need it most.
5. **Does AC13's shuffle apply within FEATURE?** Shuffling 167 FEATURE ids maximises the chance of
   finding leakage and also maximises the run's cost and its diagnostic difficulty. Per-family shuffle
   is cheaper and weaker. Not decided here.

