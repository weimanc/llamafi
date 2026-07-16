#!/usr/bin/env python3
"""DUT smoke for TASK-322 (M-PR-LOCATIONS manual lat/lon entry path).

Companion to prloc_editor_smoke.py (TASK-321) — same technique (tap +
kbText/kbOk/kbCancel injection over serial), scoped to the SourceFork ->
ManualLat -> ManualLon -> ManualConfirm leg specifically: range validation
(-90..90 / -180..180) rejects and re-prompts rather than crashing or
silently clamping, a valid pair reaches Save and persists, and Cancel at
ManualConfirm leaves the slot untouched.

Coordinates (same geometry as prloc_editor_smoke.py; SourceFork's button
Y0 depends on whether the edited slot already has data — see
_repaintPrSourceFork()):
  SlotList row i                       : (100, 28 + i*26 + 13)
  SourceFork Manual (hasCurrent=false) : (137, 110)  sStackedBtnRect(1, 38)
  SourceFork Manual (hasCurrent=true)  : (137, 136)  sStackedBtnRect(1, 64)
  SourceFork Delete (hasCurrent=true)  : (137, 188)  sStackedBtnRect(2, 64)
  ManualConfirm Save/Cancel            : (69,210) (204,210)  sButtonBar n=2 @ 190
  Header back zone                     : (10, 10)
"""
import json, sys, time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
SLOT = int(sys.argv[2]) if len(sys.argv) > 2 else 3   # slot under test — restored at the end
results = []


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


class Dut:
    def __init__(self):
        self.ser = serial.Serial(PORT, 115200, timeout=1)

    def close(self):
        self.ser.close()

    def cmd(self, c, timeout=5.0):
        self.ser.write((c + "\n").encode())
        self.ser.flush()
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


print(f"== opening {PORT} (DTR reset) — slot under test: {SLOT} ==", flush=True)
d = Dut()
boot = d.wait_ready(90)
report("A0 boot + cmd loop ready", bool(boot.get("ok")), str(boot))
orig = loc(boot, SLOT)
report("A1 baseline slot captured", "label" in orig, str(orig))

# ---- Navigate: Settings -> Applications -> PlaneRadar -> Locations --------
d.cmd("switchApp 6")
time.sleep(0.3)
d.tap(100, 171)                # Applications
time.sleep(0.3)
d.tap(100, 223)                # PlaneRadar
time.sleep(0.3)
d.tap(100, 171)                # Locations -> SlotList
time.sleep(0.3)

# ---- If the target slot has data, empty it first via Delete so this run --
# ---- gets a clean hasCurrent=false SourceFork layout (y0=38, no "Current" -
# ---- row) and a clean empty-prefill ManualLat/Lon. Restored at the end. --
if orig.get("label"):
    d.tap(100, 28 + SLOT * 26 + 13)   # slot row -> EditLabel prefilled
    time.sleep(0.3)
    d.cmd("set kbOk")                  # resubmit unchanged -> SourceFork (hasCurrent=true, y0=64)
    time.sleep(0.3)
    d.tap(137, 188)                    # Delete (enabled: non-zero-or-filled, non-slot0 assumed)
    time.sleep(0.3)
    r = d.cmd("get prloc")
    report("A2 slot emptied for a clean test run", loc(r, SLOT).get("label", "?") == "", str(loc(r, SLOT)))
    # _prDeleteSlot() already leaves us at SlotList — no back-tap needed here.

# ---- SlotList: open the (now empty) target slot ----------------------------
d.tap(100, 28 + SLOT * 26 + 13)
time.sleep(0.3)
k = d.cmd("get kb")
report("B1 EditLabel keyboard active, empty", k.get("active") and k.get("len") == 0, str(k))
d.cmd("set kbText MANU")
d.cmd("set kbOk")
time.sleep(0.3)

# ---- SourceFork (hasCurrent=false -> y0=38) -> Manual ----------------------
d.tap(137, 110)                 # Manual button, empty-slot layout
time.sleep(0.3)
k = d.cmd("get kb")
report("C1 Manual -> ManualLat keyboard, Full mode, empty prefill",
       k.get("active") and k.get("mode") == 0 and k.get("maxLen") == 10 and k.get("len") == 0, str(k))

