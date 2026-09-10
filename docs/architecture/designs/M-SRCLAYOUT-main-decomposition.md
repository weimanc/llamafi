# Design — M-SRCLAYOUT: decompose `main.cpp` and move state ownership out of it

> Owner: Architect
> Status: proposed
> As-built: landed; Stages A and B VERIFIED 2026-08-16 (a044f5d, 78caa95, b36f184) —
> reviewed and DUT-verified under TASK-488, nothing reverted; see §5a. Stages C and D remain
> **proposed** and need ADR-060 sign-off before TASK-455 begins.
> Date: 2026-08-15
> Feeds: ADR-060 (to be written)
> Tracked-as: TASK-453, TASK-454, TASK-455, TASK-456, TASK-457, TASK-464, TASK-471, TASK-472
> Registers: no new `feature_inventory.yaml` id — this is structural, not a feature. New cross-feature
> seam registers as **X065** (shell state ownership).
> Precedent: [M-AUDIO-ENGINE-extraction.md](M-AUDIO-ENGINE-extraction.md) / ADR-059 D2 — the
> pure-move-plus-gate discipline this design reuses wholesale.

**Standalone value:** full. Every stage is behaviour-neutral and independently valuable. Nothing here
depends on M-WINAMP-PLAYER or M-SDFS, and none of it needs a working Spotify account or a playing
audio path — `run/check` is the whole gate.

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

Because these definitions live in the globals block near the top of `app/src/main.cpp` (`currentAppId`
through the app-instance table), any code that touches them must be
*textually downstream of that point*, and `main.cpp` is the only translation unit that is. The
include list is correspondingly load-bearing: `settings/*.h` is pulled in mid-file at `938`–`944`,
apps are instantiated immediately before the `dbg` shims that reference them, and `appRegistry.h` is
included twice (`1959`, `3665`) as an X-macro.

That is why every new feature landed here. Not sloppiness — **it was the only location with the
whole world already in scope.**

## 4. Design

### D0 — The unit of physical design is a *component*: one class, one `.h`, one `.cpp`

This is the decision everything else follows from, and the one the first draft of this document
failed to make. It is not a preference — it is what the standard references require, and this
codebase currently violates all of them.

| Reference | Requirement | Status here |
|---|---|---|
| **C++ Core Guidelines, SF.1** | *"Use a `.cpp` suffix for code files and `.h` for interface files"* | violated — 58 headers, 8 `.cpp` |
| **C++ Core Guidelines, SF.5** | a `.cpp` must include the `.h` defining its interface | n/a — most classes have no `.cpp` |
| **C++ Core Guidelines, SF.11** | headers must be **self-contained** | violated — app headers rely on `main.cpp`'s include order |
| **Lakos, *Large-Scale C++ Software Design*** | a **component** = one `.h` + one `.cpp`; it is the atomic unit of physical design, of testing, and of dependency management | violated — no component boundaries exist |
| **Google C++ Style Guide** | self-contained headers; one class per header, `.h`/`.cc` pairs | violated |

Lakos is the governing reference because this is precisely the problem he defines: *physical* design
(files, translation units, link-time dependencies) as distinct from *logical* design (classes,
inheritance). This codebase has reasonable logical design — a clean `App` interface, an X-macro
registry, per-app `dbgGet`/`dbgSet` — and effectively **no physical design at all**. One translation
unit contained 20 % of the source.

**The rule, stated once:**

> Every class that is not a pure interface, a template, or a set of `constexpr`/`inline` helpers gets
> exactly one component: `foo.h` declaring it, `foo.cpp` defining it. The header is self-contained —
> it compiles standing alone, includes what it uses, and never depends on being included at a
> particular point in some other file.

**The three legitimate header-only exceptions**, so this does not get applied mechanically:

- **Pure interfaces / abstract base classes** — `app.h` is correct as a header with no `.cpp`; it is
  all pure-virtual with an inline defaulted destructor.
- **Templates** — must be visible at instantiation.
- **`constexpr` / `inline` helper sets** — `util/mathUtil.h`, `util/textFit.h`, `touch/hitbox.h`.

Everything else — all thirteen apps, the shell, the taskbar, the boot sequence, the debug console —
is a component.

### D0a — The embedded objection, bounded honestly

The counter-argument for header-only on a 320 KB-RAM device is lost cross-TU inlining. It is real but
**much smaller here than it first appears**, and it does not justify abandoning physical design:

