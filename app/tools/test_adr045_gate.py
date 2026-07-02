#!/usr/bin/env python3
"""ADR-045 exit-criterion gate + WiFi outage attribution — TASK-238 / TASK-275.

Dual-purpose instrumented run (M-WIFI-DIAG §3.3/3.4, panel-approved):

  A. ADR-045 gate: N cold-entry trials — stable PLAYING (>=60 s hold) within
     <=6 auto-skips on >=90 % of attempts.
  B. Outage attribution: every outage window classified against link truth
     ([wifi-ev] reason codes via TASK-274 sensor), LAN truth (host ping of the
     DUT), and WAN truth (host upstream probe). Five classes:
     link-down / IP-layer / WAN-upstream / no-link-evidence / unattributed.

Harness architecture (VE-1 blocker fix): ONE continuous reader thread owns the
serial port and tees every line, host-timestamped, to a log file; [wifi-ev]
lines and failure signatures are parsed on the fly; cmd() consumes JSON replies
from the stream. reset_input_buffer() is never called after startup — async
evidence is never destroyed.

Exit protocol (design §3.4): run in the previously-dirty window; after the base
trials, extend only while 1-2 outage windows are captured (stop at >=3) up to a
hard on-air cap. A clean run is scored against the ADR-045 bar as-is (PM-2).

Usage:
    python3 test_adr045_gate.py --port /dev/ttyUSB0 [--trials 10] [--hold-secs 60]
        [--max-skips 6] [--pass-rate 0.9] [--trial-cap 300] [--cap-min 90]
        [--log-dir DIR]
Exit 0 = ADR-045 gate PASS; 1 otherwise. The attribution table prints either way.
"""
import os
import re
import sys
import json
import time
import queue
import argparse
import threading
import subprocess
import serial

UPSTREAM_URL = "http://connectivitycheck.gstatic.com/generate_204"

RE_WIFI_EV = re.compile(r"\[wifi-ev\] t=(\d+) ev=\d+ (\S+)(?: reason=(\d+))?")
# DUT-side failure signatures that open/extend an outage window
RE_FAIL = re.compile(r"errno: 118|DNS Failed|connecttohost failed")
# success signature that closes a window
RE_OK = re.compile(r"MP3Decoder has been initialized|Connection has been established")
RE_BOOT = re.compile(r"ets Jun  8 2016|rst:0x")


