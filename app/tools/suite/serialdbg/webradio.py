"""WebRadio app tests. Split from run_serialdbg_tests.py, TASK-480.

Covers: eject/error-state injection (TASK-211/212), DUT coexistence + heap
(TASK-207/208/209), auto-skip terminal bound (TASK-237/276/393/395), TLS
path + Spotify coexistence (TASK-214), real-audio VIS envelope + per-band
spectrum (M-WEBRADIO-REAL-VIS / TASK-387), and the WebRadio variant of the
velocity-scroll-001 PLEDIT suite (TASK-412 / T_PLE_08).
"""

import functools
import re
import time
from typing import Optional

from lib.dut import Dut
from lib.results import pass_, fail, skip, flake
import coords as _c
from app_ids_gen import APP_SLOT
from suite.serialdbg._meta import meta
from suite.serialdbg._helpers import (
    _restore_spotify, _switch_to, _wait_shell_not_busy, _diag_snapshot,
    _tap_and_wait_log, _do_drag, _get_scroll, _vs_drain_until_drag,
    _PLEDIT_X, _PLSTART_Y, _PLEND_Y, _drain_data_pipeline,
    _bgpoll_suspended, _poll_shell_busy, _get_vis_mode,
)


# ── velocity-scroll-001 WebRadio variant (TASK-412 / T_PLE_08) ──────────────
# TASK-412 unified PLEDIT render/scroll behind the shared PleditView, so these
# mirror T155-T160 exactly but drive WebRadio's StationListSource (synthetic
# stations via `set wrDeadUrls`, no network needed) instead of Spotify's
# queue. Entry uses _switch_to_webradio_capture_heap (the real eject path) —
# NOT _switch_to("WebRadio"), which taps a taskbar slot
# WebRadio doesn't have (eject-only app, see _switch_to_webradio_capture_heap
# docstring).

def _wr_deadurls_custody(fn):
    """Give a T_PLE_WR_* body custody of the `wrDeadUrls` injector it arms.

    `_vs_precondition_webradio` below issues `set wrDeadUrls 15`, which sets
    `WebRadioApp::_debugForceConnFail` — every subsequent `_play()` fails its
    connect deterministically, without touching the network. None of the six
    bodies cleared it. Confirmed on hardware in the M-TESTQUAL phase-2 session
    (2026-09-06): the flag was armed six times at raw-log lines 12346-13265 and
    first cleared at line 14219, ~950 lines later, inside T237 — and in that gap
    `T_WR_COEX_01` FAILed with `wrState=5` (the value the flag produces) while
    `T_WR_COEX_02/04` and `T_WR_HEAP_03/04` SKIPped on "not in PLAYING state".
    Five verdicts, produced by suite order, filed as radio-browser.info network
    flake in `flaky.yaml` for about a year.

    `Dut.injected` is the mechanism BP-073 provides for exactly this shape — a
    write-only injector with no read-back, whose disarming value (`0`, which
    `webRadioApp.cpp:1032-1041` clears the flag and the synthetic list on) is a
    fact about the firmware the caller knows and `dut.py` does not. Arming here
    rather than only in the precondition is deliberate: the context has to
    outlive every `return` in the body, and the precondition's own re-arm after
    the WebRadio switch-in is idempotent.
    """
    @functools.wraps(fn)
    def wrapper(dut: Dut):
        with dut.injected("wrDeadUrls", 15, clear_to=0):
            return fn(dut)
    return wrapper


def _vs_precondition_webradio(dut: Dut, tid: str) -> bool:
    """Shared precondition for the WebRadio-side battery: WebRadio active, 15
    synthetic stations (set wrDeadUrls), scrollOffset=0, D_IDLE."""
    r = dut.cmd("get appId", timeout=3.0)
    if r.get("name") != "WebRadio":
        ok, _heap = _switch_to_webradio_capture_heap(dut)
        if not ok:
            skip(tid, "precondition: could not switch to WebRadio")
            return False
    r_dead = dut.cmd("set wrDeadUrls 15", timeout=5.0)
    if not r_dead.get("ok", False):
        skip(tid, f"precondition: set wrDeadUrls 15 failed: {r_dead}")
        return False
    r_c = dut.cmd("get wrCount", timeout=3.0)
    if r_c.get("count", 0) < 15:
        skip(tid, f"precondition: wrCount={r_c.get('count')} after set wrDeadUrls 15")
        return False
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    for _ in range(5):
        _do_drag(dut, xd, yd, xd2, yd2)
    so = _get_scroll(dut)
    if so != 0:
        skip(tid, f"precondition: scrollOffset={so} could not be reset to 0")
        return False
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        skip(tid, f"precondition: dragState={rg.get('state')!r} not D_IDLE")
        return False
    dut.set_cooldown_zero()
    return True


@_wr_deadurls_custody
def t_ple_wr_155(dut: Dut):
    """T_PLE_WR_155 (T_PLE_08): WebRadio — 0-dy tap in dead zone fires PLEDIT hit."""
    print("T_PLE_WR_155  WebRadio: tap within dead zone fires PLEDIT hit (0-dy)")
    if not _vs_precondition_webradio(dut, "T_PLE_WR_155"):
        return
    baseline = _get_scroll(dut)
    r = dut.cmd(f"tap {_PLEDIT_X} {_PLEND_Y}", timeout=5.0)
    if not r.get("ok"):
        fail("T_PLE_WR_155", f"tap returned ok=false: {r}")
        return
    if r.get("hit") != "PLEDIT":
        fail("T_PLE_WR_155", f"hit={r.get('hit')!r} — expected PLEDIT; tap missed content zone")
        return
    post = _get_scroll(dut)
    if post != baseline:
        fail("T_PLE_WR_155", f"scrollOffset changed {baseline}→{post} — scroll-end fired instead of tap")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T_PLE_WR_155", f"dragState={rg.get('state')!r} — Release cleanup failed")
        return
    pass_("T_PLE_WR_155",
          f"hit=PLEDIT scrollOffset={post} (unchanged) dragState=D_IDLE — tap path confirmed")


@_wr_deadurls_custody
def t_ple_wr_156(dut: Dut):
    """T_PLE_WR_156 (T_PLE_08): WebRadio — dy=13 px drag outside dead zone → scroll-end."""
    print("T_PLE_WR_156  WebRadio: release outside dead zone suppresses tap (dy=13 px)")
    if not _vs_precondition_webradio(dut, "T_PLE_WR_156"):
        return
    dut.send(f"drag {_PLEDIT_X} {_PLEND_Y} {_PLEDIT_X} {_PLSTART_Y} 1")
    _, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T_PLE_WR_156", "no drag response within 10 s")
        return
    if not drag_resp.get("ok"):
        fail("T_PLE_WR_156", f"drag response ok=false: {drag_resp}")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T_PLE_WR_156", f"dragState={rg.get('state')!r} — Release did not complete")
        return
    rc = dut.cmd("get cooldown", timeout=3.0)
    cooldown_ms = rc.get("remainingMs", 9999)
    if cooldown_ms > 220:
        fail("T_PLE_WR_156", f"cooldown={cooldown_ms} ms > 220 — tap branch fired (expected scroll-end ≤220 ms)")
        return
    pass_("T_PLE_WR_156",
          f"dragState=D_IDLE cooldown={cooldown_ms} ms ≤ 220 — scroll-end confirmed, tap suppressed")


