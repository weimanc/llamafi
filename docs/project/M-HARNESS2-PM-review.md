# M-HARNESS2 — Project Manager review and programme decision

> Owner: **Project Manager**
> Status: review — **a proposal. No board was edited.** Every task id below that does not already
> exist on a board is marked **(prov.)** and is a suggestion for the human to schedule.
> Written: 2026-09-03
> Reviews, in the order they were written and must be read:
> [M-HARNESS2 requirements](../verification/M-HARNESS2-requirements.md) (@VE, 55 reqs) ·
> [Architect review](../architecture/designs/M-HARNESS2-architect-review.md) (ACCEPT 42 / AMEND 12 /
> REJECT 1 / DEFER 1) ·
> [Developer review](../architecture/designs/M-HARNESS2-DEV-review.md) (~154 engineer-days) ·
> [QM review](../quality/M-HARNESS2-QM-review.md) (21 of 55 are BPs that did not hold; ~30 ungated days)
> Against: [WP-Z §4](../verification/reviews/M-TESTQUAL-Z-findings-review.md) (41 proposed tasks) ·
> [tasks.md](tasks.md) · [tasks-architecture.md](tasks-architecture.md) ·
> [tasks-winamp-player.md](tasks-winamp-player.md) · [roadmap.md](roadmap.md)
> Method: static only. No DUT, no serial port, nothing under `app/tools/` imported. The board is
> pinned to the `-DBOD_WATCH` debug build for TASK-557.

---

## 0. The programme decision

**I am scheduling ~30 engineer-days, not 154, and I am scheduling them as one programme with WP-Z
rather than two.** M-HARNESS2's diagnosis is the best-evidenced thing this project's quality history
contains and I am not arguing with it; what I will not do is fund seven months of engineering as a
lump against a project that also owes an unclosed hardware investigation (TASK-557), an @Architect
ruling that gates the whole execution queue (TASK-578), a class-order switch held since it landed
(TASK-566), and a feature milestone that has never been looked at on the physical LCD
(M-WINAMP-PLAYER). Phase 1 is the ~30 host-only days the QM identified as gated on nothing — it is
buildable today with the board pinned, it retires a class of false verdict that has already produced
one wrong REGRESS in production use (TASK-573), and it makes the registry smaller and more honest
rather than larger. Everything after Phase 1 is gated on a decision a human has not taken or on
board time that does not currently exist, and is marked so; the 55 requirements are re-graded from
"37 MUST" to "18 that block a phase exit", with roughly 60 days cut outright and the rest deferred
behind named entry criteria. I depart from the QM on one point and it is the one that matters
operationally: **the 80-minute session blocks Phase 2 onward, not Phase 1** — blocking the only work
that can proceed while the board is pinned, on a session that is itself blocked on a human decision,
would idle the programme for an interval nobody can bound.

---

## 1. What this project actually owes right now

The test-harness programme does not float above the board. It competes with these, for the same
@Developer and the same single serialised DUT.

### 1.1 The hardware investigation that has the board pinned

**TASK-557 (P2, open).** The supply sag is no longer a mystery — it is measured. `VDD3P3` dips
below the level-2 brownout threshold (indicatively ~2.5 V, a ~25 % sag) during WiFi init on 4/4
boots; ESP-IDF's brownout *interrupt* is what converts a survivable transient into a reboot loop;
with it cleared the board rides through (0 USB disconnects in 120 s against 77). Three further
things are established and all three are bad news for scheduling:

* **The sag is not boot-only.** Five `tag=run` trips from steady state, clustered with WiFi/TLS
  failures. The rail dips whenever the radio works hard.
* **The depth is not stationary across a day.** Production recorded a `BROWNOUT` reset at IDF's
  default threshold in the morning and by evening the sag stopped above level 1. That variability
  is the reliability issue and is why this read as intermittent for weeks.
* **Firmware cannot reach it.** The boot-inrush mitigation experiment — backlight duty and WiFi TX
  power, 4 variants × 2 thresholds × 3 reps — tripped 24/24. A clean negative, properly
  instrumented after two instrumentation faults were found and fixed. It needs a meter, the
  GPIO35/ADC1_CH7 divider, or a hardware change, and all three need a human at the bench.

**Consequence for every plan in this document:** the board stays on the `-DBOD_WATCH` debug build
indefinitely, with no date. Production must not be restored.

**A ruling nobody has made, and I am making it here because three phases depend on it:** the pin is
"do not restore *production*", not "do not reflash". Rebuilding and flashing the *same* debug env
with added `SERIAL_DEBUG` code is inside the pin, provided `-DBOD_WATCH` survives every commit and
no flash happens inside a TASK-557 measurement window. That materially unblocks the firmware phase
below, which all three reviewers wrote as though it were blocked.

### 1.2 The rulings and holds the queue is gated on

