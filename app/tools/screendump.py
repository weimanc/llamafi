#!/usr/bin/env python3
"""
screendump.py — pull an exact DUT screenshot via the SERIAL_DEBUG `screendump`
command, instead of relying on a human eyeballing the physical screen.

The firmware reads the live TFT GRAM back over SPI (MISO is wired on this
board — TFT_MISO=12, SPI_READ_FREQUENCY=2.5MHz, see app/platformio.ini;
lowered from 20MHz by TASK-340 — 20MHz was signal-integrity-unreliable on
this board's MISO read) and streams it out as base64 RGB565 bands, already
byte-swap-corrected firmware-side (TASK-340) back to true RGB565. This
script reassembles those bands into a PNG.

Requires: debug firmware flashed (./run/flash-debug), pyserial, numpy, Pillow.
Use the ./run/screendump wrapper, not this script directly — it handles
killing/restoring the tmux serial monitor around the port access.

Usage:
    python3 app/tools/screendump.py -o /tmp/clock.png
    python3 app/tools/screendump.py -x 0 -y 0 -w 275 -h 240 -o /tmp/canvas.png   # app canvas only, excludes taskbar
"""
import argparse
import base64
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run_serialdbg_tests import Dut, _DUT_WIFI_WAIT_S, _PORTAL_INDICATORS  # reuse DRD-gap/boot handling

import numpy as np
from PIL import Image


class DutLite(Dut):
    """Same DRD-gap + reboot-on-open handling as Dut, but stops once WiFi is
    up — skips Dut's Spotify-poll readiness wait. screendump doesn't touch
    Spotify state, and TASK-243's Premium lapse means that wait currently
    always times out (~120s of dead weight) for zero benefit here.
    """
    def _wait_for_ready(self, _recovery_attempt: int = 0):
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
        print("  [DutLite] reboot detected — waiting for WiFi …", flush=True)
        self.ser.timeout = 1.0
        deadline = time.monotonic() + _DUT_WIFI_WAIT_S
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in line or any(ind in line for ind in _PORTAL_INDICATORS):
                break
        # WiFi-up isn't "loop() is servicing Serial promptly" — setup() keeps
        # doing blocking work after WiFi connects (token refresh POST,
        # spotifyTask::begin(), dataTask start...) during which a command
        # sent now can sit unanswered for several seconds (not lost — just
        # queued behind a blocking call), long enough to blow past Dut's
        # fixed 3s _verify_debug_firmware timeout. A "wait for quiet" heuristic
        # doesn't work either — steady-state emits periodic heartbeat/membudget
        # chatter forever. Instead wait for the first `[hb]` heartbeat line,
        # the project's own established "main loop is steady-state" signal
        # (logHeartbeat.h) — it only starts firing once setup()'s blocking
        # work is done and loop() is spinning normally.
        print("  [DutLite] WiFi up — waiting for first heartbeat …", flush=True)
        self.ser.timeout = 1.0
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "[hb]" in line:
                break
        self.ser.timeout = orig_timeout
        self.ser.reset_input_buffer()
        print("  [DutLite] ready.", flush=True)


def rgb565_to_rgb888(u16: np.ndarray) -> np.ndarray:
    r = ((u16 >> 11) & 0x1F).astype(np.uint16) * 255 // 31
    g = ((u16 >> 5) & 0x3F).astype(np.uint16) * 255 // 63
    b = (u16 & 0x1F).astype(np.uint16) * 255 // 31
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def autodetect_port() -> str:
    port_script = pathlib.Path(__file__).parent.parent.parent / "run" / "port"
    out = subprocess.run([str(port_script)], capture_output=True, text=True)
    port = out.stdout.strip()
    if not port:
        sys.exit(f"could not autodetect port: {out.stderr.strip()}")
    return port


def _dump_region(dut, x, y, w, h, timeout=30.0):
    """Send one `screendump` command and collect its bands.

    Returns (canvas, failed) where failed is a list of (ry, rows) bands that
    didn't decode cleanly — firmware has no cross-task Serial-write lock, so
    a background task's log line (heartbeat, membudget, TLS chatter — all
    fired from spotifyTask/dataTask independent of the main loop) can
    interleave mid-band and corrupt its base64. See module docstring.
    """
    dut.send(f"screendump {x} {y} {w} {h}")
    deadline = time.monotonic() + timeout
    canvas = None
    hdr_w = hdr_h = 0
    failed = []
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                header = json.loads(line)
            except json.JSONDecodeError:
                continue
            if header.get("cmd") != "screendump":
                continue  # stray JSON line (e.g. boot-tail chatter) — keep waiting
            if not header.get("ok"):
                raise RuntimeError(f"screendump failed: {header}")
            hdr_w, hdr_h = header["w"], header["h"]
            canvas = np.zeros((hdr_h, hdr_w), dtype="<u2")
            continue
        if line.startswith("SCREENDUMP:BAND "):
            if canvas is None:
                continue  # band before header somehow — wait for END/timeout
            body = line[len("SCREENDUMP:BAND "):]
            ry = rows = None
            try:
                ry_s, rows_s, b64_data = body.split(" ", 2)
                ry, rows = int(ry_s), int(rows_s)
                raw = base64.b64decode(b64_data, validate=True)
                band = np.frombuffer(raw, dtype="<u2").reshape(rows, hdr_w)
            except Exception:
                if ry is not None:
                    failed.append((ry, rows))
                continue
            canvas[ry:ry + rows, :] = band
            continue
        if line.strip() == "SCREENDUMP:END":
            break
    if canvas is None:
        raise RuntimeError("no screendump header received within timeout")
    return canvas, failed


def dump_with_retry(dut, x, y, w, h, max_retries=4):
    canvas, failed = _dump_region(dut, x, y, w, h)
    attempt = 0
    while failed and attempt < max_retries:
        attempt += 1
        print(f"  [screendump] retrying {len(failed)} corrupted band(s) "
              f"(attempt {attempt}/{max_retries})…", flush=True)
        still_failed = []
        for ry, rows in failed:
            sub, sub_failed = _dump_region(dut, x, y + ry, w, rows)
            canvas[ry:ry + rows, :] = sub
            still_failed.extend((ry + sry, srows) for sry, srows in sub_failed)
        failed = still_failed
    if failed:
        print(f"  [screendump] WARNING: {len(failed)} band(s) never decoded cleanly "
              f"after {max_retries} retries — image has gaps there.", file=sys.stderr)
    return canvas


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("-x", type=int, default=0)
    ap.add_argument("-y", type=int, default=0)
    ap.add_argument("-w", type=int, default=320)
    ap.add_argument("-H", "--height", type=int, default=240, dest="h")
    ap.add_argument("-o", "--out", default="/tmp/screendump.png")
    args = ap.parse_args()

    port = args.port or autodetect_port()
    dut = DutLite(port)  # opens + boot-waits in __init__

    canvas = dump_with_retry(dut, args.x, args.y, args.w, args.h)

    rgb = rgb565_to_rgb888(canvas)
    Image.fromarray(rgb, "RGB").save(args.out)
    print(f"wrote {args.out} ({canvas.shape[1]}x{canvas.shape[0]})")


if __name__ == "__main__":
    main()
