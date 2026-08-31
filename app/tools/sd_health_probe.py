#!/usr/bin/env python3
"""sd_health_probe.py — assess the DUT SD card's current filesystem health.

Written for the TASK-548 blocker re-assessment (2026-08-31). TASK-548's remaining
two gaps (T_PLR_25/T_PMT_04) are recorded as "blocked on TASK-424", but TASK-424
is a *sustained single-open* write defect and the fixture uploader
(`sd_put.py`) deliberately uses the short open/write/close burst pattern that
TASK-415 measured as working around it. Before accepting the blocker as stated,
this probe establishes three separate facts:

  1. Is the card readable and is its directory structure intact? (sdls)
  2. Do short-burst writes still work TODAY? (a tiny sdput, the exact pattern
     sd_put.py uses)
  3. Does a write large enough to need many sequential appends still work?
     (the shape a 48944 B MP3 needs, ~544 append calls)

Fact 3 is the one that actually decides whether TASK-548 can be finished
without fixing TASK-424 first.

Read-mostly: the only writes go to /sdhealth.txt, which it removes on the way
out. It does not touch /playlists, /probe200 or /mp3.

Usage:
    python3 tools/sd_health_probe.py --port /dev/ttyUSB0
"""
import argparse
import base64
import functools
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.dut import Dut, SetupFailure, resolve_port  # noqa: E402

print = functools.partial(print, flush=True)

# Deliberately /probebench.bin: it is the one scratch path `sdclean` already
# knows how to remove, so this probe needs no rm command (there is no `sdrm`).
PROBE_PATH = "/probebench.bin"
CHUNK = 90          # same as sd_put.py -- 90 B -> 120 base64 chars, under the 160 B line buffer
APPEND_CALLS = 60   # 60 * 90 = 5400 B; enough to prove the many-append shape without a 9 min run


def drain(dut: Dut, seconds: float, label: str = "") -> list[str]:
    """Collect every raw line for a fixed window. sdls emits one line per entry
    plus a summary, and a panic emits plain-text Guru Meditation lines that a
    JSON-only filter would silently swallow -- we want all of it."""
    lines = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        raw = dut.ser.readline()
        if not raw:
            continue
        line = raw.decode(errors="replace").rstrip("\r\n")
        if not line:
            continue
        lines.append(line)
    return lines


def show(lines: list[str], head: int = 8, tail: int = 4) -> None:
    """Print a bounded view -- sdls /probe200 alone is 200 lines."""
    if len(lines) <= head + tail:
        for ln in lines:
            print(f"  | {ln}")
        return
    for ln in lines[:head]:
        print(f"  | {ln}")
    print(f"  | ... ({len(lines) - head - tail} lines elided) ...")
    for ln in lines[-tail:]:
        print(f"  | {ln}")


def step(dut: Dut, cmd: str, window: float, note: str = "") -> list[str]:
    print(f"\n--- {cmd}{'   # ' + note if note else ''} ---")
    dut.send(cmd)
    lines = drain(dut, window)
    if not lines:
        print("  (NO OUTPUT -- port may have dropped, DUT may be mid-reboot)")
    else:
        show(lines)
    return lines


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=resolve_port())
    args = p.parse_args()

    print(f"Connecting to {args.port}...")
    try:
        dut = Dut(args.port, 115200, timeout=6.0)
    except SetupFailure as e:
        sys.exit(f"[SETUP-FAIL] {e.reason}: {e}")

    try:
        dut.cmd("help", timeout=4.0)
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("PART 1 -- is the card mounted and is its structure intact?")
    print("=" * 70)
    step(dut, "sdmount", 8.0, "expect 'already mounted' -- a read of mount state")
    step(dut, "sdslots", 6.0, "open FIL slots (max_files=3) -- who else holds a handle?")
    step(dut, "sdls / q", 8.0, "root, quiet")
    step(dut, "sdls /playlists", 10.0, "T_PLR fixtures -- expect 7 m3u")
    step(dut, "sdls /probe200 q", 12.0, "expect count 201")
    step(dut, "sdls /mp3", 8.0, "does the mp3 dir exist at all?")
    step(dut, "sdls /mp3/short5", 10.0, "expect 5 tone*.mp3 @ 48944 B if the push ever landed")

    print("\n" + "=" * 70)
    print("PART 2 -- does a SHORT-BURST write still work today?")
    print("   (one open/write/close, the TASK-415 workaround sd_put.py relies on)")
    print("=" * 70)
    payload = base64.b64encode(b"sdhealth probe line 0\n").decode()
    step(dut, f"sdput w {payload} {PROBE_PATH}", 10.0, "truncating create")
    step(dut, "sdls / q", 8.0, "did it appear?")

    print("\n" + "=" * 70)
    print(f"PART 3 -- does a MANY-APPEND write work? ({APPEND_CALLS} x {CHUNK} B)")
    print("   This is the shape a 48944 B MP3 needs (~544 appends). THE decisive test.")
    print("=" * 70)
    blob = base64.b64encode(b"A" * CHUNK).decode()
    bad = 0
    for i in range(APPEND_CALLS):
        dut.send(f"sdput a {blob} {PROBE_PATH}")
        lines = drain(dut, 1.2)
        joined = " ".join(lines)
        # Expected size after i+1 appends on top of the 22 B create.
        expect = 22 + (i + 1) * CHUNK
        ok = '"ok":true' in joined
        sized = f'"sizeB":{expect}' in joined
        if not ok or not sized:
            bad += 1
            print(f"  [append {i + 1:3d}] MISMATCH (expected sizeB={expect})")
            for ln in lines:
                print(f"      | {ln}")
            if bad >= 3:
                print("  -- 3 bad appends, stopping early; the pattern is established")
                break
        elif (i + 1) % 10 == 0:
            print(f"  [append {i + 1:3d}] ok, sizeB={expect}")
        if "Guru Meditation" in joined:
            print("  -- PANIC during append; stopping")
            break

    print("\n--- final state ---")
    step(dut, "sdls / q", 8.0, "final size of the probe file")

    print("\n" + "=" * 70)
    print("PART 4 -- does the data actually READ BACK, or is only the size wrong?")
    print("   THE discriminator. sdput's ack `sizeB` is an f.size() read of the FIL,")
    print("   which cmdSd.cpp's own comment already calls stale. If the bytes are")
    print("   intact and only the reported size is garbage, then TASK-548's MP3")
    print("   push may have actually SUCCEEDED and its verification is what failed.")
    print("   `zeroReads` > 0 would mean genuine data loss; fileB is the real size.")
    print("=" * 70)
    step(dut, f"sdread 200 {PROBE_PATH}", 15.0, "expect fileB=5422, zeroReads=0")
    step(dut, "sdread 200 /playlists/short5.m3u", 15.0,
         "control: a known-good host-era fixture, expect clean")

    print("\n--- cleanup ---")
    step(dut, "sdclean", 12.0, "removes /probebench.bin")

    dut.close()
    print(f"\nDONE. bad appends: {bad}/{APPEND_CALLS}")


if __name__ == "__main__":
    main()
