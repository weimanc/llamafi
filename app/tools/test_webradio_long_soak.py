#!/usr/bin/env python3
"""Long single-station WebRadio soak — TASK-393 recurrence watch.

Plays ONE real station for an extended duration, mirroring the original
human report's usage pattern ("had been playing for an extended, unmeasured
duration"). This is deliberately NOT test_webradio_soak.py's arena-churn
soak (TASK-271) — that one forcibly leaves+re-enters WebRadio every ~25s,
which would mask a station getting stuck in a parked ERROR_* state forever
(exactly TASK-393's symptom). Here the firmware's own terminal-retry
(TASK-276) is left to run in place, on the same station, for hours.

Every poll interval, reads `get wrState` and derives whether the app is
"stuck": in one of the retryable error states (ERROR_WIFI/ERROR_STALL/
ERROR_UNREACHABLE) for longer than WR_TERMINAL_RETRY_MS + slack with no
observable recovery (no state change, no wrIdx/wrSkip.tried movement). If
that fires, it's the TASK-393 signature recurring — immediately dumps full
debug state (wrState/wrIcy/wrIdx/wrSkip/heap/stacks/info) to a timestamped
report and keeps running (a later recovery, or the run ending still stuck,
both get captured too). This is the instrumentation-at-the-moment TASK-393
kept missing every time it was observed live.

Runs against whatever debug build (SERIAL_DEBUG) is currently flashed —
does not flash anything itself. Point it at cyd2usb_winamp_debug (Spotify
present, matching the actual TASK-390/393 environment) for the most
representative run.

Usage:
    python3 test_webradio_long_soak.py --port /dev/ttyUSB0 --hours 4
        [--station-name "SLAM"] [--poll-secs 10] [--report-out PATH]
Exit 0 always (this is an observational soak, not a pass/fail gate) unless
the DUT never becomes ready.
"""
import re
import sys
import json
import time
import argparse
import serial

from app_ids_gen import APP_SLOT

# WRPlayState (webRadioApp.h): 0 STOPPED,1 CONNECTING,2 PLAYING,
# 3 ERROR_WIFI,4 ERROR_STALL,5 ERROR_UNREACHABLE,6 ERROR_BLOCKED
RETRYABLE_ERROR_STATES = {3, 4, 5}
WR_TERMINAL_RETRY_MS = 30000  # webRadioApp.h:69 — keep in sync if that constant moves
STUCK_SLACK_S = 20.0          # generous margin over WR_TERMINAL_RETRY_MS before flagging


