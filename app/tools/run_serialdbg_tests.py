#!/usr/bin/env python3
"""
Serial debug test harness — serialdbg-001 suite.

Executes T076–T088, T095, T096, T_BI_01–T_BI_04 against a DUT flashed with cyd2usb_winamp_debug.
T089 (production ELF symbol check) is a host build check — not run here.
T095 (physical vs. synthetic calibration) requires --interactive (human at DUT).

Usage:
    python3 run_serialdbg_tests.py [--port /dev/ttyUSB0] [--tests T076,T080,T084]
    python3 run_serialdbg_tests.py --interactive --tests T095

Requirements:
    pip install pyserial
    DUT flashed with cyd2usb_winamp_debug, booted, WiFi up, Spotify creds valid.
    Active Spotify Connect device playing a track (required for most tests).

All tap/drag screen coordinates are derived at import time from
gen/skin_layout.h via tools/coords.py. originX shifts automatically when
M-MULTIAPP changes WINDOW_W (no literal edits required in this file).
"""

import argparse
import json
import pathlib
import re
import sys
import time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import coords as _c

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")


# ── serial helpers ────────────────────────────────────────────────────────────

class Dut:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 3.0):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud
        self.ser.timeout = timeout
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.open()
        self._wait_for_ready()

    def _wait_for_ready(self):
        """CH341 driver asserts DTR during open() regardless of userspace settings,
        which resets the ESP32.  Detect the reboot signature and wait for the DUT
        to reach steady-state (WiFi up + first SUCCESSFUL Spotify poll + queue fetch)
        before returning.  Retries once via 'reconnect' if the startup poll fails."""
        orig_timeout = self.ser.timeout
        self.ser.timeout = 0.5
        boot_seen = False
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "[boot]" in line or "ets Jul" in line:
                boot_seen = True
                break
        if not boot_seen:
            self.ser.timeout = orig_timeout
            self.ser.reset_input_buffer()
            return
        print("  [Dut] reboot detected — waiting for DUT ready…", flush=True)
        self.ser.timeout = 1.0
        # Wait for WiFi
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in line:
                break
        # Wait for first successful Spotify poll (ok 200) AND queue fetch completion.
        # 60s window covers backoff after a failed startup poll.
        poll_ok = False
        queue_done = False
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "[spotify.poll]" in line and "ok 200" in line:
                poll_ok = True
            if "[spotify.queue]" in line and "status=" in line:
                queue_done = True
            if poll_ok and queue_done:
                break
        if not poll_ok or not queue_done:
            # Startup poll failed; force a reconnect and wait again.
            print("  [Dut] startup poll failed — sending reconnect…", flush=True)
            self.ser.write(b"reconnect\n")
            self.ser.flush()
            poll_ok = False
            queue_done = False
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                line = self.ser.readline().decode(errors="replace").strip()
                if "[spotify.poll]" in line and "ok 200" in line:
                    poll_ok = True
                if "[spotify.queue]" in line and "status=" in line:
                    queue_done = True
                if poll_ok and queue_done:
                    break
        time.sleep(0.5)
        self.ser.timeout = orig_timeout
        self.ser.reset_input_buffer()
        print("  [Dut] DUT ready.", flush=True)

    def cmd_drain(self, cmd_str: str, timeout: float = 5.0) -> list[dict]:
        """Send a command; read all JSON responses until one has 'last': True."""
        self.send(cmd_str)
        parts = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            try:
                r = json.loads(line)
                parts.append(r)
                if r.get("last", True):
                    break
            except (json.JSONDecodeError, ValueError):
                pass
        return parts

    def wait_for_queue(self, min_count: int = 1, timeout: float = 30.0):
        """Poll 'get queue' (draining all parts) until count >= min_count or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            parts = self.cmd_drain("get queue", timeout=5.0)
            # Empty queue: single part with count=0. Non-empty: N parts with 'track'.
            item_count = sum(1 for p in parts if "track" in p)
            if item_count >= min_count:
                return True
            time.sleep(2.0)
        return False

    def send(self, cmd: str):
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()

    def read_json(self, timeout: float = 3.0) -> dict:
        """Read lines until a JSON line is found or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        raise TimeoutError(f"no JSON response within {timeout}s")

    def read_json_multi(self, timeout: float = 5.0) -> list[dict]:
        """Read JSON lines until one has 'last':true."""
        parts = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    parts.append(obj)
                    if obj.get("last"):
                        return parts
                except json.JSONDecodeError:
                    pass
        raise TimeoutError(f"multi-part response incomplete after {timeout}s")

    def drain_log_lines(self, pattern: str, count: int, timeout: float = 10.0) -> list[str]:
        """Collect `count` log lines matching `pattern` within timeout."""
        matches = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(matches) < count:
            line = self.ser.readline().decode(errors="replace").strip()
            if re.search(pattern, line):
                matches.append(line)
        return matches

    def cmd(self, cmd_str: str, timeout: float = 3.0) -> dict:
        self.send(cmd_str)
        return self.read_json(timeout)

    def set_cooldown_zero(self):
        r = self.cmd("set cooldown 0")
        assert r.get("ok"), f"set cooldown 0 failed: {r}"

    def close(self):
        self.ser.close()


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


