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

    # ── TASK-565 / EC-G1: the closing sentence is SELECTED BY CLASS ─────────
    # Before this, every abort printed "This is a RIG condition ... nothing here
    # says the firmware is broken" — including `wifi-not-connected`, where the
    # board is demonstrably running firmware and the only thing established is
    # that the DEVICE is unfit. §5 calls that the worst artefact found: the
    # harness telling the operator that a dead-SSID board is a cable problem.
    print("\n-- setup-failure class (TASK-565 / EC-G1) --")
    from lib.dut import SetupFailure, cls_for_reason        # noqa: E402
    for reason in ("device-vanished", "port-busy", "port-permissions",
                   "port-error", "port-ambiguous", "boot-not-observed",
                   "elf-mismatch", "prod-firmware-flashed", "dut-unresponsive"):
        check(f"{reason} -> RIG", cls_for_reason(reason), "RIG")
    for reason in ("boot-phase-timeout", "shell-unresponsive",
                   "wifi-not-connected"):
        check(f"{reason} -> HEALTH", cls_for_reason(reason), "HEALTH")
    check("an unknown reason falls back to RIG, the conservative answer",
          cls_for_reason("some-future-slug"), "RIG")
    # Derived at construction, never typed at a raise site.
    check("SetupFailure derives cls from the reason",
          SetupFailure("wifi-not-connected", "x").cls, "HEALTH")
    check("cls is in the stamped trailer",
          "cls=HEALTH" in str(SetupFailure("wifi-not-connected", "x")
                              .stamp("3 wifi", "7.1")), True)
    # The sentence itself: a HEALTH abort must not tell the reader it is a rig
    # condition, and must not claim nothing is wrong with the firmware.
    check("every class has a sentence",
          sorted(runner._CLS_SENTENCE), ["HEALTH", "RIG"])
    _hs = runner._CLS_SENTENCE["HEALTH"]
    check("HEALTH sentence does not call itself a RIG condition",
          "RIG condition" in _hs, False)
    check("HEALTH sentence says it is not a rig condition",
          "NOT a rig condition" in _hs, True)

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
