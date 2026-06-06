# M-APP-REGISTRY — Developer Review

> Reviewer: Developer  
> Date: 2026-06-06  
> Design doc: [M-APP-REGISTRY.md](M-APP-REGISTRY.md)  
> Status: **review complete**

---

## Summary verdict

The design is sound and implementable. Five of the seven issues raised below are
straight accepts or require only minor clarifications in the implementation
notes. Two items need explicit design decisions before the PR lands: the
`static` linkage clash with X-macro forward-declarations (point 6), and the
serial protocol integer `id` field emitted by `cmdGet`/`cmdSwitchApp` (point 7
cross-reference).

---

## Developer Review

### 1. g_SpotifyApp rename (Option A) — sed scope

**Finding: Accept with scoped sed, not a blanket pass.**

All nine app objects are defined `static` inside `main.cpp` and are referenced
**only** in `main.cpp`. There are zero cross-file references.

```
grep result (app/src/ *.h *.cpp, excluding main.cpp): 0 hits
```

Occurrences inside `main.cpp`:

| Object | Lines |
|---|---|
| `g_spotifyApp` | 228 (def), 1507 |
| `g_clockApp` | 300 (def), 1508 |
| `g_weatherApp` | 469 (def), 1509 |
| `g_cryptoApp` | 551 (def), 1510 |
| `g_matrixApp` | 372 (def), 1511 |
| `g_lifeApp` | 675 (def), 1512 |
| `g_settingsApp` | 824 (def), 826 (settingsDbgGet wrapper), 1513 |
| `g_stockApp` | 1496 (def), 1497 (stockDbgGet wrapper), 1498 (stockDbgSet wrapper), 1514 |
| `g_aquariumApp` | 1501 (def), 1515 |

Total: 21 occurrences, all in `main.cpp`.

**Partial-match risk:** `g_settingsApp` is a strict substring of nothing else.
`g_stockApp` appears near `stockDbgGet`/`stockDbgSet` but those are distinct
identifiers — a word-boundary sed (`\bg_stockApp\b`) is safe. The class names
`SpotifyApp`, `ClockApp`, etc. are uppercase-first already and will not be
touched by a rename of the lowercase instance names.

One concrete risk: the design renames the `static` definitions too. The X-macro
forward-declaration expansion produces `extern App g_SpotifyApp;` — but
`extern` and `static` have conflicting linkage (see point 6). The rename is
safe only after that issue is resolved. Scope the sed to `main.cpp` only, using
whole-word matching (`sed -i 's/\bg_spotifyApp\b/g_SpotifyApp/g' app/src/main.cpp`
etc.); do not run it over the whole tree.

**Recommendation: Accept, word-boundary sed on main.cpp only, after point 6 is
resolved.**

---

### 2. g_appLaunched array — persistent storage risk on app removal

**Finding: No risk. AppId is not persisted. Accept.**

A full audit of all SPIFFS writes confirms the settings JSON
(`settingsStorage.cpp:220`) does not store any AppId value. The JSON keys are
string-typed setting domains (`"time"`, `"stock"`, `"crypto"`, etc.) — never an
integer app slot or `currentAppId`.

`g_appLaunched` (`appShell.h:124`, `main.cpp:179`) is `bool
g_appLaunched[(int)AppId::COUNT]` — a transient RAM array, zero-initialised at
boot, never written to SPIFFS or NVS. It is indexed by `(int)AppId::X` at
`main.cpp:1555` and `main.cpp:1801`.

The serial debug command `get appId` (`main.cpp:2099-2101`) serialises
`(int)currentAppId` as `"id"` and the name string as `"name"`. The test suite
receives this over UART at runtime — it is not persisted across flashes. The
integer `id` field is read-back by tests (see separate point 7 below).

If an app is removed mid-list, `g_appLaunched` shrinks correctly (COUNT
decrements), and no SPIFFS data is invalidated. The only SPIFFS-persisted state
is app-specific settings (tickers, coins, etc.) keyed by domain name, which are
immune to reordering.

**Recommendation: Accept.**

---

### 3. appsSection.h — does configurable_apps.h actually simplify it?

