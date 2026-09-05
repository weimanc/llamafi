# App-conformance exceptions — the A5/A6 ledger

> Owner: **@VE** · Machine-read by `app/tools/gate/check_app_conformance.py` · Opened **2026-08-18**
> Gate: `run/check` gate 9 (`app/tools/smoke_test.sh`) · Landing task: **TASK-483**
> Design: [M-TESTARCH §2.3](../architecture/designs/M-TESTARCH-test-architecture.md) ·
> Contract source: [NEW-APP-CHECKLIST.md](../architecture/designs/NEW-APP-CHECKLIST.md) items 2 and 3

## What this file is

`check_app_conformance.py` generates the **app conformance matrix** — every app in
`app_ids_gen.APP_ORDER` (generated from `appRegistry.h`'s X-macro) × the contract rows
of `NEW-APP-CHECKLIST.md`. Rows `A5` (TLS bracket) and `A6` (debug surface) are the two
that are decidable statically, on the host, with no device and no build (M-TESTARCH §2.3,
tier T0). This file grandfathers the findings that are **deviations by design or by
mechanism**, so that everything else is a live finding from day one.

**The rules that make this a ledger and not an amnesty** — the same four the C6 ledger
(`id_binding_exceptions.md`) makes:

1. A row suppresses **one** finding, keyed on `(row, subject)`. No file, directory,
   app-family or wildcard exemption exists, by design.
2. **A stale row is a failure.** When the finding it suppresses stops existing, the
   checker reports `stale exception … delete this row`. The list can only shrink.
3. Every row needs an owning `TASK-` id and an ISO `since` date. Missing either is a
   parse failure, and an unparsable row is itself a finding.
4. A row states the **mechanism** that makes the deviation correct — not "known issue".

**Blocking since 2026-09-05.** The matrix landed warn-only (`STRICT_DEFAULT = False`) on one
unexcepted `A6` cell, with the promotion criterion written into the source: "flip this once A6's
outstanding cells are closed or excepted". A gate-layer audit re-measured it and found the
criterion met and unnoticed — `--strict` reads **0 unexcepted findings on both rows**, across
every registered app, against the 5 rows below. Advisory past its own stated precondition is the
state C3 sat in for two months; it is not left in that state here.

## Subjects

| row | subject key | the finding it suppresses |
|---|---|---|
| `A5` | `<file>:<function>` (`<file>:file-scope` for a file-scope session) | an HTTPS session-open site that is either not provably `tlsYield()`/`tlsResume()`-bracketed, or attributable to no registered app |
| `A6` | the app name, exactly as in `APP_ORDER` | no `get` key statically resolves to that app's instance (`g_<Name>App`) |

## Ledger

| row | subject | why it is not a defect today | owner | since |
|---|---|---|---|---|
| `A5` | `app/src/main.cpp:file-scope` | this **is** the Spotify TLS session — the object `tlsYield()` exists to tear down. It is the yield *target*, not a yielder; bracketing it in itself is a contradiction. Lifetime is owned by `spotifyTask` (`spotifyTaskStorage.cpp:20` declares it `extern`) | TASK-483 | 2026-08-18 |
| `A5` | `app/src/audio/audioEngine.cpp:wrPumpTaskBody` | the audio library's `connecttohost()` TLS/TCP connect runs on the **wrPump task**, dispatched by flags rather than called, so no static caller chain reaches it. The bracket is real but raised by the requester: `webRadioApp.h:1730` `tlsYield()` (guarded by `_spotifyYielded`) and `webRadioApp.h:1762` + `_stopAudio()` `tlsResume()`. Cross-task bracketing is T3 evidence (`T_AE_04`), not T0. Subject path updated 2026-08-21 (M-SRCLAYOUT Stage E, TASK-471): `wrPumpTaskBody` moved from `audioEngine.h` to `audioEngine.cpp`; same site, same reasoning | TASK-483 | 2026-08-18 |
| `A5` | `app/src/dataTaskStorage.cpp:fetchHeatmapQuote` | correctly bracketed (`tlsYield()` at :901, `tlsResume()` at :914/:982 on both paths); the *attribution* is what is missing. The fetch belongs to **Stock** (its heatmap view), but its `FetchType` tag is `DATA_FETCH_HEATMAP_QUOTE`, which carries the feature name and not the app name, so the generated attribution cannot see it | TASK-483 | 2026-08-18 |
| `A5` | `app/src/dataTaskStorage.cpp:fetchGeocode` | correctly bracketed (`tlsYield()` at :1465, `tlsResume()` at :1515); attribution only. The fetch is raised from `settings/appsSection.h:1017` (`enqueueGeocode`) — i.e. it belongs to **Settings**, on behalf of PlaneRadar's location entry — and `DATA_FETCH_GEOCODE` names neither app | TASK-483 | 2026-08-18 |
| `A6` | `Spotify` | `SpotifyApp` is a shim over two collaborators that each carry a full debug surface, both wired into `app/src/debug/serialConsole/cmdGet.h:452`: `WinampDisplay::dbgGet()` (`winamp/winampDisplay.h:1226`) and `spotifyTask::dbg_get()`. The app object holds no state that a test would ask for; `g_SpotifyApp` is referenced **nowhere** outside the composition root. Deviation from item 3's letter ("the App class implements `dbgGet`"), conformance with its intent (the app is observable) | TASK-483 | 2026-08-18 |

**5 rows.** Re-count from the tool, never from this line: `python3 app/tools/gate/check_app_conformance.py`
prints `N exception(s) on the ledger`.

## Not on the ledger, and deliberately so

- **`A6/Weather` is a live finding.** `WeatherApp` is the only one of the thirteen with no
  `dbgGet()` of its own *and* no `cmdGet.h` branch touching its instance. Its private state
  (`_wxErr`, `_lsec`) is unobservable. The one observable, `get weatherReady`, reads
  `s_wxDataReady` — a **composition-root static** (`shell/appTable.h:47`) that `app/src/apps/weatherApp.h:151`
  writes into. Crypto has the identical static (`s_cxDataReady`) but also its own `dbgGet`, which
  is exactly what makes Weather the odd one out rather than a house pattern. This is A6's
  Aquarium-shaped hole and it should be fixed, not excepted.

## Findings recorded while building this ledger, not fixed here

- **Row A5 is green for every app that fetches.** All seven app-attributable HTTPS sites bracket
  correctly, three of them only because *every caller* brackets (`fetchStockChartOnce`,
  `fetchOneMirror`, `prFetchOnce`) — a per-function check alone would have called those three
  failures. BP-031 has held.
- **The A5 domain is centralised, and NEW-APP-CHECKLIST item 2 no longer describes the code.**
  Item 2 tells a new app to "call `tlsYield()` before the fetch and `tlsResume()` after", citing
  `TeletextApp::pollTeletext()` and `StockApp::fetchQuote()` as precedents. Neither exists any
  more: **no app header opens a TLS session at all**. Every one goes through `dataTask`, which
  brackets centrally. The item should be rewritten as "your fetch goes through `dataTask`; if you
  add a new `fetchXxx()` there, bracket it" — a checklist item that names two functions that were
  deleted is a checklist item nobody can follow.
- **Two `FetchType` tags name a feature, not an app** (`HEATMAP_QUOTE`, `GEOCODE`). Renaming them
  `DATA_FETCH_STOCK_HEATMAP` and `DATA_FETCH_SETTINGS_GEOCODE` would delete two of the five rows
  above by construction. Firmware edit, out of scope for a VE gate.
