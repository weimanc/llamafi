# Design — M-SRCLAYOUT: decompose `main.cpp` and move state ownership out of it

> Owner: Architect
> Status: **proposed** — 2026-08-15. Needs ADR-060 sign-off before TASK-451 begins.
> Date: 2026-08-15
> Feeds: ADR-060 (to be written)
> Tracked-as: TASK-451, TASK-452, TASK-453, TASK-454, TASK-455
> Registers: no new `feature_inventory.yaml` id — this is structural, not a feature. New cross-feature
> seam registers as **X065** (shell state ownership).
> Precedent: [M-AUDIO-ENGINE-extraction.md](M-AUDIO-ENGINE-extraction.md) / ADR-059 D2 — the
> pure-move-plus-gate discipline this design reuses wholesale.

**Standalone value:** full. Every stage is behaviour-neutral and independently valuable. Nothing here
depends on M-WINAMP-PLAYER, M-SDFS or the TASK-442 playback blocker, and none of it needs a working
Spotify account or a playing audio path.

---

## 1. Context

`app/src` is 30 022 lines across 58 headers and 9 `.cpp` files. `main.cpp` alone is **5 880 lines** —
just under 20 % of the firmware source, in one file. It divides as:

| Region | Lines | Span |
|---|---:|---|
| App subclasses defined inline (7 of them) | **1 678** | `243`–`1920` |
| └ `StockApp` alone | 711 | `1210`–`1920` |
| App instances + `dbgGet`/`dbgSet` shims | 39 | `1921`–`1959` |
| Shell dispatch (`switchApp`, `appTick`, `appHandleInput`, taskbar press/release, `persistPlayerMode`) | 321 | `1960`–`2280` |
| `setup()` | 631 | `2281`–`2911` |
| Serial command table + touch-injection ring | 227 | `2912`–`3138` |
| SD boot mount (production, `SD_BOOT_MOUNT`) | 93 | `3139`–`3231` |
| `SERIAL_DEBUG` command implementations | **2 550** | `3232`–`5781` |
| └ `cmdGet` 618 · `cmdSet` 694 · SD bring-up probes ~1 300 | | |
| `loop()` | 99 | `5782`–`5880` |

**Roughly 2 780 lines — 47 % of the file — is a debug console that is `#ifdef`'d out of the
production binary entirely.** A further 1 678 lines are app classes that have an obvious home.

Meanwhile the pattern this design proposes **already exists in this repo and works**. Six apps live
in their own files today:

| File | Lines |
|---|---:|
| `webRadioApp.h` | 1 929 |
| `aquarium/aquariumApp.h` | 1 598 |
| `planeRadarApp.h` | 1 428 |
| `localPlayerApp.h` | 1 003 |
| `teletextApp.h` | 724 |
| `clockApp.h` | 669 |

`SettingsApp`'s sections are likewise already split across `settings/*.h` — only its class shell
stayed behind. So this is not a new architecture. It is **finishing an existing one**, applied
backwards to the apps that predate it.

## 2. What is *not* the problem

Recording this explicitly, because it was asserted in analysis, is **false**, and a future reader
acting on it would design the wrong fix.

> ~~"These headers define non-inline functions, so they physically cannot be included from a second
> `.cpp` — duplicate-symbol link errors."~~

Checked and refuted:

- `dataTask.h` has **32 declarations and zero definitions**; the bodies are in `dataTaskStorage.cpp`.
  That is the textbook-correct declare/define split.
- **Zero** namespace-scope non-`static`, non-`extern` variable definitions exist across all 58
  headers — the actual C++11 duplicate-symbol trap is not present anywhere.
- The app classes are classes, so their member functions are implicitly `inline` and are legal in any
  number of TUs.
- Only **three** true external-linkage function bodies sit in a header — `audio_showstreamtitle`,
  `audio_info`, `audio_process_extern` at `audio/audioEngine.h:83,94,209` — and `:82` already carries
  a comment acknowledging exactly that constraint.
- Proof by existence: `dataTask.h`, `spotifyTask.h` and `planeRadarApp.h` are **already** included
  from two `.cpp` files each today, and link.

The house style is correct. There is no link-level barrier to creating `stockApp.cpp` tomorrow.

Two further non-problems, to stop them being swept in:

- **This is not a unity-build problem needing a build-system change.** No CMake/PlatformIO surgery is
  in scope.
- **`static`-in-header functions duplicate per-TU**, which costs flash. That is a *cost to measure in
  Stage D*, not a defect to fix now.

