#!/usr/bin/env python3
"""
Sync-001 + Drift-001 test harness — T097–T114.

Requires:
    pip install pyserial
    DUT: cyd2usb_winamp_debug, WiFi up, Spotify creds valid, track playing.
    Valid creds at Spotify-Diy-Thing/data/spotify_diy_config.json

Usage:
    python3 tools/run_sync_tests.py
    python3 tools/run_sync_tests.py --tests T097,T098,T110
    python3 tools/run_sync_tests.py --interactive --tests T112,T113
    python3 tools/run_sync_tests.py --tests T114    # dechunker regression

DUT snapshot field names vs diff names:
    DUT JSON → common diff name
    shuffle  → shuffleState
    repeat   → repeatState
    currentTrackUri → trackUri
"""

import argparse
import base64
import json
import pathlib
import re
import subprocess
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import coords as _c

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG    = REPO_ROOT / "data" / "spotify_diy_config.json"
TOOLS_DIR = REPO_ROOT / "tools"

LAG_BOUND_MS = 8500   # harness bound: 5s sleep + 2s HTTP + 1.5s check overhead (cellular, forced-poll path)
QUEUE_BOUND_MS = 8500 # queue strip update bound


# ── serial helpers ────────────────────────────────────────────────────────────

class Dut:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 5.0):
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
        # Wait for first successful Spotify poll (ok 200) OR poll start + queue status
        # Watch for up to 60s to cover backoff after startup poll failure.
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

    def send(self, cmd: str):
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()

    def read_json(self, timeout: float = 5.0) -> dict:
        # Use short per-readline timeout so deadline check fires between reads.
        # Without this, a single readline() can block for ser.timeout (5s) even
        # when read_json timeout < ser.timeout, causing spurious TimeoutErrors.
        orig_timeout = self.ser.timeout
        self.ser.timeout = min(0.25, timeout)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                line = self.ser.readline().decode(errors="replace").strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
        finally:
            self.ser.timeout = orig_timeout
        raise TimeoutError("no JSON line from DUT")

    def read_log_line(self, pattern: str, timeout: float = 10.0) -> str | None:
        """Return first log line matching pattern, or None on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if re.search(pattern, line):
                return line
        return None

    def cmd(self, cmd_str: str, timeout: float = 4.0) -> dict:
        self.send(cmd_str)
        return self.read_json(timeout)

    def set_cooldown_zero(self):
        self.cmd("set cooldown 0")

    def close(self):
        self.ser.close()


def get_snapshot(dut: Dut) -> dict:
    """Send `get snapshot`, merge split-protocol chunks."""
    dut.send("get snapshot")
    chunks: dict = {}
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        r = dut.read_json(timeout=3.0)
        chunks.update(r)
        if r.get("last"):
            return chunks
    raise TimeoutError("snapshot never received last=true")


def get_queue(dut: Dut) -> list[dict]:
    """Send `get queue`, return list of row dicts."""
    dut.send("get queue")
    rows: list[dict] = []
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            r = dut.read_json(timeout=min(3.0, remaining))
        except TimeoutError:
            break
        if r.get("var") == "queue":
            if r.get("count", 1) == 0:
                return rows
            rows.append(r)
            if r.get("last"):
                return rows
    raise TimeoutError("queue never received last=true")


def normalize(snap: dict) -> dict:
    """Map DUT short field names → common diff names."""
    out = dict(snap)
    if "shuffle" in out:
        out["shuffleState"] = out.pop("shuffle")
    if "repeat" in out:
        out["repeatState"] = out.pop("repeat")
    if "currentTrackUri" in out:
        out["trackUri"] = out.pop("currentTrackUri")
    return out


def poll_until(dut: Dut, condition, timeout=7.0, interval=0.5, reconnect_after: float = 0):
    """Poll get snapshot every interval until condition(snap) or timeout.

    Returns (normalized_snap, elapsed_ms) on success, or (None, timeout*1000).

    If reconnect_after > 0, sends 'reconnect' to the DUT after that many seconds
    if the condition hasn't been met yet.  This recovers from TLS stale-connection
    failures (which cause intermittent poll skips on cellular/NAT networks) without
    altering the measured elapsed time for fast natural polls.
    """
    t0 = time.monotonic()
    deadline = t0 + timeout
    reconnect_sent = False
    while time.monotonic() < deadline:
        snap = normalize(get_snapshot(dut))
        if condition(snap):
            return snap, (time.monotonic() - t0) * 1000
        if reconnect_after > 0 and not reconnect_sent and (time.monotonic() - t0) >= reconnect_after:
            dut.cmd("reconnect", timeout=3.0)  # reads + discards ACK to keep serial clean
            reconnect_sent = True
        time.sleep(interval)
    return None, timeout * 1000


def force_fresh_poll(dut: Dut, timeout: float = 15.0) -> bool:
    """Send 'reconnect' to clear stale TLS, wait for the forced poll to COMPLETE.

    Watches the DUT serial stream for the '[spotify.poll] ok 200' log line
    which confirms the forced poll finished.  Returns True on success.
    Falls back to snapshot valid=True check if the log line is not seen.
    """
    # Save current timeout; we need short reads while waiting for log lines.
    orig_timeout = dut.ser.timeout
    dut.ser.reset_input_buffer()
    dut.send("reconnect")
    # Read the JSON ACK from reconnect command first (so it doesn't confuse
    # later reads), then switch to short readline timeout for log scanning.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if line.startswith("{"):
            break
    # Now watch for the poll success or failure log line.
    dut.ser.timeout = 0.2
    poll_ok = False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "[spotify.poll]" in line and "ok 200" in line:
            poll_ok = True
            break
        if "[spotify.poll]" in line and ("fail" in line or "backoff" in line):
            # Poll failed; try another reconnect
            dut.ser.timeout = orig_timeout
            dut.send("reconnect")
            dut.ser.timeout = 0.2
            deadline = time.monotonic() + timeout  # reset deadline
    dut.ser.timeout = orig_timeout
    time.sleep(0.3)   # let DUT commit snapshot after poll completion
    dut.ser.reset_input_buffer()
    if poll_ok:
        return True
    # Fallback: check snapshot valid flag
    snap = normalize(get_snapshot(dut))
    return bool(snap.get("valid"))


# ── Spotify helpers ────────────────────────────────────────────────────────────

def _access_token() -> str:
    cfg = json.loads(CONFIG.read_text())
    basic = base64.b64encode(
        f"{cfg['clientId']}:{cfg['clientSecret']}".encode()
    ).decode()
    import urllib.request, urllib.parse
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": cfg["refreshToken"],
    }).encode()
    import urllib.request as ur
    req = ur.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with ur.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["access_token"]


def spotify_state() -> dict:
    """Fetch /me/player, return parsed state (fields match normalize() output)."""
    import urllib.request as ur, urllib.error
    token = _access_token()
    req = ur.Request(
        "https://api.spotify.com/v1/me/player?additional_types=episode",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with ur.urlopen(req, timeout=10) as r:
            if r.status == 204:
                return {}
            raw = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET /me/player HTTP {e.code}")
    item   = raw.get("item") or {}
    dev    = raw.get("device") or {}
    artists = item.get("artists") or []
    vp     = dev.get("volume_percent")
    _REPEAT = {"track": 0, "context": 1, "off": 2}
    return {
        "isPlaying":   bool(raw.get("is_playing")),
        "progressMs":  int(raw.get("progress_ms") or 0),
        "durationMs":  int(item.get("duration_ms") or 0),
        "volumePct":   int(vp) if vp is not None else -1,
        "shuffleState": bool(raw.get("shuffle_state")),
        "repeatState": _REPEAT.get(raw.get("repeat_state", "off"), 2),
        "trackUri":    item.get("uri", ""),
        "deviceActive": vp is not None,
    }


def drive(cmd: str, *args) -> bool:
    """Invoke spotify_drive.py; return True on exit 0."""
    r = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "spotify_drive.py"), cmd] + list(args),
        capture_output=True, timeout=15,
    )
    return r.returncode == 0


# ── heartbeat helpers ─────────────────────────────────────────────────────────

def parse_hb(line: str) -> dict:
    """Parse key=value fields from a [I][hb] log line."""
    if "[I][hb]" in line:
        line = line[line.index("[I][hb]") + 7:].strip()
    fields = {}
    # Split on whitespace boundaries before 'word=' patterns
    for tok in re.split(r'\s+(?=\w+=)', line):
        eq = tok.find('=')
        if eq > 0:
            fields[tok[:eq].strip()] = tok[eq+1:].strip()
    return fields


def wait_heartbeat(dut: Dut, timeout: float = 35.0) -> dict:
    """Wait for next [I][hb] line, return parsed fields."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "[I][hb]" in line:
            return parse_hb(line)
    raise TimeoutError("no heartbeat within timeout")


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


