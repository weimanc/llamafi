# M-WINAMP-PLAYER — VE Review (test-id testability)

> Reviewer: Verification Engineer
> Date: 2026-08-07
> Scope: the 76 reserved ids across `T_RCL_` / `T_SD_` / `T_AE_` / `T_PLE_` / `T_PLR_`
> Design set: [M-WINAMP-PLAYER.md](M-WINAMP-PLAYER.md) + four workstream docs · **ADR:** [ADR-059](../decisions/ADR-059.md)
> Status: **Pre-implementation review — 4 blockers, 9 majors, 5 minors**

---

## Verdict

The structure is right: per-task tables, gates cited from the phasing table, negative results treated
as valid outcomes, and three genuinely destructive failure modes pushed off-device for verification.
Coverage against `cross_feature_matrix.yaml` is complete — every one of X050–X064 has ≥1 id, which is
better than this project's recent baseline (M-PR-LOCATIONS shipped with zero).

But **a significant fraction of these ids are not executable as written.** Three classes of problem
recur: assertions with no observable signal, "worst case" and "identical" bars with no sample size,
and tests that require hours of real-time playback to reach the state under test. Those need fixing
before the first task starts, because each one becomes a silent coverage skip at run time — the tester
marks it PASS on a weaker check than the design intended and nobody notices.

Two ids are not tests at all and should be reclassified.

---

## Blockers

### VE-1 — `T_PLR_21` / `T_PLR_22` are unreachable in real time

**Problem.** `T_PLR_21` exercises all four shuffle × repeat end-of-playlist cells; `T_PLR_22` requires
**20 wrap cycles** with a 0/20 collision bar. Reaching end-of-playlist means playing a playlist to
completion. At even 30 s per track over a 20-track list that is ~3.3 hours for `T_PLR_22` alone, and
the design elsewhere specifies a ≥20-track playlist for `T_PLR_20`. This is not a slow test, it is a
test nobody will ever run — which makes it worse than no test, because the id implies coverage.

**Severity:** Blocker (silent coverage skip on the single most intricate logic in the milestone).

**Resolution.** The play-order engine must expose a cursor-manipulation debug surface, and TASK-418
must deliver it as part of the feature, not as test scaffolding bolted on later:

- `set plCursor <n>` — move the bag cursor directly.
- `get plOrder` — dump `playOrder[]` (needed by VE-2 as well).
- `advance next|prev` — step the order engine **without** decoding audio.

With that, `T_PLR_22` becomes 20 forced wraps in seconds and the assertion is exact. Keep **one**
end-to-end real-playback case (`T_PLR_25`, 5 short files) to prove the `audio_eof_mp3` path actually
drives the same code the debug surface drives — otherwise the debug path is all that gets tested.

### VE-2 — Several assertions have no observable signal

**Problem.** These ids assert on state the firmware does not expose:

| id | Asserts | Observable today? |
|---|---|---|
| `T_PLE_04` | "no repaint while seqno static" | **no** — there is no repaint counter |
| `T_PLR_20` | shuffle visits each track exactly once | **no** — advance order is not dumpable |
| `T_PLR_23` | Prev replays history exactly | **no** — same |
| `T_PLR_24` | tap-to-play moves the cursor, no reshuffle | **no** — same |
| `T_AE_10` | "no mutex stall" | **no** — "stall" is not defined or measured |
| `T_PLR_25` | "no `connecttoFS` from the pump task" | **no** — not detectable from outside |

**Severity:** Blocker. A test whose expected result cannot be observed gets downgraded at run time to
"it didn't crash", which is not what any of these are for.

**Resolution.** Three instrumentation asks, all cheap, all belonging to the implementing task:

1. `get pleditRepaints` — monotonic repaint counter in `pleditView` (TASK-411). Makes `T_PLE_04` exact.
2. `get plOrder` / `get plCursor` (TASK-418, shared with VE-1). Makes `T_PLR_20/23/24` exact.
3. **`T_PLR_25` should not be a test — it should be a debug-build assert.** Put
   `configASSERT(xTaskGetCurrentTaskHandle() == g_loopTaskHandle)` at the head of the open-next-track
   path. Then the wrong-task call panics loudly in every debug run instead of being probed once.
   Same for `T_AE_10`: define "stall" as a measurable — reuse `perf::record()` on the loopTask tick
   and assert max gap < 100 ms, matching `T_AE_04`'s existing bound.

### VE-3 — "Identical pass set" will fail on known flake, not on regression

**Problem.** `T_AE_01`, `T_PLE_08`, `T_PLR_17` and `T_PLR_18` all say "identical pass set to the
baseline". The WebRadio suite has **known flaky members** — `T_WR_TLS_01` (residual mirror-truncation
flake, TASK-284), `T169` (yahoo network), `T_PR_05` (`[NETWORK]`-flaky). A single baseline run
compared to a single post-refactor run will differ for reasons that have nothing to do with the
extraction, and the most likely response under schedule pressure is to wave it through — at which
point the test has cost time and bought nothing.

