#!/usr/bin/env python3
"""ceefax_reconnect_observer.py — DS-7 data-gathering spike (M-CEEFAX).

Long-running (hours), host-only, no DUT/firmware involved. Holds a single
CeefaxClient connection open on one page and logs every status transition
with a timestamp, to build a real distribution of connection-drop frequency
and outage duration instead of guessing a hasError() sustained-failure
threshold.

Usage:
    python3 tools/ceefax_reconnect_observer.py [page] [--log PATH] [--hours N]

Writes one JSON line per status transition to the log file (default:
ceefax_reconnect_log.jsonl next to this script), flushed immediately so a
kill -9 or crash mid-run doesn't lose data already collected. Ctrl-C (or the
--hours deadline) stops it and prints a summary: total outage count, outage
duration distribution, longest single outage, and time-to-first-acquire.

What counts as an "outage" here: any span where status stops being
"acquired page N" (i.e. connecting/reconnecting/closed/error), bounded by
the previous and next "acquired" transitions. A single 3s-backoff reconnect
that succeeds on the first retry is still logged as an outage — the point
of this script is to produce the raw distribution, not to pre-judge what
counts as "sustained". That judgement call happens when reading the summary,
not in the logging.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ceefax_client import CeefaxClient

DEFAULT_LOG = pathlib.Path(__file__).parent / "ceefax_reconnect_log.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", nargs="?", type=int, default=100)
    ap.add_argument("--log", type=pathlib.Path, default=DEFAULT_LOG)
    ap.add_argument("--hours", type=float, default=None,
                     help="stop after this many hours (default: run until Ctrl-C)")
    args = ap.parse_args()

    start_wall = time.time()
    start_mono = time.monotonic()
    deadline = (start_mono + args.hours * 3600) if args.hours else None

    client = CeefaxClient(page=args.page)
    client.start()

    outages = []          # list of (start_mono, end_mono) for each non-acquired span
    outage_start = start_mono   # we start "not acquired"
    first_acquire_at = None
    last_status = None
    events = 0

    print(f"Observing page {args.page}, logging to {args.log}")
    print("Ctrl-C to stop and print summary.\n")

    with open(args.log, "a", buffering=1) as logf:
        try:
            while True:
                now_mono = time.monotonic()
                if deadline and now_mono >= deadline:
                    print("--hours deadline reached")
                    break

                _content, _dirty, status, acquired, _flof = client.snapshot()

                if status != last_status:
                    elapsed = now_mono - start_mono
                    rec = {
                        "t": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                        "elapsed_s": round(elapsed, 1),
                        "status": status,
                        "acquired": acquired,
                    }
                    logf.write(json.dumps(rec) + "\n")
                    events += 1

                    if acquired and first_acquire_at is None:
                        first_acquire_at = elapsed
                        outages.append((outage_start, now_mono))
                        print(f"[{elapsed:7.1f}s] FIRST ACQUIRE  (outage {now_mono - outage_start:.1f}s)")
                    elif acquired and last_status is not None and not _was_acquired(last_status):
                        outages.append((outage_start, now_mono))
                        print(f"[{elapsed:7.1f}s] REACQUIRED     (outage {now_mono - outage_start:.1f}s)  status={status}")
                    elif not acquired and (last_status is None or _was_acquired(last_status)):
                        outage_start = now_mono
                        print(f"[{elapsed:7.1f}s] LOST           status={status}")

                    last_status = status

                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nInterrupted.")
        finally:
            client.stop()

    total_wall = time.time() - start_wall
    print(f"\n--- summary over {total_wall/3600:.2f}h, {events} status transitions ---")
    if first_acquire_at is not None:
        print(f"time to first acquire: {first_acquire_at:.1f}s")
    if outages:
        durations = sorted(e - s for s, e in outages)
        print(f"outages logged: {len(outages)}")
        print(f"  min: {durations[0]:.1f}s  median: {durations[len(durations)//2]:.1f}s  "
              f"max: {durations[-1]:.1f}s")
        print(f"  all: {[round(d, 1) for d in durations]}")
    else:
        print("no outages observed")


def _was_acquired(status: str) -> bool:
    return status.startswith("acquired")


if __name__ == "__main__":
    main()
