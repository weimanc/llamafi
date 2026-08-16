# Design — M-TESTARCH: what the test architecture should be

> Owner: **Architect (seams) + VE (plan)** — joint. VE owns `test_plan.md` and `regression_suite/`
> per AGENTS.md; the Architect defines the seams and VE challenges them for testability.
> Status: **reviewed + restructured** — 2026-08-16 (was: skeleton, same day)
> Tracked-as: TASK-483
> Companion to: [M-TOOLING](M-TOOLING-host-tool-architecture.md) F1/F2, [ADR-060](../decisions/ADR-060.md) D0
> Supersedes: the 2026-08-16 skeleton (63 lines). Its Known/Open items are dispositioned in §1 —
> nothing was discarded silently.

**Review method.** Blank-slate, as asked: §2–§7 describe what a test architecture for this project
*should* be, derived from the system's own constraints rather than from what exists. §1 comes first
anyway, because four of the skeleton's six "Known" facts are wrong, and a blank-slate design built on
them would be blank-slate in the wrong place.

Every number below was re-measured on 2026-08-16 against the working tree. Commands are given so
they can be re-run rather than believed.

---

## 1. Corrections to the skeleton — measured, not asserted

| Skeleton claim | Verdict | Evidence |
|---|---|---|
| "There are no unit tests and no host test target." | **FALSE** | `app/tools/test_check_docs.py` (372 lines) is a fixture-backed, golden-file host suite for `T_DOC_01..09`, gated at `run/check` gate 9 via `smoke_test.sh`. `test_adr045_gate.py` (452 lines) is a second. Both are host-only, no DUT, no network, ~2 s. |
| "There is no shared DUT layer." | **FALSE — and this is the important one** | `Dut` has **16 importers**, all `from run_serialdbg_tests import Dut`. A shared DUT layer exists; it lives *inside the 10 229-line suite*. |
| "33 tools re-implement port resolution." | **WRONG SHAPE** | **Zero** Python tools re-derive VID:PID — no `udevadm`, no `list_ports`, no `1a86` anywhere under `app/tools/`. What exists is **19 files hardcoding `/dev/ttyUSB0`** as an argparse default. That is not duplicated logic; it is *absent* logic, and it is worse: the port has really been `ttyUSB1`. |
| "128 test bodies … ~150 shared helpers." | **WRONG COUNTS** | `grep -c '^def t'` → **209** test bodies; 280 top-level defs total, so **~71** helpers, not 150. The registry declares **208 ids**. The suite is half again bigger than M-TOOLING F1 says, and its helper layer is half the claimed size. |
| "The taxonomy exists in prose, not in code" / OQ3 "bound by nothing" | **TRUE, and understated** | Measured drift, both directions: **95 of 148** non-archive doc-table ids have **no executable body** (64 %). **56 of 208** runner ids appear **nowhere** in `docs/verification/`; **5** (`T_PLE_WR_156..160`) appear nowhere in `docs/` at all. `test_plan.md` is not the source of truth for what runs, in either direction. |
| "D0 changes what is possible" | **TRUE**, and VE's OQ1 caution stands verbatim | Kept as-is. See §3. |
| "Some seams are already mockable" | **TRUE** | Kept. `dataTask`/IFC-001 is the one real seam today. |

**Consequences of the corrections, before any design work:**

- **TASK-478 as written ("build `lib/dut.py`") is the wrong task.** `Dut` already exists and is
  already shared. The real defect is that it starts one step too late: it takes a port *string* and
  never finds one. The fix is a `resolve_port()` helper that shells out to `run/port`, plus moving
  `Dut` out from under the suite so importing the library does not import 209 test bodies. That is
  smaller than the design implies and should be re-scoped, not re-planned.
- **TASK-480 (split the runner) is riskier than staged.** 16 external tools import from that module,
  including private names (`_switch_to`, `_restore_spotify`, `_DUT_WIFI_WAIT_S`, `_PORTAL_INDICATORS`).
  A split is not a file move; it is an API extraction with 16 call sites, and the module has no
  declared public surface to preserve. **Extract the library first (`lib/dut.py`), migrate the 16
  importers, and only then split the test bodies.** Doing it in the stated order breaks every
  satellite suite mid-refactor, with the verification paradox (§7) in force.
- **The id-binding gap is the largest finding in the document and is currently an Open question.**
  It should be a decision. See §6.

---

## 2. The logical design — what must be true. (The tiers in §2b are only the physical half.)