The design *cites* LL-104 ("compare failure sets, not counts") but does not operationalise it.

**Severity:** Blocker on the milestone's most important safety property (behaviour-neutral refactor).

**Resolution.** Make the protocol explicit in the task:

- Baseline is **≥3 full runs** before the refactor lands, not one.
- Pre-declare the flaky set from those runs; a member that fails in the baseline is excluded from the
  identity comparison and tracked separately.
- The bar is: **no test that passed in all 3 baseline runs fails after**, and no new failure appears
  outside the pre-declared flaky set.
- This mirrors the ≥3-trial protocol VE already established on TASK-402.

### VE-4 — `T_PLE_01` / `T_PLE_07` cannot pass as specified

**Problem.** "Zero differing pixels" via `run/screendump`. The Winamp main window contains a **live
VU meter / visualiser** (`vuMeter.h`, and TASK-387/388's real spectrum and wave modes) which animates
continuously and is driven by audio. Two screendumps of the same UI state will differ in the vis
region every time. As written these tests fail 100 % of the time and will be "fixed" by relaxing them
into eyeball checks — losing the exactness that is the whole reason to use screendump here.

A second, smaller issue: the known limitation is already noted (screendump DTR-resets on connect, so
navigated state must be reached by injection) — good — but the design does not say the PLEDIT region
is the diff scope.

**Severity:** Blocker (the PLEDIT gate is the primary control on workstream 3).

**Resolution.** Scope the diff to the PLEDIT rect (`PLEDIT_Y … PLEDIT_Y + PLEDIT_H`, full width) and
disable the visualiser for the comparison (`vu::setMode(off)` already exists as a mode). State both in
the test. A whole-canvas diff is only meaningful with vis off *and* a static track — worth having as
one extra case, not as the default.

---

## Majors

### VE-5 — "Worst case" and "sustained" bars have no sample size

`T_SD_04` (≥200 KB/s sustained), `T_SD_05` (≤50 ms worst-case single read), `T_PLR_12` (heap ±256 B).
Worst-case over 100 reads and over 100 000 reads are different claims, and only the second one tells
you anything about a 30-minute soak. Specify: `T_SD_04` ≥2 MB continuous (already stated — good);
`T_SD_05` **N ≥ 5 000 reads, report p50/p99/max**, not just max — a bimodal distribution is the
interesting result and TASK-367 already burned this project once by reporting a single figure for a
bimodal fetch RTT.

### VE-6 — `T_SD_04` / `T_SD_05` "with the display actively redrawing" is unreproducible

The load is the *point* of the test (SPI/CPU contention), but "actively redrawing" is not a defined
workload. Two runs are not comparable and a near-bar result is meaningless. Specify a fixed load —
e.g. Aquarium at its natural frame rate, or a scripted `tft.fillRect` loop at a stated rate — and
record which was used alongside the number.

### VE-7 — `T_AE_03`'s duration is not a number

"At or above the duration that caught the DMA-gate regression" — that duration appears nowhere as a
figure. An implementer will pick something convenient. Given the lesson this bar exists to encode
(short soaks gave false confidence on exactly this code), it must be an explicit minute count in the
task. VE proposes **≥30 min** to match `T_PLR_39`, or the documented figure if someone can retrieve it
from the DMA-gate task.

### VE-8 — `T_AE_09` will read a contaminated high-water mark

`mb_arena_hwm()` is a **high-water mark for the session**. If any stream playback happened earlier in
the same boot — which it will, since the tester is checking WebRadio still works — the HWM reflects
that, and the file-playback number is unverifiable. Test must specify: **fresh boot, file playback
only, no stream connect**, then read HWM. Otherwise the assertion is vacuous.

### VE-9 — `T_AE_05` is a code review, not a test

"The diff is a move — `git diff -M` review, no behavioural hunks" has no repeatable procedure and no
objective pass/fail. It is a valuable *gate*, but tracking it as a test id inflates the coverage count
with something that cannot be re-run. Reclassify as a review checklist item on TASK-409 and remove the
id, or replace with something mechanical (e.g. `git diff -M --stat` shows ≥95 % rename similarity on
the moved block).

### VE-10 — `T_PLR_30` can pass by accident

The destructive-failure test (shuffle ON + reorder + SAVE writes **display** order) requires the
shuffled order to actually *differ* from the view order. On a short playlist Fisher-Yates can return
the identity permutation, and the test then passes while proving nothing. Add a precondition:
**assert `playOrder != viewOrder` before saving**, and use N ≥ 20.

### VE-11 — `T_PLR_36` will be invalidated by the wrong flash script

The variant-fallback test needs `settings.json` to **survive** the reflash. `run/flash` is
app-partition-only so SPIFFS persists — correct. `run/flash-fs` formats and rewrites SPIFFS, which
would wipe the persisted mode and make the test vacuously pass. The task must name the script
explicitly. This is the single highest-risk test in the milestone (null-app boot crash) and it is
one wrong command away from silently passing.

### VE-12 — `T_PLR_39` is not scriptable as described

"≥30 min playback **with concurrent browsing and scrolling**" — if that means a human poking the
screen for half an hour, it will be run once and never again. Drive it from the injection queue
(`tap`/`tick`/`release` already exist) so it is repeatable and can be re-run after any later change.

### VE-13 — Missing: nothing tests the SD degraded path

Local-playback §10 specifies mount failure → degraded state, `hasError()` true, bail cleanly — and
M-SDFS OQ3 leaves card-removal-mid-playback "undefined". **"Undefined" is not a test outcome.** At
minimum: `T_SD_10` (mount with no card → clean degraded entry to Player mode, no crash, taskbar
indicator red) and `T_PLR_41` (card removed mid-playback → no WDT, no crash, error surfaced). The
device will meet a missing card in normal use; it should not be the first time anyone finds out what
happens.

---

## Minors

- **VE-14** — `T_SD_02` (GPIO5 strapping, 5 cold boots): specify **power-cycle**, not esptool RTS
  reset. Straps latch on reset so RTS probably re-latches, but "probably" is not a test. Also N=5 is
  thin for an intermittent electrical fault; N=20 costs minutes.
- **VE-15** — `T_SD_06` (heap delta ≤8 KB) and `T_PLR_12` (±256 B): free-heap on this device is noisy
  with WiFi/LWIP churn. Quiesce (or state the tolerance covers it), and report **largest-free-block**
  alongside free-heap — fragmentation is the actual risk here per M-HEAP-FRAGMENTATION, and a clean
  free-heap number can hide it.
- **VE-16** — X060 (SHUFREP sprites reused verbatim) is listed as covered by `T_PLR_19`, but that
  tests *hit-testing*, not that the atlas is unchanged. It is however already covered by
  `check_build.sh` step 3 (`golden.sha256` includes `skin_assets.c`) — record that, so a future audit
  doesn't file it as a hole.
- **VE-17** — X051's manifest registration has no id, but `check_build.sh` step [6/6] is a budget
  gate that fails on unregistered buffers. Same treatment: note it as gate-covered, not untested.
- **VE-18** — `T_PLE_05` / `T_PLE_09` (scroll feel) say "indistinguishable to the operator". That is a
  vibe, not a criterion. Use the ≥3-trial A/B protocol established on TASK-402, with the operator
  blind to build order where practical.

---

## Coverage check against `cross_feature_matrix.yaml`

| Edge | Covered by | Adequate? |
|---|---|---|
| X050 | `T_AE_01`–`04` | yes (subject to VE-3) |
| X051 | `T_AE_08`, check_build [6/6] | yes (VE-17) |
| X052 | `T_PLR_09`, `13`, `39` | yes (subject to VE-12) |
| X053 | `T_SD_01`–`03`, `08` | yes (subject to VE-14) |
| X054 | `T_PLE_01`–`06` | yes (subject to VE-4) |
| X055 | `T_PLE_07`–`13` | **partial** — see below |
| X056 | `T_PLR_01`, `05` | yes |
| X057 | `T_PLR_03` | yes |
| X058 | `T_PLR_14`, `15` | yes |
| X059 | `T_PLR_31` | yes |
| X060 | `T_PLR_19` + golden.sha256 | yes (VE-16) |
| X061 | `T_PLR_17` | yes (subject to VE-3) |
| X062 | `T_PLR_30` | yes (subject to VE-10) |
| X063 | `T_PLR_25` | **reclassify** — VE-2(3) |
| X064 | `T_PLR_36` | yes (subject to VE-11) |

**X055 gap.** WebRadio's PLEDIT change-detection is `_pleditDirty` (a bool); the shared renderer's
contract is a **seqno** whose invariant is "changes iff content changes" (IFC invariant 2). Converting
a dirty-flag to a seqno is a semantic change with two distinct failure modes — a missed repaint
(seqno not bumped on a mutation) and a repaint storm (seqno bumped on every tick) — and neither is
covered. **New id needed: `T_PLE_14` — StationListSource seqno bumps exactly once per station-list
change and not at all otherwise**, observable via VE-2's `get pleditRepaints`.

---

## Handoff

**To Architect:** VE-2 and VE-1 are asks for *product* surface (`get plOrder`, `get plCursor`,
`get pleditRepaints`, the loopTask assert), not test scaffolding — they belong in the design's debug
surface, consistent with the project's existing rule that every app exposes `dbgGet`/`dbgSet`
(NEW-APP-CHECKLIST item 3). Please fold them into TASK-411 and TASK-418 rather than leaving VE to
retrofit them.

**To PM:** four blockers should gate the start of the affected tasks, not the whole milestone —
VE-1/VE-2 gate TASK-418 and TASK-411, VE-3 gates TASK-409, VE-4 gates TASK-411. TASK-408 and TASK-423
are unaffected and can start as soon as ADR-059 is signed off. Two new ids (`T_SD_10`, `T_PLR_41`) and
one (`T_PLE_14`) need adding to the reserved set; one (`T_AE_05`) should be removed as not-a-test.

Net after this review: **76 → 78 ids**, one reclassified to a review item, one to a runtime assert.
