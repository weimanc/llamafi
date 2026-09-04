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
    python3 tools/suite/serialdbg/runner.py --scope LocalPlayer
    python3 tools/suite/serialdbg/runner.py --scope app/src/apps/clockApp.cpp

`--scope` (TASK-570, M-TESTARCH §13.4) selects by the registry's `scope` field
instead of by a literal id list — either a scope name or the path of the file
you changed. `--class`/`--upto` are deliberately NOT implemented: @PM cut both
from TASK-570 on all three reviewers' recommendation (design §20).

CLASS ORDERING (TASK-566, M-TESTARCH §4) LANDS HERE BUT IS **OFF BY DEFAULT**.
`--class-order` (or `DUT_CLASS_ORDER=1`) runs the HEALTH gate first, executes
classes ascending, records blocked ids as `NOT-RUN` and exits 4 on a HEALTH
failure. Without it this file behaves EXACTLY as it did before: registry order,
no health phase, no blocking, exit 0/1/3. That is deliberate — @PM's ruling on
the TASK-566 row puts the inert landing, the order diff and the baseline in this
block and HOLDS the switch itself until TASK-557 closes or signs off, with @VE's
three preconditions (§18.6) on top. `--order-diff` prints what the switch WOULD
change, with no port and no DUT (EC-G9).

Passive triage (mode P, TASK-571, M-TESTARCH §14.2/EC-T1) is ALWAYS ON and has
no flag: every FAIL carries the session health verdict, `last-phase=`, `gen=`
and the id's own `(cls, scope)`, read from what the session already observed.
Modes D (`--triage`, in-session descent) and I (`--isolate-on-fail`) are CUT
(design §20) — there is no flag, no stub and no code path for either.

Requirements:
    pip install pyserial
    DUT flashed with cyd2usb_winamp_debug (or another testable variant —
    set DUT_ENV, e.g. DUT_ENV=cyd2usb_player), booted, WiFi up, Spotify
    creds valid. T089 (production ELF symbol check) is a host build
    check — not run here. T095 (physical vs. synthetic calibration)
    requires --interactive (human at DUT).
