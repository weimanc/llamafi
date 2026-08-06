#!/usr/bin/env python3
"""TASK-402 (M-WEBRADIO-POSBAR-SMOOTH) OQ1/OQ2 data collection: trace
`get wrPosbar` (bufPctRaw/bufPctSmoothed/redraws/lastSkipReason) at high
poll rate across several real stations, to characterize the oscillation a
human eyeball reported live on the physical LCD (~4 visible changes/sec on
SLAM!) before proposing a real smoothing-constant fix. Ad hoc script, not
added to the automated run_serialdbg_tests.py suite, same convention as
task399_402_dut_verify.py / task400_401_dut_verify.py.

Writes one CSV per station to rnd_logs/task402_trace_<ts>/<station>.csv with
columns: t_s,bufPctRaw,bufPctSmoothed,bufPctDrawn,redraws,lastSkipReason.
Analysis (period/amplitude/proposed filter) is done separately, on-host,
against these CSVs -- this script only collects.

Usage: python3 task402_posbar_trace.py [--port /dev/ttyUSB0] [--stations 5]
       [--window 45]
"""
import sys
import csv
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_serialdbg_tests import (  # noqa: E402
    Dut, _ensure_webradio, _webradio_enter_with_stations, _wait_wr_state,
)

WR_STATE_PLAYING = 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--stations", type=int, default=5)
    ap.add_argument("--window", type=float, default=45.0,
                     help="seconds of wrPosbar polling per station")
    ap.add_argument("--include-name", default=None,
                     help="substring match -- force this station into the "
                          "selection (e.g. the exact station a human is "
                          "watching live) in addition to the spread picks")
    args = ap.parse_args()

    out_dir = (Path(__file__).resolve().parent / "rnd_logs"
               / f"task402_trace_{datetime.now().strftime('%Y%m%dT%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)

    dut = Dut(args.port, log_file=str(out_dir / "raw.log"))

    entered = _ensure_webradio(dut, "trace-setup")
    if not entered:
        print("FATAL: could not enter WebRadio")
        dut.close()
        sys.exit(1)

    station_count = _webradio_enter_with_stations(dut, "trace-setup", fetch_timeout=180.0)
    if station_count < 1:
        print("FATAL: no stations loaded")
        dut.close()
        sys.exit(1)
    print(f"[setup] {station_count} stations loaded")

    # Pick up to N stations spread across the loaded list (index diversity ->
    # bitrate/mirror diversity), not just the first N.
    n = min(args.stations, station_count)
    idxs = sorted({round(i * (station_count - 1) / max(1, n - 1)) for i in range(n)})
    if args.include_name:
        for i in range(station_count):
            r = dut.cmd(f"get wrStation {i}", timeout=3.0)
            if args.include_name.lower() in (r.get("name") or "").lower():
                idxs = sorted(set(idxs) | {i})
                print(f"  [include-name] matched idx={i} name={r.get('name')!r}")
                break
    stations = []
    for idx in idxs:
        r = dut.cmd(f"get wrStation {idx}", timeout=3.0)
        stations.append((idx, r.get("name", f"idx{idx}"), r.get("bitrate")))
        print(f"  [{idx}] {r.get('name')} bitrate={r.get('bitrate')}")

    manifest = []
    for idx, name, bitrate in stations:
        safe_name = "".join(c if c.isalnum() else "_" for c in name)[:40]
        print(f"\n=== station idx={idx} name={name!r} bitrate={bitrate} ===")
        r_play = dut.cmd(f"set wrPlay {idx}", timeout=3.0)
        if not r_play.get("ok"):
            print(f"  [SKIP] set wrPlay {idx} failed: {r_play}")
            manifest.append({"idx": idx, "name": name, "bitrate": bitrate,
                              "playing": False, "samples": 0})
            continue
        playing = _wait_wr_state(dut, WR_STATE_PLAYING, timeout=25.0)
        if not playing:
            print(f"  [SKIP] never reached PLAYING for idx={idx}")
            manifest.append({"idx": idx, "name": name, "bitrate": bitrate,
                              "playing": False, "samples": 0})
            continue
        # Let the buffer settle past the connect-time fill transient
        # (TASK-266's WR_SETTLED_MS precedent) before recording -- otherwise
        # the trace opens on a monotonic fill ramp, not steady-state jitter.
        time.sleep(3.0)

        rows = []
        t0 = time.monotonic()
        deadline = t0 + args.window
        poll_n = 0
        last_state = None
        while time.monotonic() < deadline:
            t_sample = time.monotonic()
            r = dut.cmd("get wrPosbar", timeout=2.0)
            # wrState (CONNECTING vs PLAYING vs ERROR_*) matters more than
            # jitter here: _play() force-resets _bufPct=0 on every reconnect
            # attempt and the smoothing recompute only runs while PLAYING, so
            # a raw reading of 0 can mean "genuinely empty buffer" or "not
            # playing at all right now" -- indistinguishable without this.
            # Polled every 5th sample (not every sample) to keep the wrPosbar
            # poll rate high, since state changes far slower than buffer %.
            poll_n += 1
            if poll_n % 5 == 1:
                rs = dut.cmd("get wrState", timeout=2.0)
                last_state = rs.get("state")
            if r.get("ok"):
                rows.append({
                    "t_s": round(t_sample - t0, 4),
                    "bufPctRaw": r.get("bufPctRaw"),
                    "bufPctSmoothed": r.get("bufPctSmoothed"),
                    "bufPctDrawn": r.get("bufPctDrawn"),
                    "redraws": r.get("redraws"),
                    "lastSkipReason": r.get("lastSkipReason"),
                    "wrState": last_state,
                })
            # No fixed sleep -- back-to-back polling gets the highest
            # sample rate the serial round-trip allows (measured, not
            # assumed, in the CSV's own t_s deltas).

        csv_path = out_dir / f"{idx:02d}_{safe_name}.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["t_s", "bufPctRaw", "bufPctSmoothed",
                                               "bufPctDrawn", "redraws", "lastSkipReason",
                                               "wrState"])
            w.writeheader()
            w.writerows(rows)
        print(f"  {len(rows)} samples over {rows[-1]['t_s'] if rows else 0:.1f}s -> {csv_path}")
        manifest.append({"idx": idx, "name": name, "bitrate": bitrate,
                          "playing": True, "samples": len(rows), "csv": csv_path.name})

    dut.close()

    print("\n=== manifest ===")
    for m in manifest:
        print(m)
    (out_dir / "manifest.txt").write_text("\n".join(str(m) for m in manifest) + "\n")
    print(f"\nAll data in {out_dir}")


if __name__ == "__main__":
    main()
