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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.dut import resolve_port  # TASK-479: one port resolver (run/port)

CHUNK = 90            # bytes per sdput call; 90 -> 120 base64 chars, under the 160 B line buffer
DEFAULT_PORT = resolve_port()


class Dut:
    def __init__(self, port: str, boot_wait: float):
        self.ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(boot_wait)          # opening the port pulls DTR -> the ESP32 reboots
        self.ser.reset_input_buffer()

    def cmd(self, line: str, timeout: float = 10.0) -> dict:
        # Drop anything still inbound before issuing the next command. Without
        # this the reader can return a LATE ack from the *previous* sdput and
        # report ok for a call the device never received -- the transfer then
        # walks on with a silently missing chunk. Measured 2026-08-31: 4 of the
        # 5 short5 MP3s on the card were short by exact multiples of CHUNK
        # (-90, -90, -900, -90 B), which is this desync, not TASK-424.
        # Safe because every command here is strictly request/response.
        self.ser.reset_input_buffer()
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


def _put_once(dut: Dut, data: bytes, dest: str, verbose: bool = True):
    """One full upload attempt. Returns (ok, bytes_on_card).

    Checks the device's reported size after EVERY call, not just at the end.
    `cmdSdPut` flushes before reading `f.size()`, so the running size is
    trustworthy -- and since op 'w' truncates (FILE_WRITE is "w"), the expected
    size after each call is simply the number of bytes sent so far. Catching
    drift on the chunk it happens lets us restart the file instead of
    discovering a short upload thousands of calls later.
    """
    # First call truncates (op 'w'), the rest append. An empty file still needs
    # the create call, hence the "-" payload form.
    first = data[:CHUNK] if data else b""
    payload = base64.b64encode(first).decode() if first else "-"
    r = dut.cmd(f"sdput w {payload} {dest}", timeout=20.0)
    if not r.get("ok"):
        print(f"  FAIL {dest}: {r}")
        return False, -1
    sent = len(first)
    if r.get("sizeB", -1) != sent:
        print(f"  DRIFT {dest} after create: card={r.get('sizeB')} expected={sent}")
        return False, r.get("sizeB", -1)
    while sent < len(data):
        block = data[sent:sent + CHUNK]
        r = dut.cmd(f"sdput a {base64.b64encode(block).decode()} {dest}", timeout=20.0)
        if not r.get("ok"):
            print(f"  FAIL {dest} at byte {sent}: {r}")
            return False, -1
        sent += len(block)
        on_card = r.get("sizeB", -1)
        if on_card != sent:
            # The defect this guard exists for: a dropped call the old code
            # accepted because it read a stale ack.
            print(f"  DRIFT {dest} at byte {sent}: card={on_card} expected={sent}")
            return False, on_card
        if verbose and sent % (CHUNK * 50) == 0:
            print(f"    {sent}/{len(data)} B", end="\r", flush=True)
    return True, sent


def put_file(dut: Dut, src: Path, dest: str, verbose: bool = True,
             attempts: int = 3) -> bool:
    """Upload with verification and whole-file retry.

    A retry is safe and self-cleaning: the first call of each attempt is
    `sdput w`, and FILE_WRITE is "w", which truncates.
    """
    data = src.read_bytes()
    final = -1
    for attempt in range(1, attempts + 1):
        ok, final = _put_once(dut, data, dest, verbose)
        if ok and final == len(data):
            suffix = f"  (attempt {attempt})" if attempt > 1 else ""
            print(f"  OK   {dest}  {final}/{len(data)} B{suffix}")
            return True
        if attempt < attempts:
            print(f"  RETRY {dest}: {final}/{len(data)} B "
                  f"(attempt {attempt}/{attempts})")
            time.sleep(1.0)          # let the device drain before restarting
    print(f"  FAIL {dest}: {final}/{len(data)} B after {attempts} attempts")
    return False


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
