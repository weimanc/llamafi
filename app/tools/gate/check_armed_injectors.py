#!/usr/bin/env python3
"""check_armed_injectors.py — TASK-635 §2.5 (M-HARNESS2 R14) completeness gate.

"No declaration ships without a mechanical check." `armedInjectors.h` is a
hand-maintained X-macro table; nothing stops a new `set`/`dbgSet` key from
arming state exactly like `wrDeadUrls` or `nowFrozen` do while nobody adds it
to the table `get armed` / `set injclear` expand. This gate is the mechanical
check: it extracts every console `set` key that exists (`gen/gen_set_keys.py`
— cmdSet.cpp's own raw-args and var/val chains, plus every per-app `dbgSet`/
`dbg_set` body under app/src), and asserts each one is accounted for exactly
once, either as:

  * an arming key for a real injector in `armedInjectors.h` (`ARMED_BY`), or
  * a key that is NOT an injector, with a one-line reason that is actually
    true of its handler (`NOT_INJECTORS`).

Binding design: docs/architecture/designs/M-HARNESS2-armed-state-task635.md
§2.2 (membership rule + exclusions) and §2.3 (the fourteen initial members).

FOUR FINDINGS, all blocking, lands AT ZERO with no ledger:

  F1  a `set` key extracted from source is in neither `ARMED_BY`'s values nor
      `NOT_INJECTORS` — an undeclared key, exactly the gap R14 exists to close.
  F2  a `NOT_INJECTORS` or `ARMED_BY` key no longer exists in source — a stale
      row (BP-024 is additive-only, so this means the gate's own ledger, not
      the console, drifted).
  F3  an injector listed in `armedInjectors.h`'s `ARMED_INJECTORS_TABLE` has no
      `ARMED_BY` entry — the gate can't prove anything arms it.
  F4  an `ARMED_BY` entry names an injector that isn't actually in the header
      — a typo'd or removed injector name.

KNOWN LIMIT (see gen_set_keys.py's own docstring, not repeated silently here):
scope is `set` + `dbgSet`/`dbg_set` keys only. Other console verbs (`get`,
`tap`, …) and other consoles' top-level commands (cmdMisc.cpp/cmdSystem.cpp/
cmdSd.cpp/cmdTouch.cpp) that are NOT routed through `cmdSet.cpp` are out of
scope for this pass — cheap to extract now, and the entire surface the design
doc's §2.2 membership rule reasons about. Widen it the day a command outside
`set` is found to arm state.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_armed_injectors.py [--list]
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, os.path.join(TOOLS, "gen"))

from gen_set_keys import collect as collect_set_keys   # noqa: E402

ARMED_INJECTORS_H = pathlib.Path(ROOT) / "app/src/debug/armedInjectors.h"

#: One `X(name, ...)` row per line in ARMED_INJECTORS_TABLE. Matched
#: structurally (first arg of each `X(` invocation inside the macro), not by
#: re-deriving the whole table shape — the header is the single source of
#: truth this gate reads, never re-implements.
_X_ROW = re.compile(r'^\s*X\(([A-Za-z0-9_]+),\s*\\?\s*$', re.MULTILINE)


def injectors_in_header() -> list[str]:
    """Every injector `name` in armedInjectors.h's ARMED_INJECTORS_TABLE."""
    src = ARMED_INJECTORS_H.read_text()
    return sorted(set(_X_ROW.findall(src)))


# ── ARMED_BY — injector name -> the console `set` key(s) that arm it ────────
#
# Most injector names match their arming key 1:1 (`aeDmaFloor` armed by
# `set aeDmaFloor ...`). Four do not — named explicitly per the TASK-635 ask:
#   prInject        armed by `set prInjectAircraft ...`
#   nowFrozen       armed by `set now <epoch> freeze`
#   casRetryOff     armed by `set casRetry 0`
#   teletextContent armed by `set teletextPageContent <hex>`
ARMED_BY: dict[str, list[str]] = {
    "nowFrozen":         ["now"],
    "aeDmaFloor":        ["aeDmaFloor"],
    "aeNoArena":         ["aeNoArena"],
    "aeFailAudio":       ["aeFailAudio"],
    "arenaHold":         ["arenaHold"],
    "casRetryOff":       ["casRetry"],
    "certbreak":         ["certbreak"],
    "prForceParseFail":  ["prForceParseFail"],
    "geocode":           ["geocode"],
    "wrDeadUrls":        ["wrDeadUrls"],
    "wrPosbarSimDrain":  ["wrPosbarSimDrain"],
    "prInject":          ["prInjectAircraft"],
    "teletextContent":   ["teletextPageContent"],
    "ldrRaw":            ["ldrRaw"],
    "spotifyWedge":      ["spotifyWedge"],
    "bgPollOff":         ["bgPoll"],
}