**Finding: Partial simplification only. The title/list/row-count boilerplate
goes away, but the per-app repaint and cycle methods must stay. Clarify scope in
the design.**

Current `appsSection.h` has two kinds of code:

**A. Registry-driven boilerplate** (directly eliminated by the generated header):
- `title()` — `kNames[]` at lines 7–8 and 40 (`"Stock","Crypto","Aquarium","Matrix","Life"`).
- `_repaintAppList()` — iterates `kNames[]`, hardcoded count `5` (lines 40–43).
- `handleInput()` row guard `row < 5` (line 29).
- `_sub` switch in `_repaintAppRows()` and `_handleAppTap()` (lines 46–52, 101–108).

The generated `kConfigurableApps[]` struct array (name + AppId) can replace all
of the above with a loop over the table. This is a genuine win: the `title()`
ternary, the two `kNames[]` duplicates, the `< 5` guard, and both `switch
(_sub)` dispatches collapse into index-based lookups.

**B. Per-app settings content** (cannot be table-driven without a bigger design
change):
- `_repaintStock()`, `_repaintCrypto()`, `_repaintAquarium()`, `_repaintMatrix()`,
  `_repaintLife()` — each reads distinct fields from `g_settings` with
  app-specific labels, pools, and formatting logic (lines 55–98).
- `_cycleStock()`, `_cycleCrypto()`, `_cycleAquarium()`, `_cycleMatrix()`,
  `_cycleLife()` — each encodes app-specific cycling logic with different pool
  arrays (lines 111–168).

These 10 methods account for roughly 100 of the 183 lines and have no common
structure that a generated table could drive. They stay as-is.

The design says "the switch dispatch on `_sub` becomes a loop over the generated
table" — this is accurate for navigation/dispatch, but the design doc should
explicitly call out that the 10 repaint/cycle methods remain unchanged. A
developer reading the design could otherwise expect a larger simplification than
is actually delivered.

**Recommendation: Accept the generated-header approach, but add a note to the
design doc clarifying that `_repaintX()` / `_cycleX()` methods are out of
scope.**

---

### 4. #include inside a function body in taskbar.h

**Finding: Legal and safe on Xtensa GCC. Accept.**

```cpp
inline void renderTaskbar(...) {
    #define APP_X(Name, icon, cfg) icon,
    const char icons[] = {
    #include "appRegistry.h"
    };
    #undef APP_X
```

`#include` is a preprocessor directive and is legal anywhere in a translation
unit, including inside a function body. Xtensa GCC (the toolchain used by
esp-idf / PlatformIO ESP32) honours this. Arduino-ESP32 (used here via
`platform = espressif32@6.9.0`) compiles with the same Xtensa GCC. No
compile-time issue.

Static analysis tools (clang-tidy, cppcheck) may warn about `#include` inside a
function with rules like `[readability-include-inside-function]`. These are not
enforced in this project's build pipeline — `check_build.sh` only runs PIO
builds and a hash check, so no gate will fire.

There is a minor code-smell tradeoff: it is harder to search for "where is
`appRegistry.h` included?" if `#include` appears deep inside a function. Given
the project already uses multiple X-macro sites, this is acceptable.

**Recommendation: Accept. Note in the design that static analysis tools may
warn; suppress at the call site if linting is ever added.**

---

### 5. app/gen/ directory — generated vs. hand-maintained; gitignore status

**Finding: Generated files ARE checked into git in app/gen/. configurable_apps.h
would fit but must be added explicitly to golden.sha256. Accept with required
follow-up action.**

`git ls-files app/gen/` shows the following files are tracked:

```
app/gen/golden.sha256
app/gen/shell_layout.h
app/gen/skin_assets.c
app/gen/skin_layout.h
app/gen/skin_preview_animated.gif
app/gen/skin_preview_wave.gif
app/gen/vis_atlas.c  vis_atlas.h  vis_atlas.sha256
app/gen/wave_atlas.c  wave_atlas.h  wave_atlas.sha256
```

The `.gitignore` (`app/.gitignore`) only excludes review artefacts
(`skin_preview.png`, `skin_hitzones.png`, `origin_audit.png`, `composite/`,
`*.npy`). All `.h` and `.c` generated files are checked in.

