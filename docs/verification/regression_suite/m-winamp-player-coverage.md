# M-WINAMP-PLAYER — proposed `test_coverage:` for `X050`–`X064`

> Owner: @VE · Written 2026-08-17 executing P0 of
> [M-TESTBASE §4](../../architecture/designs/M-TESTBASE-phase1-player-gate.md).
> Companion to the reserved-family block in [test_plan.md](../test_plan.md).

**This is a PROPOSAL, not an edit.** `docs/project/cross_feature_matrix.yaml` is **Developer-owned**
(AGENTS.md); VE does not write it. Everything below is formatted so @Developer can apply it
mechanically: one block per interaction, the exact replacement line, and the reason.

**Today every one of the fifteen rows is `test_coverage: []` except three** — `X050`
(`[T_AE_13, T_AE_15, T_AE_16]`), `X051` (`[T_AE_11, T_AE_12, T_AE_14]`), `X063` (`[T_AE_12]`).
Those three are the only populated rows in the range **and every id in them is unimplemented**:
`T_AE_11`–`16` have no bodies and are blocked six ways over
(`docs/verification/test_plan.md:4838-4849`). The file's own `notes:` already say so — "COVERAGE
CLAIMED, NOT YET EARNED" (`docs/project/cross_feature_matrix.yaml:1125`,
`docs/project/cross_feature_matrix.yaml:1171`, `docs/project/cross_feature_matrix.yaml:1410`). So the
three populated rows are *less* honest than the twelve empty ones, and the twelve empty ones include
rows with running bodies. The list drifted in both directions.

## Convention proposed alongside the values

`test_coverage:` is a bare id list with no status. That is exactly the shape that let "covered" and
"green" be conflated. **Proposed rule, cheap and non-structural: only ids with a running body go in
the list; everything else goes in `notes:` under a `PLANNED COVERAGE:` line.** If @Developer prefers
to keep specified-but-unwritten ids in the list, then a trailing YAML comment naming their status is
the minimum — shown as the alternative on each block below.

---

## The fifteen values

### X050 — audio engine shared by WebRadio and LocalPlayer
```yaml
    test_coverage: [T_AE_04]
```
Currently `[T_AE_13, T_AE_15, T_AE_16]` — **remove all three**, none has a body. `T_AE_04` does
(`app/tools/test_ae04_teardown.py`, driver `run/ae04`). Add to `notes:`:
`PLANNED COVERAGE: T_AE_01-03 (no id-labelled body; run/wr-soak is the vehicle), T_AE_13/15/16 (blocked — B-RULING, B-NET).`
Alternative form: `[T_AE_04, T_AE_13 (resv), T_AE_15 (resv), T_AE_16 (resv)]` is **not** valid YAML —
use a comment: `test_coverage: [T_AE_04]  # + T_AE_13/15/16 specified, blocked`.

### X051 — `AUDIO_NO_SD_FS` drop vs the memory plan
```yaml
    test_coverage: []
```
Currently `[T_AE_11, T_AE_12, T_AE_14]` — **remove all three**, none has a body. The interaction is
in fact **gate-covered**, not test-covered: `run/check`'s mem-budget gate fails on an unregistered
buffer (VE-17). Add to `notes:`:
`GATE-COVERED: run/check mem_layout budget gate. PLANNED COVERAGE: T_AE_08, T_AE_11/12/14 (blocked).`

### X052 — SD/FS contention between loopTask and the pump task
```yaml
    test_coverage: [T_PLR_09, T_PLR_13]
```
Both `impl`. `PLANNED COVERAGE: T_PLR_39 (soak, resv — schedulable now, see below).`
**This row goes from `[]` to populated**: M-TESTBASE §1 lists `X052` as one of the seven high-risk
zero-coverage interactions; two of its three ids have been running for weeks.

### X053 — SD on VSPI vs the memory/pin plan
```yaml
    test_coverage: []
```
Unchanged, and **honestly empty**: no `T_SD_*` id has a body anywhere in `app/tools/`.
`PLANNED COVERAGE: T_SD_01-03, T_SD_08.`

### X054 — `pleditView` absorbed `drawPlaylist()` wholesale
```yaml
    test_coverage: []
```
Unchanged, honestly empty. `T_PLE_01`–`06` have no bodies.
`PLANNED COVERAGE: T_PLE_01-06.`

