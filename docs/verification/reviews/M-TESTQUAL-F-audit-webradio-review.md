# M-TESTQUAL WP-F — the WebRadio family, audited per test

> Owner: **Verification Engineer**
> Status: in progress
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Prior packages: [WP-A harness](M-TESTQUAL-A-harness-review.md), [WP-B taxonomy](M-TESTQUAL-B-taxonomy-review.md), [WP-C gating classes](M-TESTQUAL-C-audit-core-review.md), [WP-D shell FEATURE](M-TESTQUAL-D-audit-shell-review.md), [WP-E player](M-TESTQUAL-E-audit-player-review.md)

---

## 0. Scope, and how the corpus was measured

Every id whose body lives in `app/tools/suite/serialdbg/webradio.py`.

```sh
cd app/tools && python3 -c "import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
m=build_all_meta()
for t,v in m.items():
    if v['module']=='webradio': print(t, v['cls'], v['scope'], v['effect'])"
# -> 30 ids. All cls=FEATURE, all scope=WebRadio, all effect=mutating.
```

**The index's §3 row says "31 ids". It is 30**, and the module's own `TESTS`
dict confirms it (`webradio.py:1551-1582`, 30 entries). §3's row is corrected in
this package's index edit; the rollup uses 30.

The taxonomy is 100 % module-seeded here — not one `@meta(...)` declaration
appears in the file, so every `(cls, scope, effect)` triple is `_meta.py`'s
inference. That matters twice below: `T_WR_VIS_03` and `T_WR_VIS_05` drive
**Spotify** end to end and are scoped `WebRadio` (**F-11**, the same defect
WP-E filed as **E-5**), and `T_PLE_WR_155`–`160` are PLEDIT/`PleditView` tests
whose oracle is the *shared* renderer rather than anything WebRadio-specific.

Static audit only, per rubric §5: no flash, no `run/test*`, no `run/wr-gate`, no
`run/wr-soak`, no `run/ae04`, no serial port. The board is pinned to the
`-DBOD_WATCH` debug build for TASK-557. `build_all_meta` was the only import made
under `app/tools/` (rubric §5 / amendment A1); `webradio.py`, `_helpers.py`,
`coords.py`, `_meta.py`, `_order.py`, `runner.py`, `lib/dut.py`,
`lib/results.py`, `screendump.py`, `test_adr045_gate.py`,
`test_webradio_soak.py`, `webradio_long_soak.py`, `test_ae04_teardown.py`,
`run/wr-gate`, `run/wr-soak`, `run/ae04`, `flaky.yaml`, `test_plan.md` and the
firmware under `app/src/` were **read**, never imported or executed.

Per amendment A2 the per-test tables put the **body location in column one** and
the id in column two, and no section is headed with a bare id.

### 0.1 What is distinctive about this corpus

1. **Nothing in the rig can hear.** There is no microphone, no loopback, no
   I2S tap. Every WebRadio test that claims "plays" is asserting a proxy, and
   §6 tabulates how far each proxy sits from the audible behaviour. The family
   splits sharply: the `wrPump`/`wrSpec` pair observe the decode path actually
   advancing and are the two strongest audio proxies in the whole suite; the
   `wrState == 2` majority observe a `uint8_t` that `set wrState` can write
   directly.
2. **This family has the most out-of-registry harnesses in the repo** —
   `run/wr-gate` → `test_adr045_gate.py`, `run/wr-soak` →
   `test_webradio_soak.py`, `webradio_long_soak.py` (no `run/` entry at
   all), and `run/ae04` → `test_ae04_teardown.py`, which carries `T_AE_04`, an id
   with **no registry entry** (WP-B **B-13**). §7 grades all four as tests. §8
   answers what the M-WEBRADIO close actually proved.
3. **Two different entry paths to the same app, one of them broken by design.**
   `_switch_to_webradio_capture_heap` (`webradio.py:346`) is correct and its
   docstring says why; `_switch_to(dut, "WebRadio")` (`_helpers.py:321`) taps a
   taskbar slot WebRadio does not have — the file's own comment at `:30-33` warns
   against it — and `_ensure_webradio` (`:298`) still calls it. **F-6**.
4. **The `bitrateCap` hazard is real but narrower than feared.** `set wrDeadUrls
   N` synthesises the list in RAM and never touches the cap or the network
   (`webRadioApp.cpp:1031-1055`), so the six PLEDIT ids plus `T237`/`T276` are
   cap-immune. The nine fetch-dependent ids are not — §6.2.

---

## 1. The PLEDIT velocity-scroll mirror — `T_PLE_WR_155`–`160` (6)

Registry order `webradio.py:1552-1557`. These are the realisation of `T_PLE_08`
(`test_plan.md:502`, `M-PLEDIT-ABSTRACTION-playlist-source.md:565`) and mirror
`T155`–`T160` one for one against `StationListSource` instead of Spotify's
queue. WP-D audited the Spotify originals (WEAK / SOUND / SOUND / WEAK / SOUND /
SOUND, `M-TESTQUAL-D-audit-shell-review.md:107-112`); this section says where the
WebRadio copies differ, and cites rather than re-derives the shared mechanics.

**Three facts decide most of these rows.**

**(a) All six oracles read the *shared* view, not a WebRadio-owned value.**
`get wrScroll` is `snprintf(... winampDisplay.pleditScrollOffset(),
winampDisplay.pleditDragMode(), winampDisplay.pleditScrollVelocity(),
winampDisplay.pleditScrollAccum() ...)` (`webRadioApp.cpp:754-767`), and
`_get_scroll`/`get scrollOffset` reads the same object through
`winampDisplay.dbgGet` (`winampDisplay.cpp:742`). So the docstring's claim that
`get wrScroll` is "WebRadio's own debug surface" (`webradio.py:120-122`) is
half-true — it is WebRadio's own *command*, serving winampDisplay's state. The
substantive difference from `T157`–`T159` is the **synchronisation** (`drag …
hold` + `release` instead of a serial-buffer interleave tuned to Spotify's
`loop()` cost), which is a genuine improvement and is the reason the first
attempt failed 3/6 (`M-PLEDIT-ABSTRACTION-playlist-source.md:565`).

**(b) The precondition is cap-immune and self-sufficient.**
`_vs_precondition_webradio` (`:35-64`) synthesises 15 stations with `set
wrDeadUrls 15`, which writes `_stations[]` directly in RAM and never touches the
network, the country filter or `bitrateCap` (`webRadioApp.cpp:1031-1055`). This
is the **only** block in the family immune to both TASK-284 mirror truncation and
the `bitrateCap=192` DUT setting (§6.2) — and it is why these six are the family's
most reliable rows.

**(c) The cooldown discriminator is real on this app too.**
`PleditView::release()` returns `cooldownMs = 300` on a dispatched tap, `150` on a
scroll-end and `100` on a strip drag (`pleditView.h:303,323,337`), and
`WinampDisplay::handleWinampInput`'s Release branch arms
`touchScreenCoolDownTime` from it unconditionally (`winampDisplay.cpp:357-360`) —
the same code path in both apps. `T_PLE_WR_156`'s `<= 220` boundary therefore
separates 300 from 150 here exactly as it does in `T156`.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `webradio.py:67` | T_PLE_WR_155 | A 0-dy tap inside the PLEDIT dead zone takes the **tap** branch, not the scroll-end branch, on WebRadio's station list. | Three device-observed values: `hit == "PLEDIT"`, `scrollOffset` unchanged across the tap, `dragState == "D_IDLE"` after. | **SOUND** | S2, S13, S14 | `:73-89`. Three independent terms and the middle one is the real discriminator — a gesture that took the scroll-end branch would have moved `scrollOffset` (`webRadioApp.cpp:754-757` reads the same counter the branch increments). Unlike its Spotify original it is **not** over-claimed: `T155`'s plan row promises `ACT_PLAY_URI` and never looks for it (WP-D `:107`), whereas this body's docstring claims only the hit, and the plan's `T_PLE_08` row claims only "WebRadio scroll suite green" (`M-PLEDIT-ABSTRACTION-playlist-source.md:233`). The gap is still there — `PleditView::release()` sets `tapDispatched` and calls the source's `onTap` (`pleditView.h:320-323`), so `get wrIdx`/`get wrState` would prove the station actually started and neither is read — but it is a gap in coverage, not a lie in the row. Leaves 15 synthetic dead stations and `_debugForceConnFail = true` installed (**F-4**). |
| `webradio.py:92` | T_PLE_WR_156 | A 13 px drag exceeds the 1 px dead zone, so Release takes the scroll-end branch and **suppresses** the tap. | `dragState == "D_IDLE"` and `cooldown.remainingMs <= 220`. | **SOUND** | S10, S13, S14 | `:105-115`, against `pleditView.h:303,323,337` and `winampDisplay.cpp:357-360` — 300 ms (tap) vs 150 ms (scroll-end) genuinely brackets the 220 boundary, so this is a real branch discriminator on a device-owned countdown rather than a proxy. `rc.get("remainingMs", 9999)` defaults to the **failing** value (`:110`) — the safe direction, same as `T156`. Two inherited costs, both cited not re-derived: the `220` literal is uncited (WP-D `:108`), and `get cooldown` / `get shellCooldown` return the same field name with `Dut.cmd` issuing `get shellCooldown` before every tap and drag, with nothing correlating request to reply — WP-C **C-18**. |
| `webradio.py:118` | T_PLE_WR_157 | Velocity scaling ≈ 2.0 rows/s: `tick 50 20` fired mid-gesture at dy = −13 advances the offset into `[1, 3]`. | `drag … hold` acked with `hold` true, `dragState == "D_PLEDIT_SCROLL"` mid-gesture, then `1 <= wrScroll.offset <= 3`. | **SOUND** | S10, S13, S14 | `:130-151`. The strongest row of the six and the one that fixed a real harness defect: it proves the gesture is live *before* trusting the tick's number (`:134-138`), and the `hold`/`release` construction replaces the iteration-count-tuned interleave that produced three false failures under WebRadio's different `loop()` cost — root-caused, re-probed manually (vel ≈ 2.0004 rows/s) and rewritten rather than retried, `M-PLEDIT-ABSTRACTION-playlist-source.md:565`. `so = r_ws.get("offset", -1)` defaults to a failing value. It also `release`s on all three failure paths (`:137`, `:142`), which its Spotify original does not need but which matters here because a held drag would poison the next id. The `[1,3]` band is derived from `SCROLL_SPEED_K_DEFAULT` per `test_plan.md:1525` but written as a literal. |
| `webradio.py:154` | T_PLE_WR_158 | "Tick integration: 1 s at dy = −13 advances `wrScroll.offset` ≥ 1." | `wrScroll.offset >= 1`. | **WEAK** | S13, S8, S14 | `:161-182`. Identical precondition, identical `hold`/`tick 50 20`/`release` sequence and identical oracle field to `T_PLE_WR_157`, with a strictly weaker bound: every regression this can detect, its predecessor detects first and more precisely, and this one adds nothing the pair does not already have. Exactly WP-D **D-13** on the WebRadio side, and the cost is higher here — each precondition run re-issues `set wrDeadUrls 15` plus five reset drags (`:44-58`). Its one distinct property is that `so < 1` fails while `T_PLE_WR_157` fails on `so > 3` too, i.e. it cannot catch an over-fast scroll. |
| `webradio.py:185` | T_PLE_WR_159 | `scrollAccum` is non-zero while the gesture is live and is reset to `0.0000` on Release. | `accum != 0.0` mid-drag, `accum == 0.0` after `release`, and `dragState` `D_PLEDIT_SCROLL` → `D_IDLE` around it. | **SOUND** | S13, S14 | `:192-224`. Four device-observed values including the hard-to-fake one — a float read from *inside* a live gesture, which the `hold` construction makes deterministic here where the Spotify original needs a serial interleave. Both defaults are in the safe direction: `get("accum", 0.0)` (`:207`) fails the non-zero check, `get("accum", -1.0)` (`:214`) fails the zero check. Field verified live: `webRadioApp.cpp:764` → `winampDisplay.pleditScrollAccum()`. |
| `webradio.py:227` | T_PLE_WR_160 | `tickScroll` is a no-op while `dragState` is `D_IDLE` — the guard clause fires. | `scrollOffset` unchanged across a `tick 50 20` **and** `scrollVelocity == 0.0`. | **SOUND** | S13, S14 | `:232-255`. A real negative assertion with two independent terms, and `r_vel.get("val", None)` (`:250`) defaults to `None`, which fails `!= 0.0` — safe. Fields verified: `winampDisplay.cpp:742` (`scrollOffset`), `:767` (`scrollVelocity`). Note it reads `get scrollOffset`/`get scrollVelocity` rather than `get wrScroll`, i.e. the same two commands `T160` uses — which is correct (they are the same object) but means the *only* thing making this the "WebRadio variant" is which app happens to be foreground. |

