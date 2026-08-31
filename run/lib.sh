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
# Shared by restart_monitor() below, run/monitor-start and run/monitor-read —
# all three must agree on the path or the log is written somewhere nobody reads.
MONITOR_LOG="${MONITOR_LOG:-/tmp/spotify-mon-serial.log}"
MONITOR_HISTORY="${MONITOR_HISTORY:-50000}"

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

# Every distinct CH340 tty currently attached, one per line, deduped.
# TASK-552. Deduping is by RESOLVED target, not by symlink name, and that is
# load-bearing: udev publishes more than one by-path name for a single device
# (measured on this box: pci-…-usb-0:1:1.0-port0 AND pci-…-usbv2-0:1:1.0-port0,
# both -> ttyUSB0). Counting symlinks would report two DUTs when one is plugged
# in, which is exactly the wrong answer to build a multi-DUT guard on.
_ch340_distinct_ttys() {
  local link p
  {
    for link in /dev/serial/by-id/usb-1a86_*; do
      [ -e "$link" ] || continue
      readlink -f "$link"
    done
    for p in /dev/ttyUSB*; do
      [ -e "$p" ] || continue
      udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" \
        && echo "$p"
    done
  } 2>/dev/null | sort -u
}

# Pick one board by USB topology. TASK-552 / ADR-062's named fallback: these
# boards report SerialNumber=0, so by-id names "the CH340 attached", not a
# specific unit — useless once two are present. by-path is tied to the physical
# port instead, so it survives both re-enumeration and a second board.
# DUT_PORT_PATH is matched as a substring, so a caller can pass a short
# discriminator ("usb-0:1") rather than the full pci-… name.
_scan_ch340_by_path() {
  local want="${DUT_PORT_PATH:-}" link target
  [ -n "$want" ] || return 1
  [ -d /dev/serial/by-path ] || return 1
  for link in /dev/serial/by-path/*; do
    [ -e "$link" ] || continue
    case "${link##*/}" in *"$want"*) ;; *) continue ;; esac
    target=$(readlink -f "$link") || continue
    udevadm info -q property "$target" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" \
      || continue
    echo "$link"
    return 0
  done
  echo "ERROR: DUT_PORT_PATH='$want' matched no attached CH340 under /dev/serial/by-path" >&2
  return 1
}

_scan_ch340_port() {
  # Explicit topology selector wins when set — the two-DUT case.
  if [ -n "${DUT_PORT_PATH:-}" ]; then
    _scan_ch340_by_path
    return $?
  fi

  # Refuse to guess between two boards. Before TASK-552 this returned whichever
  # by-id symlink globbed first, which with two attached is a coin flip that
  # decides which board gets flashed — silently, and the loser is whatever the
  # other run was using.
  local n
  n=$(_ch340_distinct_ttys | grep -c .) || n=0
  if [ "$n" -gt 1 ]; then
    echo "ERROR: $n CH340 devices attached — refusing to guess which is the DUT." >&2
    _ch340_distinct_ttys | sed 's/^/  /' >&2
    echo "  Select one: DUT_PORT_PATH=<substring of a /dev/serial/by-path name>, or PORT=/dev/ttyUSBn" >&2
    ls /dev/serial/by-path/ 2>/dev/null | sed 's/^/    by-path: /' >&2
    return 1
  fi

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

# The ONE place that (re)creates the serial monitor session. TASK-554.
#
# Every trap-guarded script used to inline `tmux new-session` here and stop
# there — which starts a working monitor but never attaches `pipe-pane`, so the
# disk log stops being appended the moment any run/* script restores. Nothing
# fails and nothing warns: run/monitor-read prefers the disk log whenever it is
# non-empty (run/monitor-read:16), so it goes on serving whatever was last
# written, indefinitely. Measured 2026-08-31: monitor-read returned a
# three-day-old heartbeat twice in one session and it was read as proof the DUT
# was on production firmware. The board was fine; the evidence was not.
#
# This is the load-bearing half of the DUT-safety promise's *verification*
# side, so it lives next to restore_port() rather than in any one script.
#
# Never fails the caller: it runs inside EXIT traps under `set -e`, where a
# nonzero return would abort the rest of the cleanup. Warns and returns 0.
#
#   $1  port to open; falls back to a live scan if empty
restart_monitor() {
  local port="${1:-}"
  if [ -z "$port" ]; then
    port=$(_scan_ch340_port 2>/dev/null) || port=""
  fi
  if [ -z "$port" ]; then
    echo "WARN [restart_monitor]: no CH340 port found — monitor not started" >&2
    return 0
  fi
  if ! tmux new-session -d -s "$SESSION" \
        "cd '$PIO_DIR' && '$PIO' device monitor -e '$ENV_PROD' -p '$port'" 2>/dev/null; then
    echo "WARN [restart_monitor]: tmux session '$SESSION' did not start" >&2
    return 0
  fi
  # Session-scoped, best-effort, and deliberately not relied upon — pane
  # capacity is fixed at creation. See run/monitor-start's own note (LL-128).
  tmux set-option -t "$SESSION" history-limit "$MONITOR_HISTORY" >/dev/null 2>&1 || true
  # The half that was missing everywhere but monitor-start. Append (-o … >>) so
  # consecutive sessions across a flash cycle stay in one timeline.
  tmux pipe-pane -o -t "$SESSION" "cat >> '$MONITOR_LOG'" 2>/dev/null || \
    echo "WARN [restart_monitor]: pipe-pane failed — disk log not running" >&2
  return 0
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