- **The shell↔app boundary is already un-inlinable.** Every `App` method is `virtual`; the shell calls
  through an `App*` via vtable dispatch. Moving app bodies into `.cpp` files costs *nothing* at the
  boundary that carries the most calls, because no inlining happens there today.
- **An app's internal helpers stay in its own `.cpp`** and continue to be inlined.
- **Shared `inline`/`static inline` utility headers** keep being inlined everywhere.
- What genuinely moves out of reach is cross-app and app→shell inlining of small non-virtual helpers —
  a narrow set.

So the cost is measured per component (§6) and, where a component's promotion proves genuinely
expensive, **that component may stay header-only with the reason recorded**. That is an engineering
exception, granted on evidence. It is not the default, and "we might lose some inlining" is not a
reason to skip physical design wholesale.

### D0b — `main.cpp` is an entry point and contains no logic

Target: **under 40 lines.**

```cpp
// main.cpp — Arduino entry point. Nothing else belongs here.
#include "boot/boot.h"
#include "shell/appShell.h"

void setup() { boot::run(); }
void loop()  { shell::tick(); }
```

Everything currently in `main.cpp` — `setup()`'s 631 lines, the shell dispatch, the app instances,
the serial command table, the SD boot mount — is somebody's component. The entry point's only job is
to name the composition root and hand control to it.

### D0c — A composition root owns the instances

Thirteen `static XApp g_XApp;` definitions scattered through the entry point is the anti-pattern that
made `main.cpp` load-bearing in the first place: every app had to be *textually downstream* of its own
instance.

Instead, one **composition root** — `shell/appTable.cpp` — constructs every app and exposes them
through the registry:

```cpp
// shell/appTable.h
App& appById(AppId id);
```

```cpp
// shell/appTable.cpp — the ONLY place app instances are constructed
#define APP_X(Name, icon, cfg, disp)  static Name##App s_##Name;
#include "appRegistry.h"
#undef APP_X

static App* const s_apps[(int)AppId::COUNT] = {
#define APP_X(Name, icon, cfg, disp)  &s_##Name,
#include "appRegistry.h"
#undef APP_X
};

App& appById(AppId id) { return *s_apps[(int)id]; }
```

The X-macro registry already exists and is already staleness-gated by `run/check` step 6, so the
table cannot drift from `AppId`. `switchApp` / `appTick` / `appHandleInput` stop naming individual
apps and index instead.

This also removes the naming inconsistency the current code carries — `g_SpotifyApp` is `static` (so
the `g_` prefix is wrong; it is not global) while `g_ledFlow` genuinely is global.

### D0d — Dependency direction is one-way, and cycles are prohibited

Lakos's second requirement after components is **levelization**: the dependency graph must be acyclic,
so components can be built, tested and reasoned about bottom-up.

```
level 3   apps/*, stock/, aquarium/  (may depend on 2, 1, 0)
level 2   shell/, boot/, debug/, sd/ (may depend on 1, 0 — one exception, below)
level 1   audio/, player/, winamp/, settings/
level 0   util/, gen/, touch/, app.h
```

`taskbar/` moved into `shell/taskbar.h` (M-SRCLAYOUT Stage E / TASK-471, `871134d`) — level 2, not 1,
since it's now one of `shell/`'s own owned components rather than a standalone directory.

Two rules with teeth:

- **An app never includes another app.** Shared behaviour moves down a level.
- **No level-0 or level-1 component includes anything from `apps/` or `shell/`.**

**One necessary exception, confirmed by audit (TASK-472, 2026-08-22):** `shell/appTable.h` — the
composition root — includes all thirteen apps (level 3). This is required, not a violation: its
entire job is constructing every app instance, so it must reach into all of them. It is the *only*
level-2 file that reaches into level 3; every other `shell/`/`boot/`/`debug/`/`sd/` file holds the
rule.

