#!/usr/bin/env python3
"""clock_tap_smoke.py — M-CLOCK-TAP-CYCLE (TASK-346) DUT smoke.

  T_CLK_TAP_01  bottom tap cycles face; x4 wraps back to start
  T_CLK_TAP_02  top tap cycles theme on Nixie and VFD
  T_CLK_TAP_03  top tap on Digital/Flip = consumed no-op (style+themes unchanged)
  T_CLK_TAP_04  changes stay dirty (no save) until app exit, then exactly one save
  T_CLK_TAP_05  full-circle session -> suspend() writes nothing (wear guard)
  T_CLK_TAP_06  debounce: two taps <300ms apart advance once

Needs debug firmware (SERIAL_DEBUG shell). Restores the pre-test
clockStyle/themes (via serial set, which saves immediately) at the end.

Geometry (clockApp.h): CLK_TAP_SPLIT_Y=120 — top zone tap at (137,60),
bottom zone tap at (137,180). Canvas x<275, taskbar x>=275.
"""
import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import serial  # noqa: E402
from screendump import autodetect_port  # noqa: E402

TOP = (137, 60)
BOT = (137, 180)
DEBOUNCE_S = 0.35   # > firmware's 300 ms window

results = []


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


class Dut:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=1)

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

    def tap(self, xy):
        return self.cmd(f"tap {xy[0]} {xy[1]}")

    def style(self):
        return self.cmd("get clockStyle")

    def save_count(self):
        return self.cmd("get settingsSaveCount").get("count", -1)


port = sys.argv[1] if len(sys.argv) > 1 else autodetect_port()
print(f"== opening {port} (DTR reset) ==", flush=True)
d = Dut(port)

# boot wait
deadline = time.monotonic() + 90
r = {}
while time.monotonic() < deadline:
    r = d.style()
    if r.get("ok"):
        break
    time.sleep(2)
report("V0 boot + cmd loop ready", r.get("ok") is True, str(r))

orig = dict(r)   # val/name/nixieTheme/vfdTheme to restore later

d.cmd("switchApp 1")   # AppId::Clock
time.sleep(1.0)

# Put a known baseline: digital, themes 0/0 (serial set saves immediately,
# and resume() re-snapshots, so we start clean/non-dirty).
d.cmd("set clockStyle digital")
d.cmd("set nixieTheme 0")
d.cmd("set vfdTheme 0")
time.sleep(0.5)
r = d.style()
report("V1 baseline digital/0/0, not dirty",
       r.get("val") == 0 and r.get("dirty") is False, str(r))

# ── T_CLK_TAP_01 — bottom tap cycles face, x4 wraps ─────────────────────────
seen = []
for _ in range(4):
    time.sleep(DEBOUNCE_S)
    d.tap(BOT)
    time.sleep(0.6)   # face repaint (nixie tint etc.)
    seen.append(d.style().get("val"))
report("T_CLK_TAP_01 face cycles 1,2,3,0 (wrap)", seen == [1, 2, 3, 0], str(seen))
la = d.cmd("get clockLastAction")
report("T_CLK_TAP_01 lastAction=TAP_FACE", la.get("val") == "TAP_FACE", str(la))

# ── T_CLK_TAP_05 — full circle back to loaded value: no flash write ─────────
r = d.style()
report("T_CLK_TAP_05 full circle -> not dirty", r.get("dirty") is False, str(r))
saves_before = d.save_count()
d.cmd("switchApp 0")   # suspend clock
time.sleep(1.0)
saves_after = d.save_count()
report("T_CLK_TAP_05 suspend after full circle wrote nothing",
       saves_before == saves_after != -1, f"{saves_before} -> {saves_after}")
d.cmd("switchApp 1")
time.sleep(1.0)

# ── T_CLK_TAP_03 — top tap on Digital = consumed no-op ──────────────────────
before = d.style()
time.sleep(DEBOUNCE_S)
d.tap(TOP)
time.sleep(0.3)
after = d.style()
la = d.cmd("get clockLastAction")
report("T_CLK_TAP_03 digital top tap: style+themes unchanged",
       {k: before.get(k) for k in ("val", "nixieTheme", "vfdTheme")} ==
       {k: after.get(k) for k in ("val", "nixieTheme", "vfdTheme")} and
       after.get("dirty") is False, str(after))
report("T_CLK_TAP_03 lastAction=TAP_THEME_NA", la.get("val") == "TAP_THEME_NA", str(la))

# ── T_CLK_TAP_02 — top tap cycles theme on Nixie and VFD ────────────────────
d.cmd("set clockStyle nixie")
time.sleep(0.8)
time.sleep(DEBOUNCE_S)
d.tap(TOP)
time.sleep(0.8)
r = d.style()
report("T_CLK_TAP_02 nixie theme 0->1, dirty",
       r.get("nixieTheme") == 1 and r.get("dirty") is True, str(r))

d.cmd("set clockStyle vfd")   # immediate save; nixieTheme=1 saved with it, dirty resets
time.sleep(0.8)
time.sleep(DEBOUNCE_S)
d.tap(TOP)
time.sleep(0.8)
r = d.style()
la = d.cmd("get clockLastAction")
report("T_CLK_TAP_02 vfd theme 0->1, dirty",
       r.get("vfdTheme") == 1 and r.get("dirty") is True, str(r))
report("T_CLK_TAP_02 lastAction=TAP_THEME", la.get("val") == "TAP_THEME", str(la))

# ── T_CLK_TAP_04 — dirty until exit, then exactly one save ──────────────────
saves_before = d.save_count()
d.cmd("switchApp 0")   # suspend -> flush
time.sleep(1.0)
saves_after = d.save_count()
report("T_CLK_TAP_04 suspend flushed exactly one save",
       saves_after == saves_before + 1, f"{saves_before} -> {saves_after}")
d.cmd("switchApp 1")
time.sleep(0.8)
r = d.style()
report("T_CLK_TAP_04 flushed value survives re-enter, not dirty",
       r.get("vfdTheme") == 1 and r.get("dirty") is False, str(r))

# ── T_CLK_TAP_06 — debounce: two fast taps advance once ─────────────────────
time.sleep(DEBOUNCE_S)
v0 = d.style().get("val")
d.tap(BOT)
d.tap(BOT)   # arrives < 300 ms after the first -> DEBOUNCE
time.sleep(0.8)
r = d.style()
la = d.cmd("get clockLastAction")
report("T_CLK_TAP_06 two fast taps advance face once",
       r.get("val") == (v0 + 1) % 4, f"v0={v0} -> {r.get('val')}")
report("T_CLK_TAP_06 lastAction=DEBOUNCE", la.get("val") == "DEBOUNCE", str(la))

# ── restore pre-test state (serial set saves immediately) ───────────────────
d.cmd(f"set clockStyle {orig.get('val', 0)}")
d.cmd(f"set nixieTheme {orig.get('nixieTheme', 0)}")
d.cmd(f"set vfdTheme {orig.get('vfdTheme', 0)}")
time.sleep(0.5)
r = d.style()
report("Z0 device restored to pre-test style/themes",
       r.get("val") == orig.get("val") and
       r.get("nixieTheme") == orig.get("nixieTheme") and
       r.get("vfdTheme") == orig.get("vfdTheme") and r.get("dirty") is False,
       str(r))
d.cmd("switchApp 0")

d.ser.close()
npass = sum(1 for _, ok, _ in results if ok)
nfail = len(results) - npass
print(f"\n== TASK-346 CLOCK TAP SMOKE: {npass}/{len(results)} PASS ==", flush=True)
sys.exit(1 if nfail else 0)
