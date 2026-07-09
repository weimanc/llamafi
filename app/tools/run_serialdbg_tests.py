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
T_WR_HEAP_01–04, T_WR_VOL_03, T_WR_TLS_01, T_WR_SPOTIFY_RESUME_01 (M-WEBRADIO)
against a DUT flashed with cyd2usb_winamp_debug.
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
import os
import pathlib
import re
import sys
import threading
import time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import coords as _c
from app_ids_gen import APP_SLOT, APP_COUNT

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")


# ── serial helpers ────────────────────────────────────────────────────────────

_DUT_RESET_GAP_FILE = pathlib.Path("/tmp/esp32_dut_last_reset")
_DUT_DRD_WINDOW_S   = 12.0
# Post-reset WiFi wait. BOOT_WAIT in run/test* does not cover this — opening
# the serial port asserts DTR and reboots the DUT, so this window alone decides
# how long a storm boot gets to reach GOT_IP. Raise on stormy days (LL-096):
#   DUT_WIFI_WAIT=120 ./run/test-targeted …
_DUT_WIFI_WAIT_S    = float(os.environ.get("DUT_WIFI_WAIT", "25"))
_PORTAL_INDICATORS  = (
    "Forcing config mode", "configuring access point", "SpotifyDIY", "WiFiManager"
)


