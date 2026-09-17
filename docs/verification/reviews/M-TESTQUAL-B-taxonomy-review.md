# M-TESTQUAL WP-B — taxonomy, grouping, order, and duplicate tests

> Owner: **Verification Engineer**
> Status: complete — 2026-09-02
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Builds on: [WP-A harness review](M-TESTQUAL-A-harness-review.md) (finding **A-15** is discharged in §7.1)
> Covers: **Q7** (does the grouping and order make sense?) and **Q8** (duplicate tests?)
> Method: static audit only. No flash, no `run/test*`, no `run/dut-health`, no serial port opened.
> No module under `app/tools/` was imported except `suite.serialdbg` and `app_ids_gen` (rubric §5,
> WP-A finding A-12). `app/tools/gate/check_docs.py` was executed as a **subprocess** via its
> documented host-only CLI (`--no-git`), which is what `run/check-docs` does; it opens no port.

Every count below is produced by the command quoted next to it, run against the working tree at
`f880f52` on 2026-09-02.

---

## 0. The measurement harness for this document

```sh
cd app/tools && python3 -c "
import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_tests, build_health_tests, build_all_meta
T=dict(build_all_tests()); H=build_health_tests(); M=build_all_meta()
print(len(T), len(H), len(M))"
# -> 213  3  216
```

**A note for WP-C…H, learned running the gate against this file.** The index says a `-review.md`
suffix stops C6 reading these documents as a competing registry. That is only half true:
`is_exempt` suppresses *status* scanning, but `doc_test_entries` (`gate/check_docs.py:665-671`)
still binds any table row whose **first cell is a single bare id** — `cells[0].strip("`* ")`. A row
like `` | `T_PRM_01` | … | `` therefore resolves that id's C6.1 orphan finding and turns its
`id_binding_exceptions.md` row into a **stale exception**, which is a blocking failure. A first
cell holding two ids, an id plus any other text, or a non-id column is inert. This document keeps
one such annotation (§2.1) for that reason; `run/check-docs` is 5/5 with it.

213 runnable registry ids + 3 HEALTH ids in the separate registry (`__init__.py:44 build_health_tests`,
design §4.5) = **216 records**. The default selection is **210** — `runner.py:231-232` drops the three
interactive ids `T093/T094/T095` and `runner.py:290` drops the health ids.

---

## 1. Q7a — how much of the taxonomy is a statement, and how much is an inference?

> **Verdict: the taxonomy is almost entirely inference. Of 216 records, `cls` is DECLARED on 6
> (2.8 %), `scope` on 57 (26.4 %) and `effect` on 3 (1.4 %) — and all three `effect` declarations are
> on the three HEALTH ids, so no id in the 213-id suite proper declares an effect at all. The
> consequential number is the 43 CORE ids: not one of them is declared. Every one is CORE because
> `seed_cls()` (`_meta.py:155-163`) maps the seeded scope `shell|boot|taskbar|spotify-chrome` to
> CORE, and §13.3 is explicit that this is "a default, not an invariant". Under the held order switch
> those 43 inferred records are exactly the ids whose failure NOT-RUNs the other 167 — the blast
> radius of the whole design rests on a default nobody has affirmed.**

### 1.1 The census

```sh
cd app/tools && python3 -c "
import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
from collections import Counter
m=build_all_meta()
for k in ('cls','scope','effect','scope_seeded_by'):
    print(k, Counter(v[k] for v in m.values()))
for k in ('cls_declared','scope_declared','effect_declared'):
    print(k, Counter(v[k] for v in m.values()))"
```

| Axis | Declared | Seeded / defaulted | Declared % |
|---|---:|---:|---:|
| `cls` | **6** | 210 | 2.8 % |
| `scope` | **57** | 159 | 26.4 % |
| `effect` | **3** | 213 | 1.4 % |

Provenance of the seeded `scope`: **module 117, prefix 29, catch-all 70**
(`_meta.py:144-152`). The 29-by-prefix figure exceeds §13.2's measured 17 because `T_DH_`(3),
`T_TBFB_`(5) and `T_BI_`(4) are prefix rows too — the design counted only the four *app*-name
prefixes. The 134-of-213 seeding ceiling EC-D2 is written against is therefore met and exceeded,
and EC-D2 is satisfied. **EC-D2 is not the interesting number**; the declaration count is.

### 1.2 What is actually declared

The complete `cls` declaration set — six ids, two reasons:

| Id | Declared | Seed it overrides | Carrier | Evidence |
|---|---|---|---|---|
| `T_DH_01` `T_DH_02` `T_DH_03` | `cls=HEALTH` | CORE (via scope `shell`/`boot`) | `@meta` | `health.py:62` imports `meta`; the three decorators |
| `T093` `T094` `T095` | `cls=RIG`, `scope=rig` | CORE (catch-all `shell`) | `META_OVERRIDES` | `shell.py:3524-3528` |

That is the whole of it. `CORE` — the class that blocks — is **never declared anywhere**, and
`APP` is never declared either, which is why the class has zero members (TASK-566 baseline §4).

The 57 `scope` declarations carry exactly seven distinct reason strings:

```sh
cd app/tools && python3 -c "
import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
from collections import Counter
m=build_all_meta()
print(Counter(v['scope_reason'] for v in m.values() if v['scope_declared']))"
# -> winamp-view 27, shell-poll 11, taskbar-surface 7, settings-app 6,
#    calibration 3, cross-mode 2, wifi-identity 1
```

