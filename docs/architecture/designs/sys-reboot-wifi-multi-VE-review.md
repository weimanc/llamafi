# VE Panel Review — System Reboot + Multi-Network WiFi (TASK-400 / TASK-401)

> Owner: VE · Date: 2026-08-04 · Reviewed at commit 17cfd10 (both docs Status: draft)
> Scope: TESTABILITY review per the `touch-ux-panel-VE-review.md` precedent (that doc's own
> header) — is each design's exit criteria actually agent/harness-executable, and does the
> design expose the observables a test needs, before implementation starts.
> Docs: 1 = M-SYS-REBOOT.md (TASK-400) · 2 = M-WIFI-MULTI-AP.md (TASK-401)
> Every code claim in the docs was verified against the tree, not taken on faith. Findings are
> labelled VE-<doc>-<n>, classified blocker / major / minor, each with a proposed resolution.
> Architect dispositions.

---

## Code-claim verification (both docs)

Verified true in tree:

- Doc 1: `SETTINGS_CAT_COUNT = 6`, `_sections[0..5]` wired in `SettingsApp::init()`
  (`main.cpp:876-883`); category-list row math (`SETTINGS_CONTENT_H=212`,
  `SETTINGS_ROW_H=26` → 7 categories + Cancel = 208px used, `main.cpp:850-864,1016-1040`);
  `wifiSection.h:377` `_doForget()` calls `ESP.restart()` with no confirm step; the debug
  `reboot` serial command exists and acks before resetting (`main.cpp:4022-4026`); `SButton`
  `SBtnStyle::Danger` + `sButtonBar` kit is real and already used for a destructive confirm
  (`appsSection.h:900`, PrLoc delete-slot); `saveSettings()` autosave-on-change is the real
  pattern across every section (40+ call sites, confirmed by grep, not estimated).
- Doc 2: partition table `spiffs, 0x290000, 0x160000` = 1,441,792B (`app/partitions_no_ota.csv`);
  live SPIFFS dump totals 2,129B across 6 files (`Spotify-Diy-Thing/data/spiffs-dump/`); NVS
  holds exactly one STA profile (`esp_wifi_get_config`/`set_config`, single `wifi_sta_config_t`);
  boot chain's three tiers match the doc's line citations (`main.cpp:2246-2347`);
  `wifiDiag::superviseTick()` re-kicks with bare `WiFi.begin()` against NVS only
  (`wifiDiag.cpp:101-131`); `WiFiMulti.h`/`.cpp` does ship in the pinned
  `framework-arduinoespressif32` 2.0.17 toolchain (confirmed present, not just assumed) — moot
  for the adopted lean since it's no longer used, but the doc's claim about it is accurate.
- Both: `dbgGet()` chain pattern (`SettingsApp::dbgGet` → per-section accessor, e.g.
  `AppsSection::submenu()`/`prDivKm()`) is the established house convention for exposing UI-list
  state to the serial harness — neither doc currently proposes a new accessor of this shape for
  its own new UI surface (see VE-1-3, VE-2-1 below).

---

## Doc 1 — M-SYS-REBOOT (TASK-400)

### VE-1-1 (major) — no stable log line distinguishes a UI-confirmed reboot from a coincidental crash/watchdog reset

Existing precedent (`test_plan.md:2144-2146`, T-DISP-04/T-TIME-04/T-APPS-08/T-LED-11, all
status PASS) proves the harness already reconnects cleanly after an `ESP.restart()` triggered
by the **serial** `reboot` command, which acks `{"ok":true,"cmd":"reboot"}` immediately before
resetting (`main.cpp:4023-4026`) — a clean signal the harness can grep before the connection
drops. The design's own confirm-tap path has no equivalent: the doc specifies `ESP.restart()`
called directly from the confirm handler with no log line first. A harness driving the tap and
then reconnecting post-boot cannot tell "confirmed and rebooted as designed" from "device
crashed or TWDT-reset at the same moment for an unrelated reason" — a real ambiguity given this
project's own history of TWDT-adjacent failures elsewhere (project memory: multiple prior
watchdog-crash root-causes). The reconnect-after-restart *mechanism itself* is proven safe by
the cited precedent; what's missing is the *provenance* signal for this specific new trigger.
**Resolution:** emit a stable-prefix line (e.g. `[settings] system-reboot confirmed`) immediately
before `ESP.restart()` in the confirm handler, mirroring `cmdReboot`'s own ack; add a harness
step asserting it's the last captured line before the boot banner.

### VE-1-2 (major) — the exit criteria's "manual layout check ... confirm on-device" cannot be automated with the existing screendump tool, and the doc doesn't say so

