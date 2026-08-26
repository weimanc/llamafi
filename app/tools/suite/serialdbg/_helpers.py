"""Helpers shared by 2+ serialdbg families (TASK-480).

Not a dumping ground (M-TOOLING §3): a helper used by exactly one family
lives in that family's own module instead. Populated as families are
extracted and their transitive shared dependencies surface -- started with
the teletext family, which needs the universal app-switch / taskbar-scroll
/ diagnostics primitives almost every other family also uses.
"""

import time

from lib.dut import Dut
from lib.results import skip
import coords as _c
from app_ids_gen import APP_SLOT


def _restore_spotify(dut: Dut, timeout: float = 3.0) -> bool:
    """Ensure currentAppId == Spotify; resets scroll then taps Spotify slot if needed.

    TASK-280: cmdTap's taskbar branch now routes through resolvePlayerSlot(), same as
    production — a tap on the player slot lands on WebRadio if that's the persisted
    mode. Force playerMode=spotify first so the tap is guaranteed to land on Spotify
    regardless of what a prior test left persisted (previously masked by the bug this
    task fixed: cmdTap used to always land on Spotify no matter the persisted mode).

    TASK-413: tapping the player slot while a player-mode app (Spotify/WebRadio/
    LocalPlayer) is ALREADY active now CYCLES instead of restoring (resolvePlayerTap,
    ADR-059 D6). So when currentAppId is WebRadio or LocalPlayer, setting
    playerMode=spotify and tapping no longer lands on Spotify — it cycles away from
    whatever `set playerMode spotify` just wrote. Step off to a non-player app
    (Clock) first so the follow-up tap takes the restore path, not the cycle path.
    """
    r = dut.cmd("get appId", timeout=timeout)
    if r.get("name") == "Spotify":
        return True
    if r.get("name") in ("WebRadio", "LocalPlayer"):
        _tb_set_offset(dut, 0)
        dut.set_cooldown_zero()
        cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
        dut.cmd(f"tap {cx} {cy}", timeout=timeout)
        time.sleep(0.2)
    dut.cmd("set playerMode spotify", timeout=timeout)
    _tb_set_offset(dut, 0)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=timeout)
    time.sleep(0.3)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("name") == "Spotify"


def _switch_to(dut: Dut, app_name: str, timeout: float = 3.0) -> bool:
    """Reset scroll to 0, tap the app's taskbar slot, verify appId == app_name."""
    if app_name not in APP_SLOT:
        return False
    _tb_set_offset(dut, 0)
    dut.set_cooldown_zero()
    x, y = _c.tap_taskbar_slot(APP_SLOT[app_name])
    dut.cmd(f"tap {x} {y}", timeout=timeout)
    time.sleep(0.4)
    r = dut.cmd("get appId", timeout=timeout)
    return r.get("ok", False) and r.get("name") == app_name


