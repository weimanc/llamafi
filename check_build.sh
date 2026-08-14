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
echo "[1/7] pio build cyd2usb_winamp"
if (cd "$PIO_DIR" && "$PIO" run -e cyd2usb_winamp --silent 2>&1); then
    ok "cyd2usb_winamp compiles"
else
    fail "cyd2usb_winamp compile FAILED"
fi

# ── 2. Firmware build: debug target (used for DUT tests) ─────────────────────
echo "[2/7] pio build cyd2usb_winamp_debug"
if (cd "$PIO_DIR" && "$PIO" run -e cyd2usb_winamp_debug --silent 2>&1); then
    ok "cyd2usb_winamp_debug compiles"
else
    fail "cyd2usb_winamp_debug compile FAILED"
fi

# ── 3. Firmware build: Player-only dev variant (TASK-422 / ADR-059 D10) ──────
# The one extra gated env — not a 2^3 matrix (eight full builds would make this
# gate unusable). Catches -DDISABLE_SPOTIFY / player-mode-flag build breakage that
# the two envs above cannot see.
echo "[3/7] pio build cyd2usb_player"
if (cd "$PIO_DIR" && "$PIO" run -e cyd2usb_player --silent 2>&1); then
    ok "cyd2usb_player compiles"
else
    fail "cyd2usb_player compile FAILED"
fi

# ── 4. Golden hash: generated assets unchanged ───────────────────────────────
echo "[4/7] golden.sha256"
if (cd "$GEN_DIR" && sha256sum -c golden.sha256 --quiet 2>&1); then
    ok "golden.sha256 clean"
else
    fail "golden.sha256 mismatch — generated assets changed"
fi

# ── 5. Tool-script smoke test ────────────────────────────────────────────────
echo "[5/7] tools/smoke_test.sh"
if (cd "$PROJ_ROOT/app/tools" && bash smoke_test.sh 2>&1); then
    ok "smoke_test.sh passed"
else
    fail "smoke_test.sh FAILED"
fi

# ── 6. app registry staleness check ──────────────────────────────────────────
echo "[6/7] gen_app_registry staleness check"
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

# ── 7. mem_layout staleness + budget check ────────────────────────────────────
echo "[7/7] gen_mem_layout staleness + budget check"
TMPDIR_MEM=$(mktemp -d)
if "$VENV_PY" "$PROJ_ROOT/app/tools/gen_mem_layout.py" --out-dir "$TMPDIR_MEM" > /dev/null 2>&1; then
    if diff -q "$TMPDIR_MEM/mem_layout.h" "$PROJ_ROOT/app/gen/mem_layout.h" > /dev/null 2>&1 && \
       diff -q "$TMPDIR_MEM/mem_layout.py" "$PROJ_ROOT/app/gen/mem_layout.py" > /dev/null 2>&1; then
        ok "mem_layout files are up to date and budget passes"
    else
        fail "mem_layout.h or mem_layout.py is stale — re-run gen_mem_layout.py"
    fi
else
    fail "gen_mem_layout.py failed (budget overflow or manifest error)"
fi
rm -rf "$TMPDIR_MEM"

# ── Warn-only: settings-wiring gate (ADR-050 / M-SETTINGS-WIRE2 §6c) — WARN-ONLY ─────
# Every AppSettings field must have load/save mappings and a runtime owner
# outside app/src/settings/. Warn-only until promoted (script exits 0 unless
# --strict); does not count toward PASS/FAIL yet, so it is deliberately NOT
# numbered as one of the 7 gates (TASK-422 / DEV-7 — it used to print "[7/7]"
# alongside a "[6/6]", which is where the 6-vs-7 confusion in tasks.md came from).
echo "[warn] settings-wiring gate (warn-only, not counted)"
"$VENV_PY" "$PROJ_ROOT/app/tools/check_settings_wiring.py" || true

echo
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
