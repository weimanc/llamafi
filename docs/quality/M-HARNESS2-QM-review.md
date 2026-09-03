# M-HARNESS2 — Quality Manager review

> Owner: **Quality Manager**
> Status: review — advisory; no register was edited, every LL/BP below is a **proposal**
> Written: 2026-09-03
> Reviews: [M-HARNESS2 requirements](../verification/M-HARNESS2-requirements.md) (@VE, 55 reqs)
> · [Architect review](../architecture/designs/M-HARNESS2-architect-review.md)
> · [Developer review](../architecture/designs/M-HARNESS2-DEV-review.md) (~154 engineer-days)
> Against: [lessons_learned.md](lessons_learned.md) (145 entries) ·
> [best_practices.md](best_practices.md) (72 adopted) · [audit_log.md](audit_log.md) ·
> [WP-Z findings](../verification/reviews/M-TESTQUAL-Z-findings-review.md) ·
> [M-TESTQUAL index](../verification/reviews/M-TESTQUAL-index-review.md) ·
> [rubric](../verification/reviews/M-TESTQUAL-rubric-review.md)
> Method: static only. No DUT, no serial port, no flash — the board is pinned per TASK-557.
> Nothing under `app/tools/` was imported (see §5.2 for why that sentence is load-bearing);
> gate sources were **read**, not executed, except one `./run/check-docs` before handover.

---

## 0. Verdict

**The diagnosis is right, the prescription is two-thirds a re-issue of practices this project
already adopted and did not keep, and the programme as scoped would install fifteen new controls
on top of a quality system that has never once checked whether a test result means anything.**
Of the 55 requirements, **21 restate a best practice already on the register that failed to hold**,
**9 restate a lesson recorded and never promoted**, and **25 are genuinely new** — and the new ones
are concentrated exactly where the project has no prior art at all (result semantics, gating
machinery, session hygiene), which is a good sign for those and a bad sign for the other thirty.

I **endorse proceeding, with five conditions** (§7). The single most important is an ordering one
and it is not in any of the three documents as a blocker: **80 minutes of board time comes before
154 engineer-days.** Three of the five P1 findings that justify the largest requirement group are
static predictions with a named, cheap confirmation that nobody has been allowed to run
(TASK-618). Committing seven months of engineering ahead of eighty minutes of measurement is the
same failure shape as `LL-115`/BP-048 part 3 — sophisticated secondary work performed before the
primary result is in — and this register already carries that lesson twice.

---

## 1. Q1 — Has this project already learned these lessons?

### 1.1 The claim under test

The requirements document says it targets "the six mechanisms behind" 130 findings rather than the
findings themselves, and §16 lists what it does not re-propose — but that list names *in-tree
machinery* (`lib/dut.py`, `get idle`, the flake policy), never a **rule**. Not one of the 55
requirements cites a BP or an LL. The traceability table (§15) resolves every requirement to a
WP-Z finding key or a design document; the quality register does not appear in it once.

That is the claim I tested, and it does not hold. Below, `already-BP` means the rule is on
`best_practices.md`, adopted, with human sign-off, and the audit found it violated; `never-promoted`
means the lesson is in `lessons_learned.md` with `Status: open` or `reviewed`, so it constrains
nobody; `new` means I could not find it in either register.

### 1.2 The mapping

Requirement ids are grouped by category, then by id. Note for the reader: a `already-BP` row is not
an argument against the requirement — it is an argument that **writing the requirement again is not
the intervention**, because writing it is what was tried last time.

