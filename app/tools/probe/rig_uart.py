#!/usr/bin/env python3
"""probe/rig_uart.py — PROP-011 X-P4 UART transfer matrix driver
(TASK-677/678 H-1).

Cells (PROP-011-runbook.md §3 X-P4):
  * DUT->host: `serialburst` at lines in {2000, 20000} x pad in {8, 64, 200}
    (6 cells). Driven by sending the command through the tmux monitor and
    slicing the resulting log — parsed with the EXISTING checker
    (probe/burst_check.check()), not a second implementation of the wire
    format.
  * host->DUT: `serialsink`. Only the 64 KB cell is implemented — see
    SERIALSINK_1MB_INFEASIBLE below for why the 1 MB cell is not just a slow
    tmux path but actually unreachable on the current firmware.
  * bidirectional: `serialecho 2000` with a generated line set, diffed
    against the echoed E#-prefixed replies.

Every cell reports L (bytes lost/corrupt) and bodTrips; R (host-side
re-enumerations) is a whole-run number from `lib.rigwatch summary`, not
per-cell, since it is a kernel-side count.

Talks to the board ONLY through the tmux monitor (lib.monitor_tmux) — never
opens the serial port. `--dry-run` prints the planned command sequence and
touches nothing; this session only ever ran it that way (the task
instructions ask for that explicitly) — real cell execution and the
achievable serialsink/serialecho rate are for whoever runs it against the
live board next.

    python3 probe/rig_uart.py --dry-run
    python3 probe/rig_uart.py --out /tmp/p4.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Iterable

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from lib import monitor_tmux as mt  # noqa: E402
from lib import rigwatch  # noqa: E402
from probe import burst_check as bc  # noqa: E402

BURST_LINES = (2000, 20000)
BURST_PADS = (8, 64, 200)
#: legacy floor, kept only as the historical constant referenced in comments
#: and tests below — no longer used directly as a timeout.
BURST_TIMEOUT_S = 60.0
#: wire rate in bytes/s at 115200 baud, 8N1.
BURST_BAUD_BPS = 11520.0
#: bytes per emitted line beyond `pad` itself: `#<seq> <pad chars> <csum>\r\n`
#: overhead — 16 per the reviewer's measured-vs-formula reconciliation
#: (TASK-677, 2026-09-11: 20000x64 measured elapsedMs=139663 on the DUT).
BURST_LINE_OVERHEAD_BYTES = 16
#: safety multiplier over the raw wire-time estimate.
BURST_TIMEOUT_MULT = 1.5
#: fixed margin added on top of the scaled estimate.
BURST_TIMEOUT_MARGIN_S = 15.0
#: console is considered idle after this many seconds with no new log bytes.
IDLE_QUIET_S = 1.5
#: how long to wait for the console to go idle before giving up and sending
#: anyway (never block forever on a wedged board).
IDLE_MAX_WAIT_S = 30.0


def burst_timeout_s(lines: int, pad: int) -> float:
    """Pure: how long to wait for a `serialburst <lines> <pad>` cell to print
    its `phase:end` marker. TASK-677 X-P4 run (2026-09-11) found the old
    fixed 60s constant too short for lines=20000 pad=64/200: the cell timed
    out mid-burst while the DUT kept printing, and the next cell's command
    bytes went to a console still busy inside cmdSerialBurst, cascading into
    `began: false` / `no reply` failures for every cell after it (20000x64
    actually finished cleanly at elapsedMs=139663 per the live log — this was
    a driver timing bug, not a link fault). Formula per review:
    `lines*(pad+16)/11520*1.5 + 15`."""
    return lines * (pad + BURST_LINE_OVERHEAD_BYTES) / BURST_BAUD_BPS * \
        BURST_TIMEOUT_MULT + BURST_TIMEOUT_MARGIN_S


def wait_console_idle(quiet_s: float = IDLE_QUIET_S,
                       max_wait_s: float = IDLE_MAX_WAIT_S) -> bool:
    """Block until the tmux log has been silent for `quiet_s` seconds, or
    `max_wait_s` elapses. Cells must never overlap: a command sent while the
    DUT is still mid-print (e.g. still inside cmdSerialBurst) is what turned
    one slow cell into four failed cells in the 2026-09-11 run. Returns True
    if idle was observed, False if it gave up at max_wait_s (still safe to
    proceed — just no longer guaranteed quiet)."""
    deadline = time.monotonic() + max_wait_s
    last_size = mt.size()
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(0.3)
        cur = mt.size()
        if cur != last_size:
            last_size = cur
            last_change = time.monotonic()
        elif time.monotonic() - last_change >= quiet_s:
            return True
    return False

#: cmdSerialSink's own hard deadline (cmdMisc.cpp:377, `deadline = millis() +
#: 10000UL`). At 115200 baud, 8N1, the wire itself moves ~11520 B/s, so the
#: most that deadline can ever admit is ~115 KB — independent of whatever
#: rate tmux can push. The 1 MB cell is therefore not "slow via tmux", it is
#: UNREACHABLE on this firmware: a 1 MB `serialsink` call always ends with
#: `got` capped around 115 KB by the timeout, not by a transport failure.
#: The 921k baud env (F-3) would raise that ceiling to ~1.15 MB/10s, close to
#: viable, but that env needs its own reflash and is out of this session's
#: scope. Only the 64 KB cell is implemented here.
SERIALSINK_BAUD = 115200
SERIALSINK_DEADLINE_S = 10.0
SERIALSINK_MAX_BYTES = int(SERIALSINK_BAUD / 10 * SERIALSINK_DEADLINE_S)  # ~11520 B/s
SERIALSINK_CELL_BYTES = 64 * 1024
#: tmux send-keys -l argv is bounded well under this by the OS anyway; chunk
#: so no single call risks ARG_MAX and so the firmware's read loop (which
#: feeds the TWDT every 512 bytes) sees a steady trickle rather than one
#: giant write.
SERIALSINK_CHUNK_BYTES = 4096
SERIALSINK_1MB_INFEASIBLE = (
    f"serialsink's firmware deadline ({SERIALSINK_DEADLINE_S:.0f}s) caps a single "
    f"call at ~{SERIALSINK_MAX_BYTES} B at {SERIALSINK_BAUD} baud — a 1 MB payload "
    f"cannot complete regardless of how it is fed. Only the 64 KB cell is "
    f"implemented; a 1 MB cell needs the _921k env (F-3), not this driver."
)

ECHO_LINES = 2000
#: tmux send-keys -l with embedded '\n's sends each line without spawning a
#: process per line — this is what keeps 2000+ lines inside serialecho's 30s
#: window (cmdMisc.cpp:436).
ECHO_CHUNK = 200


# ── pure per-cell parsing/decision logic (fixture-tested, no device) ───────

def serialburst_cell(lines: Iterable[str]) -> dict:
    """Wrap burst_check's pure parser into this driver's {L, bodTrips} shape.
    `lines` is any iterable of raw log text lines (a real slice, or a
    fixture) — no device/tmux touched here."""
    r = bc.check(lines)
    # Exact loss in bytes is not recoverable from a lost sequence number
    # alone (the pad width IS known — `pad+1` for the space — but the digit
    # width of the seq number varies), so this is a documented upper bound,
    # not an exact count.
    lost_bytes = len(r.lost()) * (r.pad + 1 + len(str(max(r.lines_declared - 1, 0))))
    return {
        "began": r.began, "ended": r.ended,
        "declared_lines": r.lines_declared, "pad": r.pad,
        "lost": len(r.lost()), "corrupt": len(r.corrupt),
        "duplicates": r.duplicate_count(),
        "L_bytes_upper_bound": lost_bytes,
        "bodTrips": r.bod_trips,
        "ok": r.ok(),
    }


def sink_payload(n: int) -> bytes:
    """Printable ASCII so it survives tmux's own text argv unmangled (a raw
    NUL or control byte through send-keys -l is not guaranteed to round-trip
    through argv/UTF-8 the way a 7-bit printable byte is)."""
    pattern = bytes(range(0x20, 0x7F))  # 95 printable bytes
    reps = n // len(pattern) + 1
    return (pattern * reps)[:n]


def sink_sum8(payload: bytes) -> str:
    return f"{sum(payload) & 0xFFFFFFFF:08x}"


_SINK_REPLY_RE = re.compile(r'\{"probe":"sink"[^\n]*\}')


def serialsink_cell_result(text: str, sent_len: int, sent_sum: str) -> dict:
    """Pure: parse a `serialsink` JSON reply out of a log slice and compare
    against what was actually sent."""
    matches = _SINK_REPLY_RE.findall(text)
    if not matches:
        return {"ok": False, "reply": None, "L_bytes": sent_len,
                "reason": "no serialsink reply found"}
    try:
        obj = json.loads(matches[-1])
    except ValueError:
        return {"ok": False, "reply": None, "L_bytes": sent_len,
                "reason": "malformed serialsink reply"}
    got = obj.get("got", 0)
    L = max(0, sent_len - got)
    sum_ok = (got == sent_len and obj.get("sum") == sent_sum)
    return {"ok": sum_ok, "reply": obj, "L_bytes": L, "sumMatch": sum_ok}


_ECHO_REPLY_RE = re.compile(r"^E#(.*)$")


def serialecho_diff(sent: list, echoed_lines: list) -> dict:
    """Pure: line-for-line diff of what was sent vs what came back E#-prefixed.
    Order-preserving (serialecho's own loop is FIFO), so a missing line is
    detected as soon as the sequences diverge — good enough for this matrix's
    purpose (count loss/corruption, not reorder)."""
    echoed = []
    for line in echoed_lines:
        m = _ECHO_REPLY_RE.match(line.rstrip("\r\n"))
        if m:
            echoed.append(m.group(1))
    mismatches = sum(1 for i in range(min(len(sent), len(echoed)))
                     if sent[i] != echoed[i])
    return {
        "sent": len(sent), "echoed": len(echoed),
        "lost": max(0, len(sent) - len(echoed)),
        "mismatches": mismatches,
        "ok": len(echoed) == len(sent) and mismatches == 0,
    }


# ── device-facing cell runners (tmux only; never called by --dry-run) ─────

def run_burst_cell(lines: int, pad: int) -> dict:
    wait_console_idle()  # never start a cell while the DUT is still printing
    off = mt.size()
    rigwatch.stamp("note", phase="X-P4-burst", lines=str(lines), pad=str(pad))
    mt.send(f"serialburst {lines} {pad}")
    deadline = time.monotonic() + burst_timeout_s(lines, pad)
    text = ""
    while time.monotonic() < deadline:
        time.sleep(0.5)
        text = mt.read_from(off)
        if '"probe":"burst","phase":"end"' in text:
            break
    wait_console_idle()  # let any trailing bytes drain before the next cell
    return serialburst_cell(text.splitlines())


def run_sink_cell(n_bytes: int = SERIALSINK_CELL_BYTES) -> dict:
    wait_console_idle()
    payload = sink_payload(n_bytes)
    sent_sum = sink_sum8(payload)
    off = mt.size()
    rigwatch.stamp("note", phase="X-P4-sink", bytes=str(n_bytes))
    mt.send(f"serialsink {n_bytes}")
    time.sleep(0.5)
    for i in range(0, len(payload), SERIALSINK_CHUNK_BYTES):
        chunk = payload[i:i + SERIALSINK_CHUNK_BYTES].decode("ascii")
        mt.send_literal(chunk)
    time.sleep(SERIALSINK_DEADLINE_S + 1.0)
    text = mt.read_from(off)
    wait_console_idle()
    return serialsink_cell_result(text, n_bytes, sent_sum)


def run_echo_cell(n_lines: int = ECHO_LINES) -> dict:
    wait_console_idle()
    sent = [f"echo-line-{i:06d}" for i in range(n_lines)]
    off = mt.size()
    rigwatch.stamp("note", phase="X-P4-echo", lines=str(n_lines))
    mt.send(f"serialecho {n_lines}")
    time.sleep(0.5)
    for i in range(0, len(sent), ECHO_CHUNK):
        chunk = "\n".join(sent[i:i + ECHO_CHUNK]) + "\n"
        mt.send_literal(chunk)
    time.sleep(5.0)
    text = mt.read_from(off)
    wait_console_idle()
    return serialecho_diff(sent, text.splitlines())


def _dry_run() -> None:
    print("[dry-run] serialburst cells (DUT->host):")
    for lines in BURST_LINES:
        for pad in BURST_PADS:
            print(f"[dry-run]   send: serialburst {lines} {pad}  "
                 f"then slice log, burst_check.check() it")
    print(f"[dry-run] serialsink cells (host->DUT): only {SERIALSINK_CELL_BYTES} B "
         f"({SERIALSINK_CELL_BYTES // 1024} KB) — 1 MB cell SKIPPED:")
    print(f"[dry-run]   {SERIALSINK_1MB_INFEASIBLE}")
    print(f"[dry-run]   send: serialsink {SERIALSINK_CELL_BYTES}, then feed "
         f"{SERIALSINK_CELL_BYTES} bytes via chunked tmux send-keys -l "
         f"({SERIALSINK_CHUNK_BYTES} B/chunk)")
    print(f"[dry-run] serialecho cell: send: serialecho {ECHO_LINES}, then feed "
         f"{ECHO_LINES} lines in chunks of {ECHO_CHUNK} via tmux send-keys -l, diff replies")
    print("[dry-run] at the end: lib.rigwatch summarize() for whole-run R")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="append one JSON line per cell here too")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.dry_run:
        _dry_run()
        return 0

    out_fh = open(a.out, "a", encoding="utf-8") if a.out else None
    try:
        results = []
        for lines in BURST_LINES:
            for pad in BURST_PADS:
                r = run_burst_cell(lines, pad)
                r["cell"] = f"burst lines={lines} pad={pad}"
                results.append(r)

        r = run_sink_cell(SERIALSINK_CELL_BYTES)
        r["cell"] = f"sink bytes={SERIALSINK_CELL_BYTES}"
        results.append(r)
        print(f"skipped 1 MB sink cell: {SERIALSINK_1MB_INFEASIBLE}")

        r = run_echo_cell(ECHO_LINES)
        r["cell"] = f"echo lines={ECHO_LINES}"
        results.append(r)

        for r in results:
            line = json.dumps(r)
            print(line)
            if out_fh:
                out_fh.write(line + "\n")

        summ = rigwatch.summarize(time.time() - 3600)
        print(f"\nwhole-run R (reenum, last hour): {summ['reenum']}")
    finally:
        if out_fh:
            out_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
