#!/usr/bin/env bash
# Repository build + documentation gate. Run before committing structural
# changes (BP-008). Exit 0 = all checks pass. Exit non-zero = something broke.
#
# 11 counted gates: 1-6 the full firmware env matrix (ADR-061 D6), 7 golden
# assets, 8 tool smoke tests, 9 app-registry staleness, 10 mem_layout
# staleness+budget, 11 the documentation staleness gate (TASK-475). One
# additional warn-only gate (settings wiring) is deliberately not counted.
# TASK-531 (2026-08-23): cyd2usb_webradio_16k retired (EXP-012 closed,
# negative verdict, 2026-07-02) — matrix went 7 envs -> 6, gate count 12 -> 11.
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
TOTAL=11

ok()   { echo "  PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL + 1)); }

echo "=== Build check ==="
echo

# ── 1-6. Firmware build: full env matrix (ADR-061 D6) ─────────────────────────
# TASK-466: every env declared in app/platformio.ini is gated here. The
# previous 3-of-8 subset's stated reason ("a full matrix would make this gate
# unusable") was measured false — the five previously-ungated envs cold-built
# in 66 s total. [env:cyd2usb] is excluded because it is no longer a build
# target: ADR-061 D8 / TASK-467 first demoted it to the non-building
# [cyd2usb_base] base section (it FAILED to build — missing JPEGDEC.h);
# ADR-061 D9 step 4 / TASK-470 later deleted that section too, once
# cheapYellowLCD.h/.cpp (the JPEGDEC-needing plain-CYD path) had no
# dependents left — its few real build_flags/lib_deps folded straight into
# [env:cyd2usb_winamp]. TASK-531 retired cyd2usb_webradio_16k (EXP-012
# closed, negative verdict), leaving 6 buildable envs.
ENVS=(
    cyd2usb_winamp                  # production
    cyd2usb_winamp_debug            # DUT test target
    cyd2usb_player                  # TASK-422 / ADR-059 D10 — Player-only dev variant
    cyd2usb_winamp_screenlog        # SCREEN_LOG overlay variant
    cyd2usb_webradio                # TASK-255 / M-WEBRADIO-NOPSRAM experiment variant
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

# ── 7. Golden hash: generated assets unchanged ────────────────────────────────
echo "[7/$TOTAL] golden.sha256"
if (cd "$GEN_DIR" && sha256sum -c golden.sha256 --quiet 2>&1); then
    ok "golden.sha256 clean"
else
    fail "golden.sha256 mismatch — generated assets changed"
fi

# ── 8. Tool-script smoke test ──────────────────────────────────────────────────
echo "[8/$TOTAL] tools/smoke_test.sh"
if (cd "$PROJ_ROOT/app/tools" && bash smoke_test.sh 2>&1); then
    ok "smoke_test.sh passed"
else
    fail "smoke_test.sh FAILED"
fi

# ── 9. app registry staleness check ────────────────────────────────────────────
echo "[9/$TOTAL] gen_app_registry staleness check"
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

# ── 10. mem_layout staleness + budget check ────────────────────────────────────
echo "[10/$TOTAL] gen_mem_layout staleness + budget check"
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

# ── 11. Documentation staleness gate (TASK-475 / M-DOCLIFE phase 4) ───────────
# Blocking: C5 (relative .md links) and C1-delta (positional citations newly
# added in the diff) — both read 0 today, which is why they can block on day
# one. TASK-475 phase 2 (2026-08-25) added C2, which has also read 0 since
# phase 1. Phase 4 (same day) added C4, once TASK-508's header migration
# landed and re-measurement read 0. C1-full and C3 print [warn] and cannot
# fail the build until their own rollout phase (C3/phase 3 is unblocked —
# ADR-061 D8 landed — but its count is not near zero, so it stays advisory
# pending a human scope call). --quiet keeps this to one gate slot so
# check_build.sh's "=== Results:" tail stays the only one in the log.
echo "[11/$TOTAL] check-docs documentation gate"
if "$PROJ_ROOT/run/check-docs" --quiet; then
    ok "documentation gate (C5 + C1-delta + C2 + C4 + C6) clean"
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
