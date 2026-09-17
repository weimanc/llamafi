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
import contextlib
import json
import os
import pathlib
import re
import sys
import threading
import time
from typing import Optional

# C-17: this codebase's host tooling has an undeclared Python >= 3.12 floor.
# suite/serialdbg/shell.py uses PEP 701 nested same-type quotes inside an
# f-string (e.g. f"...{APP_SLOT["Spotify"]}..."), which only *parses* on
# 3.12+ — on 3.11 the import of shell.py raises a bare SyntaxError with no
# hint that a Python version, not a typo, is the cause. lib/dut.py is the one
# module every suite body and every entry point (runner.py, the gate scripts,
# the family modules) imports before anything else, so this is the earliest
# place to turn that SyntaxError into a legible message. Bump this alongside
# any future syntax that raises the real minimum.
if sys.version_info < (3, 12):
    raise RuntimeError(
        f"esp_spotify host tooling requires Python >= 3.12 (found "
        f"{sys.version_info.major}.{sys.version_info.minor}). "
        f"suite/serialdbg/shell.py uses PEP 701 nested same-type quotes in "
        f"f-strings, which do not parse on older interpreters — that shows up "
        f"as a bare SyntaxError deep in an import with no version hint, which "
        f"is why this check exists (C-17). Use the project venv "
        f"(~/proj/esp/venv, or VENV_PY=/path/to/python3) rather than the "
        f"system interpreter.")

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


# ── the boot-phase stream (TASK-561's producer, consumed here by TASK-564) ────
# `[bootphase] N name`, emitted once per stage boundary of setup() from
# app/src/boot/boot.cpp (phases 0-5) and from main.cpp's loop() (phase 6). The
# token is NORMATIVE on both sides — boot.cpp:141 says so, and `[boot] phase=N`
# would be swallowed by the reboot detector below.
#
# Names and numbers are transcribed from the emitting call sites, NOT from doc
# prose: boot.cpp:166/278/308/329/593/736 and main.cpp:274.
_BOOT_PHASE_NAMES = {
    0: "reset",     # first line after Serial.begin()
    1: "fs",        # SD (SD_BOOT_MOUNT) + SPIFFS mounted, settings + cal loaded
    2: "display",   # chrome painted
    3: "wifi",      # entering the cascade — the UNBOUNDED stage
    4: "time",      # entering the NTP wait
    5: "services",  # spotifyTask / logServer / dataTask up
    6: "ready",     # FIRST line of loop() — the console becomes answerable here
}
_BOOT_PHASE_RE = re.compile(r"\[bootphase\]\s+(\d+)\s+(\S+)")

# Per-phase deadlines. The value at key N bounds the wait for phase N *from the
# moment phase N-1 was observed* (phase 0 is measured from the port open). This
# is the interface M-TESTARCH §2 argued the magic numbers were downstream of:
# one flat wall-clock guess cannot be right for a boot whose third stage is
# unbounded and whose other six are sub-second.
#
# EVERY number below is derived from a firmware constant or from measured boots
# in the tmux monitor's disk log — none is a round number picked for comfort:
#
#   0  2.0s  — the incumbent constant (TASK-560's window), unchanged. Phase 0 is
#             the first printf after Serial.begin(); 18 logged boots put it at
#             ~60 ms after the ROM banner.
#   1  30.0s — SD.begin() under SD_BOOT_MOUNT (both debug envs define it),
#             tft.init(), the NFC probe, then `SPIFFS.begin(false) ||
#             SPIFFS.begin(true)` — that second call FORMATS a 1.4 MB partition,
#             which is the only genuinely slow thing in the stage and has no
#             firmware bound at all. Measured <=0.7 s on all 18 logged boots, so
#             30 s only ever fires on the format path, which is itself a rig
#             anomaly worth naming.
#   2  10.0s — chrome paint: bounded TFT writes, no I/O. Same 0.7 s bucket.
#   3  10.0s — one SPIFFS config-file read. Same 0.7 s bucket.
#   4  90.0s — THE unbounded one: the whole WiFi cascade lives in phase 3.
#             Firmware worst case, summed from boot.cpp: 10 000 ms (NVS attempt)
#             + 300 ms (TASK-404 settle) + WIFI_MAX_SAVED(5) x 10 000 ms
#             (per-candidate probe, boot.cpp:477) + 15 000 ms (TASK-290
#             re-association settle) = 75.3 s. Measured worst: 46.4 s, on the
#             NO_AP_FOUND boot TASK-561 caught on its first live run. 90 s is
#             the firmware bound plus ~20%, so a slow-WiFi boot cannot become a
#             false setup failure — the constraint this task was given.
#   5  20.0s — the NTP wait, bounded in firmware at `ntpStart + 5000`
#             (boot.cpp:595), plus spotifyTask/logServer/dataTask begin().
#             Measured worst 5.7 s.
#   6  30.0s — Spotify app init, taskbar render, and TASK-260's boot-into-
#             persisted-player-mode switchApp. Measured worst ~3.7 s.
#
# Worst-case total to phase 6 is therefore ~192 s, but only on a board that is
# simultaneously reformatting SPIFFS and failing every WiFi candidate. A healthy
# boot reaches phase 6 in ~8 s and a NO_AP_FOUND boot in ~48 s.
_BOOT_PHASE_DEADLINE_S = {
    0:  2.0,
    1: 30.0,
    2: 10.0,
    3: 10.0,
    4: 90.0,
    5: 20.0,
    6: 30.0,
}
# Grace for picking the stream up when phase 0 itself was missed. boot.cpp:170
# records why that happens: phase 0 is the first thing emitted after
# Serial.begin() with no settle, so it is the line most exposed to
# first-bytes-lost. Sized to phase 1's budget — the next line we could see.
_BOOT_PHASE_GRACE_S = _BOOT_PHASE_DEADLINE_S[1]

# How long one `get heap` liveness probe waits for its reply, and how many such
# probes the boot-not-observed branch makes before calling the shell mute. The
# 3 s comes from wait_shell_cooldown_clear: the shell drops input for up to 3 s
# under render load, so a single probe cannot distinguish "busy" from "dead".
#
# Named rather than literal (TASK-629) for one reason: test_boot_gate.py drives
# this branch against a stubbed serial that returns b"" immediately, so the
# whole 2.0 + 3x3.0 s was pure wall clock the test itself controlled — 26 s of
# the host gate's 63 s, spent sleeping through deadlines nothing could satisfy.
# The test now shrinks these the same way _fast_phases() already shrinks
# _BOOT_PHASE_DEADLINE_S, and pins the production values in a separate check so
# shrinking them for speed cannot quietly become shrinking them for real.
_SHELL_PROBE_DEADLINE_S = 3.0
_SHELL_PROBE_ATTEMPTS = 3


