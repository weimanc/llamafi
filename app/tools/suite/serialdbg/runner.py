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

THE HEALTH PHASE ALONE (TASK-597, E-13) IS A SEPARATE SWITCH, also off by
default. `--health-phase` (or `DUT_HEALTH_PHASE=1`) runs the same HEALTH gate
and the same exit-4/NOT-RUN blocking as `--class-order` does, honouring
`DUT_HEALTH=gate|warn|skip` — WITHOUT reordering ids or turning on CORE-class
blocking. It exists because `--class-order` is held (TASK-617 RULED
2026-09-03) and `run/player-gate` needs the HEALTH gate itself to be real
without pre-empting that hold. **No caller passes it yet** — wiring
`run/player-gate` is the rest of TASK-597 and is held pending a hardware
run, because the health phase adds preconditions (network in `T_DH_02`, an
app-switch excursion in the mutating `T_DH_03`) that a local-playback gate
did not have before. `--class-order` still implies the
health phase, unchanged; the two flags combine if both are given.

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
from lib.results import (print_results,                                  # noqa: E402
                         run_with_flake_retry, set_exchange_provider,
                         set_meta_provider, set_premise_provider)
import lib.armed as _armed                                                # noqa: E402
import lib.replay as _replay                                             # noqa: E402
import lib.dispatch as _dispatch_mod                                     # noqa: E402

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