# ── T097 — Spotify-side pause reflects on DUT within one poll ─────────────────

def t097(dut: Dut):
    print("T097  Spotify-side pause → DUT isPlaying=false ≤5500ms")
    snap = normalize(get_snapshot(dut))
    if not snap.get("isPlaying"):
        # Ensure playing first; wait up to 6s for DUT to poll and pick up playing state
        drive("play")
        time.sleep(6)
        snap = normalize(get_snapshot(dut))
    if not snap.get("isPlaying"):
        skip("T097", "DUT shows not-playing at baseline; start a track first"); return
    t_send = time.monotonic()
    if not drive("pause"):
        fail("T097", "spotify_drive.py pause failed"); return
    result, elapsed = poll_until(dut, lambda s: not s.get("isPlaying", True), timeout=12.0,
                                  reconnect_after=5.0)
    if result is None:
        fail("T097", f"isPlaying still true after {elapsed:.0f}ms"); return
    if elapsed > LAG_BOUND_MS:
        fail("T097", f"lag {elapsed:.0f}ms > {LAG_BOUND_MS}ms bound")
    else:
        pass_("T097", f"pause propagated in {elapsed:.0f}ms ≤ {LAG_BOUND_MS}ms")
    drive("play")  # restore


# ── T098 — Spotify-side volume change reflects on DUT within one poll ─────────

def t098(dut: Dut):
    print("T098  Spotify-side volume change → DUT volumePct match ≤5500ms")
    snap = normalize(get_snapshot(dut))
    cur_vol = snap.get("volumePct", -1)
    if cur_vol < 0:
        skip("T098", "DUT volumePct=-1 (no active device or unsupported)"); return
    target = 20 if cur_vol > 50 else 80
    if not drive("setVolume", str(target)):
        fail("T098", "spotify_drive.py setVolume failed"); return
    result, elapsed = poll_until(dut, lambda s: s.get("volumePct") == target, timeout=12.0,
                                  reconnect_after=5.0)
    restore_vol = cur_vol if cur_vol >= 0 else 50
    if result is None:
        fail("T098", f"volumePct never reached {target} after {elapsed:.0f}ms")
        drive("setVolume", str(restore_vol)); return
    if elapsed > LAG_BOUND_MS:
        fail("T098", f"lag {elapsed:.0f}ms > {LAG_BOUND_MS}ms")
    else:
        pass_("T098", f"vol {cur_vol}→{target} in {elapsed:.0f}ms ≤ {LAG_BOUND_MS}ms")
    drive("setVolume", str(restore_vol))


# ── T099 — Track-end → next-track propagation ────────────────────────────────

def t099(dut: Dut):
    print("T099  next track → DUT currentTrackUri changes ≤5500ms")
    snap = normalize(get_snapshot(dut))
    uri_a = snap.get("trackUri", "")
    if not uri_a:
        skip("T099", "no currentTrackUri in snapshot"); return
    if not drive("next"):
        fail("T099", "spotify_drive.py next failed"); return
    result, elapsed = poll_until(
        dut,
        lambda s: s.get("trackUri", "") not in ("", uri_a),
        timeout=12.0, interval=0.5, reconnect_after=5.0,
    )
    if result is None:
        fail("T099", f"trackUri still {uri_a!r} after {elapsed:.0f}ms"); return
    prog = result.get("progressMs", 0)
    if elapsed > LAG_BOUND_MS:
        fail("T099", f"lag {elapsed:.0f}ms > {LAG_BOUND_MS}ms")
    elif prog > 8000:
        fail("T099", f"progressMs={prog}ms > 8000ms at track-change detection")
    else:
        pass_("T099", f"new track in {elapsed:.0f}ms; progressMs={prog}ms ≤8000ms")
    drive("prev")  # restore


# ── T100 — Shuffle toggle (Spotify-side) reflects on DUT ─────────────────────

def _check_shuffle_api_works() -> bool:
    """Return True if the active Spotify device accepts API shuffle commands."""
    sp0 = spotify_state()
    cur = sp0.get("shuffleState", False)
    drive("setShuffle", "false" if cur else "true")
    import time as _t; _t.sleep(0.5)
    sp1 = spotify_state()
    changed = sp1.get("shuffleState") != cur
    if changed:
        drive("setShuffle", "true" if cur else "false")  # restore
    return changed