**Full audit result (TASK-472, 2026-08-22):** zero app-to-app includes (the only level-3→level-3
edges are `stock/`'s own internal structure — `stockChart`/`stockHeatmap` reaching their parent
`stockApp.h` via a back-reference, one app's internal decomposition, not a cross-app violation);
zero level-0/1 files include `apps/` or `shell/`, either direction, across the whole tree. The one
violation flagged below (`winampDisplay.h` reaching back into player-mode concepts) is confirmed
**closed**, not just "accepted" — see the note at that paragraph's end. Real, non-violating gap
found: five apps (`clockApp`, `teletextApp`, `planeRadarApp`, `webRadioApp`, `localPlayerApp`) never
moved into `apps/` despite D1's target tree placing them there — filed as TASK-530, not urgent since
it causes no actual dependency problem.

The one known violation to fix on the way: `apps/spotifyApp.h` and `webRadioApp.h` both reach into
`winamp/winampDisplay.h`, which reaches back into player-mode concepts. ADR-059's capability mask is
the accepted fix for that direction.

**CLOSED, confirmed by audit (TASK-472, 2026-08-22).** Read `winampDisplay.h` directly rather than
trusting "accepted": it no longer references `AppId`, `currentAppId`, or any player-mode/app-instance
global. The reach-back is gone, replaced by a `_playerCaps` capability bitmask
(`CAP_TRANSPORT`/`CAP_SEEK`/`CAP_SHUFFLE`/`CAP_REPEAT`) that the app layer sets via
`setPlayerCaps()` — `winampDisplay.h` only ever reads the mask, never asks which app or mode is
active. ADR-059's fix genuinely landed.

### D1 — Target tree

Every entry below is a component (`.h` + `.cpp`) unless marked **[H]** for a legitimate header-only
exception per D0. Line counts are the measured size of the code being moved.
```
app/src/
  main.cpp                     <40   entry point ONLY — setup(){boot::run();} loop(){shell::tick();}

  app.h                    [H]   51   the App interface — pure virtual, no .cpp needed (D0 exception)

  shell/
    appId.h                [H]   ~20   generated AppId enum (X-macro over appRegistry.h)
    appTable.h/.cpp               ~60   COMPOSITION ROOT — constructs all 13 apps, appById()
    appShell.h/.cpp              ~360   dispatch, switchApp, ShellState, persistPlayerMode
    taskbar.h/.cpp               ~221   moved from taskbar/

  boot/
    boot.h/.cpp                  ~631   the staged init sequence, moved verbatim from setup()

  apps/                              one component per app — 13 of them
    spotifyApp.h/.cpp             118
    clockApp.h/.cpp               669
    weatherApp.h/.cpp             135
    cryptoApp.h/.cpp              143
    matrixApp.h/.cpp              100
    lifeApp.h/.cpp                162
    settingsApp.h/.cpp            220
    aquariumApp.h/.cpp          1 598
    teletextApp.h/.cpp            724
    planeRadarApp.h/.cpp        1 428
    webRadioApp.h/.cpp          1 929
    localPlayerApp.h/.cpp       1 003
    stock/
      stockApp.h/.cpp            ~300   list view + coordination
      stockChart.h/.cpp          ~250
      stockHeatmap.h/.cpp        ~220

  sd/
    sdMount.h/.cpp                ~94   PRODUCTION (SD_BOOT_MOUNT) — never under debug/

  debug/
    serialConsole/
      console.h/.cpp             ~226   SerialCmd, kCmds[], injection ring, dispatch loop
      cmdTouch.h/.cpp             245
      cmdGet.h/.cpp               616
      cmdSet.h/.cpp               733
      cmdMisc.h/.cpp              166
      cmdSd.h/.cpp                780
      cmdSystem.h/.cpp             39
    touchDebugOverlay.h/.cpp       43

  audio/ player/ winamp/ settings/ util/ touch/ gen/     unchanged for now
```

**~28 components.** That is an ordinary size for 30 000 lines of C++ — the anomaly is the current
8 `.cpp` files, not the target.

Three entries above are decisions, not mechanical placements:

- **`app.h` stays header-only** — pure interface, D0's first exception. It does not get a `.cpp`
  merely for symmetry.
- **`stock/` becomes three components**, not one 770-line file. `StockApp` has three genuinely
  separable views (list, chart detail, heatmap detail) already expressed as a `StockSubView` enum;
  they are separate concerns sharing a data model, which is exactly the split `winamp/pleditView.h`
  established as house precedent.
- **`sd/sdMount` is production code** and is deliberately *not* under `debug/`, despite sitting
  adjacent to the SD probes in the old `main.cpp`. It is gated on `SD_BOOT_MOUNT`, not
  `SERIAL_DEBUG`. Filing it by proximity would undo a documented decision — see ADR-061 D4.

### D1a — `setup()` moves whole; this is not OQ3

`setup()` is **631 lines**, so "`main.cpp` holds `setup()` and `loop()`, under 300 lines" is
arithmetically impossible and an earlier draft of this document asserted both. The resolution:
`setup()`'s body moves **verbatim** into `shell/boot.h` as `bootSequence()`, and `main.cpp` keeps
`void setup() { bootSequence(); }`.

That is a pure move — one call site added, zero statements reordered — and it is **a different thing
from OQ3**, which proposes *decomposing* `setup()` into staged init functions (`initDisplay()`,
`initWifi()`, `initApps()`). OQ3 stays deferred: the boot ordering is load-bearing and hard-won
(TASK-288, TASK-404, TASK-426), and breaking it apart is not behaviour-neutral in the way a whole-body
move is.

### D2 — App instances: superseded by D0c

*(Retained as a pointer; the first draft placed the instance table in `appShell.cpp` and left each
instance "in its own app file". Both are wrong. An app component must not define its own global
instance — that reintroduces the scattered-ownership problem one directory down, and makes the app
untestable in isolation because merely linking it constructs it.)*

**See D0c.** One composition root, `shell/appTable.cpp`, constructs all thirteen. App components
declare and define their class and nothing else.

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

Stages are ordered so each is independently landable and independently revertible. **The end state
is D0's component model; header-only intermediates are scaffolding, not a destination.**

| Stage | Task | What | Status |
|---|---|---|---|
| **A** | TASK-453 | 7 app classes out of `main.cpp` into `apps/*.h` | **landed** `78caa95` — unreviewed |
| **B** | TASK-454 | `SERIAL_DEBUG` console into `debug/serialConsole/*.h` | **landed** `b36f184` — unreviewed |
| **C** | TASK-455 | `setup()` → `boot/boot.h` (D1a, verbatim) | **landed** — pure move proven by symbol identity |
| **D** | TASK-456 | `shell/appTable.h` composition root (D0c) + `shell/shellState.{h,cpp}` (D3/D4); instances leave `main.cpp` | **landed** — part 1 pure move proven by symbol identity; part 2 behavioural, DUT gate owed |
| **E** | TASK-471 | **Component conversion** — every app and console file becomes a real `.h`/`.cpp` pair (D0), self-contained headers (SF.11), measured per component | proposed |
| **F** | TASK-472 | `stock/` split into three components; `sd/sdMount`; levelization audit (D0d) | proposed |
| — | TASK-457 | hygiene items (§8) | proposed |
| — | TASK-464 | documentation-reference sweep | proposed |

**Three deviations from D0c/D3/D4 that Stage D took and that need Architect sign-off** (recorded
here against the table row rather than silently, per BP-DOC-2):

1. **`appTable` is a header, not `appTable.cpp`.** D0c and ADR-060 D2 both sketch a `.cpp`. A second
   translation unit is not safe before Stage E, and *not* for the reason ADR-060 D2 recorded — that
   one (the `#ifdef WINAMP_DISPLAY` fork in the table) was already closed by TASK-496/467. Two
   mechanisms, both verified in the source: (a) `audio/audioEngine.h` defines three
   **external-linkage** function bodies (`audio_showstreamtitle` `:83`, `audio_info` `:94`,
   `audio_process_extern` `:209`; `:82` documents the constraint) and both `webRadioApp.h` and
   `localPlayerApp.h` include it, so a TU constructing those two apps duplicates all three at link
   time; (b) silently worse, those headers carry **file-scope statics holding live engine state**
   (`s_icyTitleQueue`, `s_wr_audio`, the `ae*` flags). App methods are implicitly `inline` so the
   linker keeps one copy of each *method*, but each TU compiles its own copy of the *statics* —
   `main.cpp`'s `loop()`/`aeDrainEof()` and an `appTable.cpp`-constructed `WebRadioApp` would then
   read and write different objects, with no link error and no diagnostic. §2's "no link-level
   barrier" conclusion is correct about *classes* and wrong about *these three functions and their
   statics*. Splitting them out is Stage E's work.
2. **The accessor is `shell::state()`, not `shell()`.** `namespace shell` already exists in
   `main.cpp` and owns `setBusy()` / `activeError()` / `activeConnecting()`; a global function and a
   namespace cannot share the name. The namespace is the older and wider-used name.
3. **`currentAppId` is not a `ShellState` member.** D3's own struct sketch omits it while the
   surrounding prose — and §8, which files the item under TASK-457 — says to unify it with
   `previous`. Stage D followed the sketch: 85 references across nine files, and D4 mandates an
   out-of-line accessor, so folding it in adds a function call to the hottest read in the firmware
   for a naming win. Deferred to TASK-457 with the trade recorded.

**Stage E is the one that matters** and the one the first draft of this document quietly omitted.
A and B moved text into headers; that shrank `main.cpp` but produced **no components** — the headers
are not self-contained, they still rely on being included at the right point in `main.cpp`, and the
translation-unit count is unchanged at 8. Measured against D0's table, the tree after B violates
SF.1, SF.11 and Lakos exactly as thoroughly as it did before.

**Order matters: D before E.** Converting an app to a `.cpp` requires its instance to live somewhere
other than `main.cpp` (otherwise the component still cannot be linked independently) and requires
the shell state it touches to be reachable through a declared accessor. D0c and D3 supply both.
Attempting E first means each app conversion drags shell-state plumbing along with it.

**Stage E is per-component, measured, and may grant exceptions.** Each conversion is its own commit:
move method bodies out-of-line, make the header self-contained, build, record the `.map` delta. A
component whose promotion costs more than **256 B** of `dram0_0_seg` stays header-only **with the
measurement recorded in the task** — an evidence-based exception per D0a, not a default.

### 5a. As-built — Stages A and B landed 2026-08-15, VERIFIED 2026-08-16

**Status: committed to local master, reviewed and DUT-verified under TASK-488. Nothing reverted.**
Recorded here so the document matches the tree rather than describing landed work as hypothetical.

**Verification of record (TASK-488, 2026-08-16).** Full id-by-id result table and the `T_488_11`
disposition live in [tasks-archive.md § TASK-488 — full result](../../project/tasks-archive.md#task-488--full-result--pass-criteria-archived-2026-08-22-from-tasks-architecturemd).
The three findings that matter to this design:

- **The moves are pure, provably.** Every one of the 14 moved blocks is byte-identical *and*
  contiguous in its original order; the only added lines are each file's `#pragma once`, includes and
  header comment. `a044f5d`'s three deleted structs had **0** code references.
- **The compiled output is unchanged.** `.text`/`.rodata`/`.data`/`.bss` extents are identical to the
  byte across `a044f5d~1`, `b36f184` and HEAD. The `cyd2usb_winamp_debug` binaries — the build that
  actually compiles the moved SERIAL_DEBUG console — differ by 73 bytes, all build metadata
  (timestamp, injected git hash, app-descriptor SHA256, image checksum). §7a's "include order or
  static init order could still change behaviour" caveat is therefore closed by measurement, not
  argument: there is no machine-code difference for it to hide in.
- **Behaviour holds on hardware.** 39 app switches over 3 cycles with no reset; `init` once /
  `resume` after, on the one app that logs it; taskbar, eject cycle and all 7 Settings sections
  clean; the whole moved console intact — 26 commands and all 108 `get` keys resolving.

Harness: `app/tools/test_task488_partb.py`, driver `run/task488` (supports `DUT_TREE=` for flashing
another checkout, which is how the pre-refactor A/B was run).

| Commit | What | Result |
|---|---|---|
| `a044f5d` | `App` interface → `app.h`; three never-instantiated state structs removed | `appShell.h` 158 → 99 |
| `78caa95` | 7 app classes → `apps/*.h` (1 581 lines) | `main.cpp` 5 880 → 4 299 |
| `b36f184` | `SERIAL_DEBUG` console → `debug/serialConsole/*.h` (2 579 lines) | `main.cpp` 4 299 → **1 726** |

`./run/check` 7/7 after each commit. **No DUT flash; no hardware verification.**

**What landed is scaffolding, not the target.** Measured against D0, the tree after `b36f184` still
violates SF.1, SF.11 and Lakos as thoroughly as before: **zero components were created.** Three gaps,
each now an explicit stage rather than an unstated shortfall:

1. **Headers only, no components.** A `.h` per app, still `#include`d by `main.cpp`, still not
   self-contained, translation-unit count unchanged at 8. `main.cpp` got shorter; the physical design
   did not improve. → **Stage E (TASK-471)**.
2. **The `static XApp g_XApp;` instances stayed in `main.cpp`** — thirteen of them, so the entry point
   is still the composition root by accident. → **Stage D (TASK-456)**, via D0c.
3. **`setup()` has not moved**, so `main.cpp` is 1 726 against a target of under 40. → **Stage C
   (TASK-455)**, via D1a.

The honest summary: A and B were the easy 44 % of the file and left the architectural problem —
no component boundaries, no independent linkage, no self-contained headers — completely intact.

**One deliberate non-move worth recording:** the SD boot mount (`sdProbeBootMount`, `sdReady`) sits
physically adjacent to the SD probes in the old `main.cpp` but is gated on `SD_BOOT_MOUNT`, not
`SERIAL_DEBUG`, and ships in production. It was left behind rather than swept into `debug/` — the
exact mistake ADR-061 D4 exists to prevent. It still wants an `sd/` home.

**Review obligation — DISCHARGED 2026-08-16 (TASK-488).** These were asserted to be pure moves by
their author alone; §7a's recipe has now been performed in full by a second agent, and the assertion
held. TASK-497's owed ≥3-run DUT baseline was taken in the same session. Stage C (TASK-455) is
unblocked.

### 5b. What remains, in descending value

1. `setup()` → `shell/boot.h` (631 lines, verbatim per D1a) — the largest single remaining block.
2. Shell dispatch + `ShellState` → `shell/appShell.cpp` — the first real new `.cpp`, and what lets
   the app instances leave `main.cpp` (D2/D3).
3. `apps/stockApp.h` (770 lines) → `stock/{stockApp,stockList,stockChart,stockHeatmap}.h`.
4. The five surviving per-app state structs out of `appShell.h` into their apps' headers.
5. Per-app `.h`/`.cpp` conversion (deviation 1 above), measured per module against §6.

**TASK-464 is its own task, not a hygiene bullet.** Stages A–D invalidate **308 `main.cpp:NNN`
line-number citations across 49 documentation files**, plus **44 `main.cpp` references in
`feature_inventory.yaml`**. That is too large to ride along inside a stage commit — and it must be
paid **once, at the end of Stage B**, not per-stage, or the same 49 files are rewritten four times.
Stages C/D move far less text and can be absorbed into TASK-464's second pass.

**Stages A+B are proposed as a standalone deliverable; C and D need separate approval** (ADR-060 D7).
A and B deliver most of the readability win at near-zero risk — a pure text move within one TU
presents the compiler with a near-identical blob — and take `main.cpp` from 5 880 to roughly
1 400 lines without introducing any new convention. The cost, the memory risk and the new
state-ownership vocabulary all concentrate in C. The recommendation is to land A+B, live with the
result for a milestone, and decide on C with the benefit felt rather than argued. Paying TASK-464's
documentation cost at the end of B rather than the end of D follows from the same split.

**Stage D is optional and may be partially declined** — if a module's measured flash/DRAM delta is
not worth it, recording that decision is a legitimate outcome, not a failure.

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

**No stage requires Spotify playback or a DUT audio path** — `run/check` plus the DUT navigation pass
in item 4 is the whole gate. (An earlier draft justified this by noting TASK-442 was blocking every
playback-dependent gate. That is no longer true — TASK-442 was root-caused on 2026-08-15 to a Spotify
token refresh burning 43 596 B at boot on a `DISABLE_SPOTIFY` build, and fixed by TASK-447/448. The
independence claim stands on its own merits and never depended on that blocker.)

## 7a. Review recipe — how to check a "pure move" claim without reading 4 000 lines

A move commit asserts that text changed location and nothing else. That is *checkable*, and the
check is cheap. Applies to `a044f5d`, `78caa95`, `b36f184` and to every future stage.

**1. Does git agree it is a move?** Rename detection is the fastest signal — a block that moved
intact scores high similarity, a block that was edited in transit does not:

```sh
git show --stat -M --find-copies-harder <commit>
git show -M -C --summary <commit>          # explicit rename/copy detections
```

**2. Is the moved text byte-identical?** The strongest check, and the one that actually settles it —
extract the block from both sides and diff:

```sh
# example: the 7 app classes, old main.cpp vs the new headers
git show 78caa95~1:app/src/main.cpp | sed -n '243,360p'  > /tmp/before.txt
sed -n '/^class SpotifyApp/,/^};/p' app/src/apps/spotifyApp.h > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt        # empty == verbatim
```

Repeat per block. Empty diffs across all of them is proof, not assertion.

**3. Did the production binary change?** The real question for Stages A/B, since both claim to be
text moves inside one translation unit:

```sh
cd app && ~/.platformio/penv/bin/pio run -e cyd2usb_winamp
# compare .text/.data/.bss extents against the pre-move build
grep -E '^(\.text|\.data|\.bss|\.dram0|\.iram0)' .pio/build/cyd2usb_winamp/*.map
```

Sizes should be identical or near-identical. A meaningful delta means something other than a move
happened. (Exact byte-identity is not expected — `__FILE__`/`__LINE__` in asserts and log macros
shift with line numbers.)

**4. Is the deletion justified?** `a044f5d` removes three structs. The claim is zero references:

```sh
for s in SpotifyAppState ClockAppState AquariumAppState; do
  echo -n "$s: "; git grep -c "\b$s\b" a044f5d~1 -- app/src app/lib | grep -v appShell.h | wc -l
done                                        # 0 each == safe to delete
```

**5. Does the device still behave?** Nothing above proves this. `run/check` covers compile + smoke
only. The outstanding gate is §7 item 4 — a DUT pass over app switching, taskbar cycling, eject and
Settings navigation, which has **not** been run.

## 8. Hygiene items folded in (TASK-457)

- **`run/check` gate count — the drift is real but smaller than first reported, and the script is
  not at fault.** `check_build.sh` is correct and internally consistent: it prints `[1/7]` … `[7/7]`,
  and `:100-101` explicitly documents the historical `[6/6]`-vs-`[7/7]` confusion as already fixed
  (TASK-422 / DEV-7). **The true count is 7.** `appRegistry.h`'s `[6/7]` is therefore *also correct* —
  the registry staleness check really is gate 6 of 7 — and an earlier pass of this document wrongly
  listed it as drifted. Actually wrong, and to be fixed: **`CLAUDE.md:114` and `:129`** (both say 5)
  and **ADR-059 `:19` and `:227`** (both say `6/6`). `CLAUDE.md:129` also carries a stale *list*, not
  just a stale number — it omits the `cyd2usb_player` build and the `gen_mem_layout` gate.
- `appRegistry.h` is included twice in `main.cpp` (`1959`, `3665`). Legitimate X-macro re-inclusion,
  but it should carry a comment saying so at both sites.
- `app/src/main.cpp` (`g_previousAppId`)'s `g_previousAppId` and `appShell.h`'s `currentAppId` are the same concept split
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

1. `main.cpp` contains trimmed includes, `void setup() { bootSequence(); }` and `loop()`, and nothing
   else — **under 300 lines** (~150 expected; ~60 if `loop()`'s body also moves into
   `shell/appShell.cpp`). `setup()`'s 631-line body lives in `shell/boot.h`, moved verbatim (D1a).
2. No app class, app instance, or shell state variable is defined in `main.cpp`.
3. No `SERIAL_DEBUG` command implementation is defined in `main.cpp`.
4. `ShellState` and `appById()` are the sole access paths to shell state; the 72 `extern`s pointing
   into `main.cpp` are gone.
5. §7 items 1–5 green at every stage.
6. ADR-060 records the state-ownership convention (D2/D3/D4) and the D5 caution.

### Stage D — DUT verification, 2026-08-18

Stage D is the first stage where symbol identity cannot substitute for hardware: part 2 relocates nine
shell variables into a TU-static struct behind an out-of-line accessor.

**Battery chosen to hit the relocated members, not a generic run** — busy gate, cooldown, canvas
gesture, taskbar press-anchoring, `previous` (Settings back), and mode transitions:
`T-BUSY-01/01b/02/03/05`, `T-CDWN-01/02/03`, `T147`, `T148`, `T162`–`T166`, `T242`, `T_MA_01`–`03`,
`T_TBFB_01`–`05`, `T_PMT_00`–`03` — **27 passed, 0 failed, 1 skipped** on `cyd2usb_winamp_debug`.
The skip is `T_MA_03` ("Spotify not rendering"), the standing TASK-243 403, not a Stage D effect.

Leg B via `run/player-gate`: `T_PMT_00`/`03`/`04` and `T_PLR_25_playback` all PASS.

**`T_SRC_05`/`T_SRC_06` and D9's ≥3-run baseline remain owed** — this battery is targeted evidence,
not a behaviour-neutrality baseline, and it should not be recorded as one.
