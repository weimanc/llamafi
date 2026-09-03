# M-TESTQUAL WP-C — the gating classes: RIG, HEALTH and CORE, audited per test

> Owner: **Verification Engineer**
> Status: **done** — 20 findings (P1×6, P2×9, P3×5)
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Prior packages: [WP-A harness](M-TESTQUAL-A-harness-review.md), [WP-B taxonomy](M-TESTQUAL-B-taxonomy-review.md)

---

## 0. Scope, and how the corpus was measured

The 49 ids whose class is `RIG`, `HEALTH` or `CORE` — the classes that, once
TASK-566's `--class-order` switch is flipped, decide whether the other 167 ids
produce a verdict at all (`_gate.py:102-135`, `_order.py:49`).

```sh
cd app/tools && python3 -c "import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
m=build_all_meta()
for t,v in m.items():
    if v['cls'] in ('RIG','HEALTH','CORE'): print(v['cls'], t, v['scope'], v['module'])"
# -> 3 RIG + 3 HEALTH + 43 CORE = 49
```

All 46 non-HEALTH bodies live in one module, `suite/serialdbg/shell.py`; the three
HEALTH bodies live in `suite/serialdbg/health.py`. The machinery audited alongside
them: `health.py`, `_gate.py`, `_order.py`, `_triage.py`, `lib/results.py`.

Static audit only, per rubric §5: no flash, no `run/test*`, no `run/dut-health`,
no serial port; the board is pinned to the `-DBOD_WATCH` debug build for TASK-557.
Nothing under `app/tools/` was imported except the permitted
`suite.serialdbg.build_all_meta`.

WP-B established that **`cls` is declared on 6 of 216 records and `CORE` is never
declared at all** (B-15) — all 43 CORE ids are applications of `_meta.py`'s default.
This package is the first read of what those 43 bodies actually assert.

---

## 1. RIG — 3 ids