## 3. The actual defect: state ownership, not linkage

The barrier is **where the mutable state lives**, and it is a gravity well rather than a wall.

`main.cpp` holds 21 `g_`-prefixed globals, and 72 `extern` declarations across the headers point back
at them. They fall into three groups needing three different answers:

| Group | Members | Today |
|---|---|---|
| **App instances** | `g_SpotifyApp`, `g_ClockApp`, `g_MatrixApp`, `g_WeatherApp`, `g_CryptoApp`, `g_LifeApp`, `g_SettingsApp`, `g_StockApp`, `g_AquariumApp`, `g_TeletextApp`, `g_PlaneRadarApp`, `g_WebRadioApp`, `g_LocalPlayerApp` (13) | `static` in `main.cpp`, each defined *after* the class and *before* its `dbg` shim |
| **Shell state** | `g_shellBusy`, `g_shellBusySetMs`, `g_previousAppId`, `g_appLaunched[]`, `s_inGesture`, `s_lastTouchX/Y`, `s_cooldownMs`, `s_tbPressedSlot`, `s_tbPressedApp` | loose file-scope variables in `main.cpp` |
| **Shared widgets** | `g_ledFlow`, `g_backlight`, `g_keyboard`, `g_countryPicker`, `g_touchDebug` | non-`static` in `main.cpp`, reached by `extern` |

Because these definitions live at `main.cpp:164`–`1971`, any code that touches them must be
*textually downstream of that point*, and `main.cpp` is the only translation unit that is. The
include list is correspondingly load-bearing: `settings/*.h` is pulled in mid-file at `938`–`944`,
apps are instantiated immediately before the `dbg` shims that reference them, and `appRegistry.h` is
included twice (`1959`, `3665`) as an X-macro.

That is why every new feature landed here. Not sloppiness — **it was the only location with the
whole world already in scope.**

## 4. Design

### D1 — Target tree

```
app/src/
  main.cpp                    setup() + loop() ONLY.  Target: < 300 lines
  shell/
    appShell.h / .cpp         App, AppId, ShellState, dispatch, taskbar press/release
    appTable.h                X-macro-generated App* table + appById()
    taskbar/                  (moved as-is)
  apps/
    spotifyApp.h  clockApp.h  weatherApp.h  cryptoApp.h
    matrixApp.h   lifeApp.h   settingsApp.h
    stock/        stockApp.h  stockList.h  stockChart.h  stockHeatmap.h
    aquariumApp.h teletextApp.h planeRadarApp.h webRadioApp.h localPlayerApp.h
  debug/
    serialConsole/            console.h  cmdGet.h  cmdSet.h  cmdTouch.h  sdProbe.h
  audio/ player/ winamp/ settings/ util/          unchanged
```

### D2 — App instances: use the registry, not 13 accessors

`appRegistry.h` already drives `AppId` via X-macro. Extend it to generate the instance table:

```cpp
// shell/appTable.h
App& appById(AppId id);            // declaration — includable anywhere
```

with the table and the one definition in `appShell.cpp`. Each instance then moves out of `main.cpp`
into its own app file alongside its class, and `switchApp` / `appTick` / `appHandleInput` stop
naming individual apps entirely — they index. One accessor replaces thirteen, built on machinery
that already exists and is already staleness-gated by `run/check`.

### D3 — Shell state: one struct, one accessor

The loose flags become a single owned struct:

```cpp
// shell/appShell.h
struct ShellState {
    bool          busy;  unsigned long busySetMs;
    AppId         previous;
    bool          launched[(int)AppId::COUNT];
    bool          inGesture;  int lastTouchX, lastTouchY;
    unsigned long cooldownMs;
    int           tbPressedSlot, tbPressedApp;
};
ShellState& shell();               // defined in appShell.cpp
```

This is the singleton-shaped part of the design, and it is the part that earns it.

### D4 — Use file-scope `static`, **not** the Meyers singleton

```cpp
// shell/appShell.cpp
static ShellState s_shell;
ShellState& shell() { return s_shell; }
```

Explicitly **not**:

```cpp
static ShellState& shell() { static ShellState s; return s; }   // REJECTED
```

Three reasons, all specific to this target:

1. **Lazy construction breaks deterministic boot.** `setup()` is 631 lines of deliberately staged
   init (WiFi → SPIFFS → NTP → display → apps). Construct-on-first-use hands the *timing* of each
   app's memory to the compiler. With `dram0_0_seg` headroom measured between **0 B and 40 B** on the
   debug env at various points in this project's history, "when does this allocate" is not a question
   to delegate.