---

## 2. Eject and injected error states — `T_WR_EJECT_01`/`02`, `T_WR_ERR_01`–`04` (6)

Registry order `webradio.py:1558-1563`.

**The firmware fact that decides four of these six rows.** `WRPlayState` is
`STOPPED = 0, CONNECTING = 1, PLAYING = 2, ERROR_WIFI = 3, ERROR_STALL = 4,
ERROR_UNREACHABLE = 5, ERROR_BLOCKED = 6` (`webRadioApp.h:36-44`). The shared
helper `_wr_err_test`'s cleanup is
`dut.cmd("set wrState 3")  # back to STOPPED (quiescent)` (`webradio.py:512`).
**State 3 is `ERROR_WIFI`, not `STOPPED`.** Every one of the four `T_WR_ERR_*`
ids therefore exits leaving the app parked in an error state, with a comment
asserting the opposite — and `T_WR_ERR_03`, whose whole subject *is* state 3,
"cleans up" by writing the value it was testing. Filed as **F-1**.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `webradio.py:388` | T_WR_EJECT_01 | Eject **from Spotify** hits `EJECT`, fires TLS reset + force poll (same as the logo tap), and does **not** switch apps (TASK-414 / ADR-059 D6). | `hit == "EJECT"`, `action == "EJECT"`, `get appId.name == "Spotify"` after, and a `"hard reset"` log line within 8 s. | **SOUND** | S13, S5, S14 | `:413-432`. Four device-observed values across two independent surfaces, and the log half uses the **right** instrument: `_tap_and_wait_log` keeps the tap-ack parse and the marker scan in one unbroken `readline()` loop (`_helpers.py:20-65`), which is precisely the race `T_PLR_07` still has (WP-E **E-10**). The marker is live — `LOG_I("spotify.tls", "hard reset — stopping client")`, `spotifyTaskStorage.cpp:363`. The body's own comment records that its historical FLAKE result was the harness race, not firmware (`:405-412`), which is the best kind of test archaeology. Two costs. **(a)** The missing-log branch calls `flake("T_WR_EJECT_01", …)` (`:429`) and **`T_WR_EJECT_01` is not declared in `flaky.yaml`**, so `flake()` rewrites it to `FAIL: UNDECLARED flake — no entry for T_WR_EJECT_01 …` (`lib/results.py:184-191`) — a failure message about bookkeeping instead of about TLS. Third instance of WP-C **C-7**, second of WP-E **E-3**. **(b)** Its three assertions duplicate the Spotify leg of `T_PLR_06` (`player.py:220-247`), which the section header at `:381-386` acknowledges ("Superseded by `T_PLR_06` for the cross-mode gate; kept as the WebRadio-app-specific unit check") — except that this leg is the one that never enters WebRadio, so the retained id is the half that is *not* WebRadio-specific. |
| `webradio.py:437` | T_WR_EJECT_02 | Eject **from WebRadio** re-enqueues the station list (`wrEnqueues` advances) and does not switch apps. | `hit`/`action == "EJECT"`, `get appId.name == "WebRadio"` after, and `enq_after > enq_before` on `get dataq.wrEnqueues`. | **SOUND** | S7, S13, S14, S6 | `:450-477`. The `wrEnqueues` comparison is the load-bearing one and it is strict — `enq_after <= enq_before` is a `fail()` (`:471`) — on a monotonic device counter that only `enqueueWebRadioStations()` moves (`dataTask.h:357`, `dataTaskStorage.cpp:2064`, surfaced at `cmdGet.cpp:106`). Both reads default to 0, so two lost replies fail rather than pass: the safe direction. It restores Spotify on every exit path including the failures (`:458`, `:462`, `:468`, `:477`) — the only body in this family that is systematic about it. Costs: the entry is `_webradio_enter_with_stations`, whose failure is a `skip` (`:446-448`), and the row duplicates `T_PLR_06`'s WebRadio leg assertion for assertion (`player.py:233-252`). |
| `webradio.py:518` | T_WR_ERR_01 | `set wrState 6` (ERROR_BLOCKED) is accepted and round-trips; "visual: 'Station blocked'". | `_wr_err_test`: `set wrState 6` returns `ok`, then `get wrState.state == 6`. | **HOLLOW** | S3, S4, S2, S14 | `:521-522` via `:502-510`. Textbook S3: the asserted value is the harness's own input, read back out of the same `_state` byte the setter wrote — `dbgSet` does `_state = (WRPlayState)s` (`webRadioApp.cpp:955-960`) and `dbgGet` prints `(int)_state` (`:716-720`), one member, no intervening behaviour. Nothing in the ERROR_BLOCKED *behaviour* is observed: not the banner text, not `isRunning()`, not `hasTerminalError()` (`webRadioApp.h:227-230`), not the auto-skip exclusion that makes BLOCKED different from the other errors (`webRadioApp.cpp:316`). The pass detail hands the actual subject to a human — `"(visual: 'Station blocked')"` — which is S4's shape exactly. And `set wrState` returns `true` for **any** input, applying the value only when in range (`webRadioApp.cpp:956-959`), so the `ok` check proves nothing either. What the id genuinely covers is "the debug injector works", which is a fixture, not a feature. |
| `webradio.py:527` | T_WR_ERR_02 | `set wrState 5` (ERROR_UNREACHABLE) round-trips; "visual: 'Station unreachable'". | Same helper, state 5. | **HOLLOW** | S3, S4, S2, S13, S14 | `:530-531` via `:502-510`. Identical to `T_WR_ERR_01` with one integer changed. Additionally redundant against a test that *does* prove the state: `T237` drives the firmware to ERROR_UNREACHABLE through the real auto-skip path and asserts `state == 5` as an *outcome* (`:926-929`), which is the assertion this id makes by injection. |
| `webradio.py:536` | T_WR_ERR_03 | `set wrState 3` (ERROR_WIFI) round-trips; "visual: 'WiFi lost'". | Same helper, state 3. | **BROKEN** | S3, S4, S12, S14 | `:539-540` via `:502-513`. The round-trip half is the same tautology as its two siblings, but this row has a defect the others do not: **its cleanup writes the same value it just tested.** `_wr_err_test`'s `finally` block issues `set wrState 3` labelled *"back to STOPPED (quiescent)"* (`:512`) while `STOPPED` is 0 and 3 is `ERROR_WIFI` (`webRadioApp.h:37-40`). For this id the "restore" is a no-op that leaves the injected state installed; for all four ids it leaves the app in ERROR_WIFI rather than quiescent. Per rubric §2 — "a body that no longer matches the firmware surface it drives" — a test whose teardown asserts the wrong enum value of the very enum under test is BROKEN, not merely leaky. **F-1**. |
| `webradio.py:545` | T_WR_ERR_04 | Stop audio (so `_bufPct` resets), then `set wrState 1` (CONNECTING) round-trips; "visual: 'Connecting…', POSBAR empty". | Same helper, state 1, preceded by `set wrStop 1`. | **HOLLOW** | S3, S4, S2, S14, S7 | `:548-554` via `:502-510`. Same tautology; and the one thing that would distinguish it from its siblings — that the POSBAR is empty because `_bufPct` was reset — is asserted nowhere, although `get wrPosbar` reports `bufPctRaw`, `bufPctSmoothed` and `bufPctDrawn` in one line (`webRadioApp.cpp:869-882`, `MEMBUDGET_PHASE1`). The `set wrStop 1` preamble is therefore an unverified fixture step whose only stated purpose is a visual a human is asked to check. It is also the one `T_WR_ERR_*` that enters through `_ensure_webradio` (`:548`) rather than `_switch_to_webradio_capture_heap` — **F-6**. |


---

## 3. Coexistence, heap and volume — `T_WR_COEX_01`/`02`/`04`, `T_WR_HEAP_01`–`04`, `T_WR_VOL_03`, `T_WR_VOL_CLAMP` (9)

Registry order `webradio.py:1564-1572`. This is the block where "audio is
unobservable" bites hardest: seven of the nine either assert `wrState == 2` as a
stand-in for "it is playing", or depend on a station list the harness cannot
guarantee. `T_WR_COEX_01` and `T_WR_VOL_03` are both declared flakes for exactly
that reason (`flaky.yaml:72-93`, `:95-108` — TASK-540, four different outcomes
across five runs, attributed to radio-browser.info station churn).