| Req | Category | Existing register entry | Why it did not hold / note |
|---|---|---|---|
| R1 — vocabulary rule | already-BP | BP-016 (2026-05-30, "tests must assert causal behavior, not trivially-true defaults"); BP-013 (assert completions, not commands fired); BP-015 (test the firmware constraint, not a proxy) | BP-016 is R1 and R2 in one sentence, adopted three months ago, with the audit that produced it naming six of the ids this audit re-finds. It is a question to ask yourself, with no mechanism. See §1.3. |
| R2 — no self-write oracle | already-BP | BP-016's "what firmware defect would cause this assertion to fail?" | 21 HOLLOW ids answer "none". The rule was never converted into the one-line grep (`set X` … `get X`) that R2 now specifies. |
| R3 — app admission contract | already-BP | BP-024 (2026-06-08: VE authors a debug-variable spec **before** implementation; Developer ships `dbgGet`/`dbgSet` **with** the feature); BP-036 clause 3 (per-app cross-cutting checklist includes the debug surface) | BP-024 is R3 and R6 stated as a workflow. It held for LocalPlayer (ADR-059 D12) and for TASK-112's counters — the two families the audit grades best — and was simply not applied to Clock, Stock or WebRadio. A workflow rule with no gate holds exactly where somebody remembered it. |
| R4 — `UNOBSERVABLE` ledger | already-BP | BP-003, BP-035, BP-054 (the "prose-with-no-owner" family: a caveat needs a task id or an explicit marker); BP-034 ("blocked is not coverage") | Four adopted BPs already say a known gap must carry an owner and a number. `H-2` booked five criteria PASS instead — the failure is not that the ledger shape was unknown, it is that nothing refuses a PASS. |
| R5 — render signature | already-BP | BP-048 part 2 (2026-07-12, amended 2026-07-31): any pixel-level exit criterion **must** carry an explicit acceptance gate — a named harness or an explicit human eyeball — that blocks DONE | This is the most serious violation in the register. BP-048 exists *because* PlaneRadar shipped painting nothing and passed two reviews and a full DUT suite. `H-2` is BP-048 breached exactly: five pixel-level criteria, no harness, no eyeball, all PASS. R5 is BP-048 with a mechanism attached, which is what it always needed. |
| R6 — observable ships with the feature | already-BP | BP-024; BP-025 (never ship the writer without the reader) | `H-5` is BP-025 inverted — a reader-less injector — and BP-025's rule does not cover it because it is written about suppression flags, not instruments. One clause short. |
| R8 — injection surface parity | already-BP | BP-034 (2026-06-14: "Developer must expose injection interfaces for any new complex input format at feature implementation time") | Both halves failed at once in `H-5`: the injector was built and the test that needed it was left a permanent SKIP whose docstring says no such hook exists. BP-034 has no discoverability clause; R8's generated injector list is the missing half. |
| R12 — negative assertion proves its channel | never-promoted | **LL-127** (2026-08-14, `Status: open`): a fault-injection gate must assert the injected fault fired, not just that the outcome matched | See §2.1. This is the sharpest failure in the episode: LL-127 names `set wrDeadUrls`, `_debugForceConnFail` and the short-circuit, three weeks before WP-F re-derived them from scratch as `F-4`. |
| R14 — armed state enumerable | new (mechanism) | ancestry in BP-025 | The *enumeration* is new and is the only requirement that catches the fourth instance. Keep. |
| R15 — injector cleared on `resume()` | already-BP, ungeneralised | BP-032 (from LL-068): `resume()` must reset the fetch timer so re-entry behaves | The project already ruled that `resume()` owns per-visit state. Nobody generalised it from `_lastFetch` to injection flags, and three subsystems then made the same omission. |
| R16 — declared `effect` | new | — | No prior art. See §4 for why I would not make it a declaration at all. |
| R17 — restore is a context manager | already-BP | BP-049 (2026-07-18, human-adopted after real user data loss): snapshot persisted state at session start, verify a fully-populated round trip at end | BP-049 is implemented as `run/test` steps 0b/5b — and `H-10` shows the suite writing flash ~50× per run *inside* that envelope, with the session-level restore erasing the evidence. The BP held at the session boundary and there was no rule at the test boundary. |
| R18 — no defaulted read | never-promoted | **LL-107** (2026-07-11): a fetcher's "success" sentinel equal to its "never fetched" sentinel produced two wrong VE tests | `G-2` is LL-107 exactly, in the harness rather than the firmware: `-1` for "bad read" is consumed as a satisfied threshold across nine ids. LL-107 was fixed in place and never generalised into a rule about sentinels. |
| R19 — session snapshot | already-BP | BP-049 | Adopted and implemented; R19's real content is the interaction with step 5b, which is new. |
| R20 — order independence by shuffle | new | project memory only (`feedback_isolated_rerun_vs_suite_state`) | The knowledge that an isolated rerun proves nothing about suite state is in the user's memory file and in `_order.py`'s design, never in a register entry. Genuinely new as a control. |
| R21 — `ORDER-DEPENDENT` outcome | already-BP, ungeneralised | BP-012 (tag known-intermittent tests; a count must name the failing test) | BP-012 created the flake category. `C-7`/`E-3`/`F-8` show every examined declaration mismatched with its call sites, in both directions — the category exists and its bookkeeping was never audited. |
| R22 — a wait is a failure bound | already-BP | BP-023 (2026-06-08: write a two-sentence sync contract — "this mechanism proves X; it is unreliable when Y" — before the first test that uses it) | BP-023 is R22 and R23's parent and it is a documentation rule. `H-9`'s undocumented `sleep(0.35)` is a mechanism with no contract, three call sites deep. |
| R23 — no bare sleep | already-BP | BP-023; BP-046 (a sync/quiescence claim is checked against the tool's source) | 253 sleeps against 2 named constants. |
| R24 — one timeout policy | new | — | Maintenance debt; correctly a SHOULD. |
| R25/R26/R27 — protocol | new | — | No prior art. The console has never been treated as an interface (the Architect is right that it has no IFC number). |
| R28 — verdict vocabulary, `UNMET` | already-BP + never-promoted | BP-059 (2026-08-11: a `skip()` reason states what the test observed, not an unverified cause); **LL-140** (`Status: open`): an assertion whose precondition never arose must report **inconclusive, not pass** | LL-140 is `UNMET` under another name, written 2026-08-17, never promoted, and its own case (`T_PMT_03`, a vacuous arena assertion) is the same shape as `C-5`. BP-059 governs the *text* of a skip; nothing governs its *status*. |
| R29/R30 — the artifact and its premise | already-BP (R30) / new (R29) | BP-062 (2026-08-15: a DUT measurement carries its conditions — commit, build variant, seconds since reset, network state — or it is not a measurement); BP-017 | `F-19` is BP-062 breached by a release gate: `run/wr-gate` cannot say what firmware it measured. R30 is BP-062 made machine-readable, which is the right move. R29 (the artifact as the sole interface) is new. |
| R31 — typed verdict | new | — | `_gate.py`'s `startswith("FAIL")` has no register ancestry. |
| R32 — structured reasons | already-BP, ungeneralised | BP-060 (label every diagnostic claim measured / inferred / assumed) | `G-10`'s three failure messages assert an unverified cause in prose while dropping the discriminating value — BP-060's exact prohibition, inside a test's output rather than a handover prompt. |
| R33 — one results layer | already-BP | BP-047 (a fix in duplicated logic extracts the helper or names the siblings); LL-145/BP-069 (one artifact absorbs everything of a kind because nothing else is designated to hold it) | `A-6`'s private pre-TASK-520 copy is BP-047's subject. The mechanism BP-069 describes — a thing accretes because nothing else may hold it — is exactly why four `SerialDut` clones exist. |
| R34 — no unfalsifiable coverage | already-BP + never-promoted | BP-034 ("blocked is not coverage"); BP-005/BP-010 (registry honesty); **LL-140** | `D-4`: an id whose body is one `skip()`, counted in the total, with the archived plan reading `Status: pass`. Three adopted BPs and one open LL all point at this and none of them can refuse a coverage figure. |
| R35 — declared class | new | — | The class hierarchy postdates every register entry. |
| R36 — gating class works offline | never-promoted | **LL-014** (2026-05-08: "don't blame the network without a positive test"); LL-096 | `B-1`/`B-2` let a network outage or a missing checkout directory declare the firmware untestable. LL-014's principle, one altitude up, never promoted. |
| R37 — no flake in a gating class | already-BP, ungeneralised | BP-012 | The flake registry is good work (§3.2). The coupling to gating was never specified. |
| R38 — `UNMET` blocks | new | — | Follows R28. |
| R39 — real HEALTH checks | never-promoted | **LL-014**; BP-017 (verify SERIAL_DEBUG before any VE test) | `C-9` certifies a board as knowing its network without ever comparing the SSID — an ACK-only check, the exact class the 2026-05-30 audit graded AMBER as "fire-and-forget". BP-017 is the one health-shaped BP and it checks firmware identity only. |
| R40 — every class dispatchable | new | — | `C-3` has no ancestry; it is a wiring defect. |
| R41 — generated APP class | already-BP | BP-047; BP-036 | `B-12`'s twelve hand-copied conformance rows are BP-047's subject verbatim, in the suite instead of the firmware. |
| R42/R43 — no mirrored facts | already-BP + never-promoted | BP-026 (2026-06-08: express count-derived constants symbolically — written **about `_TB_N`**); **LL-114** (2026-07-18, parse-don't-mirror; `Status:` TASK-335 filed, never promoted) | `C-13` is `_TB_N` again, three months after BP-026 was adopted about `_TB_N`. LL-114 established parse-don't-mirror for host tools and was never promoted, so the suite — a host tool — was never bound by it. `A-18` is right that nothing gates it. |
| R44 — cited thresholds | already-BP, ungeneralised | BP-015; BP-064 (cite symbols, not coordinates — and its **delta-scoped** enforcement) | See §3.4: I disagree with the Developer's "cut it" and with the VE's un-floored ratchet. Delta-scope it and it costs nothing. |
| R45 — generated code has a consumer | already-BP | BP-025 (never ship the writer without the reader); BP-041 (a kept build variant is gated in the same change or the flag is removed — gate-it-or-delete-it) | BP-041 is R45 for build envs, adopted 2026-06-27. `A-17`'s zero-importer generated modules are the identical decision for generated code, never taken. |
| R46 — ids exist once | already-BP | BP-010; BP-071 (a reservation lands in its board the moment it is claimed) | C6 exists and works; the holes (`B-13`, `F-2`) are parser gaps, not rule gaps. |
| R47 — one session layer | already-BP | BP-020 (the atomic pre-validation sequence, "do not issue the raw steps manually"); BP-014 (`Dut` ownership by assertion) | BP-020 told everyone to use the wrappers; four harnesses were built beside them anyway. A convention that is not enforced by the type is a convention. |
| R48 — import must not touch the board | **already-BP, and the BP is the hazard** | BP-009 (2026-05-24): "For Python tool scripts, confirm `python3 -c \"import module\"` from the new location" | This is the finding I care most about in §1. The WP-A agent that reset the board mid-audit was **following an adopted best practice**. BP-009's verification step is unsafe against six modules in this tree. R48 fixes the tree; BP-009 needs amending in the same pass. |
| R49 — typed rig-vs-device exit | never-promoted | **LL-135** (2026-08-16, `Status: open`): a test-harness defect presented as a firmware failure, and the standing instruction was to revert on exactly that signal | `A-2`'s four-file compliance is LL-135's mechanism left unbuilt. |
| R50 — fitness before, never after | already-BP | BP-017; BP-018 (reset discipline) | Already true in `run/dut-health`; R50 is the codification. |
| R51 — pinned build, never silently restored | **already-BP, and the BP is the obstruction** | BP-020 (the `trap EXIT` restore guarantee, adopted 2026-06-06 as a *safety* property) | See §3.3. BP-020's trap is precisely what blocks TASK-618 and therefore the 80-minute session. A control with no escape hatch became an obstruction when the context changed, and BP-020 carries no retirement criterion. |
| R52 — declared fixtures | already-BP | BP-037 (use the minimum-sufficient helper; don't inherit live-data gates); BP-038 (read the test spec before diagnosing infrastructure) | `E-1`/`E-16` are BP-037's own case (`T_WR_ERR_*` and their inherited station gate) recurring in the player family. BP-037 was adopted about these exact ids. |
| R53/R54/R55 — budget | new | BP-021 is adjacent (targeted runs for features, full suite for regression) | New. See §3.4 on whether a "reported, not failed" budget is a control. |
| R7 — versioned console | already-BP | BP-024; LL-114 | BP-024's "additive-only" convention is the half that held (M-TESTARCH OQ-C closed it on zero violations); the generator completeness half is `A-3` and is new. |
| R9/R10/R11 — falsifiers | already-BP, scope never extended | **BP-068** (2026-08-17: a gate ships with negative tests, and they break it the way it is meant to catch — "a gate that has only ever been observed passing has been read, not tested") | BP-068 is R9's entire argument, adopted three weeks ago, applied to *gates* and never to *tests*. Four deliberate breaks found three defects in a 180-line gate; nobody asked the same question of 216 test bodies until this audit. Extending BP-068's scope is cheaper and more credible than inventing a new `falsifier` field, and it is what R10 actually is. |
| R13 — never-failed report | new | BP-012 adjacent | Free once R30 exists. |

**Split: 21 already-BP-and-it-did-not-hold · 9 never-promoted · 25 new.**
(Counting `R3`/`R6` as one already-BP pair, `R25`/`R26`/`R27` as three new, `R42`/`R43` as one
already-BP row. Requirement-level counting, not clause-level.)

### 1.3 The one that matters most: BP-016 and the ids that came back

`best_practices.md` BP-016 was adopted **2026-05-30** from an audit in `audit_log.md` (2026-05-30,
"serialdbg test suite coverage quality") that classified all 78 tests then in the suite by assertion
strength. Its finding 3 named nine weak tests. Its finding 4 named five permanently-skipped ones.

Compare that list against the M-TESTQUAL rollup, three months later:

| Named 2026-05-30 | Verdict then | Verdict 2026-09-03 |
|---|---|---|
| an id asserting `scrollOffset=0` at startup | "pure observation with no assertion value" | **BROKEN** — body is now one unconditional `skip()`, archived plan still says `Status: pass` (`D-4`) |
| an id asserting a hardcoded chart range | "trivially true, no causal assertion" | **HOLLOW** — same id, now asserting two values its own `set triggerFetch 1` wrote (`G-7`) |
| the two `[MANUAL]` pixel ids | "GREEN (by design)" | **HOLLOW** — bodies are one `skip()` each, counted in the 213-id total (`G-16`) |
| the two ready-before-fetch ids | "inherently racy" | **BROKEN** — precondition destroyed by their own predecessors, never run in a full suite (`B-3`) |
| the `>= 0` liveness assertion | "field presence only" | still registered; the family's residue sibling is BROKEN (`D-2`) |

Five of the nine ids that BP-016 was adopted to fix are in the 2026-09-03 BROKEN/HOLLOW lists.
One of them got **worse under remediation**: WP-G records that "the TASK-112 audit-001 pass that
created `T178`'s body replaced a hardcoded-default tautology with a harness-write one". A task
filed by the QM audit, executed by the VE, closed as a fix, substituted one unfalsifiable
construction for another — because the rule it was executing said *assert something causal* and
nothing checked whether the value asserted was one the test had just written.

And BP-016 carries an escalation clause of its own: *"QM: flag trivially-true assertions in audits
as AMBER; escalate to RED if a suite has > 10 % trivial tests."* The measurement was never repeated.
It reads **16.2 %** (35 of 216) today. **The threshold existed, had a number, named an owner — me —
and had no cadence, so it never fired.**

The honest conclusion for Q1: **this project has learned almost all of these lessons and has no
mechanism for keeping any of them.** M-HARNESS2's real novelty is not its rules. It is that it is
the first document here to propose *enforcement* for them. That is worth funding, and it is a
different argument from the one the document makes about itself.

---

## 2. Q2 — Why did the existing controls fail?

The controls in force on 2026-09-02: 11 counted gates in `check_build.sh`, 6 documentation checks
in `check_docs.py` (4 blocking), a pre-declared flake registry with an enforced expiry, a
five-level test class hierarchy with a class-ordered runner, an id-binding gate with a dated
exception ledger, `check_test_meta.py`'s record well-formedness gate, `check_app_conformance.py`,
`check_settings_wiring.py`, `check_player_binding.py`, and 72 adopted best practices. That system
did not notice 35 registered tests that cannot fail, or three debug injectors that have been
wedging whole families for up to a year.

### 2.1 Cluster C9 — `set wrDeadUrls` (`F-4`)

**Which control should have caught it: `lessons_learned.md` itself, and it is the one I own.**

`LL-127` (2026-08-14) reads, in full and in the register today:

> `set wrDeadUrls` arms `_debugForceConnFail`, and `_play()` short-circuits on it *before* the
> audio path is reached … Prefer an injector that does not itself short-circuit the code under
> test (here: `set wrUrl`, which clears `_debugForceConnFail`, over `set wrDeadUrls`, which arms
> it).

Every mechanical fact in `F-4` — the flag, the short-circuit, the clearing command — was written
down **three weeks before** WP-F re-derived it from source. Twelve days after LL-127 was written,
two `flaky.yaml` entries were filed against `T_WR_COEX_01` and `T_WR_VOL_03` with
`symptom: "wrState=5"` and `dependency: "[NETWORK] — radio-browser.info station
availability/churn"`. `wrState=5` is the state that flag assigns.

Why the control did not fire, precisely:

1. **An LL is a memory, not a control.** `LL-127`'s `Status:` is *"open — proposed for BP
   promotion, human sign-off required"*, and it has been for twenty days. Nothing reads
   `lessons_learned.md` at gate time, at test-authoring time, or at flake-declaration time. Its
   only reader is a human who already suspects the answer.
2. **It was filed under the wrong subject.** LL-127 is written about a *fault-injection gate*
   (`task432_alloc_guard_gate.py`). The generalisable half — "this injector arms a flag that
   nothing in a test run clears, and here is the command that clears it" — was stated and never
   routed to @VE as a question about the suite. I wrote a firmware fact into a quality register
   and did not ask who else uses it.
3. **The flake registry recorded a cause it had not verified.** BP-059 (adopted 2026-08-11, three
   days *before* LL-127) says a `skip()` reason may state only what the test observed, and that a
   named cause must be verified independently first. A `flaky.yaml` `dependency:` field is a skip
   reason with a year's lease, and BP-059 was never extended to it. The entry is otherwise
   exemplary — dated, owned, evidenced, with an explicit reopen condition — which is what makes
   this instructive: the *form* was right and the *content* was an unverified attribution.
4. **The order scanner cannot see the shape.** `_order.py`'s edge enumeration reports 0→1 edges
   and, per `B-4`, cannot represent "a `set` in a body or reachable helper with no matching
   restore on all exit paths". The scanner's exception ledger (`EDGE_ADJUDICATION`) is forced to
   stay complete by `test_class_order.py` — a gate over a list that guarantees the list covers
   what the scanner found, and says nothing about what it missed. `C-19` shows one of those
   adjudications is itself wrong. **A ledger over an under-detecting scanner grants a false
   all-clear with a gate's authority.**
5. **BP-025 is one clause short.** "Never commit a suppression flag without the guard that reads
   it" would have caught a flag with no *reader*. `_debugForceConnFail` has a reader. What it has
   no path to is being *cleared*. No rule covers that.

Credit where due: the expiry on that flake entry (`review_by: 2026-09-26`) would have forced a
re-justification within three weeks, and the entry names its own reopen condition. That is the only
control in the system that was actually going to fire. It is dynamic, dated and attributable —
which is exactly the profile §3 identifies as the one that sticks.

### 2.2 Cluster C10 — `set triggerHeatmap` (`G-1`)

**Which control should have caught it: the run summary. It failed because SKIP is green and
unaggregated.**

`G-1` predicts seven ids exiting `SKIP: could not normalize to list view` **in every full-suite
run**, with a CORE id passing vacuously behind them. That is not a subtle signature — it is seven
identical skip lines, every run, for as long as the injector has existed. Nothing in the reporting
layer aggregates skips per scope, nothing compares a run's skip set against the previous run's, and
a skip prints green.

BP-012 (2026-05-25) is the nearest control and it stops one step short: it requires that a *count*
name the failing test, and it created a distinct FLAKE bucket precisely so a category of non-result
could not hide inside a pass/fail total. The same argument applies to skips with equal force and
was never made. WP-Z's own cheapest recommendation is exactly this: *"print the SKIP count per
scope in the run summary. A number that goes up when coverage disappears is most of what is
missing."* I agree, and I would add that it is an afternoon's work that has been available for
fifteen months of this suite's life.

BP-059 **held** here — the skip reason states what the test observed and does not invent a cause.
It is honest and it is invisible, which is the failure mode of a rule that governs wording but not
status. R28's `UNMET` is the fix, and `LL-140` proposed it (as "inconclusive rather than pass") on
2026-08-17 and was never promoted.

The deeper cause is a firmware-reachability property — an injector writes a state the firmware has
no path out of — and **no control in this project has ever looked for one.** Nothing static could
find it without reading `stockApp.cpp` and `stockHeatmap.cpp` together, which is what WP-G did.
R14's armed-state enumeration is the only proposed mechanism that catches this class without a
human reading two files, and it is the right one.

### 2.3 Cluster C11 — `set prInjectAircraft` (`H-1`)

**Which control should have caught it: BP-047, applied to test bodies. It applies to firmware
only.**

`T_PRI_01` injects twice and never clears; **its two siblings in the same file both clear at the
end.** That is a divergence between three copies of one pattern — BP-047's exact subject ("a fix
landing in duplicated logic either extracts the shared helper in the same commit or names the
sibling sites"), adopted 2026-07-12 after a PlaneRadar fix diverged across two call sites in 24
hours. BP-047's `Applies to` line reads *Developer (fix workflow), QM (retrospectives), PM
(scheduling duplication audits on mature apps)*. The suite is not mature-app firmware, so nobody
ever scheduled a duplication audit over it, and the one that finally happened was this review.

Second control that should have applied: BP-032, from LL-068 — `resume()` must reset per-visit
state. That ruling was made about `_lastFetch` and generalises verbatim to injection flags. It was
never generalised, and three separate firmware authors then made the same omission in three
subsystems. **A rule stated about one field is a rule about one field.**

Third: nothing could have caught this from verdicts, and the review says so — `H-1` "costs no
verdict today only by accident of registry order". Any control that reads only results is blind to
it in principle. That is the argument for R14 over R15, and the VE's grading (R14 MUST, R15 SHOULD)
is correct.

### 2.4 The structural diagnosis

Three separate near-misses is a pattern, and the pattern has one shape:

> **Every control this project owns reads an artifact. Not one reads a run.**

- `check_build.sh`'s 11 gates: six firmware builds, a checksum over generated assets, tool smoke
  tests, two staleness checks, the documentation gate. All static, all over files in the tree.
- `check_docs.py`'s C1–C6, SPIKE, ROWLEN: all static, all over documents.
- `check_test_meta.py`: asserts records are *well-formed*. `B-15`'s line is exact — "the gate
  asserts records are well-formed, never that they are true."
- `check_app_conformance.py`, `check_settings_wiring.py`, `check_player_binding.py`: static
  source scans.
- The class hierarchy is the sole exception — it is the only control that consumes a result — and
  it consumes it as a **string prefix** (`_gate.py`'s `startswith("FAIL")`), which the dominant
  failure mode does not match.
- The flake registry is the only other dynamic control, and it is the only one that was going to
  catch anything (§2.1).

So the answer to "how did 11 gates and 6 checks miss 35 tests that cannot fail" is: **none of them
was ever pointed at a test result, and the one that was reads a prefix.** The quality system is a
document-and-artifact integrity system that has been read as a test-quality system, and this is the
same conflation `LL-140` named ("covered" and "green") one altitude up.

Second structural cause, and it is my charter: **the QM audit's four dimensions are all presence
checks.** `docs/agents/quality_manager.md` §3 lists features not in the inventory, features
`implemented` with no `test_ids`, cross-feature interactions with no `test_coverage`, and docs
lagging code. A feature whose `test_ids` names a test that cannot fail satisfies dimension 2
perfectly. The only audit that ever found this class (2026-05-30) was triggered by a human asking
*"how many tests are fire-and-forget?"* — not by the charter, which has no such dimension and never
acquired one even after that audit produced BP-016.

Third: **no rule in this register carries a re-measurement cadence.** BP-016 has a threshold and no
schedule. BP-018 is the single counter-example — its 2026-09-01 amendment voided its own rationale,
kept the rule as an explicitly unverified precaution, and wrote a **retirement criterion** with the
coupling to check first. That amendment is the best piece of register hygiene in the file and it is
one of 72.

---

## 3. Q3 — Will these controls hold?

The Developer's §5 asks this question and answers it from experience. I am answering it from the
record, because this project has run the experiment fifteen times and the results are in the source
of the gates themselves.

### 3.1 The evidence: what stuck, what rotted, and the promotion protocol nobody wrote down

**Stuck.**

* **`golden.sha256`** (gate 8 of `check_build.sh`). A checksum over generated assets. It has never
  been reported as noise, it needs no ledger, and re-baking is the fix. Profile: zero authoring
  cost, zero judgement, binary outcome, attributable to one file, and it fails on the developer's
  own next command.
* **C5, C2, C4, C1-delta, SPIKE.** All five were promoted advisory → blocking, and
  `check_docs.py`'s own header records why each was allowed to: *"phase 1 blocked on C5 and
  C1-delta only: both read 0 on ship day, and a gate that fails on day one gets switched off"*;
  C2 *"has read 0 since phase 1 and still does at promotion time — verified immediately before
  this edit, not assumed from the board note"*; C4 promoted *"once TASK-508's ~189-header
  migration landed and re-measurement read 0"*; SPIKE promoted only after TASK-538 cleared the six
  spikes. **That is a promotion protocol — measure zero, then block — and it is written in a
  source comment rather than in `best_practices.md`.**
* **C6, which landed with 49 failures and works anyway.** This is the important exception and the
  file argues it explicitly: *"A blocking check plus a ledger that cannot grow silently is
  strictly stronger than an advisory check with 49 permanent failures: advisory failures are
  scrolled past, which is the exact mechanism by which 'covered' and 'green' got conflated
  (LL-140) … a ledger row whose failure no longer occurs is itself a BLOCKING failure, so the list
  can only shrink."* The distinguishing property is not zero-on-landing. It is **blocking plus a
  dated, shrink-only ledger**.
* **The flake registry's `review_by`.** Enforced in code — an expired declaration becomes a FAIL
  naming the id and the date. Profile: mechanical, attributable to one id, and renewing it
  honestly costs one line. It is the only control in the system that was going to catch `F-4`
  (§2.1).
* **C1-delta / BP-064.** The one ratchet in this repo that has actually moved, and it moved because
  it is **delta-scoped**: it "fails only on newly introduced coordinates so the existing backlog
  decays opportunistically instead of needing its own milestone." 274 of 576 citations were broken
  when it landed; it never needed a sweep.
* **BP-013's ok-counter.** The single most effective test-quality intervention in the register's
  history, and the reason is that it **is not a rule** — it added an observable. WP-Z: "TASK-112
  added `quoteOkCount`/`fetchOkCount` as a test-quality fix, and the four SOUND Stock fetch ids are
  exactly the four built on them." Contrast BP-016, adopted from the same audit on the same day as
  a *question to ask yourself*, whose named ids are still broken (§1.3). **Same audit, same day,
  two remediations: the one that changed what could be written held, the one that changed what
  should be written did not.**

**Rotted.**

* **C3.** Advisory, and the reason recorded in the source is honest: *"promoting it is a scope call
  for a human, not a mechanical one."* It landed non-zero, with no ledger and no owner for the
  failures, and it is now a permanent red line inside a passing gate suite. Note the irony the
  Developer already spotted: the paragraph explaining why advisory failures are worthless sits
  **in the same file, forty lines above C3's definition**.
  **Measured while writing this review**: `check_docs.py`'s header records 58 occurrences across 10
  unknown env names; `./run/check-docs` run for this handover reports **60 occurrences of 10
  unknown env names (of 389 `cyd2usb*` references)**. The three M-HARNESS2 documents added two, in
  a review cycle whose entire subject is that controls decay. That is C3's failure mode
  demonstrating itself inside the audit of C3: **an advisory count grows silently, and the number
  in the source comment is already stale.** It is also, incidentally, the mirror class (`R42`) —
  a count re-declared in a comment beside the code that computes it.
* **BP-016.** §1.3. A judgement rule, unmeasured after adoption, with an escalation threshold that
  had a number and no cadence.
* **BP-018.** Rationale void one week after adoption (the firmware it described was deleted in
  `ddf6433`); the harness machinery matching it was unreachable for three months while reading as
  live safety code; corrected only in 2026-09-01's amendment. Cause: no retirement criterion at
  adoption.
* **BP-020, which rotted into an obstruction.** Adopted 2026-06-06 as a safety property — the
  `trap EXIT` restore guarantee that made the pre-validation sequence atomic. `run/lib.sh` makes
  the restored variable deliberately non-overridable. That control is now the single thing
  blocking WP-Z's 80-minute session, which would settle 32 of 58 open items including all three
  injector confirmations. **A control with no escape hatch becomes an obstruction when the context
  changes**, and BP-020 has neither a retirement criterion nor an exception path.
* **BP-009's import smoke-test.** Rotted into a hazard (§1.2, R48). A best practice that instructs
  `python3 -c "import module"` is unsafe against six modules that open the serial port at import.
* **`EDGE_ADJUDICATION`.** A hand-maintained exception list over an under-detecting scanner, kept
  complete by a gate that cannot check it is correct — and `C-19` shows one row is wrong. Worse
  than no control, because it was delivered *as the precondition for the class-order switch*.
* **A smaller one, in the gate infrastructure itself:** `check_build.sh` sets `TOTAL=11` and its
  header says "11 counted gates"; `run/check`'s header says "12-gate" and enumerates a 7-env
  matrix. `CLAUDE.md` says 11. The gate count is mirrored in three places and two of them
  disagree. That is `R42`'s subject inside the tooling that would enforce `R42`.

### 3.2 The rule the evidence supports

> **A control holds when its failure is (a) mechanical — no judgement in the verdict; (b)
> attributable to one named artifact the failing author owns; (c) cheap to clear *honestly*, so
> the honest fix is cheaper than the dishonest one; and (d) it lands either at zero, or blocking
> with a dated shrink-only ledger. It rots when any of the four is missing, and it rots fastest
> when (c) is missing, because then the cheap path is the lie.**

Two corollaries the record supports and neither review states:

1. **"Red on day one is the correct first result" is false as stated.** The requirements document
   says this twice (R3's verification, and §14's gate-first mode), and the Architect endorses it.
   The record says every gate that landed red *and stayed advisory* rotted (C3, ROWLEN,
   pre-TASK-538 SPIKE), and the one that landed red *and worked* (C6) did so because it landed
   **blocking with a shrink-only ledger**. The distinction is not red-vs-green. It is
   ledgered-vs-advisory. §14's `gate-first` row says "land the gate with today's violations on a
   dated ledger; a stale row is itself a failure" — which is exactly right — but R3's own
   verification paragraph does not repeat it, and R3 is the requirement most likely to land red
   across several apps. **Make the ledger clause explicit in every `gate-first` requirement, or
   the first one that lands advisory will become the next C3.**
2. **Prefer an observable to a rule wherever both are available.** BP-013 versus BP-016 is a
   controlled experiment on this exact question, and the observable won by a wide margin. This is
   also, independently, WP-Z's theme T3 and the requirements document's own central claim — the
   document just never notices that its register has already tested it.

### 3.3 Verdicts on the fifteen proposed enforcement mechanisms

| Mechanism | Will it hold? | Which of (a)–(d) it has |
|---|---|---|
| R28/R31 verdict enum + typed gating | **Holds.** The strongest in the document. | all four; zero authoring cost — the author declares nothing, the type does |
| R48 import-in-subprocess gate | **Holds.** | all four; lands at zero after six `__main__` guards |
| R29/R30 artifact schema + negative tests | **Holds**, if the negative tests ship with it (BP-068). | a, b, d |
| R18 no defaulted read | **Holds.** 98 measured sites, one regex, a countable ratchet with a floor of zero. | all four |
| R37 flake × gating-class cross-check | **Holds.** Cross-product of two parsed files. | all four; lands at or near zero |
| R42 mirror-equality gate | **Holds** — it is `golden.sha256`'s shape (equality between a copy and its source). | a, b, d — but see the Developer's correct objection that the *pair register* is itself a hand-maintained mirror; generate the pairs where the firmware symbol is already in `app/gen/` |
| R46 duplicate-id detection | **Holds.** Extends C6, which works, using C6's ledger. | all four |
| R33/R47 one results/session layer | **Holds as a ratchet**, because the counts are small (3 producers, 19 files) and each is a named file. | a, b, d |
| R35 declared class | **Holds** — but only because R36 checks the substance. See §4. | a, b, c via R36 |
| R14 armed-state boundary check | **Holds.** Mechanical, and the failure lands on the test that armed it — (b) is the whole point of the requirement. | all four |
| R16 declared effect | **Rots as written** — the "stronger declaration never fails" clause makes `resetting` a free pass. Holds in the Developer's three-run form, and better still in the harness-observed form (§4.3). | b, d only, as written |
| R9 prose `falsifier` | **Rots, and worse than rotting** — it manufactures AC3 = 100 % out of typing. Holds only as the Developer's two-field split. | b, d only |
| R1 `oracle_reason` | **Rots.** Free prose, "by review", reviewed by the test's author. The document says so itself and still grades it MUST. | b only |
| R23 sleep ratchet / AC11 | **Rots.** A ratchet with an underived floor. Both the Architect and the Developer flagged the number; they are right. Classify the 253 first, publish three counts, set the floor to the physical count. | a, b — no (c), no floor |
| R44 threshold citations | **Rots as scoped. Do not cut it — delta-scope it.** See §3.5. | fixable to all four |
| R53 budget table | **Not a control at all** — "reported, not failed" is a measurement. Fold into R30; keep the table as a target. | measurement, not gate |
| R11 quarterly campaign | **Rots**, and the document predicts its own failure: graded SHOULD explicitly *because* a MUST "would make it the first thing dropped under time pressure". Naming the failure mode is not mitigating it. Fix: the Developer's expiry field, enforced the way `results.py` enforces an expired flake. | b, d — no (a) trigger |
| R20/AC13 three shuffled full runs | **Rots as a campaign, holds as a capability.** ~3 board-hours on a one-board rig happens once. Per-family shuffle triggered by that family's file changing is the C1-delta pattern and would run thirty times. | capability: all four; campaign: none |
| R52 fixture declarations | **Cannot be judged** — the format is undecided, which the document says honestly. An undesigned declaration is a comment. | — |

### 3.4 The two schedule questions I was asked to rule on

**The Developer's ~154 engineer-days: wrong in both directions, and the useful number is neither.**

* **Over-stated on the retrofit half.** The retrofit estimates (R9 8.5 d, R1 8 d, R17 8 d, R23
  9 d, R28 5.5 d) are all denominator-driven off 213 ids. The Developer's own §8 removes 27 bodies
  and puts Clock's 14 into a rewrite rather than a migration — 41 ids, **19 % off the
  denominator**, ~10 d off the retrofit total before anything else happens. He sequences the
  deletions on day 6 and does not credit them back into §1.2's table.
* **Under-stated on the mechanism half.** R10's 6 d assumes a recorder on `Dut.cmd`; four
  `SerialDut` clones and 19 direct `serial.Serial` files mean **R47 is a hard precondition of
  R10**, which he notes in §4.3 and does not add to the estimate. The Architect's landing rule
  (one app per commit, freshly derived `.map` each time) makes the OBS contract 13 firmware
  commits on a board that is pinned — that is calendar, not effort, and neither document prices
  calendar.
* **The number that matters is neither 154 nor his net 116.** It is **the ~30 days that are gated
  on nothing** — no ADR, no board, no graded finding. That is his ten-day plan plus R18, R37, R46
  and the deletions. Everything else is blocked on a decision or a measurement that has not been
  taken. Give @PM the 30, not the 154.

**The VE's acceptance criteria: the mechanical half is excellent, and AC1 is not a measurement.**

AC1 ("share of registered ids that assert what they claim: 54 % → ≥ 85 %, measured by a rubric
re-audit, same method") is the headline criterion for a seven-month programme, and its instrument
is a single-grader subjective rubric with **no inter-rater agreement measurement anywhere in the
review** (§5.1). Neither the Architect nor the Developer challenged it; the Architect's only note is
that it will be misread as coverage, which is true and is a smaller problem. A programme cannot be
accepted against a re-run of an unvalidated instrument by the same method. Two fixes, in order of
preference: (i) before AC1 is adopted, re-grade one family with a second independent agent and
publish the disagreement rate — if two graders disagree on more than ~10 % of a 40-id sample, AC1
must be struck; (ii) failing that, demote AC1 to a reported figure and let the programme be accepted
on the mechanical criteria only — AC5, AC7, AC10, AC13, AC16 — every one of which is a count nobody
can argue with.

AC3 and AC9 have the opposite problem: they are counts *of declarations* (100 % falsifiers, 213/213
effects) and can therefore be satisfied by typing. See §4.4. AC13 is the strongest criterion in the
table and the VE says so; I agree, and note that it is also the only one the document schedules as a
calendar item rather than a gate, which is where things go to be dropped.

### 3.5 Where I disagree with the Developer on R44

He would cut it outright: >1 000 sites, no completion condition, "this is `check_docs` C3's exact
shape". The diagnosis is right and the remedy is wrong, because this repo has already solved that
exact shape once. **C1-delta** faced 274 broken citations out of 576 — a worse ratio than R44's —
and neither swept them nor abandoned the rule. It gated *newly introduced* coordinates only, and
the backlog now decays opportunistically. R44 delta-scoped ("a numeric bound in an assertion you
touch cites its origin") costs approximately zero days, needs no ledger, has a floor of zero by
construction on every future line, and cannot become C3 because it can never accumulate a standing
failure count. Cut the retrofit; keep the rule; scope it to the diff. His alternative (scope it to
the 43 gating ids, one day) is also fine and the two compose.

---

## 4. Q4 — The declarations problem

The Developer's measurement is the one to reason from: the honest cost of the new declarations is
40–50 minutes on a 1–3 hour job; the hurried cost is **about four minutes of typing that passes
every gate**. That gap is not a risk to be managed. It is a specification of what the gate
measures.

### 4.1 The ruling

> **A declaration is a control when something mechanically checks it against a fact the declarer
> does not control, and the resulting failure names the declarer's own artifact. It is theatre
> when its only reader is a gate looking for its presence, or a human looking for its
> plausibility.**

Two corollaries, both evidenced in this project:

**(1) A presence gate produces plausible strings, and this has been measured.**
`check_test_meta.py` gates record well-formedness today. The result, re-measured for the
requirements document via `build_all_meta()`: `cls` declared on **6 of 213**, `scope` on 57,
`effect` on **3**, and **209 records carrying a seeded `mutating` nobody typed**. `B-15`'s sentence
is the finding of the whole taxonomy package — *"a `cls` value has never been wrong in this repo,
because no `cls` value has ever been written down"* — and it is the empirical answer to "will
authors fill in a field a gate requires?" They will fill it in with whatever costs nothing.

**(2) An unverified declaration has negative value, not zero.** This is BP-060/LL-125, adopted
after three successive wrong root-cause theories were written into handover prompts and acted on
unchallenged by every receiving agent: *"a prompt reads as briefing rather than hypothesis."* A
`falsifier:` string reads as *"somebody checked that this test can fail."* The next reader — a
milestone report, an acceptance table, a cold agent — will treat the id as falsification-checked
because a field says so. BP-060's remedy is exactly the right one here: **label how the claim was
established, or make it executable.** A declaration that cannot be checked is worse than an absent
one, because absence is honest.

### 4.2 The three fields, ruled individually

**R35 `cls` — ACCEPT as a declaration.** It is the only one of the three that is a *choice* rather
than a *claim about the world*. Its value set is closed, it is consumed immediately and visibly (it
changes dispatch order and blocking power), and — decisively — **R36 mechanically checks the
substance of the CORE claim**: a gating-class precondition must be satisfiable offline on a healthy
board. The prose `cls_reason` is not the control and should not be mistaken for one; R36 is. WP-Z
is right that writing the 43 reason strings *is* the audit, and `B-1`/`B-2` are the proof — someone
attempting to justify a live-HTTPS-fetch CORE test would have stopped. Add the Developer's cap on
CORE membership (43 today; raising the count needs a design-doc row, not a decorator), which
supplies property (c): the honest path is cheaper than growing the class.

**R16 `effect` — REJECT as a declaration; it should not be one at all.** This is the field whose
ground truth the harness observes for free on every run — injections armed, settings hash changed,
reboot seen, entry app changed — which R16 already specifies as the boundary check. Asking 213
authors to type a value the machine is about to compute anyway is 213 opportunities to be wrong for
no information gain, and the requirement then permits over-declaration to pass forever, which makes
`resetting` a universal free pass and turns the field R14/R17/R19 key off into a constant.

My position is one step past the Developer's three-run rule: **do not ask for `effect` on the legacy
corpus at all. Have the harness observe it, write it into the record, freeze it, and fail on drift.**
Zero authoring cost, no lie surface, and a change in a test's observed effect becomes a reviewable
diff instead of a declaration nobody re-reads. Keep an authored `effect` only for a *new* test,
where it functions as an expectation the first run can contradict — which is a control, because the
run does the checking. The Developer's three-run over-declaration rule is the right fallback if the
freeze-and-diff form is judged too clever; both are strictly better than R16 as written.

**R9 `falsifier` — REJECT the prose field outright.** This is the theatre case, and it is the most
expensive one because AC3 converts it directly into a headline percentage. It is a claim about
counterfactual behaviour: the most costly field to establish honestly (the Developer measures 10–20
minutes, because you must actually run the perturbation), the cheapest to fake (30 seconds), and
unverifiable at declaration time by construction. A gate can confirm the field is non-empty and
nothing else.

Accept **only** in the Developer's two-field split, and I would go further and make the split a
condition of building R9 at all:

* `falsifier_replay: {key, mutation, expect: FAIL}` — executable, exercised every run by R10's job.
  A control: the machine does the checking.
* `falsifier_physical: {action, owner, task, executed_on, review_by}` — with expiry enforced
  exactly as `lib/results.py` already enforces an expired flake declaration (it becomes a FAIL
  naming the id and the date). A control: the expiry is mechanical, dated and attributable, and
  this repo has a working instance of the mechanism ten metres away.

A bare `falsifier:` string gates nothing, and R9's own verification sentence — "a T0 gate fails on
any registered id with no `falsifier`" — is a presence gate, which §4.1(1) has already measured at
209 seeded values out of 213.

### 4.3 The same test applied to R1

The Developer's amendment is correct and I would adopt it as the model for the whole group:
**generate `reads:` from the source walk that must happen anyway, and have the author declare a
`claim_class` from a closed enum.** That converts the vocabulary rule from a review judgement into
a cross-check between two things the author does not control — a declared enum value and a parsed
key set — for the common cases. `oracle_reason` survives as documentation for the residue and
**must not be counted in any acceptance criterion**. R1 as written grades itself "the weakest link
in the group" and then makes it a MUST; that combination is exactly what §3.2(c) predicts will rot.

### 4.4 One consequence for the acceptance table

**No acceptance criterion may be a count of declarations.** AC3 (100 % of ids carry a falsifier) and
AC9 (213/213 declare an effect) are satisfiable by typing, and AC3's real sibling AC4 (falsifiers
*confirmed*) is graded ≥ 90 % host-replayable with the remainder merely "scheduled". Publishing AC3
next to AC4 invites the first number to be quoted. Strike AC3 as a standalone criterion, or print it
only as a denominator inside AC4. AC8 (43/43 declared classes) survives because R36 checks the
substance behind it. AC9 survives only under the harness-observed form in §4.2.

---

## 5. Q5 — Process audit of the M-TESTQUAL review itself

**Method as executed** (from the index ledger and the rubric): eight work packages, one AI subagent
each, dispatched sequentially over two days; static analysis only; a rubric fixed before the first
body was read; every finding required to cite `path:line`; an orchestrator spot-checking selected
claims; `./run/check-docs` run before each handover to prove the audit had not moved the gate it was
auditing (C6 identical seven times — a genuinely good discipline, and rubric amendment A2 is why).

### 5.1 What this method systematically misses

**1. False negatives are invisible, and the headline number has an unaudited denominator.** The
method grades tests that exist. It cannot find a behaviour with no test at all, and WP-Z says so:
absence was surveyed for **three apps only** (Clock, Teletext, PlaneRadar) — and those three turned
out to have the largest holes, which is evidence the survey was worth doing and was not done for the
other ten. So "54 % of registered ids assert what they claim" is a quality figure over a denominator
nobody measured. Expect the untested-surface problem to be at least as large as the weak-test
problem and entirely unquantified. A programme scheduled off the 54 % will spend its effort
improving the tests that exist rather than covering what does not, and neither the requirements
document nor either review notices this.

**2. Per-package framing under-weights anything that is uniform.** Each agent read one family
against one rubric. A defect present in *one* family per package gets found; a defect present in
*every* family looks like background and is invisible to all of them. The evidence is in which
findings came from where: the 253 sleeps, the timeout policy with zero users, the four `SerialDut`
clones and the results-summary interface are all WP-A's, because WP-A was the only package pointed
at the shared layer. `C-18` (positional reply correlation, a defect in `Dut.cmd` that affects every
id in the suite) surfaced in WP-C by luck of what that package happened to read. **A ninth package
that read only the shared layer a second time would probably find as much again**, and the review
has no mechanism that would tell us either way.

**3. The rubric is a ceiling as well as a floor.** Four values fixed in advance, plus a closed smell
list. WP-Z admits the compression: WEAK spans "one term of a conjunction is loose" and "the only
oracle is a proxy two rungs from the subject", across 64 ids. A defect with no smell code becomes
prose in one package and dies there — WP-F §6.1's ranking of oracles by distance from the audible
behaviour is the best analytical passage in the whole review and it is carried into WP-Z as a
sentence.

**4. Static means the load-bearing findings are unconfirmed.** All three armed-injector clusters —
the only findings claimed to produce wrong verdicts *today*, and the justification for the largest
requirement group — are inferences filed NEEDS-DUT. Each has a named confirmation that takes
minutes. The confirming session cannot run (TASK-618). See §7.

**5. Verification was of counts, not of judgements.** The orchestrator re-verified three WP-A claims
and WP-B's declared-vs-seeded census (exact match) — good practice, and honestly logged. But every
spot-check was **a count**. Not one SOUND / WEAK / HOLLOW / BROKEN verdict was independently
re-graded by a second agent, and the rubric anticipated the need: *"a family audit reporting 100 %
SOUND will be re-run by another auditor."* No family reported 100 % SOUND, so no family was re-run,
and the trigger never fired. **Every one of the 216 verdicts has a sample size of one grader**, and
AC1 proposes to re-run that instrument as the acceptance criterion for a seven-month programme
(§3.4).

There is indirect evidence the packages were careful and the *rollup* was not: three of the eight
corpus counts in the index were wrong and were corrected by the packages themselves (31 not 29,
30 not 31, 30 not 40), and `A-8` was refuted in-flight by `H-4` as a live defect while being
confirmed as a latent one. A method that publicly corrects its own inputs and refutes its own
earlier finding is behaving correctly; that is the strongest single indicator of the review's
integrity and I weight it heavily in §5.3.

### 5.2 Incident 1 — the bulk import that reset the board

**Judgement: a real process failure, correctly handled, and the underlying defect is mine as much
as the agent's.**

The WP-A agent imported `app/tools/*.py` to find broken imports; six modules open the serial port
and run their DUT suite at import time; the board was reset and taps were injected at ~18:50 on
2026-09-02, inside a TASK-557 observation window.

The agent was **following an adopted best practice**. BP-009 (2026-05-24, still current) instructs:
*"For Python tool scripts, confirm `python3 -c \"import module\"` from the new location."* That is
the action, named, in a rule this project adopted and never amended. Blaming the agent for it would
be exactly the misattribution BP-009 exists to prevent in the other direction.

What was done right, and it is a lot: disclosed in WP-A §0 rather than buried; filed as a finding
(`A-12`); the rubric amended the same day (A1) so no later package could repeat it; the
contamination window flagged so any TASK-557 measurement from that evening is treated as suspect;
and an open item (WP-A N-5) filed to have the TASK-557 owner read the log and settle whether it
mattered — which WP-Z correctly calls the cheapest open item in the whole list.

Cost: one observation window on the task that is currently the reason the board is pinned, and one
item that may never be settleable. That is a real cost on a project where the rig is the scarcest
resource, and it is bounded. The outcome — R48, which both other reviewers call the strongest
requirement in the document, and which the Developer says he would land unilaterally today — is
worth more than the window. **The correct disposition is to amend BP-009 in the same commit that
lands R48**, so that the rule and the tree stop contradicting each other. That is a QM action and I
have proposed it in §6.

### 5.3 Incident 2 — the three session-limit deaths

**Judgement: handled well, cheaply mitigated in flight, with one residual risk that lands on the
wrong package.**

The record: WP-C died at its first tool call when the orchestrating session hit a 5-hour usage limit
(~03:00), produced nothing, and was re-dispatched unchanged at 04:07. The rubric's amendment A3
records that **two** packages were killed mid-run by the same cause: *"WP-C's first attempt held
everything in memory and lost all of it, WP-F wrote as it went and lost only the tail, which was
then completed by resuming the same agent. The cost difference is the whole package."*

Three observations:

1. **The mitigation was derived from the incident and applied mid-review**, as a standing work
   order (A3: write incrementally, save after each batch, never hold the document in memory), and
   it held for the five packages that followed. That is the register's own BP-052 (check for
   salvageable work on subagent death, adopted 2026-08-05 after a credit-limit death) extended
   from *salvage* to *prevention*. The team did in two days what the register took a task to do.
2. **Nothing was lost that mattered.** WP-C's first attempt died before its first tool call —
   there was no partial work to salvage, and the re-dispatch was unchanged. WP-F lost a tail and
   resumed the same agent, preserving its context.
3. **The residual risk lands on the one package that can least afford it.** WP-C is the
   gating-class package: 49 ids — RIG, HEALTH and CORE — *"audited first, because everything above
   them inherits their trust."* It is the only package with no first-attempt output to compare its
   second attempt against, and it produced three of the structural findings the whole programme
   rests on (`C-5` the skip-gate, `C-3` the unreachable RIG class, `C-4` the false health banner).
   Those three are mechanical and I do not doubt them. But if any family gets a second grader, it
   should be C — **not because it died, but because its verdicts license the other 167 ids' claim
   to be gated at all.**

### 5.4 Are the findings trustworthy enough to spend 154 days on?

Plainly: **the findings are trustworthy enough to act on; they do not authorise 154 days; and 154
days is not what they support.** The review's evidence separates cleanly into three tiers and they
deserve different treatment.

**Tier 1 — mechanical findings. Trust at high confidence; act now.** "This body has no reachable
`fail()`." "This `get` key does not exist in the firmware." "This log marker is never emitted."
"`gen_get_keys.py` sees 43 of 71+ keys." "31 of 43 CORE ids have a `skip()` exit." "Six modules open
a port at import." "`_gate.py` blocks on a string prefix." These are greps and source reads,
re-derivable in minutes, several independently re-measured by the orchestrator and again by the VE
writing the requirements document, and at least one (`A-8`) refuted in flight. They carry the whole
of the Developer's four irreducible days and most of his ten-day plan. **Nothing about the audit's
method threatens them.**

**Tier 2 — graded findings (117/216 SOUND; the family spread). Trust as a rank order, not as a
number.** Single grader per family, rubric-bounded, no inter-rater measurement. The *ordering* —
LocalPlayer best, Clock worst, by a wide margin, with a mechanically-visible cause (which families
had observables designed first) — is robust because it is corroborated by an independent fact: the
families that score well are exactly the ones with ADR-059 D12's and TASK-112's designed
observables. The *number* 54 % is not robust enough to be an acceptance baseline. Use theme T3's
conclusion; do not use AC1's arithmetic (§3.4).

**Tier 3 — predicted findings (the three clusters' blast radius). Do not spend against these until
the session runs.** They are explicitly filed as inferences with named confirmations, and WP-Z
itself says a reading can be wrong in ways a run would expose in minutes — `G-1`'s blast radius
"would change from thirteen ids to none" if a clearing path was missed in the source read.

So my ruling on order is a quality ruling, not a scheduling preference: **80 minutes of board time
before 154 engineer-days.** The session settles 32 of 58 open items including all three injector
confirmations and both isolated-vs-in-suite splits. Committing seven months of engineering ahead of
it repeats `LL-115`/BP-048 part 3 — elaborate secondary work performed before the primary result is
in, where the rigour of the secondary work is itself what makes the gap invisible. TASK-618 is
therefore the highest-value item in any of the three documents, and it is currently filed as a
procedural footnote in a decisions table.

---

## 6. Q6 — Proposed register entries

**Nothing below has been written to `lessons_learned.md` or `best_practices.md`.** The LL entries
are proposals for the register and are mine to add once this review is accepted; the BP candidates
go to the human, per the standing rule that QM never self-promotes. Ids are provisional — LL-146 is
the next free number (LL-145 is the highest in use), and BP numbers are deliberately not assigned.

### 6.1 Proposed lessons — `lessons_learned.md`

#### LL-146 — 2026-09-03 — A lesson that names a live defect mechanism is not a control, and this one sat three weeks while the defect was re-derived from scratch

**Context**: `LL-127` (2026-08-14, `Status: open`) recorded, from TASK-432's fault-injection gate,
that `set wrDeadUrls` arms `_debugForceConnFail`, that `_play()` short-circuits on it before the
audio path, and that `set wrUrl` is the injector that clears it. Twelve days later two `flaky.yaml`
entries were filed against `T_WR_COEX_01` and `T_WR_VOL_03` with `symptom: "wrState=5"` — the state
that flag assigns — and `dependency: "[NETWORK] — radio-browser.info station availability/churn"`.
Twenty days later WP-F re-derived every one of those facts from source as finding `F-4`, the largest
coverage defect in the review, and attributed roughly a year of misfiled flake data to it.
**Observation**: The register held the mechanism, the flake registry held the symptom, and the two
were never in the same room. Nothing in this project reads `lessons_learned.md` at gate time, at
test-authoring time, or at flake-declaration time; its only reader is a human who already suspects
the answer. The entry was also filed under the wrong subject — written about *a gate*, when its
generalisable half was a fact about *an injector every WebRadio test uses* — and was never routed to
@VE as a question about the suite.
**Root cause**: An LL is an archive, not a control. Filing a firmware fact into a quality register
discharges the writer's sense of having recorded it, and reaches nobody who would act on it. The
`Status: open` field, meaning "proposed for BP promotion", also functions as an unbounded delay with
no owner.
**Suggested improvement**: When an LL records a **concrete, live mechanism** (a named flag, a
command, a code path) rather than a process pattern, it is not finished until the fact reaches the
artifact that would act on it — a `flaky.yaml` entry, a test docstring, a firmware comment, a
filed task naming the owning role. Additionally: an LL with `Status: open` for more than one
milestone is either promoted, dismissed with a reason, or re-filed as a task; a permanently-open
lesson is a lesson nobody decided about.
**Status**: open

#### LL-147 — 2026-09-03 — Three months after a BP was adopted to kill tests that cannot fail, five of the ids it named are still in the suite and one had its tautology replaced by a different tautology

**Context**: The 2026-05-30 audit (`audit_log.md`) classified all 78 serialdbg tests by assertion
strength and produced BP-016 ("tests must assert causal behavior, not initial state or
trivially-true defaults") plus TASK-112 as the remediation. The 2026-09-03 M-TESTQUAL review graded
216 ids and found 35 that cannot fail. Five of the nine ids BP-016 named are among them, and WP-G
records that *"the TASK-112 audit-001 pass that created `T178`'s body replaced a hardcoded-default
tautology with a harness-write one"*.
**Observation**: The remediation of a finding reproduced the finding's own defect class, because the
rule it was executing said *assert something causal* and nothing checked whether the value asserted
was one the test had just written. BP-016 also carries its own escalation clause — *"escalate to RED
if a suite has >10 % trivial tests"* — which was never re-measured after adoption and reads 16.2 %
today. Contrast the other remediation from the same audit on the same day: BP-013's ok-counters
(`quoteOkCount`, `fetchOkCount`) held, and the four SOUND Stock fetch ids are exactly the four built
on them.
**Root cause**: Two failures, one structural. (a) BP-016 changed what an author *should* write and
supplied no way to check it; BP-013 changed what an author *could* write by shipping an observable.
The observable held and the exhortation did not. (b) A threshold with a number, an owner and no
cadence never fires; nothing in this project schedules a re-measurement of a rule after it is
adopted.
**Suggested improvement**: Prefer an observable to an exhortation wherever both are available —
a debug counter that makes the honest assertion writable beats a rule telling authors to write it.
Where a BP states a numeric threshold, it must also state who re-measures it and when, or the
threshold is decoration. And a remediation task filed off a test-quality finding is not closed until
the replacement assertion has been checked against the same rubric that condemned the original.
**Status**: open

#### LL-148 — 2026-09-03 — Eleven build gates, six documentation checks and a class hierarchy, and not one of them reads a test result

**Context**: On 2026-09-02 this project had 11 counted gates in `check_build.sh`, 6 checks in
`check_docs.py` (4 blocking), an id-binding gate with a shrink-only ledger, three source-conformance
gates, a five-level test class hierarchy and 72 adopted best practices. A static audit then found 35
registered tests that cannot fail, three debug injectors wedging whole families for up to a year,
and five milestone exit criteria booked PASS against oracles that cannot observe them.
**Observation**: Every one of those controls reads an **artifact** — a build product, a checksum, a
document, a source file, a record's shape. The class hierarchy is the sole control that consumes a
*result*, and it consumes it as a string prefix (`RESULTS.get(tid,"").startswith("FAIL")`), which the
dominant failure mode — a skipped precondition — does not match. The one control that was actually
going to catch the WebRadio injector was the flake registry's `review_by` expiry, which is the only
other dynamic, dated, attributable mechanism in the system.
**Root cause**: The quality system is a document-and-artifact integrity system that has been read as
a test-quality system — the same "covered" / "green" conflation `LL-140` named, one altitude up. A
suite is the one artifact that reports on itself, and nothing was ever pointed at whether its
reports mean anything.
**Suggested improvement**: At least one control must consume a run rather than a file: a typed
verdict, a per-run artifact carrying the run's premise, and a summary that makes disappearing
coverage visible (a per-scope SKIP count that goes up). Separately, the QM audit's four dimensions
are all *presence* checks — a feature whose `test_ids` names a test that cannot fail passes
dimension 2 — and need a fifth: **tests that cannot produce a verdict**, on a stated cadence.
**Status**: open

#### LL-149 — 2026-09-03 — An adopted best practice was the action that reset the board mid-audit

**Context**: BP-009 (2026-05-24) requires, for any structural refactor: *"For Python tool scripts,
confirm `python3 -c \"import module\"` from the new location."* On 2026-09-02 the WP-A audit agent
imported `app/tools/*.py` to find broken imports. Six modules open the serial port and run their
whole DUT suite at import time; the board reset, taps were injected, and a TASK-557 observation
window was contaminated.
**Observation**: The agent followed a current, adopted rule into a hazard the rule's author could
not have foreseen and nobody had re-checked in three months. Handling was correct — disclosed in
WP-A §0, filed as `A-12`, rubric amended the same day to ban the import, contamination flagged, and
an open item filed for the TASK-557 owner to read the log — and the finding became the requirement
both other reviewers rate the strongest in the programme.
**Root cause**: A best practice is a standing instruction executed by agents who cannot audit its
present safety. BP-009's verification step encodes an assumption about the tree (that importing a
tool module is side-effect free) which the tree stopped satisfying without anyone noticing. No BP in
this register is re-validated against the tree after adoption.
**Suggested improvement**: Amend BP-009 in the same change that lands the import-safety gate: the
import smoke-test runs in a subprocess with a stubbed `serial`, never in the agent's own
interpreter. More generally, a BP that instructs an agent to **execute** something (not merely to
check or record) carries the environmental precondition its safety depends on, so a reader can tell
when the instruction has expired.
**Status**: open

#### LL-150 — 2026-09-03 — A safety control with no escape hatch became the obstruction blocking the most valuable measurement available

**Context**: BP-020 (2026-06-06) made the DUT pre-validation sequence atomic with a `trap EXIT`
restore of production firmware — a genuine safety property, adopted after three failed launch
attempts. `run/lib.sh` makes the restored variable deliberately non-overridable. TASK-557 then
pinned the board to a `-DBOD_WATCH` debug build with a standing instruction not to restore
production. The consequence: `run/test` and `run/test-targeted` cannot be run at all, and the
80-minute session that would settle 32 of 58 open M-TESTQUAL items — including all three
armed-injector confirmations — is blocked on a procedural decision (TASK-618).
**Observation**: The control is behaving exactly as designed and is producing the opposite of its
purpose. Killing the script mid-flight is not a workaround — it races the trap and can boot-loop the
board — so the correct resolutions are all *changes to the control*, not ways around it. BP-018 is
the register's counter-example: its 2026-09-01 amendment voided its own rationale, kept the rule as
an explicitly unverified precaution, and wrote a retirement criterion naming the coupling to check
first. It is the only BP of 72 with one.
**Root cause**: A control adopted under one context hardens into an obstruction when the context
changes, and nothing in the adoption format asks under what conditions the rule would stop applying
or who may grant an exception.
**Suggested improvement**: Every BP that constrains a mechanism (rather than describing a habit)
states, at adoption, a retirement criterion or an exception path with a named grantor. Where a rule
is enforced in code by a deliberate non-overridable, that non-overridability is itself a decision
that needs a documented owner.
**Status**: open

#### LL-151 — 2026-09-03 — Incremental writing was the difference between losing a tail and losing a package, and the rubric was amended mid-review to say so

**Context**: Three subagent runs in the M-TESTQUAL review died on the orchestrating session's usage
limit. WP-C's first attempt died at its first tool call and lost nothing (no partial work existed).
A later death took a package that had held its whole document in memory; another took only the tail
of a package that had been writing incrementally, and resuming the same agent recovered it. Rubric
amendment A3 was written mid-review as a standing work order: write the document incrementally,
save after each batch, never hold it in memory to write at the end. It held for the five packages
that followed.
**Observation**: The register already carried BP-052 (on subagent death, check for salvageable work
before relaunching) — the *salvage* half. A3 is the *prevention* half, derived from an incident and
applied within the same review. The residual risk is not the loss: it is that the re-dispatched
package was WP-C, the gating-class audit whose 49 verdicts license the other 167 ids' claim to be
gated at all, and it is the one package with no first-attempt output to compare against.
**Root cause**: Long analytical outputs from subagents are all-or-nothing unless the agent is
instructed otherwise, and the instruction is not the agent's default.
**Suggested improvement**: Any subagent brief whose deliverable is a long document carries the
incremental-write instruction explicitly (header and scope first, then batches, saving after each).
Pairs with BP-052: prevention first, salvage second. Where a package's output is load-bearing for
other packages' conclusions, schedule a second independent grader for that package specifically —
not because it died, but because everything downstream inherits its trust.
**Status**: open

#### LL-152 — 2026-09-03 — A single-grader subjective figure became the acceptance criterion for a seven-month programme

**Context**: The M-TESTQUAL review graded 216 test ids SOUND / WEAK / HOLLOW / BROKEN, one agent per
family, against a rubric fixed in advance. The headline result (54 % SOUND) became AC1 of the
M-HARNESS2 requirements: *"≥ 85 % on a re-audit of a 40-id random sample, same method"*. The
orchestrator's spot-checks were all of counts (WP-A's three claims, WP-B's census — exact match); no
family's verdicts were re-graded by a second agent, and the rubric's own re-audit trigger ("a family
audit reporting 100 % SOUND will be re-run") never fired because no family reported 100 %.
**Observation**: Two independent reviewers read the requirements document and neither challenged
AC1; the Architect's only note was that the number will be misread as coverage, which is a smaller
problem. The rank order the grading produced is well corroborated — the families that score well are
exactly the ones whose observables were designed first — but the acceptance criterion rests on the
absolute number and on re-running the same unvalidated instrument.
**Root cause**: A number produced by a careful, well-evidenced process reads as a measurement even
when its instrument has a sample size of one grader and no agreement statistic. Nothing in this
project's review practice asks for inter-rater agreement before a subjective scale is used as a
gate.
**Suggested improvement**: Before a subjective grading scale is used as an acceptance criterion,
measure the instrument: have a second independent grader re-grade one bounded sample and publish the
disagreement rate. If the rate is material, the criterion is replaced by the mechanical ones. This
is BP-066's independent-review rule applied to a *measurement* rather than to a document.
**Status**: open

### 6.2 Proposed best-practice candidates — for the human, not self-promoted

Four candidates, ranked. If only two are taken, take the first two. Each is written in the adopted
format so it can be pasted after sign-off; none is in `best_practices.md`.

**Candidate 1 — A declaration is only a control when something mechanically checks it against a
fact the declarer does not control**
*Proposed from*: LL-148 + this review §4; evidence in `B-15` and the `build_all_meta()` census.
*Rule*: A required metadata field, record attribute or declaration is a control only if (a) a check
compares it against a fact the declarer does not control, and (b) the failure names the declarer's
own artifact. A gate that asserts only *presence* measures compliance with typing, not truth, and
must not be cited as coverage, quoted in an acceptance criterion, or counted in a percentage. Where
the machine can observe the fact directly, do not ask for a declaration at all — observe it, record
it, freeze it, and fail on drift.
*Rationale*: `check_test_meta.py` has gated record well-formedness for months; the measured outcome
is `cls` declared on 6 of 213, `effect` on 3, and 209 seeded values nobody typed — with `CORE`, the
class that can block 167 other ids, never declared once. WP-B's line is the finding: *"a `cls` value
has never been wrong in this repo, because no `cls` value has ever been written down."* The
M-HARNESS2 proposal adds three more declarations, and the Developer measures the honest cost at
40–50 minutes per test against four minutes of plausible typing that passes every gate. BP-060
already establishes that an unverified claim written into a document is amplified rather than
neutral, so a declaration that cannot be checked has negative value, not zero.
*Applies to*: All (VE and Architect especially — anyone specifying a required field or an
acceptance criterion)

**Candidate 2 — A debug injector ships with its clearing path, its enumeration, and a named
consumer, in the same commit**
*Proposed from*: LL-146; WP-Z theme T1 (`F-4`, `G-1`, `H-1`) and `H-5`.
*Rule*: Any firmware debug setter that latches state (a forced-failure flag, a synthetic-data
injection, a mode override) ships in one commit with: (i) a clearing path reachable by an app
switch — `resume()`, not only `init()`; (ii) membership in the enumerable set of currently-armed
injections, so a test boundary can assert it empty; and (iii) at least one consumer in
`app/tools/`. An injector with no clearing path is a latent suite-wide defect; an injector with no
consumer is dead state (BP-025) that the next author will not find.
*Rationale*: Three injectors in three subsystems by three authors made the identical omission — each
arms a flag that nothing a test run clears — and one of them has been misfiled as network flakiness
for about a year across two `flaky.yaml` entries, because an isolated re-run cold-boots and passes.
BP-025 covers the writer-without-a-reader half and does not cover the missing *clearer*; BP-032's
`resume()`-resets-per-visit-state ruling was made about a fetch timer and never generalised. The
mirror-image waste is `H-5`: a deterministic fault injector built by TASK-361 with no consumer
anywhere, while the test it exists for has been a permanent SKIP whose docstring says no such hook
exists.
*Applies to*: Developer (firmware), VE (spec the injector alongside the observable, per BP-024),
Architect (NEW-APP-CHECKLIST)

**Candidate 3 — A new gate lands at zero, or lands blocking with a dated shrink-only ledger; never
advisory with a standing failure count**
*Proposed from*: this review §3; `check_docs.py`'s own promotion history and its C6 comment.
*Rule*: A new check is promoted to blocking only after re-measuring zero failures on the current
tree (measured at promotion time, not assumed from a prior note) — or it lands blocking immediately
with every known violation enumerated on a dated, owned ledger whose rows can only shrink and whose
stale rows are themselves blocking failures. An advisory check with a standing failure count is not
a weaker gate; it is a mechanism for training everyone to scroll past a red line.
*Rationale*: Five checks in this repo were promoted advisory → blocking and every one of them
re-measured zero first; the exception, C6, landed with 49 failures and works because of its ledger,
as its own source comment argues: *"advisory failures are scrolled past, which is the exact
mechanism by which 'covered' and 'green' got conflated."* C3 is the counter-example — advisory and
permanent, and its count grew from the 58 recorded in its own source comment to 60 during the
writing of this review, because an advisory failure has no owner and nothing stops it accumulating.
The M-HARNESS2 proposal adds roughly fifteen gates and calls "day one is red" the correct first
result; on this evidence that is only true with the ledger.
*Applies to*: Developer, VE (gate authors), QM (audit for advisory checks with standing counts)

**Candidate 4 — Every rule that constrains a mechanism carries a retirement criterion and a named
re-measurement trigger at adoption**
*Proposed from*: LL-147 + LL-150; BP-018's 2026-09-01 amendment as the working model.
*Rule*: When a BP constrains a mechanism (a timing gap, a lifecycle, a build variant, a threshold)
rather than describing a habit, it states at adoption: what would have to be true for the rule to be
retired, who may grant an exception, and — if it names a number — who re-measures it and on what
cadence. A rule enforced in code by a deliberate non-overridable names the owner of that decision.
*Rationale*: BP-018's rationale was void one week after adoption (the firmware it described was
deleted) and the mismatch stood for three months, discovered only when someone re-derived it; its
amendment then wrote the retirement criterion and the coupling to check first, and is the only such
clause among 72 entries. BP-020 hardened into the obstruction now blocking the highest-value
measurement available. BP-016 states an escalation threshold (>10 % trivial tests) with an owner and
no cadence; it reads 16.2 % and never fired. BP-009's execution step became unsafe against the
current tree.
*Applies to*: QM (adoption format), All (anyone proposing a BP)

### 6.3 Two entries already written that I would bring for promotion first

Ahead of anything new: **`LL-127` and `LL-140` are on the register, `Status: open`, and each names a
defect this audit paid to re-discover.** LL-127 is `F-4`'s mechanism, three weeks early (§2.1).
LL-140 is `UNMET` under another name — "an assertion whose precondition never arose is reported
inconclusive rather than pass" — which is R28's central value, proposed 2026-08-17 and never
adopted. Promoting those two costs a human sign-off and no engineering, and it is the cheapest
action available anywhere in this review.

---

## 7. Endorsement

**I endorse proceeding — conditionally, and not as scoped.** The diagnosis is correct and better
evidenced than anything else in this project's quality history; the mechanism half of the proposal
is the first serious attempt here to make test quality enforceable rather than exhorted; and the
Developer's four irreducible days (typed verdicts, the artifact, the deletions) would remove a class
of false verdict that has already produced one wrong REGRESS in production use.

Five conditions. The first is an ordering condition and I would treat it as blocking.

1. **Run the 80 minutes before spending the 154 days.** Resolve TASK-618 and execute WP-Z §5's
   session. All three armed-injector clusters — the evidence base for group STA and a large part of
   the case for the whole programme — are static predictions. `G-1`'s blast radius could be
   thirteen ids or none. Nothing else in either review is this cheap or this decisive. If
   TASK-618's resolution slips, that is itself the finding: the project cannot measure its own rig
   (§3.1, BP-020).
2. **Fund the ~30 ungated days now, and schedule nothing else yet.** The Developer's ten-day plan
   plus R18, R37, R46 and the §8 deletions are gated on no ADR, no board and no graded finding.
   Everything beyond them waits on ADRs A–E, on hardware, or on Tier-2 evidence (§5.4). Schedule
   M-HARNESS2 and WP-Z's 41 tasks as one programme — ~38 days are the same work — or a month is
   paid twice.
3. **No declaration ships without a mechanical check behind it.** Build R35 (with R36), the
   generated `reads:` plus `claim_class`, and R9 only in the executable/expiring two-field split.
   Do not build a prose `falsifier`, do not ask 213 authors for `effect` the harness can observe,
   and strike AC3 as a standalone criterion (§4).
4. **Every gate-first requirement carries C6's ledger clause explicitly, and no new gate lands
   advisory.** R3 in particular will land red across several apps; on this project's evidence that
   is survivable only with a dated shrink-only ledger, and fatal without one (§3.2).
5. **Validate AC1's instrument or replace it.** Re-grade one family with a second independent
   agent and publish the disagreement rate before AC1 is adopted. If that is not done, accept the
   programme on the mechanical criteria only — AC5, AC7, AC10, AC13, AC16 (§3.4, §5.4).

Two things I would add that are not conditions but are, on the register's evidence, the highest
ratio items available: **print the per-scope SKIP count in the run summary** (an afternoon; it is
what would have made C10 visible every run for a year), and **land the shell-side identity guard and
tick counters** the Architect identifies (~60 B, one commit, fixes `A-8` for all thirteen apps). Both
are observables rather than rules, which is the one intervention shape this project's own history
says holds (§3.1, BP-013 vs BP-016).

**What I do not endorse**: adopting the 55 requirements as a set of MUSTs on the strength of Tier-2
evidence; building any of the fifteen gates before the four that land at zero are in; and treating
this document set as the *first* time these rules have been written down. Twenty-one of them are
already adopted best practices on my own register. If the programme lands and there is still no
control that reads a run and no cadence that re-measures a threshold, this review will be written
again in a year with different finding keys.
