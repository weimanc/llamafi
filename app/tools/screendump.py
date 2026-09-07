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
# TASK-479: reuse lib/dut.py's boot handling rather than re-deriving it.
# TASK-589: this line used to also import `_PORTAL_INDICATORS`, which TASK-555
# deleted — it matched WiFiManager's force-portal banners, and WiFiManager left
# this firmware in ddf6433 (2026-06-11). The import therefore raised
# ImportError before the port was ever opened, taking this instrument and its
# three dependants (clock_delta_smoke, pr_delta_smoke, slider_delta_smoke) down
# with it. The branch is DROPPED, not restored: a constant brought back locally
# to feed a branch that no firmware can fire is dead code that reads as live
# safety machinery, which is exactly what TASK-555 removed.
from lib.dut import Dut, _DUT_WIFI_WAIT_S, _is_ip_line

import numpy as np
from PIL import Image


class DutLite(Dut):
    """Same DRD-gap + reboot-on-open handling as Dut, but stops once WiFi is
    up — skips Dut's Spotify-poll readiness wait. screendump doesn't touch
    Spotify state, and TASK-243's Premium lapse means that wait currently
    always times out (~120s of dead weight) for zero benefit here.
    """
    def _wait_for_ready(self):   # TASK-555 dropped Dut's _recovery_attempt arg
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
            # TASK-589: `_is_ip_line` is lib/dut.py's own predicate, so this
            # matches `STA_GOT_IP` too — the line the supervisor's reconnect
            # path prints when it acquires an address without re-running
            # setup()'s `IP address:` print (dut.py's 2026-08-14 note).
            if _is_ip_line(line):
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


# ── the readback path's own oracle (TASK-589, re-verifying TASK-340) ─────────
# TASK-340 found two compounding faults in `tft.readRect()`: a deliberate
# upstream byte swap ("swapped colour byte order for compatibility with
# pushRect()") that `cmdScreenDump` now undoes firmware-side, and a genuinely
# unreliable MISO read at SPI_READ_FREQUENCY=20 MHz, fixed by dropping to
# 2.5 MHz. It closed on `colorprobe` reading 25/25 clean. That evidence was a
# one-off in a task record; ADR-064 then made this exact path the project's
# render-verification mechanism. So the oracle lives in the instrument now, and
# `./run/screendump --colorprobe` re-runs it on demand.
#
# The transform is asserted, not assumed: `colorprobe` prints readRect's RAW
# return, so a `fill` probe must come back byte-swapped and a `push` probe
# (pushRect writes raw words with _swapBytes off) must round-trip identically.


def _byteswap16(v: int) -> int:
    return ((v << 8) | (v >> 8)) & 0xFFFF


def colorprobe_verdict(probes):
    """Pure: [(kind, expected, actual)] -> (n_ok, n_total, [failure strings]).

    Separated from the serial read so the TASK-340 transform can be exercised
    on the host, with no board, by gate/check_screendump_instrument.py.
    """
    fails = []
    for kind, exp, act in probes:
        want = _byteswap16(exp) if kind == "fill" else exp
        if act != want:
            fails.append(f"{kind} expected={exp:#06x} want_readback={want:#06x} "
                         f"actual={act:#06x}")
    return len(probes) - len(fails), len(probes), fails


def run_colorprobe(dut, timeout=30.0):
    """Drive `colorprobe` and adjudicate it. Returns (n_ok, n_total, failures)."""
    dut.send("colorprobe")
    deadline = time.monotonic() + timeout
    probes = []
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "probe" not in rec:
            continue
        probes.append((rec["probe"], int(rec["expected"]), int(rec["actual"])))
        if rec.get("last"):
            break
    return colorprobe_verdict(probes)


#: Where `cmdColorProbe` leaves its last `pushRect` swatch, and the value it
#: leaves there. Reading THAT back through the band/base64 path is the
#: end-to-end ground truth: firmware-known pixels in, host PNG pixels out, with
#: readRect, the firmware byte-swap correction, base64 and the host reassembly
#: all in the loop. `colorprobe` alone only proves readRect.
COLORPROBE_SWATCH = (40, 40, 2, 2)
COLORPROBE_SWATCH_VALUE = 0xF0F0


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
    ap.add_argument("--colorprobe", action="store_true",
                    help="re-verify the GRAM readback path (TASK-340's 25/25 "
                         "sweep) and then read the swatch it leaves back "
                         "through this tool's own band path; exits 1 on any "
                         "mismatch. Overwrites an 8x8 area at (40,40).")
    args = ap.parse_args()

    port = args.port or autodetect_port()
    dut = DutLite(port)  # opens + boot-waits in __init__

    if args.colorprobe:
        n_ok, n_total, fails = run_colorprobe(dut)
        print(f"[colorprobe] readRect transform: {n_ok}/{n_total} clean "
              f"(TASK-340 recorded 25/25 at SPI_READ_FREQUENCY=2.5MHz)")
        for f in fails:
            print(f"  MISMATCH {f}")
        sx, sy, sw, sh = COLORPROBE_SWATCH
        swatch = dump_with_retry(dut, sx, sy, sw, sh)
        want = COLORPROBE_SWATCH_VALUE
        bad = int((swatch != want).sum())
        print(f"[colorprobe] end-to-end swatch at ({sx},{sy}) {sw}x{sh}: "
              f"{swatch.size - bad}/{swatch.size} px == {want:#06x} "
              f"(values seen: {sorted(set(int(v) for v in swatch.flat))})")
        ok = (not fails) and n_total > 0 and bad == 0
        print("[colorprobe] " + ("PASS — readback path intact end to end"
                                 if ok else "FAIL"))
        return 0 if ok else 1

    canvas = dump_with_retry(dut, args.x, args.y, args.w, args.h)

    rgb = rgb565_to_rgb888(canvas)
    Image.fromarray(rgb, "RGB").save(args.out)
    print(f"wrote {args.out} ({canvas.shape[1]}x{canvas.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
