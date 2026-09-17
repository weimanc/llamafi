# M-TESTQUAL WP-Z — consolidated findings, themes, and proposed tasks

> Owner: **Verification Engineer**
> Status: **done** — 130 register rows consolidated from 147 package findings
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Consolidates: [WP-A](M-TESTQUAL-A-harness-review.md), [WP-B](M-TESTQUAL-B-taxonomy-review.md),
> [WP-C](M-TESTQUAL-C-audit-core-review.md), [WP-D](M-TESTQUAL-D-audit-shell-review.md),
> [WP-E](M-TESTQUAL-E-audit-player-review.md), [WP-F](M-TESTQUAL-F-audit-webradio-review.md),
> [WP-G](M-TESTQUAL-G-audit-stock-review.md), [WP-H](M-TESTQUAL-H-audit-data-apps-review.md)
> Method: no new audit. Every row here is carried from a package with its evidence anchor intact.
> No DUT, no serial port, nothing under `app/` or `run/` touched, `docs/project/tasks.md` not edited.

Per rubric amendment A2, no table in this document opens a cell with a bare test id, and no
section is headed with one. Finding keys (`A-3`, `G-1`) are not test ids and bind nothing.

---

## 1. Executive summary

This suite is **better than its reputation in five families and much worse than its reputation in
one**, and the single number that matters is this: **of the 216 registered test ids, 117 assert
the behaviour they claim — 54 %.** Sixty-four are weaker than they claim, twenty-one prove nothing
at all, and fourteen cannot do their job as written. Those are not impressions; every one of the
216 verdicts was reached by reading the body, resolving the firmware field or log marker it names,
and citing the line.

The 54 % is not spread evenly, and reporting it as an average would be the most misleading thing
in this document. LocalPlayer is 77 % SOUND with zero dead markers and a run of seven consecutive
ids that assert exact permutations against a device-computed order. The gating CORE class is 59 %.
The shell's FEATURE class is 56 %, WebRadio 50 %, Stock 40 %. PlaneRadar and Teletext are both
67 %. Clock is **7 % — one sound test in fourteen** — and the M-CLOCK-STYLES milestone report
books five visual exit criteria as PASS against oracles that read a settings byte, so a clock face
rendering as a solid black rectangle passes all fourteen ids and all five criteria.

The spread has one dominant cause and it is not the people who wrote the tests. All of these
families were written by the same VE, against the same harness, in the same period. What differs
is **what the firmware gave each family to look at**. Where someone designed the observable first
— ADR-059 D12's `get plOrder`/`get plCursor`/`advance`, PlaneRadar's `activeError` split, TASK-112's
`quoteOkCount` — the tests built on it are exact and the verdicts are SOUND. Where the observable
was never designed, the test reached for the nearest debug injector and asserted its own input, or
wrote "verify manually" into the pass string. Clock's 7 % and LocalPlayer's 77 % are the same
engineer with different material. That is the review's most actionable conclusion, because it says
the fix is upstream of the suite.

Three defects are producing wrong verdicts on hardware **today**, and all three have the same
shape: a `set` command arms a firmware flag that nothing clears. `set wrDeadUrls 15` forces every
later WebRadio connect to fail without touching the network and is cleared by nothing but its own
inverse — six PLEDIT ids arm it and eleven downstream ids then run against a board that cannot
connect, which is almost certainly what `flaky.yaml` has been recording as radio-browser.info
churn since 2025. `set triggerHeatmap 1` writes a `prevSubView` value the firmware has no path out
of, and the entire eight-id stock-002 block plus a CORE Stock driver behind it are predicted to be
permanent non-results in every full-suite run. `set prInjectAircraft` freezes PlaneRadar on one
synthetic aircraft for the remaining 187 ids. In all three cases isolated re-runs cold-boot and
pass, which is exactly why none has been attributed in a year of looking.

Underneath the individual defects sit two structural facts. First, **a skip gates nothing**:
`_gate.py` blocks only on a result string beginning `FAIL`, and 31 of the 43 CORE ids exit as
SKIPs when their precondition fails — so the class hierarchy's central promise, that a class-N
failure invalidates class N+1, is delivered by a string prefix test that the common failure mode
does not match. Second, **the taxonomy is 97 % inference**: `cls` is declared on 6 of 216 records
and `CORE` — the class that would block the other 167 under the held order switch — has never been
declared once. The 43 ids that would acquire that power are 43 applications of a documented
default, and seven of them are single-app Stock tests whose precondition is a live HTTPS fetch.

What should not be lost in that: the harness itself is good. `lib/results.py`'s flake policy is
correct and fails closed. `lib/dut.py`'s port resolution, DRD guard and boot-phase deadlines are
careful work, and the "19 files hardcoding `/dev/ttyUSB0`" finding is now genuinely zero code
sites. `run/player-gate` compares per-id against a pre-declared pass set and negative-tests its own
comparator — a gate with its own tests is rare anywhere. The two best-engineered tests in the whole
review, `test_ae04_teardown.py` and `test_webradio_soak.py`, are real, sustained, well-instrumented
tests. They are also both outside the registry, which is its own finding.

The honest one-sentence verdict: **this is a real test suite with real coverage that is
systematically overstated by roughly a third, whose worst failures are concentrated in the
families the firmware never gave an observable to, and whose reporting layer cannot currently tell
you which of its green cells ran.**

---

## 2. The consolidated finding register

147 findings from eight packages, deduplicated to **130 rows**. Where several packages found the
same underlying defect the row keeps the earliest key and names the others in **Also seen**;
seventeen keys were merged this way. Severity is the package's own, per rubric §4.3
(**P1** counted as coverage but provides none, or a documented entry point does not work;
**P2** materially weaker than claimed; **P3** hygiene). Sorted by severity, then by blast radius —
the number of ids, entry points or verdicts the defect can reach.

**Severities are the originating package's**, not re-graded here — a consolidation that quietly
re-scores its inputs is not a consolidation. Two rows are ones WP-Z would grade differently and
says so in place: `B-15` (undeclared `cls`, filed P3, argued as P1 in Theme 5) and `B-14` (the
`effect` axis, filed P3, and correct as filed).

### 2.1 P1 — 33 rows

