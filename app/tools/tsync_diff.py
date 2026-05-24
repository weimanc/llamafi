#!/usr/bin/env python3
"""
tsync_diff.py — DUT snapshot vs Spotify /me/player field diff.

Fetches `get snapshot` over serial from the DUT and /me/player over HTTPS
from Spotify. Diffs the firmware-consumed field set (per T073 / ADR-015).
Prints [OK] when fields agree, [DRIFT] <field>=<dut_val> spotify=<spotify_val>
for each mismatch.

Exit 0 = no drift (or only progressMs within slack). Exit 1 = drift detected.

Usage:
    python3 tools/tsync_diff.py [--port /dev/ttyUSB0] [--progress-slack 2000]
    # run N times:
    python3 tools/tsync_diff.py --count 10 --interval 1

Requirements:
    pip install pyserial
    DUT flashed with cyd2usb_winamp_debug, booted, WiFi up, Spotify creds valid.
    Active Spotify Connect device playing a track.
    Valid creds at Spotify-Diy-Thing/data/spotify_diy_config.json
"""

import argparse
import base64
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "data" / "spotify_diy_config.json"

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")

# Firmware-consumed fields compared by T073. progressMs is compared with slack.
# shuffleState / repeatState map Spotify strings → firmware int.
_REPEAT_MAP = {"track": 0, "context": 1, "off": 2}
_PROGRESS_SLACK_MS_DEFAULT = 2000  # interpolation + sequential-call drift


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
        """CH341 driver asserts DTR during open(); detect reboot and wait for ready.
        Waits for first SUCCESSFUL poll (ok 200) + queue fetch. Retries via reconnect
        if startup poll fails."""
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
        self.ser.timeout = 1.0
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in line:
                break
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

    def send(self, cmd: str):
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()

    def read_json(self, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        raise TimeoutError("no JSON line from DUT within timeout")

    def close(self):
        self.ser.close()


def get_snapshot(dut: Dut) -> dict:
    """Send `get snapshot`, accumulate split-protocol chunks, return merged dict."""
    dut.send("get snapshot")
    chunks: dict = {}
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        r = dut.read_json(timeout=3.0)
        chunks.update(r)
        if r.get("last"):
            return chunks
    raise TimeoutError("snapshot: never received last=true chunk")


# ── Spotify helpers ────────────────────────────────────────────────────────────

def get_access_token(cfg: dict) -> str:
    basic = base64.b64encode(
        f"{cfg['clientId']}:{cfg['clientSecret']}".encode()
    ).decode()
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": cfg["refreshToken"],
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["access_token"]


def fetch_spotify(token: str) -> dict | None:
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player?additional_types=episode",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 204:
                return None
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET /me/player HTTP {e.code}")


def parse_spotify(raw: dict) -> dict:
    item = raw.get("item") or {}
    artists = item.get("artists") or []
    artist_name = artists[0].get("name", "") if artists else ""
    dev = raw.get("device") or {}
    vp = dev.get("volume_percent")
    repeat_str = raw.get("repeat_state", "off")
    return {
        "isPlaying":    bool(raw.get("is_playing")),
        "progressMs":   int(raw.get("progress_ms") or 0),
        "durationMs":   int(item.get("duration_ms") or 0),
        "volumePct":    int(vp) if vp is not None else -1,
        "shuffleState": bool(raw.get("shuffle_state")),
        "repeatState":  _REPEAT_MAP.get(repeat_str, 2),
        "trackUri":     item.get("uri", ""),
    }


# ── diff engine ───────────────────────────────────────────────────────────────

def normalize_dut_snapshot(snap: dict) -> dict:
    """Map DUT JSON field names to the common names used by diff().

    DUT emits 'shuffle'/'repeat'/'currentTrackUri'; diff() and parse_spotify()
    use 'shuffleState'/'repeatState'/'trackUri'.
    """
    out = dict(snap)
    if "shuffle" in out:
        out["shuffleState"] = out.pop("shuffle")
    if "repeat" in out:
        out["repeatState"] = out.pop("repeat")
    if "currentTrackUri" in out:
        out["trackUri"] = out.pop("currentTrackUri")
    return out


def diff(dut_snap: dict, spotify: dict, progress_slack: int) -> list[str]:
    """Return list of drift strings; empty = no drift."""
    dut_snap = normalize_dut_snapshot(dut_snap)
    drifts = []
    fields = ["isPlaying", "volumePct", "shuffleState", "repeatState", "trackUri",
              "durationMs", "progressMs"]
    for f in fields:
        dv = dut_snap.get(f)
        sv = spotify.get(f)
        if f == "progressMs":
            if dv is None or sv is None:
                continue
            if abs(int(dv) - int(sv)) > progress_slack:
                drifts.append(f"progressMs dut={dv} spotify={sv} "
                              f"(|diff|={abs(int(dv)-int(sv))}ms > slack={progress_slack}ms)")
        else:
            if dv != sv:
                drifts.append(f"{f} dut={dv!r} spotify={sv!r}")
    return drifts


# ── main ──────────────────────────────────────────────────────────────────────

def run_once(dut: Dut, token: str, progress_slack: int, verbose: bool) -> bool:
    """Returns True if no drift."""
    snap = get_snapshot(dut)
    if not snap.get("valid"):
        print("SKIP: DUT snapshot not valid (no successful poll yet)")
        return True

    raw_spotify = fetch_spotify(token)
    if raw_spotify is None:
        print("SKIP: Spotify 204 — no active device")
        return True

    spotify = parse_spotify(raw_spotify)

    if verbose:
        print(f"  DUT:     {json.dumps({k: snap.get(k) for k in spotify})}")
        print(f"  Spotify: {json.dumps(spotify)}")

    drifts = diff(snap, spotify, progress_slack)
    if drifts:
        for d in drifts:
            print(f"[DRIFT] {d}")
        return False
    print("[OK]")
    return True


def main():
    ap = argparse.ArgumentParser(description="Diff DUT snapshot against Spotify /me/player.")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--progress-slack", type=int, default=_PROGRESS_SLACK_MS_DEFAULT,
                    metavar="MS", help="max allowed progressMs delta (default %(default)s ms)")
    ap.add_argument("--count", type=int, default=1, help="number of diff runs")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="seconds between runs when --count > 1")
    ap.add_argument("--verbose", action="store_true", help="print raw field values")
    args = ap.parse_args()

    if not CONFIG.exists():
        sys.exit(f"creds not found: {CONFIG}")

    cfg = json.loads(CONFIG.read_text())
    token = get_access_token(cfg)

    dut = Dut(args.port, args.baud)
    any_drift = False
    try:
        for i in range(args.count):
            if args.count > 1:
                print(f"--- run {i+1}/{args.count} ---")
            ok = run_once(dut, token, args.progress_slack, args.verbose)
            if not ok:
                any_drift = True
            if i < args.count - 1:
                time.sleep(args.interval)
    finally:
        dut.close()

    sys.exit(1 if any_drift else 0)


if __name__ == "__main__":
    main()