2. **C++11 thread-safe statics are not free.** Each emits a guard variable plus
   `__cxa_guard_acquire/release`. The concurrency is real here — `dataTask`, `spotifyTask`, the audio
   pump task — so ×13 apps this is measurable flash and DRAM. `-fno-threadsafe-statics` removes the
   cost and reintroduces a genuine first-use race.
3. **The problem it solves is absent.** Meyers singletons exist to defeat the
   static-initialization-order fiasco. Init order here is explicit and readable in `setup()`, which
   is strictly better than lazy magic.

File-scope `static` keeps deterministic `.bss` placement, which `app/mem_manifest.yaml` already
accounts for.

There is **no singleton or accessor pattern anywhere in `app/src` today** — so D2/D3 establish a new
convention, and that is precisely what ADR-060 exists to record.

### D5 — Prefer parameters to accessors

A global accessor makes shell state *easier to reach*, which can entrench coupling rather than reduce
it. The `App` base class (`appShell.h:9`) is already a clean interface. `shell()` is accepted as a
pragmatic concession on a 320 KB-RAM device — it is **not** licence to add further singletons for
state that could be a parameter. New code reaching for `shell()` is a review question.

## 5. Staging

The stages are ordered by risk, and **A/B are deliberately separated from C/D**: the first two move
text within the existing translation unit, the last two change what the compiler sees.

| Stage | Task | What | TU change? | Binary risk |
|---|---|---|---|---|
| **A** | TASK-451 | Move the 7 inline app classes into `apps/`; move the 6 existing app headers there too, same commit, so the tree is consistent | none — still `#include`d by `main.cpp` | ~none |
| **B** | TASK-452 | Move the ~2 780-line `SERIAL_DEBUG` console into `debug/serialConsole/` headers | none | ~none (not in prod binary at all) |
| **C** | TASK-453 | D2 + D3 + D4 — state ownership: `appById()`, `ShellState`, instances move to their app files | **yes** — enables independent `.cpp`s | real, measured |
| **D** | TASK-454 | Promote selected modules to their own `.cpp`, **one at a time**, each measured | yes | real, measured |
| — | TASK-455 | `main.cpp` reduced to `setup()` + `loop()`; hygiene items (§8) | — | — |

Stages A and B deliver most of the readability win at near-zero risk, because a pure text move within
one TU presents the compiler with a near-identical blob. **Stage D is optional and may be
partially declined** — if a module's measured flash/DRAM delta is not worth it, recording that
decision is a legitimate outcome, not a failure.

## 6. Build and memory cost

Stages A/B should produce a near-identical binary; they are not expected to be *byte*-identical
(`__FILE__`/`__LINE__` in asserts and log macros shift). Stages C/D lose some cross-TU inlining and
will cost flash, possibly DRAM.

**Headroom must be re-derived fresh at each stage, never remembered.** `dram0_0_seg` headroom is a
documented moving target in this project — 0 B on 2026-07-29/30, 40 B on 2026-08-02 after the
M-CEEFAX cut. The procedure is `./run/build-debug` plus a `.map` extents grep, per
[M-MEMBUDGET](M-MEMBUDGET-memory-budget.md), and the result is recorded against
`app/mem_manifest.yaml` in the task.

Stage D's per-module rule: **any module whose promotion costs more than 256 B of `dram0_0_seg` is
not promoted** without an explicit note in the task recording the trade.

## 7. Verification obligation

Behaviour-neutrality is the entire contract, so it is verified rather than argued. This reuses
ADR-059 D2's discipline verbatim: *the extraction commit carries no behavioural hunks.*

1. `./run/check` green on both envs, every stage.
2. **`git diff -M --stat` shows ≥95 % rename similarity** on each moved block, and no hunk changes
   behaviour. (Same review gate ADR-059 used, after `T_AE_05` was correctly demoted from a test to a
   checklist item — it has no repeatable procedure and inflates coverage if counted as a test.)
3. `.map` section extents captured before and after each stage, deltas recorded.
4. A DUT pass over app switching, taskbar cycling, eject, and Settings navigation — the paths the
   shell dispatch actually owns.
5. Stage C additionally: `./run/test-smoke`, plus `get dataq` and taskbar indicator states
   (idle/busy/connecting/error) confirmed unchanged.

**No stage requires Spotify playback**, so TASK-442 does not block any of this.

