#!/usr/bin/env python3
"""lib/dut.py — the shared DUT session layer (M-TESTBASE P1, TASK-478).

Extracted VERBATIM from run_serialdbg_tests.py, which was simultaneously the
project's primary regression suite AND its DUT library: `Dut` already had 16
importers, every one of them reaching into a 10 229-line module to get it, and
several reaching past the public surface for `_switch_to`, `_restore_spotify`,
`_DUT_WIFI_WAIT_S` and `_PORTAL_INDICATORS` (the latter since deleted by
TASK-555 — the firmware it watched for went away in ddf6433).

Two things are NEW here rather than moved, both of them the point of the task:

  resolve_port()  — delegates to run/port rather than re-deriving VID:PID.
                    13 tools carried `default="/dev/ttyUSB0"` argparse defaults
                    and the port has really been ttyUSB1. The shell layer owns
                    that fact (run/lib.sh resolve_port); re-deriving it in
                    Python is LL-114 all over again.

  TIMEOUT / TIMEOUT_SLOW — one timeout policy. The runner carried 701 numeric
                    `timeout=` literals (454 of them the same 3.0). New call
                    sites take the default; only genuinely slow operations pass
                    TIMEOUT_SLOW. Existing literals are migrated opportunistically,
                    never in the same commit as a behaviour change.

run_serialdbg_tests.py re-exports every name below, so all 16 importers keep
working unchanged. Migrate them to `from lib.dut import Dut` a few at a time.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import re
import threading
import time
from typing import Optional

try:
    import serial
except ImportError:
    raise SystemExit("pip install pyserial")

# ── timeout policy (M-TESTBASE P1) ───────────────────────────────────────────
# One default, one slow-operation override. Not a knob per call site.
TIMEOUT      = float(os.environ.get("DUT_TIMEOUT", "3.0"))
TIMEOUT_SLOW = float(os.environ.get("DUT_TIMEOUT_SLOW", "10.0"))


def set_no_wifi(value: bool) -> None:
    """Set the --no-wifi opt-in from the caller's argument parsing.

    P1 hazard, caught during extraction: run_serialdbg_tests.main() used
    `global _NO_WIFI` to flip this, and Dut._wait_for_ready() read it. Once Dut
    moved here, that `global` would have set the RUNNER's copy while Dut read
    THIS module's — silently disabling --no-wifi with no error anywhere. A
    setter makes the cross-module write explicit and greppable.
    """
    global _NO_WIFI
    _NO_WIFI = value


def resolve_port(explicit: Optional[str] = None) -> str:
    """The CH340 serial port, resolved once, by the layer that owns the fact.

    Order: explicit argument > $PORT > `run/port` (udevadm VID:PID 1A86:7523).
    Falls back to /dev/ttyUSB0 only if run/port cannot be executed at all, so a
    checkout without the shell layer still limps rather than dying.
    """
    if explicit:
        return explicit
    env = os.environ.get("PORT")
    if env:
        return env
    # parents[3], NOT [2]: this file is app/tools/lib/dut.py, so [2] is app/.
    # The off-by-one shipped and was invisible for exactly as long as the DUT
    # happened to sit on the fallback port — then the CH340 re-enumerated to
    # ttyUSB1 and every caller silently kept asking for ttyUSB0. A resolver
    # that guesses wrong in silence is worse than the 13 hardcoded defaults it
    # replaced, so the failure paths below are loud now.
    run_port = pathlib.Path(__file__).resolve().parents[3] / "run" / "port"
    if not run_port.exists():
        print(f"  [dut] WARNING: {run_port} not found — falling back to /dev/ttyUSB0",
              flush=True)
        return "/dev/ttyUSB0"
    try:
        import subprocess
        out = subprocess.run([str(run_port)], capture_output=True, text=True, timeout=10)
        got = out.stdout.strip()
        if out.returncode == 0 and got:
            return got
        # TASK-552: run/port exits nonzero when it REFUSES to choose — notably
        # when 2+ CH340s are attached and no PORT/DUT_PORT_PATH selects one.
        # Falling back to /dev/ttyUSB0 there would reinstate exactly the silent
        # coin flip the shell-side guard exists to prevent, and on a two-board
        # rig that is a 50% chance of flashing the wrong board. A resolver that
        # guesses wrong in silence is worse than no resolver (see the comment
        # above): when run/port has decided it cannot answer, propagate that.
        raise SetupFailure(
            "port-ambiguous",
            f"run/port declined to resolve a port (rc={out.returncode}). "
            f"{out.stderr.strip() or 'no detail'} — "
            f"set PORT=/dev/ttyUSBn or DUT_PORT_PATH=<by-path substring> to choose.")
    except SetupFailure:
        raise
    except Exception as e:
        print(f"  [dut] WARNING: run/port failed to execute ({e}) — "
              f"falling back to /dev/ttyUSB0", flush=True)
    return "/dev/ttyUSB0"


# ── serial helpers ────────────────────────────────────────────────────────────

_DUT_DRD_WINDOW_S   = 12.0
# No fallback to the pre-TASK-552 global /tmp/esp32_dut_last_reset. Nothing
# writes it any more, so it can only ever be stale — and a stale timestamp
# yields "gap already elapsed, no wait", which is the same answer as having no
# file at all while *looking* like the guard consulted something real. Dropped
# on @Architect review rather than carried as a comforting no-op.


def _reset_gap_file(port: str) -> pathlib.Path:
    """Per-port DRD timestamp path (TASK-552).

    This used to be one global /tmp/esp32_dut_last_reset. With a single DUT that
    is correct; with two attached, one board's open would make the other board's
    open sit out a 12 s gap it never needed, and — worse — two runs could each
    believe the other's timestamp was their own. The gap is a property of the
    physical device being reset, so key it by device.

    Normalised through realpath deliberately: the same board is addressed as
    /dev/ttyUSB0 by some callers and /dev/serial/by-id/usb-1a86_… by others
    (ADR-062 made by-id the default). Keying on the raw string would give one
    device two gap files and silently defeat the guard for whichever form was
    used second. realpath collapses both onto the same ttyUSBn.

    KNOWN WEAKNESS, not fully solved: if the CH340 re-enumerates (ttyUSB0 ->
    ttyUSB1) the key changes and the next open skips the gap even though the
    same physical board may have reset seconds ago. The first draft of this
    called that "accepted" on the reasoning that a re-enumeration is itself a
    bus reset; @Architect review pushed back, and dmesg on this rig shows
    re-enumeration is frequent rather than exceptional, so the hole is real
    rather than theoretical. The durable fix is to key on the /dev/serial/by-path
    topology name (stable across re-enumeration, tied to the physical port)
    instead of the realpath. Deliberately not done in the same change as the
    port-resolution work — see TASK-552's row.

    What this gap actually protects against is an open question: do NOT re-derive
    it from _DUT_DRD_WINDOW_S's name. DoubleResetDetector left the firmware in
    ddf6433 (2026-06-11), so BP-018's stated DRD rationale is stale; the residual
    hazard is TASK-376's "back-to-back resets drop this CYD into download mode".
    TASK-555 is re-deriving the rule or retiring it.
    """
    try:
        real = os.path.realpath(port)
    except Exception:
        real = port
    slug = re.sub(r"[^A-Za-z0-9]+", "_", real).strip("_") or "unknown"
    return pathlib.Path(f"/tmp/esp32_dut_last_reset_{slug}")
# Post-reset WiFi wait. BOOT_WAIT in run/test* does not cover this — opening
# the serial port asserts DTR and reboots the DUT, so this window alone decides
# how long a storm boot gets to reach GOT_IP. Raise on stormy days (LL-096):
#   DUT_WIFI_WAIT=120 ./run/test-targeted …
_DUT_WIFI_WAIT_S    = float(os.environ.get("DUT_WIFI_WAIT", "25"))
# TASK-434 item 2: the ONE bounded extension, on the same boot. Sized so the
# total (25 + 75 = 100 s) clears wifiDiag's WIFI_SUP_DOWN_MS = 60 s — the
# supervisor's first kick, the mechanism that actually recovers a dead-candidate
# wedge (TASK-426), cannot fire within the 25 s default at all.
_DUT_WIFI_WAIT_2_S  = float(os.environ.get("DUT_WIFI_WAIT_2", "75"))
# Set by main() from --no-wifi (or NO_WIFI=1). Module-level because Dut's
# readiness check runs inside __init__, before any per-run state exists.
_NO_WIFI            = os.environ.get("NO_WIFI", "") == "1"
# TASK-560 escape hatch. "fail" (default) aborts when the port open did not
# produce an observable boot; "warn" downgrades it to a printed warning. Exists
# because this gate lands while TASK-557 (rig instability) is unresolved, and a
# gate that cannot be turned down gets reverted wholesale by the next person it
# inconveniences instead of being read.
_DUT_BOOT_GATE      = os.environ.get("DUT_BOOT_GATE", "fail").strip().lower()
# TASK-435 item 2: which build the ELF-hash guard verifies against. Mirrors
# run/lib.sh's ENV_DEBUG, which reads the same variable — set it once and the
# flash and the guard agree by construction.
_DUT_ENV            = os.environ.get("DUT_ENV", "cyd2usb_winamp_debug")
def _is_ip_line(line: str) -> bool:
    """Does this serial line mean the DUT has a link?

    TASK-441: `IP address:` is printed ONLY by setup()'s boot-cascade success
    path (main.cpp:2650). When the cascade fails and wifiDiag's supervisor
    brings the link up afterwards — routine on an AP the saved list does not
    cover — the device is fully connected and never prints it again. Measured
    2026-08-14: heartbeat `wifi=rssi(-56)`, NTP synced, token refreshed, and
    the harness still aborted at 195 s having seen no `IP address:`.
    `[wifi-ev] … STA_GOT_IP` (wifiDiag.cpp) streams on every path that
    acquires an address, including the supervisor's."""
    return "IP address:" in line or "STA_GOT_IP" in line


