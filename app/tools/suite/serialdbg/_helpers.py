"""Helpers shared by 2+ serialdbg families (TASK-480).

Not a dumping ground (M-TOOLING §3): a helper used by exactly one family
lives in that family's own module instead. Populated as families are
extracted and their transitive shared dependencies surface -- started with
the teletext family, which needs the universal app-switch / taskbar-scroll
/ diagnostics primitives almost every other family also uses.
"""

import json
import time
from contextlib import contextmanager

from lib.dut import Dut
from lib.results import skip, pass_
import coords as _c
from app_ids_gen import APP_SLOT


def _tap_and_wait_log(dut: Dut, x: int, y: int, marker: str,
                       tap_timeout: float = 5.0, log_timeout: float = 8.0
                       ) -> tuple[dict | None, bool]:
    """Send a tap and scan for `marker` in ONE continuous serial read.

    TASK-417 gate investigation (2026-08-11): the split pattern used
    elsewhere — dut.cmd(f"tap {x} {y}") followed by a separate
    _wait_for_log() — has a real race. dut.cmd()'s read_json() silently
    discards every non-JSON line while hunting for the tap's own JSON
    reply. spotifyTask's async trace lines ("dequeued action=SHUFFLE",
    "hard reset — stopping client") are printed from a DIFFERENT FreeRTOS
    task and can land in that exact window — read_json() eats them before
    the caller's own _wait_for_log() ever starts reading, and the check
    then times out even though the firmware did exactly the right thing.
    Confirmed on the DUT: a raw serial capture (LOG_FILE) showed
    "dequeued action=SHUFFLE" and "dequeued action=REPEAT" both present,
    in order, within the same second — while T_PLR_17's old split-read
    reported FAIL for both ("dispatch did not reach spotifyTask"). The
    firmware was never at fault; the harness was reading around the line
    it needed. This helper keeps the tap-ack JSON parse and the log-marker
    scan in one unbroken readline() loop so nothing sent to the wire
    between them can be silently lost. Returns
    (json_response_or_None, marker_found)."""
    dut.wait_shell_cooldown_clear()
    dut.send(f"tap {x} {y}")
    resp: dict | None = None
    marker_found = False
    deadline = time.monotonic() + max(tap_timeout, log_timeout)
    while time.monotonic() < deadline and not (resp is not None and marker_found):
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if not line:
            continue
        if resp is None and line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "tap":
                    resp = obj
                    continue
            except json.JSONDecodeError:
                pass
        if marker in line:
            marker_found = True
    return resp, marker_found


def _drain_data_pipeline(dut: Dut, timeout_s: float = 200.0, tag: str = "") -> bool:
    """Wait until the dataTask/spotifyTask fetch pipeline is quiet: nothing in
    flight or queued, no unacked tlsYield, and spotifyTask not inside an API
    call (spAct=3 — doPoll incl. token refresh has no yield check). TASK-299/300:
    a fetch enqueued behind a busy pipeline serializes for up to minutes —
    firmware working as designed (TASK-244 accepted poll-bounded yield latency)
    — so tests that measure fetch completion rather than latency under
    contention must drain first. Returns True once quiet, False on timeout."""
    prefix = f"[{tag}] " if tag else ""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            q = dut.cmd("get dataq", timeout=3.0)
            if (q.get("queueWaiting", 1) == 0 and q.get("inFlight", 0) == -1
                    and q.get("yieldCount", 1) == 0 and q.get("spAct") != 3):
                return True
            print(f"  {prefix}draining: inFlight={q.get('inFlight')} "
                  f"queueWaiting={q.get('queueWaiting')} yieldCount={q.get('yieldCount')} "
                  f"spAct={q.get('spAct')}", flush=True)
        except TimeoutError:
            pass
        time.sleep(2.0)
    return False


