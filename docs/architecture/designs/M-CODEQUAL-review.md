# Review — M-CODEQUAL, plus the axis it does not cover

> Reviewer: **Architect**
> Status: **review** — 2026-08-16
> Reviews: [M-CODEQUAL-duplication-and-abstraction.md](M-CODEQUAL-duplication-and-abstraction.md) (proposed, 2026-08-15)
> Tracked-as: TASK-458 … TASK-463 (all OPEN/MIXED as of this review — **nothing has landed**)
> Adds: **C7 – C9**, on the programming-paradigm axis M-CODEQUAL does not address

**Brief.** Review the codebase on good practice, duplication, magic constants, and modern paradigm
use. M-CODEQUAL already covers the middle two well and is **upheld** — this review re-measures it
rather than repeating it (§1), records what the codebase does *well* so the findings are calibrated
(§2), corrects three naive metrics that would otherwise become bad findings (§3), and adds the fourth
axis, which is where the largest structural finding in the codebase sits (§4).

Scope: `app/src` — **66 headers / 24 426 lines, 8 `.cpp` / 5 762 lines**. Re-measured 2026-08-16.

---

## 1. M-CODEQUAL re-measured — upheld, nothing landed

| Item | Status | Re-measured |
|---|---|---|
| C1 fetch skeleton | **stands**, as corrected by @Developer (two skeletons, not one) | the buffered/streaming split is real; keep C1 v1 scoped to the four buffered fetches |
| C2 RAII guards | **stands — still the highest-value item** | TASK-458 OPEN. Zero `= delete` in the entire tree, so `TlsYieldGuard` would be the codebase's first non-copyable type (see C9) |
| C3 table dispatch | **stands** | `cmdGet` 622 + `cmdSet` 739 = 1 361 lines, 68 keys. Grew ~50 lines since the doc was written |
| C4 debug seam | **stands** | policy, not code |
| C5 geometry constants | **stands, unlanded** | `T_CQ_03`'s acceptance grep returns **123 hits** outside `app/src/gen/`. The gate is well-formed and currently red |
| C6 palette | **stands, unlanded** | `0x4208`/`0x2104` at **22 sites across 9 files** |

M-CODEQUAL's **§3 counting note is the most valuable paragraph in it** and should be promoted to a
best practice. Every naive grep in this domain over-reports; §3 of this review is three more instances.

## 2. What the codebase does well — recorded so the findings are calibrated

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

## 3. Three metrics that look like findings and are not

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

## 4. New findings — the paradigm axis

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

## 5. Duplication not covered by C1 — checked, and small

C1 covers `dataTaskStorage.cpp`'s fetch layer. The **app** layer was checked separately, since that
is where duplication would be expected next:

`apps/weatherApp.h` (146 lines) and `apps/cryptoApp.h` (153 lines) are structurally near-identical —
same interval-check → `enqueue` → `poll` → render shape, same `isConnecting`/`hasError` overrides
over a `s_*DataReady` flag. Two files, ~300 lines, differing in render body.

**Verdict: leave it.** Two instances is not a pattern, the shared part is ~30 lines of control flow,
and an abstraction over two callers with different render bodies costs more than it saves. Recorded
so the next reviewer does not re-derive it. If a third timer-driven fetch app appears, revisit.

Also checked and **clean**: every app that enqueues async work correctly declines to override
`hasPendingAsync()` unless its async work is *input-initiated* — weather and crypto fetch on a timer,
so the interface's `false` default is right. `app.h`'s documentation of that default is what made this
verifiable in one pass.

## 6. Recommendations, in order

| # | Action | Cost | Where it goes |
|---|---|---|---|
| 1 | **TASK-458 (C2 guards)** — unchanged, still first | low | already filed |
| 2 | **C7 → a decision in ADR-060**: a component is a translation unit | doc only | ADR-060 amendment |
| 3 | **C8 + C9 → fold into TASK-463** (the C4 policy task) | doc + 4 lines | TASK-463 |
| 4 | **Promote M-CODEQUAL §3's counting note to `best_practices.md`** | doc only | QM adopts |
| 5 | TASK-461 (C5 geometry) — gate is written and red | low | already filed |
| 6 | Do **not** file: C-style casts, `new`/`delete` imbalance, plain enums, weather/crypto duplication | — | §3, §5 |

Item 2 is the one with leverage. C5/C6 are hygiene; C7 is the reason the test architecture has no
unit tier, and it currently exists only as an unstated property of the build.
