#!/usr/bin/env python3
"""DUT smoke for TASK-321 (M-PR-LOCATIONS Settings Locations sub-view + slot
editor, Lookup path). Drives the real appsSection.h state machine via touch
injection (`tap`) + KeyboardWidget injection (`set kbText`/`kbOk`/`kbCancel`)
— the same primitives TASK-325 landed for exactly this purpose. The country
step is an SPickerList since M-COUNTRY-PICKER (CP-4): it is driven with
`set pick <CC>` and asserted via `get pick` (label/postcode steps keep the
keyboard injection). Plus the
`set geocode <lat> <lon> [display]` / `set geocode err <code>` stub-injection
isolation (TASK-320/VE-PRL-2) so the lookup leg needs no live network.

No dedicated `get`/dbg hook exposes _prLocState directly (not added by
TASK-321), so this asserts via the *externally observable* surface: `get kb`
(keyboard active/mode/len) and `get prloc` (final persisted slot state) —
sufficient to prove each transition actually ran, since a wrong state would
either leave the keyboard in the wrong mode/maxLen or leave prloc unchanged/
wrong after a Save.

Coordinates: list-row Ys are derived from the firmware layout constants via
row_y() below (settingsSection.h S_CONTENT_Y/S_ROW_H, appsSection.h
_appListRowH(), main.cpp SETTINGS_ROW_H); button coords stay hardcoded from
settingsWidgets.h geometry, same approach prloc_smoke.py / the preview tool use:
  Settings row "Applications"      : (100, row_y(5)=171)  category idx 5 (main.cpp kLabels), SETTINGS_ROW_H=26
  Applications row "PlaneRadar"    : (100, row_y(8, 21)=206)  idx 8 of 10, rowH=min(26, 212//10)=21
                                     (was hardcoded 223 from the 9-app/23px era — that y now hits WebRadio)
  PlaneRadar row "Locations"       : (100, row_y(5)=171)  idx 5, S_ROW_H=26
  SlotList row i                   : (100, row_y(i))
  SourceFork Lookup (hasCurrent)   : (137, 58)   sStackedBtnRect(0, 38) — empty slot, no "Current" row
  SourceFork Lookup (hasCurrent=T) : (137, 84)   sStackedBtnRect(0, 64) — filled slot, "Current" row drawn
  SourceFork Delete (hasCurrent=T) : (137, 188)  sStackedBtnRect(2, 64)
  Confirm Save/Retry/Cancel        : (47,210) (137,210) (227,210)  sButtonBar n=3 @ S_BTN_BAR_Y=190
  Error Retry/Cancel               : (69,210) (204,210)            sButtonBar n=2 @ 190
  Header back zone                 : (10, 10)
"""
import json, sys, time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
results = []