def _poll_shell_busy(dut: Dut, expected: bool, timeout_ms: int = 500,
                     cmd_timeout: float = 5.0) -> bool:
    """Poll get shellBusy until busy==expected. Returns True if reached within timeout.
    cmd_timeout: per-command serial timeout; raised to 5 s by default to tolerate
    transient serial flooding from concurrent dataTask output (chart/quote fetches)."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get shellBusy", timeout=cmd_timeout)
            if r.get("ok") and r.get("busy") == expected:
                return True
        except TimeoutError:
            pass  # transient serial flood from dataTask; retry
        time.sleep(0.02)
    return False


def _get_vis_mode(dut: Dut) -> int | None:
    """Return current visMode integer (0–3), or None on error."""
    r = dut.cmd("get visMode", timeout=2.0)
    if r.get("ok"):
        try:
            return int(r["mode"])
        except (KeyError, ValueError, TypeError):
            pass
    return None


def _do_drag(dut: Dut, x1: int, y1: int, x2: int, y2: int,
             steps: int = 30, timeout: float = 15.0) -> dict | None:
    """Send a drag and return the drag JSON response, or None on timeout."""
    dut.send(f"drag {x1} {y1} {x2} {y2} {steps}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            return None
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    return obj
            except json.JSONDecodeError:
                pass
    return None


def _get_scroll(dut: Dut, timeout: float = 3.0) -> int | None:
    """Return scrollOffset int, or None on error."""
    r = dut.cmd("get scrollOffset", timeout=timeout)
    if not r.get("ok") or r.get("key") != "scrollOffset":
        return None
    return r.get("val")


# PLEDIT (playlist-editor) drag geometry — shared by the velocity-scroll-001
# suite (Spotify queue, shell.py) and its WebRadio variant (webradio.py).
_PLEDIT_X  = 140   # x inside PLEDIT content area  (x ∈ [12..255])
_PLSTART_Y = 163   # drag start y (below anchor)
_PLEND_Y   = 150   # drag end y   (above anchor);  dy = 150-163 = -13 (finger up)


def _vs_drain_until_drag(dut: Dut, timeout: float = 10.0) -> tuple[list[dict], dict | None]:
    """Read JSON lines until the drag-completion response arrives.
    Returns (other_responses_in_order, drag_resp_or_None)."""
    pre: list[dict] = []
    drag_resp = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("cmd") == "drag":
            drag_resp = obj
            break
        pre.append(obj)
    return pre, drag_resp


def _check_residue(dut: Dut, tid: str) -> bool:
    """After switching back to Spotify, verify lastPlaylistDraw advances within 3 s.
    Returns True if PASS was recorded, False if the check was skipped (no Spotify signal).
    Does not call fail() — caller decides on skip vs fail."""
    r_before = dut.cmd("get lastPlaylistDraw", timeout=3.0)
    if not r_before.get("ok"):
        return False
    t_before = r_before.get("ms", 0)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        r = dut.cmd("get lastPlaylistDraw", timeout=1.0)
        if r.get("ok") and r.get("ms", t_before) != t_before:
            pass_(tid, f"lastPlaylistDraw advanced {t_before}→{r['ms']} — no TFT state residue")
            return True
        time.sleep(0.05)
    return False


def _switch_to_stock(dut: Dut, timeout: float = 5.0) -> bool:
    """Switch to StockApp via the serial switchApp command.
    TASK-247: force List launch view first (in-RAM only, not persisted) so the
    list-centric suite is deterministic regardless of the device's saved stockMode
    (e.g. a user-configured Heatmap default), and so the heatmap/chart launch no
    longer pre-fetches the unused list quote."""
    dut.cmd("set stockMode 0", timeout=timeout)
    r = dut.cmd(f"switchApp {APP_SLOT['Stock']}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.3)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Stock"


def _restore_from_stock(dut: Dut, timeout: float = 5.0) -> bool:
    """Switch back to Spotify from Stock."""
    r = dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.3)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Spotify"


def _stock_get(dut: Dut, var: str, timeout: float = 3.0):
    """Get a stock debug var; return the response dict."""
    return dut.cmd(f"get {var}", timeout=timeout)


def _stock_ok_count(dut: Dut) -> int:
    """Return current fetchOkCount from firmware, or -1 on error."""
    r = _stock_get(dut, "fetchOkCount")
    if r.get("ok"):
        try:
            return int(r.get("val", -1))
        except (ValueError, TypeError):
            pass
    return -1


_CHART_PHASE_NAMES = {0: "TLS/connect", 1: "GET/response", 2: "JSON-parse"}


def _wait_chart_complete(dut: Dut, before: int, timeout_s: float = 45.0,
                         test_id: str = "") -> bool:
    """Wait until fetchOkCount advances past `before` — proves a chart fetch completed
    (HTTP + parse), not just that it was enqueued (LL-041). `before` must be snapshotted
    from fetchOkCount before the triggering tap/command. Returns True on success.
    On timeout prints stockChartProgress phase and the last dataq sample to aid
    diagnosis (TASK-300: distinguishes queued/parked-in-yield from never-enqueued
    — the fetch's tlsYield() fires BEFORE stockChartProgress is set, so
    progress=-1 alone can't tell the two apart)."""
    prefix = f"[{test_id}] " if test_id else ""
    deadline = time.monotonic() + timeout_s
    last_q = None
    ticks = 0
    while time.monotonic() < deadline:
        try:
            current = _stock_ok_count(dut)
        except TimeoutError:
            time.sleep(1.0)
            continue
        if current > before:
            return True
        ticks += 1
        if ticks % 3 == 0:  # sample the dispatch pipeline every ~3 s (TASK-300)
            try:
                q = dut.cmd("get dataq", timeout=3.0)
                if q.get("ok"):
                    q.pop("ok", None); q.pop("cmd", None); q.pop("last", None)
                    if q != last_q:
                        print(f"  {prefix}dataq: {q}", flush=True)
                    last_q = q
            except TimeoutError:
                pass
        time.sleep(1.0)
    r_prog = dut.cmd("get stockChartProgress", timeout=3.0)
    phase = r_prog.get("val") if r_prog.get("ok") else "?"
    phase_name = _CHART_PHASE_NAMES.get(phase, "idle" if phase == -1 else "unknown")
    print(f"  {prefix}_wait_chart_complete timed out — stockChartProgress={phase} "
          f"({phase_name}) dataq={last_q}", flush=True)
    # TASK-386: heap/backoff snapshot on every timeout, for every caller, automatically
    # — dataq was already sampled above, this adds the two fields it doesn't cover.
    # Return type/signature unchanged (still bool) — zero risk to any of the 9 existing
    # call sites (T176/T185/T188/T192/T193/T194/T204/T-BUSY-01b/...), and any future
    # caller gets this for free without needing to know _diag_snapshot() exists.
    _diag_snapshot(dut, f"{prefix}_wait_chart_complete-timeout")
    return False


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


@contextmanager
def _bgpoll_suspended(dut: "Dut"):
    """Suspend background Spotify polls for the duration of the block.
    Guarantees bgPoll resumes even if the test body raises.
    Pre-conditions (e.g. _wait_shell_not_busy) are the caller's responsibility.
    """
    dut.cmd("set bgPoll 0", timeout=2.0)
    try:
        yield
    finally:
        dut.cmd("set bgPoll 1", timeout=2.0)
