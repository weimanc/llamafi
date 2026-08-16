# Design — M-CODEQUAL: duplication, abstraction and constant-ownership cleanups

> Owner: Architect
> Status: **proposed** — 2026-08-15
> Date: 2026-08-15
> Companion to: [M-SRCLAYOUT-main-decomposition.md](M-SRCLAYOUT-main-decomposition.md)
> Tracked-as: TASK-458 … TASK-463
> Registers: no new `feature_inventory.yaml` id — structural.
> Extends: **LL-114** (host tools mirror firmware truth by copy) — §6 closes the hole TASK-335
> could not reach.

> **Line references updated 2026-08-16.** M-SRCLAYOUT Stages A/B (`78caa95`, `b36f184`) moved the
> debug console out of `main.cpp`, so every `main.cpp:NNNN` citation in the first draft of this
> document was invalidated within a day of writing it. This is TASK-464's cost arriving early, and a
> live argument for citing *symbols* rather than line numbers in design docs — the symbol names below
> survived the move; the numbers did not.

**Relationship to M-SRCLAYOUT — read this first.** M-SRCLAYOUT's Stages A/B are contracted as *pure
moves*: `git diff -M` ≥95 % rename similarity, zero behavioural hunks. **Nothing in this document may
be folded into those commits.** A move that also cleans up is a move that cannot be reviewed as a
move, and this project has already written that rule down twice (ADR-059 D2; the `T_AE_05` review
gate). These are separate tasks, landing separately, on their own gates.

---

## 1. Scope

Six findings from a code-quality pass over `app/src` (30 022 lines) and `app/tools`. Each is
independently landable. Ranked by value-to-risk in §9.

| id | Finding | Kind |
|---|---|---|
| **C1** | Nine `fetch*()` functions share a ~30-line skeleton | duplication |
| **C2** | Paired acquire/release managed by hand across exit paths | abstraction (RAII) |
| **C3** | `cmdGet`/`cmdSet` — 1 308 lines of flat `strcmp` chains | abstraction (table dispatch) |
| **C4** | The debug/production seam has no stated convention | policy |
| **C5** | Canvas + Winamp-window geometry: **six names, three layers, no single source** | duplication / magic numbers |
| **C6** | No shared UI palette | magic numbers |
| **C7** | The firmware is effectively one translation unit | physical design |
| **C8** | The memory-ownership policy is coherent but unwritten | policy |
| **C9** | No type suppresses copying (`= delete` appears zero times) | type hygiene |