Per rubric A2 the body location is column one; ids are never a bare first cell.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:566` | T093 | Unhealthy (greyed) titlebar overlay appears on backoff and clears after `reconnect`. | **None device-observed.** Two `input()` prompts; the only machine check is that `set backoff 5` returned `ok`. | **HOLLOW** | S4, S7, S1 | `shell.py:572-574` is the whole machine assertion; `:577`, `:586` are `input()`; `:580-581`, `:589-590` convert an answer that is not `"y"` into the fail. Nothing reads a device field after `reconnect` (`:582`). |
| `shell.py:597` | T094 | A *physical* tap on the Winamp logo triggers a TLS reset; a second tap inside the 2 s cooldown is a no-op. | Half real: a `hard reset`/`stopping client` serial line within 4 s of the operator's Enter (`:615`). The cooldown half is an operator `y/n`. | **WEAK** | S4, S7, S9 | Marker verified present: `spotifyTaskStorage.cpp:363` `LOG_I("spotify.tls", "hard reset — stopping client")`, rendered `[I][spotify.tls] …` (`logSink.h:125`). The 4 s window starts at `input()` return (`:608-612`), not at the tap — a slow operator fails a working board. `:627-631` is the cooldown oracle and it is a human. |
| `shell.py:638` | T095 | Serial injection and physical touch produce the same region+action in each of three zones — the injection-vs-physical calibration the whole tap corpus rests on. | Real for the serial half (`hit`/`action` vs an expected pair, `:669`) and for the physical half (`dequeued action=<X>` seen within 5 s, `:694-699`); a third operator `y/n` per zone gates on Spotify's audible effect. | **WEAK** | S4, S7, S9, S10 | Markers verified: `spotifyTaskStorage.cpp:420` `dequeued action=%s`. `:677-681` drains the injection's own dequeue line with a bare `break`-or-expire loop, so an unseen drain silently leaves the injection's line in the buffer to be mis-read as the physical one at `:696`. The 4 s/5 s windows have no cited origin. |

### 1.1 The RIG class never executes, and `_gate`'s RIG rule is a different mechanism

Two separate defects, both structural:

* All three ids are removed from the default selection unconditionally
  (`runner.py:231-232`), and **no `run/` script passes `--interactive`**
  (`grep -rn interactive run/` → no output). Without the flag each body takes its
  `skip()` branch (`:569`, `:600`, `:641`). So the class the hierarchy places
  *beneath* HEALTH — "is the rig itself fit" — has **zero executable coverage in
  every entry point the project ships**, and T095, the calibration that licenses
  every injected `tap` in the other 210 ids, has not been runnable by any script
  since it was written.
* `_gate.py:6` documents `RIG -> _setup_fail() in runner.py: exit 3`. Neither
  T093/T094/T095 nor `_gate.run_suite` ever calls `_setup_fail`
  (`runner.py:194`); the real exit-3 path is `SetupFailure` raised out of
  `lib/dut.Dut.__init__` (`runner.py:340-344`), which has no connection to these
  three ids. The registry's RIG class and `_gate`'s RIG rule share a name and
  nothing else.

---

## 2. HEALTH — 3 ids

These three are the entire content of `run/dut-health` exit 0. Extra standard
applied per the brief: what does a *degraded but not dead* board do to each check?

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `health.py:75` | T_DH_01 | "The shell answers **correct** data, not merely answers" — `info`, `get variant`, `get playerMode` reply with non-null fields. | `info.elf` matches `^[0-9a-f]{8}$`; `info.build` truthy; `info.heap > 0`; `variant.spotify ∈ {on,off}`; `playerMode.name ∈ {Spotify,WebRadio,Player}` and `val ∈ {0,1,2}`. | **WEAK** | S8, S11 | Every `info` field checked is a value the firmware **cannot get wrong**: `elf` is 8 hex chars formatted from a fixed 4-byte prefix (`cmdMisc.cpp:34-37`), `build` is `__DATE__ " " __TIME__` (`:49`) and can never be empty, `heap` is `ESP.getFreeHeap()` and is >0 on any board that answered at all (`:50`). `variant.spotify` is a compile-time `"on"`/`"off"` literal (`cmdGet.cpp:41-47`) so it cannot fall outside the set. What the test really detects is a **truncated or desynchronised reply** — which is exactly the `variant spotify=None` case its docstring cites, and is real — not "incorrect data". `_PLAYER_MODES` (`health.py:68`) mirrors `kPmNames` (`cmdSet.cpp:699` / `cmdGet.cpp:621`) by hand; the docstring's provenance cite is wrong, already filed as WP-A **A-10**. |
| `health.py:168` | T_DH_02 | "The device's own view of the network is coherent" — TASK-426's dead-SSID wedge signature is caught. | `get ip` not in `("", "0.0.0.0", "(IP unset)")`; `[wifiCfg] err == 0`; `wifiCfg.ssid` non-empty. | **WEAK** | S7, S8 | Oracles verified against firmware: `cmdGet.cpp:199-215` emits the bare `[wifiCfg] err=… ssid="…" pwlen=… bssid_set=…` line the regex at `health.py:131-132` parses, and `cmdGet.cpp:255-260` emits `ip`. The check is real for the wedge it names. But **the SSID is never compared against anything** — any non-empty SSID with any non-zero IP passes, so a board associated to a neighbouring AP, a guest network, or a router with no upstream route is certified. No packet leaves the board in this test: association is asserted, reachability is not. `health.py:178-182` SKIPs the whole check under `--no-wifi`, and §2.2 below shows a SKIP here is reported as `[health] PASS`. |
| `health.py:256` | T_DH_03 | "App switching is alive": switch to a neighbour and back, `appId` correct at each step, `get idle` returns idle. | `get appId.name` equals the requested app after `switchApp <n>` (`health.py:229-235`), then `get idle.idle` truthy within 10 s (`:238-251`), both ways. | **SOUND** | — | The strongest of the three. `switchApp` is verified (`cmdMisc.cpp:22-27`), `get appId` names the app from the generated `appRegistry.h` table (`cmdGet.cpp:225-236`), and `get idle` is a genuine three-term quiescence verdict — `!shell::state().busy && !appOp && !dataq` (`cmdGet.cpp:283-300`). The index sent is `APP_ORDER.index(name)` from generated `app_ids_gen.py:4`, which is the enum order, so no mirror. Entry app restored on the pass path and on the idle-fail path (`:291`), though **not** on the "switch back did not take" path (`:293-297`), which is honest — it has nothing left to try. |

### 2.1 What a degraded-but-not-dead board does to each check

| Degradation | T_DH_01 | T_DH_02 | T_DH_03 | Caught? |
|---|---|---|---|---|
| Wrong/neighbouring WiFi, no route to the internet | passes | **passes** — ssid non-empty, ip non-zero | passes | **No.** |
| DNS resolvable but every fetch failing | passes | passes | passes (Clock does no fetch — `health.py:280` picks it deliberately) | **No.** |
| dataTask wedged with a fetch permanently in flight | passes | passes | **fails** — `get idle`'s `dataq` term (`cmdGet.cpp:287-289`) never clears | Yes, by side effect. |
| dataTask that silently never dispatches | passes | passes | passes | **No.** |
| Half-flashed / wiped SPIFFS (no `cal.json`, no `settings.json`) | passes | passes | passes | **No.** Nothing in the HEALTH class reads the filesystem. |
| Broken touch-injection dispatch (`cmdTap`) | passes | passes | passes — `switchApp`, not a tap, by deliberate design (`health.py:16-22`) | **No, by construction.** The whole tap corpus then fails as firmware failures. |
| Brownout-prone supply (TASK-557) | passes | passes | passes | **No.** Nothing samples supply; and the port open resets the board, so the boot measured is the freshest and least-loaded one. |
| Board on a stale/expired Spotify token (TASK-243) | passes | passes | passes | **No** — correct: `variant`/`playerMode` are configuration, not session state. |

### 2.2 A SKIPped health check is announced as `[health] PASS`

`_gate.health_phase` computes `failed` from `run_health`, which returns only ids
whose record `startswith("FAIL")` (`health.py:349`). A `SKIP` is not a FAIL, so
`failed` is empty and the code takes the success branch (`_gate.py:66-78`), which
pops only the `PASS` rows (`:72-73`, leaving the SKIP row behind) and emits:

> `[health] PASS — the board answers correct data, knows which network it is on, and can switch apps. It is fit to test.`

T_DH_02 SKIPs under `--no-wifi` (`health.py:178-182`). Under that flag the banner
asserts the board "knows which network it is on" on the strength of a check that
did not run. `_triage.health_verdict` gets this right — it returns
`degraded(T_DH_02)` for any non-`PASS` row (`_triage.py:81-83`) — so the premise
line and the banner disagree in the same run's output.

### 2.3 `run/dut-health`'s premise line reports `switch=unavailable(no-HEALTH-class;TASK-565)`

`all_meta` is built at `runner.py:322-331`, i.e. **after** the `--order-diff`
early exit and before the port opens, so it is a populated dict by the time
`_triage.health_verdict(all_meta)` runs at `:390` — that path is fine. But
`--dut-health` reaches `:381` with `health_selected` set and `_gate_on` false,
prints the *pre-run* premise with `switch="pending"`, runs the checks at `:389`,
prints the post-run premise at `:391` — and then the **exit-0 banner at `:401-403`
is emitted unconditionally**, with no reference to the verdict at all beyond
`if health_failed`. Combined with §2.2, `run/dut-health` prints
"PASS — … knows which network it is on …" on any run where T_DH_02 skipped.

---

## 3. CORE — 43 ids

All 43 live in `suite/serialdbg/shell.py`. Rows are in registry order
(`shell.py:3399-3511`).

### 3.1 Console / shell primitives — T079, T080, T083, T084, T091, T092, T133

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:112` | T079 | The touch cooldown gate blocks a rapid follow-up tap, and clearing it re-admits taps. | `tap`'s `skipped` field true while `set cooldown 500` is armed, then `skipped` false **and** `hit == "TRANSPORT"` after `set cooldown 0`. | **SOUND** | S5, S14 | `:126-131` and `:136-138` are both real device-observed comparisons on two different gate states. Weaknesses: `_wait_shell_not_busy`'s return is discarded at `:119` and `:135`, so a board whose `shellBusy` never clears produces a misleading tap failure rather than a named precondition failure; the test fires two PLAY transport actions and does not restore playback state. |
| `shell.py:145` | T080 | `info` returns the full documented field set and a plausible heap. | Nine required keys present in the reply; `heap >= 50_000`. | **SOUND** | S10 | `:148-153` checked against `cmdMisc.cpp:39-43`, which emits exactly those keys — a dropped field is caught. `50_000` at `:155` has no cited origin (no firmware constant, no measurement) — WP-A **A-11**/§5 magic-value class. |
| `shell.py:225` | T083 | `help` is one parseable JSON line naming the required command registry. | Seven required command names present in `r["commands"]`. | **SOUND** | — | `:229-234`; `console.cpp:91` shows the registry these names come from. A command deleted from the registry fails this. |
| `shell.py:245` | T084 | `set backoff` / `get backoff` round-trip is consistent (5 → 0). | `consecutiveFailures == 5` after `set backoff 5`, `== 0` after `set backoff 0`. | **WEAK** | S3, S5 | Rubric S3 exactly: it writes a debug field and reads the same field back through the paired debug accessor (`cmdSet.cpp`/`cmdGet.cpp`), so nothing but the accessor pair is under test. Worse for gating: **all four** failure paths call `flake()` (`:250, 256, 261, 265`) and `T084` is **not declared** in `docs/verification/flaky.yaml` (only `T087`, `T091` and the WebRadio ids are), so every failure becomes `FAIL: UNDECLARED flake …` (`lib/results.py:186-191`) — an honest FAIL, but with a message about bookkeeping rather than about the shell. |
| `shell.py:509` | T091 | `reconnect` clears `consecutiveFailures`. | `consecutiveFailures == 0` after `reconnect`, having been forced to 3. | **WEAK** | S5, S9 | The assertion is real and crosses a code path the test did not write (`reconnect` → poll → counter reset). But **every** exit is `flake()` (`:514, 517, 520, 526`) and T091 **is** declared (`flaky.yaml:51-70`, `review_by 2026-09-26`), so a genuine regression that passes on the mandated retry is recorded `FLAKY-PASS` — which is neither a PASS nor a `FAIL` (`lib/results.py:227`). Under `--class-order`, `_gate.py:128-129` blocks only on `RESULTS[tid].startswith("FAIL")`, so **T091 can never block anything**: it is a CORE id with the gating power switched off by its own flake declaration. `time.sleep(2.0)` at `:522` is the synchronisation. |
| `shell.py:538` | T092 | `reconnect` triggers a force poll within 2000 ms. | A `[spotify.poll] GET` / `ok` / `204` line seen on the wire, and the elapsed time since `send("reconnect")`. | **WEAK** | S8, S10, S5 | Markers verified present: `spotifyTaskStorage.cpp:253, 273, 280` under `logsink::logLine` which renders `[D][spotify.poll] …` (`logSink.h:125`), so the literal substrings at `:554` match. But the 2 s deadline is started at `:551`, i.e. **after** a JSON-drain loop that may consume up to 1 s (`:545-549`), so the window the test tolerates is up to ~3 s while the assertion text says 2000 ms; and a timeout falls to `flake()` at `:561` with T092 undeclared → an `UNDECLARED flake` FAIL. Latent: the whole oracle is a `LOG_D` line, which `logsink::logLine`'s runtime level gate (`logSink.h:119-123`) can suppress if any earlier test lowered the log level. |
| `shell.py:725` | T133 | The `CurrentlyPlaying` zero-init guard is present and there is no crash regression. | Part A: the literal string `CurrentlyPlaying current = {}` is present in a **host source file**. Part B: no `Guru Meditation Error` line in 90 s. | **WEAK** | S8, S13 | Part A (`:730-736`) is a real regression detector but it is a host-side `grep`, not device-observed state — it belongs in `app/tools/gate/`, which is WP-B **B-2**'s finding. Part B (`:741-751`) is vacuous with respect to the claim: an idle 90 s window contains no `Guru Meditation` on a board with or without the guard, so removing the guard is caught only by the grep. The 90 s is also the single most expensive cell in the CORE block and, as B-2 notes, a checkout without `lib/SpotifyArduino/` hard-FAILs it before touching the DUT. |

