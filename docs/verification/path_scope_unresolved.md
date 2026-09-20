# `--scope <path>` files with no truthful scope — the R-PATHSCOPE ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_test_meta.py` ·
> Opened **2026-09-20** by TASK-612 · Background: `--scope <path>`
> (`suite/serialdbg/_meta.scope_from_path()`, M-TESTARCH §13.4) resolved only
> 65/143 `app/src/**/*.{cpp,h,c}` files (B-9), and two of its directory
> prefixes named directories that never existed (B-10). TASK-612 fixed the
> matcher (path-component-aware, no more filename-prefix accidents) and added
> real coverage for `app/src/player`, `app/src/settings`, `app/src/stock`'s
> residue, `app/src/shell/taskbar.{cpp,h}`, and four specific files
> (`spotifyTask.h`, `spotifyTaskStorage.cpp`, `planeRadarConfig.h`,
> `settingsCalStorage.cpp`) — bringing coverage to 90/143.

## What this file is

The 53 files below still resolve to nothing, on purpose. Each one was checked (by grepping every
`#include`/reference site, not assumed) against the danger TASK-612 was warned about: **mapping a
directory to a scope whose id set does not actually exercise that code silently runs the WRONG
tests and reports confidence.** Every row here is either

* **shared/cross-cutting** — included by two or more unrelated app families, so no single scope's
  id set is a truthful sole owner (a regression would surface as a symptom in whichever app called
  it, not as an attribution to this file), or
* **generated** (`app/src/gen/**`) — owned by its bake/gen script and gated by `run/check`'s
  `golden.sha256`/staleness checks, not by any serialdbg id, or
* **untested today** — no id in the suite exercises the file at all (backlight/LED chrome, WiFi
  diagnostics, misc scaffolding), or
* **the entry point** (`main.cpp`) — legitimately touches every scope, so naming one would be a
  false attribution, not a fix.

A row here is **not** an amnesty for "nobody got to it yet" — `check_test_meta.py` fails if a file
resolves and still has a row (stale — delete it), or if a currently-unresolved
`app/src/**/*.{cpp,h,c}` file has no row (undocumented residue — add one, or fix `_PATH_SCOPES`
instead). Keyed on the **path alone**, no wildcards, same convention as every other exception
ledger in this tree (`docs/verification/primitive_coverage_exceptions.md` et al.).

## Ledger

