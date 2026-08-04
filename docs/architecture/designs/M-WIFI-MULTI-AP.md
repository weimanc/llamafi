# Design — M-WIFI-MULTI-AP: store multiple saved WiFi networks (manual switch only)

> Owner: Architect
> Status: **accepted** (2026-08-04, human sign-off)
> Date: 2026-08-04
> Feeds: — (no ADR — OQ1's own lean adopted at sign-off: boot chain and
> `wifiDiag::superviseTick()` are unchanged, so there's no boot-order or
> recovery-policy decision left to formalize)
> Tracked-as: TASK-401
> Registers: wifi-002 (new feature) — **committed** (`feature_inventory.yaml`,
> 2026-08-04). No new cross-feature edge, per the design's own §Registers.

**Revision note (2026-08-04, same day):** first draft of this doc proposed
automatic scan-and-failover — both at boot (fall back to whichever saved
network is in range) and in `wifiDiag::superviseTick()` (roam to a
different saved network on outage). Human explicitly rejected autonomous
switching: *"I don't want the DUT switching over of wifi hotspots on its
own."* This revision drops that entire mechanism. What's below is the
storage + manual-switch-only version. The rejected design-space work
(`WiFiMulti`, boot-fallback-tier scan-and-match, supervisor failover) is
kept below, marked **rejected by explicit human decision**, not deleted —
same "record what was investigated and turned down" convention as
`M-HEAP-FRAGMENTATION.md`'s parked options, in case this is revisited later
with different constraints.

**Second revision note (2026-08-04, same day):** folded in VE's testability
review (`docs/architecture/designs/sys-reboot-wifi-multi-VE-review.md`,
verdict approve-with-changes, no blockers). Both majors closed below:
VE-2-1 (§Lean step 4, a `get wifiSaved` debug getter) and VE-2-2 (§Exit
criteria, an explicit migration-path test). Minors/informational items not
folded here — left for implementation time per the review's own
recommendation.

## Context / pain points

Asked: (1) is there SPIFFS headroom to store more than one WiFi network's
credentials, and (2) could the device support multiple saved hotspots.

**(1) SPIFFS headroom — trivially yes.** Partition table
(`app/partitions_no_ota.csv`): `spiffs, 0x290000, 0x160000` = 1,441,792
bytes (1.4 MB). Current total file footprint on a live DUT dump
(`Spotify-Diy-Thing/data/spiffs-dump/`): `cal.json` 230B + `drd.dat` 4B +
`host_overrides.json` 393B + `settings.json` 1171B +
`spotify_diy_config.json` 260B + `wifi_creds.json` 71B = **2,129 bytes
total, 0.15% of the partition.** A saved-network list (even generously
sized) is noise against this budget. Storage was never the constraint.

**(2) Today's model is single-network, in three places:**

- **NVS**, via `WiFi.persistent(true)` — ESP-IDF's WiFi driver persists
  exactly **one** STA config. Boot's fast path: `WiFi.begin()` with no args
  reconnects directly from NVS, no scan needed (`main.cpp:2271-2292`).
- **SPIFFS `/wifi_creds.json`** — a single `{ssid, pass}` object, written
  only by the host-side `run/setup` wizard (`run/setup:128`) as a one-time
  bootstrap seed. Boot falls back to it only if the NVS attempt fails
  (`main.cpp:2293-2347`), and on success re-persists it into NVS.
- **`WifiSection`'s on-device UI** (`app/src/settings/wifiSection.h`) —
  scan → tap → password → `WiFi.begin(ssid, pass)`, `persistent(true)`.
  Writes **only NVS**, never SPIFFS. "Forget network" (`_doForget()`, line
  372) clears NVS *and* deletes `/wifi_creds.json`, then reboots.

None of these three know about each other's "list" because there isn't
one — there's exactly one credential, recognized in up to three places.

### What happens today when a saved network isn't found (answering the direct question, not part of this design's scope to change)

Boot: NVS attempt times out (10s) → SPIFFS-file fallback attempt times out
(30s, same single credential) → both fail → boot does **not** block; it
arms `wifiDiag`'s supervisor, sets `WiFi.setAutoReconnect(true)`, shows
"WI-FI: RETRY IN BG," and continues into whatever app. From there the core's
own auto-reconnect is known to **wedge permanently** after a long AP
absence (`wifiDiag.h:22-24`: NO_AP_FOUND storm → disconnect reason=39 →
zero further attempts for 40+ min, reboot-only recovery) — which is exactly
why `wifiDiag::superviseTick()` exists: once down 60s continuously, it
force-kicks (`disconnect()`+`begin()`) every 30s, forever, no retry budget
— but always the *same* SSID, since only one is ever known. Mid-session
drop-outs behave the same way. **This design does not change any of that**
— see Lean/decision below.

## Goals

1. Let the user save more than one WiFi network from the device UI (not
   just via the host-side setup wizard) — pure storage/recall convenience,
   so a network used before doesn't need its password re-typed.
