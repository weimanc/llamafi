# VE Review — the test restructure, against `feature_inventory` and `cross_feature_matrix`

> Reviewer: **@VE**
> Status: **review** — 2026-08-16
> Reviews: [M-TESTARCH](M-TESTARCH-test-architecture.md) · [M-TOOLING](M-TOOLING-host-tool-architecture.md) ·
> [M-QUALITY map](M-QUALITY-improvement-map.md)
> Against: `docs/project/feature_inventory.yaml` (81 features) ·
> `docs/project/cross_feature_matrix.yaml` (65 interactions) — both Developer-owned, VE-read
> Answers: gap analysis · test grouping · **is there a sufficient VE counterpart to the designed work?**

**Headline.** The traceability that exists between features and tests is **more than half fictional**,
and the structural programme now driving the codebase has **no VE counterpart at all**. Of those two,
the second is the more serious: eleven design documents propose changing how the system is built, and
VE has reviewed one of them.

**Methodological note, recorded because it caused a wrong first count.** The two sibling artifacts use
**different field names for the same concept** — `feature_inventory` says `test_ids:`, and
`cross_feature_matrix` says `test_coverage:`. Same owner, same purpose, adjacent files. Any tool that
joins them must know both, and every hand-audit will get one of them wrong once. **Filed as a finding
in its own right (G6).**

---

## 1. Gap analysis A — `feature_inventory.yaml`

81 features. Status: 66 `implemented`, 6 `planned`, 3 `partial`, 2 `in_progress`, 4 other.

| Measure | Count | |
|---|---:|---|
| Features with **empty `test_ids`** | **41 / 81** | **51 %** |
| …of which status is `implemented` | **35** | shipped, and claiming no test |
| Distinct test ids claimed across all features | 325 | |
| …that resolve to **no executable test body** | **176** | **54 %** |
| …that appear **nowhere in `docs/verification/`** either | 38 | not even planned |

**Read the two halves together and the picture is worse than either alone.** Half the features claim
no tests; of the claims the other half makes, more than half do not resolve. The inventory therefore
cannot answer "is this feature tested?" in either direction — a `test_ids: []` may mean untested *or*
unrecorded, and a populated `test_ids` may mean tested *or* aspirational.

This is the same disease M-TESTARCH §6 measured from the other end (95 of 148 doc-table ids have no
code; 56 registry ids have no doc row). **Three artifacts — inventory, test plan, runner — pairwise
disagree, and no two of them are joined by anything a machine checks.**

## 2. Gap analysis B — `cross_feature_matrix.yaml`

65 interactions: 13 `high` risk, 24 `medium`, 28 `low`.

| Measure | Count | |
|---|---:|---|
| Interactions with **empty `test_coverage`** | **40 / 65** | **61 %** |
| …**high risk** with no coverage | **8 / 13** | **62 % of the high-risk set** |
| Distinct ids claimed | 58 | |
| …not executable | **34** | **58 %** |

AGENTS.md states the rule plainly: *"Each matrix interaction needs ≥1 cross-feature test."* It is met
for 25 of 65, and for 5 of 13 high-risk.

### 2.1 The eight uncovered high-risk interactions — VE's actual worklist

| id | Interaction | Type | Why it is high risk |
|---|---|---|---|
| `X003` | `poll-001` × `api-002` | shared_state | shared `WiFiClientSecure`; the stop-before-connect discipline is the whole fix |
| `X052` | `sdfs-001` × `localplay-001` | resource_contention | loopTask and the audio pump task both touch the filesystem |
| `X054` | `plmodel-001` × `playlist-002` | dependency | `pleditView` absorbed `drawPlaylist()` wholesale |
| `X055` | `plmodel-001` × `webradio-001` | shared_state | WebRadio's independently-evolved PLEDIT copy |
| `X057` | `player-state-001` × `app-registry-001` | dependency | taskbar asserts WebRadio is the **last** `AppId` |
| `X061` | `playorder-001` × `webradio-001` | shared_state | capability mask rewrites the "Spotify-only zones" hardcoding |
| `X062` | `playorder-001` × `plmodel-001` | shared_state | shuffle permutes `playOrder[]`; `viewOrder[]` — what PLEDIT renders **and what SAVE writes** — is never touched |
| `X064` | `player-state-001` × `app-registry-001` | dependency | ADR-059 D10 compile-time-optional player modes |

