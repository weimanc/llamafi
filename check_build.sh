#!/usr/bin/env bash
# Repository build + documentation gate. Run before committing structural
# changes (BP-008). Exit 0 = all checks pass. Exit non-zero = something broke.
#
# 12 counted gates: 1-7 the full firmware env matrix (ADR-061 D6), 8 golden
# assets, 9 tool smoke tests, 10 app-registry staleness, 11 mem_layout
# staleness+budget, 12 the documentation staleness gate (TASK-475). One
# additional warn-only gate (settings wiring) is deliberately not counted.
#
# The header used to read "Pre-restructure build check" and run/check called it
# a "7-gate" wrapper; both were stale by four gates. TASK-475 corrected them.

set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIO="$HOME/.platformio/penv/bin/pio"
_venv_default="$HOME/proj/esp/venv/bin/python3"
VENV_PY="${VENV_PY:-$([ -x "$_venv_default" ] && echo "$_venv_default" || command -v python3)}"
PIO_DIR="$PROJ_ROOT/app"
GEN_DIR="$PROJ_ROOT/app/gen"

PASS=0
FAIL=0
TOTAL=12

ok()   { echo "  PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL + 1)); }

echo "=== Build check ==="
echo

# ── 1-7. Firmware build: full env matrix (ADR-061 D6) ─────────────────────────
# TASK-466: every env declared in app/platformio.ini is gated here. The
# previous 3-of-8 subset's stated reason ("a full matrix would make this gate
# unusable") was measured false — the five previously-ungated envs cold-built
# in 66 s total. [env:cyd2usb] is excluded because it is no longer a build
# target: ADR-061 D8 / TASK-467 demoted it to the non-building [cyd2usb_base]
# section (it FAILED to build — missing JPEGDEC.h), leaving 7 buildable envs.
ENVS=(
    cyd2usb_winamp                  # production
    cyd2usb_winamp_debug            # DUT test target
    cyd2usb_player                  # TASK-422 / ADR-059 D10 — Player-only dev variant
    cyd2usb_winamp_screenlog        # SCREEN_LOG overlay variant
    cyd2usb_webradio                # TASK-255 / M-WEBRADIO-NOPSRAM experiment variant
    cyd2usb_webradio_16k            # EXP-012 16K input-ring trial
    cyd2usb_winamp_debug_noSpotify  # quiet debug build, no spotifyTask
)
N=0
for env in "${ENVS[@]}"; do
    N=$((N + 1))
    echo "[$N/$TOTAL] pio build $env"
    if (cd "$PIO_DIR" && "$PIO" run -e "$env" --silent 2>&1); then
        ok "$env compiles"
    else
        fail "$env compile FAILED"
    fi
done

# ── 8. Golden hash: generated assets unchanged ────────────────────────────────
echo "[8/$TOTAL] golden.sha256"
if (cd "$GEN_DIR" && sha256sum -c golden.sha256 --quiet 2>&1); then
    ok "golden.sha256 clean"
else
    fail "golden.sha256 mismatch — generated assets changed"
fi

# ── 9. Tool-script smoke test ──────────────────────────────────────────────────
echo "[9/$TOTAL] tools/smoke_test.sh"
if (cd "$PROJ_ROOT/app/tools" && bash smoke_test.sh 2>&1); then
    ok "smoke_test.sh passed"
else
    fail "smoke_test.sh FAILED"
fi

# ── 10. app registry staleness check ───────────────────────────────────────────
echo "[10/$TOTAL] gen_app_registry staleness check"
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

# ── 11. mem_layout staleness + budget check ────────────────────────────────────
echo "[11/$TOTAL] gen_mem_layout staleness + budget check"
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

# ── 12. Documentation staleness gate (TASK-475 / M-DOCLIFE phase 1) ───────────
# Blocking: C5 (relative .md links) and C1-delta (positional citations newly
# added in the diff) — both read 0 today, which is why they can block on day
# one. C1-full, C2, C3, C4 print [warn] and cannot fail the build until their
# own rollout phase. --quiet keeps this to one gate slot so check_build.sh's
# "=== Results:" tail stays the only one in the log.
echo "[12/$TOTAL] check-docs documentation gate"
if "$PROJ_ROOT/run/check-docs" --quiet; then
    ok "documentation gate (C5 + C1-delta) clean"
else
    fail "check-docs FAILED — see the file:line list above"
fi

# ── Warn-only: settings-wiring gate (ADR-050 / M-SETTINGS-WIRE2 §6c) — WARN-ONLY ─────
# Every AppSettings field must have load/save mappings and a runtime owner
# outside app/src/settings/. Warn-only until promoted (script exits 0 unless
# --strict); does not count toward PASS/FAIL, so it is deliberately not
# numbered among the gates above.
echo "[warn] settings-wiring gate (warn-only, not counted)"
"$VENV_PY" "$PROJ_ROOT/app/tools/check_settings_wiring.py" || true

echo
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
