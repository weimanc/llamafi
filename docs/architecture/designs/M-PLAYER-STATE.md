# M-PLAYER-STATE — Player mode as persisted, user-editable state

> Owner: Architect · Status: **DESIGN** · 2026-06-27
> Scope: TASK-259 (runtime mode toggle — **implemented, RAM-only, DUT-verified 2026-06-27**) + this design's
> additions: **SPIFFS persistence** + a **Settings → Applications → Player** toggle to show/edit it (OQ4).
> Couples: M-MEMBUDGET (mode mutual-exclusion the budget leans on). Feature: `player-state-001`.

## 1. Context & goal

The "player" is **one slot with two modes — `{Spotify | WebRadio}`**. Eject toggles the mode; the taskbar
player slot restores the last-active mode. The runtime half shipped in TASK-259 (`a825521`, RAM-only,
`g_lastPlayerMode`). This design adds the two pieces the user requested:

1. **Persist the mode across reboot** in the SPIFFS settings store (OQ4).
2. **Expose it in the Settings UI** under *Settings → Applications → Player*, as a show/edit/toggle row.

## 2. State model (single source of truth)

Collapse the runtime `g_lastPlayerMode` and the persisted setting into **one field**:
`g_settings.playerMode : PlayerMode { Spotify=0, WebRadio=1 }`. There is no separate runtime var — every
reader/writer uses `g_settings.playerMode`:

| Actor | Action on `g_settings.playerMode` |
|---|---|
| Eject toggle (`SpotifyApp`/`webRadioApp`) | flips the value, requests a persist (§4) |
| `resolvePlayerSlot()` (taskbar restore, `main.cpp`) | reads it — taskbar player slot → that mode |
| Settings UI (Player section) | shows + toggles it, `saveSettings()` |
| Boot (`settingsStorage::load`) | restored from SPIFFS |

This removes the TASK-259 `g_lastPlayerMode` global in favour of the settings field (refactor, behaviour
identical). **Invariant:** WebRadio stays its own eject-only `AppId` (not added to the taskbar — TASK-242 /
LL-085 invariant preserved); the mode field selects *which* the player slot resolves to.

## 3. Persistence — SPIFFS schema

`AppSettings` (`settingsStorage.h`): add `uint8_t playerMode;` (store the enum as `uint8_t`). Mapping in
`settingsStorage.cpp`, mirroring the existing `webRadio`/`stock` nested-object pattern:

- **defaults():** `g_settings.playerMode = (uint8_t)PlayerMode::Spotify;`
- **load():** new top-level object (mode spans both Spotify and WebRadio, so it is **not** under `webRadio`):
  `if (doc.containsKey("player")) g_settings.playerMode = doc["player"]["mode"] | 0;`
- **save():** `doc.createNestedObject("player")["mode"] = g_settings.playerMode;`

`settings.json` is on the same SPIFFS that survives a firmware reflash (per CLAUDE.md), so the mode persists
across both reboot and app-flash.

## 4. Persist policy (flash-wear)

Eject is a **deliberate, low-frequency** user action (a handful of times per session), and the existing
settings sections already `saveSettings()` synchronously on each change. So **immediate save on toggle is
acceptable** — with one guard: **no-op write avoidance** (skip the save if the value is unchanged). If field
telemetry ever shows excessive eject churn, fall back to a coalesced/dirty-flag deferred save on
`suspend()`; not needed for v1. (Decision: immediate-save + unchanged-skip.)

## 5. Settings UI — Settings → Applications → Player

The configurable-apps list is **codegen**: `appRegistry.h` column 3 (`configurable`, `1 = appears in Settings
> Applications`) → `gen_app_registry.py` → `app/gen/configurable_apps.h`, consumed by
`settings/appsSection.h`. Spotify is `cfg=0` today.

**Changes:**
1. `appRegistry.h`: flip Spotify to **`APP_X( Spotify, 'S', 1 )`**, then **re-run
   `app/tools/gen_app_registry.py`** (regenerates `gen/configurable_apps.h`; the `run/check` [5/5] staleness
   gate enforces this — a stale gen fails the build).
2. `settings/appsSection.h`: add the `AppId::Spotify` case to the repaint + cycle dispatch switches
   (`:89` / `:175`), mirroring `_repaintClock`/`_cycleClock` (single-row section):
   - `_repaintPlayer()`: one row `{ "Mode", playerMode==WebRadio ? "WebRadio" : "Spotify" }`.
   - `_cyclePlayer(row)`: toggle `g_settings.playerMode`, `saveSettings()`, repaint. (If the toggled-away mode
     is the *currently foreground* one, the change applies on next entry to the player slot — the settings
     screen is itself a different app, so no live app-switch is forced from here.)