### 3.2 App-switch and boot-integrity — T147, T148, T_BI_01…04, T_X07_01

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:973` | T147 | A taskbar tap (via `injectTouch`) switches the active app; `get appId` confirms the round-trip. | `appId.name == "Clock"` after tapping the Clock slot, then `== "Spotify"` after tapping back. | **SOUND** | S7, S9 | `:986` and `:999` are both real. Precondition failure (`Spotify` not active) is a `skip()` at `:978` — under the order switch that means a CORE id silently produces no verdict and blocks nothing (§4.1). `time.sleep(0.3)` at `:984` is the only synchronisation where `get idle` exists. Also a genuine bug in the failure path: `:990` uses double quotes inside an f-string (`f"...{APP_SLOT["Spotify"]}..."`), which is a **Python 3.12+ only** construct — on 3.11 this module fails to import at all. |
| `shell.py:1005` | T148 | With Clock active, a canvas tap routes through Clock's own handler: `hit=CLOCKAPP`, `action=CONSUMED`, never a Winamp zone name. | `r["hit"] == "CLOCKAPP"` and `r["action"] == "CONSUMED"` from the tap reply. | **SOUND** | S7, S9 | `:1030-1038`. This is the TASK-346 BUG-1 guard and it fails if Winamp zone routing leaks back. Precondition is a `skip()` (`:1016`); restore is unconditional and precedes the assertion (`:1026-1029`), which is the right order. |
| `shell.py:1045` | T_BI_01 | `lastPlaylistDraw` advances after a Spotify resume — `invalidatePlaylist()` + `tick()` fired. | Device timestamp `lastPlaylistDraw.ms` differs from the value read before the switch, within 2 s. | **SOUND** | S6, S7 | `:1064-1088`. Real, and asserts an effect rather than an ack. **S6 present but harmless**: `:1079` `r_poll.get("ms", t_before)` defaults to the value that fails the comparison, so a missing field reads as "did not advance" — the safe direction. Skips on an empty Spotify queue (`:1048-1050`), which under TASK-243's live 403 is the routine outcome. |
| `shell.py:1094` | T_BI_02 | A taskbar tap arriving while a PLAY press is pending is consumed by the shell, not by Winamp; `appId` becomes Clock. | `hit == "TASKBAR"` and `action == "APP_SWITCH"` on the tap reply, **and** `appId.name == "Clock"`. | **SOUND** | S7, S9 | `:1116-1124`. Two independent device-observed facts, restore before assert (`:1112-1115`). |
| `shell.py:1130` | T_BI_03 | `suspend()` resets drag state and `resume()` re-enables PLEDIT across Spotify→Clock→Spotify. | `dragState == "D_IDLE"` after the round-trip, and `scrollOffset >= 0`. | **WEAK** | S8, S6, S7 | `:1174-1183`. The `dragState` half is real. The `scrollOffset` half is a **vacuous bound**: `scrollOffset` is an `int` the firmware never renders negative (`winampDisplay.cpp` clamps), so `so < 0` cannot be violated by any realistic regression; `rs.get("val", -1)` (`:1180`) at least defaults to the failing value. The claimed "`resume()` re-enables PLEDIT" is never asserted at all — no PLEDIT interaction follows the switch back. |
| `shell.py:1189` | T_BI_04 | `cmdTap` delivers the Release phase; the response reports `TRANSPORT` + `PLAY`/`PAUSE`. | `hit == "TRANSPORT"`, `action ∈ {PLAY, PAUSE}` on the tap reply. | **WEAK** | S2, S13 | `:1200-1207`. This asserts the tap **reply**, not that a Release was delivered: the reply is synthesised by `cmdTap` from the hit-test, so a firmware that never delivers Release still returns `TRANSPORT`/`PLAY`. The claim in the docstring ("Release delivered") has no oracle; the assertion it does make duplicates T081's. |
| `shell.py:1585` | T_X07_01 | Rapid Weather→Crypto→Weather→Crypto→Spotify switching leaves the DUT stable; no dataTask queue corruption. | `appId.name` equals the expected app at each of five steps, then `info` returns `ok`. | **WEAK** | S8, S9 | `:1603-1614`. The app-switch half is real. "No dataTask queue corruption" (`:1618`) has **no oracle** — `get dataq` is never read, and `info` answering is a liveness check any non-crashed board passes. Five fixed `sleep(0.2)`s (`:1602`) rather than `get idle`. |

### 3.3 Busy indicator and cooldown gates — T-BUSY-01, 01b, 02, 03, 05; T-CDWN-01, 02, 03

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:1657` | T-BUSY-01 | Stock row tap raises `shellBusy`, and it auto-clears when the chart fetch completes. | Only the **clear** half: `get shellBusy.busy` is false after `chartLen > 0`. | **WEAK** | S8, S1, S7 | `:1675-1680` explicitly downgrades the "busy went true" half to a printed note ("test gap; continuing") — so the raise is never asserted and `busy_seen` reaches the pass detail at `:1699` as decoration. What remains is `busy == False` at rest, which is the resting state of the flag; the assertion cannot distinguish "auto-clear fired" from "busy never rose". The real gate is `_poll_chart_len_positive` (45 s live HTTPS to Yahoo, `:1683`), i.e. this CORE id's pass/fail is a network outcome — WP-B **B-1**. |
| `shell.py:1704` | T-BUSY-01b | A tab-range tap also raises `shellBusy`. | `_poll_shell_busy(dut, True, 5000)` — `busy` observed true within 5 s of the 5D tap. | **WEAK** | S7, S9 | `:1728`. The assertion is real and is the raise half T-BUSY-01 dropped. But the negative outcome is a `skip()` (`:1732`, "warm fetch too fast"), so a genuine regression where the tap raises nothing is indistinguishable from a fast fetch and reports green. Two more skips at `:1708` and `:1723`. Coordinates `137 36`, `184 7`, `10 7` are literals (`:1712, 1719, 1727`) — WP-A **A-9**. |
| `shell.py:1740` | T-BUSY-02 | A Spotify PLAY tap raises `shellBusy` and it clears within 3.5 s. | `busy` true within 500 ms **and** false within 3500 ms. | **SOUND** | S10 | `:1748-1756` — both edges asserted, both device-observed, both failures are `fail()` not `skip()`. The best of the busy family. 500/3500 ms have no cited origin. |
| `shell.py:1762` | T-BUSY-03 | Six passive apps do not raise `shellBusy` on a canvas tap. | `get shellBusy.busy` is false after a canvas tap in each of Clock/Weather/Crypto/Matrix/Life/Aquarium. | **SOUND** | S9, S10 | `:1788-1792`, accumulated across six apps into one `fail()` at `:1797`. Real negative assertion. Uses `APP_SLOT` correctly (`:1767`). `settle = 3.0/0.5` (`:1781`) is a fixed sleep where `get idle` exists, and `tap 137 120` is the same hardcoded canvas centre WP-B **B-12** counts four other copies of. |
| `shell.py:1804` | T-BUSY-05 | Switching app while busy clears the amber indicator — `shellBusy` false in all three polls after `switchApp`. | *Intended*: three consecutive `get shellBusy` reads all false. *Actual*: see evidence. | **BROKEN** | S1, S3 | The guard at `:1836` is **inverted**. `if any(b is not True for b in results):` — the failure it exists to catch is `results == [True, True, True]` (busy did **not** clear), for which `any(b is not True …)` is `False`, the whole check is skipped, and control falls straight through to `pass_()` at `:1841`. The test **passes precisely when the regression is present**. It fails correctly only on the mixed case (`[True, False, …]` → `bad` non-empty at `:1837-1839`). Four `skip()` exits above it (`:1808, 1822, 1827`) mean it usually never reaches the assertion at all. |
| `shell.py:1846` | T-CDWN-01 | VIS Phase-2 cooldown: tap 1 cycles `visMode`, tap 2 inside the 300 ms window is suppressed, tap 3 after the gate polls to 0 cycles again. | `visMode` before/after each of three taps, plus `get cooldown.remainingMs` read between them. | **SOUND** | S9, S7 | `:1871-1932` — three real state comparisons on a device-owned counter, with the window-miss case correctly retried rather than passed (`:1896-1901`) and a hard `fail()` after three misses (`:1936`). The most carefully built test in the CORE set. It still `skip()`s on a stuck `shellBusy` (`:1869, 1918`), and it deliberately leaves `visMode` advanced. |
| `shell.py:1942` | T-CDWN-02 | The `cmdTap` `g_shellBusy` gate drops a second canvas tap: `skipped:true`, and exactly one fetch resolves. | `tap2.skipped is true`, then `(fetchOkCount - baseline) + fetchErrCount == 1` within 60 s. | **SOUND** | S5, S7 | `:1973-2003`. Both halves are device-observed and the delta baseline is read in-test (`:1961`), which is why `_order.py:229-234` correctly dismisses it as an edge candidate. Costs: four `skip()` exits (`:1964, 1969, 1977`) and a `flake()` at `:1998` for an unresolved fetch — **undeclared**, so a 60 s network stall becomes an `UNDECLARED flake` FAIL that, under the switch, NOT-RUNs 167 ids (WP-B **B-1**). |
| `shell.py:2008` | T-CDWN-03 | A taskbar tap **bypasses** the `g_shellBusy` gate and switches the app while a fetch is in flight. | `appId.name == "Clock"` and `shellBusy is False` after the taskbar tap. | **WEAK** | S8, S9 | `:2031-2036`. The two assertions are real, but **the precondition the claim rests on is never established**: nothing between the row tap (`:2021`) and the taskbar tap (`:2024`) checks that `shellBusy` was actually true. If the fetch resolved first — the case T-BUSY-01b and T-BUSY-05 both explicitly skip for — the test passes without exercising the bypass at all. `set triggerFetch 1` (`:2020`) makes it likely, not certain. |

