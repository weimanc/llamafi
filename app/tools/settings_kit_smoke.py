#!/usr/bin/env python3
"""DUT smoke for TASK-327 (Settings style pass — widget-kit migration).

Companion to prloc_manual_smoke.py (same tap-injection technique), scoped
to the two migrated button sites that ARE serial-reachable:

  - LED picker OFF/ON/SAVE (now sButtonBar 3-across at y=32, S_BTN_H=40,
    buttons centred at x=47/137/227, y=52; SV square moved to y=78)
  - Time city-picker scrollbar step arrows (SButton at the scrollbar's own
    18x20 rects: up (266,38), down (266,230))

NOT covered here (no serial path to the precondition):
  - wifiSection Result Retry/Cancel — needs a failed connect
  - calibrationFlow Review Accept/Retry/Cancel — needs 4 raw XPT2046 taps
  Both stay on the manual/eyeball checklist (BP-048).

There is no debug `get` for LedView/cityOffset, so assertions are
indirect: back-tap semantics distinguish picker vs list (back from a
sub-view keeps settingsSection, back from the section root pops it to
-1), and every tap is followed by a `get settingsSection` liveness check —
a null-deref/WDT reboot shows up as a dead command loop.

Side effect: the LED leg cycles Mode and presses ON/SAVE, so it leaves
ledMode = Static (persisted) and then parks it at Off (= firmware
default) by cycling the Mode row. Colour (hue/sat/val) is saved
unchanged.
"""
import json, sys, time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
results = []

SETTINGS_SLOT = 6
SPOTIFY_SLOT = 0

BACK = (30, 14)
ROW = lambda i: (137, 28 + i * 26 + 13)          # category/section list rows
LED_BTN_Y = 52                                    # sButtonBar @ kBarY=32, mid
LED_OFF, LED_ON, LED_SAVE = (47, LED_BTN_Y), (137, LED_BTN_Y), (227, LED_BTN_Y)
CITY_ROW = (137, 63)                              # after 22px sub-header
ARROW_UP, ARROW_DN = (266, 38), (266, 230)


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
            r = self.cmd("get appId", 3.0)
            if r.get("ok"):
                return r
            time.sleep(2)
        return {}

    def tap(self, x, y):
        r = self.cmd(f"tap {x} {y}")
        time.sleep(0.15)
        return r

    def section(self):
        r = self.cmd("get settingsSection")
        return r.get("section") if r.get("ok") else None


d = Dut()
print(f"== opening {PORT} (DTR reset) ==", flush=True)
boot = d.wait_ready(90)
report("A0 boot + cmd loop ready", bool(boot.get("ok")), str(boot))

d.cmd(f"switchApp {SETTINGS_SLOT}")
time.sleep(0.3)
r = d.cmd("get appId")
report("A1 in Settings", r.get("name") == "Settings", str(r))

# ── LED picker leg ──────────────────────────────────────────────────────────
d.tap(*ROW(4))                                    # LED section
report("B0 LED section entered", d.section() == 4)

# Probe until Colour row opens the picker (mode must be Static|Pulse).
# Detection: back-tap from the picker returns to the LED *list* (section
# stays 4); back-tap from the list pops the section (-1).
picker_reachable = False
for attempt in range(5):
    d.tap(*ROW(1))                                # Colour row (list rows are
    d.tap(*BACK)                                  # at content y, no sub-hdr)
    if d.section() == 4:
        picker_reachable = True
        break
    # we popped to the category list — re-enter LED, cycle Mode once
    d.tap(*ROW(4))
    d.tap(*ROW(0))
report("B1 picker reachable (mode cycled to Static/Pulse)", picker_reachable,
       f"attempts={attempt + 1}")

if picker_reachable:
    d.tap(*ROW(1))                                # re-open picker
    d.tap(*LED_OFF)
    ok_off = d.section() == 4
    d.tap(*LED_ON)                                # Off -> Static
    ok_on = d.section() == 4
    d.tap(*LED_SAVE)                              # flash() + saveSettings()
    ok_save = d.section() == 4
    report("B2 OFF hit, loop alive", ok_off)
    report("B3 ON hit, loop alive", ok_on)
    report("B4 SAVE hit (kit flash + persist), loop alive", ok_save)
    d.tap(*BACK)                                  # picker -> list
    report("B5 back-tap picker->list", d.section() == 4)
    # park ledMode at Off (firmware default): Static -> Pulse -> Clock -> Off
    for _ in range(3):
        d.tap(*ROW(0))
    d.tap(*BACK)                                  # list -> category
    report("B6 back-tap list->category", d.section() == -1)

# ── Time city-picker arrow leg ──────────────────────────────────────────────
d.tap(*ROW(1))                                    # Time & Location
report("C0 Time section entered", d.section() == 1)
d.tap(*CITY_ROW)                                  # -> CityPicker
d.tap(*ARROW_DN)
ok_dn = d.section() == 1
d.tap(*ARROW_DN)
d.tap(*ARROW_UP)
ok_up = d.section() == 1
report("C1 down-arrow taps, loop alive", ok_dn)
report("C2 up-arrow tap, loop alive", ok_up)
d.tap(*BACK)                                      # picker -> Main
report("C3 back-tap picker->main", d.section() == 1)
d.tap(*BACK)                                      # Main -> category
report("C4 back-tap main->category", d.section() == -1)

d.cmd(f"switchApp {SPOTIFY_SLOT}")
d.close()

npass = sum(1 for _, ok, _ in results if ok)
print(f"\n== {npass}/{len(results)} PASS ==", flush=True)
sys.exit(0 if npass == len(results) else 1)