**The state field is directly writable.** `set wrState <n>` assigns `_state`
outright (`webRadioApp.cpp:954-960`) and `get wrState` prints `(int)_state`
(`:716-720`). Any id whose oracle is `wrState == 2` is therefore asserting a
`uint8_t` that four ids in §2 write by hand — which makes the ordering hazard in
**F-1** a correctness question, not only hygiene.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `webradio.py:559` | T_WR_COEX_01 | Enter WebRadio, load the station list, start play, reach PLAYING. | `count >= 1` from `get wrCount`, then `get wrState.state == 2` within 30 s. | **WEAK** | S2, S7, S8, S14 | `:563-578`. Two real device-observed values, and the fetch half is genuine — `count` is `_stationCount` (`webRadioApp.cpp:721-726`), which only a completed `enqueueWebRadioStations` result installs. The play half is where the claim outruns the oracle. `set wrPlay 0` is a **silent no-op** when the index is out of range (`if (idx >= 0 && idx < _stationCount) _play(idx);` and `return true` regardless, `webRadioApp.cpp:969-973`), and `wrState == 2` is set by `_play()`'s success path but is also the value four `T_WR_ERR_*` neighbours can leave behind. Nothing downstream of the state byte is read — not `wrPump.cycles` (which would prove the decode loop is turning), not `wrUnderruns.playMs`, not `wrPlaying.ms` (`webRadioApp.cpp:833-839`), all of which exist. So "the stream is playing" is asserted as "a byte says PLAYING". The 30 s bound is uncited. Correctly declared flaky (`flaky.yaml:72`) — but see **F-8**: the body never calls `flake()`, so the declaration and its mandated retry never fire. |
| `webradio.py:583` | T_WR_COEX_02 | While playing, NEXT and PREV taps change the station index. | `not (idx1 == idx0 and idx2 == idx1)` — i.e. **at least one** of the two taps moved `wrIdx`. | **WEAK** | S8, S2, S14, S9 | `:589-608`. The oracle is a disjunction where the claim is a conjunction: a NEXT that does nothing passes as long as PREV moves, and vice versa. The expected values are knowable and trivially assertable (`idx1 == (idx0+1) % count` and `idx2 == idx0`) — `_nextStation()`/`_prevStation()` are plain index steps (`webRadioApp.cpp:972-973` region) — and neither is used, so a NEXT/PREV pair wired to the *same* handler passes. The defaults are in the safe direction (`get("idx", idx0)` / `get("idx", idx1)` both collapse to "no change", which fails). It also never restores: on the pass path `wrIdx` is wherever the two taps left it, and the PREV tap is issued unconditionally so a failed NEXT still moves the index backwards. Two `time.sleep(0.5)` used as the settle oracle. |
| `webradio.py:613` | T_WR_COEX_04 | "Touch latency during playback < 500 ms" — the UI stays responsive while audio decodes. | Wall-clock from `dut.send("tap …")` to the first JSON line `dut.read_json` returns, compared against 500 ms. | **WEAK** | S8, S2, S14 | `:619-636`. What is measured is the **host-to-device serial round trip for a tap command**, which includes the harness's own write, the firmware's command parse and the `Serial.printf` — not the touch-to-repaint latency the title claims, and not anything a user would perceive. The bound is vacuous in the other direction too: the same command in every other body in this file is issued with `timeout=3.0` and completes routinely, so 500 ms is roughly an order of magnitude above the observed cost and can only be violated by a near-hang, which `T_WR_HEAP_04` would also catch. `dut.read_json` returns the **first** JSON line it sees (`lib/dut.py`), not necessarily the tap's own reply, so an async reply from another task shortens the measurement. Leaves the station index moved on the fail path (the PREV restore is after the measurement but before the threshold check, so that much is right). |
| `webradio.py:641` | T_WR_HEAP_01 | App-launch heap baseline: `HEAP init` min ≥ 30 KB after a fresh WebRadio launch. | `get wrHeap.initMin >= 30000`. | **SOUND** | S7, S10, S14 | `:648-670`. The values are device-recorded at the top of `init()` — `_heapInitFree = ESP.getFreeHeap(); _heapInitMin = ESP.getMinFreeHeap();` (`webRadioApp.cpp:40-43`) — and re-read through a purpose-built getter (`:841-849`) rather than scraped from a log line, which is the right call and the body says why (`:643-645`). The `_restore_spotify` + cycle entry guarantees `init()` actually re-ran, so the numbers are this launch's, not a stale pair from an earlier entry. Two costs: `30_000` is an uncited literal that `mem_manifest.yaml` does not carry, and the all-zeros case is a `skip` (`:664-666`) although zeros would themselves be evidence that `init()` never ran. |
| `webradio.py:675` | T_WR_HEAP_02 | Post-fetch heap: the TLS spike from the station fetch is fully recovered, min ≥ 30 KB. | `HEAP post-fetch free=… min=…` scraped from the log, falling back to `get wrHeap.fetchMin`; then `>= 30000`. | **SOUND** | S7, S10, S14 | `:684-713`. Marker verified live: `LOG_I("webradio", "HEAP post-fetch free=%u min=%u")` (`webRadioApp.cpp:379`). The two-source construction is the good part — a missed log line falls back to the stored pair (`:702-706`) rather than failing on a capture race — and the `dut.send`-before-drain ordering is deliberate and explained (`:681-683`). The structural weakness is that the marker is emitted **only on the branch that installs a result** (`webRadioApp.cpp:376-380`, after the stale-result discard at `:365-374`), so a fetch that never resolves leaves both sources at 0 and the id skips (`:707-709`) — a fetch failure and a heap regression are distinguishable here only because the *value* is zero rather than low. `30_000` uncited, as above. |
| `webradio.py:718` | T_WR_HEAP_03 | Audio-decode heap watermark ≥ 40 KB during sustained decode. | `HEAP play free=… min=…` scraped from the log within 65 s, then `min >= 40000`. | **SOUND** | S7, S10, S14 | `:736-748`. Marker verified live and, unlike the other two, it is emitted **only while `_state == PLAYING`**, on a 30 s cadence (`webRadioApp.cpp:423-431`) — which makes the log line itself a genuine playback proxy: it cannot be printed unless the app held PLAYING across a 30 s boundary. That is a materially better audio oracle than `wrState == 2`, and it is incidental to the id's purpose. Costs: three separate `skip()` exits for "not playing" (`:725`, `:729`, `:733`) plus a fourth for "line not seen" (`:738`), so on a board with no station list the id contributes nothing and says PASS-adjacent nothing; the printed message says "within 35s" while the timeout is 65 s (`:735` vs `:736`); and `40_000` is uncited. |
| `webradio.py:753` | T_WR_HEAP_04 | No panic / abort / stack overflow in a 2-minute playback window. | `dut.drain_log_lines(r"panic\|abort\|stack overflow\|Guru Meditation\|LoadProhibited\|StoreProhibited", count=1, timeout=120.0)` returning empty. | **WEAK** | S8, S2, S14, S7 | `:770-777`. A real negative assertion on a real channel, and the regex covers the loud crash classes. Three gaps make it narrower than "no crash in 2 minutes of playback". **(a) It never re-checks that playback was still running.** The precondition establishes PLAYING, then the body watches the log for 120 s and asserts nothing at the end — a stream that died at second 3 and left the app parked in `ERROR_UNREACHABLE` produces a clean 120 s and a PASS, which is precisely the failure `T_WR_COEX_01`'s flaky entry describes. `get wrPlaying.ms >= 120000` (`webRadioApp.cpp:833-839`) is one command and would close it. **(b) The regex misses the reset classes the DUT actually produces** — `rst:0x`, `ets Jul`, "Brownout detector was triggered", "Task watchdog got triggered" — all of which `test_fbrowser_player.py:50` and `test_playorder_player.py:224-232` treat as hard failures. A silent WDT reboot mid-window passes. **(c) The 120 s are unattributed:** nothing establishes the board was decoding rather than idling in a foreground app. |
| `webradio.py:782` | T_WR_VOL_03 | "Normal `_play()` applies the `webRadioMaxVolume` cap (not 21)" — after `set wrVol 21`, a normal play resets the volume to the configured ceiling. | `get wrState.state == 2` after `set wrPlay 0`. **The volume is never read.** | **HOLLOW** | S4, S2, S8, S14 | `:790-806`. The pass detail states the reasoning instead of asserting it — *"Volume reset is confirmed **structurally**: `_play()` always calls `setVolume(webRadioMaxVolume)` before `connecttohost()`. Audible clipping at vol=21 vs clean at vol=10 is the full check"* (`:802-806`) — which is S4 in its purest form: the precondition (playback started) is asserted and called a pass for a claim about volume. And the oracle it *needs* exists and is used by the very next id: `get wrEffectiveVol` reports `eff`, `maxVol` and `hwMod` in one line (`webRadioApp.cpp:775-783`), and `get wrVolPct` reports the `scaled` value actually fed to `setVolume()` (`:786-790`). Neither is read. Worse, the injected value may never have been applied at all — `set wrVol` with no live `Audio` session is clamp-store-only and logs *"vol set=%d — no active session, not applied"* (`webRadioApp.cpp:1107-1115`), and the body issues it immediately after `set wrStop 1`, i.e. exactly when there is no session. So the id can pass having never established its own premise. It is also a declared flake whose body never calls `flake()` (**F-8**). |
| `webradio.py:811` | T_WR_VOL_CLAMP | `wrEffectiveVolume()` enforces the §HW Mod ceiling: stock soft-caps at 12, the mod passes the full 1–21 range. | Eight `(hwMod, maxVol)` inputs, each asserting **three** returned fields — `eff == expected`, `maxVol == mx`, `bool(hwMod) == bool(hw)`. | **SOUND** | S11, S10, S14 | `:837-859`. The best-constructed row in the family and the only one in this block whose oracle is the function under test rather than a proxy: `get wrEffectiveVol` calls `wrEffectiveVolume()` directly (`webRadioApp.cpp:775-783`), whose body is `uint8_t hi = g_settings.webRadioHwMod ? WR_VOLUME_MAX : WR_VOLUME_SOFT_CAP_STOCK;` (`audio/audioEngine.h:70`). Eight cases bracket the cap from both sides (at it, below it, above it, with and without the mod), and the companion `maxVol`/`hwMod` assertions mean a setter that silently ignored the write fails rather than passing on a stale ceiling. It restores stock defaults and Spotify in a `finally` (`:860-865`) — one of only three bodies in the family that restore anything on the exception path. The one real cost is S11: `12` and `21` are re-declared eight times over as literals while `WR_VOLUME_SOFT_CAP_STOCK = 12` and `WR_VOLUME_MAX` live in `audio/audioEngine.h:62,70` and are not parsed (LL-114). |

---

## 4. The auto-skip bound and its retry — `T237`, `T276` (2)

Registry order `webradio.py:1573-1574`. These two are the family's high-water
mark: both drive real firmware state machines through the deterministic
`set wrDeadUrls N` hook (`webRadioApp.cpp:1031-1055`), which needs no network, no
account and no station list, and both assert *transitions* rather than resting
values.

**Both ids collide with an unrelated `test_plan.md` entry.** The plan declares
`### T237 — [app-settings-wire-001] Crypto currency change updates app state`
(`test_plan.md:4188`) and `### T276 — [M-WEBRADIO-PREVIEW] Skin base layer loaded
from gen/skin_preview.png` (`:4537`). Neither describes the body that carries the
id in the registry, and `build_all_meta` shows no second body for either. Filed
as **F-2**.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `webradio.py:875` | T237 | Auto-skip-on-stall is **bounded to one list pass** and lands terminal: with auto-skip ON a user play skips exactly N−1 times and never loops; with it OFF it parks on the first failure. ADR-045 runaway-skip safety bound. | Six device-observed values: `wrCount.count == N`; `wrSkip.tried` saturating at exactly `N-1`; `tried` **still** `N-1` 1.5 s later; `wrState.state == 5`; then with auto-skip off, `tried == 0` **and** `wrIdx.idx == 0`. | **SOUND** | S9, S10, S14 | `:895-954`. The strongest test in the family. It asserts an exact saturation value rather than a bound, then re-reads the same counter to prove *absence of motion* — the runaway case the ADR-045 bound exists to exclude — and only then reads the terminal state, so a scan that reached state 5 by looping is still caught. The negative leg is a genuine second behaviour with two independent terms (`tried == 0` and `idx == 0`), not a restatement. Every field is device-computed: `_autoSkipTried` and `_currentIdx` are printed by `get wrSkip`/`get wrIdx` (`webRadioApp.cpp:821-830`, `:746-750`), and `_wr_skip_tried` returns `-1` on a non-ok reply (`:870-872`) so a lost read fails rather than defaulting to a passing value. The `finally` restores `wrDeadUrls 0`, `wrAutoSkip 1`, stop and Spotify (`:949-954`). Costs: `N = 4`, the 12 s saturation deadline and the 1.5 s no-loop window are all uncited literals, and the 1.5 s window is short relative to `WR_SKIP_PACE_MS = 2000` (`webRadioApp.h:72`) — one pace interval, so a slow runaway could sneak through. |
| `webradio.py:959` | T276 | TASK-276's terminal-retry re-arm actually recovers a parked `ERROR_*` after `WR_TERMINAL_RETRY_MS`, "closing the gap" TASK-393 opened. | `wrSkip.tried` observed **dropping below** the saturated `N-1` within 45 s of terminal — chosen because the retry handler resets `_autoSkipTried` to 0 before re-playing, so a lower reading cannot arise any other way. | **WEAK** | S11, S10, S14 | `:1002-1053`. The oracle choice is excellent and the docstring argues it properly (`:976-980`): a transient CONNECTING could be missed between polls, a dropped counter could not. The assertion is real and the id genuinely covers the re-arm's condition logic. Three reasons it is narrower than it claims. **(a) It cannot cover the defect it says it closes.** The synthetic path forces the failure before `connecttohost()` is ever called, and the task board records the consequence in as many words: *"That path never calls the real `connecttohost()`, so this narrows the regression to something specific to state left behind by a genuine failed connect, not the retry logic itself"* (`tasks.md:1189-1193`). TASK-393 is still open (`tasks.md:1123`, status "open"). **(b) The docstring is stale in the opposite direction** — *"Expected to currently FAIL — that is the point"* (`:982-984`) — while the id has passed since authoring (fired at 32 s, `tasks-archive.md:14383-14384`). A reader triaging a red run is told to expect red. **(c) S11:** `WR_TERMINAL_RETRY_MS = 30000  # webRadioApp.h:69 — keep in sync if that constant moves` (`:989`) is a mirrored firmware constant with a self-aware comment, and the cited line is **already stale** — the constant is at `webRadioApp.h:73`. `SLACK_S = 15.0` and `N = 3` are uncited. |

---

## 5. TLS path, Spotify coexistence and the VIS batteries — `T_WR_TLS_01`, `T_WR_SPOTIFY_RESUME_01`, `T_WR_VIS_01`–`05` (7)

Registry order `webradio.py:1575-1581`.

**The `visMode` remap.** `get visMode` does not report `vu::VisMode`'s ordinal;
`cmdGet.cpp:477-487` remaps `VIS_ATLAS_MODE → 0`, `VIS_VU → 1`, `VIS_BLANK → 2`,
`VIS_WAVE_ATLAS → 3`, `VIS_SPECTRUM → 4`, `VIS_WAVE → 5`. The module's own header
comment says *"VIS_WAVE is still dead … and reads back -1"* (`webradio.py:1267`)
— stale: it reads back 5, and −1 is now only the unreachable default. No oracle
depends on it, so this is documentation drift, not a defect (**F-13**).

