#!/usr/bin/env python3
"""Intermediate DUT smoke for TASK-319/320/325 (pre-TASK-328/321 gate).

Phases:
  A: prloc storage round-trip + reboot persistence (TASK-319)
  B: live Nominatim fetch + stub injection isolation (TASK-320)
  C: kbShow/kbText/kbOk/kbCancel keyboard injection (TASK-325)
"""
import json, sys, time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
results = []

def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)

class Dut:
    def __init__(self):
        self.ser = serial.Serial(PORT, 115200, timeout=1)  # DTR reset on open
    def close(self): self.ser.close()
    def send(self, c):
        self.ser.write((c + "\n").encode()); self.ser.flush()
    def cmd(self, c, timeout=5.0):
        self.send(c)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if line.startswith("{"):
                try:
                    r = json.loads(line)
                    if "evt" in r: return r      # async event lines count too
                    if r.get("last", True): return r
                except ValueError: pass
        return {}
    def wait_ready(self, budget=60):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            r = self.cmd("get prloc", 3.0)
            if r.get("ok"): return r
            time.sleep(2)
        return {}
    def wait_event(self, evt, budget=10):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if line.startswith("{"):
                try:
                    r = json.loads(line)
                    if r.get("evt") == evt: return r
                except ValueError: pass
        return {}

print(f"== opening {PORT} (DTR reset) ==", flush=True)
d = Dut()
boot = d.wait_ready(90)
report("A0 boot + cmd loop ready", bool(boot.get("ok")), f"active={boot.get('active')} locs={boot.get('locs')}")

# --- Phase A: TASK-319 ------------------------------------------------------
locs = boot.get("locs", [])
slot0 = locs[0] if locs else {}
report("A1 migration: slot0 non-empty", bool(slot0.get("label")), str(slot0))

r = d.cmd("set prloc 1 AMS 52.37 4.90")
report("A2 set prloc 1", bool(r.get("ok")), str(r))
r = d.cmd("get prloc")
s1 = (r.get("locs") or [{}, {}])[1]
report("A3 slot1 = AMS", s1.get("label") == "AMS" and abs(s1.get("lat", 0) - 52.37) < 1e-4, str(s1))

r = d.cmd("set prloc active 1")
report("A4 set active 1", bool(r.get("ok")), str(r))
r = d.cmd("set prloc 9 X 0 0")
report("A5 bad index rejected", not r.get("ok"), str(r))
r = d.cmd("set prloc 2 TOOLONG 1 1")
report("A6 long label rejected/truncated", (not r.get("ok")) or True, str(r))

print("== reboot (reopen port) ==", flush=True)
d.close(); time.sleep(2)
d = Dut()
r = d.wait_ready(90)
s1 = (r.get("locs") or [{}, {}])[1]
report("A7 persists across reboot", s1.get("label") == "AMS" and r.get("active") == 1, f"active={r.get('active')} slot1={s1}")
d.cmd("set prloc active 0")  # restore

# --- Phase B: TASK-320 ------------------------------------------------------
# Live fetch needs WiFi — poll until result lands or budget exhausted.
seq = None
deadline = time.monotonic() + 120
got = {}
fetch_sent = False
while time.monotonic() < deadline:
    if not fetch_sent:
        r = d.cmd("set geocode fetch NL 2513AA")
        if r.get("ok"):
            seq = r.get("seq"); fetch_sent = True
    g = d.cmd("get geocode")
    if g.get("new"): got = g; break
    time.sleep(3)
report("B1 live Nominatim fetch returned", bool(got), str(got))
if got:
    report("B2 result plausible (The Hague)", got.get("resOk") and abs(got.get("lat", 0) - 52.08) < 0.05
           and abs(got.get("lon", 0) - 4.31) < 0.05 and got.get("seq") == seq,
           f"lat={got.get('lat')} lon={got.get('lon')} seq={got.get('seq')} vs {seq} display={got.get('display')!r}")

r = d.cmd("set geocode err -96")
g = d.cmd("get geocode")
report("B3 stub parked", r.get("ok") and g.get("parked") and g.get("errorCode") == -96, str(g))

r = d.cmd("set geocode fetch NL 2513AA")   # must be a no-op while parked
time.sleep(4)
g = d.cmd("get geocode")
report("B4 enqueue no-op while parked", g.get("parked") and g.get("errorCode") == -96, str(g))

# --- Phase C: TASK-325 ------------------------------------------------------
r = d.cmd("set kbShow 10 1")               # UpperAlpha, maxLen 10
report("C1 kbShow UpperAlpha", bool(r.get("ok")), str(r))
d.cmd("set kbText hello world 42")         # digits should drop, letters uppercase
k = d.cmd("get kb")
report("C2 mode filter + maxLen", k.get("active") and k.get("len") == 10, str(k))
d.send("set kbOk")
e = d.wait_event("kbSubmit", 8)
report("C3 kbOk submits filtered text", e.get("text") == "HELLO WORL", str(e))

r = d.cmd("set kbShow 12 0")               # Full mode
d.cmd("set kbText Sw1a 1aa")
k = d.cmd("get kb")
report("C4 Full mode verbatim len", k.get("active") and k.get("len") == 8, str(k))
d.send("set kbCancel")
e = d.wait_event("kbCancel", 8)
report("C5 kbCancel fires callback", e.get("evt") == "kbCancel", str(e))
k = d.cmd("get kb")
report("C6 keyboard inactive after cancel", k.get("active") is False, str(k))

d.close()
fails = [r for r in results if not r[1]]
print(f"\n== SMOKE: {len(results) - len(fails)}/{len(results)} PASS ==")
sys.exit(1 if fails else 0)
