#!/usr/bin/env python3
"""
wifi_watch — TASK-282 (M-WIFI-DIAG Phase 2) instrument validation + storm catcher.

Phase 1 (validation, ~20 s): enable the beacon watcher, confirm beacons are
being counted at ~10/s with sane RSSI/noise-floor, confirm async scan works.

Phase 2 (watch): sit on the port logging every line to --log. Every 60 s poll
`get beacon` + `get wifi`. Storm protocol (automated §5 evidence collection):
  - link down (status != 3) for > 120 s:
      1. fire `set wifiScan 1`, poll `get wifiScan`  -> is the BSSID on air?
      2. read `get beacon`                            -> did beacons stop at the antenna?
      3. after +60 s more down: one `set wifiDisc`    -> does a manual re-kick
         recover the TASK-283 park-dead wedge that auto-reconnect can't?
  - all findings printed as single "[watch]" lines (stdout + log) for the
    monitor to surface.

Usage:
  python3 app/tools/wifi_watch.py --port $(./run/port) --hours 4 \
      --log scratch/wifi_watch.log
"""

from __future__ import annotations

import argparse
import json
import time

from run_serialdbg_tests import Dut


class WatchDut(Dut):
    """Dut without the WiFi-up ready gate.

    The stock gate refuses to start against a disconnected DUT — correct for
    VE suites, wrong here: this tool's whole job is observing a DUT whose WiFi
    is down (storm/park-dead states). Readiness = serial responds to a debug
    command; link state is data, not a precondition.
    """

    def _wait_for_ready(self, _recovery_attempt: int = 0):
        deadline = time.monotonic() + 90.0
        self.ser.timeout = 0.5
        while time.monotonic() < deadline:
            self.ser.reset_input_buffer()
            self.send("get wifi")
            t_probe = time.monotonic()
            while time.monotonic() - t_probe < 3.0:
                line = self.ser.readline().decode(errors="replace").strip()
                if line.startswith("{") and '"var":"wifi"' in line.replace(" ", ""):
                    # Drain any late replies from earlier probes — a stale JSON
                    # left buffered here shifts every later cmd/reply pairing
                    # by one (observed 2026-07-03: get beacon read the
                    # beaconWatch ack; LL-042 class).
                    time.sleep(0.6)
                    self.ser.reset_input_buffer()
                    return
            time.sleep(2.0)
        raise RuntimeError("DUT serial not responding to debug commands")

    def _verify_debug_firmware(self):
        pass  # _wait_for_ready above already proved the SERIAL_DEBUG surface


def note(logf, msg: str):
    line = f"[watch] t={time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


def poll_json(d: Dut, cmd: str, timeout: float = 5.0) -> dict:
    """Send cmd; read JSON lines until one matches THIS command (drops stale
    replies instead of pairing off-by-one — the failure mode that broke the
    first validation run)."""
    want_var = cmd.split()[1] if " " in cmd else cmd
    try:
        d.send(cmd)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            r = d.read_json(max(0.5, deadline - time.monotonic()))
            if r.get("var") == want_var or r.get("cmd") == want_var:
                return r
        return {"error": f"no matching reply for {cmd}"}
    except Exception as e:
        return {"error": str(e)}


def drain_to_log(d: Dut, logf, seconds: float):
    deadline = time.monotonic() + seconds
    d.ser.timeout = 0.5
    while time.monotonic() < deadline:
        line = d.ser.readline().decode(errors="replace").strip()
        if line:
            logf.write(line + "\n")
    logf.flush()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB1")
    p.add_argument("--hours", type=float, default=4.0)
    p.add_argument("--log", default="wifi_watch.log")
    args = p.parse_args()

    d = WatchDut(args.port, 115200, timeout=3.0)
    logf = open(args.log, "a")
    note(logf, f"session start, {args.hours}h watch")

    # ── Phase 1: instrument validation ────────────────────────────────────────
    # beaconWatch needs an associated STA to lock the BSSID; wait for link-up
    # if the DUT booted into a storm (this tool must start either way).
    w = poll_json(d, "get wifi")
    note(logf, f"wifi: {json.dumps(w)}")
    wait_deadline = time.monotonic() + 600
    while w.get("status") != 3 and time.monotonic() < wait_deadline:
        note(logf, f"link not up (status={w.get('status')}) — waiting to arm beaconWatch")
        drain_to_log(d, logf, 30.0)
        d.ser.timeout = 3.0
        w = poll_json(d, "get wifi")
    r = poll_json(d, "set beaconWatch 1")
    note(logf, f"beaconWatch start: {json.dumps(r)}")
    time.sleep(10)
    b0 = poll_json(d, "get beacon")
    note(logf, f"beacon after 10s: {json.dumps(b0)}")
    ok = b0.get("count", 0) > 50  # ~10/s at 102.4 ms interval
    note(logf, f"VALIDATION beacon-rate: {'PASS' if ok else 'FAIL'} (count={b0.get('count')})")
    poll_json(d, "set wifiScan 1")
    time.sleep(6)
    s = poll_json(d, "get wifiScan", 8.0)
    note(logf, f"VALIDATION scan: total={s.get('total')} matches={json.dumps(s.get('matches'))}")

    # ── Phase 2: storm watch ──────────────────────────────────────────────────
    down_since = None
    scanned = False
    rekicked = False
    end = time.monotonic() + args.hours * 3600
    while time.monotonic() < end:
        drain_to_log(d, logf, 30.0)
        d.ser.timeout = 3.0
        w = poll_json(d, "get wifi")
        b = poll_json(d, "get beacon")
        status = w.get("status", -1)
        note(logf, f"poll status={status} rssi={w.get('rssi')} disc={w.get('discCount')} "
                   f"reason={w.get('lastDiscReason')} beacons={b.get('count')} "
                   f"gapMax={b.get('gapMaxMs')} gaps1s={b.get('gapsOver1s')} "
                   f"lastAgo={b.get('lastAgoMs')} nf={b.get('noiseFloor')} "
                   f"otherMgmt={b.get('otherMgmt')}")
        if status == 3:
            if down_since is not None:
                note(logf, f"RECOVERED after {time.monotonic()-down_since:.0f}s down "
                           f"(rekick={'yes' if rekicked else 'no'})")
            down_since, scanned, rekicked = None, False, False
            continue
        # link down
        if down_since is None:
            down_since = time.monotonic()
            note(logf, f"LINK DOWN detected reason={w.get('lastDiscReason')} — storm protocol armed")
        downtime = time.monotonic() - down_since
        if downtime > 60 and not scanned:
            poll_json(d, "set wifiScan 1")
            time.sleep(6)
            s = poll_json(d, "get wifiScan", 8.0)
            note(logf, f"STORM-EVIDENCE scan@{downtime:.0f}s: total={s.get('total')} "
                       f"matches={json.dumps(s.get('matches'))}")
            note(logf, f"STORM-EVIDENCE beacon@{downtime:.0f}s: {json.dumps(b)}")
            scanned = True
        if downtime > 120 and not rekicked:
            note(logf, f"REKICK attempting set wifiDisc at {downtime:.0f}s down (TASK-283 probe)")
            poll_json(d, "set wifiDisc 1")
            rekicked = True

    note(logf, "watch complete")
    d.close()
    logf.close()


if __name__ == "__main__":
    main()
