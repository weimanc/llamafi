#!/usr/bin/env python3
"""WebRadio playback + arena-churn soak — TASK-271.

Repeatedly enters WebRadio, plays a station, then leaves the slot — churning the
A-lite decoder arena (TASK-262: a JIT heap_caps_malloc(24K)/free on every _play /
suspend). One-shot validation only proved a few cycles; this soaks the cycle to
surface what only time shows:

  - ARENA FRAGMENTATION CREEP — lfbBefore(INTERNAL) captured at each acquire. If the
    largest contiguous INTERNAL block decays over hundreds of cycles, the arena is
    fragmenting the heap.
  - ARENA ACQUIRE FAILURE — a `FAIL` means 24K is no longer contiguous (the wall the
    whole A-lite design guards against).
  - ACQUIRE/RELEASE BALANCE — a leak detector (acquires must equal releases).
  - SUSTAINED-PLAYBACK DISTRIBUTION — seconds PLAYING per station, quantifying the
    TASK-233 "best-effort on no-PSRAM" claim instead of asserting it.
  - UNDERRUNS + error/skip outcomes per cycle.

Runs on cyd2usb_webradio (Spotify DISABLED → no TASK-243 403 fetch starvation, so
stations actually load + play). The arena code is identical to production
cyd2usb_winamp (both -DMEMBUDGET_PHASE1); only Spotify differs. Pairs with
`run/wr-soak` (flash webradio build → soak → restore prod).

Instrumentation parsed from the serial log (SERIAL_DEBUG build):
    [membudget] TASK-267 arena acquire=24576B lfbBefore=<N> OK|FAIL...
    [membudget] TASK-267 arena released
plus serial-debug queries: get wrCount / wrState / wrPlaying / wrUnderruns.

Usage:
    python3 test_webradio_soak.py --port /dev/ttyUSB0 --minutes 10 [--play-secs 20] [--verbose]
Exit 0 = soak completed, arena balanced, zero acquire-FAIL, no lfb collapse; 1 otherwise.
"""
import re
import sys
import json
import time
import argparse
import statistics
import serial