| Item | State | What it gates |
|---|---|---|
| TASK-578 | OPEN, @Architect — brownout ISR: fix the supply, keep the clear as a debug-only rig affordance, or promote with a bounded window | The M-ARCH execution queue names this and TASK-557 as its two gates |
| TASK-566 | PARTIAL DONE, **order switch HELD** — runner landed inert, order diff taken (210 ids, all 210 move, 6 505 inverted pairs), 3-run baseline taken with **7.1 % flake exposure, non-stationary across the first two runs alone** | The whole precedence hierarchy's payoff: a CORE failure costing ~6 min instead of ~40 |
| TASK-567 | DEFERRED behind 566's baseline — 187 remaining `skip()` sites | Verdict honesty across the corpus |
| TASK-575 | FIXED host-side, **full `run/test` pass owed** once the board can hold a session | Every timeout in the harness just got tighter and nothing has re-run |
| TASK-576, TASK-577 | OPEN, both blocked on TASK-557 | Monitor-fd staleness; the SD-write workaround revert |
| TASK-243 | External blocker — Spotify 403 for the owner account | Twelve permanently-skipped ids; live-playback oracles |

### 1.3 The feature milestone

**M-WINAMP-PLAYER — paused, 12 active entries.** The hard chain `424 → 420/421` is now unblocked
(TASK-424 closed 2026-09-01 as PATCH-TLS-1 — it was never an SD defect). TASK-419 is READY and
TASK-422-D is runnable. The milestone's own record names its largest unmitigated risk plainly:
**no human has viewed Player mode on the physical LCD**, everything is serial-asserted, and
LL-109/BP-048 exist because that gap has bitten before. That is a *direct* competitor to this
programme for board time, and it is the one item on the boards where a human eyeball is the
instrument.

### 1.4 The rest, briefly

