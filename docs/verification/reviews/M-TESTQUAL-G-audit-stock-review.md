# M-TESTQUAL WP-G — the Stock family, audited per test

> Owner: **Verification Engineer**
> Status: done
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Prior packages: [WP-A harness](M-TESTQUAL-A-harness-review.md), [WP-B taxonomy](M-TESTQUAL-B-taxonomy-review.md), [WP-C gating classes](M-TESTQUAL-C-audit-core-review.md), [WP-D shell FEATURE](M-TESTQUAL-D-audit-shell-review.md), [WP-E player](M-TESTQUAL-E-audit-player-review.md), [WP-F webradio](M-TESTQUAL-F-audit-webradio-review.md)

---

## 0. Scope, and how the corpus was measured

Every id whose body lives in `app/tools/suite/serialdbg/stock.py`.

```sh
cd app/tools && python3 -c "import sys;sys.path.insert(0,'.')
from suite.serialdbg import build_all_meta
m=build_all_meta()
for t,v in m.items():
    if v['module']=='stock': print(t, v['cls'], v['scope'], v['effect'])"
# -> 30 ids. All cls=FEATURE, all scope=Stock, all effect=mutating.
```

**The index's §3 row says "40 ids". It is 30**, and the module's own `TESTS`
dict confirms it (`stock.py:1464-1495`, 30 entries). §3's row is corrected in
this package's index edit; the rollup uses 30. The "40" appears to have come
from WP-B's C1 row, which counts *callers of `_switch_to_stock`* — the 30
Stock ids plus the six CORE Stock drivers in `shell.py` plus their helpers —
not the module's registry.

The taxonomy is **100 % module-seeded**: not one `@meta(...)` declaration
appears in the file (`grep -n "@meta" stock.py` → no hits), so every
`(cls, scope, effect)` triple is `_meta.py`'s inference from the module name
(`_meta.py:29-33`). That matters once below: `T182` is a declared
cross-feature test against `stock-001` **and** `taskbar-scroll-001`
(`test_plan.md:1936`) whose body drives the taskbar drag/slot arithmetic, and
it is scoped `Stock`, so `./run/test-targeted --scope taskbar` misses it
(**G-13**, the Stock instance of WP-E **E-5** / WP-F **F-11**).

Static audit only, per rubric §5: no flash, no `run/test*`, no serial port.
The board is pinned to the `-DBOD_WATCH` debug build for TASK-557.
`build_all_tests`/`build_all_meta` were the only imports made under
`app/tools/` (rubric §5 / amendment A1); `stock.py`, `_helpers.py`,
`_meta.py`, `_order.py`, `coords.py`, `app_ids_gen.py`, `lib/dut.py`,
`lib/results.py`, `flaky.yaml`, `test_plan.md`, and the firmware under
`app/src/stock/`, `app/src/appShell.cpp`, `app/src/settingsStorage.cpp` and
`app/src/debug/serialConsole/` were **read**, never imported or executed.

Per amendment A2 the per-test tables put the **body location in column one**
and the id in column two, and no section is headed with a bare id.

### 0.1 What is distinctive about this corpus

1. **It is the suite's single largest source of order dependence, and this
   package found a second mechanism nobody had catalogued.** WP-B's cluster
   **C1** is `_switch_to_stock` writing `set stockMode 0` on every entry with
   `_restore_from_stock` restoring the app only (**B-5**). That one is real
   and §6.1 traces it precisely. But the damaging leak is a different one:
   `set triggerHeatmap 1` assigns `_s.prevSubView = _s.subView`
   (`stockApp.cpp:248`), `T196` issues it without normalising the sub-view
   first, and its predecessor `T204` exits in **chart** view — which makes
   `prevSubView == ChartDetail`, a state `backToPrevView()` cannot leave
   (`stockApp.cpp:312-321`). The back button becomes a fixed point and the
   **whole seven-id stock-002 block behind it is predicted to be a permanent
   SKIP in full-suite order.** That is **G-1**, this package's headline, and
   the new WP-B §5.2 cluster **C10**.
2. **It is the most magic-number-dense family in the suite, and the firmware
   `constrain()`s the very coordinates it mirrors.** Zero references to any
   `ST_*` name exist anywhere under `app/tools/`
   (`grep -rn "ST_LIST_ROW_H\|ST_CHART_TAB_W\|ST_CHART_TABS_X\|ST_LIST_ROW_START_Y" app/tools/`
   → no hits), while `stock.py` carries 16 literal `tap 137 <y>` row taps, 15
   `tap 10 7` back taps, 10 `tap 220 10` HEAT taps, 6 `tap 10 30` tile taps
   and `_TAB_XY`'s four tab coordinates. Both hit-tests `constrain()` the
   result (`stockApp.cpp:95-96`, `:117`), so a layout drift can never make a
   tap *miss* — only make it select something else, silently. §8 is the
   required impact list.
3. **The family's central oracle has a defaulting hole that converts it to an
   unconditional pass.** `_stock_ok_count`/`_stock_quote_ok_count` return
   `-1` on a non-`ok` reply (`_helpers.py:225-233`, `stock.py:58-66`), and
   `_wait_chart_complete(before=-1)` returns `True` on its first poll
   (`_helpers.py:258-259`). One dropped or raced serial reply on the baseline
   read makes nine ids pass without observing a fetch. **G-2**.
4. **`get fetchErrorCode` does not exist.** `StockApp::dbgGet` has no case for
   it (`stockApp.cpp:134-201`) and no other file answers it
   (`grep -rn fetchErrorCode app/src/` → three hits, all in `stock/`), so the
   command returns `{"ok":false,…,"error":"unknown var"}`
   (`cmdGet.cpp` final `printf`). `set fetchErrorCode` **does** exist
   (`stockApp.cpp:218-221`). Five diagnostics built by TASK-385/TASK-386
   specifically to capture stock fetch failures have therefore been printing
   `fetchErrorCode=None` for their whole lives. **G-3**.

---

## 1. stock-001 core navigation — `T169`–`T175` (7)

Registry order `stock.py:1465-1471`.

**Two firmware facts decide most of this block.**

**(a) The list-row hit test cannot miss.** `handleInput`'s List branch accepts
any `y >= ST_LIST_ROW_START_Y (25)` up to the canvas bottom and computes
`rowIdx = constrain((y - 25) / ST_LIST_ROW_H, 0, STOCK_TICKER_COUNT - 1)`
(`stockApp.cpp:94-97`). A row tap always drills into *some* ticker. The only
ids that can detect a wrong one are the four that assert the ticker string.

**(b) `switchApp` runs `init()` once per boot, `resume()` thereafter**
(`appShell.cpp:200-207`, gated on `shell::state().launched[]`). So every
"launch view" claim in this family is a claim about `init()` on the first
entry and about `resume()` (`stockApp.cpp:35-60`) on all 29 later ones — and
`resume()` re-applies the launch view **only** when `g_settings.stockMode`
differs from `_appliedMode`, which `_switch_to_stock`'s unconditional
`set stockMode 0` guarantees it does not.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `stock.py:75` | T169 | `switchApp`→Stock activates StockApp; `switchApp`→Spotify restores; `stockSubView=list` on first launch. | Three device reads: `get appId.name == "Stock"`, `get stockSubView.val == "list"`, `get appId.name == "Spotify"` after the switch-back. | **SOUND** | S13, S14 | `:84-101` via `_helpers.py:195-217`. The round-trip claim and the oracle match exactly — both directions are read back from `get appId`, not inferred from the `switchApp` ack, and both switch failures are `fail()`, not `skip()`. It is also the family's only id that suspends background polling around the switch (`_bgpoll_suspended`, `:82-84`), which is why it is the least contended entry in the file. Costs: the `subView == "list"` term is the List leg of `T231` (`:712-717`) with the mode written by the helper rather than by the test, so as a *launch-view* assertion it is redundant; and the helper's `set stockMode 0` is never restored (**G-4**, WP-B **B-5**). Note for the flake ledger: `flaky.yaml:155-156` lists `T169` as a candidate with the note *"yahoo/network flakiness"*, and **nothing in this body touches Yahoo** — the failure mode it actually has is a serial-flood timeout on `get appId` while `_applyLaunchView()`'s 8-ticker quote batch is in flight (`stockApp.cpp:71`). **G-14**. |
| `stock.py:109` | T170 | Quote fetch **completes** after switch-in: `quoteOkCount` advances within 65 s (the TASK-112 audit-001 replacement for the old `lastQuoteFetch > 0` enqueue proxy). | `_stock_quote_ok_count` delta — `current > before`, plus a stuck-progress watchdog on `stockQuoteProgress`. | **WEAK** | S6, S10, S14, S13 | `:116-150`. The counter is the right observable and the body earned it: `_s.quoteOkCount++` happens **only** inside `if (r.ok)` in `stockTickQuotes()` (`stockApp.cpp:338`), so an advance genuinely proves an HTTP+parse round trip, and the 20 s stuck-ticker watchdog (`:132-136`) is a real second failure mode with a named ticker in the message. What downgrades it is **G-2**: `_stock_quote_ok_count` returns `-1` when the reply is not `ok` or has no `val` (`stock.py:58-66`), so a single raced baseline read sets `before = -1` and the *next* poll — reading the real, already-non-zero count — satisfies `current > before` immediately, with no fetch in the window at all. That is the whole oracle, defaulted to pass. Two lesser costs: `65.0` is uncited (it is presumably `STOCK_QUOTE_FETCH_MS = 60000` + 5 s, `stockShared.h:18`, but nothing says so), and the plan's primary `### T170` entry (`test_plan.md:1802-1811`) still describes the retired `lastQuoteFetch` proxy — the live description is the audit-001 fix row at `:2106-2111` (**G-12**). |
| `stock.py:155` | T171 | "Positive `changePct` rows render green, negative red." | **None.** The body is `print(...)` then one unconditional `skip()`. | **HOLLOW** | S7, S4, S1 | `:157-158`. Two statements, no device read, no assertion, no branch. It is honest about it — the docstring carries `[MANUAL — pixel verification required]` and `test_plan.md:1813-1822` says *"Harness: manual only (no pixel-read command)"* — so unlike WP-D's `T136` there is no stale PASS claim to correct. It is graded HOLLOW rather than excused because it **is** counted: it occupies a registry slot, it is dispatched by `run/test`, and it is one of the 30 ids `./run/test-targeted --scope Stock` selects. A pixel-read command now exists (`run/screendump`, used by four WebRadio ids — `webradio.py:1398-1428`), so the "no pixel-read command" premise is also stale. |
| `stock.py:163` | T172 | Spotify→Stock→Spotify leaves no TFT residue: the Winamp chrome repaints cleanly. | `_check_residue` — `lastPlaylistDraw.ms` changes within 3 s. **On failure the body `skip()`s.** | **BROKEN** | S7, S5, S8, S14 | `:169-178` via `_helpers.py:177-192`. This is the fifth instance of WP-D **D-2**, verbatim: `_check_residue` calls `pass_()` itself and returns `False` for the caller to adjudicate — its docstring says *"Does not call fail() — caller decides on skip vs fail"* (`_helpers.py:180`) — and this caller chose `skip()`, with the reason *"Spotify not rendering (not playing?)"* (`:178`). The regression the id exists to detect is exactly "Spotify does not repaint after the switch-back", so **the test cannot fail for the reason it exists**; per rubric §2 that is BROKEN. WP-D **D-2** additionally established that the excuse is wrong (`SpotifyApp::resume()` calls `invalidatePlaylist()`, forcing the repaint regardless of what is playing), and this row inherits that finding rather than re-deriving it. Independently, a repaint timestamp is not evidence of clean pixels — the claim is a pixel claim and the oracle is a counter. |
| `stock.py:183` | T173 | Switching away from Stock and back within 60 s does **not** trigger a new quote fetch — the resume is served from cache. | `get lastQuoteFetch` identical before and after a 2 s Spotify round trip. | **WEAK** | S7, S8, S14 | `:190-209`. The value is device-owned and the assertion is a real negative: `stockTickQuotes()` re-enqueues and re-stamps `_s.lastQuoteFetch` whenever `now - lastQuoteFetch > STOCK_QUOTE_FETCH_MS` (`stockApp.cpp:325-327`), so an unchanged reading does mean no re-enqueue fired. Three things make it narrower than it claims. **(a) It never checks the sub-view.** `tick()` only runs `stockTickQuotes()` when `subView == List` (`stockApp.cpp:79-83`), and `resume()` repaints whatever sub-view the previous test left. If a predecessor left Stock in chart or heatmap view, the quote tick cannot run and the assertion is pre-satisfied by construction — a vacuity `_order.py` does not record (its `T173` row, `:217-220`, is only about the SKIP direction). **(b) The 60 s window is a false-red generator.** The test asserts "unchanged" but does not bound the elapsed time since the last fetch; running after `T170`'s 65 s wait and `T171`/`T172`, `now - lastQuoteFetch` can already exceed `STOCK_QUOTE_FETCH_MS`, in which case the re-entry tick legitimately re-fetches and the id reports *"unexpected re-fetch on resume"*. **(c)** `baseline == 0` is a `skip` (`:192-195`) — the ORDER-SENSITIVE dependency `_order.py:217` names. |
| `stock.py:214` | T174 | Tapping the NVDA row (row 7, `y=218`) enters chart view with the correct ticker and the default D1 range. | Three device values: `stockSubView == "chart"`, `stockChartTicker == "NVDA"`, `stockChartRange == "D1"`. | **SOUND** | S11, S10, S14, S13 | `:230-245`. Three independent terms, and the middle one is the family's only real defence against coordinate drift: `y = 218` resolves to `rowIdx = constrain((218-25)/26, 0, 7) = 7` (`stockApp.cpp:95-96`), so a changed `ST_LIST_ROW_H` selects a different ticker and this id fails **loudly** (§8). The range term is a genuine second behaviour — `drillTo()` assigns `StockRange::D1` unconditionally (`stockChart.cpp:76`). Costs: `"NVDA"` mirrors `kDefTickers[7]` (`settingsStorage.cpp:91`), which is a *persisted user setting* rather than a compile-time constant, so a reconfigured watchlist (`settings/appsSection.h`) fails this id for the wrong reason (S11); the arithmetic is spelled out in a comment (`:230`) rather than parsed; and `:226` reads `stockSubView` into `r_ff` and never uses it — dead code whose own comment (`:227-228`) explains a check that was never written. |
| `stock.py:250` | T175 | From chart view, the back zone `(10,7)` returns `stockSubView` to `list`. | `stockSubView == "chart"` after the drill, then `== "list"` after `tap 10 7`. | **SOUND** | S10, S7, S14 | `:258-275`. A real two-state transition on a device-owned field, and the tap is a genuine hit on the firmware's back zone: `y = 7 < ST_CHART_HEADER_H (18)` and `x = 10 < ST_CHART_BACK_W * 2 (60)` (`stockApp.cpp:111-114`). One documentation defect worth fixing while nearby: the body's comment says *"x=10 < ST_CHART_BACK_W(30)"* (`:266`) — the firmware condition is `x < ST_CHART_BACK_W * 2`, i.e. 60, so the comment understates the zone by half and would mislead anyone widening the glyph. The precondition is unguarded: if a predecessor left Stock in chart view, `tap 137 36` lands in the chart body and is a no-op (`stockApp.cpp:129`), the `subView == "chart"` guard still passes on the *pre-existing* state, and the id proves back-navigation from a chart it did not enter. Still a real assertion, so SOUND, but the drill-in half is unverified. |

