# Review — M-WEBRADIO-SETTINGS (design)

> Panel: consolidated Developer + VE + QM + PM design review
> Date: 2026-07-16
> Subject: `docs/architecture/designs/M-WEBRADIO-SETTINGS.md` (draft, 2026-07-16)
> Verdict: **PASS-with-actions** — WR-1 (BLOCKER) must be amended into D3 before
> PM slices; WR-2/3/4 (MAJOR) need design-text dispositions; the rest are
> spec/consistency fixes that can ride implementation.

---

## Claim verification (adversarial pass)

Every file:line claim in the design was checked against the working tree.

| Design claim | Verified? | Evidence |
|---|---|---|
| WebRadio `cfg=0` at `appRegistry.h:27` | YES | `APP_X( WebRadio, 'R', 0, "WebRadio" )` — app/src/appRegistry.h:27, and it is the last row |
| Taskbar unaffected by `cfg` flip | YES | `TASKBAR_APP_COUNT = (int)AppId::WebRadio` (app/src/taskbar/taskbar.h:37) is **position**-derived, guarded by `static_assert((int)AppId::WebRadio == (int)AppId::COUNT - 1, ...)` (taskbar.h:33-35). The `cfg` column feeds only `gen_app_registry.py` → `app/gen/configurable_apps.h` (`kConfigurableApps`, currently `CONFIGURABLE_APP_COUNT 9`). Disjoint lists — X022 invariant holds. |
| Applications list grows to 10; `_appListRowH()` self-scales | YES (with VE consequence — WR-4) | 9 current cfg=1 rows + WebRadio = 10. `_appListRowH()` at app/src/settings/appsSection.h:145-148 returns `min(S_CONTENT_H / CONFIGURABLE_APP_COUNT, S_ROW_H)` = 212/10 = **21 px** rows (was 23 at 9 apps). 10×21 = 210 ≤ 212 — all rows visible and tappable; 21 px on the resistive panel is marginal but only 2 px below today's shipping 23 px. |
| Fetch once at `init()` — `webRadioApp.h:331` | YES | `dataTask::enqueueWebRadioStations(...)` at app/src/webRadioApp.h:331-332 |
| `resume()` second-chance only if `_stationCount == 0` | YES | app/src/webRadioApp.h:351-355; autoplay gate at :357-360 |
| RAM-only `lastStation` write in `_play()` — `webRadioApp.h:1182` | YES | `g_settings.webRadioLastStation = idx;` at :1182, no save |
| `wrEffectiveVolume()` at `~:88-91` | YES (89-92) | single clamp authority, hwMod-gated ceiling |
| Stale comment at `webRadioApp.h:1523` | YES (1522-1524) | "the active country is surfaced via Settings, not an overlay" — UI that never existed |
| `applyDefaults()` bitrateCap at `settingsStorage.cpp:74` | YES exact | `g_settings.webRadioBitrateCap = 96;` at app/src/settingsStorage.cpp:74 |
| Load fallback `\| 96` at `settingsStorage.cpp:253` | YES exact | `wr["bitrateCap"] \| 96` at :253 — the two-sites-together instruction is correct and complete (save path at :390 is value-passthrough, no third default site) |
| StockApp ticker-diff precedent `main.cpp:1080-1090` | YES exact | `StockApp::resume()` diff loop at app/src/main.cpp:1080-1090 |
| prloc country keyboard idiom `appsSection.h:614` | YES (617) | `g_keyboard.show("Country", ..., UpperAlpha, 2, ...)` |
| Teletext greyed-Country posture `appsSection.h:365` | YES (366) | `drawRow(y, { "Country", "NL (NOS)", S_LABEL, 0x7BEF })`, no row-2 case in `_cycleTeletext` → inert |
| "cap 0 = off" semantics | YES | `bitrateMax` appended only `if (bitrateCap > 0)` — app/src/dataTaskStorage.cpp:941-942; full-URL `LOG_D` at :946 (T-WRSET-02's observable exists) |
| `set kbText` (TASK-325) available | YES | app/src/main.cpp:3124 — dependency already landed |
| "suspend() freed the audio stack" | YES in production | Audio delete + `mb_arena_release()` are `#ifdef MEMBUDGET_PHASE1` (webRadioApp.h:373-388), and `cyd2usb_winamp` defines `-DMEMBUDGET_PHASE1` (app/platformio.ini:76, TASK-262 promotion). See WR-13 for the caveat. |
| Autoplay cannot fire when the refetched list lands | YES | list arrival in `tick()` (webRadioApp.h:466-507) never calls `_play()` except the debug `_deferredInject` wrUrl path (:475-485) |
| X034 reserved and matches D3 | YES | cross_feature_matrix.yaml:631-654 — text matches D3 verbatim incl. autoplay-must-not-fire and no-edit-no-refetch |
| `settings-webradio` inventory reserved, bitrateCap-128 recorded | YES (with WR-8 nits) | feature_inventory.yaml:1801-1828; notes carry OQ1 = 128 + "both sites together" + honest NPO-192 consequence — consistent with the lean table and OQ1 |

---

## Findings

### WR-1 — BLOCKER — D3 does not defeat a stale in-flight/parked station fetch; old-country list can repopulate after the resume-diff

The exact failure class this project has already paid for twice (TASK-289,
TASK-300 "dataq quiet ≠ no parked result").

Evidence:

- `suspend()` (webRadioApp.h:363-389) does **not** abort a pending station
  fetch; `abortWebRadioFetch()` is called only from `_play()` (:1221) and the
  wrUrl inject path (:956).
- The fetch latches its params at service start (dataTaskStorage.cpp:1338-1341)
  and parks its result in a single depth-1 slot (`s_webRadioResult`,
  `s_webRadioNew` — :1789-1800). `pollWebRadioStations()` performs **no
  identity check**; `tick()` (webRadioApp.h:486-492) installs whatever pops.
- Scenario: fetch pending (slow mirror / TASK-284 truncation retry) → user
  taskbars to Settings (no abort) → changes country → returns. The **old-
  country** result is either already parked or still in flight. resume()'s D3
  diff clears the list and enqueues the new fetch — and on the next tick the
  old result pops first and installs an old-country list. `_stationCount > 0`
  now, so nothing re-diffs. If the *new* fetch then fails (TASK-284 is
  intermittent by record), the stale-country list persists for the whole
  session — with the user free to tap a station from the wrong country.
  This directly falsifies Goal 2 / exit criterion 2 ("stale-list …
  impossible by construction").
- The abort flag alone cannot fix the parked case: it is re-armed (cleared) at
  fetch start (dataTaskStorage.cpp:1343-1346), so an abort raised when the
  result is already parked is a no-op.

Disposition (design amendment required before slicing):
D3 must add result identity, the same medicine as TASK-300's
`StockChartResult` fix — either (a) compare `result.countryCode` (already in
the struct, logged at webRadioApp.h:492) **plus** a cap echo (must be added to
`WebRadioStationsResult`) against the current snapshot before installing, or
(b) a request seq token (the `_prGeoSeq` idiom, appsSection.h:127). Also call
`abortWebRadioFetch()` in the diff branch to kill a genuinely in-flight fetch
early. T-WRSET-03 gains a leg: change country *while a fetch is pending*, or
inject via the parked-result timing, and assert the old-country list is never
installed.

### WR-2 — MAJOR — the lastStation reset is RAM-only and the snapshot is RAM-only: a reboot window resurrects the stale-index autoplay bug D3 claims to kill

Evidence:

- D3 resets `g_settings.webRadioLastStation = 0` inside `resume()` but the
  save is deferred to the coalesced suspend()-save (D3 last paragraph). The
  `_cfgCountry/_cfgCap` snapshots are app RAM.
- Sequence: user changes country in Settings (section saves — flash now holds
  **new country + old lastStation**, e.g. 7, because every `saveSettings()`
  serializes the whole struct, settingsStorage.cpp:388-394) → device reboots
  (power cut, crash, `run/flash`) **before** the radio's next suspend().
  Boot → first entry runs `init()` (main.cpp:1940-1942): `_currentIdx =
  g_settings.webRadioLastStation` (= 7, webRadioApp.h:297), fetch fires with
  the new country, snapshot is taken with the *new* values → no diff ever
  fires → `resume()`/autoplay path connects to index 7 of the new-country
  list — the arbitrary-station bug of §1, reintroduced through the reboot
  window. (The in-range clamp at webRadioApp.h:490 only zeroes out-of-range
  indices.)
- Also an ADR-050 rule-3 tension: the resume()-reset is a `g_settings`
  mutation outside the Settings UI with an unbounded RAM-only window — the
  rule demands the window be bounded-and-documented or saved.

Disposition: reset `webRadioLastStation = 0` **at edit time in the section's
country/cap commit handlers** — they already call `saveSettings()`, so the
reset rides an existing flash write for free (zero extra wear) and closes the
reboot window completely for UI edits. Keep the resume-diff for
stop+clear+refetch (and as the safety net for serial `set` edits, whose
residual reboot window should be documented as accepted). Order-of-writes
question (suspend-before-resume) is otherwise sound: the old app's coalesced
save happens before Settings is even entered, so it never clobbers the reset.

### WR-3 — MAJOR — D2's Max-volume SliderWidget cannot work under AppsSection's Release-only input gate as designed

Evidence: `AppsSection::handleInput()` drops all non-Release phases at
appsSection.h:81 (`if (phase != TouchPhase::Release) return ...;`), before any
row dispatch. `SliderWidget` requires Press/Move/Release forwarding
(sliderWidget.h:5-12) — the cited "dispLevel idiom" works in
`DisplaySection::handleInput()` only because that section receives and routes
all three phases (displaySection.h:60-75). Dropping the widget into the
WebRadio row view without restructuring gives a slider that never drags.

Disposition: design should specify the integration: a pre-Release forwarding
hook when `_sub == <WebRadio>` and the slider row is hit (precedent: the
keyboard capture block at appsSection.h:77-80 already pierces the
Release-only gate). Alternatively downgrade the row to a tap-cycle 1..21-in-
steps if the phase plumbing is judged not worth it — but say which. Budget it
in the PM slice either way.

### WR-4 — MAJOR — the 10th entry shifts every Applications-list tap coordinate (23→21 px rows); §6 regression scope omits the coordinate audit

Evidence: `_appListRowH()` = 212/9 = 23 px today → 212/10 = 21 px after the
flip; every app row's mid-y moves (row i mid = 28 + i·rowH + rowH/2). Existing
DUT suites navigate Settings → Applications by hardcoded `tap x y`
(app-settings-wire-001.md §Layout reference and test bodies, e.g. `tap 137
67`; m-clock-styles.md, m-pr-locations-dut.md reach their sections the same
way). The layout-reference table is *already* stale (it still assumes 26 px
rows and a 5-app list — predates Winamp/Clock/Teletext/PlaneRadar rows), and
the project memory carries an explicit watchlist item ("Settings nav
coordinate drift — audit tests/docs if section order ever changes"). §6 lists
`T_WR_ERR_x` + eject/T242 re-runs but not the settings-suite coordinate
re-derivation, which is the regression that will actually fire.

Disposition: add to §6: re-derive and update the Applications-list tap table
(and refresh the already-stale layout reference while there); re-run the
settings suites that navigate via the app list, not just the WR/eject
families.

### WR-5 — MINOR — T-WRSET-05 references `get wrVolume`, which does not exist

The observable exists under a different name: `wrEffectiveVol`
(webRadioApp.h:784-792), which reports exactly the tuple the test needs
(`maxVol`, `hwMod`, `eff`) and was built for T_WR_VOL_03. Fix the test spec to
`get wrEffectiveVol`.

### WR-6 — MINOR — T-WRSET-06's "exactly one save" count is wrong on the eject path

Eject-out of WebRadio calls `persistPlayerMode(Spotify)` (webRadioApp.h:690,
:903 → main.cpp:1835-1839) — the mode *changes*, so the unchanged-value skip
does not apply and a `SettingsStorage: saved` line (settingsStorage.cpp:417,
the countable observable — good) fires **in addition to** the new coalesced
lastStation save in suspend(). Expect ≥2 saved-lines on eject; also note
persistPlayerMode's full-struct save already persists lastStation
incidentally, so the two may be foldable into one if suspend() saves before
the mode toggle — order-dependent. Respec the assertion as "zero saves per
auto-skip hop; lastStation on flash == 3 after eject; total saved-lines for
the eject == N (derived, not 'one')".

### WR-7 — MINOR — D3's "stop playback if playing" is unreachable in the app-switch flow; T-WRSET-03 asserts the wrong actor

Every path out of WebRadio (taskbar, eject, serial `switchApp`, Settings)
goes through `switchApp()` which calls `suspend()` (main.cpp:1924) →
`_stopAudio()` → `_state = STOPPED` (webRadioApp.h:1146-1154) **before** any
later `resume()`. resume() can never observe PLAYING. Keep the stop as
defensive code if desired, but T-WRSET-03's "playback stopped" leg is
verifying suspend(), not the diff — reword the expected-evidence so a future
reader doesn't credit D3 with it.

### WR-8 — MINOR — inventory reserved-entry inconsistencies (QM)

feature_inventory.yaml:1801-1828 (`settings-webradio`):
(a) files list has `app/src/gen/configurable_apps.h` — actual path is
`app/gen/configurable_apps.h` (no `src`);
(b) files list omits `app/src/settingsStorage.cpp`, which OQ1's 128-default
change (both sites) touches;
(c) description says "Country (keyboard, ISO alpha-2)" unconditionally,
while the design's OQ2 resolution says the keyboard row may *never land* if
M-COUNTRY-PICKER ships with/before — the reserved entry should carry the same
contingency wording. The bitrateCap-128 decision itself is recorded
consistently in all three places (lean table, OQ1, inventory notes) including
the honest NPO-192-still-filtered consequence — no contradiction found.

### WR-9 — MINOR — T-WRSET-01's render/greyed legs have no automated observable

There is no framebuffer/screenshot facility (none in run/ or main.cpp);
suite precedent marks such checks `[MANUAL]` (T-WIRE-MAT-03,
T-WIRE-LIFE-03). The *inert* half of the hwMod assertion is automatable
(tap row + spiffs-pull diff shows no change); the *greyed* half is eyeball
(BP-048 posture). Split the test accordingly.

### WR-10 — NIT — citation line-number drift

`wrEffectiveVolume` is :89-92 (cited 88-91); `_appListRowH` :145-148 (cited
144-147); Teletext greyed row :366 (cited 365); prloc country keyboard :617
(cited 614); stale comment :1522-1524 (cited 1523). All substantively
correct; sweep on the next edit.

### WR-11 — NIT — bitrateCap tap-cycle behaviour for off-list persisted values is unspecified

A serial-set value (e.g. 100) is not in `off/64/96/128/192`; specify the
existing cycle convention (find-current-else-default-next, as
`_cycleTeletext` at appsSection.h:369-384 does) so the row can't wedge.

### WR-12 — NIT — OQ2 cross-reference imprecision

OQ2 says the interim keyboard "is retired by T-CPICK-03"; in
M-COUNTRY-PICKER, T-CPICK-03 is the round-trip test — keyboard retirement is
that design's **exit criterion 1**. Point at the criterion, not the test.
Otherwise the two documents' ship-order contingency is coherent in both
directions (picker-first: keyboard never lands; settings-first: keyboard
interim), and M-COUNTRY-PICKER §3-D3 explicitly re-fires this design's D3
contract on select — no contradiction.

### WR-13 — NIT — the heap-race-safety argument is build-flag-conditional

"the audio stack is torn down (suspend() freed it)" holds because
`-DMEMBUDGET_PHASE1` is in the production env (app/platformio.ini:76); in a
hypothetical non-arena build, suspend() only stops the stream (Audio object
and its buffers persist). One sentence in D3 noting the dependency keeps the
claim honest if the flag ever changes.

---

## PM notes (dependency ordering / sizing)

- **TASK-325 (`set kbText`)** — already landed (main.cpp:3124); not a blocker.
- **ADR-050** — accepted with human sign-off; D3's coalesced lastStation save
  *implements* its rule 3, no upstream change needed.
- **M-COUNTRY-PICKER** — genuinely optional in both orders (OQ2); do not
  serialize on it. If picker lands first, T-WRSET country legs drive the
  picker (or the proposed `set country <CC>` direct-set) instead of kbText.
- Sizing is honest for the row/registry/propagation work (one-line registry +
  regen, ~6 rows of section code on existing idioms, a small resume-diff),
  **but** WR-1 (result identity), WR-3 (slider phase plumbing) and WR-4
  (coordinate re-derivation across suites) are real unbudgeted line items —
  fold them into the slice estimate.

## Verdict

**PASS-with-actions.** The placement (D1b), row set (D2), taskbar-invariant
analysis, registry reservations (X034 / settings-webradio), and the
bitrateCap-128 decision trail are all verified sound against the code. The
change-propagation contract (D3) is the right shape but has two holes its own
exit criteria promise away — WR-1 (stale parked/in-flight fetch result;
BLOCKER, amend D3 with result identity + abort before PM slices) and WR-2
(RAM-only reset/snapshot reboot window; MAJOR, move the lastStation reset to
edit-time). WR-3 and WR-4 are implementation-feasibility and regression-scope
gaps to be written into the design; the remaining findings are test-spec and
registry hygiene.