### 3.4 Taskbar scroll and tap feedback — T162…T166, T242, T_TBFB_01…05

All eleven enter through `_tb_precondition` (`_helpers.py:432-441`), whose two
failure modes are both `skip()`.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:2564` | T162 | A taskbar slot tap (rawDy magnitude below the 3 px dead zone) fires `switchApp` and leaves `tbScrollOffset` unchanged. | `appId.name == "Clock"` **and** `tbScrollOffset` equal to the pre-tap baseline. | **SOUND** | S7 | `:2576-2581`. Two device-observed values, one of them a genuine discrimination assertion (tap vs scroll). Baseline read in-test at `:2569`. |
| `shell.py:2586` | T163 | A 50 px / 10-step drag-up increments `tbScrollOffset` by 1 (mod N). | `tbScrollOffset == (baseline + 1) % _TB_N`. | **SOUND** | S10, S11 | `:2593-2597`. Correctly dismissed as an edge candidate (`_order.py:236`) because the baseline is read immediately before the drag. `50` px / `10` steps have no cited firmware origin; `_TB_N` is discussed in §3.4.1. |
| `shell.py:2603` | T164 | A 50 px drag-down decrements `tbScrollOffset` by 1, from a non-wrap start. | `tbScrollOffset == (baseline - 1) % _TB_N`, having set the start to 1. | **SOUND** | S10, S7 | `:2609-2619`. Establishes its own precondition (`_tb_set_offset(dut, 1)`), which is why `_order.py:237` dismisses it. |
| `shell.py:2625` | T165 | Wrap-around down: offset 0, drag-down → offset N-1. | `tbScrollOffset == _TB_N - 1`. | **SOUND** | S11 | `:2637-2639`. **Correction to the TASK-566 adjudication:** `_order.py:213-216` records T165 as `ORDER-SENSITIVE` because it "requires `tbScrollOffset==0` and SKIPs when a predecessor left it non-zero". That is not what the body does — `_tb_precondition` **drives** the offset to 0 (`_helpers.py:437`) and returns False if it cannot, so the `skip()` at `:2632` is unreachable in registry order. The adjudication overstates this cell's order-sensitivity. |
| `shell.py:2644` | T166 | Wrap-around up: offset N-1, drag-up → offset 0. | `tbScrollOffset == 0`. | **SOUND** | S11 | `:2649-2658`. Sets its own start. |
| `shell.py:2664` | T242 | WebRadio is never reachable from a taskbar slot, and a full scroll cycle does not crash the render (LL-085 regression). | Every offset 0…N reachable and `get appId` still answering (liveness), then `appId.name != "WebRadio"` after tapping the top slot at two offsets. | **WEAK** | S8, S13 | `:2676-2699`. The crash half is real (a reboot makes `_tb_set_offset`/`get appId` fail). The leak half samples **two** of eleven offsets (`:2692`) and asserts only `!= "WebRadio"` — it does not assert which app *was* selected, so a slot resolving to the wrong non-WebRadio app passes. `_restore_spotify` is called only on the pass path (`:2700`); every `fail()` above it leaves the board on an arbitrary app and a non-zero scroll offset. |
| `shell.py:2739` | T_TBFB_01 | On a taskbar tap: `tb-press` then `tb-commit` strictly before `[shell] entered`, and the switch lands on the tapped app. | Relative index order of three log markers in one captured drain, plus `appId.name == "Clock"`. | **SOUND** | S9 | `:2747-2762`. All three markers verified in firmware: `appShell.cpp:111` (`tb-press slot=%d`), `:138` (`tb-commit slot=%d`), `:212` (`entered %d  heap=…`, two spaces — the trailing-space guard at `:2749` is correct and necessary). Ordering assertions on captured lines, not sleeps. |
| `shell.py:2767` | T_TBFB_02 | A scroll drag produces `tb-press` then `tb-press-cancel`, **no** commit and **no** switch, and the offset still steps by 1. | Marker presence/absence/order, plus `tbScrollOffset == 1`. | **SOUND** | S10 | `:2780-2790`. The strongest row in this family: it asserts a negative (`i_commit >= 0 or i_enter >= 0` → fail) as well as the positive. `appShell.cpp:126` confirms `tb-press-cancel`. The `slot=2` expectation is derived by a hand comment (`110//40 = 2`) rather than from `TASKBAR_SLOT_H`. |
| `shell.py:2795` | T_TBFB_03 | With persisted mode WebRadio, a player-slot tap paints amber on the **tapped** slot (`tb-commit slot=0`) and resolves to WebRadio, with no reverse app→slot lookup crash. | `tb-commit slot=0` present, ordered before `entered <WebRadio>`, and `appId.name == "WebRadio"`. | **SOUND** | S6, S7 | `:2816-2823`. Real, and it restores `playerMode` in a `finally` (`:2813-2815`) — the only test in the CORE set that uses one. **S6, and this one is the dangerous direction**: `r_pm.get("val", 0)` at `:2814` defaults the restore target to `0` (Spotify), so if the entry `get playerMode` reply was lost the test silently rewrites the persisted mode instead of restoring it. |
| `shell.py:2828` | T_TBFB_04 | A taskbar gesture never arms the SpotifyApp canvas cooldown; a canvas gesture still does. | `get cooldown.remainingMs == 0` after the taskbar gesture, and `> 0` after the VIS canvas tap. | **SOUND** | S6, S10 | `:2852-2858`. Both directions asserted. `int(r.get("remainingMs", -1))` defaults to `-1`, which fails both checks — the safe direction. Note the family-wide desync hazard in §4.3: `get cooldown` and `get shellCooldown` return the *same* field name. |
| `shell.py:2863` | T_TBFB_05 | The shell-level `s_cooldownMs` reads 0 once decayed and (0, 300] ms immediately after an injected taskbar release. | `shellCooldown.remainingMs == 0` before, `tb-commit slot=1` present, `0 < remainingMs <= 300` after. | **SOUND** | S9, S10, S6 | `:2884-2893`. Three assertions, including the marker check that proves the release branch was actually reached — which is exactly what T-CDWN-03 omits. The `time.sleep(0.5)` decay wait at `:2875` and the `300` bound are uncited literals. |