---

## 2. Chart fetch, range tabs and placeholder state — `T176`–`T182` (7)

Registry order `stock.py:1472-1478`.

**The firmware fact that decides two of these rows.**
`set triggerFetch 1` is not a neutral "force a refresh". It assigns
`_s.lastQuoteFetch = 0; _s.lastChartFetch = 0; _s.chartLen = 0;
_s.fetchFailed = false;` and discards the parked chart result
(`stockApp.cpp:222-233`). So any id that injects `triggerFetch` and then
asserts `chartLen == 0` or `fetchFailed == false` is reading back its own
write. `T178` asserts both.

**And the tab hit test clamps.** `tab = constrain((x - ST_CHART_TABS_X) /
ST_CHART_TAB_W, 0, 3)` (`stockApp.cpp:117`) — a tab tap can never miss, only
select a different range, which matters for `T188`/`T204` in §4 and is
tabulated in §8.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `stock.py:280` | T176 | "Plot bounds": chart fetch completes — `fetchOkCount` advances (the audit-001 replacement for the `lastChartFetch > 0` enqueue proxy). Pixel confinement to y:18..213 is manual. | `_wait_chart_complete(before)` — `fetchOkCount` delta within 45 s, after draining the fetch pipeline with `bgPoll` off. | **WEAK** | S6, S7, S10, S13, S14 | `:294-319`. The counter is the correct observable (`_s.fetchOkCount++` only inside `if (r.ok)`, `stockChart.cpp:139`) and the TASK-300 pipeline drain around it is the best-argued piece of synchronisation in the family — `_drain_data_pipeline`'s defaults are all in the safe direction (`queueWaiting, 1`, `inFlight, 0` vs the required `-1`, `_helpers.py:81-82`), so a missing field keeps draining rather than declaring quiet, and `bgPoll` is restored in a `finally` (`:312-313`). Three things hold it back. **(a) G-2:** `before = _stock_ok_count(dut)` (`:301`) defaults to `-1`, and `_wait_chart_complete(-1)` returns `True` on its first poll (`_helpers.py:254-259`) — the oracle, defaulted to pass. **(b)** The pixel half of the claim, which is what "plot bounds" *means*, is asserted nowhere and is admitted in the pass string (`:319`) — S4's shape, though the docstring is honest about it. **(c)** What remains is "a chart fetch completed", which is exactly `T186`/`T187`'s assertion with a different ticker (S13). The 45 s and 200 s budgets are uncited. |
| `stock.py:324` | T177 | Tapping the 5D tab `(184,7)` sets `stockChartRange=D5` **and triggers a new fetch** — `lastChartFetch` advances. | `stockChartRange == "D5"`, and `lastChartFetch > 0` polled for 5 s. | **WEAK** | S8, S3, S10, S14 | `:340-359`. The range half is real, loud and correctly derived: `x = 184` → `constrain((184-130)/36, 0, 3) = 1` → `StockRange::D5` (`stockApp.cpp:117-118`), so a tab-handler regression fails here. The fetch half is vacuous. The plan prescribes *"Record `lastChartFetch`. … Poll until it **advances**"* (`test_plan.md:1886`); the body polls for `> 0` **absolute** (`:348`) against a field the drill-in three lines earlier already set to `millis()` (`stockChart.cpp:84`). The loop therefore returns `True` on its first iteration in every run, and the comment above it — *"lastChartFetch resets to 0 on tab change, then advances when enqueue fires"* (`:343`) — is wrong: nothing in the tab handler resets it to 0; it is overwritten in place (`stockApp.cpp:124`). A tab tap that changed the range but never enqueued would pass. One `before`/`after` comparison fixes it. |
| `stock.py:364` | T178 | Immediately after a reset + drill-in, `chartLen == 0` and `fetchFailed == false` — the pre-fetch placeholder state. | `get chartLen == 0` and `get fetchFailed` falsy, 100 ms after `set triggerFetch 1` + `tap 137 36`. | **HOLLOW** | S3, S3, S7, S14 | `:387-406`. Both asserted values are the test's own writes. `set triggerFetch 1` (`:387`) assigns `_s.chartLen = 0` **and** `_s.fetchFailed = false` (`stockApp.cpp:225-226`); the drill-in that follows assigns `_s.chartLen = 0` a second time (`stockChart.cpp:86`). There is no firmware behaviour between the write and the read — this is `T_WR_ERR_01`'s shape (WP-F **F-3**) with two fields instead of one. The history makes it sharper: `test_plan.md:2120-2124` is the audit-001 row that *created* this body, recording that the previous assertion (`stockChartRange == D1`) was **"trivially true — `drillToChart()` always sets D1"** and prescribing `chartLen=0` + `fetchFailed=false` as the fix. The replacement is the same defect: two values the harness set, instead of one the firmware hardcodes. What the id could assert — that the placeholder *rendered* (`chartLen < 2` draws the flat mid-line, `stockChart.cpp:34-36`; `chartLen == 0` draws `lo: ---`/`hi: ---`, `:56-59`) — needs a screendump, which the suite now has. Its real contribution is as an ordering canary, which is why `_order.py:200-207` calls it *"THE HIGHEST-RISK CELL IN THE REORDER"*; that is a property of the fixture, not of the assertion. |
| `stock.py:411` | T179 | "`lo:` and `hi:` values visible in the footer after fetch; `lo < hi`." | **None.** One unconditional `skip()`. | **HOLLOW** | S7, S4, S1 | `:413-414`. Identical in shape to `T171`: two statements, no device read, no branch, honestly labelled `[MANUAL — pixel verification required]` and matched by `test_plan.md:1901-1910` (*"Harness: manual only"*). Graded the same way and for the same reason — it is counted in the 213-id total and in `--scope Stock`'s 30 while asserting nothing. It is also the more fixable of the two: `chartLo`/`chartHi` are in `StockAppState` (`stockShared.h:67`) and are the exact numbers the footer prints (`stockChart.cpp:61-64`), but neither is exposed by `dbgGet` (`stockApp.cpp:134-201`), so the numeric half of the claim — `lo < hi` — is one getter away from being automatable and nobody has added it. |
| `stock.py:419` | T180 | Every drill-in resets `stockChartRange` to D1 — drill, change range, back, re-drill. | `stockChartRange == "D1"` after the second drill. | **WEAK** | S8, S10, S14 | `:433-460`. The final assertion is real and discriminating: without `drillTo()`'s unconditional `_s.chartRange = StockRange::D1` (`stockChart.cpp:76`) the re-drill would read D5. The weakness is that **the middle step is never verified**. The 5D tap at `:444` is fired and its effect is never read back, so if that tap misses — a cooldown race, a changed `ST_CHART_TAB_W`, a `fetchFailed` latch, which suppresses the tab branch entirely (`stockApp.cpp:116`) — the range was never D5, the "reset" has nothing to reset, and the id passes having proved that D1 stayed D1. One `get stockChartRange == "D5"` after `:444` converts the whole sequence into a real assertion; `T177` already performs exactly that read four lines from an identical tap. The three `_wait_shell_not_busy(10.0)` calls are the right synchronisation instrument (they gate on `g_shellBusy`, not a sleep), but their return values are all discarded. |
| `stock.py:465` | T181 | Back → list → tap NVDA again; the chart redraws with the correct ticker. | `stockSubView == "chart"` and `stockChartTicker == "NVDA"` after the re-drill. | **SOUND** | S11, S13, S10, S14 | `:474-495`. Two real device values, and the ticker term is again the coordinate-drift detector (`y = 218` → row 7, `stockApp.cpp:95-96`). It is a genuine second behaviour beyond `T174`: the sequence AAPL → back → NVDA proves `backToPrevView()` clears `chartSymbol` (`stockApp.cpp:314`) and that the second `drillTo` re-keys `chartTickerIdx` rather than reusing the first — the exact TASK-380 regression the firmware comment at `stockChart.cpp:78-82` describes. Costs: `"NVDA"` is again the persisted-setting mirror (S11, `settingsStorage.cpp:91`); the intermediate back tap's effect is not read back (the same gap as `T180`, but harmless here because a failed back leaves the AAPL chart and the NVDA assertion then fails loudly); and it overlaps `T174` on two of its two assertions (S13). |
| `stock.py:500` | T182 | Stock → chart view → `switchApp` away → **taskbar** scroll + slot tap back → no residue on the return to Spotify (cross-feature: `stock-001` + `taskbar-scroll-001`). | `get appId.name == "Stock"` after the taskbar tap — **a miss is a `skip`** — then `_check_residue`, whose failure is also a `skip`. | **BROKEN** | S1, S7, S5, S13, S14 | `:518-558`. **The body has no reachable `fail()`.** Both `fail()` calls are unreachable: `:508` fires only if the *serial* `switchApp` fails, which the id is not about, and `:553-555` tests `r_app.get("ok")` **after** `:541-545` has already `skip`ped on `r_app.get("name") != "Stock"` — a non-`ok` reply has no `name`, so it takes the skip first. Everything the id exists to detect — the taskbar scroll not reaching offset 2 (`:525-528`), the slot tap missing Stock (`:541-545`), Spotify not repainting (`:556-558`) — exits as a SKIP. Sixth instance of WP-D **D-2**, and the worst-shaped one, because two of its three skip branches are the *taskbar* behaviour the cross-feature claim is about. Two further defects. `r_sv = _stock_get(dut, "stockSubView")` at `:549` is read and **never used**, with a three-line comment (`:546-548`) that talks itself out of the assertion (*"The test is: no display crash, subView is still whatever it was"*) — the sub-view-preservation half of the docstring is deliberately unasserted. And the id is scoped `Stock` while being the family's only taskbar test (**G-13**). One thing it does right, and it is the only place in the file that does: the physical slot is **computed** from the generated registry — `(APP_SLOT["Stock"] - 2) % APP_SLOT["WebRadio"]` (`:536`) = `(6-2) % 11 = 4` → `tap_taskbar_slot(4)` → `(297, 180)` — with a comment explaining why the mod base is `TASKBAR_APP_COUNT` and not `APP_COUNT` (`:530-535`). That is LL-114 done correctly, in a file that otherwise never does it. |