### X055 — WebRadio's independently-evolved PLEDIT copy
```yaml
    test_coverage: [T_PLE_WR_155, T_PLE_WR_156, T_PLE_WR_157, T_PLE_WR_158, T_PLE_WR_159, T_PLE_WR_160]
```
These six are the realisation of `T_PLE_08` (velocity-scroll, WebRadio variant) and are registered in
the runner. They cover scroll behaviour, **not** the seqno contract.
`PLANNED COVERAGE: T_PLE_07/09-13; T_PLE_14 (StationListSource seqno bumps exactly once per change) is NOT YET SPECIFIED in any owned doc — VE-review flagged it and nobody filed it.`

### X056 — player-mode cycling on the taskbar slot
```yaml
    test_coverage: [T_PLR_01, T_PLR_05]
```
Both `impl`. **`[]` → populated.**

### X057 — taskbar asserts WebRadio is the last `AppId`
```yaml
    test_coverage: [T_PLR_03]
```
`impl`. Also enforced at compile time by three `static_assert`s
(`app/src/taskbar/taskbar.h:42-63`); add `GATE-COVERED: taskbar.h static_asserts (T0).`
**`[]` → populated.** M-TESTBASE §1 lists this as zero-coverage; it is not.

### X058 — browser paging vs the shell busy gate
```yaml
    test_coverage: [T_PLR_14, T_PLR_15]
```
Both `impl`. **`[]` → populated.**

### X059 — edit ops mutate RAM only until SAVE
```yaml
    test_coverage: []
```
Honestly empty. `PLANNED COVERAGE: T_PLR_31 — blocked on TASK-424.`

### X060 — SHUFREP sprites reused verbatim
```yaml
    test_coverage: [T_PLR_19]
```
`impl` (hit-test). Asset identity is `golden.sha256` in `run/check`, not this id (VE-16) —
add `GATE-COVERED: run/check golden.sha256 (skin_assets.c).` **`[]` → populated.**

### X061 — capability mask rewrites the Spotify-only zone hardcoding
```yaml
    test_coverage: [T_PLR_18]
```
**`[]` → populated, but the id name depends on the unresolved 17/18 swap** (next section). `T_PLR_18`
is the runner's WebRadio id; the design doc calls that same test `T_PLR_17`. Apply this line **only
after** the swap is settled, or apply it now and re-point if the design doc wins.

### X062 — `playOrder` vs `viewOrder` vs what SAVE writes
```yaml
    test_coverage: []
```
**Stays empty deliberately.** `T_PLR_20`–`24`/`26` are `impl` and exercise `playOrder` mechanics, but
they cannot observe the divergence that *is* this interaction — `viewOrder` is an identity
permutation with no mutator (`app/src/player/m3u.h:230`) and there is no SAVE. Listing them here
would be the exact conflation this file exists to stop.
`PLANNED COVERAGE: T_PLR_30 — blocked on TASK-424. X062 is OBSERVED, NOT CLOSED by M-TESTBASE phase 1.`

### X063 — `audio_eof_mp3` auto-advance on the pump task
```yaml
    test_coverage: [T_PLR_25]
```
`impl`. Currently `[T_AE_12]`, which has no body — **replace, do not append**. Also
`GATE-COVERED: ADR-059 D12 runtime configASSERT on the open-next-track path (panics every debug run).`

### X064 — compile-time-optional player modes
```yaml
    test_coverage: []
```
Honestly empty. `PLANNED COVERAGE: T_PLR_36, T_PLR_37 — both blocked: no shipping env defines -DPLAYER_SPOTIFY/-DPLAYER_WEBRADIO/-DPLAYER_LOCAL, so the fallback path is implemented and unexercised in every configuration (docs/project/tasks-winamp-player.md:664-676).`

---

## Summary of the proposed change

| | rows |
|---|---|
| `[]` → populated with running bodies | `X052`, `X056`, `X057`, `X058`, `X060`, `X061` (6) |
| populated → corrected (unimplemented ids removed) | `X050`, `X051`, `X063` (3) |
| stays `[]`, honestly | `X053`, `X054`, `X059`, `X062`, `X064` (5) |
| `[]` → populated, partial only | `X055` (1) |

**Five interactions remain genuinely uncovered after this change** — `X053`, `X054`, `X059`, `X062`,
`X064` — plus the `X055` seqno half. Two of them (`X059`, `X062`) are blocked on the same open task,
**TASK-424**; two (`X053`, `X054`) are simply unwritten and blocked on nothing.

---

## The `T_PLR_17`/`T_PLR_18` swap — VE recommendation and blast radius