The adjudication rule §13.3 wrote for the Spotify/chrome split ("*if the id would still exist were
the Spotify app deleted, it is `spotify-chrome`*") was applied to 38 ids and produced two reason
strings; no id carries a per-id justification, so the rule's application is not reviewable
per id — only in bulk, which is how `T133` (§2.2) got a `shell-poll` reason it does not fit.

### 1.3 What the gate does and does not assert

`gate/check_test_meta.py:52-109 evaluate()` asserts: every id resolves to a scope; the scope is in
the enum; no case-only enum collision; every `scope`/`effect` override carries a reason; a
declaration may not restate its own seed (EC-D2); a catch-all outside `shell.py` is a failure.
`main():142-160` additionally asserts the meta id-set equals `tests ∪ health` and that `cls=HEALTH`
and `HEALTH_TESTS` are the same set.

It asserts **nothing about whether a `cls` is right**, and — by design (`:22-25`) — nothing about
seed-vs-declaration equality. Combined with §1.1, the practical consequence is:

> **A `cls` value has never been wrong in this repo, because no `cls` value has ever been written
> down.** 210 of 216 are whatever `seed_cls()` returned. The gate's green light means the records
> are *well-formed*, not that they are *true*.

---

## 2. Q7b — sample correctness check

> **Verdict: the `effect` axis is sound but vacuous; the `scope` axis is mostly right with one
> systematic hole; the `cls` axis contains a live P1. Effect first, because it was named as the
> highest-value check: there are no `effect: read-only` lies, and there cannot easily be, because
> `seed_effect()` defaults to `mutating` and only 4 of 216 records are read-only — I read all four
> and all four are honest. The axis is information-free rather than dishonest, and its only
> consumer (mode D descent admissibility, §16.3) was CUT (§20), so it is dead weight today. The
> real defect is on `cls`: at least seven ids are classed CORE whose body is a single app's
> feature test — `T-BUSY-01`, `T-BUSY-01b`, `T-BUSY-05`, `T-CDWN-02`, `T-CDWN-03`, `T-UART-01`,
> `T-ERR-07` all drive StockApp and assert on Stock's own fetch pipeline. Under the order switch a
> Stock outage NOT-RUNs all 167 FEATURE ids.**

### 2.1 The `effect` axis, exhaustively (not a sample — it is only 7 rows)

```sh
cd app/tools && python3 -c "
import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
for k,v in build_all_meta().items():
    if v['effect']!='mutating': print(k,v['effect'],v['module'],v['scope'],v['effect_declared'])"
```

| Id | Effect | Declared? | Body read | Verdict |
|---|---|---|---|---|
| `T_DH_01` | read-only | yes (`three-gets`) | `health.py` | correct |
| `T_DH_02` | read-only | yes (`ip+wifiCfg`) | `health.py` | correct |
| `T080` | read-only | **no — seeded** | `shell.py:145-158` — one `info`, field-presence + `heap<50000` | **correct** |
| `T083` | read-only | **no — seeded** | `shell.py:225-236` — one `help`, command-name presence | **correct** |
| `T_PR_04` | resetting | no — seeded | `planeradar.py:140 dut.send("reboot")` | correct |
| `T_PRM_01` (ledger orphan) | resetting | no — seeded | `planeradar.py:301 dut.send("reboot")` | correct |
| `T_PLR_26` | resetting | no — seeded | `player.py:1610 dut.send("reboot")` | correct |

**209 of 216 records (96.8 %) say `mutating`.** The seeder is conservative by construction
(`_meta.py:212-231`: unrecognised ⇒ `mutating`) and its reachability walk is genuinely transitive
— it follows helper calls into the fn's own module *and* `_helpers`, and family modules import
cross-family helpers by name (`shell.py:54`, `player.py:25`), so those resolve too. I could not
construct a false `read-only` and did not find one.

The cost of that conservatism is that the axis carries no signal. §16.3's admissibility table
would admit **2 ids** (`T_DH_01`, `T_DH_02`) into a descent — and mode D, the only consumer, is
CUT (§20). The field is correct, complete, gated, and used by nothing.

One residual blind spot worth recording rather than acting on: `seed_effect` classifies from
**command-string literals** (`_meta.py:174 _CMD_RE`). A command built in a variable and passed as
`dut.cmd(cmd)` is invisible. I found no such site in the suite; `dut` exposes no `tap()`/`drag()`
method that would bypass the literal (`lib/dut.py` defines only `send`, `cmd`, `cmd_drain`,
`cmd_raw`, `set_cooldown_zero` — and `set_cooldown_zero` is explicitly listed at `_meta.py:172`).

### 2.2 `cls` — FEATURE that should be CORE, and CORE that is really one app

The question "are there FEATURE-class tests that are really CORE" resolves to **no, and that is
itself the finding**: 167 ids are FEATURE and every one of them is FEATURE *by default*, so
nothing was mis-promoted — nothing was promoted at all. The APP class that §3 defines
(conformance rows A1–A7, "generated per app from `APP_ORDER`, never written per app") is empty
while its rows exist, hand-copied, as FEATURE — see §7.2.

The opposite error is real and material. Seven CORE ids exercise StockApp and nothing else:

| Id | Class (seed) | Scope (seed) | What the body actually drives | Evidence |
|---|---|---|---|---|
| `T-BUSY-01` | CORE | shell | `_switch_to_stock` → tap AAPL row → oracle is `chartLen>0` then `shellBusy==false` | `shell.py:1665,1673,1683,1691` |
| `T-BUSY-01b` | CORE | shell | Stock chart drill + 5D tab fetch, oracle `_stock_ok_count` advances | `shell.py:1707,1717-1729` |
| `T-BUSY-05` | CORE | shell | `stockMode` + `triggerFetch` + `switchApp` | mutation scan, §5.1 |
| `T-CDWN-02` | CORE | shell | `_stock_ok_count` delta across two taps | `_order.py:229-234` |
| `T-CDWN-03` | CORE | shell | Stock fetch + cooldown | mutation scan |
| `T-UART-01` | CORE | shell | `_switch_to_stock` → tap AAPL → 20 `get heap` under Core-0 load | `shell.py:3149-3169` |
| `T-ERR-07` | CORE | shell | `switchApp Stock` + `set fetchFailed 1/0`, oracle `activeError.active` | `shell.py:3385-3391` |

§13.2 measured this exact set ("**9 residue ids reach into Stock**") and prescribed declaring
them. **Zero `scope="Stock"` declarations exist** (§1.2's list contains none). The seed stood.

Two of the seven have a genuinely shell-level oracle (`T-BUSY-01`'s `shellBusy` auto-clear,
`T-UART-01`'s JSON integrity) and are defensible as CORE. But their *precondition* is a live Stock
HTTPS fetch: `T-BUSY-01` FAILs — not skips — if `chartLen` does not exceed 0 in 45 s
(`shell.py:1683-1688`), and the flaky-tests memory records exactly that network dependency for
the Stock family. **Today that is one red cell at index 169 of 210. Under the switch it is a CORE
red at index 14 that NOT-RUNs 167 ids** (`_gate.py:124-135`).

`T133` is the second `cls` defect and it is a different shape:

* Declared `scope=spotify-chrome` (`shell.py:722`), seeded `cls=CORE`.
* Part A is a **host-side grep of an upstream source file** —
  `lib/SpotifyArduino/src/SpotifyArduino.cpp`, resolved by four `.parent` hops
  (`shell.py:730`), failing with `source not found` if the file is absent (`:731-733`). Per
  M-TESTARCH §2b's tier rule and §13.5's last row, a static source check belongs in the **T1 host
  tier**, not in a DUT class at all.
* Part B is a 90 s serial soak for `Guru Meditation Error` (`shell.py:741-751`).
* It drives no Spotify chrome. Its `spotify-chrome` scope is wrong on §13.3's own adjudication rule:
  delete the Spotify app and this test still exists.
* As CORE, a checkout without the upstream `lib/SpotifyArduino/` tree fails it — and under the
  switch that missing *file on the host* NOT-RUNs the entire FEATURE suite.

### 2.3 `scope` — bodies that drive another app

Sampled 58 ids across every scope and every id-prefix family. The scope value is right for the
large majority; the failures cluster:

| Id(s) | Records scope | Body drives | Verdict | Evidence |
|---|---|---|---|---|
| `T-BUSY-01/01b/05`, `T-CDWN-02/03`, `T-UART-01`, `T-ERR-07` | `shell` (catch-all) | **Stock** | wrong — §13.2 said declare, nobody did | §2.2 table |
| `T-ERR-02` | `shell` | Spotify **+ Clock** (`switchApp 1`/`0`) | ambiguous, defensible | `shell.py:3302-3305` |
| `T-ERR-06` | `shell` | **Clock + Matrix** | wrong — it is an offline-app property | `shell.py:3371-3372` |
| `T-BUSY-03` | `shell` | Clock, Weather, Crypto, Matrix, Life, **Aquarium** | genuinely multi-app; `shell` is right | `shell.py:1766-1770` |
| `T133` | `spotify-chrome` (declared) | a host file + the serial log | wrong (§2.2) | `shell.py:722,730` |
| `T_DH_01`, `T_DH_03` | `shell` | console + `switchApp` | right, and deliberate (`_meta.py:121-127`) | `_meta.py:128` |
| `T_PMT_01`, `T_PMT_02` | declared `Spotify`/`WebRadio` | cross-mode | right — the reference case §13.3 protects | declaration list |
| `T_CLK_01…14` | `Clock` (module) | Clock, except `T_CLK_09` which drives **Matrix** (`switchApp 4`) as a waypoint | right | `clock.py:152` |
| `T_WX_*`, `T_CX_*`, `T_MA_*`, `T_GOL_*` | prefix-seeded | their own app | right | `shell.py:1216-1580` |
| `T-SET-01…08` | declared `Settings` | Settings, and `T-SET-08` uses **Crypto** as the previous app | right | `shell.py:3106-3140` |
| `T162–T166`, `T242`, `T_TBFB_*` | declared `taskbar` | taskbar | right | declaration list |
| the 30 `Stock`, 29 `LocalPlayer`, 31 `WebRadio`, 9 `PlaneRadar`, 3 `Teletext` module-seeded ids | module | their own app | right on inspection of the mutation scan (§5.1); no body drives a foreign app | §5.1 |

**Net: 9 of 58 sampled ids carry a scope I judge wrong (7 Stock-in-shell, `T-ERR-06`, `T133`).**
All nine are in `shell.py`'s catch-all residue, which is precisely the population §13.2 said would
need declarations and which received them for Settings, taskbar, winamp-view and shell-poll but
not for Stock or the offline apps.

---

## 3. Q7c — is `--scope` a usable selection mechanism?

> **Verdict: for an app you own, yes; for anything else, no. Three separate holes. (1) The
> file→scope map cannot resolve 74 of the 135 firmware source files — including everything under
> `app/src/settings/`, `app/src/player/`, `app/src/audio/`, `app/src/mem/arena/`, `app/src/touch/`,
> `app/src/util/` and 25 files at the root of `app/src/` — and `--scope <path>` on any of them
> exits with an error, so EC-D4's "one command from a changed file" fails for 55 % of the tree.
> (2) Two of the eight path prefixes point at directories that do not exist, so the `taskbar` scope
> (12 ids) is unreachable from any path and `spotify-chrome` is reachable only by an accidental
> substring match. (3) `--scope Stock` returns 30 ids and omits the 7 CORE ids in `shell.py` that
> drive Stock — the ids most likely to catch a Stock regression are the ones the selector drops.**

### 3.1 The file→scope map, measured

```sh
cd app/tools && python3 -c "
import sys,os,glob;sys.path.insert(0,'.')
from suite.serialdbg import _meta
root=_meta.REPO_ROOT
files=[f for f in glob.glob(os.path.join(root,'app/src/**/*'),recursive=True)
       if os.path.isfile(f) and f.rsplit('.',1)[-1] in ('cpp','h')]
ok=0;bad=[]
for f in files:
    rel=os.path.relpath(f,root)
    try: _meta.scope_from_path(rel); ok+=1
    except ValueError: bad.append(rel)
print(len(files),'files;',ok,'resolve;',len(bad),'do NOT')"
# -> 135 files; 61 resolve; 74 do NOT
```

Unresolvable, by directory: `app/src` root **25**, `app/src/gen` 13, `app/src/settings` 12,
`app/src/util` 6, `app/src/stock` 5 (everything except `stockApp.cpp`), `app/src/audio` 2,
`app/src/display` 2, `app/src/mem/arena` 2, `app/src/player` 2, `app/src/sd` 2, `app/src/touch` 2,
`app/src/ui` 1.

Concretely: a developer who changes `app/src/settings/settingsSection.h` — the file whose three
constants `shell.py:2925-2927` mirrors and which drives every Settings tap test — gets
`--scope: cannot resolve app/src/settings/settingsSection.h to a scope`
(`_meta.py:330-332`). The `Settings` scope exists and holds 6 ids; the path map cannot reach it.

### 3.2 Two path prefixes name directories that do not exist

`_meta.py:298-307 _PATH_SCOPES` lists `("app/src/taskbar", "taskbar")` and
`("app/src/spotify", "spotify-chrome")`.

```sh
ls -d app/src/taskbar app/src/spotify
# ls: cannot access 'app/src/taskbar': No such file or directory
# ls: cannot access 'app/src/spotify': No such file or directory
```

The taskbar source is `app/src/shell/taskbar.{h,cpp}`, which matches the earlier
`("app/src/shell", "shell")` row and resolves to `shell` (18 ids), not `taskbar` (12 ids).
**No path resolves to the `taskbar` scope.** The `spotify-chrome` row resolves only because
`rel.startswith("app/src/spotify")` matches the *files* `app/src/spotifyTask.h` and
`app/src/spotifyTaskStorage.cpp` — a prefix-match accident, not a directory. Both rows are
untested: `gate/check_test_meta.py` validates that `PREFIX_SCOPES` values are in the enum
(`:174-176`) but never checks that a `_PATH_SCOPES` prefix exists on disk.

### 3.3 Scope-by-scope usefulness

| Scope | Ids | Would selecting it catch a regression in that surface? |
|---|---:|---|
| `WebRadio` | 31 | yes |
| `Stock` | 30 | **partially — misses the 7 CORE Stock drivers (§2.2)**; those are where Stock's fetch pipeline is actually asserted |
| `LocalPlayer` | 29 | yes; `T_PMT_01/02` are correctly declared away |
| `Spotify` | 28 | yes for the winamp view |
| `shell` | 18 | over-broad: it is the catch-all, holding 7 Stock tests, 1 Clock/Matrix test, `T079/T080/T083` console shape and `T148` |
| `Clock` | 14 | yes, but see §7.2 — most of the 14 assert the same thing |
| `taskbar` | 12 | yes by name; **unreachable by path** (§3.2) |
| `spotify-chrome` | 11 | yes, except `T133` (§2.2) |
| `PlaneRadar` | 9 | yes |
| `Settings` | 6 | yes by name; **unreachable by path** (§3.1) |
| `boot` `Weather` `Crypto` | 5 each | yes |
| `Life` | 4 | yes |
| `Teletext` `Matrix` | 3 each | yes |
| `rig` | 3 | **never selectable.** The only rig ids are `T093/94/95`, and `runner.py:231-232` removes them from `default_tests` unconditionally. `--scope rig` with no `--tests` therefore hits `runner.py:306-309` "selects none of the 210 candidate ids" and exits. CLAUDE.md documents `rig` as a valid `--scope` value |
| `Aquarium` | **0** | **orphan app.** `Aquarium` is in `APP_ORDER` and in the `app/src/**/*App.cpp` map (`_meta.py:289`), so `--scope app/src/aquarium/aquariumApp.cpp` resolves — to an empty set and an exit. Its only appearance in the suite is as one entry in `T-BUSY-03`'s passive-app loop (`shell.py:1768`) |

```sh
cd app/tools && python3 -c "
import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta,_meta
have={r['scope'] for r in build_all_meta().values()}
print([s for s in _meta.SCOPES if s not in have])"
# -> ['Aquarium']
```

---

## 4. Q8a — registry order today vs the class order the switch would impose

> **Verdict: the switch is a pure "move the 43 CORE ids to the head" transform and nothing else.
> Within a class the sort is stable (`_order.py:63`), so no intra-family order changes at all —
> every FEATURE id keeps its neighbours and shifts uniformly by +43. TASK-566's "210 moved, 6505
> inverted pairs" is arithmetically right but reads as more disruption than the transform contains:
> the 6505 inversions are exactly the 43×167 CORE-before-FEATURE pairs minus those already in that
> order. The consequence that matters is not that ids move, it is that **43 ids acquire the power to
> NOT-RUN the other 167**, and §1 established that none of those 43 was ever affirmed as CORE.**

### 4.1 What the switch changes, precisely

`runner.py:454-462` calls `_gate.run_suite(..., class_order=_gate_on)` where `_gate_on` is
`args.class_order and not args.dut_health` (`runner.py:378`), defaulting to
`os.environ.get("DUT_CLASS_ORDER","")=="1"` (`runner.py:250-251`). With it **off** — today's held
state — `_gate.run_suite` executes `selected` in registry order, runs no health phase, sets
`blocked_by` never (the only writer is guarded by `class_order and cls=="CORE"`, `_gate.py:128`),
and returns `print_results()`'s own 0/1. That is a genuine no-op path; `_gate.py:96-98` says so and
the code bears it out.

With it **on**, four things happen, in this order:

1. **HEALTH phase** (`_gate.py:102-114`, `health_phase` at `:51`). `runner.py:379-380` replaces
   `health_selected` with the whole health registry. A failure → every selected id gets
   `not_run(tid, "HEALTH/<id>")` and the run exits **4**. A pass contributes **no** RESULTS rows
   (`_gate.py:70-77`).
2. **Reorder** (`_gate.py:115-119`) via `_order.class_order` = `sorted(ids, key=rank)`, stable.
3. **CORE blocking** (`_gate.py:128-135`): the first CORE `FAIL` sets `blocked_by`, and every
   subsequent id whose class is in `CORE_BLOCKS = ("APP","FEATURE")` (`_order.py:49`) is recorded
   `NOT-RUN`. CORE ids after it still run.
4. **Exit-code vocabulary** widens to include 4.

### 4.2 The diff, re-derived

```sh
cd app/tools && python3 -c "
import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_tests,build_all_meta,_order
T=build_all_tests();M=build_all_meta()
ids=[k for k in T if k not in ('T093','T094','T095')]
after=_order.class_order(ids,M)
print(len(ids), len(_order.moves(ids,after)), len(_order.inverted_pairs(ids,after)))"
# -> 210  210  6505
```

Matches the TASK-566 baseline exactly. Class census of the **default selection**: RIG 0, HEALTH 0,
CORE 43, APP 0, FEATURE 167 — the three RIG ids are the interactive ones, excluded, and the three
HEALTH ids live in the other registry. So under the switch the run is 43 CORE then 167 FEATURE,
and the HEALTH gate runs ahead of both.

The 43 CORE ids currently occupy indices **119–209** (they are not contiguous — `shell.py`'s CORE
and FEATURE ids interleave from 119 on). Selected movements:

| Id | Class | Index now | Index under switch | Δ |
|---|---|---:|---:|---:|
| `T-BUSY-01` | CORE | 169 | 14 | −155 |
| `T-CDWN-02` | CORE | 175 | 20 | −155 |
| `T-UART-01` | CORE | 200 | 33 | −167 |
| `T-BGPOLL-01` | CORE | 201 | 34 | −167 |
| `T-ERR-04` | CORE | 206 | 39 | −167 |
| `T-ERR-07` | CORE | 209 | 42 | −167 |
| `T133` | CORE | 131 | 6 | −125 |
| `T178` | FEATURE | 35 | 78 | +43 |
| `T_PR_04` (reboot) | FEATURE | 20 | 63 | +43 |
| `T_PMT_04` | FEATURE | 116 | 159 | +43 |

Every FEATURE id is +43. **No FEATURE/FEATURE pair inverts**, which is the load-bearing property
`_order.py:23-26` claims and which the stable sort delivers. Intra-family dependencies — the Clock
family's `_restore_spotify_from_clock` chain, the Stock family's internal sequencing, the
player family's `plLoad`→`plPlay` chains — are all preserved by the switch.

---

## 5. Q8b — order dependence: who leaves state, who reads it

> **Verdict: the suite has one disciplined restore primitive and forty-one hand-rolled mutations
> around it. `set` commands are issued 179 times across 179 ids; exactly one restore is
> exception-safe (`_bgpoll_suspended`, `_helpers.py:444`), used at 20 of the 41 `bgPoll` sites. I
> found six clusters where a test's result depends on what ran before it, and — this is the
> important half — **three of them are invisible to the `EDGE_ADJUDICATION` enumeration TASK-566
> delivered as the switch's precondition**, because `edge_candidates()` only matches counter words
> compared against 0 or 1 (`_order.py:94-111`). A precondition SKIP keyed on `ready is True`, an
> in-RAM setting left behind by a helper, and a mid-suite reboot all pass straight through that
> scanner. The enumeration is described as over-reporting on purpose; on these three shapes it
> under-reports, which is the direction that hands the switch a false all-clear.**

### 5.1 The mutation census

```sh
cd app/tools/suite/serialdbg && grep -ohE '(cmd|send|cmd_drain)\(\s*f?"set [a-zA-Z_]+' *.py \
  | sed -E 's/.*"set //' | sort | uniq -c | sort -rn
# 41 bgPoll, 17 playerMode, 16 clockStyle, 15 fetchFailed, 11 stockMode, 10 fetchErrorCode,
#  9 wrPlay, 8 triggerFetch, 8 prRange, 8 prPollSec, 8 lastHttp, 7 wrStop, 7 wrAutoSkip,
#  7 triggerHeatmap, 6 wrDeadUrls, 6 songDuration, 6 backoff, 5 plPlay, 5 cooldown, …
```

179 of the 213 registry ids issue at least one `set`, `switchApp` or `reboot` in their own or a
reachable helper's source (script in §0's shape, using `_meta._reachable_source`).

**`set queue N` does not appear in the suite at all** (`grep -rn 'set queue' suite/serialdbg/*.py`
→ no matches). It is a manual debug injection recorded in project memory, not a harness path; no
registered test depends on it and no registered test leaves a queue snapshot behind.

### 5.2 The order-dependence table

| Cluster | Mutated by | Restored? | Read / spoilt by | Live today? | Under the switch |
|---|---|---|---|---|---|
| **C1 — `stockMode` + the Stock fetch pipeline** (`stockMode`, `fetchOkCount`, `lastQuoteFetch`, `lastHeatmapFetch`, in-flight `triggerFetch`) | `_helpers.py:195-207 _switch_to_stock` issues `set stockMode 0` on **every** entry; `_restore_from_stock` (`:210-217`) restores the **app only, never `stockMode`**. Callers: the whole Stock family plus CORE `T-BUSY-01/01b/05`, `T-CDWN-02/03`, `T-UART-01` | **no** | `T173` (needs `lastQuoteFetch != 0`, else SKIP), `T178` (needs `chartLen == 0` at rest), `T193`/`T196` (absolute `>0` a predecessor pre-satisfies), `T231` (sets its own) | yes — `T178` measured at `chartLen=33` on 2026-07-10 | **worse.** The six CORE Stock drivers move from indices 169–200 to 14–33; the 30-id Stock family moves to 69–98. Every Stock cell now runs *after* six CORE fetches instead of before them. TASK-566 named `T178`/`T173`/`T193`/`T196`; the mechanism is the whole family |
| **C2 — `bgPoll`** | 41 sites. Guarded by `_bgpoll_suspended` at 20 (13 shell, 2 webradio, 2 planeradar, 2 stock, 1 def). **Two hard leaks:** `T_PMT_04` (`player.py:1854`, no matching `set bgPoll 1` anywhere in its body) and `T-BGPOLL-02` (`shell.py:3207`, relies on `reconnect` to restore — if `reconnect` regresses the test fails *and* leaves polling off) | partial | Everything Spotify-facing. `T-BGPOLL-01` opens with `dut.cmd("set bgPoll 1")` and the comment *"Ensure we start in a clean state"* (`shell.py:3176-3177`) — that line is a compensator for a predecessor's leak | yes — `T_PMT_04` (idx 116) leaves `bgPoll=0` for the remaining 94 ids | **better.** All six spotify-chrome CORE ids move ahead of `T_PMT_04` and stop inheriting its leak. The 51 FEATURE ids after it still do |
| **C3 — `playerMode`** | `_helpers.py:286-318 _restore_spotify` writes `set playerMode spotify` on every restore (17 `set playerMode` sites overall). Never restored to the prior value; the runner takes an entry and an exit snapshot precisely because of this (`runner.py:369-372`, `:437-442`, TASK-407) | **no, by design** | `T_PLR_01/02/04/05` (mode round-trip and persistence), `T_TBFB_03`, the `T_PMT_*` cross-mode cells | yes, and accepted | changed: the 12 taskbar CORE ids that call `_restore_spotify` move ahead of the 29-id player family, so the player family now starts from `playerMode=spotify` rather than from whatever WebRadio left |
| **C4 — `clockStyle` (persisted)** | 16 sites, all in `clock.py`. `_restore_spotify_from_clock` (`clock.py:17-21`) writes `set clockStyle 0` — but **`T_CLK_12` never calls it** (`clock.py:193-205`) and exits having set style 3 | almost | `T_CLK_02` asserts "defaults to digital" — and is immune only because it forces `set clockStyle 0` first (`clock.py:44`), which also makes it a tautology (§7.3) | contained; `T_CLK_13/14` set their own style | unchanged — clock is a single FEATURE family and the stable sort preserves its internal order |
| **C5 — injected Spotify error state** (`lastHttp`, `backoff`, `lastOkMs`, `fetchFailed`) | `T-ERR-01` (restores `lastHttp 200`), `T-ERR-02` (restores), `T-ERR-04` sets `lastHttp 200`+`backoff 0`+`lastOkMs 0` then `lastOkMs 1` and **restores none of the three** (`shell.py:3328-3331`), `T-ERR-05` restores `lastHttp` but deliberately leaves `backoff 0` (`shell.py:3350-3355`), `T-ERR-07` restores `fetchFailed 0` | partial | `T084`/`T091` do their own `set backoff` round-trip so they are immune; the Spotify poll's own state machine is not | **latent** — `T-ERR-04/05` are at indices 206/207, so almost nothing runs after them | **NEW EXPOSURE.** They move to 39/40. `lastOkMs=1` and `backoff=0` are then injected into the board for the remaining 170 ids. **This is not in `EDGE_ADJUDICATION`** — the scanner cannot see it |
| **C6 — mid-suite reboots** | `T_PR_04` (`planeradar.py:140`), `T_PRM_01` (`:301`), `T_PLR_26` (`player.py:1610`) | n/a — they end a generation | Everything. A reboot resets `bgPoll`, `cooldown`, in-RAM `stockMode`, injected `lastHttp`/`backoff`/`lastOkMs`, and starts a new boot generation | yes: two reboots at indices 20 and 23, one at 111 | **inverted.** The two PlaneRadar reboots move to 63/66 — i.e. **after** the entire 43-id CORE block. Everything the CORE block established is wiped 20 cells into FEATURE. Today the reboots happen early and the CORE block runs on a settled board |

### 5.3 Tests that pass only because a predecessor set something up

| Id | Depends on | Failure mode if run alone or reordered |
|---|---|---|
| `T173` | a predecessor's Stock quote fetch (`lastQuoteFetch != 0`) | SKIP — silent non-result. Adjudicated ORDER-SENSITIVE |
| `T196` | a predecessor's screener fetch (`heatmapCount > 0` absolute) | false green. Adjudicated VACUITY |
| `T193` | a predecessor's chart fetch (`chart_len > 0` absolute, and `enterHeatmap()` re-uses cache when `lastHeatmapFetch != 0`) | false green. Adjudicated VACUITY |
| `T165` | `tbScrollOffset == 0` from a predecessor | SKIP. Adjudicated ORDER-SENSITIVE |
| `T_PMT_04` | a boot where nothing has acquired the arena | SKIP with an explicit precondition message (`player.py:1838-1847`). Adjudicated EDGE |
| **`T_WX_04`** | **`weatherReady` still false — i.e. Weather has never been visited this session** | **SKIP** (`shell.py:1420-1424`). `T_WX_01/02/03` all switch to Weather and run at indices 158–160, immediately before it at 161. **The test is already dead in a full-suite run and nothing says so.** Not in `EDGE_ADJUDICATION` |
| **`T_CX_04`** | identical, for `cryptoReady` | identical (`shell.py:1535-1539`), indices 163–165 precede it at 166. Not in `EDGE_ADJUDICATION` |
| `T-BUSY-01b` | a warm chart fetch that is not *too* warm | two SKIP exits (`shell.py:1723`, `:1732`) — "warm fetch too fast" |

`T_WX_04` and `T_CX_04` are the sharpest cases in this document: they are **guaranteed** to skip in
registry order, because their own family's A1/A2/A3 cells visit the app three times immediately
before them. They will still skip under the switch (the family moves as a block). They are
counted as coverage, they have never been able to run in a full suite, and the enumeration that
was delivered as the switch's precondition cannot see them because `ready is True` matches none of
`_order.py:94`'s counter words.

For scale on the SKIP surface generally: `grep -h 'skip(' suite/serialdbg/*.py | wc -l` → **262
call sites** (stock 86, shell 80, webradio 41, player 34, planeradar 12, teletext 5, `_helpers` 3,
health 1). TASK-574 owns the adjudication of these; WP-C…H will grade them per test.

### 5.4 The gap in the switch's own precondition

`_order.edge_candidates()` matches two shapes only: a baseline-assign-then-compare
(`_BASELINE_ASSIGN`/`_BASELINE_USE`, `:100-103`) and an absolute comparison of a **counter word**
against 0 or 1 (`_ABS_EDGE`, `:106-111`, word list at `:94-97`). It found 20 candidates and
`EDGE_ADJUDICATION` (`:193-248`) adjudicates all 20; `test_class_order.py` fails if any candidate
is unadjudicated, so the list cannot rot. That machinery is sound **for the shapes it looks for**.

Three order-dependence shapes are outside it, all demonstrated above:

* **precondition SKIP on a boolean readiness flag** — `T_WX_04`, `T_CX_04` (§5.3);
* **an in-RAM setting a shared helper writes and never restores** — `stockMode` (C1), `bgPoll` (C2),
  `playerMode` (C3);
* **injected debug state left behind on the pass path** — `lastOkMs`, `backoff` (C5).

The first is a silent non-result, the second and third are false-green sources. All three are in
the direction that hands the switch an all-clear it has not earned.

---

## 6. Q8c — does the order make sense for cost?

> **Verdict: there is no cost ordering today and the class order does not introduce one — but it
> improves the cost of a CORE failure enormously and worsens the time-to-first-result slightly.
> Today the six most blocking cells (`T-BGPOLL-*`, `T-ERR-*`) sit at indices 201–209, so a CORE
> regression is discovered after the whole ~40-minute run has been spent producing results that the
> design says are uninterpretable. Under the switch it is discovered inside the first ~6 minutes.
> That is the strongest cost argument for the switch and it is not made in the TASK-566 baseline.**

Static cost proxy — the worst-case bounded wait each id can incur (largest `timeout_s=` /
`deadline = monotonic() + N` in its reachable source), plus its summed fixed sleeps:

| Id | Worst-case wait | Sleeps | Class | Index now | Index under switch |
|---|---:|---:|---|---:|---:|
| `T_WR_TLS_01` | 180 s | 5.3 s | FEATURE | 79 | 122 |
| `T_PR_05` / `T_PRM_02` / `T_PR_02` | 90 s | ~2–6 s | FEATURE | 18–24 | 61–67 |
| **`T133`** | **90 s** | 0 | **CORE** | 131 | **6** |
| `T185` / `T170` | 65 s | ~3 s | FEATURE | 27, 43 | 70, 86 |
| `T192` `T193` `T194` `T202` `T203` `T196` | 60 s | 4–14 s | FEATURE | 48–55 | 91–98 |
| **`T-CDWN-02`** | **60 s** | 2.9 s | **CORE** | 175 | **20** |
| **`T-BUSY-01b`** | **45 s** | 4.3 s | **CORE** | 170 | **15** |
| `T_PLR_25` | 60 s | 1.8 s | FEATURE | 110 | 153 |

Plus `_drain_data_pipeline` (`_helpers.py:68`, default `timeout_s=200.0`), called by `T176`
(`stock.py:296`), `T178` (`stock.py:381`) and `T_WR_TLS_01` (`webradio.py:1103`) — a 200-second
worst case in three cells.

Reading:

* **Today**: the run front-loads the cheap Clock/Teletext family, then hits three 90 s PlaneRadar
  cells and two 200 s drains inside the first 40 ids, and puts every blocking cell last. An early
  failure wastes nothing (nothing blocks); a *late* CORE failure wastes the entire run.
* **Under the switch**: the first ~6 minutes are `T133` (90 s), `T-CDWN-02` (60 s), `T-BUSY-01b`
  (45 s) and 40 fast cells. A CORE failure inside that window converts the remaining ~35 minutes
  into 167 `NOT-RUN` rows *deliberately*, which is the design's whole point (`_gate.py:128-135`).
* The cost hazard the switch introduces is the flip side of §2.2: `T-BUSY-01` and `T-BUSY-01b`
  depend on a live Stock HTTPS fetch and are 45–60 s cells at indices 14–15. A network blip in the
  first minute now costs the whole run.

Neither order groups by cost, and nothing in the registry expresses cost. That is not a defect
against a stated requirement — no design asks for it — but a `--smoke`-style selection derived
from cost is the obvious follow-on once `cls` is trusted (WP-A A-19 makes the same point about
`run/test-smoke`'s hardcoded 11-id list).

---

## 7. Q8b — duplicate tests

### 7.1 Ids with two executable bodies — WP-A A-15 discharged

```sh
cd app/tools && for f in *.py; do ids=$(grep -oh "T_[A-Z0-9]\+_[0-9]\+\|\bT[0-9]\{3\}\b\|T-[A-Z]\+-[0-9]\+[a-z]*" $f | sort -u | tr '\n' ' '); [ -n "$ids" ] && printf "%-34s %s\n" "$f" "$ids"; done
# then: intersect each file's ids with build_all_tests() ∪ build_health_tests()
```

Seven registry ids appear in a standalone `app/tools/*.py`. Reading each occurrence:

| Id | Standalone file | Is it a second **body**? | Evidence |
|---|---|---|---|
| `T_PLR_13` | `test_fbrowser_player.py` | **YES** — "TASK-416 / T_PLR_13 (**playback half**)" | `test_fbrowser_player.py:2`; registry body `player.py:783` |
| `T_PLR_25` | `test_playorder_player.py` | **YES** — "TASK-418 / T_PLR_25 (**playback half**)" | `test_playorder_player.py:2`; registry body in `player.py` |
| `T_PMT_04` | `test_fbrowser_player.py:227`, `test_playorder_player.py:172`, `test_class_order.py:263`, `sd_health_probe.py:5`, `test_triage_context.py` | no — comments and a host-test fixture string | cited lines |
| `T237` | `webradio_long_soak.py:433,482` | no — prose | cited lines |
| `T088` | `coords.py:135` | no — a comment explaining a coordinate | `coords.py:135` |
| `T_PR_06` | `pr_delta_smoke.py:11` | no — prose | `pr_delta_smoke.py:11` |
| `T_PLR_20` | `test_playorder_player.py:9` | no — prose naming what the gate covers | `test_playorder_player.py:9` |

**A-15's list is complete and correct for registry ids: exactly two ids have two bodies.** Both
are the same pattern — the registry body covers the mechanism and a standalone script covers "the
playback half" on a different firmware variant (`cyd2usb_player`), with a different oracle and a
different reporting vocabulary (exit 0/2 rather than `lib/results.py` — WP-A §3.2). Neither script
carries a `TESTS`/`ALL_TESTS` dict, so C6 binds only the registry half; the plan's status for these
ids is therefore satisfied by whichever body someone happens to mean.

`T_AE_04` is a third case and it is worse than A-15 described:

* `test_ae04_teardown.py` is its only body, and has no registry dict
  (`grep -n '^ALL\|^TESTS' test_ae04_teardown.py` → nothing), so `test_registries()` cannot see it.
* `docs/verification/test_plan.md:497` declares it **`impl`** — which is precisely what C6.3
  (`gate/check_docs.py:747-756`) exists to catch: *"declared `impl` but is in no executable
  registry"*.
* C6.3 does **not** fire, because `doc_test_entries()` does not parse the id out of that row —
  it is inside a prose table cell, not an id-declaring heading or row:

```sh
python3 -c "
import sys; sys.path.insert(0,'app/tools/gate'); import check_docs as C
print('T_AE_04' in C.test_registries('.'), 'T_AE_04' in C.doc_test_entries(C.Corpus('.')))"
# -> False False
```

So the id is invisible on **both** sides of the gate, and `id_binding_exceptions.md` has no row for
it — correctly, since no finding fires. **The ledger is honest to its own rules; the rules have a
hole and `T_AE_04` sits in it.** `test_webradio_soak.py` also labels `T_AE_04` (per test_plan:497,
it is the only vehicle for `T_AE_01`–`03` and labels `T_AE_04` alone), so the id has two
label-sites and zero registry entries.

### 7.2 Distinct ids whose assertions are the same assertion

Comparing oracles, not names. Six clusters.

**D1 — the app-conformance matrix, hand-copied four times (12 ids).** §3's APP class exists to be
"*generated per app from `APP_ORDER`, never written per app*". It has zero members because its rows
were written per app, as FEATURE, in `shell.py`:

| Row | Matrix cell | Ids | Oracle — identical in all four |
|---|---|---|---|
| A1 | switch round-trip | `T_MA_01` `T_GOL_01` `T_WX_01` `T_CX_01` | `_restore_spotify` → `_switch_to(app)` → `_restore_spotify`, all three bools true |
| A2 | canvas-tap isolation | `T_MA_02` `T_GOL_02` `T_WX_02` `T_CX_02` | `dut.cmd("tap 137 120")` → `r["hit"] == "CLOCK"` |
| A3 | switch-back residue | `T_MA_03` `T_GOL_03` `T_WX_03` `T_CX_03` | `_switch_to(app)` → tap Spotify slot → `_check_residue(dut, tid)` |

Evidence: `shell.py:1216-1232` / `1277-1290` / `1354-1370` / `1470-1486` (A1);
`:1246`, `:1303`, `:1383`, `:1499` — the same literal `"tap 137 120"` four times (A2);
`:1271`, `:1326`, `:1406`, `:1522` (A3). Bodies differ only in the app name string and the
print/pass text. `T172` (`stock.py:177`) and `T182` (`stock.py:556`) are two further A3 copies, and
`stock.py:580` is a fifth `tap 137 120`.

A3 carries a second, independent defect: `_check_residue` (`_helpers.py:177-192`) calls `pass_()`
itself and returns `False` on failure, and all six call sites convert that `False` into `skip()`.
**The six A3 cells can PASS or SKIP. They can never FAIL.** A real canvas-residue regression
reports as a skip.

**D2 — Clock style set/readback, five ids for one assertion.**

| Id | Oracle | Evidence |
|---|---|---|
| `T_CLK_03` | `set clockStyle flip` ok+name, `get clockStyle` name=="flip" | `clock.py:57-63` |
| `T_CLK_04` | same, "nixie" | `clock.py:73-79` |
| `T_CLK_05` | same, "vfd" | `clock.py:89-95` |
| `T_CLK_02` | same, "digital" — after forcing `set clockStyle 0` first | `clock.py:44-47` |
| `T_CLK_06` | **the same assertion for all four styles in a loop** | `clock.py:106-113` |
| `T_CLK_08` | `set clockStyle nixie` → `get` name=="nixie" | `clock.py:138-141` |

`T_CLK_06` strictly subsumes `T_CLK_02/03/04/05`. `T_CLK_08` is byte-equivalent to `T_CLK_04` plus
a 0.4 s sleep — and its docstring claims *"persists in settings.json (save confirmed)"* while the
body never reboots and never reads a file, so the claim is unverified and the assertion is a
duplicate. `T_CLK_14` (`clock.py:232-239`) re-asserts `val==2` + `name=="nixie"` (= `T_CLK_04`
again) and adds one unique check, `last is True`.

**D3 — Clock "app is still Clock", three ids.** `T_CLK_01` (`clock.py:31-33`), `T_CLK_10`
(`:167-169`) and `T_CLK_13` (`:220-222`) all assert `get appId → id == 1`. `T_CLK_10` prefixes
`set clockStyle vfd`, `T_CLK_13` prefixes `set clockStyle flip` and re-asserts the style readback
(= `T_CLK_03`). `T_CLK_13`'s docstring claims the *"Flip animation tick gate — 30 ms while
animating vs 1000 ms stable"* and its own comment (`clock.py:211-212`) concedes *"We cannot
directly measure tick interval via serial"* — so the claim has no oracle and what remains is
`T_CLK_10`'s assertion with a different style.

**D4 — Settings drill-and-unwind, two ids.** `T-SET-03` (`shell.py:3005-3043`) and `T-SET-07`
(`:3075-3104`) assert the identical sequence — tap row 5 → `section==5`, tap app-list row *N* →
`submenu==N`, back → `submenu==-1`, back → `section==-1` — differing only in *N* (0 vs 2) and
`T-SET-03`'s extra `submenu == -1` check at level 1. `T-SET-07`'s own comment says the tests
*"assert indices, not app identity"*, which is the admission.

**D5 — Settings entry state, four ids.** `settingsSection == -1` on entry is asserted by `T-SET-01`
(`:2970`), inside `T-SET-02`'s loop (`:2996`), as `T-SET-06`'s outcome (`:3066`) and as `T-SET-08`'s
precondition (`:3125`). `T-SET-01`'s entire body is that one assertion.

**D6 — the WebRadio PLEDIT mirror, six ids.** `T_PLE_WR_155`–`160` are documented as *"WebRadio
PLEDIT battery **mirroring** `T155`–`T160`"* (`id_binding_exceptions.md:23`). This is a deliberate
same-assertion-different-source pair set (Spotify queue vs station list) and I do not call it a
defect — but it is 12 ids for 6 behaviours and it belongs in the register.

**Partial overlaps, recorded but not called duplicates:** `T-ERR-01` and `T-ERR-05` both assert
`lastHttp 403 → spotifyAuthError true` (`shell.py:3279-3285` / `:3350-3351`); `T-ERR-05`'s unique
half (survives `set backoff 0`) is real. `T-BGPOLL-01` and `T-BGPOLL-03` both assert
`set bgPoll 0 → enabled == 0` (`:3182-3183` / `:3235-3237`); `T-BGPOLL-03`'s force-poll half is real.

### 7.3 Ids that assert several unrelated things at once

| Id | The unrelated assertions | Why it matters |
|---|---|---|
| `T133` | (a) a **host file** contains the literal `CurrentlyPlaying current = {}`; (b) the DUT prints no `Guru Meditation Error` in 90 s | A failure cannot be localised to firmware or to the host checkout. Two tiers in one cell (§2.2), and the cell is CORE |
| `T_CLK_11` | heap delta < 4096 B across a style cycle **and** the style cycle itself completing | `clock.py:181-189`; a set-failure and a leak read the same |
| `T-SET-03` | section index, submenu index at L1, submenu index at L2, and two unwind steps — five assertions, five distinct `fail()` sites | `shell.py:3018-3040`. Localisable, but the id covers five behaviours |
| `T_CLK_02` | claims "default is digital" but writes `set clockStyle 0` first (`clock.py:44`) | Rubric **S3** — the oracle re-reads a value the harness just wrote. The claim in the docstring is untested by the body |
| `T_CLK_08` | claims settings-file persistence, asserts an in-RAM readback (`clock.py:138-141`) | Rubric **S3**; and a duplicate of `T_CLK_04` |
| `T_CLK_13` | claims a tick-rate gate, asserts style readback + `appId` | Rubric **S4/S13** — the claim has no oracle |

### 7.4 Registered-but-unreachable, and the honesty of the ledger

```sh
timeout 300 python3 app/tools/gate/check_docs.py --no-git 2>&1 | grep -i c6
# PASS C6: 265 registry ids, 424 doc ids, 224 bound; 41 orphan / 3 undeclared /
#          0 mismatched; 44 on the ledger, 0 unexcepted
```

* **Registered but unreachable in a default run: 3** — `T093/T094/T095`, removed from
  `default_tests` at `runner.py:231-232` and reachable only via `--interactive --tests`. Deliberate
  and documented (`runner.py:229-230`). Their `rig` scope makes `--scope rig` a dead selector (§3.3).
* **Registered but never *runnable* in a full suite: at least 2** — `T_WX_04`, `T_CX_04` (§5.3).
  Not a registry defect; a design defect in the tests.
* **Doc ids with no executable body: 200 of 424** (script in §7.1's shape,
  `set(doc_entries) - set(registries)`). C6 does not gate that direction *unless* the entry
  declares `impl` (C6.3), so 200 documented ids sit outside every check. Most are historical
  (`T001`–`T054`, `T117`–`T132`) and legitimately so; the ledger does not claim otherwise.
* **The ledger itself is honest**: 44 rows, 44 used, 0 stale, 0 unexcepted, and its own
  "the list can only shrink" rule (`id_binding_exceptions.md:` rules 1–4) is enforced by
  `check_docs.py:774-778`. Its self-reported findings section is accurate. The single dishonest
  cell in the corpus is `T_AE_04` (§7.1) — declared `impl`, no registry, no ledger row, no
  finding — and it is dishonest by escaping the parser, not by a ledger entry.

---

## 8. Findings

Severity: **P1** = produces or can produce a wrong verdict, or blocks a documented workflow.
**P2** = materially weakens a guarantee the architecture claims. **P3** = hygiene / debt.

| # | Sev | Finding | Evidence | Proposed fix |
|---|:-:|---|---|---|
| **B-1** | **P1** | **Seven CORE ids are single-app Stock tests whose precondition is a live HTTPS fetch.** `T-BUSY-01` FAILs (not skips) if `chartLen` does not exceed 0 in 45 s. Under the order switch it runs at index 14 and its failure records `NOT-RUN(CORE/T-BUSY-01)` against all 167 FEATURE ids. §13.2 measured this residue and prescribed declarations; none was written. | `shell.py:1665,1673,1683-1688` (`T-BUSY-01`), `:1707-1734` (`01b`), `:3149-3169` (`T-UART-01`), `:3385-3391` (`T-ERR-07`); `_order.py:49 CORE_BLOCKS`; `_gate.py:128-135`; declaration census §1.2 contains no `Stock` | Declare `scope="Stock"` on the seven, which moves them to `cls=FEATURE` by seed. Where the oracle really is shell-level (`T-BUSY-01`'s `shellBusy` auto-clear, `T-UART-01`'s JSON integrity), keep `cls="CORE"` **explicitly declared with a reason** and replace the live fetch precondition with an injected one. Do this **before** the switch flips. |
| **B-2** | **P1** | **`T133` is CORE, mixes a host-file grep with a 90 s DUT soak, and is scoped `spotify-chrome` although it drives no Spotify surface.** Under the switch it runs at index 6; a checkout without `lib/SpotifyArduino/` NOT-RUNs the entire FEATURE suite on a host-side file-existence failure. | `shell.py:730` (`src = … "lib/SpotifyArduino/src/SpotifyArduino.cpp"`), `:731-733` (`fail("T133", f"source not found")`), `:741-751` (the 90 s soak); declaration `shell.py:722`; §13.5's last row ("some changes should not produce a DUT test at all") | Split it: part A becomes a host gate under `app/tools/gate/` (it is a source grep, T1 tier); part B stays as a DUT id with an honest scope. Neither half is CORE. |
| **B-3** | **P1** | **`T_WX_04` and `T_CX_04` cannot run in a full suite and nothing says so.** Both SKIP when the app's `ready` flag is already true; their own family's A1/A2/A3 cells visit the app three times at the three indices immediately preceding them. They are counted as coverage and have never produced a result in registry order. | `shell.py:1420-1424` (`T_WX_04`, index 161; `T_WX_01/02/03` at 158-160), `:1535-1539` (`T_CX_04`, index 166; `T_CX_01/02/03` at 163-165) | Either move them to the head of their family, or give the firmware a `set weatherReady 0`/`set cryptoReady 0` reset so the precondition can be established rather than hoped for. Until then the SKIP text must name the predecessor, not the network. |
| **B-4** | **P1** | **The 0→1-edge enumeration that TASK-566 delivered as a precondition of the switch under-reports three order-dependence shapes.** `edge_candidates()` matches only counter-word-vs-0/1 and baseline-compare shapes, so a readiness-flag precondition SKIP (B-3), an unrestored in-RAM setting (B-5/B-6) and injected debug state left on the pass path (B-7) all pass through. The scanner is documented as over-reporting on purpose; on these it under-reports, which is the direction that produces a false all-clear. | `_order.py:94-111` (`_COUNTER_WORDS`, `_ABS_EDGE`); the 20 adjudicated candidates at `:193-248` contain none of `T_WX_04`, `T_CX_04`, `T-ERR-04`, `T-ERR-05`; §5.3, §5.4 | Add two scanner shapes before the switch: (a) any `skip(...)` whose guard reads a device field the test does not itself write; (b) any `set <key>` in a test or reachable helper with no matching restore on all exit paths. Both are greppable and both feed `EDGE_ADJUDICATION`, which `test_class_order.py` already forces to stay complete. |
| **B-5** | **P2** | **`_switch_to_stock` writes `set stockMode 0` on every entry and nothing ever restores it.** `_restore_from_stock` restores the app only. ~40 ids pass through it, including six CORE ids. The design's own §16.3 uses this helper as its reference case for why `effect` exists — and the leak it names is still there. | `_helpers.py:195-207` vs `:210-217`; §16.3 of the precedence design | Make `_switch_to_stock` a context manager that snapshots `stockMode` and restores it, alongside `_bgpoll_suspended` (`_helpers.py:444`) as the pattern. |
| **B-6** | **P2** | **Two hard `bgPoll` leaks.** `T_PMT_04` sets `bgPoll 0` with no restore anywhere in its body, suppressing Spotify polling for the 94 ids that follow it today. `T-BGPOLL-02` sets `bgPoll 0` and relies on the behaviour under test (`reconnect`) to restore it — so the regression it exists to catch also poisons its successors. `T-BGPOLL-01`'s opening `set bgPoll 1` "*Ensure we start in a clean state*" is a compensator for exactly this. | `player.py:1854` (no `set bgPoll 1` after it in the file); `shell.py:3207,3213`; `shell.py:3176-3177`; measurement script §5.2 | Route all 41 sites through `_bgpoll_suspended`. `T-BGPOLL-02` additionally needs a `finally` that forces `bgPoll 1` after asserting. |
| **B-7** | **P2** | **`T-ERR-04` and `T-ERR-05` leave injected Spotify state behind, and the switch moves them from indices 206/207 to 39/40.** `T-ERR-04` writes `lastOkMs 1`, `backoff 0`, `lastHttp 200` and restores none; `T-ERR-05` deliberately leaves `backoff 0`. Today almost nothing runs after them; under the switch 170 ids do. This is a new exposure created by the reorder and it is not in the adjudication. | `shell.py:3328-3331`, `:3350-3355`; index table §4.2 | Restore the three keys inside the existing `_bgpoll_suspended` block, or extend that context manager into a general `_injected(dut, **keys)` that snapshots and restores. |
| **B-8** | **P2** | **The order switch inverts the mid-suite reboots relative to the CORE block.** `T_PR_04` and `T_PRM_01` reboot the board at indices 20/23 today — before any CORE id runs. Under the switch they run at 63/66, i.e. 20 cells after the CORE block completes, wiping every piece of state it established (`bgPoll`, `cooldown`, in-RAM `stockMode`, the B-7 injections) and starting a new boot generation mid-run. TASK-566's baseline already records four boot generations per run from instability; this adds two deliberate ones after the gate. | `planeradar.py:140`, `:301`; `player.py:1610`; index table §4.2; TASK-566 baseline §3 | Either declare the three `resetting` ids as a class the gate runs last, or accept it explicitly in the switch's landing note. It is currently unstated. |
| **B-9** | **P2** | **`--scope <path>` cannot resolve 74 of 135 firmware source files (55 %), so EC-D4 — "from a changed file, the id set in one command" — fails for most of the tree.** `app/src/settings/`, `app/src/player/`, `app/src/audio/`, `app/src/mem/arena/`, `app/src/touch/`, `app/src/util/`, `app/src/display/`, `app/src/sd/`, `app/src/ui/` and 25 root files all raise `ValueError`. | `_meta.py:298-332`; measurement §3.1 | Extend `_PATH_SCOPES` with the missing directories (`app/src/settings`→`Settings`, `app/src/player`→`LocalPlayer`, `app/src/audio`→`WebRadio`, `app/src/stock`→`Stock`, `app/src/touch`/`display`/`ui`→`shell`) and add a gate case asserting every `app/src/**/*.{h,cpp}` resolves — the same shape `app_source_map()` already uses to fail loudly (`_meta.py:289-293`). |
| **B-10** | **P2** | **Two `_PATH_SCOPES` prefixes name directories that do not exist**, so the `taskbar` scope (12 ids) is unreachable from any path and `spotify-chrome` resolves only by an accidental filename-prefix match. `gate/check_test_meta.py` validates `PREFIX_SCOPES` values against the enum but never checks a `_PATH_SCOPES` prefix against the filesystem. | `_meta.py:301,304`; `ls -d app/src/taskbar app/src/spotify` → both missing; taskbar source is `app/src/shell/taskbar.cpp`, which matches the earlier `app/src/shell` row; gate at `gate/check_test_meta.py:174-176` | Point the row at `app/src/shell/taskbar` and order it before `app/src/shell`; delete or correct the `app/src/spotify` row. Add a gate case that every `_PATH_SCOPES` prefix exists. |
| **B-11** | **P2** | **The A3 canvas-residue cells can never FAIL.** `_check_residue` calls `pass_()` itself and returns `False` on failure; all six call sites convert that into `skip()`. A genuine residue regression reports as a skip in six ids. | `_helpers.py:177-192`; call sites `shell.py:1271,1326,1406,1522`, `stock.py:177,556` | Have `_check_residue` return a tristate (`pass`/`fail`/`no-signal`) and let the callers fail on the middle one. Feeds TASK-574. |
| **B-12** | **P2** | **The APP class is empty because its rows were hand-copied per app as FEATURE.** 12 ids across four families implement A1/A2/A3 identically, plus two more A3 copies in `stock.py`. §3 specifies these as "generated per app from `APP_ORDER`, never written per app". The empty-APP observation in the TASK-566 baseline records the symptom; this is the cause. | `shell.py:1216-1232`, `1277-1290`, `1354-1370`, `1470-1486`; `:1246,1303,1383,1499` (four identical `"tap 137 120"`); `:1271,1326,1406,1522`, `stock.py:177,556` | Generate the three rows from `APP_ORDER` into a single parameterised family with `cls="APP"`, deleting the twelve copies. This also gives EC-G8's APP arm a non-empty set to assert over. |
| **B-13** | **P2** | **`T_AE_04` is declared `impl` in the plan, has one body, no registry, and escapes C6 in both directions** — it is neither an orphan (not in a registry) nor a mismatch (its `impl` declaration is inside a prose cell the parser does not treat as an entry). `id_binding_exceptions.md` correctly has no row, because no finding fires. The ledger is honest; the gate has a hole. | `test_plan.md:497`; `test_ae04_teardown.py` has no `TESTS`/`ALL_TESTS`; `check_docs.py:747-756` (C6.3); measurement §7.1 | Give `test_ae04_teardown.py` an `ALL_TESTS` dict so `test_registries()` sees it — WP-A A-15's proposal, which then makes C6.3 meaningful. Separately, widen `doc_test_entries` or move the `T_AE_04` `impl` claim into a proper plan row. |
| **B-14** | **P3** | **The `effect` axis is correct, complete, gated and consumed by nothing.** 209 of 216 records say `mutating`; only 4 are `read-only` and all four are honest. Its sole specified consumer — mode D descent admissibility (§16.3) — was CUT (§20). | census §1.1; the seven non-`mutating` rows §2.1; `_meta.py:212-231`; design §20 | Keep it (it is cheap and correct) but stop describing it as a live mechanism until mode D is re-proposed. If it stays, make the ~15 tests that genuinely only issue `get` declare `read-only` so the axis carries signal. |
| **B-15** | **P3** | **`cls` is declared on 6 of 216 records and `CORE` is never declared at all.** The 43 CORE ids that will block 167 others are 43 applications of a documented *default*. The gate asserts well-formedness, never truth. | census §1.1-§1.3; `_meta.py:155-163`; `gate/check_test_meta.py:52-109` | Before the switch flips, require an explicit `@meta(cls="CORE", cls_reason=…)` on every id the switch would let block, and make `check_test_meta` fail on an *undeclared* CORE. That converts 43 inferences into 43 statements, and B-1/B-2 would have been caught by the act of writing them. |
| **B-16** | **P3** | **Duplicate-assertion clusters: 26 ids collapse to about 11 behaviours.** D1 (12 ids → 3 rows), D2 (`T_CLK_02/03/04/05/08` ⊂ `T_CLK_06`), D3 (`T_CLK_01/10/13`), D4 (`T-SET-03` ≡ `T-SET-07`), D5 (`settingsSection==-1` in four ids). Three of the clock ids additionally carry claims their bodies do not test (`T_CLK_02` forces the default it "verifies"; `T_CLK_08` claims file persistence and reads RAM; `T_CLK_13` claims a tick-rate gate its own comment says it cannot measure). | §7.2, §7.3 with per-id line cites | Collapse D2 into `T_CLK_06` and `resv` the rest; merge D4; keep one of D5. For the three false claims, either write the real oracle (a reboot for `T_CLK_08`, a tick counter for `T_CLK_13`) or rewrite the claim. Hand the verdicts to **WP-H** (clock) and **WP-D** (shell/Settings). |
| **B-17** | **P3** | **`--scope rig` never selects anything and `--scope Aquarium` selects nothing**, yet both are documented values. `rig`'s only ids are `T093/94/95`, removed from `default_tests` unconditionally; `Aquarium` is an `APP_ORDER` app with zero suite ids whose `*App.cpp` nonetheless resolves. Both exit with an error message that reads like a typo. | `runner.py:231-232`, `:306-309`; `_meta.py:289`; census §3.3 | Make `--scope rig` imply `--interactive`-eligible ids, or say plainly that rig ids are not in the default selection. For `Aquarium`, either write the three conformance rows (B-12 would generate them) or record it as knowingly uncovered. |
| **B-18** | **P3** | **Neither order is cost-aware, but the switch is a large cost *improvement* for a CORE failure and that argument is not made in the TASK-566 landing note.** Today the blocking cells are at indices 201–209, so a CORE regression is found after ~40 minutes of results the design calls uninterpretable; under the switch it is found in ~6 minutes. The counter-risk is that `T-BUSY-01`/`01b` (45–60 s, live network) then sit at indices 14–15. | index table §4.2; cost table §6; `_gate.py:128-135` | Record it in the switch's decision note. Once `cls` is trusted, derive `run/test-smoke`'s hardcoded 11-id list (`run/test-smoke:5`, WP-A A-19) from class + cost rather than by hand. |

**Counts: P1 × 4, P2 × 9, P3 × 5 — 18 findings.**

---

## 9. Could not be settled statically (NEEDS-DUT / NEEDS-DECISION)

| # | Question | Why static analysis cannot answer it |
|---|---|---|
| **N-B1** | Do `T_WX_04`/`T_CX_04` actually skip on every full-suite run (B-3)? | The reasoning is sound — the predecessors visit the app — but `weatherReady`/`cryptoReady` could conceivably be cleared by something between them. One `./run/test` log, grepped for those two ids' verdicts, settles it. TASK-566's own baseline runs would already contain the answer if their per-id rows were archived. |
| **N-B2** | Does `T-BUSY-01` fail from network flakiness often enough for B-1 to be a live P1 rather than a theoretical one? | Needs the failure history. `T-BUSY-01` and `T-BUSY-01b` are both in the TASK-566 baseline's 15-id non-stationary set, which is corroboration, not a rate. |
| **N-B3** | Do `T_PLR_13`'s and `T_PLR_25`'s two bodies agree — can one pass while the other fails? | WP-A's N-4, unchanged. Both must be run, and on different firmware variants (`cyd2usb_winamp_debug` vs `cyd2usb_player`). |
| **N-B4** | After `T_PR_04`/`T_PRM_01`/`T_PLR_26` reboot the board, is `T_PMT_04`'s 150 s heap-settle guarantee still valid? It measures from `dut._port_open_time` (`player.py:1873`), not from the last reset. | Under the switch the two PlaneRadar reboots move to indices 63/66, i.e. ~96 ids before `T_PMT_04` — probably far enough. Whether the elapsed-since-port-open proxy is ever *short* of 150 s since the last reboot needs a timestamped run. |
| **N-B5** | Does `T-BGPOLL-02`'s reliance on `reconnect` to restore `bgPoll` ever actually leave polling off (B-6)? | Only observable when `reconnect` regresses, which has not been seen. The structural point stands regardless. |

Two are decisions, not measurements, and belong to @Architect/@PM rather than VE:

* **Whether the `effect` axis stays** now that its only consumer is cut (B-14) — keep as cheap
  future-proofing, or delete the field and its gate clause.
* **Whether the switch may flip before B-1, B-2, B-4 and B-7 are closed.** My reading of @VE §18.6
  is that B-4 in particular is a precondition failure: the enumeration was required *as* a
  precondition, and it does not cover three demonstrated shapes. That is a ruling, not a
  measurement, and it is stated here so WP-Z can carry it.