# Self-contained serial wrapper. We deliberately do NOT reuse run_serialdbg_tests.Dut:
# its constructor enforces the canonical cyd2usb_winamp_debug ELF hash, but this soak runs
# on the cyd2usb_webradio build (different ELF). Both have SERIAL_DEBUG, which is all we need.
class SerialDut:
    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False

    def boot_wait(self, timeout=45):
        """CH341 asserts DTR on open → ESP32 resets. Wait for WiFi, then the shell."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in l or "spotify=off" in l:
                break
        # poll until the serial-debug shell answers
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
                    continue          # bare JSON scalars (stray numbers) on serial
                if r.get("last", True):
                    return r
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

RE_ACQUIRE = re.compile(r"arena acquire=(\d+)B lfbBefore=(\d+)\s+(\S+)")
RE_RELEASE = re.compile(r"arena released")

# WRPlayState (webRadioApp.h): 0 IDLE,1 CONNECTING,2 PLAYING,3 STOPPED,4 ERROR_*...
PLAYING = 2


def pct(xs, p):
    if not xs:
        return 0
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


class Soak:
    def __init__(self, dut, play_secs, verbose):
        self.d = dut
        self.play_secs = play_secs
        self.verbose = verbose
        self.lfb = []            # lfbBefore at each acquire
        self.acquires = 0
        self.releases = 0
        self.acquire_fail = 0
        self.play_secs_seen = []  # sustained PLAYING seconds per cycle
        self.reached_playing = 0
        self.underruns = 0
        self.errors = 0
        self.cycles = 0

    def _read_for(self, secs, want_substr=None):
        """Read serial for `secs`, returning all lines; early-out on want_substr."""
        lines = []
        end = time.monotonic() + secs
        while time.monotonic() < end:
            l = self.d.ser.readline().decode(errors="replace").strip()
            if not l:
                continue
            lines.append(l)
            if self.verbose and ("membudget" in l or "webradio" in l):
                print(f"    | {l}", flush=True)
            if want_substr and want_substr in l:
                break
        return lines

    def _cmd(self, s, t=3.0):
        try:
            return self.d.cmd(s, timeout=t)
        except Exception:
            return {}

    def _scan_arena(self, lines):
        for l in lines:
            m = RE_ACQUIRE.search(l)
            if m:
                self.acquires += 1
                self.lfb.append(int(m.group(2)))
                if "OK" not in m.group(3):
                    self.acquire_fail += 1
            if RE_RELEASE.search(l):
                self.releases += 1

    def cycle(self, idx):
        self.cycles += 1
        # play a station — arena acquires in _play()
        self.d.ser.reset_input_buffer()
        self.d.ser.write(f"set wrPlay {idx}\n".encode())
        self.d.ser.flush()
        lines = self._read_for(6.0, want_substr="arena acquire=")
        self._scan_arena(lines)

        # sample sustained playback over the full window. A stream takes a few seconds
        # to go CONNECTING→PLAYING, so we do NOT break on the first wrPlaying=0 — we wait
        # up to CONNECT_GRACE for it to start; once it has played, a later 0 means it
        # stalled/stopped (the TASK-233 best-effort signal) and we stop, recording how
        # long it held. reached_playing is derived from the poll, robust to log races.
        CONNECT_GRACE = 7.0
        t0 = time.monotonic()
        played = False
        first_play = None
        last_play = None
        end = t0 + self.play_secs
        while time.monotonic() < end:
            pl = self._cmd("get wrPlaying", 2.0).get("playing")
            now = time.monotonic()
            if pl:
                played = True
                if first_play is None:
                    first_play = now
                last_play = now
            elif played:
                break                      # was playing → stalled/stopped
            elif now - t0 > CONNECT_GRACE:
                break                      # never started → dead station
            time.sleep(2.0)
        sustained = (last_play - first_play) if (first_play and last_play) else 0.0
        if played:
            self.reached_playing += 1
        self.play_secs_seen.append(round(sustained, 1))
        ur = self._cmd("get wrUnderruns").get("underruns")
        if isinstance(ur, int):
            self.underruns = max(self.underruns, ur)  # counter is per-PLAYING-session
        st2 = self._cmd("get wrState").get("state")
        if st2 is not None and st2 >= 4:
            self.errors += 1

        # leave the slot → suspend() releases the arena
        self.d.ser.reset_input_buffer()
        self.d.ser.write(b"switchApp 0\n")
        self.d.ser.flush()
        self._scan_arena(self._read_for(3.0, want_substr="arena released"))
        time.sleep(0.5)
        # re-enter WebRadio (stations persist — init() only runs on first launch)
        self._cmd("switchApp 10", 3.0)
        time.sleep(1.0)

        if self.verbose:
            print(f"  cycle {self.cycles}: idx={idx} state={st2} sustained={sustained:.0f}s "
                  f"lfb={self.lfb[-1] if self.lfb else '?'} acq={self.acquires} rel={self.releases}",
                  flush=True)

    def report(self):
        print("\n================ WebRadio soak report (TASK-271) ================", flush=True)
        print(f"cycles                : {self.cycles}", flush=True)
        print(f"arena acquires        : {self.acquires}", flush=True)
        print(f"arena releases        : {self.releases}", flush=True)
        bal = (self.acquires == self.releases)
        print(f"acquire/release balance: {'OK (no leak)' if bal else 'MISMATCH (possible leak)'}", flush=True)
        print(f"arena acquire FAILures : {self.acquire_fail}", flush=True)
        if self.lfb:
            print(f"lfbBefore(INTERNAL)   : first={self.lfb[0]} min={min(self.lfb)} "
                  f"last={self.lfb[-1]}  (24K arena needs >=24576)", flush=True)
            drop = (self.lfb[0] - min(self.lfb)) / self.lfb[0] * 100 if self.lfb[0] else 0
            print(f"lfb worst-case drop   : {drop:.1f}% from first", flush=True)
        if self.play_secs_seen:
            ps = self.play_secs_seen
            print(f"sustained playback (s): min={min(ps)} median={statistics.median(ps)} "
                  f"p95={pct(ps,95)} max={max(ps)}  (cap={self.play_secs}s)", flush=True)
        print(f"reached PLAYING       : {self.reached_playing}/{self.cycles}", flush=True)
        print(f"max underruns/session : {self.underruns}", flush=True)
        print(f"error/skip cycles     : {self.errors}", flush=True)

        # verdict
        ok = (self.cycles >= 3 and bal and self.acquire_fail == 0)
        if self.lfb:
            ok = ok and (min(self.lfb) >= 24576)   # 24K always stayed contiguous
        print("================================================================", flush=True)
        print(f"VERDICT: {'PASS' if ok else 'FAIL'}", flush=True)
        return ok


def main():
    ap = argparse.ArgumentParser(description="WebRadio playback + arena-churn soak (TASK-271)")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--play-secs", type=int, default=20, help="seconds to hold each station")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print(f"[wr-soak] connecting {args.port} …", flush=True)
    dut = SerialDut(args.port)
    if not dut.boot_wait():
        print("[wr-soak] FAIL: shell did not become ready (WiFi up? debug build?)", flush=True)
        sys.exit(1)
    print("[wr-soak] entering WebRadio (switchApp 10) + waiting for station list …", flush=True)
    dut.cmd("switchApp 10", timeout=3.0)
    time.sleep(1.0)

    cnt = 0
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        cnt = dut.cmd("get wrCount", timeout=3.0).get("count", 0) or 0
        if cnt > 0:
            break
        time.sleep(2.0)
    if cnt <= 0:
        print("[wr-soak] FAIL: no stations loaded (check WiFi / radio-browser reachability)", flush=True)
        sys.exit(1)
    print(f"[wr-soak] {cnt} stations loaded — soaking {args.minutes} min "
          f"({args.play_secs}s/station)…", flush=True)

    soak = Soak(dut, args.play_secs, args.verbose)
    end = time.monotonic() + args.minutes * 60
    i = 0
    while time.monotonic() < end:
        soak.cycle(i % cnt)
        i += 1
    ok = soak.report()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