---

## 3. Error injection and the launch-view setting — `T183`, `T184`, `T231`, `T185` (4)

Registry order `stock.py:1479-1482`.

**The firmware fact that decides `T185`.** `set fetchFailed 1` sets a bool
(`stockApp.cpp:205-208`) and `set triggerFetch 1` **clears it**
(`stockApp.cpp:226`) as part of the same reset that zeroes the two fetch
timestamps. An "error recovery" test that injects an error and then issues
`triggerFetch` has already cleared the error before any fetch runs.

**And `lastQuoteFetch` is an enqueue stamp, not a completion stamp.** Both
writers set it at the moment the request is queued — `_applyLaunchView()`
(`stockApp.cpp:71-72`) and `stockTickQuotes()` (`stockApp.cpp:326-327`) — and
neither touches it when the result lands. `_wait_quote_fetch`'s docstring,
*"Wait until lastQuoteFetch advances past baseline (fetch completed)"*
(`stock.py:43`), is wrong about the second half; TASK-112 identified exactly
this (`test_plan.md:2106-2111`) and fixed `T170` by adding `quoteOkCount`, but
`T185` was left on the proxy.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `stock.py:563` | T183 | `set fetchFailed 1` shows the error screen and makes list-row taps a no-op — `stockSubView` stays `list`. | `stockSubView == "list"` after `tap 137 120` with `fetchFailed = 1`. | **WEAK** | S8, S4, S14 | `:575-590`. The guard it targets is real and one line: `if (_s.fetchFailed) return true;` sits between the HEAT-zone check and the row-drill branch (`stockApp.cpp:93`), so this is a correctly-aimed negative assertion, and the injection/cleanup are symmetric (`:584-585`). The weakness is that it is **only** a negative: nothing establishes that the same tap at the same coordinates *would* drill without the flag, so any unrelated reason the tap did not register — an armed cooldown, a sub-view that is not List (the body normalises, `:571-574`, but does not verify the normalisation), a coordinate drift — reads as the guard working. A two-phase form (tap → assert chart → back → inject → tap → assert list) costs three commands and makes the id falsifiable. The other half of the claim is handed to a human in the pass string: *"error screen shown (manual verify)"* (`:590`), while `repaintError()`'s output is deterministic text (`stockApp.cpp:257-271`) and `run/screendump` exists. |
| `stock.py:595` | T184 | The back button still works while `fetchFailed = 1` in chart view. | `stockSubView` goes `chart` → `list` after `tap 10 7` with the flag set. | **SOUND** | S10, S14 | `:609-621`. A positive assertion on a real device transition, aimed at a real branch order: the back-zone check precedes the `!_s.fetchFailed` guard in the chart branch (`stockApp.cpp:111-116`), and `isNavigationTap()` exists specifically so the shell lets this tap through while a fetch is in flight (`stockApp.h:39-42`, `stockApp.cpp:12-19`). Invert that order in the firmware and this id fails. It clears the flag before returning (`:616`), which is why the `T186`–`T204` block downstream is not poisoned by it. Costs: the tap coordinates are literals (§8), and it inherits `T175`'s unverified drill-in precondition — though here the drill is asserted (`:605-608`) before the injection, so the sequence is sound. |
| `stock.py:637` | T231 | The Settings → Stock **mode** (List/Chart/Heatmap) is honoured at launch; the Chart launch has a non-empty ticker; List is the back-navigation base for both detail views. | Nine device-observed values across three legs: `stockSubView` after each of `set stockMode 1/2/0` + re-entry, a non-empty `stockChartTicker` on the Chart leg, and `stockSubView == "list"` after the back tap on the Chart and Heatmap legs. | **SOUND** | S10, S12, S14 | `:656-722`. The strongest test in the family and the only one built around a deliberately-designed observable. It is the one id that does **not** use `_switch_to_stock` for its real legs — `_enter_stock_no_force` (`:626-634`) exists precisely so the helper's `set stockMode 0` cannot pre-empt what the test is measuring, and the docstring says so. Each leg asserts a different `_applyLaunchView()` branch (`stockApp.cpp:62-76`) and the Chart leg's extra ticker check targets the exact original defect (*"Chart launched with an empty ticker"*, `:669`) — `drillTo(0)` must run, not just `subView = ChartDetail` be assigned. The two back-nav assertions are genuine: `backToPrevView()` returning List depends on `drillTo`/`enter()` having stamped `prevSubView` correctly (`stockChart.cpp:73`, `stockHeatmap.cpp:26`). Costs: the tap coordinates are literals (`tap 10 7`, `tap 260 7`); the mode restore is issued on every exit path, which is more than any other body in the file manages, but `_appliedMode` is left wherever the last leg put it; and the id **collides with an unrelated plan entry** — `test_plan.md:4109` declares `### T231 — [app-settings-wire-001] Aquarium speed slow/fast visually distinct [MANUAL]`, and no second body carries the id (**G-11**, the Stock instance of WP-F **F-2**). |
| `stock.py:727` | T185 | Error → `triggerFetch` → `lastQuoteFetch` advances: the error state is recoverable by a successful fetch. | `_wait_quote_fetch` — `lastQuoteFetch != baseline` within 65 s. `fetchFailed` is **never re-read**. | **HOLLOW** | S3, S2, S8, S14 | `:734-747`. Two independent reasons the claimed behaviour is not observed. **(a) The test clears its own error.** `set fetchFailed 1` at `:734`, then `set triggerFetch 1` at `:740`, which assigns `_s.fetchFailed = false` directly (`stockApp.cpp:226`) — before any fetch is enqueued, let alone completed. Whatever the fetch does afterwards, the flag is already down, and the body never reads it back to find out. The claim "error clears **on successful fetch**" is performed by the injector. **(b) The oracle is an enqueue proxy, not a completion proxy.** `set triggerFetch 1` zeroes `lastQuoteFetch`, and the very next `stockTickQuotes()` tick re-stamps it with `millis()` at the moment it calls `dataTask::enqueue` (`stockApp.cpp:325-327`) — so `!= baseline` is satisfied within one tick whether or not Yahoo ever answers. This is the precise defect TASK-112 catalogued and fixed for `T170` (`test_plan.md:2106-2111`); the fix was never carried across, although `quoteOkCount` is exposed (`stockApp.cpp:173-177`) and `_stock_quote_ok_count` already exists two functions above this body (`stock.py:58`). What remains is "a quote fetch was enqueued after `triggerFetch`", asserted through a timestamp the same command zeroed. On the failure path it also leaves `fetchErrorCode = -99` installed, which nothing reads because **G-3**. |

---

## 4. M-DATATASK-STREAM-PARSE and the alloc/free stress — `T186`, `T187`, `T188`, `T204` (4)

Registry order `stock.py:1483-1486`. These four share the LL-041
snapshot-then-wait-for-the-counter pattern, and it is the right pattern:
`_s.fetchOkCount++` fires only inside `if (r.ok)` in `StockChart::tick()`
(`stockChart.cpp:132-139`), **after** the identity check that discards a
result belonging to a superseded request (`:124-130`), so an advance proves a
matching HTTP + parse round trip and not merely a dequeue. Everything below is
about what surrounds that counter.

**Two facts split the block.** `T186`/`T187` additionally assert the ticker,
which is a real second term and a coordinate-drift detector. `T188`/`T204`
assert only the counter and `fetchFailed`, and **never read
`stockChartRange`** — so given `tab = constrain((x - 130) / 36, 0, 3)`
(`stockApp.cpp:117`), a changed tab geometry silently redirects their taps
without changing the verdict (§8).

**And `fetchFailed` is read with an unsafe default.** All four use
`r_ff.get("val") == "1" or r_ff.get("val") is True` (`stock.py:800`, `:865`,
`:932`). The firmware prints an unquoted JSON literal — `"val":true` /
`"val":false` (`stockApp.cpp:183-186`) — so the `== "1"` half is dead and the
`is True` half carries it; but a reply with no `val` at all yields `None`,
which is neither, and the id reads it as "not failed". S6, in the unsafe
direction, on the term that names the regression.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `stock.py:806` (shared body `:763`) | T186 | MSFT (`tickerIdx = 6`) chart fetch succeeds after the `tickerIdx >= 8` guard fix. | Four device values: `stockSubView == "chart"`, `stockChartTicker == "MSFT"`, `fetchOkCount` advances within 45 s, `fetchFailed` not true. | **SOUND** | S6, S11, S14, S10 | `:769-803`. Multi-term and correctly ordered: the ticker assertion (`:785-788`) is a hard `fail()` and pins the tap to row 6, so it is the drift detector §8 relies on, and the counter delta then proves the fetch the guard used to reject actually completed. The body normalises to list view first (`:769-772`) and clears any inherited error state (`:773-774`) — the only bodies in the file that clean up *before* rather than after. Costs: **G-2** applies to `before = _stock_ok_count(dut)` (`:790`) as everywhere else, but here it is one term of four rather than the whole oracle, which is why this row keeps its verdict; `"MSFT"` and `192` mirror `kDefTickers[6]` and `25 + 6*26 + 11` (`settingsStorage.cpp:91`, `stockShared.h:37-38`) as literals passed in from `:809`; and the `fetchFailed` read defaults to passing. |
| `stock.py:812` (shared body `:763`) | T187 | NVDA (`tickerIdx = 7`) same. | Same four values, `"NVDA"` / `row_y = 218`. | **SOUND** | S6, S11, S13, S14, S10 | `:815` → `:763-803`. Identical to `T186` with two arguments changed, which is the right way to parameterise a guard test — the guard was `tickerIdx >= 8`, so 6 and 7 are the two indices that were rejected and both are worth covering. It carries `T186`'s costs unchanged, plus S13 against `T174`/`T181`, which already assert `stockChartTicker == "NVDA"` after a `tap 137 218`; the distinct part here is only the fetch completion. |
| `stock.py:818` | T188 | Cycling all four range tabs fetches without a `-99` NET ERR (the `getStream()` fix, ADR-034). | Per tab: `fetchOkCount` advances within 45 s, then `fetchFailed` not true. Four iterations over `_TAB_XY`. | **WEAK** | S6, S8, S11, S13, S14 | `:848-874`. The loop structure is good — the counter is re-snapshotted before every tap (`:850`) so the assertion is a per-tab delta rather than a cumulative one, and the comment at `:840-846` records exactly why tab taps were chosen over `triggerFetch` (which would also fire an 8-ticker quote batch). Three weaknesses. **(a) It never asserts which range it fetched.** `stockChartRange` is not read anywhere in the body, so under a changed `ST_CHART_TAB_W` the four taps can clamp onto two or three distinct tabs and the id still reports *"all 4 ranges (D1/D5/Mo1/Ytd) fetched"* — a false coverage claim, not just a missed regression (§8). **(b) G-2** on all four `before` reads. **(c)** The `-99` in the claim is never tested for: `fetchErrorCode` is unreadable (**G-3**), so the id can only distinguish "failed" from "not failed", and its own failure message prints `fetchErrorCode=None`. The uncited `45.0` is the fourth-largest timeout budget in the family. |
| `stock.py:883` | T204 | D1↔Ytd rapid alternation (3 cycles, 6 fetches) exercises back-to-back `DynamicJsonDocument(16384)` alloc/free **under heap pressure** without `fetchFailed`. | Per tap: `fetchOkCount` advances within 45 s, then `fetchFailed` not true. Six iterations. **No heap value is compared to anything.** | **WEAK** | S6, S8, S10, S13, S14 | `:909-944`. The instrumentation is genuinely good and genuinely new — `_diag_snapshot` is taken at entry and before every one of the six taps (`:890`, `:917`), with a comment explaining that the subject is a *trend* across the cycle, not a single failure point (`:913-916`). But **the snapshots are printed and embedded in `fail()` strings; not one of them is ever compared.** `freeInt`/`lfbInt` shrinking cycle over cycle — the stated hypothesis — cannot fail this id. What can fail it is the same pair of terms `T188` already asserts, run six times instead of four, which is why the row is WEAK rather than SOUND: as written it is `T188` with a different tab sequence (S13). It also inherits `T188`'s blindness to which range it fetched, and here that matters more, because the plan's whole rationale is *"the largest (Ytd) and smallest (D1) payloads"* (`test_plan.md:2081`) — a tab-geometry drift that turns `_TAB_XY[3]` into Mo1 silently converts the stress test into a smaller-payload one while it still reports green. `entry_diag` is computed **before** `_switch_to_stock` (`:890`), so on the skip path it is a snapshot of Spotify, not of Stock. |

---

## 5. stock-002 — the heatmap sub-view — `T196`, `T200`–`T203`, `T192`–`T194` (8)

Registry order `stock.py:1487-1494`. Every one of these eight is inside
**G-1**'s blast radius (§6.2): seven of them enter through
`_ensure_stock_list_view` (`stock.py:967-986`), which is the helper the wedge
disables, and the eighth (`T196`) is the one that arms it.

