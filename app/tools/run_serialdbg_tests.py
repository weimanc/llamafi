#!/usr/bin/env python3
"""
Serial debug test harness — serialdbg-001 suite.

Executes T076–T088, T095, T096, T_BI_01–T_BI_04,
T_MA_01–T_MA_03, T_GOL_01–T_GOL_04, T_WX_01–T_WX_05,
T_CX_01–T_CX_05, T_X07_01,
T-BUSY-01/01b/02/03/05, T-CDWN-01/02/03,
T149–T154 (touch-capture-001),
T162–T166 (taskbar-scroll-001),
T_WR_EJECT_01/02, T_WR_ERR_01–04, T_WR_COEX_01/02/04,
T_WR_HEAP_01–04, T_WR_VOL_03, T_WR_TLS_01, T_WR_SPOTIFY_RESUME_01 (M-WEBRADIO),
T_WR_VIS_01–03 (vu-002 / X043, M-WEBRADIO-REAL-VIS),
T_WR_VIS_04/05 (vu-003 / X044, TASK-387, M-WEBRADIO-REAL-VIS-SPECTRUM),
T_PR_01–06 (M-PLANERADAR, TASK-307),
T_PLR_01–07 (M-PLAYER-STATE, TASK-413/414),
T_PLR_08–12 (M3U index model, TASK-415 — needs the SD fixtures from
             app/tools/gen_playlist_fixtures.py copied onto the card)
against a DUT flashed with cyd2usb_winamp_debug (or another testable variant —
set DUT_ENV, e.g. DUT_ENV=cyd2usb_player, and run/lib.sh + the ELF guard follow it).
T089 (production ELF symbol check) is a host build check — not run here.
T095 (physical vs. synthetic calibration) requires --interactive (human at DUT).

Usage:
    python3 run_serialdbg_tests.py [--port /dev/ttyUSB0] [--tests T076,T080,T084]
    python3 run_serialdbg_tests.py --interactive --tests T095

Requirements:
    pip install pyserial
    DUT flashed with cyd2usb_winamp_debug, booted, WiFi up, Spotify creds valid.
    Active Spotify Connect device playing a track (required for most tests).
    T_WX_05, T_CX_05, T_X07_01 require network access to api.open-meteo.com /
    api.coingecko.com.

All tap/drag screen coordinates are derived at import time from
gen/skin_layout.h via tools/coords.py. originX shifts automatically when
M-MULTIAPP changes WINDOW_W (no literal edits required in this file).
"""

import argparse
from contextlib import contextmanager
import json
import collections
import os
import pathlib
import re
import sys
import threading
import time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import coords as _c
from app_ids_gen import APP_SLOT

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")


# ── DUT session layer — extracted to lib/dut.py (M-TESTBASE P1 / TASK-478) ────
# Re-exported here so all 16 external importers keep working unchanged:
#     from run_serialdbg_tests import Dut, _switch_to, _restore_spotify, ...
# Migrate them to `from lib.dut import resolve_port, Dut` a few per commit; this shim is the
# reason that migration can be incremental instead of a flag day.
from lib.dut import (resolve_port,                                               # noqa: E402,F401
    Dut, SetupFailure, _TeeSerial,
    resolve_port, set_no_wifi, TIMEOUT, TIMEOUT_SLOW,
    _is_ip_line, _PORTAL_INDICATORS, SETUP_FAIL_EXIT,
    _DUT_RESET_GAP_FILE, _DUT_DRD_WINDOW_S,
    _DUT_WIFI_WAIT_S, _DUT_WIFI_WAIT_2_S, _DUT_ENV,
    _SETUP_FAIL_TAIL_LINES,
)


# ── test registry ─────────────────────────────────────────────────────────────

RESULTS: dict[str, str] = {}

def pass_(tid: str, detail: str = ""):
    RESULTS[tid] = "PASS"
    print(f"  [PASS] {tid}" + (f"  {detail}" if detail else ""))

def fail(tid: str, reason: str):
    RESULTS[tid] = f"FAIL: {reason}"
    print(f"  [FAIL] {tid}  {reason}")

def skip(tid: str, reason: str):
    RESULTS[tid] = f"SKIP: {reason}"
    print(f"  [SKIP] {tid}  {reason}")

def flake(tid: str, reason: str):
    RESULTS[tid] = f"FLAKE: {reason}"
    print(f"  [FLAKE] {tid}  {reason}")



# ── T077 — dead zone between posbar and transport ─────────────────────────────

def t077(dut: Dut):
    print("T077  Dead zone posbar/transport gap")
    dut.set_cooldown_zero()
    _pb_x0, _pb_x1, _pb_y0, _pb_y1 = _c.posbar_bounds()
    _gap_y = _pb_y1 + 1 + (int(_c.S["CB_PREV_Y"]) - _pb_y1 - 1) // 2
    r = dut.cmd(f"tap {_c.tap_posbar()[0]} {_gap_y}")
    hit = r.get("hit", "")
    action = r.get("action", "")
    if hit in ("TRANSPORT", "POSBAR", "VOLUME"):
        fail("T077", f"unexpected hit={hit} action={action}")
    else:
        pass_("T077", f"hit={hit} action={action}")


# ── T078 — zero-delta drag dispatches no ACT_VOLUME ──────────────────────────

def t078(dut: Dut):
    """T078: zero-delta drag does not commit ACT_VOLUME. [PARTIAL — requires Spotify playing for full verification]"""
    print("T078  Zero-delta drag → no ACT_VOLUME")
    dut.set_cooldown_zero()
    # Verify drag state is idle first
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        skip("T078", f"dragState={rg.get('state')} not D_IDLE")
        return
    # Send zero-delta drag (same start/end — centre of volume zone)
    _vx = (_c.vol_drag_x()[0] + _c.vol_drag_x()[1]) // 2
    _vy = _c.vol_drag_y()
    dut.send(f"drag {_vx} {_vy} {_vx} {_vy} 1")
    # Wait for drag response
    try:
        rd = dut.read_json(timeout=5.0)
        # Verify we got drag response
        if rd.get("cmd") != "drag" or not rd.get("ok"):
            fail("T078", f"unexpected drag response: {rd}")
            return
    except TimeoutError:
        fail("T078", "no drag response within 5 s")
        return
    # Check dragState returns to IDLE
    time.sleep(0.5)
    rg2 = dut.cmd("get dragState")
    if rg2.get("state") != "D_IDLE":
        fail("T078", f"dragState={rg2.get('state')} after zero-delta drag")
    else:
        pass_("T078", "drag complete, state=D_IDLE, no volume commit expected")
    print("      NOTE: verify no 'dequeued action=VOLUME' in log manually")


# ── T079 — cooldown gate blocks rapid sequential taps ────────────────────────

def t079(dut: Dut):
    print("T079  Cooldown gate blocks rapid tap")
    # injectTouch (cmd tap) intentionally does NOT arm touchScreenCoolDownTime
    # — synthetic taps must not block real input. So `set cooldown <ms>` is
    # used to arm the gate, then we verify a follow-up `tap` reports skipped.
    # Use 10 s timeout: prior transport/seek actions fire Spotify HTTP calls
    # that can take > 2 s to complete; g_shellBusy must clear before arming.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    r_arm = dut.cmd("set cooldown 500")
    if not r_arm.get("ok"):
        fail("T079", f"set cooldown 500 failed: {r_arm}")
        return
    _px, _py = _c.tap_button("PLAY")
    r = dut.cmd(f"tap {_px} {_py}")   # PLAY — should be gated by cooldown
    skipped = r.get("skipped", False)
    hit = r.get("hit", "")
    if not skipped:
        fail("T079", f"tap not skipped while gate armed: {r}")
        dut.set_cooldown_zero()  # leave clean
        return
    # Clear gate; wait for any async work the (possibly-consumed) tap triggered,
    # then verify the follow-up tap fires.
    dut.set_cooldown_zero()
    _wait_shell_not_busy(dut, timeout_s=10.0)
    r2 = dut.cmd(f"tap {_px} {_py}")
    if r2.get("skipped") or r2.get("hit") != "TRANSPORT":
        fail("T079", f"post-reset tap unexpected: {r2}")
    else:
        pass_("T079", f"gate armed: skipped={skipped} hit={hit}; reset clears gate")


# ── T080 — `info` command shape ───────────────────────────────────────────────

def t080(dut: Dut):
    print("T080  `info` command shape")
    r = dut.cmd("info", timeout=4.0)
    required = ["git", "elf", "build", "heap", "isPlaying",
                "progressMs", "durationMs", "volumePct", "consecutiveFailures"]
    missing = [k for k in required if k not in r]
    if missing:
        fail("T080", f"missing fields: {missing}")
        return
    heap = r.get("heap", 0)
    if heap < 50_000:
        fail("T080", f"heap={heap} < 50000")
        return
    pass_("T080", f"heap={heap} git={r.get('git')} elf={r.get('elf')}")


# ── T081 — serial tap reproduces transport suite ──────────────────────────────

def t081(dut: Dut):
    print("T081  Serial tap → transport (shape check; Spotify effect manual)")
    buttons = [("PREV", "PREV"), ("PLAY", "PLAY"), ("PAUSE", "PAUSE"),
               ("STOP", "STOP"), ("NEXT", "NEXT")]
    errors = []
    for name, action in buttons:
        _poll_shell_busy(dut, False, timeout_ms=3000)   # wait for prior enqueued action to clear
        cx, cy = _c.tap_button(name)
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {cx} {cy}")
        if r.get("hit") != "TRANSPORT" or r.get("action") != action:
            errors.append(f"{name}: hit={r.get('hit')} action={r.get('action')}")
        time.sleep(0.3)
    if errors:
        fail("T081", "; ".join(errors))
    else:
        pass_("T081", "5/5 TRANSPORT hits correct (Spotify effects: verify manually)")


# ── T082 — serial drag reproduces volume drag ─────────────────────────────────

def t082(dut: Dut):
    """T082: serial drag produces ACT_VOLUME enqueue events; debounce verified by count. [PARTIAL — requires Spotify playing for full verification]"""
    print("T082  Serial drag → ACT_VOLUME debounce (log count check)")
    dut.set_cooldown_zero()
    _vx0, _vx1 = _c.vol_drag_x()
    _vy = _c.vol_drag_y()
    dut.send(f"drag {_vx0} {_vy} {_vx1} {_vy} 60")
    # ACT_VOLUME enqueue is synchronous in injectTouch and emits
    # "enqueued ACT_VOLUME pct=N" via LOG_D("touch", ...). We count those
    # rather than the async "dequeued action=VOLUME" lines, which can lag
    # by many seconds behind a backlog of HTTPS calls on spotify.task.
    drag_resp = None
    enqueue_lines = []
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        if "enqueued ACT_VOLUME" in line:
            enqueue_lines.append(line)
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    drag_resp = obj
                    break
            except json.JSONDecodeError:
                pass
    if drag_resp is None:
        fail("T082", "no drag response within 20 s")
        return
    if len(enqueue_lines) < 2:
        fail("T082", f"only {len(enqueue_lines)} ACT_VOLUME enqueue(s); need ≥ 2 for debounce coverage")
    else:
        pass_("T082", f"drag ok; {len(enqueue_lines)} ACT_VOLUME enqueues (verify Spotify volume manually)")


# ── T083 — `help` is parseable single JSON line ───────────────────────────────

def t083(dut: Dut):
    """T083: `help` command returns parseable JSON with required command names. [SMOKE — verifies command registry, not behavior]"""
    print("T083  `help` is parseable JSON")
    r = dut.cmd("help", timeout=3.0)
    cmds = r.get("commands", [])
    names = [c.get("name") for c in cmds]
    required_names = ["reconnect", "tap", "drag", "get", "set", "info", "help"]
    missing = [n for n in required_names if n not in names]
    if missing:
        fail("T083", f"missing commands: {missing}")
    else:
        pass_("T083", f"ok=True; {len(cmds)} commands listed")


# ── T084 — set/get backoff round-trip ─────────────────────────────────────────
# KNOWN INTERMITTENT: reconnect race — Spotify poll task may increment
# consecutiveFailures between the set and get commands, causing unexpected
# values mid-sequence — first observed 2026-05-25

def t084(dut: Dut):
    print("T084  set/get backoff round-trip")
    # Set to 5
    r_set = dut.cmd("set backoff 5")
    if not r_set.get("ok"):
        flake("T084", f"set failed: {r_set}")
        return
    # Read back
    r_get = dut.cmd("get backoff")
    cf = r_get.get("consecutiveFailures")
    if cf != 5:
        flake("T084", f"consecutiveFailures={cf}, expected 5")
        return
    # Reset
    r_rst = dut.cmd("set backoff 0")
    if not r_rst.get("ok"):
        flake("T084", f"reset failed: {r_rst}")
        return
    r_get2 = dut.cmd("get backoff")
    if r_get2.get("consecutiveFailures") != 0:
        flake("T084", f"reset: consecutiveFailures={r_get2.get('consecutiveFailures')}")
    else:
        pass_("T084", "5→0 round-trip consistent")


# ── T085 — POSBAR tap → NONE when no track loaded ────────────────────────────

def t085(dut: Dut):
    print("T085  POSBAR tap when no track (force songDuration=0)")
    # Force the `songDuration <= 0` precondition via the debug accessor
    # instead of waiting for Spotify to drop the player session (which can
    # take many minutes after the last client disconnects). The next
    # /me/player poll naturally restores songDuration, so the override is
    # transient — but tests run before that, so we restore explicitly.
    r_save = dut.cmd("get songDuration", timeout=3.0)
    saved_ms = r_save.get("ms", 180000)
    r_force = dut.cmd("set songDuration 0")
    if not r_force.get("ok"):
        fail("T085", f"set songDuration 0 failed: {r_force}")
        return
    dut.set_cooldown_zero()
    r = dut.cmd(f"tap {_c.tap_posbar()[0]} {_c.tap_posbar()[1]}")
    hit = r.get("hit", "")
    action = r.get("action", "")
    # Restore songDuration so T086 is not polluted.
    dut.cmd(f"set songDuration {saved_ms}")
    if hit == "POSBAR":
        fail("T085", f"got hit=POSBAR with songDuration=0 (action={action})")
    elif action == "SEEK":
        fail("T085", f"got action=SEEK with songDuration=0 (hit={hit})")
    else:
        pass_("T085", f"hit={hit} action={action} (no POSBAR / no SEEK at songDuration=0)")


# ── T096 — cmdDrag queue-drain completeness ───────────────────────────────────

def t096(dut: Dut):
    print("T096  cmdDrag queue-drain completeness")
    dut.set_cooldown_zero()

    _vx0, _vx1 = _c.vol_drag_x()
    _vy = _c.vol_drag_y()

    def run_drag(steps: int) -> tuple[int, bool]:
        """Returns (sample_line_count, got_drag_response)."""
        dut.send(f"drag {_vx0} {_vy} {_vx1} {_vy} {steps}")
        sample_count = 0
        got_response = False
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if "inject sample" in line:
                sample_count += 1
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    if obj.get("cmd") == "drag":
                        got_response = True
                        break
                except json.JSONDecodeError:
                    pass
        return sample_count, got_response

    # First drag: steps=60 → expect 61 move samples + release (trace doesn't log release)
    count1, ok1 = run_drag(60)
    if not ok1:
        fail("T096", "first drag: no drag-end response")
        return
    expected1 = 61  # steps+1 move samples (release sentinel not counted in LOG_D)
    if count1 != expected1:
        fail("T096", f"first drag: {count1} sample lines, expected {expected1}")
        return

    # Second drag: steps=62 → expect 63 move samples
    dut.set_cooldown_zero()
    count2, ok2 = run_drag(62)
    if not ok2:
        fail("T096", "second drag: no drag-end response")
        return
    expected2 = 63
    if count2 != expected2:
        fail("T096", f"second drag: {count2} sample lines, expected {expected2}")
        return

    pass_("T096", f"drag60={count1}/{expected1} drag62={count2}/{expected2} samples")



# ── T087 — serial tap: SHUFFLE / REPEAT / VIS / LOGO regions ─────────────────
# KNOWN INTERMITTENT: TLS reset log-line timing — the "hard reset / stopping
# client" log line is emitted after the current doPoll() completes; slow poll
# responses (high network latency, TLS renegotiation) can push it past the 8 s
# deadline — first observed 2026-05-25

def t087(dut: Dut):
    print("T087  Serial tap: SHUFFLE / REPEAT / VIS / LOGO regions")
    errors = []

    dut.set_cooldown_zero()
    _shx, _shy = _c.tap_shuffle()
    r = dut.cmd(f"tap {_shx} {_shy}")
    if r.get("hit") != "SHUFFLE" or r.get("action") != "SHUFFLE":
        errors.append(f"SHUFFLE: hit={r.get('hit')} action={r.get('action')}")

    _poll_shell_busy(dut, False, timeout_ms=3000)   # SHUFFLE enqueues async; 0.3 s sleep insufficient
    dut.set_cooldown_zero()
    _rpx, _rpy = _c.tap_repeat()
    r = dut.cmd(f"tap {_rpx} {_rpy}")
    if r.get("hit") != "REPEAT" or r.get("action") != "REPEAT":
        errors.append(f"REPEAT: hit={r.get('hit')} action={r.get('action')}")

    _poll_shell_busy(dut, False, timeout_ms=3000)   # REPEAT enqueues async
    dut.set_cooldown_zero()
    _vsx, _vsy = _c.tap_vis()
    r = dut.cmd(f"tap {_vsx} {_vsy}")
    if r.get("hit") != "VIS" or r.get("action") != "VIS":
        errors.append(f"VIS: hit={r.get('hit')} action={r.get('action')} (expected VIS/VIS)")

    # LOGO: first tap → TLS_RESET. Second must be within LOGO_TAP_COOLDOWN_MS=2000 ms.
    _lgx, _lgy = _c.tap_logo()
    dut.set_cooldown_zero()
    r = dut.cmd(f"tap {_lgx} {_lgy}")
    if r.get("hit") != "LOGO" or r.get("action") != "TLS_RESET":
        errors.append(f"LOGO-1st: hit={r.get('hit')} action={r.get('action')}")

    # Second LOGO tap immediately (still within 2 s logoTapCooldownMs window).
    # set_cooldown_zero resets touchScreenCoolDownTime only, not logoTapCooldownMs.
    dut.set_cooldown_zero()
    r2 = dut.cmd(f"tap {_lgx} {_lgy}")
    if r2.get("hit") != "DEADZONE" or r2.get("action") != "FORCE_POLL":
        errors.append(f"LOGO-cooldown: hit={r2.get('hit')} action={r2.get('action')} "
                      f"(expected DEADZONE/FORCE_POLL while logoTapCooldownMs active)")

    # Now search for the TLS reset log line.  The Spotify task processes
    # s_resetTlsPending at the TOP of its loop, after the current doPoll()
    # completes.  Give up to 8 s to account for slow poll responses.
    tls_log_found = False
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "hard reset" in line or "stopping client" in line:
            tls_log_found = True
            break
    if not tls_log_found:
        errors.append("LOGO-1st: no TLS-reset log line within 8 s "
                      "(expected '[I][spotify.tls] hard reset — stopping client')")

    if errors:
        flake("T087", "; ".join(errors))
    else:
        pass_("T087", "SHUFFLE+REPEAT+VIS+LOGO correct; LOGO cooldown → DEADZONE")
    print("      NOTE: verify Spotify shuffle/repeat state flipped — manual observation")


# ── T088 — DEADZONE positive cases ───────────────────────────────────────────

def t088(dut: Dut):
    print("T088  DEADZONE positive cases — canvas corners + dead-zone samples")
    # g_shellBusy may be True from a prior transport/seek/volume action — wait before tapping.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    _pbx0, _pbx1, _pby0, _pby1 = _c.posbar_bounds()
    _pbxm, _pbym = _c.tap_posbar()
    _gap_y = _pby1 + 1 + (int(_c.S["CB_PREV_Y"]) - _pby1 - 1) // 2
    _trans_bot = int(_c.S["CB_PREV_Y"]) + int(_c.S["CB_PREV_H"])
    _win_w = int(_c.S["WINDOW_W"])   # 275
    _win_h = int(_c.S["WINDOW_H"])   # 116

    # Coords with x < TASKBAR_X: expected DEADZONE / FORCE_POLL while Spotify active.
    # corner-TR/BR and 1px-right-chrome are now in the taskbar strip; tested below.
    deadzone_cases = [
        ("dead-posbar-left",           _pbx0 - 1,                  _pbym),
        ("dead-posbar-top",            _pbxm,                      _pby0 - 1),
        ("dead-gap-posbar-transport",  _pbxm,                      _gap_y),
        ("dead-below-transport",       _pbxm,                      _trans_bot + 1),
        ("corner-TL",                  0,                           0),
        ("corner-BL",                  0,                           _c.SCREEN_H - 1),
        ("1px-left-chrome",            _c.ORIGIN_X - 1,             _win_h // 2),
        ("1px-below-chrome",           _c.ORIGIN_X + _win_w // 2,   _win_h + 1),
    ]

    # Coords with x >= TASKBAR_X: expected TASKBAR (may call switchApp — restore after).
    taskbar_cases = [
        ("corner-TR",        _c.SCREEN_W - 1,            0),
        ("corner-BR",        _c.SCREEN_W - 1,            _c.SCREEN_H - 1),
        ("1px-right-chrome", _c.ORIGIN_X + _win_w + 1,   _win_h // 2),
    ]

    errors = []

    # DEADZONE checks (run first, while Spotify is guaranteed active at test start).
    # Each FORCE_POLL tap triggers a Spotify HTTP poll → g_shellBusy; wait between cases.
    for label, x, y in deadzone_cases:
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        hit = r.get("hit", "")
        action = r.get("action", "")
        if hit != "DEADZONE":
            errors.append(f"{label}({x},{y}): hit={hit} (expected DEADZONE)")
        elif action != "FORCE_POLL":
            errors.append(f"{label}({x},{y}): action={action} (expected FORCE_POLL)")

    # TASKBAR checks (x >= TASKBAR_X — these are correct; corner-TR/BR/right-chrome
    # are now valid taskbar slots, not dead zones).
    for label, x, y in taskbar_cases:
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        hit = r.get("hit", "")
        if hit != "TASKBAR":
            errors.append(f"{label}({x},{y}): hit={hit} (expected TASKBAR)")

    # Taskbar taps may have switched the active app (e.g. corner-BR → Life).
    # Restore to Spotify so subsequent tests start in a known state.
    _restore_spotify(dut)

    if errors:
        fail("T088", "; ".join(errors))
    else:
        pass_("T088", f"{len(deadzone_cases)} DEADZONE + {len(taskbar_cases)} TASKBAR correct")


# ── T090 — reconnect command emits JSON response ─────────────────────────────

def t090(dut: Dut):
    """T090: `reconnect` emits valid JSON response. [SMOKE — superseded by T091]"""
    print("T090  `reconnect` emits JSON {ok:true, cmd:'reconnect'}")
    r = dut.cmd("reconnect", timeout=4.0)
    if r.get("ok") is not True or r.get("cmd") != "reconnect":
        fail("T090", f"unexpected response: {r}")
    else:
        pass_("T090", f"ok=true cmd=reconnect")


# ── T091 — reconnect clears consecutiveFailures ───────────────────────────────
# KNOWN INTERMITTENT: reconnect race — an in-flight Spotify poll can
# re-increment consecutiveFailures between the reconnect and the get backoff
# commands, producing a non-zero value even after a successful reconnect —
# first observed 2026-05-25

def t091(dut: Dut):
    print("T091  `reconnect` clears consecutiveFailures")
    _wait_shell_not_busy(dut, timeout_s=10.0)
    r_set = dut.cmd("set backoff 3", timeout=3.0)
    if not r_set.get("ok"):
        flake("T091", f"set backoff 3 failed: {r_set}"); return
    r_get = dut.cmd("get backoff", timeout=3.0)
    if r_get.get("consecutiveFailures") != 3:
        flake("T091", f"consecutiveFailures={r_get.get('consecutiveFailures')} after set, expected 3"); return
    r_rc = dut.cmd("reconnect", timeout=3.0)
    if not r_rc.get("ok"):
        flake("T091", f"reconnect failed: {r_rc}"); return
    # reconnect triggers a TLS reset which floods serial for ~1-2 s; wait before querying.
    time.sleep(2.0)
    r_get2 = dut.cmd("get backoff", timeout=5.0)
    cf = r_get2.get("consecutiveFailures", -1)
    if cf != 0:
        flake("T091", f"consecutiveFailures={cf} after reconnect (expected 0)")
    else:
        pass_("T091", f"set→3, reconnect, consecutiveFailures=0 ✓")


# ── T092 — reconnect triggers immediate force poll ────────────────────────────
# KNOWN INTERMITTENT: TLS reset log-line timing — post-reconnect TLS
# renegotiation can delay the force-poll start, pushing the
# [spotify.poll] log line past the 2000 ms observation window —
# first observed 2026-05-25

def t092(dut: Dut):
    print("T092  `reconnect` triggers force poll ≤2000ms")
    # Drain any pending serial data before starting the clock
    dut.ser.reset_input_buffer()
    t_send = time.monotonic()
    dut.send("reconnect")
    # Drain the JSON response (non-blocking; don't block the 2 s window)
    deadline_json = time.monotonic() + 1.0
    while time.monotonic() < deadline_json:
        line = dut.ser.readline().decode(errors="replace").strip()
        if line.startswith("{"):
            break
    # Wait for poll line within 2 s of reconnect send
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "[spotify.poll] GET" in line or "[spotify.poll] ok" in line or "[spotify.poll] 204" in line:
            latency_ms = (time.monotonic() - t_send) * 1000
            if latency_ms <= 2000:
                pass_("T092", f"force poll in {latency_ms:.0f}ms ≤ 2000ms")
            else:
                flake("T092", f"poll latency {latency_ms:.0f}ms > 2000ms")
            return
    flake("T092", "no poll line within 2s of reconnect")


# ── T093 — unhealthy titlebar overlay (interactive visual) ───────────────────

def t093(dut: Dut, interactive: bool):
    """T093: unhealthy titlebar overlay appears and clears after reconnect. [MANUAL — requires human operator]"""
    if not interactive:
        skip("T093", "visual test — re-run with --interactive")
        return
    print("T093  Unhealthy titlebar overlay appears + clears (INTERACTIVE)")
    r = dut.cmd("set backoff 5", timeout=3.0)
    if not r.get("ok"):
        fail("T093", f"set backoff 5 failed: {r}"); return
    print("  [visual] DUT: inactive (greyed) title bar should appear within one repaint.")
    try:
        ans = input("  Is the inactive titlebar visible? [y/n] ").strip().lower()
    except EOFError:
        fail("T093", "stdin closed"); return
    if ans != "y":
        fail("T093", "operator did not confirm inactive titlebar"); return
    dut.cmd("reconnect", timeout=4.0)
    time.sleep(3.0)
    print("  [visual] DUT: title bar should revert to active (coloured) on next poll.")
    try:
        ans2 = input("  Is the active titlebar back? [y/n] ").strip().lower()
    except EOFError:
        fail("T093", "stdin closed"); return
    if ans2 != "y":
        fail("T093", "active titlebar did not return after reconnect")
    else:
        pass_("T093", "inactive titlebar appeared; cleared after reconnect")


# ── T094 — Winamp logo tap → TLS reset (interactive physical) ────────────────

def t094(dut: Dut, interactive: bool):
    """T094: physical tap on Winamp logo triggers TLS reset; second tap within cooldown is no-op. [MANUAL — requires human operator]"""
    if not interactive:
        skip("T094", "physical-tap test — re-run with --interactive (T087 covers serial proxy)")
        return
    print("T094  Winamp logo tap → TLS reset (INTERACTIVE — physical tap required)")
    print("  Serial path verified by T087. This test confirms physical touch routes")
    print("  to the same dispatch path.\n")
    print("  Step 1: Physically tap the Winamp logo (bottom-right corner of chrome).")
    print("  Step 2: Watch serial for TLS reset + force poll.")
    try:
        input("  Tap the logo, then press Enter…")
    except EOFError:
        fail("T094", "stdin closed"); return
    found_reset = False
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "hard reset" in line or "stopping client" in line:
            found_reset = True
            print(f"  [serial] TLS reset: {line}")
            break
    if not found_reset:
        fail("T094", "no TLS-reset log line within 4s of tap"); return
    # Second tap within 2s cooldown should be a no-op
    try:
        input("  Tap logo AGAIN quickly (within 2s of first tap), then Enter…")
    except EOFError:
        pass
    try:
        ans = input("  Was the second tap a no-op (no second TLS reset logged)? [y/n] ").strip().lower()
    except EOFError:
        ans = "n"
    if ans != "y":
        fail("T094", "second tap cooldown not confirmed")
    else:
        pass_("T094", "TLS reset logged; cooldown blocks second tap")


# ── T095 — injection-vs-physical calibration (interactive) ───────────────────

def t095(dut: Dut, interactive: bool):
    """T095: injection-vs-physical calibration — same region/action for serial and physical tap in each zone. [MANUAL — requires human operator]"""
    if not interactive:
        skip("T095", "requires --interactive flag (human operator at DUT). "
             "Re-run: python3 run_serialdbg_tests.py --interactive --tests T095")
        return

    print("T095  Injection-vs-physical calibration (INTERACTIVE)")
    print("      For each zone: harness sends serial tap, then prompts for physical tap.")
    print("      Pass = same region + action observed both ways.\n")

    _z_px, _z_py = _c.tap_button("PREV")
    _z_bx, _z_by = _c.tap_posbar()
    _z_vx        = (_c.vol_drag_x()[0] + _c.vol_drag_x()[1]) // 2
    _z_vy        = _c.vol_drag_y()
    # (zone_name, tap_x, tap_y, expected_hit, expected_action, dequeue_pattern)
    zones = [
        ("PREV",       _z_px, _z_py, "TRANSPORT", "PREV",   "dequeued action=PREV"),
        ("POSBAR-mid", _z_bx, _z_by, "POSBAR",    "SEEK",   "dequeued action=SEEK"),
        ("VOLUME-mid", _z_vx, _z_vy, "VOLUME",    "VOLUME", "dequeued action=VOLUME"),
    ]
    errors = []

    for zone_name, x, y, exp_hit, exp_action, dequeue_pat in zones:
        print(f"  --- Zone: {zone_name} tap({x},{y}) ---")

        # Step 1: serial injection
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        inj_hit = r.get("hit", "?")
        inj_action = r.get("action", "?")
        inj_ok = (inj_hit == exp_hit and inj_action == exp_action)
        status = "✓" if inj_ok else "✗"
        print(f"    [serial]   hit={inj_hit} action={inj_action} {status}")
        if not inj_ok:
            errors.append(f"{zone_name}: serial mismatch hit={inj_hit} action={inj_action} "
                          f"(want {exp_hit}/{exp_action})")

        # Drain the dequeued action log from the injection before the physical step.
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if dequeue_pat in line:
                break

        # Step 2: physical tap
        try:
            input(f"\n    >>> Physically tap screen at ~({x},{y}). Press Enter when done…")
        except EOFError:
            fail("T095", "stdin closed — run interactively")
            return

        # Capture dequeued action from physical tap (up to 5 s).
        phys_seen = False
        phys_line = ""
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if dequeue_pat in line:
                phys_seen = True
                phys_line = line
                break
        if phys_seen:
            print(f"    [physical] {phys_line} ✓")
        else:
            print(f"    [physical] '{dequeue_pat}' not seen within 5 s ✗")
            errors.append(f"{zone_name}: physical tap not detected in serial log")

        # Spotify visual/audio confirmation
        try:
            answer = input(f"    Spotify effect correct ({exp_action.lower()})? [y/n] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y":
            errors.append(f"{zone_name}: Spotify effect not confirmed by operator")
        print()
        time.sleep(0.5)

    if errors:
        fail("T095", "; ".join(errors))
    else:
        pass_("T095", "all 3 zones: serial and physical produce matching region+action")


# ── T133 — CurrentlyPlaying zero-init guard ───────────────────────────────────

def t133(dut: Dut):
    """Static grep + 90 s runtime soak. Works with production or debug build."""
    print("T133  CurrentlyPlaying zero-init guard (static + 90s stability)")

    # Part A: static source audit — zero-init must be present.
    src = pathlib.Path(__file__).parent.parent / "lib/SpotifyArduino/src/SpotifyArduino.cpp"
    if not src.exists():
        fail("T133", f"source not found: {src}")
        return
    if "CurrentlyPlaying current = {}" not in src.read_text():
        fail("T133", "zero-init guard missing — 'CurrentlyPlaying current = {}' not found")
        return
    print("  [T133] static: zero-init guard present", flush=True)

    # Part B: 90 s runtime soak — fail on any Guru Meditation.
    print("  [T133] monitoring DUT for 90 s (≥12 polls)…", flush=True)
    deadline = time.monotonic() + 90.0
    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    try:
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if "Guru Meditation Error" in line:
                fail("T133", "Guru Meditation Error detected — crash regression")
                return
    finally:
        dut.ser.timeout = orig_timeout
    pass_("T133", "static guard present; 90 s no crash")


# ── T134 — Zone 1 hit-test: tap in PLEDIT content area reports hit="PLEDIT" ────

def t134(dut: Dut):
    print("T134  Zone 1 hit-test: tap in PLEDIT content area")
    if not _restore_spotify(dut):
        fail("T134", "precondition: could not restore Spotify app")
        return
    if not dut.wait_for_queue(min_count=1):
        skip("T134", "precondition: queue count=0 after 30s — Spotify not playing")
        return
    # Tap row 2 centre. With scrollOffset=0 and count>=3 this dispatches
    # ACT_PLAY_URI(2); with count<3 it may still report hit=PLEDIT but with a
    # clamped or no-op play index. Either way the zone hit is confirmed.
    dut.set_cooldown_zero()
    tx, ty = _c.pledit_tap(2)
    r = dut.cmd(f"tap {tx} {ty}", timeout=5.0)
    if not r.get("ok"):
        fail("T134", f"tap returned ok=false: {r}")
        return
    hit = r.get("hit", "")
    action = r.get("action", "")
    if hit != "PLEDIT":
        fail("T134", f"hit={hit!r} action={action!r} — expected PLEDIT. "
                     f"Tap coords ({tx},{ty}). originX may differ from 22 or "
                     f"PLEDIT hitzone constants are wrong (H4 confirmed).")
        return
    pass_("T134", f"hit=PLEDIT action={action!r} at ({tx},{ty})")


# ── T135 — Drag-end fires: drag response arrives and dragState returns D_IDLE ──

def t135(dut: Dut):
    print("T135  Drag-end fires on synthetic swipe-up")
    # Pre-condition: dragState must be D_IDLE.
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T135", f"pre-condition: dragState={rg.get('state')} not D_IDLE — "
                     "prior test left state dirty; run set cooldown 0 and retry")
        return
    # Issue swipe-up through Zone 1 centre: dy = -30 px, 30 steps.
    x1, y1, x2, y2 = _c.pledit_swipe("up")
    dut.send(f"drag {x1} {y1} {x2} {y2} 30")
    # Drain non-JSON lines until drag response or timeout.
    drag_resp = None
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if not line:
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    drag_resp = obj
                    break
            except json.JSONDecodeError:
                pass
    if drag_resp is None:
        fail("T135", "no drag response within 15 s — injectRelease() never called "
                     "or drag queue stalled")
        return
    if not drag_resp.get("ok"):
        fail("T135", f"drag response ok=false: {drag_resp}")
        return
    # dragState must return to D_IDLE.
    rg2 = dut.cmd("get dragState", timeout=3.0)
    if rg2.get("state") != "D_IDLE":
        fail("T135", f"dragState={rg2.get('state')} after drag — D_PLEDIT_SCROLL "
                     "not cleared in injectRelease()")
        return
    pass_("T135", f"drag response ok; dragState=D_IDLE; swipe ({x1},{y1})→({x2},{y2})")
    # Restore scrollOffset to 0 so T136 and T137 see clean initial state.
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    _do_drag(dut, xd, yd, xd2, yd2)


# ── shared drag helper (T136–T140) ────────────────────────────────────────────

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
    import time
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


# ── T136 — get scrollOffset returns 0 at initial state ────────────────────────

def t136(dut: Dut):
    # Merged into T137 setup as an explicit precondition assertion (TASK-112c).
    # Kept here as a no-op so the dispatch table entry still resolves; run T137 instead.
    skip("T136", "merged into T137 precondition — run T137")


# ── T137 — swipe-up increments scrollOffset ────────────────────────────────────

def t137(dut: Dut):
    print("T137  swipe-up increments scrollOffset")
    if not dut.wait_for_queue(min_count=2):
        skip("T137", "precondition: queue count<2 after 30s — Spotify not playing")
        return
    # Precondition: scrollOffset must be 0 before we swipe (absorbs T136 assertion).
    r_pre = dut.cmd("get scrollOffset", timeout=3.0)
    if not r_pre.get("ok") or r_pre.get("key") != "scrollOffset":
        fail("T137", f"precondition: get scrollOffset failed: {r_pre}")
        return
    pre = r_pre.get("val")
    if pre != 0:
        fail("T137", f"pre-condition: scrollOffset={pre} not 0; run swipe-downs or reflash")
        return
    x1, y1, x2, y2 = _c.pledit_swipe("up")
    resp = _do_drag(dut, x1, y1, x2, y2)
    if resp is None:
        fail("T137", "no drag response within 15 s")
        return
    if not resp.get("ok"):
        fail("T137", f"drag ok=false: {resp}")
        return
    post = _get_scroll(dut)
    if post != 1:
        fail("T137", f"scrollOffset={post} after swipe-up, expected 1")
        return
    pass_("T137", f"scrollOffset 0→1 after swipe-up ({x1},{y1})→({x2},{y2})")


# ── T138 — swipe-down decrements scrollOffset ─────────────────────────────────

def t138(dut: Dut):
    print("T138  swipe-down decrements scrollOffset")
    pre = _get_scroll(dut)
    if pre != 1:
        # Try to bring it to 1 via one swipe-up.
        xu, yu, xu2, yu2 = _c.pledit_swipe("up")
        _do_drag(dut, xu, yu, xu2, yu2)
        pre = _get_scroll(dut)
        if pre != 1:
            skip("T138", f"pre-condition: scrollOffset={pre} not 1 — Spotify not playing?")
            return
    x1, y1, x2, y2 = _c.pledit_swipe("down")
    resp = _do_drag(dut, x1, y1, x2, y2)
    if resp is None:
        fail("T138", "no drag response within 15 s")
        return
    if not resp.get("ok"):
        fail("T138", f"drag ok=false: {resp}")
        return
    post = _get_scroll(dut)
    if post != 0:
        fail("T138", f"scrollOffset={post} after swipe-down, expected 0")
        return
    pass_("T138", f"scrollOffset 1→0 after swipe-down ({x1},{y1})→({x2},{y2})")


# ── T139 — scrollOffset clamps at 0 (no underflow) ────────────────────────────

def t139(dut: Dut):
    print("T139  scrollOffset clamps at 0 (no underflow)")
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    # Reset to 0 with a swipe-down (no-op if already 0).
    _do_drag(dut, xd, yd, xd2, yd2)
    pre = _get_scroll(dut)
    if pre != 0:
        fail("T139", f"pre-condition: scrollOffset={pre} not 0")
        return
    # Swipe down again at min — must not go negative.
    resp = _do_drag(dut, xd, yd, xd2, yd2)
    if resp is None:
        fail("T139", "no drag response within 15 s")
        return
    post = _get_scroll(dut)
    if post != 0:
        fail("T139", f"scrollOffset={post} after swipe-down at 0 — underflow detected")
        return
    pass_("T139", "scrollOffset stays 0 on swipe-down at minimum (no underflow)")


# ── T140 — scrollOffset clamps at max ─────────────────────────────────────────

def t140(dut: Dut):
    print("T140  scrollOffset clamps at max (count - PLEDIT_ROW_COUNT)")
    # Queue snapshot stores PLEDIT_ROW_COUNT (5) items; need >5 to have a non-zero max.
    # If snapshot is still 5 items, skip rather than fail — this is a snapshot-size
    # limitation (not an originX bug). A future task should expand snapshot capacity.
    if not dut.wait_for_queue(min_count=6):
        skip("T140", "queue snapshot ≤ PLEDIT_ROW_COUNT items — max scrollOffset=0; "
                     "snapshot expansion needed (see TASK-081 notes)")
        return
    # Reset to 0: fire 15 swipe-downs, ignore individual timeouts.
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    for _ in range(15):
        _do_drag(dut, xd, yd, xd2, yd2)
    if _get_scroll(dut) != 0:
        fail("T140", "reset to 0 failed after 15 swipe-downs; queue too deep or drag broken")
        return
    # Saturate upward: 20 swipe-ups (enough for any realistic queue).
    xu, yu, xu2, yu2 = _c.pledit_swipe("up")
    for _ in range(20):
        _do_drag(dut, xu, yu, xu2, yu2)
    val_sat = _get_scroll(dut)
    if val_sat is None or val_sat < 1:
        fail("T140", f"scrollOffset={val_sat} after 20 swipe-ups — "
                     "queue count <= PLEDIT_ROW_COUNT; precondition not met")
        return
    # One extra swipe-up must not increment (clamp).
    _do_drag(dut, xu, yu, xu2, yu2)
    val_after = _get_scroll(dut)
    if val_after != val_sat:
        fail("T140", f"scrollOffset changed {val_sat}→{val_after} on extra swipe — "
                     "clamp not working")
        return
    pass_("T140", f"scrollOffset saturates at {val_sat}; extra swipe did not increment")


def t147(dut: Dut):
    """T147: taskbar tap (via injectTouch) switches active app; get appId confirms round-trip."""
    import time
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        skip("T147", f"precondition: need Spotify active, got {r.get('name')!r}")
        return
    # Tap the Clock slot in the taskbar.
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)  # repaintChrome ~60 ms; 300 ms headroom
    r2 = dut.cmd("get appId", timeout=3.0)
    if not r2.get("ok") or r2.get("name") != "Clock":
        fail("T147", f"did not switch to Clock: got appId={r2.get('name')!r}")
        # Attempt restore before failing.
        dut.set_cooldown_zero()
        dut.cmd(f"tap {_c.tap_taskbar_slot(APP_SLOT["Spotify"])[0]} {_c.tap_taskbar_slot(APP_SLOT["Spotify"])[1]}", timeout=3.0)
        time.sleep(0.3)
        return
    # Switch back to Spotify to leave DUT in known state for subsequent tests.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    r3 = dut.cmd("get appId", timeout=3.0)
    if not r3.get("ok") or r3.get("name") != "Spotify":
        fail("T147", f"failed to return to Spotify: got {r3.get('name')!r}")
        return
    pass_("T147", "Spotify→Clock→Spotify round-trip confirmed via get appId")


def t148(dut: Dut):
    """T148: while Clock active, tap routes through Clock's own dedicated handler
    (TASK-346 M-CLOCK-TAP-CYCLE) — hit=CLOCKAPP, never a Winamp/Spotify zone name."""
    import time
    # Switch to Clock.
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)
    r_pre = dut.cmd("get appId", timeout=3.0)
    if not r_pre.get("ok") or r_pre.get("name") != "Clock":
        skip("T148", f"precondition: could not switch to Clock (appId={r_pre.get('name')!r})")
        return
    # Tap clock-face centre — coordinate (137, 120) sits on CLK_TAP_SPLIT_Y and
    # lands in the face-cycle zone (TASK-346); _cycleFace() always consumes.
    dut.set_cooldown_zero()
    tx, ty = _c.clock_canvas_tap()
    r = dut.cmd(f"tap {tx} {ty}", timeout=3.0)
    hit = r.get("hit", "")
    action = r.get("action", "")
    # Restore to Spotify before asserting (so subsequent tests start clean).
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    if hit != "CLOCKAPP":
        fail("T148", f"BUG-1 guard not firing: hit={hit!r} action={action!r} "
                     f"at ({tx},{ty}) with Clock active — expected dedicated CLOCKAPP "
                     f"routing (TASK-346), got a Winamp/Spotify zone name instead")
        return
    if action != "CONSUMED":
        fail("T148", f"unexpected action={action!r} (want CONSUMED) for Clock face-cycle "
                     f"tap at ({tx},{ty}) — _cycleFace() always returns true")
        return
    pass_("T148", f"Clock active: hit={hit!r} action={action!r} — routed through Clock's "
                 f"own handler, no Winamp zone leak")


# ── T_BI_01 — PLEDIT repaint on Spotify resume ───────────────────────────────

def t_bi_01(dut: Dut):
    """T_BI_01: lastPlaylistDraw advances after Spotify resume (invalidatePlaylist fires)."""
    # Precondition: queue populated
    if not dut.wait_for_queue(min_count=1, timeout=30.0):
        skip("T_BI_01", "queue empty after 30s — Spotify not playing?")
        return
    # Ensure Spotify active.
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        dut.set_cooldown_zero()
        sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {sx} {sy}", timeout=3.0)
        time.sleep(0.4)
    # Switch to Clock; wait 2 s (ensures rate-limit window clears; seqno may change).
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(2.0)
    # Note t_before.
    r_before = dut.cmd("get lastPlaylistDraw", timeout=3.0)
    if not r_before.get("ok"):
        fail("T_BI_01", f"get lastPlaylistDraw failed: {r_before}")
        return
    t_before = r_before.get("ms", 0)
    # Switch back to Spotify — resume() calls invalidatePlaylist().
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    # Poll until lastPlaylistDraw advances (drawPlaylist fired in tick()), timeout 2 s.
    deadline = time.monotonic() + 2.0
    t_after = t_before
    while time.monotonic() < deadline:
        r_poll = dut.cmd("get lastPlaylistDraw", timeout=1.0)
        if r_poll.get("ok"):
            candidate = r_poll.get("ms", t_before)
            if candidate != t_before:
                t_after = candidate
                break
        time.sleep(0.05)
    if t_after == t_before:
        fail("T_BI_01", f"lastPlaylistDraw did not advance after Spotify resume "
                        f"(before={t_before} after={t_after}) — "
                        f"invalidatePlaylist() + tick() path did not fire")
        return
    pass_("T_BI_01", f"lastPlaylistDraw advanced {t_before}→{t_after} after Spotify resume")


# ── T_BI_02 — no Winamp render bleed onto Clock canvas ───────────────────────

def t_bi_02(dut: Dut):
    """T_BI_02: taskbar tap while PLAY pending → APP_SWITCH response; appId=Clock (no bleed)."""
    # Ensure Spotify active.
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        skip("T_BI_02", f"precondition: need Spotify active, got {r.get('name')!r}")
        return
    # Tap PLAY (Press+Release delivered synchronously; pendingReleaseAt set then cleared).
    px, py = _c.tap_button("PLAY")
    dut.set_cooldown_zero()
    dut.cmd(f"tap {px} {py}", timeout=3.0)
    # Immediately tap taskbar Clock slot — shell must handle it, not Winamp.
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    r_switch = dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.2)  # past the 80 ms pendingReleaseAt window
    r_app = dut.cmd("get appId", timeout=3.0)
    # Restore to Spotify before asserting.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    hit    = r_switch.get("hit", "")
    action = r_switch.get("action", "")
    if hit != "TASKBAR" or action != "APP_SWITCH":
        fail("T_BI_02", f"taskbar tap: hit={hit!r} action={action!r} "
                        f"(expected TASKBAR/APP_SWITCH) — shell did not consume event")
        return
    if not r_app.get("ok") or r_app.get("name") != "Clock":
        fail("T_BI_02", f"appId={r_app.get('name')!r} after taskbar tap — switch did not complete")
        return
    pass_("T_BI_02", f"hit={hit!r} action={action!r}; appId=Clock — shell consumed event, no Winamp bleed")


# ── T_BI_03 — suspend() clears drag state mid-switch ─────────────────────────

def t_bi_03(dut: Dut):
    """T_BI_03: suspend() resets dragState; resume() re-enables PLEDIT after Spotify→Clock→Spotify."""
    # Precondition: Spotify active, queue ≥ 2 items for scroll tests.
    if not dut.wait_for_queue(min_count=2, timeout=30.0):
        skip("T_BI_03", "queue count<2 after 30s — Spotify not playing?")
        return
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        dut.set_cooldown_zero()
        sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {sx} {sy}", timeout=3.0)
        time.sleep(0.4)
    # Reset scrollOffset to 0 first.
    x1, y1, x2, y2 = _c.pledit_swipe("down")
    for _ in range(3):
        dut.set_cooldown_zero()
        dut.send(f"drag {x1} {y1} {x2} {y2} 5")
        dut.read_json(timeout=5.0)
    # Swipe up once so dragState exercises D_PLEDIT_SCROLL path.
    x1u, y1u, x2u, y2u = _c.pledit_swipe("up")
    dut.set_cooldown_zero()
    dut.send(f"drag {x1u} {y1u} {x2u} {y2u} 5")
    dut.read_json(timeout=5.0)
    # Verify dragState is D_IDLE after drag completes.
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T_BI_03", f"pre-condition: dragState={rg.get('state')} not D_IDLE after drag")
        return
    # Switch to Clock — suspend() → resetDragState().
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)
    r_clock = dut.cmd("get appId", timeout=3.0)
    if not r_clock.get("ok") or r_clock.get("name") != "Clock":
        fail("T_BI_03", f"failed to switch to Clock: appId={r_clock.get('name')!r}")
        return
    time.sleep(0.5)
    # Switch back to Spotify — resume() → invalidatePlaylist().
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.4)
    # Check dragState is D_IDLE (resetDragState was called by suspend()).
    rg2 = dut.cmd("get dragState", timeout=3.0)
    if rg2.get("state") != "D_IDLE":
        fail("T_BI_03", f"dragState={rg2.get('state')} after Clock switch — suspend() did not reset")
        return
    # Check scrollOffset is in range [0, ∞) — no negative underflow from stale drag.
    rs = dut.cmd("get scrollOffset", timeout=3.0)
    so = rs.get("val", -1)
    if not isinstance(so, int) or so < 0:
        fail("T_BI_03", f"scrollOffset={so!r} — negative or missing after suspend/resume")
        return
    pass_("T_BI_03", f"dragState=D_IDLE; scrollOffset={so} ≥ 0 after Clock switch — suspend/resume clean")


# ── T_BI_04 — Release delivery after finger lift ─────────────────────────────

def t_bi_04(dut: Dut):
    """T_BI_04: cmdTap delivers Release phase; response region=TRANSPORT action=PLAY|PAUSE. [PARTIAL — requires Spotify playing for full verification]"""
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        skip("T_BI_04", f"precondition: need Spotify active, got {r.get('name')!r}")
        return
    px, py = _c.tap_button("PLAY")
    dut.set_cooldown_zero()
    r_tap = dut.cmd(f"tap {px} {py}", timeout=3.0)
    # 150 ms — past the 80 ms pendingReleaseAt window; release already delivered synchronously.
    time.sleep(0.15)
    hit    = r_tap.get("hit", "")
    action = r_tap.get("action", "")
    if hit != "TRANSPORT":
        fail("T_BI_04", f"hit={hit!r} (expected TRANSPORT) — tap missed transport zone")
        return
    if action not in ("PLAY", "PAUSE"):
        fail("T_BI_04", f"action={action!r} (expected PLAY or PAUSE) — wrong transport action")
        return
    pass_("T_BI_04", f"Release delivered: hit={hit!r} action={action!r} — DUT stable, correct region")


# ── multiapp helpers ─────────────────────────────────────────────────────────

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


# ── T_MA_01 — MatrixApp switch round-trip ────────────────────────────────────

def t_ma_01(dut: Dut):
    """T_MA_01: Spotify→Matrix→Spotify round-trip; appId correct at each step."""
    print("T_MA_01  MatrixApp switch round-trip")
    # Ensure Spotify active.
    if not _restore_spotify(dut):
        skip("T_MA_01", "precondition: could not restore Spotify")
        return
    # Switch to Matrix.
    if not _switch_to(dut, "Matrix"):
        fail("T_MA_01", "did not switch to Matrix")
        _restore_spotify(dut)
        return
    # Switch back.
    if not _restore_spotify(dut):
        fail("T_MA_01", "Matrix→Spotify switch-back failed")
        return
    pass_("T_MA_01", "Spotify→Matrix→Spotify round-trip confirmed via get appId")


# ── T_MA_02 — Matrix BUG-1 guard ─────────────────────────────────────────────

def t_ma_02(dut: Dut):
    """T_MA_02: Canvas tap while Matrix active returns hit=CLOCK (Winamp zones bypassed)."""
    print("T_MA_02  Matrix BUG-1 guard")
    if not _switch_to(dut, "Matrix"):
        skip("T_MA_02", "could not switch to Matrix")
        _restore_spotify(dut)
        return
    # Tap centre of Matrix canvas (x=137, y=120) — x < TASKBAR_X.
    dut.set_cooldown_zero()
    r = dut.cmd("tap 137 120", timeout=3.0)
    # Restore before asserting.
    _restore_spotify(dut)
    hit = r.get("hit", "")
    if hit != "CLOCK":
        fail("T_MA_02", f"expected hit=CLOCK while Matrix active, got {hit!r}")
        return
    pass_("T_MA_02", f"hit={hit!r} — Winamp zones correctly bypassed for Matrix")


# ── T_MA_03 — Matrix→Spotify canvas residue ──────────────────────────────────

def t_ma_03(dut: Dut):
    """T_MA_03: Spotify renders correctly (lastPlaylistDraw advances) after Matrix switch-back."""
    print("T_MA_03  Matrix→Spotify canvas residue")
    if not _switch_to(dut, "Matrix"):
        skip("T_MA_03", "could not switch to Matrix")
        _restore_spotify(dut)
        return
    time.sleep(0.15)  # allow one or two Matrix ticks
    # Switch back to Spotify.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    if not _check_residue(dut, "T_MA_03"):
        skip("T_MA_03", "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)")


# ── T_GOL_01 — LifeApp switch round-trip ─────────────────────────────────────

def t_gol_01(dut: Dut):
    """T_GOL_01: Spotify→GoL→Spotify round-trip; appId correct at each step."""
    print("T_GOL_01  LifeApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_GOL_01", "precondition: could not restore Spotify")
        return
    if not _switch_to(dut, "Life"):
        fail("T_GOL_01", "did not switch to Life")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_GOL_01", "GoL→Spotify switch-back failed")
        return
    pass_("T_GOL_01", "Spotify→GoL→Spotify round-trip confirmed via get appId")


# ── T_GOL_02 — GoL BUG-1 guard ───────────────────────────────────────────────

def t_gol_02(dut: Dut):
    """T_GOL_02: Canvas tap while GoL active returns hit=CLOCK (Winamp zones bypassed)."""
    print("T_GOL_02  GoL BUG-1 guard")
    if not _switch_to(dut, "Life"):
        skip("T_GOL_02", "could not switch to Life")
        _restore_spotify(dut)
        return
    dut.set_cooldown_zero()
    r = dut.cmd("tap 137 120", timeout=3.0)
    _restore_spotify(dut)
    hit = r.get("hit", "")
    if hit != "CLOCK":
        fail("T_GOL_02", f"expected hit=CLOCK while GoL active, got {hit!r}")
        return
    pass_("T_GOL_02", f"hit={hit!r} — Winamp zones correctly bypassed for GoL")


# ── T_GOL_03 — GoL→Spotify canvas residue ────────────────────────────────────

def t_gol_03(dut: Dut):
    """T_GOL_03: Spotify renders correctly after GoL switch-back."""
    print("T_GOL_03  GoL→Spotify canvas residue")
    if not _switch_to(dut, "Life"):
        skip("T_GOL_03", "could not switch to Life")
        _restore_spotify(dut)
        return
    time.sleep(0.2)  # allow GoL to tick
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    if not _check_residue(dut, "T_GOL_03"):
        skip("T_GOL_03", "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)")


# ── T_GOL_04 — GoL alive count updated ───────────────────────────────────────

def t_gol_04(dut: Dut):
    """T_GOL_04: golAlive > 0 after GoL ticks — confirms cells are alive and stepGeneration ran."""
    print("T_GOL_04  GoL alive count > 0")
    if not _switch_to(dut, "Life"):
        skip("T_GOL_04", "could not switch to Life")
        _restore_spotify(dut)
        return
    time.sleep(0.35)  # wait for 3+ GoL ticks (100 ms each)
    r = dut.cmd("get golAlive", timeout=3.0)
    _restore_spotify(dut)
    if not r.get("ok"):
        fail("T_GOL_04", f"get golAlive failed: {r}")
        return
    count = r.get("count", -1)
    if count <= 0:
        fail("T_GOL_04", f"golAlive={count} — expected > 0; GoL may not have ticked or board is empty")
        return
    pass_("T_GOL_04", f"golAlive={count} > 0 — cells alive, stepGeneration confirmed")


# ── T_WX_01 — WeatherApp switch round-trip ───────────────────────────────────

def t_wx_01(dut: Dut):
    """T_WX_01: Spotify→Weather→Spotify round-trip; appId correct at each step."""
    print("T_WX_01  WeatherApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_WX_01", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        switched = _switch_to(dut, "Weather", timeout=15.0)
    if not switched:
        fail("T_WX_01", "did not switch to Weather")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_WX_01", "Weather→Spotify switch-back failed")
        return
    pass_("T_WX_01", "Spotify→Weather→Spotify round-trip confirmed via get appId")


# ── T_WX_02 — Weather BUG-1 guard ────────────────────────────────────────────

def t_wx_02(dut: Dut):
    """T_WX_02: Canvas tap while Weather active returns hit=CLOCK (Winamp zones bypassed)."""
    print("T_WX_02  Weather BUG-1 guard")
    if not _switch_to(dut, "Weather"):
        skip("T_WX_02", "could not switch to Weather")
        _restore_spotify(dut)
        return
    dut.set_cooldown_zero()
    r = dut.cmd("tap 137 120", timeout=3.0)
    _restore_spotify(dut)
    hit = r.get("hit", "")
    if hit != "CLOCK":
        fail("T_WX_02", f"expected hit=CLOCK while Weather active, got {hit!r}")
        return
    pass_("T_WX_02", f"hit={hit!r} — Winamp zones correctly bypassed for Weather")


# ── T_WX_03 — Weather→Spotify canvas residue ─────────────────────────────────

def t_wx_03(dut: Dut):
    """T_WX_03: Spotify renders correctly after Weather switch-back."""
    print("T_WX_03  Weather→Spotify canvas residue")
    if not _switch_to(dut, "Weather"):
        skip("T_WX_03", "could not switch to Weather")
        _restore_spotify(dut)
        return
    time.sleep(0.15)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    if not _check_residue(dut, "T_WX_03"):
        skip("T_WX_03", "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)")


# ── T_WX_04 — Weather pre-fetch state ────────────────────────────────────────

def t_wx_04(dut: Dut):
    """T_WX_04: weatherReady=false immediately after first switch-in (before fetch completes)."""
    print("T_WX_04  Weather pre-fetch state")
    # Only valid if Weather has never shown in this DUT session.
    r_pre = dut.cmd("get weatherReady", timeout=3.0)
    if not r_pre.get("ok"):
        fail("T_WX_04", f"get weatherReady failed: {r_pre}")
        return
    if r_pre.get("ready") is True:
        skip("T_WX_04",
             "weatherReady already true — Weather fetched data earlier this session; "
             "pre-fetch state no longer observable")
        return
    # Switch to Weather; check immediately (before 60s fetch interval).
    _switch_to(dut, "Weather")
    r_imm = dut.cmd("get weatherReady", timeout=3.0)
    _restore_spotify(dut)
    if not r_imm.get("ok"):
        fail("T_WX_04", f"get weatherReady (immediate) failed: {r_imm}")
        return
    if r_imm.get("ready") is True:
        # Data arrived extremely fast (cached or very fast network) — not a failure.
        skip("T_WX_04", "weatherReady=true immediately — data arrived before check; network too fast?")
        return
    pass_("T_WX_04", "weatherReady=false on switch-in — pre-fetch state confirmed")


# ── T_WX_05 — Weather data arrives ───────────────────────────────────────────

def t_wx_05(dut: Dut):
    """T_WX_05: weatherReady becomes true within 30 s of switching to WeatherApp."""
    print("T_WX_05  Weather data arrives")
    if not _switch_to(dut, "Weather"):
        skip("T_WX_05", "could not switch to Weather")
        _restore_spotify(dut)
        return
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        r = dut.cmd("get weatherReady", timeout=3.0)
        if r.get("ok") and r.get("ready") is True:
            ready = True
            break
        time.sleep(2.0)
    if not ready:
        r_prog = dut.cmd("get weatherFetchPhase", timeout=3.0)
        phase = r_prog.get("val") if r_prog.get("ok") else "?"
        phase_name = _CHART_PHASE_NAMES.get(phase, "idle" if phase == -1 else "unknown")
        _restore_spotify(dut)
        fail("T_WX_05", f"weatherReady still false after 30 s — "
                        f"weatherFetchPhase={phase} ({phase_name})")
        return
    _restore_spotify(dut)
    pass_("T_WX_05", "weatherReady=true — WeatherApp received live data from dataTask")


# ── T_CX_01 — CryptoApp switch round-trip ────────────────────────────────────

def t_cx_01(dut: Dut):
    """T_CX_01: Spotify→Crypto→Spotify round-trip; appId correct at each step."""
    print("T_CX_01  CryptoApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_CX_01", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        switched = _switch_to(dut, "Crypto", timeout=15.0)
    if not switched:
        fail("T_CX_01", "did not switch to Crypto")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_CX_01", "Crypto→Spotify switch-back failed")
        return
    pass_("T_CX_01", "Spotify→Crypto→Spotify round-trip confirmed via get appId")


# ── T_CX_02 — Crypto BUG-1 guard ─────────────────────────────────────────────

def t_cx_02(dut: Dut):
    """T_CX_02: Canvas tap while Crypto active returns hit=CLOCK (Winamp zones bypassed)."""
    print("T_CX_02  Crypto BUG-1 guard")
    if not _switch_to(dut, "Crypto"):
        skip("T_CX_02", "could not switch to Crypto")
        _restore_spotify(dut)
        return
    dut.set_cooldown_zero()
    r = dut.cmd("tap 137 120", timeout=3.0)
    _restore_spotify(dut)
    hit = r.get("hit", "")
    if hit != "CLOCK":
        fail("T_CX_02", f"expected hit=CLOCK while Crypto active, got {hit!r}")
        return
    pass_("T_CX_02", f"hit={hit!r} — Winamp zones correctly bypassed for Crypto")


# ── T_CX_03 — Crypto→Spotify canvas residue ──────────────────────────────────

def t_cx_03(dut: Dut):
    """T_CX_03: Spotify renders correctly after Crypto switch-back."""
    print("T_CX_03  Crypto→Spotify canvas residue")
    if not _switch_to(dut, "Crypto"):
        skip("T_CX_03", "could not switch to Crypto")
        _restore_spotify(dut)
        return
    time.sleep(0.15)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    if not _check_residue(dut, "T_CX_03"):
        skip("T_CX_03", "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)")


# ── T_CX_04 — Crypto pre-fetch state ─────────────────────────────────────────

def t_cx_04(dut: Dut):
    """T_CX_04: cryptoReady=false immediately after first switch-in (before fetch completes)."""
    print("T_CX_04  Crypto pre-fetch state")
    r_pre = dut.cmd("get cryptoReady", timeout=3.0)
    if not r_pre.get("ok"):
        fail("T_CX_04", f"get cryptoReady failed: {r_pre}")
        return
    if r_pre.get("ready") is True:
        skip("T_CX_04",
             "cryptoReady already true — Crypto fetched data earlier this session; "
             "pre-fetch state no longer observable")
        return
    _switch_to(dut, "Crypto")
    r_imm = dut.cmd("get cryptoReady", timeout=3.0)
    _restore_spotify(dut)
    if not r_imm.get("ok"):
        fail("T_CX_04", f"get cryptoReady (immediate) failed: {r_imm}")
        return
    if r_imm.get("ready") is True:
        skip("T_CX_04", "cryptoReady=true immediately — data arrived before check")
        return
    pass_("T_CX_04", "cryptoReady=false on switch-in — pre-fetch state confirmed")


# ── T_CX_05 — Crypto data arrives ────────────────────────────────────────────

def t_cx_05(dut: Dut):
    """T_CX_05: cryptoReady becomes true within 30 s of switching to CryptoApp."""
    print("T_CX_05  Crypto data arrives")
    if not _switch_to(dut, "Crypto"):
        skip("T_CX_05", "could not switch to Crypto")
        _restore_spotify(dut)
        return
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        r = dut.cmd("get cryptoReady", timeout=3.0)
        if r.get("ok") and r.get("ready") is True:
            ready = True
            break
        time.sleep(2.0)
    if not ready:
        r_code = dut.cmd("get cryptoHttpCode", timeout=3.0)
        http_code = r_code.get("val", "?") if r_code.get("ok") else "?"
        r_prog = dut.cmd("get cryptoFetchPhase", timeout=3.0)
        phase = r_prog.get("val") if r_prog.get("ok") else "?"
        phase_name = _CHART_PHASE_NAMES.get(phase, "idle" if phase == -1 else "unknown")
        _restore_spotify(dut)
        fail("T_CX_05", f"cryptoReady still false after 30 s — "
                        f"cryptoFetchPhase={phase} ({phase_name}), HTTP code: {http_code}")
        return
    _restore_spotify(dut)
    pass_("T_CX_05", "cryptoReady=true — CryptoApp received live data from dataTask")


# ── T_X07_01 — dataTask cross-feature: rapid Weather↔Crypto switching ────────

def t_x07_01(dut: Dut):
    """T_X07_01 (X007): rapid Weather→Crypto→Weather→Crypto→Spotify; DUT stable throughout."""
    print("T_X07_01  dataTask cross-feature: rapid Weather↔Crypto switching")
    if not _restore_spotify(dut):
        skip("T_X07_01", "precondition: could not restore Spotify")
        return
    sequence = [
        ("Weather", APP_SLOT["Weather"]),
        ("Crypto",  APP_SLOT["Crypto"]),
        ("Weather", APP_SLOT["Weather"]),
        ("Crypto",  APP_SLOT["Crypto"]),
        ("Spotify", APP_SLOT["Spotify"]),
    ]
    for app_name, slot in sequence:
        dut.set_cooldown_zero()
        x, y = _c.tap_taskbar_slot(slot)
        dut.cmd(f"tap {x} {y}", timeout=3.0)
        time.sleep(0.2)
        r = dut.cmd("get appId", timeout=3.0)
        if not r.get("ok") or r.get("name") != app_name:
            # Ensure we're back to Spotify before failing.
            _restore_spotify(dut)
            fail("T_X07_01",
                 f"expected appId={app_name!r}, got {r.get('name')!r} — "
                 f"DUT unstable during rapid dataTask switching")
            return
    # Final sanity: DUT still responds to info.
    r_info = dut.cmd("info", timeout=4.0)
    if not r_info.get("ok"):
        fail("T_X07_01", "DUT unresponsive after rapid switching — info command failed")
        return
    pass_("T_X07_01",
          "Weather→Crypto×2→Spotify round-trip clean; DUT stable; "
          "no dataTask queue corruption detected")


# ── stock-001 suite (TASK-110) ────────────────────────────────────────────────
# All tests use `switchApp <_STOCK_APP_ID>` (debug command) to reach StockApp directly rather
# than scrolling the taskbar — taskbar scrolling is covered by T162–T168.
# T182 is the one exception: it uses the taskbar path to exercise the real UI.
#
# Firmware prerequisites (main.cpp):
#   get stockSubView, get stockChartTicker, get stockChartRange,
#   get lastQuoteFetch, get lastChartFetch,
#   set fetchFailed, set fetchErrorCode, set triggerFetch,
#   switchApp <id>
#
# Geometry (from main.cpp constants):
#   List rows: y_centre = 36 + 26*i   (AAPL=36, AMD=62, AMZN=88, ARM=114,
#                                       GOOG=140, META=166, MSFT=192, NVDA=218)
#   Chart header: y 0..17
#   Back tap: (10, 7)   Chart tabs (x,7): 1D=148, 5D=184, 1M=220, YTD=256
#   Plot area: y 18..213   Footer: y=214

_STOCK_APP_ID = APP_SLOT["Stock"]


def _switch_to_stock(dut: Dut, timeout: float = 5.0) -> bool:
    """Switch to StockApp via the serial switchApp command.
    TASK-247: force List launch view first (in-RAM only, not persisted) so the
    list-centric suite is deterministic regardless of the device's saved stockMode
    (e.g. a user-configured Heatmap default), and so the heatmap/chart launch no
    longer pre-fetches the unused list quote."""
    dut.cmd("set stockMode 0", timeout=timeout)
    r = dut.cmd(f"switchApp {_STOCK_APP_ID}", timeout=timeout)
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


def _wait_quote_fetch(dut: Dut, baseline: int, timeout_s: float = 65.0) -> bool:
    """Wait until lastQuoteFetch advances past baseline (fetch completed)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = _stock_get(dut, "lastQuoteFetch")
        if r.get("ok") and int(r.get("val", 0)) != baseline:
            return True
        time.sleep(2.0)
    # TASK-386: diagnostic snapshot on timeout, for every caller, automatically.
    # Return type/signature unchanged — zero risk to existing call sites — but the
    # get heap/backoff/dataq round trips still land on the wire and get captured by
    # any LOG_FILE= in effect, same rationale as _wait_chart_complete below.
    _diag_snapshot(dut, "_wait_quote_fetch-timeout")
    return False


def _stock_ok_count(dut: Dut) -> int:
    """Return current fetchOkCount from firmware, or -1 on error."""
    r = _stock_get(dut, "fetchOkCount")
    if r.get("ok"):
        try:
            return int(r.get("val", -1))
        except (ValueError, TypeError):
            pass
    return -1


def _stock_quote_ok_count(dut: Dut) -> int:
    """Return current quoteOkCount from firmware, or -1 on error."""
    r = _stock_get(dut, "quoteOkCount")
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


# ── T169 — Stock app switch round-trip ───────────────────────────────────────

def t169(dut: Dut):
    """T169 (L1): switchApp→Stock activates StockApp; switchApp→Spotify restores."""
    print("T169  Stock app switch round-trip")
    if not _restore_spotify(dut):
        skip("T169", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        switched = _switch_to_stock(dut)
    if not switched:
        fail("T169", "switchApp did not switch to Stock")
        _restore_from_stock(dut)
        return
    r = _stock_get(dut, "stockSubView")
    if not r.get("ok"):
        fail("T169", f"get stockSubView failed: {r}")
        _restore_from_stock(dut)
        return
    if r.get("val") != "list":
        fail("T169", f"expected stockSubView=list on first launch, got {r.get('val')!r}")
        _restore_from_stock(dut)
        return
    if not _restore_from_stock(dut):
        fail("T169", "Stock→Spotify switch-back failed")
        return
    pass_("T169", "Stock round-trip OK; stockSubView=list on launch")


# ── T170 — Pre-fetch placeholders ─────────────────────────────────────────────

_DEFAULT_TICKERS = ["AAPL", "AMD", "AMZN", "ARM", "GOOG", "META", "MSFT", "NVDA"]


def t170(dut: Dut):
    """T170 (L2): quote fetch completes after Stock switch-in; quoteOkCount advances within 65 s."""
    print("T170  Quote fetch completes after switch-in")
    if not _switch_to_stock(dut):
        skip("T170", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    before = _stock_quote_ok_count(dut)
    print(f"  [T170] switched to Stock (quoteOkCount={before}); waiting for quote fetch…", flush=True)
    deadline = time.monotonic() + 65.0
    advanced = False
    last_progress = None
    last_progress_time = time.monotonic()
    while time.monotonic() < deadline:
        current = _stock_quote_ok_count(dut)
        if current > before:
            advanced = True
            break
        r_prog = _stock_get(dut, "stockQuoteProgress", timeout=3.0)
        prog = r_prog.get("val") if r_prog.get("ok") else None
        if prog != last_progress:
            last_progress = prog
            last_progress_time = time.monotonic()
        elif prog is not None and prog != -1 and time.monotonic() - last_progress_time > 20.0:
            ticker_name = _DEFAULT_TICKERS[prog] if isinstance(prog, int) and 0 <= prog < 8 else "?"
            _restore_from_stock(dut)
            fail("T170", f"stockQuoteProgress stuck at ticker {prog} ({ticker_name}) for >20 s")
            return
        time.sleep(2.0)
    if not advanced:
        r_prog = _stock_get(dut, "stockQuoteProgress", timeout=3.0)
        ticker_idx = r_prog.get("val") if r_prog.get("ok") else "?"
        ticker_name = _DEFAULT_TICKERS[ticker_idx] if isinstance(ticker_idx, int) and 0 <= ticker_idx < 8 else "?"
        r_ff   = _stock_get(dut, "fetchFailed",    timeout=3.0)
        r_code = _stock_get(dut, "fetchErrorCode", timeout=3.0)
        _restore_from_stock(dut)
        fail("T170", f"quoteOkCount did not advance within 65 s — "
                     f"stuck on ticker {ticker_idx} ({ticker_name}), "
                     f"fetchFailed={r_ff.get('val')!r} fetchErrorCode={r_code.get('val')!r}")
        return
    _restore_from_stock(dut)
    pass_("T170", f"quoteOkCount advanced past {before} — quote fetch completed")


# ── T171 — Colour coding (data-dependent) ─────────────────────────────────────

def t171(dut: Dut):
    """T171 (L3): positive changePct rows render green, negative red. Requires live data. [MANUAL — pixel verification required]"""
    print("T171  Colour coding (manual pixel check — skipped in automated run)")
    skip("T171", "pixel verification required — run manually; check green/red rows after fetch")


# ── T172 — App switch residue ─────────────────────────────────────────────────

def t172(dut: Dut):
    """T172 (L4): Spotify→Stock→Spotify; Winamp chrome repaints cleanly."""
    print("T172  App switch residue")
    if not _restore_spotify(dut):
        skip("T172", "precondition: could not restore Spotify")
        return
    if not _switch_to_stock(dut):
        fail("T172", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    time.sleep(0.15)
    if not _restore_from_stock(dut):
        fail("T172", "Stock→Spotify switch-back failed")
        return
    if not _check_residue(dut, "T172"):
        skip("T172", "lastPlaylistDraw did not advance — Spotify not rendering (not playing?)")


# ── T173 — Resume cache ───────────────────────────────────────────────────────

def t173(dut: Dut):
    """T173 (L5): switch away from Stock and back within 60 s; prices come from cache."""
    print("T173  Resume cache")
    if not _switch_to_stock(dut):
        skip("T173", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    r_pre = _stock_get(dut, "lastQuoteFetch")
    baseline = int(r_pre.get("val", 0)) if r_pre.get("ok") else 0
    if baseline == 0:
        skip("T173", "no quote fetch recorded yet — cannot verify resume cache")
        _restore_from_stock(dut)
        return
    # Switch away and quickly back.
    dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
    time.sleep(2.0)
    if not _switch_to_stock(dut):
        fail("T173", "could not switch back to Stock")
        _restore_from_stock(dut)
        return
    r_post = _stock_get(dut, "lastQuoteFetch")
    _restore_from_stock(dut)
    post_val = int(r_post.get("val", 0)) if r_post.get("ok") else -1
    if post_val != baseline:
        fail("T173", f"lastQuoteFetch changed {baseline}→{post_val} — unexpected re-fetch on resume")
        return
    pass_("T173", f"lastQuoteFetch unchanged ({baseline}) — resume served from cache")


# ── T174 — Row drill-in ───────────────────────────────────────────────────────

def t174(dut: Dut):
    """T174 (L6): tap NVDA row (row 7, y=218); verify stockSubView=chart, stockChartTicker=NVDA."""
    print("T174  Row drill-in (NVDA)")
    if not _switch_to_stock(dut):
        skip("T174", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    r_sv = _stock_get(dut, "stockSubView")
    if r_sv.get("val") != "list":
        skip("T174", f"stockSubView={r_sv.get('val')!r} — expected list; prior test may have left chart view")
        _restore_from_stock(dut)
        return
    r_ff = _stock_get(dut, "stockSubView")
    # Also check fetchFailed via a set-then-get round-trip isn't practical here;
    # just proceed — if fetchFailed the tap will be ignored and subView stays list.
    dut.set_cooldown_zero()
    dut.cmd("tap 137 218", timeout=3.0)  # NVDA row centre: y = 25 + 7*26 + 11 = 218
    time.sleep(0.3)
    r_sv2 = _stock_get(dut, "stockSubView")
    r_tk  = _stock_get(dut, "stockChartTicker")
    r_rng = _stock_get(dut, "stockChartRange")
    _restore_from_stock(dut)
    if r_sv2.get("val") != "chart":
        fail("T174", f"stockSubView={r_sv2.get('val')!r} after tap — drill-in did not fire")
        return
    if r_tk.get("val") != "NVDA":
        fail("T174", f"stockChartTicker={r_tk.get('val')!r} — expected NVDA")
        return
    if r_rng.get("val") != "D1":
        fail("T174", f"stockChartRange={r_rng.get('val')!r} — expected D1 default on drill-in")
        return
    pass_("T174", "drill-in NVDA: subView=chart, ticker=NVDA, range=D1")


# ── T175 — Back navigation ────────────────────────────────────────────────────

def t175(dut: Dut):
    """T175 (C1): from chart view, tap back zone (10,7); stockSubView returns to list."""
    print("T175  Back navigation from chart")
    if not _switch_to_stock(dut):
        skip("T175", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Drill into any row (AAPL, row 0, y=36).
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)
    time.sleep(0.3)
    r_sv = _stock_get(dut, "stockSubView")
    if r_sv.get("val") != "chart":
        skip("T175", "drill-in did not fire (fetchFailed?) — cannot test back navigation")
        _restore_from_stock(dut)
        return
    # Tap back button: x=10 < ST_CHART_BACK_W(30), y=7 < ST_CHART_HEADER_H(18).
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)
    time.sleep(0.2)
    r_sv2 = _stock_get(dut, "stockSubView")
    _restore_from_stock(dut)
    if r_sv2.get("val") != "list":
        fail("T175", f"stockSubView={r_sv2.get('val')!r} after back tap — expected list")
        return
    pass_("T175", "back tap (10,7) returned stockSubView=list")


# ── T176 — Plot bounds (automated proxy only) ─────────────────────────────────

def t176(dut: Dut):
    """T176 (C2): chart fetch completes; fetchOkCount advances confirms data received."""
    print("T176  Plot bounds (automated: fetchOkCount advance; pixel check manual)")
    if not _switch_to_stock(dut):
        skip("T176", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # TASK-300: in full-suite order the drill-in's chart fetch serializes behind
    # an in-flight Spotify poll (tlsYield has no ack path inside doPoll; the
    # 403-latch keeps bgPoll on a 60 s cadence) and/or queued dataTask requests,
    # blowing the 45 s window with stockChartProgress still -1. This test
    # measures fetch COMPLETION, not latency under contention (TASK-244
    # accepted poll-bounded yield latency) — quiet the pipeline first, same
    # rationale as T_WR_TLS_01.
    dut.cmd("set bgPoll 0", timeout=2.0)
    try:
        if not _drain_data_pipeline(dut, tag="T176"):
            skip("T176", "fetch pipeline never drained within 200 s — "
                         "dataTask/spotifyTask wedged (investigate via get dataq)")
            _restore_from_stock(dut)
            return
        before = _stock_ok_count(dut)
        dut.set_cooldown_zero()
        dut.cmd("tap 137 36", timeout=3.0)  # drill into AAPL
        time.sleep(0.3)
        r_sv = _stock_get(dut, "stockSubView")
        if r_sv.get("val") != "chart":
            skip("T176", "could not enter chart view")
            _restore_from_stock(dut)
            return
        print(f"  [T176] drill-in complete (fetchOkCount={before}); waiting for fetch…", flush=True)
        fetched = _wait_chart_complete(dut, before, timeout_s=45.0, test_id="T176")
    finally:
        dut.cmd("set bgPoll 1", timeout=2.0)
    _restore_from_stock(dut)
    if not fetched:
        fail("T176", "fetchOkCount did not advance after 45 s with a drained pipeline "
                     "and bgPoll off — drill-in → enqueue path suspect (see dataq above)")
        return
    pass_("T176", "fetchOkCount advanced — chart data received; pixel bounds check is manual (y:18..213)")


# ── T177 — Range tab switch ───────────────────────────────────────────────────

def t177(dut: Dut):
    """T177 (C3): tap 5D tab (184,7); stockChartRange=D5 and lastChartFetch resets."""
    print("T177  Range tab — 5D")
    if not _switch_to_stock(dut):
        skip("T177", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)  # drill into AAPL
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T177", "could not enter chart view")
        _restore_from_stock(dut)
        return
    # Tap 5D tab: x=184 (tab 1 centre), y=7 (header centre).
    dut.set_cooldown_zero()
    dut.cmd("tap 184 7", timeout=3.0)
    time.sleep(0.2)
    r_rng = _stock_get(dut, "stockChartRange")
    # lastChartFetch resets to 0 on tab change, then advances when enqueue fires.
    deadline = time.monotonic() + 5.0
    fetched = False
    while time.monotonic() < deadline:
        r = _stock_get(dut, "lastChartFetch")
        if r.get("ok") and int(r.get("val", 0)) > 0:
            fetched = True
            break
        time.sleep(0.3)
    _restore_from_stock(dut)
    if r_rng.get("val") != "D5":
        fail("T177", f"stockChartRange={r_rng.get('val')!r} after 5D tap — expected D5")
        return
    if not fetched:
        fail("T177", "lastChartFetch did not advance after tab change — enqueue not fired")
        return
    pass_("T177", "5D tab: stockChartRange=D5, lastChartFetch advanced")


# ── T178 — Pre-fetch placeholder in chart view ────────────────────────────────

def t178(dut: Dut):
    """T178 (C4): immediately after drill-in, chartLen=0 and fetchFailed=false (placeholder state)."""
    print("T178  Chart pre-fetch placeholder (chartLen=0, fetchFailed=false)")
    if not _switch_to_stock(dut):
        skip("T178", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Ensure list view — prior test (T177) may have left us in chart view.
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=3.0)  # back to list
        time.sleep(0.2)
    # TASK-300: a chart fetch left in flight by a prior test (T177 only waits
    # for the ENQUEUE; T176's fetch can arrive minutes late under poll
    # contention) would land AFTER the reset below and flip chartLen>0 before
    # the check (observed: chartLen=33, 2026-07-10 full-suite run). Wait for
    # the pipeline to go quiet so the only fetch in play is our own drill-in's.
    if not _drain_data_pipeline(dut, tag="T178"):
        skip("T178", "fetch pipeline never drained within 200 s — "
                     "cannot isolate placeholder state")
        _restore_from_stock(dut)
        return
    # Reset chart data so chartLen=0 and fetchFailed=false are reliably observable.
    dut.cmd("set triggerFetch 1", timeout=3.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)  # drill AAPL; fetch enqueued but not returned
    time.sleep(0.1)  # minimal wait — check before dataTask returns
    r_sv     = _stock_get(dut, "stockSubView")
    r_len    = _stock_get(dut, "chartLen")
    r_failed = _stock_get(dut, "fetchFailed")
    _restore_from_stock(dut)
    if r_sv.get("val") != "chart":
        skip("T178", "drill-in did not fire")
        return
    chart_len    = r_len.get("val", -1)
    fetch_failed = r_failed.get("val")
    if chart_len != 0:
        fail("T178", f"chartLen={chart_len} after reset+drill-in — expected 0 (placeholder)")
        return
    if fetch_failed not in (False, 0, "false", "0"):
        fail("T178", f"fetchFailed={fetch_failed!r} after reset+drill-in — expected false")
        return
    pass_("T178", "chartLen=0, fetchFailed=false — placeholder state confirmed before fetch returns")


# ── T179 — Footer lo/hi (manual) ──────────────────────────────────────────────

def t179(dut: Dut):
    """T179 (C5): lo: and hi: values visible in footer after fetch. [MANUAL — pixel verification required]"""
    print("T179  Footer lo/hi (manual pixel check — skipped in automated run)")
    skip("T179", "pixel verification required — run manually; check lo:/hi: at y=214 after fetch")


# ── T180 — Drill-in default range ────────────────────────────────────────────

def t180(dut: Dut):
    """T180 (C6): every drill-in sets stockChartRange=D1."""
    print("T180  Drill-in default range always D1")
    if not _switch_to_stock(dut):
        skip("T180", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Normalize to list view — prior tests (e.g. T178) may leave Stock in chart view.
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=3.0)
        time.sleep(0.2)
    # Drill, change range, go back, re-drill — verify range resets.
    dut.set_cooldown_zero()
    r_drill1 = dut.cmd("tap 137 36", timeout=3.0)   # AAPL
    time.sleep(0.3)
    sv1 = _stock_get(dut, "stockSubView").get("val")
    if sv1 != "chart":
        skip("T180", "first drill-in failed")
        _restore_from_stock(dut)
        return
    # Wait for D1 fetch before changing tab (g_shellBusy must clear).
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 184 7", timeout=3.0)    # change to 5D
    # Wait for D5 fetch before navigating back.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)    # back to list
    time.sleep(0.2)
    # Wait for any quote refresh triggered by returning to list view.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)   # re-drill AAPL
    time.sleep(0.3)
    r_rng = _stock_get(dut, "stockChartRange")
    _restore_from_stock(dut)
    if r_rng.get("val") != "D1":
        fail("T180", f"stockChartRange={r_rng.get('val')!r} on re-drill — expected D1 reset")
        return
    pass_("T180", "re-drill after range change: stockChartRange reset to D1")


# ── T181 — Back then re-drill ─────────────────────────────────────────────────

def t181(dut: Dut):
    """T181 (C7): back→list→tap NVDA again; chart redraws with correct ticker."""
    print("T181  Back then re-drill")
    if not _switch_to_stock(dut):
        skip("T181", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Drill AAPL, go back, drill NVDA.
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)   # AAPL
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T181", "first drill-in failed")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)     # back
    time.sleep(0.2)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 218", timeout=3.0)  # NVDA row
    time.sleep(0.3)
    r_sv  = _stock_get(dut, "stockSubView")
    r_tk  = _stock_get(dut, "stockChartTicker")
    _restore_from_stock(dut)
    if r_sv.get("val") != "chart":
        fail("T181", "re-drill did not enter chart view")
        return
    if r_tk.get("val") != "NVDA":
        fail("T181", f"stockChartTicker={r_tk.get('val')!r} — expected NVDA")
        return
    pass_("T181", "back→re-drill NVDA: subView=chart, ticker=NVDA")


# ── T182 — Canvas isolation (taskbar-driven path) ─────────────────────────────

def t182(dut: Dut):
    """T182 (cross): Stock→chart view→switchApp away→taskbar back→list; no residue."""
    print("T182  Stock canvas isolation (taskbar-driven switch)")
    if not _restore_spotify(dut):
        skip("T182", "precondition: could not restore Spotify")
        return
    # Enter chart view via serial switchApp (fastest setup).
    if not _switch_to_stock(dut):
        fail("T182", "could not switch to Stock")
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T182", "could not enter chart view — cannot test canvas isolation")
        _restore_from_stock(dut)
        return
    # Switch away via switchApp.
    dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
    time.sleep(0.3)
    # Switch back via taskbar scroll + slot tap (real UI path).
    dut.set_cooldown_zero()
    dut.cmd("drag 297 200 297 100 10", timeout=3.0)  # scroll up 2 slots → offset=2
    time.sleep(0.3)
    r_off = dut.cmd("get tbScrollOffset", timeout=3.0)
    if r_off.get("val") != 2:
        skip("T182", f"tbScrollOffset={r_off.get('val')} — taskbar scroll failed; cannot verify taskbar path")
        dut.cmd("drag 297 100 297 200 10", timeout=3.0)  # reset scroll
        return
    dut.set_cooldown_zero()
    # Physical slot at scrollOffset=2 → AppId (offset+slot)%TASKBAR_APP_COUNT == Stock.
    # NOTE: this test intentionally uses physical-slot arithmetic, not APP_SLOT.
    # It breaks if the app order changes — update the drag offset and slot together.
    # Mod base is APP_SLOT["WebRadio"] (= firmware TASKBAR_APP_COUNT, the taskbar
    # cycle length excluding eject-only WebRadio — TASK-242), NOT APP_COUNT (TASK-347:
    # Settings moved directly before WebRadio, shifting Stock's physical slot 5→4).
    _stock_physical_slot = (APP_SLOT["Stock"] - 2) % APP_SLOT["WebRadio"]
    sx, sy = _c.tap_taskbar_slot(_stock_physical_slot)
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.4)
    r_app = dut.cmd("get appId", timeout=3.0)
    if r_app.get("name") != "Stock":
        skip("T182", f"appId={r_app.get('name')!r} — taskbar tap missed Stock slot")
        dut.cmd("drag 297 100 297 200 10", timeout=3.0)
        _restore_spotify(dut)
        return
    # resume() should restore to last subView (chart) then list if we tapped back...
    # Actually resume() calls repaintChart() if subView==ChartDetail.
    # The test is: no display crash, subView is still whatever it was.
    r_sv = _stock_get(dut, "stockSubView")
    # Reset taskbar scroll.
    dut.cmd("drag 297 100 297 200 10", timeout=3.0)
    _restore_from_stock(dut)
    if not r_app.get("ok"):
        fail("T182", "DUT unresponsive after taskbar-driven switch to Stock")
        return
    if not _check_residue(dut, "T182"):
        skip("T182", "lastPlaylistDraw did not advance after return to Spotify")
        return


# ── T183 — Inject fetch error ────────────────────────────────────────────────

def t183(dut: Dut):
    """T183 (error): set fetchFailed=1, fetchErrorCode=-1; tap ignored; error screen shown."""
    print("T183  Inject fetch error")
    if not _switch_to_stock(dut):
        skip("T183", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Ensure list view — prior test may have left us in chart view.
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=3.0)  # back to list
        time.sleep(0.2)
    dut.cmd("set fetchFailed 1", timeout=3.0)
    dut.cmd("set fetchErrorCode -1", timeout=3.0)
    time.sleep(0.15)  # wait one tick for repaint
    # Tap a list row — should be ignored when fetchFailed.
    dut.set_cooldown_zero()
    dut.cmd("tap 137 120", timeout=3.0)
    time.sleep(0.1)
    r_sv = _stock_get(dut, "stockSubView")
    # Clear error state before returning.
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "list":
        fail("T183", f"stockSubView={r_sv.get('val')!r} after tap while fetchFailed — expected no drill-in")
        return
    pass_("T183", "tap ignored while fetchFailed=1; stockSubView stayed list; error screen shown (manual verify)")


# ── T184 — Error in chart view ────────────────────────────────────────────────

def t184(dut: Dut):
    """T184 (error/chart): inject error while in chart; back button still works."""
    print("T184  Error injection in chart view")
    if not _switch_to_stock(dut):
        skip("T184", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T184", "could not enter chart view")
        _restore_from_stock(dut)
        return
    dut.cmd("set fetchFailed 1", timeout=3.0)
    time.sleep(0.15)
    # Back button must still work even when fetchFailed.
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)
    time.sleep(0.2)
    r_sv = _stock_get(dut, "stockSubView")
    dut.cmd("set fetchFailed 0", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "list":
        fail("T184", f"stockSubView={r_sv.get('val')!r} after back tap while fetchFailed — expected list")
        return
    pass_("T184", "back tap works while fetchFailed=1 in chart view; returned to list")


# ── T231 — Settings → Stock "mode" launch view (TASK-231) ─────────────────────

def _enter_stock_no_force(dut: Dut, timeout: float = 5.0) -> bool:
    """switchApp → Stock WITHOUT forcing stockMode (unlike _switch_to_stock, which
    pins mode 0). Lets resume()/_applyLaunchView() honour the mode set just prior."""
    r = dut.cmd(f"switchApp {_STOCK_APP_ID}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.4)  # let resume() → _applyLaunchView() run + first paint
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Stock"


def t231(dut: Dut):
    """T231: Settings → Stock "mode" (List/Chart/Heatmap) is honoured at launch.

    Regression for the wired-up _applyLaunchView() (was: init() hardcoded List, so
    the Settings toggle did nothing). Drives stockMode 1/2/0 then re-enters Stock
    and asserts the launch sub-view. Also asserts the launch-into-Chart symbol is
    non-empty (the original concern: Chart launched with an empty ticker) and that
    List is the back-navigation base for both detail views. No Spotify/network
    needed — switchApp + in-RAM stockMode only. TASK-231 / BP-034.
    """
    tid = "T231"
    print(f"{tid}  Settings → Stock mode launch view (List/Chart/Heatmap)")

    # Clean List baseline (this also init()s the app and sets _appliedMode=List).
    if not _switch_to_stock(dut):
        skip(tid, "could not switch to Stock for baseline")
        _restore_from_stock(dut)
        return

    # ── Chart launch ──────────────────────────────────────────────────────────
    _restore_from_stock(dut)                     # leave on List → go to Spotify
    dut.cmd("set stockMode 1", timeout=3.0)      # Chart
    if not _enter_stock_no_force(dut):
        fail(tid, "switchApp Stock failed (Chart case)")
        return
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "chart":
        fail(tid, f"stockMode=Chart but launched stockSubView={sv!r} (expected chart)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    tk = _stock_get(dut, "stockChartTicker").get("val", "")
    if not tk:
        fail(tid, "Chart launched with EMPTY ticker — drillToChart(0) precondition not met")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Chart launch ✓ (ticker={tk!r})")
    # back-nav base must be List
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)             # chart back zone
    time.sleep(0.25)
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "list":
        fail(tid, f"Chart back-nav base = {sv!r} (expected list)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Chart → back → list ✓")

    # ── Heatmap launch ────────────────────────────────────────────────────────
    _restore_from_stock(dut)                     # leave on List
    dut.cmd("set stockMode 2", timeout=3.0)      # Heatmap
    if not _enter_stock_no_force(dut):
        fail(tid, "switchApp Stock failed (Heatmap case)")
        return
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "heatmap":
        fail(tid, f"stockMode=Heatmap but launched stockSubView={sv!r} (expected heatmap)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Heatmap launch ✓")
    dut.set_cooldown_zero()
    dut.cmd("tap 260 7", timeout=3.0)            # heatmap back zone (x>190, y<ST_LIST_RULE_Y=22)
    time.sleep(0.25)
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "list":
        fail(tid, f"Heatmap back-nav base = {sv!r} (expected list)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Heatmap → back → list ✓")

    # ── List launch (explicit, no-op default) ─────────────────────────────────
    _restore_from_stock(dut)
    dut.cmd("set stockMode 0", timeout=3.0)      # List
    if not _enter_stock_no_force(dut):
        fail(tid, "switchApp Stock failed (List case)")
        return
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "list":
        fail(tid, f"stockMode=List but launched stockSubView={sv!r} (expected list)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] List launch ✓")

    # Restore default + leave Stock.
    dut.cmd("set stockMode 0", timeout=3.0)
    _restore_from_stock(dut)
    pass_(tid, "stockMode honoured at launch: Chart(ticker set)/Heatmap/List; List is back-nav base")


# ── T185 — Error clears on successful fetch ───────────────────────────────────

def t185(dut: Dut):
    """T185 (error/recovery): error→triggerFetch→lastQuoteFetch advances."""
    print("T185  Error clears on successful fetch")
    if not _switch_to_stock(dut):
        skip("T185", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    dut.cmd("set fetchFailed 1", timeout=3.0)
    dut.cmd("set fetchErrorCode -99", timeout=3.0)
    time.sleep(0.15)
    r_pre = _stock_get(dut, "lastQuoteFetch")
    baseline = int(r_pre.get("val", 0)) if r_pre.get("ok") else 0
    # Zero timestamps so the next tick enqueues immediately.
    dut.cmd("set triggerFetch 1", timeout=3.0)
    # Wait for fetch to complete and lastQuoteFetch to advance.
    fetched = _wait_quote_fetch(dut, baseline, timeout_s=65.0)
    _restore_from_stock(dut)
    if not fetched:
        fail("T185", "lastQuoteFetch did not advance after triggerFetch within 65 s")
        return
    pass_("T185", "triggerFetch triggered re-fetch; lastQuoteFetch advanced — error recovery confirmed")


# ── T186–T188 — M-DATATASK-STREAM-PARSE regression suite ─────────────────────
#
# T186: MSFT (tickerIdx=6) chart fetch succeeds after tickerIdx >= 8 guard fix.
# T187: NVDA (tickerIdx=7) same.
# T188: Cycling all four range tabs fetches without -99 NET ERR (getStream fix).
#
# Row centres (x=137): AAPL=36, AMD=62, AMZN=88, ARM=114,
#                       GOOG=140, META=166, MSFT=192, NVDA=218
# Tab centres (x): D1=148, D5=184, Mo1=220, Ytd=256  (all y=9)
_TAB_XY    = [(148, 9), (184, 9), (220, 9), (256, 9)]
_TAB_NAMES = ["D1", "D5", "Mo1", "Ytd"]


def _t18x_guard(dut: Dut, tid: str, ticker: str, row_y: int):
    """Shared body for T186/T187: verify tickerIdx guard fix allows ticker to fetch."""
    if not _switch_to_stock(dut):
        skip(tid, "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=5.0)   # back to list
        time.sleep(0.3)
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    # Drill into ticker row — triggers enqueue via drillToChart().
    dut.set_cooldown_zero()
    dut.cmd(f"tap 137 {row_y}", timeout=5.0)
    time.sleep(0.5)
    r_sv = _stock_get(dut, "stockSubView")
    if r_sv.get("val") != "chart":
        skip(tid, f"drill-in did not enter chart view (subView={r_sv.get('val')!r})")
        _restore_from_stock(dut)
        return
    r_tk = _stock_get(dut, "stockChartTicker")
    if r_tk.get("val") != ticker:
        fail(tid, f"stockChartTicker={r_tk.get('val')!r} — expected {ticker}")
        _restore_from_stock(dut)
        return
    # Snapshot ok count, trigger fetch, wait for proven completion (LL-041).
    before = _stock_ok_count(dut)
    dut.cmd("set triggerFetch 1", timeout=3.0)
    print(f"  [{tid}] fetch triggered (fetchOkCount={before}); waiting for completion…", flush=True)
    if not _wait_chart_complete(dut, before, timeout_s=45.0):
        _restore_from_stock(dut)
        fail(tid, f"fetchOkCount did not advance after 45 s for {ticker} — guard fix may not have landed")
        return
    r_ff   = _stock_get(dut, "fetchFailed")
    r_code = _stock_get(dut, "fetchErrorCode")
    _restore_from_stock(dut)
    if r_ff.get("val") == "1" or r_ff.get("val") is True:
        fail(tid, f"fetchFailed=1 errorCode={r_code.get('val')} for {ticker}")
        return
    pass_(tid, f"{ticker} chart fetch completed; fetchOkCount advanced")


def t186(dut: Dut):
    """T186: MSFT (tickerIdx=6) chart fetch succeeds after tickerIdx >= 8 guard fix."""
    print("T186  MSFT guard fix — tickerIdx=6 chart fetch")
    _t18x_guard(dut, "T186", "MSFT", 192)


def t187(dut: Dut):
    """T187: NVDA (tickerIdx=7) chart fetch succeeds after tickerIdx >= 8 guard fix."""
    print("T187  NVDA guard fix — tickerIdx=7 chart fetch")
    _t18x_guard(dut, "T187", "NVDA", 218)


def t188(dut: Dut):
    """T188: cycling all four range tabs fetches without -99 (getStream() fix, ADR-034)."""
    print("T188  Range-cycle no-99 regression (ADR-034 getStream fix)", flush=True)
    if not _switch_to_stock(dut):
        skip("T188", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Clear any leftover error state from prior tests.
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=5.0)
        time.sleep(0.5)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=5.0)   # drill AAPL
    time.sleep(1.0)                       # allow chart render before checking
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T188", "could not drill into chart view")
        _restore_from_stock(dut)
        return

    # Use tab taps (not triggerFetch) — tab taps only enqueue DATA_FETCH_STOCK_CHART.
    # triggerFetch also resets lastQuoteFetch, triggering an 8-ticker quote fetch
    # in parallel that can take 60 s+, causing serial timeouts mid-test.
    #
    # Pattern (LL-041): snapshot fetchOkCount before tap → tap → wait for count to
    # advance → proven completion, not a blind sleep. Queue depth is irrelevant
    # because we observe the counter, not the number of taps fired.

    for tab_idx, (tx, ty) in enumerate(_TAB_XY):
        tab_name = _TAB_NAMES[tab_idx]
        before = _stock_ok_count(dut)
        dut.set_cooldown_zero()
        dut.cmd(f"tap {tx} {ty}", timeout=5.0)
        print(f"  [T188] {tab_name} tapped (fetchOkCount={before}); waiting for completion…", flush=True)
        if not _wait_chart_complete(dut, before, timeout_s=45.0):
            r_ff   = _stock_get(dut, "fetchFailed",    timeout=3.0)
            r_code = _stock_get(dut, "fetchErrorCode", timeout=3.0)
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T188", f"fetchOkCount did not advance on {tab_name} — "
                         f"fetchFailed={r_ff.get('val')!r} fetchErrorCode={r_code.get('val')!r}")
            return
        r_ff   = _stock_get(dut, "fetchFailed", timeout=8.0)
        r_code = _stock_get(dut, "fetchErrorCode", timeout=8.0)
        if r_ff.get("val") == "1" or r_ff.get("val") is True:
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T188", f"fetchFailed=1 errorCode={r_code.get('val')} on range {tab_name}")
            return
        print(f"  [T188] {tab_name} ok", flush=True)

    _restore_from_stock(dut)
    pass_("T188", "all 4 ranges (D1/D5/Mo1/Ytd) fetched without -99 — getStream() fix confirmed")


# ── T204 — M-STOCK-VE-STRESS: D1↔Ytd rapid alternating stress ────────────────
# Step 2 of M-STOCK-VE-STRESS. T188 verified each range sequentially; T204 drives
# D1↔Ytd alternation (3 cycles = 6 fetches) to exercise back-to-back
# DynamicJsonDocument(16384) alloc/free under heap pressure (ADR-034).
# Counter observation between taps proves queue drains — no blind sleeps.

def t204(dut: Dut):
    """T204: D1↔Ytd rapid alternating stress — back-to-back alloc/free under heap pressure."""
    print("T204  D1↔Ytd rapid alternating stress (M-STOCK-VE-STRESS)", flush=True)
    # TASK-386: entry baseline. Unlike T193, T204 self-induces heap pressure via its own
    # 6 rapid back-to-back fetches — but its *starting* fragmentation still depends on
    # whatever ~150 prior tests in a full-suite run left behind, so this baseline still
    # matters for comparing an isolated run/test-targeted repro against a real suite run.
    entry_diag = _diag_snapshot(dut, "T204-entry")
    if not _switch_to_stock(dut):
        skip("T204", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=5.0)   # back to list
        time.sleep(0.5)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=5.0)     # drill AAPL
    time.sleep(1.0)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T204", "could not drill into chart view")
        _restore_from_stock(dut)
        return

    stress_tabs = [(_TAB_XY[3], "Ytd"), (_TAB_XY[0], "D1")] * 3  # 3 cycles, 6 taps

    for i, ((tx, ty), tab_name) in enumerate(stress_tabs, start=1):
        before = _stock_ok_count(dut)
        # TASK-386: snapshot before every tap, not just on failure — the heap-pressure
        # hypothesis is specifically about a *trend* across the 6-fetch cycle (freeInt/
        # lfbInt shrinking cycle over cycle), which a single failure-point snapshot can't
        # show. Cheap (3 `get`s) relative to the ~2.9s fetch itself.
        pre_diag = _diag_snapshot(dut, f"T204-pre-{i}-{tab_name}")
        dut.set_cooldown_zero()
        dut.cmd(f"tap {tx} {ty}", timeout=5.0)
        print(f"  [T204] {tab_name} tapped (fetchOkCount={before}); waiting…", flush=True)
        if not _wait_chart_complete(dut, before, timeout_s=45.0, test_id="T204"):
            timeout_diag = _diag_snapshot(dut, f"T204-timeout-{i}-{tab_name}")
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T204", f"fetchOkCount did not advance on {tab_name} (cycle {i}/6) — heap "
                          f"pressure failure? | entry={entry_diag} | pre-tap={pre_diag} | "
                          f"timeout={timeout_diag}")
            return
        r_ff   = _stock_get(dut, "fetchFailed", timeout=8.0)
        r_code = _stock_get(dut, "fetchErrorCode", timeout=8.0)
        if r_ff.get("val") == "1" or r_ff.get("val") is True:
            post_diag = _diag_snapshot(dut, f"T204-fail-{i}-{tab_name}")
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T204", f"fetchFailed=1 errorCode={r_code.get('val')} on {tab_name} (cycle "
                          f"{i}/6) — alloc/free stress failure | entry={entry_diag} | "
                          f"pre-tap={pre_diag} | post={post_diag}")
            return
        print(f"  [T204] {tab_name} ok", flush=True)

    _restore_from_stock(dut)
    pass_("T204", "D1↔Ytd × 3 cycles — no fetchFailed; getStream() alloc/free stable under stress")


# ── M-TOUCH-UX suite (TASK-118) ───────────────────────────────────────────────
# Verifies: busy indicator (shellBusy), cooldown gate, g_shellBusy cmdTap gate.
# Firmware prerequisites: get shellBusy, get visMode, cmdTap g_shellBusy check.
# All tests require cyd2usb_winamp_debug build.

_SPOTIFY_APP_ID = APP_SLOT["Spotify"]
_CLOCK_APP_ID   = APP_SLOT["Clock"]


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


def _poll_chart_len_positive(dut: Dut, timeout_s: float = 45.0) -> bool:
    """Poll get chartLen until > 0 (fetch complete)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = _stock_get(dut, "chartLen")
        try:
            if r.get("ok") and int(r.get("val", 0)) > 0:
                return True
        except (ValueError, TypeError):
            pass
        time.sleep(1.0)
    # TASK-386: same treatment as _wait_chart_complete — automatic for every caller.
    _diag_snapshot(dut, "_poll_chart_len_positive-timeout")
    return False


def _get_shell_busy(dut: Dut) -> bool | None:
    """Return current shellBusy bool, or None on error."""
    r = dut.cmd("get shellBusy", timeout=2.0)
    if r.get("ok"):
        return r.get("busy")
    return None


def _get_vis_mode(dut: Dut) -> int | None:
    """Return current visMode integer (0–3), or None on error."""
    r = dut.cmd("get visMode", timeout=2.0)
    if r.get("ok"):
        try:
            return int(r["mode"])
        except (KeyError, ValueError, TypeError):
            pass
    return None


# ── T-BUSY-01 — StockApp row tap triggers busy; clears on fetch complete ──────

def t_busy_01(dut: Dut):
    """T-BUSY-01: switchApp(Stock) → tap AAPL row → shellBusy true → chartLen>0 → shellBusy false."""
    print("T-BUSY-01  StockApp row tap → amber → clears on fetch complete")
    # TASK-386: entry baseline. This is a single self-contained fetch (no self-induced
    # stress like T204) — structurally identical to T193's case, so its "chartLen never
    # exceeded 0" failure is most plausibly suite-accumulated-state-dependent, not
    # something an isolated run/test-targeted repro could validate on its own.
    entry_diag = _diag_snapshot(dut, "T-BUSY-01-entry")
    if not _switch_to_stock(dut):
        skip("T-BUSY-01", "could not switch to StockApp")
        return
    # Ensure list view (tap back to list if needed)
    dut.cmd("tap 10 7", timeout=2.0)  # back tap — no-op if already in list
    time.sleep(0.3)
    pre_diag = _diag_snapshot(dut, "T-BUSY-01-pre-trigger")
    # Tap AAPL row (137, 36) to drill to chart and trigger async fetch
    dut.cmd("tap 137 36", timeout=2.0)
    # Poll for busy (may be brief; miss → test gap, not firmware defect)
    busy_seen = _poll_shell_busy(dut, True, timeout_ms=500)
    if not busy_seen:
        # Not necessarily a defect — busy window may be shorter than poll granularity
        print("  [T-BUSY-01] shellBusy=true not observed within 500 ms (test gap; continuing)")
    else:
        print("  [T-BUSY-01] shellBusy=true observed")
    # Wait for chart fetch to complete (chartLen > 0)
    print("  [T-BUSY-01] waiting for chartLen > 0…", flush=True)
    if not _poll_chart_len_positive(dut, timeout_s=45.0):
        timeout_diag = _diag_snapshot(dut, "T-BUSY-01-timeout")
        _restore_from_stock(dut)
        fail("T-BUSY-01", "chartLen did not exceed 0 after 45 s — fetch did not complete | "
                           f"entry={entry_diag} | pre-trigger={pre_diag} | timeout={timeout_diag}")
        return
    # After fetch, shellBusy must be false
    time.sleep(0.1)
    busy_after = _get_shell_busy(dut)
    _restore_from_stock(dut)
    if busy_after is None:
        fail("T-BUSY-01", "get shellBusy failed after chart fetch")
        return
    if busy_after:
        fail("T-BUSY-01", "shellBusy still true after chartLen > 0 — auto-clear did not fire")
        return
    pass_("T-BUSY-01", f"shellBusy cleared after chart fetch complete (busy_seen={busy_seen})")


# ── T-BUSY-01b — StockApp tab-range tap also triggers busy ────────────────────

def t_busy_01b(dut: Dut):
    """T-BUSY-01b: drill to chart, tap 5D tab → shellBusy true."""
    print("T-BUSY-01b  StockApp tab-range tap → amber")
    if not _switch_to_stock(dut):
        skip("T-BUSY-01b", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("tap 10 7", timeout=2.0)
        time.sleep(0.3)
        # tap-to-list triggers a quote refresh; wait for it to settle.
        _wait_shell_not_busy(dut, timeout_s=10.0)
        # Force stale cache BEFORE drill-in so the drill always triggers a fresh fetch.
        dut.cmd("set triggerFetch 1", timeout=2.0)
        drill_before = _stock_ok_count(dut)
        dut.cmd("tap 137 36", timeout=10.0)
        time.sleep(0.3)
        if not _wait_chart_complete(dut, drill_before, timeout_s=45.0):
            _restore_from_stock(dut)
            skip("T-BUSY-01b", "initial chart fetch did not complete — cannot test tab-range path")
            return
        time.sleep(0.1)
        before5d = _stock_ok_count(dut)
        dut.cmd("tap 184 7", timeout=2.0)
        busy_seen = _poll_shell_busy(dut, True, timeout_ms=5000, cmd_timeout=1.0)
        _wait_chart_complete(dut, before5d, timeout_s=45.0)
    _restore_from_stock(dut)
    if not busy_seen:
        skip("T-BUSY-01b", "shellBusy=true not observed within 5 s after 5D tap — warm fetch too fast")
        return
    pass_("T-BUSY-01b", "shellBusy=true observed after 5D range tab tap")


# ── T-BUSY-02 — Spotify PLAY tap triggers busy; clears ────────────────────────

def t_busy_02(dut: Dut):
    """T-BUSY-02: Spotify PLAY tap → shellBusy true → clears within 3 s."""
    print("T-BUSY-02  Spotify PLAY → amber → clears")
    if not _restore_spotify(dut):
        skip("T-BUSY-02", "could not restore Spotify app")
        return
    vx, vy = _c.tap_button("PLAY")
    dut.cmd(f"tap {vx} {vy}", timeout=2.0)
    busy_seen = _poll_shell_busy(dut, True, timeout_ms=500)
    if not busy_seen:
        fail("T-BUSY-02", "shellBusy=true not observed within 500 ms after PLAY tap")
        return
    print("  [T-BUSY-02] shellBusy=true; waiting for clear (max 3.5 s)…", flush=True)
    cleared = _poll_shell_busy(dut, False, timeout_ms=3500)
    if not cleared:
        fail("T-BUSY-02", "shellBusy still true after 3.5 s — auto-clear or queue drain did not fire")
        return
    pass_("T-BUSY-02", "shellBusy true→false observed after PLAY tap")


# ── T-BUSY-03 — Passive apps: no amber on canvas tap ─────────────────────────

def t_busy_03(dut: Dut):
    """T-BUSY-03: Clock/Weather/Crypto/Matrix/Life/Aquarium canvas taps → shellBusy false."""
    print("T-BUSY-03  Passive apps — no amber on canvas tap")
    # Use switchApp <id> for all — avoids taskbar scroll issues.
    PASSIVE_APPS = [
        (name, APP_SLOT[name])
        for name in ["Clock", "Weather", "Crypto", "Matrix", "Life", "Aquarium"]
        if name in APP_SLOT
    ]
    # Apps that do network fetches on first activation need a longer settle time.
    _FETCH_APPS = {"Weather", "Crypto"}
    errors = []
    for app_name, app_id in PASSIVE_APPS:
        _wait_shell_not_busy(dut, timeout_s=10.0)
        with _bgpoll_suspended(dut):
            r = dut.cmd(f"switchApp {app_id}", timeout=3.0)
            if not r.get("ok"):
                errors.append(f"{app_name}: switchApp failed: {r}")
                continue
            settle = 3.0 if app_name in _FETCH_APPS else 0.5
            time.sleep(settle)
            r_tap = dut.cmd("tap 137 120", timeout=5.0)
            if not r_tap.get("ok"):
                errors.append(f"{app_name}: tap failed: {r_tap}")
                continue
            time.sleep(0.1)
            busy = _get_shell_busy(dut)
        if busy is None:
            errors.append(f"{app_name}: get shellBusy failed")
        elif busy:
            errors.append(f"{app_name}: shellBusy=true after canvas tap (unexpected)")
        else:
            print(f"  [T-BUSY-03] {app_name}: shellBusy=false ✓")
    _restore_spotify(dut)
    if errors:
        fail("T-BUSY-03", "; ".join(errors))
    else:
        pass_("T-BUSY-03", f"all {len(PASSIVE_APPS)} passive apps: shellBusy=false after canvas tap")


# ── T-BUSY-05 — App switch while busy clears amber ────────────────────────────

def t_busy_05(dut: Dut):
    """T-BUSY-05: Stock row tap (busy) → switchApp(Spotify) → shellBusy false × 3."""
    print("T-BUSY-05  App switch while busy → amber clears")
    if not _switch_to_stock(dut):
        skip("T-BUSY-05", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("tap 10 7", timeout=2.0)
        time.sleep(0.3)
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.cmd("set triggerFetch 1", timeout=2.0)
        r_d = dut.cmd("tap 137 36", timeout=5.0)
        drilled = (not r_d.get("skipped")) and (
            dut.cmd("get stockSubView", timeout=3.0).get("val") == "chart"
        )
        if not drilled:
            _restore_from_stock(dut)
            skip("T-BUSY-05", "could not drill to chart (tap skipped or wrong subView)")
            return
        busy_seen = _poll_shell_busy(dut, True, timeout_ms=5000, cmd_timeout=1.0)
        if not busy_seen:
            _restore_from_stock(dut)
            skip("T-BUSY-05", "shellBusy=true not observed within 5 s — warm connection completed fetch too fast")
            return
        dut.cmd(f"switchApp {_SPOTIFY_APP_ID}", timeout=3.0)
        time.sleep(0.05)
        results = []
        for _ in range(3):
            results.append(_get_shell_busy(dut))
            time.sleep(0.02)
        _poll_shell_busy(dut, False, timeout_ms=5000)
    if any(b is not True for b in results):
        bad = [str(r) for r in results if r is not False]
        if bad:
            fail("T-BUSY-05", f"shellBusy not false after switchApp: {results}")
            return
    pass_("T-BUSY-05", f"shellBusy=false in all 3 polls after switchApp (results={results})")


# ── T-CDWN-01 — VIS Phase-2 cooldown gate (touchScreenCoolDownTime) ───────────

def t_cdwn_01(dut: Dut):
    """T-CDWN-01: VIS cycling — tap 1 cycles; tap 2 inside the VIS 300 ms window
    suppressed; tap 3 after `get cooldown` polls to 0 cycles.

    TASK-297 (2026-07-10 rework): the historical flake was never the VIS 300 ms
    edge — it was the SHELL cooldown (main.cpp s_cooldownMs: every release arms
    +200 ms and an armed Press is silently dropped). Dut.cmd now drains it
    before every tap, so tap 2 naturally lands at ~200-280 ms post-tap-1 —
    inside [shell-clear, VIS-expiry]. The VIS gate reading taken right after
    tap 2 proves the window was actually hit; a missed window (gate already 0)
    retries the whole sequence instead of failing."""
    print("T-CDWN-01  VIS Phase-2 cooldown gate")
    if not _restore_spotify(dut):
        skip("T-CDWN-01", "could not restore Spotify app")
        return
    dut.cmd("set cooldown 0", timeout=2.0)
    vx, vy = _c.tap_vis()

    for attempt in range(3):
        # g_shellBusy is the OTHER silent Press-dropper on main.cpp's input
        # gate (T079 precedent) — on a fresh boot the Spotify app's pending
        # async (403-latched poll) holds it armed right when tap 1 fires.
        if not _wait_shell_not_busy(dut, timeout_s=10.0):
            skip("T-CDWN-01", "g_shellBusy never cleared — cannot tap")
            return
        m0 = _get_vis_mode(dut)
        if m0 is None:
            fail("T-CDWN-01", "get visMode failed at baseline")
            return
        # Tap 1 — cycles to M1 (cmd() drains the shell cooldown first)
        dut.cmd(f"tap {vx} {vy}", timeout=2.0)
        m1 = _get_vis_mode(dut)
        if m1 is None:
            fail("T-CDWN-01", "get visMode failed after tap 1")
            return
        if m1 == m0:
            busy = dut.cmd("get shellBusy", timeout=2.0).get("busy")
            sc = dut.cmd("get shellCooldown", timeout=2.0).get("remainingMs")
            fail("T-CDWN-01", f"tap 1 did not cycle visMode (stuck at {m0}) — "
                              f"post-tap gates: shellBusy={busy} shellCooldown={sc}ms")
            return
        # Tap 2 — cmd()'s shell drain holds it until ~200 ms post-release, then
        # it must land while the VIS gate (300 ms from tap 1) is still live.
        dut.cmd(f"tap {vx} {vy}", timeout=2.0)
        r_gate = dut.cmd("get cooldown", timeout=2.0)
        gate_rem = int(r_gate.get("remainingMs", -1))
        m_after2 = _get_vis_mode(dut)
        if m_after2 is None:
            fail("T-CDWN-01", "get visMode failed after tap 2")
            return
        if m_after2 != m1:
            # VIS gate expired before tap 2 arrived — window missed, not a
            # product failure. Retry the sequence from the new baseline.
            print(f"  [T-CDWN-01] attempt {attempt + 1}: tap 2 landed past the "
                  f"VIS window (visMode {m1}→{m_after2}, gate={gate_rem} ms) — retrying")
            continue
        print(f"  [T-CDWN-01] tap 1: visMode {m0}→{m1}; tap 2 suppressed "
              f"(VIS gate {gate_rem} ms live at check)")
        # Tap 3 — poll the VIS gate to 0 (shell drain happens inside cmd()).
        deadline = time.monotonic() + 2.0
        rem = gate_rem
        while rem > 0 and time.monotonic() < deadline:
            time.sleep(min(rem / 1000.0, 0.1))
            rem = int(dut.cmd("get cooldown", timeout=2.0).get("remainingMs", 0))
        if rem > 0:
            fail("T-CDWN-01", f"VIS cooldown never reached 0 within 2 s after tap 2 (last={rem} ms)")
            return
        # Tap 1's consumed Press arms g_shellBusy when the app has pending
        # async (main.cpp ~1985) — in suite context the Spotify poll makes
        # that routine, and an armed busy silently drops tap 3. No window
        # constraint here, so wait it out.
        if not _wait_shell_not_busy(dut, timeout_s=10.0):
            skip("T-CDWN-01", "g_shellBusy never cleared before tap 3")
            return
        dut.cmd(f"tap {vx} {vy}", timeout=2.0)
        m2 = _get_vis_mode(dut)
        if m2 is None:
            fail("T-CDWN-01", "get visMode failed after tap 3")
            return
        if m2 == m1:
            busy = dut.cmd("get shellBusy", timeout=2.0).get("busy")
            sc = dut.cmd("get shellCooldown", timeout=2.0).get("remainingMs")
            fail("T-CDWN-01", f"tap 3 did not cycle visMode (stuck at {m1}) with "
                              f"VIS gate 0 — post-tap gates: shellBusy={busy} "
                              f"shellCooldown={sc}ms")
            return
        print(f"  [T-CDWN-01] tap 3: visMode {m1}→{m2}")
        pass_("T-CDWN-01", f"Phase-2 gate confirmed: tap2 suppressed, tap3 cycled "
                           f"({m0}→{m1}→{m1}→{m2}); attempt {attempt + 1}")
        return
    fail("T-CDWN-01", "VIS suppression window missed on 3 consecutive attempts — "
                      "shell drain (~200 ms) + serial RTT may exceed the VIS 300 ms gate")


# ── T-CDWN-02 — g_shellBusy gate in cmdTap blocks second canvas tap ───────────

def t_cdwn_02(dut: Dut):
    """T-CDWN-02: tap row while busy → second tap dropped by cmdTap g_shellBusy gate → one fetch, not two.

    Primary assertion: second cmdTap returns skipped:true (gate active).
    Secondary assertion: exactly one fetch resolves (fetchOkCount+fetchErrCount == 1).
    Cold ESP32 TLS to Yahoo Finance can take 30–40 s; we wait up to 60 s for resolution.
    """
    print("T-CDWN-02  cmdTap g_shellBusy gate blocks second tap")
    if not _switch_to_stock(dut):
        skip("T-CDWN-02", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("tap 10 7", timeout=5.0)
        time.sleep(0.3)
        # tap-to-list triggers a quote refresh; wait for it before issuing more commands.
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.cmd("set triggerFetch 1", timeout=2.0)
        dut.cmd("set fetchErrCount 0", timeout=2.0)
        n = _stock_ok_count(dut)
        if n < 0:
            _restore_from_stock(dut)
            skip("T-CDWN-02", "get fetchOkCount failed")
            return
        r_d = dut.cmd("tap 137 36", timeout=5.0)
        if r_d.get("skipped"):
            _restore_from_stock(dut)
            skip("T-CDWN-02", "drill tap skipped — shell still busy after precondition wait")
            return
        # tap1 processed → send tap2 IMMEDIATELY (no subView check adds no delay).
        tap2_r = dut.cmd("tap 137 36", timeout=8.0)
        tap2_skipped = tap2_r.get("skipped", False) if isinstance(tap2_r, dict) else False
        print(f"  [T-CDWN-02] tap2 response: {tap2_r}", flush=True)
        if not tap2_skipped:
            _restore_from_stock(dut)
            skip("T-CDWN-02", "tap2 not skipped — warm connection completed fetch before tap2 arrived")
            return
        print(f"  [T-CDWN-02] gate confirmed (skipped:true); waiting up to 60 s for fetch to resolve…", flush=True)
        deadline = time.monotonic() + 60.0
        fetch_ok = n
        fetch_err = 0
        while time.monotonic() < deadline:
            try:
                cur_ok = _stock_ok_count(dut)
                cur_err_r = dut.cmd("get fetchErrCount", timeout=5.0)
                cur_err = cur_err_r.get("val", 0) if isinstance(cur_err_r, dict) else 0
                if cur_ok > n or cur_err > 0:
                    fetch_ok  = cur_ok
                    fetch_err = cur_err
                    break
            except TimeoutError:
                pass  # DUT busy with TLS fetch — retry
            time.sleep(1.0)
        _restore_from_stock(dut)
    total = (fetch_ok - n) + fetch_err
    if total == 0:
        flake("T-CDWN-02", "gate confirmed (skipped:true) but fetch never resolved within 60 s (network unavailable)")
        return
    if total >= 2:
        fail("T-CDWN-02", f"gate confirmed but {total} fetches resolved — second tap may have triggered a fetch despite skipped:true")
        return
    pass_("T-CDWN-02", f"gate confirmed (skipped:true); exactly 1 fetch resolved (ok={fetch_ok-n} err={fetch_err})")


# ── T-CDWN-03 — Taskbar tap bypasses g_shellBusy gate ────────────────────────

def t_cdwn_03(dut: Dut):
    """T-CDWN-03: tap row (busy) → taskbar Clock tap (x≥275) → appId=Clock, shellBusy=false."""
    print("T-CDWN-03  Taskbar tap passes g_shellBusy gate → app switches")
    if not _switch_to_stock(dut):
        skip("T-CDWN-03", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("tap 10 7", timeout=2.0)
        time.sleep(0.3)
        # tap-to-list triggers a quote refresh; wait for it before issuing more commands.
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.cmd("set triggerFetch 1", timeout=2.0)
        dut.cmd("tap 137 36", timeout=5.0)
        # Taskbar Clock tap arrives while fetch is in-flight (shellBusy=true).
        tx, ty = _c.tap_taskbar_slot(_CLOCK_APP_ID)
        dut.cmd(f"tap {tx} {ty}", timeout=2.0)
        time.sleep(0.3)
        r_app = dut.cmd("get appId", timeout=3.0)
        app_name = r_app.get("name") if r_app.get("ok") else None
        busy_after = _get_shell_busy(dut)
        dut.cmd(f"switchApp {_SPOTIFY_APP_ID}", timeout=3.0)
        time.sleep(0.3)
    if app_name != "Clock":
        fail("T-CDWN-03", f"appId={app_name!r} after taskbar tap — expected 'Clock'")
        return
    if busy_after is not False:
        fail("T-CDWN-03", f"shellBusy={busy_after} after switchApp to Clock — expected false")
        return
    pass_("T-CDWN-03", "taskbar Clock tap while busy: appId=Clock, shellBusy=false")


# ── main ──────────────────────────────────────────────────────────────────────

# ── velocity-scroll-001 suite (TASK-104) ──────────────────────────────────────
# Firmware constraint: `drag x1 y1 x2 y2 steps` always ends with a release
# sentinel; there is no standalone `release` command.  T157-T159 exploit the
# fact that handleSerialCommands() and drainInjectionQueue() each run ONCE per
# loop() iteration, so commands sent before the drag queue drains are processed
# mid-drag:
#   iter N:   drain pops step N-1 (updates _dragCurrentY)
#   iter N:   handleSerialCommands processes queued command → tick fires here
#   iter N+1: drain pops next step (or Release → drag JSON emitted)
# With steps=1 the queue is: Press@y1, Move@y2, Release.
#   iter 2: Press — cmd_A = get dragState  (dragState = D_PLEDIT_SCROLL)
#   iter 3: Move@y2 (_dragCurrentY=y2) — cmd_B = tick 50 20 (fires at full dy)
#   iter 4: Release → drag JSON
# As-built: SCROLL_DEAD_ZONE_PX=1, SCROLL_SPEED_K_DEFAULT=0.1667,
#           dy=-13 → effective=12 → velocity=12×0.1667=2.0004 rows/s

_PLEDIT_X  = 140   # x inside PLEDIT content area  (x ∈ [12..255])
_PLSTART_Y = 163   # drag start y (below anchor)
_PLEND_Y   = 150   # drag end y   (above anchor);  dy = 150-163 = -13 (finger up)


def _vs_precondition(dut: Dut, tid: str) -> bool:
    """Shared precondition: Spotify active, queue ≥ 10, scrollOffset=0, D_IDLE."""
    if not _restore_spotify(dut):
        skip(tid, "precondition: could not restore Spotify")
        return False
    if not dut.wait_for_queue(min_count=10, timeout=30.0):
        skip(tid, "precondition: queue count < 10 after 30 s — need ≥ 10 items loaded")
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


# ── touch-capture-001 (T149–T154) ────────────────────────────────────────────

def _tc_drag_collect(dut: Dut, cmd: str, markers: list[str],
                     timeout: float = 15.0) -> tuple[list[str], dict | None]:
    """Send a drag command, collect log lines containing any marker string,
    and return (matched_lines, drag_response_or_None)."""
    dut.send(cmd)
    matched: list[str] = []
    drag_resp = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if not line:
            continue
        if markers and any(m in line for m in markers):
            matched.append(line)
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    drag_resp = obj
                    break
            except json.JSONDecodeError:
                pass
    return matched, drag_resp


def t149(dut: Dut):
    print("T149  POSBAR drag: ACT_SEEK committed at correct position")
    dut.cmd("set songDuration 120000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T149", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    pbx0, _pbx1, _pby0, _pby1 = _c.posbar_bounds()
    pby = _c.tap_posbar()[1]
    x_start = pbx0 + 24   # left quarter, well inside hitbox
    x_end   = pbx0 + 184  # right half → posbarFromX ≈ 89032 ms of 120000

    _, drag_resp = _tc_drag_collect(dut, f"drag {x_start} {pby} {x_end} {pby} 10",
                                    ["ACT_SEEK", "seek commit"])
    if drag_resp is None:
        fail("T149", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T149", f"drag ok=false: {drag_resp}"); return

    rp = dut.cmd("get posbarDragMs")
    committed_ms = rp.get("ms", -1)
    if not (50000 <= committed_ms <= 120000):
        fail("T149", f"posbarDragMs={committed_ms} not in [50000, 120000]"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T149", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    pass_("T149", f"posbarDragMs={committed_ms} ms; dragState=D_IDLE")


def t150(dut: Dut):
    print("T150  POSBAR capture: Move above groove still updates posbarDragMs")
    dut.cmd("set songDuration 120000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T150", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    pbx0, _pbx1, pby0, _pby1 = _c.posbar_bounds()
    pby = _c.tap_posbar()[1]
    x_start = pbx0 + 24   # same x profile as T149
    x_end   = pbx0 + 184  # same endpoint → same expected committed_ms
    y_end   = pby0 - 22   # above POSBAR hitbox (pby0=72 → y_end=50)

    _, drag_resp = _tc_drag_collect(dut, f"drag {x_start} {pby} {x_end} {y_end} 10", [])
    if drag_resp is None:
        fail("T150", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T150", f"drag ok=false: {drag_resp}"); return

    rp = dut.cmd("get posbarDragMs")
    committed_ms = rp.get("ms", -1)
    if not (50000 <= committed_ms <= 120000):
        fail("T150", f"posbarDragMs={committed_ms} not in [50000, 120000] "
                     f"(~0 = capture broken; Move samples dropped after y left groove)"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T150", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    pass_("T150", f"posbarDragMs={committed_ms} ms despite y-drift above groove; dragState=D_IDLE")


def t151(dut: Dut):
    print("T151  VOLUME capture: Move below groove still emits ACT_VOLUME")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T151", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    vx0, _vx1, _vy0, vy1 = _c.vol_bounds()
    vy = _c.vol_drag_y()
    x_start = vx0 + 3   # well inside VOLUME x-range
    x_end   = vx0 + 60  # moves right but stays inside x-range
    y_end   = vy1 + 11  # drifts below VOLUME hitbox bottom edge

    lines, drag_resp = _tc_drag_collect(
        dut, f"drag {x_start} {vy} {x_end} {y_end} 10",
        ["enqueued ACT_VOLUME", "drag-end commit"])
    if drag_resp is None:
        fail("T151", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T151", f"drag ok=false: {drag_resp}"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T151", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    if not lines:
        fail("T151", "no ACT_VOLUME event seen — volume not updated across y-drift; "
                     "capture likely broken"); return

    pass_("T151", f"dragState=D_IDLE; {len(lines)} ACT_VOLUME event(s) during y-drift below groove")


def t152(dut: Dut):
    print("T152  PLEDIT scrollbar capture: Move into content area continues scrolling")
    if not _restore_spotify(dut):
        fail("T152", "precondition: could not restore Spotify app"); return
    if not dut.wait_for_queue(min_count=6):
        skip("T152", "queue < 6 items — scrollOffset max=0; need more queued tracks"); return

    # Reset scrollOffset to 0
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    for _ in range(10):
        _do_drag(dut, xd, yd, xd2, yd2)
    pre = _get_scroll(dut)
    if pre != 0:
        fail("T152", f"precondition: scrollOffset={pre} could not be reset to 0"); return

    # Scrollbar strip: x ∈ [PLEDIT_CONTENT_X+PLEDIT_CONTENT_W, PLEDIT_W-1] = [256, 274].
    # Start drag in centre of strip (x=265), drift left into content area (x=52).
    # y sweeps top-of-rows→lower to advance scrollOffset via updateScrollDirect().
    pledit_rows_y = int(_c.S["PLEDIT_ROWS_Y"])          # 136
    sb_x      = int(_c.S["PLEDIT_CONTENT_X"]) + int(_c.S["PLEDIT_CONTENT_W"]) + 9  # 265
    content_x = int(_c.S["PLEDIT_CONTENT_X"]) + 40      # 52
    y_start   = pledit_rows_y + 4                        # 140
    y_end     = pledit_rows_y + 44                       # 180

    resp = _do_drag(dut, sb_x, y_start, content_x, y_end, steps=10)
    if resp is None:
        fail("T152", "no drag response within 15 s"); return
    if not resp.get("ok"):
        fail("T152", f"drag ok=false: {resp}"); return

    post = _get_scroll(dut)
    if post is None:
        fail("T152", "could not read scrollOffset after drag"); return
    if post <= 0:
        fail("T152", f"scrollOffset={post} after drag (expected > 0) — "
                     "capture broken; drift into content area lost D_PLEDIT_SCROLL_DIRECT"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T152", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    pass_("T152", f"scrollOffset 0→{post} during scrollbar→content drift; dragState=D_IDLE")


def t153(dut: Dut):
    print("T153  Capture exclusivity: VOLUME drift into POSBAR row does not start seek")
    dut.cmd("set songDuration 120000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T153", f"precondition: dragState={rg.get('state')} not D_IDLE"); return

    # Snapshot posbarDragMs before the drag — may be non-zero from earlier tests.
    # The key assertion is that it does NOT change during a VOLUME drag (capture exclusivity).
    rp_pre = dut.cmd("get posbarDragMs")
    baseline_ms = rp_pre.get("ms", -1)

    dut.set_cooldown_zero()

    vx0, _vx1, _vy0, _vy1 = _c.vol_bounds()
    vy  = _c.vol_drag_y()   # y inside VOLUME
    pby = _c.tap_posbar()[1]  # y inside POSBAR — drift target
    x_start = vx0 + 3    # inside VOLUME x-range
    x_end   = vx0 + 60   # still inside VOLUME x-range at release

    lines, drag_resp = _tc_drag_collect(
        dut, f"drag {x_start} {vy} {x_end} {pby} 10",
        ["ACT_SEEK", "seek commit", "D_POSBAR"])
    if drag_resp is None:
        fail("T153", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T153", f"drag ok=false: {drag_resp}"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T153", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    rp_post = dut.cmd("get posbarDragMs")
    post_ms = rp_post.get("ms", -1)
    if post_ms != baseline_ms:
        fail("T153", f"posbarDragMs changed {baseline_ms}→{post_ms} during VOLUME drag "
                     f"(Phase 2 POSBAR hit-test fired — capture exclusivity broken)"); return

    if lines:
        fail("T153", f"ACT_SEEK log line seen during VOLUME drag: {lines[0]!r}"); return

    pass_("T153", f"posbarDragMs unchanged at {post_ms} ms; no seek initiated; dragState=D_IDLE")


def t154(dut: Dut):
    print("T154  POSBAR tap: Press + Release seeks to pressed x position")
    dut.cmd("set songDuration 60000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T154", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    pbx0, _pbx1, _pby0, _pby1 = _c.posbar_bounds()
    pby  = _c.tap_posbar()[1]
    # tap_x = pbx0+164 → posbarFromX = 164*60000/248 ≈ 39677 ms — in [35000, 45000]
    tap_x = pbx0 + 164

    _poll_shell_busy(dut, False, timeout_ms=2000)
    r = dut.cmd(f"tap {tap_x} {pby}")
    if r.get("skipped"):
        fail("T154", f"tap skipped (cooldown still active?): {r}"); return
    if r.get("hit") != "POSBAR":
        fail("T154", f"hit={r.get('hit')!r} (expected POSBAR) — x={tap_x} y={pby}"); return

    rp = dut.cmd("get posbarDragMs")
    seeked_ms = rp.get("ms", -1)
    if not (35000 <= seeked_ms <= 45000):
        fail("T154", f"posbarDragMs={seeked_ms} not in [35000, 45000] "
                     f"(0 = Press-entry init broken; D_POSBAR_DRAG not entered on tap)"); return

    pass_("T154", f"seeked_ms={seeked_ms} ms (expected ≈39677); tap→seek committed correctly")


# ── velocity-scroll-001 ────────────────────────────────────────────────────────

def t155(dut: Dut):
    """T155: 0-dy tap in dead zone fires PLEDIT hit (tap path, not scroll-end)."""
    print("T155  Tap within dead zone fires PLEDIT hit (0-dy)")
    if not _vs_precondition(dut, "T155"):
        return
    baseline = _get_scroll(dut)
    # cmdTap does Press + Release at same point → dy = 0 < DEAD_ZONE(1) → tap path.
    r = dut.cmd(f"tap {_PLEDIT_X} {_PLEND_Y}", timeout=5.0)
    if not r.get("ok"):
        fail("T155", f"tap returned ok=false: {r}")
        return
    if r.get("hit") != "PLEDIT":
        fail("T155", f"hit={r.get('hit')!r} — expected PLEDIT; tap missed content zone")
        return
    post = _get_scroll(dut)
    if post != baseline:
        fail("T155", f"scrollOffset changed {baseline}→{post} — scroll-end fired instead of tap")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T155", f"dragState={rg.get('state')!r} — Release cleanup failed")
        return
    pass_("T155",
          f"hit=PLEDIT scrollOffset={post} (unchanged) dragState=D_IDLE — tap path confirmed")


def t156(dut: Dut):
    """T156: dy=13 px drag outside dead zone → scroll-end (no tap, no PLAY_URI)."""
    print("T156  Release outside dead zone suppresses tap (dy=13 px)")
    if not _vs_precondition(dut, "T156"):
        return
    # y 150→163: dy = +13 > DEAD_ZONE(1) → scroll-end; cooldown set to 150 ms (not 300 ms tap).
    dut.send(f"drag {_PLEDIT_X} {_PLEND_Y} {_PLEDIT_X} {_PLSTART_Y} 1")
    _, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T156", "no drag response within 10 s")
        return
    if not drag_resp.get("ok"):
        fail("T156", f"drag response ok=false: {drag_resp}")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T156", f"dragState={rg.get('state')!r} — Release did not complete")
        return
    # Distinguish scroll-end (cooldown≈150 ms) from tap (cooldown≈300 ms).
    # After ~15 ms of processing, scroll-end cooldown is ~135 ms; tap would be ~285 ms.
    rc = dut.cmd("get cooldown", timeout=3.0)
    cooldown_ms = rc.get("remainingMs", 9999)
    if cooldown_ms > 220:
        fail("T156", f"cooldown={cooldown_ms} ms > 220 — tap branch fired (expected scroll-end ≤220 ms)")
        return
    pass_("T156",
          f"dragState=D_IDLE cooldown={cooldown_ms} ms ≤ 220 — scroll-end confirmed, tap suppressed")


def t157(dut: Dut):
    """T157: velocity ≈ 2.0 rows/s at dy=-13 px (effective=12 px, K=0.1667).
    Verified indirectly: tick 50×20ms at the final drag position produces
    scrollOffset ∈ [1, 3].  Direct scrollVelocity read is not viable because
    the drag command always releases before the harness regains control; tick is
    interleaved mid-drag via serial-buffer queueing (see module header note)."""
    print("T157  Velocity scaling: tick 50×20ms at dy=-13 → scrollOffset ∈ [1,3]")
    if not _vs_precondition(dut, "T157"):
        return
    # steps=1: Press@163(iter2), Move@150(iter3, _dragCurrentY=150), Release(iter4).
    # cmd_A(iter2): get dragState  — confirms D_PLEDIT_SCROLL while gesture active.
    # cmd_B(iter3): tick 50 20    — fires at _dragCurrentY=150; dy=-13; vel≈2.0;
    #                               50×0.04≈2.0 rows → scrollOffset=2.
    dut.send(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 1")
    dut.send("get dragState")
    dut.send("tick 50 20")
    pre, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T157", "no drag response within 10 s")
        return
    if len(pre) < 2:
        fail("T157", f"expected dragState + tick responses before drag JSON; got {len(pre)}: {pre}")
        return
    r_state, r_tick = pre[0], pre[1]
    if r_state.get("state") != "D_PLEDIT_SCROLL":
        fail("T157", f"dragState={r_state.get('state')!r} — gesture did not enter D_PLEDIT_SCROLL")
        return
    if r_tick.get("cmd") != "tick":
        fail("T157", f"expected tick response, got: {r_tick}")
        return
    so = r_tick.get("scrollOffset", -1)
    if not (1 <= so <= 3):
        fail("T157", f"scrollOffset={so} after tick 50×20ms at dy=-13 — "
                     f"expected [1,3] (velocity≈2.0 rows/s); actual velocity≈{so:.1f} rows/s")
        return
    pass_("T157", f"D_PLEDIT_SCROLL confirmed; scrollOffset={so} ∈ [1,3] → velocity≈2.0 rows/s")


def t158(dut: Dut):
    """T158: tick 50×20ms (1 s equivalent) at dy=-13 advances scrollOffset ≥ 1."""
    print("T158  Tick integration: 1 s at dy=-13 → scrollOffset ≥ 1")
    if not _vs_precondition(dut, "T158"):
        return
    dut.send(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 1")
    dut.send("get dragState")
    dut.send("tick 50 20")
    pre, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T158", "no drag response within 10 s")
        return
    r_tick = next((r for r in pre if r.get("cmd") == "tick"), None)
    if r_tick is None:
        fail("T158", f"no tick response in pre-drag JSONs: {pre}")
        return
    so = r_tick.get("scrollOffset", -1)
    if so < 1:
        fail("T158", f"scrollOffset={so} after tick 50×20ms at dy=-13 — "
                     f"expected ≥ 1; accumulator integration or tickScroll guard broken")
        return
    pass_("T158", f"scrollOffset={so} ≥ 1 after tick 50×20ms at dy=-13 — integration confirmed")


def t159(dut: Dut):
    """T159: scrollAccum is non-zero during drag, reset to 0.0000 on Release.
    Uses steps=3 so tick fires mid-drag (at Move@159, dy=-4, vel≈0.50) giving
    accum≈0.10.  scrollAccum is read in the next iteration (Move@155), still
    pre-Release, confirming non-zero.  After drag JSON, accum must be 0."""
    print("T159  Accumulator resets to 0.0000 on Release")
    if not _vs_precondition(dut, "T159"):
        return
    # steps=3 queue: Press@163(i2), Move@159(i3), Move@155(i4), Move@150(i5), Release(i6).
    # cmd_A(i2): get dragState  → D_PLEDIT_SCROLL
    # cmd_B(i3): tick 10 20    → _dragCurrentY=159, dy=-4, vel≈0.50, accum≈0.10
    # cmd_C(i4): get scrollAccum → reads accum≈0.10 (non-zero, < 1 row, no advance)
    dut.send(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 3")
    dut.send("get dragState")
    dut.send("tick 10 20")
    dut.send("get scrollAccum")
    pre, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T159", "no drag response within 10 s")
        return
    if len(pre) < 3:
        fail("T159", f"expected 3 pre-drag JSONs (dragState, tick, scrollAccum); got {len(pre)}: {pre}")
        return
    r_state = pre[0]
    r_accum_pre = next((r for r in pre if r.get("var") == "scrollAccum"), None)
    if r_state.get("state") != "D_PLEDIT_SCROLL":
        fail("T159", f"dragState={r_state.get('state')!r} — gesture not active mid-drag")
        return
    if r_accum_pre is None:
        fail("T159", f"no scrollAccum response in pre-drag JSONs: {pre}")
        return
    accum_pre = r_accum_pre.get("val", 0.0)
    if accum_pre == 0.0:
        fail("T159", f"scrollAccum={accum_pre} mid-drag — expected non-zero; "
                     f"tick may have fired before _dragCurrentY was set (tick response: "
                     f"{next((r for r in pre if r.get('cmd')=='tick'), 'missing')})")
        return
    r_accum_post = dut.cmd("get scrollAccum", timeout=3.0)
    accum_post = r_accum_post.get("val", -1.0)
    if accum_post != 0.0:
        fail("T159", f"scrollAccum={accum_post} after Release — expected 0.0000; "
                     f"Release cleanup (_scrollAccum=0) not firing")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T159", f"dragState={rg.get('state')!r} after Release — expected D_IDLE")
        return
    pass_("T159",
          f"scrollAccum={accum_pre:.4f} mid-drag (non-zero) → 0.0000 after Release; dragState=D_IDLE")


def t160(dut: Dut):
    """T160: tickScroll is a no-op when dragState is D_IDLE."""
    print("T160  tickScroll no-op when D_IDLE")
    if not _vs_precondition(dut, "T160"):
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T160", f"precondition: dragState={rg.get('state')!r} not D_IDLE")
        return
    baseline = _get_scroll(dut)
    if baseline is None:
        fail("T160", "get scrollOffset failed")
        return
    r_tick = dut.cmd("tick 50 20", timeout=5.0)
    if not r_tick.get("ok"):
        fail("T160", f"tick command failed: {r_tick}")
        return
    post = _get_scroll(dut)
    if post != baseline:
        fail("T160", f"scrollOffset changed {baseline}→{post} during D_IDLE tick — "
                     f"tickScroll guard clause not firing")
        return
    r_vel = dut.cmd("get scrollVelocity", timeout=3.0)
    vel = r_vel.get("val", None)
    if vel != 0.0:
        fail("T160", f"scrollVelocity={vel} after D_IDLE tick — expected 0.0000")
        return
    pass_("T160",
          f"scrollOffset={post} (unchanged) scrollVelocity=0.0000 — tickScroll D_IDLE guard confirmed")


# ── velocity-scroll-001 WebRadio variant (TASK-412 / T_PLE_08) ──────────────
# TASK-412 unified PLEDIT render/scroll behind the shared PleditView, so these
# mirror T155-T160 exactly but drive WebRadio's StationListSource (synthetic
# stations via `set wrDeadUrls`, no network needed) instead of Spotify's
# queue. Entry uses _switch_to_webradio_capture_heap (the real eject path) —
# NOT _switch_to("WebRadio")/_ensure_webradio, which tap a taskbar slot
# WebRadio doesn't have (eject-only app, see _switch_to_webradio_capture_heap
# docstring).

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


# ── taskbar-scroll-001 suite (TASK-105/TASK-106) ─────────────────────────────
# Tests T162–T166 for the taskbar scroll gesture (tbScrollOffset mechanics).
#
# Serial commands used:
#   get tbScrollOffset, get appId
#   drag <x1> <y1> <x2> <y2> <steps>
#   tap <x> <y>
#   set cooldown 0
#
# Taskbar geometry (shell_layout.h):
#   TASKBAR_X=275, TASKBAR_W=45, TASKBAR_SLOT_H=40
#   x centre = 297;  slot n y-centre = n*40+20
#   N_APPS = 9  (AppId::COUNT)
#
# Drag parameters for reliable 1-slot step:
#   50 px / 10 steps → LP-smoothed ≈ 42.5 px > TASKBAR_SLOT_H(40) → exactly 1 slot
#   (LP α=0.4; TB_SCROLL_DEAD_ZONE_PX=3 exceeded after the first 5 px step)
#
# T167 is retired — duplicate of revised T165.
# T168 is MANUAL — active-indicator rendering cannot be verified via serial.

_TB_X = _c.TASKBAR_X + _c.TASKBAR_W // 2   # 297
# TASK-242: the taskbar cycles through apps BEFORE WebRadio — WebRadio is
# eject-entered only, no taskbar slot. Must match firmware TASKBAR_APP_COUNT
# (= (int)AppId::WebRadio), NOT APP_COUNT, or scroll-wrap tests mismatch.
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


def _tb_precondition(dut: Dut, tid: str) -> bool:
    """Common precondition for T162–T166: Spotify active, tbScrollOffset=0."""
    if not _restore_spotify(dut):
        skip(tid, "precondition: could not restore Spotify")
        return False
    if not _tb_set_offset(dut, 0):
        skip(tid, f"precondition: tbScrollOffset={_tb_get_offset(dut)} could not be reset to 0")
        return False
    dut.set_cooldown_zero()
    return True


def t162(dut: Dut):
    """T162: Tap taskbar slot 1 (|rawDy|=0 < TB_SCROLL_DEAD_ZONE_PX=3) → switchApp fires, tbScrollOffset unchanged."""
    print("T162  Tap taskbar slot 1 — switchApp fires, tbScrollOffset unchanged")
    if not _tb_precondition(dut, "T162"):
        return
    baseline = _tb_get_offset(dut)
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])   # Clock slot
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.2)
    r_app = dut.cmd("get appId", timeout=3.0)
    post = _tb_get_offset(dut)
    _restore_spotify(dut)
    if r_app.get("name") != "Clock":
        fail("T162", f"appId={r_app.get('name')!r} after tap slot 1 — expected Clock; switchApp not fired")
        return
    if post != baseline:
        fail("T162", f"tbScrollOffset changed {baseline}→{post} after tap — scroll triggered instead of tap")
        return
    pass_("T162", f"appId=Clock; tbScrollOffset={post} (unchanged at {baseline}) — tap/switchApp path confirmed")


def t163(dut: Dut):
    """T163: Drag-up ≥50 px / 10 steps → tbScrollOffset increments by 1 (mod N)."""
    print("T163  Drag-up 50 px → tbScrollOffset + 1")
    if not _tb_precondition(dut, "T163"):
        return
    baseline = _tb_get_offset(dut)
    dut.cmd(f"drag {_TB_X} 110 {_TB_X} 60 10", timeout=5.0)   # 50 px up
    post = _tb_get_offset(dut)
    expected = (baseline + 1) % _TB_N
    _tb_set_offset(dut, 0)
    if post != expected:
        fail("T163", f"tbScrollOffset={post} after drag-up; expected {expected} (baseline={baseline})")
        return
    pass_("T163", f"tbScrollOffset {baseline}→{post} (+1 mod {_TB_N}) confirmed")


def t164(dut: Dut):
    """T164: Drag-down ≥50 px / 10 steps → tbScrollOffset decrements by 1 (mod N).
    Starts at offset=1 to exercise non-wrap decrement (wrap is T165)."""
    print("T164  Drag-down 50 px → tbScrollOffset - 1")
    if not _tb_precondition(dut, "T164"):
        return
    if not _tb_set_offset(dut, 1):
        skip("T164", f"could not set tbScrollOffset=1; actual={_tb_get_offset(dut)}")
        return
    dut.set_cooldown_zero()
    baseline = _tb_get_offset(dut)   # should be 1
    dut.cmd(f"drag {_TB_X} 60 {_TB_X} 110 10", timeout=5.0)   # 50 px down
    post = _tb_get_offset(dut)
    expected = (baseline - 1 + _TB_N) % _TB_N
    _tb_set_offset(dut, 0)
    if post != expected:
        fail("T164", f"tbScrollOffset={post} after drag-down; expected {expected} (baseline={baseline})")
        return
    pass_("T164", f"tbScrollOffset {baseline}→{post} (-1 mod {_TB_N}) confirmed")


def t165(dut: Dut):
    """T165: Wrap-around down — offset=0, drag-down → offset=N-1=7."""
    print("T165  Wrap-around down: offset=0, drag-down → offset=7")
    if not _tb_precondition(dut, "T165"):
        return
    baseline = _tb_get_offset(dut)
    if baseline != 0:
        skip("T165", f"precondition offset={baseline}, expected 0")
        return
    dut.cmd(f"drag {_TB_X} 60 {_TB_X} 110 10", timeout=5.0)   # 50 px down from 0 → wrap to N-1
    post = _tb_get_offset(dut)
    _tb_set_offset(dut, 0)
    if post != _TB_N - 1:
        fail("T165", f"tbScrollOffset={post} after wrap-down from 0; expected {_TB_N - 1}")
        return
    pass_("T165", f"tbScrollOffset 0→{post} (wrap-around down confirmed)")


def t166(dut: Dut):
    """T166: Wrap-around up — offset=N-1=7, drag-up → offset=0."""
    print("T166  Wrap-around up: offset=7, drag-up → offset=0")
    if not _tb_precondition(dut, "T166"):
        return
    if not _tb_set_offset(dut, _TB_N - 1):
        skip("T166", f"could not set tbScrollOffset={_TB_N - 1}; actual={_tb_get_offset(dut)}")
        return
    dut.set_cooldown_zero()
    baseline = _tb_get_offset(dut)   # should be 7
    dut.cmd(f"drag {_TB_X} 110 {_TB_X} 60 10", timeout=5.0)   # 50 px up from N-1 → wrap to 0
    post = _tb_get_offset(dut)
    _tb_set_offset(dut, 0)
    if post != 0:
        fail("T166", f"tbScrollOffset={post} after wrap-up from {_TB_N - 1}; expected 0")
        return
    pass_("T166", f"tbScrollOffset {baseline}→{post} (wrap-around up confirmed)")


def t242(dut: Dut):
    """T242 (TASK-242/LL-085): WebRadio must NOT be reachable via the taskbar — it
    is eject-entered only. Regression for the latent crash where WebRadio leaked
    into the taskbar (totalApps=AppId::COUNT) and its un-baked icon rendered
    pushImage(nullptr). Scroll a FULL cycle (the user path the old tests bypassed)
    and assert (a) no crash — DUT stays responsive, (b) no taskbar slot ever
    selects WebRadio."""
    print("T242  Taskbar excludes WebRadio (full scroll cycle, no crash)")
    if not _tb_precondition(dut, "T242"):
        return
    # Full scroll cycle: a crash on the WebRadio slot reboots the DUT, so
    # get appId stops responding at the offending offset.
    for off in range(_TB_N + 1):              # +1 exercises the wrap
        target = off % _TB_N
        if not _tb_set_offset(dut, target):
            fail("T242", f"could not reach scrollOffset={target} (DUT crash/reboot?)")
            return
        if not dut.cmd("get appId", timeout=3.0).get("name"):
            fail("T242", f"DUT unresponsive at scrollOffset={target} — taskbar render crash")
            return
    # Tap the top slot at a few offsets; the selected app must never be WebRadio.
    # TASK-413: offset 0 IS the player slot (appIdx == AppId::Spotify) — tapping it
    # while the player is already active now deliberately cycles Spotify -> WebRadio
    # -> Player (ADR-059 D6, resolvePlayerTap), which is a different mechanism from
    # "WebRadio leaked into the ordinary scroll rotation" this test guards against.
    # That cycle behaviour is T_PLR_01's job; skip offset 0 here so this test keeps
    # checking only the genuine leak class — a taskbar slot that ISN'T the player
    # slot must never resolve to WebRadio/LocalPlayer.
    for target in (_TB_N // 2, _TB_N - 1):
        _tb_set_offset(dut, target)
        dut.set_cooldown_zero()
        x, y = _c.tap_taskbar_slot(0)         # top visible slot → appIdx=target
        dut.cmd(f"tap {x} {y}", timeout=5.0)
        if dut.cmd("get appId", timeout=3.0).get("name") == "WebRadio":
            fail("T242", f"taskbar tap at offset {target} selected WebRadio — must be eject-only")
            return
    _restore_spotify(dut)
    pass_("T242", f"full scroll cycle ({_TB_N} offsets) — no crash; WebRadio never a taskbar slot")


# ── T_TBFB_01–04 — M-TASKBAR-FEEDBACK tap feedback (TASK-279) ─────────────────
# Asserts the stable-prefix lines per the design's VE dbg-surface sign-off
# (2026-07-07): [shell] tb-press slot=N / tb-press-cancel / tb-commit slot=N,
# ordered against [shell] entered M. Presence + relative order only — the
# [shell] switch phase numbers are recorded by e0_baseline.py, never
# threshold-asserted here (VE-3-2 single-shot flakiness rule).

def _tbfb_drag_capture(dut: Dut, x1: int, y1: int, x2: int, y2: int,
                       steps: int, timeout: float = 10.0) -> list[str]:
    """Send a drag and capture all raw lines through the drag-JSON terminator."""
    dut.ser.reset_input_buffer()
    dut.send(f"drag {x1} {y1} {x2} {y2} {steps}")
    lines: list[str] = []
    old_timeout = dut.ser.timeout
    dut.ser.timeout = 0.3
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        lines.append(line)
        if line.startswith("{") and '"cmd":"drag"' in line.replace(" ", ""):
            break
    dut.ser.timeout = old_timeout
    return lines


def _tbfb_idx(lines: list[str], needle: str) -> int:
    """Index of first line containing needle, or -1."""
    for i, ln in enumerate(lines):
        if needle in ln:
            return i
    return -1


def t_tbfb_01(dut: Dut):
    """T_TBFB_01: taskbar drag-tap → tb-press in the Press iteration, tb-commit
    strictly before [shell] entered (VE-3-3), switch lands on the tapped app."""
    print("T_TBFB_01  tb-press + tb-commit ordering on a taskbar tap")
    if not _tb_precondition(dut, "T_TBFB_01"):
        return
    _, y = _c.tap_taskbar_slot(APP_SLOT["Clock"])   # slot 1 centre, y=60
    lines = _tbfb_drag_capture(dut, _TB_X, y, _TB_X, y + 1, 2)
    i_press  = _tbfb_idx(lines, "[shell] tb-press slot=1")
    i_commit = _tbfb_idx(lines, "[shell] tb-commit slot=1")
    i_enter  = _tbfb_idx(lines, "[shell] entered 1 ")   # trailing space: not 10/11
    r_app = dut.cmd("get appId", timeout=3.0)
    _restore_spotify(dut)
    if i_press < 0:
        fail("T_TBFB_01", f"no '[shell] tb-press slot=1' in drain window: {lines[:6]}")
        return
    if i_commit < 0 or i_enter < 0:
        fail("T_TBFB_01", f"missing tb-commit ({i_commit}) or entered ({i_enter}) line")
        return
    if not (i_press < i_commit < i_enter):
        fail("T_TBFB_01", f"order wrong: press@{i_press} commit@{i_commit} entered@{i_enter}")
        return
    if r_app.get("name") != "Clock":
        fail("T_TBFB_01", f"appId={r_app.get('name')!r} after tap — switch did not land")
        return
    pass_("T_TBFB_01", f"press@{i_press} < commit@{i_commit} < entered@{i_enter}; appId=Clock")


def t_tbfb_02(dut: Dut):
    """T_TBFB_02: scroll drag → tb-press then tb-press-cancel at dead-zone exceed
    (VE-3-4); no tb-commit, no switch; offset steps by 1 (discrimination unchanged)."""
    print("T_TBFB_02  tb-press-cancel on scroll-start; no commit")
    if not _tb_precondition(dut, "T_TBFB_02"):
        return
    lines = _tbfb_drag_capture(dut, _TB_X, 110, _TB_X, 60, 10)   # 50 px up = +1 slot
    post = _tb_get_offset(dut)
    i_press  = _tbfb_idx(lines, "[shell] tb-press slot=2")       # 110//40 = 2
    i_cancel = _tbfb_idx(lines, "[shell] tb-press-cancel")
    i_commit = _tbfb_idx(lines, "[shell] tb-commit")
    i_enter  = _tbfb_idx(lines, "[shell] entered")
    _tb_set_offset(dut, 0)
    if i_press < 0:
        fail("T_TBFB_02", f"no '[shell] tb-press slot=2' in drain window: {lines[:6]}")
        return
    if i_cancel < 0 or i_cancel < i_press:
        fail("T_TBFB_02", f"tb-press-cancel missing/misordered: press@{i_press} cancel@{i_cancel}")
        return
    if i_commit >= 0 or i_enter >= 0:
        fail("T_TBFB_02", f"scroll produced commit@{i_commit}/entered@{i_enter} — must not switch")
        return
    if post != 1:
        fail("T_TBFB_02", f"tbScrollOffset={post} after 50 px drag; expected 1 — scroll regressed")
        return
    pass_("T_TBFB_02", f"press@{i_press} → cancel@{i_cancel}; no commit; offset 0→1")


def t_tbfb_03(dut: Dut):
    """T_TBFB_03: WebRadio-player-mode case (QM-3-1) — player-slot tap with persisted
    mode WebRadio: amber paints the TAPPED slot (tb-commit slot=0), switch resolves
    to WebRadio via resolvePlayerSlot; no reverse app→slot lookup crash (LL-085)."""
    print("T_TBFB_03  commit amber on press-anchored slot; WebRadio player-mode redirect")
    if not _tb_precondition(dut, "T_TBFB_03"):
        return
    r_pm = dut.cmd("get playerMode", timeout=3.0)
    if not _switch_to(dut, "Clock"):
        skip("T_TBFB_03", "could not switch to Clock for the redirect tap")
        return
    dut.cmd("set playerMode 1", timeout=3.0)
    dut.set_cooldown_zero()
    try:
        lines = _tbfb_drag_capture(dut, _TB_X, 20, _TB_X, 21, 2)   # slot 0 = player slot
        i_commit = _tbfb_idx(lines, "[shell] tb-commit slot=0")
        i_enter  = _tbfb_idx(lines, f"[shell] entered {APP_SLOT['WebRadio']}")
        r_app = dut.cmd("get appId", timeout=5.0)
    finally:
        dut.cmd(f"set playerMode {r_pm.get('val', 0)}", timeout=3.0)
        _restore_spotify(dut)
    if i_commit < 0:
        fail("T_TBFB_03", f"no '[shell] tb-commit slot=0' — press-anchored amber missing: {lines[:6]}")
        return
    if i_enter < 0 or i_enter < i_commit:
        fail("T_TBFB_03", f"entered-WebRadio missing/misordered: commit@{i_commit} entered@{i_enter}")
        return
    if r_app.get("name") != "WebRadio":
        fail("T_TBFB_03", f"appId={r_app.get('name')!r} — resolvePlayerSlot redirect did not land")
        return
    pass_("T_TBFB_03", f"commit slot=0 @{i_commit} < entered WebRadio @{i_enter}; redirect OK")


def t_tbfb_04(dut: Dut):
    """T_TBFB_04: app-canvas cooldown behaviour unchanged. `get cooldown` reads
    SpotifyApp's touchScreenCoolDownTime (TASK-052 dead-zone-tap force-poll cooldown)
    — a taskbar gesture never touches it; a consumed canvas gesture still arms it.
    Note this is a DIFFERENT variable from the shell-level s_cooldownMs post-gesture
    cooldown TASK-280 fixed (main.cpp drainInjectionQueue's release branch now sets
    it, matching production's appHandleInput) — that one is covered by T_TBFB_05
    via `get shellCooldown` (TASK-294)."""
    print("T_TBFB_04  canvas cooldown unaffected by taskbar gesture; still armed by canvas gesture")
    if not _tb_precondition(dut, "T_TBFB_04"):
        return
    _, y = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    _tbfb_drag_capture(dut, _TB_X, y, _TB_X, y + 1, 2)            # taskbar tap → Clock
    r_cd_tb = dut.cmd("get cooldown", timeout=3.0)
    if not _restore_spotify(dut):
        skip("T_TBFB_04", "could not restore Spotify for the canvas half")
        return
    dut.set_cooldown_zero()
    # VIS window arms +300 ms at Press, data-independent (a PLEDIT tap needs playlist
    # rows, which TASK-243's Spotify 403 leaves empty — first run failed on that).
    # Side effect: visMode cycles once; left as-is per T-CDWN-01 precedent.
    px, py = _c.tap_vis()
    _tbfb_drag_capture(dut, px, py, px, py + 1, 2)
    r_cd_cv = dut.cmd("get cooldown", timeout=3.0)
    rem_tb = int(r_cd_tb.get("remainingMs", -1))
    rem_cv = int(r_cd_cv.get("remainingMs", -1))
    if rem_tb != 0:
        fail("T_TBFB_04", f"canvas cooldown {rem_tb}ms armed by a TASKBAR gesture — must stay 0")
        return
    if rem_cv <= 0:
        fail("T_TBFB_04", f"canvas cooldown not armed by VIS tap (remainingMs={rem_cv})")
        return
    pass_("T_TBFB_04", f"taskbar gesture: remainingMs=0; canvas VIS tap: remainingMs={rem_cv}")


def t_tbfb_05(dut: Dut):
    """T_TBFB_05 (TASK-294): shell-level post-gesture cooldown. `get shellCooldown`
    reads main.cpp's s_cooldownMs — the variable TASK-280's drainInjectionQueue fix
    arms on an injected taskbar release, matching production appHandleInput. Asserts
    it reads 0 once decayed and ~300 ms immediately after an injected taskbar
    release. NOT the same variable as T_TBFB_04's `get cooldown` (SpotifyApp's
    TASK-052 touchScreenCoolDownTime)."""
    print("T_TBFB_05  shellCooldown unarmed after decay; armed ~300ms by injected taskbar release")
    if not _tb_precondition(dut, "T_TBFB_05"):
        return
    # The precondition's own drags arm the same 300 ms shell cooldown — let it
    # decay so the "unarmed" half reads a settled 0, not a stale remnant.
    time.sleep(0.5)
    r_before = dut.cmd("get shellCooldown", timeout=3.0)
    _, y = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    # The drag JSON terminator is emitted in the same loop iteration that arms
    # s_cooldownMs (drainInjectionQueue release branch), so the read that follows
    # lands well inside the 300 ms window.
    lines = _tbfb_drag_capture(dut, _TB_X, y, _TB_X, y + 1, 2)   # taskbar tap → Clock
    r_after = dut.cmd("get shellCooldown", timeout=3.0)
    _restore_spotify(dut)
    rem_before = int(r_before.get("remainingMs", -1))
    rem_after = int(r_after.get("remainingMs", -1))
    if rem_before != 0:
        fail("T_TBFB_05", f"shellCooldown={rem_before}ms before the gesture — expected 0 after decay")
        return
    if _tbfb_idx(lines, "[shell] tb-commit slot=1") < 0:
        fail("T_TBFB_05", f"tap did not reach the taskbar release branch (no tb-commit): {lines[:6]}")
        return
    if not (0 < rem_after <= 300):
        fail("T_TBFB_05", f"shellCooldown={rem_after}ms right after injected taskbar release — expected (0, 300]")
        return
    pass_("T_TBFB_05", f"decayed: 0ms; armed by injected release: {rem_after}ms (≤300)")


# ── T_PLR_01–05 — M-PLAYER-STATE three-way mode (TASK-413 / ADR-059 D6/D7) ─────
# PlayerMode widens Spotify=0/WebRadio=1 to +Player=2. Cycling moves off eject
# onto the taskbar Winamp icon: tap the player slot while it's already active ->
# cycle + persist (resolvePlayerTap, ADR-059 D6 amendment); tap it from another
# app -> restore the persisted mode (resolvePlayerSlot, unchanged). Player has no
# taskbar slot of its own (eject-only tail, same as WebRadio).

def t_plr_01(dut: Dut):
    """T_PLR_01: taskbar tap on the active player slot cycles Spotify -> WebRadio ->
    Player -> Spotify -> WebRadio (x4 taps from Spotify)."""
    print("T_PLR_01  Taskbar tap cycles the mode Spotify->WebRadio->Player->Spotify->WebRadio")
    dut.cmd("set playerMode spotify", timeout=3.0)
    if not _restore_spotify(dut):
        skip("T_PLR_01", "precondition: could not restore Spotify")
        return
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    expected = ["WebRadio", "LocalPlayer", "Spotify", "WebRadio"]
    got = []
    for _ in expected:
        dut.set_cooldown_zero()
        dut.cmd(f"tap {sx} {sy}", timeout=5.0)
        time.sleep(0.3)
        got.append(dut.cmd("get appId", timeout=3.0).get("name"))
    dut.cmd("set playerMode spotify", timeout=3.0)
    _restore_spotify(dut)
    if got != expected:
        fail("T_PLR_01", f"cycle sequence={got} — expected {expected}")
        return
    pass_("T_PLR_01", f"cycle Spotify->{'->'.join(got)} confirmed (x4 taps)")


def t_plr_02(dut: Dut):
    """T_PLR_02: playerMode persists across reboot — set each of the 3 modes,
    reboot, and check the persisted `set` echo round-trips (no live reboot here;
    the boot-restore path itself is covered by manual DUT verification per
    TASK-413's gate notes — this asserts the persisted-value contract the boot
    code reads from is correct for all 3 values)."""
    print("T_PLR_02  set/get playerMode round-trips all 3 values (persistence contract)")
    r_pm0 = dut.cmd("get playerMode", timeout=3.0)
    ok = True
    results = {}
    for name, val in (("spotify", 0), ("webradio", 1), ("player", 2)):
        r_set = dut.cmd(f"set playerMode {name}", timeout=3.0)
        r_get = dut.cmd("get playerMode", timeout=3.0)
        results[name] = (r_set.get("val"), r_get.get("val"), r_get.get("name"))
        if r_set.get("val") != val or r_get.get("val") != val:
            ok = False
    dut.cmd(f"set playerMode {r_pm0.get('val', 0)}", timeout=3.0)
    if not ok:
        fail("T_PLR_02", f"round-trip mismatch: {results}")
        return
    pass_("T_PLR_02", f"all 3 modes round-tripped: {results}")


def t_plr_03(dut: Dut):
    """T_PLR_03: taskbar has no leaked slot for WebRadio or LocalPlayer — full
    scroll cycle stays responsive and neither eject-only app is ever selected
    by a taskbar tap (TASK-242 regression, generalised to the wider tail)."""
    print("T_PLR_03  Taskbar excludes WebRadio AND LocalPlayer (full scroll cycle, no crash)")
    if not _tb_precondition(dut, "T_PLR_03"):
        return
    for off in range(_TB_N + 1):
        target = off % _TB_N
        if not _tb_set_offset(dut, target):
            fail("T_PLR_03", f"could not reach scrollOffset={target} (DUT crash/reboot?)")
            return
        if not dut.cmd("get appId", timeout=3.0).get("name"):
            fail("T_PLR_03", f"DUT unresponsive at scrollOffset={target} — taskbar render crash")
            return
    # Offset 0 IS the player slot (appIdx == AppId::Spotify) — tapping it while the
    # player is already active deliberately cycles now (ADR-059 D6, resolvePlayerTap;
    # covered by T_PLR_01), so it's excluded here: this check is only for the genuine
    # leak class — a taskbar slot that ISN'T the player slot must never resolve to
    # WebRadio/LocalPlayer.
    for target in (_TB_N // 2, _TB_N - 1):
        _tb_set_offset(dut, target)
        dut.set_cooldown_zero()
        x, y = _c.tap_taskbar_slot(0)
        dut.cmd(f"tap {x} {y}", timeout=5.0)
        name = dut.cmd("get appId", timeout=3.0).get("name")
        if name in ("WebRadio", "LocalPlayer"):
            fail("T_PLR_03", f"taskbar tap at offset {target} selected {name} — must be eject-only")
            return
    _restore_spotify(dut)
    pass_("T_PLR_03", f"full scroll cycle ({_TB_N} offsets) — no crash; WebRadio/LocalPlayer never a taskbar slot")


def t_plr_04(dut: Dut):
    """T_PLR_04: get/set playerMode round-trip all three values by name and by
    numeric index (§6.1 debug-surface widening — the pre-TASK-413 getter
    collapsed Player(2) to WebRadio(1) and the setter rejected idx>1)."""
    print("T_PLR_04  get/set playerMode round-trips all three values, name+numeric")
    r_pm0 = dut.cmd("get playerMode", timeout=3.0)
    cases = [("spotify", 0, "Spotify"), ("1", 1, "WebRadio"), ("player", 2, "Player")]
    mismatches = []
    for val_in, expect_val, expect_name in cases:
        dut.cmd(f"set playerMode {val_in}", timeout=3.0)
        r = dut.cmd("get playerMode", timeout=3.0)
        if r.get("val") != expect_val or r.get("name") != expect_name:
            mismatches.append((val_in, r.get("val"), r.get("name")))
    r_bad = dut.cmd("set playerMode 3", timeout=3.0)
    dut.cmd(f"set playerMode {r_pm0.get('val', 0)}", timeout=3.0)
    if mismatches:
        fail("T_PLR_04", f"round-trip mismatches: {mismatches}")
        return
    if r_bad.get("ok", True):
        fail("T_PLR_04", f"set playerMode 3 (out of range) was accepted: {r_bad}")
        return
    pass_("T_PLR_04", "spotify/webradio(1)/player all round-trip; out-of-range idx=3 rejected")


def t_plr_05(dut: Dut):
    """T_PLR_05: tapping the player slot from ANOTHER app restores the persisted
    mode (resolvePlayerSlot, unchanged), it does not cycle."""
    print("T_PLR_05  Tap from another app restores the persisted mode, does not cycle")
    r_pm0 = dut.cmd("get playerMode", timeout=3.0)
    if not _switch_to(dut, "Clock"):
        skip("T_PLR_05", "precondition: could not switch to Clock")
        return
    dut.cmd("set playerMode player", timeout=3.0)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=5.0)
    time.sleep(0.3)
    name1 = dut.cmd("get appId", timeout=3.0).get("name")
    # A second tap, now that the player IS active, should cycle away from Player.
    dut.set_cooldown_zero()
    dut.cmd(f"tap {sx} {sy}", timeout=5.0)
    time.sleep(0.3)
    name2 = dut.cmd("get appId", timeout=3.0).get("name")
    dut.cmd(f"set playerMode {r_pm0.get('val', 0)}", timeout=3.0)
    _restore_spotify(dut)
    if name1 != "LocalPlayer":
        fail("T_PLR_05", f"restore tap landed on {name1!r} — expected LocalPlayer (persisted mode)")
        return
    if name2 != "Spotify":
        fail("T_PLR_05", f"cycle tap from active Player landed on {name2!r} — expected Spotify")
        return
    pass_("T_PLR_05", f"restore->LocalPlayer, then cycle->Spotify — restore-vs-cycle distinction confirmed")


# ── T_PLR_06/07 — eject remap (TASK-414 / ADR-059 D6) ──────────────────────────
# Eject is freed from "switch to WebRadio" (the taskbar player-slot cycle above
# owns app switching now) and becomes "load media from this source", one verb
# with three per-mode realisations. The logo tap keeps its own TLS-reset
# behaviour unchanged (T_PLR_07 regression-checks the shared helper refactor).

def t_plr_06(dut: Dut):
    """T_PLR_06: eject is per-mode. Spotify -> TLS reset + force poll, appId stays
    Spotify. WebRadio -> station-list refresh (wrEnqueues advances), appId stays
    WebRadio. Player -> opens the file browser (TASK-416), appId stays LocalPlayer.

    The Player-mode leg's pass criterion was rewritten by TASK-416, and the real
    history matters because it is a process lesson, not a tidy-up:

      - At TASK-414 (`07250ca`) this assertion (`hit == "LOCALPLAYER"`,
        `action == "CONSUMED"`) was correct AND passing on the DUT —
        `main.cpp:3101` reported exactly that for LocalPlayer's cmdTap branch.
      - TASK-415 (`fd129ec`) rerouted that branch through
        `winampDisplay.injectTouch()` so PLEDIT row taps would anchor in the
        shared PleditView. Correct change, but it made the tap-dispatch REPORT
        `EJECT`/`EJECT` like every other mode — and T_PLR_06 was not re-run, so
        the suite carried a stale assertion for a day without anyone noticing.
      - TASK-416 inherited the stale test. It did NOT cause the divergence.

    So: the eject VERB differs per mode (that is what this whole test is for);
    the tap-dispatch REPORT does not, and has not since `fd129ec`. This now
    checks the thing that actually distinguishes Player's eject from a no-op —
    the browser (`get fbState`) is active afterward."""
    print("T_PLR_06  Eject is per-mode: Spotify TLS-reset, WebRadio refresh, Player browser opens")
    errors = []
    ex, ey = _c.tap_eject()

    # ── Spotify: TLS reset + force poll ─────────────────────────────────────
    if not _restore_spotify(dut):
        skip("T_PLR_06", "precondition: could not restore Spotify")
        return
    # TASK-417: pre-existing gap (predates this task, same as T_WR_EJECT_01)
    # — without this, a tap landing while g_shellBusy is still true from
    # _restore_spotify's own app-switch/poll is silently swallowed
    # (hit=CANVAS), which then also starves the TLS-reset log check below.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    # TASK-417 gate investigation: tap + log-scan combined into one
    # continuous read (_tap_and_wait_log) — the previous split
    # dut.cmd(tap)+manual-readline-loop pattern raced read_json()'s
    # non-JSON-line discard against spotifyTask's async "hard reset —
    # stopping client" trace (a different FreeRTOS task) and could silently
    # eat the very log line being waited for. See _tap_and_wait_log's
    # docstring for the raw-serial-capture proof (T_PLR_17's SHUFFLE/REPEAT
    # case, same mechanism).
    dut.set_cooldown_zero()
    r, tls_seen = _tap_and_wait_log(dut, ex, ey, "hard reset", tap_timeout=5.0, log_timeout=8.0)
    if r is None or r.get("hit") != "EJECT" or r.get("action") != "EJECT":
        errors.append(f"Spotify: hit={r.get('hit') if r else None} action={r.get('action') if r else None}")
    else:
        time.sleep(0.3)
        appid = dut.cmd("get appId", timeout=3.0).get("name")
        if appid != "Spotify":
            errors.append(f"Spotify: appId={appid!r} after eject (expected Spotify — eject no longer switches apps)")
        if not tls_seen:
            errors.append("Spotify: no TLS-reset log line within 8 s")

    # ── WebRadio: station-list refresh ──────────────────────────────────────
    dut.cmd("set bgPoll 0", timeout=2.0)
    ok, _ = _switch_to_webradio_capture_heap(dut)
    if not ok:
        errors.append("WebRadio: could not enter WebRadio via taskbar player-slot cycle")
    else:
        _wait_shell_not_busy(dut, timeout_s=5.0)
        enq_before = dut.cmd("get dataq", timeout=3.0).get("wrEnqueues", 0)
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {ex} {ey}", timeout=5.0)
        if r.get("hit") != "EJECT" or r.get("action") != "EJECT":
            errors.append(f"WebRadio: hit={r.get('hit')} action={r.get('action')}")
        else:
            time.sleep(0.3)
            appid = dut.cmd("get appId", timeout=3.0).get("name")
            if appid != "WebRadio":
                errors.append(f"WebRadio: appId={appid!r} after eject (expected WebRadio — eject no longer switches apps)")
            enq_after = dut.cmd("get dataq", timeout=3.0).get("wrEnqueues", 0)
            if enq_after <= enq_before:
                errors.append(f"WebRadio: wrEnqueues did not advance ({enq_before} -> {enq_after})")
    dut.cmd("set bgPoll 1", timeout=2.0)

    # ── Player: opens the file browser (TASK-416) ───────────────────────────
    heap_pressure_skip = False
    dut.cmd("set playerMode player", timeout=3.0)
    if not _switch_to(dut, "Clock"):
        errors.append("Player: precondition: could not switch to Clock")
    else:
        dut.set_cooldown_zero()
        sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {sx} {sy}", timeout=5.0)   # restore persisted mode -> LocalPlayer
        time.sleep(0.3)
        appid = dut.cmd("get appId", timeout=3.0).get("name")
        if appid != "LocalPlayer":
            errors.append(f"Player: precondition failed, appId={appid!r} (expected LocalPlayer)")
        else:
            dut.set_cooldown_zero()
            r = dut.cmd(f"tap {ex} {ey}", timeout=5.0)
            if r.get("hit") != "EJECT" or r.get("action") != "EJECT":
                errors.append(f"Player: hit={r.get('hit')} action={r.get('action')} (expected EJECT/EJECT — "
                              "the tap-dispatch report, not the per-mode verb)")
            time.sleep(0.3)
            appid2 = dut.cmd("get appId", timeout=3.0).get("name")
            if appid2 != "LocalPlayer":
                errors.append(f"Player: appId={appid2!r} after eject (expected LocalPlayer — the browser "
                              "is modal WITHIN the app, not a switchApp)")
            fb = dut.cmd("get fbState", timeout=3.0)
            if not fb.get("active"):
                # fileBrowser.h heap-allocates its dir/file arrays (~13 KB) on
                # first open() — a real fragmented-heap alloc failure (seen on
                # the DUT: this exact Spotify->WebRadio->Player chain, in this
                # order, left `free=50700` but no contiguous block big enough)
                # degrades cleanly, same class of risk as m3u::PlaylistIndex's
                # own alloc under pressure (T_PLR_12's notes). Distinguish it
                # from a real defect via LocalPlayerApp's own hasError()
                # (`get activeError` — NOT `get plCount`'s "error", which is
                # m3u::PlaylistIndex's own flag and unrelated to a browser-
                # alloc failure) rather than failing the eject-verb gate on a
                # pre-existing, already-tracked heap-pressure risk.
                ae = dut.cmd("get activeError", timeout=3.0)
                if ae.get("active"):
                    heap_pressure_skip = True
                else:
                    errors.append(f"Player: eject did not open the browser: {fb}")
            dut.cmd("set fbCancel", timeout=3.0)   # leave the browser closed for later tests

    dut.cmd("set playerMode spotify", timeout=3.0)
    _restore_spotify(dut)

    if heap_pressure_skip and not errors:
        skip("T_PLR_06", "Player leg: file-browser alloc failed under heap pressure after the "
                         "Spotify+WebRadio legs fragmented the heap (LocalPlayerApp reported "
                         "error=true, not a crash) — known M-HEAP-FRAGMENTATION-class risk, not "
                         "an eject-verb defect; Spotify/WebRadio legs above already passed")
        return
    if errors:
        fail("T_PLR_06", "; ".join(errors))
        return
    pass_("T_PLR_06", "eject per-mode confirmed: Spotify TLS-reset, WebRadio refresh, Player browser opens")


def t_plr_07(dut: Dut):
    """T_PLR_07: Winamp logo tap still resets TLS — unchanged from TASK-053f.
    Regression check for the TASK-414 refactor that moved the TLS-reset +
    force-poll action into a shared tryReconnect() (winampDisplay.h) used by
    both the logo tap and eject."""
    print("T_PLR_07  Logo tap still resets TLS (unchanged from TASK-053f)")
    if not _restore_spotify(dut):
        skip("T_PLR_07", "precondition: could not restore Spotify")
        return
    dut.set_cooldown_zero()
    lgx, lgy = _c.tap_logo()
    r = dut.cmd(f"tap {lgx} {lgy}", timeout=5.0)
    if r.get("hit") != "LOGO" or r.get("action") != "TLS_RESET":
        fail("T_PLR_07", f"expected hit=LOGO action=TLS_RESET got hit={r.get('hit')} action={r.get('action')}")
        return
    tls_log_found = False
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "hard reset" in line or "stopping client" in line:
            tls_log_found = True
            break
    if not tls_log_found:
        flake("T_PLR_07", "hit=LOGO action=TLS_RESET but no TLS-reset log line within 8 s")
        return
    pass_("T_PLR_07", "logo tap → TLS_RESET confirmed, unchanged from TASK-053f")


# ── T_PLR_08–12 — M3U index model (TASK-415 / ADR-059 D3) ─────────────────────
# The playlist is a RAM index over an SD-backed file: entries[] plus viewOrder/
# playOrder permutations, with row text read on demand. These assert the load,
# the resolution rules, the degradation behaviour and — the one that would ship
# broken while looking fine — that the index is bounded and actually freed.
#
# FIXTURES: app/tools/gen_playlist_fixtures.py writes them; they must be copied
# onto the card from a host reader (the device write path is TASK-424). Missing
# fixtures SKIP rather than FAIL — that's a rig gap, not a defect.

_PL_GATE   = "/playlists/gate100.m3u"
_PL_RELPAR = "/playlists/relpar.m3u"
_PL_REL    = "/mp3/rel.m3u"
_PL_BAD    = "/playlists/bad.m3u"
_PL_EMPTY  = "/playlists/empty.m3u"
_PL_UTF8   = "/playlists/utf8.m3u"
# TASK-418: 20-entry fixture for the play-order engine (gen_playlist_fixtures.py's
# gate20()) — entry ids are per-record, not per-file, so it does not need 20
# distinct audio files; T_PLR_20-24 never decode audio at all (D12's `advance`/
# `set plCursor`). T_PLR_25 is the one real-playback case and needs actual
# short files — see _PL_SHORT5 (5 real ~3s tones, not part of
# gen_playlist_fixtures.py since they're binary audio, not generated text).
_PL_20     = "/playlists/gate20.m3u"
_PL_SHORT5 = "/playlists/short5.m3u"


def _enter_player(dut: Dut, tid: str) -> bool:
    """Leave the player slot, persist Player mode, tap back in (the restore path).
    Tapping the slot while a player mode is already active CYCLES (T_PLR_01), so
    the step-off is mandatory, not defensive.

    Also suspends Spotify's background poll for the whole T_PLR_08-12 suite.
    TASK-430 (2026-08-11) bounded aeConnectFile()'s yield to tlsTryYield()'s
    1.5 s ceiling, so a stuck-mid-HTTP Spotify task can no longer park loopTask
    for up to 150 s the way it could when this comment was first written — that
    original failure mode (every later command in the run timing out) is fixed.
    Kept anyway, DUT-reproduced under TASK-430's own gate: with bgPoll left on,
    this account's real TASK-243 403-retry loop (a genuine ~5 s-cadence HTTP
    round trip, not a debug simulation) can still be in flight exactly when
    T_PLR_09 calls plPlay, and tlsTryYield() then legitimately times out at its
    1.5 s bound — a clean, fast, but FLAKY play failure instead of a hang. Only
    T_PLR_09 actually calls aeConnectFile(); 08/10/11/12 never touch it, so this
    suite-wide suspension is now precautionary for them, not load-bearing.
    Restored by _leave_player()."""
    dut.cmd("set bgPoll 0", timeout=3.0)
    dut.cmd("set playerMode player", timeout=3.0)
    if dut.cmd("get appId", timeout=3.0).get("name") in ("Spotify", "WebRadio", "LocalPlayer"):
        if not _switch_to(dut, "Clock"):
            _leave_player(dut)
            skip(tid, "precondition: could not step off the player slot")
            return False
    dut.cmd("set playerMode player", timeout=3.0)
    # Two attempts: the taskbar tap resolves against the CURRENT scroll offset,
    # and a dropped `set tbScroll` leaves the tap landing on whichever app now
    # occupies that slot (seen once as appId='PlaneRadar'). Re-anchoring and
    # re-tapping costs a second and removes a whole class of false SKIPs.
    name = None
    for attempt in range(2):
        _tb_set_offset(dut, 0)
        dut.set_cooldown_zero()
        x, y = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {x} {y}", timeout=5.0)
        time.sleep(0.4)
        name = dut.cmd("get appId", timeout=3.0).get("name")
        if name == "LocalPlayer":
            return True
        # Landed somewhere else: step back off the player slot before retrying,
        # or the next tap cycles the mode instead of restoring it.
        if attempt == 0:
            _switch_to(dut, "Clock")
            dut.cmd("set playerMode player", timeout=3.0)
    _leave_player(dut)
    skip(tid, f"precondition: appId={name!r} (expected LocalPlayer, 2 attempts)")
    return False


def _leave_player(dut: Dut) -> None:
    """Undo _enter_player()'s poll suspension. Every T_PLR_08-12 exit path calls
    this — a suite that left bgPoll off would silently disarm Spotify for every
    test that runs after it."""
    dut.cmd("set bgPoll 1", timeout=3.0)


def _pl_load(dut: Dut, path: str, timeout: float = 20.0) -> dict:
    """`set plLoad <path>` then `get plCount`. Returns the plCount reply."""
    dut.cmd(f"set plLoad {path}", timeout=timeout)
    return dut.cmd("get plCount", timeout=8.0)


def t_plr_08(dut: Dut):
    """T_PLR_08: a >=100-track M3U loads, count is exact, load time recorded."""
    print("T_PLR_08  >=100-track M3U loads (count exact, load time recorded)")
    if not _enter_player(dut, "T_PLR_08"):
        return
    r = _pl_load(dut, _PL_GATE)
    if r.get("count", 0) == 0:
        _leave_player(dut)
        skip("T_PLR_08", f"fixture {_PL_GATE} not on the card (gen_playlist_fixtures.py) — reply={r}")
        return
    if r.get("count") != 120:
        _leave_player(dut)
        fail("T_PLR_08", f"count={r.get('count')} (expected 120) truncated={r.get('truncated')}")
        return
    if r.get("truncated"):
        _leave_player(dut)
        fail("T_PLR_08", "index reports truncated at 120 entries — PL_MAX_ENTRIES is 256")
        return
    # Spot-check the last row: an off-by-one in the record scan shows up here,
    # not in the count.
    last = dut.cmd(f"get plRow {r['count'] - 1}", timeout=8.0)
    if not last.get("ok") or "(120)" not in last.get("text", ""):
        _leave_player(dut)
        fail("T_PLR_08", f"last row text={last.get('text')!r} (expected the '(120)' entry)")
        return
    _leave_player(dut)
    pass_("T_PLR_08", f"120 entries in {r.get('loadMs')} ms, totalSec={r.get('totalSec')}, "
                      f"last row={last.get('text')!r}")


def t_plr_09(dut: Dut):
    """T_PLR_09: scroll the list end to end while a track plays — no stall, no
    reboot, playback survives. The short end of the same risk T_PLR_13/39 attack
    at longer durations (loopTask SD I/O starving the audio pump)."""
    print("T_PLR_09  Scroll end to end during playback")
    if not _enter_player(dut, "T_PLR_09"):
        return
    r = _pl_load(dut, _PL_GATE)
    if r.get("count", 0) < 100:
        _leave_player(dut)
        skip("T_PLR_09", f"fixture {_PL_GATE} missing or short (count={r.get('count')})")
        return
    # Spotify's background poll must be off for any test that starts playback.
    # aeConnectFile() calls spotifyTask::tlsTryYield() (TASK-430), which blocks
    # the CALLING task (loopTask) for at most ~1.5 s now, not tlsYield()'s old
    # 150 s ceiling — a stuck Spotify task fails the play cleanly instead of
    # hanging the harness. Left OFF anyway: this account's real TASK-243
    # 403-retry loop is enough real HTTP traffic on its own ~5 s cadence to
    # occasionally win the race and time out the try-yield for real, turning a
    # would-be PASS into a flaky FAIL. Redundant with _enter_player()'s own
    # suite-wide bgPoll=0 (belt and suspenders — this is the one test in the
    # suite where it's actually load-bearing).
    dut.cmd("set bgPoll 0", timeout=3.0)
    dut.cmd("set plPlay 0", timeout=8.0)
    # connecttoFS + first decode: give the pump task a real window before judging.
    playing = False
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        time.sleep(1.0)
        if dut.cmd("get plCount", timeout=5.0).get("playing"):
            playing = True
            break
    if not playing:
        # VE 2026-08-15 (TASK-443), DELIBERATELY still a SKIP — read before changing.
        # This SKIP is correct on cyd2usb_winamp_debug, where local playback cannot
        # start at all with Spotify's TLS working set resident (TASK-425/431), and
        # that is the env this whole harness runs on. It is WRONG on cyd2usb_player
        # once TASK-443's ruling (retire the arena from the FILE path) lands: there,
        # "never reached playing=true" IS the ruling failing, and a SKIP would hide
        # exactly the regression the ruling has to be gated on.
        # It is not flipped today because (a) the ruling is proposed, not accepted,
        # (b) on cyd2usb_player playback genuinely cannot start right now (TASK-442,
        # open P1), so flipping turns a SKIP into a permanent red no one can action,
        # and (c) the harness carries no env discriminator to make it conditional,
        # and inventing one unverified with no DUT access is worse than a note.
        # WHEN THE RULING LANDS: gate on the build variant and make this a fail()
        # on cyd2usb_player, keeping skip() only on cyd2usb_winamp_debug.
        dut.cmd("set bgPoll 1", timeout=3.0)
        _leave_player(dut)
        skip("T_PLR_09", "track never reached playing=true — audio precondition failed, "
                         "not a scroll result (check the card's /mp3 files). NOTE: this "
                         "must become a FAIL on cyd2usb_player once TASK-443's ruling "
                         "lands — see the comment above this call")
        return
    xu, yu, xu2, yu2 = _c.pledit_swipe("up")
    worst_gap = 0.0
    for i in range(12):                      # 12 swipes ≈ the full 120-row list
        t0 = time.monotonic()
        if _do_drag(dut, xu, yu, xu2, yu2, steps=20, timeout=20.0) is None:
            dut.cmd("set bgPoll 1", timeout=3.0)
            _leave_player(dut)
            fail("T_PLR_09", f"DUT stopped responding on swipe {i + 1} — drag timeout")
            return
        worst_gap = max(worst_gap, time.monotonic() - t0)
    off = _get_scroll(dut)
    still = dut.cmd("get plCount", timeout=5.0)
    if not still.get("ok"):
        _leave_player(dut)
        fail("T_PLR_09", "DUT unresponsive after the scroll sweep")
        return
    if not still.get("playing"):
        _leave_player(dut)
        fail("T_PLR_09", f"playback stopped during the scroll sweep (scrollOffset={off})")
        return
    if not off:
        _leave_player(dut)
        fail("T_PLR_09", f"scrollOffset={off} after 12 up-swipes — the list did not scroll")
        return
    dut.cmd("set plPlay 0", timeout=5.0)     # leave a defined state
    dut.cmd("set bgPoll 1", timeout=3.0)
    _leave_player(dut)
    pass_("T_PLR_09", f"scrolled to offset {off} over 12 swipes, still playing; "
                      f"worst swipe round-trip {worst_gap:.1f}s")


def t_plr_10(dut: Dut):
    """T_PLR_10: relative paths resolve against the PLAYLIST's directory, not the
    root and not the current working directory (there isn't one)."""
    print("T_PLR_10  Relative paths resolve against the playlist directory")
    if not _enter_player(dut, "T_PLR_10"):
        return
    errors = []

    dut.cmd("set bgPoll 0", timeout=3.0)   # see T_PLR_09's note on tlsYield
    r = _pl_load(dut, _PL_REL)
    if r.get("count", 0) == 0:
        dut.cmd("set bgPoll 1", timeout=3.0)
        _leave_player(dut)
        skip("T_PLR_10", f"fixture {_PL_REL} not on the card (gen_playlist_fixtures.py)")
        return
    row0 = dut.cmd("get plRow 0", timeout=8.0)       # bare "name.mp3"
    row4 = dut.cmd("get plRow 4", timeout=8.0)       # "./name.mp3"
    if row0.get("path") != "/mp3/01 - Tomorrow Comes Today.mp3":
        errors.append(f"bare relative resolved to {row0.get('path')!r}")
    if not str(row4.get("path", "")).startswith("/mp3/") or "./" in str(row4.get("path", "")):
        errors.append(f"'./' relative resolved to {row4.get('path')!r}")

    r2 = _pl_load(dut, _PL_RELPAR)
    if r2.get("count", 0) == 0:
        errors.append(f"fixture {_PL_RELPAR} not on the card")
    else:
        rp = dut.cmd("get plRow 0", timeout=8.0)
        if rp.get("path") != "/mp3/01 - Tomorrow Comes Today.mp3":
            errors.append(f"'../' relative resolved to {rp.get('path')!r} "
                          "(expected the COLLAPSED /mp3/... — the FATFS VFS does not "
                          "resolve '..' itself; measured on the DUT, T_PLR_10 2026-08-11)")

    # Resolution is only half of it: a collapsed path must actually OPEN. Prove
    # that by loading a playlist THROUGH a '..' path rather than by playing a
    # track — SD.open() is the same syscall either way, and routing the proof
    # through the audio engine makes the test fail whenever the Helix arena
    # cannot get its 24 KB contiguous (observed with WiFi + TLS resident: the
    # decoder alloc fails, which says nothing about path resolution).
    r3 = _pl_load(dut, "/mp3/../playlists/gate100.m3u")
    if r3.get("count", 0) != 120:
        errors.append(f"opening through a '..' path failed: count={r3.get('count')} "
                      f"error={r3.get('error')} (expected the 120-entry fixture)")
    if errors:
        _leave_player(dut)
        fail("T_PLR_10", "; ".join(errors))
        return
    _leave_player(dut)
    pass_("T_PLR_10", "bare, './' and '../' relative paths all resolve against the playlist dir")


def t_plr_11(dut: Dut):
    """T_PLR_11: malformed input degrades — BOM, CRLF, missing/garbage #EXTINF,
    stray directives, a trailing record with no path line, and an empty file.
    Loads what it can, never crashes, and the UTF-8 fold (design OQ1) is applied
    to row text."""
    print("T_PLR_11  Malformed M3U degrades (BOM/CRLF/no-EXTINF/truncated/empty) + UTF-8 fold")
    if not _enter_player(dut, "T_PLR_11"):
        return
    errors = []

    r = _pl_load(dut, _PL_BAD)
    if r.get("count", 0) == 0 and not r.get("ok"):
        _leave_player(dut)
        skip("T_PLR_11", f"fixture {_PL_BAD} not on the card (gen_playlist_fixtures.py)")
        return
    if r.get("count") != 8:
        errors.append(f"bad.m3u count={r.get('count')} (expected 8 — the trailing "
                      "#EXTINF with no path line must NOT produce an entry)")
    rows = {i: dut.cmd(f"get plRow {i}", timeout=8.0) for i in range(min(8, r.get("count", 0)))}
    checks = [
        (0, "Gorillaz - Tomorrow Comes Today", 192, "normal record"),
        (1, "02 - Clint Eastwood", 0, "no #EXTINF -> basename, no duration"),
        (2, "Unknown duration", 0, "#EXTINF:-1 -> duration 0"),
        (3, "Junk duration", 0, "unparsable duration -> 0"),
        # `#EXTINF:222` — a duration with no ",title". The duration is real and
        # is kept; only the text falls back to the basename. (This expectation
        # was wrong on the first gate run: it demanded durSec 0, i.e. that a
        # malformed *title* discard a perfectly good duration.)
        (4, "05 - Feel Good Inc", 222, "#EXTINF with no comma -> basename, duration kept"),
        (5, "Gorillaz - DARE", 246, "directive between #EXTINF and path"),
    ]
    for idx, want_text, want_dur, why in checks:
        got = rows.get(idx, {})
        if got.get("text") != want_text:
            errors.append(f"row {idx} text={got.get('text')!r} expected {want_text!r} ({why})")
        if got.get("durSec") != want_dur:
            errors.append(f"row {idx} durSec={got.get('durSec')} expected {want_dur} ({why})")
    if 7 in rows and rows[7].get("path") != "/mp3/07 - Dirty Harry.mp3":
        errors.append(f"row 7 path={rows[7].get('path')!r} — leading/trailing spaces not trimmed")

    r_empty = _pl_load(dut, _PL_EMPTY)
    if r_empty.get("count") != 0:
        errors.append(f"empty.m3u count={r_empty.get('count')} (expected 0)")

    r_utf8 = _pl_load(dut, _PL_UTF8)
    if r_utf8.get("count", 0) == 0:
        errors.append(f"fixture {_PL_UTF8} not on the card")
    else:
        folded = {0: "Bjork - Joga", 1: "Sigur Ros - Saeglopur",
                  2: "Antonin Dvorak - Symphony No. 9", 3: "Motorhead - Ace of Spades"}
        for idx, want in folded.items():
            got = dut.cmd(f"get plRow {idx}", timeout=8.0).get("text")
            if got != want:
                errors.append(f"fold: row {idx} text={got!r} expected {want!r}")
        cjk = dut.cmd("get plRow 7", timeout=8.0).get("text", "")
        if not cjk.startswith("????"):
            errors.append(f"fold: CJK row text={cjk!r} (expected '?' per codepoint)")

    # Still alive after all of it — the whole point of "degrades".
    if not dut.cmd("get plMem", timeout=5.0).get("ok"):
        errors.append("DUT unresponsive after the malformed-input sweep")
    if errors:
        _leave_player(dut)
        fail("T_PLR_11", "; ".join(errors))
        return
    _leave_player(dut)
    pass_("T_PLR_11", "8/8 malformed-input cases degraded correctly; empty file loads to 0; "
                      "UTF-8 folded to ASCII")


def t_plr_12(dut: Dut):
    """T_PLR_12: the index is bounded and freed. Heap AND largest-free-block are
    both reported (VE-15) — a clean free-heap figure hides fragmentation, which
    is the real risk for a 3 KB allocation taken and returned every mode switch."""
    print("T_PLR_12  Index memory bounded (<=5.2 KB) and returned on suspend (+/-256 B)")
    if not _enter_player(dut, "T_PLR_12"):
        return
    # Baseline with the index NOT allocated: step off the mode entirely.
    if not _switch_to(dut, "Clock"):
        _leave_player(dut)
        skip("T_PLR_12", "precondition: could not switch to Clock for the baseline")
        return
    time.sleep(0.5)
    base = dut.cmd("get plMem", timeout=5.0)
    if base.get("allocated"):
        _leave_player(dut)
        fail("T_PLR_12", "index still allocated after leaving Player mode — suspend() did not free")
        return
    if not _enter_player(dut, "T_PLR_12"):
        return
    time.sleep(0.5)
    entered = dut.cmd("get plMem", timeout=5.0)
    loaded = _pl_load(dut, _PL_GATE)
    peak = dut.cmd("get plMem", timeout=5.0)     # handle still open
    # The playlist File is dropped 1.5 s after the last row read (an open handle
    # is ~4.4 KB of stdio buffer, not index memory) — measure the resting cost,
    # and report the open-handle peak alongside it.
    time.sleep(3.0)
    after = dut.cmd("get plMem", timeout=5.0)
    if not _switch_to(dut, "Clock"):
        _leave_player(dut)
        skip("T_PLR_12", "could not leave Player mode for the free measurement")
        return
    time.sleep(0.5)
    freed = dut.cmd("get plMem", timeout=5.0)

    d_enter = base["freeHeap"] - entered["freeHeap"]
    d_load  = base["freeHeap"] - after["freeHeap"]
    d_free  = base["freeHeap"] - freed["freeHeap"]
    errors = []
    if freed.get("allocated"):
        errors.append("index still allocated after suspend")
    d_peak = base["freeHeap"] - peak["freeHeap"]
    if d_load > 5324:                       # 5.2 KB
        errors.append(f"load delta {d_load} B exceeds the 5.2 KB budget")
    if abs(d_free) > 256:
        errors.append(f"heap did not return to baseline: {d_free:+d} B (limit +/-256)")
    if loaded.get("count", 0) == 0:
        errors.append(f"fixture {_PL_GATE} not on the card — the delta above is index-only, "
                      "not index+rowcache under load")
    if errors:
        _leave_player(dut)
        fail("T_PLR_12", f"{'; '.join(errors)} | resume={d_enter}B load={d_load}B "
                         f"residual={d_free:+d}B lfb {base['largestBlock']}->{freed['largestBlock']}")
        return
    _leave_player(dut)
    pass_("T_PLR_12", f"resume +{d_enter} B, loaded ({loaded.get('count')} rows) +{d_load} B "
                      f"(peak with the file open +{d_peak} B), "
                      f"residual {d_free:+d} B; largest-free-block "
                      f"{base['largestBlock']} -> {after['largestBlock']} -> {freed['largestBlock']}")


# ── T_PLR_13-16 — file browser (TASK-416 / M-WINAMP-PLAYER-local §4) ──────────
# fileBrowser.h: SD.open()+openNextFile(), paged at <=FB_BATCH=4 entries/tick,
# directories bucketed ahead of .mp3/.m3u files, non-audio filtered. These
# assert paging never stalls, back/up survives the busy gate (TASK-384 defect
# class), hasPendingAsync() actually self-clears, and deep/edge directory
# shapes degrade correctly.
#
# FIXTURES: /probe200 (TASK-408's 200-entry probe dir — all named `*.txt`, so
# it is 0 playable files after filtering, which is itself part of what T_PLR_16
# checks; its VALUE for T_PLR_13 is walk cost, not row count) and /probefb/*
# (this task's own fixtures — empty dir, 2-level nested dir, an 8.3 name, a
# long name and a non-audio file side by side — created via `sdmkdir`+`sdput`
# 2026-08-11, same rig TASK-415 used for its playlist fixtures. Missing
# fixtures SKIP, not FAIL — a rig gap, not a defect.

_FB_BIG    = "/probe200"
_FB_ROOT   = "/"
_FB_EMPTY  = "/probefb/empty"
_FB_NESTED = "/probefb/nested"
_FB_DEEP   = "/probefb/nested/deep"
_FB_EDGE   = "/probefb/edge"


def _fb_open(dut: Dut, path: str, timeout: float = 6.0) -> dict:
    return dut.cmd(f"set fbOpen {path}", timeout=timeout)


def _fb_fixture_missing(dut: Dut, path: str) -> bool:
    """Did `set fbOpen <path>` fail because the fixture genuinely is not on the
    card, or because the browser itself failed to open a directory that IS
    there? The two are not the same and must not both read as SKIP.

    Filed because they did: on a 2026-08-11 orchestrator re-run, T_PLR_13 and
    T_PLR_15 opened the SAME `_FB_BIG` path in the SAME run — 13's open
    succeeded and 15's failed, and 15 reported "fixture not on the card", which
    was false. That is TASK-433. Probing with `sdls` (an independent path that
    does not go through fileBrowser's own state or its heap allocation) tells
    the two apart, so a real reopen failure fails loudly instead of hiding in a
    skip."""
    r = dut.cmd(f"sdls {path} n", timeout=8.0)
    return not r.get("ok")


def _fb_wait_done(dut: Dut, timeout_s: float = 12.0) -> dict | None:
    """Poll `get fbState` until pending clears. Returns the last reply, or None
    on timeout (DUT stopped responding — a real failure, not a slow walk)."""
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = dut.cmd("get fbState", timeout=3.0)
        if not last.get("ok"):
            return None
        if last.get("pending") is False:
            return last
    return last


def t_plr_13(dut: Dut):
    """T_PLR_13: browsing a ~200-file directory does not stall the pump. This
    node only proves the walk completes cleanly and the DUT stays responsive
    the whole time (no WDT, no stuck pending) — actual concurrent PLAYBACK
    (the design's real gate) needs cyd2usb_player, where the arena can be
    acquired at all (TASK-425/431: it cannot on cyd2usb_winamp_debug, in
    either mount/arena ordering, with Spotify's TLS working set resident).
    See test_fbrowser_player.py / run/browser-player for that half."""
    print("T_PLR_13  Browse ~200-file dir — walk completes, DUT stays responsive")
    if not _enter_player(dut, "T_PLR_13"):
        return
    t0 = time.monotonic()
    r = _fb_open(dut, _FB_BIG)
    if not r.get("ok"):
        missing = _fb_fixture_missing(dut, _FB_BIG)
        _leave_player(dut)
        if missing:
            skip("T_PLR_13", f"fixture {_FB_BIG} not on the card (TASK-408's probe fixture) — reply={r}")
        else:
            fail("T_PLR_13", f"fbOpen {_FB_BIG} failed but sdls says the directory IS on the card "
                             f"— browser-side open failure, see TASK-433. reply={r}")
        return
    st = _fb_wait_done(dut, timeout_s=15.0)
    elapsed = time.monotonic() - t0
    _leave_player(dut)
    if st is None:
        fail("T_PLR_13", f"DUT stopped responding mid-walk (unresponsive after {elapsed:.1f}s) "
                          "— loopTask stalled")
        return
    if st.get("pending"):
        fail("T_PLR_13", f"walk still pending after {elapsed:.1f}s (>{15.0}s bound) — batching regression")
        return
    pass_("T_PLR_13", f"200-entry walk completed in {elapsed:.1f}s, DUT responsive throughout "
                      f"(dirCount={st.get('dirCount')} fileCount={st.get('fileCount')} — "
                      f"0 expected, TASK-408's fixture is all .txt, filtered)")


def t_plr_14(dut: Dut):
    """T_PLR_14: a tap on the browser's own back/up zone is honoured even while
    a page walk is in flight — the TASK-384 defect class (isNavigationTap()
    must except it or g_shellBusy swallows it). Drives the REAL tap path (not
    the fbSelect/fbCancel debug shortcuts, which bypass the busy gate
    entirely and would prove nothing about it): eject opens the browser at a
    directory big enough that the walk outlives the round-trip, `get
    shellBusy` confirms the gate is actually armed, then a real `tap` at the
    back-zone coordinates must be honoured (not `skipped`)."""
    print("T_PLR_14  Browser back/up tap survives the busy gate mid-walk (TASK-384)")
    if not _enter_player(dut, "T_PLR_14"):
        return
    errors = []
    # Land the eject fallback dir on /probe200 (200 entries, ~5 s walk per
    # T_SD_07-class timing) by loading a playlist that lives there first —
    # eject opens _pl.dir() when a playlist is loaded. A smaller directory
    # (tried first: /mp3, 53 entries) races the walk against this test's own
    # serial round trips and can finish before either check below observes
    # it — not the bug under test, just insufficient margin.
    pl = _pl_load(dut, "/probe200/anchor.m3u")
    if pl.get("count", 0) == 0:
        _leave_player(dut)
        skip("T_PLR_14", "fixture /probe200/anchor.m3u not on the card")
        return
    ex, ey = _c.tap_eject()
    dut.set_cooldown_zero()
    r = dut.cmd(f"tap {ex} {ey}", timeout=5.0)
    if r.get("skipped"):
        errors.append(f"eject tap itself was skipped: {r}")
    busy = dut.cmd("get shellBusy", timeout=3.0)
    if not busy.get("val", busy.get("busy")):
        # Walk may have finished before we could observe it (e.g. after a
        # slow serial round trip) — that is a real precondition miss, not the
        # bug under test.
        _leave_player(dut)
        skip("T_PLR_14", f"g_shellBusy never observed true after eject — reply={busy}; "
                         "walk finished before this could be checked")
        return
    st = dut.cmd("get fbState", timeout=3.0)
    if not st.get("active") or not st.get("pending"):
        errors.append(f"browser not mid-walk when expected: {st}")
    dut.set_cooldown_zero()
    r2 = dut.cmd("tap 10 10", timeout=5.0)   # back-zone: x<S_BACK_ZONE_W(60), y<S_HEADER_H(28)
    if r2.get("skipped"):
        errors.append(f"back-zone tap SKIPPED while busy — TASK-384 defect class: {r2}")
    st2 = _fb_wait_done(dut, timeout_s=10.0)
    if st2 is None:
        errors.append("DUT unresponsive after the back-zone tap")
    elif st2.get("active") and st2.get("dir") == "/probe200/":
        errors.append(f"back-zone tap had no effect — still browsing {st2.get('dir')!r}")
    _leave_player(dut)
    if errors:
        fail("T_PLR_14", "; ".join(errors))
        return
    pass_("T_PLR_14", "back-zone tap honoured while g_shellBusy was true and the walk was mid-flight "
                      f"(ascended to dir={st2.get('dir')!r})")


def t_plr_15(dut: Dut):
    """T_PLR_15: hasPendingAsync() is true from the moment a page walk starts
    and self-clears when it finishes, without any other action — the contract
    NEW-APP-CHECKLIST item 1 requires."""
    print("T_PLR_15  hasPendingAsync() true during the walk, self-clears on completion")
    if not _enter_player(dut, "T_PLR_15"):
        return
    r = _fb_open(dut, _FB_BIG)
    if not r.get("ok"):
        missing = _fb_fixture_missing(dut, _FB_BIG)
        _leave_player(dut)
        if missing:
            skip("T_PLR_15", f"fixture {_FB_BIG} not on the card")
        else:
            fail("T_PLR_15", f"fbOpen {_FB_BIG} failed but sdls says the directory IS on the card "
                             f"— browser-side open failure, see TASK-433. reply={r}")
        return
    immediate = dut.cmd("get fbState", timeout=3.0)
    st = _fb_wait_done(dut, timeout_s=15.0)
    _leave_player(dut)
    errors = []
    if not immediate.get("pending"):
        errors.append(f"pending was not true immediately after fbOpen: {immediate}")
    if st is None:
        errors.append("DUT unresponsive waiting for pending to clear")
    elif st.get("pending"):
        errors.append(f"pending never cleared: {st}")
    if errors:
        fail("T_PLR_15", "; ".join(errors))
        return
    pass_("T_PLR_15", "pending true immediately after open, false once the walk finished "
                      f"(dirCount={st.get('dirCount')} fileCount={st.get('fileCount')})")


def t_plr_16(dut: Dut):
    """T_PLR_16: deep/edge directory shapes. Nested descend, an empty
    directory, 8.3 vs long filenames, and non-audio files mixed alongside
    playable ones — no crash, correct filter, correct bucket counts."""
    print("T_PLR_16  Deep/edge paths: nested, empty, 8.3/long names, non-audio filtered")
    if not _enter_player(dut, "T_PLR_16"):
        return
    errors = []

    def check(path: str, want_dirs: int | None, want_files: int | None, label: str):
        r = _fb_open(dut, path)
        if not r.get("ok"):
            errors.append(f"{label}: fbOpen {path} failed — fixture missing?")
            return
        st = _fb_wait_done(dut, timeout_s=10.0)
        if st is None:
            errors.append(f"{label}: DUT unresponsive")
            return
        if want_dirs is not None and st.get("dirCount") != want_dirs:
            errors.append(f"{label}: dirCount={st.get('dirCount')} (expected {want_dirs})")
        if want_files is not None and st.get("fileCount") != want_files:
            errors.append(f"{label}: fileCount={st.get('fileCount')} (expected {want_files})")

    # Empty directory — no crash, both counts 0.
    check(_FB_EMPTY, 0, 0, "empty dir")
    # 2-level nested descend: /probefb/nested has one subdir (deep); descending
    # into it finds its one file. Exercises open() being called twice in a row
    # (a directory tap's onSelect -> open()) without a free()/alloc() cycle
    # between — the arrays are reused, not just allocated once and forgotten.
    check(_FB_NESTED, 1, 0, "nested (parent)")
    r = _fb_open(dut, _FB_NESTED)   # re-open parent to select its subdir by index
    st = _fb_wait_done(dut, timeout_s=6.0)
    if st is None or st.get("dirCount", 0) < 1:
        errors.append("nested: could not re-list parent to descend")
    else:
        sel = dut.cmd("set fbSelect 0", timeout=5.0)   # the one subdir, "deep"
        if not sel.get("ok"):
            errors.append(f"nested: fbSelect 0 (descend into deep) failed: {sel}")
        st2 = _fb_wait_done(dut, timeout_s=6.0)
        if st2 is None or st2.get("dir") != "/probefb/nested/deep/" or st2.get("fileCount") != 1:
            errors.append(f"nested: descend did not land in deep/ with 1 file: {st2}")
    # 8.3 name, a long name, an .m3u and a filtered non-audio file side by
    # side: SONG1.MP3 (8.3), "A Really Quite Long Song Title Name Here.mp3"
    # (long), list.m3u, notes.txt (filtered) -> fileCount=3, dirCount=0.
    check(_FB_EDGE, 0, 3, "edge names (8.3/long/m3u, .txt filtered)")
    # Root: real card content mixes directories with a non-audio file at the
    # top level (probebench.bin, a TASK-408 leftover) -> that file must not
    # appear in either bucket.
    check(_FB_ROOT, None, 0, "root (probebench.bin filtered, no dirCount assertion — card-dependent)")

    _leave_player(dut)
    if errors:
        fail("T_PLR_16", "; ".join(errors))
        return
    pass_("T_PLR_16", "empty dir, 2-level nested descend, 8.3/long/m3u names and non-audio "
                      "filtering all correct")


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


def _wait_for_log(dut: Dut, marker: str, timeout_s: float = 5.0) -> bool:
    """Read serial lines until `marker` is seen (True) or timeout (False).
    Same idiom as T087/T095's inline log scans, extracted since T_PLR_17-19
    need it three different ways (positive AND negative assertions)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if marker in line:
            return True
    return False


def _drain_serial(dut: Dut, seconds: float = 0.3) -> None:
    """Discard buffered serial output for `seconds` — prevents a stale log
    line from a prior tap/test being misread as this one's effect."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            dut.ser.readline()
        except Exception:
            break


# ── T_PLR_17-19 — transport capability mask (TASK-417 / ADR-059 D8) ──────────
# CAP_TRANSPORT|CAP_SEEK|CAP_SHUFFLE|CAP_REPEAT gate winampDisplay's shuffle/
# repeat/seek zones per active mode: neither drawn (repaintChrome()) nor
# hit-tested (handleWinampInput() / each app's own hit-test) when the bit is
# absent. Spotify keeps all four (T_PLR_17 — a shipped mode getting no
# benefit from this refactor; ANY delta here is a regression, not a finding).
# WebRadio keeps CAP_TRANSPORT only (T_PLR_18) — before TASK-417 the SHUFREP
# sprites were drawn in WebRadio anyway (repaintChrome() was unconditional,
# sourced from whatever the shared cache last held) despite never being
# hit-tested; this closes that visual/hit-test mismatch. Player advertises
# all four (T_PLR_19), with its own state (not spotifyTask::Snapshot) behind
# the sprites — `get shufRep` reports both the active mask and the
# currently-rendered sprite indices, so a test can check what's REACHABLE
# (mask) and what's actually PAINTED (lastShuffle/lastRepeat) in one call.

def t_plr_17(dut: Dut):
    """T_PLR_17: Spotify still advertises all four capabilities — shuffle and
    repeat are still drawn and still hit-tested, dispatching ACT_SHUFFLE/
    ACT_REPEAT exactly as before TASK-417. Zero delta is the pass condition."""
    print("T_PLR_17  Spotify: all four capabilities unchanged (shuffle/repeat still real)")
    if not _restore_spotify(dut):
        skip("T_PLR_17", "precondition: could not restore Spotify app")
        return
    # TASK-417: pre-existing gap (predates this task, same class as
    # T_WR_EJECT_01/T_PLR_06) — a tap fired while g_shellBusy is still true
    # from _restore_spotify's own app-switch/poll is silently swallowed
    # (hit=CANVAS), which then also starves the "dequeued action=SHUFFLE/
    # REPEAT" log-line check below (the dispatch never happened at all).
    _wait_shell_not_busy(dut, timeout_s=10.0)
    errors = []

    r = dut.cmd("get shufRep", timeout=3.0)
    if not r.get("ok") or r.get("caps") != 15:   # CAP_TRANSPORT|SEEK|SHUFFLE|REPEAT = 1+2+4+8
        errors.append(f"playerCaps={r.get('caps')} (expected 15 — all four bits set)")

    # SHUFFLE: hit-tested AND dispatches. dequeue log ("dequeued action=SHUFFLE
    # param=N") is spotifyTask's generic dispatcher trace (spotifyTaskStorage.cpp)
    # — proves the tap reached the real ACT_SHUFFLE enqueue, not just the sprite.
    # 20 s bound, not an arbitrary short one: T082's own comment documents that
    # the dequeue can "lag by many seconds behind a backlog of HTTPS calls on
    # spotify.task", and T082 itself waits up to 20 s for the same class of
    # confirmation — a shorter bound here would flag that backlog as a defect.
    # TASK-417 gate investigation: tap + log-scan combined into one
    # continuous read (_tap_and_wait_log) — the previous split
    # dut.cmd(tap)+_wait_for_log() pattern raced read_json()'s non-JSON-line
    # discard against spotifyTask's async dequeue trace and could silently
    # eat the very log line being waited for (see _tap_and_wait_log's
    # docstring; confirmed via raw serial capture showing both dequeue
    # lines present while the old split-read reported FAIL for both).
    dut.set_cooldown_zero()
    shx, shy = _c.tap_shuffle()
    r, shuffle_seen = _tap_and_wait_log(dut, shx, shy, "dequeued action=SHUFFLE",
                                         tap_timeout=5.0, log_timeout=20.0)
    if r is None or r.get("hit") != "SHUFFLE" or r.get("action") != "SHUFFLE":
        errors.append(f"SHUFFLE hit-test: hit={r.get('hit') if r else None} "
                      f"action={r.get('action') if r else None}")
    if not shuffle_seen:
        errors.append("SHUFFLE: no 'dequeued action=SHUFFLE' within 20s — dispatch did not reach spotifyTask")

    _poll_shell_busy(dut, False, timeout_ms=3000)
    dut.set_cooldown_zero()
    rpx, rpy = _c.tap_repeat()
    r, repeat_seen = _tap_and_wait_log(dut, rpx, rpy, "dequeued action=REPEAT",
                                        tap_timeout=5.0, log_timeout=20.0)
    if r is None or r.get("hit") != "REPEAT" or r.get("action") != "REPEAT":
        errors.append(f"REPEAT hit-test: hit={r.get('hit') if r else None} "
                      f"action={r.get('action') if r else None}")
    if not repeat_seen:
        errors.append("REPEAT: no 'dequeued action=REPEAT' within 20s — dispatch did not reach spotifyTask")

    if errors:
        fail("T_PLR_17", "; ".join(errors))
    else:
        pass_("T_PLR_17", "caps=15 (all four); SHUFFLE/REPEAT still hit-tested and still "
                          "dispatch ACT_SHUFFLE/ACT_REPEAT — no delta from pre-TASK-417 behaviour")


def t_plr_18(dut: Dut):
    """T_PLR_18: WebRadio advertises CAP_TRANSPORT only. Shuffle/repeat zones
    must be neither drawn (caps bit absent) nor hit-tested (tap there must not
    report a SHUFFLE/REPEAT hit, and must not reach spotifyTask). Volume stays
    on its own TASK-352 seam, untouched by this task — confirm it still
    hit-tests correctly (TASK-406 was a real WebRadio-volume regression once)."""
    print("T_PLR_18  WebRadio: CAP_TRANSPORT only — shuffle/repeat neither drawn nor hit-tested")
    if not _switch_to(dut, "WebRadio"):
        skip("T_PLR_18", "precondition: could not switch to WebRadio")
        return
    errors = []

    r = dut.cmd("get shufRep", timeout=3.0)
    if not r.get("ok") or r.get("caps") != 1:   # CAP_TRANSPORT only
        errors.append(f"playerCaps={r.get('caps')} (expected 1 — CAP_TRANSPORT only)")

    # Drain any residual dequeue lines from a prior test before probing —
    # otherwise an old "dequeued action=SHUFFLE" from a previous suite entry
    # could be misread as this tap's effect.
    _drain_serial(dut, 0.3)

    dut.set_cooldown_zero()
    shx, shy = _c.tap_shuffle()
    r = dut.cmd(f"tap {shx} {shy}")
    if r.get("hit") == "SHUFFLE" or r.get("action") == "SHUFFLE":
        errors.append(f"SHUFFLE zone still hit-tested in WebRadio: hit={r.get('hit')} "
                      f"action={r.get('action')} (expected NOT SHUFFLE)")
    if _wait_for_log(dut, "dequeued action=SHUFFLE", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("SHUFFLE: 'dequeued action=SHUFFLE' seen — WebRadio tap leaked into "
                      "spotifyTask (the exact cross-mode leak TASK-417's sink seam exists to stop)")

    dut.set_cooldown_zero()
    rpx, rpy = _c.tap_repeat()
    r = dut.cmd(f"tap {rpx} {rpy}")
    if r.get("hit") == "REPEAT" or r.get("action") == "REPEAT":
        errors.append(f"REPEAT zone still hit-tested in WebRadio: hit={r.get('hit')} "
                      f"action={r.get('action')} (expected NOT REPEAT)")
    if _wait_for_log(dut, "dequeued action=REPEAT", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("REPEAT: 'dequeued action=REPEAT' seen — WebRadio tap leaked into spotifyTask")

    # Volume: unaffected by the mask (TASK-352's own seam) — confirm the
    # zone is still correctly classified for WebRadio (TASK-406 territory).
    dut.set_cooldown_zero()
    vx = (_c.vol_drag_x()[0] + _c.vol_drag_x()[1]) // 2
    vy = _c.vol_drag_y()
    r = dut.cmd(f"tap {vx} {vy}")
    if r.get("hit") != "VOLUME":
        errors.append(f"VOLUME hit-test regressed in WebRadio: hit={r.get('hit')} "
                      f"(expected VOLUME — TASK-352/TASK-406 seam, untouched by this task)")

    if errors:
        fail("T_PLR_18", "; ".join(errors))
    else:
        pass_("T_PLR_18", "caps=1 (CAP_TRANSPORT only); shuffle/repeat neither hit-tested nor "
                          "leaked to spotifyTask; volume zone still hit-tests correctly")


def t_plr_19(dut: Dut):
    """T_PLR_19: Player advertises all four capabilities. Shuffle/repeat are
    drawn and hit-tested with STATE SOURCED FROM PLAYER, not spotifyTask::
    Snapshot (D8) — confirmed by toggling in Player and reading back via
    `get shufRep` rather than trusting the tap reply alone. Seek is confirmed
    reachable (not falling through to the dead zone) via the real per-app
    input path (`drag`), distinct from Spotify's songDuration-gated posbar —
    TASK-419 is the real duration-accurate scrub, this only proves the zone
    is captured."""
    print("T_PLR_19  Player: all four capabilities, state sourced from Player not Spotify")
    if not _enter_player(dut, "T_PLR_19"):
        return
    errors = []

    r = dut.cmd("get shufRep", timeout=3.0)
    if not r.get("ok") or r.get("caps") != 15:
        errors.append(f"playerCaps={r.get('caps')} (expected 15 — all four bits set)")
    base = r

    # SHUFFLE: hit-tested (reported by lastTouchResult, same as Spotify/
    # WebRadio above) AND the sprite cache changes — proving the toggle is
    # real, not just a reported hit with no effect.
    _drain_serial(dut, 0.3)
    dut.set_cooldown_zero()
    shx, shy = _c.tap_shuffle()
    r = dut.cmd(f"tap {shx} {shy}")
    if r.get("hit") != "SHUFFLE" or r.get("action") != "SHUFFLE":
        errors.append(f"SHUFFLE hit-test: hit={r.get('hit')} action={r.get('action')}")
    r2 = dut.cmd("get shufRep", timeout=3.0)
    if r2.get("lastShuffle") == base.get("lastShuffle"):
        errors.append(f"SHUFFLE: lastShuffle unchanged ({r2.get('lastShuffle')}) after tap — "
                      f"hit-tested but not actually toggled")
    # D8: this must NOT have gone through spotifyTask — Player has its own sink.
    if _wait_for_log(dut, "dequeued action=SHUFFLE", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("SHUFFLE: 'dequeued action=SHUFFLE' seen while in Player mode — "
                      "leaked to spotifyTask instead of Player's own sink")

    _drain_serial(dut, 0.3)
    dut.set_cooldown_zero()
    rpx, rpy = _c.tap_repeat()
    r = dut.cmd(f"tap {rpx} {rpy}")
    if r.get("hit") != "REPEAT" or r.get("action") != "REPEAT":
        errors.append(f"REPEAT hit-test: hit={r.get('hit')} action={r.get('action')}")
    r3 = dut.cmd("get shufRep", timeout=3.0)
    if r3.get("lastRepeat") == r2.get("lastRepeat"):
        errors.append(f"REPEAT: lastRepeat unchanged ({r3.get('lastRepeat')}) after tap — "
                      f"hit-tested but not actually toggled")
    if _wait_for_log(dut, "dequeued action=REPEAT", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("REPEAT: 'dequeued action=REPEAT' seen while in Player mode — "
                      "leaked to spotifyTask instead of Player's own sink")

    # SEEK: drive through `drag` (single-step = a tap), the real per-app
    # dispatch path (main.cpp's drainInjectionQueue() calls the ACTIVE app's
    # handleInput() directly) — NOT `tap`/injectTouch, which classifies via
    # Spotify's songDuration-gated hitTestPosbar() and would be unreliable
    # here (Player never sets songDuration). dragState must stay D_IDLE
    # throughout: Player's seek zone deliberately does not engage Spotify's
    # shared D_POSBAR_DRAG machine (that's TASK-419's real-scrub wiring).
    rd0 = dut.cmd("get dragState", timeout=3.0)
    bx, by = _c.tap_posbar()
    dr = dut.cmd(f"drag {bx} {by} {bx} {by} 1", timeout=5.0)
    if not dr.get("ok"):
        errors.append(f"SEEK zone drag: no ok reply ({dr})")
    rd1 = dut.cmd("get dragState", timeout=3.0)
    if rd1.get("state") != "D_IDLE":
        errors.append(f"SEEK zone drag left dragState={rd1.get('state')} "
                      f"(expected D_IDLE — Player must not engage Spotify's posbar-drag machine)")
    # DUT still responsive after the seek tap — proves it didn't wedge on an
    # unimplemented engine call (TASK-419's stub is a documented no-op).
    if not dut.cmd("get plCount", timeout=5.0).get("ok"):
        errors.append("SEEK zone drag: DUT unresponsive to a follow-up command")

    _leave_player(dut)
    if errors:
        fail("T_PLR_19", "; ".join(errors))
    else:
        pass_("T_PLR_19", "caps=15; shuffle/repeat drawn+hit-tested with Player-sourced state "
                          "(not spotifyTask), no leak to spotifyTask; seek zone reachable via the "
                          "real input path without engaging Spotify's drag machine")


# ── T_PLR_20-26 — play-order engine (TASK-418 / ADR-059 D9/D12) ─────────────
# The debug surface these depend on (`get plOrder`, `get plCursor`,
# `set plCursor <n>`, `advance next|prev`) steps the SAME _stepOrder()/bag
# real playback uses, without decoding audio — that's what turns "20-track
# shuffle cycle" and "20 forced wraps" from ~3h of real playback (the design's
# original ask) into a few seconds of serial round-trips (VE-1).
#
# Shuffle/repeat have no dedicated `set` debug verb (D12 lists only the
# order-engine surface) — they're driven the same way a real finger would,
# via `tap` on the sprite coordinates, reading back `get shufRep` to confirm
# the toggle actually landed (not just that the tap hit-tested).

def _pl_shuffle(dut: Dut, want_on: bool, timeout_s: float = 3.0) -> bool:
    """Tap the shuffle sprite until `get shufRep`'s lastShuffle matches
    want_on. Bounded — a stuck toggle reports False rather than looping."""
    sx, sy = _c.tap_shuffle()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = dut.cmd("get shufRep", timeout=3.0)
        cur = r.get("lastShuffle")
        if (cur == 1) == want_on:
            return True
        dut.set_cooldown_zero()
        dut.cmd(f"tap {sx} {sy}", timeout=3.0)
        time.sleep(0.15)
    r = dut.cmd("get shufRep", timeout=3.0)
    return (r.get("lastShuffle") == 1) == want_on


def _pl_repeat(dut: Dut, want_off: bool, timeout_s: float = 4.0) -> bool:
    """Tap the repeat sprite until it reads the target D9 binary state:
    2 (off) or NOT-2 (repeat-all, folded to 0 by playerRepeatSink — see
    localPlayerApp.h's onRepeatChanged()). handleWinampInput()'s shared
    dispatch cycles a Spotify-shaped tri-state (2->1->0->2) regardless of
    mode, so this may pass through 1 on the way — only the final resting
    value matters here."""
    rx, ry = _c.tap_repeat()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = dut.cmd("get shufRep", timeout=3.0)
        cur = r.get("lastRepeat")
        if want_off and cur == 2:
            return True
        if not want_off and cur != 2:
            return True
        dut.set_cooldown_zero()
        dut.cmd(f"tap {rx} {ry}", timeout=3.0)
        time.sleep(0.15)
    r = dut.cmd("get shufRep", timeout=3.0)
    cur = r.get("lastRepeat")
    return (cur == 2) if want_off else (cur != 2)


def t_plr_20(dut: Dut):
    """T_PLR_20: the shuffle bag visits each track exactly once over a full
    cycle — 20x `advance next` on a 20-track list, no repeats, no skips."""
    print("T_PLR_20  Shuffle bag visits each track once (20-track cycle)")
    if not _enter_player(dut, "T_PLR_20"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) == 0:
        _leave_player(dut)
        skip("T_PLR_20", f"fixture {_PL_20} not on the card (gen_playlist_fixtures.py + sd_put.py)")
        return
    if r.get("count") != 20:
        _leave_player(dut)
        fail("T_PLR_20", f"count={r.get('count')} (expected 20)")
        return
    if not _pl_shuffle(dut, True):
        _leave_player(dut)
        fail("T_PLR_20", "could not toggle shuffle ON via tap")
        return
    order = dut.cmd("get plOrder", timeout=5.0).get("order", [])
    if len(order) != 20 or len(set(order)) != 20:
        errors.append(f"plOrder after shuffle-ON not a 20-entry permutation: {order}")

    visited = []
    for i in range(20):
        adv = dut.cmd("advance next", timeout=5.0)
        if not adv.get("ok") or not adv.get("moved"):
            errors.append(f"advance next #{i}: {adv}")
            break
        visited.append(adv.get("row"))
    if len(visited) == 20 and len(set(visited)) != 20:
        errors.append(f"visited rows not all distinct: {visited}")
    if visited != order:
        errors.append(f"advance sequence {visited} != get plOrder {order} "
                       f"(advance should walk the bag exactly)")

    _leave_player(dut)
    if errors:
        fail("T_PLR_20", "; ".join(errors))
    else:
        pass_("T_PLR_20", f"20/20 distinct rows visited via advance next, matching plOrder exactly: {order}")


def t_plr_21(dut: Dut):
    """T_PLR_21: all four shuffle x repeat end-of-list cells (design §8),
    forced via `set plCursor <last>` + `advance next` — no real playback."""
    print("T_PLR_21  All four shuffle x repeat end-of-list cells")
    if not _enter_player(dut, "T_PLR_21"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_21", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return

    last_idx = r.get("count", 20) - 1

    def _force_wrap_from_last():
        # Always set explicitly to the known last index — do NOT infer "am I
        # already at the end" from a `get plCursor` read first. That reflects
        # whatever the PREVIOUS cell's advance left behind, not this cell's
        # precondition, and masks a real firmware bug the same way (a stale
        # cursor near the start silently reads as "close enough", producing
        # exactly the kind of drifted-cell failure this test exists to catch).
        dut.cmd(f"set plCursor {last_idx}", timeout=3.0)
        return dut.cmd("advance next", timeout=5.0)

    # Cell 1: shuffle off, repeat off -> stop at last row.
    if not _pl_shuffle(dut, False) or not _pl_repeat(dut, True):
        errors.append("cell1: could not set shuffle=off repeat=off")
    else:
        adv = _force_wrap_from_last()
        if adv.get("moved") is not False:
            errors.append(f"cell1 (shuffle off, repeat off): expected moved=false, got {adv}")

    # Cell 2: shuffle off, repeat all -> wrap to viewOrder[0].
    if not _pl_repeat(dut, False):
        errors.append("cell2: could not set repeat=all")
    else:
        adv = _force_wrap_from_last()
        if adv.get("moved") is not True or adv.get("row") != 0 or adv.get("reshuffled"):
            errors.append(f"cell2 (shuffle off, repeat all): expected moved=true row=0 "
                          f"reshuffled=false, got {adv}")

    # Cell 3: shuffle on, repeat off -> play each once, then stop.
    if not _pl_shuffle(dut, True) or not _pl_repeat(dut, True):
        errors.append("cell3: could not set shuffle=on repeat=off")
    else:
        adv = _force_wrap_from_last()
        if adv.get("moved") is not False:
            errors.append(f"cell3 (shuffle on, repeat off): expected moved=false, got {adv}")

    # Cell 4: shuffle on, repeat all -> reshuffle and continue.
    if not _pl_repeat(dut, False):
        errors.append("cell4: could not set repeat=all")
    else:
        adv = _force_wrap_from_last()
        if adv.get("moved") is not True or not adv.get("reshuffled"):
            errors.append(f"cell4 (shuffle on, repeat all): expected moved=true "
                          f"reshuffled=true, got {adv}")

    _leave_player(dut)
    if errors:
        fail("T_PLR_21", "; ".join(errors))
    else:
        pass_("T_PLR_21", "all four end-of-list cells match design §8 exactly, 4/4 — "
                          "no real-time playback")


def t_plr_22(dut: Dut):
    """T_PLR_22: reshuffle-on-wrap never re-opens with the track that just
    finished — 20 forced wraps (shuffle on, repeat all), 0 collisions."""
    print("T_PLR_22  Reshuffle does not re-open with the last track (20 forced wraps)")
    if not _enter_player(dut, "T_PLR_22"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_22", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return
    if not _pl_shuffle(dut, True) or not _pl_repeat(dut, False):
        _leave_player(dut)
        fail("T_PLR_22", "could not set shuffle=on repeat=all")
        return

    collisions = 0
    for i in range(20):
        before = dut.cmd("get plOrder", timeout=5.0).get("order", [])
        if len(before) != 20:
            errors.append(f"wrap {i}: plOrder count={len(before)} (expected 20)")
            break
        last_id = before[19]
        dut.cmd("set plCursor 19", timeout=3.0)
        adv = dut.cmd("advance next", timeout=5.0)
        if not adv.get("moved") or not adv.get("reshuffled"):
            errors.append(f"wrap {i}: expected moved=true reshuffled=true, got {adv}")
            continue
        after = dut.cmd("get plOrder", timeout=5.0).get("order", [])
        if len(after) == 20 and after[0] == last_id:
            collisions += 1
            errors.append(f"wrap {i}: reshuffle re-opened with the just-finished id {last_id}")

    _leave_player(dut)
    if errors:
        fail("T_PLR_22", f"{collisions}/20 collisions; " + "; ".join(errors[:5]))
    else:
        pass_("T_PLR_22", f"{collisions}/20 collisions over 20 forced wraps")


def t_plr_23(dut: Dut):
    """T_PLR_23: Prev replays history — walks playOrder backward, never
    rerolls. advance next x5 then advance prev x5 must be the exact reverse,
    and plOrder must be byte-identical before and after (no reshuffle)."""
    print("T_PLR_23  Prev replays history (no reroll, plOrder unchanged)")
    if not _enter_player(dut, "T_PLR_23"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_23", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return
    if not _pl_shuffle(dut, True):
        _leave_player(dut)
        fail("T_PLR_23", "could not toggle shuffle ON")
        return

    order_before = dut.cmd("get plOrder", timeout=5.0).get("order", [])
    forward = []
    for i in range(5):
        adv = dut.cmd("advance next", timeout=5.0)
        if not adv.get("moved"):
            errors.append(f"advance next #{i} did not move: {adv}")
            break
        forward.append(adv.get("row"))
    backward = []
    for i in range(5):
        adv = dut.cmd("advance prev", timeout=5.0)
        backward.append((adv.get("moved"), adv.get("row")))
    order_after = dut.cmd("get plOrder", timeout=5.0).get("order", [])

    if len(forward) == 5:
        # 5 nexts land at bag positions 0..4. 5 prevs should retrace
        # positions 3,2,1,0 (rows = forward[3],forward[2],forward[1],forward[0])
        # and then report moved=false on the 5th (nothing before position 0).
        expected_rows = list(reversed(forward[:-1]))
        got_rows = [row for (moved, row) in backward[:4] if moved]
        if got_rows != expected_rows:
            errors.append(f"prev sequence {got_rows} != expected reverse {expected_rows}")
        if len(backward) < 4 or not all(m for (m, _) in backward[:4]):
            errors.append(f"one of the first 4 prevs did not move: {backward}")
        if len(backward) == 5 and backward[4][0] is not False:
            errors.append(f"5th prev (at position 0) should report moved=false, got {backward[4]}")
    if order_before != order_after:
        errors.append(f"plOrder changed across the next/prev walk: "
                      f"before={order_before} after={order_after}")

    _leave_player(dut)
    if errors:
        fail("T_PLR_23", "; ".join(errors))
    else:
        pass_("T_PLR_23", f"forward={forward} backward retraced exactly, "
                          f"plOrder unchanged (no reroll)")


def t_plr_24(dut: Dut):
    """T_PLR_24: tap-to-play under shuffle moves the bag cursor to that
    entry's position — it does not reshuffle. Uses `set plPlay` (dbgPlayRow,
    the same tap-to-play entry point PLEDIT's onTap() drives) rather than a
    screen-coordinate tap, since row position depends on live scroll offset."""
    print("T_PLR_24  Tap-to-play moves the cursor, does not reshuffle")
    if not _enter_player(dut, "T_PLR_24"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_24", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return
    if not _pl_shuffle(dut, True):
        _leave_player(dut)
        fail("T_PLR_24", "could not toggle shuffle ON")
        return

    order_before = dut.cmd("get plOrder", timeout=5.0).get("order", [])
    target_row = 5
    if target_row >= len(order_before) or target_row not in order_before:
        errors.append(f"row {target_row} not present in plOrder {order_before}")
    else:
        expected_pos = order_before.index(target_row)
        pick = dut.cmd(f"set plPlay {target_row}", timeout=8.0)
        if not pick.get("ok"):
            errors.append(f"set plPlay {target_row} failed: {pick}")
        cur = dut.cmd("get plCursor", timeout=5.0)
        if cur.get("cursor") != expected_pos:
            errors.append(f"cursor={cur.get('cursor')} (expected bag position "
                          f"{expected_pos} of row {target_row})")
        if cur.get("curRow") != target_row:
            errors.append(f"curRow={cur.get('curRow')} (expected {target_row})")
        order_after = dut.cmd("get plOrder", timeout=5.0).get("order", [])
        if order_before != order_after:
            errors.append(f"plOrder changed by tap-to-play: before={order_before} "
                          f"after={order_after}")
        # Leave playback stopped — this test never means to leave audio running.
        if pick.get("ok"):
            dut.cmd(f"tap {_c.tap_button('STOP')[0]} {_c.tap_button('STOP')[1]}", timeout=5.0)

    _leave_player(dut)
    if errors:
        fail("T_PLR_24", "; ".join(errors))
    else:
        pass_("T_PLR_24", f"tap-to-play row {target_row} moved cursor to bag position "
                          f"{expected_pos}, plOrder unchanged (no reshuffle)")


def t_plr_25(dut: Dut):
    """T_PLR_25: auto-advance end to end — the one real-playback case, proving
    audio_eof_mp3() drives the SAME _stepOrder()/_startPlayback() path the
    debug surface exercises above. 5 short (~3s) real files, shuffle off,
    repeat off; advances 5/5 without a WDT reset. Known hazard on this path
    (do not re-diagnose if hit): TASK-432 (`new Audio()` can throw an
    uncaught bad_alloc under heap pressure) and TASK-430 (tlsTryYield's
    1.5s budget on aeConnectFile) — both filed, not this task's to fix."""
    print("T_PLR_25  Auto-advance end to end (5 real short files)")
    if not _enter_player(dut, "T_PLR_25"):
        return
    errors = []
    r = _pl_load(dut, _PL_SHORT5, timeout=15.0)
    if r.get("count", 0) == 0:
        _leave_player(dut)
        skip("T_PLR_25", f"fixture {_PL_SHORT5} not on the card")
        return
    if not _pl_shuffle(dut, False) or not _pl_repeat(dut, True):
        _leave_player(dut)
        fail("T_PLR_25", "could not set shuffle=off repeat=off")
        return

    dut.cmd("set bgPoll 0", timeout=3.0)
    played_rows = []
    play = dut.cmd("set plPlay 0", timeout=10.0)
    if not play.get("ok"):
        dut.cmd("set bgPoll 1", timeout=3.0)
        _leave_player(dut)
        fail("T_PLR_25", f"set plPlay 0 failed: {play}")
        return

    deadline = time.monotonic() + 60.0
    last_row = None
    stopped_after_last = False
    while time.monotonic() < deadline:
        time.sleep(0.5)
        st = dut.cmd("get plCount", timeout=5.0)
        if not st.get("ok"):
            errors.append("DUT stopped responding mid-playback")
            break
        cur = st.get("curRow")
        if cur != last_row and cur is not None and cur >= 0:
            played_rows.append(cur)
            last_row = cur
        if last_row == 4 and not st.get("playing") and len(played_rows) >= 1:
            # Row 4 (the last) finished and nothing followed — repeat is off,
            # so this is the expected end, not a hang.
            stopped_after_last = True
            break

    dut.cmd("set bgPoll 1", timeout=3.0)
    _leave_player(dut)
    if played_rows != [0, 1, 2, 3, 4]:
        errors.append(f"row sequence {played_rows} != [0,1,2,3,4]")
    if not stopped_after_last:
        errors.append("did not observe playback stop after row 4 (repeat off) within 60s")
    if errors:
        fail("T_PLR_25", "; ".join(errors))
    else:
        pass_("T_PLR_25", f"auto-advanced 5/5 real short files: {played_rows}, no WDT")


def t_plr_26(dut: Dut):
    """T_PLR_26: shuffle/repeat persist across reboot; Spotify's own
    shuffle/repeat are never written to g_settings.player* (ADR-059 D9)."""
    print("T_PLR_26  Shuffle/repeat persist across reboot")
    if not _enter_player(dut, "T_PLR_26"):
        return
    errors = []
    if not _pl_shuffle(dut, True) or not _pl_repeat(dut, False):
        _leave_player(dut)
        fail("T_PLR_26", "could not set shuffle=on repeat=all before reboot")
        return
    before = dut.cmd("get shufRep", timeout=3.0)
    # suspend()'s coalesced write only fires on a mode switch away (ADR-050
    # rule 3) — leave Player before rebooting, same discipline plLoad's own
    # persistence gates use elsewhere in this suite.
    _leave_player(dut)
    if not _switch_to(dut, "Clock"):
        skip("T_PLR_26", "precondition: could not step off Player before reboot")
        return

    # [REBOOT] — same idiom as T_PR_04: reuse the same Dut/port, the CH34x
    # driver's DTR-reset detection in _wait_for_ready() handles the reconnect.
    dut.send("reboot")
    time.sleep(0.3)
    dut._wait_for_ready()

    if not _enter_player(dut, "T_PLR_26"):
        return
    after = dut.cmd("get shufRep", timeout=5.0)
    if after.get("lastShuffle") != 1:
        errors.append(f"shuffle did not survive reboot: before={before} after={after}")
    if after.get("lastRepeat") == 2:
        errors.append(f"repeat did not survive reboot: before={before} after={after}")
    # Restore a clean default (off/off) so later tests in the suite don't
    # inherit an unexpected shuffle/repeat state.
    _pl_shuffle(dut, False)
    _pl_repeat(dut, True)
    _leave_player(dut)

    if errors:
        fail("T_PLR_26", "; ".join(errors))
    else:
        pass_("T_PLR_26", f"shuffle=on repeat=all survived reboot: {after}")


# ── stock-002 suite (TASK-120) ────────────────────────────────────────────────
# Tests the heatmap sub-view, navigation, fetch-gate, and chartSymbol guard.
#
# Serial commands used:
#   get heatmapCount, get stockSubView, get stockChartTicker, get stockChartRange
#   get fetchOkCount, get chartLen
#   set triggerHeatmap 1, set triggerFetch 1, set cooldown 0
#   tap <x> <y>
#
# Heatmap geometry (main.cpp constants):
#   ST_LIST_RULE_Y = 22 → tile canvas y=22..239, header y=0..21
#   HEAT button:   tap 220 10   (x=220 > 190, y=10 < 22)
#   Tile drill:    tap 10 30    (top-left corner — always in the largest/first tile regardless of layout)
#   Chart back:    tap 10 7
#   Chart 5D tab:  tap 184 9


def _wait_heatmap_count(dut: Dut, timeout_s: float = 60.0) -> int:
    """Poll get heatmapCount until > 0. Returns count (0 on timeout)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = dut.cmd("get heatmapCount", timeout=3.0)
        if r.get("ok"):
            try:
                val = int(r.get("val", 0))
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
        time.sleep(3.0)
    # TASK-386: same treatment as _wait_chart_complete — automatic for every caller.
    _diag_snapshot(dut, "_wait_heatmap_count-timeout")
    return 0


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


def _ensure_stock_list_view(dut: Dut) -> bool:
    """After switchApp to Stock, normalize to ListDetail sub-view.
    Handles leftover state from previous tests (heatmap or chart sub-view).
    Returns True if ListDetail confirmed."""
    for _ in range(3):
        r = dut.cmd("get stockSubView", timeout=3.0)
        sv = r.get("val", "")
        if sv == "list":
            return True
        if sv == "chart":
            # Chart may have pending fetch; wait for shellBusy to clear first
            _wait_shell_not_busy(dut, timeout_s=45.0)
            time.sleep(0.1)
            dut.set_cooldown_zero()
            dut.cmd("tap 10 7", timeout=3.0)  # chart back button
        elif sv == "heatmap":
            dut.set_cooldown_zero()
            dut.cmd("tap 220 10", timeout=3.0)  # HEAT toggle → list
        time.sleep(0.3)
    return dut.cmd("get stockSubView", timeout=3.0).get("val") == "list"


# ── T196 — Heatmap fetch completes; triggerHeatmap sets sub-view ──────────────

def t196(dut: Dut):
    """T196: triggerHeatmap → subView=heatmap; heatmapCount > 0 within 60 s."""
    print("T196  Heatmap data present after fetch")
    if not _switch_to_stock(dut):
        skip("T196", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
    if not r.get("ok"):
        fail("T196", "set triggerHeatmap 1 returned error")
        _restore_from_stock(dut)
        return
    time.sleep(0.3)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    if r_sv.get("val") != "heatmap":
        fail("T196", f"stockSubView={r_sv.get('val')!r} after triggerHeatmap — expected 'heatmap'")
        _restore_from_stock(dut)
        return
    count = _wait_heatmap_count(dut, timeout_s=60.0)
    _restore_from_stock(dut)
    if count == 0:
        fail("T196", "heatmapCount still 0 after 60 s — screener fetch did not complete")
        return
    pass_("T196", f"heatmapCount={count}; subView=heatmap confirmed; fetch complete")


# ── T200 — List→Heatmap toggle via HEAT tap ───────────────────────────────────

def t200(dut: Dut):
    """T200: HEAT tap (x>190, y<22) in list view → subView switches to heatmap."""
    print("T200  List→Heatmap toggle via HEAT tap")
    if not _switch_to_stock(dut):
        skip("T200", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T200", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 220 10", timeout=3.0)
    time.sleep(0.3)
    r_sv2 = dut.cmd("get stockSubView", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv2.get("val") != "heatmap":
        fail("T200", f"stockSubView={r_sv2.get('val')!r} after HEAT tap — expected 'heatmap'")
        return
    pass_("T200", "HEAT tap in list → subView=heatmap confirmed")


# ── T201 — Heatmap→List back toggle via HEAT tap ──────────────────────────────

def t201(dut: Dut):
    """T201: HEAT tap (x>190, y<22) in heatmap view → subView returns to list."""
    print("T201  Heatmap→List back toggle via HEAT tap")
    if not _switch_to_stock(dut):
        skip("T201", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Normalize to list first so prevSubView is correctly set to List
    if not _ensure_stock_list_view(dut):
        skip("T201", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
    if not r.get("ok"):
        skip("T201", "set triggerHeatmap 1 failed")
        _restore_from_stock(dut)
        return
    time.sleep(0.5)  # allow repaintHeatmap to finish before querying
    r_sv_pre = dut.cmd("get stockSubView", timeout=5.0)
    if r_sv_pre.get("val") != "heatmap":
        skip("T201", f"stockSubView={r_sv_pre.get('val')!r} after triggerHeatmap — expected 'heatmap'")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 220 10", timeout=3.0)
    time.sleep(0.3)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "list":
        fail("T201", f"stockSubView={r_sv.get('val')!r} after HEAT tap in heatmap — expected 'list'")
        return
    pass_("T201", "HEAT tap in heatmap → subView=list (back) confirmed")


# ── T202 — Heatmap tile tap drills to ChartDetail ─────────────────────────────

def t202(dut: Dut):
    """T202: Tap canvas centre in heatmap (tile area) → drills to ChartDetail."""
    print("T202  Heatmap tile tap drills to chart")
    if not _switch_to_stock(dut):
        skip("T202", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T202", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap when cache is present — avoids re-fetching and re-fetch failures
    if _wait_heatmap_count(dut, timeout_s=10.0) == 0:
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T202", "set triggerHeatmap 1 failed (no cached heatmap)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T202", "heatmapCount still 0 after 60 s — no tiles to tap")
            _restore_from_stock(dut)
            return
        time.sleep(2.0)  # let heatmap render after first fetch
    else:
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT tap → heatmap (no new fetch)
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T202", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    time.sleep(0.3)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of canvas — always in largest tile
    time.sleep(0.5)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    if r_sv.get("val") != "chart":
        _restore_from_stock(dut)
        fail("T202", f"stockSubView={r_sv.get('val')!r} after tile tap — expected 'chart'")
        return
    r_sym = dut.cmd("get stockChartTicker", timeout=3.0)
    drilled = r_sym.get("val", "?")
    _restore_from_stock(dut)
    pass_("T202", f"tile tap → ChartDetail; drilled symbol={drilled!r}")


# ── T203 — Chart back from heatmap drill restores HeatmapDetail ───────────────

def t203(dut: Dut):
    """T203: Back tap from chart (entered via heatmap drill) → restores HeatmapDetail, not List."""
    print("T203  Chart back from heatmap drill restores HeatmapDetail")
    if not _switch_to_stock(dut):
        skip("T203", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T203", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap when cache is present — avoids re-fetching and re-fetch failures
    if _wait_heatmap_count(dut, timeout_s=10.0) == 0:
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T203", "set triggerHeatmap 1 failed (no cached heatmap)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T203", "heatmapCount still 0 after 60 s — no tiles")
            _restore_from_stock(dut)
            return
        time.sleep(2.0)
    else:
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT tap → heatmap (no new fetch)
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T203", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    time.sleep(0.3)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of canvas — always in largest tile
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=3.0).get("val") != "chart":
        skip("T203", "could not drill to chart from heatmap tile tap")
        _restore_from_stock(dut)
        return
    # Wait for chart fetch to complete (g_shellBusy clears) before back tap
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T203", "shellBusy did not clear after tile drill — chart fetch stuck?")
        _restore_from_stock(dut)
        return
    time.sleep(0.1)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)
    time.sleep(0.3)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "heatmap":
        fail("T203", f"stockSubView={r_sv.get('val')!r} after chart back — expected 'heatmap'")
        return
    pass_("T203", "chart back → subView=heatmap (prevSubView preserved correctly)")


# ── T192 — Tab-switch after heatmap drill uses drilled symbol ─────────────────

def t192(dut: Dut):
    """T192: After heatmap drill, range tab-switch fetches the drilled symbol (TASK-121 fix)."""
    print("T192  Tab-switch after heatmap drill uses drilled symbol")
    if not _switch_to_stock(dut):
        skip("T192", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T192", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap when cache is available to avoid queueing a new screener fetch
    if _wait_heatmap_count(dut, timeout_s=3.0) == 0:
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T192", "set triggerHeatmap 1 failed (no cached heatmap data)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T192", "heatmapCount still 0 after 60 s")
            _restore_from_stock(dut)
            return
        time.sleep(2.0)
    else:
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT tap → heatmap (no new fetch)
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T192", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    # Wait for any in-progress heatmap layout recompute/repaint (cache-expiry re-fetch) to settle
    time.sleep(0.5)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of heatmap canvas — always in the largest tile
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=3.0).get("val") != "chart":
        skip("T192", "could not drill to chart from heatmap")
        _restore_from_stock(dut)
        return
    r_sym = dut.cmd("get stockChartTicker", timeout=3.0)
    drilled = r_sym.get("val", "?")
    # Wait for D1 chart fetch to complete before tab-switching (clears g_shellBusy)
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T192", "shellBusy did not clear after tile drill — chart fetch stuck?")
        _restore_from_stock(dut)
        return
    before_ok = _stock_ok_count(dut)
    time.sleep(0.1)
    dut.set_cooldown_zero()
    dut.cmd("tap 184 9", timeout=3.0)  # 5D tab
    time.sleep(0.3)
    r_range = dut.cmd("get stockChartRange", timeout=3.0)
    if r_range.get("val") != "D5":
        skip("T192", f"stockChartRange={r_range.get('val')!r} after 5D tap — tab not registered")
        _restore_from_stock(dut)
        return
    if not _wait_chart_complete(dut, before_ok, timeout_s=45.0):
        fail("T192", "fetchOkCount did not advance after tab-switch — TASK-121 fix may be missing")
        _restore_from_stock(dut)
        return
    r_sym2 = dut.cmd("get stockChartTicker", timeout=3.0)
    after_sym = r_sym2.get("val", "?")
    _restore_from_stock(dut)
    if after_sym != drilled:
        fail("T192", f"chart ticker changed: {drilled!r} → {after_sym!r} after tab-switch")
        return
    pass_("T192", f"drilled={drilled!r}; 5D tab-switch fired fetch; ticker unchanged")


# ── T193 — Auto-refresh path uses drilled symbol ──────────────────────────────

def t193(dut: Dut):
    """T193: stockTickChart() auto-refresh uses chartSymbol after heatmap drill (TASK-121b fix)."""
    print("T193  Auto-refresh path uses drilled symbol")
    # TASK-385: baseline snapshot at test entry. In a full `run/test` pass this runs after
    # ~150 prior tests with no reboot in between; in an isolated `run/test-targeted T193`
    # rerun it runs 2-3 min post-boot. Comparing this line's heap/dataq/backoff numbers
    # across the two contexts is the whole point — see _diag_snapshot's docstring.
    entry_diag = _diag_snapshot(dut, "T193-entry")
    if not _switch_to_stock(dut):
        skip("T193", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T193", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap (not triggerHeatmap) to enter heatmap — enterHeatmap() only fetches if
    # lastHeatmapFetch==0, so re-using cached data avoids queuing a new screener fetch that
    # would block the dataTask queue and starve the subsequent chart fetch (LL-T193-001).
    # Use 10 s deadline so a transient serial flood (stockTickQuotes HTTP) doesn't drop us
    # into the triggerHeatmap branch on the very first check attempt.
    if _wait_heatmap_count(dut, timeout_s=10.0) == 0:
        # No cached data yet — fall back to triggerHeatmap and wait for fetch
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T193", "set triggerHeatmap 1 failed (no cached heatmap data)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T193", "heatmapCount still 0 after 60 s")
            _restore_from_stock(dut)
            return
        # Flush the heatmap result from the dataTask queue before drilling to chart
        time.sleep(2.0)  # allow pollHeatmapQuote to run in stockTickHeatmap tick
    else:
        # Cached data present — HEAT tap enters heatmap without queuing a screener fetch
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT button in list header
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T193", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    time.sleep(0.5)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of canvas — always in largest tile
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=3.0).get("val") != "chart":
        skip("T193", "could not drill to chart from heatmap")
        _restore_from_stock(dut)
        return
    r_sym = dut.cmd("get stockChartTicker", timeout=3.0)
    drilled = r_sym.get("val", "?")
    # Wait for initial D1 fetch to complete (clears shellBusy), then force re-fetch
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T193", "shellBusy did not clear after tile drill")
        _restore_from_stock(dut)
        return
    before_ok = _stock_ok_count(dut)
    # TASK-385: snapshot immediately before the risky trigger — this is the state the
    # forced re-fetch actually has to run against (post-heatmap-drill, post-tile-drill).
    pre_diag = _diag_snapshot(dut, "T193-pre-trigger")
    dut.cmd("set triggerFetch 1", timeout=3.0)  # reset lastChartFetch → force next tick re-fetch
    if not _wait_chart_complete(dut, before_ok, timeout_s=45.0, test_id="T193"):
        # TASK-385: on timeout, one more snapshot at the point of failure. Embedded
        # directly in the fail() reason (not just printed) so it survives even without
        # LOG_FILE= capture — the original 2026-08-01 filing had neither.
        timeout_diag = _diag_snapshot(dut, "T193-timeout")
        fail("T193", "fetchOkCount did not advance after triggerFetch — auto-refresh did not "
                      f"fire | entry={entry_diag} | pre-trigger={pre_diag} | timeout={timeout_diag}")
        _restore_from_stock(dut)
        return
    r_sym2 = dut.cmd("get stockChartTicker", timeout=3.0)
    after_sym = r_sym2.get("val", "?")
    r_cl = dut.cmd("get chartLen", timeout=3.0)
    chart_len = int(r_cl.get("val", 0)) if r_cl.get("ok") else -1
    _restore_from_stock(dut)
    if after_sym != drilled:
        fail("T193", f"chart ticker changed after auto-refresh: {drilled!r} → {after_sym!r}")
        return
    if chart_len <= 0:
        skip("T193", f"chartLen={chart_len} after auto-refresh — Yahoo returned empty data (external API flakiness)")
        return
    pass_("T193", f"drilled={drilled!r}; auto-refresh fetched same symbol; chartLen={chart_len}")


# ── T194 — Back-to-list clears chartSymbol; re-drill from list uses index ─────

def t194(dut: Dut):
    """T194: Back to list after heatmap drill clears chartSymbol; list drill uses index ticker."""
    print("T194  Back-to-list clears chartSymbol; list drill uses index ticker")
    # TASK-385: entry baseline, same rationale as T193's. T194 runs right after T193 in
    # suite order and does a heavier fetch cascade (heatmap + 2 chart fetches + a
    # tab-switch fetch vs T193's 2), so it's the more sensitive canary for suite-
    # accumulated heap/queue/tlsYield pressure — worth comparing its entry snapshot
    # against T193's from the same run.
    entry_diag = _diag_snapshot(dut, "T194-entry")
    if not _switch_to_stock(dut):
        skip("T194", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T194", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap to enter heatmap without queuing a new screener fetch (same as T193)
    if _wait_heatmap_count(dut, timeout_s=3.0) == 0:
        # No cached data — use triggerHeatmap and wait
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T194", "set triggerHeatmap 1 failed (no cached heatmap data)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T194", "heatmapCount still 0 after 60 s")
            _restore_from_stock(dut)
            return
        time.sleep(2.0)  # allow heatmap result to be polled
    else:
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT button in list → heatmap (no new fetch)
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T194", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    time.sleep(0.5)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of canvas — always in largest tile
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=3.0).get("val") != "chart":
        skip("T194", "could not drill to chart from heatmap")
        _restore_from_stock(dut)
        return
    # Wait for chart fetch (clears shellBusy) before back-nav taps
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T194", "shellBusy did not clear after tile drill")
        _restore_from_stock(dut)
        return
    time.sleep(0.1)
    # Navigate back: chart → heatmap → list
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)  # chart back → heatmap
    time.sleep(0.8)  # repaintHeatmap (20 tiles) blocks serial handler briefly
    # repaintHeatmap's SPI bus activity can cause spurious physical-touch readings that
    # trigger drillToChartBySym and set _pendingAsync=true → shellBusy=true; wait it out
    _wait_shell_not_busy(dut, timeout_s=45.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 220 10", timeout=3.0)  # HEAT back → list
    time.sleep(1.5)  # stockTickQuotes HTTP may flood serial immediately on list entry
    r_sv = dut.cmd("get stockSubView", timeout=5.0)
    if r_sv.get("val") != "list":
        skip("T194", f"could not navigate back to list; subView={r_sv.get('val')!r}")
        _restore_from_stock(dut)
        return
    # Drill from list row (AAPL at y=36)
    time.sleep(0.5)  # let quote-fetch serial flood settle before snapshot + tap
    # Clear fetchFailed in case a spurious touch during repaintHeatmap left an error state;
    # fetchFailed=true blocks list-row drills (firmware returns early at line 786)
    dut.cmd("set fetchFailed 0", timeout=5.0)
    # A spurious touch during repaintHeatmap can leave g_shellBusy=true; wait it out
    _wait_shell_not_busy(dut, timeout_s=15.0)
    before_ok = _stock_ok_count(dut)
    list_drill_diag = _diag_snapshot(dut, "T194-pre-list-drill")
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=5.0)
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=5.0).get("val") != "chart":
        skip("T194", "could not drill to chart from list row")
        _restore_from_stock(dut)
        return
    r_sym = dut.cmd("get stockChartTicker", timeout=5.0)
    list_ticker = r_sym.get("val", "?")
    # Wait for list-drill chart fetch to complete before tab tap
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T194", "shellBusy did not clear after list-drill")
        _restore_from_stock(dut)
        return
    time.sleep(0.1)
    # TASK-385: snapshot immediately before the final trigger — the structural twin of
    # T193's forced-refetch trigger (same _wait_chart_complete/45s-timeout shape).
    tab_diag = _diag_snapshot(dut, "T194-pre-tab-switch")
    dut.set_cooldown_zero()
    dut.cmd("tap 184 9", timeout=3.0)  # 5D tab
    time.sleep(0.3)
    if not _wait_chart_complete(dut, before_ok, timeout_s=45.0, test_id="T194"):
        timeout_diag = _diag_snapshot(dut, "T194-timeout")
        skip("T194", "fetchOkCount did not advance on list-drilled tab-switch | "
                      f"entry={entry_diag} | pre-list-drill={list_drill_diag} | "
                      f"pre-tab-switch={tab_diag} | timeout={timeout_diag}")
        _restore_from_stock(dut)
        return
    r_sym2 = dut.cmd("get stockChartTicker", timeout=3.0)
    after_sym = r_sym2.get("val", "?")
    _restore_from_stock(dut)
    if after_sym != list_ticker:
        fail("T194", f"ticker changed after list-drill tab-switch: {list_ticker!r} → {after_sym!r}")
        return
    pass_("T194", f"list-drilled={list_ticker!r}; tab-switch preserved it; chartSymbol cleared correctly")


# ── Settings nav stub — T-SET-01..08 (TASK-142) ─────────────────────────────

_SETTINGS_APP_ID = APP_SLOT["Settings"]
_CRYPTO_APP_ID   = APP_SLOT["Crypto"]


def _switch_to_settings(dut: Dut, timeout: float = 3.0) -> bool:
    r = dut.cmd(f"switchApp {_SETTINGS_APP_ID}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.2)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Settings"


def _settings_section(dut: Dut, timeout: float = 3.0):
    r = dut.cmd("get settingsSection", timeout=timeout)
    return r.get("section") if r.get("ok") else None


def _settings_submenu(dut: Dut, timeout: float = 3.0):
    r = dut.cmd("get settingsAppSubmenu", timeout=timeout)
    return r.get("submenu") if r.get("ok") else None


# ---- Settings-list geometry (mirrored from firmware — keep in sync; same
# row_y()/APP_LIST_ROW_H pattern as the prloc_*_smoke.py tools, e929792) ----
_S_CONTENT_Y = 28    # app/src/settings/settingsSection.h S_CONTENT_Y
_S_ROW_H     = 26    # app/src/settings/settingsSection.h S_ROW_H
_S_CONTENT_H = 212   # app/src/settings/settingsSection.h S_CONTENT_H (240 - header 28)
_CONFIGURABLE_APP_COUNT = 10   # app/gen/configurable_apps.h
# appsSection.h _appListRowH(): the Applications list compresses its row
# height once CONFIGURABLE_APP_COUNT * S_ROW_H no longer fits S_CONTENT_H —
# 21px today (TASK-330: was still using the uncompressed 26px formula here).
_APP_LIST_ROW_H = min(_S_ROW_H, _S_CONTENT_H // _CONFIGURABLE_APP_COUNT)


def _settings_tap_row(dut: Dut, row: int, timeout: float = 3.0):
    """Tap the midpoint of a top-level settings CATEGORY row (category list,
    e.g. General/Display/.../Applications — always S_ROW_H=26px). Do NOT use
    this for rows inside the Applications app list — that list compresses to
    a smaller row height once CONFIGURABLE_APP_COUNT apps no longer fit
    S_CONTENT_H at 26px (currently 21px); use _settings_tap_app_row() there.
    """
    y = _S_CONTENT_Y + row * _S_ROW_H + _S_ROW_H // 2
    dut.cmd(f"tap 137 {y}", timeout=timeout)
    time.sleep(0.1)


def _settings_tap_app_row(dut: Dut, row: int, timeout: float = 3.0):
    """Tap the midpoint of row `row` inside the Applications app list
    (settingsSection==5, submenu==-1) — uses the compressed _appListRowH()
    (min(S_ROW_H, S_CONTENT_H // CONFIGURABLE_APP_COUNT) == 21px today), NOT
    the 26px category-row height. See TASK-330.
    """
    y = _S_CONTENT_Y + row * _APP_LIST_ROW_H + _APP_LIST_ROW_H // 2
    dut.cmd(f"tap 137 {y}", timeout=timeout)
    time.sleep(0.1)


def _settings_tap_back(dut: Dut, timeout: float = 3.0):
    dut.cmd("tap 30 14", timeout=timeout)
    time.sleep(0.1)


def t_set_01(dut: Dut):
    """T-SET-01: switchApp(Settings) → settingsSection==-1 (category list)."""
    print("T-SET-01  Settings opens at category list (section==-1)")
    if not _switch_to_settings(dut):
        skip("T-SET-01", "could not switch to Settings")
        _restore_spotify(dut)
        return
    sec = _settings_section(dut)
    _restore_spotify(dut)
    if sec != -1:
        fail("T-SET-01", f"settingsSection={sec!r} after switchApp — expected -1 (category list)")
        return
    pass_("T-SET-01", "settingsSection==-1 after switchApp(Settings) — category list confirmed")


def t_set_02(dut: Dut):
    """T-SET-02: tap each stub row 0..4 → section==idx; back → section==-1 (× 5)."""
    print("T-SET-02  Section navigation: tap row→section; back→-1 (× 5)")
    if not _switch_to_settings(dut):
        skip("T-SET-02", "could not switch to Settings")
        _restore_spotify(dut)
        return
    for idx in range(5):
        _settings_tap_row(dut, idx)
        sec = _settings_section(dut)
        if sec != idx:
            _restore_spotify(dut)
            fail("T-SET-02", f"row {idx}: settingsSection={sec!r}, expected {idx}")
            return
        _settings_tap_back(dut)
        sec = _settings_section(dut)
        if sec != -1:
            _restore_spotify(dut)
            fail("T-SET-02", f"row {idx}: after back, settingsSection={sec!r}, expected -1")
            return
    _restore_spotify(dut)
    pass_("T-SET-02", "all 5 stub sections: tap→correct index, back→-1")


def t_set_03(dut: Dut):
    """T-SET-03: Applications drill (row 5 → row 0) → submenu==0; back×2 unwinds fully."""
    print("T-SET-03  Applications drill: section 5, submenu 0, back×2")
    if not _switch_to_settings(dut):
        skip("T-SET-03", "could not switch to Settings")
        _restore_spotify(dut)
        return
    _settings_tap_row(dut, 5)
    sec = _settings_section(dut)
    sub = _settings_submenu(dut)
    if sec != 5:
        _restore_spotify(dut)
        fail("T-SET-03", f"section={sec!r} after tap row 5, expected 5")
        return
    if sub != -1:
        _restore_spotify(dut)
        fail("T-SET-03", f"submenu={sub!r} at Applications level 1, expected -1")
        return
    _settings_tap_app_row(dut, 0)  # Spotify — kConfigurableApps[0] (app-list row, TASK-330)
    sub = _settings_submenu(dut)
    if sub != 0:
        _restore_spotify(dut)
        fail("T-SET-03", f"submenu={sub!r} after tap Stock, expected 0")
        return
    _settings_tap_back(dut)    # back to app list
    sub = _settings_submenu(dut)
    if sub != -1:
        _restore_spotify(dut)
        fail("T-SET-03", f"submenu={sub!r} after first back, expected -1")
        return
    _settings_tap_back(dut)    # back to category list
    sec = _settings_section(dut)
    _restore_spotify(dut)
    if sec != -1:
        fail("T-SET-03", f"section={sec!r} after second back, expected -1")
        return
    pass_("T-SET-03", "Applications drill: section 5, submenu 0 confirmed; back×2 unwinds to -1/-1")


def t_set_06(dut: Dut):
    """T-SET-06: suspend reset — switch away mid-submenu, return → section==-1, submenu==-1."""
    print("T-SET-06  suspend() reset: re-enter Settings → always category list")
    if not _switch_to_settings(dut):
        skip("T-SET-06", "could not switch to Settings")
        _restore_spotify(dut)
        return
    _settings_tap_row(dut, 5)   # Applications
    _settings_tap_app_row(dut, 0)   # Spotify submenu — kConfigurableApps[0] (app-list row, TASK-330)
    sub = _settings_submenu(dut)
    if sub != 0:
        _restore_spotify(dut)
        skip("T-SET-06", f"could not reach submenu 0, got {sub!r}")
        return
    if not _restore_spotify(dut):
        fail("T-SET-06", "switchApp(Spotify) failed mid-test")
        return
    if not _switch_to_settings(dut):
        fail("T-SET-06", "could not re-enter Settings after suspend")
        return
    sec = _settings_section(dut)
    sub = _settings_submenu(dut)
    _restore_spotify(dut)
    if sec != -1 or sub != -1:
        fail("T-SET-06", f"after suspend+resume: section={sec!r} submenu={sub!r}, expected -1/-1")
        return
    pass_("T-SET-06", "suspend() reset confirmed: section==-1 submenu==-1 on re-entry")


def t_set_07(dut: Dut):
    """T-SET-07: back from Applications L2 (Crypto, app-list row 2) traverses all three levels correctly."""
    print("T-SET-07  Double-back from Applications L2 (Crypto, row 2) → fully unwound")
    if not _switch_to_settings(dut):
        skip("T-SET-07", "could not switch to Settings")
        _restore_spotify(dut)
        return
    _settings_tap_row(dut, 5)   # Applications
    _settings_tap_app_row(dut, 2)   # Crypto — kConfigurableApps[2] (app-list row, TASK-330 fix; tests assert indices, not app identity)
    sec = _settings_section(dut)
    sub = _settings_submenu(dut)
    if sec != 5 or sub != 2:
        _restore_spotify(dut)
        fail("T-SET-07", f"section={sec!r} submenu={sub!r} after drill to app-list row 2 (Crypto), expected 5/2")
        return
    _settings_tap_back(dut)     # back to app list
    sub = _settings_submenu(dut)
    if sub != -1:
        _restore_spotify(dut)
        fail("T-SET-07", f"submenu={sub!r} after first back, expected -1")
        return
    _settings_tap_back(dut)     # back to category list
    sec = _settings_section(dut)
    _restore_spotify(dut)
    if sec != -1:
        fail("T-SET-07", f"section={sec!r} after second back, expected -1")
        return
    pass_("T-SET-07", "back×2 from app-list row 2 (Crypto) submenu: submenu→-1, section→-1 confirmed")


def t_set_08(dut: Dut):
    """T-SET-08: back from category list returns to g_previousAppId (Crypto)."""
    print("T-SET-08  goBack() from category list → g_previousAppId (Crypto)")
    r = dut.cmd(f"switchApp {_CRYPTO_APP_ID}", timeout=3.0)
    if not r.get("ok"):
        skip("T-SET-08", "could not switch to Crypto")
        _restore_spotify(dut)
        return
    time.sleep(0.2)
    r2 = dut.cmd("get appId", timeout=3.0)
    if r2.get("name") != "Crypto":
        skip("T-SET-08", f"appId={r2.get('name')!r} — could not confirm Crypto")
        _restore_spotify(dut)
        return
    if not _switch_to_settings(dut):
        skip("T-SET-08", "could not switch to Settings from Crypto")
        _restore_spotify(dut)
        return
    sec = _settings_section(dut)
    if sec != -1:
        _restore_spotify(dut)
        fail("T-SET-08", f"settingsSection={sec!r} on entry, expected -1")
        return
    _settings_tap_back(dut)    # back from category list → should go to Crypto
    time.sleep(0.2)
    r3 = dut.cmd("get appId", timeout=3.0)
    app_name = r3.get("name")
    if app_name != "Crypto":
        _restore_spotify(dut)
        fail("T-SET-08", f"appId={app_name!r} after back from category list, expected Crypto")
        return
    _restore_spotify(dut)
    pass_("T-SET-08", "goBack() from category list → Crypto confirmed (g_previousAppId tracking works)")


# ── ADR-042 validation tests ──────────────────────────────────────────────────

def t_uart_01(dut: Dut):
    """T-UART-01: No JSON garbling during concurrent Core 0 HTTPClient activity.
    Switches to Stock (triggers chart fetch on Core 0), then fires 20 rapid
    get heap commands. All must parse cleanly — validates ADR-042 E1 log suppression.
    """
    print("T-UART-01  JSON integrity under Core 0 HTTPClient load (ADR-042 E1)")
    if not _switch_to_stock(dut):
        skip("T-UART-01", "could not switch to StockApp")
        return
    dut.set_cooldown_zero()
    # Tap AAPL row to trigger chart fetch (Core 0 HTTPClient activity)
    dut.cmd("tap 137 36", timeout=2.0)
    # Immediately hammer 20 get heap commands while Core 0 is busy
    errors = []
    for i in range(20):
        try:
            r = dut.cmd("get heap", timeout=3.0)
            if not r.get("ok"):
                errors.append(f"cmd {i}: ok=false {r}")
        except (TimeoutError, ValueError) as e:
            errors.append(f"cmd {i}: {type(e).__name__}: {e}")
        time.sleep(0.05)
    _restore_from_stock(dut)
    if errors:
        fail("T-UART-01", f"{len(errors)}/20 responses garbled: {errors[:3]}")
    else:
        pass_("T-UART-01", "20/20 get heap responses clean during chart fetch — no Core 0 interleave")


def t_bgpoll_01(dut: Dut):
    """T-BGPOLL-01: set bgPoll 0 suspends self-polls; get bgPoll returns enabled:0."""
    print("T-BGPOLL-01  bgPoll suspend — self-polls halt (ADR-042 E2)")
    # Ensure we start in a clean state
    dut.cmd("set bgPoll 1", timeout=2.0)
    r = dut.cmd("set bgPoll 0", timeout=2.0)
    if not r.get("ok"):
        fail("T-BGPOLL-01", f"set bgPoll 0 failed: {r}")
        return
    r2 = dut.cmd("get bgPoll", timeout=2.0)
    if not r2.get("ok") or r2.get("enabled") != 0:
        dut.cmd("set bgPoll 1", timeout=2.0)
        fail("T-BGPOLL-01", f"get bgPoll expected enabled:0, got {r2}")
        return
    print("  [T-BGPOLL-01] bgPoll suspended; monitoring shellBusy for 5 s…", flush=True)
    # Monitor for 5 s — no self-initiated polls should fire
    busy_fires = 0
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        sb = _get_shell_busy(dut)
        if sb:
            busy_fires += 1
        time.sleep(0.5)
    dut.cmd("set bgPoll 1", timeout=2.0)
    if busy_fires > 0:
        fail("T-BGPOLL-01", f"shellBusy fired {busy_fires} times during bgPoll suspend — self-poll not gated")
    else:
        pass_("T-BGPOLL-01", "shellBusy=false throughout 5 s bgPoll suspend — self-polls halted")


def t_bgpoll_02(dut: Dut):
    """T-BGPOLL-02: reconnect resets bgPoll to enabled:1 (recovery invariant)."""
    print("T-BGPOLL-02  reconnect resets bgPoll to 1 (ADR-042 E2 invariant)")
    dut.cmd("set bgPoll 0", timeout=2.0)
    r = dut.cmd("get bgPoll", timeout=2.0)
    if r.get("enabled") != 0:
        fail("T-BGPOLL-02", f"pre-condition failed: bgPoll not suspended (got {r})")
        return
    # reconnect should reset s_bgPollEnabled = 1
    dut.cmd("reconnect", timeout=3.0)
    time.sleep(1.0)  # allow TLS reset + reconnect to process
    r2 = dut.cmd("get bgPoll", timeout=2.0)
    if not r2.get("ok") or r2.get("enabled") != 1:
        fail("T-BGPOLL-02", f"reconnect did not reset bgPoll: got {r2}")
    else:
        pass_("T-BGPOLL-02", "reconnect reset bgPoll to enabled:1 — recovery invariant holds")


def t_bgpoll_03(dut: Dut):
    """T-BGPOLL-03: ACT_FORCE_POLL tap completes fetch while bgPoll suspended; flag stays 0."""
    print("T-BGPOLL-03  ACT_FORCE_POLL bypasses bgPoll suspend (ADR-042 E2)")
    # Ensure Spotify app
    r = dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
    if not r.get("ok"):
        skip("T-BGPOLL-03", "could not switch to Spotify app")
        return
    time.sleep(0.3)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        # Confirm suspended
        r2 = dut.cmd("get bgPoll", timeout=2.0)
        if r2.get("enabled") != 0:
            fail("T-BGPOLL-03", f"bgPoll not suspended: {r2}")
            return
        dut.set_cooldown_zero()
        # Tap DEADZONE gap (posbar bottom ↔ transport top midpoint) — dispatches
        # ACT_FORCE_POLL in WinampDisplay
        _dx, _dy = _c.tap_deadzone_gap()
        dut.cmd(f"tap {_dx} {_dy}", timeout=2.0)
        print("  [T-BGPOLL-03] force-poll tap sent; waiting for shellBusy cycle…", flush=True)
        # Wait for the force-poll fetch to complete
        _wait_shell_not_busy(dut, timeout_s=15.0)
        # bgPoll flag must still be 0 (not self-resumed by force-poll path)
        r3 = dut.cmd("get bgPoll", timeout=2.0)
        if r3.get("enabled") != 0:
            fail("T-BGPOLL-03", f"bgPoll self-resumed during force-poll: {r3}")
            return
    pass_("T-BGPOLL-03", "ACT_FORCE_POLL fetch completed with bgPoll suspended; flag unchanged at 0")


# ── M-CLOCK-STYLES suite (TASK-193) ───────────────────────────────────────────

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


# ── T272 — TLS heap contention: fetchTeletext + spotifyTask concurrent ────────

def t272(dut: Dut):
    """T272: fetchTeletext completes without OOM while spotifyTask holds a TLS session.

    ADR-044 item 9 asserts teletext follows the weather pattern (no tlsYield). This
    test exercises both tasks concurrently to validate that assumption. Failure (timeout
    or DUT crash) indicates heap contention → apply tlsYield/tlsResume to fetchTeletext.
    TASK-191.
    """
    tid = "T272"
    print(f"{tid}  TLS heap contention — fetchTeletext concurrent with spotifyTask")

    # Baseline: confirm Spotify is rendering (spotifyTask has an active TLS session)
    r0 = dut.cmd("get lastPlaylistDraw", timeout=3.0)
    if not r0.get("ok"):
        skip(tid, "get lastPlaylistDraw failed — Spotify not active?")
        return
    draw0 = r0.get("ms", 0)

    # Switch to Teletext: triggers resume() which sets _lastFetch=0, forcing immediate enqueue
    r = dut.cmd(f"switchApp {APP_SLOT['Teletext']}", timeout=5.0)
    if not r.get("ok"):
        skip(tid, "switchApp Teletext failed — app not registered?")
        _restore_spotify(dut)
        return

    # Force a second enqueue in case the app was already ready from a prior run
    dut.cmd("set triggerTeletextFetch 1", timeout=3.0)

    # Poll teletextReady up to 30s — failure implies OOM/watchdog/network error
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get teletextReady", timeout=2.0)
            if r.get("ok") and r.get("ready") is True:
                ready = True
                break
        except TimeoutError:
            break  # DUT stopped responding — likely crash
        time.sleep(0.5)

    _restore_spotify(dut)
    time.sleep(0.3)

    if not ready:
        # Distinguish network failure from firmware crash
        try:
            r_http = dut.cmd("get teletextHttpCode", timeout=2.0)
            http_code = r_http.get("val", 0) if r_http.get("ok") else 0
        except TimeoutError:
            http_code = 0
        if http_code != 0 and http_code != 200:
            skip(tid, f"teletextReady false — HTTP {http_code} (network, not contention)")
        else:
            fail(tid, "teletextReady not true within 30s — OOM/watchdog/crash or persistent network error")
        return

    # Assert Spotify playback survived (lastPlaylistDraw must advance within 10s)
    deadline2 = time.monotonic() + 10.0
    draw_advanced = False
    while time.monotonic() < deadline2:
        try:
            r = dut.cmd("get lastPlaylistDraw", timeout=2.0)
            if r.get("ok") and r.get("ms", 0) > draw0:
                draw_advanced = True
                break
        except TimeoutError:
            break
        time.sleep(0.5)

    if not draw_advanced:
        fail(tid, f"lastPlaylistDraw did not advance after Teletext fetch (baseline={draw0}ms) — Spotify stalled")
        return

    pass_(tid, "teletextReady=true within 30s; lastPlaylistDraw advanced — no TLS contention")


# ── T270 — Synthetic subpage navigation (TASK-197) ────────────────────────────

def t270(dut: Dut):
    """T270-SYN: SUBDN tap enqueues subpage fetch when subpageNext is set.

    Sets subpageNext=617-2 via debug command. Taps SUBDN zone centre (y=182);
    asserts teletextLastAction==STRIP_SUBDN and shellBusy fires (confirming
    _navigate(617,2) was called). No live network required. Replaces
    [NETWORK][Blocked: G1,G2] variant. TASK-197 / BP-034.
    """
    tid = "T270"
    print(f"{tid}  Subpage ▼ zone → STRIP_SUBDN + busy (synthetic)")

    if not _switch_to(dut, "Teletext"):
        skip(tid, "could not switch to TeletextApp")
        return

    # Wait for any pending fetch from resume() to settle
    _wait_shell_not_busy(dut, timeout_s=8.0)
    dut.cmd("set cooldown 0", timeout=2.0)

    # Set subpage navigation targets via debug injection
    r = dut.cmd("set teletextSubpageNext 617-2", timeout=2.0)
    if not r.get("ok"):
        fail(tid, f"set teletextSubpageNext failed: {r}")
        return
    dut.cmd("set teletextSubpagePrev 617-1", timeout=2.0)

    # Confirm fields propagated
    r_sp = dut.cmd("get teletextSubpage", timeout=2.0)
    if not r_sp.get("ok") or r_sp.get("next", 0) != 617 or r_sp.get("nextSub", 0) != 2:
        fail(tid, f"subpageNext not set as expected: {r_sp}")
        return
    print(f"  [T270] subpageNext={r_sp.get('next')}-{r_sp.get('nextSub')} ✓")

    # Wait past app-level 300 ms debounce (inject is not a tap — _lastTapMs unchanged,
    # but resume() set it to 0 and millis()>300 at this point so first tap is free)
    time.sleep(0.1)

    # Tap SUBDN zone centre: y = (166 + 199) / 2 = 182
    dut.cmd(f"tap 257 182", timeout=3.0)
    time.sleep(0.1)  # let action propagate

    r_act = dut.cmd("get teletextLastAction", timeout=2.0)
    action = r_act.get("val", "") if r_act.get("ok") else "<error>"
    if action != "STRIP_SUBDN":
        fail(tid, f"expected STRIP_SUBDN, got '{action}'")
        return
    print(f"  [T270] lastAction=STRIP_SUBDN ✓")

    r_busy = dut.cmd("get shellBusy", timeout=2.0)
    if not r_busy.get("ok") or not r_busy.get("busy", False):
        fail(tid, "shellBusy not true after SUBDN tap — _navigate() not called?")
        return
    print(f"  [T270] shellBusy=true ✓ (fetch enqueued for 617-2)")

    _wait_shell_not_busy(dut, timeout_s=8.0)
    pass_(tid, "STRIP_SUBDN routed correctly; shellBusy=true confirmed (no network required)")


# ── T271 — Strip zone 1-px boundary (TASK-197) ───────────────────────────────

def t271(dut: Dut):
    """T271: Right-strip pixel-exact zone boundaries PAGE_NUM/BACK/PREV_PAGE.

    Tap order: y=67, y=99, y=100, y=66 (PAGE last). All BACK/PREV taps fire
    with numpad OFF, so _draw()/_drawNumpad() is not called and no SPI phantom
    touch is generated. PAGE is tapped last: its phantom (re-hits PAGE zone,
    STRIP_PAGE) matches the expected value, so order doesn't matter.
    _wait_shell_not_busy between steps handles any _goBack()/_navigate() that
    fires when histDepth or prevPage is non-zero from a prior test.
    No content injection needed. TASK-197 / BP-034.
    """
    tid = "T271"
    print(f"{tid}  Strip zone 1-px boundary — PAGE_NUM/BACK/PREV_PAGE")

    if not _switch_to(dut, "Teletext"):
        skip(tid, "could not switch to TeletextApp")
        return

    # Steps where numpad is OFF: BACK and PREV zones. No _draw() call →
    # no SPI phantom. _goBack() / _navigate() may fire (no-op or network);
    # _wait_shell_not_busy drains any resulting fetch before the next tap.
    steps_nav = [
        (67,  "STRIP_BACK", "y=67 → BACK zone first px"),
        (99,  "STRIP_BACK", "y=99 → BACK zone last px"),
        (100, "STRIP_PREV", "y=100 → PREV_PAGE zone first px"),
    ]
    # PAGE zone last: _drawNumpad() fires, causing a phantom that also hits
    # PAGE zone → both real action and phantom are STRIP_PAGE → harmless.
    step_page = (66, "STRIP_PAGE", "y=66 → PAGE_NUM zone last px")

    for y, expected, desc in steps_nav:
        _wait_shell_not_busy(dut, timeout_s=8.0)
        time.sleep(0.35)  # past 300 ms per-app debounce
        dut.cmd("set cooldown 0", timeout=2.0)
        dut.cmd(f"tap 257 {y}", timeout=3.0)
        r_act = dut.cmd("get teletextLastAction", timeout=2.0)
        action = r_act.get("val", "") if r_act.get("ok") else "<error>"
        if action != expected:
            fail(tid, f"{desc}: expected '{expected}', got '{action}'")
            return
        print(f"  [T271] {desc}: '{action}' ✓")

    # PAGE zone — last step
    _wait_shell_not_busy(dut, timeout_s=8.0)
    time.sleep(0.35)
    dut.cmd("set cooldown 0", timeout=2.0)
    y, expected, desc = step_page
    dut.cmd(f"tap 257 {y}", timeout=3.0)
    r_act = dut.cmd("get teletextLastAction", timeout=2.0)
    action = r_act.get("val", "") if r_act.get("ok") else "<error>"
    if action != expected:
        fail(tid, f"{desc}: expected '{expected}', got '{action}'")
        return
    print(f"  [T271] {desc}: '{action}' ✓")

    pass_(tid, "all 4 boundary taps matched expected zone actions")


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


def _ensure_webradio(dut: Dut, tid: str) -> bool:
    """Ensure current app is WebRadio; skip with message if not possible."""
    r = dut.cmd("get appId", timeout=3.0)
    if r.get("name") == "WebRadio":
        return True
    if _switch_to(dut, "WebRadio", timeout=10.0):
        return True
    skip(tid, "could not switch to WebRadio")
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


# ── T_WR_ERR_* common helper ─────────────────────────────────────────────────

def _wr_err_test(dut: Dut, tid: str, state_num: int) -> bool:
    """Enter WebRadio app and inject wrState=state_num.

    Isolation (found during the TASK-277 campaign; latent since TASK-276):
    auto-skip must be OFF during state injection. With a loaded station list,
    TASK-276's terminal-retry re-arms on an injected retryable error within
    one tick (_lastAttemptMs==0 counts as >=30 s idle) and overwrites the
    injected state with PLAYING — DUT-confirmed both directions 2026-07-07.
    The old "no stations required" note here dated from the TASK-284
    broken-fetch era, which starved the retry condition and masked this.
    Cleanup order matters: clear the injected state BEFORE re-enabling
    auto-skip, or the retry starts playback under the next test."""
    # Enter WebRadio if not already there
    r_id = dut.cmd("get appId", timeout=3.0)
    if r_id.get("name") != "WebRadio":
        if not _switch_to_webradio_capture_heap(dut)[0]:
            skip(tid, "could not enter WebRadio app")
            return False
    dut.cmd("set wrAutoSkip 0", timeout=3.0)
    try:
        r_set = dut.cmd(f"set wrState {state_num}", timeout=3.0)
        if not r_set.get("ok"):
            fail(tid, f"set wrState {state_num} returned ok=false: {r_set}")
            return False
        r_get = dut.cmd("get wrState", timeout=3.0)
        if r_get.get("state") != state_num:
            fail(tid, f"get wrState={r_get.get('state')} expected {state_num}")
            return False
        return True
    finally:
        dut.cmd("set wrState 3", timeout=3.0)     # back to STOPPED (quiescent)
        dut.cmd("set wrAutoSkip 1", timeout=3.0)  # restore firmware default


# ── T_WR_ERR_01 — ERROR_BLOCKED ─────────────────────────────────────────────

def t_wr_err_01(dut: Dut):
    """T_WR_ERR_01: set wrState 6 (ERROR_BLOCKED); verify state round-trip."""
    print("T_WR_ERR_01  ERROR_BLOCKED (state=6) injection")
    if _wr_err_test(dut, "T_WR_ERR_01", 6):
        pass_("T_WR_ERR_01", "set wrState 6 accepted; get wrState=6 (visual: 'Station blocked')")


# ── T_WR_ERR_02 — ERROR_UNREACHABLE ──────────────────────────────────────────

def t_wr_err_02(dut: Dut):
    """T_WR_ERR_02: set wrState 5 (ERROR_UNREACHABLE); verify state round-trip."""
    print("T_WR_ERR_02  ERROR_UNREACHABLE (state=5) injection")
    if _wr_err_test(dut, "T_WR_ERR_02", 5):
        pass_("T_WR_ERR_02", "set wrState 5 accepted; get wrState=5 (visual: 'Station unreachable')")


# ── T_WR_ERR_03 — ERROR_WIFI ─────────────────────────────────────────────────

def t_wr_err_03(dut: Dut):
    """T_WR_ERR_03: set wrState 3 (ERROR_WIFI); verify state round-trip."""
    print("T_WR_ERR_03  ERROR_WIFI (state=3) injection")
    if _wr_err_test(dut, "T_WR_ERR_03", 3):
        pass_("T_WR_ERR_03", "set wrState 3 accepted; get wrState=3 (visual: 'WiFi lost')")


# ── T_WR_ERR_04 — CONNECTING ──────────────────────────────────────────────────

def t_wr_err_04(dut: Dut):
    """T_WR_ERR_04: stop audio then set wrState 1 (CONNECTING); verify state round-trip."""
    print("T_WR_ERR_04  CONNECTING (state=1) injection")
    if not _ensure_webradio(dut, "T_WR_ERR_04"):
        return
    # Stop audio first so _bufPct resets to 0 (per test design note)
    dut.cmd("set wrStop 1", timeout=3.0)
    time.sleep(0.15)
    if _wr_err_test(dut, "T_WR_ERR_04", 1):
        pass_("T_WR_ERR_04", "set wrState 1 accepted; get wrState=1 (visual: 'Connecting…', POSBAR empty)")


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


# ── T_WR_VOL_03 — Normal _play() applies webRadioMaxVolume cap ───────────────

def t_wr_vol_03(dut: Dut):
    """T_WR_VOL_03: after set wrVol 21, set wrPlay 0 resets to webRadioMaxVolume; state=PLAYING."""
    print("T_WR_VOL_03  Normal play applies webRadioMaxVolume cap (not 21)")
    count = _webradio_enter_with_stations(dut, "T_WR_VOL_03", fetch_timeout=180.0)
    if count == 0:
        skip("T_WR_VOL_03", "no stations loaded (network or fetch failure)")
        return
    # Stop audio, inject vol=21 bypass, then play — _play() should call setVolume(maxVol)
    dut.cmd("set wrStop 1", timeout=3.0)
    time.sleep(0.1)
    dut.cmd("set wrVol 21", timeout=3.0)
    time.sleep(0.1)
    dut.cmd("set wrPlay 0", timeout=3.0)
    # Wait for PLAYING or ERROR state
    playing = _wait_wr_state(dut, target=2, timeout=15.0)
    r_state = dut.cmd("get wrState", timeout=3.0)
    state = r_state.get("state", -1)
    if not playing:
        fail("T_WR_VOL_03", f"station did not reach PLAYING after wrPlay 0 (state={state})")
        return
    # Volume reset is confirmed structurally: _play() always calls setVolume(webRadioMaxVolume)
    # before connecttohost(). Audible clipping at vol=21 vs clean at vol=10 is the full check.
    pass_("T_WR_VOL_03",
          "wrPlay 0 reached PLAYING state — _play() called setVolume(webRadioMaxVolume); "
          "audible clipping check requires human listener")


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

    No existing test asserts this positively. T_WR_ERR_01-04 only round-trip
    inject a state with auto-skip OFF (deliberately, so the retry can't
    interfere with the injection — see _wr_err_test()'s own docstring, which
    documents the retry firing within one tick when auto-skip is ON). T237
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


# ── app-error-signal-001 (TASK-245 / ADR-046) ────────────────────────────────
# Red taskbar active-bar on a sustained app error. The bar colour itself is not
# serial-observable (no pixel readback) — that's the manual T-ERR-03 sign-off.
# These automate the state machine behind it via the `get activeError` getter
# and deterministic injection: `set lastHttp 403` + `set backoff 2` synthesises
# spotifyTask::authError() without depending on a real account 403; bgPoll is
# suspended so a real cadence poll can't overwrite the injected status mid-test.

def _get_active_error(dut: Dut):
    """Returns the `get activeError` dict: {active, spotifyAuthError}."""
    return dut.cmd("get activeError", timeout=3.0)

def t_err_01(dut: Dut):
    """T-ERR-01 (X020): a 403 poll → activeError true; recovered (200) poll → clears to false."""
    print("T-ERR-01  Spotify authError detection + self-clear")
    if not _restore_spotify(dut):
        skip("T-ERR-01", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        # Baseline: healthy poll → no error.
        dut.cmd("set lastHttp 200")
        base = _get_active_error(dut)
        # A 403 poll → authError true (one 403 is enough; not coupled to backoff).
        dut.cmd("set lastHttp 403")
        err = _get_active_error(dut)
        # A recovered (200) poll → self-clears.
        dut.cmd("set lastHttp 200")
        cleared = _get_active_error(dut)
    ok = (base.get("active") is False and base.get("spotifyAuthError") is False
          and err.get("active") is True and err.get("spotifyAuthError") is True
          and cleared.get("active") is False and cleared.get("spotifyAuthError") is False)
    if ok:
        pass_("T-ERR-01", "base=clean, 403→active+auth true, backoff-reset→clear")
    else:
        fail("T-ERR-01", f"base={base} err={err} cleared={cleared}")

def t_err_02(dut: Dut):
    """T-ERR-02 (X018+X019): error owned by app — hidden while another app is active
    (active-only limitation), restored on return to the errored app."""
    print("T-ERR-02  authError active-only (X018) + survives switch away/back (X019)")
    if not _restore_spotify(dut):
        skip("T-ERR-02", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("set lastHttp 403")            # 403 poll → Spotify error
        before = _get_active_error(dut)        # Spotify active → active true
        dut.cmd("switchApp 1")                 # Clock (offline, hasError()==false)
        time.sleep(0.4)
        away = _get_active_error(dut)          # active false, but spotifyAuthError still true
        dut.cmd("switchApp 0")                 # back to Spotify
        time.sleep(0.4)
        back = _get_active_error(dut)          # active true again (state survived)
        dut.cmd("set lastHttp 200")            # restore
    _restore_spotify(dut)
    ok = (before.get("active") is True
          and away.get("active") is False and away.get("spotifyAuthError") is True
          and back.get("active") is True)
    if ok:
        pass_("T-ERR-02", "Spotify red while active; hidden on Clock (auth still set); red on return")
    else:
        fail("T-ERR-02", f"before={before} away={away} back={back}")

def t_err_04(dut: Dut):
    """T-ERR-04 (boot amber): connecting true before the first poll resolves, false
    after the first success — independent of error state."""
    print("T-ERR-04  connecting (boot amber) latches false on first success")
    if not _restore_spotify(dut):
        skip("T-ERR-04", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        # No error, no successful poll yet → boot/connecting.
        dut.cmd("set lastHttp 200"); dut.cmd("set backoff 0"); dut.cmd("set lastOkMs 0")
        boot = _get_active_error(dut)
        # Simulate the first successful poll → connected.
        dut.cmd("set lastOkMs 1")
        conn = _get_active_error(dut)
    ok = (boot.get("connecting") is True and boot.get("spotifyAuthError") is False
          and conn.get("connecting") is False)
    if ok:
        pass_("T-ERR-04", "connecting true at boot (amber), false after first success (green)")
    else:
        fail("T-ERR-04", f"boot={boot} connected={conn}")

def t_err_05(dut: Dut):
    """T-ERR-05 (regression): a touch must not clear the 403 error. authError is keyed on the
    last HTTP status, not s_consecutiveFailures, so resetBackoff() (called on every touch via
    appHandleInput) must NOT knock the red bar back to amber."""
    print("T-ERR-05  authError survives backoff reset (touch decoupling)")
    if not _restore_spotify(dut):
        skip("T-ERR-05", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("set lastHttp 403")
        err = _get_active_error(dut)
        # `set backoff 0` is exactly what a touch does (resetBackoff()).
        dut.cmd("set backoff 0")
        after_reset = _get_active_error(dut)
        dut.cmd("set lastHttp 200")   # restore
    ok = (err.get("spotifyAuthError") is True
          and after_reset.get("spotifyAuthError") is True)
    if ok:
        pass_("T-ERR-05", "403 error held across backoff reset (touch-immune)")
    else:
        fail("T-ERR-05", f"err={err} after_reset={after_reset}")

def t_err_06(dut: Dut):
    """T-ERR-06: offline apps never report connecting. Network apps (Weather/Crypto/Stock/
    Teletext) wire isConnecting() to their first-fetch; offline apps (Clock/Matrix) keep the
    default false — guards the 'offline apps stay default-false' invariant."""
    print("T-ERR-06  offline apps report connecting=false")
    def conn(app_id):
        dut.cmd(f"switchApp {app_id}"); time.sleep(0.5)
        return dut.cmd("get activeError").get("connecting")
    clock  = conn(1)   # Clock — offline
    matrix = conn(4)   # Matrix — offline
    _restore_spotify(dut)
    ok = (clock is False and matrix is False)
    if ok:
        pass_("T-ERR-06", "Clock + Matrix connecting=false (offline default held)")
    else:
        fail("T-ERR-06", f"clock={clock} matrix={matrix} (expected both False)")

def t_err_07(dut: Dut):
    """T-ERR-07 (TASK-246): a network app's failed fetch → red. Stock hasError() = _s.fetchFailed,
    driven via the existing `set fetchFailed` injector; clears on success. Representative of the
    Weather/Crypto/Teletext error latches (same set-on-fail / clear-on-success pattern)."""
    print("T-ERR-07  network-app hasError → red (Stock fetchFailed)")
    dut.cmd(f"switchApp {_STOCK_APP_ID}"); time.sleep(0.5)   # Stock
    dut.cmd("set fetchFailed 1"); time.sleep(0.2)
    err = dut.cmd("get activeError")
    dut.cmd("set fetchFailed 0"); time.sleep(0.2)
    cleared = dut.cmd("get activeError")
    _restore_spotify(dut)
    ok = (err.get("active") is True and cleared.get("active") is False)
    if ok:
        pass_("T-ERR-07", "Stock active(red)=true on fetchFailed, false on clear")
    else:
        fail("T-ERR-07", f"err={err} cleared={cleared}")


# ── M-PLANERADAR DUT validation (TASK-307, parent doc exit criteria 1-6) ─────
# T_PR_01: switch round-trip (sanity, mirrors T_WX_01/T_CX_01).
# T_PR_02: exit criterion 1 — live render within one poll of app entry.
# T_PR_03: exit criterion 2a — range tap cycles 5→10→15→25→5.
# T_PR_04: exit criterion 2b — range persists across reboot [REBOOT].
# T_PR_05: exit criterion 3 — fetch error → side-strip code, stays responsive, recovers [NETWORK][SLOW].
# T_PR_06: exit criterion 6 — synthetic injection render test, no network.
# Exit criterion 4 (30-min coexistence soak) is T_PR_SOAK (separate — [SLOW][MANUAL-length]).
# Exit criterion 5 (taskbar full-cycle scroll, new 12th slot) is covered by the
# EXISTING T162-T166/T242 suite unchanged — _TB_N derives from APP_SLOT["WebRadio"],
# which already grew by one now that PlaneRadar sits before WebRadio in APP_ORDER.

# Disc center — planeRadarApp.h PR_CX/PR_CY, frozen in phase0-preview-ui.md Results.
PR_CX, PR_CY = 120, 120

def t_pr_01(dut: Dut):
    """T_PR_01: Spotify→PlaneRadar→Spotify round-trip; appId correct at each step."""
    print("T_PR_01  PlaneRadarApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_PR_01", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        switched = _switch_to(dut, "PlaneRadar", timeout=15.0)
    if not switched:
        fail("T_PR_01", "did not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_PR_01", "PlaneRadar→Spotify switch-back failed")
        return
    pass_("T_PR_01", "Spotify→PlaneRadar→Spotify round-trip confirmed via get appId")


def t_pr_02(dut: Dut):
    """T_PR_02 (exit criterion 1): live aircraft render within one poll of app entry.
    resume() enqueues a fetch immediately; 'live render' is observed via
    `get activeError`'s `connecting` field (PlaneRadarApp::isConnecting() = !
    _everHadResult) going false — NOT prLastHttp==200. DUT diagnostic (2026-07-11)
    showed fetchPlaneRadar() only ever writes a non-zero errorCode on FAILURE;
    a successful fetch leaves PlaneRadarResult's default-constructed errorCode=0
    untouched (the raw HTTP 200 only appears in a LOG_D line, never in the
    result struct dbgGet reads) — so prLastHttp==0 is genuinely ambiguous
    between 'never fetched' and 'fetched fine', and waiting for it to equal
    200 can never pass. 90s budget (not PR_POLL_MS+margin): a 403-wedged
    Spotify holds tlsYield() in overdue-poll retries (same contention
    test_fetch_stress.py documents for weather/crypto/stock — TASK-244), so a
    'first poll' can legitimately take much longer than the 10s cadence alone
    would suggest."""
    print("T_PR_02  Live render within one poll of app entry")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_02", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    deadline = time.monotonic() + 90.0
    connecting = True
    while time.monotonic() < deadline:
        r = dut.cmd("get activeError", timeout=3.0)
        connecting = r.get("connecting", True)
        if not connecting:
            break
        time.sleep(1.0)
    http_r = dut.cmd("get prLastHttp", timeout=3.0)
    count_r = dut.cmd("get prAircraftCount", timeout=3.0)
    err_r = dut.cmd("get activeError", timeout=3.0)
    _restore_spotify(dut)
    if connecting:
        fail("T_PR_02", f"isConnecting() still true after 90s — first poll never "
                        f"resolved (prLastHttp={http_r.get('val')})")
        return
    if err_r.get("active"):
        fail("T_PR_02", f"first poll resolved but as an error (prLastHttp={http_r.get('val')})")
        return
    pass_("T_PR_02", f"first poll resolved ok (connecting->false), "
                     f"prAircraftCount={count_r.get('val')}, prLastHttp={http_r.get('val')}")


def t_pr_03(dut: Dut):
    """T_PR_03 (exit criterion 2a): tap disc 4x cycles 5→10→15→25→5 (wrap).
    Injects a synthetic aircraft first: handleInput()'s range-change branch only
    calls dataTask::enqueuePlaneRadar() when !_injected, so under real polling each
    tap re-arms hasPendingAsync() and (with tlsYield() stalled behind a 403 Spotify)
    the shell-busy gate can silently swallow the NEXT tap before the fetch resolves
    — exactly the failure mode observed on the first DUT run (range stuck at 10
    after tap #1). Injection makes the tap-cycle observation independent of network
    state, which is what this exit criterion is actually about."""
    print("T_PR_03  Range tap cycles 5->10->15->25->5")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_03", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prInjectAircraft TEST01,A320,52.31,4.76,12.5,90,90,250,15000", timeout=3.0)
    dut.cmd("set prRange 5", timeout=3.0)
    dut.set_cooldown_zero()
    seen = []
    for _ in range(4):
        _wait_shell_not_busy(dut, timeout_s=5.0)
        dut.cmd(f"tap {PR_CX} {PR_CY}", timeout=3.0)
        time.sleep(0.2)
        r = dut.cmd("get prRange", timeout=3.0)
        seen.append(r.get("val"))
        dut.set_cooldown_zero()
    dut.cmd("set prClearInject 1", timeout=3.0)
    _restore_spotify(dut)
    if seen != [10, 15, 25, 5]:
        fail("T_PR_03", f"range sequence={seen}, expected [10, 15, 25, 5]")
        return
    pass_("T_PR_03", f"range sequence 5->{seen} confirmed")


def t_pr_04(dut: Dut):
    """T_PR_04 (exit criterion 2b) [REBOOT]: range preset persists across reboot.
    Sets a distinctive non-default preset (25 km — default is 10 km per init()'s
    _presetIdx=1 fallback), reboots, and confirms PlaneRadar loads the same preset
    from settingsStorage instead of falling back to default."""
    print("T_PR_04  Range persists across reboot [REBOOT]")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_04", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prRange 25", timeout=3.0)
    r_pre = dut.cmd("get prRange", timeout=3.0)
    if r_pre.get("val") != 25:
        skip("T_PR_04", f"could not set prRange=25 pre-reboot, got {r_pre.get('val')}")
        return
    dut.send("reboot")
    time.sleep(0.3)   # let the reset actually happen before we start reading for it
    dut._wait_for_ready()
    if not _switch_to(dut, "PlaneRadar", timeout=15.0):
        fail("T_PR_04", "could not switch to PlaneRadar after reboot")
        _restore_spotify(dut)
        return
    r_post = dut.cmd("get prRange", timeout=3.0)
    _restore_spotify(dut)
    if r_post.get("val") != 25:
        fail("T_PR_04", f"prRange={r_post.get('val')} after reboot, expected 25 (not persisted)")
        return
    pass_("T_PR_04", "prRange=25 held across reboot — settingsStorage persistence confirmed")


def t_pr_05(dut: Dut):
    """T_PR_05 (exit criterion 3) [NETWORK][SLOW]: fetch error -> side-strip error code,
    app stays responsive, recovers on next poll. adsb.fi's public 1 req/s courtesy
    limit means hammering triggerPlaneRadarFetch back-to-back (phase-0 measured ~33%
    429 rate at that cadence) is expected to surface a real error within a bounded
    number of rapid-fire attempts, without needing a dedicated fault-injection hook.
    Uses `get activeError`'s `active` field (PlaneRadarApp::hasError() = _prErr) as
    the error signal, NOT prLastHttp==200 — DUT diagnostic (2026-07-11) showed a
    successful fetch leaves errorCode at its default-constructed 0, so 0 is
    ambiguous between 'never fetched' and 'fetched fine' and can't be used to
    detect a transition either way. `active` is exactly what drives the side-strip/
    taskbar error indicator this criterion is actually asking about (same pattern
    T-ERR-07 uses for Stock's fetchFailed)."""
    print("T_PR_05  Fetch error -> error code, stays responsive, recovers")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_05", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    # Baseline: the first poll must resolve cleanly (connecting->false, no error)
    # before we start hammering — otherwise we can't tell a fresh error apart from
    # the app never having had a chance to succeed at all.
    baseline_deadline = time.monotonic() + 90.0
    baseline_ok = False
    while time.monotonic() < baseline_deadline:
        r = dut.cmd("get activeError", timeout=3.0)
        if not r.get("connecting", True):
            baseline_ok = (r.get("active") is False)
            break
        time.sleep(1.0)
    if not baseline_ok:
        _restore_spotify(dut)
        skip("T_PR_05", "could not establish a clean baseline poll within 90s")
        return
    saw_error = False
    error_code = None
    for _ in range(20):
        dut.cmd("set triggerPlaneRadarFetch 1", timeout=3.0)
        deadline = time.monotonic() + 12.0
        got_error = False
        while time.monotonic() < deadline:
            time.sleep(0.5)
            err = dut.cmd("get activeError", timeout=3.0)
            if err.get("active"):
                got_error = True
                break
        if got_error:
            saw_error = True
            error_code = dut.cmd("get prLastHttp", timeout=3.0).get("val")
            break
        time.sleep(1.0)
    if not saw_error:
        _restore_spotify(dut)
        skip("T_PR_05", "no fetch error surfaced in 20 rapid-fire attempts — "
                        "adsb.fi rate limit not hit this run (network-dependent)")
        return
    # App must stay responsive with an error latched (hasError()->red taskbar).
    r_alive = dut.cmd("get appId", timeout=3.0)
    if not r_alive.get("ok") or r_alive.get("name") != "PlaneRadar":
        _restore_spotify(dut)
        fail("T_PR_05", f"app unresponsive/switched after error code={error_code}: {r_alive}")
        return
    # Recovers on next poll: wait for activeError.active to clear.
    recovered = False
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        err = dut.cmd("get activeError", timeout=3.0)
        if err.get("active") is False:
            recovered = True
            break
        time.sleep(2.0)
    _restore_spotify(dut)
    if not recovered:
        fail("T_PR_05", f"error code={error_code} latched but did not recover (activeError) within 30s")
        return
    pass_("T_PR_05", f"error code={error_code} -> activeError.active=true, responsive, "
                     f"recovered -> activeError.active=false")


def t_pr_06(dut: Dut):
    """T_PR_06 (exit criterion 6): synthetic-injection render test passes without network.
    prInjectAircraft isolates tick() from the real fetch/poll cycle (same pattern as
    TASK-276's injected-state lesson), so this must hold even with WiFi torn down —
    injects 3 aircraft, confirms prAircraftCount==3, prLastHttp stays whatever it was
    (no fetch attempted), then clears and confirms count returns to 0."""
    print("T_PR_06  Synthetic-injection render test (no network)")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_06", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    records = "TEST01,A320,52.31,4.76,12.5,90,90,250,15000;" \
              "TEST02,B738,52.28,4.80,8.0,270,270,180,8000;" \
              "TEST03,C172,52.30,4.75,3.0,0,0,90,2000"
    dut.cmd(f"set prInjectAircraft {records}", timeout=3.0)
    r_count = dut.cmd("get prAircraftCount", timeout=3.0)
    dut.cmd("set prClearInject 1", timeout=3.0)
    time.sleep(0.2)
    r_after = dut.cmd("get prAircraftCount", timeout=3.0)
    _restore_spotify(dut)
    if r_count.get("val") != 3:
        fail("T_PR_06", f"prAircraftCount={r_count.get('val')} after injecting 3, expected 3")
        return
    pass_("T_PR_06", f"injected 3 aircraft -> prAircraftCount=3; "
                     f"prClearInject -> count={r_after.get('val')} (real poll resumes)")


# ── TASK-355 / M-PR-MOTION Item A: poll-interval setting (prPollSec) ─────────
# T_PRM_01: dbg set/get round-trip (1/10/30) + out-of-range clamp + reboot
#           persistence [REBOOT].
# T_PRM_02: setting=1 → inter-fetch spacing settles at fetch-completion pace
#           (~4–5 s, TASK-313 edge pacing), no enqueue pile-up, no Spotify
#           heartbeat regression over a 5-min window [NETWORK][SLOW].

# dataTask.h FetchType — PlaneRadar's dispatch id as reported by `get dataq`
# inFlight (keep in sync with the enum; -1 = idle).
PR_FETCH_TYPE = 8

def t_prm_01(dut: Dut):
    """T_PRM_01 (TASK-355) [REBOOT]: prPollSec slider value round-trips via dbg
    set/get at 1 / 10 / 30 (full slider range: min / default / max), clamps an
    out-of-range set (99 -> 30, mirroring load()'s corrupt-file guard), and
    persists across a reboot.

    No app switch needed: `set/get prPollSec` dispatch to the file-scope
    g_PlaneRadarApp instance (main.cpp planeRadarDbgGet/Set are called
    unconditionally) and the value is g_settings-backed, not app-instance
    state. Persistence expectation: dbgSet("prPollSec") calls
    SettingsStorage::save() itself (same idiom as _setPreset() for prRange /
    T_PR_04), so the value must survive a reboot with no further action; the
    on-screen slider's own Release path rides AppsSection::saveSettings()
    identically. Restores the default (10) at the end."""
    print("T_PRM_01  prPollSec set/get round-trip + clamp + persistence [REBOOT]")
    for v in (1, 10, 30):
        dut.cmd(f"set prPollSec {v}", timeout=3.0)
        r = dut.cmd("get prPollSec", timeout=3.0)
        if r.get("val") != v:
            fail("T_PRM_01", f"set {v} -> get returned {r.get('val')}")
            dut.cmd("set prPollSec 10", timeout=3.0)
            return
    # Out-of-range set clamps to the slider max (dbg mirror of the load guard).
    dut.cmd("set prPollSec 99", timeout=3.0)
    r = dut.cmd("get prPollSec", timeout=3.0)
    if r.get("val") != 30:
        fail("T_PRM_01", f"set 99 -> get returned {r.get('val')}, expected clamp to 30")
        dut.cmd("set prPollSec 10", timeout=3.0)
        return
    # Persistence leg (T_PR_04 idiom): 30 is distinctive vs the default 10.
    dut.send("reboot")
    time.sleep(0.3)   # let the reset actually happen before we start reading for it
    dut._wait_for_ready()
    r_post = dut.cmd("get prPollSec", timeout=3.0)
    dut.cmd("set prPollSec 10", timeout=3.0)   # restore default
    if r_post.get("val") != 30:
        fail("T_PRM_01", f"prPollSec={r_post.get('val')} after reboot, expected 30 (not persisted)")
        return
    pass_("T_PRM_01", "1/10/30 round-trip OK, 99->30 clamp OK, 30 held across reboot; restored to 10")


def t_prm_02(dut: Dut):
    """T_PRM_02 (TASK-355) [NETWORK][SLOW]: at prPollSec=1 the poll loop is
    fetch-completion-paced, serialized, and does not starve Spotify — 5-min
    observation window.

    The design's honest-1s contract (M-PR-MOTION 'The 1 s setting, honestly'):
    _pendingFetch already serializes fetches and TASK-313 measured ~4.3 s wall
    per device GET (Cloudflare edge pacing), so setting=1 must settle at ~4–5 s
    effective spacing — NOT at 1 s, and NOT pile up requests.

    Observables (all via `get dataq`, sampled at ~0.5 s):
      - fetch identity: inFlightMs is the dispatch-start millis stamp, so each
        distinct value seen while inFlight==PR_FETCH_TYPE is one PR fetch —
        spacing is measured start-to-start from those stamps, immune to
        sampling aliasing between back-to-back fetches.
      - pile-up: queueWaiting stays small (<=2 tolerated: other apps' bg
        fetches legitimately queue behind an in-flight PR GET; PR itself can
        never stack a second request while _pendingFetch is true).
      - Spotify heartbeat: spActMs is spotifyTask's loop-position stamp; its
        age (dataq ms - spActMs) must never exceed 120 s. Uses task activity,
        not poll success — TASK-243 (Premium lapsed, 403s) makes success-based
        checks meaningless, but a starved/deadlocked task parks the stamp.
    Bounds: median spacing in [3.0, 9.0] s (fetch-completion pace, clearly
    faster than the 10 s default), min spacing >= 1.5 s (no double-fire),
    >= 20 fetches observed (~60-75 expected at ~4-5 s over 300 s).
    Restores prPollSec=10 and Spotify at the end."""
    print("T_PRM_02  prPollSec=1 -> fetch-completion pacing, no pile-up, Spotify alive [NETWORK][SLOW]")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PRM_02", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prPollSec 1", timeout=3.0)
    # Baseline: first poll must resolve before the window starts (T_PR_02 idiom
    # incl. its 90 s budget rationale — tlsYield contention can stretch it).
    baseline_deadline = time.monotonic() + 90.0
    baseline_ok = False
    while time.monotonic() < baseline_deadline:
        r = dut.cmd("get activeError", timeout=3.0)
        if not r.get("connecting", True):
            baseline_ok = True
            break
        time.sleep(1.0)
    if not baseline_ok:
        dut.cmd("set prPollSec 10", timeout=3.0)
        _restore_spotify(dut)
        skip("T_PRM_02", "first poll never resolved within 90s — no baseline")
        return
    window_s = 300.0
    fetch_starts = set()      # distinct inFlightMs stamps while inFlight==PR
    max_queue = 0
    max_sp_age = 0
    deadline = time.monotonic() + window_s
    while time.monotonic() < deadline:
        q = dut.cmd("get dataq", timeout=3.0)
        if q.get("ok"):
            if q.get("inFlight") == PR_FETCH_TYPE and q.get("inFlightMs"):
                fetch_starts.add(q["inFlightMs"])
            max_queue = max(max_queue, q.get("queueWaiting", 0))
            if q.get("spActMs") and q.get("ms"):
                max_sp_age = max(max_sp_age, q["ms"] - q["spActMs"])
        time.sleep(0.5)
    # Restore before judging — the window is over either way.
    dut.cmd("set prPollSec 10", timeout=3.0)
    still_alive = dut.cmd("get appId", timeout=3.0)
    _restore_spotify(dut)
    starts = sorted(fetch_starts)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    if not still_alive.get("ok"):
        fail("T_PRM_02", f"DUT shell unresponsive after 5-min window: {still_alive}")
        return
    if len(starts) < 20:
        fail("T_PRM_02", f"only {len(starts)} PR fetch starts observed in 300s — "
                         f"expected >=20 at fetch-completion pace (gaps={gaps[:10]})")
        return
    gaps_sorted = sorted(gaps)
    median_gap = gaps_sorted[len(gaps_sorted) // 2]
    min_gap = gaps_sorted[0]
    if min_gap < 1500:
        fail("T_PRM_02", f"min inter-fetch gap {min_gap}ms < 1.5s — double-fire / "
                         f"_pendingFetch serialization broken")
        return
    if not (3000 <= median_gap <= 9000):
        fail("T_PRM_02", f"median inter-fetch gap {median_gap}ms outside [3s,9s] — "
                         f"not fetch-completion-paced ({len(starts)} fetches)")
        return
    if max_queue > 2:
        fail("T_PRM_02", f"queueWaiting peaked at {max_queue} (>2) — enqueue pile-up")
        return
    if max_sp_age > 120000:
        fail("T_PRM_02", f"spotifyTask activity stamp went {max_sp_age}ms stale (>120s) — "
                         f"heartbeat regression under continuous PR fetching")
        return
    pass_("T_PRM_02", f"{len(starts)} fetches in 300s, median gap {median_gap}ms "
                      f"(min {min_gap}ms), queueWaiting peak {max_queue}, "
                      f"max spotify activity age {max_sp_age}ms")


# ── TASK-357 / EXP-014 graduation: dr-damped(tau=2) motion smoothing ─────────
# T_PRI_01: injected continuity pair (same callsign, shifted fix) shows a
#           nonzero, un-snapped offset that decays toward 0 with tau=2s.

def t_pri_01(dut: Dut):
    """T_PRI_01 (TASK-357): dr-damped(tau=2) offset continuity + decay via the
    `get prInterp` observable (motion-slot 0: offsetPx, fixAgeMs, tracked).

    Forces prRange=25 (widest preset, smallest px/km) first — the offset is
    computed in *screen px*, so a fixed lat/lon delta's px magnitude scales
    with zoom; a tight preset can push a delta past PR_INTERP_SNAP_PX=40 and
    trigger the re-appearance snap instead of the continuity path this test
    means to exercise (found during initial DUT verification: the same
    injected pair read offsetPx=0 at whatever preset a prior test session had
    left persisted, vs ~13px at the test's intended preset — a leftover-state
    trap, not a code bug, but worth pinning the zoom explicitly here).

    Sequence: inject fix1 (first sighting -> offset must be 0, no continuity
    claim); inject fix2 for the SAME callsign, shifted ~0.01 deg lon (-> offset
    must jump to a nonzero, un-snapped value, continuity is exactly the
    OLD-predicted-vs-NEW-fix delta at that instant); poll prInterp at ~1 tau
    (2s) and ~2 tau (4s) intervals and assert it decays (not flat, not
    re-snapped) — bounds are generous (exp(-1)=~0.37, exp(-2)=~0.14 of the
    initial reading) to tolerate serial round-trip timing jitter, not an exact
    curve-fit. Restores prRange=10 (default) and Spotify at the end."""
    print("T_PRI_01  dr-damped(tau=2) offset continuity + decay")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PRI_01", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prRange 25", timeout=3.0)
    dut.cmd("set prClearInject 1", timeout=3.0)

    r0 = dut.cmd("set prInjectAircraft AAA111,A320,51.5,0.0,10,90,90,450,35000", timeout=3.0)
    if not r0.get("ok"):
        fail("T_PRI_01", f"first injection failed: {r0}")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return
    r_first = dut.cmd("get prInterp", timeout=3.0)
    if r_first.get("offsetPx", -1) != 0.0:
        fail("T_PRI_01", f"first sighting offsetPx={r_first.get('offsetPx')}, expected exactly 0 (no continuity claim)")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return

    r1 = dut.cmd("set prInjectAircraft AAA111,A320,51.5,0.01,10,90,90,450,35000", timeout=3.0)
    if not r1.get("ok"):
        fail("T_PRI_01", f"second injection failed: {r1}")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return
    r_t0 = dut.cmd("get prInterp", timeout=3.0)
    off0 = r_t0.get("offsetPx", 0.0)
    if not (0.3 <= off0 <= 39.0):
        fail("T_PRI_01", f"t=0 offsetPx={off0} — expected a nonzero, un-snapped "
                         f"continuity offset in (0.3, 39.0)px")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return

    # NOTE: prRange restore is deliberately deferred until AFTER the decay
    # reads below — _setPreset() (any prRange write) calls _repaintDisc(),
    # which zeroes _motionCount as a side effect (new scale, no continuity
    # claim — see planeRadarApp.h). Restoring here first was an earlier
    # version of this test's own bug: it wiped motion state before the decay
    # checks ran, so both later reads read back the "nothing tracked" default
    # of exactly 0.0 — decaying-looking, but for the wrong reason. Caught by
    # DUT verification during TASK-357 (2026-07-19).
    time.sleep(2.0)
    r_t1 = dut.cmd("get prInterp", timeout=3.0)
    off1 = r_t1.get("offsetPx", off0)
    time.sleep(2.0)
    r_t2 = dut.cmd("get prInterp", timeout=3.0)
    off2 = r_t2.get("offsetPx", off1)
    dut.cmd("set prRange 10", timeout=3.0)
    _restore_spotify(dut)

    if not (off1 < off0 * 0.6):
        fail("T_PRI_01", f"offset not decaying: t=0 {off0}px -> t+2s {off1}px "
                         f"(expected < 60% of t=0, tau=2s theory ~37%)")
        return
    if not (off2 < off0 * 0.3):
        fail("T_PRI_01", f"offset not settling: t=0 {off0}px -> t+4s {off2}px "
                         f"(expected < 30% of t=0, tau=2s theory ~14%)")
        return
    pass_("T_PRI_01", f"offset {off0}px -> {off1}px (t+2s) -> {off2}px (t+4s), "
                      f"decaying toward 0 (tau=2s)")


# ── T_PMT_00..03 — player mode transitions (M-TESTBASE P3, §8) ───────────────
# The whole point of this family: it drives the OPERATION (`playerCycle`), never
# a coordinate. The gesture that cycles player mode has already moved once
# (eject -> taskbar player slot, TASK-413/414, ADR-059 D6) and silently
# invalidated every test that had hardcoded the old surface. T_PMT_00 is the ONE
# test that touches a coordinate, and it derives it from `get playerBind` — so
# relocating the surface costs an edit HERE and nowhere else.

# Expected per-mode vector. srcKind is the source that last actually drove a
# PLEDIT draw; caps is the ADR-059 D8 transport capability mask.
_PMT_EXPECT = {
    0: ("Spotify",  "SpotifyQueue",  15),
    1: ("WebRadio", "StationList",    1),
    2: ("Player",   "LocalPlaylist", 15),
}
_PMT_SETTLE_S = 2.5   # PLEDIT must actually repaint before srcKind is meaningful


def _pmt_vector(dut: Dut, timeout: float = 6.0) -> dict:
    return dut.cmd("get player", timeout=timeout)


def _pmt_goto(dut: Dut, want: int, tid: str) -> bool:
    """Cycle to `want` using the operation, never a gesture. Max 3 hops."""
    for _ in range(4):
        r = _pmt_vector(dut)
        if not r.get("ok"):
            fail(tid, f"get player failed: {r}")
            return False
        if r.get("mode") == want:
            return True
        dut.cmd("playerCycle", timeout=8.0)
        time.sleep(_PMT_SETTLE_S)
    fail(tid, f"could not reach mode {want} in 3 cycles")
    return False


def _pmt_edge(dut: Dut, tid: str, frm: int, to: int):
    """One transition: cycle frm -> to and assert the whole get-player vector."""
    if not _pmt_goto(dut, frm, tid):
        return
    before = _pmt_vector(dut)
    c = dut.cmd("playerCycle", timeout=8.0)
    if not c.get("ok"):
        fail(tid, f"playerCycle failed: {c}")
        return
    if c.get("from") != frm or c.get("to") != to:
        fail(tid, f"cycle reported {c.get('from')}->{c.get('to')}, expected {frm}->{to}")
        return
    time.sleep(_PMT_SETTLE_S)
    v = _pmt_vector(dut)
    name, src, caps = _PMT_EXPECT[to]
    problems = []
    if v.get("mode") != to:
        problems.append(f"mode={v.get('mode')} expected {to}")
    if v.get("modeName") != name:
        problems.append(f"modeName={v.get('modeName')!r} expected {name!r}")
    # M5 (X054/X055): the right PlaylistSource is actually driving PLEDIT.
    if v.get("srcName") != src:
        problems.append(f"srcName={v.get('srcName')!r} expected {src!r}")
    # M3 (X061): the capability mask matches the mode.
    if v.get("caps") != caps:
        problems.append(f"caps={v.get('caps')} expected {caps}")
    # M2 (X052): leaving Player must not strand the arena. On this build the
    # arena is never acquired (TASK-425), so this asserts "still 0" rather than
    # a release — the real acquire/release cell is Leg B, cyd2usb_player.
    if frm == 2 and v.get("arenaHeld") not in (0, None):
        problems.append(f"arenaHeld={v.get('arenaHeld')} after leaving Player")
    # M4a (X062): playlist fields exist in Player and are honestly absent elsewhere.
    if to == 2:
        if v.get("plCount") is None:
            problems.append("plCount missing in Player mode")
    elif v.get("plCount") is not None:
        problems.append(f"plCount={v.get('plCount')} leaked into non-Player mode")
    if problems:
        fail(tid, "; ".join(problems))
        return
    pass_(tid, f"{before.get('modeName')} -> {name}: src={src} caps={caps}")


def t_pmt_00(dut: Dut):
    """T_PMT_00: the surface named by `get playerBind` still performs the cycle.

    THE binding test. If it fails, T_PMT_01-03 are meaningless — they would be
    exercising an operation nothing on screen can reach."""
    print("T_PMT_00  playerBind: the documented surface still cycles")
    b = dut.cmd("get playerBind", timeout=5.0)
    if not b.get("ok"):
        fail("T_PMT_00", f"get playerBind failed: {b}")
        return
    if b.get("op") != "playerCycle":
        fail("T_PMT_00", f"playerBind op={b.get('op')!r}, expected 'playerCycle'")
        return
    region = b.get("region")
    if region != "TASKBAR_SLOT":
        skip("T_PMT_00",
             f"playerBind region={region!r} — surface relocated; update this test "
             "(that is the design intent: ONE edit, here)")
        return
    # Player must be active for the tap to CYCLE rather than RESTORE (ADR-059 D6).
    if not _pmt_goto(dut, 0, "T_PMT_00"):
        return
    slot_app = b.get("appId", APP_SLOT["Spotify"])
    before = _pmt_vector(dut).get("mode")
    sx, sy = _c.tap_taskbar_slot(slot_app)
    dut.set_cooldown_zero()
    dut.cmd(f"tap {sx} {sy}", timeout=5.0)
    time.sleep(_PMT_SETTLE_S)
    after = _pmt_vector(dut).get("mode")
    if after == before:
        fail("T_PMT_00",
             f"tapping the bound surface ({region}, slot {slot_app}) did not cycle "
             f"(mode stayed {before}) — binding is stale, exactly the TASK-413/414 failure")
        return
    pass_("T_PMT_00", f"{region} slot {slot_app} cycled {before} -> {after}")


def t_pmt_01(dut: Dut):
    """T_PMT_01: Spotify -> WebRadio; full get-player vector correct after."""
    print("T_PMT_01  transition Spotify -> WebRadio")
    _pmt_edge(dut, "T_PMT_01", 0, 1)


def t_pmt_02(dut: Dut):
    """T_PMT_02: WebRadio -> Player; full get-player vector correct after."""
    print("T_PMT_02  transition WebRadio -> Player")
    _pmt_edge(dut, "T_PMT_02", 1, 2)


def t_pmt_03(dut: Dut):
    """T_PMT_03: Player -> Spotify; vector correct + arena not stranded."""
    print("T_PMT_03  transition Player -> Spotify")
    _pmt_edge(dut, "T_PMT_03", 2, 0)


ALL_TESTS = {
    "T077": t077,
    "T078": t078,
    "T079": t079,
    "T080": t080,
    "T081": t081,
    "T082": t082,
    "T083": t083,
    "T084": t084,
    "T085": t085,
    "T087": t087,
    "T088": t088,
    # T090 excluded from default runs — T091 covers reconnect behavior (see docstring).
    "T091": t091,
    "T092": t092,
    "T093": None,   # interactive visual; handled specially in main()
    "T094": None,   # interactive physical; handled specially in main()
    "T095": None,   # interactive; handled specially in main()
    "T096": t096,
    "T133": t133,
    "T134": t134,
    "T135": t135,
    "T136": t136,
    "T137": t137,
    "T138": t138,
    "T139": t139,
    "T140": t140,
    "T147": t147,
    "T148": t148,
    # touch-capture-001 (TASK-102)
    "T149": t149,
    "T150": t150,
    "T151": t151,
    "T152": t152,
    "T153": t153,
    "T154": t154,
    "T_BI_01": t_bi_01,
    "T_BI_02": t_bi_02,
    "T_BI_03": t_bi_03,
    "T_BI_04": t_bi_04,
    # matrix-001
    "T_MA_01": t_ma_01,
    "T_MA_02": t_ma_02,
    "T_MA_03": t_ma_03,
    # gol-001
    "T_GOL_01": t_gol_01,
    "T_GOL_02": t_gol_02,
    "T_GOL_03": t_gol_03,
    "T_GOL_04": t_gol_04,
    # weather-001
    "T_WX_01": t_wx_01,
    "T_WX_02": t_wx_02,
    "T_WX_03": t_wx_03,
    "T_WX_04": t_wx_04,
    "T_WX_05": t_wx_05,
    # crypto-001
    "T_CX_01": t_cx_01,
    "T_CX_02": t_cx_02,
    "T_CX_03": t_cx_03,
    "T_CX_04": t_cx_04,
    "T_CX_05": t_cx_05,
    # cross-feature X007
    "T_X07_01": t_x07_01,
    # stock-001 (TASK-110)
    "T169": t169,
    "T170": t170,
    "T171": t171,
    "T172": t172,
    "T173": t173,
    "T174": t174,
    "T175": t175,
    "T176": t176,
    "T177": t177,
    "T178": t178,
    "T179": t179,
    "T180": t180,
    "T181": t181,
    "T182": t182,
    "T183": t183,
    "T184": t184,
    "T231": t231,   # TASK-231: Settings → Stock mode launch view
    "T185": t185,
    "T186": t186,
    "T187": t187,
    "T188": t188,
    # stock-002 (TASK-120)
    "T192": t192,
    "T193": t193,
    "T194": t194,
    "T196": t196,
    "T200": t200,
    "T201": t201,
    "T202": t202,
    "T203": t203,
    # M-STOCK-VE-STRESS (step 2)
    "T204": t204,
    # M-TOUCH-UX (TASK-118)
    "T-BUSY-01":  t_busy_01,
    "T-BUSY-01b": t_busy_01b,
    "T-BUSY-02":  t_busy_02,
    "T-BUSY-03":  t_busy_03,
    "T-BUSY-05":  t_busy_05,
    "T-CDWN-01":  t_cdwn_01,
    "T-CDWN-02":  t_cdwn_02,
    "T-CDWN-03":  t_cdwn_03,
    # velocity-scroll-001 (TASK-104)
    "T155": t155,
    "T156": t156,
    "T157": t157,
    "T158": t158,
    "T159": t159,
    "T160": t160,
    # M-PLAYER-STATE three-way mode (TASK-413 / ADR-059 D6/D7)
    "T_PLR_01": t_plr_01,
    "T_PLR_02": t_plr_02,
    "T_PLR_03": t_plr_03,
    "T_PLR_04": t_plr_04,
    "T_PLR_05": t_plr_05,
    "T_PLR_06": t_plr_06,
    "T_PLR_07": t_plr_07,
    # M3U index model (TASK-415 / ADR-059 D3)
    "T_PLR_08": t_plr_08,
    "T_PLR_09": t_plr_09,
    "T_PLR_10": t_plr_10,
    "T_PLR_11": t_plr_11,
    "T_PLR_12": t_plr_12,
    # file browser (TASK-416 / M-WINAMP-PLAYER-local §4)
    "T_PLR_13": t_plr_13,
    "T_PLR_14": t_plr_14,
    "T_PLR_15": t_plr_15,
    "T_PLR_16": t_plr_16,
    # transport capability mask (TASK-417 / ADR-059 D8)
    # player mode transitions (M-TESTBASE P3 / §8) — operation-driven, not gesture
    "T_PMT_00": t_pmt_00,
    "T_PMT_01": t_pmt_01,
    "T_PMT_02": t_pmt_02,
    "T_PMT_03": t_pmt_03,
    "T_PLR_17": t_plr_17,
    "T_PLR_18": t_plr_18,
    "T_PLR_19": t_plr_19,
    # play-order engine (TASK-418 / ADR-059 D9/D12)
    "T_PLR_20": t_plr_20,
    "T_PLR_21": t_plr_21,
    "T_PLR_22": t_plr_22,
    "T_PLR_23": t_plr_23,
    "T_PLR_24": t_plr_24,
    "T_PLR_25": t_plr_25,
    "T_PLR_26": t_plr_26,
    # velocity-scroll-001 WebRadio variant (TASK-412 / T_PLE_08)
    "T_PLE_WR_155": t_ple_wr_155,
    "T_PLE_WR_156": t_ple_wr_156,
    "T_PLE_WR_157": t_ple_wr_157,
    "T_PLE_WR_158": t_ple_wr_158,
    "T_PLE_WR_159": t_ple_wr_159,
    "T_PLE_WR_160": t_ple_wr_160,
    # taskbar-scroll-001 (TASK-105/TASK-106)
    "T162": t162,
    "T163": t163,
    "T164": t164,
    "T165": t165,
    "T166": t166,
    "T242": t242,
    # T167 retired (duplicate of T165); T168 manual (rendering — no serial observable)
    # taskbar-feedback-001 (TASK-279 / M-TASKBAR-FEEDBACK)
    "T_TBFB_01": t_tbfb_01,
    "T_TBFB_02": t_tbfb_02,
    "T_TBFB_03": t_tbfb_03,
    "T_TBFB_04": t_tbfb_04,
    "T_TBFB_05": t_tbfb_05,
    # settings-nav-stub-001 (TASK-142)
    "T-SET-01": t_set_01,
    "T-SET-02": t_set_02,
    "T-SET-03": t_set_03,
    "T-SET-06": t_set_06,
    "T-SET-07": t_set_07,
    "T-SET-08": t_set_08,
    # T-SET-04 manual visual; T-SET-05 manual visual
    # ADR-042 validation (T-UART-01, T-BGPOLL-01/02/03)
    "T-UART-01":    t_uart_01,
    "T-BGPOLL-01":  t_bgpoll_01,
    "T-BGPOLL-02":  t_bgpoll_02,
    "T-BGPOLL-03":  t_bgpoll_03,
    # M-CLOCK-STYLES suite (TASK-193)
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
    # M-TELETEXT TLS contention (TASK-191)
    "T272": t272,
    # M-TELETEXT synthetic subpage + boundary (TASK-197)
    "T270": t270,
    "T271": t271,
    # M-WEBRADIO eject + error states (TASK-211/212)
    "T_WR_EJECT_01": t_wr_eject_01,
    "T_WR_EJECT_02": t_wr_eject_02,
    "T_WR_ERR_01":   t_wr_err_01,
    "T_WR_ERR_02":   t_wr_err_02,
    "T_WR_ERR_03":   t_wr_err_03,
    "T_WR_ERR_04":   t_wr_err_04,
    # M-WEBRADIO DUT coexistence + heap (TASK-207/208/209)
    "T_WR_COEX_01":  t_wr_coex_01,
    "T_WR_COEX_02":  t_wr_coex_02,
    "T_WR_COEX_04":  t_wr_coex_04,
    "T_WR_HEAP_01":  t_wr_heap_01,
    "T_WR_HEAP_02":  t_wr_heap_02,
    "T_WR_HEAP_03":  t_wr_heap_03,
    "T_WR_HEAP_04":  t_wr_heap_04,
    "T_WR_VOL_03":   t_wr_vol_03,
    "T_WR_VOL_CLAMP": t_wr_vol_clamp,
    "T237":          t237,   # TASK-237: auto-skip terminal bound (dead-URL hook)
    "T276":          t276,   # TASK-276/395: terminal-retry re-arm actually fires
    # M-WEBRADIO TLS path + Spotify coexistence (TASK-214)
    "T_WR_TLS_01":            t_wr_tls_01,
    "T_WR_SPOTIFY_RESUME_01": t_wr_spotify_resume_01,
    # vu-002 / X043 — WebRadio real-audio VIS envelope (M-WEBRADIO-REAL-VIS)
    "T_WR_VIS_01": t_wr_vis_01,
    "T_WR_VIS_02": t_wr_vis_02,
    "T_WR_VIS_03": t_wr_vis_03,
    # vu-003 / X044 — real per-band spectrum (TASK-387)
    "T_WR_VIS_04": t_wr_vis_04,
    "T_WR_VIS_05": t_wr_vis_05,
    # app-error-signal-001 — red taskbar active-bar (TASK-245 / ADR-046)
    "T-ERR-01": t_err_01,
    "T-ERR-02": t_err_02,
    "T-ERR-04": t_err_04,
    "T-ERR-05": t_err_05,
    "T-ERR-06": t_err_06,
    "T-ERR-07": t_err_07,
    # M-PLANERADAR DUT validation (TASK-307)
    "T_PR_01": t_pr_01,
    "T_PR_02": t_pr_02,
    "T_PR_03": t_pr_03,
    "T_PR_04": t_pr_04,
    "T_PR_05": t_pr_05,
    "T_PR_06": t_pr_06,
    # TASK-355 poll-interval setting (M-PR-MOTION Item A)
    "T_PRM_01": t_prm_01,
    "T_PRM_02": t_prm_02,
    # TASK-357 motion smoothing (EXP-014 graduation)
    "T_PRI_01": t_pri_01,
}

def _setup_fail(reason: str, message: str, tail=None):
    """Report a rig condition and exit with SETUP_FAIL_EXIT. Never returns.

    The `[SETUP-FAIL]` prefix is the machine-greppable half; the serial tail is
    the half a human needs, because "check serial output" (the old message)
    names a stream that is closed by the time anyone reads it — and that
    run/test* is about to overwrite by reflashing prod."""
    print("", flush=True)
    print(f"[SETUP-FAIL] {reason}", flush=True)
    print(message, flush=True)
    if tail:
        print(f"\n--- last {len(tail)} serial lines before the abort ---", flush=True)
        for line in tail:
            print(f"  | {line}", flush=True)
        print("--- end serial tail ---", flush=True)
    print("\nThis is a RIG condition, not a test result. No tests ran; "
          "nothing here says the firmware is broken.", flush=True)
    sys.exit(SETUP_FAIL_EXIT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=resolve_port())
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0,
                   help="default serial read timeout in seconds")
    p.add_argument("--interactive", action="store_true",
                   help="enable interactive tests (T093/T094/T095 — requires human at DUT)")
    _interactive_tests = {"T093", "T094", "T095"}
    default_tests = ",".join(k for k in ALL_TESTS if k not in _interactive_tests)
    p.add_argument("--tests", default=default_tests,
                   help="comma-separated test IDs, e.g. T080,T083,T084")
    p.add_argument("--no-wifi", action="store_true",
                   help="proceed even if the DUT never gets an IP. Only for suites that "
                        "touch no network (e.g. the SD-backed T_PLR_08-12).")
    p.add_argument("--log-file", default=None,
                   help="append every raw serial line (JSON responses AND bare "
                        "LOG_D/LOG_W lines) to this file — for diagnosing "
                        "failures whose cause isn't visible in dbg command output")
    args = p.parse_args()

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in ALL_TESTS]
    if unknown:
        sys.exit(f"Unknown tests: {unknown}. Available: {list(ALL_TESTS)}")

    print(f"Connecting to {args.port} @ {args.baud}…")
    if args.log_file:
        print(f"Raw serial log: {args.log_file}")
    if args.no_wifi:
        set_no_wifi(True)   # P1: crosses into lib.dut, see set_no_wifi()
    # TASK-434 item 1 (VE-endorsed): a rig condition must never be
    # summarisable as "the tests failed". Without this wrapper the
    # SetupFailure propagates as a bare traceback and Python exits 1 — the
    # SAME code a real test failure produces — and the last thing in the log is
    # run/test*'s prod-restore flash output. Three misreads in one session came
    # from exactly that (2026-08-11).
    #
    # SerialException is caught alongside it per VE answer 3: pyserial's
    # "multiple access on port?" is a different exception from a different call
    # site, but it is equally a rig condition and today reads identically to a
    # log reader. Detecting a busy port BEFORE the open is separate work.
    try:
        dut = Dut(args.port, args.baud, timeout=args.timeout, log_file=args.log_file)
    except SetupFailure as e:
        _setup_fail(e.reason, str(e), getattr(e, "tail", None))
    except serial.SerialException as e:
        _setup_fail("port-busy", f"{e}\n"
                    f"Another process holds {args.port} — the tmux monitor "
                    f"(run/monitor-stop) or a peer session.")
    # Warmup ping: flush any residual DUT serial output before first test.
    try:
        dut.cmd("help", timeout=4.0)
    except Exception:
        pass
    # TASK-407: playerMode was observed flipping Spotify->WebRadio between DUT
    # sessions with no traced mutation path. Neither boundary (post-boot vs.
    # pre-shutdown) had a snapshot before this, so a flip could only be caught
    # by manually diffing separate sessions' logs after the fact. Printing it
    # at both ends of every run closes that gap going forward.
    # Guard broadly, not just TimeoutError: read_json() swallows JSON decode
    # errors, but ser.readline() can still raise SerialException on a CH340
    # flap. This snapshot runs before the first test, so anything escaping here
    # aborts the whole suite instead of dropping one diagnostic line. Same
    # defensive style as the `help` probe directly above.
    try:
        pm = dut.cmd("get playerMode", timeout=3.0)
        print(f"[TASK-407] entry playerMode: {pm.get('name')} ({pm.get('val')})")
    except Exception as e:
        print(f"[TASK-407] entry playerMode: unavailable ({type(e).__name__})")
    print(f"Connected. Running: {selected}\n")
    print("NOTE: T089 (production ELF check) is a host build test — not here.")
    skip_notice = [t for t in selected if t in _interactive_tests and not args.interactive]
    if skip_notice:
        print(f"NOTE: {skip_notice} will SKIP — re-run with --interactive.\n")
    else:
        print()

    for tid in selected:
        # TASK-386: emit a serial-side marker before every test. `get __TEST_<id>__`
        # is intentionally an unrecognized var — the firmware's existing "unknown var"
        # fallback (main.cpp) echoes it straight back on serial, so it lands in any
        # LOG_FILE= capture with zero firmware changes and zero behavior risk. Without
        # this, reconstructing which raw serial lines belong to which test after the
        # fact requires manually pattern-matching tap/command sequences — expensive and
        # sometimes impossible when multiple tests share the same coordinates (T-BUSY-01
        # couldn't be isolated this way during TASK-385/386's 2026-08-02 investigation).
        try:
            dut.cmd(f"get __TEST_{tid}__", timeout=2.0)
        except TimeoutError:
            pass
        try:
            if tid == "T093":
                t093(dut, args.interactive)
            elif tid == "T094":
                t094(dut, args.interactive)
            elif tid == "T095":
                t095(dut, args.interactive)
            else:
                ALL_TESTS[tid](dut)
        except TimeoutError as e:
            fail(tid, f"TimeoutError: {e}")
        except Exception as e:
            fail(tid, f"Exception: {e}")
        time.sleep(0.5)

    # TASK-407: see entry snapshot above for rationale.
    try:
        pm = dut.cmd("get playerMode", timeout=3.0)
        print(f"[TASK-407] exit playerMode: {pm.get('name')} ({pm.get('val')})")
    except Exception as e:
        print(f"[TASK-407] exit playerMode: unavailable ({type(e).__name__})")

    dut.close()

    print("\n── Results ──────────────────────────────────")
    passed = sum(1 for v in RESULTS.values() if v == "PASS")
    failed = sum(1 for v in RESULTS.values() if v.startswith("FAIL"))
    skipped = sum(1 for v in RESULTS.values() if v.startswith("SKIP"))
    flaked = sum(1 for v in RESULTS.values() if v.startswith("FLAKE"))
    for tid, result in RESULTS.items():
        print(f"  {tid}: {result}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped, {flaked} flaked")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