def select_health_ids(health_tests, spec):
    """The HEALTH ids a run will gate on. Pure, so it can be tested (TASK-597).

    `spec` is `--health-ids`' comma-separated string, or None for the whole
    class. An id that is not in the HEALTH class is a USAGE ERROR, not a silent
    narrowing: a run that checked fewer premises than it was told to, and said
    nothing, is the same shape as the C-4 banner this programme has already
    fixed once. Order follows `health_tests`, not the spec, so the class's own
    ordering constraint survives (ADR-064 D4 puts T_DH_05 before the mutating
    T_DH_03).
    """
    if not spec:
        return list(health_tests)
    want = [t.strip() for t in spec.split(",") if t.strip()]
    unknown = [t for t in want if t not in health_tests]
    if unknown:
        raise SystemExit(f"--health-ids: not in the HEALTH class: {unknown}. "
                         f"Available: {list(health_tests)}")
    return [t for t in health_tests if t in want]


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
    p.add_argument("--health-phase", action="store_true",
                   default=os.environ.get("DUT_HEALTH_PHASE", "") == "1",
                   help="TASK-597: run the HEALTH class (T_DH_01..03) as a "
                        "gate before the selected ids, honouring DUT_HEALTH="
                        "gate|warn|skip, and exit 4 on a blocking HEALTH "
                        "verdict with every other selected id recorded "
                        "NOT-RUN(blocked-by=HEALTH/<id>). INDEPENDENT of "
                        "--class-order (the held TASK-566 switch): this flag "
                        "does NOT reorder ids or turn on CORE-class blocking, "
                        "it only makes the HEALTH gate itself real. "
                        "--class-order already implies this phase, same as "
                        "before; the two combine (health gate, then class "
                        "order) if both are given.")
    p.add_argument("--health-ids", default=os.environ.get("DUT_HEALTH_IDS") or None,
                   metavar="IDS",
                   help="TASK-597/EXP-040: restrict --health-phase to this "
                        "comma-separated subset of the HEALTH class. A caller "
                        "asks only for the premises it actually needs: "
                        "run/player-gate takes T_DH_01,T_DH_03 because it "
                        "exercises local SD playback and mode switching, and a "
                        "network premise it never needed could only refuse it. "
                        "Unknown or non-HEALTH ids are a usage error, not a "
                        "silent narrowing. Default: the whole class.")
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
    p.add_argument("--record", default=os.environ.get("SERIALDBG_RECORD_DIR") or None,
                   metavar="DIR",
                   help="TASK-671: opt-in per-test transcript recording, via "
                        "lib/replay.py's `recording()`/`Transcript.save()`. Each "
                        "test id's session (not the `get __TEST_<id>__` marker) "
                        "is recorded and saved to DIR/<id>.json. Off by default; "
                        "env SERIALDBG_RECORD_DIR is the default when the flag "
                        "is omitted. Health ids are never recorded. Never "
                        "affects a verdict: a save failure is printed and "
                        "swallowed.")
    p.add_argument("--no-armed-check", action="store_true",
                   default=os.environ.get("DUT_ARMED_CHECK", "1") == "0",
                   help="TASK-635/R14: the armed-state boundary check "
                        "(`get armed` after every id, FAIL the id that leaked "
                        "an injector, `set injclear`) is ON by default. This "
                        "flag (or DUT_ARMED_CHECK=0) turns it off — e.g. to "
                        "run against firmware from before TASK-635 without "
                        "the once-per-run 'unsupported' notice, or while "
                        "diagnosing whether a FAIL came from the check itself.")
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

    # TASK-631 / Dev D3. The last 20 command/reply pairs, so a FAIL carries the
    # exchanges that led to it instead of sending triage to a serial log that
    # `run/test`'s firmware restore may already have outlived. Installed HERE,
    # after the Dut exists and before any test runs, for the same reason mode P
    # is: no blocking verdict may escape without its context. Costs one
    # `deque.append` per command; nothing is built on a green run.
    _fail_ring = _replay.FailRing().wrap(dut)
    set_exchange_provider(_fail_ring.snapshot)

    # TASK-608 / R30 / ADR-066 D3. `lib/` never imports a suite (M-TOOLING), so
    # the premise fields only this layer can know are INSTALLED, exactly as
    # _triage.install() installs the mode-P context above. Closures, not a
    # snapshot: `_gate.EXECUTED_ORDER` and the generation tag are not known yet
    # and are read when the artifact is built.
    set_meta_provider(lambda: all_meta)
    set_premise_provider(lambda: {
        "entry_point": "suite/serialdbg/runner.py",
        "argv": sys.argv[1:],
        "elf": getattr(dut, "elf", None),
        "elf_expected": getattr(dut, "elf_expected", None),
        "build_env": getattr(dut, "build_env", None),
        # TASK-645 / ADR-066 D3. Was `{port, baud}` — a fact about the cable,
        # which a USB re-enumeration invalidates and a second board can
        # duplicate. `Dut.board()` puts the efuse MAC in the identity position
        # and demotes the transport to where it belongs.
        "board": dut.board(),
        "generation": dut.gen_tag(),
        "class_order_in_force": _gate.ORDER_IN_FORCE,
        "class_order": list(_gate.EXECUTED_ORDER),
        "selection": {
            "ids": list(selected),
            # WHY these ids — R30 asks for the reason, not just the set, and
            # "what did this run actually choose to look at" is the question a
            # later reader cannot reconstruct from the id list alone.
            "reason": ("--tests" if args.tests else
                       f"--scope {args.scope}" if args.scope else
                       "default (every registered id)"),
            "interactive": bool(args.interactive),
        },
        # A downgraded gate must never be silently absent from a result someone
        # later cites (the same reasoning as _gate's summary stamp).
        "downgraded_gates": ([f"DUT_HEALTH={health_mode}"]
                             if health_mode != "gate" else []),
    })

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
    #
    # `_gate_on` controls ONLY class ordering + CORE blocking (TASK-566, still
    # held OFF by default). `_health_on` controls whether the HEALTH class runs
    # as a gate (TASK-597): --class-order implies it, same as before, but
    # --health-phase now gets it WITHOUT adopting class ordering — that
    # independence is the whole point of this flag (TASK-597, not a TASK-566
    # widening).
    _gate_on = args.class_order and not args.dut_health
    _health_on = (args.class_order or args.health_phase) and not args.dut_health
    if _health_on and health_mode != "skip":
        health_selected = select_health_ids(list(health_tests), args.health_ids)
    print(_health.premise(dut, switch_verdict="pending" if health_selected
                          else "not-run(no-health-phase;TASK-566)"), flush=True)

    health_failed = []
    # Bound unconditionally: `health_selected` is `list(health_tests)` on the
    # --dut-health path, and `build_health_tests()` resolving empty is exactly
    # the case `_triage` has a word for. Leaving `sw` to the branch below made
    # the C-4 banner a NameError in that case instead of an honest verdict.
    sw = "unavailable(no-HEALTH-class;TASK-565)"
    if health_selected and not _health_on:
        # Explicitly-named health ids, with no gate phase: run/dut-health reached
        # by another name (§4.5). The gate phase itself lives in _gate.run_suite.
        print(f"\n── HEALTH class ── {health_selected}")
        health_failed = _health.run_health(dut, health_selected)
        sw = _triage.health_verdict(all_meta)
        print(_health.premise(dut, switch_verdict=sw), flush=True)

    if args.dut_health:
        dut.close()
        print(f"\n{_health.RESET_WARNING}")
        # TASK-645 / R29: "EVERY run MUST emit a schema-versioned artifact".
        # This path used to `sys.exit()` from here, three lines before
        # `print_results` — so `run/dut-health`, the one entry point whose whole
        # job is to state whether the board is a valid subject, was the only
        # entry point that stated it in prose alone. Its three ids recorded real
        # verdicts and no machine could read them, which is the same shape as
        # the summary-text parsing R29 exists to retire: a verdict that exists
        # and is unreadable.
        #
        # `exit_on_finish=False` because the 0/4 mapping below is this entry
        # point's own contract (`run/dut-health`: 0 fit, 3 rig, 4 not a valid
        # subject) and must not be inferred from bucket counts. `health_fail`
        # carries the exit-4 case into the ARTIFACT as well as the text, so a
        # reader of the artifact alone sees the same verdict a reader of the log
        # does.
        rc = print_results(list(health_selected), exit_on_finish=False,
                           health_fail=(",".join(health_failed) or None))
        if health_failed:
            print(f"\n[HEALTH-FAIL] {','.join(health_failed)} — this board is NOT "
                  f"a valid test subject right now. Every result a suite produced "
                  f"against it would be uninterpretable.", flush=True)
            sys.exit(HEALTH_FAIL_EXIT)
        if rc != 0:
            # Not reachable from a health FAIL (that is the branch above). This
            # is the results layer reporting that its OWN record is broken — an
            # IFC-008 I2/I3 invariant violation. Exiting 0 on it would announce
            # a fit board on the strength of a record the layer just said it
            # cannot vouch for.
            print(f"\n[health] rc={rc} from the results layer — see the "
                  f"[VERDICT-INVARIANT] block above. NOT a statement about the "
                  f"board.", flush=True)
            sys.exit(rc)
        # C-4: this used to be the same literal PASS sentence unconditionally,
        # even when a HEALTH id SKIPped (e.g. T_DH_02 under --no-wifi) — the
        # premise line printed two lines above (`switch={sw}`) would then say
        # `degraded(...)` for the identical run. `sw` is `_triage.health_verdict`
        # for these same ids (always computed above: `health_selected` is
        # unconditional for --dut-health, so the `not _health_on` branch always
        # ran), so the banner and the premise can no longer disagree.
        if sw == "ok":
            print("\n[health] PASS — the board answers correct data, knows which "
                  "network it is on, and can switch apps. It is fit to test.",
                  flush=True)
        else:
            print(f"\n[health] {sw} — no HEALTH id FAILed or was UNMET, so this "
                  f"is not exit 4, but the board was not SHOWN healthy: an id "
                  f"named in the verdict either did not PASS or did not run, so "
                  f"its premise was never established. This is NOT the same "
                  f"claim as '[health] PASS' — see the premise line above and "
                  f"the row(s) in the results.", flush=True)
        sys.exit(0)

    if args.record:
        print(f"[record] transcripts -> {args.record}")
    _record_count = [0]

    # TASK-635/R14: the armed-state boundary check (design §3). `_armed_notify`
    # is a fresh `BoundaryNotifier` per run — its "print once" state must not
    # leak across runner.py invocations (it doesn't; this is a local, not a
    # module global). `_read_armed()` is the only place that talks to the
    # device for this feature, so a TimeoutError (older firmware never answers
    # a var it doesn't have — some builds just hang up rather than answering
    # cmdGet.cpp's unknown-var reply) reduces to the same `None` the unknown-var
    # JSON shape does, via `lib.armed.parse_armed`.
    _armed_notify = _armed.BoundaryNotifier()

    def _read_armed():
        try:
            reply = dut.cmd("get armed", timeout=2.0)
        except Exception:
            # A TimeoutError (older firmware that hangs up instead of
            # answering cmdGet.cpp's unknown-var JSON) must not crash the run
            # or change a verdict — reduce it to the same `None` the
            # unknown-var reply shape produces (design §3).
            reply = None
        return _armed.parse_armed(reply), reply

    def _issue_injclear(context: str):
        try:
            dut.cmd("set injclear", timeout=2.0)
        except Exception as e:
            print(f"[armed] set injclear failed ({context}): "
                  f"{type(e).__name__}: {e}", flush=True)
        still, _ = _read_armed()
        if still:
            print(_armed.clear_failed_note(context, still), flush=True)

    def _check(context):
        armed_list, reply = _read_armed()
        if armed_list is None:
            if _armed.reply_status(reply) == _armed.UNSUPPORTED:
                note = _armed_notify.none_notice()
                if note:
                    print(note, flush=True)
            else:
                print(_armed.unreadable_note(context), flush=True)
        return armed_list

    def _boundary_start():
        armed_list = _check("at session start")
        if armed_list:
            print(_armed.session_start_note(armed_list), flush=True)
            _issue_injclear("at session start")

    def _boundary(tid):
        armed_list = _check(f"after {tid}")
        if armed_list:
            _armed.apply_leak(tid, armed_list)
            _issue_injclear(f"after {tid}")

    _boundary_fn = None if args.no_armed_check else _boundary
    _boundary_start_fn = None if args.no_armed_check else _boundary_start

    print(f"Connected. Running: {selected}\n")
    print("NOTE: T089 (production ELF check) is a host build test — not here.")
    skip_notice = [t for t in selected if t in _interactive_tests and not args.interactive]
    if skip_notice:
        print(f"NOTE: {skip_notice} will SKIP — re-run with --interactive.\n")
    else:
        print()

    def _dispatch(tid):
        _fail_ring.begin(tid)           # TASK-631: attribute exchanges to an id
        try:
            dut.cmd(f"get __TEST_{tid}__", timeout=2.0)
        except TimeoutError:
            pass

        def _once_body(tid=tid):
            # TASK-671: the exception-to-verdict arms live in lib/dispatch.py so
            # the replay-driven gates run the SAME mapping this loop does.
            if tid == "T093":
                body = lambda d: t093(d, args.interactive)          # noqa: E731
            elif tid == "T094":
                body = lambda d: t094(d, args.interactive)          # noqa: E731
            elif tid == "T095":
                body = lambda d: t095(d, args.interactive)          # noqa: E731
            else:
                body = all_tests[tid]
            _dispatch_mod.run_body(tid, body, dut)

        def _once(tid=tid):
            # TASK-671. Recording wraps only the body — the `get __TEST_<tid>__`
            # marker above is deliberately outside the `with`. If flake retry
            # re-runs the body, each run opens a fresh recording and its save
            # OVERWRITES DIR/<tid>.json: the retry is the run's final word on
            # that id, so the transcript on disk matches the verdict that
            # actually shipped, not a discarded first attempt.
            if args.record:
                with _replay.recording(dut, tid) as rec:
                    _once_body(tid)
                try:
                    path = pathlib.Path(args.record) / f"{tid}.json"
                    rec.transcript.save(path)
                    _record_count[0] += 1
                except Exception as e:
                    print(f"[record] {tid}: save failed: {e}")
            else:
                _once_body(tid)
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

    # TASK-566/597. With --class-order and --health-phase both OFF (the
    # default) this is today's loop byte-for-byte: registry order, no health
    # phase, no blocking, print_results()'s own 0/1. `class_order=_gate_on`
    # still gates ONLY reordering + CORE blocking inside run_suite (TASK-566,
    # still held). `health_ids`/`run_health` are now gated on `_health_on`
    # (TASK-597) instead of `_gate_on`, so --health-phase alone reaches
    # `_gate.health_phase()` and its exit-4 path without turning class
    # ordering on.
    rc = _gate.run_suite(
        selected, all_meta, _dispatch,
        class_order=_gate_on,
        # `health_selected`, NOT `health_tests`: the gate phase must run the
        # SUBSET --health-ids narrowed to (TASK-597/EXP-040). Passing the full
        # registry here accepted the flag, passed every host check, and ran all
        # four ids anyway — caught only by reading a real run's output.
        health_ids=list(health_selected) if _health_on else (),
        run_health=_run_health if _health_on else None,
        health_mode=health_mode,
        before_summary=_exit_snapshot,
        exit_on_finish=False,
        boundary=_boundary_fn,
        boundary_start=_boundary_start_fn,
        emit=lambda *a: print(*a, flush=True))

    if args.record:
        print(f"[record] {_record_count[0]} transcript(s) written")

    dut.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