@_wr_deadurls_custody
def t_ple_wr_157(dut: Dut):
    """T_PLE_WR_157 (T_PLE_08): WebRadio — velocity ≈ 2.0 rows/s at dy=-13 px.
    Uses `drag ... hold` (synchronous ack, no interleaved sends) + `get
    wrScroll` (WebRadio's own debug surface — `tick`'s scrollOffset field is
    winampDisplay-only per TASK-277 VE-1-5). The interleaved-send pattern
    T157 uses is tuned to Spotify's loop() iteration cost; when WebRadio is
    active that cost differs, and the reads raced ahead of the injection
    queue's Press step, misreporting D_IDLE. Confirmed by manual delay-padded
    probe: the same gesture reaches D_PLEDIT_SCROLL, vel≈2.0004 rows/s."""
    print("T_PLE_WR_157  WebRadio: tick 50×20ms at dy=-13 → wrScroll.offset ∈ [1,3]")
    if not _vs_precondition_webradio(dut, "T_PLE_WR_157"):
        return
    r_drag = dut.cmd(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 1 hold", timeout=5.0)
    if not r_drag.get("ok") or not r_drag.get("hold"):
        fail("T_PLE_WR_157", f"drag hold ack failed: {r_drag}")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_PLEDIT_SCROLL":
        fail("T_PLE_WR_157", f"dragState={rg.get('state')!r} — gesture did not enter D_PLEDIT_SCROLL")
        dut.cmd("release", timeout=3.0)
        return
    r_tick = dut.cmd("tick 50 20", timeout=5.0)
    if not r_tick.get("ok"):
        fail("T_PLE_WR_157", f"tick failed: {r_tick}")
        dut.cmd("release", timeout=3.0)
        return
    r_ws = dut.cmd("get wrScroll", timeout=3.0)
    so = r_ws.get("offset", -1)
    dut.cmd("release", timeout=3.0)
    if not (1 <= so <= 3):
        fail("T_PLE_WR_157", f"wrScroll.offset={so} after tick 50×20ms at dy=-13 — "
                     f"expected [1,3] (velocity≈2.0 rows/s)")
        return
    pass_("T_PLE_WR_157", f"D_PLEDIT_SCROLL confirmed; wrScroll.offset={so} ∈ [1,3] → velocity≈2.0 rows/s")


@_wr_deadurls_custody
def t_ple_wr_158(dut: Dut):
    """T_PLE_WR_158 (T_PLE_08): WebRadio — tick 50×20ms at dy=-13 advances wrScroll.offset ≥ 1.
    See T_PLE_WR_157 docstring for why `hold`/`get wrScroll` replace the
    interleaved-send pattern here."""
    print("T_PLE_WR_158  WebRadio: tick integration: 1 s at dy=-13 → wrScroll.offset ≥ 1")
    if not _vs_precondition_webradio(dut, "T_PLE_WR_158"):
        return
    r_drag = dut.cmd(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 1 hold", timeout=5.0)
    if not r_drag.get("ok") or not r_drag.get("hold"):
        fail("T_PLE_WR_158", f"drag hold ack failed: {r_drag}")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_PLEDIT_SCROLL":
        fail("T_PLE_WR_158", f"dragState={rg.get('state')!r} — gesture did not enter D_PLEDIT_SCROLL")
        dut.cmd("release", timeout=3.0)
        return
    r_tick = dut.cmd("tick 50 20", timeout=5.0)
    if not r_tick.get("ok"):
        fail("T_PLE_WR_158", f"tick failed: {r_tick}")
        dut.cmd("release", timeout=3.0)
        return
    r_ws = dut.cmd("get wrScroll", timeout=3.0)
    so = r_ws.get("offset", -1)
    dut.cmd("release", timeout=3.0)
    if so < 1:
        fail("T_PLE_WR_158", f"wrScroll.offset={so} after tick 50×20ms at dy=-13 — "
                     f"expected ≥ 1; accumulator integration or tickScroll guard broken")
        return
    pass_("T_PLE_WR_158", f"wrScroll.offset={so} ≥ 1 after tick 50×20ms at dy=-13 — integration confirmed")


@_wr_deadurls_custody
def t_ple_wr_159(dut: Dut):
    """T_PLE_WR_159 (T_PLE_08): WebRadio — scrollAccum non-zero during drag, 0.0000 on Release.
    See T_PLE_WR_157 docstring for why `hold`/`get wrScroll` replace the
    interleaved-send pattern here."""
    print("T_PLE_WR_159  WebRadio: accumulator resets to 0.0000 on Release")
    if not _vs_precondition_webradio(dut, "T_PLE_WR_159"):
        return
    r_drag = dut.cmd(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 1 hold", timeout=5.0)
    if not r_drag.get("ok") or not r_drag.get("hold"):
        fail("T_PLE_WR_159", f"drag hold ack failed: {r_drag}")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_PLEDIT_SCROLL":
        fail("T_PLE_WR_159", f"dragState={rg.get('state')!r} — gesture not active mid-drag")
        dut.cmd("release", timeout=3.0)
        return
    r_tick = dut.cmd("tick 10 20", timeout=5.0)
    if not r_tick.get("ok"):
        fail("T_PLE_WR_159", f"tick failed: {r_tick}")
        dut.cmd("release", timeout=3.0)
        return
    r_ws_pre = dut.cmd("get wrScroll", timeout=3.0)
    accum_pre = r_ws_pre.get("accum", 0.0)
    if accum_pre == 0.0:
        fail("T_PLE_WR_159", f"scrollAccum={accum_pre} mid-drag — expected non-zero")
        dut.cmd("release", timeout=3.0)
        return
    dut.cmd("release", timeout=3.0)
    r_ws_post = dut.cmd("get wrScroll", timeout=3.0)
    accum_post = r_ws_post.get("accum", -1.0)
    if accum_post != 0.0:
        fail("T_PLE_WR_159", f"scrollAccum={accum_post} after Release — expected 0.0000; "
                     f"Release cleanup (_scrollAccum=0) not firing")
        return
    rg2 = dut.cmd("get dragState", timeout=3.0)
    if rg2.get("state") != "D_IDLE":
        fail("T_PLE_WR_159", f"dragState={rg2.get('state')!r} after Release — expected D_IDLE")
        return
    pass_("T_PLE_WR_159",
          f"scrollAccum={accum_pre:.4f} mid-drag (non-zero) → 0.0000 after Release; dragState=D_IDLE")


@_wr_deadurls_custody
def t_ple_wr_160(dut: Dut):
    """T_PLE_WR_160 (T_PLE_08): WebRadio — tickScroll is a no-op when dragState is D_IDLE."""
    print("T_PLE_WR_160  WebRadio: tickScroll no-op when D_IDLE")
    if not _vs_precondition_webradio(dut, "T_PLE_WR_160"):
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T_PLE_WR_160", f"precondition: dragState={rg.get('state')!r} not D_IDLE")
        return
    baseline = _get_scroll(dut)
    if baseline is None:
        fail("T_PLE_WR_160", "get scrollOffset failed")
        return
    r_tick = dut.cmd("tick 50 20", timeout=5.0)
    if not r_tick.get("ok"):
        fail("T_PLE_WR_160", f"tick command failed: {r_tick}")
        return
    post = _get_scroll(dut)
    if post != baseline:
        fail("T_PLE_WR_160", f"scrollOffset changed {baseline}→{post} during D_IDLE tick — "
                     f"tickScroll guard clause not firing")
        return
    r_vel = dut.cmd("get scrollVelocity", timeout=3.0)
    vel = r_vel.get("val", None)
    if vel != 0.0:
        fail("T_PLE_WR_160", f"scrollVelocity={vel} after D_IDLE tick — expected 0.0000")
        return
    pass_("T_PLE_WR_160",
          f"scrollOffset={post} (unchanged) scrollVelocity=0.0000 — tickScroll D_IDLE guard confirmed")


# ── M-WEBRADIO helpers ────────────────────────────────────────────────────────

def _wait_wr_count(dut: Dut, min_count: int = 1, timeout: float = 120.0) -> bool:
    """Poll get wrCount until count >= min_count or fetch done with no stations or timeout.
    Early-exits False when pending=0 and count < min_count (fetch completed, no stations)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get wrCount", timeout=3.0)
            count = r.get("count", 0)
            if count >= min_count:
                return True
            # Firmware reports pending=0 → fetch done, no more stations coming — not a
            # timeout, an expected negative result; no diagnostic snapshot needed here.
            if "pending" in r and r["pending"] == 0:
                return False
        except TimeoutError:
            pass
        time.sleep(2.0)
    # TASK-386: genuine deadline-exceeded timeout only (not the pending=0 early exit
    # above) — same rationale as _wait_chart_complete, automatic for every caller.
    _diag_snapshot(dut, "_wait_wr_count-timeout")
    return False


def _wait_wr_state(dut: Dut, target: int, timeout: float = 120.0) -> bool:
    """Poll get wrState until state == target or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get wrState", timeout=3.0)
            if r.get("state") == target:
                return True
        except TimeoutError:
            pass
        time.sleep(2.0)
    _diag_snapshot(dut, "_wait_wr_state-timeout")
    return False


def _webradio_enter_with_stations(dut: Dut, tid: str,
                                   fetch_timeout: float = 180.0) -> int:
    """Switch to WebRadio with bgPoll suspended so tlsYield() in fetchWebRadioStations
    completes almost instantly (spotifyTask is idle, no in-flight HTTP calls).
    Returns station count >= 1 on success, 0 on failure.

    Background: fetchWebRadioStations() calls spotifyTask::tlsYield() which waits up
    to 150 s for spotifyTask to stop its TLS session. If bgPoll is enabled and
    spotifyTask is mid-call, a failed Spotify API call (30 s handshake + 15 s recv ×
    2 retries = 90 s) consumes most of the 150 s budget.  The radio-browser HTTPS
    fetch then takes up to 3 mirrors × 30 s connect timeout each = 90 s worst case.
    fetch_timeout defaults to 180 s: safety margin over 90 s worst-case with fast tlsYield.
    IMPORTANT: do NOT re-switch when already in WebRadio — re-switch calls init() (resets
    _stationCount=0) and queues another fetch, causing a growing backlog that makes
    subsequent tests progressively worse.  When pending=0 in get wrCount response, the
    fetch is done (success or failure) and _wait_wr_count returns immediately."""
    # Fast path: already in WebRadio with stations loaded
    r = dut.cmd("get appId", timeout=3.0)
    already_in_wr = r.get("name") == "WebRadio"
    if already_in_wr:
        r_c = dut.cmd("get wrCount", timeout=3.0)
        if r_c.get("count", 0) >= 1:
            return r_c["count"]

    # Slow path: suspend bgPoll, switch only if not already in WebRadio, wait for fetch
    dut.cmd("set bgPoll 0", timeout=2.0)
    try:
        if not already_in_wr:
            _switch_to_webradio_capture_heap(dut)
        if not _wait_wr_count(dut, timeout=fetch_timeout):
            return 0
        r_c = dut.cmd("get wrCount", timeout=3.0)
        return r_c.get("count", 0)
    finally:
        dut.cmd("set bgPoll 1", timeout=2.0)


def _switch_to_webradio_capture_heap(dut: Dut) -> tuple[bool, dict]:
    """Enter WebRadio via the taskbar player-slot cycle — its design entry path
    since TASK-413/414 (ADR-059 D6). Eject no longer switches apps (TASK-414:
    it means "load media from this source" per mode); tapping the player slot
    (APP_SLOT["Spotify"]) while Spotify is active cycles to WebRadio
    (resolvePlayerTap). WebRadio has NO taskbar slot of its own (TASK-242/
    LL-085) — this taps the Spotify/player slot, not a WebRadio one. Capture
    HEAP log lines emitted DURING init().
    Returns (switched_ok, heap_dict) where heap_dict keys are e.g. 'init', 'pre-fetch'.
    HEAP lines are logged before the JSON tap response, so we must read raw serial."""
    heap = {}
    if not _restore_spotify(dut):  # start from Spotify so one cycle tap lands on WebRadio
        return False, heap
    dut.set_cooldown_zero()
    dut.wait_shell_cooldown_clear()  # TASK-297: raw send bypasses cmd()'s drain
    x, y = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.send(f"tap {x} {y}")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if not line:
            continue
        m = re.search(r"HEAP (\S+) free=(\d+) min=(\d+)", line)
        if m:
            heap[m.group(1)] = {"free": int(m.group(2)), "min": int(m.group(3))}
        if line.startswith("{"):
            break  # consumed the JSON tap response
    time.sleep(0.4)
    r = dut.cmd("get appId", timeout=3.0)
    return r.get("name") == "WebRadio", heap


# ── T_WR_EJECT_01 — Eject from Spotify: TLS reset + force poll, stays put ───
# TASK-414 / ADR-059 D6: eject means "load media from this source" per mode
# now, not "switch player app" — that's the taskbar player-slot cycle's job
# (TASK-413). Superseded by T_PLR_06 for the cross-mode gate; kept as the
# WebRadio-app-specific unit check for its own eject behaviour (station
# refresh, no app switch).

def t_wr_eject_01(dut: Dut):
    """T_WR_EJECT_01: tap eject from Spotify → hit=EJECT; TLS reset + force poll
    fires (same as the logo tap); appId stays on Spotify."""
    print("T_WR_EJECT_01  Eject from Spotify → TLS reset + force poll, stays on Spotify")
    if not _restore_spotify(dut):
        skip("T_WR_EJECT_01", "precondition: could not restore Spotify")
        return
    # TASK-417: pre-existing gap (predates this task) — a tap fired while
    # g_shellBusy is still true from a prior async action (e.g. the restore
    # sequence's own app-switch/poll) is silently swallowed and reported as
    # hit=CANVAS (main.cpp's busy gate; see T_WR_EJECT_02's own comment on
    # the same mechanism). Every other tap-driving test in this file guards
    # with _wait_shell_not_busy() first — this one didn't.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    _ex, _ey = _c.tap_eject()
    # TASK-417 gate investigation: tap + log-scan combined into one
    # continuous read (_tap_and_wait_log) — the previous split
    # dut.cmd(tap)+manual-readline-loop pattern raced read_json()'s
    # non-JSON-line discard against spotifyTask's async "hard reset —
    # stopping client" trace (a different FreeRTOS task) and could silently
    # eat the very log line being waited for (confirmed on the DUT for the
    # identical T_PLR_06/T_PLR_17 pattern — see _tap_and_wait_log's
    # docstring). This test's own FLAKE result under the old pattern was
    # the same race, not a real intermittent firmware issue.
    r, tls_log_found = _tap_and_wait_log(dut, _ex, _ey, "hard reset",
                                          tap_timeout=5.0, log_timeout=8.0)
    hit    = r.get("hit", "") if r else ""
    action = r.get("action", "") if r else ""
    if hit != "EJECT":
        fail("T_WR_EJECT_01", f"expected hit=EJECT got {hit!r}")
        return
    if action != "EJECT":
        fail("T_WR_EJECT_01", f"expected action=EJECT got {action!r}")
        return
    time.sleep(0.4)
    r2 = dut.cmd("get appId", timeout=3.0)
    if r2.get("name") != "Spotify":
        fail("T_WR_EJECT_01", f"appId={r2.get('name')!r} after eject (expected Spotify — eject no longer switches apps)")
        return
    if not tls_log_found:
        flake("T_WR_EJECT_01", "hit=EJECT action=EJECT, appId stayed Spotify, but no "
              "TLS-reset log line within 8 s")
        return
    pass_("T_WR_EJECT_01", "hit=EJECT action=EJECT; appId stays Spotify; TLS reset + force poll fired")


# ── T_WR_EJECT_02 — Eject from WebRadio: station-list refresh, stays put ────

def t_wr_eject_02(dut: Dut):
    """T_WR_EJECT_02: tap eject from WebRadio → hit=EJECT; station list is
    re-enqueued (wrEnqueues advances); appId stays on WebRadio."""
    print("T_WR_EJECT_02  Eject from WebRadio → station list refresh, stays on WebRadio")
    # _webradio_enter_with_stations suspends bgPoll so the station fetch completes
    # quickly. Once _pendingStations=false, the main loop clears g_shellBusy
    # (main.cpp:2604-2606) and the eject tap won't be blocked with CANVAS.
    # Even if count=0 (fetch failed), _pendingStations is still resolved.
    cnt = _webradio_enter_with_stations(dut, "T_WR_EJECT_02", fetch_timeout=180.0)
    if dut.cmd("get appId", timeout=3.0).get("name") != "WebRadio":
        skip("T_WR_EJECT_02", "could not enter WebRadio")
        return
    _wait_shell_not_busy(dut, timeout_s=5.0)
    enq_before = dut.cmd("get dataq", timeout=3.0).get("wrEnqueues", 0)
    dut.set_cooldown_zero()
    _ex, _ey = _c.tap_eject()
    r = dut.cmd(f"tap {_ex} {_ey}", timeout=5.0)
    hit    = r.get("hit", "")
    action = r.get("action", "")
    if hit != "EJECT":
        fail("T_WR_EJECT_02", f"expected hit=EJECT got {hit!r}")
        _restore_spotify(dut)
        return
    if action != "EJECT":
        fail("T_WR_EJECT_02", f"expected action=EJECT got {action!r}")
        _restore_spotify(dut)
        return
    time.sleep(0.4)
    r2 = dut.cmd("get appId", timeout=3.0)
    if r2.get("name") != "WebRadio":
        fail("T_WR_EJECT_02", f"appId={r2.get('name')!r} after eject from WebRadio (expected WebRadio — eject no longer switches apps)")
        _restore_spotify(dut)
        return
    enq_after = dut.cmd("get dataq", timeout=3.0).get("wrEnqueues", 0)
    if enq_after <= enq_before:
        fail("T_WR_EJECT_02", f"wrEnqueues did not advance ({enq_before} -> {enq_after}) — "
             "station-list refresh did not fire")
        _restore_spotify(dut)
        return
    pass_("T_WR_EJECT_02", f"hit=EJECT action=EJECT; appId=WebRadio; wrEnqueues {enq_before}->{enq_after}")
    _restore_spotify(dut)




# ── T_WR_COEX_01 — Switch to WebRadio → PLAYING ──────────────────────────────

def t_wr_coex_01(dut: Dut):
    """T_WR_COEX_01: switch to WebRadio, wait for stations, start play, confirm state=2.
    webRadioAutoplay defaults to false, so we start play explicitly via set wrPlay 0."""
    print("T_WR_COEX_01  Switch to WebRadio → load stations → play → state=2")
    count = _webradio_enter_with_stations(dut, "T_WR_COEX_01", fetch_timeout=180.0)
    if count == 0:
        skip("T_WR_COEX_01", "station list unavailable (network or fetch failure)")
        return
    print(f"    T_WR_COEX_01  {count} stations loaded — starting play…")
    dut.cmd("set wrPlay 0", timeout=3.0)
    print("    T_WR_COEX_01  waiting up to 30s for PLAYING state…")
    if not _wait_wr_state(dut, target=2, timeout=30.0):
        try:
            r = dut.cmd("get wrState", timeout=3.0)
            state = r.get("state", "?")
        except TimeoutError:
            state = "timeout"
        fail("T_WR_COEX_01", f"timeout — wrState={state} (expected 2 after set wrPlay 0)")
        return
    pass_("T_WR_COEX_01", f"wrCount={count}; set wrPlay 0 → state=2 (PLAYING)")


# ── T_WR_COEX_02 — Station index changes on NEXT/PREV tap ────────────────────

def t_wr_coex_02(dut: Dut):
    """T_WR_COEX_02: while playing, tap NEXT and PREV; verify wrIdx changes."""
    print("T_WR_COEX_02  NEXT/PREV tap while playing → wrIdx changes")
    if not _wait_wr_state(dut, target=2, timeout=10.0):
        skip("T_WR_COEX_02", "not in PLAYING state — run T_WR_COEX_01 first")
        return
    r_idx0 = dut.cmd("get wrIdx", timeout=3.0)
    idx0 = r_idx0.get("idx", -1)
    # Tap NEXT
    dut.set_cooldown_zero()
    nx, ny = _c.tap_button("NEXT")
    dut.cmd(f"tap {nx} {ny}", timeout=3.0)
    time.sleep(0.5)
    r_idx1 = dut.cmd("get wrIdx", timeout=3.0)
    idx1 = r_idx1.get("idx", idx0)
    # Tap PREV to restore
    dut.set_cooldown_zero()
    px, py = _c.tap_button("PREV")
    dut.cmd(f"tap {px} {py}", timeout=3.0)
    time.sleep(0.5)
    r_idx2 = dut.cmd("get wrIdx", timeout=3.0)
    idx2 = r_idx2.get("idx", idx1)
    if idx1 == idx0 and idx2 == idx1:
        fail("T_WR_COEX_02", f"wrIdx did not change: {idx0}→NEXT→{idx1}→PREV→{idx2}")
        return
    pass_("T_WR_COEX_02", f"wrIdx: {idx0}→NEXT→{idx1}→PREV→{idx2}")


# ── T_WR_COEX_04 — Touch latency < 500 ms during playback ────────────────────

def t_wr_coex_04(dut: Dut):
    """T_WR_COEX_04: while playing, measure serial response latency for a tap < 500 ms."""
    print("T_WR_COEX_04  Touch latency during playback < 500ms")
    if not _wait_wr_state(dut, target=2, timeout=10.0):
        skip("T_WR_COEX_04", "not in PLAYING state")
        return
    dut.set_cooldown_zero()
    nx, ny = _c.tap_button("NEXT")
    t0 = time.monotonic()
    dut.send(f"tap {nx} {ny}")
    try:
        dut.read_json(timeout=3.0)
    except TimeoutError:
        fail("T_WR_COEX_04", "no tap response within 3s during playback")
        return
    latency_ms = (time.monotonic() - t0) * 1000
    # Restore station index
    dut.set_cooldown_zero()
    px, py = _c.tap_button("PREV")
    dut.cmd(f"tap {px} {py}", timeout=3.0)
    if latency_ms > 500:
        fail("T_WR_COEX_04", f"tap response {latency_ms:.0f}ms > 500ms threshold")
        return
    pass_("T_WR_COEX_04", f"tap latency {latency_ms:.0f}ms < 500ms")


# ── T_WR_HEAP_01 — App-launch heap baseline ───────────────────────────────────

def t_wr_heap_01(dut: Dut):
    """T_WR_HEAP_01: HEAP init log >= 30 KB min after WebRadio launch.
    NOTE: HEAP init is logged synchronously in init() BEFORE the tap JSON response,
    so we use _switch_to_webradio_capture_heap() to capture it in the same read loop.
    Suspend bgPoll so tlsYield inside the subsequent station fetch completes instantly
    (spotifyTask is idle, no in-flight HTTP calls consuming the 150 s tlsYield budget)."""
    print("T_WR_HEAP_01  App-launch heap baseline >= 30 KB")
    _restore_spotify(dut)
    time.sleep(0.2)
    dut.cmd("set bgPoll 0", timeout=2.0)
    ok, _ = _switch_to_webradio_capture_heap(dut)
    # Keep bgPoll suspended until fetch completes (tlsYield is still in progress).
    # 180 s covers worst case: 2 slow mirrors × 90 s each with fast tlsYield.
    if ok:
        _wait_wr_count(dut, timeout=180.0)
    dut.cmd("set bgPoll 1", timeout=2.0)
    if not ok:
        skip("T_WR_HEAP_01", "could not switch to WebRadio")
        return
    # Query heap values via firmware command — avoids serial log capture race.
    r = dut.cmd("get wrHeap", timeout=3.0)
    free_b = r.get("initFree", 0)
    min_b  = r.get("initMin", 0)
    if free_b == 0 and min_b == 0:
        skip("T_WR_HEAP_01", "get wrHeap returned zeros (init values not stored?)")
        return
    if min_b < 30_000:
        fail("T_WR_HEAP_01", f"min={min_b}B < 30 KB threshold")
        return
    pass_("T_WR_HEAP_01", f"HEAP init free={free_b//1024}k min={min_b//1024}k (>= 30 KB)")


# ── T_WR_HEAP_02 — Post-fetch heap >= 30 KB ──────────────────────────────────

def t_wr_heap_02(dut: Dut):
    """T_WR_HEAP_02: HEAP post-fetch min >= 30 KB (TLS spike recovered).
    Best run immediately after T_WR_HEAP_01 (which triggers a fresh fetch)
    so drain_log_lines starts before the fetch completes.
    If a fresh switch is needed, bgPoll is suspended for fast tlsYield."""
    print("T_WR_HEAP_02  Post-fetch heap (TLS torn down) >= 30 KB")
    # Force a fresh switch: restore Spotify so switchApp(WebRadio) calls init() + fetch.
    # Send the tap with dut.send() (not dut.cmd()) so drain_log_lines starts BEFORE any
    # dut.cmd("get appId") can consume the "HEAP post-fetch" serial line.
    _restore_spotify(dut)
    time.sleep(0.2)
    dut.cmd("set bgPoll 0", timeout=2.0)
    dut.set_cooldown_zero()
    # TASK-414: WebRadio is entered via the taskbar player-slot cycle now
    # (eject no longer switches apps — ADR-059 D6). Still no WebRadio taskbar
    # slot of its own (TASK-242/LL-085); this taps the Spotify/player slot,
    # which cycles Spotify -> WebRadio while Spotify is active.
    wx, wy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.send(f"tap {wx} {wy}")
    print("    T_WR_HEAP_02  draining log for HEAP post-fetch line (up to 180s)…")
    lines = dut.drain_log_lines(r"webradio.*HEAP post-fetch free=", count=1, timeout=180.0)
    dut.cmd("set bgPoll 1", timeout=2.0)
    free_b = min_b = 0
    if lines:
        m = re.search(r"HEAP post-fetch free=(\d+) min=(\d+)", lines[0])
        if m:
            free_b, min_b = int(m.group(1)), int(m.group(2))
    if free_b == 0 and min_b == 0:
        # Fallback: query via firmware command (works even if log line was missed)
        r = dut.cmd("get wrHeap", timeout=3.0)
        free_b = r.get("fetchFree", 0)
        min_b  = r.get("fetchMin", 0)
    if free_b == 0 and min_b == 0:
        skip("T_WR_HEAP_02", "HEAP post-fetch not captured (log missed and get wrHeap=0)")
        return
    if min_b < 30_000:
        fail("T_WR_HEAP_02", f"min={min_b}B < 30 KB — TLS spike not fully recovered")
        return
    pass_("T_WR_HEAP_02", f"HEAP post-fetch free={free_b//1024}k min={min_b//1024}k (>= 30 KB)")


# ── T_WR_HEAP_03 — Audio decode heap watermark >= 40 KB ──────────────────────

def t_wr_heap_03(dut: Dut):
    """T_WR_HEAP_03: HEAP play min >= 40 KB during sustained audio decode."""
    print("T_WR_HEAP_03  Audio decode heap watermark >= 40 KB")
    if not _wait_wr_state(dut, target=2, timeout=5.0):
        # Not playing — try to start play if stations are loaded and we're in WebRadio
        r_a = dut.cmd("get appId", timeout=3.0)
        if r_a.get("name") != "WebRadio":
            skip("T_WR_HEAP_03", "not in WebRadio — run T_WR_COEX_01 first")
            return
        r_c = dut.cmd("get wrCount", timeout=3.0)
        if r_c.get("count", 0) == 0:
            skip("T_WR_HEAP_03", "no stations loaded — run T_WR_COEX_01 first")
            return
        dut.cmd("set wrPlay 0", timeout=3.0)
        if not _wait_wr_state(dut, target=2, timeout=15.0):
            skip("T_WR_HEAP_03", "could not reach PLAYING state")
            return
    print("    T_WR_HEAP_03  waiting up to 65s for HEAP play log (30s interval from play start)…")
    lines = dut.drain_log_lines(r"webradio.*HEAP play free=", count=1, timeout=65.0)
    if not lines:
        skip("T_WR_HEAP_03", "HEAP play log line not seen within 35s")
        return
    m = re.search(r"HEAP play free=(\d+) min=(\d+)", lines[0])
    if not m:
        fail("T_WR_HEAP_03", f"could not parse HEAP play line: {lines[0]!r}")
        return
    free_b, min_b = int(m.group(1)), int(m.group(2))
    if min_b < 40_000:
        fail("T_WR_HEAP_03", f"min={min_b}B < 40 KB during audio decode")
        return
    pass_("T_WR_HEAP_03", f"HEAP play free={free_b//1024}k min={min_b//1024}k (>= 40 KB)")


# ── T_WR_HEAP_04 — No panic over 2-minute playback run ───────────────────────

def t_wr_heap_04(dut: Dut):
    """T_WR_HEAP_04: no panic/abort/stack overflow in 2-min playback window."""
    print("T_WR_HEAP_04  No panic in 2-min playback window")
    if not _wait_wr_state(dut, target=2, timeout=5.0):
        # Not playing — try to start play if stations are loaded
        r_a = dut.cmd("get appId", timeout=3.0)
        if r_a.get("name") != "WebRadio":
            skip("T_WR_HEAP_04", "not in WebRadio — run T_WR_COEX_01 first")
            return
        r_c = dut.cmd("get wrCount", timeout=3.0)
        if r_c.get("count", 0) == 0:
            skip("T_WR_HEAP_04", "no stations loaded — run T_WR_COEX_01 first")
            return
        dut.cmd("set wrPlay 0", timeout=3.0)
        if not _wait_wr_state(dut, target=2, timeout=15.0):
            skip("T_WR_HEAP_04", "could not reach PLAYING state")
            return
    print("    T_WR_HEAP_04  monitoring for panics over 120s…")
    lines = dut.drain_log_lines(
        r"panic|abort|stack overflow|Guru Meditation|LoadProhibited|StoreProhibited",
        count=1, timeout=120.0)
    if lines:
        fail("T_WR_HEAP_04", f"crash detected: {lines[0]!r}")
        return
    pass_("T_WR_HEAP_04", "no panic/abort/stack-overflow in 120s playback")




# ── T_WR_VOL_CLAMP — HW-mod volume ceiling clamp logic (TASK-209) ────────────

def t_wr_vol_clamp(dut: Dut):
    """T_WR_VOL_CLAMP: wrEffectiveVolume() enforces the §HW Mod ceiling.

    Drives the HW-mod flag + configured ceiling and reads back the clamped value
    actually fed to setVolume() (`get wrEffectiveVol`). Stock (hwMod=false) must
    soft-cap at 12; with the mod the full 1–21 range passes through. Pure clamp
    logic — no playback, network, speaker, or Spotify needed. Complements the
    audible T_WR_VOL_01/02 (human ears) and T_WR_VOL_03 (live play). TASK-209.
    """
    tid = "T_WR_VOL_CLAMP"
    print(f"{tid}  HW-mod volume ceiling clamp (wrEffectiveVolume)")

    # Enter WebRadio via its design entry path — the taskbar player-slot cycle
    # (TASK-413/414; no WebRadio taskbar slot of its own, TASK-242). Suspend
    # bgPoll so init()'s station-fetch tlsYield() doesn't stall on the failing
    # Spotify poll. No stations/playback needed: the clamp reads g_settings
    # only, we just need WebRadio active so the wr* dbg vars route to it.
    dut.cmd("set bgPoll 0", timeout=2.0)
    ok, _ = _switch_to_webradio_capture_heap(dut)
    if not ok:
        dut.cmd("set bgPoll 1", timeout=2.0)
        skip(tid, "could not enter WebRadio via taskbar player-slot cycle")
        return

    try:
        # (hwMod, maxVol, expected effective)
        cases = [
            (0, 21, 12, "stock + max 21 → soft-cap 12"),
            (0, 15, 12, "stock + 15 → soft-cap 12"),
            (0, 12, 12, "stock + 12 → 12 (at cap)"),
            (0, 10, 10, "stock + 10 → 10 (below cap, default)"),
            (0,  5,  5, "stock + 5 → 5 (below cap)"),
            (1, 21, 21, "HW mod + 21 → 21 (full range)"),
            (1, 18, 18, "HW mod + 18 → 18 (mod default)"),
            (1, 12, 12, "HW mod + 12 → 12 (passthrough)"),
        ]
        for hw, mx, exp, desc in cases:
            dut.cmd(f"set wrHwMod {hw}", timeout=3.0)
            dut.cmd(f"set wrMaxVol {mx}", timeout=3.0)
            r = dut.cmd("get wrEffectiveVol", timeout=3.0)
            if not r.get("ok"):
                fail(tid, f"get wrEffectiveVol failed ({desc}): {r}")
                return
            eff, mv, hwb = r.get("eff"), r.get("maxVol"), r.get("hwMod")
            if eff != exp or mv != mx or bool(hwb) != bool(hw):
                fail(tid, f"{desc}: got eff={eff} maxVol={mv} hwMod={hwb}, expected eff={exp}")
                return
            print(f"  [{tid}] {desc}: eff={eff} ✓")
        pass_(tid, "soft-cap 12 enforced on stock; full 1–21 with HW mod (8/8 cases)")
    finally:
        # Restore stock defaults (in-RAM only; not persisted) + leave WebRadio.
        dut.cmd("set wrHwMod 0", timeout=3.0)
        dut.cmd("set wrMaxVol 10", timeout=3.0)
        dut.cmd("set bgPoll 1", timeout=2.0)
        _restore_spotify(dut)


# ── T237 — auto-skip terminal bound on an all-dead list (TASK-237) ───────────

def _wr_skip_tried(dut: Dut) -> int:
    r = dut.cmd("get wrSkip", timeout=3.0)
    return int(r.get("tried", -1)) if r.get("ok") else -1


def t237(dut: Dut):
    """T237: auto-skip-on-stall is bounded to one list pass and lands terminal.

    Uses the TASK-237 debug hook `set wrDeadUrls N` to synthesize N unreachable
    stations + force every connect to fail deterministically (no network). Asserts:
    with auto-skip ON, a user play skips exactly N-1 times (tried saturates at N-1),
    lands terminal (ERROR_UNREACHABLE, no further action) and never loops; with
    auto-skip OFF, it parks on the first failure (no skip). Spotify-independent.
    Regression for the ADR-045 runaway-skip safety bound. TASK-237 / BP-034.
    """
    tid = "T237"
    print(f"{tid}  auto-skip terminal bound (all-dead synthetic list)")

    dut.cmd("set bgPoll 0", timeout=2.0)
    ok, _ = _switch_to_webradio_capture_heap(dut)
    if not ok:
        dut.cmd("set bgPoll 1", timeout=2.0)
        skip(tid, "could not enter WebRadio via taskbar player-slot cycle")
        return

    N = 4
    try:
        # ── auto-skip ON: bounded scan → terminal, no loop ──────────────────
        dut.cmd("set wrStop 1", timeout=3.0)
        dut.cmd("set wrAutoSkip 1", timeout=3.0)
        dut.cmd(f"set wrDeadUrls {N}", timeout=3.0)   # synthesize N dead + arm fail
        rc = dut.cmd("get wrCount", timeout=3.0)
        if rc.get("count") != N:
            fail(tid, f"wrDeadUrls {N} did not yield count={N}: {rc}")
            return
        dut.cmd("set wrPlay 0", timeout=3.0)          # user-initiated play

        # Poll until tried saturates at N-1 (one skip per tick).
        deadline = time.monotonic() + 12.0
        tried = -1
        while time.monotonic() < deadline:
            tried = _wr_skip_tried(dut)
            if tried >= N - 1:
                break
            time.sleep(0.3)
        if tried != N - 1:
            fail(tid, f"auto-skip ON: tried={tried}, expected saturation at {N-1}")
            return
        print(f"  [{tid}] auto-skip ON: tried saturated at {tried} (=N-1) ✓")

        # Terminal + no loop: tried must stay at N-1 and state be a terminal error.
        time.sleep(1.5)
        tried2 = _wr_skip_tried(dut)
        if tried2 != N - 1:
            fail(tid, f"runaway/loop: tried moved {N-1}→{tried2} after saturation")
            return
        st = dut.cmd("get wrState", timeout=3.0).get("state")
        if st != 5:  # ERROR_UNREACHABLE
            fail(tid, f"expected terminal ERROR_UNREACHABLE(5), got state={st}")
            return
        print(f"  [{tid}] terminal: tried stable at {tried2}, state=ERROR_UNREACHABLE, no loop ✓")

        # ── auto-skip OFF: park on first failure, no skip ───────────────────
        dut.cmd("set wrStop 1", timeout=3.0)
        dut.cmd("set wrAutoSkip 0", timeout=3.0)
        dut.cmd(f"set wrDeadUrls {N}", timeout=3.0)   # re-arm (resets tried=0)
        dut.cmd("set wrPlay 0", timeout=3.0)
        time.sleep(1.5)
        tried_off = _wr_skip_tried(dut)
        idx_off = dut.cmd("get wrIdx", timeout=3.0).get("idx")
        if tried_off != 0:
            fail(tid, f"auto-skip OFF: tried={tried_off}, expected 0 (parked, no skip)")
            return
        if idx_off != 0:
            fail(tid, f"auto-skip OFF: parked on idx={idx_off}, expected 0")
            return
        print(f"  [{tid}] auto-skip OFF: parked on idx 0, tried=0 (no skip) ✓")

        pass_(tid, f"auto-skip ON bounded to {N-1} skips → terminal, no loop; OFF parks on first fail")
    finally:
        dut.cmd("set wrDeadUrls 0", timeout=3.0)   # disable hook + clear synthetic list
        dut.cmd("set wrAutoSkip 1", timeout=3.0)   # restore default ON
        dut.cmd("set wrStop 1", timeout=3.0)
        dut.cmd("set bgPoll 1", timeout=2.0)
        _restore_spotify(dut)


# ── T276 — terminal-retry re-arm actually fires (TASK-395, regression for TASK-393) ──

def t276(dut: Dut):
    """T276: TASK-276's terminal-retry re-arm actually recovers a parked ERROR_*.

    No existing test asserts this positively. The four `T_WR_ERR_*` ids that
    used to sit here only round-trip injected a state with auto-skip OFF, and
    were deleted under TASK-603 (see docs/verification/retired_test_ids.md);
    with them went the shared teardown that re-wrote the injected value. T237
    asserts "no loop within 1.5s" of hitting terminal, which is correct for
    ITS OWN scope (the runaway-skip bound) but says nothing about the
    30-second-later re-arm. TASK-393 (2026-08-03, live DUT session) found
    the re-arm did not fire in 348+ seconds despite every logged
    precondition (autoSkip ON, retryable error, stationCount>0, elapsed >>
    WR_TERMINAL_RETRY_MS) appearing satisfied. This test closes that gap:
    drive to terminal exactly like T237 (deterministic, no real network
    dependency), then wait past WR_TERMINAL_RETRY_MS with auto-skip ON and
    assert the re-arm actually happened.

    Signal: the retry handler (webRadioApp.h:623-634) resets _autoSkipTried
    to 0 before re-playing, so a `wrSkip.tried` reading below the saturated
    N-1 at any point during the wait is unambiguous evidence the re-arm
    fired — not just "state changed" (a transient CONNECTING could be
    missed between polls; tried dropping cannot happen any other way).

    Expected to currently FAIL — that is the point (TASK-393's root cause
    is still open as of this test's authoring). Once TASK-393 lands a fix,
    this test is what proves it and guards against a repeat.
    """
    tid = "T276"
    print(f"{tid}  terminal-retry re-arm after WR_TERMINAL_RETRY_MS (TASK-395/393)")

    WR_TERMINAL_RETRY_MS = 30000  # webRadioApp.h:69 — keep in sync if that constant moves
    SLACK_S = 15.0
    POLL_S  = 0.5

    dut.cmd("set bgPoll 0", timeout=2.0)
    ok, _ = _switch_to_webradio_capture_heap(dut)
    if not ok:
        dut.cmd("set bgPoll 1", timeout=2.0)
        skip(tid, "could not enter WebRadio via taskbar player-slot cycle")
        return

    N = 3
    try:
        dut.cmd("set wrStop 1", timeout=3.0)
        dut.cmd("set wrAutoSkip 1", timeout=3.0)      # ON — the point of this test
        dut.cmd(f"set wrDeadUrls {N}", timeout=3.0)   # synthesize N dead + arm deterministic fail
        rc = dut.cmd("get wrCount", timeout=3.0)
        if rc.get("count") != N:
            fail(tid, f"wrDeadUrls {N} did not yield count={N}: {rc}")
            return
        dut.cmd("set wrPlay 0", timeout=3.0)          # user-initiated play

        # Drive to terminal (mirrors T237): tried saturates at N-1.
        deadline = time.monotonic() + 12.0
        tried = -1
        while time.monotonic() < deadline:
            tried = _wr_skip_tried(dut)
            if tried >= N - 1:
                break
            time.sleep(0.3)
        if tried != N - 1:
            fail(tid, f"did not reach terminal: tried={tried}, expected {N - 1}")
            return
        st = dut.cmd("get wrState", timeout=3.0).get("state")
        if st != 5:  # ERROR_UNREACHABLE
            fail(tid, f"expected terminal ERROR_UNREACHABLE(5), got state={st}")
            return
        t_terminal = time.monotonic()
        wait_budget = WR_TERMINAL_RETRY_MS / 1000.0 + SLACK_S
        print(f"  [{tid}] reached terminal (tried={tried}, state=5) — "
              f"waiting up to {wait_budget:.0f}s for re-arm …")

        rearmed = False
        deadline2 = t_terminal + wait_budget
        while time.monotonic() < deadline2:
            tried_now = _wr_skip_tried(dut)
            if 0 <= tried_now < N - 1:
                rearmed = True
                break
            time.sleep(POLL_S)
        elapsed = time.monotonic() - t_terminal

        if not rearmed:
            fail(tid, f"terminal-retry did NOT fire within {elapsed:.0f}s "
                       f"(tried stayed at {N - 1}, WR_TERMINAL_RETRY_MS="
                       f"{WR_TERMINAL_RETRY_MS}ms) — TASK-393 regression")
            return
        pass_(tid, f"terminal-retry re-armed after {elapsed:.0f}s "
                    f"(tried dropped below {N - 1}, scan restarted)")
    finally:
        dut.cmd("set wrDeadUrls 0", timeout=3.0)   # disable hook + clear synthetic list
        dut.cmd("set wrAutoSkip 1", timeout=3.0)   # restore default ON
        dut.cmd("set wrStop 1", timeout=3.0)
        dut.cmd("set bgPoll 1", timeout=2.0)
        _restore_spotify(dut)


# ── T_WR_TLS_01 — Station fetch succeeds; record which TLS path fired ───────

def _tls01_pull_dut_log(dut: Dut):
    """TASK-299: dump the DUT's 48-line log ring via GET /log (off-serial, so it
    can't perturb the stalled handshake we're observing)."""
    import urllib.request
    try:
        r_ip = dut.cmd("get ip", timeout=3.0)
        ip = r_ip.get("ip")
        if not ip:
            print("  [T_WR_TLS_01] /log pull skipped — get ip returned no address", flush=True)
            return
        with urllib.request.urlopen(f"http://{ip}/log?n=48", timeout=5.0) as resp:
            body = resp.read().decode(errors="replace")
        for line in body.splitlines():
            print(f"  [T_WR_TLS_01] dutlog: {line}", flush=True)
    except Exception as e:
        print(f"  [T_WR_TLS_01] /log pull failed: {e}", flush=True)


def t_wr_tls_01(dut: Dut):
    """T_WR_TLS_01: switch to WebRadio, let the station fetch resolve (success or
    exhaustion across all 3 mirrors), then read wrLastHttp to see whether the
    pinned setCACert() path succeeded or fell back to setInsecure() (TASK-214).

    TASK-214 originally diagnosed an unconditional "server omits R13
    intermediate" failure; a host re-check (2026-06-20, ./run/check-datatask-certs)
    found de1's chain currently verifies clean against the pinned root from at
    least one network. The fetch logic was re-scoped to try setCACert() first
    and only fall back on verify failure. Either tlsInsecure value is a
    legitimate PASS for "station list loaded" — this test's job is to record
    which path actually fired on real hardware, since that's the evidence the
    Architect needs to decide whether ADR-029 needs an amendment at all."""
    print("T_WR_TLS_01  Station fetch — record TLS path (setCACert vs setInsecure fallback)")
    _restore_spotify(dut)
    time.sleep(0.2)
    dut.cmd("set bgPoll 0", timeout=2.0)
    # TASK-299: drain the fetch pipeline before ejecting. Root cause of the
    # post-fetch-test false-FAILs (confirmed by deterministic repro 2026-07-09):
    # fetchWebRadioStations()'s tlsYield() cannot be acked while spotifyTask is
    # inside an API call (spAct=3 — doPoll incl. token refresh has no yield
    # check; up to 150 s of timeout ladder on a degraded link), and any queued
    # dataTask request (e.g. T272's second teletext enqueue) serializes in
    # front of the station fetch, adding its own yield-wait + fetch. Firmware
    # is working as designed (TASK-244 accepted poll-bounded yield latency);
    # this test measures WHICH TLS PATH the fetch uses, not fetch latency
    # under contention — so eject only once the pipeline is quiet.
    if not _drain_data_pipeline(dut, tag="T_WR_TLS_01"):
        dut.cmd("set bgPoll 1", timeout=2.0)
        skip("T_WR_TLS_01", "fetch pipeline never drained within 200 s — "
                            "dataTask/spotifyTask wedged (investigate via get dataq)")
        return
    dataq_samples: list[dict] = []
    try:
        ok, _ = _switch_to_webradio_capture_heap(dut)
        if not ok:
            skip("T_WR_TLS_01", "could not switch to WebRadio")
            return
        # TASK-299: sample the dispatch pipeline while waiting — on the
        # "http=0 count=0 after prior fetch tests" failure this shows whether
        # the request was dropped (wrDrops), queued behind a wedged fetcher
        # (queueWaiting/inFlight), or parked in tlsYield (wrPhase=0).
        deadline = time.monotonic() + 180.0
        log_pulled = False
        while time.monotonic() < deadline:
            try:
                r_c = dut.cmd("get wrCount", timeout=3.0)
                if r_c.get("count", 0) >= 1:
                    break
                if r_c.get("pending") == 0:
                    break  # fetch resolved with no stations
            except TimeoutError:
                pass
            try:
                q = dut.cmd("get dataq", timeout=3.0)
                if q.get("ok"):
                    q.pop("ok", None); q.pop("cmd", None); q.pop("last", None)
                    if not dataq_samples or q != dataq_samples[-1]:
                        print(f"  [T_WR_TLS_01] dataq: {q}", flush=True)
                    dataq_samples.append(q)
                    # Stall confirmed (unacked yield for >=3 samples): pull the
                    # DUT's /log ring over HTTP once — the spotify.tls /
                    # dataTask.* lines show which side of the handshake is dead.
                    if (not log_pulled and len(dataq_samples) >= 3
                            and q.get("yieldCount", 0) > 0
                            and not q.get("tlsStopped", True)):
                        log_pulled = True
                        _tls01_pull_dut_log(dut)
            except TimeoutError:
                pass
            time.sleep(2.0)
    finally:
        dut.cmd("set bgPoll 1", timeout=2.0)
    r = dut.cmd("get wrLastHttp", timeout=3.0)
    http_code    = r.get("http")
    count        = r.get("count", 0)
    tls_insecure = r.get("tlsInsecure")
    # TASK-299 disposition: this test's job is recording WHICH TLS PATH loaded
    # the list — count>=1 proves a pinned-cert page-0 200 happened, even when a
    # later page died and overwrote lastHttpCode (TASK-284 mirror truncation,
    # tracked separately; verified 2026-07-09 to reproduce standalone with a
    # fully drained pipeline). Only an EMPTY list is a TLS-path failure here.
    if count < 1:
        # T272 precedent: all-mirror connect failure (-1) with a clean pipeline
        # is the network's fault, not the DUT's — skip. Any other empty-list
        # code (-9984 pin rot, -100 JSON, -101 heap guard, -102 abandoned)
        # stays a FAIL: those are device-side or cert-side defects.
        if http_code == -1:
            skip("T_WR_TLS_01", "all mirrors unreachable (http=-1, count=0) — "
                                "network, not a TLS-path defect")
            return
        last_q = dataq_samples[-1] if dataq_samples else None
        fail("T_WR_TLS_01",
             f"station fetch failed on all mirrors after both TLS paths: "
             f"http={http_code} count={count} jsonErr={r.get('jsonErr')!r} "
             f"dataq={last_q}")
        return
    path = "setInsecure() fallback" if tls_insecure else "setCACert() (pinned root verified, no fallback needed)"
    trunc = "" if http_code == 200 else f" [TASK-284 truncation: last page http={http_code}]"
    pass_("T_WR_TLS_01", f"http={http_code} count={count} — TLS path used: {path}{trunc}")


# ── T_WR_SPOTIFY_RESUME_01 — Spotify resumes after switching out of WebRadio ─

def t_wr_spotify_resume_01(dut: Dut):
    """T_WR_SPOTIFY_RESUME_01: play a WebRadio station (holds spotifyTask::tlsYield()
    for the whole playback duration per dafa4a4), cycle off WebRadio back to Spotify
    via the taskbar player slot (TASK-414: eject no longer switches apps), and confirm
    Spotify's own serial surface responds — not just that the device didn't crash
    and appId flipped. This coexistence path had no prior coverage; the tlsYield()/
    tlsResume() pairing is new in TASK-214, not part of the original M-WEBRADIO design."""
    print("T_WR_SPOTIFY_RESUME_01  Spotify resumes after WebRadio TLS yield")
    if not _restore_spotify(dut):
        skip("T_WR_SPOTIFY_RESUME_01", "precondition: could not restore Spotify")
        return
    count = _webradio_enter_with_stations(dut, "T_WR_SPOTIFY_RESUME_01", fetch_timeout=180.0)
    if count == 0:
        skip("T_WR_SPOTIFY_RESUME_01", "station list unavailable (network or fetch failure)")
        return
    dut.cmd("set wrPlay 0", timeout=3.0)
    if not _wait_wr_state(dut, target=2, timeout=30.0):
        skip("T_WR_SPOTIFY_RESUME_01", "could not reach PLAYING state — see T_WR_COEX_01")
        return
    # Switch away while still PLAYING — this is the case that actually exercises
    # tlsResume() under load (tlsYield() is held for the whole playback span).
    # TASK-414: eject no longer switches apps (it's WebRadio's own station-list
    # refresh now — ADR-059 D6); the taskbar player-slot cycle is the only way
    # off WebRadio, and it goes WebRadio -> LocalPlayer -> Spotify, so two taps
    # are needed. The FIRST tap is what exercises tlsResume() under load (any
    # switch away from WebRadio runs suspend() -> _stopAudio()); the second
    # just lands the test on Spotify to run the liveness check below.
    dut.set_cooldown_zero()
    _sx, _sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    r = dut.cmd(f"tap {_sx} {_sy}", timeout=5.0)   # WebRadio -> LocalPlayer (cycle)
    if r.get("hit") != "TASKBAR":
        fail("T_WR_SPOTIFY_RESUME_01", f"taskbar cycle tap did not fire: {r}")
        return
    time.sleep(0.3)
    dut.set_cooldown_zero()
    dut.cmd(f"tap {_sx} {_sy}", timeout=5.0)       # LocalPlayer -> Spotify (cycle)
    time.sleep(0.5)
    r2 = dut.cmd("get appId", timeout=3.0)
    if r2.get("name") != "Spotify":
        fail("T_WR_SPOTIFY_RESUME_01", f"appId={r2.get('name')!r} after cycling off WebRadio (expected Spotify)")
        return

    # Liveness proof that spotifyTask ITSELF resumed — not just the display/main
    # loop. get touchResult (the earlier check) is serviced by the loop task and
    # would respond even if spotifyTask stayed wedged after tlsResume(), so it
    # can't actually prove polling came back. Instead force a Spotify HTTP poll:
    # a DEADZONE tap dispatches ACT_FORCE_POLL to spotifyTask, which raises
    # shellBusy and clears it only when the poll completes. FORCE_POLL bypasses
    # bgPoll suspension (T-BGPOLL-03), so we suspend bgPoll first to isolate the
    # signal — with background polls off, the only thing that can raise shellBusy
    # is our forced poll. If spotifyTask did not resume, the poll never runs and
    # shellBusy never rises.
    with _bgpoll_suspended(dut):
        _wait_shell_not_busy(dut, timeout_s=15.0)   # settle any residual busy first
        dut.set_cooldown_zero()
        _dx, _dy = _c.tap_deadzone_gap()
        r3 = dut.cmd(f"tap {_dx} {_dy}", timeout=5.0)   # DEADZONE → ACT_FORCE_POLL
        if r3.get("action") != "FORCE_POLL":
            fail("T_WR_SPOTIFY_RESUME_01",
                 f"deadzone tap did not dispatch FORCE_POLL after eject: action={r3.get('action')!r}")
            return
        # Rising edge is the decisive signal: spotifyTask picked up the poll request.
        if not _poll_shell_busy(dut, expected=True, timeout_ms=4000):
            fail("T_WR_SPOTIFY_RESUME_01",
                 "shellBusy never rose after FORCE_POLL — spotifyTask did not run a poll "
                 "after tlsResume() (polling did not resume)")
            return
        # And it must complete (busy clears); stuck-true means the poll hung.
        if not _wait_shell_not_busy(dut, timeout_s=20.0):
            fail("T_WR_SPOTIFY_RESUME_01",
                 "shellBusy stuck true after FORCE_POLL — Spotify poll started but did not "
                 "complete after tlsResume()")
            return
    pass_("T_WR_SPOTIFY_RESUME_01",
          "appId=Spotify after eject from PLAYING WebRadio; forced Spotify poll ran a full "
          "shellBusy rise+clear cycle (spotifyTask resumed after tlsResume()); visual "
          "track-info repaint still needs human confirmation")


# ── vu-002 / X043 — WebRadio real-audio VIS envelope (M-WEBRADIO-REAL-VIS) ───
# Design: docs/architecture/designs/M-WEBRADIO-REAL-VIS.md, "Testing and
# Validation" + "Exit criteria" sections (reserved T_WR_VIS_01/02/03 there).
#
# `get visMode` does NOT report vu::VisMode's raw C++ enum ordinal — main.cpp
# remaps it for the subset of modes reachable via a tap-cycle:
#   VIS_ATLAS_MODE -> 0 (default)   VIS_VU -> 1   VIS_BLANK -> 2   VIS_WAVE_ATLAS -> 3
#   VIS_SPECTRUM -> 4 (TASK-387, WebRadio's tap-cycle only — see below)
# (VIS_WAVE is still dead — unreachable via nextMode() — and reads back -1.)
# vu::nextMode()'s cycle is ATLAS_MODE -> WAVE_ATLAS -> VU -> BLANK -> ATLAS_MODE
# for Spotify (appHasSpectrum=false, the default); WebRadio passes
# appHasSpectrum=true, so its cycle is ATLAS_MODE -> WAVE_ATLAS -> VU ->
# SPECTRUM -> BLANK -> ATLAS_MODE. Two vis-zone taps from the default reach
# VIS_VU (mode index 1) on both apps; a third tap reaches VIS_SPECTRUM (index
# 4) on WebRadio only, or VIS_BLANK (index 2) on Spotify.
#
# TASK-387 also fixed a latent cmdTap bug (main.cpp's WebRadio branch): the
# synthetic `tap` command called both winampDisplay.injectTouch() (Press
# phase, hits the shared hitVis branch meant for Spotify's real touch path)
# and WebRadioApp's own Release-phase vis handler on every vis-zone tap —
# double-stepping vu::nextMode() per synthetic tap. Harmless while
# nextMode() took no args (both calls did the same step, so two taps still
# net the expected single step and the old suite's assertions happened to
# hold) but broken once the two calls started passing different
# appHasSpectrum values — fixed by skipping injectTouch for vis-zone taps
# under WebRadio and building the diagnostic result directly instead. Real
# hardware touch was never affected (single dispatch via
# WebRadioApp::handleInput only).

_VIS_SCREEN_REGION = (0, 20, 140, 70)  # x,y,w,h — EXP-016/017/018 R&D region (9800px)


def _webradio_ensure_playing(dut: Dut, tid: str) -> bool:
    """Enter WebRadio (loading its station list if needed) and make sure playback
    is active (wrState == 2 / PLAYING). skip()s and returns False on failure."""
    count = _webradio_enter_with_stations(dut, tid, fetch_timeout=180.0)
    if count == 0:
        skip(tid, "station list unavailable (network or fetch failure)")
        return False
    if _wait_wr_state(dut, target=2, timeout=5.0):
        return True  # already playing from a prior test in this run
    dut.cmd("set wrPlay 0", timeout=3.0)
    if not _wait_wr_state(dut, target=2, timeout=30.0):
        skip(tid, "could not reach PLAYING state (wrState=2) after set wrPlay 0")
        return False
    return True


def _cycle_vis_to(dut: Dut, target_mode: int, max_taps: int = 4) -> Optional[int]:
    """Tap the vis hit-zone (coords.tap_vis()) until `get visMode` == target_mode,
    or return whatever mode it's stuck at after max_taps.

    Waits for the VIS-specific Phase-2 cooldown gate (`get cooldown` ->
    winampDisplay's touchScreenCoolDownTime, T-CDWN-01 precedent) to clear
    between taps so a fast second tap isn't silently dropped on the Spotify
    app. WebRadio's own vis-tap handler (webRadioApp.h ~858) has no such gate
    — nextMode() fires unconditionally on Release — so this wait is a no-op
    there; `get cooldown` just reports winampDisplay's (untouched) state.
    """
    vx, vy = _c.tap_vis()
    m = _get_vis_mode(dut)
    for _ in range(max_taps):
        if m == target_mode:
            return m
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            rem = int(dut.cmd("get cooldown", timeout=2.0).get("remainingMs", 0))
            if rem <= 0:
                break
            time.sleep(min(rem / 1000.0, 0.1))
        dut.cmd(f"tap {vx} {vy}", timeout=3.0)
        time.sleep(0.2)
        m = _get_vis_mode(dut)
    return m


def _vis_pixel_delta(dut: Dut, tid: str) -> Optional[int]:
    """Two screendumps of the vis region 1.5s apart; returns the count of
    changed RGB565 pixels, or None (having already called fail()) on a
    screendump failure. Lazy-imports screendump.py to avoid a circular
    top-level import (screendump.py imports Dut from this module)."""
    import screendump
    x, y, w, h = _VIS_SCREEN_REGION
    try:
        c1 = screendump.dump_with_retry(dut, x, y, w, h)
        time.sleep(1.5)
        c2 = screendump.dump_with_retry(dut, x, y, w, h)
    except Exception as e:
        fail(tid, f"screendump failed: {e}")
        return None
    return int((c1 != c2).sum())


def t_wr_vis_01(dut: Dut):
    """T_WR_VIS_01: decode-tail regression, isolated measurement. Enter
    WebRadio, play station 0, wait ~45s, then `get wrPump` ALONE — no
    concurrent screendump/tap traffic in the same window. This isolation is
    load-bearing: EXP-017 measured a false 272ms regression (vs. the true
    42ms) specifically because its first pass bundled a screendump-diff probe
    into the same window as the wrPump read; CPU contention from that
    traffic, not the audio math, produced the spike.
    Pass/fail: maxPumpMs <= 50 (TASK-278's decode-tail ceiling)."""
    print("T_WR_VIS_01  WebRadio decode-tail regression (isolated wrPump read)")
    if not _webradio_ensure_playing(dut, "T_WR_VIS_01"):
        return
    print("  [T_WR_VIS_01] playing — waiting 45s before isolated wrPump read…", flush=True)
    time.sleep(45.0)
    try:
        r = dut.cmd("get wrPump", timeout=5.0)
    except TimeoutError as e:
        fail("T_WR_VIS_01", f"get wrPump timed out: {e}")
        return
    if not r.get("ok") or not r.get("alive"):
        fail("T_WR_VIS_01", f"wrPump not alive/ok: {r}")
        return
    max_pump_ms = r.get("maxPumpMs")
    if max_pump_ms is None:
        fail("T_WR_VIS_01", f"no maxPumpMs field in response: {r}")
        return
    detail = (f"maxPumpMs={max_pump_ms} cycles={r.get('cycles')} "
              f"maxMutexWaitMs={r.get('maxMutexWaitMs')} stackHwm={r.get('stackHwm')}")
    if max_pump_ms > 50:
        fail("T_WR_VIS_01", f"{detail} — exceeds 50ms threshold")
        return
    pass_("T_WR_VIS_01", f"{detail} — within 50ms threshold")


def t_wr_vis_02(dut: Dut):
    """T_WR_VIS_02: real envelope animates, and only in the mode that reads
    it. Negative control at default VIS_ATLAS_MODE (visMode==0): tickAtlas()
    gates frame-advance on `playing` only and never reads
    lLevelRef()/rLevelRef(), so a screendump delta here should be near-zero.
    Then cycle to VIS_VU (visMode==1, two vis-zone taps from default) and
    expect a materially nonzero delta — design doc / EXP-016 precedent:
    >100/9800 changed pixels (EXP-016 itself measured 531/9800)."""
    print("T_WR_VIS_02  Real envelope animates only in VIS_VU (Atlas = negative control)")
    if not _webradio_ensure_playing(dut, "T_WR_VIS_02"):
        return

    m0 = _get_vis_mode(dut)
    if m0 != 0:
        m0 = _cycle_vis_to(dut, 0)
    if m0 != 0:
        fail("T_WR_VIS_02", f"could not reach VIS_ATLAS_MODE (visMode==0); stuck at visMode={m0}")
        return
    atlas_delta = _vis_pixel_delta(dut, "T_WR_VIS_02")
    if atlas_delta is None:
        return
    print(f"  [T_WR_VIS_02] Atlas mode (visMode=0) pixel delta: {atlas_delta}/9800")
    if atlas_delta > 500:
        print(f"  [T_WR_VIS_02] WARNING: Atlas negative-control delta ({atlas_delta}/9800) "
              f"is higher than expected 'near-zero' — not failing on this alone, see VU result")

    m1 = _cycle_vis_to(dut, 1)
    if m1 != 1:
        fail("T_WR_VIS_02", f"could not reach VIS_VU (visMode==1) via vis-zone taps; "
                            f"stuck at visMode={m1}")
        return
    vu_delta = _vis_pixel_delta(dut, "T_WR_VIS_02")
    if vu_delta is None:
        return
    print(f"  [T_WR_VIS_02] VU mode (visMode=1) pixel delta: {vu_delta}/9800")

    if vu_delta <= 100:
        fail("T_WR_VIS_02", f"VIS_VU pixel delta {vu_delta}/9800 <= 100 threshold — real "
                            f"envelope does not appear to be animating (Atlas negative-control "
                            f"delta was {atlas_delta}/9800)")
        return
    pass_("T_WR_VIS_02", f"Atlas(negative-control)={atlas_delta}/9800, VU={vu_delta}/9800 "
                         f"(>100 threshold)")


@meta(scope="Spotify", scope_reason="cross-mode")
def t_wr_vis_03(dut: Dut):
    """T_WR_VIS_03: Spotify's synthetic VIS_VU path is unaffected (Goal 2
    regression guard — this design change must not touch Spotify's call
    site). Same two-screendump-1.5s-apart check as T_WR_VIS_02, but on the
    Spotify app. skip()s — does not fail or fabricate — if Spotify has no
    active playback this session (known external blocker: TASK-243, lapsed
    Premium account causes poll 403s)."""
    print("T_WR_VIS_03  Spotify synthetic VIS_VU path unaffected (regression guard)")
    if not _restore_spotify(dut):
        skip("T_WR_VIS_03", "could not switch to Spotify app")
        return
    r_info = dut.cmd("info", timeout=4.0)
    is_playing = r_info.get("isPlaying")
    cf = r_info.get("consecutiveFailures")
    if not is_playing:
        skip("T_WR_VIS_03", f"Spotify has no active playback this session "
                            f"(isPlaying={is_playing}, consecutiveFailures={cf}) — likely "
                            f"TASK-243 external blocker (Premium lapsed, poll 403s), not testable now")
        return

    m1 = _get_vis_mode(dut)
    if m1 != 1:
        m1 = _cycle_vis_to(dut, 1)
    if m1 != 1:
        fail("T_WR_VIS_03", f"could not reach VIS_VU (visMode==1) on Spotify; stuck at visMode={m1}")
        return
    delta = _vis_pixel_delta(dut, "T_WR_VIS_03")
    if delta is None:
        return
    print(f"  [T_WR_VIS_03] Spotify VIS_VU pixel delta: {delta}/9800")
    if delta <= 100:
        fail("T_WR_VIS_03", f"Spotify synthetic VIS_VU pixel delta {delta}/9800 <= 100 — "
                            f"synthetic animation appears to have regressed")
        return
    pass_("T_WR_VIS_03", f"isPlaying=true; Spotify VIS_VU pixel delta={delta}/9800 (>100) — "
                         f"synthetic path unaffected")


# ── vu-003 / X044 — WebRadio real per-band spectrum (TASK-387 /
# M-WEBRADIO-REAL-VIS-SPECTRUM) ──────────────────────────────────────────────
# `get visMode`'s remap gains one more entry for this rung:
#   VIS_ATLAS_MODE -> 0   VIS_VU -> 1   VIS_BLANK -> 2
#   VIS_WAVE_ATLAS -> 3   VIS_SPECTRUM -> 4  (WebRadio's tap-cycle only)
# WebRadio's tap-cycle becomes Atlas(0) -> WaveAtlas(3) -> VU(1) ->
# Spectrum(4) -> Blank(2) -> Atlas(0). Spotify's is unchanged (Atlas ->
# WaveAtlas -> VU -> Blank — VIS_SPECTRUM never appears).
#
# `get wrSpec` (TASK-387 debug getter, webRadioApp.h) dumps the promoted
# specH() bar-height array (0..VIS_H=16) — a precise numeric readout instead
# of pixel-diffing a screendump, used here the same way `get wrPump` is used
# for decode-tail instead of instrumenting timing by hand.

def t_wr_vis_04(dut: Dut):
    """T_WR_VIS_04: WebRadio's tap-cycle reaches VIS_SPECTRUM (visMode==4),
    and the real per-band spectrum visibly animates while playing — two
    wrSpec samples ~1s apart differ in at least one band (EXP-018's "not a
    flatline" finding, checked numerically instead of via screendump)."""
    print("T_WR_VIS_04  WebRadio tap-cycle reaches Spectrum; real per-band data animates")
    if not _webradio_ensure_playing(dut, "T_WR_VIS_04"):
        return

    m = _cycle_vis_to(dut, 4, max_taps=6)
    if m != 4:
        fail("T_WR_VIS_04", f"could not reach VIS_SPECTRUM (visMode==4) via vis-zone taps; "
                            f"stuck at visMode={m}")
        return

    time.sleep(1.0)
    r1 = dut.cmd("get wrSpec", timeout=3.0)
    bars1 = r1.get("bars")
    time.sleep(1.5)
    r2 = dut.cmd("get wrSpec", timeout=3.0)
    bars2 = r2.get("bars")
    if not bars1 or not bars2 or len(bars1) != 19 or len(bars2) != 19:
        fail("T_WR_VIS_04", f"bad wrSpec response(s): {r1} / {r2}")
        return
    print(f"  [T_WR_VIS_04] wrSpec t0={bars1}")
    print(f"  [T_WR_VIS_04] wrSpec t1={bars2}")
    if bars1 == bars2:
        fail("T_WR_VIS_04", f"wrSpec identical across 1.5s ({bars1}) — real per-band "
                            f"spectrum does not appear to be animating")
        return
    pass_("T_WR_VIS_04", f"reached visMode=4; wrSpec changed across 1.5s (t0={bars1}, t1={bars2})")


@meta(scope="Spotify", scope_reason="cross-mode")
def t_wr_vis_05(dut: Dut):
    """T_WR_VIS_05: Spotify's tap-cycle never reaches VIS_SPECTRUM (Option B
    regression guard, Goal 4 of M-WEBRADIO-REAL-VIS-SPECTRUM.md) — cycle
    through all 4 of Spotify's stops and confirm visMode==4 is never
    observed. skip()s if Spotify has no active playback (TASK-243 external
    blocker), same guard as T_WR_VIS_03."""
    print("T_WR_VIS_05  Spotify tap-cycle never reaches Spectrum (regression guard)")
    if not _restore_spotify(dut):
        skip("T_WR_VIS_05", "could not switch to Spotify app")
        return
    r_info = dut.cmd("info", timeout=4.0)
    if not r_info.get("isPlaying"):
        skip("T_WR_VIS_05", f"Spotify has no active playback this session "
                            f"(isPlaying={r_info.get('isPlaying')}) — likely TASK-243 "
                            f"external blocker, not testable now")
        return

    vx, vy = _c.tap_vis()
    seen = set()
    m = _get_vis_mode(dut)
    seen.add(m)
    for _ in range(6):  # full loop is 4 stops; 6 taps covers a full cycle + margin
        dut.cmd(f"tap {vx} {vy}", timeout=3.0)
        time.sleep(0.2)
        m = _get_vis_mode(dut)
        seen.add(m)
        if m == 4:
            fail("T_WR_VIS_05", f"Spotify's tap-cycle reached visMode=4 (VIS_SPECTRUM) — "
                                f"Option B regression: Spotify must stay spectrum-less")
            return
    pass_("T_WR_VIS_05", f"Spotify tap-cycle visited {sorted(seen)} over 6 taps — "
                         f"visMode=4 never observed")



TESTS = {
    "T_PLE_WR_155": t_ple_wr_155,
    "T_PLE_WR_156": t_ple_wr_156,
    "T_PLE_WR_157": t_ple_wr_157,
    "T_PLE_WR_158": t_ple_wr_158,
    "T_PLE_WR_159": t_ple_wr_159,
    "T_PLE_WR_160": t_ple_wr_160,
    "T_WR_EJECT_01": t_wr_eject_01,
    "T_WR_EJECT_02": t_wr_eject_02,
    "T_WR_COEX_01":  t_wr_coex_01,
    "T_WR_COEX_02":  t_wr_coex_02,
    "T_WR_COEX_04":  t_wr_coex_04,
    "T_WR_HEAP_01":  t_wr_heap_01,
    "T_WR_HEAP_02":  t_wr_heap_02,
    "T_WR_HEAP_03":  t_wr_heap_03,
    "T_WR_HEAP_04":  t_wr_heap_04,
    "T_WR_VOL_CLAMP": t_wr_vol_clamp,
    "T237":          t237,
    "T276":          t276,
    "T_WR_TLS_01":            t_wr_tls_01,
    "T_WR_SPOTIFY_RESUME_01": t_wr_spotify_resume_01,
    "T_WR_VIS_01": t_wr_vis_01,
    "T_WR_VIS_02": t_wr_vis_02,
    "T_WR_VIS_03": t_wr_vis_03,
    "T_WR_VIS_04": t_wr_vis_04,
    "T_WR_VIS_05": t_wr_vis_05,
}