class SerialDut:
    """Matches test_webradio_soak.py's SerialDut — no ELF-hash check (this
    tool runs against whatever debug build is currently flashed)."""

    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False

    def boot_wait(self, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in l or "spotify=off" in l:
                break
        for _ in range(40):
            if self.cmd("get appId", 2.0).get("name"):
                return True
            time.sleep(1.0)
        return False

    def cmd(self, s, timeout=3.0):
        self.ser.reset_input_buffer()
        self.ser.write((s + "\n").encode())
        self.ser.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if not l:
                continue
            try:
                r = json.loads(l)
                if not isinstance(r, dict):
                    continue
                if r.get("last", True):
                    return r
            except (json.JSONDecodeError, ValueError):
                pass
        return {}


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def log(msg):
    print(f"[{_ts()}] {msg}", flush=True)


def pick_station(dut, name_hint):
    cnt = dut.cmd("get wrCount", timeout=3.0).get("count", 0) or 0
    if cnt <= 0:
        return None, None
    stations = []
    for i in range(cnt):
        r = dut.cmd(f"get wrStation{i}", timeout=3.0)
        if "name" in r:
            stations.append((i, r["name"]))
    if not stations:
        return None, None
    if name_hint:
        for i, name in stations:
            if name_hint.lower() in name.lower():
                return i, name
        log(f"WARN: no station matched {name_hint!r} among {len(stations)} loaded — "
            f"falling back to idx 0 ({stations[0][1]!r})")
    return stations[0]


def snapshot(dut):
    return {
        "ts": _ts(),
        "wrState": dut.cmd("get wrState", timeout=3.0),
        "wrIcy": dut.cmd("get wrIcy", timeout=3.0),
        "wrIdx": dut.cmd("get wrIdx", timeout=3.0),
        "wrSkip": dut.cmd("get wrSkip", timeout=3.0),
        "heap": dut.cmd("get heap", timeout=3.0),
        "stacks": dut.cmd("get stacks", timeout=3.0),
    }


def write_report(report_out, data):
    with open(report_out, "w") as f:
        json.dump(data, f, indent=2, default=str)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--hours", type=float, default=4.0)
    ap.add_argument("--station-name", default="SLAM",
                     help="substring to match against loaded station names "
                          "(default SLAM, matching the original TASK-390 report)")
    ap.add_argument("--poll-secs", type=float, default=10.0)
    ap.add_argument("--report-out", default=None,
                     help="path for the anomaly/final report JSON "
                          "(default: app/tools/rnd_logs/webradio_long_soak_<stamp>.json)")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%dT%H%M%S")
    report_out = args.report_out or f"rnd_logs/webradio_long_soak_{stamp}.json"

    log(f"connecting {args.port} …")
    dut = SerialDut(args.port)
    if not dut.boot_wait():
        log("FAIL: shell did not become ready (WiFi up? debug build?)")
        sys.exit(1)

    log(f"entering WebRadio (switchApp {APP_SLOT['WebRadio']}) + waiting for station list …")
    dut.cmd(f"switchApp {APP_SLOT['WebRadio']}", timeout=3.0)
    cnt = 0
    for attempt in range(1, 4):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            r = dut.cmd("get wrCount", timeout=3.0)
            cnt = r.get("count", 0) or 0
            if cnt > 0:
                break
            if r.get("pending") == 0 and cnt == 0:
                break  # fetch already gave up, no point waiting out the full window
            time.sleep(2.0)
        if cnt > 0:
            break
        lh = dut.cmd("get wrLastHttp", timeout=3.0)
        log(f"WARN: station fetch attempt {attempt}/3 failed "
            f"(http={lh.get('http')} ok={lh.get('ok')} jsonErr={lh.get('jsonErr')!r}) — "
            f"re-triggering via leave/re-enter")
        dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
        time.sleep(1.0)
        dut.cmd(f"switchApp {APP_SLOT['WebRadio']}", timeout=3.0)  # TASK-289 second-chance fetch
    if cnt <= 0:
        log("FAIL: no stations loaded after 3 attempts (check WiFi / radio-browser reachability)")
        sys.exit(1)

    idx, name = pick_station(dut, args.station_name)
    if idx is None:
        log("FAIL: could not resolve a station to play")
        sys.exit(1)
    log(f"{cnt} stations loaded — playing idx={idx} ({name!r}) for {args.hours:.1f}h, "
        f"polling every {args.poll_secs:.0f}s")
    dut.cmd(f"set wrPlay {idx}", timeout=3.0)

    start = time.monotonic()
    end = start + args.hours * 3600
    events = []
    stuck_since = None
    flagged_this_episode = False
    last_state = None
    last_tried = None
    last_title = None
    polls = 0

    def elapsed():
        return round(time.monotonic() - start, 1)

    while time.monotonic() < end:
        time.sleep(args.poll_secs)
        polls += 1
        st_r = dut.cmd("get wrState", timeout=3.0)
        state = st_r.get("state")
        skip_r = dut.cmd("get wrSkip", timeout=3.0)
        tried = skip_r.get("tried")
        icy_r = dut.cmd("get wrIcy", timeout=3.0)
        title = icy_r.get("title")

        if title and title != last_title:
            events.append({"ts": _ts(), "elapsed_s": elapsed(), "event": "title", "title": title})
            log(f"  title: {title!r} (elapsed={elapsed():.0f}s)")
        last_title = title or last_title

        if state != last_state:
            events.append({"ts": _ts(), "elapsed_s": elapsed(), "event": "state_change",
                            "from": last_state, "to": state})
            log(f"  state {last_state} -> {state} (elapsed={elapsed():.0f}s)")
        last_state = state

        moving = (tried != last_tried)
        last_tried = tried

        if state in RETRYABLE_ERROR_STATES:
            if stuck_since is None:
                stuck_since = time.monotonic()
                flagged_this_episode = False
            elif moving:
                # tried counter moved -- the retry re-armed and is scanning again;
                # this episode is alive, reset the stuck clock.
                stuck_since = time.monotonic()
            else:
                stuck_s = time.monotonic() - stuck_since
                if stuck_s > (WR_TERMINAL_RETRY_MS / 1000.0 + STUCK_SLACK_S) and not flagged_this_episode:
                    flagged_this_episode = True
                    snap = snapshot(dut)
                    log(f"  *** ANOMALY: stuck in state={state} for {stuck_s:.0f}s with no "
                        f"observable recovery (TASK-393 signature) — capturing full state ***")
                    events.append({"ts": _ts(), "elapsed_s": elapsed(), "event": "ANOMALY",
                                    "stuck_s": round(stuck_s, 1), "snapshot": snap})
                    write_report(report_out, {"start": _ts(), "station": name, "idx": idx,
                                               "events": events, "status": "anomaly-in-progress"})
        else:
            stuck_since = None
            flagged_this_episode = False

        if polls % 30 == 0:  # ~every poll_secs*30 (default 5 min), a heartbeat line
            log(f"  alive: elapsed={elapsed():.0f}s state={state} tried={tried} "
                f"title={last_title!r}")
            write_report(report_out, {"start": _ts(), "station": name, "idx": idx,
                                       "events": events, "status": "running",
                                       "elapsed_s": elapsed()})

    log(f"soak complete: {elapsed():.0f}s elapsed, {len(events)} event(s), "
        f"{'ANOMALY CAPTURED' if any(e['event']=='ANOMALY' for e in events) else 'no anomaly'}")
    write_report(report_out, {"start": _ts(), "station": name, "idx": idx,
                               "events": events, "status": "complete",
                               "elapsed_s": elapsed()})
    log(f"report written -> {report_out}")


if __name__ == "__main__":
    main()