**The defect.** The design doc assigns `T_PLR_17` = "WebRadio unchanged", `T_PLR_18` = "Spotify
unchanged" (`docs/architecture/designs/M-WINAMP-PLAYER-local-playback.md:466-467`). The runner
implements the opposite: `t_plr_17` is Spotify (`app/tools/run_serialdbg_tests.py:5958`), `t_plr_18`
is WebRadio (`app/tools/run_serialdbg_tests.py:6019`).

**Recommendation: change the design doc to match the implementation.** Not the code. Three reasons,
in order of weight:

1. **The historical record is already written in the runner's numbering, in files that must not be
   rewritten.** `T_PLR_17` is named as the *failing Spotify* leg in LL-122 and LL-123
   (`docs/quality/lessons_learned.md:2132`, `docs/quality/lessons_learned.md:2153`), in BP entries
   (`docs/quality/best_practices.md:597`, `docs/quality/best_practices.md:627`), in the QM audit log
   (`docs/quality/audit_log.md:1764`) and in the archived TASK-417 record
   (`docs/project/tasks-archive.md:16689`, `docs/project/tasks-archive.md:17705`). Every one of those
   describes a **Spotify** SHUFFLE/REPEAT dispatch race under the label `T_PLR_17`. Renaming the test
   code would silently falsify five closed quality artifacts — the worst possible direction for a
   bookkeeping fix.
2. **A gate result of record exists under the runner labels.** `docs/project/tasks-archive.md:17707`
   records "Gate closed 2026-08-11: `T_PLR_17,18,19,06,07`". Swapping the code re-labels a passed
   gate.
3. **The design doc's two rows are one line each and are cited by nothing that ran.** The cheaper,
   safer artifact to move is the spec.

**Blast radius of the recommended fix (edit the doc, leave the code):**

| Site | Today | Action |
|---|---|---|
| `docs/architecture/designs/M-WINAMP-PLAYER-local-playback.md:466-467` | 17 = WebRadio, 18 = Spotify | **swap the two rows** (Architect) |
| `docs/architecture/designs/M-WINAMP-PLAYER-local-playback.md:516` | "`T_PLR_17`/`18` protect two shipped modes" | no change — order-neutral |
| `docs/architecture/designs/M-WINAMP-PLAYER-VE-review.md:229` | `X061` → `T_PLR_17` | **→ `T_PLR_18`** (X061 is the WebRadio row) |
| `docs/architecture/designs/M-TESTBASE-phase1-player-gate.md:46` | quotes `app/src/winamp/winampDisplay.h:158` as citing `T_PLR_17` for the CAP_TRANSPORT invariant behind X061 | **→ `T_PLR_18`**, and the cited comment moves with it |
| `app/src/winamp/winampDisplay.h:158` | "WebRadio advertises CAP_TRANSPORT only (unchanged — `T_PLR_17`)" | **comment → `T_PLR_18`** |
| `app/src/webRadioApp.h:266` | "not a feature (`T_PLR_17`)" — WebRadio context | **comment → `T_PLR_18`** |
| `app/src/webRadioApp.h:242` | "the exact bug `T_PLR_18` caught (playerCaps=15…)" — WebRadio context | **already correct** under the runner numbering |
| `app/src/apps/spotifyApp.h:21` | "bit WebRadio and Player (`T_PLR_18`'s caught bug)" | **already correct** |
| `docs/architecture/decisions/ADR-059.md:396` | cites both as baseline ids | no change — the pair is cited, not the assignment |
| `docs/architecture/designs/M-WINAMP-PLAYER.md:326`, `:358` | cite both / the range | no change |
| `docs/architecture/designs/M-WINAMP-PLAYER-VE-review.md:79` | cites both | no change |
| `app/tools/run_serialdbg_tests.py` (17/18 bodies, docstrings, registry) | Spotify=17, WebRadio=18 | **no change — this is the reference** |
| quality artifacts (LL-122/123, BP, audit log, tasks-archive) | Spotify=17 | **no change, and must not be changed** |

**Net: 4 doc edits + 2 firmware comment edits, zero test-code change.** The opposite choice — fixing
the code — costs 2 function renames plus registry, 2 firmware comments the other way, and either
falsifying or annotating **five** closed quality documents. Both edits are outside VE's write scope;
this is filed for @Architect (doc rows, VE-review, M-TESTBASE) and @Developer (the two firmware
comments).

**Until it is settled, treat every bare citation of `T_PLR_17` or `T_PLR_18` as ambiguous** and
resolve it by reading which mode the surrounding text is about.