**Correction to this document, 2026-08-16.** §2b's five-tier model answers *where a test runs*. It
does not answer *what must be true*, and a taxonomy of execution venues is a physical design, not a
logical one. The firmware got a logical design — components, levels, interfaces (ADR-060). The test
architecture, as written up to this point, did not. This section is the missing half, and it changes
the plan: **the tier is an implementation detail of a contract row, not the organising principle.**

### 2.1 The evidence that this is missing, not merely unstated

`t_wx_01…05` (Weather) and `t_cx_01…05` (Crypto) are **the same five tests, character for character**
— same comment banners, same `sleep(0.15)`/`sleep(0.1)`, same skip strings — with `Weather`→`Crypto`
and `weatherReady`→`cryptoReady` substituted. They are two hand-copied instances of an unnamed
battery.

Because the battery is unnamed, nobody can see where it was *not* copied. Derived mechanically from
`app_ids_gen.APP_ORDER` against the test bodies:

| app | round-trip | canvas-tap guard | switch-back residue | data-arrives | error state |
|---|:--:|:--:|:--:|:--:|:--:|
| Spotify | ✅ | ✅ | ✅ | ✅ | ✅ |
| Clock | ✅ | ✅ | — | — | ✅ |
| Weather | ✅ | ✅ | ✅ | ✅ | ✅ |
| Crypto | ✅ | ✅ | ✅ | ✅ | ✅ |
| Matrix | ✅ | ✅ | ✅ | — | ✅ |
| Life | ✅ | ✅ | ✅ | — | — |
| Stock | ✅ | — | ✅ | — | ✅ |
| **Aquarium** | **—** | **—** | **—** | **—** | **—** |
| Teletext | ✅ | — | — | ✅ | ✅ |
| PlaneRadar | ✅ | — | — | — | ✅ |
| Settings | ✅ | — | ✅ | — | ✅ |
| WebRadio | ✅ | — | ✅ | — | ✅ |
| LocalPlayer | ✅ | — | — | — | ✅ |

**Aquarium has zero conformance coverage** — a registered, taskbar-visible app. The canvas-tap guard
is a *shell* invariant that must hold for every app; it is tested for **5 of 13**. Nobody chose these
gaps. They are the residue of hand-copying, and 209 test bodies is exactly how many it takes for the
gaps to become invisible.

### 2.2 The logical design already exists — in prose, and it was never given a structure

`NEW-APP-CHECKLIST.md` is a ~25-item list of what must be true of every app: `hasPendingAsync()` set
from enqueue to completion; `tlsYield`/`tlsResume` bracketing *every* HTTPS call site; `dbgGet`
registered with a minimum VE hook; `cmdTap` busy propagation; `init()` producing a complete first
paint; taskbar-cycle survival. **That is the contract.** It is executed by a human ticking boxes.

Exactly **one** of its items was ever automated: settings wiring, as `check_settings_wiring.py` —
which parses `struct AppSettings`, enumerates **58 fields**, asserts a three-part contract per field
(present in `load()`, present in `save()`, ≥1 consumer outside `settings/`), carries a documented
allowlist of 2, and runs as a `run/check` step.

**That file is the whole design, already working, at one-item scale.** Enumerate the domain from the
generated source of truth → assert a contract per element → allowlist the documented exceptions →
gate it. It has simply never been generalised past its own corner.

### 2.3 The shape: conformance matrices, generated — never hand-written per app

The domain here is unusually regular, and it is *already generated*:

- **Apps** — `appRegistry.h` is an X-macro; `app_ids_gen.py` emits `APP_ORDER`, `CONFIGURABLE`,
  `APP_SLOT`, `DISPLAY`. 13 apps, all implementing one `App` interface with documented defaults.
- **Settings** — one `AppSettings` struct, 58 fields, each with its domain written in the header
  comment (`1..10`, `0..255`, `0=km, 1=mi`, `30/60/120`). That is a schema with boundary values in it.
- **Debug keys** — `gen_get_keys.py` already statically enumerates all 68.

So:

```
Conformance matrix = (domain enumerated from a generated source)
                   × (contract rows)
                   → instances generated, not written
```

**App conformance** — ~6 contract rows × 13 apps. Five parameterised bodies replace ~30 hand-copied
ones, and the 27 empty cells in §2.1 become *failing or explicitly allowlisted*, never invisible.
Rows come straight off `NEW-APP-CHECKLIST.md`:

| Row | What must be true | Cheapest tier |
|---|---|---|
| `A1` switch round-trip | Spotify→app→Spotify, `appId` correct at each step | T3 |
| `A2` canvas-tap isolation | a canvas tap while app active does not hit Winamp zones | T3 |
| `A3` switch-back residue | Spotify repaints cleanly after switch-away | T3 |
| `A4` busy contract | `hasPendingAsync()` true from enqueue until completion | T3 (T2 after D0) |
| `A5` TLS bracket | every HTTPS call site brackets `tlsYield`/`tlsResume` | **T0 — static** |
| `A6` debug surface | app registers `dbgGet` + its minimum VE hook | **T0 — static** |
| `A7` first paint | `init()` produces a complete first paint | T3 |

Note A5/A6 fall to **T0 static** — no device, no build. Two of seven rows are free, and they are
exactly the two that today are human checkboxes on a checklist.

**Settings conformance** — 6 lifecycle rows × 58 fields:

| Row | What must be true | Tier | Status |
|---|---|---|---|
| `S1` wired | in `load()`, in `save()`, ≥1 external consumer | T0 | **already exists and is green** |
| `S2` default | missing key ⇒ documented default applied | T1 (after shim) | — |
| `S3` domain | out-of-domain value rejected/clamped per the header comment | T1 | — |
| `S4` reachable | the field has a UI row that changes it | T3 | — |
| `S5` persists | `set` → reboot → value survives | T3 | — |
| `S6` applies | the owning app observes the change | T3 | — |

Today ~12 settings tests exist against **58 fields × 6 rows**. The matrix does not say "write 348
tests" — it says *which cells matter*, makes the rest explicitly allowlisted, and generates the
instances from the struct rather than from memory. S2/S3 are pure host work and land on the T1 tier
the moment the shim exists.

### 2.4 What this changes about the rest of this document