# ── NOT_INJECTORS — every other extracted `set` key, with a reason that must
# be TRUE of its actual handler (read the code, don't guess). Grouped to
# match the design doc's own categories where one applies.
NOT_INJECTORS: dict[str, str] = {
    # -- design §2.2's named rig/diagnostic exclusions -----------------------
    "fault":       "rig instrument (`set fault bod <level>`) — TASK-557/678's "
                   "bodWatch fault injector, excluded by design §2.2 (bod*)",
    "logLevel":    "changes observation (log verbosity), not an app's verdict "
                   "path — design §2.2 exclusion",
    "logKeep":     "changes observation (log tag allowlist), not an app's "
                   "verdict path — design §2.2 exclusion",
    "wifiPs":      "radio power-save A/B toggle, not a verdict-path override "
                   "— design §2.2 exclusion",
    "beaconWatch": "diagnostic beacon-timeout watcher on/off, not a "
                   "verdict-path override — design §2.2 exclusion",
    "cooldown":    "the harness arms this itself before almost every tap and "
                   "it expires by time — design §2.2 exclusion",
    "nvsSsid":     "writes flash NVS; clearing that is not a RAM operation, "
                   "so an armed-set entry `injclear` cannot clear would be a "
                   "lie — design §2.2 exclusion",

    # -- clause-3 exclusions: overwritten by the real path, so "forced" and
    # "real" cannot be told apart without adding state (design §2.2) --------
    "wrState":        "overwritten by the real playback path on every state "
                      "transition — design §2.2 clause-3 exclusion",
    "songDuration":   "overwritten by the real /me/player poll — design §2.2 "
                      "clause-3 exclusion (named explicitly)",
    "wrBufPct":       "overwritten every tick by the real buffer-fill EMA "
                      "path — design §2.2 clause-3 exclusion (named explicitly)",
    "wrIcy":          "overwritten by the real ICY StreamTitle callback — "
                      "design §2.2 clause-3 exclusion (named explicitly)",
    "fetchFailed":    "a real Stock fetch failure also sets this — design "
                      "§2.2 clause-3 exclusion (named explicitly)",
    "fetchErrorCode": "a real Stock fetch failure also sets this "
                      "(stockApp.cpp:357, same struct as fetchFailed)",
    "wrUrl":          "the injected station is overwritten by the next real "
                      "station fetch (_stations/_stationCount), same "
                      "overwrite category as wrState/wrBufPct",
    "teletextPage":   "a real navigate() sets the same field; g_settings."
                      "teletextPage is also the persisted real-navigation value",
    "teletextSubpageNext": "a real page fetch's ns= param sets the same "
                           "field (dataTaskStorage.cpp) — indistinguishable "
                           "from an injected value without new state",
    "teletextSubpagePrev": "a real page fetch's ps= param sets the same "
                           "field (dataTaskStorage.cpp) — indistinguishable "
                           "from an injected value without new state",
    "backoff":        "a real poll failure advances s_consecutiveFailures the "
                      "same way (doPoll's own latch rule) — clause-3 exclusion",
    "lastHttp":       "the next real poll overwrites this — clause-3 "
                      "exclusion (source comment: \"Overwritten by the next "
                      "real poll\")",
    "lastOkMs":       "the next real poll overwrites this — clause-3 "
                      "exclusion (source comment: \"Overwritten by the next "
                      "real poll\")",
    "queue":          "the next successful real poll overwrites the "
                      "snapshot — clause-3 exclusion (source comment: "
                      "\"Overwritten by the next successful real poll\")",

    # -- settings-like: a persisted user-facing config value, not a forced
    # override distinguishable from a real (or future on-device UI) choice --
    "fmt24h":      "settings path (g_settings.fmt24h, SettingsStorage::save())",
    "dateFmt":     "settings path (g_settings.dateFmt, SettingsStorage::save())",
    "clockStyle":  "settings path (g_settings.clockStyle, SettingsStorage::save())",
    "nixieTheme":  "settings path (g_settings.nixieTheme, SettingsStorage::save())",
    "vfdTheme":    "settings path (g_settings.vfdTheme, SettingsStorage::save())",
    "playerMode":  "settings path (persistPlayerMode -> g_settings, survives "
                   "reboot by design — TASK-260/413)",
    "prloc":       "settings path (g_settings.prLocs[], SettingsStorage::save())",
    "prRange":     "settings path (g_settings.prRangeIdx via _setPreset(), "
                   "SettingsStorage::save()) — same primitive the real range "
                   "strip tap uses",
    "prPollSec":   "settings path (g_settings.prPollSec, SettingsStorage::save())",
    "stockMode":   "settings path (g_settings.stockMode)",
    "wrAutoSkip":  "settings path (g_settings.webRadioAutoSkip)",
    "wrHwMod":     "settings path (g_settings.webRadioHwMod)",
    "wrMaxVol":    "settings path (g_settings.webRadioMaxVolume)",
    "speedK":      "runtime tuning knob (PleditView scroll speed), same "
                   "config-not-injection category as the settings keys above",
    "wrSpeedK":    "runtime tuning knob mirroring `speedK` on the WebRadio "
                   "PleditView instance — same config category",
    "wrVol":       "drives the same runtime volume control a real UI action "
                   "would (wrEffectiveVolume is the production clamp path); "
                   "not distinguishable from a real volume change",

    # -- one-shot actions: fire once, no forced state persists afterward ----
    "kbText":      "one-shot keyboard text injection, no persisted override "
                   "(KeyboardWidget::injectText, same callback as a real tap)",
    "kbOk":        "one-shot keyboard submit action (commitFromHost)",
    "kbCancel":    "one-shot keyboard cancel action (cancelFromHost)",
    "kbShow":      "one-shot action: opens the keyboard widget",
    "pick":        "one-shot picker-selection action (pickByCode), same "
                   "callback as a real row tap",
    "aePlayFile":  "drives a real action (starts FILE playback via "
                   "aeConnectFile) — not a forced override, no armed state "
                   "persists once playback starts normally",
    "plLoad":      "drives a real action (loads an M3U into the player "
                   "index) — not a forced override",
    "plPlay":      "drives a real action (plays a row by index) — not a "
                   "forced override",
    "plCursor":    "sets the real play-order cursor directly — "
                   "indistinguishable from the cursor reaching that position "
                   "through real navigation, without adding state (clause 3)",
    "fbOpen":      "drives real FileBrowser navigation (dbgFbOpen), same "
                   "path a real tap takes",
    "fbSelect":    "drives real FileBrowser navigation (dbgFbSelect), same "
                   "path a real tap takes",
    "fbCancel":    "drives real FileBrowser navigation (dbgFbCancel), same "
                   "path a real tap takes",
    "arenaStaleFree": "one-shot diagnostic probe (acquire/alloc/release/free "
                      "in one call) — no state persists after it returns",
    "scanLoop":    "self-restoring diagnostic loop — explicitly restores the "
                   "saved SSID/config and WiFi storage mode before returning; "
                   "nothing is left armed",
    "wifiScan":    "one-shot action: kicks an async scan, no persisted "
                   "override",
    "reboot":      "one-shot action (ESP.restart()) — nothing to observe "
                   "armed after a reset",
    "wifiKick":    "one-shot diagnostic action that runs its own connect "
                   "cycle to completion and re-enables auto-reconnect before "
                   "returning",
    "wifiDisc":    "one-shot action: forces a disconnect + immediate "
                   "reconnect from NVS creds",
    "settingsSave": "one-shot action: forces SettingsStorage::save(), no "
                    "state of its own",
    "triggerFetch":        "one-shot action: resets fetch timestamps to "
                           "force an immediate real fetch, named explicitly "
                           "in the TASK-635 prompt's one-shot list",
    "triggerTeletextFetch": "one-shot action: forces an immediate real fetch",
    "triggerPlaneRadarFetch": "one-shot action: forces an immediate real fetch",
    "triggerHeatmap":      "one-shot action: switches sub-view + forces an "
                           "immediate real fetch",
    "fetchErrCount":  "one-shot action: resets a counter to 0, no forced "
                      "state persists",
    "fetchOkCount":   "one-shot action: resets a counter to 0, no forced "
                      "state persists",
    "quoteOkCount":   "one-shot action: resets a counter to 0, no forced "
                      "state persists",
    "wrEject":     "one-shot action: stops audio and switches app away — no "
                   "armed state left in WebRadio",
    "wrPlay":      "drives real playback of a station index — not a forced "
                   "override",
    "wrStop":      "one-shot action: stops audio (_stopAudio)",
    "wrNext":      "one-shot action: advances to the next station",
    "wrPrev":      "one-shot action: advances to the previous station",
    "wrInjectResult": "self-consuming: parks one result for the next real "
                      "poll to consume (_pendingStations), same shape as a "
                      "real fetch landing — nothing stays armed once "
                      "consumed",
    "injclear":    "the clearing command itself — expands the same table "
                   "this gate checks, not an injector",
    "prClearInject": "the CLEAR mechanism `armedInjectors.h` invokes for the "
                     "`prInject` injector (see ARMED_BY) — not an arming key "
                     "itself",

    # -- CANDIDATE: satisfies §2.2's three clauses but is not yet in the
    # header. Left here (not silently in NOT_INJECTORS without comment) per
    # the TASK-635 prompt's instruction §5 — a real finding, filed as a
    # follow-up rather than blocking this gate.
}