`golden.sha256` currently covers `skin_assets.c`, `skin_layout.h`, and
`shell_layout.h`. It does **not** auto-cover new files. The design doc says
"`check_build.sh` can optionally verify the generated files are not stale" — but
the current `check_build.sh` only verifies existing golden entries via `sha256sum
-c`. To gate staleness of `configurable_apps.h`, either:

- Add it to `golden.sha256`, or
- Extend `check_build.sh` with an explicit regenerate-and-diff step.

Neither is specified in the design. The staleness guard described in the doc
("a comment block at the top of `appRegistry.h` reminds the developer to
re-run") is a convention, not an automated check.

**Recommendation: Accept the `app/gen/` location. Before closing the
implementation task, add `configurable_apps.h` to `golden.sha256` or extend
`check_build.sh` step [3/4] to cover it. This must be a required acceptance
criterion, not optional.**

---

### 6. Forward declarations in main.cpp — static linkage clash

**Finding: The X-macro forward-declaration approach as written is broken.
Requires design modification.**

All nine app objects are defined with `static` storage class in `main.cpp`:

```cpp
// main.cpp:228, 300, 372, 469, 551, 675, 824, 1496, 1501
static SpotifyApp  g_spotifyApp;
static ClockApp    g_clockApp;
// ...
static StockApp    g_stockApp;
static AquariumApp g_aquariumApp;
```

The proposed X-macro expansion is:

```cpp
#define APP_X(Name, icon, cfg) extern App g_##Name##App;
#include "appRegistry.h"
#undef APP_X
```

This generates `extern App g_SpotifyApp;` etc. An `extern` declaration for a
name that was defined `static` in the same translation unit is a **constraint
violation** in C and is ill-formed in C++. GCC will produce a diagnostic
(`error: 'g_SpotifyApp' was declared 'extern' and later 'static'` or similar,
depending on declaration order). On some compilers the error fires on the
`extern` line if it appears before the `static` definition; on others it fires
at the `static` definition site.

Additionally, `extern App g_SpotifyApp;` declares a variable of base type `App`
(an abstract class with pure virtuals), not `SpotifyApp`. This is a separate
type mismatch — the forward declaration type must match the definition type, or
use a base-class pointer, not a base-class value declaration.

**The real purpose of the X-macro block is to populate `g_apps[]`, not to
provide cross-TU visibility.** Since all objects are defined in the same file,
no `extern` forward declaration is needed at all. The correct implementation is:

```cpp
// In main.cpp, at the g_apps[] initialiser, after all class definitions:
#ifdef WINAMP_DISPLAY
App* g_apps[(int)AppId::COUNT] = {
#define APP_X(Name, icon, cfg) &g_##Name##App,
#include "appRegistry.h"
#undef APP_X
};
#endif
```

This works without any separate forward-declaration block — the `static`
instances (`g_spotifyApp` etc., renamed to `g_SpotifyApp` etc. post-Option-A)
are already visible at the point where `g_apps[]` is initialised (they are all
defined above line 1506 in `main.cpp`). Delete the extern block from the design.

The `#else` branch for non-WINAMP_DISPLAY currently uses `App* g_apps[...] = {}` —
this branch also needs the X-macro treatment or a separate explicit count update
if the array size must track COUNT. Given the non-WINAMP path is never deployed,
minimal change is acceptable here.

**Recommendation: Modify — remove the forward-declaration X-macro block from the
design. The dispatch table initialiser X-macro is sufficient and correct on its
own.**

---

### 7. Enum value shift on disable — serial protocol integer id field

**Finding: The integer `id` field in the `get appId` and `switchApp` serial
responses creates a latent breakage path if apps are disabled or reordered.
The design acknowledges this for the debug tool but misses one concrete coupling
in the test suite.**

Settings/SPIFFS storage: confirmed clean (see point 2). No SPIFFS or NVS writes
encode AppId.

**Serial protocol exposure:** `cmdGet` (`main.cpp:2099-2101`) emits:

```json
{"ok":true,"cmd":"get","var":"appId","id":3,"name":"Crypto","last":true}
```

`cmdSwitchApp` (`main.cpp:2183`) emits:

```json
{"ok":true,"cmd":"switchApp","id":3}
```

And it accepts numeric arguments: `switchApp 3` (`main.cpp:2175-2183`).

**Test suite coupling:**

- `test_tls_yield_reliability.py` defines `_STOCK_APP_ID = 7`, `_CRYPTO_APP_ID
  = 3`, `_WEATHER_APP_ID = 2` as top-level constants (lines 50-52) and sends
  `switchApp 7` / `switchApp 3` / `switchApp 2` to the DUT. These are the exact
  integer constants that would shift on app removal.
- `run_serialdbg_tests.py` defines `_STOCK_APP_ID = 7` (line 2040),
  `_SPOTIFY_APP_ID = 0` (2806), `_CLOCK_APP_ID = 1` (2807), `_SETTINGS_APP_ID
  = 6` (4426), `_CRYPTO_APP_ID = 3` (4427). The `PASSIVE_APPS` list (line
  2965) encodes all six non-Spotify passive apps as `(name, integer_id)` tuples
  — including `("Aquarium", 8)`.
- `_TB_N = 8` (line 3768) is `AppId::COUNT - 1`, used in T163-T166 taskbar
  scroll modular arithmetic.

The design's migration to `APP_SLOT["Stock"]` etc. correctly addresses this for
the test constants. However, the design does **not** address the hardcoded
integer in the `get appId` response (`"id":%d`) or the integer-only `switchApp
<N>` command. After the refactor:

- If a developer disables Crypto, `_STOCK_APP_ID` becomes 6, not 7. The Python
  tests will be regenerated correctly via `app_ids_gen.py`. Fine.
- But the DUT must also be re-flashed with the new build — if a developer
  sends `switchApp 7` to an old firmware and `7` is now Aquarium instead of
  Stock, silent mismatch occurs. This is the "acceptable for a dev tool"
  disclaimer in the design, which is reasonable.
- The `_parse_switchapp_ack` function in `test_tls_yield_reliability.py`
  (`line 73-80`) does **not** check the `id` field in the ack — it only checks
  `cmd == "switchApp" and ok is True`. So no integer id is compared in the ack
  path; the tests validate by subsequently calling `get appId` and comparing
  `"name"`. This is robust to reordering.
- `get appId` responses: the `"name"` field is what all tests actually assert
  against (e.g., `r.get("name") == "Stock"`). The `"id"` integer field is
  emitted but never read by the test suite. Confirmed: `grep '"id"'` in both
  test files returns 0 hits.

**The `cmdGet` appId name-table** (`main.cpp:2089-2098`) is a manual chain of
ternaries hardcoded to each `AppId::` enum value. After the X-macro refactor
this becomes another drift point. The design doc does not mention it. It should
be replaced (or at minimum noted) — e.g., a small `kAppNames[]` array indexed by
`(int)AppId` generated from the macro would eliminate this chain.

**Recommendation: Accept the design's approach of migrating `_*_APP_ID`
constants to `APP_SLOT[]` lookups. Add a required implementation note: the
`cmdGet appId` name-chain (`main.cpp:2089-2098`) must also be X-macro-driven or
table-indexed to prevent it from drifting after app removal.**

---

## Required implementation actions before merge

1. **Remove `extern App g_##Name##App;` forward-declaration block** from the
   implementation. The X-macro is only needed for the `g_apps[]` array
   initialiser. (Point 6 — blocks PR if not addressed.)

2. **Do not declare app objects as `extern`** — they are `static` and must
   remain so. The rename from `g_spotifyApp` → `g_SpotifyApp` etc. renames the
   `static` definition only; no linkage change. (Point 1 / 6 combined.)

3. **Add `configurable_apps.h` to `golden.sha256`** or extend
   `check_build.sh` check [3/4] to detect stale generated files. (Point 5 —
   required gate for the "run on demand" workflow to be reliable.)

4. **Replace `cmdGet appId` name-chain** with a table or X-macro to prevent it
   from drifting when apps are disabled. (Point 7 — medium priority; not a
   correctness blocker today, but will become one on first disable.)

5. **Clarify in the design doc** that `_repaintX()` / `_cycleX()` methods in
   `appsSection.h` are out of scope for the generated-header approach. (Point 3
   — documentation only, no code impact.)
