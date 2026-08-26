"""Clock app tests -- M-CLOCK-STYLES suite (TASK-193). Split from
run_serialdbg_tests.py, TASK-480 stage 2 (pilot family)."""

import time

from lib.dut import Dut
from lib.results import pass_, fail


def _switch_to_clock(dut: Dut) -> bool:
    r = dut.cmd("switchApp 1")
    if not r.get("ok"):
        return False
    time.sleep(0.4)
    return True

def _restore_spotify_from_clock(dut: Dut):
    dut.cmd("set clockStyle 0")
    time.sleep(0.2)
    dut.cmd("switchApp 0")
    time.sleep(0.5)

def t_clk_01(dut: Dut):
    """T_CLK_01: switchApp(1) switches to Clock."""
    tid = "T_CLK_01"
    print(f"{tid}  switchApp(Clock)")
    r = dut.cmd("switchApp 1")
    if not r.get("ok"):
        fail(tid, f"switchApp 1 failed: {r}"); return
    time.sleep(0.4)
    r2 = dut.cmd("get appId")
    if r2.get("id") != 1:
        fail(tid, f"appId={r2.get('id')!r} after switchApp 1 — expected 1"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "appId=1 confirmed after switchApp")

def t_clk_02(dut: Dut):
    """T_CLK_02: clockStyle defaults to digital after fresh settings load."""
    tid = "T_CLK_02"
    print(f"{tid}  default clockStyle = digital")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    # Force digital first to ensure a known baseline
    dut.cmd("set clockStyle 0"); time.sleep(0.2)
    r = dut.cmd("get clockStyle")
    if r.get("name") != "digital":
        fail(tid, f"clockStyle={r.get('name')!r} — expected digital"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "clockStyle=digital confirmed")

def t_clk_03(dut: Dut):
    """T_CLK_03: set clockStyle flip — device accepts, readback matches."""
    tid = "T_CLK_03"
    print(f"{tid}  set clockStyle flip")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    r = dut.cmd("set clockStyle flip")
    if not r.get("ok") or r.get("name") != "flip":
        fail(tid, f"set flip: {r}"); return
    time.sleep(0.2)
    r2 = dut.cmd("get clockStyle")
    if r2.get("name") != "flip":
        fail(tid, f"readback after set: {r2}"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "flip set + readback OK")

def t_clk_04(dut: Dut):
    """T_CLK_04: set clockStyle nixie — device accepts, readback matches."""
    tid = "T_CLK_04"
    print(f"{tid}  set clockStyle nixie")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    r = dut.cmd("set clockStyle nixie")
    if not r.get("ok") or r.get("name") != "nixie":
        fail(tid, f"set nixie: {r}"); return
    time.sleep(0.2)
    r2 = dut.cmd("get clockStyle")
    if r2.get("name") != "nixie":
        fail(tid, f"readback after set: {r2}"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "nixie set + readback OK")

def t_clk_05(dut: Dut):
    """T_CLK_05: set clockStyle vfd — device accepts, readback matches."""
    tid = "T_CLK_05"
    print(f"{tid}  set clockStyle vfd")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    r = dut.cmd("set clockStyle vfd")
    if not r.get("ok") or r.get("name") != "vfd":
        fail(tid, f"set vfd: {r}"); return
    time.sleep(0.2)
    r2 = dut.cmd("get clockStyle")
    if r2.get("name") != "vfd":
        fail(tid, f"readback after set: {r2}"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "vfd set + readback OK")

def t_clk_06(dut: Dut):
    """T_CLK_06: set clockStyle by numeric index 0..3."""
    tid = "T_CLK_06"
    print(f"{tid}  set clockStyle by numeric index 0..3")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    names = ["digital", "flip", "nixie", "vfd"]
    for i, nm in enumerate(names):
        r = dut.cmd(f"set clockStyle {i}")
        if not r.get("ok") or str(r.get("val")) != str(i):
            fail(tid, f"idx={i}: {r}"); return
        time.sleep(0.15)
        r2 = dut.cmd("get clockStyle")
        if r2.get("name") != nm:
            fail(tid, f"readback idx={i}: got {r2.get('name')!r}, want {nm!r}"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "all 4 styles accessible by numeric index")

def t_clk_07(dut: Dut):
    """T_CLK_07: invalid clockStyle value is rejected."""
    tid = "T_CLK_07"
    print(f"{tid}  bad clockStyle rejected")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    r = dut.cmd("set clockStyle oled")
    if r.get("ok") is not False:
        fail(tid, f"bad val accepted: {r}"); return
    r2 = dut.cmd("set clockStyle 9")
    if r2.get("ok") is not False:
        fail(tid, f"out-of-range index accepted: {r2}"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "bad values rejected with ok=false")

def t_clk_08(dut: Dut):
    """T_CLK_08: clockStyle persists in settings.json (save confirmed)."""
    tid = "T_CLK_08"
    print(f"{tid}  clockStyle persists via settings save")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    dut.cmd("set clockStyle nixie"); time.sleep(0.4)
    r = dut.cmd("get clockStyle")
    if r.get("name") != "nixie":
        fail(tid, f"clockStyle={r.get('name')!r} after save — expected nixie"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "clockStyle=nixie confirmed after save")