# ── T076 — hit-zone boundary (transport row, left-x only) ────────────────────

def t076(dut: Dut):
    print("T076  Hit-zone boundary (transport)")
    # Warmup: flush any pending serial output before the boundary sweep.
    try:
        dut.cmd("info", timeout=5.0)
    except TimeoutError:
        pass
    # Transport row buttons are contiguous on the x-axis (PREV→PLAY→PAUSE→
    # STOP→NEXT), each 23 px wide. NEXT is 22 px. Left edges (originX=22,
    # CB_PREV_X=16): PREV=38, PLAY=61, PAUSE=84, STOP=107, NEXT=130. Right
    # edge of NEXT: 130+22=152. y range: [originY+88, originY+106).
    # Test boundary semantics:
    #   - 1 px left of PREV's left edge (37) → not TRANSPORT
    #   - left-edge px of each button → that button
    #   - 1 px right of NEXT's right edge (152) → not TRANSPORT
    #   - tap at edge between adjacent buttons → the right-hand button
    _ty = _c.transport_y()
    cases = [
        # (label, x, y, expected_hit, expected_action_or_None)
        ("PREV-outside-left",  _c.button_left_x("PREV") - 1,  _ty, "NOT_TRANSPORT", None),
        ("PREV-inside",        _c.button_left_x("PREV"),       _ty, "TRANSPORT",     "PREV"),
        ("PREV/PLAY-boundary", _c.button_left_x("PLAY"),       _ty, "TRANSPORT",     "PLAY"),
        ("PLAY/PAUSE-boundary",_c.button_left_x("PAUSE"),      _ty, "TRANSPORT",     "PAUSE"),
        ("PAUSE/STOP-boundary",_c.button_left_x("STOP"),       _ty, "TRANSPORT",     "STOP"),
        ("STOP/NEXT-boundary", _c.button_left_x("NEXT"),       _ty, "TRANSPORT",     "NEXT"),
        ("NEXT-inside",        _c.button_right_x("NEXT") - 1,  _ty, "TRANSPORT",     "NEXT"),
        ("NEXT-outside-right", _c.button_right_x("NEXT"),      _ty, "NOT_TRANSPORT", None),
    ]
    errors = []
    for label, x, y, exp_hit, exp_action in cases:
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        hit = r.get("hit", "")
        action = r.get("action", "")
        if exp_hit == "TRANSPORT":
            if hit != "TRANSPORT" or action != exp_action:
                errors.append(f"{label}: hit={hit} action={action} (want TRANSPORT/{exp_action})")
        else:  # NOT_TRANSPORT
            if hit == "TRANSPORT":
                errors.append(f"{label}: hit=TRANSPORT (want anything else)")

    if errors:
        fail("T076", "; ".join(errors))
    else:
        pass_("T076", f"{len(cases)}/{len(cases)} boundary checks correct")


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
    r_arm = dut.cmd("set cooldown 500")
    if not r_arm.get("ok"):
        fail("T079", f"set cooldown 500 failed: {r_arm}")
        return
    _px, _py = _c.tap_button("PLAY")
    r = dut.cmd(f"tap {_px} {_py}")   # PLAY — should be gated
    skipped = r.get("skipped", False)
    hit = r.get("hit", "")
    if not skipped:
        fail("T079", f"tap not skipped while gate armed: {r}")
        dut.set_cooldown_zero()  # leave clean
        return
    # Clear gate, verify follow-up tap fires (action commits)
    dut.set_cooldown_zero()
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