# ---- Settings-list geometry (mirrored from firmware — keep in sync) ---------
S_CONTENT_Y = 28    # app/src/settings/settingsSection.h S_CONTENT_Y
S_ROW_H     = 26    # app/src/settings/settingsSection.h S_ROW_H (== main.cpp SETTINGS_ROW_H)
S_CONTENT_H = 212   # app/src/settings/settingsSection.h S_CONTENT_H (240 - header 28)
CONFIGURABLE_APP_COUNT = 10   # app/gen/configurable_apps.h
PLANERADAR_APP_IDX     = 8    # kConfigurableApps[] order (WebRadio is idx 9)
# appsSection.h _appListRowH(): the Applications list compresses its row height
# once CONFIGURABLE_APP_COUNT * S_ROW_H no longer fits S_CONTENT_H -> 21 today.
APP_LIST_ROW_H = min(S_ROW_H, S_CONTENT_H // CONFIGURABLE_APP_COUNT)


def row_y(i, row_h=S_ROW_H):
    """Center y of row i in a settings list starting at S_CONTENT_Y."""
    return S_CONTENT_Y + i * row_h + row_h // 2


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


class Dut:
    def __init__(self):
        self.ser = serial.Serial(PORT, 115200, timeout=1)  # DTR reset on open

    def close(self):
        self.ser.close()

    def send(self, c):
        self.ser.write((c + "\n").encode())
        self.ser.flush()

    def cmd(self, c, timeout=5.0):
        self.send(c)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if line.startswith("{"):
                try:
                    r = json.loads(line)
                    if r.get("last", True):
                        return r
                except ValueError:
                    pass
        return {}

    def wait_ready(self, budget=90):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            r = self.cmd("get prloc", 3.0)
            if r.get("ok"):
                return r
            time.sleep(2)
        return {}

    def tap(self, x, y):
        return self.cmd(f"tap {x} {y}")


def loc(r, i):
    locs = r.get("locs") or []
    return locs[i] if i < len(locs) else {}


print(f"== opening {PORT} (DTR reset) ==", flush=True)
d = Dut()
boot = d.wait_ready(90)
report("D0 boot + cmd loop ready", bool(boot.get("ok")), str(boot))
s2_before = loc(boot, 2)
report("D1 slot2 empty before test", s2_before.get("label", "?") == "", str(s2_before))

# ---- Navigate: Settings -> Applications -> PlaneRadar -> Locations --------
d.cmd("switchApp 6")           # Settings
time.sleep(0.3)
d.tap(100, row_y(5))           # Applications category row (main.cpp kLabels idx 5)
time.sleep(0.3)
d.tap(100, row_y(PLANERADAR_APP_IDX, APP_LIST_ROW_H))   # PlaneRadar row in the app list (=206)
time.sleep(0.3)
d.tap(100, row_y(5))           # Locations row -> opens SlotList
time.sleep(0.3)

# ---- SlotList: tap empty slot 2 -> EditLabel keyboard ----------------------
d.tap(100, row_y(2))           # slot 2 row
time.sleep(0.3)
k = d.cmd("get kb")
report("E1 EditLabel keyboard active, UpperAlpha, maxLen=5, empty",
       k.get("active") and k.get("mode") == 1 and k.get("maxLen") == 5 and k.get("len") == 0,
       str(k))

d.cmd("set kbText TEST")
d.cmd("set kbOk")
time.sleep(0.3)
k = d.cmd("get kb")
report("E2 label submit closes keyboard (-> SourceFork)", k.get("active") is False, str(k))

# ---- SourceFork (slot2, was empty -> hasCurrent=false, y0=38) -------------
# Park the geocode stub BEFORE the postcode submit so enqueueGeocode() is a
# structural no-op (VE-PRL-2) and the parked seq is what LookupPending polls.
stub = d.cmd("set geocode 52.0800 4.3132 TEST DISPLAY NAME")
report("F0 geocode stub parked", bool(stub.get("ok")) and stub.get("parked"), str(stub))

d.tap(137, 58)                 # Lookup button (empty-slot fork layout)
time.sleep(0.3)
p = d.cmd("get pick")
report("F1 Lookup -> Country picker active, opened at current selection",
       p.get("active") and p.get("highlightIdx", -1) >= 0, str(p))

d.cmd("set pick NL")           # select "NL" (default _prLastCountry) as if tapped
time.sleep(0.3)
k = d.cmd("get kb")
report("F2 Country pick -> Postcode keyboard, Full maxLen=10",
       k.get("active") and k.get("mode") == 0 and k.get("maxLen") == 10 and k.get("len") == 0,
       str(k))

d.cmd("set kbText 2513AA")
d.cmd("set kbOk")             # -> LookupPending -> enqueueGeocode() no-ops (parked) -> _tickPrLookup consumes stub
time.sleep(1.0)
k = d.cmd("get kb")
report("F3 Postcode submit closes keyboard (-> LookupPending)", k.get("active") is False, str(k))

time.sleep(1.0)                 # let a couple of SettingsApp ticks run _tickPrLookup()
d.tap(47, 210)                  # Confirm screen: Save
time.sleep(0.3)

r = d.cmd("get prloc")
s2 = loc(r, 2)
report("F4 slot2 saved from geocode stub",
       s2.get("label") == "TEST" and abs(s2.get("lat", 0) - 52.08) < 1e-3 and abs(s2.get("lon", 0) - 4.3132) < 1e-3,
       str(s2))

# ---- Slot 0: Delete must be disabled (renders but never hits) -------------
d.tap(100, row_y(0))           # slot 0 row -> EditLabel prefilled "HOME"
time.sleep(0.3)
d.cmd("set kbOk")             # resubmit "HOME" unchanged -> SourceFork (hasCurrent=true, y0=64)
time.sleep(0.3)
d.tap(137, 188)                 # Delete button position (disabled for slot 0)
time.sleep(0.3)
r = d.cmd("get prloc")
s0 = loc(r, 0)
report("G1 slot0 Delete is a no-op (disabled, not absent)", s0.get("label") == "HOME", str(s0))

d.tap(10, 10)                   # back: SourceFork -> SlotList
time.sleep(0.2)

# ---- Slot 1 (AMS, non-active, non-zero): Delete must work ------------------
d.tap(100, row_y(1))           # slot 1 row -> EditLabel prefilled "AMS"
time.sleep(0.3)
d.cmd("set kbOk")             # resubmit "AMS" unchanged -> SourceFork (hasCurrent=true, y0=64)
time.sleep(0.3)
d.tap(137, 188)                 # Delete button (enabled — Danger style, non-zero non-active filled slot)
time.sleep(0.3)
r = d.cmd("get prloc")
s1 = loc(r, 1)
report("H1 slot1 Delete clears the slot", s1.get("label", "?") == "" and s1.get("lat", 1) == 0.0, str(s1))
report("H2 active slot untouched by deleting a non-active slot", r.get("active") == 0, str(r))

# ---- Error path: -97 GEOCODE_PARSE_FAILED via the generic decoded-error ---
# path (QM check-in 2026-07-14 note 7 — TASK-317 frames only eyeballed -96).
d.tap(100, row_y(3))           # slot 3 row (still empty) -> EditLabel
time.sleep(0.3)
d.cmd("set kbText ERR")
d.cmd("set kbOk")             # -> SourceFork (hasCurrent=false, y0=38)
time.sleep(0.3)
err_stub = d.cmd("set geocode err -97")
report("I0 -97 stub parked", bool(err_stub.get("ok")) and err_stub.get("errorCode") == -97, str(err_stub))

d.tap(137, 58)                  # Lookup (empty-slot layout)
time.sleep(0.3)
d.cmd("set pick NL")           # country picker: select "NL" (session default)
time.sleep(0.3)
d.cmd("set kbText 9999ZZ")
d.cmd("set kbOk")              # postcode submit -> LookupPending -> consumes -97 stub -> LookupError
time.sleep(1.2)

d.tap(204, 210)                 # Error screen: Cancel -> SlotList, nothing persisted
time.sleep(0.3)
r = d.cmd("get prloc")
s3 = loc(r, 3)
report("I1 slot3 untouched after -97 error + Cancel", s3.get("label", "?") == "", str(s3))

d.tap(10, 10)                   # SlotList -> back to PlaneRadar app rows
time.sleep(0.2)
d.cmd("switchApp 0")            # leave Settings, restore normal shell state

d.close()
fails = [r for r in results if not r[1]]
print(f"\n== TASK-321 EDITOR SMOKE: {len(results) - len(fails)}/{len(results)} PASS ==")
sys.exit(1 if fails else 0)
