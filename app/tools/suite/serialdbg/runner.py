#!/usr/bin/env python3
"""
suite/serialdbg — the serialdbg-001 regression suite's CLI entry point.

Runs the DUT test suite assembled by suite/serialdbg/__init__.py's
build_all_tests() from each family module's own TESTS dict. This replaces
run_serialdbg_tests.py (TASK-480 final step — see M-TOOLING-host-tool-
architecture.md §3/§6), which stayed the live entry point throughout the
staged family-by-family migration and is now deleted; this file mirrors
its main() unchanged in behavior (same --port/--tests/--interactive/
--no-wifi/--log-file flags, same flake-retry and TASK-407 playerMode
snapshot, same TASK-386 per-test serial marker).

Usage:
    python3 tools/suite/serialdbg/runner.py [--port /dev/ttyUSB0] [--tests T077,T080,T084]
    python3 tools/suite/serialdbg/runner.py --interactive --tests T095

Requirements:
    pip install pyserial
    DUT flashed with cyd2usb_winamp_debug (or another testable variant —
    set DUT_ENV, e.g. DUT_ENV=cyd2usb_player), booted, WiFi up, Spotify
    creds valid. T089 (production ELF symbol check) is a host build
    check — not run here. T095 (physical vs. synthetic calibration)
    requires --interactive (human at DUT).
"""

import argparse
import pathlib
import sys
import time

# app/tools/ is the importable root every family module's top-level imports
# assume (`from lib.dut import Dut`, `import coords as _c`, ...) — this file
# lives three directories below it (suite/serialdbg/runner.py), so it takes
# three .parent hops to reach app/tools/, not one (LL-114/TASK-480: got this
# wrong once already for shell.py's T133 static-source path, same class of
# mistake, caught here before it repeats).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from lib.dut import Dut, SetupFailure, resolve_port, set_no_wifi           # noqa: E402
from lib.results import fail, run_with_flake_retry, print_results         # noqa: E402

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")

import suite.serialdbg as _suite                                          # noqa: E402
from suite.serialdbg.shell import t093, t094, t095                        # noqa: E402

SETUP_FAIL_EXIT = 3


def _setup_fail(reason: str, message: str, tail=None):
    """Report a rig condition and exit with SETUP_FAIL_EXIT. Never returns."""
    print("", flush=True)
    print(f"[SETUP-FAIL] {reason}", flush=True)
    print(message, flush=True)
    if tail:
        print(f"\n--- last {len(tail)} serial lines before the abort ---", flush=True)
        for line in tail:
            print(f"  | {line}", flush=True)
        print("--- end serial tail ---", flush=True)
    print("\nThis is a RIG condition, not a test result. No tests ran; "
          "nothing here says the firmware is broken.", flush=True)
    sys.exit(SETUP_FAIL_EXIT)


def main():
    all_tests = _suite.build_all_tests()

    p = argparse.ArgumentParser()
    p.add_argument("--port", default=resolve_port())
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0,
                   help="default serial read timeout in seconds")
    p.add_argument("--interactive", action="store_true",
                   help="enable interactive tests (T093/T094/T095 — requires human at DUT)")
    _interactive_tests = {"T093", "T094", "T095"}
    default_tests = ",".join(k for k in all_tests if k not in _interactive_tests)
    p.add_argument("--tests", default=default_tests,
                   help="comma-separated test IDs, e.g. T080,T083,T084")
    p.add_argument("--no-wifi", action="store_true",
                   help="proceed even if the DUT never gets an IP. Only for suites that "
                        "touch no network (e.g. the SD-backed T_PLR_08-12).")
    p.add_argument("--log-file", default=None,
                   help="append every raw serial line (JSON responses AND bare "
                        "LOG_D/LOG_W lines) to this file — for diagnosing "
                        "failures whose cause isn't visible in dbg command output")
    args = p.parse_args()

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in all_tests]
    if unknown:
        sys.exit(f"Unknown tests: {unknown}. Available: {list(all_tests)}")

    print(f"Connecting to {args.port} @ {args.baud}…")
    if args.log_file:
        print(f"Raw serial log: {args.log_file}")
    if args.no_wifi:
        set_no_wifi(True)
    try:
        dut = Dut(args.port, args.baud, timeout=args.timeout, log_file=args.log_file)
    except SetupFailure as e:
        _setup_fail(e.reason, str(e), getattr(e, "tail", None))
    except serial.SerialException as e:
        _setup_fail("port-busy", f"{e}\n"
                    f"Another process holds {args.port} — the tmux monitor "
                    f"(run/monitor-stop) or a peer session.")
    # Warmup ping: flush any residual DUT serial output before first test.
    try:
        dut.cmd("help", timeout=4.0)
    except Exception:
        pass
    try:
        pm = dut.cmd("get playerMode", timeout=3.0)
        print(f"[TASK-407] entry playerMode: {pm.get('name')} ({pm.get('val')})")
    except Exception as e:
        print(f"[TASK-407] entry playerMode: unavailable ({type(e).__name__})")
    print(f"Connected. Running: {selected}\n")
    print("NOTE: T089 (production ELF check) is a host build test — not here.")
    skip_notice = [t for t in selected if t in _interactive_tests and not args.interactive]
    if skip_notice:
        print(f"NOTE: {skip_notice} will SKIP — re-run with --interactive.\n")
    else:
        print()

    for tid in selected:
        try:
            dut.cmd(f"get __TEST_{tid}__", timeout=2.0)
        except TimeoutError:
            pass
        def _once(tid=tid):
            try:
                if tid == "T093":
                    t093(dut, args.interactive)
                elif tid == "T094":
                    t094(dut, args.interactive)
                elif tid == "T095":
                    t095(dut, args.interactive)
                else:
                    all_tests[tid](dut)
            except TimeoutError as e:
                fail(tid, f"TimeoutError: {e}")
            except Exception as e:
                fail(tid, f"Exception: {e}")
        run_with_flake_retry(tid, _once)
        time.sleep(0.5)

    try:
        pm = dut.cmd("get playerMode", timeout=3.0)
        print(f"[TASK-407] exit playerMode: {pm.get('name')} ({pm.get('val')})")
    except Exception as e:
        print(f"[TASK-407] exit playerMode: unavailable ({type(e).__name__})")

    dut.close()
    print_results()


if __name__ == "__main__":
    main()