**Label (OQ-LABEL):** the section title comes from `kConfigurableApps[_sub].name` = the app's registry name,
which is `"Spotify"`. The user asked for **"Winamp"/"Player"**. Two options: (a) accept `"Spotify"` for v1
(zero extra work); (b) add a **display-name** to the codegen (4th `APP_X` column) so the list can show
`"Player"` while the `AppId` stays `Spotify`. **Recommend (b)** — small codegen addition, and it reads
correctly now that the slot hosts both Spotify and WebRadio. Decide before impl.

## 6. Boot behaviour (OQ-BOOT)

`currentAppId` boots to `AppId::Spotify` (the player slot). Question: if the persisted mode is WebRadio,
should the device **cold-boot into WebRadio**?
- **v1 (recommended):** persist the mode + use it for taskbar restore and the settings display, but **cold
  boot still lands on the Spotify view** of the player slot. Auto-launching radio at boot is governed by the
  *existing* `webRadioAutoplay` knob ("reconnect last station on resume") — these compose; do not duplicate.
- **v2 (deferred):** boot directly into the persisted mode. Couples with `webRadioAutoplay` and the
  M-MEMBUDGET arena (a boot-into-WebRadio appliance is the Option-A-lite story). Out of scope here.

## 7. Components touched

| File | Change |
|---|---|
| `app/src/settingsStorage.h` | `+ uint8_t playerMode;` in `AppSettings`; `enum PlayerMode` |
| `app/src/settingsStorage.cpp` | defaults / load / save mapping (new `player` object) |
| `app/src/main.cpp` | replace `g_lastPlayerMode` with `g_settings.playerMode` in `switchApp()` tracking + `resolvePlayerSlot()`; init implicit (loaded before first app) |
| `app/src/appRegistry.h` | Spotify `cfg` 0→1 (+ optional display-name column) |
| `app/gen/configurable_apps.h` (+ siblings) | **regenerated** by `gen_app_registry.py` |
| `app/src/settings/appsSection.h` | `_repaintPlayer` / `_cyclePlayer` + dispatch cases |
| eject sites (`main.cpp` Spotify handler, `webRadioApp.h:309`) | write `g_settings.playerMode` + persist on toggle |
| serial dbg | **add `get playerMode`** (VE ask) — turns the persistence/settings tests from MANUAL into agent-driven (the CHALLENGE-1 pattern from the last settings milestone) |

## 8. Verification

- **Test ids (VE B2 — required for sign-off):** `T_PS_PERSIST_01` (eject→reboot→slot restores mode),
  `T_PS_PERSIST_02` (settings toggle → `player.mode:1` in JSON), `T_PS_SETTINGS_01` (Player row renders +
  `_cyclePlayer` toggles, agent-driven via `get playerMode`), `T_PS_NOOP_01` (unchanged-value skips the save),
  `T_PS_NAV_01` (regression: other apps' Applications tap-Y still correct after the Spotify `cfg=1` insertion —
  the settings-nav coordinate-drift hazard), `T_PS_TASKBAR_01` (regression: WebRadio still absent from taskbar).
- **Offline / build:** `run/check` 5/5 — critically [5/5] codegen-staleness (the `appRegistry` edit must have
  its gen regenerated and committed) and golden.sha256.
- **Settings round-trip (offline-ish):** toggle in Settings → `saveSettings()` writes `player.mode` to
  `settings.json`; verifiable by `run/spiffs pull spotify… settings.json` and inspecting JSON (no DUT play
  needed).
- **DUT (when available):** set mode → reboot → confirm taskbar player slot restores the persisted mode;
  toggle via eject → reboot → confirm it persisted; toggle via Settings UI → confirm both the live behaviour
  and the JSON.

## 9. Open questions

- **OQ-LABEL** (§5): show `"Spotify"` vs add a `"Player"`/`"Winamp"` display-name column to the codegen.
- **OQ-BOOT** (§6): cold-boot-into-mode (v2) vs taskbar-restore-only (v1). Recommend v1.
- **OQ-WEAR** (§4): immediate-save (recommended) vs deferred — revisit only on observed churn.

## 10. Links

TASK-259 (runtime toggle, DUT-verified 2026-06-27 — `a825521`) · M-MEMBUDGET §2c/4a · `settings-001`
(SettingsApp + SPIFFS) · `taskbar-001` (app-shell dispatch / `switchApp`) · `app-interface-001`
(init/resume/suspend) · ADR-046 (Spotify dormant-stub bar) · NEW-APP-CHECKLIST (codegen-staleness gate).