> **C7–C9 and §12–§13 added on review, 2026-08-16.** Re-measurement upheld C1–C6 unchanged; nothing
> had landed (TASK-458 OPEN, C5's `T_CQ_03` grep red at 123 hits, C6 at 22 sites across 9 files).
> These sections were briefly a separate `M-CODEQUAL-review.md`; folded back in because every other
> `-review.md` in this directory is **cross-role** (DEV/VE/QM/PM reviewing the Architect), and an
> Architect reviewing an Architect document is an amendment, not a review.

## 2. C1 — the nine-fetch skeleton

`dataTaskStorage.cpp` defines `fetchWeather` (`:248`), `fetchCrypto` (`:314`), `fetchStockQuote`
(`:390`), `fetchStockChart` (`:583`), `fetchTeletext` (`:617`), `fetchHeatmapQuote` (`:895`),
`fetchStockChartBySym` (`:986`), `fetchPlaneRadar` (`:1313`), `fetchGeocode` (`:1456`),
`fetchWebRadioStations` (`:1518`). Every one runs the same sequence:

```
tlsYield → LOG_HEAP → WiFiClientSecure → setCACert(consumeCertBreak(TAG) ? wrongCaFor(TAG) : ROOT_CA)
→ HTTPClient → useHTTP10(true) → begin() [+ error path + tlsResume + return] → phase = 1
→ t0 = millis() → certSentinel(http.GET()) → elapsed log → getString() → http.end() → LOG_HEAP
→ phase = 2 → parse → mux-guarded result store → phase = -1 → tlsResume
```

Three things vary: **the URL, the root CA, and the parse body.** Everything else is copied ~9 times —
roughly 200 lines of repetition, and it is *load-bearing* repetition: the phase tracking, the
`tlsResume`-on-every-exit-path rule, the HTTP/1.0-forces-close trick and the `certSentinel` wrapper
are all correctness-critical, and each is independently re-typed per fetch.

> **CORRECTED — @Developer review, 2026-08-16 (finding 2). The claim above is wrong: these are two
> skeletons, not one, and there is a live behavioural divergence inside them.**
>
> **Two I/O strategies, not one.** *Buffered* — `fetchWeather`, `fetchCrypto`, `fetchTeletext`,
> `fetchGeocode` — `http.getString()` into a `String`, `http.end()`, *then* parse. *Streaming* —
> `fetchStockQuote` (`:437`), `fetchStockChartWithRetry` (`:511`), `fetchHeatmapQuote` (`:947`),
> `fetchStockChartBySym` (`:1049`), `fetchPlaneRadar` (`:1228`, plus a bespoke `prParseStream()` that
> is not even `deserializeJson`) — parse directly off `http.getStream()` under a
> `DeserializationOption::Filter`, so `http.end()` runs *after* the parse. The skeleton written above
> describes only the buffered half. One fixed-order wrapper cannot serve both without dropping the
> streaming `Filter` for five endpoints — a real heap regression, since those filters are load-bearing
> for headroom.
>
> **And a genuine correctness divergence, verified in source.** `fetchWeather` resumes **after** its
> parse (`:311`, parse at `:289-309`). `fetchCrypto` resumes **before** its parse (`:360`, parse at
> `:362-386`) — while `:262-265` claims in a comment that weather *"matches crypto below"*. It does
> not. **A `TlsYieldGuard` scoped to end-of-function would silently move crypto's resume to after its
> parse**, changing when the Spotify task may reconnect and re-take heap mid-parse. That is a
> behaviour change a refactor must not make by accident. **Filed as TASK-495 — decide which timing is
> correct first; do not let tooling pick.**
>
> `fetchWebRadioStations` (`:1518-1636`) is a `fetch*()` in the same file but is **out of C1's scope**
> — multi-mirror retry loop with an abort window, no single GET, nothing like either skeleton.

**Design (revised).** **Scope C1 v1 to the four buffered fetches only.** A `httpFetchJsonBuffered()`
taking `{url, rootCa, certTag, phaseSlot}` plus a parse callback; the five streaming fetches get their
own consolidation later, or none. Do it **after C2 and after TASK-495** — the guards remove the
exit-path bookkeeping, and TASK-495 settles the resume timing that a guard would otherwise decide
silently.

**Constraint.** `-std=gnu++11` — the parse callback is a template parameter or a plain function
pointer, not `std::function` (heap allocation on a memory-constrained device).

## 3. C2 — RAII scope guards

**This is the highest-value item in the document, because it fixes a bug class with a proven
production instance.**

Measured across `app/src`, excluding comments and counting only real call sites:

| Pair | Acquires | Releases | Reading |
|---|---:|---:|---|
| `tlsYield()` / `tlsResume()` | 12 | **24** | one acquire per fetch, one release per exit path |
| `http.begin` / `http.end` | 8 | **15** | all in `dataTaskStorage.cpp`; ~2 exit paths per fetch |
| `mb_arena_acquire` / `mb_arena_release` | 4 | **7** | 2/5 in production (`debug/serialConsole/cmdSet.h:211/217` and `:335/…` are balanced debug-command pairs) |
| `xSemaphoreTake` / `xSemaphoreGive` | 17 | 19 | — |
| `portENTER_CRITICAL_SAFE` / `portEXIT_CRITICAL_SAFE` | 59 | 59 | balanced |

> **Counting note.** These are real call sites — comment lines stripped, `(` required. A naive
> `grep -c` of the bare names inflates every row: it picks up declarations, the stats accessors
> (`mb_arena_acquire_total` etc.), and the `#else` no-op inlines in `mb_arena.h:70-71`. An earlier
> pass of this analysis reported `mb_arena` as **13/8** and `http` as **25/22** from exactly that
> mistake. Anyone re-deriving these numbers must filter, or they will "find" leaks that are not there.

**None of the asymmetric rows is a leak.** All three resolve to the same shape as the headline
finding: **one acquire, many exit paths, each releasing by hand.** `mb_arena_acquire()` is
documented idempotent at both call sites (`webRadioApp.h:1727`, `audioEngine.h:711` — *"idempotent;
on FAIL → libc fallback"*), so it is a latch rather than a refcount and multiple releases are the
expected shape. That is the argument for C2, not against it: the imbalance is *by design*, and the
design is the thing that keeps costing bugs.

Correctness therefore depends on a human enumerating every `return`. The code says so out loud at
`dataTaskStorage.cpp:277` — `spotifyTask::tlsResume();  // BP-031: every exit path`.

**The discipline has already failed in production.** `dataTaskStorage.cpp:264-267`:

> *"BP-031: yield Spotify's TLS before our own handshake … **Was previously omitted here despite
> BP-031 citing weather as conforming** — fixed 2026-06-21 (TASK-222)."*

A best practice that a reviewer certified as conforming, while it was not. That is exactly the
failure mode RAII removes by construction rather than by vigilance.

**Design (C++11-clean):**

```cpp
// A guard that releases on every exit path, including exceptions-off early returns.
class TlsYieldGuard {
public:
    TlsYieldGuard()  { spotifyTask::tlsYield(); ok_ = true; }
    ~TlsYieldGuard() { if (ok_) spotifyTask::tlsResume(); }
    TlsYieldGuard(const TlsYieldGuard&) = delete;
    TlsYieldGuard& operator=(const TlsYieldGuard&) = delete;
private:
    bool ok_;
};
```

with a `tryFor(ms)` factory covering `tlsTryYield()`'s contract (`spotifyTask.h:180-193`: on `false`
the caller must **not** resume — the guard encodes that as `ok_ = false`, which is strictly safer
than the current comment-enforced rule).

**C2b — `audio/audioEngine.h` already hand-rolls this, with a bool.** `s_aeSpotifyYielded` is
declared at `:132`, set at `:700`, and checked-and-cleared at `:165`, `:730` and `:771` — three
release sites, in three different functions, none of which performed the acquire. The comment at
`:726` states the intent plainly:

> *"…which also leaves it held; `aeTeardownFile()` on mode exit is what releases it."*

A lock deliberately held across function boundaries, tracked by a manual flag. This is a scope guard
someone wrote by hand because the vocabulary was not available. Migrating it is the clearest possible
demonstration of C2's value — but note it is a **deliberate** cross-scope hold, so it needs a
*transferable* guard (move-style release), not a plain stack guard. Treat as its own task.

## 4. C3 — table-driven debug dispatch

`cmdGet` is 616 lines / 40 `strcmp` branches (`debug/serialConsole/cmdGet.h:7`). `cmdSet` is 733
lines / 28 branches (`debug/serialConsole/cmdSet.h:7`). **1 308 lines to dispatch 68 keys.**

The table-driven pattern **already exists alongside them**: `kCmds[]` at `main.cpp:1335` dispatches
the command *verbs* through a `{name, handler}` table, and every app implements `dbgGet`/`dbgSet`. Only
the shell-level variable dispatch never adopted either.

**Design.** A `{name, getter, setter, help}` table, sectioned per subsystem. Three follow-on wins:

1. `cmdHelp` (`debug/serialConsole/cmdSystem.h:35`) enumerates the table instead of hardcoding text — it cannot go stale.
2. The debug surface becomes *introspectable*, which is what `run_serialdbg_tests.py` wants.
3. `T_SRC_07`'s "every registered key still resolves" becomes a loop over the table rather than a
   hand-written list.

Debug-only code, so a defect here cannot ship. Low risk, high readability payoff.

## 5. C4 — the debug/production seam

There is no written convention, so three mechanisms coexist: `#ifdef SERIAL_DEBUG` (the bulk),
`#ifdef SD_BOOT_MOUNT` (production-safe subset, correctly separated and explained at
`main.cpp:1486`), and `#ifdef MEMBUDGET_PHASE1`. The separation is *reasoned* — `main.cpp:675`
documents why the SD boot mount is gated on `SD_BOOT_MOUNT` rather than `SERIAL_DEBUG` — but it is
reasoned per-site, not by policy.

**Design — adopt the compile-out-behind-a-stable-interface convention (§ "Debug code" below), and
state it once:**

1. **Production code never contains `#ifdef` for debug.** It calls a normally-named function.
2. The *implementation* is compiled out; the *interface* is not. A no-op inline is the release build.
3. Debug hooks live in `debug/`, never inline in the subsystem they observe.
4. Per-app introspection stays behind the existing `dbgGet`/`dbgSet` virtuals — that contract already
   does this correctly and is the model to generalise.
5. Diagnostics that are *production-safe and production-valuable* (the SD boot mount, `wifiDiag`)
   get their own feature gate and are **not** lumped under `SERIAL_DEBUG`. This is already the de
   facto rule; C4 writes it down.

Rationale: today `main.cpp` is ~47 % `SERIAL_DEBUG` body, which means reading the production boot
path requires skipping 2 780 lines that never ship. M-SRCLAYOUT Stage B relocates that bulk; C4 stops
it re-accumulating.

## 6. C5 — one canonical set of canvas and Winamp-window constants

**The most cross-cutting finding, spanning firmware, the skin bake, and every host preview tool.**

The number `275` currently exists under **six names across three layers**:

| Layer | Name | Site | Source |
|---|---|---|---|
| generated | `TASKBAR_X` | `gen/shell_layout.h:6` | `preview_layout.py` |
| generated | `WINDOW_W`, `SKIN_MAIN_BG_W` | `gen/skin_layout.h` | `bake_skin.py` (from the `.wsz`) |
| firmware | `S_CANVAS_W` | `settings/settingsSection.h:29` | hand-typed |
| firmware | `KB_CANVAS_W` | `settings/keyboardWidget.h:21` | hand-typed |
| firmware | `AQ_CANVAS_W` | `aquarium/aquariumApp.h:190` | hand-typed |
| firmware | raw `275` | `touchDebugOverlay.h:36`, `calibrationFlow.h:376`, `pleditView.h:173` | literal |
| host | `APP_W` | `tools/preview_common.py:18` | hand-typed |
| host | `CANVAS_W` | `tools/_clock_nixie.py:47`, `_clock_flip.py:59` | hand-typed |
| host | raw `275` | `_clock_nixie.py:82,384`, `clock_delta_smoke.py:48` | literal |
| host | `SCREEN_W = 320` | `preview_common.py:16`, `audit_origin.py:33`, `coords.py:29` | hand-typed |

### 6.1 The subtlety — this is two constants that happen to share a value

- The **Winamp window** is 275 px wide *because the base-2.91 skin is*. It comes out of the `.wsz`
  via `bake_skin.py`.
- The **app canvas** is 275 px wide *because the taskbar starts at x=275*. It comes out of
  `shell_layout.h`.

These are independent facts. **Do not collapse them into one constant** — that couples the skin
format to the shell layout and makes a future skin of a different width unrepresentable. The correct
shape is *one source of truth per concept*, plus a `static_assert` recording that they currently
coincide:

```c
// gen/shell_layout.h  (generated)
#define APP_CANVAS_W  TASKBAR_X        // canvas ends where the taskbar begins
#define APP_CANVAS_H  240
#define SCREEN_W      320
#define SCREEN_H      240

// firmware, one place
static_assert(APP_CANVAS_W == WINDOW_W,
              "skin window and app canvas have diverged — intentional? see M-CODEQUAL C5");
```

`S_CANVAS_W`, `KB_CANVAS_W`, `AQ_CANVAS_W` and every raw literal then become `APP_CANVAS_W`.

### 6.2 The host half — closing LL-114's remaining hole

The right mechanism **already exists**: `tools/shell_layout.py` is a shared parser, and
`preview_common.py:12` carries the rule — *"geometry — PARSED from `gen/shell_layout.h`, never
mirrored (LL-114)"*. TASK-335 fixed the taskbar mirrors after LL-114.

But the fix could not be complete, and the file says why. `preview_common.py:16`:

```python
SCREEN_W  = 320   # hardware, not in shell_layout.h
SCREEN_H  = 240
APP_W     = 275
APP_H     = 240
```

**The canvas and screen dimensions are not in any generated header, so even the disciplined tool must
mirror them.** That is not a lapse — it is a missing emission. §6.1 supplies it, and this is the
change that lets `preview_common.py` delete its last four hardcoded constants.

Three further gaps in the same class:

- **Tools that bypass the shared parser entirely**: `_clock_nixie.py:47,82,384`, `_clock_flip.py:59`,
  `audit_origin.py:33`, `clock_delta_smoke.py:48`. They must import `shell_layout.py`.
- **A second, ad-hoc parser.** `coords.py:33-46` parses `vuMeter.h`'s `constexpr int`s with its own
  `_parse_cpp_constexpr_int()` because the VIS constants are in neither generated header. Either emit
  them into `shell_layout.h`, or fold the second parser into `shell_layout.py`. Two parsing
  mechanisms is one too many.
- **A known-open TODO.** `coords.py:31` — `ORIGIN_X = 0  # M-SHELL-LAYOUT will drive this from
  shell_layout.h`. Close it or delete it.
- **`prloc_manual_smoke.py:32`** re-derives `S_CONTENT_H = 212` with a comment pointing at the C
  header — a mirror bound by a comment, the exact LL-114 pattern.

### 6.3 Why this matters more than it looks

Per LL-114's own root-cause note: *"host tools have no gate — they're only exercised when a human
reaches for them, which is exactly when they must not lie."* A drifted preview does not fail a build;
it silently shows the wrong picture at the moment a human is making a visual decision on it. And
`preview_layout.py --export` **writes** `shell_layout.h`, so a drifted host mirror is a *write-path*
regression into the firmware's generated source.

**Verification obligation**: after C5, `grep -rnE '\b(275|320)\b' app/tools/ app/src/` returns only
generated headers and genuine data tables. That grep is the acceptance test.

## 7. C6 — shared UI palette

Named colours exist per-file (`CAL_*_COLOR` at `calibrationFlow.h:144-156`, `TASKBAR_*_COLOR` at
`taskbar.h:14-20`) but there is no shared palette, so the same values recur under different names or
none: `0x4208` appears 15× (as `CAL_SEP_COLOR`, as `TASKBAR_SEP_COLOR`, and raw at
`touchDebugOverlay.h:36`); `0x2104` likewise as background.

**Design.** A `ui/palette.h` holding the ~10 genuinely shared UI colours. App-specific colours stay
local — this is not an invitation to centralise every colour in the firmware.

## 8. Explicitly out of scope

Recording these so nobody "fixes" them later on the strength of a naive metric.

- **`webRadioApp.h:392` `tick()` — 399 lines, 33 branches.** The worst function in the app layer by
  raw measure, and a state machine written as flat sequential blocks. It also carries interleaved
  fixes from TASK-218, 220, 234, 263, 266, 291, 398, 402 and 405. Refactoring value is real; the
  regression risk is higher, and there is no forcing reason. **Leave it.**
- **`clockApp.h:19-28`** — the 45× `0x0603` / 37× `0x0007` literals that dominate a hex scan are
  **nixie glyph bitmap data**. Naming them would be actively worse.
- **`settings/cities.h`** (363 numeric literals) — a **data table**, not magic numbers.
- **`std::array`** — raw fixed arrays are the right call on this target; predictable layout,
  `mem_manifest.yaml` accounts for them.

Any lint rule adopted from this document must exclude generated files and data tables, or it will
rank the three items above at the top and the real findings below them.

## 9. Tasks and sequencing

| Task | Item | Depends on | Risk | Gate |
|---|---|---|---|---|
| **TASK-458** | C2 — `TlsYieldGuard` + `HttpSession` guards | — | low | `run/check`; `T_CQ_01` |
| **TASK-459** | C2b — migrate `s_aeSpotifyYielded` to a transferable guard | 456 | **medium** | `run/check`; `wr-soak` ≥30 min |
| **TASK-460** | C1 — consolidate the nine fetch functions | 456 | medium | `run/check`; `T_CQ_02`; cert preflight |
| **TASK-461** | C5 — canonical canvas/window constants, firmware + bake + tools | — | low | `T_CQ_03`; golden re-bake |
| **TASK-462** | C3 — table-driven `cmdGet`/`cmdSet` | M-SRCLAYOUT B | low | `T_CQ_04` |
| **TASK-463** | C4 policy + C6 palette | — | low | `run/check` |

TASK-458 and TASK-461 are independent of M-SRCLAYOUT and of each other — either can start
immediately. **TASK-459 is the one to be careful with**: it touches the audio engine's teardown
ordering, which `T_AE_04` exists to protect.

## 10. Test & validation

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_CQ_01` | No yield/resume imbalance after C2 | DUT — `get dataq`, `tlsYieldCount()` across 20 fetch cycles per app | count returns to 0 between fetches; never strands > 1 |
| `T_CQ_02` | Fetch consolidation is behaviour-neutral | DUT — every app's fetch path + `run/check-datatask-certs` + `T_WR_TLS_01` | all endpoints resolve; cert-break injection (`consumeCertBreak`) still fires per-tag |
| `T_CQ_03` | One source of truth for geometry | host — `grep -rnE '\b(275\|320)\b' app/tools/ app/src/` | hits only in generated headers and data tables |
| `T_CQ_04` | Debug surface unchanged after C3 | host — `run_serialdbg_tests.py` over every registered key | every key resolves identically; `cmdHelp` output derives from the table |
| `T_CQ_05` | Bake determinism preserved | host — `run/bake-skin` then `sha256sum -c app/gen/golden.sha256` | byte-identical (T025) |
| `T_CQ_06` | No memory regression | host — `run/build-debug` + `.map` | `dram0_0_seg` headroom re-derived fresh per task, recorded |

`T_CQ_05` matters because C5 changes what the bake emits. Re-baking must stay deterministic or the
`golden.sha256` gate becomes noise.

## 11. Exit criteria

1. No manual `tlsResume()` on an exit path anywhere in `app/src`; every acquire is scoped.
2. The nine `fetch*()` functions differ only in URL, root CA and parse body.
3. `T_CQ_03`'s grep is clean — one name per concept, per layer, parsed not mirrored.
4. `preview_common.py` holds zero hardcoded geometry constants.
5. `cmdGet`/`cmdSet` are tables; `cmdHelp` derives from them.
6. The C4 debug-code convention is recorded in `best_practices.md` (QM adopts; Architect proposes).

## 12. C7–C9 — the programming-paradigm axis

### C7 — the firmware is effectively a single translation unit. This is the largest structural fact in the codebase, and it is written down nowhere.

**66 headers, 24 426 lines. 8 `.cpp`, 5 762 lines.** `main.cpp` includes 67 headers directly; 17
headers define non-`inline` free functions. Those definitions can only be included once, so the
header layout is not a choice about style — **it is load-bearing on the build being one TU.**

Consequences, all currently paid:

1. **No incremental build.** Any header edit rebuilds everything. With 7 build envs in `run/check`
   this is the dominant cost of the gate.
2. **No link-time isolation, so no enforced boundaries.** Every header can see every global
   (40 `g_*`, 70 `extern`s, 24 file-static `s_*`). ADR-060 D0's component model is not just
   *unimplemented* — the current physical design actively permits what D0 wants to forbid, and
   nothing fails when it is violated.
3. **It is the root cause of M-TESTARCH's T1 problem.** A host unit tier needs a component that can
   be compiled alone. Today almost nothing can be, and the reason is physical layout, not `<Arduino.h>`.
   The three host-clean `util/` files are exactly the three with no cross-header dependency.
4. **The 8 `.cpp` files are the tell.** `settingsStorage.cpp`, `spotifyTaskStorage.cpp`,
   `logSinkStorage.cpp`, `settingsCalStorage.cpp` — "storage" files that exist to give a header's
   definitions a home. The codebase has already discovered it needs separate TUs, four times, and
   solved it ad hoc each time without naming the pattern.

**This is not a refactor proposal.** Converting 66 headers to `.h`/`.cpp` pairs is a very large,
very low-reward diff on its own. The finding is that **D0 must state this explicitly as the thing it
is fixing**, and that "component" must mean *its own translation unit* — otherwise D0 lands as a
directory reshuffle with the coupling intact, and M-TESTARCH's T1/T2 tiers never become possible.
The `*Storage.cpp` convention is the existing precedent to name and generalise.

**Recommend: add as a decision to ADR-060, not a new task.**

### C8 — the memory-ownership policy is coherent, deliberate, and unwritten

Five real allocation sites, and they fall into exactly two patterns:

| Pattern | Sites | Freed? |
|---|---|---|
| **Lazy-allocate-once, never free** | `logServer.h:53`, `teletextApp.h:382`, `planeRadarApp.h:646`, `settings/systemSection.h:81`, `settings/wifiSection.h:774` | never, by design |
| **Explicit lifecycle** | `audio/audioEngine.h:559,601,791`, `webRadioApp.h:364` (`s_wr_audio`) | yes, and the teardown ordering is what `T_AE_04` protects |

The first pattern is the accepted fix for `.dram0.bss` pressure — allocate on first use so the debug
build does not overflow, then never free because nothing ever needs the memory back. It is correct on
this target and applied consistently at all five sites. **It is also invisible to a reader**, who sees
five unmatched `new`s and reasonably concludes there are five leaks.

**Recommend: one paragraph in `best_practices.md`** naming both patterns and the rule for choosing —
fold into TASK-463 (C4), which is already the "write the policy down" task. Zero code change.

### C9 — no type in the codebase suppresses copying

`= delete` appears **zero times** in `app/src`. Several types own a raw pointer with never-free
semantics (`_nos`, `_motion`, `_savedState`, `_confirmBtnsPtr`) and are copy-constructible by default.
A copy would produce two objects pointing at one allocation, and because nothing ever frees, **it
would not crash — it would silently diverge**, which is strictly worse to diagnose.

Not observed in production; no copy site found. Filed as **latent**, not a bug.

The fix is four lines total and C++11-legal under `-std=gnu++11`. It is also **already on the
critical path**: M-CODEQUAL's `TlsYieldGuard` sketch uses `= delete` for exactly this reason, so
TASK-458 introduces the idiom regardless. Extending it to the four owning types is a footnote on that
task, not a task of its own.

> **Note for TASK-458 / C2.** Guard types must additionally suppress *move*, or the audio engine's
> deliberate cross-scope hold (C2b, `s_aeSpotifyYielded`) gets a second, subtly different release
> path. M-CODEQUAL already flags C2b as needing a *transferable* guard — that is the one type where
> move must be defined rather than deleted, and it should be the only one.

## 13. Calibration — what is good, and what was measured and NOT filed

### 13.1 What the codebase does well

These are not filler. Each is a place where the obvious criticism does **not** apply, and a reviewer
who skips the measurement will file it anyway.

- **String safety is excellent.** 385 `snprintf`/`strncpy` call sites against **one** `strcpy` and
  **zero** `sprintf`/`strcat` (`winamp/pleditView.h:457`, a fixed literal into a sized field). On a
  C-string-heavy embedded codebase this is unusual and deliberate.
- **Timing constants are not magic.** 57 named `*_MS` constants; only **3** raw millisecond literals
  in `millis() - x > N` comparisons tree-wide. The magic-number problem here is *specifically*
  geometry and colour — exactly where M-CODEQUAL put it. A generic "extract the magic numbers" task
  would find almost nothing.
- **Modern-C++ hygiene is present where it costs nothing**: 429 `constexpr`, 203 `override`,
  136 `nullptr` against 10 `NULL`, `enum class` for 32 of 40 enums (the 8 plain ones are bitmask
  flags and legacy drag states — correct as-is).
- **Arduino `String` is nearly absent** — 14 sites total, concentrated in `dataTaskStorage.cpp`'s
  buffered fetches where the API forces it. The right call on this target, and evidently a held line.
- **`App` (`app.h`) is a genuinely good interface.** Five pure virtuals, four optional predicates each
  with a documented safe default and the task that introduced it. `hasPendingAsync`/`isNavigationTap`
  encode a subtle shell contract *in the interface* rather than in convention.
- **`appRegistry.h` is the best pattern in the tree**: an X-macro single source of truth, consumed by
  codegen, staleness-gated at `run/check`. This is what C5 wants for geometry and C3 for the debug
  surface — **the model already exists in-repo; it just was not generalised.**

### 13.2 Three metrics that look like findings and are not

- **"1 116 C-style casts vs 25 `static_cast`."** Sampled 20 at random: every one is an idiomatic
  embedded numeric conversion — `(float)` in fixed-point maths, `(int)`/`(unsigned long)` for
  `printf` varargs, `(uint8_t)` on `tm` fields, `(int)` on an `enum class` for a format string.
  `static_cast` would be more precise and would catch nothing here. **Not a finding.** Filing it
  would generate a large, risky, zero-value diff.
- **"77 `new` vs 19 `delete`."** Wrong by an order of magnitude: the English word *new* in comments.
  Real allocations: **5**. Real `delete`: **5**, all in the audio engine. See C8.
- **"40 plain enums."** The regex matches `enum class` too. Real plain enums: **8**.

Each is the same trap M-CODEQUAL §3 documents. That note now has four independent confirmations and
should be adopted as a best practice: *in this codebase, a grep-derived count is a hypothesis, not a
finding.*

---
