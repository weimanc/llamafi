#!/usr/bin/env bash
# Smoke-test: verify tool scripts resolve paths without FileNotFoundError.
# Does not bake anything — just imports and --help dry-runs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"

# 1. Import check — catches missing-file errors at module load
# TASK-481: bake_skin.py lives in bake/ now; coords.py stays flat.
"$PYTHON" -c "import sys; sys.path.insert(0, 'bake'); import coords; import bake_skin" 2>&1 | grep -q "FileNotFoundError" && {
    echo "FAIL: FileNotFoundError during import" >&2; exit 1
}

# 2. bake_wave.sh --help dry-run — catches stale -o path in shell script
output=$(bash bake/bake_wave.sh --help 2>&1 || true)
if echo "$output" | grep -q "No such file or directory"; then
    echo "FAIL: bake_wave.sh --help reported missing file" >&2
    echo "$output" >&2
    exit 1
fi

# 3. check-docs harness — T_DOC_01..09 (TASK-475).
# Runs here rather than as its own check_build.sh gate so the documentation
# gate itself (gate 12) stays one slot: gate 9 covers the CHECKER, gate 12
# runs it against the live corpus. Host-side only, no DUT, ~2 s.
# TASK-481: check_*.py + test_check_*.py live in gate/ now.
if ! "$PYTHON" gate/test_check_docs.py; then
    echo "FAIL: test_check_docs.py (T_DOC_01..09) FAILED" >&2
    exit 1
fi

# 4. player-mode binding gate — M-TESTBASE §8.4 (TASK-512).
# Asserts the resolvePlayerTap -> playerCycle -> playerBind -> T_PMT_00 chain is
# intact. TASK-413 added a dispatch path and left the harness on the old surface
# with every gate green; this is the check that would have caught it.
if ! "$PYTHON" gate/check_player_binding.py; then
    echo "FAIL: check_player_binding.py (M-TESTBASE §8.4) FAILED" >&2
    exit 1
fi

# 4b. suite/serialdbg/ cross-file Name-reference gate (TASK-480/TASK-545).
# A pure code move can't introduce a logic bug but can absolutely drop an
# import — caught 3 times live during TASK-480's split (_drain_data_pipeline,
# _tap_and_wait_log, _tb_precondition), each time only after a DUT run threw
# a NameError hours in. This is the same AST walk that caught them, made
# permanent so the next suite/serialdbg/ change gets the check for free.
if ! "$PYTHON" gate/check_suite_serialdbg_names.py; then
    echo "FAIL: check_suite_serialdbg_names.py (TASK-480/TASK-545) FAILED" >&2
    exit 1
fi

# 4c. serial-failure classifier — TASK-556.
# runner.py used to label every serial.SerialException `port-busy` and name the
# tmux monitor; a device that VANISHED mid-open (CH340 re-enumeration) got the
# same label as genuine contention, and that wrong label misdirected the same
# investigation more than once on 2026-08-31. Pure logic, no DUT, sub-second.
if ! "$PYTHON" test_serial_classify.py; then
    echo "FAIL: test_serial_classify.py (TASK-556 classifier) FAILED" >&2
    exit 1
fi

# 4d. boot-observation gate — TASK-560.
# _wait_for_ready() used to return silently when no boot banner appeared within
# 2 s, skipping every readiness gate below it with no trace. The bannerless case
# cannot be produced on hardware on demand, so the branch is stubbed here.
if ! "$PYTHON" test_boot_gate.py; then
    echo "FAIL: test_boot_gate.py (TASK-560 boot gate) FAILED" >&2
    exit 1
fi

# 5. app conformance matrix, rows A5/A6 — M-TESTARCH §2.3 (TASK-483).
# The CHECKER's own negative suite (BP-068) is blocking: a conformance gate that
# cannot be shown to fail is not a gate. The MATRIX itself is advisory today —
# it lands with one unexcepted finding (A6/Weather), and warn-only is the same
# bargain check_settings_wiring.py makes. Promote by flipping STRICT_DEFAULT in
# check_app_conformance.py once that cell is closed or excepted; the ledger
# (docs/verification/app_conformance_exceptions.md) states the criterion.
if ! "$PYTHON" gate/test_check_app_conformance.py; then
    echo "FAIL: test_check_app_conformance.py (A5/A6 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_app_conformance.py; then
    echo "FAIL: check_app_conformance.py crashed (findings are warn-only; a" \
         "non-zero exit here means the checker itself broke)" >&2
    exit 1
fi

echo "OK: smoke_test.sh passed"