**`X062` is the one VE should escalate.** A divergence between what is played, what is displayed and
**what is persisted** is a silent data-correctness bug, not a UI bug — the failure mode is a saved
playlist that does not match what the user saw. It is untested, and no id is reserved for it.

**`X057` and `X064` are the same structural fact the levelization audit found independently**:
`taskbar/taskbar.h → appShell.h` is one of only two genuine D2a violations
([M-LEVELS §4](M-LEVELS-dependency-audit.md)). An enum-tail ordering assumption is exactly the class
of thing that breaks silently when the registry changes — and the registry is generated, so it *will*
change. **Two artifacts, arrived at from opposite directions, naming the same edge. That agreement is
the strongest evidence in this review.**

## 3. Grouping and reorganisation — what the data says the families should be

M-TOOLING TASK-480 proposes splitting the runner into one module per app. **VE objects: that mirrors
the app list and reproduces the current problem in new files.** The evidence from §1–§2 and from
M-TESTARCH §2.1 supports a different cut:

```
suite/
  conformance/          GENERATED — parameterised over app_ids_gen / AppSettings
    app_contract.py       7 rows × 13 apps      (M-TESTARCH §2.3)
    settings_contract.py  6 rows × 58 fields
  interaction/          ONE MODULE PER RISK, from cross_feature_matrix
    x_shared_state.py     X055 X061 X062 …      ← 8 high-risk ids land here first
    x_contention.py       X052 …
    x_dependency.py       X057 X064 …
  behaviour/            HAND-WRITTEN — genuinely unique per app
    stock.py  webradio.py  planeradar.py  player.py  teletext.py  clock.py
  shell/                the L2 entry surface itself (T077…T096, busy/cooldown)
  _lib/                 helpers, named and owned
```

Three grouping principles, each falsifiable against the data:

1. **Conformance is generated, never written.** It is the only cut that makes the 27 empty cells in
   M-TESTARCH §2.1 visible, and the only one that cannot hardcode app order.
2. **Interaction tests are grouped by `interaction_type`, not by app** — because that is how the
   matrix already classifies them, and because a shared-state test and a resource-contention test
   need different rigs (state injection vs. concurrent load). Grouping them by app would split the
   rig work across six files.
3. **Behaviour modules hold only what is genuinely unique.** On today's suite that is roughly the
   Stock chart/heatmap family, WebRadio's retry machine, PlaneRadar's interpolation, Player's M3U
   handling — the material that is *worth* 209 hand-written bodies. Everything else is conformance
   with different nouns.

**Expected effect on the count:** ~30 of the 209 bodies are per-app conformance copies (Weather and
Crypto alone are two verbatim sets of five). They collapse into 2 generated modules whose cell count
*grows* to ~91 app cells + ~348 settings cells, with the gaps explicit rather than absent.

## 4. VE process sufficiency — the direct answer is **no**

Eleven structural design documents now exist. Their VE counterpart:

| Design doc | VE review? | Cited in `test_plan.md`? |
|---|:--:|:--:|
| M-SRCLAYOUT | — | yes |
| M-CONCURRENCY | — | yes |
| M-DOCLIFE | — | yes |
| M-CODEQUAL | *(Architect review only)* | yes |
| **M-TOOLING** | **—** | **no** |
| **M-TESTARCH** | **—** | **no** |
| **M-LEVELS** | **—** | **no** |
| **M-ERRMODEL** | **—** | **no** |
| **M-VENDORING** | **—** | **no** |
| **M-DISPLAYSEAM** | **—** | **no** |

**Zero VE reviews across the structural programme, and six of ten documents are not referenced by
VE's own test plan at all.**