2. **No autonomous network selection, anywhere, ever.** Boot and the
   background supervisor keep retrying exactly the one last-active network,
   exactly like today, forever — explicit human requirement, not a
   default this design chose. Switching to a different saved network is
   always a deliberate tap in Settings → WiFi.
3. Reuse existing UI kit (`SButton`/`sButtonBar`, `SBtnStyle::Danger`, the
   scan-list row renderer already in `WifiSection`) — no new widget
   mechanism.
4. Keep the new storage format separate from `g_settings`/`settings.json`
   — see rationale below.

## Design space (options + tradeoffs)

### Where does the saved-network list live?

**A — Extend `g_settings` (`settingsStorage.h`/`.cpp`), persisted in the
existing `settings.json` blob.** Reject. `settingsStorage.cpp`'s own
comments document a previous **capacity incident** (TASK-329: the
`kSettingsJsonCapacity` ArduinoJson document was undersized, and every
field add silently no-op'd — "valid-but-defaulted file" — until the exact
worst-case byte math was redone). Adding a WiFi-network array here means
redoing that math and re-justifying headroom for a field conceptually
unrelated to app settings, when a separate small file (Option B)
sidesteps it entirely.

**B — A dedicated file, `/wifi_networks.json`, holding a small JSON array —
direct extension of today's `/wifi_creds.json`.** **LEAN.** Mirrors the
existing architectural boundary (WiFi credentials already live outside
`g_settings`, in their own file). No new capacity-math burden on the
already-once-bitten `settings.json` path. Trivial size: even
`WIFI_MAX_SAVED = 5` entries at `{ssid[33], pass[64]}` ≈ 500B raw.

**C — Keep using NVS as the only store.** Reject — ESP-IDF's WiFi driver
NVS slot holds exactly one STA profile; no multi-profile NVS API exists.
NVS still holds the single *active* profile (unchanged from today), just
not the multi-network list.

### Autonomous selection at boot / in the supervisor — rejected by explicit human decision

First draft proposed two mechanisms here, both now **rejected, not
adopted**, kept for the record:

**~~D — `WiFiMulti::run()` scan-and-match at boot~~** and
**~~E — same, as the boot fallback tier only (fast NVS path preserved)~~.**
`WiFiMulti.h`/`.cpp` does ship in this project's pinned
`framework-arduinoespressif32` (2.0.17), and mechanically is the right
primitive for "given a list, connect to whichever is in range" — confirmed
by reading the vendored source, not assumed. Not being used: the human
requirement is that the device never chooses a network on its own,
including at boot. (Also would have needed a DUT check against this
project's own established "avoid async `WiFi.scanNetworks()` near
Spotify's socket task" constraint, `wifiSection.h:301-302` — moot now, but
worth remembering if `WiFiMulti` is ever reconsidered for something else.)

**~~F — leave supervisor as bare `WiFi.begin()` retry~~** vs.
**~~G — supervisor fails over to other saved networks via `WiFiMulti`~~.**
G is explicitly what was rejected ("I don't want the DUT switching over of
wifi hotspots on its own" — this is precisely the mid-session-roam
scenario). **F is now the adopted position** — `wifiDiag::superviseTick()`
is **completely unchanged** by this design. It keeps retrying the one
active NVS network forever, exactly as documented in the "what happens
today" section above.

### "Forget" / "switch" semantics with a list, manual-only

**H — "Saved networks" management screen (list + per-entry Danger-styled
confirm-delete, reusing the PrLoc delete-slot confirm pattern,
`appsSection.h:900`) reachable from WiFi → Status. Tapping a saved entry
attempts a direct connect using its stored credentials** (same call shape
as `_startConnect()`, just sourced from the stored entry instead of the
keyboard) **— a deliberate, user-initiated action**, no different in kind
from today's "tap a scanned network, type its password" flow, just
skipping the retyping for a network already known. A successful connect
here re-persists to NVS (`WiFi.persistent(true)` + `WiFi.begin(ssid,
pass)`) exactly like today's manual connect does — this *is* "switching,"
but only because the user tapped it, which is the whole point. **LEAN.**

"Forget network" (top-level, existing single action) keeps its current
position and one-tap feel, now scoped to remove just the
currently-connected entry from the list (plus NVS, plus reboot — unchanged
otherwise). A fresh scan-connect (existing List step, unchanged, still
synchronous scan) **adds** the new network to the saved list (up to
`WIFI_MAX_SAVED`, LRU-evicting the oldest if full) instead of replacing a
single slot — this is the actual "multiple networks" behavior change.

## Lean / decision

**Adopt B + H. Boot chain and `wifiDiag::superviseTick()` are unchanged —
zero new autonomous behavior anywhere.**

1. New `/wifi_networks.json`: `{"networks": [{"ssid":"...", "pass":"...",
   "lastUsedMs":...}, ...]}`, cap `WIFI_MAX_SAVED = 5` (fits comfortably
   inside `WifiSection`'s existing `S_MAX_ROWS = 8` list rendering).
   One-time boot migration: if `/wifi_creds.json` exists and
   `/wifi_networks.json` doesn't, convert the single entry over (keeps
   existing DUTs/host-wizard flow working without a re-setup).