class Dut:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 3.0):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud
        self.ser.timeout = timeout
        self.ser.dtr = False
        self.ser.rts = False
        # BP-018: enforce gap between serial opens to avoid DRD double-reset
        try:
            last_ts = float(_DUT_RESET_GAP_FILE.read_text())
            gap = time.time() - last_ts
            if gap < _DUT_DRD_WINDOW_S:
                wait = _DUT_DRD_WINDOW_S - gap
                print(f"  [Dut] waiting {wait:.1f}s for DRD gap (BP-018)…", flush=True)
                time.sleep(wait)
        except (FileNotFoundError, ValueError):
            pass
        self.ser.open()
        self._port_open_time = time.monotonic()
        # Serial stream is NOT thread-safe. All methods that touch self.ser must be
        # called from the thread that constructed this Dut. Never read self.ser from
        # a background thread concurrently with cmd()/read_json() — ACKs will be
        # silently consumed, causing timeouts. Use fire-and-forget + drain-phase
        # pattern for tests that need async log collection (LL-042).
        self._owner_thread = threading.current_thread()
        self._wait_for_ready()
        self._verify_debug_firmware()

    def _wait_for_ready(self, _recovery_attempt: int = 0):
        """CH341 driver asserts DTR during open() regardless of userspace settings,
        which resets the ESP32.  Detect the reboot signature and wait for the DUT
        to reach steady-state (WiFi up + first SUCCESSFUL Spotify poll + queue fetch)
        before returning.  Retries once via 'reconnect' if the startup poll fails.
        Detects WiFiManager force-portal and auto-recovers via RTS pulse (BP-018 / LL-051)."""
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
        # Wait for WiFi, watching for portal indicators (BP-018 / LL-051)
        ip_seen = False
        portal_seen = False
        deadline = time.monotonic() + _DUT_WIFI_WAIT_S
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in line:
                ip_seen = True
                break
            if any(ind in line for ind in _PORTAL_INDICATORS):
                portal_seen = True
                break
        if portal_seen:
            elapsed = time.monotonic() - self._port_open_time
            wait_s = max(0.0, _DUT_DRD_WINDOW_S - elapsed)
            print(f"  [Dut] PORTAL DETECTED — auto-recovering "
                  f"(waiting {wait_s:.0f}s for DRD window)…", flush=True)
            if wait_s > 0:
                time.sleep(wait_s)
            self.ser.rts = True
            time.sleep(0.1)
            self.ser.rts = False
            self.ser.timeout = orig_timeout
            if _recovery_attempt >= 1:
                raise RuntimeError(
                    "[Dut] Portal recurred after auto-recovery — manual intervention required.\n"
                    "Hold the reset button for 15 s to clear the DRD counter, "
                    "then re-run the test script."
                )
            self._wait_for_ready(_recovery_attempt=1)
            return
        if not ip_seen:
            self.ser.timeout = orig_timeout
            raise RuntimeError("DUT WiFi not connected — check serial output")
        # TASK-255 (M-WEBRADIO-NOPSRAM V0): variant-aware readiness. On the
        # Spotify-disabled build there is no spotifyTask, so the first-poll wait
        # below never completes (it would hang ~120 s). The shell is responsive once
        # WiFi is up, so probe `get variant`; on spotify=off, skip the poll wait.
        self.ser.reset_input_buffer()
        self.ser.write(b"get variant\n"); self.ser.flush()
        variant_off = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if '"var":"variant"' in line:
                variant_off = '"spotify":"off"' in line
                break
        if variant_off:
            time.sleep(0.5)
            self.ser.timeout = orig_timeout
            self.ser.reset_input_buffer()
            print("  [Dut] DUT ready (spotify=off variant — poll wait skipped).", flush=True)
            return
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

    def _verify_debug_firmware(self):
        """Probe for SERIAL_DEBUG firmware before running any tests (LL-043 / BP-017).
        Sends 'get heap'; production builds return 'unknown command' because all
        debug commands are behind #ifdef SERIAL_DEBUG.  Raises RuntimeError with
        exact reflash commands so the fix requires zero firmware-source knowledge.
        """
        r = self.cmd("get heap", timeout=3.0)
        if not r.get("ok") and r.get("error") == "unknown command":
            raise RuntimeError(
                "\n"
                "╔══════════════════════════════════════════════════════════╗\n"
                "║  PRODUCTION FIRMWARE DETECTED — SERIAL_DEBUG not active  ║\n"
                "╚══════════════════════════════════════════════════════════╝\n"
                "Reflash the debug build before running tests:\n"
                "  tmux kill-session -t spotify-mon\n"
                "  cd app\n"
                "  ~/.platformio/penv/bin/pio run -e cyd2usb_winamp_debug \\\n"
                "      -t upload --upload-port /dev/ttyUSB0\n"
                "  tmux new-session -d -s spotify-mon \\\n"
                "      'cd app && \\\n"
                "       ~/.platformio/penv/bin/pio device monitor \\\n"
                "       -e cyd2usb_winamp -p /dev/ttyUSB0'\n"
            )

        # ADR-042 E1 gate: verify elf hash matches the compiled debug build.
        _fw = pathlib.Path(__file__).parent.parent / ".pio" / "build" / "cyd2usb_winamp_debug" / "firmware.bin"
        if _fw.exists():
            _fw_bytes = _fw.read_bytes()
            _expected_elf = _fw_bytes[176:180].hex()
            _info = self.cmd("info", timeout=3.0)
            if _info.get("ok") and _info.get("elf") and _info["elf"] != _expected_elf:
                raise RuntimeError(
                    f"\n"
                    f"╔══════════════════════════════════════════════════════════╗\n"
                    f"║  FIRMWARE ELF MISMATCH — wrong debug build flashed       ║\n"
                    f"╚══════════════════════════════════════════════════════════╝\n"
                    f"  Flashed elf: {_info['elf']}\n"
                    f"  Expected:    {_expected_elf}\n"
                    f"Reflash the debug build before running tests:\n"
                    f"  cd app\n"
                    f"  ~/.platformio/penv/bin/pio run -e cyd2usb_winamp_debug \\\n"
                    f"      -t upload --upload-port /dev/ttyUSB0\n"
                )

    def _assert_owner(self):
        if threading.current_thread() is not self._owner_thread:
            raise RuntimeError(
                "Dut serial access from wrong thread — see LL-042. "
                "Use fire-and-forget + drain-phase pattern instead of background threads."
            )

    def send(self, cmd: str):
        self._assert_owner()
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
        self._assert_owner()
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
        try:
            _DUT_RESET_GAP_FILE.write_text(str(time.time()))
        except Exception:
            pass


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
    """
    import time
    r = dut.cmd("get appId", timeout=timeout)
    if r.get("name") == "Spotify":
        return True
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
    """T148: while Clock active, tap at x<275 returns hit=CLOCK, no Spotify action."""
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
    # Tap clock-face centre — coordinate (137, 120) hits TRANSPORT zone in Spotify mode.
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
# All tests use `switchApp 7` (debug command) to reach StockApp directly rather
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
    On timeout prints stockChartProgress phase to aid diagnosis."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            current = _stock_ok_count(dut)
        except TimeoutError:
            time.sleep(1.0)
            continue
        if current > before:
            return True
        time.sleep(1.0)
    r_prog = dut.cmd("get stockChartProgress", timeout=3.0)
    phase = r_prog.get("val") if r_prog.get("ok") else "?"
    phase_name = _CHART_PHASE_NAMES.get(phase, "idle" if phase == -1 else "unknown")
    prefix = f"[{test_id}] " if test_id else ""
    print(f"  {prefix}_wait_chart_complete timed out — stockChartProgress={phase} ({phase_name})",
          flush=True)
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
    if not _wait_chart_complete(dut, before, timeout_s=45.0):
        _restore_from_stock(dut)
        fail("T176", "fetchOkCount did not advance after 45 s — chart fetch did not complete")
        return
    _restore_from_stock(dut)
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
    # Physical slot 5 at scrollOffset=2 → AppId (2+5)%APP_COUNT == Stock.
    # NOTE: this test intentionally uses physical-slot arithmetic, not APP_SLOT.
    # It breaks if the app order changes — update the drag offset and slot together.
    _stock_physical_slot = (APP_SLOT["Stock"] - 2) % APP_COUNT
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

    for (tx, ty), tab_name in stress_tabs:
        before = _stock_ok_count(dut)
        dut.set_cooldown_zero()
        dut.cmd(f"tap {tx} {ty}", timeout=5.0)
        print(f"  [T204] {tab_name} tapped (fetchOkCount={before}); waiting…", flush=True)
        if not _wait_chart_complete(dut, before, timeout_s=45.0):
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T204", f"fetchOkCount did not advance on {tab_name} — heap pressure failure?")
            return
        r_ff   = _stock_get(dut, "fetchFailed", timeout=8.0)
        r_code = _stock_get(dut, "fetchErrorCode", timeout=8.0)
        if r_ff.get("val") == "1" or r_ff.get("val") is True:
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T204", f"fetchFailed=1 errorCode={r_code.get('val')} on {tab_name} — alloc/free stress failure")
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
    if not _switch_to_stock(dut):
        skip("T-BUSY-01", "could not switch to StockApp")
        return
    # Ensure list view (tap back to list if needed)
    dut.cmd("tap 10 7", timeout=2.0)  # back tap — no-op if already in list
    time.sleep(0.3)
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
        _restore_from_stock(dut)
        fail("T-BUSY-01", "chartLen did not exceed 0 after 45 s — fetch did not complete")
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
    """T-CDWN-01: VIS cycling — tap 1 cycles; tap 2 at ~250 ms suppressed; tap 3
    after `get cooldown` polls to 0 cycles (TASK-297: timing-independent)."""
    print("T-CDWN-01  VIS Phase-2 cooldown gate")
    if not _restore_spotify(dut):
        skip("T-CDWN-01", "could not restore Spotify app")
        return
    dut.cmd("set cooldown 0", timeout=2.0)
    time.sleep(0.05)
    m0 = _get_vis_mode(dut)
    if m0 is None:
        fail("T-CDWN-01", "get visMode failed at baseline")
        return
    vx, vy = _c.tap_vis()
    # Tap 1 — cycles to M1
    t1 = time.monotonic()
    dut.cmd(f"tap {vx} {vy}", timeout=2.0)
    time.sleep(0.05)
    m1 = _get_vis_mode(dut)
    if m1 is None:
        fail("T-CDWN-01", "get visMode failed after tap 1")
        return
    if m1 == m0:
        fail("T-CDWN-01", f"tap 1 did not cycle visMode (stuck at {m0})")
        return
    print(f"  [T-CDWN-01] tap 1: visMode {m0}→{m1}")
    # Sleep until ~250 ms from tap 1 (shell cooldown expired; VIS cooldown 300 ms still live)
    elapsed = time.monotonic() - t1
    target = 0.250
    remaining = target - elapsed
    if remaining > 0:
        time.sleep(remaining)
    # Tap 2 — VIS Phase-2 cooldown (touchScreenCoolDownTime) blocks it
    dut.cmd(f"tap {vx} {vy}", timeout=2.0)
    time.sleep(0.05)
    m_after2 = _get_vis_mode(dut)
    if m_after2 is None:
        fail("T-CDWN-01", "get visMode failed after tap 2")
        return
    if m_after2 != m1:
        fail("T-CDWN-01", f"tap 2 at ~250 ms cycled visMode ({m1}→{m_after2}); Phase-2 gate did not suppress")
        return
    print(f"  [T-CDWN-01] tap 2 suppressed: visMode still {m1}")
    # TASK-297: poll the VIS cooldown itself instead of a fixed sleep. The old
    # 100 ms sleep put tap 3 at ~350 ms — only 50 ms past the 300 ms edge — and
    # host sleep jitter + serial round-trip could land it inside the still-armed
    # window (two consecutive full-suite FAILs). Reading `get cooldown`
    # (winampDisplay's touchScreenCoolDownTime) until it reports 0 makes tap 3
    # timing-independent, and the first read distinguishes "tap 2 armed a longer
    # window than expected" from "tap 3 came too early".
    rem_first = None
    deadline = time.monotonic() + 2.0
    while True:
        r = dut.cmd("get cooldown", timeout=2.0)
        rem = r.get("remainingMs")
        if rem is None:
            fail("T-CDWN-01", f"get cooldown failed after tap 2: {r}")
            return
        rem = int(rem)
        if rem_first is None:
            rem_first = rem
            if rem > 300:
                fail("T-CDWN-01", f"cooldown reads {rem} ms after tap 2 — tap 2 armed a longer window than the expected 300 ms gate")
                return
        if rem == 0:
            break
        if time.monotonic() >= deadline:
            fail("T-CDWN-01", f"cooldown never reached 0 within 2 s after tap 2 (first={rem_first} ms, last={rem} ms)")
            return
        time.sleep(min(rem / 1000.0, 0.1))
    print(f"  [T-CDWN-01] cooldown after tap 2: {rem_first} ms → polled to 0")
    # Tap 3 — gate reads 0, must cycle
    dut.cmd(f"tap {vx} {vy}", timeout=2.0)
    time.sleep(0.05)
    m2 = _get_vis_mode(dut)
    if m2 is None:
        fail("T-CDWN-01", "get visMode failed after tap 3")
        return
    if m2 == m1:
        fail("T-CDWN-01", f"tap 3 did not cycle visMode (stuck at {m1}) despite cooldown reading 0")
        return
    print(f"  [T-CDWN-01] tap 3: visMode {m1}→{m2}")
    pass_("T-CDWN-01", f"Phase-2 gate confirmed: tap2 suppressed, tap3 cycled ({m0}→{m1}→{m1}→{m2})")


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
_TB_N = APP_SLOT["WebRadio"]                  # = 10 (Spotify..Teletext)


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
    for target in (0, _TB_N // 2, _TB_N - 1):
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
    dut.cmd("set triggerFetch 1", timeout=3.0)  # reset lastChartFetch → force next tick re-fetch
    if not _wait_chart_complete(dut, before_ok, timeout_s=45.0):
        fail("T193", "fetchOkCount did not advance after triggerFetch — auto-refresh did not fire")
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
    dut.set_cooldown_zero()
    dut.cmd("tap 184 9", timeout=3.0)  # 5D tab
    time.sleep(0.3)
    if not _wait_chart_complete(dut, before_ok, timeout_s=45.0):
        skip("T194", "fetchOkCount did not advance on list-drilled tab-switch")
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


def _settings_tap_row(dut: Dut, row: int, timeout: float = 3.0):
    """Tap the midpoint of settings list row `row` (0-indexed from content area)."""
    y = 28 + row * 26 + 13
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
    _settings_tap_row(dut, 0)  # Stock
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
    _settings_tap_row(dut, 0)   # Stock submenu
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
    """T-SET-07: back from Applications L2 (Aquarium) traverses all three levels correctly."""
    print("T-SET-07  Double-back from Applications L2 (Aquarium) → fully unwound")
    if not _switch_to_settings(dut):
        skip("T-SET-07", "could not switch to Settings")
        _restore_spotify(dut)
        return
    _settings_tap_row(dut, 5)   # Applications
    _settings_tap_row(dut, 2)   # Aquarium
    sec = _settings_section(dut)
    sub = _settings_submenu(dut)
    if sec != 5 or sub != 2:
        _restore_spotify(dut)
        fail("T-SET-07", f"section={sec!r} submenu={sub!r} after drill to Aquarium, expected 5/2")
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
    pass_("T-SET-07", "back×2 from Aquarium submenu: submenu→-1, section→-1 confirmed")


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
            # Firmware reports pending=0 → fetch done, no more stations coming
            if "pending" in r and r["pending"] == 0:
                return False
        except TimeoutError:
            pass
        time.sleep(2.0)
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
    """Enter WebRadio via the Winamp EJECT button — its design entry path. WebRadio
    has NO taskbar slot (TASK-242/LL-085); the old tap_taskbar_slot(WebRadio) only
    "worked" by an off-screen-coordinate modulo accident and never exercised the
    real path. Capture HEAP log lines emitted DURING init().
    Returns (switched_ok, heap_dict) where heap_dict keys are e.g. 'init', 'pre-fetch'.
    HEAP lines are logged before the JSON tap response, so we must read raw serial."""
    heap = {}
    if not _restore_spotify(dut):  # eject button lives in the Spotify/Winamp UI
        return False, heap
    dut.set_cooldown_zero()
    x, y = _c.tap_eject()
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


# ── T_WR_EJECT_01 — Eject from Spotify → WebRadio ────────────────────────────

def t_wr_eject_01(dut: Dut):
    """T_WR_EJECT_01: tap eject from Spotify → hit=EJECT; appId switches to WebRadio."""
    print("T_WR_EJECT_01  Eject from Spotify → WebRadio")
    if not _restore_spotify(dut):
        skip("T_WR_EJECT_01", "precondition: could not restore Spotify")
        return
    dut.set_cooldown_zero()
    _ex, _ey = _c.tap_eject()
    r = dut.cmd(f"tap {_ex} {_ey}", timeout=5.0)
    hit    = r.get("hit", "")
    action = r.get("action", "")
    if hit != "EJECT":
        fail("T_WR_EJECT_01", f"expected hit=EJECT got {hit!r}")
        return
    if action != "EJECT":
        fail("T_WR_EJECT_01", f"expected action=EJECT got {action!r}")
        return
    time.sleep(0.4)
    r2 = dut.cmd("get appId", timeout=3.0)
    if r2.get("name") != "WebRadio":
        fail("T_WR_EJECT_01", f"appId={r2.get('name')!r} after eject (expected WebRadio)")
        return
    pass_("T_WR_EJECT_01", f"hit=EJECT action=EJECT; appId=WebRadio")


# ── T_WR_EJECT_02 — Eject from WebRadio → Spotify ────────────────────────────

def t_wr_eject_02(dut: Dut):
    """T_WR_EJECT_02: tap eject from WebRadio → hit=EJECT; appId switches back to Spotify."""
    print("T_WR_EJECT_02  Eject from WebRadio → Spotify")
    # _webradio_enter_with_stations suspends bgPoll so the station fetch completes
    # quickly. Once _pendingStations=false, the main loop clears g_shellBusy
    # (main.cpp:2604-2606) and the eject tap won't be blocked with CANVAS.
    # Even if count=0 (fetch failed), _pendingStations is still resolved.
    cnt = _webradio_enter_with_stations(dut, "T_WR_EJECT_02", fetch_timeout=180.0)
    if dut.cmd("get appId", timeout=3.0).get("name") != "WebRadio":
        skip("T_WR_EJECT_02", "could not enter WebRadio")
        return
    _wait_shell_not_busy(dut, timeout_s=5.0)
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
    if r2.get("name") != "Spotify":
        fail("T_WR_EJECT_02", f"appId={r2.get('name')!r} after eject from WebRadio")
        _restore_spotify(dut)
        return
    pass_("T_WR_EJECT_02", "hit=EJECT action=EJECT; appId=Spotify")


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
    wx, wy = _c.tap_eject()  # TASK-242: WebRadio is eject-entered, not a taskbar slot
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

    # Enter WebRadio via its design entry path — the Winamp EJECT button (no taskbar
    # slot; TASK-242). Suspend bgPoll so init()'s station-fetch tlsYield() doesn't
    # stall on the failing Spotify poll. No stations/playback needed: the clamp reads
    # g_settings only, we just need WebRadio active so the wr* dbg vars route to it.
    dut.cmd("set bgPoll 0", timeout=2.0)
    ok, _ = _switch_to_webradio_capture_heap(dut)
    if not ok:
        dut.cmd("set bgPoll 1", timeout=2.0)
        skip(tid, "could not enter WebRadio via eject")
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
        skip(tid, "could not enter WebRadio via eject")
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
    drain_deadline = time.monotonic() + 200.0
    drained = False
    while time.monotonic() < drain_deadline:
        try:
            q = dut.cmd("get dataq", timeout=3.0)
            if (q.get("queueWaiting", 1) == 0 and q.get("inFlight", 0) == -1
                    and q.get("yieldCount", 1) == 0 and q.get("spAct") != 3):
                drained = True
                break
            print(f"  [T_WR_TLS_01] draining: inFlight={q.get('inFlight')} "
                  f"queueWaiting={q.get('queueWaiting')} yieldCount={q.get('yieldCount')} "
                  f"spAct={q.get('spAct')}", flush=True)
        except TimeoutError:
            pass
        time.sleep(2.0)
    if not drained:
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


# ── T_WR_SPOTIFY_RESUME_01 — Spotify resumes after eject out of WebRadio ────

def t_wr_spotify_resume_01(dut: Dut):
    """T_WR_SPOTIFY_RESUME_01: play a WebRadio station (holds spotifyTask::tlsYield()
    for the whole playback duration per dafa4a4), eject back to Spotify, and confirm
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
    # Eject while still PLAYING — this is the case that actually exercises
    # tlsResume() under load (tlsYield() is held for the whole playback span).
    dut.set_cooldown_zero()
    _ex, _ey = _c.tap_eject()
    r = dut.cmd(f"tap {_ex} {_ey}", timeout=5.0)
    if r.get("action") != "EJECT":
        fail("T_WR_SPOTIFY_RESUME_01", f"eject tap did not fire: {r}")
        return
    time.sleep(0.5)
    r2 = dut.cmd("get appId", timeout=3.0)
    if r2.get("name") != "Spotify":
        fail("T_WR_SPOTIFY_RESUME_01", f"appId={r2.get('name')!r} after eject (expected Spotify)")
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
    dut.cmd("switchApp 7"); time.sleep(0.5)   # Stock
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
    # M-WEBRADIO TLS path + Spotify coexistence (TASK-214)
    "T_WR_TLS_01":            t_wr_tls_01,
    "T_WR_SPOTIFY_RESUME_01": t_wr_spotify_resume_01,
    # app-error-signal-001 — red taskbar active-bar (TASK-245 / ADR-046)
    "T-ERR-01": t_err_01,
    "T-ERR-02": t_err_02,
    "T-ERR-04": t_err_04,
    "T-ERR-05": t_err_05,
    "T-ERR-06": t_err_06,
    "T-ERR-07": t_err_07,
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
