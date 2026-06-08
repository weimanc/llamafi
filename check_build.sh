#!/usr/bin/env bash
# Pre-restructure build check. Run before and after each restructure step.
# Exit 0 = all checks pass. Exit non-zero = something broke.

set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIO="$HOME/.platformio/penv/bin/pio"
_venv_default="$HOME/proj/esp/venv/bin/python3"
VENV_PY="${VENV_PY:-$([ -x "$_venv_default" ] && echo "$_venv_default" || command -v python3)}"
PIO_DIR="$PROJ_ROOT/app"
GEN_DIR="$PROJ_ROOT/app/gen"

PASS=0
FAIL=0

ok()   { echo "  PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL + 1)); }

echo "=== Build check ==="
echo

# ── 1. Firmware build: production target ─────────────────────────────────────
echo "[1/5] pio build cyd2usb_winamp"
if (cd "$PIO_DIR" && "$PIO" run -e cyd2usb_winamp --silent 2>&1); then
    ok "cyd2usb_winamp compiles"
else
    fail "cyd2usb_winamp compile FAILED"
fi

# ── 2. Firmware build: debug target (used for DUT tests) ─────────────────────
echo "[2/5] pio build cyd2usb_winamp_debug"
if (cd "$PIO_DIR" && "$PIO" run -e cyd2usb_winamp_debug --silent 2>&1); then
    ok "cyd2usb_winamp_debug compiles"
else
    fail "cyd2usb_winamp_debug compile FAILED"
fi

# ── 3. Golden hash: generated assets unchanged ───────────────────────────────
echo "[3/5] golden.sha256"
if (cd "$GEN_DIR" && sha256sum -c golden.sha256 --quiet 2>&1); then
    ok "golden.sha256 clean"
else
    fail "golden.sha256 mismatch — generated assets changed"
fi

# ── 4. Tool-script smoke test ────────────────────────────────────────────────
echo "[4/5] tools/smoke_test.sh"
if (cd "$PROJ_ROOT/app/tools" && bash smoke_test.sh 2>&1); then
    ok "smoke_test.sh passed"
else
    fail "smoke_test.sh FAILED"
fi

# ── 5. app registry staleness check ──────────────────────────────────────────
echo "[5/5] gen_app_registry staleness check"
TMPDIR_REG=$(mktemp -d)
if "$VENV_PY" "$PROJ_ROOT/app/tools/gen_app_registry.py" --out-dir "$TMPDIR_REG" > /dev/null 2>&1; then
    if diff -q "$TMPDIR_REG/app_ids_gen.py" "$PROJ_ROOT/app/tools/app_ids_gen.py" > /dev/null 2>&1 && \
       diff -q "$TMPDIR_REG/configurable_apps.h" "$PROJ_ROOT/app/gen/configurable_apps.h" > /dev/null 2>&1; then
        ok "app registry generated files are up to date"
    else
        fail "app_ids_gen.py or configurable_apps.h is stale — re-run gen_app_registry.py"
    fi
else
    fail "gen_app_registry.py failed to run"
fi
rm -rf "$TMPDIR_REG"

echo
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
