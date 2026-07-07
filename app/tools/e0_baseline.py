#!/usr/bin/env python3
"""
E0 shared baseline session — M-WR-AUDIO-TASK §E0 + M-TASKBAR-FEEDBACK §Measurement plan.

One DUT session on current master records BOTH designs' before-numbers
(QM-2-2 / VE-2-1 / VE-3-2 / DEV-X-1: single shared session, same-length windows,
N>=5 taps per state, [wifi-ev] captured throughout). Re-run post-implementation
with the same arguments; both tables land in the design docs.

Per state (idle_clock, spotify, wr_stopped, wr_playing):
  1. enter state via switchApp / transport tap, settle;
  2. capture a same-length hb window (default 10 min): per-hb-window loop_max
     series, worst paths, [wifi-ev] lines, [perf] iter warnings;
  3. N injected taskbar drag-taps (real gesture path — `tap` bypasses it,
     doc 3 §Measurement plan): per tap record drain_ms (drag cmd -> drag JSON,
     queue drains 1 sample/loop => loop-cadence proxy) and entered_ms
     (drag JSON -> `[shell] entered` line = tap-to-switch-committed);
     then switch back and re-settle.
  wr_playing additionally snapshots wrUnderruns/minBufPct at window start/end
  (counter resets on every _play() — [webradio] restarts within the window are
  counted and annotated, VE-2-1 outage-attribution caveat applies).

Usage:
  ./run/flash-debug   # harness owns the port; monitor stays down
  python3 app/tools/e0_baseline.py --port /dev/ttyUSB0 \
      --window-min 10 --taps 5 --out e0_results.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time

from run_serialdbg_tests import Dut
from wifi_watch import WatchDut  # lenient gate: skips ELF + Spotify-poll checks

# App registry order (appRegistry.h) — taskbar slot i shows app (tbScrollOffset+i) % 10.
APP_SPOTIFY, APP_CLOCK, APP_WEATHER, APP_WEBRADIO = 0, 1, 2, 10
TASKBAR_X_TAP = 290          # > TASKBAR_X (275) — routed to taskbar gesture handlers
TASKBAR_SLOT_H = 40
# Winamp transport (skin_layout.h): button centres, main-window origin 0,0.
PLAY_XY = (50, 97)           # CB_PLAY  39,88 + 23x18/2
STOP_XY = (96, 97)           # CB_STOP  85,88 + 23x18/2

HB_RE = re.compile(
    r"\[hb\].*wifi=(?P<wifi>\S+) disc=(?P<disc>\d+) heap=(?P<heap>\d+)k.*"
    r"last=(?P<last>-?\d+).*loop_max=(?P<loopmax>\d+)ms slow=(?P<slow>[^:]+):(?P<slowms>\d+)ms"
)
WIFI_EV_RE = re.compile(r"\[wifi-ev\]")
PERF_WARN_RE = re.compile(r"\[perf\] iter=(\d+)ms")
ENTERED_RE = re.compile(r"\[shell\] entered (\d+)")
WR_LOG_RE = re.compile(r"\[webradio\]")
# TASK-279 (M-TASKBAR-FEEDBACK): post-implementation observables. Additive — the
# entered/drain clocks above are untouched, so before/after stays comparable.
TB_PRESS_RE = re.compile(r"\[shell\] tb-press slot=(\d+)")
TB_COMMIT_RE = re.compile(r"\[shell\] tb-commit slot=(\d+)")
SWITCH_RE = re.compile(
    r"\[shell\] switch (\d+)->(\d+) suspend=(?P<suspend>\d+)ms wipe=(?P<wipe>\d+)ms "
    r"init=(?P<init>\d+)ms taskbar=(?P<taskbar>\d+)ms total=(?P<total>\d+)ms")

STATES = ["idle_clock", "spotify", "wr_stopped", "wr_playing"]
STATE_APP = {"idle_clock": APP_CLOCK, "spotify": APP_SPOTIFY,
             "wr_stopped": APP_WEBRADIO, "wr_playing": APP_WEBRADIO}
# Tap target slot per state — must switch to a *different* app (same-app tap is a no-op).
# Slot 1 = Clock everywhere except when Clock is foreground; then slot 2 = Weather.
STATE_TAP_SLOT = {"idle_clock": 2, "spotify": 1, "wr_stopped": 1, "wr_playing": 1}


def wr_state(d: Dut) -> int:
    return int(d.cmd("get wrState").get("state", -1))


def wr_wait_state(d: Dut, want: int, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if wr_state(d) == want:
            return True
        time.sleep(2.0)
    return False


def enter_state(d: Dut, state: str) -> dict:
    """Drive the DUT into `state`; returns entry annotations."""
    notes: dict = {}
    d.cmd(f"switchApp {STATE_APP[state]}", 5.0)
    if state == "wr_playing":
        # The serial-open reboot (CH341 DTR pulse) wipes the loaded station list;
        # the re-fetch takes ~15 s. Tapping PLAY before wrCount>0 plays nothing and
        # parks in STOPPED (the bug that lost the wr_playing row in runs 1-4,
        # 2026-07-03). Wait for a non-zero station count FIRST.
        for _ in range(20):
            try:
                if int(d.cmd("get wrCount", 5.0).get("count", 0)) > 0:
                    break
            except Exception:
                pass
            time.sleep(3.0)
        notes["stations"] = int(d.cmd("get wrCount", 5.0).get("count", 0))
        # resume() auto-plays only with webRadioAutoplay + STOPPED; otherwise tap PLAY.
        if not wr_wait_state(d, 2, timeout=10.0):
            d.cmd(f"tap {PLAY_XY[0]} {PLAY_XY[1]}", 5.0)
            ok = wr_wait_state(d, 2, timeout=60.0)
            notes["play_via_tap"] = True
            if not ok:
                notes["enter_failed_state"] = wr_state(d)
    elif state == "wr_stopped":
        time.sleep(3.0)
        if wr_state(d) != 0:
            d.cmd(f"tap {STOP_XY[0]} {STOP_XY[1]}", 5.0)
            time.sleep(2.0)
            notes["final_wr_state"] = wr_state(d)
    return notes


def capture_window(d: Dut, minutes: float) -> dict:
    """Passive capture: no commands issued mid-window (LL-042 single-reader rule)."""
    out = {"hb": [], "wifi_ev": [], "perf_warn": [], "wr_lines": []}
    d.ser.timeout = 0.5
    deadline = time.monotonic() + minutes * 60.0
    while time.monotonic() < deadline:
        line = d.ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        m = HB_RE.search(line)
        if m:
            out["hb"].append({"t": round(time.monotonic(), 1), **m.groupdict()})
            continue
        if WIFI_EV_RE.search(line):
            out["wifi_ev"].append(line)
        elif PERF_WARN_RE.search(line):
            out["perf_warn"].append(line)
        elif WR_LOG_RE.search(line):
            out["wr_lines"].append(line)
    return out


def one_tap(d: Dut, state: str, slot: int) -> dict:
    """Injected taskbar drag-tap; returns drain_ms + entered_ms (or error markers)."""
    y = slot * TASKBAR_SLOT_H + TASKBAR_SLOT_H // 2
    d.ser.timeout = 0.2
    t0 = time.monotonic()
    d.send(f"drag {TASKBAR_X_TAP} {y} {TASKBAR_X_TAP} {y + 1} 2")
    # Injection ordering (main.cpp drainInjectionQueue release branch):
    # tbGestureEnd -> switchApp (prints "[shell] entered N") -> renderTaskbar ->
    # drag JSON. So the entered line PRECEDES the JSON; both are measured from t0.
    #   entered_ms = tap-to-switch-committed (doc 3 definition)
    #   drain_ms   = full injection drain incl. taskbar repaint + serial print
    drain_ms = entered_ms = press_ms = commit_ms = None
    phases = None
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        line = d.ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        # TASK-279 lines exist only post-implementation; None on baseline firmware.
        if TB_PRESS_RE.search(line) and press_ms is None:
            press_ms = (time.monotonic() - t0) * 1000.0
            continue
        if TB_COMMIT_RE.search(line) and commit_ms is None:
            commit_ms = (time.monotonic() - t0) * 1000.0
            continue
        m_sw = SWITCH_RE.search(line)
        if m_sw and phases is None:
            phases = {k: int(v) for k, v in m_sw.groupdict().items()}
            continue
        if ENTERED_RE.search(line) and entered_ms is None:
            entered_ms = (time.monotonic() - t0) * 1000.0
            continue
        if line.startswith("{") and '"cmd":"drag"' in line.replace(" ", ""):
            drain_ms = (time.monotonic() - t0) * 1000.0
            break
    res = {"slot": slot, "drain_ms": round(drain_ms, 1) if drain_ms else None,
           "entered_ms": round(entered_ms, 1) if entered_ms else None,
           "press_ms": round(press_ms, 1) if press_ms else None,
           "commit_ms": round(commit_ms, 1) if commit_ms else None,
           "switch_phases": phases}
    # restore state
    enter_state(d, state)
    settle = 12.0 if state == "wr_playing" else 5.0
    time.sleep(settle)
    return res


def med_max(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "median": round(statistics.median(vals), 1),
            "max": round(max(vals), 1)}


def main():
    p = argparse.ArgumentParser(description="E0 shared baseline (TASK-278 E0 + TASK-279 matrix)")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--window-min", type=float, default=10.0)
    p.add_argument("--taps", type=int, default=5)
    p.add_argument("--out", default="e0_results.json")
    p.add_argument("--states", default=",".join(STATES))
    p.add_argument("--any-firmware", action="store_true",
                   help="skip the cyd2usb_winamp_debug ELF/Spotify-poll gate "
                        "(for the cyd2usb_webradio DISABLE_SPOTIFY build)")
    args = p.parse_args()

    DutClass = WatchDut if args.any_firmware else Dut
    d = DutClass(args.port, args.baud, timeout=3.0)
    # Pre-flight WiFi gate (lesson from run 1, 2026-07-03: DUT parked link-DOWN for a
    # full 4-window session — every baseline invalid per the VE-2-1 attribution rule).
    wifi = d.cmd_drain("get wifi", 5.0)
    if not wifi or wifi[0].get("status") != 3:
        raise SystemExit(f"ABORT: WiFi not connected (status != 3): {wifi} — "
                         "fix the link first; a dead-link session baselines nothing.")
    results = {"meta": {"date": time.strftime("%Y-%m-%d %H:%M"), "window_min": args.window_min,
                        "taps": args.taps, "wifi_preflight": wifi,
                        "info": d.cmd_drain("info", 8.0)}}
    try:
        for state in args.states.split(","):
            print(f"\n=== state: {state} ===", flush=True)
            r: dict = {"enter": enter_state(d, state)}
            time.sleep(20.0)  # settle before the window
            r["wifi_start"] = d.cmd_drain("get wifi", 5.0)
            if state == "wr_playing":
                r["underruns_start"] = d.cmd("get wrUnderruns")
                r["wr_state_start"] = wr_state(d)
            print(f"  capturing {args.window_min} min window…", flush=True)
            r["window"] = capture_window(d, args.window_min)
            d.ser.timeout = 3.0
            r["wifi_end"] = d.cmd_drain("get wifi", 5.0)
            if state == "wr_playing":
                r["underruns_end"] = d.cmd("get wrUnderruns")
                r["wr_state_end"] = wr_state(d)
            print(f"  {len(r['window']['hb'])} hb lines, "
                  f"{len(r['window']['wifi_ev'])} wifi-ev, "
                  f"{len(r['window']['perf_warn'])} perf warns", flush=True)
            r["taps"] = [one_tap(d, state, STATE_TAP_SLOT[state]) for _ in range(args.taps)]
            loopmax = [int(h["loopmax"]) for h in r["window"]["hb"]]
            r["summary"] = {
                "loop_max": med_max(loopmax),
                "worst_paths": sorted({h["slow"] for h in r["window"]["hb"]}),
                "drain_ms": med_max([t["drain_ms"] for t in r["taps"]]),
                "entered_ms": med_max([t["entered_ms"] for t in r["taps"]]),
                "press_ms": med_max([t["press_ms"] for t in r["taps"]]),
                "commit_ms": med_max([t["commit_ms"] for t in r["taps"]]),
                "switch_phases": {
                    k: med_max([(t["switch_phases"] or {}).get(k) for t in r["taps"]])
                    for k in ("suspend", "wipe", "init", "taskbar", "total")},
            }
            print(f"  summary: {json.dumps(r['summary'])}", flush=True)
            results[state] = r
    finally:
        try:
            d.cmd(f"switchApp {APP_SPOTIFY}", 5.0)  # leave DUT on the player slot
        except Exception:
            pass
        d.close()
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
        print(f"\nresults -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
