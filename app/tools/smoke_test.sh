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

echo "OK: smoke_test.sh passed"