#### 3.4.1 `_TB_N` is a coincidence, not a derivation

`_helpers.py:400` sets `_TB_N = APP_SLOT["WebRadio"]` with the comment "Must match
firmware `TASKBAR_APP_COUNT` (= `(int)AppId::WebRadio`)". The firmware constant is
`TASKBAR_APP_COUNT = (int)AppId::Settings + 1` (`shell/taskbar.h:45`). Both evaluate
to 11 **only because WebRadio happens to be the row immediately after Settings** in
`appRegistry.h`. Insert any non-taskbar app between them and the suite's N and the
firmware's N diverge silently, mis-scoring every wrap assertion in T165, T166, T242
and `_tb_set_offset`'s path arithmetic. Rubric S11; the fix is
`_TB_N = APP_SLOT["Settings"] + 1`, or a parsed `TASKBAR_APP_COUNT`, matching WP-A
**A-18**'s proposed mirror gate.

### 3.5 ADR-042 UART / bgPoll and the ADR-046 error signal — T-UART-01, T-BGPOLL-01…03, T-ERR-01, 02, 04, 05, 06, 07

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `shell.py:3143` | T-UART-01 | No JSON garbling during concurrent Core-0 HTTPClient activity — 20 rapid `get heap` commands all parse cleanly (ADR-042 E1). | *Intended*: each of 20 replies parses. *Actual*: none of them can fail to. | **BROKEN** | S5, S3, S8 | **The one mechanism that could observe garbling is swallowed by the shared reader.** `Dut.read_json` (`lib/dut.py:1086-1090`) catches `json.JSONDecodeError` and **continues reading** to the next well-formed line; `cmd()` returns that line with no check that its `cmd`/`var` matches the request (`:1122-1136`). So a garbled reply is discarded, the reply intended for command *i+1* is returned as command *i*'s, and every subsequent reply is off by one while still reporting `ok:true`. `errors` at `shell.py:3156-3163` can only be non-empty on a full 3 s timeout, i.e. on total loss — never on interleave, which is the entire subject. `ValueError` in that `except` clause is unreachable for the same reason (`JSONDecodeError` never escapes `read_json`). Additionally the "under Core-0 load" precondition is never verified: nothing checks `chartLen`/`shellBusy` between the row tap at `:3154` and the loop, so on a fast or failed fetch the 20 commands run against an idle board. |
| `shell.py:3173` | T-BGPOLL-01 | `set bgPoll 0` suspends self-polls; `get bgPoll` returns `enabled:0`. | `get bgPoll.enabled == 0`, then `shellBusy` sampled ten times over 5 s must never read true. | **WEAK** | S3, S8, S9 | `:3182-3198`. The `enabled == 0` half is S3 (write a debug flag, read the same flag). The behavioural half uses `shellBusy` as a **proxy** for "a poll fired", sampled every 500 ms (`:3191-3195`) — a poll that starts and finishes between samples is invisible, and any *other* source of busy produces a false red. The poll itself (`[D][spotify.poll] GET`, `spotifyTaskStorage.cpp:253`) is on the wire and is not read. |
| `shell.py:3204` | T-BGPOLL-02 | `reconnect` resets `bgPoll` to `enabled:1` (recovery invariant). | `get bgPoll.enabled == 1` after `reconnect`. | **SOUND** | S9, S14 | `:3215-3217`. The assertion crosses a real code path. WP-B **B-6**: if `reconnect` fails, the test leaves `bgPoll 0` for every id that follows — the regression it exists to catch also poisons its successors, and there is no `finally`. `time.sleep(1.0)` at `:3214`. |
| `shell.py:3223` | T-BGPOLL-03 | An `ACT_FORCE_POLL` tap completes its fetch while `bgPoll` is suspended, and the flag stays 0. | Only `get bgPoll.enabled == 0` after the tap. | **WEAK** | S2, S8 | `:3248-3251`. The "fetch completed" half of the claim has **no oracle**: `_wait_shell_not_busy(dut, 15.0)`'s return value is discarded (`:3246`), and the tap's own `hit`/`action` reply is never inspected (`:3243`) — so a tap that dispatched nothing at all yields the same PASS as one that force-polled. What is asserted (a flag the test itself wrote is still 0) would also hold if the tap were never sent. |
| `shell.py:3268` | T-ERR-01 | A 403 poll raises `activeError`; a recovered 200 clears it. | `activeError.{active, spotifyAuthError}` across three injected `lastHttp` values. | **SOUND** | S3 | `:3276-3286`. The injected key (`set lastHttp`) and the read key (`get activeError`) are **different**, so the derivation `lastHttp → authError() → hasError() → active` is genuinely under test — this is the good version of the injection pattern, unlike T084. |
| `shell.py:3292` | T-ERR-02 | The error is owned by the app: hidden while another app is active, restored on return. | `active` true / false / true across Spotify → Clock → Spotify, with `spotifyAuthError` staying true throughout. | **SOUND** | S11, S9 | `:3310-3312`. Four device-observed values, including the discriminating one (`away.spotifyAuthError is True` while `away.active is False`). `switchApp 1` / `switchApp 0` are **hardcoded slot numbers** (`:3302, 3305`) although `APP_SLOT` is imported in this module — the same S11 class as WP-A **A-8**. |
| `shell.py:3319` | T-ERR-04 | `connecting` (boot amber) is true before the first poll resolves and false after the first success. | `activeError.connecting` true then false across an injected `lastOkMs` 0 → 1. | **SOUND** | S14 | `:3333-3334`. Real derivation. WP-B **B-7**: `lastOkMs`, `backoff` and `lastHttp` are all written (`:3328, 3331`) and **none is restored**; under the order switch this cell moves from index ~206 to ~39, in front of 170 ids. |
| `shell.py:3341` | T-ERR-05 | A touch must not clear a 403 — `authError` is keyed on the last HTTP status, not on `s_consecutiveFailures`. | `spotifyAuthError` still true after `set backoff 0` (the exact call `resetBackoff()` makes). | **SOUND** | S14 | `:3356-3357`. A precise regression guard for a real past defect. Leaves `backoff 0` deliberately (WP-B **B-7**). |
| `shell.py:3363` | T-ERR-06 | Offline apps never report `connecting`. | `activeError.connecting is False` for Clock and for Matrix. | **SOUND** | S11, S9, S8 | `:3371-3374`. Real negative assertion, though a weak one — `connecting` defaults false, so this asserts that a default was not overwritten. Hardcoded `conn(1)` / `conn(4)` (`:3371-3372`) instead of `APP_SLOT`, and `switchApp`'s `ok` is never checked, so a failed switch reads the *previous* app's `connecting`. |
| `shell.py:3380` | T-ERR-07 | A network app's failed fetch turns the bar red and clears on success (Stock `hasError() = _s.fetchFailed`). | `activeError.active` true after `set fetchFailed 1`, false after `set fetchFailed 0`. | **SOUND** | S9, S3 | `:3391`. Different write key from read key, so the derivation is exercised. Two fixed 0.2 s sleeps (`:3386, 3388`) and no `ok` check on the `switchApp` at `:3385`. |