1. **The runner split (§8 item 6) should not be one module per app.** That mirrors the app list —
   physical again. It should be *conformance* (generated, parameterised over the registry) versus
   *app-specific behaviour* (hand-written, genuinely unique: Stock's chart drill-down, WebRadio's
   station retry, PlaneRadar's interpolation). The first shrinks as it generalises; the second is the
   real content.
2. **It is the durable answer to "the app list order was hardcoded in the test suite."** A generated
   matrix cannot encode app order by hand, because it never types the list.
3. **It re-prices the tiers.** Two of seven app rows and two of six settings rows are T0/T1 — they do
   not compete for the single DUT. That materially eases OQ-D's ceiling.
4. **It gives the id-binding gate (§6) something to bind to.** A generated id (`A2/Aquarium`) has a
   registry row and a doc row by construction; the 56 orphans exist precisely because ids are typed.

**Recommendation: build the app conformance matrix first, on rows A5/A6 (T0, static, no device).**
It proves the generation pattern against `check_settings_wiring.py`'s working precedent, costs no DUT
time, and lands the Aquarium hole as a real failing cell on day one — which is the correct first
result, and the same shape as every other gate in this programme.



## 2b. The physical design: what the tiers actually are

A test architecture for *this* system has to answer one question honestly: **what can be known
without the device?** Everything else follows. Five tiers, ordered by cost per run, each with an
entry rule strict enough that things cannot drift upward into the expensive tier by default —
which is exactly how the project arrived at 100 % DUT testing.

| Tier | Runs on | Cost | Gate | What belongs here |
|---|---|---|---|---|
| **T0 — static** | host, no compile | ~1 s | every commit | grep/parse invariants over the source: `run/check-docs`, `check_settings_wiring`, registry staleness, `T_CC_01`/`T_CQ_03`-shaped rules, id binding (§6) |
| **T1 — unit** | host, compiled | seconds | every commit | pure functions over pure data: `util/mathUtil`, `asciiFold`, `textFit`, `timeFmt`, M3U parsing, playlist ordering, settings (de)serialisation, ICY/HTTP header parsing |
| **T2 — component** | host, compiled, mocked seams | seconds | every commit | one component against a faked collaborator: an app's tick/input state machine against a fake `dataTask` (IFC-001), playlist source against a fake FS |
| **T3 — functional** | **the DUT** | 30–90 min | before merge of behaviour change | anything touching `tft`, WiFi, I2S, SD, touch, FreeRTOS scheduling, or real Spotify — today's whole suite |
| **T4 — endurance** | the DUT, hours | hours | on demand / before a milestone close | `run/wr-soak`, `run/stress`, `run/pr-soak`, heap-fragmentation and drift behaviour |

**The entry rule, which is the whole design:** a test goes in the *lowest* tier that can falsify the
claim. A test may only sit in T3 if it names the physical dependency that forces it there. That one
sentence, enforced at review, is what stops T3 growing to 209 bodies again.

**What this project would gain, concretely.** Of the 209 T3 bodies, the ones asserting on parsing,
ordering, formatting, clamping and state-machine transitions do not need a device — they need the
device only because that is where the code is. That is a structural fact about `#include <Arduino.h>`,
not about the tests. Which brings us to why T1 is not free.

## 2c. Coverage against ADR-060's levels — the answer is *no*, and it is structural

ADR-060 D2a declares four levels. [M-LEVELS](M-LEVELS-dependency-audit.md) has now measured them.
Mapping the 224 executable ids onto that graph:

| Level | lines | share | tests addressing it **as a component** | how it is covered today |
|---|---:|---:|:--:|---|
| **L0** `util/ gen/ touch/ app.h` | 560 | 2 % | **0** | incidentally, through L3 app paths |
| **L1** `audio/ player/ winamp/ settings/ taskbar/ dataTask spotifyTask settingsStorage wifiDiag` | **15 289** | **52 %** | **0** | incidentally — heavily exercised, never addressed |
| **L2** `appShell logging screenLog debug/` | 3 559 | 12 % | **0** | it is the **entry door** for all 224 ids, never the subject |
| **L3** `apps/` + 6 app headers outside it | 9 067 | 31 % | ~all 224 | end-to-end |
| **L4** `main.cpp` (composition root) | 1 713 | 6 % | `T_BI_*` boot ids | end-to-end |

**Every executable test enters through the serial shell (L2) and asserts on app-observable state
(L3).** There is no other door. `dut.cmd("get …")`, `tap x y`, `injectTouch` — all of them are shell
commands, so no test can address an L1 component without traversing L2 and L3 first.

**Levels 0 and 1 are 15 849 lines — 54 % of the firmware — with zero tests that target them.** That
is not a coverage gap in the usual sense; those lines are *exercised* constantly. It is an
**addressability** gap: nothing can name them as a subject, so nothing can fail in a way that points
at them.

Three consequences worth stating plainly:

1. **A failure in L1 always surfaces as an L3 symptom.** The project's own record is full of the
   resulting misattribution — TASK-286 (a real `Audio.cpp` version-guard bug, originally blamed for
   TASK-285's crash and falsified only on DUT re-verify), TASK-442 (an arena shortfall that was
   actually a boot-time token refresh burning 43 KB). Both are L1 causes found through L3 symptoms,
   the long way round.
2. **The cause is C7, not the test suite.** You cannot address a component you cannot compile alone,
   and the firmware is effectively one translation unit
   ([M-CODEQUAL §12 C7](M-CODEQUAL-duplication-and-abstraction.md)). This is the third document to arrive at C7 from a
   different direction, and the sharpest statement of why it matters: **D0 is what makes level-aware
   testing possible at all.**
3. **The conformance matrices (§2) are level-aware where it is free.** Rows `A5` (TLS bracket) and
   `A6` (debug surface) are static/L0-addressable today. `S1` (settings wiring) already is, and is
   green. Those three are the only level-addressable assertions the project currently has, and all
   three are static — which is the honest shape of what is reachable before D0.

**This does not argue for building L1 tests now.** It argues that "coverage" figures for this project
must be read as *end-to-end coverage of L3 behaviour*, and should never be quoted as component
coverage — and that the levels, once gated (M-LEVELS §5), give the tier model something real to
attach to.

## 3. T1/T2 — the honest cost, and the one thing that makes it payable

VE's OQ1 caution is upheld and restated as the governing constraint:

> *"Don't let 'D0 makes unit tests possible' imply it makes them cheap — construction-order/global-state
> coupling (21 `g_` globals, 72 `extern`s) is the actual blocker, and D0 alone doesn't remove it."*

Re-verified against the tree: `player/m3u.h` includes `<Arduino.h>` and `<SD.h>`; `settingsStorage.h`
includes `<Arduino.h>`. Host-clean **today** — re-checked at the include level, and better than both the skeleton and OQ2
said: `util/mathUtil.{h,cpp}` (`<cmath>`), `util/asciiFold.h` (`<stddef.h>`, `<stdint.h>`) and
`util/textFit.h` (`<string.h>`) have **no Arduino dependency at all**. Three files are compilable on
the host today with zero shim. `util/timeFmt.h` is **not** a near-miss — it pulls `<Arduino.h>` *and*
`../settingsStorage.h`, so it lands behind the shim with `m3u` and friends.

So T1 has a precondition, and the precondition is **not** "finish D0". It is a **host shim**:

```
app/test/host/
  arduino_shim/     String, millis(), Serial, min/max, F() — ~200 lines, no behaviour
  fs_shim/          SD/File over std::filesystem — needed by m3u.h, fileBrowser.h
  main.cpp          the runner
```

**This is the single highest-leverage item in the whole document.** ~200–300 lines of shim converts
`m3u`, `settingsStorage`, `asciiFold`, `textFit`, `timeFmt` and the playlist-ordering logic from
DUT-forever into T1 candidates — without waiting for the component model, without touching a global.
It is bounded, it is verifiable (it either compiles or it does not), and it fails cheaply.

And because three files are already clean, **T1 can be proven with zero shim**: stand up the runner
against `mathUtil` + `asciiFold` + `textFit` first. That is a real tier, gated, in an afternoon — and
it makes the shim an *extension* of a working thing rather than a prerequisite for an unproven one.

**Recommendation: prove T1 on the three clean files, then build the shim as a spike (a day, timeboxed)
before committing to anything wider.**
If `m3u.h` compiles against it, T1 is real. If it drags in half of `app/src`, T1 is deferred until
after D0 and this document says so honestly instead of promising it.

**Framework choice for T1/T2: none, initially.** Not Unity, not GoogleTest, not PlatformIO's `test/`.
The precedent to generalise is already in-tree: `test_check_docs.py` — plain functions, a frozen
fixture directory, a golden file, an exit code, wired into `run/check`. A C++ T1 tier should look the
same: one `main.cpp`, `assert`-style helpers, ~50 lines of harness, `run/test-host`. Adopt a framework
only when the hand-rolled one demonstrably hurts. A test framework the team must learn is a tax paid
on day one against a benefit that arrives at test #200.

**T2 waits for D0 and is correctly *not* scheduled yet.** Do not pre-build mock infrastructure for
components that do not exist. `dataTask`/IFC-001 is the one seam ready today, and one seam does not
justify a mocking layer.

## 3b. The synchronisation model — why the suite is full of waits, and which ones a better harness deletes

Measured in the T3 suite:

| Kind | Count | Shape | Removable? |
|---|---:|---|---|
| **A — transport timeout** | **672+** (`timeout=3.0` ×454, `5.0` ×99, `2.0` ×76) | "how long may the shell take to answer" | **No.** Serial is a real channel. But it is *one policy*, currently retyped 672 times |
| **B — condition poll** | ~40 loops | `while deadline: cmd("get X"); sleep(2.0)` | **Yes, entirely** |
| **C — settling sleep** | **252** (`sleep(0.3)` ×63, `0.5` ×38, `0.2` ×32 …) | "give the device a moment after a tap" | **Yes, nearly all** |

Against **2** named sleep constants and 42 module-level constants in a 10 229-line file. Every one of
those 924 numbers is a guess calibrated on one device, one network, one day.

### 3b.1 They are not robust, and the project has the scars to prove it

This is not a theoretical concern — it is the single most expensive recurring failure mode in the
project's own record:

- `DUT_WIFI_WAIT` exists as an environment knob because 25 s was not enough on a bad WiFi day.
  `DUT_WIFI_WAIT_2` was added (TASK-434) because the first extension still raced the firmware's own
  60 s supervisor kick — **a harness constant tuned against a firmware constant, by hand, twice.**
- `T_AE_04` was "INCONCLUSIVE, maybe an accumulation bug" for an entire session. It was an 8 s harness
  wait racing a 10 s connect timeout in `Audio.cpp`. The lesson was recorded as *derive test bounds
  from firmware constants* — good advice that only works if a human remembers to apply it 924 times.
- **`T_WX_04` is the reductio.** It asserts `weatherReady == false` "immediately" after switch-in, and
  carries `skip("network too fast?")` for when it is not. **A test a fast network can defeat is
  sampling a window it does not control, not asserting an invariant.**

There is also a measurement error nobody accounts for: a condition loop polling every 2 s inside a
30 s bound reports latency at **±2 s granularity**. `T_WX_05` cannot tell 1 s from 3 s, so it can
never detect a 2× fetch-latency regression.

### 3b.2 The root cause: the harness polls a device that is already an event source

The device streams events continuously — `[spotify.poll] ok 200`, `[wifi-ev] STA_GOT_IP`,
`[boot]`. And **the harness already knows how to consume them**: `Dut._wait_for_ready()` blocks on the
stream watching for exactly those lines. It is the most reliable component in the whole harness.

But the `get`/`set` shell is strictly request/response — ask now, answer now — and there is no
*"tell me when"* primitive. So a test that wants "wait until weatherReady" has only one tool
available: ask repeatedly and sleep between asks. **The event-driven pattern was proven in the
harness's own constructor and never made available to a single test body.**

### 3b.3 The four primitives that delete B and C

Ordered — each depends on the one before.

1. **Correlated commands** (precondition for everything else). Every command carries a sequence id;
   every reply echoes it. Today replies are matched *positionally*, which is why the code carries this
   warning: *"Serial stream is NOT thread-safe … ACKs will be silently consumed, causing timeouts."*
   That hazard is a direct consequence of positional matching, and it is also what makes async event
   lines unsafe to add today — a pushed event would land mid-reply and corrupt the parse.
   **Nothing else in this section is safe to build before this.**

2. **Completion semantics — deletes most of C.** `injectTouch` acknowledges after the tap has been
   *dispatched*, not when the bytes arrived. The 63 `sleep(0.3)` calls that follow taps exist purely
   because the current ack means "received", and the test has no way to learn "handled".

3. **A quiescence predicate — deletes the rest of C, and is nearly free.** The firmware **already
   tracks every input**: `g_shellBusy`, `App::hasPendingAsync()`, `App::isConnecting()`, the dataTask
   queue depth. Not one of them is aggregated. A single `get idle` that ANDs them converts *"sleep 0.3
   and hope"* into *"block until quiet, fail at deadline"* — the state exists, it has never been
   exposed as one answer.

4. **Watch / subscribe — deletes B.** `watch weatherReady` → the device emits one line the moment it
   changes. The 30 s bound stops being a sampling budget and becomes a genuine **failure bound**:
   assert it happened within 30 s, and report *when* it actually happened, exactly. Latency
   measurement goes from ±2 s to real, which is what makes a latency regression detectable at all.

   **Scope discipline:** do not build `watch` for all 68 debug keys. Build it for the ~10 that the
   existing condition loops actually target — that list is derivable mechanically from the loops
   themselves, and it should be, not guessed.

### 3b.4 What stays, and why that is the point

Physical waits are irreducible and must remain: boot, WiFi association, TLS handshake, the DRD reset
gap, a firmware connect timeout. **The change is what they mean.** Today a wait is a *sampling
budget* — poll until this expires, then give up. After (3) and (4) it is a *failure bound* — the
event either arrives inside it or the test fails with the real elapsed time attached. Only the second
can be a test result; the first is a coin toss with a deadline.

Class A stays too, but collapses to **one policy in `lib/dut.py`** rather than 672 literals: a default,
one override for known-slow operations, and — because the transport latency is measurable — a p99
sampled once at session start rather than assumed forever.

### 3b.5 Second-order: this is also the throughput fix

252 sleeps at a ~0.4 s mean is **~100 s of pure sleeping per full run**, before counting the
overshoot every condition loop adds by construction (on average half its poll interval, every time).
Against OQ-D's hard ceiling — 224 ids serialised on a single DUT, 30–90 minutes — event-driven
synchronisation is the only lever that shortens the run without removing coverage.

### 3b.6 Honest costs

- **This is firmware work**, on the debug build, and the debug build is the memory-constrained one
  (`.dram0.bss` overflow precedent). Price items 3 and 4 against OQ-B before committing.
- **Item 1 is a breaking change to the wire format** and touches all 16 `Dut` importers. It should
  land *with* the `lib/dut.py` extraction (§8 item 1), not after it — the extraction is already
  touching every one of those call sites.
- **Item 3 is the cheap one and should be tried first.** One new `get` key, no protocol change, no
  async lines, and it is testable against the existing suite by replacing settling sleeps a few at a
  time and watching for new failures. If `get idle` alone removes a meaningful share of the 252
  sleeps, items 1/2/4 have an evidence base. If it does not, that is worth learning for one day's work.

## 4. Debug and instrumentation infrastructure — the part the skeleton omitted entirely

The skeleton has nothing about instrumentation, and it is the most mature asset in the project.

`app/src/debug/serialConsole/` is **2 615 lines across 6 files** (`cmdGet` 622, `cmdSet` 739, `cmdSd`
786, `cmdTouch` 251, `cmdMisc` 172, `cmdSystem` 45), `SERIAL_DEBUG`-only, emitting one-line JSON
(`{"ok":true,"cmd":"get","var":"wifi",…,"last":true}`). It is not a debug aid that tests happen to
use. **It is the test API** — the entire T3 tier is a client of it, and it is the reason DUT tests
are writable at all.

Architecturally it should be named as such, with the obligations that follow:

- **I1 — the console is a contract, not a debug aid.** BP-024 ("field set VE-gated; extend, don't
  rename") already says this in a comment on one command. It should be a stated property of the
  surface: every `get` reply is a versioned, additive-only JSON object. Renaming a field breaks tests
  silently, months later, on hardware.
- **I2 — the client should be generated, not hand-written.** `gen_get_keys.py` already statically
  parses `cmdGet.h`'s `strcmp` chain **and** the per-app `dbgGet()` chains, precisely so the key list
  "cannot drift from firmware". That is the LL-114 parse-don't-mirror fix, already built, and it is
  used by exactly one test (`T_488_10`). Generalising it into a typed accessor for the DUT library
  (`dut.get("wifi").rssi`) would delete a large slice of the ~71 hand-rolled helpers and make a
  renamed field a **host-side, T0, one-second failure** instead of a DUT mystery.
- **I3 — production must not be able to depend on it.** Already true by construction (the headers are
  included inside `#ifdef SERIAL_DEBUG`). Worth stating so it stays true.
- **I4 — the debug surface is part of every component's interface.** ADR-060 D0 components should
  declare their `dbgGet`/`dbgSet` keys alongside their public API. A component with no debug surface
  is a component that can only be tested end-to-end — which is how things arrive in T3 and stay there.
  `T_SRC_xx`'s "debug-surface parity" check already assumes this; D0 should make it explicit.

**The gap worth filling:** there is no injection/fault surface to match the observation surface.
`set queue N`, `prInjectAircraft` and `set aePlayFile` exist as one-off injectors, each invented for
one task. A systematic `set fault <subsystem> <mode>` (drop the next TLS handshake, return a short
read, fail the next allocation) would move a class of tests that today can only be observed during a
multi-hour soak into deterministic, minutes-long ones. That is a proposal, not a decision — it costs
firmware bytes on the debug build only, and it should be priced before it is promised.

## 5. Code reuse — the layering, corrected

M-TOOLING §3's target layout is right in shape. Two corrections from §1:

```
app/tools/lib/
  dut.py       ← EXTRACT from run_serialdbg_tests.py (16 importers, incl. private names)
               ← ADD resolve_port(): shell out to run/port, kill 19 hardcoded defaults
               ← ADD generated typed accessors from gen_get_keys.py (§4 I2)
  report.py    ← today's ve_suite_base (pass_/fail/skip/flake + runner)
  layout.py    ← today's shell_layout
  coords.py    ← unchanged
  preview.py   ← today's preview_common
```

**`report.py` and `dut.py` must not depend on each other.** Today `ve_suite_base` type-imports `Dut`
from the suite it is supposed to serve — reporting has no business knowing what a DUT is. Cutting
that is a two-line change and it is the difference between a library and a knot.

**The dependency rule stands** (levels depend downward; `lib/` never imports a suite), and it is what
makes the T3 split safe. It is also the rule the current tree violates in exactly one place — the one
that matters.

## 6. Id binding — promote OQ3 from question to decision

The measured drift (95 doc ids with no code; 56 code ids with no doc; 5 with no doc anywhere) is not
a documentation-hygiene problem. It means **neither artefact can answer "what is our coverage?"** —
`test_plan.md` overstates it by 95 and understates it by 56 simultaneously.

The mechanism already exists. `run/check-docs` (TASK-475, gate 12) is a host-side, seconds-long,
already-wired gate, and `run/check --docs-only` exists specifically so doc-only commits still run it.
Proposed check, in its spirit:

1. Every id in a `test_plan.md` / `regression_suite/` table row is in exactly one of three states,
   **declared in the row**: `automated` (a registry entry exists → the gate asserts it), `manual`
   (a human runs it → the gate asserts a procedure link), `planned` (neither → the gate asserts an
   owning task id).
2. Every registry id resolves to a doc row. The 5 orphans (`T_PLE_WR_156..160`) fail immediately.
3. Coverage counts are **generated** from that binding, never hand-maintained.

Rule 2 will fail on 56 ids the day it lands. That is the correct first result — the same shape as
M-TOOLING §4's spike rule failing on all six spikes, and the same shape as TASK-475's own gate
rejecting its own spec. Land it with those 56 grandfathered on an explicit, dated, task-owned list;
an exception list that shrinks is a gate, an exception list that is invisible is a fiction.

**On OQ4 (does the runner split mirror the VE taxonomy?): yes, and rule 2 makes it structural.** If
every registry id must resolve to a doc row, then the family a test lives in is the family the doc
gives it, and a second taxonomy cannot form without failing the gate. The lean was right; this is the
mechanism that makes it stick.

## 7. Flake policy — promote OQ5 to a decision too

`ve_suite_base` has a `flake()` state and ADR-059 D13 requires a pre-declared flaky set. Neither says
what a flake *entitles* you to. Proposed, minimal:

- **A flake must be declared before the run, with an id and a reason.** Calling `flake()` for a test
  not on the list is a **FAIL**. Undeclared flake is the whole problem — a red test that is talked
  about rather than recorded.
- **A declared flake is retried once, and both outcomes are reported.** `PASS(1 retry)` is not `PASS`.
- **Every flake carries an owning task and a review date.** No date, no flake status.
- **A flake blocks a behaviour-neutrality baseline** (ADR-059 D13) unless it was declared *before*
  the first baseline run. Otherwise the baseline can absorb the regression it exists to detect.

The existing watchlist memory (`T169` yahoo/network, `T_PR_05` `[NETWORK]`, `T_WR_TLS_01` residual)
is the seed list, and it already carries reasons — it just lives outside the harness.


## 8. Staging — superseded; see M-TESTBASE phase 1

**Priority is set by [M-TESTBASE phase 1](M-TESTBASE-phase1-player-gate.md)**, which scopes the first
tranche to the 3-mode player and funds four items: `lib/dut.py` (P1), `get player` (P2), the 9×7
mode-transition matrix (P3), `get idle` (P4). That document is the schedule; this one is the reasoning
behind it.

Everything else this document argues for is **deferred, deliberately**, and recorded here so it is not
re-derived: id-binding gate (§6), flake policy (§7), T1 on the three clean `util/` files (§3), the
Arduino/FS shim spike (§3), generated console accessors (§4 I2), correlated commands + `watch`
(§3b.3 items 1/2/4 — gated on P4 producing evidence), the runner split (TASK-480, **after** P1 not
before), the directory move (TASK-481).

Two items remain **do-not**, on measurement rather than taste: a C++ test framework (generalise
`test_check_docs.py` instead) and T2 mock infrastructure (nothing to mock until D0).

## 9. Do not lose

**The verification paradox: the regression suite cannot verify a refactor of itself.** TASK-480 needs
≥3 baseline runs before it lands. Two things sharpen this since the skeleton wrote it down:

- The baseline must be taken with the **flaky set pre-declared** (§7), or the baseline absorbs the
  regression it exists to detect. That baseline **was never taken** for the two M-SRCLAYOUT stages
  that already landed (`78caa95`, `b36f184`) — see TASK-488, and note that TASK-488 closed by
  comparing *compiled binaries*, which is a stronger check than a suite run and should be the first
  tool reached for on any "pure move" claim.
- **Items 1–5 above are all outside the paradox.** They are host-side, gated, and cheap to verify.
  Sequencing them ahead of the split is not just risk management — it is the only part of this
  programme that can be verified at all without spending an hour of DUT time per attempt.

## 10. Still genuinely open

- **OQ-A — is the T1 tier real?** Blocked on the §3 shim spike. Do not schedule T1 work before it.
- **OQ-B — what is the `set fault` surface worth in firmware bytes?** The debug build has repeatedly
  been the constrained one (`.dram0.bss` overflow precedent). Price before promising.
- **OQ-C — does the console JSON need an explicit schema version?** I1 says additive-only, which
  works until it does not. A `get schema` returning a version would let the DUT library refuse a
  mismatched firmware instead of timing out. Cheap; unproven need.
- **OQ-D — 224 executable ids on one device is a serialisation limit.** A full run is 30–90 minutes
  and cannot parallelise across a single DUT. That is a hard ceiling on T3, and it is the strongest
  argument for T0/T1 that this document has — but a second DUT is a real alternative and has never
  been costed.
