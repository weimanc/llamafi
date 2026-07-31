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
    a = ap.parse_args()

    s = serial.Serial(); s.port = a.port; s.baudrate = 115200; s.timeout = 1.0
    s.dtr = False; s.rts = False
    s.open()  # opening asserts DTR -> board resets -> fresh boot
    dl = time.monotonic() + 60
    while time.monotonic() < dl:
        if "IP address:" in s.readline().decode(errors="replace"):
            print("[ready]"); break
    else:
        print("[warn] no IP banner seen; continuing")

    def send(c): s.write((c + "\n").encode()); s.flush()

    print(f">> switchApp {APP_TELETEXT} (Teletext / Ceefax)")
    send(f"switchApp {APP_TELETEXT}"); time.sleep(1)

    ever_conn = ever_acq = crashed = False
    t0 = time.monotonic(); last_poll = 0.0
    KEYS = ("wsdbg", "wstype", "ceefax", "guru", "rst:", "panic", "-32512", "connect")
    while time.monotonic() - t0 < a.secs:
        l = s.readline().decode(errors="replace").rstrip()
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
                x = s.readline().decode(errors="replace").strip()
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