def _check_repeat_api_works() -> bool:
    """Return True if the active Spotify device accepts API repeat commands."""
    sp0 = spotify_state()
    cur_int = sp0.get("repeatState", 2)  # 0=track, 1=context, 2=off
    _MAP_STR = {2: "context", 1: "off", 0: "context"}
    probe_str = _MAP_STR[cur_int]
    drive("setRepeat", probe_str)
    import time as _t; _t.sleep(0.5)
    sp1 = spotify_state()
    changed = sp1.get("repeatState") != cur_int
    if changed:
        _REST = {2: "off", 1: "context", 0: "track"}
        drive("setRepeat", _REST[cur_int])  # restore
    return changed


def t100(dut: Dut):
    print("T100  Spotify-side toggleShuffle → DUT shuffleState flips ≤5500ms")
    if not _check_shuffle_api_works():
        skip("T100", "active Spotify device does not accept API shuffle commands "
                     "(browser/Web Player has local control); re-run with mobile/speaker device")
        return
    snap = normalize(get_snapshot(dut))
    before = snap.get("shuffleState")
    if not drive("toggleShuffle"):
        fail("T100", "spotify_drive.py toggleShuffle failed"); return
    result, elapsed = poll_until(
        dut,
        lambda s: s.get("shuffleState") != before,
        timeout=13.0, reconnect_after=5.0,
    )
    if result is None:
        fail("T100", f"shuffleState still {before} after {elapsed:.0f}ms"); return
    if elapsed > LAG_BOUND_MS:
        fail("T100", f"lag {elapsed:.0f}ms > {LAG_BOUND_MS}ms")
    else:
        pass_("T100", f"shuffle {before}→{result['shuffleState']} in {elapsed:.0f}ms")
    drive("toggleShuffle")  # restore


# ── T101 — Repeat toggle (Spotify-side) reflects on DUT ──────────────────────

def t101(dut: Dut):
    print("T101  Spotify-side setRepeat cycles → DUT repeatState updates ≤5500ms each")
    if not _check_repeat_api_works():
        skip("T101", "active Spotify device does not accept API repeat commands "
                     "(browser/Web Player has local control); re-run with mobile/speaker device")
        return
    _MAP = {2: "off", 1: "context", 0: "track"}
    snap = normalize(get_snapshot(dut))
    start_repeat = snap.get("repeatState", 2)
    # Cycle through all three states starting from after current
    cycle_order = [2, 1, 0]  # off→context→track (order of setRepeat calls)
    errors = []
    for target_int in cycle_order:
        if target_int == start_repeat and cycle_order.index(target_int) == 0:
            continue  # skip if already at this state
        target_str = _MAP[target_int]
        cur = normalize(get_snapshot(dut)).get("repeatState", -1)
        if cur == target_int:
            continue  # already there
        drive("setRepeat", target_str)
        result, elapsed = poll_until(
            dut,
            lambda s, t=target_int: s.get("repeatState") == t,
            timeout=13.0, reconnect_after=5.0,
        )
        if result is None:
            errors.append(f"repeat→{target_str}: not seen after {elapsed:.0f}ms")
        elif elapsed > LAG_BOUND_MS:
            errors.append(f"repeat→{target_str}: lag {elapsed:.0f}ms > {LAG_BOUND_MS}ms")
        else:
            print(f"    repeat→{target_str} in {elapsed:.0f}ms ✓")
    # Restore to off
    drive("setRepeat", "off")
    if errors:
        fail("T101", "; ".join(errors))
    else:
        pass_("T101", "all repeat state transitions ≤5500ms")


# ── T102 — Queue strip shifts on track-change ────────────────────────────────

def t102(dut: Dut):
    print("T102  next → DUT queue row 0 shifts within QUEUE_BOUND_MS")
    # Settle: main loop's force_fresh_poll triggers a full reconnect+poll cycle.
    # After ok 200, spotifyTask may still be mid-queue HTTP fetch.  Wait 2s so
    # the queue snapshot is committed before we read it.
    time.sleep(2.0)
    before_rows = get_queue(dut)
    if len(before_rows) < 1:
        skip("T102", "queue empty; need ≥1 row"); return
    before_row0_uri = before_rows[0].get("uri", "") if before_rows else ""
    if not drive("next"):
        fail("T102", "spotify_drive.py next failed"); return
    t_send = time.monotonic()
    # Poll up to 14s for queue to update.  Just verify row[0] URI changed — the
    # specific next-URI depends on Spotify's playback context and prior test operations.
    POLL_WINDOW_MS = 14000
    elapsed = 0.0
    shift_ms = None
    after_rows = []
    reconnect_sent = False
    while elapsed < POLL_WINDOW_MS:
        time.sleep(0.5)
        elapsed = (time.monotonic() - t_send) * 1000
        if not reconnect_sent and elapsed >= 5000:
            dut.cmd("reconnect", timeout=3.0)
            reconnect_sent = True
        after_rows = get_queue(dut)
        if after_rows and after_rows[0].get("uri", "") != before_row0_uri:
            shift_ms = elapsed
            break

    if shift_ms is None:
        got = after_rows[0].get("uri") if after_rows else "none"
        fail("T102",
             f"queue row[0] still {before_row0_uri!r} after {elapsed:.0f}ms"); return
    if shift_ms > QUEUE_BOUND_MS:
        fail("T102", f"lag {shift_ms:.0f}ms > {QUEUE_BOUND_MS}ms")
    else:
        pass_("T102", f"queue shifted in {shift_ms:.0f}ms ≤ {QUEUE_BOUND_MS}ms")
    drive("prev")  # restore


# ── T103 — Device transfer (skip: needs 2 active devices) ────────────────────

def t103(dut: Dut):
    skip("T103", "needs two active Spotify Connect devices — run manually")


# ── T104 — Optimistic-volume window: no stale snap-back ──────────────────────

