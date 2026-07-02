#!/usr/bin/env python3
"""ADR-045 MVP exit-criterion gate — TASK-238 (M-WEBRADIO milestone-close).

The criterion (ADR-045, supersedes the Tier-1-only wording in M-WEBRADIO.md):

    From cold entry on the no-PSRAM DUT, WebRadio reaches a stable PLAYING state
    (holds >= 60 s) within <= 6 auto-skips on >= 90 % of attempts.

This is a STATISTICAL feature-level gate over N cold-entry trials, not a code gate
(TASK-234's mechanism tests already cover the skip logic). One trial:

  1. Cold entry: switchApp 10 (Winamp slot -> WebRadio). On re-entry the arena was
     released by suspend() and the Audio object destroyed — the memory-cold path
     ADR-045 worries about. Stations persist after the first fetch (init() runs once).
  2. set wrPlay 0 (user-initiated -> resets the auto-skip scan; deterministic start).
  3. Tune+hold: poll get wrSkip / get wrPlaying every 2 s. Auto-skip (default ON)
     walks dead stations. Track CUMULATIVE skips — `tried` resets both on settle
     (12 s) and on user play, so the gate counter must accumulate increments, never
     read the final value. Trial passes when a continuous PLAYING run reaches
     >= 60 s (wrPlaying.ms) with cumulative skips <= 6 inside the trial cap.
  4. switchApp 0 (suspend releases arena) -> next trial.

Runs on cyd2usb_webradio (Spotify disabled -> no TASK-243 403 fetch starvation;
identical MEMBUDGET_PHASE1 arena to production). Pairs with run/wr-gate.

Usage:
    python3 test_adr045_gate.py --port /dev/ttyUSB0 [--trials 10] [--hold-secs 60]
                                [--max-skips 6] [--pass-rate 0.9] [--trial-cap 300]
Exit 0 = gate PASS (pass rate >= threshold), 1 otherwise.
"""
import sys
import json
import time
import argparse
import serial