| Key | Also seen | Statement | Pkg | Evidence anchor |
|---|---|---|---|---|
| `C-5` | — | The CORE block almost never fires: 31 of 43 CORE ids have a `skip()` exit and `_gate` blocks only on a result starting `FAIL`, so a failed CORE precondition is green and NOT-RUNs nothing. | C | `_gate.py:128-129`; `_helpers.py:435,438`; `lib/results.py:152-154` |
| `G-1` | — | New leak cluster `C10`: `set triggerHeatmap 1` stamps `prevSubView = ChartDetail`, a fixed point no back tap, `resume()` or app switch clears — `T200`/`T201`/`T202`/`T203`/`T192`/`T193`/`T194` predicted permanent SKIP in every full run, with `T-BUSY-01` passing vacuously behind them. | G | `stockApp.cpp:246-253`, `:312-321`; `stockHeatmap.cpp:26`; `stock.py:967-998`; `shell.py:1669` |
| `F-4` | — | New leak cluster `C9`: `set wrDeadUrls N` arms `_debugForceConnFail`, cleared by nothing but `set wrDeadUrls 0`/`set wrUrl` — six PLEDIT ids arm it, eleven fetch-dependent ids downstream run with connect forced to fail, and `wrState=5` is the exact symptom two `flaky.yaml` entries blame on the network. | F | `webradio.py:44` vs `:950`, `:1049`; `webRadioApp.cpp:1031-1055`, `:1325-1334`; `flaky.yaml:72-108`; `_order.py:241-247` |
| `B-1` | — | Seven CORE ids are single-app Stock tests whose precondition is a live HTTPS fetch; `T-BUSY-01` FAILs (not skips) if `chartLen` does not exceed 0 in 45 s, and under the switch that failure NOT-RUNs all 167 FEATURE ids from index 14. | B | `shell.py:1665,1683-1688`, `:1707-1734`, `:3149-3169`, `:3385-3391`; `_order.py:49`; `_gate.py:128-135` |
| `B-4` | — | The 0→1-edge enumeration delivered as the order switch's precondition under-reports three demonstrated order-dependence shapes (readiness-flag SKIP, unrestored in-RAM setting, injected state left on the pass path) — under-reporting in the direction that grants a false all-clear. | B | `_order.py:94-111`, `:193-248`; §5.3, §5.4 |
| `H-2` | — | Five M-CLOCK-STYLES exit criteria are recorded **PASS** against oracles that cannot observe them (C4→"responsiveness proxy", C5/C6→"DUT accepts, no crash", C7→"no heap anomaly", C8→"app stable"); C3 claims a power cycle no clock id performs. A black rectangle passes all fourteen ids. | H | `regression_suite/m-clock-styles.md:46-55`; `clock.py:73-79,89-95,179-189,199-204,213-222`; `clockApp.cpp:89-454` |
| `D-2` | `B-11`, `G-5` | The six `_check_residue` call sites convert the helper's `False` — the residue regression itself — into `skip()`, so six ids can PASS or SKIP and never FAIL; `T182` additionally skips on both taskbar failures its cross-feature claim is about, leaving no reachable `fail()`. | D, B, G | `_helpers.py:177-192`; `shell.py:1271,1326,1406,1522`; `stock.py:174-178`, `:518-558` |
| `H-1` | — | New leak cluster `C11`: `set prInjectAircraft` sets `_injected`, which guards every real-fetch site and is cleared only by `set prClearInject 1` or `init()` — not by `resume()`; `T_PRI_01` never clears it, leaving the radar frozen on one synthetic aircraft for the remaining 187 ids. | H | `planeRadarApp.cpp:279`, `:27,33,37,135,164`; `planeradar.py:453`, `:480-481`; `appShell.cpp:200-207` |
| `D-1` | — | The four "BUG-1 guard" ids assert `hit == "CLOCK"`, a fixed `Serial.printf` on `cmdTap`'s terminal `else` that calls no app handler — the claimed regression is unrepresentable on that path and the assertion is a tautology on the test's own precondition. | D | `shell.py:1246-1253,1303-1309,1383-1389,1499-1505`; `cmdTouch.cpp:56-58,141-144` |
| `G-2` | — | `_stock_ok_count`/`_stock_quote_ok_count` return `-1` on a bad read and `_wait_chart_complete(-1)` then returns `True` on its first poll — one raced serial reply turns the family's central fetch oracle into an unconditional pass across nine ids. | G | `_helpers.py:225-233`, `:254-259`; `stock.py:58-66`; `lib/dut.py:1079-1091` |
| `H-3` | — | Five Clock ids assert only values the harness wrote or the firmware hardcodes — 5 of 14 HOLLOW, 36 %, the highest rate in the review; `T_CLK_08` claims `settings.json` persistence and reads a RAM member back through the command that wrote it. | H | `clock.py:44-47,138-141,151-156,213-222,232-239`; `cmdSet.cpp:634-638` vs `:669-674` |
| `A-8` | `H-4` | `clock.py` hardcodes app slots and never imports `app_ids_gen`; `_switch_to_clock` returns `True` on an ack that echoes the host's own argument, and every clock oracle is a global readable from any app — so a `switchApp` that stopped switching would fail no clock id. Slots are correct today: latent, not live. | A, H | `clock.py:10-15,20,152-153`; `cmdMisc.cpp:20-28`; `app_ids_gen.py:4`; `console.cpp:91` |
| `C-3` | — | The RIG class has no executable coverage in any shipped entry point — no `run/` script passes `--interactive` — so `T095`, the injection-vs-physical calibration licensing every `tap` in the other 210 ids, has never been runnable from a script; `_gate`'s RIG rule is an unrelated mechanism sharing the name. | C | `runner.py:231-232`, `:194`, `:340-344`; `grep -rn interactive run/` → empty; `_gate.py:6` |
| `C-4` | — | A SKIPped HEALTH check is announced as `[health] PASS` with a sentence asserting the thing that did not run; `_triage.health_verdict` says `degraded` for the same run, so banner and premise contradict each other in one output. | C | `health.py:349`, `:178-182`; `_gate.py:66-78`; `runner.py:401-403`; `_triage.py:78-83` |
| `A-2` | — | The `SetupFailure`→exit-3 contract that separates "the rig broke" from "the firmware broke" is honoured by 4 files; eight tools construct the shared `Dut` and let it escape as an uncaught traceback → exit 1. | A | `grep -rln 'except SetupFailure'` → 4; `test_planeradar_soak.py:56`, `test_fetch_stress.py:214`, `run_sync_tests.py:1304`, +5 |
| `A-4` | — | Four independent `SerialDut` classes bypass `lib/dut.py` entirely — no DRD reset-gap stamp, no debug-firmware verify, no cooldown drain, no `SetupFailure`; three sit behind documented `run/` entry points. | A | `test_adr045_gate.py:55`; `test_webradio_soak.py:55`; `webradio_long_soak.py:142`; `test_ae04_teardown.py:105`; `lib/dut.py:115,123,1156` |
| `A-3` | — | `gen/gen_get_keys.py` globs headers only, so 10 `dbgGet()` bodies that moved to `.cpp` are invisible: it enumerates 43 of 71+ `get` keys and `run/task488`'s "every key resolves" covers ~60 %. | A | `gen/gen_get_keys.py:44`; `app/src/apps/webRadioApp.cpp:716`; §6.2 commands |
| `A-5` | — | `run/test-targeted` — the entry point CLAUDE.md directs you to — skips the TLS-pin preflight `run/test` runs as step 0 precisely so a CA rotation does not present as cryptic fetch FAILs; `run/player-gate`, a release gate, skips it too. | A | `run/test:99`; `grep -c check-datatask-certs run/test-targeted run/player-gate` → 0, 0 |
| `C-6` | — | `T091`'s gating power is switched off by its own flake declaration: every exit is `flake()`, and a declared flake that passes on retry becomes `FLAKY-PASS`, which is neither PASS nor `FAIL` and can never set `blocked_by`. | C | `shell.py:514,517,520,526`; `flaky.yaml:51-70`; `lib/results.py:227`; `_gate.py:128-129` |
| `C-1` | — | `T-BUSY-05`'s guard is inverted (`any(b is not True …)`), so it passes exactly when the amber fails to clear — it has been green on an untested and possibly broken path for its whole life. | C | `shell.py:1836-1841`; claim at `:1805` |
| `C-2` | — | `T-UART-01` structurally cannot observe its own subject: JSON garbling is detectable only via `JSONDecodeError`, which the shared reader swallows before returning the next well-formed line; the `ValueError` in its `except` is unreachable. | C | `lib/dut.py:1086-1090`, `:1122-1136`; `shell.py:3156-3167` |
| `B-2` | `C-14` | `T133` is CORE, scoped `spotify-chrome`, and is a host-side source grep plus a 90 s vacuous soak — a checkout missing `lib/SpotifyArduino/` would NOT-RUN the entire FEATURE suite from index 6 on a host file-existence failure. | B, C | `shell.py:722,730-736,741-752`; §13.5 |
| `B-3` | `D-3` | `T_WX_04` and `T_CX_04` can never run in a full suite: their "app never visited" precondition is destroyed by their own three immediate predecessors, so both take the "already true" `skip()` every time, and neither is in `EDGE_ADJUDICATION`. | B, D | `shell.py:1420-1424`, `:1535-1539`; indices 158-161, 163-166 |
| `E-2` | — | `T_PLR_25` has no variant guard and is a deterministic 60 s false red on the only env that dispatches it; `run/player-gate` stays green only by omitting the id from leg A's list. | E | `player.py:1526-1585`; `:493-505,788-790,1780-1783`; `run/player-gate:84-87`; `player-gate-baseline.md:94-96` |
| `F-1` | — | The shared `T_WR_ERR_*` teardown writes `set wrState 3` believing it is STOPPED — 3 is `ERROR_WIFI` — so `T_WR_ERR_03`'s restore re-writes the value it injected (BROKEN) and all four ids exit parked in an error state ahead of six ids whose oracle is `wrState == 2`. | F | `webradio.py:511-513`; `webRadioApp.h:36-44`; `webRadioApp.cpp:954-960` |
| `F-3` | — | All four `T_WR_ERR_*` round-trip an injected byte through one `_state` member and name the real subject — a banner, an empty POSBAR — in the pass string; `dbgSet` returns `true` for any input, so the `ok` check proves nothing either. | F | `webradio.py:502-510,522,531,540,554`; `webRadioApp.cpp:716-720`, `:954-960` |
| `F-7` | — | `T_WR_VOL_03` claims a volume behaviour and reads no volume — its only oracle is `wrState == 2` — and its `set wrVol 21` after `set wrStop 1` hits the no-live-session branch, so it may never have injected the value it exists to see overridden. | F | `webradio.py:789-806`; `webRadioApp.cpp:775-790`, `:1104-1116` |
| `G-7` | — | `T178` and `T185` assert values their own `set triggerFetch 1` wrote: the injector assigns `chartLen = 0` and `fetchFailed = false`, which is `T178`'s entire oracle and is what clears the error `T185` injected one line earlier. | G | `stockApp.cpp:222-233,325-327,338`; `stock.py:387-406`, `:734-747` |
| `G-6` | — | `T194`'s one `fail()` compares `stockChartTicker` against a read of the same field two commands earlier with no firmware write between; its real oracle exits via `skip()` where the identical construction in `T192`/`T193` is a `fail()`. | G | `stock.py:1434`, `:1448-1461`; `stockChart.cpp:75`; `stockApp.cpp:116-127,314` |
| `E-8` | — | Two player ids assert behaviour that cannot regress: `T_PLR_02` reads back its own write for a reboot claim its docstring hands to a human, and `T_PLR_03`'s "no leaked taskbar slot" is arithmetically unrepresentable — `appIdx = offset % TASKBAR_APP_COUNT` cannot yield WebRadio or LocalPlayer. | E | `player.py:70-80,61-65,103-111`; `cmdTouch.cpp:29-31`; `appShell.cpp:76-77` |
| `D-4` | — | `T136` is a registered id whose entire body is one `skip()`, dispatched every run, while its only plan declaration — in the archive, which `check_docs` scans — still records `Status: pass`. | D | `shell.py:843-846`, `:3421`; `test_plan-archive.md:1453-1465`; `test_plan.md:2117-2118` |
| `D-5` | — | `T078` defers its whole claim to a human (`NOTE: verify … manually`) and asserts a resting state that holds either way; the marker it needs is emitted, greppable, and already collected by two other ids in the same module. | D | `shell.py:103-107`; `winampDisplay.cpp:367-369,496,510`; cf. `shell.py:204`, `:2196` |
| `A-1` | — | `run/screendump` is hard-broken at import since TASK-555 removed `_PORTAL_INDICATORS`, and three further tools die the same way — while it is documented in `CLAUDE.md` and is the instrument two other findings propose using. | A | `screendump.py:30`; `lib/dut.py:310`; `clock_delta_smoke.py:26`, `pr_delta_smoke.py:54`, `slider_delta_smoke.py:33` |

### 2.2 P2 — 58 rows

