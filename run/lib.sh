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

# Stamp the DRD reset-gap file that lib/dut.py reads, after anything that
# resets the DUT. TASK-559.
#
# The gap exists because two resets close together put this CYD somewhere bad
# (BP-018; TASK-376 recorded a silent port / download mode). But the guard in
# lib/dut.py only ever wrote its timestamp in Dut.close(), so it knew about
# dut.py's OWN opens and nothing else — and the single most common reset pair
# in this whole workflow is the one it could not see:
#
#   pio upload  -> esptool "Hard resetting via RTS pin"   RESET 1
#   sleep $BOOT_WAIT                                       (8 s by default)
#   Dut(...)    -> serial open asserts DTR                 RESET 2
#
# 8 < _DUT_DRD_WINDOW_S (12.0). Every trap-guarded script has been opening the
# port inside the window its own repo mandates, on every run, for as long as
# BOOT_WAIT has been 8. Stamping here closes it at the root: dut.py's existing
# guard then sees the flash's reset and waits out the remainder by itself, so
# BOOT_WAIT stops being load-bearing for reset safety.
#
# Path must match lib/dut.py's _reset_gap_file(): realpath, then every run of
# non-alphanumerics collapsed to "_", leading/trailing "_" stripped.
#   $1  port that was just reset (defaults to a live scan)
stamp_reset_gap() {
  local port="${1:-}" real slug
  [ -n "$port" ] || port=$(_scan_ch340_port 2>/dev/null) || return 0
  real=$(readlink -f "$port" 2>/dev/null) || real="$port"
  slug=$(printf '%s' "$real" | sed 's/[^A-Za-z0-9]\+/_/g; s/^_//; s/_$//')
  [ -n "$slug" ] || slug=unknown
  printf '%s' "$(date +%s.%N)" > "/tmp/esp32_dut_last_reset_${slug}" 2>/dev/null || true
}

# TASK-558 (A): reap `pio device monitor` processes that outlived their tmux
# session. `tmux kill-session` kills the SESSION, not necessarily the pio
# process tree hanging off its pane — and an escaped monitor is not idle: it
# retries the port in a loop, and every single port open asserts DTR, which
# resets the ESP32. Measured 2026-08-31: two orphaned monitors produced ~420
# USB re-enumerations at a ~1.45 s period; killing them by PID gave 0
# disconnects over the next 135 s. So this must run BEFORE a new session is
# created, or the fresh monitor competes with the orphans for the port.
#
# CRITICAL — the match pattern is the bracket form '[p]io device monitor'.
# A plain `pgrep -f 'pio device monitor'` (or any `pkill -f`) also matches the
# CALLING SHELL, whose own /proc/self/cmdline contains that literal string
# whenever the function is invoked from a `bash -c` one-liner or a script whose
# argv mentions it — i.e. it kills itself. That happened three times while this
# was being developed. The bracket expression never matches its own literal
# text, so the caller is immune.
#
# Never fails the caller: it runs inside EXIT traps under `set -e`.
#
# Belt and braces on top of the bracket form: _self_ancestors lists this
# process and every ancestor of it, and those PIDs are never signalled. The
# bracket expression protects us from a script whose SOURCE mentions the
# pattern; the ancestor skip additionally protects a caller invoked as e.g.
# `bash -c '... pio device monitor ...'`, whose argv contains the bare string
# and therefore genuinely does match.
_self_ancestors() {
  local pid=$$ parent
  while [ -n "$pid" ] && [ "$pid" != "0" ] && [ "$pid" != "1" ]; do
    echo "$pid"
    # ps, not /proc/<pid>/stat: field 4 there is only reachable past a comm
    # field that may itself contain spaces and parentheses.
    parent=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ') || break
    [ -n "$parent" ] || break
    pid="$parent"
  done
}

reap_orphan_monitors() {
  local pids pid n=0 alive mine
  pids=$(pgrep -f '[p]io device monitor' 2>/dev/null) || pids=""
  [ -n "$pids" ] || return 0
  mine=" $(_self_ancestors | tr '\n' ' ') "

  for pid in $pids; do
    case "$mine" in *" $pid "*) continue ;; esac
    kill "$pid" 2>/dev/null && n=$((n + 1)) || true
  done
  [ "$n" -gt 0 ] || return 0

  # Short grace for TERM, then SIGKILL only whatever is still there.
  local i
  for i in 1 2 3 4 5 6; do
    alive=$(pgrep -f '[p]io device monitor' 2>/dev/null) || alive=""
    [ -n "$alive" ] || break
    sleep 0.25
  done
  alive=$(pgrep -f '[p]io device monitor' 2>/dev/null) || alive=""
  for pid in $alive; do
    case "$mine" in *" $pid "*) continue ;; esac
    kill -9 "$pid" 2>/dev/null || true
  done

  echo "[reap] killed $n orphaned monitor process(es)" >&2
  return 0
}

# TASK-558 (B): is a running monitor holding a tty fd that no longer refers to
# the device we would open today?
#
# Second failure mode measured 2026-08-31: the CH340 re-enumerated ttyUSB1 ->
# ttyUSB0, and the monitor kept its now-`(deleted)` ttyUSB1 fd. It captured
# nothing for 8 minutes while the board was perfectly healthy — no kernel
# event, no error, no exit, just silence. Read as a dead board.
#
# Returns 0 (TRUE = STALE) if some `pio device monitor` process holds a tty fd
# that is `(deleted)`, or whose basename differs from what the by-id path
# resolves to right now. Returns 1 for healthy, and for "no monitor running"
# (nothing to be stale about). Never errors out: /proc reads on another user's
# process fail with EACCES and are simply skipped.
monitor_fd_stale() {
  local pids pid line target base cur cur_base
  pids=$(pgrep -f '[p]io device monitor' 2>/dev/null) || pids=""
  [ -n "$pids" ] || return 1

  cur=$(_scan_ch340_port 2>/dev/null) || cur=""
  cur_base=""
  if [ -n "$cur" ]; then
    cur_base=$(readlink -f "$cur" 2>/dev/null) || cur_base="$cur"
    cur_base="${cur_base##*/}"
  fi

  for pid in $pids; do
    while IFS= read -r line; do
      target="${line#*-> }"
      [ "$target" != "$line" ] || continue
      case "$target" in
        *"/dev/ttyUSB"*|*"/dev/ttyACM"*) ;;
        *) continue ;;
      esac
      case "$target" in
        *"(deleted)"*) return 0 ;;
      esac
      base="${target##*/}"
      if [ -n "$cur_base" ] && [ "$base" != "$cur_base" ]; then
        return 0
      fi
    done < <(ls -l "/proc/$pid/fd" 2>/dev/null || true)
  done
  return 1
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
  # TASK-558: before anything else — an orphaned monitor from a previous
  # session will fight the new one for the port, DTR-resetting the board on
  # every retry.
  reap_orphan_monitors
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