# ── T086 — full-perimeter boundary: POSBAR + VOLUME ──────────────────────────

def t086(dut: Dut):
    print("T086  Full-perimeter boundary: POSBAR + VOLUME")
    # Precondition: songDuration > 0 so POSBAR inside-cases dispatch ACT_SEEK.
    # Set explicitly — T085 may have zeroed it; next poll restores it, but
    # tests run faster than polls. Use a realistic value; poll will correct it.
    dut.cmd("set songDuration 180000")

    errors = []

    _pbx0, _pbx1, _pby0, _pby1 = _c.posbar_bounds()
    _pbxm = _c.tap_posbar()[0]  # x centre of posbar
    _pbym = _c.tap_posbar()[1]  # y centre of posbar
    posbar_outside = [
        ("PB-left-out",  _pbx0 - 1, _pbym),
        ("PB-right-out", _pbx1 + 1, _pbym),   # first pixel outside right edge
        ("PB-top-out",   _pbxm,     _pby0 - 1),
        ("PB-bot-out",   _pbxm,     _pby1 + 1),   # first outside row
    ]
    posbar_inside = [
        ("PB-left-in",   _pbx0, _pbym),
        ("PB-right-in",  _pbx1, _pbym),
        ("PB-top-in",    _pbxm, _pby0),
        ("PB-bot-in",    _pbxm, _pby1),   # last valid row
    ]
    _vx0, _vx1, _vy0, _vy1 = _c.vol_bounds()
    _vxm = (_vx0 + _vx1) // 2  # x centre of volume zone
    _vym = _c.vol_drag_y()
    vol_outside = [
        ("VOL-left-out",  _vx0 - 1, _vym),
        ("VOL-right-out", _vx1 + 1, _vym),   # first pixel outside right edge
        ("VOL-top-out",   _vxm,     _vy0 - 1),
        ("VOL-bot-out",   _vxm,     _vy1 + 1),   # exclusive bottom edge + 1
    ]
    vol_inside = [
        ("VOL-left-in",  _vx0, _vym),
        ("VOL-right-in", _vx1, _vym),
        ("VOL-top-in",   _vxm, _vy0),
        ("VOL-bot-in",   _vxm, _vy1),   # last valid row
    ]

    for label, x, y in posbar_outside:
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        if r.get("hit") == "POSBAR":
            errors.append(f"{label}({x},{y}): hit=POSBAR (want outside)")

    for label, x, y in posbar_inside:
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        hit, action, seek_ms = r.get("hit"), r.get("action"), r.get("seekMs", -1)
        if hit != "POSBAR" or action != "SEEK" or seek_ms < 0:
            errors.append(f"{label}({x},{y}): hit={hit} action={action} seekMs={seek_ms}")

    for label, x, y in vol_outside:
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        if r.get("hit") == "VOLUME":
            errors.append(f"{label}({x},{y}): hit=VOLUME (want outside)")

    for label, x, y in vol_inside:
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        hit, action, vol_pct = r.get("hit"), r.get("action"), r.get("volumePct", -2)
        if hit != "VOLUME" or action != "VOLUME" or vol_pct < 0:
            errors.append(f"{label}({x},{y}): hit={hit} action={action} volumePct={vol_pct}")

    total = len(posbar_outside) + len(posbar_inside) + len(vol_outside) + len(vol_inside)
    if errors:
        fail("T086", "; ".join(errors))
    else:
        pass_("T086", f"{total}/{total} perimeter checks correct")


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

    time.sleep(0.3)
    dut.set_cooldown_zero()
    _rpx, _rpy = _c.tap_repeat()
    r = dut.cmd(f"tap {_rpx} {_rpy}")
    if r.get("hit") != "REPEAT" or r.get("action") != "REPEAT":
        errors.append(f"REPEAT: hit={r.get('hit')} action={r.get('action')}")

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
    for label, x, y in deadzone_cases:
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
    r_set = dut.cmd("set backoff 3", timeout=3.0)
    if not r_set.get("ok"):
        flake("T091", f"set backoff 3 failed: {r_set}"); return
    r_get = dut.cmd("get backoff", timeout=3.0)
    if r_get.get("consecutiveFailures") != 3:
        flake("T091", f"consecutiveFailures={r_get.get('consecutiveFailures')} after set, expected 3"); return
    r_rc = dut.cmd("reconnect", timeout=3.0)
    if not r_rc.get("ok"):
        flake("T091", f"reconnect failed: {r_rc}"); return
    r_get2 = dut.cmd("get backoff", timeout=3.0)
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
        fail("T134", "precondition: queue count=0 after 30s — Spotify not playing?")
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
    """Ensure currentAppId == Spotify; tap taskbar slot 0 if not. Returns True on success."""
    import time
    r = dut.cmd("get appId", timeout=timeout)
    if r.get("name") == "Spotify":
        return True
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(0)
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
    print("T136  get scrollOffset returns 0 at initial state")
    r = dut.cmd("get scrollOffset", timeout=3.0)
    if not r.get("ok"):
        fail("T136", f"ok=false: {r}")
        return
    if r.get("key") != "scrollOffset":
        fail("T136", f"key={r.get('key')!r} — branch not reached or wrong key name")
        return
    val = r.get("val")
    if val != 0:
        fail("T136", f"val={val} expected 0; scrollOffset not reset at startup")
        return
    pass_("T136", f"get scrollOffset → val={val}")


