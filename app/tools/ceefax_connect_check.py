#!/usr/bin/env python3
"""TASK-376 — does Ceefax actually CONNECT + acquire a page on the DUT?

Patient functional check (the test M-CEEFAX's close-out originally skipped).
From a fresh boot: switch to the Teletext app (Ceefax backend), poll
`get ceefaxStatus`, and capture the WebSocket connect flow. Reports whether
`connected` and `acquired` ever go true, and flags any crash/reboot.

Requires debug firmware for the richest logs (./run/flash-debug), but the
connected/acquired verdict works on prod too (get ceefaxStatus ships).

Usage:
  python3 app/tools/ceefax_connect_check.py [--port /dev/ttyUSB0] [--secs 200]
  # resolve the CH340 port first if it flapped:  ./run/port

Interpreting results (see TASK-376):
  - never "connect() start"      -> gate never opened / pump not attempting
  - "connect() FAILED" repeated  -> TCP-stage failure (DNS? TCP? relay IP block?
                                     verify the relay is up from host with curl)
  - "connect() OK" then no        -> handshake-completion bug (servicing window):
    WStype_CONNECTED               the 101 upgrade isn't serviced in time
  - Guru Meditation / rst:        -> the null-deref crash under contention
"""
import argparse, json, time, sys
try:
    import serial
except ImportError:
    sys.exit("pyserial not found — use the project venv (~/proj/esp/venv/bin/python3)")

APP_TELETEXT = 8

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0", help="CH340 port (resolve via ./run/port)")
    ap.add_argument("--secs", type=int, default=200, help="observation window after switch")
    ap.add_argument("--no-reset", action="store_true",
                    help="don't toggle DTR/RTS (avoids CH340 re-enumeration flap on some "
                         "rigs); run right after ./run/flash-debug, which already leaves a "
                         "fresh boot. Waits for the periodic heartbeat instead of the IP banner.")
    a = ap.parse_args()

    # Open with the plain constructor (default DTR/RTS) — on this CYD's CH340
    # adapter, pre-setting dtr=False/rts=False *before* open() intermittently
    # latches GPIO0 low and drops the board into download mode (silent port ->
    # SerialException on the first read).
    s = serial.Serial(a.port, 115200, timeout=1.0)
    if not a.no_reset:
        # Reliable RUN-mode reset (matches esptool's hard_reset): DTR low keeps
        # GPIO0 HIGH (run, not download); pulse EN via RTS low->high. On a flaky
        # CH340 rig this pulse can re-enumerate the port — use --no-reset there.
        s.dtr = False        # GPIO0 HIGH -> normal boot
        s.rts = True         # EN LOW  -> hold in reset
        time.sleep(0.15)
        s.rts = False        # EN HIGH -> release, boots to run mode
        time.sleep(0.05)
    try: s.reset_input_buffer()
    except Exception: pass
    # With --no-reset the board is already up, so the "IP address:" banner has
    # long scrolled past; the heartbeat line ("[hb]") is the readiness signal.
    ready_markers = ("IP address:",) if not a.no_reset else ("IP address:", "[hb] ")
    dl = time.monotonic() + 60
    while time.monotonic() < dl:
        try:
            line = s.readline().decode(errors="replace")
        except serial.SerialException:
            # transient glitch right after the EN pulse — tolerate and retry
            time.sleep(0.2); continue
        if any(m in line for m in ready_markers):
            print("[ready]"); break
    else:
        print("[warn] no readiness marker seen; continuing")

    def send(c): s.write((c + "\n").encode()); s.flush()

    print(f">> switchApp {APP_TELETEXT} (Teletext / Ceefax)")
    send(f"switchApp {APP_TELETEXT}"); time.sleep(1)

    ever_conn = ever_acq = crashed = False
    t0 = time.monotonic(); last_poll = 0.0
    KEYS = ("wsdbg", "wstype", "ceefax", "guru", "rst:", "panic", "-32512", "connect")
    while time.monotonic() - t0 < a.secs:
        try:
            l = s.readline().decode(errors="replace").rstrip()
        except serial.SerialException:
            # a hard crash/reboot can glitch the USB-UART mid-read; count it as
            # a crash rather than aborting the run, then keep observing.
            crashed = True; time.sleep(0.2); continue
        if l and '"var"' not in l and any(k in l.lower() for k in KEYS):
            print(f"  [{time.monotonic()-t0:5.0f}s] {l}", flush=True)
            if "guru" in l.lower() or "rst:" in l.lower(): crashed = True
        if time.monotonic() - last_poll >= 4:
            last_poll = time.monotonic()
            try: s.reset_input_buffer()
            except Exception: pass
            send("get ceefaxStatus")
            d = {}; dl2 = time.monotonic() + 2
            while time.monotonic() < dl2:
                try:
                    x = s.readline().decode(errors="replace").strip()
                except serial.SerialException:
                    crashed = True; break
                if x.startswith("{") and "ceefaxStatus" in x:
                    try: d = json.loads(x); break
                    except json.JSONDecodeError: pass
            if d:
                c, ac = d.get("connected"), d.get("acquired")
                print(f"  [{time.monotonic()-t0:5.0f}s] STATUS connected={c} acquired={ac} "
                      f"hasError={d.get('hasError')} freeDma={d.get('dmaFree')}", flush=True)
                ever_conn = ever_conn or bool(c)
                ever_acq  = ever_acq  or bool(ac)

    print("\n===== VERDICT =====")
    print(f"ever connected:     {ever_conn}")
    print(f"ever acquired page: {ever_acq}")
    print(f"crashed/rebooted:   {crashed}")
    s.close()
    sys.exit(0 if (ever_conn and ever_acq and not crashed) else 1)

if __name__ == "__main__":
    main()
