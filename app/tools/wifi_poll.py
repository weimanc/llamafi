#!/usr/bin/env python3
"""
wifi_poll — lightweight link-state poller, NO promiscuous beacon watcher.

Companion to wifi_watch.py. That tool arms esp_wifi_set_promiscuous (the
TASK-282 beacon watcher), which on the ESP32 interferes with the STA
scan/reconnect state machine — turning a brief antenna fade into a long
NO_AP_FOUND reconnect storm (observed 2026-07-03: DUT couldn't rejoin an AP
the host saw strong+present for 97 s while promiscuous was on). This tool
explicitly turns the watcher OFF and only polls `get wifi`, so the measured
reconnect behaviour is the production one (production never enables the watcher).

Usage:
  python3 app/tools/wifi_poll.py --port $(./run/port) --hours 4 --log poll.log
"""
from __future__ import annotations
import argparse, json, time
from wifi_watch import WatchDut, note, poll_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB1")
    p.add_argument("--hours", type=float, default=4.0)
    p.add_argument("--log", default="wifi_poll.log")
    p.add_argument("--interval", type=float, default=30.0)
    args = p.parse_args()

    d = WatchDut(args.port, 115200, timeout=3.0)
    logf = open(args.log, "a")
    note(logf, f"poll start (NO beacon watcher), {args.hours}h")
    r = poll_json(d, "set beaconWatch 0")
    note(logf, f"beaconWatch OFF: {json.dumps(r)}")

    down_since = None
    end = time.monotonic() + args.hours * 3600
    while time.monotonic() < end:
        # passive drain between polls keeps [wifi-ev]/[wifi-sup] lines in the log
        dl = time.monotonic() + args.interval
        d.ser.timeout = 0.5
        while time.monotonic() < dl:
            line = d.ser.readline().decode(errors="replace").strip()
            if line:
                logf.write(line + "\n")
        logf.flush()
        d.ser.timeout = 3.0
        w = poll_json(d, "get wifi")
        st = w.get("status", -1)
        note(logf, f"poll status={st} rssi={w.get('rssi')} disc={w.get('discCount')} "
                   f"reason={w.get('lastDiscReason')} kicks={w.get('kicks')}")
        if st == 3 and down_since is not None:
            note(logf, f"RECOVERED after {time.monotonic()-down_since:.0f}s down")
            down_since = None
        elif st != 3 and down_since is None:
            down_since = time.monotonic()
            note(logf, f"LINK DOWN reason={w.get('lastDiscReason')}")
    note(logf, "poll complete")
    d.close(); logf.close()


if __name__ == "__main__":
    main()