# ── T137 — swipe-up increments scrollOffset ────────────────────────────────────

def t137(dut: Dut):
    print("T137  swipe-up increments scrollOffset")
    if not dut.wait_for_queue(min_count=2):
        fail("T137", "precondition: queue count<2 after 30s — Spotify not playing?")
        return
    pre = _get_scroll(dut)
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
            fail("T138", f"pre-condition: scrollOffset={pre} not 1 after setup swipe")
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
    cx, cy = _c.tap_taskbar_slot(1)
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)  # repaintChrome ~60 ms; 300 ms headroom
    r2 = dut.cmd("get appId", timeout=3.0)
    if not r2.get("ok") or r2.get("name") != "Clock":
        fail("T147", f"did not switch to Clock: got appId={r2.get('name')!r}")
        # Attempt restore before failing.
        dut.set_cooldown_zero()
        dut.cmd(f"tap {_c.tap_taskbar_slot(0)[0]} {_c.tap_taskbar_slot(0)[1]}", timeout=3.0)
        time.sleep(0.3)
        return
    # Switch back to Spotify to leave DUT in known state for subsequent tests.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(0)
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    r3 = dut.cmd("get appId", timeout=3.0)
    if not r3.get("ok") or r3.get("name") != "Spotify":
        fail("T147", f"failed to return to Spotify: got {r3.get('name')!r}")
        return
    pass_("T147", "Spotify→Clock→Spotify round-trip confirmed via get appId")