## 8. Hygiene items folded in (TASK-455)

- **`run/check` gate count disagrees with itself in three places**: `CLAUDE.md` says 5 gates,
  ADR-059 §"What acceptance authorises" says `6/6`, `appRegistry.h`'s comment says step `[6/7]`.
  Reconcile to the actual number and fix all three.
- `appRegistry.h` is included twice in `main.cpp` (`1959`, `3665`). Legitimate X-macro re-inclusion,
  but it should carry a comment saying so at both sites.
- `main.cpp:164`'s `g_previousAppId` and `appShell.h`'s `currentAppId` are the same concept split
  across two files with different naming conventions. Unify under `ShellState` in Stage C.

## 9. Test & validation

Ids reserved in the `T_SRC_` family. The governing property is behaviour-neutrality, tested by
re-running existing suites unchanged — new ids cover only what the reorganisation itself can break.

| id | Must be true | Method | Pass criterion |
|---|---|---|---|
| `T_SRC_01` | No behavioural change, any stage | DUT — existing suite, unchanged. **Baseline = ≥3 full runs before Stage A lands**, flaky set pre-declared from them (ADR-059 D13) | no test passing in all 3 baselines fails after; no new failure outside the pre-declared flaky set |
| `T_SRC_02` | Stages A/B are text moves | host — `git diff -M --stat` | ≥95 % rename similarity; zero behavioural hunks on review |
| `T_SRC_03` | Build gates green | host — `./run/check` | green on both envs, every stage |
| `T_SRC_04` | Memory budget respected | host — `run/build-debug` + `.map` extents | `dram0_0_seg` headroom **re-derived fresh**, recorded per stage; Stage D per-module ceiling 256 B |
| `T_SRC_05` | App dispatch intact after D2 | DUT — cycle every taskbar slot, both eject paths, ×3 | every app inits, resumes, suspends; no slot lands on the wrong app |
| `T_SRC_06` | Taskbar indicator semantics intact | DUT — force a Spotify error and a connecting state | idle/busy/connecting/error precedence unchanged (ADR-046) |
| `T_SRC_07` | Debug console intact after Stage B | DUT — `get`/`set` over every registered key, `tap`, `drag`, `switchapp` | every key resolves as before; injection queue behaves identically |
| `T_SRC_08` | Registry staleness gate still fires | host — edit `appRegistry.h`, do not re-run codegen, `./run/check` | the gate fails, as it does today |

**Validation note.** `T_SRC_01` is the load-bearing test and is *deliberately not new work* — the
value is that the existing suite runs untouched. It must be baselined **before Stage A lands**, or
there is nothing to compare against. This is the same trap ADR-059 D13 called out, and the same
answer.

## 10. Open questions

- **OQ1** — does Stage A move the 6 already-extracted app headers into `apps/` too? Leaning **yes**:
  a half-migrated tree is worse than either end state, and it is a pure rename. Cost is that every
  include path referencing them changes in one commit.
- **OQ2** — does `SettingsApp` move to `apps/settingsApp.h` while its sections stay in `settings/`,
  or does `settings/` move under `apps/settings/`? Leaning **the former** — `settings/` holds shared
  widgets (`keyboardWidget.h`, `sliderWidget.h`, `settingsWidgets.h`) used beyond Settings itself, so
  it is not purely one app's territory.
- **OQ3** — should `setup()`'s 631 lines be decomposed into staged init functions
  (`initDisplay()`, `initWifi()`, `initApps()`) in Stage C? Attractive, but it reorders nothing and
  risks obscuring a boot sequence whose ordering is load-bearing and hard-won (TASK-288, TASK-404,
  TASK-426). Leaning **defer to its own task** rather than folding it into a stage whose contract is
  "pure move".
- **OQ4** — Stage D scope. Which modules actually warrant their own TU? Proposal: decide empirically
  from Stage C's measurements rather than committing a list now.

## 11. Exit criteria

1. `main.cpp` contains `setup()` and `loop()` and nothing else — **under 300 lines**.
2. No app class, app instance, or shell state variable is defined in `main.cpp`.
3. No `SERIAL_DEBUG` command implementation is defined in `main.cpp`.
4. `ShellState` and `appById()` are the sole access paths to shell state; the 72 `extern`s pointing
   into `main.cpp` are gone.
5. §7 items 1–5 green at every stage.
6. ADR-060 records the state-ownership convention (D2/D3/D4) and the D5 caution.