class SerialDut:
    """Self-contained (no run_serialdbg Dut — its ELF gate rejects the webradio build)."""
    def __init__(self, port, baud=115200):
        self.port, self.baud = port, baud
        self.ser = serial.Serial(port, baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False

    def reboot(self):
        """CH340 pulses DTR on open → ESP32 resets. Close + reopen = clean reboot."""
        self.ser.close()
        time.sleep(1.0)
        self.ser = serial.Serial(self.port, self.baud, timeout=0.4)
        self.ser.dtr = False
        self.ser.rts = False
        return self.boot_wait()

    def boot_wait(self, timeout=45):
        # NB: the boot log prints "IP address: 0.0.0.0" from an early WiFi event
        # before the real lease — matching the first occurrence proceeds before
        # WiFi is actually up and the app's one-shot station fetch then fails.
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in l and "0.0.0.0" not in l:
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
                    continue          # bare JSON scalars (stray numbers) on serial
                if r.get("last", True):
                    return r
            except (json.JSONDecodeError, ValueError):
                pass
        return {}


def run_trial(d, n, hold_secs, max_skips, trial_cap):
    """One cold-entry attempt. Returns dict with pass/skips/time_to_stable/hold."""
    t = {"n": n, "pass": False, "skips": 0, "ttfp": None, "holdMs": 0, "why": ""}
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
                cum_skips += tried - prev_tried   # new skips since last poll
            prev_tried = tried                    # handles the reset-on-settle to 0
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
        t["why"] = f"no {hold_secs}s hold within {trial_cap}s (maxHold={t['holdMs']}ms, skips={cum_skips})"

    # leave the slot — suspend() releases the arena; next trial is memory-cold
    d.cmd("switchApp 0", 3.0)
    time.sleep(3.0)
    return t


def main():
    ap = argparse.ArgumentParser(description="ADR-045 exit-criterion gate (TASK-238)")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--hold-secs", type=int, default=60)
    ap.add_argument("--max-skips", type=int, default=6)
    ap.add_argument("--pass-rate", type=float, default=0.9)
    ap.add_argument("--trial-cap", type=int, default=300)
    args = ap.parse_args()

    print(f"[adr045] connecting {args.port} …", flush=True)
    d = SerialDut(args.port)
    if not d.boot_wait():
        print("[adr045] FAIL: shell not ready", flush=True); sys.exit(1)

    # First entry fetches the station list — wait for a STABLE count (LL-090).
    # The app fetches ONCE at init() with no retry: if the fetch fired before WiFi
    # was fully up (or radio-browser hiccuped), count stays 0 forever with pending=0.
    # Detect that (wrCount.pending + wrLastHttp) and recover by rebooting — a reboot
    # IS a cold entry, so the retry is methodologically clean.
    cnt = 0
    for attempt in range(1, 4):
        d.cmd("switchApp 10", 3.0)
        cnt, stable = 0, 0
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and stable < 3:
            r = d.cmd("get wrCount")
            c = r.get("count", 0) or 0
            if c == 0 and r.get("pending") == 0:
                break                      # fetch concluded with nothing — retry now
            stable = stable + 1 if (c == cnt and c > 0) else 0
            cnt = c
            time.sleep(4.0)
        if cnt > 0:
            break
        lh = d.cmd("get wrLastHttp")
        print(f"[adr045] station fetch failed (attempt {attempt}/3): "
              f"http={lh.get('http')} ok={lh.get('ok')} — rebooting DUT", flush=True)
        if not d.reboot():
            print("[adr045] FAIL: shell not ready after reboot", flush=True); sys.exit(1)
    if cnt <= 0:
        print("[adr045] FAIL: no stations loaded after 3 attempts", flush=True); sys.exit(1)
    d.cmd("set wrAutoSkip 1")          # the mechanism under test (default ON anyway)
    d.cmd("switchApp 0", 3.0)          # leave so trial 1 is a genuine cold entry
    # Boot settle: this DUT's WiFi shows a near-deterministic drop at ~35 s uptime
    # (recovers by ~60 s; heartbeat rssi(0) during it). A trial started inside the
    # outage fast-fails the whole station list into the terminal state and reads as
    # a gate failure that is environment, not feature. Start trials past it.
    print("[adr045] 60s boot settle (rides out the ~35-60s WiFi drop)", flush=True)
    time.sleep(60.0)
    print(f"[adr045] {cnt} stations, auto-skip ON — {args.trials} cold-entry trials "
          f"(hold>={args.hold_secs}s, skips<={args.max_skips}, cap {args.trial_cap}s)", flush=True)

    results = []
    for i in range(1, args.trials + 1):
        t = run_trial(d, i, args.hold_secs, args.max_skips, args.trial_cap)
        results.append(t)
        print(f"  trial {i:>2}: {'PASS' if t['pass'] else 'FAIL'} skips={t['skips']} "
              f"time-to-first-play={t['ttfp']}s hold={t['holdMs']}ms  {t['why']}", flush=True)

    passes = sum(1 for t in results if t["pass"])
    rate = passes / len(results)
    skips = [t["skips"] for t in results]
    print("\n=============== ADR-045 exit-criterion gate (TASK-238) ===============", flush=True)
    print(f"trials                : {len(results)}", flush=True)
    print(f"passes                : {passes}  (rate {rate:.0%}, gate >= {args.pass_rate:.0%})", flush=True)
    print(f"skips per trial       : min={min(skips)} max={max(skips)}", flush=True)
    ttfps = [t["ttfp"] for t in results if t["ttfp"] is not None]
    if ttfps:
        print(f"time to first play (s): min={min(ttfps)} max={max(ttfps)}", flush=True)
    ok = rate >= args.pass_rate
    print(f"GATE: {'PASS' if ok else 'FAIL'}", flush=True)
    print("=======================================================================", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