| path | why | owner | since |
|---|---|---|---|
| `app/src/audio/audioEngine.cpp` | audioEngine.{cpp,h} is shared by LocalPlayer and WebRadio (also boot/debug, grepped); no single scope is a truthful sole owner. | TASK-612 | 2026-09-20 |
| `app/src/audio/audioEngine.h` | audioEngine.{cpp,h} is shared by LocalPlayer and WebRadio (also boot/debug, grepped); no single scope is a truthful sole owner. | TASK-612 | 2026-09-20 |
| `app/src/backlightFlow.h` | Device-wide backlight/LED chrome; no id in the suite exercises either today. | TASK-612 | 2026-09-20 |
| `app/src/dataTaskCerts.h` | Shared fetch-task infra used by nearly every app family (grepped: 10+ include sites); the one cross-app dataTask id (T_X07_01) is `shell`-scoped for its OWN stated reason (shell.py's docstring), not because this file is shell's. | TASK-612 | 2026-09-20 |
| `app/src/dataTask.h` | Shared fetch-task infra used by nearly every app family (grepped: 10+ include sites); the one cross-app dataTask id (T_X07_01) is `shell`-scoped for its OWN stated reason (shell.py's docstring), not because this file is shell's. | TASK-612 | 2026-09-20 |
| `app/src/dataTaskStorage.cpp` | Shared fetch-task infra used by nearly every app family (grepped: 10+ include sites); the one cross-app dataTask id (T_X07_01) is `shell`-scoped for its OWN stated reason (shell.py's docstring), not because this file is shell's. | TASK-612 | 2026-09-20 |
| `app/src/display/tft.cpp` | Shared TFT driver wrapper used by every app; cross-cutting. | TASK-612 | 2026-09-20 |
| `app/src/display/tft.h` | Shared TFT driver wrapper used by every app; cross-cutting. | TASK-612 | 2026-09-20 |
| `app/src/gen/configurable_apps.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/countries.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/mem_layout.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/nixie_glyphs.cpp` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/nixie_glyphs.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/planeradar_airports.c` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/planeradar_airports.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/shell_layout.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/skin_assets.c` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/skin_layout.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/taskbar_icons.cpp` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/taskbar_icons.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/teletext_layout.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/vis_atlas.c` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/vis_atlas.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/wave_atlas.c` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/gen/wave_atlas.h` | Generated file — owned by its bake/gen script and gated by `golden.sha256`/staleness checks in `run/check`, not by a serialdbg id; no id's subject is the generator's output. | TASK-612 | 2026-09-20 |
| `app/src/ledFlow.h` | Device-wide backlight/LED chrome; no id in the suite exercises either today. | TASK-612 | 2026-09-20 |
| `app/src/logDecode.h` | Logging/diagnostics infra included by nearly every app family (grepped); no scope owns it specifically. | TASK-612 | 2026-09-20 |
| `app/src/logHeartbeat.h` | Logging/diagnostics infra included by nearly every app family (grepped); no scope owns it specifically. | TASK-612 | 2026-09-20 |
| `app/src/logServer.h` | Logging/diagnostics infra included by nearly every app family (grepped); no scope owns it specifically. | TASK-612 | 2026-09-20 |
| `app/src/logSink.h` | Logging/diagnostics infra included by nearly every app family (grepped); no scope owns it specifically. | TASK-612 | 2026-09-20 |
| `app/src/logSinkStorage.cpp` | Logging/diagnostics infra included by nearly every app family (grepped); no scope owns it specifically. | TASK-612 | 2026-09-20 |
| `app/src/main.cpp` | Entry point wiring every subsystem together — legitimately touches every scope (per TASK-612's own ruling 4), so no single scope is a truthful attribution rather than an invented one. | TASK-612 | 2026-09-20 |
| `app/src/mem/arena/mb_arena.cpp` | Shared allocator arena used by every fetch-capable app; cross-cutting infra, not one app's code. | TASK-612 | 2026-09-20 |
| `app/src/mem/arena/mb_arena.h` | Shared allocator arena used by every fetch-capable app; cross-cutting infra, not one app's code. | TASK-612 | 2026-09-20 |
| `app/src/perf.h` | Generic utility/secrets scaffolding; not app-specific and untested by any id. | TASK-612 | 2026-09-20 |
| `app/src/screenLog.h` | Logging/diagnostics infra included by nearly every app family (grepped); no scope owns it specifically. | TASK-612 | 2026-09-20 |
| `app/src/sd/sdMount.cpp` | SD mount lifecycle shared by boot, main.cpp and the debug console (grepped); not owned by one app or scope. | TASK-612 | 2026-09-20 |
| `app/src/sd/sdMount.h` | SD mount lifecycle shared by boot, main.cpp and the debug console (grepped); not owned by one app or scope. | TASK-612 | 2026-09-20 |
| `app/src/secret.h` | Generic utility/secrets scaffolding; not app-specific and untested by any id. | TASK-612 | 2026-09-20 |
| `app/src/settingsStorage.cpp` | Generic per-app settings persistence used by every app (grepped: 12+ include sites, including non-Settings apps) — broader than the Settings app's own 6 nav ids, so mapping it to `Settings` would be a false attribution, not a fix. | TASK-612 | 2026-09-20 |
| `app/src/settingsStorage.h` | Generic per-app settings persistence used by every app (grepped: 12+ include sites, including non-Settings apps) — broader than the Settings app's own 6 nav ids, so mapping it to `Settings` would be a false attribution, not a fix. | TASK-612 | 2026-09-20 |
| `app/src/touch/hitbox.h` | Shared touch-hit-testing helper (grepped includes: Settings widgets, winamp PLEDIT, WebRadio); no single scope owns it. | TASK-612 | 2026-09-20 |
| `app/src/touchPhase.h` | Shared touch-phase state machine used by LocalPlayer, Settings and Spotify/winamp (grepped); cross-cutting. | TASK-612 | 2026-09-20 |
| `app/src/touch/scrollTuning.h` | Shared touch-hit-testing helper (grepped includes: Settings widgets, winamp PLEDIT, WebRadio); no single scope owns it. | TASK-612 | 2026-09-20 |
| `app/src/ui/palette.h` | Shared colour/style constants used across apps; cross-cutting. | TASK-612 | 2026-09-20 |
| `app/src/util/asciiFold.h` | Cross-cutting utility (grepped: included by 3+ unrelated app families); a regression here would surface as a symptom in whichever app happened to call it, never as this file's own attribution. | TASK-612 | 2026-09-20 |
| `app/src/util/mathUtil.cpp` | Cross-cutting utility (grepped: included by 3+ unrelated app families); a regression here would surface as a symptom in whichever app happened to call it, never as this file's own attribution. | TASK-612 | 2026-09-20 |
| `app/src/util/mathUtil.h` | Cross-cutting utility (grepped: included by 3+ unrelated app families); a regression here would surface as a symptom in whichever app happened to call it, never as this file's own attribution. | TASK-612 | 2026-09-20 |
| `app/src/util/textFit.h` | Cross-cutting utility (grepped: included by 3+ unrelated app families); a regression here would surface as a symptom in whichever app happened to call it, never as this file's own attribution. | TASK-612 | 2026-09-20 |
| `app/src/util/tftViewportRepair.h` | Cross-cutting utility (grepped: included by 3+ unrelated app families); a regression here would surface as a symptom in whichever app happened to call it, never as this file's own attribution. | TASK-612 | 2026-09-20 |
| `app/src/util/timeFmt.h` | Cross-cutting utility (grepped: included by 3+ unrelated app families); a regression here would surface as a symptom in whichever app happened to call it, never as this file's own attribution. | TASK-612 | 2026-09-20 |
| `app/src/wifiDiag.cpp` | WiFi diagnostics surface; no serialdbg id exercises it today. | TASK-612 | 2026-09-20 |
| `app/src/wifiDiag.h` | WiFi diagnostics surface; no serialdbg id exercises it today. | TASK-612 | 2026-09-20 |

## How a row leaves

Either the file gets a genuine single-scope owner (a new app splits shared code out, or a new id
starts exercising it) and `_PATH_SCOPES` grows a real entry for it — delete the row in the same
change — or the file is deleted outright. The gate fails on a row that no longer resolves as
unresolved (stale) exactly as it fails on an unresolved file with no row (undocumented) — this
ledger only shrinks.
