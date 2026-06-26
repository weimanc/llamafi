# Design — M-WEBRADIO-NOPSRAM: No-PSRAM playback viability via a Spotify-disabled build

> Owner: Architect
> Status: **sketch / proposed** (2026-06-26) — not implemented; PM to schedule as an `rnd/` experiment.
> Review: **panel consensus reached, 2026-06-26** (PM/Dev/VE/QM/R&D). R1: 4 NEEDS-CHANGES + 1 AGREE-WITH-NITS → rev2. R2: Dev AGREE, PM/VE/QM/R&D AGREE-WITH-NITS → rev3 folds the substantive nits (two-threshold prediction, `get wrPlaying` V0 signal, dead-block method, single-guard comment, vacuous-coex warning).
> Tracked-as: M-WEBRADIO-NOPSRAM (roadmap); experiment record → **EXP-008**; feeds TASK-241 / TASK-233 / ADR-045.
> Deps: M-WEBRADIO (firmware complete); **prereq-done:** TASK-239/240 (~11 KB reclaim); **sidesteps:** TASK-243 (Premium); **baseline:** EXP-007.

## Problem

WebRadio MP3 playback is unstable on the production no-PSRAM CYD. Per **EXP-007 / TASK-233**
the limiter is **usable heap, not the contiguous block**: EXP-007 measured `maxAllocHeap`
**pinned at 38,900 bytes in *both* the 8 KB and 16 KB input-buffer runs** — growing the input
buffer did *not* shrink it and the 22.7 KB decoder alloc did *not* come from it. That 38.9 KB is
a **caps-restricted region that audio allocations cannot use**; the decoder allocates from the
*usable* pool ≈ `free − 38.9 KB`. The 16 KB-buffer run failed at **usable = 59.5 − 38.9 =
20.6 KB < 22.7 KB** (the decoder demand) — a ~2.1 KB shortfall, and the input-buffer ⟷ decoder
being zero-sum makes the underrun fix (a bigger buffer) impossible at that budget. ADR-045
concluded "stable no-PSRAM playback = NO-GO." TASK-239/240 reclaimed ~11 KB; TASK-241 got a
*provisional* pass before being blocked on TASK-243 (Premium) for a valid tight baseline.

## Hypothesis (corrected per R&D round-1 review)

> **Mechanism — usable-pool, not contiguity.** The doc's first draft claimed "less fragmentation
> → larger contiguous block." That is **wrong and contradicts EXP-007** (maxAlloc is pinned,
> caps-restricted, and not the audio allocator's source). The defensible mechanism is simpler:
> **not creating `spotifyTask` raises the `free` floor by its resident footprint → raises the
> usable pool `free − 38.9 KB` by the same amount.** That usable pool is exactly the lever
> EXP-007 identified against the 22.7 KB demand / 2.1 KB shortfall.

| Reclaimed (raises `free`) | Size | Notes |
|---------------------------|------|-------|
| `spotifyTask` stack | **~10 KB** | Heap-resident for life; **`tlsYield` does NOT free it** (frees the TLS *session* + suspends). Unreclaimable in the multi-app build; never created here. |
| Album-art / metadata / queue snapshots | a few KB | Spotify-side resident buffers. |
| TLS-session **fragmentation** | (2nd-order) | Never allocating the ~50 KB session yields a cleaner heap; **claimed only as 2nd-order**, *not* as a maxAlloc win — see threat N1. |

**Quantified prediction (must hold before any soak — R&D N-r2-1: the two thresholds are
*different* and must not be conflated).** EXP-007's 16 KB-buffer run failed at usable ≈ 20.6 KB
(< 22.7 KB decoder demand). Adding ~10 KB stack → **~30.6 KB usable**. Against the two sub-questions
the zero-sum input-buffer⟷decoder squeeze poses (pin the input-buffer target as a **number**:
16 KB nominal ≈ **14.4 KB usable**, the underrun-fix target):

| Sub-question | Threshold | Predicted | Meaning |
|---|---|---|---|
| **(a) Startup reliability** | decoder alone = **22.7 KB** | ~30.6 KB ⇒ **+8 KB → PASS** | doubles the ~5 KB intermittent margin → fixes the `MP3Decoder_AllocateBuffers` failures |
| **(b) Underrun tolerance** | decoder + 14.4 KB buffer ≈ **37 KB** | ~30.6 KB ⇒ **−6 KB → FAIL on stack reclaim alone** | the zero-sum squeeze EXP-007 flagged is not funded by ~10 KB |

