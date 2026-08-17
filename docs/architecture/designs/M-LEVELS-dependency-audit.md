# Design — M-LEVELS: auditing the dependency graph ADR-060 D2a asserts

> Owner: Architect
> Status: **audited** — 2026-08-16 (was: skeleton, same day)
> Tracked-as: TASK-485
> Governs: [ADR-060](../decisions/ADR-060.md) D2a / D2b
> Related: [M-TESTARCH §2c](M-TESTARCH-test-architecture.md) — test coverage per level
> Supersedes: the skeleton. **OQ1 is answered**: the graph has now been generated.

**OQ1 said this should be the first action. It was, and it changes the picture.** Every "Known" item
in the skeleton was asserted from reading; this document replaces them with a measurement. The
headline: **D2a is broadly correct, the raw violation count is misleading, and only two edges are
genuine structural problems.**

Method: parse every `#include "…"` in `app/src` (74 files), resolve to a file, assign each file a
level, count edges. Reproducible; the script is throwaway analysis, not a committed tool (it should
become one — see §5).

---

## 1. The measured graph

```
  from → to     count
  L0 → L0           2
  L0 → L1           1   ← upward
  L1 → L0          18
  L1 → L1          43
  L1 → L2          13   ← upward
  L2 → L0           8
  L2 → L1          13
  L2 → L2          19
  L2 → L3          13   ← upward
  L3 → L0           9
  L3 → L1          35
  L3 → L2          17
```

| Level | lines | share |
|---|---:|---:|
| L0 `util/ gen/ touch/ app.h touchPhase.h` | 395–560 | 2 % |
| L1 `audio/ player/ winamp/ settings/ taskbar/ dataTask spotifyTask settingsStorage wifiDiag` | **15 289** | **52 %** |
| L2 `appShell logging screenLog backlightFlow ledFlow debug/` | 5 272 | 18 % |
| L3 `apps/ + 6 app headers outside it` | 9 067 | 31 % |

**27 raw upward edges. Resolved:**

| Class | Count | Verdict |
|---|---:|---|
| `main.cpp` → every app header | **13** | **Not a violation — it is the composition root.** See §2 |
| `logSink.h` / `logDecode.h` / `logHeartbeat.h` ← L1 | **10** | **Mis-levelled.** Logging is an L0 concern. See §3 |
| `backlightFlow.h` / `ledFlow.h` ← `settings/` | **2** | Same class as logging — a "flow" is L1, not L2 |
| `taskbar/taskbar.h` → `appShell.h` | **1** | **Genuine** |
| `util/timeFmt.h` → `settingsStorage.h` | **1** | **Genuine** — and the only L0→L1 edge in the codebase |

*(The L0 figure varies with where `perf.h`/`secret.h`/`planeRadarConfig.h` are assigned; an independent re-measure put it at 395. The conclusion is unaffected.)*

**Two genuine violations out of 27.** D2a's asserted graph survives the audit far better than the
skeleton feared. The value of the audit is not the violations — it is the two classification errors
underneath them, which were invisible without a graph.

## 2. D2a is missing a level: the composition root

Thirteen of the 27 upward edges are `main.cpp` including every app header. That is not a violation —
**it is what a composition root does**, and D2a has no level for it, so the audit is forced to score
it as one.

`main.cpp` sits *above* L3: it constructs the apps, wires the registry, owns `setup()`/`loop()`. Every
other L2 file (`appShell`, logging, `screenLog`) is genuinely below the apps. Lumping them together
means the level model cannot express the one file whose whole job is to depend on everything.

**Recommend: ADR-060 D2a gains an explicit composition-root level (L4 / `root`), with one rule —
exactly one file may live there, and nothing may include it.** Re-scored that way, `main.cpp`'s 13
edges disappear from the violation list and L2 drops from 5 272 to 3 559 lines, which is a truer
picture of the shell.

This also makes D2a *checkable*: today a cycle checker would report 13 false positives on the entry
point and be switched off within a week.

## 3. Logging is mis-levelled, and it accounts for 10 of the 14 remaining edges

`logSink.h`, `logDecode.h` and `logHeartbeat.h` are classified L2 but are included by L1 throughout:
`audio/audioEngine.h`, `dataTaskStorage.cpp`, `player/fileBrowser.h`, `player/m3u.h`,
`settings/systemSection.h`, `settings/appsSection.h`, `spotifyTaskStorage.cpp`,
`winamp/pleditView.h`.

**Logging is a level-0 concern in every layered design, for the obvious reason: everything logs.**
Nothing about `logSink.h` depends upward; it was simply filed with the shell because that is where it
was written. Reclassify to L0 and 10 edges resolve with **zero code change** — this is a one-line
correction to D2a, not a refactor.

Same argument, smaller: `backlightFlow.h` and `ledFlow.h` are consumed by `settings/` sections. They
are L1 device-flows, not L2 shell.

## 4. The two genuine violations

- **`taskbar/taskbar.h` → `appShell.h` (L1 → L2).** The taskbar needs `AppId` and shell dispatch
  state. Fix is the standard one: the enum and the dispatch interface belong lower — `AppId` is
  already in `appShell.h` alongside three unrelated concerns, and `app.h` was extracted from exactly
  that file for exactly this reason (M-SRCLAYOUT). Extract `AppId` next, and the edge goes away.
- **`util/timeFmt.h` → `settingsStorage.h` (L0 → L1).** The only L0→L1 edge in the codebase, and it
  is the **third independent confirmation** of the same finding: `timeFmt` is also the one `util/`
  file that is not host-buildable (M-TESTARCH §3) and the one that pulls `<Arduino.h>`. One file, one
  dependency, three separate audits. It formats a time according to a persisted setting — the fix is
  to pass the format in rather than read the global.

**Both are small, both are pure wins, and both unblock something else** (a taskbar that can be tested
below the shell; a `util/` that is fully host-clean).

## 5. OQ4 — yes, gate it, and the gate is now cheap

The audit script is ~40 lines of Python over `#include` lines. As a `run/check` step it would:

1. Assert no upward edge except from the composition root.
2. Assert no cycles (**OQ2 — still unanswered**; the graph is built but a cycle pass was not run.
   `winamp/` ↔ player-mode is the suspected one and is the obvious next measurement).
3. Carry a dated allowlist for the two genuine violations in §4 until they are fixed.

Land it **red with the two allowlisted**, per the programme's standing rule (M-QUALITY §4). It is the
same shape as `check_settings_wiring.py` — enumerate from source, assert a contract, allowlist the
documented exceptions — which is already green and already wired.

## 6. Still open

- **OQ2 — are there cycles?** Graph is generated; the cycle pass was not run. Cheap follow-up.
- **OQ3 — is `settings/` L1 or L3?** The audit sharpens but does not settle it. `settings/` is
  **5 451 lines, the largest L1 directory**, and its edges split cleanly: shared widgets
  (`keyboardWidget`, `sliderWidget`, `settingsWidgets`) look L1; the per-app sections
  (`appsSection` 1 342 lines, `ledSection`, `displaySection`) reach into app-level and flow concerns
  and look L3. **The measured evidence now supports the split M-SRCLAYOUT OQ2 proposed** — but which
  side `settingsSection.h` itself lands on is undecided.
- **Does `app/lib/` (D2b, L−1) hold?** Not audited — the vendored tree was out of scope for this pass.