**The three firmware facts this block turns on.**

**(a) `set triggerHeatmap 1` is not just a fetch trigger.** It assigns
`_s.prevSubView = _s.subView`, `_s.subView = HeatmapDetail`,
`_s.lastHeatmapFetch = 0` and repaints (`stockApp.cpp:246-253`). The
`prevSubView` write is the one nobody accounted for.

**(b) `backToPrevView()` has a fixed point.** It sets
`subView = prevSubView`, and rewrites `prevSubView` only when the new
sub-view is `HeatmapDetail` (`stockApp.cpp:312-315`). With
`prevSubView == ChartDetail`, back navigation maps `Chart → Chart` and
`Heatmap → Chart` forever. In production `prevSubView` can only ever be
`List` or `HeatmapDetail` — `drillTo`/`drillToBySym` stamp it from the
current sub-view and `enter()` hardcodes `List` (`stockChart.cpp:73`, `:93`,
`stockHeatmap.cpp:26`) — so the fixed point is reachable **only through the
debug injector**.

**(c) `heatmapCount` survives a failed fetch.** `StockHeatmap::tick()`
replaces `_s.heatmapData` only on `r.ok`, and on a failure keeps the last
good data if there is any (`stockHeatmap.cpp:223-236`). So `heatmapCount > 0`
is an absolute assertion that a predecessor's successful screener fetch
pre-satisfies — which is what `_order.py:221-224` records as `T196`'s
VACUITY.

| Body | Id | Claim | Oracle | Verdict | Smells | Evidence |
|---|---|---|---|---|---|---|
| `stock.py:991` | T196 | `set triggerHeatmap 1` sets the sub-view and forces a fresh fetch; `heatmapCount > 0` within 60 s. | `stockSubView == "heatmap"` after the injection, then `heatmapCount > 0`. | **WEAK** | S3, S8, S14, S7 | `:998-1014`. The first term is a tautology of the WP-F `T_WR_ERR_*` kind: `set triggerHeatmap` assigns `_s.subView = StockSubView::HeatmapDetail` (`stockApp.cpp:249`) and `get stockSubView` prints that member (`:136-138`) — one write, one read, no behaviour between. The second term is real but absolute, and `heatmapCount` is not reset by the trigger (only `lastHeatmapFetch` is, `:250`), so a screener fetch that *fails* leaves the previous run's count in place and the id passes on stale data — `_order.py:221-224`'s VACUITY, confirmed against `stockHeatmap.cpp:229-236`. What the id could assert is the fetch it names: `lastHeatmapFetch` is zeroed by the trigger and re-stamped by the next tick, and `heatmapData.ok`/`errorCode` are populated per attempt — none of the three is exposed by `dbgGet` (`stockApp.cpp:134-201`), so the observable that would make this id sound does not exist. **This is also the body that arms G-1**: it issues the injection immediately after `_switch_to_stock` with no sub-view normalisation (`:994-998`), and its registry predecessor `T204` exits in chart view. |
| `stock.py:1019` | T200 | A HEAT tap (`x>190`, `y<22`) in list view switches the sub-view to heatmap. | `stockSubView == "heatmap"` after `tap 220 10`. | **SOUND** | S7, S10, S14 | `:1026-1039`. A correctly-aimed single-behaviour assertion: `y = 10 < ST_LIST_RULE_Y (22)` and `x = 220 > 190` is exactly the List-branch HEAT zone (`stockApp.cpp:92`), which calls `_heatmap.enter()`, and the sub-view read afterwards is a real device value. It normalises first and gates on the normalisation (`:1026-1029`). The verdict is on the body as written; **in full-suite order it is predicted never to run** — `_ensure_stock_list_view` is the helper G-1 disables, and this is the first id to call it after `T196` arms the wedge, so the observed result would be `SKIP: could not normalize to list view`. That prediction is NEEDS-DUT #1, not a verdict. |
| `stock.py:1044` | T201 | A HEAT tap in heatmap view returns the sub-view to list. | `stockSubView == "list"` after `tap 220 10` from heatmap. | **SOUND** | S7, S10, S3, S14 | `:1052-1075`. The complement of `T200` and a real assertion on `backToPrevView()` (`stockApp.cpp:101`, `:312-321`): it passes only if `prevSubView` was correctly stamped `List` by the entry path, which is the behaviour the id exists for. The body is careful about that — the comment at `:1051` says *"Normalize to list first so prevSubView is correctly set to List"* — and this is precisely the invariant `T196`'s injection breaks for everything downstream, which makes the omission in `T196` sharper, not softer. Costs: it reaches heatmap via `set triggerHeatmap 1` rather than the HEAT tap, so the entry half is the S3 injection rather than the UI; the mismatch is a `skip` (`:1063-1066`); and the same full-suite SKIP prediction applies. |
| `stock.py:1080` | T202 | Tapping a tile in heatmap drills to ChartDetail, and `stockChartTicker` returns **the symbol from the tapped tile**. | `stockSubView == "chart"` after `tap 10 30`. The drilled symbol is read into `drilled` and **printed, never asserted**. | **WEAK** | S6, S7, S10, S14 | `:1113-1124`. Half the claim is asserted and half is narrated. The sub-view term is real: `tap 10 30` lands in tile 0 — the treemap's first strip always starts at `(rx, ry) = (0, ST_LIST_RULE_Y)` in both the horizontal and vertical branches (`stockHeatmap.cpp:62`, `:87-113`), and tile 0 is the largest by market cap because `order[]` is sorted descending (`:44-49`) — so the tap does hit a tile and `drillToBySym` does run (`stockApp.cpp:102-107`). The symbol term is not: `drilled = r_sym.get("val", "?")` (`:1122`) defaults to `"?"` and is only interpolated into the pass string, so a `drillToBySym` that installed the wrong symbol, or a `get` that failed outright, both pass. `_s.heatmapData.symbols[t.tickerIdx]` is available to compare against nothing the host can read — there is no `get heatmapSymbol <i>` — so the honest fix is to assert `drilled` is one of the eight configured tickers or simply non-empty and not `"?"`. Note the plan (`test_plan.md:2444`) still specifies `tap 137 130` while the body taps `(10,30)`; the plan's own trailing note records the change but its Steps block was not updated. |
| `stock.py:1129` | T203 | A back tap from a chart entered via a heatmap tile restores **HeatmapDetail**, not List. | `stockSubView == "heatmap"` after `tap 10 7`. | **SOUND** | S7, S10, S14 | `:1175-1183`. The best-aimed row in this block. The naive implementation returns `list`, and the id's oracle distinguishes exactly that: `drillToBySym` stamps `prevSubView = HeatmapDetail` (`stockChart.cpp:93`) and `backToPrevView()` reads it (`stockApp.cpp:313`), so a regression that hardcoded List — or that dropped the `prevSubView` stamp — fails here and nowhere else in the suite. The synchronisation is also right: it waits for `g_shellBusy` to clear after the tile drill before the back tap (`:1170-1173`) rather than sleeping, with the failure of that wait a `skip`. Costs: four separate `skip()` exits before the assertion is reached (`:1144`, `:1148`, `:1157`, `:1166`, `:1171`), the tap literals, and the full-suite SKIP prediction. |
| `stock.py:1188` | T192 | After a heatmap drill, a range tab-switch fetches **the drilled symbol** (the TASK-121 fix). | Three device values: `stockChartRange == "D5"` after the 5D tap, `fetchOkCount` advances within 45 s, and `stockChartTicker` unchanged across the tab-switch. | **SOUND** | S6, S3, S7, S14 | `:1236-1256`. The load-bearing term is the counter delta, and it is load-bearing for a non-obvious reason worth stating: the regression this id guards is the tab handler enqueueing by **index** while `chartSymbol` is set (`stockApp.cpp:120-123`). Under that bug the result comes back for the wrong symbol, `StockChart::tick()`'s identity check discards it (`stockChart.cpp:124-130`) and `fetchOkCount` **never advances** — so the delta, not the ticker comparison, is what detects it. The range term is a genuine third value and a drift detector. The ticker comparison itself is close to tautological (S3): `get stockChartTicker` reads `chartSymbol` (`stockApp.cpp:141-144`) and nothing in the tab path writes it, so `after_sym != drilled` is a comparison of one member against itself two reads apart. **G-2** applies to `before_ok`. Registry-order note: this id and its two successors are the only bodies in the family that repair G-1's wedge (a heatmap tile drill re-stamps `prevSubView = HeatmapDetail`), but only if they get past `_ensure_stock_list_view` — which under the wedge they do not. |
| `stock.py:1261` | T193 | The `stockTickChart()` auto-refresh path uses `chartSymbol` after a heatmap drill (the TASK-121b fix). | `fetchOkCount` advances after `set triggerFetch 1`; `stockChartTicker` unchanged; `chartLen > 0` — **and `chartLen <= 0` is a `skip`**. | **WEAK** | S6, S3, S7, S8, S14 | `:1320-1345`. Same real mechanism as `T192` — under the bug, `StockChart::tick()`'s re-enqueue keys on the index (`stockChart.cpp:112-115`), the identity check discards the result and the counter never moves — so the id does cover its subject. Four costs, and together they are why it is WEAK rather than SOUND. **(a)** The ticker comparison is the same self-comparison as `T192`'s (S3). **(b)** `chartLen > 0` is an absolute assertion a predecessor's fetch can pre-satisfy — `_order.py:225-228`'s VACUITY, and correct: `chartLen` is only zeroed by a drill or by `triggerFetch`, and `triggerFetch` runs here before the wait, so this one is actually self-clearing; the VACUITY that remains is the heatmap-cache reuse the same `_order.py` entry names. **(c)** `chartLen <= 0` exits as a **`skip`** blaming Yahoo (`:1342-1344`) — the one branch where the auto-refresh returning an empty payload and the upstream returning an empty payload are indistinguishable, resolved in favour of the upstream. **(d) G-2** on `before_ok`. The TASK-385 diagnostic scaffolding (`:1268`, `:1323`, `:1329`) is thorough and, as in `T204`, purely narrative — no snapshot is compared. |
| `stock.py:1350` | T194 | Back-to-list after a heatmap drill **clears `chartSymbol`**; the subsequent list drill uses the index ticker. | `stockChartTicker` after the list-drill tab-switch equals the value read immediately after the list drill. `fetchOkCount` failing to advance is a **`skip`**. | **BROKEN** | S3, S7, S6, S8, S14 | `:1425-1461`. **No reachable assertion can fail for the claimed reason.** Two independent proofs. **(a) The one `fail()` is a tautology.** `list_ticker` is read at `:1434` and `after_sym` at `:1455`; between them the only firmware write to either backing field would be a `drillTo`/`drillToBySym`, and the tab handler performs neither (`stockApp.cpp:116-127`). `after_sym != list_ticker` compares a value with itself. **(b) The real oracle cannot fail at all**: `_wait_chart_complete` returning `False` exits via `skip()` (`:1448-1454`), not `fail()` — the only body in the family that does this, and the identical construction in `T192`/`T193` is a `fail()`. So a tab-switch that never fetched is a green-adjacent non-result. On top of that, **the claimed behaviour is unobservable by construction**: `drillTo()` assigns `_s.chartSymbol[0] = '\0'` unconditionally on every list drill (`stockChart.cpp:75`), so whether or not `backToPrevView()` cleared it (`stockApp.cpp:314`) the subsequent list drill produces an index-keyed ticker either way. The id would need to read `stockChartTicker` **between** the back-to-list and the list drill — one command, at `:1417` — to test what it says it tests. Per rubric §2 (unreachable assertion, a skip that hides a real failure) this is BROKEN. |

---

## 6. Order dependence — the brief's first question

### 6.1 `set stockMode 0` (WP-B cluster C1): who depends on it, who is damaged

`_switch_to_stock` issues `dut.cmd("set stockMode 0")` before every
`switchApp` (`_helpers.py:201`); `_restore_from_stock` restores the app and
nothing else (`:210-217`). WP-B filed the leak as **B-5** (P2). This section
answers the two questions **B-5** did not: which ids *need* the write, and
which are *damaged* by it.

**Who depends on it — 27 of 30, hard.** `set stockMode m` writes
`g_settings.stockMode` (`stockApp.cpp:212-216`), which `init()` and — on a
mode change — `resume()` feed to `_applyLaunchView()`
(`stockApp.cpp:32`, `:51-53`, `:62-76`). Without the write, a board whose
persisted mode is Chart or Heatmap launches Stock into a detail view, and
every id whose first act is a list-row tap (`T174`–`T182`, `T183`, `T186`–
`T188`, `T204`) taps into a chart body where the row branch does not exist
(`stockApp.cpp:110-130`). The write is not gratuitous; it is the precondition
that makes a list-centric suite deterministic, and TASK-247's comment
(`_helpers.py:197-200`) says exactly that.