2. Boot chain (`main.cpp:2239-2349`): **no changes.** Hardcoded tier, NVS
   fast path, single-file SPIFFS fallback, and the "no credentials → open
   Settings" tail all stay exactly as they are today. The saved-network
   *list* is not consulted at boot at all — only the one active NVS
   profile.
3. `wifiDiag::superviseTick()`: **no changes.** Still bare
   `WiFi.disconnect()` + `WiFi.begin()` against NVS, forever, on the
   existing cadence.
4. `WifiSection`: scan-connect success appends/updates an entry in
   `/wifi_networks.json` (in addition to NVS, as today) with LRU eviction
   past `WIFI_MAX_SAVED`. New "Saved networks" row on the Status screen →
   list view (reuse the existing scan-list row renderer) → tap an entry to
   connect directly (stored creds, no keyboard) or Danger-confirm-delete
   it. "Forget network" unchanged in position/feel, now scoped to one list
   entry rather than the only file that existed.
5. **Debug observable (VE-2-1):** add `get wifiSaved` →
   `{count, entries:[{ssid, lastUsedMs}, ...]}`, same `dbgGet()` chain
   pattern already used by `AppsSection::submenu()`/`prDivKm()`. Without
   this there's no way for an automated test to know which row index in
   "Saved networks" maps to which SSID before tapping it, and no way to
   assert the LRU-eviction outcome OQ4 below leaves as an open policy
   question — the getter is what makes that policy, whatever it ends up
   being, actually testable rather than just implemented.

Not adopted: Option A (capacity-math risk on `settings.json` for no
benefit), Option C (no multi-profile NVS API exists), Options D/E/G
(autonomous switching — explicitly rejected by human decision, not a
technical rejection).

## Open questions

- **OQ1 (ADR needed?) — RESOLVED 2026-08-04.** Human signed off on this
  design doc directly, no separate ADR — boot/supervisor are unchanged, so
  there was never a boot-order or recovery-policy decision to formalize.
- **OQ2 (password storage — plaintext, same as today).** `/wifi_creds.json`
  already stores the password in cleartext SPIFFS today; this design
  extends that posture to a list, doesn't change it. Flagging as a
  conscious carry-forward, not an oversight.
- **OQ3 (`WIFI_MAX_SAVED` cap value).** Proposed 5 as a first guess (fits
  UI, covers realistic "home + work + hotspot" recall) — not load-bearing
  on anything technical, easy to revisit.
- **OQ4 (LRU eviction policy exact trigger).** "Least-recently-connected"
  read off `lastUsedMs` is the obvious choice but needs Developer to decide
  exactly when that timestamp updates — small enough to leave to
  implementation.
- **OQ5 (should "Saved networks" show which entry is currently active?).**
  Almost certainly yes (a list you can't tell the current state of is
  confusing) — flagged only because it wasn't spelled out as a UI
  requirement above; Developer/QM polish detail, not a design fork.

## Exit criteria

- DUT (VE-2-2): flash a device with only the legacy `/wifi_creds.json`
  present (i.e. every DUT's actual current state — this is the upgrade
  path every existing device hits first, not a hypothetical), boot, and
  confirm `/wifi_networks.json` is created with the migrated single entry
  — `get wifiSaved` (per VE-2-1's getter) reports `count==1` with the
  correct SSID.
- DUT: with 2+ saved networks, boot and background behavior are
  byte-for-byte unchanged from today (same NVS retry, same timings) —
  confirms the "no autonomous switching" requirement holds, not just at
  the design level.
- DUT: Settings → WiFi → Saved networks lists all saved entries
  (cross-check against `get wifiSaved`); tapping a non-active, in-range
  entry connects to it (manual switch) and that becomes the new
  NVS-active profile.
- DUT: tapping a saved entry that's *not* in range fails the same way a
  fresh manual connect attempt fails today (Result screen, "Network not
  found," Retry/Cancel) — no silent fallback to anything else.
- DUT: deleting a non-active entry doesn't disconnect; deleting the active
  entry via "Forget network" behaves exactly as today (disconnect +
  reboot), now scoped to just that one list entry.
- Regression: `run/test` WiFi suite (`T-WIFI-01..06`, `settings-wifi`'s
  registered test ids) still green.
- `./run/check` 5-gate green.

## Registers

**Committed 2026-08-04** (`feature_inventory.yaml`), following human
sign-off:

New feature: **wifi-002** — "Multi-network WiFi credential storage +
manual-switch UI (`WifiSection` 'Saved networks' screen). No change to
boot connect order or `wifiDiag` supervisor behavior — explicit non-goal."
Pointer: this design doc.

No new cross-feature edge proposed. This extends **`settings-wifi`**
(`WifiSection`'s connect-success/forget/UI surface) directly rather than
introducing a new interaction with another feature — `wifi-diag-001`
(the supervisor) is explicitly *not* touched, so no edge to it is needed.
No change to `settings-001`'s category-list layout (WiFi stays one
category; "Saved networks" is a sub-view within it) — contrast
`M-SYS-REBOOT.md`, which does add a category.