class SerialDut:
    """Continuous-reader serial DUT (TASK-275a). The reader thread owns RX."""

    def __init__(self, port, log_path, baud=115200):
        self.port, self.baud = port, baud
        self.ser = serial.Serial(port, baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False
        self.log = open(log_path, "a", buffering=1)
        self.replies = queue.Queue()
        self.wifi_events = []     # (host_ts, dev_ms, name, reason|None)
        self.fail_marks = []      # host_ts of DUT-side connect-failure lines
        self.ok_marks = []        # host_ts of DUT-side success lines
        self.boot_marks = []      # host_ts of reboot banners
        self.lock = threading.Lock()
        self._alive = True
        self._rx = threading.Thread(target=self._reader, daemon=True)
        self._rx.start()

    def _reader(self):
        while self._alive:
            try:
                raw = self.ser.readline()
            except (serial.SerialException, OSError):
                time.sleep(0.2)
                continue
            if not raw:
                continue
            ts = time.time()
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            self.log.write(f"{ts:.3f}|{line}\n")
            m = RE_WIFI_EV.search(line)
            if m:
                with self.lock:
                    self.wifi_events.append((ts, int(m.group(1)), m.group(2),
                                             int(m.group(3)) if m.group(3) else None))
            if RE_FAIL.search(line):
                with self.lock:
                    self.fail_marks.append(ts)
            if RE_OK.search(line):
                with self.lock:
                    self.ok_marks.append(ts)
            if RE_BOOT.search(line):
                with self.lock:
                    self.boot_marks.append(ts)
            if line.startswith("{"):
                try:
                    r = json.loads(line)
                    if isinstance(r, dict) and r.get("last", True):
                        self.replies.put((ts, r))
                except (json.JSONDecodeError, ValueError):
                    pass

    def cmd(self, s, timeout=3.0):
        # drain stale replies, then send and wait for the next JSON dict
        while not self.replies.empty():
            try:
                self.replies.get_nowait()
            except queue.Empty:
                break
        self.ser.write((s + "\n").encode())
        self.ser.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                _, r = self.replies.get(timeout=0.2)
                return r
            except queue.Empty:
                continue
        return {}

    def reboot(self):
        with self.lock:
            ev_mark = len(self.wifi_events)
        self._alive = False
        self._rx.join(timeout=2)
        self.ser.close()
        time.sleep(1.0)
        self.ser = serial.Serial(self.port, self.baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False
        self._alive = True
        self._rx = threading.Thread(target=self._reader, daemon=True)
        self._rx.start()
        return self.boot_wait(ev_mark=ev_mark)

    def boot_wait(self, timeout=60, ev_mark=0):
        """Wait for a GOT_IP event newer than ev_mark, then the shell."""
        end = time.monotonic() + timeout
        got_ip = False
        while time.monotonic() < end and not got_ip:
            with self.lock:
                got_ip = any(n == "STA_GOT_IP"
                             for _, _, n, _ in self.wifi_events[ev_mark:])
            time.sleep(0.5)
        for _ in range(40):
            if self.cmd("get appId", 2.0).get("name"):
                return True
            time.sleep(1.0)
        return False


class PingProbe:
    """Host->DUT LAN truth. ping -D -i 1; timeline of (host_ts, ok)."""

    def __init__(self, log_path):
        self.timeline = []
        self.log = open(log_path, "a", buffering=1)
        self.proc = None
        self.ip = None
        self._thread = None
        self._alive = False

    def start(self, ip):
        self.stop()
        self.ip = ip
        self.proc = subprocess.Popen(
            ["ping", "-D", "-i", "1", ip],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self._alive = True
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        last_ok = time.time()
        while self._alive and self.proc and self.proc.poll() is None:
            line = self.proc.stdout.readline()
            if not line:
                continue
            self.log.write(line)
            ts = time.time()
            if "bytes from" in line:
                # backfill misses: gap since last success > 2 s
                if ts - last_ok > 2.0:
                    self.timeline.append((last_ok + 1.0, False))
                self.timeline.append((ts, True))
                last_ok = ts

    def dead_in(self, t0, t1):
        """True if ping showed a >=2 s hole overlapping [t0,t1]."""
        oks = [ts for ts, ok in self.timeline if ok and t0 - 3.0 <= ts <= t1 + 3.0]
        if not oks:
            return True   # no successes anywhere near the window
        oks.sort()
        prev = t0 - 3.0
        for ts in oks + [t1 + 3.0]:
            if ts - prev >= 2.0 and prev < t1 and ts > t0:
                return True
            prev = ts
        return False

    def stop(self):
        self._alive = False
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None


class UpstreamProbe:
    """Host->WAN truth. curl of a stable 204 endpoint every 10 s."""

    def __init__(self):
        self.timeline = []
        self._alive = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._alive:
            t0 = time.time()
            try:
                rc = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-m", "5", UPSTREAM_URL],
                    timeout=8).returncode
                ok = (rc == 0)
            except Exception:
                ok = False
            self.timeline.append((t0, ok))
            time.sleep(max(0.0, 10.0 - (time.time() - t0)))

    def failing_in(self, t0, t1):
        near = [ok for ts, ok in self.timeline if t0 - 10.0 <= ts <= t1 + 10.0]
        return bool(near) and not any(near)

    def stop(self):
        self._alive = False


def attribute_windows(dut, ping, upstream):
    """Cluster failure marks into outage windows; classify each (design §3.4)."""
    with dut.lock:
        fails = sorted(dut.fail_marks)
        oks = sorted(dut.ok_marks)
        evs = list(dut.wifi_events)
        boots = sorted(dut.boot_marks)
    # cluster: gaps <10 s join a window
    windows = []
    for ts in fails:
        if windows and ts - windows[-1][1] < 10.0:
            windows[-1][1] = ts
        else:
            windows.append([ts, ts])
    out = []
    for t0, t1 in windows:
        # end bound: first DUT success after t1 (recovery), capped +60 s
        rec = next((o for o in oks if o > t1), t1 + 60.0)
        t1e = min(rec, t1 + 60.0)
        if any(t0 - 5.0 <= b <= t1e for b in boots):
            out.append((t0, t1e, "excluded-reboot", None))
            continue
        disc = [(ts, r) for ts, _, n, r in evs
                if n == "STA_DISCONNECTED" and t0 - 5.0 <= ts <= t1e]
        if disc:
            reasons = sorted({r for _, r in disc if r is not None})
            out.append((t0, t1e, "link-down", reasons))
        elif ping.dead_in(t0, t1e):
            out.append((t0, t1e, "IP-layer", None))
        elif upstream.failing_in(t0, t1e):
            out.append((t0, t1e, "WAN-upstream", None))
        elif ping.timeline:
            out.append((t0, t1e, "no-link-evidence", None))
        else:
            out.append((t0, t1e, "unattributed", None))
    return out


def run_trial(d, n, hold_secs, max_skips, trial_cap):
    t = {"n": n, "pass": False, "skips": 0, "ttfp": None, "holdMs": 0,
         "discDelta": 0, "why": ""}
    w0 = d.cmd("get wifi")
    disc0 = w0.get("discCount", 0) or 0
    d.cmd("switchApp 10", 3.0)
    time.sleep(1.5)
    d.cmd("set wrPlay 0", 3.0)

    t0 = time.monotonic()
    cum_skips = 0
    prev_tried = 0
    while time.monotonic() - t0 < trial_cap:
        sk = d.cmd("get wrSkip")
        tried = sk.get("tried")
        if isinstance(tried, int):
            if tried > prev_tried:
                cum_skips += tried - prev_tried
            prev_tried = tried
        pl = d.cmd("get wrPlaying")
        ms = pl.get("ms") or 0
        if pl.get("playing") and t["ttfp"] is None:
            t["ttfp"] = round(time.monotonic() - t0, 1)
        t["holdMs"] = max(t["holdMs"], ms)
        t["skips"] = cum_skips
        if ms >= hold_secs * 1000:
            t["pass"] = cum_skips <= max_skips
            t["why"] = "OK" if t["pass"] else f"held but {cum_skips} skips > {max_skips}"
            break
        time.sleep(2.0)
    else:
        t["why"] = (f"no {hold_secs}s hold within {trial_cap}s "
                    f"(maxHold={t['holdMs']}ms, skips={cum_skips})")

    w1 = d.cmd("get wifi")
    t["discDelta"] = (w1.get("discCount", 0) or 0) - disc0
    d.cmd("switchApp 0", 3.0)
    time.sleep(3.0)
    return t


def main():
    ap = argparse.ArgumentParser(description="ADR-045 gate + outage attribution (TASK-238/275)")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--hold-secs", type=int, default=60)
    ap.add_argument("--max-skips", type=int, default=6)
    ap.add_argument("--pass-rate", type=float, default=0.9)
    ap.add_argument("--trial-cap", type=int, default=300)
    ap.add_argument("--cap-min", type=float, default=90, help="hard on-air cap (minutes)")
    ap.add_argument("--log-dir", default=None)
    args = ap.parse_args()

    log_dir = args.log_dir or f"/tmp/wr-gate-{time.strftime('%Y%m%d-%H%M%S')}"
    os.makedirs(log_dir, exist_ok=True)
    print(f"[adr045] logs: {log_dir}", flush=True)

    t_start = time.time()
    d = SerialDut(args.port, os.path.join(log_dir, "serial.log"))
    upstream = UpstreamProbe()
    ping = PingProbe(os.path.join(log_dir, "ping.log"))

    print(f"[adr045] connecting {args.port} …", flush=True)
    if not d.boot_wait():
        print("[adr045] FAIL: shell not ready", flush=True)
        sys.exit(1)

    # station list: wait for STABLE count; the app fetches once with no retry —
    # a 0-station conclusion means the fetch died; recover by rebooting.
    cnt = 0
    for attempt in range(1, 4):
        d.cmd("switchApp 10", 3.0)
        cnt, stable = 0, 0
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and stable < 3:
            r = d.cmd("get wrCount")
            c = r.get("count", 0) or 0
            if c == 0 and r.get("pending") == 0:
                break
            stable = stable + 1 if (c == cnt and c > 0) else 0
            cnt = c
            time.sleep(4.0)
        if cnt > 0:
            break
        lh = d.cmd("get wrLastHttp")
        print(f"[adr045] station fetch failed (attempt {attempt}/3): "
              f"http={lh.get('http')} ok={lh.get('ok')} — rebooting DUT", flush=True)
        if not d.reboot():
            print("[adr045] FAIL: shell not ready after reboot", flush=True)
            sys.exit(1)
    if cnt <= 0:
        print("[adr045] FAIL: no stations loaded after 3 attempts", flush=True)
        sys.exit(1)

    # LAN-truth ping: needs the DUT IP; pre-flight one known-good ping window
    ip = d.cmd("get wifi").get("ip")
    if ip and ip != "0.0.0.0":
        ping.start(ip)
        time.sleep(5)
        if not any(ok for _, ok in ping.timeline):
            print("[adr045] WARN: ping pre-flight failed (client isolation?) — "
                  "IP-layer class will be unreliable", flush=True)
    else:
        print("[adr045] WARN: no DUT IP — ping probe disabled", flush=True)

    d.cmd("set wrAutoSkip 1")
    d.cmd("switchApp 0", 3.0)
    print("[adr045] 60s boot settle", flush=True)
    time.sleep(60.0)
    print(f"[adr045] {cnt} stations, auto-skip ON — {args.trials} cold-entry trials "
          f"(hold>={args.hold_secs}s, skips<={args.max_skips}, cap {args.trial_cap}s)", flush=True)

    results = []
    i = 0
    while True:
        i += 1
        # keep ping pointed at the current IP (DTR reboots can change it)
        cur_ip = d.cmd("get wifi").get("ip")
        if cur_ip and cur_ip != "0.0.0.0" and cur_ip != ping.ip:
            ping.start(cur_ip)
        t = run_trial(d, i, args.hold_secs, args.max_skips, args.trial_cap)
        results.append(t)
        print(f"  trial {i:>2}: {'PASS' if t['pass'] else 'FAIL'} skips={t['skips']} "
              f"ttfp={t['ttfp']}s hold={t['holdMs']}ms discΔ={t['discDelta']}  {t['why']}",
              flush=True)
        elapsed_min = (time.time() - t_start) / 60.0
        if i >= args.trials:
            wins = attribute_windows(d, ping, upstream)
            n_out = sum(1 for w in wins if w[2] != "excluded-reboot")
            # extension rule (§3.4): extend only while 1-2 windows captured
            if n_out in (1, 2) and elapsed_min < args.cap_min:
                print(f"[adr045] {n_out} outage windows < 3 — extending "
                      f"({elapsed_min:.0f}/{args.cap_min:.0f} min)", flush=True)
                continue
            break
        if elapsed_min >= args.cap_min:
            print("[adr045] hard on-air cap reached", flush=True)
            break

    ping.stop()
    upstream.stop()

    # ── report ──────────────────────────────────────────────────────────────
    passes = sum(1 for t in results if t["pass"])
    rate = passes / len(results)
    skips = [t["skips"] for t in results]
    wins = attribute_windows(d, ping, upstream)
    print("\n========== ADR-045 gate + attribution (TASK-238/275) ==========", flush=True)
    print(f"trials                : {len(results)}", flush=True)
    print(f"passes                : {passes}  (rate {rate:.0%}, gate >= {args.pass_rate:.0%})", flush=True)
    print(f"skips per trial       : min={min(skips)} max={max(skips)}", flush=True)
    print(f"\noutage windows        : {len(wins)}", flush=True)
    for t0, t1, cls, reasons in wins:
        dur = t1 - t0
        rs = f" reasons={reasons}" if reasons else ""
        print(f"  {time.strftime('%H:%M:%S', time.localtime(t0))} "
              f"dur={dur:5.1f}s  {cls}{rs}", flush=True)
    counts = {}
    for _, _, cls, _ in wins:
        counts[cls] = counts.get(cls, 0) + 1
    print(f"attribution           : {counts or 'no outages'}", flush=True)
    with d.lock:
        n_disc = sum(1 for _, _, n, _ in d.wifi_events if n == "STA_DISCONNECTED")
    print(f"total STA_DISCONNECTED: {n_disc}", flush=True)
    ok = rate >= args.pass_rate
    print(f"GATE: {'PASS' if ok else 'FAIL'}", flush=True)
    print("================================================================", flush=True)
    print(f"[adr045] full logs in {log_dir}", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