This is not the project's normal standard. The *feature* work has a strong VE tradition — dedicated
VE reviews exist for M-APP-REGISTRY, M-PR-LOCATIONS, M-WINAMP-PLAYER, M-COUNTRY-PICKER,
M-HOME-LOCATION, M-SETTINGS-WIRE2, M-WEBRADIO-POSBAR-SLEW, touch-ux-panel, velocity-scroll,
touch-capture, heatmap-reliability, sys-reboot-wifi-multi. **The habit exists and is good. It simply
was never applied to structural work**, presumably because structural work has no feature id — which
is exactly why it slips past a process keyed on `feature_inventory`.

### 4.1 Why this matters more here than for a feature

Per AGENTS.md, VE's standing obligations are *"challenges Developer on testability before
implementation finalised"* and *"challenges Architect on testability of interface contracts before
they are finalised."* Both are unmet for this programme, and the programme is unusually exposed:

- **The verification paradox.** M-TESTARCH §9 records that the regression suite cannot verify a
  refactor of itself, and that ADR-059 D13 requires ≥3 pre-declared baseline runs. **That baseline was
  never taken for the two M-SRCLAYOUT stages that already landed.** TASK-488 closed by comparing
  compiled binaries instead — a stronger check, and the right call, but it is not the D13 process and
  nothing recorded the substitution as a precedent.
- **The precedent that VE review works.** When VE *did* review reserved ids for M-CONCURRENCY,
  **two of five (`T_CC_03`, `T_CC_04`) were discarded because the invariants they asserted were
  factually wrong**, and a sixth (`T_SRC_09`) was added. A 40 % correction rate on one small batch is
  the strongest available argument that the other ten documents need the same pass.

### 4.2 VE's minimum counterpart, in priority order

1. **Reserve ids for the 8 uncovered high-risk interactions** (§2.1), `X062` first. Reserved ids
   with a stated obligation are how the M-ARCH families already work in `test_plan.md`.
2. **Challenge M-TESTARCH's own testability claims** — specifically §3b's assertion that `get idle`
   can replace settling sleeps, and §2.3's claim that rows A5/A6 are statically decidable. Both are
   Architect assertions with no VE pass. Note the precedent: the last time VE checked such a list,
   `T_CC_01`'s "review-shaped" note was **overturned** and two ids were **deleted**.
3. **Own the flake policy** (M-TESTARCH §7). It is proposed by the Architect and sits squarely in
   VE's artifact; `ve_suite_base.flake()` is VE's code.
4. **State the baseline rule as VE's**, and record the TASK-488 binary-comparison substitution as an
   accepted alternative to D13's ≥3 runs, or reject it. Right now it is an undocumented precedent.
5. **Take a position on the grouping in §3 before TASK-480 lands.** Once the runner is split, the
   family boundaries are expensive to move — and VE owns the taxonomy those families are supposed to
   mirror (M-TESTARCH OQ4).

## 5. Findings summary

| id | Finding | Severity |
|---|---|---|
| **G1** | 41/81 features have empty `test_ids`; 35 are `implemented` | high |
| **G2** | 176/325 claimed feature test_ids (54 %) are not executable | high |
| **G3** | 40/65 interactions uncovered; **8 of 13 high-risk** | **high** |
| **G4** | 34/58 claimed interaction ids (58 %) are not executable | high |
| **G5** | **No VE review exists for any of the 11 structural design docs**; 6 are absent from `test_plan.md` | **high** |
| **G6** | The two sibling artifacts name the same field differently (`test_ids` vs `test_coverage`) | low, but it corrupts every audit |
| **G7** | `X062` (playOrder vs viewOrder vs what SAVE writes) is an untested silent data-correctness risk | **high** |
| **G8** | `X057`/`X064` restate a genuine D2a violation found independently by M-LEVELS — corroborated, not duplicated | medium |

**Cheapest first move**, consistent with this programme's standing rule (M-QUALITY §4): the
inventory↔plan↔runner join is a **three-way `check-docs` rule**, not three separate audits. It needs
G6 fixed first (one field rename), and it will land red on G1–G4 — which is the correct first result.