Checked, not assumed: `run/screendump` (`app/tools/screendump.py`) opens its own serial
connection via `run_serialdbg_tests.Dut`. Per `best_practices.md:243` ("Opening a serial port on
CH340-based boards counts as reset #1 (DTR pulse on port open)") and LL-051's full incident
write-up, that connection **resets the chip on open**. There is no way to navigate the device to
the 7-category list (or open the System row) over one connection, then capture it with a fresh
`run/screendump` invocation — connecting wipes the navigated state back to boot before any pixel
is read. The doc's own exit criteria already hedge ("confirm on-device rather than trusting the
arithmetic alone") but don't say *how*, and a future implementer reaching for `run/screendump` as
the obvious tool will hit this wall. **Resolution:** state explicitly that this check is
human-eyeball only under current tooling, or (larger, separate scope) extend `screendump.py` to
perform its own tap-navigation sequence within the same connection before capturing — not a
documentation nit, a real tooling gap this design's own exit criterion runs into.

### VE-1-3 (minor) — doc doesn't cite the existing `get settingsSection` observable for confirming System is reached

`SettingsApp::dbgGet("settingsSection")` already reports `_s.section` (`main.cpp:951-955`), and
`T-WIFI-04` already uses exactly this pattern (`tap 30 14` → `get settingsSection` asserts
`section==-1`, `test_plan.md:2202-2216`). No new code needed — the doc just doesn't reference it.
**Resolution:** add to exit criteria: after tapping the System row, `get settingsSection` asserts
`section==6`.

### VE-1-4 (minor) — confirm-screen state (Cancel vs. pending-Reboot) has no named observable, and the doc doesn't say that's intentional

"Cancel returns... no side effects" is verifiable only by connection continuity + visual per the
current exit criteria — acceptable for a human check, but worth saying explicitly so a future
implementer doesn't feel obligated to invent a getter the stated criteria don't actually need.
**Resolution:** one sentence in the doc: confirm-screen state is visual-only by design, no debug
accessor planned.

### VE-1-5 (informational, confirmed-safe) — no cross-section race is reachable

Checked whether Reboot could be triggered while another section's async sub-flow is mid-flight
(WiFi's Keyboard step, AppsSection's PrLoc lookup): `SettingsApp::_onCategoryTap` only fires when
`_activeSection == nullptr` (`main.cpp:929-947`), and every section's `leave()` runs before the
next `enter()`. Structurally impossible to reach the Reboot confirm mid-edit elsewhere. No
resolution needed — recorded so it isn't re-litigated later.

**Doc 1 verdict: approve-with-changes** — no blockers. VE-1-1/VE-1-2 are real testability gaps
(observability + tooling) that should be closed before implementation is called done, not before
implementation starts; the confirm-gated design itself is sound and the layout-capacity math
checks out.

---

## Doc 2 — M-WIFI-MULTI-AP (TASK-401)

### VE-2-1 (major) — no debug getter proposed for the saved-network list; every comparable list-editing UI in this codebase has one

`AppsSection::submenu()`/`prDivKm()` and `SettingsApp::dbgGet("settingsAppSubmenu")` are the
established pattern for exposing exactly this kind of UI-list state to the serial harness. Without
an equivalent here, an automated test can't know which row index in "Saved networks" corresponds
to which SSID before tapping it, and can't assert the LRU-eviction outcome the doc's own OQ4
leaves as an open implementation question — "policy TBD" compounds with "no way to observe the
result" into an untestable feature, not just an underspecified one. **Resolution:** add
`get wifiSaved` → `{count, entries:[{ssid, lastUsedMs}, ...]}` to the design before
implementation, not as a follow-up.

### VE-2-2 (major) — the one-time legacy-file migration path has no exit criterion at all

Lean/decision §1 specifies migrating `/wifi_creds.json` → `/wifi_networks.json` on first boot
after upgrade — and **every existing DUT today** has only the legacy file, making this the single
most likely code path to actually run first in the field. None of the doc's five exit-criteria
bullets test it. **Resolution:** add an explicit criterion: boot a device with only legacy
`/wifi_creds.json` present, confirm `/wifi_networks.json` is created with the migrated single
entry, and (per VE-2-1's getter) `get wifiSaved` reports `count==1` with the correct SSID.

### VE-2-3 (minor) — "byte-for-byte unchanged" (exit criterion 1) names no concrete metric

As written this isn't falsifiable — "behavior... byte-for-byte unchanged" is a claim about
behavior, not bytes, and doesn't say what a harness actually diffs. **Resolution:** name the
comparison — e.g. boot-to-GOT_IP elapsed ms within existing measurement tolerance, and matching
`[wifi-ev]`/`[wifi-sup]` line *shape* (not literal timestamps) across N boots before/after.

### VE-2-4 (minor) — none of T-WIFI-01..06 exercise `_doForget()`/reboot today, so "regression stays green" doesn't actually cover what this design changes

Checked `test_plan.md:2154-2249` directly: none of the six existing WiFi test ids reference
forget/restart. This design changes forget's scope (remove one list entry vs. the only file) —
"still green" on the existing six is true but doesn't touch the behavior that actually changed.
**Resolution:** add a new test id (e.g. T-WIFI-07: "Forget network removes only the active entry;
other saved entries survive") rather than relying on the existing suite's silence.

### VE-2-5 (informational, confirmed-safe) — no cross-step race reachable, same shape as Doc 1's VE-1-5

`WifiStep` remains a single top-level state machine (Status/Scanning/List/Keyboard/Connecting/
Result, plus the new Saved-networks step) — no UI path exists to be mid-delete on a saved entry
while connecting to it, or vice versa. Confirmed by reading the existing step-dispatch structure.
No resolution needed.

**Doc 2 verdict: approve-with-changes** — no blockers. Both majors are additive
observability/test work that fits the now-deliberately-small manual-only scope; nothing here
argues against the design itself, which is materially lower-risk than its first (rejected) draft.

---

## Verdict summary

| Doc | Verdict | Blockers | Majors |
|---|---|---|---|
| 1 — M-SYS-REBOOT (TASK-400) | **approve-with-changes** | — | VE-1-1, VE-1-2 |
| 2 — M-WIFI-MULTI-AP (TASK-401) | **approve-with-changes** | — | VE-2-1, VE-2-2 |

Neither doc needs a design rethink. Recommend both proceed to Architect disposition of the four
majors (ideally folded directly into each design doc's Lean/decision or Exit criteria section)
before Developer implementation starts; the minors and informational notes can be picked up at
implementation time without blocking.
