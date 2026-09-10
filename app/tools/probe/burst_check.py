#!/usr/bin/env python3
"""probe/burst_check.py — host checker for the firmware's `serialburst`
console command (TASK-557/PROP-011 §5 P0/§3 item). Re-committed per the P0
punch list: "the host checker was never committed" (PROP-011 §2 UART row).

WHAT `serialburst` EMITS (app/src/debug/serialConsole/cmdMisc.cpp:cmdSerialBurst,
line ~278). One JSON `begin` line, N data lines, one JSON `end` line:

    {"probe":"burst","phase":"begin","lines":N,"pad":P,"thres":T,"t":MS}
    #<seq> <pad-chars-of-'A'> <sum8hex>
    ...
    {"probe":"burst","phase":"end","lines":N,"elapsedMs":MS,"bodTrips":B,
     "firstTripSeq":S,"thres":T}

The data-line checksum is `sum(seq) + sum(each pad byte as uint8)`, printed as
8 lowercase hex digits — see `cmdSerialBurst`'s own `Serial.printf("#%d %s
%08x\n", i, buf, (unsigned)sum)`.

WHAT THIS CHECKS. Sequence continuity (0..lines-1, no gaps, no repeats) and
checksum correctness per line, tolerating INTERLEAVED lines from other tasks
(loop() keeps running background printfs while this blocks it, per the
firmware comment — actually the burst blocks loop() for its own duration, but
console echo / a straggling log line from before the command was issued can
still land in the stream ahead of `begin`). A line that does not match either
the data-line shape or a JSON probe line is skipped, not counted as a loss —
only a sequence number that is truly MISSING (never seen) counts as lost.

No DUT is required to TEST this module (see probe/test_burst_check.py) — the
checker is a pure function over a line iterator, fed either from a live `Dut`
session (--port) or from a recorded transcript file (--fixture, one line per
file line, for the device-free negative suite and for replaying a captured
session at review time).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

_BEGIN_RE = re.compile(r'^\{"probe":"burst","phase":"begin"')
_END_RE = re.compile(r'^\{"probe":"burst","phase":"end"')
#: pad is always 'A' bytes on the wire (cmdSerialBurst memset's it), but a
#: transport bit-flip can turn one into anything — match any non-space run so
#: such a line is still recognized as a DATA line (and therefore checked for
#: checksum correctness) rather than silently falling through to "missing".
_DATA_RE = re.compile(r'^#(\d+) (\S+) ([0-9a-f]{8})$')


@dataclass
class BurstResult:
    lines_declared: int = 0
    pad: int = 0
    seen: set = field(default_factory=set)
    corrupt: list = field(default_factory=list)   # [(seq, expected, got)]
    began: bool = False
    ended: bool = False
    elapsed_ms: Optional[int] = None
    bod_trips: Optional[int] = None
    first_trip_seq: Optional[int] = None

    def lost(self) -> list:
        if not self.lines_declared:
            return []
        want = set(range(self.lines_declared))
        return sorted(want - self.seen)

    def duplicate_count(self) -> int:
        # self.seen is a set, so duplicates are not directly observable from it
        # alone; _dup_count tracks the raw count separately (see check()).
        return getattr(self, "_dup_count", 0)

    def ok(self) -> bool:
        return (self.began and self.ended and not self.lost()
               and not self.corrupt and self.duplicate_count() == 0)


def _checksum(seq: int, pad_chars: str) -> int:
    total = seq & 0xFFFFFFFF
    for ch in pad_chars:
        total += ord(ch) & 0xFF
    return total & 0xFFFFFFFF


def check(lines: Iterable[str]) -> BurstResult:
    """Pure: consumes an iterable of raw serial lines (already decoded text,
    no trailing newline required either way) and returns a BurstResult.
    Never raises on malformed input — a burst that cut off mid-stream (a
    disconnect) is exactly the failure mode this exists to report, not crash
    on."""
    r = BurstResult()
    dup = 0
    seq_count: dict = {}
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        if _BEGIN_RE.match(line):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            r.began = True
            r.lines_declared = int(obj.get("lines") or 0)
            r.pad = int(obj.get("pad") or 0)
            continue
        if _END_RE.match(line):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            r.ended = True
            r.elapsed_ms = obj.get("elapsedMs")
            r.bod_trips = obj.get("bodTrips")
            r.first_trip_seq = obj.get("firstTripSeq")
            continue
        m = _DATA_RE.match(line)
        if not m:
            # Neither a begin/end JSON line nor a well-formed data line —
            # interleaved chatter from another task. Skip, do not count loss.
            continue
        seq = int(m.group(1))
        pad_chars = m.group(2)
        got_sum = m.group(3)
        seq_count[seq] = seq_count.get(seq, 0) + 1
        if seq_count[seq] > 1:
            dup += 1
        want_sum = f"{_checksum(seq, pad_chars):08x}"
        if want_sum != got_sum:
            r.corrupt.append((seq, want_sum, got_sum))
        r.seen.add(seq)
    r._dup_count = dup
    return r


def format_report(r: BurstResult) -> str:
    lost = r.lost()
    lines = [
        f"burst_check: began={r.began} ended={r.ended} "
        f"declared_lines={r.lines_declared} pad={r.pad}",
        f"  seen={len(r.seen)} lost={len(lost)} corrupt={len(r.corrupt)} "
        f"duplicates={r.duplicate_count()}",
    ]
    if lost:
        preview = lost[:20]
        lines.append(f"  lost seq (first 20 of {len(lost)}): {preview}")
    if r.corrupt:
        for seq, want, got in r.corrupt[:20]:
            lines.append(f"  corrupt seq={seq}: expected {want}, got {got}")
        if len(r.corrupt) > 20:
            lines.append(f"  ... {len(r.corrupt) - 20} more corrupt line(s)")
    if r.ended:
        lines.append(f"  elapsedMs={r.elapsed_ms} bodTrips={r.bod_trips} "
                     f"firstTripSeq={r.first_trip_seq}")
    lines.append(f"  RESULT: {'PASS' if r.ok() else 'FAIL'}")
    return "\n".join(lines)


# ── entry point (device or fixture) ─────────────────────────────────────────

def _from_fixture(path: str):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            yield line


def _from_device(port: str, lines: int, pad: int, timeout_s: float):
    """Drive a real DUT. Imported lazily — this function is never called by
    the test suite, so lib.dut (which imports pyserial) never has to be
    importable for `probe/test_burst_check.py` to pass."""
    import time as _time

    from lib.dut import Dut, resolve_port

    dut = Dut(resolve_port(port))
    try:
        dut.ser.reset_input_buffer()
        dut.ser.write(f"serialburst {lines} {pad}\n".encode())
        dut.ser.flush()
        deadline = _time.monotonic() + timeout_s
        seen_end = False
        while _time.monotonic() < deadline:
            raw = dut.ser.readline()
            if not raw:
                continue
            text = raw.decode(errors="replace")
            yield text
            if _END_RE.match(text.strip()):
                seen_end = True
                break
        if not seen_end:
            print(f"  [burst_check] WARN: no end-of-burst line within "
                 f"{timeout_s:.0f}s — stream may have been cut short",
                 file=sys.stderr)
    finally:
        dut.close()


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", help="a captured transcript file, one raw "
                    "serial line per text line (device-free)")
    ap.add_argument("--port", help="drive a live DUT instead of a fixture")
    ap.add_argument("--lines", type=int, default=2000)
    ap.add_argument("--pad", type=int, default=64)
    ap.add_argument("--timeout", type=float, default=60.0)
    a = ap.parse_args(argv)

    if a.fixture:
        r = check(_from_fixture(a.fixture))
    elif a.port is not None or a.port == "":
        r = check(_from_device(a.port, a.lines, a.pad, a.timeout))
    else:
        ap.error("pass --fixture <file> or --port <device>")
        return 2

    print(format_report(r))
    return 0 if r.ok() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