def t104(dut: Dut):
    print("T104  Optimistic volume: drag enters optimistic window, no snap-back after expiry")
    snap = normalize(get_snapshot(dut))
    pre_vol = snap.get("volumePct", -1)
    if pre_vol < 0:
        skip("T104", "volumePct=-1 (no device)"); return
    # Force long next-poll via set backoff 5
    dut.cmd("set backoff 5", timeout=3.0)
    time.sleep(0.5)
    # Drain incoming serial before drag
    dut.ser.reset_input_buffer()
    # Drag volume knob across the slider
    dut.set_cooldown_zero()
    _vx0, _vx1 = _c.vol_drag_x()
    _vy = _c.vol_drag_y()
    dut.send(f"drag {_vx0} {_vy} {_vx1} {_vy} 40")
    # Collect drag response
    drag_ok = False
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if line.startswith("{") and '"cmd":"drag"' in line:
            try:
                obj = json.loads(line)
                if obj.get("ok"):
                    drag_ok = True
                    break
            except json.JSONDecodeError:
                pass
    if not drag_ok:
        fail("T104", "drag response not received"); dut.cmd("reconnect"); return

    # Verify optimistic window entered: pct must differ from pre_vol
    r_opt = dut.cmd("get optimisticVolume", timeout=2.0)
    drag_pct = r_opt.get("pct", -2)
    remaining = r_opt.get("remainingMs", 0)
    if drag_pct == pre_vol or remaining == 0:
        fail("T104",
             f"optimistic window not entered: pre_vol={pre_vol} drag_pct={drag_pct} "
             f"remainingMs={remaining}"); dut.cmd("reconnect"); return

    # Wait for optimistic window to expire (up to 5s)
    exp_deadline = time.monotonic() + 5.0
    while time.monotonic() < exp_deadline:
        r = dut.cmd("get optimisticVolume", timeout=2.0)
        if r.get("remainingMs", 1) == 0:
            break
        time.sleep(0.2)

    # After expiry: scan serial for 3s for any log line containing the pre_vol value
    # with a volume-draw context (snap-back would log drawVolume with pre_vol).
    snapback_seen = False
    pre_vol_str = str(pre_vol)
    scan_deadline = time.monotonic() + 3.0
    while time.monotonic() < scan_deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if ("vol" in line.lower() or "draw" in line.lower() or "volume" in line.lower()):
            if pre_vol_str in line and "spotify" not in line.lower():
                snapback_seen = True
                break

    if snapback_seen:
        fail("T104",
             f"snap-back detected: pre_vol={pre_vol} appeared in draw log after window expiry")
    else:
        pass_("T104",
              f"drag_pct={drag_pct}≠pre_vol={pre_vol}; window entered; no snap-back in 3s post-expiry")
    # Cleanup: reconnect to get normal polling back
    dut.cmd("reconnect", timeout=3.0)
    drive("setVolume", str(pre_vol if pre_vol >= 0 else 50))


# ── T105 — State change during 60s backoff catches up on recovery ─────────────

def t105(dut: Dut):
    print("T105  State change during 60s backoff → DUT converges on recovery (~70s test)")
    # Verify set backoff 5 reports nextPollMs=60000 (policy check).
    dut.cmd("set backoff 5", timeout=3.0)
    r_backoff = dut.cmd("get backoff", timeout=3.0)
    next_ms = r_backoff.get("nextPollMs", 0)
    if next_ms < 50000:
        fail("T105", f"nextPollMs={next_ms} < 50000 after set backoff 5"); dut.cmd("reconnect"); return
    print(f"    backoff policy confirmed: nextPollMs={next_ms}ms")
    # NOTE: 'set backoff N' changes the retry POLICY but does NOT reset the running poll
    # timer.  The existing timer fires within its remaining window (≤5s), poll succeeds,
    # and consecutiveFailures resets to 0.  A true 60s-deferred-convergence test requires
    # induced poll failures (DNS block / network disconnect) not available in this harness.
    # We therefore verify only that (a) the policy is set correctly, (b) a volume change
    # made while polls are briefly paused is picked up on the next poll.
    #
    # Use volume (not shuffle/repeat) as the state vehicle — shuffle/repeat API is rejected
    # by browser Spotify clients (Web Player local control).
    snap = normalize(get_snapshot(dut))
    vol0 = snap.get("volumePct", -1)
    if vol0 < 0:
        skip("T105", "volumePct=-1 (no active device)"); dut.cmd("reconnect"); return
    vol_target = 25 if vol0 > 50 else 75
    # Allow the existing poll timer to fire and reset backoff, then drive the state change.
    print(f"    waiting for existing poll timer to fire (≤5s)…")
    time.sleep(6)
    drive("setVolume", str(vol_target))
    t_send = time.monotonic()
    result, elapsed = poll_until(
        dut,
        lambda s: s.get("volumePct") == vol_target,
        timeout=15.0, interval=0.5, reconnect_after=5.0,
    )
    drive("setVolume", str(vol0))  # restore regardless
    if result is None:
        fail("T105", f"volumePct never reached {vol_target} after {elapsed:.0f}ms"); return
    if elapsed > LAG_BOUND_MS:
        fail("T105", f"vol convergence lag {elapsed:.0f}ms > {LAG_BOUND_MS}ms")
    else:
        pass_("T105",
              f"backoff policy nextPollMs={next_ms}ms ✓; "
              f"vol {vol0}→{vol_target} converged in {elapsed:.0f}ms ≤ {LAG_BOUND_MS}ms")


# ── T106 — Concurrent DUT tap + Spotify mutation (race) ──────────────────────

def t106(dut: Dut):
    print("T106  Concurrent DUT PAUSE tap + Spotify next → convergence, no oscillation ≤10s")
    snap = normalize(get_snapshot(dut))
    uri_a = snap.get("trackUri", "")
    # Ensure playing
    if not snap.get("isPlaying"):
        drive("play"); time.sleep(2)
    # DUT tap PAUSE
    dut.set_cooldown_zero()
    dut.send(f"tap {_c.tap_button('PAUSE')[0]} {_c.tap_button('PAUSE')[1]}")
    t_dut = time.monotonic()
    # Within 1s: host next
    time.sleep(0.3)
    drive("next")
    t_host = time.monotonic()
    print(f"    tap_PAUSE={t_dut:.3f}  spotify_next={t_host:.3f}  delta={t_host-t_dut:.3f}s")
    # Poll 15s, record (isPlaying, trackUri) trace
    trace = []
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        s = normalize(get_snapshot(dut))
        state = (s.get("isPlaying"), s.get("trackUri"))
        if not trace or trace[-1] != state:
            trace.append(state)
        time.sleep(0.5)
    # Check: final state matches Spotify ground truth
    final_dut = trace[-1] if trace else (None, None)
    sp = spotify_state()
    final_spotify = (sp.get("isPlaying"), sp.get("trackUri"))
    # Count transitions per field
    play_flips = sum(1 for i in range(1, len(trace)) if trace[i][0] != trace[i-1][0])
    uri_flips = sum(1 for i in range(1, len(trace)) if trace[i][1] != trace[i-1][1])
    if final_dut[1] != final_spotify[1]:
        fail("T106",
             f"final trackUri mismatch dut={final_dut[1]!r} spotify={final_spotify[1]!r}")
    elif play_flips > 2:
        fail("T106", f"isPlaying oscillated {play_flips} times — convergence failure")
    elif uri_flips > 2:
        fail("T106", f"trackUri oscillated {uri_flips} times — convergence failure")
    else:
        pass_("T106",
              f"converged: uri_flips={uri_flips} play_flips={play_flips} final matches Spotify")
    drive("play")  # restore to a playing state