M-TESTARCH is IN PROGRESS with its final step held. The M-ARCH board carries 61 entries with real
open research in it (TASK-462's dispatch-chain risk, TASK-480's runner split owing a stable-rig
baseline, TASK-522's ~6 KB reclaim). `check_docs`'s C3 is advisory with a standing count that grew
from 58 to 60 **during this review cycle** — the three M-HARNESS2 documents added two of them.
WP-Z's 41 tasks are unscheduled. Five M-CLOCK-STYLES exit criteria are booked PASS against oracles
that cannot observe them.

**Summary of the owing.** One hardware investigation only a human can close; one @Architect ruling;
one held switch whose baseline is non-stationary; one paused feature milestone whose largest risk is
a human looking at a screen; a 130-finding remediation backlog; and an advisory gate that is
decaying while we write about decay. A 154-day programme is not fundable against that. A 30-day
host-only phase that needs none of the contended resources is.

---

## 2. Reconciling the two proposals into one programme

WP-Z proposed 41 tasks. M-HARNESS2 implies ~154 engineer-days. The Developer measured ~38 of those
days as already sitting on WP-Z's board; the QM measured ~30 days as gated on nothing at all. Those
three numbers are not in conflict — they measure different things — and the useful one is the QM's,
because it is the only one that answers *what can start*.

**Adjudication, where the reviews disagree:**

* **On the total.** The Developer's 154 is right as arithmetic and wrong as a decision input; the QM
  is right that it is over-stated on the retrofit half (the 27 body removals take ~19 % off the
  213-id denominator before anything else happens, and he does not credit them back) and under-stated
  on the mechanism half (the session layer is a hard precondition of the replay recorder). **I take
  the QM's ~30 as the number I schedule and the Developer's per-row anchors as the estimates inside
  it.** No total above 30 is committed by this document.
* **On what a declaration is worth.** The QM's ruling — *a declaration is a control only when
  something mechanically checks it against a fact the declarer does not control* — is the single
  most useful sentence in the three reviews, and it is backed by a measurement in this repo
  (`cls` declared on 6 of 213, `effect` on 3, 209 seeded values nobody typed). **I adopt it as
  binding on this programme.** It is what cuts R9's prose field, R16's authored declaration and
  R1's `oracle_reason`, and it is why AC3 and AC9 are struck as acceptance criteria.
* **On R44.** The Developer would cut it; the QM would delta-scope it. **The QM wins**, and the
  precedent is in-tree: C1-delta faced a worse ratio (274 of 576 broken) and moved, because it gated
  only newly introduced coordinates. Delta-scoped R44 costs ~0 days and cannot become C3.
* **On the ledger.** Both the requirements document and the Architect say "red on day one is the
  correct first result". The QM's record says that is false as stated: every gate that landed red
  *and stayed advisory* rotted; the one that landed red and worked (C6) landed **blocking with a
  shrink-only ledger**. **The QM wins, and it becomes a phase-exit condition below.**
* **On ordering the 80 minutes.** The QM makes it condition 1 and blocking on everything. **I
  partially reject this** — see §6.

### 2.1 WP-Z tasks subsumed by an M-HARNESS2 requirement (15)

These must not be scheduled twice. Where a WP-Z id appears in the table in §3, it is the M-HARNESS2
work; the WP-Z row is retired into it.

| WP-Z task | Subsumed by | Note |
|---|---|---|
| TASK-584, TASK-590 | R28 / R31 / R38 / R34 | the verdict vocabulary and the `UNMET` bucket are the general form of both |
| TASK-591 | R35 | the 43 CORE reason strings; writing them is the audit |
| TASK-592 | R20 | the edge scanners are the static half of order independence |
| TASK-593 | R3 (firmware half) | re-seated onto the shell per the Architect; see §3 Phase 4 |
| TASK-596, TASK-602 | R17 / R18 | one typed accessor plus one context-manager gate closes both |
| TASK-599 | R47 | one session layer; also the precondition of the replay recorder |
| TASK-600 | R7 | the generator-completeness clause, promoted to MUST by the Architect |
| TASK-603 | R34 + R4 + the Developer's delete list | the disposal path the id-retirement problem lacked |
| TASK-606 | R42 | the mirror-equality gate |
| TASK-607 | R23 / R24 | `wait_until()` is R22's named prerequisite |
| TASK-608 | R29 / R30 | the JSON artifact replaces the sidecar proposal, and answers TASK-619's `A-7` half |
| TASK-609 | R48 | six `__main__` guards plus the subprocess-import gate |
| TASK-613 | R44 | **cut to delta-scope only** — see §4 |

One near-miss the Developer did not map: **TASK-585** (the Stock fetch oracle's `-1` defaulting to
an unconditional pass across nine ids) is a specific live defect, not a requirement, but it must be
executed *in the same change* as R18's typed accessor or the accessor lands with its most valuable
consumer untouched. It is a row in §3, not a duplicate.

### 2.2 WP-Z tasks that stand alone (26)

Nothing in M-HARNESS2 covers these; they are ordinary defects with named fixes and they keep their
own rows.

* **The three armed injectors** — TASK-579, TASK-580, TASK-581. R14 *detects* the class; these
  *fix* the three known instances, and they are the three findings producing wrong verdicts today.
* **Single-defect corrections** — TASK-582 (an inverted guard that passes exactly on the
  regression), TASK-583 (a one-character teardown fix), TASK-588 (a skipped health check announced
  as `[health] PASS`), TASK-597 (a release gate whose health machinery cannot fire), TASK-594 and
  TASK-598.
* **TASK-586** is the exception that proves the rule: it is *inside* the Developer's delete list, so
  it is subsumed into the deletions row rather than standing alone.
* **Instrument repair** — TASK-589 (`run/screendump` hard-broken at import since TASK-555). This one
  is load-bearing: it blocks the pixel-oracle work twice over and is a prerequisite of Phase 4.
* **Record corrections** — TASK-587 (five milestone criteria to DEFERRED), TASK-611 (plan integrity,
  which pairs with R46's duplicate-id detection), TASK-595 (the flake sweep), TASK-604, TASK-605.
* **Hygiene and honesty** — TASK-601, TASK-610, TASK-612, TASK-614, TASK-615.
* **The four decisions** — TASK-616, TASK-617, TASK-618, TASK-619. Not schedulable by me; §5.

### 2.3 The one programme

One table, in §3. **A task appears exactly once.** If it is in the table it is not also on WP-Z's
board; if the human wants WP-Z's §4 pasted into `tasks.md`, the 15 subsumed rows must be dropped in
the same paste or a month gets paid twice.

---

## 3. The phases

Five phases, in the style M-TESTBASE phase 1 established: an entry criterion that is checkable, an
exit criterion that is a count rather than a judgement, and — new here, because this project has
funded work that nothing could stop — **a stop-the-work criterion: the result that would make me
cancel the rest.**

Two conditions apply to **every** phase and are not repeated per row:

* **No gate lands advisory.** A new check lands either at zero, or blocking with a dated,
  owned, shrink-only ledger whose stale rows are themselves blocking failures. This is C6's
  pattern and it is the QM's condition 4; it is the difference between C6, which works, and C3,
  which grew from 58 to 60 during this review.
* **No declaration ships without a mechanical check behind it.** QM condition 3, adopted verbatim.

### Phase 0 — decisions and the free win

*Nothing here is engineering.* Entry: none. Owner: human, @QM, @Architect.

**Exit:** TASK-616, TASK-617 and TASK-618 ruled; LL-127 and LL-140 promoted or explicitly dismissed;
the five ADRs the Architect requires exist as documents, even if only as filed questions.

**Stop criterion:** none. This is the cheapest action available anywhere in the review and there is
no result that would make me stop it.

### Phase 1 — host-only foundation (~26–30 d, buildable today)

**Entry: none.** This is the phase's entire justification — every row is host-only, needs no board,
no ADR and no graded finding, and is unaffected by whether the board is pinned for another week or
another quarter.

**Exit — all counts, none arguable:**

* Ids with no reachable `fail()`, or a body that is one unconditional `skip()`: **0**.
* CORE ids with a declared class and a written reason: **43 of 43**.
* Gating-class ids whose precondition needs the network or the host file layout: **0**.
* Consumers parsing the human summary text: **0**.
* Modules opening a serial port at import: **0**.
* Every run emits a schema-versioned artifact carrying the run's premise, and every gate reads a
  typed verdict rather than a string prefix.
* `run/check` wall clock **≤ 90 s**, `run/check-docs` **≤ 15 s**, measured and printed by the
  scripts themselves.

**Stop criterion:** if after the four irreducible days (typed verdict, the artifact, the deletions)
the artifact cannot retire all three summary parsers, or `run/check` cannot be held under 90 s with
the new gates in it, **stop and re-scope the whole programme**. The mechanism half is the part that
pays for itself in the first month; if it does not, nothing downstream will.

### Phase 2 — the 80-minute session (board; **BLOCKED on a human decision**)

**Entry: TASK-618 resolved** — either the Architect's verify-and-refuse conversion has landed, or a
dated exception is sanctioned. Nothing else in this phase can start first, and killing the script
mid-flight is not a workaround: it races the trap-guarded restore and can boot-loop the board.

**Exit:** each of the three armed-injector clusters confirmed or refuted with a dated record; both
isolated-vs-in-suite splits measured; the CORE skip census taken; the three cluster fixes landed.

**Stop criterion — and this is the one I most want on the record:** if the session **refutes all
three clusters** (the blast radius reads near zero rather than the predicted thirteen-plus ids),
group STA drops from foundation to hygiene, Phase 3 is cancelled, and the corpus retrofit in
Phase 5 is cut to the delta-scoped rules only. Three static predictions are the evidential base for
the largest requirement group in the document; if they are wrong, the group is not justified.

### Phase 3 — order and state hygiene, and the switch question (board)

**Entry:** Phase 1 complete; Phase 2 complete and its stop criterion not triggered; TASK-557 closed
or explicitly signed off by the human.

**Exit:** armed device state is enumerable and asserted at every test boundary, with the failure
landing on the test that armed it; per-family shuffled runs produce the canonical verdict set;
TASK-617's exit criteria met and the switch decision re-put to the human with evidence rather than
inference.

**Stop criterion:** if demoting the seven network-dependent CORE ids plus the host-file-grep id
leaves CORE with too few members to gate anything meaningful, **cancel the class-order switch
outright** and close TASK-566 as WONTFIX rather than keep engineering toward a hierarchy whose top
layers are empty. A gating class that gates nothing is worse than no gating class, because it
carries a gate's authority.

### Phase 4 — the observability contract (firmware; per-app, never a sweep)

**Entry:** ADR A (does `App` gain a debug surface) and ADR B (is GRAM readback the sanctioned render
mechanism) taken; `run/screendump` repaired; `.dram0.bss` headroom **re-derived fresh** from
`run/build-debug` and the `.map` immediately before each commit, never remembered. Permitted while
the board is pinned, per §1.1's ruling, provided `-DBOD_WATCH` survives every commit.

**Exit:** the shell-side identity guard and tick/repaint counters landed (this fixes the
answer-when-not-active defect for all thirteen apps, including the four with no `dbgGet` at all);
a signature command with ink and distinct-colour metrics exists and is preconditioned on a live
readback channel in the HEALTH class; every visual claim either has a mechanism or is carried as a
dated `UNOBSERVABLE` record with an owning task; no milestone exit criterion rests on an
`UNOBSERVABLE` id and carries a PASS.

**Stop criterion:** if a freshly derived `.dram0.bss` headroom reads under ~1 KB, **stop after the
shell half** and ledger the per-app clauses. This project has measured that pool at 0 B, 40 B,
304 B and 9 920 B inside three months; the shell half is ~60 B and pays for itself, the per-app half
is not worth a link failure.

### Phase 5 — the ratchets (open-ended, delta-scoped)

**Entry:** Phases 1 and 3. **Exit:** each ratchet count is printed by the thing developers already
run, and has fallen across two consecutive milestones.

**Stop criterion:** any ratchet whose count is unchanged across two consecutive milestones is **cut,
not carried**. That is C3's lesson applied in advance, and it is the only defence against a rule
that reads the same number in a year.

---

## 3a. The single sequenced programme

**One table. Every task appears exactly once.** Ids marked **(prov.)** do not exist on any board and
are proposals; the rest are WP-Z's provisional ids or ids already in use. Day figures are the
Developer's per-row anchors, re-apportioned where a requirement was split or cut. "Source" is the
requirement id, the WP-Z finding key, or the reviewer who raised it.

| task | phase | title | depends on | days | source |
|---|---|---|---|---|---|
| TASK-616 | 0 | decision — does the M-WEBRADIO close stand | human | — | WP-Z §4.4 |
| TASK-617 | 0 | decision — may the class-order switch flip | human | — | WP-Z §4.4 |
| TASK-618 | 0 | decision — DUT entry points own firmware lifecycle | human | — | WP-Z §4.4, R51 |
| TASK-619 | 0 | decision — artifact as interface; the generated-module and effect-axis questions | @Architect | — | WP-Z §4.4 |
| TASK-621 (prov.) | 0 | promote LL-127 and LL-140, or dismiss each with a reason | human sign-off | 0 | QM §6.3 |
| TASK-622 (prov.) | 0 | file the five ADRs as documents (App debug surface, render mechanism, console as interface, result artifact, DUT firmware lifecycle) | — | 1 | Architect §9 |
| TASK-609 | 1 | six `__main__` guards + import-in-subprocess gate with a stubbed transport | — | 1.5 | R48 / `A-12` |
| TASK-600 | 1 | generated key list sees `.cpp` bodies; count compared full-tree in `run/check` | — | 1 | R7 / `A-3` |
| TASK-623 (prov.) | 1 | cross-check the flake registry against declared gating classes | — | 0.25 | R37 / `C-6` |
| TASK-624 (prov.) | 1 | closed verdict enum incl. `UNMET`; typed gating; `UNMET` blocks; inversion selftest arm | — | 2.5 | R28/R31/R38 |
| TASK-608 | 1 | schema-versioned run artifact with the run's premise; retire all three summary parsers | TASK-624 | 2 | R29/R30, Dev D2 |
| TASK-584 | 1 | six residue callers convert the regression to a skip — make them fail | TASK-624 | 0.5 | `D-2` |
| TASK-603 | 1 | delete 19 ids, retire 8 bodies to an `UNOBSERVABLE` ledger, no-reachable-fail gate | TASK-624 | 2.25 | R34/R4, Dev §8 |
| TASK-625 (prov.) | 1 | write the id-retirement procedure into `docs/process/` | TASK-603 | 0.25 | Dev D7 |
| TASK-587 | 1 | five clock exit criteria re-recorded DEFERRED, not PASS | TASK-603 | 0.5 | `H-2` |
| TASK-591 | 1 | declare all 43 gating-class ids with written reasons; gate on an undeclared class | — | 1.75 | R35 / `B-15` |
| TASK-626 (prov.) | 1 | a gating class may not need the network or the host file layout — gate + demotions | TASK-591 | 2 | R36 / `B-1`,`B-2` |
| TASK-596 | 1 | one typed accessor; no oracle or restore satisfied by a default | — | 2 | R18 / `A-14` |
| TASK-585 | 1 | the Stock fetch oracle's sentinel is an unconditional pass across nine ids | TASK-596 | 1 | `G-2` |
| TASK-602 | 1 | restore via a context manager; gate on *use of the manager*, not on static matching | — | 2 | R17 / `F-9` |
| TASK-627 (prov.) | 1 | print the per-scope SKIP count in the run summary | TASK-608 | 0.5 | QM §7 |
| TASK-611 | 1 | plan integrity: id collisions, stale rows, duplicate-body detection | — | 2 | R46 / `F-2` |
| TASK-628 (prov.) | 1 | replay engine in `lib/`: stub transport, keyed store, virtual clock, plus its negative test | TASK-609 | 4 | R10 engine, Dev D1 |
| TASK-629 (prov.) | 1 | host-gate wall-clock budget, measured and printed by the scripts | — | 0.5 | Dev D6, Arch §8.4 |
| TASK-630 (prov.) | 1 | scaffold the record — emit the generated fields, leave the author the two that need thought | TASK-624 | 0.5 | Dev D4 |
| TASK-631 (prov.) | 1 | a FAIL carries the last 20 command/reply pairs | TASK-628 | 0.5 | Dev D3 |
| TASK-632 (prov.) | 1 | dispose of the advisory documentation check: promote with a ledger, or delete it | — | 1 | QM §3.1 |
| TASK-633 (prov.) | 2 | DUT entry points verify-and-refuse; delete the restore trap; update `CLAUDE.md` | TASK-618 | 1.5 | R51, Arch §6 |
| TASK-634 (prov.) | 2 | run the 80-minute session and file its dated records | TASK-633 | 0.5 | WP-Z §5 |
| TASK-579 | 2 | the WebRadio forced-connect-fail injector nothing clears | TASK-634 | 0.75 | `F-4` |
| TASK-580 | 2 | the heatmap injector wedges the sub-view and the block behind it | TASK-634 | 0.5 | `G-1` |
| TASK-581 | 2 | the aircraft injector freezes the radar for the rest of the boot | TASK-634 | 0.25 | `H-1` |
| TASK-582 | 2 | an inverted guard that passes exactly on the regression | TASK-634 | 0.25 | `C-1` |
| TASK-583 | 2 | the error-suite teardown writes the wrong state | TASK-634 | 0.25 | `F-1` |
| TASK-588 | 2 | a skipped health check announced as a health PASS | TASK-624 | 0.5 | `C-4` |
| TASK-597 | 2 | the player gate's health machinery cannot fire | TASK-624 | 0.5 | `E-13` |
| TASK-595 | 2 | sweep the flake registry against its call sites, both directions | TASK-579 | 0.5 | `C-7`,`E-3`,`F-8` |
| TASK-589 | 2 | repair the screendump instrument, broken at import | — | 1 | `A-1` |
| TASK-635 (prov.) | 3 | armed device state enumerable; boundary check attributes the leak to the arming test | TASK-608 | 3 | R14 |
| TASK-592 | 3 | add the readiness-skip and unrestored-set scanners to the edge enumeration | TASK-602 | 1 | `B-4` |
| TASK-636 (prov.) | 3 | per-family shuffle capability and the order-dependent verdict value | TASK-624 | 1.5 | R20/R21 |
| TASK-594 | 3 | two ids whose own predecessors destroy their precondition | TASK-636 | 0.5 | `B-3` |
| TASK-604 | 3 | six ids drive a different app than their record says | — | 0.5 | `E-5`,`F-11` |
| TASK-605 | 3 | two ids reach their app only because of what ran before them | TASK-634 | 0.5 | `E-11`,`F-6` |
| TASK-575 | 3 | the owed full suite pass after the timeout fix | TASK-633 | 0.5 | board |
| TASK-637 (prov.) | 4 | shell-side identity guard + tick/repaint counters — fixes the class for all thirteen apps | ADR A | 1.5 | Arch §1.2, §10 |
| TASK-638 (prov.) | 4 | render signature over panel readback, ink/entropy metrics, time freeze, readback liveness check | ADR B, TASK-589 | 3.5 | R5 as amended |
| TASK-593 | 4 | per-app result and entry-state observables, one app per commit, capped per app | TASK-637 | 4 | R3(c)(d) |
| TASK-639 (prov.) | 4 | the clock family is rewritten, not migrated — ledger five claims, re-file as new ids | TASK-638 | 1 | Dev §8.2 |
| TASK-607 | 5 | one wait helper, one app-entry helper, one timeout policy with users | TASK-608 | 3 | R22/R24 |
| TASK-640 (prov.) | 5 | classify all synchronisation sleeps, publish the three counts, then set the floor | TASK-607 | 2 | R23, Arch §5.1 |
| TASK-606 | 5 | mirror-equality gate, pairs generated wherever the symbol is already generated | — | 4 | R42 / `A-18` |
| TASK-613 | 5 | a numeric bound in an assertion **you touch** cites its origin — delta-scoped only | TASK-606 | 0.5 | R44, QM §3.5 |
| TASK-599 | 5 | one session layer; migrate the four bypassing harnesses | TASK-609 | 4.5 | R47 / `A-4` |
| TASK-641 (prov.) | 5 | generate the read-key set; the author declares a claim class from a closed enum | TASK-628 | 4 | R1 as amended |
| TASK-642 (prov.) | 5 | two-field falsifier: executable replay, and physical with an enforced expiry | TASK-641 | 3 | R9 as amended |
| TASK-643 (prov.) | 5 | mutation driver with the control arm; a transcript miss is inconclusive, never a confirmation | TASK-642 | 2 | R10 driver |
| TASK-601 | 5 | the TLS preflight runs from every entry point, not one | TASK-599 | 0.5 | `A-5` |
| TASK-610 | 5 | collapse 26 ids to about 11 behaviours | TASK-603 | 1.5 | `B-16` |
| TASK-612 | 5 | scope resolution for the 55 % of the tree it cannot reach | — | 1 | `B-9`,`B-10` |
| TASK-614 | 5 | registry and tooling honesty | TASK-603 | 1.5 | `B-13`,`F-12` |
| TASK-615 | 5 | small correctness debts with named fixes | — | 1 | `H-17`,`C-17` |

**Totals: Phase 0 ~1 d · Phase 1 ~28.5 d · Phase 2 ~6 d · Phase 3 ~7.5 d · Phase 4 ~10 d ·
Phase 5 ~28.5 d ≈ 81 engineer-days, of which only Phase 1 is committed by this document.**

Three notes on the table:

* **TASK-586 and TASK-598 do not have rows** — they are inside the disposal row (the registry copy
  of the player id and the three duplicated tap-guard ids are on the Developer's delete list).
  Scheduling them separately would be the double-booking this table exists to prevent.
* **The five ADR ids are provisional too.** The highest ADR in use is ADR-062, so the Architect's
  A–E would be **ADR-063 … ADR-067 (prov.)** if the human takes them.
* **Phase 5 is deliberately not sequenced past its entry criteria.** Its rows are ratchets, and a
  ratchet with a date is a sweep wearing a ratchet's clothes.

---

## 4. What I cut, and what I defer

"All of it, later" is not a plan, so this section is specific. **Cut** means it is not in the
programme and I am not carrying it as debt. **Deferred** means it has a named entry criterion in §3
and is not funded now.

### 4.1 Cut outright (~60 days, and one instrument)

| What | Days back | Why |
|---|---|---|
| R44's retrofit — citing >1 000 existing numeric thresholds | 6 | A ratchet with no completion condition, which is the advisory documentation check's exact shape and will read the same number in a year. The **rule** survives, delta-scoped to lines you touch, at ~0 days. The Developer would cut it entirely; the QM would delta-scope it; the QM wins, on in-tree precedent. |
| R8 — injection surface parity | 3 | Firmware on a static pool this project has measured at 0 B, for a benefit the requirement itself says is unmeasured. Re-propose when an incident search names one soak bug it would have converted to a fast test. |
| R26 — the device pushes on change | 4 | Breaks the one-line request/response invariant every consumer assumes, on the memory-constrained build, for a win the quiescence work's own evidence suggests is correctness on ~10 keys. Both the Architect and the Developer say defer; I am going further and cutting it from this programme. |
| R53's budget table as a requirement | 0.5 | A "reported, not failed" MUST is a measurement, not a control. The per-class elapsed measurement survives inside the artifact; the table survives as a target with no authority. The 6-minute conformance row has no derivation and is dropped. |
| R11's quarterly hardware falsification campaign | 1 + board | The requirement predicts its own failure ("the first thing dropped under time pressure") and then grades itself SHOULD *for that reason*. Replaced by an enforced expiry on the physical falsifier field, which is a mechanism this repo already runs for flake declarations. |
| Three consecutive full shuffled runs as an acceptance criterion | ~3 board-h | ~3 hours of the scarcest resource on the project, once. Replaced by per-family shuffle triggered by a change to that family's file — a 5-minute run that happens thirty times beats a 3-hour one that happens once. The shuffle *capability* stays (Phase 3). |
| R1's free-prose oracle reason as a MUST | ~4 | The document grades it "the weakest link in the group" and then makes it a MUST. It survives as uncounted documentation for the residue after the generated key set and the closed claim-class enum have done the mechanical part. |
| R16 as an authored declaration over the legacy corpus | ~2 | The harness observes the effect for free on every run. Asking 213 authors to type a value the machine is about to compute is 213 chances to be wrong for no information gain, and the over-declaration clause makes one word a permanent free pass. Observe it, freeze it, fail on drift. |
| The rubric re-audit as **the** acceptance criterion | 1 subagent-day + the framing risk | A single-grader subjective scale with no inter-rater measurement cannot be the acceptance criterion for a programme. I am **not** funding a second grading pass either — it costs a day and buys a number we have already agreed not to gate on. Report the figure; never gate on it; never quote it as coverage. |
| Two counted-declaration acceptance criteria | 0 | A criterion satisfiable by typing measures compliance with typing. The falsifier count survives only as a denominator inside the *confirmed* figure; the effect count survives only in the harness-observed form. |
| The "37 MUST" grading itself | — | 55 requirements with 37 MUSTs has not made a decision. In this programme, **MUST means "blocks a phase exit"**, and 18 requirements have it. |

### 4.2 Deferred, with the entry criterion that would start them

* **The per-app half of the observability contract beyond the first three apps** — entry: the shell
  half landed and a freshly derived headroom above ~1 KB. The shell half fixes the actual defect for
  all thirteen apps; the per-app half is a coverage improvement and is priced per app.
* **Correlated replies** — entry: the console interface ADR. Additive form only (a sequence id
  supplied optionally and echoed when supplied), never the flag-day. There is exactly one id whose
  value is unlocked by it, and that id should be cited as its justification.
* **The generated conformance class** — entry: Phase 4 complete. The existing hand-copies are
  correct today; this is the biggest structural win and the least urgent.
* **Declared fixtures** — entry: somebody decides the declaration format. An undesigned declaration
  is a comment.
* **The session-level persisted-state snapshot** — entry: the per-test restores landed. It has a
  real interaction with the existing snapshot step, which currently erases the evidence of what the
  suite left behind, and that interaction is not worth resolving first.
* **The host unit tier** — unchanged, blocked on a host C++ toolchain this machine does not have.

---

## 5. The three escalated decisions

I do not decide (a) or (b). I recommend, I price being wrong, and I name what I need from the human.

### (a) Does the M-WEBRADIO close stand? — TASK-616

**Recommendation: keep the milestone closed; re-open the *criterion*, not the milestone.** The
sustained-decode half is a real result and I would not disturb it. The skip-rate half is
unfalsifiable as it was run — every trial played the same station, so the term had zero variance,
and the run records no build identity, so it cannot say what firmware it measured. Record that
criterion **DEFERRED** in its regression-suite entry (the same disposition I am recommending for the
five clock criteria), and re-run only the skip term once the board is released, with at least three
stations and a recorded build hash. Note also that this rig runs a station-visibility setting that
differs from the firmware default, which is one more reason a single-station trial proves little.

**Cost of being wrong.** If the skip rate is genuinely bad, we have shipped a radio app that skips
more than its criterion allowed — user-visible, not data-losing, and the app has been in daily use
with nothing on the record against it. If instead we re-open the whole milestone on a static
inference, we reopen a closed milestone whose re-run needs a firmware the board cannot currently
carry, and we do it on the strength of a reading rather than a measurement.

**What I need from the human:** a yes/no on "the criterion goes DEFERRED, the milestone stays
closed, the re-run is scheduled behind the board's release". If the answer is no and the milestone
reopens, it competes with M-WINAMP-PLAYER for the same board and I need to know which loses.

### (b) May the class-order switch flip? — TASK-617

**Recommendation: no, not yet — and set the exit criteria to the declaration and offline gates,
not to the shuffle.** I concur with the VE's reading and with the Architect's narrower criteria. I
add one condition neither of them states: **the switch must not flip while TASK-557 is open**,
because the baseline it would be judged against was captured across four boot generations with a
7.1 % non-stationary flake exposure, and re-ordering a suite against a moving baseline on a rig with
an unexplained supply fault produces a diff nobody can attribute.

**Cost of being wrong.** Flipping early: one gating-class failure from index 14 — and seven of the
43 need a live fetch, with one that fails rather than skips — marks all 167 remaining ids NOT-RUN,
and the suite reports a firmware-wide catastrophe caused by a network outage. That is precisely the
misattribution the milestone exists to end, delivered with a hierarchy's authority behind it.
Holding: a gating-class failure keeps costing ~40 minutes instead of ~6. We have paid that for
months and it has not stopped anything.

**What I need from the human:** agreement that the exit criteria are (i) all 43 gating-class ids
declared with written reasons, (ii) no gating-class precondition needs the network or the host file
layout, (iii) TASK-557 closed or explicitly signed off — and, explicitly, that the shuffle campaign
is **not** a precondition. If the human wants the switch sooner, the honest lever is (ii): demote the
network-dependent ids and the switch's risk collapses, at ~2 days.

### (c) How to unblock the entry points — TASK-618

**This one is mine to recommend and I do: adopt verify-and-refuse.** Test entry points read the
board's build identity, compare it to what the run declares, and exit with the "this board is not a
valid subject" code on a mismatch — they never flash and never restore. Flashing stays an explicit
caller action through the existing flash scripts, which is already how several of them behave.
`DUT_NO_RESTORE=1` is sanctioned **only** as a dated interim exception owned by TASK-618, whose
retirement condition is that conversion, and whose ledger row is itself a blocking failure when
stale.

The reason to prefer this over the flag is not elegance. The flag suppresses an unconditional side
effect, so every future reader must know which mode they are in to know what state the board is in;
verify-and-refuse removes the ownership error that a *test* entry point owns *firmware lifecycle*.
That coupling is a safety control which hardened into an obstruction when the context changed, and
it is currently the single thing blocking the most valuable measurement available.

**Cost of being wrong.** The Developer's correction to the Architect stands and I am taking it:
verify-and-refuse is smaller in concept and larger in diff. Every documented workflow that relied on
the board coming back on production learns about it the hard way, including the run-script table in
`CLAUDE.md`. Budget 1.5 days and a documentation update, not an afternoon. Doing nothing costs more:
Phase 2 never starts, the three cluster confirmations never happen, and the evidential base for the
largest requirement group stays a static prediction indefinitely.

**What I need from the human:** sanction to change the deliberate non-overridable in the shared
shell library, and explicit acceptance that after a suite run the board stays on whatever build it
was on. And the standing hazard restated in the same change: **never kill a flash, soak or test
script mid-flight** — it races the trap-guarded restore and can boot-loop the board.

---

## 6. The QM's five conditions, and the cheapest action

**The cheapest action is scheduled as Phase 0 and it is the first thing on this programme.**
Promoting LL-127 and LL-140 costs a human sign-off and no engineering. One of them names, three
weeks early and in full mechanical detail, the injector defect the largest audit package later
re-derived from source at considerable cost, and which two flake declarations have been misattributing
to network churn for about a year. The other is the `UNMET` bucket under a different name, proposed
2026-08-17 and never adopted. There is no version of this programme in which those two entries stay
`open` while we write a fourth review about enforcement.

**Ruling on the five conditions:**

1. **"Run the 80 minutes before spending the 154 days" — accepted in substance, amended in scope.**
   The QM's principle is right and this register carries it twice: elaborate secondary work performed
   before the primary result is in. But the session is itself blocked on a human decision, on a rig
   pinned for an interval nobody can bound, and Phase 1 is 30 days that do not depend on whether the
   three clusters are real — they fix a verdict-type defect that has already produced a wrong
   REGRESS, and they delete 27 bodies that assert nothing regardless. **So: the session is Phase 2's
   entry criterion, not Phase 1's.** I honour the QM's point where it actually bites, by making
   "all three clusters refuted" a stop-the-work criterion that cancels Phase 3 and guts Phase 5.
   If TASK-618 is resolved before Phase 1 finishes — which I hope — the session runs inside Phase 1's
   window and the question is moot.
2. **Fund the ~30, schedule nothing else yet — accepted**, and that is exactly what §3a commits.
3. **No declaration without a mechanical check — accepted in full**, and it is one of the two
   programme-wide conditions in §3.
4. **Every gate-first requirement carries the ledger clause; no new gate lands advisory — accepted**,
   and extended: the existing advisory documentation check is scheduled for disposition in Phase 1.
   We cannot add fifteen gates on top of an advisory one whose count grew during the review that
   found it.
5. **Validate the rubric instrument or replace it — I take the replacement.** Strike it as an
   acceptance criterion; accept the programme on the mechanical counts only. Funding a second grader
   buys a number we have already agreed not to gate on.

Both of the QM's two non-conditions are in the programme as rows: the per-scope skip count in the
run summary (an afternoon, and it is what would have made one cluster visible every run for a year),
and the shell-side identity guard and counters.

---

## 7. Honest sequencing risk — how my own plan fails

1. **The single point of failure is a human decision, not engineering.** Phases 2, 3 and 4 all sit
   behind TASK-618, TASK-557 or an ADR. This project's record on exactly that shape is not good:
   the supply investigation has run for weeks and its three most recent results are negatives; the
   class-order switch has been held since the day it landed; the brownout ruling has an owner and no
   date. **If TASK-618 is not decided within about two weeks, Phase 1 completes and the programme
   stalls with an excellent artifact schema and no suite that can be run against a board.** That is
   the most likely failure and I want it on the record before it happens.
2. **Phase 1 changes no verdict about the firmware.** Thirty days of typed verdicts, schemas and
   deletions produces zero new evidence that any feature works. The danger is that its completion
   reads as "the suite is fixed" while the twenty-one hollow ids are still there. Mitigation is that
   Phase 1's exit criteria are counts and one of them makes the registry *smaller* — I would rather
   report 186 honest ids than 213 with 35 that cannot fail.
3. **The advisory-gate failure mode is live and growing during the review that diagnosed it.** The
   count went 58 → 60 while these four documents were written. Fifteen new gates on that substrate
   is the most plausible way this programme rots, and the tell will be `run/check`'s wall clock —
   which is why the host-gate budget is a Phase 1 row and not a footnote.
4. **Double-booking.** WP-Z's 41 tasks and M-HARNESS2 will be scheduled twice unless §3a is the only
   board. The 15 subsumed rows must be dropped in the same paste that lands the rest.
5. **Ratchets with no floor.** Phase 5 is where the programme quietly becomes a slogan. The stop
   criterion — a count unchanged across two milestones is cut, not carried — is the only defence I
   have, and it depends on somebody actually reading the counts, which is why they must be printed
   by the thing developers already run rather than stored in a document.
6. **And mine.** This is the fourth full review pass over one proposal and the programme has
   consumed zero engineer-days so far. The analysis is now the largest sunk cost in it. If Phase 1
   has not started before the next review of anything, that is the finding, and it is about
   scheduling — which is my job, not the VE's.

---

## 8. What I would start on Monday

**Phase 1, day 1: the six import guards and the import-in-subprocess gate, the generated-key-list
glob fix, and the flake-registry cross-check** — one day, host-only, needs no board, no ADR and no
decision, and it closes the defect that reset the board during the audit that found it. In parallel,
**off the engineering budget**: take TASK-618 to the human with the verify-and-refuse recommendation,
and promote LL-127 and LL-140.