# _PORTAL_INDICATORS removed by TASK-555. It matched WiFiManager's force-portal
# banners, and WiFiManager + DoubleResetDetector left this firmware in ddf6433
# ("remove WiFiManager/DRD; on-device connect UI", 2026-06-11) — a week after
# BP-018 was adopted on 2026-06-04. Nothing in app/src has printed those strings
# since; the only surviving mentions are three stale comments. The tuple, the
# portal_seen branch and its RTS-pulse recovery were therefore unreachable for
# ~3 months while still reading as live safety machinery.
# TASK-434 item 4: how many raw serial lines to keep for the abort dump. Kept
# unconditionally, not only under --log-file: the sessions that hit a setup
# failure are exactly the ones running without a log file, and "check serial
# output" names a stream the harness has just closed.
_SETUP_FAIL_TAIL_LINES = 40
# TASK-434 item 1 / VE answer 1: exit status for a RIG condition, distinct from
# a test failure. Verified free across run/test, run/test-targeted, run/test-sync
# (test-smoke execs test-targeted) — none of them branch on a specific value.
SETUP_FAIL_EXIT = 3


class SetupFailure(RuntimeError):
    """A rig condition, not a test result.

    Subclasses RuntimeError deliberately: every existing `except RuntimeError`
    around Dut construction in the other app/tools/ runners keeps working
    unchanged, while main() can catch this specifically and exit with
    SETUP_FAIL_EXIT instead of the bare traceback that TASK-434 documents
    three misreads from. `reason` is the machine-greppable slug."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class _TeeSerial:
    """Wraps a pyserial Serial to observe every readline() line (JSON responses
    and bare LOG_D/LOG_W lines alike — everything the harness's own parsing
    normally discards). Delegates everything else to the wrapped object
    unchanged.

    Two sinks, independently optional:
      * `log_path` — append to a plain-text file (the pre-existing --log-file).
      * ring buffer — the last _SETUP_FAIL_TAIL_LINES lines, always kept
        (TASK-434 item 4). Costs a bounded deque and buys the abort dump for
        runs that had no log file, which is most of the ones that abort."""

    def __init__(self, ser, log_path: Optional[str] = None):
        self._ser = ser
        self._log = open(log_path, "a", buffering=1) if log_path else None
        self._ring = collections.deque(maxlen=_SETUP_FAIL_TAIL_LINES)

    def readline(self, *a, **kw):
        line = self._ser.readline(*a, **kw)
        if line:
            text = line.decode(errors="replace")
            self._ring.append(text.rstrip("\n"))
            if self._log:
                self._log.write(text)
                if not line.endswith(b"\n"):
                    self._log.write("\n")
        return line

    def tail(self):
        return list(self._ring)

    def __getattr__(self, name):
        return getattr(self._ser, name)


class Dut:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 3.0,
                 log_file: Optional[str] = None):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud
        self.ser.timeout = timeout
        self.ser.dtr = False
        self.ser.rts = False
        # BP-018: enforce gap between serial opens to avoid DRD double-reset.
        # Per-port since TASK-552 — see _reset_gap_file(). Held on the instance
        # because close() writes the same file this read.
        self._gap_file = _reset_gap_file(port)
        try:
            last_ts = float(self._gap_file.read_text())
            gap = time.time() - last_ts
            if gap < _DUT_DRD_WINDOW_S:
                wait = _DUT_DRD_WINDOW_S - gap
                print(f"  [Dut] waiting {wait:.1f}s for DRD gap (BP-018)…", flush=True)
                time.sleep(wait)
        except (FileNotFoundError, ValueError):
            pass
        self.ser.open()
        # TASK-434 item 4: wrap unconditionally now — the ring buffer is the
        # point, the file is optional.
        self.ser = _TeeSerial(self.ser, log_file)
        # Wall-time of the open that reset the DUT. Its only consumer was the
        # portal-recovery branch TASK-555 deleted, so it is unread today — kept
        # deliberately, not by oversight: TASK-557's next-steps ask for exactly
        # this (the harness's own open timestamp, to correlate against udev
        # events and to kill the BOOT_WAIT/app-boot timing degeneracy).
        self._port_open_time = time.monotonic()
        # Serial stream is NOT thread-safe. All methods that touch self.ser must be
        # called from the thread that constructed this Dut. Never read self.ser from
        # a background thread concurrently with cmd()/read_json() — ACKs will be
        # silently consumed, causing timeouts. Use fire-and-forget + drain-phase
        # pattern for tests that need async log collection (LL-042).
        self._owner_thread = threading.current_thread()
        # TASK-434 item 4: attach the captured serial tail to any setup failure
        # here, at the one place that still has the live _TeeSerial. main()'s
        # handler prints it — by the time it runs, run/test* is moments away
        # from reflashing prod over the evidence.
        try:
            self._wait_for_ready()
            self._verify_debug_firmware()
        except SetupFailure as e:
            e.tail = self.ser.tail()
            raise

    def _wait_for_ready(self):
        """CH341 driver asserts DTR during open() regardless of userspace settings,
        which resets the ESP32.  Detect the reboot signature and wait for the DUT
        to reach steady-state (WiFi up + first SUCCESSFUL Spotify poll + queue fetch)
        before returning.  Retries once via 'reconnect' if the startup poll fails.

        TASK-555: the WiFiManager force-portal detection and its RTS-pulse
        auto-recovery used to live here and are gone — the firmware they watched
        for was removed in ddf6433 (2026-06-11), so the branch had been
        unreachable for ~3 months. The `_recovery_attempt` parameter went with
        it; no caller ever passed it."""
        orig_timeout = self.ser.timeout
        self.ser.timeout = 0.5
        boot_seen = False
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "[boot]" in line or "ets Jul" in line:
                boot_seen = True
                break
        if not boot_seen:
            # TASK-560. This used to `return` silently, and EVERY readiness gate
            # lives below this point — the WiFi wait, TASK-434's bounded
            # extension, the `get ip` fallback, the variant probe, the
            # first-successful-poll wait. So a missed banner meant the harness
            # declared itself ready in 2 s and began issuing commands with no
            # record that anything had been skipped.
            #
            # Two distinct cases hide here, and only one was ever caught:
            #
            #   * Board mute. `_verify_debug_firmware()` below raises a bare
            #     TimeoutError ~3 s later, so it does abort — but as a
            #     TimeoutError, not a SetupFailure, which misses __init__'s
            #     serial-tail attach and escapes runner.py's classifier
            #     (TASK-556). The TASK-434 legibility hole on an unenumerated
            #     path.
            #   * Board RESPONSIVE BUT NOT READY — already in loop(), WiFi
            #     down. `get heap` answers, the ELF check passes, and every gate
            #     was skipped leaving no trace at all. This is the genuinely
            #     silent one, and the one that turns into "the suite FAILed
            #     tests whose precondition was never established".
            #
            # Probe for a live shell and report which case it is. Retried, not
            # one-shot: a freshly-booted DUT can be slow (runner.py's warmup
            # wraps its own `help` in a bare except for this reason) and the
            # shell drops input for up to 3 s under render load
            # (wait_shell_cooldown_clear).
            self.ser.timeout = 1.0
            shell_up = False
            for _ in range(3):
                self.ser.reset_input_buffer()
                self.ser.write(b"get heap\n")
                self.ser.flush()
                probe_deadline = time.monotonic() + 3.0
                while time.monotonic() < probe_deadline:
                    line = self.ser.readline().decode(errors="replace").strip()
                    if '"var":"heap"' in line:
                        shell_up = True
                        break
                if shell_up:
                    break
            self.ser.timeout = orig_timeout
            self.ser.reset_input_buffer()

            if shell_up:
                detail = ("The shell ANSWERS, so the board is running — but this "
                          "open did not observe a boot, meaning it was already in "
                          "loop(). Every readiness gate (WiFi, first-poll, variant) "
                          "has been SKIPPED for this session, so any test result "
                          "from it is untrustworthy.")
            else:
                detail = ("The shell is mute too, so the board is not up at all: "
                          "no boot banner and no response to `get heap`.")
            msg = (f"no boot banner ('[boot]' / 'ets Jul') within "
                   f"{2.0:.0f}s of opening the port. {detail}\n"
                   f"Opening the port asserts DTR and resets the ESP32, so a boot "
                   f"is expected here; not seeing one means the reset did not take, "
                   f"the board was mid-boot already, or it is wedged.\n"
                   f"Set DUT_BOOT_GATE=warn to downgrade this to a warning.")
            if _DUT_BOOT_GATE == "warn":
                print(f"  [Dut] WARN boot-not-observed — {detail} "
                      f"(DUT_BOOT_GATE=warn)", flush=True)
                return
            raise SetupFailure("boot-not-observed", msg)
        print("  [Dut] reboot detected — waiting for DUT ready…", flush=True)
        self.ser.timeout = 1.0
        # Wait for WiFi, watching for portal indicators (BP-018 / LL-051)
        ip_seen = False
        extended = False   # TASK-434 item 2: one bounded second wait, below
        deadline = time.monotonic() + _DUT_WIFI_WAIT_S
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if _is_ip_line(line):
                ip_seen = True
                break
        if not ip_seen:
            if _NO_WIFI:
                # Opt-in, never the default: a WiFi failure is a real result for
                # every network-touching test, and silently proceeding would turn
                # those into confusing downstream failures. Only pass --no-wifi for
                # a suite that touches no network at all (the SD-backed T_PLR_08-12).
                # "Do not require an IP" is not "do not wait for the DUT".
                # setup()'s WiFi cascade runs before loop(), so the serial shell
                # does not answer at all until the cascade gives up — proceeding
                # straight to the tests just moves the failure to the first
                # command. Poll for a live shell instead, then continue.
                print("  [Dut] WiFi DOWN — continuing anyway (--no-wifi). Network tests "
                      "in this run are not trustworthy. Waiting for the shell…", flush=True)
                self.ser.timeout = 1.0
                shell_up = False
                shell_deadline = time.monotonic() + 90.0
                while time.monotonic() < shell_deadline:
                    self.ser.reset_input_buffer()
                    self.ser.write(b"get heap\n"); self.ser.flush()
                    probe_deadline = time.monotonic() + 3.0
                    while time.monotonic() < probe_deadline:
                        line = self.ser.readline().decode(errors="replace").strip()
                        if '"var":"heap"' in line:
                            shell_up = True
                            break
                    if shell_up:
                        break
                self.ser.timeout = orig_timeout
                self.ser.reset_input_buffer()
                if not shell_up:
                    raise SetupFailure(
                        "shell-unresponsive",
                        "DUT shell unresponsive for 90 s (--no-wifi) — "
                        "the boot cascade is still running or the DUT is wedged")
                print("  [Dut] shell responsive — proceeding.", flush=True)
                return
            # TASK-434 item 2, per VE's amendment: ONE bounded second wait on
            # the SAME boot — explicitly not the portal branch's RTS reset.
            # That reset exists because startConfigPortal() never returns
            # (LL-051/BP-018); an association timeout is not that. A reset here
            # would restart setup() from scratch, discard the supervisor's
            # arming state, and re-run the identical losing candidate sequence
            # (TASK-426's finding) — burning the retry budget for no chance of
            # success. Waiting instead lets wifiDiag::superviseTick() reach its
            # first kick, which needs WIFI_SUP_DOWN_MS = 60 s continuously down
            # and therefore cannot fire inside the 25 s default at all.
            if not extended:
                print(f"  [Dut] no IP in {_DUT_WIFI_WAIT_S:.0f}s — extending "
                      f"{_DUT_WIFI_WAIT_2_S:.0f}s to let the WiFi supervisor's "
                      f"first kick land (needs 60s down)…", flush=True)
                deadline = time.monotonic() + _DUT_WIFI_WAIT_2_S
                while time.monotonic() < deadline:
                    line = self.ser.readline().decode(errors="replace").strip()
                    if _is_ip_line(line):
                        ip_seen = True
                        break
                extended = True
            if not ip_seen:
                # Last resort: ASK. Both waits above are passive line-watchers,
                # and a link that came up before the port was opened emits
                # nothing further — the DUT is ready and the harness is staring
                # at a stream that already said so. One cheap query settles it.
                self.ser.reset_input_buffer()
                self.ser.write(b"get ip\n"); self.ser.flush()
                probe_deadline = time.monotonic() + 5.0
                while time.monotonic() < probe_deadline:
                    line = self.ser.readline().decode(errors="replace").strip()
                    if '"var":"ip"' in line and '0.0.0.0' not in line:
                        ip_seen = True
                        print(f"  [Dut] link confirmed by query: {line}", flush=True)
                        break
            if ip_seen:
                print("  [Dut] IP acquired on the extended wait.", flush=True)
            else:
                self.ser.timeout = orig_timeout
                raise SetupFailure(
                    "wifi-not-connected",
                    f"DUT WiFi not connected within "
                    f"{_DUT_WIFI_WAIT_S + _DUT_WIFI_WAIT_2_S:.0f}s of the port-open reset "
                    f"({_DUT_WIFI_WAIT_S:.0f}s + a {_DUT_WIFI_WAIT_2_S:.0f}s extension that "
                    f"covered the supervisor's first kick). Raise DUT_WIFI_WAIT (LL-096) if the "
                    f"AP is merely slow today; the captured serial tail below is the evidence.")
        # TASK-255 (M-WEBRADIO-NOPSRAM V0): variant-aware readiness. On the
        # Spotify-disabled build there is no spotifyTask, so the first-poll wait
        # below never completes (it would hang ~120 s). The shell is responsive once
        # WiFi is up, so probe `get variant`; on spotify=off, skip the poll wait.
        self.ser.reset_input_buffer()
        self.ser.write(b"get variant\n"); self.ser.flush()
        variant_off = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if '"var":"variant"' in line:
                variant_off = '"spotify":"off"' in line
                break
        if variant_off:
            time.sleep(0.5)
            self.ser.timeout = orig_timeout
            self.ser.reset_input_buffer()
            print("  [Dut] DUT ready (spotify=off variant — poll wait skipped).", flush=True)
            return
        # TASK-363 (M-SPOTIFY-BOOT-GATE, ADR-054 decision 4 / Finding 5): playerMode-aware
        # readiness. On a device persisted in WebRadio mode, spotifyTask boots idle and
        # deliberately never polls (see ADR-054) — waiting below for "[spotify.poll] ok 200"
        # would hang the full ~120 s (60 s + reconnect retry) every single run. WiFi up +
        # shell responsive is "ready" here, same standard as the variant_off branch above.
        self.ser.reset_input_buffer()
        self.ser.write(b"get playerMode\n"); self.ser.flush()
        # TASK-415: Player counts here too. playerMode widened to three values and
        # this check still named only WebRadio, so a device persisted in Player
        # mode fell through to the 60 s Spotify-poll wait and then failed startup —
        # Spotify is just as idle by design in Player mode as in WebRadio.
        player_mode_offline = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if '"var":"playerMode"' in line:
                for name in ("WebRadio", "Player"):
                    if f'"name":"{name}"' in line:
                        player_mode_offline = name
                break
        if player_mode_offline:
            time.sleep(0.5)
            self.ser.timeout = orig_timeout
            self.ser.reset_input_buffer()
            print(f"  [Dut] DUT ready (playerMode={player_mode_offline} — Spotify idle by "
                  "design, poll wait skipped).", flush=True)
            return
        # Wait for first successful Spotify poll (ok 200) AND queue fetch completion.
        # 60s window covers backoff after a failed startup poll.
        poll_ok = False
        queue_done = False
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if "[spotify.poll]" in line and "ok 200" in line:
                poll_ok = True
            if "[spotify.queue]" in line and "status=" in line:
                queue_done = True
            if poll_ok and queue_done:
                break
        if not poll_ok or not queue_done:
            # Startup poll failed; force a reconnect and wait again.
            print("  [Dut] startup poll failed — sending reconnect…", flush=True)
            self.ser.write(b"reconnect\n")
            self.ser.flush()
            poll_ok = False
            queue_done = False
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                line = self.ser.readline().decode(errors="replace").strip()
                if "[spotify.poll]" in line and "ok 200" in line:
                    poll_ok = True
                if "[spotify.queue]" in line and "status=" in line:
                    queue_done = True
                if poll_ok and queue_done:
                    break
        time.sleep(0.5)
        self.ser.timeout = orig_timeout
        self.ser.reset_input_buffer()
        print("  [Dut] DUT ready.", flush=True)

    def cmd_drain(self, cmd_str: str, timeout: float = 5.0) -> list[dict]:
        """Send a command; read all JSON responses until one has 'last': True."""
        self.send(cmd_str)
        parts = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            try:
                r = json.loads(line)
                parts.append(r)
                if r.get("last", True):
                    break
            except (json.JSONDecodeError, ValueError):
                pass
        return parts

    def wait_for_queue(self, min_count: int = 1, timeout: float = 30.0):
        """Poll 'get queue' (draining all parts) until count >= min_count or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            parts = self.cmd_drain("get queue", timeout=5.0)
            # Empty queue: single part with count=0. Non-empty: N parts with 'track'.
            item_count = sum(1 for p in parts if "track" in p)
            if item_count >= min_count:
                return True
            time.sleep(2.0)
        return False

    def _verify_debug_firmware(self):
        """Probe for SERIAL_DEBUG firmware before running any tests (LL-043 / BP-017).
        Sends 'get heap'; production builds return 'unknown command' because all
        debug commands are behind #ifdef SERIAL_DEBUG.  Raises RuntimeError with
        exact reflash commands so the fix requires zero firmware-source knowledge.
        """
        r = self.cmd("get heap", timeout=3.0)
        if not r.get("ok") and r.get("error") == "unknown command":
            # TASK-434: also a rig condition, not a test result — same
            # reasoning as the WiFi timeout, so it gets the same status.
            raise SetupFailure(
                "prod-firmware-flashed",
                "\n"
                "╔══════════════════════════════════════════════════════════╗\n"
                "║  PRODUCTION FIRMWARE DETECTED — SERIAL_DEBUG not active  ║\n"
                "╚══════════════════════════════════════════════════════════╝\n"
                f"Reflash the debug build ({_DUT_ENV}) before running tests:\n"
                "  tmux kill-session -t spotify-mon\n"
                "  cd app\n"
                f"  ~/.platformio/penv/bin/pio run -e {_DUT_ENV} \\\n"
                "      -t upload --upload-port /dev/ttyUSB0\n"
                "  tmux new-session -d -s spotify-mon \\\n"
                "      'cd app && \\\n"
                "       ~/.platformio/penv/bin/pio device monitor \\\n"
                "       -e cyd2usb_winamp -p /dev/ttyUSB0'\n"
            )

        # ADR-042 E1 gate: verify elf hash matches the compiled debug build.
        # TASK-435 item 2: the build dir is selected by DUT_ENV rather than
        # hardcoded. The guard's intent (BP-017 — never test yesterday's
        # binary) is unchanged; what changes is that it can now verify against
        # a SECOND testable variant instead of aborting on it. Before this,
        # every playback feature had to ship a standalone driver
        # (test_fbrowser_player.py, test_playorder_player.py), duplicating
        # settle/port/reporting logic and sitting outside the suite's
        # failure-set comparisons entirely.
        _fw = (pathlib.Path(__file__).parent.parent / ".pio" / "build"
               / _DUT_ENV / "firmware.bin")
        if _fw.exists():
            _fw_bytes = _fw.read_bytes()
            _expected_elf = _fw_bytes[176:180].hex()
            _info = self.cmd("info", timeout=3.0)
            if _info.get("ok") and _info.get("elf") and _info["elf"] != _expected_elf:
                raise SetupFailure(
                    "elf-mismatch",
                    f"\n"
                    f"╔══════════════════════════════════════════════════════════╗\n"
                    f"║  FIRMWARE ELF MISMATCH — wrong debug build flashed       ║\n"
                    f"╚══════════════════════════════════════════════════════════╝\n"
                    f"  Flashed elf: {_info['elf']}\n"
                    f"  Expected:    {_expected_elf}\n"
                    f"  Expected build: {_DUT_ENV} (set DUT_ENV to target another variant)\n"
                    f"Reflash it before running tests:\n"
                    f"  cd app\n"
                    f"  ~/.platformio/penv/bin/pio run -e {_DUT_ENV} \\\n"
                    f"      -t upload --upload-port /dev/ttyUSB0\n"
                )

    def _assert_owner(self):
        if threading.current_thread() is not self._owner_thread:
            raise RuntimeError(
                "Dut serial access from wrong thread — see LL-042. "
                "Use fire-and-forget + drain-phase pattern instead of background threads."
            )

    def send(self, cmd: str):
        self._assert_owner()
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()

    def read_json(self, timeout: float = 3.0) -> dict:
        """Read lines until a JSON line is found or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        raise TimeoutError(f"no JSON response within {timeout}s")

    def read_json_multi(self, timeout: float = 5.0) -> list[dict]:
        """Read JSON lines until one has 'last':true."""
        parts = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    parts.append(obj)
                    if obj.get("last"):
                        return parts
                except json.JSONDecodeError:
                    pass
        raise TimeoutError(f"multi-part response incomplete after {timeout}s")

    def drain_log_lines(self, pattern: str, count: int, timeout: float = 10.0) -> list[str]:
        """Collect `count` log lines matching `pattern` within timeout."""
        self._assert_owner()
        matches = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(matches) < count:
            line = self.ser.readline().decode(errors="replace").strip()
            if re.search(pattern, line):
                matches.append(line)
        return matches

    def cmd(self, cmd_str: str, timeout: float = 3.0,
            drain_shell_cooldown: bool = True) -> dict:
        # TASK-297 (2026-07-10): every injected tap/drag races the shell-level
        # post-gesture cooldown — appHandleTouch silently DROPS a Press while
        # s_cooldownMs is armed (main.cpp ~1977), and every prior release arms
        # it +200 ms (even for taps the app suppressed). That race, not the VIS
        # 300 ms edge, was T-CDWN-01's real flake, and it hit T079/T082 in
        # full-suite order too. Drain it here — one choke point protects every
        # tap/drag site. Tests that must inject INSIDE the window pass
        # drain_shell_cooldown=False.
        if drain_shell_cooldown and (cmd_str.startswith("tap ")
                                     or cmd_str.startswith("drag ")):
            self.wait_shell_cooldown_clear()
        self.send(cmd_str)
        return self.read_json(timeout)

    def wait_shell_cooldown_clear(self, deadline_s: float = 2.0):
        """Poll `get shellCooldown` until s_cooldownMs reads 0 (bounded)."""
        deadline = time.monotonic() + deadline_s
        while time.monotonic() < deadline:
            self.send("get shellCooldown")
            try:
                r = self.read_json(2.0)
            except TimeoutError:
                break
            rem = int(r.get("remainingMs", 0))
            if rem <= 0:
                break
            time.sleep(min(rem / 1000.0, 0.1))

    def set_cooldown_zero(self):
        r = self.cmd("set cooldown 0")
        assert r.get("ok"), f"set cooldown 0 failed: {r}"

    def close(self):
        self.ser.close()
        try:
            self._gap_file.write_text(str(time.time()))
        except Exception:
            pass