**Who is damaged by it — three, in two different ways.**

* **`T231` is damaged directly, and works around it.** Its whole subject is
  that `stockMode` is honoured at launch, so it cannot use a helper that pins
  the mode; `_enter_stock_no_force` (`stock.py:626-634`) exists solely to
  bypass `_switch_to_stock`. The workaround is correct and documented — but
  it means the family's one launch-view test is the one test that cannot use
  the family's entry helper.
* **`T169`'s launch-view assertion is hollowed by it.** `stockSubView ==
  "list"` (`:94-97`) is asserted immediately after the helper wrote the mode
  that produces it. As an *app-switch* assertion the row is sound (§1); as
  the "list on first launch" claim its plan entry makes
  (`test_plan.md:1799`), it is `T231`'s List leg with the input supplied by
  the harness.
* **The user's setting is damaged permanently, conditionally.** `dbgSet`
  writes `g_settings.stockMode` in RAM without saving
  (`stockApp.cpp:215`) — the helper's comment calls it *"in-RAM only, not
  persisted"* and that is true **of the write**. It is not true of the
  outcome: `SettingsStorage::save()` serialises the whole struct including
  `s["mode"]` (`settingsStorage.cpp:499`), and any later save in the same
  boot — a Settings-section test, an eject toggle via `persistPlayerMode`
  (`appShell.cpp:64-68`), a WiFi connect — writes the suite's `List` over the
  user's choice for good. A full `run/test` performs several. **G-4.**

**The fix is one context manager**, exactly as **B-5** proposed: snapshot
`get`-side `stockMode` on entry and restore it on exit, alongside
`_bgpoll_suspended` (`_helpers.py:444-454`) as the pattern. Note that the
snapshot half needs a firmware change — `stockMode` is settable but **not
gettable** (`stockApp.cpp:134-201` has no case; the same asymmetry as
**G-3**), so today the helper cannot know what it is overwriting.

### 6.2 The leak WP-B did not have — `prevSubView`, new cluster `C10` (**G-1**)

This is the package's headline finding, and it is a firmware/harness
interaction that only appears when the two are read together.

**The mechanism, in four lines of firmware.**

1. `set triggerHeatmap 1` assigns `_s.prevSubView = _s.subView` before
   forcing the sub-view (`stockApp.cpp:248-249`).
2. `backToPrevView()` assigns `subView = prevSubView`, and rewrites
   `prevSubView` **only** when the destination is `HeatmapDetail`
   (`stockApp.cpp:312-315`).
3. Therefore `prevSubView == ChartDetail` is a fixed point: the chart back
   zone maps `Chart → Chart`, and the heatmap HEAT zone maps
   `Heatmap → Chart` with `prevSubView` still `ChartDetail`.
4. Nothing in the entry path clears it. `switchApp` calls `resume()`, not
   `init()`, after the first launch (`appShell.cpp:200-207`), and `resume()`
   re-applies the launch view only on a mode change (`stockApp.cpp:51-53`) —
   which `_switch_to_stock`'s unconditional `set stockMode 0` guarantees does
   not happen. So an app switch does not clear it, a reboot does, and
   `_heatmap.enter()` or a `drillToBySym` does.

**In production the fixed point is unreachable.** `drillTo` and
`drillToBySym` stamp `prevSubView` from the current sub-view, which from the
List or Heatmap branches of `handleInput` is `List` or `HeatmapDetail`
(`stockChart.cpp:73`, `:93`), and `enter()` hardcodes `List`
(`stockHeatmap.cpp:26`). **Only `set triggerHeatmap` can write
`prevSubView = ChartDetail`,** and only if it is issued while the sub-view is
already `ChartDetail`.

**`T196` issues it exactly there.** Registry order is
`… T188 (47), T204 (48), T196 (49), T200 (50), T201 (51), T202 (52),
T203 (53), T192 (54), T193 (55) …` (measured with
`build_all_tests()` — see §0). `T204` drills AAPL and taps range tabs and
never navigates back, so it exits with `subView = ChartDetail`
(`stock.py:901-943`); `T188` before it does the same (`:833-873`). `T196`
then calls `_switch_to_stock` — which resumes into that chart view — and
issues `set triggerHeatmap 1` with **no sub-view normalisation**
(`stock.py:994-998`). `prevSubView := ChartDetail`.

**Predicted blast radius.** `T196` itself passes (its two terms are the
injected sub-view and the surviving `heatmapCount`) and exits at heatmap.
Every id behind it enters through `_ensure_stock_list_view`
(`stock.py:967-986`), whose three-iteration loop now cannot terminate:

| iteration | `stockSubView` read | action | firmware result |
|---|---|---|---|
| 1 | `heatmap` | `tap 220 10` | `backToPrevView()` → `subView = ChartDetail` (`stockApp.cpp:101`, `:313`) |
| 2 | `chart` | `tap 10 7` | `backToPrevView()` → `subView = ChartDetail` again (`:112-113`) |
| 3 | `chart` | `tap 10 7` | unchanged |
| final read | `chart` ≠ `list` | — | `return False` (`:986`) |

so `T200`, `T201`, `T202`, `T203`, `T192`, `T193` and `T194` all exit
`SKIP: could not normalize to list view`. **Seven ids — the entire stock-002
block — become a permanent non-result in full-suite order**, and because the
three bodies that could repair the wedge (`T192`/`T193`/`T194`, via a tile
drill's `drillToBySym`) are themselves behind it, nothing recovers within the
family.

**And it does not stop at the family.** The six CORE Stock drivers run
*later* in the current registry order — `T-BUSY-01` (172), `T-BUSY-01b`
(173), `T-BUSY-05` (176), `T-CDWN-02` (178), `T-CDWN-03` (179), `T-UART-01`
(203) — and all six need Stock's List view to drill a row. `T-BUSY-01`'s
`dut.cmd("tap 10 7")  # back tap — no-op if already in list`
(`shell.py:1669`) is a no-op in the wedge for the opposite reason, its
`tap 137 36` then lands in the chart body, and its oracle
`_poll_chart_len_positive` reads a `chartLen` left non-zero by an earlier
fetch — i.e. it passes **vacuously**, having drilled nothing. The three
mid-suite reboots that would clear the wedge (`T_PR_04` at 20, `T_PRM_01` at
23, `T_PLR_26` at 111) are all *before* index 49 in the current order and
would be *after* the CORE block under the class-ordered switch (WP-B **B-8**),
so neither order repairs it.