def _diag_snapshot(dut: Dut, tag: str = "") -> str:
    """Best-effort one-line heap/backoff/dataq snapshot (TASK-385). `run/test-targeted`
    always starts from a fresh flash+boot, so an isolated re-run can only prove a test
    fails-or-doesn't from a *clean* state — it can't observe whatever heap fragmentation,
    dataTask queue backlog, or Spotify-poll/tlsYield contention ~150 prior tests may have
    left behind by the time T193/T194 run in a real `run/test` full-suite pass. Embedding
    this snapshot directly into the fail()/skip() reason (not just printing it) means the
    evidence survives even when the run has no `LOG_FILE=` capture — closing exactly the
    gap TASK-385 was originally blocked on ('no serial capture for this run'). Compare
    against the clean-boot baseline from the 2026-08-02 isolated 5/5-pass investigation:
    heap freeInt~74-118k/lfbInt~41-45k, dataq queueWaiting=0/inFlight=0 pre-trigger,
    spAct idle between POLL dequeues — a same-run T193/T194 snapshot reading materially
    lower/busier than that is evidence for the suite-accumulation hypotheses; a snapshot
    that looks the same as a clean boot points back toward plain connect-level noise
    (TASK-383) instead."""
    parts = []
    try:
        h = dut.cmd("get heap", timeout=3.0)
        parts.append(f"heap(freeInt={h.get('freeInt')},lfbInt={h.get('lfbInt')},"
                      f"freeDma={h.get('freeDma')},lfbDma={h.get('lfbDma')})" if h.get("ok")
                      else "heap(no-ok)")
    except TimeoutError:
        parts.append("heap(timeout)")
    try:
        b = dut.cmd("get backoff", timeout=3.0)
        parts.append(f"backoff(cf={b.get('consecutiveFailures')})" if b.get("ok")
                      else "backoff(no-ok)")
    except TimeoutError:
        parts.append("backoff(timeout)")
    try:
        q = dut.cmd("get dataq", timeout=3.0)
        parts.append(
            f"dataq(ms={q.get('ms')},qw={q.get('queueWaiting')},inFlight={q.get('inFlight')},"
            f"inFlightMs={q.get('inFlightMs')},tlsStopped={q.get('tlsStopped')},"
            f"spAct={q.get('spAct')},spActMs={q.get('spActMs')},"
            f"yieldCount={q.get('yieldCount')})" if q.get("ok") else "dataq(no-ok)")
    except TimeoutError:
        parts.append("dataq(timeout)")
    snap = " ".join(parts)
    prefix = f"[{tag}] " if tag else ""
    print(f"  {prefix}diag: {snap}", flush=True)
    return snap


def _wait_shell_not_busy(dut: Dut, timeout_s: float = 45.0) -> bool:
    """Wait for g_shellBusy to clear (chart/heatmap fetch complete)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get shellBusy", timeout=5.0)
            if r.get("ok") and not r.get("busy", True):
                return True
        except TimeoutError:
            pass
        time.sleep(1.0)
    # TASK-386: same treatment as _wait_chart_complete — automatic for every caller.
    # This helper gates on g_shellBusy directly, so a timeout here is exactly as
    # relevant to the dataTask/tlsYield hypotheses as a chart-fetch timeout is.
    _diag_snapshot(dut, "_wait_shell_not_busy-timeout")
    return False


# TASK-242: the taskbar cycles through apps BEFORE WebRadio — WebRadio is
# eject-entered only, no taskbar slot. Must match firmware TASKBAR_APP_COUNT
# (= (int)AppId::WebRadio), NOT APP_COUNT, or scroll-wrap tests mismatch.
_TB_X = _c.TASKBAR_X + _c.TASKBAR_W // 2   # 297
_TB_N = APP_SLOT["WebRadio"]                  # = 11 (Spotify..PlaneRadar) — TASK-307


def _tb_get_offset(dut: Dut) -> "int | None":
    r = dut.cmd("get tbScrollOffset", timeout=3.0)
    v = r.get("val")
    return int(v) if isinstance(v, (int, float)) else None


def _tb_set_offset(dut: Dut, target: int) -> bool:
    """Drive tbScrollOffset to target via drag gestures (one drag per slot step).
    Chooses the shorter path; each drag is 50 px / 10 steps (LP-safe).
    y span [60, 110] stays within screen bounds and clear of slot 0 edge."""
    current = _tb_get_offset(dut)
    if current is None:
        return False
    n = _TB_N
    steps_up   = (target - current) % n   # up = offset++
    steps_down = (current - target) % n   # down = offset--
    if steps_up <= steps_down:
        for _ in range(steps_up):
            dut.set_cooldown_zero()
            dut.cmd(f"drag {_TB_X} 110 {_TB_X} 60 10", timeout=5.0)  # 50 px up → +1
            time.sleep(0.1)
    else:
        for _ in range(steps_down):
            dut.set_cooldown_zero()
            dut.cmd(f"drag {_TB_X} 60 {_TB_X} 110 10", timeout=5.0)  # 50 px down → -1
            time.sleep(0.1)
    return _tb_get_offset(dut) == target
