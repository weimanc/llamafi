#!/usr/bin/env python3
"""DUT smoke for TASK-324 (M-PR-LOCATIONS VE suite gate) — covers the T_PRL
legs NOT already DUT-proven by the TASK-319/320/321/322/325 smokes:

  T_PRL_02  strip tap switches location (active index, state reset, epoch bump)
  T_PRL_05a same-slot strip tap is a no-op (no state-reset flicker)
  T_PRL_05b deleting the ACTIVE slot falls back to slot 0
  T_PRL_03  -96 GEOCODE_NO_MATCH error path (companion to the -97 leg already
            proven in prloc_editor_smoke.py)
  T_PRL_08  cancel mid-lookup leaves clean state; a late real-network result
            arriving afterward is not acted on (UI has moved on — see caveat
            in the script docstring below re: what this does/doesn't prove)
  T_PRL_09  rapid double-switch (best-effort empirical epoch-race exercise)

Already DUT-proven elsewhere — cited, not re-run, in the TASK-324 write-up:
  T_PRL_01a prloc_editor_smoke.py (2026-07-15)
  T_PRL_01b prloc_smoke.py Phase B (2026-07-14, TASK-320 close-out)
  T_PRL_04  prloc_smoke.py Phase A (2026-07-14, TASK-319 close-out)
  T_PRL_06  prloc_manual_smoke.py (2026-07-16)
  T_PRL_10  prloc_editor_smoke.py G1 (2026-07-15)

Not run here (see TASK-324 tasks.md write-up for disposition):
  T_PRL_07 flash-fs-wipe leg (destructive — needs explicit human go-ahead)
  T_PRL_11 Spotify-coexistence (blocked — TASK-243 external Premium lapse)

T_PRL_08 caveat: `debugInjectGeocode()` self-stamps the injected seq to
whatever is currently pending, by design (VE-PRL-2) — so a genuinely
MISMATCHED seq can't be manufactured through the debug surface. This test
therefore does NOT park a stub; it lets a real enqueueGeocode() fire, cancels
before it can plausibly have returned, and proves the UI left LookupPending
cleanly. The seq-mismatch discard itself (`if (r.seq != _prGeoSeq) return;`)
is a code-review finding, not independently re-provable live without a
seq-injection hook that doesn't exist.

Uses whatever 4 slots are currently populated on the DUT (does not assume
labels) — restores every slot it touches to its pre-test value at the end.
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

    def wait_field(self, get_cmd, field, value, budget=90, poll=1.5):
        deadline = time.monotonic() + budget
        last = {}
        while time.monotonic() < deadline:
            last = self.cmd(get_cmd)
            if last.get(field) == value:
                return last
            time.sleep(poll)
        return last


def loc(r, i):
    locs = r.get("locs") or []
    return locs[i] if i < len(locs) else {}


# PlaneRadar strip geometry (planeRadarApp.h): label column x=257,
# rows y = 68/90/112/134/156/178/200 for slots 0..6 (Q1 amendment
# 2026-07-18: 7 slots @ 22 px pitch, AGE/ERR moved to strip bottom).
STRIP_X = 257
STRIP_ROW_Y = [68, 90, 112, 134, 156, 178, 200]

print(f"== opening {PORT} (DTR reset) ==", flush=True)
d = Dut()
boot = d.wait_ready(90)
report("V0 boot + cmd loop ready", bool(boot.get("ok")), str(boot))
orig_active = boot.get("active", 0)
orig_locs = boot.get("locs") or []
report("V1 all 4 slots filled (test needs live labels, not -- empty --)",
       all(l.get("label") for l in orig_locs), str(orig_locs))

filled = [i for i, l in enumerate(orig_locs) if l.get("label")]
target = next((i for i in filled if i != orig_active), None)
report("V2 found a non-active filled slot to switch to", target is not None, f"target={target}")

# =========================================================================
# T_PRL_02 — strip tap switches location
# =========================================================================
d.cmd("switchApp 9")   # AppId::PlaneRadar (TASK-347: Settings moved before it, shifting 10→9)
time.sleep(0.5)

d.tap(STRIP_X, STRIP_ROW_Y[target])
time.sleep(0.3)
r = d.cmd("get prloc")
la = d.cmd("get prLastAction")
report("T_PRL_02a strip tap switched active slot",
       r.get("active") == target, f"active={r.get('active')} target={target}")
report("T_PRL_02b prLastAction records the strip hit",
       la.get("val") == f"STRIP_LOC_{target}", str(la))

ae = d.cmd("get activeError")
report("T_PRL_02c switch resets connecting state (DEV-3 reset)", ae.get("connecting") is True, str(ae))

# Let it settle (connecting -> false) before the no-op check, so a
# regression that DOES re-reset on a same-slot tap is actually visible.
settled = d.wait_field("get activeError", "connecting", False, budget=90)
report("T_PRL_02d fetch settles (connecting -> false) before no-op check", settled.get("connecting") is False, str(settled))

# =========================================================================
# T_PRL_05a — same-slot strip tap is a no-op (no flicker/reset)
# =========================================================================
d.tap(STRIP_X, STRIP_ROW_Y[target])   # tap the SAME slot again
time.sleep(0.5)
ae2 = d.cmd("get activeError")
r2 = d.cmd("get prloc")
report("T_PRL_05a same-slot tap: active index unchanged", r2.get("active") == target, str(r2))
report("T_PRL_05a same-slot tap: no state reset (connecting stays false)",
       ae2.get("connecting") is False, str(ae2))

# =========================================================================
# T_PRL_09 — rapid double-switch (best-effort empirical epoch-race exercise)
# NOTE: back-to-back *tap* injection can't do this — a tap while
# hasPendingAsync() is true sets g_shellBusy, and cmdTap's very first check
# silently drops (skipped:true) any tap that arrives while g_shellBusy is
# set (discovered by this script: an earlier tap-based version of this test
# always landed on the FIRST slot, never the second, because tap #2 was
# dropped before it ever reached PlaneRadarApp::handleInput()). That's
# correct product behaviour (the shell won't let interactive taps race a
# fetch), but it means this leg has to go through `set prloc active <i>`
# (main.cpp's serial path, which calls _setActiveLoc() directly with no
# g_shellBusy gate) to actually exercise the epoch race.
# =========================================================================
others = [i for i in filled if i != target]
if len(others) >= 2:
    a, b = others[0], others[1]
    d.cmd(f"set prloc active {a}")
    d.cmd(f"set prloc active {b}")   # no sleep — race the in-flight fetch for `a`
    time.sleep(0.3)
    r = d.cmd("get prloc")
    report("T_PRL_09 rapid double-switch settles on the LAST-set slot, no crash",
           r.get("active") == b and r.get("ok"), str(r))
    settled = d.wait_field("get activeError", "connecting", False, budget=90)
    ac = d.cmd("get prAircraftCount")
    report("T_PRL_09 fetch for the final slot completes cleanly after the race",
           settled.get("connecting") is False and ac.get("ok"), f"{settled} count={ac}")
else:
    report("T_PRL_09 rapid double-switch", False, "need >=2 other filled slots besides target — skipped, not enough data")

# =========================================================================
# T_PRL_05b — deleting the ACTIVE slot falls back to slot 0
# =========================================================================
# Make a non-zero slot active first (serial path, guarded on currentAppId
# like the strip-tap path — same _setActiveLoc() primitive either way).
victim = next((i for i in filled if i != 0), None)
report("V3 found a non-zero filled slot to delete-while-active", victim is not None, f"victim={victim}")
victim_backup = dict(orig_locs[victim]) if victim is not None else {}

if victim is not None:
    d.cmd(f"set prloc active {victim}")
    time.sleep(0.3)
    r = d.cmd("get prloc")
    report("T_PRL_05b setup: victim slot is active", r.get("active") == victim, str(r))

    d.cmd("switchApp 10")           # Settings (TASK-347: moved from 6 to directly before WebRadio)
    time.sleep(0.3)
    d.tap(100, row_y(5))            # Applications (main.cpp kLabels idx 5)
    time.sleep(0.3)
    d.tap(100, row_y(PLANERADAR_APP_IDX, APP_LIST_ROW_H))   # PlaneRadar (=206; was 223 in the 9-app/23px era)
    time.sleep(0.3)
    d.tap(100, row_y(5))            # Locations
    time.sleep(0.3)
    d.tap(100, row_y(victim))       # victim's slot row -> EditLabel prefilled
    time.sleep(0.3)
    d.cmd("set kbOk")                # resubmit unchanged -> SourceFork (hasCurrent=true, y0=64)
    time.sleep(0.3)
    d.tap(137, 188)                  # Delete (enabled: non-zero, hasCurrent)
    time.sleep(0.3)
    r = d.cmd("get prloc")
    s = loc(r, victim)
    report("T_PRL_05b delete-active-slot falls back to slot 0",
           r.get("active") == 0 and s.get("label", "?") == "", str(r))
    s0 = loc(r, 0)
    report("T_PRL_05b prLat/prLon mirror follows the fallback (slot 0 coords)",
           abs(s0.get("lat", 999) - orig_locs[0]["lat"]) < 1e-3, str(s0))

    d.tap(10, 10); time.sleep(0.2)   # SlotList -> app rows
    d.tap(10, 10); time.sleep(0.2)   # app rows -> app list
    d.cmd("switchApp 0")

# =========================================================================
# T_PRL_03 — -96 GEOCODE_NO_MATCH error path (companion to the -97 leg
# already proven in prloc_editor_smoke.py)
# =========================================================================
scratch = next((i for i in filled if i != 0 and i != victim), None)
report("V4 found a scratch slot for the -96 leg (untouched by Save)", scratch is not None, f"scratch={scratch}")

if scratch is not None:
    d.cmd("switchApp 10")           # Settings (TASK-347: moved from 6 to directly before WebRadio)
    time.sleep(0.3)
    d.tap(100, row_y(5))            # Applications
    time.sleep(0.3)
    d.tap(100, row_y(PLANERADAR_APP_IDX, APP_LIST_ROW_H))   # PlaneRadar
    time.sleep(0.3)
    d.tap(100, row_y(5))            # Locations
    time.sleep(0.3)
    d.tap(100, row_y(scratch))      # scratch slot row -> EditLabel prefilled
    time.sleep(0.3)
    d.cmd("set kbOk")                     # resubmit unchanged -> SourceFork (hasCurrent=true, y0=64)
    time.sleep(0.3)
    d.tap(137, 84)                        # Lookup button (hasCurrent=true layout)
    time.sleep(0.3)
    d.cmd("set kbOk")                     # country: prefilled default, submit as-is
    time.sleep(0.3)
    stub96 = d.cmd("set geocode err -96")
    report("T_PRL_03 -96 stub parked", stub96.get("ok") and stub96.get("errorCode") == -96, str(stub96))
    d.cmd("set kbText 0000ZZ")
    d.cmd("set kbOk")                     # postcode submit -> LookupPending -> consumes -96 -> LookupError
    time.sleep(1.2)
    k = d.cmd("get kb")
    report("T_PRL_03 -96 error path: keyboard stays closed (LookupError, not a keyboard step)",
           k.get("active") is False, str(k))
    d.tap(204, 210)                       # Error screen: Cancel -> SlotList, nothing persisted
    time.sleep(0.3)
    r = d.cmd("get prloc")
    s = loc(r, scratch)
    report("T_PRL_03 scratch slot untouched after -96 error + Cancel",
           s.get("label") == orig_locs[scratch]["label"] and
           abs(s.get("lat", 0) - orig_locs[scratch]["lat"]) < 1e-3, str(s))

# =========================================================================
# T_PRL_08 — cancel mid-lookup leaves clean state (real fetch, not a stub —
# see docstring caveat on what this does/doesn't prove)
# =========================================================================
if scratch is not None:
    d.tap(100, row_y(scratch))      # scratch slot row -> EditLabel (still in SlotList from T_PRL_03)
    time.sleep(0.3)
    d.cmd("set kbOk")
    time.sleep(0.3)
    d.tap(137, 84)                        # Lookup
    time.sleep(0.3)
    d.cmd("set kbOk")                     # country default
    time.sleep(0.3)
    d.cmd("set kbText 2513AA")
    d.cmd("set kbOk")                     # postcode submit -> REAL enqueueGeocode(), no stub parked
    # Cancel immediately — races the real network fetch.
    d.tap(137, 210)                       # LookupPending: Cancel (sButtonBar n=1 @190, full-width, center x=137)
    time.sleep(0.3)
    r = d.cmd("get prloc")
    s = loc(r, scratch)
    report("T_PRL_08 cancel-mid-lookup: nothing persisted, scratch slot untouched",
           s.get("label") == orig_locs[scratch]["label"], str(s))
    # Give the real fetch time to land in the background, then confirm the
    # late result sits inert (peek, non-consuming) and didn't corrupt state.
    time.sleep(5.0)
    g = d.cmd("get geocode")
    r2 = d.cmd("get prloc")
    s2 = loc(r2, scratch)
    report("T_PRL_08 late real-network result (if any) left the slot alone",
           s2.get("label") == orig_locs[scratch]["label"], f"geocode_peek={g} slot={s2}")

    d.tap(10, 10); time.sleep(0.2)
    d.tap(10, 10); time.sleep(0.2)
    d.cmd("switchApp 0")

# =========================================================================
# Restore — every slot this script touched, and the original active index.
# =========================================================================
if victim is not None and victim_backup:
    d.cmd(f"set prloc {victim} {victim_backup['label']} {victim_backup['lat']} {victim_backup['lon']}")
    time.sleep(0.2)
d.cmd(f"set prloc active {orig_active}")
time.sleep(0.3)
final = d.cmd("get prloc")
report("Z0 device restored to pre-test slot contents + active index",
       final.get("active") == orig_active and
       all(loc(final, i).get("label") == orig_locs[i].get("label") for i in range(4)),
       str(final))

d.close()
fails = [r for r in results if not r[1]]
print(f"\n== TASK-324 VE SMOKE: {len(results) - len(fails)}/{len(results)} PASS ==")
sys.exit(1 if fails else 0)