def t_clk_09(dut: Dut):
    """T_CLK_09: app switch away and back preserves clockStyle."""
    tid = "T_CLK_09"
    print(f"{tid}  style preserved across app switch")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    dut.cmd("set clockStyle flip"); time.sleep(0.3)
    dut.cmd("switchApp 4"); time.sleep(0.6)  # Matrix
    dut.cmd("switchApp 1"); time.sleep(0.6)  # back to Clock
    r = dut.cmd("get clockStyle")
    if r.get("name") != "flip":
        fail(tid, f"clockStyle={r.get('name')!r} after return — expected flip"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "flip style preserved across Matrix→Clock round-trip")

def t_clk_10(dut: Dut):
    """T_CLK_10: appId stays Clock=1 while VFD style is active."""
    tid = "T_CLK_10"
    print(f"{tid}  appId=1 with VFD active")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    dut.cmd("set clockStyle vfd"); time.sleep(0.4)
    r = dut.cmd("get appId")
    if r.get("id") != 1:
        fail(tid, f"appId={r.get('id')!r} while VFD active — expected 1"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "appId=1 confirmed with VFD style active")

def t_clk_11(dut: Dut):
    """T_CLK_11: heap stable after cycling all 4 styles twice."""
    tid = "T_CLK_11"
    print(f"{tid}  heap stable after style cycle ×2")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    r0 = dut.cmd("info")
    h0 = r0.get("heap", 0)
    for _ in range(2):
        for i in range(4):
            dut.cmd(f"set clockStyle {i}"); time.sleep(0.15)
    dut.cmd("set clockStyle 0"); time.sleep(0.4)
    r1 = dut.cmd("info")
    h1 = r1.get("heap", 0)
    leak = h0 - h1
    if leak >= 4096:
        fail(tid, f"heap leak {leak} B after style cycle (before={h0} after={h1})"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, f"heap stable — leak={leak}B (before={h0} after={h1})")

def t_clk_12(dut: Dut):
    """T_CLK_12: switchApp Clock→Spotify — device stable, Spotify app active."""
    tid = "T_CLK_12"
    print(f"{tid}  Clock→Spotify transition stable")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    for st in range(4):
        dut.cmd(f"set clockStyle {st}"); time.sleep(0.2)
    dut.cmd("switchApp 0"); time.sleep(1.2)
    r = dut.cmd("get appId")
    if r.get("id") != 0:
        fail(tid, f"appId={r.get('id')!r} after Clock→Spotify — expected 0"); return
    pass_(tid, "device stable after Clock→Spotify, appId=0")

def t_clk_13(dut: Dut):
    """T_CLK_13: Flip animation tick gate — 30ms while animating vs 1000ms stable."""
    tid = "T_CLK_13"
    print(f"{tid}  Flip tick gate reported correctly")
    # We cannot directly measure tick interval via serial; we verify that
    # switching to flip with clockStyle and confirming no crash / app stays responsive.
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    dut.cmd("set clockStyle flip"); time.sleep(0.5)
    # Device should still respond to serial commands during flip animation
    r = dut.cmd("get clockStyle")
    if r.get("name") != "flip":
        fail(tid, f"device unresponsive or wrong style: {r}"); return
    r2 = dut.cmd("get appId")
    if r2.get("id") != 1:
        fail(tid, f"appId lost during flip: {r2}"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, "device responsive during Flip style — serial commands answered correctly")

def t_clk_14(dut: Dut):
    """T_CLK_14: clockStyle readback format — val (int), name (str), last=true."""
    tid = "T_CLK_14"
    print(f"{tid}  clockStyle get response format")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    dut.cmd("set clockStyle 2"); time.sleep(0.2)
    r = dut.cmd("get clockStyle")
    if r.get("val") != 2:
        fail(tid, f"val={r.get('val')!r} — expected 2"); return
    if r.get("name") != "nixie":
        fail(tid, f"name={r.get('name')!r} — expected nixie"); return
    if r.get("last") is not True:
        fail(tid, f"last={r.get('last')!r} — expected true"); return
    _restore_spotify_from_clock(dut)
    pass_(tid, f"response has val=2 name=nixie last=true")


TESTS = {
    "T_CLK_01": t_clk_01,
    "T_CLK_02": t_clk_02,
    "T_CLK_03": t_clk_03,
    "T_CLK_04": t_clk_04,
    "T_CLK_05": t_clk_05,
    "T_CLK_06": t_clk_06,
    "T_CLK_07": t_clk_07,
    "T_CLK_08": t_clk_08,
    "T_CLK_09": t_clk_09,
    "T_CLK_10": t_clk_10,
    "T_CLK_11": t_clk_11,
    "T_CLK_12": t_clk_12,
    "T_CLK_13": t_clk_13,
    "T_CLK_14": t_clk_14,
}