"""

import argparse
import os
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

from lib.dut import (Dut, SetupFailure, cls_for_reason, resolve_port,     # noqa: E402
                     set_no_wifi)
import lib.dut as _dut_mod                                               # noqa: E402
from lib.results import fail, unmet, run_with_flake_retry                # noqa: E402

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")

import suite.serialdbg as _suite                                          # noqa: E402
from suite.serialdbg import _gate, _meta, _order, _triage, health as _health  # noqa: E402
from suite.serialdbg.shell import t093, t094, t095                        # noqa: E402

SETUP_FAIL_EXIT = 3
#: "The board is not a valid subject" (§4 rule 3). Reached by `run/dut-health`,
#: and — since TASK-566 — by a `--class-order` suite run whose HEALTH gate fails.
#: EC-G7 forbade an exit-4 code path in the suite until every consumer in §4.1
#: understood it, or a HEALTH failure surfaces as `REGRESS` from run/player-gate;
#: that is not hypothetical, it happened for FLAKY-PASS (TASK-573). All four were
#: taught it in TASK-566's commit: run/player-gate (plus a --selftest case),
#: run/test, run/test-targeted, run/test-sync.
HEALTH_FAIL_EXIT = 4


def _port_holders(port: str) -> str:
    """Best-effort: who currently has this port open. Empty string if nobody,
    or if we cannot tell. Used only to make a message accurate, never to
    decide anything."""
    import os
    import shutil
    import subprocess
    if not shutil.which("fuser"):
        return ""
    try:
        real = os.path.realpath(port)
        out = subprocess.run(["fuser", "-v", real], capture_output=True,
                             text=True, timeout=5)
        # fuser prints the table on stderr and exits 1 when nothing holds it.
        return (out.stderr or "").strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _classify_serial_failure(port: str, exc: Exception):
    """Split serial.SerialException into distinguishable rig conditions.

    TASK-556. This used to be one blanket `port-busy` naming the tmux monitor.
    That label is right for genuine contention (LL-054, and the TASK-440
    retraction where the harness had bypassed run/*), but it is wrong — and
    actively misleading — for a device that DISAPPEARED mid-open, which is what
    a CH340 re-enumeration produces. `device reports readiness to read but
    returned no data` is pyserial's message for a tty that hung up: poll() says
    readable, read() returns b''. Reporting that as "another process holds the
    port" sent more than one investigation down the wrong path on 2026-08-31.

    Returns (reason_slug, hint_text).
    """
    import os
    text = str(exc).lower()
    holders = _port_holders(port)

    # The node itself is gone: re-enumeration, unplug, or a stale by-id target.
    if not os.path.exists(port) or not os.path.exists(os.path.realpath(port)):
        return ("device-vanished",
                f"{port} does not resolve to an existing device right now — the "
                f"CH340 re-enumerated or was unplugged mid-run.\n"
                f"Check: ls -l /dev/serial/by-id/ ; dmesg | tail -20\n"
                f"This is NOT port contention; nothing needs killing.")

    # Present, but the fd hung up under us.
    if ("returned no data" in text or "disconnected" in text
            or "errno 19" in text or "no such device" in text):
        hint = (f"The device at {port} went away mid-open (fd hung up), rather "
                f"than being held by someone else — the CH340 re-enumerating "
                f"produces exactly this.\n"
                f"Check: dmesg | grep -i ch341 | tail ; ls -l /dev/serial/by-id/\n"
                f"See TASK-557 for the standing investigation.")
        if holders:
            hint += f"\nNote: something DOES hold the port too:\n{holders}"
        return ("device-vanished", hint)

    if "permission denied" in text or "errno 13" in text:
        return ("port-permissions",
                f"Permission denied opening {port} — check group membership "
                f"(dialout/uucp) rather than assuming contention.")

    # Genuine contention — the original, still-correct case.
    busy_signal = ("busy" in text or "exclusively lock" in text
                   or "errno 16" in text)
    if busy_signal or holders:
        hint = (f"Another process holds {port} — the tmux monitor "
                f"(run/monitor-stop) or a peer session.")
        if holders:
            hint += f"\n{holders}"
        if not busy_signal:
            # Matched on the holder alone. Say so: the exception itself did not
            # report contention, and silently assuming it did is the exact
            # over-broad reasoning TASK-556 exists to remove.
            hint += ("\nNOTE: classified from the holder above, NOT from the "
                     "exception text, which is unrecognised. If killing the "
                     "holder does not fix it, treat the exception as unclassified "
                     "and report it verbatim.")
        return ("port-busy", hint)

    return ("port-error",
            f"Unclassified serial failure on {port}. Neither a vanished device "
            f"nor a detectable holder — report the exception text verbatim.")


#: The closing sentence, SELECTED BY CLASS and never typed at a call site
#: (M-TESTARCH §5 E3 / EC-G1). Before TASK-565 there was one sentence, and it
#: asserted a rig cause for every abort — including `wifi-not-connected`, where
#: the board is demonstrably running firmware and the only thing established is
#: that the DEVICE is unfit to be a subject. That sentence is the artefact §5
#: calls the worst one found: the harness telling the operator that a dead-SSID
#: board is a cable problem.
_CLS_SENTENCE = {
    "RIG": ("This is a RIG condition, not a test result. No tests ran; "
            "nothing here says the firmware is broken."),
    "HEALTH": ("This is a HEALTH condition, not a test result: the board is "
               "running, it answered (or failed to finish booting), and it is "
               "not fit to be a test subject. No tests ran.\n"
               "It is NOT a rig condition — do not blame the cable, the port or "
               "the host until this is resolved. Diagnose the DEVICE: read the "
               "monitor's disk log (run/monitor-read) for the boot above, and "
               "see the last-phase= and gen= stamps in the block above for which "
               "stage of setup() it died in and on which boot."),
}


def _setup_fail(reason: str, message: str, tail=None):
    """Report a setup failure and exit with SETUP_FAIL_EXIT. Never returns.

    The exit code stays 3 for both classes: exit 4 belongs to the suite's HEALTH
    gate (TASK-566) and may not ship before EC-G7's consumers understand it.
    What changes here is the SENTENCE, which is the half that misdirects a
    reader.
    """
    cls = cls_for_reason(reason)
    print("", flush=True)
    print(f"[SETUP-FAIL] {reason}  cls={cls}", flush=True)
    print(message, flush=True)
    if tail:
        print(f"\n--- last {len(tail)} serial lines before the abort ---", flush=True)
        for line in tail:
            print(f"  | {line}", flush=True)
        print("--- end serial tail ---", flush=True)
    print("\n" + _CLS_SENTENCE[cls], flush=True)
    sys.exit(SETUP_FAIL_EXIT)


def main():
    all_tests = _suite.build_all_tests()
    # §4.5: a SEPARATE registry. Not merged into all_tests (every id would then
    # enter default_tests and run twice, the mutating one included) and not
    # merged into default_tests (health runs because the run runs, never because
    # someone selected it) — but resolvable by name, or a health check could not
    # be debugged without running a suite around it.
    health_tests = _suite.build_health_tests()

    p = argparse.ArgumentParser()
    p.add_argument("--port", default=resolve_port())
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0,
                   help="default serial read timeout in seconds")
    p.add_argument("--interactive", action="store_true",
                   help="enable interactive tests (T093/T094/T095 — requires human at DUT)")
    _interactive_tests = {"T093", "T094", "T095"}
    default_tests = ",".join(k for k in all_tests if k not in _interactive_tests)
    p.add_argument("--tests", default=None,
                   help="comma-separated test IDs, e.g. T080,T083,T084")
    p.add_argument("--scope", default=None,
                   help="run only the ids attributed to a scope — either a scope "
                        "name (an app, or shell/boot/taskbar/spotify-chrome/rig) or "
                        "the PATH of a file you changed, e.g. "
                        "--scope app/src/apps/localPlayerApp.cpp. TASK-570 / "
                        "M-TESTARCH §13.4. Combines with --tests (intersection).")
    p.add_argument("--no-wifi", action="store_true",
                   help="proceed even if the DUT never gets an IP. Only for suites that "
                        "touch no network (e.g. the SD-backed T_PLR_08-12).")
    p.add_argument("--dut-health", action="store_true",
                   help="PRE-FLIGHT ONLY: run the HEALTH class (T_DH_01..03) and "
                        "nothing else, print the premise block, exit 0/4. This is "
                        "run/dut-health. Its own port open RESETS the board, so it "
                        "answers 'is this board fit to test NOW', never 'what was "
                        "wrong with the board a minute ago' (M-TESTARCH §5 E4).")
    p.add_argument("--class-order", action="store_true",
                   default=os.environ.get("DUT_CLASS_ORDER", "") == "1",
                   help="THE ORDER SWITCH, and it is HELD (TASK-566 row, @VE "
                        "§18.6). Runs the HEALTH gate first, executes classes "
                        "ascending, records blocked ids NOT-RUN and exits 4 on a "
                        "HEALTH failure. OFF by default: this suite has measured "
                        "order-dependence (TASK-553) and TASK-557 is unresolved. "
                        "Use --order-diff to see what it would change.")
    p.add_argument("--order-diff", action="store_true",
                   help="HOST-ONLY (no port, no DUT, EC-G9): print the "
                        "class-ordered id sequence diffed against today's, the "
                        "inverted pairs, and the 0->1-edge candidates, then exit.")
    p.add_argument("--full", action="store_true",
                   help="--order-diff: list every inverted pair, not just the "
                        "ones touching an edge candidate.")
    p.add_argument("--log-file", default=None,
                   help="append every raw serial line (JSON responses AND bare "
                        "LOG_D/LOG_W lines) to this file — for diagnosing "
                        "failures whose cause isn't visible in dbg command output")
    args = p.parse_args()

    health_mode = os.environ.get("DUT_HEALTH", "gate").strip().lower() or "gate"
    if health_mode not in _gate.HEALTH_MODES:
        sys.exit(f"DUT_HEALTH must be one of {_gate.HEALTH_MODES} (got "
                 f"{health_mode!r})")

    if args.dut_health:
        if args.tests or args.scope:
            sys.exit("--dut-health runs the HEALTH class and nothing else; it "
                     "does not combine with --tests/--scope.")
        selected = []
        health_selected = list(health_tests)
    else:
        selected = [t.strip() for t in (args.tests or default_tests).split(",")
                    if t.strip()]
        # The id resolver looks in BOTH registries (§4.5), so an explicit
        # `--tests T_DH_01` resolves instead of hitting the unknown-id guard.
        # Explicitly-named health ids run in the health phase below, with no
        # flake retry — which is run/dut-health reached by another name.
        health_selected = [t for t in selected if t in health_tests]
        selected = [t for t in selected if t not in health_tests]
        unknown = [t for t in selected if t not in all_tests]
        if unknown:
            sys.exit(f"Unknown tests: {unknown}. Available: "
                     f"{list(all_tests) + list(health_tests)}")

    all_meta = None
    if args.scope:
        # TASK-570 / M-TESTARCH §13.4. Resolve BEFORE opening the port: a typo
        # in a selector must not cost a board reset to find out about.
        try:
            scope = _meta.resolve_selector(args.scope)
        except ValueError as e:
            sys.exit(f"--scope: {e}")
        all_meta = _suite.build_all_meta()
        in_scope = [t for t in selected if all_meta[t]["scope"] == scope]
        if not in_scope:
            sys.exit(f"--scope {args.scope} -> scope '{scope}' selects none of the "
                     f"{len(selected)} candidate ids. Scopes present: "
                     + ", ".join(sorted({r['scope'] for r in all_meta.values()})))
        print(f"[scope] {args.scope} -> {scope}: {len(in_scope)} of {len(selected)} ids")
        selected = in_scope

    if args.order_diff:
        # EC-G9, and it costs ZERO DUT time — which is the entire argument for
        # landing the classification inert first (§6 R3). Placed before the port
        # is opened so it never resets a board.
        meta = all_meta if all_meta is not None else _suite.build_all_meta()
        print(_order.order_diff_report(selected, meta, all_tests,
                                       full_pairs=args.full))
        sys.exit(0)

    if all_meta is None:
        # Mode P needs the record too. Build it BEFORE the port is opened: a
        # registry error must not cost a board reset to discover, and it is the
        # same reason --scope resolves its selector up here.
        try:
            all_meta = _suite.build_all_meta()
        except Exception as e:
            print(f"[triage] registry unavailable ({type(e).__name__}: {e}) — "
                  f"FAILs will carry no (cls, scope)")
            all_meta = {}

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
        _reason, _hint = _classify_serial_failure(args.port, e)
        _setup_fail(_reason, f"{e}\n{_hint}")
    except TimeoutError as e:
        # TASK-560. Dut.__init__'s _verify_debug_firmware() raises a bare
        # TimeoutError when the board never answers `get heap`. That is a rig
        # condition like any other, but as a TimeoutError it skipped this
        # classifier entirely and surfaced as an unlabelled traceback with exit
        # 1 instead of a [SETUP-FAIL] block with exit 3 — the exact legibility
        # hole TASK-434 was written to close, on a path nobody had enumerated.
        _setup_fail("dut-unresponsive",
                    f"{e}\n"
                    f"The DUT did not answer the post-open firmware probe. "
                    f"Usually it is mute (wedged, wrong firmware, or the open's "
                    f"reset did not take) rather than contended.\n"
                    f"Check: dmesg | tail ; ls -l /dev/serial/by-id/")
    # Mode P (TASK-571): from here on every FAIL carries the session's health
    # verdict, last-phase, gen tag and the id's (cls, scope). Installed after
    # the Dut exists and before any test runs, so no FAIL can escape without it.
    _triage.install(dut, all_meta)

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
    # E5 / EC-G5: every DUT run's first output block states its own premise, so
    # a retrospective claim about the board is checkable against the run's own
    # artefact rather than against memory. Read-only, best-effort, ~1 s. The
    # switch verdict is T_DH_03's when the health phase runs and `not-run`
    # otherwise — the unconditional gate that would always run it is TASK-566.
    _gate_on = args.class_order and not args.dut_health
    if _gate_on and health_mode != "skip":
        health_selected = list(health_tests)
    print(_health.premise(dut, switch_verdict="pending" if health_selected
                          else "not-run(no-health-phase;TASK-566)"), flush=True)

    health_failed = []
    if health_selected and not _gate_on:
        # Explicitly-named health ids, with no gate phase: run/dut-health reached
        # by another name (§4.5). The gate phase itself lives in _gate.run_suite.
        print(f"\n── HEALTH class ── {health_selected}")
        health_failed = _health.run_health(dut, health_selected)
        sw = _triage.health_verdict(all_meta)
        print(_health.premise(dut, switch_verdict=sw), flush=True)

    if args.dut_health:
        dut.close()
        print(f"\n{_health.RESET_WARNING}")
        if health_failed:
            print(f"\n[HEALTH-FAIL] {','.join(health_failed)} — this board is NOT "
                  f"a valid test subject right now. Every result a suite produced "
                  f"against it would be uninterpretable.", flush=True)
            sys.exit(HEALTH_FAIL_EXIT)
        print("\n[health] PASS — the board answers correct data, knows which "
              "network it is on, and can switch apps. It is fit to test.",
              flush=True)
        sys.exit(0)

    print(f"Connected. Running: {selected}\n")
    print("NOTE: T089 (production ELF check) is a host build test — not here.")
    skip_notice = [t for t in selected if t in _interactive_tests and not args.interactive]
    if skip_notice:
        print(f"NOTE: {skip_notice} will SKIP — re-run with --interactive.\n")
    else:
        print()

    def _dispatch(tid):
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
            # TASK-596 / R18. These two arms must precede the generic ones:
            # both are RuntimeErrors and would otherwise land in `except
            # Exception` as an undifferentiated FAIL, which is the reporting
            # half of the defect the typed read exists to remove.
            except _dut_mod.NoAnswer as e:
                # The device never answered THIS question, so the body asserted
                # nothing. Its premise did not hold — that is an UNMET, which
                # still blocks and still exits 1 (ADR-066 D4), so nothing is
                # weakened; what changes is that triage is not told the firmware
                # regressed when the serial line was busy.
                unmet(tid, str(e))
            except _dut_mod.BadField as e:
                # It answered, and the answer breaks the contract: a renamed key,
                # a changed reply shape, a wrong-typed value. Reproducible, and
                # somebody's code is wrong.
                fail(tid, f"contract: {e}")
            except TimeoutError as e:
                fail(tid, f"TimeoutError: {e}")
            except Exception as e:
                fail(tid, f"Exception: {e}")
        run_with_flake_retry(tid, _once)
        time.sleep(0.5)

    def _exit_snapshot():
        try:
            pm = dut.cmd("get playerMode", timeout=3.0)
            print(f"[TASK-407] exit playerMode: {pm.get('name')} ({pm.get('val')})")
        except Exception as e:
            print(f"[TASK-407] exit playerMode: unavailable ({type(e).__name__})")

    def _run_health(ids):
        # NEVER via run_with_flake_retry (§4.4).
        failed = _health.run_health(dut, ids)
        print(_health.premise(dut, switch_verdict=_triage.health_verdict(all_meta)),
              flush=True)
        return failed

    # TASK-566. With --class-order OFF (the default, and the held state) this is
    # today's loop byte-for-byte: registry order, no health phase, no blocking,
    # print_results()'s own 0/1. Everything the switch adds is inside run_suite.
    rc = _gate.run_suite(
        selected, all_meta, _dispatch,
        class_order=_gate_on,
        health_ids=list(health_tests) if _gate_on else (),
        run_health=_run_health if _gate_on else None,
        health_mode=health_mode,
        before_summary=_exit_snapshot,
        exit_on_finish=False,
        emit=lambda *a: print(*a, flush=True))

    dut.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