**`_get_vis_mode` returns `None` on a failed read** (`_helpers.py:110-119`), which
matters only for the two negative VIS ids, where `None != 4` is a passing
comparison.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `webradio.py:1076` | T_WR_TLS_01 | Record **which** TLS path loaded the station list — pinned `setCACert()` or the `setInsecure()` fallback (TASK-214/ADR-029). Either value is a legitimate pass; an empty list is not. | `get wrLastHttp`: `count >= 1` gates the pass, then `tlsInsecure` is *reported*; `count < 1` with `http == -1` skips, any other empty-list code fails. | **SOUND** | S7, S10, S14 | `:1149-1175`, against `webRadioApp.cpp:805-813` — `_lastHttpCode`, `_lastOk`, `_stationCount`, `_lastJsonErr`, `_lastTlsInsecure` are all firmware-recorded at fetch resolution. This is the one id in the family that is honest about being an **observation** rather than a bound, and it is graded SOUND on that claim: it does fail for the reason it exists (a fetch that resolves empty for a device-side or cert-side reason). Three things make it better than its neighbours: it drains the fetch pipeline before ejecting, with the contention root-cause written out (`:1093-1107`), it samples `get dataq` throughout and prints the deltas, and on a confirmed stall it pulls the DUT's 48-line log ring **over HTTP** rather than over the serial line it is observing (`:1058-1073`) — the only off-channel diagnostic in the suite. The `http == -1` skip is a deliberate, argued network/device split (`:1159-1166`), not a swallow. Costs: it is the one id whose pass can be a TASK-284-truncated list (`:1153-1157` says so and annotates the detail string), so `count >= 1` is a weaker bound than "the list is complete"; the 180 s and 200 s budgets are uncited; and it is a `flaky.yaml` **candidate**, not a declaration (`flaky.yaml:159-161`), so if it ever called `flake()` it would fail closed with a candidates hint (`lib/results.py:184-190`) — it does not call it. |
| `webradio.py:1180` | T_WR_SPOTIFY_RESUME_01 | After WebRadio holds `spotifyTask::tlsYield()` for a whole playback span, cycling back to Spotify actually **resumes spotifyTask** — not merely that `appId` flipped and the device did not crash. | Five device-observed values: the cycle tap's `hit == "TASKBAR"`, `appId == "Spotify"`, the deadzone tap's `action == "FORCE_POLL"`, then `shellBusy` **rising** within 4 s and **clearing** within 20 s. | **SOUND** | S7, S9, S14 | `:1207-1256`. The best-reasoned oracle in the family and the body explains why the obvious one was rejected: `get touchResult` is serviced by the loop task and would answer even with `spotifyTask` wedged, so the test forces a poll and watches the **rising edge** of `shellBusy` with background polling suspended, so the only thing that can raise it is this poll (`:1222-1231`). That is a genuine liveness proof of the other task, and both directions are asserted — a poll that starts and hangs fails distinctly from one that never starts (`:1242-1252`). It is also the only body in the family that uses `_bgpoll_suspended`, the context manager that restores `bgPoll` on an exception (`_helpers.py:444-454`); every other body writes `set bgPoll 0` and hopes. Costs: the whole thing rests on a station reaching PLAYING, which is a `skip` on this rig's fetch flakiness (`:1192-1198`), so the coexistence path is unverified whenever the list is empty; the pass detail defers the visual repaint to a human (`:1256`) but does not count it as the pass, which is the honest form; and it leaves Spotify with a forced poll in flight. |
| `webradio.py:1352` | T_WR_VIS_01 | Decode-tail regression, **isolated**: after ~45 s of playback, `maxPumpMs <= 50` (TASK-278's ceiling) read with no concurrent screendump/tap traffic. | `wrPump.ok && wrPump.alive`, `maxPumpMs` present, `maxPumpMs <= 50`. | **WEAK** | S8, S10, S13, S14 | `:1362-1383`. The read is a real one on a real firmware metric — `s_wrPumpMaxPumpMs` is updated inside the pump loop (`audio/audioEngine.cpp:381`) — and the three-stage guard (`ok`, `alive`, field-present) means a renamed field fails rather than defaulting (`:1371-1377`), the opposite of an S6. But **the metric is not windowed the way the test assumes.** `s_wrPumpMaxPumpMs` is zeroed only inside `wrEnsurePumpTask()` *after* its `if (s_wrPumpTask) return;` early exit (`audio/audioEngine.cpp:405-409`), so it is a high-water mark for the life of the pump task — which survives station changes and every later test in the run. The isolation the docstring is so careful about (`:1355-1359`, EXP-017's false 272 ms) isolates the **read**, not the measurement: a spike caused by `T_WR_HEAP_03`'s log drain or by an earlier screendump is still in the number when this id reads it. In a full `run/test`, where this id runs after eleven other WebRadio ids, the 50 ms bound is being applied to the worst pump cycle since boot. The `45.0` settle and the `50` ceiling are literals; `50` at least has a stated origin (TASK-278). |
| `webradio.py:1386` | T_WR_VIS_02 | The **real** audio envelope animates, and only in the mode that reads it: near-zero pixel delta at `VIS_ATLAS_MODE` (negative control), materially non-zero at `VIS_VU`. | Two screendump diffs of a 140×70 region 1.5 s apart: `vu_delta > 100`; the Atlas control is measured, printed and **warned** on but never failed. | **WEAK** | S8, S10, S7, S14 | `:1398-1428`. The positive half is a genuine end-to-end oracle — real pixels, changing because `lLevelRef()`/`rLevelRef()` are being fed by the decoder — and reaching `VIS_VU` is asserted rather than assumed (`:1412-1416`). The negative control, which is the half that makes the claim "**only** in the mode that reads it", is not an assertion: `if atlas_delta > 500: print("WARNING … not failing on this alone")` (`:1408-1410`). So the id cannot fail if Atlas mode started animating too, which is the regression the control exists for. The `100` threshold is derived from EXP-016's measured 531/9800 and cited (`:1391-1393`); `500` is not. The screendump helper `fail()`s and returns `None` on an exception (`:1346-1348`), which is the right shape. Gated on a real station list, so it skips whenever the fetch fails. |
| `webradio.py:1431` | T_WR_VIS_03 | Spotify's **synthetic** `VIS_VU` path is unaffected by the WebRadio real-envelope work (Goal 2 regression guard). | Same two-screendump diff, on Spotify: `delta > 100`. | **WEAK** | S7, S12, S10, S14 | `:1439-1466`. The assertion is real and the same shape as `T_WR_VIS_02`'s positive half. Two problems, both structural rather than authorial. **(a) It is a permanent SKIP on this rig.** The guard is `info.isPlaying`, and TASK-243 (owner-account Premium lapsed) means Spotify polls 403 and `isPlaying` is never true — the body names the blocker itself (`:1445-1449`). Per WP-D §6 this is the twelfth-plus id in the suite degraded to a permanent non-result by the same external condition; the skip is correctly argued, the coverage is still absent. **(b) It drives Spotify end to end and is scoped `WebRadio`** (§0's command), so `./run/test-targeted --scope Spotify` misses this Spotify regression guard entirely — **F-11**, the WebRadio instance of WP-E **E-5**, and the `@meta(scope=…, scope_reason=…)` mechanism that fixes it is used nowhere in this module. |
| `webradio.py:1483` | T_WR_VIS_04 | WebRadio's tap-cycle reaches `VIS_SPECTRUM` (`visMode == 4`), and the **real per-band spectrum animates** while playing — two `wrSpec` samples 1.5 s apart differ in at least one band. | `_cycle_vis_to(4)` returning 4; `len(bars) == 19` on both samples; `bars1 != bars2`. | **SOUND** | S11, S8, S7, S14 | `:1489-1513`. **The best audio oracle in the family**, and one of the few anywhere in the suite that observes the decode path rather than a state field: `get wrSpec` dumps `vu::specHRef()` — the promoted per-band bar heights (`webRadioApp.cpp:927-940`) — which are computed from decoded PCM, so a change across 1.5 s cannot be produced by anything except audio actually flowing. It is also strictly better than a screendump diff for the same claim (numeric, no render dependency, no region tuning), and the file says so (`:1478-1481`). Two costs. The mode half and the animation half are one id, so a failure at `_cycle_vis_to` and a flatline are the same red. And `19` is `vu::SPEC_BARS` (`winamp/vuMeter.h:50`) re-declared as a literal — S11, LL-114; a build with a different bar count fails with "bad wrSpec response(s)" rather than the truth. `bars1 != bars2` is also the weakest form of "animates": one band moving by one unit passes, where a per-band spread or a non-zero maximum would be a real envelope check. |
| `webradio.py:1516` | T_WR_VIS_05 | Spotify's tap-cycle **never** reaches `VIS_SPECTRUM` (Option B regression guard) — six taps around a four-stop cycle, `visMode == 4` never observed. | `m != 4` after each of six taps. | **WEAK** | S7, S8, S12, S5, S14 | `:1533-1547`. A real negative assertion, and six taps genuinely covers Spotify's four stops with margin. Three weaknesses, in increasing order. **(a)** Same permanent-SKIP and same mis-scoping as `T_WR_VIS_03` (**F-11**). **(b)** A failed `get visMode` read returns `None` (`_helpers.py:110-119`), and `None != 4`, so a board that stopped answering that command passes six times over and reports `visited [None]`. There is no assertion that the cycle *moved* at all — a `nextMode()` that no-oped entirely is also a pass, with `seen == {0}`. **(c)** The complementary positive — that Spotify's cycle visits exactly `{0, 3, 1, 2}` — is one line away (`seen` is already collected and printed in the pass detail, `:1546`) and would turn the row from "never saw 4" into "saw exactly the four it should", which is what the Option B guard actually claims. |

---

## 6. The proxy problem — what this family actually observes

### 6.1 Nothing in the rig can hear

The brief's question. There is no microphone, no I2S loopback and no PCM tap in
the harness, so every claim of the form "the station plays" is asserted through
a proxy. The four rungs below are ordered by distance from the audible
behaviour, and the distribution is the family's headline.

| Rung | What it observes | n | Ids |
|---|---|---|---|
| **1 — decoded audio content** | a value computed *from* decoded PCM: `vu::specHRef()` bar heights (`webRadioApp.cpp:927-940`), or screen pixels driven by `lLevelRef()`/`rLevelRef()` | **2** | `T_WR_VIS_04`, `T_WR_VIS_02` |
| **2 — the decode machinery advancing** | the pump task's own counters (`wrPump.alive`/`cycles`/`maxPumpMs`, `audio/audioEngine.cpp:381,390`), or a log line the firmware emits *only* from the PLAYING branch (`HEAP play`, `webRadioApp.cpp:423-431`) | **2** | `T_WR_VIS_01`, `T_WR_HEAP_03` |
| **3 — a state byte** | `get wrState.state == 2`, or `wrPlaying.playing` — `_state`, which `set wrState` writes directly (`webRadioApp.cpp:954-960`) | **6** | `T_WR_COEX_01`, `T_WR_COEX_02`, `T_WR_COEX_04`, `T_WR_HEAP_04`, `T_WR_VOL_03`, `T_WR_SPOTIFY_RESUME_01` (precondition only) |
| **4 — no audio oracle at all** | index, heap, scroll, TLS path, clamp arithmetic, skip counters | **20** | the six PLEDIT ids, both `T_WR_EJECT_*`, all four `T_WR_ERR_*`, `T_WR_HEAP_01`, `T_WR_HEAP_02`, `T_WR_VOL_CLAMP`, `T237`, `T276`, `T_WR_TLS_01`, `T_WR_VIS_03`, `T_WR_VIS_05` |

**Rung 3 is the honest failure line, and it is worse than "narrow".** `_state`
is not merely a summary of playback — it is a byte four ids in this same module
write by hand, and `_wr_err_test`'s broken teardown (**F-1**) leaves it at
`ERROR_WIFI` rather than `STOPPED`. A test whose oracle is `wrState == 2`
cannot distinguish "the decoder is consuming stream bytes" from "something set
the byte". The mitigating firmware fact is that the stream-liveness watchdog
drops out of PLAYING within `WR_STREAM_DEAD_MS = 5000` of the input buffer
ceasing to be read down (`webRadioApp.h:59-65`), so a *sustained* PLAYING is a
much better proxy than an instantaneous one — which is exactly the distinction
the registry ids do not draw and `test_adr045_gate.py` does (§7.1).

**What makes the top rung good is that someone built the observable first.**
`get wrSpec` and `get wrPump` were added for a DUT tuning pass and a decode-tail
measurement (TASK-387, TASK-278), not for a test, and the two ids that use them
are the family's strongest. This is WP-E's lesson repeating: the quality of a
test tracks the quality of the observable it was given.

**Which ids claim playback and do not observe it.** `T_WR_VOL_03` ("normal play
applies the volume cap" — reads no volume, **HOLLOW**), `T_WR_HEAP_04` ("no panic
in a 2-min *playback* window" — never re-checks playback), `T_WR_COEX_04` ("touch
latency *during playback*" — measures a serial round trip), and `T_WR_COEX_01`
("→ PLAYING" — the byte). Four rows, and in every one of them the better oracle
already exists on the device and is used by a neighbour.

### 6.2 The `bitrateCap` and station-list hazards

The brief asks whether an index-based station selection can be selecting nothing.
Split the family in two.

**Cap-immune (16 ids).** Everything driven by `set wrDeadUrls N`, which writes
`_stations[]` in RAM with `bitrate = 0` and never consults the country filter,
the cap, or the network (`webRadioApp.cpp:1031-1055`): the six PLEDIT ids
(`_vs_precondition_webradio`, `webradio.py:44`), `T237` (`:900`), `T276`
(`:1004`). Add the four `T_WR_ERR_*` (inject a state, no list needed),
`T_WR_VOL_CLAMP` (reads `g_settings` only, and says so at `:826-827`),
`T_WR_EJECT_01` (never leaves Spotify), `T_WR_HEAP_01` (reads the `init` snapshot
taken before the fetch, `webRadioApp.cpp:40-43`), `T_WR_VIS_03` and `T_WR_VIS_05`
(Spotify). These cannot be affected by `bitrateCap = 192` vs the firmware default
96, nor by TASK-284 mirror truncation.

**Fetch-dependent (14 ids).** `T_WR_EJECT_02`, `T_WR_COEX_01`/`02`/`04`,
`T_WR_HEAP_02`/`03`/`04`, `T_WR_VOL_03`, `T_WR_TLS_01`,
`T_WR_SPOTIFY_RESUME_01`, `T_WR_VIS_01`/`02`/`04` all need a non-empty real
station list, and every one of them selects **station index 0** (`set wrPlay 0`)
without ever reading what station that is — `get wrStation <idx>` reports the
name, bitrate and URL (`webRadioApp.cpp:729-744`) and no id in the family calls
it.

**Do they distinguish an empty list from a broken feature?** Mostly yes, and
better than expected: `_webradio_enter_with_stations` returns 0 and each caller
`skip()`s with "station list unavailable (network or fetch failure)", and
`_wait_wr_count` early-exits on the firmware's own `pending == 0`
(`webradio.py:260-280`) rather than burning the full timeout — so "the fetch
resolved with nothing" is distinguished from "the fetch is still running".
`T_WR_TLS_01` goes further and splits the empty case by HTTP code, skipping only
on all-mirror `-1` and failing on `-9984`/`-100`/`-101`/`-102` (`:1158-1172`).

**What none of them distinguish is a *short* list from a complete one.**
`count >= 1` is the universal gate. Under TASK-284 truncation a 1-station list
passes every check a 30-station list passes, and `T_WR_TLS_01` annotates the
truncation into its pass string rather than failing on it (`:1174`). Under a
`bitrateCap <= 96` — the firmware default — the NPO stations vanish entirely and
index 0 becomes a different station, changing what every one of the fourteen ids
was measuring, silently. No id in the family reads `get wrCfg`-style settings or
records the station identity in its pass detail, so two runs are not comparable
after a settings change. **F-5.**

### 6.3 The leak that is not in WP-B's table: `_debugForceConnFail` (new cluster `C9`)

This is the package's headline finding and it is a firmware/harness interaction
no prior package could have seen.

`set wrDeadUrls N` does two things: it synthesises the station list **and** it
arms `_debugForceConnFail = true` (`webRadioApp.cpp:1055`). While that flag is
set, `_play()` short-circuits *before touching the network* —
`_state = WRPlayState::ERROR_UNREACHABLE; LOG_W("… forced connect-fail (debug
wrDeadUrls)"); _onPlaybackFailed(connectFail=true); return;`
(`webRadioApp.cpp:1325-1334`).

**The flag is cleared by exactly three writes**: `set wrDeadUrls 0`
(`:1034`), `set wrUrl <url>` (`:1008`), and nothing else. `init()` does **not**
clear it (`webRadioApp.cpp:20-60`), `suspend()`/`resume()` do not, an app switch
does not, and a fresh station fetch does not — the fetch replaces `_stations[]`
and `_stationCount` while the flag survives, so a board with a perfectly good
30-station list still fails every connect.

**`_vs_precondition_webradio` arms it and never disarms it.** `webradio.py:44`
issues `set wrDeadUrls 15` on the entry of all six PLEDIT ids, and no PLEDIT body
— and no helper, and no runner teardown — ever issues `set wrDeadUrls 0`. The
only two bodies that clear it are `T237` (`:950`) and `T276` (`:1049`), both in a
`finally`, and both run **later** in registry order.

**Predicted blast radius in a full `run/test`.** Registry order is
`T_PLE_WR_155`–`160`, `T_WR_EJECT_01`/`02`, `T_WR_ERR_01`–`04`,
`T_WR_COEX_01`/`02`/`04`, `T_WR_HEAP_01`–`04`, `T_WR_VOL_03`, `T_WR_VOL_CLAMP`,
`T237`, `T276`, … (`webradio.py:1551-1582`). So **every fetch-dependent id from
`T_WR_EJECT_02` through `T_WR_VOL_CLAMP` runs with connect forced to fail**, and
the tail (`T_WR_TLS_01`, `T_WR_SPOTIFY_RESUME_01`, `T_WR_VIS_01`–`05`) runs clean
because `T237`'s teardown disarmed it.

**This matches the declared flake signature exactly.** `flaky.yaml:72-93` and
`:95-108` declare `T_WR_COEX_01` and `T_WR_VOL_03` with the symptom
*"timeout — wrState=5 (expected 2/PLAYING after set wrPlay 0)"*. State 5 **is**
`ERROR_UNREACHABLE` — the state `_debugForceConnFail` assigns. TASK-540
investigated on five DUT runs, saw four different outcomes including PASS, could
not reproduce it as a firmware defect, and attributed it to radio-browser.info
station churn; the recurrence was *"in TASK-480's full-suite parity run"*
(`flaky.yaml:76-84`). An isolated `run/test-targeted T_WR_COEX_01` starts from a
cold boot with the flag clear and passes; a full-suite run arrives with it armed
and lands on state 5. That is the shape of a suite-order defect, not of network
churn, and it is precisely the case
`feedback_isolated_rerun_vs_suite_state` warns about.

`_order.py:241` records `T_WR_COEX_01` as `DISMISSED — "Station count from the
test's own fetch."` The dismissal is about the **count**, which the fetch does
restore. It does not consider the flag, which the fetch does not. Same for
`T_WR_VOL_03` (`:247`), `T_WR_TLS_01`, `T_WR_VIS_01`/`02`/`04` and
`T_WR_SPOTIFY_RESUME_01` (`:242-247`). Six dismissals resting on a premise that
covers half the mutation.

**Static reading cannot close this** — the flag is not readable from the host
(`get wrSkip` reports `autoSkip`, not `_debugForceConnFail`; `get wrState` shows
only the outcome), so the confirmation is a NEEDS-DUT (§11 #1) and the fix is one
line in a helper. Filed as **F-4 (P1)**, and proposed as WP-B §5.2 cluster
**C9 — forced connect-fail**.

---

## 7. The out-of-registry harnesses, graded as tests

Four standalone scripts carry WebRadio coverage that the registry does not.
WP-A **A-4** established that all four hand-roll their own `SerialDut` instead of
using `lib/dut.py`; this section answers the next question — **as tests, are they
sound?** Same four-value vocabulary, same evidence rule.

### 7.1 `test_adr045_gate.py` (`run/wr-gate`) — **WEAK**

The gate on which M-WEBRADIO was closed. 455 lines, dual-purpose: N cold-entry
trials scored against the ADR-045 bar, plus an outage-attribution pass that
classifies every failure window against link, LAN and WAN truth.

**The oracle, precisely.** Per trial: enter WebRadio via `switchApp`, `set wrPlay
0`, then poll `get wrPlaying` and `get wrSkip` every 2 s until
`wrPlaying.ms >= hold_secs * 1000` (60 s), with `cum_skips <= max_skips` (6)
(`test_adr045_gate.py:295-315`). The trial passes only on both.

**Does that distinguish "the stream played" from "the connection was attempted"?
Yes — and it is the only thing in this family that does.** `wrPlaying.ms` is
`millis() - _playingSinceMs` computed **only while `_state == PLAYING`**, and 0
otherwise (`webRadioApp.cpp:833-839`); `_playingSinceMs` is stamped on each entry
into PLAYING. And PLAYING is not a latch: the stream-liveness watchdog drops out
of it if the input buffer stops being read down for `WR_STREAM_DEAD_MS = 5000`
(`webRadioApp.h:56-65`), on a "no bytes consumed" test that the header explains
cannot be satisfied by chance. So `ms >= 60000` means **the decoder consumed
stream bytes continuously for a minute** — a genuinely sustained proxy, two rungs
above the registry's `wrState == 2`.

**What it still does not distinguish** is *what* was decoded. Nothing checks
`wrUnderruns`, `wrSpec` or any PCM-derived value, so sixty seconds of silence,
of a station's "this stream has moved" loop, or of a stream at the wrong bitrate
all score identically. The gate proves continuity, not content.

**Four defects that make it WEAK rather than SOUND.**

1. **Every trial plays the same station.** `run_trial` hardcodes `set wrPlay 0`
   (`:290`), and no trial reads `get wrStation 0` to record which station that
   is. The ADR-045 criterion is about cold entry *to the tuner*, whose skip term
   only means anything across a list; ten trials of index 0 sample one station
   ten times. This is why the recorded pass run has `skips=0` in **all ten**
   trials (`tasks-archive.md:3996-3998`) — the `<= 6` half of the bar had zero
   variance and was never exercised.
2. **It never verifies the firmware under test.** No ELF hash, no `get build`,
   no variant check — contrast `run/player-gate:454-486`, which hashes the binary
   actually on the device for each leg. The gate cannot tell you what it measured.
3. **The trial count is variable and grows on a bad network.** The extension rule
   (`:409-420`) adds trials while 1–2 outage windows have been captured, and the
   final rate is `passes / len(results)` (`:426-427`) — so the denominator of the
   90 % bar is decided by the network conditions during the run.
4. **A mid-run reboot does not fail the gate.** `RE_BOOT` (`:52`) feeds
   `boot_marks`, which is used **only** to mark an outage window
   `excluded-reboot` in the attribution table (`:264-266`); the boot count is
   never printed and never affects the verdict. A crash between trials is
   invisible. Two of the family's registry ids (`T_WR_HEAP_04`) and both player
   standalone scripts treat a reset as a hard failure.

**What it does well, and should be copied.** One reader thread owns RX and tees
every line host-timestamped to a log; `reset_input_buffer()` is never called
after startup, so async evidence is never destroyed (`:13-17`, `:74-108`) — the
architectural fix for the class of bug WP-C **C-19** and WP-E **E-10** keep
finding. The station-fetch preflight retries with a reboot and gives up loudly
rather than skipping (`:352-375`). And the ping pre-flight warns when LAN truth
is unreliable instead of silently mis-attributing (`:382-384`).

### 7.2 `test_webradio_soak.py` (`run/wr-soak`) — **SOUND**

**Verdict criteria** (`:295-300`): `cycles >= 3`, arena acquire/release balance
from **device-side counters**, zero acquire failures, and `min(lfbBefore) >=
24576` — i.e. the 24 KB arena stayed contiguous through every cycle.

Sound because every one of those terms is a device-computed value compared
against a firmware-derived bound, and because it defends its own measurement in
two ways other harnesses do not. It gates on `get arenaStats` deltas rather than
on counting `[membudget]` serial lines, with the reason recorded — the wire count
drops lines at `cmd()` boundaries and false-FAILed two healthy 30-minute soaks
(`:249-256`). And it detects a mid-soak reboot by comparing **device-elapsed
`upMs` against host-elapsed wall time** with 15 s of slack, because a reboot
resets the counters and would otherwise read as a clean 0/0 delta (`:264-277`) —
the most careful anti-false-pass reasoning in any harness in this repo. `24576`
is the arena size, not a magic number.

**The one thing a reader must not infer from a green run.** Despite the name and
`CLAUDE.md`'s "WebRadio playback + A-lite arena-churn soak", **playback is
measured and reported but never asserted**: `reached_playing`, `sustained`
seconds and `underruns` are printed, and the docstring says outright that this
*"quantif[ies] the TASK-233 'best-effort on no-PSRAM' claim instead of asserting
it"* (`:20-22`). A soak in which 0 of 200 cycles ever reached PLAYING passes,
provided the arena balanced. That is a defensible scope decision, stated in the
right place; it is also the reason a green `run/wr-soak` is not playback
evidence.

### 7.3 `webradio_long_soak.py` (no `run/` entry point) — **HOLLOW**

**It cannot fail.** `main()` runs to the end of the requested duration, counts
anomalies, writes a JSON report and returns — there is no `sys.exit(1)` on any
anomaly path and no verdict line (`:495-655`). The only non-zero exits are setup
failures (`:312`, `:396`, `:473`, `:493`). Anomalies — DUT silence, render
freeze, mechanism-stuck, an unexpected boot marker — increment a counter, write
`"status": "anomaly-in-progress"` into a report file, and the soak keeps running
(`:539-635`). Per rubric §2 that is HOLLOW: a run that observed a TASK-393
render freeze exits 0 exactly like a clean one.

**In fairness, it never claims otherwise** — the docstring calls it a
"recurrence watch", it has no `run/` entry, and nothing gates on it. As an
*instrument* it is excellent, and better engineered than most things here: two
independent detectors (heartbeat render-age plus an event-log mechanism check), a
DUT-silence watchdog, a single-station design argued from firmware behaviour
(`_stationCount == 1` disables the auto-skip branch so terminal-retry is the only
recovery path, `:5-14`), a continuous reader thread, and — the detail worth
citing — an independent VE review before first use that caught a **false-positive
gate**: `last_render_age_ms` climbs in lockstep with uptime during normal quiet
PLAYING too, so the detector was re-gated on the DUT being in a retryable error
state at the moment of the trip (`:565-576`). A detector that was fixed for
false-positives before it was ever trusted is rarer in this repo than one that
works.

**The finding is placement, not quality**: it sits in `app/tools/` under a
`test_*` name, alongside scripts whose exit code is a verdict, and it has none.
**F-12.**

### 7.4 `test_ae04_teardown.py` (`run/ae04`) — **SOUND**

The best-constructed test in this package's scope, registry or not.

**Per cycle it asserts nine things** (`:245-325`): WebRadio proves `STOPPED`
before injection; `arenaStats.active == 0` at baseline; `CONNECTING` reached
after `set wrUrl`; the pump proved alive while connecting; no crash/reboot
signature during teardown; no ack-timeout tripwire; the pump observed going
`alive → false` within the deadline; `worst_iter_ms <= max_block_ms` for
loopTask; a `wrpump: torn down (…)` line proving the teardown went through the
**pump's own** branch rather than synchronously on loopTask; `upMs` monotonic;
`active == 0` after; and `d_acq == d_rel == 1` exactly for this cycle.

Three properties put it above everything else audited:

* **Its bounds are derived from firmware constants with the derivation written
  down.** The teardown deadline is 16 s because `Audio::connecttohost()` forces
  `m_timeout_ms = 10000` for raw-IP hosts and the pump cannot observe the posted
  TEARDOWN until that returns (`:31-43`, `:337-341`); the 180 ms loopTask bound
  is the measured 103 ms app-switch repaint cost plus margin, replacing
  `T_AE_04`'s literal 100 ms criterion which false-positives on it (`:329-333`).
  Both are `--flag`s with the reasoning in the help text.
* **A failed precondition is reported as `SETUP`, never as an invariant
  failure**, and the docstring explains the incident that forced it: one late
  teardown left `_state` stale-CONNECTING, `_play()`'s CONNECTING guard then
  no-oped every later injection, and cycles 3–10 failed identically — "worse and
  monotonic, not flaky" (`:44-53`). Distinguishing "the harness could not set up
  the experiment" from "the firmware broke the invariant" is what the rubric's
  §1 question needs and almost nothing else in the repo does.
* **It is a negative-tested rework of a harness that previously could not render
  a verdict at all**, with all three prior defects named, root-caused and fixed
  (`:22-58`).

Two small costs. `T_AE_04` has **no registry entry** (WP-B **B-13**;
`test_plan.md:497` records that `T_AE_01`–`03` have no id-labelled body
anywhere), so this coverage exists only if someone remembers to run
`./run/ae04`. And the `INCONCLUSIVE` verdict line prints while `main()` still
returns 1 (`:376-381`), so a caller sees a FAIL where the script says no verdict
was rendered — safe in the conservative direction, but the two disagree.

---

## 8. What the M-WEBRADIO close actually proved

M-WEBRADIO was closed on `test_adr045_gate.py`'s gate run 5 — 10/10 PASS,
2026-07-02 17:55–18:35 (`tasks-archive.md:3996-4006`). In plain English, here is
what that run established and what it did not.

**What it proved.** On a board flashed with `cyd2usb_webradio` — the
Spotify-disabled build, which `run/wr-gate:15` selects deliberately — WebRadio
entered from the Spotify slot ten times in a row, connected to station index 0,
and held the PLAYING state for more than sixty seconds each time, with the
stream-liveness watchdog armed throughout. Because that watchdog drops PLAYING
within five seconds of the input buffer ceasing to be consumed
(`webRadioApp.h:56-65`), the ten holds are real evidence that the decoder was
pulling bytes off a live stream for a minute at a time. In the same window there
was one link event and zero outage windows, and the WiFi disconnect delta was
zero on every trial. That is a genuine result and a better-instrumented one than
most milestone gates in this project.

**What it did not prove.**

* **Not on the shipped firmware.** The gate flashes `cyd2usb_webradio`
  (`-DDISABLE_SPOTIFY -DWEBRADIO_ONLY`). Production is `cyd2usb_winamp`, where
  `spotifyTask` is a continuous competing TLS user — the exact contention that
  `tlsYield()`, `T_WR_SPOTIFY_RESUME_01` and five subsequent tasks
  (TASK-277/287/289/293/295) exist because of. The build was chosen for a good
  reason (TASK-243's 403 starves the station fetch), and the choice is recorded;
  it still means the number was taken on a binary no user runs.
* **The skip half of the criterion was never exercised.** ADR-045's bar is
  "stable PLAYING within **≤ 6 auto-skips**". All ten trials recorded `skips=0`
  (`tasks-archive.md:3996`), because every trial played the same station and it
  connected in ~0.1 s. The gate scored 10/10 against a two-term criterion of
  which only one term had any variance. The immediately preceding run 4 — the
  same evening — scored 7/10, and its three failures were precisely the
  outage-skip cases the ≤ 6 term is about; the archive records that run 4's bar
  "conflates dead-station skips with outage skips" and that the disposition was
  to re-run in a clean window and score that (`:3987-3994`).
* **One station, not the tuner.** Index 0 only, never identified, never varied,
  and dependent on whatever `bitrateCap`/country the settings held that evening
  (§6.2). The criterion is about the feature's behaviour across a station list.
* **The measurement may have perturbed the thing measured.** The archive records
  this honestly: the harness's 1 Hz host ping doubles as a link keepalive and may
  have suppressed the AP idle-kick that produced run 4's failures
  (`:4000-4003`, LL-093).
* **Nothing about the audio.** No underrun, spectrum or PCM-derived value is
  read; a minute of silence scores as a minute of playing.
* **Nothing about a crash.** A reboot mid-run only annotates the attribution
  table (§7.1 defect 4).

**The two-sentence version.** The 10/10 proved that a Spotify-disabled build,
entering WebRadio ten times in one clean-RF forty-minute window, connected to one
station and kept the decoder consuming bytes for over a minute each time — a
real continuity result on a real device, and the one place in this family where
"it played" is more than a state byte. It did not prove the auto-skip bound that
is half of ADR-045's criterion (every trial skipped zero times), did not run on
the firmware that ships, did not sample the station list, and said nothing about
what the audio actually contained.

---

## 9. Family findings

Severity per rubric §4.3: **P1** the test is counted as coverage but provides
none (or a documented entry point does not work); **P2** materially weaker than
claimed; **P3** hygiene.

### 9.1 The test does not prove its subject — S3 / S4 / S2

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **F-1** | **P1** | **The shared `T_WR_ERR_*` teardown writes the wrong enum value of the enum under test.** `_wr_err_test`'s `finally` issues `dut.cmd("set wrState 3")` commented *"back to STOPPED (quiescent)"*. `STOPPED` is **0**; **3 is `ERROR_WIFI`**. Consequences: `T_WR_ERR_03`, whose subject *is* state 3, "restores" by re-writing the value it just injected, so it is **BROKEN**; and all four ids exit leaving the app parked in an error state rather than quiescent — into a registry order where the next six ids' oracle is `wrState == 2`. | `webradio.py:511-513`; `webRadioApp.h:36-44`; `webRadioApp.cpp:954-960` | One character: `set wrState 0`. Then re-check whether `T_WR_ERR_03` still needs a distinct restore value from the state it injects. |
| **F-3** | **P1** | **All four `T_WR_ERR_*` are round-trips through a single byte, with the actual subject handed to a human.** `set wrState <n>` assigns `_state` and `get wrState` prints `(int)_state` — one member, no intervening behaviour — and `dbgSet` returns `true` for any input, so the `ok` check proves nothing either. Every pass detail then names the thing not asserted: `"(visual: 'Station blocked')"`, `"(visual: 'WiFi lost')"`, `"(visual: 'Connecting…', POSBAR empty)"`. Four registry slots asserting that the debug injector works. The distinguishing behaviours all have observables: `hasTerminalError()`'s membership (`webRadioApp.h:227-230`), ERROR_BLOCKED's exclusion from the terminal retry (`webRadioApp.cpp:316`), and `get wrPosbar.bufPctDrawn` for `T_WR_ERR_04`'s POSBAR claim (`:869-882`). | `webradio.py:502-510`, `:522`, `:531`, `:540`, `:554`; `webRadioApp.cpp:716-720`, `:954-960` | Keep one id as the injector fixture check; re-point the other three at a behaviour each — banner/`isRunning()`/retry-eligibility — using the getters that already exist. |
| **F-7** | **P1** | **`T_WR_VOL_03` claims a volume behaviour and reads no volume.** Its only oracle is `wrState == 2`; the pass string argues the conclusion instead of asserting it (*"confirmed **structurally**: `_play()` always calls `setVolume(webRadioMaxVolume)`"*, plus *"audible clipping … requires human listener"*). The oracle exists and its own neighbour uses it (`get wrEffectiveVol`, `get wrVolPct`). Worse, its premise may never hold: `set wrVol 21` issued immediately after `set wrStop 1` hits the no-live-session branch, which logs *"vol set=%d — no active session, not applied"* and stores without applying, so the id can pass having never injected the value it exists to see overridden. | `webradio.py:789-806`; `webRadioApp.cpp:775-790`, `:1104-1116` | Assert `get wrVolPct.scaled == wrEffectiveVolume()` after the play, and inject the bypass value while a session exists (or drop the injection and assert the clamp only). |

### 9.2 State leakage — S14 (30 of 30 rows)

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **F-4** | **P1** | **New leakage cluster `C9` — `_debugForceConnFail`, and it is the likeliest cause of two declared "network" flakes.** `set wrDeadUrls 15` arms a flag that makes every later `_play()` short-circuit to `ERROR_UNREACHABLE` without touching the network. It is cleared **only** by `set wrDeadUrls 0` or `set wrUrl` — not by `init()`, not by an app switch, not by a fresh station fetch. `_vs_precondition_webradio` arms it on all six PLEDIT entries and never disarms it; the first bodies that clear it are `T237`/`T276`, eleven ids later. So `T_WR_EJECT_02` … `T_WR_VOL_CLAMP` are predicted to run with connect forced to fail — and `flaky.yaml` declares `T_WR_COEX_01` and `T_WR_VOL_03` with the symptom *"wrState=5 (expected 2/PLAYING)"*, where **5 is exactly the state the flag assigns**, recurring in a full-suite run while isolated reruns pass. `_order.py` dismisses six WebRadio ids' order-dependence on the grounds that the station **count** comes from the test's own fetch — true, and orthogonal to the flag. | `webradio.py:44` (armed, never cleared) vs `:950`, `:1049`; `webRadioApp.cpp:1031-1055`, `:1008`, `:1325-1334`, `:20-60`; `flaky.yaml:72-93`, `:95-108`; `_order.py:241-247`; §6.3 | Add `set wrDeadUrls 0` to a `finally` in `_vs_precondition_webradio`'s callers (or make the six PLEDIT bodies share a context manager). Then re-open TASK-540 with the order hypothesis rather than the network one, and re-word the six `_order.py` dismissals. |
| **F-9** | **P3** | **Only four of thirty bodies restore anything, and only three use a `finally`.** `T_WR_EJECT_02` restores Spotify on every path (`:458`, `:462`, `:468`, `:477`); `T_WR_VOL_CLAMP`, `T237` and `T276` restore in `finally` blocks. The other 26 leave some combination of: 15 synthetic dead stations, the forced-fail flag (**F-4**), an injected `wrState`, a moved `wrIdx`, a changed `visMode`, a held drag, and `bgPoll` written with a bare `set bgPoll 0`/`1` pair rather than `_bgpoll_suspended` — which is imported into this module and used by exactly one body. | `webradio.py:860-865`, `:949-954`, `:1048-1053`, `:1232`; `_helpers.py:444-454`; the S14 column in §1–§5 | A `_webradio_state_restored()` context manager alongside `_bgpoll_suspended`, restoring dead-URL hook, state, index and vis mode; and replace every bare `set bgPoll 0` with the existing manager. |

### 9.3 Oracles narrower than the claim — S8 / S2 / S6

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **F-10** | **P2** | **`T_WR_COEX_02` asserts a disjunction where its claim is a conjunction, and `T_WR_COEX_04` measures the wrong quantity.** `not (idx1 == idx0 and idx2 == idx1)` passes when only one of NEXT/PREV works, and a NEXT/PREV pair wired to the same handler passes outright; the expected values (`(idx0+1) % count`, then `idx0`) are trivially computable. `T_WR_COEX_04`'s "touch latency" is the host→device serial round trip for a `tap` command, against a 500 ms bound roughly an order of magnitude above the routine cost, and `dut.read_json` may return an unrelated async reply. | `webradio.py:605-608`; `:619-636` | `T_WR_COEX_02`: assert both indices exactly. `T_WR_COEX_04`: either retire it (a near-hang is already `T_WR_HEAP_04`'s subject) or re-point it at a device-side measure such as `get perf`'s worst iteration. |
| **F-14** | **P2** | **`T_WR_VIS_01`'s "isolated measurement" isolates the read, not the measurement.** `s_wrPumpMaxPumpMs` is zeroed only inside `wrEnsurePumpTask()` *after* its `if (s_wrPumpTask) return;` early exit, so it is a high-water mark for the life of the pump task — which survives station changes and every other test in the run. In a full `run/test` the 50 ms decode-tail ceiling is being applied to the worst pump cycle since boot, including spikes caused by the earlier `HEAP` drains and screendumps the docstring is at pains to exclude. | `webradio.py:1352-1383`; `audio/audioEngine.cpp:398-409`, `:381` | Add a `set wrPumpReset`-style zeroing command (or read `cycles`/`maxPumpMs` as a delta across the 45 s window) so the ceiling applies to the window the test names. |
| **F-15** | **P2** | **Two negative VIS assertions cannot fail for the reason they exist.** `T_WR_VIS_02`'s Atlas negative control — the half that makes the claim "**only** in the mode that reads it" — is a `print("WARNING … not failing on this alone")`, not an assertion, so Atlas beginning to animate cannot fail the id. `T_WR_VIS_05` compares `m != 4` where `_get_vis_mode` returns `None` on a failed read, so a board that stopped answering `get visMode` passes six times and reports `visited [None]`; and nothing asserts the cycle moved at all, so a no-op `nextMode()` also passes. | `webradio.py:1408-1410`; `:1533-1547`; `_helpers.py:110-119` | `T_WR_VIS_02`: fail on `atlas_delta > 500` (or state a measured bound and enforce it). `T_WR_VIS_05`: fail on a `None` read, and assert `seen == {0, 3, 1, 2}` positively — `seen` is already collected and printed. |
| **F-19** | **P2** | **`run/wr-gate` cannot say what firmware it measured, and its denominator moves.** No ELF hash, no `get build`, no variant check — unlike `run/player-gate`, which hashes the binary on the device per leg. The pass rate is `passes / len(results)` while the extension rule adds trials whenever 1–2 outage windows have been captured, so the sample size of the 90 % bar is decided by the network during the run. And `RE_BOOT` feeds only the attribution table: a mid-run reboot is never counted, never printed and never affects the verdict. | `test_adr045_gate.py:52`, `:264-266`, `:409-427`; `run/player-gate:454-486` | Add a build/ELF assertion at start-up, print `len(boot_marks)` in the summary and fail on any, and fix the denominator (score the first `--trials` trials; report extensions separately). |
| **F-20** | **P2** | **The ADR-045 criterion's skip term was structurally unexercisable by the gate that closed it.** `run_trial` hardcodes `set wrPlay 0` for every trial and never records which station that is, so the "≤ 6 auto-skips" half had zero variance — all ten scored trials reported `skips=0`. The criterion is about cold entry to a tuner across a station list; the gate sampled one station ten times. | `test_adr045_gate.py:283-321`; `tasks-archive.md:3996-3998`, `:3987-3994`; §8 | Randomise or sweep the trial's station index, log `get wrStation <idx>` per trial, and re-run — on `cyd2usb_winamp` as well as `cyd2usb_webradio`. |

### 9.4 Records, scope and entry paths — S12 / S7

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **F-2** | **P2** | **`T237` and `T276` collide with two unrelated `test_plan.md` entries.** The plan declares `### T237 — [app-settings-wire-001] Crypto currency change updates app state` and `### T276 — [M-WEBRADIO-PREVIEW] Skin base layer loaded from gen/skin_preview.png`; the only bodies carrying those ids are WebRadio's auto-skip-bound and terminal-retry tests, and the archive confirms the WebRadio meaning is the live one. Any coverage claim citing either id is ambiguous, and the plan's two headings are bound C6 doc entries pointing at bodies that do not implement them. | `test_plan.md:4188`, `:4537`; `webradio.py:875`, `:959`; `tasks-archive.md:3953-3957`, `:14374-14384` | Re-id the WebRadio pair into the `T_WR_*` namespace (`T_WR_SKIP_01`, `T_WR_RETRY_01`) and record the rename, or retire the two colliding plan headings — an Architect/VE call, not a code change. |
| **F-6** | **P2** | **`_ensure_webradio` enters through a taskbar slot WebRadio does not have, and the module's own header says so.** `_switch_to(dut, "WebRadio")` taps `tap_taskbar_slot(APP_SLOT["WebRadio"])` → slot 11 → `appIdx = 11 % 11 = 0`, the player slot; it lands on WebRadio only when the board is already on a player-mode app so `resolvePlayerTap` takes the cycle branch. `webradio.py:30-33` warns against exactly this helper and names `_switch_to_webradio_capture_heap` as the correct entry — which every other body in the file uses. `T_WR_ERR_04` is the one that does not. Same defect WP-E filed as **E-11** for `T_PLR_18`. | `webradio.py:298-306`, `:548`; `_helpers.py:321-331`, `:400`; `coords.py:184-188`; `cmdTouch.cpp:29-33`; `appShell.cpp:76-86` | Point `_ensure_webradio` at `_switch_to_webradio_capture_heap` and delete the `_switch_to` path, or delete the helper — it has one caller. |
| **F-8** | **P2** | **All three flake declarations and call sites in this family are mismatched, in both directions — a third instance of WP-C C-7.** `flaky.yaml:72` declares `T_WR_COEX_01` and `:95` declares `T_WR_VOL_03`, and **neither body ever calls `flake()`** — both `fail()` — so `run_with_flake_retry` never fires and the mandated retry never happens. Conversely `T_WR_EJECT_01` **does** call `flake()` and is **not** declared, so `lib/results.flake()` rewrites it to `FAIL: UNDECLARED flake — no entry for T_WR_EJECT_01 …`: a bookkeeping failure message on a TLS assertion. `T_WR_TLS_01` sits in `candidates:`, which is not a declaration. | `flaky.yaml:72-108`, `:159-161`; `webradio.py:429` (the module's only `flake()`); `lib/results.py:175-199`, `:205-233` | Make the two declared ids' failure paths call `flake()` (or delete the declarations — and see **F-4** first, since the declared root cause is probably wrong), and declare `T_WR_EJECT_01` or convert it to `fail()`. |
| **F-11** | **P2** | **`T_WR_VIS_03` and `T_WR_VIS_05` drive Spotify end to end and are scoped `WebRadio`.** Both are Spotify regression guards (the synthetic VU path; Spotify's tap-cycle never reaching SPECTRUM), and both carry the module-seeded `scope=WebRadio` — no `@meta(...)` appears anywhere in this file. `./run/test-targeted --scope Spotify` therefore misses both. The mechanism exists and is used two modules away (`player.py:1750`, `:1757`). WebRadio instance of WP-E **E-5**. | §0's command output; `webradio.py:1431-1466`, `:1516-1547`; `_meta.py:22`; `player.py:1750` | `@meta(scope="Spotify", scope_reason="cross-mode")` on both. |
| **F-5** | **P2** | **Fourteen ids select station index 0 and none of them records what station that was.** `get wrStation <idx>` returns name, bitrate and URL and is called by **no** suite file; nor does anything read the country/`bitrateCap` settings that decide the list's content — the cap is a server-side `&bitrateMax=` query parameter, so changing it changes which stations exist at all. Combined with TASK-284 truncation (a 1-station list passes every `count >= 1` gate a 30-station list passes, and `T_WR_TLS_01` annotates truncation into its pass string rather than failing), two runs of this family are not comparable across a settings change, silently. | `webRadioApp.cpp:729-744`; `dataTaskStorage.cpp:1043-1058`; `webradio.py:1174`; no hits for `wrStation`/`bitrateCap` under `app/tools/suite/` | Log `get wrStation 0` (name + bitrate) and the configured cap/country into every fetch-dependent id's pass detail, so a result carries the population it was measured on. |
| **F-12** | **P3** | **`webradio_long_soak.py` is an instrument filed as a test and can never fail.** No verdict line and no non-zero exit on any anomaly path — DUT silence, render freeze, mechanism-stuck and an unexpected boot marker all just increment a counter and write a JSON report while the soak continues. It has no `run/` entry point, so nothing schedules it; but it sits in `app/tools/` under a `test_*` name beside scripts whose exit code *is* the verdict. | `webradio_long_soak.py:495-655`; §7.3 | Rename it out of the `test_*` namespace (`probe/` per M-TOOLING, or `wr_recurrence_watch.py`), or give it an exit code and a `run/` entry so its anomalies gate something. |

### 9.5 Hygiene — S10 / S11 / S13

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **F-16** | **P3** | **Three firmware constants are mirrored as literals (LL-114: parse, don't mirror), one with an already-stale cite.** `19` for `vu::SPEC_BARS` (`vuMeter.h:50`) in `T_WR_VIS_04`'s length check — a build with a different bar count fails as "bad wrSpec response(s)" rather than as itself; `12`/`21` for `WR_VOLUME_SOFT_CAP_STOCK`/`WR_VOLUME_MAX` (`audio/audioEngine.h:62,70`) eight times over in `T_WR_VOL_CLAMP`; and `WR_TERMINAL_RETRY_MS = 30000  # webRadioApp.h:69 — keep in sync if that constant moves` in `T276`, where the constant is now at `webRadioApp.h:73`. | `webradio.py:1504`, `:837-846`, `:989`; `vuMeter.h:50`; `audio/audioEngine.h:62,70`; `webRadioApp.h:73` | Parse the three from the headers the way `coords.py` parses `gen/skin_layout.h`; at minimum, fix the stale line cite. |
| **F-17** | **P3** | **`T_PLE_WR_158` is `T_PLE_WR_157` with a weaker bound** — identical precondition, identical `hold`/`tick 50 20`/`release` sequence, identical oracle field, `>= 1` instead of `1 <= so <= 3`, and it drops the `D_PLEDIT_SCROLL` liveness check its predecessor makes. Two full preconditions (each re-arming `set wrDeadUrls 15` plus five reset drags) for one assertion. WP-D **D-13**'s WebRadio instance. | `webradio.py:161-182` vs `:130-151` | Fold into `T_PLE_WR_157` and `resv` the id, or give it a distinct integration window (`tick 100 20`, `>= 3`) so the pair brackets the velocity curve. |
| **F-18** | **P3** | **Uncited thresholds throughout.** `30_000` (twice) and `40_000` heap floors with no `mem_manifest.yaml` entry; `500` for the Atlas warning; `220` for the cooldown split (inherited from `T156`); `45.0` settle and `50` ceiling in `T_WR_VIS_01` (the latter at least attributed to TASK-278); `N=4`/`N=3`, the 12 s saturation deadline and the 1.5 s no-loop window in `T237`/`T276` — the last being one `WR_SKIP_PACE_MS` interval, so a slow runaway could pass it. | `webradio.py:667`, `:710`, `:745`, `:1408`, `:111`, `:1365`, `:1380`, `:895`, `:908`, `:921`, `:1000`; `webRadioApp.h:72` | Cite each to a firmware constant or a dated measurement, and widen `T237`'s no-loop window past `WR_SKIP_PACE_MS`. |
| **F-13** | **P3** | **A stale comment in the VIS header.** *"VIS_WAVE is still dead — unreachable via `nextMode()` — and reads back -1"*; `cmdGet.cpp:484` maps `VIS_WAVE → 5`, and −1 is now only the unreachable default. No oracle depends on it. | `webradio.py:1267`; `cmdGet.cpp:477-487` | One-line correction. |

---

## 10. Counts

### 10.1 The 30 registry ids

| Verdict | PLEDIT (6) | Eject/Err (6) | Coex/Heap/Vol (9) | Skip/Retry (2) | TLS/Resume/VIS (7) | **Total** |
|---|---|---|---|---|---|---|
| SOUND | 5 | 2 | 4 | 1 | 3 | **15** |
| WEAK | 1 | 0 | 4 | 1 | 4 | **10** |
| HOLLOW | 0 | 3 | 1 | 0 | 0 | **4** |
| BROKEN | 0 | 1 | 0 | 0 | 0 | **1** |
| **total** | **6** | **6** | **9** | **2** | **7** | **30** |

* **HOLLOW:** `T_WR_ERR_01`, `T_WR_ERR_02`, `T_WR_ERR_04`, `T_WR_VOL_03`.
* **BROKEN:** `T_WR_ERR_03`.
* **WEAK:** `T_PLE_WR_158`, `T_WR_COEX_01`, `T_WR_COEX_02`, `T_WR_COEX_04`,
  `T_WR_HEAP_04`, `T276`, `T_WR_VIS_01`, `T_WR_VIS_02`, `T_WR_VIS_03`,
  `T_WR_VIS_05`.

**50 % SOUND** — below WP-E's 77 %, below WP-C's 59 % and WP-D's 56 %, and the
worst per-test result in the review so far. Four of the five non-SOUND-verdict
clusters are one shared helper each (`_wr_err_test`, `_webradio_enter_with_stations`,
`_vis_pixel_delta`, `_cycle_vis_to`), which is why the fixes are small relative
to the verdict count.

### 10.2 The four out-of-registry harnesses (§7), counted separately

| Verdict | Harness |
|---|---|
| SOUND | `test_webradio_soak.py` (`run/wr-soak`), `test_ae04_teardown.py` (`run/ae04`) |
| WEAK | `test_adr045_gate.py` (`run/wr-gate`) |
| HOLLOW | `webradio_long_soak.py` (no `run/` entry) |
| BROKEN | — |

Worth stating plainly: **the two best-engineered tests in this package's whole
scope are both outside the registry** (`test_ae04_teardown.py` and
`test_webradio_soak.py`), and one of them carries an id — `T_AE_04` — that has no
registry entry at all (WP-B **B-13**, `test_plan.md:497`).

### 10.3 Smell histogram

105 occurrences across the 30 rows (a row may carry several).

| Code | Smell | Count |
|---|---|---|
| S14 | State leakage | **30** |
| S7 | Skip-as-pass | 13 |
| S10 | Magic value | 12 |
| S8 | Vacuous bound | 10 |
| S13 | Overlap | 10 |
| S2 | Ack-not-effect | 9 |
| S4 | Deferred to a human | 5 |
| S3 | Tautology | 4 |
| S9 | Fixed-sleep synchronisation | 3 |
| S11 | Double bookkeeping | 3 |
| S12 | Wrong-id / mis-scoped record | 3 |
| S5 | Swallowed failure | 2 |
| S6 | Defaulting oracle | 1 |
| S1 | Unconditional pass | 0 |

Four things in that distribution are properties of this family rather than of
the sample.

* **S14 is 30 of 30 — every single row.** No other family has been unanimous on
  any smell. It is not laxity in one place: the family has an unusually rich
  mutable surface (`wrState`, `wrIdx`, `wrDeadUrls` + its forced-fail flag,
  `wrAutoSkip`, `wrVol`/`wrMaxVol`/`wrHwMod`, `visMode`, `bgPoll`, the drag
  state), and only four bodies restore anything. WP-E's headline was *a test
  that leaves the board changed*; this family is that failure mode taken to its
  limit, and **F-4** is what it costs — a leaked flag that plausibly explains two
  flake declarations blamed on the network for a year.
* **S3 + S4 = 9, the highest in the review.** WP-C's and WP-D's problem was
  tests that do not run; this family's second problem is tests that run and
  assert their own input, then name the real subject in the pass string. All
  five S4 rows say so out loud ("visual:", "requires human listener"), which
  makes them easy to find and easy to fix.
* **S1 is zero and S6 is one.** Defaults in this family are overwhelmingly in
  the *safe* direction — `remainingMs, 9999`, `offset, -1`, `accum, -1.0`,
  `tried, -1`, `state, -1` all fail rather than pass. Whoever wrote these knew
  the failure mode; the gap is what they chose to compare, not how.
* **S7 is 13, and unlike WP-E's the skips are not fixture preconditions but
  network ones** — a station list this rig cannot guarantee (TASK-284/TASK-540)
  and a Spotify account it does not have (TASK-243). There is no `run/wr-gate`
  equivalent of `run/player-gate`'s pass set, so a SKIP here is silent in every
  entry point.

---

## 11. NEEDS-DUT

Static reading cannot settle these. Each is stated as the question hardware
would answer, with the prediction that would confirm or refute it.

1. **F-4 — is `_debugForceConnFail` actually armed when `T_WR_COEX_01` runs?**
   The flag is not readable from the host, so the observable is the firmware's
   own `LOG_W "play idx=%u — forced connect-fail (debug wrDeadUrls)"`
   (`webRadioApp.cpp:1329`). Run `./run/test-targeted --scope WebRadio` with a
   serial capture and grep between `T_PLE_WR_160` and `T237`. **Prediction:** the
   line appears for every `set wrPlay` in that span, and `T_WR_COEX_01`/
   `T_WR_VOL_03` fail with `wrState=5`. If it does, TASK-540's network
   attribution is wrong and the two `flaky.yaml` entries should be withdrawn.
2. **F-4 (b) — does the order split reproduce?** `./run/test-targeted
   T_WR_COEX_01` from a cold boot versus the same id inside the full family run.
   **Prediction:** isolated PASS, in-family FAIL at state 5 — the signature
   `feedback_isolated_rerun_vs_suite_state` describes, and the exact pattern
   TASK-540 recorded without attributing it to order.
3. **F-6 — does `T_WR_ERR_04` reach WebRadio when run alone?**
   `./run/test-targeted T_WR_ERR_04` from a cold boot (board on Spotify,
   `playerMode` whatever boot restored). **Prediction:** `_switch_to("WebRadio")`
   restores the persisted mode instead of cycling and the id skips — meaning it
   has never been independently verifiable.
4. **F-5 — what is station index 0, and does the cap change the verdicts?**
   `get wrStation 0` (name/bitrate/url) at `bitrateCap = 192` (the DUT's current
   value) and again at 96 (the firmware default), with `get wrCount` alongside.
   The question is whether the fourteen fetch-dependent ids are measuring the
   same population across a settings change, and whether a cap ≤ 96 empties the
   list far enough to turn the block into skips.
5. **F-14 — is `T_WR_VIS_01`'s `maxPumpMs` contaminated by earlier ids?**
   Read `get wrPump` immediately before `T_WR_VIS_01` in a full run and again
   after its 45 s window. **Prediction:** the two `maxPumpMs` values are equal
   and both predate the window — i.e. the 50 ms ceiling was never applied to the
   period the test names.
6. **`T_WR_HEAP_04` — was the 2-minute window actually playback?** Read
   `get wrPlaying.ms` at the end of its 120 s watch. **Prediction (open):** if
   `ms < 120000` on any run, the id has been passing on an idle window and needs
   the liveness assertion added.
7. **Are `T_WR_VIS_03` and `T_WR_VIS_05` permanent SKIPs on this rig?** Both gate
   on `info.isPlaying`, which TASK-243 makes permanently false. Confirm from one
   full-suite result set, and if so record them the way WP-D recorded the twelve
   Spotify ids — coverage absent, not coverage passing.
8. **F-19/F-20 — re-run `run/wr-gate` with the two defects closed.** Vary the
   station index per trial and run once on `cyd2usb_webradio` and once on
   `cyd2usb_winamp` (Spotify enabled). The question that has never been asked is
   whether ADR-045's bar holds on the firmware that ships, and whether the ≤ 6
   skip term is met when it can actually be exercised. **This is the only item in
   this list that could change a milestone's status**, and it needs a PM/Architect
   ruling before it is run, not a VE decision.
9. **`T_PLE_WR_156`'s cooldown read.** WP-C **C-18**: `get cooldown` and
   `get shellCooldown` return the same `remainingMs` field name, and `Dut.cmd`
   issues `get shellCooldown` before every tap and drag with nothing correlating
   request to reply. Does the `<= 220` comparison ever read the shell's value
   instead of winampDisplay's? One instrumented run answers it for `T156` and
   `T_PLE_WR_156` together.

---

## 12. Handover

* Findings that belong to WP-Z's consolidation rather than to this family:
  **F-4** (a new state-leakage cluster `C9` for WP-B §5.2, with two standing
  flake declarations and six `_order.py` dismissals resting on it), **F-8** (the
  flaky-declaration/call-site mismatch, a third instance of WP-C **C-7** and the
  second in both directions after WP-E **E-3**), **F-2** (two registry ids
  colliding with unrelated plan entries — a `test_plan.md` ownership question),
  and **F-19**/**F-20** (a milestone closed on a gate that could not exercise
  half its own criterion, on a build that does not ship).
* Cross-references to prior packages, cited not re-derived: **F-6** is WP-E
  **E-11**'s helper, one module over; **F-11** is WP-E **E-5**; **F-17** is
  WP-D **D-13**; **F-8** extends WP-C **C-7**; `T_PLE_WR_156`'s cooldown
  exposure is WP-C **C-18**; the four `_switch_to`-vs-`resolvePlayerTap`
  arithmetic facts are WP-E §1(a); `T_AE_04`'s missing registry entry is WP-B
  **B-13**; the four hand-rolled `SerialDut`s are WP-A **A-4**, and §7 answers
  the question A-4 left open.
* The structural contrast worth carrying forward. WP-C: *a failure that does not
  block*. WP-D: *a test that does not run*. WP-E: *a test that leaves the board
  changed*. WP-F: **a test that measures a proxy and a harness that leaves the
  proxy armed** — the family cannot hear, so it asserts a state byte; and one
  helper leaves the firmware in a mode where that byte is forced to the failing
  value for eleven ids, which the project has spent a year attributing to the
  network. The two best tests in scope are outside the registry, and the
  milestone gate is the only thing in the family that asserts *sustained*
  playback.
* Nothing under `app/` or `run/` was modified. Nothing under `app/tools/` was
  imported except `suite.serialdbg.build_all_meta`. `./run/check-docs` was run
  once before handover; the C6 result is recorded in the index ledger entry for
  this package.
