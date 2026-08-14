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
# The same variable is read by run_serialdbg_tests.py for its ELF-hash guard
# (it inherits the environment), so the two cannot disagree about which binary
# is supposed to be on the device. ENV_PROD is deliberately NOT overridable:
# every test script's trap restores production, and that must stay production.
ENV_DEBUG="${DUT_ENV:-cyd2usb_winamp_debug}"
BOOT_WAIT="${BOOT_WAIT:-8}"

resolve_port() {
  if [ -n "${PORT:-}" ]; then
    echo "$PORT"
    return 0
  fi
  local p found=""
  for p in /dev/ttyUSB*; do
    [ -e "$p" ] || continue
    udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" \
      && found="$p" && break
  done
  [ -n "$found" ] || { echo "ERROR: CH340 device not found (VID:PID 1A86:7523)" >&2; exit 1; }
  echo "$found"
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
