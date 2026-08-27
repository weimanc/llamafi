#!/usr/bin/env bash
# run/lib.sh — sourced by all run/* scripts. Not executed directly.

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIO="$HOME/.platformio/penv/bin/pio"
_venv_default="$HOME/proj/esp/venv/bin/python3"
VENV_PY="${VENV_PY:-$([ -x "$_venv_default" ] && echo "$_venv_default" || command -v python3)}"
PIO_DIR="$PROJ_ROOT/app"
SESSION="spotify-mon"
ENV_PROD="cyd2usb_winamp"
# TASK-435 item 2: the debug env the test scripts flash and the harness verifies
# against. Overridable so a suite can run on a second testable variant —
# DUT_ENV=cyd2usb_player ./run/test-targeted T_PLR_01,T_PLR_02
# The same variable is read by suite/serialdbg/runner.py for its ELF-hash guard
# (it inherits the environment), so the two cannot disagree about which binary
# is supposed to be on the device. ENV_PROD is deliberately NOT overridable:
# every test script's trap restores production, and that must stay production.
ENV_DEBUG="${DUT_ENV:-cyd2usb_winamp_debug}"
BOOT_WAIT="${BOOT_WAIT:-8}"

# The live device lookup, unconditionally — no $PORT override short-circuit.
# Split out of resolve_port() (ADR-062/TASK-547) so a caller that specifically
# needs "what does the OS say right now" (restore_port(), below) can get it
# without resolve_port()'s env-var precedence masking a device that moved.
# Returns nonzero (no output) if nothing is found — never `exit`s, since
# callers may run this from inside a trap.
#
# Prefers /dev/serial/by-id/ (ADR-062 R1): udev's own persistent symlink for
# this device, named from VID:PID (+ model string), NOT from enumeration
# order. /dev/ttyUSBn is assigned in whatever order the kernel happens to
# (re-)attach devices in — the exact thing that goes stale mid-run. The by-id
# symlink target updates itself under the same path across a re-enumeration,
# and every consumer here (esptool, pyserial, tmux/pio device monitor) opens
# a symlink transparently, so passing the by-id path IS the fix at the root:
# nothing downstream needs to re-resolve anything, because the path handed
# out at script start stays valid for the device's entire session. Falls
# back to the VID:PID scan over /dev/ttyUSB* only when by-id isn't available
# (no udev, or a stripped-down environment) — that path is the one still
# exposed to enumeration-order drift, which is exactly why restore_port()
# below exists as a second layer under it.
_scan_ch340_port() {
  local by_id="/dev/serial/by-id" link
  if [ -d "$by_id" ]; then
    for link in "$by_id"/usb-1a86_*; do
      [ -e "$link" ] || continue
      echo "$link"
      return 0
    done
  fi
  local p found=""
  for p in /dev/ttyUSB*; do
    [ -e "$p" ] || continue
    udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" \
      && found="$p" && break
  done
  [ -n "$found" ] || return 1
  echo "$found"
}

resolve_port() {
  if [ -n "${PORT:-}" ]; then
    echo "$PORT"
    return 0
  fi
  _scan_ch340_port && return 0
  echo "ERROR: CH340 device not found (VID:PID 1A86:7523)" >&2
  exit 1
}

# Re-resolve the port immediately before a trap-guarded restore flash, instead
# of trusting the value resolve_port() cached at script start (ADR-062/
# TASK-547). A run/test* session spans minutes across multiple flash/DUT-open
# operations; the CH340 has re-enumerated mid-run (this is the second time —
# lib/dut.py's resolve_port() docstring already recorded an earlier instance),
# and the trap-guarded restore is the ONE thing every run/* script's safety
# promise depends on ("DUT is never left broken") — it must not silently keep
# using a device path that no longer exists.
#
# Respects an explicit PORT=... override (the documented multi-rig/manual-pin
# use case, e.g. `PORT=/dev/ttyUSB1 ./run/test`): never second-guesses it,
# only re-scans when the original resolution came from the live VID:PID
# lookup. Falls back to the cached value, with a warning, if the rescan
# itself fails — no worse than today's behavior, never silently swallowed.
#
#   $1  the port resolve_port() returned at script start
#   $2  non-empty if that resolution was an explicit PORT=... override
#       (i.e. capture `_PORT_EXPLICIT="${PORT:-}"` BEFORE calling resolve_port)
restore_port() {
  local at_start="$1" was_explicit="$2"
  if [ -n "$was_explicit" ]; then
    echo "$at_start"
    return 0
  fi
  local fresh
  if fresh=$(_scan_ch340_port 2>/dev/null) && [ -n "$fresh" ]; then
    if [ "$fresh" != "$at_start" ]; then
      echo "[restore_port] CH340 moved during the run: $at_start -> $fresh — using current port" >&2
    fi
    echo "$fresh"
    return 0
  fi
  echo "WARN [restore_port]: could not re-scan for CH340 at restore time — using cached $at_start" >&2
  echo "$at_start"
}

# TASK-342: TLS-pin preflight before compiling — mirrors run/test's step-0
# pattern (TASK-298/LL-103), extended to build/flash entry points so a pinned
# root rotation surfaces here too, not just 30+ min into a run/test session.
# WARN-ONLY, never blocks the build/flash. CERT_PREFLIGHT=0 skips the network
# leg entirely (offline/CI); the offline expiry leg always runs (no network,
# deterministic, cheap — TASK-342's second piece).
cert_preflight() {
  local lib_dir
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  if [ "${CERT_PREFLIGHT:-1}" != "0" ]; then
    local out
    if ! out=$("$lib_dir/check-datatask-certs" 2>&1); then
      echo "$out" | grep -E "^(FAIL|ERROR)" || true
      if echo "$out" | grep -q "^FAIL"; then
        echo ""
        echo "!! [cert-preflight] WARNING: pinned-CA verify FAILed for endpoint(s) above."
        echo "!!   Fix app/src/dataTaskCerts.h first (see ADR-029) unless this is a"
        echo "!!   known host-side artifact. Not blocking this build."
        echo ""
      fi
    fi
  fi

  local expiry_out
  expiry_out=$("$lib_dir/check-datatask-certs" --expiry-only 2>&1) || true
  echo "$expiry_out" | grep -E "^WARN" || true
}
