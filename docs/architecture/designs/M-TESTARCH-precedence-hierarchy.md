# Design — M-TESTARCH: a precedence hierarchy, and why a level-N failure is currently reportable as a level-N+1 failure

> Owner: Architect
> Status: proposed
> Date: 2026-09-01
> Revised: 2026-09-01 — independent review returned APPROVE WITH CHANGES; nine must-fixes and a scope
> cut applied. See §12 for what changed and the one thing I push back on.
> Companion to: [M-TESTARCH](M-TESTARCH-test-architecture.md) (§2b's tiers are the *other* axis — see §3),
> [M-TESTARCH boot-window observability](M-TESTARCH-boot-window-observability.md) (the RIG layer this
> builds on top of), [M-TOOLING](M-TOOLING-host-tool-architecture.md) §3 (the `lib/`↔`suite/` layering)
> Feeds: one ADR — **owed on acceptance, not written yet**; id allocated at creation (§10)
> Tracked-as: TASK-564, TASK-565, TASK-566, TASK-569 (TASK-567 deferred, TASK-568 to @QM)
> Registers: serialdbg-001 (extended — health surface) · X067

**Every claim below was measured against the working tree on 2026-09-01.** Line references and
commands are given so they can be re-run rather than believed.

---

## 1. The trigger, stated plainly

Over one session an agent produced four confident causal claims, each blaming something *outside* the
DUT, each wrong, each retracted only after a human challenged it: a reset-on-open theory fitted to one
sample; a failing cable; a re-plug that "fixed it" 33 minutes after the recovery had already happened;
and a WiFi AP declared down when the board was in the state [TASK-426](../../project/tasks-archive.md)
documents exactly — a degraded boot leaving the STA pinned to a dead SSID, auto-reconnect retrying it
forever until reset. The purpose-built diagnostic for that state, `get wifiCfg`
(`app/src/debug/serialConsole/cmdGet.cpp:199`), was never run. In the same window the human observed
the DUT stuck on the Winamp app and unable to switch apps — a *device* fault being read as
infrastructure.

The human's diagnosis: **there is no step anywhere that establishes DUT health before tests run or
before infrastructure is blamed, so symptoms get attributed outward.** This document takes that as the
requirement and asks what structure makes the mistake hard rather than discouraged.

It is not a proposal for a production serial console. Production firmware does not need one and none
is proposed; every health signal below is either already in production (heartbeat, `[boot]`,
`[bootphase]`) or already in the `SERIAL_DEBUG` build that the test rig flashes anyway.

---

## 2. Is the precedence axis genuinely missing?

**Yes — as an organising principle with any enforcement. Partially present, in four disconnected
places, none of which knows about the others.**

The honest inventory:

| Where precedence exists today | What it orders | Enforced? |
|---|---|---|
| `Dut.__init__` → `_wait_for_ready()` + `_verify_debug_firmware()` (`app/tools/lib/dut.py:307-312`) | connection, boot observation, WiFi, correct binary, first Spotify poll | **Yes** — raises `SetupFailure`, `app/tools/suite/serialdbg/runner.py:189` converts it to `[SETUP-FAIL]` + exit 3, no tests run |
| `run/test` step 0 — TLS-pin preflight (`run/test:80-98`) | certificate freshness before a 30–90 min run | No — explicitly warn-only, by design |
| `run/player-gate` two ordered legs (`run/player-gate:4-20`) | build variants at one commit | Yes, but this is the *variant* axis, not health |
| `run/player-gate:158-176` — `_assert_crossmode` | a leg's id list must contain a cross-mode cell | **Yes** — refuses with exit 2. The closest existing thing to a precedence rule, and it is about *suite composition*, not the board |

Above the `Dut` constructor there is nothing. `app/tools/suite/serialdbg/runner.py:225-246` iterates
`selected` and runs every id as a peer:

```python
for tid in selected:
    ...
    run_with_flake_retry(tid, _once)
    time.sleep(0.5)
```

(213 ids, counted from `build_all_tests()` — not the 208 M-TESTARCH quotes, a drift this document
should not have propagated.) No ordering is declared, no test declares a prerequisite, and no failure
stops or reclassifies anything downstream. A wedged DUT therefore produces N individual FAILs — one per test — and the run's
verdict is "the firmware has N bugs", which is the exact inversion the trigger describes.

### 2.1 It is not already covered by the tiers, the conformance matrices, or the id-binding gate

- **M-TESTARCH §2b (T0–T4)** answers *where a test runs* and is explicit that "the tier is an
  implementation detail of a contract row, not the organising principle" (§2). Its entry rule — *a
  test goes in the lowest tier that can falsify the claim* — is about cost, not prerequisite. A T3
  test that depends on WiFi and a T3 test that depends on nothing sit in the same tier.
- **The conformance matrices (§2.3, rows A1–A7 / S1–S6)** answer *what must be true of every app*.
  They are a completeness structure across a domain, not an ordering. `check_app_conformance.py`
  proves rows A5/A6 statically and has no notion of "do not bother asking A2 if the board is wedged".
- **C6 / the id-binding gate** answers *does every id resolve to a doc row*. Orthogonal again.

So the axis is genuinely new. It is also genuinely orthogonal — which is the constraint on naming
it (§3).

### 2.2 Three measured symptoms of its absence

**(a) The console's most diagnostic command returns no data through the harness's own API.**
`get wifiCfg` prints a bare `[wifiCfg] err=… ssid="…" bssid_set=… ch=… thr_rssi=…` line and *then* a
JSON ack carrying **no fields** (`app/src/debug/serialConsole/cmdGet.cpp:202-214`). `Dut.read_json()` discards every line that
does not start with `{` (`app/tools/lib/dut.py:673-676`), so `dut.cmd("get wifiCfg")` returns
`{"ok":true,"var":"wifiCfg"}` and throws the payload away. The one command that distinguishes
TASK-426's dead-SSID wedge from a genuinely absent AP is, from the harness's point of view, mute. It
is also a standing violation of M-TESTARCH §4 **I1** ("every `get` reply is a versioned, additive-only
JSON object") — recorded here because I1 has been treated as already true.

**(b) A device fault is labelled a rig fault, in code, today.** `app/tools/suite/serialdbg/runner.py:149-150` prints, for every
`SetupFailure`:

> `This is a RIG condition, not a test result. No tests ran; nothing here says the firmware is broken.`

`wifi-not-connected` (`app/tools/lib/dut.py:484-485`) routes through that sentence. So does
`boot-not-observed`'s *responsive-but-not-ready* case (`:397`). A board that booted, associated with
nothing, and is sitting in TASK-426's wedge is reported to the operator as **a rig condition**. That
sentence is the machine-readable ancestor of the failure mode in §1: the harness itself attributes a
device fault outward, in writing, on every run where it happens.

**(c) `SKIP` is the project's de-facto "precondition not established" verdict, and is indistinguishable
from "not applicable".** 261 `skip()` call sites across `app/tools/suite/serialdbg/`. Classified at
review over all 261: **172 precondition / 4 not-applicable / 74 other**. (My first pass said ~129 over
the 228 with literal messages and flagged it as a floor; it was, and the floor held.) The
`variant spotify=None` SKIP the human hit is one of the 172. **The 74 "other" are the real finding**:
they include *masked FAILs* — `"drill-in did not fire"`, `"lastPlaylistDraw did not advance"` — which
are neither preconditions nor inapplicability, but assertions that failed and were recorded as
non-results. That is the same inversion one class down. M-TESTARCH §2.3's own as-built note already
learned this lesson one level down — *"'Missing' and 'not applicable' are different, and collapsing
them would have manufactured six fake failures"* — and the same collapse is live in the result
vocabulary.

---

## 3. The hierarchy

**Tier answers *where* a test runs. Class answers *whether it may run yet*.** A test has exactly one
tier and exactly one class, chosen independently: HEALTH is T3-only by its nature, while APP has both
T0 members (rows A5/A6) and T3 members (rows A1–A4, A7). Nothing in §2b changes; this document adds
one rule alongside it — **a test declares the class whose failure would invalidate it, and may not
assert a claim belonging to a lower class.**

Deliberately **not** called a tier, and deliberately not lettered: `T0–T4` (tiers), `L0–L4`
(ADR-060 firmware levels), `C1–C6` (check_docs), `P0–P4` (M-TESTBASE items *and* task priority),
`A1–A7`/`S1–S6` (conformance rows) and `D0–D9` (ADR decisions) are all taken. The classes are named,
not numbered, and the names appear verbatim in run output.

| Class | Name | Entry rule (one sentence) | Examples |
|---|---|---|---|
| 0 | **RIG** | It belongs here if it can fail **with no firmware running at all** — everything about the host, the link, and the binary on the board. | port resolution (ADR-062), exclusive open, reset gap (BP-018), boot observed, `elf-mismatch`, `prod-firmware-flashed` |
| 1 | **HEALTH** | It belongs here if its failure **invalidates every other test in the run**, and it can be established in seconds with read-only console commands. | loop() liveness, shell answers *correct* data, task/heap floors, device-side WiFi identity, app-switch liveness |
| 2 | **CORE** | It belongs here if a **higher-class test would report a false failure** when this invariant is broken — the machinery every other test uses. | tap/drag injection dispatch, `appId` round-trip, `get idle` quiescence, shell busy gate, settings persistence |
| 3 | **APP** | It belongs here if it is a **row of the app-conformance matrix** — generated per app from `APP_ORDER`, never written per app. | A1 switch round-trip, A2 canvas-tap isolation, A3 switch-back residue, A4 busy contract, A7 first paint |
| 4 | **FEATURE** | It belongs here if **no other app could have the same test**. | Stock's chart drill-down, WebRadio's station retry, PlaneRadar's interpolation, the M3U/playorder cells |

The human's sketch maps onto this one-to-one: (1) connection → RIG, (2) DUT health → HEALTH, (3) core
functionality → CORE, (4) app functionality → APP, (5) app-specific features → FEATURE. RIG is
"largely done" exactly as they said — ADR-062, TASK-552/555/556/559/560/563 landed it — with one hole,
§7's OQ5 scripts.

### 3.1 The HEALTH class, concretely

**Ids are `T_DH_01..04`** — a `DH` (device health) family, matching the suite's own
`T_<FAMILY>_NN` convention so the ids bind under C6 like any others. Not `H1..H5`: `H1`/`H2` are
already hypothesis labels ([EXP-012](../../rnd/reports/) §3, `lessons_learned.md:381`), a collision
my §3 naming audit missed because it checked T/L/C/P/A/S/D and not H.

**Three checks ship. Two candidates were cut at review**, and the cuts matter more than the survivors:

| id | Check | Signal | Bound |
|---|---|---|---|
| **T_DH_01** | the shell answers **correct** data, not merely answers | `info`, `get variant`, `get playerMode` all reply with non-null fields | one `cmd()` each at the suite's default 3 s |
| **T_DH_02** | the device's own view of the network is coherent | `get ip` non-zero **and** `get wifiCfg`'s `ssid`/`bssid_set` consistent with an association | TASK-426's wedge signature |
| **T_DH_03** | app switching is alive | switch to a neighbour app and back; `appId` correct at each step; `get idle` returns idle | `get idle` (TASK-518) + the shell's own busy window |

`T_DH_01` is the check that would have turned tonight's `variant spotify=None` SKIP into a named
health failure. `T_DH_02` is the check that would have run `get wifiCfg` without anyone remembering
to. `T_DH_03` is the human's observed symptom, which today **nothing tests at all**.

**Cut — a loop()-liveness check.** The first draft had one (`[bootphase] 6 ready` observed, else a
heartbeat line). It is redundant: after `_wait_for_ready()` returns, boot has been observed by
construction — that is the function's postcondition and TASK-560 made it a hard one. The check
restated it, and its real value lives inside TASK-564's per-phase deadlines instead. Its proposed
bound was also the first crack in the budget (§below).

**Deferred — a heap/stack floors check (`T_DH_04`, TASK-569).** The draft cited
`docs/architecture/mem_manifest.yaml` for the floors. That file does not exist; it is
`app/mem_manifest.yaml`, and it carries `ceiling:` / `headroom:` / `buffers:` — a *static overlay
placement budget*, with no runtime `freeInt`/`lfbInt` figure and no stack watermark floor anywhere in
it. So R2(ii)'s "every bound cites a firmware constant" is **unsatisfiable for this check as
specified**. Worse, the signal is time-dependent: this project's own recorded rule is that no heap
number is trustworthy before ~150 s of settle, and the health class runs at boot+0 by design. A
check with no derivable bound, reading a signal that is invalid at the moment it is read, gating 213
tests, is a false-failure generator. It is deferred to its own task, advisory-only, and it is
therefore **not a member of this class** — a check that never blocks fails the entry rule ("its
failure invalidates every other test in the run"). Promoting it later requires deriving real floors
first, which is TASK-569's actual content.

**Cost, in honest wall-clock.** The three checks are a handful of round-trips — call it **≤ 10 s of
commands**. That is not what `run/dut-health` costs. Every `Dut` open resets the board
(`app/tools/lib/dut.py:314-316`), so the wall-clock figure is *boot + checks*, and TASK-561 measured
**46 s to console on a NO_AP_FOUND boot**. The honest number for a standalone health run is
therefore **~15 s typical, up to ~60 s on a degraded boot**, and that is what belongs in `CLAUDE.md`
and in §9, not a "20 s" that quietly excludes the boot it causes. Inside a suite run the checks are
additive-only (~10 s), because the boot has already been paid for by the constructor.

**Two implementation facts, both verified:**

- `T_DH_02` must read the bare `[wifiCfg]` line via `drain_log_lines()`, because `cmd()` discards it
  (§2.2a) — and it must then **drain the trailing JSON ack**, which `drain_log_lines` leaves in the
  buffer. Leaving it desynchronises the next `read_json()` by one reply: the TASK-548 bug class,
  and the reason this is written down rather than left to the implementer.
- `T_DH_03` is the only check that mutates device state, so it must restore the entry app and report
  entry/exit `appId`. The `[TASK-407] entry/exit playerMode` snapshot
  (`app/tools/suite/serialdbg/runner.py:214`/`:249`) is the existing precedent for exactly that shape.
  It runs last, so a failure inside it cannot leave the board on an unexpected app for the run.


## 4. Gating semantics

The property to preserve is one sentence: **a class-N failure must never be reportable as a class-N+1
failure.** Everything below is in service of it.

1. **Classes execute in ascending order.** Within a class, order is unspecified (today's family order
   is retained — see R3 on why *changing* order is not free).
2. **RIG failure** → `[SETUP-FAIL] <reason>` + exit **3**, unchanged. TASK-556's four reasons plus
   `boot-not-observed`, `elf-mismatch` and `prod-firmware-flashed` are the RIG vocabulary. No test
   results are printed because none exist.
3. **HEALTH failure** → `[HEALTH-FAIL] <check-id> <reason>` + exit **4** (new). Every CORE/APP/FEATURE
   id is recorded `NOT-RUN(blocked-by=HEALTH/<id>)`. The 3-vs-4 split *is* the payload: **3 means the
   host could not address a board; 4 means the board is not a valid subject.** Today both are 3, and
   both print "this is a RIG condition".
4. **CORE failure** → the failing test is a genuine **FAIL** (it is a real statement about the
   firmware) and exit is **1**; additionally every APP/FEATURE id is `NOT-RUN(blocked-by=CORE/<id>)`.
   Exit 4 stays reserved for "no test result in this run is trustworthy".
5. **APP failure** → FAIL, and it blocks **all** FEATURE tests. *(Corrected at review: the first
   draft blocked only that app's FEATURE tests. See §4.2 — the registry cannot express it.)*
6. **FEATURE failure** → FAIL. Blocks nothing.
7. **`NOT-RUN` is a fourth result bucket** in `lib/results.py`, printed and counted separately —
   never a PASS, never a SKIP, never a FAIL. A run whose summary reads `12 passed, 1 failed,
   200 not-run (blocked by HEALTH/T_DH_02)` cannot be misread as a firmware verdict, which
   `200 failed` can and did.
8. **`SKIP` is narrowed to "not applicable to this configuration"** — deferred to TASK-567 and
   re-scoped at review; see §4.3.

**Interaction with TASK-556 and TASK-560, precisely.** `SetupFailure` gains a `cls` field
(`RIG` | `HEALTH`); the closing sentence `_setup_fail()` prints is **selected by `cls`, not typed per
call site** — which is what makes §2.2(b) structurally unrepeatable rather than merely fixed once.
Reclassification on landing: `wifi-not-connected` → HEALTH, `boot-not-observed`'s
responsive-but-not-ready branch → HEALTH, `shell-unresponsive` → HEALTH; `device-vanished` /
`port-busy` / `port-permissions` / `port-error` / `elf-mismatch` / `prod-firmware-flashed` /
mute-board `boot-not-observed` stay RIG. `DUT_BOOT_GATE=warn` keeps working unchanged and gains a
sibling, `DUT_HEALTH=warn` (§6 R2).

### 4.1 Exit 4 is not free — four scripts and one parser must be taught it first

**This is the change most likely to cause the exact inversion the document exists to prevent, and it
was missed in the first draft.** `run/player-gate` special-cases only `rc == $SETUP_FAIL_EXIT`
(`run/player-gate:338`); an exit-4 leg falls through to `return 0`. Its log parser matches only
`PASS|FAIL|SKIP|FLAKE` (`run/player-gate:118`), so `NOT-RUN` lines are dropped, every declared id
resolves to `MISSING`, and `_compare_leg` (`run/player-gate:135-140`) prints **REGRESS** for each.
The first artifact a human would see from a HEALTH failure is the gate claiming a firmware
regression.

So exit 4 lands **with** its consumers, never before them, and the consumer list is enumerated rather
than assumed:

| Consumer | What it does today | Required change |
|---|---|---|
| `run/player-gate:338` | `rc == 3` → no verdict | add rc 4 → no verdict, distinct message |
| `run/player-gate:118` | `_parse_runner_log` regex | add `NOT-RUN` to the alternation |
| `run/player-gate:135-140` | `_compare_leg` | `NOT-RUN` must not adjudicate as `MISSING`/REGRESS |
| `run/test:69` | `[ "$rc" = "3" ]` | add the 4 arm with the health wording |
| `run/test-targeted:37` | same | same |
| `run/test-sync:29` | same | same |

`run/player-gate --selftest` already carries the gate's own negative tests (BP-068); the exit-4 and
`NOT-RUN` paths get cases there, which costs no DUT time.

### 4.2 Per-app blocking is dropped — the registry cannot express it

Rule 5 originally blocked only the failing app's FEATURE tests
(`NOT-RUN(blocked-by=APP/A2:Stock)`). Two obstacles, both structural:

- `TESTS` is `dict[str, callable]` (`app/tools/suite/serialdbg/__init__.py:24-33`) and the value is
  called directly (`app/tools/suite/serialdbg/runner.py:239`). Adding *any* per-test metadata is a
  value-type change on an interface shared by 7 family modules, `app/tools/suite/serialdbg/runner.py` (`:154`, `:164`, `:178`,
  `:239`) and `ve_suite_base.py`. That is the price of E1 as a whole and it is payable — but it is a
  refactor, not a field.
- Per-app blocking needs a **second** field, app attribution, which is not derivable. `shell.py` is
  an explicit multi-app catch-all holding the Weather, Crypto, Life, Matrix and taskbar cells, so
  neither the module name nor the id prefix identifies an app.

Not worth a second unbacked field on a first landing. **Rule 5 is all-or-nothing**, and per-app
granularity is recorded as OQ6 for when the APP class is actually generated from `APP_ORDER` (§2.3's
matrix), at which point the attribution exists by construction and the field is free.

### 4.3 The `SKIP` narrowing is deferred, and it is bigger than the draft said

The draft put the vocabulary gate in the first tranche on a ~129-site estimate. Re-measured at review
over all 261 call sites: **172 precondition / 4 not-applicable / 74 other**. My ~129 was a
conservative floor, as stated — but the "other" bucket is the finding: it contains **masked FAILs**
(`"drill-in did not fire"`, `"lastPlaylistDraw did not advance"`), which are neither preconditions
nor inapplicability. So this is ~250 sites of three-way adjudication, not a vocabulary sweep.

And the closed vocabulary as drafted **would have regressed TASK-553, which landed yesterday.** 553's
fix was precisely to *SKIP with a precondition explanation* — detecting a held arena at baseline
rather than reporting a false regression (`docs/project/tasks-architecture.md:241`). That fits none
of the five drafted members, so the gate would have converted it to a FAIL and re-manufactured the
exact false regression 553 removed. The vocabulary therefore needs a
**`precondition-not-establishable-in-suite-order`** member, and `T_PMT_04` is its reference case —
which, note, sits in the same function as a `not-applicable-variant` skip
(`app/tools/suite/serialdbg/player.py:1801` and `:1808`), so adjudication really is per-site.

Deferred to TASK-567, after TASK-566 has a baseline.


### 4.4 HEALTH × the flake policy

R2(iii) asks for the health ids to be declared in `flaky.yaml`. As drafted that is incoherent:
`run_with_flake_retry` (`app/tools/lib/results.py:105`) would then *retry* a health check — doubling
its cost, re-running the one mutating check (`T_DH_03`), and producing a `FLAKY-PASS` verdict with no
defined meaning for a gate whose whole job is a binary "is this board a valid subject".

Decided: **the HEALTH class is outside the flake policy.** No health id is declared in `flaky.yaml`;
`runner.py` dispatches the health family *without* `run_with_flake_retry`. A health check that is not
deterministic enough to answer in one attempt is not fit to gate 213 tests, and the correct response
is to fix or demote the check — the same standard §3.1 applies to the deferred `T_DH_04`. A health
check may retry *internally* on a bounded deadline (the `_wait_for_ready` probe pattern,
`app/tools/lib/dut.py:363-374`); that is a bound, not a flake.

Two consequent changes in `lib/results.py`, both small and both required:

- a `NOT-RUN` bucket in `print_results` alongside `passed`/`failed`/`skipped`/`flaky_pass`
  (`app/tools/lib/results.py:153-156`);
- `rc = 0 if failed == 0 else 1` (`:176`) must be bypassed for the health case — a run with zero
  FAILs and 200 `NOT-RUN` must exit **4**, not 0. This is the single line where "silently green" is
  most likely to reappear.


## 5. Mechanical enforcement — what protects the next agent

Prose in a design document is the weakest possible answer to the human's question, so it is not the
answer. Five mechanisms, ordered by how much of the failure they actually remove, each with its cost.

**E1 — The class is a field on the test registry, and the runner obeys it.** Each family's `TESTS`
entry carries a class; `runner.py` groups, orders and gates on it. An unclassified id defaults to
FEATURE (the safe default — it blocks nothing and is blocked by everything). A T0 gate asserts that
every id in the CORE set is *explicitly* classified, so the small consequential set cannot drift into
existence by default. *Cost*: **not one field.** `TESTS` is `dict[str, callable]` and the value is called directly, so
this is a value-type change on an interface shared by 7 family modules, `app/tools/suite/serialdbg/runner.py` (`:154`, `:164`,
`:178`, `:239`) and `ve_suite_base.py` — a refactor across 213 ids, plus R3's baseline. See §4.2.

**E2 — The verdict names the class.** `[HEALTH-FAIL]`, `NOT-RUN(blocked-by=…)`, exit 4. A reader —
human or agent — cannot get from this output to "the firmware has 200 bugs" or to "the cable is bad",
because the output already says which layer failed and which layer was therefore never asked.
*Cost*: ~60 lines in `lib/results.py` + `runner.py`; the flake policy's four-bucket summary is the
pattern to copy.

**E3 — The class-boundary message is derived, not typed.** §4's `cls`-selected sentence. This is the
smallest change in the document (~20 lines) and it deletes the single worst artefact found: the
harness telling the operator that a dead-SSID board is a rig condition.

**E4 — `run/dut-health`: a named pre-flight command, ~15 s typical (up to ~60 s on a degraded
boot).** The HEALTH class, standalone, one open, exit 0/4, printing one evidence block. Listed in
`CLAUDE.md`'s run-script table. **This is the direct fix for the actual failure**: `get wifiCfg`
existed, was purpose-built for exactly the observed state, and was never run — not because a rule was
missing but because nothing pointed at it. A cheap obvious first step beats a policy that has to be
remembered. *Cost*: a thin wrapper over E1's health family.

> **It is pre-flight, not post-mortem, and this is a hard constraint — not a caveat.** Opening the
> port asserts DTR and resets the ESP32 (`app/tools/lib/dut.py:314-316`), and per TASK-426 **a reset
> is precisely what clears the dead-SSID wedge**. So running `run/dut-health` *after* forming a
> theory about a misbehaving board destroys the state it was invoked to diagnose, shows a healthy
> board, and manufactures a fifth wrong conclusion — the failure mode of §1, with a tool's authority
> behind it. Two obligations follow, both mandatory:
>
> 1. **The tool says so in its own output.** Every run prints, before its verdict:
>    *"this opened the port, which reset the board — this verdict describes the boot that reset
>    caused, not the state you were investigating."*
> 2. **A wedged board is diagnosed from the monitor, not from this tool.** The pre-reset state lives
>    in the tmux monitor's disk log (`run/monitor-read`) and in the `[bootphase]`/heartbeat stream
>    already being captured. Read that first; `run/dut-health` answers "is this board fit to test
>    *now*", which is a different question and the only one it can honestly answer.
>
> A no-reset attach path would fix this properly and is **not** proposed here: suppressing the
> open-reset is Option E of the boot-window design, rejected on C1, and TASK-557's standing advice is
> not to touch the serial-open path on current evidence. Recorded as OQ7.

**E5 — Every run states its own premise.** One `[health]` line at the head of every DUT run: last
`[bootphase]`, boot duration, `ip`, `wifiCfg` ssid, `freeInt`/`lfbInt`, `appId` round-trip verdict,
wall-clock. The heap figures are **reported, never asserted** — they are context for a later reader,
not a gate (§3.1's deferred `T_DH_04` is where asserting on them would live, and why it does not yet). The boot-window design's §1.1 says the defining problem is that *"no run's premise is
verifiable after the fact"*; this is the line that makes it verifiable, and it costs one printf-worth
of host code. *Cost*: negligible. **Highest ratio in the document.**

### 5.1 The attribution rule — how it is enforced rather than stated

The rule: **infrastructure may not be blamed until DUT health has passed.** It cannot be enforced in
the strong sense — nothing can stop an agent from typing a sentence. What can be done is make the
wrong sentence *contradicted by the same output that would have to be quoted to support it*:

- **By construction (ordering).** `[SETUP-FAIL]`, the rig vocabulary, is only reachable *before* the
  HEALTH class has passed. After a green HEALTH block, a transport failure is classified
  `device-vanished-after-health-pass` and the classifier reprints the health line **with its
  timestamp**. A cable theory then has to explain a board that answered three checks seconds earlier
  **on the same boot** — that last qualifier is the load-bearing part, and it is why this bullet
  works where E4 alone does not: within one `Dut` session there is no intervening reset, so the
  health evidence and the failure describe the same board state. Across sessions they do not, which
  is exactly the trap E4 now prints a warning about. TASK-557's investigation is the case that needed
  this and did not have it.
- **By evidence (E5).** The premise is in the run's own output, so a retrospective claim is checkable
  against the artefact rather than against memory. Four of the trigger's claims were retracted only
  after a human challenged them; three of the four are falsifiable from an E5 line alone.
- **By discoverability (E4).** The counterfactual is not "the agent should have known the rule"; it is
  "the agent should have run one command". Name the command, put it in the script table, make it 20
  seconds.
- **By practice (a BP, QM-owned).** Proposed, not adopted here — per AGENTS.md the Architect does not
  self-promote practices: *an infrastructure or environment cause may not be asserted until
  `run/dut-health` has been run and its output quoted.* Checkable trigger: an infra-cause claim in a
  task row or commit message without an accompanying health block.

  **I recommend adopting the BP and explicitly NOT mechanising it in `check-docs`.** A natural-language
  trigger ("cable", "AP is down", "re-enumeration") over prose rows would be high-false-positive and
  would fire on every row that legitimately *discusses* one — including TASK-557's, which is correct
  as written. TASK-543 declined a `check-docs` heuristic on the same reasoning and that precedent
  should hold. The enforcement that works here is E3+E5, which put the contradicting evidence in the
  output; the BP is the human-facing half, and it should be honest about being the weaker half.

---

## 6. Risks

**R1 — Every run gets slower, and short runs get relatively much slower.** ~10 s of health commands
against a 30–90 minute `run/test` is noise; against a one-id `run/test-targeted` it is a visible
fraction of the cycle an agent iterates on. (Inside a suite run it is only the commands — the boot is
already paid for by the `Dut` constructor. Standalone, §3.1's honest figure applies.) *Mitigation*: `DUT_HEALTH=warn` (downgrade to a printed warning) and
`DUT_HEALTH=skip`, both of which stamp the summary with `health not established` so a skipped gate can
never be silently absent from a result someone later quotes. Same shape as `DUT_BOOT_GATE=warn`, same
reasoning (§8 R3 of the boot-window design): an operator mid-investigation must never be tempted to
revert the gate wholesale.

**R2 — A flaky HEALTH check is catastrophic, because it gates 213 tests.** This is the largest risk in
the document. *Mitigations, all mandatory*: (i) **no network fetch may enter the HEALTH class** —
`T_DH_02` asserts the device's own link state, never an external endpoint; (ii) **no check may enter
the class without a derivable bound** — the draft's heap/stack check failed this and was deferred
(§3.1), and the rule is what caught it; (iii) **no time-dependent signal at boot+0** — same cut, same
reason; (iv) the class is **outside the flake policy** (§4.4): a check that cannot answer in one
attempt is unfit to gate 213 tests, and retrying `T_DH_03` would re-run the one mutating check.

The draft's own mitigation list is instructive here and is left visible rather than tidied away: it
cited a `mem_manifest.yaml` that does not hold runtime figures, and mandated a flaky declaration whose
retry semantics were undefined for a gate. Both were caught at review, and both are now *entry rules*
rather than mitigations — which is the stronger place for them, because an entry rule excludes the
check instead of managing it.

**R3 — Class ordering is a change of execution order, and this suite has known order-dependence.**
TASK-553 was exactly that: `T_PMT_04` failed behind `T_PLR_25` and passed alone. Reordering by class
is therefore *not* free and cannot be verified by the suite it reorders (M-TESTARCH §9, the
verification paradox). *Mitigation*: land E1's classification **inert** first — the field is populated
and reported, execution order unchanged — take the ≥3-run baseline with the flaky set pre-declared,
and only then switch the runner to class order. That staging is TASK-566's whole shape and it is why
566 is priced above 565.

**The strongest argument for the inert stage is one the draft missed**: it makes the reorder's blast
radius *predictable on paper*. With classes populated but unused, the class-ordered id sequence can be
diffed against today's actual sequence, and every pair whose relative order inverts is enumerable —
**with zero DUT time**, before anything runs. The baseline then confirms a prediction rather than
discovering a surprise.

**And TASK-553 is a mechanism, not an anecdote.** `mb_arena_acquire()` early-returns on
`if (s_owned) return true;` *before* incrementing, so **any** test asserting a 0→1 acquire edge is
order-fragile by construction, not just `T_PMT_04`. Nobody has enumerated the other tests with that
shape. Doing so is part of TASK-566's inert stage, not a follow-up: the diff above tells you which
pairs invert, and this tells you which assertions care.

**R4 — `NOT-RUN` can hide a regression.** A permanently red CORE test would silently blank the APP and
FEATURE classes. *Mitigation*: the CORE set is small, explicitly enumerated (not defaulted), a CORE
failure is loud (FAIL + exit 1 + a NOT-RUN block naming it), and the summary prints the blocked count
in the same line as the pass count. A shrinking `NOT-RUN` count is a gate; an invisible one is a
fiction — the same argument M-TESTARCH §6.1 made for the id-binding ledger.

**R5 — Recovery, wedge risk, and the diagnostic that destroys its own evidence.** Nothing here
changes flash, reset, or restore paths, and no firmware change is proposed at all beyond §11 OQ2's
optional `wifiCfg` JSON. Two of the three health checks are read-only console reads; `T_DH_03` mutates
app state, so it restores the entry app and runs last. `run/dut-health` opens the port once and
honours the reset gap through `Dut`.

**But it does reset the board, and that is a real hazard rather than a technicality** — TASK-426's
wedge is *cleared by a reset*, so a post-hoc health run on a misbehaving board returns green and
erases the state. E4 now carries the two obligations that contain this (the printed warning, and
"read the monitor first"). It is the one place in this design where the tool could actively make a
diagnosis worse, so it is stated twice on purpose.

**R6 — Doing nothing.** The status quo has a measured cost: two of the last five test-framework tasks
(553, 557) were investigations into failures whose premise was never establishable, and one full
session was spent on four wrong outward attributions. The rig currently tells its operator, in
writing, that a dead-SSID board is a rig condition.

---

## 7. Sequencing against the in-flight work

| Item | State | Relationship |
|---|---|---|
| TASK-555 / 556 / 559 / 560 / 563 | done | **The RIG class, delivered.** This design takes them as the floor and reclassifies three of their reasons (§4) rather than changing their mechanisms. 556's `test_serial_classify.py` stub-the-serial pattern is the model for 565/566's negative tests (BP-068). |
| **TASK-561 (`[bootphase]`) — nothing consumes it** | done, **gap open** | **The consumer belongs here, and it is TASK-564.** The phase stream is HEALTH's cheapest evidence and the RIG/HEALTH boundary detector: stuck at phase 1 = SPIFFS wedge (RIG-adjacent, board fault), stuck at phase 3 = the WiFi cascade (HEALTH/`T_DH_02`), reached 6 = the console is answerable and every later timeout is about *something else*. It also converts three of the boot-window design's 13 undeclared constants into per-phase deadlines and gives every `SetupFailure` a `last-phase=` field. Doing it as part of this design rather than as an orphan follow-up is the single sequencing call I am most confident about. |
| **TASK-557** (rig instability, unresolved, non-stationary) | open | **Helped, not disturbed.** Nothing here touches the serial-open path — 557's standing advice is respected. E5's premise line and the `-after-health-pass` label are the discrimination 557's arm-A/arm-B design was reaching for and could not get. **Land 564/565 freely; hold 566's order switch until 557 closes or signs off**, since a reordered suite changes what 557 is measuring. |
| TASK-558 (monitor liveness) | open | Adjacent, not blocking. The tmux monitor is not on the test path — no `run/test*` invocation reads it. If 558 adds a liveness probe, HEALTH should *not* absorb it: a dead monitor invalidates nothing about a test run, and folding it in would put a non-invalidating check inside a class whose entry rule is "its failure invalidates every other test". |
| **OQ5** — scripts that bypass `Dut` | open | **Now load-bearing, and the "three scripts" figure is a substantial undercount.** Re-measured 2026-09-01: **14 files** construct a raw `serial.Serial` outside `lib/dut.py`, **9 of them defining their own `class Dut`**. The ones a `run/` script actually invokes are six plus a whole suite: `test_adr045_gate.py` (`wr-gate`), `test_webradio_soak.py` (`wr-soak`), `test_ae04_teardown.py` (`ae04`), `test_fbrowser_player.py:273` + `test_playorder_player.py:216` (**invoked as gate cells at `run/player-gate:386-387`**, and as `browser-player`/`playorder-player`), and `run_sync_tests.py:51`, whose private `class Dut` means **all of `run/test-sync`'s T097–T116 bypasses the ladder**. The "three" traces to TASK-563's row, which was about the reset-gap *stamp* — a different property, correctly counted for its own purpose and wrongly reused for this one. Under this design all of these bypass RIG *and* HEALTH. Still its own row; the scope on that row needs correcting first. |
| M-TESTBASE P4 / `get idle` (TASK-518) | landed | **Reused directly.** `T_DH_03` and CORE's quiescence rows are clients of it. No new firmware primitive is needed for anything in §3.1. |
| M-TESTARCH §2.3 conformance matrices | rows A5/A6 built | **The APP class is that matrix.** This design does not create an app taxonomy; it says the matrix rows *are* class APP and inherit the gating semantics. A5/A6 stay T0. |

**Condensed order** (scope cut applied at review): **564** (`[bootphase]` consumer) → **565**
(the slimmed HEALTH family `T_DH_01..03` + `run/dut-health` + E3's derived sentence + E5's premise
line) → **566** (classification inert → baseline → class-ordered runner + `NOT-RUN` + exit 4, landing
**with** §4.1's four scripts and one parser) → **569** (`T_DH_04` heap/stack floors, advisory, once
real floors exist) → **567** (SKIP adjudication, after 566 has a baseline) → **568** (QM: LL + the
proposed BP). 566's order switch is gated on 557.

**What ships first, and it is deliberately small**: E3 and E5. Both are host-only, both are a few
dozen lines, and between them they delete the worst artefact in the system (the harness calling a
device fault a rig condition) and add the thing whose absence made every previous investigation
unfalsifiable (a run that states its own premise). Neither needs the class machinery to be worth
landing.

---

## 8. What this does **not** do

- It does not add a production serial console, and does not propose one.
- It does not make boot faster or WiFi more reliable (TASK-426/436 territory).
- It does not create a second tier vocabulary — §3's reconciliation is the whole point of the naming.
- It does not touch the reset-on-open path, `_DUT_DRD_WINDOW_S`, or any flash/restore sequence.
- It does not claim to prevent an agent from asserting a wrong cause. It makes the wrong assertion
  contradicted by the output it would have to cite (§5.1), which is the strongest available mechanism
  and is worth less than it sounds.

---

## 9. Exit criteria

1. No `SetupFailure` prints "this is a RIG condition" for a device-side fault. Provable by reading
   `_setup_fail()`: the sentence is selected by `cls`, and no call site types it.
2. A run whose board is unhealthy exits **4**, prints `[HEALTH-FAIL] <id>`, and reports every other id
   as `NOT-RUN`, with zero FAILs. Negative-tested against a stubbed serial (BP-068), no DUT needed.
3. `run/dut-health` exists and its output alone answers all three of §3.1's questions. Wall-clock is
   stated honestly wherever it is documented — **~15 s typical, up to ~60 s on a degraded boot**,
   because the tool's own open resets the board (TASK-561 measured 46 s to console on a
   NO_AP_FOUND boot). A "20 s" figure that excludes the boot it causes is not acceptable in
   `CLAUDE.md` or here.
4. `run/dut-health` prints its reset warning (§5 E4) **before** its verdict, on every run,
   unconditionally.
5. Every DUT run's first output block states the board's premise (E5), including the last
   `[bootphase]` reached.
6. Every registry id carries a class; the CORE set is explicitly classified, not defaulted; a T0 gate
   asserts both.
7. Exit 4 is understood by every consumer enumerated in §4.1 — four `run/` scripts, one log parser,
   one comparator — with `--selftest` cases for the exit-4 and `NOT-RUN` paths. **No exit-4 code path
   ships before this row is green**, or a HEALTH failure surfaces as `REGRESS` from
   `run/player-gate`.
8. Before the runner's execution order changes: the class-ordered id sequence has been diffed against
   today's on paper, the inverted pairs enumerated, and the 0→1-edge-assertion tests (R3's
   `mb_arena_acquire` shape) listed; plus a ≥3-run pre-declared-flaky baseline (R3).
9. `run/check` 11/11 and `run/check-docs` 6/6 at every step.

---

## 10. What is owed on acceptance

- **An ADR** (next free id at creation time; ADR-062 is the highest allocated as of 2026-09-01) — "DUT test results are
  ordered by precedence class, and a class-N failure is never reported as a class-N+1 failure",
  carrying §3's tier/class reconciliation and §4's exit-code contract.
- **No new IFC.** The `[bootphase]` contract is already owed by
  [M-TESTARCH boot-window observability](M-TESTARCH-boot-window-observability.md) §9 and is still
  unwritten; TASK-564 consumes that token, so it should be pinned in the same pass rather than
  duplicated here. If §11 OQ2 is taken, `get wifiCfg`'s JSON payload extends serialdbg-001 under
  BP-024 (additive-only) and needs no separate contract.
- **Registry**: no new feature id — this extends **serialdbg-001** (health surface). One interaction
  edge reserved: **X067** (health class ↔ runner ordering ↔ verdict taxonomy), `test_coverage: []`
  until VE lands the suite.

---

## 11. Open questions

- **OQ1 — Should HEALTH run once per boot or once per run?** `run/test-targeted` boots fresh every
  invocation, so they coincide today; a future harness that attaches to a running board would need
  the distinction. Defer until such a harness exists.
- **OQ2 — Should `get wifiCfg` emit its payload as JSON?** It is the I1 violation in §2.2(a), it is
  additive-only under BP-024, and it would let `T_DH_02` use `cmd()` instead of `drain_log_lines()` and remove the ack-drain hazard of §3.1. Cheap
  firmware change; **Architect lean yes, but out of scope for 564–568** — the harness-side parse works
  today and this design should not acquire a firmware dependency it does not need.
- **OQ3 — Does CORE need its own generated matrix, as APP has?** The CORE set is currently a
  judgement call over ~15 ids. If it grows past ~25, it wants the same enumerate-and-generate treatment
  §2.3 gives apps and settings. Revisit at that size, not before.
- **OQ4 — Should `NOT-RUN` block the run or merely mark it?** §4 blocks. The alternative — run
  everything, mark the results untrustworthy — preserves information about intermittent faults at the
  cost of 30–90 minutes of DUT time per unhealthy run. Blocking is right while the DUT is a single
  serialised resource (OQ-D); revisit if a second board lands (TASK-550/552).
- **OQ5 — Where do the `Dut`-bypassing scripts get their ladder?** §7 raises the priority of the
  boot-window design's OQ5, corrects its count (6 scripts + the whole `run/test-sync` suite, from 14
  raw-`serial.Serial` files), and does not answer it. Migrating them onto `Dut` is the obvious answer
  and remains that document's row, not this one's.
- **OQ6 — Per-app FEATURE blocking.** Dropped from §4 rule 5 because the registry cannot attribute a
  test to an app (`shell.py` is a multi-app catch-all). It becomes free once the APP class is
  generated from `APP_ORDER` per M-TESTARCH §2.3, because attribution then exists by construction.
  Revisit there, not before.
- **OQ7 — A no-reset attach path for `run/dut-health`.** It would make the tool a genuine post-mortem
  instrument instead of a pre-flight one (§5 E4). Not proposed: suppressing the open-reset is the
  boot-window design's Option E, rejected on C1, and TASK-557's standing advice is not to touch the
  serial-open path on current evidence. Re-open only after 557 closes.


---

## 12. Review response — what changed, and what I push back on

Independent review, 2026-09-01, returned APPROVE WITH CHANGES. **All nine must-fixes verified against
the tree before applying** — none was taken on the reviewer's word, and every one of them held.

| # | Item | Applied |
|---|---|---|
| G1 | exit 4 silently breaks `run/player-gate` | **The most important find in the review.** New §4.1 enumerates all six consumers; exit criterion 7 forbids shipping an exit-4 path before they are taught. Verified: `run/player-gate:338` handles only rc 3, `:118`'s regex drops `NOT-RUN`, `:135-140` then prints REGRESS. A HEALTH failure would have surfaced as a firmware regression — this document's own inversion, produced by this document's own change. |
| W1 | H3's citation wrong, bound unsatisfiable | Verified: the file is `app/mem_manifest.yaml` (not `docs/architecture/`) and holds `ceiling:`/`headroom:`/`buffers:` only. Check **deferred** to TASK-569, advisory, and explicitly **not** a member of the class (§3.1). R2 rewritten so "derivable bound" and "no boot+0 time-dependent signal" are *entry rules*, not mitigations. |
| W2 | ≤20 s budget self-contradictory | §3.1 restated: ~10 s of commands inside a suite run; **~15 s typical / ~60 s degraded** standalone, because the tool's own open resets the board. Exit criterion 3 pins the honest figure for `CLAUDE.md` too. |
| W3 | `run/dut-health` destroys the state it diagnoses | **Fixed first, as instructed.** E4 re-framed as pre-flight with two mandatory obligations (a printed reset warning before the verdict; "read the monitor first" for a wedged board). §5.1's bullet re-argued around *same-boot* evidence, which is the only form that holds. OQ7 records the no-reset path as deliberately not proposed. |
| G2 | registry cannot express per-app blocking | Rule 5 dropped to all-or-nothing; new §4.2 states the value-type refactor cost across 7 modules + `app/tools/suite/serialdbg/runner.py:154`/`:164`/`:178`/`:239` + `ve_suite_base.py`, and why app attribution is not derivable (`shell.py` is a multi-app catch-all). Per-app granularity → OQ6, free once the APP class is generated from `APP_ORDER`. E1's cost line corrected from "one field" to "a refactor". |
| C1 | TASK-567 regresses TASK-553 | Verified at `tasks-architecture.md:241` — 553's fix *was* a precondition-explained SKIP. Vocabulary gains `precondition-not-establishable-in-suite-order`; §4.3 records `T_PMT_04` as its reference case and notes it sits in the same function as a genuine `not-applicable-variant` skip (`app/tools/suite/serialdbg/player.py:1801`/`:1808`). 567 deferred. |
| W4 | OQ5 "three scripts" undercount | Re-measured: **14** files build a raw `serial.Serial` outside `lib/dut.py`, **9** with a private `class Dut`; six are `run/`-invoked, plus `run_sync_tests.py` taking all of T097–T116 off the ladder. §7 corrected, with the provenance of the wrong number named (TASK-563's row, counting a different property). |
| G3 | HEALTH × flake undefined | New §4.4: the class is **outside** the flake policy — no declaration, no `run_with_flake_retry`, internal bounded retries only. `lib/results.py:153-156` gains a `NOT-RUN` bucket and `:176`'s `rc = 0 if failed == 0` is called out as the single line where "silently green" would reappear. |
| W5 | six citation drifts | All six verified and fixed: `app/tools/suite/serialdbg/runner.py:149-150`; TASK-407 at `:214`/`:249`; `app/tools/lib/dut.py:484-485`; **213 ids not 208**; `wait_shell_cooldown_clear` removed entirely from §3.1 — it defaults to 2.0 s (`app/tools/lib/dut.py:728`) and polls `get shellCooldown`, so it was cited for a job it does not do (the 3 s came from a stale comment at `app/tools/lib/dut.py:359-360`); and §2 now lists `_assert_crossmode` (`run/player-gate:158-176`) as a fourth enforced precondition. |

**Scope cut applied in full**: ship E3, E5, TASK-564, and a slimmed TASK-565 (`T_DH_01..03`); delete
the loop()-liveness check; defer the heap/stack check to TASK-569; defer TASK-567; keep TASK-566
staged as written.

**Nice-to-haves taken**: `T_DH_*` ids replace `H1..H5` (the reviewer is right that my §3 naming audit
checked T/L/C/P/A/S/D and not H, and `H1`/`H2` are live hypothesis labels); the `wifiCfg` ack-drain
hazard is written into §3.1 rather than left to the implementer; `suite/serialdbg/__init__.py:8-15`'s
stale "0 families migrated / not yet the live path" docstring is noted on TASK-566's row.

**The inert-first call was upheld, and the reviewer's argument for it is better than mine** — it is
now R3's lead: the inert stage makes the reorder's blast radius predictable **on paper**, by diffing
the class-ordered id sequence against today's with zero DUT time. Also folded in: TASK-553 is a
*mechanism*, not an anecdote — `mb_arena_acquire()`'s `if (s_owned) return true;` makes **any** 0→1
edge assertion order-fragile, and enumerating the others is now part of 566's inert stage (exit
criterion 8) rather than an unowned follow-up.

**One push-back, on framing rather than substance.** The review is right that ~250 sites need
three-way adjudication and that 567 must wait. But the 74 "other" skips it surfaced — the masked FAILs
— are **not** merely a sizing problem to be deferred with the rest. A test that failed and recorded a
SKIP is the document's own thesis reproduced inside individual test bodies, and it is the one part of
567 that is a *live defect* rather than a hygiene debt. I have kept 567 deferred as instructed, but
its row now names that bucket as the first thing to look at when it is picked up, rather than treating
the three categories as equal work. If any of those 74 turn out to be masking a real regression, that
is a finding that should not wait on a baseline.