**Honest hypothesis:** the ~10 KB reclaim **likely fixes startup decoder-alloc intermittency but
does NOT by itself fund the underrun fix.** The experiment must report (a) and (b) **separately** —
a full PASS needs both; an **(a)-only partial is itself a publishable result** (startup fixed,
underruns remain ⇒ the buffer squeeze is the residual wall, and a shipped variant would ship
best-effort-but-reliable-startup). This is no longer "flash and see."

**Re-baseline caveat (R&D M3):** EXP-007's 38,900 / 59.5 K / 78 K were taken under a Spotify-
*playing* condition that TASK-243 shows was likely never a live session. So: **re-measure the
caps-restricted dead-block on the disabled build** (removing `spotifyTask` may shift the caps
layout — do not assume 38,900 transfers), and state the enabled-build comparison condition
explicitly (idle vs playing) since idle `tlsYield` → ~130 K free makes any test pass trivially.

## Approach (minimal — a single functional guard)

A dedicated PlatformIO env so the production multi-app build is untouched:

```ini
[env:cyd2usb_webradio]
extends = env:cyd2usb_winamp
build_flags = ${env:cyd2usb_winamp.build_flags} -DDISABLE_SPOTIFY   ; presence flag — never =0 (LL-006)
```

**One functional guard:** `#ifndef DISABLE_SPOTIFY` around `spotifyTask::begin(&spotify)`
(main.cpp:~2092) — the *sole* creator of `reqQueue` / `s_tlsYieldedSem` (spotifyTaskStorage.cpp
:453-454). With those null, **`tlsYield()`/`tlsResume()` already early-return** (existing null-
guard at :531) — so all 34 call sites no-op *with no source edit* (Developer review: drop the
proposed guard #2; fewer touched lines = a cleaner byte-unchanged gate).

**Link-safety constraint (VE B2 — design-level, must be honoured by impl):** `cmdGet`/`info`/dbg
paths call `spotifyTask::stackHighWaterBytes()`, `stackSizeBytes()`, `activeError()`, `dbgGet/
dbgSet`, `cmdReconnect` **unconditionally** (main.cpp:2461/2470/2536/2611/2124). Each must remain
**link-safe and return a zero/empty/no-op value when the task was never created** (most already
null-check; the impl must audit *all* of them, or the disabled build crashes on the first `get
stacks`). This is the real design obligation — not new `#ifdef`s, but a verified null-safety
audit of every `spotifyTask::` accessor.

**Dormant Spotify stub (kept — no `AppId` surgery):** the Spotify app stays registered
(appRegistry.h:13, so `gen_app_registry.py` output is unchanged) and stays the boot default. Its
`tick()` runs every frame but is **provably inert**: with no task, `g_snapshot.valid` stays false
→ `updateCurrentlyPlaying` early-returns (spotifyLogic.h:141); no `reqQueue` deref. **Correction
(Developer review):** `connecting()` returns true forever (`s_lastSuccessfulPollMs==0`) → per
ADR-046 the Spotify taskbar slot shows a **permanent amber "connecting" bar**, *not* a
disconnected/red state. Cosmetic for the experiment; a shipped variant (Open-A) would add a
proper "disabled" state.

**BP-031 reconciliation (QM B2):** making `tlsYield`/`tlsResume` no-op in this variant does **not**
violate BP-031 (balanced yield/resume per fetcher). BP-031 governs the **default** build, which is
byte-unchanged here; in the disabled variant there is no TLS session to balance, so the invariant
is vacuously satisfied. The single guard site (the `#ifndef` at main.cpp:~2092) carries a
`// DISABLE_SPOTIFY: no Spotify session — BP-031 n/a; see this doc` comment so a future BP-031
auditor (cf. LL-084) isn't misled (one comment, not 34 — guard #2 is gone).

> **Open question (A):** keep the dormant stub, or boot directly into WebRadio + add a real
> "disabled" Spotify state? Stub is lowest-risk for the experiment; direct-boot is for a shipped
> variant. **Deferred past the gate** — out of the experiment's DoD.

## Measurement, kill criterion & decision gate

**Step 0 — predicted-delta sanity (paper, done above):** usable must clear threshold (a)
22.7 KB to even attempt, and threshold (b) ~37 KB for the underrun fix. If the measured numbers
contradict the prediction, that itself is the finding.

**Step 1 — CHEAP PRE-GATE / HARD KILL (the abort point, PM B2 + QM B1).** On `cyd2usb_webradio`,
at WebRadio `_play()` entry, capture `get stacks` (`heapFree`, `heapMin`, `heapMaxAlloc`) and
re-measure the caps-restricted dead-block. **Dead-block measurement method (VE N-a / QM N-r2-2):**
`dead_block = heapFree − heapMaxAlloc` at that point (or a `heap_caps_get_largest_free_block(
MALLOC_CAP_8BIT)` probe added to `get stacks`); `usable = heapFree − dead_block`. The pass test is
a **deterministic heap number**, not a single observed `MP3Decoder_AllocateBuffers` outcome (R&D
N-r2-2 — a one-shot alloc can be fragmentation luck at the ~5 KB margin):
- **HARD KILL (threshold a):** if `usable < 22.7 KB` → abort, do **not** spend DUT playback time;
  record FAIL.
- **(threshold b):** if `22.7 KB ≤ usable < ~37 KB` → proceed to Step 2 but **expect an (a)-only
  partial** (startup reliable, underruns likely persist) — a valid result, not a full PASS.

The pass signal is **usable headroom, NOT `maxAlloc` rising** (EXP-007: maxAlloc is constant). On
abort: abandon the `rnd/` branch (nothing merged to trunk → nothing to clean; if any guard was
merged, the named cleanup task reverts it).

**Step 2 — only if Step 1 clears threshold (a) — playback soak (V3):** re-run the TASK-241
input-buffer experiment (`setBufsize` ~16 KB) and measure sustained playback against the gate
below, reporting (a) startup reliability and (b) underrun tolerance **separately**.

**Decision gate (ADR-045 / TASK-238 bar):** stable PLAYING ≥ 60 s within ≤ 6 auto-skips on
**≥ 90 % of cold-boot entries**, over a **fixed station set, ≥ 3 cold-boot trials per station**
(fragmentation is run-to-run per EXP-007), with **network-flake entries excluded from the
denominator** (mirror the T169 carve-out). Measured by the new `T_WR_PLAY_SUSTAIN` test (see V).

## What a PASS proves — relationship to ADR-045 and TASK-241 (Architect recommendation)

**A PASS here does NOT supersede ADR-045 for the multi-app (Spotify-enabled) board** (R&D M4 —
avoid the over-claim). It proves a narrower, still-valuable thing: **no-PSRAM WebRadio is viable
*in a Spotify-free build*** — i.e. the hardware *can* do it given the RAM; the wall was the budget,
not the silicon. Consequences:
- **PASS →** graduates a **product-split proposal (PROP / follow-on milestone)** for a shipped
  WebRadio-focused variant; ADR-045 is *amended* to record "viable with Spotify disabled," not
  overturned for the default build.
- **FAIL →** the 38.9 KB caps-restricted block is the hard wall even with the stack reclaimed;
  ADR-045 stands; experiment shelved.

**Sequencing recommendation to PM (PM B3):** this lane is **runnable now without Premium**, whereas
TASK-241's tight re-test is blocked indefinitely on external TASK-243. Recommend: **mark TASK-241
deferred-behind-TASK-243 and make this experiment the active gate for "is no-PSRAM WebRadio viable
at all."** The two are *parallel lanes answering different questions* (this: Spotify-free
viability; TASK-241: multi-app reclaim viability), not competing supersedes.