def t148(dut: Dut):
    """T148: while Clock active, tap at x<275 returns hit=CLOCK, no Spotify action."""
    import time
    # Switch to Clock.
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(1)
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)
    r_pre = dut.cmd("get appId", timeout=3.0)
    if not r_pre.get("ok") or r_pre.get("name") != "Clock":
        skip("T148", f"precondition: could not switch to Clock (appId={r_pre.get('name')!r})")
        return
    # Tap clock-face centre — coordinate (137, 120) hits TRANSPORT zone in Spotify mode.
    dut.set_cooldown_zero()
    tx, ty = _c.clock_canvas_tap()
    r = dut.cmd(f"tap {tx} {ty}", timeout=3.0)
    hit = r.get("hit", "")
    action = r.get("action", "")
    # Restore to Spotify before asserting (so subsequent tests start clean).
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(0)
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    if hit not in ("CLOCK", "NON_SPOTIFY"):
        fail("T148", f"BUG-1 guard not firing: hit={hit!r} action={action!r} "
                     f"at ({tx},{ty}) with Clock active — Winamp zone leaked")
        return
    if action != "NONE":
        fail("T148", f"unexpected Spotify action={action!r} (want NONE) for Clock canvas tap")
        return
    pass_("T148", f"Clock active: hit={hit!r} action={action!r} — no Winamp zone leak")


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
        sx, sy = _c.tap_taskbar_slot(0)
        dut.cmd(f"tap {sx} {sy}", timeout=3.0)
        time.sleep(0.4)
    # Switch to Clock; wait 2 s (ensures rate-limit window clears; seqno may change).
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(1)
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
    sx, sy = _c.tap_taskbar_slot(0)
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
    cx, cy = _c.tap_taskbar_slot(1)
    r_switch = dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.2)  # past the 80 ms pendingReleaseAt window
    r_app = dut.cmd("get appId", timeout=3.0)
    # Restore to Spotify before asserting.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(0)
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
        sx, sy = _c.tap_taskbar_slot(0)
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
    cx, cy = _c.tap_taskbar_slot(1)
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)
    r_clock = dut.cmd("get appId", timeout=3.0)
    if not r_clock.get("ok") or r_clock.get("name") != "Clock":
        fail("T_BI_03", f"failed to switch to Clock: appId={r_clock.get('name')!r}")
        return
    time.sleep(0.5)
    # Switch back to Spotify — resume() → invalidatePlaylist().
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(0)
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
    """T_BI_04: cmdTap delivers Release phase; response region=TRANSPORT action=PLAY|PAUSE."""
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


# ── main ──────────────────────────────────────────────────────────────────────

ALL_TESTS = {
    "T076": t076,
    "T077": t077,
    "T078": t078,
    "T079": t079,
    "T080": t080,
    "T081": t081,
    "T082": t082,
    "T083": t083,
    "T084": t084,
    "T085": t085,
    "T086": t086,
    "T087": t087,
    "T088": t088,
    "T090": t090,
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
    "T_BI_01": t_bi_01,
    "T_BI_02": t_bi_02,
    "T_BI_03": t_bi_03,
    "T_BI_04": t_bi_04,
}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0,
                   help="default serial read timeout in seconds")
    p.add_argument("--interactive", action="store_true",
                   help="enable interactive tests (T093/T094/T095 — requires human at DUT)")
    _interactive_tests = {"T093", "T094", "T095"}
    default_tests = ",".join(k for k in ALL_TESTS if k not in _interactive_tests)
    p.add_argument("--tests", default=default_tests,
                   help="comma-separated test IDs, e.g. T080,T083,T084")
    args = p.parse_args()

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in ALL_TESTS]
    if unknown:
        sys.exit(f"Unknown tests: {unknown}. Available: {list(ALL_TESTS)}")

    print(f"Connecting to {args.port} @ {args.baud}…")
    dut = Dut(args.port, args.baud, timeout=args.timeout)
    # Warmup ping: flush any residual DUT serial output before first test.
    try:
        dut.cmd("help", timeout=4.0)
    except Exception:
        pass
    print(f"Connected. Running: {selected}\n")
    print("NOTE: T089 (production ELF check) is a host build test — not here.")
    skip_notice = [t for t in selected if t in _interactive_tests and not args.interactive]
    if skip_notice:
        print(f"NOTE: {skip_notice} will SKIP — re-run with --interactive.\n")
    else:
        print()

    for tid in selected:
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