def evaluate(set_keys, header_injectors) -> list[str]:
    """Pure: the four findings, so the negative suite can drive it directly
    without touching the real tree."""
    out: list[str] = []
    set_keys = set(set_keys)
    header_injectors = set(header_injectors)
    armed_by_keys: set[str] = set()
    for inj, keys in ARMED_BY.items():
        armed_by_keys.update(keys)

    # F1 — an extracted key accounted for nowhere.
    accounted = armed_by_keys | set(NOT_INJECTORS)
    for k in sorted(set_keys - accounted):
        out.append(f"F1 {k!r}: a `set` key with no ARMED_BY entry and no "
                   f"NOT_INJECTORS reason — undeclared armed state (or an "
                   f"undeclared exclusion)")

    # F2 — a ledger row (NOT_INJECTORS or ARMED_BY value) naming a key that
    # no longer exists in source.
    for k in sorted(set(NOT_INJECTORS) - set_keys):
        out.append(f"F2 {k!r}: a NOT_INJECTORS row for a `set` key that no "
                   f"longer exists in source — stale reason")
    for k in sorted(armed_by_keys - set_keys):
        out.append(f"F2 {k!r}: an ARMED_BY arming key that no longer exists "
                   f"in source — stale row")

    # F3 — a header injector with no ARMED_BY entry.
    for inj in sorted(header_injectors - set(ARMED_BY)):
        out.append(f"F3 {inj!r}: an injector in armedInjectors.h with no "
                   f"ARMED_BY entry — nothing proves what arms it")

    # F4 — an ARMED_BY entry naming an injector that isn't in the header.
    for inj in sorted(set(ARMED_BY) - header_injectors):
        out.append(f"F4 {inj!r}: an ARMED_BY entry for an injector name not "
                   f"present in armedInjectors.h")

    return out


def main(argv) -> int:
    set_keys = collect_set_keys()
    header_injectors = injectors_in_header()
    findings = evaluate(set_keys, header_injectors)
    print(f"check_armed_injectors: {len(set_keys)} set keys extracted, "
          f"{len(header_injectors)} injectors in armedInjectors.h, "
          f"{len(NOT_INJECTORS)} NOT_INJECTORS rows, {len(ARMED_BY)} "
          f"ARMED_BY entries")
    if "--list" in argv:
        for k in sorted(set_keys):
            tag = ("ARMED_BY" if k in {kk for v in ARMED_BY.values() for kk in v}
                   else "NOT_INJECTORS" if k in NOT_INJECTORS
                   else "UNACCOUNTED")
            print(f"    {k:24s} {tag}")
    if findings:
        print(f"\nFAIL: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    print("  PASS  every console `set` key is an injector or says why not")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