def _run_id_file(port: str) -> pathlib.Path:
    """Per-port monotonic run counter, for the generation tag's `<run-id>` half.

    Same shape, same directory and same failure handling as _reset_gap_file()
    above — deliberately, because it is the pattern this project already trusts
    for per-device host-side state (TASK-552).

    Why persisted rather than a per-session random token (design §16.2, which
    allows either): a run id that increments makes two tags ORDERABLE, and the
    reference case §16.1 exists for — "the re-plug fixed it", a pre-re-plug boot
    compared against a post-re-plug boot — is a cross-SESSION comparison. A
    per-session counter starting at 1 would print `gen=1` on both sides and
    assert sameness where there is none, which is strictly worse than no tag.
    """
    try:
        real = os.path.realpath(port)
    except Exception:
        real = port
    slug = re.sub(r"[^A-Za-z0-9]+", "_", real).strip("_") or "unknown"
    return pathlib.Path(f"/tmp/esp32_dut_run_id_{slug}")


def _next_run_id(port: str) -> str:
    """Bump and return this session's run id. Never raises."""
    f = _run_id_file(port)
    try:
        n = int(f.read_text().strip()) + 1
    except (FileNotFoundError, ValueError, OSError):
        n = 1
    try:
        f.write_text(str(n))
    except OSError:
        # Unwritable /tmp: fall back to a token that is at least VISIBLY
        # different from another session's, which is the defect that actually
        # matters (design §16.2's second acceptable source).
        return f"t{int(time.time())}"
    return str(n)
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


#: reason slug -> precedence class (M-TESTARCH §3/§4, EC-G1). DERIVED, never
#: typed at a raise site: TASK-434's whole finding is that the site which forgets
#: is the one that fires. A reason absent from this table is RIG, which is the
#: conservative answer — RIG is the only class whose failure message makes no
#: claim about the firmware at all.
#:
#: RIG is §4's stated vocabulary: TASK-556's four serial conditions
#: (device-vanished / port-busy / port-permissions / port-error) plus
#: port-ambiguous, boot-not-observed, elf-mismatch and prod-firmware-flashed.
#: `dut-unresponsive` joins them: a mute board may not be running firmware at
#: all, which is RIG's entry rule verbatim.
#:
#: HEALTH is the set where firmware demonstrably IS running and the DEVICE is
#: nonetheless unfit to be a test subject. Calling any of these three a "RIG
#: condition" is exactly the defect EC-G1 names — the harness telling the
#: operator that a dead-SSID board is a cable problem.
_SETUP_FAIL_CLS = {
    "boot-phase-timeout": "HEALTH",
    "shell-unresponsive": "HEALTH",
    "wifi-not-connected": "HEALTH",
}


#: WHERE THE COMPILED ARTIFACTS LIVE — `app/.pio/build`. Defined once, here,
#: and imported by lib/verify_build.py rather than recomputed there.
#:
#: TASK-661 / D-2. This was an inline expression inside _verify_debug_firmware()
#: reading `pathlib.Path(__file__).parent.parent`, which was correct while the
#: code lived in `app/tools/run_serialdbg_tests.py` and became wrong the moment
#: TASK-478 moved it to `app/tools/lib/dut.py` — `parent.parent` went from
#: `app/` to `app/tools/`. The move's commit message says the code was "moved
#: VERBATIM. Verified byte-identical", and it was: byte-identity is precisely
#: the check that cannot see a `__file__`-relative path change homes. The guard
#: BP-017 exists for ("never test yesterday's binary") was therefore off from
#: 2026-08-17 to 2026-09-07, silently, because the dead path sat behind an
#: `if _fw.exists():` that simply never ran. Two rules follow, and both are
#: enforced below:
#:   1. ONE definition, imported — not two expressions that must agree.
#:   2. A guard that cannot find its comparand REFUSES. It does not pass.
BUILD_ROOT = pathlib.Path(__file__).resolve().parents[2] / ".pio" / "build"


def firmware_bin(env: str) -> pathlib.Path:
    """The host-side artifact the board is compared against, for `env`."""
    return BUILD_ROOT / env / "firmware.bin"


def cls_for_reason(reason: str) -> str:
    """The precedence class of a setup-failure reason slug (EC-G1)."""
    return _SETUP_FAIL_CLS.get(reason, "RIG")