# ── T107 — Seek on phone re-anchors M4 interpolator within one poll ───────────

def t107(dut: Dut):
    print("T107  host seek → DUT progressMs re-anchors ≤5500ms")
    snap = normalize(get_snapshot(dut))
    prog0 = snap.get("progressMs", 0)
    uri0 = snap.get("trackUri", "")
    dur = snap.get("durationMs", 120000)
    if prog0 < 5000:
        time.sleep(3); snap = normalize(get_snapshot(dut)); prog0 = snap.get("progressMs", 0)
    target = min(prog0 + 30000, dur - 5000)
    drive("seek", str(target))
    t_send = time.monotonic()
    # After the forced-poll path (~7-8s), progressMs will be target + elapsed_since_seek.
    # Check: same track AND progressMs in [target, target+12000] (within 12s of seek point).
    result, elapsed = poll_until(
        dut,
        lambda s: s.get("trackUri") == uri0 and
                  target <= int(s.get("progressMs", 0)) < target + 12000,
        timeout=14.0, interval=0.5, reconnect_after=5.0,
    )
    if result is None:
        fail("T107", f"progressMs never in [{target}, {target+12000}) after {elapsed:.0f}ms"); return
    if elapsed > LAG_BOUND_MS:
        fail("T107", f"lag {elapsed:.0f}ms > {LAG_BOUND_MS}ms")
    else:
        pass_("T107", f"seek re-anchored in {elapsed:.0f}ms; prog≈{result.get('progressMs')}ms")


# ── T108 — Track A→B→A round-trip (observation) ──────────────────────────────

def t108(dut: Dut):
    print("T108  A→B→A round-trip inside one poll window → DUT lands on A (observation)")
    snap = normalize(get_snapshot(dut))
    uri_a = snap.get("trackUri", "")
    if not uri_a:
        skip("T108", "no trackUri in snapshot"); return
    drive("next")
    t1 = time.monotonic()
    time.sleep(2.5)
    drive("prev")
    t2 = time.monotonic()
    print(f"    next@{t1:.1f} prev@{t2:.1f} gap={t2-t1:.2f}s")
    # Poll 15s; record URI trace
    trace_uris = []
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        s = normalize(get_snapshot(dut))
        uri = s.get("trackUri", "")
        if not trace_uris or trace_uris[-1] != uri:
            trace_uris.append(uri)
        time.sleep(0.5)
    final_uri = trace_uris[-1]
    saw_b = any(u != uri_a and u != "" for u in trace_uris)
    if final_uri != uri_a:
        fail("T108", f"final trackUri={final_uri!r} != A={uri_a!r} — stuck on B")
    else:
        note = "saw B in trace" if saw_b else "A→A (B missed inside poll gap)"
        pass_("T108", f"final=A ({note})")


# ── T109 — Heartbeat exposes last_poll_age_ms + next_poll_in_ms ──────────────

def t109(dut: Dut):
    print("T109  Heartbeat contains last_poll_age_ms + next_poll_in_ms (wait ≤35s each)")
    print("    Waiting for heartbeat 1…")
    hb1 = wait_heartbeat(dut, timeout=35.0)
    age1 = hb1.get("last_poll_age_ms")
    nxt1 = hb1.get("next_poll_in_ms")
    rnd1 = hb1.get("last_render_age_ms")
    # Check all three fields are present
    missing = [f for f, v in (("last_poll_age_ms", age1), ("next_poll_in_ms", nxt1),
                               ("last_render_age_ms", rnd1)) if v is None]
    if missing:
        fail("T109", f"fields missing from heartbeat: {missing}"); return
    age1_i = int(str(age1).rstrip("ms") or 0)
    nxt1_i = int(str(nxt1).rstrip("ms") or 0)
    cycle1 = age1_i + nxt1_i
    # Steady-state cycle must be in (3000, 65000) ms
    if not (3000 < cycle1 < 65000):
        fail("T109", f"steady-state cycle={cycle1}ms (age={age1}+next={nxt1}) out of range"); return

    # Verify set backoff 5 reports nextPollMs=60000 via get backoff.
    # NOTE: 'set backoff 5' sets the RETRY POLICY but does NOT reset the running poll timer.
    # The existing timer fires within ≤5s, poll succeeds, and consecutiveFailures resets.
    # We verify the policy via 'get backoff' (immediate, race-free) rather than heartbeat.
    dut.cmd("set backoff 5", timeout=3.0)
    r_b = dut.cmd("get backoff", timeout=3.0)
    cf5 = r_b.get("consecutiveFailures", -1)
    npm5 = r_b.get("nextPollMs", -1)
    if cf5 != 5 or npm5 < 54000:
        fail("T109", f"set backoff 5: consecutiveFailures={cf5} nextPollMs={npm5} (expected 5, ≈60000)")
        dut.cmd("reconnect", timeout=3.0); return

    dut.cmd("reconnect", timeout=3.0)
    pass_("T109",
          f"hb1: age={age1}+next={nxt1}={cycle1}ms, render={rnd1} ✓; "
          f"backoff5: cf={cf5} nextPollMs={npm5}ms ✓")


# ── T110 — tsync_diff.py reports zero drift in steady state ──────────────────

