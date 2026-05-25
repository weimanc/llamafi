#!/usr/bin/env bash
# Pre-restructure build check. Run before and after each restructure step.
# Exit 0 = all checks pass. Exit non-zero = something broke.

set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIO="$HOME/.platformio/penv/bin/pio"
VENV_PY="$HOME/proj/esp/venv/bin/python3"
PIO_DIR="$PROJ_ROOT/app"
GEN_DIR="$PROJ_ROOT/app/gen"

PASS=0
FAIL=0

ok()   { echo "  PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL + 1)); }

echo "=== Build check ==="
echo

# ── 1. Firmware build: production target ─────────────────────────────────────
echo "[1/4] pio build cyd2usb_winamp"
if (cd "$PIO_DIR" && "$PIO" run -e cyd2usb_winamp --silent 2>&1); then
    ok "cyd2usb_winamp compiles"
else
    fail "cyd2usb_winamp compile FAILED"
fi

# ── 2. Firmware build: debug target (used for DUT tests) ─────────────────────
echo "[2/4] pio build cyd2usb_winamp_debug"
if (cd "$PIO_DIR" && "$PIO" run -e cyd2usb_winamp_debug --silent 2>&1); then
    ok "cyd2usb_winamp_debug compiles"
else
    fail "cyd2usb_winamp_debug compile FAILED"
fi

# ── 3. Golden hash: generated assets unchanged ───────────────────────────────
echo "[3/4] golden.sha256"
if (cd "$GEN_DIR" && sha256sum -c golden.sha256 --quiet 2>&1); then
    ok "golden.sha256 clean"
else
    fail "golden.sha256 mismatch — generated assets changed"
fi

# ── 4. Tool-script smoke test ────────────────────────────────────────────────
echo "[4/4] tools/smoke_test.sh"
if (cd "$PROJ_ROOT/app/tools" && bash smoke_test.sh 2>&1); then
    ok "smoke_test.sh passed"
else
    fail "smoke_test.sh FAILED"
fi

echo
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