class SetupFailure(RuntimeError):
    """A rig condition, not a test result.

    Subclasses RuntimeError deliberately: every existing `except RuntimeError`
    around Dut construction in the other app/tools/ runners keeps working
    unchanged, while main() can catch this specifically and exit with
    SETUP_FAIL_EXIT instead of the bare traceback that TASK-434 documents
    three misreads from. `reason` is the machine-greppable slug.

    TASK-565 adds `cls` — RIG or HEALTH — so the closing sentence a reader is
    handed is SELECTED by the class rather than typed at the call site (EC-G1).
    A rig sentence for a device-side fault ("this is a RIG condition, nothing
    here says the firmware is broken", printed because WiFi never associated) is
    the trigger case this whole design exists to remove.

    TASK-564 adds two stamped fields, `last_phase` and `gen`. They are NOT
    constructor arguments: every raise site inside the readiness path would then
    have to remember to pass them, and the one that forgot would be the one that
    fired. Dut.__init__ stamps them instead, at the same single place it already
    attaches the serial tail — so every SetupFailure that escapes construction
    carries "which boot phase did it die in" and "which boot are we talking
    about", whether or not its raise site knew either. Stamping is idempotent
    and only ever adds; nothing consumes the message text positionally
    (runner.py:189 passes str(e) straight through to _setup_fail)."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.last_phase = None    # "3 wifi" — stamped by Dut.__init__
        self.gen = None           # "7.1" / "?" — stamped by Dut.__init__
        # TASK-565 adds a third field, `cls`. Unlike the other two it is known
        # AT CONSTRUCTION — it is a property of the reason slug — so it is
        # DERIVED here rather than stamped later, and for the same underlying
        # reason the other two are not constructor arguments: no raise site
        # types it, so no raise site can get it wrong. See _SETUP_FAIL_CLS.
        self.cls = cls_for_reason(reason)

    def stamp(self, last_phase: Optional[str], gen: Optional[str]) -> "SetupFailure":
        self.last_phase = last_phase
        self.gen = gen
        return self

    def __str__(self):
        base = super().__str__()
        if self.last_phase is None and self.gen is None:
            # Raised before a Dut existed (resolve_port's port-ambiguous). There
            # is no boot to name, so do not invent a `last-phase=?` that reads
            # like the readiness path ran and learned nothing.
            return base
        return (f"{base}\n"
                f"cls={self.cls} last-phase={self.last_phase or 'none'} "
                f"gen={self.gen or '?'}")


# ─────────────────────────────────────────────────────────────────────────────
# TASK-596 / M-HARNESS2 R18 — the typed read.
#
# THE DEFECT THIS TYPE EXISTS TO MAKE UNREPRESENTABLE. The suite reads device
# state as `int(r.get("val", 0))`. WP-A counted seven different defaults for
# that one field and six of them are values a comparison can pass on; WP-G then
# found the live instance — `_stock_ok_count` returns `-1`, `_wait_chart_complete(-1)`
# is satisfied by the first poll it makes, and the Stock family's central fetch
# oracle is an unconditional pass across nine ids. The defect is not the default
# VALUE. It is that a failed read and a real reading have the SAME TYPE, so no
# call site is forced to distinguish them and none of the 171 of them does.
#
# So the accessor returns a value or raises. There is deliberately no
# `try_get_int()` and no `default=` parameter: either would restore the shape in
# one line, and the gate (`gate/check_defaulted_reads.py`) would not see it,
# because the ratchet counts `.get(<key>, <literal>)` on a reply, not the ways a
# helper could re-offer one.
#
# TWO FAILURE MODES, TWO VERDICTS (and this is the part worth arguing about).
#
#   BadField  — the device answered THIS question and the answer breaks the
#               contract: `ok:false` (the firmware does not know the var — a
#               rename, which is precisely S6's silent-success case), the field
#               absent, or the value the wrong type. Somebody's code is wrong
#               and the evidence is reproducible. That is a FAIL.
#
#   NoAnswer  — nothing came back for this question inside the window, or every
#               reply that came back was labelled with a different `var`. The
#               commonest cause on this rig is not a firmware defect at all: it
#               is stockTickQuotes' documented 8-ticker serial flood arriving on
#               top of the read (WP-C's raced-reply hazard, `read_json` returning
#               the FIRST `{`-line it sees). The test then asserted nothing. Its
#               premise — "the device answered" — never held, and TASK-624 made
#               exactly that expressible: it is an `UNMET`, not a FAIL and
#               emphatically not a SKIP.
#
# Why UNMET rather than FAIL for NoAnswer, given UNMET was NOT available when
# this suite was written: an UNMET already BLOCKS and already exits 1
# (ADR-066 D4 / IFC-008 I4), so nothing is weakened by the split — a gating-class
# id that cannot read its device still stops the run. What is gained is that the
# triage reader stops being told the firmware regressed when the serial line was
# busy. Reporting a rig-noise read as a FAIL is how a suite trains its owner to
# re-run reds, and a suite whose reds are re-run by habit has no reds.
#
# Both are RuntimeError subclasses, so every existing `except RuntimeError` and
# every bare `except Exception` in the runners keeps working; the runner's
# dispatch loop adds the two arms that make the split visible.
class DeviceReadError(RuntimeError):
    """Base: a typed read did not yield a trustworthy value (R18)."""

    def __init__(self, var: str, detail: str):
        super().__init__(detail)
        self.var = var
        self.detail = detail


class NoAnswer(DeviceReadError):
    """The device did not answer THIS question. -> UNMET (premise unestablished)."""


class BadField(DeviceReadError):
    """It answered, and the answer breaks the contract. -> FAIL (a real defect)."""


class RestoreFailed(RuntimeError):
    """A restore did not complete. TASK-602 / M-HARNESS2 R17.

    Deliberately NOT a DeviceReadError: this is not "the test could not read its
    subject", it is "the device is now in a state the next test did not ask for",
    which is the defect class R17 exists for. It is raised out of the context
    manager's exit so the run cannot continue quietly on leaked state; the
    runner maps it to FAIL on the test that armed it, which is the attribution
    R14 asks for.
    """

    def __init__(self, var: str, detail: str):
        super().__init__(detail)
        self.var = var
        self.detail = detail


#: Sentinel for "the caller did not name a field" — distinct from None, which is
#: a legitimate thing to look for.
_UNSET = object()


class _TeeSerial:
    """Wraps a pyserial Serial to observe every readline() line (JSON responses
    and bare LOG_D/LOG_W lines alike — everything the harness's own parsing
    normally discards). Delegates everything else to the wrapped object
    unchanged.

    Two sinks, independently optional:
      * `log_path` — append to a plain-text file (the pre-existing --log-file).
      * ring buffer — the last _SETUP_FAIL_TAIL_LINES lines, always kept
        (TASK-434 item 4). Costs a bounded deque and buys the abort dump for
        runs that had no log file, which is most of the ones that abort.

    Third job since TASK-564: the GENERATION COUNTER. See boot_count's docstring
    below for what it can and cannot be trusted to say. It lives here, and only
    here, because readline() is the one place every byte the harness reads
    passes through — read_json() would have been the obvious-looking home and is
    wrong, because it discards every line that does not start with `{` and
    `[bootphase] 0` does not."""

    # Attributes that live on the WRAPPER. Everything else assigned through the
    # tee is forwarded to the wrapped serial by __setattr__ below — see there
    # for why. Adding state to this class means adding its name here, or the
    # assignment in __init__ ends up on the pyserial object instead.
    _OWN_ATTRS = frozenset({"_ser", "_log", "_ring", "run_id", "boot_count",
                            "_ts_sidecar_path", "expecting_reboot"})

    #: TASK-677 / PROP-011 §5 P0 deliverable B. Off by default (public
    #: checkout, RIGWATCH unset): zero behaviour change, not even the sidecar
    #: file gets created. See lib/rigwatch.py's module docstring for what
    #: reads this sidecar and why it exists — a host receive-timestamp per DUT
    #: line, so the timeline tool can merge this session's boot/bod/wifi lines
    #: against kernel USB events and other harness actions.
    _RIGWATCH_ON = os.environ.get("RIGWATCH", "") == "1"

    def __init__(self, ser, log_path: Optional[str] = None,
                 run_id: Optional[str] = None):
        self._ser = ser
        self._log = open(log_path, "a", buffering=1) if log_path else None
        self._ring = collections.deque(maxlen=_SETUP_FAIL_TAIL_LINES)
        # One shared file with the rigwatch daemon's monitor tail (they are
        # never live together — the monitor is killed for every run), so a run
        # without LOG_FILE still leaves timestamped DUT lines for the artifact's
        # `rig` section to reason about. Same default as lib/rigwatch.py's
        # DEFAULT_DUT_LINES; not imported from there to keep this module free
        # of any rigwatch import at construction time.
        # Real port only. run/lib.sh exports RIGWATCH=1 from run/local.env, so
        # every host test that wraps a fake serial in this tee inherited it and
        # wrote its fixture `[bootphase] 0` lines into the live DUT-lines file —
        # 16 fabricated "unexplained boots" on 2026-09-11 (EXP-029).
        self._ts_sidecar_path = (
            os.environ.get("RIG_DUT_LINES", "/tmp/spotify-mon-dut-lines.jsonl")
            if (self._RIGWATCH_ON and isinstance(ser, serial.Serial)) else None)
        # ── generation counter (TASK-564, design §16.2 / EC-S4) ──────────────
        # Counts observed `[bootphase] 0` lines, i.e. boots this session SAW.
        #
        # UNDER-COUNTS, KNOWN AND DECLARED, NOT FIXED. _TeeSerial.__getattr__
        # forwards any unknown attribute straight to the raw serial, so the 44
        # `reset_input_buffer()` call sites across app/tools/ and run/ (10 of
        # them inside this very file) never pass through readline(): a
        # `[bootphase] 0` sitting in the OS buffer when one of them fires is
        # discarded UNSEEN. So `gen=N` is "boots observed", never "boots that
        # happened", and it under-counts precisely at the moments a caller had
        # decided the stream was untrustworthy — which correlates with the
        # moments a board is misbehaving. Do not present it as an exact boot
        # count. The named fix (design §16.2) is an explicit
        # _TeeSerial.reset_input_buffer() that drains via its own readline
        # before delegating; deliberately out of scope here.
        self.run_id = run_id or "?"
        self.boot_count = 0
        # TASK-698. Set by the dispatch loop immediately before it invokes a
        # test whose `effect` is "resetting" (it deliberately reboots the
        # board as part of what it asserts), cleared in a `finally` right
        # after. readline() below consults this instead of the bare
        # `boot_count == 1` test, so a DELIBERATE reboot prints a plain
        # observation and a real mid-session reset still prints the alarm.
        # Does not affect the boot_count INCREMENT, which stays unconditional
        # — this is a labeling change only, other code depends on the raw
        # count being accurate.
        self.expecting_reboot = False

    def readline(self, *a, **kw):
        line = self._ser.readline(*a, **kw)
        if line:
            text = line.decode(errors="replace")
            self._ring.append(text.rstrip("\n"))
            if self._log:
                self._log.write(text)
                if not line.endswith(b"\n"):
                    self._log.write("\n")
            # TASK-677: host-timestamp the lines rigwatch's timeline reasons
            # about. Written straight to disk (not through lib.rigwatch, which
            # must never be import-time-coupled to a live serial session) so
            # this stays a plain file append, never a board-touching call.
            if self._ts_sidecar_path is not None:
                stripped = text.rstrip("\n")
                if ("[bootreason]" in stripped or "[bootphase]" in stripped
                        or "[bod]" in stripped or "[wifi-ev]" in stripped
                        or "[I][hb]" in stripped):
                    try:
                        with open(self._ts_sidecar_path, "a",
                                 encoding="utf-8") as fh:
                            fh.write(json.dumps(
                                {"host_ts": time.time(), "line": stripped,
                                 "via": "harness"}) + "\n")
                    except OSError:
                        pass
            # One `if`, on the one path every read line takes. EC-S4 wants the
            # increment VISIBLE in the run log: a spontaneous mid-session reset
            # (the TASK-557 class, a TWDT, a brownout) leaves no mark in the
            # results today, which is exactly what makes it an invisible
            # confound rather than an event.
            if "[bootphase] 0" in text:
                self.boot_count += 1
                # TASK-698: a reset the CURRENTLY RUNNING test deliberately
                # triggers (effect="resetting", e.g. T_PR_04) is not an
                # alarm — only a boot the dispatch loop did not arm for is.
                unexpected = self.boot_count != 1 and not self.expecting_reboot
                print(f"  [Dut] gen={self.gen_tag()} — [bootphase] 0 observed"
                      + ("  << UNEXPECTED: the board reset mid-session"
                         if unexpected else ""),
                      flush=True)
        return line

    def gen_tag(self) -> str:
        """`<run-id>.<n>`, or `?` when no boot has been observed.

        Globally unique, not per-session (design §16.2): a per-session counter
        starting at 1 makes EVERY session's first boot `gen=1`, so a
        cross-session comparison — which is the shape of the reference case in
        §16.1 — would print the same tag on both sides and assert sameness where
        there is none. `?` is not a placeholder to be tidied away later: under
        DUT_BOOT_GATE=warn there may genuinely have been no observed boot, and a
        `?` observation is comparable to nothing."""
        if self.boot_count == 0:
            return "?"
        return f"{self.run_id}.{self.boot_count}"

    def tail(self):
        return list(self._ring)

    def __getattr__(self, name):
        return getattr(self._ser, name)

    def __setattr__(self, name, value):
        """Forward attribute ASSIGNMENT to the wrapped serial (TASK-575).

        __getattr__ alone is half a proxy: reads fell through to pyserial,
        writes did not. Every `dut.ser.timeout = 0.5` across app/tools/ landed
        in this wrapper's __dict__ instead — where it also shadowed the read
        path, so the value read back looked right — and pyserial kept using
        whatever timeout Dut.__init__ passed (3.0 s by default) for the whole
        session. Deadline loops are monotonic-clock based and so stayed
        correct; what they lost was granularity, and `write_timeout` was never
        armed at all.

        The wrapper's own attributes must still land here, so they are named
        explicitly rather than inferred from a leading underscore: `run_id` and
        `boot_count` have no underscore, and a rule based on one would have
        pushed the generation counter onto the pyserial object."""
        if name in _TeeSerial._OWN_ATTRS:
            object.__setattr__(self, name, value)
        else:
            setattr(self._ser, name, value)


class Dut:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 3.0,
                 log_file: Optional[str] = None):
        # TASK-608 / R30. The build identity the ELF guard reads below, and the
        # port, held on the instance so the run's premise can be stated without
        # a second device read. None until _verify_debug_firmware() has run.
        self.elf = None
        self.elf_expected = None
        self.build_env = _DUT_ENV
        # TASK-645 / ADR-066 D3. WHICH BOARD produced this run. `{port, baud}`
        # is a fact about the cable, not the board: a USB re-enumeration renames
        # ttyUSB0 to ttyUSB1 on the same hardware, and plugging a second board
        # into the freed node gives two different boards an identical premise.
        # Filled by _read_board_id() below from the factory efuse MAC; stays
        # None with a NAMED reason when the firmware does not answer, because
        # "this run did not state which board" is honest and a fabricated
        # identity is not.
        self.board_id = None
        self.board_id_source = "unread"
        self.port = port
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
        # TASK-564: and it carries the generation counter, so the run id has to
        # be minted before the first byte is read.
        self.ser = _TeeSerial(self.ser, log_file, run_id=_next_run_id(port))
        # Wall-time of the open that reset the DUT. Its only consumer was the
        # portal-recovery branch TASK-555 deleted, so it is unread today — kept
        # deliberately, not by oversight: TASK-557's next-steps ask for exactly
        # this (the harness's own open timestamp, to correlate against udev
        # events and to kill the BOOT_WAIT/app-boot timing degeneracy).
        self._port_open_time = time.monotonic()
        # TASK-677 / PROP-011 §5 P0: the reader PROP-011 §3 notes this field
        # never had (`Dut._port_open_time is written and never read`). Off by
        # default (RIGWATCH unset) — see _TeeSerial._RIGWATCH_ON above for why
        # this must cost nothing on a public checkout. Lazy-imported and
        # best-effort: a stamp failing must never fail a DUT session.
        if os.environ.get("RIGWATCH", "") == "1":
            try:
                from . import rigwatch as _rigwatch
                _rigwatch.stamp("port-open", port=port)
            except Exception:
                pass
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
        # TASK-564: the last boot phase observed, so a setup failure can say
        # which stage of setup() it died in. Set here rather than in
        # _wait_for_ready() so the stamp below is valid even for a failure
        # raised before that method runs.
        self._last_phase = None
        try:
            self._wait_for_ready()
            self._verify_debug_firmware()
            # TASK-645. Read HERE, beside the ELF identity and for the same
            # reason (R30's note two screens down): a premise field that costs a
            # device read at summary time perturbs the run it describes.
            self._read_board_id()
        except SetupFailure as e:
            e.tail = self.ser.tail()
            # TASK-564: one stamp site for every readiness-path failure —
            # boot-not-observed, boot-phase-timeout, shell-unresponsive,
            # wifi-not-connected and _verify_debug_firmware's
            # prod-firmware-flashed alike. See SetupFailure's docstring for why
            # this is not a constructor argument.
            e.stamp(self.last_phase(), self.gen_tag())
            raise

    #: shape of a `get boardId` value: twelve lowercase hex digits (a 48-bit MAC).
    _BOARD_ID_RE = re.compile(r"^[0-9a-f]{12}$")

    def _read_board_id(self) -> None:
        """One read of `get boardId` (TASK-645). Best-effort, never raises.

        A board-identity read must not be able to fail a run: the identity is a
        LABEL on the result, and a harness that refused to test because it could
        not read a label would be trading a real capability for a record. Every
        failure path therefore lands on a NAMED `board_id_source` — `absent` for
        firmware predating the key, `malformed` for an answer that does not
        parse, `unanswered` for silence — and the artifact carries the reason
        instead of an identity. Deliberately NOT a fallback to the port: the
        whole finding is that the port is not an identity.
        """
        try:
            r = self.cmd("get boardId", timeout=3.0)
        except Exception as e:
            self.board_id_source = f"unanswered:{type(e).__name__}"
            return
        if not r or not r.get("ok"):
            # Firmware without the key. Expected on any build older than
            # TASK-645, and on every production build (the console is
            # SERIAL_DEBUG-only), so it is not a warning.
            self.board_id_source = "absent"
            return
        val = str(r.get("val") or "").strip().lower()
        if not self._BOARD_ID_RE.match(val):
            self.board_id_source = "malformed"
            return
        self.board_id = val
        self.board_id_source = str(r.get("src") or "efuse-mac")

    def board(self) -> dict:
        """The artifact's `premise.board` (TASK-645 / ADR-066 D3).

        `id` is the board. `transport` is how this run reached it — kept,
        because "which port was it on" is still worth knowing when a run
        misbehaves, but demoted out of the identity position it never earned.
        """
        return {
            "id": self.board_id,
            "id_source": self.board_id_source,
            "transport": {"port": self.port,
                          "baud": getattr(self.ser, "baudrate", None)},
        }

    def gen_tag(self) -> str:
        """This session's generation tag (TASK-564, design §16.2/§16.5).

        Every observation a run records should carry it, so that comparing two
        observations across a boot boundary is VISIBLY a cross-generation
        inference rather than an invisible confound. `?` means no boot was
        observed and the observation is comparable to nothing."""
        return getattr(self.ser, "gen_tag", lambda: "?")()

    def last_phase(self) -> Optional[str]:
        """`"<n> <name>"` for the last `[bootphase]` seen, or None."""
        p = getattr(self, "_last_phase", None)
        return None if p is None else f"{p[0]} {p[1]}"

    def _note_phase(self, n: int, name: str) -> None:
        """Record an observed `[bootphase] N name`.

        Trusts the number, not our table, for the name — the firmware is the
        authority on its own stream and a respelling there should show up in the
        harness output rather than be silently normalised away."""
        self._last_phase = (n, name or _BOOT_PHASE_NAMES.get(n, "?"))

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
        # Belt and braces: __init__ sets this, but the host-only stub tests
        # (test_boot_gate.py) drive _wait_for_ready() on an object.__new__'d Dut.
        self._last_phase = None
        boot_seen = False
        # TASK-564: `[bootphase] 0 reset` is now the primary boot signature. It
        # is emitted BEFORE `[boot] git=…` (boot.cpp:166 vs :227), so on current
        # firmware it is what we see first. The legacy `[boot]`/`ets Jul` match
        # stays as an alternate: it is what a board flashed with pre-TASK-561
        # firmware says, and it is also what we see if phase 0's line was lost
        # to the no-settle-after-Serial.begin() hazard boot.cpp:170 names.
        deadline = time.monotonic() + _BOOT_PHASE_DEADLINE_S[0]
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            m = _BOOT_PHASE_RE.search(line)
            if m:
                self._note_phase(int(m.group(1)), m.group(2))
                boot_seen = True
                break
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
            for _ in range(_SHELL_PROBE_ATTEMPTS):
                self.ser.reset_input_buffer()
                self.ser.write(b"get heap\n")
                self.ser.flush()
                probe_deadline = time.monotonic() + _SHELL_PROBE_DEADLINE_S
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
            msg = (f"no boot signature ('[bootphase] 0' / '[boot]' / 'ets Jul') "
                   f"within {_BOOT_PHASE_DEADLINE_S[0]:.0f}s of opening the port. "
                   f"{detail}\n"
                   f"Opening the port asserts DTR and resets the ESP32, so a boot "
                   f"is expected here; not seeing one means the reset did not take, "
                   f"the board was mid-boot already, or it is wedged.\n"
                   f"Set DUT_BOOT_GATE=warn to downgrade this to a warning.")
            if _DUT_BOOT_GATE == "warn":
                print(f"  [Dut] WARN boot-not-observed — {detail} "
                      f"(DUT_BOOT_GATE=warn)", flush=True)
                return
            raise SetupFailure("boot-not-observed", msg)
        print(f"  [Dut] reboot detected ({self.last_phase() or 'legacy banner'}) "
              f"— waiting for the boot-phase stream to reach 6 ready…", flush=True)
        self.ser.timeout = 1.0
        # TASK-564: the real readiness gate. Phase 6 is the FIRST line of
        # loop(), and handleSerialCommands() is pumped nowhere else in the
        # firmware — so before it the console is deaf by construction, and after
        # it every remaining timeout in this method is about something other
        # than "the board has not finished booting". That distinction is what
        # the flat 2 s window could never draw.
        ip_seen = self._wait_for_bootphase_6()
        # Wait for WiFi, watching for portal indicators (BP-018 / LL-051)
        extended = False   # TASK-434 item 2: one bounded second wait, below
        deadline = time.monotonic() + _DUT_WIFI_WAIT_S
        # `not ip_seen` guard (TASK-564): the phase wait above consumes the boot
        # stream up to phase 6, and setup()'s `IP address:` / `STA_GOT_IP` lines
        # are inside that window — so without this the harness would sit out the
        # full 25 s + 75 s + `get ip` cascade on a board that had already told
        # it the link was up, and blame WiFi for it.
        while not ip_seen and time.monotonic() < deadline:
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
                print(f"  [Dut] shell responsive — proceeding. "
                      f"gen={self.gen_tag()} last-phase={self.last_phase()}",
                      flush=True)
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
            print(f"  [Dut] DUT ready (spotify=off variant — poll wait skipped). "
                  f"gen={self.gen_tag()} last-phase={self.last_phase()}", flush=True)
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
                  f"design, poll wait skipped). gen={self.gen_tag()} "
                  f"last-phase={self.last_phase()}", flush=True)
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
        print(f"  [Dut] DUT ready. gen={self.gen_tag()} "
              f"last-phase={self.last_phase()}", flush=True)

    def reboot_and_wait(self):
        """Public alias for `_wait_for_ready()` (H-17).

        This is the only reboot-settle primitive Dut has: it detects the CH341
        DTR-reset boot signature and blocks until the DUT reaches steady state
        (WiFi up + first successful poll + queue fetch), retrying once via
        `reconnect` if the startup poll fails. Suite bodies that need to wait
        out a deliberate `dut.send("reboot")` — a persistence test is the
        prototypical case — should call this, not the private method, which
        stays as the internal name `__init__` itself uses. No behavior change:
        this is a visibility-only wrapper."""
        return self._wait_for_ready()

    def _wait_for_bootphase_6(self) -> bool:
        """Advance the boot-phase state machine to `[bootphase] 6 ready`.

        Returns whether an IP line was seen on the way — setup()'s
        `IP address:` / `STA_GOT_IP` are emitted inside this window, and the
        caller's WiFi wait would otherwise never see them.

        Each hop gets its OWN deadline (_BOOT_PHASE_DEADLINE_S) rather than
        sharing one wall-clock budget. That is the whole point of consuming the
        stream: phase 3's cascade is bounded at 75.3 s by firmware constants
        while every other stage is sub-second, so a single number is either far
        too tight for the WiFi stage or so loose it gates nothing. TASK-561
        measured a 46 s boot on its first live run — under the flat 2 s window
        the harness declared itself ready mid-cascade.

        Timeouts raise SetupFailure("boot-phase-timeout"), honouring
        DUT_BOOT_GATE=warn exactly like the boot-not-observed gate above: this
        lands while TASK-557 (rig instability) is open, and a gate that cannot
        be turned down gets reverted wholesale by the next person it
        inconveniences.
        """
        ip_seen = False
        while True:
            if self._last_phase is None:
                # Phase 0's line was lost (boot.cpp:170's first-bytes hazard) or
                # this is pre-TASK-561 firmware. Give the stream one grace
                # window to show up at all before deciding which.
                budget, want = _BOOT_PHASE_GRACE_S, None
            else:
                want = self._last_phase[0] + 1
                budget = _BOOT_PHASE_DEADLINE_S.get(want, _BOOT_PHASE_DEADLINE_S[6])
            deadline = time.monotonic() + budget
            got = None
            while time.monotonic() < deadline:
                line = self.ser.readline().decode(errors="replace").strip()
                if not line:
                    continue
                if _is_ip_line(line):
                    ip_seen = True
                m = _BOOT_PHASE_RE.search(line)
                if m:
                    got = (int(m.group(1)), m.group(2))
                    break
            if got is None:
                if self._last_phase is None:
                    # No `[bootphase]` at all. Pre-TASK-561 firmware, or a build
                    # that predates it. Do NOT fail: the stream ships in all
                    # builds today, but failing here would turn "you flashed an
                    # old binary" into an unreadable phase timeout instead of
                    # the ELF/`get heap` verdict _verify_debug_firmware() is
                    # about to give, which is the legible one.
                    print("  [Dut] WARN no [bootphase] stream — pre-TASK-561 "
                          "firmware? Falling back to the legacy readiness gates.",
                          flush=True)
                    return ip_seen
                msg = (f"boot stalled at [bootphase] {self.last_phase()}: no phase "
                       f"{want} ({_BOOT_PHASE_NAMES.get(want, '?')}) within "
                       f"{budget:.0f}s.\n"
                       f"That bound is derived, not guessed — see "
                       f"_BOOT_PHASE_DEADLINE_S. Stuck at 1 fs is a SPIFFS/SD "
                       f"wedge; at 3 wifi it is the connect cascade (raise "
                       f"DUT_WIFI_WAIT / see TASK-426); at 5 services it is a "
                       f"task that failed to start. Reaching 6 ready is what "
                       f"makes the serial console answerable at all, so nothing "
                       f"below this point could have run.\n"
                       f"Set DUT_BOOT_GATE=warn to downgrade this to a warning.")
                if _DUT_BOOT_GATE == "warn":
                    print(f"  [Dut] WARN boot-phase-timeout — {msg} "
                          f"(DUT_BOOT_GATE=warn)", flush=True)
                    return ip_seen
                raise SetupFailure("boot-phase-timeout", msg)
            if got[0] == 0 and self._last_phase is not None:
                # The board reset while we were watching it boot. _TeeSerial has
                # already bumped and printed the generation; restart the state
                # machine so the deadlines below apply to the NEW boot rather
                # than being measured from a boot that no longer exists.
                print(f"  [Dut] WARN board reset mid-boot (was at "
                      f"{self.last_phase()}) — restarting the phase gate",
                      flush=True)
                ip_seen = False
            self._note_phase(got[0], got[1])
            if got[0] >= 6:
                print(f"  [Dut] [bootphase] 6 ready — console answerable "
                      f"(gen={self.gen_tag()})", flush=True)
                return ip_seen

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
                # TASK-596: `.get("last", True)` was a defaulted reply read.
                # Same behaviour, no default: absent still terminates.
                if "last" not in r or r["last"]:
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
                f"The debug console is compiled out of this build, so NO test can\n"
                f"run against it. ADR-067: nothing was flashed and nothing will be\n"
                f"restored — the board keeps what it has. Flash the debug build\n"
                f"({_DUT_ENV}) yourself, then re-run:\n"
                "  ./run/flash-debug\n"
                "or, explicitly:\n"
                "  tmux kill-session -t spotify-mon\n"
                "  cd app\n"
                f"  ~/.platformio/penv/bin/pio run -e {_DUT_ENV} \\\n"
                "      -t upload --upload-port <port>\n"
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
        #
        # TASK-661 / D-2: the path comes from BUILD_ROOT (one definition), and a
        # MISSING artifact is a refusal, not a skip. The previous shape —
        # `if _fw.exists():` around the whole comparison — is what let a wrong
        # path disable the guard for three weeks without a single word of
        # output. A guard that cannot find its comparand must say so.
        _fw = firmware_bin(_DUT_ENV)
        if not _fw.is_file():
            raise SetupFailure(
                "elf-unverifiable",
                "\n"
                "╔══════════════════════════════════════════════════════════╗\n"
                "║  ELF GUARD CANNOT RUN — no host artifact to compare to   ║\n"
                "╚══════════════════════════════════════════════════════════╝\n"
                f"  WANTED:   build {_DUT_ENV}\n"
                f"  LOOKED IN: {_fw}\n"
                "\n"
                "  The board answered, but this run cannot tell WHICH build it is\n"
                "  running, so it is not allowed to proceed (BP-017: never test\n"
                "  yesterday's binary — and never test an unknown one).\n"
                "\n"
                "  NOTHING WAS FLASHED AND NOTHING WILL BE RESTORED (ADR-067).\n"
                "  Build it, then flash it, then re-run:\n"
                f"    cd app && ~/.platformio/penv/bin/pio run -e {_DUT_ENV}\n"
                "    ./run/flash-debug        # or the run/flash* script for this env\n")
        _fw_bytes = _fw.read_bytes()
        _expected_elf = _fw_bytes[176:180].hex()
        _info = self.cmd("info", timeout=3.0)
        # TASK-608 / R30 / ADR-067 D1: the build identity this guard already
        # reads is the run's premise. Recorded here rather than re-read at
        # summary time — a premise field that costs a second device read is
        # a premise field that perturbs the run it describes.
        self.elf = _info.get("elf")
        self.elf_expected = _expected_elf
        # The other half of "cannot find its comparand": the HOST artifact is
        # there, but the BOARD did not state an elf. Before TASK-661 this fell
        # through to a pass, and the run reported `elf=?` — the same silence the
        # dead path produced, from the opposite side. Refuse (BP-074: an
        # assertion whose precondition never occurred is inconclusive, not a
        # pass). Verified on hardware 2026-09-07: this firmware DOES answer
        # `info` with `elf`, so this arm fires only when something is wrong.
        if not (_info.get("ok") and _info.get("elf")):
            raise SetupFailure(
                "elf-unverifiable",
                "\n"
                "╔══════════════════════════════════════════════════════════╗\n"
                "║  ELF GUARD CANNOT RUN — the board stated no build id     ║\n"
                "╚══════════════════════════════════════════════════════════╝\n"
                f"  WANTED:       elf {_expected_elf}  (build {_DUT_ENV})\n"
                f"  ON THE BOARD: `info` answered {_info!r}\n"
                "\n"
                "  The comparison BP-017 requires did not happen, so this run is\n"
                "  not allowed to proceed on the assumption that it would have\n"
                "  passed. Nothing was flashed and nothing will be restored.\n")
        if _info["elf"] != _expected_elf:
            # ADR-067: this refusal is now the ONLY thing standing between a
            # run and the wrong subject — no entry point flashes the build
            # first any more, so this message is read by a human who must
            # act on it, not by one watching a reflash scroll past.
            _f = SetupFailure(
                "elf-mismatch",
                f"\n"
                f"╔══════════════════════════════════════════════════════════╗\n"
                f"║  FIRMWARE ELF MISMATCH — wrong build on the board        ║\n"
                f"╚══════════════════════════════════════════════════════════╝\n"
                f"  ON THE BOARD: elf {_info['elf']}\n"
                f"  WANTED:       elf {_expected_elf}  (build {_DUT_ENV})\n"
                f"                set DUT_ENV to target another variant\n"
                f"\n"
                f"  NOTHING WAS FLASHED AND NOTHING WILL BE RESTORED (ADR-067).\n"
                f"  The board keeps the build it has. Put the one you want on\n"
                f"  it yourself, then re-run:\n"
                f"    ./run/flash-debug        # or run/flash-player, run/flash-webradio\n"
                f"  or, explicitly:\n"
                f"    cd app && ~/.platformio/penv/bin/pio run -e {_DUT_ENV} \\\n"
                f"        -t upload --upload-port <port>\n"
            )
            # Read by lib/verify_build.py to name what is on the board in
            # its own refusal, without re-parsing this text.
            _f.flashed_elf = _info["elf"]
            _f.expected_elf = _expected_elf
            _f.expected_env = _DUT_ENV
            raise _f

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
            # TASK-596: no default. An ack without `remainingMs` means the
            # cooldown surface is not what this loop thinks it is; treat it the
            # way the old `0` default did (stop waiting) but say so.
            if "remainingMs" not in r:
                break
            rem = int(r["remainingMs"])
            if rem <= 0:
                break
            time.sleep(min(rem / 1000.0, 0.1))

    def set_cooldown_zero(self):
        r = self.cmd("set cooldown 0")
        assert r.get("ok"), f"set cooldown 0 failed: {r}"

    # ── TASK-596 / R18: the typed read ───────────────────────────────────────

    def read_reply(self, cmd_str: str, timeout: float = 3.0,
                   expect_var: Optional[str] = None) -> dict:
        """Send `cmd_str` and return the reply that ANSWERS IT, or raise NoAnswer.

        The difference from `cmd()` is the correlation. `read_json` returns the
        first `{`-line on the wire, which under a concurrent fetch is routinely
        somebody else's reply (WP-C; WP-G's `G-2` names it as the trigger that
        makes the `-1` baseline non-hypothetical). Every `get` handler in
        `cmdGet.cpp` echoes `"var"`, including the `ok:false` unknown-var path,
        so a mismatch is decidable: keep reading until the deadline rather than
        adjudicating a reply to a question nobody asked.

        A reply with NO `var` field is ACCEPTED. Correlation is a property of
        the firmware's reply format, not of this file, and turning an unlabelled
        but correct reply into a failure would mirror a firmware fact here
        (LL-114). Accepting it is strictly no worse than today's behaviour.
        """
        if expect_var is None and cmd_str.startswith("get "):
            expect_var = cmd_str[4:].strip().split()[0] if cmd_str[4:].strip() else None
        self.send(cmd_str)
        deadline = time.monotonic() + timeout
        # A SET, and the count kept separately: under the serial flood this loop
        # exists to survive, a list would grow without bound for the whole
        # timeout window just to be summarised into five names.
        seen: set = set()
        n_seen = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                r = self.read_json(remaining)
            except TimeoutError:
                break
            if expect_var is None or "var" not in r or r["var"] == expect_var:
                return r
            n_seen += 1
            if len(seen) < 8:
                seen.add(r["var"])
        raise NoAnswer(
            expect_var or cmd_str,
            f"no reply to {cmd_str!r} within {timeout}s"
            + (f" — {n_seen} reply/replies for other vars arrived instead "
               f"({', '.join(sorted(seen)[:5])}), which is a raced serial "
               f"read, not a device answer" if n_seen else ""))

    def get_val(self, var: str, field: str = "val", timeout: float = 3.0):
        """The raw value of `field` in the reply to `get <var>`, or raise.

        Raises NoAnswer if nothing answered; BadField if the device refused the
        var (`ok:false` — a renamed or deleted debug key, the S6 case), if the
        field is absent, or if it is JSON null.
        """
        r = self.read_reply(f"get {var}", timeout=timeout)
        if not r.get("ok"):
            raise BadField(var, f"device refused `get {var}`: {r!r} — the debug "
                                f"key does not exist on this build (renamed? "
                                f"deleted? wrong variant?)")
        if field not in r:
            raise BadField(var, f"`get {var}` replied without a {field!r} field: "
                                f"{r!r} — the reply shape changed under the test")
        v = r[field]
        if v is None:
            raise BadField(var, f"`get {var}` replied {field}=null: {r!r}")
        return v

    def get_int(self, var: str, field: str = "val", timeout: float = 3.0) -> int:
        v = self.get_val(var, field=field, timeout=timeout)
        if isinstance(v, bool):
            # JSON true/false is an int in Python and would silently become 1/0.
            raise BadField(var, f"`get {var}` {field}={v!r} is a bool where an "
                                f"int was asked for")
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str):
            try:
                return int(v.strip(), 10)
            except ValueError:
                pass
        raise BadField(var, f"`get {var}` {field}={v!r} ({type(v).__name__}) is "
                            f"not an integer")

    def get_float(self, var: str, field: str = "val", timeout: float = 3.0) -> float:
        v = self.get_val(var, field=field, timeout=timeout)
        if isinstance(v, bool):
            raise BadField(var, f"`get {var}` {field}={v!r} is a bool where a "
                                f"float was asked for")
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError:
                pass
        raise BadField(var, f"`get {var}` {field}={v!r} ({type(v).__name__}) is "
                            f"not a number")

    def get_str(self, var: str, field: str = "val", timeout: float = 3.0) -> str:
        v = self.get_val(var, field=field, timeout=timeout)
        if isinstance(v, str):
            return v
        raise BadField(var, f"`get {var}` {field}={v!r} ({type(v).__name__}) is "
                            f"not a string")

    def get_bool(self, var: str, field: str = "val", timeout: float = 3.0) -> bool:
        v = self.get_val(var, field=field, timeout=timeout)
        if isinstance(v, bool):
            return v
        # The firmware prints most flags with %u/%d, and a few as "true"/"false"
        # strings. Both are unambiguous; anything else is not.
        if isinstance(v, int) and v in (0, 1):
            return bool(v)
        if isinstance(v, str) and v.strip().lower() in ("true", "false", "0", "1"):
            return v.strip().lower() in ("true", "1")
        raise BadField(var, f"`get {var}` {field}={v!r} ({type(v).__name__}) is "
                            f"not a boolean")

    # R18's second clause — the one that bites. A restore is a read AND a write,
    # and a restore satisfied by a default rewrites persisted state with a guess.
    # `get_*` closes the read half by construction (a snapshot that could not be
    # read raises, so the restore never runs with an invented value). This closes
    # the write half: an unacknowledged `set` is not a restore either. TASK-602
    # owns the context manager that pairs them; this is the primitive it needs,
    # and it is deliberately not that manager — writing one here would double-book
    # that row.
    def set_val(self, var: str, value, timeout: float = 3.0) -> dict:
        """`set <var> <value>`, raising unless the device acknowledges `ok`."""
        cmd_str = f"set {var} {value}"
        r = self.read_reply(cmd_str, timeout=timeout, expect_var=var)
        if not r.get("ok"):
            raise BadField(var, f"device refused `{cmd_str}`: {r!r}")
        return r

    # ── TASK-602 / R17: restore is a mechanism, not a convention ─────────────
    #
    # R17's failure modes, all four measured in the tree, and how the shape below
    # closes each:
    #
    #   (a) `C-15` — the restore is on the pass path only, so every FAILURE leaves
    #       an arbitrary app. Closed by being a context manager at all: the exit
    #       runs on the exception path, the `return` path and the `skip()` path
    #       alike, and there is no way to write the body that skips it.
    #   (b) `C-12`/`D-15`/`E-4` — the restore defaults (`r.get('val', 0)` for
    #       `playerMode`, four times), so a failed snapshot read silently REWRITES
    #       persisted state with a literal. Closed by taking the snapshot with
    #       `get_val`, which RAISES: the snapshot happens before `yield`, so a
    #       snapshot that could not be read means the body never runs at all.
    #       There is no path on which this manager restores to a guess.
    #   (c) an unacknowledged `set` on the way out, which is not a restore. Closed
    #       by `set_val`, which raises unless the device acks — that is the whole
    #       reason TASK-596 built `set_val` returning the reply rather than a bool.
    #   (d) a restore that fails while the body is ALSO failing. Closed loudly: the
    #       body's exception still propagates (it is the verdict), the restore
    #       failure is printed at the point it happens and attached to the
    #       propagating exception as `.restore_errors`, so a leak can never be
    #       swallowed by the exception that happened to be in flight.
    #
    # Why two managers rather than one. `saved()` needs a read-back, and a real
    # part of the surface has none: `bgPoll`, `wrDeadUrls`, `triggerHeatmap`,
    # `prInjectAircraft` and `stockMode` are settable and NOT gettable (WP-B
    # `B-5`; check against `gen_get_keys.py`'s list, which is generated). For
    # those, a snapshot is not merely missing, it is impossible — so `injected()`
    # requires the caller to NAME the clearing value instead of inventing one.
    # That is BP-073 as an API: an injector cannot be armed here without its
    # clearing path being written down on the same line.

    @contextlib.contextmanager
    def saved(self, *variables: str, set_to=None, field: str = "val",
              timeout: float = 3.0):
        """Snapshot `variables`, run the body, restore them on EVERY exit path.

        `set_to` (single variable only) writes a value after the snapshot, so the
        common "mutate for the duration of this block" case is one line.

        Raises before the body runs if any snapshot could not be read (NoAnswer
        -> UNMET, BadField -> FAIL). Raises `RestoreFailed` after a clean body if
        any restore was not acknowledged.
        """
        if set_to is not None and len(variables) != 1:
            raise ValueError("set_to= applies to exactly one variable")
        snapshot = {v: self.get_val(v, field=field, timeout=timeout)
                    for v in variables}
        if set_to is not None:
            self.set_val(variables[0], set_to, timeout=timeout)
        try:
            yield snapshot
        finally:
            self._restore(snapshot, timeout)

    @contextlib.contextmanager
    def injected(self, var: str, value, clear_to, timeout: float = 3.0):
        """Arm a write-only debug injector, and clear it on EVERY exit path.

        For flags with no read-back, where `saved()` is impossible. `clear_to` is
        mandatory and not defaulted: the disarming value is a fact about the
        firmware that the caller knows and this file does not.
        """
        self.set_val(var, value, timeout=timeout)
        try:
            yield
        finally:
            self._restore({var: clear_to}, timeout)

    def _restore(self, values: dict, timeout: float) -> None:
        """Write `values` back, loudly. Shared exit path of both managers."""
        errors = []
        for var, val in values.items():
            try:
                self.set_val(var, val, timeout=timeout)
            except Exception as e:                      # noqa: BLE001 — see below
                # Bare `except` on purpose: whatever went wrong, the state is now
                # unknown, and the one outcome that must not happen is silence.
                msg = f"restore of {var}={val!r} FAILED: {e}"
                print(f"    [restore] {msg}")
                errors.append(RestoreFailed(var, msg))
        if not errors:
            return
        pending = sys.exc_info()[1]
        if pending is not None:
            # The body is already failing; its exception is the verdict. Do not
            # replace it — annotate it, so triage sees both.
            existing = list(getattr(pending, "restore_errors", []))
            pending.restore_errors = existing + errors        # type: ignore[attr-defined]
            return
        if len(errors) == 1:
            raise errors[0]
        raise RestoreFailed(
            ",".join(e.var for e in errors),
            "; ".join(e.detail for e in errors))

    def close(self):
        self.ser.close()
        try:
            self._gap_file.write_text(str(time.time()))
        except Exception:
            pass
        if os.environ.get("RIGWATCH", "") == "1":
            try:
                from . import rigwatch as _rigwatch
                _rigwatch.stamp("port-close", port=self.port)
            except Exception:
                pass