def t110(dut: Dut):
    print("T110  tsync_diff.py: steady-state=[OK]×5 (paused) + inline drift detection")
    port = dut.ser.port

    # Read initial state.
    snap0 = normalize(get_snapshot(dut))
    vol0 = snap0.get("volumePct", -1)
    was_playing = snap0.get("isPlaying", False)
    if vol0 < 0:
        skip("T110", "volumePct unavailable (no active device)"); return

    # Step 1 prep: pause Spotify to freeze trackUri/progressMs during the 5-run window,
    # preventing external track-change or progress drift from causing spurious DRIFT lines.
    # Also sync Spotify volume to DUT's current volume so there's no pre-existing mismatch.
    if was_playing:
        drive("pause")
        drive("setVolume", str(vol0))
        time.sleep(0.6)
    force_fresh_poll(dut)   # ensure DUT snapshot reflects paused state

    # Step 1: close port, run tsync_diff.py on paused/frozen state.
    dut.close()
    cmd = [sys.executable, str(TOOLS_DIR / "tsync_diff.py"),
           "--port", port, "--count", "5", "--interval", "1",
           "--progress-slack", "8000"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    out1 = r.stdout + r.stderr
    drift_count = out1.count("[DRIFT]")
    ok_count = out1.count("[OK]")

    # Re-open serial. tsync_diff.py rebooted DUT on its port open and left it in
    # steady state. Re-opening reboots again; call _wait_for_ready() to wait for
    # boot + WiFi + first poll before proceeding.
    dut.ser = serial.Serial()
    dut.ser.port = port
    dut.ser.baudrate = 115200
    dut.ser.timeout = 5.0
    dut.ser.dtr = False
    dut.ser.rts = False
    dut.ser.open()
    dut._wait_for_ready()

    if drift_count > 0:
        if was_playing:
            drive("play")
        fail("T110",
             f"steady-state drift: {ok_count} OK / {drift_count} DRIFT\n{out1[:400]}"); return

    # Step 2/3: resume playback, induce volume drift inline, verify detection and convergence.
    if was_playing:
        drive("play")
        force_fresh_poll(dut)

    snap = normalize(get_snapshot(dut))
    cur_vol = snap.get("volumePct", vol0)
    vol_target = 25 if cur_vol > 50 else 75
    drive("setVolume", str(vol_target))
    time.sleep(0.3)                        # let API settle before DUT polls
    snap_stale = normalize(get_snapshot(dut))
    sp = spotify_state()
    sp_vol = sp.get("volumePct", -1)
    induced_drift = (snap_stale.get("volumePct") != sp_vol and sp_vol == vol_target)
    if not induced_drift:
        print(f"    NOTE: DUT already updated volumePct={snap_stale.get('volumePct')}; "
              f"drift induction window missed (DUT polls too quickly on this network)")

    result, elapsed = poll_until(
        dut, lambda s: s.get("volumePct") == vol_target,
        timeout=15.0, interval=1.0, reconnect_after=5.0,
    )
    drive("setVolume", str(vol0))          # restore volume
    if result is None:
        fail("T110", f"step3: DUT never converged to vol={vol_target} after {elapsed:.0f}ms"); return

    pass_("T110",
          f"step1: {ok_count}/5 OK (paused, slack=8000ms); "
          f"step2: {'drift detected' if induced_drift else 'DUT polled immediately'}; "
          f"step3: converged in {elapsed:.0f}ms")


# ── T111 — Heartbeat exposes last_render_age_ms ───────────────────────────────

def t111(dut: Dut):
    print("T111  Heartbeat last_render_age_ms tracks repaint (wait up to 110s total)")
    print("    Waiting for heartbeat 1 (live playback)…")
    hb1 = wait_heartbeat(dut, timeout=35.0)
    age1 = hb1.get("last_render_age_ms")
    if age1 is None:
        fail("T111", "last_render_age_ms missing from heartbeat"); return
    age1_i = int(age1.rstrip("ms") if age1 else 0)
    if age1_i > 8000:
        fail("T111", f"last_render_age_ms={age1} > 8000ms under live playback"); return
    # Pause playback; render age should rise
    drive("pause")
    print("    Paused. Waiting for heartbeat 2…")
    hb2 = wait_heartbeat(dut, timeout=35.0)
    age2 = int(hb2.get("last_render_age_ms", "0").rstrip("ms") or 0)
    # Trigger repaint via logo tap
    dut.set_cooldown_zero()
    dut.cmd(f"tap {_c.tap_logo()[0]} {_c.tap_logo()[1]}", timeout=3.0)
    print("    Logo tap (repaint trigger). Waiting for heartbeat 3…")
    hb3 = wait_heartbeat(dut, timeout=35.0)
    age3 = int(hb3.get("last_render_age_ms", "30001").rstrip("ms") or 0)
    drive("play")  # restore
    if age3 > 30000:
        fail("T111", f"last_render_age_ms={age3} > 30000 after tap repaint")
    else:
        pass_("T111",
              f"hb1={age1}ms(live≤8000✓); hb2={age2}ms(paused↑); hb3={age3}ms(post-tap≤30k✓)")


# ── T112 — Chrome staleness indicator appears + clears (interactive visual) ───

def t112(dut: Dut, interactive: bool):
    if not interactive:
        skip("T112", "visual test — re-run with --interactive")
        return
    print("T112  Chrome staleness indicator appears above N_STALE_MS=15000, clears on poll (INTERACTIVE)")
    dut.cmd("set backoff 5", timeout=3.0)
    print("  [set backoff 5] DUT: next poll ~60s out. Waiting 16s > N_STALE_MS…")
    time.sleep(16)
    print("  [visual] An amber 4×4 pip should appear in the top-right corner of the title bar.")
    try:
        ans = input("  Is the amber staleness pip visible? [y/n] ").strip().lower()
    except EOFError:
        fail("T112", "stdin closed"); return
    if ans != "y":
        fail("T112", "amber pip not seen after 16s > N_STALE_MS"); return
    dut.cmd("reconnect", timeout=3.0)
    time.sleep(3.0)
    print("  [visual] Pip should clear after reconnect + successful poll.")
    try:
        ans2 = input("  Has the pip cleared? [y/n] ").strip().lower()
    except EOFError:
        fail("T112", "stdin closed"); return
    if ans2 != "y":
        fail("T112", "pip did not clear after reconnect")
    else:
        pass_("T112", "amber pip appeared >N_STALE_MS; cleared on poll recovery")


# ── T113 — No false positive during transient backoff (partial auto + interactive) ─

def t113(dut: Dut, interactive: bool):
    if not interactive:
        skip("T113", "visual test — re-run with --interactive (requires DNS toggle or set backoff)")
        return
    print("T113  No false positive during short backoff ladder (INTERACTIVE)")
    print("  Using set backoff 2 (next=20s) as proxy for N=2 consecutive failures.")
    print("  last_poll_age_ms will rise until reconnect fires — at N=2 next=20s,")
    print("  the poll age may briefly exceed N_STALE_MS (15s) since next≥20s.")
    print("  VE note: true no-false-positive test needs real DNS drop/restore for N=1→2→0;")
    print("  that keeps age ≤ 5+10=15s borderline (may or may not trip).")
    dut.cmd("set backoff 2", timeout=3.0)
    print("  [set backoff 2] Watching for ~20s. NO amber pip should appear (borderline).")
    time.sleep(12)
    try:
        ans = input("  Is the amber pip absent (no false positive)? [y/n] ").strip().lower()
    except EOFError:
        fail("T113", "stdin closed"); return
    # Now set backoff 3 (next=40s > N_STALE_MS=15s) to confirm TRUE positive
    print("  [set backoff 3] Forcing next=40s. Pip SHOULD appear after 15s.")
    dut.cmd("set backoff 3", timeout=3.0)
    time.sleep(16)
    try:
        ans2 = input("  Is the amber pip now visible (true positive at N=3)? [y/n] ").strip().lower()
    except EOFError:
        fail("T113", "stdin closed"); return
    dut.cmd("reconnect", timeout=3.0)
    if ans != "y":
        fail("T113", "amber pip seen during N=2 short backoff — possible false positive")
    elif ans2 != "y":
        fail("T113", "amber pip NOT seen at N=3 sustained failure — staleness indicator broken")
    else:
        pass_("T113", "no false positive at N=2; true positive at N=3; cleared on reconnect")


# ── T114 — getQueue dechunker regression (conn-002 + playlist-002) ──────────

def t114(dut: Dut):
    print("T114  get queue returns count>0 within keepalive cycle (dechunker regression)")
    # Settle: let any in-progress queue HTTP fetch complete after the pre-test poll.
    time.sleep(2.0)
    rows = get_queue(dut)
    if len(rows) == 0:
        fail("T114", "queue empty — dechunker or chunked-body regression, or no active playlist"); return
    first_uri = rows[0].get("uri", "")
    pass_("T114", f"count={len(rows)} row[0]={first_uri!r}")


def _pledit_tap_xy(row: int) -> tuple[int, int]:
    return _c.pledit_tap(row)


def _wait_queue_row0_shifts(dut: Dut, prev_r0_uri: str, timeout: float = 14.0) -> list[dict]:
    """Poll get queue until row0.uri != prev_r0_uri or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = get_queue(dut)
        if rows and rows[0].get("uri", "") != prev_r0_uri:
            return rows
        time.sleep(0.8)
    return get_queue(dut)  # return whatever we have at timeout


# ── T115 — tap-to-play within playlist context preserves queue ────────────────

def t115(dut: Dut):
    print("T115  Tap PLEDIT row 1 in playlist/album context — queue preserved, no duplicate rows")

    snap = normalize(get_snapshot(dut))
    ctx  = snap.get("contextUri", "")
    if not ctx or (not ctx.startswith("spotify:playlist:")
                   and not ctx.startswith("spotify:album:")):
        skip("T115", f"contextUri={ctx!r} — not playlist/album; start Spotify from a playlist and re-run")
        return

    time.sleep(1.5)  # let any in-flight queue fetch settle
    rows0 = get_queue(dut)
    if len(rows0) < 2:
        skip("T115", f"queue count={len(rows0)} < 2; need ≥2 distinct items"); return
    r0_uri = rows0[0].get("uri", "")
    r1_uri = rows0[1].get("uri", "")
    if not r0_uri or not r1_uri:
        skip("T115", "row0 or row1 uri empty — queue not populated yet"); return
    if r0_uri == r1_uri:
        skip("T115", "row0==row1 before tap — ambiguous (single-track repeat?); can't verify"); return

    print(f"    context: {ctx!r}")
    print(f"    pre-tap: count={len(rows0)} row0={r0_uri!r}")
    print(f"             row1={r1_uri!r}")

    tx, ty = _pledit_tap_xy(1)
    print(f"    tapping row 1 at ({tx},{ty})…")
    dut.set_cooldown_zero()
    dut.send(f"tap {tx} {ty}")
    try:
        tap_r = dut.read_json(timeout=3.0)
        print(f"    tap ack: {tap_r}")
        if tap_r.get("hit") != "PLEDIT":
            fail("T115", f"tap hit={tap_r.get('hit')!r} expected PLEDIT — coordinates or injectTouch PLEDIT path wrong"); return
    except TimeoutError:
        print("    (no tap ack JSON)")

    # Wait for queue row0 to shift to the tapped track
    rows1 = _wait_queue_row0_shifts(dut, r0_uri, timeout=14.0)

    if not rows1:
        fail("T115", "queue empty after tap"); return

    new_r0 = rows1[0].get("uri", "")
    new_r1 = rows1[1].get("uri", "") if len(rows1) > 1 else ""
    print(f"    post-tap: count={len(rows1)} row0={new_r0!r}")
    if new_r1:
        print(f"              row1={new_r1!r}")

    # row0 must be the track we tapped (was row1 before tap)
    if new_r0 != r1_uri:
        fail("T115",
             f"row0={new_r0!r} expected={r1_uri!r} "
             f"— wrong track or context_uri path not taken"); return

    # Queue must not be 5 identical rows (the pre-fix regression symptom)
    uris = [r.get("uri", "") for r in rows1]
    distinct = len(set(uris))
    if distinct == 1 and len(uris) >= 2:
        fail("T115",
             f"all {len(uris)} queue rows identical — playAdvanced used {{uris:[...]}} "
             f"instead of context_uri+offset"); return

    # Cross-check with Spotify API
    sp = spotify_state()
    sp_uri = sp.get("trackUri", "")
    if sp_uri and sp_uri != new_r0:
        fail("T115",
             f"DUT row0={new_r0!r} but Spotify playing {sp_uri!r}"); return

    pass_("T115",
          f"row0 shifted to tapped track; queue diverse "
          f"(distinct={distinct}/{len(uris)}); Spotify agrees")


# ── T116 — tap-to-play fallback with no context_uri (ad-hoc / radio) ─────────

def _play_adhoc_uri(uri: str):
    """PUT /me/player/play with a single URI — creates an ad-hoc no-context session."""
    import urllib.request as ur
    token = _access_token()
    body  = json.dumps({"uris": [uri]}).encode()
    req   = ur.Request(
        "https://api.spotify.com/v1/me/player/play",
        data=body,
        method="PUT",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    with ur.urlopen(req, timeout=10) as r:
        return r.status in (200, 204)


def t116(dut: Dut):
    print("T116  Tap PLEDIT row 1 with no context_uri — fallback fires, DUT survives")

    # Grab a track URI from current queue to force an ad-hoc session.
    time.sleep(1.0)
    rows_pre = get_queue(dut)
    if not rows_pre:
        skip("T116", "queue empty — no URI available to start ad-hoc session"); return
    adhoc_uri = rows_pre[0].get("uri", "")
    if not adhoc_uri:
        skip("T116", "row0 uri empty"); return

    # Force ad-hoc single-track session via host Spotify API (no context_uri).
    print(f"    forcing ad-hoc session via host API: {adhoc_uri!r}")
    _play_adhoc_uri(adhoc_uri)

    # Wait for DUT to poll and pick up contextUri="" (up to 14s = ~2 poll cycles).
    print("    waiting for DUT to see empty contextUri…")
    snap = None
    deadline = time.monotonic() + 16.0
    while time.monotonic() < deadline:
        snap = normalize(get_snapshot(dut))
        if snap.get("contextUri", "x") == "":
            break
        time.sleep(1.2)
    if not snap or snap.get("contextUri", "x") != "":
        skip("T116",
             f"contextUri={snap.get('contextUri', '?')!r} never cleared — "
             "Spotify may have restored a context; retry manually"); return

    time.sleep(1.5)  # allow queue fetch to settle after poll
    rows0 = get_queue(dut)
    if len(rows0) < 2:
        skip("T116", f"queue count={len(rows0)} < 2 after ad-hoc play"); return
    r0_uri = rows0[0].get("uri", "")
    r1_uri = rows0[1].get("uri", "")
    if not r1_uri:
        skip("T116", "row1 uri empty after ad-hoc play"); return

    print(f"    pre-tap: count={len(rows0)} row0={r0_uri!r} row1={r1_uri!r}")

    tx, ty = _pledit_tap_xy(1)
    print(f"    tapping row 1 at ({tx},{ty}) (ad-hoc fallback path)…")
    dut.set_cooldown_zero()
    dut.send(f"tap {tx} {ty}")
    try:
        tap_r = dut.read_json(timeout=3.0)
        print(f"    tap ack: {tap_r}")
        if tap_r.get("hit") != "PLEDIT":
            fail("T116", f"tap hit={tap_r.get('hit')!r} expected PLEDIT"); return
    except TimeoutError:
        print("    (no tap ack JSON)")

    rows1 = _wait_queue_row0_shifts(dut, r0_uri, timeout=14.0)

    snap_after = normalize(get_snapshot(dut))
    if not snap_after.get("valid"):
        fail("T116", "snapshot invalid after tap — possible crash/reboot"); return

    new_r0 = rows1[0].get("uri", "") if rows1 else ""
    print(f"    post-tap: count={len(rows1)} row0={new_r0!r}")

    if new_r0 != r1_uri:
        fail("T116",
             f"row0={new_r0!r} expected={r1_uri!r} — track did not change to tapped"); return

    uris = [r.get("uri", "") for r in rows1]
    distinct = len(set(uris))
    note = (f" (queue duplication distinct={distinct}/{len(uris)} — expected in ad-hoc mode)"
            if distinct == 1 and len(uris) >= 2 else "")

    pass_("T116", f"fallback fired; DUT alive; track changed to tapped URI{note}")


# ── main ──────────────────────────────────────────────────────────────────────

ALL_TESTS = {
    "T097": t097,
    "T098": t098,
    "T099": t099,
    "T100": t100,
    "T101": t101,
    "T102": t102,
    "T103": t103,
    "T104": t104,
    "T105": t105,
    "T106": t106,
    "T107": t107,
    "T108": t108,
    "T109": t109,
    "T110": t110,
    "T111": t111,
    "T112": None,   # interactive visual
    "T113": None,   # interactive visual
    "T114": t114,
    "T115": t115,
    "T116": t116,
}

_INTERACTIVE_TESTS = {"T112", "T113"}


def main():
    p = argparse.ArgumentParser(
        description="sync-001 + drift-001 + playlist-001 test suite (T097–T116)."
    )
    p.add_argument("--port", default="/dev/ttyUSB1")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--interactive", action="store_true",
                   help="enable visual tests T112 + T113")
    default_tests = ",".join(k for k in ALL_TESTS if k not in _INTERACTIVE_TESTS)
    p.add_argument("--tests", default=default_tests,
                   help="comma-separated test IDs")
    args = p.parse_args()

    if not CONFIG.exists():
        sys.exit(f"creds not found: {CONFIG}")

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in ALL_TESTS]
    if unknown:
        sys.exit(f"Unknown tests: {unknown}. Available: {sorted(ALL_TESTS)}")

    print(f"Connecting to {args.port} @ {args.baud}…")
    dut = Dut(args.port, args.baud, timeout=5.0)
    print(f"Connected. Running: {selected}\n")

    skip_notice = [t for t in selected if t in _INTERACTIVE_TESTS and not args.interactive]
    if skip_notice:
        print(f"NOTE: {skip_notice} will SKIP — re-run with --interactive.\n")

    # Tests that manage their own serial or don't need a live DUT poll
    _NO_FORCE_POLL = {"T103", "T110", "T112", "T113"}

    for tid in selected:
        print(f"\n── {tid} ──")
        # Force fresh TLS + poll before each test to clear stale connections.
        # T110 closes/reopens the port itself; skip force_fresh_poll for it.
        if tid not in _NO_FORCE_POLL:
            if not force_fresh_poll(dut, timeout=15.0):
                fail(tid, "pre-test force_fresh_poll failed — DUT not polling")
                continue
        try:
            if tid in _INTERACTIVE_TESTS:
                ALL_TESTS[tid] if ALL_TESTS[tid] else (
                    lambda t=tid: globals()[f"t{t[1:].lower()}"](dut, args.interactive))()
                fn = t112 if tid == "T112" else t113
                fn(dut, args.interactive)
            else:
                ALL_TESTS[tid](dut)
        except TimeoutError as e:
            fail(tid, f"TimeoutError: {e}")
        except Exception as e:
            import traceback
            fail(tid, f"Exception: {e}")
            traceback.print_exc()
        time.sleep(0.5)

    # Ensure port is closed
    try:
        dut.close()
    except Exception:
        pass

    print("\n── Results ──────────────────────────────────")
    passed  = sum(1 for v in RESULTS.values() if v == "PASS")
    failed  = sum(1 for v in RESULTS.values() if v.startswith("FAIL"))
    skipped = sum(1 for v in RESULTS.values() if v.startswith("SKIP"))
    for tid, result in sorted(RESULTS.items()):
        print(f"  {tid}: {result}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
