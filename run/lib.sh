#!/usr/bin/env bash
# run/lib.sh — sourced by all run/* scripts. Not executed directly.

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIO="$HOME/.platformio/penv/bin/pio"
VENV_PY="$HOME/proj/esp/venv/bin/python3"
PIO_DIR="$PROJ_ROOT/app"
SESSION="spotify-mon"
ENV_PROD="cyd2usb_winamp"
ENV_DEBUG="cyd2usb_winamp_debug"
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
