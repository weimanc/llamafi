#!/usr/bin/env python3
"""test_serial_classify.py — TASK-556's serial-failure classifier.

Host-only, no DUT, sub-second. Wired into smoke_test.sh.

Why this exists: `runner.py` used to label EVERY serial.SerialException
`port-busy` and name the tmux monitor. That is correct for genuine contention
(LL-054) and wrong for a device that vanished mid-open, which is what a CH340
re-enumeration produces. On 2026-08-31 the wrong label sent the same
investigation down the wrong path more than once.

`_port_holders` is stubbed in every case. Without that, results depend on
whether a serial monitor happens to be running on the machine — which is
exactly the confound that made the first manual check of this code misreport.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import serial  # noqa: E402

from suite.serialdbg import runner  # noqa: E402

REAL = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
GONE = "/dev/ttyUSB-does-not-exist-99"

_failures = []


def check(label: str, got, want):
    if got != want:
        _failures.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got}")


def classify(port, msg, holders=""):
    """Classify with _port_holders stubbed to a known value."""
    orig = runner._port_holders
    runner._port_holders = lambda _p: holders
    try:
        return runner._classify_serial_failure(port, serial.SerialException(msg))
    finally:
        runner._port_holders = orig


def main() -> int:
    print("test_serial_classify.py — TASK-556 classifier")

    # A device node that does not resolve at all -> vanished, regardless of
    # what the exception said and regardless of holders.
    r, h = classify(GONE, "could not open port")
    check("missing node -> device-vanished", r, "device-vanished")
    check("missing node hint disclaims contention",
          "NOT port contention" in h, True)

    # The exact pyserial message for a tty that hung up under us. This is the
    # one that was being reported as port-busy.
    HUNGUP = ("device reports readiness to read but returned no data "
              "(device disconnected or multiple access on port?)")
    r, _ = classify(REAL, HUNGUP)
    check("hung-up fd -> device-vanished", r, "device-vanished")

    # Note the message names both 'disconnected' AND 'multiple access', so a
    # naive substring match on the latter would classify it as contention.
    # Vanished must win.
    r, _ = classify(REAL, HUNGUP, holders="pid 123 pio")
    check("hung-up fd wins over a present holder", r, "device-vanished")

    # ...but the holder is still reported, because it is true and useful.
    _, h = classify(REAL, HUNGUP, holders="pid 123 pio")
    check("hung-up fd still surfaces the holder", "pid 123 pio" in h, True)

    r, _ = classify(REAL, "[Errno 13] Permission denied")
    check("permission denied -> port-permissions", r, "port-permissions")

    r, _ = classify(REAL, "[Errno 16] Device or resource busy")
    check("busy errno -> port-busy", r, "port-busy")

    r, _ = classify(REAL, "could not exclusively lock port")
    check("exclusive lock -> port-busy", r, "port-busy")

    # Unrecognised text and nobody holding it: must NOT be guessed as busy.
    r, _ = classify(REAL, "something entirely unrecognised", holders="")
    check("unknown + no holder -> port-error", r, "port-error")

    # Unrecognised text but somebody IS holding it: port-busy is defensible,
    # but the message must say the call came from the holder, not the text.
    r, h = classify(REAL, "something entirely unrecognised",
                    holders="pid 456 pio")
    check("unknown + holder -> port-busy", r, "port-busy")
    check("unknown + holder discloses holder-based call",
          "NOT from the exception text" in h, True)

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} case(s)")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("PASS: all classifier cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
