#!/usr/bin/env bash
# Smoke-test: verify tool scripts resolve paths without FileNotFoundError.
# Does not bake anything — just imports and --help dry-runs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"

# 1. Import check — catches missing-file errors at module load
"$PYTHON" -c "import coords; import bake_skin" 2>&1 | grep -q "FileNotFoundError" && {
    echo "FAIL: FileNotFoundError during import" >&2; exit 1
}

# 2. bake_wave.sh --help dry-run — catches stale -o path in shell script
output=$(bash bake_wave.sh --help 2>&1 || true)
if echo "$output" | grep -q "No such file or directory"; then
    echo "FAIL: bake_wave.sh --help reported missing file" >&2
    echo "$output" >&2
    exit 1
fi

# 3. check-docs harness — T_DOC_01..09 (TASK-475).
# Runs here rather than as its own check_build.sh gate so the documentation
# gate itself (gate 12) stays one slot: gate 9 covers the CHECKER, gate 12
# runs it against the live corpus. Host-side only, no DUT, ~2 s.
if ! "$PYTHON" test_check_docs.py; then
    echo "FAIL: test_check_docs.py (T_DOC_01..09) FAILED" >&2
    exit 1
fi

echo "OK: smoke_test.sh passed"