**Why nobody has seen it.** An isolated `./run/test-targeted T200` cold-boots
(`_diag_snapshot`'s docstring, `_helpers.py:335-337`), so `prevSubView` is
`List` and the id passes; the wedge exists only in the full-suite path. That
is exactly the split
`feedback_isolated_rerun_vs_suite_state` describes, and the same shape as
WP-F **F-4**. `_order.py` adjudicates `T196` as VACUITY on the *count* term
(`:221-224`) — true, and orthogonal to the `prevSubView` write, which no
entry in `EDGE_ADJUDICATION` mentions.

**Two fixes, both one line.** In the suite: call `_ensure_stock_list_view`
before `set triggerHeatmap 1` in `T196` (`stock.py:997`), which every other
heatmap id already does. In the firmware, better: make `backToPrevView()`
self-healing by treating `ChartDetail` as `List`, or make `dbgSet`'s
`triggerHeatmap` stamp `prevSubView = List` the way `enter()` does
(`stockHeatmap.cpp:26`) — the injector's job is to reproduce
`enter()`, and it currently does not. Proposed as WP-B §5.2 cluster **C10**.

### 6.3 The other three surfaces the brief asked about

* **The chart tab (`chartRange`).** Leaked by ten ids and consumed by three.
  `T177`, `T180`, `T188`, `T204`, `T192`, `T194` all leave a non-D1 range
  installed; nothing restores it. It is harmless only because every
  consumer's precondition is a fresh drill, and `drillTo()` resets the range
  to D1 unconditionally (`stockChart.cpp:76`). The one id that would be
  damaged is `T180`, whose subject *is* that reset — and it is protected by
  the same firmware line, so the leak is real but currently inert. Worth
  recording in `_order.py` rather than fixing.
* **The selected row / `chartSymbol`.** `T202`, `T192` and `T193` exit with
  `chartSymbol` set to a screener symbol. Every consumer either normalises
  (`_ensure_stock_list_view`) or drills from a list row, and `drillTo()`
  clears `chartSymbol` unconditionally (`stockChart.cpp:75`) — the same
  accidental protection, and the reason `T194`'s claim is unobservable (§5).
* **The watchlist.** No suite file writes it: `dbgSet` has no ticker case
  (`stockApp.cpp:204-255`) and `settingsDbgSet` is not used by this family.
  But four ids **read** it as a literal — `"NVDA"` in `T174`/`T181`/`T187`,
  `"MSFT"` in `T186` — against `kDefTickers` (`settingsStorage.cpp:91`),
  which is a *persisted user setting* editable from Settings
  (`settings/appsSection.h`) and wiped by `run/flash-fs`. A reconfigured
  watchlist turns four SOUND ids red for a reason that is not a regression.
  **G-9**.
* **Quote-fetch state.** `lastQuoteFetch` is the only cross-id dependency and
  it runs both ways: `T173` **needs** a predecessor's fetch
  (`_order.py:217-220`) and `T178` needs the pipeline **quiet**
  (`:200-207`). `fetchFailed`/`fetchErrorCode` are injected by `T183`,
  `T184` and `T185`; the first two clear up, `T185` leaves
  `fetchErrorCode = -99` behind (nothing reads it — **G-3**) and relies on
  `triggerFetch` to have cleared `fetchFailed`. The three ids downstream
  that would care (`T186`, `T187`, `T188`, `T204`) all clear it defensively
  on entry.

---

## 7. Network dependence — the brief's second question

### 7.1 How much of the family needs a live upstream at all

**Sixteen of thirty ids need no successful fetch.** `drillTo()` assigns the
sub-view, the ticker index and the range **synchronously**, before the
enqueue (`stockChart.cpp:73-77`), and `backToPrevView()`/`enter()` are pure
state transitions — so every navigation assertion in this family resolves
without Yahoo. That is `T169`, `T171`, `T172`, `T174`, `T175`, `T177`,
`T178`, `T179`, `T180`, `T181`, `T182`, `T183`, `T184`, `T231`, `T200`,
`T201`. It is a genuine strength and it is why the family's navigation
coverage is its best-graded part.

**Fourteen are fetch-dependent**: `T170`, `T173`, `T176`, `T185`, `T186`,
`T187`, `T188`, `T204` (Yahoo quote/chart), `T196`, `T202`, `T203`, `T192`,
`T193`, `T194` (the screener, then a chart).

### 7.2 Does each distinguish "the feature is broken" from "the upstream was slow"?

Mostly the *branching* is honest and the *messages* are not.

**Honest skips (S7 used correctly).** `T173`'s `baseline == 0`
(`:192-195`), `T176`'s 200 s drain timeout (`:296-300`), `T202`/`T203`'s
`heatmapCount == 0` after 60 s (`:1098-1101`, `:1147-1150`) and `T192`/
`T193`'s `shellBusy` never clearing (`:1232-1235`, `:1316-1319`) all name a
precondition the rig could not establish and decline to grade. None of them
hides a failure the id was built to catch.

**One dishonest skip, and it is the reason `T194` is BROKEN.**
`_wait_chart_complete` returning `False` — the tab-switch never fetched,
which is exactly the TASK-121 regression class — exits as
`skip("T194", "fetchOkCount did not advance on list-drilled tab-switch …")`
(`:1448-1454`). The identical construction in `T192` (`:1246-1249`) and
`T193` (`:1325-1333`) is a `fail()`. **G-6.**

**Three misattributing failure messages.** `T186`/`T187`'s
*"fetchOkCount did not advance after 45 s for {ticker} — **guard fix may not
have landed**"* (`:795`) and `T192`'s *"— **TASK-121 fix may be missing**"*
(`:1247`) blame a named firmware fix for what is, on this rig, most often a
slow or empty Yahoo response. The information that would separate the two is
in hand and discarded: `fetchFailed` distinguishes "the fetch resolved with
an error" from "no result arrived", and `stockChartProgress` reports which
phase it died in — `0=TLS/connect`, `1=GET/response`, `2=JSON-parse`,
`-1=idle` (`dataTaskStorage.cpp:553`, `:571`, `:615`, `:638`) — and
`_wait_chart_complete` **already reads and prints it on timeout**
(`_helpers.py:272-276`) without putting it in the `fail()` reason the three
callers construct. **G-10.**

**One skip that is arguably the honest choice made twice over.** `T193`'s
`chartLen <= 0` → *"Yahoo returned empty data (external API flakiness)"*
(`:1342-1344`). It is defensible; it is also the only place in the family
where an empty payload and a broken parser are indistinguishable, and
`fetchErrCount` (the cumulative `-91..-95` parse-error counter,
`stockShared.h:71`, exposed at `stockApp.cpp:163-167`) would separate them in
one read. **No suite file reads `fetchErrCount`** —
`grep -rn fetchErrCount app/tools/` returns nothing.

### 7.3 `activeError` vs `errorCode` — does Stock repeat the PlaneRadar mistake?

**No — and the reason is an accident.** The PlaneRadar lesson (memory
`project_planeradar_state`, TASK-313) is that `errorCode == 0` is ambiguous
and only the boolean `activeError` is reliable. Stock's boolean is
`_s.fetchFailed`, surfaced two ways: directly through
`get fetchFailed` (`stockApp.cpp:183-187`) and through
`get activeError`'s `active` field, which reads
`StockApp::hasError() { return _s.fetchFailed; }` when Stock is foreground
(`stockApp.h:38`, `cmdGet.cpp:242`). Its `errorCode` is
`_s.fetchErrorCode`, which is set on failure and zeroed on success
(`stockChart.cpp:137-143`, `stockApp.cpp:336-343`) — i.e. exactly as
ambiguous as PlaneRadar's.

**Every fetch-failure gate in the family reads the boolean.** `T178`
(`:403`), `T186`/`T187` (`:800`), `T188` (`:865`), `T204` (`:932`) all
compare `fetchFailed`; `fetchErrorCode` appears **only** inside `fail()`
message strings (`:147`, `:801`, `:861`, `:869`, `:937`). So the family gets
the right answer — but not by choosing it. `get fetchErrorCode` **does not
exist** (**G-3**): `StockApp::dbgGet` has no case for it
(`stockApp.cpp:134-201`), nothing else in `app/src/` answers it
(`grep -rn fetchErrorCode app/src/` → `stockShared.h:70`,
`stockChart.cpp:138`, `:143`), and `cmdGet`'s fallthrough returns
`{"ok":false,…,"error":"unknown var"}`. Every one of those five diagnostics
has been printing `fetchErrorCode=None` since it was written — including the
two that TASK-385/TASK-386 added specifically so a fetch failure would carry
its own evidence. Meanwhile `set fetchErrorCode` exists and is used by
`T183`/`T185` to inject a value nothing can read back.

**And the connecting half is unused.** `get activeError` also reports
`connecting`, which for Stock is `!_everHadData` (`stockApp.h:35`) — the
"never had *any* data since boot" latch, which is precisely the term that
separates "this fetch failed" from "this board has never reached Yahoo".
`grep -c activeError stock.py` → **0**.

---

## 8. What breaks if `stockShared.h` changes

The required section. Two firmware hit-tests decide everything here, and
both **clamp**, which is what makes the answer uncomfortable:

```c
rowIdx = constrain((y - ST_LIST_ROW_START_Y) / ST_LIST_ROW_H, 0, STOCK_TICKER_COUNT - 1);  // stockApp.cpp:95-96
tab    = constrain((x - ST_CHART_TABS_X)     / ST_CHART_TAB_W, 0, 3);                      // stockApp.cpp:117
```

A drifted coordinate can never produce a *miss*. It produces a **different
selection**, which only an id that asserts the selection can see. Nothing
under `app/tools/` parses any of these names
(`grep -rn "ST_LIST_ROW_H\|ST_CHART_TAB_W\|ST_CHART_TABS_X\|ST_LIST_ROW_START_Y\|ST_LIST_RULE_Y" app/tools/`
→ no hits), and `stock.py` uses `coords` exactly once, for `T182`'s taskbar
slot (`grep -c '_c\.' stock.py` → 1). WP-A **A-9** / **D4** / **D5** filed
this as P2; the counts in **D5** ("48 literal `tap 137 <y>` sites") are not
reproducible — re-measured, it is **16 in `stock.py`** and **31 suite-wide**
(`grep -rn 'tap 137 ' --include=*.py app/tools/ | wc -l`, across
`stock.py`, `shell.py` and `test_task488_partb.py`).

| Constant (`stockShared.h`) | Value | Mirrored as | Ids that fail **loudly** | Ids that go **silently wrong** |
|---|---|---|---|---|
| `ST_LIST_ROW_START_Y` :37 / `ST_LIST_ROW_H` :38 | 25 / 26 | 16 literal `tap 137 <y>` (`36`×10, `120`×1, `218`×2 in this file) + the arithmetic comments at `stock.py:15-16`, `:230`, `:756-757` | `T174`, `T181` (assert `stockChartTicker == "NVDA"` for `y=218` → row 7), `T186` (`"MSFT"`, `y=192` → row 6), `T187` (`"NVDA"`, `y=218`) | `T175`, `T176`, `T177`, `T180`, `T182`, `T188`, `T204`, `T194` — all drill `tap 137 36` and never read the ticker, so they keep drilling *some* row and keep passing. `T183` taps `y=120` and asserts the tap is **ignored**, so it cannot notice at all. **8 ids blind, 4 covered.** |
| `ST_CHART_TABS_X` :46 / `ST_CHART_TAB_W` :47 | 130 / 36 | `_TAB_XY = [(148,9),(184,9),(220,9),(256,9)]` (`stock.py:759`) + `tap 184 7` ×2 (`:340`, `:444`) + `tap 184 9` ×2 (`:1239`, `:1446`) | `T177` (asserts `stockChartRange == "D5"` after `x=184`), `T192` (same) | `T188` — taps all four x's and asserts only the counter, so a widened tab makes it fetch e.g. D1/D5/D5/Mo1 while still printing *"all 4 ranges (D1/D5/Mo1/Ytd) fetched"*, a **false coverage claim**. `T204` — `_TAB_XY[3]`/`_TAB_XY[0]` become Mo1/D1, silently converting the largest-vs-smallest-payload heap stress (`test_plan.md:2081`) into a smaller one. `T180` — its 5D tap is never read back, so a tap that lands on D1 makes the "resets to D1" assertion vacuously true. `T194` — no range assertion. **4 ids blind, 2 covered.** |
| `ST_CHART_HEADER_H` :43 / `ST_CHART_BACK_W` :44 | 18 / 30 (zone is `x < 2*W` = 60) | 15 literal `tap 10 7`, plus the **wrong** comment at `stock.py:266` (*"x=10 < ST_CHART_BACK_W(30)"* — the firmware tests `< 60`) | `T175`, `T184`, `T203`, `T231` — all assert a sub-view transition caused by the back tap, so a shrunken header makes the tap land in the plot area, the transition not happen, and the id fail | `_ensure_stock_list_view` (`:981`) — its back tap failing converts `T200`–`T203`, `T192`–`T194` into **skips**, not reds. **The zone is well covered by direct asserters and completely uncovered by the shared normaliser.** |
| `ST_LIST_RULE_Y` :36 | 22 | 10 literal `tap 220 10`, 1 `tap 260 7` (`:697`), 6 literal `tap 10 30` | `T200`, `T201`, `T231` (assert the sub-view flip caused by the HEAT zone), `T202`, `T203` (a raised rule line turns `tap 10 30` from a tile tap into a back tap → `subView` is `list`/`heatmap`, not `chart` → `fail`) | `_ensure_stock_list_view`'s heatmap branch and `T192`/`T193`/`T194`'s tile drills, all of which exit as **skips** |
| `STOCK_TICKER_COUNT` :17 | 8 | `_DEFAULT_TICKERS` (8 entries, `stock.py:106`), `0 <= prog < 8` (`:133`, `:141`) | — | Nothing asserts on it; a changed count only mislabels `T170`'s stuck-ticker diagnostic. Harmless, but it is a mirror of a `#define`. |
| `ST_CANVAS_X2` :34, `ST_CHART_PLOT_Y/H` :48-49, `ST_CHART_FOOTER_Y` :50 | 274 / 18 / 196 / 214 | Comments only (`stock.py:19`, `:319`, `:414`) | — | The plot-bounds and footer claims they belong to (`T176`, `T179`) are the manual halves nobody automated. |

**The two-sentence answer.** A change to `ST_LIST_ROW_START_Y`/`ST_LIST_ROW_H`
or to `ST_CHART_TABS_X`/`ST_CHART_TAB_W` is caught by six ids and missed by
twelve, because the firmware `constrain()`s both hit-tests so a drifted tap
selects a different row or tab instead of missing, and only the six ids that
read back `stockChartTicker` or `stockChartRange` can tell. A change to the
header, back or rule-line zones is the safer half — four ids assert a
sub-view transition through each of them and fail loudly — except that the
same drift silently disables `_ensure_stock_list_view`, which converts the
seven stock-002 ids from red to skip, the same non-result **G-1** produces.

---

## 9. Family findings

### 9.1 The test cannot fail for the reason it exists — S1 / S3 / S7

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **G-1** | **P1** | **New leakage cluster `C10` — `set triggerHeatmap` writes `prevSubView = ChartDetail`, which `backToPrevView()` cannot leave, and the whole stock-002 block behind it is predicted to be a permanent SKIP.** `dbgSet`'s `triggerHeatmap` stamps `_s.prevSubView = _s.subView` where `StockHeatmap::enter()` hardcodes `List`; `backToPrevView()` rewrites `prevSubView` only when the destination is `HeatmapDetail`, so `prevSubView == ChartDetail` is a fixed point that no app switch, no `resume()` and no later back tap clears. `T204` (index 48) exits in chart view, `T196` (49) injects without normalising, and `_ensure_stock_list_view`'s three-iteration loop then cannot terminate — `T200`, `T201`, `T202`, `T203`, `T192`, `T193`, `T194` all exit `SKIP: could not normalize to list view`. The six CORE Stock drivers at indices 172–203 need the same List view; `T-BUSY-01`'s `chartLen > 0` oracle passes vacuously on a stale value in that state. The three mid-suite reboots that would clear it are all earlier in the order (and later than the CORE block under the class-ordered switch, WP-B **B-8**). Isolated `run/test-targeted` reruns cold-boot and pass, which is why it has never been attributed. | `stockApp.cpp:246-253`, `:312-321`, `:51-53`, `:101`, `:112-113`; `stockHeatmap.cpp:26`; `stockChart.cpp:73`, `:93`; `appShell.cpp:200-207`; `stock.py:994-998`, `:901-943`, `:967-986`; `shell.py:1669`; §6.2 | Suite: call `_ensure_stock_list_view` before `set triggerHeatmap 1` in `T196` (one line, `stock.py:997`). Firmware, better: make `dbgSet`'s `triggerHeatmap` stamp `prevSubView = List` the way `enter()` does — the injector's job is to reproduce `enter()` and it does not. Then add `C10` to WP-B §5.2 and an `EDGE_ADJUDICATION` row for `T196`'s `prevSubView` write, which the existing VACUITY row does not cover. |
| **G-2** | **P1** | **The family's central fetch oracle defaults to an unconditional pass.** `_stock_ok_count` and `_stock_quote_ok_count` return `-1` when the reply is not `ok` or carries no `val`; `_wait_chart_complete(before=-1)` then satisfies `current > before` on its first poll and returns `True` without a fetch having happened. Nine ids snapshot a baseline that way — `T170`, `T176`, `T186`, `T187`, `T188` (×4), `T204` (×6), `T192`, `T193`, `T194` — and for `T170`, `T176` and `T204` the delta is the *only* oracle. The trigger is not hypothetical: `Dut.read_json` returns the **first** JSON line it sees (`lib/dut.py:1079-1091`), `_stock_get` never checks the reply's `var` field, and every stock body is issued into a documented serial flood from `stockTickQuotes`' 8-ticker batch (`stock.py:1412`, `:1419`). | `_helpers.py:225-233`, `:254-259`; `stock.py:58-66`, `:116`, `:301`, `:790`, `:850`, `:912`, `:1236`, `:1320`, `:1425`; `lib/dut.py:1079-1091`, `:1122-1136` | Make the two counters raise or return `None` on a bad read and have every caller `fail()` on it; and make `_stock_get` assert `r.get("var") == var`, which closes the raced-reply hazard for all 30 ids at one choke point. |
| **G-5** | **P1** | **`T172` and `T182` have no reachable `fail()` — the fifth and sixth instances of WP-D `D-2`.** Both end on `_check_residue`, whose `False` return — Spotify not repainting after the switch-back, i.e. the regression — exits as `skip()` with the reason *"Spotify not rendering (not playing?)"*. `T182` is worse: its taskbar-scroll miss (`:525-528`) and slot-tap miss (`:541-545`) are also skips, and its one remaining `fail()` (`:553-555`) is unreachable because the `name` check above it already skipped. So the cross-feature id that exists to prove the **real taskbar UI** reaches Stock cannot report a taskbar failure. `_check_residue`'s own docstring says *"Does not call fail() — caller decides on skip vs fail"*; six callers have now made the wrong choice. | `stock.py:174-178`, `:518-558`; `_helpers.py:177-192`; `M-TESTQUAL-D-audit-shell-review.md:216` | Change the `_check_residue is False` branch to `fail()` in both, and `fail()` on `T182`'s two taskbar misses. WP-D's D-2 fix should be applied to all six callers in one pass. |
| **G-6** | **P1** | **`T194` cannot fail for its claimed reason, three times over.** Its one `fail()` compares `stockChartTicker` against a read of the same field two commands earlier, with no firmware write in between (the tab handler performs no drill) — a value against itself. Its real oracle, `_wait_chart_complete`, exits via `skip()` on failure where the identical construction in `T192`/`T193` is a `fail()`. And the claimed behaviour is unobservable regardless: `drillTo()` clears `chartSymbol` unconditionally on every list drill, so whether `backToPrevView()` cleared it or not, the list-drilled ticker is index-keyed either way. | `stock.py:1434`, `:1448-1461`; `stockChart.cpp:75`; `stockApp.cpp:116-127`, `:314` | Read `stockChartTicker` **between** the back-to-list and the list drill (one command at `:1417`) and assert it is empty/index-keyed there; convert the `_wait_chart_complete` skip to a `fail()`; assert `list_ticker == "AAPL"` rather than against itself. |
| **G-7** | **P1** | **`T178` and `T185` assert values their own injection wrote.** `set triggerFetch 1` assigns `chartLen = 0` **and** `fetchFailed = false` (and the drill-in assigns `chartLen = 0` again) — which is `T178`'s entire oracle. The same command clears the error `T185` injected one line earlier, before any fetch runs, so *"error clears on successful fetch"* is performed by the injector and `fetchFailed` is never re-read; `T185`'s remaining term, `lastQuoteFetch != baseline`, is an **enqueue** stamp (`stockTickQuotes` writes it at `dataTask::enqueue` time), so it resolves in one tick whether or not the upstream ever answers. TASK-112 diagnosed the enqueue-proxy problem and fixed `T170` with `quoteOkCount`; `T185` was left behind, and `T178`'s audit-001 "fix" replaced a hardcoded-default tautology with a harness-write tautology. | `stockApp.cpp:222-233`, `:325-327`, `:338`; `stockChart.cpp:86`; `stock.py:387-406`, `:734-747`, `:42-55`; `test_plan.md:2106-2111`, `:2120-2124` | `T185`: assert `quoteOkCount` advances **and** `fetchFailed == false` afterwards, and inject the error *after* `triggerFetch` so the fetch is what clears it. `T178`: assert the placeholder **render** via `run/screendump` (the flat mid-line + `lo: ---`/`hi: ---`, `stockChart.cpp:34-36`, `:56-59`), or retire the id and keep it as the ordering canary `_order.py` values it for. |

### 9.2 Oracles narrower than the claim — S6 / S8 / S2

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **G-8** | **P2** | **Three ids drive the range tabs and none of them reads the range back.** `T188` taps all four `_TAB_XY` coordinates and asserts only the counter and `fetchFailed`, then reports *"all 4 ranges (D1/D5/Mo1/Ytd) fetched"* — a coverage claim it never checked. `T204`'s Ytd↔D1 alternation is the same, and there the range **is** the subject: the plan's rationale is the largest-vs-smallest JSON payload. `T180`'s mid-sequence 5D tap is never read back either, so a tap that silently landed on D1 makes its "resets to D1" assertion vacuously true. `T177` and `T192` do the read, one line after an identical tap. | `stock.py:848-874`, `:909-944`, `:444`; `:342`, `:1241`; `stockApp.cpp:116-118`; `test_plan.md:2081` | One `get stockChartRange` assertion per tab tap in `T188`/`T204` and after `T180`'s 5D tap. |
| **G-3** | **P2** | **`get fetchErrorCode` does not exist, so every stock fetch-failure diagnostic prints `None`.** `StockApp::dbgGet` has no case for it and nothing else in `app/src/` answers it, so `cmdGet` returns `{"ok":false,…,"error":"unknown var"}`. Five `fail()` messages interpolate it — `T170`, `T186`/`T187`, `T188` (×2), `T204` (×2) — including the two TASK-385/TASK-386 added specifically so a failure would carry its own evidence. `set fetchErrorCode` exists and is used by `T183`/`T185` to inject a value nothing can read back. The related `fetchErrCount` (cumulative parse errors, the term that separates an empty upstream from a broken parser) **is** exposed and is read by no suite file at all. | `stockApp.cpp:134-201`, `:163-167`, `:218-221`; `grep -rn fetchErrorCode app/src/` → `stockShared.h:70`, `stockChart.cpp:138`, `:143`; `cmdGet.cpp` fallthrough; `stock.py:143`, `:798`, `:856`, `:864`, `:931`; `grep -rn fetchErrCount app/tools/` → nothing | Add the `fetchErrorCode` (and `chartLo`/`chartHi`, `lastHeatmapFetch`, `stockMode`) cases to `dbgGet` — the struct fields all exist — and gate `T193`'s "Yahoo returned empty" skip on `fetchErrCount` so an empty payload and a parse failure stop being the same result. |
| **G-4** | **P2** | **`set stockMode 0` leaks (WP-B `B-5`) and the "in-RAM only" comment is true of the write but not of the outcome.** `_switch_to_stock` writes it on every one of ~40 entries and `_restore_from_stock` restores the app only. 27 of the 30 ids genuinely need the write; the damage is that `SettingsStorage::save()` serialises `s["mode"]` from the same struct, so any later save in the same boot — a Settings test, an eject toggle via `persistPlayerMode`, a WiFi connect — makes the suite's `List` the user's persisted preference permanently. It also hollows `T169`'s launch-view term and forces `T231` to bypass the family's own entry helper. **The restore cannot be written today**: `stockMode` is settable but not gettable, so the helper cannot snapshot what it overwrites. | `_helpers.py:195-217`; `stockApp.cpp:212-216`; `settingsStorage.cpp:499`; `appShell.cpp:64-68`; `stock.py:626-634`, `:94-97`; WP-B `:445`, `:710` | Add `stockMode` to `dbgGet`, then make `_switch_to_stock` a snapshot/restore context manager alongside `_bgpoll_suspended` — the fix `B-5` proposed, now with its missing precondition named. |
| **G-9** | **P2** | **Four ids assert ticker strings that are a persisted user setting, not a firmware constant.** `"NVDA"` (`T174`, `T181`, `T187`) and `"MSFT"` (`T186`) mirror `kDefTickers[7]`/`[6]`, which the Settings → Stock section can edit, `settings.json` persists and `run/flash-fs` wipes. A reconfigured watchlist turns four otherwise-SOUND ids red for something that is not a regression — and these are precisely the four ids §8 relies on to detect a row-geometry drift, so the mirror that protects the family is also its most fragile assertion. | `stock.py:230`, `:484`, `:809`, `:815`; `settingsStorage.cpp:91`, `:258`, `:498`; `settings/appsSection.h` | Read `get stockTicker7` / `get stockTicker6` (both already exposed, `stockApp.cpp:193-200`) and assert `stockChartTicker` equals **that**, not a literal. This is the parse-don't-mirror fix and the getter already exists. |
| **G-13** | **P2** | **`T182` is the family's only taskbar test and is scoped `Stock`.** Its plan entry declares it cross-feature against `stock-001` **and** `taskbar-scroll-001`, its body drives the scroll drag, asserts `tbScrollOffset == 2` and computes a physical slot from `APP_SLOT`, and the module-seeded record gives it `scope=Stock` — so `./run/test-targeted --scope taskbar` misses it. No `@meta(...)` appears anywhere in this module; the mechanism is two files away (`player.py:1750`). Stock instance of WP-E **E-5** / WP-F **F-11**. | §0's command output; `stock.py:500-558`; `test_plan.md:1934-1943`; `_meta.py:29-33` | `@meta(scope="taskbar", scope_reason="cross-feature")` on `t182`. |

### 9.3 Records, messages and hygiene — S10 / S11 / S12 / S13

| # | Sev | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| **G-11** | **P2** | **`T231` collides with an unrelated plan entry.** `test_plan.md:4109` declares `### T231 — [app-settings-wire-001] Aquarium speed slow/fast visually distinct [MANUAL]`; the only body carrying the id is the Stock launch-view test, and `build_all_meta` shows no second body. Any coverage claim citing `T231` is ambiguous, and the plan's heading is a bound C6 doc entry pointing at a body that does not implement it. Stock instance of WP-F **F-2**. | `test_plan.md:4109`; `stock.py:637-722`; §0's command output | Re-id one of the two and record the rename, or retire the Aquarium heading — an Architect/VE call, not a code change. |
| **G-10** | **P3** | **Three failure messages attribute an upstream timeout to a named firmware fix.** `T186`/`T187`: *"fetchOkCount did not advance after 45 s for {ticker} — **guard fix may not have landed**"*; `T192`: *"— **TASK-121 fix may be missing**"*. On this rig the far commoner cause is a slow or empty Yahoo response, and the discriminator is already read and printed by the helper and then dropped: `_wait_chart_complete` reports `stockChartProgress` (`0=TLS/connect`, `1=GET/response`, `2=JSON-parse`, `-1=idle`) on timeout but the three callers do not put it in the `fail()` reason. | `stock.py:795`, `:1247`; `_helpers.py:272-276`; `dataTaskStorage.cpp:553`, `:571`, `:615`, `:638` | Have `_wait_chart_complete` return the phase (or a small record) and interpolate it into every caller's `fail()` reason. |
| **G-12** | **P3** | **Four plan entries no longer describe their bodies.** `### T170` still specifies the retired `lastQuoteFetch > 0` proxy (the live description is the audit-001 row at `:2106`); `### T176` still specifies `lastChartFetch > 0` (live row at `:2101`); `### T178`'s Steps assert `stockSubView`/`stockChartRange` while the body asserts `chartLen`/`fetchFailed` (live row at `:2120`); `### T202`'s Steps specify `tap 137 130` while the body taps `(10,30)` — its own trailing note records the change, its Steps block does not. A reader triaging a red run reads the wrong steps first. | `test_plan.md:1802-1811` vs `:2106-2111`; `:1868-1877` vs `:2101-2105`; `:1890-1899` vs `:2120-2124`; `:2444` vs `stock.py:1114` | Fold the audit-001 fix rows into the primary entries and delete the duplicates; correct `T202`'s Steps. |
| **G-14** | **P3** | **`T169`'s flake candidacy is attributed to a dependency it does not have.** `flaky.yaml:155-156` notes *"yahoo/network flakiness, long-standing"*; the body performs a `switchApp` round trip and three `get`s and touches no upstream. Its real failure mode is a serial-flood timeout on `get appId` while `_applyLaunchView()`'s 8-ticker quote batch is in flight — which is why it is also the only body in the file that wraps the switch in `_bgpoll_suspended`. Investigating it as a network flake will not converge. | `flaky.yaml:155-156`; `stock.py:75-101`; `stockApp.cpp:71` | Re-word the candidate note to "serial contention during the launch quote batch", and measure it before it earns a declaration. |
| **G-15** | **P3** | **Uncited thresholds throughout.** `65.0` twice (`T170`, `T185` — presumably `STOCK_QUOTE_FETCH_MS + 5`, nothing says so), `45.0` nine times, `60.0` three times, `200.0` for the pipeline drain, `20.0` for `T170`'s stuck-ticker window, `5.0` for `T177`'s enqueue poll, and every sleep in the file. Not one is tied to a firmware constant or a dated measurement, although `STOCK_QUOTE_FETCH_MS`, `STOCK_CHART_FETCH_D1`, `STOCK_CHART_FETCH_SLOW` and `STOCK_HEATMAP_FETCH_MS` are four adjacent `#define`s in the header the suite already needs to parse for **G-8**/§8. | `stockShared.h:18-21`; `stock.py:42`, `:118`, `:311`, `:344`, `:742`, `:793`, `:854`, `:921`, `:1009`, `:1246`, `:1325`, `:1448` | Parse the four `#define`s alongside the layout constants and derive the budgets from them. |
| **G-16** | **P3** | **`T171` and `T179` are registry ids whose entire body is one `skip()`.** No device read, no branch, no assertion. Both are honestly labelled `[MANUAL]` and both plan entries say *"manual only (no pixel-read command)"* — a premise that is now stale, since `run/screendump` exists and four WebRadio ids use it for exactly this kind of claim. Meanwhile they are counted in the 213-id total and in `--scope Stock`'s 30. `T179`'s numeric half (`lo < hi`) needs only a `dbgGet` case for `chartLo`/`chartHi`, which **G-3** already proposes. | `stock.py:155-158`, `:411-414`; `test_plan.md:1813-1822`, `:1901-1910`; `webradio.py:1398-1428` | Automate `T179` via `chartLo`/`chartHi` and `T171` via a screendump colour sample, or move both out of the registry into a documented manual checklist so the id count stops overstating coverage. |
| **G-17** | **P3** | **The TASK-385/386 heap diagnostics are never compared to anything.** `T204` takes eight `_diag_snapshot`s and `T193` three, with comments stating the hypothesis is a *trend* in `freeInt`/`lfbInt` across the cycle — and every snapshot is printed or interpolated into a `fail()` string. No threshold, no delta, no assertion. The "under heap pressure" half of `T204`'s claim cannot fail. `T204`'s `entry_diag` is also taken **before** `_switch_to_stock`, so on the skip path it snapshots Spotify. | `stock.py:890`, `:917`, `:1268`, `:1323`, `:1329`; `_helpers.py:334-375` | Assert a floor on `lfbInt` at the last cycle relative to the first (the trend the comment names), sourced from `mem_manifest.yaml`; move `entry_diag` after the switch. |
| **G-18** | **P3** | **Two comments state the firmware wrongly, in the direction that hides a bug.** `stock.py:266` says the back tap works because *"x=10 < ST_CHART_BACK_W(30)"* — the firmware tests `x < ST_CHART_BACK_W * 2` (60), so the comment understates the zone by half and would mislead anyone narrowing the glyph. `stock.py:343` says *"lastChartFetch resets to 0 on tab change, then advances when enqueue fires"* — nothing resets it; the tab handler overwrites it in place, which is why `T177`'s `> 0` poll is vacuous (**G-8**'s sibling). Also `stock.py:23` documents the heatmap canvas as `y=22..239` from `ST_LIST_RULE_Y`, which is correct and is the only place in the file that names a constant at all. | `stock.py:266` vs `stockApp.cpp:112`; `stock.py:343` vs `stockApp.cpp:124`; `stock.py:21-26` | Two one-line corrections. |

