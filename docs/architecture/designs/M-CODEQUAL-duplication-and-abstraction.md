# Design — M-CODEQUAL: duplication, abstraction and constant-ownership cleanups

> Owner: Architect
> Status: **proposed** — 2026-08-15
> Date: 2026-08-15
> Companion to: [M-SRCLAYOUT-main-decomposition.md](M-SRCLAYOUT-main-decomposition.md)
> Tracked-as: TASK-456 … TASK-461
> Registers: no new `feature_inventory.yaml` id — structural.
> Extends: **LL-114** (host tools mirror firmware truth by copy) — §6 closes the hole TASK-335
> could not reach.

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

**Design.** A single `httpFetchJson()` taking `{url, rootCa, certTag, phaseSlot}` and a parse
callback; each `fetch*()` shrinks to URL construction plus its parse body. Do it **after C2** — the
scope guards are what make the consolidation safe, because they remove the exit-path bookkeeping that
is the most error-prone part of the skeleton.

**Constraint.** `-std=gnu++11` — the parse callback is a template parameter or a plain function
pointer, not `std::function` (heap allocation on a memory-constrained device).

## 3. C2 — RAII scope guards

**This is the highest-value item in the document, because it fixes a bug class with a proven
production instance.**

Measured across `app/src`, excluding comments and counting only real call sites:

| Pair | Acquires | Releases |
|---|---:|---:|
| `tlsYield()` / `tlsResume()` | 12 | **24** |
| `http.begin` / `http.end` | 25 | 22 |
| `mb_arena_acquire` / `mb_arena_release` | 13 | 8 |
| `xSemaphoreTake` / `xSemaphoreGive` | 18 | 19 |
| `portENTER_CRITICAL_SAFE` / `portEXIT_CRITICAL_SAFE` | 59 | 59 |

The 12/24 ratio is not itself a bug — it is one acquire per fetch and one release per *exit path*.
That is precisely the problem: correctness depends on a human enumerating every `return`. The code
says so at `dataTaskStorage.cpp:277` — `spotifyTask::tlsResume();  // BP-031: every exit path`.

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

`cmdGet` is 616 lines / 40 `strcmp` branches (`main.cpp:3484`). `cmdSet` is 692 lines / 28 branches
(`main.cpp:4101`). **1 308 lines to dispatch 68 keys.**

The table-driven pattern **already exists in this file**: `kCmds[]` at `main.cpp:2976` dispatches the
command *verbs* through a `{name, handler}` table, and every app implements `dbgGet`/`dbgSet`. Only
the shell-level variable dispatch never adopted either.

**Design.** A `{name, getter, setter, help}` table, sectioned per subsystem. Three follow-on wins:

1. `cmdHelp` (`main.cpp:5769`) enumerates the table instead of hardcoding text — it cannot go stale.
2. The debug surface becomes *introspectable*, which is what `run_serialdbg_tests.py` wants.
3. `T_SRC_07`'s "every registered key still resolves" becomes a loop over the table rather than a
   hand-written list.

Debug-only code, so a defect here cannot ship. Low risk, high readability payoff.

## 5. C4 — the debug/production seam

There is no written convention, so three mechanisms coexist: `#ifdef SERIAL_DEBUG` (the bulk),
`#ifdef SD_BOOT_MOUNT` (production-safe subset, correctly separated at `main.cpp:3127-3139` and
explained there), and `#ifdef MEMBUDGET_PHASE1`. The separation is *reasoned* — `main.cpp:81-84`
documents exactly why the SD boot mount left the `SERIAL_DEBUG` gate — but it is reasoned per-site,
not by policy.

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
| **TASK-456** | C2 — `TlsYieldGuard` + `HttpSession` guards | — | low | `run/check`; `T_CQ_01` |
| **TASK-457** | C2b — migrate `s_aeSpotifyYielded` to a transferable guard | 456 | **medium** | `run/check`; `wr-soak` ≥30 min |
| **TASK-458** | C1 — consolidate the nine fetch functions | 456 | medium | `run/check`; `T_CQ_02`; cert preflight |
| **TASK-459** | C5 — canonical canvas/window constants, firmware + bake + tools | — | low | `T_CQ_03`; golden re-bake |
| **TASK-460** | C3 — table-driven `cmdGet`/`cmdSet` | M-SRCLAYOUT B | low | `T_CQ_04` |
| **TASK-461** | C4 policy + C6 palette | — | low | `run/check` |

TASK-456 and TASK-459 are independent of M-SRCLAYOUT and of each other — either can start
immediately. **TASK-457 is the one to be careful with**: it touches the audio engine's teardown
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