---

## 4. The machinery these run inside

### 4.1 `_gate.py` — the blocking logic, audited as code

**Can a class-N failure be reported as anything other than blocking? Yes, three ways.**

1. **As a SKIP.** The block fires only on `RESULTS.get(tid, "").startswith("FAIL")`
   (`_gate.py:128-129`). A `skip()` is not a FAIL, and **31 of the 43 CORE ids have
   at least one `skip()` exit** — 25 directly, 6 more via `_tb_precondition`
   (`_helpers.py:435, 438`). Measured with `ast` (no import), functions resolved
   through `shell.py:3399`'s `TESTS` map. Every one of those exits is a CORE
   precondition that did not hold, i.e. exactly the condition the class exists to
   stop the run on, and every one of them reads green and blocks nothing.
2. **As a FLAKY-PASS.** `T091` is declared in `flaky.yaml:51`, so any failure goes
   `flake()` → mandated retry → `FLAKY-PASS` on a green second attempt
   (`lib/results.py:227`). `FLAKY-PASS` does not start with `FAIL`, so a CORE id
   that failed once and passed once blocks nothing — while `_triage.health_verdict`
   correctly refuses to call the same outcome `ok` for a HEALTH id
   (`_triage.py:78-83`). The two layers disagree about what a flake means.
3. **As an exception, only for HEALTH.** `run_health` converts a raised exception
   into `fail()` (`health.py:345-348`), which is right. The CORE path relies on the
   runner's `_dispatch` doing the same (`runner.py:430-433`), which it does. No hole
   here — but note that a `SystemExit` or `KeyboardInterrupt` from a body escapes
   both handlers.

**Is the class order enforced or only sorted?** Only sorted, and that is honest:
`class_order()` is `sorted(ids, key=rank)`, stable (`_order.py:61-63`), documented
as such. What is *not* honest is what it sorts over. RIG ids are stripped from the
selection before `run_suite` ever sees them (`runner.py:232`), and HEALTH ids live
in a separate registry (`__init__.py`, `health.py:311`), so the "ascending classes"
sequence the switch produces begins at CORE. The `order_diff_report` class census
(`_order.py:275-278`) will therefore always print `RIG 0` — the empty-RIG line in
the TASK-566 baseline is not an artefact of the selection, it is structural.

**What if a HEALTH check raises?** `run_health` catches it as a FAIL (`health.py:347`)
and `health_phase` blocks (`_gate.py:79-87`), which is correct. But see §2.2: a
health check that **SKIPs** is treated as a pass and announced as one.

### 4.2 `lib/results.py` — the buckets

The four buckets are correctly separated and the exit-4 opt-in is right
(`:301-309`). Two observations for the record:

* `not_run()` records silently by design (`:168-174`). Combined with §4.1, a run
  where a CORE precondition skipped produces zero NOT-RUN rows and a green summary —
  the mitigation quoted at `:286-287` ("a shrinking NOT-RUN count is a gate; an
  invisible one is a fiction") does not apply to the failure mode that is actually
  common here, which is an invisible *SKIP* count.
* `print_results(exit_on_finish=False)` is called with `all_tests=None`
  (`_gate.py:149`), so rows print in insertion order — correct, and deliberately
  documented at `:143-148`.

### 4.3 A cross-cutting hazard the CORE set is unusually exposed to

`Dut.cmd()` sends a command and returns **the next parseable JSON line**, with no
correlation between request and reply (`lib/dut.py:1122-1136`), and `read_json`
silently discards any line that fails to parse (`:1086-1090`). Most oracles here
survive that by accident, because they read a distinctively-named field. Two do
not: `get cooldown` and `get shellCooldown` both answer with `remainingMs`, and
`T_TBFB_04`/`T_TBFB_05` are built on exactly that pair (`shell.py:2841, 2851, 2876,
2882`); `Dut.cmd` itself issues `get shellCooldown` before every `tap`/`drag`
(`lib/dut.py:1132-1134`). A one-reply desync between them is undetectable. This is
also the mechanism that makes **C-2** unfixable inside the test body.

---

## 5. Family findings

Severity per rubric §4.3: **P1** counted as coverage but provides none, **P2**
materially weaker than claimed, **P3** hygiene.

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **C-1** | **P1** | **`T-BUSY-05` passes precisely when the regression it guards is present.** The guard is inverted: `if any(b is not True for b in results):` — when all three post-switch `shellBusy` reads are `True` (the amber did **not** clear), the condition is `False`, the check is skipped entirely, and control falls through to `pass_()`. It fails only on the mixed case. | `shell.py:1836-1841`; the claim at `:1805` | `if any(b is not False for b in results): fail(...)`. Then re-run — this cell has been reporting green on an untested, possibly broken, path. |
| **C-2** | **P1** | **`T-UART-01` structurally cannot observe the thing it tests.** Its subject is JSON garbling under Core-0 load; the only detector is a `JSONDecodeError`, and the shared reader swallows it and returns the *next* well-formed line instead, silently shifting every subsequent reply by one while all 20 still report `ok:true`. `errors` can only fill on a total timeout. The `ValueError` in its `except` is unreachable. | `lib/dut.py:1086-1090`, `:1122-1136`; `shell.py:3156-3167` | Give `Dut` a `read_json_strict()` that raises on a malformed line, and have T-UART-01 assert on `var == "heap"` in each reply as well. Additionally assert the fetch is actually in flight (`chartLen`/`shellBusy`) before the loop, or the load precondition is fiction. |
| **C-3** | **P1** | **The RIG class has no executable coverage in any shipped entry point, and `_gate`'s RIG rule is an unrelated mechanism.** No `run/` script passes `--interactive`; all three ids are stripped from `default_tests` unconditionally. T095 — the injection-vs-physical calibration that licenses every `tap` in the other 210 ids — has never been runnable from a script. `_gate.py:6`'s "RIG → `_setup_fail()` → exit 3" describes `SetupFailure` out of `Dut.__init__`, which has nothing to do with T093/94/95. | `runner.py:231-232`, `:194`, `:340-344`; `grep -rn interactive run/` → empty; `shell.py:569, 600, 641`; `_gate.py:6` | Add `run/calibrate` wrapping `--interactive --tests T093,T094,T095` and record its last-run date as a rig artefact; and either rename the registry class or rename `_gate`'s rule so one name does not denote two mechanisms. |
| **C-4** | **P1** | **A SKIPped HEALTH check is announced as `[health] PASS`, with a sentence asserting the thing that was not checked.** `run_health` returns only `FAIL` ids; a SKIP leaves `failed` empty, so the success branch emits "the board answers correct data, **knows which network it is on**, and can switch apps". `T_DH_02` SKIPs under `--no-wifi`. `_triage.health_verdict` says `degraded(T_DH_02)` for the same run — the banner and the premise line contradict each other. | `health.py:349`, `:178-182`; `_gate.py:66-78`; `runner.py:401-403`; `_triage.py:78-83` | Make `health_phase` treat any non-`PASS` health row as not-established, and build the banner from `health_verdict()` rather than from a literal. |
| **C-5** | **P1** | **The CORE block almost never fires, because CORE preconditions fail as SKIPs.** 31 of 43 CORE ids have a `skip()` exit (25 direct, 6 through `_tb_precondition`). A skip is not a `FAIL`, so `_gate.py:128` does not set `blocked_by`, no id is marked NOT-RUN, and the summary is green. The class hierarchy's entire promise — "a class-N failure invalidates class N+1" — is delivered by a string prefix test that the common failure mode does not match. | measured with `ast` over `shell.py:3399`'s `TESTS` map (no import); `_gate.py:128-129`; `_helpers.py:435, 438`; `lib/results.py:152-154` | Introduce a distinct `blocked_precondition(tid, why)` result for a CORE id whose precondition did not hold, treat it as blocking, and convert the 31 sites. A CORE test that cannot run is not "not applicable" — it is an unestablished premise, which is what `NOT-RUN` was invented to say. |
| **C-6** | **P1** | **`T091`'s gating power is switched off by its own flake declaration.** Every exit path is `flake()`, T091 is declared, and a declared flake that passes on the mandated retry becomes `FLAKY-PASS` — which is neither a PASS nor a `FAIL`, so it can never set `blocked_by`. A CORE id in this state contributes no verdict in either direction. | `shell.py:514, 517, 520, 526`; `flaky.yaml:51-70`; `lib/results.py:227`; `_gate.py:128-129` | Either declare CORE ineligible for flake declarations (a flaky premise is not a premise), or make `_gate` block on `FLAKY-PASS` for CORE. Decide before the switch flips. |
| **C-7** | **P2** | **Three CORE ids route failures through an *undeclared* `flake()`**, so every failure surfaces as `FAIL: UNDECLARED flake — no entry for … in flaky.yaml`. The message is about bookkeeping; the reader has to dig for the real symptom. Under the switch, a 60 s network stall in `T-CDWN-02` NOT-RUNs 167 ids with that text as the stated cause. | `shell.py:250, 256, 261, 265` (T084), `:559, 561` (T092), `:1998` (T-CDWN-02); `flaky.yaml` contains none of the three; `lib/results.py:186-191` | Either declare them with owner/task/review_by, or replace the network-condition `flake()` calls with an explicit precondition result (see C-5). |
| **C-8** | **P2** | **`T_DH_01` does not check that the shell answers *correct* data — it checks that it answered without truncation.** Every field it validates is a compile-time or trivially-nonzero constant (`elf` from a fixed sha prefix, `build` from `__DATE__`/`__TIME__`, `heap` from `getFreeHeap()`, `variant.spotify` from an `#ifdef`). The one thing that can genuinely vary — `playerMode` — can only read outside the set on corrupt settings. | `health.py:93-119` vs `cmdMisc.cpp:34-50`, `cmdGet.cpp:41-47`, `:620-627` | Keep it (reply-integrity is worth gating on) but rewrite the claim to say so, and add one field whose value can actually be wrong — e.g. assert `info.elf` matches the ELF the host just built, which turns it into a "right firmware on the board" check. |
| **C-9** | **P2** | **`T_DH_02` never compares the SSID against anything.** Any non-empty SSID plus any non-zero IP passes, so a board joined to a neighbour's AP, a guest VLAN, or a router with no upstream route is certified as "knows which network it is on". | `health.py:201-213`; the banner text at `_gate.py:75-76` and `runner.py:401-402` | Compare `cfg["ssid"]` against an expected value from `app/data/wifi_creds.json` (or a `DUT_SSID` env), and add one reachability probe — the device already answers `get ip`; a `get dataq`-observable fetch or a firmware ping getter would close it. |
| **C-10** | **P2** | **No HEALTH check performs any I/O off the board, reads the filesystem, exercises the tap path, or samples supply** — so a board with a wiped SPIFFS, a broken `cmdTap` dispatch, a silently-non-dispatching dataTask, or TASK-557's supply sag passes all three checks and is certified fit. The tap exclusion is deliberate and correctly argued (`health.py:16-22`); the consequence — that the entire tap corpus's failures are then attributed to firmware — is not recorded anywhere. | §2.1's table; `health.py:16-22` | Record the exclusions explicitly in the HEALTH module header as "what a green gate does **not** cover", and reconsider the deferred `T_DH_04` in that light: the gap is not heap, it is filesystem + input path. |
| **C-11** | **P2** | **Two CORE ids never establish the precondition their claim rests on.** `T-CDWN-03` asserts a taskbar tap bypasses the busy gate without ever checking `shellBusy` was true when the tap arrived; `T-BGPOLL-03` asserts a force-poll "completed" while discarding `_wait_shell_not_busy`'s return and never inspecting the tap reply — the only thing it asserts is that a flag it wrote itself is unchanged. | `shell.py:2021-2036`; `:3243-3251` | `T-CDWN-03`: insert `_poll_shell_busy(dut, True, …)` between the row tap and the taskbar tap and fail (not skip) if it does not rise. `T-BGPOLL-03`: assert the tap reply's `action == "FORCE_POLL"` and gate on `_wait_shell_not_busy`'s return. |
| **C-12** | **P2** | **`T_TBFB_03`'s restore has a defaulting oracle in the dangerous direction.** `dut.cmd(f"set playerMode {r_pm.get('val', 0)}")` — if the entry `get playerMode` reply was lost, the `finally` writes `playerMode 0`, silently *rewriting* persisted state instead of restoring it. `playerMode` is persisted to SPIFFS, so this survives the run. | `shell.py:2802`, `:2814` | Read the entry mode into a variable, `skip()` if it is absent, and restore only a value that was actually observed. |
| **C-13** | **P2** | **`_TB_N` equals `TASKBAR_APP_COUNT` by coincidence.** The suite computes `APP_SLOT["WebRadio"]`; the firmware computes `(int)AppId::Settings + 1`. Equal only because WebRadio follows Settings in `appRegistry.h`. Any non-taskbar app inserted between them silently mis-scores T165, T166, T242 and `_tb_set_offset`'s shortest-path arithmetic. | `_helpers.py:396-400` vs `app/src/shell/taskbar.h:45` | `_TB_N = APP_SLOT["Settings"] + 1`, or parse `TASKBAR_APP_COUNT` — and seed WP-A **A-18**'s mirror gate with the pair. |
| **C-14** | **P2** | **`T133` proves its claim with a host-side `grep` and pads it with a 90 s vacuous soak.** Removing the zero-init guard is caught only by the source match; the runtime half ("no `Guru Meditation` in 90 s") is satisfied by any idle board with or without the guard, and it is the single most expensive cell in the CORE block. Confirms WP-B **B-2** from the body side. | `shell.py:730-736` (part A), `:741-752` (part B) | Move part A to `app/tools/gate/` as a source check; delete part B or replace it with an assertion that ≥12 polls actually occurred (`consecutiveFailures`/`lastOkMs` deltas), which is what the docstring claims it counts. |
| **C-15** | **P2** | **`T242` samples 2 of 11 taskbar offsets and asserts only "not WebRadio".** A slot resolving to the *wrong non-WebRadio* app passes. Its restore is on the pass path only, so every `fail()` leaves the board on an arbitrary app with a non-zero scroll offset for whatever runs next. | `shell.py:2692-2701` | Assert the *expected* app name at each sampled offset (derivable from `APP_ORDER` and the offset), iterate all offsets — the loop above already does — and move `_restore_spotify` into a `finally`. |
| **C-16** | **P3** | **Hardcoded app slot numbers in `T-ERR-02` and `T-ERR-06`** (`switchApp 1`, `switchApp 0`, `conn(1)`, `conn(4)`) although `APP_SLOT` is imported at the top of the same module. Same S11 class as WP-A **A-8**'s `clock.py` finding, in a module that otherwise uses `APP_SLOT` correctly. Neither checks the switch's `ok`, so a failed switch reads the previous app's state. | `shell.py:3302, 3305, 3371, 3372`; `shell.py:43` | Replace with `APP_SLOT[...]` and check `ok`. Mechanical. |
| **C-17** | **P3** | **`shell.py` silently requires Python ≥ 3.12.** `f"tap {…APP_SLOT["Spotify"]…}"` nests same-type quotes inside an f-string (PEP 701), which is a `SyntaxError` on 3.11 — the whole module, and therefore the whole suite, fails to import. Nothing declares a minimum version. | `shell.py:990` | Use single quotes inside the f-string, and state the interpreter floor in `M-TOOLING` (both interpreters on this machine are ≥3.12, so this is latent, not live). |
| **C-18** | **P3** | **`get cooldown` and `get shellCooldown` return the same field name and `Dut.cmd` does not correlate replies**, so a one-reply desync between them is undetectable — and `Dut.cmd` itself issues `get shellCooldown` before every tap/drag. `T_TBFB_04` and `T_TBFB_05` are built entirely on that pair. | `lib/dut.py:1132-1136`; `shell.py:2841, 2851, 2876, 2882` | Have `Dut.cmd` verify `reply["var"] == <the requested var>` for `get`, raising on a mismatch. One change, and it also closes half of C-2. |
| **C-19** | **P3** | **`_order.py`'s `EDGE_ADJUDICATION` misdescribes `T165`.** It records "requires `tbScrollOffset==0` and SKIPs when a predecessor left it non-zero"; in fact `_tb_precondition` *drives* the offset to 0 and returns False if it cannot, making the cited `skip()` unreachable in registry order. The adjudication is a stated precondition of the order switch, so an inaccurate row in it matters. | `_order.py:213-216` vs `shell.py:2628-2633` and `_helpers.py:437-439` | Re-verdict `T165` as `DISMISSED` with the `_tb_precondition` cite, alongside `T163`/`T164`. |
| **C-20** | **P3** | **`T_BI_04`'s claimed subject has no oracle and its actual assertion duplicates `T081`'s.** "cmdTap delivers the Release phase" is unobservable in the tap reply, which `cmdTap` synthesises from the hit-test; what is left is `hit == TRANSPORT`, `action ∈ {PLAY,PAUSE}` — the same assertion `T081` makes five times. | `shell.py:1200-1207` vs `:169-176` | Either assert a Release-specific observable (a `[touch]` release marker, or `pendingReleaseAt` via a getter) or fold the id into `T081` and `resv` it. |

---

## 6. Counts

| Verdict | RIG | HEALTH | CORE | **Total** |
|---|---|---|---|---|
| SOUND | 0 | 1 | 28 | **29** |
| WEAK | 2 | 2 | 13 | **17** |
| HOLLOW | 1 | 0 | 0 | **1** |
| BROKEN | 0 | 0 | 2 | **2** |
| **total** | **3** | **3** | **43** | **49** |

* **HOLLOW:** `T093`.
* **BROKEN:** `T-BUSY-05`, `T-UART-01`.

Smell histogram (occurrences across the 49 rows; a row may carry several):

| Code | Smell | Count |
|---|---|---|
| S9 | Fixed-sleep synchronisation | 18 |
| S7 | Skip-as-pass | 16 |
| S8 | Vacuous bound | 11 |
| S10 | Magic value | 10 |
| S3 | Tautology | 6 |
| S5 | Swallowed failure | 6 |
| S11 | Double bookkeeping | 6 |
| S6 | Defaulting oracle | 4 |
| S14 | State leakage | 4 |
| S1 | Unconditional pass | 3 |
| S4 | Deferred to a human | 3 |
| S13 | Overlap | 3 |
| S2 | Ack-not-effect | 2 |
| S12 | Wrong-id / mis-scoped | 0 |

S6 is notable for being *rarer* and *safer* than WP-A's seven-defaults finding
predicted: of the four occurrences, three default to a value that **fails**
(`T_BI_01`'s `t_before`, `T_BI_03`'s `-1`, `T_TBFB_04`'s `-1`). Only `T_TBFB_03`'s
`r_pm.get('val', 0)` defaults in the dangerous direction (**C-12**).

---

## 7. NEEDS-DUT

Static reading cannot settle these. Each is stated as the question hardware would answer.

1. **`T-BUSY-05` (C-1) — how long has it been green on a broken path?** After the
   guard is corrected, does `shellBusy` actually clear on `switchApp` while a Stock
   fetch is in flight? The inverted guard means we have no evidence either way.
2. **`T-UART-01` (C-2) — does garbling actually occur?** With a strict reader in
   place, do any of the 20 `get heap` replies interleave during a live chart fetch?
   ADR-042 E1's claim has never been tested by this id.
3. **`T-CDWN-03` / `T-BGPOLL-03` (C-11) — is the precondition ever true in practice?**
   How often is `shellBusy` genuinely high when the taskbar tap lands? If it is rarely
   true, these two have been passing vacuously for their whole life.
4. **`T-BUSY-01`'s dropped raise half.** Is the `shellBusy` true window really shorter
   than the 500 ms poll granularity (`shell.py:1677`), or was that conclusion drawn
   from a board that never raised it? A `get idle`-based watch would settle it.
5. **`T092`'s window.** Measured force-poll latency after `reconnect`, to decide
   whether 2000 ms from `send()` (rather than from after the drain loop) is achievable.
6. **`T091` / `T084` / `T092` / `T-CDWN-02` flake rates** under the current TASK-243
   403, so C-6/C-7 can be settled by declaration or by fix rather than by argument.
7. **Whether the log-level gate (`logSink.h:119-123`) can suppress `[D][spotify.poll]`
   mid-suite.** If any test lowers `logMinLevel`, `T092`, `T094` and `T095` lose their
   oracles silently.

---

## 8. What a green `run/dut-health` actually proves

`run/dut-health` exit 0 prints:

> `[health] PASS — the board answers correct data, knows which network it is on, and can switch apps. It is fit to test.`
> — `runner.py:401-403`, and the same sentence at `_gate.py:75-77`.

**What the three checks actually establish, in plain English:**

> A board is attached to the named serial port; it accepted three `get` commands and
> answered each with a well-formed JSON line whose fields were present and within
> their compile-time possible ranges; its WiFi driver reports *some* SSID configured
> with no error and the stack has been handed *some* non-zero IP; and it can switch
> between two apps by console command and reach quiescence at each step, within 10 s.

**Where that differs from the claim, precisely — three gaps:**

1. **"answers correct data" → *answers, uncorrupted*.** Every field `T_DH_01`
   validates is a compile-time constant or a trivially non-zero runtime value
   (`elf`, `build`, `heap`, `variant.spotify`); none of them can carry a wrong value
   on a board that is running at all. The check's real and useful content is that the
   reply was not truncated or desynchronised — a narrower and different claim (C-8).
2. **"knows which network it is on" → *is associated with a network, name unchecked*.**
   The SSID is compared against nothing, and no packet leaves the board during the
   gate. A board on the wrong AP, on a guest VLAN, or behind a router with no upstream
   route passes (C-9). Worse: under `--no-wifi` the check does not run at all and the
   sentence is still printed verbatim (C-4).
3. **"It is fit to test" → *it is not obviously dead*.** The gate reads no filesystem,
   exercises no touch input, and samples no supply rail — so a wiped SPIFFS, a broken
   `cmdTap` dispatch, a dataTask that silently never dispatches, and TASK-557's supply
   sag all pass. The tap exclusion is a deliberate and correct class-precedence
   decision (`health.py:16-22`), but its consequence is that a board which cannot
   accept an injected tap is certified fit, and the ~150 tap-driven ids downstream
   then report their failures as firmware defects.

Only the third clause of the sentence — **"and can switch apps"** — is fully earned.
`T_DH_03` is the one SOUND check of the three.

---

## 9. Handover

* Machinery findings that belong to WP-Z's consolidation rather than to a family:
  **C-1 … C-6** (all P1) and **C-18**.
* Cross-references to prior packages: **C-2/C-18** extend WP-A **A-11**/§3.3;
  **C-7** is the body-level instance of WP-B **B-1**; **C-14** confirms **B-2**;
  **C-12/C-15** are new instances of **B-7**'s unrestored-state class; **C-13/C-16**
  extend **A-8**/**A-18**; **C-19** corrects a row in the TASK-566 adjudication that
  **B-4** already flagged as under-reporting.
* Nothing under `app/` or `run/` was modified. `./run/check-docs` was run once before
  handover; the C6 result is recorded in the ledger entry for this package.
