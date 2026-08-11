#!/usr/bin/env python3
"""sd_put.py — upload host files onto the DUT's SD card over serial (TASK-415).

Drives the SERIAL_DEBUG `sdmkdir` / `sdput` commands. Each `sdput` call is one
open / write / close of at most 90 bytes — deliberately the short-burst pattern
that works around TASK-424's sustained-write defect, and slow (~25 KB/min) for
exactly that reason. This is for test fixtures, not for bulk data.

    python3 app/tools/sd_put.py app/tools/fixtures/sd/playlists/bad.m3u /playlists/bad.m3u
    python3 app/tools/sd_put.py --tree app/tools/fixtures/sd        # mirrors the whole tree

Requires the DUT flashed with cyd2usb_winamp_debug and the serial monitor down.
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

import serial

CHUNK = 90            # bytes per sdput call; 90 -> 120 base64 chars, under the 160 B line buffer
DEFAULT_PORT = "/dev/ttyUSB1"


class Dut:
    def __init__(self, port: str, boot_wait: float):
        self.ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(boot_wait)          # opening the port pulls DTR -> the ESP32 reboots
        self.ser.reset_input_buffer()

    def cmd(self, line: str, timeout: float = 10.0) -> dict:
        self.ser.write((line + "\n").encode())
        self.ser.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self.ser.readline().decode("utf-8", "replace").strip()
            if not raw.startswith("{"):
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "cmd" in obj:
                return obj
        return {"ok": False, "error": "timeout", "cmd": line}


def put_file(dut: Dut, src: Path, dest: str, verbose: bool = True) -> bool:
    data = src.read_bytes()
    # First call truncates (op 'w'), the rest append. An empty file still needs
    # the create call, hence the "-" payload form.
    first = data[:CHUNK] if data else b""
    payload = base64.b64encode(first).decode() if first else "-"
    r = dut.cmd(f"sdput w {payload} {dest}", timeout=15.0)
    if not r.get("ok"):
        print(f"  FAIL {dest}: {r}")
        return False
    sent = len(first)
    while sent < len(data):
        block = data[sent:sent + CHUNK]
        r = dut.cmd(f"sdput a {base64.b64encode(block).decode()} {dest}", timeout=15.0)
        if not r.get("ok"):
            print(f"  FAIL {dest} at byte {sent}: {r}")
            return False
        sent += len(block)
        if verbose and sent % (CHUNK * 20) == 0:
            print(f"    {sent}/{len(data)} B", end="\r", flush=True)
    final = r.get("sizeB", -1)
    ok = final == len(data)
    print(f"  {'OK  ' if ok else 'SIZE MISMATCH '} {dest}  {final}/{len(data)} B")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", help="host file to upload")
    ap.add_argument("dest", nargs="?", help="absolute path on the card")
    ap.add_argument("--tree", help="mirror a host directory onto the card root")
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--boot-wait", type=float, default=8.0,
                    help="seconds to wait for the DTR-triggered reboot to finish")
    a = ap.parse_args()

    dut = Dut(a.port, a.boot_wait)
    ok = True
    if a.tree:
        root = Path(a.tree)
        files = sorted(p for p in root.rglob("*") if p.is_file())
        dirs = sorted({("/" + str(p.parent.relative_to(root))) for p in files} - {"/."})
        for d in dirs:
            print(f"mkdir {d}: {dut.cmd(f'sdmkdir {d}')}")
        for p in files:
            dest = "/" + str(p.relative_to(root))
            print(f"put {p} -> {dest}")
            ok &= put_file(dut, p, dest)
    elif a.src and a.dest:
        ok = put_file(dut, Path(a.src), a.dest)
    else:
        ap.error("give SRC DEST, or --tree DIR")
    dut.ser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