## Verification

> Drafted by Architect; **@VE owns** formalising into `test_plan.md` + the regression suite.
> Two-variant matrix — every claim holds in *both* `cyd2usb_winamp` (default) and `cyd2usb_webradio`.

**V0 — prerequisites (critical path, before ANY DUT run — PM B1 / VE B1):**
- **Firmware variant signal (Developer):** (a) a **boot-log token** `[boot] spotify=off` printed
  under `-DDISABLE_SPOTIFY` *during boot* (the harness reads it from serial scraping in the reset
  window, before the shell is responsive); and (b) `get variant` (or an `info` field
  `"spotify":"off"`) for post-shell assertions. Specify exact JSON in impl.
- **Harness readiness (VE):** `Dut._wait_for_ready()` (run_serialdbg_tests.py:88-178) hard-blocks
  on `[spotify.poll] ok 200` (:153) — which **never emits** here → up to 120 s hang per Dut open.
  Add a variant branch keyed on the boot token: readiness = **WiFi-up (`IP address:`) + shell-ready
  (probe `info` in a retry loop)**, skipping the poll-wait. This V0 work is **task #1**; no other V
  runs until it is itself green.
- **PLAYING-duration signal (Developer — VE B3', NOW a named V0 deliverable, not a V3 aside):** the
  decision gate's "≥ 60 s hold" half **has no queryable signal today** — `get wrSkip.settled` flips
  at `WR_SETTLED_MS = 12000` (12 s, webRadioApp.h:48), and `_playingSinceMs` (webRadioApp.h:537) is
  private. Add `get wrPlaying` → `millis() − _playingSinceMs` while `_state==PLAYING` (else 0). A few
  lines, same surface as `wrSkip`. Without it `T_WR_PLAY_SUSTAIN` cannot measure the ADR-045 bar, so
  the whole gate is un-instrumented — this lands in V0 alongside the variant signal (BP-024: spec the
  debug var before the test that needs it).

**V1 — build matrix + default-build isolation (host, gated):** both envs compile + pass
`./run/check`. **Default unchanged (risk D):** compare `cyd2usb_winamp` `.elf` `.text`/`.rodata`/
`.data` **section hashes** before/after the patch (the robust gate — Arduino-ESP32 bakes a build
timestamp so a raw `.bin` sha256 may differ; the non-debug env injects no git hash so `.bin` is a
fast-path-if-it-matches). The **6th `./run/check` gate** for `cyd2usb_webradio` lands only **on
promotion toward shipping** (PM N3 / QM N3) — not at experiment start; the branch builds it locally.

**V2 — conditional-compile + link-safety (DUT, disabled variant):**
- **Link-safety (VE B2):** `get stacks` / `info` / dbg / `reconnect` all execute without crashing
  (proves every unconditional `spotifyTask::` accessor is null-safe).
- **Task absent:** `get stacks` reports `spotSize==0 && spotFree==0` (the line is always emitted —
  assert the values, not the line's absence; BP-016), corroborating the reclaim.
- **`tlsYield` no-op:** WebRadio entry does not stall on a yield ack (enabled build can block ≤150 s
  with the 403). *(Note: this is a 2nd confound on any "stations now play" result — R&D N3.)*
- **Usable-headroom capture (the Step-1 metric):** at `_play()` entry capture `heapFree`/`heapMin`/
  `heapMaxAlloc` via `get stacks` (the `HEAP` log regex at :5393 must be extended to capture
  `maxAlloc=`, already logged at webRadioApp.h:621), and compute `usable`. **This is the kill gate.**

**V3 — functional parity (DUT, disabled variant):**
- **`T_WR_PLAY_SUSTAIN` (NEW — VE B3, the gate's missing instrument):** no current test measures
  sustained PLAYING / counts skips. Build one that reads `get wrPlaying` (the **V0** duration signal)
  + `wrSkip.tried`, asserts ≥ 60 s hold, and tallies the ≥ 90 %/≤ 6-skip ratio over the fixed station
  set × ≥ 3 trials, reporting (a)/(b) separately. (The instrument's firmware signal is a V0
  prerequisite — see V0; without it PASS is a human eyeball, not a suite result.)
- **Inverse-`tlsYield` per-fetcher check (VE M1 — a NEW assertion, not a coex-suite reuse):** the
  existing `t_wr_coex_*`/T272 tests assert correctness *while spotifyTask holds a session* — on the
  disabled variant that contention is gone, so they pass **vacuously** and cover nothing. Write a new
  per-fetcher assertion: weather/crypto/stock/teletext/heatmap each fetch successfully + capture
  `maxAlloc`-at-fetch on the disabled variant (the real risk is a fetcher that *relied on* the freed
  session, not contention). Each new matrix row (Process §) links ≥ 1 of these test IDs (VE N-d).
- **Eject round-trip into the dormant stub (VE M2):** eject Spotify→WebRadio→Spotify with no poll
  task — assert no hang and `appId` round-trips (this is the entry path every WebRadio test uses;
  highest-risk harness path; cf. LL-085 dormant-app crash).

**V4 — regression on the enabled build:** full serialdbg suite green on `cyd2usb_winamp`, excluding
the known-flaky carve-out (T-CDWN-01, T169 — VE N3).

**Ownership / artifacts (VE M3/M4):** 6th gate = `check_build.sh` edit (Developer, on promotion);
harness variant-awareness = `run_serialdbg_tests.py` edit (VE, gated on V0). PASS/FAIL recorded as a
dated DUT log with the `T_WR_PLAY_SUSTAIN` ratio + before/after `heapFree`/`usable` numbers pasted
into TASK-241, plus an **EXP-008 report** and an **ADR-045 amendment** id.

## Risks / threats to validity

- **(B) Usable-pool, not maxAlloc (R&D B1/B2).** Resolved in Hypothesis: measure `usable = free −
  dead_block`, re-measured on this build. maxAlloc is reported only to confirm the dead-block, never
  as the pass signal.
- **(N1) Not a clean ablation (R&D N1).** Removing a resident occupant relayouts the heap; a PASS
  supports "*with Spotify disabled*, playback is stable," **not** "*Spotify's RAM* was the cause."
- **(N3) Two variables at once (R&D N3).** The disabled build differs in RAM *and* the removed
  yield-stall; a "plays now" result is partly the removed stall. Fine for the heap gate; muddies any
  pure "stability" attribution.
- **(C) Scope creep.** Experiment first; a shipped Spotify-or-WebRadio build matrix (registry
  disable + boot default + eject + settings) is a follow-on milestone **only on PASS**.
- **(D) Default-build drift.** Single guard + `.elf`-section gate (V1) protect the shipping product.

## Process & lifecycle

- **Branch:** `rnd/webradio-nopsram` (AGENTS.md: R&D on branches, never merged to main directly; PM
  decides graduation). **Merge of env/guards to main is gated on PASS + the follow-on milestone**,
  not on the experiment completing.
- **Kill/cleanup (QM B1):** FAIL → branch abandoned, env+guards never merged (nothing to clean). The
  scheduling task names the cleanup task explicitly as a placeholder, per the BP candidate below.
- **Cross-feature (QM M4 / Dev M5):** add a `cross_feature_matrix.yaml` row *DISABLE_SPOTIFY ×
  {weather,crypto,stock,teletext,heatmap,webradio}* (shared `tlsYield` contract change) **before**
  V3 runs.
- **Experiment record:** **EXP-008** (mirror EXP-007 format: Hypothesis/Approach/Outcome/Conclusion/
  Recommendation/Branch) — R&D-owned; the supersede/amend ADR — Architect-owned. Its Outcome section
  records the **re-measured disabled-build dead-block next to EXP-007's 38,900 even on a FAIL** (R&D
  N-r2-3 — a shifted caps-region from the relayout is itself a finding); and reports (a)/(b) separately.
- **BP candidates flagged to QM/human (QM M1/M2):** (1) *any R&D/experiment/spike names its decision
  gate, its FAIL artefact-disposition, and a cleanup task id before being scheduled*; (2) *any
  `-D`-flag build variant kept past its experiment is added to `run/check` in the same change, or the
  flag is removed.*
- **Scheduling (PM):** convert to a task (M-WEBRADIO-NOPSRAM, P1) with an explicit **DoD** (env
  builds; default `.elf` sections unchanged; V0 lands green; Step-1 usable captured; on PASS → V3
  gate met + EXP-008 + ADR amendment + Open-A graduated to a PROP; on FAIL → ADR-045 stands, branch
  shelved, result in TASK-241) and the **ordered handoff**: Developer (variant signal + guard) →
  VE (V0 harness) → DUT Step-1 kill gate → conditional V3 → Architect (ADR verdict).

## Out of scope

Runtime (non-build) Spotify toggle; removing the Spotify app from the registry; any production
build-matrix change. All downstream of a PASS.
