# Design — M-SYS-REBOOT: Settings → System → Reboot (user-triggered soft reboot)

> Owner: Architect
> Status: draft
> Date: 2026-08-04
> Feeds: ADR-NNN (TBD — human to decide if this small a change warrants its
> own ADR, or whether accepting this design doc directly is enough; flagged
> as an open question below rather than pre-judged)
> Tracked-as: — (not yet scheduled; PM to file a task if this design is
> accepted)
> Registers: settings-system (new feature) · X047 (new cross-feature edge) —
> **not yet committed to the registry files**, per this project's own
> "reserve at acceptance, not before" precedent (see `M-HEAP-FRAGMENTATION.md`'s
> parked entry). Listed in full under §Registers below for the human/PM to
> commit if this design is accepted.

**Revision note (2026-08-04, same day):** folded in VE's testability review
(`docs/architecture/designs/sys-reboot-wifi-multi-VE-review.md`, verdict
approve-with-changes, no blockers). Both majors closed below: VE-1-1 (§Lean
step 2, a stable pre-restart log line) and VE-1-2 (§Exit criteria, the
"confirm on-device" layout check stated as human-eyeball-only, not
automatable with current tooling). Minors/informational items not folded
here — left for implementation time per the review's own recommendation.

## Context / pain points

The device occasionally fragments its heap badly enough that an app fails to
open or a fetch is refused. This is a known, previously-investigated failure
class — `M-HEAP-FRAGMENTATION.md` root-caused one specific instance
(Spotify's TLS connect permanently splitting the largest free block from
~73 KB down to a ~43 KB ceiling for the rest of the boot) and left it
**parked**: the structural fix (Option E, sequencing the WebRadio fetch
before Spotify's TLS connect) wasn't adopted, and the same doc's own OQ4
spike proved that partial in-process recovery (`vTaskDelete()`ing
`spotifyTask`) does **not** reliably un-fragment the heap (6 of 7 trials
stayed pinned at the ceiling — see that doc's OQ4 write-up). So today, once
a boot's heap has fragmented, there is no in-session recovery — the failure
persists until the device is power-cycled.

Today's only reset paths:
- A hard power cycle (physical, requires access to the device).
- `ESP.restart()` reachable only via the `SERIAL_DEBUG` `reboot` command
  (`main.cpp:4022-4026`) — requires a USB/serial connection, not available
  to an end user.
- `ESP.restart()` as an unprompted side effect of WiFi's "Forget network"
  action (`wifiSection.h:372-378`, `_doForget()`) — exists, but is scoped to
  the WiFi-credential-reset flow, not a general-purpose recovery control.

There is no user-facing, touch-only way to recover from a fragmented-heap
state (or any other "app won't open, device needs a fresh start" symptom)
without physical access to pull power or a laptop on serial. That's the gap
this design closes: **expose the existing, already-proven `ESP.restart()`
mechanism as a discoverable Settings control**, not invent a new recovery
mechanism.

### Why a full reboot succeeds where the OQ4 spike's partial teardown failed

Worth stating explicitly since `M-HEAP-FRAGMENTATION.md` is sitting right
next to this design and a reader could reasonably ask "didn't we already
measure that tearing things down doesn't fix this?" — the OQ4 spike measured
a **partial, in-process** teardown (`vTaskDelete()` of one task, while the
rest of the heap allocator's live state — every other task's allocations,
the TLSF free-list bucket structure itself — stayed exactly as it was). That
measured that *deleting spotifyTask specifically* doesn't reach the wedge.
`ESP.restart()` (`esp_restart()` under the hood) is a full chip reset: the
entire heap allocator reinitializes from the linker's `.bss`/`.data`
boundaries on the next boot, with **zero** carried-over allocator state.
There is no wedge to fail to reach — the wedge doesn't survive a reset at
all. This is the same mechanism as a watchdog-triggered reboot (which this
project already relies on and has verified doesn't corrupt persisted state —
see `TASK-285`/`TASK-288` crash-recovery history), not a variant of the
OQ4 spike's mechanism. The two findings don't conflict.

One caveat to keep honest: OQ4 also found that under `WebRadio` boot mode,
`lfbInt` is *already* ~43 KB at cold boot before Spotify ever connects (some
resident WebRadio-mode state, not Spotify TLS, pins it). A soft reboot
resets to **whatever that mode's true cold-boot baseline is** — for
WebRadio-mode boots specifically, that baseline may itself be below the
"pristine" ~73 KB figure quoted for Spotify-mode boots. It is still
strictly better than not rebooting (no fetch/app has ever *specifically*
lost against the WebRadio-mode cold-boot baseline — every observed failure
in that doc's data involved additional dynamic fragmentation stacked on top
of it), just not a guaranteed return to the highest baseline number in that
doc. Not a reason to reject this design — a plain, honest bound to record.

## Goals

1. Give the user a touch-only way to recover from "device is fragmented /
   sluggish / an app won't open" without physical power-cycle or serial
   access.
2. Reuse the existing, already-proven `ESP.restart()` call — no new reset
   mechanism, no new firmware risk surface.
3. Don't lose any state that isn't already lost on every other reboot path
   this project relies on (crash, watchdog, power cycle) — per-field
   settings autosave (see below) means there's no new "unsaved changes"
   risk to design around.
4. Make the control impossible to trigger by accident (it's a full device
   reset, mid-playback, mid-fetch — more consequential than "Forget
   network").
5. Fit inside `SettingsApp`'s existing category-list layout budget without
   restructuring it.

## Design space (options + tradeoffs)

### Where does the control live?

**A — New top-level "System" category, 7th entry in `SettingsApp`'s category
list, single-row section body ("Reboot device").** Matches the ask
literally (Settings → System → Reboot) and matches how every other
cross-cutting, non-app-specific control already surfaces (WiFi, Time &
Location, Touch Calibration, Display, LED are all peers at this level).
**LEAN.**

**B — Bury it as a row inside the existing "Applications" section.**
Reject: `AppsSection` is specifically about per-app configuration
(`kConfigurableApps`); a device-wide reset isn't scoped to an app and would
be a confusing, undiscoverable place to look for it.

**C — A dedicated always-visible reboot icon in the taskbar or header
chrome, outside Settings entirely.** Reject: over-scoped for what's asked,
and every other "cross-cutting device control" in this codebase already
lives in Settings (precedent: WiFi forget, display cal). No reason to break
that pattern for this one control. Settings is also naturally where a user
already goes to look for "system-level" actions.

### Layout capacity check (this is the part worth flagging explicitly)

`SettingsApp`'s category list renders `SETTINGS_CAT_COUNT` rows of
`SETTINGS_ROW_H = 26`px inside a `SETTINGS_CONTENT_H = 212`px content area,
plus one more 26px row for "Cancel" below a separator
(`main.cpp:1016-1040`). Today: `SETTINGS_CAT_COUNT = 6`
(WiFi/Time & Location/Touch Calibration/Display/LED/Applications) → 6×26 +
26 (Cancel) = **182px used, 30px spare**. Adding a 7th category ("System")
brings it to 7×26 + 26 = **208px used, 4px spare** — it fits, but just
barely, and **there is no room left for an 8th category** without either
shrinking `SETTINGS_ROW_H`, dropping the separator gap, or making the
category list scroll. This isn't a blocker for this design, but it is a
real constraint the next designer to reach for "add a Settings category"
will hit immediately — worth registering as a matrix edge (see §Registers)
rather than rediscovering by trial and error.

### Confirm-before-reboot, or direct tap?

**D — Direct tap, no confirmation** (mirrors `wifiSection.h`'s "Forget
network" — tap fires `ESP.restart()` immediately, no intermediate screen).
Reject as the primary flow: "Forget network" only discards WiFi credentials
(recoverable — re-enter the password); a reboot discards **all**
in-progress session state — whatever app was mid-flight, WebRadio's audio
pump, an in-flight fetch, Spotify's playback position — across the entire
device. That's a materially bigger blast radius for a single mis-tap than
the one existing no-confirm precedent, and this codebase already has a
house pattern for exactly this severity of action.

**E — Danger-styled confirm screen using the existing `SButton`/
`sButtonBar` kit** (`settingsWidgets.h`, `SBtnStyle::Danger`,
"TASK-317 confirm frame" — already used for the PrLoc delete-slot
confirmation, `appsSection.h:900`). Tap "Reboot device" row → full-canvas
confirm screen ("Reboot now? Playback and any unsaved activity will
restart.") with `[Cancel]` (Neutral) / `[Reboot]` (Danger) buttons via
`sButtonBar`. Tapping `[Reboot]` fires the existing `SButton::flash()`
acknowledgement, then `ESP.restart()`. **LEAN.** Zero new widget code — this
is exactly what the confirm-frame kit exists for, and reusing it here is
free.

### Does this interact with pending/unsaved Settings edits?

Checked, not assumed: every existing `SettingsSection` widget calls
`saveSettings()` (→ `SettingsStorage::save()`) **immediately on change**
(displaySection.h, ledSection.h, appsSection.h — 40+ call sites, all
per-field, not batched). `SettingsApp::_cancel()`'s snapshot/rollback
(`main.cpp:988-992`) exists for the "Cancel" affordance at the category-list
level, not because edits are otherwise held unsaved — by the time a user
could navigate into a hypothetical "System" section, any edit made in
*another* section this same Settings visit is already durably on SPIFFS.
**Conclusion: no special handling needed.** A reboot triggered from the
System section loses nothing beyond what a watchdog/crash reboot already
loses today (in-flight, not-yet-persisted runtime state — expected and
already accepted project-wide).

## Lean / decision

**Adopt A + E.** Concretely:
1. `SettingsApp`: bump `SETTINGS_CAT_COUNT` to 7, add `"System"` to
   `kLabels[]`, wire a new `SystemSection` at `_sections[6]` — same pattern
   as the existing five wired sections.
2. New `app/src/settings/systemSection.h`: single-row body ("Reboot
   device", chevron) that pushes a confirm screen (built from
   `SButton`/`sButtonBar`, `SBtnStyle::Danger` for the reboot action) on
   tap. Confirming fires `SButton::flash()`, then **emits a stable-prefix
   log line — `[settings] system-reboot confirmed` — immediately before**
   calling `ESP.restart()` directly (VE-1-1: mirrors `cmdReboot`'s own
   `{"ok":true,"cmd":"reboot"}` ack, `main.cpp:4023-4026`, so a harness
   reconnecting after the restart can confirm this was the confirm-tap path
   firing as designed, not a coincidental crash/TWDT reset landing at the
   same moment). Otherwise the same one-line `ESP.restart()` call already
   proven at `wifiSection.h:377` and `main.cpp:4026` — no new reset
   mechanism.
3. No changes to `settingsStorage.h`/`SettingsApp::_cancel()` — confirmed
   unnecessary above.

Not adopted: Option B/C (wrong location), Option D (confirm-less — wrong
severity match for this action).

## Open questions

- **OQ1 (ADR or not).** Is this change small/low-risk enough to ship as an
  accepted design doc alone, or does the project want a dedicated ADR for
  "user-triggered soft reboot is a supported recovery mechanism" (arguably
  a real architectural statement: it's this project's first admission that
  in-session recovery from fragmentation is a UI feature, not just a
  debug-serial escape hatch)? Human call — leaning toward "design doc is
  enough" given the mechanism is 100% reused, not new, but flagging rather
  than deciding unilaterally.
- **OQ2 (label copy).** Exact confirm-screen wording is a Developer/QM
  polish detail, not gated here — "Reboot now? Playback and any unsaved
  activity will restart." is a placeholder, not a final string.
- **OQ3 (does this belong to M-HEAP-FRAGMENTATION or stand alone).** This
  design deliberately does **not** reopen or amend `M-HEAP-FRAGMENTATION.md`
  (still correctly `parked` — its own structural fix is a separate,
  larger question about whether to sidestep the ceiling at all). This
  design is a narrower, independent, much-lower-risk mitigation (give the
  user a manual escape hatch) that's useful regardless of whether Option E
  there is ever picked back up. Keeping them as separate docs so accepting
  this one doesn't imply anything about that one's parked status.
- **OQ4 (should System eventually hold more than Reboot).** Not scoped here
  — e.g. a "heap/diagnostics" readout, firmware version, factory reset are
  all plausible future System-section rows, but adding them now would be
  scope creep against the actual ask. Flagged only so the 7th-category
  layout decision above is understood as "makes room for a System section,"
  not "makes room for exactly one row forever."

## Exit criteria

- DUT: tapping Settings → System → Reboot device → confirm → Reboot
  produces a full device restart (boot splash reappears) within the normal
  boot-time window, landing back on whatever app/mode was active pre-reboot
  per existing boot-restore behavior (`playerMode` persistence, etc. —
  unchanged by this design).
- DUT (VE-1-1): the harness's captured serial output shows
  `[settings] system-reboot confirmed` as the last line before the boot
  banner — distinguishes this specific trigger from any other reset cause.
  Reconnect-after-restart itself follows the already-proven pattern from
  `T-DISP-04`/`T-TIME-04`/`T-APPS-08`/`T-LED-11` (all PASS against the
  serial `reboot` command, `test_plan.md:2144-2146`) — no new harness
  mechanism needed, just the new log line to assert against.
- DUT: after tapping the System row from the category list,
  `get settingsSection` reports `section==6` (same observable pattern as
  `T-WIFI-04`'s `section==-1` check, `main.cpp:951-955`) — confirms the
  category is reachable before exercising the confirm flow above.
- DUT: tapping Cancel on the confirm screen returns to the System section
  with no restart and no side effects.
- DUT: triggering Reboot while WebRadio is actively playing / a fetch is
  in-flight does not corrupt SPIFFS-persisted settings or leave the device
  in a state requiring `flash-fs` to recover (same bar every other reboot
  path already clears).
- `./run/check` 5-gate green (category-list layout change, low risk, but
  gate anyway per BP-008).
- Manual layout check (VE-1-2: **human-eyeball only, not automatable with
  current tooling** — `run/screendump` opens its own serial connection,
  which resets the DUT via CH340 DTR-on-open before a pixel can be read,
  per `best_practices.md`'s live rule and LL-051; there is no way to
  navigate to the 7-category list on one connection and screenshot it from
  a fresh tool invocation without a `screendump.py` change to navigate
  in-connection, which is out of scope here): category list with 7 entries
  + Cancel renders fully inside the 212px content area with no clipping
  (208px computed above — should be a non-issue, confirmed by eye on
  device, not by the arithmetic alone).

## Registers

**Not yet committed** (draft status — per this project's "reserve at
acceptance" precedent). If accepted:

New feature: **settings-system** — "Settings → System section: device
soft-reboot control (`ESP.restart()` exposed as a confirm-gated UI action)."
Pointer: this design doc + `app/src/settings/systemSection.h` (once
created).

New cross-feature edge: **X047** — `settings-system` × `settings-001`
(`SettingsApp`'s shared category-list layout/`SETTINGS_CAT_COUNT` budget) —
`dependency`, `risk: low`. Description: category-list content area
(212px / 26px rows) is now 208px used / 212px available with 7 categories
+ Cancel — effectively zero headroom for an 8th category without a layout
change (smaller row height, dropped separator, or scrolling list). Anyone
adding a future Settings category should read this edge first.
`test_coverage: []` — VE to attach once a test id exists.
