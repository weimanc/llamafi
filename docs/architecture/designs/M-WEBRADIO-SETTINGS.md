# Design — M-WEBRADIO-SETTINGS: on-device UI for the WebRadio settings block

> Owner: Architect
> Status: **accepted** (r2 2026-07-16 — panel-reviewed PASS-with-actions
> [1 BLOCKER WR-1 + 3 MAJOR, all folded into D2/D3/§6], human sign-off;
> review: `M-WEBRADIO-SETTINGS-review.md`. WR-8 registry fixes applied to
> `settings-webradio`; WR-12: OQ2's keyboard retirement is M-COUNTRY-PICKER
> **exit criterion 1**, not T-CPICK-03)
> Date: 2026-07-16
> Feeds: — (no new decision expected; applies ADR-050 + existing patterns)
> Tracked-as: — (PM to slice after review)
> Registers: settings-webradio · X034 (reserved 2026-07-16)
> Prior art: M-SETTINGS-APP-WIRE (per-app rows), M-PLAYER-STATE (player entry),
> M-PR-LOCATIONS (country keyboard input), ADR-045/TASK-221 (bitrateCap),
> TASK-209 (hwMod/maxVolume clamp), ADR-050 (ownership rules)

## 1. Context / pain points

The 2026-07-16 settings audit (M-SETTINGS-WIRE2 §1, out-of-scope list) found the
entire WebRadio settings block **consumed correctly but invisible on-device**:
`webRadioCountry`, `webRadioAutoplay`, `webRadioBitrateCap`, `webRadioAutoSkip`,
`webRadioHwMod`, `webRadioMaxVolume` are edited only via serial `set` or
`run/spiffs push`. WebRadio has no entry in `kConfigurableApps`
(`appRegistry.h:27` has `cfg=0`); the "Winamp" player entry exposes only
`playerMode`. A stale comment (`webRadioApp.h:1523` "active country is surfaced
via Settings") claims UI that never existed.

Concrete user pain on record: a settings wipe reverts `bitrateCap` to the
default 96, which silently hides **all** NPO stations (192 kbps + https-only
alternates) from the station list — currently unfixable without a host
(`project_webradio_bitratecap` memory; the diagnosis needed `get wrStation` +
full-URL LOG_D).

Two latent correctness gaps this design must also close, because a UI makes
them reachable by normal users instead of only by serial:

- **No change-propagation contract.** The station list is fetched once at
  `init()` (`webRadioApp.h:331`); `resume()` re-enqueues only if
  `_stationCount == 0` (TASK-289 second-chance). Changing country or cap in
  Settings today would not refetch the list until a reboot or a failed-fetch
  session.
- **`webRadioLastStation` is an index into the *current* list.** After a
  country or cap change the persisted index points into a different list —
  autoplay would "reconnect" to an arbitrary station.

## 2. Goals

1. All user-preference WebRadio settings editable on-device; the bitrateCap
   wipe-trap becomes user-recoverable.
2. Changes apply on next entry to the radio (pull-on-resume, ADR-050) without
   reboot; stale-index and stale-list states are impossible by construction.
3. Zero change to playback/volume safety semantics: `wrEffectiveVolume()`
   (TASK-209) remains the single clamp authority.
4. Registry + VE coverage reserved up front (ADR-050 §4, Architect remit).

Non-goals: a country *picker* list (Q5 heritage — revisit when a second
consumer justifies the shared widget; see §7); exposing `webRadioLastStation`
(runtime state, not preference); changing the radio-browser fetch mechanics.

## 3. Design space

### D1 — Where does the UI live?

- **(a) Extra rows under the "Winamp" player entry** (below the existing Mode
  row). No registry change, but mixes player-slot config with radio-only
  config, the entry is named for the slot not the app, and six extra rows make
  the Mode row's section scroll-adjacent. Rejected: conflates two features the
  M-PLAYER-STATE design deliberately separated (mode selection vs per-mode
  settings).
- **(b) Flip WebRadio to `cfg=1` in `appRegistry.h` → own "WebRadio" entry in
  Settings → Applications.** One-line registry change + regen
  (`gen_app_registry.py`; `run/check` staleness gate enforces the commit), plus
  `AppId::WebRadio` cases in appsSection's repaint/tap dispatch. **Lean.**

Invariant check (LL-085/TASK-242): the *taskbar* exclusion is untouched —
`taskbar.h` iterates `TASKBAR_APP_COUNT`, a separate list from
`kConfigurableApps`; the `cfg` column only feeds Settings → Applications.
WebRadio stays last in the registry (taskbar `static_assert` ordering), and
`cfg` doesn't reorder. Eject remains the only way to *enter* the app; Settings
merely configures it. The Applications list grows to 10 entries —
`_appListRowH()` self-scales (the TASK-321 9th-app lesson is already coded in,
`appsSection.h:144-147`).

### D2 — Row set and widgets

| Row | Field | Widget / interaction | Notes |
|---|---|---|---|
| Country | `webRadioCountry` | KeyboardWidget, `UpperAlpha`, maxLen 2 (prloc country idiom, `appsSection.h:614`) | free-typed ISO 3166-1 alpha-2; invalid codes simply fetch an empty list — the app already renders "No stations", acceptable v1 (see §7-OQ2) |
| Autoplay | `webRadioAutoplay` | tap-toggle On/Off | |
| Bitrate cap | `webRadioBitrateCap` | tap-cycle `off → 64 → 96 → 128 → 192` (find-current-else-default-next, `_cycleTeletext` convention — a serial-set off-list value like 100 cannot wedge the row, WR-11) | "off" renders for 0; this is the wipe-trap fix row |
| Auto-skip | `webRadioAutoSkip` | tap-toggle On/Off | ADR-045 behaviour toggle |
| Max volume | `webRadioMaxVolume` | SliderWidget 1..21 — **with a phase-forwarding hook (WR-3, r2)**: `AppsSection::handleInput()` drops all non-Release phases at `:81`, so the "dispLevel idiom" cannot work unmodified. Add a pre-Release forwarding branch when `_sub == WebRadio` and the slider row is hit (keyboard-capture precedent at `:77-80` already pierces the gate). This hook is a shared prerequisite with M-COUNTRY-PICKER's draggable scrollbar — build once | value label shows the *effective* cap when clamped: "18 (cap 12)" when `!hwMod` and value > 12 — makes the TASK-209 clamp visible instead of mysterious |
| HW mod | `webRadioHwMod` | **read-only, greyed** (Teletext Country posture, `appsSection.h:365`) | a statement about installed hardware, not a preference — a casual toggle defeats the anti-clipping ceiling. Stays serial/spiffs-only |

6 rows ≤ 8-row content budget; no sub-view needed. All rows persist via
`saveSettings()` on commit (standard section behaviour).

### D3 — Change propagation (the ADR-050 owner contract)

Owner is `webRadioApp` via **pull-on-resume with a config snapshot diff**
(StockApp ticker-diff precedent, `main.cpp:1080-1090`):

- App keeps `_cfgCountry[4]` + `_cfgCap` snapshots taken at each list fetch.
- **Result identity (WR-1, r2 — BLOCKER fix).** The diff alone cannot defeat a
  stale in-flight/parked fetch: `pollWebRadioStations()` has no identity check
  and the abort flag is re-armed at fetch start, so an old-country result can
  pop *after* the diff clears the list and reinstall a stale-country list
  (persistent for the session if the new fetch hits TASK-284 truncation — the
  TASK-300 parked-result pattern exactly). Fix, same medicine as
  `StockChartResult`: `WebRadioStationsResult` gains a **cap echo** alongside
  the existing `countryCode` echo; `tick()`'s install site compares BOTH
  against the current snapshot and discards mismatches. The diff branch also
  calls `abortWebRadioFetch()` to kill a genuinely in-flight fetch early.
- **Edit-time reset (WR-2, r2 — moves out of resume()).** The section's
  country/cap commit handlers reset `g_settings.webRadioLastStation = 0`
  **at edit time** — the reset rides the handler's existing `saveSettings()`
  (zero extra flash wear) and closes the reboot window that a resume()-time
  RAM reset leaves open (flash holding new-country + old-index → reboot →
  `init()` seeds `_currentIdx` from the stale index with a fresh snapshot, no
  diff ever fires). The resume-diff remains as the safety net for serial
  `set` edits, whose residual reboot window is documented as accepted.
- `resume()` on snapshot mismatch: stop stream defensively (see note below),
  reset `_currentIdx = 0`, clear the list (`_stationCount = 0`), enqueue a
  fresh fetch. The TASK-289 `_stationCount == 0` second-chance path then owns
  retries — no new retry machinery.
- The TASK-289 heap-race guard is respected by construction: the refetch fires
  from `resume()` where the audio stack is torn down. (WR-13: this argument is
  `-DMEMBUDGET_PHASE1`-conditional — true in the production env; a non-arena
  build only stops the stream. WR-7: in practice `resume()` can never observe
  PLAYING — every exit path runs `suspend()` → `_stopAudio()` first — so the
  "stop" is defensive code, and T-WRSET-03's stopped assertion verifies
  suspend(), not the diff.)
- Autoplay after a config change deliberately does **not** fire (list is
  empty at that instant; by the time stations land the autoplay check in
  `resume()` has passed). First station selection after a country change is a
  user act — correct, since index 0 of a new country is arbitrary.

`lastStation` save policy lands here too (ADR-050 rule 3): drop the RAM-only
write at `webRadioApp.h:1182` in favour of a dirty flag; persist once in
`suspend()`/eject if changed since load. Auto-skip churn then costs zero flash
writes. (Edit-time resets above are the section's job and ride its saves.)

### D4 — Stale comment + docs

Fix `webRadioApp.h:1523` comment to point at the real Settings entry this
design adds. Update `docs/quality`/memory-adjacent guidance implicitly via the
inventory entry (§5) — the bitrateCap trap note should say "fix on-device via
Settings → Applications → WebRadio".

## 4. Lean / decision — summary

| Item | Decision |
|---|---|
| Placement | D1(b): `cfg=1`, own Applications entry |
| Rows | D2 table: 5 editable + hwMod greyed |
| Propagation | D3: resume-diff → stop + reset indices + refetch; lastStation coalesced save on suspend |
| hwMod | never editable on-device |
| bitrateCap default | **128** — human decision 2026-07-16 (OQ1 resolved). Change `applyDefaults()` (settingsStorage.cpp:74) AND the load fallback (`\| 96`, settingsStorage.cpp:253) together. Honest consequence on record: NPO's 192 kbps streams are still filtered at 128 — the default is a decode-safety midpoint, and the new UI row is the recovery path for 192k content |

## 5. Registry (Registers: line, reserved with this design)

- `feature_inventory.yaml` → **`settings-webradio`** (settings-wifi naming
  precedent): reserved entry pointing here; Developer completes at
  implementation (files: appRegistry.h, gen/configurable_apps.h,
  appsSection.h, webRadioApp.h).
- `cross_feature_matrix.yaml` → **X034** `settings-webradio ↔ webradio-001`
  (dependency): the D3 resume-diff contract — country/cap edits void station
  identity; lastStation reset is mandatory on either change; refetch rides the
  TASK-289 second-chance path; `wrEffectiveVolume()` remains the only volume
  clamp regardless of what the slider stores. Risk medium.
  (No taskbar edge: `cfg` and taskbar lists are disjoint — X022's invariant is
  unaffected and its entry already documents the eject-only rule.)

## 6. Verification sketch (VE to own)

New family `T-WRSET` (DUT, serial-driven; `set kbText` from TASK-325 covers
the country keyboard):

- T-WRSET-01 — rows render with persisted values (split per WR-9: the *inert*
  half of hwMod is automated — tap row + spiffs-pull diff shows no change; the
  *greyed* half is [MANUAL] eyeball, house precedent T-WIRE-MAT-03).
- T-WRSET-02 — bitrateCap cycle persists (spiffs pull diff) and survives
  reboot; the NPO scenario: cap →192, resume radio → station list refetch
  fires with `bitrateMax=192` in the LOG_D URL. Defaults leg (OQ1): wiped
  settings.json → boot → cap reads 128.
- T-WRSET-03 — country change: playing radio → change country in Settings →
  resume radio → stream stopped (verified at suspend(), per WR-7 — not
  credited to the diff), lastStation==0 **already on flash from the edit-time
  reset (WR-2)**, fresh list for new country; autoplay did NOT auto-fire.
  **Stale-result leg (WR-1)**: change country while a fetch is pending (or
  park one via timing) → assert the old-country result is discarded by the
  identity check and never installed.
- T-WRSET-04 — no-change resume: enter/leave Settings without edits → NO
  refetch (snapshot diff is quiet — guards against re-introducing fetch churn
  and the TASK-284 rate-limit sensitivity).
- T-WRSET-05 — maxVolume slider: set 18 with hwMod=false → label shows
  "18 (cap 12)", `get wrEffectiveVol` (WR-5 — exists at webRadioApp.h:784,
  built for T_WR_VOL_03; there is no `get wrVolume`) reports eff=12; audible
  calibration remains deferred on the 8Ω speaker rig.
- T-WRSET-06 — lastStation coalesced save: play station 3, auto-skip a few
  hops → **zero** `SettingsStorage: saved` lines per hop; eject → flash shows
  lastStation=3. Saved-line count on eject is **derived, not "one"** (WR-6):
  persistPlayerMode also saves on mode change, so expect ≥2 unless the
  implementation folds suspend()-save before the mode toggle — assert the
  derived N, and zero per-hop.
- Regression: T_WR_ERR_x + eject/T242 suite re-run (appsSection dispatch and
  registry regen touch shared surfaces); `run/check` gates the regen.
  **Coordinate audit (WR-4)**: the 10th Applications entry shrinks list rows
  23→21 px — every suite that navigates Settings→Applications by hardcoded
  `tap x y` needs its tap table re-derived, and the already-stale layout
  reference (26 px/5-app era) refreshed in the same pass. This is the
  memory-watchlist "settings nav coordinate drift" item firing — budget it.

## 7. Open questions

- **OQ1** — RESOLVED 2026-07-16 (human): default bitrateCap becomes **128**
  (was 96). T-WRSET-02 gains a defaults leg: wiped settings.json → boot →
  cap reads 128.
- **OQ2** — RESOLVED by design 2026-07-16: shared country picker drafted
  (M-COUNTRY-PICKER — SPickerList + baked full ISO table); the Country row
  opens the picker instead of the keyboard, making invalid codes
  unrepresentable. If the picker ships with/before this milestone, D2's
  keyboard row never lands; if after, the keyboard is the interim and is
  retired by T-CPICK-03.
- **OQ3**: should the radio's PLEDIT header surface the active country badge
  tap-to-edit (deep-link into Settings)? Nice-to-have; out of scope v1.

## 8. Exit criteria

1. All five editable fields round-trip Settings UI → settings.json → radio
   behaviour without serial access; wipe-trap recovery demonstrated on-device
   (cap 96→192 restores NPO stations).
2. Country/cap change while radio suspended or playing never yields a stale
   list, stale index, or surprise autoplay (T-WRSET-03/04).
3. `run/check` green including registry regen staleness; taskbar untouched
   (no WebRadio icon — X022 invariant).
4. T-WRSET-01..06 pass on DUT; existing WR + eject suites regress clean.
5. `settings-webradio` inventory entry completed; X034 test_coverage filled.