| Key | Also seen | Statement | Pkg | Evidence anchor |
|---|---|---|---|---|
| `C-7` | `E-3`, `F-8` | All eight flake declarations and call sites examined across three families are mismatched **in both directions**: `T_PLR_17`/`T_PMT_04`/`T_WR_COEX_01`/`T_WR_VOL_03` are declared and never call `flake()`, while `T_PLR_07`/`T_WR_EJECT_01`/`T084`/`T092`/`T-CDWN-02` call it undeclared and surface every failure as a bookkeeping message. | C, E, F | `flaky.yaml:51-161`; `shell.py:250,559,1998`; `player.py:335`; `webradio.py:429`; `lib/results.py:186-199` |
| `E-5` | `F-11`, `G-13` | Six ids drive a different app than their record says and carry a module-seeded scope, so `--scope` misses them: `T_PLR_17`/`T_PLR_18` (Spotify/WebRadio), `T_WR_VIS_03`/`T_WR_VIS_05` (Spotify), `T182` (taskbar, the family's only taskbar test). The `@meta(scope=…, scope_reason="cross-mode")` mechanism is used correctly 30 lines away. | E, F, G | `player.py:1750,1757`; `webradio.py:1431-1466`, `:1516-1547`; `stock.py:500-558`; `test_plan.md:1934-1943` |
| `C-12` | `D-15`, `E-4` | Seven restores default to a value that silently **rewrites** persisted state instead of restoring it — `r.get('val', 0)` for `playerMode` ×4, `r_save.get('ms', 180000)` for `songDuration`, two more in `T085`/`T153` where two lost replies compare equal and pass. | C, D, E | `shell.py:2802,2814,281,288-289,2269,2292`; `player.py:76,130,159` |
| `B-5` | `G-4` | `_switch_to_stock` writes `set stockMode 0` on every one of ~40 entries and nothing restores it; the field is settable but **not gettable**, so the restore cannot be written today, and `SettingsStorage::save()` serialises the same struct — any later save in the boot makes the suite's `List` the user's persisted preference. | B, G | `_helpers.py:195-217`; `stockApp.cpp:212-216`; `settingsStorage.cpp:499`; `stock.py:626-634` |
| `E-11` | `F-6` | `_switch_to(dut,"WebRadio")` taps slot 11 → `appIdx = 11 % 11 = 0`, the *player* slot; it reaches WebRadio only when a predecessor left the board on Spotify. `webradio.py`'s own header warns against this helper. Affects `T_PLR_18` and `T_WR_ERR_04`; invisible to `edge_candidates()`. | E, F | `player.py:1084-1086`; `webradio.py:30-33`, `:298-306,548`; `_helpers.py:321-331,400`; `coords.py:184-188` |
| `E-7` | — | New leak cluster `C8` — the arena: `T_PLR_25` plays five tracks and never releases on exit, and `mb_arena_acquire()` early-returns before incrementing, so a later acquire is invisible by design. This is how `T_PMT_04` became TASK-553's false regression; the leaker is named nowhere. | E | `player.py:1576-1577` vs `:1938-1959`; `mem/arena/mb_arena.cpp:106,134-147`; `test_plan.md:474` |
| `B-6` | — | Two hard `bgPoll` leaks: `T_PMT_04` sets `bgPoll 0` with no restore anywhere in its body (94 ids follow it), and `T-BGPOLL-02` relies on the behaviour under test (`reconnect`) to restore it, so the regression it guards also poisons its successors. | B | `player.py:1854`; `shell.py:3207,3213`; `shell.py:3176-3177` (the compensator) |
| `B-7` | — | `T-ERR-04`/`T-ERR-05` leave injected Spotify state (`lastOkMs`, `backoff`, `lastHttp`) behind; today almost nothing runs after them, under the switch they move to indices 39/40 and inject it into 170 ids. A new exposure created by the reorder and not in the adjudication. | B | `shell.py:3328-3331`, `:3350-3355`; index table §4.2 |
| `B-8` | — | The switch inverts the three mid-suite reboots relative to the CORE block: `T_PR_04`/`T_PRM_01` move from indices 20/23 to 63/66, wiping everything the CORE block established twenty cells into FEATURE and starting a new boot generation mid-run. | B | `planeradar.py:140,301`; `player.py:1610`; §4.2 |
| `B-9` | — | `--scope <path>` cannot resolve 74 of 135 firmware source files (55 %), so EC-D4's "from a changed file, the id set in one command" fails for most of the tree — including all of `app/src/settings/`, `player/`, `audio/`, `touch/`, `util/` and 25 root files. | B | `_meta.py:298-332`; measurement §3.1 |
| `B-10` | — | Two `_PATH_SCOPES` prefixes name directories that do not exist, so the `taskbar` scope (12 ids) is unreachable from any path and `spotify-chrome` resolves only by an accidental filename-prefix match; the gate never checks a prefix against the filesystem. | B | `_meta.py:301,304`; `ls -d app/src/taskbar app/src/spotify` → missing; `gate/check_test_meta.py:174-176` |
| `B-12` | — | The APP class is empty because its three conformance rows were hand-copied per app as FEATURE — 12 ids across four families plus two more copies in `stock.py`, where §3 specifies them as generated from `APP_ORDER` and never written per app. | B | `shell.py:1216-1232,1277-1290,1354-1370,1470-1486`; `stock.py:177,556` |
| `B-13` | — | `T_AE_04` is declared `impl` in the plan, has one body, no registry entry, and escapes C6 in both directions — neither orphan nor mismatch, because the parser does not read an id out of a prose cell. The ledger is honest; the gate has a hole. | B | `test_plan.md:497`; `test_ae04_teardown.py` has no `TESTS`; `check_docs.py:747-756` |
| `E-13` | — | `run/player-gate`'s HEALTH machinery cannot fire: it invokes `runner.py` without `--class-order`, so no HEALTH phase runs and exit 4 is unreachable — the gate emits PASS/REGRESS without ever establishing that the board was a fit subject. | E | `run/player-gate:110-124,485-486,495-502`; `runner.py:376-381`; `lib/results.py:251-260` |
| `E-1` | — | `_pl_load` discards `set plLoad`'s reply and returns only `get plCount`, so the family's fixture oracle cannot tell a missing fixture from a broken load or an unresumed mode — eight ids `skip()` on it, two `fail()`, and one's skip branch is unreachable. | E | `player.py:423-426`; skips `:435-437` … `:1486-1488`; `cmdSet.cpp:197-199`; `cmdGet.cpp:629-633` |
| `E-6` | — | Four negative assertions in `T_PLR_18`/`T_PLR_19` treat a `_wait_for_log` timeout as the pass on a suppressible `LOG_D` channel, so "no leak" and "no logging" are the same result, at 32 s a run. | E | `player.py:1104,1114,1167,1181`, `:974-986`; `logSink.h:116-123` |
| `E-9` | — | `T_PMT_00`, "THE binding test", asserts two string literals from a fixed `Serial.printf` and a change of unspecified direction (`after != before`), so a cycle landing on the wrong mode passes; the successor table is available in the same file. | E | `player.py:1723-1747`, `:1643-1647`; `cmdGet.cpp:612-618`; `appShell.cpp:83-85` |
| `E-10` | — | `T_PLR_07` uses the split-read pattern `_tap_and_wait_log` exists to remove, 90 lines below a body using the helper for the identical marker, and routes the resulting race through an undeclared `flake()`. | E | `player.py:323-335` vs `:220`; `_helpers.py:20-65`; `lib/dut.py:1079-1091` |
| `D-6` | — | The Settings tap geometry hand-mirrors four firmware constants **and re-implements `_appListRowH()`'s formula in Python**, using a count that lives in `app/gen/` — the generated header LL-114 says to parse. Drift lands every Settings tap on the neighbouring row. | D | `shell.py:2923-2932`; `settingsSection.h:39-43`; `appsSection.h:256-259`; `app/gen/configurable_apps.h:4` |
| `D-7` | — | Three ids grep for log markers the firmware has never emitted (`ACT_SEEK`, `seek commit`): `T149` collects and discards the result, `T153` gates a `fail()` on a list that can never fill, and `T149`'s plan step 5 is unimplementable as written. | D | `shell.py:2127-2128,2279-2281,2297-2298`; `spotifyTask.h:28`; `winampDisplay.cpp:683`; `test_plan.md:1413` |
| `D-8` | — | `posbarDragMs` is the live drag-tracking value, not the committed seek, so "commits a seek" has no oracle anywhere in the suite; two ids claim it and both read the Press/Move value. | D | `winampDisplay.cpp:362,389,434,737-740`; `shell.py:2134-2143,2324-2330` |
| `D-9` | — | New leak cluster `C7` — `songDuration`: four ids inject 120000/60000 and none restores; the firmware comment justifying the accessor assumes a successful poll overwrites it, which TASK-243's permanent 403 prevents, so the injection lasts the run and makes POSBAR hittable for every later hit-test id. | D | `shell.py:2116,2149,2261,2306`; `:280-281,291`; `winampDisplay.cpp:785-791` |
| `D-10` | — | `T139` has no queue precondition, so with a short queue the view cannot scroll whatever the clamp does — the one PLEDIT id that passes green under TASK-243 while exercising nothing; its two siblings both gate on `wait_for_queue`. | D | `shell.py:913-931` vs `:854,942`; `:955-968` |
| `D-11` | — | `T082`'s "debounce verified by count" is `len(lines) >= 2` over a 60-step drag: a firmware that lost its debounce entirely emits 61 and passes. Only under-firing fails. | D | `shell.py:192`, `:217-220` |
| `D-12` | — | `T087` uses the split-read pattern between the LOGO tap and the reset-line hunt — the documented race — bundles six unrelated assertions under one id, and hides the consequence behind a flake declaration that names a different cause. | D | `shell.py:389,396,404-416`; `_helpers.py:23-42`; `flaky.yaml:27-43` |
| `D-13` | `F-17` | Two id pairs are the same test with a weaker bound: `T158` is `T157` with `>= 1` for `1 <= so <= 3` and drops the gesture-state check; `T_PLE_WR_158` is `T_PLE_WR_157` the same way — each costing a full second precondition run. | D, F | `shell.py:2400-2428` vs `:2435-2453`; `webradio.py:161-182` vs `:130-151` |
| `F-2` | `G-11` | Three registry ids collide with unrelated `test_plan.md` headings — `T237` (Crypto currency change), `T276` (skin preview base layer), `T231` (Aquarium speed) — so the plan's bound C6 entries point at bodies that do not implement them and any coverage claim citing them is ambiguous. | F, G | `test_plan.md:4188,4537,4109`; `webradio.py:875,959`; `stock.py:637-722` |
| `F-5` | — | Fourteen WebRadio ids select station index 0 and none records what station that was; `get wrStation` is called by no suite file, and nothing reads the `bitrateCap`/country settings that decide the list's content — so two runs are not comparable across a settings change, silently. | F | `webRadioApp.cpp:729-744`; `dataTaskStorage.cpp:1043-1058`; `webradio.py:1174` |
| `F-10` | — | `T_WR_COEX_02` asserts a disjunction where its claim is a conjunction (one working direction passes, and NEXT/PREV wired to one handler passes outright); `T_WR_COEX_04`'s "touch latency" is the host→device serial round trip against a bound an order of magnitude too loose. | F | `webradio.py:605-608`, `:619-636` |
| `F-14` | — | `T_WR_VIS_01`'s "isolated measurement" isolates the read, not the measurement: `s_wrPumpMaxPumpMs` is a high-water mark for the life of the pump task, which survives every earlier test, so the 50 ms ceiling is applied to the worst cycle since boot. | F | `webradio.py:1352-1383`; `audio/audioEngine.cpp:381,398-409` |
| `F-15` | — | Two negative VIS assertions cannot fail: `T_WR_VIS_02`'s Atlas control is a `print(...)` warning, and `T_WR_VIS_05` compares `m != 4` where a failed read returns `None`, so a board that stopped answering `get visMode` passes six times. | F | `webradio.py:1408-1410`, `:1533-1547`; `_helpers.py:110-119` |
| `F-19` | — | `run/wr-gate` cannot say what firmware it measured (no ELF hash, no build check, unlike `run/player-gate`) and its denominator moves during the run because the extension rule adds trials; a mid-run reboot is detected, never counted and never affects the verdict. | F | `test_adr045_gate.py:52,264-266,409-427`; `run/player-gate:454-486` |
| `F-20` | — | The ADR-045 criterion's skip term was structurally unexercisable by the gate that closed the milestone: every trial hardcodes station 0, so all ten scored trials reported `skips=0` and the "≤ 6 auto-skips" half had zero variance. | F | `test_adr045_gate.py:283-321`; `tasks-archive.md:3987-3998`; §8 |
| `G-3` | — | `get fetchErrorCode` does not exist, so five stock fetch-failure diagnostics — including the two TASK-385/386 added so a failure would carry its own evidence — have always printed `None`; `set fetchErrorCode` exists and injects a value nothing can read back, and `fetchErrCount` is read by no suite file. | G | `stockApp.cpp:134-201`; `stock.py:143,798,856,864,931` |
| `G-8` | — | Three ids drive the chart range tabs and none reads the range back: `T188` taps all four and reports "all 4 ranges fetched" without checking, `T204`'s Ytd↔D1 alternation is the subject of its own claim, and `T180`'s "resets to D1" is vacuous if the 5D tap missed. | G | `stock.py:848-874,909-944,444`; `stockApp.cpp:116-118`; `test_plan.md:2081` |
| `G-9` | — | Four ids assert ticker strings that are a persisted, user-editable setting rather than a firmware constant — and they are precisely the four the family relies on to detect a row-geometry drift, so the mirror that protects the family is also its most fragile assertion. | G | `stock.py:230,484,809,815`; `settingsStorage.cpp:91,258,498` |
| `H-5` | — | `set prForceParseFail` (TASK-361) is a deterministic PlaneRadar fetch-failure injector with **no consumer anywhere** in `app/tools/` or `run/`, while `T_PR_05` — the id it exists for — has been a permanent SKIP since 2026-07-11 and both its docstring and plan row still say no such hook exists. | H | `planeradar.py:159-160,188-209`; `planeRadarApp.cpp:242-245`; `test_plan.md:4724-4728`; `flaky.yaml:157` |
| `H-6` | — | `T_PR_02`'s oracle is a boot-scoped latch (`!_everHadResult`) that its own predecessor consumes, so what it proves is "a fetch has resolved since boot", not "within one poll of app entry"; the render half of its exit criterion has no oracle at all. | H | `planeRadarApp.h:244,278`; `planeRadarApp.cpp:6,60,153,306`; `planeradar.py:69-89` |
| `H-7` | — | `T_PR_06` asserts one of the three things it claims: the clear-half read is taken and appears only in the pass string, and `prLastHttp` is never read; the one assertion is a round trip through a counter the same command wrote. | H | `planeradar.py:234-238,247-257`; `planeRadarApp.cpp:168-170,274-307` |
| `H-8` | — | The tap reply's `"skipped"` flag is discarded at every tap site in the data-app corpus, and `T271` taps two consecutive boundaries expecting the same action — so a tap swallowed by the busy gate or the 300 ms debounce passes on its predecessor's residue. | H | `cmdTouch.cpp:47-51,70-77`; `teletext.py:185-207,132-139` |
| `H-9` | — | `set cooldown 0` is the wrong variable in all three Teletext call sites: it zeroes the Spotify dead-zone force-poll timer, not the app's own 300 ms `_lastTapMs` debounce; the three calls are inert and a `time.sleep(0.35)` is what actually clears the gate. | H | `teletext.py:111,128-129,187,199`; `winampDisplay.cpp:776-782`; `teletextApp.cpp:102,139-144` |
| `H-10` | — | The data-app corpus writes `settings.json` roughly fifty times per suite run — real flash writes, not RAM — and restores the user's clock face and radar range only by luck, because a later test happens to write a different value. | H | `cmdSet.cpp:669-671`; `planeRadarApp.cpp:347-350`; `clock.py:105-113,181-184,199-201`; `planeradar.py:480` |
| `H-12` | — | `app/gen/teletext_layout.h` is a **generated** header the suite mirrors by hand in six places, and `coords` — the parser that already reads two other generated headers — is imported and unused in both `teletext.py` and `planeradar.py`. | H | `app/gen/teletext_layout.h:25-40`; `teletext.py:8,132,177-182`; `planeradar.py:8,28,119,269` |
| `A-9` | — | Stock tab and row coordinates are 16 literal taps in `stock.py` (31 suite-wide) plus a four-pair `_TAB_XY` table replacing a two-`#define` formula, while `coords.py`'s parser sits imported-and-used-once in the same file. | A, G | `stock.py:756-760`; `stockShared.h:38,46,47`; WP-G §8 corrects the count |
| `A-10` | — | `PR_FETCH_TYPE = 8` and `_PLAYER_MODES` mirror firmware enums with "keep in sync" comments, and the second's provenance cite is wrong — `kPmNames` is in `cmdSet.cpp`, not `cmdGet.cpp`, so a reader following it finds nothing. | A | `planeradar.py:267-269` vs `dataTask.h:20`; `health.py:66-68` vs `cmdSet.cpp:699` |
| `A-6` | — | `run_sync_tests.py` (20 ids, `run/test-sync`) carries a private pre-TASK-520 copy of `RESULTS`/`pass_`/`fail`/`skip` and its own summary: no flaky policy, no `FLAKY-PASS`, no `NOT-RUN`, no exit 4, and ids printed sorted rather than in registry order. | A | `run_sync_tests.py:370-382,1344-1349`; `grep -c flake` → 0 |
| `A-7` | — | The results summary's per-id line is a machine interface with no specification: `run/player-gate` parses it with a `sed` regex, a missing token there already produced a false REGRESS verdict (TASK-573), and a second producer emits the shape by coincidence. | A | `lib/results.py:270`; `run/player-gate:150-158,162`; `run_sync_tests.py:1348` |
| `A-11` | — | `lib/dut.TIMEOUT`/`TIMEOUT_SLOW` — the declared single timeout policy — has zero users against 823 numeric `timeout=` literals, 459 of them exactly the default. The policy exists on paper only. | A | `lib/dut.py:47-48`; `grep -c 'TIMEOUT_SLOW\|dut\.TIMEOUT'` → 0 in all 15 |
| `A-12` | — | Six DUT scripts execute their whole suite at **import** time — module-level `serial.Serial()` outside any `__main__` guard — so importing one resets the board; this cost a reset and a contaminated observation window during WP-A, and it blocks any import-level lint over `app/tools/`. | A | `prloc_smoke.py:16,25`; `prloc_ve_smoke.py:45,71`; `settings_kit_smoke.py:35,56`; +3 |
| `A-13` | — | Sixteen implementations of "enter an app and confirm arrival" and 57 hand-written bounded poll loops (11 named); `_helpers.py` is 454 lines against 9 983 lines of family modules — the TASK-480 split distributed the bodies and never consolidated the helpers. | A | §4.1/§4.2 tables; `grep -c 'while time.monotonic()'` → 57 |
| `A-14` | — | Seven different defaults for `r.get("val", …)` across the suite, six of them values a comparison can pass on; there is no shared accessor that would close the S6 defaulting-oracle class at one choke point. | A | §4.5 histogram; `suite/serialdbg/*.py` |
| `C-8` | — | `T_DH_01` does not check the shell answers *correct* data — every field it validates is a compile-time or trivially non-zero value; what it really detects is a truncated or desynchronised reply, which is worth gating on but is a different claim. | C | `health.py:93-119`; `cmdMisc.cpp:34-50`; `cmdGet.cpp:41-47` |
| `C-9` | — | `T_DH_02` never compares the SSID against anything: any non-empty SSID plus any non-zero IP passes, so a board on a neighbour's AP, a guest VLAN or a router with no upstream route is certified as knowing which network it is on. | C | `health.py:201-213`; banner `_gate.py:75-76`, `runner.py:401-402` |
| `C-10` | — | No HEALTH check performs off-board I/O, reads the filesystem, exercises the tap path or samples supply — so a wiped SPIFFS, a broken `cmdTap` dispatch, a silently non-dispatching dataTask and TASK-557's supply sag all pass, and the ~150 tap-driven ids then report rig failures as firmware defects. | C | §2.1 table; `health.py:16-22` |
| `C-11` | — | Two CORE ids never establish the precondition their claim rests on: `T-CDWN-03` asserts a tap bypasses the busy gate without checking `shellBusy` was ever true, and `T-BGPOLL-03` asserts only that a flag it wrote itself is unchanged. | C | `shell.py:2021-2036`, `:3243-3251` |
| `C-13` | — | `_TB_N` equals `TASKBAR_APP_COUNT` by coincidence — the suite computes `APP_SLOT["WebRadio"]`, the firmware `(int)AppId::Settings + 1` — so any non-taskbar app inserted between them silently mis-scores three ids and the shortest-path arithmetic. | C | `_helpers.py:396-400` vs `app/src/shell/taskbar.h:45` |
| `C-15` | — | `T242` samples 2 of 11 taskbar offsets and asserts only "not WebRadio", so a slot resolving to the wrong non-WebRadio app passes; its restore is on the pass path only, so every failure leaves an arbitrary app and a non-zero scroll offset. | C | `shell.py:2692-2701` |
| `B-16` | `H-11` | Duplicate-assertion clusters: 26 ids collapse to about 11 behaviours — the 12 hand-copied conformance rows, `T_CLK_03/04/05/08` inside `T_CLK_06`, `T_CLK_01/10/13`, `T-SET-03` ≡ `T-SET-07`, and `settingsSection == -1` asserted in four ids. | B, H | §7.2/§7.3 with per-id cites; `clock.py:51-115`; `shell.py:3005-3104` |

### 2.3 P3 — 39 rows

| Key | Also seen | Statement | Pkg | Evidence anchor |
|---|---|---|---|---|
| `B-15` | — | `cls` is declared on 6 of 216 records and `CORE` is never declared at all; the gate asserts records are well-formed, never that they are true. **Filed P3; WP-Z argues P1** — see Theme 5, because it is the precondition the held order switch rests on. | B | `_meta.py:155-163`; `gate/check_test_meta.py:52-109`; census §1.1-§1.3 |
| `A-18` | — | Nothing gates mirroring: `run/check` gates generated-output staleness, `check_docs` C6 gates id binding, and no gate asks whether a suite literal still equals the firmware constant it copied — which is why the D1–D7 register grew *after* LL-114 was closed. | A | §6.3; the nine-mirror register §6.1 |
| `C-18` | — | `get cooldown` and `get shellCooldown` answer with the same field name and `Dut.cmd` correlates nothing, so a one-reply desync is undetectable — and `Dut.cmd` itself issues `get shellCooldown` before every tap and drag. | C | `lib/dut.py:1132-1136`; `shell.py:2841,2851,2876,2882` |
| `A-15` | — | Two registry ids have two executable bodies with different oracles and different reporting; WP-B confirmed the list is complete and WP-E adjudicated both — the standalone body wins in each case, and `T_PLR_25`'s registry copy is the broken one. | A, B, E | `player.py:783` vs `test_fbrowser_player.py`; `player.py:1526` vs `test_playorder_player.py` |
| `A-17` | — | Generated infrastructure nobody consumes: `app/gen/mem_layout.py` is generated expressly "for the test suite" and has zero importers repo-wide, `shell_layout.py` has zero suite importers, and `coords` is imported-and-unused in two modules. | A | `grep -rn mem_layout --include=*.py`; `grep -c '_c\.' planeradar.py teletext.py` → 0, 0 |
| `A-16` | — | Two byte-identical `main()` runners in `gate/`, and three different functions named `check` with three different signatures across the gate tests. | A | `gate/test_check_app_conformance.py:273-289` ≡ `gate/test_check_test_meta.py:234-250` |
| `A-19` | — | Four `run/` scripts do not source `run/lib.sh`, and `run/test-smoke` hardcodes an 11-id list not derivable from the registry's `cls`. | A | `grep -c 'source .*lib\.sh' run/*`; `run/test-smoke:5` |
| `B-14` | — | The `effect` axis is correct, complete, gated and consumed by nothing: 209 of 216 records say `mutating`, all four `read-only` records are honest, and its sole specified consumer (mode D descent admissibility) was CUT. | B | census §1.1; §2.1's seven rows; `_meta.py:212-231`; design §20 |
| `B-17` | — | `--scope rig` never selects anything (its three ids are stripped from `default_tests` unconditionally) and `--scope Aquarium` selects nothing (an `APP_ORDER` app with zero suite ids), yet both are documented values and both exit with a message that reads like a typo. | B | `runner.py:231-232,306-309`; `_meta.py:289`; §3.3 |
| `B-18` | — | Neither order is cost-aware, but the switch is a large cost improvement for a CORE failure (~40 minutes → ~6) and that argument is not made in the TASK-566 landing note; the counter-risk is that two live-network 45–60 s cells land at indices 14–15. | B | §4.2 index table; §6 cost table |
| `C-16` | — | Hardcoded app slots in `T-ERR-02`/`T-ERR-06` although `APP_SLOT` is imported at the top of the same module, and neither checks the switch's `ok`, so a failed switch reads the previous app's state. | C | `shell.py:3302,3305,3371,3372`; `shell.py:43` |
| `C-17` | — | `shell.py` silently requires Python ≥ 3.12 (PEP 701 nested same-type quotes in an f-string); on 3.11 the whole module, and therefore the whole suite, fails to import, and nothing declares a floor. | C | `shell.py:990` |
| `C-19` | — | `_order.py`'s `EDGE_ADJUDICATION` misdescribes `T165` — the cited `skip()` is unreachable because `_tb_precondition` drives the offset to 0 — and the adjudication is a stated precondition of the order switch. | C | `_order.py:213-216` vs `shell.py:2628-2633`, `_helpers.py:437-439` |
| `C-20` | — | `T_BI_04`'s claimed subject ("cmdTap delivers the Release phase") is unobservable in a reply `cmdTap` synthesises from the hit-test; what remains duplicates `T081`'s assertion. | C | `shell.py:1200-1207` vs `:169-176` |
| `D-14` | — | `T077`'s oracle is negative-only with a passing default: `hit not in (…)` lets a lost reply, a busy-gate swallow and any future region name all pass, and `ok` is never checked — twelve lines from `T088`, which asserts the positive pair. | D | `shell.py:66-71` vs `:466-469`; `cmdTouch.cpp:48-51` |
| `D-16` | — | `_PLEDIT_X`/`_PLSTART_Y`/`_PLEND_Y` are literals duplicating a derivation `coords.pledit_swipe()` already owns, and both paths are used in the same family, so a skin-layout change moves one and not the other. | D | `_helpers.py:149-153` vs `coords.py:154-181`; `shell.py:866` vs `:2343` |
| `D-17` | — | Two ids bundle enough assertions that a failure cannot be localised — 11 hit checks under `T088`, six across four regions plus a cooldown and a log line under `T087` — both accumulating into one `fail()` string. | D | `shell.py:456-487`, `:364-418` |
| `E-12` | — | `T_PLR_13`'s only assertion is a strict subset of `T_PLR_15`'s, at the cost of a second full 200-entry browser walk per run. | E | `player.py:805-814` vs `:895-904` |
| `E-14` | — | `run/player-gate`'s log parser sees a `FLAKY-PASS` id twice, because `print_results` prints declared flakes again under their own heading in the same `  <id>: <status>` shape — a second unenumerated coupling to the unspecified summary format. | E | `lib/results.py:270-283`; `run/player-gate:161-163,203-216` |
| `E-15` | — | The player family restores almost nothing it toggles — shuffle, repeat, an open file browser, an arbitrary app and a non-zero scroll offset on failure paths — 17 of 31 rows carrying S14, with one `fbCancel` and one shuffle/repeat restore in the whole module. | E | `player.py:295`, `:1623-1624`, `:110-111`, `:1127-1131` |
| `E-16` | — | `T_PLR_11`'s fixture-missing skip is unreachable: its guard requires `not r.get("ok")` from a `dbgReport()` that prints `"ok":true` unconditionally, so a genuinely absent fixture falls through and fails — louder, but by accident. | E | `player.py:605-608`; `localPlayerApp.cpp:418-422` |
| `F-9` | — | Only four of thirty WebRadio bodies restore anything and only three use a `finally`; the other 26 leave some combination of fifteen synthetic dead stations, the forced-fail flag, an injected state, a moved index, a changed vis mode and a bare `set bgPoll` pair. | F | `webradio.py:860-865,949-954,1048-1053,1232`; `_helpers.py:444-454` |
| `F-12` | — | `webradio_long_soak.py` is an instrument filed as a test: no verdict line and no non-zero exit on any anomaly path — DUT silence, render freeze, stuck mechanism and an unexpected boot marker all just increment a counter. | F | `webradio_long_soak.py:495-655`; §7.3 |
| `F-13` | — | A stale comment in the VIS header claims `VIS_WAVE` is unreachable and reads back −1; `cmdGet.cpp` maps it to 5. No oracle depends on it. | F | `webradio.py:1267`; `cmdGet.cpp:477-487` |
| `F-16` | — | Three firmware constants mirrored as literals in WebRadio (`SPEC_BARS`, the two volume caps ×8), one carrying an already-stale line cite. | F | `webradio.py:1504,837-846,989`; `vuMeter.h:50`; `audioEngine.h:62,70`; `webRadioApp.h:73` |
| `F-18` | — | Uncited thresholds throughout WebRadio, including a no-loop window equal to one `WR_SKIP_PACE_MS` interval — so a slow runaway passes it. | F | `webradio.py:667,710,745,895,908,921,1000,1365,1380,1408`; `webRadioApp.h:72` |
| `G-12` | `H-13` | Six plan entries no longer describe their bodies — four Stock rows specifying retired proxies or the wrong tap, and both Teletext rows still reading `planned`/`[Blocked]` with one specifying markers (`KEYPAD_OPEN`) the firmware has never emitted. | G, H | `test_plan.md:1802-1811,1868-1877,1890-1899,2444,4459-4480`; `teletextApp.cpp:297-330` |
| `G-16` | — | `T171` and `T179` are registry ids whose entire body is one `skip()` — no device read, no branch — honestly labelled `[MANUAL]` against a "no pixel-read command" premise that `run/screendump` made stale, while both count toward the 213-id total. | G | `stock.py:155-158,411-414`; `test_plan.md:1813-1822,1901-1910`; `webradio.py:1398-1428` |
| `G-17` | — | The TASK-385/386 heap diagnostics are never compared to anything: eleven `_diag_snapshot`s across two ids, all printed or interpolated into a `fail()` string, no threshold and no delta — so `T204`'s "under heap pressure" half cannot fail. | G | `stock.py:890,917,1268,1323,1329`; `_helpers.py:334-375` |
| `G-10` | — | Three failure messages attribute an upstream timeout to a named firmware fix ("guard fix may not have landed", "TASK-121 fix may be missing") while the discriminating value — `stockChartProgress` — is read by the helper and dropped. | G | `stock.py:795,1247`; `_helpers.py:272-276` |
| `G-14` | — | `T169`'s flake candidacy blames yahoo/network flakiness for a body that touches no upstream; its real failure mode is a serial-flood timeout during the launch quote batch, which is why it is the only body in the file wrapped in `_bgpoll_suspended`. | G | `flaky.yaml:155-156`; `stock.py:75-101`; `stockApp.cpp:71` |
| `G-15` | — | Uncited thresholds throughout Stock — `65.0` twice, `45.0` nine times, `60.0` three times, `200.0`, `20.0`, `5.0` — while the four governing `#define`s sit adjacent in a header the suite already needs to parse. | G | `stockShared.h:18-21`; `stock.py:42,118,311,344,742,793,854,921,1009,1246,1325,1448` |
| `G-18` | — | Two Stock comments state the firmware wrongly in the direction that hides a bug: the back-tap zone is understated by half, and "lastChartFetch resets to 0 on tab change" is false — nothing resets it, which is why a `> 0` poll is vacuous. | G | `stock.py:266` vs `stockApp.cpp:112`; `stock.py:343` vs `:124` |
| `H-14` | — | The Clock family's only plan-of-record is the `regression_suite` report that carries `H-2`'s five wrong criterion mappings: 17 of the 26 data-app ids have no `### ` plan entry, and the 14 clock ids bind through that document's inventory table instead. | H | `grep -n "^### T_CLK_" test_plan.md` → none; `m-clock-styles.md:11-55`; `id_binding_exceptions.md:65-67` |
| `H-15` | — | `_order.py` has no entry for any of the 26 data-app ids although they are registry indices 0–25 and therefore precede all 187 others; the three real dependencies this corpus has are all invisible to the edge enumeration. | H | `grep -n "T_CLK\|T27\|T_PR" _order.py` → no hits |
| `H-16` | — | `T_PRM_02` is the most flake-exposed id in its corpus — a 300 s live-network window and five bounds, one from a single 2026-07 measurement — and is not in `flaky.yaml`, while `T_PR_05` is and should be retired rather than measured once `H-5` lands. | H | `flaky.yaml:150-160`; `planeradar.py:312-406` |
| `H-17` | — | Three suite bodies reach into `Dut._wait_for_ready()`, a private — the only reboot-settle primitive there is, and the one operation that makes a persistence test possible is reached by convention. | H | `planeradar.py:142,303`; `player.py:1610`; `lib/dut.py:606-620` |
| `H-18` | — | Uncited thresholds throughout the data-app corpus, including `T_CLK_11`'s 4096 B leak bound on a code path that allocates nothing — against which `T_PR_02`'s and `T_PRM_02`'s bounds all carry a derivation and are the two best-graded network ids in the package. | H | `clock.py:188`; `teletext.py:44,73,110,186`; `planeradar.py:190-218,460-487` vs `:57-63,334-337` |
| `H-19` | — | `console.cpp`'s `switchApp` help string is stale (`<appId 0..8>` against `APP_COUNT = 13`) — the same mirror-drift class as `A-8`, in the firmware, where a reader would trust it. | H | `console.cpp:91`; `app_ids_gen.py:4-8` |

---

## 3. The themes

The register is a list. This section is the argument: six structural causes account for 104 of the
130 rows, and every one of them is a *mechanism the project built* rather than a mistake somebody
made in a test body. That distinction matters, because it decides whether the fix is 130 edits or
six.

The six were derived from the register, not from the brief. Five of the brief's candidates
survived contact with the evidence; one — "mirrored firmware constants with no gate" — turned out
to be the *second* half of a larger theme about observables, and is presented that way. A sixth
theme the brief did not name emerged from the counts and is, on the evidence, the most important
one in the document: **T3, the quality of a test tracks the quality of the observable it was
given.** It is the only theme with a controlled experiment behind it.

### T1 — Debug injectors armed by a `set` that nothing clears

**What it is.** Three firmware debug setters latch a flag that changes the app's behaviour for the
rest of the boot, and are cleared by nothing a test suite naturally does — not `init()`, not
`resume()`, not an app switch, not a fresh fetch. `set wrDeadUrls N` arms `_debugForceConnFail`
(`F-4`); `set triggerHeatmap 1` writes a `prevSubView` the firmware has no path out of (`G-1`);
`set prInjectAircraft` sets `_injected`, which guards every real-fetch site in PlaneRadar (`H-1`).
Three families, three subsystems, three separate authors of the firmware side, one shape. WP-H went
looking for the third deliberately after WP-F and WP-G found the first two, and found it in one
pass — which suggests the shape, not the count, is the finding.

**What it costs today.** `F-4` is predicted to force connect-failure on eleven WebRadio ids in
every full-suite run, and `wrState=5` — the exact state the flag assigns — is the symptom
`flaky.yaml:72-108` has recorded against `T_WR_COEX_01` and `T_WR_VOL_03` since TASK-540
attributed it to radio-browser.info churn. That is **a year of a suite-order defect filed as
network flake**, plus six `_order.py` dismissals resting on a premise (the station *count* comes
from the test's own fetch) that is true and orthogonal to the flag. `G-1` is worse in scope: the
entire eight-id stock-002 block plus `T192`/`T193`/`T194` are predicted to exit
`SKIP: could not normalize to list view` in every full run, with `T-BUSY-01` — a CORE id — passing
vacuously on a stale `chartLen` behind them. `H-1` costs no verdict today, and only by accident of
registry order: no later id enters PlaneRadar. All three share the property that makes them
invisible — an isolated `run/test-targeted` rerun cold-boots with the flag clear and passes, which
is precisely the trap `feedback_isolated_rerun_vs_suite_state` describes.

**Cheapest thing that stops it recurring.** Not the three one-line suite fixes, though those should
land first. The recurrence-stopper is a **firmware rule**: a debug injector is a within-visit
instrument, so `App::resume()` clears its own injection flags, and `init()` already does. That is
three one-line firmware edits and it makes an app switch a recovery path for the whole class,
including injectors nobody has written yet. Second-cheapest, and complementary: teach
`_order.edge_candidates()` the shape "a `set <key>` in a test or reachable helper with no matching
restore on all exit paths" (`B-4`'s proposal (b)) so a fourth instance fails
`test_class_order.py` instead of being discovered by an audit.

### T2 — Oracles that cannot observe their subject

**What it is.** A test names a behaviour, and its comparison cannot see that behaviour — because
the value it reads is one the harness itself wrote (`G-7`, `H-3`, `F-3`, `D-1`), because the
subject is a rendered pixel and the oracle is a struct member (`H-2`, `G-16`), because the marker
it greps for is never printed (`D-7`), or because the detector is swallowed by the layer beneath it
(`C-2`). Twenty-one ids are HOLLOW by this route and a large share of the 64 WEAK verdicts are the
same defect one degree milder.

**What it costs today.** The sharpest instance is not a test at all, it is a *record*:
`regression_suite/m-clock-styles.md:46-55` books five M-CLOCK-STYLES exit criteria as **PASS** —
flip animation ≤500 ms, Nixie tube bounds, VFD segment visibility, the 1000 ms tick gate, no pixel
residue — against oracles that read a settings byte, plus a sixth (C3) claiming a power cycle no
clock id performs. A clock face rendering as a solid black rectangle passes all fourteen ids and
all five criteria (`H-2`). That is a milestone recorded complete on evidence that would survive
deleting all four face renderers, and it is the one finding in this review that misstates a
*shipped* result rather than a test's strength. `F-20` is the same class one level up: ADR-045's
"≤ 6 auto-skips" term had zero variance in the gate run that closed M-WEBRADIO, because every
trial played station 0. And `C-2`'s `T-UART-01` cannot observe JSON garbling at all, because
`read_json` discards the malformed line and returns the next one — so ADR-042 E1's claim has never
been tested by the id that exists for it.

**Cheapest thing that stops it recurring.** A rule with teeth, applied where the claim is written
rather than where the code is: **a `regression_suite/*.md` exit criterion may cite a test id only
if that id's oracle reads a value in the criterion's own vocabulary.** A criterion about pixels
cites a screendump; a criterion about timing cites a counter. Mechanically, the cheapest first step
is unblocking `run/screendump` (`A-1` — it has been broken at import since TASK-555, and four
WebRadio ids already use the screendump pattern for exactly this class of claim), then re-opening
the five clock criteria as DEFERRED. Second: for the tautology half, one grep gate — a `set <key>`
and a `get <key>` on the same key inside one body, with no third command between them, is a
tautology candidate and should have to justify itself.

### T3 — The quality of a test tracks the quality of the observable it was given

**What it is.** This is the theme the brief did not name and the counts insist on. The six family
audits were written by the same VE, against the same harness, in the same period, and their SOUND
rates are 77 % (LocalPlayer), 67 % (PlaneRadar), 67 % (Teletext), 59 % (CORE), 56 % (shell
FEATURE), 50 % (WebRadio), 40 % (Stock), **7 % (Clock)**. That is an eleven-fold spread with
author, harness and period held constant. What varies is what the firmware offered. ADR-059 D12
designed `get plOrder`, `get plCursor` and `advance`'s `moved`/`row`/`reshuffled` *before* the
tests, and the seven ids built on them compare exact permutations and exact triples — the strongest
run of consecutive SOUND rows in the review. TASK-112 added `quoteOkCount`/`fetchOkCount` as a
test-quality fix, and the four SOUND Stock fetch ids are exactly the four built on them. Where no
observable was designed, the test reached for the nearest injector and asserted its own input.

**What it costs today.** It costs the 21 HOLLOW ids, most of the 64 WEAK ones, and — read the other
way — it is the reason five ids' worth of Stock render claims sit parked on `[MANUAL]` (`G-16`),
the reason WebRadio asserts a state byte because the rig cannot hear (`F-3`, `F-7`), and the reason
Clock scores 7 %. It also has a *positive* cost being paid right now: `H-5` records a deterministic
PlaneRadar fault injector, built by TASK-361, with **no consumer anywhere in the repo**, while
`T_PR_05` — the id it was built for — has been a permanent SKIP since 2026-07-11 and its docstring
still says no such hook exists. And `G-3` is the mirror image: five stock fetch diagnostics have
been printing `None` for months because `get fetchErrorCode` does not exist, including the two
TASK-385/386 added expressly so a failure would carry its own evidence.

**Cheapest thing that stops it recurring.** Make the observable a deliverable of the feature, not
of the test: **no app ships a behaviour whose acceptance criterion cannot be read through its own
`dbgGet`.** The `NEW-APP-CHECKLIST` is the existing place for that rule. Concretely and cheaply
today, the register names the exact gaps — `chartLo`/`chartHi`, `lastHeatmapFetch`, `stockMode`,
`fetchErrorCode` (`G-3`, `B-5`), a seek-commit log line (`D-7`/`D-8`), a clock frame or
`_lastTickMs` counter (`H-2`) — and each is a `case` in an existing `dbgGet` whose struct field
already exists. That is a day of firmware work that would move more verdicts than a month of test
edits.

### T4 — Skip-as-pass, and a gate that blocks only on `FAIL`

**What it is.** `_gate.py:128-129` sets `blocked_by` on `RESULTS.get(tid,"").startswith("FAIL")`
and on nothing else. A `skip()` is not a FAIL; neither is `FLAKY-PASS`. And 31 of the 43 CORE ids
have at least one `skip()` exit (`C-5`), every one of them a CORE precondition that did not hold —
which is exactly the condition the class exists to stop the run on. The suite has 262 `skip()` call
sites, and a skipped cell is invisible in the summary: twelve dead cells look identical to twelve
passing ones.

**What it costs today.** The class hierarchy's entire promise — a class-N failure invalidates class
N+1 — is delivered by a string-prefix test the common failure mode does not match, so the CORE
block almost never fires (`C-5`). `T091` is a CORE id whose own flake declaration makes it
incapable of blocking (`C-6`). A SKIPped HEALTH check is announced as `[health] PASS` with a
sentence asserting the thing that did not run, while `_triage` calls the same run degraded in the
same output (`C-4`). Downstream, six residue ids can PASS or SKIP and never FAIL (`D-2`), two ids
are structurally dead in every full-suite run and nothing says so (`B-3`), and twelve Spotify ids
plus (predicted) seven Stock ids produce no verdict at all. The one place the project got this
right is `run/player-gate`, which compares per-id against a declared pass set, so a declared PASS
that skips is a REGRESS — the S7 surface is caught inside the gate and silent everywhere else.

**Cheapest thing that stops it recurring.** One new result value. `blocked_precondition(tid, why)`
in `lib/results.py`, treated as blocking by `_gate` and as a distinct bucket by `print_results` —
"a CORE test that cannot run is not *not applicable*, it is an unestablished premise". Then convert
the 31 CORE sites, and make `health_phase` treat any non-`PASS` health row as not-established
(`C-4`). Cheaper still, and worth doing first because it takes an afternoon: print the SKIP count
per scope in the run summary. A number that goes up when coverage disappears is most of what is
missing.

### T5 — Mirrored firmware facts, in a project that built the parsers

**What it is.** The suite re-declares firmware constants, enum values, app slots, layout
coordinates and generated-header values in at least nine registered places (`A-9`, `A-10`, `A-18`,
`C-13`, `D-6`, `F-16`, `H-12`, `H-19`, and `A-8`'s clock slots), and in every case a generator, a
parser or a generated Python module already exists that it could import instead. The sharpest
instance is `H-12`: `app/gen/teletext_layout.h` is *generated*, `teletext.py` mirrors six of its
y-values by hand, and `import coords as _c` sits at the top of that file **unused**. `D-6` is the
second sharpest — the Settings geometry re-implements `_appListRowH()`'s formula in Python, using a
count that lives in `app/gen/`.

**What it costs today.** Less than it looks, and that is the point. WP-H checked and every mirrored
value is *correct today* (`A-8` is refuted as a live defect and confirmed as a latent one). The
cost is entirely future and entirely silent: the firmware clamps every coordinate the Stock suite
mirrors, so a drifted value never *misses* — it selects a different row or tab, which only the six
ids that read their selection back can see, while twelve are blind and `T188` would still print
"all 4 ranges fetched" (`G-8`, WP-G §8). A mirror that drifts here does not fail the suite; it
quietly changes what the suite is measuring.

**Cheapest thing that stops it recurring.** `A-18`'s proposal, seeded with the register that
already exists: a `gate/check_no_mirrors.py` holding the nine `(suite symbol, firmware symbol)`
pairs and asserting equality at gate time. It is a small script, it runs on the host, and it
converts every future mirror from a silent drift into a build failure. The nine imports that would
retire most of the register are individually one-liners; what has been missing is anything that
notices when a tenth appears.

### T6 — A taxonomy that is 97 % inference, holding up a switch

**What it is.** Of 216 records, `cls` is declared on 6 (2.8 %), `scope` on 57 (26.4 %) and `effect`
on 3. `CORE` — the class that blocks — has never been declared once (`B-15`). All 43 CORE ids are
`seed_cls()` applying a documented default, and `gate/check_test_meta.py` asserts the records are
*well-formed*, never that they are *true*. WP-B's line is the accurate one: **a `cls` value has
never been wrong in this repo, because no `cls` value has ever been written down.**

**What it costs today.** Nothing, because the order switch is HELD. It costs everything the moment
it flips. Seven of the 43 undeclared CORE ids are single-app Stock tests whose precondition is a
live HTTPS fetch, and `T-BUSY-01` FAILs rather than skips — from index 14, that failure NOT-RUNs
all 167 FEATURE ids (`B-1`). `T133`, also CORE, is a host-side source grep: a checkout missing
`lib/SpotifyArduino/` NOT-RUNs the FEATURE suite from index 6 on a host file-existence failure
(`B-2`). And the enumeration delivered *as the switch's precondition* under-reports three
demonstrated order-dependence shapes (`B-4`), all three in the direction that grants a false
all-clear — to which this review adds three more clusters (`C9`, `C10`, `C11`) the same scanner
cannot see. WP-Z's disagreement with WP-B's own P3 grading is recorded in the register: on the
evidence assembled since, `B-15` is a P1, because it is the one finding that converts every other
CORE finding from "a weak test" into "a weak test with a veto".

**Cheapest thing that stops it recurring.** Make `check_test_meta.py` fail on an **undeclared
CORE**. Forty-three `@meta(cls="CORE", cls_reason=…)` declarations is an afternoon, and the act of
writing them is the audit — `B-1` and `B-2` would both have been caught by someone trying to write
the reason string for a Stock fetch test and a host-file grep. Do it before the switch flips, not
after.

### What the themes do *not* explain

Twenty-six register rows are ordinary defects with no structural parent: an inverted guard
(`C-1`), a teardown writing the wrong enum value (`F-1`), a broken entry point (`A-1`), five
duplicate-assertion clusters (`B-16`), the plan-id collisions (`F-2`), the stale plan rows
(`G-12`). They are cheap, they are individually small, and they should be fixed as hygiene rather
than reasoned about. Grouping them into a theme they do not belong to would overstate how much of
this suite has a systemic problem.

---

## 4. Proposed task rows for @PM

**A proposal, not an edit.** `docs/project/tasks.md` was not touched. Ids `TASK-579`…`TASK-620` are
provisional (578 is the highest in use across the three boards today); renumber freely. Every row
is in the board's format, is a pointer per BP-069 — it names the finding key and the package, and
does not restate the evidence — and is under the 400-character ROWLEN limit `run/check-docs`
enforces. Priorities are the register's severities, except where a P2 becomes P1 by being a
precondition of something else.

Suggested paste target: a new `## M-TESTQUAL — test-suite quality remediation` section, with the
four groups below as sub-headings. The four decision rows must not be scheduled by @PM alone.

### 4.1 Fix now — a wrong verdict is being produced today (11)

| task | pri | status | title |
|---|---|---|---|
| **TASK-579** | P1 | PROPOSED | **`set wrDeadUrls` arms a forced connect-fail nothing clears** — WP-F `F-4`, cluster `C9`. Suite: clear in `_vs_precondition_webradio`'s callers. Firmware: clear the flag in `resume()`. Then re-open TASK-540 with the order hypothesis and withdraw the two `flaky.yaml` "wrState=5" declarations it explains |
| **TASK-580** | P1 | PROPOSED | **`set triggerHeatmap` wedges `prevSubView` and the whole stock-002 block behind it** — WP-G `G-1`, cluster `C10`. One-line suite fix (`_ensure_stock_list_view` before the inject); better firmware fix is to make the injector stamp `List` the way `enter()` does. Seven ids predicted permanent SKIP, one CORE id vacuous |
| **TASK-581** | P1 | PROPOSED | **`set prInjectAircraft` freezes PlaneRadar for the rest of the boot** — WP-H `H-1`, cluster `C11`. `T_PRI_01` never clears; `resume()` does not either. One line in `planeradar.py`, one in `PlaneRadarApp::resume()`. Costs no verdict today only by accident of registry order |
| **TASK-582** | P1 | PROPOSED | **`T-BUSY-05`'s guard is inverted — it passes exactly on the regression** — WP-C `C-1`. Correct the predicate, then re-run: this CORE cell has been green on an untested path for its whole life and there is no evidence either way about the behaviour it covers |
| **TASK-583** | P1 | PROPOSED | **the `T_WR_ERR_*` teardown writes `ERROR_WIFI` believing it is STOPPED** — WP-F `F-1`. One character (`set wrState 0`). Makes `T_WR_ERR_03` non-BROKEN and stops all four ids parking the app in an error state ahead of six ids whose oracle is `wrState == 2` |
| **TASK-584** | P1 | PROPOSED | **six `_check_residue` callers turn the regression into a SKIP** — WP-D `D-2`, WP-B `B-11`, WP-G `G-5`. `fail()` not `skip()` at all six sites in one pass, plus `T182`'s two taskbar misses. Six ids currently can PASS or SKIP and can never FAIL |
| **TASK-585** | P1 | PROPOSED | **the Stock fetch oracle defaults to an unconditional pass** — WP-G `G-2`. `_stock_ok_count`'s `-1` satisfies `_wait_chart_complete` on the first poll across nine ids. Fix the two counters, and make `_stock_get` assert the reply's `var` — which also closes WP-C `C-18`'s raced-reply hazard at one choke point |
| **TASK-586** | P1 | PROPOSED | **`T_PLR_25` is a deterministic 60 s false red on the only env that dispatches it** — WP-E `E-2`/§7.2. Delete the registry copy and let the standalone body own the id (the gate's pass set already assumes it), porting the two things the registry copy does better first |
| **TASK-587** | P1 | PROPOSED | **five M-CLOCK-STYLES exit criteria are booked PASS against oracles that cannot see them** — WP-H `H-2`. Re-open C4/C5/C6/C8 (and C1) as DEFERRED in `regression_suite/m-clock-styles.md` and correct C3, which claims a power cycle no clock id performs. A record correction, not a test fix |
| **TASK-588** | P1 | PROPOSED | **a SKIPped HEALTH check is announced as `[health] PASS`** — WP-C `C-4`. `health_phase` must treat any non-`PASS` row as not-established, and the banner must be built from `health_verdict()` rather than a literal, which today contradicts `_triage` in the same output |
| **TASK-589** | P1 | PROPOSED | **`run/screendump` has been hard-broken at import since TASK-555** — WP-A `A-1`, plus its three dependants. It is documented in `CLAUDE.md` and is the instrument TASK-587 and WP-G `G-16` both need, so it blocks the pixel-oracle work |

### 4.2 Fix next — a guarantee is weaker than claimed (16)

| task | pri | status | title |
|---|---|---|---|
| **TASK-590** | P1 | PROPOSED | **a skip gates nothing: introduce `blocked_precondition`** — WP-C `C-5`/`C-6`. 31 of 43 CORE ids exit as SKIPs, and `_gate` blocks only on `FAIL`, so the class hierarchy's promise is delivered by a string-prefix test the common failure mode does not match. Also decide whether CORE may carry a flake declaration at all |
| **TASK-591** | P1 | PROPOSED | **declare the 43 CORE ids, and gate on an undeclared CORE** — WP-B `B-15`/`B-1`/`B-2`. Writing the reason strings *is* the audit: the seven single-app Stock CORE ids and `T133`'s host-file grep would both have been caught by it. Precondition of TASK-566's switch — see the decision row |
| **TASK-592** | P2 | PROPOSED | **the order switch's edge enumeration under-reports three shapes** — WP-B `B-4`. Add the readiness-flag SKIP and unrestored-`set` scanners; feed `EDGE_ADJUDICATION`, which `test_class_order.py` already forces to stay complete. Clusters `C7`–`C11` from this review are all currently invisible to it |
| **TASK-593** | P2 | PROPOSED | **the debug-surface gaps that cause the WEAK/HOLLOW verdicts** — WP-Z Theme T3. Add the `dbgGet` cases the suite needs and whose struct fields exist (`G-3`, `B-5`), a seek-commit log line (`D-7`/`D-8`) and a clock tick/frame counter (`H-2`). A day of firmware moves more verdicts than a month of test edits |
| **TASK-594** | P2 | PROPOSED | **`T_WX_04`/`T_CX_04` have never run in a full suite** — WP-B `B-3`, WP-D `D-3`. Their own three predecessors destroy the precondition. Move them to the head of their family or add a `set weatherReady 0`/`set cryptoReady 0` reset, and adjudicate both in `_order.py` |
| **TASK-595** | P2 | PROPOSED | **every flake declaration examined is mismatched with its call site, in both directions** — WP-C `C-7`, WP-E `E-3`, WP-F `F-8`. Four declared ids never call `flake()`; five undeclared ones do and report bookkeeping instead of the symptom. Sweep `flaky.yaml` against the bodies. Do TASK-579 first — one declared cause is wrong |
| **TASK-596** | P2 | PROPOSED | **seven restores default to a value that rewrites persisted state** — WP-C `C-12`, WP-D `D-15`, WP-E `E-4`. Read into a variable, `skip()` on absence, never default an oracle or a restore to a value that passes. Pair with WP-A `A-14`'s `Dut.get_int`/`get_str` accessor, which closes the class |
| **TASK-597** | P2 | PROPOSED | **`run/player-gate`'s HEALTH machinery cannot fire** — WP-E `E-13`. It refuses `DUT_HEALTH=warn\|skip` and maps exit 4, but invokes the runner without `--class-order`, so no health phase runs. Needs a `--health-phase` flag that does not require adopting class ordering, or the banner must stop implying it |
| **TASK-598** | P2 | PROPOSED | **the four "BUG-1 guard" ids assert a printf on a branch that calls no app handler** — WP-D `D-1`. Either give the four small apps a real `cmdTap` branch (the shape `T148` is SOUND on) or delete the ids and record that they have no canvas interaction. Do not leave a green row asserting a literal |
| **TASK-599** | P2 | PROPOSED | **the rig-vs-firmware exit contract is honoured by 4 files, and four harnesses bypass `lib/dut.py` entirely** — WP-A `A-2`/`A-4`. Route the eight bare `Dut` constructors through one handler and migrate the four `SerialDut` clones, which today skip the DRD stamp, the firmware verify and the cooldown drain |
| **TASK-600** | P2 | PROPOSED | **`gen_get_keys.py` sees 43 of 71+ `get` keys** — WP-A `A-3`. One-word glob fix (`*.h` → `*.[hc]*`); 10 `dbgGet()` bodies moved to `.cpp` under M-SRCLAYOUT and are invisible, so `run/task488`'s "every key resolves" covers ~60 %. Expect new unknowns on the next run |
| **TASK-601** | P2 | PROPOSED | **`run/test-targeted` and `run/player-gate` skip the TLS-pin preflight** — WP-A `A-5`. Move it into `run/lib.sh` and call it from all three. It exists so a CA rotation does not present as a spray of cryptic fetch FAILs 30 minutes in (TASK-298/LL-103) |
| **TASK-602** | P2 | PROPOSED | **state leakage: give the suite the context managers it has one of** — WP-B `B-5`/`B-6`/`B-7`, WP-E `E-7`/`E-15`, WP-F `F-9`, WP-H `H-10`. `_bgpoll_suspended` is the pattern and is used at 20 of 41 sites. Note `B-5` needs `stockMode` gettable first (TASK-593) and `H-10` writes real flash |
| **TASK-603** | P2 | PROPOSED | **ids that are counted as coverage and assert nothing** — WP-D `D-4` (`T136`, body is one `skip()`, archive still says pass), WP-G `G-16` (`T171`/`T179`, same), WP-E `E-8` (two unfalsifiable player claims). Retire or automate each, and record the retirement — they inflate the 213-id total |
| **TASK-604** | P2 | PROPOSED | **six ids drive a different app than their record says** — WP-E `E-5`, WP-F `F-11`, WP-G `G-13`. Add `@meta(scope=…, scope_reason="cross-mode")`; the mechanism is used correctly two modules away. Today `--scope Spotify`, `--scope WebRadio` and `--scope taskbar` each miss ids that cover them |
| **TASK-605** | P2 | PROPOSED | **two ids reach WebRadio only because of what ran before them** — WP-E `E-11`, WP-F `F-6`. `_switch_to("WebRadio")` taps slot 11 → `appIdx = 0`, the player slot; `webradio.py`'s own header warns against the helper and names the correct entry. Neither id has ever been independently verifiable |

### 4.3 Hygiene (10)

| task | pri | status | title |
|---|---|---|---|
| **TASK-606** | P3 | PROPOSED | **nothing gates a mirrored firmware constant** — WP-A `A-18`, seeded with the nine-mirror register (`A-8`, `A-9`, `A-10`, `C-13`, `D-6`, `F-16`, `H-12`, `H-19`). A host gate asserting each `(suite symbol, firmware symbol)` pair converts every future mirror from a silent drift into a build failure |
| **TASK-607** | P3 | PROPOSED | **57 hand-written poll loops, 16 app-entry helpers, and a timeout policy with zero users** — WP-A `A-13`/`A-11`. One `wait_until()` and one `enter_app()` in `_helpers.py`, then adopt `lib.dut.TIMEOUT`. Do it before M-TESTARCH's `watch` primitive, so that lands in one file instead of 57 |
| **TASK-608** | P3 | PROPOSED | **the results summary is an unspecified machine interface with three consumers** — WP-A `A-6`/`A-7`, WP-E `E-14`. A `--results-json` sidecar for `run/player-gate`, deletion of `run_sync_tests.py`'s private results copy, and dedup of the `FLAKY-PASS` double-parse. TASK-573 was this class of defect |
| **TASK-609** | P3 | PROPOSED | **six DUT scripts run their whole suite at `import`** — WP-A `A-12`. Wrap each in `if __name__ == "__main__":`. Mechanical, six files, and it unblocks any import-level lint over `app/tools/`; one such import reset the board mid-review and cost an observation window |
| **TASK-610** | P3 | PROPOSED | **26 ids collapse to about 11 assertions** — WP-B `B-16`, WP-H `H-11`, WP-D `D-13`, WP-F `F-17`. Collapse the clock style cluster into `T_CLK_06`, merge the two Settings drill ids, and either fold or re-aim the two "same test with a weaker bound" pairs. Each costs a full duplicate precondition run |
| **TASK-611** | P3 | PROPOSED | **`test_plan.md` integrity: three id collisions and six stale rows** — WP-F `F-2`, WP-G `G-11`/`G-12`, WP-H `H-13`/`H-14`. Two headings bind C6 entries pointing at bodies that do not implement them; six Steps blocks no longer describe their bodies, one naming markers the firmware never emitted |
| **TASK-612** | P3 | PROPOSED | **`--scope <path>` cannot resolve 55 % of the firmware tree, and two prefixes name missing directories** — WP-B `B-9`/`B-10`. EC-D4's "one command from a changed file" fails for `settings/`, `player/`, `audio/`, `touch/` and 25 root files; the `taskbar` scope is unreachable from any path |
| **TASK-613** | P3 | PROPOSED | **uncited thresholds: >1 000 literals, 3 citing a firmware constant** — WP-F `F-18`, WP-G `G-15`, WP-H `H-18`, WP-A §5. Tie each to a parsed constant or a dated measurement, starting with the four adjacent `#define`s Stock already needs parsed and the no-loop window equal to one skip-pace interval |
| **TASK-614** | P3 | PROPOSED | **registry and tooling honesty** — WP-B `B-13` (`T_AE_04`: declared `impl`, one body, no registry, escapes C6 both ways), WP-F `F-12` (a soak that can never fail, named `test_*`), WP-A `A-16`/`A-17`/`A-19` (duplicate gate runners, generated modules with zero importers, a hardcoded smoke list) |
| **TASK-615** | P3 | PROPOSED | **small correctness debts with named fixes** — WP-H `H-17` (promote `Dut.reboot_and_wait`), WP-C `C-17` (undeclared Python ≥3.12 floor), `C-19` + WP-H `H-15` (an inaccurate `EDGE_ADJUDICATION` row, and no rows at all for registry indices 0–25), `C-16`/`C-20`, `G-18` |

### 4.4 Decisions for a human — VE must not decide these alone (4)

| task | pri | status | title |
|---|---|---|---|
| **TASK-616** | P1 | DECISION | **does the M-WEBRADIO close stand?** WP-F §8/`F-19`/`F-20`: the ADR-045 gate proved sustained decode for 60 s ×10 — a real result — but the "≤ 6 auto-skips" half had zero variance (every trial, one station, `skips=0`), it ran on a build that does not ship, and records no build identity. Re-affirm, re-run or re-open. @PM/@Architect |
| **TASK-617** | P1 | DECISION | **may TASK-566's class-order switch flip?** VE's reading is **no, not yet**: `B-15` (no CORE was ever declared), `B-1` (seven CORE ids need a live fetch; one FAILs, from index 14, NOT-RUNning 167), `B-2`, `B-4` plus clusters `C9`–`C11`, all invisible to the enumeration delivered as its precondition. TASK-591/592 are the exit criteria. @PM/@Architect |
| **TASK-618** | P1 | DECISION | **`run/test` and `run/test-targeted` cannot be run while the board is pinned** — their EXIT trap restores `ENV_PROD`, which `run/lib.sh:16` makes deliberately non-overridable, against TASK-557's standing "do not restore production". Sanction a `DUT_NO_RESTORE=1` opt-out, or grant a one-off exception. Blocks §5 entirely. @PM + human |
| **TASK-619** | P3 | DECISION | **three standing architecture questions this review reopened** — WP-A `A-7` (specify the summary line as an IFC or replace it with a JSON sidecar), `A-17` (wire in `app/gen/mem_layout.py` or delete it and its `run/check` step), WP-B `B-14` (keep the `effect` axis now that its only consumer is CUT, or delete the field and its gate clause). @Architect |

---

## 5. The DUT run that would settle the most

The eight packages filed **58 NEEDS-DUT items** (A 5, B 5, C 7, D 8, E 8, F 9, G 8, H 8). One
session of roughly **80 minutes of board time** resolves about **32 of them** — every one of the
three armed-injector confirmations, both isolated-vs-in-suite splits, the CORE skip census, and
the whole of WP-H's list bar one. What it cannot reach is not a matter of time; it is three hard
walls, named in §5.5.

### 5.1 The blocker that must be cleared before the session can run at all

`run/test` and `run/test-targeted` re-flash `ENV_DEBUG` — which *is* the `-DBOD_WATCH` build the
board is pinned to (`app/platformio.ini:145-158`), so that half is a content no-op — and then their
EXIT trap restores `ENV_PROD` (`run/test:40-42`), which `run/lib.sh:16` makes **deliberately
non-overridable**. That is a direct violation of TASK-557's standing "do not restore production",
and it is unconditional: the trap fires on success, on failure and on interrupt.

So the two entry points this session is built on **cannot be run as shipped**. That is
`TASK-618`, filed in §4.4 as a decision, and it gates everything below. Two acceptable resolutions:
sanction a `DUT_NO_RESTORE=1` opt-out in `run/lib.sh`, or grant an explicit one-off exception with
an immediate re-flash of `cyd2usb_winamp_debug` afterwards. **Do not** resolve it by killing the
script mid-flight — that races the trap-guarded restore and can boot-loop the board.

A second, quieter interaction: `run/test` snapshots `settings.json` at step 0b and restores it at
step 5b. That restore **erases WP-H NEEDS-DUT #7's evidence** (what the suite leaves in persisted
settings). The same opt-out must suppress 5b, or the settings diff must be pulled between the
runner exiting and the trap completing — which is not possible from outside the script.

### 5.2 The session, in order

Budget: ~80 minutes of board time, one window. Hold `systemd-inhibit --mode=block` across it; a
host suspend mid-run is a USB reset. Check `pgrep -f '[p]io device monitor'` first — orphaned
monitors have previously driven hundreds of re-enumerations that read as failing hardware.

**Phase 0 — pre-flight, ~5 min.** Host-side, no risk.

1. `./run/monitor-read 200` — confirm uptime is *advancing* and the log's mtime is ~now. A frozen
   log reads as both a dead board and a healthy one depending on which line you look at.
2. `./run/spiffs pull settings.json`, archived with a timestamp — **the baseline for `H-10`**.
3. `./run/check-datatask-certs` — run it explicitly, because `run/test-targeted` (Phase 3) does not
   (`A-5`), and a CA rotation would otherwise arrive as a spray of fetch FAILs.
4. `./run/dut-health` — pre-flight only. It does not flash. It *does* reset the board on port open,
   which is the price of the check; take it here, before anything is being measured, never after.

**Phase 1 — one full suite run with the raw serial log, ~45 min.** This is the workhorse.

```sh
LOG_FILE=/tmp/testqual-serial.log ./run/test > /tmp/testqual-run.txt 2>&1
```

`LOG_FILE` is the whole point: TASK-386 added it precisely so a suite-order-dependent failure that
only exists after 150 prior tests can be caught in situ, which is exactly the shape of `F-4`,
`G-1` and `H-1`. Redirect, do not pipe — a pipe through `tail` discards the PASS/FAIL summary.

Then, from the two captured files and nothing else:

| From | Settles | Item |
|---|---|---|
| `grep 'forced connect-fail (debug wrDeadUrls)'` between the `T_PLE_WR_160` and `T237` markers | `F-4` — the flag is armed for eleven ids, or it is not | F #1 |
| verdicts of `T_WR_COEX_01` / `T_WR_VOL_03` (predict FAIL, `wrState=5`) | whether TASK-540's network attribution is wrong | F #1 |
| verdicts of `T200`/`T201`/`T202`/`T203`/`T192`/`T193`/`T194` (predict `SKIP: could not normalize to list view`) with `T196` PASS | `G-1`, the largest coverage hole in the review | G #1 |
| verdicts of `T_WX_04` / `T_CX_04` (predict SKIP) | `B-3`/`D-3` — two ids that have never run | B N-B1 |
| the SKIP list intersected with the 43 CORE ids | `C-5`'s "31 of 43 can exit as a skip" in practice, not in `ast` | C #6 |
| `T_PLR_25`'s verdict and duration (predict FAIL at ~60 s, `row sequence [0]`) | `E-2` | E #3 |
| `T139`'s verdict with an empty queue (predict PASS) | `D-10` — the evidence that it tests nothing | D #4 |
| whether `[D]` lines appear in the raw log at the point `T_PLR_18`/`T_PLR_19` run | `E-6` — negative assertions on a channel that can be off | C #7, D #8, E #1 |
| `"skipped":true` in the captured `tap` replies for `T270`/`T271` | `H-8` — a boundary passing on its predecessor's residue | H #6 |
| the eight `_diag_snapshot` lines `T204` already prints, and `T193`'s three | `G-17` — nobody has ever compared them | G #6 |
| `T_CLK_11`'s `h0`/`h1` | `H-18` — whether 4096 was ever a threshold | H #8 |
| verdicts of `T_WR_VIS_03` / `T_WR_VIS_05` (predict SKIP on `isPlaying`) | `F`'s permanent-SKIP question | F #7 |
| `T_GOL_04`'s verdict across the run | WP-D's unattributed extinction risk | D #7 |
| the run's own timestamps around `T092` and `T_PMT_04` | `C`'s force-poll window; whether the 150 s heap-settle proxy ever runs short | C #5, B N-B4 |

**Phase 2 — console probes on the post-run board, ~8 min. Before any reboot.** This is the one
step that is not a `run/` script: `./run/monitor-start`, type the commands into the tmux pane,
`./run/monitor-read 400` to collect. It is listed as such deliberately rather than smuggled in.

```
get prAircraftCount        # H-1: predict 1, callsign AAA111, and it never moves
get prLastHttp             # H-1: predict 0 — tick()'s enqueue is behind !_injected
set prClearInject 1        # H-1: then re-read the count 15 s later; predict it moves
get stockSubView           # G-1 residue: predict "chart", not "list"
get wrState                # F-4 residue
get wrCount / get wrStation 0   # F-5: what index 0 actually was, this run
get stockTicker0 … get stockTicker7   # G-9: is this board still on kDefTickers?
get clockStyle / get prRange          # H-10: what the suite left behind, in RAM
set prForceParseFail 3 ; set triggerPlaneRadarFetch 1 ; get activeError (poll)
                           # H-5: T_PR_05's entire subject, deterministic, in two commands
```

**Phase 3 — cold-boot isolated re-runs, ~20 min.** Each `run/test-targeted` invocation cold-boots,
so each is the *isolated* arm of an isolated-vs-in-suite comparison whose other arm Phase 1 already
captured. This is the only way to establish the split, and an isolated rerun on its own proves
nothing about suite state — which is why Phase 1 must come first.

```sh
./run/test-targeted T_WR_COEX_01          # F #2  — predict isolated PASS vs in-suite FAIL
./run/test-targeted T200                  # G #2a — predict isolated PASS
./run/test-targeted T204,T196,T200        # G #2b — predict the third SKIPs
./run/test-targeted T_PLR_18              # E #2  — predict SKIP when run alone
./run/test-targeted T_PLR_17,T_PLR_18     # E #2  — predict PASS only in this order
./run/test-targeted T_WR_ERR_04           # F #3  — predict SKIP when run alone
./run/test-targeted T150                  # D #6  — does it pass on T149's leftover?
```

**Phase 4 — close out, ~3 min.** `./run/spiffs pull settings.json` and diff against Phase 0
(`H-10`, item H #7); then deliberately restore the user's values, re-flash
`cyd2usb_winamp_debug` if the exception route was taken rather than the opt-out, and
`./run/monitor-start`.

### 5.3 What is safe under the TASK-557 constraint, and what is not

**Safe — no other env is flashed and production is never written:** `run/monitor-start|stop|read`,
`run/spiffs pull|push`, `run/port`, `run/dut-health` (resets on port open, does not flash), the
host gates `run/check`, `run/check-docs`, `run/check-datatask-certs`, `run/check-teletext-api`. All
of Phase 0, Phase 2 and Phase 4 are in this set unconditionally.

**Safe only once TASK-618 is resolved:** `run/test` and `run/test-targeted` — Phases 1 and 3. They
re-flash the same debug env (harmless) but restore production on exit (not harmless).

**Must wait — each flashes a different firmware:** `run/flash`, `run/flash-player`,
`run/flash-webradio`, `run/flash-debug`, `run/flash-fs`, `run/player-gate`, `run/browser-player`,
`run/playorder-player`, `run/wr-gate`, `run/wr-soak`, `run/ae04`, `run/stress`, `run/pr-soak`,
`run/task488`. Nothing in the session above touches any of them, and no finding should be closed by
one until TASK-557 releases the board. `run/screendump` is separately unavailable: it is broken at
import (`A-1`/TASK-589), so the pixel-oracle items are blocked twice over.

### 5.4 Yield

About **32 of the 58** items, and the important property is *which* 32: all three armed-injector
confirmations (`F-4`, `G-1`, `H-1` — the three findings that produce wrong verdicts today), both
order-split comparisons, the CORE skip census that decides `C-5`, the whole of WP-H's list except
its screendump item, and the two entry-path questions (`E-11`/`F-6`) whose ids have never been
independently verifiable. Every one of the eleven **fix now** tasks in §4.1 either is confirmed by
this session or needs no confirmation.

### 5.5 What it leaves open, and why

* **Seven items need a different firmware on the board** — WP-A N-1/N-2/N-4, WP-B N-B3, WP-E #4/#8,
  WP-F #8. These are the `run/ae04`, `run/task488`, `run/player-gate` leg B and `run/wr-gate`
  questions, including the one that could change a milestone's status (`F-20`). They wait on
  TASK-557 releasing the board, and `F-20` additionally needs the TASK-616 ruling *before* it is
  run, not after.
* **Nine items need a code change before hardware can answer them** — WP-C #1/#2/#3/#4, WP-D #2/#5,
  WP-F #6/#9, WP-G #4. `T-BUSY-05` cannot tell us anything until its guard is corrected; garbling
  cannot be observed until `read_json_strict` exists; the `-1` baseline cannot be counted until
  `_stock_ok_count` says when it fires. These are the *outputs* of §4.1 and §4.2, not inputs, and
  each becomes a five-minute confirmation once its task lands.
* **Two items need `run/screendump`** — WP-H #3 (are the four clock faces actually rendering?) and
  WP-G #8 (are `T171`/`T179` automatable?). Both blocked on TASK-589, and both are the evidence
  TASK-587's criteria were booked PASS without.
* **Four items need repetition, not a run** — flake rates (WP-C #6, WP-B N-B2), `T_PLR_12`'s ±256 B
  residual (WP-E #5), and the `bitrateCap` half of WP-F #4. One run yields one sample; a rate needs
  three to five, and a several-minute soak, because a short probe has produced false confidence
  here before.
* **Two items may never be settleable as posed** — WP-B N-B5 (`T-BGPOLL-02`'s reliance on
  `reconnect` is only observable when `reconnect` regresses) and WP-A N-5 (whether WP-A's own
  accidental board reset disturbed a TASK-557 window; that one is a log read by the TASK-557 owner,
  not a DUT run, and is the cheapest open item in the whole list).
* **Phase 2's partials.** The `bitrateCap ≤ 96` half of `F-5` needs a settings change and a second
  fetch; `T_WR_HEAP_04`'s "was that window actually playback?" needs a `get wrPlaying.ms` read
  *inside* the id's own 120 s window, which no external probe can reach.

---

## 6. What this review did not cover

A reader must not mistake this for exhaustive. Eight packages read a great deal of code and ran
none of it, and the limits below are structural, not oversights.

**It is static, and that bounds every verdict in it.** No test was executed, no board was touched,
nothing was flashed. Every "predicted" claim in §5 — the eleven forced-connect-fail ids, the seven
stock-002 skips, the frozen radar — is an inference from reading firmware and harness together, and
each is filed as NEEDS-DUT precisely because a reading can be wrong in ways a run would expose in
minutes. This is also, deliberately, the only honest way to audit a suite: a suite cannot be
trusted to report on its own soundness (M-TESTARCH §7). But it means the review can say a test
*cannot* fail for its stated reason, and cannot say what the board would actually do.

**A SOUND verdict is a statement about the oracle, not about the firmware.** 117 ids assert what
they claim; nothing here says those 117 currently pass, or that the behaviour they cover is
correct. Conversely a HOLLOW verdict does not mean the feature is broken — `H-2`'s clock faces
almost certainly render correctly. The review measured whether a regression would be caught, and
nothing else.

**The host gates were audited as harnesses, not as gates.** WP-A read `gate/check_docs.py`,
`check_test_meta.py`, `check_app_conformance.py`, `test_class_order.py` and the rest for their
result mechanisms, duplication and entry-point wiring (`A-16`, `A-19`), and WP-B executed
`check_docs.py` as a subprocess to measure C6. **No host gate was audited per-check against the
rubric.** Whether `check_docs`'s C1–C6 or `check_app_conformance`'s A1–A7 assert what *they* claim
is an open question of the same shape as Q9, and nobody has asked it. `run/check`'s eleven gates
and `smoke_test.sh` were not read at all.

**`run_sync_tests.py`'s 20 ids were never audited per test.** They are outside the 216 — a separate
registry, a private results layer, its own summary (`A-6`) — and `run/test-sync` is a documented
entry point covering the sync/drift/playlist suite T097–T116. That is roughly a tenth again of the
suite's id count, graded by nobody. The same is true of `test_task488_partb.py`'s 8 ids,
`test_tls_yield_reliability.py`'s 3 and `test_heatmap_reliability.py`'s 5: WP-A counted them and
placed them in the harness matrix; no package graded a body. Only WP-F went further, grading the
four standalone WebRadio harnesses as tests (§7), and it found the two best-engineered tests in the
entire review among them — which is a reason to expect the ungraded remainder to contain both good
and bad, not to assume either.

**Two firmware questions were adjudicated from source alone.** `H-4` refutes `A-8` as a live defect
because `APP_ORDER` gives the expected slots *today*; `G-1` and `F-4` trace clearing paths through
`init()`/`resume()`/`suspend()` by reading them. A firmware path missed in that reading changes the
finding, and in `G-1`'s case would change its blast radius from thirteen ids to none.

**The rubric's four values compress real differences.** WEAK spans "one term of a conjunction is
loose" and "the only oracle is a proxy two rungs from the subject"; 64 ids share that label. Where
a package had more to say it said it in prose (WP-F §6.1's ranking of oracles by distance from the
audible behaviour is the best example), but the register carries the four-value verdict, and a
reader who needs the gradation must go to the package.

**Test *absence* was surveyed for three apps only.** WP-H §5 enumerated the untested surfaces of
Clock, Teletext and PlaneRadar — the Clock tap-cycle feature is entirely outside the registry, four
of Teletext's seven `dbgGet` keys have no reader anywhere, M-PR-LOCATIONS coverage lives entirely
in four standalone smoke scripts. No equivalent survey exists for Spotify, WebRadio, Stock,
LocalPlayer, Settings or the shell. **This review counted the quality of what is tested; it did not
count what is not tested**, except in those three apps, and the three it did count were the ones
that turned out to have the largest holes.

**Cross-feature coverage was not examined.** `cross_feature_matrix.yaml`'s interactions and their
`test_coverage` claims are untouched here, and TASK-510 already records that three of fifteen swept
rows claimed coverage that did not exist. That is the same class of defect as `H-2` at a different
altitude, and it is unaudited.

**One observation window was contaminated by this review itself.** WP-A imported six modules that
open the serial port and run their suite at import time (`A-12`), resetting the board and injecting
taps at ~18:50 on 2026-09-02. It is disclosed in WP-A §0, it is why rubric §5 now bans the import,
and any TASK-557 measurement from that evening should be treated as suspect.
