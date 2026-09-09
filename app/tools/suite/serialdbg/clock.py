"""Clock app tests -- M-CLOCK-STYLES suite (TASK-193). Split from
run_serialdbg_tests.py, TASK-480 stage 2 (pilot family)."""

import time

from lib.dut import BadField, Dut
import coords as _c
from lib.results import pass_, fail, unmet


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
    """T_CLK_08: `set clockStyle` reports that SettingsStorage::save() succeeded.

    TASK-603 (WP-H §1, disposition §4.6). The body used to write the style and
    then read it back through the same command — true whether or not the save
    aborted, which is the whole of the claim. `set clockStyle` now returns
    `saved`, the way `set fmt24h` has since TASK-429
    (app/src/debug/serialConsole/cmdSet.cpp), so the persistence half has an
    oracle the harness did not write.

    This is deliberately NOT bundled with the five visual clock claims that need
    ADR-064's `get sig` (T_CLK_02/09/13/14 are retired UNOBSERVABLE); it was a
    four-line firmware change, and pricing it as a blocked ledger row would have
    parked it behind the Clock family rewrite. It is also not a reboot test: the
    stronger form is `Dut.reboot_and_wait`, the route T_PR_04 and T_PRM_01 take,
    and that is a separate id under TASK-615.
    """
    tid = "T_CLK_08"
    print(f"{tid}  set clockStyle reports SettingsStorage::save() succeeded")
    if not _switch_to_clock(dut):
        fail(tid, "could not switch to Clock"); return
    r_set = dut.cmd("set clockStyle nixie")
    time.sleep(0.4)
    saved = r_set.get("saved")
    if saved is None:
        unmet(tid, "`set clockStyle` returned no `saved` field — this firmware "
                   "predates the TASK-603 cmdSet change, so the persistence claim "
                   "has no oracle on this build. Inconclusive (BP-074), not a pass: "
                   f"reply was {r_set!r}")
        return
    if saved is not True:
        fail(tid, f"SettingsStorage::save() reported saved={saved!r} — the style is "
                  f"live in RAM but will NOT survive a reboot")
        return
    if dut.get_str("clockStyle", field="name") != "nixie":
        fail(tid, "clockStyle did not read back as nixie after a reported-successful save")
        return
    _restore_spotify_from_clock(dut)
    pass_(tid, "set clockStyle nixie -> saved=true, and the value reads back")


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


def _sig_field(r: dict, name: str) -> int:
    """A typed read of one `get sig` field (R18: no defaults)."""
    if not r.get("ok"):
        raise BadField("sig", f"device refused `get sig`: {r!r}")
    if name not in r or r[name] is None:
        raise BadField("sig", f"`get sig` replied without {name!r}: {r!r}")
    return int(r[name])


def t_clk_sig_01(dut: Dut):
    """T_CLK_SIG_01: the Clock canvas is DRAWN — ink and distinct colours over
    the panel readback (ADR-064 D3), the structural assertion H-2 lacked.

    A face rendering as a solid rectangle (H-2: passed all fourteen Clock ids)
    reads back inkCount=0, distinctColors=1 and fails here with no golden hash
    and no time freeze. Region is the app canvas, derived from the generated
    shell layout (D7), read once after `get idle` (D8), never polled (D2).
    """
    tid = "T_CLK_SIG_01"
    if not _switch_to_clock(dut):
        unmet(tid, "switchApp 1 refused, so no Clock canvas was on screen to read")
        return
    deadline = time.monotonic() + 8.0
    while not dut.get_bool("idle", field="idle", timeout=3.0):
        if time.monotonic() > deadline:
            unmet(tid, "shell never went idle within 8 s after switching to Clock — "
                       "a signature taken mid-repaint is a torn read (ADR-064 D8)")
            _restore_spotify_from_clock(dut)
            return
        time.sleep(0.2)
    # Canvas = everything left of the taskbar: (0, 0, TASKBAR_X, SCREEN_H).
    w, h = _c.TASKBAR_X, _c.SCREEN_H
    r = dut.read_reply(f"get sig 0 0 {w} {h}", timeout=8.0, expect_var="sig")
    ink, colours, bg = (_sig_field(r, "inkCount"), _sig_field(r, "distinctColors"),
                        _sig_field(r, "bgColor"))
    # Floor: 1 % of the canvas. Origin: ADR-064 D3 asks only that the region is
    # not a constant; every shipped style's digits alone cover far more than
    # 1 % of 275x240 (the Nixie tubes are ~120x60 each). A tighter bound is a
    # per-style golden, which is TASK-639's job, not this id's.
    floor = (w * h) // 100
    if colours < 2 or ink < floor:
        fail(tid, f"Clock canvas reads back as (nearly) a constant: inkCount={ink} "
                  f"(floor {floor}), distinctColors={colours}, bgColor=0x{bg:04x} — "
                  f"H-2's solid rectangle, now observable")
        _restore_spotify_from_clock(dut)
        return
    pass_(tid, f"inkCount={ink} distinctColors={colours} over {w}x{h}, bg=0x{bg:04x}")
    _restore_spotify_from_clock(dut)


TESTS = {
    "T_CLK_01": t_clk_01,
    "T_CLK_03": t_clk_03,
    "T_CLK_04": t_clk_04,
    "T_CLK_05": t_clk_05,
    "T_CLK_06": t_clk_06,
    "T_CLK_07": t_clk_07,
    "T_CLK_08": t_clk_08,
    "T_CLK_10": t_clk_10,
    "T_CLK_11": t_clk_11,
    "T_CLK_12": t_clk_12,
    "T_CLK_SIG_01": t_clk_sig_01,
}