---

## 10. Counts

### 10.1 The 30 registry ids

| Verdict | Nav (7) | Chart/tabs (7) | Error/mode (4) | Stream-parse (4) | Heatmap (8) | **Total** |
|---|---|---|---|---|---|---|
| SOUND | 3 | 1 | 2 | 2 | 4 | **12** |
| WEAK | 2 | 3 | 1 | 2 | 3 | **11** |
| HOLLOW | 1 | 2 | 1 | 0 | 0 | **4** |
| BROKEN | 1 | 1 | 0 | 0 | 1 | **3** |
| **total** | **7** | **7** | **4** | **4** | **8** | **30** |

* **SOUND:** `T169`, `T174`, `T175`, `T181`, `T184`, `T231`, `T186`, `T187`,
  `T200`, `T201`, `T203`, `T192`.
* **WEAK:** `T170`, `T173`, `T176`, `T177`, `T180`, `T183`, `T188`, `T204`,
  `T196`, `T202`, `T193`.
* **HOLLOW:** `T171`, `T178`, `T179`, `T185`.
* **BROKEN:** `T172`, `T182`, `T194`.

**40 % SOUND — the worst per-test result in the review**, below WP-F's 50 %,
WP-D's 56 %, WP-C's 59 % and WP-E's 77 %. Three properties of this family
explain most of it, and none is laziness:

* **Half of what the plan asks for is a pixel claim, and the family never got
  a pixel instrument.** `T171` (colour coding), `T179` (footer lo/hi), the
  manual halves of `T176` (plot bounds) and `T178` (placeholder render), and
  `T183`'s error screen are all render assertions. That is five ids' worth of
  intended coverage sitting on `[MANUAL]`, in a family whose renderers
  (`repaintList`, `StockChart::repaint`, `StockHeatmap::repaint`) are 200
  lines of deterministic drawing with no `dbgGet` surface at all.
* **The observables were never designed for the tests.** The one exception
  proves it: `quoteOkCount`/`fetchOkCount` were added *by* TASK-112 as a
  test-quality fix, and the four SOUND fetch ids are exactly the ones built
  on them. Everywhere the suite wanted a value that was not added on purpose
  — `chartLo`/`chartHi`, `lastHeatmapFetch`, `heatmapData.ok`, `stockMode`,
  `fetchErrorCode` — it either reached for an injection round trip (S3, four
  ids) or handed the claim to a human (S4, three ids). WP-E's lesson, third
  repetition: **the quality of a test tracks the quality of the observable it
  was given.**
* **The firmware clamps every coordinate the suite mirrors**, so the twelve
  ids that do not read back their selection cannot detect a layout drift
  (§8) — a structural ceiling on the verdicts, not a per-test defect.

### 10.2 Smell histogram

113 occurrences across the 30 rows (a row may carry several).

| Code | Smell | Count |
|---|---|---|
| S14 | State leakage | **28** |
| S7 | Skip-as-pass | 16 |
| S10 | Magic value | 16 |
| S8 | Vacuous bound | 11 |
| S6 | Defaulting oracle | 10 |
| S13 | Overlap | 9 |
| S3 | Tautology | 8 |
| S11 | Double bookkeeping | 5 |
| S1 | Unconditional pass | 3 |
| S4 | Deferred to a human | 3 |
| S5 | Swallowed failure | 2 |
| S2 | Ack-not-effect | 1 |
| S12 | Wrong-id / mis-scoped record | 1 |
| S9 | Fixed-sleep synchronisation | 0 |

Four things in that distribution belong to this family rather than to the
sample.

* **S14 is 28 of 30** — every id except the two that do nothing. Like WP-F's
  30 of 30 it is a property of a rich mutable surface (`stockMode`,
  `subView`, `prevSubView`, `chartSymbol`, `chartRange`, `chartTickerIdx`,
  `fetchFailed`, `fetchErrorCode`, the three fetch timestamps, `bgPoll`) —
  but unlike WP-F's, most of it is *inert*, because `drillTo()` and
  `_applyLaunchView()` happen to reset the leaked fields on the next entry.
  Exactly one leaked field has no such reset — `prevSubView` — and that one
  is **G-1**.
* **S6 is 10, the highest in the review, and it is one helper.** Nine of the
  ten are the `-1` baseline (**G-2**); the tenth is `T202`'s
  `r_sym.get("val", "?")`. WP-F recorded that its family's defaults were
  overwhelmingly in the *safe* direction; this family's are not, and they sit
  on the term that decides the verdict.
* **S9 is zero, and that is real.** Every wait in the file is either a
  counter poll, a `_wait_shell_not_busy` gate on `g_shellBusy`, or a
  `_drain_data_pipeline` gate on `get dataq`. The `time.sleep()` calls are
  post-tap settle delays with the assertion *after* them, not the oracle.
  For a family this fetch-heavy that is a genuine engineering result, and it
  is the TASK-299/300 work showing.
* **S3 is 8 against WP-F's 4.** The shape differs: WP-F's tautologies were
  `set X` / `get X` on the same byte; four of these eight are a *value the
  test wrote through a different command* (`triggerFetch` → `chartLen`,
  `triggerHeatmap` → `subView`) and three are a field compared against an
  earlier read of itself. Harder to spot, same consequence.

---

## 11. NEEDS-DUT

Static reading cannot settle these. Each is stated as the question hardware
would answer, with the prediction that would confirm or refute it.

1. **G-1 — does the `prevSubView` wedge actually fire?** Run
   `./run/test-targeted --scope Stock` with a serial capture.
   **Prediction:** `T196` PASSes and `T200`, `T201`, `T202`, `T203`, `T192`,
   `T193`, `T194` all report `SKIP: could not normalize to list view`.
   Confirm the mechanism directly by issuing `get stockSubView` after each of
   `_ensure_stock_list_view`'s three taps — the sequence should read
   `heatmap → chart → chart → chart`. If it fires, the seven ids have not
   been covering anything in a full run and the fix is one line.
2. **G-1 (b) — the isolated/in-suite split.** `./run/test-targeted T200` from
   a cold boot versus `T204,T196,T200` in that order.
   **Prediction:** isolated PASS, in-sequence SKIP — the
   `feedback_isolated_rerun_vs_suite_state` signature, and the reason nothing
   has attributed it.
3. **G-1 (c) — does it reach the CORE block?** Read `get stockSubView`
   immediately before `T-BUSY-01` (index 172) in a full run, and read
   `get chartLen` before and after its `tap 137 36`.
   **Prediction:** `subView == "chart"` on entry, `chartLen` identical across
   the tap, and `T-BUSY-01` PASSes without having drilled — a vacuous green
   on a CORE id, which is a gate question, not a family question.
4. **G-2 — how often does the `-1` baseline actually happen?** Instrument
   `_stock_ok_count` to print when it returns `-1` and run the family once.
   **Prediction (open):** if it ever fires during the nine snapshot reads,
   that id passed without observing a fetch, and the fix is mandatory rather
   than defensive.
5. **`T173`'s 60 s window.** Log `millis()` and `lastQuoteFetch` at `T173`'s
   entry across a full run. **Prediction:** on some runs
   `now - lastQuoteFetch > STOCK_QUOTE_FETCH_MS` already at entry, and the
   id reports *"unexpected re-fetch on resume"* — a false red, not a cache
   regression. Also record `stockSubView` at entry: if it is not `list`, the
   assertion was pre-satisfied and the pass was vacuous.
6. **`T204`'s heap trend.** The eight `_diag_snapshot` lines are already
   printed; nobody has compared them. Extract `lfbInt` per cycle from one
   captured run. **Prediction (open):** if the trend is flat, `T204`'s
   "under heap pressure" premise never held and the id is `T188` with more
   taps; if it declines, the assertion **G-17** proposes has a threshold.
7. **Which ticker is row 0?** `get stockTicker0` … `get stockTicker7` on the
   DUT as configured. The question is whether this board's watchlist is still
   `kDefTickers`, i.e. whether `T174`/`T181`/`T186`/`T187` are currently
   asserting against the settings the firmware defaults to or against
   something a Settings test left behind (**G-9**).
8. **Do `T171`/`T179` have a screendump-based form?** One `run/screendump`
   with Stock in list view after a fetch, and one in chart view, would settle
   whether the colour and footer claims are automatable at this resolution —
   the premise `test_plan.md` records as "no pixel-read command" is stale
   (**G-16**).

---

## 12. Handover

* Findings that belong to WP-Z's consolidation rather than to this family:
  **G-1** (a new state-leakage cluster `C10` for WP-B §5.2, with a predicted
  seven-id non-result and a vacuous CORE pass behind it — the largest single
  coverage hole the review has found), **G-2** (a shared-helper defaulting
  hole reaching nine ids in this family and every other caller of
  `_wait_chart_complete`), **G-5** (the fifth and sixth callers of
  `_check_residue` making WP-D **D-2**'s wrong choice — the fix should be one
  pass over all six), **G-3** (a firmware debug-surface gap: five getters the
  suite needs and one it has been printing as `None` for months), and
  **G-11** (a `test_plan.md` id collision, second instance after WP-F
  **F-2**).
* Cross-references to prior packages, cited not re-derived: **G-5** is WP-D
  **D-2**; **G-4** extends WP-B **B-5**/cluster `C1` with the persistence
  path and the missing getter; **G-13** is WP-E **E-5** / WP-F **F-11**;
  **G-11** is WP-F **F-2**; §8 answers WP-A **A-9**/**D4**/**D5** and
  corrects **D5**'s literal count (16 in `stock.py`, 31 suite-wide, not 48);
  **G-1**'s isolated-vs-suite signature is WP-F **F-4**'s shape in a
  different subsystem; the raced-reply hazard behind **G-2** is WP-C
  **C-18**'s `get cooldown`/`get shellCooldown` problem generalised — no
  `_stock_get` caller checks the reply's `var`.
* The corpus was re-measured at **30 ids, not the 40 the index carried**;
  §3's row is corrected in this package's index edit and the rollup uses 30.
* The structural contrast worth carrying forward. WP-C: *a failure that does
  not block*. WP-D: *a test that does not run*. WP-E: *a test that leaves the
  board changed*. WP-F: *a test that measures a proxy and a harness that
  leaves the proxy armed*. WP-G: **a test whose subject is on the screen and
  whose oracle is in a struct.** Five ids' worth of render claims are parked
  on `[MANUAL]`, four ids assert a value the harness itself wrote through a
  second command, twelve ids tap coordinates the firmware clamps so a drift
  selects the wrong thing silently — and the one leaked field the firmware
  does *not* happen to reset on the next entry takes seven ids and one CORE
  id down with it in every full-suite run.
* Nothing under `app/` or `run/` was modified. Nothing under `app/tools/` was
  imported except `suite.serialdbg.build_all_tests`/`build_all_meta`.
  `./run/check-docs` was run once before handover; the C6 result is recorded
  in the index ledger entry for this package.
