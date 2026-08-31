#!/usr/bin/env python3
"""task424_sdwrite_repro.py — fresh live reproduction of TASK-424's SD write panic.

Not a registered T_ id (this is a raw repro/diagnostic probe, not a regression
test). Connects to an already-debug-flashed DUT and re-runs the exact chunk
counts TASK-424's own re-characterisation table used (64/256/512/1024/2048),
via the `sdclean`/`sdwrite` debug console commands, to get a fresh, live data
point before any fix attempt — per this project's own "measure fresh, don't
trust stale numbers" discipline.

Usage:
    python3 tools/task424_sdwrite_repro.py --port /dev/ttyUSB0
"""
import argparse
import functools
import pathlib
import sys
import time

print = functools.partial(print, flush=True)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.dut import Dut, SetupFailure, resolve_port  # noqa: E402

CHUNK_COUNTS = [64, 256, 512, 1024, 2048]


def read_raw_for(dut: Dut, seconds: float) -> list[str]:
    """Print+collect every raw line for a fixed window — sdwrite emits several
    JSON lines per call (opened/shortWrite/heapCorrupt/ok), and a real panic
    emits plain-text Guru Meditation / backtrace lines that read_json's
    JSON-only filter would silently swallow. We want to see all of it."""
    lines = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        raw = dut.ser.readline()
        if not raw:
            continue
        line = raw.decode(errors="replace").rstrip("\r\n")
        if not line:
            continue
        print(f"  | {line}", flush=True)
        lines.append(line)
    return lines


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=resolve_port())
    args = p.parse_args()

    print(f"Connecting to {args.port}…", flush=True)
    try:
        dut = Dut(args.port, 115200, timeout=6.0)
    except SetupFailure as e:
        sys.exit(f"[SETUP-FAIL] {e.reason}: {e}")

    try:
        dut.cmd("help", timeout=4.0)
    except Exception:
        pass

    for n in CHUNK_COUNTS:
        # TASK-424, 2026-08-27 finding: `sdwrite`'s FILE_WRITE open mode does
        # NOT truncate — startSizeB grows across successive calls in the same
        # boot unless the fixture is removed first. Without this, later
        # trials run against leftover (possibly already-corrupted) state from
        # the previous trial, and results aren't comparable across chunk
        # counts. sdclean before EVERY trial, not once per session.
        print(f"\n--- sdclean (before sdwrite {n}) ---")
        dut.send("sdclean")
        read_raw_for(dut, 8.0)

        print(f"\n--- sdwrite {n} ---")
        dut.send(f"sdwrite {n}")
        # 2048 chunks * 512B at the historical ~1.2 MB/s is well under a
        # second; the window is generous because a panic-triggered reboot
        # prints its own boot banner over several seconds, and that banner
        # (or its absence) is itself diagnostic.
        lines = read_raw_for(dut, 15.0)
        if not lines:
            print("  (no output at all in the window — port likely dropped, "
                  "DUT may be mid-reboot)")

    dut.close()


if __name__ == "__main__":
    main()