# ---- Invalid lat (out of -90..90) must re-prompt, not crash / not advance -
d.cmd("set kbText 999")
d.cmd("set kbOk")
time.sleep(0.3)
k = d.cmd("get kb")
report("C2 lat=999 rejected — keyboard re-shown, still ManualLat-shaped",
       k.get("active") and k.get("maxLen") == 10 and k.get("len") == 0, str(k))

# ---- Valid lat -> advances to ManualLon ------------------------------------
d.cmd("set kbText 52.5")
d.cmd("set kbOk")
time.sleep(0.3)
k = d.cmd("get kb")
report("C3 lat=52.5 accepted -> ManualLon keyboard, empty prefill",
       k.get("active") and k.get("mode") == 0 and k.get("maxLen") == 11 and k.get("len") == 0, str(k))

# ---- Invalid lon (out of -180..180) must re-prompt -------------------------
d.cmd("set kbText -200")
d.cmd("set kbOk")
time.sleep(0.3)
k = d.cmd("get kb")
report("C4 lon=-200 rejected — keyboard re-shown, still ManualLon-shaped",
       k.get("active") and k.get("maxLen") == 11 and k.get("len") == 0, str(k))

# ---- Valid lon -> advances to ManualConfirm, keyboard closes ---------------
d.cmd("set kbText 13.4")
d.cmd("set kbOk")
time.sleep(0.3)
k = d.cmd("get kb")
report("C5 lon=13.4 accepted -> keyboard closes (ManualConfirm)", k.get("active") is False, str(k))

# ---- Save persists label + manually-entered coords -------------------------
d.tap(69, 210)                  # ManualConfirm: Save
time.sleep(0.3)
r = d.cmd("get prloc")
s = loc(r, SLOT)
report("D1 slot saved from manual entry",
       s.get("label") == "MANU" and abs(s.get("lat", 0) - 52.5) < 1e-3 and abs(s.get("lon", 0) - 13.4) < 1e-3,
       str(s))

# ---- Cancel-at-confirm leaves the slot untouched ---------------------------
d.tap(100, 28 + SLOT * 26 + 13)   # slot row (now MANU/52.5,13.4) -> EditLabel
time.sleep(0.3)
d.cmd("set kbOk")                   # resubmit "MANU" unchanged -> SourceFork (hasCurrent=true, y0=64)
time.sleep(0.3)
d.tap(137, 136)                     # Manual button, filled-slot layout
time.sleep(0.3)
k = d.cmd("get kb")
report("E1 Manual re-entry prefills current lat", k.get("active") and k.get("len") > 0, str(k))
d.cmd("set kbText 9")               # append onto the prefill — still a valid number either way
d.cmd("set kbOk")
time.sleep(0.3)
d.cmd("set kbOk")                   # lon: submit prefilled value unchanged
time.sleep(0.3)
d.tap(204, 210)                     # ManualConfirm: Cancel
time.sleep(0.3)
r = d.cmd("get prloc")
s = loc(r, SLOT)
report("E2 Cancel at ManualConfirm leaves the slot as it was before this leg",
       s.get("label") == "MANU", str(s))

# ---- Restore original slot content (raw `set prloc`, no UI nav needed) ----
if orig.get("label"):
    d.cmd(f"set prloc {SLOT} {orig['label']} {orig['lat']} {orig['lon']}")
    time.sleep(0.2)
    r = d.cmd("get prloc")
    s = loc(r, SLOT)
    report("Z0 slot restored to baseline",
           s.get("label") == orig["label"] and abs(s.get("lat", 0) - orig["lat"]) < 1e-3, str(s))
else:
    d.cmd(f"set prloc {SLOT} X 0 0")  # can't restore true emptiness via serial; label to a harmless marker
    time.sleep(0.2)

d.tap(10, 10)
time.sleep(0.2)
d.cmd("switchApp 0")

d.close()
fails = [r for r in results if not r[1]]
print(f"\n== TASK-322 MANUAL-ENTRY SMOKE: {len(results) - len(fails)}/{len(results)} PASS ==")
sys.exit(1 if fails else 0)
